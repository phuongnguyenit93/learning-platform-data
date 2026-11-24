# Empty OpenAPI Specification Due to Scanning Conditions or Group Filters

When opening `/v3/api-docs` or a group's documentation returns valid JSON with an empty `paths` object, springdoc-openapi is usually running properly but found no endpoints matching the current scan scope. Common causes are that controllers have not been registered by Spring, package or URL scan configuration is too narrow, `GroupedOpenApi` filters exclude all endpoints, or controllers/methods are hidden with annotations.

Check the JSON returned by API docs first, then verify Spring mappings, global scanning conditions, and each group's filters in turn. This approach pinpoints the exact layer excluding endpoints instead of changing multiple settings at once.

## 1. Distinguishing an Empty Specification from Documentation Access Errors

Swagger UI not showing endpoints is not enough to conclude the specification is empty. First call API docs directly and inspect the HTTP status code and JSON content.

| Symptom | Meaning to check |
| --- | --- |
| HTTP `200`, `openapi` present, `paths` is `{}` | The document is generated, but no endpoints passed the scanning or filtering conditions. |
| HTTP `404` at `/v3/api-docs` | Check the starter, API docs path, `springdoc.api-docs.enabled` configuration, and context path. This is not evidence that filters returned an empty spec. |
| HTTP `401` or `403` | The documentation request is blocked by Spring Security or a gateway. Resolve access permissions before analyzing spec content. |
| `/v3/api-docs` has endpoints but `/v3/api-docs/{group}` is empty | Focus on that specific group's configuration and any global conditions in effect. |
| JSON has endpoints but Swagger UI is blank or shows an error | Check the JSON URL loaded by the UI, UI configuration, network errors, and browser permissions. |

Example checking the default document:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs \
  | jq '{openapi, pathCount: ((.paths // {}) | length), paths: ((.paths // {}) | keys)}'
```

For a group named `public`, check its corresponding endpoint separately:

```bash
curl -i http://localhost:8080/v3/api-docs/public
curl -sS http://localhost:8080/v3/api-docs/public \
  | jq '{openapi, pathCount: ((.paths // {}) | length), paths: ((.paths // {}) | keys)}'
