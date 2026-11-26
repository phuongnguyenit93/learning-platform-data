# ETag

Một REST API thường trả cùng một tài nguyên nhiều lần: trình duyệt mở lại trang đơn hàng, ứng dụng di động làm mới màn hình hoặc một API gateway truy vấn lại catalog. Nếu representation không đổi, việc gửi lại toàn bộ JSON vừa tốn băng thông vừa tăng tải serialization và mạng. Nếu representation đã đổi, client vẫn cần nhận phiên bản mới để không hiển thị dữ liệu cũ.

HTTP giải quyết bài toán xác thực phiên bản bằng **ETag (Entity Tag)**. Server gắn một validator vào response; client lưu validator đó và gửi lại trong request tiếp theo. Server có thể xác nhận representation vẫn còn hiệu lực mà không phải truyền lại body. ETag cũng có thể được dùng để bảo vệ thao tác ghi khỏi việc cập nhật đè lên phiên bản mà client chưa từng đọc.

Trong Spring HATEOAS, response không chỉ gồm các trường dữ liệu mà còn có thể chứa _links, _embedded và affordances. Vì vậy, ETag cần xác thực đúng representation mà server đã gửi, không chỉ một bản ghi domain. Bài học này trình bày cách thiết kế validator, xử lý conditional request bằng Spring MVC, kết hợp ResponseEntity với representation model, và kiểm thử cache validation cùng optimistic concurrency.

Sau bài học, bạn có thể:

- Giải thích ETag là gì và phân biệt strong ETag với weak ETag.
- Xác định phạm vi representation mà ETag cần đại diện trong HAL.
- Tạo ETag ổn định từ phiên bản tài nguyên hoặc từ representation.
- Xử lý If-None-Match cho conditional GET và trả 304 Not Modified.
- Dùng If-Match để bảo vệ PUT/DELETE và trả 412 Precondition Failed khi phiên bản đã cũ.
- Kết hợp WebRequest.checkNotModified, ResponseEntity, Cache-Control và Vary.
- Phân biệt controller-level validation với ShallowEtagHeaderFilter.
- Kiểm thử ETag, body, status và hành vi cập nhật đồng thời bằng MockMvc.

## ETag là gì?

ETag là một HTTP response header chứa entity tag do server tạo ra để định danh một phiên bản của representation được chọn cho request. Giá trị này là một chuỗi opaque (client không cần hiểu cấu trúc bên trong), được đặt trong dấu ngoặc kép:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-42-v7-hal-v1"

{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": { "href": "/orders/42" }
  }
}
~~~

Chuỗi order-42-v7-hal-v1 chỉ là ví dụ. ETag không bắt buộc phải là ID, số version hoặc hash; server được quyền chọn cách tạo validator miễn là tuân thủ semantics của HTTP. Client phải xem giá trị này là opaque và gửi lại nguyên vẹn trong request có điều kiện.

### ETag không phải Cache-Control

ETag và Cache-Control giải quyết hai câu hỏi khác nhau:

- **Cache-Control** quyết định response có thể được lưu ở đâu, được dùng lại trong bao lâu và có cần xác thực lại trước khi dùng hay không.
- **ETag** giúp client hoặc cache xác thực representation đã lưu có còn tương ứng với representation hiện tại của server hay không.

Ví dụ, Cache-Control: private, max-age=60 cho phép cache riêng của người dùng dùng lại response trong 60 giây mà chưa cần hỏi server. Sau khi response trở nên stale, cache có thể gửi If-None-Match cùng ETag đã lưu. Nếu representation vẫn không đổi, server trả 304 thay vì gửi lại JSON.

| Header/directive | Ý nghĩa |
| --- | --- |
| ETag | Validator của representation hiện tại |
| If-None-Match | Hỏi server representation có khác các ETag client đã lưu không |
| If-Match | Chỉ thực hiện thao tác nếu representation hiện tại khớp ETag client cung cấp |
| Cache-Control: max-age | Thời gian response còn fresh trong cache |
| Cache-Control: no-cache | Có thể lưu nhưng phải revalidate trước khi dùng lại |
| Cache-Control: no-store | Không lưu response vào cache |
| Cache-Control: private | Chỉ cache riêng của client, không dùng shared cache |
| Vary | Khai báo request headers làm thay đổi representation được chọn |

ETag không thay thế authorization. Client biết ETag của tài nguyên không có nghĩa là được quyền đọc hoặc cập nhật tài nguyên đó.

