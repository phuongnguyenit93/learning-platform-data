# Validate response để tránh lộ field ngoài contract

API contract mô tả dữ liệu mà một endpoint cam kết trao đổi với client. Với response, contract xác định những field được phép xuất hiện, kiểu dữ liệu, cấu trúc lồng nhau và điều kiện của từng biến thể response. Kiểm tra response theo contract giúp phát hiện trường dữ liệu nội bộ hoặc nhạy cảm bị trả ra ngoài ngoài ý muốn.

Đây là một phần của bảo mật API theo từng endpoint và đối tượng dữ liệu. HTTPS bảo vệ dữ liệu trên đường truyền; xác thực xác định người gọi; phân quyền quyết định người gọi được truy cập tài nguyên nào. Những lớp đó vẫn chưa bảo đảm response chỉ chứa dữ liệu cần thiết. Một endpoint có thể kiểm tra quyền đọc đơn hàng đúng nhưng vô tình serialize toàn bộ entity, làm lộ ghi chú nội bộ, mã định danh của tenant, thông tin thanh toán hoặc thuộc tính chỉ dành cho vận hành.

## 1. Vì sao cần kiểm tra response

Lỗi lộ field thường xuất hiện khi cấu trúc nội bộ của ứng dụng được dùng trực tiếp làm cấu trúc công khai. Ví dụ, một entity trong database có thể chứa nhiều thuộc tính phục vụ xử lý nghiệp vụ, nhưng client chỉ cần một phần nhỏ trong số đó.

| Dữ liệu nội bộ | Rủi ro khi trả ra ngoài |
|---|---|
| `passwordHash`, `passwordResetToken`, `mfaSecret` | Hỗ trợ chiếm tài khoản hoặc làm lộ bí mật xác thực. |
| `isAdmin`, `internalRole`, `permissionFlags` | Làm lộ cấu trúc phân quyền hoặc trạng thái nội bộ; client có thể hiểu nhầm đây là dữ liệu đáng tin cậy. |
| `tenantId`, `ownerId`, `internalAccountId` | Tiết lộ định danh nội bộ hoặc thông tin liên kết giữa các khách hàng. |
| `riskScore`, `fraudReviewNote`, `moderationComment` | Tiết lộ đánh giá hoặc ghi chú chỉ dành cho nhân viên. |
| `createdByIp`, `debugInfo`, `stackTrace` | Tiết lộ dữ liệu cá nhân, chi tiết triển khai hoặc thông tin hỗ trợ tấn công. |
| `paymentProviderPayload`, `accessToken` | Làm lộ dữ liệu thanh toán hoặc thông tin xác thực của dịch vụ khác. |

Không phải mọi field ngoài contract đều là bí mật. Tuy nhiên, field xuất hiện ngoài hợp đồng có thể làm lộ dữ liệu, mở rộng bề mặt tấn công, phá vỡ giả định của client hoặc khiến dữ liệu nội bộ trở thành giao diện công khai khó thu hồi. Vì vậy, nguyên tắc an toàn là chỉ trả những field cần thiết và được cho phép.

### 1.1. Những nguyên nhân phổ biến

- Controller trả trực tiếp entity hoặc object ORM thay vì một response model riêng.
- Serializer tự động xuất tất cả thuộc tính public hoặc getter.
- Response được tạo từ `Map`, `Object` động hoặc dữ liệu ghép từ nhiều nguồn mà không có allowlist.
- Một field mới được thêm vào model nội bộ và tự động xuất hiện trong JSON.
- Đối tượng lồng nhau được serialize toàn bộ dù endpoint chỉ cần một số thuộc tính.
- Cấu hình theo role, tenant hoặc trạng thái nghiệp vụ không loại bỏ field nhạy cảm đúng cách.
- Error handler trả stack trace, câu truy vấn, đường dẫn file hoặc thông tin debug.

Kiểm tra quyền truy cập tài nguyên và kiểm tra field được phép xuất hiện là hai việc khác nhau. Người dùng có thể được phép xem một đơn hàng nhưng không được phép xem ghi chú điều tra gian lận của đơn hàng đó.

## 2. Thiết kế response contract theo allowlist

