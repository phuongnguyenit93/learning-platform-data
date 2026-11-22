# Tạo unary RPC với validation và status mapping

Trong bài thực hành này, bạn sẽ xây dựng một API gRPC unary để tra cứu tài khoản. Client gửi một `account_id`; server kiểm tra định dạng, tìm tài khoản và trả về thông tin. Nếu dữ liệu đầu vào sai hoặc tài khoản không tồn tại, server trả về gRPC status phù hợp để client có thể xử lý theo từng trường hợp.

Dự án tập trung vào ba ranh giới quan trọng: hợp đồng Protocol Buffers, validation ở tầng ứng dụng và ánh xạ lỗi miền nghiệp vụ sang status của gRPC. Bạn sẽ dùng Spring để quản lý service implementation, kiểm thử kết quả thành công và các nhánh lỗi, sau đó gọi API bằng một client thực tế.

## Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Định nghĩa unary RPC và message request/response bằng `.proto`.
- Sinh Java message và gRPC service base class từ hợp đồng.
- Đăng ký service implementation như một Spring bean.
- Kiểm tra dữ liệu request trước khi truy cập repository.
- Ánh xạ lỗi validation thành `INVALID_ARGUMENT`, dữ liệu không tồn tại thành `NOT_FOUND` và lỗi ngoài dự kiến thành `INTERNAL`.
- Kiểm thử cả response thành công lẫn status lỗi mà client quan sát được.

## Bài toán

Xây dựng `AccountService` với một RPC:

```text
GetAccount(GetAccountRequest) returns (GetAccountResponse)
```

Quy tắc nghiệp vụ:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `account_id` có dạng `ACC-` theo sau bởi đúng 6 chữ số và tài khoản tồn tại | Trả về thông tin tài khoản. |
| `account_id` rỗng hoặc sai định dạng | `INVALID_ARGUMENT`. |
| ID hợp lệ nhưng không có trong repository | `NOT_FOUND`. |
| Có lỗi ngoài dự kiến khi xử lý | `INTERNAL` với mô tả chung, không tiết lộ chi tiết nội bộ. |

Ví dụ dữ liệu có sẵn:

| Account ID | Chủ tài khoản | Currency | Balance (minor unit) | Active |
| --- | --- | --- | ---: | --- |
| `ACC-000001` | Nguyen An | VND | 12500000 | true |
| `ACC-000002` | Tran Binh | VND | 8300000 | true |

Số dư được lưu dưới dạng số nguyên ở đơn vị nhỏ nhất của tiền tệ để tránh sai số dấu phẩy động. Với VND, ví dụ này dùng đồng làm đơn vị nhỏ nhất.

## Chuẩn bị dự án

Tạo một ứng dụng Spring Boot có Java 17 trở lên và Spring gRPC server starter tương thích với phiên bản Spring Boot của dự án. Cấu hình protobuf code generation để build sinh cả Java message và gRPC stub/service base class. Giữ phiên bản `protoc`, `protoc-gen-grpc-java`, protobuf runtime và gRPC runtime tương thích, đồng thời ưu tiên dependency management/BOM mà dự án đang dùng.

Nếu bạn đang tiếp tục module Spring gRPC đã có cấu hình sinh mã, hãy dùng lại cấu hình đó. Nếu tạo project mới, thêm plugin protobuf và gắn plugin `grpc` vào task sinh mã như phần thực hành sinh code của module đã hướng dẫn. Đừng thêm một phiên bản runtime riêng nếu Spring Boot BOM đã quản lý dependency tương ứng.

Cấu trúc mã nguồn mục tiêu:

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

Tên package và đường dẫn có thể điều chỉnh theo quy ước dự án. Ví dụ bên dưới dùng `com.example.accounts`.

## Bước 1: Định nghĩa hợp đồng Protocol Buffers

Tạo file `src/main/proto/account.proto`:

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

