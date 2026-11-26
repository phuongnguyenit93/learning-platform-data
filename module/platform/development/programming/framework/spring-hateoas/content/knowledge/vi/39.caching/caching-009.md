# Conditional request

Conditional request (request có điều kiện) cho phép client gửi lại một HTTP request kèm validator của representation đã nhận trước đó. Server chỉ truyền body mới khi representation thay đổi hoặc chỉ thực hiện thao tác ghi khi phiên bản tài nguyên vẫn đúng với phiên bản client đã đọc. Cơ chế này giảm dữ liệu truyền qua mạng và giúp tránh ghi đè cập nhật của người khác.

Trong API dùng Spring HATEOAS, representation không chỉ gồm các field của resource. Nó còn có self link, action link, affordance và embedded resource. Vì vậy, validator phải phản ánh đúng representation mà client nhận được, không chỉ phản ánh một vài cột dữ liệu trong database.

## 1. Conditional request giải quyết vấn đề gì?

Giả sử client đọc một đơn hàng qua GET /orders/42. Response có trạng thái PENDING, một self link và link cancel. Sau đó client đọc lại nhiều lần để kiểm tra đơn hàng có thay đổi hay không. Nếu dữ liệu chưa thay đổi, server không cần gửi lại toàn bộ JSON.

Một tình huống khác: hai client cùng đọc đơn hàng ở version 7. Client A cập nhật và tạo version 8. Client B vẫn giữ dữ liệu version 7; nếu B gửi PUT mà server chấp nhận vô điều kiện, thay đổi của A có thể bị ghi đè. Conditional request cho phép B nói rõ: “Chỉ cập nhật nếu representation vẫn là phiên bản tôi đã đọc”.

Hai nhóm điều kiện thường gặp:

- **Cache validation:** If-None-Match hoặc If-Modified-Since để hỏi representation có còn giống bản client đã cache hay không.
- **Write precondition:** If-Match hoặc If-Unmodified-Since để chỉ cho phép thay đổi khi validator hiện tại thỏa điều kiện.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring API
    C->>S: GET /orders/42
    S-->>C: 200 OK + ETag + HAL body
    C->>S: GET /orders/42 + If-None-Match
    alt Representation không đổi
        S-->>C: 304 Not Modified (không body)
    else Representation đã đổi
        S-->>C: 200 OK + ETag mới + HAL body
    end
~~~

## 2. Validator: ETag và Last-Modified

HTTP có hai validator phổ biến.

| Validator | Ý nghĩa | Đặc điểm |
| --- | --- | --- |
| ETag | Mã định danh cho một phiên bản representation | Có thể phản ánh chính xác nội dung; phù hợp cho cache validation và optimistic concurrency |
| Last-Modified | Thời điểm representation được sửa lần cuối | Dễ triển khai nếu có timestamp đáng tin cậy; độ phân giải HTTP date chỉ đến giây |

### ETag

ETag là một opaque validator do server tạo. Ví dụ:

~~~http
ETag: "order-42-v7"
~~~

Giá trị trong dấu ngoặc kép là entity-tag. Client không cần hiểu cấu trúc bên trong; client chỉ lưu và gửi lại giá trị nguyên vẹn. Không đặt access token, session ID hoặc dữ liệu nhạy cảm vào ETag.

Có hai dạng:

- **Strong ETag:** "order-42-v7". Chỉ ra representation data tương ứng là giống nhau theo phép so sánh strong. Đây là loại cần dùng cho If-Match và các thao tác cần kiểm soát ghi chặt chẽ.
- **Weak ETag:** W/"order-42-v7". Chỉ khẳng định các representation tương đương về mặt ngữ nghĩa theo chính sách server, không cam kết byte-for-byte giống nhau. Weak validator hữu ích cho cache validation nhưng không thỏa strong comparison của If-Match.

ETag có thể được tạo từ version của entity, hash của representation đã serialize hoặc một version tổng hợp. Nếu tạo từ version database, chỉ an toàn khi mọi thay đổi ảnh hưởng representation đều làm version thay đổi.

