# Phạm vi quyền cho tìm kiếm, đếm, phân trang và thống kê trong Spring Security

## 1. Vấn đề: không trả bản ghi trái quyền chưa đủ

Giả sử Alice thuộc tenant ALPHA, có quyền `DOC_READ` và được xem những tài liệu do mình sở hữu hoặc được công khai cho nhóm nội bộ. API tìm kiếm trả đúng hai tài liệu của Alice, nhưng trường `totalElements` lại đếm toàn bộ tài liệu của công ty, facet `status` tính cả tài liệu bí mật, hoặc dashboard hiển thị doanh thu từ khách hàng không thuộc tenant của Alice. Dù phần tử trong `content` đã được lọc, hệ thống **vẫn làm lộ thông tin qua số lượng và thống kê**.

Trong Spring Security, `@PreAuthorize("hasAuthority('DOC_READ')")` kiểm tra caller **có được gọi chức năng** hay không. Nó **không tự thêm điều kiện WHERE** để chỉ chọn những bản ghi caller được phép xem. Một hệ thống bảo mật danh sách dữ liệu phải kiểm soát **tập tài nguyên được phép nhìn thấy**, rồi áp dụng tìm kiếm/đếm/phân trang/thống kê trên tập đó.

Cần phân biệt:

- **Function-level authorization:** người dùng có quyền gọi API tìm kiếm/đếm/báo cáo không?
- **Object-/row-level authorization:** trong các document, invoice, order hoặc user records, bản ghi nào thuộc phạm vi xem được?
- **Property-level authorization:** trên một bản ghi đã được phép xem, field nào được trả về? Ví dụ được thấy tên đơn hàng nhưng không được thấy thông tin lương.
- **Aggregate-level authorization:** có được công bố số lượng, tổng tiền, phân vị, biểu đồ, facet hoặc xu hướng tạo ra từ những bản ghi đó hay không?

Bài này tập trung vào **phạm vi quyền trên dữ liệu** cho bốn thao tác: *search, count, pagination, statistics*. Ví dụ Spring Data JPA và SQL minh họa cách áp dụng chính sách ngay tại truy vấn; ví dụ Java 17 độc lập cho thấy chính xác kết quả khi dùng cùng một filter.

## 2. Công thức nền tảng cho một tập kết quả an toàn

Ký hiệu:

- `D` là tập tất cả bản ghi.
- `A(u,d)` là chính sách “người dùng `u` được đọc bản ghi `d`”.
- `F(q,d)` là bộ lọc nghiệp vụ do truy vấn tìm kiếm `q` yêu cầu (từ khóa, trạng thái, khoảng ngày, ...).
- `R(u,q) = {d ∈ D | A(u,d) ∧ F(q,d)}` là **tập kết quả hợp lệ**.

Từ đó:

```text
AuthorizedScope(user) = dữ liệu thỏa chính sách quyền
SearchResults         = AuthorizedScope ∩ BusinessFilters
TotalElements         = COUNT(SearchResults)
PageContent           = SORT(SearchResults)[offset : offset + limit]
Statistics            = AGGREGATE(SearchResults)
FacetCounts           = GROUP BY / COUNT trên phạm vi được thiết kế rõ
```

Đây là thứ tự **logic**: điều kiện quyền phải tham gia trước khi `LIMIT`/`OFFSET` và trước khi tổng hợp. Cơ sở dữ liệu có thể thay đổi thứ tự thực thi vật lý vì tối ưu hóa, nhưng ngữ nghĩa truy vấn phải tương đương với công thức trên.

Ba bất biến bảo mật nên biến thành automated tests:

1. **Không lộ tài nguyên:** mọi phần tử trả về phải thỏa `A(u,d)`.
2. **Không lộ số lượng:** `totalElements` và count API phải tính theo `A(u,d) ∧ F(q,d)`, không theo dữ liệu toàn hệ thống.
3. **Không lộ qua phép dẫn xuất:** thống kê, facet, biểu đồ, export count và gợi ý/tìm kiếm phải dùng đúng phạm vi quyền và những chính sách bổ sung dành cho aggregate.

### Ví dụ lỗi thường gặp

```java
// SAI: trang dữ liệu có scope nhưng tổng số lại đếm toàn hệ thống.
Page<Document> page = repository.findAll(allowedSpec, pageable);
long total = repository.count(); // Vô tình lộ quy mô dữ liệu khác quyền.
```

```java
// ĐÚNG HƯỚNG: dùng cùng phạm vi và cùng filter.
Specification<Document> fullSpec = allowedSpec.and(searchSpec);
Page<Document> page = repository.findAll(fullSpec, pageable);
long total = repository.count(fullSpec);
```

Hai đoạn là **mã tích hợp**, cần Spring Data JPA repository và các Specification tương ứng. Với `Page` do `findAll(fullSpec, pageable)` trả về, `getTotalElements()` được xây dựng từ logic count theo specification; thông thường **không cần gọi `count` riêng** nếu chỉ để lập lại số đó.

## 3. Xây dựng phạm vi quyền từ nguồn đáng tin cậy

Một rule minh họa:

> Caller có `DOC_READ`, chỉ thấy tài liệu trong tenant mình được phép truy cập và (là owner của tài liệu **hoặc** tài liệu có visibility `TEAM` trong tenant đó).

Biểu thức:

```text
CAN_READ(user, doc) =
  user.authenticated
  AND hasAuthority(user, "DOC_READ")
  AND doc.tenant_id = user.tenant_id
  AND (
       doc.owner_id = user.subject_id
       OR doc.visibility = "TEAM"
  )
```

Điều kiện tenant nằm **ngoài** nhóm OR. Sai lầm nguy hiểm là:

```sql
-- SAI: OR TEAM không còn ràng buộc tenant.
WHERE d.tenant_id = :tenant_id
  AND d.owner_id = :subject_id
   OR d.visibility = 'TEAM'
```

Do `AND` ưu tiên cao hơn `OR`, truy vấn trên có thể trả mọi tài liệu TEAM ở tenant khác. Đúng phải đặt ngoặc:

```sql
WHERE d.tenant_id = :tenant_id
  AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
```

### Caller scope đến từ đâu?

- `subjectId`: identity ổn định lấy từ principal/JWT được xác minh (không mặc định lấy raw username nếu username có thể trùng/đổi).
- `tenantId`: tenant đã được hệ thống xác nhận caller là thành viên hoặc có quyền truy cập; không tin header `X-Tenant-Id` do client tự khai.
- `roles`/`authorities`: từ `Authentication` đã được xác thực và ánh xạ đúng, không từ request body.
- Quyền chia sẻ theo tài liệu, ACL và trạng thái nhạy cảm: lấy từ nguồn server đáng tin cậy (DB/policy service), không nhận một danh sách document IDs “được phép” do client tự điền.

