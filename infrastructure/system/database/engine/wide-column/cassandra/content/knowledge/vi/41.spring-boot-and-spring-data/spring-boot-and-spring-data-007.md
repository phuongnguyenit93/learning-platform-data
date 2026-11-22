# Mapping collection/UDT, enum, thời gian và custom converter với Spring Boot và Spring Data Cassandra

## 1. Tại sao mapping Cassandra cần được thiết kế có chủ đích?

Trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, Apache Cassandra là hệ quản trị **wide-column phân tán**: **partition key** quyết định phân phối dữ liệu, bảng được tạo theo mẫu truy vấn, **replication factor (RF)** cùng **consistency level (CL)** quyết định điều kiện đọc/ghi và các hoạt động repair, compaction, xử lý lỗi có ảnh hưởng trực tiếp đến ứng dụng Java.

**Spring Boot** giúp cấu hình Java Driver, còn **Spring Data Cassandra** ánh xạ đối tượng Java sang cột CQL qua `MappingCassandraConverter`, `CassandraTemplate` và repository. Việc một đối tượng được lưu/đọc thành công **không có nghĩa** mô hình CQL tối ưu, thao tác update là nguyên tử, hoặc mọi chuyển đổi kiểu đều không mất dữ liệu.

Với dữ liệu đơn giản `UUID`, `String`, `long`, mapping thường dễ hiểu. Khi xuất hiện:

- `List<E>`, `Set<E>`, `Map<K,V>` với quy tắc collection/tombstone/frozen riêng;
- **UDT** (*user-defined type*) lồng nhau, đôi khi nằm trong collection;
- **enum** Java có thể được đổi tên/thêm giá trị sau khi dữ liệu cũ đã lưu;
- `Instant`, `LocalDate`, `LocalTime`, timezone và độ chính xác thời gian;
- **custom converter** cho value object, stable code hoặc định dạng lưu đặc thù;

thì cần quy định **schema CQL ⇄ Java type ⇄ wire representation ⇄ business contract** một cách tường minh.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Chọn đúng CQL type cho `List/Set/Map` và map sang Java, hiểu `frozen` và giới hạn collection.
2. Định nghĩa `CREATE TYPE` cùng `@UserDefinedType`, `@Frozen` và `@Column` cho nested object.
3. Phân biệt mapping enum mặc định sang text, mapping theo ordinal và mapping bằng **stable code + converter**.
4. Ánh xạ thời gian một cách an toàn: instant, ngày, giờ trong ngày, múi giờ và precision.
5. Đăng ký `@ReadingConverter`, `@WritingConverter` bằng `CassandraCustomConversions`; phân biệt **global type converter** với **per-property converter**.
6. Kiểm thử round-trip và schema compatibility trước khi áp dụng migration.
7. Nhận biết tình huống cần dùng CQL/Java Driver trực tiếp thay vì repository `save(...)`.

Bài thuộc chương **Spring Boot và Spring Data**; ví dụ dùng API Spring Data Cassandra đời hiện đại cùng Java Driver 4.x. **Không mặc định phiên bản Spring Boot, Spring Data, Java Driver và Cassandra Server có cùng số phiên bản hoặc hỗ trợ lẫn nhau.** Kiểm version matrix trước khi đưa mã vào dự án thực tế.

## 2. Bảng đối chiếu CQL type và Java type

| CQL type | Java type thường dùng | Điều cần kiểm |
| --- | --- | --- |
| `uuid` | `UUID` | Khóa partition/ID được tạo nhất quán, không dùng chuỗi sai định dạng |
| `text` / `varchar` | `String` | Encoding, enum code, length validation ở ứng dụng |
| `int`, `bigint` | `Integer`, `Long` | Tránh dùng sai kiểu/sai phạm vi |
| `decimal` | `BigDecimal` | Precision/scale theo hợp đồng nghiệp vụ |
| `list<text>` | `List<String>` | Có thứ tự; append/prepend có thể không idempotent |
| `set<text>` | `Set<String>` | Không trùng phần tử; không dựa vào thứ tự iteration |
| `map<text,text>` | `Map<String,String>` | Cập nhật theo key; kích thước collection cần giới hạn |
| `frozen<postal_address>` | `@Frozen PostalAddress` | UDT frozen được xử lý như một giá trị |
| `list<frozen<postal_address>>` | `List<@Frozen PostalAddress>` | UDT bên trong collection phải theo quy định frozen |
| `timestamp` | `Instant` | Điểm thời gian tuyệt đối, CQL precision millisecond |
| `date` | `LocalDate` | Ngày lịch, không chứa offset/timezone |
| `time` | `LocalTime` | Giờ trong ngày, không chứa ngày hay múi giờ |
| `duration` | Kiểu duration của driver như `CqlDuration` | Tháng/ngày/nanosecond không tương đương trực tiếp `java.time.Duration` |
| `text` cho timezone | `String` hoặc value object `ZoneId` có converter | Lưu zone ID như `Asia/Ho_Chi_Minh`, không chỉ offset cố định |

**Các mối quan hệ là hướng dẫn chọn kiểu**, không cam kết auto mapping cho mọi version/annotation combination. Khi gặp nested UDT, custom type hoặc trường đặc biệt, hãy kiểm hỗ trợ của Spring Data/driver đang dùng và viết test round-trip.

### Mapping không thay thế thiết kế partition key

Ví dụ một bảng tra cứu hồ sơ theo `customer_id`:

```sql
SELECT customer_id, status_code, joined_at
FROM commerce.customer_profiles_by_id
WHERE customer_id = ?;
```

Spring repository `findById(customerId)` có thể phù hợp vì partition key được xác định. Nhưng nếu muốn liệt kê hồ sơ theo `city`, không thể giải quyết chỉ bằng cách thêm getter Java hoặc `@Column`; cần đánh giá bảng theo truy vấn, index phù hợp hoặc pipeline denormalization.

## 3. Thiết lập Spring Boot + Spring Data Cassandra

### 3.1. Chọn dependency

Với Maven và Spring Boot có dependency management tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-cassandra")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Các ví dụ giả định project đã áp dụng **Spring Boot plugin/parent hoặc BOM phù hợp** để quản lý phiên bản. Đừng chèn thêm nhiều `java-driver-core` khác group/version hoặc tự nâng Spring Data Cassandra ngoài support matrix vì có thể dẫn tới `NoSuchMethodError`, `ClassNotFoundException` hay lỗi mapping ở runtime.

Spring Data Cassandra **khác Spring Data JPA**: không có join/JPA persistence context, không tự tạo transaction ACID đa bảng. Repository cung cấp abstraction tiện dụng, không đổi ngữ nghĩa Cassandra.

### 3.2. Cấu hình kết nối

Ví dụ `application.yml`:

```yaml
spring:
  cassandra:
    keyspace-name: commerce
    contact-points:
      - cassandra-node-1:9042
      - cassandra-node-2:9042
    local-datacenter: dc1
    schema-action: NONE
```

Cấu hình phải khớp **tên datacenter thực tế**, native protocol endpoint, auth/TLS và Cassandra Server được triển khai. Với Spring Boot production:

- Cung cấp credential qua secret manager/configuration có quyền truy cập hạn chế.
- Bật TLS, xác minh trust material/hostname và chính sách certificate.
- Dùng role ứng dụng **quyền tối thiểu**, không dùng superuser.
- **Không bật tạo/xóa schema tự động trong production** để thay thế lịch sử DDL Git; lựa chọn `schema-action: NONE` là định hướng an toàn cho bài.
- Có thể dùng `CqlSession`, `CassandraTemplate` hoặc `CassandraRepository` do Boot/Spring Data quản lý; không tạo một session mới mỗi HTTP request.

Các property trên là mẫu của Spring Boot hiện đại. Nếu dự án còn bản Spring Boot cũ hoặc config riêng của Driver, **xác minh tên property theo bản đang chạy** trước khi sao chép.

## 4. Schema CQL xuyên suốt: collection, UDT, enum và thời gian

