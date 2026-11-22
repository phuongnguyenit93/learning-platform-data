# Ranh giới giữa một câu lệnh và một giao dịch nhiều câu lệnh

Trong hệ quản trị cơ sở dữ liệu quan hệ, **câu lệnh SQL (statement)** là một đơn vị yêu cầu thực thi, còn **giao dịch (transaction)** là một đơn vị công việc có ranh giới commit hoặc rollback. Một giao dịch có thể chỉ chứa một câu lệnh, nhưng cũng có thể chứa nhiều câu lệnh cùng tạo thành một thao tác nghiệp vụ.

Phân biệt hai ranh giới này là nền tảng để hiểu vòng đời giao dịch và hành vi cạnh tranh đồng thời. Một chương trình có thể thực hiện ba lệnh SQL liên tiếp trên cùng kết nối mà vẫn tạo ra **ba transaction độc lập** nếu mỗi lệnh tự commit. Ngược lại, cùng ba lệnh đó có thể thuộc **một transaction duy nhất** nếu ứng dụng mở transaction trước và chỉ commit sau khi hoàn tất toàn bộ thao tác.

Ví dụ dễ thấy là chuyển 100 đơn vị tiền từ tài khoản A sang B:

- Trừ 100 từ A.
- Cộng 100 cho B.
- Ghi lịch sử chuyển tiền.

Nếu từng câu lệnh được commit độc lập, bước đầu có thể thành công và bước hai thất bại, để lại trạng thái chuyển tiền dở dang. Nếu cả ba bước nằm trong một transaction và chương trình rollback khi một bước thất bại, các thay đổi chưa commit của transaction đó sẽ được hoàn tác.

## 1. Ba lớp ranh giới cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Một câu lệnh SQL** | Một yêu cầu SQL do client gửi cho database để thực thi | `UPDATE accounts SET balance = balance - 100 WHERE id = 1` |
| **Một transaction** | Nhóm thao tác có chung điểm bắt đầu, commit/rollback và ngữ cảnh cô lập | `BEGIN; UPDATE ...; UPDATE ...; COMMIT;` |
| **Một thao tác nghiệp vụ** | Kết quả mà hệ thống hứa với người dùng, có thể cần một hoặc nhiều transaction và cả hệ thống ngoài DB | “Chuyển tiền thành công”, “Đặt hàng và gửi thông báo” |

Ba lớp này không tự động trùng nhau. Một câu `UPDATE` có thể cập nhật hàng nghìn hàng trong một statement. Một transaction có thể bao gồm hàng chục `SELECT`, `INSERT`, `UPDATE`. Một nghiệp vụ có thể gọi dịch vụ bên ngoài hoặc nhiều database, vượt khỏi phạm vi một transaction cục bộ.

**Mốc chính là commit**: những câu lệnh đã được gửi đi nhưng chưa commit vẫn thuộc giao dịch đang mở. Đã chạy xong câu SQL **không đồng nghĩa** kết quả của cả nghiệp vụ đã được xác nhận bền vững.

### Sơ đồ hai cách tổ chức

~~~text
Cách A — autocommit, mỗi câu SQL là một transaction

Ứng dụng          Database
  |                  |
  |-- UPDATE A ----->|  Transaction T1
  |<-- thành công ---|  COMMIT T1
  |-- UPDATE B ----->|  Transaction T2
  |<-- lỗi ----------|  ROLLBACK T2
  |                  |
Kết quả: A đã đổi; B không đổi.


Cách B — một transaction bao nhiều câu SQL

Ứng dụng          Database
  |                  |
  |-- BEGIN -------->|
  |-- UPDATE A ----->|  Transaction T
  |-- UPDATE B ----->|  T báo lỗi
  |-- ROLLBACK ----->|  Hoàn tác T
  |                  |
Kết quả: cả A và B đều trở về trạng thái trước T.
~~~

Đây là ví dụ với cùng một database giao dịch, cùng một transaction và không có tác động bên ngoài như gửi tiền qua API khác.

## 2. Một câu lệnh trong chế độ autocommit

