# Autocommit và giao dịch tường minh

## 1. Vì sao ranh giới giao dịch quan trọng?

Một ứng dụng thường thực hiện nhiều câu SQL để hoàn thành một thao tác nghiệp vụ. Chẳng hạn, khi đặt hàng, hệ thống phải trừ tồn kho, tạo đơn và lưu các dòng hàng. Nếu mỗi câu lệnh được chốt độc lập, một lỗi ở bước tạo đơn có thể để lại tồn kho đã bị trừ mà không có đơn hàng tương ứng.

Đó là vấn đề về **ranh giới giao dịch (transaction boundary)**: những thay đổi nào phải được chấp nhận hoặc hủy cùng nhau?

Trong cơ sở dữ liệu quan hệ, hai cách làm việc thường gặp là:

- **Autocommit:** mỗi câu lệnh được xử lý và tự hoàn tất theo giao dịch riêng, trừ khi đã mở một giao dịch tường minh hoặc có quy tắc đặc biệt của hệ quản trị.
- **Giao dịch tường minh (explicit transaction):** ứng dụng chủ động bắt đầu một đơn vị công việc, chạy nhiều thao tác, rồi quyết định `COMMIT` hoặc `ROLLBACK`.

Khác biệt này liên quan trực tiếp đến **tính nguyên tử, vòng đời giao dịch, khả năng quan sát thay đổi và cách các giao dịch cạnh tranh với nhau**. Hiểu autocommit là hiểu *ai quyết định khi nào một giao dịch kết thúc*.

### Ví dụ mở đầu

Giả sử còn 5 sản phẩm. Người dùng đặt 2 sản phẩm:

```sql
UPDATE inventory
SET available = available - 2
WHERE product_id = 10 AND available >= 2;

INSERT INTO orders (customer_id, status)
VALUES (101, 'CREATED');
```

Nếu câu `UPDATE` thành công và tự commit nhưng `INSERT` bị lỗi, số lượng hàng đã giảm mà đơn hàng chưa được tạo. Trong khi đó, nếu hai câu thuộc **cùng một giao dịch**, lỗi ở bước tạo đơn có thể dẫn tới rollback cả phép trừ kho.

Một giao dịch không thay ứng dụng quyết định đặt hàng có hợp lệ hay không. Ứng dụng vẫn phải xác nhận số dòng cập nhật, kiểm tra ràng buộc và xử lý tình huống cạnh tranh.

## 2. Các mốc cơ bản trong vòng đời giao dịch

Trước khi so sánh hai chế độ, cần phân biệt các trạng thái:

1. **Bắt đầu giao dịch:** một phạm vi đọc và ghi được thiết lập. DBMS có thể bắt đầu thực tế khi nhận lệnh `BEGIN`, khi câu SQL đầu tiên chạy hoặc khi driver cần giao dịch, tùy hệ và API.
2. **Đang hoạt động:** các câu lệnh đọc, chèn, sửa, xóa diễn ra trong cùng phạm vi. Các thay đổi chưa commit được quản lý theo cơ chế giao dịch của DBMS.
3. **Commit:** giao dịch được chấp nhận. Các thay đổi đã chốt trở thành dữ liệu được công bố theo quy tắc cô lập và sao chép của hệ.
4. **Rollback:** các thay đổi chưa commit của giao dịch bị hủy.
5. **Kết thúc:** giao dịch cũ không còn hoạt động; phiên kết nối có thể bắt đầu giao dịch mới hoặc trở lại chế độ tự commit.

Một giao dịch điển hình:

```text
Bắt đầu giao dịch
       |
       v
Thực hiện SQL
       |
       +---------------------+
       |                     |
   Hợp lệ, xong việc       Lỗi / điều kiện không đạt
       |                     |
       v                     v
     COMMIT                ROLLBACK
       |                     |
       +----------+----------+
                  |
                  v
           Giao dịch kết thúc
```

**`COMMIT` không đồng nghĩa với “một câu SQL đã chạy xong”.** Một câu SQL trong giao dịch mở có thể thực thi thành công nhưng thay đổi của nó vẫn chưa được commit. Ngược lại, sau khi đã commit, `ROLLBACK` của một giao dịch sau đó không thể hoàn tác bản ghi đã chốt ở giao dịch trước.

## 3. Autocommit là gì?

Ở chế độ autocommit, mỗi câu lệnh SQL độc lập thông thường được thực hiện trong một giao dịch riêng và, nếu thành công, giao dịch đó được commit tự động. Nếu câu lệnh thất bại, DBMS xử lý rollback theo quy tắc của câu lệnh và hệ quản trị.

Có thể hình dung:

```text
Câu SQL A
    |
    v
[Giao dịch A: chạy A -> tự COMMIT]
    |
    v
Câu SQL B
    |
    v
[Giao dịch B: chạy B -> tự COMMIT]
```

Điều này lý giải vì sao autocommit tiện dùng khi chỉ cần một câu lệnh độc lập. Nó cũng giải thích rủi ro khi nhiều câu SQL phải cùng thành công.

### 3.1. Ví dụ hai câu lệnh độc lập