Bài sẽ dùng một ví dụ **hồ sơ khách hàng** với các thuộc tính được đọc/ghi theo `customer_id`. Trên cluster lab có datacenter `dc1` với ít nhất ba node:

```sql
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TYPE IF NOT EXISTS commerce.postal_address (
    street text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS commerce.customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    interests set<text>,
    recent_codes list<text>,
    preferences map<text, text>,
    shipping_address frozen<commerce.postal_address>,
    backup_addresses list<frozen<commerce.postal_address>>,
    status_code text,
    joined_at timestamp,
    date_of_birth date,
    preferred_contact_time time,
    timezone_id text
);
```

**Thứ tự tạo:** keyspace → UDT → bảng phụ thuộc UDT. Trong CQL, type `postal_address` thuộc keyspace `commerce`; kết hợp keyspace nhất quán khi tham chiếu UDT và tạo entity.

**RF=3 là ví dụ có điều kiện**, không phù hợp cluster một node. Khi thực hành, dùng RF/CL tương ứng topology và kiểm `nodetool status`/schema agreement; đừng mở sản phẩm lên production chỉ vì lệnh `CREATE ... IF NOT EXISTS` không báo lỗi. `IF NOT EXISTS` có thể che một bảng đã tồn tại **khác schema mong đợi**.

Để hiểu các kiểu:

- `interests`: tập sở thích, không trùng.
- `recent_codes`: chuỗi mã có thứ tự; nếu vô hạn cần đổi mô hình vì collection trong một partition/cell có giới hạn thực tế.
- `preferences`: map nhỏ key/value; không phải nơi lưu JSON khổng lồ.
- `shipping_address`: nested object cố định dạng **frozen UDT**.
- `backup_addresses`: list chứa UDT frozen.
- `status_code`: mã trạng thái ổn định từ enum Java qua converter.
- `joined_at`: một thời điểm tuyệt đối.
- `date_of_birth`: ngày lịch.
- `preferred_contact_time`: giờ trong ngày theo múi giờ mà nghiệp vụ quy định.
- `timezone_id`: tên vùng IANA để diễn giải giờ địa phương.

## 5. Mapping entity và UDT bằng annotation

### 5.1. Định nghĩa lớp UDT

Spring Data Cassandra hỗ trợ `@UserDefinedType`:

```java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("postal_address")
public class PostalAddress {

    private String street;
    private String city;

    @Column("postal_code")
    private String postalCode;

    public PostalAddress() { }

    public PostalAddress(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
```

Điểm quan trọng:

- `@UserDefinedType("postal_address")` ánh xạ lớp Java với CQL UDT tên `postal_address`.
- `@Column("postal_code")` rất quan trọng nếu field Java là `postalCode` nhưng CQL dùng `postal_code`.
- No-arg constructor và getter/setter là một kiểu model đơn giản để học. Spring Data hiện đại còn hỗ trợ constructor binding/record/immutable objects theo điều kiện riêng; **không nên trộn cơ chế immutable với setter khi chưa kiểm version**.
- Khi dùng mapped UDT, `MappingCassandraConverter` cần metadata/resolver của UDT và keyspace chính xác. Một bean tạo bằng tay không có mapping context/user type resolver có thể khác auto-config của Spring Boot.

### 5.2. Entity chứa collections, UDT và time

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Frozen;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customer_profiles_by_id")
public class CustomerProfile {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("interests")
    @CassandraType(
        type = CassandraType.Name.SET,
        typeArguments = CassandraType.Name.TEXT)
    private Set<String> interests;

    @Column("recent_codes")
    private List<String> recentCodes;

    @Column("preferences")
    private Map<String, String> preferences;

    @Column("shipping_address")
    @Frozen
    private PostalAddress shippingAddress;

    @Column("backup_addresses")
    private List<@Frozen PostalAddress> backupAddresses;

    @Column("status_code")
    private CustomerStatus statusCode;

    @Column("joined_at")
    private Instant joinedAt;

    @Column("date_of_birth")
    private LocalDate dateOfBirth;

    @Column("preferred_contact_time")
    @CassandraType(type = CassandraType.Name.TIME)
    private LocalTime preferredContactTime;

    @Column("timezone_id")
    private String timezoneId;

    public CustomerProfile() { }

    // Getters/setters đầy đủ cần có trong mã ứng dụng thực tế.
}
```

Ở đây `@CassandraType` trên `interests` minh họa cách khai báo tường minh `set<text>`, còn `List<String>` và `Map<String,String>` cho thấy mapping thường được suy từ generic type. Cần kiểm schema thực tế thay vì cho rằng tên property tự chuyển thành snake_case như ý: hãy dùng `@Column` cho các cột khác tên.

`CustomerStatus` là enum sẽ được định nghĩa ở phần 9. Nếu dùng ví dụ riêng từng đoạn, **cần ghép class enum/converter** và các getter/setter trước khi biên dịch; những đoạn trên là khối domain model, không phải một source file độc lập.

### 5.3. Khi nào phải dùng `@CassandraType`?

Spring Data thường suy từ khai báo Java, nhưng annotation có ích khi:

- Cần một **CQL type khác default** của Java type.
- Collection cần chỉ rõ `LIST/SET/MAP` và element/key/value type.
- Bạn dùng `UdtValue` thuần thay vì một class có `@UserDefinedType`.
- Enum phải lưu dạng số theo legacy schema.
- Code generator/schema validation cần hiểu chính xác loại CQL.

Ví dụ map có key và value text:

```java
@CassandraType(
    type = CassandraType.Name.MAP,
    typeArguments = {
        CassandraType.Name.TEXT,
        CassandraType.Name.TEXT
    })
private Map<String, String> preferences;
```

Không dùng annotation để “sửa” schema sai: `Map<String,String>` không thể tự nhiên ánh xạ an toàn sang `map<uuid,decimal>` chỉ vì typeArguments khai báo khác mà dữ liệu Java vẫn là chuỗi. **CQL DDL và Java generic type phải thống nhất**.

## 6. Collection mapping: List, Set, Map và đặc tính cập nhật

Cassandra collections hữu ích khi **số phần tử nhỏ và có giới hạn thực tế** trong một partition. Không nên dùng chúng như bảng con vô hạn hay một thay thế join 1-n của RDBMS.

| CQL/Java | Ngữ nghĩa | Rủi ro |
| --- | --- | --- |
| `list<text>` ↔ `List<String>` | Thứ tự phần tử có ý nghĩa | Append/prepend/index mutation, concurrency, kích thước/đọc toàn list |
| `set<text>` ↔ `Set<String>` | Duy nhất theo giá trị, không có thứ tự nghiệp vụ | Không được dựa vào iteration order; xóa/tombstone và update |
| `map<text,text>` ↔ `Map<String,String>` | Tra cứu giá trị theo key trong một collection | Rất nhiều key, phần tử được thay/xóa, tombstone |
| `frozen<list<text>>` ↔ `@Frozen List<String>` (tùy mapping) | Toàn collection được lưu như một giá trị | Cập nhật phần tử riêng không tương tự non-frozen |
| `list<frozen<postal_address>>` | Mỗi UDT element frozen | Phần tử dạng object; cập nhật nested object có giới hạn |

### 6.1. Update trực tiếp bằng CQL để giữ ngữ nghĩa phần tử

Ví dụ cập nhật set, map và list:

```sql
-- Thêm một giá trị vào set (ngữ nghĩa không trùng phần tử).
UPDATE commerce.customer_profiles_by_id
SET interests = interests + {'java'}
WHERE customer_id = ?;

-- Cập nhật một key trong map.
UPDATE commerce.customer_profiles_by_id
SET preferences['language'] = 'vi'
WHERE customer_id = ?;

