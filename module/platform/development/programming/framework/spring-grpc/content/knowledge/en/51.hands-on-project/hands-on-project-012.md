# Writing Unit, Integration, and Contract Tests

A gRPC service can return the right result when invoked directly in a unit test and still fail over a real channel: the service might not be registered with Spring, wire method names might mismatch, serialization might change, or the server might return a different status than what the client expects. Therefore, gRPC testing requires multiple layers, each verifying a specific boundary.

In this hands-on project, you will test `AccountService.GetAccount` across three dimensions:

- **Unit tests** verify business rules and how the adapter translates results/errors into responses or gRPC statuses.
- **Integration tests** invoke the service through a gRPC channel to verify generated stubs, serialization, dispatch, and end-to-end statuses.
- **Contract tests** verify services, methods, messages, and fields in Protocol Buffers, and check whether schema updates remain compatible with the published baseline.

The examples use JUnit 5, Mockito, Spring Boot Test, and gRPC's in-process transport. They continue the account lookup problem with IDs formatted as `ACC-` followed by six digits.

## Objectives and Scope

Upon completion, the test suite should prove the following behaviors:

| Scenario | Behavior to Verify |
| --- | --- |
| Valid and existing ID | Returns the expected account ID, owner, currency, balance, and active status. |
| Empty or malformed ID | Client receives `INVALID_ARGUMENT`. |
| Valid ID format, but not found | Client receives `NOT_FOUND`. |
| Unexpected application error | Client receives `INTERNAL` with a safe description. |
| Proto unexpectedly renames service, method, or field numbers | Contract test fails. |
| Updated proto is incompatible with published schema | Schema compatibility check fails in CI. |

## 1. Organizing Test Layers

```text
                    AccountService
                          |
              +-----------+-----------+
              |           |           |
           Unit test  Integration   Contract test
              |        test             |
              |           |             |
         Application   gRPC channel   Proto descriptor
         service       + server       + schema baseline
         gRPC adapter  + generated    + compatibility
                       stub
```

| Test Type | Scope | External Dependencies | When to Run |
| --- | --- | --- | --- |
| Unit | A single class or narrow boundary | Mock/fake dependencies | Every build and during development. |
| Integration | Multiple components working together over transport | gRPC server/channel; optionally Spring context | Every pull request. |
| Contract | API structure and backwards compatibility | Generated descriptors and schema baseline | Every proto change, before release. |

Unit tests should form the majority of the suite because they run fast and isolate failures cleanly. Integration tests are fewer in number, yet must go through gRPC stubs to catch issues unit tests miss. Contract tests are small and focus on wire contract details that must stay stable.

## 2. Setting Up Project and Test Dependencies

Assume the application already contains the components from the `AccountService` lesson:

```text
src/main/proto/account.proto

src/main/java/com/example/accounts/
  application/AccountApplicationService.java
  domain/Account.java
  domain/AccountNotFoundException.java
  domain/InvalidAccountIdException.java
  infrastructure/AccountRepository.java
  infrastructure/InMemoryAccountRepository.java
  grpc/AccountGrpcEndpoint.java

src/test/java/com/example/accounts/
  application/AccountApplicationServiceTest.java
  grpc/AccountGrpcEndpointTest.java
  grpc/AccountGrpcTransportIntegrationTest.java
  grpc/AccountSpringContextTest.java
  contract/AccountProtoContractTest.java
```

In Gradle, test dependencies typically include:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation "io.grpc:grpc-inprocess:${grpcVersion}"
}
```

`spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring Test. `grpc-inprocess` must match the same gRPC Java version used by runtime modules. If your project manages versions via a BOM, omit the explicit version and let dependency management resolve it.

With Maven, declare `spring-boot-starter-test` and `io.grpc:grpc-inprocess` in `test` scope. Do not introduce an independent gRPC version line solely for running tests.

Ensure proto code generation runs before compiling tests. Contract tests inspect descriptors generated from the exact same `.proto` file the application uses.

## 3. Unit Testing the Application Service

