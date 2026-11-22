# Deprecation header và liên kết tài liệu chuyển đổi

REST API đã có **/v2/orders/{id}** nhưng nhiều ứng dụng vẫn gọi **/v1/orders/{id}**. Nếu chỉ công bố qua email, client mobile/đối tác có thể bỏ lỡ và lỗi khi v1 ngừng phục vụ.

HTTP có thể phát tín hiệu **ngay trong response**: **Deprecation** thông báo mốc không còn khuyến nghị, **Link rel="deprecation"** dẫn tới hướng dẫn chuyển đổi, **Sunset** nêu ngày ngừng dự kiến. Chúng hỗ trợ cảnh báo, không thay quy trình migration.

Bài thuộc chương **Tiến hóa API** của **INTEGRATION_API_REST**, kết hợp HTTP, Java/Spring, OpenAPI, bảo mật và kiểm thử chuyển đổi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **deprecated**, **sunset**, **removed** và các loại thay đổi tương thích/phá vỡ hợp đồng.
2. Viết đúng **Deprecation response header** theo **RFC 9745** và liên kết tài liệu bằng **Link relation deprecation** theo Web Linking.
3. Phân biệt định dạng thời gian **Deprecation** và **Sunset** (RFC 8594), cùng ý nghĩa vận hành của từng mốc.
4. Thiết kế trang migration gồm mapping endpoint/payload/status, quyền, pagination, cache, idempotency và hướng dẫn rollback.
5. Dùng Spring MVC để trả header theo đúng resource/operation đang chuyển đổi, không gắn bừa cho API còn được hỗ trợ.
6. Đảm bảo header qua gateway/CDN/CORS, không rò token/dữ liệu nội bộ và không gây lỗi client cũ.
7. Kiểm thử việc xuất hiện header, tài liệu chuyển đổi, thông báo lịch trình, 304/cache và các tình huống cắt phiên bản.

## 2. Tín hiệu vòng đời API: thay đổi lời khuyên hay thay đổi khả dụng?

**Deprecation** là trạng thái một resource hoặc bề mặt API **đã hoặc sẽ không còn được khuyến nghị cho sử dụng mới**. Client cũ **vẫn có thể được phục vụ** trong giai đoạn chuyển tiếp. **Sunset** là mốc thời gian mà nhà cung cấp dự kiến resource sẽ **không còn khả dụng**. Việc thực sự trả **404, 410 hoặc lỗi hợp đồng** sau mốc đó phụ thuộc quyết định rollout, không tự phát sinh chỉ vì thêm header.

| Trạng thái | Tín hiệu HTTP | Hành vi mà client nên hiểu |
|---|---|---|
| Hoạt động, được khuyến nghị | Không nhất thiết có Deprecation | Dùng theo hợp đồng hiện tại |
| Sẽ bị deprecate | Deprecation mang thời điểm trong tương lai | Lập kế hoạch chuyển đổi trước mốc đó |
| Đã deprecate, vẫn phục vụ | Deprecation mang thời điểm đã qua | Ngừng tích hợp mới, ưu tiên nâng cấp |
| Dự kiến ngừng phục vụ | Có thể thêm Sunset | Hoàn tất migration trước mốc ngừng |
| Đã ngừng phục vụ | Trả status thực tế theo hợp đồng (ví dụ 410/404) | Chuyển sang tài nguyên thay thế |

**Deprecation không phải lỗi HTTP:** GET v1 vẫn có thể trả 200, POST v1 vẫn có thể trả 201. Header không thay authorization, validation hoặc status code nghiệp vụ.

Không phải mọi thay đổi cần deprecation. Thêm field tùy chọn có thể tương thích; xóa field bắt buộc, đổi kiểu hoặc ngữ nghĩa status/idempotency thường là **breaking change**.

## 3. Deprecation header theo RFC 9745

### 3.1. Cú pháp đúng: Structured Field Date

**Deprecation** là một HTTP response header field đã chuẩn hóa trong **RFC 9745**. Giá trị là **Structured Field Date**, được viết bằng ký tự **@** theo sau là số giây Unix epoch, chẳng hạn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1811808000

{"id":"o-918","totalAmount":359000,"currency":"VND"}
~~~

**@1811808000** là **2027-06-01T00:00:00Z**, mốc resource bắt đầu deprecated; request có thể tiếp tục hoạt động sau đó nếu chưa sunset.

