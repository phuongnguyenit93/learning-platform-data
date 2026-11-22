# Phân biệt concurrency control và business transaction trong Java

## 1. Hai bài toán khác nhau nhưng thường xuất hiện cùng lúc

Giả sử một hệ thống chuyển 200 đơn vị tiền từ tài khoản A sang B, trong khi nhiều người dùng có thể đồng thời chuyển tiền từ cùng tài khoản.

Có **hai câu hỏi độc lập**:

1. **Concurrency control (kiểm soát truy cập đồng thời):** Khi nhiều luồng/yêu cầu chạm vào cùng trạng thái, thao tác nào được phép diễn ra trước, thao tác nào phải chờ hoặc bị từ chối? Làm sao tránh *race condition*, *lost update*, đọc trạng thái trung gian, dữ liệu không nhìn thấy giữa luồng, hoặc deadlock?
2. **Business transaction (giao dịch nghiệp vụ):** Một hành động nghiệp vụ hoàn tất khi nào và phải giữ những quy tắc nào? Chuyển tiền chỉ được xem là thành công nếu các bước bắt buộc cùng thành công; nếu thất bại, trạng thái cuối cần được phục hồi/đền bù theo cam kết của hệ thống.

**Concurrency control quản lý sự tương tác giữa các hoạt động cùng thời điểm; business transaction quản lý tính đúng đắn và vòng đời của một hoạt động nghiệp vụ.** Một ứng dụng thường cần cả hai, nhưng không thể thay thế chúng cho nhau.

Từ `transaction` đôi khi có nghĩa hẹp là **database transaction (ACID)**, đôi khi có nghĩa rộng là **business transaction** kéo dài qua nhiều thao tác hoặc nhiều dịch vụ. Cần nói rõ đang dùng nghĩa nào. Một business transaction có thể chứa một hoặc nhiều database transaction; có thể có bước gọi bên ngoài mà một DB rollback không đảo ngược được.

### So sánh theo trách nhiệm

| Góc nhìn | Concurrency control | Business transaction |
|---|---|---|
| Câu hỏi cốt lõi | Nhiều tác nhân thực hiện cùng lúc có ảnh hưởng nhau ra sao? | Một yêu cầu nghiệp vụ được coi là thành công/thất bại theo điều kiện gì? |
| Đối tượng quản lý | Vùng trạng thái dùng chung, thứ tự thực thi, quyền truy cập, tính nhìn thấy của dữ liệu | Đơn vị nghiệp vụ, bất biến (*invariant*), các bước và kết quả cam kết |
| Cơ chế Java thông dụng | `synchronized`, `ReentrantLock`, `volatile`, `AtomicInteger`, `ConcurrentHashMap`, CAS, executor | Điều phối thao tác, kiểm tra quy tắc, trạng thái yêu cầu; với DB dùng JDBC `commit`/`rollback`; qua nhiều hệ thống dùng idempotency/compensation |
| Điều bảo đảm điển hình | Loại trừ lẫn nhau, thứ tự/happens-before, cập nhật nguyên tử trên một biến, hoặc phát hiện xung đột | Thành công có ý nghĩa nghiệp vụ; nhất quán với luật kinh doanh; tùy hạ tầng, atomicity/rollback/durability hoặc bù trừ |
| Khi có lỗi | Luồng có thể chờ, retry, timeout, hoặc thất bại do tranh chấp | Có thể rollback giao dịch DB, đánh dấu thất bại, hoặc thực hiện bước bù trừ |
| Ranh giới | Luồng, đối tượng, tiến trình; với cơ sở dữ liệu còn có khóa và mức cô lập | Một yêu cầu/đơn hàng/chuyển tiền; có thể vượt qua luồng, tiến trình và dịch vụ |

> Khóa Java giúp phối hợp luồng trong **một JVM**. Nó không mặc nhiên tạo transaction bền vững, không rollback dữ liệu đã ghi, và không khóa được các JVM khác. Ngược lại, `Connection.commit()` không làm cho các biến Java bên ngoài DB trở nên thread-safe.

## 2. Nhìn thấy vấn đề bằng một lịch thực thi

Tài khoản A còn 100. Hai yêu cầu X và Y cùng muốn rút 80, đều triển khai sai bằng `read → check → write` mà không phối hợp:

| Thời điểm | Yêu cầu X | Yêu cầu Y |
|---|---|---|
| t1 | Đọc số dư A = 100 | |
| t2 | | Đọc số dư A = 100 |
| t3 | Kiểm tra 100 ≥ 80: hợp lệ | |
| t4 | | Kiểm tra 100 ≥ 80: hợp lệ |
| t5 | Ghi A = 20, trả thành công | |
| t6 | | Ghi A = 20, trả thành công |

Trạng thái cuối là 20, nhưng **hai yêu cầu cùng tuyên bố đã chi 80 từ 100**. Đây là *lost update* và đồng thời vi phạm quy tắc nghiệp vụ. Việc chia mỗi yêu cầu thành “một transaction” ở mức gọi hàm không đủ: ta cần cơ chế DB/Java phù hợp để hai lần đọc-kiểm tra-ghi không chấp nhận cùng một số dư cũ.

Ở chiều ngược lại, chỉ đặt `synchronized` quanh phép trừ số dư có thể chặn race trong một JVM, nhưng nếu một yêu cầu đã trừ A rồi gặp lỗi trước khi cộng B, Java lock **không tự động hoàn tác** phép trừ A. Thứ tự thực thi có thể đúng mà kết quả nghiệp vụ vẫn sai.

Phân biệt ba thuộc tính:

- **Mutual exclusion:** hai luồng không đồng thời chạy vùng được khóa.
- **Atomicity:** một thao tác hoặc một nhóm thao tác xuất hiện như một đơn vị không chia nhỏ theo cơ chế đang xét. `AtomicInteger.incrementAndGet()` nguyên tử trên **một biến**, không biến nhiều bước chuyển tiền thành một transaction.
- **Durability:** kết quả đã commit sống sót qua sự cố theo cam kết lưu trữ. `synchronized`, `volatile` và CAS không cung cấp durability.

Một thao tác có thể an toàn trên một biến nhưng vẫn không bảo vệ **bất biến liên quan nhiều đối tượng** (ví dụ A + B không đổi).

## 3. Concurrency control ở mức Java

Các công cụ dưới đây giải quyết những phần khác nhau của bài toán:

- `synchronized` và `ReentrantLock`: loại trừ lẫn nhau cho đoạn mã truy cập trạng thái chia sẻ. `synchronized` còn thiết lập quan hệ *happens-before* từ lần nhả monitor đến lần khóa monitor tiếp theo trên cùng monitor; `ReentrantLock` cung cấp hiệu ứng đồng bộ bộ nhớ tương đương với lock/unlock đúng cách.
- `volatile`: cung cấp tính nhìn thấy và quy tắc thứ tự đối với một trường; **không** biến `counter++` thành phép tăng nguyên tử. Dùng cho cờ trạng thái đơn giản, không dùng riêng để bảo vệ bất biến nhiều trường.
- `AtomicInteger`, `AtomicLong`, `AtomicReference`: các phép CAS/cập nhật nguyên tử trên từng biến hoặc tham chiếu; nếu cần bất biến nhiều trường, có thể dùng một trạng thái bất biến được thay thế nguyên tử hoặc dùng khóa phù hợp.
- `ConcurrentHashMap`: thread-safe cho các thao tác được API bảo đảm; chuỗi `get → if → put` không tự nguyên tử, nên dùng `compute`, `putIfAbsent`, hoặc phối hợp khác khi toàn bộ phép tính phải nhất quán.
- `ExecutorService`, `CompletableFuture`, `CountDownLatch`: tổ chức công việc và phối hợp; bản thân việc chạy/bắt đầu/chờ nhiều task **không phải transaction**. `CompletableFuture.allOf(...)` không rollback các task đã hoàn thành nếu task khác thất bại.

Chọn đúng **đơn vị khóa**: tất cả đường đọc/ghi một trạng thái cần đi theo cùng quy ước. Bảo vệ mỗi trường bằng một lock riêng chưa đủ nếu một quy tắc cần đọc đồng thời nhiều trường; khóa một object chỉ có tác dụng nếu mọi bên tham gia dùng đúng object đó. Khóa càng rộng thì càng dễ giữ bất biến nhưng có thể giảm khả năng thực thi song song.

### Ví dụ Java 17 chạy được: chuyển tiền an toàn trong bộ nhớ