Hợp đồng này định nghĩa một unary RPC: một request tạo ra một response hoặc một lỗi RPC. `java_package` quyết định package Java được sinh; `java_multiple_files = true` giúp mỗi message trở thành một lớp Java riêng. Tên service tạo ra lớp `AccountServiceGrpc`, còn method `GetAccount` được chuyển thành method Java `getAccount` trên stub và service base class.

Proto3 mặc định giá trị chuỗi chưa được gán là chuỗi rỗng. Vì vậy, request có thể được tạo hợp lệ về mặt protobuf nhưng vẫn thiếu `account_id` về mặt nghiệp vụ. Validation cần được thực hiện ở server.

## Bước 2: Sinh mã Java

Chạy task sinh mã và compile của build tool. Ví dụ với Gradle protobuf plugin:

```bash
./gradlew clean generateProto compileJava
```

Hoặc trên Windows:

```powershell
gradlew.bat clean generateProto compileJava
```

Với Maven, nếu protobuf plugin đã gắn `compile` và `compile-custom` vào lifecycle:

```bash
mvn clean compile
```

Kiểm tra các lớp được sinh, đặc biệt là:

- `GetAccountRequest` và `GetAccountResponse`.
- `AccountServiceGrpc`.
- `AccountServiceGrpc.AccountServiceImplBase`.
- Các kiểu stub, chẳng hạn `AccountServiceBlockingStub` và `AccountServiceStub`.

Nếu chỉ có message mà không có `AccountServiceGrpc`, kiểm tra cấu hình plugin gRPC. Không chỉnh sửa trực tiếp file generated; thay đổi hợp đồng trong `.proto` rồi sinh lại mã.

## Bước 3: Tạo model và repository

Tạo domain model `Account.java`:

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

Tạo hai exception biểu diễn lỗi nghiệp vụ. Đây là các exception độc lập với gRPC để tầng ứng dụng không phụ thuộc vào transport:

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

Khai báo repository:

```java
package com.example.accounts.infrastructure;

import com.example.accounts.domain.Account;
import java.util.Optional;

public interface AccountRepository {
    Optional<Account> findById(String accountId);
}
```

Tạo implementation trong bộ nhớ để dự án có thể chạy mà chưa cần database:

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

Repository trả về `Optional` để biểu diễn trường hợp không tìm thấy dữ liệu. Nó không quyết định gRPC status; việc đó thuộc adapter gRPC ở bước sau.

## Bước 4: Validation ở tầng ứng dụng

Tạo `AccountApplicationService.java`:

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

Validation diễn ra trước khi gọi repository. Nhờ vậy, ID sai định dạng luôn được phân loại là lỗi đầu vào, còn ID đúng định dạng nhưng không tồn tại mới trở thành lỗi không tìm thấy.

Trong bài này, validation được viết tường minh để dễ thấy quy tắc nghiệp vụ. Các message Java sinh từ proto không tự động mang các annotation Jakarta Bean Validation như `@NotBlank` hoặc `@Pattern`. Nếu dự án dùng Protovalidate hoặc plugin sinh constraint, hãy tích hợp theo cấu hình riêng và vẫn giữ quy tắc phân loại lỗi nhất quán.

## Bước 5: Ánh xạ exception sang gRPC status

Tạo `AccountGrpcEndpoint.java`:

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

`@GrpcService` đánh dấu implementation để Spring gRPC đăng ký service với server. Import trong ví dụ là của Spring gRPC; nếu phiên bản starter của dự án dùng package hoặc cơ chế đăng ký khác, hãy dùng annotation/API tương ứng với đúng phiên bản đã khai báo.

Một unary response tuân theo một trong hai nhánh:

- Thành công: gọi `onNext` đúng một lần, sau đó gọi `onCompleted`.
- Thất bại: gọi `onError` đúng một lần rồi kết thúc; không gọi `onNext` hoặc `onCompleted` sau đó.

