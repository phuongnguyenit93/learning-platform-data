# @Column, tên có phân biệt hoa thường và CqlIdentifier

Trong **Spring Data Cassandra**, một thuộc tính Java không nhất thiết có cùng tên với cột trong Apache Cassandra. Annotation `@Column` giúp xác định cột CQL tương ứng; còn `CqlIdentifier` của Java driver biểu diễn tên keyspace, bảng và cột sao cho không nhầm giữa tên **có phân biệt hoa/thường** và tên **không phân biệt hoa/thường**.

Bài học thuộc chương **Ánh xạ entity** của module **SPRING_DATA_CASSANDRA**. Ngoài việc ánh xạ entity cho `CassandraRepository` và `CassandraTemplate`, ta sẽ thấy quy tắc đặt tên ảnh hưởng đến truy vấn CQL thủ công, khóa partition, đọc dữ liệu và cách kiểm tra schema. Các ví dụ dùng Spring Data Cassandra hiện đại và Apache Cassandra Java driver 4.x.

## 1. Quy tắc tên định danh của Cassandra

Tên *identifier* là tên của keyspace, bảng, cột và các đối tượng schema. Trong CQL, **dấu nháy kép (`"..."`)** quyết định cách Cassandra xử lý chữ hoa/thường:

- **Không đặt trong nháy kép:** Cassandra coi identifier là không phân biệt hoa/thường và chuẩn hóa tên về chữ thường. `DisplayName`, `displayname` và `DISPLAYNAME` trong CQL đều chỉ tên nội bộ `displayname`.
- **Có nháy kép:** Cassandra giữ nguyên ký tự và phân biệt hoa/thường. `"DisplayName"`, `"displayname"` và `"DISPLAYNAME"` là những identifier khác nhau.
- Tên chứa khoảng trắng/ký tự đặc biệt, hoặc trùng từ khóa cần tránh, thường phải sử dụng nháy kép hợp lệ. Dấu nháy kép nằm *trong tên* được escape bằng cách viết hai dấu nháy kép liên tiếp trong CQL.
- Dấu nháy đơn (`'...'`) dùng cho **giá trị chuỗi CQL**, không dùng để báo rằng một tên cột là identifier có phân biệt hoa/thường.

| CQL viết ra | Tên nội bộ | Có phân biệt hoa/thường? |
| --- | --- | --- |
| `display_name` | `display_name` | Không |
| `DisplayName` | `displayname` | Không |
| `"DisplayName"` | `DisplayName` | Có |
| `"displayname"` | `displayname` | Có, nhưng trùng chính xác tên chữ thường |
| `"Display Name"` | `Display Name` | Có; chứa dấu cách |

**Ví dụ:** Giả sử keyspace `commerce` đã có sẵn.

```sql
-- Tạo bảng có quy ước tên chữ thường, dễ sử dụng nhất.
CREATE TABLE commerce.customer_profile (
    customer_id uuid PRIMARY KEY,
    display_name text,
    created_at timestamp
);

-- Không có dấu nháy kép: DISPLAY_NAME và display_name cùng là một identifier.
SELECT DISPLAY_NAME FROM commerce.customer_profile
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Trái lại, schema sau cố ý dùng identifier giữ nguyên chữ hoa:

```sql
-- Ví dụ tương thích hệ thống cũ; không khuyến khích đặt tên kiểu này cho schema mới.
CREATE TABLE commerce."LegacyCustomer" (
    "CustomerId" uuid PRIMARY KEY,
    "DisplayName" text,
    "createdAt" timestamp
);

-- ĐÚNG: tên bảng và tên cột được trích dẫn đúng.
SELECT "CustomerId", "DisplayName", "createdAt"
FROM commerce."LegacyCustomer"
WHERE "CustomerId" = 11111111-1111-1111-1111-111111111111;