Ví dụ sau chỉ mô phỏng một *đơn vị nghiệp vụ trong một JVM*. Tất cả dữ liệu tài khoản và phép đọc snapshot đi qua cùng monitor; các điều kiện thất bại dự kiến được kiểm tra **trước** khi sửa số dư. Đây chưa phải hệ thống ngân hàng thực: không có lưu trữ bền vững, nhật ký giao dịch, bảo đảm phục hồi khi tiến trình chết, hay giao tiếp liên dịch vụ.

Tạo tệp `LedgerDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class LedgerDemo {
    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        ledger.open("A", 1_000);
        ledger.open("B", 500);

        ledger.transfer("A", "B", 200);
        System.out.println(ledger.snapshot());

        try {
            ledger.transfer("A", "B", 900);
        } catch (IllegalStateException ex) {
            System.out.println("Rejected: insufficient funds");
        }
        System.out.println(ledger.snapshot());
    }

    static final class Ledger {
        private final Object mutex = new Object();
        private final Map<String, Long> balances = new HashMap<>();

        void open(String id, long cents) {
            if (cents < 0) throw new IllegalArgumentException("negative balance");
            synchronized (mutex) {
                if (balances.putIfAbsent(id, cents) != null) {
                    throw new IllegalArgumentException("duplicate account");
                }
            }
        }

        void transfer(String from, String to, long cents) {
            if (cents <= 0 || from.equals(to)) {
                throw new IllegalArgumentException("invalid transfer");
            }
            synchronized (mutex) {
                Long debit = balances.get(from);
                Long credit = balances.get(to);
                if (debit == null || credit == null) {
                    throw new IllegalArgumentException("unknown account");
                }
                if (debit < cents) {
                    throw new IllegalStateException("insufficient funds");
                }
                // Tính trước để lỗi tràn số không xảy ra sau khi trừ.
                long nextCredit = Math.addExact(credit, cents);
                balances.put(from, debit - cents);
                balances.put(to, nextCredit);
            }
        }

        String snapshot() {
            synchronized (mutex) {
                long a = balances.get("A");
                long b = balances.get("B");
                return "A=" + a + ", B=" + b + ", total=" + (a + b);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LedgerDemo.java
java LedgerDemo
```

Kết quả:

```text
A=800, B=700, total=1500
Rejected: insufficient funds
A=800, B=700, total=1500
```

Ở ví dụ này:

1. **Concurrency control:** monitor `mutex` buộc những thao tác liên quan đến map đi vào vùng được bảo vệ; luồng khác không quan sát được trạng thái trung gian qua `snapshot()`.
2. **Logic business transaction:** chỉ cho chuyển số dương, giữa hai tài khoản khác nhau, đủ số dư; tổng số dư được giữ qua ca chuyển thành công. Trường hợp thiếu tiền thất bại trước khi ghi.
3. **Giới hạn:** nếu mất điện/JVM dừng hoặc xuất hiện lỗi không thể phục hồi khi đang ghi bộ nhớ, không có rollback/durability như một DB transaction. Lock không trải sang JVM khác; tổng in ra dùng `long`, trong ứng dụng thật phải có chính sách chống tràn số và biểu diễn tiền phù hợp.

Thử đặt các lời gọi `transfer` trên nhiều luồng vẫn có chung quy tắc vì các phương thức phối hợp qua một monitor. Tuy nhiên dùng một lock cho cả ledger sẽ tạo điểm nghẽn khi số tài khoản lớn; hệ thống thực thường chuyển việc cô lập cập nhật sang DB, dùng khóa hạt mịn hoặc optimistic concurrency với phạm vi bất biến được xác định rõ.

## 4. Business transaction và database transaction

**Business transaction** là cam kết nghiệp vụ như “đặt hàng thành công khi tồn kho được giữ và đơn hàng được ghi nhận”. Một business transaction có thể thực thi bằng một **database transaction** nếu toàn bộ các thay đổi nằm trong cùng cơ sở dữ liệu, được hỗ trợ bởi cùng transaction manager.

ACID trong database transaction thường được hiểu là:

- **Atomicity:** toàn bộ các thay đổi thuộc transaction commit hoặc rollback theo cơ chế DB.
- **Consistency:** transaction chuyển từ một trạng thái thỏa các ràng buộc đã được hệ thống mô hình hóa sang trạng thái thỏa ràng buộc; DB không thể tự biết mọi quy tắc kinh doanh chưa được khai báo/lập trình.
- **Isolation:** mức độ transaction này nhìn thấy/ảnh hưởng transaction khác tùy **isolation level** và cách truy vấn/ghi; không có nghĩa mọi lịch song song đều tự động tương đương chạy tuần tự.
- **Durability:** dữ liệu đã commit tồn tại sau lỗi theo cơ chế và cấu hình bảo đảm của DB.