Một schema response tốt mô tả rõ cấu trúc công khai của endpoint. Mỗi object nên liệt kê các property được phép, kiểu dữ liệu và cấu trúc con. Với JSON Schema, có thể dùng `additionalProperties: false` để từ chối property không được khai báo. Nếu không khai báo quy tắc này, JSON Schema thường cho phép property bổ sung.

Ví dụ một contract OpenAPI cho response đơn hàng:

~~~yaml
paths:
  /orders/{orderId}:
    get:
      responses:
        '200':
          description: Thông tin đơn hàng được phép hiển thị
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'

components:
  schemas:
    OrderResponse:
      type: object
      additionalProperties: false
      required:
        - id
        - status
        - total
        - items
      properties:
        id:
          type: string
        status:
          type: string
          enum: [PENDING, PAID, SHIPPED, CANCELLED]
        total:
          type: number
          minimum: 0
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderItemResponse'
    OrderItemResponse:
      type: object
      additionalProperties: false
      required: [productName, quantity]
      properties:
        productName:
          type: string
        quantity:
          type: integer
          minimum: 1
~~~

Contract này chỉ công khai mã đơn hàng, trạng thái, tổng tiền và danh sách sản phẩm với tên, số lượng. Các field như `fraudReviewNote`, `paymentProviderPayload` hoặc `internalRiskScore` không thuộc schema và phải bị phát hiện nếu xuất hiện trong response.

### 2.1. Các quy tắc cần mô tả

Khi thiết kế schema, hãy xác định:

- **Danh sách property:** field nào được phép xuất hiện trong response của endpoint.
- **Kiểu dữ liệu:** string, integer, number, boolean, array hoặc object.
- **Required:** field nào bắt buộc phải có.
- **Nullable:** field có thể có giá trị null hay không.
- **Giới hạn:** độ dài chuỗi, giá trị số tối thiểu/tối đa, số phần tử mảng và định dạng.
- **Object lồng nhau:** schema riêng cho từng cấu trúc con; không để object con tự do nếu không có chủ đích.
- **Biến thể response:** các trường hợp `oneOf`, `anyOf` hoặc discriminator phải giới hạn rõ field cho từng biến thể.
- **Header và content type:** những header công khai nào được phép xuất hiện và media type nào được hỗ trợ.

`required` chỉ yêu cầu property có mặt; nó không tự động có nghĩa property không được null. Quy tắc nullable cần được mô tả phù hợp với phiên bản OpenAPI/JSON Schema mà dự án sử dụng. Tương tự, `additionalProperties: false` phải được áp dụng ở từng object lồng nhau cần đóng schema; đóng object ngoài cùng không tự động đóng mọi object con.

### 2.2. Cẩn trọng với schema kết hợp và mở rộng

Khi dùng `allOf`, `oneOf`, `anyOf` hoặc schema kế thừa, cần hiểu dialect JSON Schema và phiên bản OpenAPI của dự án. Đặt `additionalProperties: false` ở một nhánh `allOf` có thể khiến property được khai báo ở nhánh khác bị xem là property lạ. Với OpenAPI 3.1 và JSON Schema tương ứng, `unevaluatedProperties: false` có thể phù hợp hơn trong một số cấu trúc kết hợp; cần xác minh khả năng hỗ trợ của validator đang dùng. Không sao chép một cấu hình schema đóng mà chưa chạy thử trên response hợp lệ.

Schema đóng giúp phát hiện field ngoài contract, nhưng cũng ảnh hưởng đến chiến lược tương thích. Nếu API cần mở rộng, hãy thay đổi contract có chủ đích, đánh giá client hiện tại và quản lý version theo chính sách. Không mở mọi object chỉ để tránh lỗi khi thêm field; điều đó làm mất tín hiệu phát hiện dữ liệu xuất hiện ngoài dự kiến.

## 3. Tách response model khỏi entity nội bộ

Cách phòng vệ quan trọng nhất là không serialize trực tiếp đối tượng lưu trữ hoặc domain object thành response công khai. Hãy tạo response DTO (Data Transfer Object) riêng cho từng endpoint hoặc nhóm endpoint có cùng contract. DTO đóng vai trò allowlist ở tầng ứng dụng: chỉ những field được khai báo và ánh xạ mới có thể đi ra ngoài.

