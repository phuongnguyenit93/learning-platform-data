# Đổi tên, xóa trường và thay kiểu dữ liệu

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Contract Verifier sinh kiểm thử phía producer; stub artifact giúp consumer kiểm tra code của mình qua **Stub Runner**. Một trong những nguyên nhân phổ biến gây API incompatibility là thay đổi schema: **đổi tên field, xóa field hoặc thay kiểu dữ liệu** trong request, response hay message event.

Những thay đổi này thường trông nhỏ trong code: đổi `name` thành `displayName`, bỏ `legacyCode` đã lâu không dùng, hoặc chuyển `amount` từ string sang number. Nhưng consumer có thể đang phụ thuộc vào tên, kiểu, null semantics hoặc đơn vị của dữ liệu. Producer mới có thể compile và generated tests của producer vẫn PASS, trong khi consumer cũ không deserialize được response hoặc gửi request bị producer từ chối.

Bài **“Đổi tên, xóa trường và thay kiểu dữ liệu”** thuộc chương **Phiên bản và tương thích**. Nội dung tập trung vào cách đánh giá tác động theo chiều giao tiếp, tổ chức migration có giai đoạn và dùng Spring Cloud Contract để kiểm chứng các phiên bản consumer đang được hỗ trợ.

Sau bài học, bạn có thể:

- Phân biệt thay đổi tương thích và breaking change đối với **request**, **response** và **message event**.
- Đánh giá riêng việc đổi tên, xóa field, thay kiểu, thay tính bắt buộc, null và đơn vị.
- Thiết kế chiến lược **expand – migrate – contract** để nhiều service được triển khai độc lập.
- Dùng Jackson để hỗ trợ đọc cả tên cũ và tên mới trong giai đoạn chuyển tiếp.
- Viết contract scenarios cho producer và chạy consumer tests với stub của các phiên bản liên quan.
- Xây ma trận producer–consumer compatibility và CI gates trước khi xóa field cũ.
- Nhận diện những trường hợp “thêm field” vẫn có thể làm consumer cũ thất bại.

> **Nguyên tắc quan trọng:** Tương thích phụ thuộc vào hướng dữ liệu và hành vi của consumer thực tế. “Thêm một field” thường dễ tương thích hơn “đổi kiểu field”, nhưng không phải consumer nào cũng bỏ qua field lạ. Không có thay đổi schema nào được coi là an toàn chỉ vì producer compile thành công.

## 1. Nhìn thay đổi từ phía người gửi và người nhận

Một API có hai chiều:

- **Request:** consumer gửi dữ liệu; producer nhận và deserialize.
- **Response:** producer gửi dữ liệu; consumer nhận và deserialize.

Message event cũng có cùng quan hệ: producer phát event, một hoặc nhiều consumer nhận event. Một thay đổi có thể an toàn theo một chiều nhưng phá chiều còn lại.

~~~mermaid
flowchart LR
    C["Consumer"] -->|"Request body"| P["Producer"]
    P -->|"Response body"| C
    P -->|"Message event"| M["Broker / destination"]
    M --> C2["Consumer khác"]
~~~

Ví dụ consumer gọi:

~~~http
POST /api/customers
Content-Type: application/json

{
  "customerId": "CUS-1001",
  "name": "An"
}
~~~

Producer trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "CUS-1001",
  "name": "An"
}
~~~

Nếu đổi `name` thành `displayName`, phải hỏi:

1. Producer có còn nhận request cũ không?
2. Producer mới trả response nào cho consumer cũ?
3. Consumer mới có đọc được response từ producer cũ không?
4. Có consumer nào dùng field này trong database, event, report hoặc rule nghiệp vụ không?
5. Có parser strict từ chối unknown fields không?
6. Có message consumer đang subscribe và xử lý event cũ không?

**Không dùng một kết luận chung “backward compatible” cho cả request và response.**

## 2. Ma trận đánh giá các thay đổi schema

Bảng sau là hướng dẫn thực tế; kết quả cuối cùng phụ thuộc parser, validation, contract và consumer versions.

| Thay đổi | Request tới producer | Response tới consumer | Rủi ro thường gặp |
| --- | --- | --- | --- |
| Thêm field optional | Thường tương thích nếu producer bỏ qua/nhận field mới đúng cách | Thường tương thích nếu consumer bỏ qua field lạ | Strict unknown-field parser, validation |
| Thêm field required | Consumer cũ có thể không gửi | Consumer cũ có thể không hiểu hoặc không có giá trị | Thiếu dữ liệu, deserialization |
| Đổi tên field | Producer mới phải tiếp tục nhận tên cũ trong giai đoạn chuyển tiếp | Consumer cũ vẫn đọc tên cũ | Missing property, null, validation fail |
| Xóa field | Producer mới có thể từ chối request cũ | Consumer cũ không tìm thấy field | Business logic hoặc DTO phụ thuộc |
| String → number | Producer cũ có thể từ chối number hoặc coercion khác | Consumer cũ có thể không đọc number | Type mismatch, precision |
| Number → string | Producer cũ có thể không parse string | Consumer cũ có thể không parse string | Coercion che lỗi, mất semantics |
| Object → scalar/array | Request shape cũ không còn parse | Consumer DTO cũ không còn khớp | Structural breaking change |
| Optional → required | Consumer cũ có thể không cung cấp field | Producer phải bảo đảm field luôn có | 400/validation failure |
| Non-null → null | Request validation/logic có thể không chấp nhận | Consumer dereference null | NullPointerException |
| Null → missing | Producer không còn gửi explicit null | Consumer phân biệt absent và null | Defaulting/patch semantics |
| Đổi đơn vị/format | Producer hiểu sai giá trị cũ | Consumer diễn giải sai dữ liệu mới | Lỗi nghiệp vụ dù type không đổi |

### Thay đổi response và request không đối xứng

- Với **request**, producer là bên nhận. Producer mới có thể hỗ trợ cả field cũ và field mới để consumer triển khai dần.
- Với **response**, consumer là bên nhận. Consumer mới có thể đọc cả hai tên, nhưng producer mới phải cân nhắc consumer cũ có từ chối field mới hay không.
- Với **event**, consumer có thể deploy chậm và không được nâng cấp đồng thời. Cần thời gian hỗ trợ schema cũ hoặc một versioned destination.

## 3. Đổi tên field: thực chất là xóa một tên và thêm tên khác

Giả sử API hiện có response:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

Phiên bản mới muốn dùng:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

Consumer cũ có thể có DTO:

~~~java
public class CustomerResponse {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
    public void setId(String id) { this.id = id; }
    public void setName(String name) { this.name = name; }
}
~~~

Nếu producer bỏ `name` ngay lập tức, consumer cũ có thể nhận `name == null`. Nếu consumer dùng `name` làm tiêu đề đơn hàng, tên hiển thị sẽ biến mất dù HTTP status vẫn 200.

**Đổi tên không phải thao tác cosmetic**. Ở mức wire contract, đây là một field cũ bị xóa và một field mới được thêm.

### Câu hỏi bắt buộc trước khi đổi tên

- Consumer nào đang đọc tên cũ?
- Consumer có parser strict với unknown fields không?
- Consumer có dùng tên cũ trong business logic hoặc persistence không?
- Request có consumer cũ vẫn gửi tên cũ không?
- Có thể giữ cả hai tên trong giai đoạn chuyển tiếp không?
- Nếu không thể giữ cả hai, có cần API version hoặc message version mới không?

## 4. Chiến lược đổi tên field trong request

Giả sử consumer gửi `name` nhưng producer mới muốn dùng `displayName`.

**Producer là bên nhận request**, nên có thể triển khai theo thứ tự:

1. Producer chấp nhận cả `name` và `displayName`.
2. Consumer mới chuyển dần sang gửi `displayName`.
3. Theo dõi request nào còn gửi `name`.
4. Khi không còn consumer được hỗ trợ gửi tên cũ, lên kế hoạch ngừng hỗ trợ `name`.
5. Xóa alias cũ sau thời gian deprecation và kiểm chứng.

### DTO dùng Jackson để đọc alias

~~~java
package com.example.customers.api;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class CreateCustomerRequest {

    private String customerId;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Với cấu hình Jackson phù hợp:

- `displayName` là tên property chính.
- `name` là alias được chấp nhận khi deserialize request.
- Khi serialize object này, property chính được biểu diễn theo `displayName`.

**`@JsonAlias` hỗ trợ tên thay thế khi đọc dữ liệu**, không tự tạo hai field trong JSON output. Hãy kiểm tra behavior của Jackson version và DTO accessors thực tế.

### Nếu request gửi cả hai tên?

Ví dụ:

~~~json
{
  "name": "An",
  "displayName": "Bình"
}
~~~

Không nên phụ thuộc vào thứ tự field hoặc hành vi “field nào ghi sau thắng”. Hãy định nghĩa policy rõ:

- Từ chối nếu cả hai có giá trị khác nhau.
- Hoặc ưu tiên tên mới và ghi nhận metric cho tên cũ.
- Hoặc chỉ cho phép cả hai nếu giá trị bằng nhau.

Với dữ liệu quan trọng, validate xung đột tường minh để không âm thầm ghi sai tên.

## 5. Chiến lược đổi tên field trong response

Với response, **consumer là bên nhận**, vì vậy producer cần cân nhắc consumer cũ.

Một response chuyển tiếp có thể chứa cả hai:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "displayName": "An"
}
~~~

Điều này chỉ an toàn với consumer cũ nếu chúng **bỏ qua field lạ**. Một số consumer cấu hình Jackson strict để từ chối unknown properties. Khi đó thêm `displayName` cũng có thể làm consumer cũ fail.

### Hai phương án

**Phương án A — Consumer cũ tolerant**

1. Triển khai consumer có thể đọc cả `name` và `displayName`, trong khi producer vẫn chỉ gửi `name`.
2. Cập nhật tất cả consumer cần hỗ trợ.
3. Producer bắt đầu gửi cả hai field.
4. Consumer mới ưu tiên `displayName`, fallback `name`.
5. Theo dõi việc sử dụng field cũ.
6. Sau khi mọi consumer đã migrate, producer ngừng gửi `name`.
7. Khi không còn producer response cũ, consumer có thể bỏ fallback.

**Phương án B — Consumer cũ strict**

Nếu consumer cũ từ chối unknown fields, không thể mặc định dual-write an toàn. Có thể:

- Nâng tất cả consumer strict trước khi producer thêm field mới.
- Tách endpoint version `/v1` và `/v2`.
- Dùng media type/version negotiation.
- Với event, phát schema mới qua destination/topic có version riêng.

Không nên thêm field mới vào response dùng chung khi chưa biết parser của consumer cũ xử lý field lạ thế nào.

## 6. Consumer có thể đọc cả tên cũ và mới

DTO consumer có thể dùng `@JsonAlias`:

~~~java
package com.example.checkout.api;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class CustomerView {

    private String id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Consumer này có thể deserialize cả response cũ `{"name":"An"}` và response mới `{"displayName":"An"}`, nếu Jackson được cấu hình tương thích.

### Kiểm tra cả hai dạng dữ liệu

~~~java
@Test
void readsLegacyName() throws Exception {
    CustomerView view = objectMapper.readValue(
        "{\"id\":\"CUS-1001\",\"name\":\"An\"}",
        CustomerView.class
    );

    assertThat(view.getDisplayName()).isEqualTo("An");
}

@Test
void readsNewDisplayName() throws Exception {
    CustomerView view = objectMapper.readValue(
        "{\"id\":\"CUS-1001\",\"displayName\":\"An\"}",
        CustomerView.class
    );

    assertThat(view.getDisplayName()).isEqualTo("An");
}
~~~

Đây là **unit tests cho deserialization**. Cần thêm consumer integration test với stub artifact để chứng minh HTTP client và business code thực sự hoạt động với response producer.

## 7. Xóa field: kiểm tra cả dependency trực tiếp và gián tiếp

Một field có thể được consumer sử dụng ở nhiều nơi:

- Deserialize vào DTO.
- Lưu database hoặc cache.
- Dùng làm điều kiện if/switch.
- Chuyển tiếp sang service khác.
- Dùng trong message/event.
- Xuất báo cáo hoặc audit.
- Tạo khóa idempotency.
- Làm input cho rule/feature flag.

Ví dụ producer muốn xóa `legacyCode`:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "legacyCode": "C-7788"
}
~~~

Response mới:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

Consumer cũ có thể vẫn compile vì DTO chứa field `legacyCode`, nhưng nhận giá trị `null`. Lỗi có thể chỉ xuất hiện khi business logic thực thi.

### Xóa field có thể là breaking change ngay cả khi consumer không deserialize fail

Ví dụ:

~~~java
if ("VIP".equals(customer.getLegacyCode())) {
    applyPriorityShipping();
}
~~~

Nếu field biến mất, điều kiện không còn đúng. HTTP request/response vẫn thành công, nhưng behavior nghiệp vụ đã thay đổi.

