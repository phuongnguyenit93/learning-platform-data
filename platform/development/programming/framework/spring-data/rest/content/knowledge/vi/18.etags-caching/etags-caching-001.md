# ETag và quan hệ với thuộc tính phiên bản @Version

## Mục tiêu

Spring Data REST hỗ trợ các HTTP conditional headers để bảo vệ resource khỏi cập nhật lỗi thời và giảm dữ liệu phải truyền qua mạng. Cơ chế này kết hợp hai nhu cầu:

- Optimistic locking: ngăn một client ghi đè thay đổi mới hơn của client khác.
- HTTP caching/revalidation: cho phép client hỏi resource có thay đổi kể từ lần đọc trước hay chưa.

Với entity có thuộc tính được đánh dấu `@Version`, Spring Data REST sử dụng giá trị phiên bản làm ETag của resource. Client lấy ETag từ response GET rồi gửi lại qua `If-Match` khi PUT, PATCH hoặc DELETE. Nếu phiên bản hiện tại không còn khớp, server từ chối thao tác với `412 Precondition Failed`.

Với GET, client gửi `If-None-Match` cùng ETag đã nhận trước đó. Nếu resource vẫn giữ ETag đó, server có thể trả `304 Not Modified` và bỏ response body.

## 1. ETag là gì?

ETag (Entity Tag) là HTTP response header dùng làm validator cho một representation/resource. Server gửi một giá trị ETag trong response, client lưu lại và dùng giá trị đó trong request sau.

Ví dụ response minh họa:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json
    ETag: "3"

    {
      "id": 1001,
      "name": "An Nguyen",
      "status": "ACTIVE"
    }

Giá trị `"3"` ở đây chỉ là ví dụ. Hãy sử dụng chính xác giá trị server trả về, bao gồm dấu ngoặc kép nếu có. Client nên xem ETag là một opaque token: không tự tăng, giảm, phân tích hoặc tạo lại giá trị.

ETag có hai mục đích thường gặp:

1. So sánh phiên bản resource khi ghi để tránh lost update.
2. Revalidate cache khi đọc để tránh tải lại representation không thay đổi.

ETag không tự bật cache lâu dài. Chính sách cache như `Cache-Control`, thời hạn lưu và nơi được phép cache vẫn là phần cấu hình riêng.

## 2. Liên kết ETag với @Version

Spring Data REST nhận diện thuộc tính phiên bản của entity thông qua metadata của Spring Data. Khi entity có version property, giá trị property đó được dùng làm ETag cho REST resource.

Ví dụ với Spring Data JPA:

    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.Id;
    import jakarta.persistence.Version;

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        @Version
        private Long version;

        private String name;
        private String status;
    }

Với Spring Data JPA, dùng `jakarta.persistence.Version` (hoặc `javax.persistence.Version` trong ứng dụng JPA thế hệ cũ). Với các Spring Data store module khác, dùng annotation `org.springframework.data.annotation.Version` theo hướng dẫn của module đó.

### 2.1. Ý nghĩa của version property

`@Version` đánh dấu property dùng cho optimistic locking. Persistence provider lưu giá trị version trong database và kiểm tra nó khi cập nhật hoặc xóa entity.

Một luồng cập nhật điển hình:

1. Entity được đọc với version hiện tại, ví dụ 3.
2. Client thay đổi entity và gửi yêu cầu lưu.
3. Persistence provider chỉ cập nhật row nếu ID vẫn đúng và version trong database vẫn là 3.
4. Nếu update thành công, version được tăng lên, ví dụ thành 4.
5. Nếu một transaction khác đã cập nhật row trước đó, điều kiện version không còn khớp và thao tác hiện tại thất bại.

SQL minh họa về ý tưởng:

    UPDATE customer
       SET name = ?, version = 4
     WHERE id = 1001
       AND version = 3;

Đây là mô tả khái niệm; câu SQL thực tế do persistence provider tạo và có thể khác theo database.

### 2.2. Các kiểu version

Với JPA, version property phải dùng kiểu dữ liệu được Jakarta Persistence hỗ trợ cho optimistic locking, ví dụ `int`, `Integer`, `long`, `Long`, `short`, `Short` hoặc `Timestamp` theo phiên bản specification và provider.

