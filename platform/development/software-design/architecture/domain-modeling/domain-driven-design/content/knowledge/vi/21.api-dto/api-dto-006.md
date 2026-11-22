# Phiên bản hợp đồng giao tiếp và thay đổi mô hình bên trong

Trong Domain-Driven Design (DDD), domain model được thiết kế để diễn đạt quy tắc và ngôn ngữ của một bounded context. API lại phục vụ một mục tiêu khác: cung cấp hợp đồng giao tiếp ổn định cho client, đối tác hoặc hệ thống khác. Hai mô hình có liên quan nhưng không cần giống nhau.

Nếu API trả thẳng entity hoặc aggregate của domain, thay đổi nội bộ như tách aggregate, đổi tên thuộc tính, thay ORM hay điều chỉnh quan hệ có thể vô tình làm thay đổi hợp đồng mà client đang sử dụng. Ngược lại, nếu API contract được thiết kế độc lập, nhóm có thể thay đổi mô hình bên trong và chuyển đổi dữ liệu tại ranh giới mà không buộc mọi client nâng cấp cùng lúc.

Khi API đã được sử dụng, hợp đồng cần tiến hóa có kiểm soát. Thêm trường, đổi kiểu dữ liệu, thay ý nghĩa trạng thái hoặc loại bỏ endpoint đều có thể ảnh hưởng đến client. Versioning giúp quản lý những thay đổi không tương thích, nhưng không phải thay đổi nào cũng cần tạo phiên bản mới. Nhóm cần phân biệt thay đổi tương thích với breaking change, chọn cách version phù hợp, duy trì mapping giữa DTO và domain model, rồi triển khai theo lộ trình để các phiên bản cũ và mới có thời gian cùng hoạt động.

## 1. Domain model và API contract phục vụ hai mục đích khác nhau

**Domain model** diễn đạt khái niệm, hành vi, identity và invariant bên trong bounded context. Nó được tối ưu để bảo vệ quy tắc nghiệp vụ và hỗ trợ thay đổi mô hình.

**API contract (hợp đồng giao tiếp)** mô tả những gì một bên cung cấp và bên khác được phép gửi hoặc nhận: endpoint, phương thức, trường dữ liệu, kiểu dữ liệu, validation, lỗi, phân trang, quyền truy cập và semantics của thao tác.

Hai mô hình có thể cùng nói về một đơn hàng nhưng thể hiện các khía cạnh khác nhau:

| Domain model | API contract |
| --- | --- |
| `Order` aggregate | `OrderResponse` hoặc resource đơn hàng |
| `OrderId` | Chuỗi `orderId` trong JSON hoặc path parameter |
| `Money` value object | Cặp `amount` và `currency` theo schema API |
| `confirm()` | Request gửi đến endpoint hoặc command API |
| Invariant đơn không thể xác nhận khi rỗng | Validation/error contract mà client có thể hiểu |
| Domain event `OrderConfirmed` | Response HTTP hoặc integration event được công bố riêng |

API không cần phơi bày cấu trúc aggregate, entity con hoặc tên class Java. Một domain model có thể thay đổi nhiều lần trong khi API contract vẫn giữ nguyên nếu ý nghĩa mà client sử dụng không đổi.

### 1.1. Vì sao không trả trực tiếp entity hoặc aggregate?

Trả trực tiếp entity thường tạo ra các rủi ro:

- Client phụ thuộc vào tên và cấu trúc thuộc tính nội bộ.
- ORM có thể serialize quan hệ lazy, gây truy vấn ngoài dự kiến hoặc vòng tham chiếu.
- Thêm thuộc tính nội bộ có thể vô tình làm lộ dữ liệu.
- Thay đổi aggregate hoặc quan hệ entity buộc API thay đổi theo.
- Client có thể gửi lại các trường mà họ không được phép sửa.
- Quy tắc bảo mật và quyền chỉnh sửa khó được kiểm soát theo từng use case.

DTO (Data Transfer Object) tạo ra một hình dạng dữ liệu dành riêng cho việc truyền qua ranh giới. DTO giúp chọn trường nào được công bố, trường nào được nhận và cách biểu diễn dữ liệu mà không làm domain model phụ thuộc giao thức.

### 1.2. DTO không phải domain object

DTO thường chỉ mang dữ liệu. Nó có thể được tạo ra từ request, response hoặc message. Nó không nhất thiết có identity, hành vi hay invariant như entity và aggregate.

Một `OrderCreateRequest` có thể chứa `productId`, `quantity` và địa chỉ giao hàng. Domain model có thể chuyển những giá trị đó thành `Order`, `OrderLine`, `ProductId`, `Quantity` và `ShippingAddress`, sau khi kiểm tra quy tắc miền. Không nên dùng request DTO làm aggregate chỉ vì các trường trông giống nhau.

## 2. Hợp đồng giao tiếp là cam kết với consumer

Khi một client tích hợp với API, client dựa vào một số giả định:

- Endpoint và HTTP method có ý nghĩa ổn định.
- Tên trường và kiểu dữ liệu không đổi ngoài dự kiến.
- Trường bắt buộc, tùy chọn và nullable có semantics rõ.
- Các giá trị enum và trạng thái được diễn giải nhất quán.
- Mã lỗi và cấu trúc lỗi có thể xử lý được.
- Quy tắc phân trang, sắp xếp và lọc không thay đổi âm thầm.
- Các hành động có tác dụng phụ có semantics được công bố.

