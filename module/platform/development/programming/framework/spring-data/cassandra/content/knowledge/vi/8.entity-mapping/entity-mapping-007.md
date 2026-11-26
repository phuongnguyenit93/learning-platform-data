# @Transient và @ReadOnlyProperty

Khi ánh xạ **entity** với bảng **Apache Cassandra** bằng **Spring Data Cassandra**, không phải thuộc tính Java nào cũng cần đọc và ghi xuống CQL. Hai annotation dễ bị nhầm lẫn là **`@Transient`** và **`@ReadOnlyProperty`**: cả hai đều giúp tránh ghi một thuộc tính qua cơ chế mapping, nhưng **chỉ một trong hai còn được ánh xạ khi đọc dữ liệu từ Cassandra**.

Bài thuộc chương **Ánh xạ entity** của module **SPRING_DATA_CASSANDRA**. Sau khi học, bạn có thể phân biệt hai annotation, lựa chọn đúng cho các trường tính toán hoặc trường do quy trình khác quản lý, hiểu tác động tới repository, `CassandraTemplate`, CQL, schema và paging, đồng thời tránh những lỗi phát sinh trong mô hình dữ liệu phân tán.

## 1. Phân biệt trong một bảng

| Tiêu chí | `@Transient` | `@ReadOnlyProperty` |
| --- | --- | --- |
| Được Spring Data xem là thuộc tính lưu trữ để ánh xạ từ Cassandra? | **Không** | **Có**, thuộc tính vẫn tham gia mapping khi đọc |
| Đọc giá trị cột từ kết quả CQL vào entity? | **Không** | **Có**, nếu cột phù hợp có mặt trong kết quả và mapping hợp lệ |
| Có trong câu `INSERT`/`UPDATE` được sinh cho entity? | **Không** | **Không** |
| Có cần cột tương ứng trong bảng Cassandra? | Không, vì trường bị loại khỏi mapping | Có, nếu muốn đọc giá trị từ cột đó |
| Thường dùng cho | Trạng thái giao diện, cache tạm, giá trị tính toán chỉ dùng trong Java | Cột được service khác, batch, job hoặc câu CQL riêng ghi và entity hiện tại chỉ đọc |
| Có tự bảo vệ cột khỏi mọi thao tác ghi CQL? | Không áp dụng | **Không**: annotation chỉ giới hạn đường ghi do entity mapping quản lý |

**Quy tắc chọn nhanh:** nếu một thuộc tính **không phải dữ liệu lưu trữ trong bảng**, dùng `@Transient`. Nếu nó **là cột thực trong Cassandra**, ứng dụng cần đọc nhưng **không muốn repository/template ghi đè** khi lưu entity, dùng `@ReadOnlyProperty`.

Hai annotation này thuộc **Spring Data Commons**:

~~~java
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.ReadOnlyProperty;
~~~

Không nhầm `@Transient` của Spring Data với `jakarta.persistence.Transient` trong JPA hoặc từ khóa `transient` của Java. Chúng thuộc các cơ chế khác nhau; khi làm việc với Spring Data Cassandra, nên dùng annotation `org.springframework.data.annotation.Transient`.

## 2. Ví dụ nghiệp vụ: đơn hàng và điểm đánh giá rủi ro

Giả sử ứng dụng bán hàng dùng Cassandra để lưu **đơn hàng theo khách hàng và ngày**. Service đặt hàng chịu trách nhiệm ghi `amount` và `status`. Một service phân tích độc lập xử lý bất đồng bộ và ghi `risk_level`, ví dụ `LOW` hoặc `HIGH`. Giao diện còn cần `display_label` ghép từ các thông tin đã đọc, nhưng nhãn này không cần lưu xuống Cassandra.

Phân quyền sở hữu dữ liệu:

~~~text
Order Service ──ghi──> amount, status
                        |
                        v
             Cassandra: orders_by_customer_day
                        ^
                        |
Risk Service ──ghi──> risk_level

Order Reader ──đọc──> status + risk_level
                        |
                        v
              displayLabel chỉ tồn tại trong Java
~~~