### Last-Modified

Server có thể trả:

~~~http
Last-Modified: Wed, 25 Nov 2026 08:30:00 GMT
~~~

Client dùng timestamp này làm điều kiện cho lần đọc tiếp theo. Timestamp cần được chuẩn hóa theo HTTP-date (UTC, độ phân giải giây). Nếu dữ liệu có thể thay đổi nhiều lần trong cùng một giây, Last-Modified có thể không phân biệt được hai phiên bản; ETag thường đáng tin cậy hơn.

Với representation HATEOAS, timestamp phải phản ánh thời điểm mà cả dữ liệu, link và embedded resource có ý nghĩa đối với client được cập nhật. Nếu link được thêm/bỏ do quyền của caller thay đổi nhưng timestamp của entity không đổi, chỉ dùng Last-Modified có thể trả về kết quả không chính xác.

## 3. Conditional GET với If-None-Match

Client nhận response lần đầu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-42-v7"
Cache-Control: private, no-cache

{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "/orders/42" },
    "cancel": { "href": "/orders/42/cancellations" }
  }
}
~~~

Ở lần đọc sau, client gửi ETag đã lưu:

~~~http
GET /orders/42 HTTP/1.1
If-None-Match: "order-42-v7"
Accept: application/hal+json
~~~

Nếu representation vẫn tương ứng validator đó, server trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-42-v7"
Cache-Control: private, no-cache
~~~

304 Not Modified không có response body. Client giữ lại body đã cache và cập nhật metadata cache theo các header response. Nếu representation đã đổi, server trả 200 OK, ETag mới và body mới.

If-None-Match có thể chứa nhiều ETag hoặc dấu *. Với GET/HEAD, phép so sánh là weak comparison: weak ETag có thể được xem là match nếu opaque tag tương ứng. Nếu request có cả If-None-Match và If-Modified-Since, If-None-Match có mức ưu tiên; server không dùng If-Modified-Since để bỏ qua một điều kiện ETag đã được gửi.

### Triển khai bằng WebRequest trong Spring MVC

Spring MVC cung cấp WebRequest.checkNotModified(...) để xử lý điều kiện đọc. Ví dụ dưới đây tạo strong ETag từ ID và version của đơn hàng:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/orders/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    ResponseEntity<EntityModel<OrderRepresentation>> one(
            @PathVariable UUID id, WebRequest request) {

        Order order = orderService.findVisible(id);
        String etag = etagFor(order);
        long lastModified = order.updatedAt().toEpochMilli();

        if (request.checkNotModified(etag, lastModified)) {
            // Spring đã đặt status và validator header cho response 304.
            return null;
        }

        EntityModel<OrderRepresentation> model = assembler.toModel(order);
        return ResponseEntity.ok()
                .eTag(etag)
                .lastModified(lastModified)
                .body(model);
    }

    private String etagFor(Order order) {
        return "\"order-" + order.id() + "-v" + order.version() + "\"";
    }
}
~~~

Order, OrderService, OrderModelAssembler và OrderRepresentation là các kiểu domain/ứng dụng minh họa. Ví dụ giả định version tăng mỗi khi bất kỳ dữ liệu hoặc link nào trong representation thay đổi. Nếu giả định này không đúng, cần dùng validator đại diện cho toàn bộ representation thay vì chỉ dùng version của entity.

Khi checkNotModified(...) trả về true, Spring đã đánh dấu response là không cần gửi representation mới; controller kết thúc bằng null. Khi request không thỏa điều kiện cache validation, controller tạo model và trả 200 OK cùng validator.

## 4. Conditional GET với If-Modified-Since

Nếu API có timestamp chính xác, có thể kiểm tra điều kiện theo thời gian:

~~~http
GET /orders/42 HTTP/1.1
If-Modified-Since: Wed, 25 Nov 2026 08:30:00 GMT
~~~