Phần lớn driver và công cụ kết nối có chế độ **autocommit**: mỗi câu SQL đủ điều kiện được thực thi như một transaction riêng khi client không đặt nó vào transaction đang mở. Khi câu lệnh thành công, transaction được commit; nếu thất bại, tác dụng của câu lệnh đó không được commit.

Ví dụ thực hiện độc lập:

~~~sql
-- Lệnh 1: transaction riêng nếu autocommit bật.
UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

-- Lệnh 2: transaction riêng nếu autocommit bật.
UPDATE accounts
SET balance = balance + 100
WHERE id = 2;
~~~

Khi lệnh đầu thành công, thay đổi của nó đã được commit trước khi lệnh sau bắt đầu. Nếu lệnh thứ hai gặp lỗi, database **không tự quay ngược transaction đã commit ở lệnh đầu**.

Điều này xảy ra ngay cả khi hai câu lệnh nằm sát nhau trong cùng hàm Java hoặc cùng một request HTTP. **Một hàm gọi hai repository method không tự tạo ra một transaction bao cả hai method.**

### Tính nguyên tử của một câu lệnh có giới hạn gì?

Một câu `UPDATE` thường được thực thi như một statement nguyên tử trong database giao dịch: lỗi giữa lúc cập nhật nhiều hàng không được để lại một nửa thay đổi của statement đã commit. Tuy nhiên:

- Tính nguyên tử của statement **không bao phủ câu SQL kế tiếp** đã chạy trong transaction khác.
- Tính chất cụ thể phụ thuộc database, storage engine, loại câu lệnh và cơ chế giao dịch. Chẳng hạn, hệ quản trị có thao tác DDL tự commit hoặc bảng dùng engine không hỗ trợ transaction có thể hành xử khác.
- Một câu lệnh SQL với `WHERE` sai có thể chạy **thành công về mặt kỹ thuật** nhưng cập nhật 0 hàng hoặc cập nhật sai hàng. Atomicity không chứng minh tính đúng đắn nghiệp vụ.
- `SELECT` đơn lẻ cũng tham gia vào ngữ cảnh transaction/isolation của database, dù không sửa dữ liệu và thông thường không cần commit thủ công khi client dùng autocommit.

Vì vậy, không nên coi “một statement nguyên tử” đồng nghĩa “một thao tác nghiệp vụ nguyên tử”.

## 3. Giao dịch nhiều câu lệnh: BEGIN, COMMIT và ROLLBACK

Ví dụ dưới đây sử dụng cú pháp **PostgreSQL**. Trong một phiên làm việc:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
~~~

`BEGIN` mở một transaction tường minh. Những câu lệnh được thực thi trên **cùng kết nối** sau đó là một phần của transaction này, cho tới khi `COMMIT` hoặc `ROLLBACK` kết thúc nó. `COMMIT` xác nhận toàn bộ các thay đổi của transaction. `ROLLBACK` hủy các thay đổi chưa commit thuộc transaction.

Nếu ứng dụng phát hiện một điều kiện không hợp lệ, nó phải chủ động rollback:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1
  AND balance >= 100
RETURNING id;

-- Ứng dụng phải kiểm tra có đúng một hàng được cập nhật.
-- Nếu không: ROLLBACK ngay, không thực hiện các bước còn lại.

UPDATE accounts
SET balance = balance + 100
WHERE id = 2
RETURNING id;

-- Ứng dụng phải kiểm tra có đúng một hàng được cập nhật.
-- Nếu không: ROLLBACK ngay.

COMMIT;
~~~

Đây là **mẫu điều khiển do ứng dụng thực hiện**; phần chú thích không phải các nhánh SQL tự động. Chỉ chạy nguyên script từ trên xuống mà không kiểm tra số hàng được cập nhật sẽ không đảm bảo đúng nghiệp vụ. Hệ thống thực tế còn cần kiểm tra tài khoản, quyền chuyển, loại tiền, số tiền dương và yêu cầu xử lý lặp.

### Commit là một quyết định ở cấp transaction

Giả sử transaction T chứa `UPDATE A`, `UPDATE B`, `INSERT log`. Khi cả ba đã chạy thành công nhưng chưa commit:

- Trong cùng transaction, các câu lệnh tiếp theo thông thường có thể thấy các thay đổi mà chính T vừa tạo ra.
- Transaction khác có thể thấy dữ liệu trước commit hoặc bị chặn, tùy câu lệnh và mức cô lập.
- Nếu T rollback, các thay đổi dữ liệu đã thực hiện trong T bị hoàn tác.
- Nếu T commit thành công, các thay đổi được xác nhận cùng nhau.

Một điểm quan trọng: **database không tự suy ra toàn bộ các quy tắc nghiệp vụ cần kiểm tra**. Việc gom ba bước vào một transaction ngăn trạng thái ghi dở dang, nhưng ứng dụng vẫn phải chọn đúng ba bước, kiểm tra kết quả và ràng buộc dữ liệu.

## 4. Vòng đời giao dịch và trạng thái lỗi

Một mô hình đơn giản:

~~~mermaid
flowchart TD
    A["Chưa có transaction tường minh"] -->|BEGIN hoặc bắt đầu transaction ngầm| B["Transaction đang hoạt động"]
    B -->|Thực thi câu SQL thành công| B
    B -->|COMMIT thành công| C["Đã commit"]
    B -->|ROLLBACK| D["Đã rollback"]
    B -->|Lỗi làm transaction bị abort| E["Transaction lỗi / không thể tiếp tục bình thường"]
    E -->|ROLLBACK| D
    E -->|ROLLBACK TO SAVEPOINT khi phù hợp| B
    C --> A
    D --> A
~~~

Sơ đồ thể hiện cách suy nghĩ về vòng đời, không phải mọi database đều có cùng trạng thái lỗi. Một số engine chỉ rollback statement gặp lỗi và cho phép transaction tiếp tục; số khác đưa toàn transaction vào trạng thái phải rollback.

**Riêng PostgreSQL:** khi một lỗi SQL làm transaction không còn hợp lệ, nhiều câu lệnh tiếp theo sẽ bị từ chối với thông báo tương tự “current transaction is aborted”; ứng dụng thường cần `ROLLBACK` hoặc khôi phục về savepoint đã đặt trước lỗi. Không nên giả định bắt một exception trong Java là transaction đã tự quay về trạng thái sạch.

### Phân biệt bốn kết cục

| Kết cục | Ý nghĩa |
|---|---|
| Statement trả kết quả thành công, transaction vẫn mở | Thay đổi có thể đang chờ commit; chưa được xác nhận cuối cùng |
| `COMMIT` thành công | Transaction hoàn thành; các thay đổi đã commit cùng nhau |
| `ROLLBACK` thành công | Những thay đổi chưa commit trong transaction được hủy |
| Mất kết nối khi đang commit | Client có thể **không biết** commit đã được database thực hiện hay chưa; cần cơ chế xác minh/idempotency |

Đừng lập trình theo giả định “không nhận được phản hồi COMMIT tức là database chắc chắn rollback”. Tình huống mất kết nối đúng lúc commit tạo ra **kết quả không xác định từ phía client**.

## 5. Ranh giới transaction trong một ứng dụng Java

### 5.1. JDBC: một transaction theo Connection

Với JDBC, mặc định một `Connection` mới thường có `autoCommit = true` theo hợp đồng JDBC. Khi ứng dụng muốn nhiều câu SQL cùng thuộc một transaction, nó có thể tắt autocommit, thực thi các bước, rồi gọi `commit()` hoặc `rollback()`.

Ví dụ minh họa, giả sử schema tài khoản dùng `NUMERIC` cho số dư và các ràng buộc hợp lệ:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int debited;
                try (PreparedStatement debit = connection.prepareStatement(
                        "UPDATE accounts SET balance = balance - ? " +
                        "WHERE id = ? AND balance >= ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    debited = debit.executeUpdate();
                }

                if (debited != 1) {
                    throw new IllegalStateException("Insufficient funds or source missing");
                }

                int credited;
                try (PreparedStatement credit = connection.prepareStatement(
                        "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    credited = credit.executeUpdate();
                }

                if (credited != 1) {
                    throw new IllegalStateException("Destination missing");
                }

                connection.commit();
            } catch (SQLException | RuntimeException e) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    e.addSuppressed(rollbackError);
                }
                throw e;
            }
        }
    }
}
~~~