-- Nối phần tử vào list; không mặc định idempotent nếu retry.
UPDATE commerce.customer_profiles_by_id
SET recent_codes = recent_codes + ['WELCOME10']
WHERE customer_id = ?;
```

**Điểm phải nhớ:**

- `Set` không trùng giá trị theo kiểu dữ liệu và phương thức ghi, nhưng **điều này không tạo exactly-once** cho side effect khác.
- `Map` update theo key khác với thay **toàn map**; nhiều writer sửa các key độc lập có thể hợp lý hơn ghi đè cả object.
- `List` append khi request timeout **không nên retry mù quáng**: cùng phần tử có thể được nối hai lần.
- Với Spring Data repository `save(entity)`, đừng giả định nó tạo đúng từng lệnh `SET col[key] = ...` hoặc append element. Nếu cần atomic-ish theo phần tử của CQL và tối ưu write, dùng **CqlTemplate/driver statement có chủ đích**, kiểm các semantics liên quan.
- Cập nhật/xóa phần tử có thể tạo tombstone; cần theo dõi retention/compaction và giới hạn collection.

### 6.2. `null`, empty và absent không tự đồng nghĩa

Trong application Java có thể có:

```text
null
Collections.emptySet()
Collections.emptyList()
Collections.emptyMap()
```

Đối với persistence:

- **Không có cột/value** có thể được Java mapper biểu diễn bằng `null`.
- Một collection rỗng không phải lúc nào cũng được Cassandra lưu/tái tạo giống một object rỗng trên heap; hành vi phụ thuộc kiểu, phiên bản, write mode và converter.
- Gán `null` cho property rồi gọi `save` có thể dẫn đến thao tác xóa/tombstone hoặc bị bỏ qua theo null-handling của API/mapping. **Không suy đoán**: kiểm generated CQL và integration round-trip.
- Cassandra collection **không hỗ trợ mọi kiểu `null` element** như Java collections; validate list/set/map trước khi ghi.
- Không dùng `null` để phân biệt nhiều trạng thái nghiệp vụ mà không có schema/cột biểu diễn rõ.

Nếu API cần phân biệt “không được cập nhật property” và “xóa property”, hãy dùng PATCH contract/dedicated mutation rõ ràng; không ném một DTO partial vào repository `save` rồi mong Spring tự hiểu.

### 6.3. Hạn mức collection và mô hình wide-column

Giả sử một khách có một triệu đơn hàng: **không** lưu toàn bộ order IDs trong một `List<UUID>` thuộc một hàng. Hãy tạo bảng theo truy vấn:

```sql
CREATE TABLE commerce.orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Bảng có clustering columns cho phép đọc theo partition `customer_id` và phân trang; khi partition vẫn quá lớn, nghiên cứu **bucket theo thời gian/khóa**. Collection nên dùng cho **sở thích nhỏ, thuộc tính cấu hình ngắn**, không phải lịch sử không giới hạn.

## 7. UDT: cấu trúc hợp lý nhưng không phải bảng quan hệ

`postal_address` là một **user-defined type** thuộc keyspace, chứa `street`, `city`, `postal_code`. UDT không có primary key riêng như một bảng độc lập.

### 7.1. `frozen` và giới hạn thay đổi

```sql
shipping_address frozen<postal_address>
```

Với `frozen<postal_address>`, Cassandra xử lý cấu trúc như một **giá trị**; khi muốn đổi một field, ứng dụng thường phải cung cấp UDT mới đầy đủ thay vì UPDATE trực tiếp từng trường con.

Ví dụ CQL thay toàn UDT:

```sql
UPDATE commerce.customer_profiles_by_id
SET shipping_address = {
    street: '12 Nguyen Hue',
    city: 'Ho Chi Minh City',
    postal_code: '700000'
}
WHERE customer_id = ?;
```

Đây là cú pháp minh họa UDT literal có tên trường. Phải kiểm kiểu UDT/frozen và CQL syntax theo phiên bản. Thay một UDT frozen có thể làm **mất sửa đổi đồng thời** nếu hai request đọc cùng snapshot, mỗi request thay trường khác nhau rồi ghi đè toàn object.

Nếu nghiệp vụ cần cập nhật từng field độc lập, cân nhắc một UDT **không frozen** ở vị trí được Cassandra version hỗ trợ hoặc mô hình cột riêng. **Không thể tự loại bỏ `frozen` khỏi schema hiện hữu chỉ bằng việc bỏ annotation Java**; thay đổi CQL type cần migration được kiểm soát.

### 7.2. Nested UDT trong collection

```sql
backup_addresses list<frozen<postal_address>>
```

UDT trong list phải tuân thủ yêu cầu frozen của kiểu phần tử. Spring Data biểu diễn bằng:

```java
@Column("backup_addresses")
private List<@Frozen PostalAddress> backupAddresses;
```

Hãy kiểm support của **version Spring Data/driver thực tế** cho type-use annotations. Nếu stack cũ không hỗ trợ cách annotate này, có thể cần cấu hình kiểu tường minh, dùng `UdtValue` với prepared statement hoặc chỉnh model; không tự đổi wire type.

### 7.3. Khi thêm field vào UDT

```sql
ALTER TYPE commerce.postal_address
ADD country_code text;
```

Sau migration:

1. Chờ schema agreement; schema cũ/mới trong rolling deploy phải tương thích.
2. Bổ sung field Java `@Column("country_code") private String countryCode`.
3. Chấp nhận dữ liệu UDT cũ có field mới `null` hoặc migration/backfill nếu nghiệp vụ yêu cầu.
4. Test ghi của phiên bản ứng dụng cũ: một client không biết field mới **có thể ghi lại một frozen UDT thiếu field đó**.
5. Không dùng “mapping thành công” để chứng minh dữ liệu field mới của mọi record đã được backfill.
6. Tránh đổi tên/xóa UDT field khi client cũ còn đang dùng, và có kế hoạch migration riêng cho thay đổi phá vỡ tương thích.

**UDT dùng chung bởi nhiều bảng:** một `ALTER TYPE` có thể ảnh hưởng nhiều nơi; kiểm các table, ứng dụng và backup/restore liên quan trước khi đổi.

## 8. Enum: mặc định text, không mặc định an toàn khi đổi tên

Giả sử enum:

```java
public enum CustomerStatus {
    ACTIVE,
    PAUSED,
    CLOSED
}
```

Spring Data Cassandra có thể mapping enum sang **CQL text** theo tên của enum ở thiết lập mặc định. Điều này thường dễ quan sát hơn ordinal:

| Cách lưu | Ví dụ CQL | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Tên enum | `'ACTIVE'` | Dễ đọc, ổn định nếu tên giữ nguyên | Đổi `ACTIVE` → `ENABLED` làm dữ liệu cũ không map được |
| Ordinal/int | `0`, `1`, `2` | Nhỏ, có thể phù hợp legacy | Thêm/sắp xếp lại enum constants khiến số mang nghĩa khác |
| **Stable code** | `'A'`, `'P'`, `'C'` | Có hợp đồng lưu trữ tách khỏi tên Java | Cần converter và quản lý code độc lập |
| Cột text business code thuần | `String statusCode` | Không cần converter | Mất type-safety ở domain nếu không validate |

### 8.1. Vì sao không nên phụ thuộc enum ordinal

```java
// Ví dụ cho thấy annotation numeric tồn tại, KHÔNG khuyến nghị dùng mới.
@CassandraType(type = CassandraType.Name.INT)
private CustomerStatus statusCode;
```

Giả sử enum ban đầu:

```java
enum CustomerStatus { ACTIVE, PAUSED, CLOSED } // ordinal 0, 1, 2
```

Một developer chèn `PENDING` ở đầu:

```java
enum CustomerStatus { PENDING, ACTIVE, PAUSED, CLOSED }
```

Nếu lưu ordinal, giá trị `1` vốn là `PAUSED` nay được diễn giải là `ACTIVE`. Đây có thể là lỗi **âm thầm sai dữ liệu**, khó phát hiện hơn exception. Do vậy, **không dùng ordinal làm giao thức lưu trữ ổn định** cho dữ liệu lâu dài nếu không có yêu cầu legacy và biện pháp tương thích.

### 8.2. Thêm enum code mới phải có chiến lược rollout

