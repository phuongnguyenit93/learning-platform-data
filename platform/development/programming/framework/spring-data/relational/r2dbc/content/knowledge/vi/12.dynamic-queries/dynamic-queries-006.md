# Chọn cột, sắp xếp và giới hạn kết quả

Truy vấn động trong Spring Data R2DBC thường cần thay đổi ba phần theo yêu cầu của người gọi: tập cột được đọc, thứ tự sắp xếp và số hàng trả về. Một API danh sách có thể chỉ cần mã và tên để hiển thị bảng, sắp xếp theo ngày tạo hoặc tên, rồi trả tối đa 20 kết quả mỗi lần. Nếu luôn đọc toàn bộ entity, luôn dùng một thứ tự cố định và tải mọi hàng về Java, ứng dụng sẽ lãng phí I/O, bộ nhớ và thời gian xử lý.

Spring Data R2DBC cung cấp `Query`, `Criteria` và `Sort` để xây dựng truy vấn theo metadata entity. Với SQL tùy chỉnh hoặc projection riêng, `DatabaseClient` cho phép chỉ định cột, `ORDER BY`, `LIMIT` và `OFFSET` trực tiếp. Dù dùng API nào, dữ liệu đầu vào từ client phải được xác thực: giá trị có thể bind như parameter, còn tên cột và hướng sắp xếp phải được chọn từ danh sách cho phép.

## 1. Vì sao cần chọn cột và giới hạn kết quả?

Giả sử bảng `person` có các cột `id`, `firstname`, `lastname`, `email`, `phone`, `address`, `created_at`, `updated_at`, `profile_json` và `notes`. Một màn hình danh sách chỉ hiển thị ID, họ tên và email. Nếu ứng dụng dùng `SELECT *`, database phải đọc và truyền thêm các cột không cần thiết, trong đó có thể có dữ liệu lớn như JSON hoặc ghi chú.

Ba quyết định giúp truy vấn gọn hơn:

- **Projection (chọn cột):** chỉ đọc những trường cần cho use case.
- **Sort (sắp xếp):** xác định thứ tự ổn định, phù hợp với cách người dùng xem dữ liệu.
- **Limit (giới hạn):** chỉ lấy một phần dữ liệu cần hiển thị hoặc xử lý trong một lượt.

Ví dụ SQL:

```sql
SELECT id, firstname, lastname, email
FROM person
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

Truy vấn này không tải `profile_json`, `address` hoặc `notes`; kết quả được sắp xếp theo thời điểm tạo mới nhất và giới hạn theo kích thước trang. `id` được thêm làm khóa phụ để các hàng có cùng `created_at` vẫn có thứ tự xác định.

Chọn ít cột không tự động làm mọi truy vấn nhanh hơn: database vẫn phải tìm hàng thỏa điều kiện và có thể phải đọc trang dữ liệu cần thiết. Tuy nhiên, projection thường giảm lượng dữ liệu truyền qua mạng, giảm chi phí ánh xạ và tránh tải các trường lớn không cần dùng.

## 2. Chọn cột bằng SQL projection

Với `DatabaseClient`, phần `SELECT` xác định trực tiếp các cột cần đọc. Ví dụ tạo DTO dành riêng cho màn hình danh sách:

```java
public record PersonSummary(
    Long id,
    String firstname,
    String lastname,
    String email
) {}
```

Repository tùy chỉnh có thể ánh xạ kết quả vào DTO:

```java
@Repository
public class PersonQueryRepository {

    private final DatabaseClient databaseClient;

