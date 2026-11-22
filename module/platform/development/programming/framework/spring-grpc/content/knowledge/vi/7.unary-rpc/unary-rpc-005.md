# Mapping request từ application model

## 1. Vì sao cần ánh xạ application model sang request protobuf?

Trong **Spring gRPC**, phương thức unary nhận **một protobuf request** và trả về **một protobuf response** khi thành công. Tuy nhiên, dữ liệu mà nghiệp vụ sử dụng thường nằm trong **application model**: đối tượng Java chứa kiểu dữ liệu và quy tắc phù hợp với ứng dụng, chẳng hạn `UUID`, `Currency`, `Instant`, enum nội bộ hay một nhóm thông tin đã được kiểm tra.

Generated protobuf message lại là **hợp đồng truyền qua mạng**: các field theo số thứ tự và kiểu của Protocol Buffers, được mã hóa để client/server ở những ngôn ngữ khác nhau cùng hiểu. Hai loại model có trách nhiệm khác nhau nên cần một bước ánh xạ tại **ranh giới client gRPC**.

Ví dụ: nghiệp vụ muốn hỏi báo giá sản phẩm.

```text
HTTP/CLI/job input
       │  chuyển đổi và kiểm tra đầu vào
       ▼
PriceQuoteQuery                ← application model
       │
       │ PriceQuoteRequestMapper.toProto(...)
       ▼
PriceQuoteRequest              ← protobuf request
       │
       │ PricingServiceGrpc stub (unary RPC)
       ▼
Spring gRPC server
       │
       ▼
PriceQuoteResponse hoặc gRPC status lỗi
```

Mapper giúp:

- **Giữ kiểu nghiệp vụ rõ ràng:** `productId` ở ứng dụng là `UUID`, trong protobuf có thể là `string` để các nền tảng khác xử lý thuận tiện.
- **Tập trung quy tắc chuyển đổi:** enum, tiền tệ, thời điểm, danh sách, trường tùy chọn và giới hạn dữ liệu được xử lý ở một nơi.
- **Giảm phụ thuộc:** service nghiệp vụ không phải gọi `PriceQuoteRequest.newBuilder()` ở khắp nơi.
- **Kiểm thử riêng biệt:** có thể xác nhận quy tắc chuyển đổi mà không khởi động gRPC server hoặc mở cổng mạng.
- **Hỗ trợ phát triển hợp đồng:** khi schema thay đổi, mapper là điểm kiểm tra tương thích giữa application model và wire contract.

**Phạm vi bài học:** ánh xạ **request** cho unary RPC trong module `SPRING_GRPC`. Client vẫn cần cấu hình deadline, metadata, interceptor, TLS và xử lý gRPC status khi gửi lời gọi; mapper không thay thế các cơ chế đó.

## 2. Ví dụ hợp đồng unary trong file .proto

Giả sử một dịch vụ tính báo giá nhận ID sản phẩm, số lượng, tiền tệ, kênh bán, danh sách mã khuyến mãi, ghi chú tùy chọn và thời điểm áp giá. File `src/main/proto/pricing.proto`:

```proto
syntax = "proto3";

package pricing.v1;

option java_package = "com.example.pricing.grpc";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";

service PricingService {
  rpc GetQuote (PriceQuoteRequest) returns (PriceQuoteResponse);
}

enum SalesChannelProto {
  SALES_CHANNEL_UNSPECIFIED = 0;
  SALES_CHANNEL_WEB = 1;
  SALES_CHANNEL_STORE = 2;
}

message PriceQuoteRequest {
  string product_id = 1;
  int32 quantity = 2;
  string currency_code = 3;
  SalesChannelProto sales_channel = 4;
  repeated string promotion_codes = 5;
  optional string customer_note = 6;
  google.protobuf.Timestamp price_at = 7;
}

message PriceQuoteResponse {
  int64 total_minor_units = 1;
  string currency_code = 2;
}
```

Đây là **unary RPC** vì `GetQuote` không khai báo `stream` ở request hoặc response. Các lớp `PriceQuoteRequest`, `PriceQuoteResponse`, `SalesChannelProto` và `PricingServiceGrpc` được sinh bởi `protoc` cùng plugin gRPC Java đã cấu hình trong dự án.

Một số chi tiết quan trọng của request:

| Trường trong .proto | API Java sinh ra điển hình | Ý nghĩa khi mapping |
| --- | --- | --- |
| `string product_id` | `setProductId(String)` | Chuyển từ `UUID` sang chuỗi có quy ước ổn định. |
| `int32 quantity` | `setQuantity(int)` | Kiểm tra `quantity > 0` và giới hạn nghiệp vụ trước khi gửi. |
| `string currency_code` | `setCurrencyCode(String)` | Chuyển `Currency` thành mã như `USD` hoặc `VND`. |
| `SalesChannelProto sales_channel` | `setSalesChannel(SalesChannelProto)` | Ánh xạ enum nội bộ sang enum được sinh. |
| `repeated string promotion_codes` | `addAllPromotionCodes(Iterable<String>)` | Chuyển danh sách theo thứ tự, kiểm tra kích thước/nội dung. |
| `optional string customer_note` | `setCustomerNote(String)`, `hasCustomerNote()` | Phân biệt **không cung cấp** với **có cung cấp nhưng rỗng**. |
| `google.protobuf.Timestamp price_at` | `setPriceAt(Timestamp)`, `hasPriceAt()` | Chuyển `Instant` thành giây và nano; không chuyển thời gian thành chuỗi tùy ý. |

Trong `proto3`, các scalar thông thường như `int32` hay `string` nếu chưa được gán sẽ đọc ra giá trị mặc định (`0` hoặc `""`), không tự cho biết người gửi đã cố tình đặt giá trị đó hay chưa. `optional string customer_note` tạo **presence** để có thể dùng `hasCustomerNote()`. Message field như `price_at` cũng có presence. `repeated` khi không có phần tử được đọc như danh sách rỗng.

Số trong khai báo như `= 4` là **field number trên wire**, không phải giá trị mặc định của field. Không tùy tiện đổi hoặc tái sử dụng field number khi tiến hóa một hợp đồng đã có client sử dụng.

## 3. Định nghĩa application model độc lập với protobuf

Trong tầng ứng dụng, một yêu cầu báo giá có thể có kiểu mạnh hơn:

```java
// SalesChannel.java
package com.example.pricing.application;

public enum SalesChannel {
    WEB,
    STORE
}
```

```java
// PriceQuoteQuery.java
package com.example.pricing.application;

import java.time.Instant;
import java.util.Currency;
import java.util.List;
import java.util.UUID;

public record PriceQuoteQuery(
        UUID productId,
        int quantity,
        Currency currency,
        SalesChannel channel,
        List<String> promotionCodes,
        String customerNote,
        Instant priceAt
) {
    public PriceQuoteQuery {
        // null từ form/API có nghĩa là không có mã khuyến mãi.
        // Sao chép để tránh danh sách bị chỉnh sửa sau khi tạo query.
        promotionCodes = promotionCodes == null
                ? List.of()
                : List.copyOf(promotionCodes);
    }
}
```

`PriceQuoteQuery` là **model nội bộ**. Nó không import `PriceQuoteRequest`, `Timestamp` hay `SalesChannelProto`. Khi một HTTP controller đọc JSON, controller hoặc lớp chuyển đổi đầu vào có nhiệm vụ phân tích chuỗi thành `UUID`, `Currency`, `Instant`, enum nội bộ và tạo `PriceQuoteQuery`. Nếu ứng dụng gọi từ scheduler hoặc message consumer, cùng model này vẫn dùng được.

Ví dụ dữ liệu ứng dụng:

```java
PriceQuoteQuery query = new PriceQuoteQuery(
        UUID.fromString("a14b04af-13b1-40a8-a76d-4c171e481b76"),
        3,
        Currency.getInstance("USD"),
        SalesChannel.WEB,
        List.of("SAVE10", "MEMBER"),
        null,
        Instant.parse("2026-11-19T02:15:30.123456789Z")
);
```

Ở ví dụ này `customerNote == null` được hiểu là **field không xuất hiện** trong request; nếu `customerNote.equals("")`, field xuất hiện với giá trị rỗng. Cần thống nhất ngữ nghĩa này trong hợp đồng API trước khi triển khai.

**Không nên đặt generated protobuf class làm kiểu tham số trực tiếp của mọi application service.** Làm vậy khiến nghiệp vụ phụ thuộc wire schema và buộc nhiều nơi phải nhớ các đặc điểm như enum `UNSPECIFIED` hoặc presence của `optional`. Mapper tách trách nhiệm này ra.

## 4. Viết mapper từ application model sang protobuf request

Một mapper có thể là Spring `@Component` không lưu trạng thái để tái sử dụng và dễ unit test. Nó gồm hai việc:

1. **Kiểm tra các bất biến phù hợp tại biên client**: ID, quantity, currency, channel, giới hạn độ dài và danh sách.
2. **Chuyển kiểu có chủ đích**: UUID → string; Currency → ISO 4217 code; enum ứng dụng → enum proto; danh sách → repeated; nullable string → optional; Instant → Timestamp.

