# Xử lý khoảng trống số thứ tự và kỳ vọng nghiệp vụ về mã định danh

Trong một ứng dụng Java dùng JPA/Hibernate, bảng `orders` có thể chứa các ID `101, 102, 104, 109`. Người dùng thường thắc mắc: “Đơn hàng số 103 ở đâu?”, “Có phải dữ liệu bị mất?”, “Vì sao hệ thống không đánh số liên tục?”. Câu trả lời là **khóa chính tự sinh không có cam kết liên tục**. Database sequence, identity column, Hibernate optimizer, transaction rollback và cách xử lý đồng thời đều có thể làm dãy ID bỏ qua một số giá trị.

Muốn xử lý đúng cần phân biệt **ID kỹ thuật**, **mã nghiệp vụ hiển thị** và **số chứng từ cần quản lý chuỗi phát hành**. ID kỹ thuật tập trung bảo đảm tính duy nhất; còn việc không bỏ số, phát hành theo năm, giữ lịch sử số bị hủy hay đối soát có thể là quy tắc nghiệp vụ riêng. Bài học này giải thích nguyên nhân xuất hiện khoảng trống và thiết kế một cơ chế phù hợp với từng kỳ vọng trong ngữ cảnh JPA, Hibernate và cơ sở dữ liệu quan hệ.

## 1. Phân biệt định danh và số thứ tự nghiệp vụ

Giả sử bảng `purchase_orders` có dữ liệu:

| id | created_at | status |
|---:|---|---|
| 1001 | 08:00 | CONFIRMED |
| 1002 | 08:01 | CONFIRMED |
| 1004 | 08:03 | CANCELED |
| 1007 | 08:05 | CONFIRMED |

Dãy thiếu 1003, 1005 và 1006 không chứng minh rằng các đơn hàng tương ứng từng tồn tại rồi bị xóa. Có thể các số đó đã được bộ sinh khóa cấp cho những giao dịch cuối cùng rollback hoặc chưa từng được sử dụng.

| Loại định danh | Ví dụ | Mục đích | Có thể bỏ số? |
|---|---|---|---|
| **Primary key kỹ thuật** | `purchase_orders.id = 1007` | Nhận diện hàng dữ liệu, foreign key và entity | Có |
| **Mã tra cứu đơn hàng** | `ORD-2026-1007` | Hiển thị trong giao diện và khi chăm sóc khách hàng | Tùy quy định |
| **Số chứng từ đã phát hành** | `INV-2026-000158` | Đối soát, lập sổ và theo dõi chứng từ | Có thể yêu cầu quản lý liên tục theo một scope |
| **Thứ tự hiển thị** | Dòng 1, dòng 2 trong trang kết quả | Phân trang và giao diện | Phụ thuộc bộ lọc/sắp xếp, không phải định danh |

Cần diễn đạt chính xác yêu cầu:

- **Unique:** mỗi đối tượng có giá trị khác nhau trong phạm vi ràng buộc.
- **Increasing:** các số mới có xu hướng lớn hơn số cũ theo một cơ chế cấp phát.
- **Gapless/contiguous:** không có giá trị nào bị bỏ qua trong phạm vi đã định nghĩa.
- **Commit order:** số nhỏ hơn được commit/phát hành trước số lớn hơn.
- **Durable identifier:** mã đã phát hành không bị tái sử dụng cho đối tượng khác.

Các khái niệm trên **không tương đương**. Một sequence cấp số 10 rồi 11 có thể chứng kiến giao dịch nhận 11 commit trước giao dịch nhận 10. Cả hai vẫn duy nhất, nhưng thứ tự cấp số không phản ánh thứ tự commit.

## 2. Hợp đồng của khóa chính trong JPA

JPA dùng `@Id` để khai báo định danh entity và `@GeneratedValue` để mô tả chiến lược tạo giá trị.

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public PurchaseOrder(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }
}
~~~

Với mapping này, `id` giúp JPA provider nhận diện entity và database bảo vệ primary key. Không có annotation chuẩn nào ở đây mang ý nghĩa “giá trị phải liên tục sau rollback”.

Các chiến lược cấp ID phổ biến:

| Strategy | Nguồn cấp ID | Lý do có thể tạo khoảng trống |
|---|---|---|
| `GenerationType.IDENTITY` | Identity/auto-increment của database | Insert thất bại, rollback, cấp phát hoặc cache bên dưới |
| `GenerationType.SEQUENCE` | Database sequence | Gọi nextval không rollback, sequence cache, ORM preallocation |
| `GenerationType.TABLE` | Bảng chứa thông tin cấp số do provider quản lý | Tùy thuật toán/optimizer, allocation và transaction; không cam kết gapless |
| `GenerationType.AUTO` | JPA provider lựa chọn | Có thể dùng sequence, identity hoặc phương án tương ứng |
| `GenerationType.UUID` | UUID theo provider/API tương thích | Không phải dãy số nguyên để yêu cầu gapless |

`GenerationType.UUID` có trong Jakarta Persistence 3.1; mức hỗ trợ thực tế phụ thuộc phiên bản API/provider. Dùng UUID có thể giảm nhu cầu phối hợp cấp ID giữa các node, nhưng không giải quyết kỳ vọng “dãy số nguyên từ 1 tới N”.

### 2.1. Ví dụ SEQUENCE

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_generator"
    )
    @SequenceGenerator(
        name = "purchase_order_generator",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 1
    )
    private Long id;

    protected PurchaseOrder() {}
}
~~~

DDL minh họa trên PostgreSQL:

~~~sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);
~~~

