# Đồng bộ lại dữ liệu khi nhiều máy khách cùng chỉnh sửa

## Mục tiêu

Khi nhiều máy khách cùng đọc và chỉnh sửa một resource Spring Data REST, mỗi máy có thể đang giữ một bản dữ liệu cũ. Nếu server nhận hai lần ghi mà không phát hiện bản cũ, lần ghi sau có thể ghi đè thay đổi của lần ghi trước. Hiện tượng này thường gọi là **lost update**.

Spring Data REST có thể phối hợp ETag với optimistic locking để phát hiện tình huống đó:

- Client đọc resource và lưu ETag hiện tại.
- Khi ghi, client gửi ETag đã đọc trong header `If-Match`.
- Server chỉ chấp nhận ghi nếu resource vẫn ở phiên bản tương ứng.
- Nếu một client khác đã cập nhật trước, server từ chối lần ghi dựa trên bản cũ; client phải tải lại, xử lý xung đột rồi mới gửi thay đổi tiếp theo.

Cơ chế này giúp nhiều client đồng bộ thay đổi mà không cần khóa resource trong suốt thời gian người dùng mở màn hình chỉnh sửa.

## 1. Vấn đề khi nhiều client cùng sửa

Giả sử Person có dữ liệu:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Hanoi"
}
~~~

Client A và Client B cùng GET Person 42. Cả hai đều nhận bản dữ liệu ở thời điểm T1.

- A đổi `city` thành `Da Nang`.
- B đổi `lastName` thành `Tran`.
- A gửi cập nhật và server lưu thành công.
- B vẫn giữ bản cũ; nếu B gửi toàn bộ representation cũ cùng thay đổi của mình, giá trị `city` mới của A có thể bị ghi đè trở lại thành `Hanoi`.

Đây là lost update: thao tác của A đã thành công nhưng thay đổi đó bị mất sau lần ghi của B.

Nếu server không kiểm tra phiên bản, cả hai request có thể đều trả thành công. Client khó nhận ra dữ liệu đã bị ghi đè nếu không đọc lại.

## 2. Optimistic locking và @Version

Optimistic locking giả định xung đột không xảy ra thường xuyên. Client được phép đọc và làm việc trên bản dữ liệu của mình; khi ghi, server kiểm tra xem bản đó còn mới hay không.

Với Spring Data JPA, có thể khai báo trường version trên entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Person {

    @Id
    private Long id;

    private String firstName;
    private String lastName;
    private String city;

    @Version
    private Long version;

    // getters and setters
}
~~~

`@Version` đánh dấu thuộc tính được persistence provider sử dụng để phát hiện cập nhật cạnh tranh.

Khi một entity được lưu:

1. Persistence provider đọc version hiện tại.
2. Khi UPDATE, câu lệnh ghi kiểm tra version cũ trong điều kiện cập nhật.
3. Nếu chưa có transaction khác thay đổi entity, update thành công và version được tăng.
4. Nếu version đã thay đổi, update không khớp bản ghi/version mong đợi và optimistic locking phát hiện xung đột.

Cách thực hiện cụ thể phụ thuộc persistence provider và datastore. Với JPA, trường `@Version` thường do provider quản lý; không để client tự chọn version mới.

### @Version và ETag liên hệ thế nào?

Spring Data REST có thể dùng version của entity để tạo ETag cho representation. ETag là validator mà client nhận trong response header; client không cần biết cách server tạo giá trị đó.

Ví dụ response GET minh họa:

~~~http
GET /api/people/42
Accept: application/hal+json

HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Hanoi"
}
~~~

Giá trị `"7"` chỉ là ví dụ. ETag thực tế là giá trị do server tạo, có thể phụ thuộc phiên bản Spring Data REST và cấu hình. Hãy coi ETag là một chuỗi opaque: lưu nguyên giá trị nhận được, bao gồm dấu ngoặc kép nếu có, và không tự tính hoặc chỉnh sửa nó.

Nếu entity không có version property hoặc server không phát ETag, optimistic concurrency qua ETag có thể chưa được bật cho resource đó. Hãy xác nhận response và cấu hình thực tế của ứng dụng.