```java
package com.example.pricing.client;

import com.example.pricing.application.PriceQuoteQuery;
import com.example.pricing.application.SalesChannel;
import com.example.pricing.grpc.PriceQuoteRequest;
import com.example.pricing.grpc.SalesChannelProto;
import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

@Component
public class PriceQuoteRequestMapper {

    private static final int MAX_QUANTITY = 1_000;
    private static final int MAX_PROMOTIONS = 10;
    private static final Pattern PROMO_CODE =
            Pattern.compile("[A-Z0-9_-]{1,32}");

    public PriceQuoteRequest toProto(PriceQuoteQuery query) {
        Objects.requireNonNull(query, "query");

        if (query.productId() == null) {
            throw new IllegalArgumentException("productId là bắt buộc");
        }
        if (query.quantity() < 1 || query.quantity() > MAX_QUANTITY) {
            throw new IllegalArgumentException(
                    "quantity phải nằm trong khoảng 1..1000");
        }
        if (query.currency() == null) {
            throw new IllegalArgumentException("currency là bắt buộc");
        }
        if (query.channel() == null) {
            throw new IllegalArgumentException("channel là bắt buộc");
        }

        List<String> codes = query.promotionCodes();
        if (codes.size() > MAX_PROMOTIONS) {
            throw new IllegalArgumentException("Quá nhiều mã khuyến mãi");
        }
        for (String code : codes) {
            if (!PROMO_CODE.matcher(code).matches()) {
                throw new IllegalArgumentException(
                        "Mã khuyến mãi không hợp lệ: " + code);
            }
        }

        PriceQuoteRequest.Builder builder = PriceQuoteRequest.newBuilder()
                .setProductId(query.productId().toString())
                .setQuantity(query.quantity())
                .setCurrencyCode(query.currency().getCurrencyCode())
                .setSalesChannel(toProtoChannel(query.channel()))
                .addAllPromotionCodes(codes);

        if (query.customerNote() != null) {
            if (query.customerNote().length() > 200) {
                throw new IllegalArgumentException(
                        "customerNote vượt 200 ký tự UTF-16");
            }
            builder.setCustomerNote(query.customerNote());
        }

        if (query.priceAt() != null) {
            Timestamp timestamp = Timestamp.newBuilder()
                    .setSeconds(query.priceAt().getEpochSecond())
                    .setNanos(query.priceAt().getNano())
                    .build();

            // Kiểm tra khoảng thời gian hợp lệ của protobuf Timestamp.
            Timestamps.checkValid(timestamp);
            builder.setPriceAt(timestamp);
        }

        return builder.build();
    }

    private static SalesChannelProto toProtoChannel(
            SalesChannel channel) {
        return switch (channel) {
            case WEB -> SalesChannelProto.SALES_CHANNEL_WEB;
            case STORE -> SalesChannelProto.SALES_CHANNEL_STORE;
        };
    }
}
```

Đoạn code sử dụng `com.google.protobuf.util.Timestamps` trong thư viện **protobuf-java-util**; cần có dependency tương thích với phiên bản protobuf của dự án. Nếu không dùng thư viện tiện ích này, vẫn phải kiểm tra range/định dạng thời điểm trước khi gửi vì `Instant` của Java có khoảng giá trị rộng hơn chuẩn `google.protobuf.Timestamp`.

Các quyết định đáng chú ý:

- **Mapper không gọi mạng.** `toProto` chỉ nhận application model và trả một message bất biến; không tạo channel hoặc stub bên trong mapper.
- **ID ổn định.** `UUID#toString()` tạo dạng chuỗi chuẩn thống nhất. Server phải parse/validate theo cùng hợp đồng; không dùng `toString()` tùy tiện của một đối tượng ID không có format ổn định.
- **Enum ánh xạ tường minh.** Nếu ứng dụng thêm `PARTNER`, `switch` không có `default` khiến thiếu mapping trở nên dễ phát hiện khi biên dịch. Không nên dùng `enum.name()` ghép với chuỗi magic hoặc dựa vào ordinal.
- **Khuyến mãi không bị tự đổi thứ tự.** `repeated` trong protobuf có thứ tự; nếu mã trùng nhau cần được loại hoặc bị từ chối thì quy tắc đó phải được nêu rõ trong nghiệp vụ và bổ sung vào validator.
- **Ghi chú giữ nguyên presence.** `null` nghĩa là không gọi setter, còn `""` là set một chuỗi rỗng và `hasCustomerNote()` trả `true`.
- **Thời gian giữ độ chính xác nano.** `getEpochSecond()` và `getNano()` tránh việc làm mất phần nano khi chuyển qua mili giây.
- **Giới hạn dữ liệu là ví dụ.** `MAX_QUANTITY`, `MAX_PROMOTIONS` và mẫu mã khuyến mãi phải phản ánh hợp đồng nghiệp vụ thực tế, được thực thi nhất quán ở phía server.

