# Ngăn truy vấn không giới hạn và rò rỉ dữ liệu qua bộ lọc

## 1. Mục tiêu học tập

Trong module **INTEGRATION_API_REST**, người học thiết kế API dựa trên tài nguyên, URI, phương thức HTTP và hợp đồng dữ liệu rõ ràng, sau đó thực hành phân trang, cache, xác thực, phân quyền, OpenAPI, xử lý lỗi và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Bài này thuộc chương **Truy vấn tập hợp** và giải quyết hai rủi ro đi đôi với nhau:

1. **Truy vấn không giới hạn (unbounded query):** client có thể yêu cầu quá nhiều bản ghi, quét một vùng dữ liệu lớn hoặc tạo phép lọc tốn kém, khiến API chậm, hết bộ nhớ, gây quá tải CSDL và ảnh hưởng người dùng khác.
2. **Rò rỉ dữ liệu qua bộ lọc (filter-based data leakage):** dù endpoint trả danh sách, client có thể thay điều kiện lọc, sắp xếp, tổng số lượng, facet hoặc tham số phân trang để đọc hoặc **suy ra** thông tin không thuộc quyền truy cập.

Hai rủi ro liên quan: truy vấn quá rộng có thể phát lộ một lượng lớn dữ liệu; ngược lại, một bộ lọc có vẻ vô hại có thể tiết lộ sự tồn tại của tài nguyên bị hạn chế ngay cả khi response chỉ chứa một con số.

Sau bài học, bạn có thể:

- Thiết kế endpoint danh sách có giới hạn mặc định, giới hạn tối đa và chiến lược phân trang phù hợp.
- Phân biệt các bộ lọc do client đề xuất với **điều kiện phạm vi được máy chủ bắt buộc áp dụng**.
- Chống lỗi ghép điều kiện AND/OR, SQL injection, truy vấn biểu thức tùy ý và bộ lọc tốn kém.
- Tránh rò rỉ qua dữ liệu trong danh sách, total count, facet, sort, thông báo lỗi, cursor, cache và export.
- Viết truy vấn có điều kiện tenant/owner/permission được thực thi ở tầng dữ liệu, cùng ví dụ Spring Boot.
- Công bố hợp đồng trong OpenAPI và thiết kế ma trận kiểm thử đúng trạng thái, phân quyền và hiệu năng.

**Tình huống xuyên suốt:** SaaS quản lý tài liệu có nhiều tổ chức. Nhân viên chỉ được xem tài liệu mình sở hữu hoặc được chia sẻ trong tổ chức; quản trị viên có quyền xem thêm một số tài liệu. API cung cấp GET **/api/v1/documents** với filter theo trạng thái, ngày tạo và người sở hữu. Thiết kế phải bảo đảm một tenant không thể nhìn thấy dữ liệu tenant khác, kể cả thông qua tổng số hoặc filter.

## 2. Vì sao endpoint GET danh sách cần mô hình đe dọa riêng?

Một API đọc tài liệu đơn có thể kiểm tra quyền trên ID:

~~~http
GET /api/v1/documents/3f42 HTTP/1.1
Authorization: Bearer <token>
~~~

Endpoint danh sách phức tạp hơn:

~~~http
GET /api/v1/documents?status=APPROVED&ownerId=u-17&sort=createdAt:desc&page=0&size=25 HTTP/1.1
Authorization: Bearer <token>
~~~

Server phải kiểm tra **tập kết quả** chứ không chỉ một ID:

- Người gọi thuộc tenant nào và được xem những loại tài liệu nào?
- Giá trị ownerId do client gửi có nằm trong phạm vi được phép không?
- Có tài liệu bị xóa mềm hoặc đang ở trạng thái riêng tư cần ẩn không?
- Số bản ghi có thể lớn đến đâu?
- Filter có thể tạo join, quét bảng, tìm chuỗi, regex hoặc phép tổng hợp tốn kém không?
- Các trường trong response có chứa dữ liệu chỉ quản trị viên được xem?
- Thông tin **total**, **facet**, **nextCursor** và thời gian phản hồi có thể tiết lộ điều không được phép xem không?

Một đường truy vấn có thể đúng về mặt cú pháp và chỉ trả HTTP 200 nhưng vẫn có **lỗi phân quyền cấp tập hợp**. Vì vậy, xác thực người gọi và hạn chế request size chỉ là lớp đầu; **lọc theo quyền phải gắn với truy vấn dữ liệu**.

## 3. Phân biệt bộ lọc nghiệp vụ với điều kiện bảo mật

Giả sử mỗi tài liệu có:

| Trường | Ý nghĩa |
| --- | --- |
| id | ID tài liệu |
| tenant_id | Tổ chức sở hữu dữ liệu |
| owner_id | Người tạo hoặc người sở hữu |
| visibility | PRIVATE hoặc TENANT |
| status | DRAFT, APPROVED, ARCHIVED |
| created_at | Thời điểm tạo |
| deleted_at | Mốc xóa mềm, có thể null |
| classification | Mức phân loại nhạy cảm |

Client có thể đề xuất lọc theo **status**, **createdFrom**, hoặc **ownerId** trong hợp đồng. Nhưng các điều kiện sau phải do server xác định từ phiên xác thực và chính sách:

- **tenant_id = tenant thực được phép truy cập**;
- **deleted_at IS NULL** đối với danh sách thông thường;
- tài liệu thuộc quyền đọc của principal, ví dụ **owner_id = user hiện tại OR visibility = TENANT** với các quy tắc bổ sung theo vai trò.

Một cấu trúc logic dễ đánh giá:

~~~text
ALLOWED_SCOPE(principal, resource)
    AND RESOURCE_LIFECYCLE_RULES(resource)
    AND CLIENT_FILTERS(resource)
~~~

Trong đó client chỉ được làm **hẹp** kết quả đã được phép, không được mở rộng phạm vi quyền.

**Ví dụ nguy hiểm:**

~~~sql
SELECT *
FROM documents
WHERE tenant_id = :tenant_id
  AND owner_id = :user_id
  OR status = :status;
~~~

Do **AND** có độ ưu tiên cao hơn **OR** trong SQL, nhánh **OR status = :status** có thể đưa bản ghi thuộc tenant khác vào tập kết quả. Nếu truyền status=APPROVED, người gọi có thể xem mọi tài liệu APPROVED mà truy vấn nhìn thấy, không chỉ tài liệu của mình.

