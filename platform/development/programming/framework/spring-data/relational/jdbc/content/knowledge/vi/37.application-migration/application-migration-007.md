# Tiếp nhận schema có sẵn mà không thay đổi dữ liệu ngoài ý muốn

Đưa Spring Data Relational JDBC vào một ứng dụng đang có database không có nghĩa là phải tạo lại schema hoặc nạp lại dữ liệu. Spring Data JDBC có thể làm việc với các bảng, khóa và dữ liệu hiện hữu nếu mapping khớp chính xác với cấu trúc database. Phần khó là giữ nguyên hợp đồng mà các ứng dụng, báo cáo, trigger, stored procedure và batch job đang phụ thuộc.

Nguyên tắc an toàn là **khám phá trước, ánh xạ sau, thay đổi schema cuối cùng và chỉ khi thực sự cần**:

1. Ghi nhận schema, dữ liệu, constraints, index, sequence, trigger và các consumer hiện có.
2. Thiết kế mapping Spring Data JDBC khớp schema hiện hữu bằng tên bảng/cột tường minh.
3. Kiểm tra hành vi insert/update/delete trên bản sao database có dữ liệu đại diện.
4. Quản lý thay đổi cần thiết bằng migration có version, không để ứng dụng tự ý sửa schema.
5. So sánh dữ liệu trước/sau và triển khai theo từng bước có thể quan sát, khôi phục.

Bài này tập trung vào việc tiếp nhận database hiện hữu cho Spring Data JDBC, giữ nguyên dữ liệu và hạn chế side effect. Mục tiêu đầu tiên là đọc đúng dữ liệu hiện có; chỉ bật đường ghi sau khi đã xác nhận mapping và transaction behavior.

## 1. Phân biệt schema hiện hữu với mapping Java

Schema là hợp đồng của database: bảng, cột, kiểu dữ liệu, primary key, foreign key, unique/check constraint, index, default, sequence, trigger, view và quyền truy cập.

Mapping Java là cách Spring Data JDBC diễn giải hợp đồng đó. Annotation không tự thay đổi schema hiện hữu. Ví dụ:

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @Column("customer_no")
    private Long customerId;

    @Column("order_state")
    private String status;
}
~~~

Class trên yêu cầu Spring Data JDBC ánh xạ vào bảng legacy_order với các cột order_no, customer_no và order_state. Nếu database thật có tên khác, type khác hoặc schema khác, mapping phải được điều chỉnh cho đúng.

Đừng suy ra rằng đổi tên property Java sẽ rename cột database. Đổi annotation cũng không chạy migration. DDL chỉ thay đổi khi một công cụ hoặc người dùng thực thi câu lệnh DDL tương ứng.

### Những thành phần cần kiểm kê

| Thành phần | Cần ghi nhận |
|---|---|
| Bảng và schema | Tên chính xác, case sensitivity, owner/schema mặc định |
| Cột | Tên, kiểu, length, precision/scale, nullable |
| Primary key | Một cột hay composite, kiểu ID, generated hay assigned |
| Foreign key | Cột tham chiếu, delete/update action, constraint có đang enabled không |
| Unique/check | Business key, điều kiện dữ liệu hợp lệ |
| Index | Cột, thứ tự, unique, partial/filter index |
| Default | Giá trị mặc định, expression, sequence |
| Trigger | Tự sinh audit, cập nhật timestamp, cascade nghiệp vụ |
| Sequence/identity | Tên sequence, current value, increment, cache |
| View/procedure | Consumer, quyền và semantics |
| Data | Số hàng, NULL, duplicate, orphan, giá trị biên |
| Writer hiện tại | Ứng dụng, batch, ETL, báo cáo hoặc SQL thủ công |

Schema dump và migration history nên được lưu cùng hồ sơ triển khai để có thể đối chiếu sau này.

## 2. Bắt đầu bằng quyền đọc và bản sao dữ liệu

Trước khi nối Spring Data JDBC vào môi trường có dữ liệu thật:

- Lấy schema dump hoặc metadata snapshot.
- Tạo backup có thể restore và kiểm tra quy trình restore.
- Dùng staging/database clone có cấu trúc và dữ liệu đại diện.
- Cấp quyền read-only cho bước khám phá nếu có thể.
- Không chạy repository save/delete, migration hoặc seed script trên production chỉ để xem mapping.
- Ghi lại migration version và database version hiện tại.

Một kết nối đọc có thể giúp xác minh mapping và query mà không cần cấp quyền ghi. Với ứng dụng mới, có thể cấu hình một DataSource read-only hoặc database user chỉ có SELECT trong giai đoạn shadow-read. Quyền read-only ở JDBC connection hoặc application configuration không thay thế quyền database; quyền thực tế nên được giới hạn ở database user.

### Chụp số liệu baseline

Ví dụ các câu SQL kiểm tra tổng quan:

~~~sql
SELECT COUNT(*) AS order_count
FROM legacy_order;

SELECT COUNT(*) AS line_count
FROM legacy_order_line;

SELECT COUNT(*) AS rows_without_customer
FROM legacy_order
WHERE customer_no IS NULL;

SELECT order_state, COUNT(*) AS total
FROM legacy_order
GROUP BY order_state
ORDER BY order_state;
~~~

Đây là baseline để so sánh sau migration hoặc sau khi bật đường ghi mới. Với bảng lớn, COUNT(*) có thể tốn tài nguyên; chọn thời điểm, snapshot hoặc thống kê phù hợp với database.

Ngoài số lượng, nên ghi nhận:

- Tổng số ID distinct.
- Min/max ID và timestamp.
- Số NULL theo cột quan trọng.
- Số duplicate theo business key.
- Số FK không có parent nếu schema legacy không enforce FK.
- Tổng tiền/tổng quantity cho các invariant quan trọng.
- Một tập mẫu đã mask nhưng giữ quan hệ và kiểu dữ liệu.

## 3. Ánh xạ tên bảng và cột tường minh

Spring Data Relational có NamingStrategy để suy ra tên bảng/cột từ class/property. Schema legacy thường có quy ước riêng: prefix, abbreviation, chữ hoa, tên viết tắt hoặc tên cột không khớp property Java.

Khi tiếp nhận schema có sẵn, ưu tiên mapping tường minh cho những tên quan trọng:

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @Column("customer_no")
    private Long customerId;

    @Column("order_state")
    private String status;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

Nếu schema có bảng ORDER_HEADER và cột ORDER_ID, hãy map đúng identifier theo database và JDBC driver. Một số database phân biệt identifier được quote với identifier không quote; quy tắc case-folding khác nhau giữa vendor. Đừng đổi chữ hoa/thường trong migration chỉ để khớp style Java.

### Dùng NamingStrategy khi có quy ước nhất quán

Nếu toàn bộ schema legacy dùng một quy tắc rõ ràng, có thể cấu hình NamingStrategy tùy chỉnh. Tuy nhiên, nếu chỉ một số bảng/cột có ngoại lệ, @Table và @Column thường dễ hiểu và ít ảnh hưởng diện rộng hơn.

Khi đổi NamingStrategy, ảnh hưởng có thể lan đến nhiều aggregate. Hãy kiểm tra metadata mapping cho toàn bộ entity liên quan trước khi triển khai.

### Schema/catalog và default schema

Nếu database có nhiều schema như sales, billing và reporting, bảo đảm connection mặc định trỏ đúng schema hoặc SQL/mapping được cấu hình đúng. Một bảng cùng tên có thể tồn tại trong nhiều schema; query chạy đúng ở local nhưng trỏ nhầm schema ở production là rủi ro dữ liệu lớn.

Không giả định tên database trong JDBC URL đồng nghĩa tên schema. Xác minh current schema/search path bằng câu query đặc thù database và user thực tế.

## 4. Giữ nguyên primary key và chiến lược ID

ID hiện hữu thường được tham chiếu bởi bảng khác, API, file import, hệ thống ngoài và báo cáo. Không đổi ID chỉ để chuyển framework.

Với root có primary key số:

~~~java
@Table("legacy_customer")
public class Customer {

    @Id
    @Column("customer_no")
    private Long id;

    @Column("display_name")
    private String name;
}
~~~

Trước khi ghi, xác định ID được sinh bởi:

- Identity/auto-increment column.
- Database sequence.
- Trigger.
- Ứng dụng cấp ID.
- Hệ thống ngoài/import file cấp ID.

Spring Data JDBC và JDBC dialect cần phù hợp với cách sinh ID của database. Kiểm thử insert trên đúng engine/driver để xác nhận generated key được trả về và gán vào object.

### Assigned ID và xác định entity mới

Nếu ứng dụng legacy cấp ID trước khi insert, ID khác null không nhất thiết có nghĩa row đã tồn tại. Spring Data JDBC dùng newness detection; với assigned ID, cần cấu hình trạng thái mới phù hợp, ví dụ implement Persistable và isNew() khi cần.

~~~java
public class ImportedCustomer implements Persistable<Long> {

    @Id
    @Column("customer_no")
    private Long id;

    @Transient
    private boolean newEntity;

    protected ImportedCustomer() {}

    public ImportedCustomer(Long id, String name) {
        this.id = id;
        this.name = name;
        this.newEntity = true;
    }

    @Override
    public Long getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }
}
~~~

Ví dụ rút gọn; cần bổ sung cách chuyển trạng thái sau insert theo lifecycle/immutable model của ứng dụng. Nếu cờ isNew luôn true, lần save tiếp theo có thể thử insert lại và vi phạm primary key. Nếu luôn false, lần save đầu có thể đi vào nhánh update.

### Không reset sequence tùy tiện

