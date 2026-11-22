# gRPC, protobuf và các thành phần phải cấu hình ngoài Spring Boot

Trong hệ thống tích hợp Spring Boot, REST/JSON phù hợp với nhiều API HTTP công khai; JMS hoặc các broker thông điệp hỗ trợ chuyển giao công việc bất đồng bộ; còn **gRPC** là lựa chọn để các dịch vụ gọi nhau qua hợp đồng có kiểu dữ liệu rõ ràng, thường dùng **Protocol Buffers (protobuf)** để biểu diễn dữ liệu và **HTTP/2** làm giao thức truyền tải. gRPC đặc biệt hữu ích cho RPC nội bộ có tần suất cao, yêu cầu stub sinh mã, payload gọn và streaming. Nhưng một RPC hoàn tất không tương đương một thông điệp đã được lưu bền vững trong broker.

Bài học thuộc chương **Thư viện bổ sung** của module **SPRING_BOOT_INTEGRATION**, nơi xem xét tích hợp HTTP client, cơ sở dữ liệu, cache, broker thông điệp và Spring Integration adapter. Trọng tâm ở đây là hợp đồng dữ liệu, cấu hình, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và khả năng quan sát của luồng gRPC. Ta sẽ phân biệt những gì do **gRPC Java/protobuf** cung cấp với những gì **ứng dụng Spring Boot hoặc hạ tầng phải tự cấu hình**. Việc thêm thư viện grpc-java vào classpath không tự bảo đảm rằng ứng dụng đã mở cổng gRPC, đăng ký service, tạo client channel, cấu hình TLS hay định nghĩa deadline. Các starter tích hợp có thể hỗ trợ tự động hóa một phần, nhưng khả năng cụ thể phụ thuộc phiên bản và thư viện được chọn.

## 1. gRPC dùng trong bức tranh tích hợp thế nào?

Giả sử `checkout-service` cần kiểm tra tồn kho trước khi tạo đơn hàng. Dòng xử lý đồng bộ có thể là:

~~~mermaid
sequenceDiagram
    participant C as checkout-service
    participant I as inventory-service (gRPC)
    participant D as Inventory database
    C->>I: CheckAvailability(request) - HTTP/2
    I->>D: Đọc tồn kho
    D-->>I: Stock snapshot
    I-->>C: CheckAvailabilityResponse
~~~

gRPC chuyển một lời gọi method từ client sang server và trả response hoặc status lỗi. Điều này tạo ra sự phụ thuộc trong thời gian thực: khi server chậm hoặc không sẵn sàng, caller phải có deadline và chính sách xử lý lỗi. Để phục hồi một công việc khi service xử lý offline nhiều giờ, cần queue/broker hoặc một kho sự kiện có cơ chế lưu trữ thích hợp.

| Thành phần | Chức năng chủ yếu | Không tự giải quyết |
| --- | --- | --- |
| **Protobuf** | Khai báo schema, field number, kiểu dữ liệu và mã hóa binary | Validation nghiệp vụ, auth, transaction |
| **gRPC Java** | RPC stub, HTTP/2 transport, status, metadata, deadline, streaming | Tích hợp trọn vẹn lifecycle và policy của Spring Boot |
| **Spring Boot** | Bean, dependency injection, configuration, service/transaction, lifecycle ứng dụng | Sinh protobuf hoặc ngầm tạo mọi gRPC endpoint chỉ từ grpc-java dependency |
| **Broker/JMS** | Chuyển giao message theo queue/topic và chính sách của broker | Thay thế hoàn toàn synchronous RPC |
| **Hạ tầng** | DNS, LB, ingress, TLS, certificate, network policy, health và observability | Tự biết schema compatibility của hai service |

### Bốn kiểu RPC

| Kiểu | Dạng service method trong proto | Ví dụ |
| --- | --- | --- |
| Unary | `rpc Check(A) returns (B);` | Kiểm tra tồn kho, lấy giá |
| Server streaming | `rpc Watch(A) returns (stream B);` | Phát thay đổi trạng thái theo kết nối |
| Client streaming | `rpc Upload(stream A) returns (B);` | Tải nhiều chunk dữ liệu |
| Bidirectional streaming | `rpc Exchange(stream A) returns (stream B);` | Phiên trao đổi dữ liệu hai chiều |

Streaming là một luồng truyền qua kết nối và có flow control. Nó không mặc nhiên lưu trữ lịch sử, offset hoặc tự phát lại thông điệp sau khi một consumer đã offline. Các yêu cầu resume/replay phải được thiết kế bằng state và nơi lưu dữ liệu riêng.

## 2. Thiết kế hợp đồng protobuf: từ file .proto đến stub Java

Tạo file `src/main/proto/inventory/v1/inventory.proto`:

~~~proto
syntax = "proto3";