Các giá trị sau **không đúng cách biểu diễn RFC 9745**:

~~~http
Deprecation: true
Deprecation: 2027-06-01
Deprecation: Tue, 01 Jun 2027 00:00:00 GMT
~~~

Deprecation dùng **Structured Field Date @epoch** (UTC), không phải HTTP-date của Sunset hay RFC 3339 trong JSON.

### 3.2. Phạm vi áp dụng và phản hồi

Theo mô hình RFC, tín hiệu deprecation liên quan đến **resource trong ngữ cảnh HTTP**, không tự tuyên bố toàn bộ miền **api.example.test** sắp ngừng. Một số trường hợp điển hình:

- Chỉ **/v1/orders/{id}** và collection **/v1/orders** bị thay thế: đánh dấu đúng nhóm tài nguyên này.
- Chỉ một thao tác POST nghiệp vụ chuyển đổi trong khi GET vẫn được hỗ trợ: phải **công bố phạm vi operation** trong chính sách và ví dụ; không phát header một cách khiến người dùng tưởng toàn API bị bỏ.
- Một API version được sunset toàn phần: có thể cấu hình nhất quán trên tập route thuộc version đó, nhưng vẫn cần phân biệt các route còn được hỗ trợ.

Khi response trả 304 do conditional GET, cache và client có thể cần thông tin header cập nhật để biết deprecation. Cần kiểm thử **các đường đi 200/304 và qua cache**; không chỉ nhìn output controller khi không có ETag. Với API có tác động nghiệp vụ, cũng nên xác minh header trên các **2xx** liên quan và chính sách lỗi để client nhận cảnh báo theo kỳ vọng.

### 3.3. Deprecation không có nghĩa xóa ngay

Việc thêm:

~~~http
Deprecation: @1811808000
~~~

không tự chuyển mọi request sau ngày 1/6/2027 thành 410 Gone. Để thay đổi availability, nhóm backend vẫn cần cập nhật routing, kế hoạch sunset, thông báo cho đối tác, hỗ trợ rollback và giám sát lỗi.

Nếu nhà cung cấp quyết định lùi lịch deprecation, phải cập nhật header, tài liệu và changelog một cách nhất quán. **Tín hiệu HTTP không thay thế cam kết SLA/hợp đồng pháp lý** của đối tác.

## 4. Link relation deprecation: đưa hướng dẫn chuyển đổi vào response

**Link** là HTTP header theo **RFC 8288**. Với relation **deprecation**, response có thể trỏ đến một tài nguyên mô tả chính sách, thay đổi và cách migration:

~~~http
HTTP/1.1 200 OK
Deprecation: @1811808000
Link: <https://developers.example.test/migrations/orders-v1-to-v2>; rel="deprecation"; type="text/html"
Content-Type: application/json

{"id":"o-918","totalAmount":359000,"currency":"VND"}
~~~

Client có thể tìm **Link** với relation `deprecation`, mở tài liệu thay vì chỉ hiển thị một warning không có hành động. Link **không nhất thiết** là URL của API v2; nó thường là **hướng dẫn chuyển đổi**. Tài liệu nên có link riêng tới OpenAPI v2, SDK, changelog và nơi liên hệ hỗ trợ.

Có thể thêm relation phiên bản kế tiếp:

~~~http
Link: <https://developers.example.test/migrations/orders-v1-to-v2>; rel="deprecation"
Link: <https://api.example.test/v2/orders/o-918>; rel="successor-version"
~~~

**successor-version** chỉ nên trỏ sang order v2 khi **resource và quyền tương ứng thực sự tồn tại**; không mặc định ID ánh xạ 1:1. Nếu chưa chắc, chỉ dùng link tài liệu.

### 4.1. Nội dung trang deprecation/migration tối thiểu

Trang tài liệu cần tự trả lời được:

1. **Phạm vi:** operation/route/media type/version nào bị ảnh hưởng; loại client nào; mốc deprecation và sunset UTC.
2. **Lý do:** vấn đề cũ (ví dụ trường tiền không gắn đơn vị, quyền truy cập chưa rõ), lợi ích/cảnh báo của cách mới.
3. **Thay thế:** URI, HTTP method, schema, auth scope, error format, paging/cache/idempotency tương ứng.
4. **Mapping:** bảng field và response từ v1 → v2; ví dụ request/response trước/sau, các bước chuyển đổi dữ liệu.
5. **Khả năng tương thích:** dual-read, dual-write nếu thật sự cần và an toàn, các version SDK hỗ trợ, các thay đổi không tự động.
6. **Kiểm thử:** contract test, staging/sandbox, cách xác minh không còn traffic v1 và tiêu chí rollout/cutover.
7. **Hỗ trợ:** owner, kênh báo lỗi, changelog, lịch cập nhật và quy trình xin ngoại lệ có thời hạn.

