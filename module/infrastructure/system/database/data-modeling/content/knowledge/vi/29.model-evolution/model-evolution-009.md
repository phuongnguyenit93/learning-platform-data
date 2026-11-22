# Đồng bộ thay đổi giữa mô hình Java, lưu trữ, sự kiện và báo cáo

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định tác động của **một thay đổi nghiệp vụ** lên đồng thời mô hình miền Java, schema lưu trữ, integration event/API và mô hình báo cáo.
- Phân biệt **tương thích về cấu trúc** với **tương thích về ngữ nghĩa**, nhất là khi thêm field, đổi cách tính tiền, đặt lại tên trạng thái hoặc thay grain.
- Thiết kế lộ trình **expand → backfill/migrate → switch → contract**, có khả năng chạy đồng thời phiên bản ứng dụng cũ và mới trong một khoảng triển khai.
- Bảo vệ bất biến nghiệp vụ bằng Java, CHECK/FK, transaction, optimistic locking và kiểm tra đối soát khi schema đang được nâng cấp.
- Tiến hóa integration event theo phiên bản, giữ đúng ý nghĩa của sự kiện đã commit, tính idempotency, thứ tự, khả năng replay và cách nâng cấp consumer.
- Tiến hóa dữ kiện phân tích (*fact*), dimension và metric mà không đánh đồng **giá trị bán**, **số tiền phải trả**, **tiền đã thu** và **doanh thu kế toán**.
- Lập ma trận tương thích, cổng chất lượng, quan sát vận hành, chiến lược rollback/roll-forward và quy trình xử lý dữ liệu cũ.
- So sánh điểm khác biệt khi áp dụng trên cơ sở dữ liệu quan hệ, document, đồ thị hoặc kho phân tích.

Trong **DATABASE_DATA_MODELING**, nhiệm vụ không chỉ là chuyển yêu cầu thành thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý có thể kiểm chứng. Một mô hình tốt còn phải **tiến hóa được khi quy tắc nghiệp vụ thay đổi** mà không làm sai những bản ghi đã lưu, sự kiện đã công bố hoặc báo cáo đã phát hành. Chương **Tiến hóa mô hình** nhìn thay đổi như một quá trình trải qua nhiều biểu diễn dữ liệu, chứ không phải một lần sửa class và chạy câu ALTER TABLE.

## 1. Vì sao bốn lớp phải tiến hóa cùng một ý nghĩa?

Một thay đổi có thể được nhìn ở bốn lớp:

| Lớp | Câu hỏi khi thay đổi | Điều dễ hỏng nếu bỏ sót |
| --- | --- | --- |
| **Mô hình Java/miền** | Bất biến và hành vi nào thay đổi? | Ứng dụng tính tổng sai, cho phép state không hợp lệ |
| **Lưu trữ** | Dòng cũ được biểu diễn thế nào, ràng buộc và chỉ mục còn đúng không? | Backfill thiếu, dữ liệu mới đọc từ phiên bản cũ lỗi |
| **Sự kiện/hợp đồng** | Bên nhận đang hiểu field, trạng thái và đơn vị ra sao? | Consumer phiên bản cũ hiểu sai dù JSON vẫn parse được |
| **Báo cáo/phân tích** | Grain, metric, lịch sử và cách xử lý dữ liệu cũ có đổi không? | Tổng doanh số đúng về số học nhưng sai ý nghĩa |

Các lớp không cần chung một cấu trúc. Một aggregate Java có thể chứa value object Money; PostgreSQL lưu BIGINT VND; message trao đổi công bố chuỗi số tiền và currency; bảng fact lưu các measure riêng cho phép tổng hợp. **Điều phải đồng bộ là hợp đồng về ý nghĩa và tính đúng**, không phải ép chúng có cùng danh sách field.

~~~mermaid
flowchart TB
    R["Yêu cầu nghiệp vụ<br/>thêm chiết khấu dòng đơn"]
    R --> D["Domain Java<br/>quy tắc tổng tiền"]
    R --> S["Storage<br/>cột và constraint"]
    R --> E["Event/API contract<br/>version & semantics"]
    R --> M["Reporting model<br/>grain & metric"]
    D --> W["Transactional write"]
    S --> W
    W --> O["Outbox đã commit"]
    O --> E
    E --> P["Consumer / CDC / ETL"]
    P --> M
    M --> Q["Đối soát và kiểm chứng"]
    Q -.-> R
~~~

Nếu chỉ thay một chiều:

- Java bắt đầu áp chiết khấu nhưng storage chưa có cột: dữ liệu không thể phục hồi hoặc tổng tiền bị tính lại sai.
- Storage có cột mới nhưng ứng dụng cũ vẫn ghi: mặc định và dữ liệu do old writer tạo phải được hiểu đúng.
- Producer thay nghĩa trường event mà giữ version cũ: consumer có thể tính KPI sai mà không báo lỗi.
- Dashboard giữ công thức cũ: giảm giá bị báo như lỗi doanh thu hoặc doanh thu gộp biến thành doanh thu thuần.

## 2. Tình huống xuyên suốt: thêm chiết khấu theo từng đơn vị hàng

Giả sử hệ thống bán hàng ban đầu không có chiết khấu. Một Order gồm các OrderLine:

~~~text
Trước thay đổi:
OrderLine { lineNo, skuId, quantity, unitPriceVnd }
Order      { orderId, status, totalVnd }

totalVnd = SUM(quantity × unitPriceVnd)
~~~

Ở hợp đồng cũ, **totalVnd nghĩa là số tiền khách phải thanh toán cho các dòng hàng**, không phải một trường cố ý biểu diễn giá niêm yết trước giảm giá. Vì chưa có giảm giá nên tổng giá niêm yết và tổng phải trả bằng nhau.

Yêu cầu mới: cho phép **chiết khấu cố định trên từng đơn vị của một dòng**, không vượt đơn giá; tổng tiền phải trả giảm theo mức chiết khấu. Ví dụ:

| Dòng | Số lượng | Đơn giá | Giảm trên mỗi đơn vị | Giá trị gộp | Giảm tổng | Phải trả |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Áo thun | 2 | 100.000 | 10.000 | 200.000 | 20.000 | 180.000 |
| Mũ | 1 | 50.000 | 0 | 50.000 | 0 | 50.000 |
| **Tổng** | | | | **250.000** | **20.000** | **230.000** |

Các bất biến mới:

\[
0 \le d_i \le p_i,\qquad q_i>0,
\]

\[
\text{gross}=\sum_i q_ip_i,\quad
\text{discount}=\sum_i q_id_i,\quad
\text{payable}=\text{gross}-\text{discount}.
\]

Ở đây \(p_i\) là đơn giá VND, \(d_i\) là giảm giá trên đơn vị, \(q_i\) là số lượng. Không có giảm giá vượt giá dòng, không có tổng âm; mọi phép nhân/cộng phải kiểm soát tràn số. Bài **chưa** xét giảm giá cấp đơn, thuế, vận chuyển, ngoại tệ, voucher nhiều nguồn hay hoàn tiền; nếu nghiệp vụ mở rộng, cần mô hình chính sách/phân bổ tiền đầy đủ hơn.

### Hợp đồng ngữ nghĩa không đổi của totalVnd

Quyết định quan trọng: trường **totalVnd cũ tiếp tục mang nghĩa số tiền phải thanh toán**. Với đơn cũ discount=0, totalVnd=gross=payable. Với đơn mới có giảm giá, totalVnd=payable. Nếu consumer cũ đã được cam kết totalVnd là số tiền phải thanh toán, giữ nghĩa ấy cho phép tương thích.

Nếu hợp đồng cũ đã định nghĩa totalVnd là **giá trị trước giảm giá**, thì không thể âm thầm đổi nó thành payable mà vẫn coi là backward compatible. Khi ấy phải giữ nguyên nghĩa cũ hoặc ban hành contract/field mới và chuyển consumer có kiểm soát. **Cùng tên và cùng kiểu dữ liệu không chứng minh cùng ý nghĩa.**

## 3. Lập bản đồ tác động trước khi sửa code

Một thay đổi đơn giản ở UI có thể lan tới:

| Thành phần | Hiện tại | Sau thay đổi | Quyết định cần ghi rõ |
| --- | --- | --- | --- |
| Java OrderLine | quantity, unitPriceVnd | thêm discountPerUnitVnd | Điều kiện 0 ≤ discount ≤ price |
| Java Order | totalVnd() | gross(), discount(), payable() | totalVnd cũ là payable |
| SQL order_line | quantity, unit_price_vnd | thêm discount_per_unit_vnd | Default/backfill đơn cũ = 0 |
| SQL order_header | total_vnd | thêm gross_total_vnd, discount_total_vnd | Giữ total_vnd = payable |
| API response | totalVnd | thêm breakdown tùy chọn | Client cũ không bị buộc đọc field mới |
| Integration event | OrderPaid v1: totalVnd | OrderPaid v2: gross/discount/payable | Version, consumer migration |
| Analytics fact | paid_line_amount_vnd | gross/discount/net_paid_vnd | Cùng grain dòng bán, không nhân bản |
| KPI dashboard | tổng đã thanh toán | phân biệt gross, discount, payable | Đổi nhãn và chủ metric |
| ETL/CDC | đọc giá và số lượng | đọc discount + version | Retry, late data, backfill |
| Monitoring | thiếu kiểm tra giảm giá | đối soát gross−discount=payable | Ngưỡng và cảnh báo |

Ngoài cột mới, cần kiểm tra các **đường ghi**: web checkout, ứng dụng mobile, batch nhập đơn, tác vụ sửa đơn, admin, message listener và tool quản trị. Nếu một old writer vẫn tính lại total từ quantity × unitPrice rồi ghi đè sau khi new writer đã áp giảm giá, dữ liệu sẽ sai dù câu ALTER TABLE đã thành công.

### Ma trận tương thích qua giai đoạn triển khai

| Thành phần | Schema cũ | Schema mở rộng, chưa bật giảm giá | Đã có dữ liệu giảm giá |
| --- | --- | --- | --- |
| **Old application** | Hoạt động | Có thể tiếp tục nếu cột mới nullable/default và không thay nghĩa field cũ | **Không an toàn** nếu old writer sửa đơn giảm giá bằng logic cũ |
| **New application** | Có thể lỗi khi truy vấn cột chưa tồn tại | Hoạt động sau deploy theo thứ tự | Hoạt động với bất biến mới |
| **Old event consumer** | Đọc v1 | Đọc v1 theo hợp đồng | Chỉ an toàn nếu totalVnd vẫn có nghĩa đã cam kết |
| **New event consumer** | Chưa đủ thông tin breakdown | Nhận v2 hoặc adapter có default hợp lệ | Xử lý breakdown với version đúng |
| **Old report** | Tổng = gross = payable | Vẫn đúng khi discount=0 | Cần xem lại **nhãn và công thức**, không tự gọi gross |

Đường triển khai an toàn thường là **mở rộng storage trước**, nâng cấp tất cả writer quan trọng để hiểu cột mới, đối soát, rồi **mới bật tính năng giảm giá**. Đây là **feature gate theo dữ liệu**, không chỉ cờ UI: người dùng không nhìn thấy nút giảm giá chưa đủ bảo đảm batch hoặc API khác không ghi giảm giá.

## 4. Mô hình Java mới: bất biến thuộc về hành vi miền

Đoạn Java 17 dưới đây diễn đạt phép tính và bảo vệ trạng thái. Nó không chứa SQL, REST hay logic Kafka.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderLine(
        int lineNo, UUID skuId, int quantity,
        long unitPriceVnd, long discountPerUnitVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0
                || unitPriceVnd < 0
                || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long grossVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    long discountVnd() {
        return Math.multiplyExact(
            (long) quantity, discountPerUnitVnd);
    }

    long payableVnd() {
        return Math.subtractExact(grossVnd(), discountVnd());
    }
}

record OrderAmounts(long grossVnd, long discountVnd, long payableVnd) {
    OrderAmounts {
        if (grossVnd < 0 || discountVnd < 0
                || discountVnd > grossVnd
                || payableVnd != grossVnd - discountVnd) {
            throw new IllegalArgumentException("Invalid amounts");
        }
    }
}

enum OrderState { DRAFT, PAID, CANCELLED }

record PaymentEvidence(UUID captureId, long capturedVnd, Instant capturedAt) {
    PaymentEvidence {
        Objects.requireNonNull(captureId);
        Objects.requireNonNull(capturedAt);
        if (capturedVnd < 0) throw new IllegalArgumentException("amount");
    }
}

record OrderPaid(
        UUID eventId, UUID orderId, long aggregateVersion,
        Instant occurredAt, OrderAmounts amounts, UUID captureId) {}

final class SalesOrder {
    private final UUID orderId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderState state = OrderState.DRAFT;
    private long version;

    SalesOrder(UUID orderId) {
        this.orderId = Objects.requireNonNull(orderId);
    }

    void addLine(OrderLine line) {
        if (state != OrderState.DRAFT) {
            throw new IllegalStateException("Order not editable");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("Duplicate line number");
        }
        // Tính thử tổng mới trước khi thay đổi trạng thái.
        Math.addExact(amounts().grossVnd(), line.grossVnd());
        Math.addExact(amounts().discountVnd(), line.discountVnd());
        Math.addExact(amounts().payableVnd(), line.payableVnd());
        lines.add(line);
        version++;
    }

    OrderAmounts amounts() {
        long gross = 0, discount = 0;
        for (OrderLine line : lines) {
            gross = Math.addExact(gross, line.grossVnd());
            discount = Math.addExact(discount, line.discountVnd());
        }
        return new OrderAmounts(
            gross, discount, Math.subtractExact(gross, discount));
    }

    OrderPaid recordCapturedPayment(UUID eventId, PaymentEvidence evidence) {
        if (state != OrderState.DRAFT || lines.isEmpty()) {
            throw new IllegalStateException("Order cannot be paid");
        }
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(evidence);
        OrderAmounts total = amounts();
        if (evidence.capturedVnd() != total.payableVnd()) {
            throw new IllegalStateException("Captured amount mismatch");
        }
        state = OrderState.PAID;
        version++;
        return new OrderPaid(
            eventId, orderId, version, evidence.capturedAt(),
            total, evidence.captureId());
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    UUID id() { return orderId; }
    OrderState state() { return state; }
    long version() { return version; }
}
~~~

Ví dụ Order sử dụng **bằng chứng PaymentCaptured do Payment context có thẩm quyền cung cấp**; không tin một capturedVnd bất kỳ do client tự gửi. Hệ thống thực cần xác thực nguồn, quyền tenant, chống trùng captureId, liên kết payment/order và xử lý timeout. Phương thức trả OrderPaid mới chỉ tạo **sự kiện miền trong bộ nhớ**; integration event phải được ghi sau khi transaction nghiệp vụ phù hợp được commit.

### Trách nhiệm của Java khác nhiệm vụ của schema

- Constructor/value object bảo vệ điều kiện ở **một dòng**.
- Aggregate tính tổng và quyết định chuyển trạng thái; không cho caller tự set total.
- Repository phải phục hồi state đã lưu, **không gọi lại addLine hoặc recordCapturedPayment** để giả lập lịch sử, vì điều đó có thể tăng version và phát tác động phụ.
- Dùng Math.multiplyExact/addExact/subtractExact để phát hiện tràn số nguyên. Nếu business amount vượt phạm vi long, cần BigDecimal/NUMERIC với đơn vị và precision được thống nhất.
- Application service giữ **originalVersion** khi load, dùng optimistic concurrency ở DB, và ánh xạ OrderPaid thành integration contract.

Phép tính đúng trong Java không thay thế việc database kiểm tra khi có **nhiều request đồng thời hoặc đường ghi SQL khác**.

## 5. Mô hình cũ và mục tiêu lưu trữ mới

Giả sử nguồn OLTP dùng PostgreSQL; schema cũ tối giản:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED')),
    total_vnd BIGINT NOT NULL CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    paid_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);
~~~

Yêu cầu mới **không buộc đổi ngay tên total_vnd**. Giữ nó là **số phải trả** để ứng dụng cũ vẫn có thể đọc theo đúng hợp đồng. Bổ sung:

- order_line.discount_per_unit_vnd, mặc định 0 cho dữ liệu cũ.
- order_header.gross_total_vnd và discount_total_vnd để phục vụ đối soát/truy vấn nóng.
- Kiểm tra tổng: gross−discount = total_vnd.
- Khi PAID, giá và giảm giá đã chốt phải bất biến theo chính sách; sửa sai dùng adjustment/correction được kiểm soát, không sửa ngầm lịch sử.

Nên đặt **tên đo lường thể hiện nghĩa**: grossTotalVnd, discountTotalVnd, payableTotalVnd. Nếu giữ tên totalVnd vì tương thích, tài liệu và mapper phải quy định **totalVnd = payableTotalVnd**, không để mỗi module tự diễn giải.

## 6. Expand: bổ sung schema theo cách chịu được phiên bản cũ

Một migration giai đoạn **EXPAND** minh họa:

~~~sql
-- Chạy dưới cơ chế migration có quản lý phiên bản/schema.
-- Kiểm tra locks, quyền và khả năng deploy thực tế trước production.

ALTER TABLE sales.order_line
    ADD COLUMN discount_per_unit_vnd BIGINT DEFAULT 0;

ALTER TABLE sales.order_header
    ADD COLUMN gross_total_vnd BIGINT,
    ADD COLUMN discount_total_vnd BIGINT;

-- CHECK NOT VALID tránh quét toàn bộ dữ liệu cũ khi tạo constraint.
-- PostgreSQL vẫn kiểm tra hàng INSERT/UPDATE mới.
ALTER TABLE sales.order_line
    ADD CONSTRAINT ck_discount_per_unit
    CHECK (
        discount_per_unit_vnd IS NOT NULL
        AND discount_per_unit_vnd >= 0
        AND discount_per_unit_vnd <= unit_price_vnd
    ) NOT VALID;

-- Hai cột tổng còn nullable trong giai đoạn chuyển tiếp.
ALTER TABLE sales.order_header
    ADD CONSTRAINT ck_order_amount_breakdown
    CHECK (
        (gross_total_vnd IS NULL AND discount_total_vnd IS NULL)
        OR
        (
            gross_total_vnd IS NOT NULL
            AND discount_total_vnd IS NOT NULL
            AND gross_total_vnd >= 0
            AND discount_total_vnd >= 0
            AND discount_total_vnd <= gross_total_vnd
            AND gross_total_vnd - discount_total_vnd = total_vnd
        )
    ) NOT VALID;
~~~

**Tại sao không đặt NOT NULL ngay cho mọi cột mới?** Những hàng header cũ chưa được backfill sẽ thiếu gross/discount; việc ép quá sớm có thể chặn deploy. Trên order_line, DEFAULT 0 làm dữ liệu cũ có ý nghĩa "không giảm giá" và cho old writer INSERT không nêu cột mới vẫn tạo dòng hợp lệ; tuy nhiên app nào cố INSERT NULL vẫn bị CHECK chặn.

**Chú ý PostgreSQL:** NOT VALID trên CHECK không kiểm tra tất cả hàng cũ lúc tạo, nhưng **các hàng mới/được cập nhật phải thỏa CHECK**. Việc thêm cột/default và VALIDATE CONSTRAINT có đặc điểm lock/phiên bản engine riêng, cần thử trên bản PostgreSQL và lượng dữ liệu thực, không mặc định mọi ALTER TABLE là zero-downtime.

Ở giai đoạn expand, **feature discount vẫn tắt**. Old writer chưa biết discount vẫn có thể ghi với discount=0; chỉ khi các writer, reader và pipeline cần thiết đã được nâng cấp mới bật ghi giảm giá lớn hơn 0. Cần kiểm tra code cũ có dùng INSERT không liệt kê cột, SELECT * rồi map theo vị trí hoặc serializer tự động không; các thói quen đó có thể phá khả năng tương thích dù cột mới nullable.

## 7. Backfill: đưa dữ liệu cũ vào ngữ nghĩa mới

Một quy tắc then chốt: **không có chiết khấu trước khi tính năng tồn tại** không đồng nghĩa mọi cột mới được để NULL mãi. Đơn hàng cũ hợp lệ có:

\[
\text{discount}=0,\quad
\text{gross}=\text{total cũ},\quad
\text{payable}=\text{total cũ}.
\]

Mọi phép backfill phải có thể **chạy lại an toàn**, có checkpoint, đo tiến độ và không ghi đè thay đổi hợp lệ của ứng dụng mới.

### 7.1. Backfill đơn đã PAID và bất biến

Giả định theo hợp đồng nghiệp vụ, những Order **PAID** trước khi bật tính năng không bị sửa dòng hàng thông thường. Khi đó có thể tính lại gross từ OrderLine và discount=0. Ví dụ SQL cho một tập được xử lý có kiểm soát:

~~~sql
WITH line_sums AS (
    SELECT l.tenant_id, l.order_id,
           SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross,
           SUM(
               l.quantity::NUMERIC
               * COALESCE(l.discount_per_unit_vnd, 0)
           ) AS discount
    FROM sales.order_line AS l
    JOIN sales.order_header AS o
      ON o.tenant_id = l.tenant_id
     AND o.order_id = l.order_id
    WHERE o.status = 'PAID'
      AND o.gross_total_vnd IS NULL
      AND o.tenant_id = :tenant_id
    GROUP BY l.tenant_id, l.order_id
)
UPDATE sales.order_header AS o
SET gross_total_vnd = s.gross,
    discount_total_vnd = s.discount
FROM line_sums AS s
WHERE o.tenant_id = s.tenant_id
  AND o.order_id = s.order_id
  AND o.status = 'PAID'
  AND o.gross_total_vnd IS NULL
  AND s.gross - s.discount = o.total_vnd;
~~~

**Đây là minh họa logic, chưa phải một backfill production đầy đủ.** Lệnh cố ý **không sửa total_vnd** để che đi bất nhất dữ liệu nguồn. Nếu gross−discount khác total cũ, hàng không được cập nhật và phải nằm trong báo cáo sai khác. Nếu gross không nằm trong miền BIGINT, cần báo lỗi/điều tra thay vì cắt bớt; kiểu NUMERIC trong SUM giúp phát hiện tổng vượt phạm vi đích. Dữ liệu đã PAID chỉ an toàn để backfill theo cách này nếu thực sự **bất biến** trong giao thức ghi của nguồn.

Với hàng DRAFT hoặc các trạng thái còn sửa được, cần một chiến lược khác:

- mọi writer bắt đầu **khóa Order root** trước khi sửa dòng;
- backfill từng Order trong transaction, lấy đúng phiên bản/hàng con dưới cùng giao thức khóa;
- tránh đọc dòng cũ rồi cập nhật summary sau khi writer khác đã sửa;
- hoặc chốt một cửa sổ ngắn không cho ghi nếu sản phẩm và SLA chấp nhận.

Backfill ở quy mô lớn cần phân lô theo khóa ổn định (keyset/chunk), checkpoint, giới hạn lock/I/O, retry theo lỗi và số lượng hàng dự kiến. Không nên thực thi một UPDATE không giới hạn hàng chục triệu đơn trong giờ cao điểm rồi giả định sẽ không ảnh hưởng latency OLTP.

### 7.2. Câu SQL phát hiện chênh lệch giữa header và dòng

~~~sql
WITH sums AS (
    SELECT tenant_id, order_id,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC *
               COALESCE(discount_per_unit_vnd, 0)) AS discount
    FROM sales.order_line
    WHERE tenant_id = :tenant_id
    GROUP BY tenant_id, order_id
)
SELECT o.order_id, o.status, o.total_vnd,
       o.gross_total_vnd, o.discount_total_vnd,
       s.gross AS recomputed_gross,
       s.discount AS recomputed_discount,
       s.gross - s.discount AS recomputed_payable
FROM sales.order_header AS o
LEFT JOIN sums AS s
  ON s.tenant_id = o.tenant_id AND s.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
  AND (
      s.order_id IS NULL
      OR o.gross_total_vnd IS NULL
      OR o.discount_total_vnd IS NULL
      OR o.gross_total_vnd IS DISTINCT FROM s.gross
      OR o.discount_total_vnd IS DISTINCT FROM s.discount
      OR o.total_vnd IS DISTINCT FROM (s.gross - s.discount)
  );
~~~

Query này **giả định Order có ít nhất một dòng**, kể cả DRAFT. Nếu nghiệp vụ cho phép DRAFT tạm rỗng, cần phân loại riêng, không coi tất cả hàng DRAFT rỗng là lỗi. Nó cũng có thể tốn tài nguyên: chạy trên read replica/snapshot ổn định hoặc theo từng lô và cùng cutoff với hệ thống có thẩm quyền; không lấy một truy vấn không nhất quán trong lúc nhiều writer đang thay đổi rồi coi tất cả sai khác là lỗi thật.

### 7.3. Siết ràng buộc sau khi dữ liệu và writer sẵn sàng

~~~sql
-- Chỉ sau khi kết quả backfill/đối soát đã PASS.
ALTER TABLE sales.order_line
    VALIDATE CONSTRAINT ck_discount_per_unit;

ALTER TABLE sales.order_header
    VALIDATE CONSTRAINT ck_order_amount_breakdown;

-- Bước tiếp theo chỉ khi TẤT CẢ header, kể cả DRAFT, đã có breakdown.
ALTER TABLE sales.order_header
    ADD CONSTRAINT ck_amount_breakdown_present
    CHECK (
        gross_total_vnd IS NOT NULL
        AND discount_total_vnd IS NOT NULL
    ) NOT VALID;

