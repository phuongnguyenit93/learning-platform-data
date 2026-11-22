# Allowed sort fields — Giới hạn trường sắp xếp được phép

## 1. Sort là một khả năng truy vấn, không chỉ là lựa chọn giao diện

Một API liệt kê đề nghị thanh toán có thể cho người dùng chọn sắp xếp theo thời điểm tạo hoặc số tiền. Nếu backend nhận nguyên tên thuộc tính, đường dẫn quan hệ hoặc biểu thức do client gửi, phạm vi truy vấn có thể rộng hơn rất nhiều so với một nút trên bảng.

Những rủi ro có thể xuất hiện:

- Input trở thành cú pháp `ORDER BY` không được kiểm soát.
- Người dùng sắp xếp theo field nhạy cảm dù field đó không xuất hiện trong response.
- Một property path làm ORM tạo join hoặc truy cập quan hệ ngoài hợp đồng.
- Sort không ổn định khiến pagination lặp hoặc bỏ dòng.
- Một sort tính toán tốn kém làm tăng tải của truy vấn được gọi thường xuyên.
- Thứ tự hiển thị bị dùng như thứ tự thực thi, giúp client thay đổi ưu tiên nghiệp vụ ngoài thẩm quyền.

**Allowed sort fields** là danh mục những khả năng sắp xếp mà server công nhận, gồm field công khai, chiều, điều kiện quyền, ngữ nghĩa dữ liệu và cách thực thi đã được kiểm soát.

Mục tiêu không chỉ là loại ký tự nguy hiểm. Một tên field hợp lệ về cú pháp vẫn có thể không được phép sử dụng hoặc không phù hợp với nghiệp vụ.

## 2. Phân biệt ba loại tên

| Loại tên | Ví dụ | Ai quản lý? |
| --- | --- | --- |
| Tên sort công khai | `createdAt`, `amount` | Hợp đồng API |
| Thuộc tính hoặc cột nội bộ | `p.created_at`, `p.amount_minor` | Mô hình lưu trữ và query phía server |
| Sort plan | `CREATED_DESC_V1`, `AMOUNT_ASC_V1` | Catalog thực thi đã được server kiểm soát |

Client không cần biết tên cột để chọn một khả năng hợp lệ. Server ánh xạ lựa chọn công khai sang một plan được hỗ trợ.

Một field mới trong entity hoặc index không nên tự trở thành field sort của endpoint cũ. Đặc biệt, không lấy toàn bộ property của entity làm danh sách công khai chỉ để giảm công sức cấu hình.

### 2.1. Permission đọc và permission sort không luôn giống nhau

Một caller có thể được đọc một tập summary nhưng không được dùng mọi field để sắp xếp tập đó. Nếu quyền dữ liệu khác nhau theo dòng, cần xem sort có được phép trên toàn bộ tập tham gia không.

Ví dụ người dùng được xem số tiền ở A1 nhưng chỉ thấy summary hạn chế của một hồ sơ được chia sẻ tại A2. Một role tài chính chung không tự đủ để sort cả tập theo số tiền bị ẩn của A2.

## 3. Danh mục sort cần có những thông tin nào?

```text
AllowedSortEntry = {
    public_field_or_sort_id,
    endpoint_and_action,
    allowed_directions,
    required_authority,
    scope_and_field_visibility_conditions,
    data_type_and_business_unit,
    null_order,
    collation_or_normalization_if_needed,
    tie_breaker,
    cursor_key_schema,
    execution_plan,
    cost_limits,
    contract_revision
}
```

Ví dụ cho endpoint đọc summary của đề nghị thanh toán:

| Lựa chọn công khai | Điều kiện minh họa | Thực thi |
| --- | --- | --- |
| `createdAt` | Có quyền đọc summary trong scope | Sắp theo thời điểm tạo và ID phá hòa |
| `amount` | Được dùng số tiền để sort trên tập kết quả, có một tiền tệ xác định | Sắp theo số tiền đơn vị nhỏ nhất và ID |
| `internalRiskScore` | Không thuộc hợp đồng ví dụ | Từ chối |
| `beneficiary.bankAccount` | Không thuộc hợp đồng ví dụ | Từ chối |
| Biểu thức hoặc tên hàm tùy ý | Không thuộc hợp đồng | Từ chối |

Các điều kiện là lựa chọn chính sách của ví dụ. Một sản phẩm có thể có những khả năng khác, nhưng cần định nghĩa và kiểm tra chúng rõ ràng.

### 3.1. Tập được phép phụ thuộc endpoint

Một field được sort ở báo cáo kiểm toán không tự được sort ở màn hình khách hàng. Dùng cùng entity không có nghĩa hai endpoint có cùng quyền hoặc cùng ngân sách truy vấn.