**Ví dụ đúng theo chính sách minh họa:**

~~~sql
SELECT id, title, status, created_at
FROM documents
WHERE tenant_id = :trusted_tenant_id
  AND deleted_at IS NULL
  AND (
      owner_id = :trusted_user_id
      OR visibility = 'TENANT'
  )
  AND status = :allowed_status
ORDER BY created_at DESC, id DESC
LIMIT :bounded_limit;
~~~

Sự khác biệt không chỉ ở dấu ngoặc: giá trị **trusted_tenant_id** và **trusted_user_id** phải được server rút ra từ authentication/authorization context. Client không được tự quyết định phạm vi bằng cách thêm query parameter **tenantId**.

## 4. Thiết kế hợp đồng GET collection có giới hạn

Một hợp đồng ban đầu cho danh sách tài liệu:

~~~http
GET /api/v1/documents?status=APPROVED&createdFrom=2026-11-01T00:00:00Z&page=0&size=25 HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
~~~

Quy tắc ví dụ:

| Tham số | Mặc định | Phạm vi hợp lệ | Ý nghĩa |
| --- | --- | --- | --- |
| page | 0 | 0 đến 500 | Trang theo offset, đánh số từ 0 |
| size | 25 | 1 đến 100 | Số item tối đa mỗi trang |
| status | Không lọc | DRAFT, APPROVED, ARCHIVED | Lọc trạng thái được hỗ trợ |
| createdFrom | Không lọc | Thời điểm ISO 8601 hợp lệ | Chỉ lấy tài liệu tạo từ thời điểm đó |
| sort | createdAt:desc | Cho phép một số khóa đã công bố | Thứ tự có thể dự đoán |

**Giới hạn tối đa là hợp đồng server**, không phải một đề xuất để client tự tuân thủ. Server phải từ chối hoặc chuẩn hóa giá trị vượt ngưỡng theo chính sách đã công bố. Trong ví dụ này, server **trả 400** nếu size lớn hơn 100 thay vì âm thầm chấp nhận và trả hàng triệu bản ghi.

Một response đơn giản:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {
      "id": "2fe1",
      "title": "Quy trình giao nhận",
      "status": "APPROVED",
      "createdAt": "2026-11-17T08:45:00Z"
    }
  ],
  "page": 0,
  "size": 25,
  "hasNext": true
}
~~~

Số item trả về ở trang cuối có thể nhỏ hơn size. **hasNext** được tính dựa trên tập dữ liệu **đã áp chính sách quyền**, không phải toàn bộ bảng. Response không cần cung cấp total count nếu UI chỉ cần tải thêm.

### 4.1. Vì sao không để size mặc định là “không giới hạn”?

Với 2 triệu tài liệu, trả mọi bản ghi có thể gây:

- Full table scan hoặc quét index lớn;
- tạo hàng triệu object trong JVM và áp lực GC;
- nhiều MB/GB JSON trên mạng;
- timeout ở gateway, tăng retry, tăng số kết nối đang mở;
- cạn connection pool/DB IOPS và gây **noisy neighbor** giữa tenant;
- phát lộ dữ liệu vượt phạm vi nếu security filter chỉ được thêm sau khi truy vấn xong.

Phân trang và giới hạn là biện pháp **availability**, còn phân quyền và projection là biện pháp **confidentiality**. Cần cả hai.

### 4.2. Có nên tự động giảm size quá lớn xuống 100?

Có hai chính sách:

1. **Reject:** size=100000 → 400 với mã lỗi **INVALID_PAGE_SIZE**, giúp client biết hợp đồng đã bị vi phạm.
2. **Clamp:** size=100000 → thực tế dùng 100, kèm metadata rõ về size hiệu lực.

Cả hai đều có thể chấp nhận khi được tài liệu hóa. Với API dành cho lập trình viên, **reject** thường dễ phát hiện lỗi tích hợp hơn. Không được thực thi query theo giá trị chưa giới hạn rồi mới cắt kết quả ở cuối: làm vậy vẫn có thể khiến DB và JVM quá tải.

## 5. Chống truy vấn sâu bằng offset và chọn cursor khi phù hợp

### 5.1. Offset pagination

Ví dụ trang 4 với size 25:

~~~sql
SELECT id, title, created_at
FROM documents
WHERE tenant_id = :trusted_tenant_id
  AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 25 OFFSET 100;
~~~

Offset dễ hiểu, thuận tiện nhảy đến một số trang. Nhưng với OFFSET rất lớn, CSDL vẫn có thể phải duyệt và bỏ qua nhiều dòng. Ngoài ra, dữ liệu thay đổi trong lúc phân trang có thể làm bản ghi **bị lặp hoặc bị bỏ sót** giữa các trang.

Giới hạn size **không đủ** để bảo vệ hiệu năng nếu cho phép page=1000000. Có thể đặt maxPage, maxOffset hoặc chặn truy vấn sâu và chuyển sang cursor.

### 5.2. Cursor/keyset pagination

Khi client liên tục tải trang kế tiếp và tập dữ liệu lớn, cursor/keyset thường phù hợp hơn. Với thứ tự **created_at DESC, id DESC**, trang tiếp theo có thể dùng điều kiện:

~~~sql
SELECT id, title, created_at
FROM documents
WHERE tenant_id = :trusted_tenant_id
  AND deleted_at IS NULL
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Tất cả các bộ lọc và điều kiện phân quyền **của request hiện tại** vẫn phải nằm trong query. Điều kiện cursor **không thay thế** tenant scope.

Để biết còn trang sau, server có thể lấy **limit+1** dòng, trả tối đa **limit** dòng và tạo nextCursor khi còn dòng thứ limit+1. Nên sắp xếp theo khóa ổn định, có **tie-breaker id** để tránh hai bản ghi có cùng created_at làm mất vị trí.

Cursor không nên chỉ là chuỗi ngẫu nhiên không rõ phạm vi. Một cursor có thể chứa:

- version định dạng;
- vị trí khóa sắp xếp (lastCreatedAt, lastId);
- thứ tự và fingerprint của các filter có ý nghĩa;
- phạm vi tenant hoặc subject phù hợp;
- thời hạn hết hiệu lực;
- chữ ký/HMAC hoặc tham chiếu tới trạng thái cursor lưu phía server.

