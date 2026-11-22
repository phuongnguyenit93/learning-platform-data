# Ánh xạ yêu cầu bên ngoài sang ý định nghiệp vụ

Trong Domain-Driven Design (DDD), API là ranh giới giao tiếp giữa hệ thống với client, đối tác hoặc một thành phần bên ngoài. Dữ liệu gửi đến qua HTTP thường được thiết kế theo nhu cầu của giao thức: JSON field, path parameter, query parameter, header và mã trạng thái. Domain Model lại diễn đạt ngôn ngữ nghiệp vụ: xác nhận đơn hàng, đổi địa chỉ giao, giữ chỗ tồn kho hoặc đăng ký thành viên.

**Ánh xạ yêu cầu bên ngoài sang ý định nghiệp vụ** là quá trình chuyển dữ liệu ở ranh giới API thành một Command hoặc Query có ý nghĩa trong Application Layer. Quá trình này cần làm rõ client đang muốn thực hiện hành động gì, dữ liệu nào là đầu vào, dữ liệu nào đến từ danh tính đã xác thực, và quy tắc nào thuộc trách nhiệm của domain.

Một API request không nên được chuyển nguyên xi thành Entity hoặc Aggregate. DTO mô tả hợp đồng giao tiếp; Command mô tả ý định mà ứng dụng cần thực hiện; Aggregate bảo vệ quy tắc nghiệp vụ khi ý định đó được thực thi. Giữ rõ các vai trò này giúp API có thể thay đổi mà không làm domain model bị chi phối bởi cấu trúc JSON hoặc framework web.

## 1. Từ HTTP request đến hành vi nghiệp vụ

Một request đi qua nhiều lớp trước khi tạo ra thay đổi trong domain:

    HTTP request
        |
        v
    Interface / API Adapter
        |
        | parse, deserialize, validate transport shape
        v
    Request DTO
        |
        | map data + authenticated context
        v
    Application Command
        |
        | invoke use case
        v
    Application Handler
        |
        | load Aggregate, call domain behavior
        v
    Domain Model
        |
        | result / domain events
        v
    Application Result
        |
        | map to response DTO
        v
    HTTP response

Mỗi bước có một nhiệm vụ:

- **HTTP request:** mang dữ liệu theo giao thức và hợp đồng API.
- **Request DTO:** biểu diễn cấu trúc dữ liệu bên ngoài sau khi deserialize.
- **Command:** biểu diễn ý định thực hiện một hành động nghiệp vụ.
- **Application Handler:** điều phối use case và các dependency cần thiết.
- **Domain Model:** kiểm tra và thực thi quy tắc nghiệp vụ.
- **Response DTO:** biểu diễn dữ liệu được phép trả ra ngoài theo hợp đồng API.

Ví dụ, client gửi yêu cầu xác nhận đơn hàng:

    POST /api/orders/ORD-123/confirmation

    {
      "confirmationNote": "Khách đã xác nhận địa chỉ",
      "expectedVersion": 7
    }

Request DTO có thể mang confirmationNote và expectedVersion. Adapter lấy OrderId từ path, lấy người thực hiện từ security context, rồi tạo command:

    ConfirmOrderCommand(
        orderId = ORD-123,
        actorId = USER-42,
        note = "Khách đã xác nhận địa chỉ",
        expectedVersion = 7
    )

Command thể hiện rõ hành động cần thực hiện và dữ liệu cần cho use case. Handler sẽ nạp Order, kiểm tra quyền và version theo chính sách, gọi order.confirm(...), sau đó lưu kết quả.

Client không được gửi trạng thái mới như CONFIRMED rồi yêu cầu server gán thẳng vào Aggregate. Client gửi ý định; domain quyết định trạng thái có thể chuyển đổi hay không.

## 2. Phân biệt Request DTO, Command và Domain Model

Ba khái niệm này thường có dữ liệu giống nhau một phần, nhưng phục vụ các mục đích khác nhau.

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Request DTO | Mô tả payload của API | ConfirmOrderRequest |
| Command | Diễn đạt ý định của use case | ConfirmOrderCommand |
| Domain Entity/Aggregate | Giữ state và bảo vệ hành vi nghiệp vụ | Order |
| Value Object | Biểu diễn giá trị miền có quy tắc | OrderId, Money, DeliveryAddress |
| Response DTO | Mô tả dữ liệu trả về client | OrderConfirmationResponse |

### Request DTO thuộc ranh giới giao tiếp

DTO có thể thay đổi theo phiên bản API hoặc theo client. Ví dụ một API có thể dùng tên field deliveryAddress, trong khi domain model dùng ShippingAddress. Một API khác có thể gửi provinceCode và wardCode; domain lại cần một Address Value Object đã được chuẩn hóa.

DTO có thể có:

- Field name theo quy ước JSON.
- Kiểu dữ liệu thuận tiện cho serialization.
- Annotation validation của framework.
- Field chỉ dành cho tương thích ngược.
- Cấu trúc lồng nhau phù hợp với trải nghiệm client.

Không nên để những chi tiết này trở thành cấu trúc bắt buộc của domain.

### Command thuộc Application Layer

Command thể hiện một yêu cầu thực hiện use case. Nó thường bất biến và chỉ chứa dữ liệu cần thiết để handler điều phối hành động.

Ví dụ:

    public record ChangeDeliveryAddressCommand(
            OrderId orderId,
            CustomerId customerId,
            DeliveryAddress newAddress,
            long expectedVersion
    ) {}

Command không nhất thiết phải giống Request DTO. Command có thể dùng kiểu miền như OrderId và DeliveryAddress thay vì String và nested JSON object. Nó cũng có thể chứa actor hoặc tenant đã được xác thực từ security context.

### Domain Model không nhận DTO làm tham số

Một thiết kế dễ gây phụ thuộc là:

    order.updateFrom(requestDto);

Cách này khiến Aggregate biết về API contract và có thể vô tình cho phép client quyết định field nào được cập nhật. Thay vào đó, application mapper chuyển DTO thành command và các kiểu miền; handler gọi hành vi có tên nghiệp vụ:

    order.changeDeliveryAddress(newAddress);

Domain model nhận ý định và dữ liệu đã được chuyển về ngôn ngữ miền.

## 3. Xác định ý định thay vì ánh xạ từng field máy móc

Một lỗi phổ biến là xem API mapping như việc sao chép mọi field từ request sang entity:

    request.id        -> entity.id
    request.status    -> entity.status
    request.total     -> entity.total
    request.createdAt -> entity.createdAt

Cách này biến API thành công cụ sửa trực tiếp state và có thể cho phép client thay đổi những dữ liệu chỉ server hoặc domain được quyền quyết định.

Hãy bắt đầu bằng câu hỏi: **Client đang yêu cầu nghiệp vụ nào?**

Ví dụ:

| Request bên ngoài | Ý định nghiệp vụ | Hành vi domain phù hợp |
|---|---|---|
| POST /orders | Đặt một đơn hàng | Order.place(...) |
| POST /orders/{id}/confirmation | Xác nhận đơn | order.confirm(...) |
| POST /orders/{id}/cancellation | Hủy đơn | order.cancel(reason) |
| PUT /orders/{id}/delivery-address | Đổi địa chỉ giao | order.changeDeliveryAddress(address) |
| POST /inventory/{id}/reservations | Giữ một số lượng hàng | inventory.reserve(quantity) |
| POST /memberships | Đăng ký thành viên | Membership.register(...) |

HTTP method và URL là cách biểu diễn hành động ở giao thức. Command name nên phản ánh use case bằng ngôn ngữ nghiệp vụ. Không phải lúc nào một endpoint cũng tương ứng một method domain, nhưng mapping cần có ý nghĩa rõ ràng.

## 4. Thiết kế Request DTO theo hợp đồng API

Request DTO nên phản ánh dữ liệu mà client được phép gửi. Ví dụ:

~~~json
{
  "items": [
    {
      "productId": "PRD-100",
      "quantity": 2
    },
    {
      "productId": "PRD-205",
      "quantity": 1
    }
  ],
  "deliveryAddress": {
    "line1": "12 Nguyễn Huệ",
    "wardCode": "W-01",
    "cityCode": "HCM"
  },
  "customerNote": "Gọi trước khi giao"
}
~~~

Một DTO Java có thể là:

    public record PlaceOrderRequest(
            @NotEmpty List<@Valid PlaceOrderLineRequest> items,
            @NotNull @Valid DeliveryAddressRequest deliveryAddress,
            @Size(max = 500) String customerNote
    ) {}

    public record PlaceOrderLineRequest(
            @NotBlank String productId,
            @Positive int quantity
    ) {}

    public record DeliveryAddressRequest(
            @NotBlank String line1,
            @NotBlank String wardCode,
            @NotBlank String cityCode
    ) {}

Các annotation như NotEmpty, Positive và Size giúp kiểm tra hình dạng và ràng buộc đầu vào ở API boundary. Chúng không thay thế quy tắc domain như sản phẩm có được bán hay không, địa chỉ có phục vụ được không hoặc số lượng có vượt giới hạn đặt hàng không.

DTO nên tránh chứa những field client không được phép quyết định, ví dụ:

- orderStatus
- approvedBy
- createdAt
- totalAmount
- paymentState
- internalRiskScore

Những giá trị này được domain hoặc server tính toán, lấy từ identity đã xác thực, hoặc cập nhật qua use case riêng.

