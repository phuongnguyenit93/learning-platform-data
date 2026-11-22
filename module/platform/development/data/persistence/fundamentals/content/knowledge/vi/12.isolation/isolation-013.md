# Vì sao cùng tên mức cô lập vẫn cần kiểm tra hành vi của từng hệ quản trị

Hai hệ quản trị cơ sở dữ liệu cùng hỗ trợ mức cô lập `READ COMMITTED` hoặc `REPEATABLE READ` không có nghĩa hai ứng dụng sẽ quan sát cùng một kết quả khi giao dịch chạy đồng thời. Tên mức cô lập mô tả một **mức cam kết về hành vi**, còn cách thực hiện có thể dựa trên khóa, phiên bản dữ liệu (MVCC), ảnh chụp dữ liệu (snapshot), khóa phạm vi hay cơ chế phát hiện xung đột. Một hệ quản trị có thể ngăn được một hiện tượng mà tên mức cô lập theo cách diễn giải truyền thống vẫn cho phép; hệ khác có thể chặn truy vấn hoặc yêu cầu thử lại giao dịch.

Với ứng dụng Java, khác biệt này ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ: cùng một đoạn mã kiểm tra tồn kho, đặt lịch hoặc chuyển trạng thái có thể chạy đúng ở môi trường kiểm thử nhưng vi phạm điều kiện nghiệp vụ khi đổi hệ quản trị hoặc cấu hình. Bài học thuộc chương **Tính cô lập** của **DATA_PERSISTENCE_FUNDAMENTALS** tập trung vào cách hiểu tên mức cô lập, kiểm tra kết quả thực tế và thiết kế ranh giới persistence phù hợp.

## 1. Tên mức cô lập nói lên điều gì?

*Isolation* là chữ **I** trong ACID. Mục đích của nó là kiểm soát những gì một giao dịch có thể quan sát khi giao dịch khác đang đọc hoặc ghi. Các thuật ngữ thường gặp:

| Hiện tượng | Ví dụ hai giao dịch | Rủi ro |
| --- | --- | --- |
| **Dirty read** | A đọc giá trị B đã sửa nhưng B chưa commit; sau đó B rollback. | A sử dụng dữ liệu chưa từng trở thành dữ liệu chính thức. |
| **Non-repeatable read** | A đọc một hàng; B sửa hàng và commit; A đọc lại cùng hàng thấy giá trị khác. | Hai lần đọc cùng điều kiện cho kết quả khác nhau. |
| **Phantom read** | A đếm hàng khớp điều kiện; B thêm/xóa một hàng phù hợp và commit; A đếm lại thấy tập hàng thay đổi. | Truy vấn theo tập/predicate cho số lượng khác. |
| **Lost update** | A và B cùng đọc một giá trị, mỗi bên tính giá trị mới rồi ghi đè dựa trên giá trị cũ. | Một cập nhật nghiệp vụ bị mất; mức bảo vệ phụ thuộc kiểu cập nhật và DB. |
| **Write skew** | A và B cùng đọc một điều kiện trên nhiều hàng rồi cập nhật **hai hàng khác nhau**; cả hai commit khiến điều kiện chung bị vi phạm. | Không nhất thiết có xung đột ghi trên cùng một hàng nên khóa hàng đơn lẻ không đủ. |

Theo cách trình bày kinh điển về bốn mức cô lập SQL, có thể dùng bảng định hướng sau. “Có thể” không có nghĩa hệ quản trị nào cũng cho hiện tượng đó xảy ra:

| Tên mức | Ý nghĩa tối thiểu thường được dạy | Điều chưa thể kết luận từ tên |
| --- | --- | --- |
| `READ UNCOMMITTED` | Cho phép các hiện tượng đọc yếu, bao gồm dirty read theo mô hình truyền thống. | Một số DB thực tế vẫn **không** cho đọc dữ liệu chưa commit. |
| `READ COMMITTED` | Ngăn dirty read; mỗi lần đọc chỉ thấy dữ liệu đã commit theo quy tắc của DB. | Hai câu `SELECT` trong cùng transaction có cùng snapshot hay không; đọc có khóa hay dùng version. |
| `REPEATABLE READ` | Ngăn dirty read và non-repeatable read theo phân loại truyền thống. | Có ngăn phantom, write skew hay không; `SELECT` bình thường khác `SELECT ... FOR UPDATE` thế nào. |
| `SERIALIZABLE` | Các giao dịch **commit** phải có kết quả tương đương với một lịch thực thi tuần tự hợp lệ. | DB dùng khóa để chặn hay cho chạy rồi hủy một giao dịch; lỗi xuất hiện khi đọc, ghi hay commit. |