Tài liệu có thể trả HTML cho người đọc, còn OpenAPI/JSON schema có thể được liên kết từ đó cho máy. **Đảm bảo link ổn định, HTTPS, không trả 404**, và có bản lưu phù hợp với các ứng dụng client cũ. Không để đường dẫn tài liệu chuyển đổi chỉ tồn tại trên mạng nội bộ mà bên đối tác không truy cập được.

### 4.2. Vừa có tài liệu vừa có contract máy đọc được

~~~mermaid
flowchart LR
    A["GET /v1/orders/{id}"] --> B["200 + Deprecation + Link"]
    B --> C["Client/SDK nhận biết cảnh báo"]
    C --> D["Đọc migration guide"]
    D --> E["OpenAPI v2 + examples"]
    E --> F["Nâng cấp client/test"]
    F --> G["Gọi v2 và theo dõi lỗi"]
~~~

**Link rel=deprecation** là tín hiệu khám phá tài liệu; nó không tự chuyển GET/POST sang endpoint v2, cũng không làm SDK được nâng cấp. Hãy xem header là **kênh truyền thông runtime**, còn migration guide và kiểm thử là **kế hoạch thay đổi thực tế**.

## 5. Sunset: đừng nhầm với thời điểm deprecation

**Sunset** theo **RFC 8594** công bố thời gian mà resource **dự kiến không còn khả dụng**, dùng **HTTP-date**, ví dụ:

~~~http
HTTP/1.1 200 OK
Deprecation: @1811808000
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://developers.example.test/migrations/orders-v1-to-v2>; rel="deprecation"
Content-Type: application/json
Cache-Control: private, no-store

{"id":"o-918","totalAmount":359000,"currency":"VND"}
~~~

Trong ví dụ:

| Mốc | Thời điểm | Hành động khuyến nghị |
|---|---|---|
| Công bố kế hoạch | Trước 01/06/2027 | Cập nhật tài liệu, thông báo trực tiếp, đo lưu lượng v1 |
| **Deprecation** | **01/06/2027 UTC** | Không phát triển tích hợp mới trên v1, chuyển client sang v2 |
| **Sunset dự kiến** | **01/01/2028 UTC** | Hoàn tất cutover, bỏ phụ thuộc v1 |
| Sau sunset | Theo quyết định rollout thực tế | Theo dõi status chính thức, xử lý traffic còn sót |

**Sunset là dự báo thời gian ngừng phục vụ**, không phải đồng hồ tự động kích hoạt việc xóa resource. Nếu deadline thay đổi, header và trang migration phải đồng bộ. Khi đã dừng, hãy trả HTTP status phù hợp với tình trạng resource/route thật; có thể giữ tài liệu và thông báo ngừng phục vụ trong giai đoạn chuyển tiếp.

**Khác biệt về cú pháp:** Deprecation dùng **@Unix-seconds**; Sunset dùng **HTTP-date**. Không viết `Sunset: @1830297600` hoặc `Deprecation: Sat, 01 Jan 2028 00:00:00 GMT`.

### 5.1. Kết hợp HTTP status đúng ngữ nghĩa

| HTTP status | Ý nghĩa thực | Liên quan tới deprecation |
|---|---|---|
| **200 OK** | Request đọc thành công | Có thể vẫn phát Deprecation/Link |
| **201 Created** | Resource mới đã tạo | Có thể phát warning nếu POST v1 còn hoạt động |
| **204 No Content** | Thành công không có body | Header vẫn có thể truyền thông tin migration |
| **301/308 redirect** | Chuyển địa chỉ theo quy tắc redirect | **Không tự động dùng** để thay v1 bằng v2 khi semantics thay đổi |
| **404 Not Found** | Resource không có/current representation không tìm thấy | Không tự suy là “deprecated” |
| **410 Gone** | Resource không còn và tình trạng được cho là lâu dài | Có thể dùng khi ngừng một resource/route theo policy, không thay header deprecation |