Khi client thay filter, sort hoặc tenant nhưng giữ cursor cũ, server phải phát hiện và từ chối hoặc quy định chính sách rõ. **Base64 không phải bảo mật**: giá trị có thể bị sửa nếu không kiểm tra tính toàn vẹn. Dù cursor có ký, mỗi query vẫn cần áp quyền dựa trên phiên hiện tại.

### 5.3. Cursor không tự tạo snapshot

Nếu dữ liệu được thêm, xóa hoặc cập nhật giữa các trang, cursor giúp ổn định vị trí theo thứ tự nhưng không tự hứa một snapshot bất biến. Với báo cáo tài chính hoặc export cần kết quả nhất quán tại một thời điểm, phải thiết kế thêm snapshot/version/asOf watermark hoặc job xuất dữ liệu có cơ chế chốt tập kết quả.

## 6. Kiểm soát các trường được phép lọc và sắp xếp

Cho phép client gửi bất kỳ tên cột, tên bảng, toán tử hoặc biểu thức SQL đều có thể tạo rủi ro bảo mật và hiệu năng. Thiết kế nên theo **allowlist**:

| Đầu vào | Nên hỗ trợ | Nên từ chối hoặc kiểm soát chặt |
| --- | --- | --- |
| status | Enum rõ ràng | Mọi chuỗi không được định nghĩa |
| createdFrom/createdTo | Thời điểm hợp lệ, giới hạn khoảng nếu cần | Tự do truyền biểu thức SQL hoặc ngày sai |
| ownerId | ID đúng kiểu, vẫn phải áp quyền | Thay thế tenant context bằng ownerId |
| sort | createdAt, title hoặc ID khi có index và policy | sort theo trường bí mật, join động, SQL expression |
| search | Full-text query có giới hạn và engine an toàn | Regex tùy ý trên toàn dữ liệu, wildcard quá rộng |
| fields | Tập projection được phép theo role | passwordHash, secretToken, internalNotes |
| includeDeleted | Chỉ role/endpoint được phép | Client thường tự bật để xem dữ liệu ẩn |
| expand | Danh sách quan hệ hỗ trợ, giới hạn độ sâu | Expand vô hạn gây N+1 hoặc lộ liên kết |

Một mẫu nguy hiểm:

~~~java
String sql = "SELECT * FROM documents ORDER BY " + request.getParameter("sort");
~~~

Dùng bind parameters cho **giá trị** không giải quyết việc tên cột hay câu lệnh được nối trực tiếp vào SQL. Thay vì tin chuỗi sort, ánh xạ tham số từ allowlist:

~~~java
String sortField = switch (sortKey) {
    case "createdAt" -> "createdAt";
    case "title" -> "title";
    default -> throw new BadRequestException("UNSUPPORTED_SORT");
};
~~~

Nếu dữ liệu dùng mã phân loại nhạy cảm, việc cho phép **sort theo trường bí mật** hoặc **filter theo trường mà caller không được đọc** cũng có thể tiết lộ quan hệ, thứ tự hoặc sự tồn tại qua thay đổi của tập kết quả. Quyền dùng một filter hoặc facet cần được xem là một phần của **authorization**, không chỉ validation.

## 7. SQL injection, expression injection và truy vấn tốn kém

### 7.1. Dùng parameterized query

Giá trị filter phải được truyền qua **prepared statement/ORM parameter**, không nối chuỗi SQL do người dùng nhập:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :trusted_tenant_id
  AND deleted_at IS NULL
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :bounded_limit;
~~~

**:status** được bind làm giá trị, không được đưa trực tiếp vào SQL string. Với JPA Criteria/Specifications, dùng typed predicate để tránh nối biểu thức SQL.

### 7.2. Không chấp nhận ngôn ngữ truy vấn tùy ý nếu chưa có sandbox

Endpoint như **?filter=status eq APPROVED or true** hoặc cho phép JSON tùy ý mô tả cây boolean có thể khiến client dựng điều kiện bỏ qua ràng buộc, join không hạn chế hoặc truy vấn rất tốn tài nguyên. Nếu sản phẩm thật sự cần một ngôn ngữ lọc:

1. Định nghĩa grammar và allowlist trường/toán tử.
2. Giới hạn số node, độ sâu, số mệnh đề OR, độ dài chuỗi, số phần tử IN.
3. Compile thành biểu thức được parameterize.
4. **Luôn AND scope quyền ở cấp ngoài cùng**, không cho phép cú pháp client tham chiếu hoặc phủ định predicate bảo mật.
5. Đặt giới hạn chi phí, thời gian chạy và ngân sách theo tenant.

Không dựa vào regex thay thế chuỗi SQL hoặc blacklist từ khóa để bảo đảm an toàn.

### 7.3. Chi phí của LIKE, regex và tìm kiếm

Các tìm kiếm kiểu **LIKE '%text%'** có thể không tận dụng index B-tree thông thường, đặc biệt khi wildcard ở đầu. Regex phức tạp có thể tạo tải CPU bất thường hoặc nguy cơ ReDoS tùy engine và biểu thức. Nên cân nhắc:

- giới hạn độ dài từ khóa, danh sách từ và số wildcard;
- dùng full-text/search index phù hợp với yêu cầu;
- giới hạn thời gian truy vấn và concurrency;
- áp phân vùng tenant và policy trước khi truy vấn;
- đo query plan cho các mẫu filter có tải thật.

Nếu API cho phép lọc trên nhiều quan hệ, join có thể nhân số hàng và gây sai phân trang/count. Cần kiểm tra duplicate, DISTINCT, tính đúng của aggregation và tác động index.

## 8. Rò rỉ thông tin không chỉ nằm trong items

Một response không có tài liệu trái quyền vẫn có thể **rò rỉ dữ liệu qua metadata**.

### 8.1. Total count

Giả sử user A chỉ được xem 20 tài liệu, nhưng server trả:

~~~json
{
  "items": [{"id":"visible-document"}],
  "total": 7350
}
~~~

Nếu **total=7350** lấy từ toàn bảng, người dùng đã biết có 7.350 tài liệu, thậm chí có thể lặp filter để suy ra số lượng tài liệu nhạy cảm. Total phải được tính **trên cùng tập dữ liệu đã áp scope quyền và filter hợp lệ** hoặc không công bố.

### 8.2. Facet/aggregation

Endpoint tìm kiếm có thể trả:

~~~json
{
  "items": [],
  "facets": {
    "classification": {
      "PUBLIC": 20,
      "CONFIDENTIAL": 3
    }
  }
}
~~~