Điểm quyết định là **hai câu UPDATE chạy trên cùng Connection trước một lần commit**. Chuyển câu UPDATE thứ hai sang một `Connection` khác không tự đưa nó vào transaction ban đầu. Trong ứng dụng có connection pool, quản lý connection, trạng thái autocommit và thời điểm trả connection cần được thực hiện nhất quán; nếu dùng framework quản lý transaction, hãy để framework sở hữu vòng đời này.

Ví dụ trên tập trung vào ranh giới và xử lý rollback. Một hệ thống tiền thật còn cần kiểm soát loại tiền, quyền truy cập, ghi sổ kế toán, idempotency, giới hạn retry, kiểm tra khoản tiền và các chính sách nghiệp vụ khác.

### 5.2. Spring: ranh giới transaction nằm ở service

Với Spring và một transaction manager được cấu hình phù hợp, `@Transactional` thường thể hiện một ranh giới **logical transaction** của method. Khi method được gọi qua proxy do Spring quản lý, framework mở hoặc tham gia transaction, dùng kết nối được gắn vào ngữ cảnh hiện tại, rồi commit hoặc rollback theo kết quả method.

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final AccountRepository accountRepository;
    private final TransferRepository transferRepository;

    public PaymentService(AccountRepository accountRepository,
                          TransferRepository transferRepository) {
        this.accountRepository = accountRepository;
        this.transferRepository = transferRepository;
    }

    @Transactional
    public void transfer(long sourceId, long targetId, BigDecimal amount) {
        int debited = accountRepository.debitIfEnough(sourceId, amount);
        if (debited != 1) {
            throw new IllegalStateException("Insufficient balance");
        }

        int credited = accountRepository.credit(targetId, amount);
        if (credited != 1) {
            throw new IllegalStateException("Destination unavailable");
        }

        transferRepository.record(sourceId, targetId, amount);
    }
}
~~~

Nếu các repository tham gia **cùng transaction manager và cùng tài nguyên giao dịch**, ba lời gọi này có thể thuộc chung một transaction. Ngược lại, nếu mỗi repository tự chạy với autocommit và không có transaction bao ngoài, từng lời gọi có thể commit riêng.

Cần hiểu các giới hạn quan trọng:

- `@Transactional` không tự mở một transaction khi lời gọi **không đi qua cơ chế interception phù hợp**. Với kiểu proxy mặc định, method của đối tượng tự gọi method khác bằng `this.someTransactionalMethod()` thường không kích hoạt advice cho method được gọi nội bộ.
- Theo mặc định, cơ chế rollback thông dụng của Spring áp dụng cho **RuntimeException** và **Error**; checked exception cần cấu hình quy tắc rollback nếu nghiệp vụ yêu cầu, ví dụ `rollbackFor = Exception.class`. Không phải mọi exception đều có cùng chính sách.
- Nếu code **bắt rồi nuốt exception**, method có thể kết thúc bình thường và framework có thể commit, trừ khi transaction đã bị đánh dấu rollback-only hoặc có điều kiện khác buộc rollback.
- Propagation như `REQUIRED` thường tham gia transaction hiện có; `REQUIRES_NEW` tạo transaction độc lập, có thể commit dù transaction bao ngoài sau đó rollback. Cần dùng theo đúng ý nghĩa nghiệp vụ.
- Nếu `@Transactional` bao cả lời gọi HTTP chậm, transaction/connection/lock có thể bị giữ quá lâu. Phạm vi transaction nên tập trung vào thao tác dữ liệu cần nguyên tử.

Không nên suy luận rằng một annotation trên controller tự động bao mọi hệ thống tham gia request. Transaction manager điều phối **những tài nguyên mà nó thực sự quản lý**.

## 6. Cùng chuỗi SQL, ranh giới khác thì kết quả khác

Giả sử bảng `inventory` có một hàng cho sản phẩm P với số lượng ban đầu 1. Hai khách cùng muốn mua một sản phẩm.

### Trường hợp A — kiểm tra rồi trừ ở hai transaction riêng

