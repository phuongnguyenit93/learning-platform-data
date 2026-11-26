# Rò rỉ thông tin qua link

Một API quản lý khách hàng có thể trả link đến hồ sơ, lịch sử giao dịch hoặc thao tác hoàn tiền. Nếu URI chứa email, số điện thoại, mã định danh nhạy cảm, token truy cập hoặc tham số tìm kiếm riêng tư, những giá trị này có thể xuất hiện trong access log, browser history, hệ thống phân tích, cache và HTTP `Referer`. Ngay cả khi API dùng HTTPS, thông tin trong URL vẫn có thể được lưu tại các thành phần đầu cuối.

Trong Spring HATEOAS, link là một phần của representation và cũng là dữ liệu được công bố cho client. Rò rỉ có thể xảy ra ở `href`, query template, relation name, title, embedded resource hoặc host được tạo sai. Cần xem toàn bộ response hypermedia như một bề mặt công bố dữ liệu: chỉ đưa thông tin mà client hiện tại được phép biết, không đặt bí mật vào URL, và vẫn kiểm tra quyền tại endpoint đích.

## Những gì có thể bị lộ qua link?

Một link có nhiều thành phần và mỗi thành phần có thể tiết lộ một loại thông tin:

| Thành phần | Ví dụ | Rủi ro |
| --- | --- | --- |
| Path | `/api/users/mai.nguyen@example.com` | Lộ thông tin cá nhân hoặc định danh nội bộ. |
| Query | `?phone=090...&status=REVIEW` | Lộ dữ liệu tìm kiếm, thông tin cá nhân hoặc trạng thái nghiệp vụ. |
| Token | `?access_token=...` | Lộ bearer credential; người có URL có thể sử dụng quyền của token. |
| Capability URL | `/download?signature=...` | Link có thể hoạt động như một chìa khóa truy cập tài nguyên. |
| Host/port | `http://orders-db-02.internal:8080/...` | Tiết lộ topology, hostname hoặc môi trường nội bộ. |
| Relation/title | `acme:fraud-investigation`, title `Tài khoản bị khóa` | Tiết lộ workflow, trạng thái hoặc sự tồn tại của dữ liệu nhạy cảm. |
| Embedded resource | `_embedded.customer` chứa email và địa chỉ | Dữ liệu có thể bị lộ dù client không theo bất kỳ link nào. |

Rò rỉ không chỉ xảy ra khi link được mở. URL có thể được ghi lại hoặc sao chép ngay khi response được tạo, hiển thị trong UI, đưa vào log hoặc chuyển qua hệ thống trung gian.

## Vì sao URL dễ làm lộ dữ liệu?

URI được thiết kế để định danh tài nguyên và có thể xuất hiện trong nhiều nơi trong quá trình xử lý HTTP. Một request như:

```http
GET /api/customers/search?email=mai.nguyen@example.com&status=REVIEW HTTP/1.1
Host: api.example.com
```

có thể được ghi lại trong:

- Access log của ứng dụng, reverse proxy, API gateway, WAF hoặc CDN.
- APM, distributed tracing, request diagnostics và error report.
- Browser history, bookmark, clipboard, ảnh chụp màn hình hoặc ticket hỗ trợ.
- HTTP `Referer` khi trình duyệt điều hướng đến tài nguyên khác, tùy Referrer Policy.
- Cache key và dữ liệu lưu tại browser/proxy/CDN.
- Analytics hoặc hệ thống theo dõi click link.

HTTPS mã hóa dữ liệu trên đường truyền giữa các điểm TLS, nhưng không ngăn máy chủ, proxy kết thúc TLS, browser hoặc hệ thống logging nhìn thấy URI sau khi giải mã. URL encoding, Base64 hoặc đổi tên query parameter cũng không phải biện pháp bảo mật.

## Không đặt credential trong URL

Không đưa bearer access token, session ID, API key, password hoặc reset token vào path hay query parameter. Ví dụ sau có nguy cơ nghiêm trọng:

```http
GET /api/orders?access_token=eyJhbGciOi... HTTP/1.1
```

Bearer token là thông tin xác thực: ai có token có thể sử dụng quyền mà token cấp. RFC 6750 khuyến nghị truyền bearer token bằng HTTP `Authorization` header; truyền token trong URI không được khuyến nghị vì URI thường được ghi log.