Nếu bản Java cũ không biết code `'H'` nhưng bản mới ghi `'H'`, bản cũ có thể throw khi đọc. Nên:

1. **Expand reader**: triển khai code hiểu code mới nhưng chưa ghi nó.
2. Xác nhận tất cả reader/worker đã có logic tương thích.
3. **Enable writer**: bắt đầu ghi code mới có feature flag nếu cần.
4. Theo dõi errors và phân phối mã lưu.
5. Chỉ xóa code cũ khi dữ liệu và mọi consumer được migration.

Đừng để converter lặng lẽ biến **mọi unknown code thành ACTIVE**: sẽ che data corruption hoặc lỗi rollout. Tùy hợp đồng, dùng `UNKNOWN` explicit, quarantine hoặc fail fast có metrics.

## 9. Custom converter cho enum stable code

Tạo một enum có code bất biến:

```java
public enum CustomerStatus {
    ACTIVE("A"),
    PAUSED("P"),
    CLOSED("C");

    private final String code;

    CustomerStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static CustomerStatus fromCode(String code) {
        for (CustomerStatus value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        throw new IllegalArgumentException(
            "Unknown customer status code: " + code);
    }
}
```

Trên CQL, cột `status_code text` chứa `'A'`, `'P'` hay `'C'`, **không phụ thuộc** tên Java enum. Ví dụ hai converter:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class CustomerStatusWriteConverter
        implements Converter<CustomerStatus, String> {

    @Override
    public String convert(CustomerStatus source) {
        return source.code();
    }
}
```

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class CustomerStatusReadConverter
        implements Converter<String, CustomerStatus> {

    @Override
    public CustomerStatus convert(String source) {
        return CustomerStatus.fromCode(source);
    }
}
```

Điểm quan trọng:

- `@WritingConverter` áp dụng chuyển **Java domain → loại lưu được trong Cassandra**.
- `@ReadingConverter` áp dụng chuyển **loại đọc từ Cassandra → Java domain**.
- Phải định nghĩa cả hai hướng nếu service cần round-trip. Chỉ có write converter sẽ làm đọc enum thất bại/không theo contract.
- Mapping `String → CustomerStatus` ở đây áp dụng cho **tất cả property cùng kiểu `CustomerStatus`** mà cơ chế mapping chọn, không chỉ một field.
- Converter **không tự được lấy từ classpath scan theo mọi trường hợp**; phải đăng ký với mapping infrastructure.
- Trong converter, nên validate `null`/unknown code theo contract. Không log dữ liệu nhạy cảm. Có thể làm lớp enum có giá trị `UNKNOWN` nếu nghiệp vụ chấp nhận, nhưng cần định nghĩa rõ không biến “mã chưa hỗ trợ” thành “status hợp lệ”.

### 9.1. Đăng ký bằng `CassandraCustomConversions`

Ví dụ với Spring Data Cassandra 4.x+ tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration(proxyBeanMethods = false)
public class CassandraMappingConfiguration {

    @Bean
    CassandraCustomConversions cassandraCustomConversions() {
        return CassandraCustomConversions.create(registry -> {
            registry.registerConverter(new CustomerStatusWriteConverter());
            registry.registerConverter(new CustomerStatusReadConverter());
        });
    }
}
```

Nếu ứng dụng **tự extends `AbstractCassandraConfiguration`**, cách cấu hình có thể là override `customConversions()` thay vì khai báo một bean trùng. Nếu Spring Boot đã auto-config Cassandra mapping, xác nhận bean `CassandraCustomConversions` được sử dụng bởi **`MappingCassandraConverter` thật** và không bị một config thứ hai ghi đè. Chính xác API `create(...)`/registration phụ thuộc Spring Data version; nếu stack cũ hơn, dùng constructor/registration được bản đó hỗ trợ.

**Không đăng ký converter chung `Converter<String,String>` để chuẩn hóa mọi status**: nó có thể tác động không mong muốn lên **mọi cột text**. Với yêu cầu chỉ tác động một property, xem phần per-property converter.

### 9.2. Kiểm thử converter độc lập

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class CustomerStatusConversionTest {

    private final CustomerStatusWriteConverter writer =
        new CustomerStatusWriteConverter();
    private final CustomerStatusReadConverter reader =
        new CustomerStatusReadConverter();

    @Test
    void roundTripStableCode() {
        assertEquals("A", writer.convert(CustomerStatus.ACTIVE));
        assertEquals(CustomerStatus.ACTIVE, reader.convert("A"));
        assertEquals(CustomerStatus.PAUSED, reader.convert("P"));
    }

    @Test
    void rejectUnknownCode() {
        assertThrows(
            IllegalArgumentException.class,
            () -> reader.convert("UNSUPPORTED"));
    }
}
```

Đây là **unit test converter**, chưa chứng minh `CassandraTemplate`/repository đã dùng đúng converter hoặc column CQL đúng kiểu. Cần thêm integration test đọc/ghi Cassandra thật.

## 10. Per-property converter: khi không muốn tác động toàn bộ kiểu

Có thể xảy ra trường hợp cùng Java `String` nhưng một field lưu uppercase, một field cần giữ nguyên, hoặc cùng một value object có hai wire formats ở những bảng khác nhau.

Với các bản Spring Data Cassandra hỗ trợ **property-based conversions**, sử dụng `@ValueConverter` và một `PropertyValueConverter`/`CassandraValueConverter` phù hợp. Ví dụ ý tưởng:

```java
// Ví dụ minh họa annotation per-property; cần import từ bản
// Spring Data Commons/Cassandra đang dùng và triển khai converter phù hợp.
@ValueConverter(NormalizedLanguageCodeConverter.class)
@Column("language_code")
private String languageCode;
```

`NormalizedLanguageCodeConverter` là **lớp giả định** do ứng dụng tạo; snippet trên không hoàn chỉnh nếu chưa khai báo converter. Ý nghĩa là chỉ conversion của **property `languageCode`** được thay đổi thay vì áp cho mọi `String` trong Cassandra entity.

### 10.1. Chọn global hay per-property?

| Cơ chế | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| `CassandraCustomConversions` + `@ReadingConverter/@WritingConverter` | Cùng domain type luôn có một wire representation | Phạm vi áp dụng rộng tới mọi property dùng type |
| `@ValueConverter`/`PropertyValueConverter` | Một cột có quy tắc chuyển đổi riêng | Phụ thuộc version, cần test registration/context |
| Dùng `@CassandraType` | Chọn kiểu CQL cho property | Không tự giải quyết business encoding đặc biệt |
| Dùng explicit `CqlSession` + codec | Cần quyền kiểm soát CQL/wire protocol thấp hơn | Bỏ qua một phần mapping Spring, phải tự map/validate |
| Domain DTO → entity mapping ngoài Spring Data | Cần tách API/domain model khỏi persistence | Thêm mã chuyển đổi nhưng ranh giới rõ |

**Đừng sử dụng converter để thực hiện network I/O hoặc gọi dịch vụ khác.** Mapper được gọi khi đọc/ghi persistence và phải giữ deterministic/nhanh/thread-safe. Nếu cần mã hóa trường dữ liệu nhạy cảm, dùng converter/codec được quản trị khóa đúng, tránh viết crypto tự chế và đo overhead.

## 11. Thời gian: `Instant`, `LocalDate`, `LocalTime`, `ZoneId`

Phần dễ lỗi nhất là nhầm **thời điểm tuyệt đối** với **ngày/giờ địa phương**.

| Ý định nghiệp vụ | CQL | Java | Giải thích |
| --- | --- | --- | --- |
| Khách đăng ký tại một thời điểm | `timestamp` | `Instant` | Một điểm trên UTC timeline |
| Sinh nhật | `date` | `LocalDate` | Ngày lịch, không có timezone/giờ |
| Muốn nhận thông báo lúc 09:30 | `time` | `LocalTime` | Giờ trong ngày, chưa thể xác định instant |
| Múi giờ khách chọn | `text` | `String` lưu IANA `ZoneId` | Cần ghép với date/time để ra instant |
| Khoảng chờ chính xác 30 phút | Thường dùng `bigint` số millis hoặc kiểu phù hợp | `Duration` | Là độ dài cố định; tránh suy rằng CQL `duration` luôn tương đương |
| Chu kỳ “một tháng” | CQL `duration` hoặc mô hình riêng | `Period`/quy tắc nghiệp vụ | “1 tháng” không phải số giây cố định |