Ở ví dụ này, `allocationSize = 1` giúp thấy rõ mỗi lần provider cần một giá trị mới. **Không có nghĩa các bản ghi đã commit sẽ mang ID 1, 2, 3,... liên tục.**

Khi dùng `allocationSize` lớn hơn 1, Hibernate có thể tận dụng thuật toán cấp phát theo nhóm. Cần cấu hình database sequence tương thích với optimizer mà phiên bản Hibernate sử dụng; không tùy tiện thay `allocationSize` mà không kiểm tra database generator.

### 2.2. Ví dụ IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với một DBMS có identity column tương ứng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

Database có thể cấp ID ngay khi thực thi INSERT. Provider đôi khi cần gửi INSERT sớm để nhận giá trị ID. Nếu transaction sau đó thất bại và rollback, số identity đã cấp có thể không được trả lại.

**IDENTITY không bảo đảm “ít khoảng trống hơn SEQUENCE”.** Cả hai là giải pháp nhận diện hàng dữ liệu, không phải bộ máy phát hành chứng từ tuần tự.

## 3. Các nguồn tạo khoảng trống ID

### 3.1. Transaction rollback

Với PostgreSQL, thao tác `nextval()` trên sequence không bị rollback khi transaction rollback. Ví dụ:

~~~sql
CREATE SEQUENCE demo_seq START WITH 1;

BEGIN;
SELECT nextval('demo_seq'); -- 1
ROLLBACK;

BEGIN;
SELECT nextval('demo_seq'); -- 2
COMMIT;
~~~

Số 1 đã được lấy nhưng không có hàng dữ liệu nào bắt buộc phải tồn tại với ID 1. Đó là hành vi thiết kế của sequence để hỗ trợ cấp số hiệu quả trong môi trường concurrent.

Trong JPA:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    PurchaseOrder order = new PurchaseOrder("NEW");
    em.persist(order);

    // Một kiểm tra nghiệp vụ thất bại.
    throw new IllegalStateException("Thông tin đặt hàng không hợp lệ");
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
}
~~~

Nếu provider đã tiêu thụ ID trong quá trình xử lý, rollback transaction không có nghĩa ID được tái sử dụng. Đối với IDENTITY, INSERT có thể đã chạy trước lỗi; cơ chế identity của database quyết định việc cấp số.

### 3.2. INSERT lỗi ràng buộc

Khi INSERT vi phạm `UNIQUE`, `CHECK` hoặc `FOREIGN KEY`, database có thể đã cấp identity/sequence trước khi phát hiện lỗi. Transaction thất bại nhưng số sinh ra không nhất thiết quay lại dãy cấp phát. Không phải mỗi lần gọi generator đều dẫn tới một hàng commit thành công.

### 3.3. Sequence cache của database

PostgreSQL cho phép sequence lưu đệm giá trị:

~~~sql
CREATE SEQUENCE cached_order_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 20;
~~~

Một backend có thể giữ một nhóm số trước khi thực sự sử dụng hết. Nếu backend kết thúc hoặc database restart, một số giá trị dự trữ có thể bị bỏ qua. Khi có nhiều backend, việc đọc các giá trị sinh ra từ các phiên khác nhau cũng có thể tạo cảm giác không tăng đều theo từng INSERT quan sát được.

Sequence cache ở DBMS và allocation ở Hibernate là hai lớp khác nhau.

### 3.4. allocationSize và optimizer của Hibernate

~~~java
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
~~~

Khi cấu hình phù hợp, một lần phối hợp với database có thể giúp provider cấp nhiều ID trong bộ nhớ. Nhờ đó giảm lượt truy cập database, nhưng nếu ứng dụng ngừng hoạt động trước khi dùng hết nhóm ID được dự trữ thì một phần giá trị có thể không được ghi vào bảng.

~~~text
Một nhóm giá trị được cấp phát:  1 ... 50
Ứng dụng đã sử dụng:             1 ... 12
Ứng dụng dừng trước khi dùng hết
Lần khởi động sau dùng nhóm khác
=> Có thể thiếu 13 ... 50 trong dữ liệu.
~~~

Đây là mô hình khái niệm, không phải công thức luôn đúng cho mọi optimizer. Cách Hibernate dùng `pooled`, `pooled-lo`, database increment, restart và các cơ chế khác phụ thuộc phiên bản/cấu hình.

Giảm `allocationSize` về 1 có thể giảm số chưa sử dụng do cấp phát theo lô, nhưng không giải quyết rollback, insert lỗi, cache của DBMS hay concurrency. Đồng thời nó có thể làm tăng số lượt database round-trip.

### 3.5. Transaction song song

~~~text
Thời điểm    Transaction A             Transaction B
---------------------------------------------------------
T1           Nhận ID 101
T2                                     Nhận ID 102
T3                                     COMMIT
T4           Thực hiện thêm nghiệp vụ
T5           COMMIT hoặc ROLLBACK
~~~

ID 102 có thể đã xuất hiện với người dùng trước 101. Nếu A rollback, chỉ có bản ghi 102. Một số nhỏ hơn **không chứng minh** giao dịch đó được commit sớm hơn.

### 3.6. Xóa dữ liệu, import và thao tác vận hành

Khoảng trống còn có thể phát sinh từ việc xóa bản ghi, import dữ liệu với ID có sẵn, cập nhật sequence trong migration, reset không phù hợp hoặc một thao tác thử nghiệm từng dùng ID.

| Nguồn gap | Có đồng nghĩa dữ liệu bị mất? |
|---|---|
| Rollback sau khi cấp ID | Không |
| Constraint violation | Không |
| Sequence cache/ORM allocation | Không |
| App/database restart | Không |
| Transaction concurrent | Không |
| DELETE một hàng đã tồn tại | Có thể đã xóa bản ghi; cần audit để xác định |
| Migration hoặc thao tác quản trị | Cần xem log và lịch sử thực tế |

