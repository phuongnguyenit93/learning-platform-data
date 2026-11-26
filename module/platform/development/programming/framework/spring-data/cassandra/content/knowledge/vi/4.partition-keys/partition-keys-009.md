# Khóa nghiệp vụ, UUID và timeuuid theo nhu cầu định danh

Trong **Spring Data Cassandra**, việc chọn ID cho một thực thể không chỉ là chọn kiểu dữ liệu cho một trường Java. Cassandra phân phối dữ liệu theo **partition key**, sắp xếp các hàng bên trong partition theo **clustering columns**, và nhận diện một hàng bằng **toàn bộ primary key**. Vì vậy, ID nghiệp vụ, UUID và timeuuid có ý nghĩa khác nhau tùy cách ứng dụng cần tra cứu, sắp xếp và cập nhật dữ liệu.

Bài thuộc chương **Khóa và phân vùng**. Chúng ta sẽ áp dụng nguyên tắc **thiết kế bảng theo truy vấn** vào ba nhu cầu: tìm sản phẩm theo mã nghiệp vụ, tìm đơn hàng theo ID được sinh tự động và đọc nhật ký sự kiện theo thời gian. Ví dụ sử dụng CQL, entity mapping, repository và `CassandraTemplate` trong Spring Data Cassandra; đồng thời đề cập tính nhất quán, paging và hiệu năng của hệ phân tán.

## 1. Ba câu hỏi cần trả lời trước khi chọn khóa

Khi thiết kế một bảng Cassandra, hãy tách ba câu hỏi:

1. **Định danh nào ổn định cho nghiệp vụ?** Ví dụ mã SKU trong một tenant, ID đơn hàng sinh bởi hệ thống hoặc ID của sự kiện.
2. **Ứng dụng sẽ truy vấn theo thông tin nào?** Ví dụ `(tenant_id, sku)`, `(tenant_id, order_id)` hoặc `(device_id, day_bucket)`. Các giá trị thường xuất hiện trong điều kiện `WHERE` sẽ quyết định partition key.
3. **Trong một partition, các hàng cần có thứ tự nào?** Ví dụ theo thời điểm sự kiện mới nhất trước. Thứ tự này thường quyết định clustering columns, không phải chỉ kiểu ID.

Ví dụ hai truy vấn khác nhau trên cùng một đơn hàng:

~~~text
GET /tenants/{tenantId}/orders/{orderId}
  → tìm một đơn theo tenant và ID

GET /tenants/{tenantId}/orders?month=2026-11&limit=20
  → liệt kê 20 đơn gần nhất trong tháng
~~~

Một ID có thể rất tốt để tìm **một** đơn nhưng không tự đáp ứng truy vấn **danh sách** theo thời gian. Cassandra thường dùng hai bảng truy cập (read models) có cách tổ chức khóa khác nhau cho hai nhu cầu này.

### 1.1. Phân biệt ba loại khóa trong Cassandra