## 5. Chuyển kiểu dữ liệu thô thành Value Object

API thường nhận dữ liệu ở dạng String, number hoặc nested object. Domain Model nên dùng kiểu miền để biểu diễn giá trị có ý nghĩa và quy tắc riêng.

Ví dụ, productId từ JSON là String nhưng domain có thể dùng ProductId:

    public record ProductId(String value) {
        public ProductId {
            if (value == null || value.isBlank()) {
                throw new InvalidProductId();
            }
        }
    }

Quantity từ request là int nhưng domain có thể dùng Value Object:

    public record Quantity(int value) {
        public Quantity {
            if (value <= 0) {
                throw new InvalidQuantity(value);
            }
        }
    }

Money có thể gồm amount và currency thay vì dùng một số decimal đơn lẻ:

    public record Money(BigDecimal amount, Currency currency) {
        public Money {
            Objects.requireNonNull(amount);
            Objects.requireNonNull(currency);

            if (amount.signum() < 0) {
                throw new InvalidMoneyAmount();
            }
        }
    }

Mapper chuyển đổi kiểu dữ liệu:

    ProductId productId = new ProductId(request.productId());
    Quantity quantity = new Quantity(request.quantity());

Lợi ích:

- Kiểu dữ liệu thể hiện rõ ngữ nghĩa.
- Tránh truyền nhầm các ID có cùng representation.
- Quy tắc cấu trúc được tập trung tại Value Object.
- Domain method không cần lặp lại kiểm tra cơ bản.
- API có thể đổi representation mà domain không cần đổi theo.

Không nên biến mọi String thành một Value Object nếu không có ngữ nghĩa hoặc quy tắc cần bảo vệ. Hãy tạo kiểu miền cho những khái niệm quan trọng hoặc dễ bị dùng nhầm.

## 6. Mapping nested DTO thành cấu trúc domain

Một request có thể chứa danh sách item hoặc object lồng nhau. Mapper cần chuyển từng phần tử thành kiểu miền và tạo command phù hợp.

Ví dụ:

    public record PlaceOrderLineCommand(
            ProductId productId,
            Quantity quantity
    ) {}

    public record PlaceOrderCommand(
            CustomerId customerId,
            List<PlaceOrderLineCommand> lines,
            DeliveryAddress deliveryAddress,
            CustomerNote customerNote
    ) {}

    public final class PlaceOrderMapper {
        public PlaceOrderCommand toCommand(
                PlaceOrderRequest request,
                CustomerId authenticatedCustomerId
        ) {
            List<PlaceOrderLineCommand> lines =
                    request.items().stream()
                            .map(item -> new PlaceOrderLineCommand(
                                    new ProductId(item.productId()),
                                    new Quantity(item.quantity())
                            ))
                            .toList();

            DeliveryAddress address = new DeliveryAddress(
                    request.deliveryAddress().line1(),
                    new WardCode(request.deliveryAddress().wardCode()),
                    new CityCode(request.deliveryAddress().cityCode())
            );

            return new PlaceOrderCommand(
                    authenticatedCustomerId,
                    lines,
                    address,
                    CustomerNote.of(request.customerNote())
            );
        }
    }

Trong ví dụ, CustomerId được lấy từ danh tính đã xác thực thay vì tin một customerId tùy ý trong body. Điều này ngăn client gửi ID của người khác để tạo đơn dưới danh nghĩa họ.

Nếu use case cho phép nhân viên đặt đơn thay khách hàng, actor và customer cần được biểu diễn riêng. Application cần xác thực quyền thực hiện hành động đó.

## 7. Validation ở nhiều lớp có trách nhiệm khác nhau

Validation không phải một bước duy nhất. Cần phân biệt kiểm tra giao thức, cấu trúc dữ liệu, quy tắc giá trị và quy tắc nghiệp vụ.

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Transport / parsing | JSON hợp lệ, content type, kiểu field | API adapter/framework |
| Structural validation | Field bắt buộc, chuỗi không rỗng, độ dài tối đa | Request DTO / boundary |
| Value Object validation | Quantity dương, email có cấu trúc hợp lệ | Value Object |
| Use case validation | Actor có quyền chạy use case, tài nguyên tồn tại | Application Layer |
| Domain rule | Đơn đã giao không thể hủy; sản phẩm đang bán mới được đặt | Aggregate / Domain Service |
| Persistence constraint | Unique key, foreign key, version | Infrastructure/database |

### Boundary validation không thay thế domain validation

Client có thể bỏ qua validation JavaScript và gửi request trực tiếp. Vì vậy server phải kiểm tra dữ liệu.

