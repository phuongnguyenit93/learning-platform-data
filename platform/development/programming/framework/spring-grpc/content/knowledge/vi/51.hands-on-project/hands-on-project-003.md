# Tạo Spring Boot gRPC server

## 1. Mục tiêu dự án

Trong **SPRING_GRPC**, ta xây dựng dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, mã Java được sinh tự động và service implementation do Spring quản lý. Bài thực hành này tạo một server quản lý mặt hàng với một RPC unary để tra cứu mặt hàng theo ID.

Sau khi hoàn thành, dự án có thể:

- Khai báo service và message trong file protobuf.
- Sinh Java message classes, service descriptor và server base class.
- Khởi động gRPC server cùng Spring Boot application context.
- Đăng ký implementation bằng annotation của Spring gRPC.
- Trả protobuf response hoặc gRPC status phù hợp.
- Kiểm tra server bằng grpcurl và một test ở cấp service.

Phạm vi tập trung vào việc tạo server chạy được. Authentication, TLS production, streaming, discovery và observability là các bước mở rộng sau khi đường đi cơ bản hoạt động.

## 2. Kiến trúc và cấu trúc thư mục

Client không gọi trực tiếp Java method của server. Client gửi HTTP/2 gRPC request theo service/method được mô tả trong protobuf contract. Generated stub và descriptor giúp hai phía dùng cùng định nghĩa message và RPC.

~~~mermaid
flowchart LR
    P["inventory.proto"] --> G["protoc + gRPC plugin"]
    G --> M["Generated Java messages"]
    G --> S["Generated service base"]
    M --> I["InventoryGrpcService"]
    S --> I
    I --> U["InventoryUseCase"]
    U --> R["InventoryRepository"]
    C["gRPC client / grpcurl"] -->|HTTP/2 + protobuf| V["Spring gRPC server"]
    V --> I
~~~

Một cấu trúc dự án đơn giản:

~~~text
inventory-grpc/
  build.gradle.kts
  settings.gradle.kts
  src/
    main/
      proto/
        inventory/v1/inventory.proto
      java/
        com/example/inventory/
          InventoryApplication.java
          grpc/
            InventoryGrpcService.java
          application/
            InventoryUseCase.java
          domain/
            InventoryItem.java
    test/
      java/
        com/example/inventory/grpc/
          InventoryGrpcServiceTest.java
~~~

Thư mục generated source thường được plugin protobuf tạo trong build directory. Không chỉnh sửa trực tiếp các file Java được sinh; thay đổi contract trong file .proto rồi chạy lại task generate.

## 3. Tạo Spring Boot project và dependency

Tạo một Spring Boot project có Java toolchain phù hợp với phiên bản Spring Boot đã chọn. Thêm Spring gRPC server starter và protobuf Gradle plugin. Starter cung cấp tích hợp server với Spring; plugin chạy protoc để sinh message classes và gRPC service code.

Ví dụ cấu hình Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    id("com.google.protobuf") version "0.9.5"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.grpc:spring-grpc-spring-boot-starter:<spring-grpc-version>")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.grpc:grpc-inprocess:<grpc-java-version>")
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:<protoc-version>"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:<grpc-java-version>"
        }
    }
    generateProtoTasks {
        all().configureEach {
            plugins {
                grpc {}
            }
        }
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Các placeholder version phải được thay bằng phiên bản tương thích của Spring Boot, Spring gRPC, protobuf compiler và gRPC Java code generator trong dự án. Dùng dependency management/BOM được starter hoặc dự án cung cấp để giữ các thư viện runtime gRPC đồng bộ. Không tự chọn một phiên bản grpc-protobuf hoặc grpc-stub khác với runtime mà starter quản lý.

Nếu starter của phiên bản đang dùng đã quản lý grpc-protobuf và grpc-stub, không cần khai báo lại với version độc lập. Khi generated code báo thiếu class hoặc lỗi method không tương thích, kiểm tra runtime dependency tree và phiên bản protoc plugin trước khi sửa source.

## 4. Khai báo protobuf contract

Tạo file src/main/proto/inventory/v1/inventory.proto:

~~~proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.example.inventory.grpc.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  string name = 2;
  int32 available_quantity = 3;
}
~~~

