# Tách client adapter khỏi business code

Khi application service gọi trực tiếp generated gRPC stub, mã nghiệp vụ phải biết `HelloRequest`, `StatusRuntimeException`, deadline và các kiểu Protobuf. Điều đó khiến business code phụ thuộc vào hợp đồng truyền thông từ xa. Khi `.proto` đổi hoặc ứng dụng chuyển sang một dịch vụ khác, nhiều lớp nghiệp vụ có thể phải sửa theo.

Một **client adapter** tạo ranh giới giữa ứng dụng và gRPC: nó nhận một yêu cầu theo ngôn ngữ của ứng dụng, chuyển thành Protobuf, gọi generated stub, rồi chuyển response hoặc lỗi gRPC thành kết quả/exception mà application service hiểu. Business code chỉ phụ thuộc vào một interface do ứng dụng sở hữu. Cách tổ chức này thuộc kiến trúc ports and adapters (hexagonal architecture), phù hợp với Spring client trong mô-đun **SPRING_GRPC**: phát triển client/server từ hợp đồng Protocol Buffers và mã Java sinh ra, hỗ trợ unary/streaming RPC, metadata, deadline, status, interceptor, TLS, kiểm thử và giám sát.

## 1. Ranh giới giữa business code và gRPC

Một luồng gọi nên có dạng:

```mermaid
flowchart LR
    A[Application Service] --> B[InventoryPort]
    B --> C[GrpcInventoryAdapter]
    C --> D[Generated gRPC Stub]
    D --> E[ManagedChannel]
    E --> F[gRPC Server]
```

- **Port** là interface thuộc application/domain layer. Nó mô tả khả năng ứng dụng cần, bằng kiểu dữ liệu của chính ứng dụng.
- **Adapter** là phần triển khai port bằng một công nghệ cụ thể. Trong bài này, adapter dùng generated gRPC stub.
- **Business service** điều phối quy tắc nghiệp vụ thông qua port; nó không cần biết request/response Protobuf hay gRPC status.

Quy tắc phụ thuộc là: business code định nghĩa điều nó cần; adapter phụ thuộc vào business contract để thực hiện điều đó. Không để domain import package `io.grpc` hoặc package Java được sinh từ `.proto`.

## 2. Thiết kế port theo nhu cầu nghiệp vụ

Giả sử nghiệp vụ cần kiểm tra số lượng tồn kho theo SKU. Port nên mô tả kết quả mà ứng dụng cần, không sao chép nguyên cấu trúc của RPC:

```java
package com.example.inventory.application;

public interface InventoryPort {
    StockAvailability getAvailability(Sku sku);
}
```

Các kiểu dữ liệu đi cùng port được đặt ở những file riêng trong package application. `Sku.java`:

```java
package com.example.inventory.application;

public record Sku(String value) {
    public Sku {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("SKU không được rỗng");
        }
        value = value.trim();
    }
}
```

`StockAvailability.java`:

```java
package com.example.inventory.application;

public record StockAvailability(int availableUnits) {
    public StockAvailability {
        if (availableUnits < 0) {
            throw new IllegalArgumentException("Số lượng tồn không thể âm");
        }
    }
}
```

`InventoryPort` không trả `StockReply` và cũng không nhận `StockRequest`. Nếu gRPC server bổ sung field kỹ thuật, đổi package Protobuf hoặc thay transport, port vẫn có thể giữ nguyên miễn là ý nghĩa nghiệp vụ không đổi.

Port cần phản ánh đúng ngữ nghĩa của ứng dụng. Nếu nghiệp vụ cần kiểm tra tồn kho, `getAvailability` phù hợp hơn một interface tổng quát như `GrpcClient.call(byte[])`. Tránh tạo abstraction quá rộng khiến business service lại phải biết tên RPC, protobuf message hoặc mã status.

## 3. Adapter chuyển đổi giữa application model và Protobuf

Giả sử hợp đồng gRPC có RPC `GetStock`:

```protobuf
syntax = "proto3";

package inventory.v1;

option java_package = "com.example.contract.inventory";
option java_multiple_files = true;

service Inventory {
  rpc GetStock (StockRequest) returns (StockReply);
}

message StockRequest {
  string sku = 1;
}

message StockReply {
  int32 available_units = 1;
}
```