**Snapshot isolation (SI)** là một cơ chế quan trọng nhưng không phải một trong bốn tên mức SQL nói trên. Một giao dịch thường đọc một snapshot ổn định và việc ghi lên cùng hàng có thể dẫn đến xung đột; tuy nhiên hai giao dịch cập nhật các hàng khác nhau vẫn có thể gây **write skew**. Do đó **snapshot ổn định không tự động đồng nghĩa với serializable**.

Định nghĩa “tương đương tuần tự” không bảo đảm mọi giao dịch sẽ thành công: hệ quản trị có thể chủ động hủy một giao dịch để giữ tính cô lập. Ứng dụng phải biết xử lý kết quả hủy và thử lại *toàn bộ giao dịch* khi phù hợp.

## 2. Vì sao triển khai khác nhau tạo ra hành vi khác nhau?

Hãy phân biệt ba cơ chế chính:

1. **Khóa (locking):** truy vấn đọc hoặc ghi có thể lấy khóa trên hàng, khóa hoặc khoảng khóa, khiến giao dịch khác phải đợi. Thời điểm giải phóng khóa tùy mức cô lập và loại thao tác.
2. **MVCC và snapshot:** cơ sở dữ liệu lưu các phiên bản hàng để một truy vấn đọc phiên bản phù hợp mà không nhất thiết chặn người ghi. Snapshot có thể được chọn **cho từng câu lệnh** hoặc **cho cả giao dịch**.
3. **Phát hiện xung đột/kiểm tra khả tuần tự:** DB có thể giám sát phụ thuộc đọc–ghi, từ chối một cập nhật hoặc hủy giao dịch ở thời điểm commit để không công nhận lịch chạy không hợp lệ.

```text
Hai phiên A và B đọc/ghi đồng thời
            |
            v
  Mức cô lập được yêu cầu
            |
            v
  Cách DB triển khai mức đó
   - Khóa và thời gian giữ khóa
   - Snapshot từng lệnh hay cả transaction
   - Kiểm tra xung đột, khóa phạm vi/predicate
            |
            v
  Quan sát thực tế
   - Kết quả SELECT có đổi không?
   - Truy vấn có phải chờ không?
   - UPDATE/COMMIT có bị từ chối không?
```

Vì vậy, kiểm tra tính đúng đắn phải dựa trên **đặc tả sản phẩm, phiên bản, cấu hình và kết quả chạy đồng thời**, chứ không dừng ở việc đọc tên mức cô lập hoặc thấy JDBC trả về một hằng số tương ứng.

## 3. Cùng tên nhưng khác hành vi: các hệ quản trị phổ biến

Bảng dưới đây minh họa những khác biệt đáng kiểm tra. Đây là nhận định về các cơ chế thông dụng; hành vi chi tiết vẫn phụ thuộc phiên bản, engine lưu trữ, câu SQL và cấu hình.

