# Đặt ranh giới giữa lớp truy cập dữ liệu và logic nghiệp vụ trong JDBC

## 1. Vấn đề kiến trúc: Ai quyết định *làm gì*, ai quyết định *lưu như thế nào*?

**JDBC (Java Database Connectivity)** là API của Java để làm việc với cơ sở dữ liệu quan hệ: lấy `Connection`, thực thi SQL, đọc `ResultSet` và quản lý giao dịch. JDBC cung cấp các công cụ kỹ thuật, nhưng không tự quyết định nên chia mã nguồn thành những lớp nào. Trong chương **Kiến trúc JDBC**, một ranh giới quan trọng là phân biệt:

- **Logic nghiệp vụ (business logic):** quy tắc của hệ thống, chẳng hạn số tiền chuyển phải dương, người dùng được phép thực hiện thao tác, hai tài khoản phải khác nhau, và các bước nào cần thành công cùng nhau.
- **Lớp truy cập dữ liệu (data access):** cách biến yêu cầu đọc/ghi thành câu SQL, truyền tham số, ánh xạ hàng dữ liệu về đối tượng Java, kiểm tra số dòng bị tác động và quản lý tài nguyên của từng câu lệnh.

Ví dụ yêu cầu “chuyển 200.000 đồng từ tài khoản A sang B” có hai nhóm quyết định:

| Câu hỏi | Lớp nên chịu trách nhiệm |
| --- | --- |
| Số tiền âm, bằng 0 hay chuyển cho chính mình có hợp lệ không? | **Service / nghiệp vụ** |
| Cần trừ tiền và cộng tiền trong cùng một giao dịch không? | **Service / điều phối nghiệp vụ** |
| Cập nhật cột `balance` bằng SQL nào? | **DAO / repository** |
| Dùng `PreparedStatement.setBigDecimal` như thế nào? | **DAO / repository** |
| Nếu không có dòng nào được trừ tiền, có nghĩa nghiệp vụ là gì? | DAO báo kết quả; **service diễn giải** thành lỗi nghiệp vụ phù hợp |
| Bao giờ `commit()` hoặc `rollback()` cho cả hai bước? | **Lớp sở hữu giao dịch** (service hoặc transaction manager) |

Mục tiêu là để sửa một quy tắc nghiệp vụ không buộc phải thay đổi cơ chế đọc `ResultSet`, và thay đổi bảng/câu SQL không lan ra toàn bộ logic đặt hàng, thanh toán hay xử lý người dùng.

## 2. Sơ đồ phân lớp: Controller → Service → DAO → Database

Một ứng dụng Java đơn giản có thể chia theo luồng sau:

~~~mermaid
flowchart TD
    A["Controller / API / CLI"] -->|"Yêu cầu, DTO đầu vào"| B["Application Service"]
    B -->|"Gọi thao tác nghiệp vụ trên dữ liệu"| C["DAO / Repository"]
    C -->|"JDBC: PreparedStatement, ResultSet"| D[("Cơ sở dữ liệu quan hệ")]
    D --> C
    C -->|"Bản ghi/đối tượng kết quả"| B
    B -->|"Kết quả hoặc lỗi nghiệp vụ"| A
~~~

**Controller hoặc API adapter** nhận dữ liệu HTTP, xử lý xác thực/định dạng phản hồi theo cơ chế của tầng giao tiếp. **Service** dùng các quy tắc nghiệp vụ để điều phối một hoặc nhiều DAO. **DAO** biết cấu trúc lưu trữ và thao tác JDBC. **Database** thực thi SQL, cung cấp ràng buộc và các tính chất giao dịch theo DBMS.

Đây là sơ đồ *trách nhiệm*, không bắt buộc mỗi chương trình phải có đúng ba lớp hoặc một DAO cho mỗi bảng. Với chương trình nhỏ, có thể gom một số phần, miễn là ranh giới giữa **quyết định nghiệp vụ** và **chi tiết JDBC** vẫn rõ ràng.