Ví dụ không an toàn:

~~~java
@GetMapping("/orders/{id}")
public OrderEntity getOrder(@PathVariable String id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Nếu serializer nhìn thấy các getter của `OrderEntity`, những thuộc tính được thêm sau này có thể tự động xuất hiện trong JSON. Kết quả còn phụ thuộc annotation và cấu hình serializer, nên việc kiểm soát chỉ dựa vào cấu trúc entity rất mong manh.

Ví dụ dùng response DTO:

~~~java
public record OrderResponse(
    String id,
    String status,
    BigDecimal total,
    List<OrderItemResponse> items
) {}

public record OrderItemResponse(
    String productName,
    int quantity
) {}

@GetMapping("/orders/{id}")
public OrderResponse getOrder(@PathVariable String id) {
    OrderEntity order = orderService.getVisibleOrder(id);

    List<OrderItemResponse> items = order.getItems().stream()
        .map(item -> new OrderItemResponse(
            item.getProductName(),
            item.getQuantity()
        ))
        .toList();

    return new OrderResponse(
        order.getPublicId(),
        order.getPublicStatus(),
        order.getTotal(),
        items
    );
}
~~~

Ví dụ trên minh họa cách ánh xạ thủ công. `getVisibleOrder` cần thực hiện hoặc gọi đến kiểm tra quyền sở hữu/tenant phù hợp; DTO không thay thế authorization. Mapper cũng phải tránh sao chép toàn bộ entity hoặc dùng reflection tự động theo kiểu “mọi field trùng tên đều được đưa ra” nếu không có allowlist rõ ràng.

### 3.1. Vì sao không nên chỉ dựa vào annotation ẩn field

Các annotation như `@JsonIgnore`, `@JsonView` hoặc cấu hình visibility có thể hữu ích, nhưng không nên là ranh giới duy nhất giữa dữ liệu nội bộ và dữ liệu công khai:

- Field mới có thể được thêm mà không có annotation bảo vệ.
- Một endpoint khác có thể dùng view hoặc serializer khác và vô tình xuất field.
- Cấu hình global có thể thay đổi hành vi serialization của nhiều endpoint.
- Getter dẫn xuất hoặc quan hệ ORM có thể tạo thêm dữ liệu ngoài dự kiến.
- Annotation trên entity có thể ảnh hưởng cả những luồng nội bộ cần dữ liệu đó.

DTO riêng với mapping tường minh tạo ra một ranh giới dễ review hơn. Annotation serializer nên bổ trợ cho contract, không thay thế việc thiết kế contract và test response.

### 3.2. Kiểm soát object động và dữ liệu lồng nhau

Các kiểu như `Map<String, Object>`, `JsonNode`, `Object` hoặc trường mở rộng tùy ý làm giảm khả năng kiểm soát property. Nếu nghiệp vụ thật sự cần field động, hãy định nghĩa namespace hoặc schema riêng cho phần mở rộng, giới hạn loại dữ liệu, kích thước và tên key. Không đưa nguyên object từ dịch vụ nội bộ hoặc database vào response.

Với collection và object lồng nhau, hãy kiểm tra đệ quy. Một response có thể có object ngoài đúng schema nhưng phần `customer`, `payment` hoặc `metadata` lại chứa field nhạy cảm. Mỗi phần tử trong array cũng phải tuân theo schema của item.

## 4. Phân quyền ở mức field

Contract mô tả hình dạng response; authorization quyết định người gọi cụ thể có được xem từng dữ liệu hay không. Hai cơ chế cần phối hợp.

Ví dụ một endpoint có thể trả thông tin đơn hàng cho:

- Khách hàng sở hữu đơn: mã đơn, trạng thái, tổng tiền và địa chỉ giao hàng đã được phép hiển thị.
- Nhân viên hỗ trợ: thêm một số thông tin phục vụ xử lý yêu cầu.
- Nhân viên điều tra gian lận: có thể xem một số tín hiệu rủi ro theo quyền và mục đích được phê duyệt.

Không nên trả tất cả field rồi trông chờ client tự ẩn những field người dùng không được xem. Dữ liệu đã gửi tới trình duyệt hoặc ứng dụng client đã nằm ngoài ranh giới tin cậy, kể cả khi giao diện không hiển thị nó.

Có hai cách thường dùng:

1. **Contract/DTO riêng theo use case hoặc vai trò:** phù hợp khi các nhóm người dùng có tập field khác nhau rõ ràng. Mỗi loại response có schema và test riêng.
2. **Projection theo policy:** dùng khi tập field thay đổi theo quyền, tenant hoặc trạng thái. Server xác định policy trước khi tạo response và chỉ đưa field được phép vào DTO.

Không nên lấy role từ request body hoặc query parameter để quyết định field. Quyền phải đến từ danh tính đã xác thực và policy phía server. Nếu một field được phép với nhân viên nhưng không được phép với khách hàng, cần test cả hai principal trên cùng tài nguyên.

Đặc biệt, field nhạy cảm có thể không được phép với một số trạng thái nghiệp vụ. Ví dụ thông tin vận chuyển chỉ xuất hiện sau khi đơn hàng được xác nhận; thông tin điều tra chỉ hiển thị cho nhóm được ủy quyền. Điều kiện này cần được thể hiện trong policy và test, không chỉ trong schema tĩnh.

## 5. Kiểm tra response ở đâu trong ứng dụng

Một luồng xử lý điển hình:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Authentication]
    B --> C[Authorization tài nguyên và chức năng]
    C --> D[Đọc dữ liệu cần thiết]
    D --> E[Ánh xạ sang response DTO]
    E --> F[Serialization thành JSON]
    F --> G[Kiểm tra contract/schema]
    G -->|Hợp lệ| H[Gửi response]
    G -->|Không hợp lệ| I[Chặn response và ghi nhận sự kiện an toàn]
