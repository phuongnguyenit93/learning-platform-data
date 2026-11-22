# Viết unit, integration và contract test

Một gRPC service có thể trả kết quả đúng khi gọi trực tiếp trong một unit test nhưng vẫn lỗi khi chạy qua channel thật: service chưa được Spring đăng ký, tên method trên wire không khớp, serialization thay đổi hoặc server trả status khác với điều client mong đợi. Vì vậy, kiểm thử gRPC cần nhiều lớp, mỗi lớp xác minh một ranh giới cụ thể.

Trong dự án thực hành này, bạn sẽ kiểm thử `AccountService.GetAccount` theo ba hướng:

- **Unit test** kiểm tra quy tắc nghiệp vụ và cách adapter chuyển kết quả/lỗi thành response hoặc gRPC status.
- **Integration test** gọi service qua gRPC channel để xác minh generated stub, serialization, dispatch và status end-to-end.
- **Contract test** kiểm tra service, method, message và field trong Protocol Buffers; đồng thời kiểm tra schema mới có tương thích với baseline đã phát hành hay không.

Các ví dụ dùng JUnit 5, Mockito, Spring Boot Test và gRPC in-process transport. Chúng tiếp tục bài toán tra cứu tài khoản với ID dạng `ACC-` theo sau bởi sáu chữ số.

## Mục tiêu và phạm vi

Khi hoàn thành, test suite cần chứng minh được các hành vi sau:

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| ID hợp lệ và tồn tại | Trả đúng account ID, owner, currency, balance và active. |
| ID rỗng hoặc sai định dạng | Client nhận `INVALID_ARGUMENT`. |
| ID đúng định dạng nhưng không tồn tại | Client nhận `NOT_FOUND`. |
| Lỗi ngoài dự kiến trong ứng dụng | Client nhận `INTERNAL` với mô tả an toàn. |
| Proto thay đổi tên service, method hoặc field number ngoài dự kiến | Contract test thất bại. |
| Proto mới không tương thích với schema đã phát hành | Schema compatibility check trong CI thất bại. |

## 1. Phân chia các lớp kiểm thử

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

| Loại test | Phạm vi | Phụ thuộc bên ngoài | Khi nào chạy |
| --- | --- | --- | --- |
| Unit | Một class hoặc một ranh giới nhỏ | Mock/fake dependency | Mỗi lần build và khi phát triển. |
| Integration | Nhiều thành phần hoạt động cùng nhau qua transport | gRPC server/channel; có thể dùng Spring context | Mỗi pull request. |
| Contract | Cấu trúc và tính tương thích của API | Generated descriptor và schema baseline | Mỗi thay đổi proto, trước khi phát hành. |

Unit test nên chiếm số lượng lớn nhất vì chạy nhanh và khoanh vùng lỗi rõ. Integration test ít hơn nhưng phải đi qua gRPC stub để phát hiện lỗi mà unit test không thấy. Contract test nhỏ và tập trung vào những chi tiết của wire contract cần giữ ổn định.

## 2. Chuẩn bị project và test dependencies

Giả sử ứng dụng đã có các thành phần từ bài `AccountService`:

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

Trong Gradle, các dependency test thường gồm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation "io.grpc:grpc-inprocess:${grpcVersion}"
}
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và Spring Test. `grpc-inprocess` phải dùng cùng phiên bản gRPC Java với các module runtime khác. Nếu dự án quản lý phiên bản bằng BOM, hãy bỏ version riêng và để dependency management quyết định.

Với Maven, dùng `spring-boot-starter-test` và `io.grpc:grpc-inprocess` ở scope `test`. Không thêm một bộ phiên bản gRPC độc lập chỉ để chạy test.

Đảm bảo proto đã được sinh mã trước khi compile test. Contract test sẽ truy cập descriptor được tạo từ cùng file `.proto` mà ứng dụng dùng.

## 3. Unit test cho application service

Application service kiểm tra định dạng ID rồi truy vấn repository. Đây là nơi phù hợp để kiểm tra quy tắc nghiệp vụ mà không cần khởi động Spring hoặc gRPC server.

Ví dụ `AccountApplicationServiceTest.java`:

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

Các test này xác minh ba nhánh: tìm thấy, ID sai và ID hợp lệ nhưng không có dữ liệu. `verifyNoInteractions(repository)` chứng minh validation chạy trước khi truy cập dữ liệu. Nếu đổi quy tắc ID, chỉ cần cập nhật unit test ở tầng này cùng với contract nghiệp vụ liên quan.

## 4. Unit test cho gRPC adapter

Adapter chuyển exception của application service thành status của gRPC. Ta có thể kiểm tra nó bằng một `StreamObserver` ghi lại callback mà không cần mở server.

Đảm bảo implementation có nguyên tắc terminal rõ ràng:

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

Trong ứng dụng thực tế, nhánh `INTERNAL` cần ghi exception vào logger phía server với correlation ID; không gửi stack trace hoặc thông tin kết nối database về client. Đoạn rút gọn trên tập trung vào hành vi được test.

Tạo `AccountGrpcEndpointTest.java`:

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