Nếu facet tính từ mọi bản ghi thay vì tập user được đọc, số **CONFIDENTIAL=3** là rò rỉ dù items rỗng. Count, facet, min/max, histogram, autocomplete, suggestion và distinct values phải tuân cùng policy.

### 8.3. Bộ lọc cho trường không được xem

Ví dụ user không được xem trường **salary**, nhưng API cho phép **?salaryMin=100000** và trả **total=1**. Chỉ cần thử nhiều giá trị, người gọi có thể suy ra gần đúng mức lương. Ngay cả khi không trả salary trong body, filter là một **kênh suy luận**.

Giải pháp không chỉ là ẩn trường khỏi JSON: phải giới hạn **quyền lọc và thống kê** theo classification/role, và cân nhắc aggregation privacy với dữ liệu nhạy cảm.

### 8.4. Error, pagination và thời gian phản hồi

Các kênh phụ khác:

- **Lỗi khác nhau:** “Owner u-123 tồn tại nhưng bạn không có quyền” có thể lộ người dùng; cân nhắc 404/403 theo chính sách.
- **Pagination metadata:** hasNext, nextCursor hoặc số trang có thể lộ tổng số không được phép nếu tính sai scope.
- **Sort:** thứ tự, trang trống hoặc thay đổi phân bố có thể biểu lộ giá trị của trường ẩn.
- **Timing:** truy vấn trả rất nhanh/chậm tùy dữ liệu hiện hữu có thể tạo side channel; với dữ liệu nhạy cảm cần đánh giá giới hạn truy vấn, chuẩn hóa thông tin lỗi, rate limiting và threat model phù hợp.
- **Cache:** cache chung không có scope theo user/tenant có thể trả danh sách hoặc count của người khác.

Không thể chỉ dùng một chính sách **field projection** rồi tuyên bố API không rò rỉ. Kiểm tra phải bao gồm **mọi quan sát mà client có thể thu được**.

## 9. Response projection và quyền theo từng trường

Kể cả sau khi lọc đúng tài nguyên, không nên trả entity CSDL nguyên vẹn. Một entity có thể chứa nội dung nội bộ:

~~~text
DocumentEntity:
  id
  tenantId
  title
  status
  createdAt
  ownerId
  internalNotes
  encryptionKeyReference
  reviewerEmail
  deletedAt
~~~

Một response danh sách chỉ cần:

~~~json
{
  "id": "2fe1",
  "title": "Quy trình giao nhận",
  "status": "APPROVED",
  "createdAt": "2026-11-17T08:45:00Z"
}
~~~

**DTO projection** giúp giảm payload và tránh công bố nhầm cột dữ liệu. Tuy nhiên, DTO không thay thế **row-level authorization**: nếu query lấy cả tài liệu tenant B, việc chỉ trả title vẫn là rò rỉ.

Nếu có lựa chọn **fields=...**, chỉ cho phép field được công bố và người gọi được quyền đọc. Không cho client yêu cầu nested association tùy ý; giới hạn depth/expand để tránh N+1 và lộ dữ liệu liên quan.

## 10. Kiến trúc phòng thủ nhiều lớp

~~~mermaid
flowchart TD
    C[Client GET /documents?filters] --> G[Gateway: auth, rate, request limits]
    G --> V[Controller: parse và validate filter/page]
    V --> P[Policy engine: trusted tenant/user scope]
    P --> Q[Query builder: scope AND client filters]
    Q --> DB[(DB: indexes, RLS nếu phù hợp)]
    DB --> X[Projection: chỉ field được phép]
    X --> M[Metadata: count/facet trên authorized set]
    M --> R[Bounded JSON response]
    R --> C
~~~

Các lớp phòng thủ:

1. **Gateway:** giới hạn request, tốc độ và concurrency; không coi rate limit là biện pháp phân quyền.
2. **Controller:** validate kiểu dữ liệu, enum, độ lớn, page, size, sort và khoảng thời gian.
3. **Authorization:** tính tenant/user/role scope từ principal đã xác thực.
4. **Query/Data access:** gắn scope bắt buộc vào mọi SELECT, COUNT, export và aggregation.
5. **Database:** index, timeout, resource quotas; có thể dùng Row Level Security làm lớp phòng thủ bổ sung nếu DB phù hợp.
6. **Serializer:** trả DTO được phép, không serialize entity tùy ý.
7. **Cache và telemetry:** tránh cache chéo quyền; không log giá trị query bí mật hoặc nhãn metric có cardinality lớn.

### 10.1. Row Level Security không thay cho kiểm tra quyền ở API

Với PostgreSQL, RLS có thể giúp giới hạn hàng dữ liệu theo session context. Nhưng để bảo vệ thực tế:

- role ứng dụng không phải superuser, không có BYPASSRLS;
- tenant context được thiết lập từ thông tin đã xác thực, không từ chuỗi client tự cung cấp;
- cấu hình connection pool/transaction pooling không làm rò session context;
- policy được áp dụng cho **SELECT, COUNT, UPDATE, DELETE** theo yêu cầu;
- đường truy vấn bằng privileged role, backup, reporting và migration phải được kiểm soát riêng.

RLS là một lớp **defense-in-depth**. Application vẫn cần quy tắc nghiệp vụ, field-level authorization, validation filter và giới hạn chi phí truy vấn.

## 11. Ví dụ Java/Spring Boot: danh sách có scope và giới hạn

Ví dụ minh họa dùng **Java 17+**, **Spring Boot 3/Spring Data JPA**. API liệt kê tài liệu của tenant đã xác thực, trong đó user chỉ thấy tài liệu **do mình sở hữu** hoặc **được chia sẻ trong tenant**. Client được lọc status và thời gian tạo, nhưng **không được override tenant scope**.

### 11.1. DTO và repository

~~~java
public enum DocumentStatus {
    DRAFT, APPROVED, ARCHIVED
}

public record DocumentSummary(
        UUID id, String title, DocumentStatus status, Instant createdAt) {}

public record DocumentPageResponse(
        List<DocumentSummary> items,
        int page,
        int size,
        boolean hasNext) {}

public interface DocumentRepository
        extends JpaRepository<Document, UUID>,
                JpaSpecificationExecutor<Document> {}
~~~

Entity **Document** trong ví dụ có các thuộc tính: **tenantId**, **ownerId**, **visibility**, **status**, **createdAt**, **deletedAt**, **id**, **title**. Đây là đoạn code minh họa để tập trung vào query design; import và mapping entity thực tế cần được bổ sung.

