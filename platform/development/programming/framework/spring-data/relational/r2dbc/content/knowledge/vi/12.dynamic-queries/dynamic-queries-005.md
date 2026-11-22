# Tạo điều kiện từ bộ lọc tùy chọn mà không mở rộng truy vấn ngoài ý muốn

Trong một ứng dụng Spring Data Relational R2DBC, màn hình tìm kiếm thường cho phép người dùng nhập một số bộ lọc tùy chọn: tên, trạng thái, khoảng thời gian, người phụ trách hoặc danh sách ID. Người dùng có thể chỉ nhập một bộ lọc, kết hợp nhiều bộ lọc hoặc để trống một số trường.

Truy vấn cần được xây dựng sao cho mỗi bộ lọc chỉ ảnh hưởng đúng phạm vi dữ liệu mà người dùng yêu cầu. Một điều kiện bị bỏ qua nhầm có thể làm kết quả rộng hơn dự kiến. Với truy vấn đọc, lỗi này có thể làm lộ dữ liệu ngoài phạm vi. Với UPDATE hoặc DELETE, hậu quả có thể là thay đổi hàng loạt bản ghi.

Nguyên tắc cốt lõi là: **xác định rõ ý nghĩa của từng trạng thái bộ lọc, chỉ ghép các predicate được phép, bind giá trị thay vì nối input vào SQL, và kiểm tra phạm vi truy vấn trước khi thực thi**.

## 1. Bộ lọc tùy chọn là gì?

Giả sử màn hình tìm kiếm khách hàng có các trường:

- Tên hoặc một phần tên.
- Trạng thái hoạt động.
- Người phụ trách.
- Ngày tạo từ và đến.
- Một danh sách ID khách hàng.

Người dùng có thể chỉ tìm khách hàng theo trạng thái, hoặc kết hợp trạng thái với ngày tạo. Ứng dụng cần tạo WHERE tương ứng.

Ví dụ chỉ lọc theo trạng thái:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status;
~~~

Khi lọc cả trạng thái và người phụ trách:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status
  AND owner_id = :ownerId;
~~~

Khi chỉ lọc theo ngày tạo:

~~~sql
SELECT id, name, status
FROM customer
WHERE created_at >= :createdFrom;
~~~

Điều kiện không được cung cấp sẽ không xuất hiện trong WHERE. Tuy nhiên, việc bỏ một điều kiện làm phạm vi kết quả rộng hơn. Vì thế, ứng dụng cần xác định trường nào thật sự tùy chọn và trường nào là điều kiện bắt buộc như tenant, tổ chức hoặc quyền truy cập.

## 2. Phân biệt absent, null, rỗng, false và 0

Một lỗi thường gặp là xem tất cả giá trị “không có nội dung” như nhau. Trong thực tế, chúng có thể mang ý nghĩa khác nhau.

| Trạng thái đầu vào | Ví dụ | Ý nghĩa có thể có |
|---|---|---|
| Không gửi trường | Không có key status | Người dùng không yêu cầu lọc theo trạng thái |
| Gửi null | status = null | Có thể là không lọc, hoặc yêu cầu tìm giá trị SQL NULL tùy hợp đồng |
| Chuỗi rỗng | name = "" | Thường chuẩn hóa thành không lọc; đôi khi là tìm chuỗi rỗng |
| Danh sách rỗng | ownerIds = [] | Có thể có nghĩa không chọn ai, tức không có kết quả |
| Boolean false | active = false | Đây là một giá trị lọc hợp lệ, không phải trạng thái thiếu |
| Số 0 | priority = 0 | Đây có thể là giá trị lọc hợp lệ |

Không nên viết điều kiện dựa trên kiểm tra truthy/falsy chung chung. Ví dụ, nếu dùng:

~~~java
if (filter.active()) {
    // add predicate
}
~~~

thì giá trị false sẽ bị bỏ qua, dù người dùng muốn tìm các khách hàng không hoạt động.

Với Boolean tùy chọn, nên dùng kiểu wrapper:

~~~java
if (filter.active() != null) {
    // false vẫn được thêm vào query và được bind
}
~~~

