# Last-Modified, @LastModifiedDate và điều kiện hỗ trợ auditing trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể giải thích header HTTP `Last-Modified`; cấu hình Spring Data auditing để cập nhật thuộc tính `@LastModifiedDate`; hiểu cách Spring Data REST dùng giá trị đó cho request có điều kiện `If-Modified-Since`; phân biệt cache revalidation với kiểm soát cập nhật đồng thời bằng ETag; và biết những điều kiện khiến header bị thiếu hoặc không phản ánh thay đổi mới nhất.

## 1. Last-Modified là gì?

`Last-Modified` là response header HTTP cho biết thời điểm server ghi nhận resource được sửa đổi lần cuối. Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Tue, 11 Nov 2025 09:30:00 GMT
```

Client có thể lưu timestamp này cùng URI của resource. Khi cần đọc lại, client gửi timestamp đã nhận trong request header `If-Modified-Since`. Server có thể trả:

- `200 OK` cùng representation mới nếu resource đã thay đổi kể từ thời điểm client gửi.
- `304 Not Modified` không có response body nếu resource chưa thay đổi và representation được cache vẫn còn phù hợp.

Cơ chế này gọi là conditional GET hoặc cache revalidation. Client không phải tải lại toàn bộ body khi dữ liệu chưa đổi, giúp giảm băng thông và công việc serialize ở server.

`Last-Modified` là metadata HTTP của response. Nó không tự tạo cột database, không tự bật auditing và cũng không tự đặt thời gian hết hạn cache. Muốn Spring Data REST phát header dựa trên entity, domain model cần có thông tin thời điểm sửa đổi mà Spring Data REST nhận diện được.

## 2. @LastModifiedDate cung cấp thời điểm sửa đổi cho entity

Spring Data Commons cung cấp annotation:

```java
import org.springframework.data.annotation.LastModifiedDate;
```

Đặt annotation trên property biểu diễn thời điểm entity được sửa gần nhất:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Receipt {

    @Id
    @GeneratedValue
    private Long id;

    private String saleItem;

    private BigDecimal amount;

    @LastModifiedDate
    private Instant lastModifiedAt;

    // Constructor, getters và setters
}
```

`@LastModifiedDate` là metadata cho auditing. Khi auditing infrastructure được bật và entity listener chạy, Spring Data ghi thời điểm sửa đổi vào property này khi entity được persist hoặc update.

Các kiểu thời gian được Spring Data auditing hỗ trợ gồm các kiểu ngày giờ Java hiện đại, `long`, `Long`, `java.util.Date` và `Calendar`. Với ứng dụng mới, `Instant` thường là lựa chọn thuận tiện vì biểu diễn một thời điểm tuyệt đối và không mang múi giờ địa phương.

Có thể dùng thêm `@CreatedDate` để lưu thời điểm tạo:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
```

Hai trường có ý nghĩa khác nhau: `createdAt` giữ nguyên thời điểm tạo, còn `lastModifiedAt` được cập nhật khi entity thay đổi. Theo cấu hình mặc định của `@EnableJpaAuditing`, `modifyOnCreate` là `true`, nên thời điểm sửa đổi cũng được thiết lập lúc tạo entity. Có thể thay đổi hành vi này bằng thuộc tính cấu hình nếu nghiệp vụ yêu cầu.

## 3. Điều kiện để auditing hoạt động với Spring Data JPA

Chỉ thêm `@LastModifiedDate` lên field là chưa đủ. Với Spring Data JPA, cần bật auditing và đăng ký `AuditingEntityListener`.

Cấu hình bật auditing:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
```