Một người có thể thuộc nhiều tenant. Khi đó tenant đang chọn là tham số nghiệp vụ, nhưng **phải được kiểm tra membership trước khi dùng**. Với quyền administrator xuyên tenant, policy cần ghi rõ phạm vi global/tenant, audit và test nhánh ngoại lệ; không thêm `OR isAdmin` vào mọi query mà chưa kiểm tra nguồn quyền.

### Fail closed

Nếu `Authentication` vắng mặt, tenant chưa xác định, token không có claim cần thiết hoặc policy backend lỗi, **không được** thay scope bằng một `Specification` null/`unrestricted()` hay chuỗi SQL rỗng. Từ chối API hoặc trả lỗi vận hành thích hợp. Trong Spring Data JPA, một specification null có thể đồng nghĩa **không lọc dữ liệu**; đây là failure mode cần chặn.

## 4. Tìm kiếm phải bắt đầu bằng tập dữ liệu được phép

Với tìm kiếm “roadmap”, thay vì:

```text
SELECT toàn bộ document chứa roadmap
  -> OFFSET/LIMIT
  -> lọc theo owner/tenant bằng Java
```

phải dùng logic:

```text
Query DB/Search Engine
  -> điều kiện tenant + owner/TEAM/ACL
  -> điều kiện keyword/status/date
  -> sort ổn định
  -> LIMIT/OFFSET hoặc cursor
  -> projection các field được phép hiển thị
```

### Vì sao lọc sau query là sai?

Giả sử DB tìm được 100 kết quả, trong đó 10 kết quả người dùng được xem. Nếu lấy trang đầu 20 kết quả rồi `stream().filter(this::canRead)`, có thể chỉ còn 1–2 kết quả. Không còn biết trang tiếp có bản ghi hợp lệ không; `totalElements=100` có thể lộ dữ liệu; người dùng phải lật nhiều trang rỗng và hệ thống đã tải tài nguyên nhạy cảm vào application memory.

`@PostFilter` trên một collection là tính năng thực của Spring Security, nhưng **không nên dùng làm cách chính** để bảo vệ tìm kiếm/pagination lớn. Nó lọc sau khi method đã lấy dữ liệu; không tự tính lại SQL count, aggregate, facet hoặc phân trang theo tập quyền.

### Từ khóa tìm kiếm và escaping

- Dùng bind parameters, không ghép nguyên text người dùng vào SQL/JPQL.
- Nếu dùng SQL `LIKE`, ký tự `%` và `_` có ý nghĩa wildcard; nếu ý định là tìm chuỗi literal, phải escape chúng với cú pháp phù hợp dialect.
- Giới hạn độ dài keyword, số filter, số điều kiện OR và kích thước trang để chống lạm dụng tài nguyên.
- Nếu dùng full-text search, policy filter phải áp dụng ngay trong truy vấn search index cùng logic membership/ACL, **không chỉ cắt kết quả ở API cuối**.
- Highlight, suggest/autocomplete và ranking cũng có thể lộ title/term tồn tại trong tài liệu không thuộc quyền.

## 5. Count không chỉ là một con số vô hại

Ví dụ người dùng được thấy 4 tài liệu chứa “roadmap”, nhưng `GET /documents/count?q=roadmap` trả 7 (vì đếm thêm các tài liệu ở tenant khác hoặc PRIVATE của người khác). Kẻ tấn công có thể thử hàng loạt từ khóa và suy đoán:

- Sự tồn tại của dự án nhạy cảm.
- Số khách hàng/đơn hàng trong một tenant khác.
- Mức độ hoạt động của người dùng khác.
- Số record theo tình trạng chờ duyệt, đã thanh toán hoặc bị khóa.

Vì vậy:

```sql
SELECT COUNT(*)
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
  AND LOWER(d.title) LIKE :pattern ESCAPE '!';
```

Trong SQL trên, `:subject_id` và `:tenant_id` là giá trị từ **caller scope đã xác minh**, còn `:pattern` là từ khóa được bind/escape. Dùng `!` làm escape character và phải escape chính ký tự `!`, `%`, `_` trước khi bind nếu muốn tìm literal.

### COUNT(*) và COUNT(DISTINCT ...)

Khi thêm join với bảng chia sẻ quyền hoặc tags, một document có thể nhân bản trong result set:

```sql
SELECT COUNT(*)
FROM documents d
JOIN document_share s ON s.document_id = d.id
WHERE ...;
```

Nếu mỗi document có nhiều hàng share, `COUNT(*)` có thể đếm **số dòng join**, không phải số document. Có hai chiến lược phổ biến:

- Dùng `EXISTS` để kiểm tra quyền khi mỗi resource chỉ cần xuất hiện một lần.
- Dùng `COUNT(DISTINCT d.id)` khi thực sự có join one-to-many và muốn đếm số tài nguyên duy nhất.

Không dựa vào `COUNT(DISTINCT)` để che lỗi cross-tenant join: mọi join tới bảng ACL/share cũng phải ràng buộc tenant và object identity.

## 6. Phân trang: áp dụng scope rồi mới offset/limit

Một response `Page<DocumentDto>` thường có:

```json
{
  "content": [
    {"id": 1, "title": "Roadmap platform"},
    {"id": 5, "title": "Roadmap archive"}
  ],
  "number": 0,
  "size": 2,
  "totalElements": 4,
  "totalPages": 2
}
```

Ý nghĩa chính sách:

- `content` chỉ có bản ghi được phép.
- `totalElements` tính trên toàn bộ **kết quả hợp lệ**, không chỉ các item trong page, và không bao gồm bản ghi trái quyền.
- `totalPages` phải suy ra từ `totalElements` hợp lệ và `size`; nếu total sai sẽ lộ dữ liệu dù content đúng.
- Page số lớn hơn không được biến thành “đọc trực tiếp OFFSET của bảng toàn hệ thống” bỏ qua scope.
- Các trường metadata khác như `hasNext`, `hasPrevious`, `numberOfElements` cũng phải nhất quán với tập hợp lệ.

### Stable sort là bắt buộc cho pagination đáng tin

Nếu chỉ `ORDER BY created_at DESC` và nhiều bản ghi trùng timestamp, các trang có thể trùng hoặc bỏ qua record do thứ tự không xác định. Thêm khóa ổn định:

```sql
ORDER BY d.created_at DESC, d.id DESC
LIMIT :page_size OFFSET :offset;
```

