# Building a Unary RPC with Validation and Status Mapping

In this hands-on lesson, you will build a unary gRPC API for account lookup. The client sends an `account_id`; the server validates the format, finds the account, and returns its details. If the input is invalid or the account does not exist, the server returns the appropriate gRPC status so the client can handle each case properly.

The project focuses on three critical boundaries: the Protocol Buffers contract, application-layer validation, and mapping business domain errors to gRPC statuses. You will use Spring to manage the service implementation, write tests for both success responses and error branches, and invoke the API with a real client.

## Expected Outcomes

After completing this lesson, you will be able to:

- Define a unary RPC and request/response messages using `.proto`.
- Generate Java message classes and gRPC service base classes from the contract.
- Register the service implementation as a Spring bean.
- Validate request data before accessing the repository.
- Map validation errors to `INVALID_ARGUMENT`, missing data to `NOT_FOUND`, and unexpected errors to `INTERNAL`.
- Test both successful responses and the error statuses observed by the client.

## Problem Statement

Build `AccountService` with a single RPC:

```text
GetAccount(GetAccountRequest) returns (GetAccountResponse)
```

Business rules:

| Case | Expected Result |
| --- | --- |
| `account_id` has format `ACC-` followed by exactly 6 digits and the account exists | Return the account details. |
| `account_id` is empty or malformed | `INVALID_ARGUMENT`. |
| Valid ID format, but not present in the repository | `NOT_FOUND`. |
| Unexpected error during processing | `INTERNAL` with a generic description, without leaking internal details. |

Sample seed data:

| Account ID | Owner Name | Currency | Balance (minor unit) | Active |
| --- | --- | --- | ---: | --- |
| `ACC-000001` | Nguyen An | VND | 12500000 | true |
| `ACC-000002` | Tran Binh | VND | 8300000 | true |

Balances are stored as integers in the currency's minor unit to avoid floating-point rounding errors. For VND, this example uses dong as the minor unit.

## Project Setup

Create a Spring Boot application with Java 17 or higher and a Spring gRPC server starter compatible with your project's Spring Boot version. Configure protobuf code generation so the build generates both Java messages and gRPC stubs/service base classes. Keep `protoc`, `protoc-gen-grpc-java`, the protobuf runtime, and the gRPC runtime on compatible versions, and prefer the dependency management/BOM used by your project.

If you are continuing from a Spring gRPC module that already has code generation configured, reuse that configuration. If creating a new project, add the protobuf plugin and attach the `grpc` plugin to the generation task as covered in the module's code generation lesson. Do not add an independent runtime version if the Spring Boot BOM already manages the corresponding dependency.

Target source structure:

```text
src/main/proto/
  account.proto

src/main/java/com/example/accounts/
  AccountsApplication.java
  application/
    AccountApplicationService.java
  domain/
    Account.java
    AccountNotFoundException.java
    InvalidAccountIdException.java
  infrastructure/
    AccountRepository.java
    InMemoryAccountRepository.java
  grpc/
    AccountGrpcEndpoint.java

src/test/java/com/example/accounts/grpc/
  AccountGrpcEndpointTest.java
```

Package names and paths can be adjusted to match your project conventions. The examples below use `com.example.accounts`.

## Step 1: Define the Protocol Buffers Contract

Create `src/main/proto/account.proto`:

```proto
syntax = "proto3";

package accounts.v1;

option java_package = "com.example.accounts.v1";
option java_multiple_files = true;
option java_outer_classname = "AccountApiProto";

service AccountService {
  rpc GetAccount(GetAccountRequest) returns (GetAccountResponse);
}

message GetAccountRequest {
  string account_id = 1;
}

message GetAccountResponse {
  string account_id = 1;
  string owner_name = 2;
  string currency = 3;
  int64 balance_minor = 4;
  bool active = 5;
}
```

This contract defines a unary RPC: one request produces one response or one RPC error. `java_package` determines the generated Java package; `java_multiple_files = true` makes each message its own top-level Java class. The service name generates `AccountServiceGrpc`, and the `GetAccount` method is mapped to the Java method `getAccount` on stubs and the service base class.

Proto3 defaults unassigned string fields to an empty string. Therefore, a request can be valid at the protobuf level while still missing `account_id` at the business level. Validation must be performed on the server.

## Step 2: Generate Java Code