Đặc biệt, **308 Permanent Redirect** có thể giữ method/body khi redirect nhưng vẫn **không giải quyết** thay đổi request schema, auth scope, semantics hay xử lý idempotency. Nếu v2 breaking, cần migration có chủ đích, không redirect mù từ mọi POST v1.

## 6. Thiết kế tài liệu chuyển đổi dựa trên một ví dụ cụ thể

Giả sử GET order v1 trả tổng tiền bằng số nguyên và currency ở hai trường riêng:

~~~http
GET /v1/orders/o-918 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~json
{
  "id": "o-918",
  "status": "PAID",
  "totalAmount": 359000,
  "currency": "VND"
}
~~~

Ở v2, tổng tiền được chuyển thành object và tên field nói rõ **đơn vị nhỏ nhất của tiền tệ** theo hợp đồng:

~~~http
GET /v2/orders/o-918 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~json
{
  "id": "o-918",
  "status": "PAID",
  "total": {
    "amountMinor": 359000,
    "currency": "VND"
  }
}
~~~

Một migration guide tốt không chỉ ghi “dùng URL /v2”. Nó phải mô tả **ngữ nghĩa**, ví dụ:

| Khía cạnh | V1 | V2 | Việc client cần sửa |
|---|---|---|---|
| Đường dẫn chi tiết | GET /v1/orders/{id} | GET /v2/orders/{id} | Thay entrypoint sau khi kiểm tra quyền/compatibility |
| Tổng tiền | totalAmount và currency riêng | total.amountMinor và total.currency | Cập nhật DTO, parser và phép tính |
| Trạng thái | PAID | PAID | Giữ mapping trạng thái nếu semantics không đổi |
| 404/403 | Theo hợp đồng v1 | Theo hợp đồng v2 | Không suy nhầm lỗi quyền là không tồn tại |
| Phân trang collection | page/size | cursor/limit theo ví dụ thay đổi | Theo next link/cursor được cấp, không tự tăng page |
| Bảo mật | Token với orders:read | Có thể yêu cầu scope mới | Đăng ký quyền, không đưa token vào URL |
| Caching | Chính sách theo v1 | Chính sách v2 được công bố | Không dùng nhầm bản cache/ETag giữa version |
| Request ghi | PUT/POST v1 | Theo operation v2 | Kiểm tra If-Match và Idempotency-Key; không replay mù |

Ví dụ code client thay mapping:

~~~java
// v1: totalAmount là field ở cấp root.
record OrderV1(String id, String status,
               long totalAmount, String currency) {}

// v2: total là object có đơn vị rõ ràng.
record MoneyV2(long amountMinor, String currency) {}
record OrderV2(String id, String status, MoneyV2 total) {}

// Hệ thống nghiệp vụ phải biết currency/rounding policy.
long payableMinor = orderV2.total().amountMinor();
~~~

Không tự suy rằng **359000** trong mọi currency đều tương đương cùng một số đơn vị lớn. Nếu v2 đổi **đơn vị/rounding**, tài liệu phải có quy tắc chuyển đổi và test số tiền biên; chỉ đổi tên field là không đủ.

### 6.1. Nội dung tài liệu phải tương thích với tình huống thực

Một trang chuyển đổi hữu ích có thể trình bày theo thứ tự: **“Bạn có bị ảnh hưởng không?” → “Lịch trình” → “Cần sửa gì?” → “Kiểm thử ở đâu?” → “Khi nào v1 ngừng?”**. Hướng dẫn phải giải quyết cả **pagination, ETag/conditional request, idempotency khi POST, phân quyền và lỗi Problem Details** nếu các điểm này thay đổi. Nếu không thay đổi, ghi rõ **giữ nguyên** để người dùng không tự giả định.

Đặt **ví dụ request thật** theo v1 và v2, liên kết tới OpenAPI v2 và bộ SDK tương thích. Các đoạn code mẫu không nên chứa API key, JWT thật hoặc dữ liệu khách hàng thật. Nếu có nhiều nhánh migration (mobile, đối tác, nội bộ), dùng anchor/mục riêng nhưng giữ một tài liệu canonical liên kết từ header.

### 6.2. Một lần thay đổi version không nên làm mất dữ liệu