The application service validates the ID format and then queries the repository. This is the right place to verify business rules without starting Spring or a gRPC server.

Example `AccountApplicationServiceTest.java`:

```java
package com.example.accounts.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.accounts.domain.Account;
import com.example.accounts.domain.AccountNotFoundException;
import com.example.accounts.domain.InvalidAccountIdException;
import com.example.accounts.infrastructure.AccountRepository;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AccountApplicationServiceTest {

    @Mock
    AccountRepository repository;

    @InjectMocks
    AccountApplicationService applicationService;

    @Test
    void returnsAccountWhenIdExists() {
        Account expected = new Account(
                "ACC-000001", "Nguyen An", "VND", 12_500_000L, true);
        when(repository.findById("ACC-000001"))
                .thenReturn(Optional.of(expected));

        Account actual = applicationService.findById("ACC-000001");

        assertEquals(expected, actual);
        verify(repository).findById("ACC-000001");
    }

    @Test
    void rejectsMalformedIdBeforeRepositoryLookup() {
        assertThrows(InvalidAccountIdException.class,
                () -> applicationService.findById("ACC-12"));

        verifyNoInteractions(repository);
    }

    @Test
    void reportsNotFoundWhenValidIdDoesNotExist() {
        when(repository.findById("ACC-999999"))
                .thenReturn(Optional.empty());

        assertThrows(AccountNotFoundException.class,
                () -> applicationService.findById("ACC-999999"));
    }
}
```

These tests verify three branches: found, malformed ID, and valid ID with no record. `verifyNoInteractions(repository)` proves validation runs before data access. If the ID rule changes, update the unit tests at this layer alongside the corresponding business contract.

## 4. Unit Testing the gRPC Adapter

The adapter translates application service exceptions into gRPC statuses. We can test it using a recording `StreamObserver` without starting a server.

Ensure the implementation follows explicit terminal rules:

```java
package com.example.accounts.grpc;

import com.example.accounts.application.AccountApplicationService;
import com.example.accounts.domain.Account;
import com.example.accounts.domain.AccountNotFoundException;
import com.example.accounts.domain.InvalidAccountIdException;
import com.example.accounts.v1.AccountServiceGrpc;
import com.example.accounts.v1.GetAccountRequest;
import com.example.accounts.v1.GetAccountResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class AccountGrpcEndpoint
        extends AccountServiceGrpc.AccountServiceImplBase {

    private static final Logger log =
            LoggerFactory.getLogger(AccountGrpcEndpoint.class);

    private final AccountApplicationService accounts;

    public AccountGrpcEndpoint(AccountApplicationService accounts) {
        this.accounts = accounts;
    }

    @Override
    public void getAccount(
            GetAccountRequest request,
            StreamObserver<GetAccountResponse> responseObserver) {
        final GetAccountResponse response;
        try {
            Account account = accounts.findById(request.getAccountId());
            response = GetAccountResponse.newBuilder()
                    .setAccountId(account.accountId())
                    .setOwnerName(account.ownerName())
                    .setCurrency(account.currency())
                    .setBalanceMinor(account.balanceMinor())
                    .setActive(account.active())
                    .build();
        } catch (InvalidAccountIdException ex) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid account_id")
                    .asRuntimeException());
            return;
        } catch (AccountNotFoundException ex) {
            responseObserver.onError(Status.NOT_FOUND
                    .withDescription("Account was not found")
                    .asRuntimeException());
            return;
        } catch (RuntimeException ex) {
            log.error("Unexpected error while retrieving account", ex);
            responseObserver.onError(Status.INTERNAL
                    .withDescription("Unable to retrieve account")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
```

In a real application, the `INTERNAL` branch should log the exception server-side with a correlation ID; never send stack traces or database connection details to the client. This concise snippet focuses on the behavior under test.

Create `AccountGrpcEndpointTest.java`:

```java
package com.example.accounts.grpc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.when;

import com.example.accounts.application.AccountApplicationService;
import com.example.accounts.domain.Account;
import com.example.accounts.domain.AccountNotFoundException;
import com.example.accounts.domain.InvalidAccountIdException;
import com.example.accounts.v1.GetAccountRequest;
import com.example.accounts.v1.GetAccountResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AccountGrpcEndpointTest {

    @Mock
    AccountApplicationService accounts;

    @InjectMocks
    AccountGrpcEndpoint endpoint;

    @Test
    void emitsOneResponseAndCompletesOnSuccess() {
        when(accounts.findById("ACC-000001"))
                .thenReturn(new Account(
                        "ACC-000001", "Nguyen An", "VND", 12_500_000L, true));
        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();

        endpoint.getAccount(request("ACC-000001"), observer);

        assertEquals(1, observer.nextCount);
        assertTrue(observer.completed);
        assertNull(observer.error);
        assertEquals("ACC-000001", observer.value.getAccountId());
    }

    @Test
    void mapsInvalidInputToInvalidArgument() {
        when(accounts.findById("bad-id"))
                .thenThrow(new InvalidAccountIdException());
        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();

        endpoint.getAccount(request("bad-id"), observer);

        assertStatus(Status.Code.INVALID_ARGUMENT, observer);
        assertEquals(0, observer.nextCount);
        assertFalse(observer.completed);
    }

    @Test
    void mapsMissingAccountToNotFound() {
        when(accounts.findById("ACC-999999"))
                .thenThrow(new AccountNotFoundException());
        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();

        endpoint.getAccount(request("ACC-999999"), observer);

        assertStatus(Status.Code.NOT_FOUND, observer);
    }

    @Test
    void mapsUnexpectedFailureToInternalWithoutLeakingDetails() {
        when(accounts.findById("ACC-000001"))
                .thenThrow(new IllegalStateException("database credentials"));
        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();

        endpoint.getAccount(request("ACC-000001"), observer);

        assertStatus(Status.Code.INTERNAL, observer);
        assertEquals("Unable to retrieve account",
                Status.fromThrowable(observer.error).getDescription());
    }

    private static GetAccountRequest request(String id) {
        return GetAccountRequest.newBuilder().setAccountId(id).build();
    }

    private static void assertStatus(
            Status.Code expected, RecordingObserver<?> observer) {
        assertNotNull(observer.error);
        assertEquals(expected, Status.fromThrowable(observer.error).getCode());
        assertEquals(0, observer.nextCount);
        assertFalse(observer.completed);
    }

    private static final class RecordingObserver<T> implements StreamObserver<T> {
        private T value;
        private Throwable error;
        private int nextCount;
        private boolean completed;

        @Override
        public void onNext(T value) {
            this.value = value;
            nextCount++;
        }

        @Override
        public void onError(Throwable error) {
            this.error = error;
        }

        @Override
        public void onCompleted() {
            completed = true;
        }
    }
}
```

In this unit test, `StreamObserver` runs synchronously inside the method call because the endpoint executes logic directly. When testing over a gRPC channel, callbacks cross the transport and must be handled like a real RPC invocation.

## 5. Integration Testing Over the gRPC In-Process Transport

Unit tests do not verify whether the generated stub invokes the right method or whether protobuf serializes and deserializes cleanly. The following integration test uses `InProcessServerBuilder` and `InProcessChannelBuilder`: requests traverse the gRPC client/server pipeline without opening a TCP port.

Example `AccountGrpcTransportIntegrationTest.java`:

```java
package com.example.accounts.grpc;

import static org.junit.jupiter.api.Assertions.*;

import com.example.accounts.application.AccountApplicationService;
import com.example.accounts.domain.Account;
import com.example.accounts.infrastructure.AccountRepository;
import com.example.accounts.v1.AccountServiceGrpc;
import com.example.accounts.v1.GetAccountRequest;
import com.example.accounts.v1.GetAccountResponse;
import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.Server;
import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AccountGrpcTransportIntegrationTest {

    private Server server;
    private ManagedChannel channel;
    private AccountServiceGrpc.AccountServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        AccountRepository repository = accountId -> {
            if ("ACC-000001".equals(accountId)) {
                return Optional.of(new Account(
                        "ACC-000001", "Nguyen An", "VND", 12_500_000L, true));
            }
            if ("ACC-000002".equals(accountId)) {
                throw new IllegalStateException("database unavailable");
            }
            return Optional.empty();
        };

        AccountApplicationService applicationService =
                new AccountApplicationService(repository);
        AccountGrpcEndpoint endpoint = new AccountGrpcEndpoint(applicationService);
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(endpoint)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        stub = AccountServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void sendsRequestAndReceivesSerializedResponse() {
        GetAccountResponse response = stub.getAccount(
                GetAccountRequest.newBuilder()
                        .setAccountId("ACC-000001")
                        .build());

        assertEquals("ACC-000001", response.getAccountId());
        assertEquals("Nguyen An", response.getOwnerName());
        assertEquals("VND", response.getCurrency());
        assertEquals(12_500_000L, response.getBalanceMinor());
        assertTrue(response.getActive());
    }

    @Test
    void returnsInvalidArgumentToGrpcClient() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getAccount(request("bad-id")));

        assertEquals(Status.Code.INVALID_ARGUMENT, error.getStatus().getCode());
    }

    @Test
    void returnsNotFoundToGrpcClient() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getAccount(request("ACC-999999")));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }

    @Test
    void returnsInternalToGrpcClient() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getAccount(request("ACC-000002")));

        assertEquals(Status.Code.INTERNAL, error.getStatus().getCode());
        assertEquals("Unable to retrieve account", error.getStatus().getDescription());
    }

    private static GetAccountRequest request(String id) {
        return GetAccountRequest.newBuilder().setAccountId(id).build();
    }
}
```

This test exercises the generated blocking stub, gRPC method dispatch, protobuf serialization/deserialization, and status propagation. `directExecutor()` keeps small tests simple, though it does not exercise multi-threaded scheduling or race conditions. It also opens no sockets and does not verify TLS.

When you need to test TLS, HTTP/2, port binding, load balancers, or network timeouts, add an integration test with a real TCP server in the test environment. Never treat in-process tests as proof that TLS or network configuration is correct.

## 6. Testing Spring Context and Component Discovery

The in-process test above instantiates the endpoint via its constructor to isolate the transport. It does not prove Spring created the beans and recognized `@GrpcService`. Add a context test to verify wiring:

```java
package com.example.accounts.grpc;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.example.accounts.application.AccountApplicationService;
import com.example.accounts.infrastructure.AccountRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(properties = "spring.grpc.server.port=0")
class AccountSpringContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsApplicationAndGrpcBeans() {
        assertNotNull(context.getBean(AccountApplicationService.class));
        assertNotNull(context.getBean(AccountRepository.class));
        assertNotNull(context.getBean(AccountGrpcEndpoint.class));
    }
}
```

Port `0` asks the OS to assign an ephemeral port for the test server, avoiding collisions in parallel test runs. The exact property name and test server management behavior depend on your Spring gRPC version; check the configuration for your project's version. If your version does not support `0`, use the random port or test server mechanism documented for that version.

The context test confirms Spring discovers the beans, including `@GrpcService` implementations, and that server auto-configuration starts in tests. Combine it with in-process transport tests to cover two distinct layers: Spring wiring and the gRPC request/response pipeline. If you need to verify the exact TCP port and network exposure, add a test calling a client against the test server's bound port.

## 7. Contract Testing Protocol Buffers

Contract tests protect the details shared by client and server: service name, method name, input/output types, and field numbers. Field numbers are part of the binary wire format; never change a published field's number just because its name changed.

Example `AccountProtoContractTest.java`:

```java
package com.example.accounts.contract;

import static org.junit.jupiter.api.Assertions.*;

import com.example.accounts.v1.AccountApiProto;
import com.example.accounts.v1.GetAccountRequest;
import com.example.accounts.v1.GetAccountResponse;
import com.google.protobuf.Descriptors;
import org.junit.jupiter.api.Test;

class AccountProtoContractTest {

    @Test
    void keepsServiceAndMethodIdentity() {
        Descriptors.ServiceDescriptor service = AccountApiProto.getDescriptor()
                .findServiceByName("AccountService");

        assertNotNull(service);
        assertEquals("accounts.v1.AccountService", service.getFullName());

        Descriptors.MethodDescriptor method =
                service.findMethodByName("GetAccount");

        assertNotNull(method);
        assertEquals("accounts.v1.GetAccountRequest",
                method.getInputType().getFullName());
        assertEquals("accounts.v1.GetAccountResponse",
                method.getOutputType().getFullName());
    }

    @Test
    void keepsRequestFieldNumberAndType() {
        Descriptors.FieldDescriptor accountId = GetAccountRequest.getDescriptor()
                .findFieldByName("account_id");

        assertNotNull(accountId);
        assertEquals(1, accountId.getNumber());
        assertEquals(Descriptors.FieldDescriptor.Type.STRING, accountId.getType());
    }

    @Test
    void keepsResponseFieldNumbers() {
        Descriptors.Descriptor response = GetAccountResponse.getDescriptor();

        Descriptors.FieldDescriptor accountId = response.findFieldByName("account_id");
        Descriptors.FieldDescriptor ownerName = response.findFieldByName("owner_name");
        Descriptors.FieldDescriptor currency = response.findFieldByName("currency");
        Descriptors.FieldDescriptor balance = response.findFieldByName("balance_minor");
        Descriptors.FieldDescriptor active = response.findFieldByName("active");

        assertNotNull(accountId);
        assertNotNull(ownerName);
        assertNotNull(currency);
        assertNotNull(balance);
        assertNotNull(active);
        assertEquals(1, accountId.getNumber());
        assertEquals(2, ownerName.getNumber());
        assertEquals(3, currency.getNumber());
        assertEquals(4, balance.getNumber());
        assertEquals(5, active.getNumber());
        assertEquals(Descriptors.FieldDescriptor.Type.INT64, balance.getType());
        assertEquals(Descriptors.FieldDescriptor.Type.BOOL, active.getType());
    }
}
```

These tests fail if anyone accidentally modifies service/method identities, input/output types, or field numbers in the proto. If the project renames a field while keeping its field number for wire compatibility, update the name assertion deliberately and document the impact on generated code; never alter the field number.

The contract test above checks the current schema against expectations hardcoded in the test. It does not automatically compare against a previously published proto version. To catch breaking changes between two schema versions, add a schema compatibility check in CI.

## 8. Schema Compatibility Checking in CI

Rules when modifying protos:

- Never change the field number of a published field.
- Never reuse the number of a deleted field.
- Use `reserved` for retired field numbers and names.
- Never change protobuf package, service name, or RPC method names without a client/server migration plan.
- When adding a field, pick a new number and evaluate the default value old clients will see.
- When adding an enum value, check how older clients handle unknown enum values.

Example when removing an old field from a message:

```proto
message GetAccountResponse {
  reserved 6;
  reserved "legacy_label";

  string account_id = 1;
  string owner_name = 2;
  string currency = 3;
  int64 balance_minor = 4;
  bool active = 5;
}
```

Never assign a new field to number 6 or reuse the name `legacy_label` once reserved. Reserving lets the compiler prevent accidental reuse in future schema edits.

You can use Buf to lint and compare the current schema against a published baseline. Example CI commands, with the baseline stored on the main Git branch:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

Ensure the repository includes a valid `buf.yaml` and the baseline branch contains the latest released or approved proto version. Buf configuration and baseline source syntax must match your project's CLI version. `buf lint` enforces schema conventions; `buf breaking` catches incompatible changes against the configured rule set. Keep both descriptor contract tests and schema compatibility checks, as they catch different classes of errors.

## 9. Client-Side Status and Deadline Testing

A gRPC client receives errors as `StatusRuntimeException` when using a blocking stub. Client tests should assert the status code, and assert the description only when that wording is part of an API contract the team commits to keeping stable.

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.withDeadlineAfter(1, TimeUnit.MILLISECONDS)
                .getAccount(validRequest));