Run your build tool's code generation and compile tasks. For example, with the Gradle protobuf plugin:

```bash
./gradlew clean generateProto compileJava
```

Or on Windows:

```powershell
gradlew.bat clean generateProto compileJava
```

With Maven, if the protobuf plugin binds `compile` and `compile-custom` to the lifecycle:

```bash
mvn clean compile
```

Verify the generated classes, especially:

- `GetAccountRequest` and `GetAccountResponse`.
- `AccountServiceGrpc`.
- `AccountServiceGrpc.AccountServiceImplBase`.
- Stub types such as `AccountServiceBlockingStub` and `AccountServiceStub`.

If messages exist without `AccountServiceGrpc`, check your gRPC plugin configuration. Never edit generated files directly; update the contract in `.proto` and regenerate.

## Step 3: Create the Model and Repository

Create the domain model `Account.java`:

```java
package com.example.accounts.domain;

public record Account(
        String accountId,
        String ownerName,
        String currency,
        long balanceMinor,
        boolean active
) {}
```

Create two exceptions representing business errors. These are gRPC-independent exceptions so the application layer does not depend on the transport:

```java
package com.example.accounts.domain;

public class InvalidAccountIdException extends RuntimeException {
    public InvalidAccountIdException() {
        super("account_id must use the format ACC- followed by 6 digits");
    }
}
```

```java
package com.example.accounts.domain;

public class AccountNotFoundException extends RuntimeException {
    public AccountNotFoundException() {
        super("Account was not found");
    }
}
```

Declare the repository:

```java
package com.example.accounts.infrastructure;

import com.example.accounts.domain.Account;
import java.util.Optional;

public interface AccountRepository {
    Optional<Account> findById(String accountId);
}
```

Create an in-memory implementation so the project can run without a database yet:

```java
package com.example.accounts.infrastructure;

import com.example.accounts.domain.Account;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryAccountRepository implements AccountRepository {

    private final Map<String, Account> accounts = Map.of(
            "ACC-000001", new Account(
                    "ACC-000001", "Nguyen An", "VND", 12_500_000L, true),
            "ACC-000002", new Account(
                    "ACC-000002", "Tran Binh", "VND", 8_300_000L, true)
    );

    @Override
    public Optional<Account> findById(String accountId) {
        return Optional.ofNullable(accounts.get(accountId));
    }
}
```

The repository returns `Optional` to represent missing data. It does not decide gRPC statuses; that belongs to the gRPC adapter in the next step.

## Step 4: Application-Layer Validation

Create `AccountApplicationService.java`:

```java
package com.example.accounts.application;

import com.example.accounts.domain.Account;
import com.example.accounts.domain.AccountNotFoundException;
import com.example.accounts.domain.InvalidAccountIdException;
import com.example.accounts.infrastructure.AccountRepository;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class AccountApplicationService {

    private static final Pattern ACCOUNT_ID_PATTERN =
            Pattern.compile("ACC-[0-9]{6}");

    private final AccountRepository repository;

    public AccountApplicationService(AccountRepository repository) {
        this.repository = repository;
    }

    public Account findById(String accountId) {
        if (accountId == null || !ACCOUNT_ID_PATTERN.matcher(accountId).matches()) {
            throw new InvalidAccountIdException();
        }

        return repository.findById(accountId)
                .orElseThrow(AccountNotFoundException::new);
    }
}
```

Validation runs before calling the repository. That way, malformed IDs are always classified as input errors, while well-formed IDs that do not exist become not-found errors.

In this lesson, validation is written explicitly to make the business rules clear. Java messages generated from proto do not automatically carry Jakarta Bean Validation annotations like `@NotBlank` or `@Pattern`. If your project uses Protovalidate or a constraint-generating plugin, integrate it according to its configuration while preserving a consistent error classification policy.

## Step 5: Map Exceptions to gRPC Statuses

Create `AccountGrpcEndpoint.java`:

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
                    .withDescription("account_id must use the format ACC- followed by 6 digits")
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

`@GrpcService` marks the implementation so Spring gRPC registers the service with the server. The import in this example is from Spring gRPC; if your starter version uses a different package or registration mechanism, use the annotation/API matching your declared version.

A unary response follows one of two branches:

- Success: call `onNext` exactly once, then call `onCompleted`.
- Failure: call `onError` exactly once and return; never call `onNext` or `onCompleted` afterward.

The code builds the response inside the `try` block before sending it to the observer. That ensures if validation or repository access fails, the client receives only a single terminal error and never a partial response.

Status codes are chosen based on the meaning of the error:

| Exception / Scenario | gRPC Status | Meaning to Client |
| --- | --- | --- |
| `InvalidAccountIdException` | `INVALID_ARGUMENT` | Client must fix the request. |
| `AccountNotFoundException` | `NOT_FOUND` | Requested resource does not exist. |
| Unexpected runtime exception | `INTERNAL` | Server encountered an error; client should not rely on internal details. |

Never return `ex.getMessage()` from an unexpected error to the client. Log the exception on the server for investigation, while keeping the status description safe and stable. In production systems, include a request/correlation ID in logs or traces so client-visible errors can be linked to server-side logs.

## Step 6: Configure and Run the Spring Application

Ensure the main class resides in the parent package of all components:

```java
package com.example.accounts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountsApplication.class, args);
    }
}
```

Configure the server port in `src/main/resources/application.properties` according to your Spring gRPC version. For a Spring gRPC server setup using `spring.grpc.server.port`:

```properties
spring.grpc.server.port=9090
```

Run the application using the project wrapper:

```bash
# Gradle
./gradlew bootRun

# Maven
mvn spring-boot:run
```

If the application fails to start, inspect the logs to verify that `AccountService` is registered and port `9090` is not already in use by another process. If the port property is ignored, verify the property name against the Spring gRPC starter version used in your project.

## Step 7: Test Status Mapping

Testing the endpoint directly verifies both the response and the status delivered to the observer. The example below uses JUnit 5 and Mockito; `AccountApplicationService` is mocked to isolate the gRPC adapter.

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
import io.grpc.StatusRuntimeException;
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
    void returnsAccountWhenRequestIsValid() {
        when(accounts.findById("ACC-000001"))
                .thenReturn(new Account(
                        "ACC-000001", "Nguyen An", "VND", 12_500_000L, true));

        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();
        endpoint.getAccount(request("ACC-000001"), observer);

        assertNull(observer.error);
        assertTrue(observer.completed);
        assertNotNull(observer.value);
        assertEquals("ACC-000001", observer.value.getAccountId());
        assertEquals("Nguyen An", observer.value.getOwnerName());
        assertEquals(12_500_000L, observer.value.getBalanceMinor());
    }

    @Test
    void mapsInvalidIdToInvalidArgument() {
        when(accounts.findById("bad-id"))
                .thenThrow(new InvalidAccountIdException());

        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();
        endpoint.getAccount(request("bad-id"), observer);

        assertStatus(Status.Code.INVALID_ARGUMENT, observer);
        assertNull(observer.value);
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
    void hidesUnexpectedExceptionDetails() {
        when(accounts.findById("ACC-000001"))
                .thenThrow(new IllegalStateException("database password leaked"));

        RecordingObserver<GetAccountResponse> observer = new RecordingObserver<>();
        endpoint.getAccount(request("ACC-000001"), observer);

        assertStatus(Status.Code.INTERNAL, observer);
        StatusRuntimeException error = (StatusRuntimeException) observer.error;
        assertEquals("Unable to retrieve account", error.getStatus().getDescription());
    }

    private static GetAccountRequest request(String accountId) {
        return GetAccountRequest.newBuilder().setAccountId(accountId).build();
    }

    private static void assertStatus(
            Status.Code expected,
            RecordingObserver<?> observer) {
        assertNotNull(observer.error);
        assertEquals(expected, Status.fromThrowable(observer.error).getCode());
    }

    private static final class RecordingObserver<T> implements StreamObserver<T> {
        private T value;
        private Throwable error;
        private boolean completed;

        @Override
        public void onNext(T value) {
            this.value = value;
        }

        @Override
        public void onError(Throwable error) {
            this.error = error;
        }

        @Override
        public void onCompleted() {
            this.completed = true;
        }
    }
}
```

These tests verify four key contracts: the right response on success, `INVALID_ARGUMENT` on malformed IDs, `NOT_FOUND` on missing IDs, and `INTERNAL` on unexpected errors without leaking sensitive details. Add the Mockito JUnit Jupiter dependency to test scope if your project does not already include it.

You should also unit test `AccountApplicationService` separately to ensure malformed IDs never hit the repository:

```java
@Test
void rejectsMalformedIdBeforeRepositoryLookup() {
    assertThrows(InvalidAccountIdException.class,
            () -> applicationService.findById("ACC-12"));
    verifyNoInteractions(repository);
}
```

This test uses a mock repository and confirms that validation occurs before data access.

Run the tests:

```bash
# Gradle
./gradlew clean test

