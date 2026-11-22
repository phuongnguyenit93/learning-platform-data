# Lưu ETag và xử lý xung đột chỉnh sửa trên giao diện

## 1. Vì sao frontend cần lưu ETag?

Một người dùng mở hồ sơ và bắt đầu chỉnh sửa. Trong lúc form vẫn mở, một người khác có thể cập nhật cùng resource. Nếu frontend gửi bản dữ liệu cũ lên bằng PUT hoặc PATCH mà không kiểm tra phiên bản, thay đổi mới của người kia có thể bị ghi đè.

Đây là tình huống lost update:

1. User A GET resource và nhận dữ liệu phiên bản 7.
2. User B cũng GET phiên bản 7.
3. User A cập nhật thành công, server lưu phiên bản 8.
4. User B vẫn giữ form dựa trên phiên bản 7.
5. Nếu server chấp nhận ghi của B mà không kiểm tra phiên bản, dữ liệu A vừa sửa có thể bị ghi đè.

HTTP ETag kết hợp với request header If-Match giúp phát hiện tình huống này. Frontend lưu ETag nhận từ GET và gửi lại nguyên văn khi cập nhật. Server chỉ chấp nhận thao tác nếu resource vẫn khớp validator đó.

Trong Spring Data REST, ETag có thể được tạo từ version property của entity. Với Spring Data JPA, thường dùng annotation @Version.

## 2. ETag là validator của resource

ETag là giá trị do server cấp để nhận diện một phiên bản representation. Ví dụ response GET:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "id": 42,
  "name": "Alice",
  "department": "Sales"
}
~~~~

Frontend cần lưu nguyên văn giá trị header ETag, bao gồm dấu ngoặc kép nếu có. ETag là opaque validator; client không tự tăng số, bỏ dấu ngoặc kép hoặc suy ra phiên bản tiếp theo.

Ví dụ lưu:

~~~~javascript
const etag = response.headers.get("ETag");
~~~~

Không dùng timestamp ở giao diện hoặc trường version tự tăng do client tự quản lý để thay thế ETag do server phát ra.

ETag thường có dạng strong hoặc weak:

- Strong ETag: "7".
- Weak ETag: W/"7".

If-Match sử dụng strong comparison theo HTTP Semantics. Với cập nhật có điều kiện, server nên cung cấp validator mạnh phù hợp. Client không tự chuyển weak ETag thành strong ETag.

## 3. Bật version metadata trong Spring Data

Spring Data REST có thể phát ETag từ version property của domain object.

Ví dụ entity JPA:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @jakarta.persistence.Version
    private Long version;

    private String name;

    private String department;
}
~~~~

Khi entity được cập nhật thành công, persistence provider quản lý version. Lần GET tiếp theo sẽ nhận ETag mới nếu version đã thay đổi.

Với Spring Data module không dùng JPA, annotation version có thể là org.springframework.data.annotation.Version:

~~~~public class Person {

    @Id
    private String id;

    @org.springframework.data.annotation.Version
    private Long version;

    private String name;
}
~~~~

Hãy dùng annotation tương ứng với store đang triển khai. Không giả định mọi repository đều tạo ETag chỉ vì entity có một field tên version. Kiểm tra response GET thực tế để xác nhận header ETag xuất hiện.

@Version cũng hỗ trợ optimistic locking ở persistence layer. ETag/If-Match đưa kiểm soát phiên bản đó thành một precondition rõ ràng trong HTTP API.

## 4. Luồng GET, lưu ETag và gửi cập nhật

Một workflow frontend cơ bản:

1. Gửi GET tới item resource.
2. Đọc response body và header ETag.
3. Lưu body làm bản dữ liệu ban đầu của form.
4. Lưu ETag cùng resource URI.
5. Người dùng chỉnh sửa form.
6. Gửi PUT hoặc PATCH cùng header If-Match chứa ETag đã lưu.
7. Nếu thành công, cập nhật body và ETag theo response mới.
8. Nếu nhận 412, giữ bản nháp của người dùng và bắt đầu quy trình xử lý conflict.

Ví dụ GET:

~~~~http
GET /people/42 HTTP/1.1
Accept: application/hal+json
~~~~

Response:

~~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/hal+json
~~~~

