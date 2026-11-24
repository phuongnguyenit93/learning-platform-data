# Testing @PostAuthorize: authorized, unauthorized, and null results

## 1. Learning objectives

This lesson belongs to the **Method Testing** section of the Spring Security – Authorization module. After completing this practice, you will be able to:

- Explain why @PostAuthorize checks **the return value after method execution** and distinguish it from @PreAuthorize.
- Write ownership checks against the current user using **returnObject** and **authentication.name**.
- Use JUnit 5 and **@WithMockUser** to test three mandatory scenarios: result owned by caller, result not owned by caller, and **null** result.
- Distinguish a **deny-null** policy from an **allow-null** policy, asserting the corresponding exception or return value.
- Verify that the method actually ran even when its result was denied; avoid mistakes that commonly cause method security tests to yield false results.

Example scope: Spring Boot application using **servlet method security**, Java 17+, Spring Security 6.x (via Spring Boot 3.5.x), JUnit Jupiter. The example tests a Spring bean directly, without creating an HTTP controller or database.

## 2. What does @PostAuthorize do?

When @EnableMethodSecurity is enabled, Spring Security registers a proxy-based interceptor to enforce @PostAuthorize on Spring bean methods. For a call passing through the proxy, the basic flow is:

1. The test sets up **Authentication** (here using @WithMockUser).
2. The proxy invokes the service method; the method computes or fetches the result.
3. The interceptor evaluates the SpEL expression in @PostAuthorize. **returnObject** is the result just returned by the method; **authentication.name** is the current user's name.
4. Expression evaluates to true: the object is returned to the caller. Expression evaluates to false: by default Spring Security throws an exception in the **AccessDeniedException** hierarchy, and the caller does not receive the object.

Example rule for a document with an owner property:

~~~java
@PostAuthorize("returnObject != null and returnObject.owner == authentication.name")
public DocumentView findStrict(long id) {
    // Return the document or null.
}
~~~

The condition has two clauses evaluated with short-circuiting: the result must be non-null **and** the document owner must match the authenticated user. SpEL can access the **owner** property via the Java getter **getOwner()**.

Timing difference:

| Annotation | Decision timing | When privileges are insufficient |
| --- | --- | --- |
| @PreAuthorize | Before executing the method body | The method body is not executed |
| @PostAuthorize | After the method body returns | The method body already ran, but the result is blocked |

**Important consequence:** @PostAuthorize is suitable for protecting already-loaded read results; do not rely on it to guard write/delete operations that have side effects. Denying the return value **does not mean** automatically rolling back mutations already performed.

## 3. Locking down expectations for each case

In the sample data, document 1 belongs to **alice**, document 2 belongs to **bob**, and ID 999 does not exist. We intentionally create two methods with two null policies:

- **findStrict**: null results are denied because the condition starts with **returnObject != null**.
- **findAllowMissing**: null results are allowed to return because the condition starts with **returnObject == null**; non-null results must still match the owner.

| Caller | Method | ID | Result produced by service | Expected outcome observed by caller |
| --- | --- | ---: | --- | --- |
| alice | findStrict | 1 | DocumentView(owner=alice) | Receives the exact document |
| bob | findStrict | 1 | DocumentView(owner=alice) | AccessDeniedException |
| alice | findStrict | 999 | null | AccessDeniedException |
| alice | findAllowMissing | 999 | null | Receives null |
| alice | findAllowMissing | 2 | DocumentView(owner=bob) | AccessDeniedException |

There is no default rule that @PostAuthorize always allows or always denies null; **your expression and business policy** decide. If an expression accesses **returnObject.owner** directly without handling null, SpEL may fail with a null property-access error, which differs from an intentional access denial decision. Both expressions above avoid that pitfall.

## 4. Standalone runnable Maven project

Create the following structure (package names aligned with directories):

~~~text
post-authorize-demo/
├── pom.xml
├── src/main/java/com/example/authz/
│   ├── PostAuthorizeApplication.java
│   ├── DocumentView.java
│   └── DocumentService.java
└── src/test/java/com/example/authz/
    └── DocumentServiceSecurityTest.java
~~~

**pom.xml** — pinned versions so it is reproducible; the test starter provides JUnit Jupiter, and spring-security-test provides @WithMockUser.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>post-authorize-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**PostAuthorizeApplication.java** — enables method security. Without @EnableMethodSecurity, annotations on services may not take effect and denial tests will fail.

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }
}
~~~

**DocumentView.java** — a return object with public getters so SpEL can read the owner property.

~~~java
package com.example.authz;

public final class DocumentView {
    private final long id;
    private final String owner;

    public DocumentView(long id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }
}
~~~

**DocumentService.java** — deterministic mock data for testing. A counter proves the method body executed, even when the caller receives AccessDeniedException.