Một kiểu số như `Long` thường dễ quan sát và phù hợp cho ví dụ:

    @Version
    private Long version;

Không tự gán hoặc tăng version trong business code. Hãy để persistence provider quản lý giá trị này. Gán version thủ công có thể phá vỡ optimistic locking hoặc làm trạng thái entity không đồng bộ với database.

### 2.3. Version và ETag có quan hệ thế nào?

Spring Data REST dùng version property để tạo ETag. Do đó:

- Khi GET item resource, client nhận ETag phản ánh version hiện tại.
- Khi update thành công, version thường tăng và response tiếp theo có ETag mới.
- Client còn giữ ETag cũ sẽ biết representation đã lỗi thời khi gửi conditional write.

ETag là phần giao tiếp ở tầng HTTP. `@Version` là metadata optimistic locking ở tầng persistence. Chúng phối hợp với nhau, nhưng đảm nhiệm các bước khác nhau.

## 3. Đọc ETag từ GET response

Đọc item resource và lấy header ETag:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/customers/1001

Response minh họa:

    HTTP/1.1 200 OK
    ETag: "3"
    Content-Type: application/hal+json

    {
      "id": 1001,
      "name": "An Nguyen",
      "status": "ACTIVE"
    }

Client cần lưu ETag gắn với đúng resource URI vừa đọc. Không dùng ETag của Customer 1001 cho Customer 1002 hoặc cho một collection URL khác.

Nếu representation được đọc qua URI có query parameter hoặc projection khác, hãy giữ ETag cùng đúng request/resource context theo contract của server. Không trộn ETag giữa các resource hoặc các query khác nhau.

## 4. If-Match để bảo vệ PUT, PATCH và DELETE

`If-Match` là request header mang ETag mà client đã đọc trước đó. Server chỉ thực hiện conditional write khi ETag hiện tại của resource khớp với giá trị client gửi.

Ví dụ client đọc Customer 1001 và nhận:

    ETag: "3"

Sau đó client gửi PATCH:

    curl -i -X PATCH       -H 'If-Match: "3"'       -H "Content-Type: application/merge-patch+json"       -H "Accept: application/hal+json"       -d '{"status":"INACTIVE"}'       http://localhost:8080/customers/1001

Nếu ETag hiện tại vẫn là `"3"`, điều kiện có thể được chấp nhận và update được thực hiện. Response thành công có thể cung cấp ETag mới, ví dụ `"4"`.

Cũng có thể dùng `If-Match` với PUT hoặc DELETE:

    curl -i -X PUT       -H 'If-Match: "3"'       -H "Content-Type: application/json"       -d '{"name":"An Nguyen","status":"ACTIVE"}'       http://localhost:8080/customers/1001

    curl -i -X DELETE       -H 'If-Match: "3"'       http://localhost:8080/customers/1001

Ví dụ chỉ minh họa header và luồng request. Body PUT/PATCH phải tuân theo representation, media type và mapping mà ứng dụng thực tế hỗ trợ.

### 4.1. Khi ETag đã cũ

Giả sử hai client cùng đọc Customer khi version là 3:

1. Client A nhận ETag `"3"`.
2. Client B cũng nhận ETag `"3"`.
3. Client A cập nhật thành công; version chuyển thành 4.
4. Client B vẫn giữ ETag `"3"`.
5. Client B gửi PUT/PATCH/DELETE với `If-Match: "3"`.
6. ETag hiện tại không khớp nên Spring Data REST từ chối request với `412 Precondition Failed`.

Response minh họa:

    HTTP/1.1 412 Precondition Failed

Client B không nên tự đổi header thành `"4"` rồi gửi lại cùng body ngay lập tức. B cần GET lại resource, xem thay đổi của A, hợp nhất dữ liệu theo nghiệp vụ rồi gửi request mới với ETag hiện tại.

### 4.2. Vì sao cần gửi If-Match?

Nếu client đọc một representation cũ rồi gửi update mà không mang theo validator, dữ liệu mới hơn có thể bị ghi đè theo semantics của request.