-- SAI: DisplayName không quote sẽ được hiểu thành displayname.
SELECT DisplayName
FROM commerce."LegacyCustomer"
WHERE "CustomerId" = 11111111-1111-1111-1111-111111111111;
```

Lệnh `SELECT` cuối có thể thất bại vì cột `displayname` không tồn tại, dù trong bảng có `"DisplayName"`. Đây là lỗi **định danh schema**, không phải lỗi chuyển đổi kiểu `String`, consistency level hay kết nối cluster.

## 2. `@Column` giải quyết bài toán gì?

Spring Data Cassandra dùng metadata của entity để ánh xạ trường Java với cột CQL. `@Column("ten_cot")` xác định rõ tên cột vật lý; phần `value` nhận **CQL identifier hợp lệ**, bao gồm dạng đã quote khi schema yêu cầu giữ nguyên chữ hoa/thường.

Ví dụ bảng `commerce.customer_profile` ở trên và Java entity:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customer_profile")
public class CustomerProfile {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("display_name")
    private String displayName;

    @Column("created_at")
    private Instant createdAt;

    public CustomerProfile() {}

    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID id) { this.customerId = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { this.displayName = value; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { this.createdAt = value; }
}
```

Ở ví dụ:

- `customerId` là **tên thuộc tính Java**, `customer_id` là cột partition key trong CQL; `@PrimaryKey` biểu diễn khóa chính của entity.
- `displayName` là thuộc tính Java kiểu camelCase; `@Column("display_name")` buộc mapper dùng cột `display_name` (snake_case).
- `createdAt` được ánh xạ sang `created_at`; `Instant` tương ứng kiểu CQL `timestamp` qua bộ chuyển đổi phù hợp.
- `@Table("customer_profile")` chỉ định tên bảng. Keyspace mặc định có thể được cung cấp bằng cấu hình session/Spring Boot.

`@Column` **không tự tạo alias hoặc đổi tên cột đã tồn tại**. Nó chỉ hướng dẫn Spring Data đọc/ghi vào tên CQL nào. Nếu annotation trỏ sai tên, việc ánh xạ hoặc thực thi query sẽ lỗi; thêm annotation cũng không tự tạo column trong cluster đang chạy.

### So sánh cách viết trên trường `displayName`

| Annotation | Identifier CQL được nêu ra | Khớp bảng nào? |
| --- | --- | --- |
| `@Column("display_name")` | `display_name` | Cột `display_name` trong schema snake_case. |
| `@Column("DisplayName")` | `displayname` vì không quote | Chỉ khớp cột không quote `displayname`, **không** khớp `"DisplayName"`. |
| `@Column("\"DisplayName\"")` | `"DisplayName"` | Khớp chính xác cột mixed-case `"DisplayName"`. |
| Bỏ `@Column` | Tên do **naming strategy** hiện hành suy ra | Phải kiểm tra quy tắc đặt tên đã cấu hình, tránh đoán. |

Trong Java source, `\"` là cách escape ký tự nháy kép bên trong chuỗi. Do đó `@Column("\"DisplayName\"")` truyền cho mapper một chuỗi chứa **dấu nháy kép thực sự** bao quanh tên cột; nó khác với chuỗi `"DisplayName"` không có nháy kép CQL.

Đối với các khóa ghép, annotation tương ứng thường là `@PrimaryKeyColumn` với `PrimaryKeyType.PARTITIONED` hoặc `CLUSTERED`; khi tên khóa có mixed-case thì nguyên tắc quoting vẫn phải khớp schema. Không thay `@PrimaryKeyColumn` bằng `@Column` rồi kỳ vọng Spring tự nhận biết partition key.

## 3. Ánh xạ bảng có tên cột mixed-case bằng Spring Data Cassandra

Khi phải tích hợp hệ Cassandra cũ, đôi khi schema chứa các tên như `"LegacyCustomer"` và `"DisplayName"`. Để Spring Data sinh CQL với **chính xác những tên đó**, hãy ghi quoted identifier trong annotation.

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

// Phải trùng với bảng CQL: commerce."LegacyCustomer"
@Table("\"LegacyCustomer\"")
public class LegacyCustomer {

    // Phải trùng với cột CQL: "CustomerId"
    @PrimaryKey("\"CustomerId\"")
    private UUID customerId;

    @Column("\"DisplayName\"")
    private String displayName;

    @Column("\"createdAt\"")
    private Instant createdAt;

