# Ánh xạ khóa ghép, static column, UDT và collection

Bài thực hành này xây dựng một kho dữ liệu đơn hàng trên **Apache Cassandra** bằng **Spring Data Cassandra**. Ta sẽ tạo một bảng đọc theo tenant và tháng, định nghĩa **khóa ghép** (*composite primary key*), sử dụng **static column** cho thông tin chung của partition, ánh xạ **UDT** (*User-Defined Type*) cho địa chỉ giao hàng, và lưu một số thuộc tính nhỏ bằng **collection** (`set`, `list`, `map`).

Bài thuộc chương **Bài thực hành** của module **SPRING_DATA_CASSANDRA**. Mục tiêu không chỉ là làm cho entity lưu/đọc được: bạn cần hiểu chính xác dữ liệu được phân vùng, giá trị nào là thuộc tính của cả partition, vì sao UDT có thể cần `frozen`, và khi nào collection gây khó khăn về truy vấn, kích thước bản ghi hoặc hiệu năng. Phần triển khai dùng `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@UserDefinedType`, `@Table`, `CassandraRepository`, `CassandraTemplate` và CQL.

## 1. Kết quả cần đạt

Hoàn thành bài, bạn có thể:

1. Thiết kế bảng Cassandra theo truy vấn **“lấy các đơn của một tenant trong một tháng, mới nhất trước”** và phân biệt partition key với clustering columns.
2. Ánh xạ khóa ghép sang một lớp Java có `equals()` và `hashCode()` đúng; dùng khóa đó với `CassandraRepository`.
3. Ghi và đọc **static column**; chứng minh cập nhật giá trị static ảnh hưởng đến các hàng cùng partition.
4. Định nghĩa UDT trong CQL, ánh xạ bằng `@UserDefinedType` và hiểu tác động của `frozen` đến cách cập nhật.
5. Ánh xạ `set<text>`, `list<text>`, `map<text,text>`; thử thao tác thêm/thay đổi phần tử và quan sát rủi ro của collection lớn.
6. Viết truy vấn có đầy đủ partition key, dùng paging/giới hạn dữ liệu đúng chỗ, và kiểm tra bằng Cassandra thật thay vì chỉ mock repository.

### Bối cảnh

Một hệ thống đơn hàng nhiều tenant có màn hình **“Đơn hàng tháng 11/2026”**. Với mỗi đơn cần lưu:

- `tenant_id`, `month_bucket`, `created_at`, `order_id`;
- tên hiển thị tenant tại partition trong tháng;
- địa chỉ giao hàng (đường, thành phố, mã bưu chính);
- tập nhãn không trùng (`tags`);
- danh sách mã sản phẩm có thứ tự (`item_skus`);
- tập thuộc tính mở rộng nhỏ (`attributes`).

Ứng dụng cần lấy đơn theo **tenant + tháng**, sắp xếp theo thời gian mới nhất. Đây là **access pattern quyết định khóa**. Nếu sau này cần tìm một đơn chỉ bằng `order_id`, ta phải thiết kế thêm read model/bảng tương ứng hoặc thay hợp đồng truy vấn; không giả định Cassandra sẽ quét toàn bộ dữ liệu hiệu quả như một cơ sở dữ liệu quan hệ.

```text
GET /tenants/{tenantId}/orders?month=2026-11
                         |
                         v
              OrderQueryService
                         |
                         v
        OrderByTenantMonthRepository
                         |
                         v
       Partition (tenant_id, month_bucket)
          +---------------------------+
          | tenant_display_name static|
          +---------------------------+
          | created_at DESC, order_id |
          | shipping_address (UDT)    |
          | tags / item_skus / map    |
          +---------------------------+
```

Trong ứng dụng thực tế, `tenantId` phải lấy từ ngữ cảnh đã xác thực/ủy quyền hoặc được đối chiếu membership; việc đưa tenant vào partition key **không tự tạo cơ chế phân quyền**.

## 2. Môi trường thực hành

Ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Data Cassandra 4.x** và một Cassandra tương thích. Bạn cần một Cassandra chạy được (local/Docker/Testcontainers hoặc môi trường lab), công cụ `cqlsh` và kết nối tới đúng keyspace.

Dependency Gradle cơ bản (chọn phiên bản bằng BOM của Spring Boot đang sử dụng):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:cassandra'
}
```

Một cấu hình kết nối điển hình trong `application.yml`:

```yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: practice_cassandra
    schema-action: none
