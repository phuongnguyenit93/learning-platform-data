# @CassandraType và điều khiển kiểu CQL tường minh

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Spring Data Cassandra suy luận kiểu CQL từ field Java như thế nào và khi nào cần khai báo `@CassandraType`.
- Dùng đúng ba thuộc tính của annotation: `type`, `typeArguments` và `userTypeName` để diễn đạt kiểu scalar, collection và user-defined type (UDT).
- Phân biệt `UUID` với `timeuuid`, `int` với `bigint`/`varint`, `decimal` với `double`, `date`/`time` với `timestamp` và `duration` với số giây thông thường.
- Phối hợp `@Table`, `@Column`, `@CassandraType`, `@UserDefinedType`, repository, `CassandraTemplate` và CQL mà không tạo metadata trái với schema thực tế.
- Nhận biết giới hạn của annotation: nó không tự sửa cột đã tồn tại, không tự tạo converter/codec, không tự chọn partition key và không biến collection thành bảng quan hệ.
- Kiểm tra schema và thử ghi/đọc để tránh lỗi chuyển kiểu, mất độ chính xác, dữ liệu null, retry và partition phình lớn.

Bài thuộc chương **Kiểu dữ liệu** trong **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng Spring Data Cassandra, gồm entity mapping, repository, `CassandraTemplate` và truy vấn CQL. Chọn đúng kiểu là một phần của **thiết kế bảng theo truy vấn**: kiểu của partition key/clustering column ảnh hưởng đến khả năng bind tham số, so sánh giá trị, phạm vi truy vấn, paging và hiệu năng trên hệ thống phân tán.

## 1. Vì sao cần @CassandraType?

Một bảng Cassandra có schema CQL xác định rõ kiểu từng cột:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    total_amount decimal,
    tags set<text>
);
~~~

Java entity có thể ánh xạ thông qua kiểu thông dụng:

~~~java
@Table("orders_by_id")
public class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("created_at")
    private Instant createdAt;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @Column("tags")
    private Set<String> tags;

    // Constructor, getters, setters...
}
~~~

Trong nhiều trường hợp, `MappingCassandraConverter` của Spring Data Cassandra đã có đủ thông tin để suy luận kiểu. Không cần gắn `@CassandraType` vào mọi field một cách máy móc. Tuy nhiên, cùng một kiểu Java có thể biểu diễn **nhiều kiểu CQL**:

- `String` có thể tương ứng với `text`, `varchar` hoặc `ascii`.
- `UUID` có thể lưu dưới `uuid` hoặc `timeuuid`, nhưng hai kiểu có ràng buộc khác nhau.
- Một collection Java cần biết chính xác kiểu phần tử trong schema CQL, đặc biệt với `Map` hoặc collection có kiểu phức hợp.
- Với `UdtValue`, Java không tự cho biết tên kiểu UDT trong keyspace.
- Với custom converter, kiểu Java miền nghiệp vụ không nhất thiết trùng một kiểu CQL theo quy ước.

**`@CassandraType` cho phép diễn đạt kiểu CQL mong muốn trực tiếp trong metadata mapping**, giảm nhập nhằng khi Spring Data chuyển đổi giữa object Java và giá trị driver Cassandra.

### 1.1. Vị trí của annotation trong luồng dữ liệu

~~~mermaid
flowchart LR
    A[Entity Java] --> B[MappingCassandraConverter]
    C["@CassandraType / @Column"] --> B
    B --> D[Java Driver codec / CQL statement]
    D --> E[Schema bảng Cassandra]
    E --> D
    D --> B
    B --> F[Entity được đọc]
~~~

Vai trò từng lớp:

| Thành phần | Trách nhiệm |
| --- | --- |
| Kiểu Java của field | Dạng dữ liệu mà ứng dụng thao tác: `UUID`, `Instant`, `BigDecimal`, `Map`... |
| `@CassandraType` | Gợi ý/khai báo kiểu Cassandra mà mapping cần sử dụng |
| `MappingCassandraConverter` và custom conversions | Chuyển giữa entity, kiểu miền nghiệp vụ và dạng dữ liệu của driver |
| Codec của Java Driver | Mã hóa/giải mã kiểu Java hỗ trợ sang binary protocol theo kiểu CQL |
| Schema CQL thật | Quy định cột tồn tại, tên, kiểu, partition key, clustering key và các ràng buộc |

**Đừng nhầm annotation với migration:** sửa `@CassandraType(type = Name.BIGINT)` không đổi một cột Cassandra đang có kiểu `int` thành `bigint`. Khi không khớp, câu lệnh có thể thất bại ở bước mapping, bind, decode hoặc thực thi trên server. Việc thay schema/dữ liệu phải thực hiện qua quy trình riêng.

## 2. Cú pháp chính xác của @CassandraType

Import trong Spring Data Cassandra:

~~~java
import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.CassandraType.Name;
~~~

Ba thuộc tính của annotation:

~~~java
@CassandraType(
    type = Name.MAP,
    typeArguments = {Name.TEXT, Name.BOOLEAN},
    userTypeName = ""
)
private Map<String, Boolean> flags;
~~~

| Thuộc tính | Kiểu | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `type` | `CassandraType.Name` | Có | Kiểu CQL chính, ví dụ `TEXT`, `TIMEUUID`, `MAP`, `UDT` |
| `typeArguments` | `CassandraType.Name[]` | Không | Một phần tử cho `list`/`set`; hai phần tử cho `map`, lần lượt key và value |
| `userTypeName` | `String` | Không | Tên user-defined type khi kiểu sử dụng `UDT` mà không thể suy được từ class có `@UserDefinedType` |

Annotation áp dụng được cho field và những vị trí khác do API hỗ trợ, gồm tham số của query method. Ở bài này, ta tập trung vào field entity vì đây là trường hợp phổ biến nhất của `Spring Data Cassandra`.

Với collection, cần nhớ chính xác số `typeArguments`:

~~~java
@CassandraType(
    type = Name.SET,
    typeArguments = Name.TEXT
)
private Set<String> tags;

@CassandraType(
    type = Name.LIST,
    typeArguments = Name.UUID
)
private List<UUID> relatedIds;

@CassandraType(
    type = Name.MAP,
    typeArguments = {Name.TEXT, Name.BOOLEAN}
)
private Map<String, Boolean> settings;
~~~

| Java field | CQL mong đợi | Ý nghĩa arguments |
| --- | --- | --- |
| `Set<String>` | `set<text>` | Một argument: `TEXT` |
| `List<UUID>` | `list<uuid>` | Một argument: `UUID` |
| `Map<String, Boolean>` | `map<text, boolean>` | Hai arguments: key `TEXT`, value `BOOLEAN` |
| `Map<UUID, BigDecimal>` | `map<uuid, decimal>` | Hai arguments: `UUID`, `DECIMAL` |

`typeArguments` không được hiểu là kích thước collection, số hàng/trang hay thứ tự cột khóa. Nó chỉ nói kiểu phần tử/khóa/giá trị của collection CQL. Nếu field **không** phải collection/map, `typeArguments` không có ý nghĩa.