Vì vậy, không thể chỉ nhìn dãy ID để kết luận nguyên nhân.

## 4. Vì sao gapless không phải mặc định của database sequence?

Giả sử yêu cầu: “Mỗi transaction phải chờ transaction trước commit hoặc rollback để không bỏ số nào”. Để bảo đảm điều đó, hệ thống phải có một cơ chế **tuần tự hóa cấp số gắn với kết quả của transaction**. Các transaction cạnh tranh cùng một chuỗi có thể phải đợi nhau.

Generator khóa chính tối ưu chủ yếu cho:

- Tính duy nhất.
- Cấp số nhanh khi có nhiều request.
- Giảm tranh chấp và round-trip.
- Cho phép transaction chạy độc lập.
- Không cần hoàn trả hoặc tái sử dụng số đã phát.

Bộ cấp số chứng từ gapless lại đặt trọng tâm vào:

- Mỗi số phát hành tương ứng với một kết quả đã commit trong phạm vi.
- Một transaction lỗi không làm tiêu thụ số vĩnh viễn.
- Có log/audit và quy tắc hủy mà vẫn giữ dấu vết.
- Có cơ chế bảo vệ concurrency và retry.

Hai mục tiêu này khác nhau. **Đừng dùng cùng một bộ sinh ID cho cả hai chỉ vì cả hai đều trả về số nguyên.**

## 5. Kỳ vọng nghiệp vụ cần được làm rõ như thế nào?

Câu “không được mất số” thường chưa đủ chi tiết. Cần xác định:

| Vấn đề | Những câu hỏi cần trả lời |
|---|---|
| Đối tượng nào có số? | Đơn hàng, hóa đơn, phiếu thu, đơn nháp, bản ghi log? |
| Cấp số lúc nào? | Khi bắt đầu draft, khi xác nhận, khi thanh toán hay khi chính thức phát hành? |
| Phạm vi liên tục | Toàn hệ thống, từng năm, từng chi nhánh, từng loại chứng từ? |
| Nếu rollback | Số đó được phép bỏ hay phải trả về counter? |
| Nếu hủy sau commit | Giữ số và đánh dấu VOID hay có quy tắc khác? |
| Nếu retry HTTP | Tạo chứng từ mới hay trả lại kết quả cũ? |
| Có yêu cầu thứ tự? | Thứ tự cấp số, thứ tự commit hay thứ tự hiển thị? |
| Hiệu năng | Một vài chứng từ/phút hay hàng nghìn giao dịch/giây? |
| Nhiều database | Có một transaction database chung hay phân tán? |
| Quy định áp dụng | Cần kiểm tra chuẩn/quy định cụ thể của loại chứng từ và nơi vận hành nào? |

Ví dụ về số phát hành trong từng năm:

~~~text
INV-2026-000001
INV-2026-000002
INV-2026-000003

INV-2027-000001  // Chuỗi mới theo năm
~~~

Nếu muốn chuỗi “không bỏ số”, phải nói rõ yêu cầu đó áp dụng **cho tất cả bản ghi phát hành năm 2026, kể cả những chứng từ đã hủy nhưng được giữ lại trong sổ**, hay chỉ cho bản ghi đang hiệu lực. Hai cách tính có thể cho kết luận hoàn toàn khác nhau.

Một mô hình vòng đời thường gặp:

~~~text
DRAFT
  |
  | Kiểm tra, duyệt và chuẩn bị dữ liệu
  v
ISSUED       <- Cấp serial chính thức trong transaction phát hành
  |
  +----> VOID / CANCELED  <- Giữ nguyên serial, lưu lý do hủy
  |
  +----> CLOSED / PAID
~~~

Không nên cấp số chính thức quá sớm cho mọi draft nếu nhiều draft có thể bị bỏ dở. Chỉ cấp khi nghiệp vụ xác định trạng thái phát hành; khi hủy sau phát hành, thường nên giữ số cùng hồ sơ audit. Các quy tắc pháp lý về phát hành/hủy/chỉnh sửa chứng từ phụ thuộc lĩnh vực và nơi áp dụng; thiết kế JPA không thay thế việc xác nhận yêu cầu đó.

## 6. Tách khóa chính kỹ thuật khỏi mã nghiệp vụ

Một thiết kế phù hợp:

~~~text
IssuedInvoice
  id         = 893212               <- PRIMARY KEY kỹ thuật
  fiscalYear = 2026
  serialNo   = 158                  <- Số phát hành trong năm
  status     = ISSUED
  displayNo  = INV-2026-000158      <- Định dạng cho người dùng
~~~

DB có thể định nghĩa:

~~~sql
CREATE TABLE issued_invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    serial_no BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_invoice_no UNIQUE (fiscal_year, serial_no),
    CONSTRAINT ck_invoice_serial CHECK (serial_no > 0),
    CONSTRAINT ck_invoice_status
        CHECK (status IN ('ISSUED', 'VOID'))
);
~~~

Ưu điểm:

1. `id` phục vụ ORM, foreign key và cập nhật bản ghi ổn định; có thể gap.
2. `(fiscal_year, serial_no)` là business key có unique constraint riêng.
3. `status` cho phép chứng từ đã hủy vẫn giữ serial trong lịch sử.
4. Chuỗi hiển thị có thể được tạo từ dữ liệu có cấu trúc, không nhất thiết phải làm primary key.
5. Có thể tạo draft không có serial trước khi phát hành.