    public LegacyCustomer() {}

    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID id) { customerId = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }
}
```

**Lưu ý trong dự án thực:** entity có thể đặt ở một package Java riêng, còn keyspace `commerce` được khai báo bằng `spring.cassandra.keyspace-name=commerce`. Tên bảng trong `@Table` là identifier của bảng; nếu chọn keyspace cụ thể ở annotation hoặc cấu hình khác, phải bảo đảm không tạo ra đường dẫn tham chiếu sai.

Repository:

```java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface LegacyCustomerRepository
        extends CassandraRepository<LegacyCustomer, UUID> {
}
```

Khi gọi `repository.findById(customerId)`, Spring Data dùng metadata từ `@Table` và `@PrimaryKey`. Nếu các tên đã khai báo đúng, caller không phải tự viết các dấu nháy kép trong phương thức repository cơ bản.

Với `CassandraTemplate`, cùng metadata entity được sử dụng:

```java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraTemplate;

public class LegacyCustomerReader {
    private final CassandraTemplate template;

    public LegacyCustomerReader(CassandraTemplate template) {
        this.template = template;
    }

    public LegacyCustomer load(UUID customerId) {
        return template.selectOneById(customerId, LegacyCustomer.class);
    }
}
```

Ở đây, `selectOneById` minh họa truy vấn theo **khóa chính đầy đủ**. Lớp service không cần tự biết cú pháp quoting vì mapper đã có metadata đúng. Khi schema có compound key, ID phải là key object thích hợp; không thể lấy một cột thông thường thay cho khóa partition.

### `@Query` thủ công vẫn phải quote đúng

`@Query` nhận **chuỗi CQL do bạn viết**, không tự sửa mọi tên identifier dựa trên annotation của entity:

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface LegacyCustomerRepository
        extends CassandraRepository<LegacyCustomer, UUID> {

    @Query("SELECT \"CustomerId\", \"DisplayName\", \"createdAt\" " +
           "FROM \"LegacyCustomer\" WHERE \"CustomerId\" = ?0")
    Optional<LegacyCustomer> findLegacyById(UUID customerId);
}
```

Trong Java, `\"` bên trong chuỗi biểu diễn nháy kép cần xuất hiện trong CQL. Khi dùng repository trên, hãy đặt file chứa interface đúng theo quy tắc Java (không khai báo hai phiên bản cùng tên `LegacyCustomerRepository` trong một package); hai ví dụ chỉ trình bày các cách sử dụng thay thế.

**Sai phổ biến:** đổi `@Column` cho đúng nhưng giữ nguyên query `SELECT DisplayName FROM ...`; lúc này câu CQL vẫn tham chiếu cột `displayname` thay vì `"DisplayName"`. Để sửa, phải chỉnh cả literal query.

## 4. `CqlIdentifier`: phân biệt *CQL form* và *internal form*

Java driver 4.x sử dụng `com.datastax.oss.driver.api.core.CqlIdentifier` để biểu diễn tên đối tượng CQL một cách tường minh. Đối tượng này tách hai khái niệm:

- **CQL form:** cách bạn viết tên trong câu CQL, có hoặc không có nháy kép.
- **Internal form:** tên chính xác được lưu trong metadata Cassandra, **không có** dấu nháy kép.

Các phương thức quan trọng:

| API | Nhận hoặc trả về | Cách dùng |
| --- | --- | --- |
| `CqlIdentifier.fromCql(String)` | Đầu vào là **CQL form** | Parse tên có quote, hoặc chuẩn hóa tên không quote về chữ thường. |
| `CqlIdentifier.fromInternal(String)` | Đầu vào là **internal form** | Khi đã biết tên đúng như được lưu trong schema. |
| `asInternal()` | Internal form | Lấy tên thật không kèm nháy kép, giữ chính xác chữ hoa/thường. |
| `asCql(true)` | CQL form ngắn gọn | Chỉ thêm nháy kép khi cần. |
| `asCql(false)` | CQL form luôn quote | Hữu ích khi dựng biểu thức CQL hợp lệ; không phải phương pháp bind tham số giá trị. |

Ví dụ thực thi độc lập:

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier a = CqlIdentifier.fromCql("DisplayName");
CqlIdentifier b = CqlIdentifier.fromCql("\"DisplayName\"");
CqlIdentifier c = CqlIdentifier.fromInternal("DisplayName");

