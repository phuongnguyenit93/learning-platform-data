# Kiểm tra mã sinh trong build cho Spring gRPC

Trong **SPRING_GRPC**, các message class và service stub được tạo từ hợp đồng Protocol Buffers trước khi Java compiler biên dịch ứng dụng. Một build thành công cần chứng minh nhiều hơn việc thư mục generated có file: **đúng schema đã được xử lý, đủ cả message và gRPC API, compiler nhận các source đó, và API sinh ra hoạt động với runtime**.

Bài này tập trung vào cách kiểm tra generated code ngay trong quy trình build Gradle/Maven: xác minh output, kiểm tra descriptor và serialization, chạy compile/test, thử gọi stub tới server, nhận diện output cũ và đưa các kiểm tra vào CI. Mục tiêu là phát hiện lỗi code generation trước khi đóng gói hoặc triển khai dịch vụ.

## 1. Kiểm tra ở những tầng nào?

Một quy trình kiểm chứng hợp lý có các tầng sau:

| Tầng | Điều cần xác nhận | Dấu hiệu đạt |
| --- | --- | --- |
| Generation | Build đã gọi đúng protoc và gRPC plugin | Task/goal chạy thành công, output được tạo |
| Output | Có message, enum và service API mong đợi | Các generated classes cần thiết tồn tại |
| Compilation | Generated source thuộc đúng source set và compile classpath | `compileJava`/Maven `compile` thành công |
| Descriptor/schema | Generated API phản ánh đúng service, method, field number và RPC type | Descriptor assertions pass |
| Runtime call | Stub và server base hoạt động cùng grpc-java runtime | In-process hoặc integration RPC test pass |
| Application wiring | Spring đăng ký service và cấu hình client/server đúng | Spring integration test pass |
| Clean build | Kết quả không phụ thuộc output cũ trên máy developer | Build từ `clean`/checkout sạch pass |

Không phải mỗi tầng đều cần một task riêng. Một test compile có thể kiểm tra source root; descriptor test xác nhận chi tiết schema; in-process test kiểm tra generated stub và dispatch. Phân chia tầng giúp xác định lỗi nằm ở generation, Java compile hay runtime.

## 2. Hợp đồng mẫu để kiểm tra

Dùng schema nhỏ cho dịch vụ tồn kho:

```proto
syntax = "proto3";

package learning.stock.v1;

option java_package = "vn.example.stock.v1";
option java_multiple_files = true;

message StockRequest {
  string sku = 1;
}

message StockReply {
  string sku = 1;
  int64 available = 2;
}

service StockService {
  rpc GetStock(StockRequest) returns (StockReply);
  rpc WatchStock(StockRequest) returns (stream StockReply);
}
```

Với hợp đồng này, build cần tạo ít nhất:

- `StockRequest` và `StockReply` từ Java protobuf generator.
- `StockServiceGrpc` từ plugin gRPC Java.
- Các descriptor cho message, service và từng RPC.

Ví dụ output phổ biến với Gradle protobuf plugin:

```text
build/generated/source/proto/main/
├── java/vn/example/stock/v1/
│   ├── StockRequest.java
│   └── StockReply.java
└── grpc/vn/example/stock/v1/
    └── StockServiceGrpc.java
```

Với protobuf Maven plugin, output thường nằm dưới `target/generated-sources/protobuf/java` và `target/generated-sources/protobuf/grpc-java`. Đường dẫn chính xác phụ thuộc plugin và cấu hình; hãy dùng output thực tế của build hiện tại.

## 3. Kiểm tra task/goal generation đã chạy

### Gradle

Trong cấu hình dùng protobuf Gradle plugin, các task thường gặp là:

- `generateProto`: sinh mã từ proto của main source set.
- `generateTestProto`: sinh mã từ proto của test source set nếu có.
- `compileJava`: biên dịch mã ứng dụng cùng generated source của main.
- `compileTestJava`: biên dịch test và generated source dành cho test.

Chạy:

```bash
./gradlew tasks --all
./gradlew clean generateProto
./gradlew compileJava
./gradlew compileTestJava
```