Giao dịch DB thường có trình tự: mở connection → tắt auto-commit → đọc/kiểm tra/cập nhật → `commit()` khi toàn bộ thành công, hoặc `rollback()` khi thất bại → đóng connection. Transaction gắn với connection/resource cụ thể; **không tự bao phủ** mọi object Java, request HTTP, message broker hay dịch vụ thanh toán.

### Trích đoạn JDBC: ranh giới commit/rollback

Đây là đoạn phương thức minh họa trong một lớp có import `javax.sql.DataSource` và `java.sql.*`; cần bảng `account(id, balance_cents)`, connection/driver và schema thực tế để chạy. Giả sử `balance_cents` là số nguyên được kiểm soát phạm vi và DB có ràng buộc số dư không âm. Không phải một chương trình độc lập.

```java
void transfer(DataSource dataSource, long fromId, long toId, long amount)
        throws SQLException {
    if (amount <= 0 || fromId == toId) {
        throw new IllegalArgumentException("invalid transfer");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE account SET balance_cents = balance_cents - ? " +
                    "WHERE id = ? AND balance_cents >= ?")) {
                debit.setLong(1, amount);
                debit.setLong(2, fromId);
                debit.setLong(3, amount);
                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException("insufficient funds");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE account SET balance_cents = balance_cents + ? " +
                    "WHERE id = ?")) {
                credit.setLong(1, amount);
                credit.setLong(2, toId);
                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException("destination missing");
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
```

Điểm cần đọc đúng:

- Hai câu `UPDATE` nằm trên **cùng một connection và cùng DB transaction**; lần ghi nợ thất bại hoặc tài khoản nhận không tồn tại sẽ kích hoạt `rollback`. Việc DB thực sự đảm bảo atomicity/durability còn phụ thuộc loại engine và cấu hình lưu trữ.
- `UPDATE ... SET balance_cents = balance_cents - ? WHERE ... balance_cents >= ?` kiểm tra điều kiện và cập nhật ở phía DB dưới cơ chế đồng thời của DB. Nó tránh mẫu dễ lỗi “SELECT số dư sang Java → tính → UPDATE giá trị mới” khi nhiều transaction đụng cùng hàng.
- Transaction **vẫn cần** isolation và concurrency control thích hợp (khóa hàng, kiểm tra version, constraint, hoặc mức cô lập mạnh hơn). Nhiều RDBMS có thể báo deadlock/serialization failure khi tranh chấp; phải xử lý lỗi và chỉ retry **toàn bộ** transaction khi an toàn.
- Mẫu minh họa không giải quyết hết yêu cầu sản phẩm: kiểm tra overflow, giới hạn và đơn vị tiền, bản ghi ledger/audit, idempotency key, ủy quyền, độ bền và chính sách retry phải được thiết kế thêm. Trên DB hoặc driver cụ thể, cần kiểm tra loại dữ liệu, hành vi lock, timeout và câu SQL hỗ trợ.
- `rollback()` có thể thất bại vì mất kết nối; ứng dụng cần xử lý trường hợp **chưa biết chắc outcome** sau lỗi mạng lúc commit, không tự suy rằng “ném exception = chưa commit”.

**Điều quan trọng:** DB transaction và Java monitor là hai phạm vi độc lập. Giữ Java lock quanh JDBC không khiến các instance dịch vụ khác chờ theo lock đó. Dùng JDBC transaction quanh `HashMap` không rollback các thay đổi trên map.

## 5. Ba chiến lược xử lý tranh chấp thường gặp

### 5.1. Pessimistic locking

Đặt lock trước khi làm việc với tài nguyên; trong Java dùng `synchronized` hoặc `ReentrantLock`; trong DB có cơ chế lock được duy trì trong transaction (ví dụ `SELECT ... FOR UPDATE` ở DB hỗ trợ). Phù hợp khi xung đột thường xuyên hoặc tính toán phải giữ bất biến trước khi ghi.