Nếu có nhiều loại chứng từ hoặc chi nhánh, bổ sung các trường scope và đặt unique constraint phù hợp, ví dụ `UNIQUE(document_type, branch_id, fiscal_year, serial_no)`.

**Unique constraint ngăn số trùng, nhưng không tự bảo đảm dãy liên tục.** Phải có thêm quy tắc cấp số và quản lý transaction.

### 6.1. Ví dụ entity JPA

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "issued_invoices",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_invoice_no",
        columnNames = {"fiscal_year", "serial_no"}
    )
)
public class IssuedInvoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "fiscal_year", nullable = false, updatable = false)
    private int fiscalYear;

    @Column(name = "serial_no", nullable = false, updatable = false)
    private long serialNo;

    @Column(nullable = false)
    private String status;

    @Column(name = "issued_at", nullable = false)
    private Instant issuedAt;

    protected IssuedInvoice() {}

    public IssuedInvoice(int fiscalYear, long serialNo, Instant issuedAt) {
        this.fiscalYear = fiscalYear;
        this.serialNo = serialNo;
        this.issuedAt = issuedAt;
        this.status = "ISSUED";
    }

    public String displayNo() {
        return String.format("INV-%d-%06d", fiscalYear, serialNo);
    }

    public Long getId() {
        return id;
    }
}
~~~

Hàm `displayNo()` chỉ định dạng mã; định dạng có thể thay đổi theo quy ước UI. Nếu serial lớn hơn độ rộng 6 chữ số, `String.format` không cắt phần chữ số cao hơn, nhưng nghiệp vụ vẫn cần quyết định chính sách độ dài.

Ràng buộc trong schema thực tế phải được tạo bằng migration hoặc cơ chế DDL phù hợp; annotation `@UniqueConstraint` không đảm bảo schema production đã được cập nhật nếu hệ thống tắt auto-DDL.

## 7. Trường hợp không cần gapless: dùng generator bình thường

Đối với mã đơn hàng thông thường, yêu cầu có thể chỉ là:

- Không trùng mã.
- Dễ đọc và tra cứu.
- Không cần mọi số đều xuất hiện.
- Người dùng chấp nhận các số bị bỏ qua.
- Không tuyên bố thứ tự ID là thứ tự commit chính xác.

Trong trường hợp đó, dùng `@GeneratedValue(IDENTITY)`, `SEQUENCE` hoặc UUID là phù hợp. Có thể format ID:

~~~java
public static String displayOrderNo(long id) {
    return "ORD-" + String.format("%08d", id);
}
~~~

Ví dụ tạo ra `ORD-00001001`, `ORD-00001002` và `ORD-00001004`. Formatter không lấp gap. Điều cần làm là **đặt kỳ vọng đúng trong sản phẩm**: mã đơn là định danh để tra cứu, không phải bằng chứng số đơn đã xử lý.

Nếu muốn không lộ quy mô kinh doanh qua dãy ID tăng dần, có thể chọn mã ngẫu nhiên/UUID riêng cho public API, nhưng yêu cầu đó cũng khác với gapless.

## 8. Khi cần dãy phát hành liên tục: counter row trong cùng transaction

Đối với chuỗi chứng từ đòi hỏi không bỏ số trong các bản ghi phát hành đã commit, có thể dùng **counter row được cập nhật trong cùng database transaction** với việc tạo chứng từ.

Tư tưởng chính:

~~~text
BEGIN
  Khóa/cập nhật bộ đếm theo năm
  Lấy serial kế tiếp
  Ghi chứng từ ISSUED với serial đó
COMMIT

Nếu bất kỳ thao tác nào thất bại:
ROLLBACK cả bộ đếm lẫn chứng từ
~~~

Khác với `nextval()`, cập nhật một hàng dữ liệu bình thường **có thể rollback**. Transaction còn hoạt động sẽ giữ row lock để transaction khác cùng scope chờ, từ đó tránh cả hai cùng lấy một serial.

### 8.1. Bảng counter

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE invoice_counters (
    fiscal_year INTEGER PRIMARY KEY,
    next_number BIGINT NOT NULL,
    CONSTRAINT ck_counter_positive CHECK (next_number > 0)
);

INSERT INTO invoice_counters (fiscal_year, next_number)
VALUES (2026, 1);
~~~

`next_number` là số sẽ cấp cho lần phát hành kế tiếp. Các năm khác nhau có hàng counter khác nhau, nên có thể cấp số song song nếu yêu cầu nghiệp vụ tách chuỗi theo năm.

### 8.2. Transaction cấp số và insert cùng lúc

~~~sql
BEGIN;

WITH allocated AS (
    UPDATE invoice_counters
       SET next_number = next_number + 1
     WHERE fiscal_year = 2026
    RETURNING next_number - 1 AS allocated_no
)
INSERT INTO issued_invoices (
    fiscal_year,
    serial_no,
    status,
    issued_at
)
SELECT
    2026,
    allocated_no,
    'ISSUED',
    CURRENT_TIMESTAMP
FROM allocated;

COMMIT;
~~~

Cơ chế trong PostgreSQL:

1. `UPDATE` lấy row lock của counter thuộc năm 2026.
2. `RETURNING` lấy số vừa được cấp bằng `next_number - 1`.
3. `INSERT` tạo chứng từ dùng số đó trong **cùng transaction**.
4. Transaction khác muốn cập nhật counter của năm 2026 phải chờ.
5. Nếu transaction rollback, cả `next_number` lẫn bản ghi chứng từ cùng được phục hồi về trạng thái trước.

**Giới hạn cần xử lý:** nếu hàng counter chưa tồn tại, `UPDATE` trả zero rows và `INSERT ... SELECT` sẽ không chèn gì. Ứng dụng phải kiểm tra số hàng insert bằng 1, báo lỗi nếu bằng 0 và bảo đảm counter được khởi tạo an toàn bằng migration hoặc một protocol chịu concurrency.