Tuy nhiên, ngay cả khi DTO hợp lệ, domain vẫn có thể từ chối. Ví dụ quantity là số dương nhưng sản phẩm chỉ còn 2 đơn vị, trong khi request muốn 10. Đây là kết quả nghiệp vụ, không phải lỗi cấu trúc JSON.

### Không đưa mọi lỗi vào HTTP 400

Một request sai định dạng có thể trả 400 Bad Request. Nhưng một hành động không hợp lệ theo trạng thái hiện tại có thể cần mã phản hồi khác tùy hợp đồng API, ví dụ 409 Conflict hoặc 422 Unprocessable Content.

Điều quan trọng là giữ rõ loại lỗi bên trong Application/Domain rồi ánh xạ ra HTTP tại adapter.

## 8. Lấy dữ liệu từ security context, không tin body

Một request có thể cần thông tin về người thực hiện:

- Actor ID.
- Customer ID.
- Tenant ID.
- Role hoặc scope.
- Correlation ID.
- Locale hoặc timezone theo ngữ cảnh.

Không phải mọi giá trị này đều nên đến từ JSON body. Thông tin định danh và quyền thường phải lấy từ security context đã xác thực.

Ví dụ:

    @PostMapping("/orders")
    public ResponseEntity<OrderResponse> place(
            @Valid @RequestBody PlaceOrderRequest request,
            Authentication authentication
    ) {
        ActorId actorId = actorResolver.from(authentication);
        CustomerId customerId = customerResolver.customerFor(actorId);

        PlaceOrderCommand command =
                mapper.toCommand(request, customerId);

        PlaceOrderResult result = handler.handle(command);

        return ResponseEntity.status(201)
                .body(responseMapper.toResponse(result));
    }

Ví dụ minh họa cách lấy actor. Trong hệ thống thật, cần phân biệt người đăng nhập, khách hàng sở hữu dữ liệu và người được ủy quyền thao tác. Chỉ biết actor đã xác thực không có nghĩa actor được phép thực hiện mọi hành động trên mọi Aggregate.

Application layer cần thực hiện authorization theo resource và use case. Domain có thể bảo vệ một số quy tắc quyền hạn mang ý nghĩa nghiệp vụ, nhưng không nên để DTO tự quyết định quyền.

## 9. Phân biệt dữ liệu client cung cấp và dữ liệu server quyết định

Một API request thường trộn các field mà client được phép chọn với những field server phải tính hoặc xác định.

Ví dụ đặt hàng:

| Dữ liệu | Nguồn có thẩm quyền |
|---|---|
| Product ID và quantity | Client gửi, server kiểm tra |
| Customer ID | Security context hoặc quyền đại diện đã xác thực |
| Unit price | Pricing domain/service có thẩm quyền |
| Discount amount | Promotion policy |
| Order total | Domain/application tính từ dữ liệu đã xác thực |
| Order status | Hành vi domain quyết định |
| CreatedAt | Clock do ứng dụng cung cấp |
| Aggregate version | Persistence/concurrency mechanism |
| Actor ID | Security context |

Không nên nhận totalAmount từ client rồi lưu trực tiếp. Client có thể gửi giá tham khảo để hiển thị, nhưng server phải tính lại từ nguồn giá có thẩm quyền.

Tương tự, không nên nhận status rồi gán thẳng vào entity. Muốn xác nhận đơn, client gửi command xác nhận; domain kiểm tra điều kiện và tự chuyển trạng thái.

## 10. Mapping dữ liệu thời gian, tiền tệ và đơn vị

Một số kiểu dữ liệu có ý nghĩa phụ thuộc ngữ cảnh:

### Thời gian

API có thể nhận ISO-8601 timestamp hoặc local date. Cần phân biệt:

- Instant: một thời điểm tuyệt đối trên timeline.
- LocalDate: ngày lịch không có timezone.
- LocalDateTime: ngày giờ địa phương chưa gắn timezone.
- ZonedDateTime: ngày giờ có zone.
- Duration: khoảng thời gian.

Không nên tự chuyển LocalDate thành Instant nếu chưa xác định timezone nghiệp vụ. Ví dụ ngày hết hạn hợp đồng theo lịch địa phương có thể không tương đương thời điểm UTC lúc 00:00.

### Tiền tệ

Nếu API nhận amount và currency, mapper nên tạo Money Value Object. Domain cần xác định rounding, scale, currency compatibility và quy tắc cộng trừ.

Không nên dùng double cho tiền vì sai số biểu diễn nhị phân có thể làm lệch kết quả.

### Đơn vị đo

Nếu client gửi trọng lượng hoặc kích thước, hãy xác định đơn vị và chuẩn hóa ở boundary hoặc Value Object. Không được coi 5 là cùng ý nghĩa nếu một client gửi kilogram còn client khác gửi gram.

## 11. PUT, PATCH và ý nghĩa của field bị thiếu