## 3. Client phải giữ ETag cùng bản dữ liệu

Khi client GET resource, hãy lưu ETag cùng với representation:

~~~text
resource = Person 42
body     = { firstName, lastName, city, ... }
etag     = "7"
~~~

ETag thuộc về đúng resource representation đã đọc. Không dùng ETag của Person 42 để cập nhật Person 43, và không dùng ETag cũ sau khi client đã tải phiên bản mới.

Client nên lưu đồng thời:

- URI của resource, lấy từ link `self` hoặc URI do server công bố.
- Dữ liệu đã đọc.
- ETag nhận từ response header.
- Các thay đổi người dùng thực hiện so với bản đã đọc, nếu cần hỗ trợ merge.

Đừng lấy trường `version` trong JSON làm ETag bằng cách tự nối chuỗi. Hãy dùng chính header ETag do server trả.

## 4. Gửi If-Match khi ghi

Khi gửi PUT, PATCH hoặc DELETE tới resource có hỗ trợ optimistic locking, client gửi ETag đã nhận trong header `If-Match`.

Ví dụ cập nhật bằng PUT:

~~~http
PUT /api/people/42
Content-Type: application/json
Accept: application/hal+json
If-Match: "7"

{
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Da Nang"
}
~~~

Server so sánh precondition với phiên bản hiện tại:

- Nếu ETag còn khớp, request có thể tiếp tục và lưu thay đổi.
- Nếu resource đã được client khác cập nhật, ETag không còn khớp và request bị từ chối.
- Nếu server yêu cầu conditional write mà client không gửi precondition, response có thể là `428 Precondition Required`; hành vi cụ thể phụ thuộc cấu hình và version.

`If-Match` dùng strong comparison theo HTTP. Với ETag yếu có tiền tố `W/`, không nên kỳ vọng nó đáp ứng precondition `If-Match`. Hãy dùng đúng ETag mà API cung cấp và kiểm tra contract của endpoint.

### Dùng If-Match cho PATCH và DELETE

PATCH:

~~~http
PATCH /api/people/42
Content-Type: application/merge-patch+json
If-Match: "7"

{
  "city": "Da Nang"
}
~~~

DELETE:

~~~http
DELETE /api/people/42
If-Match: "7"
~~~

Các ví dụ trên minh họa conditional request. Media type PATCH và method được hỗ trợ còn phụ thuộc API. Với DELETE, `If-Match` giúp tránh xóa resource dựa trên một bản mà client đã đọc trước khi người khác thay đổi.

`If-Match: *` chỉ kiểm tra resource hiện tồn tại; nó không xác nhận client đang dùng phiên bản cụ thể đã đọc. Nếu mục tiêu là ngăn lost update, hãy dùng ETag cụ thể thay vì wildcard.

## 5. Hai client cùng cập nhật: diễn biến từng bước

Giả sử server trả ETag `"7"` cho Person 42.

<text-placeholder/>

~~~text
             Server: Person 42, ETag "7"
                       |
              +--------+--------+
              |                 |
           Client A          Client B
           GET "7"           GET "7"
              |                 |
         Sửa city           Sửa lastName
              |                 |
     PUT If-Match "7"             |
              |                 |
       Thành công                |
       Server -> "8"             |
              |                 |
              +-----------------+
                                |
                       PUT If-Match "7"
                                |
                         ETag đã cũ
                                |
                     412 Precondition Failed
                                |
                         Client B GET lại
                                |
                     Nhận representation "8"
                                |
                       So sánh và merge
                                |
                     PUT If-Match "8"
                                |
                       Lưu nếu vẫn mới
                                |
                         Server -> "9"
~~~

Trình tự:

1. A và B đều GET cùng một resource và nhận ETag `"7"`.
2. A gửi PUT với `If-Match: "7"`; server chấp nhận, lưu thay đổi và phiên bản mới có ETag `"8"`.
3. B gửi PUT với ETag `"7"`; server thấy precondition đã cũ và từ chối.
4. B nhận `412 Precondition Failed`, tải lại resource và ETag mới.
5. B so sánh dữ liệu mới với thay đổi của mình, merge nếu an toàn hoặc yêu cầu người dùng giải quyết.
6. Nếu merge hợp lệ, B gửi request mới với `If-Match: "8"`. Nếu không có ai cập nhật thêm, server chấp nhận và tạo phiên bản tiếp theo.