    public PersonQueryRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PersonSummary> findSummaries(String status, int pageSize) {
        return databaseClient.sql("""
                SELECT id, firstname, lastname, email
                FROM person
                WHERE status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :pageSize
                """)
            .bind("status", status)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> new PersonSummary(
                row.get("id", Long.class),
                row.get("firstname", String.class),
                row.get("lastname", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
```

DTO làm rõ dữ liệu mà use case cần và tránh biến một entity đầy đủ thành đối tượng dùng cho mọi màn hình. Nếu `PersonSummary` chỉ phục vụ đọc, không nên dùng nó để ghi ngược trở lại bảng như thể nó là entity hoàn chỉnh.

### Chọn cột theo nhu cầu API

Nếu API có một vài kiểu projection cố định, thường nên tạo các phương thức hoặc DTO riêng. Ví dụ:

- `PersonListItem`: ID, họ tên và email cho danh sách.
- `PersonContact`: ID, email và số điện thoại cho chức năng liên hệ.
- `PersonDetail`: các trường cần cho màn hình chi tiết.

Cách này giúp câu SQL và kiểu kết quả có cấu trúc rõ ràng, dễ kiểm tra khi schema thay đổi. Không cần tạo một API chọn tùy ý mọi cột nếu sản phẩm chỉ có vài màn hình xác định.

### Trường hợp thật sự cần chọn cột động

Một số API cho phép client gửi danh sách trường muốn nhận. Tên cột SQL không thể được truyền bằng bind parameter như giá trị thông thường. Do đó, phải ánh xạ tên trường công khai sang tên cột cố định trong code:

```java
private static final Map<String, String> SELECTABLE_COLUMNS = Map.of(
    "id", "p.id AS id",
    "firstName", "p.firstname AS first_name",
    "lastName", "p.lastname AS last_name",
    "email", "p.email AS email"
);

private List<String> resolveColumns(List<String> requestedFields) {
    if (requestedFields == null || requestedFields.isEmpty()) {
        return List.of(
            SELECTABLE_COLUMNS.get("id"),
            SELECTABLE_COLUMNS.get("firstName"),
            SELECTABLE_COLUMNS.get("lastName")
        );
    }

    return requestedFields.stream()
        .map(field -> {
            String column = SELECTABLE_COLUMNS.get(field);
            if (column == null) {
                throw new IllegalArgumentException("Unsupported field: " + field);
            }
            return column;
        })
        .distinct()
        .toList();
}
```

Sau khi resolve, chỉ ghép các biểu thức đã được định nghĩa sẵn vào phần `SELECT`. Mọi giá trị lọc vẫn phải bind parameter. Với projection động có hình dạng thay đổi, kiểu trả về có thể là map hoặc một cấu trúc dữ liệu linh hoạt; cần giữ alias cột ổn định để ánh xạ dễ dàng.

Không chấp nhận trực tiếp chuỗi `fields` từ request để ghép vào SQL. Một tên như `id, (SELECT ...)` hoặc biểu thức SQL độc hại có thể thay đổi ý nghĩa truy vấn. Allow-list phải kiểm tra cả tên cột và biểu thức được phép sử dụng.

## 3. Chọn cột bằng R2dbcEntityTemplate

Khi truy vấn vẫn thao tác với entity và muốn tận dụng mapping metadata, có thể dùng `Query` cùng `Columns` để chỉ định các cột cần lấy:

```java
public Flux<Person> findBasicPeople(String status) {
    Query query = Query.query(Criteria.where("status").is(status))
        .columns(Columns.include("id", "firstname", "lastname"));

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

`Columns.include(...)` chỉ định những thuộc tính/cột được đưa vào kết quả. Spring Data dùng mapping metadata để chuyển tên thuộc tính entity thành tên cột theo cấu hình mapping.

Khi chỉ đọc một phần cột vào entity, các thuộc tính không được chọn có thể không có giá trị trong đối tượng được ánh xạ. Vì vậy, hãy coi kết quả này là dữ liệu đọc một phần. Không lấy entity thiếu trường rồi gọi `save()` như thể đó là bản ghi đầy đủ, vì các trường không được tải có thể không có giá trị cần thiết cho thao tác ghi. Với projection chỉ đọc, DTO chuyên biệt qua `DatabaseClient` thường thể hiện ý định rõ hơn.

API `Columns` và các overload của `Query` cần được đối chiếu với phiên bản Spring Data Relational đang dùng. Nếu phiên bản hoặc kiểu query không hỗ trợ projection mong muốn, có thể dùng `DatabaseClient` để chỉ định SQL tường minh.

## 4. Sắp xếp bằng Sort

Sắp xếp quyết định thứ tự hàng được trả về. Trong Spring Data Relational, `Sort` mô tả thuộc tính và hướng sắp xếp; `Query` kết hợp `Sort` với điều kiện `Criteria`.

Ví dụ sắp xếp người dùng theo họ tăng dần:

```java
public Flux<Person> findByStatus(String status) {
    Query query = Query.query(Criteria.where("status").is(status))
        .sort(Sort.by(Sort.Order.asc("lastname")));

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

Có thể kết hợp nhiều trường sắp xếp:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("lastname"),
    Sort.Order.asc("id")
);
```

Thứ tự được áp dụng lần lượt: trước hết theo `createdAt` giảm dần; nếu hai hàng cùng thời điểm, so sánh `lastname`; nếu vẫn bằng nhau, so sánh `id`. Thêm một khóa phụ duy nhất như ID giúp thứ tự ổn định khi phân trang.

Tên thuộc tính trong `Sort` thường là tên thuộc tính Java của entity. Spring Data chuyển đổi sang tên cột vật lý theo mapping context. Khi dùng `DatabaseClient`, SQL sử dụng tên cột thực tế của database.

## 5. Chọn trường và hướng sắp xếp từ request một cách an toàn

API danh sách có thể nhận `sortBy` và `direction` từ query parameter. Không được đưa trực tiếp các chuỗi đó vào `ORDER BY`:

```java
// Không an toàn: sortBy và direction đến từ request.
String sql = "SELECT id, firstname FROM person ORDER BY "
    + sortBy + " " + direction;
```

Bind parameter chỉ dùng cho giá trị. Tên cột và từ khóa `ASC`/`DESC` là một phần cấu trúc SQL nên phải được kiểm soát riêng.

### Allow-list cho thuộc tính Sort

Với `R2dbcEntityTemplate`, ánh xạ tên trường API sang tên thuộc tính entity:

```java
private String resolveSortProperty(String sortBy) {
    return switch (sortBy == null ? "" : sortBy) {
        case "firstName" -> "firstname";
        case "lastName" -> "lastname";
        case "createdAt" -> "createdAt";
        case "email" -> "email";
        default -> "id";
    };
}

private Sort.Direction resolveDirection(String direction) {
    return "asc".equalsIgnoreCase(direction)
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;
}
```

Sau đó tạo `Sort` từ những giá trị đã được kiểm soát:

```java
String property = resolveSortProperty(sortBy);
Sort.Direction direction = resolveDirection(directionParam);

Sort sort = Sort.by(
    new Sort.Order(direction, property),
    Sort.Order.asc("id")
);
```

Ở đây, mọi giá trị không được nhận diện sẽ rơi về thứ tự mặc định. Một API khác có thể trả HTTP 400 khi `sortBy` không hợp lệ; điều quan trọng là không chuyển chuỗi chưa xác thực thành tên cột.

### Allow-list cho SQL với DatabaseClient

Khi viết SQL thủ công, ánh xạ sang tên cột vật lý:

```java
String orderColumn = switch (sortBy == null ? "" : sortBy) {
    case "firstName" -> "firstname";
    case "lastName" -> "lastname";
    case "createdAt" -> "created_at";
    case "email" -> "email";
    default -> "id";
};

String orderDirection = "asc".equalsIgnoreCase(directionParam)
    ? "ASC"
    : "DESC";
```

Hai biến chỉ nhận giá trị từ các nhánh cố định trong code, vì vậy có thể đưa vào phần `ORDER BY`. Các giá trị như trạng thái, ID hoặc từ khóa tìm kiếm vẫn phải bind bằng `.bind(...)`.

Không dùng `Sort.Direction.valueOf(directionParam)` trực tiếp với dữ liệu client nếu không bắt và xử lý trường hợp không hợp lệ. Cũng không dùng tên thuộc tính Java trong SQL thuần nếu tên cột vật lý khác nhau.

## 6. Giới hạn kết quả bằng Query.limit

Khi dùng `R2dbcEntityTemplate`, có thể đặt giới hạn số hàng ngay trong `Query`:

```java
public Flux<Person> findFirstPeople(String status, int pageSize) {
    int safePageSize = Math.max(1, Math.min(pageSize, 100));

    Query query = Query.query(Criteria.where("status").is(status))
        .sort(Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id")))
        .limit(safePageSize);

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

`limit(...)` yêu cầu database chỉ trả tối đa số hàng đã chỉ định. Giới hạn tối đa ở phía server giúp tránh một request gửi `pageSize` quá lớn làm tăng bộ nhớ, thời gian truy vấn và số connection bị chiếm dụng.

`Flux` vẫn phát các hàng theo kiểu reactive; điều đó không có nghĩa database tự giới hạn số hàng nếu SQL hoặc Query không có limit. Không nên tải hàng trăm nghìn hàng rồi dùng `take(20)` ở phía Reactor nếu mục tiêu là giảm lượng dữ liệu database phải trả về. Hãy đặt giới hạn trong truy vấn database.

## 7. Kết hợp điều kiện, cột, sort và limit

Một query động có thể kết hợp filter theo trạng thái, projection, sắp xếp và giới hạn:

```java
public Flux<Person> searchPeople(
        String status,
        String sortBy,
        String direction,
        int pageSize) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));
    String property = resolveSortProperty(sortBy);
    Sort.Direction sortDirection = resolveDirection(direction);

    Criteria criteria = Criteria.where("status").is(status);

    Query query = Query.query(criteria)
        .columns(Columns.include("id", "firstname", "lastname", "email"))
        .sort(Sort.by(
            new Sort.Order(sortDirection, property),
            Sort.Order.asc("id")
        ))
        .limit(safePageSize);

    return template.select(Person.class)
        .matching(query)
        .all();
}
```

Đoạn code minh họa việc kết hợp các API query; các import tương ứng thường gồm `Criteria`, `Query`, `Columns`, `Sort` từ Spring Data Relational. Hãy kiểm tra overload cụ thể trong release train của ứng dụng.

Nếu truy vấn chỉ cần một DTO, có thể dùng `DatabaseClient` để định nghĩa projection và mapping rõ ràng. Nếu cần entity đầy đủ cho nghiệp vụ cập nhật, hãy cân nhắc có nên chọn một phần cột hay không; entity không đầy đủ thường phù hợp cho đọc hơn ghi.

## 8. Giới hạn kết quả bằng LIMIT trong DatabaseClient

Với SQL tùy chỉnh, `LIMIT` giới hạn số hàng. Ví dụ PostgreSQL:

```java
public Flux<PersonSummary> findPage(
        String status,
        int pageSize,
        long offset) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));
    long safeOffset = Math.max(0, offset);

    return databaseClient.sql("""
            SELECT id, firstname, lastname, email
            FROM person
            WHERE status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize OFFSET :offset
            """)
        .bind("status", status)
        .bind("pageSize", safePageSize)
        .bind("offset", safeOffset)
        .map((row, metadata) -> new PersonSummary(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

Trong ví dụ này, `pageSize` và `offset` được kiểm tra giới hạn ở Java rồi bind như giá trị. PostgreSQL hỗ trợ tham số trong `LIMIT` và `OFFSET`; cú pháp phân trang có thể khác ở SQL Server hoặc một số hệ quản trị khác. Hãy điều chỉnh theo dialect và khả năng của driver đang dùng.

Giới hạn số hàng trả về không đồng nghĩa giới hạn tổng số hàng mà database phải xem xét. Nếu filter và sort không có index phù hợp, database vẫn có thể phải quét hoặc sắp xếp một lượng dữ liệu lớn trước khi trả về `LIMIT` hàng. Vì vậy cần xem execution plan và thiết kế index theo truy vấn.

## 9. Offset pagination

Offset pagination chia kết quả thành các trang có kích thước cố định. Với trang đầu tiên, offset thường bằng 0; trang thứ hai có offset bằng page size; công thức tổng quát:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Ví dụ:

| Trang | Page size | Offset |
|---:|---:|---:|
| 1 | 20 | 0 |
| 2 | 20 | 20 |
| 3 | 20 | 40 |
| 4 | 20 | 60 |

Ưu điểm của offset pagination:

- Dễ hiểu và dễ triển khai.
- Phù hợp với giao diện có số trang và chức năng nhảy tới trang bất kỳ.
- Có thể kết hợp với tổng số bản ghi để hiển thị số trang.

Hạn chế:

- Offset lớn có thể làm database phải duyệt và bỏ qua nhiều hàng.
- Nếu dữ liệu được thêm hoặc xóa giữa hai lần gọi, hàng có thể dịch chuyển giữa các trang, gây lặp hoặc bỏ sót.
- Việc đếm tổng số hàng để hiển thị tổng trang có thể tốn kém với tập dữ liệu lớn.

Khi dùng offset, luôn chỉ định `ORDER BY` ổn định. Sắp xếp chỉ theo `created_at` có thể không xác định thứ tự giữa các hàng cùng thời điểm. Thêm ID hoặc một khóa duy nhất làm tie-breaker.

## 10. Keyset pagination (cursor pagination)

Với tập dữ liệu lớn hoặc luồng cuộn liên tục, keyset pagination thường hiệu quả hơn offset pagination. Thay vì yêu cầu bỏ qua N hàng, client gửi giá trị của hàng cuối cùng ở trang trước làm cursor.

Giả sử sắp xếp theo `created_at DESC, id DESC`, truy vấn trang tiếp theo có thể là:

```sql
SELECT id, firstname, lastname, created_at
FROM person
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

Cursor gồm cả `created_at` và `id` vì hai trường cùng tạo thứ tự. Nếu chỉ dùng `created_at`, các hàng có timestamp giống nhau có thể bị lặp hoặc bỏ sót giữa các trang.

Index phù hợp có thể là:

```sql
CREATE INDEX idx_person_status_created_id
    ON person (status, created_at DESC, id DESC);
```

Index này là điểm bắt đầu để thử nghiệm; cần xác minh bằng execution plan và dữ liệu thực tế. Keyset pagination đặc biệt hữu ích khi người dùng đi tiếp từ trang hiện tại, nhưng không thuận tiện cho việc nhảy trực tiếp tới trang số 100.

### Ví dụ triển khai cursor bằng DatabaseClient

DTO của truy vấn cursor chứa cả giá trị cần trả về lẫn trường thời gian dùng để tạo cursor cho trang kế tiếp:

```java
public record PersonCursorItem(
    Long id,
    String firstname,
    String lastname,
    Instant createdAt
) {}
```

```java
public Flux<PersonCursorItem> findNextPage(
        String status,
        Instant cursorCreatedAt,
        Long cursorId,
        int pageSize) {

    int safePageSize = Math.max(1, Math.min(pageSize, 100));

    return databaseClient.sql("""
            SELECT id, firstname, lastname, created_at
            FROM person
            WHERE status = :status
              AND (
                  created_at < :cursorCreatedAt
                  OR (created_at = :cursorCreatedAt AND id < :cursorId)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("cursorCreatedAt", cursorCreatedAt)
        .bind("cursorId", cursorId)
        .bind("pageSize", safePageSize)
        .map((row, metadata) -> new PersonCursorItem(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("created_at", Instant.class)
        ))
        .all();
}
```

Ví dụ minh họa khi cursor đã có. Với trang đầu tiên, cần dùng một nhánh truy vấn không có điều kiện cursor hoặc xây dựng query tương ứng; không bind `null` vào phép so sánh rồi kỳ vọng nó có nghĩa là không lọc. DTO thực tế nên khớp chính xác các cột được chọn.

Nếu cột sắp xếp cho phép `NULL`, phải xác định quy tắc `NULLS FIRST`/`NULLS LAST` và đưa quy tắc đó vào cursor. Dễ nhất là chọn các cột cursor `NOT NULL` hoặc chuẩn hóa giá trị null theo một biểu thức có thứ tự rõ ràng.

## 11. Tính nhất quán của thứ tự và phân trang

Sắp xếp ổn định rất quan trọng khi kết hợp với limit và offset. Một câu truy vấn không có `ORDER BY` không bảo đảm thứ tự hàng. Database có thể trả hàng theo thứ tự khác nhau tùy execution plan, index hoặc thay đổi dữ liệu.

Ngay cả khi có `ORDER BY` trên một cột không duy nhất, các hàng có cùng giá trị vẫn có thể xuất hiện theo thứ tự khác nhau giữa các lần truy vấn. Hãy thêm một cột duy nhất vào cuối danh sách sort.

Với dữ liệu thường xuyên thay đổi, offset pagination vẫn có thể thay đổi nội dung trang giữa các lần gọi. Nếu yêu cầu người dùng duyệt một snapshot nhất quán, cần cân nhắc transaction isolation, snapshot token hoặc cơ chế lưu thời điểm truy vấn. Không nên giữ một transaction database mở trong suốt thời gian người dùng đọc nhiều trang; điều đó có thể giữ connection và snapshot quá lâu. Cursor dựa trên các cột bất biến hoặc ít thay đổi thường phù hợp hơn.

## 12. Xử lý sort null và kiểu dữ liệu

Các hệ quản trị có thể khác nhau về thứ tự mặc định của giá trị `NULL`. Nếu một trường sort cho phép null, kết quả có thể không nhất quán giữa database hoặc giữa các hướng sắp xếp.

Một số hệ quản trị hỗ trợ cú pháp `NULLS FIRST` hoặc `NULLS LAST`. Nếu dùng `Sort`, hãy kiểm tra API null handling của phiên bản Spring Data và khả năng dịch của dialect. Nếu cần kiểm soát chính xác, dùng SQL cụ thể cho database.

Không nên sắp xếp theo một biểu thức tốn kém như `LOWER(name)` hoặc `CAST(...)` trên tập dữ liệu lớn mà không xem execution plan. Nếu use case thường xuyên sắp xếp không phân biệt hoa thường, có thể cần functional index hoặc cột chuẩn hóa tùy database.

Kiểu dữ liệu cũng ảnh hưởng thứ tự: chuỗi được so sánh theo collation, số theo giá trị số, thời gian theo thời điểm. Nếu lưu ngày giờ dưới dạng chuỗi, thứ tự có thể không tương ứng thứ tự thời gian. Hãy dùng kiểu cột phù hợp và quy ước timezone rõ ràng.

## 13. Giới hạn page size và bảo vệ tài nguyên

Không nên để client yêu cầu một page size tùy ý. Một request có thể gửi `pageSize=1000000` và buộc ứng dụng tạo một luồng dữ liệu rất lớn. Hãy đặt giới hạn mặc định và tối đa ở server:

```java
private int normalizePageSize(Integer requested) {
    if (requested == null) {
        return 20;
    }
    return Math.max(1, Math.min(requested, 100));
}
```

Giá trị tối đa nên dựa trên kích thước projection, độ trễ truy vấn, tải database và khả năng xử lý của consumer. Nếu client cần xuất dữ liệu lớn, hãy xây dựng endpoint export hoặc job streaming riêng với quota, thời hạn và kiểm soát concurrency; không mở rộng page size của API thông thường vô hạn.

Với `Flux`, backpressure giúp consumer điều tiết tốc độ nhận phần tử, nhưng không thay thế `LIMIT`. Query không giới hạn vẫn có thể tạo một công việc database lớn và giữ connection lâu trong khi publisher được tiêu thụ.

## 14. Tối ưu index cho filter, sort và limit

Truy vấn thường kết hợp `WHERE`, `ORDER BY` và `LIMIT`. Index cần hỗ trợ cả điều kiện lọc lẫn thứ tự nếu muốn tránh quét hoặc sắp xếp nhiều hàng.

Ví dụ:

```sql
SELECT id, firstname, lastname, created_at
FROM person
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Một index ứng viên:

```sql
CREATE INDEX idx_person_status_created_id
    ON person (status, created_at DESC, id DESC);
```

`status` đứng đầu vì được lọc bằng điều kiện bằng; các cột sau phục vụ thứ tự sắp xếp. Tuy nhiên, hiệu quả phụ thuộc độ chọn lọc của `status`, số lượng hàng, database engine và các truy vấn khác. Một index riêng có thể cần thiết nếu nhiều truy vấn chỉ lọc theo `created_at` hoặc sort theo trường khác.

Nếu projection nhỏ, một số database hỗ trợ covering index hoặc `INCLUDE` để phục vụ truy vấn mà không cần đọc heap/table cho mọi cột. Đây là tối ưu database-specific và làm index lớn hơn; chỉ dùng sau khi đo lường.

Kiểm tra truy vấn với `EXPLAIN` hoặc công cụ tương đương. Với PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` cho biết kế hoạch thực thi, thời gian và số buffer được đọc; câu lệnh có `ANALYZE` sẽ thực sự chạy truy vấn.

## 15. Tổng số trang và truy vấn COUNT

Giao diện có thể muốn biết tổng số hàng phù hợp để hiển thị “1–20 trong 540”. Khi đó có thể chạy thêm câu `COUNT(*)` với cùng điều kiện:

```sql
SELECT COUNT(*)
FROM person
WHERE status = :status;
```

Tổng số trang có thể tính bằng:

\[
\text{totalPages} = \left\lceil
\frac{\text{totalElements}}{\text{pageSize}}
\right\rceil
\]

Truy vấn count có thể tốn kém với bảng lớn, filter phức tạp hoặc join nhiều bảng. Nó cũng có thể quan sát dữ liệu ở thời điểm khác với truy vấn lấy trang nếu hai câu lệnh không chạy trong cùng snapshot transaction. Nếu giao diện chỉ cần nút “Tải thêm”, có thể lấy `pageSize + 1` hàng để biết còn dữ liệu hay không mà không cần đếm toàn bộ.

Với reactive application, hãy kết hợp hai publisher có chủ đích nếu cần trả cả dữ liệu và tổng số. Không nên thực hiện `block()` để chờ count trong luồng WebFlux. Nếu count không cần thiết cho use case, bỏ truy vấn đó sẽ tiết kiệm tài nguyên.

## 16. Một thiết kế API tìm kiếm hoàn chỉnh

Một request danh sách có thể nhận filter, sort, page size và cursor. DTO request nên giới hạn các trường hợp được hỗ trợ:

```java
public record PersonSearchRequest(
    String status,
    String sortBy,
    String direction,
    Integer pageSize,
    Long offset
) {}
```

Service chuẩn hóa input trước khi gọi lớp truy cập dữ liệu:

```java
public Flux<PersonSummary> search(PersonSearchRequest request) {
    int size = normalizePageSize(request.pageSize());
    long offset = request.offset() == null
        ? 0
        : Math.max(0, request.offset());

    String sortColumn = switch (request.sortBy() == null ? "" : request.sortBy()) {
        case "firstName" -> "firstname";
        case "lastName" -> "lastname";
        case "createdAt" -> "created_at";
        default -> "id";
    };

    String direction = "asc".equalsIgnoreCase(request.direction())
        ? "ASC"
        : "DESC";

    String sql = """
        SELECT id, firstname, lastname, email
        FROM person
        WHERE status = :status
        ORDER BY %s %s, id ASC
        LIMIT :pageSize OFFSET :offset
        """.formatted(sortColumn, direction);

    return databaseClient.sql(sql)
        .bind("status", request.status())
        .bind("pageSize", size)
        .bind("offset", offset)
        .map((row, metadata) -> new PersonSummary(
            row.get("id", Long.class),
            row.get("firstname", String.class),
            row.get("lastname", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

Trong ví dụ, `sortColumn` và `direction` chỉ nhận các literal đã được allow-list; filter và pagination values được bind. Nếu `status` là tùy chọn, cần xây dựng điều kiện tương ứng và xác định hành vi khi không có filter. Không nên bỏ điều kiện tenant hoặc authorization scope chỉ vì request không gửi giá trị.

Nếu ứng dụng có nhiều hệ quản trị, cần tách cú pháp pagination và các biểu thức sort theo dialect. Với truy vấn entity đơn giản, `R2dbcEntityTemplate` thường giảm lượng SQL phải ghép thủ công.

## 17. Kiểm thử truy vấn động

Nên kiểm tra các trường hợp:

- Projection chỉ trả các cột cần thiết và mapping đúng alias.
- Cột không được phép chọn bị từ chối.
- `sortBy` lạ không thể chèn SQL và được xử lý theo chính sách API.
- Hướng sort chỉ nhận `ASC` hoặc `DESC` theo allow-list.
- Kích thước trang mặc định và tối đa được áp dụng.
- Page size bằng 0, âm hoặc rất lớn được xử lý đúng.
- Thứ tự có tie-breaker duy nhất, không lặp tùy tiện khi nhiều hàng có cùng giá trị sort.
- Offset lớn có hành vi hiệu năng chấp nhận được hoặc API chuyển sang cursor.
- Cursor trả đúng trang tiếp theo, kể cả khi nhiều hàng có cùng timestamp.
- Các filter và giá trị người dùng luôn được bind parameter.
- Index và execution plan được kiểm tra với dữ liệu gần thực tế.

Kiểm thử nên chạy trên cùng hệ quản trị và driver dự kiến triển khai, đặc biệt khi dùng cú pháp `LIMIT`, `OFFSET`, null ordering hoặc kiểu thời gian đặc thù.

## 18. Quy trình chọn cột, sắp xếp và giới hạn

Khi triển khai một API truy vấn động, có thể làm theo trình tự:

**Bước 1 — Xác định dữ liệu cần trả về.** Liệt kê các trường thực sự được màn hình hoặc nghiệp vụ sử dụng và tạo DTO/projection tương ứng.

**Bước 2 — Xác định các trường được phép sort.** Tạo allow-list ánh xạ tên API sang thuộc tính entity hoặc tên cột SQL.

**Bước 3 — Chuẩn hóa hướng sort.** Chỉ chấp nhận `ASC` hoặc `DESC`; định nghĩa hướng mặc định và xử lý giá trị không hợp lệ.

**Bước 4 — Giới hạn page size.** Đặt giá trị mặc định và mức tối đa phía server; kiểm tra offset hoặc cursor.

**Bước 5 — Chọn chiến lược phân trang.** Dùng offset cho tập dữ liệu vừa phải và nhu cầu nhảy trang; cân nhắc keyset khi dữ liệu lớn hoặc người dùng cuộn liên tục.

**Bước 6 — Thêm thứ tự ổn định.** Bổ sung khóa duy nhất làm tie-breaker và xác định quy tắc null.

**Bước 7 — Thiết kế index.** Cân nhắc các cột filter, sort và thứ tự index; xác minh bằng execution plan.

**Bước 8 — Kiểm thử an toàn và hiệu năng.** Kiểm tra input độc hại, projection, phân trang, tải đồng thời và hành vi trên database thật.

Chọn cột giúp giảm dữ liệu không cần thiết; `Sort` hoặc `ORDER BY` xác định thứ tự; `limit` hoặc `LIMIT` giữ số hàng trong giới hạn. Khi kết hợp ba yếu tố này với allow-list, bind parameter, thứ tự ổn định và index phù hợp, truy vấn động trong Spring Data R2DBC sẽ dễ kiểm soát, an toàn và có hiệu năng dự đoán tốt hơn.