`PriceQuoteQuery` dùng `List.copyOf` nên danh sách không chứa phần tử `null`; nếu đầu vào đưa phần tử `null`, việc tạo application model sẽ lỗi trước mapper. Đó là một quyết định có chủ đích. Nếu cần trả lỗi validation chi tiết cho từng phần tử, hãy kiểm tra và báo lỗi ở lớp nhận đầu vào trước khi gọi constructor này.

### Lược đồ dữ liệu trước và sau mapping

```mermaid
flowchart LR
    A["PriceQuoteQuery<br/>UUID, Currency, enum, List,<br/>String?, Instant?"] -->|"validate + convert"| B["PriceQuoteRequest.Builder"]
    B --> C["PriceQuoteRequest<br/>string, int32, enum,<br/>repeated, optional, Timestamp"]
    C --> D["PricingServiceGrpc stub"]
    D --> E["Unary GetQuote"]
```

Một mapper tốt thường là một hàm đơn giản, **deterministic** với cùng đầu vào và quy tắc, để unit test có thể so sánh các field mà không quan tâm thứ tự thực thi hoặc mạng.

## 5. Gọi unary RPC từ Spring bằng request đã map

Sau khi mapping thành công, client mới đưa request vào generated stub. Với Spring gRPC, có thể cấu hình channel tên `pricing` và đăng ký blocking stub:

```properties
# application.properties; địa chỉ local chỉ để minh họa.
spring.grpc.client.channels.pricing.address=static://localhost:9090
```

```java
package com.example.pricing.client;

import com.example.pricing.grpc.PricingServiceGrpc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.grpc.client.GrpcChannelFactory;

@Configuration
public class PricingGrpcClientConfiguration {

    @Bean
    PricingServiceGrpc.PricingServiceBlockingStub pricingBlockingStub(
            GrpcChannelFactory factory) {
        return PricingServiceGrpc.newBlockingStub(
                factory.createChannel("pricing"));
    }
}
```

Client đặt mapper giữa application model và stub:

```java
package com.example.pricing.client;

import com.example.pricing.application.PriceQuoteQuery;
import com.example.pricing.grpc.PriceQuoteRequest;
import com.example.pricing.grpc.PriceQuoteResponse;
import com.example.pricing.grpc.PricingServiceGrpc;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class PricingGrpcClient {

    private final PriceQuoteRequestMapper mapper;
    private final PricingServiceGrpc.PricingServiceBlockingStub stub;

    public PricingGrpcClient(
            PriceQuoteRequestMapper mapper,
            PricingServiceGrpc.PricingServiceBlockingStub stub) {
        this.mapper = mapper;
        this.stub = stub;
    }

    public PriceQuoteResponse getQuote(PriceQuoteQuery query) {
        // Lỗi mapping xảy ra trước khi khởi tạo lời gọi RPC.
        PriceQuoteRequest request = mapper.toProto(query);

        // withDeadlineAfter trả về stub dẫn xuất cho RPC hiện tại.
        return stub.withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
                .getQuote(request);
    }
}
```

`getQuote(query)` có hai lớp lỗi khác nhau:

| Vị trí lỗi | Ví dụ | Loại lỗi |
| --- | --- | --- |
| Ở application input/mapper, trước network | `quantity == 0`, thiếu `Currency`, Timestamp ngoài range | Thường là `IllegalArgumentException` hoặc lỗi validation ứng dụng; **chưa gửi RPC**. |
| Sau khi stub gọi server | `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAVAILABLE`, `DEADLINE_EXCEEDED` | `StatusRuntimeException` với gRPC status; cần quyết định cách xử lý ở ranh giới gọi. |
| Server trả thành công | Payload và status `OK` | Một `PriceQuoteResponse` trong lời gọi unary. |

Blocking stub được chọn vì đây là ví dụ luồng đồng bộ. Nếu ứng dụng dùng future stub, **mapper giữ nguyên**:

```java
// Ví dụ trong lớp client đã được tiêm PricingServiceFutureStub.
PriceQuoteRequest request = mapper.toProto(query);
ListenableFuture<PriceQuoteResponse> pending =
        futureStub.withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
                .getQuote(request);
```

Future stub là kiểu `PricingServiceGrpc.PricingServiceFutureStub`, còn `ListenableFuture` của Guava. Với async stub, gọi `getQuote(request, responseObserver)`. Cả ba đều gửi cùng protobuf message theo hợp đồng unary.

**Deadline** phải được đặt gần thời điểm phát sinh từng RPC. Nếu đặt `withDeadlineAfter` khi tạo singleton bean, hạn có thể đã hết trước khi request được gửi. Cấu hình transport, TLS và connection/channel là trách nhiệm của client infrastructure; mapper vẫn chỉ chuyển đổi dữ liệu.