Đoạn code dựng response trong khối `try`, rồi mới gửi response ra observer. Nhờ vậy, nếu validation hoặc truy cập repository thất bại, client chỉ nhận một terminal error và không nhận response dở dang.

Status được chọn theo ý nghĩa của lỗi:

| Exception / tình huống | gRPC status | Ý nghĩa với client |
| --- | --- | --- |
| `InvalidAccountIdException` | `INVALID_ARGUMENT` | Client cần sửa request. |
| `AccountNotFoundException` | `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại. |
| Runtime exception không dự kiến | `INTERNAL` | Server gặp lỗi; client không nên dựa vào chi tiết nội bộ. |

Không trả `ex.getMessage()` của lỗi ngoài dự kiến về client. Log exception ở server để điều tra, còn status description nên là thông báo an toàn và ổn định. Trong hệ thống thực tế, hãy bổ sung request/correlation ID vào log hoặc tracing để liên kết lỗi client nhìn thấy với log phía server.

## Bước 6: Cấu hình và chạy ứng dụng Spring

Đảm bảo lớp main nằm ở package cha của các component:

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

Cấu hình cổng server trong `src/main/resources/application.properties` theo phiên bản Spring gRPC đang dùng. Với cấu hình Spring gRPC server có property `spring.grpc.server.port`:

```properties
spring.grpc.server.port=9090
```

Chạy ứng dụng bằng wrapper của dự án:

```bash
# Gradle
./gradlew bootRun

# Maven
mvn spring-boot:run
```

Nếu ứng dụng không khởi động, kiểm tra log để xác nhận service `AccountService` được đăng ký và cổng 9090 chưa bị tiến trình khác chiếm. Nếu property cổng không được nhận diện, đối chiếu tên property với phiên bản Spring gRPC starter mà dự án đang dùng.

## Bước 7: Kiểm thử status mapping

Kiểm thử trực tiếp endpoint giúp xác minh cả response và status mà observer nhận. Ví dụ dưới đây dùng JUnit 5 và Mockito; `AccountApplicationService` được mock để cô lập adapter gRPC.

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

Các test trên xác minh bốn hợp đồng quan trọng: response đúng khi thành công, ID sai trả `INVALID_ARGUMENT`, ID không tồn tại trả `NOT_FOUND`, và lỗi bất ngờ trả `INTERNAL` mà không lộ thông tin nhạy cảm. Thêm dependency Mockito JUnit Jupiter vào test scope nếu dự án chưa có.

Bạn cũng nên kiểm thử riêng `AccountApplicationService` để bảo đảm ID sai định dạng không gọi repository:

```java
@Test
void rejectsMalformedIdBeforeRepositoryLookup() {
    assertThrows(InvalidAccountIdException.class,
            () -> applicationService.findById("ACC-12"));
    verifyNoInteractions(repository);
}
```

Test này dùng mock repository và xác nhận validation diễn ra trước thao tác truy cập dữ liệu.

Chạy test:

```bash
# Gradle
./gradlew clean test

# Maven
mvn clean test
```

## Bước 8: Gọi RPC từ client

Khi server chạy ở `localhost:9090`, có thể dùng `grpcurl` trong môi trường phát triển local. Lệnh dưới đây giả định server đang dùng plaintext và file proto nằm trong thư mục hiện tại:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto account.proto \
  -d '{"accountId":"ACC-000001"}' \
  localhost:9090 accounts.v1.AccountService/GetAccount
```

Response dự kiến:

```json
{
  "accountId": "ACC-000001",
  "ownerName": "Nguyen An",
  "currency": "VND",
  "balanceMinor": "12500000",
  "active": true
}
```

Thử ID sai định dạng:

```bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto account.proto \
  -d '{"accountId":"bad-id"}' \
  localhost:9090 accounts.v1.AccountService/GetAccount
```