```

Tên data center, cổng và keyspace phải khớp môi trường; `datacenter1` chỉ là ví dụ cho cluster local phù hợp. Ở đây **schema được tạo trước bằng CQL**, vì vậy không trông chờ ứng dụng tự sinh DDL. Nếu Cassandra bật authentication/TLS, cấu hình driver và secrets theo yêu cầu môi trường; không đặt mật khẩu thật trong tài liệu hoặc source code.

Trong production, nên quản lý schema theo quy trình migration/review tương thích với Cassandra. Các lệnh `CREATE` của bài chỉ dùng cho môi trường thực hành.

## 3. Tạo keyspace, UDT và bảng bằng CQL

### 3.1. Keyspace lab

Trong `cqlsh` của Cassandra một node phục vụ bài lab:

```sql
CREATE KEYSPACE IF NOT EXISTS practice_cassandra
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE practice_cassandra;
```

**Giới hạn:** `SimpleStrategy`/RF=1 dùng để học và kiểm thử chức năng trên một node. Cụm production nhiều node/datacenter thường cần `NetworkTopologyStrategy` và replication factor thích hợp, sau đó chọn consistency theo yêu cầu dữ liệu và availability. RF=1 không thể chứng minh quorum/failover.

### 3.2. UDT cho địa chỉ

```sql
CREATE TYPE IF NOT EXISTS shipping_address (
    street      text,
    city        text,
    postal_code text
);
```

UDT là kiểu dữ liệu có các field cố định, thích hợp cho một **value object** nhỏ. Khác với bảng riêng, UDT không tự có partition key, không được truy vấn độc lập bằng `SELECT` như một bảng.

### 3.3. Bảng với khóa ghép, static, frozen UDT và collection

```sql
CREATE TABLE IF NOT EXISTS orders_by_tenant_month (
    tenant_id           uuid,
    month_bucket        text,
    created_at          timestamp,
    order_id            uuid,

    tenant_display_name text static,
    shipping_address    frozen<shipping_address>,
    tags                set<text>,
    item_skus           list<text>,
    attributes          map<text, text>,

    PRIMARY KEY (
        (tenant_id, month_bucket),
        created_at,
        order_id
    )
)
WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
```

Giải thích từng phần:

| Cột/nhóm cột | Loại | Ý nghĩa |
| --- | --- | --- |
| `tenant_id` + `month_bucket` | **Composite partition key** | Định vị các đơn của một tenant trong một tháng. |
| `created_at` | Clustering column thứ nhất | Tổ chức dữ liệu mới trước cũ **trong cùng partition**. |
| `order_id` | Clustering column thứ hai | Phân biệt hai đơn cùng `created_at`, có thứ tự xác định khi timestamp bằng nhau. |
| `tenant_display_name` | **Static column** | Một giá trị chung cho toàn bộ partition `(tenant_id, month_bucket)`. |
| `shipping_address` | `frozen<shipping_address>` | Một value object UDT được lưu và cập nhật như một giá trị nguyên khối. |
| `tags` | `set<text>` | Tập phần tử duy nhất, không bảo đảm thứ tự nghiệp vụ. |
| `item_skus` | `list<text>` | Danh sách có thứ tự, cho phép trùng giá trị. |
| `attributes` | `map<text,text>` | Các cặp khóa–giá trị nhỏ, không dùng làm hệ thống tìm kiếm không giới hạn. |

### Bẫy cú pháp khóa ghép

Hai kiểu khai báo sau có ngữ nghĩa **khác nhau**:

```sql
-- Một partition key gồm hai thành phần: tenant + tháng.
PRIMARY KEY ((tenant_id, month_bucket), created_at, order_id)

-- Chỉ tenant là partition key; month_bucket trở thành clustering column.
PRIMARY KEY (tenant_id, month_bucket, created_at, order_id)
```

Với cú pháp thứ hai, toàn bộ lịch sử đơn của tenant có thể tập trung vào **một partition rất lớn**. Mục tiêu của bucket tháng là hạn chế độ lớn partition, nên **cặp ngoặc lồng nhau** bao quanh các partition-key columns trong CQL có ý nghĩa rất quan trọng.

**Cảnh báo dữ liệu:** bucket theo tháng chưa chắc đủ cho tenant có tốc độ ghi rất cao. Nếu một tenant tạo hàng triệu đơn trong một tháng, cần cân nhắc bucket ngày/giờ hoặc một chiến lược phân vùng khác dựa trên số hàng, kích thước và access pattern thực tế.

## 4. Tạo dữ liệu mẫu để quan sát

Các UUID và thời gian dưới đây chỉ dùng để thử. Trong `cqlsh`, sau khi `USE practice_cassandra`:

```sql
INSERT INTO orders_by_tenant_month (
    tenant_id,
    month_bucket,
    created_at,
    order_id,
    tenant_display_name,
    shipping_address,
    tags,
    item_skus,
    attributes
)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11',
    '2026-11-25T09:00:00Z',
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1,
    'Tenant Alpha',
    {street: '12 Nguyen Hue', city: 'Ho Chi Minh City',
     postal_code: '700000'},
    {'priority', 'gift'},
    ['SKU-001', 'SKU-002'],
    {'channel': 'web', 'currency': 'VND'}
);

INSERT INTO orders_by_tenant_month (
    tenant_id, month_bucket, created_at, order_id,
    shipping_address, tags, item_skus, attributes
)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11',
    '2026-11-25T08:00:00Z',
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2,
    {street: '8 Le Loi', city: 'Ho Chi Minh City',
     postal_code: '700000'},
    {'fragile'},
    ['SKU-003'],
    {'channel': 'mobile'}
);

INSERT INTO orders_by_tenant_month (
    tenant_id, month_bucket, created_at, order_id,
    tenant_display_name, tags, item_skus
)
VALUES (
    22222222-2222-2222-2222-222222222222,
    '2026-11',
    '2026-11-25T07:00:00Z',
    bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1,
    'Tenant Beta',
    {'standard'},
    ['SKU-004']
);
```

Ở bản ghi thứ hai của tenant Alpha, ta **không ghi lại static column**. Vì hai hàng cùng partition, truy vấn bảng vẫn hiển thị `tenant_display_name = 'Tenant Alpha'` cho cả hai. Nếu hai hàng cùng partition ghi các giá trị static khác nhau, giá trị cuối cùng được Cassandra phân giải theo quy tắc timestamp ghi; không có static value riêng cho từng hàng.

Truy vấn kiểm tra:

```sql
SELECT tenant_id, month_bucket, created_at, order_id,
       tenant_display_name, shipping_address,
       tags, item_skus, attributes