### 2.1. Name là tên kiểu CQL, không phải class Java

Các hằng thường gặp:

~~~java
Name.TEXT
Name.ASCII
Name.INT
Name.BIGINT
Name.VARINT
Name.DECIMAL
Name.TIMESTAMP
Name.DATE
Name.TIME
Name.UUID
Name.TIMEUUID
Name.LIST
Name.SET
Name.MAP
Name.UDT
Name.TUPLE
~~~

Các hằng trên là giá trị `CassandraType.Name`, không phải tên bảng, Java class hay chuỗi truyền vào annotation.

Ví dụ sai cú pháp:

~~~java
// SAI: type cần enum Name, không phải chuỗi.
@CassandraType(type = "timeuuid")
private UUID eventId;
~~~

Ví dụ đúng:

~~~java
@CassandraType(type = Name.TIMEUUID)
private UUID eventId;
~~~

Việc enum `Name` của Spring Data có hằng nào phải đối chiếu theo **phiên bản Spring Data Cassandra** đang dùng. Chẳng hạn hỗ trợ CQL vector xuất hiện trong các phiên bản Cassandra/Spring Data mới và có yêu cầu mapping bổ sung; không suy rằng một phiên bản cũ hỗ trợ chỉ vì server mới có kiểu đó.

## 3. Các kiểu scalar và sự khác nhau dễ gây lỗi

Trong những trường hợp quy ước đã rõ và schema khớp, không bắt buộc gắn annotation; bảng sau cho biết các cặp kiểu phổ biến:

| Kiểu CQL | Kiểu Java thường dùng | Ý nghĩa/ràng buộc |
| --- | --- | --- |
| `text` / `varchar` | `String` | Chuỗi Unicode UTF-8 |
| `ascii` | `String` | Chỉ ký tự ASCII; không dùng cho văn bản tiếng Việt |
| `boolean` | `Boolean` / `boolean` | Giá trị đúng/sai |
| `tinyint` | `Byte` | Số nguyên 8-bit |
| `smallint` | `Short` | Số nguyên 16-bit |
| `int` | `Integer` | Số nguyên 32-bit |
| `bigint` | `Long` | Số nguyên 64-bit |
| `varint` | `BigInteger` | Số nguyên độ chính xác tùy ý |
| `float` | `Float` | Số thực IEEE-754 32-bit |
| `double` | `Double` | Số thực IEEE-754 64-bit |
| `decimal` | `BigDecimal` | Số thập phân độ chính xác tùy ý, phù hợp tiền khi chọn scale đúng |
| `uuid` | `UUID` | UUID thường, có thể là nhiều version |
| `timeuuid` | `UUID` | Bắt buộc UUID version 1 |
| `date` | `LocalDate` | Chỉ ngày, không có giờ/múi giờ |
| `time` | `LocalTime` | Giờ trong ngày, độ chính xác nano giây |
| `timestamp` | `Instant` | Thời điểm tuyệt đối, Cassandra lưu theo mili giây |
| `inet` | `InetAddress` | IPv4/IPv6 |
| `blob` | `ByteBuffer` | Dữ liệu nhị phân tùy ý |
| `duration` | `CqlDuration` của Java Driver | Có riêng months/days/nanoseconds; khác thời lượng cố định |
| `counter` | Giá trị số 64-bit khi đọc | Chỉ cập nhật bằng phép cộng/trừ counter; không lưu như cột `bigint` thường |

Bảng biểu diễn cách ánh xạ điển hình với Cassandra Java Driver 4.x; các converter được đăng ký trong dự án có thể thay đổi kiểu Java ở tầng domain. Không chọn kiểu chỉ theo tên giống nhau: **ý nghĩa dữ liệu và phạm vi giá trị mới quyết định**.

### 3.1. TEXT, VARCHAR và ASCII

~~~sql
CREATE TABLE customer_profiles (
    customer_id uuid PRIMARY KEY,
    full_name text,
    country_code ascii
);
~~~

~~~java
@Table("customer_profiles")
public class CustomerProfile {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("full_name")
    @CassandraType(type = Name.TEXT)
    private String fullName;

    @Column("country_code")
    @CassandraType(type = Name.ASCII)
    private String countryCode;

    // Constructor, getters, setters...
}
~~~

Chọn `ascii` cho mã quốc gia như `"VN"` có thể hợp lý nếu data contract chỉ cho phép ký tự ASCII. Không dùng `ascii` cho họ tên hay nội dung tiếng Việt có dấu: ví dụ `"Nguyễn"` cần `text`/`varchar`. `varchar` và `text` trong Cassandra đều biểu diễn chuỗi UTF-8, nên nhiều khi không cần ép riêng hai kiểu.

Annotation không thay thế validation dữ liệu. Nếu API nhận `countryCode = "Việt Nam"`, vẫn cần validate trước khi ghi để trả lỗi nghiệp vụ dễ hiểu; đừng trông chờ driver báo lỗi encoding để làm bước kiểm tra đầu vào.

### 3.2. INT, BIGINT, VARINT và DECIMAL

~~~sql
CREATE TABLE order_amounts_by_id (
    order_id uuid PRIMARY KEY,
    item_count int,
    total_amount decimal,
    reward_points varint
);
~~~

~~~java
@CassandraType(type = Name.INT)
private Integer itemCount;

@CassandraType(type = Name.DECIMAL)
private BigDecimal totalAmount;

@CassandraType(type = Name.VARINT)
private BigInteger rewardPoints;
~~~

Những khác biệt thực tế:

- `int` và `bigint` đều là **số nguyên kích thước cố định**, nhưng giới hạn 32-bit và 64-bit khác nhau.
- `varint` là số nguyên có độ dài tùy ý, thích hợp khi miền số thực sự vượt giới hạn `long`; nếu không, kiểu này có thể gây chi phí mã hóa/lưu trữ không cần thiết.
- `decimal` lưu giá trị thập phân chính xác hơn `float`/`double` cho mục đích tiền tệ. Tránh dùng `double` làm số tiền rồi “chữa” bằng annotation `DECIMAL` trên field `Double`: cần chuyển Java sang `BigDecimal` và xem lại hợp đồng API.
- `BigDecimal` không tự áp dụng quy tắc làm tròn/scale nghiệp vụ. Với tiền, xác định đơn vị và cách làm tròn ở domain, ví dụ hai chữ số thập phân, thay vì đặt kỳ vọng Cassandra làm công việc đó.

Ví dụ ranh giới: lưu 4.294.967.296 vào cột `int` là vượt giới hạn 32-bit. Nếu business cần miền số này, sửa schema sang `bigint`/`varint` theo kế hoạch migration, và cập nhật kiểu Java/converter tương ứng. Chỉ đổi annotation không khắc phục.

### 3.3. UUID và TIMEUUID

`UUID` trong Java đại diện cả hai kiểu CQL, nhưng `timeuuid` có yêu cầu UUID version 1:

~~~sql
CREATE TABLE events_by_user (
    user_id uuid,
    event_id timeuuid,
    description text,
    PRIMARY KEY ((user_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

~~~java
@PrimaryKeyColumn(
    name = "user_id",
    ordinal = 0,
    type = PrimaryKeyType.PARTITIONED
)
private UUID userId;

@PrimaryKeyColumn(
    name = "event_id",
    ordinal = 1,
    type = PrimaryKeyType.CLUSTERED,
    ordering = Ordering.DESCENDING
)
@CassandraType(type = Name.TIMEUUID)
private UUID eventId;
~~~

Java Driver 4.x có tiện ích sinh time-based UUID:

~~~java
import com.datastax.oss.driver.api.core.uuid.Uuids;

UUID eventId = Uuids.timeBased();  // UUID version 1
~~~

Cần đảm bảo `eventId.version() == 1` cho giá trị ghi vào CQL `timeuuid`. `UUID.randomUUID()` thường sinh UUID version 4 và không hợp lệ cho `timeuuid`. Một kiểu Java `UUID` vẫn không đủ để biểu đạt ràng buộc này nếu thiếu annotation/schema validation.

`timeuuid` có thứ tự dựa trên thành phần thời gian, hữu ích khi clustering theo sự kiện. Tuy nhiên, ứng dụng vẫn cần cân nhắc trùng thời gian, thời gian hệ thống không đồng bộ, phân bố tải và kích thước partition. Không dùng một partition vô hạn chỉ vì timeuuid tự mang timestamp.

### 3.4. DATE, TIME, TIMESTAMP và DURATION

Các kiểu này không thể hoán đổi chỉ vì cùng liên quan “thời gian”:

~~~sql
CREATE TABLE appointments_by_id (
    appointment_id uuid PRIMARY KEY,
    appointment_date date,
    appointment_time time,
    created_at timestamp,
    reminder_delay duration
);
~~~

~~~java
@CassandraType(type = Name.DATE)
private LocalDate appointmentDate;

@CassandraType(type = Name.TIME)
private LocalTime appointmentTime;

@CassandraType(type = Name.TIMESTAMP)
private Instant createdAt;

@CassandraType(type = Name.DURATION)
private CqlDuration reminderDelay;
~~~

Import `CqlDuration` từ `com.datastax.oss.driver.api.core.data.CqlDuration` khi dùng Java Driver 4.x. Ví dụ:

~~~java
CqlDuration reminderDelay =
    CqlDuration.newInstance(0, 1, 0);  // 0 tháng, 1 ngày, 0 nano giây
~~~

`duration` trong CQL mô tả **số tháng, số ngày và số nano giây**. `1mo` không phải hằng số 30 ngày, và `1d` không luôn tương đương 24 giờ theo ngữ nghĩa thời gian lịch. Không mặc định ánh xạ thẳng sang `java.time.Duration` (chỉ biểu diễn thời lượng theo giây/nano giây) mà không có quy tắc chuyển đổi rõ ràng.

Lưu ý:

- `date` không chứa múi giờ hay giờ trong ngày.
- `time` không chứa ngày/múi giờ.
- `timestamp` biểu diễn thời điểm, được Cassandra lưu theo **mili giây**; Java `Instant` có thể có nano giây và bị mất phần nhỏ hơn một mili giây khi lưu/đọc.
- `duration` không được dùng trong primary key CQL do không thể có thứ tự tổng quát độc lập với ngữ cảnh ngày tháng.

Nếu hệ thống cần hiển thị “09:00 giờ Việt Nam”, phải xác định múi giờ ở tầng ứng dụng/contract. Lưu mỗi `LocalTime` không đủ để suy ra một thời điểm toàn cầu.

### 3.5. BLOB và INET

~~~java
@CassandraType(type = Name.BLOB)
private ByteBuffer checksumBytes;

@CassandraType(type = Name.INET)
private InetAddress sourceIp;
~~~

`blob` chứa byte thô; không tự hiểu nội dung là JSON, ảnh hay chuỗi UTF-8. Khi cần dữ liệu lớn như ảnh/tệp, cân nhắc object storage và lưu metadata/tham chiếu trong Cassandra thay vì đưa blob lớn vào row làm tăng payload, compaction và chi phí truyền dữ liệu.

`inet` lưu địa chỉ IPv4/IPv6. Nếu domain dùng chuỗi `"192.0.2.5"`, phải đảm bảo có cách parse/convert đúng kiểu; đổi annotation cho field `String` thành `INET` không bảo đảm Spring Data/driver tự sinh converter mong muốn.

## 4. Collection: LIST, SET và MAP với typeArguments

Cassandra hỗ trợ ba kiểu collection chính, phù hợp **nhóm dữ liệu nhỏ, có giới hạn** thuộc cùng một row/partition. Đây không phải lựa chọn tốt để lưu hàng triệu event của một khách hàng.

~~~sql
CREATE TABLE notification_settings_by_user (
    user_id uuid PRIMARY KEY,
    channels set<text>,
    recent_device_ids list<uuid>,
    feature_flags map<text, boolean>
);
~~~

Ánh xạ tường minh:

~~~java
@Table("notification_settings_by_user")
public class NotificationSettings {

    @PrimaryKey("user_id")
    private UUID userId;

    @Column("channels")
    @CassandraType(
        type = Name.SET,
        typeArguments = Name.TEXT
    )
    private Set<String> channels;

    @Column("recent_device_ids")
    @CassandraType(
        type = Name.LIST,
        typeArguments = Name.UUID
    )
    private List<UUID> recentDeviceIds;

    @Column("feature_flags")
    @CassandraType(
        type = Name.MAP,
        typeArguments = {Name.TEXT, Name.BOOLEAN}
    )
    private Map<String, Boolean> featureFlags;

    // Constructor, getters, setters...
}
~~~

Trong đoạn trên, `Name` là `CassandraType.Name`. Cần có import `UUID`, `Set`, `List`, `Map` và các annotation Spring Data tương ứng.

### 4.1. Chọn collection theo cách dùng

| CQL | Đặc trưng | Tình huống phù hợp | Sai lầm cần tránh |
| --- | --- | --- | --- |
| `set<text>` | Tập giá trị không trùng, không mang thứ tự chèn | Một danh sách tag nhỏ | Dùng như log sự kiện có thứ tự |
| `list<uuid>` | Danh sách có thứ tự, phần tử có thể trùng | Một số ID liên quan có giới hạn | Dùng như lịch sử vô hạn, mutate theo index liên tục |
| `map<text, boolean>` | Key duy nhất, tra cứu theo key trong row | Cờ cấu hình nhỏ | Thay thế bảng tra cứu quy mô lớn |

Các collection không phải mảng các row độc lập được Cassandra phân trang tự động như một truy vấn hàng theo clustering key. Đọc một row chứa collection quá lớn có thể trả payload lớn, gây áp lực bộ nhớ và timeout. Một số cập nhật `list` còn có tính chất **read-before-write** và khó retry an toàn nếu thao tác không idempotent.

### 4.2. Kiểm tra đúng thứ tự typeArguments của MAP

Ví dụ này **sai** với schema `map<text, boolean>`:

~~~java
// SAI: đối số bị đảo, biến schema thành map<boolean, text>.
@CassandraType(
    type = Name.MAP,
    typeArguments = {Name.BOOLEAN, Name.TEXT}
)
private Map<String, Boolean> featureFlags;
~~~

Thứ tự đúng là **key trước, value sau**:

~~~java
@CassandraType(
    type = Name.MAP,
    typeArguments = {Name.TEXT, Name.BOOLEAN}
)
private Map<String, Boolean> featureFlags;
~~~

Sai kiểu phần tử có thể được phát hiện trong lúc tạo schema, sinh statement, bind hoặc decode. Nếu bảng đã tồn tại, lỗi không được khắc phục bằng việc đổi một phía; phải thống nhất giữa CQL, annotation và kiểu Java.

### 4.3. Collection lồng nhau và FROZEN

Khi cần collection lồng nhau hoặc collection chứa UDT, CQL có những quy tắc về `frozen<...>`. Ví dụ:

~~~sql
CREATE TABLE user_notification_snapshots (
    user_id uuid PRIMARY KEY,
    channel_groups map<text, frozen<set<text>>>
);
~~~

`frozen` là khái niệm của **schema CQL**: với giá trị frozen, Cassandra xử lý giá trị phức hợp như một khối khi cập nhật, thay vì cập nhật riêng các phần tử bên trong theo một số cơ chế áp dụng cho kiểu non-frozen.

`@CassandraType` **không phải cú pháp thay thế cho `frozen<...>` trong schema**. Với kiểu lồng nhau, cần đối chiếu khả năng mapping, codec và CQL của phiên bản Spring Data/driver. `typeArguments` trong annotation chỉ nhận các phần tử `Name` đơn giản; không coi nó là ngôn ngữ mô tả đệ quy toàn bộ `map<text, frozen<set<text>>>`. Nếu mapping mặc định không xử lý rõ ràng, hãy dùng kiểu/codec/UDT phù hợp và kiểm thử round-trip trên Cassandra.

## 5. User-Defined Type: @UserDefinedType và userTypeName

UDT cho phép gom những field có cấu trúc lại thành một giá trị CQL. Ví dụ địa chỉ giao hàng:

~~~sql
CREATE TYPE shipping_address (
    street text,
    city text,
    postal_code text
);

CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    shipping_address frozen<shipping_address>
);
~~~

Trong ví dụ, `shipping_address` là tên type do schema khai báo; field cùng tên trong bảng dùng `frozen<shipping_address>`. Dùng frozen giúp thao tác giá trị như một khối, phù hợp với snapshot địa chỉ ít cập nhật từng thuộc tính.

### 5.1. Ánh xạ UDT thành domain class

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("shipping_address")
public class ShippingAddress {

    @Column("street")
    private String street;

    @Column("city")
    private String city;

    @Column("postal_code")
    private String postalCode;

    public ShippingAddress() {
    }

    // Getters, setters hoặc constructor mapping phù hợp...
}
~~~

Sử dụng trong entity:

~~~java
@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("status")
    private String status;

    @Column("shipping_address")
    @CassandraType(type = Name.UDT)
    private ShippingAddress shippingAddress;

    // Constructor, getters, setters...
}
~~~

Vì `ShippingAddress` đã có `@UserDefinedType("shipping_address")`, Spring Data có thể suy được tên UDT khi mapping. Tùy cấu hình ứng dụng, hệ thống cần `UserTypeResolver`/metadata driver phù hợp và keyspace chứa UDT đó; Spring Boot/Spring Data thông thường cung cấp cơ chế cấu hình tương ứng.

Nếu không có annotation `@UserDefinedType` hoặc dùng `UdtValue` từ driver, có thể cần xác định tên type tường minh:

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;

@Column("shipping_address")
@CassandraType(
    type = Name.UDT,
    userTypeName = "shipping_address"
)
private UdtValue rawShippingAddress;
~~~

`userTypeName` định danh **tên type CQL**, không phải tên class Java, bảng hay field. Không dùng `userTypeName` cho `text` hoặc `int` và mong nó đổi schema.

### 5.2. UDT trong collection

Giả sử một row chứa vài địa chỉ đã xác nhận, schema có thể dùng:

~~~sql
CREATE TABLE addresses_by_user (
    user_id uuid PRIMARY KEY,
    addresses list<frozen<shipping_address>>
);
~~~

Khi annotation cần làm rõ phần tử UDT:

~~~java
@CassandraType(
    type = Name.LIST,
    typeArguments = Name.UDT,
    userTypeName = "shipping_address"
)
private List<ShippingAddress> addresses;
~~~

Đoạn này diễn đạt ý định kiểu UDT của collection. Trong Spring Data, `userTypeName` không bắt buộc nếu class phần tử đã ánh xạ bằng `@UserDefinedType` và metadata/UDT resolver đã đủ thông tin. Cần kiểm tra tương thích với phiên bản driver và schema frozen thực tế.

**Cẩn trọng với kích thước:** UDT/collection là lựa chọn tốt cho nhóm dữ liệu nhỏ có vòng đời cùng row; nếu người dùng có hàng nghìn địa chỉ, đơn hàng hoặc lịch sử cập nhật, hãy thiết kế bảng riêng theo truy vấn thay vì một `list<frozen<udt>>` tăng liên tục.

### 5.3. Schema UDT và sự phát triển dữ liệu

Thay đổi UDT có thể ảnh hưởng tới mọi bảng/collection dùng type đó. Đừng tự giả định sửa class Java là đủ để thêm field vào UDT CQL. Cần migration schema trước hoặc đồng thời theo kế hoạch, kiểm tra đọc dữ liệu cũ, ghi dữ liệu mới và tương thích giữa các version ứng dụng.

Đối với giá trị `frozen<shipping_address>`, nếu muốn thay một trường như `city`, thông thường phải ghi lại giá trị UDT theo ngữ nghĩa cập nhật whole value. Không suy ra rằng setter Java chỉ làm server patch đúng một field nếu schema frozen.

## 6. Tuple và kiểu phức hợp khác

CQL còn có `tuple<...>`, trong khi Spring Data Cassandra có mô hình ánh xạ riêng bằng `@Tuple` và `@Element`. Ví dụ CQL:

~~~sql
CREATE TABLE location_snapshots (
    location_id uuid PRIMARY KEY,
    point tuple<text, double, double>
);
~~~

Một class tuple có thể được ánh xạ như sau:

~~~java
import org.springframework.data.cassandra.core.mapping.Element;
import org.springframework.data.cassandra.core.mapping.Tuple;

@Tuple
public class LocationPoint {

    @Element(0)
    @CassandraType(type = Name.TEXT)
    private String label;

    @Element(1)
    private Double latitude;

    @Element(2)
    private Double longitude;

    // Constructor, getters, setters...
}
~~~

Entity có field `LocationPoint point` tương ứng với cột `point`. Với tuple, `@Element(0)`, `@Element(1)`, `@Element(2)` mô tả **vị trí** trong tuple CQL, khác với `ordinal` của khóa chính. Thứ tự phần tử tuple là phần của kiểu, nên khi thay đổi nó phải xem xét tương thích dữ liệu và codec.

CQL tuple có tính chất frozen: khi đổi một thành phần, thao tác thường ghi lại tuple. Annotation `@CassandraType(type = Name.TUPLE)` một mình không diễn tả rõ mọi phần tử; Spring Data hỗ trợ `@Tuple`/`@Element` để ánh xạ đối tượng đúng cấu trúc.

Với CQL `vector<...>` ở các phiên bản mới, không thể giả định gắn `@CassandraType(type = Name.VECTOR)` là đủ. Spring Data mới có cơ chế bổ sung như `@VectorType`, đồng thời cần Java Driver và server hỗ trợ cùng kiểu/phạm vi phần tử. Xác minh compatibility matrix trước khi dùng.

## 7. @CassandraType không thay thế custom converters và codecs

Giả sử ứng dụng sử dụng value object riêng:

~~~java
public record OrderCode(String value) {
}
~~~

CQL bảng lưu giá trị này dưới `text`:

~~~sql
CREATE TABLE orders_by_code (
    order_code text PRIMARY KEY,
    status text
);
~~~

Entity có thể khai báo:

~~~java
@Table("orders_by_code")
public class OrderByCode {

    @PrimaryKey("order_code")
    @CassandraType(type = Name.TEXT)
    private OrderCode orderCode;

    @Column("status")
    private String status;

    // Constructor, getters, setters...
}
~~~

Tuy nhiên, Java Driver **không tự biết** cách mã hóa class `OrderCode` theo codec `text`; annotation chỉ nêu kiểu CQL mục tiêu. Cần custom conversions giữa `OrderCode` và `String` nếu Spring Data không có converter phù hợp.

Ví dụ converter ở tầng Spring Data:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderCodeWriteConverter
        implements Converter<OrderCode, String> {

    @Override
    public String convert(OrderCode source) {
        return source.value();
    }
}

@ReadingConverter
public class OrderCodeReadConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        return new OrderCode(source);
    }
}
~~~