Hãy dùng:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/hal+json
```

Trong Spring HATEOAS, `href` chỉ nên chứa URI cần thiết để định vị resource hoặc action. Cơ chế xác thực được client gửi trong header theo chính sách bảo mật của API, không gắn vào từng link.

Không dùng URL fragment như `#token=...` để thay thế một cơ chế truyền credential an toàn. Fragment không được gửi trong HTTP request target, nhưng vẫn có thể bị lưu trong browser history, đọc bởi script trên trang hoặc lộ qua công cụ phía client.

## Path và query parameter cũng có thể chứa dữ liệu nhạy cảm

Không chỉ token mới cần tránh trong URL. Email, số điện thoại, số giấy tờ, địa chỉ, từ khóa tìm kiếm riêng tư, mã hồ sơ y tế hoặc trạng thái tài khoản cũng có thể là dữ liệu nhạy cảm.

Ví dụ nên tránh:

```text
/api/customers/mai.nguyen@example.com
/api/identity-checks?nationalId=079xxxxxxxxx
/api/orders?search=khach-hang-no-xau
```

Ưu tiên định danh tài nguyên không mang trực tiếp PII, nhưng không xem ID khó đoán là biện pháp phân quyền. UUID hoặc ID ngẫu nhiên vẫn có thể bị chia sẻ, ghi log hoặc lộ qua response; endpoint luôn phải kiểm tra authorization.

Với truy vấn có điều kiện nhạy cảm hoặc quá dài, cân nhắc một search operation dùng `POST` với request body và trả về search resource hoặc kết quả có link điều hướng:

```http
POST /api/order-searches HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "customerEmail": "mai.nguyen@example.com",
  "riskStatus": "REVIEW"
}
```

Server có thể trả `201 Created` cùng `Location` hoặc một representation có link đến search resource. Đây là một thiết kế ứng dụng; `POST` không có semantics safe như `GET` và cần quy định rõ về tạo search resource, lưu trữ, quyền truy cập, idempotency và cache. Dữ liệu trong body cũng có thể bị logging middleware ghi lại, nên vẫn phải cấu hình redaction cho request body.

## Capability URL là một dạng credential

Một số link được thiết kế có chủ ý để người nắm URL có thể thực hiện một hành động mà không cần đăng nhập lại, ví dụ:

- Link đặt lại mật khẩu.
- Link xác nhận email hoặc lời mời tham gia.
- Link tải tài liệu riêng tư có chữ ký.
- Link chia sẻ tạm thời đến một file.

Đây là *capability URL*: quyền truy cập được mang theo chính URL. Nếu sử dụng, phải xem toàn bộ URL như một bí mật tương đương credential. Người nhận nhầm hoặc hệ thống ghi lại URL có thể sử dụng capability đó.

Giảm thiểu rủi ro bằng cách:

1. Tạo token ngẫu nhiên bằng bộ sinh số an toàn mật mã, đủ entropy.
2. Giới hạn token vào đúng resource và một hành động cụ thể.
3. Đặt thời hạn ngắn, có thể thu hồi và dùng một lần nếu phù hợp.
4. Lưu hash của token ở server thay vì lưu token rõ khi kiến trúc cho phép.
5. Không chuyển tiếp capability sang host khác hoặc redirect đến URL do người dùng tùy ý cung cấp.
6. Tránh tải nội dung bên thứ ba trên trang đích có token; đặt `Referrer-Policy: no-referrer`.
7. Redact token khỏi access log, proxy log, tracing, analytics và error report.
8. Không cache response chứa capability; dùng `Cache-Control: no-store`.
9. Sau khi xác thực capability, cân nhắc đổi nó lấy session ngắn hạn rồi redirect đến URL sạch không còn token.

Signed URL của object storage cũng là bearer capability. Chữ ký không làm URL trở nên vô hại; cần giới hạn object, method, thời hạn và quyền. Không đưa signed URL vào log hoặc gửi nó đến bên thứ ba.

## Link có thể tiết lộ trạng thái và capability

Trong hypermedia, sự hiện diện hoặc vắng mặt của một relation có thể tiết lộ trạng thái nghiệp vụ. Ví dụ:

```json
{
  "id": "ord-1042",
  "status": "PENDING_APPROVAL",
  "_links": {
    "self": { "href": "/api/orders/ord-1042" },
    "acme:approve": { "href": "/api/orders/ord-1042/approval" },
    "acme:fraud-review": { "href": "/api/orders/ord-1042/fraud-review" }
  }
}
```

Ngay cả khi response không chứa trường `status`, các relation `approve` hoặc `fraud-review` vẫn có thể tiết lộ trạng thái hoặc quy trình nội bộ. `title`, `name`, CURIE, URI template và các thuộc tính link khác cũng có thể tiết lộ metadata.

Chỉ công bố link mà principal hiện tại được phép biết. Nếu tên relation tiết lộ quá nhiều chi tiết nội bộ, xem xét một relation capability ít nhạy cảm hơn hoặc cung cấp capability qua một representation được phân quyền chặt chẽ. Tuy nhiên, không đổi nghĩa relation chỉ để che giấu dữ liệu; cần giữ hợp đồng rõ ràng cho client được phép sử dụng nó.

Ẩn link không phải authorization. Client có thể giữ response cũ hoặc tự tạo request đến target. Endpoint đích phải xác thực, phân quyền và kiểm tra trạng thái mới nhất khi nhận request.

## Kiểm soát dữ liệu trong HAL và embedded resource

Một response HAL có thể lộ dữ liệu trong nhiều vị trí:

- `_links.*.href`: path, query, token hoặc host.
- `_links.*.title`: mô tả nhạy cảm hoặc trạng thái nội bộ.
- `_links.curies`: namespace và tên relation riêng.
- `_embedded.*`: dữ liệu của resource liên quan.
- `page` và URI template: filter, sort hoặc cấu trúc truy vấn.

Đừng cho rằng chỉ `href` mới cần kiểm tra. Embedded resource phải được serialize từ DTO/projection được phép công bố, không serialize toàn bộ entity JPA hoặc object domain có field nhạy cảm.

Ví dụ, một item đơn hàng chỉ cần hiển thị tên người nhận đã được phép xem. Không nhúng email đăng nhập, số giấy tờ hoặc địa chỉ đầy đủ nếu client không cần chúng. Tạo DTO như `OrderSummary` hoặc `CustomerReference` giúp kiểm soát chính xác field xuất hiện trong response.

URI template cũng có thể tiết lộ khả năng tìm kiếm và tên filter. Đó thường là thông tin hợp đồng hữu ích, nhưng không nên đưa giá trị nhạy cảm mặc định vào template hoặc query string. Nếu template hỗ trợ filter riêng tư, endpoint vẫn phải phân quyền và bảo vệ log.

## Không để link tiết lộ hạ tầng nội bộ

Ứng dụng sau reverse proxy có thể nhận request nội bộ tại `http://orders-service:8080` trong khi client truy cập `https://api.example.com/shop`. Nếu link builder dùng sai request context, response có thể tiết lộ hostname nội bộ, port hoặc đường dẫn triển khai.

Ví dụ link không nên công bố:

```text
http://orders-service.internal:8080/api/orders/ord-1042
```

Link công khai nên dùng origin và prefix mà client thực sự truy cập:

```text
https://api.example.com/shop/api/orders/ord-1042
```

Trong Spring MVC, `WebMvcLinkBuilder` dựa trên request context. Khi chạy sau proxy, cấu hình forwarded-header handling phù hợp để tạo URI công khai. Chỉ tin `Forwarded` hoặc `X-Forwarded-*` do proxy đáng tin cậy ghi đè; không chấp nhận giá trị host do client Internet tự gửi để dựng link.

Nếu link được tạo trong batch job hoặc không có HTTP request hiện tại, dùng public base URI lấy từ cấu hình đáng tin cậy thay vì suy ra host từ dữ liệu người dùng.

## HTTP Referer và Referrer-Policy

Khi trình duyệt điều hướng từ một trang sang tài nguyên khác, nó có thể gửi header `Referer` chứa thông tin về URL nguồn. Nội dung header phụ thuộc `Referrer-Policy` của trang và quy tắc trình duyệt. Chính sách mặc định phổ biến hiện nay thường giảm thông tin khi đi cross-origin, nhưng vẫn có thể gửi path và query trong một số điều kiện cùng origin.

