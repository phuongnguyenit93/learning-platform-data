# Downloading JSON or YAML from a Running Documentation Endpoint

Springdoc-openapi generates an OpenAPI document from the controllers, models, configuration, and Swagger annotations of a Spring Boot application. While the application is running, the document can be retrieved directly via an HTTP endpoint. Under the default configuration, the JSON endpoint is `/v3/api-docs`, and the YAML endpoint is `/v3/api-docs.yaml`.

Downloading directly from a running endpoint is useful when you need to inspect the API contract of an environment, save an artifact for review, feed the specification into a CI pipeline, or pass the documentation to an SDK generator tool. You must call the right endpoint and the right group, authenticate if the documentation is protected, and inspect the downloaded content to avoid saving an HTML error page under a JSON/YAML filename.

## 1. Default documentation endpoints

When using springdoc-openapi with Spring MVC or WebFlux, the common endpoints are:

| Content | Default endpoint |
|---|---|
| OpenAPI JSON | `/v3/api-docs` |
| OpenAPI YAML | `/v3/api-docs.yaml` |
| Group OpenAPI JSON | `/v3/api-docs/{group-name}` |
| Group OpenAPI YAML | `/v3/api-docs.yaml/{group-name}` |
| Swagger UI entry | `/swagger-ui.html` |
| Swagger UI assets | `/swagger-ui/**` |
| Swagger UI config | `/v3/api-docs/swagger-config` |

Example when the application runs on port 8080:

~~~text
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
http://localhost:8080/swagger-ui.html
~~~

The first two endpoints return the OpenAPI document in two different formats. Swagger UI is an interface for presenting and interacting with the documentation; the Swagger UI URL is not a JSON/YAML specification file to save directly.

The URLs above are defaults. An application can change `springdoc.api-docs.path`, the context path, the WebFlux base path, or be placed behind a reverse proxy with a prefix. In that case, you must use the environment's actual public URL.

## 2. Prerequisites for downloading the documentation

Before calling the endpoint, verify:

1. The Spring Boot application has started and is listening on the right host/port.
2. The project includes the springdoc starter matching Spring MVC or WebFlux.
3. API docs are enabled.
4. The proxy/gateway routes the documentation endpoint to the application.
5. The security policy allows your account or token to read the documentation.
6. You are calling the right group and the right base path if the application has custom configuration.

You can enable or disable the API docs endpoint via configuration:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

If you set `enabled: false`, the OpenAPI endpoint is not served under that configuration. The `springdoc.swagger-ui.enabled` property controls Swagger UI separately; disabling the UI does not automatically disable the JSON/YAML endpoint.

Example disabling only the UI while still allowing specification downloads:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Conversely, if API docs are disabled, Swagger UI has no document to load even though the UI page may still be configured. Check both components according to your deployment purpose.

## 3. Downloading JSON with curl

Simple command to save OpenAPI JSON to a file:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Options:

- `-f` makes curl return an error when the HTTP status is 400 or higher.
- `-S` displays the error message when the command fails.
- `-o openapi.json` writes the response body to a file instead of printing it to the terminal.

If the application redirects the URL, you can add `-L` to follow redirects:

~~~bash
curl -fSL http://localhost:8080/v3/api-docs -o openapi.json
~~~

Do not omit `-f` in an export script without checking the status code. If the server returns a login page or an error page with HTTP 200, curl may still save that content to the file. Therefore, you must verify the JSON after downloading.

## 4. Downloading YAML with curl

YAML has a dedicated endpoint, typically by adding the `.yaml` suffix:

~~~bash
curl -fS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

Do not rename a JSON file to `openapi.yaml` to create YAML. The file extension does not convert the content; you must call the YAML endpoint or use a controlled conversion tool.

JSON and YAML represent the same OpenAPI document. The difference lies mainly in serialization syntax; the `openapi`, `info`, `servers`, `paths`, `components` structures and operations carry the exact same meaning.

## 5. Downloading JSON and YAML in a single run