System.out.println(a.asInternal()); // displayname
System.out.println(b.asInternal()); // DisplayName
System.out.println(b.asCql(true));  // "DisplayName"
System.out.println(a.asCql(true));  // displayname
System.out.println(b.equals(c));   // true
System.out.println(a.equals(b));   // false
```

Những kết quả trên rất quan trọng: `fromCql("DisplayName")` **không phải** cách lấy tên mixed-case được quote; muốn giữ đúng tên phải truyền `fromCql("\"DisplayName\"")` hoặc `fromInternal("DisplayName")`.

### Dùng identifier khi làm việc với metadata

`CqlIdentifier` không chỉ dùng với cột, mà còn xuất hiện trong API metadata của keyspace và bảng:

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;

CqlIdentifier keyspaceId = CqlIdentifier.fromCql("commerce");
CqlIdentifier tableId = CqlIdentifier.fromCql("\"LegacyCustomer\"");
CqlIdentifier columnId = CqlIdentifier.fromCql("\"DisplayName\"");

try (CqlSession session = CqlSession.builder()
        .withKeyspace(keyspaceId)
        // Contact points, local DC, TLS, credentials được cấu hình ngoài ví dụ.
        .build()) {

    session.getMetadata()
        .getKeyspace(keyspaceId)
        .flatMap(ks -> ks.getTable(tableId))
        .ifPresent(table -> {
            boolean exists = table.getColumn(columnId).isPresent();
            System.out.println("Exists: " + exists);
        });
}
```

Ví dụ trình bày API; session vẫn cần cấu hình driver đầy đủ theo môi trường. Trong ứng dụng Spring Boot, nên dùng session bean do Spring quản lý thay vì tạo `CqlSession` mới cho mỗi lần tra metadata.

### Tên identifier và giá trị dữ liệu không phải một

Cassandra chuẩn hóa **tên cột**, không có nghĩa dữ liệu string trong các ô bị tự động đổi thành chữ thường. Ví dụ:

```sql
-- "DisplayName" là identifier, 'Nguyễn Văn A' là giá trị string.
UPDATE commerce."LegacyCustomer"
SET "DisplayName" = 'Nguyễn Văn A'
WHERE "CustomerId" = 11111111-1111-1111-1111-111111111111;
```

Trong truy vấn có tham số, ký tự `?`/bind marker đại diện cho **giá trị dữ liệu**, không thể dùng thay tên bảng/cột. Nếu chương trình cần chọn một cột động, hãy chọn từ danh sách identifier cho phép rồi dùng `CqlIdentifier.asCql(...)` để render tên cột, đồng thời bind các giá trị riêng. Không nối trực tiếp tên bảng/cột lấy từ request HTTP vào CQL.

## 5. Chuẩn đặt tên: ưu tiên chữ thường và snake_case

Nếu bạn kiểm soát schema mới, tên viết thường như `customer_profile`, `customer_id`, `display_name` làm truy vấn và ánh xạ đơn giản hơn. Phương án này phù hợp cả khi dùng `CassandraRepository`, `CassandraTemplate` hay CQL thủ công.

Quy trình nhất quán:

1. **Thiết kế bảng theo truy vấn:** chọn partition key, clustering columns và cột dữ liệu trước; tránh phụ thuộc vào việc entity Java có camelCase.
2. **Đặt tên CQL rõ ràng:** ưu tiên `snake_case` không quote cho keyspace, bảng và cột.
3. **Đánh dấu mapping cần thiết:** dùng `@Table("customer_profile")`, `@PrimaryKey("customer_id")`, `@Column("display_name")` để không phụ thuộc ngoài ý muốn vào naming strategy.
4. **Tách quản lý schema:** sử dụng CQL migration/quy trình triển khai được kiểm soát; annotation mapping không có nghĩa tự thực hiện migration dữ liệu an toàn.
5. **Viết `@Query` dựa trên schema thật:** dùng đúng tên bảng/cột và điều kiện partition key; quote đồng bộ nếu buộc phải hỗ trợ legacy mixed-case.
6. **Kiểm tra bằng môi trường tích hợp:** chạy insert/select theo repository/template/CQL và so sánh column metadata với những gì mapper kỳ vọng.

`CqlIdentifier` vẫn hữu ích khi đọc metadata hoặc xây các công cụ làm việc với nhiều schema, nhưng bạn ít phải thao tác trực tiếp với nó nếu toàn bộ schema dùng identifier chữ thường không quote.

### Có nên dùng `forceQuote = true`?