Đăng ký listener trên entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Receipt {
    // Các property của entity
}
```

Nếu muốn áp dụng listener cho nhiều entity trong persistence unit, có thể khai báo listener mặc định trong `orm.xml` thay vì lặp lại `@EntityListeners` trên từng entity. Với ứng dụng Spring Data JPA, dùng đúng cấu hình store-specific theo phiên bản Spring Data đang chạy.

Các điều kiện cần kiểm tra:

1. Ứng dụng có Spring Data JPA và provider Bean/Auditing cần thiết trên classpath.
2. Có cấu hình `@EnableJpaAuditing` trong Spring application context.
3. `AuditingEntityListener` được đăng ký trên entity hoặc persistence unit.
4. Property được đánh dấu bằng đúng annotation `org.springframework.data.annotation.LastModifiedDate`.
5. Property có kiểu dữ liệu auditing hỗ trợ và được persistence mapping lưu lại.
6. Entity thực sự đi qua lifecycle persist/update mà auditing listener quan sát được.

Nếu dùng Spring Data MongoDB, JDBC, R2DBC hoặc store khác, cần bật auditing bằng cấu hình tương ứng của store đó. `@EnableJpaAuditing` chỉ dành cho JPA; không dùng nó như cấu hình chung cho mọi Spring Data module.

## 4. AuditorAware có bắt buộc không?

Không. Nếu chỉ cần thời điểm tạo và sửa đổi, không cần triển khai `AuditorAware`.

`AuditorAware<T>` chỉ cần khi muốn ghi nhận ai đã tạo hoặc sửa entity bằng `@CreatedBy` và `@LastModifiedBy`. Ví dụ:

```java
@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

Nếu cần các property này, cung cấp bean `AuditorAware` để auditing infrastructure biết principal hiện tại. Ví dụ dùng Spring Security:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
```

Nếu có nhiều bean `AuditorAware`, chỉ định bean cần dùng bằng thuộc tính `auditorAwareRef` của `@EnableJpaAuditing`. Với job nền hoặc message consumer không có HTTP authentication, cần định nghĩa auditor phù hợp, ví dụ tài khoản hệ thống.

Đối với bài toán `Last-Modified`, trọng tâm là `@LastModifiedDate`; không thêm `AuditorAware` nếu ứng dụng không cần lưu tên người sửa.

## 5. Spring Data REST tạo Last-Modified header như thế nào?

Khi Spring Data REST phục vụ một repository item resource có property `@LastModifiedDate` được auditing cập nhật, nó có thể đưa giá trị đó vào response header `Last-Modified`.

Ví dụ entity Receipt có:

```java
@LastModifiedDate
private Instant lastModifiedAt;
```

Request đọc item:

```http
GET /receipts/42 HTTP/1.1
Accept: application/hal+json
```

Response có thể chứa:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Tue, 11 Nov 2025 09:30:00 GMT
```

Giá trị header được định dạng theo HTTP-date và thể hiện thời điểm theo GMT/UTC. Client nên lấy chính xác giá trị header server trả về thay vì tự chuyển đổi timestamp database hoặc tự dựng chuỗi ngày giờ.

Nếu property tồn tại nhưng auditing không chạy, giá trị có thể null hoặc cũ và header có thể không được phát ra hoặc không đại diện cho thay đổi gần nhất. Vì vậy, cần kiểm tra cả giá trị field đã được lưu và header HTTP sau khi gọi endpoint.

## 6. Dùng If-Modified-Since cho conditional GET

Sau lần GET đầu tiên, client lưu URI resource và giá trị `Last-Modified`. Khi đọc lại cùng resource, gửi timestamp đó:

```http
GET /receipts/42 HTTP/1.1
Accept: application/hal+json
If-Modified-Since: Tue, 11 Nov 2025 09:30:00 GMT
```

Nếu resource chưa thay đổi kể từ thời điểm đó, Spring Data REST có thể trả:

```http
HTTP/1.1 304 Not Modified
```

Response `304` không cần gửi lại body. Client tiếp tục dùng representation đã cache. Nếu entity đã thay đổi, server trả `200 OK`, body mới và giá trị `Last-Modified` mới để client lưu lại.

Có thể kiểm tra bằng curl:

```bash
curl -i http://localhost:8080/receipts/42 \
  -H "Accept: application/hal+json"
```

Sau khi lấy giá trị `Last-Modified` từ response, dùng nguyên giá trị đó:

```bash
curl -i http://localhost:8080/receipts/42 \
  -H "Accept: application/hal+json" \
  -H "If-Modified-Since: Tue, 11 Nov 2025 09:30:00 GMT"
```

Kết quả cụ thể phụ thuộc timestamp hiện tại của resource. Ví dụ trên minh họa cách truyền header; không dùng một timestamp cố định trong môi trường thật.