FROM orders_by_tenant_month
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11';
```

Kỳ vọng: **hai hàng** của Alpha, `created_at 09:00Z` trước `08:00Z`; cả hai nhìn thấy cùng `tenant_display_name`. Không thấy dữ liệu của Beta vì truy vấn có **đủ partition key**.

## 5. Ánh xạ composite primary key với Spring Data Cassandra

Spring Data Cassandra cần biết cột nào nằm trong partition key, cột nào là clustering key và thứ tự của chúng. Dùng `@PrimaryKeyClass` cho kiểu khóa tổng hợp, `@PrimaryKeyColumn` cho từng trường.

### 5.1. Lớp khóa

```java
package example.cassandra.practice;

import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderMonthKey implements Serializable {

    @PrimaryKeyColumn(
        name = "tenant_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private UUID orderId;

    public OrderMonthKey() {}

    public OrderMonthKey(
            UUID tenantId, String monthBucket,
            Instant createdAt, UUID orderId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.monthBucket = Objects.requireNonNull(monthBucket);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.orderId = Objects.requireNonNull(orderId);
    }

    public UUID getTenantId() { return tenantId; }
    public String getMonthBucket() { return monthBucket; }
    public Instant getCreatedAt() { return createdAt; }
    public UUID getOrderId() { return orderId; }

    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }
    public void setMonthBucket(String monthBucket) {
        this.monthBucket = monthBucket;
    }
    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
    public void setOrderId(UUID orderId) { this.orderId = orderId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderMonthKey key)) return false;
        return Objects.equals(tenantId, key.tenantId)
            && Objects.equals(monthBucket, key.monthBucket)
            && Objects.equals(createdAt, key.createdAt)
            && Objects.equals(orderId, key.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
            tenantId, monthBucket, createdAt, orderId);
    }
}
```

**Giải thích:**

- `type = PARTITIONED` đánh dấu hai thành phần partition key; `type = CLUSTERED` đánh dấu hai clustering columns.
- `ordinal` phản ánh thứ tự định nghĩa khóa; `ordering` phải tương thích `CLUSTERING ORDER BY` trong schema.
- `equals()`/`hashCode()` quan trọng khi khóa được dùng trong repository, cache, tập hợp Java hoặc unit test.
- Constructor không tham số và getter/setter giúp mapping theo cơ chế đối tượng mutable. Nếu chọn kiểu bất biến, cần cấu hình constructor mapping phù hợp thay vì xóa setters một cách tùy ý.
- Không tạo `monthBucket` từ múi giờ hệ thống ngẫu nhiên. Trong ví dụ, quy ước bucket là **tháng UTC**; logic tạo key phải đồng nhất giữa ghi và đọc.

### 5.2. UDT dưới dạng value object

```java
package example.cassandra.practice;

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

    public ShippingAddress() {}

    public ShippingAddress(
            String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }

    public void setStreet(String street) { this.street = street; }
    public void setCity(String city) { this.city = city; }
    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
```

Tên `shipping_address` trong `@UserDefinedType` phải khớp tên UDT đã tạo trong keyspace. Kiểu Java `ShippingAddress` được Spring Data Cassandra converter ánh xạ với UDT theo metadata của schema. Nếu đổi tên field trong Java mà quên `@Column("postal_code")`, dữ liệu có thể đọc sai hoặc mapping lỗi.

UDT là **giá trị có cấu trúc**, hữu ích khi các trường thường được đọc/ghi cùng nhau. Vì cột bảng khai báo `frozen<shipping_address>`, mỗi lần thay địa chỉ nên thay **toàn bộ UDT**. Không mong cập nhật trực tiếp `shipping_address.city` như một cột con độc lập của frozen UDT.

### 5.3. Entity chứa static column, UDT và ba collection

```java
package example.cassandra.practice;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_tenant_month")
public class OrderByTenantMonth {

    @PrimaryKey
    private OrderMonthKey key;

    @Column("tenant_display_name")
    private String tenantDisplayName;

    @Column("shipping_address")
    private ShippingAddress shippingAddress;

    @Column("tags")
    private Set<String> tags;

    @Column("item_skus")
    private List<String> itemSkus;

    @Column("attributes")
    private Map<String, String> attributes;

    public OrderByTenantMonth() {}

    public OrderMonthKey getKey() { return key; }
    public void setKey(OrderMonthKey key) { this.key = key; }

    public String getTenantDisplayName() { return tenantDisplayName; }
    public void setTenantDisplayName(String tenantDisplayName) {
        this.tenantDisplayName = tenantDisplayName;
    }

    public ShippingAddress getShippingAddress() {
        return shippingAddress;
    }
    public void setShippingAddress(ShippingAddress shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> tags) { this.tags = tags; }

    public List<String> getItemSkus() { return itemSkus; }
    public void setItemSkus(List<String> itemSkus) {
        this.itemSkus = itemSkus;
    }

    public Map<String, String> getAttributes() { return attributes; }
    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }
}
```

Lưu ý quan trọng về `tenantDisplayName`: nó được ánh xạ như một property để **đọc giá trị**, nhưng CQL schema quyết định đây là **static column**. Nếu lưu entity có field static `null` hoặc giá trị khác nhau trên nhiều hàng cùng partition, cần kiểm tra CQL thực tế của thao tác save để tránh tình cờ xóa/ghi đè static value. Trong ứng dụng thật, thường nên có **đường cập nhật static riêng** do service kiểm soát, thay vì để mỗi lần save đơn tùy ý thay đổi tên tenant.

## 6. Repository và lớp service cho bài thực hành

### 6.1. Repository

```java
package example.cassandra.practice;