**Phải kiểm tra tác động sử dụng field, không chỉ compile/deserialization.**

## 8. Quy trình xóa field an toàn

Dùng quy trình:

1. **Discover:** tìm các consumer và luồng dữ liệu phụ thuộc field.
2. **Deprecate:** thông báo field sẽ ngừng hỗ trợ, ghi rõ thời điểm và replacement.
3. **Observe:** đo request usage hoặc response consumer telemetry nếu có.
4. **Migrate:** chuyển consumer sang field thay thế.
5. **Verify:** chạy consumer tests với producer stub mới và kiểm tra business outcomes.
6. **Remove:** ngừng gửi/nhận field cũ sau khi các consumer thuộc phạm vi hỗ trợ đã migrate.
7. **Clean up:** xóa DTO properties, matchers, fixtures, mapping và tài liệu không còn dùng.

### Không chỉ dựa vào log request

Với request, producer có thể đếm số request còn chứa `legacyCode`. Với response, producer không tự biết consumer có đọc field hay không chỉ bằng việc gửi response. Cần phối hợp telemetry ở consumer, inventory các consumers hoặc migration deadline có owner.

Nếu không có telemetry đáng tin, phải có **danh sách consumer và xác nhận migration** trước khi xóa.

## 9. Thay kiểu dữ liệu: cùng tên field không có nghĩa cùng hợp đồng

Ví dụ:

**V1 — amount là string**

~~~json
{
  "orderId": "ORD-1001",
  "amount": "125000"
}
~~~

**V2 — amount là number**

~~~json
{
  "orderId": "ORD-1001",
  "amount": 125000
}
~~~

Một consumer DTO cũ:

~~~java
public class OrderResponseV1 {
    private String orderId;
    private String amount;
    // getters/setters
}
~~~

Consumer mới có thể định nghĩa `BigDecimal amount`. Nhưng nếu producer đổi type ngay tại cùng field, consumer cũ có thể:

- Từ chối vì type mismatch.
- Coerce number thành string tùy Jackson settings.
- Parse được nhưng có semantics khác.
- Làm mất precision nếu dùng `double` thay vì kiểu decimal phù hợp.

**Không dựa vào coercion ngầm để tuyên bố tương thích.** Contract cần kiểm tra đúng JSON type.

## 10. Dùng field mới khi thay kiểu

Thay vì đổi type tại cùng tên, có thể mở rộng schema:

~~~json
{
  "orderId": "ORD-1001",
  "amountText": "125000",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

Tên `amountMinor` cần diễn đạt rõ đơn vị (ví dụ đồng, cent, minor unit) theo domain. Không dùng một field mới tên mơ hồ nếu consumer không thể biết cách diễn giải.

Quy trình:

1. Consumer hỗ trợ đọc field mới và cũ.
2. Producer bổ sung field mới, vẫn giữ field cũ trong giai đoạn chuyển tiếp.
3. Consumer mới ưu tiên field mới.
4. Kiểm tra dữ liệu hai field nhất quán theo quy tắc đã công bố.
5. Theo dõi consumer cũ.
6. Ngừng field cũ sau thời gian deprecation.

Cũng như rename, **dual-write chỉ an toàn nếu consumer cũ không từ chối field mới**. Nếu parser strict, hãy migrate consumers trước hoặc version hóa response/event.

## 11. Kiểu dữ liệu có thể thay đổi semantics dù JSON type giữ nguyên

Một số thay đổi không thể phát hiện bằng kiểm tra type đơn giản:

| Field | Trước | Sau | Rủi ro |
| --- | --- | --- | --- |
| `amount` | Đồng | Nghìn đồng | Giá trị cùng là number nhưng đơn vị đổi |
| `createdAt` | ISO-8601 UTC | Local time string | Mất timezone/offset |
| `duration` | Giây | Millisecond | Giá trị lệch 1.000 lần |
| `status` | `PAID` | `SETTLED` | Enum/business state đổi |
| `phone` | E.164 | Chuỗi tự do | Validation và normalization |
| `id` | String giữ leading zero | Number | Mất leading zero |
| `percentage` | 0–100 | 0–1 | Cùng number nhưng semantics khác |
| `amount` | Decimal chính xác | Floating point | Sai số tính toán |

### Ví dụ về timestamp

V1:

~~~json
{"createdAt":"2026-11-24T09:30:00Z"}
~~~

V2:

~~~json
{"createdAt":1795512600000}
~~~

Cả hai có thể đại diện cùng một thời điểm, nhưng khác JSON type và đơn vị. Consumer cũ mong đợi ISO string có thể fail hoặc diễn giải sai.

Nếu cần chuyển, dùng field mới có tên rõ:

~~~json
{
  "createdAt": "2026-11-24T09:30:00Z",
  "createdAtEpochMillis": 1795512600000
}
~~~

Giá trị epoch phải được tính đúng từ thời điểm và timezone đã công bố. Không copy một số ví dụ rồi coi là timestamp chuẩn nếu chưa xác minh.

## 12. Thay đổi null, optional và required

Ba response sau khác nhau:

~~~json
{"middleName": null}
~~~

~~~json
{}
~~~

~~~json
{"middleName": ""}
~~~

- **Explicit null:** field tồn tại nhưng không có giá trị.
- **Missing:** field không xuất hiện.
- **Empty string:** field có chuỗi rỗng.

Consumer có thể xử lý khác nhau. Ví dụ PATCH API có thể hiểu missing là “không thay đổi”, null là “xóa giá trị”, còn empty string là “đặt chuỗi rỗng”.

### Thay đổi cần đánh giá

- Optional → required: consumer cũ có thể không gửi request field.
- Required → optional: producer/consumer cần định nghĩa fallback/default.
- Non-null → nullable: consumer có thể dereference null.
- Null → omitted: consumer có thể dùng default khác.
- Empty → null: có thể thay đổi validation/business rules.

Không coi `@JsonInclude(NON_NULL)` là một thay đổi format vô hại nếu consumer phụ thuộc explicit null.

## 13. Thay đổi object, array và enum

### Object đổi thành array

V1:

~~~json
{
  "address": {
    "city": "HCMC",
    "country": "VN"
  }
}
~~~

V2:

~~~json
{
  "address": [
    {"city": "HCMC", "country": "VN"}
  ]
}
~~~

Consumer DTO có field `Address` không thể mặc định đọc một JSON array thành object. Đây là structural breaking change.

### Enum thêm giá trị

Producer thêm `REFUNDED` vào trường `status`. Consumer dùng switch exhaustive hoặc enum parser strict có thể fail dù JSON type vẫn là string.

Cần xem consumer xử lý **unknown enum values** thế nào. Có thể dùng fallback `UNKNOWN` nếu semantics cho phép, nhưng không được tự map mọi trạng thái mới thành một trạng thái nghiệp vụ hiện hữu.

### Thay đổi collection

- Object thành array.
- Array thành object.
- Array cho phép rỗng thành bắt buộc có ít nhất một phần tử.
- Thay thứ tự có ý nghĩa của array.
- Đổi element type.

Tất cả cần được mô tả và test như thay đổi schema, không chỉ là refactor DTO.

## 14. Phân biệt compatibility theo hướng request/response

Bảng sau giúp tránh kết luận sai:

| Thay đổi | Producer mới nhận request từ consumer cũ | Consumer cũ đọc response producer mới |
| --- | --- | --- |
| Thêm optional field | Có thể tương thích nếu producer chấp nhận request cũ | Có thể tương thích nếu consumer bỏ qua field lạ |
| Đổi tên field | Cần alias/dual-read tên cũ | Cần producer giữ tên cũ hoặc consumer hỗ trợ cả hai |
| Xóa field | Có thể lỗi nếu producer còn yêu cầu field cũ | Consumer có thể nhận null/missing và hỏng logic |
| Thay type | Có thể deserialize fail hoặc coercion | Có thể deserialize fail hoặc diễn giải sai |
| Optional thành required | Consumer cũ không gửi field | Producer mới không gửi field có thể làm consumer fail |
| Nullability thay đổi | Validation có thể từ chối request cũ | Consumer có thể dereference null |

**Một thay đổi chỉ tương thích khi cả hai phía liên quan có behavior hỗ trợ nó trong giai đoạn triển khai.**

## 15. Event/message schema cần thận trọng hơn

Với HTTP, có thể version endpoint hoặc điều chỉnh header negotiation. Với message, consumer có thể xử lý event chậm, replay từ broker hoặc nhận lại event cũ trong thời gian dài.

Ví dụ event cũ:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "CUSTOMER_UPDATED",
  "name": "An"
}
~~~