Vẫn phải có `WHERE` chứa **policy predicate**. Hãy giới hạn `page_size` (ví dụ 1–100 theo SLA) và tránh tính `offset = page * size` bằng số nguyên tràn. Sort field do client chỉ định phải được allowlist; đừng mở sắp xếp theo trường nhạy cảm không được phép nhìn thấy.

### Count query và data query có thể khác thời điểm

Giữa query lấy `content` và query đếm `totalElements`, các bản ghi có thể được thêm, sửa, xóa hoặc thay đổi quyền. Nếu không có snapshot/isolation thích hợp, số lượng và nội dung có thể không nhất quán tạm thời. Đây là vấn đề consistency **khác** lỗi scope. Với báo cáo tài chính hoặc pagination đòi hỏi snapshot mạnh, chọn transaction isolation, snapshot token hoặc dữ liệu bất biến tương ứng.

### Cursor/keyset pagination

Cursor nên được tạo dựa trên **sort key hợp lệ** và ràng buộc với query/filter, tenant, user hoặc scope version khi cần. Không dùng một cursor của tenant A để chuyển tiếp trang của tenant B. Mã hóa/đăng ký chữ ký cursor để chống sửa giá trị nhạy cảm, và **áp dụng lại predicate quyền cho mỗi trang**: cursor không phải giấy phép truy cập vĩnh viễn.

Offset có thể chậm trên tập lớn, keyset/cursor có lợi khi cần cuộn liên tục; cả hai vẫn phải dùng đúng authorized scope.

## 7. Thống kê và biểu đồ cũng có thể làm lộ dữ liệu

Thống kê thường bao gồm:

- Count theo trạng thái: ACTIVE, ARCHIVED, PENDING.
- SUM(amount), AVG(price), MIN/MAX, median/percentiles.
- Group by team, project, department, region, tháng.
- Facet/filter counts trong UI tìm kiếm.
- Biểu đồ xu hướng và dữ liệu exports tổng hợp.

Nếu dashboard hiển thị `COUNT(*)` hoặc `SUM(invoice.amount)` toàn công ty cho người chỉ được xem một tenant, đó là rò rỉ dữ liệu **qua aggregate**.

Thứ tự đúng:

```text
Tập dữ liệu gốc
    |
    v
AuthorizedScope(user)
    |
    v
BusinessFilters(search/query)
    |
    v
GROUP BY / SUM / COUNT / AVG / MIN / MAX
    |
    v
Chính sách công bố aggregate (nếu cần)
    |
    v
Response
```

Ví dụ SQL:

```sql
WITH visible AS (
    SELECT d.id, d.status, d.amount
    FROM documents d
    WHERE d.tenant_id = :tenant_id
      AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
      AND LOWER(d.title) LIKE :pattern ESCAPE '!'
)
SELECT status,
       COUNT(*) AS visible_count,
       COALESCE(SUM(amount), 0) AS visible_amount
FROM visible
GROUP BY status
ORDER BY status;
```

Tất cả số đếm/tổng tiền của query này đến từ `visible`. Đừng dùng một bảng thống kê đã tổng hợp toàn công ty (materialized view/cache) mà không có chiều tenant/permission cần thiết.

### Lọc theo quyền là cần, nhưng đôi khi chưa đủ

Ngay cả aggregate chỉ tính từ các record được phép cũng có thể nhạy cảm. Ví dụ một group chỉ có **một** nhân viên, `AVG(salary)` lộ đúng lương của người đó; query khác nhau một điều kiện có thể suy ra giá trị của một record (differencing attack).

Tùy nghiệp vụ cần thêm:

- Chỉ cho phép một số vai trò nhận báo cáo tổng hợp.
- Đặt ngưỡng nhóm tối thiểu (`k`-anonymity/suppression), nhưng nhớ cả phép trừ nhóm/chênh lệch.
- Hạn chế kết hợp filters, độ phân giải theo thời gian/vùng/nhóm và số lần truy vấn nếu rủi ro cao.
- Làm tròn, gộp bucket hoặc cơ chế bảo vệ riêng cho dữ liệu thống kê nhạy cảm.
- Audit export/report; không mặc định ai được đọc document cũng được tính mọi chỉ số tài chính.

Các kỹ thuật này là **chính sách aggregate bổ sung**, không thay thế row-level scope.

## 8. Facet: tổng số theo từng bộ lọc phải thống nhất

Giả sử tìm tài liệu với keyword “roadmap”, UI có facet `status`:

```text
ACTIVE   3
ARCHIVED 1
```

Những con số phải đến từ **tài liệu thuộc quyền** phù hợp với tập tìm kiếm đang hiển thị.

Có hai semantics facet phổ biến:

1. **Conjunctive facet:** sau khi áp dụng tất cả filters đang chọn, đếm mỗi nhóm trên tập còn lại.
2. **Disjunctive facet:** khi tính nhóm của một dimension (ví dụ status), có thể cố ý bỏ filter status đang chọn để hiển thị số lựa chọn khác; nhưng **không bao giờ bỏ authorized scope**, tenant hay các constraints không được miễn.

Mỗi endpoint phải ghi rõ semantics. Dù lựa chọn nào, một facet count không được từ bảng tổng toàn tổ chức rồi trả lại số khác phạm vi.

Các đường dữ liệu phải dùng scope giống nhau: search results, global count, facets, autocomplete/suggestions, analytics tab, CSV export, asynchronous reports và scheduled email summaries. Một endpoint ít được dùng cũng có thể tạo data leak.

## 9. Demo Java 17 chạy độc lập: search, count, page và stats dùng chung scope

Đây là một chương trình Java 17 **đầy đủ và không cần Spring** để nhìn rõ bất biến. Nó mô phỏng chính sách `DOC_READ`, tenant, owner và visibility TEAM.