### 11.1. Timestamp mang thời điểm, không mang timezone gốc

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant stored = Instant.parse("2026-11-21T02:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime local = stored.atZone(zone);
// local tương ứng 09:30 tại Asia/Ho_Chi_Minh.
```

CQL `timestamp` lưu thời điểm; nó không tự lưu “người dùng chọn múi giờ nào”. Khi cần hiển thị địa phương, phải có **zone ID riêng hoặc policy cố định**.

**Vì sao không dùng `LocalDateTime` để lưu thời điểm tuyệt đối?** Nó thiếu offset/timezone; `2026-11-21T09:30` có thể là nhiều instant khác nhau tùy khu vực. Default converter của Java time ở một số stack có thể phụ thuộc **system-default timezone** khi đi qua `java.util.Date`. Với event/audit/purchase timestamps, ưu tiên `Instant` và integration test trên các JVM timezone khác nhau.

### 11.2. Độ chính xác của `timestamp`

CQL `timestamp` sử dụng **độ chính xác millisecond**. `Instant` có thể biểu diễn nanoseconds, nên round-trip có thể mất các chữ số nhỏ hơn millisecond.

```java
import java.time.Instant;

Instant source = Instant.parse("2026-11-21T02:30:00.123456789Z");
Instant expected = Instant.ofEpochMilli(source.toEpochMilli());

// expected có phần giây .123, không phải .123456789.
```

Nếu business cần micro/nanosecond precision, không âm thầm lưu vào `timestamp` rồi mong round-trip đầy đủ: cần mô hình lưu riêng, ví dụ epoch nanoseconds theo quy tắc chính xác và khả năng overflow được phân tích, hoặc một kiểu dữ liệu ứng dụng khác.

### 11.3. CQL `date` và giờ sinh nhật

`LocalDate.of(1998, 4, 12)` ánh xạ tự nhiên với CQL `date`. Không chuyển nó sang `Instant` tại midnight UTC nếu yêu cầu chỉ là **ngày lịch**, bởi múi giờ người dùng có thể biến một instant đó thành **ngày khác**.

```java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1998, 4, 12);
```

### 11.4. CQL `time` có nano-of-day, không có timezone

```java
import java.time.LocalTime;

LocalTime contactHour = LocalTime.of(9, 30);
long nanoOfDay = contactHour.toNanoOfDay();
```

CQL `time` biểu diễn thời gian trong ngày, không phải một instant có thể so với `Instant.now()` trực tiếp. Với thông báo lúc 09:30 tại múi giờ khách, cần:

1. Đọc `LocalDate` mà thông báo được lên lịch.
2. Đọc `LocalTime 09:30`.
3. Đọc `ZoneId` hợp lệ (ví dụ `Asia/Ho_Chi_Minh`).
4. Xác định policy với giờ **không tồn tại/lặp** trong ngày DST tại những múi giờ có chuyển giờ.
5. Chuyển ra `Instant` chỉ khi thực sự lập lịch.

**Không lưu timezone dưới dạng offset `+07:00` cho mọi nơi** nếu cần xử lý lịch dài hạn tại khu vực có DST hoặc thay đổi quy định.

### 11.5. CQL `duration` không phải Java `Duration` thuần

Cassandra `duration` có thể biểu diễn thành phần **tháng, ngày và nanoseconds**, trong khi `java.time.Duration` là độ dài thời gian dựa trên giây/nanoseconds, và `Period` lại thiên về lịch.

- “Một tháng” không có số giây cố định.
- Việc cộng `1 month` vào ngày 31 có thể khác việc cộng 30 ngày.
- Nếu dùng kiểu driver `CqlDuration`, xác minh serialization/mapping và cách diễn giải business.
- Nếu chỉ cần timeout xử lý, `java.time.Duration` thuộc **cấu hình request ứng dụng**, không phải bắt buộc lưu CQL `duration`.

## 12. Custom converter cho value object thời gian: khi cần và không cần

Spring Data Cassandra đã hỗ trợ nhiều kiểu `java.time` phổ biến; không nên viết converter tùy ý cho `Instant ↔ String` nếu cột thật là `timestamp` và driver đã map đúng.

Tuy nhiên một legacy schema có thể dùng `bigint` để lưu **epoch milliseconds**. Nếu domain muốn một value object giữ `Instant` để biểu diễn thời điểm quan sát:

```java
import java.time.Instant;

public record ObservedAt(Instant value) {
    public ObservedAt {
        if (value == null) {
            throw new IllegalArgumentException("ObservedAt is required");
        }
    }
}
```

Chuyển `ObservedAt ↔ Long` theo epoch millis:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ObservedAtWriteConverter
        implements Converter<ObservedAt, Long> {

    @Override
    public Long convert(ObservedAt source) {
        return source.value().toEpochMilli();
    }
}
```

```java
import java.time.Instant;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ObservedAtReadConverter
        implements Converter<Long, ObservedAt> {

    @Override
    public ObservedAt convert(Long source) {
        return new ObservedAt(Instant.ofEpochMilli(source));
    }
}
```

Đăng ký thêm hai converter này vào **cùng `CassandraCustomConversions`** đã dùng ở phần 9 nếu muốn áp dụng. Trong entity, property phải map tới cột **`bigint`** và phải đảm bảo mọi ứng dụng diễn giải nó là epoch **milliseconds**, không phải seconds. Nếu schema dùng `timestamp`, không được tự áp converter này lên cột mà không migration CQL.

**Lưu ý về Java record:** ví dụ `record` đòi JDK hỗ trợ. Với stack cũ, thay bằng class bất biến và constructor/getter. Cần kiểm Spring Data mapping/constructor handling khi dùng value object/record trong domain model.

## 13. Repository, Template và CQL trực tiếp: chọn công cụ theo ngữ nghĩa

### 13.1. Repository cho đọc/ghi một entity theo khóa chính

```java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerProfileRepository
        extends CassandraRepository<CustomerProfile, UUID> {
}
```

Sử dụng từ service:

```java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile load(UUID customerId) {
        return repository.findById(customerId)
            .orElseThrow(() ->
                new IllegalArgumentException("Profile not found"));
    }

    public CustomerProfile save(CustomerProfile profile) {
        return repository.save(profile);
    }
}
```

Repository dùng mapping metadata/custom conversions, nhưng:

- `save` không đồng nghĩa một ACID transaction như trong JPA.
- Không giả định save chỉ cập nhật trường vừa thay trong collection hoặc UDT.
- Không mặc định một entity có UDT/list được đọc/ghi toàn bộ mà không quan tâm latency/row size.
- Nếu Spring Data Cassandra schema không đúng với CQL thì cần sửa model/DDL, không đổ lỗi đơn thuần cho converter.
- Khi nhiều writer cập nhật cùng frozen UDT/collection, cần kiểm version/cạnh tranh và lựa chọn CQL mutation có điều kiện phù hợp.

### 13.2. `CassandraTemplate` cho thao tác có mapping mà linh hoạt hơn

Spring Boot có thể inject `CassandraTemplate`:

```java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfileTemplateService {

    private final CassandraTemplate template;

    public ProfileTemplateService(CassandraTemplate template) {
        this.template = template;
    }

    public CustomerProfile load(UUID id) {
        return template.selectOneById(id, CustomerProfile.class);
    }

    public CustomerProfile insert(CustomerProfile profile) {
        return template.insert(profile);
    }
}
```

Trước khi dùng code, xác nhận overload/return type `insert(...)` của bản Spring Data cụ thể. Các ví dụ ở đây hướng dẫn chọn abstraction và mapping; **không thay cho integration test về generated CQL**.