Event mới:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "CUSTOMER_UPDATED",
  "displayName": "An"
}
~~~

Nếu consumer cũ vẫn subscribe cùng topic và strict parser, dual-write có thể khiến nó fail. Các lựa chọn:

- Deploy consumer tolerant trước.
- Giữ field cũ trong event cho đến khi consumer đã migrate.
- Dùng versioned event type hoặc destination mới.
- Dual-publish có chủ đích và xử lý duplicate/idempotency.
- Có schema registry/policy nếu nền tảng messaging dùng schema registry.

### Event replay làm deprecation khó hơn

Consumer có thể replay event cũ nhiều tháng sau. Xóa field khỏi code consumer mới có thể làm replay cũ không deserialize được. Cần xác định **retention, replay window và archive** trước khi bỏ support schema cũ.

Không giả định event đã publish hôm nay chỉ được xử lý trong hôm nay.

## 16. Version hóa API và event khi không thể chuyển tiếp an toàn

Khi thay đổi quá lớn, version hóa có thể rõ ràng hơn dual-read/dual-write.

Ví dụ HTTP:

~~~text
GET /api/v1/customers/CUS-1001
GET /api/v2/customers/CUS-1001
~~~

V1 response:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

V2 response:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

Với event:

~~~text
customers.updated.v1
customers.updated.v2
~~~

Hoặc event type/version rõ trong payload:

~~~json
{
  "eventType": "CUSTOMER_UPDATED",
  "schemaVersion": 2,
  "displayName": "An"
}
~~~

### Chọn versioning strategy

| Chiến lược | Phù hợp khi | Chi phí |
| --- | --- | --- |
| Dual-read/dual-write | Thay đổi nhỏ, consumer tolerant | Code chuyển tiếp và cleanup |
| Versioned endpoint | HTTP clients cần migration độc lập | Duy trì nhiều routes |
| Versioned media type | API đã có content negotiation | Client/server phải hỗ trợ negotiation |
| Versioned topic/event type | Message consumers deploy chậm | Nhiều destinations/consumer groups |
| New field alongside old | Schema mở rộng được | Tăng payload, cần deprecation |

Không cần version hóa mọi lần thêm optional field. Nhưng nếu cùng một field đổi type hoặc semantics, **field mới/version mới** thường dễ quản lý hơn thay đổi âm thầm tại chỗ.

## 17. Contract YAML cho response cũ và mới

Ví dụ hợp đồng V1:

~~~yaml
description: "V1 trả tên khách hàng bằng field name"
name: get_customer_v1
request:
  method: GET
  url: /api/v1/customers/CUS-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CUS-1001
    name: An
~~~

Hợp đồng V2:

~~~yaml
description: "V2 trả tên khách hàng bằng field displayName"
name: get_customer_v2
request:
  method: GET
  url: /api/v2/customers/CUS-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CUS-1001
    displayName: An
~~~

Hai contracts minh họa hai endpoint được version hóa. Nếu project dùng cùng endpoint và dual-write, hãy viết scenario tương ứng với behavior thật, không copy cả V1/V2 endpoint nếu API không cung cấp chúng.

### Producer verification kiểm tra điều gì?

Generated producer tests sẽ kiểm tra:

- V1 vẫn trả field `name` khi V1 được hỗ trợ.
- V2 trả field `displayName`.
- Các field và JSON types đúng contract.
- Endpoint/method/status/header đúng.

Nếu producer đã bỏ V1 route, contract V1 test phải FAIL — đó là tín hiệu có chủ đích cần xử lý theo deprecation plan, không phải xóa test để làm CI xanh.

## 18. Contract cho request: producer cần chấp nhận tên cũ trong giai đoạn chuyển tiếp

Một request V1:

~~~yaml
description: "Tạo khách hàng với field name cũ"
name: create_customer_legacy_name
request:
  method: POST
  url: /api/customers
  headers:
    Content-Type: application/json
  body:
    customerId: CUS-1001
    name: An
response:
  status: 201
  body:
    id: CUS-1001
~~~

Một request V2:

~~~yaml
description: "Tạo khách hàng với field displayName mới"
name: create_customer_display_name
request:
  method: POST
  url: /api/customers
  headers:
    Content-Type: application/json
  body:
    customerId: CUS-1002
    displayName: Bình
response:
  status: 201
  body:
    id: CUS-1002
~~~