import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface OrderByTenantMonthRepository
        extends CassandraRepository<OrderByTenantMonth, OrderMonthKey> {

    @Query("""
        SELECT * FROM orders_by_tenant_month
        WHERE tenant_id = ?0
          AND month_bucket = ?1
        """)
    List<OrderByTenantMonth> findInMonth(
        UUID tenantId, String monthBucket);
}
```

`CassandraRepository` cung cấp các thao tác theo **khóa chính đầy đủ**: `save`, `findById`, `deleteById`. Phương thức `findInMonth` có câu CQL cụ thể theo partition key và sẽ trả nhiều hàng **trong một partition**. Dùng `List` chỉ phù hợp với tập kết quả có quy mô nhỏ và đã được khống chế; với dữ liệu lớn, cần bổ sung giới hạn truy vấn và **paging state**.

Nếu muốn học query derivation, có thể thử tự khai báo phương thức phù hợp với các property của embedded key, nhưng phải **kiểm tra CQL thật** để chắc rằng query hỗ trợ schema. `@Query` ở bài này giúp thấy rõ điều kiện tenant và tháng.

### 6.2. Tạo đơn mới với composite key

Đoạn service sau minh họa cách dựng key từ tenant và `Instant`:

```java
package example.cassandra.practice;

import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class OrderPracticeService {

    private final OrderByTenantMonthRepository repository;

    public OrderPracticeService(
            OrderByTenantMonthRepository repository) {
        this.repository = repository;
    }

    public OrderMonthKey create(
            UUID authorizedTenantId,
            Instant createdAt,
            ShippingAddress address,
            Set<String> tags,
            List<String> itemSkus,
            Map<String, String> attributes) {

        if (authorizedTenantId == null || createdAt == null) {
            throw new IllegalArgumentException(
                "Tenant và createdAt là bắt buộc");
        }

        String bucket = YearMonth.from(
            createdAt.atZone(ZoneOffset.UTC)).toString();

        OrderMonthKey key = new OrderMonthKey(
            authorizedTenantId,
            bucket,
            createdAt,
            UUID.randomUUID());

        OrderByTenantMonth row = new OrderByTenantMonth();
        row.setKey(key);
        row.setShippingAddress(address);
        row.setTags(tags);
        row.setItemSkus(itemSkus);
        row.setAttributes(attributes);

        // Demo: không tự cấp tên static mới khi tạo từng đơn.
        // Thao tác static nên có đường cập nhật riêng được kiểm soát.
        repository.save(row);
        return key;
    }
}
```

**Điều kiện để dùng service trong production:** `authorizedTenantId` phải do tầng authentication/authorization cấp hoặc kiểm chứng, không lấy từ body mà client tự điền. Với `repository.save`, nên kiểm tra cách phiên bản Spring Data đang dùng phát CQL khi property static null; nếu save ghi null vào static, hãy tách entity/đường ghi hoặc cấu hình write strategy phù hợp để tránh xóa dữ liệu chung của partition. Phần thực hành static ở bước 7 dùng CQL cập nhật tường minh.

Một điểm khác cần kiểm tra là logic chọn `month_bucket` theo UTC. Nếu nghiệp vụ phân nhóm theo ngày/tháng địa phương của tenant, phải đặt timezone trong hợp đồng dữ liệu và tạo bucket nhất quán ở tất cả điểm ghi/đọc.

### 6.3. Đọc bằng khóa chính

```java
OrderMonthKey key = new OrderMonthKey(
    tenantId,
    "2026-11",
    Instant.parse("2026-11-25T09:00:00Z"),
    orderId);

Optional<OrderByTenantMonth> result =
    repository.findById(key);
```

Đây là lookup theo **đủ khóa chính**, khác với lấy một trang đơn hàng trong tháng (chỉ cần composite partition key và giới hạn). Không nên dùng `findAll()` để phục vụ màn hình danh sách tenant: phương thức này không tự áp dụng tenant filter và có thể rất tốn kém khi dữ liệu lớn.

## 7. Thực hành static column: giá trị chung cho partition

Static column thuộc về **partition**, không thuộc về từng clustering row. Với khóa `((tenant_id, month_bucket), created_at, order_id)`, giá trị `tenant_display_name` được chia sẻ bởi mọi đơn trong cùng tenant và tháng.

### 7.1. Cập nhật static mà không chỉ định clustering key

```sql
UPDATE orders_by_tenant_month
SET tenant_display_name = 'Alpha Vietnam'
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11';
```

Không cần `created_at` hay `order_id` vì đang cập nhật thuộc tính **của partition**. Kiểm tra:

```sql
SELECT created_at, order_id, tenant_display_name
FROM orders_by_tenant_month
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11';
```

Cả hai đơn của Alpha trong tháng đều thấy tên mới. Đơn Beta không bị ảnh hưởng vì thuộc partition khác. Nếu Alpha có dữ liệu trong tháng khác, static value ở partition tháng đó **không tự thay đổi**.

### 7.2. Đường cập nhật bằng Java Driver

Để tránh phụ thuộc vào cách `save` xử lý các field null, có thể dùng prepared statement cập nhật static một cách rõ ràng:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

public final class TenantLabelWriter {

    private final CqlSession session;
    private final PreparedStatement updateLabel;

    public TenantLabelWriter(CqlSession session) {
        this.session = session;
        this.updateLabel = session.prepare("""
            UPDATE orders_by_tenant_month
            SET tenant_display_name = ?
            WHERE tenant_id = ?
              AND month_bucket = ?
            """);
    }

    public void renameMonthPartition(
            UUID authorizedTenantId,
            String monthBucket,
            String newLabel) {

        if (authorizedTenantId == null ||
                monthBucket == null ||
                newLabel == null || newLabel.isBlank()) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }

        session.execute(updateLabel.bind(
            newLabel, authorizedTenantId, monthBucket));
    }
}
```

Trong mã thực tế, service phải xác minh người gọi có quyền đổi tên tenant. Prepared statement bảo vệ cách truyền dữ liệu, **không tự bảo đảm quyền**. Nếu thao tác đổi tên tenant cần áp dụng cho **mọi tháng**, phải thiết kế nơi lưu tên chuẩn hoặc cơ chế cập nhật các partition liên quan; static không phải biến toàn cục của tenant.

