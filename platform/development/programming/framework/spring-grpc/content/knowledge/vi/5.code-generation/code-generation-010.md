# Không sửa tay mã được sinh trong Spring gRPC

Trong **Spring gRPC**, các lớp như `OrderRequest`, `OrderReply` và `OrderServiceGrpc` thường được tạo từ hợp đồng Protocol Buffers bằng `protoc` và plugin gRPC Java. Những tệp này là **generated source**: chúng phản ánh schema và phiên bản generator tại thời điểm build. Vì vậy, sửa trực tiếp generated Java không phải cách mở rộng ứng dụng an toàn. Lần sinh mã tiếp theo có thể ghi đè thay đổi, còn nếu thay đổi được giữ lại ngoài ý muốn, client và server có thể dùng hai phiên bản API khác nhau.

Quy tắc làm việc là: **sửa nguồn tạo ra mã, hoặc mở rộng ở lớp ứng dụng; không vá trực tiếp kết quả generator**. Với gRPC Java, nguồn tạo ra message/service API là tệp `.proto` và cấu hình generator. Nghiệp vụ thuộc service implementation, client facade, mapper, validator và interceptor do ứng dụng quản lý.

Bài học tập trung vào lý do không sửa tay generated code, cách tìm đúng nơi để thay đổi, cách xử lý trường hợp generator thiếu khả năng cần thiết và cách kiểm tra sau khi tái sinh.

## 1. Vì sao không sửa trực tiếp generated Java?

Giả sử `StockReply.java` được sinh từ:

```proto
syntax = "proto3";

package learning.stock.v1;

option java_package = "vn.example.stock.v1";
option java_multiple_files = true;

message StockReply {
  string sku = 1;
  int64 available = 2;
}
```

Một developer mở `build/generated/source/proto/main/java/vn/example/stock/v1/StockReply.java` và thêm phương thức:

```java
// Không làm theo cách này: đây là generated source.
public boolean isOutOfStock() {
    return getAvailable() == 0;
}
```

Thay đổi có thể hoạt động tạm thời, nhưng khi `generateProto` chạy lại, generator tạo lại `StockReply.java` từ `stock.proto` và phương thức vừa thêm sẽ biến mất. Nếu build không chạy generation vì output đang được xem là up-to-date, thay đổi thủ công có thể còn tồn tại trên máy developer nhưng không xuất hiện trên CI hoặc máy đồng nghiệp.

| Rủi ro | Hệ quả |
| --- | --- |
| Generation ghi đè file | Logic thêm thủ công bị mất |
| Máy local giữ file đã vá, CI sinh mới | “Works on my machine”; build hoặc test khác nhau |
| Commit generated file đã sửa | Khó phân biệt thay đổi schema với thay đổi thủ công |
| Nâng generator | Bản vá không còn áp dụng được hoặc xung đột với output mới |
| Sửa một phía client/server | Các bên có thể biên dịch với API khác nhau |
| Chèn nghiệp vụ vào message class | Generated model bị gắn với quy tắc của một ứng dụng cụ thể |

Generated source được tạo lại có chủ đích. Hãy coi nó là **đầu ra có thể tái sinh**, tương tự file build output, dù bạn có thể đọc để hiểu API được sinh.

## 2. Xác định đúng nguồn cần sửa

Trước khi mở generated file để thay đổi, hãy xác định mục tiêu thực sự:

| Bạn muốn thay đổi | Nơi nên sửa |
| --- | --- |
| Thêm, bỏ hoặc đổi field của message | Tệp `.proto` |
| Đổi kiểu RPC hoặc tên service/method | Phần `service`/`rpc` trong `.proto` |
| Đổi package Java, outer class hoặc cách sinh nhiều file | Các `option java_*` trong schema |
| Thay đổi logic xử lý request | Lớp server implementation kế thừa generated server base |
| Thêm validation nghiệp vụ | Validator hoặc application service |
| Chuyển đổi protobuf message sang domain model | Mapper/adapter do ứng dụng viết |
| Thêm header, token, trace ID | Client/server interceptor hoặc call credentials |
| Đổi cách gọi stub cho phù hợp API nội bộ | Client facade/wrapper |
| Thay đổi định dạng hoặc cấu trúc mã sinh | Cấu hình generator hoặc plugin codegen riêng |

Ví dụ, nếu cần thêm field `warehouse_id` vào response, sửa schema:

```proto
message StockReply {
  string sku = 1;
  int64 available = 2;
  int64 version = 3;
  string warehouse_id = 4;
}
```