### 11.2. Principal scope đáng tin

~~~java
public record DocumentScope(UUID tenantId, UUID userId) {}

public interface DocumentScopeResolver {
    // Chỉ lấy từ authentication + membership đã kiểm chứng.
    DocumentScope requireDocumentScope();
}
~~~

**Không** cho phép controller nhận **tenantId** như tham số để sử dụng thay scope. Nếu một người dùng thuộc nhiều tổ chức, lựa chọn tenant của client phải được backend **đối chiếu với membership và quyền** trước khi tạo DocumentScope.

### 11.3. Controller và giới hạn truy vấn

~~~java
@RestController
@RequestMapping("/api/v1/documents")
public class DocumentQueryController {
    private final DocumentQueryService service;
    private final DocumentScopeResolver scopeResolver;

    public DocumentQueryController(
            DocumentQueryService service,
            DocumentScopeResolver scopeResolver) {
        this.service = service;
        this.scopeResolver = scopeResolver;
    }

    @GetMapping
    public DocumentPageResponse list(
            @RequestParam(required = false) DocumentStatus status,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant createdFrom,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "25") int size) {

        if (page < 0 || page > 500 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid page or size");
        }

        DocumentScope scope = scopeResolver.requireDocumentScope();
        return service.findDocuments(scope, status, createdFrom, page, size);
    }
}
~~~

Nếu sử dụng thêm tham số **sort**, áp dụng allowlist và mapping ở backend. Ví dụ cố định thứ tự **createdAt DESC, id DESC**, giảm khả năng sort theo trường nhạy cảm và giúp phân trang ổn định.

### 11.4. Service: policy luôn nằm ngoài filter của client

~~~java
@Service
public class DocumentQueryService {
    private final DocumentRepository repository;

    public DocumentQueryService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public DocumentPageResponse findDocuments(
            DocumentScope scope,
            DocumentStatus requestedStatus,
            Instant createdFrom,
            int pageNumber,
            int pageSize) {

        Specification<Document> securityScope = (root, query, cb) ->
            cb.and(
                cb.equal(root.get("tenantId"), scope.tenantId()),
                cb.isNull(root.get("deletedAt")),
                cb.or(
                    cb.equal(root.get("ownerId"), scope.userId()),
                    cb.equal(root.get("visibility"), "TENANT")
                )
            );

        Specification<Document> filters = Specification.where(null);

        if (requestedStatus != null) {
            filters = filters.and((root, query, cb) ->
                cb.equal(root.get("status"), requestedStatus));
        }
        if (createdFrom != null) {
            filters = filters.and((root, query, cb) ->
                cb.greaterThanOrEqualTo(
                    root.get("createdAt"), createdFrom));
        }

        Specification<Document> finalSpec = securityScope.and(filters);

        Sort stableSort = Sort.by(Sort.Direction.DESC, "createdAt")
            .and(Sort.by(Sort.Direction.DESC, "id"));
        Pageable pageable = PageRequest.of(
            pageNumber, pageSize, stableSort);

        Page<Document> result = repository.findAll(finalSpec, pageable);
        List<DocumentSummary> items = result.getContent().stream()
            .map(d -> new DocumentSummary(
                d.getId(), d.getTitle(), d.getStatus(),
                d.getCreatedAt()))
            .toList();

        return new DocumentPageResponse(
            items, pageNumber, pageSize, result.hasNext());
    }
}
~~~

**Ý nghĩa an toàn:** finalSpec luôn bao gồm **securityScope AND filters**. Một status do client cung cấp không thể thay thế tenant ID hoặc vô hiệu hóa visibility. Điều kiện phân quyền được áp dụng trong SQL/ORM query, **trước khi** giới hạn trang và lấy dữ liệu lên JVM.

**Giới hạn của ví dụ:**

- Các class, import, entity mapping, quy tắc quyền đầy đủ và exception handler được lược bỏ.
- Trường visibility được minh họa bằng string **TENANT**; trong production nên dùng enum/typed mapping nhất quán.
- **JpaSpecificationExecutor.findAll(spec, pageable)** trả **Page**, có thể cần truy vấn COUNT và ảnh hưởng hiệu năng. Nếu UI không cần total, cân nhắc repository tùy chỉnh trả **Slice** hoặc truy vấn **limit+1** để tránh COUNT đắt. Ví dụ này chỉ dùng **hasNext** và không công bố total.
- **Page** là offset pagination; page tối đa 500 chỉ là giới hạn giả định. Với tập lớn, chuyển sang keyset/cursor.
- Cần bảo đảm owner/visibility đủ diễn tả chính sách thật; nếu tài liệu nhạy cảm có classification hoặc ACL riêng, phải bổ sung predicate bắt buộc.
- CSDL phải có index phù hợp và kiểm thử chi phí truy vấn. **@Transactional(readOnly = true)** không tự đặt DB statement timeout hoặc bảo đảm query nhẹ.
- Client không được tự điều khiển tên cột trong Sort, điều kiện tenant hoặc expression SQL.

### 11.5. Giới hạn bảo vệ thêm ở DB và hạ tầng

Ngay cả với size ≤ 100:

- đặt statement timeout phù hợp với SLA để chặn query bất thường;
- hạn chế concurrent expensive queries và quota theo tenant;
- cấu hình DB user quyền tối thiểu;
- có index đúng theo predicate tenant/status và sort;
- theo dõi query plan, số hàng quét, latency p95/p99 và số lỗi timeout.

Nếu người dùng cần **xuất hàng trăm nghìn bản ghi**, nên dùng **export job có quota, audit, progress, giới hạn quyền và storage bảo vệ**, thay vì cho size=1000000 trên GET.

## 12. Index, kế hoạch truy vấn và giới hạn tài nguyên

Ví dụ PostgreSQL, với dữ liệu thường được đọc theo tenant và ngày tạo, có thể cân nhắc index:

~~~sql
CREATE INDEX idx_documents_tenant_created_active
ON documents (tenant_id, created_at DESC, id DESC)
WHERE deleted_at IS NULL;
~~~

Index này minh họa cách thu hẹp theo tenant và hỗ trợ thứ tự mới nhất trước. Hiệu quả thực tế phụ thuộc phân bố dữ liệu, điều kiện owner/visibility, status, số hàng, thống kê và query plan. Không có index duy nhất tối ưu cho mọi tổ hợp filter.