assertEquals(Status.Code.DEADLINE_EXCEEDED, error.getStatus().getCode());
```

Use the pattern above only when the test controls an intentionally slow service. Never put an aggressively tiny deadline on a normal service expecting it to always time out; machine load and thread scheduling can make results flaky. A better approach is a test service that blocks until the deadline expires, or uses a latch to control when the server completes.

For retries, cancellation, and deadlines, isolate each behavior into its own test:

- Deadline expires before server responds: client observes `DEADLINE_EXCEEDED`.
- Client actively cancels: server receives the cancellation signal and stops cancellable work.
- Retries trigger: only policy-approved statuses and operations are retried; never blindly retry `INVALID_ARGUMENT`.

These tests complement the basic unary tests; they do not replace success, validation, and contract tests.

## 10. Running Tests and Organizing CI

Run the full test suite via the build wrapper:

```bash
# Gradle
./gradlew clean test

# Maven
mvn clean test
```

A CI pipeline can execute steps in this order:

1. Lint and run breaking-change checks on proto files.
2. Generate Java code from proto and compile sources.
3. Run unit tests for application services and gRPC adapters.
4. Run integration tests over the in-process gRPC transport.
5. Boot the Spring context to verify bean wiring and service registration.
6. Archive test reports and fail the pipeline if any test layer fails.

In multi-module repositories, run tests in modules containing protos/services as well as dependent client modules. Ensure CI uses the exact committed JDK and wrapper rather than relying on stale generated sources on developer machines.

## 11. Test Matrix and Acceptance Criteria

| Check | Unit | Integration | Contract |
| --- | :---: | :---: | :---: |
| ID validation | Yes | Yes | No |
| Repository lookup | Yes | Yes, with fake or test DB | No |
| Status mapping | Yes | Yes, via client stub | No |
| Protobuf serialization | No | Yes | Descriptor/schema |
| Spring bean wiring | No | Spring context test | No |
| Service/method names | No | May surface on call | Yes |
| Field numbers/types | No | Can affect serialization | Yes |
| Backwards compatibility with published schema | No | Insufficient to verify | Buf breaking/baseline |

Mark complete when:

- [ ] Unit tests cover valid cases, malformed IDs, and missing accounts.
- [ ] Adapter tests verify `onNext`/`onCompleted` on success and `onError` on failure.
- [ ] Integration tests invoke generated stubs against an in-process server and verify responses/statuses.
- [ ] Spring context tests instantiate required beans and gRPC server auto-configuration.
- [ ] Contract tests verify service names, method names, input/output types, and critical field numbers.
- [ ] CI validates updated schemas against the published baseline.
- [ ] Channels and servers are closed in cleanup to prevent thread and resource leaks.
- [ ] `clean test` and contract checks pass.

## 12. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Unit tests pass, but client RPC calls fail | Never tested through generated stubs and server | Add integration tests using in-process or TCP transport. |
| In-process tests pass, but Spring app fails to expose service | Test instantiates endpoint manually, bypassing Spring bean registration | Add a Spring context test and verify `@GrpcService`/auto-configuration. |
| Flaky tests | Using `sleep` or sharing mutable state between callbacks and test threads | Synchronize on callbacks, queues/futures/latches with timeouts, and isolate test state. |
| Test hangs on RPC error | Not asserting terminal error or missing deadline | Assert status and set finite deadlines on calls. |
| Contract tests miss breaking changes | Only testing Java code without inspecting descriptors or baselines | Assert service/method/field numbers and run schema compatibility checks. |
| Port already in use | Multiple tests booting servers on the same hardcoded port | Use in-process servers or random ports for Spring integration tests. |
| Thread leaks after tests | Channels/servers not closed | Use `@AfterEach`, `shutdown`, and `awaitTermination`. |

A strong gRPC test suite proves more than that a method returns the right data. It proves client and server speak the exact same contract, Spring wires the service properly, errors translate into meaningful statuses, and proto changes do not break released clients.