Sau đó chạy generation và cập nhật mã ứng dụng sử dụng field mới. Không thêm `getWarehouseId()` trực tiếp vào `StockReply.java` vì API đó phải được sinh từ schema.

Khi thay đổi field đã phát hành, vẫn phải tuân thủ quy tắc tương thích Protocol Buffers: không tái sử dụng field number đã xóa; cân nhắc `reserved`; đánh giá tác động của kiểu dữ liệu và presence. “Sửa đúng file .proto” không đồng nghĩa mọi thay đổi schema đều an toàn với client cũ.

## 3. Generated message là dữ liệu; nghiệp vụ đặt ở lớp ứng dụng

Message class protobuf được tối ưu cho biểu diễn dữ liệu, builder, parse và serialization. Nó không nên trở thành nơi chứa quy tắc nghiệp vụ của một dịch vụ.

Ví dụ, thay vì thêm `isOutOfStock()` vào generated class, tạo một policy hoặc mapper trong source code ứng dụng:

```java
package vn.example.stock;

import vn.example.stock.v1.StockReply;

public final class StockPolicy {
    private StockPolicy() {}

    public static boolean isOutOfStock(StockReply reply) {
        return reply.getAvailable() <= 0;
    }
}
```

Sử dụng:

```java
if (StockPolicy.isOutOfStock(reply)) {
    // Áp dụng quy tắc nghiệp vụ của ứng dụng.
}
```

Cách này có một lợi ích quan trọng: cùng một generated message có thể được dùng bởi nhiều client mà không kéo theo policy riêng của một ứng dụng. Policy cũng có thể được unit test độc lập với code generation.

Nếu ứng dụng có domain model riêng, không nên để protobuf message lan sâu vào toàn bộ domain chỉ vì class đó có sẵn. Dùng mapper để chuyển đổi tại ranh giới RPC:

```java
public record Stock(String sku, long available) {}

public final class StockMapper {
    private StockMapper() {}

    public static Stock toDomain(StockReply reply) {
        return new Stock(reply.getSku(), reply.getAvailable());
    }
}
```

`StockReply` là kiểu giao tiếp; `Stock` là kiểu domain do ứng dụng quản lý. Nếu schema đổi, mapper là một điểm tập trung để xử lý thay đổi thay vì phải sửa nhiều nơi.

## 4. Mở rộng server qua generated server base

Plugin gRPC Java sinh server base class, ví dụ `StockServiceGrpc.StockServiceImplBase`. Đây là **điểm mở rộng được thiết kế sẵn**: ứng dụng kế thừa và override các RPC cần triển khai.

```java
package vn.example.stock;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

@Service
public class StockServiceImpl
        extends StockServiceGrpc.StockServiceImplBase {

    private final StockApplicationService applicationService;

    public StockServiceImpl(StockApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        if (request.getSku().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("sku không được rỗng")
                    .asRuntimeException());
            return;
        }

        StockReply reply = applicationService.findStock(request.getSku());
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

`StockServiceImpl` là file do nhóm phát triển sở hữu; `StockServiceImplBase` là generated code. Khi generator chạy lại, lớp triển khai vẫn được giữ nguyên vì nó nằm trong `src/main/java`.

Với Spring gRPC, cách đăng ký service bean phụ thuộc starter/phiên bản tích hợp. Hãy dùng cơ chế đăng ký `BindableService` mà dự án hỗ trợ. Không thêm code đăng ký hoặc logic nghiệp vụ vào generated `*Grpc.java`.

## 5. Mở rộng client qua facade thay vì sửa stub

Generated client stub cung cấp API giao tiếp gRPC. Ứng dụng có thể bọc stub trong một facade để tập trung deadline mặc định, mapping lỗi và chuyển đổi kiểu:

```java
package vn.example.stock;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

public class StockGateway {
    private final StockServiceGrpc.StockServiceBlockingStub stub;