Tenant admin cũng không mặc nhiên được mọi sort nhạy cảm. Quyền quản trị cấu hình hoặc thành viên khác với quyền đọc và suy ra dữ liệu nghiệp vụ.

## 4. SQL identifier không phải một giá trị bind thông thường

Ví dụ không an toàn:

```java
String sql = baseQuery
        + " ORDER BY " + input.field()
        + " " + input.direction();
```

Chuẩn bị statement sau khi đã nối chuỗi không làm phần cú pháp vừa chèn trở nên an toàn.

Parameter marker dùng cho giá trị, không thay trực tiếp tên cột hoặc từ khóa chiều sort. OWASP khuyến nghị ánh xạ những lựa chọn cấu trúc này vào một tập giá trị cố định do ứng dụng quản lý. [OWASP SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html#allow-list-input-validation)

Một cách làm sai khác:

```sql
ORDER BY :columnName
```

Bind một chuỗi ở vị trí đó không có nghĩa database sẽ chọn cột mà chuỗi đặt tên. Nó có thể là giá trị hằng hoặc bị xử lý không như tác giả mong muốn tùy query và driver.

### 4.1. Regex không thay thế danh mục thẩm quyền

Một regex chỉ cho chữ, số, dấu gạch dưới hoặc dấu chấm có thể loại một số input sai cú pháp nhưng vẫn nhận những field hợp lệ mà caller không được dùng.

Ví dụ `internalRiskScore` hoặc `owner.privateStatus` có thể không chứa ký tự lạ. Vấn đề là chúng không thuộc khả năng được cấp, không chỉ là chuyện escape chuỗi.

### 4.2. Quote identifier cũng không tự cấp quyền

Đóng một tên cột trong dấu quote đúng cú pháp có thể giải quyết một vấn đề biểu diễn. Nó không chứng minh cột đó được endpoint công bố, không nhạy cảm hoặc có chi phí phù hợp.

Cần ánh xạ từ danh mục đóng, không chỉ làm sạch mọi tên client đề nghị rồi đưa vào query.

## 5. Hợp đồng request phải có mặc định và giới hạn rõ

Ví dụ API chỉ cho một field sort chính:

```json
{
  "filters": {
    "state": "APPROVED",
    "currency": "VND"
  },
  "sort": {
    "field": "createdAt",
    "direction": "desc"
  },
  "pageSize": 25,
  "cursor": null
}
```

Lựa chọn của ví dụ:

- Không gửi `sort`: dùng mặc định server `createdAt desc`.
- Đã gửi sort nhưng thiếu field hoặc direction: lỗi theo hợp đồng, không đoán nhánh có lợi.
- Chỉ nhận các tên công khai được đăng ký.
- Direction được ánh xạ riêng từ các giá trị đã định nghĩa.
- Không nhận raw SQL, tên hàm, alias nội bộ hoặc property path tự do.
- Page size được giới hạn độc lập.

Không biến một field không được hỗ trợ thành sort mặc định một cách âm thầm nếu client cần biết lựa chọn của họ chưa được áp dụng. Nếu sản phẩm có cơ chế tương thích riêng, phải mô tả rõ và không làm rộng quyền.

### 5.1. Nhiều sort cần một hợp đồng khác

Nếu cho nhiều field, cần giới hạn số lượng, tổ hợp được hỗ trợ, field lặp và chiều mâu thuẫn. Không nhận một danh sách không giới hạn rồi để ORM tự mở rộng mọi đường dẫn.

Thứ tự các sort term có ý nghĩa, nên canonical hóa không được tự sắp lại chúng như một tập không có thứ tự.

### 5.2. Tham số lặp không được tạo hai cách hiểu

Nếu cùng request có nhiều giá trị sort mà các lớp có thể lấy giá trị đầu hoặc cuối khác nhau, cần xử lý theo schema rõ ràng. Với endpoint chỉ nhận một sort, có thể từ chối biểu diễn mơ hồ thay vì validate một giá trị rồi thực thi giá trị khác.

## 6. Quyền sort có thể làm lộ giá trị không được trả về

Giả sử response chỉ có ID và tên hồ sơ, không có điểm rủi ro. Nếu caller được sort tăng và giảm theo `internalRiskScore`, thứ tự có thể tiết lộ quan hệ tương đối giữa các giá trị bị ẩn.

Vấn đề vẫn tồn tại khi hoàn toàn không có SQL injection. Đây là ngữ nghĩa dữ liệu mà một khả năng sort cho phép suy ra.

Cần chọn rõ:

- Field có được dùng cho sort với actor và tập dữ liệu này không?
- Việc lộ thứ tự tương đối có được policy chấp nhận không?
- Có được trả thêm sort value trong metadata hoặc cursor không?
- Những field liên quan có quyền theo dòng khác nhau không?

### 6.1. Không mặc định mọi ranking đều bị cấm

Một sản phẩm có thể chủ ý cho xếp hạng theo mức ưu tiên mà không trả công thức hoặc điểm thô. Khi đó thứ tự được công bố là một phần của hợp đồng và cần được cấp quyền tương ứng.

Điều cần tránh là một field nội bộ tự trở thành kênh xếp hạng chỉ vì framework nhận property name tùy ý.

### 6.2. Tập kết quả có quyền field không đồng đều

Có thể từ chối một sort trên toàn query khi không bảo đảm field được phép dùng cho mọi đối tượng tham gia, hoặc thiết kế một chế độ thu hẹp tập kết quả có tên và ý nghĩa rõ ràng.

Không âm thầm bỏ những dòng khó cấp quyền sort rồi vẫn mô tả kết quả như toàn bộ tập hồ sơ caller được phép tìm.

## 7. Sort vẫn phải nằm sau phạm vi được cấp quyền

Một luồng logic cần giữ:

```text
tenant và predicate quyền
  → filter nghiệp vụ
  → sort plan được cấp
  → điều kiện tiếp tục tương thích
  → giới hạn trang
  → projection được phép
```

Đây là cách diễn đạt ngữ nghĩa query, không phải yêu cầu database thực thi từng thao tác theo một thứ tự vật lý cố định.

Sort hợp lệ không cho phép bỏ tenant, join một tài nguyên khác sai phạm vi hoặc tính thứ tự từ dữ liệu ngoài quyền mà policy chưa chấp nhận.

### 7.1. Quyền trên quan hệ được dùng để sort

Nếu sort theo thuộc tính nhà cung cấp, cần biết quan hệ join, tenant và thông tin dùng làm khóa đều đúng hợp đồng. Một path thuộc tính không phải một quyền truy cập quan hệ.

Có thể cần một field denormalize hoặc một biểu diễn công khai khác thay vì mở trực tiếp cấu trúc entity nội bộ. Dữ liệu sao chép vẫn giữ yêu cầu bảo mật của nó.

### 7.2. Không tính thứ tự trên tập rộng rồi mới lọc sơ sài

Nếu engine tạo ranking hoặc metadata dựa trên dữ liệu ngoài scope, cần đánh giá đúng mức công bố của thông tin đó. Chỉ bỏ ID cấm ở response cuối không tự giải quyết mọi suy đoán qua thứ tự, điểm số hoặc số lượng.

Với API đơn giản, query trên tập đã được cấp quyền và sort theo các field công khai thường dễ giải thích và kiểm thử hơn.

## 8. Thứ tự phải đủ xác định cho pagination

Nhiều hồ sơ có thể cùng `created_at` hoặc cùng số tiền. Chỉ sort theo một giá trị không duy nhất dễ làm các trang không có vị trí tiếp tục rõ ràng.

Ví dụ:

```sql
ORDER BY p.created_at DESC, p.id DESC
```

ID đóng vai trò phá hòa trong tenant của truy vấn. PostgreSQL lưu ý LIMIT cần thứ tự đủ xác định nếu muốn nhận các tập con có thể dự đoán. [PostgreSQL: LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)

### 8.1. Chiều áp dụng cho từng term

Không suy chiều của field cuối áp dụng cho mọi field trước đó. Với nhiều term, cần chỉ rõ từng chiều theo plan. PostgreSQL cũng định nghĩa thứ tự và cách xử lý null trên từng biểu thức sort. [PostgreSQL: Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html)

### 8.2. Null cần được thiết kế

Nếu mở sort theo `dueAt` có thể null, cần định nghĩa null đứng đầu hay cuối và position được biểu diễn ra sao.

Một phép so tuple chứa null không tự cho kết quả tiếp tục giống thứ tự mong muốn. Có thể cần một cờ nhóm null và các nhánh so sánh rõ ràng; không thay null bằng một sentinel tùy ý mà chưa kiểm tra va chạm và ngữ nghĩa.

### 8.3. String và collation

Sort theo tên có thể phụ thuộc collation hoặc quy tắc chuẩn hóa. Nếu client được chọn locale, đó phải là lựa chọn có giới hạn và được ánh xạ vào plan đã kiểm soát.

Không nhận một chuỗi `COLLATE` tùy ý hoặc giả rằng Java comparator mặc định sẽ luôn cho cùng thứ tự với database.

## 9. Ví dụ Java: catalog sort plan đóng

Ví dụ sau hỗ trợ một field chính, hai chiều và các cột không null. ID là khóa phá hòa. Những sort tiền chỉ dùng khi policy cho phép và query có một tiền tệ xác định.

```java
public enum PaymentSortPlan {
    CREATED_ASC_V1(
            "created-asc-v1",
            "p.created_at ASC, p.id ASC",
            CursorKeyKind.CREATED_AT_AND_ID),
    CREATED_DESC_V1(
            "created-desc-v1",
            "p.created_at DESC, p.id DESC",
            CursorKeyKind.CREATED_AT_AND_ID),
    AMOUNT_ASC_V1(
            "amount-asc-v1",
            "p.amount_minor ASC, p.id ASC",
            CursorKeyKind.AMOUNT_MINOR_AND_ID),
    AMOUNT_DESC_V1(
            "amount-desc-v1",
            "p.amount_minor DESC, p.id DESC",
            CursorKeyKind.AMOUNT_MINOR_AND_ID);

    private final String cursorSortId;
    private final String orderBySql;
    private final CursorKeyKind keyKind;

    PaymentSortPlan(
            String cursorSortId,
            String orderBySql,
            CursorKeyKind keyKind) {
        this.cursorSortId = cursorSortId;
        this.orderBySql = orderBySql;
        this.keyKind = keyKind;
    }

    public String cursorSortId() { return cursorSortId; }
    public String orderBySql() { return orderBySql; }
    public CursorKeyKind keyKind() { return keyKind; }
}
```

Các enum và kiểu được tham chiếu cần được định nghĩa trong dự án. Những đoạn SQL này là hằng nội bộ, không phải chuỗi được deserialize vào enum từ JSON.

Lấy giá trị từ một tập hằng đã được server chọn khác với nối thẳng `input.field()` hoặc `input.direction()`. Tuy nhiên, catalog vẫn cần được rà soát về quyền, chi phí và tính đúng, không chỉ an toàn cú pháp.

### 9.1. Resolver kiểm tra cả hợp đồng lẫn quyền

```java
public final class PaymentSortResolver {
    private final PaymentSortPolicy policy;

    public PaymentSortResolver(PaymentSortPolicy policy) {
        this.policy = policy;
    }

    public PaymentSortPlan resolve(
            VerifiedActor actor,
            CurrentSearchScope scope,
            CanonicalPaymentFilters filters,
            SortInput input) {

        if (input == null) {
            policy.requireCreatedSortAllowed(actor, scope);
            return PaymentSortPlan.CREATED_DESC_V1;
        }
        input.requireCompleteAndWithinBounds();

        SortDirection direction = switch (input.direction()) {
            case "asc" -> SortDirection.ASC;
            case "desc" -> SortDirection.DESC;
            default -> throw new UnsupportedSortException();
        };

        return switch (input.field()) {
            case "createdAt" -> {
                policy.requireCreatedSortAllowed(actor, scope);
                yield direction == SortDirection.ASC
                        ? PaymentSortPlan.CREATED_ASC_V1
                        : PaymentSortPlan.CREATED_DESC_V1;
            }
            case "amount" -> {
                policy.requireAmountSortAllowedForWholeScope(actor, scope);
                filters.requireExactlyOneCurrency();
                yield direction == SortDirection.ASC
                        ? PaymentSortPlan.AMOUNT_ASC_V1
                        : PaymentSortPlan.AMOUNT_DESC_V1;
            }
            default -> throw new UnsupportedSortException();
        };
    }
}
```

Các kiểu và policy là thành phần cần triển khai; code minh họa thiết kế, không phải một endpoint chạy độc lập. `requireCompleteAndWithinBounds()` phải xử lý null, độ dài và biểu diễn theo hợp đồng trước khi switch.

`CurrentSearchScope` phải đến từ đường phân quyền được tin cậy, không từ body. Policy amount cần xét đúng tập đối tượng và mức quyền field của actor, không chỉ một boolean đọc từ client.

### 9.2. Mặc định cũng là một plan có chính sách

Không cần bỏ kiểm tra chỉ vì caller không gửi sort. Plan mặc định phải có ngữ nghĩa, chi phí và điều kiện quyền phù hợp với endpoint.

Mẫu chọn tên và direction khớp chính xác. API có thể hỗ trợ alias hoặc chuẩn hóa khác, nhưng chỉ sau khi định nghĩa rõ; không mở property path nội bộ như một fallback.

## 10. Tích hợp plan vào query mà không nhận cú pháp client

Một repository có thể dựng câu SQL từ các thành phần thuộc quyền server:

```java
String sql = AUTHORIZED_QUERY_FOR_VALIDATED_FILTERS
        + " ORDER BY " + validatedSort.orderBySql()
        + " LIMIT :fetchCount";

return jdbc.query(sql, trustedBindings, summaryRowMapper);
```

Đây là đoạn minh họa. Hằng query hoặc compiler được gọi phải giữ predicate quyền, còn `trustedBindings` chứa những giá trị đã được kiểm tra và bind đúng kiểu. Chữ “trusted” trong tên biến không tự tạo bảo đảm.

Ví dụ một query cho scope đơn vị, một trạng thái và một tiền tệ đã được chọn:

```sql
SELECT p.id,
       p.created_at,
       p.display_reference,
       p.amount_minor,
       p.currency,
       p.state
FROM payment_request p
WHERE p.tenant_id = :verifiedTenantId
  AND p.org_unit_id = ANY(:authorizedUnitIds)
  AND p.state = :validatedRequestedState
  AND p.currency = :validatedCurrency
ORDER BY p.created_at DESC, p.id DESC
LIMIT :fetchCount;
```

Các dấu `:` là tham số bind của lớp truy cập dữ liệu, gồm mảng ID theo cơ chế hỗ trợ của driver hoặc thư viện. Đây chỉ là một mô hình scope và filter cụ thể, không thay toàn bộ policy ownership hoặc delegation của hệ thống khác.

Nếu filter tùy chọn, chọn những đoạn query cố định hoặc compiler có cấu trúc được kiểm soát. Không lấy một raw predicate hoặc sort expression từ input để thay chúng.

### 10.1. ORM cũng cần danh mục field công khai

Một API của ORM có thể tạo câu lệnh an toàn khỏi một số kiểu injection nhưng vẫn cho caller truy cập property hoặc quan hệ không được công bố.

Không coi việc gọi một hàm `sortBy(propertyName)` là authorization. Cần resolver ánh xạ public field sang thuộc tính được phép và giữ quyền, scope cùng chi phí ở mức ứng dụng.

### 10.2. Stored query hoặc read model không tự loại bỏ rủi ro

Nếu một procedure hay query engine tiếp tục dựng cú pháp động bên trong từ string input, vấn đề vẫn còn ở lớp đó. Hợp đồng cần đi đến nơi query thực sự được thực thi.

## 11. Sort và cursor phải cùng mô tả một thứ tự

Với `created_at DESC, id DESC`, trang sau dùng vị trí tương thích:

```sql
AND (p.created_at, p.id) < (:lastCreatedAt, :lastId)
```

Với chiều tăng của cùng hai cột không null, toán tử tiếp tục tương ứng phải thay đổi. Không tái sử dụng một position schema hoặc predicate cho mọi sort.

Cursor cần được ràng buộc với sort plan ID, direction, query và scope theo hợp đồng. Client không được giữ cursor amount rồi đổi request sang createdAt để server diễn giải lại các giá trị khóa.

### 11.1. Khóa hỗn hợp chiều cần logic riêng

Nếu mở rộng catalog để hỗ trợ:

```text
amount_minor DESC, created_at ASC, id ASC
```

thì một điều kiện trang sau cho các cột không null có thể được viết theo dạng:

```sql
AND (
       p.amount_minor < :lastAmount
    OR (p.amount_minor = :lastAmount
        AND p.created_at > :lastCreatedAt)
    OR (p.amount_minor = :lastAmount
        AND p.created_at = :lastCreatedAt
        AND p.id > :lastId)
)
```

Nhóm OR này vẫn phải nằm trong các predicate tenant, quyền và filter bắt buộc. Không mở một nhánh so sánh rồi làm mất scope cho phần sau.

Đây là ví dụ mở rộng, không phải plan đã có trong enum phía trên. Mỗi tổ hợp mới cần schema position và test phù hợp.

### 11.2. Quyền sort có thể đổi giữa hai trang

Caller có thể vẫn được đọc danh sách nhưng không còn được dùng field amount. Cursor cũ không tự giữ khả năng đó đến hết phiên.

Kiểm tra lại quyền và những revision cần thiết. Nếu phải bắt đầu lại, phản hồi rõ ràng; không tự đổi sang sort mặc định rồi dùng position cũ trên thứ tự mới.

### 11.3. Không làm tròn khóa qua client

Timestamp, số nguyên tiền và ID cần giữ đúng biểu diễn server sử dụng để so sánh. Không đưa số tiền hoặc timestamp độ chính xác cao qua một kiểu số làm mất dữ liệu rồi dùng nó làm cursor.

## 12. Sort theo số tiền cần đúng đơn vị nghiệp vụ

`amount_minor` của VND và một tiền tệ khác không tự có cùng ý nghĩa kinh tế. Sắp các con số nguyên với nhau có thể đúng theo máy nhưng sai với nhãn “giá trị tăng dần” mà sản phẩm công bố.

Ví dụ chọn yêu cầu đúng một tiền tệ khi sort amount. Một thiết kế khác có thể dùng giá trị quy đổi do server tính, nhưng cần xác định nguồn tỷ giá, thời điểm, cách làm tròn và quyền sử dụng kết quả đó.

Không lấy tỷ giá hoặc một field `normalizedAmount` từ client để quyết định thứ tự có thẩm quyền.

### 12.1. Field dẫn xuất phải có ngữ nghĩa ổn định

Nếu sort theo trạng thái ưu tiên, mức đến hạn hoặc điểm tổng hợp, cần xác định công thức hoặc phiên bản có liên quan đến hợp đồng.

Một thay đổi công thức có thể làm cursor cũ không còn diễn giải đúng. Có thể cần revision của plan hoặc bắt đầu lại lượt duyệt theo policy.

### 12.2. Sort key mutable không tạo snapshot

Số tiền, trạng thái hoặc due date có thể đổi giữa các trang. Cursor có tính toàn vẹn và thứ tự đủ xác định không tự làm tập dữ liệu bất biến.

API cần công bố LIVE hoặc một read view phù hợp khi cần kết quả cố định. Không hứa không bao giờ lặp hoặc bỏ sót qua mọi update nếu thiết kế không cung cấp bảo đảm đó.

## 13. Giới hạn chi phí và bề mặt mở rộng truy vấn

Một sort hợp lệ về quyền vẫn có thể rất tốn kém. Ví dụ sort theo một phép tính, một quan hệ nhiều dòng hoặc kết quả tổng hợp có thể khác nhiều so với sort theo cột đã được tối ưu cho scope phổ biến.

Cần đánh giá:

- Kiểu query và join mà plan tạo ra.
- Số term và những tổ hợp được hỗ trợ.
- Page size, độ sâu offset hoặc cách tiếp tục.
- Khối lượng dữ liệu theo tenant và scope thực tế.
- Timeout, mức song song và giới hạn chi phí theo policy.
- Index hoặc read model phù hợp nếu cần.

Không coi truy vấn chỉ đọc là không thể gây ảnh hưởng vận hành. Một request nhỏ vẫn có thể yêu cầu một phép sort lớn nếu đầu vào được mở quá rộng.

### 13.1. Giới hạn field không chỉ bằng cấm tên hàm

Một property path thuần ký tự có thể tạo join đắt đỏ. Một field tính sẵn trong read model có thể rẻ hơn một field có tên trông đơn giản nhưng phải tính trên nhiều bảng.

Danh mục cần biết cách thực thi và ngân sách, không chỉ tên công khai.

### 13.2. Không nới scope để query chạy nhanh hơn

Không được bỏ predicate quyền hoặc dùng kết quả cache của tập rộng hơn chỉ vì sort trong scope nhỏ khó tối ưu. Cần tối ưu một query giữ đúng ngữ nghĩa hoặc thay đổi hợp đồng có chủ ý.

Một kế hoạch không hỗ trợ không nên fallback sang query toàn cục hoặc một biểu thức bỏ kiểm tra.

## 14. Thứ tự hiển thị khác với ưu tiên thực thi

Một người được đổi cách xem danh sách không tự được thay scheduler, độ ưu tiên chuyển tiền hoặc thứ tự tiêu thụ quota chung.

Ví dụ lỗi:

```text
Client chọn sort theo một field tự khai.
Server lấy trang đầu rồi mặc định thực thi các hồ sơ đó trước.
Thứ tự hiển thị trở thành quyền ưu tiên dùng tài nguyên hiếm.
```

Nếu sản phẩm chủ ý cho người có thẩm quyền chọn thứ tự xử lý, đó là một khả năng nghiệp vụ cần rule riêng. Nó vẫn không cho bỏ kiểm tra action, số tiền hoặc approval của từng hồ sơ.

### 14.1. “Xử lý những dòng đầu” phải xác định tập thực sự

Một batch từ kết quả search cần biết những ID hoặc query snapshot nào được chọn, cùng những version cần thiết. Không cho một sort tùy ý thay đổi tập được nhận sau khi người dùng đã xác nhận một danh sách khác.

Worker cũng không được lấy `sort` trong payload làm `priority` hoặc tín hiệu bỏ qua hàng đợi nếu chưa có hợp đồng cấp quyền đó.

### 14.2. Quyền đọc không trở thành quyền action

Dù mọi dòng đã được tìm, lọc và sort đúng quyền đọc, bước duyệt, hủy, hoàn tiền hoặc thực thi vẫn phải có authorization và bất biến riêng.

Idempotency của những action đó cũng không được thay bằng việc cursor đã từng đi qua dòng nào.

## 15. Lỗi, cache và quản lý thay đổi

### 15.1. Phân loại lỗi mà không lộ cấu trúc nội bộ

Có thể dùng mã như `SORT_NOT_AVAILABLE` hoặc những mã cụ thể theo hợp đồng. Không trả toàn bộ tên cột, property entity hoặc câu SQL để giải thích lựa chọn không được hỗ trợ.

Input sai, thiếu quyền dùng field, cursor không khớp sort và sự cố query là những nguyên nhân khác nhau cần được quan sát nội bộ. Không đổi mọi lỗi database thành “field không hợp lệ” rồi che một lỗi hệ thống.

### 15.2. Cache cần đúng sort và scope

Cache response không thể chỉ theo từ khóa và page size. Nó cần sort plan, query, tenant, chủ thể hoặc scope cùng những revision mà quyền và ngữ nghĩa phụ thuộc.

Nếu field permission bị thu hồi, token hoặc cache cũ không tự biết điều đó. Cơ chế dùng lại phải đáp ứng giới hạn thu hồi của hệ thống.

### 15.3. Thêm field sort là mở thêm một khả năng API

Mỗi plan mới cần được xem xét về thông tin suy ra, quyền trên scope, kiểu dữ liệu, null, collation, chi phí, cursor và các đường export hoặc batch dùng lại.

Không tự mở sort cho field mới chỉ vì ORM nhận nó hoặc database vừa có một index. Khả năng thực thi và thẩm quyền công bố là hai quyết định khác nhau.

Audit hoặc metric có thể giữ sort plan ID, action, scope revision, số term, kích thước trang và reason code. Không cần ghi dữ liệu nhạy cảm hoặc raw expression không kiểm soát để làm được điều đó.

## 16. Kiểm thử danh mục và truy vấn

### 16.1. Đối chứng đúng và input ngoài hợp đồng

Chuẩn bị actor có quyền đọc, scope không rỗng và filter hợp lệ. Chứng minh một sort được phép trả đúng thứ tự trước khi kiểm tra các input bị từ chối.

| Trường hợp | Kết quả cần chứng minh |
| --- | --- |
| Không có sort | Dùng đúng plan mặc định được cấp |
| Field công khai hợp lệ và direction được hỗ trợ | Chọn đúng plan |
| Tên cột nội bộ thay public field | Không tự mở thêm alias ngoài hợp đồng |
| Tên field hợp lệ về cú pháp nhưng bị bảo vệ | Không được chấp nhận chỉ vì regex cho qua |
| Biểu thức hoặc tên hàm | Không được đưa vào query cấu trúc |
| Direction có nội dung ngoài tập cho phép | Bị từ chối, không nối nguyên chuỗi |
| Field hoặc direction thiếu trong object đã gửi | Không dùng mặc định mơ hồ ngoài hợp đồng |
| Nhiều tham số xung đột hoặc quá nhiều term | Hành vi rõ ràng, không validate một giá trị rồi dùng giá trị khác |

Không dùng một actor đã bị chặn từ authentication để kết luận resolver sort an toàn. Những hàng rào đó cần test riêng.

### 16.2. Quyền field và tenant

1. Caller đọc summary nhưng không được sort amount.
2. Caller có quyền amount ở một phần scope nhưng không phải toàn tập.
3. Caller giữ cursor amount sau khi quyền field bị thu hồi.
4. Sort qua một quan hệ khác tenant hoặc field ngoài quyền.
5. Mọi sort được phép vẫn không trả hàng ngoài scope.
6. Quyền admin cục bộ không tự mở field nội bộ của nền tảng.

Kiểm tra dữ liệu, metadata và cursor trả về, không chỉ tên plan được chọn.

### 16.3. Thứ tự và tính đầy đủ trên dataset cố định

Tạo nhiều dòng có cùng thời điểm, cùng số tiền và ID khác nhau. Duyệt hết mọi trang cho từng plan được phép, kiểm tra:

```text
thứ tự đúng theo plan
không có dòng lặp trái hợp đồng
không bỏ dòng được phép
hợp toàn bộ trang bằng tập khớp được phép
```

Thay sort có thể đổi thành phần trang đầu một cách hợp lệ, nên không yêu cầu các trang đầu phải có cùng ID ở mọi plan. Trên dataset cố định với cùng filter và quyền, tập đầy đủ sau khi duyệt hết mới là đối tượng so sánh phù hợp.

Với string hoặc kiểu dữ liệu có comparator riêng, expected result phải theo hợp đồng đã công bố, không mặc định dùng thứ tự chuỗi Java rồi cho rằng database sai.

### 16.4. Null, tiền tệ và cursor

- Field nullable đứng đúng nhóm và vị trí đã chọn.
- Những dòng nằm ở ranh giới null không bị bỏ hoặc lặp.
- Amount sort yêu cầu đúng điều kiện tiền tệ của plan.
- Không có mất độ chính xác khi serialize position.
- Cursor của plan khác bị xử lý rõ ràng, không đổi sort ngầm.
- Plan nhiều chiều nếu được hỗ trợ có predicate tiếp tục đúng từng term.
- Thay dữ liệu hoặc quyền giữa các trang tuân theo LIVE hoặc snapshot contract.

### 16.5. Điểm vào và thay đổi model

Kiểm tra endpoint web, export, report và worker nào có thể sử dụng cùng sort input. Một đường dùng allowlist không bảo vệ một đường khác truyền property trực tiếp vào ORM.

Khi thêm field entity hoặc index, xác nhận nó không tự được sort bởi API cũ. Những bảo đảm về query, kiểu dữ liệu, cursor và kế hoạch thực thi cần test ở tầng phù hợp; mock repository trả sẵn một danh sách đã sort không chứng minh database query được bảo vệ.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao có vấn đề | Hướng thay thế |
| --- | --- | --- |
| Nối field và direction client vào SQL | Input trở thành cú pháp truy vấn | Catalog plan cố định và bind giá trị |
| Dùng `ORDER BY ?` như tên cột động | Không có ngữ nghĩa chọn cột mong muốn | Ánh xạ public choice sang expression đã kiểm soát |
| Regex đúng là coi được phép | Field hợp lệ cú pháp vẫn có thể nhạy cảm | Danh mục theo endpoint, action và scope |
| Không trả field thì cho sort thoải mái | Thứ tự có thể tiết lộ thông tin tương đối | Quyền sử dụng field cho sort rõ ràng |
| Role amount ở một đơn vị áp dụng cho toàn tập | Ghép quyền field với scope rộng hơn | Kiểm tra trên tập đối tượng thực sự tham gia |
| ORM xử lý property là đủ | Có thể mở quan hệ hoặc query ngoài hợp đồng | Resolver trước lớp truy cập dữ liệu |
| Mọi sort dùng cùng cursor predicate | Sai chiều hoặc kiểu khóa, dễ mất dòng | Plan ID và position schema tương thích |
| Sort không phá hòa | Pagination không có thứ tự đủ xác định | Khóa phụ duy nhất trong scope |
| Null hoặc collation theo mặc định không được mô tả | Các lớp có thể hiểu vị trí khác nhau | Ngữ nghĩa và test riêng |
| Sort số tiền khác đơn vị như cùng nghĩa | Máy so đúng số nhưng sản phẩm diễn đạt sai | Một tiền tệ hoặc giá trị quy đổi có thẩm quyền |
| Sort hiển thị quyết định ưu tiên thực thi ngầm | Mở một khả năng nghiệp vụ khác | Policy và command riêng cho thứ tự xử lý |
| Field mới tự được mở theo entity | Schema change trở thành quyền mới | Catalog đóng và đánh giá thay đổi |

## 18. Bài tập thiết kế

Thiết kế danh mục sort cho danh sách đề nghị thanh toán nhiều tenant. Mặc định sắp theo thời điểm tạo, có thể chọn tăng hoặc giảm; sort theo số tiền chỉ mở cho những scope đủ quyền và có tiền tệ xác định.

Hãy mô tả:

1. Public field được ánh xạ vào những plan nội bộ nào?
2. Vì sao bind tên cột hoặc chỉ dùng regex không đủ?
3. Quyền sort amount được kiểm tra ra sao khi scope gồm nhiều nguồn quyền khác nhau?
4. Null, khóa phá hòa, collation và độ chính xác được định nghĩa thế nào?
5. Cursor ràng buộc plan, direction và position schema bằng cách nào?
6. Những giới hạn chi phí và số term nào cần áp dụng theo query thực tế?
7. Điều gì ngăn sort của màn hình trở thành quyền ưu tiên xử lý hoặc bỏ kiểm tra action?
8. Những test nào chứng minh field nội bộ, property path và cursor cũ không mở thêm dữ liệu hoặc làm sai tập kết quả?

Một thiết kế đạt yêu cầu phải kiểm soát được cả cú pháp lẫn ý nghĩa của lựa chọn sắp xếp, giữ đúng phạm vi dữ liệu và không để một tùy chọn trình bày âm thầm trở thành quyền truy vấn hoặc điều khiển nghiệp vụ rộng hơn.