Để kiểm chứng, dùng **EXPLAIN (ANALYZE, BUFFERS)** trong môi trường thử với dữ liệu đại diện, theo dõi số dòng quét và I/O. Không chạy phép phân tích gây tải cao vào production nếu chưa có quy trình kiểm soát.

Những giới hạn cần định nghĩa:

| Hạn mức | Mục đích |
| --- | --- |
| Max size/page | Chặn response quá lớn |
| Max offset | Tránh truy vấn bỏ qua hàng triệu dòng |
| Max date range | Giới hạn tập lọc khi truy vấn thống kê |
| Max filter complexity | Tránh điều kiện OR/IN/regex phức tạp |
| Statement timeout | Giới hạn thời gian query chạy |
| Max concurrent queries | Bảo vệ connection pool/DB |
| Rate limit / weighted quota | Ngăn một client tạo quá nhiều query đắt |
| Export limit và job quota | Tách bài toán dữ liệu lớn khỏi API danh sách |

**Chính sách quota theo request** có thể chưa đủ: một request có filter phức tạp có thể đắt hơn hàng chục request lọc theo ID. Khi sản phẩm có nhiều dạng query, cân nhắc **weighted rate limit** hoặc lớp phân loại độ phức tạp theo khả năng đo được.

## 13. Cache, ETag và phân quyền của danh sách

Một danh sách tài liệu là dữ liệu thay đổi theo tenant, user, quyền và filter. Nếu response cache bị chia sẻ sai, request của user B có thể nhận dữ liệu của user A.

Các lựa chọn:

- Với dữ liệu nhạy cảm, có thể dùng **Cache-Control: private, no-store** để ngăn lưu ở HTTP cache theo yêu cầu hợp đồng.
- Nếu cho phép cache phía client, dùng **private** với thời hạn ngắn và bảo đảm dữ liệu không xuất hiện ở shared cache.
- Nếu có application cache, key cần bao gồm **tenant, phạm vi quyền/policy version, filter, sort, page/cursor và các thuộc tính ảnh hưởng kết quả**.
- Invalidate cache khi quyền, visibility, membership hoặc bản ghi thay đổi.
- **ETag** cho collection phải phản ánh biểu diễn được phép của người gọi, không tái sử dụng ETag toàn cục cho những biểu diễn khác quyền.
- Không cho client sửa cache key hoặc dùng tenant ID tùy ý để đọc dữ liệu đã cache.

**Vary** và Authorization có liên quan đến HTTP caching, nhưng chỉ thêm **Vary: Authorization** không đủ để chứng minh toàn bộ proxy/CDN và cache ứng dụng không rò rỉ; cần kiểm thử chính sách thực tế của hệ thống.

## 14. API trả lỗi nhất quán cho filter và phân trang

Một contract có thể dùng **application/problem+json** theo RFC 9457.

Ví dụ size vượt giới hạn:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-page-size",
  "title": "Invalid page size",
  "status": 400,
  "detail": "size phải nằm trong khoảng từ 1 đến 100.",
  "code": "INVALID_PAGE_SIZE"
}
~~~

Các trường **code** là extension do ứng dụng định nghĩa; status HTTP cần phù hợp.

| Tình huống | Phản hồi gợi ý |
| --- | --- |
| size=0 hoặc size>100 | 400 INVALID_PAGE_SIZE |
| page âm hoặc vượt page cap | 400 INVALID_PAGE |
| sort field không có trong allowlist | 400 UNSUPPORTED_SORT |
| status enum không hợp lệ | 400 INVALID_FILTER |
| createdFrom không parse được | 400 INVALID_DATE |
| cursor sai chữ ký/hết hạn/khác filter | 400 INVALID_CURSOR hoặc lỗi hợp đồng đã định |
| Không có token hợp lệ | 401 kèm challenge phù hợp |
| Không có quyền sử dụng endpoint | 403, hoặc chính sách riêng |
| Không có dữ liệu trong phạm vi đã lọc | 200 với items rỗng |
| Vượt rate limit | 429 với Retry-After khi có căn cứ |
| DB tạm không thể xử lý | 503/500 theo nguyên nhân, không ngụy trang thành 400 |

**Không dùng 416 Range Not Satisfiable** cho page out-of-range thông thường: 416 áp dụng ngữ nghĩa **Range** của HTTP, không phải query parameter page. Một trang hợp lệ nhưng nằm sau trang cuối thường trả 200 với danh sách rỗng theo hợp đồng.

Không trả thông điệp kiểu **“Tài liệu của tenant khác tồn tại nhưng bạn không có quyền”** khi filter theo ID/owner: lỗi và response không được tiết lộ metadata ngoài phạm vi.

## 15. OpenAPI 3.1 cho collection queries an toàn

Đoạn dưới đây mô tả hợp đồng offset pagination có giới hạn, filter status và createdFrom. Trong ví dụ, backend không nhận tenantId làm query parameter:

~~~yaml
openapi: 3.1.0
info:
  title: Document Collection API
  version: 1.0.0
paths:
  /api/v1/documents:
    get:
      operationId: listDocuments
      summary: Danh sách tài liệu trong phạm vi được phép
      description: >
        Server luôn áp điều kiện tenant và quyền từ người gọi.
        Filter của client chỉ thu hẹp tập dữ liệu đã được phân quyền.
      security:
        - bearerAuth: []
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [DRAFT, APPROVED, ARCHIVED]
        - name: createdFrom
          in: query
          required: false
          schema:
            type: string
            format: date-time
        - name: page
          in: query
          required: false
          schema:
            type: integer
            minimum: 0
            maximum: 500
            default: 0
        - name: size
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 25
      responses:
        '200':
          description: Danh sách đã phân quyền và phân trang
          content:
            application/json:
              schema:
                type: object
                required: [items, page, size, hasNext]
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      required: [id, title, status, createdAt]
                      properties:
                        id:
                          type: string
                          format: uuid
                        title:
                          type: string
                        status:
                          type: string
                          enum: [DRAFT, APPROVED, ARCHIVED]
                        createdAt:
                          type: string
                          format: date-time
                  page:
                    type: integer
                  size:
                    type: integer
                  hasNext:
                    type: boolean
        '400':
          description: Bộ lọc hoặc tham số phân trang không hợp lệ
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền truy vấn
        '429':
          description: Vượt giới hạn truy vấn
        '503':
          description: Dịch vụ truy vấn tạm không sẵn sàng
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