Nếu URL có thể chứa capability hoặc dữ liệu nhạy cảm, không dựa vào default của browser. Có thể gửi:

```http
Referrer-Policy: no-referrer
```

Header này là chính sách referrer cho document/browser context được response tạo ra. Hãy đặt nó trên HTML landing page hoặc document hiển thị và follow capability link; với browser `fetch`, cũng cần kiểm tra referrer policy của trang và request. Không giả định chỉ thêm header vào một JSON API response sẽ bảo vệ mọi request phát sinh từ một trang khác. `strict-origin` là lựa chọn khác khi chỉ muốn chia sẻ origin trong điều kiện phù hợp, nhưng không bảo vệ khỏi browser history, logs hoặc analytics của chính ứng dụng.

Đặt `Referrer-Policy` là một lớp giảm thiểu bổ sung. Biện pháp chính vẫn là không đưa credential hoặc dữ liệu nhạy cảm vào URI.

## Logging, tracing và redaction

Các hệ thống log thường ghi request line hoặc full URL để hỗ trợ chẩn đoán. Với API hypermedia, link được click cũng có thể được thu thập bởi analytics hoặc tracing.

Hãy rà soát các lớp sau:

- Reverse proxy, ingress, API gateway và load balancer.
- Servlet container và application access log.
- Spring request logging, filters và interceptors.
- APM, distributed tracing, error tracking và audit log.
- Frontend analytics, session replay và crash reporting.
- Hệ thống support ticket, chat hoặc email chứa URL do người dùng gửi.

Chỉ log những trường cần thiết. Nếu cần ghi URI, bỏ query hoặc redact các parameter nhạy cảm như `token`, `signature`, `code`, `email`, `phone` và `nationalId`. Danh sách redaction phải theo domain thực tế; không chỉ dựa trên tên parameter vì dữ liệu nhạy cảm có thể được đặt dưới tên khác.

Không ghi toàn bộ request/response body của endpoint nhạy cảm vào log mặc định. Nếu cần audit, ghi actor, action, resource ID đã được kiểm soát và kết quả thay vì credential hoặc payload bí mật.

## Cache và response chứa link theo người dùng

Root resource hoặc item representation có thể chứa link phụ thuộc quyền, tenant hoặc trạng thái của user. Nếu response đó bị shared cache dùng lại cho người khác, link có thể tiết lộ capability hoặc URI thuộc phạm vi của user trước.

Với response chứa dữ liệu cá nhân, capability hoặc link phụ thuộc principal, cân nhắc:

```http
Cache-Control: no-store
Referrer-Policy: no-referrer
```

`no-store` yêu cầu cache không lưu response; `private` có thể dùng khi cho phép private cache của user nhưng cấm shared cache lưu response. Chọn chính sách theo độ nhạy dữ liệu và khả năng cache thực tế. Không dựa vào `Vary: Authorization` như biện pháp duy nhất để bảo vệ dữ liệu.

Nếu response công khai và có thể cache, hãy bảo đảm các link trong đó thực sự công khai, không phụ thuộc session hoặc tenant. Cache key phải phản ánh các biến ảnh hưởng đến representation; nhưng tốt hơn là không đưa response cá nhân vào shared cache nếu không có thiết kế cache an toàn rõ ràng.

## Kiểm soát cross-origin khi client follow link

Một hypermedia link có thể trỏ sang host khác. Client không nên gửi `Authorization`, cookie hoặc header nội bộ đến mọi origin chỉ vì response chứa một `href`.

Client cần:

- Kiểm tra scheme và origin đích theo chính sách tin cậy.
- Không gửi credential đến host chưa được cho phép.
- Giới hạn redirect và kiểm tra origin sau mỗi redirect.
- Không tự động tải link bên ngoài nếu không cần thiết.
- Tránh hiển thị link capability trong analytics, referrer hoặc nội dung bên thứ ba.

Đối với server-side client, kiểm tra origin cũng giúp giảm nguy cơ SSRF khi target URI đến từ dữ liệu không đáng tin cậy. Chỉ follow scheme và host được phép; không cho phép link tùy ý đến loopback, private network hoặc metadata endpoint của hạ tầng.

## Tạo link an toàn trong Spring HATEOAS