~~~

Kiểm tra có thể được thực hiện ở nhiều lớp:

- **Compile-time hoặc mapping review:** DTO tường minh giúp ngăn nhiều field ngoài ý muốn ngay từ thiết kế.
- **Unit test mapper:** xác minh mapper chỉ ánh xạ field được cho phép và xử lý đúng các trạng thái.
- **Test response sau serialization:** kiểm tra JSON thực tế do serializer tạo ra, vì annotation và cấu hình có thể làm thay đổi kết quả so với DTO.
- **Contract test/API test:** gửi request qua HTTP và xác minh response theo schema công khai.
- **Runtime response validation:** với endpoint hoặc dữ liệu có rủi ro cao, có thể validate payload đã serialize trước khi gửi ra ngoài.

Runtime validation tạo thêm chi phí CPU và có thể cần buffer response. Cần cân nhắc kích thước payload, latency, streaming và mức rủi ro. Với response streaming hoặc file lớn, validator dạng buffer thông thường có thể không phù hợp; khi đó cần thiết kế kiểm soát riêng cho định dạng và luồng truyền. Dù có bật runtime validation hay không, test ở tầng HTTP vẫn cần xác minh response thực tế.

Nếu runtime validation thất bại, không gửi nguyên payload sai contract cho client. Hãy trả lỗi server đã được chuẩn hóa, không chứa response nội bộ, và phát sinh sự kiện để nhóm điều tra. Không log toàn bộ payload vì chính payload có thể chứa dữ liệu nhạy cảm.

## 6. Xây dựng bộ test phát hiện field ngoài contract

Test phải kiểm tra cả response hợp lệ lẫn những trường hợp có nguy cơ rò rỉ. Không chỉ assert rằng các field mong đợi có mặt; cần xác minh các field không được phép vắng mặt.

### 6.1. Các nhóm test nên có

| Nhóm | Trường hợp cần kiểm tra |
|---|---|
| Field ngoài contract | Response không chứa `passwordHash`, `internalNote`, `tenantSecret` hoặc field nội bộ khác. |
| Object lồng nhau | Không có field thừa trong customer, item, payment, metadata và từng phần tử array. |
| Field theo vai trò | Khách hàng, nhân viên hỗ trợ và quản trị chỉ nhận field theo policy của mình. |
| Field theo tenant/object | Người dùng tenant A không nhận thuộc tính hoặc dữ liệu liên kết của tenant B. |
| Giá trị null và thiếu field | Required, nullable và quy tắc omit/null được thực hiện đúng. |
| Biến thể response | Mỗi nhánh `oneOf` hoặc discriminator chỉ chứa field thuộc biến thể đó. |
| Error response | Không lộ stack trace, câu SQL, token, đường dẫn nội bộ hoặc debug context. |
| Header và content type | Không gửi header debug hoặc header nội bộ không thuộc contract công khai. |
| Phiên bản API | Response của version cũ không tự xuất field mới ngoài schema đã công bố. |