`tasks --all` giúp xác nhận tên task trong project; source set tùy chỉnh hoặc plugin version có thể tạo task khác. Khi plugin đã nối task dependency đúng, chạy `compileJava` thường tự kích hoạt generation trước compiler. `clean` hữu ích khi xác minh output từ đầu, còn vòng build bình thường có thể dựa vào incremental/up-to-date checks.

Để xem task nào chạy và output được xử lý ra sao:

```bash
./gradlew generateProto --info
./gradlew compileJava --dry-run
```

Nếu generation không xuất hiện trong task graph, kiểm tra plugin protobuf, proto source set và cấu hình task. Đừng tự thêm generated directory vào Java source set trước khi xác định plugin đã đăng ký nó hay chưa.

### Maven

Với `protobuf-maven-plugin`, goals sinh message và gRPC stub thường được bind ở phase `generate-sources`:

- `protobuf:compile`: sinh message Java.
- `protobuf:compile-custom`: gọi plugin gRPC Java để sinh service API.

Chạy:

```bash
mvn clean generate-sources
mvn compile
mvn test
```

`mvn compile` và các phase sau nó đi qua `generate-sources`; nếu execution đã bind đúng, generation được gọi tự động. Với Maven, kiểm tra log plugin để biết protoc và plugin binary nào thực sự được chạy.

## 4. Xác nhận generated files có mặt và đúng source set

Chỉ kiểm tra một file tồn tại là chưa đủ. Cần xác nhận **đủ các loại output** và chúng thuộc đúng source set.

Checklist cho main:

- Message class từ Java generator tồn tại.
- Service class `StockServiceGrpc` tồn tại khi schema có `service`.
- File nằm trong generated root của `main`, không phải chỉ ở `test`.
- Java compiler nhìn thấy cả hai nhóm source.
- Không có bản class trùng tên được sinh từ một schema copy khác.

Có thể dùng lệnh liệt kê file sau generation:

```powershell
Get-ChildItem -Recurse build/generated/source/proto/main |
    Select-Object -ExpandProperty FullName
```

Trên shell Unix:

```bash
find build/generated/source/proto/main -type f
```

Đây là bước chẩn đoán output. Với CI, nên để test compile và descriptor test kiểm tra API thay vì chỉ phụ thuộc vào tên file trong một script.

Nếu có proto dành riêng cho test, kiểm tra `generateTestProto` và `compileTestJava` riêng. Test-only service không nên xuất hiện trong main artifact; ngược lại, message/service production phải được sinh từ main source set.

## 5. Kiểm tra descriptor và schema được sinh

Một test descriptor xác nhận generated API phản ánh đúng các khai báo quan trọng trong `.proto`. Test này bắt được trường hợp build vẫn tạo Java nhưng service/method/field bị đổi ngoài dự kiến.

Ví dụ JUnit 5:

```java
package vn.example.stock;

import io.grpc.MethodDescriptor;
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockServiceGrpc;

import static org.junit.jupiter.api.Assertions.*;

class GeneratedSchemaTest {

    @Test
    void generatedMessageContainsExpectedFieldNumbers() {
        var descriptor = StockReply.getDescriptor();

        assertEquals(
                1,
                descriptor.findFieldByName("sku").getNumber());

        assertEquals(
                2,
                descriptor.findFieldByName("available").getNumber());
    }

    @Test
    void generatedServiceContainsExpectedRpcMethods() {
        assertEquals(
                "learning.stock.v1.StockService",
                StockServiceGrpc.SERVICE_NAME);

        assertEquals(
                MethodDescriptor.MethodType.UNARY,
                StockServiceGrpc.getGetStockMethod().getType());

        assertEquals(
                MethodDescriptor.MethodType.SERVER_STREAMING,
                StockServiceGrpc.getWatchStockMethod().getType());
    }
}
```

Tên accessor descriptor như `getGetStockMethod()` và `getWatchStockMethod()` là API thường được gRPC Java generator tạo; nếu phiên bản generator của dự án khác, đối chiếu generated class thực tế và điều chỉnh test theo public API đó.

Descriptor test có giá trị vì nó kiểm tra **field number** và **RPC cardinality**, không chỉ tên Java class. Khi schema được đổi có chủ đích, cập nhật assertion cùng thay đổi contract để diff thể hiện rõ điều gì đã đổi.