### 7.3. Khi nào không nên dùng static?

Không dùng static để lưu **địa chỉ giao hàng của từng đơn**: các đơn cùng tenant/tháng có thể có địa chỉ khác nhau, và static sẽ ghi đè một giá trị chung. Cũng không dùng static để lưu một “order status” riêng cho từng `order_id`.

Static hữu ích khi giá trị **bất biến hoặc thực sự chung trong partition**, chẳng hạn snapshot tên tenant hay cấu hình của bucket. Phải xác nhận phạm vi “chung” chính xác là `(tenant_id, month_bucket)`, không phải chỉ `tenant_id`.

## 8. Thực hành UDT và frozen semantics

### 8.1. Đọc UDT bằng Spring Data

Khi đọc hàng Alpha đầu tiên bằng repository, `getShippingAddress()` trả đối tượng `ShippingAddress` có ba field. Ví dụ:

```java
OrderByTenantMonth order =
    repository.findById(existingKey).orElseThrow();

ShippingAddress address = order.getShippingAddress();
System.out.println(address.getCity());
```

Kiểm tra xem Spring mapping chuyển `postal_code` → `postalCode` đúng nhờ `@Column("postal_code")` và phân biệt `null` với giá trị rỗng.

### 8.2. Thay toàn bộ địa chỉ frozen

CQL update một hàng cụ thể:

```sql
UPDATE orders_by_tenant_month
SET shipping_address = {
    street: '99 Dong Khoi',
    city: 'Ho Chi Minh City',
    postal_code: '700000'
}
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-25T09:00:00Z'
  AND order_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1;
```

Vì `shipping_address` khai báo **`frozen<shipping_address>`**, thao tác này thay toàn bộ value UDT. Nếu chỉ muốn đổi `city` mà không mất các field còn lại, ứng dụng phải chuẩn bị value UDT mới có đủ field cần giữ và cập nhật nó như một đơn vị. Trong trường hợp cần cập nhật từng field độc lập với tần suất cao, cân nhắc mô hình khác (các cột thường, kiểu UDT không frozen khi được hỗ trợ phù hợp, hoặc bảng riêng), cùng chi phí và ràng buộc nhất quán tương ứng.

### 8.3. UDT không phải bảng con

UDT phù hợp cho một nhóm trường nhỏ, có schema và thường được đọc cùng nhau. Nó không có partition riêng, không có foreign key và không tự động tạo index cho từng field. Nếu hệ thống cần tìm “mọi đơn có `shipping_address.city='...'`”, không nên suy ra có thể lọc hiệu quả trên trường UDT theo cách SQL quan hệ. Hãy thiết kế **bảng đọc theo thành phố** hoặc indexing/search phù hợp với Cassandra phiên bản đang dùng, rồi đo thực tế.

## 9. Thực hành collection: set, list, map

Cassandra hỗ trợ nhiều collection nhưng chúng phù hợp nhất với **tập phần tử nhỏ và có giới hạn**. Spring Data Cassandra ánh xạ tự nhiên sang `Set<String>`, `List<String>`, `Map<String,String>` trong entity.

### 9.1. Set: nhãn duy nhất

```sql
UPDATE orders_by_tenant_month
SET tags = tags + {'vip', 'gift'}
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-25T09:00:00Z'
  AND order_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1;
```

`set` không lưu hai bản sao của một giá trị như `'gift'`, đồng thời **không bảo đảm thứ tự hiển thị nghiệp vụ**. Nếu UI cần thứ tự do người dùng sắp xếp, `set` không phải lựa chọn đúng.

### 9.2. List: thứ tự và trùng phần tử

```sql
UPDATE orders_by_tenant_month
SET item_skus = item_skus + ['SKU-005']
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-25T09:00:00Z'
  AND order_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1;
```

`list` giữ thứ tự phần tử và có thể chứa bản sao. Nhưng append vào list là thao tác có đặc tính retry/concurrency cần xem xét: nếu request timeout nhưng server đã áp dụng và client thử lại, phần tử có thể bị thêm hai lần. **Không mặc định mọi thao tác collection đều idempotent.** Với đơn hàng nghiệp vụ cần đúng từng dòng hàng, bảng chi tiết riêng theo `order_id + line_id` thường an toàn và mở rộng tốt hơn list không giới hạn.

### 9.3. Map: metadata có khóa

```sql
UPDATE orders_by_tenant_month
SET attributes['channel'] = 'partner'
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-25T09:00:00Z'
  AND order_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1;
```

`map` phù hợp cho một số thuộc tính mở rộng **nhỏ, ổn định về số lượng và kích thước**. Khi map trở thành “JSON không giới hạn” chứa hàng nghìn khóa, việc cập nhật, đọc, serialize, tombstone và lưu trữ có thể tốn kém. Nếu cần tìm kiếm/sắp xếp theo một key trong map, đừng coi toàn bộ map là index: truy vấn phải được thiết kế theo access pattern và khả năng indexing cụ thể.

### 9.4. Đọc và kiểm tra collection

```sql
SELECT order_id, tags, item_skus, attributes
FROM orders_by_tenant_month
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND month_bucket = '2026-11';
```

Ở Java:

```java
OrderByTenantMonth row =
    repository.findById(existingKey).orElseThrow();

Set<String> tags = row.getTags();
List<String> skus = row.getItemSkus();
Map<String, String> attributes = row.getAttributes();

// Tránh giả định mọi collection luôn khác null.
boolean isVip = tags != null && tags.contains("vip");
String channel =
    attributes == null ? null : attributes.get("channel");
```