## Strong ETag và weak ETag

HTTP có hai loại entity tag:

- **Strong ETag** không có tiền tố W/, ví dụ "order-42-v7". Strong validator chỉ được giữ nguyên khi representation data vẫn tương đương byte-for-byte theo yêu cầu của HTTP.
- **Weak ETag** có tiền tố W/, ví dụ W/"order-42-v7". Weak validator cho phép server coi hai representation là tương đương về ngữ nghĩa ngay cả khi dữ liệu biểu diễn có khác biệt nhỏ.

| Loại | Ví dụ | Strong comparison | Weak comparison | Tình huống |
| --- | --- | --- | --- | --- |
| Strong | "v7" | Khớp với "v7" | Khớp với "v7" | Xác thực representation chính xác, optimistic concurrency |
| Weak | W/"v7" | Không khớp với "v7" hoặc W/"v7" | Khớp với "v7" và W/"v7" | Cache validation khi thay đổi byte không làm thay đổi ý nghĩa |

Sự khác nhau quan trọng nằm ở cách HTTP so sánh validator:

- If-None-Match dùng **weak comparison**. Vì vậy weak ETag có thể được dùng cho conditional GET.
- If-Match dùng **strong comparison**. Weak ETag không thể thỏa mãn điều kiện này, nên không dùng weak ETag làm cơ chế bảo vệ cập nhật.

Nếu API chỉ cần cache validation cho GET, weak ETag có thể phù hợp khi server có thể bảo đảm representation tương đương về ngữ nghĩa. Nếu API dùng ETag để ngăn lost update qua PUT hoặc DELETE, cần strong ETag.

## Chọn cách tạo ETag cho representation HATEOAS

Một ETag chỉ có giá trị nếu nó thay đổi khi representation cần được xác thực thay đổi. Có hai cách phổ biến để tạo tag.

### Dựa trên phiên bản tài nguyên

Nếu entity có trường version tăng mỗi khi trạng thái nghiệp vụ thay đổi, server có thể tạo ETag từ ID và version:

~~~java
private String etagFor(Order order) {
    return "\"order-" + order.id()
        + "-v" + order.version()
        + "-hal-v1\"";
}
~~~

Đây là ví dụ strong ETag khi thỏa mãn các giả định sau:

1. order.version() tăng mỗi khi bất kỳ trường nào xuất hiện trong representation thay đổi.
2. hal-v1 được thay đổi khi cấu trúc representation, relation hoặc affordance làm thay đổi body.
3. Những yếu tố động khác có thể thay đổi representation, chẳng hạn base URI, tenant, ngôn ngữ hoặc quyền của người dùng, cũng được tính vào validator hoặc được xử lý bằng cache variation phù hợp.

Không được mặc định rằng version của một hàng trong database luôn đại diện đầy đủ cho representation HATEOAS. Ví dụ, dữ liệu đơn hàng không đổi nhưng controller đổi relation từ cancel sang void, thêm affordance hoặc thay URI của self link. Body HAL đã thay đổi; nếu ETag vẫn giữ nguyên, cache có thể sử dụng representation cũ.

### Dựa trên nội dung representation

Server có thể tạo hash từ byte của representation đã serialize. Cách này phản ánh trực tiếp body được gửi:

~~~text
Representation HAL
       |
       v
Serialize theo media type đã chọn
       |
       v
Hash byte của representation
       |
       v
ETag: "hash-value"
~~~

Hash cần được tính từ cùng một representation mà response thực sự gửi. Nếu chỉ hash DTO nhưng bỏ qua _links, _embedded hoặc affordances, validator không đại diện cho toàn bộ body. Khi có nhiều media type hoặc ngôn ngữ, mỗi representation variant cần validator phù hợp.

Không nên serialize tùy tiện một object lần thứ hai chỉ để tạo ETag nếu việc serialize có thể tạo links khác với response thực tế. Với strong ETag, điều quan trọng là validator phải gắn với đúng representation bytes; với weak ETag, server vẫn phải bảo đảm các representation được coi là tương đương về ngữ nghĩa.

### Những phần cần tính đến trong Spring HATEOAS

Khi tạo ETag cho HAL, cần xem xét toàn bộ các thành phần có thể xuất hiện trong body:

- Content của EntityModel<T>.
- Relation và href trong _links, bao gồm self, next, prev hoặc custom relation.
- Các item được serialize trong _embedded.
- Affordances hoặc metadata được bổ sung bởi cấu hình representation.
- Media type hoặc profile được chọn thông qua content negotiation.
- Request context nếu URI hoặc nội dung phụ thuộc host, scheme, locale, tenant hay quyền.

Nếu endpoint chỉ trả một HAL representation cố định, ETag có thể dựa trên resource version cộng với revision của representation. Nếu cùng URI có thể trả HAL JSON, JSON khác hoặc representation theo ngôn ngữ, cần phân biệt validator theo variant và khai báo Vary cho các request headers có ảnh hưởng.

Không đưa dữ liệu bí mật hoặc thông tin nhạy cảm vào ETag. ETag là header có thể được client lưu và gửi lại; một tag có thể là hash hoặc token opaque thay vì để lộ trực tiếp version nội bộ.

## Conditional GET với If-None-Match

Conditional GET giúp client không phải tải lại body khi representation chưa thay đổi.

Luồng xử lý:

1. Client gọi GET lần đầu.
2. Server trả 200 OK, body representation và header ETag.
3. Client lưu body cùng ETag.
4. Lần sau client gửi GET với If-None-Match bằng ETag đã lưu.
5. Server so sánh validator với representation hiện tại.
6. Nếu còn tương ứng, server trả 304 Not Modified và không gửi lại body; nếu đã khác, server trả 200 OK cùng representation mới và ETag mới.

### Request và response

Lần đọc đầu:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-42-v7-hal-v1"
Cache-Control: private, max-age=60

{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": { "href": "/orders/42" },
    "invoice": { "href": "/orders/42/invoice" }
  }
}
~~~

Lần đọc tiếp theo:

~~~http
GET /orders/42
Accept: application/hal+json
If-None-Match: "order-42-v7-hal-v1"
~~~

Nếu representation chưa thay đổi:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-42-v7-hal-v1"
Cache-Control: private, max-age=60
~~~

Response 304 không chứa representation body. Client dùng body đã lưu trước đó và cập nhật metadata cache theo response mới.

Nếu server đã thay đổi status hoặc links, ETag hiện tại sẽ khác; server trả 200 cùng body mới. If-None-Match cũng có thể chứa danh sách nhiều tag hoặc wildcard *; không nên tự parse header bằng phép so sánh chuỗi đơn giản.

### Dùng WebRequest.checkNotModified trong Spring MVC

Spring MVC cung cấp WebRequest.checkNotModified(String) để xử lý conditional request. Phương thức này kiểm tra validator theo HTTP preconditions, đồng thời đặt ETag và status thích hợp. Khi phương thức trả về true, controller có thể dừng xử lý bằng cách trả null.

~~~java
import java.time.Duration;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.context.request.WebRequest;

@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> one(
        @PathVariable Long id,
        WebRequest webRequest) {

    Order order = orderService.get(id);
    String etag = etagFor(order);

    if (webRequest.checkNotModified(etag)) {
        return null;
    }

    EntityModel<OrderResponse> model = assembler.toModel(order);

    return ResponseEntity.ok()
        .eTag(etag)
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(1)).cachePrivate())
        .varyBy(HttpHeaders.ACCEPT)
        .body(model);
}
~~~

Trong ví dụ, etagFor trả về một strong ETag đã có dấu ngoặc kép. Khi If-None-Match khớp, checkNotModified đặt status 304 và controller không serialize body. Khi không khớp, controller tạo EntityModel và trả response 200 cùng ETag.

Vary: Accept phù hợp khi cùng URI có thể trả nhiều media type theo header Accept. Nếu endpoint chỉ hỗ trợ một media type và không có variation theo header này, có thể bỏ varyBy. Nếu nội dung còn phụ thuộc Accept-Language hoặc request header khác, hãy khai báo các header tương ứng.

### Kết hợp Last-Modified và ETag

HTTP cho phép server cung cấp cả ETag và Last-Modified. ETag thường có độ chính xác tốt hơn timestamp, đặc biệt khi nhiều thay đổi có thể xảy ra trong cùng một giây. Spring hỗ trợ:

~~~java
if (webRequest.checkNotModified(etag, order.lastModifiedAt().toEpochMilli())) {
    return null;
}
~~~

