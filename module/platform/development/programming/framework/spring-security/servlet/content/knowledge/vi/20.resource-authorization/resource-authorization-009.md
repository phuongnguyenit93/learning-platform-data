# Phân trang, hiệu năng và lựa chọn giữa lọc truy vấn với lọc sau khi đọc trong Spring Security Servlet

## 1. Bài toán: phân quyền tài nguyên và phân trang phải nhất quán

Giả sử một ứng dụng Spring Security Servlet cung cấp danh sách báo cáo qua API:

```text
GET /api/reports?page=0
Authorization: Basic <credentials>
```

Mỗi báo cáo có `id`, `tenantId`, `ownerUsername`, `title`. Người dùng bình thường chỉ được đọc báo cáo thuộc đúng **tenant** và **owner** của mình; quản trị viên tenant được xem tất cả báo cáo trong **tenant của họ**, không được xem tenant khác.

Hai cách viết truy vấn có vẻ giống nhau nhưng dẫn đến kết quả khác xa:

**Cách A — lọc quyền trước phân trang ở database:**

```sql
SELECT id, title
FROM reports
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_user
ORDER BY id ASC
LIMIT :page_size OFFSET :offset;
```

**Cách B — lấy trang từ dữ liệu chung rồi lọc bằng Java:**

```java
Page<ReportEntity> globalPage = repository.findAll(pageable);
List<ReportEntity> allowed = globalPage.getContent().stream()
    .filter(report -> mayRead(authentication, report))
    .toList();
```

Cách B có thể tạo **trang chỉ có một kết quả dù vẫn còn nhiều tài nguyên được phép ở trang sau**, làm sai `totalElements`, lộ số lượng tài nguyên của người khác và tiêu tốn công sức tải những record không bao giờ được trả cho user. Nếu dữ liệu nhạy cảm đã được đọc vào process trước khi lọc, biên bảo mật còn bị đẩy sâu vào ứng dụng.

**Thông điệp chính:** Với danh sách lớn và policy có thể diễn đạt bằng truy vấn, hãy áp dụng **điều kiện phân quyền trước `LIMIT/OFFSET` hoặc trước cursor/seek**. Sau đó mới phân trang, tính tổng số và mapping DTO trên **tập dữ liệu mà user thật sự được phép thấy**.

Mục tiêu học tập:

1. Hiểu tương tác giữa `Authentication`, `AuthorizationManager`, quyền sở hữu/tenant và truy vấn.
2. Phân biệt **lọc trong query**, **lọc sau truy vấn nhưng trước phân trang**, và **lọc sau khi phân trang**.
3. Giải thích vì sao `@PostFilter`/`Stream.filter` không tự mang lại tính đúng đắn của `Page<T>`.
4. Biết chọn `Page`, `Slice`, offset pagination hay keyset/cursor pagination.
5. Thiết kế `countQuery`/`hasNext` có cùng ranh giới truy cập như truy vấn nội dung.
6. Hạn chế N+1, overfetch, query nặng, cache sai tenant, snapshot drift và lộ thông tin qua metadata.
7. Tự xây dựng ứng dụng Spring Boot 3.3.5 / Java 17 / Spring Data JPA / H2 có kiểm thử MockMvc.

Nội dung áp dụng cho **Servlet stack**, HTTP Basic hoặc form login đều có thể cung cấp Authentication. Ví dụ dùng HTTP Basic để dễ kiểm chứng 401/403, không có nghĩa API production nên truyền mật khẩu qua HTTP không mã hóa.

## 2. Bốn thời điểm lọc dễ bị nhầm lẫn

| Cách thực hiện | Thời điểm policy được áp dụng | Tính đúng đắn của trang | Chi phí/độ an toàn |
| --- | --- | --- | --- |
| **Lọc trong WHERE/JOIN/EXISTS ở DB rồi phân trang** | Trước ORDER BY và LIMIT/OFFSET/seek trên tập được phép | Đúng nếu content/count cùng predicate và thứ tự ổn định | Thường tối ưu nhất; DB có thể tận dụng index và không phải đưa row bị cấm lên application |
| Load **tất cả** record vào Java, lọc quyền, **sau đó** phân trang in-memory | Trước pagination nhưng sau khi đọc toàn bộ tập | Có thể tính đúng trên một snapshot nhỏ nếu cùng policy | Tốn RAM/băng thông, không mở rộng cho tập lớn, có nguy cơ nạp dữ liệu không cần thiết |
| **Lấy global page trước**, rồi `filter(...)` hoặc `@PostFilter` | Sau LIMIT/OFFSET đã áp lên toàn bộ dữ liệu | **Sai/không đầy trang** khi row bị cấm chen giữa; total/hasNext có thể sai | Tải row không được phép, phát sinh thông tin qua metadata |
| Lấy nhiều batch, kiểm tra quyền từng record rồi gom đủ một trang | Sau từng batch query | Có thể đạt số lượng item sau overfetch nhưng khó bảo đảm hasNext/total/cursor đúng | Phức tạp, chi phí biến thiên, cần chặn lặp vô hạn và nhất quán snapshot |

**Đừng đánh đồng “lọc ở service” với “lọc sau phân trang”.** Một service có thể cấu trúc policy và xây predicate truy vấn an toàn; khi đó dữ liệu vẫn được lọc trong database. Vấn đề nằm ở **thứ tự lọc so với việc giới hạn dữ liệu**.

### 2.1. Authorization không chỉ là hasRole

`hasRole("READER")` có thể xác nhận loại quyền chung, nhưng chưa trả lời user A có được đọc báo cáo ID 812 của tenant B không. Chính sách danh sách thường cần ít nhất:

```text
CanSee(report, principal) =
    principal đã authenticated
    AND report.tenant_id == tenant được cấp cho principal
    AND (
        report.owner_username == principal.username
        OR principal có quyền TENANT_ADMIN trong tenant đó
    )
    AND các điều kiện trạng thái nghiệp vụ khác (nếu có)
```

Biểu thức trên là **policy khái niệm**, không phải câu lệnh SQL tự động chạy. Danh tính, tenant membership và role phải lấy từ nguồn **đáng tin**; không coi query `?owner=lan` hay header `X-Tenant: t1` do browser tự gắn là dữ liệu chứng minh quyền.

### 2.2. “Ẩn item sau khi lấy” chưa chắc đủ để bảo vệ

Nếu query đọc toàn bộ entity bao gồm nội dung riêng tư rồi Java mới lọc, các row chưa được phép có thể đã đi qua connection, heap, ORM persistence context, instrumentation hoặc debug log. Điều đó không nhất thiết tự tạo lộ dữ liệu tới client, nhưng làm tăng bề mặt rủi ro và chi phí so với truy vấn chỉ lấy row được phép.

Với dữ liệu nhạy cảm, nên ưu tiên **data minimization**: filter đúng ở query, dùng projection chỉ lấy cột cần cho danh sách, và kiểm tra quyền lại ở đường truy cập tài nguyên chi tiết.

## 3. Ví dụ số học: vì sao lọc sau Page tạo trang sai?

Giả sử database có 8 báo cáo được sắp theo ID tăng dần. User `lan` chỉ được đọc các ID `3, 5, 7, 8`; các ID còn lại thuộc người khác. Trang có tối đa 3 kết quả.

```text
Toàn bộ sau ORDER BY id ASC:
  [1, 2, 3, 4, 5, 6, 7, 8]
Visible với lan:
  [3, 5, 7, 8]

LẤY GLOBAL PAGE RỒI FILTER:
  page 0 global = [1, 2, 3]  -> filter lan = [3]
  page 1 global = [4, 5, 6]  -> filter lan = [5]
  page 2 global = [7, 8]     -> filter lan = [7, 8]

FILTER ĐÚNG TRONG QUERY RỒI LẤY PAGE:
  visible = [3, 5, 7, 8]
  page 0 = [3, 5, 7]
  page 1 = [8]
```

Hậu quả của cách sai:

- Trang đầu chỉ trả 1 item dù tập dữ liệu được phép còn 3 item.
- Metadata `totalElements=8` nếu mượn từ global query sẽ **lộ tổng số của toàn bộ hệ thống**, không phải số user được phép xem.
- Nếu lấy `totalElements=1` từ số item sau lọc của **một trang**, nó lại không phản ánh tổng số visible.
- Client không thể biết chính xác trang tiếp theo có item được phép hay không chỉ bằng `globalPage.hasNext()`.
- Page indexes không còn là chỉ số trang trong **tập visible**; chúng đang trỏ vào trang của tập dữ liệu rộng hơn.
- Với dữ liệu phân bố không đều, nhiều trang liên tiếp có thể rỗng dù vẫn có bản ghi visible ở rất xa.

