# Sort field allowlist — Danh sách field được phép sắp xếp

## 1. Allowlist kiểm soát quyền lựa chọn thứ tự

Trong chương **Sorting Rules** của Business Logic Security, sort field allowlist là tập lựa chọn sắp xếp được ứng dụng công bố và cho phép sử dụng trong một ngữ cảnh cụ thể. Server ánh xạ mỗi tên công khai sang property hoặc biểu thức truy vấn đã được kiểm soát, thay vì chuyển nguyên tên field do client gửi xuống lớp dữ liệu.

Ví dụ, API tìm đơn của người dùng cho phép sắp xếp theo ngày tạo hoặc mã đơn. Một số người có quyền tài chính được phép sắp xếp thêm theo tổng tiền. Điều đó không có nghĩa client được dùng mọi property của entity, mọi quan hệ lồng nhau hoặc mọi biểu thức mà database hỗ trợ.

Trong phạm vi module này, lựa chọn thứ tự phải giữ nguyên các invariant: đúng tenant, đúng quyền đối tượng, đúng điều kiện nghiệp vụ, không làm lộ field bị hạn chế và không biến việc đứng đầu danh sách thành quyền sửa giá hay bỏ qua phê duyệt.

Sau bài học, người học có thể thiết kế hợp đồng sort nhỏ, xây bộ phân giải Java, phân biệt tham số dữ liệu với cấu trúc query và kiểm thử cả quyền dùng field lẫn thứ tự kết quả thực tế.

## 2. Bốn nhóm rủi ro khi nhận tên field tự do

### 2.1. Chèn cấu trúc vào query

Đoạn mã sau ghép trực tiếp cấu trúc SQL từ input:

```java
String sql = BASE_QUERY
    + " ORDER BY " + request.field()
    + " " + request.direction();
```

Nếu input không được giới hạn đúng, client có thể tác động tới biểu thức hoặc cấu trúc mà ứng dụng không định cung cấp. Việc sau đó đưa chuỗi đã ghép vào `PreparedStatement` không khôi phục ranh giới dữ liệu và cấu trúc đã bị mất.

Tên cột, tên bảng và từ khóa chiều sort không được biến thành định danh/cú pháp chỉ bằng cách bind như một giá trị thông thường. OWASP khuyến nghị ánh xạ các lựa chọn cấu trúc này sang một tập giá trị cố định do ứng dụng sở hữu, đồng thời tiếp tục bind các giá trị dữ liệu. Xem [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).

### 2.2. Suy luận từ field không được phép sử dụng

Một API có thể giấu `internalRiskScore` khỏi JSON nhưng vẫn cho `sort=internalRiskScore`. Thứ tự các đối tượng có thể tiết lộ quan hệ tương đối về điểm rủi ro. Nếu actor còn điều khiển được một số bản ghi đối chiếu, khả năng suy luận có thể tăng thêm.

Đây không nhất thiết là SQL injection. Field có thể tồn tại và ORM có thể xử lý hợp lệ, nhưng việc sử dụng field đó vẫn vượt hợp đồng quyền của API.

### 2.3. Tạo truy vấn tốn tài nguyên hoặc sai tập kết quả

Sort theo một quan hệ nhiều phần tử, một phép tính hoặc một field không được hỗ trợ bởi kế hoạch truy vấn phù hợp có thể gây join, nhân dòng hoặc xử lý tốn kém. Một tên property tồn tại không chứng minh chi phí và ngữ nghĩa của nó phù hợp với endpoint.

### 2.4. Thay đổi thứ tự nghiệp vụ bắt buộc

Với hàng đợi xử lý rủi ro, hệ thống có thể yêu cầu lớp ưu tiên bắt buộc đứng trước, rồi mới cho người dùng chọn thứ tự bên trong lớp. Nếu sort từ client thay thế toàn bộ `ORDER BY`, một người có thể đẩy các đối tượng cần xử lý trước xuống cuối.

Vì vậy, allowlist không chỉ trả lời “field có hợp lệ về cú pháp không?”. Nó còn trả lời “actor có được dùng field này, theo cách này, tại endpoint này không?”.

## 3. Thiết kế hợp đồng sort công khai

### 3.1. Tên API không phải tên cột database

Xét API tìm đơn thuộc người gọi. Hợp đồng minh họa:

| Tên công khai | Property JPA nội bộ | Kiểu/ngữ nghĩa | Điều kiện sử dụng |
| --- | --- | --- | --- |
| `createdAt` | `createdAt` | Thời điểm tạo, không null | Người có quyền tìm đơn của mình |
| `number` | `reference` | Mã đơn dạng chuỗi, không null | Người có quyền tìm đơn của mình |
| `amount` | `totalAmount` | Tổng tiền trong phạm vi tiền tệ đã xác định, không null | Có cả quyền đọc và quyền sort số tiền |
| Không công bố | `internalRiskScore` | Điểm kiểm soát nội bộ | Không thuộc API này |
| Không công bố | `id` | Khóa phân xử do server thêm | Client không chọn trong hợp đồng ví dụ |

Alias `number` giúp hợp đồng API không phụ thuộc việc entity dùng `reference` và database dùng `reference_code` hay một tên cột khác. Không dùng danh sách property lấy bằng reflection làm tài liệu tự động cho phép mọi field.

### 3.2. Cấu trúc request có ý nghĩa rõ ràng

Một body tìm kiếm có thể chứa:

```json
{
  "state": "PENDING_APPROVAL",
  "page": 0,
  "size": 20,
  "sort": [
    { "field": "createdAt", "direction": "DESC" },
    { "field": "number", "direction": "ASC" }
  ]
}
```

API thực tế có thể dùng query string thay cho JSON. Dù chọn cách nào, cần quy định rõ cách biểu diễn nhiều term và cách parser giữ thứ tự. Không để một lớp hiểu hai term nhưng lớp khác chỉ lấy term đầu hoặc cuối.

Trong bài này, hợp đồng chọn:

- Bỏ `sort` hoặc truyền null thì dùng mặc định `createdAt DESC`.
- Mảng sort rỗng bị từ chối, không có nghĩa “không cần thứ tự”.
- Tối đa hai term do client lựa chọn.
- Mỗi field chỉ xuất hiện một lần sau khi ánh xạ về ý nghĩa chuẩn.
- Direction chỉ nhận chính xác `ASC` hoặc `DESC`.
- Tên field phân biệt hoa/thường và phải khớp chính xác allowlist.
- Một term sai làm cả yêu cầu sort bị từ chối; không âm thầm bỏ term đó.
- Server thêm `id ASC` làm khóa phân xử sau các term hợp lệ.

Đây là các lựa chọn thiết kế minh họa. Có thể chọn quy tắc khác, nhưng parser, authorization, query adapter, cursor và test phải hiểu cùng một hợp đồng.

### 3.3. Giới hạn cả field, direction và tổ hợp

Một field có thể chỉ được phép theo một chiều trong workflow cụ thể, hoặc chỉ được dùng cùng một số field khác. Nếu chỉ vài thứ tự có ý nghĩa và có chi phí được kiểm soát, có thể công bố các profile như `NEWEST` hoặc `AMOUNT_LOWEST` thay vì hỗ trợ mọi tổ hợp.

Đừng mở `ignoreCase`, `nullsFirst`, `collation`, tên hàm hoặc đường dẫn quan hệ chỉ vì thư viện có thuộc tính tương ứng. Mỗi khả năng bổ sung là một phần hợp đồng cần được đánh giá.

## 4. Allowlist phải gắn với actor và mục đích

### 4.1. Field tồn tại chưa có nghĩa được phép sort

Kiểm tra bằng reflection rằng `internalRiskScore` là property của `Order` chỉ chứng minh model có property đó. Nó không chứng minh actor được dùng property để thay đổi thứ tự.

Một blacklist như `password`, `secret` hoặc `riskScore` cũng dễ bỏ sót field mới. Với allowlist đóng, việc thêm một property vào entity không tự làm rộng khả năng của API.

Việc bảo vệ quyền trên các property nhạy cảm liên quan tới nhóm vấn đề được OWASP mô tả trong [API3:2023 — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/). Trong bài này, quyền sử dụng property để sắp xếp là một phần cần được quyết định rõ, kể cả khi giá trị không được trả trực tiếp.

### 4.2. Quyền đọc field và quyền sort có thể được định nghĩa riêng