Tạo file `ScopedQueryDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public final class ScopedQueryDemo {

    enum Visibility { PRIVATE, TEAM }

    record UserScope(
            String subject, String tenant, Set<String> authorities) {}

    record Document(
            long id,
            String tenant,
            String owner,
            Visibility visibility,
            String status,
            String title,
            long amount) {}

    private static Predicate<Document> allowed(UserScope user) {
        return doc -> user.authorities().contains("DOC_READ")
                && doc.tenant().equals(user.tenant())
                && (doc.owner().equals(user.subject())
                    || doc.visibility() == Visibility.TEAM);
    }

    private static Predicate<Document> titleContains(String keyword) {
        String needle = keyword.strip().toLowerCase(Locale.ROOT);
        return doc -> doc.title()
                .toLowerCase(Locale.ROOT)
                .contains(needle);
    }

    private static List<Long> ids(List<Document> documents) {
        return documents.stream().map(Document::id).toList();
    }

    public static void main(String[] args) {
        List<Document> documents = List.of(
                new Document(1, "ALPHA", "alice", Visibility.PRIVATE,
                        "ACTIVE", "Roadmap platform", 100),
                new Document(2, "ALPHA", "bob", Visibility.TEAM,
                        "ACTIVE", "Release notes", 200),
                new Document(3, "ALPHA", "bob", Visibility.PRIVATE,
                        "ACTIVE", "Payroll", 300),
                new Document(4, "BETA", "alice", Visibility.TEAM,
                        "ACTIVE", "Roadmap beta", 900),
                new Document(5, "ALPHA", "alice", Visibility.PRIVATE,
                        "ARCHIVED", "Roadmap archive", 150),
                new Document(6, "ALPHA", "cara", Visibility.TEAM,
                        "ACTIVE", "Roadmap team", 50),
                new Document(7, "BETA", "bob", Visibility.TEAM,
                        "ACTIVE", "Roadmap other", 500),
                new Document(8, "ALPHA", "alice", Visibility.PRIVATE,
                        "ACTIVE", "Budget", 80),
                new Document(9, "ALPHA", "bob", Visibility.TEAM,
                        "ACTIVE", "Roadmap milestone", 400),
                new Document(10, "ALPHA", "dave", Visibility.PRIVATE,
                        "ACTIVE", "Roadmap confidential", 1000)
        );

        UserScope alice = new UserScope(
                "alice", "ALPHA", Set.of("DOC_READ"));

        List<Document> visible = documents.stream()
                .filter(allowed(alice))
                .sorted(Comparator.comparingLong(Document::id))
                .toList();

        List<Document> result = visible.stream()
                .filter(titleContains("roadmap"))
                .toList();

        List<Long> page0 = result.stream()
                .limit(2).map(Document::id).toList();
        List<Long> page1 = result.stream()
                .skip(2).limit(2).map(Document::id).toList();

        Map<String, Long> statusCounts = result.stream()
                .collect(Collectors.groupingBy(
                        Document::status,
                        TreeMap::new,
                        Collectors.counting()));
        long amountSum = result.stream()
                .mapToLong(Document::amount)
                .sum();

        System.out.println("scopeIds=" + ids(visible));
        System.out.println("searchIds=" + ids(result));
        System.out.println("page0=" + page0);
        System.out.println("page1=" + page1);
        System.out.println("totalElements=" + result.size());
        System.out.println("statusCounts=" + statusCounts);
        System.out.println("amountSum=" + amountSum);

        UserScope noReadAuthority = new UserScope(
                "alice", "ALPHA", Set.of());

        long unauthorizedCount = documents.stream()
                .filter(allowed(noReadAuthority))
                .count();
        System.out.println("withoutReadAuthority=" + unauthorizedCount);
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac ScopedQueryDemo.java
java ScopedQueryDemo
```

Stdout của chương trình:

```text
scopeIds=[1, 2, 5, 6, 8, 9]
searchIds=[1, 5, 6, 9]
page0=[1, 5]
page1=[6, 9]
totalElements=4
statusCounts={ACTIVE=3, ARCHIVED=1}
amountSum=700
withoutReadAuthority=0
```

### Đọc kết quả

Alice được xem sáu tài liệu trong tenant ALPHA: ID 1, 2, 5, 6, 8, 9. Tài liệu PRIVATE 3 và 10 của người khác bị loại; các tài liệu tenant BETA 4 và 7 cũng bị loại dù một số có visibility TEAM.

Trong sáu tài liệu hợp lệ, bốn tài liệu chứa “roadmap”: ID 1, 5, 6, 9. Phân trang size 2 tạo trang đầu [1,5] và trang sau [6,9], tổng `totalElements=4`. Thống kê ACTIVE=3, ARCHIVED=1, amountSum=700 đều tính từ **bốn bản ghi hợp lệ và khớp keyword**, không có amount 900, 500 hay 1000 của các bản ghi trái quyền.

User thiếu `DOC_READ` có scope rỗng (`withoutReadAuthority=0`). Đây là demo filter theo dữ liệu, **không phải** quá trình authentication thật: trong service Spring Security production, thiếu authority nên bị `AccessDeniedException`/403 trước khi chạy truy vấn thay vì trả im lặng kết quả rỗng, tùy API contract.

### Điều demo chưa mô phỏng

Java Stream đang lọc một danh sách trong bộ nhớ. Trong hệ thống thật có hàng triệu bản ghi, không được `repository.findAll()` rồi lọc bằng Java. Điều kiện `allowed(user)` phải được chuyển thành `WHERE`/`Specification`/RLS/search-index filter và thống kê tính ở DB hoặc engine đã được scope. Mục sau triển khai mẫu đó.

## 10. Spring Data JPA: ghép Specification quyền và filter nghiệp vụ

Spring Data JPA cung cấp `JpaSpecificationExecutor<T>` với các phương thức chính:

```java
Page<T> findAll(Specification<T> spec, Pageable pageable);
long count(Specification<T> spec);
List<T> findAll(Specification<T> spec);
```

Những phương thức này được tài liệu Spring Data JPA 3.5 xác nhận. Ngoài ra có overload dùng `countSpec` riêng; nếu dùng, **countSpec vẫn phải chứa cùng điều kiện quyền** và business filter cần đếm.

### 10.1. Entity/repository

Các đoạn bên dưới là **mã tích hợp**, không phải một project Maven hoàn chỉnh; giả định đã có entity, cột và Spring Data JPA configuration.

```java
@Entity
@Table(name = "documents")
class DocumentEntity {

    @Id
    Long id;

    String tenantId;
    String ownerId;
    String title;
    String status;

    @Enumerated(EnumType.STRING)
    Visibility visibility;

    // Getter và mapping dữ liệu khác thuộc ứng dụng.
}

enum Visibility { PRIVATE, TEAM }

interface DocumentRepository extends
        JpaRepository<DocumentEntity, Long>,
        JpaSpecificationExecutor<DocumentEntity> {
}
```

### 10.2. CallerScope từ identity đã xác minh

```java
record CallerScope(String subjectId, String tenantId) {}

@Component
class CallerScopeResolver {

    CallerScope requireScope(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }

        // Trong ứng dụng thật, subject/tenant lấy từ identity đã xác minh
        // và membership/tenant policy phía server, KHÔNG từ query params.
        String subjectId = authentication.getName();
        String tenantId = resolveAuthorizedTenant(authentication);
        return new CallerScope(subjectId, tenantId);
    }

    private String resolveAuthorizedTenant(Authentication authentication) {
        // Bean/identity integration phải cài theo application của bạn.
        throw new UnsupportedOperationException("Tenant identity integration");
    }
}
```