Schema CQL ví dụ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_customer_day (
    customer_id uuid,
    order_day   date,
    placed_at   timestamp,
    order_id    uuid,
    amount      decimal,
    status      text,
    risk_level  text,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

`(customer_id, order_day)` là **partition key tổng hợp**; `placed_at` và `order_id` là **clustering columns**. Ví dụ dùng tên datacenter `dc1` và RF = 3 để minh họa; cluster thực tế phải có topology phù hợp. Không dùng RF = 3 trên môi trường chỉ có một node để suy ra rằng ba replica đang tồn tại.

Bảng có cột `risk_level` vì ta **muốn đọc** giá trị thật từ Cassandra. Bảng **không có cột `display_label`**, vì đó là giá trị tính toán tạm thời của ứng dụng. Đây là điểm phân biệt quan trọng khi thiết kế entity.

## 3. Ánh xạ entity với cả hai annotation

Một ví dụ Java rút gọn:

~~~java
import java.io.Serializable;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.annotation.Transient;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.Table;

@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "order_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(name = "placed_at", ordinal = 2,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private UUID orderId;

    // Bổ sung constructor, getter/setter, equals/hashCode phù hợp.
}

@Table("orders_by_customer_day")
public class OrderRow {

    @PrimaryKey
    private OrderKey key;

    @Column("amount")
    private BigDecimal amount;

    @Column("status")
    private String status;

    // Cột có thật, do Risk Service quản lý.
    @ReadOnlyProperty
    @Column("risk_level")
    private String riskLevel;

    // Chỉ phục vụ ứng dụng: không có cột display_label.
    @Transient
    private String displayLabel;

    public void refreshDisplayLabel() {
        displayLabel = status
                + (riskLevel == null ? "" : " / risk=" + riskLevel);
    }

    // Bổ sung constructor/getter/setter phù hợp cơ chế mapping.
}
~~~

Ví dụ giả định ứng dụng đang kết nối đến keyspace `commerce_ks`. Đoạn mã minh họa metadata và quan hệ read/write; để biên dịch cần đặt `OrderKey` và `OrderRow` vào các file/class phù hợp, bổ sung constructor/accessor và triển khai giá trị khóa theo nguyên tắc Java/Spring Data đang dùng.

Ba nhóm thuộc tính trong `OrderRow`:

1. **Thông thường:** `amount`, `status` được ánh xạ để đọc và ghi qua entity.
2. **Chỉ đọc qua entity:** `riskLevel` có ánh xạ cột `risk_level`, nhưng Spring Data Cassandra **không đưa cột này vào câu insert/update được sinh từ entity**.
3. **Không tham gia mapping:** `displayLabel` không được đọc từ CQL, cũng không được ghi xuống Cassandra. Phương thức `refreshDisplayLabel()` là logic Java và **không tự chạy khi entity được materialize**, trừ khi ứng dụng chủ động gọi.

Trong nhiều ứng dụng, `displayLabel` thậm chí nên được tính trực tiếp bằng getter hoặc ở lớp DTO/view model để tránh giữ state có nguy cơ cũ. Ở đây trường `@Transient` được giữ lại để minh họa đúng hành vi mapping.

## 4. Hành vi khi ghi qua repository hoặc CassandraTemplate

Repository đồng bộ:

~~~java
public interface OrderRepository
        extends CassandraRepository<OrderRow, OrderKey> {
}
~~~

Khi gọi:

~~~java
order.setStatus("PAID");
order.setRiskLevel("HIGH");
order.setDisplayLabel("Paid / risk=HIGH");

orderRepository.save(order);
~~~

**Điều gì xảy ra?**

- `status` là thuộc tính thường: giá trị `PAID` **có thể được đưa vào câu ghi entity** tương ứng.
- `riskLevel` được đánh dấu `@ReadOnlyProperty`: giá trị `HIGH` vừa set trên object **không được đưa vào entity-bound INSERT/UPDATE**.
- `displayLabel` được đánh dấu `@Transient`: không tham gia ánh xạ hoặc ghi dữ liệu.

Vì vậy, **chỉ thay đổi `riskLevel` trên object rồi gọi `save()` không cập nhật cột `risk_level` của bảng**. Tương tự, `save()` không đảm bảo khởi tạo lại giá trị `riskLevel` mới từ Cassandra sau khi ghi; object Java có thể đang giữ giá trị do người dùng set, trong khi database có giá trị khác.

Với `CassandraTemplate`, các thao tác ghi **dựa trên mapped entity** cũng tôn trọng metadata read-only/transient. Tuy nhiên các API viết CQL trực tiếp hoặc những statement tự xây dựng **không bị annotation tự động kiểm soát**.