Trong thực tế, giá trị collection vắng mặt có thể được mapping thành `null` hoặc dạng rỗng tùy tình huống và converter. Thiết kế API phải quyết định rõ cách thể hiện và test theo hợp đồng, tránh thao tác `row.getTags().add(...)` khi property chưa được khởi tạo.

### 9.5. So sánh các collection

| Tiêu chí | `set<text>` | `list<text>` | `map<text,text>` |
| --- | --- | --- | --- |
| Kiểu Java | `Set<String>` | `List<String>` | `Map<String,String>` |
| Thứ tự nghiệp vụ | Không đảm bảo | Có thứ tự | Không thiết kế cho thứ tự |
| Giá trị trùng | Không | Có | Key duy nhất |
| Thao tác thường gặp | Thêm/xóa một nhãn | Append, cập nhật phần tử | Đặt/xóa giá trị theo key |
| Rủi ro | Tập nhãn tăng không giới hạn | Retry append, thay đổi đồng thời, list lớn | Map lớn, key linh hoạt khó kiểm soát |
| Mô hình thay thế khi lớn | Bảng riêng theo phần tử | Bảng dòng hàng theo ID | Bảng thuộc tính hoặc schema rõ ràng |

**Lưu ý về hiệu năng:** collection lớn có thể ảnh hưởng read/write amplification, kích thước row, serialization và tombstones khi phần tử bị xóa/thay đổi. `LIMIT 20` giới hạn số hàng của query, **không giới hạn số phần tử nằm trong một collection của mỗi hàng**.

## 10. CassandraTemplate, CQL và repository: dùng đường nào?

Bài tập tập trung vào mapping entity nhưng cần biết ba đường truy cập thường gặp.

### Repository

`CassandraRepository` phù hợp với thao tác CRUD theo `OrderMonthKey`. Đọc một đơn bằng `findById(key)`, lưu entity bằng `save(row)`, hoặc khai báo query đọc theo partition. Khi save toàn entity, phải kiểm soát null/collection/static writes và không vô tình thay giá trị chung của partition.

### CassandraTemplate / CassandraOperations

`CassandraOperations` dùng mapping entity để chuyển CQL result thành Java object, thuận tiện với query có điều kiện:

```java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public final class OrderMonthReader {

    private final CassandraOperations cassandra;

    public OrderMonthReader(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    public List<OrderByTenantMonth> findInMonth(
            UUID tenantId, String monthBucket, int limit) {
        if (tenantId == null || monthBucket == null
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }

        Query query = Query
            .query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .limit(limit);

        return cassandra.select(
            query, OrderByTenantMonth.class);
    }
}
```

Đoạn code này tận dụng Spring Data entity/UDT/collection mapping. Nhưng **Criteria không thay Cassandra query rules**: nếu thiếu một phần partition key hoặc tạo lọc trên cột thường không có access path phù hợp, câu CQL vẫn có thể bị từ chối hoặc chạy đắt đỏ. Integration test cần đối chiếu CQL với schema thật.

### Java Driver / CqlSession

`CqlSession` phù hợp khi cần CQL chính xác hoặc thao tác đặc thù như cập nhật static, thay UDT, thay phần tử collection với prepared statements. Khi dùng Driver trực tiếp, việc ánh xạ `Row`/UDT/collection vào entity có thể phải làm thủ công hoặc qua converter phù hợp. Cách này cho phép thiết lập consistency, page size, timeout theo statement; cấu hình phải được chọn theo yêu cầu hệ thống, không đặt tùy ý trong mỗi truy vấn.

## 11. Kiểm thử bài thực hành với Cassandra thật

Mock repository giúp xác nhận service truyền đúng `OrderMonthKey`; **mock không chứng minh** static column chia sẻ theo partition, UDT mapping hoặc query CQL hợp lệ. Hãy chạy integration test trên Cassandra một node để xác minh chức năng, sau đó dùng môi trường đại diện nếu cần kết luận về phân tán/hiệu năng.

### 11.1. Bộ kiểm thử tối thiểu

| Ca | Dữ liệu/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Khóa ghép | Hai tenant cùng tháng, hai đơn cùng timestamp | Không đè khóa, mỗi cặp khóa đầy đủ xác định bản ghi riêng |
| Partition | Truy vấn tenant Alpha tháng 11 | Không trả tenant Beta hoặc tháng khác |
| Thứ tự clustering | Seed dữ liệu không theo thứ tự thời gian | Kết quả trong partition theo `created_at DESC` |
| Static | Hai đơn cùng partition; update tên bằng CQL | Cả hai cùng thấy tên mới |
| Static khác partition | Đổi tên ở Alpha/tháng 11 | Beta và Alpha/tháng 10 không đổi |
| UDT | Ghi đủ 3 field, đọc lại entity | `postalCode`/`city` khớp schema |
| Frozen UDT | Thay toàn bộ địa chỉ bằng CQL | Đọc ra value mới, không kỳ vọng cập nhật field riêng |
| Set | Thêm lại một tag đã tồn tại | Không có giá trị trùng |
| List | Append SKU | Thứ tự và số lần append đúng với thao tác thực tế |
| Map | Đặt `attributes['channel']` | Chỉ key đó thay đổi như kỳ vọng |
| Null và dữ liệu rỗng | UDT/collection bị thiếu | Mapping không gây NPE ở service/API |
| Paging | Partition có nhiều hàng hơn page size | Đọc được trang tiếp theo, không lẫn tenant |
| CQL sai | Bỏ `month_bucket` khỏi restriction | Query bị từ chối hoặc không đạt access path đã thiết kế |

### 11.2. Ví dụ integration test đọc key và giá trị ánh xạ