`If-Match` thể hiện rõ ý định: chỉ thực hiện thay đổi nếu resource vẫn ở phiên bản mà client đã quan sát.

Nên áp dụng conditional write cho thao tác mà việc ghi đè thay đổi của người khác gây mất dữ liệu hoặc tạo trạng thái nghiệp vụ sai. Client cần xử lý rõ trường hợp precondition thất bại thay vì tự động lặp lại vô hạn.

## 5. If-None-Match để kiểm tra cache khi GET

`If-None-Match` dùng cho conditional read. Client gửi ETag đã nhận trước đó:

    curl -i       -H 'If-None-Match: "3"'       -H "Accept: application/hal+json"       http://localhost:8080/customers/1001

Nếu ETag hiện tại vẫn khớp, Spring Data REST có thể trả:

    HTTP/1.1 304 Not Modified
    ETag: "3"

Response 304 không gửi lại representation body. Client giữ bản copy đã cache và tiếp tục dùng nó.

Nếu resource đã thay đổi, server trả representation mới cùng ETag mới, ví dụ:

    HTTP/1.1 200 OK
    ETag: "4"
    Content-Type: application/hal+json

    {
      "id": 1001,
      "name": "An Nguyen",
      "status": "INACTIVE"
    }

Luồng này giúp giảm băng thông và thời gian truyền khi client thường xuyên đọc resource nhưng nội dung ít thay đổi.

### 5.1. ETag không đồng nghĩa với Cache-Control

ETag cho biết representation có khớp với validator mà client gửi hay không. `Cache-Control` xác định cách cache được phép lưu và tái sử dụng response.

Ví dụ các directive thường gặp:

- `Cache-Control: no-store`: không lưu response trong cache.
- `Cache-Control: no-cache`: có thể lưu nhưng cần revalidate trước khi tái sử dụng.
- `Cache-Control: private`: chỉ cache riêng của client, không cho shared cache.
- `Cache-Control: max-age=60`: response có thể được xem là fresh trong 60 giây theo quy tắc HTTP cache.

Đừng thêm thời hạn cache dài chỉ vì response có ETag. Dữ liệu nhạy cảm hoặc phụ thuộc quyền truy cập có thể cần chính sách cache chặt chẽ hơn.

## 6. If-Modified-Since và Last-Modified

Spring Data REST còn hỗ trợ conditional request dựa trên thời điểm sửa đổi:

- `Last-Modified` là response header cho biết thời điểm resource được sửa lần cuối.
- `If-Modified-Since` là request header để client hỏi resource có thay đổi kể từ thời điểm đó không.

Với Spring Data auditing, có thể đánh dấu property bằng `@LastModifiedDate` và bật auditing theo cấu hình phù hợp.

Ví dụ:

    @Entity
    public class Customer {

        @Id
        private Long id;

        @Version
        private Long version;

        @LastModifiedDate
        private Instant lastModifiedDate;
    }

Request sau có thể nhận 304 nếu resource chưa thay đổi kể từ thời điểm gửi:

    curl -i       -H 'If-Modified-Since: Wed, 11 Nov 2026 09:00:00 GMT'       http://localhost:8080/customers/1001

ETag và Last-Modified là hai validator khác nhau. ETag thường phù hợp hơn khi cần token phiên bản chính xác; timestamp có độ phân giải và cách cập nhật phụ thuộc hệ thống. Không tự tạo hoặc sửa các giá trị header; hãy dùng giá trị server trả về.

## 7. ETag, optimistic locking và transaction

Cần phân biệt hai tình huống:

### 7.1. ETag không khớp trước khi thực hiện thao tác

Spring Data REST so sánh ETag request với version hiện tại. Nếu điều kiện `If-Match` không thỏa mãn, request bị từ chối bằng `412 Precondition Failed` trước khi update/delete được chấp nhận.

Đây là kiểm tra ở ranh giới HTTP và giúp client nhận biết representation đã cũ.

### 7.2. Dữ liệu đổi sau khi kiểm tra ETag

Có thể xảy ra race giữa lúc Spring Data REST kiểm tra ETag và lúc persistence provider ghi dữ liệu. Một transaction khác có thể thay đổi row trong khoảng thời gian đó.