Sau khi chạy `protoc` và plugin `protoc-gen-grpc-java`, client có `InventoryGrpc`, `StockRequest` và `StockReply`. Các kiểu đó chỉ xuất hiện trong adapter:

```java
package com.example.inventory.infrastructure.grpc;

import com.example.contract.inventory.InventoryGrpc;
import com.example.contract.inventory.StockReply;
import com.example.contract.inventory.StockRequest;
import com.example.inventory.application.InventoryIntegrationException;
import com.example.inventory.application.InventoryItemNotFoundException;
import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import com.example.inventory.application.InventoryUnavailableException;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class GrpcInventoryAdapter implements InventoryPort {

    private final InventoryGrpc.InventoryBlockingStub stub;

    public GrpcInventoryAdapter(InventoryGrpc.InventoryBlockingStub stub) {
        this.stub = stub;
    }

    @Override
    public StockAvailability getAvailability(Sku sku) {
        StockRequest request = StockRequest.newBuilder()
                .setSku(sku.value())
                .build();

        try {
            StockReply reply = stub
                    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                    .getStock(request);

            return new StockAvailability(reply.getAvailableUnits());
        } catch (StatusRuntimeException failure) {
            throw mapFailure(failure);
        }
    }

    private RuntimeException mapFailure(StatusRuntimeException failure) {
        Status.Code code = failure.getStatus().getCode();

        return switch (code) {
            case NOT_FOUND -> new InventoryItemNotFoundException(failure);
            case UNAVAILABLE, DEADLINE_EXCEEDED ->
                    new InventoryUnavailableException(failure);
            default -> new InventoryIntegrationException(failure);
        };
    }
}
```

Các exception dưới đây là những file riêng trong package application. `InventoryItemNotFoundException.java`:

```java
package com.example.inventory.application;

public class InventoryItemNotFoundException extends RuntimeException {
    public InventoryItemNotFoundException(Throwable cause) {
        super("Không tìm thấy mặt hàng trong hệ thống tồn kho", cause);
    }
}
```

`InventoryUnavailableException.java`:

```java
package com.example.inventory.application;

public class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(Throwable cause) {
        super("Dịch vụ tồn kho hiện không sẵn sàng", cause);
    }
}
```

`InventoryIntegrationException.java`:

```java
package com.example.inventory.application;

public class InventoryIntegrationException extends RuntimeException {
    public InventoryIntegrationException(Throwable cause) {
        super("Không thể hoàn tất yêu cầu tới dịch vụ tồn kho", cause);
    }
}
```

Các exception chỉ dùng kiểu Java của ứng dụng và `Throwable` làm cause. Adapter vẫn có thể đọc `Status.Code` để quyết định nhánh mapping, nhưng package application không phải phụ thuộc `io.grpc`. Exception gốc được giữ làm cause cho log nội bộ; message gửi lên tầng trên do ứng dụng kiểm soát.

**Mapping phải theo ngữ nghĩa operation.** `NOT_FOUND` ở `GetStock` có thể biểu thị SKU không tồn tại; ở RPC khác, cùng status có thể biểu thị route sai hoặc resource phụ thuộc khác. Không xây một quy tắc toàn cục rằng mọi `NOT_FOUND` đều là lỗi domain giống nhau. Tương tự, `UNAVAILABLE` và `DEADLINE_EXCEEDED` thường chỉ ra dependency không sẵn sàng/đúng hạn, nhưng không tự động cho phép retry một thao tác có tác dụng phụ.

## 4. Business service chỉ phụ thuộc port

Application service dùng `InventoryPort` và các kiểu domain/application, không import gRPC:

```java
package com.example.order.application;

import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class CheckOrderAvailability {

    private final InventoryPort inventory;

    public CheckOrderAvailability(InventoryPort inventory) {
        this.inventory = inventory;
    }

    public AvailabilityResult check(String rawSku) {
        StockAvailability stock = inventory.getAvailability(new Sku(rawSku));

        if (stock.availableUnits() == 0) {
            return AvailabilityResult.OUT_OF_STOCK;
        }
        return AvailabilityResult.AVAILABLE;
    }

    public enum AvailabilityResult {
        AVAILABLE,
        OUT_OF_STOCK
    }
}
```