Khi cần cả hai validator, WebRequest.checkNotModified(String, long) sẽ đánh giá các preconditions theo thứ tự HTTP. Không tự kiểm tra If-Modified-Since trước If-None-Match bằng logic riêng vì có thể làm sai thứ tự ưu tiên của conditional headers.

## Conditional update với If-Match

ETag không chỉ giúp tiết kiệm băng thông. Nó còn giúp bảo vệ tài nguyên khỏi lost update.

Giả sử hai người dùng cùng tải đơn hàng ở version 7:

1. Người dùng A đọc ETag "order-42-v7-hal-v1".
2. Người dùng B cũng đọc cùng version.
3. A cập nhật trạng thái đơn hàng; server lưu version 8.
4. B gửi PUT dựa trên dữ liệu version 7.

Nếu server chấp nhận PUT của B mà không kiểm tra phiên bản, thay đổi của A có thể bị ghi đè. Client nên gửi If-Match để chỉ cập nhật nếu representation hiện tại vẫn khớp validator mà client đã đọc.

Request:

~~~http
PUT /orders/42
Content-Type: application/json
Accept: application/hal+json
If-Match: "order-42-v7-hal-v1"

{
  "deliveryAddress": "12 Nguyen Hue"
}
~~~

Nếu ETag hiện tại vẫn là version 7, server có thể thực hiện cập nhật. Nếu server đã chuyển sang version 8, điều kiện không thỏa mãn và response là:

~~~http
HTTP/1.1 412 Precondition Failed
~~~

Client cần tải representation mới, xử lý xung đột và gửi lại thao tác dựa trên phiên bản mới nếu nghiệp vụ cho phép.

### Dùng WebRequest.checkNotModified cho PUT

Trong Spring MVC, WebRequest.checkNotModified không chỉ dành cho GET. Nó còn đánh giá conditional request trên POST, PUT và DELETE. Với phương thức ghi, If-Match được kiểm tra bằng strong comparison; khi điều kiện thất bại, Spring đặt 412 Precondition Failed.

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.context.request.WebRequest;