Contract có một service và một unary method. Request mang ID mặt hàng; response trả ID, tên và số lượng khả dụng.

Một số quy tắc cần giữ:

- package là namespace protobuf trên wire và tham gia vào tên đầy đủ của service.
- java_package quyết định package Java được sinh.
- java_multiple_files = true sinh message classes thành các Java type riêng.
- Field number là định danh trên wire; không đổi hoặc tái sử dụng field number đã phát hành.
- Không dùng required trong proto3; validate dữ liệu ở boundary hoặc domain.
- Khi bỏ field, reserve field number và tên nếu cần tránh tái sử dụng về sau.

Tên đầy đủ của RPC trong ví dụ là inventory.v1.InventoryService/GetItem. Client cần dùng đúng package, service và method này.

## 5. Sinh Java message và gRPC service code

Plugin protobuf tạo Java classes từ .proto. Với Gradle, chạy:

~~~bash
./gradlew clean generateProto
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean generateProto
~~~

Sau khi sinh mã, cần có các thành phần tương đương:

- GetItemRequest và GetItemResponse: protobuf message classes.
- InventoryServiceGrpc: gRPC service descriptor, stub types và server base class.
- InventoryServiceGrpc.InventoryServiceImplBase: base class để server implementation kế thừa.

Tên và vị trí source generated phụ thuộc plugin/version. IDE có thể cần Gradle sync hoặc đánh dấu generated source root để nhận diện class. Không copy generated Java vào src/main/java; để build tái sinh từ contract.

Nếu task không tìm thấy file .proto, kiểm tra file nằm dưới src/main/proto. Nếu message được sinh nhưng service base class không có, kiểm tra cấu hình gRPC plugin trong generateProtoTasks.

## 6. Tạo Spring Boot application

Tạo entry point:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Spring Boot tạo application context và khởi tạo các bean được cấu hình. Spring gRPC starter tích hợp gRPC server với lifecycle của context, vì vậy service implementation có thể được quản lý như một Spring bean.

Không cần tự tạo io.grpc.Server trong main nếu starter đã quản lý server. Tự tạo server song song có thể dẫn đến hai listener, port conflict và lifecycle shutdown không nhất quán.

## 7. Cấu hình port gRPC

Tạo src/main/resources/application.yml:

~~~yaml
spring:
  grpc:
    server:
      port: 9090
~~~

Property namespace phụ thuộc Spring gRPC starter và phiên bản được chọn. Ví dụ trên dùng namespace của Spring gRPC starter; xác minh property reference của đúng version khi dự án dùng starter khác.

Nếu ứng dụng đồng thời có Spring MVC/WebFlux, HTTP server có thể chạy ở port riêng (ví dụ 8080), còn gRPC server chạy ở 9090. Không mặc định server.port của Spring Boot là port gRPC.

Có thể override port theo môi trường qua environment variable hoặc profile. Khi deploy, kiểm tra port mà process thực sự bind và port/targetPort mà container platform công bố.

## 8. Tạo application use case và domain model

Giữ quy tắc nghiệp vụ ngoài lớp gRPC adapter. Ví dụ domain model:

~~~java
package com.example.inventory.domain;

public record InventoryItem(
        String id,
        String name,
        int availableQuantity) {}
~~~

Use case tra cứu item:

~~~java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import java.util.Optional;

public interface InventoryUseCase {
    Optional<InventoryItem> findById(String itemId);
}
~~~

Một implementation đơn giản cho bài thực hành có thể dùng in-memory map:

~~~java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.Optional;

@Service
public class InMemoryInventoryService implements InventoryUseCase {
    private final Map<String, InventoryItem> items = Map.of(
            "item-100", new InventoryItem("item-100", "Keyboard", 12),
            "item-200", new InventoryItem("item-200", "Mouse", 25));

    @Override
    public Optional<InventoryItem> findById(String itemId) {
        return Optional.ofNullable(items.get(itemId));
    }
}
~~~

In-memory data chỉ dùng để chạy thử server. Ứng dụng thực tế nên thay bằng repository phù hợp và xác định rõ transaction/consistency nếu dữ liệu được cập nhật đồng thời.