## 6. Presence, giá trị mặc định và dữ liệu thiếu

Mapping thường sai không phải do `Builder` khó dùng mà do **ngữ nghĩa vắng mặt** giữa hai model khác nhau.

Xét ba trường hợp của `customerNote`:

| Giá trị trong application model | Mapping | Quan sát phía server |
| --- | --- | --- |
| `null` | Không gọi `setCustomerNote` | `hasCustomerNote() == false`; `getCustomerNote()` vẫn trả `""`. |
| `""` | Gọi `setCustomerNote("")` | `hasCustomerNote() == true`, giá trị rỗng. |
| `"Giao sau 18:00"` | Gọi setter với nội dung | `hasCustomerNote() == true` và có nội dung. |

**Không nên tự đổi `null` thành `""`** nếu hợp đồng cần phân biệt người dùng không nhập ghi chú với người dùng chủ động nhập chuỗi rỗng. Ngược lại, nếu business coi cả hai là “không có ghi chú”, nên chuẩn hóa tại một biên nhất quán và ghi rõ quy tắc.

Với `quantity` và `sales_channel`:

- `int32 quantity` không có `optional` sẽ đọc là `0` nếu vắng mặt. Server **phải tự kiểm tra** quantity hợp lệ, ngay cả khi Spring client đã validate.
- `SalesChannelProto` mặc định là `SALES_CHANNEL_UNSPECIFIED` (số `0`). Không dùng giá trị này như một kênh bán hợp lệ.
- Khi nhận enum mới từ phiên bản server/client khác, Java generated enum có thể cung cấp `UNRECOGNIZED`; code mapping ngược cần xử lý nhánh đó thay vì giả định chỉ có các giá trị ứng dụng hiện biết.
- `repeated promotion_codes` đọc là danh sách rỗng khi vắng; thường không phân biệt danh sách vắng với danh sách rỗng. Nếu cần phân biệt, hợp đồng phải mô hình hóa presence rõ ràng.
- `google.protobuf.Timestamp price_at` là message field có `hasPriceAt()`. Nếu không có thời điểm do client cung cấp, server phải định nghĩa và thực thi chính sách mặc định, ví dụ dùng thời điểm xử lý từ clock đáng tin cậy.

### Thêm trường oneof khi một request có nhiều cách xác định đối tượng

Khi yêu cầu chỉ cho phép **một trong hai khóa tra cứu**, có thể thiết kế một hợp đồng khác với `oneof`:

```proto
message LookupProductRequest {
  oneof identifier {
    string product_id = 1;
    string sku = 2;
  }
}
```

Generated builder sẽ có `setProductId(...)` hoặc `setSku(...)`; trên server có thể kiểm tra `getIdentifierCase()`. Nếu application model có hai trường nullable, mapper phải **kiểm tra chính xác một trường có giá trị** trước khi chọn setter. Đoạn này là ví dụ thiết kế mở rộng, không thay đổi contract `PriceQuoteRequest` đang dùng trong bài.

## 7. Chuyển đổi thời gian, enum và kiểu số mà không mất ngữ nghĩa

### Timestamp: Instant → protobuf Timestamp

`Instant` và `google.protobuf.Timestamp` đều biểu diễn thời điểm theo trục thời gian UTC, nhưng không có cùng phạm vi hợp lệ. Mapper:

```java
Timestamp timestamp = Timestamp.newBuilder()
        .setSeconds(priceAt.getEpochSecond())
        .setNanos(priceAt.getNano())
        .build();

Timestamps.checkValid(timestamp);
```

Cặp seconds/nanos giữ độ chính xác nano. Không nên dùng chuỗi ngày giờ theo múi giờ máy, `LocalDateTime.toString()` hoặc chuyển vòng qua `Date` nếu hợp đồng đòi thời điểm tuyệt đối. Nếu nghiệp vụ chỉ cần **ngày địa phương** (ví dụ ngày giao hàng), hãy cân nhắc kiểu lịch như `google.type.Date` với chính sách timezone rõ ràng, thay vì ép ngày thành một thời điểm tùy tiện.

**Bảo mật/nghiệp vụ:** `price_at` đến từ client chỉ là dữ liệu yêu cầu, không mặc nhiên là thời gian đáng tin để audit hoặc phê duyệt. Server nên áp quy tắc cho phép báo giá lịch sử và lưu thời điểm xử lý riêng.

### Enum ứng dụng → enum protobuf

Nên dùng chuyển đổi tường minh và có một giá trị `UNSPECIFIED = 0` trong enum proto. Tránh dựa vào thứ tự khai báo:

```java
private static SalesChannelProto toProtoChannel(SalesChannel value) {
    return switch (value) {
        case WEB -> SalesChannelProto.SALES_CHANNEL_WEB;
        case STORE -> SalesChannelProto.SALES_CHANNEL_STORE;
    };
}
```