-- Không chạy ngay nếu old writer còn tạo header thiếu breakdown.
ALTER TABLE sales.order_header
    VALIDATE CONSTRAINT ck_amount_breakdown_present;

-- Có thể cân nhắc ALTER COLUMN SET NOT NULL ở bước CONTRACT riêng,
-- sau khi kiểm chứng cách khóa và đặc điểm engine/phiên bản đang dùng.
~~~

**Thứ tự là một phần của tính đúng.** VALIDATE thành công không chứng minh old writer sẽ không tiếp tục ghi thiếu cột nếu constraint vừa đưa vào vẫn cho phép NULL. Muốn đóng khả năng ghi NULL cần bảo đảm **mọi writer đã hỗ trợ** hoặc có cơ chế default/trigger được thử tương thích, rồi mới enforce. Với cột mới không có nghĩa mặc định hợp lý cho mọi dữ liệu, không được tự điền 0 chỉ để migration xanh.

## 8. Đồng bộ đường ghi Java ↔ SQL khi chạy nhiều phiên bản

Một old writer không biết chiết khấu có thể đọc Order rồi ghi lại toàn bộ OrderLine với discount mặc định 0. Sau khi có đơn giảm giá, đây là **lost business meaning** chứ không chỉ lost update. Vì vậy không cho writer đó sửa những đơn được tạo/đổi theo mô hình mới.

Chiến lược thường dùng:

1. Deploy schema mở rộng.
2. Deploy Java mới có mapper đọc được dữ liệu cũ: NULL từ giai đoạn chuyển tiếp được hiểu là 0 **chỉ khi có bằng chứng hợp đồng legacy rằng không tồn tại discount**.
3. Deploy toàn bộ **command writer**, batch, admin, import và service liên quan.
4. Bật phép ghi discount>0 sau khi xác nhận không còn đường ghi cũ có thể làm hỏng dữ liệu.
5. Với các đơn đã giảm giá, dùng một giao thức version/lock chung cho mọi thay đổi.

**Không sử dụng dual-write tùy tiện**: cùng lúc ghi Order vào hai schema/database rồi hy vọng hai bên giống nhau. Nếu một lần ghi thành công, lần kia timeout, sẽ có hai nguồn sự thật cạnh tranh. Khi bắt buộc chuyển dữ liệu, phải xác định một nguồn có thẩm quyền và hướng cập nhật; CDC/outbox, checkpoint, replay và đối soát thường dễ kiểm soát hơn một request tự ghi hai kho độc lập.

### Giao dịch thanh toán và outbox cùng commit

Sau khi Payment context cung cấp bằng chứng capture hợp lệ, Sales chuyển Order sang PAID và ghi integration event trong **transaction cục bộ**:

~~~sql
CREATE TABLE IF NOT EXISTS sales.order_outbox (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    order_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);

BEGIN;

UPDATE sales.order_header
SET status = 'PAID',
    paid_at = :captured_at,
    total_vnd = :payable_vnd,
    gross_total_vnd = :gross_vnd,
    discount_total_vnd = :discount_vnd,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
  AND :gross_vnd >= :discount_vnd
  AND :payable_vnd = :gross_vnd - :discount_vnd
RETURNING version;

-- Nếu không trả đúng 1 hàng: ROLLBACK, không ghi event.
-- Các OrderLine phải đúng với gross/discount và được bảo vệ bằng
-- cùng transaction cùng giao thức khóa root.