    public StockGateway(StockServiceGrpc.StockServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Stock find(String sku) {
        try {
            StockReply reply = stub
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getStock(StockRequest.newBuilder()
                            .setSku(sku)
                            .build());

            return StockMapper.toDomain(reply);
        } catch (StatusRuntimeException error) {
            if (error.getStatus().getCode() == Status.Code.NOT_FOUND) {
                return null;
            }
            throw error;
        }
    }
}
```

Facade là mã ứng dụng, có thể được thay đổi và kiểm thử độc lập. Stub vẫn là generated API và được tạo từ channel do Spring hoặc cấu hình grpc-java quản lý.

Không cần tạo một subclass của generated message chỉ để bổ sung helper method. Generated message thường được sinh theo mô hình bất biến và không được thiết kế làm base class mở rộng nghiệp vụ. Dùng facade, mapper hoặc utility là ranh giới rõ ràng hơn.

## 6. Nếu muốn thay đổi cách generated code được tạo?

Có trường hợp nhóm thực sự cần output khác với mặc định, ví dụ muốn sinh annotation nội bộ, wrapper hoặc tài liệu API. Khi đó thay đổi phải nằm trong **quy trình code generation**:

1. Kiểm tra generator options và cấu hình mà plugin hiện tại hỗ trợ.
2. Nếu cần hành vi riêng, cân nhắc viết hoặc sử dụng một `protoc plugin` bổ sung.
3. Để plugin sinh file riêng hoặc phần mở rộng riêng có namespace rõ ràng.
4. Đưa plugin, version và options vào build tool để mọi máy chạy cùng một quy trình.
5. Kiểm thử output từ trạng thái sạch và xác minh generated source không phụ thuộc workspace.

Ví dụ về nguyên tắc: plugin riêng có thể sinh `StockReplyMapper.java` hoặc `StockValidationMetadata.java` từ descriptor, trong khi `StockReply.java` vẫn do Java protobuf generator tạo. Tách output theo trách nhiệm giúp tránh hai generator cùng ghi vào một file.

Không nên sửa template/binary của generator trong cache Gradle/Maven hoặc trong thư mục dependency đã tải. Thay đổi đó không được quản lý bởi source control, dễ biến mất khi cache bị xóa và không tái tạo được trên CI. Nếu cần sửa generator upstream, hãy nâng cấp phiên bản đã sửa hoặc duy trì fork/plugin riêng có version rõ ràng.

## 7. Khi generated code có lỗi hoặc thiếu tính năng

Nếu output có lỗi, trước hết xác định nguồn:

- **Schema sai:** sửa `.proto` và sinh lại.
- **Generator bug:** xác minh bằng schema tối thiểu, kiểm tra phiên bản và issue/release của generator; nâng cấp hoặc báo lỗi upstream.
- **Generator thiếu tính năng:** tìm option/plugin phù hợp hoặc tạo plugin riêng.
- **Runtime incompatibility:** đồng bộ phiên bản `protoc`, `protoc-gen-grpc-java` và protobuf/grpc-java runtime.
- **Ứng dụng cần helper/validation:** viết ở lớp ứng dụng, không thêm vào generated class.

Trong tình huống khẩn cấp, một bản vá hậu xử lý output có thể được cân nhắc như biện pháp tạm thời, nhưng nó phải được tự động hóa, version control, chạy sau generation một cách xác định và có test kiểm tra. Bản vá thủ công trong thư mục output không phải giải pháp có thể bàn giao.

Nếu lỗi thuộc generated code, tạo một schema tối thiểu tái hiện vấn đề và lưu lại:
- Phiên bản protoc và gRPC plugin.
- Các options và import roots.
- Generated output liên quan.
- Lỗi compile/runtime chính xác.
- Kết quả khi thử với phiên bản generator khác.

Bộ thông tin này giúp phân biệt lỗi generator với lỗi do schema, dependency hoặc cách dùng API.

## 8. Quy trình tái sinh an toàn sau khi đổi schema

Sau khi chỉnh `.proto`, thực hiện một vòng kiểm tra có thể lặp lại:

1. Review thay đổi schema: field number, kiểu dữ liệu, presence, tên RPC và tương thích.
2. Chạy generation từ build tool đã pin version.
3. Xem diff generated source để xác nhận thay đổi đúng với schema.
4. Biên dịch main và test source sets.
5. Cập nhật server implementation, client facade, mapper và validator nếu API thay đổi.
6. Chạy unit test và integration test gọi RPC thật hoặc in-process.
7. Kiểm tra client/server version compatibility nếu hai bên phát hành độc lập.

Ví dụ Gradle:

```bash
./gradlew clean generateProto compileJava compileTestJava test
```

Ví dụ Maven:

```bash
mvn clean generate-sources compile test
```

Các lệnh trên giả định dự án đã cấu hình đúng protobuf plugin, gRPC plugin và test lifecycle. Không cần commit generated output trong một dự án có quy ước sinh mã tại build time; nếu tổ chức phát hành contract JAR chứa generated classes, hãy tạo artifact từ pipeline chuẩn.

## 9. Kiểm thử để phát hiện sửa tay bị mất

Một test hữu ích là xác nhận logic mở rộng nằm trong mã ứng dụng và vẫn hoạt động sau khi generated code được tạo lại.

Ví dụ unit test cho policy:

```java
import org.junit.jupiter.api.Test;
import vn.example.stock.StockPolicy;
import vn.example.stock.v1.StockReply;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StockPolicyTest {

    @Test
    void determinesWhetherStockIsEmpty() {
        StockReply empty = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(0)
                .build();

        StockReply available = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(4)
                .build();

        assertTrue(StockPolicy.isOutOfStock(empty));
        assertFalse(StockPolicy.isOutOfStock(available));
    }
}
```

Sau đó chạy generation sạch và test:

```bash
./gradlew clean generateProto test
```

Nếu policy vẫn compile và test pass, logic thuộc source do ứng dụng quản lý, không phụ thuộc bản vá trong generated output.

Đối với server implementation, integration test nên gọi generated stub để xác nhận method được bind và status đúng:

```java
@Test
void blankSkuReturnsInvalidArgument() {
    var error = org.junit.jupiter.api.Assertions.assertThrows(
            io.grpc.StatusRuntimeException.class,
            () -> blockingStub.getStock(
                    StockRequest.newBuilder().setSku("").build()));

    org.junit.jupiter.api.Assertions.assertEquals(
            io.grpc.Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
}
```

Test này giả định `blockingStub` được cấu hình tới test server và `StockServiceImpl` trả `INVALID_ARGUMENT` cho SKU rỗng như ví dụ. Nó kiểm tra hành vi RPC; test generation riêng vẫn cần bảo đảm source được tái sinh từ `.proto`.

## 10. Những dấu hiệu cho thấy generated code đã bị sửa tay

| Dấu hiệu | Cần kiểm tra |
| --- | --- |
| Generated file có logic nghiệp vụ hoặc gọi repository | Logic bị đặt nhầm vào generated class |
| Diff generated file không tương ứng thay đổi schema/toolchain | Có chỉnh sửa thủ công hoặc output từ generator khác |
| Sau `clean generateProto` helper method biến mất | Helper được thêm trực tiếp vào generated source |
| Máy A có method nhưng CI không có | Local generated output chưa được tái tạo từ source |
| Nâng plugin làm mất các đoạn code | Bản vá đang nằm trong output bị generator ghi đè |
| Client và server dùng generated JAR khác version | Contract artifact hoặc dependency chưa được đồng bộ |

Khi phát hiện, so sánh generated output với kết quả tái sinh từ trạng thái sạch. Chuyển phần nghiệp vụ sang source do ứng dụng quản lý; chuyển thay đổi API về `.proto`; chuyển thay đổi cấu trúc generated output về cấu hình/plugin. Không giữ bản vá cũ chỉ vì nó đang làm build pass.

## 11. Bài tập thực hành

1. Thêm một helper method trực tiếp vào generated `StockReply.java` trong bản sao dự án. Chạy `clean generateProto` và quan sát helper biến mất.
2. Chuyển helper đó sang `StockPolicy` trong `src/main/java`; viết unit test và chạy lại sau generation.
3. Thêm field mới vào `stock.proto`, sinh lại và xác nhận generated API thay đổi; cập nhật mapper mà không sửa generated file.
4. Viết một `StockServiceImpl` kế thừa `StockServiceImplBase` và override unary RPC. Xác nhận implementation không bị ảnh hưởng khi generation chạy lại.
5. Tạo `StockGateway` bọc generated stub, áp deadline và chuyển status phù hợp; test facade độc lập.
6. Giả lập lỗi compile do lệch version runtime; xác định lỗi nằm ở generator hay dependency, không vá generated source.
7. Nếu cần helper được sinh tự động, thiết kế một plugin sinh file riêng `StockReplyMapper.java` và kiểm tra hai generator không ghi cùng output.
8. Chạy clean generation hai lần và so sánh generated directories; xác nhận mọi thay đổi đều truy nguyên được về schema hoặc toolchain.

### Ghi nhớ

**Generated source là kết quả của hợp đồng và generator, không phải nơi lưu logic ứng dụng.** Muốn đổi message hoặc RPC, sửa `.proto`; muốn đổi nghiệp vụ, viết service implementation, mapper, validator hoặc client facade; muốn đổi cách sinh, cấu hình generator hoặc dùng plugin riêng có version. Sau mỗi thay đổi, tái sinh từ build sạch, xem diff, biên dịch và chạy test. Quy tắc này giữ cho client/server Spring gRPC nhất quán và ngăn bản vá biến mất khi build lại.