Đây là **đoạn khung tích hợp**: `resolveAuthorizedTenant` không phải API Spring dựng sẵn. Nó cần được thay bằng việc xác minh tenant thật của hệ thống trước khi sử dụng. Không copy vào production khi chưa triển khai. Nếu caller chọn tenant trong URL/header, resolver phải đối chiếu với membership đã xác minh.

### 10.3. Specification scope

```java
final class DocumentSpecs {

    private DocumentSpecs() {}

    static Specification<DocumentEntity> visibleTo(CallerScope caller) {
        return (root, query, cb) -> cb.and(
                cb.equal(root.get("tenantId"), caller.tenantId()),
                cb.or(
                    cb.equal(root.get("ownerId"), caller.subjectId()),
                    cb.equal(root.get("visibility"), Visibility.TEAM)
                )
        );
    }

    static Specification<DocumentEntity> titleContains(String raw) {
        String needle = raw == null
                ? ""
                : raw.strip().toLowerCase(Locale.ROOT);
        if (needle.isEmpty()) {
            return (root, query, cb) -> cb.conjunction();
        }

        String escaped = needle.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");

        return (root, query, cb) -> cb.like(
                cb.lower(root.get("title")),
                "%" + escaped + "%",
                '!'
        );
    }
}
```

`DocumentSpecs.visibleTo(caller)` là **bắt buộc**, không được bỏ đi khi keyword rỗng. Dùng `CriteriaBuilder.and` với `or` đã có ngoặc ngữ nghĩa đúng:

```sql
WHERE tenant_id = :tenant
  AND (owner_id = :subject OR visibility = 'TEAM')
  AND LOWER(title) LIKE :keyword
```

Pattern `LIKE` được escape `!`, `%`, `_` theo contract SQL và bind qua JPA Criteria; kiểm tra lại escaping của dialect đang dùng. Cần import `java.util.Locale`, `org.springframework.data.jpa.domain.Specification`, JPA Criteria API và entity.

### 10.4. Query service dùng một fullSpec

```java
@Service
class DocumentQueryService {

    private final DocumentRepository repository;
    private final CallerScopeResolver scopeResolver;

    DocumentQueryService(DocumentRepository repository,
                         CallerScopeResolver scopeResolver) {
        this.repository = repository;
        this.scopeResolver = scopeResolver;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    @Transactional(readOnly = true)
    public Page<DocumentSummary> search(
            String keyword, int page, int size) {

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        CallerScope caller = scopeResolver.requireScope(auth);

        Specification<DocumentEntity> fullSpec =
                DocumentSpecs.visibleTo(caller)
                    .and(DocumentSpecs.titleContains(keyword));

        int safePage = Math.max(0, page);
        int safeSize = Math.max(1, Math.min(size, 100));

        Pageable pageable = PageRequest.of(
                safePage,
                safeSize,
                Sort.by("id").ascending());

        return repository.findAll(fullSpec, pageable)
                .map(DocumentSummary::fromEntity);
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    @Transactional(readOnly = true)
    public long count(String keyword) {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        CallerScope caller = scopeResolver.requireScope(auth);

        Specification<DocumentEntity> fullSpec =
                DocumentSpecs.visibleTo(caller)
                    .and(DocumentSpecs.titleContains(keyword));

        return repository.count(fullSpec);
    }
}
```

`DocumentSummary` là projection/DTO do ứng dụng định nghĩa, và `fromEntity` chỉ chọn field được công bố. Đây là snippet **tích hợp**, yêu cầu các imports Spring Data/JPA/Security và entity/DTO. Nếu DTO vô tình chứa salary/internalNote/token, scope theo hàng vẫn chưa giải quyết **property-level authorization**.

Điểm quan trọng:

- `@PreAuthorize` kiểm tra quyền gọi chức năng, còn `visibleTo` kiểm soát rows.
- Không nhận `CallerScope` từ request body/client; resolver phải lấy identity đã xác minh.
- Cùng `fullSpec` được dùng cho `findAll` và `count`. Có thể rút thành một hàm `authorizedQuery(auth, filters)` duy nhất để tránh copy-paste không nhất quán.
- `Page.getTotalElements()` được tính theo fullSpec; không tự ghi đè bằng repository.count() không có scope.
- Ở demo này sort là ID ổn định. Nếu cho phép client chọn sort, cần allowlist field và tie-break ID.
- `safePage` và `safeSize` là clamp tối thiểu phục vụ minh họa; production nên trả 400 cho input không hợp lệ, giới hạn offset/độ sâu trang và không chấp nhận integer overflow.
- `@EnableMethodSecurity` cần được bật, và lời gọi `DocumentQueryService` phải đi qua bean Spring proxy. Không dựa duy nhất vào method security: nếu có đường gọi repository trực tiếp, vẫn phải bảo vệ ranh giới đó.

### 10.5. Tránh countSpec không scope

Spring Data JPA có overload dạng:

```java
Page<DocumentEntity> page =
        repository.findAll(dataSpec, countSpec, pageable);
```

Nếu `dataSpec` có tenant/owner nhưng `countSpec` chỉ có keyword, response `totalElements` có thể đếm cả document trái quyền. Muốn tối ưu count bằng query khác (ví dụ tránh fetch join), ít nhất phải giữ **cùng policy predicate và business semantics**, rồi kiểm thử `totalElements` với các tenant/users cụ thể.

## 11. SQL thống kê: dùng một tập visible trong mọi phép tổng hợp

Trong hệ thống cần biểu đồ nhóm, có thể dùng CTE với điều kiện quyền:

```sql
WITH visible AS (
  SELECT d.id, d.status, d.amount, d.created_at
  FROM documents d
  WHERE d.tenant_id = :tenant_id
    AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
    AND LOWER(d.title) LIKE :pattern ESCAPE '!'
)
SELECT status,
       COUNT(*) AS number_of_documents,
       COALESCE(SUM(amount), 0) AS total_amount
FROM visible
GROUP BY status
ORDER BY status;
```

Trong ví dụ demo Java ở mục 9, query theo keyword “roadmap” sẽ tạo:

| status | number_of_documents | total_amount |
| --- | ---: | ---: |
| ACTIVE | 3 | 550 |
| ARCHIVED | 1 | 150 |
| **Tổng** | **4** | **700** |