Trong thời kỳ hai version chạy song song, backend có thể dùng chung nguồn dữ liệu nhưng phải bảo đảm:

- **Resource identity** có ánh xạ đúng; không lấy ID v1 thay vào v2 nếu hai hệ có định danh khác.
- Nếu có **dual-write**, cần chống trùng và xung đột: một retry của client không được tạo hai đơn hay hai giao dịch.
- **Backward compatibility** của schema và các client cũ được kiểm chứng; không xóa field v1 trước sunset chỉ vì v2 đã phát hành.
- **Authorization** của v2 không bị rộng hơn v1 do mapping role sai, cache không trả nhầm biểu diễn giữa user/version.

Migration guide là **hợp đồng chuyển đổi**, không phải trang giới thiệu.

## 7. Kế hoạch rollout: gửi tín hiệu, đo khả năng di chuyển, rồi sunset

Một lịch trình mẫu, không phải lịch bắt buộc:

~~~mermaid
flowchart LR
    A["Công bố v2 + guide"] --> B["Gửi Deprecation + Link"]
    B --> C["Thông báo trực tiếp + đo v1 traffic"]
    C --> D["Client migrate + contract tests"]
    D --> E{"Đã đạt tiêu chí cutover?"}
    E -->|Chưa| F["Gia hạn có kiểm soát / hỗ trợ"]
    F --> C
    E -->|Rồi| G["Sunset v1 theo kế hoạch"]
    G --> H["Theo dõi lỗi và giữ tài liệu"]
~~~

**Giai đoạn chuẩn bị:** xác định owner, danh sách operation v1, version thay thế, lý do thay đổi, mức độ tác động, deadline và tiêu chí ngoại lệ. Phải có **v2 chạy thực tế** trước khi yêu cầu partner chuyển, kèm sandbox/test data và đủ thời gian cập nhật mobile release.

**Giai đoạn thông báo:** phát Deprecation và Link đúng route, có thể thêm Sunset khi đã thống nhất lịch. Gửi email/portal/changelog cho đối tác quan trọng, vì không phải client nào cũng đọc response headers. Dựng dashboard theo **version/operation/consumer** để biết traffic giảm hay chưa.

**Giai đoạn cutover:** xác nhận phần lớn traffic đã chuyển và các client quan trọng đã pass contract test. Nếu còn traffic v1, đánh giá chủ tài khoản, mức độ rủi ro, deadline hỗ trợ và phương án ngoại lệ; **không xem số lượng request gần bằng 0 là bằng chứng duy nhất**.

**Giai đoạn ngừng:** cập nhật router/service theo chính sách đã duyệt, trả status rõ nghĩa, tiếp tục phục vụ trang migration trong thời gian hợp lý và đo error rate của cả v1 lẫn v2. Cần **rollback plan** nếu cutover gây gián đoạn không chấp nhận được.

### 7.1. Các metric đáng theo dõi

| Metric | Vì sao cần |
|---|---|
| Requests v1 theo route/method/client class | Biết surface nào còn phụ thuộc v1 |
| Tỷ lệ request v1 giảm theo tuần | Đo xu hướng migration |
| Số consumer đã xác nhận dùng v2 | Bổ sung bối cảnh mà request count không thể hiện |
| Lỗi 4xx/5xx và latency v2 | Xem v2 có đủ ổn định để ngừng v1 không |
| Số response v1 có Deprecation/Link | Kiểm tra mức độ bao phủ tín hiệu |
| Tỷ lệ 304 và cache hit v1 | Phát hiện client không nhận cảnh báo mới do cache |
| Ticket hỗ trợ, ngoại lệ deadline | Đánh giá rủi ro vận hành và pháp lý |

**Consumer ID** từ API key/tài khoản có thể giúp trao đổi hỗ trợ nhưng phải **giảm thiểu và bảo vệ dữ liệu**. Không đưa JWT, raw API key, URL chứa token hay user ID vào metric label có cardinality cao; đo theo mã đã pseudonymize và quyền truy cập thích hợp. **User-Agent** không đáng tin làm định danh duy nhất vì client có thể dùng chung hoặc tùy ý thay.

### 7.2. Nếu dời Sunset thì sao?

Đừng đổi header trên origin nhưng quên CDN, OpenAPI, changelog hoặc email khách hàng. Cập nhật **ngày UTC ở cùng nguồn cấu hình**, kiểm thử response thực qua gateway, sửa migration guide và phát thông báo thay đổi. Nếu extension chỉ dành cho một đối tác, cần giải thích **phạm vi ngoại lệ** để không gây hiểu lầm rằng mọi client đều được tiếp tục v1.