Business service không biết lời gọi là gRPC blocking, REST hay một implementation giả trong test. Nó chỉ biết cần hỏi tồn kho và nhận `StockAvailability`. Đây là lợi ích chính của adapter: thay đổi kỹ thuật ở biên không lan vào quy tắc nghiệp vụ.

## 5. Spring wiring: để container chọn adapter

Trong cấu hình Spring, `GrpcInventoryAdapter` được đăng ký bằng `@Component` và nhận generated stub qua constructor. Stub được cung cấp bởi một `@Bean` tạo từ `ManagedChannel` đã cấu hình:

```java
@Bean
InventoryGrpc.InventoryBlockingStub inventoryBlockingStub(
        @Qualifier("inventoryChannel") ManagedChannel channel) {
    return InventoryGrpc.newBlockingStub(channel);
}
```

Vì `GrpcInventoryAdapter` là implementation duy nhất của `InventoryPort`, Spring có thể inject nó vào `CheckOrderAvailability`. Nếu ứng dụng có nhiều implementation (ví dụ gRPC primary và fake/local implementation), dùng `@Qualifier` hoặc `@Primary` để chọn rõ ràng. Không để business service tự gọi `new GrpcInventoryAdapter(...)`; container chịu trách nhiệm wiring các dependency hạ tầng.

Adapter là nơi phù hợp để áp dụng deadline cho RPC, chọn stub, chuyển đổi Protobuf và mapping status. Interceptor dùng chung cho logging/tracing/metrics có thể được gắn ở channel để mọi adapter dùng channel đó được quan sát thống nhất. Tránh đưa logic quan sát xuyên suốt vào business service.

## 6. Kiểm thử business code mà không cần gRPC server

Vì business service chỉ phụ thuộc `InventoryPort`, có thể kiểm tra quy tắc nghiệp vụ bằng một implementation giả rất nhỏ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import org.junit.jupiter.api.Test;

class CheckOrderAvailabilityTest {

    @Test
    void reportsOutOfStockWhenInventoryReturnsZero() {
        InventoryPort inventory = sku -> new StockAvailability(0);
        var service = new CheckOrderAvailability(inventory);

        assertEquals(
                CheckOrderAvailability.AvailabilityResult.OUT_OF_STOCK,
                service.check("SKU-42"));
    }