Ví dụ service Risk có thể cập nhật cột bằng một câu CQL rõ ràng:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET risk_level = 'HIGH'
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Lưu ý truy vấn cập nhật dùng **đầy đủ primary key** trong bảng minh họa. Đây là một đường ghi CQL riêng; `@ReadOnlyProperty` trong entity của Order Service không cản trở service khác thực hiện câu lệnh đó. Muốn kiểm soát quyền ghi thực sự, cần **phân quyền CQL, quản lý credential và giới hạn API** thay vì chỉ dựa vào annotation Java.

**Lưu ý về upsert và ghi đè:** Cassandra có ngữ nghĩa upsert, sử dụng timestamp để phân giải nhiều ghi. Việc đặt `@ReadOnlyProperty` giúp đường ghi entity tránh chủ động gửi cột do service khác sở hữu, nhưng không tự tạo ra transaction liên service hay đảm bảo mọi trường khác không bị ghi đè khi có cập nhật đồng thời.

## 5. Hành vi khi đọc từ Cassandra

Giả sử câu CQL dưới đây đọc đúng một hàng (các dấu `?` là tham số):

~~~sql
SELECT customer_id, order_day, placed_at, order_id,
       amount, status, risk_level
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Khi Spring Data Cassandra mapping kết quả vào `OrderRow`:

- `key`, `amount`, `status` được đọc từ các cột tương ứng.
- `riskLevel` có thể nhận giá trị `risk_level` của hàng, ví dụ `HIGH`.
- `displayLabel` **không** được đọc từ CQL. Với object mới được materialize và không có gán bổ sung, nó thường giữ giá trị mặc định (`null`).

Ứng dụng có thể tính nhãn sau khi đọc:

~~~java
OrderRow order = orderRepository.findById(orderKey)
        .orElseThrow();

// riskLevel được mapping từ risk_level nếu cột có trong kết quả.
order.refreshDisplayLabel();
String label = order.getDisplayLabel();
~~~

Hai điều kiện khi đọc `@ReadOnlyProperty`:

1. **Cột phải tồn tại trong schema**, nếu ứng dụng kỳ vọng query đọc cột đó. Chỉ thêm `@ReadOnlyProperty` vào entity không tạo giá trị và không tự sửa bảng đã có.
2. **Query phải trả về cột đó.** Nếu truy vấn dùng projection và không chọn `risk_level`, giá trị `riskLevel` không tự xuất hiện trong entity. Đừng suy ra rằng bất kỳ câu `SELECT` nào cũng tải đủ mọi cột.

Nếu service Risk chưa từng ghi `risk_level` cho đơn hàng, trường trong Java có thể là `null`. Cassandra không tự tính mức rủi ro từ annotation. Cần xử lý trạng thái “chưa có kết quả đánh giá” theo nghiệp vụ.

## 6. `@Transient` là loại khỏi persistence, không phải cơ chế ẩn dữ liệu API

Trong Spring Data Cassandra, `@Transient` cho biết một thuộc tính **không được mapper coi là cột persistent**. Đây là quyết định ở tầng ORM/ODM mapping, không phải chính sách serialize JSON hay bảo mật.

Ví dụ:

~~~java
@Transient
private String internalUiHint;
~~~

Trường này không được Cassandra converter đọc/ghi như một cột. Nhưng nếu có getter công khai:

~~~java
public String getInternalUiHint() {
    return internalUiHint;
}
~~~

thì một JSON serializer như Jackson **vẫn có thể đưa nó vào response API**, tùy cách cấu hình serializer. Nếu cần che giấu trong JSON, hãy xử lý riêng bằng DTO, `@JsonIgnore` hoặc quy tắc serialization phù hợp. Không dùng `@Transient` với kỳ vọng tự ngăn lộ dữ liệu qua HTTP response.

Tương tự, annotation **không làm một đối tượng Java trở thành bất biến**. Code vẫn có thể gán giá trị `displayLabel`, và giá trị đó vẫn tồn tại trong bộ nhớ cho tới khi object thay đổi hoặc bị hủy.

### `@Transient` khác từ khóa Java `transient` thế nào?

~~~java
// Hướng dẫn Spring Data mapping:
@Transient
private String derivedLabel;

// Phục vụ Java Serialization, không nên coi là tương đương:
private transient String serializationHint;
~~~