Giả sử hai lệnh sau được gửi ở chế độ autocommit và không có giao dịch tường minh nào đang mở:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;
```

Sau câu thứ nhất thành công, phép trừ có thể đã **commit vĩnh viễn theo bảo đảm của DBMS**, trước khi câu thứ hai bắt đầu. Nếu câu thứ hai lỗi, một `ROLLBACK` sau đó không thể tự khôi phục phép trừ đã commit.

Có thể viết thêm câu `UPDATE` để bù trừ, nhưng đó là **một thao tác nghiệp vụ mới**, có thể bị cạnh tranh, lỗi tiếp hoặc làm sai lịch sử kế toán. Với các thay đổi phải nguyên tử, cần đặt chúng trong một giao dịch từ đầu.

### 3.2. Một câu lệnh vẫn có giao dịch

Autocommit không có nghĩa DBMS “bỏ qua transaction” hay ACID. Một câu `INSERT` hay `UPDATE` tự commit vẫn được thực hiện với cơ chế giao dịch mà engine hỗ trợ.

Điểm cần nhớ là **đơn vị nguyên tử mặc định thường chỉ là câu lệnh hiện tại**, chứ không phải toàn bộ chuỗi câu lệnh trong hàm ứng dụng, một request HTTP hay một đoạn mã giữa hai dòng chú thích.

### 3.3. Truy vấn `SELECT` cũng có phạm vi giao dịch

Trong nhiều DBMS có cơ chế giao dịch, một câu `SELECT` chạy ở autocommit được xử lý trong một phạm vi giao dịch/đọc chỉ tồn tại trong thời gian câu lệnh. Snapshot dữ liệu, khóa đọc hoặc cách giải phóng tài nguyên tùy engine và isolation level.

Ví dụ:

```sql
SELECT SUM(amount) FROM payments WHERE status = 'SUCCESS';
SELECT COUNT(*) FROM payments WHERE status = 'SUCCESS';
```

Nếu hai câu chạy riêng lẻ theo autocommit, một giao dịch khác có thể commit giữa chúng. Tổng tiền và số lượng có thể tương ứng **hai trạng thái dữ liệu khác nhau**. Nếu một báo cáo yêu cầu ảnh chụp nhất quán, phải cân nhắc giao dịch nhiều câu lệnh với mức cô lập/snapshot phù hợp; chỉ dùng `BEGIN` nhưng giữ mức `READ COMMITTED` không phải lúc nào cũng cố định snapshot giữa các câu.

## 4. Giao dịch tường minh là gì?

Với giao dịch tường minh, ứng dụng xác định rõ điểm bắt đầu và điểm kết thúc. Cú pháp quen thuộc:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

Hai lệnh `UPDATE` được đặt trong cùng giao dịch. Nếu xảy ra lỗi hoặc một điều kiện nghiệp vụ không đạt, ứng dụng cần thực hiện `ROLLBACK` thay vì `COMMIT`:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

-- Nếu phát hiện không thể hoàn tất thao tác:
ROLLBACK;
```

Các ví dụ SQL trên diễn tả cơ chế ranh giới. Một chuyển tiền thực tế phải kiểm tra số tiền dương, tài khoản tồn tại, số dư hợp lệ, số dòng được cập nhật và xử lý xung đột. Việc chỉ gom hai câu `UPDATE` vào giao dịch chưa đủ chứng minh nghiệp vụ đúng.

### 4.1. Ba đặc điểm quyết định

**Thứ nhất, nhóm thay đổi được commit hoặc rollback cùng nhau.** Nếu công việc chưa hợp lệ, không chốt một nửa kết quả.

**Thứ hai, các câu lệnh liên tiếp cùng một giao dịch có thể chia sẻ ngữ cảnh khóa, snapshot và mức cô lập.** Hành vi đọc thấy dữ liệu nào vẫn phụ thuộc DBMS và isolation level, không chỉ phụ thuộc việc dùng `BEGIN`.

**Thứ ba, giao dịch có thời điểm kết thúc do ứng dụng quyết định.** Trong lúc chưa kết thúc, DBMS có thể giữ khóa, phiên bản, tài nguyên hoặc trạng thái cần thiết. Mở giao dịch quá lâu khiến các giao dịch khác khó tiến triển.

### 4.2. Lệnh kết thúc và hậu quả

| Hành động | Kết quả về mặt giao dịch |
| --- | --- |
| `BEGIN` / `START TRANSACTION` | Bắt đầu phạm vi giao dịch tường minh theo cú pháp DBMS. |
| `COMMIT` | Chấp nhận toàn bộ thay đổi đang chờ commit của giao dịch hiện tại. |
| `ROLLBACK` | Hủy những thay đổi chưa commit trong giao dịch hiện tại. |
| Mất kết nối khi giao dịch chưa commit | DBMS thông thường hủy giao dịch còn mở khi phát hiện phiên kết thúc; việc phát hiện và dọn dẹp có thể không tức thời. |
| Kết nối mất đúng lúc `COMMIT` | Ứng dụng có thể không biết giao dịch đã commit hay chưa; cần xác minh theo mã nghiệp vụ, không retry mù. |

Không nên coi việc đóng kết nối là lệnh rollback có thể dựa vào ở mọi trình điều khiển. **Luôn commit hoặc rollback tường minh khi ứng dụng đang sở hữu giao dịch**, kể cả trên đường lỗi.