| Hệ quản trị | Điều đáng chú ý |
| --- | --- |
| **PostgreSQL** | Yêu cầu `READ UNCOMMITTED` thực tế hoạt động như `READ COMMITTED`. `READ COMMITTED` dùng snapshot mới cho từng câu lệnh. `REPEATABLE READ` dựa trên snapshot ổn định, không nhìn thấy phantom trong các truy vấn thường, nhưng vẫn có thể xảy ra write skew. `SERIALIZABLE` dùng cơ chế SSI để phát hiện lịch không khả tuần tự và có thể trả lỗi `40001`. |
| **MySQL / InnoDB** | `REPEATABLE READ` thường là mặc định của InnoDB; các **consistent read** (`SELECT` thông thường) dùng snapshot được thiết lập ở lần đọc nhất quán đầu tiên trong transaction. Nhưng `SELECT ... FOR UPDATE` và thao tác ghi dùng cơ chế đọc/khóa theo trạng thái hiện hành; khóa next-key/gap ảnh hưởng đến truy vấn phạm vi. `READ COMMITTED` thường tạo snapshot mới cho từng consistent read. |
| **SQL Server** | `READ COMMITTED` có thể đọc bằng khóa hoặc dùng row versioning tùy tùy chọn database `READ_COMMITTED_SNAPSHOT` (RCSI). `SNAPSHOT` là mức riêng, không đồng nghĩa với `REPEATABLE READ`. `SERIALIZABLE` thường sử dụng khóa phạm vi để bảo vệ predicate; kiểu chờ khóa và lỗi khác cơ chế PostgreSQL SSI. |
| **Oracle Database** | `READ COMMITTED` cho ảnh chụp nhất quán ở mức câu lệnh. `SERIALIZABLE` có chế độ nhìn dữ liệu nhất quán theo transaction và có thể trả lỗi `ORA-08177` khi không thể tuần tự hóa quyền truy cập. Không nên suy hành vi khóa/xung đột từ cách PostgreSQL triển khai tên tương tự. |
| **SQLite** | Không trình bày đầy đủ bốn mức theo cùng giao diện với các DB trên. Ở chế độ WAL, reader có snapshot còn writer được tuần tự hóa (mỗi thời điểm chỉ có một writer); chuyển một snapshot đọc cũ thành giao dịch ghi có thể nhận `SQLITE_BUSY_SNAPSHOT`. |

### 3.1. PostgreSQL: REPEATABLE READ mạnh hơn bảng hiện tượng cổ điển ở một điểm, yếu hơn SERIALIZABLE ở điểm khác

Trong PostgreSQL, `REPEATABLE READ` giữ ảnh chụp ổn định trong giao dịch nên việc chạy lại `SELECT COUNT(*) ...` thông thường sẽ không nhìn thấy những hàng mới do giao dịch khác commit. Tuy nhiên, hai giao dịch có thể cùng dựa trên thông tin cũ để sửa **các hàng khác nhau**, cùng commit, và làm sai điều kiện trên toàn tập dữ liệu. Đây là lý do *không thấy phantom* vẫn chưa đủ kết luận *khả tuần tự*.

Với `SERIALIZABLE`, PostgreSQL theo dõi các quan hệ phụ thuộc nguy hiểm theo SSI (*Serializable Snapshot Isolation*) và hủy một giao dịch khi cần. Ứng dụng nhận lỗi serialization phải chạy lại các phép đọc và quyết định nghiệp vụ, không chỉ lặp câu `UPDATE` cuối cùng.

### 3.2. MySQL/InnoDB: SELECT thông thường khác locking read

Trong InnoDB, câu `SELECT` không gắn khóa thường là **consistent read**, còn `SELECT ... FOR UPDATE` là **locking read**. Dưới `REPEATABLE READ`, hai câu đọc bình thường có thể nhìn cùng một snapshot trong khi một câu locking read phải xét trạng thái cập nhật mới hơn, lấy khóa và có thể chờ giao dịch khác. Do đó không nên phát biểu “mọi câu SELECT ở REPEATABLE READ luôn nhìn một dữ liệu giống nhau” mà không chỉ rõ **loại SELECT**.

Ví dụ mô hình:

```sql
-- Trong InnoDB, cần xét các câu dưới trong transaction đang mở.
SELECT status FROM orders WHERE order_id = 10;
SELECT status FROM orders WHERE order_id = 10 FOR UPDATE;
```

Khi giải thích hai kết quả có thể khác nhau, hãy kiểm tra có writer khác commit giữa các thời điểm, loại read, index được dùng và thời điểm snapshot được tạo. Next-key locking giúp bảo vệ nhiều truy vấn theo khoảng nhưng còn phụ thuộc đường truy cập và mức cô lập; không suy ra rằng mọi điều kiện nghiệp vụ đa hàng đều được bảo vệ hoàn toàn ở `REPEATABLE READ`.

### 3.3. SQL Server: chỉ một tùy chọn database đã thay đổi cách READ COMMITTED hoạt động