Optimistic locking ở database/persistence provider tiếp tục kiểm tra version trong câu UPDATE hoặc DELETE. Nếu version không còn khớp, thao tác persistence có thể phát sinh optimistic locking exception và transaction rollback.

Vì vậy, ETag không thay thế `@Version`; `@Version` vẫn bảo vệ persistence khi có cạnh tranh ở thời điểm ghi. Ngược lại, chỉ có `@Version` cũng không cung cấp cho client một token HTTP để biết representation mà client đang sửa đã lỗi thời từ trước khi request bắt đầu.

### 7.3. Xử lý optimistic locking exception

Tùy persistence provider, Spring Data module và exception translation, xung đột có thể xuất hiện dưới dạng `OptimisticLockingFailureException`, `ObjectOptimisticLockingFailureException` hoặc exception persistence tương ứng.

Khi ứng dụng dùng custom service/controller, hãy xử lý lỗi ở transaction boundary phù hợp:

- Để transaction thất bại rollback.
- Không tiếp tục dùng persistence context đã gặp lỗi như thể update thành công.
- Trả lỗi API có mã ổn định để client biết cần đọc lại resource.
- Không tự động ghi lại cùng payload với version mới mà chưa hợp nhất thay đổi.

Với custom exception mapping, phân biệt precondition thất bại ở HTTP (412) với optimistic lock conflict xảy ra trong quá trình ghi. Status cuối cùng phải tuân theo API contract và exception handler của ứng dụng; không giả định mọi module đều ánh xạ hai tình huống giống nhau.

## 8. Cấu hình và những điều kiện cần có

Để dùng ETag theo version trong Spring Data REST:

1. Domain type cần có property phiên bản được đánh dấu đúng annotation cho persistence module.
2. Repository phải được export như REST resource.
3. Spring Data REST phải nhận diện version property qua persistent entity metadata.
4. Client phải đọc và lưu ETag từ response.
5. Client gửi lại đúng ETag trong `If-Match` khi thực hiện conditional write.
6. Client xử lý `412 Precondition Failed` bằng cách đọc lại và hợp nhất thay đổi.

Ví dụ với Spring Data JPA:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        @Version
        private Long version;

        private String name;
    }

Không tự expose version property trong JSON chỉ để client có thể dùng optimistic locking. Client nên sử dụng HTTP ETag header; header này là contract dành cho conditional request.

Nếu resource không có version property, không nên giả định Spring Data REST có thể tạo ETag version-based cho nó. Có thể thiết kế validator riêng ở custom controller hoặc dùng cơ chế conditional request khác phù hợp, nhưng cần cấu hình và kiểm thử rõ ràng.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Response không có ETag như mong đợi | Entity thiếu version property hoặc annotation không đúng module |
| PUT/PATCH/DELETE trả 412 | If-Match đã cũ hoặc không khớp với version hiện tại |
| Client cập nhật đè thay đổi mới | Client không gửi If-Match hoặc không xử lý stale representation |
| GET trả 304 và không có body | ETag trong If-None-Match khớp; dùng bản cache đã lưu |
| GET luôn trả 200 | ETag không được gửi, không khớp, hoặc endpoint/representation không hỗ trợ conditional request như mong đợi |
| Version không tăng | Kiểm tra persistence mapping và thao tác có thực sự thay đổi entity hay không |
| Lỗi optimistic locking xuất hiện khi flush/commit | Một transaction khác đã thay đổi hoặc xóa row |
| Client gửi ETag tự tạo nhưng luôn bị từ chối | ETag phải được sao chép nguyên vẹn từ response |
| Dùng ETag của resource khác | ETag phải gắn với đúng URI/representation |
| Cache trả dữ liệu nhạy cảm hoặc cũ quá lâu | Kiểm tra Cache-Control, authorization và cache scope |

## 10. Quy trình client khuyến nghị

Một client chỉnh sửa Customer có thể triển khai luồng sau:

1. GET `/customers/1001`.
2. Lưu body cùng ETag response.
3. Cho người dùng chỉnh sửa dữ liệu trên bản đã đọc.
4. Gửi PUT hoặc PATCH kèm `If-Match` chứa ETag đã lưu.
5. Nếu thành công, thay body và ETag cache bằng response mới.
6. Nếu nhận 412, GET lại resource và hiển thị xung đột để người dùng hợp nhất.
7. Với lần GET tiếp theo, gửi `If-None-Match` để server trả 304 nếu resource chưa đổi.

Ví dụ luồng shell rút gọn:

    # Read and capture the ETag from response headers.
    curl -i http://localhost:8080/customers/1001

    # Update only if the resource still has the observed version.
    curl -i -X PATCH       -H 'If-Match: "3"'       -H "Content-Type: application/merge-patch+json"       -d '{"status":"INACTIVE"}'       http://localhost:8080/customers/1001

    # Revalidate a cached representation.
    curl -i       -H 'If-None-Match: "4"'       http://localhost:8080/customers/1001

Các ETag `"3"` và `"4"` chỉ là giá trị minh họa. Trong ứng dụng thật, lấy giá trị từ header response tương ứng.

## 11. Kiểm thử ETag và @Version

Một integration test nên kiểm tra cả HTTP header và persistence behavior.

Các trường hợp nên có:

| Trường hợp | Điều cần xác nhận |
|---|---|
| GET resource có @Version | Response có ETag phản ánh version |
| PATCH với ETag hiện tại | Request được thực hiện và version/ETag mới được trả về |
| PUT với ETag cũ | Server trả 412 và dữ liệu mới hơn không bị ghi đè |
| DELETE với ETag cũ | Server từ chối thao tác xóa bằng precondition failure |
| GET với If-None-Match khớp | Server trả 304, không gửi representation body |
| GET với If-None-Match cũ | Server trả representation mới và ETag hiện tại |
| Hai transaction cập nhật đồng thời | Chỉ một cập nhật dựa trên cùng version có thể thành công |
| Không gửi If-Match | Xác nhận behavior đúng với API contract và optimistic locking của persistence layer |
| Resource không có @Version | Xác nhận không phụ thuộc vào ETag version-based |
| Cache-Control được cấu hình | Cache behavior phù hợp dữ liệu và quyền truy cập |

Ví dụ MockMvc minh họa:

    mockMvc.perform(get("/customers/{id}", customerId))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"));

    mockMvc.perform(patch("/customers/{id}", customerId)
            .header("If-Match", currentEtag)
            .contentType("application/merge-patch+json")
            .content("{\"status\":\"INACTIVE\"}"))
        .andExpect(status().isOk());

    mockMvc.perform(get("/customers/{id}", customerId)
            .header("If-None-Match", updatedEtag))
        .andExpect(status().isNotModified());

Các assertion về status và media type cần khớp với cấu hình Spring Data REST thực tế. Test stale ETag riêng bằng cách gửi lại ETag cũ sau một lần update thành công và xác nhận response 412.

## 12. Checklist triển khai

1. Thêm version property vào entity và dùng đúng @Version annotation của persistence module.
2. Để persistence provider quản lý version; không tự tăng version trong business code.
3. GET item resource và lưu ETag nguyên vẹn từ response header.
4. Gửi If-Match khi PUT, PATCH hoặc DELETE cần bảo vệ khỏi stale update.
5. Xử lý 412 bằng cách GET lại, so sánh và hợp nhất thay đổi.
6. Gửi If-None-Match khi revalidate cached GET representation.
7. Xử lý 304 bằng cách dùng representation đã cache.
8. Phân biệt ETag với Last-Modified và Cache-Control.
9. Giữ @Version để persistence layer phát hiện race xảy ra trong lúc ghi.
10. Không trộn ETag giữa resource URI hoặc query khác nhau.
11. Xác định API behavior khi thiếu If-Match và khi optimistic locking exception xuất hiện.
12. Kiểm thử response headers, stale writes, concurrent transactions và cache behavior.

## Tài liệu tham khảo

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [Spring Data Commons — @Version annotation](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/annotation/Version.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-persistence.html)
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)
- [Jakarta Persistence — Version attributes and optimistic locking](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