package integration.inventory.v1;

option java_multiple_files = true;
option java_package = "com.example.integration.inventory.v1";
option java_outer_classname = "InventoryContractProto";

service InventoryService {
  rpc CheckAvailability(CheckAvailabilityRequest)
      returns (CheckAvailabilityResponse);
}

message CheckAvailabilityRequest {
  string sku = 1;
  int32 requested_quantity = 2;
  string request_id = 3;
}

message CheckAvailabilityResponse {
  bool available = 1;
  int64 stock_version = 2;
  string warehouse_id = 3;
}
~~~

Khi build, `protoc` sinh message Java, còn plugin `protoc-gen-grpc-java` sinh mã service/stub. Với `java_multiple_files = true`, mã Java có các lớp như `CheckAvailabilityRequest`, `CheckAvailabilityResponse` và `InventoryServiceGrpc`. Client dùng `InventoryServiceGrpc.newBlockingStub(channel)` hoặc loại stub bất đồng bộ; server triển khai `InventoryServiceGrpc.InventoryServiceImplBase`.

Trong protobuf, **field number là danh tính trên wire**, không phải thứ tự hiển thị. `string sku = 1` và `int32 requested_quantity = 2` không thể tùy tiện đổi field number trong hợp đồng đã phát hành. `java_package` điều khiển Java package; `package` điều khiển namespace protobuf và góp phần tạo full RPC method name trên wire. Đổi package/service/method có thể làm client không gọi được dù payload vẫn tương thích.

### Default, presence và validation

Ở `proto3`, một scalar string thường mặc định rỗng, số bằng 0 và boolean bằng false. Với các scalar không dùng presence, phía server không thể dễ dàng phân biệt “client không gửi” và “client đã gửi giá trị mặc định”. Nếu có yêu cầu này, dùng `optional` hoặc `oneof`:

~~~proto
message UpdateInventoryRequest {
  string sku = 1;

  optional int32 target_quantity = 2;

  oneof adjustment {
    int32 increase_by = 3;
    int32 decrease_by = 4;
  }
}
~~~

Mã sinh có thể cung cấp `hasTargetQuantity()` cho trường `optional`. `oneof` mô tả lựa chọn loại trừ lẫn nhau, nhưng server vẫn phải kiểm tra trường hợp không chọn giá trị nào, số âm hoặc SKU không hợp lệ. Protobuf chỉ kiểm tra cấu trúc/kiểu dữ liệu trên wire; quy tắc nghiệp vụ vẫn nằm ở application service.

Với dữ liệu tiền, hạn chế `float` và `double` khi cần chính xác: dùng `int64` theo đơn vị nhỏ nhất cùng mã tiền tệ hoặc một schema decimal có quy định cụ thể. Với timestamp, dùng `google.protobuf.Timestamp` hoặc định dạng thời gian được thỏa thuận rõ. Với enum nên có giá trị số 0 mang nghĩa `UNSPECIFIED` để không diễn giải mặc định thành một trạng thái nghiệp vụ hợp lệ.

### Tương thích schema theo thời gian

| Thay đổi | Đánh giá | Cần làm |
| --- | --- | --- |
| Thêm field mới với số chưa sử dụng | Thường tương thích wire | Xử lý giá trị mặc định và consumer cũ |
| Đổi tên field nhưng giữ số/kiểu | Có thể tương thích wire | Kiểm tra code sinh, JSON mapping và API docs |
| Xóa field cũ | Có thể tương thích wire | Dùng `reserved` để không tái sử dụng số/tên |
| Đổi field number | Breaking | Tạo field mới hoặc version API |
| Đổi kiểu/ý nghĩa của field | Nguy cơ breaking | Kiểm tra cả wire type và ngữ nghĩa |
| Đổi tên service/RPC/protobuf package | Breaking đối với route RPC | Version method/service và cập nhật clients |
| Thêm RPC mới | Thường giữ được RPC cũ | Chỉ gọi khi server đã hỗ trợ |

Ví dụ khi loại bỏ trường từng được phát hành:

~~~proto
message StockSnapshot {
  string sku = 1;
  reserved 2, 5;
  reserved "legacy_location";
  int64 version = 3;
}
~~~

Đừng tái sử dụng tag 2 và 5 để mang nghĩa khác. Nên lưu `.proto` trong version control hoặc artifact contract quản lý tập trung, sinh mã trong CI và kiểm tra tương thích khi nhiều service không thể nâng cấp đồng thời. “Tương thích protobuf” chỉ là một phần: nếu consumer cũ không hiểu một enum mới hoặc yêu cầu nghiệp vụ mới, contract vẫn có thể không tương thích về hành vi.

## 3. Các dependency và bước sinh mã phải cấu hình

Dùng grpc-java thuần, các artifact phổ biến gồm:

| Artifact | Vai trò |
| --- | --- |
| `io.grpc:grpc-protobuf` | Tích hợp protobuf marshaller cho RPC |
| `io.grpc:grpc-stub` | Client stub, StreamObserver và API hỗ trợ |
| `io.grpc:grpc-netty-shaded` | HTTP/2 Netty transport với dependencies được shaded |
| `io.grpc:grpc-services` | Dịch vụ hỗ trợ như gRPC health/reflection nếu sử dụng |
| `io.grpc:grpc-inprocess` | Server/channel in-process cho unit/integration test |
| `com.google.protobuf:protobuf-java` | Protobuf runtime, cần tương thích protoc đã dùng |
| `protoc` + `protoc-gen-grpc-java` | Sinh Java message và Java gRPC code khi build |

Ví dụ một phần `pom.xml` dùng gRPC BOM:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.grpc</groupId>
      <artifactId>grpc-bom</artifactId>
      <version>${grpc.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-protobuf</artifactId>
  </dependency>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-stub</artifactId>
  </dependency>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-netty-shaded</artifactId>
  </dependency>
</dependencies>
~~~

`grpc.version` cần được dự án chọn và quản lý thống nhất; BOM giúp đồng bộ các artifact gRPC nhưng không thay thế việc quản lý tương thích `protobuf-java`, protoc và generator. Nếu gặp lỗi lớp thiếu/sai method giữa runtime và code sinh, kiểm tra dependency tree và version alignment trước khi sửa code nghiệp vụ.

Với Maven, một cách sinh Java source là `protobuf-maven-plugin` cùng `os-maven-plugin`:

~~~xml
<build>
  <extensions>
    <extension>
      <groupId>kr.motd.maven</groupId>
      <artifactId>os-maven-plugin</artifactId>
      <version>${os.maven.plugin.version}</version>
    </extension>
  </extensions>

  <plugins>
    <plugin>
      <groupId>org.xolstice.maven.plugins</groupId>
      <artifactId>protobuf-maven-plugin</artifactId>
      <version>${protobuf.maven.plugin.version}</version>
      <configuration>
        <protocArtifact>
          com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}
        </protocArtifact>
        <pluginId>grpc-java</pluginId>
        <pluginArtifact>
          io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}
        </pluginArtifact>
      </configuration>
      <executions>
        <execution>
          <goals>
            <goal>compile</goal>
            <goal>compile-custom</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Đây là **khung cấu hình**, phải khai báo các version property `grpc.version`, `protobuf.version`, `os.maven.plugin.version` và `protobuf.maven.plugin.version` phù hợp với project. Không dùng mặc định một số phiên bản lấy ngẫu nhiên vì generator, runtime và JDK cần tương thích. Với Gradle, plugin `com.google.protobuf` thực hiện vai trò tương tự. CI phải chạy bước sinh code, compile và contract test trước khi phát hành artifact.

Một số tổ hợp protoc/JDK sinh annotation `@javax.annotation.Generated` nhưng JDK hiện tại không mang sẵn API tương ứng; lúc ấy cần dependency annotation ở compile scope hoặc generator phù hợp. Đây là vấn đề annotation của **mã sinh**, độc lập với lựa chọn namespace `jakarta.*` trong Spring Boot.

### Starter tích hợp gRPC với Spring là một lựa chọn khác

Các annotation như `@GrpcService`, `@GrpcClient` thường thuộc **starter tích hợp** cụ thể, không phải grpc-java core. Chọn một starter cần kiểm tra rõ phiên bản Spring Boot/JDK mà nó hỗ trợ, server/channel auto-configuration, TLS, interception, metrics, health, shutdown và testing. Một ứng dụng không nên vừa khởi động server bằng starter vừa tự mở một server cùng cổng qua `NettyServerBuilder`; hãy xác định cơ chế quản lý duy nhất.

Các ví dụ tiếp theo dùng **grpc-java + Spring bean thủ công** để minh họa đầy đủ các thành phần người phát triển phải cấu hình.

## 4. Triển khai server gRPC trong ứng dụng Spring Boot

Endpoint nhận protobuf request, kiểm tra đầu vào, gọi Spring service và trả response/status. Với một Spring service có transaction, đưa logic SQL vào tầng service do container quản lý; gRPC endpoint chỉ làm nhiệm vụ chuyển đổi và ánh xạ lỗi.

### 4.1. Endpoint Java

~~~java
package com.example.integration.inventory;