Frontend lưu ETag "7". Khi người dùng sửa name, gửi PATCH:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json
If-Match: "7"

{
  "name": "Alice Nguyen"
}
~~~~

Nếu resource vẫn ở phiên bản 7, server áp dụng patch. Nếu resource đã thay đổi và ETag hiện tại không còn khớp, server từ chối precondition và trả 412 Precondition Failed.

## 5. If-Match ngăn ghi đè phiên bản cũ

If-Match yêu cầu server chỉ thực hiện method nếu validator của resource khớp một trong các ETag được gửi.

Ví dụ:

~~~~http
If-Match: "7"
~~~~

Nếu current ETag là "7", precondition đạt. Nếu current ETag đã thành "8", precondition không đạt và server không được áp dụng thay đổi theo request đó.

Một request có thể gửi nhiều ETag:

~~~~http
If-Match: "6", "7"
~~~~

Server kiểm tra current entity tag có strong-match với một giá trị trong danh sách không.

Wildcard:

~~~~http
If-Match: *
~~~~

Wildcard chỉ yêu cầu resource hiện tồn tại. Nó không chứng minh client đang chỉnh sửa bản mới nhất và không ngăn lost update giữa hai người cùng đọc một phiên bản. Nếu mục tiêu là optimistic concurrency, hãy gửi ETag cụ thể đã nhận từ GET.

Không tự tạo If-Match từ số version client đoán. Luôn dùng validator do server cấp.

## 6. PUT và PATCH đều có thể dùng If-Match

If-Match là HTTP precondition, có thể được dùng với các method thay đổi resource như PUT, PATCH và DELETE.

- PUT thường gửi representation thay thế theo contract của endpoint.
- PATCH gửi document mô tả thay đổi một phần.
- If-Match bảo đảm thao tác chỉ được áp dụng nếu resource vẫn ở phiên bản client đã đọc.

Ví dụ PUT:

~~~~http
PUT /people/42 HTTP/1.1
Content-Type: application/json
If-Match: "7"

{
  "name": "Alice Nguyen",
  "department": "Engineering"
}
~~~~

Ví dụ PATCH:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "7"

{
  "department": "Engineering"
}
~~~~

Nếu client chỉ sửa một field, PATCH thường giúp giảm nguy cơ gửi lại các field cũ không liên quan. Tuy vậy, PATCH vẫn cần If-Match để tránh cập nhật trên phiên bản đã lỗi thời.

## 7. Phân biệt 412 Precondition Failed và 409 Conflict

Hai status này thường bị nhầm khi xử lý xung đột:

| Status | Ý nghĩa | Ví dụ |
|---|---|---|
| 412 Precondition Failed | HTTP precondition của request không thỏa | ETag gửi trong If-Match đã cũ |
| 409 Conflict | Request xung đột với trạng thái hoặc quy tắc nghiệp vụ hiện tại | Đơn hàng đã giao nên không thể hủy |

Ví dụ 412:

- Frontend đọc ETag "7".
- Người khác cập nhật resource, ETag thành "8".
- Frontend gửi PATCH với If-Match "7".
- Server trả 412 và không áp dụng patch.

Ví dụ 409:

- Frontend đọc resource ở trạng thái DRAFT.
- Quy tắc nghiệp vụ hiện tại không cho phép chuyển đơn hàng đã giao về DRAFT.
- Request có thể có ETag hợp lệ nhưng thao tác vẫn trái quy tắc nghiệp vụ.
- Server trả 409 Conflict theo contract ứng dụng.

Nếu API yêu cầu mọi update phải có If-Match nhưng client bỏ header, có thể dùng 428 Precondition Required theo RFC 6585. Việc bắt buộc header cần được cấu hình hoặc kiểm tra ở server; chỉ thêm @Version không đồng nghĩa mọi endpoint tự động yêu cầu client gửi If-Match.

## 8. Frontend cần giữ cả bản gốc và bản nháp

Khi mở form, frontend nên giữ ba giá trị:

- **Original snapshot:** body ban đầu đã GET.
- **Draft:** dữ liệu người dùng đang chỉnh sửa.
- **ETag:** validator đi cùng original snapshot.

Ví dụ state:

~~~~javascript
const [original, setOriginal] = useState(null);
const [draft, setDraft] = useState(null);
const [etag, setEtag] = useState(null);
const [saving, setSaving] = useState(false);
const [conflict, setConflict] = useState(false);
~~~~