Hai converter cần được **đăng ký** vào `CassandraCustomConversions` hoặc cơ chế cấu hình conversions tương ứng của phiên bản Spring Data Cassandra. Chỉ tạo class/đánh dấu annotation converter không bảo đảm Spring tự quét đăng ký chúng.

Một cách tổng quát:

~~~text
OrderCode  --writing converter--> String
   |                                 |
   |                          Java Driver text codec
   |                                 |
   +<--reading converter---  CQL text
~~~

Phân biệt:

| Cơ chế | Xử lý |
| --- | --- |
| `@CassandraType` | Khai báo Cassandra type metadata cho property/parameter |
| Spring `Converter` / `CassandraCustomConversions` | Chuyển object domain sang kiểu dữ liệu có thể lưu/đọc |
| Driver `TypeCodec` | Chuyển kiểu Java driver hiểu sang bytes cho kiểu CQL |
| Migration CQL | Tạo/sửa schema vật lý trong cluster |

Nếu dùng custom Java codec trực tiếp với `CqlSession`, phải đảm bảo codec được đăng ký với driver và không xung đột với đường chuyển đổi của Spring Data. Tránh gắn converter hai chiều chồng chéo khiến dữ liệu bị mã hóa hai lần hoặc chuyển đổi mất thông tin.

