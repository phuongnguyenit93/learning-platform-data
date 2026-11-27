# Coordinating CORS with Spring Security and OPTIONS Requests

## 1. Why Do CORS and Spring Security Need to Coordinate?

CORS (Cross-Origin Resource Sharing) lets a browser read a response from another origin when the server permits it. With Spring Data REST applications, the frontend often runs on its own origin, for example:

- Frontend: \`https://app.example.com\`
- API: \`https://api.example.com\`

The two addresses have different hosts, so they are cross-origin. When the frontend calls the API via JavaScript, the browser enforces the same-origin policy and inspects the CORS response headers.

Meanwhile, Spring Security checks authentication and authorization before a request reaches the controller or Spring Data REST exporter. If CORS is processed too late, a preflight request can be rejected by Spring Security before the server returns the required CORS headers.

The key point is that **CORS must be processed before Spring Security's authentication step**. Preflight requests usually do not send login session cookies such as JSESSIONID. If a security filter requires the user to be authenticated before CORS is processed, the preflight may receive 401 or 403 and the browser will not send the actual request.

Spring Security supports CORS integration via \`http.cors(...)\`. The application can provide a \`CorsConfigurationSource\` to describe permitted origins, methods, and headers.

## 2. What Is an OPTIONS Preflight?

Some cross-origin requests are sent directly by the browser. Other requests require a preliminary check step called a **preflight**. The browser sends an HTTP OPTIONS request to ask the server whether the actual request is permitted.

Preflight typically occurs when a request uses:

- A non-CORS-safelisted method, such as PUT, PATCH, or DELETE.
- A non-safelisted header, such as Authorization, If-Match, or If-None-Match.
- A Content-Type outside the safelisted values; for example, \`application/json\` usually triggers the browser to perform a preflight.

For example, the frontend wants to send a JSON PATCH with If-Match. The browser may send the request:

~~~~http
OPTIONS /people/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, if-match
~~~~

Three components to understand:

- \`Origin\` indicates which origin the web page is running on.
- \`Access-Control-Request-Method\` indicates the method of the actual request the browser intends to send.
- \`Access-Control-Request-Headers\` lists the request headers the browser wants to use.

Preflight is not the resource PATCH operation. It is a cross-origin permission negotiation step. If the preflight is accepted, the browser then sends the actual PATCH request.

Not every OPTIONS request is a preflight. A regular OPTIONS request can be an API endpoint used to discover resource capabilities. A CORS preflight can be identified by the presence of Origin, Access-Control-Request-Method, and the OPTIONS method; Spring provides \`CorsUtils.isPreFlightRequest(...)\` to check this.

## 3. Correct Processing Flow with Spring Security

The desired flow:

~~~~text
Browser
   |
   | OPTIONS + Origin + Access-Control-Request-Method
   v
Spring Security CORS filter
   |
   +-- Invalid origin/method/header --> reject preflight
   |
   +-- Valid preflight
          |
          v
       Return CORS response headers
       Do not require session cookie for preflight
          |
          v
       Browser sends actual request
          |
          v
       Spring Security authentication
          |
          v
       Authorization rules
          |
          v
       Spring Data REST / repository
          |
          v
       Actual response with CORS headers
~~~~

Spring Security's CORS filter is placed before security filters that might require authentication. When configured properly, valid preflights are handled first; the actual request still goes through authentication and authorization normally.

Allowing a preflight does not mean allowing users to read or modify resources. CORS only tells the browser whether the cross-origin request is allowed to proceed. Security rules still determine who can access the API.

## 4. Configuring CorsConfigurationSource

A common approach is declaring a \`CorsConfigurationSource\` bean. This bean describes the policy Spring Security uses when handling CORS.

Example for a frontend at \`https://app.example.com\`, needing GET, POST, PUT, PATCH, and DELETE:

~~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();

        configuration.setAllowedOrigins(
                List.of("https://app.example.com")
        );

        configuration.setAllowedMethods(List.of(
                "GET", "POST", "PUT", "PATCH", "DELETE"
        ));

        configuration.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match"
        ));

        configuration.setExposedHeaders(List.of(
                "ETag",
                "Location",
                "Link"
        ));

        configuration.setAllowCredentials(true);
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
~~~~

Meaning of each configuration setting:

| Setting | Purpose |
|---|---|
| allowedOrigins | Frontend origins permitted to access |
| allowedMethods | Actual methods the browser is permitted to send |
| allowedHeaders | Request headers the frontend is permitted to send |
| exposedHeaders | Response headers JavaScript is permitted to read |
| allowCredentials | Allows the browser to send credentials such as cookies |
| maxAge | Duration for which the browser caches the preflight result |

In the example, \`/**\` applies the policy to all URLs. If Spring Data REST has a base path such as \`/api\`, you can limit the mapping to \`/api/**\`. When an application has multiple security filter chains, ensure the chain handling REST URLs also uses the corresponding CORS configuration.

### allowedMethods and OPTIONS

In a preflight, the browser sends method OPTIONS while the \`Access-Control-Request-Method\` header contains the actual method, such as PATCH. The CORS processor checks that requested method.

Therefore, to allow PATCH requests, \`allowedMethods\` must include PATCH. Adding OPTIONS to the list does not replace allowing PATCH. Only add OPTIONS as an allowed method if the API also needs to handle regular OPTIONS requests.

### allowedHeaders and exposedHeaders

These two settings point in opposite directions:

- \`allowedHeaders\` allows the browser to send headers in requests, such as Authorization, Content-Type, If-Match.
- \`exposedHeaders\` allows JavaScript to read response headers, such as ETag, Location, or Link.

For example, if the frontend uses ETag for conditional updates, ETag must be exposed so JavaScript can read the value from the response. Adding only If-Match to allowedHeaders is not enough for reading ETag.

## 5. Enabling CORS in SecurityFilterChain

Once a \`CorsConfigurationSource\` bean exists, enable CORS in the Spring Security configuration:

~~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsUtils;
import org.springframework.web.cors.CorsConfigurationSource;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            CorsConfigurationSource corsConfigurationSource)
            throws Exception {

        http
            .cors(cors -> cors.configurationSource(
                    corsConfigurationSource
            ))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(CorsUtils::isPreFlightRequest)
                    .permitAll()
                .anyRequest()
                    .authenticated()
            );

        return http.build();
    }
}
~~~~

The \`http.cors(...)\` line instructs Spring Security to integrate the CORS filter and use the declared policy. The CORS filter processes preflights before the authorization step.

The \`CorsUtils::isPreFlightRequest\` matcher lets preflight requests pass authorization rules if they reach that step. In the standard configuration flow, the CORS filter usually handles and terminates valid preflights before the request reaches downstream filters. The permitAll rule here makes the security policy's intent explicit.

You should not simply write:

~~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~~

and assume CORS is working. That rule only lets certain OPTIONS requests pass authorization; it does not automatically generate \`Access-Control-Allow-Origin\`, \`Access-Control-Allow-Methods\`, or \`Access-Control-Allow-Headers\`. The browser will still reject the preflight if CORS response headers are invalid.

If an older Spring Security version uses a different configuration style, adjust the DSL to that version. With modern Spring Security, use a \`SecurityFilterChain\` bean and lambda DSL rather than the legacy WebSecurityConfigurerAdapter pattern.

## 6. Spring Data REST and RepositoryRestConfigurer

Spring Data REST has its own CORS support for repository resources. It can be configured at the REST exporter level using \`RepositoryRestConfigurer\`:

~~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE"
            )
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match"
            )
            .exposedHeaders(
                "ETag",
                "Location",
                "Link"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~~

This configuration applies to REST resources exported by Spring Data REST. A specific mapping such as \`/people/**\` can be used if only the people repository needs this policy.

In an application with Spring Security, keep two points in mind:

1. Spring Data REST's CORS config is applied in the REST/MVC processing layer.
2. The security filter chain runs before handler mapping. Therefore, if Spring Security blocks preflight before the request reaches Spring Data REST, RepositoryRestConfigurer configuration alone may not be sufficient.

Configure CORS in Spring Security using \`http.cors(...)\` and \`CorsConfigurationSource\` so preflights are processed before authentication. If you also keep RepositoryRestConfigurer configuration, put the same origins, methods, request headers, exposed headers, and credentials policy in both places.

Do not let the two configurations conflict. If the security filter allows broader origins than the REST config, requests may be processed with an unintended policy. If the REST config allows it but the security filter rejects the preflight earlier, the browser still will not send the actual request.

Spring MVC \`WebMvcConfigurer.addCorsMappings(...)\` should not be assumed to configure the Spring Data REST exporter. Use the right extension point for each layer and verify the actual responses.

## 7. Configuring Credentials and Cookies

If the frontend uses login session cookies, the browser needs to send credentials in cross-origin requests. The server configuration must permit credentials:

~~~~java
configuration.setAllowedOrigins(
        List.of("https://app.example.com")
);
configuration.setAllowCredentials(true);
~~~~

The frontend can use:

~~~~javascript
fetch("https://api.example.com/people", {
    method: "GET",
    credentials: "include"
});
~~~~

With cookie authentication, also check:

- Whether the cookie belongs to the appropriate domain/path.
- Whether the cookie has the Secure attribute when using HTTPS.
- Whether SameSite permits sending the cookie in the required cross-site context.
- Whether the browser blocks third-party cookies under its own policies.
- Whether CSRF protection is configured for data-modifying requests.

Do not use the wildcard origin \`*\` when allowing credentials. When \`allowCredentials(true)\`, declare specific origins or tightly controlled patterns.

If the frontend only sends an explicit bearer token in the Authorization header and does not use cookies or automatic HTTP authentication, allowCredentials can usually remain false while Authorization must still be allowed in allowedHeaders. The Authorization header and cookie credentials are two separate concerns.

Do not enable credentials just because the frontend and API are on different origins. Enable it only when requests actually require cookies or corresponding browser credentials.

## 8. CORS Does Not Replace Authentication, Authorization, and CSRF

CORS is a browser mechanism that controls whether JavaScript reads cross-origin responses. It is not a user authentication barrier.

For example:

- curl can send requests directly and does not enforce CORS policy like a browser.
- A backend service can call the API if networking and authentication permit.
- A request with valid CORS can still receive 401 from Spring Security if unauthenticated.
- An authenticated user can still receive 403 if lacking permission on the resource.
- With cookie authentication, data-modifying requests still need protection against CSRF.

Do not disable CSRF just because CORS is configured. Only consider disabling CSRF for truly stateless APIs authenticated by bearer tokens that are not automatically sent by the browser and do not rely on cookie/session ambient credentials. If using cookies/sessions, keep CSRF protection and configure an appropriate token flow with the frontend.

A valid CORS policy only answers the question: "Is this origin allowed to make cross-origin requests and read responses in the browser?". Authentication and authorization answer the questions: "Who is calling and what permissions do they have?".

## 9. Testing Preflight with curl

curl does not enforce the same-origin policy, but it can send a simulated preflight to inspect response headers.

For example, the frontend wants to PATCH JSON and send If-Match:

~~~~bash
curl -i -X OPTIONS \
  "https://api.example.com/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type, if-match"
~~~~

The expected response has headers similar to:

~~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, If-Match, If-None-Match
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~~

Valid preflight status codes can be 200 or 204 depending on configuration. What matters is that the CORS response headers permit the exact origin, method, and request headers the browser asked for.

If the browser sends \`Access-Control-Request-Headers: content-type, if-match\`, the server must allow both headers. Header names are case-insensitive, but the values need to match the policy.

## 10. Testing the Actual Request After Preflight

After the preflight succeeds, the browser sends the actual request. Example:

~~~~bash
curl -i -X PATCH \
  "https://api.example.com/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Content-Type: application/merge-patch+json" \
  -H 'If-Match: "7"' \
  -H "Authorization: Bearer <access-token>" \
  -d '{"firstName":"Alice Smith"}'
~~~~

The actual request still must pass authentication and authorization. If the token is missing or expired, the API may return 401. If the user lacks permission, the API may return 403. These are normal security outcomes, not indications that the CORS preflight failed.

If the frontend needs to read ETag or Location in the response, check that the header appears in \`Access-Control-Expose-Headers\`. Otherwise, the browser may receive the response yet JavaScript will not be able to read those headers.

## 11. Allowing Only Preflight, Not All OPTIONS

Some security configurations use:

~~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~~

This lets all OPTIONS requests pass authorization across all URLs. If the application has business OPTIONS endpoints or many routes, this rule may be broader than necessary.

Prefer identifying CORS preflights:

~~~~java
.requestMatchers(CorsUtils::isPreFlightRequest).permitAll()
~~~~

This targets only OPTIONS requests structured as a CORS preflight. Regular OPTIONS requests remain subject to the corresponding security rules.

However, permitAll does not replace CorsConfigurationSource. A preflight from a disallowed origin must still be rejected by the CORS processor. Do not use permitAll to open the entire API to all origins.

## 12. Multiple SecurityFilterChains and Filter Order

Large applications can have multiple \`SecurityFilterChain\` beans, for example:

- One chain for /api/**.
- One chain for /actuator/**.
- One chain for form login and web pages.
- A separate chain for the Spring Data REST base path.

In that case, check:

1. Which chain matches the repository resource URL.
2. Whether that chain enables \`http.cors(...)\`.
3. Whether CorsConfigurationSource has a mapping for that URL.
4. Whether the CORS filter comes before authentication/authorization filters.
5. Whether preflights are being intercepted by a different chain first.
6. Whether all relevant chains share the intended policy.

If Spring Data REST uses base path /api, the CORS mapping and security matcher must match /api/**. Do not configure CorsConfigurationSource for /rest/** when repositories actually live at /api/**.

When debugging multiple chains, enable appropriate Spring Security logging to determine which chain matched and which filter returned the response. Do not add a broad permitAll to mask selecting the wrong chain.

## 13. Testing with MockMvc

You can simulate preflights with MockMvc:

~~~~java
mockMvc.perform(options("/people/42")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "PATCH")
        .header(
            "Access-Control-Request-Headers",
            "content-type, if-match"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.com"
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("PATCH")
    ));
~~~~

If the test setup uses status 204 for preflight, adjust the matcher to match the actual configured response. You should also verify:

- Permitted origins receive Access-Control-Allow-Origin.
- Disallowed origins do not receive the allow-origin header.
- PATCH is allowed when Access-Control-Request-Method is PATCH.
- The If-Match header is allowed when requested by the browser.
- ETag is exposed when the frontend needs to read it.
- Preflight does not require a session cookie.
- The actual PATCH request still requires authentication.
- The actual request is rejected when permissions are lacking.
- CSRF is still enforced appropriately with cookie authentication.

MockMvc tests can verify the filter chain and response headers in the application. Real browser testing remains helpful to verify cookies, SameSite, credentials mode, and browser behavior.

## 14. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| OPTIONS returns 401 | Preflight is handled by authentication before CORS | Enable http.cors() and provide CorsConfigurationSource |
| OPTIONS returns 403 | Origin, method, or request header is not in policy; or blocked by security chain | Check Access-Control-Request-* and CORS policy |
| Preflight succeeds but PATCH returns 401 | Actual request is missing or has invalid authentication | Check token/session of the actual request |
| Preflight succeeds but PATCH returns 403 | User lacks permission or CSRF token is missing | Check authorization and CSRF separately |
| Configured only RepositoryRestConfigurer yet OPTIONS is still blocked | Security filter chain blocks before REST handler mapping | Configure CORS in Spring Security |
| Permitted OPTIONS yet browser still reports CORS | Authorization lets it through, but response lacks CORS headers | Configure CorsConfigurationSource; permitAll is not enough |
| PATCH rejected even though OPTIONS is permitted | allowedMethods does not contain PATCH | Add PATCH to allowedMethods |
| If-Match rejected in preflight | allowedHeaders lacks If-Match | Add If-Match to allowedHeaders |
| JavaScript cannot read ETag | ETag is not in exposedHeaders | Expose ETag |
| Cookies are not sent | allowCredentials or cookie attributes are incorrect | Check credentials, SameSite, Secure, and domain |
| CORS works on one route but not another | Mapping or SecurityFilterChain does not cover the URL | Check base path, matcher, and source mapping |
| Regular OPTIONS endpoint gets overly broad access | Used permitAll for all OPTIONS | Use CorsUtils.isPreFlightRequest |
| curl succeeds but browser fails | curl does not enforce CORS policy | Inspect preflight and browser DevTools |
| Wildcard origin combined with credentials | Invalid CORS configuration for credentials | Use a specific origin or a controlled pattern |

## 15. Deployment Checklist

Before releasing the API, confirm:

- [ ] Frontend origin is identified accurately by scheme, host, and port.
- [ ] CorsConfigurationSource covers the actual Spring Data REST URLs.
- [ ] SecurityFilterChain enables http.cors(...).
- [ ] CORS is processed before authentication.
- [ ] Valid preflights do not require a session cookie.
- [ ] allowedMethods includes the actual methods the frontend intends to call.
- [ ] allowedHeaders includes custom headers such as Authorization, Content-Type, If-Match.
- [ ] exposedHeaders includes ETag, Location, or Link if JavaScript needs to read them.
- [ ] allowCredentials is enabled only when cookies/credentials are required.
- [ ] If using RepositoryRestConfigurer, the policy does not conflict with Spring Security's policy.
- [ ] Actual requests still require authentication and authorization.
- [ ] CSRF is configured according to the authentication model, not disabled just for CORS.
- [ ] Valid origins, invalid origins, preflights, and actual requests have been tested.
- [ ] If multiple SecurityFilterChains exist, the chain for REST APIs also has CORS configured.

## 16. Conclusion

When Spring Data REST runs alongside Spring Security, CORS must be processed before authentication so browser OPTIONS preflights are not rejected merely because the request does not yet carry a login session cookie. Configuring \`CorsConfigurationSource\` describes origins, methods, request headers, exposed response headers, and credentials; \`http.cors(...)\` enables CORS integration in SecurityFilterChain.

A valid preflight only permits the browser to send the actual request. The actual request must still pass authentication, authorization, and appropriate CSRF policies. With Spring Data REST, RepositoryRestConfigurer can configure CORS for the REST exporter; if also using the Spring Security CORS filter, keep both policies consistent and ensure the security filter chain covers the right URLs. Permit only CORS preflights using the appropriate matcher; allowing all OPTIONS does not automatically generate CORS headers. Verify preflight, the actual request, and response headers separately in a browser.

## References

- [Spring Security Reference — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — CORS configuration API](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Framework Reference — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