INSERT INTO sales.order_outbox (
    event_id, tenant_id, order_id, order_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-paid', 2, :captured_at,
    jsonb_build_object(
        'orderId', :order_id,
        'grossVnd', :gross_vnd_text,
        'discountVnd', :discount_vnd_text,
        'payableVnd', :payable_vnd_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~

Đoạn transaction là minh họa cho **một lần chuyển DRAFT → PAID** trong hệ thống rút gọn. Nó giả định line đã được lưu đúng và toàn bộ đường ghi line tôn trọng root lock/version. Nếu cần lưu line thay đổi cùng lệnh, thực hiện trong chính transaction. Phải kiểm tra row count và điều kiện trước COMMIT ở application; SQL không tự ROLLBACK chỉ vì UPDATE trả 0 hàng.

Vì **Payment** có nguồn có thẩm quyền riêng, Sales phải đối chiếu captureId, amount, orderId, tenant và idempotency của kết quả thanh toán. Transaction ở Sales không có nghĩa đã ghi cùng một transaction ACID với cổng thanh toán.

**Một thay đổi về domain và storage phải thống nhất trong cùng commit**, còn sự công bố ra broker có thể diễn ra sau nhờ outbox. Relay có thể phát lại vì crash giữa publish và đánh dấu sent, nên consumer cần dedup. Khi retry lệnh chuyển PAID, eventId của sự thật đã commit không được tạo mới rồi công bố như một lần thanh toán khác.

## 9. Hợp đồng sự kiện: từ OrderPaidV1 sang OrderPaidV2

Hợp đồng cũ đã công bố:

~~~json
{
  "eventId": "2ef6d3b4-809e-4a44-95fa-f2d1c1e15470",
  "eventType": "sales.order-paid",
  "schemaVersion": 1,
  "tenantId": "517da76b-b642-4842-84db-17f4b54c9203",
  "aggregateId": "038b3e41-894a-410e-899e-25fb5e22cf30",
  "aggregateVersion": 6,
  "occurredAt": "2026-11-01T09:00:00Z",
  "payload": {
    "orderId": "038b3e41-894a-410e-899e-25fb5e22cf30",
    "totalVnd": "250000"
  }
}
~~~

**Ngữ nghĩa đã cam kết:** totalVnd là **số phải trả/đã được ghi nhận thanh toán cho hàng của đơn**, không phải giá trị trước chiết khấu. Đơn này chưa có giảm giá nên payable=250.000.

Hợp đồng mới:

~~~json
{
  "eventId": "448ce62a-0e46-41ab-b88b-979fd4908548",
  "eventType": "sales.order-paid",
  "schemaVersion": 2,
  "tenantId": "517da76b-b642-4842-84db-17f4b54c9203",
  "aggregateId": "b1c06314-3994-4396-a43d-6785a177edfa",
  "aggregateVersion": 9,
  "occurredAt": "2026-11-22T09:00:00Z",
  "payload": {
    "orderId": "b1c06314-3994-4396-a43d-6785a177edfa",
    "grossVnd": "250000",
    "discountVnd": "20000",
    "payableVnd": "230000",
    "currency": "VND"
  }
}
~~~

**Đây là hai sự kiện minh họa của hai Order khác nhau**, không phải phát lại cùng một eventId với hai payload khác nhau. schemaVersion biểu thị **hợp đồng payload**, aggregateVersion biểu thị **phiên bản state Order**. Chúng có thể thay đổi độc lập.

### Kế hoạch chuyển consumer

- **Consumer v1:** cần một contract còn có totalVnd với nghĩa payable. Nếu vẫn phục vụ, một adapter có thể chiếu event v2 về v1 bằng **totalVnd = payableVnd**, giữ đúng ngữ nghĩa đã cam kết.
- **Consumer v2:** dùng grossVnd, discountVnd, payableVnd để báo cáo hoặc xử lý cần breakdown; phải kiểm tra currency và tính nhất quán.
- **Consumer đang chuyển:** có thể đọc v1 và v2 qua adapter/upcaster có version, nhưng **không được tự suy ra gross=payable, discount=0 cho các giao dịch mới đã giảm giá** chỉ từ v1. Nếu cần breakdown, phải tra nguồn có thẩm quyền hoặc công bố unknown/thiếu dữ liệu.

Nếu publish **hai projection v1 và v2 cho cùng một sự thật** trong giai đoạn chuyển tiếp, phải xác định rõ topic/consumer nào nhận bản nào, có **logicalOccurrenceId** chung hoặc quy tắc dedup thích hợp, và tuyệt đối không để báo cáo đếm cả hai như hai lần OrderPaid. Cách dễ kiểm soát là chỉ có **một event canonical trong outbox**, còn lớp compatibility dịch sang kênh v1 cho các subscriber cụ thể cho tới khi họ nâng cấp.

### Compatibility không chỉ là thêm/xóa field

| Thay đổi event | Có thể tương thích không? | Lưu ý |
| --- | --- | --- |
| Thêm field optional với default có nghĩa rõ | Thường có | Consumer phải chấp nhận trường lạ |
| Đổi tên totalVnd thành payableVnd, xóa field cũ | Không với consumer v1 dùng field cũ | Version mới hoặc adapter |
| Đổi totalVnd từ payable thành gross nhưng giữ tên | **Không** | Lỗi ngữ nghĩa dù schema vẫn parse |
| Đổi VND nguyên thành đơn vị nghìn VND | **Không** | Tiền bị sai theo tỷ lệ |
| Thêm enum trạng thái mới | Tùy hợp đồng | Client/consumer cũ có thể dùng switch không xử lý |
| Thay eventId trên một lần broker redelivery | Không an toàn | Dedup thất bại, nhân tác động |
| Dùng aggregateVersion làm schemaVersion | Sai khái niệm | Mất khả năng version độc lập |

**Schema registry chỉ có thể bảo vệ một phần tương thích cấu trúc.** Một event giữ nguyên JSON nhưng đổi nghĩa "đã thanh toán" thành "đã ủy quyền thanh toán" là breaking change nghiệp vụ mà không công cụ schema nào tự phát hiện.

## 10. Replay, CDC, thứ tự và consumer idempotency

Khi consumer mới cần xây lại projection từ lịch sử, câu hỏi không chỉ là "còn message trong broker không?" mà còn là:

1. **Có giữ đủ event v1/v2 trong khoảng thời gian cần rebuild?**
2. **Consumer có adapter giải được từng phiên bản?**
3. **Dữ liệu v1 có đủ tạo gross/discount không, hay chỉ biết payable?**
4. **Nếu có correction/hoàn tiền, event nào đảo/điều chỉnh phép đo?**
5. **Replay có làm lặp email, charge hoặc các tác động ngoài không?**

Một consumer ứng dụng có thể bảo vệ với khóa:

~~~sql
CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE integration.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

-- Bắt đầu transaction cục bộ của consumer:
-- INSERT processed_event(...); nếu khóa đã tồn tại, coi đã xử lý.
-- Nếu mới, cập nhật projection / aggregate thuộc consumer trong
-- cùng transaction; ACK broker chỉ sau khi commit thành công.
~~~

Nếu bản v1 và v2 cùng diễn đạt một business occurrence nhưng mang **eventId khác nhau**, bảng này không tự ngăn double counting. Phải chọn đúng **logical occurrence ID** hoặc đảm bảo mỗi consumer chỉ theo một kênh canonical. Đối với tác động ngoài không chung transaction (gửi email, cổng thanh toán), còn cần idempotency riêng ở phía đích hoặc quy trình đối soát.

**CDC row change ≠ domain event**. Nếu CDC thấy một UPDATE chỉ dùng để backfill gross_total_vnd, đó không phải một lần trả tiền mới. Một pipeline đọc thay đổi vật lý phải phân biệt:

- chỉnh sửa schema/backfill;
- thay đổi trạng thái nghiệp vụ thật;
- sửa dữ liệu theo correction;
- lần gửi lại của cùng thay đổi.

Không lấy mọi UPDATE của order_header rồi phát OrderPaid hoặc tăng doanh số.

**Thứ tự:** aggregateVersion chỉ áp dụng cho một Order, và một version có thể được tăng vì thay đổi **không có event OrderPaid**. Consumer không được mặc định mọi version 1,2,3... đều là các sự kiện cùng một loại. Nếu cần xác định thứ tự, dùng sequence theo stream có thẩm quyền, hợp đồng snapshot và cơ chế phát hiện gap thích hợp; timestamp không tạo thứ tự toàn hệ thống.

## 11. Báo cáo: phát triển fact và metric đúng grain

Đường phân tích cần giữ rõ câu hỏi:

- **Gross goods value:** tổng quantity × unitPrice của các dòng đã đủ điều kiện ghi nhận.
- **Discount given:** tổng quantity × discountPerUnit.
- **Net paid goods value:** gross−discount của các dòng thuộc Order đã PAID theo hợp đồng.
- **Payment captured:** kết quả có thẩm quyền từ Payment, có thể khác thời điểm/đơn vị ghi nhận hàng.
- **Refund:** khoản hoàn thực tế, phải có fact/quy tắc riêng.
- **Accounting revenue:** có thể phụ thuộc giao hàng, nghĩa vụ thực hiện, thuế và quy tắc kế toán; không tự đồng nhất với một trong các số trên.

Giả sử mỗi Order PAID nghĩa là **toàn bộ giá trị hàng của đơn đã được capture đúng một lần**, chưa xét thuế/phí/hủy/hoàn. Ta dùng fact tại grain:

> **Một hàng = một OrderLine của một Order đã PAID**, với khóa (tenantId, orderId, lineNo), snapshot giá lúc bán, các measure gross/discount/net và paidAt.

Ví dụ bảng fact:

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL
        CHECK (discount_per_unit_vnd >= 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_paid_vnd BIGINT NOT NULL CHECK (net_paid_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_per_unit_vnd <= unit_price_vnd),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_paid_vnd)
);

CREATE INDEX fact_paid_line_by_date
    ON mart.fact_paid_order_line (tenant_id, paid_date, sku_id);
~~~

**Đây là schema đích minh họa**, không nhất thiết là ALTER trực tiếp cho warehouse đang có dữ liệu. Trong migration thật, cần expand fact/giữ view cũ, backfill lịch sử và chuyển BI dần. Nếu có partial capture hoặc nhiều lần ghi nhận cho một OrderLine, grain **một dòng đã PAID** có thể không còn phù hợp: khi đó cân nhắc fact theo **capture allocation** với ID riêng. Không mở thêm cột rồi giữ một khóa không đại diện đúng dữ kiện nữa.

### Đổi metric theo đúng ý nghĩa

~~~sql
SELECT paid_date,
       SUM(gross_vnd) AS gross_goods_vnd,
       SUM(discount_vnd) AS discount_given_vnd,
       SUM(net_paid_vnd) AS net_paid_goods_vnd,
       COUNT(DISTINCT order_id) AS paid_orders
FROM mart.fact_paid_order_line
WHERE tenant_id = :tenant_id
  AND paid_date >= DATE '2026-11-01'
  AND paid_date <  DATE '2026-12-01'
GROUP BY paid_date
ORDER BY paid_date;
~~~

**COUNT(DISTINCT order_id)** đếm số Order theo ngày trong phạm vi tenant; một Order có hai dòng chỉ là **một Order**, không phải hai. Nếu một Order có dòng thuộc nhiều ngày thanh toán, quy ước grain/mốc phải được xem lại. paid_date phải dùng **business timezone/cutoff thống nhất**, không lấy bừa ngày CDC ingest.

### Không đổi nhãn dashboard rồi coi là xong

Nếu báo cáo cũ ghi "Sales" nhưng thực chất đo **totalVnd = payable**, sau khi có discount phải quyết định:

- Giữ metric cũ theo nghĩa **net paid goods value** và đổi nhãn/tài liệu cho rõ.
- Tạo metric mới **gross goods value** từ snapshot đơn giá, không giả định gross=net sau khi bật giảm giá.
- Báo cáo chiết khấu = gross−net, và đối chiếu bằng tổng trên từng grain.
- Nếu cần **doanh thu kế toán**, kết nối đúng nguồn ghi nhận và quy tắc thuế/hoàn/giao hàng; không tự đổi tên trường net_paid thành revenue.

Đối với dữ liệu trước ngày có discount, có thể backfill discount=0 nếu chắc rằng **chính sách cũ thật sự không tồn tại chiết khấu**; nếu có voucher ngoài hệ thống không được phản ánh vào OrderLine, **điền 0 là sai sự thật**. Mức độ đầy đủ dữ liệu cũ cần được công bố trong metadata/quality flag.

## 12. Phối hợp tiến hóa fact, dimension và pipeline

Giả sử BI đang đọc bảng fact cũ có mỗi paid_amount_vnd. Một kế hoạch tương thích:

1. **Expand fact:** thêm gross_vnd, discount_vnd, net_paid_vnd dạng nullable; không phá query cũ.
2. **Xây transform v2:** lấy snapshot giá và giảm giá từ Sales hoặc OrderPaidV2 theo hợp đồng; khi payload thiếu breakdown, cần nguồn bổ sung hoặc đánh dấu chưa đủ.
3. **Backfill lịch sử:** ghi theo khóa (tenantId, orderId, lineNo), với sourceVersion, transformVersion và loadBatchId để có thể đối soát/tái xử lý.
4. **Đối chiếu:** tổng net của fact v2 phải bằng tổng đã thanh toán trong source theo cùng kỳ/định nghĩa. Gross−discount phải bằng net theo từng dòng và từng nhóm.
5. **Chạy song song dashboard:** so metric cũ và metric mới trên cùng cutoff; không kỳ vọng gross mới bằng net cũ sau khi bật giảm giá.
6. **Switch semantic layer:** đổi truy vấn dashboard theo field có nghĩa rõ; version metric và ghi ngày thay đổi.
7. **Contract:** xóa field fact cũ chỉ khi không còn job/BI dùng nó và có lộ trình khôi phục.

### Dữ liệu đến muộn và sửa hồi tố

Event OrderPaid có thể đến kho phân tích sau ngày thanh toán; phải phân loại theo **paidAt** đã định nghĩa, không theo lúc consumer nhận. Nếu nguồn sửa một khoản discount vì sự cố hoặc hoàn tiền, cần quy tắc:

- **Correction/restatement:** cập nhật fact đúng grain và những bảng tổng hợp phụ thuộc, phát hành metric version/cutoff mới.
- **Adjustment fact:** ghi bút toán điều chỉnh tách biệt, tránh vừa sửa số cũ vừa cộng điều chỉnh lần nữa.
- **Refund event/fact:** một dòng hoàn tiền có refundId và thời điểm riêng, không tự biến một OrderPaid thành hai lần bán.

Khi dùng SCD Type 2 cho SKU/category hoặc phân khúc, fact cần liên kết tới **phiên bản dimension tại thời điểm nghiệp vụ** hoặc lưu snapshot thích hợp. Việc đổi danh mục sau ngày bán không đồng nghĩa phải sửa mọi giao dịch cũ. Một migration giá trị tiền và một migration danh mục lịch sử là hai thay đổi ngữ nghĩa khác nhau, cần kiểm thử riêng.

### Rebuild không được nhân bản

Một backfill fact chạy lại phải **MERGE/UPSERT** theo khóa grain ổn định, không INSERT thêm bản sao rồi SUM cả hai. Nếu mỗi event replay tự tạo mới loadId rồi dùng loadId làm business key, sẽ tạo doanh số ảo. LoadBatchId chỉ phục vụ lineage, **không thay thế khóa nghiệp vụ của fact**.

## 13. Thứ tự triển khai: không buộc toàn hệ thống nâng cấp một lúc

Trong thực tế, có thể có nhiều replica ứng dụng, batch chạy lâu, consumer thuộc đội khác và dashboard được cache. Thay đổi chỉ an toàn khi **mỗi cặp phiên bản có thể gặp nhau trong thời gian triển khai** đã được xem xét.

~~~mermaid
flowchart TB
    A["1. Chốt hợp đồng ngữ nghĩa<br/>và impact matrix"]
    B["2. Expand schema<br/>cột nullable/default, constraint"]
    C["3. Nâng cấp Java writers/readers<br/>chưa bật discount"]
    D["4. Backfill + reconciliation<br/>và kiểm tra compatibility"]
    E["5. Công bố event v2<br/>consumer upgrade/adapter"]
    F["6. Nâng cấp pipeline fact + BI<br/>đối chiếu shadow"]
    G["7. Feature gate ON<br/>cho phép discount > 0"]
    H["8. Theo dõi, điều chỉnh<br/>và contract schema cũ"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Thứ tự trên là **một phương án**, không phải quy tắc bất biến cho mọi hệ thống. Có thể bật event v2 trước khi tất cả consumer chuyển nếu có adapter và consumer cũ vẫn nhận hợp đồng cũ. Nhưng **không nên bật tính năng tạo dữ liệu mới mà các writer quan trọng chưa hiểu**.

### Cổng điều kiện qua từng giai đoạn

| Giai đoạn | Điều kiện tối thiểu để đi tiếp |
| --- | --- |
| Chốt ngữ nghĩa | Owner của Sales, Payment, Analytics và consumer xác nhận totalVnd nghĩa là gì |
| Expand storage | Schema cũ/new code trong ma trận đã test; rollback schema có kế hoạch |
| Deploy Java | Không còn old writer có thể sửa đơn giảm giá; API/batch đều có version hỗ trợ |
| Backfill | Số hàng/cột null đạt ngưỡng chấp nhận; sai khác tài chính đã xử lý |
| Event | Producer/consumer contract test PASS, không double count khi phát v1/v2 |
| Fact/report | Gross−discount=net; các dashboard song song khớp theo metric đúng |
| Enable feature | Có cờ tắt an toàn, dashboard và monitoring biết dữ liệu giảm giá |
| Contract | Không còn dependency vào field cũ; lưu/đọc lịch sử đã kiểm chứng |

Một tính năng đôi khi phải đi qua **nhiều đợt deploy ứng dụng nhưng chỉ một lần đổi ngữ nghĩa**. Ví dụ mọi Order cũ vẫn discount=0 cho đến thời điểm có thể chứng minh các writer đã được nâng cấp. Việc nâng cấp Java code và bật nghiệp vụ giảm giá không nhất thiết cùng thời điểm.

### Feature flag có phạm vi và thời gian

Nếu tính năng chỉ bật cho tenant A:

- Validate tenant của mọi command trên server, không tin một field tenantId tự gửi.
- Old writer ở tenant B vẫn chỉ tạo discount=0, nhưng schema phải hỗ trợ cả hai.
- Report kết hợp nhiều tenant phải biết kỳ bắt đầu có discount của từng tenant.
- Khi tắt flag, **không được cố chuyển các đơn đã giảm giá về trạng thái cũ**; flag chỉ chặn tạo hành vi mới hoặc dẫn tới cách xử lý có kiểm soát.

Một flag có thể đặt theo tenant/kênh/phiên bản API, nhưng phải tránh có hai rule engine cùng cấp giảm giá trên một đơn. Bất biến phải được kiểm tra ở domain/root và persistence, không chỉ trong UI.

## 14. Rollback và roll-forward: mã cũ có đọc được dữ liệu mới không?

**Rollback ứng dụng sau khi đã có đơn giảm giá** là tình huống khác hoàn toàn rollback trước khi bật tính năng:

| Thời điểm sự cố | Có thể rollback bằng cách nào? | Điều không được làm |
| --- | --- | --- |
| Chỉ mới expand schema, chưa có discount > 0 | Thường có thể tạm chạy app cũ nếu compatibility test PASS | Vội DROP cột khi bản mới vẫn truy cập |
| Java mới đã deploy nhưng feature chưa bật | Tắt feature/rollback logic nếu old app tương thích schema | Bỏ qua batch writer hoặc consumer |
| Đã phát sinh đơn có discount > 0 | **Ưu tiên roll-forward/hotfix hoặc chế độ đọc an toàn** | Cho old writer tính lại payable=original gross |
| Event v2 đã phát, consumer cũ lỗi | Dùng adapter/version routing, tạm dừng consumer và replay | Tạo event mới đại diện cùng business occurrence để "gửi lại" |
| Fact/report sai công thức | Dừng công bố KPI, rebuild có version và đối soát | Âm thầm sửa tổng mà không giữ dòng truy vết |

Nếu old binary không thể hiểu hoặc không giữ nguyên discount đã lưu, rollback binary đó có thể **làm hỏng dữ liệu**. Một phương án an toàn hơn là dừng đường ghi discount, triển khai hotfix forward-compatible hoặc đặt hệ thống vào trạng thái read-only có chọn lọc. Không nên xem rollback là chỉ việc đổi image tag trong deployment.

### Contract schema sau khi có dữ liệu mới

Chỉ gỡ cột/field legacy khi:

1. Tất cả writer và reader đã dùng representation mới.
2. Consumer v1 đã được chuyển hoặc có adapter còn được vận hành theo SLA.
3. Backfill/rebuild dữ liệu cũ đã kiểm tra và lịch sử report có thể đọc.
4. Cơ chế backup, restore, replay và rollback còn phù hợp.
5. Query, view, export, script quản trị và BI ngoài hệ thống đã được rà soát.
6. Có cửa sổ bảo trì, giám sát lỗi và người sở hữu quyết định phá tương thích.

**Một migration "DROP COLUMN total_vnd" không nên được chạy chỉ vì class Java không còn field ấy.** Chừng nào công cụ báo cáo hoặc consumer còn phụ thuộc vào ngữ nghĩa cũ, việc xóa có thể là breaking change.

## 15. Kiểm thử sự đồng bộ ở nhiều mức

Viết test chỉ xác minh Java getter/setter là không đủ. Mỗi lớp cần bằng chứng riêng và các lớp cần được **đối soát với nhau**.

### 15.1. Unit test miền: giá trị, bất biến, phiên bản

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderEvolutionTest {
    @Test
    void oldOrderWithZeroDiscountKeepsOldTotalMeaning() {
        var line = new OrderLine(1, UUID.randomUUID(), 2, 100_000, 0);
        assertEquals(200_000, line.grossVnd());
        assertEquals(0, line.discountVnd());
        assertEquals(200_000, line.payableVnd());
    }

    @Test
    void discountedLinesMaintainGrossMinusDiscountEqualsPayable() {
        var order = new SalesOrder(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 2, 100_000, 10_000));
        order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 50_000, 0));

        var totals = order.amounts();
        assertEquals(250_000, totals.grossVnd());
        assertEquals(20_000, totals.discountVnd());
        assertEquals(230_000, totals.payableVnd());
    }

    @Test
    void discountCannotExceedUnitPrice() {
        assertThrows(IllegalArgumentException.class,
            () -> new OrderLine(1, UUID.randomUUID(), 1, 100_000, 100_001));
    }

    @Test
    void capturedAmountMustMatchPayable() {
        var order = new SalesOrder(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 100_000, 10_000));
        var evidence = new PaymentEvidence(
            UUID.randomUUID(), 100_000, Instant.parse("2026-11-22T09:00:00Z"));
        assertThrows(IllegalStateException.class,
            () -> order.recordCapturedPayment(UUID.randomUUID(), evidence));
        assertEquals(OrderState.DRAFT, order.state());
    }
}
~~~