Việc này đảm bảo thuộc tính mong muốn **trong phạm vi các bản ghi đã commit và được giữ lại**, với điều kiện mọi writer đều đi qua cơ chế này và không có thao tác xóa/sửa serial trái quy tắc.

### 8.3. Vì sao không dùng MAX(serial_no)+1?

Một cách ngắn nhưng dễ mắc race condition:

~~~sql
SELECT COALESCE(MAX(serial_no), 0) + 1
FROM issued_invoices
WHERE fiscal_year = 2026;
~~~

Hai transaction đồng thời có thể cùng đọc kết quả 58:

~~~text
Request A: MAX + 1 -> 58
Request B: MAX + 1 -> 58
Request A: INSERT 58 -> thành công
Request B: INSERT 58 -> lỗi UNIQUE
~~~

Unique constraint bảo vệ khỏi trùng dữ liệu nhưng không tự biến câu `MAX+1` thành giao thức cấp số tuần tự an toàn. Muốn áp dụng MAX+1 cũng phải có cơ chế khóa/serialization đủ chặt, lúc đó cần thiết kế và đánh đổi tương tự counter.

`COUNT(*) + 1` còn tệ hơn: nếu có bản ghi bị xóa hoặc lọc trạng thái thì số lượng không tương ứng với serial kế tiếp.

### 8.4. Tại sao counter giảm throughput?

Một counter duy nhất cho một scope buộc các giao dịch phát hành cùng scope phải **đợi nhau** tại row lock. Nếu mỗi transaction giữ khóa trong thời gian dài, số request phải chờ tăng lên.

Cần giữ transaction phát hành ngắn:

~~~text
Trước transaction:
    Kiểm tra đầu vào và chuẩn bị dữ liệu hợp lệ.

Trong transaction:
    Xác nhận các điều kiện cần tính nhất quán.
    Cập nhật counter.
    Ghi chứng từ và audit/outbox event.
    Commit.

Sau commit:
    Gửi email hoặc xử lý event bên ngoài DB.
~~~

Những kiểm tra phụ thuộc dữ liệu có thể thay đổi đồng thời vẫn phải chạy trong transaction với locking/isolation phù hợp; không được đẩy hết ra ngoài rồi giả định trạng thái không đổi.

Nếu throughput quá cao, xem xét chia scope **khi nghiệp vụ thực sự cho phép**, ví dụ theo loại chứng từ hoặc chi nhánh. Không tự ý tạo một counter mỗi node nếu nghiệp vụ yêu cầu một dãy duy nhất trên toàn hệ thống.

## 9. Tích hợp với Spring/JPA

Trong ứng dụng Spring, `@Transactional` có thể bảo đảm logic cập nhật counter và lưu entity chạy trong một transaction database khi cấu hình datasource/transaction manager đúng. Ví dụ dùng PostgreSQL native query vì JPA chuẩn không định nghĩa `UPDATE ... RETURNING`:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Instant;

@Service
public class InvoiceIssuer {
    @PersistenceContext
    private EntityManager em;

    private final Clock clock;

    public InvoiceIssuer(Clock clock) {
        this.clock = clock;
    }

    @Transactional
    public IssuedInvoice issue(int fiscalYear) {
        Number number = (Number) em.createNativeQuery(
                """
                UPDATE invoice_counters
                   SET next_number = next_number + 1
                 WHERE fiscal_year = :year
                RETURNING next_number - 1
                """
            )
            .setParameter("year", fiscalYear)
            .getSingleResult();

        IssuedInvoice invoice = new IssuedInvoice(
            fiscalYear,
            number.longValue(),
            Instant.now(clock)
        );

        em.persist(invoice);
        em.flush();
        return invoice;
    }
}
~~~

Đây là mã minh họa cho môi trường PostgreSQL/JPA provider có hỗ trợ trả kết quả từ native query cập nhật. Những DBMS/provider khác có thể cần câu lệnh và cách lấy giá trị khác. Bản production còn cần kiểm tra đầu vào, xử lý counter chưa khởi tạo, giới hạn serial, quyền phát hành, trạng thái draft và idempotency.

Lưu ý khi sử dụng:

- `@Transactional` của Spring quản lý transaction cho lời gọi service được thực hiện qua Spring proxy phù hợp; self-invocation có thể bỏ qua transaction advice theo cấu hình proxy thông thường.
- Không dùng `em.getTransaction().begin()` trực tiếp trong service do Spring quản lý transaction.
- `em.flush()` không phải commit: nó đồng bộ SQL nhưng thay đổi vẫn có thể rollback.
- Không gửi email hoặc gọi API cổng thanh toán bên trong transaction rồi kỳ vọng rollback DB sẽ hoàn tác được các tác động bên ngoài.
- Nếu gọi qua transaction manager cho một database khác counter, bảo đảm transaction liên kết đúng cùng nguồn dữ liệu; nhiều persistence unit không tự động tạo một transaction phân tán thống nhất.

### 9.1. Vì sao không dùng @GeneratedValue cho serial nghiệp vụ?

`@GeneratedValue` giải quyết cơ chế sinh **định danh entity**. Nó không cung cấp một hợp đồng generic rằng field thường như `serialNo` được cấp gapless trong một transaction phát hành. Thiết kế trên giữ:

- `id` do DB/JPA sinh.
- `serialNo` do service nghiệp vụ cấp khi phát hành.
- Unique constraint bảo vệ tránh trùng.
- Counter row giao dịch bảo vệ tính liên tục trong scope.
- Lịch sử trạng thái bảo vệ audit.