Ứng dụng có thể chọn không cho sort một field dù actor được đọc nó, chẳng hạn vì field không có ngữ nghĩa thứ tự ổn định hoặc truy vấn quá tốn kém. Ngược lại, nếu sản phẩm cố ý cho sort theo một chỉ số không hiển thị, phải chấp nhận và đánh giá thông tin thứ tự có thể bị suy ra.

Trong ví dụ, `amount` yêu cầu cả `ORDER_AMOUNT_READ` và `ORDER_AMOUNT_SORT`. Context quyền lấy từ server, không từ body có cờ `financeUser=true`.

Quyền theo tenant/đối tượng cũng không biến mất khi đã cho phép sort field. Actor tài chính của tenant A không được thấy đơn của tenant B chỉ vì cả hai tenant đều có cột `totalAmount`.

### 4.3. Không dùng một allowlist toàn cục cho mọi endpoint

API cá nhân, báo cáo tài chính, hàng đợi phê duyệt và endpoint quản trị có thể cần những tập field khác nhau. Nên gắn policy với operation và phạm vi cụ thể để tránh việc thêm một field cho báo cáo vô tình mở nó ở API công khai.

Nếu có cache tập lựa chọn được phép, cần xử lý thay đổi quyền theo cam kết của hệ thống. Một danh sách đã cache không được trở thành quyền vĩnh viễn sau khi actor mất khả năng truy cập dữ liệu tài chính.

## 5. Bộ phân giải Java: từ input sang Sort do server kiểm soát

Ví dụ dưới sử dụng record và switch expression. Các kiểu `Actor` và `InvalidSortException` là thành phần ứng dụng cần hiện thực. Exception được ánh xạ thành lỗi input an toàn ở tầng API theo hợp đồng.

```java
public record SortTerm(String field, String direction) {}

public final class OrderSortResolver {
    private static final int MAX_CLIENT_TERMS = 2;
    private static final Map<String, String> JPA_PROPERTIES = Map.of(
        "createdAt", "createdAt",
        "number", "reference",
        "amount", "totalAmount"
    );

    public Sort resolve(List<SortTerm> requested, Actor actor) {
        List<SortTerm> effective = requested == null
            ? List.of(new SortTerm("createdAt", "DESC"))
            : requested;

        if (effective.isEmpty() || effective.size() > MAX_CLIENT_TERMS) {
            throw new InvalidSortException();
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seenProperties = new HashSet<>();

        for (SortTerm term : effective) {
            if (term == null || term.field() == null || term.direction() == null) {
                throw new InvalidSortException();
            }
            if (term.field().length() > 32 || term.direction().length() > 4) {
                throw new InvalidSortException();
            }

            String property = JPA_PROPERTIES.get(term.field());
            if (property == null || !seenProperties.add(property)) {
                throw new InvalidSortException();
            }

            Sort.Direction direction = switch (term.direction()) {
                case "ASC" -> Sort.Direction.ASC;
                case "DESC" -> Sort.Direction.DESC;
                default -> throw new InvalidSortException();
            };

            if (term.field().equals("amount")
                    && (!actor.hasCapability("ORDER_AMOUNT_READ")
                        || !actor.hasCapability("ORDER_AMOUNT_SORT"))) {
                throw new InvalidSortException();
            }
            orders.add(new Sort.Order(direction, property));
        }

        orders.add(Sort.Order.asc("id"));
        return Sort.by(orders);
    }
}
```

Các import chính là `java.util.*` và `org.springframework.data.domain.Sort`. Ví dụ thể hiện một operation cụ thể có ba lựa chọn; nếu nhiều workflow có policy khác nhau, tách phần quyền/định nghĩa field thành policy theo operation thay vì nới map này thành danh sách toàn bộ entity.

Những bảo đảm của bộ phân giải:

1. Property truyền cho Spring Data chỉ có thể đến từ map tĩnh hoặc khóa phân xử tĩnh.
2. Direction được tạo thành enum từ một tập token cụ thể, không ghép nguyên chuỗi input vào query.
3. Term được giữ theo thứ tự client yêu cầu; đây là thứ tự ưu tiên giữa các khóa.
4. `amount` không được dùng khi thiếu một trong hai quyền được quy định.
5. Term trùng bị từ chối theo property đã ánh xạ, giúp giữ quy tắc khi tương lai có thêm alias cùng nghĩa.
6. Giá trị thiếu/sai không trở thành `Sort.unsorted()` hoặc một property bất kỳ.