Mapping request update cần phân biệt ba tình huống:

1. Field không xuất hiện: client không yêu cầu thay đổi field đó.
2. Field xuất hiện với null: client muốn xóa giá trị hoặc biểu diễn giá trị không có, tùy hợp đồng.
3. Field xuất hiện với giá trị: client muốn thay đổi sang giá trị đó.

Nếu DTO dùng một field nullable thông thường, Java có thể không phân biệt field bị bỏ qua với field được gửi null sau deserialize.

Ví dụ PATCH:

~~~json
{
  "customerNote": null
}
~~~

Có thể mang ý nghĩa xóa ghi chú, trong khi request không có customerNote nghĩa là giữ nguyên. API cần định nghĩa rõ semantics.

Các lựa chọn triển khai:

- Dùng JSON Merge Patch hoặc JSON Patch với semantics chuẩn.
- Dùng wrapper biểu diễn trạng thái absent/present/null.
- Tạo request riêng cho từng hành động cụ thể.
- Dùng command như ClearCustomerNote hoặc ChangeDeliveryAddress thay cho một PATCH tổng quát.

Với nghiệp vụ quan trọng, command tường minh thường dễ hiểu và dễ bảo vệ hơn một DTO cho phép cập nhật mọi field.

## 12. Mapping không nên biến thành mass assignment

Mass assignment xảy ra khi hệ thống tự động bind mọi field request vào object persistence/domain mà không kiểm soát field nào được phép thay đổi.

Ví dụ nguy hiểm:

    BeanUtils.copyProperties(request, order);

Nếu request chứa status, approved, total hoặc customerId, các field đó có thể bị ghi đè ngoài ý muốn. Ngay cả khi DTO hiện tại không chứa chúng, việc thêm field mới sau này có thể vô tình mở rộng quyền ghi.

Cách an toàn hơn là mapping tường minh:

    ChangeCustomerNoteCommand command =
            new ChangeCustomerNoteCommand(
                    orderId,
                    CustomerNote.of(request.customerNote())
            );

    order.changeCustomerNote(command.note());

Chỉ những dữ liệu thuộc ý định của use case mới được đưa vào command. Domain method quyết định field nào có thể thay đổi và trong trạng thái nào.

## 13. Phiên bản API và chống phụ thuộc ngược

API có thể phát triển theo thời gian. Client cũ có thể gửi field cũ, client mới gửi field mới hoặc một field được đổi tên.

Không nên để API version quyết định cấu trúc Domain Model. Thay vào đó:

    API v1 DTO ----\
                    +--> Application Command --> Domain Model
    API v2 DTO ----/

Hai DTO khác nhau có thể được ánh xạ về cùng một command nếu ý nghĩa nghiệp vụ giống nhau.

Ví dụ:

- API v1 gửi provinceName.
- API v2 gửi provinceCode.
- Application mapper của từng phiên bản chuẩn hóa về DeliveryAddress theo mô hình miền hiện tại.

Nếu semantics khác nhau, có thể cần command hoặc use case riêng. Không nên ép hai payload có ý nghĩa khác nhau vào một command chỉ để giảm số class.

### Tương thích ngược

Khi đổi API contract:

- Giữ field cũ trong giai đoạn deprecation nếu cần.
- Xác định precedence khi client gửi cả field cũ và mới.
- Không âm thầm đổi ý nghĩa field.
- Chuẩn hóa dữ liệu trước khi tạo command.
- Ghi rõ version và lỗi validation theo hợp đồng.
- Kiểm thử mapping của từng API version.

DTO là biên chống thay đổi giữa giao thức bên ngoài và mô hình bên trong. Một API thay đổi không nhất thiết phải làm domain thay đổi.

## 14. Ánh xạ kết quả nghiệp vụ sang HTTP response

Mapping không chỉ diễn ra theo chiều request vào. Kết quả từ Application Layer cũng cần được chuyển thành response DTO.

Ví dụ:

    public record PlaceOrderResult(
            OrderId orderId,
            OrderStatus status,
            Instant placedAt
    ) {}

    public record PlaceOrderResponse(
            String orderId,
            String status,
            Instant placedAt
    ) {}

    public final class PlaceOrderResponseMapper {
        public PlaceOrderResponse toResponse(PlaceOrderResult result) {
            return new PlaceOrderResponse(
                    result.orderId().value(),
                    result.status().name(),
                    result.placedAt()
            );
        }
    }

Không nên trả trực tiếp Aggregate hoặc ORM entity ra HTTP. Việc đó có thể làm lộ:

- Field nội bộ chưa được phép công khai.
- Quan hệ object graph và lazy-loading behavior.
- Cấu trúc persistence.
- Domain Event collection.
- Trạng thái chưa phù hợp với API contract.
- Dữ liệu nhạy cảm hoặc thông tin thuộc context khác.

