# If-Modified-Since và kiểm tra thời điểm thay đổi trong Spring Data REST

Spring Data REST hỗ trợ conditional GET bằng header HTTP `Last-Modified` và `If-Modified-Since`. Cơ chế này cho phép client hỏi server xem một tài nguyên có thay đổi kể từ lần đọc trước hay chưa. Nếu chưa thay đổi, server có thể trả `304 Not Modified` và bỏ phần response body, giúp giảm băng thông và thời gian truyền dữ liệu.

Để Spring Data REST có thời điểm thay đổi của một entity, domain type cần có thuộc tính được đánh dấu bằng `@LastModifiedDate` và auditing phải được bật. Client lưu giá trị `Last-Modified` nhận được rồi gửi lại trong `If-Modified-Since` khi yêu cầu đúng cùng tài nguyên.

## 1. Last-Modified và If-Modified-Since hoạt động như thế nào?

Hai header tạo thành một cơ chế kiểm tra cache theo thời gian:

- **`Last-Modified`** là response header cho biết thời điểm tài nguyên được sửa lần cuối theo dữ liệu server.
- **`If-Modified-Since`** là request header cho biết thời điểm mà client đã có bản representation trước đó.
- Nếu tài nguyên được sửa sau thời điểm client gửi, server trả representation mới, thường với HTTP `200 OK` và giá trị `Last-Modified` mới.
- Nếu tài nguyên chưa được sửa sau thời điểm đó, server trả HTTP `304 Not Modified`, không gửi lại representation trong response body.

Ví dụ response đầu tiên:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT

{
  "id": 42,
  "name": "An Nguyen"
}
~~~

Client lưu giá trị header:

~~~text
Wed, 11 Nov 2026 02:30:00 GMT
~~~

Ở lần đọc tiếp theo, client gửi:

~~~http
GET /people/42
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
Accept: application/hal+json
~~~

Nếu tài nguyên không thay đổi kể từ thời điểm trên, response có thể là:

~~~http
HTTP/1.1 304 Not Modified
~~~

Client giữ bản representation đã cache và không cần tải lại nội dung.

## 2. Cấu hình @LastModifiedDate cho domain entity

Spring Data Commons cung cấp annotation `@LastModifiedDate` để lưu thời điểm entity được sửa gần nhất. Spring Data REST sử dụng metadata này để tạo response header `Last-Modified`.

Ví dụ với Spring Data JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // getters and setters
}
~~~

Các thành phần chính:

- `@LastModifiedDate` đánh dấu thuộc tính lưu thời điểm sửa gần nhất.
- `Instant` biểu diễn thời điểm trên dòng thời gian UTC, phù hợp với dữ liệu audit.
- `@EntityListeners(AuditingEntityListener.class)` kết nối entity với auditing listener của Spring Data JPA.
- Auditing infrastructure cập nhật thuộc tính khi entity được tạo hoặc sửa theo lifecycle persistence tương ứng.

Tên thuộc tính không bắt buộc phải là `lastModifiedDate`, nhưng nên đặt tên rõ nghĩa và chọn kiểu dữ liệu được Spring Data auditing hỗ trợ.

## 3. Bật auditing trong Spring Data JPA

Chỉ thêm `@LastModifiedDate` vào entity là chưa đủ. Ứng dụng cần bật auditing để Spring Data đăng ký cơ chế cập nhật metadata.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

Nếu ứng dụng dùng Spring Boot, class cấu hình này cần nằm trong phạm vi component scan hoặc được import vào ApplicationContext.

Với Spring Data module khác, dùng cấu hình auditing tương ứng của module đó, ví dụ `@EnableMongoAuditing` cho MongoDB. Không áp dụng JPA `AuditingEntityListener` cho mọi store.

Có thể kết hợp `@CreatedDate` và `@LastModifiedDate` nếu cần lưu cả thời điểm tạo và sửa:

~~~java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
~~~

Nếu chỉ theo dõi thời điểm, ứng dụng không bắt buộc phải triển khai `AuditorAware`. Interface này chỉ cần khi muốn ghi nhận người tạo hoặc người sửa thông qua `@CreatedBy` và `@LastModifiedBy`.

## 4. Spring Data REST trả về Last-Modified

Khi repository công bố entity có thuộc tính `@LastModifiedDate`, Spring Data REST có thể đưa thời điểm đó vào response header `Last-Modified` của item resource.

Ví dụ request:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT
ETag: "7"