Sau khi test đã khởi động Cassandra, tạo keyspace/type/table đúng như DDL và kết nối Spring Data tới container, có thể viết test theo mẫu:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class OrderMappingIntegrationTest {

    @Autowired
    OrderByTenantMonthRepository repository;

    @Test
    void roundTripCompositeKeyUdtVaCollection() {
        UUID tenant = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        Instant createdAt =
            Instant.parse("2026-11-25T12:00:00Z");

        OrderMonthKey key = new OrderMonthKey(
            tenant, "2026-11", createdAt, orderId);

        OrderByTenantMonth row = new OrderByTenantMonth();
        row.setKey(key);
        row.setTenantDisplayName("Tenant Test");
        row.setShippingAddress(new ShippingAddress(
            "1 Tran Hung Dao", "Ha Noi", "100000"));
        row.setTags(Set.of("gift", "priority"));
        row.setItemSkus(List.of("SKU-A", "SKU-B"));
        row.setAttributes(Map.of("channel", "web"));

        repository.save(row);

        OrderByTenantMonth actual =
            repository.findById(key).orElseThrow();

        assertEquals(key, actual.getKey());
        assertEquals("Ha Noi",
            actual.getShippingAddress().getCity());
        assertEquals("100000",
            actual.getShippingAddress().getPostalCode());
        assertEquals(Set.of("gift", "priority"),
            actual.getTags());
        assertEquals(List.of("SKU-A", "SKU-B"),
            actual.getItemSkus());
        assertEquals("web",
            actual.getAttributes().get("channel"));
    }
}
```

Đây là **mẫu phần thân test**, giả sử context/repository đã cấu hình với Cassandra thực; nó chưa bao gồm toàn bộ bootstrap Testcontainers, lifecycle keyspace và cleanup. Với môi trường test có thể tái lập, hãy chạy schema migration trong setup, giữ mỗi test độc lập và không phụ thuộc dữ liệu thử CQL ở phần trước. Test một node RF=1 xác minh **mapping/CQL cơ bản**, không kiểm tra behavior quorum/failover.

### 11.3. Test static column cần hai hàng

Một test khác nên:

1. Tạo hai `OrderMonthKey` có cùng `tenantId`, `monthBucket` nhưng `createdAt/orderId` khác.
2. Lưu hai hàng bình thường, bảo đảm chúng thuộc cùng partition.
3. Dùng CQL `UPDATE ... SET tenant_display_name = ? WHERE tenant_id = ? AND month_bucket = ?`.
4. Đọc lại **cả hai hàng** qua repository và assert cùng tên mới.
5. Thêm hàng thuộc tenant khác và assert không bị ảnh hưởng.

Không thể chứng minh ngữ nghĩa static chỉ bằng unit test cấu hình mock trả cùng tên cho hai entity; test phải **đi qua Cassandra server thật**.

### 11.4. Kiểm tra CQL không hợp lệ

Truy vấn sau thiếu một phần partition key:

```sql
SELECT *
FROM orders_by_tenant_month
WHERE tenant_id = 11111111-1111-1111-1111-111111111111;
```

Với schema của bài, không nên xử lý yêu cầu “tất cả tháng của một tenant” bằng cách thêm `ALLOW FILTERING`. Hãy thiết kế bảng đọc khác, ví dụ `orders_by_tenant_day` có bucket phù hợp hoặc một bảng tóm tắt những tháng hiện có, rồi gọi query riêng cho mỗi bucket có giới hạn hợp lý.

## 12. Paging, consistency và hiệu năng trong bài

### 12.1. Phân biệt LIMIT với fetch size

`LIMIT 50` trong CQL giới hạn **tổng số hàng tối đa** của truy vấn. Driver page size chỉ điều chỉnh số hàng được tải **mỗi lượt fetch**, và `ResultSet` có thể tự tải các trang tiếp theo khi ứng dụng duyệt kết quả. `repository.findInMonth(...)` trả toàn bộ kết quả vào `List`, nên không phù hợp cho partition lớn.

Khi làm API “Xem thêm”, hãy trả cursor/paging state gắn với tenant, tháng, filter và query; không cho client tùy ý sử dụng cursor từ tenant khác. Trong một hệ dữ liệu đang được ghi song song, paging không tự cho snapshot cố định giống transaction read-only ở một số RDBMS.

### 12.2. Consistency không thay thế mô hình khóa

`LOCAL_ONE`, `LOCAL_QUORUM` hoặc consistency level khác điều khiển mức yêu cầu phản hồi giữa các replica theo replication của cluster. Chúng **không** sửa query thiếu partition key, không làm collection lớn tự nhỏ lại và không tạo authorization cho tenant. Ở lab một node RF=1, các kết quả consistency không phản ánh kịch bản cụm nhiều replica.

### 12.3. Giá thành của thiết kế

Các yếu tố cần quan sát khi tải tăng:

- **Partition size**: một tenant có quá nhiều đơn trong tháng có thể tạo partition lớn, dù partition key có hai phần.
- **Clustering scan**: đọc đúng partition nhưng không giới hạn kết quả có thể tải nhiều row.
- **Collection growth**: hàng lớn vì `tags`, `item_skus` hoặc `attributes` tăng không giới hạn.
- **Tombstones**: xóa/cập nhật các phần tử collection, TTL hoặc thay đổi dữ liệu có thể phát sinh tombstones ảnh hưởng read path.
- **Static updates**: static thuộc partition; cập nhật liên tục có thể gây tranh chấp ghi/cần kiểm soát nghiệp vụ.
- **UDT frozen**: thay đổi một field kéo theo thay toàn bộ value, nên đánh giá khi địa chỉ lớn hoặc bị cập nhật liên tục.

Có thể dùng metrics Cassandra, `nodetool tablestats`, tracing có chọn lọc và benchmark với nhiều kích thước partition để đánh giá. Không suy ra hiệu năng production từ việc vài dòng dữ liệu lab đọc rất nhanh.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `InvalidQueryException` về restriction | Query thiếu `month_bucket` hoặc điều kiện clustering không hợp lệ | Đối chiếu `PRIMARY KEY` và CQL; không ép `ALLOW FILTERING` |
| Hai đơn có cùng timestamp ghi đè nhau | Khóa không có `order_id` hoặc mã tạo ID trùng | Thêm clustering discriminator và kiểm tra tính duy nhất |
| Mapping `OrderMonthKey` sai | `@PrimaryKeyColumn` thiếu/sai type, ordinal hoặc tên cột | Kiểm tra annotation so với DDL; chạy integration test |
| `ShippingAddress` đọc ra null/mất field | UDT/type/field name không khớp | Kiểm tra `@UserDefinedType`, `@Column` và keyspace |
| Update `shipping_address.city` không thực hiện | Cột UDT đang `frozen` | Thay toàn bộ UDT hoặc chọn mô hình lưu trữ khác |
| Tên tenant khác nhau giữa các đơn trong partition | Ghi static từ nhiều hàng cùng partition | Đưa cập nhật static vào đường riêng và kiểm soát invariant |
| Collection trả null gây NPE | Tưởng lúc nào set/list/map cũng hiện diện | Chuẩn hóa nullable/empty ở API và test |
| Append list bị lặp sau retry | Phép append list không idempotent | Dùng ID ổn định/bảng chi tiết hoặc thiết kế retry phù hợp |
| Đọc chậm dù có key partition | Partition/row/collection lớn hoặc nhiều tombstone | Đo partition size, giới hạn kết quả, chỉnh bucket/model |
| Test mock xanh nhưng chạy thật lỗi | Mock bỏ qua CQL/schema/UDT conversion | Test tích hợp với Cassandra thực |

## 14. Bài tập mở rộng

**Bài 1 — Thay đổi time bucket.** Chuyển `month_bucket` thành `day_bucket`. Sửa schema, `OrderMonthKey`, query và test. Giải thích vì sao API “đơn của tháng” lúc này phải truy vấn nhiều partition; giới hạn số request và gộp kết quả thế nào?

**Bài 2 — UDT có field mới.** Thêm `country_code` vào UDT bằng migration phù hợp, cập nhật lớp `ShippingAddress` và viết test tương thích với dữ liệu cũ chưa có field. Xác định ý nghĩa của `null` và cách backfill.

**Bài 3 — Static column bị dùng sai.** Thử chuyển `shipping_address` thành static. Tạo hai đơn cùng partition nhưng địa chỉ khác nhau và giải thích sự sai lệch. Chỉ ra thuộc tính nào **thực sự chung partition** để static hợp lý.

**Bài 4 — Collection phát triển lớn.** Giả lập đơn có 10.000 `item_skus`. So sánh chi phí serialize/read/update list với thiết kế bảng `order_items_by_order` có partition key theo tenant và order, clustering key theo `line_id`. Nêu cách paging dòng hàng mà không materialize toàn bộ.

**Bài 5 — Truy cập theo ID đơn.** Thêm yêu cầu `GET /orders/{orderId}` khi client chỉ biết tenant và orderId. Thiết kế read model thứ hai với `PRIMARY KEY ((tenant_id, order_id))`, mô tả cách ghi/cập nhật vào hai bảng và kiểm thử consistency khi một bước ghi thất bại.

**Bài 6 — API đa tenant.** Tạo test actor tenant A yêu cầu đơn tenant B, thử dùng paging cursor từ tenant khác và xác minh mọi query sử dụng `authorizedTenantId` đã kiểm chứng. Giải thích vì sao `tenant_id` trong partition key là cần thiết cho access pattern nhưng chưa đủ để thay authorization.

## 15. Checklist nộp bài

- [ ] Có schema CQL với **composite partition key** `(tenant_id, month_bucket)` và hai clustering columns đúng thứ tự.
- [ ] `@PrimaryKeyClass`, `@PrimaryKeyColumn` và entity mapping đúng CQL; khóa có `equals()/hashCode()`.
- [ ] Có `@UserDefinedType("shipping_address")` và giải thích rõ `frozen`.
- [ ] `tenant_display_name` là static ở schema; test hai đơn cùng partition thấy chung giá trị.
- [ ] `Set<String>`, `List<String>`, `Map<String,String>` lưu/đọc đúng và biết khác biệt ngữ nghĩa.
- [ ] Không dùng collection như bảng vô hạn hoặc dùng static cho dữ liệu khác nhau theo từng đơn.
- [ ] Repository/Template query có **đầy đủ partition key**, tách rõ read theo key và read danh sách.
- [ ] Có integration test với Cassandra thực; không chỉ mock `CassandraRepository`.
- [ ] Kiểm tra null, CQL sai, tenant khác, timestamp trùng, static update và UDT update.
- [ ] Có giới hạn dữ liệu/paging và nhận thức về consistency, tombstone, partition size.

**Ghi nhớ:** ánh xạ entity thành công mới là bước đầu. Trong **Spring Data Cassandra**, **khóa ghép** quyết định phân vùng và thứ tự dữ liệu, **static column** thuộc cả partition, **UDT frozen** biểu diễn một value object cập nhật nguyên khối, còn **collection** thích hợp với dữ liệu nhỏ có giới hạn. Khi code Java, CQL schema, access pattern và integration test cùng phản ánh những ngữ nghĩa đó, ứng dụng mới có cơ sở để vận hành đúng và mở rộng tốt trên Cassandra phân tán.