Từ khóa `transient` thuộc cơ chế Java Serialization. Spring Data có quy tắc mapping riêng và tài liệu Spring Data Cassandra khuyên dùng **annotation `@Transient`** để loại một property khỏi persistence. Nếu một trường vừa cần loại khỏi Cassandra vừa cần loại khỏi JSON hoặc Java Serialization, hãy cấu hình **riêng từng cơ chế**.

### Constructor và property không persistent

Spring Data cần tạo object và gán những thuộc tính được đọc từ CQL. Không nên đặt một thuộc tính `@Transient` thành **tham số bắt buộc** mà persistence constructor phải lấy từ Cassandra: converter không có giá trị cột để materialize nó. Với entity bất biến, thiết kế constructor/factory và default value rõ ràng, hoặc tính trạng thái tạm ở phương thức/DTO thay vì yêu cầu converter cung cấp một cột không tồn tại.

Đối với `@ReadOnlyProperty`, property **vẫn được ánh xạ để đọc**, do đó kiểu dữ liệu, tên cột và cách khởi tạo object cần tương thích dữ liệu CQL thực tế.

## 7. `@ReadOnlyProperty` là đọc được, nhưng không phải column “tự sinh”

Trong một số cơ sở dữ liệu quan hệ, developer quen với trường do database trigger hoặc computed column tự tạo. Với Cassandra, **không nên giả định có cơ chế tự sinh kiểu đó** chỉ vì thêm `@ReadOnlyProperty`.

Nguồn của giá trị read-only phải được xác định rõ:

| Nguồn dữ liệu | Có phù hợp với `@ReadOnlyProperty`? | Lưu ý |
| --- | --- | --- |
| Service khác ghi cùng cột CQL | Có | Cần phối hợp lifecycle, consistency và quyền ghi |
| Batch job tính và ghi giá trị | Có | Có thể đọc giá trị cũ/trống trước khi job hoàn thành |
| Dữ liệu từ materialized view hoặc bảng đọc riêng | Tùy thiết kế | View/bảng phải có schema và mapping tương thích; không tự JOIN khi đọc |
| Getter Java tính từ các field khác | Thường dùng phương thức hoặc `@Transient` | Không cần tạo cột chỉ để mang giá trị có thể tính cục bộ |
| Field do cùng repository cần ghi khi save | **Không nên** | `@ReadOnlyProperty` khiến mapped insert/update bỏ qua field |

Trong Cassandra, **đọc được cột** còn phụ thuộc vào consistency level, trạng thái replica và thời điểm writer cập nhật. Ví dụ Order Service ghi `status=PAID` rồi Risk Service mới ghi `risk_level=HIGH` sau vài giây. Query đọc giữa hai bước có thể thấy `status` mới nhưng `risk_level` chưa có hoặc còn cũ.

`@ReadOnlyProperty` không giải quyết tính nhất quán giữa nhiều service; cần định nghĩa hợp đồng nghiệp vụ, trạng thái “pending”, thời điểm hoàn tất và lựa chọn consistency/đường xử lý phù hợp.

## 8. Chọn đúng annotation để không lệch schema

Giả sử cột `risk_level` đã có thật trong Cassandra. Nếu nhầm dùng:

~~~java
@Transient
private String riskLevel;
~~~

thì entity **không đọc** `risk_level`, cho dù dữ liệu vẫn tồn tại trong bảng. Dùng `@ReadOnlyProperty` kết hợp tên cột là lựa chọn phù hợp hơn nếu mục tiêu đọc nhưng không ghi:

~~~java
@ReadOnlyProperty
@Column("risk_level")
private String riskLevel;
~~~

Ngược lại, nếu thêm:

~~~java
@ReadOnlyProperty
@Column("display_label")
private String displayLabel;
~~~

trong khi bảng **không có `display_label`**, mapping không thể tự tạo nhãn từ `status`. Một câu query/statement chọn cột không tồn tại có thể bị Cassandra từ chối. Nếu muốn nhãn hiển thị, hãy dùng tính toán Java hoặc DTO; nếu thực sự muốn lưu nhãn, phải thiết kế cột và writer đúng nghĩa.

**Schema action không phải migration an toàn.** Thêm/đổi annotation không mặc nhiên làm bảng đã tồn tại thay đổi. Với production, nên quản lý schema bằng CQL migration được review, không mặc định cho ứng dụng recreate bảng để sửa lỗi mapping.

## 9. Tác động tới khóa, truy vấn và hiệu năng