Nếu import dữ liệu với ID thủ công vào bảng identity/sequence, sequence hiện tại có thể thấp hơn MAX(id). Insert tiếp theo có thể va chạm primary key.

Trước khi đồng bộ sequence:

1. Xác định sequence/identity thực sự được dùng.
2. Đọc current value và MAX(primary_key).
3. Kiểm tra các writer khác có thể cấp ID đồng thời không.
4. Dùng lệnh vendor-specific được review và chạy trong maintenance window nếu cần.
5. Xác nhận insert tiếp theo không tạo ID trùng.

Không chạy lệnh setval/ALTER SEQUENCE theo ví dụ chung trên production mà chưa xác định tên sequence, quyền và concurrency.

## 5. Ánh xạ collection mà không thay đổi cấu trúc bảng ngoài ý muốn

Trong Spring Data JDBC, entity được sở hữu trong collection thường nằm ở bảng riêng và có FK về owner. @MappedCollection xác định cột FK và cột key/index nếu collection cần định vị phần tử.

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @MappedCollection(idColumn = "order_no", keyColumn = "line_position")
    private List<OrderLine> lines = new ArrayList<>();
}

@Table("legacy_order_line")
public class OrderLine {

    @Id
    @Column("line_no")
    private Long id;

    @Column("product_no")
    private Long productId;

    @Column("ordered_qty")
    private Integer quantity;
}
~~~

Mapping này giả định bảng legacy_order_line có cột order_no trỏ về legacy_order.order_no và line_position lưu vị trí của List. Hãy đối chiếu chính xác tên cột, kiểu dữ liệu và constraints trong schema thật.

| Mapping | Cột legacy cần có |
|---|---|
| Root @Id | Primary key root |
| @MappedCollection(idColumn = "order_no") | FK order_no trong bảng child |
| keyColumn = "line_position" | Cột lưu index/key của collection |
| Child @Id | PK của child nếu mapping dùng child identity |
| Child reference productId | Cột product_no, có FK nếu schema enforce |

### List cần thứ tự bền vững

Nếu Java model dùng List, database phải có cách lưu vị trí phần tử. Nếu bảng legacy không có order/index column, không thể giả định thứ tự đọc sẽ giống thứ tự insert hoặc thứ tự vật lý trong bảng.

Các lựa chọn:

- Thêm cột position qua migration nếu thứ tự là một phần của contract.
- Dùng Set nếu domain không cần thứ tự.
- Dùng query tùy chỉnh có ORDER BY cho read model.
- Giữ một property sortOrder/businessLineNumber đã tồn tại nếu nó biểu diễn thứ tự.

Không tự thêm keyColumn vào annotation khi cột tương ứng chưa tồn tại. Annotation không tạo cột và query sẽ lỗi khi framework tham chiếu cột không có.

### Map và Set

Map cần cột key phù hợp; Set không nên dựa vào thứ tự. Nếu schema legacy dùng composite key hoặc association table đặc biệt, kiểm tra mapping thực tế trước khi coi đó là owned collection tiêu chuẩn.

Nếu một bảng child được nhiều root cùng tham chiếu hoặc có lifecycle độc lập, đừng map nó thành child được sở hữu chỉ để tiện tải. Hãy xác định aggregate boundary và dùng ID/reference hoặc read query phù hợp.

## 6. Giữ nguyên quan hệ giữa các aggregate

Một cột FK như customer_no trong legacy_order thường biểu diễn reference đến Customer, không có nghĩa Customer là child của PurchaseOrder.

Có thể map scalar ID:

~~~java
@Column("customer_no")
private Long customerId;
~~~

Hoặc dùng AggregateReference nếu domain muốn biểu đạt rõ reference đến aggregate root khác:

~~~java
private AggregateReference<Customer, Long> customer;
~~~

Dù chọn cách nào, Spring Data JDBC không tự tải Customer qua lazy proxy và không cascade save/delete sang aggregate Customer.

Nếu cần customer name trên màn hình đơn hàng, dùng query JOIN/projection. Nếu cần sửa Customer, tải và lưu Customer qua repository của aggregate đó.

### Bảo vệ FK legacy

Không thêm FK mới chỉ vì Java model có property reference. Trước hết kiểm tra dữ liệu hiện hữu có thỏa constraint hay không:

~~~sql
SELECT o.order_no, o.customer_no
FROM legacy_order o
LEFT JOIN legacy_customer c
    ON c.customer_no = o.customer_no
WHERE o.customer_no IS NOT NULL
  AND c.customer_no IS NULL;
~~~

Nếu query trả hàng, database đang có orphan reference. Thêm FK ngay có thể thất bại hoặc buộc phải sửa dữ liệu. Hãy xác định đây là dữ liệu hợp lệ theo legacy contract, lỗi cần làm sạch, hay reference đến hệ thống ngoài.

## 7. Giữ nguyên nullability, default và SQL type