Những giả định này hình thành contract. Một thay đổi có thể không làm server compile lỗi nhưng vẫn phá client ở runtime. Ví dụ, đổi `totalAmount` từ số thập phân sang chuỗi có thể khiến client parse thất bại; thêm một giá trị mới vào enum có thể làm client cũ rơi vào nhánh không xử lý.

Hợp đồng cần được xem như sản phẩm mà provider cung cấp cho consumer. Vì thế, thay đổi phải được đánh giá từ góc nhìn của consumer, không chỉ từ góc nhìn mã nguồn phía server.

## 3. DTO ở ranh giới API

Thông thường nên có DTO riêng cho request và response. Hai chiều có nhu cầu khác nhau: request chỉ nhận dữ liệu client được phép cung cấp; response chỉ công bố dữ liệu client được phép nhìn thấy.

Ví dụ:

```java
public record CreateOrderRequest(
        String customerId,
        List<CreateOrderLineRequest> lines,
        String promotionCode
) {}

public record CreateOrderLineRequest(
        String productId,
        int quantity
) {}

public record OrderResponse(
        String orderId,
        String status,
        MoneyResponse total,
        Instant createdAt
) {}

public record MoneyResponse(
        String amount,
        String currency
) {}
```

Các DTO trên là hình dạng giao tiếp. Application layer có thể chuyển `CreateOrderRequest` thành command hoặc kiểu dữ liệu đầu vào của use case. Response được tạo từ kết quả ứng dụng hoặc read model.

### 3.1. Request DTO không phải bản sao có thể ghi của entity

Không nên nhận một `OrderEntity` đầy đủ rồi để client gửi mọi thuộc tính. Client không nên tự quyết định các trường như `status`, `createdAt`, `approvedBy`, `version` nội bộ hoặc `paymentCapturedAt` nếu use case không cho phép.

Hãy tạo request theo hành động:

- `CreateOrderRequest` để tạo đơn.
- `ChangeDeliveryAddressRequest` để đổi địa chỉ giao hàng.
- `CancelOrderRequest` để yêu cầu hủy đơn.
- `ConfirmOrderRequest` nếu client thực sự được phép kích hoạt use case xác nhận.

Cách này giúp API thể hiện ý định và giới hạn quyền ghi. Với một thao tác có ý nghĩa nghiệp vụ, endpoint/command riêng thường rõ hơn một request tổng quát cho phép sửa mọi trường.

### 3.2. Response DTO có thể khác nhau theo use case

Màn hình danh sách có thể chỉ cần `OrderSummaryResponse`, trong khi trang chi tiết cần `OrderDetailResponse`. Một đối tác vận chuyển chỉ cần mã đơn, địa chỉ giao, kiện hàng và thời gian bàn giao. Không cần dùng một DTO khổng lồ cho mọi consumer.

Tuy nhiên, đừng tạo quá nhiều DTO chỉ vì mỗi màn hình có cách hiển thị khác nhau. Hãy phân biệt nhu cầu trình bày của client với các hợp đồng nghiệp vụ cần ổn định.

## 4. Thay đổi mô hình bên trong không nhất thiết làm đổi API

Giả sử ban đầu `Order` lưu trực tiếp `customerName` và `customerAddress`. Sau đó nhóm chuyển sang tham chiếu `CustomerId` và lấy thông tin khách hàng qua một aggregate khác. Đây là thay đổi domain model. Nếu API vẫn cần trả tên và địa chỉ tại thời điểm đặt hàng, mapper có thể lấy snapshot phù hợp và tiếp tục trả cùng cấu trúc response.

Một số thay đổi nội bộ thường có thể được che giấu sau mapping:

- Đổi tên class, package hoặc method.
- Tách một entity thành nhiều value object.
- Gộp hoặc tách aggregate.
- Chuyển từ JPA sang JDBC hoặc thay database.
- Đổi cấu trúc bảng và cách lưu dữ liệu.
- Thêm domain service hoặc thay đổi policy.
- Thay đổi cách tính toán nhưng vẫn giữ semantics API đã công bố.

Điều kiện là output và hành vi quan sát được từ phía consumer vẫn đáp ứng contract. Nếu thay đổi làm đổi ý nghĩa nghiệp vụ mà client dựa vào, đó có thể là thay đổi contract dù JSON schema không đổi.

### 4.1. Mapping là ranh giới bảo vệ mô hình

Mapper chuyển đổi giữa DTO, command/query và domain/read model. Mapping không chỉ đổi tên trường; nó còn là nơi thể hiện cách biểu diễn của API tương ứng với khái niệm miền.

Ví dụ, API nhận `customerId` dưới dạng chuỗi. Mapper có thể chuyển thành `CustomerId`. API nhận số lượng dạng integer. Mapper có thể chuyển thành `Quantity` value object. API trả trạng thái `CONFIRMED`, trong khi domain model dùng một kiểu trạng thái khác; mapper quyết định biểu diễn công khai nào thuộc contract.