Response DTO nên chỉ chứa dữ liệu cần thiết cho client. Nếu API cần một view tổng hợp từ nhiều Aggregate, query service có thể tạo read model riêng.

## 15. Ánh xạ lỗi từ domain/application sang HTTP

Domain và Application không nên phụ thuộc vào HTTP status code. Domain có thể trả hoặc ném lỗi có ý nghĩa nghiệp vụ; API adapter ánh xạ các lỗi đó thành response theo hợp đồng.

| Lỗi bên trong | Ví dụ | HTTP có thể dùng |
|---|---|---|
| Request parse/shape error | JSON sai, field bắt buộc thiếu | 400 |
| Authentication failure | Chưa xác thực | 401 |
| Authorization failure | Không có quyền thao tác | 403 |
| Resource not found | Order không tồn tại hoặc không được phép hiển thị | 404 |
| Business state conflict | Đơn đã giao nên không thể hủy | 409 |
| Validation/domain input error | Quantity không hợp lệ | 400 hoặc 422 theo API contract |
| Optimistic concurrency conflict | Version đã thay đổi | 409 |
| Rate limit | Gửi quá nhiều request | 429 |
| Unexpected infrastructure failure | Database hoặc dependency lỗi | 5xx |

Bảng này là gợi ý, không phải ánh xạ bắt buộc cho mọi API. Cần giữ hợp đồng nhất quán và tránh tiết lộ thông tin nhạy cảm.

Một response lỗi có thể dùng Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Không thể hủy đơn hàng",
  "status": 409,
  "detail": "Đơn hàng đã được giao.",
  "code": "ORDER_CANNOT_BE_CANCELLED"
}
~~~

Mã lỗi ổn định giúp client xử lý theo chương trình. Message có thể được bản địa hóa và không nên chứa stack trace hoặc chi tiết nội bộ.

## 16. Mapping và idempotency

Một request có thể được gửi lại vì client timeout hoặc không nhận được response. Nếu use case tạo đơn hoặc giữ hàng, request lặp có thể tạo nghiệp vụ trùng.

API có thể nhận Idempotency-Key trong header:

    POST /api/orders
    Idempotency-Key: 8c8a...

Adapter chuyển key vào command hoặc metadata của use case. Application xử lý key theo phạm vi actor/tenant và use case, lưu kết quả để request lặp có thể nhận lại cùng outcome.

Không nên để idempotency key trở thành một field domain của Order nếu nó chỉ phục vụ giao thức/API. Có thể lưu trong application persistence hoặc bảng request deduplication riêng.

Nếu key có ý nghĩa nghiệp vụ lâu dài hoặc là một phần của yêu cầu đối soát, cần xác định rõ ownership và vòng đời của nó.

## 17. Mapping và optimistic concurrency

Client có thể đọc một tài nguyên ở version 7 rồi gửi yêu cầu thay đổi sau khi một người khác đã cập nhật version 8.

API có thể dùng:

- Version field trong request.
- ETag và If-Match header.
- Một token concurrency do server phát.

Ví dụ:

    PATCH /api/orders/ORD-123
    If-Match: "7"

Adapter chuyển expected version vào command. Application/repository kiểm tra khi lưu. Nếu version không còn khớp, use case trả conflict thay vì ghi đè thay đổi mới.

Sau conflict, không nên dùng lại Aggregate cũ hoặc chỉ thay version. Nếu chính sách cho phép retry tự động, cần nạp lại Aggregate và đánh giá lại ý định nghiệp vụ trên state mới. Với thao tác cần người dùng xác nhận nội dung đã thay đổi, hãy trả conflict để client tải lại và quyết định.

## 18. Bảo vệ ranh giới giữa các Bounded Context

Cùng một khái niệm có thể có representation khác nhau trong các bounded context. Ví dụ Customer trong Sales có thông tin phục vụ bán hàng, Customer trong Billing có thông tin hóa đơn, còn Customer trong Shipping có thông tin người nhận.

Không nên dùng một DTO hoặc Entity chung cho tất cả context chỉ vì chúng cùng có customerId.

API adapter hoặc Anti-Corruption Layer có thể chuyển dữ liệu từ hệ thống bên ngoài sang mô hình của context hiện tại:

    External Partner Payload
              |
              v
    Partner Adapter / ACL
              |
              v
    Context-specific Command
              |
              v
    Local Domain Model

Ví dụ đối tác vận chuyển gửi trạng thái DELIVERED. Shipping context có thể ánh xạ nó thành ShipmentDelivered sau khi kiểm tra mã vận đơn và tính hợp lệ của chuyển trạng thái. Order context nhận một integration event đã được chuẩn hóa, không cần phụ thuộc payload riêng của đối tác.