# Maven
mvn clean test
```

## Step 8: Call the RPC from a Client

Once the server is running on `localhost:9090`, you can use `grpcurl` in a local development environment. The command below assumes the server uses plaintext and the proto file is in the current directory:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto account.proto \
  -d '{"accountId":"ACC-000001"}' \
  localhost:9090 accounts.v1.AccountService/GetAccount
```

Expected response:

```json
{
  "accountId": "ACC-000001",
  "ownerName": "Nguyen An",
  "currency": "VND",
  "balanceMinor": "12500000",
  "active": true
}
```

Try a malformed ID:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto account.proto \
  -d '{"accountId":"bad-id"}' \
  localhost:9090 accounts.v1.AccountService/GetAccount
```

The client should receive `Code: InvalidArgument`. For `ACC-999999`, the client should receive `Code: NotFound`. For unexpected server errors, the client receives only `Code: Internal` and a generic description.

If you want to test with a Java client, create a blocking stub via `AccountServiceGrpc.newBlockingStub(channel)` and call `getAccount(request)`. On errors, catch `StatusRuntimeException` and inspect `ex.getStatus().getCode()` to decide how to handle it. Always close the channel when finished with the test or client operation.

## Acceptance Criteria

Mark the project complete when all of the following conditions are met:

- [ ] `account.proto` properly defines `AccountService.GetAccount` and both messages.
- [ ] The build generates Java messages and `AccountServiceGrpc` from the proto.
- [ ] Spring boots and registers `AccountGrpcEndpoint` with the gRPC server.
- [ ] `ACC-000001` returns the expected account data.
- [ ] Empty or malformed IDs return `INVALID_ARGUMENT`.
- [ ] Well-formed but non-existent IDs return `NOT_FOUND`.
- [ ] Unexpected errors return `INTERNAL` without exposing internal details.
- [ ] Tests verify responses, status codes, and unary observer terminal rules.
- [ ] `clean test` passes.

## Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `AccountServiceGrpc` not found | `protoc-gen-grpc-java` plugin not run or not wired to the task | Inspect protobuf configuration and re-run code generation. |
| Cannot import Java messages | `java_package` differs from import package or generated sources not recognized by build | Check package in generated files and build source sets. |
| `@GrpcService` not recognized | Missing Spring gRPC server starter or version-mismatched import | Verify dependencies and annotation API for your exact Spring gRPC version. |
| Client receives `UNIMPLEMENTED` | Service not registered or client calling wrong package/service/method | Verify `@GrpcService`, service name in proto, and client target endpoint. |
| Empty IDs are not rejected | Relying solely on proto3 without application-layer validation | Check for blank strings before calling the repository. |
| Database errors return `UNKNOWN` or inconsistent `INTERNAL` | Exceptions not explicitly classified at the gRPC boundary | Add intentional mappings for business/infrastructure errors; reserve `INTERNAL` for unexpected failures. |
| Client sees internal exception details | Server passed `ex.getMessage()` directly into status description | Return a safe description; log stack traces on the server. |

## Extensions After Completion

1. Replace `InMemoryAccountRepository` with a database-backed repository; map transient connection errors to `UNAVAILABLE` if appropriate for your client's retry policy.
2. Add a `CreateAccount` RPC and return `ALREADY_EXISTS` when the ID already exists.
3. Add authentication/authorization and distinguish `UNAUTHENTICATED` from `PERMISSION_DENIED`.
4. Propagate a correlation ID via metadata and include it in per-request logs for tracing.
5. Add an integration test that starts the Spring context and invokes the RPC over a real channel to verify service registration, serialization, and statuses end-to-end.

The result of this hands-on lesson is a unary RPC with a clear contract, deterministic validation, and consistent status mapping. When clients receive meaningful statuses, they can distinguish invalid requests, missing resources, and server failures and respond appropriately.