Khi `READ_COMMITTED_SNAPSHOT` tắt, cách thực thi phổ biến của `READ COMMITTED` là dùng shared lock cho các đọc, có thể chặn/đợi writer theo thời điểm. Khi bật RCSI, các `SELECT` ở `READ COMMITTED` thường đọc phiên bản đã commit ở đầu câu lệnh, giảm va chạm reader–writer. Cả hai cùng mang tên **READ COMMITTED** nhưng đặc điểm blocking, độ trễ và thời điểm quan sát khác nhau.

Điều này không làm cho RCSI trở thành snapshot của **toàn bộ transaction**; đó vẫn là ảnh chụp theo câu lệnh. Mức `SNAPSHOT` riêng của SQL Server có quy tắc khác và cần xem cả cấu hình `ALLOW_SNAPSHOT_ISOLATION`.

## 4. Thí nghiệm 1: đọc một hàng hai lần

Để quan sát bằng chứng thay vì đoán theo tên, dùng hai kết nối riêng (**A** và **B**) trên PostgreSQL. Chuẩn bị dữ liệu thử nghiệm:

```sql
CREATE TABLE account_balance (
    account_id INT PRIMARY KEY,
    balance    INT NOT NULL
);
INSERT INTO account_balance (account_id, balance)
VALUES (1, 100);
```

Thực hiện **đúng thứ tự** sau (mỗi phiên giữ kết nối/transaction riêng):

| Bước | Phiên A | Phiên B |
| --- | --- | --- |
| 1 | `BEGIN ISOLATION LEVEL READ COMMITTED;` | |
| 2 | `SELECT balance FROM account_balance WHERE account_id = 1;` → 100 | |
| 3 | | `UPDATE account_balance SET balance = 120 WHERE account_id = 1;`, sau đó `COMMIT` nếu B đã mở transaction riêng; hoặc chạy một lệnh `UPDATE` ở auto-commit. |
| 4 | Chạy lại `SELECT balance ...` → 120 ở PostgreSQL `READ COMMITTED` | |
| 5 | `ROLLBACK;` | |

Đặt lại `balance = 100`, sau đó lặp lại ở A với `BEGIN ISOLATION LEVEL REPEATABLE READ;`. Ở bước 4, phiên A vẫn thấy **100** từ snapshot ban đầu. Hệ quản trị khác có thể dùng khóa và thời gian chờ khác nhau, kể cả khi cuối cùng kết quả quan sát giống nhau.

Để kiểm tra **phantom**, thay truy vấn đọc hàng bằng:

```sql
SELECT COUNT(*) FROM account_balance WHERE balance >= 100;
```

Cho B thêm một tài khoản có `balance >= 100` rồi commit giữa hai lần đếm. PostgreSQL `READ COMMITTED` có thể cho số đếm tăng; `REPEATABLE READ` giữ số đếm theo snapshot đã thiết lập. Bài thử này chỉ kiểm tra *đọc lại*, chưa kiểm tra việc hai giao dịch cùng cập nhật dựa trên cùng một điều kiện.

## 5. Thí nghiệm 2: write skew mà REPEATABLE READ chưa ngăn được

Giả sử bệnh viện quy định **một ca trực phải luôn có ít nhất một bác sĩ trực**. Có hai bác sĩ A và B, cả hai đang trực. Mỗi bác sĩ được phép xin rời ca nếu kiểm tra thấy vẫn có ít nhất hai người trực tại thời điểm quyết định.

```sql
-- PostgreSQL, chạy khi chưa có bảng demo trùng tên.
CREATE TABLE shift_duty (
    doctor_id INT PRIMARY KEY,
    on_call   BOOLEAN NOT NULL
);
INSERT INTO shift_duty (doctor_id, on_call)
VALUES (1, TRUE), (2, TRUE);
```

Hai phiên thực hiện các câu sau trong **hai giao dịch đồng thời**. Ở mỗi phiên, hãy dừng sau câu `SELECT` để chắc chắn **cả hai đều nhìn thấy 2 người đang trực**, rồi mới cho phép cập nhật.