Mapping là nơi chuyển ngữ giữa các mô hình. Không nên để external enum, field name hoặc status code lan sâu vào domain.

## 19. Ví dụ end-to-end: đổi địa chỉ giao hàng

Giả sử client gửi:

~~~json
{
  "line1": "12 Nguyễn Huệ",
  "wardCode": "W-01",
  "cityCode": "HCM"
}
~~~

API DTO:

    public record ChangeDeliveryAddressRequest(
            @NotBlank String line1,
            @NotBlank String wardCode,
            @NotBlank String cityCode
    ) {}

Command:

    public record ChangeDeliveryAddressCommand(
            OrderId orderId,
            CustomerId customerId,
            DeliveryAddress address,
            long expectedVersion
    ) {}

Mapper:

    public ChangeDeliveryAddressCommand toCommand(
            OrderId orderId,
            ChangeDeliveryAddressRequest request,
            CustomerId authenticatedCustomer,
            long expectedVersion
    ) {
        DeliveryAddress address = new DeliveryAddress(
                AddressLine.of(request.line1()),
                new WardCode(request.wardCode()),
                new CityCode(request.cityCode())
        );

        return new ChangeDeliveryAddressCommand(
                orderId,
                authenticatedCustomer,
                address,
                expectedVersion
        );
    }

Handler:

    public ChangeDeliveryAddressResult handle(
            ChangeDeliveryAddressCommand command
    ) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(OrderNotFoundException::new);

        authorization.checkCanChangeAddress(
                command.customerId(),
                order
        );

        order.changeDeliveryAddress(command.address());

        orders.save(order, command.expectedVersion());

        return ChangeDeliveryAddressResult.changed(
                order.id(),
                order.version()
        );
    }

Domain behavior:

    public void changeDeliveryAddress(DeliveryAddress address) {
        if (status == OrderStatus.SHIPPED
                || status == OrderStatus.DELIVERED
                || status == OrderStatus.CANCELLED) {
            throw new DeliveryAddressCannotBeChanged();
        }

        this.deliveryAddress = Objects.requireNonNull(address);
    }

Mỗi lớp có một trách nhiệm:

- API DTO kiểm tra cấu trúc payload.
- Mapper tạo Value Object và Command.
- Security context cung cấp customer/actor đã xác thực.
- Handler điều phối authorization, concurrency, repository và transaction.
- Aggregate kiểm tra trạng thái và thay đổi địa chỉ.
- Response mapper chuyển kết quả về hợp đồng API.

Ví dụ rút gọn; OrderRepository cần triển khai save có expectedVersion bằng conditional write hoặc ORM optimistic locking. Việc kiểm tra version phải được bảo vệ tại thời điểm ghi trong cùng transaction; chỉ so sánh hai giá trị trong bộ nhớ trước khi lưu không ngăn được request khác cập nhật xen giữa.

## 20. Kiểm thử mapping

Mapping là logic ở boundary và cần được kiểm thử riêng. Một số nhóm test hữu ích:

### DTO validation test

- Field bắt buộc bị thiếu.
- Chuỗi vượt giới hạn.
- Số lượng bằng 0 hoặc âm.
- Nested object không hợp lệ.
- JSON có kiểu dữ liệu sai.

### Mapper test

- String ID được chuyển thành đúng kiểu ID.
- Quantity được chuyển thành Value Object.
- Field không được client quyết định không xuất hiện trong command.
- Customer/Actor lấy từ security context, không lấy từ body khi không được phép.
- Null, absent và empty được xử lý đúng semantics.
- API v1 và v2 ánh xạ về command đúng.

### Application test

- Command gọi đúng use case.
- Không tìm thấy Aggregate trả kết quả phù hợp.
- Authorization được kiểm tra trước hành động.
- Domain rule từ chối được chuyển thành application result/error.
- Concurrency conflict không bị bỏ qua.
- Request lặp được xử lý theo idempotency policy.

### API contract test

- Request/response JSON đúng schema.
- HTTP status và error code ổn định.
- Không lộ field nội bộ của Aggregate.
- Response không phụ thuộc cấu trúc ORM.
- API version cũ vẫn hoạt động theo thời hạn hỗ trợ.

## 21. Những sai lầm thường gặp

### Dùng Request DTO làm Domain Entity

DTO được thiết kế theo JSON contract, có thể thay đổi vì client. Domain Entity có identity, lifecycle và behavior riêng. Trộn hai vai trò làm domain phụ thuộc API.

### Bind trực tiếp request vào Aggregate

Client có thể ghi đè status, total, owner hoặc field nội bộ. Hãy tạo command tường minh và gọi domain behavior.

### Copy toàn bộ field bằng reflection