### 13.3. Khi cần CQL update phần tử

Để thay một key trong map mà không replace cả map, có thể dùng `CqlSession` do Spring Boot quản lý:

```java
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

@Service
public class ProfilePreferencesWriter {

    private final CqlSession session;
    private final PreparedStatement updateLanguage;

    public ProfilePreferencesWriter(CqlSession session) {
        this.session = session;
        this.updateLanguage = session.prepare(
            "UPDATE commerce.customer_profiles_by_id " +
            "SET preferences['language'] = ? " +
            "WHERE customer_id = ?");
    }

    public void setLanguage(UUID customerId, String language) {
        session.execute(updateLanguage.bind(language, customerId));
    }
}
```

**Điểm cần nhớ:** khi dùng **CqlSession trực tiếp**, `CassandraCustomConversions` không tự động chuyển đổi mọi domain object cho bạn. Phần bind phải cung cấp kiểu driver hiểu (ở đây hai `String/UUID` đơn giản). Nếu bind `CustomerStatus` domain enum trực tiếp, bạn cần chuyển sang stable code hoặc dùng mapper đúng, không mặc định custom Spring converter sẽ chạy qua low-level driver.

**Không nối untrusted input vào tên cột/table hoặc literal CQL**. Với value, sử dụng prepared/bound statement. Nếu query phức tạp liên quan collection/UDT và nhiều writer, test cả semantics và idempotency trước khi retry.

## 14. Mapping collection/UDT và hiệu năng cluster

Một ứng dụng có thể compile tốt và mapping không lỗi nhưng vẫn gây vấn đề production:

### 14.1. Collections lớn làm tăng I/O và tombstone

Bảng có một partition cho mỗi khách; nếu một profile có hàng chục nghìn keys trong `preferences`, mỗi lần load full entity có thể tốn memory và network. Nhiều thay đổi/xóa phần tử tạo tombstone; phụ thuộc compaction/TTL/repair và access pattern.

Đánh giá:

- Số phần tử/trường **p95/p99**, không chỉ trung bình.
- Bytes/profile, số row/cell, GC/heap của Java, page size nếu query nhiều rows.
- Tần suất thay thế toàn collection so với cập nhật phần tử.
- Số mutation/tombstone từ use case xóa/cập nhật.
- RF/CL, coordinator read/write latency và disk/compaction metrics.

### 14.2. Frozen UDT có thể làm tăng lost update

Nếu hai worker:

1. Cùng đọc `shipping_address` cũ.
2. Worker A thay `city` rồi ghi toàn UDT.
3. Worker B thay `postal_code` trên snapshot cũ rồi ghi toàn UDT.

kết quả cuối có thể chỉ giữ thay đổi của writer cuối theo timestamp; thay đổi của writer trước bị ghi đè. **Không dùng `@Frozen` chỉ vì mapping thuận tiện** khi use case đòi cập nhật từng field đồng thời.

### 14.3. Không nhầm CQL collection với domain aggregate vô hạn

Một domain `Customer` có `List<Order>` vô hạn không nhất thiết nên map thành `list<frozen<order>>` trong một CQL column. Trong Cassandra, tốt hơn có bảng `orders_by_customer` với clustering columns, giới hạn partition size và có pagination rõ ràng.

## 15. Quy trình migration khi thay schema hoặc cách chuyển đổi

### 15.1. Thêm enum state mới

Giả sử cần trạng thái `SUSPENDED("S")`:

1. Mở rộng enum và converter để reader hiểu `"S"` nhưng **chưa ghi** state này.
2. Chạy integration test với dữ liệu chứa cả code cũ/mới.
3. Deploy toàn bộ reader, worker, batch jobs và service liên quan.
4. Bật writer phát sinh `"S"` theo feature flag.
5. Theo dõi conversion errors, unknown codes, business metrics.
6. Giữ code cũ/alias nếu cần đọc dữ liệu lịch sử; không xóa cách diễn giải quá sớm.

Nếu đổi stable code đang được lưu (ví dụ `"A"` thành `"ACTIVE"`) phải có **dual-reader/dual-writer hoặc migration dữ liệu** rõ ràng, không sửa converter một bước rồi mặc định CQL đã đổi.

### 15.2. Chuyển từ enum ordinal sang text

Legacy schema `status_code int` muốn chuyển sang `status_code text`:

- Không đơn giản sửa `@CassandraType` hoặc Java converter mà không sửa CQL type.
- Xem xét tạo cột mới `status_code_v2 text` hoặc bảng version mới theo quy trình expand–migrate–contract.
- Reader mới hiểu cả cũ và mới trong giai đoạn chuyển, writer phát ra mã ổn định.
- Backfill theo partition key có checkpoint, giới hạn concurrency và idempotency.
- Sau khi đối soát và mọi code cũ đã rời, mới gỡ bỏ cột/đường cũ theo migration đã review.

### 15.3. Đổi field của UDT

Thêm `country_code` vào `postal_address` cũng cần chú ý:

- UDT dùng chung có thể phụ thuộc nhiều bảng.
- App cũ có thể rewrite frozen UDT, làm field mới mất giá trị.
- Schema agreement phải đạt trước khi code mới dùng field.
- Bản ghi cũ đọc field mới là `null`; đừng ép giá trị mặc định sai nghiệp vụ.
- Khi sửa CQL type hoặc frozen semantics, có thể cần field/table mới thay vì `ALTER` trực tiếp.

### 15.4. Chuẩn hóa timezone/precision

Nếu cột cũ dùng `LocalDateTime` nhưng team muốn `Instant`:

1. Xác định timezone mà dữ liệu cũ **thực sự mang ý nghĩa**. Không tự suy là UTC.
2. Kiểm những record nằm trong DST gap/overlap.
3. Backfill có chính sách xử lý record không thể xác định tức thời.
4. Giữ dữ liệu gốc/quy tắc chuyển đổi để audit.
5. Deploy reader/writer theo thứ tự, thử trên container/JVM timezone khác nhau.
6. Tránh chạy cùng lúc nâng Cassandra Server, đổi CL và migration thời gian nếu có thể.

**Version control giữ lịch sử DDL; custom converter là code trong một release cụ thể.** Muốn rollback app, phải bảo đảm phiên bản cũ **vẫn hiểu wire format** do phiên bản mới đã ghi.

## 16. Kiểm thử mapping: unit converter chưa đủ

### 16.1. Tầng unit

Kiểm riêng:

- Enum `CustomerStatus ↔ String` có round-trip.
- Unknown code gây kết quả theo policy đã định.
- `ObservedAt ↔ Long` ở giá trị 0, trước epoch, giới hạn và precision milliseconds.
- Null/empty/invalid values theo contract.
- Converter thread-safe, không giữ state dùng chung có thể thay đổi.

### 16.2. Tầng integration với Cassandra thật

Dùng test cluster/container có version gần production, migration CQL tương ứng; **không** chỉ mock `CassandraTemplate` rồi coi đã xong.

Các case tối thiểu:

| Case | Dữ liệu vào | Kiểm sau đọc lại |
| --- | --- | --- |
| `Set<String>` | Hai interests không trùng | Không sinh phần tử trùng, không giả định thứ tự |
| `List<String>` | Hai recent codes | Giữ thứ tự và đo khi append |
| `Map<String,String>` | `language=vi` | Update một key không mất các key khác |
| Frozen UDT | Street/city/postalCode | Round-trip đầy đủ |
| List frozen UDT | Hai địa chỉ | Nested type đúng và map được |
| Enum stable code | `ACTIVE` | Cassandra lưu `"A"`, Java đọc lại ACTIVE |
| Enum unknown | `"X"` viết bởi CQL | Reader fail/quarantine theo policy |
| `Instant` | Có nanosecond | So sánh theo millisecond |
| `LocalDate` | Ngày sinh | Không lệch ngày do timezone |
| `LocalTime` | 09:30 | Không tự sinh offset/ngày |
| Null vs empty | Set/list/map null/rỗng | Hành vi thực được ghi nhận; không đoán |
| Legacy migration | Cột mới nullable | App cũ/mới cùng đọc/ghi được theo kế hoạch |

