# Mô hình họ cột (wide-column) và tổ chức dữ liệu theo truy vấn

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mô hình **họ cột (wide-column)** và phân biệt nó với cơ sở dữ liệu quan hệ cũng như kho dữ liệu **lưu trữ dạng cột phục vụ phân tích**.
2. Thiết kế `partition key` và `clustering key` từ các truy vấn cụ thể, ước lượng kích thước và tải của từng partition.
3. Xây dựng các bảng đọc theo nhu cầu (query-specific tables), hiểu chi phí nhân bản dữ liệu và xử lý cập nhật giữa các bảng.
4. Hiện thực một truy vấn có giới hạn trong Java, nhận biết các rủi ro về phân trang, hot partition, nhất quán và xóa dữ liệu.

Bài học nằm trong phạm vi **DATA_PERSISTENCE_FUNDAMENTALS**: thiết kế ranh giới persistence cho ứng dụng Java, từ mô hình dữ liệu, lược đồ và truy vấn đến kiểm soát đồng thời, lỗi, bảo mật và hiệu năng. Ví dụ dùng **Apache Cassandra/CQL** để minh họa; nguyên tắc thiết kế theo truy vấn cũng hữu ích với ScyllaDB, HBase và Bigtable, nhưng cú pháp, cách sắp xếp khóa và bảo đảm nhất quán giữa các hệ thống này **không hoàn toàn giống nhau**.

## 1. Wide-column là gì?

Mô hình wide-column lưu dữ liệu theo các **hàng thuộc một nhóm/partition**, mỗi hàng có thể gắn với tập cột và khóa riêng. Những hàng gần nhau theo khóa thường được bố trí để truy xuất hiệu quả cùng nhau. Tên gọi *column family* bắt nguồn từ việc các hệ thống này tổ chức cột thành nhóm; trong Cassandra hiện đại, đơn vị người lập trình thao tác là **table**.

Khác biệt quan trọng nằm ở **mục tiêu truy cập**: thay vì chuẩn hóa dữ liệu trước rồi kỳ vọng hệ quản trị tự tìm cách kết hợp bảng để giải quyết các truy vấn mới, thiết kế wide-column thường bắt đầu từ **các câu hỏi ứng dụng sẽ hỏi**, sau đó xây bảng và khóa phục vụ từng kiểu truy vấn. Điều này phù hợp khi cần ghi nhiều, mở rộng theo chiều ngang và truy xuất có mẫu lặp lại, dự đoán được.

| Mô hình | Tổ chức và truy cập nổi bật | Khi thuận lợi | Hạn chế liên quan |
| --- | --- | --- | --- |
| Quan hệ (ví dụ PostgreSQL) | Bảng, khóa ngoại, JOIN, chỉ mục, giao dịch đa hàng | Truy vấn thay đổi, ràng buộc chặt, nghiệp vụ giao dịch | Mở rộng phân tán có thể phức tạp |
| Wide-column (ví dụ Cassandra) | Partition theo khóa; các hàng trong partition sắp theo clustering key | Truy vấn theo khóa đã biết, dữ liệu lớn, tải phân tán | JOIN/scan tùy ý bị giới hạn; thường cần bảng nhân bản |
| Columnar analytics (ví dụ Parquet/ClickHouse) | Giá trị cùng cột được lưu gần nhau để quét, nén và tổng hợp | Phân tích trên nhiều hàng, `GROUP BY`, tổng hợp | Không đồng nghĩa với mô hình wide-column dùng cho truy vấn OLTP |

**Tránh nhầm lẫn:** chữ “column” trong *wide-column* không có nghĩa mọi truy vấn phân tích quét hàng triệu bản ghi sẽ nhanh như một kho dữ liệu columnar.

## 2. Cấu trúc khóa trong Cassandra

Một bảng Cassandra có **primary key** gồm hai phần:

- **Partition key**: xác định partition logic, dùng để định tuyến dữ liệu đến các node. Partition key có thể là một cột hoặc một bộ nhiều cột.
- **Clustering columns**: sắp thứ tự các hàng *bên trong một partition*, cho phép đọc theo thứ tự hoặc theo khoảng khóa phù hợp.