Đánh đổi: thao tác có thể chờ lâu, deadlock, giảm throughput. Cần chọn phạm vi khóa nhỏ nhưng đủ bao trùm bất biến, thứ tự lấy khóa nhất quán, tránh gọi API chậm trong lúc giữ lock và có chính sách timeout/failure.

### 5.2. Optimistic concurrency control

Không giữ lock ứng dụng suốt lúc tính; khi ghi xác nhận dữ liệu vẫn đúng phiên bản đã đọc. Ví dụ hàng có cột `version`:

```sql
UPDATE account
SET balance_cents = :new_balance, version = version + 1
WHERE id = :id AND version = :version_read;
```

Nếu số hàng được cập nhật bằng **0**, phiên bản đã thay đổi hoặc bản ghi không còn tồn tại: coi là xung đột/không tìm thấy, **không** báo thành công. Phải tải lại, kiểm tra lại bất biến và quyết định retry, trả lỗi cho người dùng hoặc hòa giải. Dùng `AtomicReference.compareAndSet(expected, updated)` cũng là ý tưởng xác nhận giá trị cũ nhưng chỉ trong bộ nhớ của JVM đó.

Lưu ý: thay lại `new_balance` đã tính từ dữ liệu cũ sau khi gặp conflict là sai. Nếu nghiệp vụ liên quan nhiều hàng hoặc predicate xuyên nhiều bản ghi, version của một hàng không đủ bảo vệ toàn bộ bất biến.

### 5.3. Lệnh cập nhật có điều kiện và ràng buộc ở DB

Ví dụ: `UPDATE stock SET quantity = quantity - 1 WHERE sku = ? AND quantity > 0` rồi kiểm tra số hàng ảnh hưởng; cùng với `CHECK`, `UNIQUE`, foreign key và ranh giới transaction phù hợp. Cách này chuyển điều kiện quan trọng sát nơi có thể tranh chấp; một unique constraint trên `idempotency_key` có thể chặn hai request trùng cùng tạo hiệu ứng.

Lựa chọn chiến lược dựa trên **điểm tranh chấp thực tế và bất biến nghiệp vụ**, không dựa vào việc trong code có bao nhiêu luồng.

## 6. Khi nghiệp vụ kéo dài qua nhiều tài nguyên

Ví dụ đặt hàng gồm: giữ hàng trong DB, gọi dịch vụ thanh toán, phát sự kiện xác nhận, gửi email. Một local DB transaction **không tự rollback** khoản thanh toán đã được hệ thống khác chấp nhận hoặc email đã gửi.

Cách tư duy an toàn:

1. Xác định trạng thái nghiệp vụ rõ ràng: `PENDING`, `CONFIRMED`, `CANCELLED` (hoặc các trạng thái đúng với domain).
2. Dùng transaction cục bộ để commit những thay đổi cùng DB; dùng **transactional outbox** khi cần ghi trạng thái và sự kiện sẽ phát như một quyết định bền vững. Publisher xử lý outbox sau, chấp nhận khả năng phát lại và để consumer idempotent.
3. Qua nhiều dịch vụ, dùng saga/workflow có bước **compensation** rõ ràng (ví dụ hoàn tiền hoặc giải phóng hàng). Compensation là hành động nghiệp vụ mới, **không** tương đương rollback ACID tức thì; có thể thất bại, cần retry và theo dõi.
4. Gắn **idempotency key** cho yêu cầu có thể retry; lưu kết quả/hiệu ứng một cách nguyên tử với ràng buộc duy nhất phù hợp. Idempotency không thay thế khóa hoặc isolation cho hai yêu cầu khác nhau cùng tranh chấp tài nguyên.
5. Phân biệt timeout với thất bại đã xác nhận. Một request HTTP timeout có thể đã tạo giao dịch ở phía nhận; trước khi retry phải tra cứu/có khóa chống lặp phù hợp.

Có thể dùng mô hình transaction phân tán như two-phase commit khi hệ thống và resource hỗ trợ, nhưng có đánh đổi lớn về coupling, tính sẵn sàng và vận hành. Không suy rằng cứ có nhiều service thì một lời gọi Java duy nhất có thể commit/rollback đồng bộ trên tất cả.

## 7. Kết hợp hai lớp bảo đảm đúng cách

Xét chức năng đặt một ghế còn trống. *Business invariant*: mỗi ghế chỉ có tối đa một booking thành công, và một yêu cầu không được tạo hai lần do retry.