@PutMapping(
    value = "/{id}",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<EntityModel<OrderResponse>> update(
        @PathVariable Long id,
        @RequestBody UpdateOrderRequest request,
        WebRequest webRequest) {

    if (webRequest.getHeader(HttpHeaders.IF_MATCH) == null) {
        return ResponseEntity.status(HttpStatus.PRECONDITION_REQUIRED).build();
    }

    Order current = orderService.get(id);
    String currentEtag = etagFor(current);

    if (webRequest.checkNotModified(currentEtag)) {
        return null;
    }

    Order updated = orderService.updateIfVersion(
        id, current.version(), request);

    EntityModel<OrderResponse> model = assembler.toModel(updated);
    String newEtag = etagFor(updated);

    return ResponseEntity.ok()
        .eTag(newEtag)
        .body(model);
}
~~~

Ví dụ giả định API yêu cầu If-Match cho mọi PUT. Nếu client không gửi precondition, server trả 428 Precondition Required. Nếu header có nhưng không khớp, checkNotModified trả true, Spring đã đặt 412 và controller dừng mà không cập nhật. Nếu header khớp, controller tiếp tục cập nhật và trả representation mới cùng ETag mới.

WebRequest.checkNotModified hỗ trợ danh sách ETag và wildcard theo semantics HTTP; không tự viết requestHeader.equals(currentEtag) vì cách đó không xử lý đầy đủ nhiều tag, wildcard, weak/strong comparison và các quy tắc precondition.

### Bảo vệ race condition ở tầng persistence

Kiểm tra If-Match trước khi gọi service vẫn chưa đủ để bảo vệ mọi trường hợp đồng thời. Một request khác có thể cập nhật tài nguyên sau bước kiểm tra nhưng trước khi transaction ghi dữ liệu. Cần bảo vệ thao tác ghi một cách nguyên tử ở tầng persistence.

Với JPA, có thể dùng optimistic locking bằng @Version:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Order {

    @Id
    private Long id;

    @Version
    private long version;

    Long id() { return id; }

    long version() { return version; }

    // Other fields and methods.
}
~~~

Service updateIfVersion phải thực hiện trong transaction, kiểm tra version mong đợi với entity được load trong transaction, áp dụng thay đổi trên chính entity đó và flush để JPA thực hiện optimistic lock. Nếu một transaction khác đã thay đổi entity, cập nhật version có thể thất bại và Spring ném exception optimistic locking.

Đối với endpoint yêu cầu If-Match, hãy ánh xạ lỗi stale version phát sinh trong transaction thành 412 Precondition Failed. Có thể dùng @RestControllerAdvice để xử lý ObjectOptimisticLockingFailureException hoặc exception nghiệp vụ riêng. Không nên chỉ so sánh version trong controller rồi bỏ qua optimistic locking ở database, vì cách đó vẫn còn khoảng thời gian race condition.

Phân biệt:

| Status | Ý nghĩa |
| --- | --- |
| 412 Precondition Failed | Điều kiện HTTP như If-Match không thỏa mãn |
| 428 Precondition Required | API yêu cầu precondition nhưng client không gửi |
| 409 Conflict | Xung đột nghiệp vụ không nhất thiết xuất phát từ HTTP precondition |
| 404 Not Found | Resource không tồn tại |

### If-Match cho DELETE

DELETE cũng có thể yêu cầu client xác nhận phiên bản trước khi xóa. Ví dụ:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.context.request.WebRequest;

@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(
        @PathVariable Long id,
        WebRequest webRequest) {

    if (webRequest.getHeader(HttpHeaders.IF_MATCH) == null) {
        return ResponseEntity.status(HttpStatus.PRECONDITION_REQUIRED).build();
    }

    Order current = orderService.get(id);

    if (webRequest.checkNotModified(etagFor(current))) {
        return null;
    }

    orderService.deleteIfVersion(id, current.version());
    return ResponseEntity.noContent().build();
}
~~~

Service cần thực hiện xóa có kiểm tra version trong transaction hoặc bằng câu lệnh delete có điều kiện version. Nếu dữ liệu thay đổi sau bước kiểm tra ban đầu, thao tác xóa phải thất bại thay vì xóa nhầm phiên bản mới hơn.

## ETag trong response tạo mới và cập nhật

Khi POST tạo tài nguyên, response 201 Created có thể trả đồng thời:

- Location: URI của resource mới.
- ETag: validator của representation vừa tạo.
- Body: EntityModel<T> có self link và các relation cần thiết.

~~~java
import java.net.URI;

Order created = orderService.create(request);
EntityModel<OrderResponse> model = assembler.toModel(created);
URI location = URI.create(model.getRequiredLink("self").getHref());

return ResponseEntity.created(location)
    .eTag(etagFor(created))
    .body(model);
~~~

Client có thể lưu ETag này để thực hiện GET có điều kiện hoặc gửi If-Match trong lần cập nhật sau. Sau mỗi cập nhật thành công, server cần trả ETag mới tương ứng representation mới; không tiếp tục gửi tag của version trước.

## ETag và Cache-Control cho HAL

ETag là validator, còn cache policy xác định cách cache sử dụng response. Một số lựa chọn:

~~~java
return ResponseEntity.ok()
    .eTag(etag)
    .cacheControl(CacheControl.maxAge(Duration.ofMinutes(2)).cachePrivate())
    .varyBy(HttpHeaders.ACCEPT)
    .body(model);
~~~

Đoạn code trên phù hợp với representation chỉ dành cho cache riêng của client và có thể được dùng lại trong hai phút. Khi response stale, cache có thể revalidate bằng ETag.

Một số nguyên tắc:

- **Dữ liệu công khai, ổn định:** có thể cân nhắc public và max-age nếu representation thực sự không phụ thuộc user.
- **Dữ liệu cá nhân:** ưu tiên private hoặc policy chặt hơn; không dùng shared cache nếu response phụ thuộc quyền hoặc danh tính.
- **Dữ liệu nhạy cảm:** cân nhắc no-store.
- **Luôn cần kiểm tra quyền trước khi trả dữ liệu:** ETag không phải cơ chế phân quyền và không được dùng để bỏ qua authorization.
- **Nhiều media type:** khai báo Vary: Accept và tạo ETag riêng cho từng representation variant.
- **Nội dung đa ngôn ngữ:** nếu Accept-Language làm thay đổi body hoặc links, cần Vary: Accept-Language và validator phù hợp.

Nếu API có HAL JSON và một representation khác, không nên dùng cùng một strong ETag chỉ dựa trên version database khi cấu trúc byte của hai representation khác nhau. Hãy tạo tag theo media type/profile hoặc hash từng representation variant.

## ShallowEtagHeaderFilter

Spring MVC cung cấp ShallowEtagHeaderFilter để tạo ETag từ response content. Filter bọc response, lưu nội dung được ghi, tính hash rồi so sánh với If-None-Match. Nếu khớp, response body không được gửi lại và status trở thành 304.

Filter có thể phù hợp với endpoint GET đơn giản khi muốn bổ sung ETag mà không viết logic validator trong từng controller. Tuy nhiên, có một giới hạn quan trọng: **filter vẫn phải thực thi controller và tạo toàn bộ response body trước khi tính hash**. Vì vậy, filter tiết kiệm băng thông nhưng không tiết kiệm đáng kể CPU, database query hoặc chi phí dựng representation.

So sánh:

| Tiêu chí | Controller-level checkNotModified | ShallowEtagHeaderFilter |
| --- | --- | --- |
| Thời điểm có ETag | Có thể tính trước khi dựng body | Sau khi response body được tạo |
| Tiết kiệm băng thông | Có | Có |
| Tránh dựng lại representation | Có thể, nếu validator tính từ version/metadata | Không |
| Hỗ trợ If-Match cho thao tác ghi | Có qua WebRequest.checkNotModified | Không thuộc phạm vi filter |
| Kiểm soát validator theo HATEOAS variant | Chủ động | Dựa trên body đã serialize |
| Phù hợp | API cần tối ưu query/serialization và kiểm soát precondition | Endpoint GET đơn giản, body đã được tạo sẵn |

Filter không thay thế optimistic concurrency. Nó cũng không phải lựa chọn phù hợp cho response streaming vì cần buffer response content để tính hash. Với API HATEOAS cần xử lý cả conditional GET lẫn If-Match cho PUT/DELETE, controller-level validation thường linh hoạt hơn.

## Kiểm thử ETag bằng MockMvc

Kiểm thử ETag nên xác minh status, header và body. Chỉ kiểm tra ETag tồn tại chưa chứng minh conditional request được xử lý đúng.

### Kiểm thử GET lần đầu

~~~java
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class OrderEtagTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsHalRepresentationAndEtag() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42L)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(header().exists("ETag"))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Test giả định order 42 tồn tại và assembler tạo self link. ETag được trả cùng representation HAL.