**Đúng:** Với tập visible `[3,5,7,8]` và size 3, `totalElements=4`, `totalPages=2`, page 0 có 3 item, page 1 có 1 item.

### 3.1. Một dòng code nhìn có vẻ hợp lý nhưng sai

```java
Page<ReportEntity> page = repo.findAll(pageable);

List<ReportEntity> allowed = page.getContent().stream()
    .filter(row -> canRead(authentication, row))
    .toList();

// Sai nếu dùng page.getTotalElements(): đó là total của toàn DB.
// Sai nếu dùng allowed.size(): chỉ là số item được giữ ở page đang xem.
```

Không có mẹo “cộng lại một chút” để sửa `totalElements` chính xác từ một page đã lọc. Bạn cần biết **tập visible đầy đủ** (hoặc có một filtered count query tương đương).

### 3.2. Page.map() không phải Page.filter()

Spring Data `Page.map(...)` hữu ích để **chuyển kiểu** các item, ví dụ entity sang DTO. Nó không có ý nghĩa tự động làm lại phép phân trang và total sau khi loại bỏ phần tử. Không viết một mapper trả `null` rồi tuyên bố đã có filtered Page: null item có thể xuất hiện trong content, và các metadata vẫn có nguồn gốc trước mapping.

```java
Page<ReportSummary> summaries =
    authorizedPage.map(report ->
        new ReportSummary(report.getId(), report.getTitle()));
```

Mảnh code trên đúng khi **`authorizedPage` đã là trang được lọc quyền trước đó**, không phải khi `authorizedPage` chứa mọi tenant rồi định dùng mapping để ẩn.

## 4. Chọn lọc trong database khi policy diễn đạt được bằng SQL/JPQL

Với policy cơ bản:

```text
member: tenant_id = trustedTenant AND owner_username = authenticatedUsername
tenant admin: tenant_id = trustedTenant
```

Một cách rõ ràng là có **hai truy vấn riêng**:

```sql
-- Người dùng bình thường:
SELECT id, title
FROM reports
WHERE tenant_id = :tenant_id
  AND owner_username = :username
ORDER BY id ASC
LIMIT :limit OFFSET :offset;

-- Admin của tenant:
SELECT id, title
FROM reports
WHERE tenant_id = :tenant_id
ORDER BY id ASC
LIMIT :limit OFFSET :offset;
```

Đây là SQL định hướng ví dụ, không phải cú pháp `@Query` của JPA. Spring Data `Pageable` có thể chuyển sort/limit/offset thành câu lệnh phù hợp với database dialect.

Ưu điểm:

1. DB lọc ngay lúc tìm row, có thể dùng index theo tenant/owner.
2. Truy vấn danh sách không phải nạp record thuộc tenant khác vào Java.
3. `COUNT(*)` có thể sử dụng **cùng điều kiện quyền** để trả tổng visible.
4. Content và metadata không vô tình dùng hai phạm vi khác nhau.
5. Cùng predicate có thể được tái sử dụng trong các thao tác search/sort mà vẫn giữ biên truy cập.

### 4.1. Tránh dùng OR thiếu kiểm soát với quyền admin

Một cách viết khái niệm:

```sql
WHERE tenant_id = :tenant
  AND (owner_username = :username OR :is_tenant_admin = TRUE)
```

Có thể đúng nếu `is_tenant_admin` thật sự được tính từ Authentication/permission server-side cho chính tenant đó. Nhưng boolean do client gửi `?admin=true` là **không an toàn**. Trong ví dụ code, service chọn query admin/owner riêng để dễ review, tránh một điều kiện OR khó tối ưu hoặc sai nguồn tham số.

### 4.2. Truy vấn cần cùng semantics với resource authorization

Giả sử endpoint `GET /api/reports/{id}` kiểm tra owner + tenant + status "VISIBLE", nhưng list chỉ lọc owner + tenant. Khi đó list có thể tiết lộ title/ID của báo cáo đã bị khóa, dù detail bị chặn. **List và detail phải cùng một chính sách visibility có chủ đích**.

Nếu permission thay đổi theo nhóm, ACL hoặc thời gian, hãy đưa predicate tương ứng vào JOIN/EXISTS, row-level security, materialized access table hoặc view, thay vì cố gắng duy trì bộ lọc Java khác biệt với query.

### 4.3. Count query cũng phải lọc quyền

Một `Page<T>` thường có thêm truy vấn tổng số item để tính:

```text
totalElements = COUNT(visible rows under the same policy)
totalPages = ceil(totalElements / pageSize)
```

SQL/JPQL sai:

```sql
-- Nội dung đã lọc tenant, nhưng count không lọc tenant/owner:
SELECT COUNT(*) FROM reports;
```

Kết quả sai/leak. Count đúng cho member:

```sql
SELECT COUNT(*)
FROM reports
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_username;
```

Nếu query content có JOIN nhiều-một khiến một report xuất hiện nhiều row, count có thể cần `COUNT(DISTINCT report.id)` hoặc cấu trúc `EXISTS` tránh nhân bản. Đừng đoán rằng `COUNT(*)` luôn bằng số report duy nhất.

## 5. Khi nào dùng Page, Slice hoặc trả list không có tổng?

| Kiểu kết quả | Có count tổng? | Có hasNext? | Khi phù hợp |
| --- | --- | --- | --- |
| `Page<T>` | Có `totalElements`/`totalPages` (thường cần count query) | Có | UI cần số trang/tổng visible và dữ liệu không quá đắt để count |
| `Slice<T>` | Không cam kết total count toàn tập | Có, dựa trên cơ chế đọc thêm/kiểm tra còn trang sau | Infinite scrolling, API không cần đếm tổng; count tốn kém |
| `List<T>` với limit rõ ràng | Không tự có total/hasNext | Phải thiết kế riêng | Các truy vấn cố định/nhỏ, hoặc endpoint không có khái niệm trang |
| Cursor/keyset window | Thường không count tổng | Có next cursor nếu còn row theo seek | Feed dữ liệu lớn, deep pagination và thứ tự ổn định |

### 5.1. Page và count query

Spring Data JPA `Page<ReportSummary>` có thể tính `getTotalElements()` và `getTotalPages()`. Repository thường thực hiện count query khi cần (framework có thể tối ưu trong vài tình huống, không nên giả định luôn đúng một số SQL cố định).

Quan trọng nhất: count query phải bị giới hạn bởi đúng **tenant, owner, status, search filters và các policy khác** như content query.

### 5.2. Slice tránh count nhưng không sửa lỗi lọc sau phân trang

`Slice` giúp tránh count toàn bộ visible. Tuy nhiên, nếu trước tiên lấy một **global slice** rồi lọc quyền ở Java, `hasNext` vẫn đang phản ánh global dataset, và trang có thể rỗng/thiếu item. Muốn Slice đúng, phải áp policy trước khi xác định slice boundary.

### 5.3. Không phải UI nào cũng cần totalElements

Nếu UX chỉ là nút “Tải thêm”, việc tính count lớn có thể không cần. Có thể dùng `Slice` với điều kiện quyền trong query và câu trả lời có `hasNext`, hoặc keyset cursor. Không trả global count chỉ vì framework `Page` hỗ trợ, bởi nó làm tăng truy vấn và có thể tiết lộ quy mô dữ liệu.

## 6. Sắp xếp ổn định: phân trang phải có thứ tự xác định

Một truy vấn chỉ `LIMIT/OFFSET` nhưng không `ORDER BY` không bảo đảm cùng một tập item trên mỗi trang. Ngay cả khi có `ORDER BY created_at`, nhiều item có cùng timestamp có thể đổi thứ tự tương đối.

Vì vậy một sort key nên là **duy nhất** hoặc được bổ sung tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

Ví dụ runnable dùng `ORDER BY id ASC` thông qua `PageRequest.of(page, 2, Sort.by("id").ascending())` vì ID duy nhất và dữ liệu demo tĩnh.

### 6.1. Offset pagination và dữ liệu đang đổi

Giả sử page 0 lấy IDs `[10, 9, 8]` theo thời gian giảm dần. Một record mới được thêm lên đầu trước khi client lấy page 1. Offset 3 có thể trả lại ID 8 hoặc bỏ sót item tùy biến động dữ liệu.

Đây là **pagination drift**, không phải lỗi riêng Spring Security. Các lựa chọn gồm snapshot isolation/cursor theo thời điểm, keyset pagination và thiết kế UI cho phép dữ liệu thay đổi.

### 6.2. Keyset/cursor pagination

Với thứ tự `created_at DESC, id DESC`, lần gọi tiếp theo có thể seek dựa trên cặp key của item cuối:

```sql
SELECT id, title, created_at
FROM reports
WHERE tenant_id = :tenant
  AND owner_username = :username
  AND (
    created_at < :last_created_at
    OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
```

Đây là SQL minh họa, cần xử lý giá trị cursor đầu tiên riêng. **Điều kiện quyền phải nằm trong mọi truy vấn cursor**, không chỉ ở trang đầu. Không cho client sửa tenant/owner bên trong cursor tùy ý. Cursor nên opaque, có integrity protection hoặc được kiểm tra với user/tenant/search/sort hiện tại.

### 6.3. Keyset không luôn thay thế Page

Keyset phù hợp khi “đi tiếp từ record cuối” hơn là “nhảy tới trang số 300”. Nếu UI thực sự cần random page, offset có thể hợp lý trong phạm vi và chi phí chấp nhận được. Không tối ưu bằng keyset trước khi hiểu giao diện, data distribution và index thực tế.

## 7. Tác động đến hiệu năng và tài nguyên hệ thống

### 7.1. Lượng dữ liệu di chuyển

Giả sử trong 1 triệu report, một user chỉ được xem 500 item. Cách lọc sai có thể đọc hàng nghìn/global pages để gom một trang, thậm chí quét toàn bộ nếu quyền phân bố thưa. Cách lọc query có thể dùng index để lấy trực tiếp item thỏa tenant/owner.

**Đây là ví dụ định tính**, không phải benchmark. Tốc độ thực phụ thuộc index, optimizer, query plan, cardinality, join và backend.

### 7.2. Index cho điều kiện quyền + thứ tự

Nếu truy vấn member có:

```sql
WHERE tenant_id = :tenant
  AND owner_username = :owner
ORDER BY id ASC
```

một index dạng:

```sql
CREATE INDEX idx_reports_tenant_owner_id
ON reports (tenant_id, owner_username, id);
```

có thể giúp DB tìm/tạo thứ tự trong tập user nhìn thấy. Với admin query chỉ theo tenant, index khác có thể hữu ích:

```sql
CREATE INDEX idx_reports_tenant_id
ON reports (tenant_id, id);
```

Không tự thêm mọi index vào production không đo lường: index tốn storage và chi phí ghi. Dùng `EXPLAIN`/query plan cùng dữ liệu gần thực tế để quyết định. Dữ liệu phân bố khác nhau giữa tenants có thể khiến cùng truy vấn có chi phí khác nhau.

### 7.3. COUNT có thể rất đắt

`COUNT(*)` có thể tốn thời gian khi predicate phức tạp, nhiều joins/ACL hoặc data volume rất lớn. Các giải pháp:

- `Slice` nếu UI chỉ cần “còn trang sau không?”.
- Tối ưu count query đúng điều kiện; tránh join không cần thiết.
- Chỉ expose total khi sản phẩm thật sự cần.
- Cache có kiểm soát, phân biệt user/tenant/policy/search và TTL hợp lý.
- Một số UI có thể chấp nhận ước tính, **nhưng phải ghi rõ đó là approximate count**; không trình bày như count chính xác.

### 7.4. N+1 khi lọc quyền từng row

Nếu Java gọi `permissionService.canRead(user, row)` và mỗi lời gọi tải một ACL hoặc nhóm từ DB, 20 item có thể tạo 20+ queries. Với pages lớn và nhiều users, N+1 làm p95 tăng mạnh.

Giải pháp thường là đưa quyền vào query qua `JOIN`/`EXISTS` hoặc đọc ACL theo **batch** với index phù hợp. Nếu permission logic thực sự cần từng row, hãy đo chi phí và đặt giới hạn số candidate đọc.

### 7.5. Projection DTO giảm băng thông

Danh sách chỉ cần ID và title nên query có thể tạo `ReportSummary(id,title)` trực tiếp, không cần load nội dung đầy đủ/tệp đính kèm/trường nhạy cảm:

```java
public record ReportSummary(Long id, String title) {}
```

Một projection đúng biên quyền giảm lượng dữ liệu đưa vào Java. Nhưng **projection không phải authorization**: query tạo DTO vẫn phải lọc tenant/owner/status và không trả metadata ngoài phạm vi.

## 8. @PostFilter và lọc sau khi đọc: khi nào phù hợp?

Spring Security method security có `@PostFilter` để lọc các phần tử từ collection/array hoặc các kiểu kết quả được implementation hỗ trợ sau khi method chạy. Cú pháp minh họa:

```java
// CHỈ MINH HỌA API cho một List nhỏ đã lấy từ service;
// không dùng làm pagination cho database lớn.
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<ReportRow> allRowsForSmallTest() {
    return tinyRepository.loadAllRows();
}
```

`filterObject` là phần tử đang được xét. Đoạn trên chỉ là mảnh ví dụ trong một class có `@EnableMethodSecurity`, `ReportRow` và repository phù hợp; **không phải file Java runnable độc lập**.

### 8.1. Khi @PostFilter có giá trị

Có thể hữu ích khi:

- Dataset rất nhỏ, bounded, đã được nạp vì lý do nghiệp vụ khác.
- Policy khó đưa vào một query và không có yêu cầu về page metadata.
- Đây là một lớp defense-in-depth bổ sung, không phải kiểm soát quyền duy nhất.
- Sự khác biệt giữa visibility và pagination đã được thiết kế rõ ràng, không trả `Page<T>` global có metadata sai.

### 8.2. Vì sao không dùng @PostFilter trực tiếp cho Page<T> một cách mù quáng?

`Page<T>` vừa chứa content vừa có metadata total, page, hasNext; các method-security filtering implementations **không nhất thiết hỗ trợ trực tiếp Page như một collection có thể mutate**, và kể cả lọc content được thì metadata đã được tính theo truy vấn cũ.

Nên **không giả định** rằng thêm một `@PostFilter` lên method trả `Page<ReportEntity>` tự giải quyết:

- số item mỗi trang;
- totalElements;
- totalPages;
- offset giữa các lần gọi;
- hasNext;
- dữ liệu nào đã được load trước filtering.

Phần demo thực tế dùng **repository query đã lọc**, trả `Page<ReportSummary>` và count query tương ứng.

### 8.3. Lọc sau đọc rồi phân trang trong bộ nhớ có lúc đúng không?

Nếu nguồn dữ liệu chỉ vài chục phần tử, có thể đọc toàn bộ, lọc theo policy, rồi thực hiện `skip/limit` sau khi lọc. Khi đó kết quả page có thể đúng về mặt tập hợp ở snapshot hiện tại, nhưng đó là giải pháp **không mở rộng**; không phù hợp khi dữ liệu lớn hoặc có PII không được phép đưa vào process.

Cần đánh giá chi phí/bảo mật, không phủ nhận hoàn toàn mọi in-memory filtering. Sai lầm cần tránh là **lọc sau khi đã lấy một page toàn cục**.

### 8.4. Hybrid: overfetch có kiểm soát

Khi policy phụ thuộc dịch vụ bên ngoài và không thể biểu diễn trong SQL, có thể chọn candidate prefilter theo tenant/status trong DB, lấy từng batch và kiểm tra quyền Java cho tới khi đủ item. Cần thiết kế:

1. Server-side prefilter tối thiểu, **không cho lộ tenant khác**.
2. Giới hạn số batch/candidates/time để chống DoS.
3. Cursor tiến lên theo candidate đã scan, không chỉ item được trả, tránh lặp vô hạn.
4. Cách tính `hasNext` xét cả những candidate chưa kiểm quyền.
5. Không tuyên bố `totalElements` chính xác nếu không thể count toàn bộ visible.
6. Audit và phân loại quyền thay đổi trong lúc đang fetch, cache/consistency đúng.
7. Không trả empty page như thể không còn tài nguyên nếu mới quét một batch toàn item denied.

Nếu sản phẩm yêu cầu offset page với tổng chính xác và policy không thể áp dụng ở database, đây là **bài toán kiến trúc thực sự**; cần cân nhắc materialized visibility, ACL index hoặc thay UX/API.

## 9. HTTP authorization và truy vấn danh sách phải bảo vệ hai lớp

Spring Security Servlet có `SecurityFilterChain` để xác thực và bảo vệ endpoint. Ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports").authenticated()
    .anyRequest().denyAll()
);
```

Rule trên chỉ đảm bảo caller không phải anonymous theo chính sách, **chưa hề lọc báo cáo theo owner/tenant**. Service/query phải thực thi chính sách resource-level.

Một luồng đúng:

```text
GET /api/reports?page=0
    |
    v
HTTP Basic filter xác thực principal
    |
    v
authorizeHttpRequests xác nhận request đã authenticated
    |
    v
ReportController
    |
    v