Nếu sau này bổ sung kênh `PARTNER` ở app, `switch` tường minh giúp phát hiện phần mapping cần cập nhật. Khi thiết kế server nhận bản tin từ client cũ/mới, xử lý enum không hỗ trợ như lỗi có mã `INVALID_ARGUMENT` hoặc chính sách fallback được định nghĩa rõ; không ngầm hiểu mọi giá trị lạ là `WEB`.

### Tiền tệ và số tiền

Request dùng `Currency#getCurrencyCode()` để truyền mã tiền tệ. Không chuyển tiền sang `double` để tính toán hoặc truyền qua protobuf: nếu cần truyền số tiền, thường dùng **đơn vị nhỏ nhất dưới dạng `int64`** kèm currency code, hoặc schema decimal được thống nhất.

Trong ví dụ, `PriceQuoteResponse.total_minor_units` trả số nguyên. Nếu ứng dụng cần hiển thị `USD 12.34`, lớp xử lý response phải biết số chữ số thập phân của tiền tệ; không được mặc định mọi tiền tệ đều có hai chữ số thập phân.

## 8. Validation đặt ở đâu và ai chịu trách nhiệm?

Một yêu cầu có thể đi qua nhiều ranh giới:

1. **Adapter đầu vào** (REST controller, CLI, message consumer): parse JSON/string thành `UUID`, `Currency`, `Instant`; xử lý lỗi cú pháp và dữ liệu thiếu.
2. **Application model và validation nghiệp vụ**: xác định quantity, loại sản phẩm, chính sách giá, currency/channel được phép.
3. **gRPC request mapper**: bảo đảm mỗi field có biểu diễn protobuf đúng, presence và giới hạn wire phù hợp.
4. **gRPC server**: xác thực lại mọi dữ liệu vì request có thể đến từ client khác, không qua mapper Spring của ta.

Không nên dựa vào validation client để bảo vệ server. Mọi client đều có thể tự tạo protobuf message hợp lệ về cú pháp nhưng không hợp lệ về nghiệp vụ, ví dụ quantity `0` hoặc enum `UNSPECIFIED`.

### Phân biệt lỗi mapping và lỗi server

Ví dụ trong Spring MVC có thể chuyển lỗi validation ứng dụng thành HTTP `400 Bad Request` (tùy quy ước API). Với lỗi từ gRPC server, phải xét `StatusRuntimeException#getStatus().getCode()` để chuyển đúng thành lỗi nghiệp vụ hoặc trạng thái bên ngoài.

```java
try {
    PriceQuoteResponse response = pricingGrpcClient.getQuote(query);
    // Xử lý response khi status gRPC là OK.
} catch (IllegalArgumentException validationError) {
    // Input/application model/mapper không hợp lệ: chưa gửi RPC.
    throw validationError;
} catch (io.grpc.StatusRuntimeException rpcError) {
    switch (rpcError.getStatus().getCode()) {
        case INVALID_ARGUMENT -> {
            // Server từ chối request sau khi đã gửi.
            throw new IllegalArgumentException(
                    "Server từ chối thông tin báo giá", rpcError);
        }
        case DEADLINE_EXCEEDED, UNAVAILABLE -> {
            // Để tầng trên quyết định fallback/retry an toàn.
            throw new IllegalStateException(
                    "Dịch vụ báo giá chưa sẵn sàng", rpcError);
        }
        default -> throw rpcError;
    }
}
```

Đoạn code chỉ minh họa cách phân loại; hệ thống thực tế thường định nghĩa exception riêng và quy tắc ánh xạ lỗi có cấu trúc. Không nên parse chuỗi `Status.getDescription()` để phân nhánh nghiệp vụ hoặc trả nguyên stack trace/server internals về client.

## 9. Metadata, phân quyền và thông tin không nên đưa vào request

Mapper chuyển **dữ liệu nghiệp vụ**. Authentication token, trace context hoặc request correlation ID thường thuộc **gRPC metadata/interceptor/CallCredentials**, không phải field `customer_note` hoặc field token do người dùng nhập.

Trong hệ thống nhiều tenant, `tenantId` trong application context có thể được lấy từ principal đã xác thực. Nếu contract cần tenant field, client cần lấy từ **ngữ cảnh đáng tin** và server phải kiểm tra quyền truy cập tenant đó; không chỉ sao chép một chuỗi tenant bất kỳ từ HTTP body rồi tin rằng nó hợp lệ.

Một thiết kế có thể chia như sau:

| Loại thông tin | Nơi truyền thông thường | Nguyên tắc |
| --- | --- | --- |
| ID sản phẩm, số lượng, tiền tệ | Protobuf request | Validate và chuẩn hóa theo contract. |
| Authentication token | Metadata/CallCredentials qua kết nối TLS | Không đưa token vào log, message nghiệp vụ hoặc metric label. |
| Correlation ID/trace context | Metadata/interceptor/tracing instrumentation | Dùng để liên kết log/trace, có giới hạn và kiểm tra đầu vào. |
| Deadline cho RPC | Call options của stub | Đặt gần mỗi lần gọi; không nhúng timeout vào protobuf nếu đó là chính sách vận chuyển. |
| Tenant được phép truy cập | Security context và chính sách authorization của server | Không tin tenant chỉ vì client gửi trong payload. |

TLS phải được cấu hình cho channel phù hợp với server; mapper không quyết định plaintext/TLS. Khi cần theo dõi độ tin cậy, ghi thời gian mapping riêng nếu thấy cần, nhưng các metric RPC trọng tâm thường là latency, status, deadline và số lời gọi đang xử lý. Tránh đặt product ID hoặc token làm label metric có cardinality cao.

## 10. Kiểm thử mapper độc lập và kiểm thử tích hợp

Vì mapper không phụ thuộc network, một **unit test JUnit 5** có thể kiểm tra đầy đủ field conversion và presence. Ví dụ:

```java
package com.example.pricing.client;

import com.example.pricing.application.PriceQuoteQuery;
import com.example.pricing.application.SalesChannel;
import com.example.pricing.grpc.PriceQuoteRequest;
import com.example.pricing.grpc.SalesChannelProto;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Currency;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class PriceQuoteRequestMapperTest {

    private final PriceQuoteRequestMapper mapper =
            new PriceQuoteRequestMapper();

    private static PriceQuoteQuery sample(String note) {
        return new PriceQuoteQuery(
                UUID.fromString("a14b04af-13b1-40a8-a76d-4c171e481b76"),
                3,
                Currency.getInstance("USD"),
                SalesChannel.WEB,
                List.of("SAVE10", "MEMBER"),
                note,
                Instant.parse("2026-11-19T02:15:30.123456789Z"));
    }

    @Test
    void mapsAllFieldsAndPreservesNanoseconds() {
        PriceQuoteRequest proto = mapper.toProto(sample(null));

        assertEquals(
                "a14b04af-13b1-40a8-a76d-4c171e481b76",
                proto.getProductId());
        assertEquals(3, proto.getQuantity());
        assertEquals("USD", proto.getCurrencyCode());
        assertEquals(SalesChannelProto.SALES_CHANNEL_WEB,
                proto.getSalesChannel());
        assertEquals(List.of("SAVE10", "MEMBER"),
                proto.getPromotionCodesList());

        assertFalse(proto.hasCustomerNote());
        assertTrue(proto.hasPriceAt());
        assertEquals(123_456_789, proto.getPriceAt().getNanos());
        assertEquals(
                Instant.parse("2026-11-19T02:15:30.123456789Z")
                        .getEpochSecond(),
                proto.getPriceAt().getSeconds());
    }

    @Test
    void distinguishesAbsentNoteFromExplicitEmptyNote() {
        PriceQuoteRequest absent = mapper.toProto(sample(null));
        PriceQuoteRequest empty = mapper.toProto(sample(""));

        assertFalse(absent.hasCustomerNote());
        assertTrue(empty.hasCustomerNote());
        assertEquals("", empty.getCustomerNote());
    }

    @Test
    void rejectsQuantityBeforeCreatingRpcRequest() {
        PriceQuoteQuery invalid = new PriceQuoteQuery(
                UUID.randomUUID(),
                0,
                Currency.getInstance("USD"),
                SalesChannel.STORE,
                List.of(),
                null,
                null);

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toProto(invalid));
    }
}
```

Các test trên kiểm tra kết quả **trước khi gửi qua channel**. Có thể bổ sung test xác minh mã khuyến mãi sai pattern, quá nhiều mã, note quá dài, thiếu currency/channel, và Timestamp ngoài range.

### Kiểm thử tích hợp tại ranh giới gRPC

Một integration test nên gọi `PricingGrpcClient` hoặc generated stub tới server thử nghiệm và kiểm tra:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Mapping thành công, server chấp nhận request | Server nhận đúng product ID, quantity, currency, enum, danh sách, optional presence và Timestamp; unary trả một response `OK`. |
| Input sai quantity | Client từ chối trước RPC, xác nhận server không nhận lời gọi. |
| Server tự nhận protobuf thiếu trường bắt buộc về nghiệp vụ | Server trả `INVALID_ARGUMENT`, không tin rằng client đã validate. |
| Server chậm vượt deadline | Client nhận `DEADLINE_EXCEEDED`; xem xét hủy và tài nguyên còn hoạt động. |
| Mất kết nối | Client xử lý `UNAVAILABLE`/deadline phù hợp, tránh retry thao tác ghi thiếu idempotency. |
| Bật TLS và xác thực | Channel/certificate đúng mới kết nối thành công; server kiểm tra metadata và quyền truy cập. |