Client phải nhận `Code: InvalidArgument`. Với `ACC-999999`, client phải nhận `Code: NotFound`. Với lỗi server ngoài dự kiến, client chỉ nhận `Code: Internal` và mô tả chung.

Nếu muốn thử bằng Java client, tạo blocking stub từ `AccountServiceGrpc.newBlockingStub(channel)` rồi gọi `getAccount(request)`. Khi nhận lỗi, bắt `StatusRuntimeException` và đọc `ex.getStatus().getCode()` để quyết định cách xử lý. Luôn đóng channel sau khi hoàn tất test hoặc tác vụ client.

## Tiêu chí nghiệm thu

Đánh dấu dự án hoàn thành khi tất cả điều kiện sau đạt:

- [ ] `account.proto` định nghĩa đúng `AccountService.GetAccount` và hai message.
- [ ] Build sinh được message Java và `AccountServiceGrpc` từ proto.
- [ ] Spring khởi động và đăng ký `AccountGrpcEndpoint` với gRPC server.
- [ ] `ACC-000001` trả về đúng dữ liệu tài khoản.
- [ ] ID rỗng hoặc sai định dạng trả `INVALID_ARGUMENT`.
- [ ] ID đúng định dạng nhưng không tồn tại trả `NOT_FOUND`.
- [ ] Lỗi ngoài dự kiến trả `INTERNAL` và không tiết lộ thông tin nội bộ.
- [ ] Test xác minh response, status code và quy tắc terminal của unary observer.
- [ ] `clean test` chạy thành công.

## Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `AccountServiceGrpc` | Chưa chạy plugin `protoc-gen-grpc-java` hoặc plugin chưa gắn vào task | Kiểm tra cấu hình protobuf và chạy lại task sinh mã. |
| Không import được message Java | `java_package` khác package trong import hoặc source generated chưa được build nhận diện | Kiểm tra package trong file generated và source set của build. |
| `@GrpcService` không được nhận diện | Thiếu Spring gRPC server starter hoặc import không khớp phiên bản | Kiểm tra dependency và API annotation của đúng phiên bản Spring gRPC. |
| Client nhận `UNIMPLEMENTED` | Service chưa được đăng ký hoặc client gọi sai package/service/method | Kiểm tra `@GrpcService`, service name trong proto và endpoint client gọi. |
| ID rỗng không bị chặn | Chỉ dựa vào proto3 mà không validate ở tầng ứng dụng | Kiểm tra chuỗi rỗng trước khi gọi repository. |
| Lỗi database bị trả thành `UNKNOWN` hoặc `INTERNAL` không ổn định | Exception chưa được phân loại rõ tại ranh giới gRPC | Bổ sung mapping có chủ đích cho lỗi nghiệp vụ/hạ tầng; giữ `INTERNAL` cho lỗi không dự kiến. |
| Client thấy thông tin exception nội bộ | Server đưa trực tiếp `ex.getMessage()` vào status description | Trả mô tả an toàn; ghi stack trace ở log server. |

## Mở rộng sau khi hoàn thành

1. Thay `InMemoryAccountRepository` bằng repository truy cập database; ánh xạ lỗi kết nối tạm thời sang `UNAVAILABLE` nếu phù hợp với chính sách retry của client.
2. Thêm RPC `CreateAccount` và dùng `ALREADY_EXISTS` khi ID đã tồn tại.
3. Bổ sung authentication/authorization và phân biệt `UNAUTHENTICATED` với `PERMISSION_DENIED`.
4. Truyền correlation ID qua metadata và ghi log theo request để hỗ trợ truy vết.
5. Thêm integration test khởi động Spring context và gọi RPC qua channel thật để xác nhận service registration, serialization và status end-to-end.

Kết quả của bài thực hành là một unary RPC có hợp đồng rõ ràng, validation xác định và status mapping nhất quán. Khi client nhận được status có ý nghĩa, nó có thể phân biệt request sai, tài nguyên không tồn tại và lỗi server để đưa ra hành động phù hợp.
