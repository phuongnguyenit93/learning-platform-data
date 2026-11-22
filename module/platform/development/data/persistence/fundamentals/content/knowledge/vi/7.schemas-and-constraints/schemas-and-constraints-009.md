# Phi chuẩn hóa có chủ đích theo nhu cầu truy cập

Một cơ sở dữ liệu quan hệ được chuẩn hóa thường giảm dữ liệu lặp và giúp bảo vệ tính nhất quán. Tuy nhiên, có những chức năng phải đọc dữ liệu liên tục, gộp nhiều bảng hoặc tính cùng một tổng hàng nghìn lần mỗi giây. Trong một số trường hợp đã đo đạc, việc **lưu thêm một giá trị dẫn xuất hoặc một mô hình chuyên cho đọc** có thể cải thiện độ trễ và thông lượng.

Kỹ thuật đó gọi là **phi chuẩn hóa (denormalization)**. Từ khóa quan trọng là **có chủ đích**: nhóm thiết kế phải biết mình đang sao chép giá trị nào, để phục vụ truy cập nào, sẽ giữ các bản sao đồng bộ bằng cách nào và kiểm chứng lợi ích ra sao.

Bài học thuộc chương **Lược đồ và ràng buộc** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Nội dung kết nối việc mô hình hóa và lược đồ với truy vấn, chỉ mục, giao dịch, cô lập, kiểm soát đồng thời, ranh giới persistence trong Java, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Chuẩn hóa và phi chuẩn hóa giải quyết những vấn đề nào?

**Chuẩn hóa (normalization)** tổ chức dữ liệu thành những quan hệ có phụ thuộc hợp lý, hạn chế trùng lặp không cần thiết và các bất thường khi thêm, sửa, xóa. Trong mô hình quan hệ, ta thường đưa thông tin chỉ phụ thuộc vào mã sản phẩm vào bảng sản phẩm, và thông tin chỉ phụ thuộc vào mã khách hàng vào bảng khách hàng.

Ví dụ:

~~~text
products(id, name, current_price)
orders(id, customer_id, created_at, status)
order_lines(order_id, line_no, product_id, quantity, unit_price)
~~~

Trong mô hình này, tên sản phẩm hiện tại được quản lý tập trung ở `products`, mỗi đơn có nhiều dòng hàng và tổng tiền hàng có thể được **tính từ các dòng hàng**.

**Phi chuẩn hóa** là đưa vào mô hình lưu trữ một số giá trị lặp, tổng hợp hoặc dữ liệu đã được kết hợp sẵn nhằm tối ưu đường đọc hoặc xử lý cụ thể:

~~~text
orders(..., items_total)           -- tổng tiền hàng lưu sẵn
customer_order_stats(..., count)   -- số đơn tổng hợp theo khách
order_search(..., customer_name)   -- dữ liệu đã ghép cho tìm kiếm
~~~

Các giá trị trên có thể làm đọc nhanh hơn, nhưng kéo theo trách nhiệm **cập nhật, đồng bộ và sửa sai** khi nguồn dữ liệu thay đổi.

| Tiêu chí | Mô hình chuẩn hóa | Mô hình phi chuẩn hóa có chủ đích |
| --- | --- | --- |
| Dữ liệu lặp | Thường ít | Chủ động lưu thêm giá trị lặp/dẫn xuất |
| Đọc thông tin tổng hợp | Có thể cần `JOIN`, `SUM`, `GROUP BY` | Có thể đọc trực tiếp cột/bảng đã tính |
| Ghi và sửa | Thường cập nhật ít nơi | Có thể phải cập nhật nhiều nơi |
| Tính nhất quán | Tập trung vào dữ liệu gốc và ràng buộc | Phải định nghĩa quan hệ giữa dữ liệu gốc và bản sao |
| Dung lượng | Thường tiết kiệm hơn | Tăng lưu trữ, chỉ mục và đôi khi WAL/replication |
| Phù hợp | Nền tảng mặc định cho dữ liệu nghiệp vụ | Sau khi có bằng chứng về đường truy cập cần tối ưu |

Phi chuẩn hóa **không đồng nghĩa bỏ khóa ngoại, bỏ kiểm tra dữ liệu hay lưu mọi thứ vào một bảng**. Có thể giữ schema chuẩn hóa làm nguồn sự thật, đồng thời tạo một bản đọc tối ưu riêng.

## 2. Ví dụ xuyên suốt: danh sách đơn hàng và tổng tiền hàng

Một hệ thống bán hàng có các yêu cầu:

- Xem **20 đơn hàng gần nhất** của một khách.
- Trên mỗi đơn, hiển thị số tiền hàng trước phí vận chuyển và thuế.
- Cho phép thêm, sửa, xóa dòng hàng khi đơn ở trạng thái nháp.
- Khi đã xác nhận đơn, giữ số tiền nhất quán với dữ liệu được chốt.

Đầu tiên, dùng mô hình quan hệ đơn giản theo PostgreSQL:

~~~sql
CREATE TABLE orders (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_lines (
    order_id    BIGINT NOT NULL REFERENCES orders(id),
    line_no     INTEGER NOT NULL CHECK (line_no > 0),
    product_id  BIGINT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE INDEX idx_orders_customer_latest
    ON orders (tenant_id, customer_id, created_at DESC, id DESC);
~~~

Ở đây `unit_price` là **đơn giá áp dụng cho dòng đơn tại thời điểm đặt hàng**, không phải giá hiện tại của sản phẩm. Một **ảnh chụp giá lịch sử** có ý nghĩa nghiệp vụ độc lập và có thể cần được lưu ngay cả khi không thực hiện tối ưu phi chuẩn hóa. Không nên tự động xem mọi dữ liệu trông có vẻ lặp là một lỗi cần loại bỏ.

Tổng tiền hàng của đơn được định nghĩa rõ:

`items_total = SUM(quantity × unit_price)`

Phạm vi ví dụ **không bao gồm** thuế, giảm giá và vận chuyển. Trong hệ thống thực tế, công thức phải tính cả đơn vị tiền tệ, quy tắc làm tròn, hoàn tiền và các yếu tố khác nếu chúng thuộc nghiệp vụ.

Giả sử đơn 42 có hai dòng:

| Dòng | Số lượng | Đơn giá (VND) | Thành tiền (VND) |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 125.000,00 | 250.000,00 |
| 2 | 1 | 50.000,00 | 50.000,00 |
| | | **Tổng** | **300.000,00** |

Nếu thêm dòng 3 gồm 3 sản phẩm giá 20.000,00, tổng mới sẽ là **360.000,00**.

## 3. Trước khi phi chuẩn hóa: tối ưu truy vấn trên mô hình hiện có

Một sai lầm là thấy `JOIN` hoặc `SUM` rồi lập tức thêm cột tổng. Trước hết cần xem liệu **truy vấn đúng phạm vi** và **chỉ mục phù hợp** đã đủ nhanh chưa.

Ví dụ lấy một trang 20 đơn trước, sau đó mới tính tổng cho chính những đơn đó:

~~~sql
WITH page AS (
    SELECT id, customer_id, created_at, status
    FROM orders
    WHERE tenant_id = :tenant_id
      AND customer_id = :customer_id
    ORDER BY created_at DESC, id DESC
    LIMIT 20
)
SELECT p.id,
       p.customer_id,
       p.created_at,
       p.status,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS items_total
FROM page AS p
LEFT JOIN order_lines AS l ON l.order_id = p.id
GROUP BY p.id, p.customer_id, p.created_at, p.status
ORDER BY p.created_at DESC, p.id DESC;
~~~

Dấu `:tenant_id` và `:customer_id` là tham số minh họa của tầng ứng dụng; với JDBC thuần, dùng dấu `?` và `PreparedStatement` thay vì đưa giá trị người dùng vào SQL bằng nối chuỗi.

Với `PRIMARY KEY (order_id, line_no)`, database có một chỉ mục phù hợp để tìm các dòng của từng đơn theo `order_id`. Chỉ mục `idx_orders_customer_latest` hỗ trợ phần lọc và sắp xếp đơn mới nhất theo tenant/khách, tùy kế hoạch tối ưu thực tế.

Khi xem xét hiệu năng, cần kiểm tra:

1. Truy vấn đã **phân trang trước khi tính tổng** hay đang quét/tổng hợp mọi đơn của khách?
2. Điều kiện `WHERE` và `ORDER BY` có dùng chỉ mục phù hợp không?
3. Một API có vô tình tạo **N+1 queries** do ORM tải dòng hàng từng đơn không?
4. Database có phải đọc hàng triệu dòng vì thiếu điều kiện lọc không?
5. Độ trễ p95/p99 được đo ở **toàn bộ API** hay chỉ tại một câu SQL?
6. Tập dữ liệu, số dòng/đơn và tỷ lệ đọc/ghi của benchmark có gần môi trường thật không?

Trên PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` có thể giúp kiểm tra kế hoạch và I/O khi được sử dụng trong môi trường kiểm thử phù hợp. Câu truy vấn tốt cùng chỉ mục đúng nhiều khi đã giải quyết vấn đề, tránh phải duy trì thêm một bản dữ liệu sao chép.

### Khi nào có bằng chứng để tiếp tục?

Ví dụ giả định: API danh sách cần p99 dưới 200 ms tại 800 lượt đọc/giây trong giờ cao điểm. Sau khi phân trang, thêm chỉ mục và loại bỏ N+1, phần tính tổng vẫn chiếm nhiều I/O/CPU vì đa số đơn có rất nhiều dòng. Một cột tổng đã tính sẵn có thể đáng thử nghiệm.

Đây chỉ là **tình huống minh họa**. Ngưỡng p99, RPS và tỷ lệ đọc/ghi phải được xác định theo nhu cầu thực tế, không dùng như một tiêu chuẩn chung.

## 4. Các dạng phi chuẩn hóa thường gặp

Không phải mọi cách phi chuẩn hóa đều giống nhau.

| Kỹ thuật | Ví dụ | Lợi ích | Nghĩa vụ đồng bộ |
| --- | --- | --- | --- |
| **Lưu tổng/đếm sẵn** | `orders.items_total`, `customers.order_count` | Tránh tính lại `SUM`/`COUNT` thường xuyên | Cập nhật khi thêm, sửa, xóa dữ liệu nguồn |
| **Sao chép thuộc tính phục vụ đọc** | Lưu tên nhóm sản phẩm vào bảng kết quả tìm kiếm | Giảm bước ghép bảng hoặc truy vấn tới hệ khác | Quyết định khi nguồn đổi tên |
| **Bảng đọc đã ghép (read model)** | `order_list_view` chứa số đơn, tên khách, tổng | Một truy vấn tối ưu cho giao diện | Cập nhật hoặc dựng lại từ dữ liệu nguồn |
| **Materialized view** | Kết quả truy vấn tổng hợp được lưu vật lý | Đọc báo cáo nhanh | Phải refresh; chấp nhận dữ liệu trễ hoặc có cơ chế cập nhật |
| **Bản sao vào search index** | Tài liệu đơn hàng trong Elasticsearch/OpenSearch | Full-text search và tìm kiếm linh hoạt | Đồng bộ sự kiện, xử lý retry/thứ tự |
| **Cache/projection** | Tổng quan tài khoản trong Redis | Đọc ít tốn tài nguyên DB | TTL, invalidation, consistency và xử lý cache miss |
| **Dữ liệu JSON đã gom** | Snapshot thông tin giao diện trong JSONB | Đọc trọn một cấu trúc theo một lần lấy | Quy tắc cập nhật một phần, index, migration và kiểm tra schema |

**Đừng đánh đồng snapshot với dữ liệu lặp vô ích.** Chẳng hạn, địa chỉ giao hàng hoặc giá bán được chốt tại thời điểm đặt hàng là **bằng chứng lịch sử**. Dù dữ liệu khách hàng hoặc giá niêm yết thay đổi về sau, snapshot đơn hàng có thể phải giữ nguyên theo hợp đồng nghiệp vụ. Ngược lại, trường `current_customer_name` được sao chép để hiển thị tên mới nhất là dữ liệu dẫn xuất cần đồng bộ khi tên khách đổi.

### Một số kỹ thuật không phải phi chuẩn hóa

- **Thêm chỉ mục:** tạo cấu trúc truy cập vật lý nhưng không nhất thiết thay đổi mô hình logic hay lưu thêm một thuộc tính nghiệp vụ.
- **Phân vùng (partitioning):** tổ chức dữ liệu thành phần để quản lý/truy vấn, không bắt buộc tạo bản sao dẫn xuất.
- **Đổi cách encode byte hoặc nén:** chủ yếu đổi biểu diễn vật lý.
- **Lưu sự kiện lịch sử:** có thể là nguồn dữ liệu chính (event sourcing), không mặc định là bản sao dư thừa.

Cần xác định rõ đang tối ưu **mô hình logic**, **đường truy vấn**, hay **cơ chế lưu trữ** để đánh giá đúng chi phí.

## 5. Thêm cột tổng tiền hàng: lợi ích và bất biến mới

Giả sử nhóm chọn lưu tổng tiền hàng trên `orders`:

~~~sql
ALTER TABLE orders
ADD COLUMN items_total NUMERIC(19, 2);
~~~

Cột được thêm ở trạng thái nullable để thuận tiện cho quá trình triển khai và điền dữ liệu cũ. Sau khi có quy trình đồng bộ, backfill và kiểm tra, ta mới áp dụng `DEFAULT`, `NOT NULL` và ràng buộc phù hợp cho trạng thái cuối.

Truy vấn trang danh sách sau khi có tổng sẵn trở nên đơn giản:

~~~sql
SELECT id, customer_id, created_at, status, items_total
FROM orders
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Từ đây xuất hiện **bất biến (invariant)** mà schema phải duy trì:

`orders.items_total = SUM(order_lines.quantity × order_lines.unit_price)`

Mặc định với đơn chưa có dòng, tổng là **0**, chứ không phải `NULL`. Nếu ứng dụng chỉ cập nhật `order_lines` mà quên `orders.items_total`, bất biến sẽ bị phá vỡ.

Những trường hợp phải được thiết kế đầy đủ:

| Thay đổi dòng hàng | Tác động đúng lên tổng |
| --- | --- |
| Thêm dòng giá trị `+60.000` | Tăng `items_total` 60.000 |
| Xóa dòng giá trị `50.000` | Giảm `items_total` 50.000 |
| Sửa số lượng từ 2 lên 3, đơn giá 125.000 | Tăng `items_total` 125.000 |
| Đổi đơn giá dòng từ 20.000 lên 18.000, số lượng 3 | Giảm `items_total` 6.000 |
| Rollback thao tác dòng hàng | Mọi thay đổi tổng liên quan phải rollback cùng |
| Xóa cả đơn theo chính sách hợp lệ | Xử lý dữ liệu con và tổng theo quan hệ/ràng buộc đã chọn |

Một thay đổi có thể tác động **nhiều bản ghi nguồn**, nên không thể coi việc tính tổng là giá trị tự động từ một cột cùng hàng. Trong PostgreSQL, **generated column** hỗ trợ biểu thức trong hàng theo giới hạn của hệ quản trị, không thay thế việc tổng hợp `SUM` trên bảng khác.

### Tính chính xác của số tiền

Dùng `NUMERIC/DECIMAL` trong database và `BigDecimal` trong Java cho nghiệp vụ cần chính xác thập phân. Cần thống nhất:

- Đơn vị tiền tệ của tổng.
- Scale cho đơn giá, tổng và phép nhân số lượng.
- Quy tắc làm tròn, giảm giá và thuế nếu có.
- Giới hạn miền giá trị để tránh tràn kiểu/cột.
- Cách hoàn tiền hoặc giá trị âm nếu nghiệp vụ cho phép.

Ví dụ đang giới hạn `items_total` là tiền hàng không âm. Nếu sau này đưa hoàn tiền, điều chỉnh hoặc nhiều loại tiền tệ vào công thức, **phải thay đổi bất biến một cách có chủ đích**, không chỉ sửa một dòng SQL.

## 6. Đồng bộ mạnh: cập nhật nguồn và cột dẫn xuất trong một giao dịch

Khi tổng phải đúng ngay sau khi thao tác ghi thành công, một cách tiếp cận là **cập nhật dòng hàng và tổng trong cùng transaction của một database**.

Minh họa một thao tác thêm dòng cho đơn `DRAFT`:

~~~sql
BEGIN;

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price)
VALUES
    (42, 3, 9003, 3, 20000.00);

UPDATE orders
SET items_total = items_total + 60000.00
WHERE id = 42
  AND tenant_id = 7
  AND status = 'DRAFT';

COMMIT;
~~~

**Đây chỉ là luồng minh họa, không phải script nên thực thi nguyên khối mà không kiểm tra kết quả.** Ứng dụng phải xác nhận `INSERT` thành công và lệnh `UPDATE` ảnh hưởng **đúng một hàng**. Nếu không tìm thấy đơn, sai tenant, đơn đã chốt hoặc có xung đột, cần `ROLLBACK` để không để lại dòng hàng nhưng thiếu phần tổng tương ứng.

Phép `items_total = items_total + 60000` thực hiện cộng dựa trên giá trị hiện tại trong database. Khi nhiều giao dịch cùng cập nhật một hàng PostgreSQL, khóa hàng và quy tắc isolation của engine điều phối các thay đổi; cách này tránh lỗi phổ biến là đọc tổng về Java, cộng trên một giá trị cũ rồi ghi đè bằng `SET items_total = :stale_value`.

**Điều kiện bắt buộc:** mọi đường ghi dữ liệu gốc phải duy trì cùng bất biến. Nếu một batch, script, job hoặc dịch vụ khác sửa `order_lines` mà không cập nhật `orders.items_total`, một transaction riêng lẻ trong đường API không thể giữ hệ thống nhất quán toàn cục.

### Ví dụ Java JDBC theo một transaction

Một phương thức minh họa, giả định `orders.items_total` đã được khởi tạo chính xác và chuyển sang không null:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderLineWriter {
    private final DataSource dataSource;

    public OrderLineWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void addLine(
            long tenantId,
            long orderId,
            int lineNo,
            long productId,
            int quantity,
            BigDecimal unitPrice) throws SQLException {

        if (lineNo <= 0 || quantity <= 0 ||
                unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }

        BigDecimal normalizedPrice =
            unitPrice.setScale(2, RoundingMode.UNNECESSARY);
        BigDecimal delta =
            normalizedPrice.multiply(BigDecimal.valueOf(quantity));

        String insert = """
            INSERT INTO order_lines
                (order_id, line_no, product_id, quantity, unit_price)
            VALUES (?, ?, ?, ?, ?)
            """;

        String update = """
            UPDATE orders
            SET items_total = items_total + ?
            WHERE id = ? AND tenant_id = ? AND status = 'DRAFT'
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement stmt =
                         connection.prepareStatement(insert)) {
                    stmt.setLong(1, orderId);
                    stmt.setInt(2, lineNo);
                    stmt.setLong(3, productId);
                    stmt.setInt(4, quantity);
                    stmt.setBigDecimal(5, normalizedPrice);

                    if (stmt.executeUpdate() != 1) {
                        throw new IllegalStateException("Không chèn được dòng");
                    }
                }

                try (PreparedStatement stmt =
                         connection.prepareStatement(update)) {
                    stmt.setBigDecimal(1, delta);
                    stmt.setLong(2, orderId);
                    stmt.setLong(3, tenantId);

                    if (stmt.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Đơn không tồn tại, sai tenant hoặc không còn DRAFT"
                        );
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đoạn code dùng Java 17+ (text block), JDBC và `DataSource` được cấu hình sẵn. `tenantId` phải đến từ ngữ cảnh xác thực/phân quyền đáng tin cậy, không chỉ từ giá trị do client tự gửi. Ngoài ra, **đơn giá có thể cần được xác định lại ở server từ quy tắc giá đã được phép áp dụng**, chứ không mù quáng tin một con số từ request.

Ví dụ tập trung vào quy tắc cập nhật tổng và commit; chưa bao gồm xử lý mọi dạng cập nhật/xóa dòng, cơ chế idempotency, API errors, event publishing hoặc cấu hình connection pool. Với pool và framework transaction, vòng đời, trạng thái `autoCommit` và cách trả kết nối phải tuân theo hợp đồng của chúng.

**Phân biệt lỗi trước và sau commit:** khi mạng đứt đúng lúc `commit()`, ứng dụng có thể không biết giao dịch đã thành công hay chưa. Thử lại `addLine()` một cách mù quáng có thể tạo xung đột dòng hoặc ghi lặp ở những đường xử lý khác. Nếu cần retry an toàn, thiết kế **idempotency key** cho thao tác nghiệp vụ với ràng buộc unique và kết quả đã lưu.

## 7. Giao dịch và đồng thời chưa đủ nếu quy tắc cập nhật không đồng nhất

Cột tổng là một bản sao dẫn xuất. Để giữ nó đúng trong môi trường nhiều người ghi, cần xác định **ai được phép cập nhật** và cập nhật theo quy tắc nào.

### Khi sửa hoặc xóa dòng hàng

Giả sử dòng hàng có giá trị ban đầu 250.000 và giá trị mới 375.000. Delta đúng là:

`delta = new_line_amount - old_line_amount = 125.000`

Ứng dụng cần lấy **giá trị cũ trong một transaction có kiểm soát**, cập nhật dòng hàng, cộng delta vào tổng và commit tất cả cùng nhau. Nếu một giao dịch khác sửa dòng trước khi delta được tính xong, cần khóa dòng/đơn hoặc dùng optimistic version để tránh dựa trên trạng thái lỗi thời.

Một chính sách đơn giản để giảm phức tạp là **khóa bản ghi đơn trước mọi thay đổi ở các dòng của đơn đó**, sau đó sửa dòng và tổng trong cùng transaction. Cách này tuần tự hóa thay đổi theo đơn nhưng có thể giảm thông lượng nếu nhiều request liên tục sửa cùng một đơn. Không nên khóa cả tập dữ liệu lớn hơn mức nghiệp vụ yêu cầu.

### Triggers ở database

Một lựa chọn khác là khai báo trigger để khi `order_lines` được thêm, sửa hoặc xóa, database tự cập nhật `orders.items_total`. Lợi ích là các đường ghi SQL hợp lệ cùng đi qua trigger. Nhưng trigger:

- Phải tính đúng delta cho cả `INSERT`, `UPDATE` và `DELETE`.
- Phải xét thứ tự, khóa, transaction, các trường hợp bulk load.
- Có thể tạo logic khó nhìn từ mã Java và tăng chi phí ghi.
- Cần kiểm thử trên DB engine và phiên bản cụ thể.

Trigger không tự giải quyết lỗi nghiệp vụ nếu công thức không rõ, dữ liệu cũ sai hoặc có nhiều database độc lập.

### Optimistic locking và phiên bản

Nếu Java/JPA quản lý entity với `@Version` hoặc cột `version`, ứng dụng có thể phát hiện một số xung đột khi hai transaction sửa cùng bản ghi. Nhưng cần tránh vừa áp optimistic locking tại entity vừa có batch SQL cập nhật trực tiếp bỏ qua cơ chế phiên bản, khiến đường ghi không đồng nhất.

Mức isolation cao hơn không thay thế bất biến: nếu code chỉ cập nhật dòng và quên tổng thì dù transaction ở mức SERIALIZABLE, dữ liệu dẫn xuất vẫn có thể sai.

## 8. Đồng bộ bất đồng bộ: read model, event và eventual consistency

Trong nhiều hệ thống, bảng chuyên để phục vụ màn hình hoặc tìm kiếm có thể được cập nhật **sau** khi giao dịch nguồn commit.

Ví dụ:

~~~mermaid
flowchart LR
    A["API ghi đơn và dòng hàng"] --> B[("DB nguồn sự thật")]
    B --> C["Outbox event cùng transaction"]
    C --> D["Worker / message relay"]
    D --> E["Projection / read model"]
    E --> F["API đọc danh sách / tìm kiếm"]
~~~

Đường đi này thường gặp trong **CQRS** hoặc hệ thống có read model tách biệt. Thay vì bắt mọi thay đổi nghiệp vụ cập nhật ngay nhiều nơi, ứng dụng có thể:

1. Ghi dữ liệu gốc cùng một bản ghi **outbox** trong cùng transaction database.
2. Một worker lấy event từ outbox rồi gửi đến hệ thống xử lý.
3. Consumer cập nhật projection, cache hoặc search index.
4. Đường đọc chuyên dụng truy vấn read model.

Lợi ích là giảm phụ thuộc tức thời giữa giao dịch ghi và kho đọc, có thể mở rộng độc lập và tối ưu truy vấn. Đổi lại, **dữ liệu đọc có thể trễ** so với dữ liệu gốc.

### Định nghĩa rõ độ trễ được chấp nhận

Thay vì nói chung “nhất quán cuối cùng”, hãy viết hợp đồng:

> Sau khi cập nhật đơn thành công, chi tiết đơn ở kho nguồn phản ánh thay đổi ngay theo mức isolation đã quy định. Trang danh sách tổng hợp có thể chậm tối đa 5 giây trong điều kiện hoạt động bình thường; nếu projection lỗi, hệ thống hiển thị trạng thái đang cập nhật hoặc đọc từ nguồn theo chính sách.

Mức 5 giây chỉ là **ví dụ yêu cầu**, cần đo thực tế và có chiến lược khi vượt ngưỡng. Với nghiệp vụ chuyển tiền, hạn mức tín dụng hoặc giữ chỗ, không được mặc định rằng tổng trễ vài giây cũng chấp nhận được.

### Event có thể bị lặp hoặc đến sai thứ tự

Một hệ thống truyền event có retry thường có thể giao **ít nhất một lần (at-least-once)**. Consumer phải xử lý:

- **Chống lặp** bằng `event_id` hoặc `operation_id` đã xử lý.
- **Thứ tự** theo khóa thực thể/stream và version nguồn.
- **Khôi phục** projection từ snapshot hoặc dữ liệu nguồn khi bỏ lỡ sự kiện.
- **Tự đối soát** thay vì tin rằng mọi sự kiện đã được xử lý đúng.
- **Quyền đọc dữ liệu** trên projection giống hoặc chặt hơn nguồn khi cần.

Ví dụ nếu consumer nhận hai lần sự kiện `OrderLineAdded(+60000)` mà chỉ làm `total += 60000`, tổng sẽ bị cộng đôi. Có thể lưu `event_id` với ràng buộc unique trong cùng transaction cập nhật read model, hoặc xây dựng projection từ phiên bản trạng thái được tính lại. Không thể chỉ thêm message queue rồi tuyên bố đã đồng bộ chính xác.

## 9. Materialized view và bảng tổng hợp: chọn đúng thời điểm làm mới

Khi một truy vấn phân tích nhiều đơn hàng phức tạp hoặc có tải đọc cao, cơ sở dữ liệu có thể duy trì **materialized view**.

Ví dụ PostgreSQL:

~~~sql
CREATE MATERIALIZED VIEW order_items_totals AS
SELECT o.id AS order_id,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS items_total
FROM orders AS o
LEFT JOIN order_lines AS l ON l.order_id = o.id
GROUP BY o.id;

CREATE UNIQUE INDEX uq_order_items_totals_id
ON order_items_totals (order_id);
~~~

Đọc:

~~~sql
SELECT order_id, items_total
FROM order_items_totals
WHERE order_id = 42;
~~~

Materialized view lưu kết quả truy vấn để đọc nhanh, nhưng **PostgreSQL không tự làm mới nó theo mỗi lần thay đổi ở bảng nguồn**. Cần chủ động chọn chính sách refresh:

~~~sql
REFRESH MATERIALIZED VIEW order_items_totals;
~~~

Mức độ dữ liệu cũ phụ thuộc thời điểm refresh. `REFRESH MATERIALIZED VIEW CONCURRENTLY` có các điều kiện riêng (ví dụ unique index phù hợp, view đã được populate); nó không phải lời hứa cập nhật tức thời và có chi phí vận hành.

Với truy vấn cần gần thời gian thực và bảng lớn, một **bảng tổng hợp được cập nhật tăng dần bằng event/transaction** có thể phù hợp hơn việc refresh toàn bộ materialized view. Nhưng bảng tổng hợp tự quản lý đòi hỏi cơ chế đồng bộ, versioning và phục hồi phức tạp hơn.

Cần phân biệt:

- **View thường:** biểu thức truy vấn, không phải bản sao tổng được lưu vật lý theo nghĩa materialized view.
- **Materialized view:** kết quả được lưu và cần refresh.
- **Cột tổng trong bảng gốc:** cập nhật theo đường ghi hoặc trigger.
- **Read model ngoại vi:** dữ liệu nằm tại kho khác, có thể trễ và cần cơ chế phát sự kiện đáng tin cậy.

## 10. Đọc nhanh hơn có thể khiến ghi chậm hơn

Phi chuẩn hóa không miễn phí. Khi thêm `orders.items_total`, một lệnh thêm dòng hàng cần cập nhật thêm hàng cha. Nếu nhiều người cùng ghi vào **một đơn hàng nóng**, hàng cha trở thành điểm tranh chấp.

### Chi phí thường phát sinh

| Chi phí | Ví dụ |
| --- | --- |
| **Write amplification** | Một thao tác dòng hàng còn ghi hàng cha, index, WAL, replica |
| **Hot row / lock contention** | Nhiều transaction chờ cập nhật cùng `orders.id` |
| **Dung lượng và index** | Cột tổng, bảng đọc, materialized view và index tăng dung lượng |
| **Độ trễ ghi** | Tính toán, khóa và xác nhận nhiều thay đổi trước commit |
| **Độ phức tạp khi đổi schema** | Một trường đổi tên phải cập nhật source, projection và consumer |
| **Rủi ro dữ liệu cũ** | Cache/read model không cập nhật kịp hoặc bỏ lỡ event |
| **Vận hành/khôi phục** | Rebuild projection và đối soát khi triển khai/sự cố |

Có những trường hợp bản tổng thậm chí không làm đọc nhanh hơn đáng kể vì truy vấn chuẩn hóa đã được index tốt và chỉ xử lý vài dòng.

### Đánh giá bằng cùng workload

Trước và sau khi thay đổi, nên dùng cùng:

- Số bản ghi, phân phối kích thước đơn và tỷ lệ đơn có nhiều dòng.
- Tỷ lệ đọc/ghi và các tình huống sửa/xóa dòng hàng.
- Mức đồng thời, đặc biệt là số request cùng sửa một đơn.
- SLO p50/p95/p99 của API đọc **và** API ghi, RPS thành công và tỷ lệ lỗi.
- Cấu hình tài nguyên database, connection pool, kích thước cache, index và replication.
- Kiểm tra tính đúng đắn của tổng sau khi có lỗi, retry và concurrent update.

Kết luận “đọc nhanh gấp đôi” không đủ nếu ghi chậm nghiêm trọng, sai lệch dữ liệu tăng hoặc khả năng phục hồi bị suy giảm. Việc chấp nhận đánh đổi phải dựa vào mục tiêu hệ thống, bao gồm tính đúng đắn.

## 11. Migration an toàn khi bổ sung dữ liệu dẫn xuất

Thêm một cột tổng vào bảng đã có hàng triệu đơn cần nhiều bước hơn một lệnh `ALTER TABLE`. Nếu áp `NOT NULL DEFAULT 0` rồi coi toàn bộ dữ liệu cũ có tổng bằng 0, giá trị đọc sẽ sai với những đơn đã có dòng.

Một quy trình triển khai theo giai đoạn:

### Bước 1 — Chốt quy tắc nguồn và bất biến

Ghi rõ `items_total` là tổng các dòng hàng, làm tròn ra sao, đơn vị tiền là gì và trường hợp dữ liệu hỏng xử lý thế nào. Xác định **nguồn sự thật** (ở đây là `order_lines`), chủ sở hữu cập nhật và các đường ghi cần thay đổi.

### Bước 2 — Mở rộng schema, chưa chuyển người đọc

~~~sql
ALTER TABLE orders
ADD COLUMN items_total NUMERIC(19, 2);
~~~

Giá trị của đơn cũ là `NULL` cho đến khi backfill. Trong giai đoạn chuyển đổi, đường đọc có thể tạm tính lại từ dữ liệu nguồn khi `items_total IS NULL`, nhưng phải ghi rõ cách fallback.

### Bước 3 — Triển khai đường ghi giữ đồng bộ

Sửa tất cả mã tạo/sửa/xóa dòng hàng để cập nhật `items_total` trong transaction tương ứng, hoặc triển khai trigger/kỹ thuật đồng bộ thích hợp. Với đơn mới, khởi tạo tổng đúng bằng 0 trước khi thêm dòng.

**Cần lập kế hoạch race với backfill:** một job điền tổng có thể đọc các dòng cũ trong lúc người dùng thêm dòng mới. Nếu không khóa/điều phối theo từng đơn hoặc dùng version, giá trị do backfill ghi có thể đè lên cập nhật mới. Chọn rõ quy tắc khóa, phân đoạn dữ liệu, kiểm tra version và thứ tự triển khai để tránh tình huống này.

### Bước 4 — Backfill theo lô

Ví dụ minh họa về cách tính lại tổng cho một khoảng ID trong PostgreSQL:

~~~sql
UPDATE orders AS o
SET items_total = COALESCE((
    SELECT SUM(l.quantity * l.unit_price)
    FROM order_lines AS l
    WHERE l.order_id = o.id
), 0)
WHERE o.id BETWEEN 1000 AND 1999;
~~~

Với bảng lớn, chia lô nhỏ và quan sát lock, I/O, replication lag và độ trễ API. **Không coi lệnh trên tự an toàn dưới ghi đồng thời**: nó cần được chạy theo cơ chế điều phối/khóa đã quyết định ở bước 3 hoặc trong cửa sổ bảo trì phù hợp. Cũng phải bảo đảm backfill không thay thế các giá trị tổng mới bằng dữ liệu cũ.

### Bước 5 — Đối soát và chốt ràng buộc

Tìm các đơn có tổng lưu sẵn khác giá trị tính từ nguồn:

~~~sql
SELECT o.id,
       o.items_total AS stored_total,
       COALESCE((
           SELECT SUM(l.quantity * l.unit_price)
           FROM order_lines AS l
           WHERE l.order_id = o.id
       ), 0) AS recomputed_total
FROM orders AS o
WHERE o.items_total IS DISTINCT FROM COALESCE((
    SELECT SUM(l.quantity * l.unit_price)
    FROM order_lines AS l
    WHERE l.order_id = o.id
), 0);
~~~

Với bảng lớn, câu truy vấn minh họa này có thể tốn tài nguyên; cần chạy theo phạm vi/lô, trên môi trường cho phép và đo chi phí. Khi tất cả đơn có tổng đúng, chính sách giữ đồng bộ đã được kiểm chứng và không còn `NULL` ngoài ý muốn, có thể áp:

~~~sql
ALTER TABLE orders
ALTER COLUMN items_total SET DEFAULT 0;

ALTER TABLE orders
ALTER COLUMN items_total SET NOT NULL;

ALTER TABLE orders
ADD CONSTRAINT ck_orders_items_total_nonnegative
CHECK (items_total >= 0);
~~~

Áp `NOT NULL` và `CHECK` không tự chứng minh tổng luôn bằng `SUM` của bảng con. Bất biến **xuyên bảng** vẫn phải được bảo vệ bởi transaction, trigger hoặc cơ chế đồng bộ do thiết kế chọn.

### Bước 6 — Chuyển người đọc và theo dõi

Sau khi dữ liệu cũ được đối soát, đường đọc mới lấy `items_total` trực tiếp. Theo dõi chênh lệch giữa tổng nguồn và tổng dẫn xuất, thời gian cập nhật, lỗi transaction, lock wait và thời gian query. Giữ phương án rollback khả thi: có thể chuyển người đọc về phép tính nguồn, nhưng vẫn phải xem xét dữ liệu và schema đã phát hành cho consumer khác.

## 12. Bảo mật, phân quyền và dữ liệu nhạy cảm khi phi chuẩn hóa

Sao chép dữ liệu để đọc nhanh hơn đồng nghĩa tạo thêm nơi cần kiểm soát.

Ví dụ một `order_search` sao chép `customer_name`, `email` và `shipping_address` từ nhiều bảng. Nếu quyền truy cập hoặc chính sách lưu giữ thay đổi:

- Dữ liệu trong search index/cache có được xóa, ẩn hoặc cập nhật kịp thời không?
- Bản đọc có ngăn truy vấn sai tenant không?
- Việc xóa/mã hóa dữ liệu cá nhân có lan tới projection, bản sao lưu và log không?
- Có truy vấn nào lấy nhiều trường nhạy cảm hơn mức cần thiết không?
- Quy trình tái dựng read model có áp đúng quy tắc phân quyền và retention không?

Trong hệ đa tenant, một read model có thể phải giữ `tenant_id` và truy vấn theo tenant trong mọi đường truy cập. **Sao chép dữ liệu không thay thế kiểm tra quyền**. Có thể giữ ID nghiệp vụ và tạo projection chỉ chứa những trường thực sự cần cho use case, giúp giảm cả dung lượng và rủi ro.

Khi tích hợp với hệ search hoặc cache ngoài database chính, cần chú ý mã hóa truyền/lưu, quyền truy cập dịch vụ, thời gian lưu, idempotency của đồng bộ và khả năng phát hiện bản ghi mồ côi.

## 13. Kiểm thử bất biến, lỗi và khả năng phục hồi

Bất kỳ bản sao dẫn xuất nào cũng nên có cách **kiểm tra và tái dựng** từ dữ liệu nguồn.

### Kiểm thử tính đúng đắn

Một bộ kiểm thử có giá trị cần bao gồm:

1. Tạo đơn rỗng: `items_total = 0`.
2. Thêm hai dòng hàng và xác minh tổng chính xác.
3. Cập nhật số lượng/đơn giá và cộng đúng delta.
4. Xóa dòng hàng và trừ đúng delta.
5. Thử thêm dòng trùng `(order_id, line_no)`: giao dịch lỗi, tổng không thay đổi.
6. Thử sửa đơn `CONFIRMED`: đường ghi bị từ chối theo chính sách, tổng và dòng hàng giữ nguyên.
7. Hai request cùng thêm dòng vào một đơn: không có lost update.
8. Lỗi sau khi cập nhật dòng nhưng trước khi cập nhật tổng: transaction rollback cả hai.
9. Timeout hoặc mất kết nối lúc commit: retry theo idempotency, không tạo hiệu ứng nghiệp vụ lặp.
10. Batch/job hoặc importer: vẫn đi qua đường đồng bộ đúng, hoặc có quy trình đối soát.

### Kiểm thử projection bất đồng bộ

Với read model tách kho, thử consumer:

- Nhận cùng event hai lần.
- Nhận event phiên bản `N+1` trước `N`.
- Khởi động lại giữa cập nhật projection và đánh dấu event đã xử lý.
- Không thể kết nối kho đích một thời gian.
- Phải rebuild lại từ dữ liệu nguồn sau khi mất projection.

Kết quả mong đợi là consumer có cơ chế phát hiện và khôi phục; không tuyên bố bảo đảm “exactly once” nếu nền tảng không thực sự cung cấp ngữ nghĩa đó ở cấp nghiệp vụ.

### Đối soát trong vận hành

Những chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số bản ghi sai tổng | Cho biết mức lệch giữa dữ liệu nguồn và dẫn xuất |
| Tuổi bản cập nhật gần nhất | Phát hiện projection/cache không còn mới |
| Event lag / backlog | Theo dõi tốc độ đồng bộ bất đồng bộ |
| Duplicate event / failed event | Phát hiện retry và lỗi xử lý |
| p95/p99 đọc và ghi | Đo lợi ích và giá phải trả sau phi chuẩn hóa |
| Lock wait, deadlock, transaction duration | Phát hiện tranh chấp khi cập nhật tổng |
| Kích thước bảng/index/WAL | Đo write amplification và chi phí lưu trữ |

Không nên chỉ giám sát tốc độ đọc; dữ liệu sai mà truy vấn nhanh không phải thành công.

## 14. Khung quyết định trước khi chấp nhận phi chuẩn hóa

Có thể sử dụng các câu hỏi sau để thẩm định một đề xuất:

| Câu hỏi | Câu trả lời phải có |
| --- | --- |
| Đường truy cập nào đang chậm? | API/truy vấn, dữ liệu, p95/p99, tải, kế hoạch thực thi |
| Đã thử tối ưu mô hình hiện tại chưa? | Index, phân trang, giảm N+1, projection và đo lại |
| Giá trị sao chép là gì? | Danh sách trường/công thức tổng hợp, kiểu, đơn vị |
| Nguồn sự thật ở đâu? | Bảng hoặc event stream có trách nhiệm định nghĩa giá trị |
| Khi nguồn thay đổi, ai cập nhật bản sao? | Service transaction, trigger, materialized refresh hoặc consumer |
| Được phép trễ bao lâu? | Phân biệt nhất quán tức thời và eventual consistency; SLO freshness |
| Có bao nhiêu đường ghi? | API, batch, importer, job, công cụ quản trị |
| Retry và concurrent update xử lý thế nào? | Khóa, version, idempotency và kiểm tra trùng |
| Đối soát và rebuild thế nào? | Truy vấn so sánh, backfill, công cụ phục hồi, dữ liệu lịch sử |
| Rủi ro tăng là gì? | Dung lượng, lock, CPU, bảo mật, backup, migration |
| Tiêu chí chấp nhận thay đổi? | SLO đọc/ghi đạt và bất biến dữ liệu được chứng minh |

**Quy trình hợp lý:** nêu nhu cầu truy cập → đo hiện trạng → tối ưu truy vấn/index → thử phi chuẩn hóa trên một phạm vi kiểm soát → xác minh độ đúng → đo lại dưới tải thật → theo dõi và có cách phục hồi.

Nếu không thể xác định một đường đồng bộ đáng tin, không có cách đối soát hoặc không biết dữ liệu có thể trễ bao lâu, quyết định phi chuẩn hóa chưa đủ cơ sở để đưa vào sản xuất.

## 15. Các nhầm lẫn thường gặp

**“Phi chuẩn hóa luôn nhanh hơn chuẩn hóa.”** Không. Nó có thể giảm chi phí đọc nhưng tăng ghi, lock, index và công việc vận hành; lợi ích phụ thuộc workload.

**“JOIN chậm nên phải sao chép mọi trường vào một bảng.”** Không. Trước tiên cần kiểm tra điều kiện lọc, chỉ mục, phân trang và query planner.

**“Đã có transaction thì các bản sao ở hai database tự đồng bộ.”** Không. Transaction cục bộ không mặc nhiên bao trùm các kho độc lập; cần outbox, consumer, idempotency và đối soát khi chọn cập nhật bất đồng bộ.

**“Trường tính toán chỉ cần cập nhật lúc INSERT.”** Sai. Còn sửa, xóa, rollback, nhập dữ liệu, thay nghiệp vụ và xử lý retry.

**“Cột tổng `NOT NULL` bảo đảm tổng đúng.”** Sai. Nó chỉ chặn `NULL`; không chứng minh sự bằng nhau với dữ liệu nguồn ở bảng khác.

**“Giá sản phẩm trong dòng đơn luôn phải theo giá hiện tại.”** Không. Giá tại thời điểm bán có thể là snapshot nghiệp vụ bắt buộc phải giữ, khác với bản sao của giá hiện hành.

**“Mỗi event chỉ đến một lần.”** Không được mặc định. Nhiều hệ messaging có thể gửi lặp hoặc thay đổi thứ tự; read model cần thiết kế đúng.

**“Đã lưu projection nên không cần nguồn gốc.”** Sai. Không có nguồn sự thật và cách tái dựng, lỗi đồng bộ hoặc thay schema sẽ rất khó khắc phục.

**“Cập nhật `items_total = :newValue` từ một giá trị đọc trước luôn an toàn.”** Không. Hai request đồng thời có thể ghi đè kết quả của nhau; cần thiết kế khóa, điều kiện/version hoặc cộng delta trong transaction.

## 16. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** Bảng `orders` chỉ có khóa đơn; `order_lines` có nhiều dòng. API liệt kê 20 đơn phải tính `SUM` cho 20 đơn. Có nên lập tức thêm cột `items_total`?

**Đáp án:** Chưa. Trước tiên cần đo bottleneck, phân trang đúng, kiểm tra index trên `order_lines.order_id` và loại bỏ N+1. Chỉ cân nhắc thêm bản sao khi có lợi ích rõ và cơ chế giữ tổng đúng.

**Câu 2.** Đơn 42 có tổng 300.000, một request thêm dòng 60.000; request khác thêm dòng 40.000. Nếu cả hai đọc 300.000 về Java rồi lần lượt ghi 360.000 và 340.000, lỗi gì xảy ra?

**Đáp án:** Lost update; tổng có thể là 340.000 thay vì 400.000. Cần cập nhật delta có kiểm soát trong database/transaction hoặc chiến lược version/lock thích hợp.

**Câu 3.** Một đơn có `items_total = 360.000`, nhưng tổng tính từ các dòng là 300.000. Đâu là dữ liệu có thẩm quyền?

**Đáp án:** Phải theo hợp đồng đã chốt. Trong ví dụ bài học, `order_lines` là nguồn sự thật; `items_total` là dữ liệu dẫn xuất cần đối soát và sửa. Không tự chọn giá trị 360.000 vì nó đọc nhanh hơn.

**Câu 4.** Một dịch vụ ghi đơn vào PostgreSQL, worker đồng bộ sang search index sau 2 giây. Trang tìm kiếm trả dữ liệu cũ trong khoảng đó có nhất thiết là lỗi không?

**Đáp án:** Phụ thuộc SLO freshness và hợp đồng nghiệp vụ. Nếu hệ thống công bố eventual consistency với mức trễ phù hợp, đây có thể là hành vi dự kiến. Nếu trang yêu cầu read-after-write ngay lập tức, phải chọn cách đọc/đồng bộ khác.

**Câu 5.** Một consumer nhận `OrderLineAdded(+60.000)` hai lần. Nên làm gì để tránh tổng projection tăng 120.000?

**Đáp án:** Xử lý event idempotent, chẳng hạn lưu `event_id` đã xử lý bằng unique constraint trong cùng transaction cập nhật projection; kết hợp kiểm tra thứ tự/version và cơ chế tái dựng khi cần.

**Câu 6.** Tại sao áp `DEFAULT 0` cho cột tổng trên bảng có dữ liệu cũ chưa chứng minh migration đã hoàn tất?

**Đáp án:** Đơn cũ có dòng hàng không có tổng bằng 0. Cần backfill từ nguồn, đối soát, bảo vệ race với ghi đồng thời và chỉ chuyển đường đọc sau khi kết quả đạt.

**Bài tập A — xác định nhu cầu:** Thiết kế một trang “10 sản phẩm bán chạy nhất tuần” có dữ liệu lớn. Hãy viết truy vấn chuẩn hóa trước, kiểm tra index và xác định khi nào nên duy trì bảng tổng hợp theo ngày. Nêu độ trễ dữ liệu cho phép, khóa tổng hợp và cách xử lý đơn hàng hủy.

**Bài tập B — tính delta:** Một dòng có `quantity = 3`, `unit_price = 40.000`. Người dùng sửa thành `quantity = 5`, `unit_price = 38.000`. Tính delta của `items_total`, đề xuất SQL/transaction bảo đảm dòng và tổng đổi cùng nhau.

**Gợi ý:** Giá trị cũ `120.000`, mới `190.000`, delta `+70.000`. Nếu giữ giá trị cũ không được bảo vệ bằng khóa hoặc version, giao dịch khác có thể đã sửa dòng trước khi áp delta.

**Bài tập C — migration đang có tải:** Bảng `orders` có 20 triệu hàng, nhiều request tạo dòng đơn hàng mỗi phút. Thiết kế kế hoạch thêm `items_total` theo các bước mở rộng schema, dual-write/trigger, backfill theo lô, đối soát, chốt ràng buộc, chuyển đọc và rollback. Nêu rõ cách tránh job backfill ghi đè dữ liệu mới.

**Bài tập D — read model tách kho:** Dùng outbox để tạo một bảng tìm kiếm đơn hàng trong kho khác. Hãy thiết kế event ID, version theo đơn, consumer chống lặp, theo dõi lag và quy trình rebuild sau khi cache/index bị xóa.

Trong thiết kế persistence cho Java, **phi chuẩn hóa có chủ đích** là quyết định lưu thêm một biểu diễn để phục vụ truy cập đã được xác định và đo lường. Giá trị của nó chỉ bền vững khi nhóm giữ rõ **nguồn sự thật**, **bất biến**, **đường đồng bộ**, **mức trễ cho phép**, **cách đối soát và khả năng phục hồi**. Khi những điều này được thiết kế cùng truy vấn, chỉ mục và giao dịch, hệ thống có thể đạt hiệu năng tốt hơn mà vẫn bảo vệ tính đúng đắn của dữ liệu.