ReportService
    +-- tra trusted tenant scope từ backend
    +-- kiểm role TENANT_ADMIN từ Authentication
    +-- xây PageRequest(size=2, sort=id ASC)
    |
    v
ReportRepository query owner hoặc tenant
    +-- SELECT projection lọc đúng điều kiện quyền
    +-- COUNT với cùng điều kiện quyền
    |
    v
PageResponse chỉ chứa ID/title và visible metadata
```

Lưu ý: khi dùng nhiều `SecurityFilterChain`, `securityMatcher` xác định chain áp dụng cho request; `requestMatchers` xác định authorization rule **trong chain đã được chọn**. Đừng giả định một rule HTTP tự lọc dữ liệu trả về.

### 9.1. Danh tính và tenant không lấy từ query string

Một endpoint nhận:

```text
GET /api/reports?tenantId=t2&owner=admin
```

không nên đổi scope theo hai tham số đó chỉ vì user yêu cầu. Với tenant-scoped application, tenant membership phải được xác minh trong server-side identity/authorization context hoặc database. Tham số tenant do client đưa có thể được dùng làm **đối tượng yêu cầu chuyển tenant**, nhưng phải qua permission check trước khi áp dụng.

Trong ví dụ runnable, endpoint **không nhận** tenant/owner từ client: nó dùng `Authentication.getName()` và `TenantScope` server-side.

### 9.2. Admin cũng bị giới hạn tenant

Một `ROLE_TENANT_ADMIN` là quyền quản trị **trong tenant đã được cấp**, không tự có quyền trên mọi tenant. Nếu query admin chỉ có `WHERE tenant_id = :trustedTenant`, admin1 không thấy rows của tenant2.

Ngược lại, query admin kiểu `SELECT * FROM reports` chỉ vì role admin là lỗi data isolation nếu admin không có quyền toàn hệ thống.

### 9.3. Request được xác thực không bảo đảm session/role luôn mới

Trong sample, HTTP Basic xác thực mỗi request. Ứng dụng khác có session hoặc remember-me; role/tenant có thể stale nếu cấp quyền đã bị thu hồi. Cần chính sách revalidation/revocation phù hợp để bảo đảm query vẫn dựa trên scope còn hiệu lực. Giới hạn này khác bài toán pagination nhưng ảnh hưởng tính đúng đắn visibility.

## 10. Ứng dụng runnable Spring Boot 3.3.5 / Java 17 / JPA / H2

Ví dụ tạo một API danh sách báo cáo **đã lọc quyền ở database trước phân trang**. Để test đơn giản, dùng fixed page size **2**, sort theo ID tăng dần và dữ liệu seed cố định.

### 10.1. Ma trận dữ liệu

| ID | Tenant | Owner | Title |
| --- | --- | --- | --- |
| 1 | t1 | lan | Lan report A |
| 2 | t1 | minh | Minh report A |
| 3 | t1 | lan | Lan report B |
| 4 | t1 | lan | Lan report C |
| 5 | t1 | minh | Minh report B |
| 6 | t2 | binh | Binh report A |
| 7 | t2 | binh | Binh report B |
| 8 | t1 | lan | Lan report D |

User scope:

- `lan`: tenant `t1`, ROLE_USER → visible IDs `1,3,4,8`, total **4**, 2 trang size2.
- `minh`: tenant `t1`, ROLE_USER → visible IDs `2,5`, total **2**.
- `admin1`: tenant `t1`, ROLE_TENANT_ADMIN → visible IDs `1,2,3,4,5,8`, total **6**.
- `binh`: tenant `t2`, ROLE_USER → visible IDs `6,7`, total **2**.
- `admin2`: tenant `t2`, ROLE_TENANT_ADMIN → visible IDs `6,7`, total **2**.

Các test về page, count và tenant leakage sẽ dựa vào dữ liệu cố định này.

### 10.2. Cấu trúc dự án

```text
resource-pagination-security/
  pom.xml
  src/
    main/
      java/example/page/
        PageApplication.java
        SecurityConfig.java
        ReportEntity.java
        ReportSummary.java
        ReportRepository.java
        TenantScope.java
        ReportService.java
        PageResponse.java
        ReportController.java
        SeedData.java
      resources/
        application.properties
    test/
      java/example/page/
        ReportPaginationSecurityTest.java
```

### 10.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>resource-pagination-security</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.4. application.properties

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:pages;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` và H2 in-memory chỉ phù hợp **demo/test**. Production dùng migrations quản lý schema, DB phù hợp, credentials bí mật và connection pool được cấu hình. Tắt open-in-view giúp tránh dựa vào lazy-loading ngoài service khi serialize JSON.

### 10.5. PageApplication.java

```java
package example.page;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PageApplication {
    public static void main(String[] args) {
        SpringApplication.run(PageApplication.class, args);
    }
}
```

### 10.6. ReportEntity.java: dữ liệu có owner và tenant

```java
package example.page;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "reports")
public class ReportEntity {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected ReportEntity() {
    }

    public ReportEntity(Long id, String tenantId,
                        String ownerUsername, String title) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }
}
```

`id` trong demo được seed thủ công nên không dùng `@GeneratedValue`. Trong sản phẩm thật, chọn ID generator và constraints phù hợp, xác định tenant ID tin cậy, row-level permissions và trạng thái resource như deleted/archived.

### 10.7. ReportSummary.java: projection cho trang danh sách

```java
package example.page;

public record ReportSummary(Long id, String title) {
}
```

DTO chỉ expose ID và title. Nếu thêm owner, tenant hoặc nội dung nhạy cảm vào DTO, cần review policy; “đã lọc owner” không có nghĩa mọi field đều có thể tiết lộ.

### 10.8. ReportRepository.java: hai filtered queries và filtered count

```java
package example.page;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReportRepository
        extends JpaRepository<ReportEntity, Long> {

    @Query(
        value = """
            select new example.page.ReportSummary(r.id, r.title)
            from ReportEntity r
            where r.tenantId = :tenant
              and r.ownerUsername = :owner
            """,
        countQuery = """
            select count(r)
            from ReportEntity r
            where r.tenantId = :tenant
              and r.ownerUsername = :owner
            """
    )
    Page<ReportSummary> findOwnerPage(
        @Param("tenant") String tenant,
        @Param("owner") String owner,
        Pageable pageable
    );

    @Query(
        value = """
            select new example.page.ReportSummary(r.id, r.title)
            from ReportEntity r
            where r.tenantId = :tenant
            """,
        countQuery = """
            select count(r)
            from ReportEntity r
            where r.tenantId = :tenant
            """
    )
    Page<ReportSummary> findTenantPage(
        @Param("tenant") String tenant,
        Pageable pageable
    );
}
```

Giải thích:

- `findOwnerPage` dùng tenant **và** owner trong cả content query và count query.
- `findTenantPage` chỉ bỏ điều kiện owner khi caller đã được service xác nhận có role tenant admin; nó **vẫn giới hạn tenant**.
- JPQL `select new example.page.ReportSummary(...)` tạo DTO, tránh load nguyên entity trước khi mapping.
- `Pageable` được service truyền vào với fixed size và sort `id ASC`; Spring Data JPA áp pagination/sort cho query.
- `countQuery` là nguồn tổng số visible. Không dùng `repository.count()` toàn bảng cho metadata người dùng.
- Nếu thêm search `title`, trạng thái `isDeleted` hoặc policy nhóm, cần bổ sung cùng điều kiện vào **cả hai query**, không chỉ content query.

**Lưu ý phiên bản:** `select new ...` cho record sử dụng constructor chuẩn Java 17; Spring Data JPA/Hibernate version của Boot 3.3.x hỗ trợ constructor expressions. Khi chạy với provider khác hoặc đổi query/mapping, hãy xác minh query parsing và sorting bằng tests.

### 10.9. TenantScope.java: trusted tenant membership phía server

```java
package example.page;

import java.util.Map;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class TenantScope {

    private final Map<String, String> tenantByUsername = Map.of(
        "lan", "t1",
        "minh", "t1",
        "admin1", "t1",
        "binh", "t2",
        "admin2", "t2"
    );

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public String requireTenant(Authentication authentication) {
        if (authentication == null
                || !trust.isAuthenticated(authentication)) {
            throw new AccessDeniedException("Authentication required");
        }

        String tenant = tenantByUsername.get(authentication.getName());
        if (tenant == null) {
            throw new AccessDeniedException("Tenant membership required");
        }

        return tenant;
    }
}
```

Dữ liệu map cố định chỉ phục vụ demo; production cần nguồn tenant membership đáng tin như database/service identity đã được kiểm tra. Với người có nhiều tenant, chuyển tenant cần kiểm tra user có membership trong tenant được chọn, không tin ID do client tự gửi.