Khi producer hỗ trợ cả hai, cả hai producer scenarios cần PASS. Điều này chứng minh server nhận được hai hình thức request đã thỏa thuận.

### Nếu producer chỉ chấp nhận tên mới

Generated test V1 sẽ fail khi gửi `name`. Nếu còn consumer cũ được hỗ trợ, đây là breaking change. Không được xóa contract V1 cho đến khi có quyết định deprecation và consumer inventory xác nhận.

## 19. Contract cho thay kiểu dữ liệu

V1:

~~~yaml
description: "V1 trả amount dưới dạng chuỗi"
name: get_order_v1
request:
  method: GET
  url: /api/v1/orders/ORD-1001
response:
  status: 200
  body:
    id: ORD-1001
    amount: "125000"
    currency: VND
~~~

V2 dùng một field mới và semantics rõ:

~~~yaml
description: "V2 trả amountMinor dưới dạng số nguyên"
name: get_order_v2
request:
  method: GET
  url: /api/v2/orders/ORD-1001
response:
  status: 200
  body:
    id: ORD-1001
    amountMinor: 125000
    currency: VND
~~~

Trong ví dụ V2, `amountMinor` phải được định nghĩa đơn vị rõ ràng trong API documentation. Không tự suy luận rằng `125000` luôn là 125.000 đồng nếu domain có minor units khác.

### Contract tests phải phân biệt JSON types

Các body sau khác nhau:

~~~json
{"amount":"125000"}
~~~

~~~json
{"amount":125000}
~~~

Nếu consumer cũ cần string và producer mới trả number tại cùng field, consumer contract V1 cần được giữ để phát hiện breaking change cho đến khi consumer được nâng cấp hoặc API version mới được chọn.

## 20. Consumer contract tests với Stub Runner

Producer generated tests xác minh **producer đáp ứng contract**. Consumer tests cần xác minh **consumer code hoạt động với stub của producer**.

Ví dụ consumer test HTTP có thể cấu hình Stub Runner:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.customers:customer-service:2.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CustomerClientContractTest {

    @Autowired
    private CustomerClient customerClient;

    @Test
    void readsCustomerDisplayName() {
        CustomerView view =
            customerClient.getCustomer("CUS-1001");

        assertThat(view.getDisplayName()).isEqualTo("An");
    }
}
~~~

Đây là **khung minh họa**; cần có client wiring, endpoint/port phù hợp với Stub Runner, imports và test dependencies của project. Stub phải chứa mapping tương ứng với request client gửi.

### Kiểm tra nhiều thế hệ stub

Một consumer mới trong giai đoạn migration có thể cần chạy với:

- Stub producer cũ (field `name`).
- Stub producer chuyển tiếp (cả `name` và `displayName` nếu consumer tolerance cho phép).
- Stub producer mới (field `displayName`).

Mục tiêu là xác nhận consumer dual-read thực sự xử lý tất cả versions còn được hỗ trợ. Chỉ test stub mới sẽ không phát hiện consumer cần fallback cho producer cũ.

## 21. Ma trận producer–consumer compatibility

Một ma trận đơn giản cho response rename:

| Producer response | Consumer cũ chỉ đọc `name` | Consumer mới đọc cả hai |
| --- | --- | --- |
| Producer cũ chỉ `name` | PASS | PASS |
| Producer dual-write | PASS nếu consumer tolerant unknown fields | PASS |
| Producer mới chỉ `displayName` | FAIL | PASS |

Nếu consumer cũ strict unknown-field, ô dual-write có thể **FAIL**. Khi đó cần nâng consumer strict trước khi producer phát thêm field, hoặc dùng versioned endpoint/topic.

### Ma trận cho request rename

| Consumer request | Producer cũ chỉ nhận `name` | Producer mới nhận cả hai | Producer mới chỉ nhận `displayName` |
| --- | --- | --- | --- |
| Consumer cũ gửi `name` | PASS | PASS | FAIL |
| Consumer mới gửi `displayName` | FAIL | PASS | PASS |

Hai ma trận cho thấy lý do phải **migrate theo đúng chiều dữ liệu**. Không thể dùng một rollout order chung cho mọi trường hợp.

## 22. Quy trình expand – migrate – contract

Đây là chiến lược triển khai thay đổi schema khi producer và consumer không deploy đồng thời.

~~~mermaid
flowchart TD
    A["Current: only old field"] --> B["EXPAND: support old + new"]
    B --> C["MIGRATE: consumers switch to new field"]
    C --> D["OBSERVE: no supported consumer uses old field"]
    D --> E["CONTRACT: remove old field"]
    E --> F["Verify old contracts retired intentionally"]
~~~

### Với request rename

1. **Expand producer:** nhận cả tên cũ và tên mới.
2. **Migrate consumers:** cập nhật request DTO/client để gửi tên mới.
3. **Observe:** đếm request còn dùng tên cũ.
4. **Contract producer:** ngừng chấp nhận tên cũ sau khi consumer đã migrate.
5. Xóa alias và V1 request contract theo chính sách deprecation.

### Với response rename

1. **Migrate consumers trước:** consumer đọc được cả tên cũ và mới, nhưng producer vẫn chỉ gửi tên cũ.
2. Xác nhận mọi consumer strict đã được nâng cấp.
3. **Expand producer:** bắt đầu gửi tên mới; có thể giữ tên cũ trong giai đoạn dual-write.
4. **Migrate consumers:** chuyển business logic ưu tiên tên mới.
5. **Observe:** xác nhận consumer versions còn hỗ trợ đã đọc field mới.
6. **Contract producer:** ngừng gửi tên cũ.
7. Khi không còn producer cũ được hỗ trợ, consumer có thể bỏ fallback.

Nếu consumer strict unknown fields, không bật dual-write trước khi nâng chúng hoặc chuyển sang API version riêng.

### Với type change

1. Bổ sung field mới với type/semantics rõ.
2. Consumer đọc được cả field cũ và mới.
3. Producer phát cả hai nếu consumer cũ tolerant; nếu không, version hóa.
4. Consumer migrate sang field mới.
5. Theo dõi usage và đối chiếu giá trị giữa hai fields.
6. Ngừng field cũ sau khi migration hoàn tất.

**Không đổi type tại cùng field name khi consumer versions cũ còn được hỗ trợ**, trừ khi có một cơ chế version negotiation rõ ràng.

## 23. Theo dõi usage và deprecation

Không xóa field chỉ vì đã đổi DTO. Cần bằng chứng:

- Request metrics cho field cũ: có consumer nào còn gửi?
- Consumer inventory: service nào deserialize hoặc sử dụng field cũ?
- Event replay policy: event cũ còn có thể được phát lại không?
- Consumer release versions: có bản cũ nào còn chạy?
- Logs/metrics: có thể quan sát fallback path không?
- API owners: ai phê duyệt thời điểm kết thúc hỗ trợ?

### Đo fallback usage ở consumer

Consumer dual-read có thể ghi metric:

~~~java
if (requestUsesLegacyName) {
    migrationMetrics.incrementLegacyNameUsage();
}
~~~

Đây là pseudocode minh họa; metric cần tránh ghi giá trị PII hoặc cardinality cao. Mục tiêu là đếm **số lần sử dụng đường tương thích cũ**, không log nội dung tên khách hàng.

### Deprecation có owner và deadline

Một kế hoạch deprecation nên ghi:

- Field cũ và field thay thế.
- Producer/consumer owners.
- Ngày bắt đầu cảnh báo.
- Phiên bản tối thiểu phải nâng.
- Thời gian quan sát không còn usage.
- Kế hoạch xử lý consumer không migrate.
- Ngày loại bỏ và rollback strategy.

Nếu không có khả năng xác định consumer usage, hãy dùng versioned API/event hoặc thời gian hỗ trợ được thống nhất rõ.

## 24. Message contracts và schema evolution

Với event, có thể bổ sung schema version:

~~~yaml
description: "Customer updated event V2"
label: customer_updated_v2
outputMessage:
  sentTo: customers.updated.v2
  headers:
    contentType: application/json
  body:
    eventId: EVT-CUS-1001
    eventType: CUSTOMER_UPDATED
    schemaVersion: 2
    customerId: CUS-1001
    displayName: An
~~~

Một message contract cũ có thể tiếp tục mô tả V1:

~~~yaml
description: "Customer updated event V1"
label: customer_updated_v1
outputMessage:
  sentTo: customers.updated.v1
  headers:
    contentType: application/json
  body:
    eventId: EVT-CUS-1001
    eventType: CUSTOMER_UPDATED
    schemaVersion: 1
    customerId: CUS-1001
    name: An
~~~

### Version field không tự tạo compatibility

`schemaVersion: 2` chỉ có ý nghĩa nếu producer/consumer thực sự định tuyến hoặc xử lý theo version. Nó không tự làm một parser cũ chấp nhận payload mới.

Với message migration, có thể:

- Giữ consumer hỗ trợ V1 và V2.
- Dùng topic/destination riêng cho V2.
- Dual-publish có kiểm soát trong thời gian chuyển tiếp.
- Bảo đảm idempotency khi cùng nghiệp vụ được phát qua hai event versions.
- Giữ logic replay cho V1 trong thời hạn cần thiết.

Không dual-publish mà không có chiến lược deduplicate; consumer có thể xử lý cùng một business event hai lần.

## 25. Các tình huống không nên dùng dual-write

Dual-write hữu ích nhưng không phải lúc nào cũng an toàn:

- Consumer cũ strict unknown-field.
- Hai field mới/cũ có semantics khác nhau, không thể biểu diễn cùng một giá trị.
- Field cũ chứa PII không còn được phép phát.
- Dữ liệu lớn làm tăng payload/chi phí đáng kể.
- Producer không thể bảo đảm hai field nhất quán.
- Event replay khiến hai schema tồn tại lâu hơn thời gian migration.
- Security policy cấm duy trì field cũ.

Trong những trường hợp này, cân nhắc **versioned endpoint, media type, topic hoặc event type**. Nếu phải ngừng field cũ ngay vì security/privacy, cần có migration plan khẩn cấp và phối hợp consumer owners; không kéo dài deprecation chỉ vì tiện lợi.

## 26. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Đổi tên field và deploy producer trước | Consumer cũ nhận null/missing | Producer dual-read cho request; consumer dual-read trước với response |
| Xóa field vì “không thấy dùng” | Bỏ sót consumer gián tiếp | Inventory và telemetry |
| Đổi string thành number cùng field | Consumer cũ parse fail/coerce sai | Field mới hoặc versioned contract |
| Thêm field response mà không kiểm tra strict parser | Consumer cũ từ chối unknown property | Nâng consumer trước hoặc version hóa |
| Dùng default value che missing field | Business logic nhận dữ liệu giả | Phân biệt missing/null và validate |
| Giữ alias vĩnh viễn | Contract và DTO khó hiểu | Deprecation owner/deadline |
| Chỉ test producer mới | Không biết consumer cũ có đọc được không | Consumer matrix với stub mới |
| Chỉ test consumer mới với stub mới | Không phát hiện cần fallback producer cũ | Test old/new stub |
| Xóa contract V1 để làm CI xanh | Mất bằng chứng regression | Retire có phê duyệt sau migration |
| Thêm cả field cũ và mới không định nghĩa precedence | Payload mâu thuẫn | Validate consistency |
| Dual-publish event nhưng không idempotent | Xử lý nghiệp vụ hai lần | Event ID/deduplication |
| Đổi đơn vị nhưng giữ field name/type | Sai số nghiệp vụ | Tên field/semantics mới, documentation và tests |

## 27. Ví dụ một migration end-to-end

Giả sử Customer Service trả `name` và muốn chuyển sang `displayName`.

### Trạng thái ban đầu

Producer response:

~~~json
{"id":"CUS-1001","name":"An"}
~~~

Consumer V1 DTO chỉ có `name`.

### Giai đoạn A — Nâng consumer trước

Consumer V2 DTO:

~~~java
public class CustomerView {
    private String id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    // getters/setters
}
~~~

Consumer V2 vẫn chạy được với response producer cũ. Test consumer với stub V1 phải PASS.

### Giai đoạn B — Producer dual-write

Producer response:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "displayName": "An"
}
~~~

Consumer V2 đọc `displayName`, fallback `name`. Consumer V1 strict parser phải được nâng trước hoặc có route V1 riêng.

### Giai đoạn C — Consumer migrate

Consumer business logic chỉ dùng `displayName`. Metric fallback cho `name` giảm về zero trong các consumer còn hỗ trợ.

### Giai đoạn D — Producer bỏ field cũ

Producer response:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

Generated producer tests của contract mới PASS. Consumer V2 tests với stub mới PASS.

### Giai đoạn E — Dọn consumer fallback

Khi không còn producer V1 hoặc dual-write nào nằm trong phạm vi hỗ trợ, consumer có thể xóa `@JsonAlias("name")` và các legacy tests. Ghi nhận rõ ngày V1 contract được retire.