### 6.2. Ví dụ kiểm tra JSON thực tế

Một test API có thể kiểm tra cả field bắt buộc và field bị cấm:

~~~java
@Test
void orderResponseContainsOnlyPublicFields() throws Exception {
    mockMvc.perform(get("/orders/order-123")
            .with(user("customer-a")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").exists())
        .andExpect(jsonPath("$.status").exists())
        .andExpect(jsonPath("$.total").exists())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(jsonPath("$.fraudReviewNote").doesNotExist())
        .andExpect(jsonPath("$.paymentProviderPayload").doesNotExist())
        .andExpect(jsonPath("$.items[0].internalCost").doesNotExist());
}
~~~

Đây là ví dụ theo Spring MockMvc; fixture, principal và đường dẫn cần thay theo dự án. Các assertion `doesNotExist` hữu ích cho những field nhạy cảm đã biết, nhưng có thể bỏ sót một field lạ mới được thêm vào. Vì vậy nên kết hợp với kiểm tra schema đóng để từ chối mọi property không được khai báo.

### 6.3. Test schema trên response sau serialization

Với contract OpenAPI hoặc JSON Schema, có thể dùng validator để kiểm tra body thực tế. Quy trình test:

1. Gọi endpoint bằng principal và dữ liệu test cụ thể.
2. Thu thập status code, content type, header và JSON body.
3. Chọn schema ứng với method, path, status code và media type.
4. Validate toàn bộ JSON, gồm object lồng nhau và phần tử array.
5. Khi thất bại, báo đường dẫn JSON của property không hợp lệ, ví dụ `$.items[0].internalCost`.
6. Không đưa giá trị nhạy cảm của property vào log test hoặc báo cáo CI.

Nên có test cho cả 200, 201, 204 và các response lỗi được định nghĩa. Response 204 không có body; validator phải xử lý đúng quy tắc đó thay vì cố parse JSON rỗng. Với response nhiều media type, mỗi media type cần contract và test tương ứng.

### 6.4. Kiểm tra thay đổi schema trong CI

Khi schema thay đổi, CI nên hiển thị khác biệt để reviewer nhận biết field mới, field bị xóa, kiểu dữ liệu thay đổi và điều kiện required thay đổi. Một thay đổi thêm field có thể là hợp lệ về mặt tương thích đối với một số client, nhưng vẫn có thể làm lộ dữ liệu nếu field đó không được chủ đích công khai.

Quy trình review nên hỏi:

- Field mới có thật sự cần cho client không?
- Field có chứa dữ liệu cá nhân, bí mật, định danh nội bộ hoặc ghi chú vận hành không?
- Ai được phép xem field này? Có khác nhau theo role, tenant hoặc trạng thái không?
- Giá trị có được lấy từ nguồn dữ liệu đáng tin cậy và đã được lọc không?
- Schema, DTO, test và tài liệu API có được cập nhật đồng bộ không?
- Client của version cũ có bị ảnh hưởng không?

## 7. Xử lý lỗi và giám sát response contract

Lỗi validation response là dấu hiệu ứng dụng sắp gửi dữ liệu không phù hợp với hợp đồng. Có thể do mapper sai, serializer thay đổi, schema lỗi thời hoặc một field nội bộ vừa được thêm vào model.

Khi phát hiện lỗi:

- Chặn response không hợp lệ trước khi gửi cho client nếu có thể kiểm soát ở runtime.
- Trả error response chung đã được chuẩn hóa, không chứa payload lỗi hoặc chi tiết nội bộ.
- Ghi nhận endpoint, phiên bản API, status code, schema version và JSON path của lỗi.
- Phân loại lỗi theo loại vi phạm: property thừa, thiếu field bắt buộc, sai kiểu, sai enum hoặc sai cấu trúc.
- Không ghi giá trị của field, token, dữ liệu cá nhân hoặc toàn bộ response vào log.
- Gắn sự kiện với release/commit để truy tìm thay đổi gây ra vi phạm.

Metric nên tập trung vào số lần vi phạm theo endpoint, phiên bản, loại lỗi và release. Nếu cùng một lỗi tăng đột ngột sau triển khai, nhóm có thể phát hiện regression. Log và metric cần được giới hạn quyền truy cập, thời gian lưu và dữ liệu nhận diện theo chính sách bảo vệ dữ liệu.

Không nên âm thầm bỏ field lạ trong mọi trường hợp để làm response có vẻ hợp lệ. Việc tự động strip có thể che giấu lỗi mapping hoặc khiến client nhận dữ liệu thiếu mà không có tín hiệu. Chính sách phù hợp là phát hiện, chặn hoặc xử lý theo quy tắc được thiết kế, đồng thời tạo cảnh báo cho đội sở hữu API.

## 8. Những sai lầm cần tránh

- **Trả entity trực tiếp:** thay đổi schema database có thể vô tình thay đổi API công khai.
- **Chỉ kiểm tra field bắt buộc:** response có đủ field mong đợi nhưng vẫn có thể chứa thêm dữ liệu nhạy cảm.
- **Chỉ ẩn field ở giao diện:** dữ liệu đã gửi tới client vẫn có thể được đọc từ network hoặc bộ nhớ ứng dụng.
- **Chỉ dùng `@JsonIgnore`:** annotation có thể bị thiếu ở model mới hoặc bị thay đổi bởi cấu hình serializer.
- **Chỉ đóng schema ngoài cùng:** field thừa vẫn có thể xuất hiện trong object con hoặc phần tử array.
- **Dùng object động không giới hạn:** `Map` hoặc JSON tự do khiến contract khó kiểm soát và review.
- **Dùng một response cho mọi vai trò:** field nhạy cảm có thể bị trả cho principal không đủ quyền.
- **Tin rằng schema thay thế authorization:** response đúng schema vẫn có thể chứa dữ liệu của người dùng hoặc tenant khác.
- **Log payload khi validation lỗi:** log trở thành một nơi lưu trữ dữ liệu nhạy cảm ngoài dự kiến.
- **Bỏ qua response lỗi:** stack trace và thông tin debug thường bị lộ qua error handler hơn response thành công.

## 9. Checklist trước khi công bố hoặc thay đổi API

- [ ] Mỗi endpoint có response schema rõ ràng theo method, status code và media type.
- [ ] Object công khai dùng allowlist property; object lồng nhau và array item cũng có schema.
- [ ] Quy tắc property bổ sung được xác định rõ, chẳng hạn `additionalProperties: false` khi cần schema đóng.
- [ ] DTO response tách khỏi entity và model lưu trữ nội bộ.
- [ ] Mapper chỉ đưa field được phép vào response.
- [ ] Field nhạy cảm được kiểm tra theo role, tenant, chủ sở hữu và trạng thái nghiệp vụ.
- [ ] Test kiểm tra JSON sau serialization, không chỉ kiểm tra DTO trước khi serialize.
- [ ] Test phát hiện property thừa, gồm cả property lồng nhau và field động.
- [ ] Error response không chứa stack trace, token, câu SQL hoặc dữ liệu nội bộ.
- [ ] Header và content type tuân theo contract công khai.
- [ ] CI kiểm tra thay đổi schema và chạy contract test trước khi phát hành.
- [ ] Runtime validation được cân nhắc cho endpoint rủi ro cao; lỗi không làm lộ payload.
- [ ] Log/metric không lưu giá trị nhạy cảm và có thể truy vết vi phạm theo endpoint, version và release.

Validate response theo contract giúp biến nguyên tắc “chỉ trả dữ liệu cần thiết” thành một điều kiện có thể kiểm tra. Khi kết hợp schema allowlist, DTO tường minh, authorization ở mức field và test trên JSON thực tế, nhóm giảm nguy cơ một thay đổi nội bộ vô tình trở thành dữ liệu công khai của API.
