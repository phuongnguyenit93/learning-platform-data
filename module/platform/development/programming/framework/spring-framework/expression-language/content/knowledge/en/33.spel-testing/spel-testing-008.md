# Testing Expressions Used in Spring Annotations

Spring uses Spring Expression Language (SpEL) in many annotations to evaluate values or decide runtime behavior. For example, `@Value` can inject values from expressions; Spring Security uses `@PreAuthorize` and `@PostAuthorize` to check permissions; other Spring annotations can also have their own expression contexts.

When testing, expressions must run through the exact infrastructure that processes annotations in the application. A test calling only `parseExpression()` proves the parser accepts the syntax, yet does not prove the annotation is configured properly, parameters are bound accurately, or permissions are enforced properly when the method is called.

## 1. Identifying the annotation and when the expression is evaluated

Before writing tests, identify which framework handles the annotation and at what point the expression is evaluated.

| Expression location | Appropriate testing time |
|---|---|
| `@Value("#{...}")` | When Spring creates beans and injects values |
| `@PreAuthorize` | When a method call passes through the method-security interceptor |
| `@PostAuthorize` | After the method returns a result |
| `@PreFilter` | Before the method receives the input collection |
| `@PostFilter` | After the method produces the result collection |
| SpEL called directly in Java | When the test calls `getValue()` with an EvaluationContext |

Annotations can use different expression handlers, root objects, variables, and resolution rules. Do not assume an expression running in method security will have the same context as an expression in `@Value` or a cache annotation.

Test through the real mechanism of the framework in use. For annotations processed during bean initialization, create an ApplicationContext. For annotations processed on method invocation, call Spring-managed beans through a proxy.

## 2. Testing SpEL directly when isolating expressions

If the goal is to test syntax, root objects, variables, or operators in isolation, write a unit test creating a parser and EvaluationContext:

    @Test
    void evaluatesOrderExpression() {
        OrderView order = new OrderView(
                new BigDecimal("150.00")
        );

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimum",
                new BigDecimal("100.00")
        );

        ExpressionParser parser =
                new SpelExpressionParser();

        Boolean result = parser.parseExpression(
                "total >= #minimum"
        ).getValue(context, Boolean.class);

        assertTrue(result);
    }

This test verifies the expression on a context created inside the test. It is suitable for testing standalone SpEL logic, yet does not replace annotation integration tests: Spring may provide a different root object, resolvers, converters, or variables when processing real annotations.

Separate parser/evaluation tests from integration tests so when a failure occurs, it is easy to pinpoint whether the error is in the expression or Spring configuration.

## 3. Testing values injected with @Value

With `@Value`, Spring evaluates the expression during bean creation and injects the value into a constructor, field, or setter. Start a real ApplicationContext in tests to confirm both the expression and the injection process.

Component example:

    @Component
    public class ReportSettings {

        private final String region;

        public ReportSettings(
                @Value("#{systemProperties['user.timezone']}")
                String region) {
            this.region = region;
        }

        public String getRegion() {
            return region;
        }
    }

The bean can be tested after the context is created:

    @SpringJUnitConfig(TestConfiguration.class)
    class ReportSettingsTest {

        @Autowired
        private ReportSettings settings;

        @Test
        void injectsExpressionValue() {
            assertNotNull(settings.getRegion());
        }
    }

If the expression depends on configuration properties, provide deterministic test values via `@TestPropertySource`, `@DynamicPropertySource`, or an appropriate test configuration. Example:

    @TestPropertySource(properties = {
        "reports.region=ap-southeast-1"
    })

    @Value("${reports.region}")
    private String region;

Placeholder `${...}` reads properties from Environment; expression `#{...}` is processed by SpEL. When needing to test a SpEL value combined with properties, set explicit test inputs so results do not depend on the machine running the test.

If the expression references a bean with `@beanName`, declare that bean in the test context or import the corresponding real configuration. Do not mock only the parser; verify the actual bean resolver finds the right bean and the value is injected as expected.

## 4. Testing @PreAuthorize via method-security proxy