| Thứ tự | Phiên A (bác sĩ 1) | Phiên B (bác sĩ 2) |
| --- | --- | --- |
| 1 | `BEGIN ISOLATION LEVEL REPEATABLE READ;` | |
| 2 | `SELECT COUNT(*) FROM shift_duty WHERE on_call = TRUE;` → 2 | |
| 3 | | `BEGIN ISOLATION LEVEL REPEATABLE READ;` |
| 4 | | `SELECT COUNT(*) FROM shift_duty WHERE on_call = TRUE;` → 2 |
| 5 | `UPDATE shift_duty SET on_call = FALSE WHERE doctor_id = 1;` | |
| 6 | | `UPDATE shift_duty SET on_call = FALSE WHERE doctor_id = 2;` |
| 7 | `COMMIT;` | |
| 8 | | `COMMIT;` |

Trong PostgreSQL `REPEATABLE READ`, **cả hai giao dịch có thể commit** vì mỗi bên cập nhật một hàng khác nhau. Kết quả:

```sql
SELECT doctor_id, on_call FROM shift_duty ORDER BY doctor_id;
-- 1 | false
-- 2 | false
```

Điều kiện nghiệp vụ bị vi phạm dù từng giao dịch riêng lẻ đã đọc dữ liệu không đổi trong transaction của mình. Đây là **write skew**: hai quyết định phụ thuộc vào cùng một tập dữ liệu nhưng các vùng ghi không giao nhau.

Đặt lại hai hàng về `TRUE`, rồi chạy **cùng lịch xen kẽ** với `BEGIN ISOLATION LEVEL SERIALIZABLE;` ở cả hai phiên. Với PostgreSQL, một giao dịch sẽ bị từ chối vì xung đột serializable (thường là SQLSTATE `40001`, có thể xuất hiện ở lệnh ghi hoặc `COMMIT`). Khi giao dịch thất bại, phải rollback và thử lại từ đầu. Trong lần chạy lại, giao dịch sẽ thấy chỉ còn một bác sĩ trực và không được chấp thuận rời ca.

Không áp dụng máy móc kỳ vọng “chắc chắn sẽ có lỗi `40001`” cho mọi DB: một hệ quản trị khác có thể **chặn** một trong hai transaction, phát hiện deadlock, hoặc thực thi cơ chế snapshot/locking khác. Đó chính là hành vi phải đo và đối chiếu với tài liệu DB đang dùng.

**Chú ý về ràng buộc:** `CHECK (on_call = TRUE)` trên từng hàng không thể diễn đạt yêu cầu “có ít nhất một hàng `on_call = TRUE`”. Có thể cân nhắc thiết kế khóa một hàng đại diện cho ca trực, khóa tường minh, hoặc ràng buộc dữ liệu/luồng nghiệp vụ được kiểm soát ở tầng cơ sở dữ liệu nếu muốn bảo vệ quy tắc mà không lệ thuộc vào việc mọi bên gọi đều chạy cùng một mẫu truy vấn.

## 6. Kiểm tra hành vi như thế nào cho có giá trị?

Một phép thử đồng thời có ý nghĩa cần mô tả **lịch xen kẽ của từng câu lệnh**, không chỉ chạy hai đoạn SQL gần nhau về thời gian. Nếu B hoàn thành trước khi A bắt đầu đọc thì sẽ không tái hiện được write skew. Dùng hai phiên độc lập, đặt mốc dừng ở các bước và ghi lại đầu ra, thời gian chờ cùng lỗi thực tế.

Checklist thực nghiệm:

1. **Chốt môi trường:** tên hệ quản trị, phiên bản, storage engine, chế độ WAL hoặc row versioning, cấu hình isolation ở database và session.
2. **Chốt ranh giới transaction:** dùng hai connection thực sự khác nhau; biết `autoCommit` đang bật/tắt; bắt đầu và kết thúc transaction ở vị trí xác định.
3. **Chốt câu đọc:** `SELECT` thường, `SELECT ... FOR UPDATE`, truy vấn trên index hay full scan có thể kích hoạt cơ chế khác nhau.
4. **Chốt lịch xen kẽ:** A đọc → B đọc → A ghi → B ghi → commit; với bài thử non-repeatable/phantom thì B phải commit **giữa hai lần đọc của A**.
5. **Ghi lại cả thành công lẫn thất bại:** giá trị đọc được, thao tác nào bị block, timeout, deadlock, serialization failure hoặc lỗi khi commit.
6. **Đặt lại dữ liệu trước lần thử tiếp:** chạy dưới từng mức cô lập; lặp nhiều lần nếu cần vì bộ lập lịch và thời điểm lấy khóa ảnh hưởng kết quả.