Bộ phân giải vẫn cần nhận actor đã xác thực, có quyền sử dụng chức năng tìm kiếm và thuộc đúng tenant. Nó không tự xác thực session hoặc quyết định phạm vi đơn được đọc.

Không dùng trực tiếp `Sort.by(request.field())` rồi coi việc thư viện tạo object thành công là bước authorization. Tương tự, annotation validation cho độ dài field chỉ là một phần kiểm tra input, không thay thế map và policy.

## 6. Tích hợp với service mà không mất phạm vi dữ liệu

Một service minh họa:

```java
@Transactional(readOnly = true)
public Page<OrderSummary> searchOwnOrders(
        OrderState state,
        int page,
        int size,
        List<SortTerm> requestedSort) {
    Actor actor = currentActor.requireActiveTenantActor();
    actor.requireCapability("ORDER_SEARCH_OWN");

    if (page < 0 || page > 1_000 || size < 1 || size > 100) {
        throw new InvalidPageRequestException();
    }

    Sort safeSort = sortResolver.resolve(requestedSort, actor);
    Pageable pageable = PageRequest.of(page, size, safeSort);
    return queries.findOwnedSummary(
        actor.tenantId(), actor.id(), state, pageable);
}
```

Repository cần có predicate tương ứng về ý nghĩa:

```sql
WHERE o.tenant_id = :trusted_tenant_id
  AND o.owner_id = :trusted_actor_id
  AND o.deleted = false
  AND (:requested_state IS NULL OR o.state = :requested_state)
```

Các giá trị này được bind phù hợp với query. Sort là một lựa chọn cấu trúc đã được phân giải riêng. Nếu API trả tổng, count phải áp dụng cùng tập điều kiện quyền và bộ lọc nghiệp vụ, không đếm toàn bộ bảng.

`OrderSummary` là projection được cấp quyền phù hợp, không phải entity đầy đủ tự serialize. Cho phép sort theo `amount` không tự cho phép API trả thêm mọi field tài chính khác.

Trong Spring Data JPA, sort property phải phù hợp property/alias tham chiếu được của query. Tài liệu cũng mô tả `JpaSort.unsafe` để hỗ trợ những biểu thức không đi qua kiểm tra property thông thường. Xem [Spring Data JPA — Using Sort](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.sorting).

Không đưa input chưa kiểm tra vào `JpaSort.unsafe`. Nếu ứng dụng cần một biểu thức cố định do developer quản lý, hãy cấp cho nó một tên API và adapter riêng với quyền, chi phí và test rõ ràng. Tên “unsafe” không tự chứng minh một cách dùng cụ thể là lỗi, nhưng cũng không phải một cơ chế kiểm soát quyền.

Các giới hạn page/size trong ví dụ là lựa chọn minh họa. Không chuyển sang unpaged khi resolver hoặc parser báo lỗi, vì như vậy một yêu cầu sort sai có thể vô tình mở rộng lượng dữ liệu trả về.

## 7. Phân biệt adapter JPA, SQL và search engine

### 7.1. Mỗi backend có không gian tên riêng

Một field công khai có thể được ánh xạ như sau:

| API | JPA | SQL native | Search index |
| --- | --- | --- | --- |
| `createdAt` | `createdAt` | `o.created_at` | Field ngày được mapping phù hợp |
| `number` | `reference` | `o.reference_code` | Field keyword/sort key được cấu hình |
| `amount` | `totalAmount` | `o.total_amount` | Field số theo ngữ nghĩa tiền tệ đã chọn |

Các tên backend trong bảng là ví dụ, không phải yêu cầu schema. Đừng lấy nguyên property JPA rồi ghép sang SQL, hoặc cho client tự thêm hậu tố index để tìm được field có thể sort.

### 7.2. Với native SQL, chỉ ghép các hằng đã được chọn

Một adapter có thể dùng lựa chọn nội bộ đã được kiểm tra:

```java
String column = switch (validatedField) {
    case CREATED_AT -> "o.created_at";
    case NUMBER -> "o.reference_code";
    case AMOUNT -> "o.total_amount";
};
String direction = validatedDirection == Direction.ASC ? "ASC" : "DESC";
String sql = BASE_QUERY + " ORDER BY " + column + " " + direction + ", o.id ASC";
```