Nếu resource chưa thay đổi kể từ thời điểm đó, server trả 304 Not Modified; nếu đã thay đổi, server trả 200 OK. Spring MVC có thể kiểm tra timestamp bằng overload checkNotModified(lastModifiedTimestamp):

~~~java
long lastModified = order.updatedAt().toEpochMilli();

if (request.checkNotModified(lastModified)) {
    return null;
}
~~~

Trong thực tế nên ưu tiên ETag khi cần xác định chính xác representation. Nếu response cung cấp cả ETag và Last-Modified, client thường gửi If-None-Match; server phải tôn trọng thứ tự ưu tiên của HTTP thay vì xử lý hai header như hai điều kiện độc lập kiểu AND.

## 5. Conditional request và representation Spring HATEOAS

Một representation HATEOAS có thể thay đổi dù các field chính của entity không đổi. Ví dụ:

- Đơn hàng chuyển từ PENDING sang SHIPPED, nên link cancel bị loại bỏ.
- Quyền của caller thay đổi, nên link edit xuất hiện hoặc biến mất.
- Một embedded resource thay đổi và được phản ánh trong representation cha.
- API trả HAL hoặc HAL-FORMS tùy Accept; affordance metadata có thể khác nhau.
- Link được render thành URI tuyệt đối theo host/proxy hoặc locale khác nhau.

Do đó, ETag của HATEOAS representation phải đại diện cho cả payload và hypermedia controls. Có ba chiến lược thường dùng:

1. **Version tổng hợp:** tăng representation version khi resource, quan hệ hoặc trạng thái ảnh hưởng link thay đổi.
2. **Hash representation:** tạo ETag từ bytes JSON/HAL cuối cùng. Cách này sát với nội dung trả về nhưng cần serialize trước khi kiểm tra validator.
3. **Version theo biến thể:** kết hợp version tài nguyên với media type hoặc một representation variant ổn định khi các yếu tố đó làm thay đổi nội dung.

Không tái sử dụng một ETag cho hai representation khác nhau chỉ vì chúng cùng lấy dữ liệu từ một entity. Đặc biệt, nếu link được cá nhân hóa theo principal hoặc authority, cần bảo đảm validator không làm response của caller này được coi là hợp lệ cho caller khác. Với representation nhạy cảm, dùng Cache-Control: private hoặc no-store theo yêu cầu bảo mật; Vary chỉ là một phần của chính sách cache.

### Vary theo media type và credential

Nếu cùng URI trả về nhiều media type, ví dụ HAL và HAL-FORMS, response nên công bố biến thể theo Accept:

~~~http
Vary: Accept
~~~

Nếu representation thay đổi theo header xác thực hoặc cookie, cần cân nhắc:

~~~http
Cache-Control: private
Vary: Accept, Authorization, Cookie
~~~

Vary giúp cache chọn đúng representation theo request header. private ngăn shared cache lưu response cá nhân hóa; no-store yêu cầu không lưu response. Không dùng Vary để thay thế authorization ở server.

## 6. Conditional write với If-Match

Conditional GET tránh truyền body không cần thiết. Với thao tác ghi, mục tiêu là tránh lost update.

Client A và B cùng đọc đơn hàng version 7, nhận ETag:

~~~http
ETag: "order-42-v7"
~~~

Client A cập nhật trước và server tạo version 8. Khi client B gửi bản cập nhật cũ, B gửi:

~~~http
PUT /orders/42 HTTP/1.1
If-Match: "order-42-v7"
Content-Type: application/json

{
  "shippingAddress": "12 Example Street"
}
~~~

Server hiện có ETag "order-42-v8", không khớp điều kiện. Server từ chối cập nhật và trả:

~~~http
HTTP/1.1 412 Precondition Failed
ETag: "order-42-v8"
~~~

Client phải đọc representation mới, hợp nhất thay đổi cần thiết rồi gửi request mới. Không tự động retry payload cũ mà bỏ qua precondition.