Ví dụ khóa tổng quát:

```sql
PRIMARY KEY ((tenant_id, customer_id, order_month), created_at, order_id)
```

`(tenant_id, customer_id, order_month)` là **partition key kết hợp**; `created_at` và `order_id` là hai **clustering columns**. Cần phân biệt hai cặp ngoặc: cặp ngoặc trong cùng gom các thành phần của partition key, không chỉ là ký hiệu trang trí.

Minh họa dữ liệu đơn hàng của một khách trong tháng:

```text
Partition key = (shop-a, customer-42, 2026-11)
    created_at DESC       order_id        status
    2026-11-21 10:10      o-103           PAID
    2026-11-19 08:00      o-102           SHIPPED
    2026-11-03 14:15      o-101           DELIVERED

Partition key = (shop-a, customer-42, 2026-10)
    2026-10-28 09:40      o-090           DELIVERED
    ...
```

Sơ đồ chỉ diễn giải thứ tự logic. Cassandra phân bố bản sao và dữ liệu vật lý theo cấu hình cụm; không suy ra rằng mọi partition nằm duy nhất trên một máy. Mỗi truy vấn có đủ partition key sẽ giúp hệ thống xác định nơi đọc trực tiếp, hạn chế quét dữ liệu không liên quan.

Với các hệ như HBase hay Bigtable, cần chuyển nguyên tắc này sang **row key và thứ tự từ điển của row key**; đừng bê nguyên cú pháp primary key của Cassandra sang các hệ đó.

## 3. Bắt đầu từ truy vấn, không bắt đầu từ bảng thực thể

Xét dịch vụ quản lý đơn hàng Java của nhiều cửa hàng. Giao diện cần ba thao tác:

| Mã | Nhu cầu đọc | Tần suất và mục tiêu | Thiết kế phù hợp |
| --- | --- | --- | --- |
| Q1 | Xem 20 đơn mới nhất của một khách trong một tháng | Rất thường xuyên, độ trễ thấp | `orders_by_customer_month` |
| Q2 | Xem chi tiết một đơn theo mã đơn | Thường xuyên, trả về đúng một đơn | `orders_by_id` |
| Q3 | Liệt kê tất cả đơn `PAID` trong ngày của một cửa hàng | Dùng cho xử lý vận hành | Cần bảng đọc riêng theo `(tenant, status, day)`, luồng sự kiện hoặc hệ tìm kiếm phù hợp |

Cùng một đơn có thể xuất hiện ở nhiều bảng. Đây là **denormalization có chủ đích** để giảm phép kết hợp và truy vấn quét toàn cục. Đổi lại, mọi bản sao cần quy tắc cập nhật, kiểm tra sai lệch và chiến lược phục hồi.

Một quy trình thiết kế có thể lặp lại:

1. Ghi rõ truy vấn: điều kiện lọc, thứ tự, số bản ghi trả về, SLA và tần suất.
2. Chọn partition key từ những điều kiện ứng dụng **luôn biết khi truy vấn**, đồng thời kiểm tra phân bố tải.
3. Chọn clustering key cho thứ tự/điều kiện khoảng thường dùng **trong partition**.
4. Đặt các cột cần trả về ngay trong bảng đọc; tránh dựa vào JOIN phía máy chủ.
5. Ước lượng số hàng, số byte và số thao tác trên mỗi partition theo thời gian; quyết định có cần *time bucket* hay chia nhóm.
6. Thiết kế đường ghi, cập nhật, xóa, phân trang và sửa lệch giữa các bảng trước khi chốt schema.

## 4. Lược đồ phục vụ hai truy vấn chính

Dưới đây là CQL minh họa cho Cassandra. `order_month` là chuỗi dạng `YYYY-MM` tính thống nhất theo **UTC**; ứng dụng phải chuyển thời gian sang UTC trước khi xác định bucket.