Không nên đặt mọi quy tắc nghiệp vụ trong mapper. Mapper chuyển đổi và kiểm tra cấu trúc; domain model vẫn phải bảo vệ invariant, kể cả khi use case được gọi từ message, batch job hoặc CLI thay vì HTTP.

## 5. Tương thích ngược và thay đổi phá vỡ

Một thay đổi API cần được đánh giá theo consumer hiện tại. Trong ngữ cảnh provider cập nhật server:

- **Tương thích với client cũ (backward-compatible provider change):** server mới vẫn chấp nhận các request hợp lệ của client cũ và vẫn trả response mà client cũ có thể hiểu.
- **Không tương thích (breaking change):** một client đang hoạt động theo contract cũ có thể lỗi hoặc hiểu sai khi gặp server mới.

Thuật ngữ backward/forward compatibility đôi khi được dùng theo góc nhìn schema hoặc consumer, vì vậy tài liệu dự án nên nói rõ đang xét chiều nào. Điều quan trọng là kiểm tra tương tác cụ thể giữa producer/provider và consumer/client.

### 5.1. Những thay đổi thường có thể tương thích

Một số thay đổi có khả năng tương thích nếu client và server tuân thủ quy tắc phù hợp:

- Thêm trường response tùy chọn mà client cũ bỏ qua trường chưa biết.
- Thêm endpoint mới mà không thay đổi endpoint cũ.
- Thêm một request field tùy chọn khi server mới có default rõ và client cũ không gửi trường đó.
- Thêm metadata không bắt buộc vào response.
- Tối ưu implementation nội bộ mà không đổi hành vi quan sát được.

Tuy nhiên, “thêm trường” không tự động an toàn. Một client dùng JSON schema strict hoặc generated model có thể từ chối trường response chưa biết. Một server cũ có thể từ chối request chứa trường mới nếu cấu hình deserialization nghiêm ngặt. Cần kiểm tra hành vi thật của các consumer và provider.

### 5.2. Những thay đổi thường là breaking change

Các thay đổi sau thường phá hợp đồng:

- Xóa hoặc đổi tên endpoint đang được dùng.
- Đổi HTTP method hoặc thay semantics của endpoint.
- Xóa trường response hoặc đổi tên trường.
- Đổi kiểu dữ liệu, đơn vị hoặc định dạng trường.
- Thêm trường request bắt buộc mà client cũ không gửi.
- Đổi trường optional thành required.
- Đổi cách hiểu `null`, trường vắng mặt hoặc giá trị mặc định.
- Đổi ý nghĩa enum, trạng thái hoặc mã lỗi.
- Thay đổi quy tắc phân trang, sắp xếp hoặc lọc.
- Siết validation khiến request trước đây hợp lệ bị từ chối.
- Thay đổi semantics của thao tác nhưng giữ nguyên endpoint và schema.

Ví dụ, `status = "CONFIRMED"` trước đây có nghĩa đơn đã được xác nhận và kho có thể chuẩn bị hàng. Nếu server đổi ý nghĩa thành “đã gửi yêu cầu xác nhận nhưng chưa hoàn tất”, schema không đổi nhưng contract đã thay đổi về semantics.

## 6. Thay đổi trường và kiểu dữ liệu

Khi thay đổi một trường, cần xem xét tên, kiểu, nullability, đơn vị, miền giá trị và semantics.

| Thay đổi | Rủi ro | Hướng xử lý thường gặp |
| --- | --- | --- |
| Thêm response field optional | Client strict có thể từ chối trường lạ | Kiểm tra consumer; công bố rõ và kiểm thử |
| Thêm request field optional | Server cũ có thể từ chối trường lạ | Chỉ gửi sau khi provider hỗ trợ hoặc version hóa |
| Xóa field | Client đang đọc field bị lỗi | Giữ field trong thời gian deprecation, tạo phiên bản mới nếu cần |
| Đổi tên field | Client không tìm thấy tên cũ | Thêm field mới song song, migrate consumer rồi loại bỏ ở version mới |
| Đổi kiểu số sang chuỗi | Client parse theo kiểu cũ bị lỗi | Tạo field/contract mới hoặc API version mới |
| Đổi đơn vị đo | Client tính toán sai dù kiểu dữ liệu không đổi | Định nghĩa trường mới có đơn vị rõ hoặc version mới |
| Thêm enum value | Client exhaustive có thể không xử lý | Thiết kế consumer tolerant và có nhánh unknown |
| Thêm giá trị required | Client cũ không cung cấp | Dùng default tương thích hoặc version mới |

### 6.1. Null, absent và empty là ba trạng thái khác nhau

Trong JSON, một trường có thể:

- Không xuất hiện: `{"name": "An"}`.
- Xuất hiện với `null`: `{"name": "An", "middleName": null}`.
- Xuất hiện với chuỗi rỗng: `{"name": "An", "middleName": ""}`.

Ba trường hợp này có thể có ý nghĩa khác nhau, đặc biệt với `PATCH`. Trường vắng mặt có thể nghĩa là “không thay đổi”; `null` có thể nghĩa là “xóa giá trị”; chuỗi rỗng có thể là một giá trị không hợp lệ hoặc giá trị hợp lệ tùy miền.