Ở đây ACTIVE gồm ID 1(100), 6(50), 9(400); ARCHIVED là ID 5(150).

Đối với time-series, vẫn filter scope trong CTE trước khi group theo thời gian:

```sql
WITH visible AS (
  SELECT d.id, d.created_at
  FROM documents d
  WHERE d.tenant_id = :tenant_id
    AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
)
SELECT DATE_TRUNC('month', created_at) AS month,
       COUNT(*) AS visible_count
FROM visible
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month;
```

`DATE_TRUNC` là cú pháp PostgreSQL; database khác cần hàm tương đương. Đây là **snippet SQL tích hợp**, phải bind parameters và xây bảng/schema đúng. Tránh ghép trực tiếp một chuỗi `ORDER BY` hoặc tên cột do client gửi.

### Một bảng summary vật hóa có đủ an toàn?

Không phải lúc nào cũng. Bảng summary theo `tenant_id + month` có thể phù hợp cho admin được xem **toàn tenant**, nhưng không đủ nếu user chỉ xem document **mình sở hữu**, hoặc chỉ xem một project. Khi policy chi tiết hơn aggregate đã được tổng hợp, số liệu trong summary không thể “lọc tiếp” để lấy đúng phạm vi user.

Tùy chọn:

- Group sau khi áp dụng policy ở bảng chi tiết.
- Materialized view có **đúng những dimension và entitlement** cần cho scope.
- RLS/authorized view trên database với truy vấn aggregate chạy trong security context đúng.
- Hệ thống báo cáo chuyên dụng với precomputed entitlements, TTL và cơ chế cập nhật/thu hồi có contract.

Không dùng cache/report toàn công ty rồi chỉ ẩn vài cột trong UI.

## 12. ACL theo đối tượng và bài toán query-time filtering

Một số dự án dùng Spring Security ACL: một tài liệu có ACE grant/deny, owner, parent inheritance. `PermissionEvaluator.hasPermission(documentId, "Document", "READ")` có thể trả lời **một resource** có được phép hay không. Nhưng nếu phải duyệt 10.000 tài liệu rồi gọi evaluator 10.000 lần:

```text
SELECT 10,000 documents
-> với mỗi document: ACL lookup / hasPermission
-> lọc Java
-> phân trang
```

thì gây N+1, tốn tài nguyên và dễ sai total/count.

Lựa chọn cho search/count/statistics phải được thiết kế cùng policy:

1. **ACL-aware SQL/query predicate:** chuyển một phần/đầy đủ logic ACE/SID vào query hoặc materialized authorization index và test với `AclPermissionEvaluator` thật.
2. **Entitlement/visibility projection:** duy trì bảng chỉ mục `authorized_document(subject/role, tenant, document_id, permission)`, cập nhật/thu hồi và phân giải deny/inheritance nhất quán.
3. **Database RLS:** dùng chính sách row-level ở DB khi thiết kế cho phép và có identity/tenant mapping đáng tin, để `SELECT`, `COUNT`, `GROUP BY` đều được ràng buộc.
4. **Search engine document-level security:** index/query phải áp dụng tenant/ACL filter ở engine, không chỉ lọc top-N sau khi lấy.

**Cảnh báo:** Spring ACL có explicit deny, nhiều SID, thứ tự ACE và inheritance; không thể tùy tiện viết `EXISTS (ACE GRANT)` rồi tuyên bố tương đương mọi trường hợp của `Acl.isGranted`. Ví dụ direct deny ở child có thể cần ngăn parent grant; query phải hiểu chính xác precedence/algorithm hoặc dùng một security index đã tính đúng policy. Cần contract tests so sánh kết quả per-object evaluator với query-time scope.

Một chiến lược kiểm chứng rất hữu ích: với tập fixtures đại diện, tính `allowedIds` bằng ACL evaluator đáng tin, rồi so sánh với danh sách ID của query search/ACL index. Mọi mismatch là lỗi quyền hoặc thiếu coverage.

## 13. Joins, shares và tránh nhân bản record

Khi chính sách là “owner hoặc được share”, sử dụng `EXISTS` giúp giữ mỗi document một dòng:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND (
      d.owner_id = :subject_id
      OR EXISTS (
          SELECT 1
          FROM document_shares s
          WHERE s.document_id = d.id
            AND s.tenant_id = d.tenant_id
            AND s.subject_id = :subject_id
            AND s.permission = 'READ'
            AND s.granting = TRUE
      )
  );