**Không bỏ qua Giai đoạn A nếu consumer V1 còn strict**: việc thêm `displayName` trong response dual-write có thể làm consumer cũ fail trước khi nó kịp migrate.

## 28. Kiểm tra thay đổi type bằng consumer tests

Giả sử producer thêm `amountMinor` trong khi giữ `amount` string.

Consumer V2 có thể hỗ trợ:

~~~java
public class OrderView {
    private String orderId;
    private String amount;

    @JsonProperty("amountMinor")
    private Long amountMinor;

    public long effectiveAmountMinor() {
        if (amountMinor != null) {
            return amountMinor;
        }
        return Long.parseLong(amount);
    }

    // getters/setters
}
~~~

Đây chỉ là ví dụ đơn giản. Trong production, cần:

- Định nghĩa currency/unit.
- Kiểm tra overflow.
- Xác định rounding/scale.
- Xử lý null/missing/invalid string.
- Không parse một giá trị sai rồi mặc định thành zero.
- Có validation và lỗi rõ ràng.

Consumer tests cần chạy với:

- Stub V1 chỉ có `amount`.
- Stub chuyển tiếp có `amount` và `amountMinor`.
- Stub V2 chỉ có `amountMinor` nếu consumer vẫn phải hỗ trợ V2.

Nếu consumer chỉ cần hỗ trợ V2 sau một major release, hãy ghi rõ compatibility boundary thay vì giữ fallback vô thời hạn.

## 29. Kiểm tra breaking change trong CI

~~~mermaid
flowchart TD
    A["PR thay đổi DTO/contract"] --> B["Review schema diff"]
    B --> C["Phân loại request/response/message"]
    C --> D["Producer generated contract tests"]
    D --> E{"Old + new scenarios PASS?"}
    E -->|Không| X["BLOCK / migration chưa hoàn tất"]
    E -->|Có| F["Package immutable stub artifact"]
    F --> G["Consumer matrix: old/new consumers"]
    G --> H{"Required consumer cells PASS?"}
    H -->|Không| X
    H -->|Có| I["Telemetry/deprecation gate"]
    I --> J{"Old field usage = 0 trong phạm vi hỗ trợ?"}
    J -->|Không| K["Giữ compatibility path"]
    J -->|Có| L["Approve contract/removal"]
~~~

### Producer CI

- Sinh và chạy contract scenarios cho field cũ/new trong giai đoạn chuyển tiếp.
- Kiểm tra JSON type, null/missing và field presence.
- Đảm bảo producer nhận request cũ/new nếu đã cam kết.
- Kiểm tra response/event vẫn có các field cần cho consumers cũ.
- Ghi producer commit và contract revision.

### Consumer CI

- Chạy consumer code với stub producer cũ.
- Chạy consumer code với stub producer chuyển tiếp.
- Chạy consumer code với stub producer mới.
- Kiểm tra business outcome, không chỉ deserialization thành công.
- Đánh dấu rõ consumer versions còn được hỗ trợ.
- Không dùng stub cache/SNAPSHOT khác bytes mà không ghi provenance.

### Removal gate

Không xóa field cũ nếu:

- Consumer được hỗ trợ còn dùng nó.
- Contract cũ vẫn là acceptance criterion.
- Message replay window chưa kết thúc.
- Không có telemetry/inventory đủ tin cậy.
- Rollback không thể khôi phục response/schema cũ.

## 30. Ma trận rollout mẫu

Một record migration có thể được nhóm tự thiết kế:

~~~yaml
change:
  field_old: name
  field_new: displayName
  direction: response
  producer: customer-service

compatibility:
  old_producer_old_consumer: PASS
  old_producer_new_consumer: REQUIRED
  dual_write_producer_old_consumer: CHECK_UNKNOWN_FIELD_POLICY
  dual_write_producer_new_consumer: REQUIRED
  new_producer_new_consumer: REQUIRED

migration:
  consumers_dual_read_deployed: false
  producer_dual_write_enabled: false
  legacy_usage_observed: true
  removal_approved: false
~~~

Đây là **metadata quản lý migration do nhóm định nghĩa**, không phải file cấu hình mặc định của Spring Cloud Contract. Các giá trị phải được cập nhật theo CI, telemetry và owner approvals thực tế.

### Không coi NOT_RUN là PASS

Trong ma trận, các ô chưa chạy phải ghi `NOT_RUN` hoặc `BLOCKED`. Không đánh dấu PASS chỉ vì consumer team chưa cung cấp test.

## 31. Quy trình review PR đổi tên, xóa hoặc thay kiểu

Reviewer nên hỏi:

1. Field nằm trong request, response hay event?
2. Consumer nào đang dùng field cũ?
3. Thay đổi có làm JSON type/semantics đổi không?
4. Có strict unknown-property deserializer không?
5. Missing/null/default behavior đã được định nghĩa chưa?
6. Có giữ tương thích với producer/consumer versions cũ không?
7. Contract scenarios cũ có còn chạy không?
8. Consumer Stub Runner tests có dùng đúng stub mới không?
9. Nếu dual-write, hai field có nhất quán không?
10. Nếu dual-publish, idempotency có được bảo vệ không?
11. Telemetry chứng minh old field không còn được sử dụng chưa?
12. Có owner, deadline và rollback strategy không?

Một PR chỉ sửa DTO mà không cập nhật contract/consumer tests có thể bỏ sót breaking change. Ngược lại, một PR xóa contract cũ chỉ để tests PASS không phải bằng chứng migration đã hoàn tất.

## 32. Bài tập thực hành

### Bài tập A — Đổi tên response field

Producer đổi `name` thành `displayName`. Consumer cũ chỉ có field `name`.

**Yêu cầu:** mô tả ít nhất hai cách triển khai an toàn và điều kiện của từng cách.

**Gợi ý:** consumer dual-read trước; producer dual-write nếu consumer cũ tolerant; hoặc version hóa endpoint nếu consumer strict.

### Bài tập B — Đổi tên request field

Consumer cũ gửi `name`; consumer mới gửi `displayName`.

**Yêu cầu:** producer cần triển khai theo thứ tự nào?

**Gợi ý:** producer nhận cả hai trước, sau đó migrate consumers, đo usage cũ rồi mới bỏ alias.

### Bài tập C — Xóa response field

Producer muốn xóa `legacyCode`, nhưng một consumer dùng nó để quyết định ưu tiên vận chuyển.

**Yêu cầu:** vì sao compile thành công không đủ? Cần thu thập bằng chứng gì?