To test `@PreAuthorize`, enable method security in the test context and call the method on a Spring-injected bean. Example:

    @Configuration
    @EnableMethodSecurity
    static class TestSecurityConfiguration {
        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    @Service
    public class DocumentService {

        @PreAuthorize("hasAuthority('document:read')")
        public String readDocument() {
            return "document";
        }
    }

Test with granted authority:

    @Test
    @WithMockUser(authorities = "document:read")
    void allowsUserWithRequiredAuthority() {
        assertEquals(
                "document",
                documentService.readDocument()
        );
    }

Test missing permission case:

    @Test
    @WithMockUser(authorities = "document:write")
    void deniesUserWithoutReadAuthority() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.readDocument()
        );
    }

`@WithMockUser` annotations belong to Spring Security Test. Tests need the corresponding test dependency and must call methods on a Spring-managed bean so the method-security interceptor actually runs.

If instantiating the object manually via `new DocumentService()`, the annotation will not be applied automatically because the call does not go through a Spring proxy.

## 5. Also checking method behavior when denied

With `@PreAuthorize`, the condition is evaluated before the method body. Besides confirming the exception, verify the method does not perform side effects when access is denied.

Example service depending on a repository:

    @Service
    public class DocumentService {

        private final DocumentRepository repository;

        public DocumentService(DocumentRepository repository) {
            this.repository = repository;
        }

        @PreAuthorize("hasAuthority('document:delete')")
        public void delete(Long id) {
            repository.deleteById(id);
        }
    }

In the test, mock the repository and confirm no delete call happens when the caller lacks authority:

    @Test
    @WithMockUser(authorities = "document:read")
    void doesNotDeleteWhenAccessIsDenied() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.delete(10L)
        );

        verify(repository, never()).deleteById(anyLong());
    }

This check proves the security boundary prevents the method from performing the operation. For methods with multiple side effects, check key dependencies to ensure they are not called when pre-authorization fails.

## 6. Testing expressions referencing method parameters

Method-security expressions often use `#parameterName` to access arguments. Example:

    @PreAuthorize(
        "#ownerId == authentication.name"
    )
    public Document findDocument(
            @P("ownerId") String ownerId) {
        return repository.findByOwner(ownerId);
    }

Tests should cover both when owner matches the principal and when it differs from the principal:

    @Test
    @WithMockUser(username = "lan")
    void allowsMatchingOwner() {
        assertNotNull(documentService.findDocument("lan"));
    }

    @Test
    @WithMockUser(username = "minh")
    void deniesDifferentOwner() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.findDocument("lan")
        );
    }

Parameter names in expressions depend on compilation metadata or annotations supplying explicit names. Java can be compiled with the `-parameters` option, or Spring Security's `@P("ownerId")` can explicitly specify the name to reference.

If the expression uses `#p0` or `#a0`, verify the exact parameter index and order. A parse-only test will not catch referencing the wrong name or wrong position.

## 7. Testing beans invoked in expressions

Method-security expressions can invoke beans via `@beanName`:

    @PreAuthorize(
        "@documentAuthorization.canRead(authentication, #documentId)"
    )
    public Document getDocument(
            @P("documentId") Long documentId) {
        return repository.findById(documentId).orElseThrow();
    }

Register the authorization bean in the test context. You can use a real bean to test domain rules, or mock the bean if the goal is to verify the expression calls the right method and passes the right arguments.

Cases to check:

- Bean name in the expression matches the registered bean name.
- The method-security expression bean resolver finds the bean.
- Current Authentication is passed accurately.
- Method argument is bound by the right name or index.
- True result allows the method to execute.
- False result denies the method before execution.

Do not mock the entire method-security infrastructure if the goal is to test annotation configuration. Let Spring evaluate the real expression, replacing only the domain dependencies the test needs to control.

## 8. Testing @PostAuthorize and returnObject

`@PostAuthorize` is evaluated after the method has run. The `returnObject` variable references the value returned by the method.

Example:

    @PostAuthorize(
        "returnObject.owner == authentication.name"
    )
    public Document load(Long id) {
        return repository.findById(id).orElseThrow();
    }

Tests need to cover both a result owned by the caller and a result owned by someone else:

    @Test
    @WithMockUser(username = "lan")
    void returnsDocumentOwnedByCurrentUser() {
        Document document = service.load(1L);
        assertEquals("lan", document.getOwner());
    }

    @Test
    @WithMockUser(username = "minh")
    void deniesDocumentOwnedByAnotherUser() {
        assertThrows(
                AccessDeniedException.class,
                () -> service.load(1L)
        );
    }