Tương tự, với số có thể bằng 0, kiểm tra null thay vì kiểm tra lớn hơn 0 nếu 0 là giá trị hợp lệ.

### Chọn một quy ước rõ ràng cho API

Một quy ước phổ biến:

- Không gửi trường hoặc gửi null: không áp dụng predicate tương ứng.
- Chuỗi chỉ có khoảng trắng: chuẩn hóa thành không lọc.
- Boolean false và số 0: vẫn là giá trị lọc.
- Danh sách null: không áp dụng bộ lọc danh sách.
- Danh sách rỗng: trả về không có kết quả, hoặc từ chối đầu vào theo hợp đồng API.

Nếu cần tìm các dòng có cột SQL NULL, hãy biểu diễn yêu cầu đó một cách tường minh, ví dụ bằng một filter mode riêng hoặc cờ isNull, rồi tạo predicate column IS NULL. Không thể dùng phép so sánh column = :value với một giá trị null để thay thế cho IS NULL, vì trong SQL phép so sánh với NULL cho kết quả UNKNOWN.

## 3. Mô hình hóa bộ lọc trước khi tạo SQL

Nên gom các tiêu chí tìm kiếm vào một kiểu dữ liệu riêng thay vì truyền nhiều tham số rời rạc qua các tầng.

~~~java
public record CustomerFilter(
    String name,
    String status,
    Boolean active,
    Long ownerId,
    Instant createdFrom,
    Instant createdTo,
    List<Long> ownerIds
) {
}
~~~

Kiểu dữ liệu này chỉ mô tả đầu vào tìm kiếm. Nó không phải entity persistence và không nên được lưu vào bảng customer.

Trước khi xây dựng truy vấn, chuẩn hóa và kiểm tra filter:

- Trim chuỗi tên và chuyển chuỗi trắng thành absent nếu hợp đồng quy định như vậy.
- Kiểm tra createdFrom không lớn hơn createdTo.
- Giới hạn độ dài chuỗi tìm kiếm.
- Giới hạn số phần tử trong danh sách ID.
- Kiểm tra ID và trạng thái có nằm trong miền giá trị hợp lệ.
- Không bỏ qua Boolean false hoặc số 0.

Ví dụ kiểm tra khoảng thời gian:

~~~java
if (filter.createdFrom() != null
        && filter.createdTo() != null
        && filter.createdFrom().isAfter(filter.createdTo())) {
    throw new IllegalArgumentException(
        "createdFrom must not be after createdTo"
    );
}
~~~

Việc xác thực nên diễn ra trước khi gọi database. Một filter sai không nên được âm thầm bỏ qua, vì bỏ qua nó có thể khiến truy vấn trả về nhiều dữ liệu hơn.

## 4. Ghép predicate bằng AND

Trong nhiều màn hình tìm kiếm, các bộ lọc độc lập được kết hợp bằng AND: một dòng phải thỏa mãn tất cả điều kiện đã được cung cấp.

Ví dụ:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status
  AND active = :active
  AND created_at >= :createdFrom;
~~~

Nếu người dùng chỉ gửi status và active, predicate created_at sẽ không được thêm. Không nên tạo placeholder cho mọi filter rồi bind null một cách tùy tiện.

Một cách tiếp cận dễ kiểm soát là lưu riêng:

- Danh sách mệnh đề SQL cố định do ứng dụng tạo.
- Map chứa tên tham số và giá trị cần bind.

Sau đó ghép các predicate bằng AND và bind từng giá trị.

## 5. Ví dụ DatabaseClient với các filter tùy chọn

Ví dụ sau xây dựng câu SELECT theo filter. Điều kiện tenant là bắt buộc, còn tên, trạng thái, active, owner và thời gian là tùy chọn.