Có thể kiểm tra mức transaction đã chọn bằng các công cụ phù hợp:

```sql
-- PostgreSQL: giá trị isolation hiện hành.
SHOW transaction_isolation;

-- MySQL/InnoDB (các phiên bản hỗ trợ biến này):
SELECT @@transaction_isolation;
```

Ở SQL Server, cần kiểm tra cả cài đặt của database như `READ_COMMITTED_SNAPSHOT` và mức session; ở SQLite, cần kiểm tra journal mode, shared-cache và cách kết nối được tạo. Một nhãn isolation trong log **không thay thế** việc đo kết quả thực tế. Khi kiểm thử, cũng nên xem chính sách chờ khóa, timeout và retry vì chúng là phần quan trọng của hành vi người dùng.

### Bảng kết luận từ thí nghiệm

| Tình huống | Điều có thể quan sát | Cần xác minh ở DB đích |
| --- | --- | --- |
| A đọc một hàng, B sửa rồi commit, A đọc lại | Giá trị đổi hoặc giữ nguyên | Snapshot theo statement/transaction; lock có giữ đến cuối giao dịch không |
| A đếm một tập, B chèn hàng phù hợp, A đếm lại | Phantom xuất hiện hoặc không | Snapshot, khóa phạm vi và loại câu đọc |
| A/B đọc cùng điều kiện rồi ghi hai hàng khác nhau | Cả hai commit, một bên chờ hoặc một bên bị hủy | Có cơ chế ngăn write skew/serialization anomaly thực sự không |
| A/B cùng sửa một hàng | Khóa chờ, update conflict, deadlock hoặc dữ liệu ghi đè | DB xử lý lost update và write conflict ra sao; có cần cột `version` không |
| A dùng `SELECT ... FOR UPDATE` | Đọc dữ liệu gần nhất theo luật DB, có thể chờ/khóa | Kiểu khóa, phạm vi khóa, mốc giải phóng và khác biệt với `SELECT` thường |

## 7. Thiết kế ranh giới giao dịch trong Java

JDBC cung cấp các hằng số `Connection.TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ` và `TRANSACTION_SERIALIZABLE`. Chúng biểu thị **mức được yêu cầu**, không xác nhận rằng mọi DB xử lý predicate, phantom hay write skew giống nhau. Có thể kiểm tra hỗ trợ qua `DatabaseMetaData.supportsTransactionIsolationLevel(...)` và đọc mức đã cấu hình bằng `getTransactionIsolation()`; sau đó vẫn phải thử hành vi.