### 10.10. PageResponse.java: metadata chỉ của tập visible

```java
package example.page;

import java.util.List;

public record PageResponse(
    List<ReportSummary> items,
    int page,
    int size,
    long totalElements,
    int totalPages
) {
}
```

Không copy global count vào `totalElements`; danh sách item và metadata phải phản ánh **cùng tập visible**. Với `Slice`, có thể thay bằng `hasNext` và bỏ total nếu sản phẩm không cần count.

### 10.11. ReportService.java: đặt chính sách trước Pageable

```java
package example.page;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    private final ReportRepository repository;
    private final TenantScope tenantScope;

    public ReportService(ReportRepository repository,
                         TenantScope tenantScope) {
        this.repository = repository;
        this.tenantScope = tenantScope;
    }

    public PageResponse listVisible(
            Authentication authentication, int page) {

        // Demo fixed size=2 và chặn offset quá lớn.
        if (page < 0 || page > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid page");
        }

        String tenant = tenantScope.requireTenant(authentication);
        String username = authentication.getName();

        boolean tenantAdmin = authentication.getAuthorities().stream()
            .anyMatch(a ->
                "ROLE_TENANT_ADMIN".equals(a.getAuthority()));

        Pageable pageable = PageRequest.of(
            page, 2, Sort.by(Sort.Direction.ASC, "id"));

        Page<ReportSummary> visible = tenantAdmin
            ? repository.findTenantPage(tenant, pageable)
            : repository.findOwnerPage(tenant, username, pageable);

        return new PageResponse(
            visible.getContent(),
            visible.getNumber(),
            visible.getSize(),
            visible.getTotalElements(),
            visible.getTotalPages()
        );
    }
}
```

**Quy trình đáng tin:** tên principal từ `Authentication`, tenant từ `TenantScope` phía server, quyền admin từ authorities do authentication provider cấp. Chỉ sau khi xây được scope và xác định query thích hợp, service mới lấy `Page<ReportSummary>` đã lọc trong repository.

`PageRequest.of(page, 2, Sort.by("id"))` tạo sort ổn định. Giới hạn page demo `<=1000` không phải con số chuẩn cho mọi sản phẩm; production nên cấu hình page/size bounds và cân nhắc keyset cho deep pagination.

### 10.12. ReportController.java: client không được chọn owner/tenant

```java
package example.page;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/reports")
    public PageResponse list(
            @RequestParam(defaultValue = "0") int page,
            Authentication authentication) {

        return reports.listVisible(authentication, page);
    }
}
```

Client chỉ điều khiển `page` trong giới hạn; ngay cả khi gửi `?tenantId=t2&owner=admin2`, các giá trị đó không tham gia truy vấn. Trong ứng dụng có multi-tenant switch, cần bổ sung explicit authorized tenant selection.

### 10.13. SecurityConfig.java: HTTP Basic và rule authenticated

```java
package example.page;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo")).roles("USER").build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo")).roles("USER").build();

        UserDetails admin1 = User.withUsername("admin1")
            .password(encoder.encode("admin1-demo"))
            .roles("TENANT_ADMIN").build();

        UserDetails binh = User.withUsername("binh")
            .password(encoder.encode("binh-demo")).roles("USER").build();

        UserDetails admin2 = User.withUsername("admin2")
            .password(encoder.encode("admin2-demo"))
            .roles("TENANT_ADMIN").build();

        return new InMemoryUserDetailsManager(
            lan, minh, admin1, binh, admin2);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(sc -> sc
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(rc -> rc
                .requestCache(new NullRequestCache()));

        // Demo chỉ có GET. Không mặc nhiên tắt CSRF cho endpoint ghi.
        return http.build();
    }
}
```

`SessionCreationPolicy.STATELESS` thể hiện mỗi request Basic được xử lý không dựa vào một HTTP session đã đăng nhập. `NullSecurityContextRepository` không lưu authentication context sang session; `NullRequestCache` không lưu URL cũ cho form redirect.

`CSRF` mặc định chưa bị tắt. Nếu thêm POST/PUT/DELETE, cần đánh giá CSRF theo client/browser và cơ chế credential thực tế; đừng coi “API stateless” là lý do tự động bỏ mọi CSRF protection.

### 10.14. SeedData.java: dữ liệu deterministic

```java
package example.page;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner seedReports(ReportRepository repository) {
        return args -> repository.saveAll(List.of(
            new ReportEntity(1L, "t1", "lan", "Lan report A"),
            new ReportEntity(2L, "t1", "minh", "Minh report A"),
            new ReportEntity(3L, "t1", "lan", "Lan report B"),
            new ReportEntity(4L, "t1", "lan", "Lan report C"),
            new ReportEntity(5L, "t1", "minh", "Minh report B"),
            new ReportEntity(6L, "t2", "binh", "Binh report A"),
            new ReportEntity(7L, "t2", "binh", "Binh report B"),
            new ReportEntity(8L, "t1", "lan", "Lan report D")
        ));
    }
}
```

Dữ liệu có ID cố định và không có test mutation, nên có thể dự đoán chính xác trang 0, trang 1 và count. Với production phải dùng migrations/seeding có version, không mặc định ghi dữ liệu mỗi lần app start.

### 10.15. JUnit 5 / MockMvc integration tests

File `src/test/java/example/page/ReportPaginationSecurityTest.java`:

```java
package example.page;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportPaginationSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotListReports() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lanPageZeroContainsTwoOwnedItemsAndScopedTotal()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(3))
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.totalElements").value(4))
            .andExpect(jsonPath("$.totalPages").value(2));
    }

    @Test
    void lanPageOneContainsRemainingOwnedItems() throws Exception {
        mvc.perform(get("/api/reports").param("page", "1")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].id").value(4))
            .andExpect(jsonPath("$.items[1].id").value(8))
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void minhSeesOnlyHisTwoReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(2))
            .andExpect(jsonPath("$.items[1].id").value(5))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void tenantOneAdminSeesSixTenantOneReports()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin1", "admin1-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(2))
            .andExpect(jsonPath("$.totalElements").value(6))
            .andExpect(jsonPath("$.totalPages").value(3));
    }

    @Test
    void tenantOneAdminThirdPageNeverContainsTenantTwo()
            throws Exception {
        mvc.perform(get("/api/reports").param("page", "2")
                .with(httpBasic("admin1", "admin1-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(5))
            .andExpect(jsonPath("$.items[1].id").value(8))
            .andExpect(jsonPath("$.totalElements").value(6));
    }

    @Test
    void tenantTwoAdminSeesOnlyTenantTwo() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin2", "admin2-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(6))
            .andExpect(jsonPath("$.items[1].id").value(7))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void tenantTwoMemberSeesOnlyOwnedReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("binh", "binh-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(6))
            .andExpect(jsonPath("$.items[1].id").value(7))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void cannotOverrideServerTenantUsingQueryParameters()
            throws Exception {
        mvc.perform(get("/api/reports")
                .param("tenantId", "t2")
                .param("owner", "admin2")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(3))
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void clientCannotInflateFixedPageSize() throws Exception {
        mvc.perform(get("/api/reports")
                .param("size", "100000")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.items.length()").value(2));
    }

    @Test
    void outOfRangePageIsEmptyButTotalRemainsScoped()
            throws Exception {
        mvc.perform(get("/api/reports").param("page", "9")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items").isEmpty())
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void negativePageIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "-1")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void excessivePageIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "1001")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPageTypeIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "abc")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownRouteIsDeniedEvenWithValidCredentials()
            throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }
}
```

**Các kiểm thử quan trọng:**

- Không có/sai Basic credentials → 401, chứng minh authentication mechanism hoạt động.
- `lan` chỉ thấy 4 report ở **đúng 2 trang**; page0 có 2 item, page1 có 2 item.
- `admin1` thấy 6 report tenant1, không thấy các ID 6/7 tenant2; `admin2` chỉ thấy tenant2.
- Query parameters `tenantId=t2&owner=admin2` **không thể thay đổi** server-side scope của Lan.
- `size=100000` không thể làm tăng kích thước trang do controller dùng fixed page size.
- Page vượt quá total vẫn trả empty content nhưng total **của user** không đổi.
- Page âm/quá lớn/không phải số được từ chối 400.
- URL ngoài phạm vi bị deny dù đã có credentials.

### 10.16. Lệnh chạy

Trong thư mục dự án `resource-pagination-security` với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

**Mười sáu bài kiểm thử được thiết kế để pass** với dependency và cấu hình ở trên. Đây là kiểm tra source và kết quả **dự kiến**, không phải khẳng định đã thực thi Maven trong môi trường của người đọc.