~~~text
Khách A                               Khách B
-----------------------------------   -----------------------------------
SELECT quantity -> 1  [commit T1]
                                      SELECT quantity -> 1  [commit T2]
UPDATE inventory SET quantity = 0
WHERE product_id = P  [commit T3]
                                      UPDATE inventory SET quantity = 0
                                      WHERE product_id = P  [commit T4]
Cả hai request có thể được báo thành công nếu ứng dụng chỉ nhìn việc UPDATE chạy được.
~~~

Kết quả cuối vẫn là `quantity = 0`, nhưng nếu ứng dụng tạo hai đơn hàng thì thực tế đã **bán hai sản phẩm khi chỉ có một sản phẩm**. Đây là ví dụ về kiểm tra–rồi–hành động (*check-then-act*) không được đồng bộ phù hợp.

### Trường hợp B — mỗi request có một transaction nhưng vẫn dùng kiểm tra cũ

Đặt `BEGIN` trước `SELECT` rồi `COMMIT` sau `UPDATE` **không luôn đủ**. Trong mức cô lập cho phép hai transaction cùng nhìn số lượng 1, nếu code vẫn dùng `UPDATE quantity = 0` một cách vô điều kiện, cả hai thao tác có thể lần lượt cập nhật hàng mà không phát hiện đã bán quá lượng tồn.

Điều này cho thấy **ranh giới transaction** và **chiến lược bảo vệ invariant** là hai quyết định liên quan nhưng khác nhau. Có transaction là điều kiện cần cho nhiều luồng nghiệp vụ, không phải phép sửa tự động cho mọi race condition.

### Trường hợp C — dùng UPDATE có điều kiện và kiểm tra số hàng

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = :product_id
  AND quantity >= 1
RETURNING quantity;
~~~

Trong PostgreSQL ở `READ COMMITTED`, khi hai transaction cạnh tranh cập nhật cùng một hàng, cơ chế khóa hàng và việc đánh giá lại điều kiện cập nhật giúp chỉ một transaction trừ được đơn vị tồn cuối. Ứng dụng phải kiểm tra có đúng một hàng được cập nhật rồi mới tạo đơn hàng và commit.

~~~text
BEGIN;
UPDATE inventory ... WHERE quantity >= 1;
-- Nếu 0 hàng: ROLLBACK, trả trạng thái hết hàng.
INSERT INTO orders (...);
-- Nếu INSERT lỗi: ROLLBACK, hoàn tác cả việc trừ hàng.
COMMIT;
~~~

Ở đây **UPDATE có điều kiện bảo vệ cạnh tranh trên hàng tồn kho**, còn **transaction nhiều câu lệnh bảo vệ sự gắn kết giữa trừ tồn và ghi đơn hàng**. Cả hai cần có mặt để đáp ứng nghiệp vụ.

## 7. Cách isolation thay đổi những gì các câu lệnh nhìn thấy

Khi nhiều câu lệnh nằm trong một transaction, không có nghĩa tất cả câu `SELECT` luôn nhìn cùng một ảnh chụp dữ liệu. Cách đọc phụ thuộc mức cô lập và cơ chế của database.

Ví dụ hai transaction T1 và T2 cùng đọc số lượng:

~~~text
T1: BEGIN;
T1: SELECT quantity FROM inventory WHERE product_id = 5;  -- thấy 10

T2: BEGIN;
T2: UPDATE inventory SET quantity = 9 WHERE product_id = 5;
T2: COMMIT;

T1: SELECT quantity FROM inventory WHERE product_id = 5;  -- thấy gì?
T1: COMMIT;
~~~

Với **PostgreSQL**:

| Mức cô lập của T1 | Kết quả có thể quan sát ở SELECT thứ hai |
|---|---|
| READ COMMITTED | Có thể thấy **9**, vì mỗi câu lệnh bắt đầu với snapshot mới của dữ liệu đã commit (vẫn có ngoại lệ ngữ nghĩa với một số lệnh/khóa). |
| REPEATABLE READ | Thường vẫn thấy **10** vì các lần đọc thông thường dùng cùng snapshot của transaction. |
| SERIALIZABLE | Bảo đảm kết quả transaction thành công tương đương một thứ tự tuần tự; có thể phải hủy và retry transaction khi phát hiện xung đột không thể tuần tự hóa. |