- **Concurrency control:** nhiều người cùng bấm đặt ghế; dùng khóa/điều kiện cập nhật/unique constraint tại nguồn dữ liệu chung để chọn đúng một người thắng. Một `synchronized` ở lớp Java của một instance không ngăn instance khác đặt cùng ghế.
- **Business transaction:** chỉ đánh dấu booking là thành công khi trạng thái ghế và bản ghi booking được commit nhất quán; lỗi trước commit cần rollback. Nếu đã thanh toán ở dịch vụ riêng rồi booking thất bại, cần luồng hoàn tiền/đền bù.
- **Idempotency:** chính một người gửi lại cùng yêu cầu do retry không tạo thêm booking hoặc thu tiền hai lần; dùng khóa nghiệp vụ/idempotency key bền vững.
- **Quan sát kết quả:** chỉ trả “đặt thành công” sau khi đạt điểm commit/nghiệp vụ xác nhận tương ứng; nếu outcome chưa biết, không được khẳng định thành công hoặc thất bại mà không đối soát.

### Bảng chọn cơ chế theo vấn đề

| Triệu chứng | Cần kiểm tra trước | Cơ chế điển hình |
|---|---|---|
| `counter++` bị mất lần tăng khi nhiều thread | Có dùng chung một biến trong một JVM? | `AtomicInteger.incrementAndGet()` hoặc lock |
| Hai request cùng trừ tồn kho tạo số âm | Kiểm tra và ghi có nguyên tử tại nơi lưu chung không? | Conditional UPDATE, DB constraint, lock hoặc version |
| Trừ A thành công nhưng cộng B thất bại | Có ranh giới commit/rollback bao cả hai thay đổi không? | Một DB transaction với xử lý lỗi đầy đủ |
| Hai hàng riêng lẻ hợp lệ nhưng tổng/quan hệ sai | Invariant nằm trên mấy hàng? Isolation có chống *write skew* không? | Serializable transaction, khóa phù hợp, thiết kế invariant/constraint |
| API thanh toán được gọi hai lần vì retry | Có nhận diện cùng một yêu cầu không? | Idempotency key được lưu bền vững, unique constraint |
| DB rollback nhưng email vẫn gửi | Side effect ngoài DB được phối hợp thế nào? | Outbox, trạng thái và compensation |
| Mở thêm nhiều JVM thì lỗi xuất hiện lại | Lock/counter có chia sẻ qua instance không? | Cơ chế tại DB/nguồn dữ liệu chung, distributed coordination khi thực sự cần |

## 8. Isolation, Java Memory Model và phạm vi bảo đảm

Đừng đánh đồng hai loại “nhìn thấy”:

- **Java Memory Model (JMM):** mô tả quan hệ giữa các thao tác luồng Java trong cùng JVM. `volatile`, monitor, lock, atomic API và các phép phối hợp tạo *happens-before* theo hợp đồng API. Ví dụ: ghi dữ liệu rồi unlock một monitor, luồng khác lock cùng monitor có thể nhìn thấy dữ liệu đã được công bố hợp lệ.
- **Database isolation:** mô tả tương tác giữa các transaction DB. Tùy DB/isolation level, có thể gặp non-repeatable read, phantom, lost update hoặc *write skew* nếu thuật toán không bảo vệ đúng bất biến. `READ COMMITTED` không mặc nhiên đồng nghĩa serializable; độ bảo vệ cụ thể phải kiểm tra theo DB đang dùng.

Một `Connection` cũng không nên được mặc nhiên chia sẻ giữa các thread để “cùng tham gia transaction”; việc sử dụng đồng thời và thread safety phụ thuộc driver/API, và ranh giới transaction thường gắn với connection. Khi công việc được chuyển qua `CompletableFuture` hoặc executor, các luồng không tự kế thừa trạng thái transaction/lock từ luồng gọi.

**Quy tắc thực hành:** kiểm tra bảo đảm tại lớp mà dữ liệu thực sự được chia sẻ: trường Java trong cùng JVM → Java concurrency primitives; dữ liệu nhiều instance trong DB → transaction, isolation, locking/constraints; hiệu ứng nhiều hệ thống → workflow, idempotency và compensation.

## 9. Cách thiết kế và kiểm thử

Một quy trình ngắn, có thể dùng khi review code:

1. **Viết bất biến trước:** ví dụ `balance >= 0`, `tổng A+B không đổi`, `ghế chỉ có một booking`, `mỗi request-id chỉ có một kết quả thành công`.
2. **Xác định nơi lưu trạng thái có thẩm quyền:** heap của một JVM, DB quan hệ, cache phân tán, message broker hay dịch vụ khác. Đếm tất cả writer, kể cả job nền và các instance.
3. **Xác định điểm tuyến tính/commit:** bước nào quyết định một thao tác thành công? Các bước trước/sau có cần rollback hoặc compensation không?
4. **Vẽ interleaving xấu:** hai request cùng đọc, cùng kiểm tra, một thất bại giữa hai lần ghi, crash ngay sau commit, response bị mất và client retry.
5. **Chọn bảo vệ ít nhất nhưng đủ:** lock/CAS trong Java; điều kiện cập nhật, version, constraint, isolation ở DB; idempotency/outbox/workflow qua nhiều hệ thống.
6. **Đặt chính sách lỗi:** lock timeout, DB deadlock, optimistic conflict, rollback failure, outcome không chắc chắn, retry với backoff và giới hạn; mọi retry phải giữ ý nghĩa nghiệp vụ.
7. **Kiểm thử tại đúng ranh giới:** thử nhiều thread với `ExecutorService` + `CountDownLatch` để tạo tranh chấp và chờ `Future.get()`; kiểm tra bất biến sau khi hoàn tất. Với nhiều JVM, kiểm thử qua DB chung; thêm fault injection giữa các bước, crash/restart, và retry trùng idempotency key.

Trong kiểm thử cạnh tranh, không dựa vào `Thread.sleep(...)` để chứng minh có hay không có race: thời gian scheduler không xác định. Dùng latch/barrier để tăng khả năng tái hiện, nhiều lần chạy và đặc biệt **assert bất biến**; một test chạy qua không phải chứng minh thuật toán đúng dưới mọi interleaving.

## 10. Những nhầm lẫn cần tránh

- **“Đã dùng `synchronized` thì chuyển tiền là transaction.”** Sai: khóa chỉ phối hợp truy cập trong phạm vi monitor/JVM; không cung cấp rollback/durability.
- **“Có DB transaction thì không thể race.”** Sai: kết quả còn phụ thuộc isolation, kiểu truy vấn, constraint và thuật toán cập nhật. Hai transaction có thể cùng đọc điều kiện cũ nếu chưa bảo vệ.
- **“`volatile` đủ cho mọi cập nhật chia sẻ.”** Sai: tính nhìn thấy khác với phép read-modify-write nguyên tử.
- **“`AtomicInteger` làm cả nghiệp vụ nguyên tử.”** Sai: một atomic variable không bảo vệ chuỗi thay đổi nhiều nguồn lực.
- **“Retry lỗi nào cũng an toàn.”** Sai: retry có thể nhân đôi thanh toán/đơn hàng khi lần đầu đã commit nhưng phản hồi thất lạc.
- **“Rollback DB hoàn tác HTTP/email.”** Sai: các side effect này cần cơ chế bù trừ hoặc điều phối riêng.
- **“Lock ở ứng dụng đủ cho cluster.”** Sai: nhiều JVM có monitor/heap tách biệt. Đặt tính nhất quán tại nguồn dùng chung hoặc sử dụng coordination phù hợp.
- **“Transaction thành công nghĩa là quy tắc nghiệp vụ đã đúng.”** Sai: ACID không tự mã hóa domain rule; thiếu invariant, constraint hoặc kiểm tra đúng thời điểm vẫn dẫn tới kết quả sai.
- **“Càng khóa rộng càng an toàn.”** Không hoàn toàn: giữ lock quanh I/O và công việc dài làm tăng latency, dễ deadlock, giảm khả năng mở rộng; vẫn có thể khóa sai đối tượng hoặc bỏ sót một writer.

## Kết luận

**Concurrency control** bảo đảm các tác nhân đồng thời phối hợp đúng trên trạng thái chia sẻ; **business transaction** định nghĩa sự thành công, thất bại và bất biến của một hành động nghiệp vụ. Database transaction là một công cụ triển khai phần cam kết đó cho dữ liệu DB, với isolation/locking cần chọn đúng. Hãy bắt đầu từ bất biến, nhận diện mọi writer và biên giới hệ thống, rồi chọn lock/CAS/constraint/transaction/idempotency/compensation tương ứng.