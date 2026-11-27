# Securing Resolvers with Spring Security

A single GraphQL operation can request multiple fields in one request. Therefore, securing the `/graphql` URL only authenticates the sender of the request; the application must also verify which resolvers that user is allowed to invoke and which fields they can read. With Spring for GraphQL, you can use Spring Security method security to enforce rules directly on `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`, `@BatchMapping`, and `@SubscriptionMapping` methods.

This hands-on practice uses JWT Bearer tokens, `@EnableMethodSecurity`, and `@PreAuthorize` to protect member queries, salary fields, and update mutations. The examples use Spring Boot 3+, Spring Security 6+, and Spring for GraphQL.

## 1. Understanding the Two Security Layers in GraphQL

There are two distinct security questions:

- **Authentication:** Who is the request from? For example, is the token valid and unexpired?
- **Authorization:** What is that user allowed to do? For example, do they have permission to read the member list, view salaries, or update emails?

The HTTP layer protects the GraphQL endpoint and authenticates the token before GraphQL executes the operation. The method security layer checks permissions as each resolver is invoked. A query may request `member { id fullName salary }`; a user might have permission to read basic information but not `salary`. In that case, the `salary` resolver needs its own rule.

Do not treat permission on a root query as proof that all child fields are permitted. A field can be reached from different queries, mutations, fragments, or resolvers. Place rules at the exact execution points where sensitive data is accessed.

## 2. Adding Dependencies

With Gradle and Spring Boot dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

`spring-boot-starter-security` provides Spring Security and method security. `spring-boot-starter-oauth2-resource-server` enables the application to validate JWT Bearer tokens. `spring-security-test` provides annotations and utilities for mocking users in tests.

## 3. Protecting the GraphQL Endpoint with JWT

Declare the token issuer in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
```

Replace the illustrative URL with your system's actual issuer. Spring Boot configures `JwtDecoder` to verify signatures, expiration, and issuer based on the provider's metadata.

Create the security configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class GraphQlSecurityConfiguration {

    @Bean
    SecurityFilterChain graphQlSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This is an illustrative configuration for a stateless API that only accepts access tokens in the `Authorization: Bearer ...` header. Under this model, browsers do not automatically attach Bearer tokens the way they do cookies, so disabling CSRF aligns with that assumption. If the application authenticates via sessions or cookies, keep CSRF protection enabled and require clients to send CSRF tokens; do not copy `csrf.disable()` to a cookie-based setup.

The example uses `/graphql` as the default endpoint. If the application changes `spring.graphql.path`, the matcher in `SecurityFilterChain` must change accordingly. `anyRequest().permitAll()` is solely for clarity in this example; in a real application, declare policies for all other endpoints according to system requirements.

When a JWT is missing or invalid, the HTTP security filter rejects the request before GraphQL runs. For an authenticated request lacking permission for a specific field, method security rejects the corresponding resolver invocation.

## 4. Understanding Authorities Generated from JWT

Under the resource server's default configuration, values in the `scope` or `scp` claim are converted into authorities prefixed with `SCOPE_`. For example, if a token has the claim:

```json
{
  "sub": "user-184",
  "scope": "members:read members:salary:read"
}
```

Spring Security creates the authorities `SCOPE_members:read` and `SCOPE_members:salary:read`. We will use these exact strings in `@PreAuthorize`.

`hasAuthority("...")` matches the authority string exactly. `hasRole("ADMIN")` conventionally prepends `ROLE_`, so do not mix the two when tokens issue standard OAuth2 scopes. If your system uses `roles`, `permissions`, or a custom claim structure, configure a `JwtAuthenticationConverter` to map claims into the appropriate `GrantedAuthority` instances.

## 5. Securing Queries and Mutations with `@PreAuthorize`

Suppose the schema has a query to fetch a member and a mutation to update email:

```graphql
type Query {
    member(id: ID!): Member
}

type Member {
    id: ID!
    fullName: String!
    email: String!
    salary: String
}

input UpdateMemberEmailInput {
    memberId: ID!
    email: String!
}

type Mutation {
    updateMemberEmail(input: UpdateMemberEmailInput!): Member
}
```

Place `@PreAuthorize` on the resolver methods:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

record UpdateMemberEmailInput(String memberId, String email) {}

@Controller
public class MemberGraphQlController {

    private final MemberService memberService;

    public MemberGraphQlController(MemberService memberService) {
        this.memberService = memberService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('SCOPE_members:read')")
    public Member member(@Argument("id") String id) {
        return memberService.findById(id);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('SCOPE_members:write')")
    public Member updateMemberEmail(
            @Argument("input") UpdateMemberEmailInput input) {
        return memberService.updateEmail(input.memberId(), input.email());
    }
}
```