### 16.3. Một integration test khung

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CustomerProfileMappingIntegrationTest {

    @Autowired
    CustomerProfileRepository repository;

    @Test
    void canReadWrittenProfile() {
        UUID id = UUID.randomUUID();

        CustomerProfile profile = new CustomerProfile();
        // Thiết lập customerId, interests, recentCodes, preferences,
        // shippingAddress, statusCode, joinedAt, dateOfBirth,
        // preferredContactTime và timezoneId qua setters.
        // Cần có migration schema và test Cassandra đang chạy.

        // Chỉ minh họa ý định:
        // repository.save(profile);
        // Optional<CustomerProfile> loaded = repository.findById(id);
        // assertTrue(loaded.isPresent());
        // assertEquals(CustomerStatus.ACTIVE, loaded.get().getStatusCode());
    }
}
```

Ví dụ là **khung test**, các dòng lưu/đọc được cố ý chú thích vì class `CustomerProfile` trong bài chưa trình bày getters/setters đầy đủ và không có test cluster thực. Trong dự án của bạn, hoàn thiện setters, tạo dữ liệu với `id`, chạy migration CQL ở test environment và **bỏ comment assertions** để xác minh round-trip thật. Đừng ghi vào cluster production từ unit/integration tests.

### 16.4. Kiểm bằng CQL độc lập với Java mapper

Nếu integration test dùng mapper ghi rồi chính mapper đọc, cùng một lỗi đối xứng có thể bị che. Hãy đọc raw CQL bằng `cqlsh` hoặc Java Driver `Row`:

```sql
SELECT customer_id, interests, recent_codes, preferences,
       shipping_address, backup_addresses,
       status_code, joined_at, date_of_birth,
       preferred_contact_time, timezone_id
FROM commerce.customer_profiles_by_id
WHERE customer_id = ?;
```

Kiểm raw `status_code='A'`, độ chính xác `timestamp`, UDT field names, list order và các collection values. Trong automation, dùng prepared statement với binding đúng; `?` ở trên là bind marker, **không phải literal để gõ trực tiếp vào `cqlsh`**.

## 17. Các lỗi thường gặp và quy trình điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `MappingException` không map được field | Java/CQL type khác, annotation thiếu, converter chưa đăng ký | Kiểm schema, entity và custom conversions |
| `Unknown type`/không tìm thấy UDT | `CREATE TYPE` chưa chạy, keyspace sai, schema chưa agreement | Chạy migration theo thứ tự, kiểm metadata |
| Đọc UDT ra `null` hoặc field null | CQL field mới, tên `@Column` lệch, dữ liệu cũ | Kiểm raw UDT, nullable và bản ứng dụng |
| `InvalidQuery` về frozen | Cố UPDATE field của frozen UDT/collection | Thay toàn frozen value hoặc thiết kế lại |
| Enum mới làm app cũ crash | Reader cũ chưa biết code mới | Expand reader trước, feature flag writer |
| Enum ordinal bị đổi nghĩa | Thêm/reorder constants | Migration sang stable text code |
| Mapping `CustomerStatus` ra tên enum thay vì code | Converter chưa được mapping infrastructure dùng | Kiểm `CassandraCustomConversions` bean/overrides |
| `LocalDateTime` lệch giờ giữa env | Default JVM timezone/Date conversion | Dùng `Instant` cho timestamp, test timezone |
| `Instant` mất micro/nanoseconds | CQL timestamp có millisecond precision | Chuẩn hóa/đổi mô hình dữ liệu theo yêu cầu |
| `LocalDate` lệch ngày | Chuyển sai qua instant/zone | Lưu CQL `date`, kiểm conversion |
| Collection update mất key/element khác | Repo save replace whole collection hoặc concurrency | CQL element mutation, CAS hoặc redesign |
| List bị append trùng sau timeout | Retry non-idempotent | Request ID/idempotency, không blind retry |
| Direct `CqlSession` bind enum thất bại | Custom Spring converter không tự chạy ở driver | Bind stable String code hoặc explicit codec |
| Memory/latency tăng khi load profile | Collection/UDT quá lớn, full entity read | Giới hạn collection, tạo bảng theo query |
| Test chạy nhưng production lỗi | RF/DC/schema/data/version không tương thích | Integration test cluster gần production, schema diff |

### 17.1. Phân loại lỗi theo tầng

```text
App startup / missing class?
  -> Spring Boot/Spring Data/Driver version, dependency graph.

CQL unknown keyspace/type/table?
  -> Schema migration, keyspace, UDT resolver, schema agreement.

Class mapped nhưng field sai?
  -> @Column, @UserDefinedType, @Frozen, @CassandraType.

Read/write conversion fail?
  -> @ReadingConverter/@WritingConverter, registration, unknown enum code.

Dữ liệu bị đổi nghĩa?
  -> Ordinal enum, timezone conversion, timestamp precision, null/empty.

Timeout/Unavailable?
  -> Cassandra RF/CL, hot partition, I/O, compaction, tombstone, retries.

Update collection bị mất dữ liệu?
  -> Whole-value overwrite, concurrency, mutation semantics, read-modify-write.