Hãy tạo URI từ mapping controller và dữ liệu đã xác thực, không ghép URL từ input tùy ý. Chỉ thêm action link khi actor hiện tại có quyền và trạng thái resource cho phép:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final OrderAuthorization authorization;

    OrderModelAssembler(OrderAuthorization authorization) {
        this.authorization = authorization;
    }

    EntityModel<OrderView> toModel(Order order, CurrentUser actor) {
        EntityModel<OrderView> model = EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());

        if (order.canBeCancelled() && authorization.canCancel(actor, order)) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId()))
                .withRel(OrderRelations.CANCEL));
        }

        return model;
    }
}
```

Ví dụ giả định `CurrentUser`, `OrderAuthorization`, `OrderView`, `OrderRelations` và controller action `cancel(UUID)` là các kiểu của ứng dụng. Assembler chỉ công bố link cancel khi actor được phép và đơn hàng đang ở trạng thái phù hợp. Endpoint `cancel` vẫn phải kiểm tra lại quyền và trạng thái ngay trước khi thay đổi dữ liệu.

Không truyền token, email, số giấy tờ hoặc secret vào tham số `methodOn(...)` chỉ để chúng xuất hiện trong `href`. Nếu endpoint cần dữ liệu đầu vào nhạy cảm, truyền qua body của request được bảo vệ và kiểm soát logging.

## Không tin host hoặc URL do request tự khai báo

Tránh các mẫu sau:

```java
// Không dùng Host/X-Forwarded-Host chưa được tin cậy để dựng link.
String href = "https://" + request.getHeader("X-Forwarded-Host")
    + "/api/orders/" + orderId;

// Không ghép query từ dữ liệu bí mật.
String searchHref = "/api/customers?email=" + customerEmail;
```

Hãy dùng `WebMvcLinkBuilder` với forwarded headers được cấu hình qua proxy đáng tin cậy; hoặc dùng base URI cố định từ cấu hình nếu link được tạo ngoài request context. Đối với query, chỉ đưa các filter không nhạy cảm cần thiết cho client; mã hóa URI không làm dữ liệu trở nên bí mật.

## Kiểm thử rò rỉ thông tin trong response

Kiểm thử security link nên xem xét toàn bộ representation, không chỉ một link cụ thể. Ví dụ, response của một API có dữ liệu nhạy cảm không được chứa access token hoặc email riêng tư trong body, link hay header:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

MvcResult result = mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON)
        .header("Authorization", "Bearer " + accessToken))
    .andExpect(status().isOk())
    .andReturn();

String body = result.getResponse().getContentAsString();

assertThat(body).doesNotContain(accessToken);
assertThat(body).doesNotContain(customerEmail);
assertThat(body).doesNotContain("access_token=");
```

Test giả định email không được phép xuất hiện trong representation này. Nếu email là field công khai của một endpoint khác, hãy xác định rõ hợp đồng dữ liệu thay vì áp dụng một assertion chung cho mọi response.

### Kiểm tra link action theo quyền