## 9. Triển khai gRPC service bằng Spring bean

Tạo adapter kế thừa generated server base class:

~~~java
package com.example.inventory.grpc;

import com.example.inventory.application.InventoryUseCase;
import com.example.inventory.application.ItemNotFoundException;
import com.example.inventory.domain.InventoryItem;
import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final InventoryUseCase inventory;

    public InventoryGrpcService(InventoryUseCase inventory) {
        this.inventory = inventory;
    }

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        String itemId = request.getItemId();
        if (itemId == null || itemId.isBlank()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("item_id must not be blank")
                            .asRuntimeException());
            return;
        }

        try {
            InventoryItem item = inventory.findById(itemId)
                    .orElseThrow(() -> new ItemNotFoundException(itemId));

            GetItemResponse response = GetItemResponse.newBuilder()
                    .setItemId(item.id())
                    .setName(item.name())
                    .setAvailableQuantity(item.availableQuantity())
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (ItemNotFoundException ex) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Item was not found")
                            .asRuntimeException());
        } catch (RuntimeException ex) {
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Unable to retrieve item")
                            .asRuntimeException());
        }
    }
}
~~~

Định nghĩa exception domain/application được dùng trong adapter:

~~~java
package com.example.inventory.application;

public final class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException(String itemId) {
        super("Item not found: " + itemId);
    }
}
~~~

Annotation @GrpcService của Spring gRPC vừa đánh dấu service để starter đăng ký vừa để Spring quản lý dependency injection.

Adapter có ba trách nhiệm:

1. Validate dữ liệu ở ranh giới RPC.
2. Gọi use case và ánh xạ domain result sang protobuf response.
3. Chuyển lỗi thành gRPC status ổn định.

Không trả stack trace, SQL message, hostname hoặc thông tin nhạy cảm trong Status description. Ghi log exception ở server với correlation/trace context phù hợp; client chỉ nhận thông tin lỗi đã được kiểm soát.

Mỗi unary RPC thành công phải phát đúng một onNext rồi một onCompleted. Khi lỗi, phát onError và không gọi thêm terminal signal khác.

## 10. Kiểm tra lỗi và status

Nên thống nhất cách ánh xạ lỗi giữa application và gRPC:

| Tình huống | gRPC status gợi ý |
|---|---|
| item_id rỗng hoặc sai định dạng | INVALID_ARGUMENT |
| Không tìm thấy item | NOT_FOUND |
| Người gọi chưa xác thực | UNAUTHENTICATED |
| Người gọi không có quyền xem item | PERMISSION_DENIED |
| Trạng thái nghiệp vụ không cho phép | FAILED_PRECONDITION |
| Dependency tạm thời không khả dụng | UNAVAILABLE |
| RPC vượt deadline | DEADLINE_EXCEEDED |
| Lỗi không dự kiến | INTERNAL |

Không dùng INTERNAL cho mọi lỗi domain. Status là một phần contract mà client dùng để quyết định retry, hiển thị lỗi hoặc xử lý tiếp. Tránh trả UNAVAILABLE cho lỗi validation vì client có thể retry vô ích.

Với hệ thống lớn, chuyển exception mapping sang interceptor hoặc error handler dùng chung để các service method không lặp logic. Dù chọn cách nào, vẫn giữ một policy status thống nhất.

## 11. Khởi động và kiểm tra server

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra log startup:

- Spring application context đã khởi động thành công.
- Spring gRPC server đã bind port 9090.
- InventoryGrpcService được phát hiện và đăng ký.
- Không có lỗi port already in use, bean creation hoặc generated class mismatch.

Server chạy không đồng nghĩa RPC đã hoạt động. Tiếp tục probe bằng gRPC client để xác minh service/method và response.

## 12. Gọi server bằng grpcurl

Nếu server bật reflection, liệt kê service:

~~~bash
grpcurl -plaintext localhost:9090 list
~~~

Xem service:

~~~bash
grpcurl -plaintext localhost:9090 describe inventory.v1.InventoryService
~~~

Gọi unary method:

~~~bash
grpcurl -plaintext \
  -d '{"itemId":"item-100"}' \
  localhost:9090 \
  inventory.v1.InventoryService/GetItem
~~~

Response dự kiến có itemId, name và availableQuantity. Thử ID không tồn tại để xác nhận server trả NOT_FOUND; thử chuỗi rỗng để xác nhận INVALID_ARGUMENT.

Nếu reflection không bật, grpcurl list không thể liệt kê service dù server vẫn chạy. Dùng file .proto:

~~~bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto inventory/v1/inventory.proto \
  -d '{"itemId":"item-100"}' \
  localhost:9090 \
  inventory.v1.InventoryService/GetItem
~~~

Không bật reflection trong production chỉ để thuận tiện debug nếu policy bảo mật không cho phép. Có thể giữ reflection trong profile development hoặc dùng descriptor/protoset do build tạo ra.

## 13. Viết test cho service

Unit test cho use case nên gọi trực tiếp use case và dùng fake repository. Để kiểm tra gRPC adapter, generated stub, protobuf mapping và status mà không mở TCP, dùng in-process gRPC transport.

Ví dụ test qua generated stub:

~~~java
import com.example.inventory.application.InventoryUseCase;
import com.example.inventory.domain.InventoryItem;
import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class InventoryGrpcServiceTest {
    private Server server;
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        InventoryUseCase useCase = itemId ->
                itemId.equals("item-100")
                        ? Optional.of(new InventoryItem("item-100", "Keyboard", 12))
                        : Optional.empty();

        server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new InventoryGrpcService(useCase))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void returnsExistingItem() {
        GetItemResponse response = stub.getItem(
                GetItemRequest.newBuilder()
                        .setItemId("item-100")
                        .build());

        assertEquals("Keyboard", response.getName());
        assertEquals(12, response.getAvailableQuantity());
    }

    @Test
    void mapsMissingItemToNotFound() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
~~~

Ví dụ giả định test có dependency grpc-inprocess, JUnit Jupiter và class InventoryGrpcService/ItemNotFoundException ở các package đã nêu. Phiên bản grpc-inprocess phải đồng bộ với gRPC Java runtime và protoc plugin. Trong test production, chờ termination khi cần, tránh chia sẻ mutable state giữa test chạy song song và bảo đảm cleanup ngay cả khi setup thất bại.

In-process test không chứng minh TCP, TLS, HTTP/2, port mapping hoặc proxy hoạt động. Giữ một số integration test nhỏ dùng server thật trên port tạm để kiểm tra transport và cấu hình deploy.

## 14. Checklist hoàn thành dự án

| Hạng mục | Tiêu chí hoàn thành |
|---|---|
| Spring Boot project | Application context khởi động |
| Dependency | Starter và gRPC/protobuf runtime tương thích |
| Protobuf contract | Service, method và message được khai báo rõ |
| Code generation | Có Java message classes và gRPC service base |
| Server configuration | Port gRPC được cấu hình đúng |
| Service registration | @GrpcService được starter phát hiện |
| Dependency injection | Use case được inject vào adapter |
| Unary response | Gửi đúng một response rồi complete |
| Error mapping | Validation và not found trả status phù hợp |
| Manual probe | grpcurl gọi được method |
| Automated test | Unit và in-process test kiểm tra logic/contract |
| Lifecycle | Server được quản lý cùng Spring context |

## 15. Lỗi thường gặp khi tạo Spring Boot gRPC server

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy generated class | Chưa chạy code generation hoặc source root chưa được IDE nhận | Kiểm tra src/main/proto, task generateProto và Gradle sync |
| Có message class nhưng thiếu service base | Chưa cấu hình gRPC protoc plugin | Kiểm tra plugins grpc trong task generation |
| Runtime báo NoClassDefFoundError | Thiếu hoặc lệch phiên bản gRPC/protobuf runtime | Kiểm tra dependency management/BOM và generated code |
| Spring không đăng ký service | Thiếu annotation đúng starter hoặc bean không được scan | Dùng @GrpcService đúng package/version và kiểm tra startup log |
| Port bind thất bại | Port bị chiếm hoặc cấu hình sai | Kiểm tra listener và property gRPC hiệu lực |
| Client gọi nhầm HTTP port | Nhầm server.port với gRPC port | Xác định port riêng của gRPC server |
| UNIMPLEMENTED | Service/method name sai hoặc service chưa register | So sánh protobuf descriptor và server registration |
| UNAUTHENTICATED | Security metadata/token chưa đúng | Kiểm tra interceptor và credential |
| grpcurl list không hoạt động | Reflection chưa bật | Dùng .proto/protoset để gọi method |
| Test rò channel/server | Không cleanup in-process fixture | Shutdown channel/server trong lifecycle test |