{
  "id": 42,
  "name": "An Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Header `Last-Modified` dùng định dạng HTTP-date và biểu diễn thời gian theo GMT. Ví dụ trên minh họa cấu trúc response; giá trị ETag chỉ xuất hiện khi entity và cấu hình hỗ trợ cơ chế ETag.

Client nên lưu header nhận được từ response thay vì tự tạo chuỗi ngày giờ. Giá trị này đã được server định dạng đúng để dùng cho request có điều kiện tiếp theo.

## 5. Gửi If-Modified-Since trong request tiếp theo

Dùng chính giá trị `Last-Modified` đã nhận ở lần GET trước:

~~~http
GET /people/42
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
Accept: application/hal+json
~~~

Spring Data REST kiểm tra thời điểm sửa gần nhất của tài nguyên:

- Nếu thời điểm sửa mới hơn giá trị `If-Modified-Since`, server trả nội dung mới và header `Last-Modified` cập nhật.
- Nếu thời điểm sửa không mới hơn giá trị client gửi, server trả `304 Not Modified`.

Ví dụ khi tài nguyên đã được sửa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 03:15:00 GMT

{
  "id": 42,
  "name": "Anh Nguyen"
}
~~~

Client thay giá trị cache validator cũ bằng `Last-Modified` mới và lưu representation mới.

Ví dụ khi tài nguyên chưa thay đổi:

~~~http
HTTP/1.1 304 Not Modified
~~~

Response `304` không mang body của tài nguyên. Client sử dụng representation đã lưu trong cache.

## 6. Dùng đúng URI và query parameter

Giá trị `Last-Modified` phải được gắn với đúng representation mà client đã tải. Không dùng timestamp lấy từ một URI cho một URI khác hoặc cho một truy vấn có tham số khác.

Ví dụ client đã đọc:

~~~http
GET /orders/42?projection=orderSummary
~~~

thì nên gửi lại `If-Modified-Since` cho chính URI và query parameter đó:

~~~http
GET /orders/42?projection=orderSummary
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
~~~

Không lấy header từ `/orders/42` rồi dùng cho `/orders/43`, hoặc lấy từ projection `orderSummary` rồi dùng cho projection khác. Các representation khác nhau có thể có thời điểm thay đổi và nội dung khác nhau.

Client nên lưu cache validator cùng cache key của request, tối thiểu gồm URI và các query parameter ảnh hưởng representation. Nếu response dùng `Vary` theo request header, cache key cũng phải tính đến các header tương ứng.

## 7. Độ chính xác thời gian và các giới hạn của Last-Modified

HTTP-date của `Last-Modified` có độ phân giải đến giây. Nếu tài nguyên thay đổi nhiều lần trong cùng một giây, timestamp có thể không phân biệt được hai phiên bản đó.

Một số giới hạn khác:

- Đồng hồ server phải được đồng bộ đủ tốt để timestamp có ý nghĩa.
- Giá trị `@LastModifiedDate` phải được cập nhật mỗi khi dữ liệu liên quan đến representation thay đổi.
- Nếu một thay đổi xảy ra ngoài cơ chế auditing của entity, timestamp có thể không được cập nhật như mong đợi.
- Một representation có thể phụ thuộc vào association hoặc dữ liệu tổng hợp bên ngoài entity; timestamp trên entity gốc chưa chắc phản ánh mọi thay đổi của dữ liệu liên quan.
- Client không nên dùng timestamp cũ cho request khác hoặc query khác.

Vì vậy, `Last-Modified` hữu ích cho cache validation nhưng không phải lúc nào cũng là validator đủ chính xác cho mọi loại representation.

## 8. Phân biệt If-Modified-Since với ETag

Spring Data REST cũng hỗ trợ ETag và các conditional header liên quan. Hai cơ chế có mục tiêu gần nhau nhưng dùng validator khác nhau:

| Cơ chế | Validator | Request header | Mục đích |
|---|---|---|---|
| Last-Modified | Thời điểm sửa gần nhất | `If-Modified-Since` | Kiểm tra tài nguyên có mới hơn một thời điểm không |
| ETag | Mã định danh phiên bản/representation | `If-None-Match` | Kiểm tra representation có khớp validator đã cache không |
| Optimistic locking | ETag hiện tại của entity | `If-Match` | Bảo vệ cập nhật khỏi ghi đè thay đổi của client khác |

ETag thường chính xác hơn khi timestamp chỉ có độ phân giải đến giây hoặc representation có cách tạo phức tạp. `If-Modified-Since` dựa trên thời gian; `If-None-Match` dựa trên validator ETag.

Nếu request GET gửi đồng thời `If-None-Match` và `If-Modified-Since`, quy tắc HTTP ưu tiên `If-None-Match`; server đánh giá ETag và không dùng `If-Modified-Since` để thay thế điều kiện đó.

Ví dụ:

~~~http
GET /people/42
If-None-Match: "7"
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
~~~

Với thao tác ghi như PUT, PATCH hoặc DELETE, dùng `If-Match` để kiểm tra ETag và bảo vệ cập nhật đồng thời. `If-Modified-Since` chủ yếu dành cho conditional GET/HEAD, không thay thế cơ chế optimistic locking.

## 9. Phân biệt conditional request với cache freshness

`If-Modified-Since` là cơ chế **revalidation**: client hỏi server xem bản cache có còn dùng được không. Nó không tự quyết định client được giữ cache trong bao lâu.

Các header như `Cache-Control` và `Expires` quy định freshness lifetime. Khi bản cache còn fresh, cache có thể sử dụng lại mà chưa cần gửi request. Khi bản cache hết freshness, client hoặc intermediary có thể gửi conditional request với `If-Modified-Since` để kiểm tra.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT
~~~

`max-age=60` cho biết response có thể được xem là fresh trong 60 giây theo quy tắc cache. Sau thời gian đó, client có thể revalidate bằng `If-Modified-Since`.

Việc cấu hình cache policy phải phù hợp với độ nhạy thời gian của dữ liệu và yêu cầu bảo mật. Không nên cache dữ liệu riêng tư hoặc dữ liệu thay đổi thường xuyên chỉ vì endpoint có `Last-Modified`.

## 10. Xử lý response 304 ở client

Khi server trả `304 Not Modified`, client không nên coi đây là lỗi. Đây là kết quả thành công của conditional GET, cho biết representation trong cache vẫn có thể sử dụng.

Luồng client:

1. GET resource lần đầu và lưu body cùng header `Last-Modified`.
2. Khi cần đọc lại, gửi GET với `If-Modified-Since` đã lưu.
3. Nếu nhận `200 OK`, thay body và validator trong cache.
4. Nếu nhận `304 Not Modified`, giữ nguyên body cache hiện có.
5. Nếu nhận lỗi khác, xử lý theo chính sách retry hoặc hiển thị lỗi của ứng dụng.

Ví dụ dùng curl:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people/42
~~~

Sau khi nhận `Last-Modified`, gửi request có điều kiện:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  -H "If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT" \
  http://localhost:8080/people/42
~~~

Có thể kiểm tra hai trường hợp bằng cách chạy request thứ hai trước và sau khi sửa entity qua API hoặc một luồng cập nhật được auditing hỗ trợ.

## 11. Kiểm thử If-Modified-Since trong Spring Data REST

Nên kiểm thử qua HTTP integration test để xác nhận cả auditing và conditional response hoạt động trong cấu hình thực tế.

Các trường hợp nên kiểm tra:

1. Tạo entity mới và xác nhận thuộc tính `@LastModifiedDate` được gán.
2. GET item resource và xác nhận response có header `Last-Modified`.
3. Gửi lại GET với chính giá trị `If-Modified-Since` vừa nhận và xác nhận server trả `304 Not Modified` khi entity chưa đổi.
4. Cập nhật entity qua endpoint REST và xác nhận timestamp thay đổi.
5. Gửi lại conditional GET với timestamp cũ và xác nhận server trả representation mới cùng header cập nhật.
6. Kiểm tra entity được cập nhật qua service hoặc luồng khác có được auditing cập nhật hay không.
7. Kiểm tra request dùng sai URI hoặc query parameter khác để bảo đảm client không tái sử dụng nhầm validator.
8. Kiểm tra request có cả `If-None-Match` và `If-Modified-Since` nếu ứng dụng hỗ trợ ETag.
9. Kiểm tra response khi entity không có metadata `@LastModifiedDate`.
10. Kiểm tra múi giờ, độ phân giải giây và thay đổi nhiều lần trong cùng một giây nếu dữ liệu có tần suất cập nhật cao.

Không chỉ xác nhận status code. Hãy kiểm tra body, header và giá trị timestamp được lưu trong entity để chắc chắn validator phản ánh thay đổi dữ liệu thực tế.

## 12. Quy trình triển khai

1. Xác định item resource cần hỗ trợ conditional GET.
2. Thêm thuộc tính thời điểm sửa vào domain entity và đánh dấu bằng `@LastModifiedDate`.
3. Bật auditing cho đúng Spring Data module; với JPA, dùng `@EnableJpaAuditing` và `AuditingEntityListener`.
4. GET resource và xác nhận Spring Data REST trả `Last-Modified`.
5. Lưu header cùng cache key của URI và query parameter tương ứng ở client.
6. Gửi `If-Modified-Since` khi revalidate cùng resource.
7. Xử lý `304 Not Modified` bằng cách dùng lại body cache.
8. Kết hợp ETag nếu cần validator chính xác hơn hoặc cần bảo vệ thao tác ghi bằng `If-Match`.
9. Chạy integration test cho cả trường hợp resource chưa đổi và đã đổi.

## 13. Những điểm cần ghi nhớ

- `Last-Modified` là response header ghi thời điểm sửa gần nhất của resource.
- `If-Modified-Since` là request header dùng để hỏi server xem resource có thay đổi kể từ thời điểm đó không.
- Nếu chưa thay đổi, Spring Data REST có thể trả `304 Not Modified` mà không gửi lại body.
- Dùng `@LastModifiedDate` và bật auditing để Spring Data có thời điểm sửa; với JPA cần cấu hình auditing listener.
- Gửi lại validator cho đúng URI và query parameter đã dùng để lấy representation.
- HTTP-date có độ phân giải đến giây; ETag có thể phù hợp hơn khi cần nhận diện phiên bản chính xác.
- Khi có cả `If-None-Match` và `If-Modified-Since`, điều kiện ETag được ưu tiên theo quy tắc HTTP.
- `If-Modified-Since` dùng để revalidate cache; `Cache-Control` và `Expires` quyết định freshness.
- Dùng `If-Match` với ETag cho conditional update; không dùng `If-Modified-Since` thay optimistic locking.

## Nguồn tham khảo

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [HTTP Semantics — RFC 9110, If-Modified-Since](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-modified-since)