Không nên áp đặt tên isolation level của một hệ quản trị cho tất cả các hệ quản trị khác. Ví dụ, cách triển khai `REPEATABLE READ` hoặc `READ COMMITTED` của PostgreSQL và MySQL/InnoDB có khác biệt ở một số loại đọc/ghi.

Một transaction nhiều câu lệnh có thể thấy **thay đổi của chính mình**; các snapshot nói trên chủ yếu liên quan đến thay đổi được commit bởi transaction **khác**.

## 8. Khóa và thời điểm giải phóng: ảnh hưởng trực tiếp từ ranh giới

Ranh giới transaction quyết định thời điểm giải phóng nhiều loại khóa dữ liệu.

~~~sql
BEGIN;

SELECT id, balance
FROM accounts
WHERE id = 100
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và thực hiện các cập nhật liên quan.

COMMIT;
~~~

`SELECT ... FOR UPDATE` trong PostgreSQL khóa hàng được chọn để phối hợp các giao dịch cập nhật cạnh tranh. Khóa giữ qua những câu lệnh tiếp theo của **cùng transaction**, thường đến khi transaction kết thúc (một số thay đổi do savepoint/rollback có quy tắc cụ thể).

Nếu thực hiện `SELECT ... FOR UPDATE` như một statement autocommit độc lập rồi mới chạy `UPDATE`, khóa đã được giải phóng khi statement transaction đó kết thúc, nên không còn bảo vệ khoảng thời gian từ lúc kiểm tra đến lúc cập nhật sau đó.

Ngược lại, transaction quá dài có thể tạo ra:

- Hàng bị khóa lâu, request khác phải chờ.
- Deadlock nếu hai transaction lần lượt khóa nhiều hàng theo thứ tự ngược nhau.
- Tăng tài nguyên giữ snapshot hoặc phiên bản dữ liệu cũ, tùy cơ chế MVCC và database.
- Tăng độ trễ và nguy cơ timeout, làm khó việc retry.

**Ranh giới hợp lý** thường bao phủ đúng các bước cần tính nguyên tử, nhất quán và phối hợp cạnh tranh; tránh mở transaction rồi chờ người dùng, gọi API chậm hoặc thực hiện xử lý không liên quan trong thời gian dài.

## 9. SAVEPOINT: điểm quay lại bên trong một transaction

`SAVEPOINT` cho phép đặt điểm khôi phục trong một transaction, hữu ích khi một thao tác con có thể thất bại nhưng phần còn lại vẫn có thể tiếp tục theo quy tắc nghiệp vụ.

Ví dụ PostgreSQL:

~~~sql
BEGIN;

INSERT INTO orders(id, customer_id) VALUES (501, 42);

SAVEPOINT optional_coupon;

-- Thử áp mã giảm giá tùy chọn.
INSERT INTO order_coupons(order_id, coupon_code)
VALUES (501, 'WELCOME');

-- Nếu mã không hợp lệ/lệnh trên lỗi:
ROLLBACK TO SAVEPOINT optional_coupon;

-- Có thể tiếp tục các bước hợp lệ khác sau khi khôi phục.
INSERT INTO order_audit(order_id, action)
VALUES (501, 'CREATED');

COMMIT;
~~~

Ví dụ diễn tả một **nhánh xử lý tùy điều kiện**: `ROLLBACK TO SAVEPOINT` chỉ được gọi nếu nghiệp vụ quyết định bỏ phần áp mã; nếu áp mã thành công và muốn giữ nó, không rollback về savepoint.

Savepoint **không phải transaction độc lập**:

- `RELEASE SAVEPOINT` không đồng nghĩa commit toàn transaction.
- Nếu transaction bên ngoài rollback, cả các thay đổi từng được giữ lại sau savepoint cũng bị rollback.
- Một lệnh có lỗi và một số khóa có thể có hành vi riêng khi rollback về savepoint, tùy hệ quản trị.
- Savepoint không đảo ngược tác động bên ngoài database như email đã gửi hay khoản thanh toán đã thực hiện qua API.