Ở các phiên bản Spring Data Cassandra hiện đại, thuộc tính `forceQuote` trên `@Column` đã **deprecated** (từ Spring Data Cassandra 3.0) và dự kiến bị loại bỏ. Tên annotation hiện được chuyển thành `CqlIdentifier`, vì vậy không nên dùng `forceQuote` như giải pháp chính để giữ tên chữ hoa. Cách rõ ràng hơn khi schema thật sự có tên mixed-case là khai báo đúng **quoted CQL identifier**, ví dụ:

```java
@Column("\"DisplayName\"")
private String displayName;
```

Đừng thêm nháy kép cho mọi cột chỉ vì thuộc tính Java viết kiểu camelCase. Với `display_name` không quote, sử dụng `@Column("display_name")` là đủ.

## 6. Kiểm tra tên schema và chẩn đoán lỗi

Khi entity map sai tên, ứng dụng có thể gặp lỗi kiểu “undefined column”, “unconfigured table”, lỗi mapping/codec, hoặc kết quả đọc không như dự kiến. Hãy kiểm tra **schema thật** trước khi thay cấu hình mapper.

Đối với bảng `commerce."LegacyCustomer"`:

```sql
-- system_schema lưu tên nội bộ chính xác, không kèm dấu nháy kép.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'commerce';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'commerce'
  AND table_name = 'LegacyCustomer';
```

Trong bảng `system_schema.columns`, giá trị `column_name` của cột mixed-case sẽ là `DisplayName`, **không phải** chuỗi có ký tự nháy kép `"DisplayName"`. Điều kiện `table_name = 'LegacyCustomer'` là phép so sánh **giá trị text**, phải đúng chữ hoa/thường của tên nội bộ.

| Triệu chứng | Cách suy luận | Cách sửa |
| --- | --- | --- |
| `@Column("DisplayName")` nhưng bảng có `"DisplayName"` | Annotation chỉ định identifier không quote, bị chuẩn hóa về `displayname`. | Đổi thành `@Column("\"DisplayName\"")`. |
| `@Table("LegacyCustomer")` không thấy `"LegacyCustomer"` | Tên bảng không quote được hiểu là `legacycustomer`. | Dùng quoted identifier trong `@Table`. |
| `@Column("display_name")` nhưng bảng chỉ có `displayName` không quote | `displayName` không quote thực ra lưu là `displayname`, khác `display_name`. | Đối chiếu schema thật, đồng bộ tên hoặc migration. |
| Repository cơ bản chạy, `@Query` thủ công báo lỗi cột | CQL trong `@Query` chưa quote identifier. | Chỉnh chuỗi CQL cho khớp schema. |
| Tìm metadata bằng `fromCql("LegacyCustomer")` không ra bảng | `fromCql` đã chuyển thành `legacycustomer`. | Dùng `fromCql("\"LegacyCustomer\"")` hoặc `fromInternal("LegacyCustomer")`. |
| Sau migration, ứng dụng tiếp tục tham chiếu cột cũ | Mapper, `@Query` hoặc code thao tác trực tiếp driver chưa cùng cập nhật. | Cập nhật code và schema theo kế hoạch tương thích/triển khai. |

**Không sửa sai tên bằng `ALLOW FILTERING`.** `ALLOW FILTERING` liên quan điều kiện truy vấn, không biến một identifier không tồn tại thành cột hợp lệ. Tương tự, tăng consistency level, tăng số contact point hoặc đổi partition key không giải quyết lỗi quoting.

### Một quy trình kiểm tra ngắn

- Lấy đúng câu CQL gây lỗi từ log có che dữ liệu nhạy cảm và xác minh tên bảng/cột.
- Kiểm tra tên nội bộ thực trong `system_schema.tables` và `system_schema.columns`.
- So sánh `@Table`, `@PrimaryKey`, `@PrimaryKeyColumn`, `@Column` và các câu `@Query`.
- Kiểm tra dấu nháy kép theo cú pháp **CQL**, sau đó mới kiểm tra escape khi biểu diễn dưới dạng chuỗi **Java**.
- Dùng `CqlIdentifier.fromCql(...).asInternal()` để xác định driver hiểu tên ra sao nếu còn nghi ngờ.
- Chạy lại một truy vấn đúng partition key và một thao tác repository/template trên môi trường thử nghiệm.