Khi GET thành công:

~~~~javascript
async function loadPerson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/hal+json"
    }
  });

  if (!response.ok) {
    throw new Error("Could not load person");
  }

  const body = await response.json();
  const versionTag = response.headers.get("ETag");

  setOriginal(body);
  setDraft(body);
  setEtag(versionTag);
}
~~~~

Không chỉ lưu ETag ở một biến global dùng chung cho mọi resource. ETag phải gắn với đúng URI và representation mà nó xác nhận. Khi đổi sang resource khác, thay cả body, draft và ETag.

## 9. Gửi PATCH kèm If-Match từ JavaScript

Ví dụ:

~~~~javascript
async function savePerson(url, patch, etag) {
  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/merge-patch+json",
      "Accept": "application/hal+json",
      "If-Match": etag
    },
    body: JSON.stringify(patch)
  });

  if (response.status === 412) {
    return { kind: "conflict" };
  }

  if (!response.ok) {
    return {
      kind: "error",
      status: response.status
    };
  }

  const nextEtag = response.headers.get("ETag");

  if (response.status === 204) {
    return {
      kind: "saved",
      etag: nextEtag
    };
  }

  const body = await response.json();

  return {
    kind: "saved",
    body,
    etag: nextEtag
  };
}
~~~~

Đây là ví dụ minh họa. Response update của Spring Data REST có thể trả representation hoặc 204 No Content tùy Accept và cấu hình return body. Nếu response thành công không có ETag mới, frontend có thể GET lại resource để lấy body và ETag mới trước khi cho phép lần sửa tiếp theo.

Không tái sử dụng ETag cũ sau khi update thành công. Một lần save có thể làm version tăng và validator thay đổi.

## 10. Giao diện nên xử lý 412 như thế nào?

Khi nhận 412, không xóa bản nháp của người dùng và cũng không tự gửi lại cùng patch với ETag mới ngay lập tức.

Một luồng xử lý phù hợp:

1. Giữ nguyên draft đang chỉnh sửa.
2. Hiển thị thông báo resource đã được người khác thay đổi.
3. GET resource mới nhất và lưu body cùng ETag mới.
4. So sánh original snapshot, draft và bản mới nhất.
5. Tự động merge những field độc lập nếu quy tắc nghiệp vụ cho phép.
6. Nếu cùng một field bị cả hai phía thay đổi, yêu cầu người dùng chọn giá trị cuối.
7. Sau khi conflict được giải quyết, gửi patch mới với ETag mới.

Ví dụ thông báo:

~~~~text
This record changed while you were editing it.
Your draft has been kept. Review the latest version
before saving your changes again.
~~~~

Giao diện có thể cung cấp các lựa chọn:

- Tải bản mới nhất và bỏ draft.
- Xem khác biệt giữa bản ban đầu, draft và bản mới.
- Áp dụng thay đổi của mình lên bản mới nhất.
- Giữ một số field của server và một số field từ draft.

Không nên có nút “Overwrite anyway” nếu API không định nghĩa rõ cơ chế ghi đè có chủ đích. Nếu có chức năng này, nó cần được phân quyền và thể hiện rõ cho người dùng.

## 11. So sánh ba phiên bản để merge

Giả sử original snapshot:

~~~~json
{
  "name": "Alice",
  "department": "Sales",
  "phone": "111"
}
~~~~

Draft của user A:

~~~~json
{
  "name": "Alice Nguyen",
  "department": "Sales",
  "phone": "111"
}
~~~~

Bản mới nhất từ server sau khi user B cập nhật:

~~~~json
{
  "name": "Alice",
  "department": "Engineering",
  "phone": "111"
}
~~~~

Hai người sửa field khác nhau:

- User A sửa name.
- User B sửa department.

Ứng dụng có thể merge thành:

~~~~json
{
  "name": "Alice Nguyen",
  "department": "Engineering",
  "phone": "111"
}
~~~~

Sau đó gửi PATCH với ETag mới lấy từ bản server mới nhất.

Nếu cả hai cùng sửa name, ứng dụng không nên tự chọn giá trị cuối mà không có quy tắc nghiệp vụ. Có thể hiển thị bản cũ, bản của người dùng hiện tại và bản mới nhất để người dùng quyết định.