**Lưu ý:** bản OpenAPI này nêu nguyên tắc phân quyền trong mô tả, nhưng OpenAPI tự nó **không thực thi** chính sách. Khi production, cần thêm schema Problem Details và ví dụ lỗi, định nghĩa cache headers, chính sách sort nếu hỗ trợ và các điều kiện giới hạn khác.

## 16. Kiểm thử bảo mật và giới hạn truy vấn

Cần dựng **ít nhất hai tenant A/B**, trong A có user owner, user bình thường và admin; dữ liệu kiểm thử gồm tài liệu private, tenant-shared, đã xóa mềm, nhạy cảm, cùng timestamp để kiểm thử tie-breaker.

### 16.1. Ma trận kiểm thử

| Mã | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Q01 | GET không có size/page | Áp mặc định 25/0, không tải toàn bộ |
| Q02 | size=100 | Tối đa 100 items |
| Q03 | size=101 hoặc size=0 | 400 theo hợp đồng, không query không giới hạn |
| Q04 | page quá giới hạn | 400 hoặc quy tắc đã định, không offset sâu |
| Q05 | page hợp lệ nằm sau trang cuối | 200 và items rỗng |
| Q06 | sort field không thuộc allowlist | 400, không đưa raw sort vào SQL |
| Q07 | status enum không hợp lệ | 400 và mã lỗi ổn định |
| Q08 | SQL injection payload trong filter | Không thể thay đổi scope hoặc câu SQL |
| Q09 | User A lọc ownerId của B cùng tenant nhưng private | Không thấy bản ghi ngoài quyền |
| Q10 | User A cố gửi tenantId của tenant B | Bỏ qua/từ chối tham số theo hợp đồng; không xuất dữ liệu B |
| Q11 | Filter dùng OR gây nguy cơ vượt policy | Scope bắt buộc vẫn được AND ngoài cùng |
| Q12 | Tài liệu đã xóa mềm | Không xuất hiện trong danh sách thường |
| Q13 | Tài liệu của tenant B có status đặc biệt | A không thấy items/count/facets của B |
| Q14 | User không được đọc classification nhưng thử filter theo classification | Filter bị từ chối hoặc không cung cấp kênh suy luận |
| Q15 | Hai bản ghi cùng createdAt | Phân trang không mất/nhân đôi do thiếu tie-breaker |
| Q16 | Thay filter khi tái sử dụng cursor | Cursor bị từ chối hoặc xử lý theo quy tắc |
| Q17 | Sửa payload cursor không có chữ ký hợp lệ | Không thể vượt tenant scope hoặc đọc trang khác |
| Q18 | Thay quyền thành viên trong lúc cache còn hiệu lực | Không trả response cũ trái quyền |
| Q19 | Request nhiều lần/tải cao | Giới hạn quota, timeout và concurrency hiệu lực |
| Q20 | User thường gọi export hoặc expand sâu | Quyền và giới hạn riêng, không bypass danh sách |
| Q21 | Aggregation theo trường nhạy cảm | Không lộ dữ liệu hoặc số lượng trái quyền |
| Q22 | Kiểm thử log/trace | Không ghi token, dữ liệu cá nhân hoặc query bí mật không cần thiết |

### 16.2. Kiểm thử một lỗi rất dễ bỏ sót

Tạo hai tenant A và B. Mỗi tenant có tài liệu **APPROVED**. User A có một tài liệu do mình sở hữu, B có 100 tài liệu APPROVED. Gửi từ A:

~~~http
GET /api/v1/documents?status=APPROVED&size=25 HTTP/1.1
Authorization: Bearer <token-tenant-A>
~~~

Bài kiểm tra phải xác minh **items, hasNext, total nếu có, facet, cache key, logs truy xuất và cursor** đều chỉ phản ánh dữ liệu A được xem. Không chỉ assert phần tử đầu tiên trả về thuộc A.

Nếu triển khai SQL dùng **tenant_id = A AND owner_id = userA OR status = APPROVED**, test này sẽ phát hiện rò rỉ ngay lập tức.

### 16.3. Kiểm thử hiệu năng với dữ liệu đại diện

Tạo dữ liệu đủ lớn để đánh giá query plan: nhiều tenant, một tenant lớn, trạng thái phân bố không đồng đều, nhiều bản ghi cùng timestamp. Thực hiện các lượt:

1. Trang đầu nhỏ có filter chọn lọc.
2. Trang tối đa size=100, filter phổ biến.
3. Truy vấn sâu tới page cap.
4. Search không chọn lọc hoặc khoảng ngày rộng.
5. Nhiều tenant gọi đồng thời với tỷ lệ filter khác nhau.

Đo **p50/p95/p99**, rows scanned, CPU, IOPS, thời gian COUNT, mức dùng connection pool, số timeout và tỉ lệ query bị rate limit. Giới hạn dựa trên SLO và tài nguyên thực; không chọn ngưỡng chỉ vì một lần thử tải nhỏ cho kết quả đẹp.

## 17. Tình huống thực hành: API tìm kiếm đơn hàng đa tenant

**Bối cảnh:** ứng dụng có endpoint **GET /api/v1/orders** với filter status, customerEmail, createdFrom/To, totalMin, sort, page và size. Dữ liệu của 100 tenant nằm trong cùng CSDL. User có quyền xem đơn trong chi nhánh của mình, admin tenant xem toàn bộ chi nhánh tenant đó. Sản phẩm muốn xuất báo cáo lớn cho admin.

Nhóm phát hiện ba vấn đề:

1. Controller đặt size mặc định bằng giá trị cực lớn khi không có tham số.
2. Query tự ghép điều kiện như **branch_id = :branch OR status = :status**.
3. API trả facets theo customerEmail domain của toàn CSDL và một trường totalCount tính từ bảng gốc.

### 17.1. Nhiệm vụ A – Chốt hợp đồng

Thiết kế URL, request schema, giới hạn size/page/cursor, danh sách trường filter/sort hợp lệ và cách xử lý filter không được hỗ trợ. Nêu chiến lược export lớn không dùng size=unlimited.

### 17.2. Nhiệm vụ B – Thực thi quyền và truy vấn

Vẽ pipeline từ gateway đến DB, đặt điều kiện **tenant + branch + role** ở nơi đáng tin. Viết SQL hoặc Criteria pseudocode cho:

~~~text
authorized_scope AND client_filters
~~~

Nêu cách bảo vệ phần OR hợp lệ mà không vượt ngoài phạm vi quyền.