`@EnableMethodSecurity` enables method security so `@PreAuthorize` is enforced. Spring Security evaluates the expression before running the resolver method. If the authority check fails, the call is rejected and `memberService` is never invoked.

Read and write permissions should be kept separate. A token with `SCOPE_members:read` does not automatically grant `SCOPE_members:write`. Avoid checking only a broad role like `USER` for every operation when operations carry different sensitivity levels.

## 6. Securing Sensitive Fields with `@SchemaMapping`

The `member` query can return a `Member` object; when the client selects the `salary` field, Spring GraphQL invokes that field's dedicated resolver. We can require an additional authority:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.security.access.prepost.PreAuthorize;

@SchemaMapping(typeName = "Member", field = "salary")
@PreAuthorize("hasAuthority('SCOPE_members:salary:read')")
public String salary(Member member) {
    return memberService.findSalary(member.id());
}
```

Users with `SCOPE_members:read` but without `SCOPE_members:salary:read` can still read basic fields. When GraphQL executes the `salary` field, Spring Security denies only this resolver. Because SDL declares `salary: String` as nullable, GraphQL can return the other fields of `Member` alongside an error at `salary`.

Illustrative response example:

```json
{
  "data": {
    "member": {
      "id": "42",
      "fullName": "Nguyen An",
      "email": "an@example.com",
      "salary": null
    }
  },
  "errors": [
    {
      "message": "You do not have permission to access this field",
      "path": ["member", "salary"],
      "extensions": {
        "classification": "FORBIDDEN"
      }
    }
  ]
}
```

The response above illustrates the case where a field resolver is denied and the error is mapped as shown in section 9. If the schema declares a sensitive field as non-null, e.g., `salary: String!`, an error causing the field to resolve to null can propagate null up to the parent object per GraphQL's non-null rules. Choose nullability to match your API contract.

## 7. Checking Per-Resource Permissions

The `SCOPE_members:read` authority only indicates that the user is allowed to read member-type data. It does not prove they are allowed to read every member. Multi-tenant applications often need to check which tenant the user belongs to or whether they own a specific record.

You can combine scope checks and per-resource authorization in the same expression:

```java
import org.springframework.security.core.parameters.P;

@QueryMapping
@PreAuthorize("hasAuthority('SCOPE_members:read') " +
        "and @memberAuthorization.canRead(authentication, #memberId)")
public Member member(
        @Argument("id") @P("memberId") String id) {
    return memberService.findById(id);
}
```

`@P("memberId")` explicitly names the parameter for the SpEL expression, without relying on whether the compiler preserves parameter names. The `memberAuthorization` bean is registered in Spring with the matching name:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("memberAuthorization")
public class MemberAuthorization {

    private final MemberRepository memberRepository;

    public MemberAuthorization(MemberRepository memberRepository) {
        this.memberRepository = memberRepository;
    }

    public boolean canRead(Authentication authentication, String memberId) {
        return memberRepository.existsByIdAndOwnerSubject(
                memberId, authentication.getName());
    }
}
```

`existsByIdAndOwnerSubject` is an example repository method to be defined according to your data model. With JWT, `authentication.getName()` typically retrieves the token's subject (`sub`) under default configuration. If your system uses a tenant claim or another internal identifier, map and verify that trusted attribute instead.

Never accept `ownerId`, `tenantId`, or privileged roles from input and trust them directly for authorization decisions. Those values must come from the authenticated identity or be verified against stored records. In addition, the service/domain layer should retain permission checks if the same operations are also called from REST APIs, background jobs, or other non-resolver paths.

## 8. Protecting Other Resolver Types

Method security applies to Spring-managed methods, so you can place the annotation on other GraphQL handlers as well:

```java
@BatchMapping(typeName = "Team", field = "members")
@PreAuthorize("hasAuthority('SCOPE_members:read')")
public Map<Team, List<Member>> members(List<Team> teams) {
    return memberService.findMembersByTeams(teams);
}

@SubscriptionMapping
@PreAuthorize("hasAuthority('SCOPE_members:events:read')")
public Publisher<MemberEvent> memberEvents() {
    return memberService.memberEvents();
}
```

These illustrate where annotations apply; `Team`, `MemberEvent`, and service methods depend on your application. For `@BatchMapping`, check permissions per parent or inside the service when a batch contains resources belonging to different tenants. A coarse authority check does not replace per-record authorization.

For subscriptions over WebSocket, authenticate the connection/handshake and establish identity for the GraphQL session according to your application's WebSocket mechanism. `@PreAuthorize` checks permissions when the subscription method is called; if permissions can change while a stream stays open, consider re-checking permissions per event or before emitting sensitive data.