~~~sql
CREATE TABLE events_by_device_day (
    device_id uuid,
    day_bucket date,
    event_id timeuuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

| Khái niệm | Trong bảng mẫu | Tác dụng |
|---|---|---|
| Partition key | `(device_id, day_bucket)` | Xác định partition và nơi lưu dữ liệu |
| Clustering column | `event_id` | Phân biệt và sắp xếp các hàng trong partition |
| Toàn bộ primary key | `(device_id, day_bucket, event_id)` | Định danh duy nhất một hàng trong bảng |
| Định danh nghiệp vụ | Có thể là `device_id` hoặc một mã bên ngoài | Giúp hệ thống và người dùng nhận biết đối tượng |

Hai event của cùng một thiết bị trong cùng ngày **không phải cùng hàng** nếu `event_id` khác nhau. Nhưng nếu ghi lại **cùng toàn bộ primary key**, Cassandra thực hiện kiểu **upsert**: các giá trị cột được cập nhật theo quy tắc xử lý timestamp của Cassandra, không tự tạo một hàng thứ hai.

**Quan trọng:** tên trường `id` hoặc `@PrimaryKey` trong Java không tự quyết định partition key. Chính định nghĩa CQL `PRIMARY KEY` và mapping tương ứng mới quyết định cách lưu và truy vấn.

## 2. So sánh khóa nghiệp vụ, UUID và timeuuid

| Loại định danh | Ví dụ | Ưu điểm | Giới hạn cần lưu ý |
|---|---|---|---|
| **Khóa nghiệp vụ (natural/business key)** | `(tenant_id, sku)`, `(country_code, tax_id)` | Có ý nghĩa nghiệp vụ; gọi API dễ nếu đã có mã | Có thể thay đổi, trùng giữa tenant hoặc phải chuẩn hóa |
| **UUID ngẫu nhiên (thường là v4)** | `UUID.randomUUID()` | Khả năng va chạm cực thấp nếu sinh đúng; không cần cấp phát ID tập trung | Không mang thứ tự thời gian; không hỗ trợ tự nhiên cho truy vấn theo thời gian |
| **timeuuid (UUID phiên bản 1)** | `Uuids.timeBased()`, CQL `now()` | Mang thành phần thời gian; hữu ích làm clustering key cho sự kiện | Không là đồng hồ toàn cục; thứ tự có thể ảnh hưởng bởi lệch đồng hồ và thời điểm sinh |

Trong CQL:

- `uuid` là kiểu lưu UUID tổng quát; ứng dụng thường tạo UUID v4 cho ID kỹ thuật.
- `timeuuid` chỉ chấp nhận **UUID phiên bản 1**, có thành phần timestamp và được Cassandra so sánh theo ngữ nghĩa timeuuid.
- Hai kiểu có liên quan nhưng **không hoán đổi tùy ý**: một UUID v4 không hợp lệ để chèn vào cột `timeuuid`.

Đừng kết luận “dùng `timeuuid` thì mọi bảng tự được sắp xếp theo thời gian”. Chỉ khi cột `timeuuid` được đặt ở **vị trí clustering phù hợp** và truy vấn cung cấp partition key, Cassandra mới có đường đọc theo thứ tự đó.

## 3. Khóa nghiệp vụ: phù hợp khi người gọi biết mã ổn định

Giả sử phần mềm bán hàng đa tenant quản lý sản phẩm theo mã SKU. SKU `BOOK-001` có thể tồn tại ở cả tenant A và tenant B. Khóa nghiệp vụ hợp lý là **cặp** `(tenant_id, sku)`, không phải riêng `sku`.

~~~sql
CREATE TABLE products_by_tenant_sku (
    tenant_id uuid,
    sku text,
    product_name text,
    unit_price decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, sku))
);

SELECT product_name, unit_price
FROM products_by_tenant_sku
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND sku = 'BOOK-001';
~~~

`(tenant_id, sku)` là **composite partition key**: cả hai thành phần được dùng để tính token phân vùng. Mỗi cặp ở ví dụ này tương ứng một hàng. Truy vấn theo **chỉ tenant** không thể tự liệt kê hiệu quả mọi SKU bằng bảng này vì thiếu thành phần partition key `sku`.

Để hỗ trợ danh sách sản phẩm của một tenant, cần đánh giá một đường đọc khác, chẳng hạn bảng `products_by_tenant_category` với partition key theo tenant và nhóm sản phẩm, clustering theo tên hoặc SKU; hoặc một index/search phù hợp nếu yêu cầu thực tế cho phép. Không nên thêm `ALLOW FILTERING` để mặc định xử lý truy vấn không đúng khóa.

### 3.1. Điều kiện để khóa nghiệp vụ là lựa chọn tốt

- **Ổn định:** mã được định nghĩa ít thay đổi. Nếu SKU thường xuyên bị đổi tên, ID kỹ thuật riêng có thể giúp giữ quan hệ với các sự kiện lịch sử.
- **Phạm vi duy nhất rõ ràng:** mã có thể duy nhất trong tenant nhưng không duy nhất toàn hệ thống; phải mang theo `tenant_id` trong hợp đồng API và trong khóa.
- **Chuẩn hóa đầu vào:** quyết định cách xử lý chữ hoa/chữ thường, khoảng trắng, Unicode và dấu phân tách **trước khi ghi**. `BOOK-001` và `book-001` là hai chuỗi khác nhau nếu không chuẩn hóa.
- **Không nhạy cảm:** email, số điện thoại hoặc số giấy tờ có thể thay đổi và nhạy cảm; thường không phải lựa chọn tốt để làm khóa lưu trữ lâu dài. Có thể đặt một ID kỹ thuật ổn định và lập đường tra cứu riêng theo giá trị nghiệp vụ.
- **Phân bố đủ tốt:** nếu chỉ dùng khóa rất ít giá trị như `status` hoặc `country` làm partition key, dễ tạo partition lớn hoặc nóng dù đó là trường nghiệp vụ hợp lệ.

### 3.2. Đổi khóa nghiệp vụ không giống sửa một cột thường