## 16. Mở rộng sau khi server cơ bản hoạt động

Khi unary server đã chạy ổn định, có thể mở rộng theo từng năng lực:

- **TLS/mTLS:** nạp certificate và trust chain qua cấu hình starter đúng phiên bản; kiểm tra SAN, SNI và ALPN h2.
- **Authentication/authorization:** xác thực metadata hoặc client identity, sau đó kiểm tra quyền ở service/use-case boundary.
- **Deadline/cancellation:** yêu cầu client đặt deadline và truyền remaining budget đến dependency.
- **Interceptors:** thêm logging, correlation ID, metrics và error mapping dùng chung.
- **Health/reflection:** bật health checking và reflection theo môi trường triển khai.
- **Streaming:** bổ sung server/client/bidirectional streaming theo contract và quản lý flow/cancellation.
- **Integration test:** kiểm tra TCP, TLS, database, broker và service discovery trong môi trường cô lập.

Không thêm tất cả các concern vào một service method. Giữ adapter mỏng, use case tập trung vào nghiệp vụ và hạ tầng được cấu hình ở các boundary phù hợp.


## 17. Kiểm thử qua server do Spring quản lý

In-process test ở phần trước xác minh generated stub, service adapter, protobuf mapping và gRPC status mà không mở socket. Nó không chứng minh Spring đã phát hiện bean, starter đã bind listener hoặc cấu hình port hoạt động. Để xác minh toàn bộ đường đi trong ứng dụng, cần ít nhất một integration test khởi động Spring context và gọi RPC qua TCP đến server do starter quản lý.

Ví dụ sau dùng port riêng 19090. Test dùng cùng bean `InMemoryInventoryService` và `InventoryGrpcService` được Spring component scan phát hiện:

~~~java
package com.example.inventory.grpc;

