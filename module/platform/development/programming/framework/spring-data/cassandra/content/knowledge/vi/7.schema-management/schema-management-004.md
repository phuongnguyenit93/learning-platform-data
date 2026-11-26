# RECREATE, RECREATE_DROP_UNUSED và phạm vi dữ liệu bị xóa trong Spring Data Cassandra

Trong Spring Data Cassandra, hai giá trị cấu hình **`SchemaAction.RECREATE`** và **`SchemaAction.RECREATE_DROP_UNUSED`** có thể khiến dữ liệu biến mất **ngay khi ứng dụng khởi động**. Đây là các chế độ quản lý lược đồ phục vụ việc tái tạo cấu trúc bảng, không phải cơ chế migration giữ nguyên dữ liệu. Điểm khác nhau quan trọng nhất là **phạm vi đối tượng bị DROP**: chỉ những bảng và user-defined type (UDT) ứng dụng nhận diện, hay cả những bảng và UDT trong keyspace mà ứng dụng không biết đến.

Bài học thuộc chương **Quản lý lược đồ** của `SPRING_DATA_CASSANDRA`. Mục tiêu là xác định chính xác điều gì sẽ bị xóa, vì sao một bảng không có `@Table` trong ứng dụng vẫn có thể mất dữ liệu, cách cấu hình schema action trong Spring Boot, và cách dùng quy trình thay đổi schema an toàn cho ứng dụng có entity mapping, repository, CassandraTemplate và truy vấn CQL.

> **Cảnh báo thực hành:** Chỉ thử `RECREATE` hoặc `RECREATE_DROP_UNUSED` trên keyspace dùng riêng để học/test và chấp nhận xóa sạch dữ liệu. Với dữ liệu cần giữ, đặt `schema-action: NONE` và quản lý các thay đổi bằng CQL/migration được kiểm soát. Không thử hai chế độ này trên keyspace production hoặc keyspace dùng chung.

## 1. SchemaAction là gì và chạy khi nào?

Apache Cassandra yêu cầu định nghĩa **keyspace**, **table**, khóa phân vùng/clustering, chỉ mục và các kiểu dữ liệu tùy chỉnh trước khi truy vấn dữ liệu. Spring Data Cassandra có cơ chế dựng một phần schema từ metadata của các lớp Java, thông qua `SchemaAction` trong package:

```java
org.springframework.data.cassandra.config.SchemaAction
```

Tại quá trình **khởi tạo thành phần kết nối/session factory** của ứng dụng, Spring Data Cassandra có thể chạy các thao tác tạo hoặc xóa đối tượng CQL theo giá trị SchemaAction được cấu hình. Đây là thao tác lúc khởi tạo ứng dụng, **không phải** mỗi khi gọi `repository.save()`, `repository.findById()` hoặc `cassandraTemplate.select(...)`.

Các lựa chọn phổ biến:

| SchemaAction | Ý nghĩa chính | Có xóa dữ liệu hiện có? |
|---|---|---|
| `NONE` | Không tạo/xóa bảng hay UDT tự động | Không do schema action |
| `CREATE` | Tạo schema dựa trên entity/UDT đã mapping; báo lỗi nếu đối tượng cần tạo đã tồn tại | Không chủ động DROP, nhưng có thể khiến khởi động thất bại |
| `CREATE_IF_NOT_EXISTS` | Tạo đối tượng còn thiếu; bỏ qua tên đã tồn tại | Không chủ động DROP; **không tự cập nhật schema cũ** |
| `RECREATE` | DROP rồi tạo lại **các bảng/UDT được ứng dụng biết và quản lý** | **Có**, trên các đối tượng bị DROP |
| `RECREATE_DROP_UNUSED` | DROP **mọi bảng/UDT trong keyspace được nhắm tới**, rồi chỉ tạo lại những đối tượng ứng dụng biết | **Có**, kể cả trên bảng/UDT ngoài mapping |

`NONE` là mặc định của cơ chế schema action. Khi cần chỉnh sửa schema đang chứa dữ liệu, không nên coi `CREATE_IF_NOT_EXISTS` là một migration tự động: nếu bảng `orders_by_id` đã tồn tại, thêm field vào Java entity không có nghĩa Cassandra tự chạy `ALTER TABLE ... ADD`.

Tài liệu tham khảo chính thức của Spring Data Cassandra mô tả cả hai chế độ `RECREATE` và `RECREATE_DROP_UNUSED` là **thao tác phá hủy dữ liệu**. Phạm vi chi tiết của việc xử lý UDT, chỉ mục và phụ thuộc schema cần được đối chiếu với phiên bản Spring Data/Cassandra đang sử dụng.

## 2. Ví dụ nhất quán: một keyspace có bảng của ứng dụng và bảng bên ngoài

Giả sử ta có keyspace **`schema_lab`** chạy trên một Cassandra node ở datacenter `dc1`. Chỉ dùng trong môi trường học tập:

```sql
CREATE KEYSPACE IF NOT EXISTS schema_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 1
}
AND durable_writes = true;
```

Trong keyspace này có ba bảng:

```sql
CREATE TABLE schema_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_status text,
    total_amount decimal
);

CREATE TABLE schema_lab.orders_by_customer_month (
    customer_id uuid,
    bucket_month date,
    created_at timestamp,
    order_id uuid,
    total_amount decimal,
    PRIMARY KEY ((customer_id, bucket_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

CREATE TABLE schema_lab.legacy_audit (
    audit_id uuid PRIMARY KEY,
    description text
);
```

- `orders_by_id`: bảng phục vụ tra cứu đơn hàng theo ID; ứng dụng **có entity `@Table`** tương ứng.
- `orders_by_customer_month`: bảng đọc danh sách đơn theo khách/tháng; ứng dụng **có entity `@Table`** tương ứng.
- `legacy_audit`: bảng được một công cụ khác hoặc nhóm khác tạo bằng CQL; trong ứng dụng Spring này **không có entity được quét và mapping vào bảng**.

Hai bảng đầu tiên phục vụ thiết kế dữ liệu theo truy vấn, với partition key và clustering phù hợp đường đọc. Bảng thứ ba cố ý không nằm trong tập entity của ứng dụng để quan sát sự khác nhau giữa hai schema action.

Có thể tạo thử dữ liệu:

```sql
INSERT INTO schema_lab.orders_by_id
    (order_id, customer_id, order_status, total_amount)
VALUES
    (11111111-1111-1111-1111-111111111111,
     22222222-2222-2222-2222-222222222222,
     'NEW', 120.00);

INSERT INTO schema_lab.legacy_audit
    (audit_id, description)
VALUES
    (33333333-3333-3333-3333-333333333333,
     'Seed data from external tool');
```

Đến đây, ta có dữ liệu mẫu để trả lời hai câu hỏi: **bảng nào còn tồn tại** và **hàng nào còn tồn tại** sau mỗi lần khởi động ứng dụng với một schema action.

## 3. “Ứng dụng biết bảng” nghĩa là gì?

Spring Data Cassandra thường nhận diện những thực thể được đánh dấu `@Table` và những UDT được đánh dấu `@UserDefinedType`, trong **phạm vi package được cấu hình để quét**. Nó không tự động xem mọi bảng đang có trong Cassandra là một entity cần tạo lại.

Ví dụ entity cho bảng `orders_by_id`:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("order_status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    // Bổ sung constructor, getter/setter.
}
```

Với bảng thứ hai, lớp `OrderByCustomerMonth` cần mapping đầy đủ partition key tổng hợp `(customer_id, bucket_month)` và clustering key `(created_at, order_id)`. Ví dụ bài học giả định lớp ấy đã được khai báo `@Table("orders_by_customer_month")` và được quét. Không cần thêm lớp Java cho `legacy_audit` vì mục đích của ví dụ là xem điều gì xảy ra với một bảng **không được mapping**.

**Phân biệt ba trạng thái:**

1. **Bảng tồn tại trong Cassandra:** ví dụ `legacy_audit` được tạo thủ công.
2. **Lớp Java tồn tại trong source code:** chưa chắc được Spring Data nhận diện; có thể thiếu `@Table` hoặc nằm ngoài package scan.
3. **Bảng được Spring Data mapping trong ứng dụng hiện tại:** có entity phù hợp và được đưa vào metadata của quá trình quản lý schema.

Với `RECREATE`, trạng thái thứ ba quyết định nhóm đối tượng được tái tạo. Với `RECREATE_DROP_UNUSED`, những bảng tồn tại trong keyspace **nhưng nằm ngoài nhóm ấy cũng bị nhắm tới để xóa**.

Điều này đặc biệt quan trọng khi deploy một service chỉ quản lý một phần keyspace, hoặc vô tình đổi cấu hình `entity-base-packages` khiến Spring không tìm thấy entity như mong đợi.

## 4. RECREATE: xóa và tạo lại những đối tượng đã mapping

Theo tài liệu chính thức, `SchemaAction.RECREATE` **drop và recreate các bảng, UDT hiện có mà ứng dụng biết là đang sử dụng**. Những bảng/UDT không được cấu hình trong ứng dụng **không bị drop bởi hành động này**.

Với ví dụ ở mục 2:

```text
Trước khởi động:
schema_lab
  orders_by_id                [mapped, có dữ liệu]
  orders_by_customer_month    [mapped, có thể có dữ liệu]
  legacy_audit                [unmapped, có dữ liệu]

SchemaAction.RECREATE
  DROP orders_by_id
  DROP orders_by_customer_month
  CREATE orders_by_id
  CREATE orders_by_customer_month

Sau khởi động thành công:
  orders_by_id                [còn bảng, dữ liệu cũ đã mất]
  orders_by_customer_month    [còn bảng, dữ liệu cũ đã mất]
  legacy_audit                [còn bảng, dữ liệu được giữ]