### DAO và repository có khác nhau?

- **DAO (Data Access Object)** thường mô tả một nhóm phương thức thao tác dữ liệu bằng các API gần với bảng và truy vấn, ví dụ `findById`, `insert`, `updateBalance`.
- **Repository** thường được mô hình hóa theo khái niệm miền nghiệp vụ (domain), ví dụ `AccountRepository`, và có thể che giấu hoàn toàn cách lưu dữ liệu phía sau giao diện.

Trong thực tế, tên hai kiểu lớp đôi khi được dùng thay nhau. Tên gọi không quyết định chất lượng thiết kế; **hợp đồng của phương thức và chiều phụ thuộc** mới quyết định xem logic nghiệp vụ có bị trộn với truy cập dữ liệu hay không.

## 3. Dấu hiệu đang đặt sai ranh giới

Xem phương thức dưới đây:

~~~java
// Ví dụ cần tránh: trộn nghiệp vụ và JDBC trong cùng phương thức.
public void transfer(Connection connection, long fromId, long toId,
                     BigDecimal amount) throws SQLException {
    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Số tiền phải dương");
    }

    try (PreparedStatement debit = connection.prepareStatement(
            "UPDATE account SET balance = balance - ? WHERE id = ?")) {
        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromId);
        debit.executeUpdate();
    }

    // Tiếp tục kiểm tra quy tắc nghiệp vụ, cộng tiền, tự quyết định commit...
}
~~~

Đoạn mã này không bảo đảm đủ các quy tắc chuyển tiền và dễ xuất hiện lỗi thiếu kiểm tra số dòng, số dư hoặc giao dịch. Quan trọng hơn, khi service trực tiếp chứa nhiều `PreparedStatement`, SQL và ánh xạ dữ liệu, một thay đổi ở schema sẽ buộc sửa lớp chuyên điều phối nghiệp vụ.

Các dấu hiệu thường gặp:

1. **Controller có SQL**: đổi URL hoặc API lại phải đọc/đổi câu `UPDATE`.
2. **DAO quyết định cả luồng nghiệp vụ**: một DAO tự gửi email, tính khuyến mãi, gọi thanh toán và quyết định ngoại lệ nghiệp vụ.
3. **DAO tự mở kết nối rồi tự commit cho từng bước**: service không thể gom hai cập nhật thành một giao dịch chung.
4. **Service phụ thuộc dữ liệu dạng `ResultSet`**: code nghiệp vụ phải biết tên cột và cần giữ kết nối mở.
5. **Một phương thức vừa duyệt cursor vừa tạo phản hồi HTTP**: lỗi database, mapping và giao tiếp người dùng bị kết dính.

Ranh giới phù hợp sẽ giúp các phần này thay đổi tương đối độc lập và dễ kiểm thử hơn.

## 4. Thiết kế hợp đồng giữa service và lớp dữ liệu

Thay vì trả `ResultSet` ra ngoài DAO, hãy trả **đối tượng dữ liệu đã ánh xạ** hoặc giá trị đơn giản mang ý nghĩa rõ ràng:

~~~java
// Record Java 16+; có thể thay bằng POJO cho dự án dùng Java cũ.
public record Account(long id, BigDecimal balance) {}

public interface AccountReader {
    Optional<Account> findById(long id);
}
~~~

Một service dùng `Optional<Account>` hoặc đối tượng `Account` không cần biết cột trong `ResultSet` tên gì. Nếu việc truy cập dữ liệu cần báo lỗi, hợp đồng nên thống nhất cách chuyển lỗi kỹ thuật (`SQLException`, lỗi mạng, timeout...) thành ngoại lệ tầng dữ liệu hoặc lỗi nghiệp vụ ở tầng thích hợp.

Ví dụ ranh giới được gợi ý:

| Đầu vào/đầu ra | Lợi ích |
| --- | --- |
| `findById(id) -> Optional<Account>` | Phân biệt rõ có/không có đối tượng; không để `ResultSet` lọt ra ngoài. |
| `debitIfEnough(id, amount) -> int` | DAO báo **số hàng được cập nhật**; service diễn giải kết quả trong nghiệp vụ. |
| `create(order) -> OrderId` | Cô lập chi tiết lấy generated keys/insert. |
| `listByCustomer(customerId) -> List<Order>` | Chuyển kết quả nhiều dòng thành collection Java; trả dữ liệu dùng được sau khi đóng JDBC. |

Hợp đồng không nhất thiết phải khớp từng dòng SQL. Ví dụ `debitIfEnough` có thể là một phương thức hợp lệ của DAO dù câu `UPDATE` bên dưới chứa điều kiện `balance >= ?`: điều kiện này giúp thực hiện thao tác trừ tiền **nguyên tử trong database**, giảm rủi ro khi nhiều giao dịch cùng cập nhật số dư. Quy tắc *có chấp nhận chuyển tiền hay không* vẫn do service quyết định dựa trên kết quả.

### Chọn kiểu dữ liệu đi qua ranh giới

Nên ưu tiên các kiểu Java tự chứa như `long`, `BigDecimal`, `String`, `record`, `List<...>`, `Optional<...>` hoặc các kiểu domain. Cẩn thận khi đưa ra ngoài DAO:

- `ResultSet`, `Statement`: phụ thuộc vào cursor và tài nguyên JDBC còn mở.
- `Connection`: là chi tiết hạ tầng; nếu xuất hiện ở service thì service phải hiểu vòng đời và giao dịch.
- Chuỗi tên cột, thứ tự cột, câu SQL: khiến logic nghiệp vụ phụ thuộc trực tiếp vào schema.

Không phải lúc nào cũng cấm `Connection` đi qua service. Khi **tự quản lý giao dịch bằng JDBC thuần**, đây có thể là lựa chọn thực dụng. Tuy nhiên, cần nhận diện đây là một phụ thuộc kỹ thuật và giới hạn nó ở đúng tầng điều phối giao dịch.

## 5. Ví dụ Java: service điều phối, DAO chịu trách nhiệm SQL

Giả sử bảng tài khoản có cấu trúc:

~~~sql
CREATE TABLE account (
    id      BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL,
    CONSTRAINT account_balance_nonnegative CHECK (balance >= 0)
);
~~~

Ví dụ dùng `javax.sql.DataSource` và JDBC chuẩn. Các phần sau có thể đặt trong những file Java riêng cùng package. Để tập trung vào ranh giới lớp, ví dụ không bao gồm xác thực người dùng hay thanh toán bên ngoài database.

### 5.1. DAO chỉ thao tác dữ liệu

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class AccountDao {
    // Điều kiện balance >= ? được kiểm tra cùng lúc với phép cập nhật.
    // 0 dòng: không có tài khoản hoặc không đủ số dư tại thời điểm UPDATE.
    public int debitIfEnough(Connection c, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE account SET balance = balance - ? "
                   + "WHERE id = ? AND balance >= ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            ps.setBigDecimal(3, amount);
            return ps.executeUpdate();
        }
    }

    // 0 dòng: tài khoản đích không tồn tại.
    public int credit(Connection c, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE account SET balance = balance + ? WHERE id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            return ps.executeUpdate();
        }
    }
}
~~~

DAO chỉ biết SQL và cách gán tham số. Nó **không gọi** `dataSource.getConnection()`, `commit()`, `rollback()` hoặc `Connection.close()` vì trong ví dụ này, các thao tác có thể thuộc cùng một giao dịch do service quản lý. DAO chỉ đóng `PreparedStatement` do chính nó tạo.

Việc trả về `int` thay vì tự ném lỗi “không đủ tiền” cho phép service quyết định cách diễn giải kết quả. Nếu các yêu cầu khác có ngữ nghĩa riêng, có thể trả một kiểu kết quả chuyên biệt để giao diện rõ ràng hơn.