### 7.1. Trường hợp String -> UUID cần quyết định nghiệp vụ

Ví dụ API nhận order ID dưới dạng chuỗi `"2b0a..."`, nhưng CQL yêu cầu `uuid`. Có hai cách thường dùng:

- Chuyển chuỗi thành `UUID` ở biên ứng dụng và để entity dùng `UUID` đúng kiểu CQL.
- Nếu domain thực sự cần `OrderId` value object, tạo converter sang `UUID` và đọc ngược; vẫn kiểm tra định dạng đầu vào.

Đặt `@CassandraType(type = Name.UUID)` lên một field `String` mà không có converter không phải cách chắc chắn để tự parse mọi chuỗi. Với partition key, lỗi chuyển đổi còn có thể khiến truy vấn sai partition hoặc fail trước khi gửi request.

## 8. Viết một entity thực tế: schema và mapping đi cùng nhau

Xét một ứng dụng bán hàng cần lưu đơn theo ID và hiển thị các thuộc tính nhỏ của đơn:

~~~sql
CREATE TYPE shipping_address (
    street text,
    city text,
    postal_code text
);

CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    created_at timestamp,
    total_amount decimal,
    status text,
    labels set<text>,
    settings map<text, boolean>,
    shipping_address frozen<shipping_address>
);
~~~

Java entity minh họa:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.CassandraType.Name;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    @CassandraType(type = Name.UUID)
    private UUID orderId;

    @Column("created_at")
    @CassandraType(type = Name.TIMESTAMP)
    private Instant createdAt;

    @Column("total_amount")
    @CassandraType(type = Name.DECIMAL)
    private BigDecimal totalAmount;

    @Column("status")
    @CassandraType(type = Name.TEXT)
    private String status;

    @Column("labels")
    @CassandraType(
        type = Name.SET,
        typeArguments = Name.TEXT
    )
    private Set<String> labels;

    @Column("settings")
    @CassandraType(
        type = Name.MAP,
        typeArguments = {Name.TEXT, Name.BOOLEAN}
    )
    private Map<String, Boolean> settings;

    @Column("shipping_address")
    @CassandraType(type = Name.UDT)
    private ShippingAddress shippingAddress;

    public OrderById() {
    }

    // Constructor, getters và setters cho các trường...
}
~~~

Trong ứng dụng, các trường đơn giản `UUID`, `Instant`, `BigDecimal` thường **không cần** ép `@CassandraType` nếu mapping convention đã khớp; ví dụ ghi đầy đủ để người đọc thấy tương ứng với CQL. `ShippingAddress` phải là class được ánh xạ bằng `@UserDefinedType("shipping_address")` như phần 5, hoặc dùng con đường `UdtValue`/converter phù hợp.

Đảm bảo schema được tạo/migrate trước khi lưu entity. Ví dụ này không có quan hệ `@OneToMany`, khóa ngoại hoặc `JOIN` như JPA. Nếu một màn hình cần danh sách đơn của khách hàng theo thời gian, có thể cần thêm bảng theo `customer_id` và clustering key, và ứng dụng phải đồng bộ dữ liệu giữa các bảng.

### 8.1. Repository làm việc theo schema thật

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Lưu/đọc:

~~~java
repository.save(order);

Optional<OrderById> loaded = repository.findById(orderId);
~~~

Repository dựa trên metadata entity để bind/read CQL values. Nó không “sửa giùm” kiểu cột thật trên cluster. Nếu database lưu `total_amount double` mà Java field khai `BigDecimal`/`DECIMAL`, cần sửa sự không nhất quán schema và migration; đừng giả định repository tự đổi kiểu khi đọc.