Ví dụ dưới dùng **PostgreSQL** và quy tắc ca trực ở phần trước. Service tự lấy kết nối từ `DataSource`, yêu cầu `SERIALIZABLE`, đọc số người đang trực, cập nhật một người rồi commit. Nếu xảy ra serialization failure `40001`, toàn bộ quyết định được tính lại trong **một transaction mới**.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ShiftService {
    private final DataSource dataSource;

    public ShiftService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean leaveShift(int doctorId) throws SQLException {
        final int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            // Mỗi lần thử dùng một kết nối và một transaction mới.
            try (Connection c = dataSource.getConnection()) {
                // Đặt isolation trước câu SQL đầu tiên của transaction.
                c.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
                c.setAutoCommit(false);

                try {
                    int onDutyCount;
                    try (PreparedStatement ps = c.prepareStatement(
                            "SELECT COUNT(*) FROM shift_duty WHERE on_call = TRUE");
                         ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        onDutyCount = rs.getInt(1);
                    }

                    if (onDutyCount <= 1) {
                        c.rollback();
                        return false;
                    }

                    int affected;
                    try (PreparedStatement ps = c.prepareStatement(
                            "UPDATE shift_duty SET on_call = FALSE " +
                            "WHERE doctor_id = ? AND on_call = TRUE")) {
                        ps.setInt(1, doctorId);
                        affected = ps.executeUpdate();
                    }

                    if (affected != 1) {
                        c.rollback();
                        return false;
                    }

                    c.commit();
                    return true;
                } catch (SQLException failure) {
                    boolean rolledBack = true;
                    try {
                        c.rollback();
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                        rolledBack = false;
                    }

                    // PostgreSQL: chỉ thử lại một giao dịch đã được
                    // xác nhận thất bại vì serialization conflict.
                    if (rolledBack
                            && "40001".equals(failure.getSQLState())
                            && attempt < maxAttempts) {
                        continue;
                    }
                    throw failure;
                }
            }
        }
        throw new IllegalStateException("Đã vượt quá số lần thử lại");
    }
}
```

Trong ví dụ này, nếu hai bác sĩ đồng thời xin rời ca, một transaction có thể bị hủy; vòng lặp chạy lại toàn bộ bước đọc số người, kiểm tra điều kiện và cập nhật. Nếu sau lần commit đầu tiên chỉ còn một người trực, lần retry trả về `false`. Mã chỉ coi `40001` là lỗi có thể thử lại **theo quy ước PostgreSQL**; deadlock, mất kết nối và lỗi commit không rõ kết quả cần chính sách riêng.

Một số điều kiện triển khai thực tế:

- **Ranh giới sở hữu:** chỉ tầng có quyền quản lý transaction mới quyết định `setAutoCommit(false)`, `commit`, `rollback` và thay isolation. Nếu transaction do Spring hoặc tầng gọi sở hữu, không tự thay mức cô lập của connection đang được dùng chung.
- **Không phát sinh side effect trước commit:** mỗi lần retry sẽ chạy lại logic. Nếu vòng lặp gửi email, trừ tiền qua API bên ngoài hay publish trực tiếp một sự kiện, retry có thể tạo tác động lặp. Tách side effect bằng outbox hoặc cơ chế idempotency phù hợp.
- **Phân loại lỗi theo DB:** SQLSTATE `40001` là ví dụ cho serialization failure ở PostgreSQL. Các DB và driver khác có mã lỗi, deadlock và hành vi commit khác; không dùng một bộ phân loại chung mà chưa kiểm chứng.
- **Không lặp vô hạn:** giới hạn số lần retry, đo số lần xung đột và có chính sách thông báo/trễ thử lại thích hợp. Nếu đã mất kết nối sau khi gửi `COMMIT`, kết quả commit có thể không rõ; cần kiểm tra bằng khóa nghiệp vụ/idempotency trước khi thực hiện lại.
- **Chi phí và lock contention:** `SERIALIZABLE` có thể tăng chờ khóa, deadlock hoặc tỷ lệ giao dịch bị hủy tùy DB. Với hệ thống ghi nhiều, hãy đo trên workload thực tế thay vì chọn mức cao nhất một cách máy móc.

Với Spring, `@Transactional(isolation = Isolation.SERIALIZABLE)` chỉ có ý nghĩa đúng khi transaction manager thực sự thiết lập mức đó cho **transaction mới**. Một phương thức tham gia transaction đã tồn tại có thể thừa hưởng mức của transaction bên ngoài; cấu hình validation có thể phát hiện bất đồng. Retry phải bao quanh điểm bắt đầu transaction mới, không chỉ bao quanh một repository call đang nằm trong transaction đã bị đánh dấu rollback-only.

## 8. Cách chọn giải pháp theo bất biến nghiệp vụ

Thay vì bắt đầu bằng câu hỏi “dùng `REPEATABLE READ` hay `SERIALIZABLE`?”, hãy diễn đạt **bất biến**: điều gì tuyệt đối không được sai sau khi các transaction commit?

| Bất biến / nhu cầu | Cách tiếp cận có thể phù hợp | Điều phải kiểm tra |
| --- | --- | --- |
| Số dư không âm khi trừ tiền | `UPDATE ... SET balance = balance - ? WHERE id = ? AND balance >= ?` và kiểm tra số hàng cập nhật; transaction cho các bút toán liên quan | Điều kiện cập nhật nguyên tử, khóa, lỗi đồng thời và việc hai bút toán có commit cùng nhau |
| Không tạo hai bản ghi cùng khóa nghiệp vụ | `UNIQUE` constraint kết hợp xử lý lỗi trùng khóa hoặc upsert có chủ đích | Khóa bao phủ đúng bất biến, xử lý race khi kiểm tra tồn tại trước khi insert |
| Một ca có ít nhất một người trực | Serializable thực sự, khóa một hàng đại diện, hoặc quy trình đồng bộ được DB bảo vệ | Write skew với hai hàng khác nhau; toàn bộ writer phải tuân thủ quy tắc |
| Cập nhật hàng nếu chưa có người khác sửa | Cột `version` với `UPDATE ... WHERE id = ? AND version = ?` | Phát hiện `affected rows = 0`, tải lại dữ liệu và báo xung đột |
| Danh sách đọc nhất quán trong nhiều câu truy vấn | Snapshot transaction phù hợp hoặc truy vấn gộp, tùy yêu cầu | Giữ snapshot có kéo dài transaction/ảnh hưởng tài nguyên không; có phải serializable cho bước ghi sau đó không |

Ví dụ về cập nhật có điều kiện nguyên tử:

```sql
UPDATE account_balance
SET balance = balance - 30
WHERE account_id = 1 AND balance >= 30;
-- Ứng dụng kiểm tra số hàng được cập nhật: 1 là thành công,
-- 0 là không đủ số dư hoặc không tìm thấy tài khoản.
```

Đoạn này an toàn hơn mẫu “`SELECT balance`; tính ở Java; `UPDATE balance = giá_trị_đã_đọc - 30`” đối với nguy cơ ghi đè một cập nhật đồng thời trên cùng hàng. Nhưng nếu nghiệp vụ là chuyển tiền giữa hai tài khoản, vẫn phải đặt các thao tác liên quan trong **một giao dịch** và xác định cách xử lý khi xung đột.

## 9. Câu hỏi thực hành

**Câu 1.** Hai lần `SELECT COUNT(*)` trong PostgreSQL `REPEATABLE READ` luôn cho cùng tập bản ghi theo snapshot; vậy có chắc hai transaction dựa trên kết quả đếm đó không thể vi phạm quy tắc “ít nhất một người trực”?  
**Trả lời:** Không. Đây là bài toán write skew ở phần 5. Snapshot ổn định không đủ bảo vệ bất biến trên nhiều hàng.

**Câu 2.** Hai môi trường SQL Server cùng đặt session `READ COMMITTED` nhưng một môi trường bật `READ_COMMITTED_SNAPSHOT`. Có thể suy ra chúng có cùng thời gian chờ đọc khi gặp writer đang giữ khóa không?  
**Trả lời:** Không. Hai cơ chế khóa và row versioning có hành vi reader–writer khác nhau; cần kiểm tra cấu hình và thử chạy đồng thời.

**Câu 3.** Sau lỗi serialization ở `COMMIT`, ứng dụng chỉ chạy lại câu `UPDATE` mà không chạy lại bước `SELECT COUNT(*)`. Có giữ được quy tắc nghiệp vụ ca trực không?  
**Trả lời:** Không. Quyết định cập nhật phải được tính lại từ một transaction và snapshot mới.

**Câu 4.** Trong InnoDB `REPEATABLE READ`, tại sao hai câu `SELECT status ...` và `SELECT status ... FOR UPDATE` có thể không cùng cách quan sát dữ liệu?  
**Trả lời:** Câu đầu thường là consistent read theo snapshot, còn câu sau là locking read với cơ chế đọc/khóa dữ liệu hiện hành. Cần xem chính xác phiên bản và lịch xen kẽ để giải thích kết quả.

Khi thay cơ sở dữ liệu, nâng phiên bản hoặc đổi cấu hình, hãy tái chạy các thí nghiệm đồng thời đại diện cho **bất biến nghiệp vụ thật**. Tên mức cô lập giúp định hướng; bằng chứng đáng tin cậy là kết quả của các giao dịch xen kẽ, cách DB quản lý khóa/snapshot và phản ứng của ứng dụng trước các lỗi xung đột.