`validatedField` và `validatedDirection` ở đây là enum nội bộ sau bước kiểm tra hợp đồng và quyền. Đoạn mã chỉ minh họa adapter một term; nếu hỗ trợ nhiều term, giữ nguyên giới hạn, thứ tự và khóa phân xử của resolver.

Việc ghép các hằng cố định sau ánh xạ khác với ghép chuỗi input tùy ý. Các giá trị của `WHERE`, hạn mức và tham số dữ liệu khác vẫn phải được bind theo API database phù hợp.

Đừng sửa lỗi bằng cách chỉ xóa dấu chấm phẩy hoặc thêm một cặp dấu quote quanh field. Một tên hợp lệ về cú pháp vẫn có thể là property nhạy cảm, và một biểu thức hợp lệ vẫn có thể ngoài hợp đồng.

### 7.3. Không để client chọn tùy ý quan hệ và hàm

Các input như `customer.internalRiskScore`, `items.unitPrice` hoặc `length(number)` có thể dẫn tới ngữ nghĩa hoàn toàn khác một scalar field của đơn. Đường dẫn hoặc hàm được ORM hỗ trợ không tự trở thành lựa chọn được cấp quyền.

Nếu nghiệp vụ thật sự cần sort theo một giá trị tổng hợp như “tổng tiền đã duyệt”, hãy công bố một field hoặc profile có tên rõ, xác định cách tính, phạm vi dữ liệu, phiên bản và quyền. Không mở cả một ngôn ngữ biểu thức chỉ để hỗ trợ một nhu cầu cụ thể.

## 8. Null, kiểu dữ liệu và collation là một phần hợp đồng

### 8.1. Null phải có ý nghĩa được chọn trước

Ba field trong ví dụ code được giả định không null trong tập kết quả. Nếu thêm `approvedAt`, cần xác định đơn chưa duyệt nằm trước hay sau và điều đó có phù hợp workflow không.