A shell script can download both formats:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8080"
OUTPUT_DIR="build/openapi"

mkdir -p "$OUTPUT_DIR"

curl -fS "$BASE_URL/v3/api-docs" \
  -o "$OUTPUT_DIR/openapi.json"

curl -fS "$BASE_URL/v3/api-docs.yaml" \
  -o "$OUTPUT_DIR/openapi.yaml"
~~~

`set -e` makes the script stop when a download command fails. This prevents the pipeline from continuing to package or publish an artifact that was not created successfully.

If using the script in CI, pass the base URL via an environment variable or pipeline parameter. Do not hard-code a local URL when the same script needs to run in test or production.

## 6. Downloading files on Windows PowerShell

In PowerShell, you can use `Invoke-WebRequest`:

~~~powershell
$BaseUrl = "http://localhost:8080"
Invoke-WebRequest -Uri "$BaseUrl/v3/api-docs" -OutFile ".\openapi.json"
Invoke-WebRequest -Uri "$BaseUrl/v3/api-docs.yaml" -OutFile ".\openapi.yaml"
~~~

On Windows, `curl` may be an alias for `Invoke-WebRequest` in some PowerShell versions. If you want to run the actual curl executable, invoke `curl.exe` explicitly:

~~~powershell
curl.exe -fS "http://localhost:8080/v3/api-docs" -o ".\openapi.json"
curl.exe -fS "http://localhost:8080/v3/api-docs.yaml" -o ".\openapi.yaml"
~~~

For pipelines, configure error handling so subsequent steps run only when the request succeeds.

## 7. Downloading documentation when the endpoint requires a Bearer token

API docs may be protected by Spring Security. When the endpoint requires an access token, send the token in the Authorization header:

~~~bash
curl -fS \
  -H "Authorization: Bearer $OPENAPI_TOKEN" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
~~~

The `OPENAPI_TOKEN` variable should be supplied from the environment's secret store or a CI secret variable. Do not put tokens directly in source code, committed YAML files, or pipeline logs.

PowerShell:

~~~powershell
$Headers = @{ Authorization = "Bearer $env:OPENAPI_TOKEN" }
Invoke-WebRequest -Uri "https://test.example.com/v3/api-docs" -Headers $Headers -OutFile ".\openapi-test.json"
~~~

If using HTTP Basic, an API key, or another authentication mechanism, the header must match the application's actual security scheme. Do not assume every docs endpoint uses a Bearer token.

## 8. Downloading documentation by group

When an application declares multiple `GroupedOpenApi` beans, each group has its own document. Example:

~~~java
@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/admin/**")
                .build();
    }
}
~~~

With group names `public` and `admin`, the default endpoints typically take the form:

~~~text
/v3/api-docs/public
/v3/api-docs.yaml/public
/v3/api-docs/admin
/v3/api-docs.yaml/admin
~~~

Download the public group:

~~~bash
curl -fS http://localhost:8080/v3/api-docs/public -o openapi-public.json
curl -fS http://localhost:8080/v3/api-docs.yaml/public -o openapi-public.yaml
~~~

The group name in the URL must match the `group(...)` value exactly. If the group does not exist or the proxy does not route the group URL, the server may return 404.

A group only determines which operations appear in the corresponding document. It does not by itself protect runtime endpoints and does not restrict who can download the document; configure Spring Security separately if a group's documentation has restricted access scope.

## 9. Downloading from a path changed via springdoc.api-docs.path

You can change the API docs path:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

When changing the path, the default JSON endpoint moves to the configured path. The YAML endpoint typically uses the corresponding `.yaml` suffix. With the configuration above, check the URLs:

~~~text
/openapi
/openapi.yaml
~~~

If the application has groups, also check the group endpoints under the new path. With `/openapi` configured as the path, the common forms are `/openapi/{group}` for JSON and `/openapi.yaml/{group}` for YAML. Verify against the exact springdoc version you are running.

After changing the path, update artifact download scripts, reverse proxy or ingress routes, Spring Security request matchers, the Swagger UI config URL if declared explicitly, and any monitoring checks referencing the docs endpoint.

## 10. Distinguishing JSON/YAML endpoints from Swagger UI

Swagger UI is a web application for viewing and trying out APIs. It typically loads configuration from `/v3/api-docs/swagger-config`, then fetches the OpenAPI JSON from the configured spec endpoint.

| URL | Purpose | Is it a direct specification file? |
|---|---|---|
| `/swagger-ui.html` | Swagger UI entry page | No |
| `/swagger-ui/index.html` | Swagger UI interface page | No |
| `/v3/api-docs/swagger-config` | Configuration for Swagger UI | No |
| `/v3/api-docs` | OpenAPI JSON | Yes |
| `/v3/api-docs.yaml` | OpenAPI YAML | Yes |

If you want to save an artifact for review or feed it into a code generator, download the JSON/YAML endpoint. Do not download the Swagger UI HTML and rename the extension to `.json`.

## 11. Verifying that the downloaded JSON file is valid

After downloading, use `jq` to parse the JSON:

~~~bash
jq empty openapi.json
~~~

If the file is valid JSON, the command succeeds without printing any output. Check the version field:

~~~bash
jq -r '.openapi' openapi.json
~~~

Check the metadata and list of paths:

~~~bash
jq '.info' openapi.json
jq '.paths | keys' openapi.json
~~~

If `jq` reports a parse error, check whether the server returned a login/error HTML page, whether the URL redirected, whether the response was replaced or truncated by a proxy, or whether the file was overwritten by another pipeline step.

## 12. Verifying the downloaded YAML file

YAML needs to be read with a YAML parser. If the environment has a YAML-capable version of `yq` installed, you can check:

~~~bash
yq '.openapi' openapi.yaml
yq '.info' openapi.yaml
yq '.paths | keys' openapi.yaml
~~~

There are multiple tools named `yq` with different syntaxes. Follow the documentation for the exact version installed. Another option is to convert YAML to JSON with a suitable parser and inspect the `openapi` and `paths` fields.

Do not just check that the file exists or has a size greater than 0. An HTML error page is also a non-empty file. You must parse the content and confirm it has an OpenAPI structure.

## 13. Checking HTTP status and response headers

When debugging exports, also save the response headers:

~~~bash
curl -sS -D openapi-headers.txt \
  -o openapi.json \
  -w "HTTP %{http_code}\nContent-Type: %{content_type}\n" \
  http://localhost:8080/v3/api-docs
~~~

Details to inspect: HTTP status, `Content-Type`, redirect Location, whether the response is JSON/YAML or HTML, and whether cache/proxy headers caused a stale document to be returned.

| Status | Possible interpretation | How to handle |
|---|---|---|
| 200 | Document returned | Parse and verify content |
| 301/302/307/308 | URL redirected | Inspect Location and follow redirects intentionally |
| 401 | Missing or invalid credentials | Supply appropriate credentials/token |
| 403 | Authenticated but unauthorized | Check authorization rules |
| 404 | Wrong path, group, or proxy route | Check docs path and group name |
| 500 | Error generating document or application error | Inspect application logs at request time |

HTTP 200 alone does not guarantee the content is OpenAPI. A reverse proxy or identity gateway may return a login page with status 200; a JSON/YAML parser will catch this case.

## 14. Downloading through a reverse proxy or context path

If the application runs behind a proxy with a public prefix, the download URL must use the path accessible to clients. Example public base URL:

~~~text
https://test.example.com/order-service
~~~

The public endpoints may be:

~~~text
https://test.example.com/order-service/v3/api-docs
https://test.example.com/order-service/v3/api-docs.yaml
~~~

The proxy may preserve the prefix or strip the prefix before forwarding the request to the application. Therefore, the upstream URL does not necessarily match the public URL. Check the proxy configuration, forwarded headers, and context path according to the actual topology.

If an MVC application has `server.servlet.context-path` or WebFlux has `spring.webflux.base-path`, the docs endpoints usually reside under that base path. Do not double the prefix between the proxy and the application.

## 15. Choosing the environment when exporting

Do not assume a document downloaded from local is completely identical to test or production. Each environment may differ in Spring profiles, profile-specific controllers/beans, groups/filters, security schemes, server URLs, context paths, proxy prefixes, Jackson, and validation.

| Environment | Example base URL | Artifact |
|---|---|---|
| Local | `http://localhost:8080` | `openapi-local.json` |
| Test | `https://test.example.com/order-service` | `openapi-test.json` |
| Production | `https://api.example.com` | `openapi-prod.json` |

If the goal is to verify the contract running in test, download from the test endpoint. Documentation generated from local may not accurately reflect the configuration, profiles, or operations of test.

## 16. Naming and storing traceable artifacts

In CI, name files to reflect the environment, group, and build version:

~~~text
artifacts/
  openapi/
    openapi-public-test.json
    openapi-public-test.yaml
    openapi-admin-test.json
~~~

You can include the commit SHA or build number in the artifact name, for example `openapi-public-test-<build-id>.json`. The filename should help trace which environment and which time/build the document was downloaded from. Do not put tokens, passwords, or sensitive data into filenames or metadata.

## 17. Using environment variables in export scripts

Do not hard-code the base URL in a script if the same script needs to run across multiple environments:

~~~bash
#!/usr/bin/env bash
set -eo pipefail

if [ -z "$API_BASE_URL" ]; then
  echo "API_BASE_URL is required" >&2
  exit 1
fi

OUTPUT_DIR="build/openapi"
mkdir -p "$OUTPUT_DIR"

curl -fS "$API_BASE_URL/v3/api-docs" -o "$OUTPUT_DIR/openapi.json"
curl -fS "$API_BASE_URL/v3/api-docs.yaml" -o "$OUTPUT_DIR/openapi.yaml"

jq -e '.openapi and .paths' "$OUTPUT_DIR/openapi.json" > /dev/null
~~~

This script requires `API_BASE_URL` to be declared, downloads both formats, and checks several core fields in the JSON. This check is only a sanity check; it does not replace an OpenAPI validator.

If the endpoint requires a token, add the Authorization header from a CI secret variable. Avoid enabling shell tracing such as `set -x` in sections handling secrets because the token could be written to logs.

## 18. Automating specification downloads in CI

A basic pipeline can run in this order:

1. Start the application or deploy the application to the test environment.
2. Wait for the health check to report the application is ready.
3. Call the JSON/YAML endpoint.
4. Check the HTTP status and parse the file.
5. Run an OpenAPI validator or contract checks.
6. Save the file as a build artifact.
7. Use the artifact in SDK generation, breaking-change comparison, or developer portal publishing steps.

Do not download the documentation immediately when the process is created if the application is not yet ready. Wait for the health endpoint or use the platform's readiness mechanism to avoid intermittent connection errors.

Example shell snippet after the application is ready:

~~~bash
set -euo pipefail
mkdir -p build/openapi

curl --retry 10 --retry-connrefused --retry-delay 2 -fS \
  "$API_BASE_URL/v3/api-docs" \
  -o build/openapi/openapi.json

jq -e '.openapi and (.paths | type == "object")' \
  build/openapi/openapi.json > /dev/null
~~~

Retries should only be used for transient startup errors. If you receive 401, 403, or 404 due to misconfiguration, the pipeline should fail so the root cause can be fixed rather than looping endlessly.

## 19. Comparing documentation downloaded from two builds

Once an OpenAPI artifact is saved, you can compare it with a previous build's version to detect new/removed operations, changes to request parameters/bodies, response statuses/schemas, required fields, enums, data constraints, security requirements, or server URLs.

Do not just compare bytes of JSON/YAML because key ordering, formatting, or metadata that do not affect the contract may change. Use an OpenAPI diff tool that understands the document structure and the project's compatibility rules.

## 20. Common errors when downloading JSON/YAML

| Symptom | Possible cause | Resolution |
|---|---|---|
| `/v3/api-docs` returns 404 | Missing springdoc, API docs disabled, or wrong context path | Check starter, `springdoc.api-docs.enabled`, and base path |
| JSON downloads but YAML returns 404 | Proxy does not route the .yaml suffix or custom path differs | Check the application's YAML endpoint and proxy |
| Group endpoint returns 404 | Wrong group name or group not declared | Check `GroupedOpenApi` and group URL |
| JSON file is actually HTML | Redirect/login page or proxy error page | Check status, Location, Content-Type, and parse JSON |
| File is empty or truncated | Interrupted connection or proxy response limit | Check curl exit code, proxy logs, and response size |
| HTTP 401 | Missing token/credentials | Send the proper Authorization header |
| HTTP 403 | Account lacks permission to view documentation | Adjust role/authority according to policy |
| Swagger UI works but curl is rejected | Browser and shell use different credentials/sessions | Configure authentication for the export script |
| Downloaded documentation from wrong environment | Wrong base URL from environment variable | Print base URL without secrets and verify environment |
| OpenAPI paths are missing prefix | Incorrect forwarded headers or proxy rewrite | Check `servers`, `paths`, and public request |
| CI uses stale file | Export step did not run or output directory kept old artifact | Use a clean workspace or check timestamp/build id |
| Renamed .json to .yaml but parser errors | Only renamed the file without converting serialization | Download the YAML endpoint or use a converter |

## 21. Checklist before using an artifact

- [ ] Selected the right base URL and environment.
- [ ] Application is ready to receive requests.
- [ ] Called the right JSON or YAML endpoint.
- [ ] Selected the right group if the application has multiple documents.
- [ ] Sent credentials via a secret variable if the endpoint is protected.
- [ ] HTTP status is successful.
- [ ] File is non-empty and parseable.
- [ ] The `openapi` field has the expected version.
- [ ] `info`, `paths`, and `components` contain appropriate content.
- [ ] `servers` does not point to localhost or unintended internal hostnames.
- [ ] Artifact is named and stored by build/environment for traceability.

## 22. Design principles

- Use `/v3/api-docs` to download JSON and `/v3/api-docs.yaml` to download YAML by default.
- Use group endpoints when you need documentation for a specific set of operations.
- Distinguish between Swagger UI, Swagger config, and the OpenAPI document.
- Check custom docs path, context path, WebFlux base path, and proxy prefix.
- Download from the exact environment that the contract needs to represent.
- Pass credentials via a secret store or environment variables, never hard-coded.
- Check HTTP status, response headers, and file content after downloading.
- Do not treat file existence or HTTP 200 as proof of a valid document.
- Save artifacts with traceable names and use an OpenAPI-aware diff/validator in CI.
- Keep Swagger UI and JSON/YAML endpoints enabled/disabled independently according to deployment needs.

## Conclusion

When a Spring Boot application is running with springdoc-openapi, you can directly download OpenAPI JSON from `/v3/api-docs` and YAML from `/v3/api-docs.yaml`. For multiple documents, use group endpoints; if you changed the docs path, context path, or placed the application behind a proxy, call the configured public URL. Use curl or PowerShell to save files, send credentials securely when needed, and verify both status and content with a parser. In CI, only store and use the artifact after a successful download, valid parsing, and confirmation of the right environment, group, and OpenAPI version.

## References

- [springdoc-openapi v2 FAQ: OpenAPI groups and group endpoints](https://springdoc.org/v2/faq.html)
- [springdoc-openapi Core Properties: `springdoc.api-docs.path` and `springdoc.api-docs.enabled`](https://springdoc.org/core-properties.html)
- [springdoc-openapi issue #1600: YAML endpoint for a group](https://github.com/springdoc/springdoc-openapi/issues/1600)