Ở unit test này, `StreamObserver` chạy đồng bộ ngay trong lời gọi method vì endpoint thực hiện logic trực tiếp. Khi test qua gRPC channel, callback sẽ đi qua transport và cần xử lý như một lời gọi RPC thực tế.

## 5. Integration test qua gRPC in-process transport

Unit test không kiểm tra generated stub có gọi đúng method hay protobuf có serialize/deserialize đúng hay không. Integration test sau dùng `InProcessServerBuilder` và `InProcessChannelBuilder`: request đi qua gRPC client/server pipeline nhưng không mở TCP port.

Ví dụ `AccountGrpcTransportIntegrationTest.java`:

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

Test này chạy qua generated blocking stub, gRPC method dispatch, protobuf serialization/deserialization và status propagation. `directExecutor()` giúp test nhỏ chạy đơn giản, nhưng không kiểm tra hành vi scheduler hoặc race condition của môi trường đa thread. Test cũng không mở socket và không xác minh TLS.

Nếu cần kiểm thử TLS, HTTP/2, port binding, load balancer hoặc network timeout, hãy bổ sung một integration test với server TCP thật trong môi trường test. Không xem in-process test là bằng chứng cho TLS hoặc cấu hình mạng đã đúng.

## 6. Kiểm tra Spring context và component discovery

In-process test ở trên tạo endpoint bằng constructor để cô lập transport. Nó chưa chứng minh Spring đã tạo các bean và nhận diện annotation `@GrpcService`. Thêm một context test để xác minh wiring:

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

Port `0` yêu cầu hệ điều hành cấp một cổng khả dụng cho server trong test, tránh xung đột khi chạy song song. Tên property và cách starter quản lý server test phụ thuộc phiên bản Spring gRPC; đối chiếu cấu hình của đúng phiên bản trong dự án. Nếu phiên bản đang dùng không hỗ trợ giá trị này, dùng cơ chế random port/test server được tài liệu của phiên bản đó cung cấp.

Test context xác nhận Spring discover các bean, bao gồm implementation có `@GrpcService`, và server auto-configuration có thể khởi động trong test. Kết hợp nó với in-process transport test để kiểm tra hai phần riêng biệt: Spring wiring và gRPC request/response pipeline. Nếu cần xác minh chính xác cổng TCP và service được expose trên mạng, bổ sung một test gọi client qua port của server test.

## 7. Contract test cho Protocol Buffers

Contract test bảo vệ các chi tiết mà client và server cùng dựa vào: tên service, tên method, input/output type và field number. Field number là một phần của binary wire format; không được đổi số của field đã phát hành chỉ vì tên field thay đổi.

Ví dụ `AccountProtoContractTest.java`:

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

Các test này thất bại khi ai đó vô tình đổi service/method identity, input/output type hoặc field number trong proto. Nếu dự án đổi tên field nhưng giữ field number để giữ wire compatibility, hãy cập nhật assertion về tên có chủ đích và ghi nhận tác động đối với code sinh; không thay field number.

Contract test ở trên kiểm tra schema hiện tại so với kỳ vọng được viết trong test. Nó không tự so sánh với phiên bản proto đã phát hành. Để kiểm tra breaking change giữa hai phiên bản schema, cần thêm công cụ kiểm tra tương thích trong CI.

## 8. Kiểm tra schema compatibility trong CI

Quy tắc khi thay đổi proto:

- Không đổi field number của field đã phát hành.
- Không tái sử dụng số của field đã xóa.
- Dùng `reserved` cho số và tên field đã ngừng sử dụng.
- Không đổi protobuf package, service name hoặc RPC method nếu chưa có kế hoạch migration cho client/server.
- Khi thêm field, chọn số mới và đánh giá default value mà client cũ sẽ quan sát.
- Khi thêm enum value, kiểm tra cách các client cũ xử lý giá trị chưa biết.

Ví dụ khi xóa field cũ khỏi message:

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

Không đưa field mới vào số 6 hoặc dùng lại tên `legacy_label` sau khi đã reserve. Việc reserve giúp compiler ngăn tái sử dụng vô tình trong các lần chỉnh schema sau.

Có thể dùng Buf để lint và so sánh schema hiện tại với baseline đã phát hành. Ví dụ lệnh trong CI, với baseline được lưu ở Git branch chính:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

Đảm bảo repository có `buf.yaml` hợp lệ và baseline branch chứa phiên bản proto gần nhất đã phát hành hoặc được chấp nhận. Cấu hình Buf và cú pháp nguồn baseline cần khớp phiên bản CLI của dự án. `buf lint` kiểm tra quy ước schema; `buf breaking` kiểm tra các thay đổi không tương thích theo rule set đang cấu hình. Giữ cả descriptor contract test lẫn schema compatibility check vì chúng bắt các lớp lỗi khác nhau.

## 9. Kiểm thử status và deadline ở phía client

Client gRPC nhận lỗi dưới dạng `StatusRuntimeException` khi dùng blocking stub. Test client cần kiểm tra status code, và chỉ kiểm tra description nếu nội dung đó là một phần API mà nhóm cam kết ổn định.

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.withDeadlineAfter(1, TimeUnit.MILLISECONDS)
                .getAccount(validRequest));