## 9. Standardizing Access-Denied Errors

When a resolver is reached and method security denies access, GraphQL represents the execution error in the `errors` array. You can use `@GraphQlExceptionHandler` to return a safe message and classify the error as `FORBIDDEN`:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlSecurityAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You do not have permission to access this field")
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` preserves location and path information for the failing field. The message does not reveal tenant names, record existence, internal policies, or exception details. You can omit the `exception` parameter if you do not need to inspect it.

Unauthenticated requests blocked at the HTTP filter normally receive HTTP 401 before GraphQL runs. Authenticated requests lacking permission for a resolver receive a GraphQL error classified as `FORBIDDEN`. The two situations occur at different layers; clients should handle both HTTP status codes and GraphQL's `errors` array.

## 10. Testing Method Security with `GraphQlTester`

Add tests confirming that users with the right scope can execute the query and users lacking the scope are denied before the service is called. `@WithMockUser` establishes authentication in tests; `GraphQlTester` executes GraphQL directly, so this example focuses on method security rather than testing the HTTP JWT filter.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(MemberGraphQlController.class)
@Import({MemberGraphQlSecurityTest.MethodSecurityTestConfig.class,
        GraphQlSecurityAdvice.class})
class MemberGraphQlSecurityTest {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    MemberService memberService;

    @Test
    @WithMockUser(authorities = "SCOPE_members:read")
    void readerCanExecuteMemberQuery() {
        graphQlTester.document("""
                query {
                    member(id: "42") {
                        id
                        fullName
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isEmpty());

        verify(memberService).findById("42");
    }

    @Test
    @WithMockUser(authorities = "SCOPE_members:basic")
    void userWithoutReadScopeIsDeniedBeforeServiceCall() {
        graphQlTester.document("""
                query {
                    member(id: "42") {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage()
                                .contains("do not have permission")));

        verifyNoInteractions(memberService);
    }

    @TestConfiguration
    @EnableMethodSecurity
    static class MethodSecurityTestConfig {}
}
```

The passing test above only verifies that there are no GraphQL errors; to verify returned data, stub `memberService.findById` to return a `Member` and assert the corresponding paths. You can add a test for the `salary` field to prove that having member-read scope does not grant permission to view salaries.

`@MockitoBean` is available in Spring Framework 6.2+. For earlier versions, use the mock bean mechanism supported by your project version, such as `@MockBean`. To test the actual HTTP and JWT layers, add integration tests with `MockMvc`/`WebTestClient` covering valid Bearer tokens, expired tokens, wrong-issuer tokens, and requests without a token.

## 11. Common Security Mistakes

- **Only requiring login on `/graphql`.** Authenticated users can still invoke sensitive mutations or fields if resolvers lack authorization rules.
- **Only protecting root queries.** Field resolvers, batch resolvers, and other mutations can expose paths to the same data; enforce rules at the corresponding execution points.
- **Using `hasRole` for scopes.** `hasRole` automatically prepends `ROLE_`; default resource server scopes carry the `SCOPE_` prefix, so use `hasAuthority` with the exact value.
- **Trusting IDs or tenants sent by the client.** A valid ID does not prove the caller has access to that record. Check the resource against the authenticated identity.
- **Checking permissions only in controllers.** If a service is called from another API or background job, that call path bypasses the controller. Enforce critical business authorization rules in the service/domain layer.
- **Disabling CSRF in cookie/session-based apps.** Browsers automatically send cookies, which can enable unintended requests. Only use stateless Bearer-token configuration when your authentication setup genuinely meets that assumption.
- **Returning exception details to clients.** Use generic messages, stable error codes, and detailed server-side logs consistent with data protection policies.
- **Forgetting to secure WebSocket subscriptions.** Verify how the handshake/connection is authenticated and how permissions are maintained over the lifetime of the stream.

## 12. Completion Exercises

Starting from `MemberGraphQlController`, complete the following tasks:

1. Configure the resource server to validate JWTs and protect the `/graphql` endpoint.
2. Require `SCOPE_members:read` for the `member` query and `SCOPE_members:write` for the update mutation.
3. Create the `salary` field restricted to users with `SCOPE_members:salary:read`.
4. Add owner or tenant-based authorization per member; never trust a client-supplied `ownerId`.
5. Standardize `AccessDeniedException` into a `FORBIDDEN` GraphQL error and confirm the response includes the denied field's path.
6. Write tests for a user with the required scope, a user missing the scope, and a user with read scope but without salary-read scope.

After completing these tasks, ask yourself: how does request authentication differ from resolver authorization; why do child fields need separate rules; how does `hasAuthority` differ from `hasRole`; and why is permission to read a resource type insufficient to allow reading every record of that type?