**Giữ đúng URI và query parameters.** Giá trị `Last-Modified` được lấy từ một representation/request cụ thể. Chỉ gửi lại giá trị đó khi yêu cầu đúng cùng URI và cùng query parameters. Không dùng timestamp của `/receipts/42` cho `/receipts/43`, collection `/receipts` hoặc một query khác. Projection, filter hoặc tham số phân trang cũng có thể làm representation khác đi.

## 7. Phân biệt Last-Modified với ETag

Cả `Last-Modified` và `ETag` đều có thể hỗ trợ conditional request, nhưng chúng mang thông tin khác nhau:

| Cơ chế | Giá trị đại diện | Request header thường dùng | Mục đích |
| --- | --- | --- | --- |
| Last-Modified | Thời điểm sửa đổi gần nhất | `If-Modified-Since` | Tránh tải lại representation chưa thay đổi |
| ETag | Mã định danh/version của representation hoặc resource theo cấu hình | `If-None-Match`, `If-Match` | Cache revalidation và ngăn cập nhật dựa trên version cũ |

Spring Data REST có thể tạo ETag từ property được đánh dấu `@Version`. Khi client gửi `If-Match` với ETag đã đọc trước đó trong PUT, PATCH hoặc DELETE, server chỉ thực hiện thao tác nếu version hiện tại vẫn khớp. Nếu một client khác đã cập nhật resource, request dùng ETag cũ bị từ chối với `412 Precondition Failed`.

Ví dụ:

```java
@Version
private Long version;
```

Client gửi:

```http
PATCH /receipts/42
If-Match: "7"
Content-Type: application/json

{"amount": 125.00}
```

Giá trị ETag thực tế phải được sao chép từ response header, kể cả dấu ngoặc kép hoặc cú pháp mà server trả về. Ví dụ `"7"` chỉ minh họa.

Với GET, client cũng có thể dùng `If-None-Match`; nếu ETag không đổi, server trả `304 Not Modified`. Khi cả hai cơ chế có sẵn, ETag thường là lựa chọn tốt hơn để kiểm soát version vì nó không phụ thuộc độ chính xác của timestamp.

## 8. Giới hạn của Last-Modified và những điều kiện cần chú ý

**Độ chính xác của HTTP-date là một giây.** Property `Instant` có thể giữ nano giây, nhưng giá trị `Last-Modified` theo HTTP-date không biểu diễn phần lẻ của giây. Nếu một resource được cập nhật nhiều lần trong cùng một giây, các lần thay đổi có thể có cùng giá trị header. Với resource thay đổi nhanh hoặc cần phát hiện mọi cập nhật, dùng ETag/version thay vì chỉ dựa vào Last-Modified.

**Timestamp phải thay đổi khi representation thay đổi.** Nếu dữ liệu được cập nhật qua đường ghi không kích hoạt auditing, field có thể không đổi. Với JPA, bulk JPQL update hoặc native SQL thường bỏ qua entity lifecycle callbacks; cần tự cập nhật cột audit hoặc dùng cơ chế khác cho đường ghi đó.

**Thay đổi entity liên quan không nhất thiết cập nhật entity cha.** Nếu response của Customer bao gồm dữ liệu Department, sửa Department không tự động làm `lastModifiedAt` của Customer thay đổi. Nếu representation cha phụ thuộc dữ liệu con, hãy xác định rõ cache invalidation và cập nhật version/timestamp ở đúng aggregate hoặc dùng ETag phù hợp.

**Auditing không thay thế cache policy.** `Last-Modified` là validator để kiểm tra resource đã đổi hay chưa. Các header như `Cache-Control` và `Expires` điều khiển thời gian cache có thể dùng response mà chưa cần revalidate. Cấu hình cache freshness riêng theo yêu cầu bảo mật và độ mới dữ liệu.

**Không dùng Last-Modified như cơ chế phân quyền.** Client có thể tự gửi timestamp. Header chỉ phục vụ conditional request; authorization vẫn phải được kiểm tra trên mỗi request. Không để lộ thông tin nhạy cảm chỉ vì resource có Last-Modified.

## 9. Các lỗi thường gặp và cách chẩn đoán

**Response không có Last-Modified**