```

Các dòng `DROP` và `CREATE` là **mô hình logic** để hiểu phạm vi hành động; không phải bản log chính xác hoặc bảo đảm thứ tự DDL của một phiên bản Spring Data cụ thể. Nếu có UDT và các ràng buộc phụ thuộc, quá trình thực tế có thể bao gồm thao tác với UDT/index và có thể lỗi giữa chừng.

### Hậu quả dữ liệu cần nhớ

- **Mất dữ liệu trên bảng mapped:** lệnh `DROP TABLE` loại bỏ bảng cùng dữ liệu bên trong, rồi lệnh `CREATE TABLE` tạo một bảng **rỗng** với cùng tên.
- **Bảng không mapping không bị xóa vì RECREATE:** `legacy_audit` vẫn nằm trong keyspace với dữ liệu cũ, nếu không chịu tác động từ các tác vụ khác.
- **Không tự migrate dữ liệu:** những hàng của `orders_by_id` không được copy sang định nghĩa mới, dù các cột và tên bảng không thay đổi.
- **Thay đổi entity có thể làm kết quả khác:** nếu chuyển tên bảng trong `@Table` từ `orders_by_id` sang `orders_current`, tên cũ không còn nằm trong nhóm mapped; `RECREATE` sẽ tạo bảng mới, nhưng không tự coi bảng cũ là đối tượng cần drop.

Ví dụ, sau khi `RECREATE` chạy xong:

```sql
SELECT *
FROM schema_lab.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;

SELECT *
FROM schema_lab.legacy_audit
WHERE audit_id = 33333333-3333-3333-3333-333333333333;
```

Truy vấn đầu dự kiến không còn hàng cũ; truy vấn thứ hai dự kiến vẫn trả về hàng audit. Kết luận áp dụng khi bài lab bắt đầu đúng trạng thái mô tả và không có writer khác chèn lại dữ liệu sau khi schema action chạy.

## 5. RECREATE_DROP_UNUSED: xóa cả những bảng không được mapping

`SchemaAction.RECREATE_DROP_UNUSED` có phạm vi rộng hơn: **drop tất cả các bảng và UDT trong keyspace mục tiêu**, rồi **chỉ tạo lại những bảng/UDT mà ứng dụng biết**. Từ “unused” dễ gây hiểu nhầm: nó không có nghĩa Spring chỉ xóa những bảng “đã được xác minh không còn người dùng”; ở đây nó là **những đối tượng không thuộc metadata mapping của ứng dụng hiện tại**.

Với cùng ví dụ:

```text
Trước khởi động:
schema_lab
  orders_by_id                [mapped, có dữ liệu]
  orders_by_customer_month    [mapped, có thể có dữ liệu]
  legacy_audit                [unmapped, có dữ liệu]

SchemaAction.RECREATE_DROP_UNUSED
  DROP orders_by_id
  DROP orders_by_customer_month
  DROP legacy_audit
  CREATE orders_by_id
  CREATE orders_by_customer_month

Sau khởi động thành công:
  orders_by_id                [còn bảng, rỗng]
  orders_by_customer_month    [còn bảng, rỗng]
  legacy_audit                [không còn bảng, mất dữ liệu]
```

**Hai cấp độ mất dữ liệu:**

1. Dữ liệu trong **mọi bảng được ứng dụng mapping** bị xóa vì bảng bị drop/recreate.
2. Dữ liệu trong **các bảng không mapping** cũng bị xóa vì bảng bị drop và **không được tạo lại**.

Nếu một bảng chỉ được sử dụng bởi **service B** nhưng cả service A và B dùng chung keyspace, service A chạy `RECREATE_DROP_UNUSED` có thể xóa bảng của B dù source code của A chưa từng nhắc tới bảng đó. Đây là lý do chế độ này chỉ phù hợp với keyspace test có quyền sở hữu và phạm vi xóa được kiểm soát rất chặt.

Không được hiểu `RECREATE_DROP_UNUSED` là “chỉ dọn bảng thừa và bảo toàn dữ liệu ở các bảng còn dùng”. **Mọi bảng bị tái tạo đều mất dữ liệu**, kể cả bảng vẫn dùng.

## 6. Bảng so sánh phạm vi DROP và kết quả sau khi tạo lại

Giả định chỉ có ứng dụng đang thực hiện schema action, thao tác DDL hoàn tất thành công, và không có cơ chế khôi phục/seed dữ liệu tự động nào khác.

| Đối tượng ban đầu | Có metadata mapping? | Sau `RECREATE` | Sau `RECREATE_DROP_UNUSED` |
|---|---|---|---|
| `orders_by_id` | Có | Bảng được tái tạo; **dữ liệu cũ mất** | Bảng được tái tạo; **dữ liệu cũ mất** |
| `orders_by_customer_month` | Có | Bảng được tái tạo; **dữ liệu cũ mất** | Bảng được tái tạo; **dữ liệu cũ mất** |
| `legacy_audit` | Không | Bảng và dữ liệu vẫn giữ | **Bảng bị drop**, không tự tái tạo |
| Một UDT được đánh dấu `@UserDefinedType` và được quét | Có | Bị drop/recreate nếu thuộc tập được quản lý | Bị drop/recreate |
| Một UDT trong keyspace nhưng ứng dụng không biết | Không | Không thuộc phạm vi DROP của action | Bị nhắm tới để drop |
| Bảng trong **keyspace khác** | Không thuộc keyspace mục tiêu | Không nằm trong phạm vi action | Không nằm trong phạm vi action |
| Chính **keyspace mục tiêu** | Không phải table/UDT | Không bị action này chủ động `DROP KEYSPACE` | Không bị action này chủ động `DROP KEYSPACE` |

**Điểm ranh giới:** hành vi được mô tả nằm ở **keyspace mà ứng dụng đang quản lý**, không phải toàn cluster. `RECREATE_DROP_UNUSED` là quét bảng/UDT trong **keyspace ấy**, không phải lệnh xóa mọi keyspace của Cassandra.

Đừng mở rộng nhận định trên thành một bảo đảm rằng mọi đối tượng khác như materialized view, role, function, hoặc chính sách bảo mật sẽ được xử lý giống nhau. Spring Data Cassandra tài liệu hóa schema action chủ yếu cho **bảng và UDT**. Chỉ mục gắn với bảng bị drop có thể biến mất theo thao tác xóa bảng; các đối tượng và quan hệ phụ thuộc khác cần kiểm tra theo phiên bản Cassandra, DDL thực tế và quyền truy cập.

## 7. UDT, index và dependency: phạm vi không chỉ có hàng dữ liệu

### 7.1. User-defined type

Cassandra hỗ trợ **UDT** để nhóm các field thành một kiểu dữ liệu CQL. Spring Data có thể nhận diện các lớp Java với `@UserDefinedType`:

```java
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("shipping_address")
public class ShippingAddress {
    private String street;
    private String city;