### 5.2. Service xác định quy tắc và ranh giới giao dịch

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;
    private final AccountDao accountDao;

    public TransferService(DataSource dataSource, AccountDao accountDao) {
        this.dataSource = dataSource;
        this.accountDao = accountDao;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        // Luật nghiệp vụ đặt ở service, không nằm trong SQL/JDBC.
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
        }
        if (fromId == toId) {
            throw new IllegalArgumentException(
                    "Tài khoản nguồn và đích phải khác nhau");
        }

        // Một Connection được dùng xuyên suốt toàn bộ giao dịch.
        try (Connection c = dataSource.getConnection()) {
            // Giả định pool trả về một Connection sạch, bật autoCommit.
            if (!c.getAutoCommit()) {
                throw new SQLException(
                        "Cần một kết nối mới, đang bật autoCommit");
            }
            c.setAutoCommit(false);
            boolean finished = false;

            try {
                int debited = accountDao.debitIfEnough(c, fromId, amount);
                if (debited != 1) {
                    throw new IllegalStateException(
                            "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
                }

                int credited = accountDao.credit(c, toId, amount);
                if (credited != 1) {
                    throw new IllegalStateException(
                            "Tài khoản đích không tồn tại");
                }

                c.commit();
                finished = true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                    finished = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Chỉ bật lại autoCommit khi transaction đã kết thúc.
                // Nếu rollback thất bại, cần tránh commit ngầm khi đổi chế độ.
                if (finished) {
                    c.setAutoCommit(true);
                }
            }
        }
    }
}
~~~

**Luồng thực tế** khi gọi `transfer(1, 2, new BigDecimal("200000.00"))`:

1. Service kiểm tra số tiền và hai tài khoản.
2. Service lấy **một `Connection`**, tắt `autoCommit`.
3. Service gọi `AccountDao.debitIfEnough(c, ...)` rồi `AccountDao.credit(c, ...)` với **cùng đối tượng `c`**.
4. DAO tự quản lý `PreparedStatement` của từng lệnh SQL và trả số hàng tác động.
5. Service quyết định `commit()` nếu cả hai lệnh thành công; nếu lỗi, cố gắng `rollback()`.
6. Khi giao dịch đã kết thúc, service khôi phục `autoCommit` và đóng/trả kết nối qua `try-with-resources`.

Nếu thao tác trừ tiền đã chạy nhưng tài khoản đích không tồn tại, service ném lỗi và yêu cầu rollback. Các thay đổi chưa commit trên kết nối đó được hoàn tác nếu rollback thành công.

**Giới hạn của ví dụ:** `DataSource` phải trả về kết nối hợp lệ, sạch, chưa có giao dịch do bên khác quản lý. Việc khôi phục kết nối hỏng hoặc giao dịch đang ở trạng thái không xác định thuộc chính sách của connection pool; không nên đưa kết nối đó trở lại sử dụng nếu driver/pool không thể đảm bảo trạng thái. Khi `commit()` báo lỗi vì mất mạng, kết quả commit có thể không xác định; các nghiệp vụ tiền tệ còn cần cơ chế chống xử lý trùng và kiểm soát đồng thời phù hợp.

### 5.3. Controller không viết SQL

Với lớp điều khiển HTTP (mã khái niệm):

~~~java
// Phần xử lý HTTP được rút gọn để minh họa trách nhiệm.
void handleTransfer(long fromId, long toId, BigDecimal amount)
        throws SQLException {
    transferService.transfer(fromId, toId, amount);
    // Tầng HTTP chọn mã trạng thái/thông điệp phù hợp.
}
~~~

Controller không biết câu `UPDATE`, không nhận `ResultSet` và không tự quyết định `commit/rollback`. Nó chỉ tiếp nhận đầu vào, gọi service và chuyển kết quả/lỗi sang định dạng giao tiếp phù hợp.