import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.CheckAvailabilityResponse;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class InventoryGrpcEndpoint
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final InventoryApplicationService inventory;

    public InventoryGrpcEndpoint(InventoryApplicationService inventory) {
        this.inventory = inventory;
    }

    @Override
    public void checkAvailability(
            CheckAvailabilityRequest request,
            StreamObserver<CheckAvailabilityResponse> observer) {

        if (request.getSku().isBlank()
                || request.getRequestedQuantity() <= 0) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("sku và quantity phải hợp lệ")
                    .asRuntimeException());
            return;
        }

        try {
            var snapshot = inventory.check(
                    request.getSku(), request.getRequestedQuantity());

            var response = CheckAvailabilityResponse.newBuilder()
                    .setAvailable(snapshot.available())
                    .setStockVersion(snapshot.stockVersion())
                    .setWarehouseId(snapshot.warehouseId())
                    .build();

            observer.onNext(response);
            observer.onCompleted();
        } catch (InventoryNotFoundException ex) {
            observer.onError(Status.NOT_FOUND
                    .withDescription("Không tìm thấy SKU")
                    .asRuntimeException());
        } catch (Exception ex) {
            observer.onError(Status.INTERNAL
                    .withDescription("Không thể kiểm tra tồn kho")
                    .asRuntimeException());
        }
    }
}
~~~

Trong ví dụ, `InventoryApplicationService` và `InventoryNotFoundException` là lớp nghiệp vụ do project định nghĩa. Một hợp đồng đơn giản cho service này là:

~~~java
public interface InventoryApplicationService {
    InventorySnapshot check(String sku, int requestedQuantity);
}

public record InventorySnapshot(
        boolean available, long stockVersion, String warehouseId) {
}
~~~

Implementation có thể dùng JPA/JDBC và `@Transactional(readOnly = true)`. Khi dùng Spring transaction proxy, gRPC endpoint cần gọi qua bean service được Spring quản lý để advice chạy đúng. Không kỳ vọng gRPC tự tạo transaction.

Với unary RPC, luồng thành công là **`onNext(response)` rồi `onCompleted()`**; luồng lỗi là **`onError(exception)`** và kết thúc. Không gọi success và error cho cùng request. Không trả stacktrace hoặc dữ liệu bí mật trong status description. Dùng trace ID để tìm bản ghi lỗi nội bộ.

### 4.2. Cổng và lifecycle

Một web application có thể mở REST trên `server.port: 8080` trong khi một Netty gRPC server khác lắng nghe `9090`. Việc cấu hình `server.port` của Spring Boot không tự động đồng nghĩa đã mở gRPC port.

~~~yaml
server:
  port: 8080

app:
  grpc:
    server:
      port: 9090
~~~

Cấu hình server bằng Spring bean:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfiguration {

    @Bean
    Server grpcServer(
            InventoryGrpcEndpoint endpoint,
            @Value("${app.grpc.server.port:9090}") int port) {
        return NettyServerBuilder.forPort(port)
                .addService(endpoint)
                .build();
    }

    @Bean
    SmartLifecycle grpcServerLifecycle(Server grpcServer) {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                try {
                    grpcServer.start();
                    running = true;
                } catch (IOException ex) {
                    throw new IllegalStateException(
                            "Không mở được cổng gRPC", ex);
                }
            }

            @Override
            public void stop() {
                grpcServer.shutdown();
                try {
                    if (!grpcServer.awaitTermination(
                            10, TimeUnit.SECONDS)) {
                        grpcServer.shutdownNow();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    grpcServer.shutdownNow();
                } finally {
                    running = false;
                }
            }

            @Override
            public boolean isRunning() {
                return running;
            }
        };
    }
}
~~~

Server `build()` chưa có nghĩa đã `start()`. `SmartLifecycle` kết nối quá trình mở/dừng server với Spring, quản lý tài nguyên khi ứng dụng shutdown. Khi cần graceful drain ở production, chuyển readiness trước khi dừng nhận request mới và cho RPC đang chạy một khoảng thời gian hữu hạn. Container/ingress phải expose và route tới cổng 9090; đừng chỉ khai báo HTTP port 8080 rồi giả định gRPC sẽ xuất hiện.

Ví dụ tối giản này chưa bật TLS, interceptor hoặc health; các thành phần đó được trình bày ở phần sau.

## 5. Cấu hình client: ManagedChannel, stub và deadline

`ManagedChannel` là tài nguyên có thể tái sử dụng qua nhiều request; không tạo channel mới cho từng lời gọi RPC. Stub từ protobuf là wrapper nhẹ được tạo cho một channel và có thể gắn deadline/metadata/call options khác nhau.

~~~yaml
app:
  grpc:
    inventory:
      host: inventory.internal
      port: 9090
      tls-enabled: true
~~~

~~~java
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel(
            @Value("${app.grpc.inventory.host}") String host,
            @Value("${app.grpc.inventory.port}") int port,
            @Value("${app.grpc.inventory.tls-enabled:true}") boolean tls) {

        ManagedChannelBuilder<?> builder =
                ManagedChannelBuilder.forAddress(host, port);

        if (tls) {
            builder.useTransportSecurity();
        } else {
            builder.usePlaintext(); // Chỉ dùng khi mô hình mạng cho phép.
        }
        return builder.build();
    }

    @Bean
    InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryServiceGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