Thử API local (chỉ dùng tài khoản giả lập):

```bash
curl -i http://localhost:8080/api/reports
curl -i -u lan:lan-demo "http://localhost:8080/api/reports?page=0"
curl -i -u lan:lan-demo "http://localhost:8080/api/reports?page=1"
curl -i -u admin1:admin1-demo "http://localhost:8080/api/reports?page=2"
curl -i -u admin2:admin2-demo "http://localhost:8080/api/reports"
```

`curl -u` có thể lộ mật khẩu ở lịch sử shell hoặc process listing; không dùng lệnh kiểu này với secret thật. HTTP Basic yêu cầu **HTTPS** trong production; Base64 không phải mã hóa vận chuyển.

Một JSON ví dụ cho Lan, page0:

```json
{
  "items": [
    {"id": 1, "title": "Lan report A"},
    {"id": 3, "title": "Lan report B"}
  ],
  "page": 0,
  "size": 2,
  "totalElements": 4,
  "totalPages": 2
}
```

Cả mảng và total đều được tạo từ **query đã lọc tenant + owner**, không dùng `repository.findAll(pageable)` và không lấy global count.

## 11. Java 17 độc lập: chứng minh lỗi lọc sau pagination

Nếu chưa cài Spring Boot, có thể chạy chương trình Java 17 sau để thấy kết quả bằng những phép toán đơn giản. Chương trình chỉ mô phỏng list + filter + pagination, không thực thi SQL hoặc method security.

Tạo file `PaginationFilteringDemo.java`:

```java
import java.util.List;

public class PaginationFilteringDemo {

    record Report(int id, String owner) {}

    static List<Integer> visibleIds(List<Report> data, String user) {
        return data.stream()
            .filter(report -> report.owner().equals(user))
            .map(Report::id)
            .toList();
    }

    public static void main(String[] args) {
        List<Report> all = List.of(
            new Report(1, "minh"),
            new Report(2, "minh"),
            new Report(3, "lan"),
            new Report(4, "minh"),
            new Report(5, "lan"),
            new Report(6, "minh"),
            new Report(7, "lan"),
            new Report(8, "lan")
        );

        int pageSize = 3;

        // SAI: lấy một global page rồi mới lọc.
        List<Report> globalPageZero = all.subList(0, pageSize);
        System.out.println("global page 0, then filter: " +
            visibleIds(globalPageZero, "lan"));

        // ĐÚNG về phép toán: lọc toàn bộ trước khi chia trang.
        // DB thực tế nên thực hiện filter trước LIMIT/OFFSET.
        List<Integer> scoped = visibleIds(all, "lan");

        System.out.println("filtered first page: " +
            scoped.subList(0, pageSize));
        System.out.println("filtered second page: " +
            scoped.subList(pageSize, scoped.size()));
        System.out.println("visible total: " + scoped.size());
    }
}
```

Biên dịch/chạy trên Java 17:

```bash
javac PaginationFilteringDemo.java
java PaginationFilteringDemo
```

Stdout **chính xác**:

```text
global page 0, then filter: [3]
filtered first page: [3, 5, 7]
filtered second page: [8]
visible total: 4
```

Bài học của demo: thứ tự hai phép toán **không giao hoán**:

```text
filter(page(globalData))  !=  page(filter(globalData))
```

Java code này duyệt toàn bộ list nhỏ để dễ nhìn. Với dữ liệu lớn, cần chuyển điều kiện filter vào DB query, không dùng `stream().filter` trên tất cả bản ghi thật để thay thế.

## 12. Count/metadata cũng là dữ liệu nhạy cảm

Đôi khi API không trả một row nào bị cấm nhưng vẫn tiết lộ:

- Tổng số báo cáo của cả tenant dù user chỉ được xem của mình.
- Số khách hàng/đơn hàng của tenant khác qua `totalElements`.
- `hasNext` dựa trên global dataset, cho thấy có item mà user không được xem ở trang sau.
- Mức tăng giảm số lượng report qua timestamp/ETag/cache key.
- ID không thuộc scope qua phản hồi khác nhau giữa 403, 404 và empty list.

Vì thế data minimization không kết thúc ở `content`. **Pagination metadata phải theo cùng quyền truy cập**. Nếu không cần count, tốt hơn không trả count thay vì đưa ra một con số toàn cục.

### 12.1. 403 và 404 ở detail endpoint

Một API `GET /api/reports/{id}` có thể chọn trả 404 cho cả “không tồn tại” và “không có quyền” để hạn chế enumeration. Cơ chế này là một quyết định thiết kế threat model; không tự dùng query list đã lọc rồi khẳng định mọi 404 đã an toàn. Chi tiết resource access cần kiểm tra owner/tenant với cùng policy và không lộ dữ liệu qua timing/metadata ngoài ý định.

### 12.2. Ngăn cache phản hồi chéo user

Nếu response `/api/reports?page=0` được cache theo URL nhưng không xét principal/tenant, request của user B có thể nhận page/total của user A. Trong Spring Security resource list, mọi lớp cache (HTTP reverse proxy, CDN, service, DB query cache, application cache) phải có policy và key đúng.

Ví dụ cache key khái niệm:

```text
tenantId | principalId | role/policyVersion | page | size | sort | filters
```

Ngay cả key này cũng chưa đầy đủ cho mọi nghiệp vụ. Với dữ liệu nhạy cảm, cân nhắc `Cache-Control: private/no-store` theo yêu cầu; không đưa raw credentials/cookie/session IDs vào cache keys hoặc logs.

## 13. Khi permissions phức tạp: ACL, nhóm, role theo resource

Owner-only là một policy đơn giản. Thực tế có thể có:

- Report chia sẻ cho nhóm A; user thuộc nhiều nhóm.
- Role `EDITOR` chỉ trên project X.
- Tenant admin được quyền xem, nhưng không export.
- ACL grant theo report ID, action, principal/group.
- Report bị khóa, hết hiệu lực hoặc soft-deleted.
- Quyền tạm thời theo lịch/đợt review.
- Policy ABAC theo trạng thái account, purpose, location hoặc service-level constraints.

Nếu visibility cần quan hệ many-to-many, có thể đưa quyền vào query:

```sql
SELECT r.id, r.title
FROM reports r
WHERE r.tenant_id = :trusted_tenant
  AND r.deleted = FALSE
  AND (
    r.owner_username = :username
    OR EXISTS (
      SELECT 1
      FROM report_grants g
      WHERE g.report_id = r.id
        AND g.grantee_username = :username
        AND g.permission = 'READ'
    )
  )
ORDER BY r.id ASC
LIMIT :limit OFFSET :offset;
```

Đây là SQL minh họa. `EXISTS` có thể tránh nhân bản rows nếu một user có nhiều grants, giúp count/partition dễ nhất quán. Cần index theo các khóa join/permission; không sử dụng string username làm khóa an toàn duy nhất trong sản phẩm thật nếu identity có thể đổi.

### 13.1. Quyền thay đổi phải được phản ánh ở query và count

Nếu một grant bị revoke giữa lần gọi page0 và page1, hai request có thể nhìn thấy tập khác nhau. Cần xem requirements:

- Dữ liệu giao diện thông thường có thể chấp nhận snapshot thay đổi.
- Audit/export tài chính có thể cần snapshot nhất quán hoặc job cố định quyền tại thời điểm được ủy quyền.
- Cache quyền phải có invalidation/TTL thỏa yêu cầu revocation.
- Không dùng “last known permit” dài hạn cho dữ liệu nhạy cảm khi policy yêu cầu revoke gần tức thời.

### 13.2. Row-level security (RLS) như lớp phòng vệ

Một số DB hỗ trợ row-level security để áp visibility sát dữ liệu. RLS có thể giảm rủi ro nếu ứng dụng quên predicate, nhưng phải cấu hình **trusted session context/DB role**, connection pool hygiene và tests để tránh tenant context của request trước rò sang request sau.

RLS không thay thế HTTP authentication và không giải quyết tự động pagination order, count cost hoặc object-level business actions. Có thể coi nó là **defense in depth** bên cạnh query/service policy.

### 13.3. Materialized visibility và search index

Khi chính sách quyền quá phức tạp cho mỗi query, hệ thống lớn có thể xây bảng/report search index đã gắn principal/group/tenant permissions. Nhưng visibility index cần cập nhật khi grant/revoke, chuyển owner, đổi nhóm. Nếu index stale, list có thể lộ item bị thu hồi.

Kiểm tra độ trễ nhất quán, audit, rebuild strategy và policy “fail closed nếu index thiếu/cũ” trước khi dùng cách này cho dữ liệu rủi ro cao.