assertEquals(Status.Code.DEADLINE_EXCEEDED, error.getStatus().getCode());
```

Ví dụ trên chỉ nên dùng khi test kiểm soát được một service chậm có chủ đích. Không đặt deadline quá nhỏ lên service bình thường rồi mong test luôn timeout; tải máy và lịch chạy thread có thể làm kết quả dao động. Một cách tốt hơn là tạo test service giữ lời gọi đến khi deadline hết, hoặc dùng latch để điều khiển lúc server hoàn tất.

Với retry, cancellation và deadline, tách test thành từng hành vi:

- Deadline hết trước khi server trả lời: client quan sát `DEADLINE_EXCEEDED`.
- Client chủ động hủy: server nhận tín hiệu cancellation và dừng công việc có thể dừng.
- Retry được kích hoạt: chỉ retry các status và thao tác được chính sách cho phép; không retry mù quáng `INVALID_ARGUMENT`.

Các test này bổ sung cho bài thực hành unary cơ bản; chúng không thay thế test success, validation và contract.

## 10. Chạy test và tổ chức CI

Chạy toàn bộ test bằng wrapper:

```bash
# Gradle
./gradlew clean test

# Maven
mvn clean test
```

Một pipeline CI có thể thực hiện theo thứ tự:

1. Lint và kiểm tra breaking change của proto.
2. Sinh Java code từ proto và compile source.
3. Chạy unit test cho application service và gRPC adapter.
4. Chạy integration test qua in-process gRPC transport.
5. Khởi động Spring context để kiểm tra bean wiring và service registration.
6. Lưu test report và dừng pipeline nếu bất kỳ lớp kiểm thử nào thất bại.

Nếu repository có nhiều module, chạy test ở module chứa proto/service và các module client phụ thuộc. Đảm bảo CI dùng đúng JDK và wrapper đã commit; không dựa vào generated source cũ trên máy developer.

## 11. Ma trận kiểm thử và tiêu chí nghiệm thu

| Kiểm tra | Unit | Integration | Contract |
| --- | :---: | :---: | :---: |
| Validation ID | Có | Có | Không |
| Repository lookup | Có | Có, bằng fake hoặc test database | Không |
| Status mapping | Có | Có, qua client stub | Không |
| Protobuf serialization | Không | Có | Descriptor/schema |
| Spring bean wiring | Không | Spring context test | Không |
| Service/method name | Không | Có thể phát hiện khi gọi | Có |
| Field number/type | Không | Có thể ảnh hưởng serialization | Có |
| Tương thích với schema đã phát hành | Không | Không đủ để xác minh | Buf breaking/baseline |

Đánh dấu hoàn thành khi:

- [ ] Unit test bao phủ trường hợp hợp lệ, ID sai và không tìm thấy account.
- [ ] Adapter test xác minh `onNext`/`onCompleted` khi thành công và `onError` khi thất bại.
- [ ] Integration test gọi generated stub qua in-process server và xác minh response/status.
- [ ] Spring context test khởi tạo được các bean cần thiết và gRPC server auto-configuration.
- [ ] Contract test xác minh service name, method name, input/output type và field number quan trọng.
- [ ] CI kiểm tra schema mới so với baseline đã phát hành.
- [ ] Channel/server được đóng trong cleanup để tránh rò rỉ thread và tài nguyên.
- [ ] `clean test` và các bước contract check chạy thành công.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Unit test pass nhưng client gọi RPC thất bại | Chưa kiểm thử qua generated stub và server | Thêm integration test dùng in-process hoặc TCP transport. |
| Test in-process pass nhưng Spring app không expose service | Test tự tạo endpoint nên không đi qua Spring bean registration | Thêm Spring context test và kiểm tra `@GrpcService`/auto-configuration. |
| Test lúc pass lúc fail | Dùng sleep hoặc chia sẻ mutable state giữa callback và test thread | Đồng bộ theo callback, queue/future/latch có timeout và trạng thái riêng từng test. |
| Test treo khi RPC lỗi | Không kiểm tra terminal error hoặc không đặt deadline | Assert status và đặt deadline hữu hạn cho lời gọi. |
| Contract test không phát hiện breaking change | Chỉ kiểm tra code Java, không kiểm tra descriptor hoặc baseline | Assert service/method/field number và chạy schema compatibility check. |
| Port đã được sử dụng | Nhiều test khởi động server trên cùng cổng cố định | Dùng in-process server hoặc port ngẫu nhiên cho Spring integration test. |
| Rò rỉ thread sau test | Không đóng channel/server | Dùng `@AfterEach`, shutdown và await termination. |

Một test suite gRPC tốt không chỉ chứng minh method trả về đúng dữ liệu. Nó còn chứng minh client và server đang nói cùng một hợp đồng, Spring khởi tạo đúng service, lỗi được truyền thành status có ý nghĩa và thay đổi proto không phá vỡ các client đã phát hành.