Hợp đồng phải định nghĩa rõ semantics này. Không nên đổi từ absent sang null hoặc ngược lại mà không đánh giá tác động đến client.

### 6.2. Enum cần có chiến lược unknown

Server có thể bổ sung trạng thái mới như `PARTIALLY_FULFILLED`. Client cũ có thể dùng switch exhaustive hoặc parser chỉ chấp nhận tập enum đã biết. API nên công bố khả năng xuất hiện giá trị mới và client cần có cách xử lý unknown phù hợp, nếu yêu cầu tương thích cho phép.

Nếu client không thể chấp nhận giá trị chưa biết, việc thêm enum có thể là breaking change. Không nên giả định enum luôn an toàn chỉ vì giá trị mới được thêm vào.

## 7. Các chiến lược versioning API

Khi cần thay đổi không tương thích, nhóm có thể công bố một phiên bản contract mới. Có một số cách phổ biến.

### 7.1. Version trong URL

Ví dụ:

```text
GET /api/v1/orders/ORD-501
GET /api/v2/orders/ORD-501
```

Ưu điểm:

- Dễ nhìn thấy và dễ thử bằng browser hoặc curl.
- Dễ định tuyến và quan sát log theo version.
- Tài liệu OpenAPI có thể tách rõ từng phiên bản.

Hạn chế:

- URL version trở thành một phần công khai của resource path.
- Có thể tạo nhiều route/controller nếu không tổ chức mapping tốt.
- Cần chính sách vòng đời cho các phiên bản cũ.

Đây là cách dễ hiểu và thường được sử dụng, nhưng không phải tiêu chuẩn duy nhất.

### 7.2. Version qua header

Client gửi version trong request header, ví dụ:

```http
GET /api/orders/ORD-501
Accept: application/vnd.example.order-v2+json
```

Ưu điểm là URI resource có thể giữ ổn định trong khi representation thay đổi. Hạn chế là version ít hiển thị hơn khi quan sát URL và cần công cụ, tài liệu hỗ trợ header rõ ràng.

### 7.3. Version qua media type hoặc content negotiation

Client dùng `Accept` để yêu cầu representation cụ thể và có thể dùng `Content-Type` cho request body. Cách này phù hợp khi tổ chức muốn biểu diễn nhiều dạng representation cho cùng một resource.

### 7.4. Version trong schema hoặc message type

Với message/event hoặc schema dùng chung, version có thể nằm trong subject, tên schema, envelope hoặc metadata. Ví dụ `sales.order-confirmed.v2`. Đây là vấn đề contract của message, không nhất thiết dùng cùng cách với REST API.

### 7.5. Không version hóa mọi lần release

API version không nên tăng chỉ vì server được deploy hoặc domain model có thêm một field nội bộ. Version phản ánh contract hoặc semantics công khai. Nếu thay đổi vẫn tương thích, có thể giữ version hiện tại và phát hành implementation mới.

## 8. Duy trì nhiều phiên bản mà không nhân đôi domain model

Khi API v1 và v2 cùng tồn tại, không nên tạo hai domain model hoàn toàn độc lập nếu cả hai cùng phục vụ một bounded context và cùng quy tắc nghiệp vụ. Thay vào đó, có thể dùng adapter/mapper riêng cho từng contract.

```text
                 API v1 Controller
                        |
                        v
                 V1 Request/Response
                        |
                        v
                 V1 Mapper / Adapter
                        |
                        +--------------------+
                                             |
                                             v
                                      Application Use Case
                                             |
                                             v
                                         Domain Model
                                             ^
                                             |
                 V2 Mapper / Adapter         |
                        ^                    |
                        |                    |
                 V2 Request/Response         |
                        ^                    |
                        |                    |
                 API v2 Controller ----------+
```

Hai controller hoặc adapter chuyển đổi các DTO phiên bản khác nhau về cùng command/use case nếu semantics tương đương. Response được ánh xạ từ kết quả ứng dụng sang DTO tương ứng.

### 8.1. Ví dụ Java: hai response contract

Giả sử v1 trả trạng thái dạng chuỗi và tổng tiền ở hai trường riêng; v2 nhóm tiền vào một object:

```java
public record OrderResponseV1(
        String id,
        String status,
        String totalAmount,
        String currency
) {}

public record OrderResponseV2(
        String orderId,
        OrderStatusResponse status,
        MoneyResponse total,
        Instant confirmedAt
) {}

public record MoneyResponse(
        String amount,
        String currency
) {}

public enum OrderStatusResponse {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

Mapper có thể chuyển cùng một read model sang hai hình dạng:

```java
public final class OrderResponseMapper {
    public OrderResponseV1 toV1(OrderView order) {
        return new OrderResponseV1(
                order.id().value(),
                order.status().name(),
                order.total().amount().toPlainString(),
                order.total().currency().getCurrencyCode()
        );
    }

    public OrderResponseV2 toV2(OrderView order) {
        return new OrderResponseV2(
                order.id().value(),
                mapStatus(order.status()),
                new MoneyResponse(
                        order.total().amount().toPlainString(),
                        order.total().currency().getCurrencyCode()
                ),
                order.confirmedAt()
        );
    }