If-Match sử dụng strong comparison. Weak ETag như W/"order-42-v7" không thỏa If-Match. Header có thể chứa danh sách validator hoặc * (match nếu resource tồn tại). Nếu server yêu cầu client luôn gửi precondition nhưng client bỏ qua, server có thể trả 428 Precondition Required.

### Kiểm tra If-Match trong Spring MVC

HttpHeaders.getIfMatch() trả về danh sách entity-tag đã parse. Ví dụ helper dưới đây thực hiện strong comparison và hỗ trợ wildcard:

~~~java
import java.util.List;

final class EntityTagMatcher {

    static boolean matchesIfMatch(List<String> candidates, String currentEtag) {
        if (candidates.contains("*")) {
            return true; // resource đã được tải và tồn tại
        }

        return candidates.stream().anyMatch(candidate ->
                !candidate.startsWith("W/") && candidate.equals(currentEtag));
    }
}
~~~

Controller có thể áp dụng helper như sau:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderUpdateController {

    private final OrderService orderService;

    OrderUpdateController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PutMapping("/orders/{id}")
    ResponseEntity<Void> replace(
            @PathVariable UUID id,
            @RequestBody UpdateOrderRequest body,
            @RequestHeader HttpHeaders headers) {

        Order current = orderService.findForUpdate(id);
        List<String> candidates = headers.getIfMatch();

        if (candidates.isEmpty()) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_REQUIRED).build();
        }

        String currentEtag = etagFor(current);
        if (!EntityTagMatcher.matchesIfMatch(candidates, currentEtag)) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
                    .eTag(currentEtag)
                    .build();
        }

        try {
            orderService.replaceIfVersionMatches(
                    id, body, current.version());
        } catch (ObjectOptimisticLockingFailureException ex) {
            // Một request khác có thể đã cập nhật sau lần đọc ở trên.
            return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED).build();
        }

        return ResponseEntity.noContent().build();
    }

    private String etagFor(Order order) {
        return "\"order-" + order.id() + "-v" + order.version() + "\"";
    }

}
~~~

UpdateOrderRequest là DTO cập nhật minh họa. replaceIfVersionMatches(...) phải bảo đảm kiểm tra version và ghi dữ liệu trong cùng transaction hoặc bằng câu lệnh cập nhật có điều kiện. Chỉ kiểm tra ETag ở controller rồi cập nhật không điều kiện vẫn có race condition: request khác có thể ghi dữ liệu giữa bước kiểm tra và bước ghi.

Với JPA, có thể dùng @Version trên trường version của entity để optimistic locking. Nếu transaction phát hiện version đã đổi, Spring có thể ném ObjectOptimisticLockingFailureException (hoặc exception tương ứng theo persistence provider); API nên chuyển trường hợp precondition đã lỗi thời thành 412 Precondition Failed. Trong trường hợp cần trả ETag mới ở response 412, hãy đọc lại resource và tạo validator mới sau khi transaction xung đột kết thúc.

## 7. If-Unmodified-Since và If-None-Match cho thao tác ghi

If-Unmodified-Since là lựa chọn theo thời gian cho thao tác ghi:

~~~http
PUT /orders/42
If-Unmodified-Since: Wed, 25 Nov 2026 08:30:00 GMT
~~~

Nếu resource đã thay đổi sau timestamp đó, server trả 412 Precondition Failed. Tuy nhiên, timestamp chỉ chính xác đến giây và phụ thuộc đồng hồ, nên ETag với If-Match thường phù hợp hơn để tránh lost update.

If-None-Match: * có thể dùng khi client muốn tạo resource mà không ghi đè resource đã tồn tại. Nếu resource đã tồn tại, điều kiện thất bại và server trả 412 Precondition Failed. Đây là cách hỗ trợ create-only semantics khi URI do client chọn.

Thứ tự đánh giá precondition phải tuân theo HTTP semantics. Khi If-Match có mặt, không được bỏ qua nó chỉ vì If-Unmodified-Since có vẻ hợp lệ. Tương tự, với GET/HEAD, If-None-Match được ưu tiên hơn If-Modified-Since.