    // Bổ sung constructor, getter/setter.
}
```

Một định nghĩa CQL tương ứng về mặt ý tưởng:

```sql
CREATE TYPE schema_lab.shipping_address (
    street text,
    city text
);
```

Nếu UDT này thuộc tập được Spring quản lý, cả hai action `RECREATE` và `RECREATE_DROP_UNUSED` có thể drop rồi tạo lại nó. Nếu có UDT `legacy_metadata` do công cụ khác quản lý mà Spring không biết, **`RECREATE` không nhắm tới nó**, còn **`RECREATE_DROP_UNUSED` có thể drop nó** trong phạm vi keyspace.

UDT có thể được dùng làm kiểu cột của bảng; các thao tác `DROP TYPE` bị chi phối bởi dependency. Không nên kỳ vọng quá trình xóa luôn thành công nếu schema còn view, table hoặc type tham chiếu đối tượng đó. Trong môi trường học tập, tránh tạo cấu trúc phụ thuộc phức tạp khi muốn quan sát hành vi cơ bản của hai action.

### 7.2. Index và các đối tượng schema khác

Khi `DROP TABLE`, dữ liệu và các cấu trúc gắn với bảng có thể bị loại bỏ, gồm các index thuộc bảng đó. Nếu mapping có khai báo index, Spring có thể tạo index theo định nghĩa mapping trong phạm vi cơ chế hỗ trợ. Tuy nhiên, không nên giả định mọi index tạo thủ công hoặc mọi tính năng Cassandra đều được khôi phục tự động sau `CREATE TABLE`.

Ví dụ:

```sql
CREATE INDEX IF NOT EXISTS orders_status_idx
ON schema_lab.orders_by_id (order_status);
```

Nếu bảng `orders_by_id` bị drop rồi tạo lại, ứng dụng phải xác minh index cần thiết có được tạo lại hay không. **`CREATE TABLE` không đồng nghĩa tự tạo lại toàn bộ cấu trúc phụ từng tồn tại**.

Đối với truy vấn quan trọng, nên ưu tiên thiết kế bảng theo **partition key và clustering key**; một index mới không thay thế được việc đánh giá phân bố dữ liệu, cardinality và truy vấn CQL.

## 8. Cấu hình Spring Boot cho một keyspace test

Với **Spring Boot 3.x/4.x** trong những phiên bản có tích hợp property tương ứng, khóa cấu hình là **`spring.cassandra.schema-action`**. Ví dụ profile chỉ dùng ở môi trường lab:

```yaml
# application-schema-lab.yml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: schema_lab
    schema-action: RECREATE
```

Đổi giá trị dòng cuối thành `RECREATE_DROP_UNUSED` sẽ thay đổi phạm vi xóa như mục 5. **Đây không phải cấu hình khuyên dùng cho production**.

Ứng dụng cần chọn đúng keyspace (`schema_lab`), đúng DC và có quyền DDL nếu muốn schema action thực thi. Nếu không thể `DROP` hoặc `CREATE`, quá trình khởi tạo có thể lỗi; việc một thao tác đã thực hiện trước lỗi có được tự phục hồi hay không không được bảo đảm.

### Cấu hình nên dùng khi có dữ liệu cần giữ

```yaml
# application-prod.yml
spring:
  cassandra:
    contact-points: cassandra-1.internal,cassandra-2.internal
    local-datacenter: dc1
    keyspace-name: orders_prod
    schema-action: NONE