Nếu `sku` nằm trong primary key, thay `BOOK-001` thành `BOOK-002` đồng nghĩa **ghi hàng mới ở khóa mới** và **xóa hàng ở khóa cũ**. Cassandra không cập nhật primary key của hàng tại chỗ.

~~~text
(tenant-A, BOOK-001)  --delete-->  tombstone
          |
          +--insert--> (tenant-A, BOOK-002)
~~~

Cần cân nhắc việc cập nhật các bảng tra cứu khác, liên kết bên ngoài, retry khi thao tác thất bại giữa chừng và quy tắc giữ mã cũ. Nếu mã thường đổi, hãy chọn `product_id uuid` làm định danh bền vững của sản phẩm rồi tạo `product_id_by_tenant_sku` như một **đường tra cứu** theo mã.

## 4. Ánh xạ composite business key với Spring Data Cassandra

`@PrimaryKeyClass` mô tả các thành phần của khóa; `@PrimaryKeyColumn` chỉ ra phần nào là partition key và thứ tự của chúng.

~~~java
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class ProductKey implements Serializable {
    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "sku", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String sku;

    public ProductKey() {}

    public ProductKey(UUID tenantId, String sku) {
        this.tenantId = tenantId;
        this.sku = sku;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductKey)) return false;
        ProductKey that = (ProductKey) other;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(sku, that.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }
}
~~~

Entity giữ khóa như một đối tượng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("products_by_tenant_sku")
public class Product {
    @PrimaryKey
    private ProductKey id;

    @Column("product_name")
    private String productName;

    @Column("unit_price")
    private BigDecimal unitPrice;

    @Column("updated_at")
    private Instant updatedAt;

    public Product() {}
    // Bổ sung constructor và getters/setters cho các field.
}
~~~

Repository làm việc với **đúng kiểu khóa**:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ProductRepository
        extends CassandraRepository<Product, ProductKey> {
}

// Ví dụ trong service có ProductRepository repository:
ProductKey key = new ProductKey(tenantId, "BOOK-001");
Optional<Product> product = repository.findById(key);
~~~

Trong đó `tenantId` là `UUID` đã xác thực từ ngữ cảnh người gọi. Spring Data Cassandra ánh xạ `ProductKey` sang composite partition key; `findById` cung cấp cả hai thành phần nên phù hợp với bảng.

**Ranh giới trách nhiệm:** repository giúp gọi CQL và chuyển dữ liệu thành entity, còn chuẩn hóa SKU, kiểm tra quyền tenant và quyết định một sản phẩm có được đổi mã hay không vẫn thuộc lớp nghiệp vụ.

## 5. UUID: ID kỹ thuật độc lập với tên và thời điểm tạo

Giả sử đơn hàng có `external_order_no` do người mua hoặc đối tác cung cấp. Mã này có thể trùng giữa hệ thống hoặc thay đổi định dạng. Sử dụng `order_id uuid` làm ID kỹ thuật giúp hệ thống giữ định danh ổn định.

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    external_order_no text,
    created_at timestamp,
    status text,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Khóa là **cặp** `(tenant_id, order_id)`; `order_id` ở đây không tự đủ để truy vấn bảng nếu thiếu `tenant_id`.

~~~java
import java.util.UUID;

UUID orderId = UUID.randomUUID(); // UUID v4 trong Java.
// Sinh một lần khi tạo đơn và lưu cùng thao tác nghiệp vụ.
// Dùng lại chính orderId đó khi retry cùng yêu cầu.
~~~

UUID v4 phù hợp khi cần phát sinh ID ở nhiều service mà không phải gọi bộ cấp phát số thứ tự tập trung. Nếu ID là partition key hoặc một phần partition key và giá trị đủ phân tán, Cassandra có thể rải tải qua nhiều token tốt hơn so với một khóa tuần tự tập trung vào rất ít partition.

Tuy nhiên:

- `uuid` **không nói lên thứ tự tạo**. Không dùng `ORDER BY order_id` để thay cho `ORDER BY created_at`; Cassandra cũng không cho phép sắp xếp tùy ý trên một cột không phải clustering column.
- UUID **không giải quyết mọi truy vấn**. Muốn liệt kê đơn mới nhất theo tenant/tháng, cân nhắc bảng `orders_by_tenant_month` có clustering key `created_at` hoặc `timeuuid`.
- UUID có xác suất va chạm rất thấp nhưng **không phải đảm bảo độc nhất bởi cơ sở dữ liệu**. Tính duy nhất ở cấp hàng phụ thuộc toàn bộ primary key; nếu cần cơ chế “chỉ tạo khi chưa tồn tại”, phải thiết kế thêm kiểm tra và atomic compare-and-set phù hợp.
- UUID ngẫu nhiên là **định danh**, không phải secret. Không coi một URL chứa UUID khó đoán là cơ chế phân quyền; vẫn kiểm tra quyền truy cập với tenant và người gọi.