~~~java
public Flux<CustomerSummary> search(
        Long tenantId,
        CustomerFilter filter) {

    List<String> predicates = new ArrayList<>();
    Map<String, Object> parameters = new LinkedHashMap<>();

    // Điều kiện phạm vi bắt buộc, không được bỏ qua.
    predicates.add("c.tenant_id = :tenantId");
    parameters.put("tenantId", tenantId);

    if (filter.name() != null && !filter.name().isBlank()) {
        predicates.add("LOWER(c.name) LIKE :name");
        parameters.put(
            "name",
            "%" + filter.name().trim().toLowerCase(Locale.ROOT) + "%"
        );
    }

    if (filter.status() != null) {
        predicates.add("c.status = :status");
        parameters.put("status", filter.status());
    }

    if (filter.active() != null) {
        predicates.add("c.active = :active");
        parameters.put("active", filter.active());
    }

    if (filter.ownerId() != null) {
        predicates.add("c.owner_id = :ownerId");
        parameters.put("ownerId", filter.ownerId());
    }

    if (filter.createdFrom() != null) {
        predicates.add("c.created_at >= :createdFrom");
        parameters.put("createdFrom", filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        predicates.add("c.created_at < :createdTo");
        parameters.put("createdTo", filter.createdTo());
    }

    String sql =
        "SELECT c.id, c.name, c.status " +
        "FROM customer c " +
        "WHERE " + String.join(" AND ", predicates) +
        " ORDER BY c.created_at DESC";

    DatabaseClient.GenericExecuteSpec spec =
        databaseClient.sql(sql);

    for (Map.Entry<String, Object> entry : parameters.entrySet()) {
        spec = spec.bind(entry.getKey(), entry.getValue());
    }

    return spec.map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    )).all();
}
~~~

Trong ví dụ:

1. Predicate tenant luôn được thêm, bảo đảm query không vượt khỏi phạm vi tenant.
2. Mỗi filter tùy chọn chỉ thêm một predicate khi có giá trị hợp lệ.
3. Giá trị filter được đưa vào map và bind riêng.
4. Chỉ các mệnh đề SQL do code kiểm soát mới được ghép thành chuỗi.
5. Query trả về Flux vì có thể có nhiều dòng.

Đây là một mẫu triển khai. Các import, kiểu CustomerSummary, DatabaseClient và repository thuộc ứng dụng cụ thể. Cú pháp named parameter được Spring DatabaseClient xử lý theo cơ chế mở rộng tham số và driver R2DBC tương ứng.

### Vì sao không viết một câu SQL cố định cho mọi filter?

Một cách thường thấy là:

~~~sql
SELECT id, name
FROM customer
WHERE (:status IS NULL OR status = :status)
  AND (:ownerId IS NULL OR owner_id = :ownerId);
~~~

Mẫu này có thể phù hợp trong một số trường hợp, nhưng có những điểm cần cân nhắc:

- Phải bind null đúng kiểu cho driver.
- Predicate luôn xuất hiện, dù filter không được cung cấp.
- Các biểu thức OR có thể làm optimizer khó tận dụng index trong một số database.
- Không diễn đạt rõ sự khác nhau giữa “bỏ qua filter” và “tìm cột có giá trị NULL”.
- Khi có nhiều filter, SQL phình to và khó đọc.

Ghép predicate động thường rõ ràng hơn khi có nhiều điều kiện tùy chọn. Nếu dùng câu SQL cố định, hãy xác định semantics null rõ ràng và đo execution plan trên database mục tiêu.

## 6. Bind giá trị thay vì nối input vào SQL

Không bao giờ nối trực tiếp dữ liệu người dùng vào câu SQL:

~~~java
String sql =
    "SELECT id, name FROM customer WHERE name = '" +
    request.name() + "'";
~~~

Nếu input chứa dấu nháy hoặc nội dung SQL, câu truy vấn có thể bị thay đổi ngoài ý muốn. Đây là nguy cơ SQL injection.

Hãy dùng placeholder và bind:

~~~java
databaseClient.sql(
        "SELECT id, name FROM customer WHERE name = :name"
    )
    .bind("name", request.name())
    .map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    ))
    .all();
~~~

Bind parameter bảo vệ giá trị dữ liệu khỏi bị diễn giải như một phần cú pháp SQL. Tuy nhiên, bind không thay thế xác thực nghiệp vụ và không áp dụng được cho mọi thành phần SQL.

### Những gì có thể và không thể bind

Thông thường có thể bind:

- Chuỗi.
- Số.
- Boolean.
- Ngày giờ.
- UUID.
- Các giá trị mà R2DBC driver hỗ trợ codec.

Không thể dùng bind parameter để thay thế:

- Tên bảng.
- Tên cột.
- Từ khóa ASC hoặc DESC.
- Toán tử SQL.
- Một đoạn ORDER BY tùy ý.

Ví dụ sau không có tác dụng như mong đợi:

~~~sql
SELECT * FROM customer ORDER BY :columnName;
~~~

Parameter ở đây là một giá trị, không phải identifier. Muốn sắp xếp theo trường động, phải chọn từ danh sách identifier cố định do ứng dụng cho phép.

## 7. Xây dựng IN với danh sách tùy chọn

Một filter có thể chứa nhiều ID:

~~~java
List<Long> ownerIds = filter.ownerIds();
~~~

Không nên mặc định bind cả collection vào một placeholder như thể mọi R2DBC driver đều tự mở rộng danh sách cho mệnh đề IN. Cần tạo một bind marker cho từng phần tử hoặc dùng abstraction có hỗ trợ collection expansion trong phiên bản framework đang dùng.

Ví dụ tạo marker theo chỉ số:

~~~java
if (filter.ownerIds() != null) {
    List<Long> ids = filter.ownerIds();

    if (ids.isEmpty()) {
        // Quy ước: danh sách rỗng nghĩa là không có owner nào được chọn.
        predicates.add("1 = 0");
    } else {
        List<String> markers = new ArrayList<>();

        for (int i = 0; i < ids.size(); i++) {
            String parameterName = "ownerId" + i;
            markers.add(":" + parameterName);
            parameters.put(parameterName, ids.get(i));
        }

        predicates.add(
            "c.owner_id IN (" + String.join(", ", markers) + ")"
        );
    }
}
~~~

Tên placeholder được tạo từ chỉ số do code kiểm soát. Giá trị ID thực tế vẫn được bind, không nối vào SQL.

Phải chọn semantics rõ ràng cho danh sách:

| Giá trị ownerIds | Ý nghĩa được chọn trong ví dụ |
|---|---|
| null | Không áp dụng filter owner |
| Danh sách rỗng | Không có kết quả, predicate luôn false |
| Có phần tử | Chỉ lấy các owner nằm trong danh sách |

Nếu API quy định danh sách rỗng có nghĩa là không lọc, hãy triển khai đúng quy ước đó. Không để hành vi phụ thuộc ngẫu nhiên vào việc SQL tạo ra IN () hay driver có chấp nhận cú pháp đó không.

Nên giới hạn số phần tử trong danh sách để tránh tạo câu SQL quá lớn và vượt giới hạn bind parameter của database.

## 8. Kết hợp AND và OR mà không mở rộng sai phạm vi

Toán tử AND và OR có độ ưu tiên khác nhau. Khi ghép điều kiện động, thiếu dấu ngoặc có thể khiến query trả về nhiều dòng hơn dự kiến.

Giả sử nghiệp vụ muốn tìm khách hàng thuộc tenant hiện tại và thỏa mãn một trong hai điều kiện: trạng thái ACTIVE hoặc được giao cho người dùng hiện tại.

Điều kiện đúng:

~~~sql
WHERE tenant_id = :tenantId
  AND (status = 'ACTIVE' OR owner_id = :currentUserId)
~~~

Nếu viết thiếu ngoặc:

~~~sql
WHERE tenant_id = :tenantId
  AND status = 'ACTIVE'
   OR owner_id = :currentUserId
~~~

Do AND được đánh giá trước OR, câu thứ hai tương đương:

~~~sql
WHERE (tenant_id = :tenantId AND status = 'ACTIVE')
   OR owner_id = :currentUserId
~~~

Như vậy, các dòng có owner_id bằng người dùng hiện tại có thể được lấy kể cả khi thuộc tenant khác. Đây là lỗi mở rộng phạm vi dữ liệu.

Khi tạo nhóm OR động, luôn bọc nhóm trong ngoặc:

~~~java
predicates.add(
    "(c.status = :status OR c.owner_id = :ownerId)"
);
~~~