## 5. So sánh autocommit với giao dịch tường minh

| Tiêu chí | Autocommit (không mở giao dịch tường minh) | Giao dịch tường minh |
| --- | --- | --- |
| Ranh giới thường gặp | Một câu lệnh độc lập | Một hoặc nhiều câu lệnh do ứng dụng nhóm |
| Ai kết thúc? | DBMS/driver tự commit khi câu lệnh thành công | Ứng dụng yêu cầu `COMMIT` hoặc `ROLLBACK` |
| Khi câu thứ hai lỗi | Câu thứ nhất có thể đã commit | Có thể rollback các bước chưa commit trong cùng giao dịch |
| Phạm vi khóa và trạng thái | Thường ngắn, theo câu SQL | Có thể kéo dài qua nhiều câu SQL |
| Tính nhất quán của nhiều lần đọc | Có thể thấy các snapshot khác nhau giữa câu | Phụ thuộc isolation level; có thể tạo snapshot nhất quán |
| Độ phức tạp phía ứng dụng | Đơn giản cho tác vụ độc lập | Cần quản lý lỗi, rollback, kết nối và retry |
| Phù hợp | Đọc đơn lẻ, ghi đơn lẻ độc lập, tác vụ quản trị tương thích | Chuyển tiền, cập nhật nhiều bảng, ghi cùng một đơn vị nghiệp vụ |

**Autocommit và giao dịch tường minh không phải hai kiểu giao dịch khác nhau về bản chất.** Chúng chủ yếu khác ở **cách xác định và điều khiển ranh giới**.

## 6. Một ví dụ xuyên suốt: đặt hàng và trừ tồn kho

Giả sử bảng `inventory` lưu số hàng khả dụng và bảng `orders` lưu đơn hàng. Còn 3 sản phẩm, người mua đặt 2.

### 6.1. Cách dễ lỗi khi dùng autocommit

```sql
-- Lệnh 1: chạy độc lập và tự commit
UPDATE inventory
SET available = available - 2
WHERE product_id = 20
  AND available >= 2;

-- Lệnh 2: cũng chạy độc lập và tự commit
INSERT INTO orders (customer_id, product_id, quantity)
VALUES (501, 20, 2);
```

Lệnh 1 thành công, tồn kho còn 1. Nếu lệnh 2 gặp lỗi ràng buộc hoặc mất kết nối trước khi gửi đi, cơ sở dữ liệu giữ tồn kho bằng 1 nhưng không có đơn hàng.

Ngay cả khi lệnh 1 cập nhật **0 dòng** vì hết hàng, lệnh 2 vẫn có thể tạo đơn nếu ứng dụng bỏ qua số dòng ảnh hưởng.

### 6.2. Cách đặt cùng ranh giới tường minh

Luồng nghiệp vụ:

```text
Nhận yêu cầu đặt 2 sản phẩm
    |
    v
BEGIN
    |
    v
UPDATE inventory
SET available = available - 2
WHERE product_id = 20 AND available >= 2
    |
    +-- affected_rows != 1 --> ROLLBACK --> từ chối đơn
    |
    v
INSERT INTO orders (...)
    |
    +-- lỗi bất kỳ ---------> ROLLBACK --> trả lỗi/thử lại có kiểm soát
    |
    v
COMMIT
    |
    v
Xác nhận đơn thành công
```

Có thể diễn đạt phần SQL chính:

```sql
BEGIN;

UPDATE inventory
SET available = available - 2
WHERE product_id = 20 AND available >= 2;

-- Ứng dụng phải kiểm tra rằng đã cập nhật đúng 1 dòng.
-- Nếu không, ROLLBACK ngay và không chạy INSERT.

INSERT INTO orders (customer_id, product_id, quantity)
VALUES (501, 20, 2);

COMMIT;
```

Đây là **mẫu trình tự**, không phải script tự xử lý nhánh lỗi nếu copy toàn bộ vào SQL client. Việc kiểm tra số dòng và quyết định rollback phải do ứng dụng, stored procedure hoặc đoạn điều khiển tương ứng thực hiện.

### 6.3. Nếu hai người đặt cùng lúc?

T1 và T2 cùng đặt 2 sản phẩm trong khi kho chỉ còn 3. Câu `UPDATE ... WHERE available >= 2` vừa kiểm tra điều kiện vừa trừ tồn trong một phép ghi có điều kiện. Trên engine giao dịch phù hợp, hai giao dịch tranh chấp bản ghi này sẽ được điều phối để không cùng trừ 2 từ một số lượng chỉ còn đủ cho một đơn.

- Giao dịch thắng cập nhật 1 dòng và có thể tiếp tục tạo đơn.
- Giao dịch còn lại có thể chờ, bị báo xung đột hoặc cập nhật 0 dòng tùy DBMS/isolation.
- Ứng dụng phải xử lý kết quả phù hợp, không nhận đơn nếu không trừ kho thành công.

**`BEGIN` và `COMMIT` bảo đảm phạm vi nguyên tử; câu cập nhật có điều kiện bảo vệ bất biến tồn kho tại điểm cạnh tranh.** Cả hai giải quyết những phần khác nhau của bài toán.

## 7. Bật/tắt autocommit trong ứng dụng và DBMS