Mass assignment có thể mở quyền ghi ngoài ý muốn khi DTO được mở rộng. Mapping tường minh giúp kiểm soát dữ liệu.

### Đưa business rule vào annotation DTO

Annotation phù hợp với structural validation. Điều kiện như sản phẩm còn bán, đơn chưa giao hoặc khách đủ hạng phải được kiểm tra trong application/domain.

### Tin ID hoặc actor từ body

Client có thể giả mạo resource owner hoặc người thực hiện. Lấy danh tính từ security context và kiểm tra quyền trên resource.

### Nhận giá và tổng tiền từ client

Giá, thuế, chiết khấu và tổng tiền cần được tính hoặc xác minh từ nguồn có thẩm quyền.

### Trả Aggregate trực tiếp ra API

Có thể làm lộ dữ liệu nội bộ, object graph và persistence detail. Dùng response DTO hoặc read model.

### Dùng một DTO cho mọi API version và mọi context

Hợp đồng giao tiếp và ngôn ngữ miền có thể khác nhau. Dùng adapter/mapper để chuyển về mô hình phù hợp.

### Không phân biệt absent và null trong PATCH

Có thể vô tình xóa dữ liệu hoặc bỏ qua yêu cầu cập nhật. Định nghĩa semantics và biểu diễn chúng rõ ràng.

### Ánh xạ lỗi domain trực tiếp thành HTTP trong domain

Domain không nên phụ thuộc HTTP status. API adapter ánh xạ lỗi theo contract.

## 22. Quy trình thiết kế mapping

Khi thêm một endpoint hoặc tích hợp một payload mới, có thể đi theo trình tự:

1. **Xác định client và contract:** ai gửi request, phiên bản nào, field nào được phép?
2. **Xác định ý định nghiệp vụ:** request tương ứng command/query nào?
3. **Xác định nguồn dữ liệu:** field nào từ body, path, header, security context hoặc server?
4. **Thiết kế DTO:** chỉ biểu diễn dữ liệu cần nhận và ràng buộc transport.
5. **Thiết kế command/query:** dùng kiểu miền và thể hiện ý định rõ.
6. **Viết mapper tường minh:** chuyển ID, Value Object, collection và context.
7. **Phân lớp validation:** parsing, structure, authorization, domain rule và persistence constraint.
8. **Gọi use case:** handler nạp Aggregate và gọi hành vi domain.
9. **Ánh xạ kết quả:** chuyển Application Result sang response DTO và HTTP.
10. **Kiểm thử:** DTO validation, mapper, use case và API contract.

## 23. Checklist ánh xạ API sang nghiệp vụ

Trước khi hoàn thiện endpoint, hãy kiểm tra:

- Request DTO có chỉ chứa field client được phép gửi không?
- Ý định nghiệp vụ đã được biểu diễn thành Command hoặc Query có tên rõ chưa?
- DTO có bị dùng trực tiếp làm Entity/Aggregate không?
- ID thô có được chuyển thành kiểu ID phù hợp không?
- Value Object có bảo vệ các quy tắc cấu trúc của giá trị không?
- Actor, tenant và owner có lấy từ nguồn đã xác thực không?
- Giá, tổng tiền, trạng thái và timestamp có được quyết định bởi nguồn có thẩm quyền không?
- Structural validation có tách khỏi domain rule không?
- PATCH có phân biệt absent, null và value không?
- API version có được tách khỏi Domain Model không?
- Mapping có tránh mass assignment không?
- Response có dùng DTO/read model thay vì trả Aggregate không?
- Lỗi domain/application có được ánh xạ thành HTTP contract ở adapter không?
- Idempotency và concurrency token có được chuyển đúng vào use case không?
- External payload có được chuẩn hóa qua adapter/ACL khi cần không?
- Mapper và API contract đã có test tương ứng chưa?

## 24. Kết luận

Ánh xạ yêu cầu bên ngoài sang ý định nghiệp vụ là ranh giới quan trọng giữa API và DDD. Request DTO mô tả dữ liệu theo hợp đồng giao tiếp; Command hoặc Query diễn đạt use case; Value Object chuẩn hóa giá trị miền; Application Handler điều phối; Aggregate thực thi quy tắc; Response DTO biểu diễn kết quả được phép công khai.

Khi mapping được thực hiện tường minh, client chỉ có thể yêu cầu những hành động được API hỗ trợ, còn domain giữ quyền quyết định trạng thái nào hợp lệ. API có thể đổi tên field, phiên bản hoặc cấu trúc JSON mà không buộc mô hình miền phải đổi theo.

Thiết kế này giúp hệ thống giữ ranh giới rõ giữa giao thức, ứng dụng và nghiệp vụ, đồng thời làm cho validation, authorization, concurrency, lỗi và kiểm thử dễ kiểm soát hơn.