Nếu một nhánh OR là tùy chọn, hãy xác định rõ cách xây dựng nhóm khi chỉ còn một nhánh. Không thêm một nhánh trống hoặc bỏ ngoặc theo cách làm thay đổi logic của điều kiện bên ngoài.

### Ví dụ ghép nhóm có chủ đích

~~~sql
WHERE tenant_id = :tenantId
  AND deleted = false
  AND (
       status = :status
       OR priority >= :minimumPriority
  )
  AND created_at >= :createdFrom
~~~

Trong ví dụ này, tenant và điều kiện chưa xóa luôn bắt buộc. Nhóm OR chỉ quyết định điều kiện nghiệp vụ bên trong; nó không thể bỏ qua tenant hoặc deleted.

## 9. Bộ lọc chuỗi và ký tự wildcard

Tham số hóa giá trị ngăn SQL injection, nhưng ký tự wildcard của LIKE vẫn có ý nghĩa tìm kiếm:

- % khớp với chuỗi có độ dài bất kỳ.
- _ khớp với một ký tự.

Nếu người dùng nhập %, truy vấn LIKE có thể khớp rất nhiều dòng. Điều đó không phải SQL injection, nhưng có thể là mở rộng kết quả ngoài ý muốn.

Nếu mục tiêu là tìm chuỗi literal, cần escape wildcard %, _ và ký tự escape theo cú pháp của database, sau đó dùng mệnh đề ESCAPE phù hợp. Quy tắc escape có thể khác giữa vendor nên cần kiểm tra dialect/database đang dùng.

Ngoài ra:

- Chuẩn hóa chữ hoa/chữ thường theo yêu cầu nghiệp vụ.
- Giới hạn độ dài input.
- Cân nhắc collation và cách database so sánh dấu tiếng Việt.
- Không tự thêm wildcard nếu nghiệp vụ yêu cầu khớp chính xác.
- Tránh tìm kiếm chuỗi rỗng theo kiểu %% ngoài ý muốn.

## 10. Sắp xếp động và phân trang

Người dùng có thể chọn sắp xếp theo tên, ngày tạo hoặc trạng thái. Tên cột không thể bind như một giá trị, do đó không được nối trực tiếp nội dung sort từ request.

Hãy dùng whitelist:

~~~java
public enum CustomerSortField {
    NAME("c.name"),
    CREATED_AT("c.created_at"),
    STATUS("c.status");

    private final String sqlExpression;

    CustomerSortField(String sqlExpression) {
        this.sqlExpression = sqlExpression;
    }

    public String sqlExpression() {
        return sqlExpression;
    }
}
~~~

Chiều sắp xếp cũng nên được chuyển từ enum hoặc boolean đã xác thực:

~~~java
String direction =
    requestedDirection == SortDirection.ASC ? "ASC" : "DESC";

String orderBy =
    sortField.sqlExpression() + " " + direction;
~~~

Chỉ giá trị lấy từ whitelist mới được ghép vào SQL. Không sử dụng chuỗi sort nguyên bản do client gửi.

Với phân trang:

- Giới hạn page size tối đa.
- Kiểm tra page và offset không âm.
- Chọn cú pháp LIMIT/OFFSET phù hợp database hoặc dùng abstraction hỗ trợ dialect.
- Luôn có ORDER BY ổn định, tốt nhất thêm ID làm tie-breaker.
- Không để người dùng chọn sort field ngoài danh sách cho phép.

Một sort order không ổn định có thể khiến bản ghi lặp hoặc bị bỏ qua giữa các trang khi dữ liệu thay đổi.

## 11. Không để thiếu filter làm mở rộng truy vấn ngoài ý muốn

Đây là điểm cần đặc biệt chú ý. Khi tất cả filter tùy chọn đều vắng mặt, danh sách predicate có thể rỗng. Nếu code nối chuỗi theo cách:

~~~java
String sql = "SELECT * FROM customer WHERE "
    + String.join(" AND ", predicates);
~~~

thì có thể tạo SQL sai cú pháp. Một cách khác là bỏ hẳn WHERE, dẫn đến truy vấn toàn bộ bảng. Đôi khi query toàn bảng là hợp lệ, nhưng không nên để nó xảy ra ngầm chỉ vì người dùng không nhập filter.