## 6. Kiểm tra message serialization

Generated message phải có thể serialize và parse lại qua protobuf runtime. Đây là kiểm tra nhanh để phát hiện lỗi do runtime dependency, generated class hoặc schema.

```java
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GeneratedMessageTest {

    @Test
    void generatedMessageRoundTripsThroughProtobuf() throws Exception {
        StockReply original = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(17)
                .build();

        StockReply parsed = StockReply.parseFrom(original.toByteArray());

        assertEquals(original, parsed);
        assertEquals("BOOK-101", parsed.getSku());
        assertEquals(17, parsed.getAvailable());
    }
}
```

Test này xác nhận generated message và protobuf runtime phối hợp được ở đường serialize/parse cơ bản. Nó không chứng minh tương thích với mọi phiên bản client đã phát hành; kiểm thử compatibility cần dùng schema/artifact cũ và mới riêng.

## 7. Kiểm tra generated stub bằng in-process RPC

Compile thành công chưa chứng minh generated stub gọi được server. Một in-process test kiểm tra generated method descriptor, marshaller, server base và client stub mà không cần mở TCP port.

Trong test scope, thêm dependency `grpc-inprocess` cùng version line grpc-java mà ứng dụng đang dùng. Nếu đã dùng grpc BOM, để BOM quản lý version:

```groovy
dependencies {
    testImplementation 'io.grpc:grpc-inprocess'
}
```

Server implementation tối thiểu:

```java
import io.grpc.stub.StreamObserver;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

final class TestStockService
        extends StockServiceGrpc.StockServiceImplBase {

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        StockReply reply = StockReply.newBuilder()
                .setSku(request.getSku())
                .setAvailable(17)
                .build();

        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Test gọi generated blocking stub:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GeneratedStubTest {

    @Test
    void generatedStubInvokesGeneratedServerBase() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder
                .forName(serverName)
                .directExecutor()
                .addService(new TestStockService())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            StockReply reply = StockServiceGrpc
                    .newBlockingStub(channel)
                    .getStock(StockRequest.newBuilder()
                            .setSku("BOOK-101")
                            .build());

            assertEquals("BOOK-101", reply.getSku());
            assertEquals(17, reply.getAvailable());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

Test này kiểm tra gRPC Java dispatch qua in-process transport. Nó không kiểm tra Spring bean registration, TCP/HTTP2, TLS hoặc cấu hình production. Nếu ứng dụng dựa vào auto-configuration của Spring gRPC, cần thêm integration test khởi động application context và gọi service qua channel/port do ứng dụng cấu hình.

## 8. Phân biệt kiểm tra codegen với kiểm tra Spring wiring

| Test | Điều được kiểm tra | Điều chưa được chứng minh |
| --- | --- | --- |
| Descriptor test | Message field numbers, service name, RPC type | Server đã được Spring đăng ký |
| Serialization test | Message parse/serialize với protobuf runtime | Client/server tương thích qua network |
| In-process RPC | Generated stub, server base, marshaller và dispatch | TCP, TLS, Spring auto-configuration |
| Spring integration test | Bean registration, channel/server configuration, interceptor theo cấu hình test | Hành vi production dưới tải thực |
| End-to-end test | Client và server độc lập giao tiếp trong môi trường gần thực tế | Mọi tình huống vận hành và tải |

Không dùng in-process test làm bằng chứng TLS hoạt động; transport in-process không thiết lập TLS như kết nối mạng. Tương tự, descriptor test không xác nhận service bean đã được đăng ký với Spring.

## 9. Phát hiện generated output cũ

Một lỗi nguy hiểm là generated directory còn file từ lần sinh trước. Ví dụ một RPC đã bị xóa khỏi `.proto`, nhưng output cũ vẫn tồn tại vì build không được làm sạch đúng cách hoặc file được tạo thủ công.

Quy trình xác minh:

1. Xem schema hiện tại và danh sách generated files.
2. Chạy `clean` để loại output cũ.
3. Chạy generation lại từ đầu.
4. Kiểm tra file và method không còn xuất hiện nếu schema đã xóa.
5. Compile/test để phát hiện source còn tham chiếu API cũ.

Với Gradle:

```bash
./gradlew clean generateProto compileJava test
```

Với Maven:

```bash
mvn clean generate-sources compile test
```

Không tự xóa từng generated file để làm build pass; hãy xác định task output và lifecycle. `clean` là bước chẩn đoán hữu ích, còn build bình thường phải có input/output tracking chính xác để generation không bị bỏ qua sai.

## 10. Đưa kiểm tra vào CI

Một pipeline kiểm tra generated code nên thực hiện ít nhất:

1. Checkout schema và build configuration.
2. Dùng Gradle/Maven Wrapper và JDK đã thống nhất.
3. Chạy clean generation.
4. Compile main và test source sets.
5. Chạy descriptor/serialization tests.
6. Chạy in-process hoặc Spring integration RPC tests theo phạm vi.
7. Lưu log generation và dependency resolution khi thất bại.

Ví dụ Gradle:

```bash
./gradlew --no-daemon clean test
```

Ví dụ Maven:

```bash
./mvnw -B clean verify
```

Nếu `check`/`verify` chưa bao gồm integration test riêng, cần nối test task/profile đó vào CI. Không tuyên bố build đã kiểm tra Spring wiring nếu pipeline chỉ chạy compile và unit tests.

Khi generated sources không được commit, CI vẫn có thể kiểm tra đầy đủ vì chúng được tạo từ `.proto`. Nếu contract JAR được phát hành, hãy kiểm tra artifact được đóng gói chứa đúng generated API và version tương ứng với schema đã review.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không có message class | Java generator không chạy, proto root sai hoặc schema lỗi |
| Có message nhưng thiếu `*Grpc.java` | gRPC plugin chưa được áp dụng cho proto task/goal |
| File tồn tại nhưng `compileJava` không thấy | Generated source root chưa được đăng ký hoặc sai source set |
| Descriptor test báo sai method type | Schema cardinality thay đổi hoặc test đang dùng output/version cũ |
| Serialization test lỗi liên kết | Protobuf runtime không tương thích hoặc thiếu dependency |
| In-process RPC trả `UNIMPLEMENTED` | Test service chưa override đúng method hoặc gọi nhầm RPC |
| Spring integration test không tìm thấy service | Bean/service registration hoặc starter configuration sai |
| Local pass, CI fail | Output cũ, toolchain khác, import dependency thiếu hoặc môi trường không sạch |
| Test pass nhưng TLS fail ngoài môi trường | In-process test không kiểm tra network TLS; cần test transport thật |

Khi điều tra, giữ log task/goal, generated output và dependency graph. Xác định lỗi ở generation, source registration, compilation, runtime dispatch hay Spring wiring trước khi thay schema hoặc nâng version.

## 12. Bài tập thực hành

1. Chạy clean generation và xác nhận đủ `StockRequest`, `StockReply`, `StockServiceGrpc`.
2. Viết descriptor test xác nhận field number và RPC type.
3. Viết serialization round-trip test cho `StockReply`.
4. Viết in-process test gọi `GetStock` bằng generated blocking stub.
5. Xóa một RPC khỏi schema, clean generation và xác nhận method không còn trong generated API.
6. Đặt test-only proto trong test source set và xác nhận output không đi vào main artifact.
7. Chạy compile từ checkout sạch trên CI; xác nhận không cần generated source được commit.
8. Bổ sung Spring integration test để xác nhận service bean được đăng ký và client gọi được server đã cấu hình.
9. Phân biệt bằng chứng của descriptor, in-process, Spring integration và end-to-end tests trong báo cáo build.

### Ghi nhớ

**Kiểm tra mã sinh trong build phải xác nhận cả output lẫn khả năng sử dụng output.** Hãy kiểm tra task/goal generation, sự hiện diện của message và gRPC API, source set, Java compilation, descriptor, serialization và một RPC qua generated stub. Bổ sung Spring integration test khi cần xác nhận bean registration, channel, TLS hoặc interceptor. Clean build trong CI giúp loại phụ thuộc vào generated output cũ và chứng minh mã sinh có thể tái tạo từ hợp đồng.