## 8. ShallowEtagHeaderFilter: tiện lợi nhưng không miễn phí

Spring Framework cung cấp ShallowEtagHeaderFilter, một servlet filter có thể tính ETag từ nội dung response đã render. Ví dụ đăng ký filter:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@Configuration
class EtagFilterConfiguration {

    @Bean
    FilterRegistrationBean<ShallowEtagHeaderFilter> shallowEtagFilter() {
        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new ShallowEtagHeaderFilter());
        registration.addUrlPatterns("/api/*");
        return registration;
    }
}
~~~

Filter bọc response, giữ nội dung đã render để tính ETag và so sánh với If-None-Match. Cách này hữu ích khi representation có nhiều link/embedded data và khó tạo version tổng hợp bằng tay. Tuy nhiên, nó thường vẫn phải chạy controller, truy vấn database, gọi assembler và serialize body trước khi biết response có thể trả 304 hay không. Nó tiết kiệm băng thông, không tự động tiết kiệm toàn bộ chi phí xử lý server.

Nếu mục tiêu là bỏ qua cả bước tạo representation tốn kém, hãy tính validator từ version hoặc metadata đáng tin cậy trước khi serialize, như ví dụ WebRequest.checkNotModified(...). Không cấu hình filter và tự đặt ETag cho cùng response mà không xác định rõ thành phần nào chịu trách nhiệm validator; tránh hai nguồn ETag mâu thuẫn.

## 9. Cache-Control và conditional request

Conditional request và cache directive bổ trợ nhau nhưng không thay thế nhau.

| Header | Ý nghĩa |
| --- | --- |
| Cache-Control: max-age=60 | Cache có thể dùng response trong 60 giây mà chưa cần revalidate |
| Cache-Control: no-cache | Có thể lưu response nhưng phải revalidate trước khi dùng lại |
| Cache-Control: no-store | Không lưu response; thường không còn body cache để tái xác thực |
| Cache-Control: private | Chỉ cache riêng của client được lưu; shared cache không được lưu response |

Một response cá nhân hóa có thể dùng:

~~~http
Cache-Control: private, no-cache
ETag: "order-42-v7-user-view-a"
Vary: Accept, Authorization, Cookie
~~~

Không nhất thiết phải mã hóa user name hoặc role trong ETag như ví dụ minh họa. Trong thực tế hãy dùng opaque tag hoặc hash representation/variant, tránh làm lộ thông tin caller. Nếu response chứa dữ liệu nhạy cảm và chính sách yêu cầu không lưu, dùng no-store; khi đó đừng kỳ vọng cache sẽ giữ body để tái xác thực.

## 10. Kiểm thử conditional request với MockMvc

Kiểm thử cơ bản nên xác nhận ba hành vi:

1. Request đầu tiên trả 200 OK và có ETag.
2. Request GET tiếp theo gửi đúng If-None-Match trả 304 và không có body.
3. Request ghi với ETag cũ bị từ chối bằng 412 (hoặc 428 nếu thiếu điều kiện bắt buộc).

Ví dụ test cho conditional GET:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConditionalRequestTest {

    private static final UUID ORDER_ID =
            UUID.fromString("a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Autowired
    MockMvc mockMvc;

    @Test
    void matchingEtagReturnsNotModifiedWithoutBody() throws Exception {
        MvcResult first = mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(header().exists(HttpHeaders.ETAG))
                .andReturn();

        String etag = first.getResponse().getHeader(HttpHeaders.ETAG);

        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON)
                        .header(HttpHeaders.IF_NONE_MATCH, etag))
                .andExpect(status().isNotModified())
                .andExpect(header().string(HttpHeaders.ETAG, etag))
                .andExpect(content().string(""));
    }
}
~~~