Hãy quyết định rõ chính sách:

| Ngữ cảnh | Hành vi khi không có filter tùy chọn |
|---|---|
| Danh sách công khai có phân trang | Có thể cho phép lấy danh sách trong phạm vi được phép |
| Tìm kiếm dữ liệu lớn | Yêu cầu ít nhất một tiêu chí hoặc giới hạn chặt |
| Dữ liệu nhiều tenant | Luôn áp dụng tenant predicate bắt buộc |
| Dữ liệu theo quyền người dùng | Luôn áp dụng predicate quyền truy cập |
| UPDATE hoặc DELETE | Không thực thi nếu thiếu điều kiện phạm vi bắt buộc |

Ví dụ bảo vệ truy vấn tìm kiếm:

~~~java
if (selectedOptionalFilterCount == 0
        && !filter.allowUnfilteredSearch()) {
    return Flux.error(
        new IllegalArgumentException(
            "At least one search filter is required"
        )
    );
}
~~~

Nếu cho phép truy vấn không filter, hãy yêu cầu một lựa chọn tường minh hoặc áp dụng phân trang/giới hạn kết quả và predicate quyền truy cập.

### Điều kiện bắt buộc phải tách khỏi điều kiện tùy chọn

Ví dụ tenant_id không được xem là một filter tùy chọn nếu người dùng chỉ được xem dữ liệu tenant của mình:

~~~java
predicates.add("c.tenant_id = :tenantId");
parameters.put("tenantId", authenticatedTenantId);
~~~

Giá trị tenant nên lấy từ ngữ cảnh xác thực đã được kiểm tra, không tin một tenantId tùy ý trong query string của client. Các filter do người dùng gửi chỉ được thu hẹp phạm vi bên trong tập dữ liệu mà họ có quyền truy cập.

## 12. Bộ lọc động cho UPDATE và DELETE cần guard nghiêm ngặt hơn

Với SELECT, bỏ hết filter có thể làm truy vấn trả về toàn bộ dữ liệu trong phạm vi quyền được phép. Với UPDATE hoặc DELETE, bỏ một predicate có thể thay đổi hoặc xóa hàng loạt bản ghi.

Ví dụ nguy hiểm:

~~~java
String sql = "DELETE FROM customer";

if (filter.status() != null) {
    sql += " WHERE status = :status";
}
~~~

Nếu status không được gửi, câu lệnh sẽ xóa toàn bộ bảng customer.

Hãy xây dựng các điều kiện bắt buộc trước:

~~~java
List<String> predicates = new ArrayList<>();
Map<String, Object> parameters = new LinkedHashMap<>();

predicates.add("tenant_id = :tenantId");
parameters.put("tenantId", tenantId);

if (filter.customerId() == null
        && filter.status() == null) {
    return Mono.error(
        new IllegalArgumentException(
            "A customer ID or status filter is required"
        )
    );
}

if (filter.customerId() != null) {
    predicates.add("id = :customerId");
    parameters.put("customerId", filter.customerId());
}

if (filter.status() != null) {
    predicates.add("status = :status");
    parameters.put("status", filter.status());
}

String sql =
    "DELETE FROM customer WHERE " +
    String.join(" AND ", predicates);
~~~

Ví dụ minh họa nguyên tắc guard. Phần thực thi vẫn cần bind tất cả tham số và kiểm tra số dòng bị tác động. Với thao tác nguy hiểm, nên có giới hạn nghiệp vụ, audit và cơ chế xác nhận phù hợp.

Không nên dùng một cờ allowAll do client tự gửi để bỏ qua toàn bộ điều kiện. Nếu có nghiệp vụ quản trị cần thao tác hàng loạt, quyền đó phải được kiểm soát riêng ở tầng authorization và có API/command rõ ràng.

## 13. Query động bằng repository, Criteria và DatabaseClient

Có nhiều mức abstraction để tạo truy vấn:

| Cách tiếp cận | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| Derived query method | Một số ít tổ hợp điều kiện ổn định | Nhiều filter có thể làm số method tăng nhanh |
| @Query | Câu SQL cố định, dễ mô tả | Filter tùy chọn phức tạp có thể khó biểu diễn |
| R2dbcEntityTemplate và Criteria | Query động cần mapping entity và các predicate được abstraction hỗ trợ | API/operator cụ thể phụ thuộc phiên bản Spring Data |
| DatabaseClient | SQL động, join, projection và truy vấn tùy chỉnh | Ứng dụng phải quản lý cấu trúc SQL, bind và mapping |

Ví dụ derived query:

~~~java
Flux<Customer> findByStatusAndActive(
    String status,
    boolean active
);
~~~

Đây là lựa chọn đơn giản khi cả hai điều kiện đều bắt buộc. Nếu mỗi điều kiện có thể vắng mặt độc lập và có nhiều tổ hợp, việc tạo hàng loạt method như findByStatus, findByOwner, findByStatusAndOwner... sẽ khó bảo trì.

Với Criteria hoặc Query abstraction của Spring Data Relational, có thể ghép các điều kiện được hỗ trợ theo filter. Cần dùng đúng API của phiên bản Spring Data đang triển khai và kiểm tra các toán tử mà dialect/database hỗ trợ. Với SQL tùy chỉnh nhiều join hoặc logic đặc thù, DatabaseClient cho phép kiểm soát câu lệnh rõ ràng hơn.

## 14. Kiểm soát phạm vi dữ liệu và bảo mật

Bộ lọc tùy chọn là một phần của truy vấn, nhưng không nên được dùng thay cho authorization. Việc client gửi ownerId hoặc tenantId không chứng minh họ có quyền đọc dữ liệu tương ứng.

Nên chia điều kiện thành hai nhóm:

**Điều kiện phạm vi bắt buộc**

- Tenant hoặc tổ chức của người dùng hiện tại.
- Quyền sở hữu hoặc phạm vi dữ liệu được phép.
- Điều kiện soft-delete nếu ứng dụng luôn ẩn bản ghi đã xóa.
- Các ràng buộc phân vùng dữ liệu của hệ thống.

**Điều kiện tìm kiếm tùy chọn**

- Tên, trạng thái, ngày tạo.
- ID người phụ trách.
- Khoảng giá trị hoặc nhóm phân loại.
- Từ khóa tìm kiếm.

Luôn ghép điều kiện phạm vi bắt buộc bằng AND ở ngoài nhóm OR do người dùng chọn. Không cho một predicate OR làm mất hiệu lực của tenant hoặc quyền truy cập.

Ví dụ:

~~~sql
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND (
       status = :status
       OR owner_id = :ownerId
  )
~~~

Nếu query có nhiều nhóm điều kiện, hãy viết rõ từng nhóm bằng ngoặc và đặt tên biến theo mục đích. Tránh tạo một biểu thức dài với nhiều OR lồng nhau khó kiểm soát.

## 15. Hiệu năng của truy vấn động

Truy vấn động giúp chỉ đưa predicate cần thiết vào SQL, nhưng số lượng tổ hợp filter có thể lớn. Một số điểm nên cân nhắc:

- Tạo index cho các cột thường được lọc và sắp xếp theo workload thực tế.
- Không tạo index cho mọi tổ hợp filter một cách máy móc.
- Kiểm tra execution plan cho những tổ hợp truy vấn phổ biến và có chi phí cao.
- Tránh áp dụng hàm lên cột trong WHERE nếu khiến index thông thường không được sử dụng, ví dụ LOWER(column), trừ khi có functional index phù hợp.
- Giới hạn page size và danh sách IN.
- Chỉ chọn các cột cần thiết thay vì SELECT *.
- Cân nhắc truy vấn riêng cho những tổ hợp đặc biệt thay vì một SQL tổng quát quá phức tạp.
- Dùng metric/log để biết người dùng thực sự sử dụng filter nào.