    @Test
    void reportsAvailableWhenStockExists() {
        InventoryPort inventory = sku -> new StockAvailability(5);
        var service = new CheckOrderAvailability(inventory);

        assertEquals(
                CheckOrderAvailability.AvailabilityResult.AVAILABLE,
                service.check("SKU-42"));
    }
}
```

Hai test này không khởi tạo Spring context, không cần generated code và không mở channel. Chúng kiểm tra trực tiếp quy tắc nghiệp vụ. Có thể bổ sung fake ném `InventoryUnavailableException` để xác minh service xử lý dependency failure theo chính sách của use case.

## 7. Kiểm thử riêng adapter với gRPC

Adapter cần một nhóm test khác để kiểm tra chuyển đổi giữa hai thế giới:

1. Dùng `grpc-inprocess` tạo server thử nghiệm triển khai `Inventory/GetStock`.
2. Tạo channel in-process và generated `InventoryBlockingStub`, sau đó khởi tạo `GrpcInventoryAdapter` bằng constructor.
3. Gửi một `Sku`; xác minh server nhận đúng `StockRequest.sku` và response được chuyển thành `StockAvailability`.
4. Cho server trả `NOT_FOUND`, `UNAVAILABLE` hoặc `INVALID_ARGUMENT`; xác minh adapter ném đúng application exception và giữ gRPC exception làm cause.
5. Đóng channel/server trong `finally` hoặc qua test lifecycle.

Test adapter không cần khởi tạo toàn bộ business service. Ngược lại, test business service không nên cần server gRPC. Sự phân tách này giúp biết lỗi nằm ở mapping Protobuf/transport hay ở quy tắc nghiệp vụ.

In-process test xác minh logic RPC nhưng không kiểm tra DNS, TLS, proxy hoặc HTTP/2 mạng thật. Một integration test qua TCP/TLS vẫn cần thiết cho các rủi ro triển khai. Khi cần xác minh Spring wiring, thêm context test kiểm tra `InventoryPort` resolve đúng `GrpcInventoryAdapter` và stub/channel được cấu hình.

## 8. Khi nào nên dùng adapter và khi nào không?

| Tình huống | Cách tiếp cận |
| --- | --- |
| Nhiều business service cần cùng một dependency gRPC | Tạo một port và adapter dùng chung để gom mapping/timeout/transport. |
| Protobuf thay đổi thường xuyên nhưng domain contract ổn định | Giữ mapping trong adapter để giới hạn phạm vi sửa đổi. |
| Cần fake dependency khi test nghiệp vụ | Inject port và cung cấp fake implementation. |
| Ứng dụng nhỏ, một use case đơn giản, không có logic nghiệp vụ đáng kể | Có thể inject stub trực tiếp vào một gateway nhỏ; tránh tạo nhiều lớp chỉ để chuyển tiếp một dòng. |
| Nhiều transport có thể thay thế nhau | Một port với các adapter riêng cho gRPC, REST hoặc local implementation. |

Adapter không phải mục tiêu tự thân. Nó hữu ích khi tạo ranh giới thực sự: chuyển kiểu dữ liệu, dịch lỗi, bảo vệ domain khỏi giao thức và làm test độc lập. Nếu adapter chỉ chuyển tiếp mọi tham số và response mà không tạo giá trị, cân nhắc giữ cấu trúc đơn giản hơn.

## 9. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Business service import generated Protobuf classes | Domain bị khóa vào contract gRPC. | Định nghĩa kiểu và port theo ngôn ngữ nghiệp vụ. |
| Port trả `StatusRuntimeException` | Chi tiết transport rò qua ranh giới. | Adapter chuyển thành application exception có ngữ nghĩa. |
| Adapter trả nguyên `StockReply` | Business code phải hiểu schema Protobuf. | Map sang `StockAvailability` hoặc kiểu ứng dụng phù hợp. |
| Một mapper toàn cục gán cùng ý nghĩa cho mọi status | `NOT_FOUND` hoặc `FAILED_PRECONDITION` bị diễn giải sai giữa các use case. | Mapping theo operation và hợp đồng nghiệp vụ. |
| Adapter tự retry mọi lỗi | Có thể lặp thao tác ghi hoặc vượt deadline tổng. | Để retry policy xét idempotency và use case. |
| Business service tự tạo channel/stub | Khó kiểm soát lifecycle và khó test. | Spring quản lý channel/stub; adapter nhận qua constructor. |
| Test business phải chạy server gRPC | Test chậm và trộn lỗi transport với lỗi nghiệp vụ. | Fake port trong unit test; test adapter riêng. |

## 10. Bài tập thực hành

1. Định nghĩa `InventoryPort` bằng các kiểu ứng dụng như `Sku` và `StockAvailability`; không import package generated gRPC.
2. Viết `GrpcInventoryAdapter` dùng `InventoryBlockingStub`, chuyển request/response Protobuf và đặt deadline phù hợp.
3. Ánh xạ `NOT_FOUND`, `UNAVAILABLE`, `DEADLINE_EXCEEDED` và lỗi không mong đợi thành exception ứng dụng có cause.
4. Sửa business service để chỉ phụ thuộc `InventoryPort`; xác minh không còn import `io.grpc` hoặc Protobuf trong package nghiệp vụ.
5. Viết unit test business bằng fake port và adapter test bằng gRPC in-process server.
6. Thay adapter gRPC bằng fake hoặc implementation khác trong Spring test context để kiểm tra business service không phụ thuộc transport.

Sau bài này, bạn cần nhận biết được port thuộc về ứng dụng, adapter thuộc về phần tích hợp, và business service chỉ nên phụ thuộc vào port. Việc chuyển đổi Protobuf, gắn deadline, xử lý gRPC status và quản lý generated stub nằm ở adapter/client infrastructure. Ranh giới này giúp Spring gRPC client thay đổi giao thức, kiểm thử dễ hơn và giữ quy tắc nghiệp vụ ổn định.