Với dữ liệu cần cập nhật có điều kiện hoặc truy vấn đặc thù, có thể dùng `CassandraTemplate`/`CqlSession`; quy tắc kiểu dữ liệu vẫn y hệt.

### 8.2. CassandraTemplate và truy vấn theo partition key

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// cassandraTemplate đã được inject qua constructor.
Query query = Query.query(
    Criteria.where("order_id").is(orderId)
);

OrderById result =
    cassandraTemplate.selectOne(query, OrderById.class);
~~~

`orderId` ở đây nên là `UUID`, phù hợp với CQL `order_id uuid PRIMARY KEY`. Mapping/codec xử lý kiểu dữ liệu, nhưng khả năng truy vấn hiệu quả đến từ việc dùng đúng **partition key**, không phải từ `@CassandraType`. CQL query tùy ý theo `status` trên bảng này không tự trở nên hiệu quả khi ta thêm annotation cho field `status`.

## 9. Điều khiển type cho tham số truy vấn và ranh giới mapping

`@CassandraType` hỗ trợ khai báo trên **tham số của query method** theo API của Spring Data Cassandra, hữu ích khi Java type có thể bị suy luận nhập nhằng và query dùng tham số có CQL type rõ ràng.

Ví dụ minh họa:

~~~java
public interface EventsByUserRepository
        extends CassandraRepository<EventByUser, EventKey> {

    @Query(
        "SELECT * FROM events_by_user " +
        "WHERE user_id = ?0 AND event_id = ?1"
    )
    Optional<EventByUser> findOne(
        UUID userId,
        @CassandraType(type = Name.TIMEUUID) UUID eventId
    );
}
~~~

Ví dụ giả định class `EventByUser`/`EventKey` đã được định nghĩa với partition key `user_id` và clustering key `event_id timeuuid`. Mục đích là minh họa metadata của parameter; type thực tế phải phù hợp schema và giá trị UUID version 1.

Không nên xem annotation trên parameter là giải pháp thay thế việc khai báo sai kiểu field trên entity hoặc schema đã tồn tại. Với query được xây dựng theo cách riêng, đường conversion/binding cần được kiểm tra bằng integration test.

## 10. Kiểm tra schema CQL và xác minh round-trip

### 10.1. Kiểm tra kiểu thực tế ở Cassandra

Trong `cqlsh`:

~~~sql
DESCRIBE TABLE order_service.orders_by_id;
~~~

`DESCRIBE` là lệnh tiện ích của `cqlsh`. Truy vấn metadata schema bằng CQL:

~~~sql
SELECT column_name, type, kind, position
FROM system_schema.columns
WHERE keyspace_name = 'order_service'
  AND table_name = 'orders_by_id';
~~~

`type` cho thấy kiểu cột thật như `uuid`, `decimal`, `set<text>`, `map<text, boolean>` hoặc `frozen<shipping_address>`. `kind` cho biết vị trí/loại cột trong primary key hay cột thường. Nếu CQL khác với annotation, cần xác định bên nào là nguồn schema dự kiến và thực hiện migration/điều chỉnh mapping có kế hoạch.

Cần so sánh ít nhất:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| CQL `total_amount decimal` | Java `BigDecimal`, nếu ép thì `Name.DECIMAL` |
| CQL `labels set<text>` | Java `Set<String>`, `Name.SET` + `Name.TEXT` |
| CQL `settings map<text, boolean>` | Java `Map<String, Boolean>`, đúng thứ tự `TEXT, BOOLEAN` |
| CQL `shipping_address frozen<shipping_address>` | Class có `@UserDefinedType` hoặc `UdtValue` với tên UDT đúng |
| CQL `event_id timeuuid` | Java `UUID` version 1 và `Name.TIMEUUID` khi cần chỉ định rõ |
| Partition key `order_id uuid` | Query/binding có `UUID orderId` và điều kiện partition hợp lệ |

### 10.2. Kiểm tra round-trip thay vì chỉ startup

Một ca kiểm tra có giá trị cần:

1. Tạo schema CQL trong test Cassandra đúng phiên bản mục tiêu.
2. Khởi tạo object Java có `BigDecimal`, `Instant`, `Set`, `Map` và UDT.
3. Ghi bằng repository/template, đọc lại bằng `findById`.
4. So sánh **giá trị nghiệp vụ** sau khi chuyển đổi: số tiền, phần nano giây, timestamp, UUID version, collection và UDT.
5. Thử giá trị lỗi có chủ đích: UUID v4 vào `timeuuid`, String chứa dấu vào `ascii`, giá trị vượt miền `int`, map có kiểu value sai.
6. Kiểm tra CQL schema thực sự khớp khi Spring Boot không bật tự động tạo schema.

Với `Instant`, test phải chấp nhận hoặc chủ động làm tròn xuống mili giây nếu quy ước lưu trữ là `timestamp`; đừng so sánh nano giây khi database chỉ lưu mili giây.

Với `BigDecimal`, phân biệt **giá trị** và **scale** theo nhu cầu. Ví dụ `new BigDecimal("10.0")` và `new BigDecimal("10.00")` có thể tương đương về số học nhưng `equals()` trong Java xem xét scale; hợp đồng domain nên quy định làm tròn/scale rõ ràng.

### 10.3. Phân biệt các nhóm lỗi

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không bind được `String` vào cột `uuid` | Java type không tương thích/thiếu converter | Chuyển sang `UUID` hoặc đăng ký converter chuẩn |
| Lỗi khi lưu UUID v4 vào `timeuuid` | `timeuuid` yêu cầu UUID version 1 | Sinh giá trị version 1, xác minh trước khi ghi |
| Lỗi ký tự tiếng Việt ở `ascii` | Kiểu CQL không cho Unicode | Dùng `text`/`varchar` cho văn bản đa ngôn ngữ |
| Đọc `decimal` vào `Double` sai/thiếu chính xác | Java type không phù hợp | Dùng `BigDecimal` và chính sách scale |
| `Map<String, Boolean>` không đọc được | CQL/typeArguments khác kiểu của field | Đối chiếu `map<text, boolean>` và mapping |
| Không resolve được UDT | Sai tên UDT, keyspace, thiếu resolver/metadata hoặc converter | Kiểm tra `@UserDefinedType`, `userTypeName` và schema |
| Đổi annotation mà lỗi vẫn còn | Schema vật lý chưa được migrate | Kiểm tra `system_schema.columns` và migration |
| Đọc timestamp lệch giờ | Nhầm `timestamp` với giờ địa phương/format hiển thị | Dùng `Instant` cho thời điểm và chuyển múi giờ ở UI |
| Collection gây timeout/memory tăng | Collection phình lớn; row payload lớn | Chia thành bảng với clustering key/partition phù hợp |
| Retry thao tác counter tạo giá trị sai | Counter update không idempotent | Thiết kế retry/hợp đồng nhất quán riêng |

## 11. Các ràng buộc quan trọng của Cassandra không thể sửa bằng annotation

### 11.1. COUNTER không phải BIGINT thông thường

~~~sql
CREATE TABLE page_views_by_page (
    page_id uuid PRIMARY KEY,
    views counter
);
~~~