Một câu SQL có ít predicate hơn không luôn nhanh hơn. Tốc độ phụ thuộc selectivity, index, thống kê, join, số dòng và optimizer của database.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng if(boolean) cho Boolean tùy chọn | Filter false bị bỏ qua | Kiểm tra khác null |
| Dùng if(number > 0) khi 0 hợp lệ | Filter giá trị 0 bị bỏ qua | Kiểm tra null và validation riêng |
| Xem list rỗng giống list null | Trả quá nhiều dữ liệu hoặc tạo IN () | Quy định semantics riêng cho null và empty |
| Nối input vào SQL | SQL injection | Bind tất cả giá trị |
| Bind tên cột hoặc ORDER BY | Không hoạt động như identifier | Dùng whitelist |
| Ghép OR thiếu ngoặc | Bỏ qua tenant hoặc điều kiện bắt buộc | Nhóm OR trong ngoặc |
| Bỏ WHERE khi không có filter | SELECT toàn bảng ngoài ý muốn | Yêu cầu filter, phân trang hoặc lựa chọn rõ ràng |
| UPDATE/DELETE không có guard | Thay đổi/xóa hàng loạt | Điều kiện bắt buộc và kiểm tra trước thực thi |
| Dùng null để tìm SQL NULL | Predicate không cho kết quả mong đợi | Dùng IS NULL tường minh |
| LIKE với wildcard không kiểm soát | Kết quả rộng ngoài ý muốn | Escape wildcard khi cần tìm literal |
| Quên tenant predicate | Truy cập chéo tenant | Thêm điều kiện phạm vi từ context xác thực |
| Quá nhiều phần tử IN | SQL lớn, vượt giới hạn bind | Giới hạn, chia batch hoặc dùng chiến lược database phù hợp |

## 17. Quy trình xây dựng một truy vấn động an toàn

Có thể áp dụng trình tự sau cho một màn hình tìm kiếm:

1. Xác định các filter bắt buộc và filter tùy chọn.
2. Định nghĩa rõ absent, null, chuỗi rỗng, danh sách rỗng, false và 0.
3. Chuẩn hóa và xác thực đầu vào trước khi tạo SQL.
4. Thêm các predicate phạm vi bắt buộc như tenant và quyền truy cập.
5. Thêm predicate tùy chọn theo đúng semantics.
6. Nhóm các điều kiện AND/OR bằng ngoặc rõ ràng.
7. Bind toàn bộ giá trị; chỉ ghép identifier hoặc SQL fragment từ whitelist cố định.
8. Kiểm tra trường hợp không có filter và quyết định có cho phép query rộng hay không.
9. Áp dụng phân trang, giới hạn và thứ tự ổn định.
10. Kiểm thử các tổ hợp filter, đặc biệt trường hợp rỗng, false, 0, list empty và điều kiện OR.

Với UPDATE hoặc DELETE, thêm bước guard riêng để từ chối thao tác khi thiếu điều kiện phạm vi an toàn. Không tái sử dụng một builder SELECT cho mutation nếu builder đó cho phép mọi predicate tùy chọn biến mất.

## 18. Ghi nhớ

- Filter tùy chọn cần có semantics rõ ràng; null, chuỗi rỗng, danh sách rỗng, false và 0 không mặc nhiên giống nhau.
- Dùng wrapper Boolean và kiểm tra null để giữ được filter có giá trị false.
- Ghép predicate động bằng danh sách điều kiện và bind map giúp SQL dễ kiểm soát.
- Chỉ nối các SQL fragment cố định do code kiểm soát; không nối input người dùng.
- Bind parameter dùng cho giá trị, không dùng thay tên cột, bảng, toán tử hoặc hướng sắp xếp.
- Với IN, quy định rõ list null và list empty; tạo placeholder riêng hoặc dùng cơ chế expansion được framework hỗ trợ.
- Nhóm OR bằng ngoặc và giữ tenant/authorization predicate ở ngoài nhóm OR.
- Không để thiếu filter âm thầm bỏ WHERE; quyết định rõ khi nào query toàn bộ được phép.
- UPDATE/DELETE phải có guard và predicate phạm vi bắt buộc để tránh thay đổi hàng loạt ngoài ý muốn.
- Dùng DatabaseClient cho SQL động phức tạp; dùng repository hoặc Criteria khi abstraction đó diễn đạt đủ yêu cầu.