~~~java
package com.example.authz;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final AtomicInteger invocations = new AtomicInteger();

    // Null is denied: only return documents owned by the caller.
    @PostAuthorize("returnObject != null and returnObject.owner == authentication.name")
    public DocumentView findStrict(long id) {
        invocations.incrementAndGet();
        return load(id);
    }

    // Null is allowed: "not found" can be returned to the caller.
    @PostAuthorize("returnObject == null or returnObject.owner == authentication.name")
    public DocumentView findAllowMissing(long id) {
        invocations.incrementAndGet();
        return load(id);
    }

    private DocumentView load(long id) {
        if (id == 1L) {
            return new DocumentView(1L, "alice");
        }
        if (id == 2L) {
            return new DocumentView(2L, "bob");
        }
        return null;
    }

    public void resetInvocationCount() {
        invocations.set(0);
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

Both public methods are called on a **Spring-managed bean**, so calls go through the security proxy. The private method load only supplies data; it does not hold authorization policies itself.

## 5. JUnit 5 test suite: authorized, unauthorized, null

**DocumentServiceSecurityTest.java** — uses @SpringBootTest to start a real context and inject the service proxy. @WithMockUser places the specified username into SecurityContext for each test; no account needs to exist in a database.

~~~java
package com.example.authz;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService service;

    @BeforeEach
    void resetCounter() {
        service.resetInvocationCount();
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadMatchingDocument() {
        DocumentView actual = service.findStrict(1L);

        assertNotNull(actual);
        assertEquals(1L, actual.getId());
        assertEquals("alice", actual.getOwner());
        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "bob")
    void nonOwnerIsDeniedAfterMethodExecutes() {
        assertThrows(AccessDeniedException.class,
                () -> service.findStrict(1L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void strictPolicyDeniesNullResult() {
        assertThrows(AccessDeniedException.class,
                () -> service.findStrict(999L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowMissingPolicyReturnsNull() {
        assertNull(service.findAllowMissing(999L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowMissingStillDeniesAnotherOwnersDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.findAllowMissing(2L));

        assertEquals(1, service.invocationCount());
    }
}
~~~

**Why is every assertion necessary?**

1. **Authorized:** do not check only that no exception occurred; also confirm that the returned ID and owner match the expected data.
2. **Unauthorized:** assertThrows confirms the return value was blocked; an invocation count of 1 confirms that denial occurred **after** the method body ran.
3. **Null + strict policy:** does not silently receive null; must receive AccessDeniedException per the configured expression.
4. **Null + allow-missing policy:** receives exact null (not an exception), preserving "not found" semantics.
5. **Allow-missing policy still protects data:** accepting null does not mean letting an object belonging to someone else slip through.

Using **AccessDeniedException** in assertThrows catches specialized Spring Security subtypes as well; tests focus on the authorization contract rather than coupling to an overly narrow implementation class.

## 6. Run and interpret the results

In the directory containing pom.xml, JDK 17+ and Maven are required:

~~~bash
java -version
mvn -version
mvn test
~~~

If the configuration and code are right, Maven Surefire will run **5 tests**; expected **5 pass, 0 failures, 0 errors** (other log lines depend on the environment). There is no need to run the main application or make HTTP calls to test service-level authorization.

Try introducing an intentional fault to make sure the tests genuinely catch omissions: temporarily remove @EnableMethodSecurity and re-run the tests. Cases expecting AccessDeniedException will fail because the service no longer has an interceptor blocking the result. Restore the annotation after the experiment.

You can change **username="alice"** to **username="bob"** in the first test: the same document ID 1 must now be denied. Try changing **and** to **or** in findStrict: the null case will pass through, causing the strict test to catch the regression.

## 7. Common mistakes and fixes

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| Unauthorized user can still read document | Missing @EnableMethodSecurity, calling object created with new, or bypassing proxy | Inject the Spring bean in tests; keep negative tests |
| Null triggers SpEL property access error | Using returnObject.owner without a null branch | Explicitly write returnObject != null and ... or returnObject == null or ... |
| Tests always pass even with security off | Only testing allowed branch, or mocking the service bearing the annotation | Test exceptions on unauthorized calls; use real service bean and mock underlying data |
| Wrong expectation for null | Unclear whether "not found" is valid null or access denied | Define business policy first, then use assertThrows or assertNull |
| Denied yet data still changed | @PostAuthorize checks after execution, does not block prior mutations | Use @PreAuthorize before operations with side effects; place authorization at the right boundary |
| Right user passes in service test, fails with real principal | @WithMockUser creates a simple username, while app uses JWT/custom principal | Add SecurityContext or request tests with matching real Authentication |

**Note on proxies:** internal calls such as **this.findStrict(...)** within the same bean normally do not traverse the proxy and therefore do not trigger the target method's annotation. Place protected calls from another bean or inject the proxy properly when testing.

**Note on test scope:** @WithMockUser tests service-level authorization; it does **not** automatically verify JWTs, login, HTTP 403 mapping, or Spring MVC exception handling. When those contracts are needed, add separate MockMvc tests. For an **Optional.empty()** result, returnObject is a non-null Optional; do not reuse the null test's assumptions for Optional without adjusting the expression.

## 8. Acceptance checklist

- [ ] Tests use the Spring-managed **DocumentService** with **@EnableMethodSecurity** enabled.
- [ ] Authorized user receives the right DocumentView.
- [ ] Unauthorized user receives **AccessDeniedException**, not data.
- [ ] Null is tested under **both explicit policies**: deny and allow.
- [ ] Allowing null does not leak another user's document.
- [ ] Assertions verify the service **executed before** @PostAuthorize denied the result.
- [ ] Code, packages, JDK, dependencies, and test names match; **mvn test** passes.

## 9. Official documentation

- Spring Security — Method Security, section **Authorization Method Results with @PostAuthorize**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Testing Method Security**, section **@WithMockUser**: https://docs.spring.io/spring-security/reference/servlet/test/method.html

**Takeaway:** write tests around the three outcomes observable by the caller (**receiving the right object / being denied / null**), while also verifying execution timing. A good @PostAuthorize policy must state explicitly how null is handled and be tested with both allow and deny branches.