    private OrderStatusResponse mapStatus(OrderStatus status) {
        return switch (status) {
            case DRAFT -> OrderStatusResponse.DRAFT;
            case CONFIRMED -> OrderStatusResponse.CONFIRMED;
            case CANCELLED -> OrderStatusResponse.CANCELLED;
        };
    }
}
```

Ví dụ minh họa mapping; `OrderView` là read model của ứng dụng, không nhất thiết là aggregate entity. Nếu domain có trạng thái mới mà v1 không biểu diễn được, mapper v1 phải có chính sách rõ: ánh xạ sang trạng thái tương đương đã công bố, trả lỗi có chủ đích hoặc không cung cấp dữ liệu đó cho v1. Không nên âm thầm gán sai semantics.

### 8.2. Giữ riêng request DTO theo version

Nếu request v1 và v2 khác nhau, hãy giữ DTO riêng:

```java
public record CreateOrderRequestV1(
        String customerId,
        List<OrderLineRequestV1> lines
) {}

public record CreateOrderRequestV2(
        String buyerReference,
        List<OrderLineRequestV2> items,
        String promotionCode
) {}
```

Mỗi adapter chuyển request thành command nội bộ. Không nên dùng một DTO duy nhất với nhiều trường nullable chỉ để phục vụ mọi phiên bản, vì sẽ tạo ra nhiều tổ hợp trạng thái không hợp lệ.

## 9. Mapping không phải nơi thay thế validation và domain rule

Validation ở ranh giới API thường kiểm tra cấu trúc và điều kiện đầu vào như trường bắt buộc, định dạng, độ dài hoặc kiểu dữ liệu. Domain model kiểm tra quy tắc nghiệp vụ và invariant.

Ví dụ:

- DTO validation: `quantity` phải có mặt và là số nguyên dương.
- Domain rule: sản phẩm có thể được bán trong thời gian đặt hàng không.
- DTO validation: `promotionCode` không vượt giới hạn độ dài.
- Domain rule: mã khuyến mại có áp dụng cho phân khúc khách hàng và sản phẩm này không.

Không nên chỉ dựa vào annotation validation của controller. Use case có thể được gọi từ message hoặc batch job; domain rule phải được bảo vệ trong mô hình hoặc application/domain service phù hợp.

### 9.1. Tránh mass assignment

Nếu request được ánh xạ tự động vào entity, client có thể gửi các trường không được phép cập nhật như `status`, `ownerId`, `approvedAt` hoặc `creditLimit`. Hãy chọn trường đầu vào theo use case và tạo command tường minh.

### 9.2. Xử lý lỗi theo contract

Domain exception không nên được serialize trực tiếp thành response. API adapter hoặc exception handler chuyển lỗi ứng dụng thành cấu trúc lỗi công khai ổn định, ví dụ mã lỗi, thông điệp phù hợp, field error và correlation ID. Không để stack trace, tên class nội bộ hoặc SQL message rò rỉ ra ngoài.

## 10. Thay đổi API tương thích: ví dụ và điều kiện

Một số thay đổi thường được xem là additive, nhưng phải xác minh theo cách consumer thực sự parse contract.

### 10.1. Thêm response field optional

Server thêm `estimatedDeliveryAt` vào response. Client cũ bỏ qua trường không biết có thể tiếp tục hoạt động. Tuy nhiên, client được sinh từ schema strict hoặc dùng deserializer từ chối unknown field có thể lỗi. Vì vậy, cần contract test hoặc xác nhận cách client parse.

### 10.2. Thêm request field optional

Server mới chấp nhận `promotionCode` nhưng vẫn xử lý request cũ khi trường này vắng mặt. Đây thường là thay đổi tương thích với client cũ. Nhưng nếu client mới gửi `promotionCode` đến server cũ đang từ chối trường lạ, request có thể thất bại. Cần triển khai server hỗ trợ trước khi client bắt đầu gửi trường mới.

### 10.3. Thêm enum value

Server thêm trạng thái `PARTIALLY_SHIPPED`. Client cũ cần có nhánh xử lý unknown hoặc cách hiển thị fallback. Nếu client dùng enum generated và parser strict, thay đổi này có thể phá vỡ tương thích.

### 10.4. Thay đổi semantics

Server đổi `createdAt` từ thời điểm nhận request thành thời điểm commit đơn. Kiểu dữ liệu và tên không đổi, nhưng ý nghĩa thay đổi. Đây là contract change vì consumer có thể đang dùng trường để đo thời gian tiếp nhận.

### 10.5. Siết validation

Trước đây API chấp nhận chuỗi có khoảng trắng ở đầu; sau đó server bắt đầu từ chối. Dù schema không đổi, một request trước đây hợp lệ đã trở thành không hợp lệ. Đây có thể là breaking change với client hiện tại.

## 11. Quy trình deprecation và loại bỏ phiên bản cũ

Khi cần thay đổi không tương thích, không nên loại bỏ version cũ ngay sau khi deploy version mới. Client có chu kỳ release và khả năng nâng cấp khác nhau.

Một lộ trình thường gồm:

1. Công bố contract mới và lý do thay đổi.
2. Triển khai version mới song song với version cũ.
3. Cung cấp hướng dẫn mapping từ field/endpoint cũ sang mới.
4. Thông báo thời gian deprecation và ngày dự kiến ngừng hỗ trợ.
5. Theo dõi traffic theo client, version và consumer.
6. Hỗ trợ consumer chuyển đổi và xác nhận contract test.
7. Ngừng nhận traffic version cũ sau khi đạt điều kiện đã công bố.
8. Loại bỏ code và mapping cũ sau khi không còn consumer hợp lệ.

### 11.1. Deprecation cần có thông tin cụ thể

Một thông báo deprecation nên nêu:

- API hoặc trường nào bị deprecated.
- Thay thế bằng endpoint, field hoặc version nào.
- Thay đổi semantics nếu có.
- Mốc thời gian ngừng hỗ trợ.
- Cách kiểm tra client còn sử dụng version cũ.
- Kênh liên hệ hoặc tài liệu migration.

Với HTTP API, có thể dùng header như `Deprecation`, `Sunset` hoặc đường dẫn tài liệu theo chính sách tổ chức nếu hạ tầng hỗ trợ. Không nên chỉ đổi tên trong tài liệu mà không thông báo cho consumer đang sử dụng.

### 11.2. Theo dõi usage trước khi xóa

Log hoặc metrics nên cho biết endpoint/version nào đang được gọi, client nào gọi và lỗi nào phát sinh. Tránh ghi dữ liệu nhạy cảm vào log chỉ để nhận diện consumer. Khi không còn traffic, vẫn cần kiểm tra batch job, đối tác hoặc client chạy định kỳ trước khi xóa version.

## 12. Thay đổi mô hình và database theo Expand–Migrate–Contract

Không chỉ API cần tiến hóa. Domain model và schema database cũng thay đổi theo thời gian. Một cách triển khai an toàn là **Expand–Migrate–Contract** (mở rộng, chuyển đổi, thu gọn), giúp các phiên bản ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

Ví dụ, database có cột `customer_name`, nhóm muốn thay bằng `buyer_display_name`.

### Giai đoạn 1: Expand

- Thêm cột mới `buyer_display_name`.
- Giữ cột cũ `customer_name`.
- Deploy code có thể đọc dữ liệu cũ và mới hoặc ghi đồng thời cả hai trong giai đoạn chuyển tiếp.
- Không xóa cột cũ khi instance ứng dụng cũ còn sử dụng.

### Giai đoạn 2: Migrate

- Backfill dữ liệu từ cột cũ sang cột mới.
- Kiểm tra số lượng, giá trị null và sai lệch.
- Chuyển dần code đọc sang cột mới.
- Theo dõi và xử lý các trường hợp ghi không đồng bộ.

### Giai đoạn 3: Contract

- Xác nhận mọi instance và job đã ngừng dùng cột cũ.
- Ngừng ghi cột cũ.
- Xóa cột cũ trong một lần triển khai riêng.
- Loại bỏ mapping và code chuyển tiếp sau khi an toàn.

```text
Old schema + old application
          |
          v