### 17.3. Nhiệm vụ C – Bảo vệ metadata

Giải thích vì sao totalCount, facet domain, sorting và thông báo lỗi vẫn có thể tiết lộ dữ liệu. Đề xuất cách tính aggregation trên authorized set hoặc từ chối filter/aggregation nhạy cảm.

### 17.4. Nhiệm vụ D – Chứng minh thiết kế

Viết tối thiểu tám test, bắt buộc gồm cross-tenant, cross-branch, size cực lớn, page sâu, filter injection, count/facet leakage, cursor tampering và cache theo quyền. Chỉ ra metrics để chứng minh truy vấn không gây quá tải.

### 17.5. Hướng giải tham khảo

Một phương án hợp lý:

- **GET /orders** nhận status, ngày, sort allowlist, page/size với default 25, max 100 và max offset.
- Backend dùng tenantId và allowedBranchIds lấy từ principal đã xác thực; câu query luôn có **tenant_id = trustedTenant AND branch_id IN trustedBranches** trước mọi filter tùy chọn.
- Không cho user thường lọc theo customerEmail nếu trường đó bị phân loại nhạy cảm; nếu role phù hợp được phép, vẫn phải áp phạm vi theo quyền.
- Total/facets được tính từ query đã áp scope, hoặc bỏ nếu không cần để tránh lộ dữ liệu và tốn COUNT.
- Với export lớn, tạo job có quyền riêng, quota, báo cáo tiến độ, lưu file bảo vệ, thời hạn tải xuống và kiểm toán.
- Kiểm thử với tenant B có dữ liệu được thiết kế để làm lộ bug OR và aggregation; đo cả lỗi lộ dữ liệu và hiệu năng.

Lựa chọn này cân bằng **availability, confidentiality, trải nghiệm truy vấn và khả năng vận hành**.

## 18. Các sai lầm phổ biến

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Trả mọi record khi size vắng mặt | Hết bộ nhớ, timeout, lộ dữ liệu diện rộng | Default size, max size, phân trang |
| Chỉ giới hạn size, không giới hạn offset | Query sâu vẫn tốn tài nguyên | Max offset, cursor/keyset |
| Đọc toàn bảng rồi filter quyền trong Java | Dữ liệu trái quyền vào bộ nhớ, tốn tài nguyên, count sai | Áp scope quyền ngay trong truy vấn |
| Ghép OR sai nhóm với tenant | Cross-tenant leakage | Scope bắt buộc AND ở cấp ngoài cùng |
| Tin tenantId/role từ query/header | Caller tự nâng quyền | Derive scope từ principal/membership |
| Cho truyền raw SQL/order expression | Injection và query chi phí cao | Parameterization + allowlist |
| Lấy total/facet từ bảng gốc | Lộ dữ liệu dù items đúng | Tính trên authorized set |
| Cho filter trên trường bí mật | Suy ra dữ liệu ẩn qua kết quả | Field-level filter authorization |
| Dùng entity làm response | Lộ field nội bộ | DTO projection được duyệt |
| Cursor chỉ base64, không kiểm tra scope | Sửa cursor để đọc trang khác | Ký/validate cursor và tái áp quyền |
| Cache chung theo URL nhưng không theo quyền | Trả danh sách user khác | no-store hoặc cache key có scope/policy |
| Dùng COUNT toàn bảng cho mọi trang | Chậm và có nguy cơ leak | Slice/limit+1, count nếu thật sự cần |
| Không hạn chế filter phức tạp | DB/CPU quá tải, ReDoS | Query complexity limits và timeout |
| Cho export bypass policy của list | Lộ dữ liệu số lượng lớn | Export dùng chung policy và quota |
| Chỉ test items, bỏ qua metadata | Không phát hiện total/facet leak | Test items, count, facets, cursor, cache |

## 19. Checklist trước khi phát hành

- [ ] Endpoint danh sách có default size, max size và giới hạn truy vấn sâu.
- [ ] Có sort ổn định với tie-breaker, cursor nếu cần cho dữ liệu lớn.
- [ ] Tất cả filter/sort/expand thuộc allowlist và được validate chặt.
- [ ] Không nối raw SQL, column name hoặc expression từ client.
- [ ] Tenant/user/role scope đến từ ngữ cảnh đã xác thực.
- [ ] Scope quyền được AND vào mọi query, COUNT, facet và export.
- [ ] Phân quyền áp dụng ở tầng dữ liệu trước phân trang/projection.
- [ ] Response chỉ gồm những trường được phép công bố.
- [ ] Không cho filter/aggregate trên trường nhạy cảm trái quyền.
- [ ] Total/hasNext/facets/cursor không làm lộ dữ liệu ngoài phạm vi.
- [ ] Cursor được kiểm tra chữ ký, expiry, tenant và fingerprint filter nếu cần.
- [ ] Cache không trả dữ liệu chéo quyền, có invalidation khi membership đổi.
- [ ] Hạn mức query complexity, timeout, rate/concurrency và quota phù hợp.
- [ ] Có index, explain plan và kiểm thử tải với phân bố tenant thực tế.
- [ ] OpenAPI công bố giới hạn, filter, sort, lỗi và security.
- [ ] Có test cross-tenant, lỗi OR, metadata leakage, injection và hiệu năng.

**Ghi nhớ:** Với REST collection queries, câu hỏi không chỉ là **“trả bao nhiêu bản ghi?”** mà còn là **“được phép biết điều gì về tập dữ liệu?”**. Giới hạn truy vấn bảo vệ hiệu năng và tính sẵn sàng; policy bắt buộc ở tầng dữ liệu, filter allowlist, metadata đúng phạm vi và cache an toàn bảo vệ tính bảo mật. Cả hai nhóm biện pháp phải được thiết kế và kiểm thử cùng nhau.

### Tài liệu tham khảo để đọc thêm

- **RFC 9110 – HTTP Semantics:** phương thức GET, status code, ý nghĩa của các header và điều kiện HTTP.
- **RFC 9111 – HTTP Caching:** Cache-Control, cách lưu và sử dụng response có xác thực.
- **RFC 9457 – Problem Details for HTTP APIs:** hợp đồng phản hồi lỗi cho tham số filter/pagination không hợp lệ.
- **OpenAPI Specification 3.1:** schema cho query parameters, giới hạn, response và security.
- **Spring Data JPA / Spring Security:** Pageable, Specification/Criteria, principal-based authorization và query projections.