Ví dụ test chỉ xác minh mô hình **trong bộ nhớ**. Để đảm bảo dữ liệu thật không sai khi concurrent, phải dùng integration test chạy trên engine lưu trữ thực, không chỉ mock repository.

### 15.2. Ma trận kiểm thử toàn bộ đường dữ liệu

| Kiểm thử | Mục tiêu | Kết quả mong đợi |
| --- | --- | --- |
| Java old line discount=0 | Tương thích dữ liệu cũ | payable=gross, không đổi nghĩa totalVnd |
| Java new line discount>0 | Công thức và bất biến mới | gross−discount=payable |
| Discount âm/vượt giá hoặc tràn long | Dữ liệu sai | Lỗi trước khi lưu |
| Old app INSERT vào schema expanded | Migration compatibility | discount mặc định 0, không lỗi mapper |
| Old app cố UPDATE đơn có discount | Khả năng ghi sai | Bị chặn/gated, không mất discount |
| Backfill chạy lại | Idempotency | Không tăng tiền hoặc đổi những hàng đã xử lý |
| Backfill gặp dòng thiếu/tiền không khớp | Data quality | Quarantine/cảnh báo, không sửa total để che lỗi |
| Hai PAID command cùng expectedVersion | Concurrency | Tối đa một transaction commit |
| Ghi header thành công nhưng outbox lỗi | Transaction | Rollback cả header |
| Broker redelivery cùng eventId | Consumer idempotency | Không tăng doanh số/lặp tác động |
| Consumer v1 trên event v2 có adapter | Compatibility | totalVnd vẫn là payable |
| Cùng occurrence đi qua hai version routes | Double counting | Một lần nghiệp vụ được tính một lần |
| Event cũ replay sau khi bật discount | Lịch sử đúng | Không tự suy gross cho event thiếu breakdown |
| Dashboard old/new trên dữ liệu discount=0 | Parallel run | Net metric khớp theo cùng cutoff |
| Dashboard có discount | Định nghĩa metric | Gross khác net đúng bằng discount |
| Event đến muộn | Business date | Phân nhóm theo paidAt, không theo ingestAt |
| Tenant B truy cập Order của tenant A | Bảo mật | Bị từ chối, không lộ dữ liệu |
| Rollback binary sau khi bật discount | An toàn dữ liệu | Không cho old writer ghi sai |