## 14. Lọc tìm kiếm và sắp xếp do client chọn

### 14.1. Search filter phải gắn cùng scope

Endpoint:

```text
GET /api/reports?query=finance&page=0
```

không nên tìm toàn bộ hệ thống theo keyword rồi lọc tenant/owner sau khi phân trang. Predicate đúng gồm:

```sql
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_username
  AND lower(title) LIKE :trusted_escaped_keyword
```

`query` là input không đáng tin, cần escape wildcard/độ dài, dùng bind parameters và kiểm soát query cost. Count query phải dùng cùng keyword + tenant/owner. Với full-text search, index hoặc search service phải bảo đảm permission filter được thực thi trước khi trả kết quả và metadata.

### 14.2. Sort whitelist

Không nhận nguyên tên cột SQL từ query `?sort=...` rồi nối thẳng vào statement. Dùng whitelist các sort keys hợp lệ như `id`, `createdAt`, `title`; có giới hạn số sort keys, chiều sort và tie-breaker ID.

Nếu sort theo field nhạy cảm không được phép hiển thị, kết quả thứ tự vẫn có thể tiết lộ thông tin; cần xét threat model.

### 14.3. Page size bounds

Một API cho `size=10000000` có thể tạo truy vấn nặng và response lớn. Giới hạn size (ví dụ 20–100 tùy mục đích), hạn chế offset và rate limit. Trong sample giữ size=2 cố định để dễ chứng minh, không nên áp dụng literal 2 cho mọi sản phẩm.

### 14.4. Tổng số không bảo đảm snapshot xuyên request

Content query và count query thường là hai thao tác DB. Với concurrent inserts/deletes, tổng số có thể thay đổi giữa chúng, tùy isolation và transaction. Nếu cần consistency nghiêm ngặt, xem transaction isolation, snapshot và dữ liệu versioned; không tuyên bố `Page` tự bảo đảm read snapshot bất biến trong mọi DB.

## 15. Chiến lược kiểm thử đúng đắn và hiệu năng

### 15.1. Ma trận phân quyền

Ít nhất phải test:

| Tình huống | Nội dung | Metadata |
| --- | --- | --- |
| Anonymous | Không vào endpoint protected | Không trả count |
| Authenticated user A | Chỉ rows A có quyền | Total chỉ rows A |
| User B cùng tenant | Không thấy rows A | Total chỉ rows B |
| Tenant admin | Chỉ scope tenant được cấp | Total chỉ rows tenant |
| Admin tenant khác | Không nhìn sang tenant A | Không lộ total tenant A |
| Client sửa `tenantId/owner` | Không thay đổi scope | Không thay đổi total |
| Page sau cùng | Không lặp/mất item với dữ liệu tĩnh | total/hasNext phù hợp |
| Page vượt cuối | Empty content | Total vẫn là visible total |
| Page âm/quá lớn | 400 | Không chạy query vô hạn |
| New/soft-deleted row | Query/count cùng policy | Không leak qua metadata |

### 15.2. Test thứ tự lọc và boundary

Đặc biệt tạo dữ liệu **xen kẽ owner** trong cùng tenant như ID 1 Lan, 2 Minh, 3 Lan... Nếu test chỉ có một user và các ID liền nhau, implementation sai “global page rồi filter” vẫn có thể cho kết quả đúng tình cờ. Test Lan page0/page1 cùng tổng 4 sẽ phát hiện lỗi.

### 15.3. Query count và index cần được đo

Các công cụ thường dùng:

- SQL logging phát triển có kiểm soát để xem predicates và ORDER BY.
- `EXPLAIN`/`EXPLAIN ANALYZE` trên DB mục tiêu để xem index scan, rows examined và sort.
- p95/p99 latency phân biệt content query và count query.
- Query count per API call nhằm phát hiện N+1.
- Heap/GC và response size khi thử page size lớn.
- Load test với dữ liệu có phân bố tenant/permissions giống production.

**Không dùng H2 in-memory làm benchmark đại diện cho PostgreSQL/MySQL/Oracle.** Nó minh họa hành vi query/pagination, còn performance cần đo bằng đúng DB/dialect và dữ liệu thực tế đã ẩn danh.

### 15.4. Regression khi thêm filter

Sau khi thêm `status` hoặc `query`:

1. Test mỗi filter kết hợp với owner/tenant.
2. Test count query cập nhật đồng thời.
3. Test sort tie-breaker và page boundary.
4. Test query parameter không trở thành nguồn chứng minh quyền.
5. Test deny khi user bị revoke hoặc tenant scope đổi.
6. Test dữ liệu có JOIN gây duplicate và count distinct.
7. Test data cache/search index không trả rows/metadata của principal trước.

## 16. Lỗi phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| `findAll(pageable)` rồi `filter(canRead)` | Trang thiếu item, total/hasNext sai | Filter trong DB trước page |
| Trả `Page.getTotalElements()` từ global query | Lộ số lượng record của người khác | Count theo scope user/tenant |
| Dùng `allowed.size()` của một page làm total | Sai total của tập visible | Count filtered query hoặc bỏ total |
| `@PostFilter` trên `Page<T>` và tin metadata tự sửa | Page semantics sai/implementation không hỗ trợ | Query-filter hoặc API riêng không total |
| Lọc đủ ở content query nhưng count query rộng | Metadata leak và sai pages | Dùng cùng predicate cho content/count |
| Member query thiếu tenant | Cross-tenant leak nếu trùng username/owner | Luôn ràng tenant |
| Tenant admin query không WHERE tenant | Admin tenant A đọc được tenant B | Dùng trusted tenant scope |
| Tin `?tenantId=t2&owner=admin` | User tự chọn scope/leo quyền | Server xác minh identity/tenant/permission |
| `Page.map` trả null để che item | Content có null, count sai | Chỉ map projection của page đã authorized |
| Không `ORDER BY` | Trang có thể đổi thứ tự | Sort ổn định với unique tie-breaker |
| Sort theo timestamp không có ID | Rows cùng thời gian lặp/mất | `ORDER BY created_at, id` |
| Deep offset không giới hạn | Truy vấn chậm/DoS | Bounds, rate limit, keyset khi phù hợp |
| Cho client tăng size vô hạn | Nặng DB/mạng/heap | Max page size |
| Dùng `Slice` trên global data rồi filter | `hasNext` không phản ánh visible data | Filter trước Slice |
| Gọi permission DB từng row | N+1 queries | JOIN/EXISTS, batch ACL, cache đúng scope |
| Query không dùng projection | Load PII/tệp lớn không cần | Chỉ lấy cột danh sách |
| Dùng `OR isAdmin` với boolean từ header | Dễ leo quyền | Role từ Authentication và scope server |
| Khi dùng ACL JOIN, count thẳng rows | Duplicate resources và sai total | `EXISTS` hoặc `count(distinct ...)` |
| Chỉ bảo vệ list, detail không có owner check | BOLA qua ID trực tiếp | Cùng policy trong detail/service |
| Cache theo URL, bỏ principal/tenant | Cross-user data leak | Scoped private cache/key, no-store khi cần |
| Giả định count và content luôn cùng snapshot | Sai khi concurrent writes | Cân nhắc transaction/snapshot |
| Query sai khi soft-deleted/archived | Lộ status/ID nhạy cảm | Áp status predicate cho query/count |
| Quên revoke/cached permission | Hiển thị item không còn quyền | Invalidation/policy version |
| Test chỉ với một owner | Không phát hiện lọc sau page | Seed dữ liệu xen kẽ nhiều owner |
| Dùng H2 để kết luận index production tối ưu | Sai kế hoạch truy vấn DB khác | EXPLAIN trên DB đích |
| Xóa CSRF vì API stateless | Client browser vẫn có thể auto-send credentials | Đánh giá CSRF theo threat model |

## 17. Quy trình debug khi pagination có dữ liệu sai