### Q1 — Lịch sử đơn hàng theo khách và tháng

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id    text,
    customer_id  uuid,
    order_month  text,
    created_at   timestamp,
    order_id     uuid,
    status       text,
    amount       decimal,
    currency     text,
    PRIMARY KEY ((tenant_id, customer_id, order_month),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Truy vấn:

```sql
SELECT order_id, created_at, status, amount, currency
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND order_month = ?
LIMIT 20;
```

Điểm cần đọc từ lược đồ:

- `tenant_id` nằm trong khóa để các truy vấn có phạm vi cửa hàng rõ ràng, nhưng **không thay thế** kiểm tra quyền truy cập ở tầng ứng dụng.
- `customer_id` giúp thao tác tìm lịch sử của đúng khách.
- `order_month` giới hạn partition theo thời gian để lịch sử nhiều năm không dồn vào một partition tăng mãi.
- `created_at DESC` tối ưu truy vấn mới nhất trước; `order_id` phân biệt hai đơn có cùng thời điểm tạo.
- `LIMIT 20` chặn số hàng trả về; bản thân nó **không cứu được** một truy vấn phải lọc toàn bảng.

Với một màn hình hiển thị nhiều tháng, dịch vụ có thể đọc tháng hiện tại, sau đó lần lượt đọc các tháng trước đến khi đủ số đơn. Không thể giả định một `ORDER BY` toàn cục hoạt động qua nhiều partition.

### Q2 — Tra cứu chi tiết theo mã đơn

```sql
CREATE TABLE orders_by_id (
    tenant_id    text,
    order_id     uuid,
    customer_id  uuid,
    order_month  text,
    created_at   timestamp,
    status       text,
    amount       decimal,
    currency     text,
    PRIMARY KEY ((tenant_id, order_id))
);
```

```sql
SELECT customer_id, order_month, created_at, status, amount, currency
FROM orders_by_id
WHERE tenant_id = ?
  AND order_id = ?;
```

Bảng Q2 lặp lại thông tin từ Q1. Nếu chỉ có bảng Q1, yêu cầu “tra cứu đơn theo mã” sẽ thiếu `customer_id` và `order_month` để định tuyến partition. Cassandra không tự tạo một đường truy vấn hiệu quả chỉ vì `order_id` có mặt trong bảng.

**Đừng mặc định thêm `ALLOW FILTERING`** để giải quyết mẫu truy vấn thiếu khóa. Lọc sau khi đọc trên lượng dữ liệu lớn có thể tạo độ trễ khó dự đoán. Secondary index và materialized view có chỗ dùng riêng, phụ thuộc phiên bản, phân bố giá trị và tải thực tế; cần đo đạc trước khi chọn thay cho một bảng đọc được thiết kế rõ ràng.

### Nếu có thêm Q3

Một bảng `orders_by_status_day` với partition key chẳng hạn `(tenant_id, status, order_day)` và clustering `(created_at, order_id)` có thể phục vụ liệt kê đơn theo trạng thái/ngày. Tuy nhiên, trạng thái thay đổi từ `PAID` sang `SHIPPED` đòi hỏi **loại bỏ bản chiếu cũ** và ghi bản chiếu mới. Với nhu cầu tổng hợp hoặc tìm kiếm linh hoạt, một hệ phân tích/tìm kiếm xây từ sự kiện có thể phù hợp hơn duy trì quá nhiều bảng Cassandra.

## 5. Triển khai truy vấn trong Java

Ví dụ sau dùng API của **Apache Cassandra Java Driver 4.x**. Một `CqlSession` do ứng dụng tạo và quản lý vòng đời được truyền vào repository. `PreparedStatement` chuẩn bị một lần và tái sử dụng; giới hạn bản ghi được kiểm tra ở tầng dịch vụ.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderHistoryRepository {
    public record OrderSummary(
            UUID orderId,
            Instant createdAt,
            String status,
            BigDecimal amount,
            String currency) {}

    private final CqlSession session;
    private final PreparedStatement findByCustomerMonth;

    public OrderHistoryRepository(CqlSession session) {
        this.session = session;
        this.findByCustomerMonth = session.prepare(
            "SELECT order_id, created_at, status, amount, currency " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? " +
            "AND order_month = ? LIMIT ?");
    }

    public List<OrderSummary> findRecent(
            String tenantId, UUID customerId, YearMonth month, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        ResultSet rows = session.execute(findByCustomerMonth.bind(
                tenantId, customerId, month.toString(), limit));

        List<OrderSummary> result = new ArrayList<>();
        for (Row row : rows) {
            result.add(new OrderSummary(
                row.getUuid("order_id"),
                row.getInstant("created_at"),
                row.getString("status"),
                row.getBigDecimal("amount"),
                row.getString("currency")));
        }
        return result;
    }
}
```

Ví dụ giả định bảng đã được tạo, keyspace được cấu hình cho session và đầu vào đã vượt qua kiểm tra danh tính/ủy quyền ở lớp phía trên. `YearMonth.toString()` tạo chuỗi `YYYY-MM` phù hợp với quy ước bucket; khi tính tháng từ `Instant`, dùng `YearMonth.from(instant.atZone(ZoneOffset.UTC))` để tránh một đơn rơi vào hai bucket khác nhau do múi giờ.

Cần phân biệt **`LIMIT`** và **phân trang**: `LIMIT` giới hạn số hàng của truy vấn này; khi trả danh sách dài hơn, driver có thể lấy các trang dữ liệu từ Cassandra. API thực tế cần cursor/paging state, mức giới hạn mỗi trang và cách xử lý hết một tháng rồi chuyển tháng. Không nên dùng phân trang bằng `OFFSET` như SQL quan hệ; Cassandra không hỗ trợ kiểu phân trang ngẫu nhiên này theo cách thông thường. Khi dữ liệu được ghi mới liên tục, ứng dụng cũng cần xác định quy tắc ổn định thứ tự và tránh hiển thị trùng/bỏ sót qua các trang.

## 6. Ghi dữ liệu và nhất quán giữa các bảng

Khi tạo đơn, ứng dụng cần:

1. Sinh `order_id` ổn định và tính `order_month` từ `created_at`.
2. Ghi thông tin đơn ở `orders_by_id`.
3. Cập nhật bản chiếu tương ứng ở `orders_by_customer_month`.
4. Đảm bảo lỗi giữa hai lần ghi được phát hiện, thử lại và hòa giải.

Hai lệnh CQL dạng khái niệm:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, order_month,
    created_at, status, amount, currency
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, order_month, created_at,
    order_id, status, amount, currency
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Đừng xem hai bảng đọc như hai thực thể độc lập cùng “sở hữu” chân lý. Chọn **nguồn dữ liệu có thẩm quyền**, rồi quyết định cách xây và sửa bản chiếu: ví dụ ghi trạng thái đơn vào nguồn có thẩm quyền, phát sự kiện qua kênh bền vững, consumer cập nhật bảng lịch sử bằng khóa định danh ổn định và chạy tác vụ reconciliation nếu thiếu bản ghi. Cấu trúc đó chấp nhận khả năng **bản chiếu tạm thời chậm hơn** nguồn chính.

Cassandra hỗ trợ batch và các mức consistency khác nhau nhưng **batch đa partition không tương đương giao dịch SQL có isolation và rollback toàn bộ**. Không nên dùng batch lớn để gom các ghi không liên quan với kỳ vọng tăng throughput. Khi cần điều kiện “chỉ ghi nếu chưa tồn tại”, có thể nghiên cứu **lightweight transaction (LWT)** như `IF NOT EXISTS` và đánh đổi độ trễ; không tự động áp dụng LWT cho mọi ghi.

Đối với Java, repository nên phân biệt lỗi tạm thời có thể retry với lỗi dữ liệu/ủy quyền không được retry vô hạn. Khóa chính cố định giúp việc ghi lại cùng một bản ghi dễ kiểm soát hơn; nếu dữ liệu thay đổi giữa các lần retry, cần chính sách phiên bản, thời điểm ghi hoặc thứ tự sự kiện rõ ràng.

## 7. Kích thước partition và phân bố tải

Chọn partition key chỉ theo độ thuận tiện của `WHERE` là chưa đủ. Phải xem **số lượng hàng** và **mức tập trung truy cập**:

- **Partition quá lớn**: một khách có hàng triệu đơn trong một partition nhiều năm; compaction, đọc và thao tác quản trị tốn kém.
- **Hot partition**: một cửa hàng/khách có lưu lượng cực lớn; thêm node không tự chia đều các request đều đánh vào cùng một khóa partition.
- **Partition quá nhỏ hoặc bucket quá mịn**: ứng dụng phải đọc rất nhiều partition cho một màn hình; tăng vòng truy vấn và chi phí kết hợp kết quả.
- **Khóa phân bố lệch**: partition theo `status` với vài giá trị như `PAID`, `NEW` có thể tạo các điểm nóng ngay cả khi số khách lớn.

Ví dụ ước lượng: nếu một khách có **10.000 đơn/tháng**, dữ liệu thực lưu trong bảng lịch sử trung bình **1 KiB/đơn** thì riêng dữ liệu hàng đã khoảng **10 MiB/partition**, chưa kể metadata và chi phí lưu trữ. Nếu khách có lưu lượng gấp 100 lần, bucket tháng có thể không còn hợp lý. Khi đó xem xét bucket theo ngày, theo shard xác định hoặc tách đường đọc, nhưng phải tính cách ứng dụng tìm và ghép kết quả.

Thiết kế cần dựa vào phân bố thực tế: số hàng/partition ở p50 và p99, kích thước partition, throughput theo khóa, p95/p99 latency, tombstone, timeout và lượng dữ liệu compaction. Không có một kích thước partition “đúng” cho mọi hệ và workload.

## 8. Hạn chế truy vấn và những bẫy phổ biến

| Bẫy | Vì sao gây vấn đề | Cách xử lý |
| --- | --- | --- |
| “Tạo bảng đơn hàng như SQL rồi muốn hỏi gì cũng được” | Truy vấn thiếu partition key có thể phải quét/lọc tốn kém | Liệt kê access patterns trước khi chốt khóa |
| “Chỉ dùng `customer_id` làm partition key” | Lịch sử vô hạn gây partition lớn | Thêm bucket thời gian phù hợp |
| “Partition theo `status`” | Ít giá trị, tải dễ dồn vào một khóa | Kết hợp khóa và thời gian, cân nhắc phân tán |
| “Dùng `ALLOW FILTERING` cho tìm kiếm toàn hệ thống” | Tăng lượng dữ liệu phải đọc, độ trễ khó đoán | Bảng đọc riêng hoặc hệ tìm kiếm/phân tích |
| “Đọc xong cập nhật hai bảng là đã giao dịch” | Lỗi mạng có thể tạo trạng thái lệch | Nguồn thẩm quyền, retry, sự kiện và reconciliation |
| “`DELETE`/TTL luôn rẻ” | Tombstone có thể ảnh hưởng truy vấn và compaction | Chính sách giữ dữ liệu, thiết kế TTL và theo dõi tombstone |
| “`COUNT(*)` là thống kê tức thì” | Đếm toàn bộ dữ liệu lớn có thể rất tốn kém | Dùng số liệu tổng hợp/đếm được duy trì riêng |
| “Đọc theo mọi thứ tự đều hiệu quả” | Sắp xếp phụ thuộc clustering key trong partition | Chọn thứ tự từ truy vấn ngay khi thiết kế |

Bổ sung về vòng đời dữ liệu: với thông tin đơn hàng cần đối soát tài chính, **không bật TTL tùy tiện**. TTL và xóa tạo tombstone theo cơ chế lưu trữ của Cassandra; việc giữ/xóa dữ liệu phải phù hợp yêu cầu nghiệp vụ, sao lưu, khôi phục và chính sách pháp lý. Với thông tin nhạy cảm, mã hóa trên đường truyền và khi lưu, phân quyền theo tenant, kiểm tra tham số và hạn chế dữ liệu ghi vào log là trách nhiệm của cả hệ thống Java lẫn kho lưu trữ.

## 9. Khi nào nên chọn wide-column?

**Phù hợp** khi dữ liệu có quy mô lớn, cần nhiều ghi, mẫu truy vấn ổn định, truy cập có khóa định tuyến rõ, chấp nhận nhân bản dữ liệu và có khả năng vận hành cụm phân tán. Ví dụ: chuỗi sự kiện theo thiết bị và khoảng thời gian, lịch sử hoạt động của một tài khoản, bản ghi đo lường theo cảm biến và ngày.

**Cần cân nhắc lựa chọn khác** khi nghiệp vụ lệ thuộc JOIN tùy ý, báo cáo phân tích ad hoc, giao dịch đa thực thể với ràng buộc mạnh, hoặc dữ liệu nhỏ mà chi phí duy trì các bảng đọc và cụm phân tán vượt lợi ích. Một ứng dụng Java có thể dùng cơ sở dữ liệu quan hệ làm nguồn nghiệp vụ, wide-column làm bảng đọc có tải lớn và kho phân tích cho truy vấn tổng hợp; khi đó phải thiết kế luồng đồng bộ và trách nhiệm dữ liệu rõ ràng.

## 10. Bài tập áp dụng và tự kiểm tra

**Tình huống:** nền tảng IoT nhận 2.000 điểm đo/phút từ một thiết bị, cần truy vấn 100 điểm đo gần nhất và xem dữ liệu trong một giờ xác định. Đề xuất đầu tiên là:

```sql
PRIMARY KEY (device_id, measured_at)
```

Hãy trả lời:

1. `device_id` có thể tạo vấn đề gì sau nhiều tháng? Nếu thiết bị rất nhiều nhưng phần lớn ít dữ liệu, phân bố tải thay đổi ra sao?
2. Bạn sẽ bổ sung bucket giờ/ngày vào partition key thế nào, và vì sao phải biết đặc tính đọc trước khi chọn?
3. Muốn tìm “mọi thiết bị có nhiệt độ > 70°C” thì bảng đo theo thiết bị đã đủ chưa?
4. Khi sự kiện đến trễ, bản ghi cũ có thể làm thay đổi trang kết quả “mới nhất” thế nào? Cần quy tắc gì ở client?

**Gợi ý đối chiếu:** khóa `device_id` đơn lẻ khiến partition tích lũy dài hạn; thêm `(device_id, day_bucket)` hoặc `(device_id, hour_bucket)` và `measured_at DESC` giúp giới hạn phạm vi, nhưng bucket giờ làm tăng số partition phải đọc khi xem nhiều giờ. Câu hỏi tìm toàn bộ thiết bị vượt ngưỡng đòi hỏi bản chiếu theo cảnh báo, hệ xử lý luồng hoặc chỉ mục phù hợp; không nên quét mọi partition để cảnh báo thời gian thực. Đọc trang liên tiếp cần sắp xếp ổn định theo thời gian và một khóa phụ duy nhất, cùng chiến lược cursor/paging state rõ ràng.

**Checklist trước khi đưa thiết kế vào hệ thống:**

- Mỗi API đọc có `WHERE` tương thích với khóa và thứ tự lưu trữ.
- Phân bố kích thước/tải partition đã được ước lượng theo dữ liệu tăng trưởng và khách lớn nhất.
- Mọi bảng nhân bản có nguồn dữ liệu thẩm quyền, cơ chế cập nhật, retry và sửa lệch.
- Giới hạn truy vấn, phân trang, timeout và consistency được kiểm tra dưới tải đại diện.
- Có kế hoạch cho schema evolution, giám sát, bảo mật, giữ/xóa và khôi phục dữ liệu.

Điều quyết định trong mô hình wide-column là **thiết kế dữ liệu từ truy vấn và hành vi tải thực tế**. Lược đồ tốt cho phép ứng dụng Java tìm đến đúng partition và đọc đúng dải hàng cần thiết, đồng thời kiểm soát được chi phí nhân bản, tăng trưởng và nhất quán khi dữ liệu thay đổi.
