<?php
// Run in an isolated Pelican panel container with --network none, no mounts.
require '/var/www/html/vendor/autoload.php';

$importer = (new ReflectionClass(App\Services\Eggs\Sharing\EggImporterService::class))->newInstanceWithoutConstructor();
$egg = $importer->parse(stream_get_contents(STDIN), App\Enums\EggFormat::YAML);
$toggle = collect($egg['variables'])->firstWhere('env_variable', 'AUTO_UPDATE');

if (!$toggle || !$toggle['user_viewable'] || !$toggle['user_editable']
    || (string) $toggle['default_value'] !== '0' || !in_array('boolean', $toggle['rules'], true)) {
    throw new RuntimeException('Missing or invalid AUTO_UPDATE variable');
}

foreach (['0', '1'] as $value) {
    $variable = new App\Models\EggVariable();
    $variable->forceFill(['env_variable' => 'AUTO_UPDATE', 'default_value' => '0', 'server_value' => $value]);
    $server = new App\Models\Server();
    $server->setRelation('variables', new Illuminate\Database\Eloquent\Collection([$variable]));
    $environment = (new App\Services\Servers\EnvironmentService())->handle($server);
    if ($environment['AUTO_UPDATE'] !== $value) {
        throw new RuntimeException('Toggle was not exported to the server environment');
    }
}

if (!str_contains($egg['startup_commands']['Default'], 'AUTO_UPDATE')) {
    throw new RuntimeException('Imported startup does not reference the toggle');
}
echo "PASS: native Pelican YAML import and environment export (0 and 1), no database writes\n";