### 5.1. UUID trong entity mapping

Với bảng chỉ có một UUID làm partition key:

~~~sql
CREATE TABLE users_by_id (
    user_id uuid PRIMARY KEY,
    display_name text
);
~~~

Spring Data Cassandra có thể ánh xạ trực tiếp:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("users_by_id")
public class UserById {
    @PrimaryKey("user_id")
    private UUID userId;

    private String displayName;

    public UserById() {}
    // Bổ sung constructor và getters/setters.
}

public interface UserRepository
        extends CassandraRepository<UserById, UUID> {
}
~~~

Ở đây `UUID` là **toàn bộ primary key**, nên `findById(userId)` là truy vấn đúng partition. Trong `orders_by_id`, khóa lại là **hai trường**: cần `@PrimaryKeyClass` và repository sử dụng kiểu composite key tương ứng.

### 5.2. ID đơn hàng và mã đơn hàng bên ngoài

Một hệ thống có thể cần cả hai đường đọc:

~~~sql
-- Đọc theo ID kỹ thuật:
-- orders_by_id: PRIMARY KEY ((tenant_id, order_id))

CREATE TABLE order_id_by_external_no (
    tenant_id uuid,
    external_order_no text,
    order_id uuid,
    PRIMARY KEY ((tenant_id, external_order_no))
);
~~~

Bảng `order_id_by_external_no` là **bảng tra cứu phụ**, trả về `order_id` để đọc dữ liệu chính. Nếu một external number được phép đổi hoặc tái sử dụng, phải có chính sách xóa/cập nhật ánh xạ cũ. Nếu business yêu cầu external number duy nhất trong tenant, phải có quy trình kiểm soát xung đột tại lúc tạo, không chỉ dựa vào một lần `SELECT` rồi `INSERT` thông thường.

## 6. timeuuid: dùng thời gian để tổ chức dòng sự kiện

`timeuuid` là UUID phiên bản 1 có thành phần thời gian. Cassandra so sánh `timeuuid` theo thứ tự phù hợp với timestamp bên trong, giúp đặt một ID sự kiện vừa **phân biệt hàng** vừa **làm khóa sắp xếp gần theo thời điểm sinh**.

Ví dụ bảng nhật ký:

~~~sql
CREATE TABLE events_by_device_day (
    device_id uuid,
    day_bucket date,
    event_id timeuuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Để thêm sự kiện:

~~~sql
INSERT INTO events_by_device_day
    (device_id, day_bucket, event_id, event_type, payload)
VALUES
    (?, ?, now(), 'TEMPERATURE_ALERT', ?);
~~~

Hàm CQL `now()` tạo **timeuuid** mới từ thời điểm thực thi. Nó phù hợp với ví dụ về sự kiện mới phát sinh khi ghi, nhưng có một đánh đổi lớn: **thực thi lại INSERT có `now()` sẽ sinh ID mới**, dễ tạo hai hàng cho cùng một sự kiện nghiệp vụ khi retry.

Thực tế, nhiều hệ thống nên tạo ID **một lần ở lớp ứng dụng** và tái sử dụng trong mọi lần thử ghi:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.uuid.Uuids;

UUID eventId = Uuids.timeBased(); // UUID v1 dùng cho cột CQL timeuuid.
// Lưu eventId trong message/request trước khi retry.
~~~

`Uuids.timeBased()` thuộc Java Driver 4 của Cassandra. Với driver/phiên bản khác, phải kiểm tra API cung cấp timeuuid tương ứng; không đưa `UUID.randomUUID()` (thường v4) vào cột CQL `timeuuid`.

### 6.1. Truy vấn sự kiện mới nhất

~~~sql
SELECT event_id, event_type, payload
FROM events_by_device_day
WHERE device_id = ?
  AND day_bucket = '2026-11-25'
LIMIT 50;
~~~

Vì `event_id` là clustering column với thứ tự `DESC`, các hàng đầu tiên trong partition tương ứng các **timeuuid mới hơn**. `LIMIT 50` có ích vì ứng dụng không cần đọc cả lịch sử trong ngày.

CQL còn cung cấp các hàm `minTimeuuid`/`maxTimeuuid` để tạo **giá trị ranh giới** cho truy vấn khoảng thời gian:

~~~sql
SELECT event_id, event_type
FROM events_by_device_day
WHERE device_id = ?
  AND day_bucket = '2026-11-25'
  AND event_id >= minTimeuuid('2026-11-25 09:00:00+0000')
  AND event_id <  minTimeuuid('2026-11-25 10:00:00+0000');
~~~

Đây là khoảng **[09:00, 10:00)** theo UTC và chỉ tìm trong một partition. Các giá trị do `minTimeuuid`/`maxTimeuuid` tạo ra dùng để **so sánh ranh giới**, không dùng làm ID thực tế để chèn vào bảng.

### 6.2. timeuuid không thay thế thời gian nghiệp vụ

Có ít nhất ba mốc thời gian cần phân biệt:

| Mốc thời gian | Ý nghĩa | Có thể khác nhau khi nào? |
|---|---|---|
| **Event time** | Thời điểm sự kiện thực sự diễn ra | Thiết bị gửi muộn hoặc gửi dữ liệu lịch sử |
| **ID generation time** | Thời điểm tạo timeuuid | Retry, pipeline, lệch đồng hồ máy phát ID |
| **Write time** | Thời điểm Cassandra nhận/ghi mutation | Hàng đợi mạng, tải cluster, retry |

Nếu thiết bị ghi nhận sự kiện lúc 09:00 nhưng gửi lên lúc 11:00, `timeuuid` sinh lúc 11:00 sẽ sắp xếp nó gần các event 11:00. Muốn hiển thị đúng theo **event time**, hãy dùng cột `event_time timestamp` làm clustering key (kèm `event_id` để tránh trùng khi nhiều sự kiện cùng thời điểm), rồi lưu UUID riêng làm định danh.

~~~sql
CREATE TABLE events_by_device_event_time (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`timeuuid` hữu ích cho **thứ tự theo thời điểm sinh ID**, nhưng không đảm bảo thứ tự nhân quả tuyệt đối giữa nhiều máy hoặc nhiều datacenter: đồng hồ có thể lệch, sự kiện đến trễ và các bộ sinh ID khác nhau không chia sẻ một đồng hồ logic thống nhất. Nếu nghiệp vụ cần thứ tự chính xác, hãy thiết kế thêm sequence/version được cấp phát và kiểm soát phù hợp.

## 7. timeuuid trong Spring Data Cassandra

Java Driver biểu diễn cả CQL `uuid` và `timeuuid` thông qua `java.util.UUID`; **kiểu CQL ở schema** mới quyết định điều kiện phiên bản UUID. Trong Spring Data Cassandra, khóa ghép với clustering `timeuuid` có thể được ánh xạ:

~~~java
import java.io.Serializable;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class DeviceEventKey implements Serializable {
    @PrimaryKeyColumn(name = "device_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "day_bucket", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate dayBucket;

    @PrimaryKeyColumn(name = "event_id", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private UUID eventId;

    public DeviceEventKey() {}
    // Bổ sung constructor, getters/setters, equals/hashCode
    // trên đầy đủ ba thành phần trước khi dùng trong ứng dụng.
}
~~~

Entity và repository:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

@Table("events_by_device_day")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey id;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public DeviceEvent() {}
    // Bổ sung constructor và getters/setters.
}

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM events_by_device_day " +
           "WHERE device_id = ?0 AND day_bucket = ?1 LIMIT 50")
    java.util.List<DeviceEvent> findRecent(UUID deviceId, LocalDate dayBucket);
}
~~~

Đoạn code trình bày cấu trúc mapping và đường truy vấn; cần bổ sung accessor/constructor phù hợp và import `UUID`/`LocalDate` trong tập tin thực tế. Điều kiện CQL đi qua **đầy đủ partition key** trước khi Cassandra trả các hàng theo clustering order.

Với `CassandraTemplate`, cùng truy vấn có thể viết:

~~~java
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// Trong service đã inject CassandraTemplate template:
Query query = Query.query(Criteria.where("device_id").is(deviceId))
        .and(Criteria.where("day_bucket").is(dayBucket))
        .limit(50);

List<DeviceEvent> result = template.select(query, DeviceEvent.class);
~~~

Ở đây `deviceId` là `UUID`, `dayBucket` là `LocalDate` và `List` thuộc `java.util`. Repository và template mang lại hai cách thể hiện truy vấn; chúng không làm thay đổi cách Cassandra xác định partition.

Khi cần đọc nhiều hàng, nên dùng **paging state** qua cơ chế paging phù hợp của repository/template/driver thay vì trả một danh sách không giới hạn. Với nhiều ngày, phải truy vấn nhiều `(device_id, day_bucket)` rồi ghép dữ liệu; paging state của một partition không tự trở thành con trỏ hợp lệ cho partition ngày khác.

## 8. Những bẫy khi chọn partition key

### 8.1. Định danh duy nhất không đảm bảo phân bố tải tốt

Giả sử mỗi yêu cầu đọc đều dùng:

~~~sql
SELECT *
FROM events_by_device_day
WHERE device_id = ?
  AND day_bucket = ?;
~~~

Dù `device_id` là UUID và các thiết bị được phân phối đều, một thiết bị gửi hàng triệu sự kiện trong cùng một ngày có thể tạo **hot/large partition**. UUID của thiết bị có khả năng duy nhất nhưng không làm giảm số hàng trong partition `(device_id, day_bucket)`.

Giải pháp có thể là bucket theo giờ, thêm shard xác định hoặc thay đổi cách truy vấn:

~~~sql
CREATE TABLE events_by_device_hour (
    device_id uuid,
    hour_bucket text,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY ((device_id, hour_bucket), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Bucket giờ giúp giới hạn thời lượng mà một partition tích lũy dữ liệu, nhưng không tự bảo đảm một partition luôn nhỏ: thiết bị rất nóng vẫn có thể ghi quá nhiều sự kiện trong một giờ. Thêm shard tăng khả năng phân tán ghi nhưng bắt buộc fan-out khi đọc và phải trộn kết quả theo thời gian.

### 8.2. Chọn một khóa có ít giá trị gây nóng

Ví dụ không tốt cho bảng sự kiện lớn:

~~~sql
CREATE TABLE events_by_status (
    status text,
    event_id timeuuid,
    payload text,
    PRIMARY KEY (status, event_id)
);
~~~

`status` chỉ có vài giá trị như `OPEN` và `CLOSED`. Một trạng thái phổ biến có thể tạo một partition cực lớn. Cũng không có partition theo tenant hoặc theo thời gian. Hãy xuất phát từ truy vấn thực tế và cân nhắc `(tenant_id, status, day_bucket, shard)` khi cần truy vấn trạng thái theo phạm vi có giới hạn; shard là lựa chọn có chi phí đọc riêng, không mặc định cần ở mọi bảng.

### 8.3. Đừng nhầm uniqueness với quan hệ giữa nhiều bảng

Cassandra đảm bảo các mutation tới cùng primary key được hợp nhất theo cơ chế ghi của Cassandra; điều đó **không** tự đảm bảo một mã ngoài chỉ tồn tại ở đúng một bảng hay một cập nhật cùng lúc ở nhiều partition là giao dịch ACID.

Nếu nhiều writer có thể cùng đăng ký một SKU hoặc external order number, có thể cần một phép ghi có điều kiện:

~~~sql
INSERT INTO order_id_by_external_no
    (tenant_id, external_order_no, order_id)
VALUES (?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` là **lightweight transaction (LWT)**, giúp một thao tác có điều kiện trên hàng/partition tương ứng tránh kiểu race condition “đọc không có rồi cả hai cùng ghi”. LWT có thêm chi phí và không tự tạo giao dịch nhiều bảng. Ứng dụng cần xem kết quả **[applied]** của statement, phân biệt trường hợp mã đã tồn tại với timeout chưa rõ kết quả, rồi áp dụng quy trình đối soát phù hợp.

### 8.4. Thời điểm sinh ID và retry

| Cách sinh ID | Retry cùng một sự kiện | Hệ quả |
|---|---|---|
| `UUID.randomUUID()` bên trong mỗi lần gọi lại | Sinh ID mới nếu chạy lại code | Có thể tạo bản ghi trùng nghiệp vụ |
| `Uuids.timeBased()` ở đầu mỗi lần thử | Sinh timeuuid mới | Có thể tạo thêm một hàng theo thời gian mới |
| Sinh ID một lần, lưu trong request/event và tái sử dụng | Dùng lại cùng primary key | Có cơ sở để ghi idempotent theo khóa, vẫn phải kiểm soát payload/phiên bản |
| Dùng `now()` ngay trong CQL khi retry | Cassandra sinh timeuuid mới mỗi lần | Không an toàn cho sự kiện cần exactly-once về mặt nghiệp vụ |

Một request có idempotency key riêng và trạng thái thực hiện có thể cần thiết nếu hệ thống yêu cầu **một hành động nghiệp vụ chỉ được áp dụng một lần**. Một UUID giữ nguyên giúp tránh tạo thêm khóa mới, nhưng không đủ để xử lý toàn bộ tranh chấp, cập nhật khác phiên bản hoặc nhiều projection.

## 9. Quy tắc chọn khóa theo yêu cầu API

| Câu hỏi nghiệp vụ | Định danh nên cân nhắc | Thiết kế bảng/khóa | Lưu ý |
|---|---|---|---|
| Tìm sản phẩm theo mã SKU của tenant | Khóa nghiệp vụ `(tenant_id, sku)` | `PRIMARY KEY ((tenant_id, sku))` | Chuẩn hóa SKU, thay đổi mã |
| Tìm một user theo ID kỹ thuật | UUID v4 | `PRIMARY KEY (user_id)` | Không có thứ tự thời gian |
| Tìm đơn hàng theo ID trong tenant | UUID v4 + tenant | `PRIMARY KEY ((tenant_id, order_id))` | API phải có tenant ID |
| Tra đơn qua mã do đối tác gửi | Khóa nghiệp vụ tra cứu → UUID | Bảng `order_id_by_external_no` riêng | Giải quyết race condition và cập nhật ánh xạ |
| 50 event gần nhất của thiết bị trong ngày | timeuuid làm clustering column | `PRIMARY KEY ((device_id, day_bucket), event_id)` | Thứ tự theo lúc sinh ID |
| Event đến trễ nhưng cần xếp theo lúc xảy ra | UUID + `timestamp` nghiệp vụ | `PRIMARY KEY ((device_id, day), event_time, event_id)` | Thời điểm sinh ID khác event time |
| Báo cáo toàn bộ event theo tháng | Không giải bằng đổi kiểu ID | Bảng tổng hợp hoặc hệ phân tích | Tránh quét quá nhiều partition |

Trình tự quyết định hữu ích:

~~~mermaid
flowchart TD
    A[Đọc hợp đồng truy vấn] --> B{Có mã nghiệp vụ ổn định và duy nhất trong phạm vi?}
    B -->|Có| C[Đánh giá business key + phạm vi tenant]
    B -->|Không| D[Chọn ID kỹ thuật UUID]
    C --> E{Có cần liệt kê nhiều hàng theo thứ tự thời gian?}
    D --> E
    E -->|Không| F[Thiết kế bảng tra cứu theo đúng partition key]
    E -->|Có| G{Thứ tự là lúc sinh ID hay event time nghiệp vụ?}
    G -->|Lúc sinh ID| H[timeuuid làm clustering key]
    G -->|Event time| I[timestamp + UUID phá hòa]
    H --> J[Chọn bucket, paging, kiểm tra hot partition]
    I --> J
    F --> K[Đo truy vấn, uniqueness và chi phí cập nhật]
    J --> K
~~~

## 10. Tính nhất quán và hiệu năng liên quan tới khóa

### 10.1. Chọn consistency level theo yêu cầu, không theo kiểu ID

`LOCAL_ONE` hoặc `LOCAL_QUORUM` quyết định mức xác nhận replica trong datacenter cục bộ đối với thao tác nhất định, tùy cấu hình replication. Chúng không đổi việc `uuid` là ID ngẫu nhiên hay `timeuuid` chứa timestamp; cũng không biến nhiều bảng truy cập thành một giao dịch thống nhất.

Nếu bảng `orders_by_id` và `order_id_by_external_no` được ghi qua hai statement, reader có thể tạm thấy bảng này đã có dữ liệu trong khi bảng kia chưa cập nhật. Phải thiết kế quy trình đồng bộ, retry, idempotency và đối soát theo mức nhất quán nghiệp vụ yêu cầu.

### 10.2. Theo dõi số hàng, tốc độ ghi và paging

Không có “ngưỡng số hàng an toàn” cố định cho mọi partition. Cần đo theo kích thước hàng, lưu lượng ghi, khả năng node và SLA. Những chỉ số cần quan sát gồm:

- Kích thước và phân bố partition: trung vị, các partition lớn nhất và hot key.
- Độ trễ `p50/p95/p99` cho đọc theo partition và cho fan-out nhiều partition.
- Timeout, số request đang xử lý, retry, heap/GC và lưu lượng giữa node.
- Tombstones khi đổi business key hoặc di chuyển dữ liệu giữa bảng trạng thái.
- Số trang đọc, fetch size, dung lượng phản hồi và số hàng thực sự trả về.

**Chìa khóa:** chọn UUID ngẫu nhiên cho ID của từng hàng chỉ giúp phân bố tải nếu UUID thực sự tham gia partition key theo cách phù hợp. Nếu partition key cố định theo một `device_id` quá nóng, thay đổi clustering column từ `uuid` sang `timeuuid` **không chia nhỏ partition**.

## 11. Bài tập tình huống

Một nền tảng logistics nhận các yêu cầu:

1. Tra kiện hàng theo mã vận đơn `tracking_no` mà đối tác cung cấp. Mã có thể trùng giữa các đối tác.
2. Tra kiện hàng bằng ID kỹ thuật, giữ nguyên ngay cả khi đối tác sửa mã vận đơn.
3. Hiển thị 100 lần quét mã gần nhất của một kiện trong ngày.
4. Cảm biến có thể gửi bản ghi lúc 10:00 vào 13:00; giao diện phải sắp xếp theo **lúc quét thực tế**.
5. Một đối tác gửi cùng event ba lần vì timeout mạng.

**Gợi ý giải:**

1. Đường tra cứu theo `(partner_id, tracking_no)`; chuẩn hóa mã và kiểm soát xung đột theo quy tắc nghiệp vụ.
2. Sinh `package_id uuid` một lần; bảng `packages_by_id` lưu dữ liệu chính, bảng tra theo tracking number lưu ánh xạ.
3. Nếu xem theo thời điểm phát sinh/ghi event, dùng `PRIMARY KEY ((package_id, day_bucket), event_id)` với `event_id timeuuid` và `DESC`; đo khả năng partition quá lớn.
4. Dùng `scan_time timestamp` làm clustering column, thêm `event_id uuid` để phân biệt nhiều event tại cùng timestamp. timeuuid sinh lúc 13:00 không phản ánh sự kiện lúc 10:00.
5. Sinh và giữ `event_id` ổn định qua các lần gửi lại; bổ sung quy trình idempotency và đối soát khi chưa rõ kết quả của lần ghi trước.

### Tự kiểm tra

1. Vì sao bảng `PRIMARY KEY ((tenant_id, sku))` không tự hỗ trợ liệt kê toàn bộ sản phẩm theo `tenant_id`?
2. Một UUID v4 có thể chèn trực tiếp vào cột `timeuuid` không?
3. Đặt `event_id timeuuid` làm cột thường có tự cho phép `ORDER BY event_id DESC` không?
4. Tại sao đổi SKU nằm trong primary key đòi hỏi hàng mới và xử lý hàng cũ?
5. Vì sao `UUID.randomUUID()` gọi lại khi retry có thể dẫn tới dữ liệu trùng nghiệp vụ?

**Đáp án ngắn:** (1) thiếu thành phần partition key `sku`; (2) không, `timeuuid` yêu cầu UUID v1; (3) không, thứ tự truy vấn phụ thuộc clustering columns; (4) primary key bất biến tại vị trí lưu; (5) mỗi retry có khóa mới nên Cassandra xem đó là hàng khác.

## 12. Checklist khi thiết kế định danh Cassandra

- [ ] Đã xác định rõ khóa nghiệp vụ, ID kỹ thuật và những truy vấn cần hỗ trợ.
- [ ] Phân biệt **toàn bộ primary key**, **partition key** và **clustering columns**.
- [ ] Mã nghiệp vụ có phạm vi duy nhất, chuẩn hóa và chính sách đổi mã rõ ràng.
- [ ] Phân biệt CQL `uuid` (có thể lưu nhiều phiên bản UUID, thường dùng v4 để định danh ngẫu nhiên) với `timeuuid` (yêu cầu UUID v1 hợp lệ).
- [ ] Biết rõ thứ tự cần theo **lúc sinh ID** hay **thời gian nghiệp vụ**.
- [ ] Mỗi truy vấn trả dữ liệu trong phạm vi có thể đo được; có bucket/paging khi cần.
- [ ] ID được giữ ổn định qua retry; đã xác định yêu cầu uniqueness/LWT nếu có.
- [ ] Đã đánh giá hot partition, dữ liệu trùng giữa access table, TTL/tombstone và consistency.
- [ ] Đã thử query pattern với dữ liệu đại diện và đo p95/p99 cùng số partition bị truy cập.

## Tài liệu tham khảo

- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL Types](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Functions](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/functions.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