## 6. Quyền sở hữu Connection: ranh giới giao dịch đi xuyên các DAO

Đây là điểm dễ sai nhất khi dùng JDBC thuần. **Giao dịch JDBC cục bộ gắn với một `Connection`**, không gắn với tên service, tên DAO hay một lời gọi HTTP.

Nếu viết:

~~~java
class AccountDaoWrong {
    private final DataSource dataSource;

    AccountDaoWrong(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void debit(/* ... */) throws SQLException {
        try (Connection c1 = dataSource.getConnection()) {
            // UPDATE tài khoản nguồn trên c1
        }
    }

    void credit(/* ... */) throws SQLException {
        try (Connection c2 = dataSource.getConnection()) {
            // UPDATE tài khoản đích trên c2
        }
    }
}
~~~

thì hai phương thức có thể dùng hai kết nối khác nhau. `c1.rollback()` không thể hoàn tác dữ liệu đã được commit ở `c2`. Ngay cả khi cả hai cùng dùng một `DataSource` và cùng một DBMS, điều đó **không tạo ra** một giao dịch chung.

Các cách điều phối thường gặp:

| Cách thiết kế | Cơ chế chia sẻ giao dịch | Lưu ý |
| --- | --- | --- |
| **JDBC thuần, truyền `Connection`** | Service lấy `Connection` và truyền cho các DAO | Đơn giản, rõ ràng; service biết một phần API JDBC. |
| **Transaction manager / Unit of Work** | Lớp điều phối giao dịch cung cấp ngữ cảnh; các repository dùng kết nối được quản lý | Giảm dấu vết JDBC trong service; cần cấu hình và giao ước nhất quán. |
| **Framework như Spring + `@Transactional`** | Transaction manager giữ kết nối/nguồn lực trong ngữ cảnh giao dịch và các thành phần truy cập dữ liệu tham gia | Phải dùng đúng transaction manager và API truy cập dữ liệu; tự lấy kết nối không được quản lý có thể thoát giao dịch. |

Trong cách **JDBC thuần** ở mục 5, service sở hữu `Connection` vì nó đang sở hữu ranh giới nghiệp vụ. Một lựa chọn kiến trúc khác là đặt việc mở/đóng kết nối, `commit/rollback` vào một lớp `TransactionRunner` chuyên trách. Khi đó service chỉ đưa *hành động nghiệp vụ cần nguyên tử* cho transaction runner, còn DAO nhận cùng kết nối trong ngữ cảnh đó. Cách này đòi hỏi thêm abstraction, phù hợp khi có nhiều service phải lặp lại đoạn quản lý giao dịch.

Không được “sửa” một hệ thống đang dùng transaction manager bằng cách cho DAO tự `commit()`: việc đó có thể kết thúc giao dịch trước khi service hoàn thành các bước nghiệp vụ khác.

## 7. Ranh giới xử lý lỗi: kỹ thuật và nghiệp vụ

`SQLException` biểu diễn lỗi khi JDBC làm việc với SQL hoặc cơ sở dữ liệu. Nó có thể chứa `SQLState`, mã lỗi nhà cung cấp, hoặc chuỗi ngoại lệ phụ. Nhưng “không đủ tiền”, “đơn hàng đã khóa”, “khách hàng không có quyền” lại là **ý nghĩa nghiệp vụ**.

Một cách phân chia hợp lý:

| Tình huống | DAO biết gì? | Service quyết định gì? |
| --- | --- | --- |
| `UPDATE` trả 0 dòng | Không có dòng thỏa điều kiện tại thời điểm SQL chạy | Đây có phải “không tồn tại”, “không đủ số dư” hay một xung đột nghiệp vụ? |
| Vi phạm khóa duy nhất | DBMS trả mã lỗi/ràng buộc tương ứng | Có báo “mã đã tồn tại” hoặc kết quả xử lý trùng hay không? |
| Mất kết nối với DB | Driver ném `SQLException` | Bước nghiệp vụ nào thất bại, có thể retry an toàn không? |
| Đầu vào có `amount <= 0` | Không cần truy cập DB | Từ chối yêu cầu trước khi gọi DAO. |

Có thể viết một lớp **adapter lỗi truy cập dữ liệu** để chuẩn hóa lỗi database thành `DataAccessException`, trong khi service dùng lỗi nghiệp vụ như `InsufficientFundsException`. Tuy nhiên, tránh bắt mọi `SQLException` rồi mặc định coi là lỗi nghiệp vụ: timeout, lỗi driver và vi phạm ràng buộc có cách khắc phục khác nhau.

Trong đoạn ví dụ để học JDBC, service khai báo `throws SQLException` nhằm giữ luồng kỹ thuật rõ ràng. Ở kiến trúc nhiều tầng lớn hơn, thường nên che loại ngoại lệ JDBC khỏi API nghiệp vụ công khai bằng một lớp chuyển đổi thích hợp, giữ nguyên nguyên nhân gốc để chẩn đoán.

Không được “nuốt lỗi” như sau:

~~~java
// Không nên: khiến tầng nghiệp vụ hiểu nhầm lỗi SQL là không có dữ liệu.
try {
    return loadAccounts();
} catch (SQLException error) {
    return java.util.List.of();
}
~~~

Danh sách trống là một **kết quả hợp lệ** và có ý nghĩa khác với thất bại truy cập cơ sở dữ liệu. Việc trộn hai trường hợp tạo ra những lỗi nghiệp vụ khó phát hiện.

## 8. Kiểm thử ranh giới: kiểm thử service và DAO theo trách nhiệm

Tách lớp tạo ra hai loại kiểm thử bổ trợ:

**Kiểm thử service (unit test):** truyền một `AccountDao` giả hoặc một giao diện `AccountStore` với hành vi được điều khiển. Kiểm tra logic như “số tiền âm bị từ chối trước khi gọi dữ liệu”, “0 dòng cập nhật dẫn tới lỗi nghiệp vụ”, hoặc “khi bước hai thất bại thì transaction runner được yêu cầu rollback”. Nếu service vẫn trực tiếp sở hữu `Connection`, cần thay thế thêm `DataSource/Connection` bằng test double hoặc trích riêng logic giao dịch để kiểm thử gọn hơn.

**Kiểm thử DAO (integration test):** dùng DBMS thử nghiệm phù hợp để xác nhận SQL, tên cột, ràng buộc, `ResultSet` mapping, giá trị `NULL`, số dòng được cập nhật và hành vi khi nhiều giao dịch cạnh tranh. Chạy trên đúng loại DBMS của production khi có thể, bởi cú pháp SQL, isolation và driver có khác biệt.

**Kiểm thử giao dịch:** khởi tạo hai tài khoản, ép thao tác thứ hai thất bại, kiểm tra số dư của cả hai không đổi sau rollback; sau đó thử hai thao tác thành công và kiểm tra tổng tiền được bảo toàn. Đây là kiểm tra của *toàn bộ luồng service + DAO + database*, không thể chứng minh chỉ bằng một unit test mock `PreparedStatement`.

Sơ đồ kiểm thử:

~~~mermaid
flowchart LR
    U["Unit test: quy tắc service"] --> S["Service"]
    I["Integration test: SQL và mapping"] --> D["DAO"]
    E["Integration test: nghiệp vụ + rollback"] --> S
    S --> D
    D --> DB[("Test database")]
~~~

## 9. Các tình huống thiết kế và cách lựa chọn

### 9.1. Một câu SELECT đơn giản

Với yêu cầu “tìm sản phẩm theo ID”, một repository `findById()` có thể tự mượn/đóng kết nối nếu phương thức được sử dụng **độc lập** và không cần tham gia giao dịch lớn hơn. Nếu muốn gọi nó trong giao dịch do service quản lý, thiết kế cần có cách chia sẻ kết nối hoặc ngữ cảnh giao dịch; trộn hai cơ chế tùy tiện sẽ làm ranh giới khó hiểu.

### 9.2. Nhiều thao tác ghi phải thành công cùng nhau

Với “tạo đơn hàng và trừ tồn kho”, service cần sở hữu một ranh giới giao dịch đi qua cả `OrderDao` và `InventoryDao`. Mỗi DAO không được tự commit trước khi service kiểm tra toàn bộ điều kiện nghiệp vụ.

### 9.3. Có API ngoài database

Nếu quy trình gồm ghi đơn hàng, gọi cổng thanh toán và gửi email, rollback JDBC **không thể hoàn tác** yêu cầu API đã gửi hoặc email đã phát. Tách lớp giúp bạn nhận ra hành động nào là SQL trong cùng DB và hành động nào cần quy trình phối hợp riêng (outbox, saga, idempotency, cơ chế bù trừ...). Không nên giữ giao dịch DB mở trong lúc chờ một dịch vụ mạng chậm nếu có phương án thiết kế tốt hơn.

### 9.4. Logic phức tạp có nên đặt trong câu SQL?

Một số điều kiện cần nằm **ngay trong SQL** để giữ tính nguyên tử, như `UPDATE ... WHERE balance >= ?`. Một số quy tắc cần được cưỡng chế bằng constraint của database, ví dụ `CHECK (balance >= 0)`, `UNIQUE`, khóa ngoại. Điều này không mâu thuẫn với việc service quyết định nghiệp vụ: **service xác định quy tắc và điều phối**, còn DAO/DBMS triển khai các thao tác sao cho dữ liệu nhất quán khi nhiều truy cập đồng thời.

Không nên nhất quyết chuyển mọi kiểm tra sang `if` trong Java. Ví dụ “đọc số dư trước, kiểm tra ở Java, rồi cập nhật sau” có thể xảy ra race condition khi có nhiều kết nối đồng thời; cần câu SQL nguyên tử, locking/isolation phù hợp hoặc chiến lược kiểm soát cạnh tranh.

## 10. Checklist để tự rà soát thiết kế JDBC

- **Controller/API:** có chỉ chuyển đổi yêu cầu và kết quả, tránh chứa SQL và quyền quyết định giao dịch không?
- **Service:** có thể đọc phương thức nghiệp vụ mà không phải hiểu từng câu SQL hoặc từng tên cột không?
- **DAO/repository:** có chịu trách nhiệm tạo `PreparedStatement`, gán tham số, ánh xạ `ResultSet` và đóng tài nguyên câu lệnh không?
- **Hợp đồng:** DAO trả đối tượng/giá trị rõ nghĩa và biểu diễn lỗi dữ liệu tách biệt với “không tìm thấy” không?
- **Giao dịch:** một yêu cầu cần nguyên tử có dùng đúng **cùng `Connection` hoặc cùng transaction manager**, và chỉ một nơi sở hữu quyền `commit/rollback` không?
- **Tài nguyên:** bên mở kết nối có chịu trách nhiệm đóng/trả kết nối đúng lúc không? Bên tạo `Statement`/`ResultSet` có dọn chúng không?
- **Đồng thời:** kiểm tra quan trọng có được bảo vệ bằng SQL/constraint/isolation thích hợp không?
- **Kiểm thử:** có thể kiểm thử quy tắc service riêng, SQL DAO riêng và một ca rollback tích hợp không?

**Kết luận:** trong kiến trúc JDBC, **service trả lời “nghiệp vụ cần đạt điều gì và các bước kết hợp ra sao”**, còn **DAO/repository trả lời “đọc/ghi dữ liệu bằng JDBC thế nào”**. Ranh giới nhất quán giúp SQL, xử lý lỗi, vòng đời kết nối và giao dịch có chủ sở hữu rõ ràng, qua đó làm ứng dụng dễ thay đổi và kiểm thử hơn.