## 7. Tình huống thực tế: chuyển từ bảng legacy sang quy ước mới

Giả sử dự án đang có bảng `commerce."LegacyCustomer"` với cột `"DisplayName"`. Nhóm muốn dần chuyển sang bảng mới `commerce.customer_profile` với `display_name` để sử dụng ổn định hơn.

Các bước nên được quản lý như một migration dữ liệu:

1. Khảo sát mọi CQL, repository, template và consumer đang sử dụng bảng mixed-case.
2. Tạo schema mới với tên chuẩn, partition key và kiểu dữ liệu phù hợp truy vấn nghiệp vụ.
3. Backfill dữ liệu, kiểm tra số lượng/bản ghi, timestamp và tính đúng đắn theo kế hoạch.
4. Chuyển dần luồng đọc/ghi, cân nhắc đồng bộ hai nơi trong giai đoạn chuyển tiếp khi cần.
5. Chỉ loại bỏ bảng cũ sau khi xác nhận các client và quy trình phụ trợ đã chuyển.

`@Column("display_name")` trên entity mới **không tự di chuyển dữ liệu** từ `"DisplayName"` sang `display_name`. Thay đổi tên còn có thể ảnh hưởng đến raw CQL, batch statements, prepared statements, metadata cache và các báo cáo vận hành.

Nếu chỉ có một cột sai tên và muốn giữ nguyên bảng, cách migration cần dựa vào những thao tác schema mà phiên bản Cassandra đang chạy thực sự hỗ trợ; **không giả định mọi cột đều có thể đổi tên tại chỗ**.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Cassandra có một cột được tạo bằng `"FullName"`. `@Column("FullName")` có tham chiếu đúng cột đó không? Giải thích.

**Câu 2.** Vì sao `@Column("display_name")` có thể cần thiết dù thuộc tính Java đã đặt tên `displayName`?

**Câu 3.** Với Java driver 4.x, hai biểu thức sau khác nhau thế nào?

```java
CqlIdentifier.fromCql("OrderItem").asInternal();
CqlIdentifier.fromCql("\"OrderItem\"").asInternal();
```

**Câu 4.** Vì sao `@Query("SELECT DisplayName FROM ...")` có thể thất bại dù mapper đã dùng `@Column("\"DisplayName\"")`?

**Câu 5.** Khi kiểm tra bảng `"LegacyCustomer"` trong `system_schema.tables`, giá trị `table_name` là `LegacyCustomer` hay `"LegacyCustomer"`? Tại sao?

**Câu 6.** Một service nhận tên cột qua HTTP và muốn truy vấn động. Có thể bind tên cột bằng `?` không? Nếu không, cần làm gì?

**Đáp án gợi ý:**

1. Không. `FullName` không quote sẽ thành `fullname`, còn cột thật có internal name `FullName`. Dùng `@Column("\"FullName\"")`.
2. Quy ước Java camelCase không bắt buộc khớp tên CQL snake_case; annotation ánh xạ tường minh để tránh phụ thuộc naming strategy.
3. Biểu thức đầu trả `orderitem`; biểu thức sau trả `OrderItem`.
4. `@Query` là chuỗi CQL do người viết kiểm soát; sửa annotation không tự động thêm nháy kép vào literal query.
5. Giá trị lưu là `LegacyCustomer`, vì metadata trả internal form không có dấu nháy kép.
6. Không bind identifier như giá trị. Cần whitelist tên cột hợp lệ, render bằng `CqlIdentifier.asCql(...)` và bind riêng các giá trị.

**Ghi nhớ:** `@Column` nối thuộc tính Java với tên cột Cassandra; quy tắc **quoted/unquoted** quyết định chữ hoa/thường của tên CQL; `CqlIdentifier` giúp chuyển đổi minh bạch giữa **CQL form** và **internal form**. Hãy ưu tiên schema chữ thường, dùng quoted identifier nhất quán khi buộc tích hợp bảng legacy, và kiểm tra cả annotation lẫn CQL viết tay.

### Tài liệu đối chiếu

- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html)
- [Spring Data Cassandra — `@Column` API](https://www.springframework.org/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/mapping/Column.html)
- [Apache Cassandra Java Driver — Case Sensitivity](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/)
- [Apache Cassandra Java Driver — `CqlIdentifier` API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/CqlIdentifier.html)