Số ETag trong sơ đồ chỉ để giải thích luồng. Client không được giả định version luôn tăng đúng một đơn vị hoặc ETag có dạng số.

## 6. Xử lý 412 Precondition Failed

`412 Precondition Failed` cho biết một điều kiện trong request không còn đúng tại thời điểm server xử lý. Với `If-Match`, nguyên nhân thường gặp là resource đã thay đổi kể từ lần GET của client.

Ví dụ:

~~~http
PUT /api/people/42
If-Match: "7"
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Hanoi"
}

HTTP/1.1 412 Precondition Failed
~~~

Khi nhận 412, client không nên gửi lại nguyên payload cũ ngay lập tức. Quy trình xử lý phù hợp:

1. Giữ lại bản người dùng đã chỉnh sửa và ETag cũ để có thể giải thích xung đột.
2. GET lại URI resource.
3. Lấy representation và ETag mới từ response.
4. So sánh bản ban đầu, bản người dùng sửa và bản mới nhất trên server.
5. Xác định field nào chỉ một bên thay đổi và field nào cả hai bên cùng sửa.
6. Merge các thay đổi không xung đột; với field bị sửa đồng thời, áp dụng quy tắc nghiệp vụ hoặc yêu cầu người dùng chọn.
7. Gửi lại thay đổi đã giải quyết cùng ETag mới.
8. Nếu lại nhận 412, lặp lại quy trình với giới hạn hợp lý hoặc yêu cầu người dùng xử lý thủ công.

Không tự động thay ETag cũ bằng ETag mới rồi gửi lại nguyên payload. Làm vậy có thể ghi đè thay đổi mới nhất của người khác và tái tạo đúng lỗi lost update mà optimistic locking đang ngăn chặn.

## 7. Merge thay đổi như thế nào?

Có thể so sánh ba phiên bản:

- **Base:** representation mà người dùng đã GET ban đầu.
- **Local:** representation sau khi người dùng chỉnh sửa.
- **Remote:** representation mới nhất tải từ server sau xung đột.

Ví dụ:

| Field | Base | Local (B) | Remote (A) | Cách xử lý |
|---|---|---|---|---|
| firstName | An | An | An | Không thay đổi |
| lastName | Nguyen | Tran | Nguyen | Chỉ B đổi; có thể giữ Tran |
| city | Hanoi | Hanoi | Da Nang | Chỉ A đổi; giữ Da Nang |
| phone | 0900 | 0911 | 0922 | Cả hai đổi; cần giải quyết xung đột |

Trong ví dụ, B có thể merge `lastName=Tran` với `city=Da Nang` vì hai client sửa field khác nhau. Nhưng `phone` bị cả hai thay đổi nên không thể tự chọn một giá trị nếu không có quy tắc nghiệp vụ.

Merge theo field chỉ là ví dụ. Nếu các field có quan hệ nghiệp vụ, chẳng hạn `startDate` và `endDate`, hoặc `quantity` và `availableStock`, cần kiểm tra invariant của domain trước khi ghép. Có những thay đổi riêng lẻ không xung đột về field nhưng lại xung đột về nghiệp vụ.

## 8. Phân biệt If-Match với If-None-Match

Cả hai header đều liên quan ETag nhưng mục tiêu khác nhau:

| Header | Mục đích | Kết quả thường gặp |
|---|---|---|
| `If-Match` | Chỉ thực hiện thao tác nếu representation/resource vẫn khớp validator đã biết | Ghi thành công hoặc `412 Precondition Failed` |
| `If-None-Match` | Chỉ lấy representation nếu validator không khớp; thường dùng để revalidate cache với GET | `200 OK` có body mới hoặc `304 Not Modified` |

Ví dụ cache revalidation:

~~~http
GET /api/people/42
If-None-Match: "8"
Accept: application/hal+json
~~~

Nếu representation vẫn tương ứng với ETag đã gửi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "8"
~~~