Nếu có nhiều kênh tương tự, dùng bean name, `@Qualifier` hoặc factory phù hợp để tránh inject nhầm. `shutdown()` bắt đầu dừng channel; nếu ứng dụng cần chờ các RPC hoàn tất, quản lý thêm `awaitTermination` và giới hạn thời gian bằng lifecycle của ứng dụng.

Ví dụ gọi unary:

~~~java
import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public boolean isAvailable(String sku, int quantity, String requestId) {
        var request = CheckAvailabilityRequest.newBuilder()
                .setSku(sku)
                .setRequestedQuantity(quantity)
                .setRequestId(requestId)
                .build();

        try {
            var response = stub.withDeadlineAfter(
                    700, TimeUnit.MILLISECONDS)
                    .checkAvailability(request);
            return response.getAvailable();
        } catch (StatusRuntimeException ex) {
            if (ex.getStatus().getCode() == Status.Code.NOT_FOUND) {
                throw new IllegalArgumentException(
                        "SKU không tồn tại", ex);
            }
            // Không coi UNAVAILABLE hoặc DEADLINE_EXCEEDED là hết hàng.
            throw ex;
        }
    }
}
~~~

Deadline là **ngân sách thời gian cho một RPC**. Đừng cho mọi downstream liên tiếp sử dụng đầy đủ tổng SLA của API upstream. Nếu checkout có 1.500 ms để trả phản hồi và cần gọi inventory, shipping và payment, phải chia ngân sách cho từng bước, xử lý local và trả response.

`BlockingStub` dễ đọc nhưng giữ thread chờ I/O; nếu ứng dụng dùng WebFlux hoặc cần nhiều concurrent call, cân nhắc async/future stub và executor phù hợp, tránh blocking trên event loop.

## 6. Những thành phần gRPC phải cấu hình ở ngoài Boot

| Thành phần | Chủ sở hữu thường gặp | Hậu quả khi bỏ sót |
| --- | --- | --- |
| Protoc/generator và code build | Maven/Gradle, CI | Không sinh stub, runtime/code sinh lệch |
| Server port, bind, lifecycle | Starter hoặc Spring bean | Server không lắng nghe hoặc trùng port |
| Service registration | Server bootstrap | `UNIMPLEMENTED` do service chưa đăng ký |
| ManagedChannel/stub/shutdown | Client integration layer | Rò rỉ kết nối, channel tạo quá nhiều |
| DNS, service discovery và LB | Platform cùng client | Chỉ đi một endpoint hoặc mất kết nối khi scale |
| TLS/mTLS, CA, rotation | Security, platform, service | Lộ traffic hoặc handshake lỗi |
| AuthN/AuthZ | Interceptor và policy | Xác thực yếu, gọi RPC sai quyền |
| Deadline, retry/backoff | Caller | Treo request, retry storm, ghi trùng |
| Health/readiness và graceful shutdown | Service/platform | Traffic đến pod chưa sẵn sàng |
| Metrics, tracing, log | Observability stack | Không thấy RPC timeout/độ trễ |
| HTTP/2, ingress và gateway | Network/ingress/mesh | Proxy không hỗ trợ gRPC hoặc cắt streaming |
| Schema compatibility | Contract repository, CI | Client/server hiểu khác contract |

### Cổng gRPC và HTTP/2

Một gRPC Java server dạng Netty thường mở cổng riêng. Cần cấu hình container port, Kubernetes Service/Ingress, proxy, TLS/ALPN hoặc HTTP/2 cleartext (h2c) theo từng mô hình. HTTP/2 connection sống lâu có đặc điểm cân bằng tải khác nhiều request HTTP/1.1 ngắn. DNS trả về nhiều IP không đảm bảo từng RPC được dàn đều tới mọi pod; cần thử nghiệm resolver và load balancing thực tế.

### Browser và gRPC-Web

Browser không nhất thiết gọi binary gRPC giống một Java client. Khi frontend cần gọi service, thường dùng gRPC-Web kèm proxy phù hợp, hoặc cung cấp REST/JSON gateway. Gateway phải được kiểm tra hỗ trợ request/response trailers, max message size, streaming, idle timeout và ánh xạ lỗi; không giả định mọi reverse proxy HTTP/1.1 chuyển tiếp được gRPC nguyên vẹn.

### TLS và mTLS

`useTransportSecurity()` trên channel yêu cầu kết nối TLS và xác minh server theo cơ chế trust tương ứng. Server `NettyServerBuilder.forPort()` trong ví dụ chưa cấu hình TLS; client TLS sẽ không thể handshake thành công với server plaintext như vậy. Để minh họa server-side TLS:

~~~java
var server = NettyServerBuilder.forPort(port)
        .useTransportSecurity(certChainFile, privateKeyFile)
        .addService(endpoint)
        .build();
~~~

`certChainFile` và `privateKeyFile` ở đây là `java.io.File` do ứng dụng nhận từ secret/file cấu hình. Với production cần quản lý CA, hostname/SAN, rotation, quyền đọc certificate và cơ chế trust. **mTLS** yêu cầu cấu hình thêm client certificate/trust và server kiểm tra certificate của caller; thường thực hiện qua Netty SSL context hoặc mesh đã xác định rõ boundary. TLS xác thực kênh, **authorization** vẫn cần kiểm tra principal/quyền theo method. Không chấp nhận một trường payload `userId` do client tự khai như danh tính đã xác minh.

Interceptor phía server thường làm nhiệm vụ xác thực bearer token hoặc client identity, đưa claim vào `io.grpc.Context`, thêm correlation/trace và giới hạn tài nguyên. Metadata như `Authorization` phải được bảo vệ; không log token, password, key hoặc payload nhạy cảm. Dùng `UNAUTHENTICATED` khi thiếu/sai chứng thực, `PERMISSION_DENIED` khi đã xác thực nhưng thiếu quyền.

## 7. Lỗi, deadline, retry và hiệu ứng nghiệp vụ một lần

gRPC có status code chuẩn tách khỏi các field protobuf của response. Khi thiết kế client cần phân biệt:

| Status | Khi nào xuất hiện | Hành động gợi ý |
| --- | --- | --- |
| `OK` | RPC hoàn tất thành công | Kiểm tra tiếp kết quả nghiệp vụ |
| `INVALID_ARGUMENT` | SKU/quantity không hợp lệ | Sửa input, không retry mù |
| `NOT_FOUND` | SKU không tồn tại | Xử lý khác `available=false` |
| `FAILED_PRECONDITION` | Trạng thái không cho phép thao tác | Đọc/cập nhật trạng thái nghiệp vụ |
| `ALREADY_EXISTS` | Tài nguyên đã tồn tại | Kiểm tra conflict và idempotency |
| `UNAUTHENTICATED` | Chưa có hoặc sai credentials | Xử lý xác thực |
| `PERMISSION_DENIED` | Client không có quyền | Xử lý phân quyền |
| `RESOURCE_EXHAUSTED` | Quota/công suất hết | Backoff, giới hạn concurrency |
| `UNAVAILABLE` | Kết nối hoặc service không sẵn sàng | Retry có kiểm soát nếu operation an toàn |
| `DEADLINE_EXCEEDED` | Hết hạn chờ | Kết quả có thể chưa biết; kiểm tra idempotency |
| `INTERNAL` | Lỗi server ngoài dự kiến | Ghi trace, điều tra; che chi tiết nhạy cảm |

### Deadline exceeded không có nghĩa server đã rollback

Giả sử client gọi `ReserveStock`, server commit SQL, nhưng response bị mất khi deadline hết hạn. Client thấy `DEADLINE_EXCEEDED` dù tồn kho **đã bị trừ**. Nếu client gửi lại một request tạo mới không có khóa idempotency, kho có thể bị trừ lần thứ hai. Do đó chỉ retry theo status code là chưa đủ; cần cả ngữ nghĩa business.

Mẫu thiết kế cho RPC ghi dữ liệu:

1. Client sinh `requestId` ổn định cho một thao tác và dùng lại cùng ID trên mỗi lần retry.
2. Server lưu `(callerIdentity, requestId)` vào bảng idempotency có unique constraint, cùng transaction cập nhật dữ liệu nghiệp vụ.
3. Request đã xử lý thành công trả lại kết quả đã ghi nhận; request đang xử lý có trạng thái nhất quán theo hợp đồng.
4. Retry có giới hạn, backoff/jitter và không vượt deadline tổng; log lại kết quả và mã idempotency.

Nếu nghiệp vụ vừa commit database vừa phát sự kiện JMS/Kafka, gRPC không tự làm hai thao tác đó atomic. Cần cơ chế như **transactional outbox**, hoặc kiến trúc giao dịch phân tán được lựa chọn và kiểm thử rõ ràng. Việc RPC thành công không chứng minh message tiếp theo đã được broker lưu.

### Cancellation và retry storm

Khi caller hủy RPC, server có thể nhận tín hiệu cancellation, nhưng cancellation không hoàn nguyên mọi side effect. Tác vụ dài cần kiểm tra cancellation và ngừng xử lý không còn cần thiết khi có thể. Thực thi retry phải có budget; nhiều upstream đồng thời retry khi service quá tải có thể làm hệ thống sụp nhanh hơn. Giới hạn số lần thử, tốc độ gửi, số RPC đồng thời và có circuit breaker/bulkhead khi phù hợp.