Hai annotation này chỉ áp dụng cho **lựa chọn property mapping**; chúng không thay đổi cơ chế partition hoặc thứ tự clustering trong Cassandra.

Trong ví dụ:

~~~sql
PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
~~~

Vì thế:

- Truy vấn lịch sử theo một khách hàng/ngày vẫn cần `customer_id` và `order_day` để xác định partition.
- `risk_level` là cột thường. Đánh dấu `@ReadOnlyProperty` **không tạo index** và không làm truy vấn `WHERE risk_level = 'HIGH'` trở thành truy vấn định tuyến theo partition.
- `displayLabel` được đánh dấu `@Transient`; nó **không tồn tại trong CQL**, nên không dùng `WHERE display_label ...` hoặc `ORDER BY display_label` ở Cassandra.
- Khi đọc nhiều hàng, cột `risk_level` vẫn có thể làm tăng dữ liệu truyền qua mạng. Nếu không cần, cân nhắc query/projection chỉ lấy các cột phục vụ use case.
- Paging bằng paging state và `LIMIT` vẫn cần thiết khi partition có nhiều hàng; chọn annotation không giải quyết partition quá lớn, tombstone hoặc hot partition.

Ví dụ truy vấn theo partition đầy đủ và giới hạn số kết quả:

~~~sql
SELECT customer_id, order_day, placed_at, order_id,
       amount, status, risk_level
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 30;
~~~

Với reactive repository hoặc `ReactiveCassandraTemplate`, kết quả có thể được bọc trong `Flux`/`Mono`, nhưng **quy tắc mapping `@Transient` và `@ReadOnlyProperty` không vì vậy mà đổi**. Tương tự, reactive I/O không biến truy vấn thiếu partition key thành truy vấn nhanh.

## 10. Ba tình huống thực hành

### Tình huống A — Trường dùng riêng cho giao diện

Giao diện cần hiển thị `"PAID / 250.000 đ"`, được tính từ `status` và `amount`.

~~~java
@Transient
private String formattedSummary;
~~~

Chọn `@Transient` nếu đây là trạng thái lưu tạm trên entity; hoặc tốt hơn, tạo getter tính trực tiếp/DTO dành cho API. Không cần thêm cột vào Cassandra chỉ để hỗ trợ trình bày dữ liệu.

### Tình huống B — Kết quả phân tích do service khác ghi

Risk Service có trách nhiệm ghi giá trị `risk_level`. Order Service chỉ đọc để hiển thị, không được ghi đè khi save `OrderRow`.

~~~java
@ReadOnlyProperty
@Column("risk_level")
private String riskLevel;
~~~

Chọn `@ReadOnlyProperty`. Nếu muốn ngăn quyền update từ Order Service ở cấp cơ sở dữ liệu, vẫn phải thiết kế kiểm soát credential/quyền và API; annotation **không thay thế cơ chế bảo mật**.

### Tình huống C — Entity nhận một trường debug tạm

Trong lúc xử lý request, code gán một ghi chú debug lên object, nhưng không muốn trường này xuất hiện trong CQL:

~~~java
@Transient
private String debugNote;
~~~

Lưu ý `debugNote` có thể xuất hiện trong JSON response nếu serializer nhìn thấy getter; xử lý hợp đồng API và dữ liệu nhạy cảm tách biệt với Cassandra mapping.

## 11. Kiểm thử hành vi thực tế bằng CQL và Java

Với môi trường học tập có dữ liệu thử, có thể thực hiện các bước sau:

1. Tạo bảng ví dụ và dùng CQL ghi một đơn hàng hợp lệ, có `risk_level='LOW'`. Các giá trị UUID và timestamp phải là literal hợp lệ hoặc tham số đã bind.
2. Đọc entity qua repository bằng đầy đủ primary key; xác minh `riskLevel` nhận `LOW` còn `displayLabel` chưa được tự tính.
3. Gán `riskLevel='HIGH'` và `displayLabel='test'` trong Java, rồi gọi `repository.save(order)`.
4. Đọc **lại từ Cassandra** bằng một session/query khác hoặc làm mới entity; xác minh `risk_level` không đổi chỉ vì lần save ở bước 3, trong khi `displayLabel` không có cột lưu trữ.
5. Dùng CQL tường minh từ writer có thẩm quyền cập nhật `risk_level='HIGH'`, sau đó đọc lại entity để xác minh giá trị mới được mapping.

Để quan sát dữ liệu trực tiếp:

~~~sql
SELECT status, risk_level
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Nếu không thấy giá trị mới ngay, kiểm tra **thời điểm ghi, consistency level, replica, câu CQL thực tế và đường đọc** trước khi kết luận mapping sai. Đừng dùng `SELECT COUNT(*)` hoặc quét toàn bộ cluster để kiểm thử một thuộc tính đơn lẻ.

Khi kiểm tra câu ghi do Spring Data phát sinh, nên bật logging CQL có kiểm soát ở môi trường thử nghiệm. Tránh ghi trực tiếp thông tin nhạy cảm hoặc payload cá nhân vào log production.

### Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “Hai annotation đều không ghi nên tương đương.” | `@Transient` **không mapping đọc**; `@ReadOnlyProperty` vẫn mapping **đọc**, bỏ qua ở mapped write. |
| “`@ReadOnlyProperty` tự tính giá trị của cột.” | Nó không tính giá trị; cần có writer và cột CQL thật. |
| “Đánh dấu read-only nghĩa là tất cả service không thể ghi.” | CQL thủ công và service khác vẫn có thể ghi; cần quyền ở tầng hệ thống. |
| “`@Transient` tự ẩn thuộc tính khỏi REST JSON.” | Annotation này điều khiển persistence mapping, không phải serialization API. |
| “Thêm field mới vào entity thì Cassandra tự tạo cột.” | Schema phải được quản lý riêng; bảng tồn tại không được migration tự động an toàn chỉ bằng sửa annotation. |
| “Read-only property giúp truy vấn theo cột đó nhanh hơn.” | Annotation không tạo partition key hoặc index. |
| “Gọi `save()` làm mới mọi giá trị database-managed.” | `save()` không mặc định re-read entity; muốn cập nhật giá trị Java phải đọc lại. |
| “Property không có cột vẫn dùng được trong persistence constructor.” | Converter không có dữ liệu CQL cho một transient property; tránh phụ thuộc vào nó như tham số bắt buộc. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Entity có trường `taxPreview` chỉ được tính từ `amount` để hiển thị, Cassandra không có cột này. Chọn annotation nào?

**Đáp án:** `@Transient` (hoặc tính trực tiếp qua method/DTO nếu không cần lưu trạng thái trên entity).

**Câu 2.** Cassandra có cột `review_result` do job đêm ghi; service hiện tại muốn đọc nhưng không ghi đè khi `save()`. Chọn annotation nào?

**Đáp án:** `@ReadOnlyProperty` cùng `@Column("review_result")` để ánh xạ đúng tên cột.

**Câu 3.** Gán `reviewResult = "PASS"` rồi gọi `repository.save(entity)` có cập nhật cột `review_result` không?

**Đáp án:** Không thông qua mapped insert/update của Spring Data Cassandra khi thuộc tính có `@ReadOnlyProperty`.

**Câu 4.** Thêm `@Transient` vào `riskLevel` trong khi Cassandra có `risk_level`. `SELECT *` trả về cột đó có khiến Spring Data set vào trường không?

**Đáp án:** Không. Trường đã bị loại khỏi persistent mapping.

**Câu 5.** `@ReadOnlyProperty` có cho phép truy vấn `WHERE risk_level = 'HIGH'` hiệu quả trên mọi partition không?

**Đáp án:** Không. Khả năng truy vấn phụ thuộc cấu trúc partition key, clustering key, index và workload của Cassandra; annotation chỉ tác động đến mapping.

---

**Tài liệu tham khảo:** [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html), phần Mapping Annotations (mô tả `@Transient` và `@ReadOnlyProperty`); [Spring Data Commons — `ReadOnlyProperty`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/ReadOnlyProperty.html). Khi dự án dùng phiên bản khác, kiểm tra API/reference đúng phiên bản trước khi vận dụng.

**Ghi nhớ:** `@Transient` loại thuộc tính khỏi quá trình ánh xạ **đọc và ghi** với Cassandra; `@ReadOnlyProperty` giữ thuộc tính để **đọc**, nhưng loại nó khỏi câu `INSERT`/`UPDATE` được tạo từ entity. Cả hai không thay đổi schema, partition key, consistency hay các câu CQL thủ công. Chọn đúng annotation giúp thể hiện rõ quyền sở hữu dữ liệu giữa các service và tránh ghi đè ngoài ý muốn trong ứng dụng Spring Data Cassandra.