Đối với field phức tạp như collection, association, trạng thái workflow hoặc số tiền, merge tự động cần quy tắc domain rõ ràng. So sánh JSON theo field đơn giản không đủ để đảm bảo tính đúng đắn nghiệp vụ.

## 12. Không retry mù sau 412

Một lỗi phổ biến là nhận 412 rồi tự GET ETag mới và gửi lại nguyên body cũ. Cách này chỉ thay header nhưng vẫn ghi đè dữ liệu người khác vừa cập nhật.

Ví dụ:

1. Client A đọc name = Alice, ETag "7".
2. Client B đổi name thành Alicia, ETag thành "8".
3. Client A gửi name = Alice Nguyen với ETag "7" và nhận 412.
4. Nếu client A GET ETag "8" rồi gửi lại nguyên body Alice Nguyen, thay đổi của B bị ghi đè.

Cách đúng là lấy bản mới nhất, so sánh và merge có chủ đích trước khi gửi request mới.

Retry tự động chỉ phù hợp khi thao tác idempotent và ứng dụng có quy tắc merge an toàn đã được xác định. Nếu không, giữ draft và yêu cầu người dùng giải quyết conflict.

## 13. Lưu ETag cùng cache entry

Nếu frontend cache resource, lưu ETag cùng body và cache key:

~~~~javascript
const cacheEntry = {
  uri: "/people/42",
  body: person,
  etag: response.headers.get("ETag"),
  fetchedAt: Date.now()
};
~~~~

Khi mở lại form:

- Dùng body cache để hiển thị nhanh nếu phù hợp.
- Revalidate bằng If-None-Match khi cần kiểm tra dữ liệu mới.
- Nếu nhận 304, body cache vẫn được dùng.
- Nếu nhận 200, thay body và ETag.
- Nếu người dùng đang chỉnh sửa, không âm thầm thay draft bằng body mới; chuyển sang luồng conflict hoặc thông báo dữ liệu đã thay đổi.

Không dùng ETag của collection để cập nhật item. ETag phải gắn với đúng resource URI và representation. Nếu response có nhiều media type hoặc query variant, cache key cần phản ánh các biến thể đó.

## 14. CORS khi frontend và Spring Data REST khác origin

Nếu frontend chạy ở origin khác API, browser cần được phép gửi If-Match và đọc ETag.

Cấu hình CORS cần:

- Cho phép request header If-Match.
- Expose response header ETag để JavaScript đọc được.
- Cho phép method PUT/PATCH tương ứng.
- Cho phép origin frontend cụ thể.
- Xử lý preflight OPTIONS trước authentication khi Spring Security được dùng.

Ví dụ cấu hình CORS toàn cục của Spring Data REST:

~~~~java
@Override
public void configureRepositoryRestConfiguration(
        RepositoryRestConfiguration config,
        CorsRegistry cors) {

    cors.addMapping("/people/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "PUT", "PATCH")
        .allowedHeaders(
            "Content-Type",
            "If-Match",
            "If-None-Match",
            "Authorization"
        )
        .exposedHeaders("ETag", "Location", "Link");
}
~~~~

Nếu có Spring Security, cần đồng bộ policy trong CorsConfigurationSource và bật http.cors() để preflight được xử lý trước authentication. CORS không thay authentication hoặc authorization.

Nếu JavaScript không đọc được ETag dù response có header, kiểm tra exposedHeaders. Nếu preflight thất bại, kiểm tra allowedHeaders có If-Match hay không.

## 15. Kiểm thử optimistic concurrency với MockMvc

Nên có integration test xác nhận hai client cùng đọc một ETag nhưng chỉ một client cập nhật được.

Ví dụ:

~~~~java
MvcResult firstGet = mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.APPLICATION_HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstGet.getResponse()
        .getHeader(HttpHeaders.ETAG);

assertThat(etag).isNotNull();

mockMvc.perform(
        patch("/people/{id}", 42L)
            .contentType("application/merge-patch+json")
            .header(HttpHeaders.IF_MATCH, etag)
            .content("""
                {
                  "name": "Alice Nguyen"
                }
                """)
    )
    .andExpect(status().is2xxSuccessful());

mockMvc.perform(
        patch("/people/{id}", 42L)
            .contentType("application/merge-patch+json")
            .header(HttpHeaders.IF_MATCH, etag)
            .content("""
                {
                  "department": "Engineering"
                }
                """)
    )
    .andExpect(status().isPreconditionFailed());
~~~~

Test này minh họa hai lần update dùng cùng validator. Sau lần đầu, version thay đổi nên lần thứ hai với ETag cũ bị từ chối.

Bổ sung kiểm tra:

1. GET trả ETag.
2. If-Match đúng cho phép update.
3. Update thành công tạo ETag mới.
4. If-Match cũ trả 412.
5. Resource không bị thay đổi bởi request 412.
6. Wildcard chỉ kiểm tra resource tồn tại, không được dùng để giả lập version check.
7. Thiếu If-Match được xử lý theo policy API.
8. Frontend giữ draft khi nhận conflict.
9. Merge disjoint fields tạo request mới với ETag mới.
10. CORS cho phép If-Match và expose ETag nếu cross-origin.

Status code chính xác của response update thành công phụ thuộc cấu hình trả body của Spring Data REST. Test nên chấp nhận status theo contract ứng dụng thay vì giả định mọi update đều trả 200.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| PATCH luôn thành công dù dữ liệu đã cũ | Không gửi If-Match hoặc server không kiểm tra precondition | Gửi ETag đã lưu và kiểm tra server support |
| Nhận 412 liên tục | Frontend giữ ETag cũ sau update hoặc cache sai URI | Cập nhật ETag sau save và gắn với resource đúng |
| JavaScript không đọc được ETag | CORS chưa expose ETag | Thêm ETag vào exposedHeaders |
| Preflight bị từ chối | If-Match chưa được cho phép trong allowedHeaders | Cập nhật CORS policy |
| Retry sau 412 ghi đè thay đổi mới | Tự lấy ETag mới rồi gửi lại draft cũ | Fetch latest, compare và merge trước khi retry |
| UI mất nội dung người dùng đang nhập | Reset form khi nhận 412 | Giữ draft và hiển thị conflict state |
| Một field bị ghi đè khi merge | Cả hai phía cùng sửa field nhưng app tự chọn một giá trị | Hiển thị diff và yêu cầu lựa chọn |
| Dùng ETag collection để update item | Cache key không phân biệt collection và item | Lưu ETag theo URI/representation |
| Không có ETag trong response | Entity/store chưa có version metadata hoặc endpoint không phát validator | Kiểm tra @Version và response thực tế |
| Dùng If-Match: * để chống lost update | Wildcard chỉ yêu cầu resource tồn tại | Gửi ETag cụ thể từ GET |
| Nhầm 409 với 412 | Không phân biệt business conflict và HTTP precondition | Dùng 412 cho If-Match không khớp; 409 cho xung đột nghiệp vụ |
| Update thành công nhưng frontend tiếp tục dùng ETag cũ | Không nhận hoặc không refresh validator mới | Đọc ETag response hoặc GET lại resource |

## 17. Kết luận

Frontend nên lưu ETag cùng body và URI của resource khi GET. Khi gửi PUT hoặc PATCH, gửi lại ETag trong If-Match để server phát hiện dữ liệu đã thay đổi kể từ lần đọc. Spring Data REST có thể tạo ETag từ version property; với JPA, dùng @Version. Nếu precondition không thỏa, server trả 412 và không áp dụng update.

Khi nhận 412, giao diện phải giữ draft, tải bản mới nhất, so sánh với snapshot ban đầu và chỉ gửi lại sau khi merge hoặc người dùng giải quyết conflict. Không tự thay ETag cũ bằng ETag mới rồi retry nguyên body vì có thể ghi đè thay đổi của người khác. Phân biệt 412 cho precondition thất bại với 409 cho xung đột nghiệp vụ. Nếu frontend cross-origin, CORS phải cho phép If-Match và expose ETag. Hãy kiểm thử hai client cùng dùng một ETag để xác nhận chỉ lần cập nhật đầu tiên thành công.

## Tài liệu tham khảo

- [Spring Data REST — Conditional Operations with ETag and If-Match](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1)
- [RFC 6585 — 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)
- [Spring Data JPA — Locking and @Version](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