```

Đoạn này minh họa một **mô hình sharing đơn giản** với bảng `document_shares`; không phải phiên bản đầy đủ của Spring ACL inheritance/deny. Nếu nghiệp vụ có explicit deny, cần thêm logic deny ưu tiên phù hợp. Điều kiện `s.tenant_id = d.tenant_id` là phần quan trọng để không dùng share row của tenant khác.

Với joins đến labels/tags/comments, có thể tạo duplicate document. Chú ý:

- `COUNT(DISTINCT d.id)` cho tổng số documents.
- Truy vấn phân trang phải phân trang theo **document IDs duy nhất**, không theo join rows; có thể dùng hai pha ID page rồi fetch.
- Nếu trả `Page` dựa trên fetch join collection trong JPA, phải kiểm tra behavior pagination/count của ORM; không tin rằng ORM luôn đẩy phân trang xuống SQL đúng cách.
- Aggregate SUM(amount) có thể bị nhân đôi nếu join một-to-many. Tính trên set unique document IDs trước khi SUM.

## 14. Cache và search index cũng cần scope

Một cache key như:

```text
documents:search:keyword=roadmap:page=0:size=20
```

là không đủ nếu Alice và Bob được thấy tập khác nhau. Kết quả trang đầu, `totalElements`, facets và stats có thể bị trả nhầm giữa hai user.

Key an toàn phải xem xét:

- Principal/subject hoặc entitlement hash (khi policy theo owner/share).
- Tenant đã xác minh.
- Role/authorities/scope version ảnh hưởng quyết định.
- Query keyword, filters, sort, page/cursor, projection và locale khi liên quan.
- Phiên bản dữ liệu/quyền và TTL tương ứng.

Quyền bị thu hồi có thể vẫn hiện trong cache cũ nếu không invalidation. Với search index không đồng bộ, xác định khoảng trễ quyền thay đổi và biện pháp xử lý cho tài liệu nhạy cảm. Không lộ trang kết quả do một user khác vừa cache chỉ vì cache nằm cùng tenant.

Với thống kê nhạy cảm, đôi khi **không cache theo user** là lựa chọn đúng; nếu cache aggregate, entitlement scopes phải được quản lý và test đầy đủ.

## 15. Quyền sau khi tạo trang và TOCTOU

Một request có thể thực hiện:

```text
T1: Query page với visibility TEAM -> record 42 được phép
T2: Owner chuyển record 42 sang PRIVATE
T3: API trả record 42 đã load ở T1
```

Đây là race condition giữa kiểm tra và sử dụng quyền (*time-of-check/time-of-use*). Các biện pháp tùy độ nhạy:

- Dùng transaction snapshot/isolation phù hợp cho các query liên quan trong một response.
- Với dữ liệu rất nhạy cảm, re-check dựa trên state hiện hành trước khi gửi/ghi, hoặc dùng query đã ràng buộc quyền tại thời điểm truy cập.
- Với mutation, dùng conditional UPDATE, optimistic locking hay row locks để ràng buộc quyền và trạng thái trong transaction.
- Với export/report bất đồng bộ, kiểm tra scope lại khi job chạy, không chỉ khi người dùng tạo job; kiểm tra quyền cả lúc tải file nếu cần.
- Nếu pagination kéo dài nhiều request, quyền có thể đổi giữa các trang; **cursor không được cấp quyền vĩnh viễn**.

Không có một isolation level duy nhất giải quyết mọi race trong hệ thống phân tán. Phải đặt yêu cầu “thu hồi quyền có hiệu lực sau bao lâu” và test tương ứng.

## 16. Kiểm thử tập dữ liệu: đừng chỉ kiểm tra status 200

Bộ integration test phải có ít nhất hai tenants, hai người dùng, cả tài liệu PRIVATE, TEAM, được share/không share và một record nhạy cảm chỉ khác keyword.

Bảng mẫu:

| Case | Điều kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Alice có DOC_READ, ALPHA | Query keyword roadmap | IDs [1,5,6,9] |
| Alice có DOC_READ, ALPHA | Total count keyword roadmap | 4 |
| Alice có DOC_READ, ALPHA | Page0 size2 | IDs [1,5] |
| Alice có DOC_READ, ALPHA | Page1 size2 | IDs [6,9] |
| Alice có DOC_READ, ALPHA | Facet status | ACTIVE=3, ARCHIVED=1 |
| Alice có DOC_READ, ALPHA | SUM(amount) | 700 |
| Alice tìm keyword chỉ có ở doc 10 PRIVATE của người khác | Search và count | Rỗng, count=0 |
| Alice tìm “Roadmap beta” của tenant BETA | Search và count | Rỗng, count=0 |
| Alice thiếu DOC_READ | Gọi search/count/stats | Bị từ chối ở service/API boundary |
| Bob ở tenant khác | Dùng cursor của Alice | Không được dùng scope/cursor của Alice |
| Alice gửi tenant=BETA trong query | Scope resolver | Không nhận tenant giả nếu không có quyền |
| JOIN shares có 2 dòng hợp lệ cùng doc | Count/total | Một document, không bị nhân bản |
| Tài liệu có ACL direct deny + parent grant | Query visibility/ACL index | Đúng với evaluator, không hiện |
| Quyền user bị thu hồi | Search/count/stats sau invalidation | Không còn bản ghi hoặc số lượng đã thu hồi |
| Thêm filter status=ACTIVE | Total và stats | Cùng filter và policy, không dùng count unscoped |
| Không có matching visible records | Empty page | content=[], totalElements=0 |
| Request sort theo field bị cấm | Validation | 400 hoặc bị từ chối theo contract |
| Page size quá lớn/offset vượt giới hạn | Validation | Bị giới hạn hoặc từ chối an toàn |

### Mẫu test Spring Data JPA với fixture đã seed

```java
@SpringBootTest
class DocumentQuerySecurityTest {