```

Đừng tăng timeout hoặc giảm CL để che lỗi mapping; ngược lại, đừng viết converter mới khi nguyên nhân là replica không đủ hoặc schema chưa triển khai.

## 18. Runbook triển khai một thay đổi mapping production

### Pha A — Trước khi viết/merge

1. Chốt CQL type/schema kỳ vọng với Java property và phương án frozen/non-frozen.
2. Kiểm dùng collection có giới hạn hay đang cố lưu quan hệ 1-n vô hạn.
3. Chốt policy enum stable code, unknown value và backward compatibility.
4. Chốt thời gian: instant, local date, local time, zone ID, precision và DST.
5. Viết converter có unit tests hai chiều và integration tests raw CQL.
6. Chốt Spring Boot/Spring Data/Driver/Server compatibility; không dùng `latest` không kiểm thử.
7. Đưa migration CQL vào Git với ID/checksum, không cho app tự sửa schema production.

### Pha B — Staging

- Chạy migration keyspace/UDT/table/cột đúng thứ tự, đợi schema agreement.
- Chạy round-trip collection/UDT, enum code và time ở nhiều timezone JVM.
- Thử app cũ/mới song song trong rolling deploy.
- Thử retry timeout khi append list/frozen UDT update để tìm thao tác chưa idempotent.
- Thử đọc dữ liệu đã ghi trước migration; kiểm null/unknown/new field.
- Đo p95/p99, row/partition size, tombstones, GC/heap, compaction và disk.

### Pha C — Rollout

- Triển khai **reader biết schema/code mới trước** khi writer bắt đầu ghi format mới.
- Bật writer bằng feature flag/canary khi phù hợp.
- Theo dõi mapping/conversion exceptions, unknown codes, latency và data correctness.
- Nếu cần backfill, dùng job theo partition key, checkpoint, bounded concurrency và đối soát.
- Không đồng thời đổi partition key, RF, compaction strategy và mapping nếu không có lý do/plan riêng.

### Pha D — Hoàn tất

- Xác nhận mọi service/worker/batch job hỗ trợ wire format mới.
- Xác nhận schema diff với Git migration và trạng thái cluster.
- Xác nhận dữ liệu cũ/new được đọc đúng, converter và time policy nhất quán.
- Ghi runbook rollback: **version cũ có thể đọc dữ liệu mới không?**
- Chỉ contract/drop field/format cũ sau khi hoàn tất chuyển đổi và backup có thể restore.

## 19. Bài tập tình huống

Một service Spring Boot lưu hồ sơ Cassandra như schema trong bài, có Java model `CustomerProfile` và UDT `PostalAddress`.

### Bài 1 — Collection

Một developer muốn lưu toàn bộ lịch sử 2 triệu order IDs trong `List<UUID> orders` của mỗi profile để API trả trang theo thời gian.

1. Vì sao điều này không phù hợp Cassandra?
2. Thiết kế lại bảng thế nào để truy vấn theo customer ID và thời gian?
3. Page size có giải quyết được vấn đề nếu vẫn lưu toàn bộ trong một collection không?
4. Tại sao retry lệnh append list sau `WriteTimeout` là rủi ro?

**Gợi ý:** bảng `orders_by_customer` với partition/clustering key phù hợp, có thể bucket. Page size không thay mô hình collection lớn; append có thể sinh duplicate khi retry.

### Bài 2 — Frozen UDT

Hai worker đọc cùng `shipping_address` frozen. Worker A đổi city, worker B đổi postal code rồi cả hai lưu.

1. Vì sao thay đổi có thể bị mất?
2. Có cách CQL nào update từng field của **frozen UDT** như với map non-frozen không?
3. Nếu nghiệp vụ đòi cập nhật concurrent independent fields, nên đổi mô hình thế nào?

**Gợi ý:** frozen là một giá trị, replace cả object; cân nhắc non-frozen UDT nếu version/use case cho phép hoặc tách cột, CAS/version/concurrency policy.

### Bài 3 — Enum ordinal

Legacy table `status_code int`; enum cũ `ACTIVE, PAUSED, CLOSED`. Bản mới chèn `PENDING` ở đầu.

1. Giá trị `1` bị đổi nghĩa thế nào?
2. Vì sao unit test của converter mới có thể vẫn pass trong khi dữ liệu cũ sai?
3. Đề xuất trình tự migration sang stable code text.

**Gợi ý:** test phải gồm dữ liệu lịch sử raw CQL; dùng expand reader, cột mới, backfill và đổi writer, không chỉ enum Java.

### Bài 4 — Thời gian

CQL `timestamp` lưu `2026-11-21T02:30:00.123Z`. Java muốn hiển thị cho người dùng tại `Asia/Ho_Chi_Minh` và người dùng đặt “nhắc tôi 09:30 mỗi ngày”.

1. Tại sao cả hai yêu cầu không dùng cùng một `Instant`?
2. Chọn Java/CQL types nào cho thời điểm phát sinh và giờ nhắc hằng ngày?
3. Giá trị `Instant` có nanosecond khi round-trip qua CQL timestamp còn chính xác đến đâu?
4. Với múi giờ có DST, phải thêm quyết định nghiệp vụ gì?

**Gợi ý:** event timestamp là `Instant`; lịch hằng ngày dùng `LocalTime + ZoneId` và quy tắc cho ngày/giờ bị lặp hoặc không tồn tại. CQL timestamp precision milliseconds.

### Bài 5 — Converter không chạy

Code đã viết `CustomerStatusWriteConverter`, nhưng raw CQL vẫn có `'ACTIVE'` thay vì `'A'`.

1. Converter có cần được đăng ký không?
2. Làm sao chứng minh `MappingCassandraConverter` thực dùng converter?
3. Nếu code ghi trực tiếp qua `CqlSession`, converter Spring có tự chạy không?
4. Cần kiểm gì trong integration test?

**Gợi ý:** đăng ký `CassandraCustomConversions`/override đúng context; đọc/ghi qua repository/Template và raw CQL đối chiếu; Driver thấp hơn không dùng converter Spring một cách tự động.

### Bài 6 — Migration tương thích

Team thêm `country_code` vào UDT frozen và deploy Java writer mới trước các reader cũ.

1. Reader cũ có thể gây lỗi nào?
2. App cũ rewrite frozen UDT có thể làm gì với field mới?
3. Đề xuất thứ tự release an toàn và test rollback.

**Gợi ý:** mở rộng reader trước writer, schema agreement, nullable old data, frozen whole-value rewrite và contract sau cùng.

## 20. Checklist cuối bài

- [ ] Đã chọn CQL `list/set/map` phù hợp và giới hạn kích thước collection theo workload.
- [ ] Không dùng collection như bảng lịch sử 1-n vô hạn; đã thiết kế bảng theo partition/clustering key.
- [ ] Entity có `@Table`, `@PrimaryKey`, `@Column` khớp DDL.
- [ ] UDT có `@UserDefinedType` và keyspace/type name nhất quán.
- [ ] `@Frozen` phù hợp CQL, nhất là UDT nằm trong list/map/set.
- [ ] Đã phân biệt cập nhật phần tử CQL với thay toàn collection/UDT qua repository.
- [ ] Xử lý null, empty, tombstone và concurrent writes bằng integration tests.
- [ ] Enum không dùng ordinal mới nếu chưa có lý do legacy rõ ràng và migration plan.
- [ ] Stable code enum có read/write converters, unknown-code policy và test code cũ/mới.
- [ ] Converter đã được đăng ký với `CassandraCustomConversions`/context thật.
- [ ] Biết khác biệt global converter và per-property converter; không áp converter native-wide gây sai cột khác.
- [ ] Không nhầm `@CassandraType` với business converter; Java/CQL types thống nhất.
- [ ] `timestamp` dùng `Instant` cho event; không lưu timezone gốc trong `timestamp` mà không có cột khác.
- [ ] Đã tính precision milliseconds của Cassandra timestamp khi kiểm equality round-trip.
- [ ] `date`/`time` dùng `LocalDate`/`LocalTime` theo đúng ý nghĩa lịch, không áp offset vô cớ.
- [ ] Nếu giờ địa phương phụ thuộc timezone, lưu `ZoneId`/timezone ID và giải quyết DST.
- [ ] Không tự suy CQL `duration` tương đương hoàn toàn `java.time.Duration`.
- [ ] Đã kiểm Spring Boot/Spring Data/Java Driver/Cassandra Server/JDK version compatibility.
- [ ] Production schema do migration Git quản lý, không tự recreate/drop khi ứng dụng khởi động.
- [ ] Unit test converter và integration test repository/Template/raw CQL đều đạt.
- [ ] Đã thử app cũ/mới trong giai đoạn expand–migrate–contract.
- [ ] Đã đo performance/GC/tombstone và lỗi mapping dưới tải thực tế, không chỉ kiểm code compile.

## 21. Tài liệu tham khảo chính thức

Các tài liệu sau mô tả mapping, converter và cấu hình Spring Boot/Spring Data Cassandra. Hãy chọn **phiên bản tương ứng dự án**, không áp một API từ tài liệu mới cho dự án đã khóa version cũ:

- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `MappingCassandraConverter`, `@Table`, `@Column`, `@CassandraType`, `@UserDefinedType` và `@Frozen`.
- [Spring Data Cassandra — Custom Conversions](https://docs.spring.io/spring-data/cassandra/reference/cassandra/converters.html): `@ReadingConverter`, `@WritingConverter`, đăng ký `CassandraCustomConversions`.
- [Spring Data Cassandra — Property-based Converters](https://docs.spring.io/spring-data/cassandra/reference/cassandra/property-converters.html): per-property conversion và `@ValueConverter` khi phiên bản hỗ trợ.
- [Spring Data Cassandra — CassandraType Javadoc](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/mapping/CassandraType.html): `type`, `typeArguments` và `userTypeName`.
- [Spring Boot — Working with NoSQL Technologies / Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter, `spring.cassandra.*`, `CqlSession` và `CassandraTemplate`.

**Kết luận:** Mapping collection, UDT, enum, thời gian và custom converter trong Spring Data Cassandra là **một phần của hợp đồng dữ liệu phân tán**, không chỉ là annotation để Java biên dịch. `List/Set/Map` cần được giới hạn và cập nhật đúng ngữ nghĩa; `frozen UDT` cần hiểu hành vi replace và concurrent writes; enum nên có **stable code** nếu dữ liệu tồn tại lâu; thời gian phải phân biệt **Instant, LocalDate, LocalTime, ZoneId**; converter phải đăng ký đúng chiều và được kiểm tra bằng raw CQL. Chỉ khi **schema CQL, Java mapping, quy trình migration và integration tests** khớp nhau thì repository/service mới đáng tin trên Cassandra production.