Test giả định dữ liệu và quyền truy cập không đổi giữa hai request. Trong test suite thực tế, khởi tạo resource cố định trước test và xác minh link HAL cùng ETag. Nếu API trả response phụ thuộc caller, test thêm các context khác nhau để bảo đảm validator không bị dùng chéo giữa anonymous user và authenticated user.

Test stale If-Match có thể gửi một ETag cũ đã biết:

~~~java
@Test
void staleIfMatchIsRejected() throws Exception {
    mockMvc.perform(put("/orders/{id}", ORDER_ID)
                    .header(HttpHeaders.IF_MATCH, "\"order-42-v6\"")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"shippingAddress\":\"New address\"}"))
            .andExpect(status().isPreconditionFailed());
}
~~~

Test này là method bổ sung trong cùng lớp ConditionalRequestTest; fixture phải bảo đảm resource hiện có version 7 trở lên. Nên có thêm test If-Match bị thiếu để xác nhận chính sách 428 Precondition Required nếu API yêu cầu precondition cho mọi lần ghi.

## 11. Lỗi thường gặp

**Tạo ETag chỉ từ một cột không đủ đại diện:** link hoặc embedded data đổi nhưng ETag không đổi. Tạo validator từ version tổng hợp hoặc representation thực tế.

**Dùng weak ETag cho If-Match:** weak validator không thỏa strong comparison. Dùng strong ETag cho optimistic concurrency.

**Trả 200 OK với body rỗng khi chưa thay đổi:** cache validation đúng nên trả 304 Not Modified không body.

**Dùng Last-Modified với dữ liệu thay đổi nhiều lần trong một giây:** độ phân giải timestamp có thể bỏ sót thay đổi. Dùng ETag.

**Chỉ kiểm tra If-Match ở controller:** request khác có thể cập nhật ngay sau bước kiểm tra. Kết hợp optimistic locking hoặc compare-and-set trong transaction.

**Nhầm no-cache với no-store:** no-cache yêu cầu revalidate trước khi dùng; no-store cấm lưu response.

**Dùng chung validator cho mọi caller:** link theo quyền có thể khác nhau. Bảo đảm ETag phản ánh representation variant và thiết lập cache privacy phù hợp.

**Cho rằng ShallowEtagHeaderFilter bỏ qua xử lý server:** filter thường tính ETag sau khi body đã được tạo. Nó giảm truyền dữ liệu chứ không loại bỏ công việc truy vấn và render.

## 12. Checklist triển khai

- Xác định response nào có thể cache và response nào phải no-store.
- Chọn ETag, Last-Modified hoặc cả hai theo semantics của resource.
- Bảo đảm ETag đại diện cho body, links, affordances và embedded resources.
- Dùng strong ETag cho If-Match và kiểm soát cập nhật đồng thời.
- Dùng WebRequest.checkNotModified(...) cho conditional GET/HEAD.
- Trả 304 không body khi representation chưa đổi.
- Trả 412 khi precondition không thỏa; cân nhắc 428 khi thiếu precondition bắt buộc.
- Dùng optimistic locking hoặc atomic version check để đóng race condition.
- Thiết lập Vary cho media type và request headers làm thay đổi representation.
- Không để validator hoặc shared cache làm lộ dữ liệu, quyền hay link của caller khác.
- Kiểm thử 200, 304, 412 và 428 bằng MockMvc.

Conditional request biến validator thành một phần của hợp đồng HTTP: client có thể tái sử dụng representation đã cache khi không đổi và bảo vệ cập nhật dựa trên phiên bản đã đọc. Với Spring HATEOAS, điều quan trọng là validator phải bao quát cả hypermedia controls và các biến thể theo caller; còn với thao tác ghi, precondition phải được kiểm tra nguyên tử cùng optimistic locking để tránh lost update.

## Tài liệu tham khảo

- [Spring Framework Reference – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)
- [Spring Framework Javadoc – WebRequest.checkNotModified](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/WebRequest.html)
- [Spring Framework Javadoc – ShallowEtagHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html)
- [RFC 9110 – HTTP Semantics, Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests)
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