Note that the method body has already executed before the post-condition is checked. If the method has side effects, tests must verify those consequences and consider moving permission checks to `@PreAuthorize` or inside the service before performing actions. Do not use `@PostAuthorize` as the sole line of defense for irreversible operations.

## 9. Testing @PreFilter and @PostFilter

Both filter annotations use `filterObject` to reference the element currently being checked.

With `@PreFilter`, tests must verify the method receives only elements matching the predicate:

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public int countOwned(
            List<Document> documents) {
        return documents.size();
    }

With `@PostFilter`, tests verify the returned collection contains only permitted elements:

    @PostFilter(
        "filterObject.owner == authentication.name"
    )
    public List<Document> findAllVisible() {
        return repository.findAll();
    }

Test collections with multiple elements, no matching elements, a single matching element, and boundary data such as null owner if allowed by the domain.

If a method has multiple collection parameters, verify `filterTarget` points to the right parameter. For large collections, filtering after loading all data can be resource-intensive; also test repository queries and consider pushing authorization conditions down to the database.

## 10. Testing root objects and special variables per annotation

Each expression handler can supply its own root object and variables. For instance, method security provides Authentication and functions like `hasAuthority`; filter annotations provide `filterObject`; post-authorization provides `returnObject`.

Do not extract an expression from an annotation, evaluate it with a manually constructed StandardEvaluationContext, and assume the result is equivalent to the framework. A manually created context may lack the root object, method arguments, security helpers, or resolvers supplied by the framework.

If you need to unit test a piece of pure SpEL logic, build the corresponding context and explicitly verify the registered components. If you need to confirm an annotation works, test through the real bean and infrastructure.

## 11. Testing that method security is not bypassed by self-invocation

Method security is typically applied via a Spring AOP proxy. If one method in the same class directly calls another method on `this`, the internal call may bypass the proxy:

    public void process(Long id) {
        update(id);
    }

    @PreAuthorize("hasAuthority('document:write')")
    public void update(Long id) {
        // ...
    }

A test calling `process()` may not trigger the interceptor on `update()` as expected. Verify actual call paths and place security boundaries on methods invoked through the proxy. Protected methods can be extracted to a separate bean if a clear boundary is needed.

In tests, inject the service from the ApplicationContext. Do not manually instantiate the service with `new`, and do not invoke methods on an unwrapped target object when intending to test method security.

## 12. Distinguishing parse errors, evaluation errors, and authorization errors

When a test fails, identify which phase the error belongs to:

| Error type | Example | How to check |
|---|---|---|
| Parse | Invalid expression syntax | Check parser and expression string |
| Evaluation | Missing variable, bean, property, or converter | Check actual EvaluationContext and resolvers |
| Authorization | Expression returns false or insufficient permissions | Check principal, authorities, arguments, and domain data |
| Proxy/infrastructure | Annotation is not applied | Check method security, bean registration, and call path |

Do not catch every exception and treat it as access denied. For example, a bean name or property error may be a configuration mistake rather than an authorization denial decision. Tests should distinguish system errors from false authorization outcomes.

## 13. Minimal test suite for annotation expressions

For each annotation with SpEL, include appropriate cases:

1. Spring configuration starts and beans are created successfully.
2. Expression receives the right properties, variables, and needed parameters.
3. Valid users or data are allowed.
4. Users lacking permissions or invalid data are denied.
5. Method performs no side effects when pre-authorization fails.
6. Beans referenced in the expression are resolved properly.
7. Nulls, empty collections, and boundary data are handled according to contract.
8. Actual call path goes through the proxy if the annotation relies on AOP.
9. Parse/evaluation errors are distinguished from authorization errors.
10. Tests do not depend on developer-machine data or properties.

Not every annotation needs all of the cases above. Pick cases matching the context and behavior provided by the annotation.

## 14. Key takeaways

Testing expressions in annotations must go through the exact Spring mechanism that processes the annotation. For `@Value`, create an ApplicationContext and confirm the value is injected; for method security, enable `@EnableMethodSecurity`, invoke Spring-managed beans through the proxy, and test both allowed and denied cases. Verify parameter names, bean references, `returnObject`, and `filterObject` within the annotation's real context. Unit tests using the parser and EvaluationContext are useful for isolating SpEL logic, but do not replace integration tests. Always distinguish parse errors, evaluation errors, proxy configuration errors, and authorization decisions.