**Gợi ý:** inventory consumer/business usage, consumer tests, telemetry và owner confirmation.

### Bài tập D — String thành number

`amount` đổi từ `"125000"` thành `125000`.

**Yêu cầu:** nêu các failure modes ở consumer và đề xuất schema transition.

**Gợi ý:** type mismatch/coercion/precision; field mới có unit rõ hoặc API version mới.

### Bài tập E — Thêm field response

Producer thêm `displayName` nhưng consumer cũ bật strict unknown properties.

**Yêu cầu:** vì sao thêm field vẫn có thể breaking? Đề xuất rollout.

**Gợi ý:** nâng consumer tolerant trước hoặc tách versioned endpoint.

### Bài tập F — Null thành missing

Producer đổi `middleName: null` thành bỏ hẳn field.

**Yêu cầu:** tìm ví dụ business semantics khiến hai trường hợp khác nhau.

**Gợi ý:** PATCH, defaulting, explicit clear và fallback logic.

### Bài tập G — Đổi đơn vị nhưng không đổi type

`duration` vẫn là number nhưng đổi từ giây sang milliseconds.

**Yêu cầu:** contract test chỉ kiểm type có phát hiện được không? Cần bổ sung gì?

**Gợi ý:** semantic/value range, field mới hoặc documentation version; test đơn vị cụ thể.

### Bài tập H — Event replay

Consumer mới bỏ field `name` nhưng broker/archive vẫn có event V1 được replay.

**Yêu cầu:** migration cần xét những khoảng thời gian nào?

**Gợi ý:** retention, replay window, consumer version support và V1 schema handler.

### Bài tập I — Dual-write và strict parser

Producer phát cả `name` và `displayName`. Một consumer cũ từ chối unknown fields.

**Yêu cầu:** có nên bật dual-write không?

**Gợi ý:** không trước khi consumer strict được nâng hoặc có route/version riêng.

### Bài tập J — Consumer matrix

Có ba consumer versions: Checkout 1.8, Checkout 2.0 và Portal 4.1. Producer sắp bỏ `legacyCode`.

**Yêu cầu:** thiết kế ma trận test và tiêu chí để xóa field.

**Gợi ý:** từng consumer version được hỗ trợ chạy với stub mới; NOT_RUN không phải PASS; yêu cầu telemetry/inventory.

### Bài tập K — Request alias xung đột

Request chứa cả `name` và `displayName` nhưng giá trị khác nhau.

**Yêu cầu:** thiết kế validation policy.

**Gợi ý:** reject conflict hoặc định nghĩa precedence rõ; không phụ thuộc JSON property order.

### Bài tập L — Enum mở rộng

Producer thêm status `REFUNDED`. Consumer cũ parse enum strict.

**Yêu cầu:** đây có phải thay đổi kiểu dữ liệu? Có thể phá consumer không?

**Gợi ý:** JSON type vẫn string nhưng tập giá trị đã đổi; test unknown enum handling.

## 33. Checklist trước khi xóa field cũ hoặc đổi schema

### Đánh giá tác động

- [ ] Xác định field nằm ở request, response hay message event.
- [ ] Xác định tất cả consumers và versions còn được hỗ trợ.
- [ ] Kiểm tra field được dùng trực tiếp và gián tiếp trong business logic.
- [ ] Phân biệt field missing, null và empty.
- [ ] Kiểm tra strict/lenient deserialization của consumer.
- [ ] Xác định type, format, unit, precision và enum semantics.
- [ ] Xem retention/replay window nếu field thuộc event.

### Thiết kế migration

- [ ] Có field mới hoặc versioned endpoint/topic nếu semantics/type đổi lớn.
- [ ] Producer nhận cả tên request cũ/mới trước khi consumers gửi tên mới.
- [ ] Consumer dual-read trước khi producer đổi response.
- [ ] Dual-write chỉ bật khi consumer cũ chấp nhận unknown fields.
- [ ] Nếu strict consumers, có kế hoạch version routing hoặc nâng consumers trước.
- [ ] Có policy khi request gửi đồng thời hai field.
- [ ] Có owner, deadline, telemetry và rollback plan.
- [ ] Không dual-publish event nếu chưa có idempotency strategy.

### Contract và kiểm thử

- [ ] Producer contracts mô tả request/response/event cũ và mới trong giai đoạn chuyển tiếp.
- [ ] Generated producer tests xác minh field names và JSON types.
- [ ] Consumer Stub Runner tests dùng đúng stub versions.
- [ ] Consumer old/new versions được chạy trong compatibility matrix.
- [ ] Business assertions kiểm tra kết quả, không chỉ deserialize thành công.
- [ ] Negative tests phát hiện missing/wrong-type/null/unknown-enum khi phù hợp.
- [ ] Stub artifact có version, contract revision và checksum truy vết được.
- [ ] Contract cũ chỉ được retire sau approval, không xóa để làm CI xanh.

### Điều kiện xóa field

- [ ] Không còn consumer được hỗ trợ phụ thuộc field cũ.
- [ ] Request usage/consumer telemetry đã được đánh giá.
- [ ] Message replay window và archive requirements đã kết thúc hoặc được xử lý.
- [ ] Consumer versions cần thiết đã PASS với schema mới.
- [ ] Rollback và deprecation completion được ghi lại.
- [ ] CI gate chặn nếu có compatibility cell bắt buộc chưa chạy.

## Kết luận

Đổi tên, xóa field và thay kiểu dữ liệu là những thay đổi **wire contract**, không chỉ là refactor DTO. Chúng cần được đánh giá theo chiều request/response/message, parser behavior và các consumer versions thực sự đang hoạt động. Đặc biệt, thêm field mới cũng có thể phá consumer strict; đổi type có thể làm parser coercion che một lỗi semantics; và xóa field có thể làm business logic sai dù HTTP vẫn trả 200.

Với Spring Cloud Contract, hãy giữ các scenarios cũ trong giai đoạn migration, bổ sung scenarios cho schema mới, chạy generated producer tests, đóng gói stub artifact có provenance và kiểm tra consumer versions bằng Stub Runner. Chỉ loại bỏ field cũ khi **consumer inventory, telemetry, contract tests và owner approval** đều xác nhận migration hoàn tất.

**Ghi nhớ:** *Producer nhận request cũ/mới trước khi consumer chuyển; consumer đọc response cũ/mới trước khi producer đổi; thay kiểu hoặc semantics nên có field/version rõ; và chỉ xóa đường tương thích cũ khi mọi consumer còn được hỗ trợ đã được kiểm chứng.*