Mapping Java phải tương thích với SQL type hiện hữu. Không chuyển tất cả numeric thành Long hoặc tất cả timestamp thành LocalDateTime mà không xem precision/semantics.

| SQL hiện hữu | Java type thường cân nhắc | Điều cần xác nhận |
|---|---|---|
| BIGINT | Long | ID range và signedness theo vendor |
| INTEGER | Integer | Range và nullability |
| NUMERIC(p,s) | BigDecimal | Precision/scale, rounding |
| CHAR(n)/VARCHAR(n) | String | Padding, length, collation |
| DATE | LocalDate | Chỉ có ngày |
| TIMESTAMP | LocalDateTime | Không tự mang timezone |
| TIMESTAMP WITH TIME ZONE | Instant/OffsetDateTime phù hợp driver | Normalize timezone và JDBC mapping |
| UUID/native uniqueidentifier | UUID hoặc converter | Driver/dialect hỗ trợ |
| JSON/JSONB | String/JsonNode/custom type | TypeHandler/converter và native JDBC type |
| BINARY/BLOB | byte[] hoặc stream | Kích thước và memory behavior |

### NULL khác với default

Một cột có DEFAULT không có nghĩa truyền SQL NULL sẽ dùng default. Trong SQL, default thường được áp dụng khi bỏ cột khỏi INSERT hoặc dùng DEFAULT keyword; nếu câu INSERT truyền NULL tường minh, cột có thể nhận NULL hoặc vi phạm NOT NULL.

Spring Data JDBC tạo INSERT dựa trên mapping và giá trị object. Nếu database có default/trigger quan trọng, kiểm tra SQL và generated-value behavior thực tế. Không giả định property Java null sẽ khiến database tự dùng default.

### Cột được sinh bởi trigger hoặc database

Schema legacy có thể tự gán created_on, modified_on, status_code hoặc audit_user bằng default/trigger. Nếu framework cũng ghi những cột đó, có thể xung đột hoặc ghi đè giá trị database sinh.

Cần quyết định rõ nguồn sự thật:

- Ứng dụng cung cấp giá trị.
- Database default/trigger cung cấp giá trị.
- Một quy trình ETL khác cung cấp giá trị.

Chỉ một cơ chế nên sở hữu một giá trị tại một thời điểm. Dùng mapping read-only hoặc generated-value mechanism được Spring Data Relational phiên bản hiện tại hỗ trợ khi thích hợp; kiểm tra SQL INSERT/UPDATE và đọc lại row để xác nhận. Nếu không chắc chắn, giữ cột ngoài write model và đọc bằng query riêng cho đến khi behavior được xác nhận.

## 8. Converter cho kiểu dữ liệu legacy

Schema có thể dùng mã trạng thái, char flag, numeric enum hoặc định dạng ngày giờ cũ. Spring Data JDBC dùng conversion infrastructure riêng; không giả định converter Hibernate/AttributeConverter tự được dùng.

Ví dụ legacy lưu trạng thái bằng một ký tự:

~~~java
public enum OrderStatus {
    OPEN("O"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException("Unknown order status"));
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Đăng ký hai converter trong JdbcCustomConversions theo cấu hình Spring Data JDBC của ứng dụng. Kiểm tra giá trị legacy không nhận diện được, NULL, khoảng trắng và chữ thường/chữ hoa. Không tự map mã không biết thành một trạng thái hợp lệ mặc định vì điều đó có thể làm sai nghiệp vụ.

Nếu cần chuyển đổi dữ liệu cũ, hãy viết migration/backfill có thống kê trước/sau; converter chỉ thay đổi cách ứng dụng đọc/ghi, không tự sửa dữ liệu đang lưu.

## 9. Không giả định save() chỉ cập nhật vài cột

Một khác biệt quan trọng khi tiếp nhận schema là hành vi ghi aggregate. Spring Data JDBC không dirty-check từng field như JPA. Repository save lưu aggregate theo mapping và có thể thực hiện nhiều INSERT/UPDATE/DELETE cho owned entities.

Với aggregate có collection, chiến lược persistence có thể xóa và insert lại các child rows khi cập nhật root. Điều này có thể ảnh hưởng:

- Child primary key và generated values.
- Trigger chạy trên DELETE/INSERT.
- Audit history và CDC.
- FK từ bảng ngoài tham chiếu đến child.
- Timestamp/created_by do database tự sinh.
- Bảng association dùng chung với hệ thống khác.

Trước khi dùng save trên aggregate legacy, bật SQL logging ở staging và quan sát đầy đủ statement. Kiểm tra liệu child row có được cập nhật tại chỗ hay bị xóa/insert lại theo phiên bản framework/mapping. Nếu bảng child được hệ thống ngoài tham chiếu bằng ID hoặc có trigger quan trọng, đây là điều kiện phải xác minh trước khi bật write path.

Không gọi save chỉ để “đồng bộ object” sau một lần đọc. Chỉ gọi save khi use case thực sự muốn lưu thay đổi aggregate.

### Partial update không phải aggregate save

Nếu chỉ muốn đổi một cột trong bảng lớn có trigger hoặc nhiều cột do hệ thống khác quản lý, một câu UPDATE tường minh có thể an toàn hơn việc load rồi save toàn aggregate. Ví dụ:

~~~java
@Modifying
@Query("""
    UPDATE legacy_order
    SET order_state = :status
    WHERE order_no = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

Đây là minh họa cho DML tường minh; cú pháp và hỗ trợ query annotation cần khớp phiên bản Spring Data JDBC. Custom repository với JdbcTemplate là lựa chọn khác.

Khi dùng direct DML, ứng dụng tự chịu trách nhiệm về version, auditing, domain invariant và cache invalidation. Không kỳ vọng entity callbacks của save được gọi cho câu UPDATE tùy chỉnh.

## 10. Soft delete và cột trạng thái legacy

Một số hệ thống không xóa row vật lý mà dùng deleted_flag, active, record_status hoặc deleted_at.

Spring Data JDBC repository.delete thường biểu diễn thao tác xóa persistence của aggregate, không tự hiểu cột soft-delete legacy. Nếu gọi delete trực tiếp, row có thể bị xóa vật lý theo mapping.

Nếu hệ thống yêu cầu soft delete:

- Dùng domain method đổi trạng thái và save aggregate nếu phù hợp.
- Hoặc dùng custom UPDATE có điều kiện.
- Đảm bảo mọi query đọc lọc đúng trạng thái deleted/active.
- Định nghĩa uniqueness semantics: unique trên tất cả row hay chỉ row chưa xóa.
- Kiểm tra FK và retention policy.
- Không gọi repository.delete khi nghiệp vụ chỉ muốn đánh dấu đã xóa.

Soft delete thường là business lifecycle, không phải chỉ là một cờ kỹ thuật. Đưa quy tắc vào service/domain và bảo vệ bằng query/constraint phù hợp.

## 11. Kiểm tra schema hiện hữu trước khi thêm constraints

Database legacy có thể chứa dữ liệu trước khi constraints được thêm hoặc có quy trình cũ không enforce đầy đủ.

Trước khi thêm NOT NULL:

~~~sql
SELECT COUNT(*)
FROM legacy_order
WHERE order_state IS NULL;
~~~

Trước khi thêm unique:

~~~sql
SELECT external_order_code, COUNT(*)
FROM legacy_order
GROUP BY external_order_code
HAVING COUNT(*) > 1;
~~~

Trước khi thêm FK:

~~~sql
SELECT line.order_no
FROM legacy_order_line line
LEFT JOIN legacy_order root
    ON root.order_no = line.order_no
WHERE root.order_no IS NULL;
~~~

Nếu dữ liệu vi phạm, không xóa hoặc sửa hàng tự động chỉ để migration chạy qua. Xác định owner nghiệp vụ, quy tắc làm sạch, backup và cách xử lý từng nhóm. Có thể thêm constraint sau khi backfill và xác minh hoàn tất.

Với bảng lớn, tạo index/constraint có thể khóa bảng hoặc tiêu tốn tài nguyên. Dùng chiến lược online/concurrent phù hợp database vendor và maintenance window.

## 12. Quản lý migration và baseline schema

Spring Data JDBC tập trung vào mapping/persistence, không phải công cụ đồng bộ DDL production. Dùng Flyway hoặc Liquibase để quản lý schema version.

Nếu database đã tồn tại trước khi đưa Flyway vào, cần **baseline** migration history đúng với trạng thái schema hiện tại. Baseline chỉ ghi nhận điểm bắt đầu theo cấu hình công cụ; nó không chứng minh schema thực tế khớp với migration history và không tự làm sạch dữ liệu.

Quy trình baseline:

1. Dump schema hiện hữu và lưu bản kiểm chứng.
2. Đối chiếu bảng/cột/constraint/index với trạng thái mà baseline version đại diện.
3. Xác định version baseline và migration nào sẽ chạy sau đó.
4. Thử baseline trên bản clone trước.
5. Xác nhận Flyway/Liquibase không chạy lại migration tạo bảng đã có.
6. Chạy migration tiếp theo trên clone và so sánh schema/data.
7. Sau khi review, mới lập kế hoạch cho môi trường dùng chung.

Không bật baselineOnMigrate một cách mù quáng trên mọi database. Cấu hình baseline không nên che giấu việc ứng dụng đang kết nối nhầm schema hoặc schema đã lệch.

### Không để nhiều cơ chế cùng sửa schema

Kiểm tra các cơ chế sau có đang bật không:

- Flyway/Liquibase migrations.
- Spring Boot SQL initialization qua schema.sql/data.sql.
- Hibernate DDL auto nếu JPA còn trong ứng dụng.
- Script khởi tạo riêng của deployment.
- Trigger/procedure tự tạo object.

Chọn một nguồn quản lý schema chính. Tránh để Hibernate create/update và Flyway cùng thay đổi một schema không có quy ước rõ ràng. Với production database hiện hữu, không chạy schema initialization ngoài ý muốn khi ứng dụng khởi động.

## 13. Dùng expand–migrate–contract cho thay đổi bắt buộc

Nếu mapping mới cần một cột chưa có, không nên deploy code mới giả định cột tồn tại trước khi schema được cập nhật.

Dùng ba giai đoạn:

~~~mermaid
flowchart TD
    A["Expand"] --> B["Thêm cột/bảng mới, giữ code cũ hoạt động"]
    B --> C["Deploy code tương thích"]
    C --> D["Backfill và xác minh dữ liệu"]
    D --> E["Chuyển read/write sang cấu trúc mới"]
    E --> F["Contract"]
    F --> G["Xóa cột/bảng cũ sau khi không còn consumer"]
~~~

Ví dụ đổi customer_code thành customer_id:

1. Expand: thêm customer_id nullable và index/FK sau khi dữ liệu sạch.
2. Deploy: code có thể đọc cả cột cũ/mới hoặc ghi đồng bộ theo quy tắc rõ.
3. Backfill: điền customer_id từ customer_code theo batch có checkpoint.
4. Verify: so sánh số hàng, NULL, orphan và mapping theo business key.
5. Cutover: chuyển đọc sang customer_id.
6. Contract: chỉ xóa customer_code sau khi mọi consumer cũ đã ngừng sử dụng.

Nếu dual-write, phải có quy tắc nhất quán và cách xử lý partial failure. Không ghi hai cột vô thời hạn mà không có nguồn sự thật duy nhất.

## 14. Kiểm thử mapping trên bản sao database

@DataJdbcTest phù hợp để kiểm tra repository và mapping. Tuy nhiên, database embedded có thể không phản ánh đúng dialect, identity, trigger, type và constraint của production.

Với schema legacy, nên dùng Testcontainers chạy cùng engine/major version khi có thể. Nạp schema từ migration hoặc schema dump đã được làm sạch dữ liệu nhạy cảm.

Các test quan trọng:

- Load row hiện hữu mà không thay đổi dữ liệu.
- Mapping đúng tên bảng/cột và type.
- Đọc được NULL và giá trị biên.
- Generated ID hoạt động theo identity/sequence hiện hữu.
- Insert không bỏ qua hoặc ghi đè default/trigger ngoài ý muốn.
- Update root không làm mất cột do hệ thống khác quản lý.
- Update aggregate không gây delete/reinsert child ngoài mong đợi.
- FK, unique và check constraints vẫn được tôn trọng.
- Soft delete không biến thành physical delete.
- Optimistic locking hoạt động nếu có version column.
- Query read-only không phát DML.
- Transaction rollback không để lại một phần dữ liệu.

### Test đọc mà không ghi

~~~java
@DataJdbcTest
class LegacyOrderMappingTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void readsExistingRowWithoutChangingStoredValues() {
        jdbcTemplate.update("""
                INSERT INTO legacy_order(
                    order_no, customer_no, order_state, created_on
                )
                VALUES (?, ?, ?, ?)
                """,
                1001L,
                42L,
                "P",
                Timestamp.valueOf("2026-01-10 09:00:00")
        );

        PurchaseOrder order = repository.findById(1001L).orElseThrow();

        assertThat(order.getId()).isEqualTo(1001L);
        assertThat(order.getCustomerId()).isEqualTo(42L);
        assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);

        String storedState = jdbcTemplate.queryForObject(
                "SELECT order_state FROM legacy_order WHERE order_no = ?",
                String.class,
                1001L
        );

        assertThat(storedState).isEqualTo("P");
    }
}
~~~

Đây là ví dụ minh họa; repository/entity/converter và schema cần được cấu hình theo ứng dụng. Test slice mặc định thường chạy trong transaction và rollback khi kết thúc.

### Test update có kiểm soát

~~~java
@Test
void updatesOnlyTheIntendedBusinessValue() {
    PurchaseOrder order = repository.findById(1001L).orElseThrow();

    order.changeStatus(OrderStatus.CANCELLED);
    repository.save(order);

    Map<String, Object> row = jdbcTemplate.queryForMap("""
            SELECT order_state, customer_no
            FROM legacy_order
            WHERE order_no = ?
            """, 1001L);

    assertThat(row.get("order_state")).isEqualTo("C");
    assertThat(((Number) row.get("customer_no")).longValue()).isEqualTo(42L);
}
~~~

Nếu bảng có trigger, audit columns hoặc child collection, mở rộng test để xác nhận những cột/rows đó giữ đúng behavior. Không chỉ assert field vừa sửa; hãy assert những dữ liệu quan trọng không được phép thay đổi.

## 15. So sánh dữ liệu trước và sau migration

Sau mỗi migration hoặc rollout có ghi dữ liệu, so sánh baseline và kết quả:

| Kiểm tra | Câu hỏi |
|---|---|
| Row count | Số hàng có thay đổi ngoài dự kiến không? |
| Primary key | Có ID bị mất, trùng hoặc đổi không? |
| Business key | Có duplicate mới hoặc giá trị bị chuẩn hóa ngoài ý muốn không? |
| NULL count | Có cột bắt buộc bị thành NULL không? |
| FK/orphan | Có reference không hợp lệ không? |
| Aggregate totals | Tổng quantity/amount có giữ nguyên không? |
| Timestamps | Timezone/precision có thay đổi không? |
| Defaults/triggers | Audit/default-generated values có còn hoạt động không? |
| Sequence | ID tiếp theo có thể va chạm không? |
| Consumer compatibility | Ứng dụng/báo cáo cũ có còn đọc được không? |

Với dữ liệu lớn, checksum toàn bảng có thể tốn kém và không phải database nào cũng có cùng hàm hash. Có thể so sánh theo partition/key range, count và tổng hợp các cột nghiệp vụ quan trọng, sau đó lấy mẫu row chi tiết.

Mọi chênh lệch phải được phân loại: thay đổi dự kiến, backfill, trigger hợp lệ hay lỗi ngoài ý muốn. Không chỉ nhìn tổng row count vì hai tập dữ liệu khác nhau vẫn có thể có cùng số hàng.

## 16. Chạy song song JPA và Spring Data JDBC trong giai đoạn chuyển đổi

Một ứng dụng có thể tạm thời giữ JPA và Spring Data JDBC trong cùng runtime. Khi đó cần đặc biệt cẩn thận:

- Cả hai có thể dùng cùng database nhưng object/cache/lifecycle khác nhau.
- JPA persistence context có thể giữ entity cũ sau khi JDBC ghi.
- JDBC không biết entity nào đang managed trong EntityManager.
- JPA dirty checking có thể flush một object stale và ghi đè thay đổi mới từ JDBC.
- JPA cascade và JDBC aggregate save có thể tác động cùng child table theo semantics khác nhau.

Nếu buộc phải coexist:

1. Chọn một write owner cho mỗi aggregate/table trong từng giai đoạn.
2. Không để JPA và JDBC cùng ghi cùng aggregate tùy tiện.
3. Sau khi JDBC ghi, EntityManager có thể cần refresh/clear trước khi đọc lại dữ liệu qua JPA.
4. Sau khi JPA ghi, Spring Data JDBC repository load mới từ database theo transaction visibility; không dùng object cũ từ application cache.
5. Chỉ dùng cùng transaction khi cả hai thật sự dùng cùng DataSource/resource và transaction manager phù hợp.
6. Có test tích hợp cho thứ tự đọc/ghi hai chiều và rollback.

Tránh dual-write từ hai framework cho cùng một aggregate trong một thời gian dài. Chuyển từng use case và xác định thời điểm bỏ write path cũ.

## 17. Bảo vệ các hệ thống ngoài database

Database hiện hữu thường có nhiều consumer: API khác, ETL, BI, data warehouse, batch job, stored procedure hoặc script vận hành.

Trước khi đổi schema:

- Tìm consumer phụ thuộc tên bảng/cột.
- Xác định consumer đọc trực tiếp hay qua view.
- Kiểm tra trigger có phát event hoặc ghi audit.
- Xác định FK từ schema khác tham chiếu bảng đang đổi.
- Kiểm tra CDC/replication publication nếu có.
- Kiểm tra stored procedure/function dùng tên cột.
- Thông báo và phối hợp cutover theo compatibility window.

Không xóa cột chỉ vì ứng dụng mới không còn map nó. Cột có thể vẫn được hệ thống ngoài dùng. Dùng expand–contract và quan sát access trước khi contract.

## 18. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Repository không tìm thấy bảng | @Table/naming strategy hoặc default schema sai | Map tên tường minh và xác minh schema hiện tại |
| Column not found | @Column/idColumn/keyColumn không khớp | Đối chiếu metadata database với entity mapping |
| Insert dùng sai ID | Dialect/identity/sequence hoặc assigned ID newness sai | Kiểm tra generated-key path và isNew |
| Insert trùng primary key | Sequence thấp hơn MAX(ID) hoặc object bị coi là new | Kiểm tra sequence và newness detection |
| Default không được áp dụng | SQL INSERT truyền NULL thay vì bỏ cột | Xác minh SQL và generated/default-value mapping |
| Trigger chạy hai lần | Cả ứng dụng và database cùng sở hữu side effect | Chọn một nguồn tạo audit/event |
| Child bị xóa và insert lại | Aggregate save xử lý owned collection theo chiến lược persistence | Quan sát SQL và đánh giá FK/trigger/child identity |
| List đọc sai thứ tự | Legacy table không có position/key column | Lưu order column hoặc dùng query ORDER BY/read model |
| Thêm FK thất bại | Dữ liệu cũ có orphan references | Thống kê, xử lý dữ liệu có review rồi mới thêm constraint |
| Soft delete bị xóa vật lý | Gọi repository.delete trong schema dùng cờ trạng thái | Dùng update trạng thái theo domain rule |
| Hibernate và JDBC đọc khác nhau | Persistence context/cache JPA stale | Refresh/clear và giới hạn write owner |
| Migration chạy lại CREATE TABLE | Baseline/version history sai | Kiểm tra schema history và baseline trên clone |
| Production khác staging | Schema drift, trigger, quyền hoặc version khác | Dump metadata và kiểm tra parity trước deploy |

## 19. Quy trình tiếp nhận schema an toàn

1. **Khóa phạm vi:** xác định database, schema, bảng và use case sẽ chuyển trước.
2. **Backup và restore thử:** bảo đảm có đường quay lại dữ liệu.
3. **Inventory schema:** lấy DDL, metadata, constraints, indexes, triggers, sequences và migration history.
4. **Baseline dữ liệu:** ghi row count, NULL/duplicate/orphan và tổng nghiệp vụ quan trọng.
5. **Thiết kế aggregate:** phân biệt root, owned child, embedded value và reference.
6. **Viết mapping tường minh:** @Table, @Column, @MappedCollection, @Embedded, @Id và converter.
7. **Xác nhận ID/default:** generated keys, assigned ID, trigger, default và sequence.
8. **Chạy read-only integration test:** xác nhận đọc đúng dữ liệu mà không có DML.
9. **Chạy write test trên clone:** insert/update/delete có kiểm soát và kiểm tra child/trigger/FK.
10. **Viết migration cần thiết:** baseline đúng; dùng expand–migrate–contract cho thay đổi phá vỡ tương thích.
11. **So sánh trước/sau:** row counts, IDs, totals, references, timestamps và audit.
12. **Shadow read/canary:** chuyển một nhóm use case hoặc tenant trước, quan sát query và lỗi.
13. **Mở write path theo từng bước:** chỉ sau khi rollback, concurrency và data verification đã được kiểm chứng.
14. **Loại bỏ writer cũ:** khi mọi consumer đã chuyển và không còn stale cache/dual-write.

### Bảng quyết định nhanh

| Tình huống | Hành động an toàn |
|---|---|
| Schema đã khớp domain | Map trực tiếp; không cần migration chỉ để đổi framework |
| Tên bảng/cột legacy khác convention | Dùng @Table/@Column tường minh |
| ID do database sinh | Xác minh identity/sequence và generated-key behavior |
| ID do hệ thống ngoài cấp | Thiết kế newness detection và test assigned ID |
| Collection có order | Map keyColumn tới cột position hiện hữu hoặc thêm migration được review |
| Có trigger/default | Xác định write owner và kiểm tra SQL NULL/default behavior |
| Có soft delete | Dùng update trạng thái; không gọi physical delete |
| Có orphan FK trong dữ liệu cũ | Phân loại và xử lý có review trước khi thêm constraint |
| Chỉ cần đọc dữ liệu | Bắt đầu bằng quyền read-only và query/projection |
| Cần thay schema | Versioned migration, backup, staging, verify và rollout theo giai đoạn |
| JPA và JDBC cùng runtime | Một write owner cho mỗi aggregate; kiểm soát persistence context/cache |
| Cần bảo đảm không mất dữ liệu | So sánh baseline, rollback test và restore rehearsal |

**Điểm cốt lõi:** tiếp nhận schema có sẵn bằng cách làm cho mapping khớp database hiện hữu trước. Giữ nguyên ID, tên cột, kiểu dữ liệu, default, trigger, FK và các consumer đang phụ thuộc. Chỉ thay đổi schema qua migration có version sau khi đã đo baseline, thử trên bản sao, xác nhận SQL thực tế và so sánh dữ liệu. Bắt đầu bằng read-only, mở write path theo từng bước và chỉ contract cấu trúc cũ khi mọi consumer đã chuyển.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): @Table, @Column, @Id, @MappedCollection, @Embedded, AggregateReference, NamingStrategy và converters.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): insert/update aggregate, generated IDs, newness detection và persistence behavior.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundary cho repository và service layer.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): SQL initialization, Flyway và Liquibase integration.
- [Flyway — Baselines](https://documentation.red-gate.com/flyway/flyway-concepts/baselines): ghi nhận schema/database hiện hữu làm điểm bắt đầu cho migration history.
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): quản lý thay đổi schema bằng migration có version.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, foreign key, unique, check và nullability.
- [PostgreSQL — Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html): identity generation và sequence behavior.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): kiểm thử với database engine thực tế.