```

Với `NONE`, ứng dụng không yêu cầu cơ chế schema action tự động drop/create các bảng và UDT. Các thay đổi schema được thực hiện ở một quy trình migration có kiểm soát, dùng CQL hoặc công cụ vận hành phù hợp. Cấu hình `NONE` **không ngăn** code khác chủ động gửi `DROP TABLE` qua `CqlSession`, script startup tùy biến hoặc công cụ quản trị; đây chỉ là lựa chọn cho một cơ chế quản lý schema cụ thể.

Với một số phiên bản Spring Boot cũ hơn, tiền tố property từng là **`spring.data.cassandra.*`**. Cần kiểm tra đúng phiên bản dependency và property metadata trong dự án, không sao chép mù quáng giữa các phiên bản.

### Cấu hình bằng Java

Khi dùng cấu hình Spring Data Cassandra dựa trên `AbstractCassandraConfiguration`, có thể ghi đè phương thức:

```java
import org.springframework.data.cassandra.config.SchemaAction;

// Trong lớp cấu hình kế thừa AbstractCassandraConfiguration:
@Override
public SchemaAction getSchemaAction() {
    return SchemaAction.NONE;
}
```

Nếu thay `NONE` thành `RECREATE` hoặc `RECREATE_DROP_UNUSED`, hãy giới hạn trong cấu hình test rõ ràng. Dùng Spring Boot auto-configuration thì thường không cần ghi đè phương thức Java; nên quản lý schema action từ property/profile để tránh nhiều nơi cấu hình có ý nghĩa chồng chéo.

## 9. Một thí nghiệm minh họa hai action

Mục tiêu của thí nghiệm là **quan sát sự khác biệt**, không dùng để cập nhật cơ sở dữ liệu thật.

### Chuẩn bị

1. Dùng một Cassandra instance dùng riêng cho lab và keyspace `schema_lab`.
2. Tạo ba bảng ở mục 2; đảm bảo chỉ hai bảng `orders_by_id` và `orders_by_customer_month` có entity được Spring nhận diện.
3. Seed ít nhất một hàng trong `orders_by_id` và `legacy_audit`.
4. Ghi lại danh sách các bảng và dữ liệu mẫu bằng truy vấn đọc.
5. Chạy ứng dụng test với `schema-action: RECREATE` và **không để một ứng dụng khác cùng ghi vào keyspace**.

Lệnh kiểm tra bảng trước/sau:

```sql
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'schema_lab';
```

Kiểm tra hàng theo khóa bằng các truy vấn `SELECT ... WHERE <primary-key> = ...` như đã viết tại mục 4. Dữ liệu ở `orders_by_id` mất, còn hàng trong `legacy_audit` được giữ là kết quả dự kiến nếu các giả định của bài lab đúng.

### Thử lần thứ hai trên một keyspace lab đã tạo lại

1. Tạo lại dữ liệu test trong ba bảng, vì bảng mapped đã bị reset ở lần đầu.
2. Dừng ứng dụng test trước đó; khởi chạy riêng phiên bản dùng `schema-action: RECREATE_DROP_UNUSED`.
3. Kiểm tra `system_schema.tables` và các truy vấn đọc.

Kết quả dự kiến: `orders_by_id` và `orders_by_customer_month` có bảng mới nhưng rỗng; `legacy_audit` **không còn tồn tại**. Câu lệnh `SELECT ... FROM schema_lab.legacy_audit` không còn thành công vì bảng đã bị drop.

Ví dụ quan sát:

| Trước schema action | Sau `RECREATE` | Sau `RECREATE_DROP_UNUSED` |
|---|---|---|
| 2 bảng mapped + 1 bảng unmapped | 2 bảng mapped rỗng + 1 bảng unmapped còn dữ liệu | 2 bảng mapped rỗng; bảng unmapped biến mất |
| Dữ liệu `orders_by_id` có hàng | Hàng cũ mất | Hàng cũ mất |
| Dữ liệu `legacy_audit` có hàng | Hàng còn | Bảng và hàng đều mất |

Thí nghiệm nên được thực hiện **riêng từng lần từ trạng thái đầu vào đã biết**. Nếu chạy `RECREATE_DROP_UNUSED` sau `RECREATE` mà không seed lại, kết quả cũng cho thấy `legacy_audit` bị drop, nhưng sẽ không phân biệt được dữ liệu `orders_by_id` đã mất ở lần nào.

## 10. Những tình huống mất dữ liệu thường bị bỏ sót

### 10.1. Đổi tên entity hoặc tên bảng

Ban đầu:

```java
@Table("orders_by_id")
public class OrderById {
    // ...
}
```

Sau đó đổi thành:

```java
@Table("orders_current")
public class OrderCurrent {
    // ...
}
```

Nếu ứng dụng không còn nhận diện `orders_by_id` nhưng keyspace vẫn chứa bảng cũ:

- Với **`RECREATE`**, bảng `orders_current` được tạo theo mapping mới; `orders_by_id` nằm ngoài tập mapped nên vẫn còn nếu không có thao tác khác tác động.
- Với **`RECREATE_DROP_UNUSED`**, bảng `orders_by_id` bị drop vì không còn thuộc tập mapping; bảng `orders_current` được tạo mới.

Không có hành vi **rename table và giữ hàng** tự động. Muốn đổi cách tổ chức dữ liệu theo partition key hoặc clustering key, thường phải thiết kế bảng mới và chuyển/backfill dữ liệu.

### 10.2. Quét sai package entity

Nếu entity `OrderById` vô tình bị di chuyển ra ngoài phạm vi component/entity scanning:

- `RECREATE` không còn nhắm đến bảng đó như một bảng đã biết.
- `RECREATE_DROP_UNUSED` vẫn quét bảng hiện có của keyspace để xóa, trong khi không còn metadata để tạo lại bảng vừa bị bỏ sót.

Đây là một lỗi đặc biệt nguy hiểm: **thay đổi phạm vi scan của Java code có thể thay đổi phạm vi dữ liệu bị xóa** dù không ai sửa CQL.

### 10.3. Nhiều service chia sẻ keyspace

Service A quản lý `orders_by_id`, service B quản lý `invoices_by_id`; cả hai kết nối cùng keyspace. Nếu A chạy `RECREATE_DROP_UNUSED`, `invoices_by_id` không có trong mapping của A nên có nguy cơ bị drop. Việc B vẫn đang chạy repository bình thường **không bảo vệ** bảng khỏi thao tác DDL của A.

Ngay cả `RECREATE` cũng không phù hợp với hệ thống đang chạy thật: nếu service A tái tạo `orders_by_id`, các service khác có thể thấy bảng tạm thời không tồn tại và dữ liệu biến mất.

### 10.4. Khởi động lại nhiều lần

Schema action không tự “ghi nhớ rằng đã chạy hôm qua”. Nếu profile vẫn dùng `RECREATE`, mỗi lần ứng dụng khởi tạo cơ chế schema tương ứng có thể tiếp tục drop/recreate bảng. Dữ liệu vừa ghi sau lần khởi động trước **cũng có thể mất ở lần khởi động sau**.

Tương tự, `RECREATE_DROP_UNUSED` có thể xóa lại những bảng được service khác tạo giữa hai lần restart.

### 10.5. Đã có replica thì không lo mất dữ liệu?

Replication factor và consistency level điều chỉnh cách đọc/ghi dữ liệu giữa các replica, **không biến `DROP TABLE` hợp lệ thành một thao tác giữ dữ liệu**. Nếu DDL xóa bảng được áp dụng trong cluster, các bản sao dữ liệu của bảng cũng chịu tác động. Không thể khôi phục hàng chỉ bằng cách nâng `LOCAL_ONE` thành `LOCAL_QUORUM` sau khi bảng đã bị drop.

Tùy cấu hình Cassandra, snapshot/backups trước thao tác DDL có thể tồn tại; khả năng phục hồi phụ thuộc việc **đã có bản sao lưu hợp lệ, quy trình khôi phục đã kiểm chứng và thời gian lưu trữ**. Không mặc định có rollback tự động cho thao tác `RECREATE`.

## 11. Tại sao CREATE_IF_NOT_EXISTS không phải migration?

Một câu hỏi thường gặp: “Nếu cần thêm cột, vì sao không chọn `CREATE_IF_NOT_EXISTS` thay vì `RECREATE`?”.

Giả sử bảng `orders_by_id` đã tồn tại, và Java entity được thêm field `shipping_note`. Với `CREATE_IF_NOT_EXISTS`, tên bảng đã tồn tại nên thao tác tạo bảng được bỏ qua. **Cột `shipping_note` không tự xuất hiện** chỉ vì entity đã thay đổi.

Thay đổi nhỏ tương thích có thể dùng migration CQL rõ ràng:

```sql
ALTER TABLE schema_lab.orders_by_id
ADD shipping_note text;
```

Lệnh này thêm cột mà không drop cả bảng. Tuy nhiên, nó vẫn là thay đổi schema phân tán; cần quan tâm schema agreement, client compatibility và quá trình rollout. Không phải mọi thay đổi đều là `ALTER TABLE` đơn giản: **partition key và clustering key không thể tùy ý sửa theo cách giữ nguyên dữ liệu**. Khi đổi access pattern hoặc primary key, cần tạo bảng mới, backfill và chuyển traffic có kiểm soát.

So sánh mục đích:

| Nhu cầu | Cách xử lý phù hợp |
|---|---|
| Tạo bảng lần đầu trên keyspace rỗng | `CREATE` hoặc migration CQL |
| Chạy lab/test và chủ động muốn bảng mapped rỗng lại | `RECREATE` với keyspace cô lập |
| Reset hoàn toàn bảng/UDT trong keyspace lab rồi dựng lại đúng tập mapping | `RECREATE_DROP_UNUSED` với keyspace cô lập |
| Giữ dữ liệu và thêm cột tùy chọn | Migration `ALTER TABLE ... ADD` được kiểm soát |
| Đổi partition/clustering key | Tạo bảng mới, backfill, chuyển đổi đọc/ghi |
| Production có dữ liệu | `NONE` + quy trình migration, backup và phê duyệt thay đổi |

`CassandraTemplate`, repository hay `CqlSession` đều có thể truy vấn dữ liệu nhưng không tự thay thế công việc lập kế hoạch migration. Đường đọc hiệu quả vẫn phụ thuộc partition key, clustering, paging, consistency và thiết kế bảng theo truy vấn.

## 12. Cách triển khai schema change có kiểm soát thay vì DROP

Với một bảng cần giữ dữ liệu, quy trình tham khảo:

1. **Xác định yêu cầu:** thay đổi cột đơn giản hay thay đổi mô hình truy vấn/primary key?
2. **Xem schema thực tế:** đối chiếu DDL của keyspace, table, index và UDT; xác định dịch vụ nào cùng sử dụng.
3. **Đánh giá tương thích:** phiên bản ứng dụng cũ và mới có thể cùng chạy với schema chuyển tiếp không?
4. **Lập kế hoạch dữ liệu:** backup/snapshot đã kiểm chứng; nếu tạo bảng mới thì có bước backfill và đối soát.
5. **Thử migration:** chạy trên môi trường chứa dữ liệu/tải đại diện, đo thời gian và kiểm tra lỗi.
6. **Triển khai theo thứ tự:** tạo schema cần thiết trước, sau đó triển khai code có thể đọc/ghi theo mô hình mới, rồi chuyển traffic.
7. **Quan sát:** theo dõi schema agreement, lỗi CQL, latency, tombstone, compaction và kết quả truy vấn.
8. **Thu hồi bảng cũ sau cùng:** chỉ khi chắc chắn các reader/writer cũ đã ngừng dùng và dữ liệu được kiểm chứng.

Nếu chuyển từ `orders_by_id` sang bảng `orders_by_customer_month` để tối ưu truy vấn danh sách, đây là **một thiết kế dữ liệu bổ sung**. Quy trình có thể gồm tạo bảng mới, đồng bộ ghi mới sang cả hai bảng, backfill dữ liệu lịch sử và so sánh số lượng/kết quả theo partition. `RECREATE_DROP_UNUSED` hoàn toàn không thực hiện công việc backfill đó.

Trong Cassandra phân tán, việc chạy DDL cần được điều phối để các node và ứng dụng có đủ thời gian nhận schema mới. Không nên để mỗi instance của một microservice tự chạy `RECREATE` khi triển khai nhiều replica ứng dụng: các lần khởi động song song có thể gây lỗi DDL, truy vấn tạm thời thất bại và mất dữ liệu lặp lại.

## 13. Kiểm tra keyspace và các đối tượng trước/sau thay đổi

Để xác định những đối tượng đang tồn tại, có thể dùng metadata CQL:

```sql
-- Các bảng trong keyspace cụ thể
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'schema_lab';