Tăng bằng CQL:

~~~sql
UPDATE page_views_by_page
SET views = views + 1
WHERE page_id = ?;
~~~

Không được xử lý counter như cột `bigint` rồi gọi `repository.save()` để đặt giá trị tuyệt đối theo cách thông thường. Counter có quy tắc riêng: không đặt trực tiếp giá trị, chỉ tăng/giảm; các cột không thuộc primary key trong bảng counter phải thuộc loại counter; không dùng TTL cho counter; retry khi timeout có nguy cơ **đếm đôi**.

`@CassandraType(type = Name.COUNTER)` chỉ nói kiểu, **không chuyển một mutation bất kỳ thành thao tác cộng counter hợp lệ**. Nếu nghiệp vụ cần bộ đếm chính xác dưới retry, phải thiết kế cơ chế chống lặp hoặc dữ liệu nguồn kiểm chứng khác.

### 11.2. NULL, unset và giá trị mặc định

- `null` của Java có thể tương ứng với trạng thái cột không có giá trị; cách statement sinh ra với `null`, `UNSET` hoặc bỏ qua field phụ thuộc API và đường ghi cụ thể.
- `null` trong CQL không đồng nghĩa ràng buộc `NOT NULL` kiểu RDBMS; một số phần của primary key bắt buộc có giá trị hợp lệ.
- Dùng Java primitive `int`, `boolean` cho field nullable có thể khiến mã ứng dụng nhầm giá trị mặc định 0/false với dữ liệu không tồn tại. Cân nhắc wrapper `Integer`/`Boolean` theo hợp đồng domain.
- Với collection rỗng, collection null và collection chưa cập nhật, cần kiểm chứng round-trip; đừng giả định cả ba trạng thái tương đương.

Không dùng `@CassandraType` để thay validation đầu vào hoặc kỳ vọng nó tự thêm default value trên server.

### 11.3. Kiểu của primary key ảnh hưởng truy vấn và clustering

Nếu schema dùng `created_at timeuuid` làm clustering key, query range và thứ tự khác với một cột `text` lưu timestamp đã format. Nếu dùng `timestamp`, thứ tự là theo thời điểm chứ không theo chuỗi hiển thị. Thiết kế type đúng giúp truy vấn range đúng, nhưng **partition key và thứ tự clustering** vẫn phải được xác định dựa trên access pattern.

Ví dụ hệ thống cần tìm “20 event mới nhất của user trong ngày”: bảng có partition key `(user_id, day_bucket)` và clustering `timeuuid DESC` có thể hữu ích. Còn bảng chỉ có khóa `event_id uuid` sẽ không tự hỗ trợ truy vấn theo user/ngày khi thêm `@CassandraType`.

### 11.4. Không dùng collection làm event log vô hạn

~~~sql
-- Thiết kế khó vận hành nếu mỗi user có hàng triệu event:
CREATE TABLE user_events_bad (
    user_id uuid PRIMARY KEY,
    all_events list<text>
);
~~~

Một mô hình tốt hơn cho lịch sử theo user/tháng:

~~~sql
CREATE TABLE events_by_user_month (
    user_id uuid,
    month_bucket text,
    event_id timeuuid,
    payload text,
    PRIMARY KEY ((user_id, month_bucket), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Ở bảng mới, mỗi event là một row có clustering key; ứng dụng có thể đọc có giới hạn, paging theo partition và quản lý kích thước bucket. Đây là **thiết kế theo truy vấn**, khác với tăng kích thước một collection không giới hạn.

## 12. Tình huống thực hành: lưu thông báo đa kênh

Yêu cầu nghiệp vụ:

- Mỗi thông báo có UUID version 1 để sắp xếp theo thời gian nhận.
- Có tiêu đề tiếng Việt và trạng thái gửi.
- Có tập kênh được chọn và một map nhỏ biểu thị bật/tắt các tuỳ chọn.
- Có địa chỉ nhận gói trong dạng UDT, thay đổi nguyên khối khi cập nhật.
- Phải đọc được 30 thông báo gần nhất của một user trong một ngày.

### 12.1. Thiết kế CQL theo truy vấn

~~~sql
CREATE TYPE recipient_address (
    city text,
    country_code ascii
);

CREATE TABLE notifications_by_user_day (
    user_id uuid,
    day_bucket date,
    notification_id timeuuid,
    title text,
    channels set<text>,
    options map<text, boolean>,
    recipient frozen<recipient_address>,
    PRIMARY KEY ((user_id, day_bucket), notification_id)
) WITH CLUSTERING ORDER BY (notification_id DESC);
~~~

### 12.2. Java mapping

~~~java
@UserDefinedType("recipient_address")
public class RecipientAddress {

    @CassandraType(type = Name.TEXT)
    private String city;

    @Column("country_code")
    @CassandraType(type = Name.ASCII)
    private String countryCode;

    // Constructor, getters, setters...
}

@PrimaryKeyClass
public class NotificationKey implements Serializable {

    @PrimaryKeyColumn(
        name = "user_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID userId;

    @PrimaryKeyColumn(
        name = "day_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private LocalDate dayBucket;

    @PrimaryKeyColumn(
        name = "notification_id",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    @CassandraType(type = Name.TIMEUUID)
    private UUID notificationId;

    // Constructor, getters, setters, equals(), hashCode()...
}

@Table("notifications_by_user_day")
public class NotificationByUserDay {

    @PrimaryKey
    private NotificationKey key;

    @CassandraType(type = Name.TEXT)
    private String title;

    @CassandraType(type = Name.SET, typeArguments = Name.TEXT)
    private Set<String> channels;

    @CassandraType(
        type = Name.MAP,
        typeArguments = {Name.TEXT, Name.BOOLEAN}
    )
    private Map<String, Boolean> options;

    @CassandraType(type = Name.UDT)
    private RecipientAddress recipient;

    // Constructor, getters, setters...
}
~~~

Ví dụ lược bỏ imports và boilerplate của hai class sau. `NotificationKey` cần `equals()`/`hashCode()` nhất quán theo tất cả thành phần khóa; giá trị khóa cần ổn định sau khi lưu. Lưu ý Spring Data có thể cần cấu hình UDT resolver phù hợp, và các annotation phải khớp schema thật.

### 12.3. Truy vấn và paging

~~~sql
SELECT notification_id, title, channels, options, recipient
FROM notifications_by_user_day
WHERE user_id = ?
  AND day_bucket = ?
LIMIT 30;
~~~

`day_bucket` là thành phần partition key thứ hai, buộc query cung cấp đủ điều kiện. `notification_id` là clustering key dạng `timeuuid`, giúp trả danh sách theo thứ tự giảm dần trong partition.

Nếu cần xem nhiều ngày, ứng dụng chọn các day bucket phù hợp và ghép kết quả theo cursor. `@CassandraType` giúp mapping kiểu, còn việc phân trang hiệu quả phụ thuộc schema và giới hạn truy vấn, không có global offset tự động.

### 12.4. Kịch bản cần tự kiểm chứng

| Tình huống | Kỳ vọng |
| --- | --- |
| Lưu tiêu đề `"Giao hàng thành công"` | Unicode được giữ nguyên với CQL `text` |
| Dùng `UUID.randomUUID()` cho `notification_id timeuuid` | Bị coi là không hợp lệ về CQL type version |
| `channels = Set.of("email", "push")` | Lưu được `set<text>` nhỏ, không có phần tử trùng |
| `options = Map.of("urgent", true)` | Lưu được `map<text, boolean>` |
| `country_code = "VN"` | Hợp với `ascii` |
| `country_code = "Việt Nam"` | Không hợp với CQL `ascii`, nên validate trước |
| Lưu UDT `RecipientAddress` | Đọc lại đúng `city`, `countryCode`, xác minh tên type và schema |
| Đọc list theo ngày | Đủ partition key, sắp xếp theo `timeuuid DESC` |
| Đổi annotation mà schema chưa đổi | Vẫn phải làm migration; mapping một phía không đủ |

## 13. Checklist thiết kế và kiểm soát hiệu năng

Trước khi chốt một field có `@CassandraType`:

1. **Xác định ý nghĩa dữ liệu:** số nguyên hay số thực; thời điểm hay ngày; UUID thường hay timeuuid.
2. **Chọn kiểu Java tương thích:** `BigDecimal` cho decimal, `Instant` cho timestamp, `UUID` version 1 cho timeuuid; dùng converter nếu domain type riêng.
3. **Đối chiếu CQL:** `@CassandraType`, tên cột, schema migration và version của cluster/driver phải đồng nhất.
4. **Điền đủ typeArguments:** một phần tử cho `list`/`set`, hai phần tử cho `map`, đúng thứ tự key/value.
5. **Phân biệt UDT và frozen:** xác định tên UDT, mapping class/`UdtValue` và ngữ nghĩa cập nhật whole value khi frozen.
6. **Xem giới hạn kiểu:** không dùng `counter` như `bigint`, `ascii` cho Unicode, `duration` làm primary key, `UUID v4` cho timeuuid.
7. **Đặt quy tắc null/precision:** wrapper nullable, timestamp mili giây, scale tiền tệ và định dạng số hợp lệ.
8. **Ràng buộc kích thước collection:** giới hạn số phần tử và payload; thiết kế bảng riêng nếu cần lịch sử vô hạn.
9. **Kiểm tra truy vấn:** partition key/clustering key phục vụ đúng `WHERE`, `ORDER BY`, paging và consistency yêu cầu.
10. **Kiểm chứng round-trip và lỗi:** chạy thử với Cassandra thực của môi trường test; đo latency/payload/tombstone và kiểm tra lỗi mapping.
11. **Quản lý thay đổi schema:** áp dụng migration và chuyển dữ liệu khi đổi kiểu; không trông chờ annotation thay toàn bộ dữ liệu cũ.
12. **Giữ tính nhất quán giữa các bảng:** nếu một thuộc tính được denormalize vào nhiều bảng phục vụ truy vấn, ứng dụng phải cập nhật/đối soát từng biểu diễn.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `@CassandraType(type = Name.TIMEUUID)` trên `UUID` có làm mọi UUID tự động trở thành UUID version 1 không?

*Gợi ý:* Không. Phải cung cấp UUID version 1 thực sự; annotation không tạo/chuyển version.

**Câu 2.** `Map<String, Boolean>` lưu vào `map<text, boolean>` cần `typeArguments` thế nào?

*Đáp án:* `{Name.TEXT, Name.BOOLEAN}`, key trước, value sau.

**Câu 3.** Tại sao không nên dùng `Double` để giữ tổng tiền nếu CQL đã dùng `decimal`?

*Gợi ý:* Số thực nhị phân có thể mất chính xác; `BigDecimal` phù hợp hơn và cần chính sách scale.

**Câu 4.** Trong trường hợp nào cần `userTypeName`?

*Gợi ý:* Khi Spring Data không suy được tên UDT từ class có `@UserDefinedType`, ví dụ mapping trực tiếp một `UdtValue`.

**Câu 5.** `@CassandraType(type = Name.TEXT)` trên field `OrderCode` có tự sinh converter `OrderCode -> String` không?

*Đáp án:* Không; cần converter/mapping phù hợp.

**Câu 6.** Vì sao `timestamp` lưu từ Java `Instant` có thể không đọc lại được đúng phần nano giây?

*Gợi ý:* Cassandra lưu timestamp theo mili giây.

**Câu 7.** Khi nào nên thay `list<text>` lớn thành bảng có clustering key?

*Gợi ý:* Khi collection tăng không giới hạn, gây payload lớn và khó phân trang/cập nhật an toàn.

**Câu 8.** Vì sao đặt `@CassandraType(type = Name.BIGINT)` không làm cột `int` đã tồn tại trên server đổi sang `bigint`?

*Gợi ý:* Annotation là mapping metadata phía ứng dụng; cần schema migration và kiểm tra dữ liệu.

**Câu 9.** Dùng `duration` để lưu “1 tháng” rồi tự đổi sang 30 ngày có đúng không?

*Gợi ý:* Không; số ngày của tháng thay đổi, duration có semantics riêng.

**Câu 10.** Nếu muốn lọc thông báo theo `user_id` và `day_bucket`, annotation cho `title` có giúp truy vấn thiếu partition key chạy hiệu quả không?

*Gợi ý:* Không. Hiệu năng phụ thuộc mô hình partition/clustering và access pattern, không phải annotation cho một cột thường.

## Tài liệu tham khảo

- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `MappingCassandraConverter`, `@CassandraType`, collection, UDT và tuple.
- [Spring Data Cassandra — API của CassandraType](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/mapping/CassandraType.html): các thuộc tính `type`, `typeArguments` và `userTypeName`.
- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html): kiểu native, collections, UDT, tuple, counter, frozen và các giới hạn.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): cú pháp schema và truy vấn.

## Kết luận

`@CassandraType` giúp Spring Data Cassandra **biết chính xác kiểu CQL mong muốn** cho property hoặc tham số, nhất là khi cùng kiểu Java có thể tương ứng nhiều kiểu Cassandra hoặc khi dùng collection, UDT và converter tùy chỉnh. `type` chọn kiểu chính, `typeArguments` mô tả kiểu phần tử của collection/map, và `userTypeName` xác định tên UDT khi cần.

Một ánh xạ đáng tin cậy phải thống nhất **Java domain type → converter/mapping → Java Driver codec → CQL schema thật**. Đừng kỳ vọng annotation tự sửa schema, tạo codec mới hoặc thay đổi đặc tính của Cassandra. Hãy kiểm chứng round-trip và những ranh giới như timeuuid, độ chính xác timestamp, decimal, null, frozen và counter. Cuối cùng, chọn kiểu hợp lý cần đi cùng thiết kế partition key, clustering key, paging, consistency và giới hạn kích thước dữ liệu để truy vấn Spring Data Cassandra vận hành ổn định trên hệ thống phân tán.