1. **Đúng SecurityFilterChain?** Xem `securityMatcher` và `@Order` nếu nhiều chain; request có authenticated thật không?
2. **Scope user từ đâu?** `Authentication.getName()` và trusted tenant membership có đúng?
3. **Policy role nào?** Tenant admin chỉ admin trong tenant, không phải admin global.
4. **Query nào được gọi?** `findOwnerPage` hay `findTenantPage`, predicate có ràng tenant?
5. **WHERE áp trước OFFSET?** Có dùng `repo.findAll(pageable).getContent().filter(...)` trong service không?
6. **COUNT query nào?** Có giống content WHERE, status/search/joins không?
7. **Sort ổn định?** Có tie-breaker ID, đúng chiều sắp xếp, row đang được cập nhật?
8. **Page size/offset?** Có guard input âm, oversized, overflow không?
9. **Metadata có lộ dữ liệu?** totalElements/totalPages/hasNext có dựa trên global dataset không?
10. **DTO đang expose gì?** Có đưa owner/tenant/private fields ra JSON khi không cần?
11. **Có N+1 permission check?** Repository hoặc permission evaluator có query cho từng row?
12. **JOIN gây trùng row?** Có dùng `DISTINCT`/`EXISTS` và count tương ứng?
13. **Có cache stale?** URL-only cache hoặc cache principal/tenant chưa invalidated?
14. **Có quyền thay đổi giữa hai trang?** Snapshot drift, revoke hoặc data mutation.
15. **Query có lộ qua error/log?** Không in credentials, session IDs hoặc dữ liệu PII.
16. **Khi dùng @PostFilter**, return type có thực sự hỗ trợ lọc và metadata đã đúng không?
17. **Nếu user thấy trang rỗng nhưng còn tài nguyên**, kiểm tra có đang lọc sau global page hay không.
18. **Nếu count quá chậm**, cân nhắc Slice/keyset, index và query plan trên DB thật.

Có thể bật SQL/debug trong môi trường thử nghiệm có kiểm soát, nhưng không log bind parameters chứa dữ liệu riêng tư hay toàn bộ report payload. Một test có dữ liệu xen kẽ tenant/owner thường làm rõ lỗi nhanh hơn đọc log dài.

## 18. Câu hỏi luyện tập kèm đáp án

**1.** Database có 100 row, user nhìn thấy 8 row. Lấy global page size20 rồi lọc Java có đảm bảo page đầu trả đủ 8 item không?

**Đáp án:** Không. 8 row visible có thể nằm ngoài 20 row global đầu tiên. Cần áp visibility filter trước pagination.

**2.** Sau lọc một global page còn 3 items, có thể đặt `totalElements=3` không?

**Đáp án:** Không, đó chỉ là số item còn lại trong **page hiện tại**, không phải total visible toàn tập.

**3.** `Page.map(...)` có tái tính total khi map entity thành null để che resource không?

**Đáp án:** Không. Mapping không thay thế quyền resource-level hay việc lọc trước page.

**4.** Vì sao `countQuery` phải có tenant/owner/search predicate giống content query?

**Đáp án:** Để metadata `totalElements/totalPages` đúng tập visible, không leak global counts hoặc số lượng resource tenant khác.

**5.** `Slice` có loại bỏ nhu cầu security filter trong database không?

**Đáp án:** Không. Nó chỉ tránh total count theo API; `hasNext` và slice boundary vẫn phải xác định trên tập được phép xem.

**6.** Một user đổi query `?tenantId=otherTenant`. Server nên tin tham số đó không?

**Đáp án:** Không. Nếu hỗ trợ chọn tenant, server phải kiểm tra membership/authorization trước; sample lấy tenant từ trusted scope.

**7.** Tenant admin có ROLE_TENANT_ADMIN. Có được bỏ WHERE tenantId khi query không?

**Đáp án:** Không nếu đó là quản trị **theo tenant**. Role không đồng nghĩa quyền xuyên mọi tenant.

**8.** Sort chỉ theo `createdAt DESC`, nhiều row có cùng timestamp. Có rủi ro nào?

**Đáp án:** Thứ tự không xác định giữa các row trùng timestamp gây lặp/mất item khi đi trang. Thêm unique tie-breaker như ID.

**9.** `@PostFilter` trên một List nhỏ có thể hữu ích trong trường hợp nào?

**Đáp án:** Khi dữ liệu bounded, đã được lấy hợp lệ và không cần đúng metadata Page; vẫn phải cân nhắc PII, performance và defense in depth.

**10.** Khi nào nên ưu tiên keyset/cursor?

**Đáp án:** Feed/list lớn cần next page, deep offset quá chậm, sort key ổn định. Mọi cursor query vẫn phải mang visibility predicates và cursor không được giả mạo scope.

**11.** Query ACL JOIN trả mỗi report nhiều row do nhiều grants; dùng `count(*)` trực tiếp có thể sai thế nào?

**Đáp án:** Count có thể tăng theo số grants thay vì số report duy nhất. Dùng EXISTS hoặc count distinct tương ứng.

**12.** User được HTTP rule `authenticated()`. Điều đó có đủ để đọc bất kỳ báo cáo nào trong database không?

**Đáp án:** Không. HTTP authentication chỉ là một bước, còn owner/tenant/action phải được xác minh ở query/service.

**13.** Test của Lan page0/1 vì sao nên có dữ liệu Minh xen kẽ?

**Đáp án:** Nó làm lộ lỗi lọc sau global pagination vốn có thể ẩn khi mọi row cùng owner nằm liền nhau.

**14.** Vì sao page count có thể khác content ngay cả khi SQL predicates đúng?

**Đáp án:** Dữ liệu có thể thay đổi giữa count/content queries do transaction isolation và concurrent writes; cần snapshot policy nếu độ nhất quán nghiêm ngặt.

**15.** Cache `/api/reports?page=0` chung cho mọi user có rủi ro gì?

**Đáp án:** Có thể trả item/metadata của user hoặc tenant khác. Cache phải partition theo principal/tenant/policy hoặc bị vô hiệu hóa với dữ liệu nhạy cảm.

## 19. Checklist trước khi triển khai

### Data access và policy

- [ ] Đã xác định trusted tenant, principal, role và visibility predicate.
- [ ] Content query áp predicate trước `ORDER BY + LIMIT/OFFSET` hoặc keyset seek.
- [ ] Count query dùng cùng predicate tenant/owner/status/search.
- [ ] Không dùng global `findAll(pageable)` rồi filter per-row cho protected list.
- [ ] Có kiểm tra resource-level cho detail/update/delete, không chỉ danh sách.
- [ ] DTO chỉ chứa field cần hiển thị, không load/expose payload nhạy cảm vô ích.
- [ ] Cơ chế revoke/cached permissions đáp ứng yêu cầu consistency.

### Pagination và hiệu năng

- [ ] Page size/offset có guard và rate limit.
- [ ] Sort có unique tie-breaker; test thêm row/xóa row/đổi quyền giữa các trang.
- [ ] Đã cân nhắc Page vs Slice vs cursor theo yêu cầu UI.
- [ ] Có EXPLAIN/metrics trên đúng DB và data distribution sản xuất.
- [ ] Không có N+1 permission queries.
- [ ] Index phù hợp với tenant, owner, trạng thái và sort.
- [ ] Metadata trả đúng visible scope hoặc được lược bỏ có chủ đích.

### Bảo mật và kiểm thử

- [ ] Test anonymous, owner, non-owner, tenant admin, cross-tenant admin.
- [ ] Test query params giả mạo tenant/owner bị bỏ qua hoặc từ chối.
- [ ] Test ID xen kẽ để bắt lọc sau page.
- [ ] Test count/totalPages/hasNext không leak.
- [ ] Test page âm, page quá lớn, size vượt cap và sort không hợp lệ.
- [ ] Test CSRF, HTTPS, auth mechanisms khi có endpoint mutation.
- [ ] Cache/proxy/log/audit không chứa credential hoặc cross-user result.
- [ ] Không dùng H2 performance test làm kết luận cho DB production.

## 20. Tóm tắt trọng tâm

- **Lọc quyền trước phân trang**: `WHERE tenant/owner/ACL` phải được áp trước `LIMIT/OFFSET` hoặc seek cursor khi chính sách có thể đưa vào query.
- **Không phân trang global rồi mới lọc Java**: cách này tạo trang thiếu item, làm sai `totalElements/totalPages/hasNext` và có nguy cơ lộ metadata.
- `Page<T>` có count metadata cần cùng scope với content query; `Slice<T>` bỏ tổng count nhưng vẫn yêu cầu visibility filter trước boundary.
- `@PostFilter`/`Stream.filter` có thể hữu ích với collection nhỏ, nhưng không thay thế phân trang đúng ở database cho danh sách lớn, và không nên giả định xử lý trực tiếp `Page<T>` đúng.
- **Tenant và owner lấy từ nguồn đáng tin**, không từ query/header tự khai; tenant admin vẫn phải được ràng tenant.
- Chọn projection DTO, sort ổn định, index phù hợp, hạn chế page size/offset, tránh N+1 và đánh giá keyset cho deep pagination.
- **Count, hasNext, cache keys, sort order và JSON metadata cũng là bề mặt bảo mật**, không chỉ từng item trả về.
- Kiểm thử bằng dữ liệu owner xen kẽ, so sánh page0/page1/tổng số, và xác minh 200/401/403 để bảo đảm cả HTTP auth lẫn data access policy đang làm đúng công việc.