### 7.1. Chế độ autocommit thường thuộc về phiên kết nối

Một kết nối DB có thể mang các thiết lập như mức cô lập, autocommit và trạng thái giao dịch. Hai kết nối trong cùng chương trình có thể ở những trạng thái khác nhau.

Không nên suy ra rằng “đã bật autocommit ở đâu đó trong ứng dụng” thì tất cả truy vấn từ mọi kết nối đều dùng chung một phạm vi. Tương tự, một lệnh `BEGIN` trên kết nối A **không tự bao gồm** các lệnh chạy trên kết nối B.

### 7.2. PostgreSQL

Các client như `psql` và driver thường cung cấp chế độ autocommit theo phía client. Khi bật, câu lệnh riêng lẻ được gửi và hoàn tất theo phạm vi giao dịch tương ứng. PostgreSQL hỗ trợ điều khiển tường minh bằng `BEGIN`, `COMMIT` và `ROLLBACK`:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 50 WHERE id = 1;
UPDATE accounts SET balance = balance + 50 WHERE id = 2;
COMMIT;
```

Trong `psql`, `\set AUTOCOMMIT off` là thiết lập **của công cụ client**, không phải tham số `SET autocommit = 0` của PostgreSQL server. Khi một câu lệnh gây lỗi trong giao dịch PostgreSQL, giao dịch thường chuyển sang trạng thái lỗi và các câu tiếp theo không thể thực thi bình thường cho đến `ROLLBACK` (hoặc xử lý bằng savepoint nếu phù hợp).

### 7.3. MySQL với InnoDB

Ở phiên MySQL/InnoDB thông thường, biến phiên `autocommit` mặc định được bật, nên các câu lệnh độc lập được commit tự động. Có thể xem trạng thái bằng:

```sql
SELECT @@autocommit;
```

Bắt đầu giao dịch tường minh bằng:

```sql
START TRANSACTION;

UPDATE accounts SET balance = balance - 50 WHERE id = 1;
UPDATE accounts SET balance = balance + 50 WHERE id = 2;

COMMIT;
```

MySQL còn hỗ trợ thiết lập autocommit của session:

```sql
SET autocommit = 0;
-- Các thao tác thuộc giao dịch do phiên quản lý.
-- Sau COMMIT/ROLLBACK, phiên vẫn ở chế độ autocommit tắt.
COMMIT;

SET autocommit = 1;
```

Thay đổi chế độ có thể có **hiệu ứng commit ngoài dự tính** (đặc biệt khi bật lại autocommit lúc còn giao dịch đang hoạt động). Vì vậy, cần hiểu chính xác semantics của lệnh và ưu tiên một chiến lược quản lý giao dịch nhất quán theo driver/framework.

Không được mặc định mọi loại bảng MySQL đều rollback giống InnoDB; engine không hỗ trợ giao dịch sẽ có hành vi khác.

### 7.4. SQL Server và các hệ khác

SQL Server hỗ trợ cú pháp `BEGIN TRANSACTION` / `COMMIT TRANSACTION` / `ROLLBACK TRANSACTION` và một chế độ gọi là `IMPLICIT_TRANSACTIONS`. Chế độ này cần được hiểu theo SQL Server; nó **không đồng nghĩa hoàn toàn** với cách mọi driver/DBMS gọi “autocommit off”.

Oracle và các hệ khác cũng có khác biệt về lệnh quản lý giao dịch và thời điểm commit ngầm. Khi viết SQL hoặc tích hợp ORM, hãy xác định rõ **engine, driver, client và phạm vi kết nối** trước khi giả định hành vi mặc định.

### 7.5. JDBC: `setAutoCommit(false)`

Với Java/JDBC, `Connection` có API điều khiển autocommit:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    try {
        connection.setAutoCommit(false);

        // Các câu SQL thực thi trên chính connection này
        // tham gia cùng một transaction.
        performFirstUpdate(connection);
        performSecondUpdate(connection);

        connection.commit();
    } catch (SQLException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    } finally {
        connection.setAutoCommit(previousAutoCommit);
    }
}
```

Đây là mẫu để **minh họa phạm vi giao dịch JDBC**, trong đó `performFirstUpdate` và `performSecondUpdate` đại diện cho các thao tác ứng dụng phải hiện thực. Một triển khai production cần xử lý kỹ lỗi commit hoặc lỗi khôi phục trạng thái kết nối, bảo đảm chỉ đưa kết nối an toàn trở lại pool và phân biệt lỗi có thể retry.

Những điểm cần hiểu:

- `connection.setAutoCommit(false)` khiến các lệnh tiếp theo trên kết nối này tham gia vào giao dịch do ứng dụng quản lý theo quy tắc JDBC/driver.
- `connection.commit()` chốt những thay đổi của giao dịch hiện hành; `connection.rollback()` hủy các thay đổi chưa chốt.
- Nếu một repository tự mở **kết nối khác**, các thao tác ở kết nối đó không tự tham gia vào giao dịch vừa tạo.
- Đổi `setAutoCommit(true)` khi còn giao dịch chưa kết thúc có thể dẫn tới commit theo semantics của JDBC/driver. Vì vậy phải kết thúc giao dịch trước khi khôi phục trạng thái.
- Nếu dùng connection pool, trạng thái của kết nối phải được hoàn nguyên hoặc do pool/framework quản lý đúng cách.