PostgreSQL cho phép `NULLS FIRST`/`NULLS LAST`, và mặc định thay đổi theo chiều sort. Xem [PostgreSQL — Sorting Rows](https://www.postgresql.org/docs/18/queries-order.html).

Không nhận một chuỗi tùy ý như `DESC NULLS FIRST` trong field direction nếu hợp đồng chỉ cho `ASC`/`DESC`. Null placement nên do định nghĩa field/profile phía server kiểm soát hoặc được biểu diễn bằng một lựa chọn riêng đã cho phép.

Spring Data mô tả null handling trong `Sort.Order` là một hint mà datastore có thể không tuân theo. Vì vậy, gọi `nullsLast()` chưa đủ chứng minh SQL/provider cụ thể đã thực hiện đúng. Xem [Spring Data Core — Sort.Order](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.Order.html).

### 8.2. Chuỗi, enum và tiền tệ không tự có thứ tự nghiệp vụ

Mã đơn dạng chuỗi có thể được sắp theo quy tắc chuỗi, không phải số tự nhiên. `ORD-10` và `ORD-2` cần một định nghĩa rõ nếu sản phẩm muốn so phần số.

Thứ tự chữ cái của trạng thái không nhất thiết trùng trình tự DRAFT → PENDING_APPROVAL → APPROVED. Nếu cần thứ tự state machine, dùng một mapping nghiệp vụ do server quản lý; đừng coi tên enum tình cờ đúng hôm nay là hợp đồng lâu dài.

So tổng tiền giữa nhiều loại tiền tệ cũng cần ý nghĩa rõ. Có thể giới hạn cùng loại tiền, nhóm theo currency hoặc dùng một giá trị quy đổi đã xác định nguồn và thời điểm. Chỉ thêm `amount` vào map không giải quyết được câu hỏi đó.

### 8.3. Case folding và locale cần cấu hình có chủ đích

Nếu cho sort tên không phân biệt hoa/thường hoặc theo một locale cụ thể, xác định sort key/collation được hỗ trợ. Không cho client gửi một biểu thức `COLLATE` hoặc tên hàm tùy ý vào query.

Quy tắc so sánh ảnh hưởng thứ tự, index và cursor. Tên công khai có thể giữ ổn định trong khi triển khai thay đổi, nhưng thay đổi ngữ nghĩa cần version/hành vi chuyển tiếp phù hợp, không âm thầm làm token cũ mang một ý nghĩa khác.

## 9. Giữ thứ tự nghiệp vụ và phân trang đúng hợp đồng

### 9.1. Khóa phân xử giúp thứ tự duy nhất

Nếu nhiều đơn có cùng `createdAt`, server thêm `id ASC` để có thứ tự xác định. Trong ví dụ, mặc định là:

```text
createdAt DESC, id ASC
```

Khóa phân xử không được vô tình bị mất khi client thêm term thứ hai. Nó cũng không tạo snapshot: bản ghi mới, thay đổi sort key hoặc đổi quyền giữa các request vẫn cần được xử lý theo hợp đồng live/snapshot của endpoint.

Với cursor, phải gắn mốc tiếp tục với toàn bộ sort chuẩn hóa, chiều từng khóa, null/collation liên quan và phạm vi query. Hai khóa có chiều khác nhau cần điều kiện tiếp tục tương ứng; không áp một dấu `<` cho mọi thành phần một cách máy móc.

### 9.2. Sort bắt buộc của workflow đứng ngoài phần tùy chọn

Nếu hàng đợi quy định `priorityClass DESC` là bắt buộc, client chỉ được chọn các term phụ sau lớp này. Việc ghép cần có ý nghĩa:

```text
khóa bắt buộc do workflow xác định
→ các term phụ được cấp quyền
→ khóa phân xử duy nhất
```

Không để `Pageable` do client cung cấp thay thế toàn bộ cấu trúc đó. Với workflow FIFO hoặc deadline bắt buộc, có thể không có lựa chọn sort tùy ý ở đường phân công xử lý, dù màn hình báo cáo vẫn cho nhiều cách xem.

### 9.3. Quyền sửa giá trị sort là một vấn đề riêng

Allowlist bảo vệ việc chọn khóa, không tự ngăn người dùng sửa giá trị của khóa đó để nhảy hàng đợi. `priorityClass`, deadline có thẩm quyền hoặc thời điểm tạo cần có đường ghi được kiểm soát phù hợp.

Một thứ tự an toàn cũng không cấp quyền phê duyệt hay thay đổi trạng thái. Khi thực hiện lệnh từ danh sách, server tiếp tục xét quyền đối tượng, tách biệt nhiệm vụ, phiên bản và invariant hiện hành.

## 10. Chi phí truy vấn, cache và xử lý lỗi

### 10.1. Kiểm soát chi phí theo những tổ hợp thực sự hỗ trợ

Giới hạn số term giúp tránh những query quá rộng về cấu trúc, nhưng hai term được cho phép riêng lẻ vẫn có thể tạo một tổ hợp đắt. Đánh giá index và kế hoạch truy vấn của những profile/tổ hợp thường dùng, đặc biệt khi có filter tenant, owner hoặc trạng thái.

Có thể giới hạn thêm theo loại endpoint, quy mô dữ liệu, page size, offset, thời gian thực thi và mức sử dụng actor/tenant. Index giúp hiệu năng, không thay thế authorization. Nếu query chậm, không fallback sang `findAll()` thiếu phạm vi quyền.

### 10.2. Cache và cursor dùng sort chuẩn hóa

Cache key cần phân biệt sort theo đúng thứ tự term và direction. `amount ASC, number DESC` khác `number DESC, amount ASC`; không sắp alphabet các term chỉ để tạo một chuỗi cache key ngắn.

Kèm những yếu tố chi phối kết quả như actor/phạm vi quyền, tenant, filter, trang/cursor và phiên bản sort policy phù hợp. Một response cache từ actor có quyền tài chính không được dùng để phục vụ actor không còn quyền sort hoặc đọc dữ liệu đó.

Cursor cũ phải được kiểm tra lại khi policy hoặc quyền thay đổi theo cam kết hệ thống. Token có sẵn không được bỏ qua resolver/policy và phục hồi một sort field mà người gọi hiện không còn được dùng.

### 10.3. Lỗi cần rõ nhưng không lộ schema

Trong hợp đồng ví dụ, field không tồn tại và field không được phép đều có thể trả mã công khai `INVALID_SORT`, không đưa tên property nội bộ hoặc stack trace ORM vào response. Lớp xác thực và quyền dùng chức năng vẫn có thể từ chối trước khi kiểm tra sort.

Nếu API công bố các lựa chọn sort, chỉ trả danh sách phù hợp operation và actor. Không dùng lỗi để gợi ý toàn bộ field nhạy cảm trong entity.

Không âm thầm bỏ term sai, đổi direction hoặc trả một trang không có thứ tự. Client cần biết yêu cầu của mình không được thực hiện để tránh nối các trang có ngữ nghĩa khác nhau.

## 11. Kiểm thử allowlist và thứ tự thực tế

### 11.1. Kiểm thử bộ phân giải

Các ca tối thiểu:

| Input | Kỳ vọng của hợp đồng minh họa |
| --- | --- |
| Không có sort/null | `createdAt DESC, id ASC` |
| `number ASC` | Property nội bộ `reference ASC`, sau đó `id ASC` |
| Hai field hợp lệ | Giữ đúng thứ tự ưu tiên, thêm khóa phân xử |
| `amount ASC` với đủ hai quyền | Được phân giải |
| `amount ASC` khi thiếu một quyền | Từ chối |
| `totalAmount` | Từ chối vì không phải tên công khai, dù property tồn tại |
| `internalRiskScore` | Từ chối, không tự mở từ entity |
| `customer.internalRiskScore` | Từ chối đường dẫn ngoài allowlist |
| `length(number)` | Từ chối biểu thức không được công bố |
| Direction khác `ASC`/`DESC` | Từ chối |
| Field lặp, kể cả khác chiều | Từ chối |
| Quá hai term | Từ chối |
| Mảng rỗng hoặc term/field/direction null | Từ chối theo quy tắc tương ứng |
| Tên khác hoa/thường hoặc ký tự nhìn giống | Từ chối nếu không khớp token công khai chính xác |

Ví dụ JUnit/AssertJ cho một phần resolver:

```java
@Test
void mapsPublicNameAndAddsTieBreaker() {
    Sort result = resolver.resolve(
        List.of(new SortTerm("number", "ASC")), basicActor);

    assertThat(result.toList())
        .extracting(Sort.Order::getProperty)
        .containsExactly("reference", "id");
    assertThat(result.toList())
        .extracting(Sort.Order::getDirection)
        .containsExactly(Sort.Direction.ASC, Sort.Direction.ASC);
}

@Test
void rejectsExistingButUnpublishedProperty() {
    assertThatThrownBy(() -> resolver.resolve(
        List.of(new SortTerm("totalAmount", "ASC")), financeActor))
        .isInstanceOf(InvalidSortException.class);
}
```

Các actor trong test phải có capability xác định. Đừng cho mọi test dùng một principal quản trị rồi coi đó là bao phủ kiểm tra quyền field.

### 11.2. Kiểm thử tích hợp với dữ liệu có chủ đích

Tạo fixture gồm nhiều đơn được phép xem, đơn người khác cùng tenant và đơn tenant khác. Các giá trị ngày, mã và số tiền phải khác nhau đủ để phát hiện đảo chiều; đồng thời có một số dòng bằng giá trị khóa chính để kiểm tra tie-breaker.

Viết thứ tự mong đợi từ dữ liệu fixture độc lập. Không gọi chính resolver đang kiểm tra để tính expected order, vì lỗi mapping có thể xuất hiện ở cả expected lẫn actual.

Những điều cần xác minh qua luồng query thật:

1. Sort theo từng field/chiều được phép cho ra đúng thứ tự các ID dự kiến.
2. Alias `number` thực sự đi tới field tham chiếu, không nhầm sang ID hoặc field khác.
3. Tenant, ownership và filter trạng thái vẫn được áp dụng với mọi lựa chọn sort.
4. Count và metadata không làm lộ đối tượng ngoài phạm vi.
5. Trang liên tiếp trên fixture tĩnh không trùng/thiếu và giữ đúng thứ tự đầy đủ.
6. Field bị từ chối không được chuyển xuống query rồi mới lộ lỗi schema; kiểm tra tại ranh giới adapter phù hợp.
7. Nếu thêm nullable field/profile, test null placement trên database/provider thật.
8. Cache hit và cursor không bỏ qua quyền field của actor hiện tại.

Một positive control cần cho thấy actor hợp lệ với sort hợp lệ nhận được dữ liệu thật. Request thiếu session, JSON hỏng hoặc CSRF sai trong một API cần CSRF có thể bị chặn trước resolver, nên không chứng minh allowlist đang hoạt động.

### 11.3. Kiểm tra không có tác động nghiệp vụ từ thao tác đọc

Sau các request sort hợp lệ và không hợp lệ, quan sát dữ liệu đã commit bằng transaction mới phù hợp mục tiêu: giá có thẩm quyền, trạng thái, quyết định phê duyệt, reservation và outbox nghiệp vụ không được thay đổi do việc chọn thứ tự đọc.

Log truy cập hoặc audit từ chối có thể phát sinh theo thiết kế. Không nhầm chúng với một quyết định nghiệp vụ đã được áp dụng. Với hệ thống có worker, kiểm tra cả lệnh được enqueue và tác động muộn liên quan, không chỉ response ngay lập tức.

Các ví dụ test trong bài là hướng dẫn cấu trúc; chúng không thay thế việc chạy kiểm thử tích hợp trên ứng dụng cụ thể.

## 12. Bảo trì allowlist khi hệ thống thay đổi

Mỗi lần thêm một field/profile sort, cần xác định:

```text
Tên API và ý nghĩa thứ tự
Operation và actor được phép sử dụng
Property/biểu thức backend cố định
Direction, null placement, locale và tie-breaker
Tổ hợp term được hỗ trợ cùng giới hạn chi phí
Ảnh hưởng tới projection, cache, cursor và version policy
Fixture cùng oracle cho thứ tự thực tế
```

Không tự sinh allowlist từ schema, entity, GraphQL model hoặc danh sách cột của một màn hình quản trị. Một field mới xuất hiện trong storage không nên tự trở thành khả năng quan sát mới của client.

Với đường export, job nền hoặc API bulk có hỗ trợ sort, áp dụng cùng cơ chế phân giải theo operation của chúng. Một endpoint chính đã được bảo vệ không đủ nếu worker nhận lại chuỗi field cũ và ghép SQL trực tiếp.

Audit hữu ích gồm actor, tenant, operation, sort chuẩn hóa, policy version, mã từ chối và correlation ID phù hợp. Không cần ghi stack trace chứa schema hoặc nguyên payload có dữ liệu nhạy cảm vào log truy cập thông thường.

## 13. Bài tập thực hành

Một hệ thống đang có quy trình:

```text
- Nhận field và direction dạng chuỗi.
- Chỉ kiểm tra field có trong Order bằng reflection.
- Gọi JpaSort.unsafe(field + " " + direction).
- Nếu query lỗi, bắt exception rồi gọi lại không có sort.
- API ẩn internalRiskScore trong JSON nhưng vẫn cho sort theo nó.
- Hàng đợi duyệt dùng toàn bộ sort do client chọn thay cho ưu tiên bắt buộc.
```

Hãy thiết kế lại:

1. Chọn các tên công khai được phép cho API cá nhân và hàng đợi duyệt.
2. Ánh xạ tên đó sang query backend, có kiểm tra quyền dùng từng field và direction.
3. Định nghĩa rõ mặc định, mảng rỗng, term trùng, term sai và số lượng tối đa.
4. Giữ lớp ưu tiên bắt buộc của hàng đợi và thêm khóa phân xử duy nhất.
5. Thiết kế lỗi, cache và cursor không làm mất ngữ nghĩa sort hoặc quyền hiện hành.
6. Tạo fixture bắt lỗi field tồn tại nhưng không được công bố, suy luận qua field ẩn, đảo chiều và mất lọc tenant.
7. Chứng minh việc thay đổi sort chỉ ảnh hưởng thứ tự được cấp quyền, không cấp thêm quyền sửa giá, duyệt hoặc chuyển trạng thái.

Một sort field allowlist đúng biến lựa chọn của client thành một tập hành vi nhỏ, có tên và được cấp quyền rõ ràng, đồng thời giữ cấu trúc truy vấn cùng các invariant nghiệp vụ dưới sự kiểm soát của server.