### Kiểm thử conditional GET trả 304

Có thể lấy ETag từ response đầu tiên rồi gửi lại trong If-None-Match:

~~~java
@Test
void returnsNotModifiedWhenEtagMatches() throws Exception {
    MvcResult firstResponse = mockMvc.perform(get("/orders/{id}", 42L)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

    String etag = firstResponse.getResponse().getHeader("ETag");

    mockMvc.perform(get("/orders/{id}", 42L)
            .accept(MediaTypes.HAL_JSON)
            .header(HttpHeaders.IF_NONE_MATCH, etag))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
}
~~~

Test giả định tài nguyên không thay đổi giữa hai request. Response thứ hai phải là 304 và không có body. Có thể kiểm tra ETag response vẫn được giữ lại nếu hợp đồng API yêu cầu.

### Kiểm thử ETag thay đổi khi resource thay đổi

~~~java
@Test
void returnsNewRepresentationWhenEtagIsStale() throws Exception {
    MvcResult firstResponse = mockMvc.perform(get("/orders/{id}", 42L)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

    String oldEtag = firstResponse.getResponse().getHeader("ETag");

    // Thực hiện thay đổi order bằng fixture hoặc service test setup.

    MvcResult updatedResponse = mockMvc.perform(get("/orders/{id}", 42L)
            .accept(MediaTypes.HAL_JSON)
            .header(HttpHeaders.IF_NONE_MATCH, oldEtag))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andExpect(jsonPath("$.status").exists())
        .andReturn();

    assertNotEquals(oldEtag, updatedResponse.getResponse().getHeader("ETag"));
}
~~~

Test cần chuẩn bị dữ liệu để thay đổi thực sự làm representation thay đổi. Nên kiểm tra ETag mới khác ETag cũ, đồng thời body phản ánh dữ liệu hoặc links mới.

### Kiểm thử If-Match cho PUT

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

@Test
void rejectsUpdateWithStaleEtag() throws Exception {
    mockMvc.perform(put("/orders/{id}", 42L)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .header(HttpHeaders.IF_MATCH, "\"order-42-v6-hal-v1\"")
            .content("""
                {
                  "deliveryAddress": "12 Nguyen Hue"
                }
                """))
        .andExpect(status().isPreconditionFailed());
}
~~~

Test giả định order hiện tại có ETag version 7 và API yêu cầu If-Match. Request dùng version 6 nên phải nhận 412 và không được thay đổi dữ liệu.

Các trường hợp nên kiểm thử thêm:

1. GET trả 200 cùng ETag và HAL body.
2. GET với If-None-Match khớp trả 304, không có body.
3. GET với ETag cũ sau khi representation thay đổi trả 200 cùng ETag mới.
4. If-None-Match hỗ trợ danh sách tag và wildcard theo semantics HTTP.
5. PUT với If-Match đúng được phép cập nhật và trả ETag mới.
6. PUT với If-Match cũ hoặc weak ETag nhận 412.
7. PUT thiếu If-Match nhận 428 nếu API yêu cầu precondition.
8. Hai request cập nhật đồng thời không làm mất thay đổi; optimistic locking phát hiện stale write.
9. DELETE với If-Match cũ không xóa tài nguyên.
10. ETag thay đổi khi content, _links, _embedded hoặc affordances thay đổi.
11. Representation theo media type hoặc ngôn ngữ có ETag và Vary phù hợp.
12. Response cá nhân không bị cấu hình cache công khai ngoài ý muốn.

## Những sai lầm thường gặp

**Tạo ETag chỉ từ một trường không đại diện đầy đủ response.** Nếu links, embedded resources hoặc affordances thay đổi mà ETag không đổi, cache có thể dùng body cũ. Hãy xác định rõ validator đại diện cho toàn bộ selected representation.

**Nhầm ETag với thời gian cache.** ETag không quy định response fresh trong bao lâu. Hãy kết hợp với Cache-Control phù hợp.

**Dùng weak ETag cho If-Match.** If-Match sử dụng strong comparison; weak validator không thỏa mãn điều kiện optimistic concurrency.

**Tự so sánh chuỗi If-Match.** Header có thể chứa nhiều tag hoặc wildcard. Dùng WebRequest.checkNotModified hoặc cơ chế parser theo HTTP semantics.

**Chỉ kiểm tra version ở controller.** Một transaction khác có thể thay đổi dữ liệu ngay sau bước kiểm tra. Cần optimistic locking hoặc conditional update nguyên tử ở tầng persistence.

**Trả body cùng 304.** 304 Not Modified không mang representation body; client sử dụng bản đã cache.

**Trả 409 cho mọi ETag mismatch.** Khi HTTP precondition không thỏa mãn, dùng 412. Dành 409 cho xung đột nghiệp vụ khác.

**Cho rằng ShallowEtagHeaderFilter tránh mọi chi phí xử lý.** Filter chỉ tính hash sau khi body đã được dựng; nó chủ yếu tiết kiệm băng thông.

**Dùng cùng strong ETag cho mọi media type.** Strong validator phải phù hợp với selected representation. Dùng Vary và tag riêng cho các variant.

**Dùng cache công khai cho representation phụ thuộc người dùng.** ETag không bảo vệ dữ liệu riêng tư; hãy chọn private hoặc no-store khi cần.

## Kết luận

ETag là validator của HTTP representation. Với Spring HATEOAS, representation bao gồm content cùng hypermedia links, embedded resources và affordances. Strong ETag phù hợp cho việc xác thực chính xác representation và bảo vệ thao tác ghi; weak ETag có thể dùng cho cache validation khi server chỉ cần bảo đảm tương đương về ngữ nghĩa.

Trong Spring MVC, WebRequest.checkNotModified hỗ trợ conditional request và giúp controller dừng sớm khi If-None-Match hoặc If-Match không thỏa mãn. Kết hợp với ResponseEntity.eTag, Cache-Control, Vary và optimistic locking ở tầng persistence, API có thể vừa giảm dữ liệu truyền qua mạng vừa ngăn lost update. ShallowEtagHeaderFilter là lựa chọn đơn giản cho GET nhưng không thay thế controller-level validation khi cần kiểm soát version và thao tác ghi.

Tài liệu tham khảo:

- [RFC 9110 — HTTP Semantics, Entity Tags](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.8.3).
- [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).
- [RFC 9110 — If-None-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2).
- [RFC 6585 — 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3).
- [Spring Framework API — ServletWebRequest.checkNotModified](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html).
- [Spring Framework API — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html).
- [Spring Framework Reference — Shallow ETag filter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Spring HATEOAS Reference — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models).