Cách phân tầng này giúp nhà phát triển nói rõ hệ thống cam kết điều gì.

## 10. Retry và idempotency

Giả sử API phát hành hóa đơn:

~~~text
Client gửi request A.
Server commit hóa đơn số 158 thành công.
HTTP response bị mất do lỗi mạng.
Client gửi lại cùng yêu cầu.
~~~

Nếu mỗi lần gọi đều tạo chứng từ mới, retry sẽ phát hành thêm số 159 cho cùng hành động. Không có khoảng trống, nhưng có **hai chứng từ nghiệp vụ** không mong muốn.

Giải pháp phổ biến là **idempotency key**: mỗi yêu cầu phát hành có khóa nghiệp vụ ổn định; server lưu khóa cùng kết quả, sau đó trả lại kết quả cũ khi gặp retry.

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE issued_invoices
ADD COLUMN idempotency_key VARCHAR(100);

CREATE UNIQUE INDEX uq_issued_invoice_request
ON issued_invoices (idempotency_key)
WHERE idempotency_key IS NOT NULL;
~~~

Quy trình:

1. Nhận request có idempotency key duy nhất cho một hành động.
2. Kiểm tra đã có chứng từ commit với key đó chưa; nếu có, trả mã cũ.
3. Nếu chưa có, tiến hành phát hành trong transaction; unique constraint bảo vệ hai request song song.
4. Nếu bị unique conflict, rollback transaction thất bại rồi đọc kết quả đã commit trong một transaction mới.
5. Nếu key cũ được gửi lại với payload khác, dùng quy tắc báo conflict thay vì âm thầm dùng lại.

Không chỉ kiểm tra `SELECT chưa thấy key` ở ứng dụng: hai request đồng thời có thể cùng không thấy. **Database unique constraint là hàng rào cuối cùng**.

Để gửi event, email hoặc cập nhật hệ thống khác sau phát hành, có thể dùng transactional outbox: ghi bản ghi sự kiện vào DB cùng transaction, rồi worker xử lý sau commit và có retry idempotent. Một transaction local không thể hoàn tác email đã gửi.

## 11. Chứng từ hủy: giữ số hay lấp số?

Một hóa đơn đã phát hành số 159 sau đó bị hủy. Nếu xóa luôn hàng đó, bảng chỉ còn 158, 160 và nhìn thấy gap. Nếu giữ bản ghi trạng thái `VOID`, sổ phát hành vẫn có số 159 và giải thích được tình trạng của nó.

Ví dụ:

| Serial | Status | Ý nghĩa |
|---:|---|---|
| 158 | ISSUED | Đã phát hành và có hiệu lực theo quy trình |
| 159 | VOID | Đã phát hành rồi hủy, còn lịch sử |
| 160 | ISSUED | Đã phát hành tiếp theo |

Đối với các hệ thống cần audit, thường không cho phép tùy ý xóa hoặc đổi số chứng từ sau phát hành. Có thể cần lưu người thao tác, thời điểm, lý do hủy và quy tắc tạo chứng từ điều chỉnh/thay thế. Yêu cầu pháp lý cụ thể về phát hành, hủy, sửa hoặc lấp số phụ thuộc loại chứng từ và khu vực hoạt động; phải xác minh trước khi xây dựng chính sách.

Cần phân biệt:

- **Chứng từ đã được cấp số nhưng sau đó VOID:** không đồng nghĩa số chưa từng tồn tại.
- **Transaction phát hành rollback:** counter transactional không cần giữ số đó vì chưa có phát hành commit.
- **Bản nháp bị xóa:** không tiêu thụ số nếu hệ thống chỉ cấp số lúc phát hành.
- **Một số bị thiếu do thao tác quản trị sai:** cần điều tra nguồn dữ liệu và audit, không tự thêm chứng từ giả để trám số.

## 12. Có nên tái sử dụng hoặc đổi những ID đã bỏ qua?

Thông thường không. Một ID đã được cấp có thể từng xuất hiện trong:

- URL hoặc đường dẫn API.
- Cache, log, audit và event.
- Foreign key hoặc dữ liệu ở hệ thống đối tác.
- File xuất hoặc báo cáo.
- Yêu cầu gửi lại từ client sau timeout.

Tái sử dụng ID có thể làm hệ thống hiểu nhầm đối tượng cũ là đối tượng mới. Đánh lại primary key cho “liền số” có nguy cơ phá vỡ quan hệ và lịch sử. Khóa chính kỹ thuật nên được coi là một danh tính ổn định, không phải dòng đánh số thứ tự.

Cũng không nên tự giảm sequence sau rollback:

~~~text
Transaction A lấy 200 rồi rollback.
Transaction B đã lấy 201 và đang thực hiện.
A cố giảm sequence về 200.
=> Có thể trùng hoặc xung đột với giá trị đã cấp cho B.
~~~

Không có lời đảm bảo rằng “số cuối cùng vừa cấp” vẫn có thể lấy lại an toàn trong môi trường concurrent.

### 12.1. Khởi tạo lại sequence sau import cần thận trọng

Khi nhập dữ liệu lịch sử có ID sẵn, sequence có thể chưa được điều chỉnh theo bảng. Nhưng việc lấy `MAX(id)` và sửa sequence tùy tiện khi các writer còn hoạt động có thể gây trùng ID hoặc mất giá trị đã dự trữ.

Cần thực hiện thay đổi theo một quy trình migration có kiểm soát, hiểu sequence cache/optimizer và phối hợp các instance cùng ghi. Mục đích là **bảo đảm không trùng ID về sau**, không phải làm dãy số đẹp.