## 8. Giao dịch do framework quản lý

Trong Spring, cách quen thuộc là xác định một phạm vi nghiệp vụ bằng `@Transactional`:

```java
@Service
public class OrderService {
    private final InventoryRepository inventoryRepository;
    private final OrderRepository orderRepository;

    public OrderService(
            InventoryRepository inventoryRepository,
            OrderRepository orderRepository) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void placeOrder(long productId, int quantity, long customerId) {
        int changed = inventoryRepository.decreaseIfAvailable(
                productId, quantity);

        if (changed != 1) {
            throw new IllegalStateException("Insufficient stock");
        }

        orderRepository.create(customerId, productId, quantity);
    }
}
```

Trong cấu hình transaction manager phù hợp, framework mở hoặc tham gia giao dịch, gắn kết nối/ngữ cảnh với luồng thực thi và quyết định commit/rollback theo kết quả phương thức. Ví dụ trên giả định phương thức repository dùng đúng datasource và transaction manager, không tự commit ở kết nối riêng.

Một số giới hạn thực tế:

- **`@Transactional` không tự bao trùm mọi DB hoặc HTTP call.** Một nguồn dữ liệu thứ hai cần cơ chế phối hợp riêng nếu muốn bảo đảm xuyên hệ thống.
- **Quy tắc rollback phụ thuộc framework:** trong Spring mặc định, runtime exception và `Error` thường kích hoạt rollback; checked exception cần cấu hình nếu muốn rollback. Không được giả định mọi loại lỗi tự động làm rollback.
- **Invocation/proxy:** trong cấu hình proxy phổ biến, gọi một phương thức `@Transactional` từ phương thức khác của chính đối tượng đó có thể bỏ qua interception nên giao dịch mong muốn không được tạo.
- **Không giữ giao dịch mở khi chờ HTTP, message broker hoặc người dùng** nếu không có một thiết kế điều phối cụ thể.
- Với luồng bất đồng bộ hoặc đổi thread, ngữ cảnh giao dịch không tự đi theo mọi tác vụ; cần xem cơ chế framework thực tế.

Vì vậy, annotation là cách quản lý ranh giới ở tầng ứng dụng. Để biết SQL nào thực sự nằm trong transaction, phải hiểu cách framework liên kết lời gọi repository với kết nối.

## 9. Autocommit, isolation level và khả năng nhìn thấy dữ liệu

**Autocommit trả lời câu hỏi “giao dịch kết thúc khi nào?”** Còn **isolation level** trả lời câu hỏi “giao dịch đang hoạt động được phép quan sát ảnh hưởng của giao dịch khác ra sao?”.

Giả sử T1 muốn đọc số lượng đơn và tổng doanh thu:

```sql
SELECT COUNT(*) FROM orders WHERE status = 'PAID';
SELECT SUM(total_amount) FROM orders WHERE status = 'PAID';
```

Nếu mỗi câu chạy trong autocommit, T2 có thể chèn một đơn mới và commit giữa hai câu. Khi đó, T1 có thể lấy số lượng từ trạng thái cũ nhưng doanh thu từ trạng thái mới.

Chuyển sang giao dịch tường minh:

```sql
BEGIN;
SELECT COUNT(*) FROM orders WHERE status = 'PAID';
SELECT SUM(total_amount) FROM orders WHERE status = 'PAID';
COMMIT;
```

Điều này **không tự động** bảo đảm hai lần đọc cùng snapshot. Ví dụ, ở nhiều hệ với `READ COMMITTED`, mỗi câu lệnh có thể lấy một snapshot mới. Nếu cần toàn bộ báo cáo có một điểm nhìn nhất quán, phải chọn isolation hoặc cơ chế snapshot phù hợp với DBMS.

### 9.1. Các mức cô lập có liên quan

| Mức cô lập | Ảnh hưởng khi nhiều câu đọc nằm trong một transaction |
| --- | --- |
| `READ UNCOMMITTED` | Theo mô hình chuẩn, có thể cho phép đọc dữ liệu chưa commit; thực tế nhiều DBMS triển khai khác. |
| `READ COMMITTED` | Không đọc thay đổi chưa commit; hai câu đọc kế tiếp vẫn có thể thấy những commit khác nhau. |
| `REPEATABLE READ` | Bảo vệ việc đọc lặp theo nghĩa của hệ; cần kiểm tra semantics snapshot, phantom và write skew của engine. |
| `SERIALIZABLE` | Các giao dịch đã commit tương đương một thứ tự thực thi tuần tự hợp lệ; có thể phải retry khi DBMS báo xung đột serialization. |

Không nên chọn isolation level chỉ vì muốn “chạy nhanh”. Hãy phát biểu rõ ràng dữ liệu nào cần nhất quán trong **cùng một quyết định nghiệp vụ**.

### 9.2. Commit và visibility không đồng nghĩa “mọi nơi đã thấy dữ liệu”

Khi một giao dịch commit, thay đổi đã chốt có thể được giao dịch khác quan sát theo quy tắc cô lập. Nhưng:

- Một giao dịch đang giữ snapshot cũ có thể tiếp tục đọc phiên bản cũ.
- Bản sao đọc bất đồng bộ có thể nhận thay đổi sau một khoảng trễ.
- Cache của ứng dụng hoặc hệ thống tìm kiếm có thể cần cập nhật riêng.

Vì thế, “đã commit” không tự bảo đảm mọi truy vấn hoặc mọi hệ thống khác nhìn thấy thay đổi ngay lập tức.

## 10. Lỗi xảy ra ở thời điểm nào?

Hãy chia vòng đời thành ba giai đoạn: **trước commit, trong lúc commit và sau commit**.

### 10.1. Lỗi trước commit

Ví dụ sau khi trừ kho, câu tạo đơn vi phạm ràng buộc `UNIQUE`. Nếu hai thao tác thuộc một transaction, ứng dụng có thể rollback và hủy phép trừ kho chưa chốt.

Tuy nhiên, xử lý lỗi SQL khác nhau giữa DBMS. Chẳng hạn, một số lỗi trong PostgreSQL làm cả transaction rơi vào trạng thái bị hủy; ứng dụng phải rollback hoặc quay về savepoint hợp lệ trước khi làm tiếp. Không nên cho rằng tất cả DBMS cho phép tiếp tục chạy SQL sau mọi lỗi.

### 10.2. Lỗi ngay lúc commit

Trường hợp khó hơn: ứng dụng gửi `COMMIT` nhưng mất kết nối trước khi nhận được phản hồi. Có ít nhất hai khả năng:

1. DBMS đã chốt dữ liệu, chỉ có phản hồi bị mất.
2. DBMS chưa chốt hoặc đã hủy giao dịch.

Ứng dụng **không thể suy luận chắc chắn từ lỗi mạng** rằng giao dịch đã rollback. Nếu thử lại toàn bộ thao tác chuyển tiền mà không có cơ chế idempotency, có thể chuyển hai lần.

Một thiết kế an toàn thường dùng **mã yêu cầu nghiệp vụ duy nhất** được lưu với ràng buộc `UNIQUE` trong cùng transaction, để sau lỗi không rõ kết quả có thể truy vấn lại và xác định yêu cầu đã hoàn thành hay chưa.

### 10.3. Lỗi sau commit

Một khi commit đã thành công, không thể dùng rollback của transaction cũ để thu hồi thay đổi. Nếu sau đó thất bại khi gửi email xác nhận, gọi đối tác hoặc xuất thông điệp, cần thiết kế xử lý riêng, chẳng hạn transactional outbox, cơ chế gửi lại có idempotency hoặc một quy trình bù trừ.

Không nên dùng giao dịch DB kéo dài qua API bên ngoài rồi mặc định thao tác ngoài DB sẽ rollback cùng dữ liệu.

## 11. Chuyển đổi chế độ và những “commit ngầm” dễ bỏ sót

Lệnh đặt autocommit, giao dịch tường minh và câu lệnh DDL có thể tương tác theo cách khác nhau ở từng hệ. Một vài tình huống cần chú ý:

### 11.1. Bật autocommit lại khi transaction chưa kết thúc

Ở một số API/DBMS, bật autocommit trở lại từ trạng thái tắt có thể **commit giao dịch hiện hành**. Trong JDBC, chuyển chế độ autocommit khi đang có giao dịch có thể làm giao dịch được commit. Vì vậy, không nên coi `setAutoCommit(true)` là cách “hủy transaction để dọn dẹp”. Phải gọi `rollback()` nếu muốn hủy.

### 11.2. Chạy DDL bên trong transaction

Không phải mọi cơ sở dữ liệu đều cho phép rollback `CREATE TABLE` hoặc `ALTER TABLE` như rollback `UPDATE`. Một số hệ, ví dụ MySQL với nhiều lệnh DDL, có thể **commit ngầm** trước hoặc sau DDL; PostgreSQL hỗ trợ nhiều DDL trong giao dịch nhưng có ngoại lệ và giới hạn cụ thể.

Không nên áp dụng suy luận “đã `BEGIN` thì mọi lệnh DDL bên trong chắc chắn rollback được” cho mọi engine. Khi viết migration, cần dựa vào tài liệu và cơ chế công cụ migration của hệ đang dùng.

### 11.3. Một batch nhiều câu SQL không mặc định là một transaction

JDBC `executeBatch()` hoặc việc gửi nhiều câu lệnh trong một lần gọi API không có nghĩa tất cả được commit nguyên tử. Phạm vi giao dịch phụ thuộc autocommit, driver và hành vi của engine. Nếu tính nguyên tử là yêu cầu, phải quản lý transaction rõ ràng và xử lý partial failure theo API tương ứng.

### 11.4. “Giao dịch lồng nhau” thường không là hai commit độc lập

Nếu một phương thức chạy trong transaction T1 rồi gọi phương thức khác cũng được đánh dấu transactional, không thể mặc định sẽ có transaction T2 độc lập. Framework có thể **tham gia T1**, tạo savepoint hoặc mở transaction mới tùy cấu hình propagation.

`SAVEPOINT` có thể giúp rollback một phần thay đổi trong cùng transaction:

```sql
BEGIN;

UPDATE inventory SET available = available - 1 WHERE product_id = 20;

SAVEPOINT after_inventory;

-- Các thao tác tiếp theo
-- Nếu cần hủy các thao tác sau savepoint:
ROLLBACK TO SAVEPOINT after_inventory;

COMMIT;
```

Rollback về savepoint không chốt các thay đổi trước savepoint. Chúng vẫn thuộc transaction tổng và vẫn có thể bị hủy nếu giao dịch chính rollback.

## 12. Giao dịch và connection pool

Ứng dụng phục vụ nhiều request thường dùng **connection pool**. Connection được mượn, dùng và trả lại để request khác tái sử dụng.

Điều này tạo ra ba yêu cầu:

1. **Không để transaction còn mở** khi trả connection về pool. Nếu xảy ra exception, ứng dụng/framework phải xử lý rollback và dọn trạng thái.
2. **Không làm rò cấu hình phiên**, gồm autocommit, isolation, các session variable hoặc trạng thái liên quan, sang request tiếp theo. Pool/framework thường có cơ chế reset nhưng phải cấu hình và hiểu đúng.
3. **Không mở connection thứ hai vô tình** cho một bước phải thuộc cùng transaction. Khi đó hai câu SQL có thể commit độc lập dù trong mã nguồn chúng nằm cạnh nhau.

Một dấu hiệu đáng nghi là đoạn code:

```text
service.placeOrder()
    -> inventoryRepository.decrease()  [connection A, auto commit]
    -> orderRepository.create()         [connection B, auto commit]
```

Hai thao tác ở cùng một hàm không đồng nghĩa chúng nằm cùng transaction. Phải bảo đảm cơ chế transaction manager thực sự điều phối cả hai trên ngữ cảnh phù hợp.

Giao dịch mở lâu còn giữ connection khỏi pool. Nếu có nhiều transaction chờ API chậm, pool có thể cạn trước khi cơ sở dữ liệu quá tải CPU.

## 13. Khi nào dùng autocommit, khi nào dùng giao dịch tường minh?

### Autocommit thường hợp lý khi

- Đọc một truy vấn độc lập, ví dụ lấy chi tiết một sản phẩm.
- Ghi một bản ghi bằng **một câu SQL nguyên tử**, có ràng buộc đầy đủ.
- Thao tác không cần phối hợp với câu lệnh thứ hai để duy trì bất biến nghiệp vụ.
- Truy vấn quản trị hoặc tác vụ cần autocommit theo quy tắc cụ thể của DBMS (phải xác minh cú pháp/hành vi).

Ví dụ cập nhật điểm thưởng bằng một phép cộng nguyên tử:

```sql
UPDATE reward_accounts
SET points = points + 10
WHERE account_id = 7;
```

Nếu đây là toàn bộ đơn vị nghiệp vụ và không cần lưu sự kiện ghi nhận trong cùng transaction, tự commit có thể phù hợp. Nếu cần vừa cộng điểm vừa ghi lịch sử để chống tính trùng, một transaction nhiều câu lệnh hoặc thiết kế ghi nguyên tử khác thường cần thiết.

### Giao dịch tường minh thường cần khi

- Nhiều bản ghi/bảng phải thay đổi như **một đơn vị nghiệp vụ**.
- Một điều kiện được đọc rồi dùng để quyết định các thao tác sau, đòi hỏi bảo vệ khỏi cạnh tranh.
- Nhiều truy vấn phải chia sẻ snapshot nhất quán và mức cô lập tương ứng.
- Hệ thống cần kiểm soát rõ commit/rollback khi gặp lỗi.
- Có chuỗi thao tác phải được ràng buộc bằng khóa hoặc phiên bản trong cùng phạm vi.

Ví dụ chuyển tiền, xác nhận thanh toán, giữ chỗ, đổi trạng thái đơn kèm lịch sử, ghi ledger và cập nhật số dư.

### Một nguyên tắc thiết kế

Đặt ranh giới giao dịch theo **bất biến phải được giữ đúng**, không chỉ theo số lượng SQL. Một giao dịch nên đủ rộng để gom các thay đổi liên quan, nhưng đủ ngắn để giảm thời gian giữ khóa và connection.

## 14. Các lỗi thiết kế thường gặp

### 14.1. Tưởng một phương thức là một transaction

Phương thức ứng dụng có thể gọi hai repository, mỗi repository tự lấy kết nối và tự commit. Cần kiểm tra ranh giới thực tế từ transaction manager/JDBC, không suy ra từ cấu trúc mã nguồn.

### 14.2. Quên commit khi tắt autocommit

Các câu SQL chạy thành công nhưng giao dịch vẫn mở; chương trình khác có thể không nhìn thấy dữ liệu đã ghi, đồng thời khóa và connection tiếp tục bị giữ. Nếu phiên bị đóng, giao dịch chưa commit thường bị hủy. Cần commit hoặc rollback ở mọi đường đi hợp lệ.

### 14.3. Bắt exception rồi tiếp tục commit

Nếu một bước thất bại và được nuốt lỗi, transaction có thể tiếp tục chốt dữ liệu thiếu hoặc sai. Hãy để lỗi dẫn tới rollback hoặc đưa ra một nhánh xử lý được thiết kế rõ ràng, có savepoint nếu thật sự phù hợp.