Với user không có quyền hủy đơn, response không nên công bố action link; request trực tiếp đến endpoint vẫn phải bị từ chối:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .with(user("reader"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['acme:cancel']").doesNotExist());

mockMvc.perform(post("/api/orders/{id}/cancellation", orderId)
        .with(user("reader")))
    .andExpect(status().isForbidden());
```

Đoạn test giả định Spring Security Test được cấu hình, user `reader` không có quyền cancel và endpoint POST được bảo vệ. Test thứ hai rất quan trọng: ẩn link chỉ cải thiện affordance, không phải hàng rào authorization.

### Kiểm tra response headers

Với response có capability hoặc dữ liệu nhạy cảm, kiểm tra chính sách cache và referrer:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/password-resets/{token}", resetToken))
    .andExpect(status().isOk())
    .andExpect(header().string("Cache-Control", containsString("no-store")))
    .andExpect(header().string("Referrer-Policy", "no-referrer"));
```

Đây là ví dụ cho endpoint capability và landing response; trong hệ thống thực tế, không nhất thiết token phải nằm trên path nếu có thể đổi sang quy trình an toàn hơn. Nếu endpoint chỉ trả JSON, kiểm tra `Cache-Control` tại endpoint và kiểm tra `Referrer-Policy` trên document/landing page thực sự điều hướng đến link. Giá trị token trong test phải là fixture giả, không ghi token thật vào test report.

### Kiểm tra host và proxy headers

Trong môi trường có reverse proxy, gửi request test với `Host` hoặc forwarded header không đáng tin cậy và xác nhận link chỉ dùng public host đã cấu hình. Kiểm thử cần phản ánh proxy thực tế: proxy phải ghi đè forwarded header từ client, còn ứng dụng chỉ tin các proxy nằm trong trust boundary.

### Kiểm tra log và telemetry

Unit test response không đủ để chứng minh token đã được redact khỏi access log, tracing hoặc analytics. Cần kiểm tra cấu hình logging ở gateway, servlet container, application và APM; có thể dùng integration test để xác nhận các trường nhạy cảm không xuất hiện trong event được ghi. Không ghi chính secret vào test report hoặc CI output.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đưa access token vào query string | Token có thể bị ghi vào log, history, referrer và cache. | Dùng `Authorization` header. |
| Đưa PII vào path/query | Dữ liệu cá nhân bị sao chép qua nhiều hệ thống. | Dùng identifier không mang PII; dùng body cho search nhạy cảm khi phù hợp. |
| Nghĩ HTTPS che giấu URL khỏi log | Proxy và server kết thúc TLS vẫn thấy URI. | Redact ở mọi lớp logging và không đặt secret trong URL. |
| Coi UUID là cơ chế bảo mật | ID vẫn có thể bị lộ hoặc chia sẻ. | Authorization ở từng endpoint. |
| Coi capability URL như link thông thường | Người có URL có thể dùng quyền của nó. | Scope hẹp, TTL ngắn, one-time/revocable, no-store và redaction. |
| Chỉ kiểm tra `_links` mà bỏ qua `_embedded` | PII vẫn có thể lộ trong embedded representation. | Dùng DTO/projection và kiểm thử toàn bộ response. |
| Công bố action link cho mọi user | Lộ capability hoặc trạng thái nội bộ. | Điều kiện hóa link theo quyền/trạng thái và bảo vệ endpoint. |
| Chỉ ẩn link để bảo mật | Client có thể gọi target trực tiếp. | Kiểm tra authorization tại endpoint. |
| Tin `X-Forwarded-Host` từ client | Link có thể trỏ đến host giả mạo. | Chỉ tin proxy đáng tin cậy và ghi đè header. |
| Cache response theo user trong shared cache | Link riêng tư có thể bị trả cho user khác. | `private` hoặc `no-store` theo độ nhạy; thiết kế cache key đúng. |
| Không kiểm soát Referer | URL capability có thể bị gửi sang trang khác. | `Referrer-Policy: no-referrer` và loại bỏ secret khỏi URL. |

## Ghi nhớ

- Mọi thành phần của hypermedia response đều có thể tiết lộ dữ liệu: `href`, relation, title, CURIE, URI template và `_embedded`.
- Không đặt bearer token, session ID, password hoặc API key trong path/query; dùng `Authorization` header.
- PII và filter nhạy cảm cũng có thể lộ qua URL; cân nhắc POST search với body khi phù hợp và vẫn redaction body logs.
- Capability URL là credential dạng bearer; giới hạn scope, thời hạn, số lần dùng và khả năng thu hồi.
- HTTPS bảo vệ đường truyền nhưng không che URL khỏi browser, proxy, server log, tracing hoặc cache.
- Chỉ công bố action link theo quyền/trạng thái; endpoint vẫn phải authorize mỗi request.
- Kiểm soát dữ liệu trong `_embedded`, relation name, title và URI template.
- Không để link lộ host/port nội bộ; cấu hình forwarded headers và chỉ tin proxy đáng tin cậy.
- Dùng `Referrer-Policy` và `Cache-Control` phù hợp cho response nhạy cảm; redaction log ở mọi tầng.
- Client chỉ gửi credential đến origin tin cậy khi follow link; server-side client cần chống SSRF.
- Kiểm thử response, headers, quyền, host, logs và telemetry; không chỉ kiểm tra một `href`.

## Tài liệu tham khảo

- [RFC 6750 – OAuth 2.0 Bearer Token Usage, Section 2.3](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.3)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [W3C – Referrer Policy](https://www.w3.org/TR/referrer-policy/)
- [OWASP – Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
- [OWASP – REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