Kiểm tra property có `@LastModifiedDate` đúng package không; auditing đã bật chưa; JPA listener đã đăng ký chưa; entity có được lưu qua lifecycle mà listener theo dõi không; và field có giá trị sau khi flush/reload không.

**Last-Modified không thay đổi sau khi cập nhật**

Kiểm tra update có thực sự lưu entity qua JPA lifecycle không. Nếu dùng bulk update/native SQL, cập nhật trường audit tường minh. Kiểm tra cả database value và response header.

**Request luôn trả 200 thay vì 304**

Xác nhận request gửi `If-Modified-Since` đúng cú pháp HTTP-date, giá trị được lấy từ response trước đó, URI và query parameters không đổi, và timestamp server chưa mới hơn giá trị client gửi.

**Request trả 304 nhưng client không hiển thị dữ liệu**

Đây là hành vi bình thường nếu client chưa lưu representation trước đó. Client phải giữ body từ lần `200 OK` trước và dùng lại khi nhận `304`. Không có body mới trong response 304.

**Dùng Last-Modified để chống ghi đè dữ liệu nhưng vẫn mất cập nhật**

Dùng ETag với `@Version` và `If-Match` cho optimistic concurrency. Last-Modified/If-Modified-Since trong Spring Data REST chủ yếu hỗ trợ conditional GET và tiết kiệm truyền tải; không thay thế version check cho PUT/PATCH/DELETE.

**Timestamp không nhất quán giữa các môi trường**

Dùng kiểu thời gian có semantics rõ ràng như `Instant`; kiểm tra timezone database, cấu hình `DateTimeProvider` và đồng hồ hệ thống. Trong test, có thể cung cấp DateTimeProvider cố định để kết quả xác định.

## 10. Quy trình kiểm tra từ database đến HTTP response

1. Thêm property `@LastModifiedDate` vào entity và bảo đảm property được persistence mapping lưu.
2. Bật auditing bằng cấu hình store phù hợp; với JPA, dùng `@EnableJpaAuditing` và `AuditingEntityListener`.
3. Tạo entity qua repository và xác nhận `lastModifiedAt` được gán.
4. Cập nhật entity qua repository, flush transaction và xác nhận timestamp được cập nhật.
5. Gọi item resource bằng GET; kiểm tra response có `Last-Modified`.
6. Gửi lại GET cùng URI và query parameters với `If-Modified-Since` vừa nhận; xác nhận response `304` khi resource chưa đổi.
7. Thực hiện thay đổi mới; GET lại với timestamp cũ và xác nhận server trả representation mới cùng `Last-Modified` mới.
8. Nếu cần bảo vệ thao tác ghi khỏi stale client, thêm `@Version` và kiểm tra ETag/`If-Match` riêng.

Trong integration test, không chỉ kiểm tra annotation có mặt. Hãy xác minh auditing listener thực sự cập nhật field, giá trị được lưu và Spring Data REST phát đúng HTTP header.

## Tóm tắt

- `@LastModifiedDate` đánh dấu property lưu thời điểm entity được sửa gần nhất; annotation thuộc Spring Data Commons.
- Với JPA, cần bật `@EnableJpaAuditing` và đăng ký `AuditingEntityListener` trên entity hoặc persistence unit.
- Không cần `AuditorAware` nếu chỉ ghi ngày tạo/sửa; cần nó khi dùng `@CreatedBy` hoặc `@LastModifiedBy`.
- Spring Data REST có thể phát `Last-Modified` từ property được auditing cập nhật.
- Client gửi `If-Modified-Since` cho đúng cùng URI và query parameters; nếu không đổi, server có thể trả `304 Not Modified`.
- Last-Modified có độ chính xác HTTP-date đến giây và không thay thế ETag cho optimistic concurrency.
- Bulk update, thay đổi entity liên quan và đường ghi bỏ qua lifecycle có thể làm timestamp không phản ánh mọi thay đổi.
- Cache freshness, authorization và version-based write protection cần được cấu hình riêng.

## Tài liệu tham khảo

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [Spring Data JPA — AuditingEntityListener API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/domain/support/AuditingEntityListener.html)
- [Spring Data JPA — EnableJpaAuditing API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/config/EnableJpaAuditing.html)