### 15.3. Property-based và kiểm thử đối soát

Ngoài vài trường hợp cố định, có thể sinh nhiều dòng hợp lệ với quantity, price, discount và kiểm chứng:

\[
\forall\ \text{valid order}:\
\text{gross}\ge\text{discount}\ge0,\quad
\text{payable}=\text{gross}-\text{discount}\ge0.
\]

Kiểm tra tính bất biến qua nhiều đường:

~~~text
Java amounts()           = persisted header breakdown
Persisted order lines    = persisted header breakdown
Committed OrderPaidV2    = persisted Order state at event version
Analytics paid-line fact = committed source OrderLine snapshots
BI net-paid metric       = SUM(valid fact.net_paid_vnd)
~~~

Không phải tất cả các vế có thể so bằng một câu JOIN trong cùng transaction — đặc biệt warehouse có độ trễ. Đối soát phải dùng **cùng phạm vi tenant, business date, currency, cut-off/watermark và sourceVersion**, ghi rõ độ trễ cho phép. Chênh lệch do dữ liệu đến muộn phải được phân loại, không lờ đi hoặc sửa dashboard để số trông khớp.

## 16. Quan sát vận hành và điều tra lỗi sau triển khai

Một lộ trình migration không kết thúc khi lệnh ALTER TABLE báo thành công. Cần theo dõi **cả bất biến và luồng dữ liệu**:

| Tín hiệu | Vì sao quan trọng? |
| --- | --- |
| Tỷ lệ order_line có discount NULL/sai phạm vi | Old writer, dữ liệu cũ chưa backfill hoặc lỗi nhập |
| Header gross−discount khác total | Bất biến tài chính bị phá |
| Tỷ lệ command bị version conflict | Old/new writer cạnh tranh; có thể cần điều chỉnh retry |
| Số code path còn ghi cột cũ | Chưa đủ điều kiện contract schema |
| Outbox lag và sự kiện phát trùng | Relay lỗi hoặc retry bình thường cần consumer dedup |
| Consumer schema reject / dead letter | Không tương thích event v1/v2 |
| Tỷ lệ event chưa có breakdown | Không thể xây metric gross/discount đầy đủ |
| Số fact trùng khóa hoặc sourceVersion quay lùi | Lỗi CDC, replay, mapping |
| Chênh lệch source total với BI net theo cutoff | Lỗi pipeline, late data hoặc khác định nghĩa |
| Dashboard query lỗi sau khi chuyển view | Consumer báo cáo chưa tương thích |
| Quyền tenant/schema migration | Rò dữ liệu hoặc vượt phạm vi quyền |

### Một kịch bản điều tra

Sau khi bật chiết khấu cho 5% tenant, dashboard báo gross 250 triệu, discount 20 triệu nhưng net là 231 triệu thay vì 230 triệu. Không nên vội sửa một cột:

1. Xác minh metric, cửa sổ thời gian, múi giờ và dataset version của dashboard.
2. Truy vấn fact tìm dòng có gross−discount≠net; nếu mọi dòng đúng, tìm lỗi group/filter hoặc duplicate JOIN.
3. Đối chiếu source Order theo (tenantId, orderId, lineNo) và sourceVersion.
4. Kiểm tra có event v1/v2 của **cùng occurrence** bị tính hai lần hay không.
5. Kiểm tra một Payment capture hoặc refund bị đếm theo ngày khác và có đúng là cùng metric không.
6. Nếu lỗi thuộc transform, dừng công bố metric chính thức, sửa code rồi rebuild phạm vi bị ảnh hưởng với transformVersion mới.
7. Ghi audit quyết định sửa và so sánh số trước/sau; không im lặng làm mất bản báo cáo đã công bố.

**Lineage** giúp nối dashboard row → fact grain → event/source Order → schema/transform version. Nếu không có khóa ổn định và metadata nguồn, điều tra sẽ dựa vào phỏng đoán dù tất cả bảng đều có nhiều cột timestamp.

## 17. Điểm khác nhau khi tiến hóa mô hình quan hệ, document, đồ thị và phân tích

Nguyên tắc chung vẫn là tương thích ngữ nghĩa và quyền sở hữu, nhưng thao tác vật lý khác nhau:

| Kiểu dữ liệu | Thay đổi thường gặp | Cơ chế chuyển tiếp | Bẫy |
| --- | --- | --- | --- |
| **Quan hệ** | Thêm cột discount, constraint, index | Expand/backfill/validate, version/transaction | DDL lock, old writer UPDATE bỏ field, cột summary lệch |
| **Document** | Thêm discountPerUnitVnd trong mảng lines | Reader default có điều kiện, schemaVersion/document migration, conditional update | Document cũ thiếu field; ghi lại document làm mất field mới |
| **Đồ thị** | Thêm quan hệ giá/khuyến mại/phiên bản | Migrate node/edge và query theo ngữ nghĩa mới | Edge mới không tự xác nhận quyền đổi Order hoặc tính tiền đúng |
| **Warehouse cột/lakehouse** | Thêm measures, đổi grain, partition, semantic layer | Fact v2, backfill/MERGE, views song song, metric version | Đếm trùng, late data, sửa lịch sử, query cũ đọc sai cột |