## 8. Java/Spring: phát header trên đúng route cần chuyển đổi

Ví dụ dùng **Spring Boot 3 / Java 17**. Các giá trị ngày là chính sách minh họa: deprecated từ **2027-06-01 UTC**, dự kiến sunset **2028-01-01 UTC**. Không phụ thuộc vào thời gian khởi động ứng dụng; header là metadata ổn định cho tới khi lịch được cập nhật.

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record OrderV1View(String id, String status,
                   long totalAmount, String currency) {}

interface OrdersReadService {
    // Kiểm tra tenant, principal và quyền đọc trước khi trả dữ liệu.
    OrderV1View findVisibleOrder(String id);
}

@RestController
@RequestMapping("/v1/orders")
class LegacyOrdersController {
    private static final Instant DEPRECATED_AT =
            Instant.parse("2027-06-01T00:00:00Z");
    private static final Instant SUNSET_AT =
            Instant.parse("2028-01-01T00:00:00Z");
    private static final String MIGRATION_GUIDE =
            "https://developers.example.test/migrations/orders-v1-to-v2";

    private final OrdersReadService service;

    LegacyOrdersController(OrdersReadService service) {
        this.service = service;
    }

    @GetMapping(value = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderV1View> get(@PathVariable String id) {
        OrderV1View order = service.findVisibleOrder(id);

        String deprecation = "@" + DEPRECATED_AT.getEpochSecond();
        String sunset = DateTimeFormatter.RFC_1123_DATE_TIME
                .format(SUNSET_AT.atZone(ZoneOffset.UTC));
        String link = "<" + MIGRATION_GUIDE
                + ">; rel=\"deprecation\"; type=\"text/html\"";

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Deprecation", deprecation)
                .header("Sunset", sunset)
                .header(HttpHeaders.LINK, link)
                .cacheControl(CacheControl.noStore())
                .body(order);
    }
}
~~~

Kết quả mong muốn đối với một GET v1 thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1811808000
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://developers.example.test/migrations/orders-v1-to-v2>; rel="deprecation"; type="text/html"
Cache-Control: no-store
~~~

**Tại sao không dùng @Deprecated?** Annotation **@Deprecated** của Java cảnh báo người viết mã về API Java, **không tự thêm HTTP response header**. Header phải được sinh bằng ResponseEntity, filter/interceptor/advice thích hợp hoặc gateway có cấu hình.

**Tại sao no-store?** Đơn hàng cá nhân có thể chứa dữ liệu nhạy cảm; trong ví dụ này response không nên được HTTP cache lưu. Với **catalog công khai** có thể chọn Cache-Control khác, nhưng phải đánh giá dữ liệu cũ, chính sách CDN và thời điểm công bố header. Không dùng public cache chỉ vì muốn Deprecation xuất hiện tại edge.

### 8.1. Gắn header ở controller hay gateway?

- **Controller/response advice:** rõ phạm vi theo operation, gần business contract; cần bảo đảm nhánh lỗi và 304 nếu hợp đồng yêu cầu.
- **Gateway:** thuận tiện khi deprecate nhiều route, nhưng dễ đánh dấu nhầm route mới, bỏ response tự sinh ở gateway hoặc ghi đè Link/Cache-Control.
- **Đặt trong shared policy:** dùng cấu hình chứa danh sách operation, thời điểm deprecation/sunset và guide URL; đồng bộ kiểm thử giữa backend, gateway và tài liệu.

Tránh một filter toàn cục gắn **Deprecation** cho mọi response chỉ vì path có chuỗi **/api/**. Với **Location, Link hoặc Sunset** đã có từ upstream, cần quy tắc **append/merge đúng cú pháp** thay vì ghi đè vô điều kiện.

Code minh họa giả định đã có service và bảo mật; **không chạy độc lập** vì thiếu implementation, SecurityFilterChain, exception handler và dữ liệu test. Đừng đặt token/hồ sơ thật vào migration guide hoặc log response headers.

## 9. OpenAPI và contract mà client có thể kiểm tra

OpenAPI khai báo **Deprecation, Sunset, Link** trong response headers; **deprecated: true** là cờ tài liệu tĩnh, còn header báo tín hiệu runtime.

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders/{id}:
    get:
      deprecated: true
      summary: Read order (migrate to v2)
      description: >
        See https://developers.example.test/migrations/orders-v1-to-v2
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Legacy order representation
          headers:
            Deprecation:
              description: Structured Field Date, RFC 9745
              schema:
                type: string
                example: '@1811808000'
            Sunset:
              description: HTTP-date of planned retirement
              schema:
                type: string
                example: 'Sat, 01 Jan 2028 00:00:00 GMT'
            Link:
              description: Link relation deprecation
              schema:
                type: string
                example: '<https://developers.example.test/migrations/orders-v1-to-v2>; rel="deprecation"'
          content:
            application/json:
              schema:
                type: object
        '404':
          description: Order not found or not disclosed
~~~

OpenAPI **không tự động gắn header** khi controller chạy, cũng không tự tạo migration guide. Khi đã sunset, cập nhật tài liệu để phản ánh thực trạng; không để OpenAPI vẫn hứa GET 200 trong khi route chỉ trả 410. Nếu SDK generator chỉ đọc **deprecated: true** lúc build, runtime header vẫn có ích cho những bản SDK cũ có cơ chế logging/telemetry nhận biết nó.

## 10. Bảo mật, CORS và caching của thông báo chuyển đổi

- **Tài liệu HTTPS, URL tin cậy:** Link không được xây từ host/header/query do người dùng điều khiển mà không kiểm tra; tránh open redirect, header injection và phishing tới trang migration giả.
- **Không rò dữ liệu:** Link thường trỏ guide chung, không gắn token, orderId nhạy cảm, email hoặc nội dung lỗi cá nhân vào URL docs. Nếu tài liệu riêng cho partner, kiểm soát quyền truy cập **ngay tại tài liệu**.
- **Cross-origin browser:** JavaScript không đọc được mọi response header tùy ý qua CORS. Nếu frontend khác origin cần nhận cảnh báo, cấu hình **Access-Control-Expose-Headers: Deprecation, Sunset, Link** trong chính sách CORS; vẫn cần Origin/credentials policy đúng, không bật wildcard thiếu kiểm soát.
- **Cache/CDN:** response cache cũ có thể chưa mang Deprecation/Link dù origin đã thêm. Cân nhắc invalidation/revalidation, ETag/304, Age và TTL hợp lệ; giữ **private/no-store** cho dữ liệu cá nhân.
- **Không giảm quyền khi migration:** v2 phải xác minh tenant/resource ownership. Truy cập guide/link không cấp permission mới; redirect sang host ngoài không được tự gửi Authorization của API.

Đặc biệt, nếu CDN hoặc API gateway tự tạo response **304, 429, 502/503**, hãy kiểm tra liệu thông báo vòng đời cần có mặt ở các đường này không. Không trộn dữ liệu nhạy cảm vào **public cached deprecation response** chỉ để tăng khả năng quan sát.

## 11. Kiểm thử thông báo vòng đời

| Kịch bản | Kết quả kỳ vọng |
|---|---|
| GET v1 thành công | 200, Deprecation đúng date, Link deprecation và Sunset đúng lịch |
| GET v2 tương ứng | Không bị đánh dấu deprecated nếu v2 vẫn được hỗ trợ |
| API v1 ghi dữ liệu còn phục vụ | Header đúng operation, status nghiệp vụ 201/204 không bị biến thành lỗi |
| Nếu có conditional GET | 304 và cache update theo contract, không mất cảnh báo sau revalidation |
| Qua gateway/CDN | Không mất/ghi đè Link, Sunset; timezone/format vẫn hợp lệ |
| Client có Origin khác | Trình duyệt đọc được header sau CORS hợp lệ; token không lộ |
| Mở trang hướng dẫn | HTTPS, trả nội dung chính xác, link OpenAPI/SDK không hỏng |
| Client bỏ qua header | V1 vẫn phục vụ trong giai đoạn hỗ trợ, không phá response JSON cũ |
| Lịch sunset thay đổi | Header, docs và thông báo đối tác cùng được cập nhật |
| Sau khi dừng v1 | Route trả status được duyệt, không silently redirect POST khác schema |

Ví dụ MockMvc kiểm tra một trường hợp thành công (cần fixture, principal và service stub):

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.hamcrest.Matchers.containsString;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LegacyOrderDeprecationTest {
    @Autowired MockMvc mvc;

    @Test
    void v1ResponseExposesMigrationContract() throws Exception {
        mvc.perform(get("/v1/orders/o-918"))
            .andExpect(status().isOk())
            .andExpect(header().string("Deprecation", "@1811808000"))
            .andExpect(header().string("Sunset",
                    "Sat, 01 Jan 2028 00:00:00 GMT"))
            .andExpect(header().string("Link",
                    containsString("rel=\"deprecation\"")))
            .andExpect(header().string("Cache-Control",
                    containsString("no-store")));
    }
}
~~~

Nếu Spring Security bật, phải cấu hình principal có quyền đọc đơn hoặc dùng Spring Security test support. **Test controller không chứng minh CDN/CORS tuân chuẩn**: cần integration test xuyên các tầng thực, đặc biệt sau khi thêm header mà cache vẫn phục vụ response cũ.

## 12. Bài tập: nâng cấp API đơn hàng của đối tác

Một nền tảng muốn chuyển GET/POST **/v1/orders** sang **/v2/orders**. V1 dùng trường **totalAmount**, v2 dùng **total.amountMinor**; POST v2 bổ sung **Idempotency-Key** bắt buộc. Ngày deprecation là **01/06/2027**, sunset dự kiến **01/01/2028**. Có 15 đối tác, 3 ứng dụng mobile còn gửi 18% traffic tới v1.

Hãy: **(1)** soạn response HTTP v1 chứa Deprecation, Sunset và Link; **(2)** phác thảo migration guide gồm ít nhất năm thay đổi hợp đồng; **(3)** đề xuất kế hoạch đo và thông báo đối tác; **(4)** giải thích vì sao không redirect mù POST v1 sang v2; **(5)** nêu ít nhất sáu ca kiểm thử, gồm bảo mật và cache; **(6)** viết một tiêu chí go/no-go cho ngày sunset.

**Gợi ý đáp án:** dùng Deprecation **@1811808000** và Sunset HTTP-date như mục 5; Link dẫn tới một trang HTTPS có mapping field, POST payload/idempotency, authentication, pagination/status/error, ví dụ SDK và sandbox. Đo v1 theo consumer/route đã được phân quyền, cảnh báo mobile/partner trực tiếp và test GET/POST thật trên v2. **Go** chỉ khi client quan trọng đã xác nhận, v2 ổn định, 4xx/5xx nằm trong SLO, kế hoạch rollback được diễn tập; nếu không, công bố gia hạn và đồng bộ lại header/docs.

## 13. Checklist và nguồn tham khảo

- [ ] Deprecation dùng **Structured Field Date @epoch**, không dùng HTTP-date.
- [ ] Link có **rel="deprecation"** dẫn tới guide HTTPS dễ truy cập và đúng phạm vi.
- [ ] Sunset dùng **HTTP-date**, tách với mốc deprecated; lịch UTC và tài liệu nhất quán.
- [ ] Route/operation được đánh dấu chính xác; status nghiệp vụ vẫn đúng.
- [ ] Migration guide có endpoint/schema, auth, cache, pagination, idempotency, lỗi, SDK và test.
- [ ] CORS/CDN/cache/304 được thử từ client thật; không rò token hoặc dữ liệu.
- [ ] Có dashboard traffic v1, tiêu chí cutover, rollback và owner hỗ trợ.

Tham khảo: **RFC 9745 — The Deprecation HTTP Response Header Field**, https://www.rfc-editor.org/rfc/rfc9745.html; **RFC 8594 — The Sunset HTTP Header Field**, https://www.rfc-editor.org/rfc/rfc8594.html; **RFC 8288 — Web Linking**, https://www.rfc-editor.org/rfc/rfc8288.html; **RFC 9110 — HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **OpenAPI Specification**, https://spec.openapis.org/oas/latest.html; **Spring MVC ResponseEntity**, https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html.

**Kết luận:** Deprecation cho client biết **khi nào tài nguyên không còn được khuyến nghị**, Link deprecation giúp tìm **cách nâng cấp**, còn Sunset thông báo **mốc ngừng phục vụ dự kiến**. Ba tín hiệu chỉ phát huy giá trị khi đi cùng hợp đồng v2 rõ ràng, bảo mật, kiểm thử và một kế hoạch chuyển đổi có thể đo được.