Có thể dùng `InProcessServerBuilder` và `InProcessChannelBuilder` của gRPC Java cho bài test giao thức/mapping nhẹ, nhưng chúng không kiểm tra TLS hay TCP/HTTP/2 thực. Để kiểm tra cấu hình Spring, interceptor và bảo mật, cần integration test chạy ứng dụng qua transport thực với cấu hình tương ứng.

### Kiểm thử tương thích schema

Khi thêm enum value hay optional field mới, viết test về cách phiên bản cũ xử lý dữ liệu vắng mặt, enum chưa biết và default. Khi xóa field đã triển khai, dùng `reserved` cho field number/name tương ứng thay vì tái sử dụng chúng cho ý nghĩa khác. Mapper cần thay đổi cùng hợp đồng, nhưng application model không bắt buộc thay đổi nếu giá trị wire mới có thể được suy ra một cách an toàn.

## 11. Những lỗi mapping thường gặp

1. **Để application service tự tạo builder khắp nơi.** Dẫn tới các quy tắc chuyển đổi/validation khác nhau. Tập trung mapping tại biên gRPC.
2. **Map enum theo ordinal hoặc chuỗi tùy ý.** Chỉ một lần sắp xếp lại enum cũng có thể khiến server hiểu sai kênh bán. Dùng `switch` tường minh.
3. **Đổi tất cả `null` thành giá trị mặc định.** Có thể xóa mất ngữ nghĩa presence của `optional` và message field.
4. **Truyền thời gian qua `LocalDateTime.toString()`.** Dễ mất múi giờ hoặc hiểu sai thời điểm; dùng `Timestamp` với seconds/nanos cho thời điểm tuyệt đối.
5. **Dùng `double` biểu diễn số tiền.** Gây sai số nhị phân; sử dụng số nguyên đơn vị nhỏ nhất hoặc decimal contract đã thống nhất.
6. **Tin rằng client validation bảo vệ server.** Bất kỳ client nào cũng có thể gửi message khác; server luôn phải xác thực và phân quyền.
7. **Đặt network call bên trong mapper.** Khiến khó test, che giấu deadline và trộn hai loại lỗi. Mapper chỉ chuyển dữ liệu.
8. **Tái sử dụng field number protobuf đã xóa.** Có thể khiến dữ liệu cũ bị giải nghĩa sai. Giữ field number ổn định và `reserved` field đã loại bỏ.
9. **Nhúng token, tenant tùy ý và trace context vào nghiệp vụ thiếu kiểm tra.** Dễ rò rỉ và vượt quyền; dùng đúng metadata/security context cùng authorization phía server.
10. **Không giới hạn danh sách hoặc độ dài chuỗi.** Message quá lớn làm tăng cấp phát bộ nhớ, thời gian mã hóa và tải server; áp hạn mức theo contract và vận hành.

## 12. Bài thực hành

Hãy mở rộng `PriceQuoteQuery` và `PriceQuoteRequest` để hỗ trợ một lựa chọn `include_tax_breakdown`, với quy tắc mặc định của ứng dụng là `false`. Xác định rõ **có cần phân biệt không cung cấp và chủ động chọn false hay không** trước khi chọn `bool` thường hay `optional bool` trong `proto3`.

Tiếp đó:

- Thêm mapping cho field mới mà không sửa controller hoặc application service để gọi builder trực tiếp.
- Viết unit test chứng minh ID, enum, repeated promotion codes, optional note và Timestamp được chuyển đúng; ghi thêm test quantity bằng `0`.
- Dựng unary gRPC server thử nghiệm ghi nhận request, xác minh request đến server đúng như mapper tạo ra và status khi server từ chối input không hợp lệ.
- Thử gửi hai request liên tiếp qua cùng stub nhưng deadline riêng, và xác nhận một RPC bị timeout không làm thay đổi request protobuf đã được tạo cho RPC còn lại.

**Tự kiểm tra:** Từ `PriceQuoteQuery` có kiểu Java phù hợp nghiệp vụ, mapper tạo **một `PriceQuoteRequest` bất biến** với các field, default và presence đúng contract. Sau đó stub mới gửi request unary. **Mapping là chuyển đổi dữ liệu trước RPC; gRPC status, deadline, TLS và authorization thuộc các lớp xử lý khác**, nhưng toàn bộ phải phối hợp để client/server hoạt động chính xác và an toàn.