## 8. Streaming, backpressure và resume

gRPC streaming giúp server/client trao đổi nhiều message trong một RPC. Nhưng nó đòi hỏi quản lý:

- Thời gian tồn tại của stream, reconnect và idle timeout qua proxy/mesh.
- Flow control và backpressure khi sender nhanh hơn receiver; `ServerCallStreamObserver` có API quan sát readiness/cancellation.
- Executor, thread safety và context khi xử lý bất đồng bộ.
- Giới hạn kích thước message, bộ đệm, số stream đồng thời và keepalive.
- Trình tự, duplicate và resume token nếu người nhận không thể bỏ lỡ dữ liệu.

Ví dụ hợp đồng streaming:

~~~proto
service InventoryUpdates {
  rpc WatchStock(WatchStockRequest) returns (stream StockChange);
}

message WatchStockRequest {
  string sku = 1;
  int64 after_version = 2;
}

message StockChange {
  string sku = 1;
  int64 version = 2;
  int32 available_quantity = 3;
}
~~~

Trường `after_version` chỉ phát huy tác dụng nếu server **thật sự** có bảng thay đổi/outbox/event log để truy xuất từ một version và xử lý gap/retention. Một field proto không tự tạo khả năng replay. Nếu cần lưu hàng triệu sự kiện hoặc đọc lịch sử theo offset, một event broker/log có khả năng lưu trữ thường phù hợp hơn duy trì gRPC stream làm nguồn sự thật duy nhất.

## 9. Health, tracing, metrics và vận hành

Spring Boot Actuator có thể hiển thị trạng thái ứng dụng/JVM trên web port, nhưng HTTP health trên `8080` không tự chứng minh gRPC server ở `9090` đã start và đăng ký service. Có thể triển khai **gRPC Health Checking Protocol** (`grpc.health.v1.Health`) thông qua các dịch vụ hỗ trợ của grpc-java. Readiness nên phản ánh server sẵn sàng nhận RPC và những phụ thuộc thiết yếu; khi shutdown cần ngừng route traffic mới trước khi chấm dứt các lời gọi còn chạy.

**Server reflection** hỗ trợ tool như `grpcurl` khám phá descriptor khi không mang file proto. Chỉ bật ở vùng mạng và môi trường được phép; reflection có thể làm lộ danh sách service/method. Khi tắt reflection, vẫn có thể thử nghiệm bằng `.proto` hoặc descriptor set đã build.

Nên theo dõi tối thiểu:

| Tín hiệu | Giá trị để ra quyết định |
| --- | --- |
| Số RPC theo full method và status | Phát hiện lỗi tập trung |
| Latency histogram, p95/p99 | Kiểm tra SLA/tail latency |
| `DEADLINE_EXCEEDED`, cancellation | Phát hiện quá chậm hoặc client bỏ cuộc |
| Active RPC/stream, payload bytes | Phát hiện nghẽn tài nguyên |
| Retry count và tỷ lệ lỗi | Cảnh báo retry storm |
| Channel connectivity/TLS lỗi | Phân biệt DNS, mạng, certificate |
| Trace span giữa services | Theo dõi request xuyên gateway, gRPC, DB |
| Idempotency hits và business failures | Phân biệt vận chuyển RPC với hiệu quả nghiệp vụ |

Micrometer/OpenTelemetry có thư viện instrumentation tương ứng; cần kiểm tra phiên bản và cách kết nối vào grpc-java/starter đang dùng. Spring Boot web metrics không mặc nhiên bao phủ mọi gRPC call. Interceptor server/client nên truyền trace context trong metadata; log method, status, latency, `requestId`, `traceId` thay vì ghi toàn bộ payload hay token.

## 10. Kiểm thử gRPC cả logic lẫn transport

### 10.1. In-process test

Có thể dùng `grpc-inprocess` để test mapping request/response mà không cần mở TCP. Ví dụ JUnit 5 + Mockito:

~~~java
import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.*;

class InventoryGrpcEndpointTest {

    @Test
    void returnsAvailableStock() throws Exception {
        var inventory = mock(InventoryApplicationService.class);
        when(inventory.check("SKU-1", 2))
                .thenReturn(new InventorySnapshot(true, 13L, "WH-1"));

        String name = InProcessServerBuilder.generateName();
        var server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new InventoryGrpcEndpoint(inventory))
                .build()
                .start();
        var channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            var stub = InventoryServiceGrpc.newBlockingStub(channel);
            var request = CheckAvailabilityRequest.newBuilder()
                    .setSku("SKU-1")
                    .setRequestedQuantity(2)
                    .build();