-- Các user-defined type trong keyspace
SELECT type_name
FROM system_schema.types
WHERE keyspace_name = 'schema_lab';

-- Các chỉ mục được khai báo
SELECT table_name, index_name
FROM system_schema.indexes
WHERE keyspace_name = 'schema_lab';
```

Trong `cqlsh` có thể xem DDL cụ thể:

```sql
DESCRIBE KEYSPACE schema_lab;
DESCRIBE TABLE schema_lab.orders_by_id;
```

`DESCRIBE` là tiện ích của `cqlsh`; còn `system_schema.*` là các bảng metadata Cassandra cho phép truy vấn bằng CQL. Lệnh liệt kê bảng **không chứng minh dữ liệu hàng đã mất hay chưa**; cần chọn một số primary key mẫu và đọc lại bằng truy vấn `SELECT`.

Nếu ứng dụng đã chạy sai schema action, trước tiên cần xác định **keyspace nào**, **các table/UDT nào**, **bản deploy/profile nào**, **thời điểm khởi động** và **backup/snapshot nào đang tồn tại**. Việc bật lại schema action phá hủy hoặc restart thêm ứng dụng khi chưa biết trạng thái có thể làm khó điều tra hơn. Phục hồi cần dựa vào bản sao lưu hoặc nguồn dữ liệu có thể tái tạo và quy trình đã thử nghiệm; tự chạy `CREATE TABLE` chỉ tạo cấu trúc rỗng.

## 14. Các nhận định đúng và sai cần ghi nhớ

| Nhận định | Đánh giá và giải thích |
|---|---|
| “`RECREATE` chỉ cập nhật schema nhưng giữ hàng.” | **Sai.** Nó drop/recreate những bảng mapped, nên dữ liệu hiện có bị mất. |
| “`RECREATE_DROP_UNUSED` chỉ xóa bảng không dùng.” | **Sai.** Nó xóa cả mapped lẫn unmapped rồi chỉ tạo lại mapped. |
| “Một bảng không có `@Table` sẽ an toàn với mọi action.” | **Sai.** `RECREATE_DROP_UNUSED` vẫn có thể drop bảng đó trong keyspace. |
| “`RECREATE_DROP_UNUSED` xóa toàn cluster.” | **Sai.** Phạm vi chính của action là các table/UDT trong keyspace mục tiêu. |
| “Không thay Java entity nên restart không mất dữ liệu.” | **Sai** nếu vẫn giữ cấu hình `RECREATE`; startup tiếp theo vẫn có thể drop/recreate. |
| “`CREATE_IF_NOT_EXISTS` sẽ thêm cột còn thiếu.” | **Sai.** Nó có thể giữ schema cũ và không thực hiện migration. |
| “RF=3 sẽ tự khôi phục bảng sau DROP.” | **Sai.** Replication không thay thế backup/migration. |
| “`NONE` là lựa chọn hợp lý khi tự quản lý migration.” | **Đúng.** Nó tắt việc tự động tạo/xóa bảng/UDT do SchemaAction. |

## 15. Bài tập tình huống có đáp án

**Tình huống 1.** Keyspace `schema_lab` có `orders_by_id`, `legacy_audit`. Ứng dụng chỉ mapping `orders_by_id`. Cả hai bảng đều có dữ liệu. Khi startup dùng `RECREATE`, bảng nào mất dữ liệu?

**Đáp án:** `orders_by_id` bị drop/recreate và mất dữ liệu cũ. `legacy_audit` không được mapping nên nằm ngoài phạm vi drop của `RECREATE`.

**Tình huống 2.** Giữ nguyên schema, chuyển sang `RECREATE_DROP_UNUSED`. Bảng nào còn lại sau khi startup thành công?

**Đáp án:** `orders_by_id` được tạo lại nhưng rỗng; `legacy_audit` bị drop và không được tạo lại vì không có mapping.

**Tình huống 3.** Một bản deploy vô tình không scan được bất kỳ lớp `@Table` nào, nhưng keyspace chứa hàng chục bảng do nhiều service quản lý. Rủi ro lớn nhất nếu dùng `RECREATE_DROP_UNUSED`?

**Đáp án:** hành động có thể drop toàn bộ bảng/UDT trong keyspace và gần như không tạo lại gì vì tập metadata được nhận diện rỗng. Đây là lý do không dùng chế độ này trên keyspace dùng chung.

**Tình huống 4.** Cần thêm trường `shipping_note` vào bảng đang chứa dữ liệu production. Có nên đổi schema action thành `RECREATE` trong một lần restart?

**Đáp án:** không. Cần migration `ALTER TABLE ... ADD` (nếu phù hợp), triển khai Java mapping tương thích và kiểm tra kết quả. `RECREATE` sẽ làm mất dữ liệu bảng.

**Tình huống 5.** Đã tắt `RECREATE_DROP_UNUSED` và đổi sang `NONE` sau khi bảng bị drop. Có nghĩa dữ liệu cũ lập tức trở lại?

**Đáp án:** không. `NONE` chỉ ngăn các thao tác schema tự động tiếp theo của cơ chế này. Dữ liệu đã bị drop cần được khôi phục từ backup/snapshot hoặc tái dựng bằng nguồn dữ liệu khác.

## 16. Checklist trước khi đặt SchemaAction

1. **Keyspace có dữ liệu thật không?** Có chấp nhận mất tất cả hàng trong các bảng bị drop không?
2. **Ai sở hữu keyspace?** Có service, công cụ hoặc nhóm khác quản lý bảng/UDT trong đó không?
3. **Đã kiểm tra mapping?** Những lớp `@Table` và `@UserDefinedType` nào thực sự được scan?
4. **Đã hiểu phạm vi?** `RECREATE` tác động nhóm mapped; `RECREATE_DROP_UNUSED` tác động toàn bộ bảng/UDT trong keyspace.
5. **Có restart tự động không?** Mỗi startup có thể chạy lại action và xóa dữ liệu mới được ghi trước đó.
6. **Có bản sao lưu và khôi phục đã thử chưa?** Replication/CL không thay backup.
7. **Có index hoặc UDT phụ thuộc không?** Đã kiểm tra khả năng drop/recreate và thứ tự thay đổi schema?
8. **Có cần migrate dữ liệu?** Nếu muốn giữ hàng, dùng migration phù hợp, không dùng chế độ drop/recreate.
9. **Ứng dụng dùng cấu hình nào thực tế?** Kiểm tra active profile, keyspace, property `spring.cassandra.schema-action` hoặc Java override.
10. **Đã kiểm chứng bằng metadata và dữ liệu?** Quan sát `system_schema`, DDL và truy vấn `SELECT` theo khóa trước/sau trên lab.

Hai công thức dễ nhớ:

- **`RECREATE` = xóa rồi tạo lại những bảng/UDT mà ứng dụng quản lý → mất dữ liệu của nhóm ấy; đối tượng không được mapping thường được giữ.**
- **`RECREATE_DROP_UNUSED` = xóa toàn bộ bảng/UDT trong keyspace mục tiêu → tạo lại riêng nhóm ứng dụng quản lý → mất dữ liệu cả ở bảng được quản lý lẫn bảng ngoài mapping.**

Với Spring Data Cassandra, hãy dùng hai chế độ này đúng mục đích **reset môi trường dùng một lần**. Đối với dữ liệu phân tán cần giữ, kết hợp `SchemaAction.NONE` với kế hoạch schema migration có kiểm soát, thiết kế bảng theo truy vấn và kiểm chứng tính nhất quán là lựa chọn vận hành phù hợp.

## Tài liệu tham khảo

- [Spring Data Cassandra — Schema Management](https://docs.spring.io/spring-data/cassandra/reference/cassandra/schema-management.html): ngữ nghĩa của `NONE`, `CREATE`, `CREATE_IF_NOT_EXISTS`, `RECREATE`, `RECREATE_DROP_UNUSED`, các bảng và UDT được quản lý.
- [Spring Data Cassandra — SchemaAction API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/config/SchemaAction.html): mô tả enum và phạm vi thao tác theo keyspace.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): thuộc tính `spring.cassandra.schema-action` và những thuộc tính kết nối Cassandra khác.