EXPAND: add new column, keep old column
          |
          v
MIGRATE: dual read/write, backfill, verify
          |
          v
Switch all consumers to new representation
          |
          v
CONTRACT: stop old writes, remove old column/code
```

### 12.1. Tại sao không đổi tên cột trực tiếp?

Nếu deploy code mới chỉ đọc cột mới nhưng một instance cũ vẫn chạy và ghi cột cũ, dữ liệu có thể không được cập nhật ở nơi code mới mong đợi. Trong rolling deployment, nhiều phiên bản ứng dụng có thể cùng tồn tại. Expand–Migrate–Contract tạo khoảng tương thích để chuyển dần.

### 12.2. Không phải mọi thay đổi đều cần dual write

Dual write có thể tạo thêm rủi ro nếu hai cột không được cập nhật nguyên tử hoặc có lỗi giữa hai lần ghi. Nếu có thể dùng view, generated column, trigger được quản lý rõ hoặc một chiến lược migration khác, hãy chọn cách ít rủi ro hơn. Dù chọn cách nào, cần có quy tắc xác định nguồn dữ liệu chính trong từng giai đoạn và cách kiểm tra sai lệch.

### 12.3. Domain model có thể đổi trong khi API giữ nguyên

Sau khi schema mới được triển khai, domain model có thể dùng `BuyerDisplayName` thay vì `customerName`. API mapper vẫn có thể trả `customerName` cho v1 và `buyerDisplayName` cho v2. Đây là lý do cần tách contract khỏi cấu trúc lưu trữ và mô hình nội bộ.

## 13. Contract testing và tài liệu API

Kiểm thử unit cho mapper không chứng minh toàn bộ provider tương thích với consumer. Cần kiểm tra contract ở ranh giới.

### 13.1. Provider contract test

Provider test xác nhận API thực tế trả đúng status code, header, schema, trường bắt buộc và semantics đã công bố. Có thể dùng OpenAPI validation hoặc test tích hợp gọi endpoint.

### 13.2. Consumer-driven contract test

Consumer-driven contract test ghi lại những giả định mà consumer thực sự sử dụng. Provider chạy kiểm thử để xác nhận thay đổi của mình không phá các consumer đã đăng ký contract.

Loại test này hữu ích khi nhiều team triển khai độc lập. Nó giúp phát hiện một thay đổi tưởng như additive nhưng thực tế phá deserializer hoặc assumptions của client.

### 13.3. Kiểm thử mapper theo từng version

Mapper v1 và v2 nên có test riêng cho:

- Trường bắt buộc và optional.
- Giá trị enum mới hoặc trạng thái không ánh xạ được.
- Null và absent.
- Đơn vị tiền tệ, thời gian và số thập phân.
- Dữ liệu nhạy cảm không được xuất hiện.
- Trạng thái domain mới được chuyển đổi theo chính sách công khai.

### 13.4. OpenAPI và ví dụ thực tế

OpenAPI có thể mô tả endpoint, request/response schema, authentication, error response và ví dụ. Tài liệu nên được cập nhật cùng code, được kiểm tra trong CI và có changelog cho thay đổi contract.

Không nên coi file OpenAPI là nguồn sự thật duy nhất nếu nó không được kiểm tra với implementation. Contract test giúp phát hiện tài liệu và code bị lệch nhau.

## 14. Quy tắc thiết kế DTO để dễ tiến hóa

Một số nguyên tắc giúp DTO ổn định hơn khi domain model thay đổi:

- **Dùng DTO riêng cho từng hướng.** Request và response thường có quyền và nhu cầu dữ liệu khác nhau.
- **Thiết kế theo use case hoặc resource contract.** Không serialize trực tiếp aggregate.
- **Chọn tên theo ngôn ngữ công khai.** Tên API có thể khác tên class hoặc field nội bộ.
- **Định nghĩa rõ optional, nullable và default.** Không để client tự suy đoán.
- **Định nghĩa đơn vị và format.** Tiền tệ, múi giờ, trọng lượng và số lượng cần semantics rõ.
- **Không phơi bày trường nội bộ.** Tránh `internalStatus`, database ID hoặc thông tin vận hành không thuộc contract.
- **Có chiến lược cho enum mở rộng.** Consumer cần xử lý giá trị chưa biết theo chính sách.
- **Giữ error contract ổn định.** Client nên dựa vào error code thay vì parse thông điệp tùy ý.
- **Không dùng một DTO khổng lồ cho mọi version.** Giữ adapter riêng và mapping rõ ràng.
- **Không version hóa chỉ vì release nội bộ.** Chỉ tạo version mới khi contract hoặc semantics cần thay đổi không tương thích.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Trả trực tiếp JPA entity hoặc aggregate | Client bị gắn với cấu trúc nội bộ và có thể thấy dữ liệu không mong muốn | Dùng response DTO riêng |
| Dùng cùng một DTO cho request và response | Client có thể gửi các trường chỉ server được phép quản lý | Tách DTO theo hướng và use case |
| Đổi domain model rồi đổi API theo ngay | Thay đổi nội bộ trở thành breaking change không cần thiết | Dùng mapper giữ contract ổn định |
| Cho rằng thêm trường luôn tương thích | Client strict hoặc server cũ có thể từ chối trường lạ | Kiểm tra cách parse và hỗ trợ của consumer/provider |
| Đổi semantics nhưng giữ nguyên tên trường | Client hiểu sai dữ liệu mà không có lỗi parse | Xem semantics là một phần của contract |
| Tạo version mới cho mọi lần deploy | Quá nhiều version và chi phí vận hành | Version hóa theo thay đổi contract không tương thích |
| Dùng một DTO với nhiều trường nullable cho mọi version | Nhiều tổ hợp trạng thái không hợp lệ và khó kiểm thử | Tạo DTO/adapter riêng cho từng contract cần hỗ trợ |
| Xóa version cũ ngay sau khi deploy version mới | Consumer chưa nâng cấp bị gián đoạn | Deprecation, đo usage và migration có thời hạn |
| Đổi schema database trong một bước khi rolling deploy | Instance cũ và mới không tương thích | Dùng Expand–Migrate–Contract |
| Dùng dual write không kiểm soát | Hai biểu diễn dữ liệu bị lệch | Xác định nguồn chính, transaction và kiểm tra backfill |
| Chỉ test mapper, không test contract | API thực tế có thể lệch OpenAPI hoặc assumptions consumer | Provider/consumer contract test |
| Ánh xạ trạng thái domain mới sang giá trị cũ một cách tùy tiện | Client nhận semantics sai | Định nghĩa mapping, fallback hoặc version mới rõ ràng |

## 16. Quy trình quản lý một thay đổi API

Khi cần thay đổi API hoặc domain model, nhóm có thể thực hiện theo trình tự sau.

### Bước 1: Xác định mục tiêu thay đổi

Làm rõ thay đổi xuất phát từ nghiệp vụ, mô hình nội bộ, bảo mật, hiệu năng hay nhu cầu consumer. Xác định bounded context sở hữu dữ liệu và use case liên quan.

### Bước 2: Xác định phạm vi contract bị ảnh hưởng

Liệt kê endpoint, request, response, error code, enum, event hoặc schema mà consumer đang dùng. Kiểm tra cả các hành vi không thể hiện trong JSON schema như thứ tự, tính idempotent và semantics trạng thái.

### Bước 3: Phân loại compatibility

Đánh giá thay đổi từ góc nhìn client cũ với server mới và, nếu cần, client mới với server cũ. Kiểm tra trường optional/required, unknown field, enum, nullability, format và validation.

### Bước 4: Chọn cách tiến hóa

Nếu tương thích, giữ version và bổ sung theo quy tắc rõ. Nếu không tương thích, chọn version mới hoặc một giai đoạn chuyển đổi tương đương. Không tạo version chỉ vì thay đổi nội bộ.

### Bước 5: Thiết kế DTO và mapping

Tạo request/response DTO phù hợp. Ánh xạ sang command/query/domain model. Xác định cách biểu diễn trạng thái mới, snapshot, default và lỗi.

### Bước 6: Triển khai song song khi cần

Giữ adapter cũ và mới cùng hoạt động. Chia sẻ use case/domain model nếu semantics giống nhau; tách logic khi nghiệp vụ thực sự khác.

### Bước 7: Migration dữ liệu và ứng dụng

Nếu schema nội bộ thay đổi, dùng Expand–Migrate–Contract hoặc kế hoạch tương thích tương đương. Kiểm tra rolling deployment và job nền.

### Bước 8: Kiểm thử contract

Chạy unit test mapper, provider contract test, consumer-driven contract test và integration test cho các luồng quan trọng. Kiểm tra cả client strict và dữ liệu cũ.

### Bước 9: Deprecate và theo dõi

Thông báo version cũ, cung cấp tài liệu migration, theo dõi usage và lỗi. Chỉ ngừng hỗ trợ khi đã đạt điều kiện công bố và xử lý các consumer còn lại.

### Bước 10: Dọn code chuyển tiếp

Sau khi version cũ không còn được sử dụng, loại bỏ controller, DTO, mapper và schema cũ theo kế hoạch. Ghi lại quyết định contract để các thay đổi sau có cơ sở.

## 17. Nguyên tắc thực hành

Khi quản lý phiên bản API và thay đổi mô hình bên trong, nhóm nên nhớ:

- **Giữ ranh giới domain/API.** Domain model bảo vệ nghiệp vụ; DTO thể hiện hợp đồng giao tiếp.
- **Đánh giá thay đổi từ góc nhìn consumer.** Mã nguồn server compile thành công không chứng minh client vẫn hoạt động.
- **Phân biệt cấu trúc với semantics.** Cùng JSON schema nhưng đổi ý nghĩa vẫn là thay đổi contract.
- **Dùng mapper có chủ đích.** Mapping là ranh giới chuyển đổi, không phải nơi thay thế domain rule.
- **Tách request và response.** Client chỉ gửi những trường use case cho phép.
- **Không version hóa mọi thay đổi nội bộ.** Version phản ánh contract công khai.
- **Quản lý nhiều version ở adapter.** Dùng DTO và mapper riêng nhưng có thể chia sẻ use case/domain model.
- **Định nghĩa rõ null, absent, enum và đơn vị.** Đây là các nguồn breaking change thường bị bỏ sót.
- **Triển khai thay đổi dữ liệu theo giai đoạn.** Expand–Migrate–Contract hỗ trợ rolling deployment.
- **Kiểm thử hợp đồng với consumer.** OpenAPI, provider test và consumer-driven contract test bổ trợ nhau.
- **Deprecate có thời hạn và đo usage.** Không loại bỏ version cũ khi chưa hiểu ai còn sử dụng.
- **Giữ lịch sử và khả năng giải thích.** Với dữ liệu giao dịch, không để đổi model làm thay đổi cách diễn giải dữ liệu đã phát sinh.

API contract cần ổn định đủ lâu để consumer có thể phát triển độc lập, trong khi domain model cần tự do thay đổi để phản ánh hiểu biết nghiệp vụ mới. DTO và mapper tạo ranh giới giữa hai nhu cầu. Khi nhóm phân loại chính xác thay đổi tương thích, version hóa những thay đổi thật sự phá contract, triển khai migration theo giai đoạn và kiểm thử với consumer, hệ thống có thể tiến hóa mà không buộc mọi thành phần phải nâng cấp cùng một thời điểm.

## 18. Câu hỏi tự kiểm tra

1. Vì sao domain model và API contract không nên bị xem là cùng một mô hình?
2. DTO giúp bảo vệ aggregate khỏi những thay đổi và rủi ro nào?
3. Phân biệt request DTO, response DTO và domain object bằng ví dụ tạo đơn hàng.
4. Thay đổi nào bên trong domain model có thể được che giấu sau mapping mà không cần tăng API version?
5. Trong ngữ cảnh provider cập nhật server, thế nào là thay đổi tương thích với client cũ?
6. Vì sao thêm response field hoặc enum value chưa chắc là thay đổi an toàn?
7. Phân biệt absent, null và empty; vì sao điều này quan trọng với PATCH?
8. So sánh version trong URL, header/media type và schema/message type.
9. Làm thế nào để hỗ trợ API v1 và v2 mà không nhân đôi toàn bộ domain model?
10. Expand–Migrate–Contract giải quyết vấn đề gì khi nhiều phiên bản ứng dụng cùng chạy trong rolling deployment?
11. Provider contract test và consumer-driven contract test bổ sung cho nhau như thế nào?
12. Hãy chọn một thay đổi API thực tế, phân loại compatibility, xác định DTO/mapper cần cập nhật, lộ trình version/deprecation và các kiểm thử cần có.