### Document và mixed-version readers

Một document Order cũ có:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 1,
  "lines": [
    { "lineNo": 1, "quantity": 2, "unitPriceVnd": 100000 }
  ],
  "totalVnd": 200000
}
~~~

Reader mới có thể diễn giải **discountPerUnitVnd=0** cho document v1, vì hợp đồng v1 chắc chắn không có giảm giá. Khi ghi document v2:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 2,
  "lines": [
    {
      "lineNo": 1,
      "quantity": 2,
      "unitPriceVnd": 100000,
      "discountPerUnitVnd": 10000
    }
  ],
  "grossTotalVnd": 200000,
  "discountTotalVnd": 20000,
  "totalVnd": 180000
}
~~~

**Chú ý:** old writer có thể tải nguyên document v2, không biết discountPerUnitVnd, sau đó replace toàn bộ document bằng v1 và **xóa mất trường mới**. Conditional update/version và việc ngăn old writer sửa document mới là quan trọng, không chỉ default khi đọc.

### Đồ thị và phân tích cũng có migration contract

Trong graph, Product và Promotion có thể trở thành các node liên kết, nhưng chiết khấu đã chốt trên một OrderLine vẫn cần **snapshot hoặc sự thật đủ rõ về thời điểm áp dụng**. Nếu chỉ nối OrderLine tới giá Promotion hiện hành, sửa promotion hôm sau có thể làm lịch sử Order thay đổi.

Trên warehouse, nếu một thay đổi buộc đổi **grain** từ một OrderLine thành một lần capture/hoàn cho OrderLine, phải tạo fact grain mới hoặc một mô hình có định danh đủ, **không nhét nhiều lần capture vào một khóa OrderLine duy nhất** và hy vọng aggregate đúng.

## 18. Bài tập thực hành: thêm thuế vào phí dịch vụ đặt xe

**Bối cảnh:** Một nền tảng đặt xe lưu Trip với số km, phí cơ bản và tổng phí VND. Trước đây không có thuế/phụ phí riêng. Chính sách mới yêu cầu hiển thị **fareBeforeTax**, **taxAmount**, **totalCharged**, trong đó một số chuyến có ưu đãi miễn/giảm theo loại dịch vụ. Hóa đơn cũ và mới phải có thể đối soát. Payment và Analytics thuộc các bounded context riêng.

### Câu hỏi

1. Viết bất biến cho TripAmount. Nếu vừa có discount vừa có tax, thứ tự áp dụng và quy tắc làm tròn thuộc hợp đồng nào? Vì sao không nên tự đoán?
2. Đề xuất thay đổi trong Java Trip aggregate và một value object MoneyVnd. Không tạo setter setTaxAmount tùy ý bỏ qua policy.
3. Thiết kế thay đổi storage bằng expand → backfill → enforce → contract, với trường cũ total_vnd vẫn mang nghĩa gì trong giai đoạn chuyển tiếp?
4. Một phần trip cũ không có thông tin thuế nhưng hệ thống kế toán từng tính ở nguồn khác. Có được điền taxAmount=0 để backfill cho tất cả không? Nếu không, cần làm gì?
5. Đề xuất TripChargedV2, kế hoạch consumer v1, idempotency và thứ tự triển khai trước khi bật thuế.
6. Thiết kế fact ở grain một chuyến được charge hoàn tất và metric phí trước thuế/thuế/tổng đã thu. Nếu có nhiều capture cho một Trip, grain nào mới phù hợp?
7. Nếu rollback Java sau khi có trip tính thuế, old writer có thể phá dữ liệu thế nào? Đề xuất một phương án chống ghi sai.
8. Viết test cho số âm, làm tròn, old/new app compatibility, late event, duplicate capture và dashboard reconciliation.

### Một hướng giải

- **Domain:** TripPricing/TripAmount chứa fareBeforeTax, discount, taxableBase, tax và totalCharged. Công thức chỉ được xác định sau khi business/policy owner chốt thứ tự khấu trừ, loại thuế, mức thuế, đơn vị làm tròn và thời điểm hiệu lực. Không tự mặc định tax tính trên giá gộp hay giá sau chiết khấu.
- **Storage:** thêm cột amount breakdown nullable/default chỉ khi có nghĩa lịch sử được chứng minh; backfill từ sổ nguồn có thẩm quyền, không điền 0 cho trường tax chưa từng lưu nếu kế toán có thể tính thuế ở nguồn khác.
- **Exchange:** TripChargedV2 công bố các số tiền có tên, currency, occurredAt, eventId, schemaVersion. Consumer v1 có thể tiếp tục nhận totalCharged qua adapter nếu tổng cũ đã có nghĩa **số thực thu**, không đổi thành "trước thuế".
- **Report:** fact có grain một TripCharged khi chính sách cho phép charge một lần; khi nhiều capture, cần grain một capture hoặc allocation có khóa riêng và quy tắc tổng hợp.
- **Triển khai:** nâng writer và pipeline trước khi bật flag; đối chiếu tiền từng trip và toàn kỳ; sau đó contract schema theo kế hoạch. Sau khi đã có dữ liệu thuế mới, rollback old binary không hiểu thuế có thể làm mất breakdown.
- **Kiểm thử:** thuộc tính số học và policy có version, backfill không sửa sai lịch sử, event cùng occurrence không đếm hai lần, giao dịch outbox nguyên tử, report đủ dữ liệu và cùng cutoff.

## 19. Checklist bàn giao và kết luận

Trước khi tuyên bố một thay đổi mô hình đã hoàn tất, hãy kiểm tra:

- **Ngữ nghĩa:** field cũ và mới có cùng nghĩa, đơn vị, trạng thái và thời điểm ghi nhận như đã công bố không?
- **Domain:** bất biến đã được cập nhật tại đúng aggregate/value object; mọi command writer cùng tuân thủ không?
- **Schema:** cột mới, default, khóa, constraint, index và migration có an toàn khi old/new instance chạy song song không?
- **Backfill:** quy tắc dữ liệu lịch sử có căn cứ, chạy lại idempotent, đối soát mismatch và xử lý NULL rõ ràng không?
- **Concurrency:** mọi đường ghi giữ đúng root version/lock, không có một old writer âm thầm ghi đè dữ liệu mới không?
- **Event:** v1/v2 có hợp đồng, quyền chủ sở hữu, schemaVersion, eventId và correlation rõ, không đổi nghĩa field im lặng không?
- **Outbox/inbox:** commit sự thật và ý định publish cùng transaction; retry/duplicate/out-of-order có phương án không?
- **Consumers:** có ma trận tương thích, adapter/contract test, phương án chuyển giao và kế hoạch ngừng v1 chưa?
- **Báo cáo:** grain, gross/discount/net, lịch sử, timezone, metric version, SCD và correction đã được xem xét không?
- **Đối soát:** có thể nối được Java/domain → SQL → event → fact → KPI theo ID/cutoff/version không?
- **Triển khai:** đã thử expand/migrate/switch/contract theo thứ tự và định nghĩa cổng bật feature chưa?
- **Rollback:** nếu đã có dữ liệu mới, việc quay lại binary cũ có gây mất thông tin không? Có phương án roll-forward an toàn chưa?
- **Bảo mật:** tenant, dữ liệu cá nhân, payload event, quyền đọc bản lịch sử và retention đã được kiểm soát chưa?
- **Quan sát:** biết phát hiện chênh lệch tài chính, message lỗi, lag, schema conflict và báo cáo sai sau deploy không?
- **Kiểm thử:** unit, integration với DB thật, contract, replay, dữ liệu biên và shadow reporting đã PASS chưa?

**Kết luận:** Đồng bộ thay đổi giữa Java, lưu trữ, sự kiện và báo cáo không phải đồng bộ **tên field**, mà là bảo vệ **một sự thật nghiệp vụ xuyên các biểu diễn và các phiên bản đang cùng tồn tại**. Java chịu trách nhiệm hành vi và bất biến; database bảo vệ dữ liệu ở điểm commit; event công bố hợp đồng có phiên bản; mô hình phân tích diễn giải dữ liệu theo grain/metric và thời điểm rõ ràng. Một thay đổi an toàn có lộ trình **expand → migrate/đối soát → switch → contract**, không bật hành vi mới trước khi mọi writer quan trọng hiểu nó, và không coi rollback code là đủ khi dữ liệu đã tiến hóa. Thiết kế được như vậy, mô hình dữ liệu mới có thể tiến hóa, truy vết và kiểm chứng mà không làm biến dạng những cam kết nghiệp vụ trong quá khứ.