import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = "spring.grpc.server.port=19090")
class InventoryGrpcServerIntegrationTest {
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void connectToSpringManagedServer() {
        channel = ManagedChannelBuilder
                .forAddress("localhost", 19090)
                .usePlaintext()
                .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(2, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }

    @Test
    void springRegistersAndServesInventoryRpc() {
        GetItemResponse response = stub.getItem(
                GetItemRequest.newBuilder()
                        .setItemId("item-100")
                        .build());

        assertEquals("item-100", response.getItemId());
        assertEquals("Keyboard", response.getName());
        assertEquals(12, response.getAvailableQuantity());
    }

    @Test
    void springServerReturnsNotFoundForUnknownItem() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
~~~

Test này xác minh đồng thời Spring context khởi động, `@GrpcService` được phát hiện, starter bind port và generated client gọi được method. Port cố định chỉ là ví dụ; không chạy nhiều bản test song song cùng port. Nếu starter/version đang dùng hỗ trợ cấp port ngẫu nhiên và công bố port thực tế, ưu tiên cơ chế đó cho test suite chạy song song.

Dùng `usePlaintext()` ở đây vì test local không đi qua mạng không tin cậy. Integration test TLS riêng cần cấu hình certificate test và client trust tương ứng. Luôn đặt deadline để test lỗi không treo suite và đóng channel sau mỗi test.

## 18. Lifecycle và các yêu cầu trước production

Spring gRPC starter quản lý server cùng ApplicationContext. Các service bean phải được tạo và inject dependency trước khi nhận traffic; khi context đóng, server được dừng theo lifecycle framework. Không tự tạo `NettyServer` thứ hai trong constructor hoặc business bean khi starter đã quản lý listener.

Trước khi triển khai, rà soát các điểm sau:

- **Port và network:** xác định riêng HTTP port và gRPC port; map đúng container port, Kubernetes Service `port`/`targetPort`, selector và endpoint Ready. Cấu hình ingress/load balancer hỗ trợ HTTP/2 và gRPC.
- **TLS/mTLS:** dùng certificate và private key được quản lý an toàn; client xác minh trust chain và SAN. Nếu bật mTLS, server cần trust client CA và client phải gửi certificate phù hợp. Cấu hình theo đúng Spring gRPC starter version.
- **Authentication/authorization:** xác thực principal ở security boundary, kiểm tra quyền cho từng RPC và không tin tenant ID do client tự khai báo.
- **Deadline/cancellation:** yêu cầu client đặt deadline hợp lý; truyền remaining budget đến downstream và dừng công việc có thể hủy khi call bị cancel.
- **Message limits:** giới hạn inbound/outbound message size và metadata size theo nhu cầu, tránh payload lớn làm cạn bộ nhớ.
- **Observability:** ghi method name, status code, duration và correlation ID; che token và dữ liệu cá nhân khỏi log.
- **Health/readiness:** chỉ nhận traffic khi listener và dependency bắt buộc sẵn sàng. Phân biệt health của HTTP management endpoint với gRPC Health Checking Protocol.
- **Graceful shutdown:** ngừng nhận call mới, cho call đang chạy thời gian hoàn tất theo policy rồi dừng listener. Streaming producer phải dừng khi client cancel.
- **Capacity:** chọn executor, concurrency limit và resource policy theo tải thực tế; không giả định một RPC luôn tương đương một thread riêng.

Property TLS, health, reflection và graceful shutdown thay đổi theo phiên bản starter. Dùng cấu hình được hỗ trợ bởi version đã pin; không sao chép property từ một thư viện Spring gRPC khác.

## 19. Chẩn đoán lỗi khởi động và đăng ký service

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Spring khởi động nhưng gRPC port không mở | Starter thiếu, auto-configuration bị loại hoặc port config sai | Kiểm tra dependency, startup log và property hiệu lực |
| Server mở port nhưng method trả `UNIMPLEMENTED` | Service bean không được scan/bind hoặc method path sai | Kiểm tra `@GrpcService`, package, descriptor và full method path |
| Không compile `InventoryServiceImplBase` | Chưa sinh gRPC Java source hoặc thiếu gRPC plugin | Kiểm tra `generateProto` và generated source output |
| Client nhận `UNAVAILABLE` | Server chưa sẵn sàng, sai host/port hoặc transport không tương thích | Kiểm tra listener, container port, network và TLS/plaintext |
| Client nhận `INVALID_ARGUMENT` | Handler đã chạy và validation từ chối request | Kiểm tra request field và status contract |
| Test treo | Thiếu deadline hoặc channel/server không đóng | Đặt deadline, teardown channel và xem server log |
| Hai server cùng chiếm port | Có server thủ công song song với auto-configuration hoặc test dùng chung port | Chỉ dùng một server lifecycle và cấp port test riêng |
| Bean tồn tại nhưng RPC không gọi được | Bean chưa được bind vào server hoặc server chưa start | Gọi bằng generated stub qua listener trong integration test |

Khi server không mở port, xác định auto-configuration đã chạy chưa, service bean có nằm trong component scan không và generated service definition có đúng không. Không chữa lỗi bằng cách tự tạo thêm Netty server khi starter chưa được kiểm tra; việc đó có thể gây hai listener, đăng ký service hai lần và shutdown không nhất quán.

**Ghi nhớ:** Tạo Spring Boot gRPC server là ghép protobuf contract và generated service base vào lifecycle của Spring. Protobuf plugin sinh message/stub; Spring gRPC starter quản lý listener và registration; `@GrpcService` đưa implementation vào server; use case giữ logic nghiệp vụ. Cấu hình đúng gRPC port, xác minh bằng `grpcurl`, kiểm tra mapping/status bằng in-process test và có ít nhất một integration test gọi server do Spring quản lý qua TCP. Sau khi đường unary hoạt động, hoàn thiện TLS, security, deadline, health, graceful shutdown và observability theo môi trường triển khai.