## 13. Sắp xếp theo ID không phải thứ tự thời gian chính xác

Đôi khi người phát triển viết:

~~~sql
SELECT * FROM purchase_orders ORDER BY id DESC;
~~~

Câu này chỉ sắp xếp theo ID. Nó không bảo đảm thứ tự commit, thanh toán hay phát hành khi có transaction concurrent hoặc sinh ID theo nhóm.

Nếu giao diện muốn hiển thị theo thời điểm tạo:

~~~sql
SELECT *
FROM purchase_orders
ORDER BY created_at DESC, id DESC;
~~~

`id` ở đây chỉ là tiêu chí phụ giúp ổn định sắp xếp khi timestamp bằng nhau. Muốn phản ánh đúng thời điểm “hoàn tất” một nghiệp vụ, cần có trường sự kiện phù hợp (ví dụ `paid_at`, `issued_at`) và xác định khi nào trường đó được ghi. Thời gian ghi tại ứng dụng trước commit cũng không tự tương đương với commit timestamp trong database.

Trong hệ thống nhiều node, đồng hồ hệ thống có thể lệch; vì vậy nếu thứ tự commit tuyệt đối có ý nghĩa quan trọng, cần một cơ chế ghi nhận/ordering được thiết kế và điều phối phù hợp.

## 14. Hệ thống nhiều node và nhiều database

Một counter trong bộ nhớ Java không đáp ứng yêu cầu số duy nhất toàn hệ thống:

~~~java
AtomicLong next = new AtomicLong(1);
~~~

Hai instance có thể cùng bắt đầu từ 1; restart làm mất trạng thái; một tăng counter trong bộ nhớ không tự rollback cùng transaction database.

Nếu có nhiều node dùng **cùng một database**, row counter transactional có thể bảo vệ chuỗi phát hành chung. Nhưng khi hai vùng dùng **hai database độc lập**, chúng không có chung transaction và row lock:

~~~text
Service A -> Database A
Service B -> Database B

Cả hai cùng phát hành vào dãy INV-2026-...
~~~

Cần chọn một cơ chế phối hợp:

- Dịch vụ phát hành tập trung với nguồn lưu trữ nhất quán.
- Chuỗi riêng theo scope nghiệp vụ thực sự cho phép.
- Hàng đợi phát hành tuần tự trong từng scope, đi cùng lưu trữ bền vững, transaction và idempotency.
- Mô hình xử lý giao dịch phân tán hoặc đối soát phù hợp kiến trúc.

Yêu cầu gapless toàn cục là một yêu cầu **serialization** khó kết hợp với khả năng xử lý độc lập, thông lượng rất cao và tiếp tục vận hành trong mọi tình huống mất kết nối. Phải cân nhắc các trade-off thực tế.

## 15. Các ngộ nhận thường gặp

### “INCREMENT BY 1 thì không có khoảng trống”

Sai. `INCREMENT BY 1` mô tả bước của sequence, không bảo đảm giá trị nào cũng có hàng commit. Rollback hoặc cache vẫn làm dãy ID thiếu số.

### “Đặt allocationSize = 1 là xử lý triệt để”

Không. Nó chỉ loại bỏ hoặc giảm một loại preallocation ở provider. Lỗi insert, rollback, restart và concurrency vẫn tồn tại; giảm allocation có thể làm giảm hiệu năng.

### “Có gap tức là chắc chắn bị xóa đơn”

Không. Gap có thể xuất hiện ngay cả khi chưa từng commit bất kỳ hàng nào mang số đó. Phải dựa vào audit, log, trạng thái và migration để điều tra.

### “Khóa chính cần đúng thứ tự commit”

JPA không đưa ra cam kết đó. Sequence có thể cấp số trước commit; transaction có ID lớn hơn có thể commit trước.

### “Dùng GenerationType.TABLE sẽ tự gapless”

Không nên giả định. `TABLE` là chiến lược sinh ID do JPA provider quản lý, thường cũng có các cơ chế tối ưu và cấp phát; semantics rollback và allocator không phải một hợp đồng nghiệp vụ phát hành chứng từ.

### “Dùng MAX(id)+1 sẽ không thiếu số”

Sai dưới concurrency. Hai transaction cùng thấy MAX có thể chọn cùng ID. Unique constraint chỉ giúp từ chối trùng, không tự làm protocol cấp số an toàn.

### “Chỉ cần UNIQUE(serial_no) là dãy không thể thiếu số”

Sai. Unique chỉ ngăn trùng. Một hệ thống có các serial 1, 2, 4, 7 vẫn thỏa mãn UNIQUE.

### “Nếu muốn gapless thì lấy lại số từng rollback từ sequence”

Nguy hiểm. Có thể các transaction khác đã được cấp số mới. Việc sửa generator trực tiếp có nguy cơ trùng khóa và hỏng quan hệ.

### “Một mã tự tăng cho biết chính xác doanh thu/số giao dịch”

Không. Sequence có thể bỏ số, transaction rollback, nhiều bản ghi được import hoặc xóa; không suy ra số giao dịch thành công từ hiệu hai ID.

## 16. Quy trình ra quyết định

Khi thiết kế mã định danh trong ứng dụng JPA, có thể làm theo những bước sau:

1. **Xác định loại mã.** ID của entity, mã người dùng tra cứu hay số chứng từ phát hành?
2. **Định nghĩa phạm vi duy nhất.** Toàn hệ thống, tenant, chi nhánh, loại chứng từ hay năm tài chính?
3. **Thống nhất tính liên tục.** Thật sự cần gapless hay chỉ cần unique và dễ tra cứu?
4. **Chỉ rõ thời điểm cấp số.** Khi tạo draft, khi xác nhận hay khi commit phát hành?
5. **Xác định hành vi lỗi.** Rollback, retry, timeout, crash và hủy sau commit?
6. **Chọn cơ chế.** `@GeneratedValue` cho PK; counter transactional và state machine nếu có yêu cầu gapless nghiệp vụ.
7. **Đặt constraint ở database.** PK, UNIQUE theo scope và các kiểm tra bắt buộc.
8. **Thiết kế audit và idempotency.** Giữ số VOID; cùng request không được cấp hai serial.
9. **Đánh giá throughput.** Một row counter tạo điểm chờ; chia scope chỉ khi nghiệp vụ cho phép.
10. **Quy định migration/operations.** Khởi tạo counter đầu kỳ, giám sát serial, quản lý quyền sửa dữ liệu và xử lý sai lệch.

### Bảng chọn chiến lược

| Nhu cầu | Lựa chọn phù hợp | Ghi chú |
|---|---|---|
| Entity CRUD thông thường | `IDENTITY` hoặc `SEQUENCE` | Gap được chấp nhận |
| Tối ưu ghi với sequence | `SEQUENCE`, optimizer phù hợp | Cần cấu hình generator và DB nhất quán |
| Mã tra cứu đơn hàng unique, dễ đọc | ID/UUID hoặc mã riêng + format | Không hứa gapless |
| Chuỗi chứng từ đã commit phải liên tục theo năm | Counter row transactional + unique + audit | Chấp nhận lock serialization |
| Một request phát hành có thể retry | Idempotency key và kết quả lưu bền vững | Trả số cũ khi retry |
| Nhiều DB cùng chia sẻ một chuỗi | Cơ chế phát hành tập trung hoặc chia scope hợp lệ | Không có row lock chung tự động |
| Mã bị hủy nhưng vẫn cần audit | Giữ bản ghi với trạng thái VOID | Không reuse serial |

## 17. Bài tập thực hành

### Bài tập 1 — Sequence rollback

Một sequence PostgreSQL bắt đầu từ 1. Transaction A lấy số 1 rồi rollback; transaction B lấy số 2 rồi commit. Hãy cho biết số 1 có được trả lại không và việc chỉ thấy hàng ID 2 có chứng minh một hàng ID 1 từng bị xóa hay không.

**Gợi ý:** `nextval()` không rollback; việc thiếu hàng ID 1 không đủ chứng minh có thao tác DELETE.

### Bài tập 2 — Hai giao dịch đồng thời

Transaction A nhận ID 10 và xử lý chậm; B nhận ID 11 và commit trước. Nếu UI sắp theo ID tăng dần, có thể suy ra thứ tự hoàn tất nghiệp vụ hay không?

**Gợi ý:** Không. Thứ tự ID và thứ tự commit là hai khái niệm khác nhau.

### Bài tập 3 — Mã hóa đơn theo năm

Doanh nghiệp muốn mã `INV-2026-000001` và `INV-2026-000002`, bắt đầu lại từ 1 vào năm 2027. Hãy thiết kế PK nội bộ, khóa unique nghiệp vụ, counter theo năm, thời điểm phát hành và trạng thái của chứng từ bị hủy.

**Gợi ý:** Tách `id` khỏi `(fiscal_year, serial_no)`; chỉ cấp serial trong transaction phát hành; dùng trạng thái VOID để giữ lịch sử.

### Bài tập 4 — MAX + 1

Hai request đồng thời cùng đọc serial lớn nhất là 57. Cả hai định insert 58. Hãy mô tả race condition và vì sao unique constraint không tự biến MAX+1 thành thuật toán cấp số đầy đủ.

### Bài tập 5 — Mất HTTP response

Server đã commit hóa đơn 75 nhưng client không nhận được phản hồi và retry. Thiết kế cách server trả lại số 75 thay vì tạo số 76 cho cùng một yêu cầu.

**Gợi ý:** Idempotency key lưu trong DB với unique constraint, kết quả phát hành được ghi bền vững và cơ chế đọc lại khi retry.

## 18. Ghi nhớ

- **ID của JPA entity cần duy nhất, không bắt buộc liên tục.**
- `IDENTITY` và `SEQUENCE` có thể bỏ số vì rollback, insert lỗi, cache, allocation, restart và concurrency.
- `allocationSize = 1` và `INCREMENT BY 1` không bảo đảm gapless.
- **Không suy ra thứ tự commit hoặc số đơn thành công từ dãy ID.**
- Mã nghiệp vụ cần quy tắc riêng: scope, thời điểm cấp, trạng thái hủy, retry, và tính duy nhất.
- Với chuỗi phát hành đã commit cần liên tục, có thể dùng **counter row cập nhật trong cùng transaction** với chứng từ, chấp nhận lock contention và throughput trade-off.
- **UNIQUE ngăn trùng; transaction gắn counter với chứng từ; idempotency ngăn trùng hành động; audit/VOID giải thích lịch sử.**
- Không tự giảm sequence, tái sử dụng hoặc renumber primary key để lấp chỗ trống.
- Với hóa đơn/chứng từ chịu quy định pháp lý, phải xác minh yêu cầu đánh số và xử lý hủy cụ thể trước khi đưa giải pháp vào production.

Phân biệt rõ **khóa chính kỹ thuật** và **số nghiệp vụ** giúp ứng dụng vừa sử dụng cơ chế ORM sinh ID hiệu quả, vừa đáp ứng yêu cầu quản trị có chủ đích. Khoảng trống ở ID là bình thường; tính liên tục chỉ nên được cam kết khi chuỗi phát hành đã có transaction, ràng buộc và vòng đời nghiệp vụ phù hợp.