Client giữ bản cache hiện có. 304 không phải response báo xung đột ghi.

Ví dụ conditional write:

~~~http
PUT /api/people/42
If-Match: "8"
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Da Nang"
}
~~~

Ở đây client yêu cầu server chỉ cập nhật nếu resource vẫn ở phiên bản mà client đã đọc. Nếu không khớp, server trả 412.

Đừng dùng `If-None-Match` thay cho `If-Match` khi bảo vệ thao tác ghi khỏi lost update.

## 9. Client cần cập nhật ETag sau mỗi lần ghi thành công

Sau khi PUT/PATCH thành công, server có thể trả ETag mới trong response header. Client phải lưu validator mới cùng representation mới.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "8"
~~~

Nếu response là 204 và server vẫn trả ETag, client có thể lưu ETag đó dù không có body. Nếu không có representation hoặc validator mới, GET lại resource để đồng bộ trạng thái.

Sau POST tạo mới, client có thể lưu URI từ `Location` và ETag nếu response cung cấp. Khi thao tác tiếp trên resource mới, hãy dùng validator tương ứng với URI đó.

Sau DELETE thành công, bỏ cache của resource đã xóa và loại bỏ ETag cũ khỏi trạng thái client.

## 10. Cấu hình Spring Data REST và lưu ý triển khai

Để optimistic locking hoạt động cho entity JPA, khai báo trường `@Version` và đảm bảo thao tác ghi đi qua persistence provider hỗ trợ version check.

Ví dụ:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String firstName;
    private String lastName;
}
~~~

Với Spring Data REST, kiểm tra các điểm sau:

- GET resource có trả ETag không?
- ETag có thay đổi sau một lần cập nhật thành công không?
- PUT/PATCH/DELETE có kiểm tra `If-Match` không?
- Request thiếu precondition được xử lý thế nào trong version/configuration hiện tại?
- ETag cũ có bị từ chối sau khi client khác cập nhật không?
- Exception do optimistic locking ở tầng persistence được ánh xạ thành status/error nào?
- Có đường ghi khác (custom controller, batch, bulk update hoặc SQL trực tiếp) bỏ qua version check không?

Bulk update JPQL/SQL hoặc thao tác ghi ngoài entity lifecycle có thể không đi qua cùng cơ chế dirty checking/version của JPA. Nếu có nhiều đường ghi, cần đảm bảo tất cả đều duy trì quy tắc concurrency của domain.

Nếu ứng dụng dùng MongoDB hoặc datastore khác, dùng annotation/version mechanism phù hợp với module Spring Data tương ứng. Không sao chép `jakarta.persistence.Version` sang module không dùng JPA.

## 11. CORS khi client chạy trên trình duyệt

Nếu frontend và API khác origin, trình duyệt phải được phép gửi header `If-Match` và đọc header `ETag`.

Cấu hình CORS có thể cần:

- Cho phép request header `If-Match` và các header cần thiết như `Content-Type`.
- Expose response header `ETag` để JavaScript đọc được.
- Cho phép method PUT, PATCH hoặc DELETE nếu API hỗ trợ.
- Xử lý preflight OPTIONS đúng cách.

Ví dụ về ý nghĩa header:

~~~http
Access-Control-Allow-Headers: Content-Type, If-Match
Access-Control-Expose-Headers: ETag, Location
~~~

Đây là các header minh họa; cấu hình thật phải được đặt ở tầng CORS phù hợp với ứng dụng và origin được phép. Nếu server trả ETag nhưng browser JavaScript không đọc được, hãy kiểm tra `Access-Control-Expose-Headers`.

## 12. Kiểm tra bằng curl

Đọc resource và lưu ETag:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Sao chép nguyên giá trị ETag từ response, ví dụ `"7"`, rồi gửi update:

~~~bash
curl -i \
  -X PUT \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  -H 'If-Match: "7"' \
  -d '{"firstName":"An","lastName":"Nguyen","city":"Da Nang"}' \
  https://localhost:8080/api/people/42
~~~

Để kiểm tra xung đột, thực hiện hai GET trước khi ghi:

1. GET lần thứ nhất, lưu ETag.
2. GET lần thứ hai, cũng lưu cùng ETag.
3. PUT từ client A với ETag đó.
4. PUT từ client B với ETag cũ.
5. Xác nhận B bị từ chối bằng precondition failure theo contract của server.
6. GET lại và kiểm tra ETag mới.

Không dùng ETag minh họa nếu server trả giá trị khác. Không bỏ dấu ngoặc kép hoặc tự thay version bằng một số phỏng đoán.

## 13. Integration test cho optimistic concurrency

Một integration test nên xác nhận hai client cùng đọc một version nhưng chỉ một lần ghi dùng version cũ được chấp nhận.

Kịch bản khái quát:

~~~text
GET /api/people/42 -> ETag "7"
GET /api/people/42 -> ETag "7"

PUT If-Match "7" -> success, new ETag "8"
PUT If-Match "7" -> 412 Precondition Failed

GET /api/people/42 -> current data, ETag "8"
~~~

Với MockMvc, có thể kiểm tra response header và status:

~~~java
MvcResult firstRead = mockMvc.perform(
        get("/api/people/42")
            .accept("application/hal+json")
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstRead.getResponse().getHeader("ETag");

mockMvc.perform(
        put("/api/people/42")
            .header("If-Match", etag)
            .contentType("application/json")
            .content("""
                {"firstName":"An","lastName":"Tran"}
                """)
    )
    .andExpect(status().isOk());
~~~

Đây chỉ là phần minh họa lấy ETag và gửi precondition. Để kiểm tra cạnh tranh thực sự, test cần giữ lại ETag cũ, thực hiện lần ghi đầu tiên, rồi gửi request thứ hai với ETag cũ và xác nhận status xung đột đúng với phiên bản/cấu hình Spring Data REST đang chạy.

## 14. Những nhầm lẫn thường gặp

- **ETag là hash nội dung mà client tự tạo.** ETag là validator do server công bố; hãy coi nó là opaque.
- **Có ETag nghĩa là tự động ngăn mọi lost update.** Server phải hỗ trợ và kiểm tra conditional write hoặc version locking.
- **Dùng If-None-Match cho PUT.** Dùng If-Match để yêu cầu phiên bản hiện tại khớp trước khi ghi.
- **Nhận 412 rồi gửi lại payload cũ với ETag mới.** Việc này có thể ghi đè thay đổi của client khác; phải refresh và merge trước.
- **Đổi trường version trong JSON để ép ghi.** Version là metadata concurrency do server/persistence provider quản lý.
- **Mọi xung đột đều là 412.** Conditional header mismatch thường là 412; lỗi optimistic locking ở tầng khác có thể được ánh xạ khác tùy stack.
- **ETag chỉ dành cho cache.** ETag còn có thể bảo vệ cập nhật có điều kiện.
- **Client có thể dùng ETag của resource khác.** Validator phải gắn với đúng URI/representation.
- **Mọi đường ghi đều tự động được bảo vệ.** Bulk SQL, batch hoặc custom write path có thể cần cơ chế version check riêng.

## 15. Ghi nhớ

- Nhiều client có thể cùng giữ một bản dữ liệu cũ; ghi không kiểm tra version có thể gây lost update.
- `@Version` cho phép persistence provider phát hiện cập nhật cạnh tranh.
- Spring Data REST có thể công bố version qua response header ETag.
- Client lưu ETag từ GET và gửi nguyên giá trị trong `If-Match` khi ghi.
- ETag khớp thì thao tác có thể tiếp tục; ETag cũ thường dẫn tới `412 Precondition Failed`.
- Khi nhận 412, GET lại, so sánh Base/Local/Remote, merge hoặc yêu cầu người dùng giải quyết rồi mới retry với ETag mới.
- `If-None-Match` chủ yếu phục vụ cache revalidation; `If-Match` bảo vệ thao tác có điều kiện.
- Cập nhật ETag sau mỗi lần ghi thành công và bảo đảm mọi đường ghi đều tuân thủ concurrency policy.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics: ETag and conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Data REST Reference — Conditional requests and optimistic locking](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data JPA Reference — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Jakarta Persistence — Version attributes](https://jakarta.ee/specifications/persistence/)