    @Autowired DocumentQueryService service;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void pageAndCountMustExcludeOtherTenantAndPrivateDocuments() {
        Page<DocumentSummary> page = service.search("roadmap", 0, 2);

        assertEquals(List.of(1L, 5L),
                page.getContent().stream().map(DocumentSummary::id).toList());
        assertEquals(4L, page.getTotalElements());
        assertEquals(2, page.getTotalPages());

        assertEquals(4L, service.count("roadmap"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void secondPageDoesNotSeeHiddenRecords() {
        Page<DocumentSummary> page = service.search("roadmap", 1, 2);
        assertEquals(List.of(6L, 9L),
                page.getContent().stream().map(DocumentSummary::id).toList());
    }
}
```

Đây là **snippet integration test**, không phải file chạy độc lập: cần fixture DB giống mục 9, `DocumentQueryService`, `DocumentSummary`, `CallerScopeResolver` thật, method-security configuration và imports JUnit/Spring Security test. Với `@WithMockUser` mặc định, tên user là alice nhưng **không có claim tenant**; trong test resolver cần lấy tenant từ một nguồn test xác minh tương ứng (ví dụ membership table) thay vì tự tin rằng mock user chứa tenant.

Thêm test cho `statistics` và `facets` dùng cùng dataset; test quá ít record có thể không phát hiện leak từ query unscoped. Tốt nhất seed những record “bẫy”: đúng keyword nhưng khác tenant, hoặc đúng tenant nhưng PRIVATE của người khác, với amount rất lớn để phát hiện việc SUM sai.

### Differential tests cho policy

Nếu có logic authorization trên từng object như `PermissionEvaluator`, dùng nó làm oracle trên tập fixture:

```text
expected = { id | perObjectPolicy.canRead(user, id) }
actual   = { id | searchQueryForUser(user).findAllIds() }

assert expected == actual
```

Đây là pseudocode kiểm thử, không phải syntax Java độc lập. Sau đó kiểm tra `count`, page, facets và statistics đều suy từ tập `actual`. Tổ chức test cả explicit deny, inheritance, multiple roles và các trường hợp tenant membership thay đổi.

## 17. Hiệu năng và indexing không được đánh đổi security

Đẩy authorization xuống DB thường **tốt hơn** tải tất cả record rồi lọc Java, nhưng các predicate owner/share/tenant có thể phức tạp. Các chiến lược:

- Index theo `(tenant_id, owner_id, id)` và `(tenant_id, visibility, id)` khi phù hợp với query workloads; đo trên DB cụ thể.
- Với shares, index `(tenant_id, subject_id, document_id, permission)` hoặc biến thể theo kế hoạch query.
- Full-text search cần security filters trong engine, không kết hợp top-K unscoped với post-filter.
- Dùng projections chỉ lấy field cần hiển thị; tránh eager fetch sensitive relations.
- Group-by và count cần tối ưu riêng: index, partition, pre-aggregation **đúng scope**, read replica có contract về độ trễ quyền.
- Count chính xác trên bảng lớn có thể đắt. Nếu dùng `Slice` hoặc “hasNext” thay vì Page để giảm count, **không được vì thế làm lộ thêm một record trái quyền**; over-fetch để kiểm tra next cũng phải theo scope.
- Approximate count có thể chấp nhận nếu UI yêu cầu và error bound rõ, nhưng estimate phải trên **tập hợp lệ**, không từ global catalog.
- Đo latency, số bản ghi scan, query plan và các trường hợp tìm kiếm vô lý mà không log raw nội dung nhạy cảm.

Không bật `Specification.unrestricted()` khi logic scope thất bại chỉ để tránh query chậm. Hiệu năng không phải lý do cho phép dữ liệu vượt quyền.

## 18. Những lỗi phổ biến cần tránh

**Lỗi 1 — Scope chỉ áp dụng cho content, không áp dụng count.** Người dùng đọc `totalElements` sẽ biết số record bị ẩn.

**Lỗi 2 — Phân trang trước rồi lọc bằng Java hoặc `@PostFilter`.** Page bị rỗng/truncated, count/hasNext sai và có nguy cơ load record trái quyền trước khi lọc.

**Lỗi 3 — OR thiếu dấu ngoặc trong SQL.** `tenant = A AND owner = alice OR visibility = TEAM` cho TEAM xuyên tenant.

**Lỗi 4 — Coi `@PreAuthorize("hasAuthority('DOC_READ')")` là row-level filter.** Nó chỉ quyết định caller có được thực hiện method.

**Lỗi 5 — Scope lấy từ header/body client.** Dễ bị giả mạo tenant/owner/role. Dùng principal/claims đã xác minh và membership server.

**Lỗi 6 — CountSpec khác dataSpec.** `Page.getTotalElements()` có thể lộ số liệu khác phạm vi khi custom count query bỏ policy.

**Lỗi 7 — Aggregate trên bảng toàn hệ thống.** COUNT/SUM/AVG/facet cùng search keyword vẫn phải ràng buộc quyền.

**Lỗi 8 — JOIN chia sẻ quyền nhân bản record.** COUNT và SUM sai, pagination lặp; dùng EXISTS/DISTINCT và kiểm tra query plan.

**Lỗi 9 — Dùng `EXISTS(grant ACL)` đơn giản với Spring ACL có deny/inheritance.** Có thể cho phép document có direct deny. Cần policy equivalence tests.

**Lỗi 10 — Cache không có caller/tenant/version.** Bob nhận kết quả tìm kiếm hoặc stats của Alice.

**Lỗi 11 — Search engine lọc top-N rồi mới kiểm tra ACL.** Results, ranking, suggestion, facets bị sai; có thể lộ bản ghi.

**Lỗi 12 — Chỉ trả IDs đúng nhưng để title/owner/salary/internal field trong DTO.** Row-level authorization không thay field-level authorization.

**Lỗi 13 — Cho phép sort/filter theo trường nhạy cảm.** Ngay cả khi không trả field, so sánh thứ tự/count nhiều truy vấn có thể suy ra giá trị; cần allowlist theo policy.

**Lỗi 14 — Thống kê nhóm size 1.** Dữ liệu thuộc scope nhưng AVG/MIN/SUM có thể tiết lộ cá nhân; cần aggregate-specific privacy controls.

**Lỗi 15 — Nghĩ cùng query name có cùng security scope ở tất cả endpoint.** Export, count, analytics, scheduled reports, facets và autocomplete thường có code path riêng.

**Lỗi 16 — Không kiểm tra quyền lại khi chạy job nền hoặc dùng cursor cũ.** Entitlement có thể thay đổi; re-evaluate theo policy hiện tại.

**Lỗi 17 — Thiếu stable sort.** Bản ghi lặp/bỏ giữa các trang, khó audit và dễ hiểu nhầm thành lỗi quyền.

**Lỗi 18 — Không phân biệt zero và forbidden.** Caller hợp lệ nhưng không có record nhìn thấy khác với caller không có quyền chạy chức năng; thống nhất API contract, không vô tình leak existence.

## 19. Checklist triển khai an toàn

- [ ] Đã xác định chính sách `A(user, record)` bằng nguồn identity và resource trusted.
- [ ] Có function-level permission riêng cho search/count/stats/export.
- [ ] Scope luôn kết hợp với filter nghiệp vụ bằng `AND` đúng nhóm dấu ngoặc.
- [ ] Search query đẩy tenant/owner/ACL/visibility xuống DB hoặc search engine.
- [ ] Count dùng **cùng policy và filter** với content; custom countSpec không bỏ scope.
- [ ] Pagination thực hiện sau filter, có sort ổn định và giới hạn page size/offset.
- [ ] `totalPages`, `hasNext`, facets và summaries không lộ số lượng khác quyền.
- [ ] Stats GROUP BY/SUM/AVG/MIN/MAX tính trên tập visible; có policy riêng cho aggregates nhạy cảm.
- [ ] JOIN chia sẻ/ACL không nhân bản record và không vượt tenant.
- [ ] Không dùng `@PostFilter` trên Page làm giải pháp phân trang chính.
- [ ] Khi policy dựa trên Spring ACL, query-time visibility được so sánh với evaluator cho direct grant, explicit deny, inheritance.
- [ ] Scope lỗi/thiếu Authentication không trở thành unrestricted query.
- [ ] DTO/projection chỉ chứa trường được phép, sort/filter được allowlist.
- [ ] Cache/search index/keyset cursor có scope và cách invalidate khi thu hồi quyền.
- [ ] Có test cross-tenant, owner mismatch, same keyword hidden records, status facets, amount SUM và zero results.
- [ ] Có test role/permission revocation, concurrency và report/export bất đồng bộ khi cần.
- [ ] Đã kiểm tra query plan, index và mục tiêu độ trễ mà không đánh đổi chính sách truy cập.

**Nguyên tắc ghi nhớ:** Phân quyền dữ liệu là một **phạm vi truy vấn**, không phải thao tác xóa những phần tử không được phép sau khi đã lấy một trang. Tập `authorized ∩ filters` phải là **nguồn sự thật duy nhất** cho tìm kiếm, tổng số bản ghi, phân trang, thống kê và facet. Nếu một con số hoặc một danh sách được tính từ tập khác, đó có thể là lỗ hổng thông tin dù `content` trông vẫn đúng.

## Tài liệu chính thức

- [Spring Data JPA 3.5 — JpaSpecificationExecutor JavaDoc](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Domain Object Security / ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API Security Top 10 — Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