## 10. Những ngộ nhận khi chọn ranh giới

| Ngộ nhận | Thực tế |
|---|---|
| “Hai câu SQL nằm cùng một hàm nên cùng transaction.” | Phải có ranh giới transaction thực tế được driver/framework quản lý. |
| “Dùng chung Connection luôn là một transaction.” | Với autocommit bật, các câu SQL kế tiếp có thể được commit riêng. |
| “Có BEGIN thì mọi lỗi tự rollback toàn bộ ngay.” | Phụ thuộc hành vi DBMS; ứng dụng cần xử lý lỗi và xác định rollback/rollback-to-savepoint. |
| “Mỗi câu lệnh thành công tức toàn nghiệp vụ thành công.” | Thành công một statement không xác nhận những statement khác đã chạy hay đã commit. |
| “Mọi SELECT trong cùng transaction đọc đúng cùng snapshot.” | Phụ thuộc isolation level và loại thao tác đọc. |
| “Đặt `@Transactional` ở một method bất kỳ là luôn có hiệu lực.” | Phụ thuộc transaction manager, proxy/interception và cách method được gọi. |
| “Transaction bao được gọi HTTP hoặc message broker.” | Một transaction database cục bộ không tự đảo ngược hay commit đồng bộ tác động ở hệ thống khác. |
| “Thay đổi autocommit chỉ là tùy chọn hiệu năng.” | Nó thay đổi ranh giới commit, do đó thay đổi tính nguyên tử của chuỗi thao tác. |

### Lưu ý khác biệt giữa các hệ quản trị

Không phải câu lệnh nào cũng tuân theo cùng quy tắc commit ở mọi hệ quản trị.

- Trong **PostgreSQL**, nhiều lệnh DDL thông dụng có thể được thực hiện trong transaction và rollback; một số thao tác đặc biệt không được phép trong transaction block.
- Trong **MySQL**, nhiều lệnh DDL gây **implicit commit**; đừng giả định `BEGIN; ALTER TABLE ...; ROLLBACK;` luôn quay lại toàn bộ thay đổi.
- Với MySQL, hành vi transaction còn phụ thuộc **storage engine**. InnoDB hỗ trợ transaction; bảng dùng engine không có transaction không tuân cùng giả định rollback.
- Một số API client có hỗ trợ **pipeline hoặc gửi nhiều statement trong một round trip**. Số lần gửi request qua mạng không nhất thiết tương ứng số transaction. Muốn chắc chắn ranh giới, xem hành vi của driver, cấu hình autocommit và quy tắc DBMS.

Vì thế, các ví dụ SQL trong bài nên được hiểu theo môi trường PostgreSQL đã nêu, rồi đối chiếu với hệ quản trị đang dùng khi triển khai thực tế.

## 11. Khi một nghiệp vụ vượt qua một database transaction

Một request đặt hàng có thể yêu cầu ba việc:

1. Trừ tồn kho trong database.
2. Gọi cổng thanh toán.
3. Gửi email xác nhận.

Ngay cả khi bước 1 nằm trong transaction, lời gọi thanh toán ở bước 2 không mặc nhiên tham gia vào `COMMIT` hoặc `ROLLBACK` của database. Nếu thanh toán thành công nhưng transaction cơ sở dữ liệu sau đó rollback, hệ thống cần cơ chế xử lý riêng.

Một mô hình hay dùng cho sự kiện sau commit:

~~~text
BEGIN TRANSACTION
    UPDATE inventory ...
    INSERT INTO orders ...
    INSERT INTO outbox_events ...
COMMIT

Worker:
    Đọc outbox đã commit
    Gửi thông điệp
    Đánh dấu đã xử lý / retry nếu cần
~~~

Outbox giúp **dữ liệu nghiệp vụ và ý định phát thông điệp cùng được commit trong một transaction DB**. Worker xử lý gửi sau commit; vì thông điệp có thể bị gửi lặp khi retry, bên nhận vẫn cần idempotency. Với thanh toán ngoài database, có thể cần mô hình quy trình dài như saga, xác nhận và bù trừ tùy trường hợp.