```

If `jq` is unavailable, open the JSON and locate the `paths` property. A document with `paths: {}` differs from a missing endpoint or an unauthorized request.

## 2. Understanding the Conditions That Include an Endpoint in Documentation

springdoc-openapi gathers information from handlers registered by the Spring application. Simply writing a Java method in the project is not enough for it to appear in OpenAPI: the controller must be created as a bean, the method must have an HTTP mapping recognized by Spring, and the endpoint must pass filtering conditions.

Common condition layers include:

1. **Bean registration conditions:** the controller must be within component scan scope or declared as a bean via appropriate configuration. `@Profile`, `@ConditionalOnProperty`, and other bean creation conditions can prevent a controller from existing in the running environment.
2. **Package conditions:** `springdoc.packages-to-scan` or `packagesToScan(...)` restricts which packages are included in documentation. The package to match is the controller's package, not the package of services called by the controller.
3. **Path conditions:** `springdoc.paths-to-match` or `pathsToMatch(...)` only accepts mappings matching the configured patterns. A wrong prefix or pattern structure can exclude all endpoints.
4. **Exclusion conditions:** `packages-to-exclude`, `paths-to-exclude`, `packagesToExclude(...)`, and `pathsToExclude(...)` can exclude endpoints that already matched inclusion rules.
5. **Hiding conditions:** `@Hidden` on a controller or `@Operation(hidden = true)` on a method can prevent the endpoint from appearing in the spec.
6. **Group-specific conditions:** each `GroupedOpenApi` bean can restrict packages and paths differently. An endpoint present in one group but absent in another may be the intended outcome of group configuration.

When configuring both packages and paths together, check both conditions. For example, a controller belongs to `com.acme.orders.api` while its mapping is `/v1/orders`; having the right package config while `paths-to-match` only accepts `/admin/**` still leaves that controller out of the documentation.

## 3. Verifying the Controller Is Registered by Spring

Before editing springdoc configuration, verify that the application actually has the corresponding HTTP mapping. A typical controller looks like:

```java
package com.acme.orders.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {

    @GetMapping
    public String listOrders() {
        return "orders";
    }
}
```

Check the following points:

- The class has `@RestController`, or `@Controller` combined with `@ResponseBody` at the class/method level when returning data directly.
- The method has a mapping annotation such as `@GetMapping`, `@PostMapping`, or `@RequestMapping`.
- The controller's package falls within component scan scope. By default, `@SpringBootApplication` scans the package containing the application class and its subpackages; controllers in sibling packages or outside that tree need appropriate scan configuration.
- Active profiles and bean conditions in the current environment allow the controller to be registered.
- No hiding annotation was placed at the class or method level unintentionally.

You can check Spring MVC startup logs to find registered mappings. If a mapping does not exist in the application, fix component scanning, bean creation conditions, or the controller declaration first. springdoc cannot generate operations for handlers that Spring does not recognize.

## 4. Checking Global Package and Path Filters

Properties in Spring Boot configuration can restrict the entire API docs. For example:

```yaml
springdoc:
  api-docs:
    enabled: true
  packages-to-scan: com.acme.orders.api
  paths-to-match: /v1/**
```

With the configuration above, the controller must belong to the selected package and the mapping must match `/v1/**`. If the controller actually lives in `com.acme.billing.api` or the mapping starts with `/api/v1/`, the corresponding condition will not match.

Compare the configuration against actual mappings, then relax only the mismatched condition. For example, if APIs live under `/api/v1/orders`, you can adjust it to:

```yaml
springdoc:
  packages-to-scan: com.acme.orders.api
  paths-to-match: /api/v1/**
```

If the application has multiple API packages, declare all packages requiring documentation using the property syntax for your springdoc version. Do not add a broader package just to populate the JSON, as doing so may accidentally expose internal APIs in public documentation.

Also review exclusion conditions. An overly broad `packages-to-exclude` or `paths-to-exclude` setting can remove the exact packages/paths selected by inclusion rules. While investigating, temporarily remove exclusion rules one by one in a development environment to observe the impact; once the cause is found, restore the exact exclusion list.

## 5. Checking GroupedOpenApi Configuration

`GroupedOpenApi` creates separate documentation per group name. For example:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .packagesToScan("com.acme.publicapi")
                .pathsToMatch("/api/public/**")
                .build();
    }
}
```

With this example, the group's documentation is accessed at `/v3/api-docs/public`. If the controller lives in `com.acme.orders.api` or the actual mapping is `/v1/orders/**`, the `public` group does not include that controller. Check the group name, packages, paths, and exclusion conditions on this bean together.

Several situations commonly cause confusion:

- Reading `/v3/api-docs` when you should inspect `/v3/api-docs/public`, or vice versa.
- Swagger UI has a different group selected than the one just configured.
- The group name in the URL does not match the `.group("...")` value.
- The group has both `packagesToScan(...)` and `pathsToMatch(...)`, yet only one of the two conditions was checked.
- Multiple group beans have similar filters; the endpoint belongs to another group and thus does not appear in the one currently viewed.
- Both global filters and group filters narrow the scope. Check all effective configurations rather than assuming filters in one place override the other.

To isolate the issue, compare `paths` in the default document against `paths` in each group. If endpoints appear in the default document but are absent in one group, focus on group filters. If every document is empty, check component scanning, controller mappings, and global conditions first.

## 6. Checking Profiles and Effective Runtime Configuration

`application.yml` may not be the final configuration source. Spring Boot can load `application-{profile}.yml`, environment variables, command-line arguments, or deployment platform settings. A configuration that works on a local machine can still be overridden in test or production environments.

When checking, determine:

- Which profiles are active, such as `dev`, `test`, or `prod`.
- Effective values of `springdoc.packages-to-scan`, `springdoc.paths-to-match`, and exclusion properties.
- Which `GroupedOpenApi` beans are created in the current profile and their corresponding group names.
- Whether `springdoc.api-docs.enabled` is enabled.
- Whether the application uses `server.servlet.context-path` or a deployment prefix that makes the docs URL differ from the expected URL.

Distinguish two properties: `springdoc.api-docs.enabled` controls API docs; `springdoc.swagger-ui.enabled` controls the Swagger UI. Disabling the UI does not mean JSON API docs are disabled. Therefore, when the UI fails to open, call the JSON endpoint directly to identify the failing layer.

Do not expose configuration management endpoints or sensitive logs publicly just to investigate. In shared environments, inspect configuration values via controlled startup logs or an internal debugger, then remove diagnostic output once finished.

## 7. Ordered Isolation Procedure

Proceed step by step and call API docs again after each change:

1. Call `/v3/api-docs`, record the HTTP status code, and inspect `paths`.
2. If investigating a group, call `/v3/api-docs/{group}` directly and confirm the group name.
3. Verify the controller has a bean and HTTP mapping in the running application.
4. Compare the controller's package against `packages-to-scan` and exclusion conditions.
5. Compare actual mappings against `paths-to-match` and `paths-to-exclude`.
6. Check `@Hidden`, `@Operation(hidden = true)`, and profile-based bean creation conditions.
7. Compare default configuration with each `GroupedOpenApi`, while checking profile/environment variable settings.
8. After fixing, call the JSON endpoint again and confirm expected paths appear. Open Swagger UI last to verify display behavior.

For example, if `/v3/api-docs` contains `/v1/orders` while `/v3/api-docs/public` does not, the controller and mapping are already recognized by Spring. At this point fix the `public` group's filter—for instance changing `pathsToMatch("/api/public/**")` to a pattern matching the actual mapping—rather than changing component scanning for the entire application.

## 8. Testing to Prevent Regressions

Check the document's content in integration tests, not only that the endpoint returns HTTP `200`. Example with Spring MVC, MockMvc, and Jackson:

```java
MvcResult result = mockMvc.perform(get("/v3/api-docs/public"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode document = objectMapper.readTree(
        result.getResponse().getContentAsString());
JsonNode paths = document.path("paths");

assertThat(paths.size()).isGreaterThan(0);
assertThat(paths.has("/api/public/orders")).isTrue();
```

Adjust expected paths to match the application's actual mappings. With multiple groups, write separate tests for each group and assert at least one representative endpoint within that group's scope. If a group is responsible for excluding internal APIs, also verify that internal endpoints do not appear in the public document.

When changing controller packages, URL mappings, profiles, or group configurations, re-run the API docs integration tests under the corresponding profile. That way, filter changes that accidentally empty the documentation are caught immediately in CI.

## 9. Common Configuration Mistakes

| Configuration or change | Why documentation can become empty | How to fix |
| --- | --- | --- |
| `packages-to-scan` points to service package | Controllers reside in a different package so none are selected. | Use the package containing the actual controllers. |
| `paths-to-match` is `/admin/**` while mapping is `/api/**` | No mapping matches the pattern. | Fix the pattern to match registered URL mappings. |
| `packagesToScan` is right but `pathsToMatch` is wrong | Endpoints do not satisfy all conditions declared by the group. | Match both packages and paths. |
| `paths-to-exclude` covers all selected paths | Endpoints are excluded right after selection. | Narrow or remove unnecessary exclusion patterns. |
| Controller is outside component scan | Spring does not create a handler for the controller. | Adjust the application class location or component scan. |
| `@Hidden` placed on a shared controller | All operations of the controller are hidden from documentation. | Hide only the specific controllers/methods you truly want unpublished. |
| UI points to the wrong group | JSON of the selected group may be empty even though another group has endpoints. | Check the JSON URL and the selected group name. |

Do not remove all filters in production as a permanent fix. Filters usually represent the boundary between public APIs and internal APIs; fix the specific condition and re-test the published scope.

## Conclusion

A specification with empty `paths` usually indicates that no handler passed the chain of registration and filtering conditions. Start from the API docs JSON, confirm Spring mappings, then check packages, paths, hiding annotations, and group-specific configurations. Once integration tests verify that the right endpoints appear in each group, springdoc-openapi configuration remains stable across controller and deployment environment changes.