### 14.4. Đọc rồi ghi mà không xử lý cạnh tranh

Hai giao dịch tường minh vẫn có thể cùng đọc “còn hàng”, cùng quyết định bán và làm sai bất biến nếu không dùng khóa, cập nhật có điều kiện, phiên bản hoặc isolation thích hợp. Atomicity không thay thế concurrency control.

### 14.5. Coi mọi retry là an toàn

Khi commit trả về lỗi mạng, kết quả có thể không xác định. Retry mù dễ tạo đơn hoặc chuyển tiền hai lần. Cần mã nghiệp vụ duy nhất, truy vấn xác minh và chính sách idempotency.

### 14.6. Giữ transaction mở trong lúc chờ dịch vụ bên ngoài

HTTP call, chờ người dùng, thao tác dài hoặc sleep kéo dài thời gian giữ khóa, tạo deadlock và cạn connection. Cố gắng chuẩn bị dữ liệu bên ngoài trước, chạy phần DB ngắn gọn trong transaction, rồi xử lý hậu commit bằng cơ chế đáng tin cậy.

### 14.7. Đổi autocommit mà không biết phạm vi

Các thiết lập session tồn tại theo connection và có thể ảnh hưởng request kế tiếp khi dùng pool. Tránh tự ý chuyển chế độ giữa chừng ngoài transaction manager đang quản lý phạm vi.

## 15. Tự suy luận qua các tình huống

**Tình huống 1 — Hai phép cập nhật.** Ứng dụng chạy câu trừ số dư rồi câu cộng số dư ở autocommit. Câu đầu đã thành công, câu sau bị lỗi. `ROLLBACK` sau đó cứu được không?

Không. Câu đầu có thể đã commit. Phải đặt cả hai trong một transaction ngay từ đầu, có kiểm tra điều kiện hợp lệ trước khi commit.

**Tình huống 2 — Hai truy vấn báo cáo.** Hai câu `SELECT` được đặt trong `BEGIN` / `COMMIT`, nhưng isolation level là `READ COMMITTED`. Có chắc chúng xem cùng snapshot không?

Không chắc. Ở nhiều DBMS, mỗi câu đọc tại mức này có thể thấy các commit mới của giao dịch khác. Phải tìm hiểu cơ chế snapshot và chọn isolation phù hợp.

**Tình huống 3 — Đổi `setAutoCommit(true)` để xử lý exception.** Ứng dụng tắt autocommit, chạy một `UPDATE` rồi phát hiện lỗi. Lập trình viên bỏ qua rollback và bật autocommit trở lại. Có an toàn không?

Không. Việc chuyển chế độ có thể commit các thay đổi đang chờ. Cần rollback khi công việc thất bại, rồi mới khôi phục trạng thái kết nối.

**Tình huống 4 — Mất mạng lúc commit.** Ứng dụng gửi `COMMIT` của thao tác tạo đơn nhưng không nhận được phản hồi. Có nên tự động tạo lại đơn?

Không nên tạo lại một cách mù quáng. Kết quả commit chưa chắc xác định được từ phía client. Cần mã yêu cầu duy nhất hoặc cơ chế xác minh kết quả trước khi thực hiện lại.

**Tình huống 5 — Một câu `UPDATE` tồn kho có điều kiện.** Ứng dụng chỉ giảm tồn kho, không tạo đơn hoặc ghi lịch sử. Có bắt buộc mở transaction tường minh không?

Không nhất thiết. Nếu đó thực sự là toàn bộ đơn vị nghiệp vụ và câu ghi nguyên tử đã bảo vệ đủ ràng buộc, autocommit có thể đáp ứng yêu cầu. Khi cần thêm các thay đổi phụ thuộc phải cùng thành công, cần xem lại ranh giới.

## 16. Ghi nhớ về vòng đời giao dịch

- **Autocommit** thuận tiện cho các câu lệnh độc lập; câu lệnh thành công thường tự được chốt.
- **Giao dịch tường minh** cho ứng dụng chủ động nhóm các thao tác và quyết định `COMMIT` hoặc `ROLLBACK`.
- Câu lệnh chạy thành công **chưa đồng nghĩa** với transaction đã commit.
- Autocommit, isolation level, locking và snapshot là các khía cạnh liên quan nhưng khác nhau.
- Đảm bảo nhiều câu SQL thuộc một transaction đòi hỏi chúng dùng **đúng ngữ cảnh giao dịch/kết nối**.
- Ranh giới transaction tốt vừa giữ bất biến nghiệp vụ, vừa tránh giữ khóa và connection quá lâu.
- Khi kết quả commit không xác định vì mất kết nối, phải xử lý theo **idempotency và xác minh trạng thái**, không dựa vào giả định rollback.

Nhìn từ vòng đời giao dịch, câu hỏi thiết kế hữu ích nhất là: **“Ở thời điểm nào ứng dụng có quyền tuyên bố toàn bộ thao tác nghiệp vụ đã hoàn tất, và nếu một bước lỗi trước thời điểm đó thì những thay đổi nào phải được hủy?”** Trả lời câu hỏi này giúp chọn đúng autocommit hay giao dịch tường minh và xác định nơi cần thêm cơ chế kiểm soát đồng thời.