Đây là ranh giới khác biệt giữa **transaction cục bộ** và **giao dịch nghiệp vụ xuyên hệ thống**. Không nên kéo một transaction DB mở chờ mọi dịch vụ hoàn thành rồi kỳ vọng nó trở thành một distributed transaction an toàn.

## 12. Một quy trình thiết kế ranh giới transaction

Với mỗi thao tác nghiệp vụ, có thể đi theo các câu hỏi sau:

1. **Kết quả nào phải cùng thành công hoặc cùng thất bại?** Nếu “trừ tồn” và “tạo đơn” phải đi cùng nhau, chúng cần chung transaction cục bộ khi cùng nằm trong một database hỗ trợ transaction.
2. **Câu lệnh nào chỉ kiểm tra, câu nào thực sự ghi?** Đừng dựa vào một `SELECT` đã commit riêng để tin dữ liệu vẫn không đổi khi thực hiện `UPDATE`.
3. **Bất biến nào phải được bảo vệ trước cạnh tranh?** Sử dụng UNIQUE, CHECK, FK, UPDATE có điều kiện, khóa hàng hoặc isolation phù hợp. Transaction nhiều câu lệnh không tự ngăn mọi write skew và race condition.
4. **Ai sở hữu ranh giới?** Ở JDBC là đoạn code kiểm soát Connection/commit; ở Spring là transaction manager và điểm interception của service.
5. **Khi lỗi thì transaction đi đâu?** Xác định khi nào rollback, khi nào retry toàn transaction, khi nào báo lỗi nghiệp vụ và khi nào cần tra lại kết quả một commit chưa rõ.
6. **Có bước nào không nằm trong database?** Tách tác động ngoài hệ thống bằng một cơ chế phối hợp thích hợp, thay vì tưởng rằng rollback SQL hoàn tác được mọi thứ.

### Bài tập thực hành

Giả sử API đăng ký học phần cần thêm sinh viên vào lớp và tăng `enrolled_count`. Mỗi lớp có giới hạn `capacity`.

**Phương án 1:**

~~~sql
-- autocommit bật
INSERT INTO enrollments(student_id, class_id)
VALUES (:student_id, :class_id);

UPDATE classes
SET enrolled_count = enrolled_count + 1
WHERE id = :class_id;
~~~

**Phương án 2:**

~~~sql
BEGIN;

UPDATE classes
SET enrolled_count = enrolled_count + 1
WHERE id = :class_id
  AND enrolled_count < capacity
RETURNING id;

-- Nếu không cập nhật đúng một hàng: ROLLBACK.
-- Nếu được: INSERT enrollment, kiểm tra lỗi rồi COMMIT.

INSERT INTO enrollments(student_id, class_id)
VALUES (:student_id, :class_id);

COMMIT;
~~~

Hãy giải thích:

- Ở phương án 1, điều gì xảy ra nếu INSERT đã commit nhưng UPDATE sau đó lỗi?
- Ở phương án 2, tại sao cần kiểm tra số hàng trả về từ UPDATE thay vì chỉ kiểm tra xem có exception không?
- Vì sao cần constraint chống một sinh viên đăng ký trùng cùng lớp, ví dụ `UNIQUE(student_id, class_id)`?
- Nếu hai request cùng đăng ký ghế cuối cùng, vì sao điều kiện `enrolled_count < capacity` gắn trực tiếp với UPDATE tốt hơn một SELECT kiểm tra ở ngoài transaction?
- Nếu transaction bị lỗi serialization hoặc deadlock, cần retry cả hai câu lệnh và bước kiểm tra theo logic nào?

**Điều cần nắm vững:** Một statement là đơn vị thực thi SQL; một transaction là ranh giới xác nhận hoặc hoàn tác. Đặt nhiều statement vào cùng transaction giúp bảo vệ tính nguyên tử của cả chuỗi, trong khi ràng buộc dữ liệu, cách ghi có điều kiện, khóa và isolation tiếp tục quyết định chuỗi đó có đúng dưới cạnh tranh đồng thời hay không. Ứng dụng phải xác định ranh giới, kiểm tra kết quả và xử lý toàn bộ vòng đời từ bắt đầu đến commit, rollback hoặc retry.