            var response = stub.checkAvailability(request);

            assertTrue(response.getAvailable());
            verify(inventory).check("SKU-1", 2);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Ví dụ dùng các interface/record đã khai báo ở mục 4 và cần test dependencies JUnit, Mockito, `grpc-inprocess`. `directExecutor()` hữu ích cho test nhỏ nhưng không phải cấu hình production cho handler có thể blocking.

### 10.2. Tích hợp thực qua HTTP/2

In-process test không chứng minh TLS, HTTP/2, DNS, ingress, proxy hoặc load balancing hoạt động. Nên có các kịch bản:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Server mở gRPC port thực | Gọi unary qua TCP/HTTP2, không chỉ kiểm tra Spring context |
| Input sai | `INVALID_ARGUMENT`, không ghi DB |
| SKU không có | `NOT_FOUND`, tách khỏi kết quả hết hàng |
| Deadline ngắn | Caller nhận `DEADLINE_EXCEEDED`; server xử lý cancellation |
| Wrong CA/hostname | TLS handshake bị từ chối an toàn |
| Gateway/Ingress | gRPC route và streaming chạy đúng, không bị cắt kết nối ngoài ý muốn |
| Version contract khác nhau | Client cũ + server mới và ngược lại theo ma trận hỗ trợ |
| Gửi lại `requestId` | Side effect ghi chỉ xảy ra một lần |
| Pod dừng giữa RPC | Readiness/graceful stop hoạt động theo chính sách |
| Hai hoặc nhiều replica | Request được phân phối và failover như thiết kế |
| Monitoring | Status, latency và trace ID hiển thị đúng |

Khi chọn starter, kiểm thử thêm điều kiện server được tự đăng ký hay không, binding property, interceptor order và cleanup resource của starter. Dù unit test pass, vẫn cần kiểm thử mạng thực với certificate và policy của môi trường deploy.

## 11. Chọn gRPC, REST hoặc messaging

| Tình huống | Công nghệ thường hợp lý | Phần cần thiết kế bổ sung |
| --- | --- | --- |
| Dịch vụ nội bộ cần RPC đồng bộ và hợp đồng typed | **gRPC/protobuf** | Stub, channel, deadline, TLS, observability |
| API công khai/browser dễ thử và dễ cache | **HTTP REST/JSON** | Contract, auth, status, retry, caching |
| Công việc cần lưu chờ worker offline | **JMS queue hoặc broker phù hợp** | Ack, redelivery, DLQ, idempotency |
| Một sự kiện gửi đến nhiều nhóm nghiệp vụ | **Topic/event bus** | Subscription, retention, schema/version |
| Stream trạng thái trực tiếp | **gRPC streaming** nếu client/proxy hỗ trợ | Reconnect, flow control, resume |
| Lưu/phát lại lịch sử nhiều tháng | **Event log/store chuyên dụng** | Offset, retention, replay và schema migration |

Một kiến trúc có thể kết hợp: `checkout-service` gọi gRPC `inventory-service` để đọc tồn kho đồng bộ, sau đó ghi đơn hàng và outbox trong một database transaction để phát `OrderPlaced` qua broker. Mỗi công nghệ đảm nhận đúng trách nhiệm mà nó được thiết kế.

### Checklist trước khi triển khai

1. Chốt hợp đồng `.proto`, quy tắc field number, version và compatibility.
2. Quản lý grpc-java BOM, protobuf runtime, protoc và generator nhất quán; sinh mã trong CI.
3. Chọn starter tương thích hoặc tự tạo server bean, service registration, lifecycle, ManagedChannel và stub.
4. Cấu hình cổng, DNS/resolver, load balancing, proxy/ingress, HTTP/2 và giới hạn tài nguyên.
5. Bật TLS/mTLS đúng ranh giới, xác thực/phân quyền bằng interceptor, quản lý secret/certificate.
6. Thiết kế deadline, cancellation, retry/backoff và idempotency theo method.
7. Phân biệt transaction SQL, RPC và việc gửi message; dùng outbox khi cần đồng bộ bền vững.
8. Thêm health/readiness, metrics, tracing, log bảo mật và graceful shutdown.
9. Kiểm thử contract, in-process mapping và tích hợp mạng/TLS/scale trước khi phát hành.

**Ghi nhớ:** protobuf mô tả hợp đồng và dữ liệu; gRPC cung cấp lời gọi từ xa/streaming; Spring Boot quản lý ứng dụng. Phần build, registration, server/channel lifecycle, TLS, discovery, deadline, retry, health và quan sát là trách nhiệm tích hợp phải được cấu hình và kiểm thử rõ ràng. gRPC giúp giao tiếp dịch vụ có cấu trúc, nhưng không tự thay thế hệ thống message bền vững hay giao dịch dữ liệu nghiệp vụ.

