# Khôi phục trạng thái và giới hạn của rollback khi xử lý exception trong Java

## 1. Vì sao khôi phục trạng thái quan trọng?

Một phương thức có thể gồm nhiều bước: kiểm tra đầu vào, sửa đối tượng, ghi database, gọi dịch vụ khác và trả kết quả. Nếu exception xuất hiện sau khi một vài bước đã hoàn thành thì chương trình có thể để lại dữ liệu mới **dù lời gọi báo thất bại**. Bởi vậy, xử lý exception đúng không dừng ở `try/catch`; còn phải quyết định trạng thái nào còn lại và ai chịu trách nhiệm phục hồi.

**Rollback** là hoàn tác các thay đổi trong một **phạm vi có thể kiểm soát** về trạng thái nhất quán được hợp đồng cam kết. Cần phân biệt:

- **Rollback bộ nhớ:** trả giá trị trường hoặc collection về trước thao tác; hoặc tốt hơn, chuẩn bị một trạng thái độc lập rồi chỉ công bố khi toàn bộ phần việc an toàn đã xong.
- **Rollback transaction:** hủy các thay đổi chưa commit trong transaction của một hệ thống hỗ trợ giao dịch, chẳng hạn database thông qua JDBC.
- **Compensation (bù trừ):** tạo thao tác nghiệp vụ mới để bù hiệu ứng của một thao tác đã thực hiện, ví dụ hoàn tiền sau khi khoản thu đã được ghi nhận. Nó không xóa được toàn bộ lịch sử hay bảo đảm người khác chưa thấy hiệu ứng ban đầu.
- **Recovery (phục hồi):** quá trình đưa hệ thống trở lại hoạt động đúng sau lỗi, có thể gồm rollback, replay log, đối soát, retry an toàn hoặc bù trừ.

Exception **không tự động rollback** dữ liệu Java, file, database hay dịch vụ mạng. `throw` chỉ chuyển luồng điều khiển; mọi thay đổi đã thực hiện vẫn có thể tồn tại.

## 2. Các mức bảo đảm an toàn exception

Khi thiết kế hoặc review API, nên hỏi “sau khi phương thức thất bại, caller quan sát thấy điều gì?” thay vì chỉ hỏi “lỗi được catch ở đâu?”.

| Mức bảo đảm | Trạng thái sau khi thất bại | Ví dụ |
| --- | --- | --- |
| **Strong exception guarantee** | Trong phạm vi đã công bố, thao tác hoặc thành công toàn bộ, hoặc trạng thái quan sát được không đổi | Tính toàn bộ dữ liệu trên bản sao, xác thực rồi thay một tham chiếu |
| **Basic exception guarantee** | Đối tượng vẫn giữ bất biến, không rò rỉ tài nguyên nhưng một phần giá trị có thể đã đổi | Một bộ xử lý lưu tiến độ từng bước và duy trì trạng thái hợp lệ khi lỗi |
| **Không có bảo đảm** | Trạng thái có thể nửa chừng, không nhất quán hoặc không rõ kết quả | Sửa nhiều trường rồi ném lỗi giữa chừng mà không có xử lý phục hồi |
| **No-throw guarantee** | Một thao tác được thiết kế không ném exception trong các điều kiện và phạm vi hợp đồng xác định | Thay tham chiếu đã chuẩn bị sẵn trong vùng đồng bộ thích hợp, không gọi I/O |

Các mức này là **bảo đảm về trạng thái**, không phải loại exception Java. Một ngoại lệ checked như `IOException` không tự có “rollback tốt hơn” `RuntimeException`. Mức *no-throw* cũng không có nghĩa mọi JVM `Error` hay lỗi hạ tầng đều không thể xảy ra; nó đòi hỏi tiền đề và phạm vi cụ thể.

Từ “trạng thái không đổi” phải có **ranh giới**: một object, một aggregate, một transaction DB, hay cả quy trình đa dịch vụ? API có thể bảo đảm mạnh đối với bộ nhớ cục bộ trong khi việc gửi message bên ngoài đã hoàn thành. Không nên ghi “atomic” hoặc “rollback hoàn toàn” nếu chưa xác định phạm vi.

## 3. Điều `try/catch/finally` thực sự làm

Ví dụ dưới đây là mảnh mã bên trong một phương thức đã có biến `balance` và hàm `notifyRemote()`:

```java
balance -= 20;       // Nếu trước đó là 100, bây giờ là 80
notifyRemote();      // Có thể ném IOException
```

Nếu `notifyRemote()` ném lỗi, `balance` **vẫn là 80** trừ khi có logic riêng để phục hồi. Java không tạo snapshot tự động cho trường đối tượng.

Những cơ chế thường bị nhầm với rollback:

- `catch` quyết định cách xử lý hoặc chuyển tiếp exception; không undo bất kỳ phép gán nào.
- `finally` chạy khi rời khối để dọn tài nguyên và trạng thái phụ trợ; tự nó không có semantics giao dịch.
- `try-with-resources` gọi `close()` theo hợp đồng của tài nguyên. Đóng file không xóa byte đã ghi, đóng connection không thay thế việc thiết kế `commit()/rollback()`.
- `synchronized` tự nhả monitor khi khối/method kết thúc vì exception, nhưng các cập nhật đã thực hiện không bị hoàn tác.
- `Thread.currentThread().interrupt()` liên quan truyền tín hiệu hủy/chờ, không phải khôi phục dữ liệu.

Muốn thiết kế phục hồi đúng, trước hết liệt kê mọi **tác dụng phụ** và xác định thời điểm chúng có thể xảy ra.

## 4. Khi nào chuẩn bị độc lập thay được rollback thủ công?

Nếu toàn bộ thay đổi nằm trong **một snapshot bộ nhớ do phương thức sở hữu**, tốt nhất là ngăn trạng thái dở dang xuất hiện ngay từ đầu: chuẩn bị giá trị ứng viên rồi thay bản đã công bố chỉ sau khi mọi kiểm tra thành công.

~~~java
// Minh họa trong lớp có current: Map<String, Integer>.
Map<String, Integer> candidate = new HashMap<>(current);
candidate.put("items",
        Math.addExact(candidate.get("items"), increment));
Map<String, Integer> ready = Map.copyOf(candidate);
current = ready; // Điểm công bố trong phạm vi một writer.
~~~

Nếu `Math.addExact` hoặc tạo `ready` thất bại **trước phép gán cuối**, `current` vẫn tham chiếu bản cũ. Nhưng `HashMap` chỉ sao chép nông: không được mutate các value object dùng chung trong lúc chuẩn bị. Với nhiều writer, cần khóa/CAS phù hợp để tránh mất cập nhật; `volatile` một mình không làm thao tác đọc–tính–ghi thành nguyên tử.

**Ranh giới quan trọng với rollback:** cách này **tránh phải undo** các phép gán nội bộ trước commit; nó không khôi phục DB, file, network request hoặc callback đã gây side effect. Khi đã có thay đổi ngoài snapshot, cần transaction/undo/compensation có hợp đồng riêng và phải tính cả khả năng **thao tác hoàn tác thất bại**. Vì vậy hãy thử prepare–publish trước, chỉ chọn rollback khi phạm vi dữ liệu và cơ chế phục hồi thực sự cho phép.

## 5. Ví dụ Java 17+ chạy được: trước commit và sau commit

Chương trình tạo sổ số dư trong JVM. Thao tác `transfer` tính trên bản sao và chỉ công bố bản mới ở cuối. Thao tác `transferThenNotify` chứng minh **lỗi sau commit** không tự trả số dư về trạng thái cũ.

Lưu file tên **`StateRollbackDemo.java`**:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class StateRollbackDemo {
    @FunctionalInterface
    interface Notifier {
        void send() throws IOException;
    }

    static final class Ledger {
        private volatile Map<String, Long> balances =
                Map.of("A", 100L, "B", 50L);

        synchronized void transfer(
                String from, String to, long amount, boolean failBeforeCommit)
                throws IOException {
            Objects.requireNonNull(from, "from");
            Objects.requireNonNull(to, "to");
            if (from.equals(to) || amount <= 0) {
                throw new IllegalArgumentException("invalid transfer");
            }

            Map<String, Long> next = new HashMap<>(balances);
            Long source = next.get(from);
            Long target = next.get(to);
            if (source == null || target == null) {
                throw new IllegalArgumentException("unknown account");
            }
            if (source < amount) {
                throw new IllegalArgumentException("insufficient funds");
            }

            next.put(from, source - amount);
            next.put(to, Math.addExact(target, amount));
            if (failBeforeCommit) {
                throw new IOException("simulated failure");
            }

            balances = Map.copyOf(next);
        }

        void transferThenNotify(String from, String to, long amount,
                                Notifier notifier) throws IOException {
            Objects.requireNonNull(notifier, "notifier");
            transfer(from, to, amount, false);
            notifier.send();
        }

        @Override
        public String toString() {
            Map<String, Long> snapshot = balances;
            return "A=" + snapshot.get("A") + ", B=" + snapshot.get("B");
        }
    }

    public static void main(String[] args) throws IOException {
        Ledger ledger = new Ledger();
        System.out.println("Initial: " + ledger);

        try {
            ledger.transfer("A", "B", 20, true);
        } catch (IOException ex) {
            System.out.println("Before commit: " + ex.getMessage());
        }
        System.out.println("After failure: " + ledger);

        ledger.transfer("A", "B", 20, false);
        System.out.println("After success: " + ledger);

        try {
            ledger.transferThenNotify("A", "B", 5, () -> {
                throw new IOException("delivery timeout");
            });
        } catch (IOException ex) {
            System.out.println("Notify failure: " + ex.getMessage());
        }
        System.out.println("After notify failure: " + ledger);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 StateRollbackDemo.java
java StateRollbackDemo
```

Standard output:

```text
Initial: A=100, B=50
Before commit: simulated failure
After failure: A=100, B=50
After success: A=80, B=70
Notify failure: delivery timeout
After notify failure: A=75, B=75
```

**Phân tích:**

- Sau khi xây trạng thái dự kiến `A=80, B=70`, nhánh tiêm lỗi ném `IOException` trước phép gán `balances`. Vì vậy người đọc vẫn thấy `100, 50`.
- Lượt không lỗi hoàn tất phép gán map mới; trạng thái đã công bố là `80, 70`.
- Lượt thứ ba chuyển thêm `5` và **commit nội bộ thành công**; rồi notifier ném `IOException`. Dữ liệu sổ vẫn là `75, 75`. Việc caller nhận exception không cho phép suy luận “chuyển tiền chưa diễn ra”; gọi lại toàn bộ phương thức có thể trừ thêm tiền.

Map được công bố bất biến và chứa `Long` bất biến. `synchronized` tuần tự hóa writer `transfer`; `volatile` công bố tham chiếu an toàn cho reader `toString()` đọc cùng một snapshot. Tuy nhiên ví dụ chỉ gồm hai tài khoản trong bộ nhớ, không dùng DB hay mạng thật, không thay thế thiết kế cho tiền thật. Cờ `failBeforeCommit` chỉ là công cụ tiêm lỗi. `Math.addExact` có thể ném lỗi tràn số trước commit nên không làm thay đổi bản công bố.

## 6. Rollback thủ công bằng snapshot: dùng được nhưng dễ thiếu

Với thay đổi nhỏ, có thể ghi nhớ giá trị cũ:

```java
int oldBalance = balance;
try {
    balance -= amount;
    performNextStep();
} catch (Exception original) {
    balance = oldBalance;
    throw original;
}
```

Đây là **đoạn minh họa trong một phương thức** đã có `balance`, `amount`, `performNextStep()`; không biên dịch độc lập. Nó chỉ an toàn khi gán lại `oldBalance` thật sự phục hồi **mọi trạng thái quan sát được** theo hợp đồng. Một số vấn đề thường gặp:

- Cùng thao tác đã sửa nhiều trường, object con, file hoặc gọi dịch vụ ngoài; chỉ gán lại `balance` không đủ.
- Snapshot nông có thể chứa các tham chiếu tới object mutable đã bị sửa.
- Một luồng khác có thể vừa cập nhật hợp lệ; rollback bằng giá trị cũ sẽ **ghi đè cập nhật của luồng đó**.
- Phép hoàn tác cũng có thể thất bại, nhất là khi cần gọi hệ thống phụ thuộc đang gặp sự cố.
- Nếu một bước đã gửi email/thanh toán, nó không có “phép gán đảo” trong JVM.
- `catch (Exception)` không bao gồm `Error`. Không nên mở rộng tùy tiện thành `catch (Throwable)` chỉ để tuyên bố hỗ trợ rollback cho mọi sự cố.

Khi nhiều bước có hàm undo riêng, thường cần hoàn tác **theo thứ tự ngược**: `A → B → C`, rồi `undo(C) → undo(B) → undo(A)`. Nhưng thứ tự ngược **chỉ là điều kiện tổ chức**, chưa bảo đảm undo sẽ thành công hoặc không tạo thêm tác dụng phụ. Một số hành động, ví dụ gửi thông báo, không có thao tác đảo đúng nghĩa.

Nếu có thể, giữ trạng thái cũ cho đến điểm commit và tránh cần rollback thủ công. Nếu bắt buộc dùng undo log, phải ghi chính xác những bước đã hoàn thành, idempotency của thao tác undo và trạng thái nào được ghi bền vững để phục hồi sau crash.

## 7. Transaction JDBC: rollback chỉ trong phạm vi transaction

Khi nhiều lệnh SQL phải cùng thành công hoặc cùng thất bại, dùng **một connection và một transaction**, thay vì dựa vào exception Java. Với JDBC, quy trình cơ bản là tắt auto-commit, chạy tất cả lệnh, `commit()` khi thành công; nếu có `SQLException` trước commit thì thử `rollback()`.

Ví dụ dưới đây là **một phương thức minh họa JDBC**, cần `DataSource` đã cấu hình, driver, bảng `accounts(id, balance)` và DB hỗ trợ transaction. Nó **không phải chương trình độc lập**. Giả định mỗi `id` là khóa duy nhất, số dư dùng kiểu dữ liệu phù hợp, và mỗi cập nhật thành công ảnh hưởng đúng một hàng.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void moveMoney(DataSource dataSource,
                             long fromId, long toId, long amount)
        throws SQLException {
    if (amount <= 0 || fromId == toId) {
        throw new IllegalArgumentException("invalid transfer");
    }

    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);
        try {
            try (PreparedStatement debit = conn.prepareStatement(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE id = ? AND balance >= ?")) {
                debit.setLong(1, amount);
                debit.setLong(2, fromId);
                debit.setLong(3, amount);
                if (debit.executeUpdate() != 1) {
                    throw new SQLException("source missing or insufficient funds");
                }
            }

            try (PreparedStatement credit = conn.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                credit.setLong(1, amount);
                credit.setLong(2, toId);
                if (credit.executeUpdate() != 1) {
                    throw new SQLException("destination missing");
                }
            }

            conn.commit();
        } catch (SQLException original) {
            try {
                conn.rollback();
            } catch (SQLException rollbackFailure) {
                original.addSuppressed(rollbackFailure);
            }
            throw original;
        }
    }
}
```

Nếu cập nhật đích gặp lỗi **trước `commit()`** và DB cho phép rollback thành công, cập nhật trừ ở nguồn cùng transaction cũng bị hủy. Điều kiện `balance >= ?` đặt trực tiếp trong lệnh `UPDATE` giúp tránh lỗi đọc số dư ở Java rồi bị thay đổi bởi transaction cạnh tranh trước khi ghi. Tuy nhiên hệ thống thật còn cần thiết kế isolation, locking, deadlock retry, constraints, overflow, độ chính xác số tiền và connection pool.

**Các giới hạn quan trọng:**

1. `rollback()` tác động đến **transaction của connection đó**. Nó không xóa email đã gửi, giao dịch đã ghi ở DB khác, file đã ghi hay HTTP request đã được xử lý.
2. Một số DB, storage engine hoặc câu lệnh DDL có semantics commit riêng; kiểm tra tài liệu DB cụ thể.
3. Nếu rollback ném exception, hệ thống chưa thể tuyên bố đã phục hồi thành công. `original.addSuppressed(rollbackFailure)` lưu thông tin lỗi thứ hai.
4. Nếu `commit()` ném exception do mất kết nối, kết quả **có thể không xác định từ phía ứng dụng**: DB có thể đã commit rồi nhưng phản hồi bị mất. Thử rollback sau đó không chứng minh transaction chưa commit.
5. `try-with-resources` đóng `Connection` và `PreparedStatement`; nó không thay thế việc thiết kế ranh giới transaction và rollback rõ ràng.

Trong Java SE/JDBC, ném exception từ mã gọi **không mặc nhiên gọi rollback cho mọi connection**. Framework transaction có thể cung cấp tự động rollback theo luật riêng, nhưng vẫn phải biết phương thức nào mở transaction, lúc nào commit, exception có bị nuốt hay không, và tài nguyên nào thật sự tham gia.

## 8. Rollback một file: đóng stream không xóa dữ liệu đã ghi

Đang ghi giữa file mà phát sinh lỗi có thể để lại nội dung dở dang; `try-with-resources` chỉ quản lý việc đóng handle. Khi thay **toàn bộ nội dung của một file**, phương pháp thường dùng là:

1. Tạo file tạm ở cùng filesystem/thư mục với file đích.
2. Viết và đóng file tạm; chỉ tiếp tục khi đã có nội dung mới đầy đủ.
3. Thay thế file đích bằng thao tác move/rename nguyên tử nếu filesystem hỗ trợ.
4. Nếu phát sinh exception trước thay thế, xóa file tạm, giữ file đích cũ.

Ví dụ mảnh mã trong phương thức đã có biến `Path target`, `String newContent`, khai báo `throws IOException` và import `java.nio.file.Files`, `Path`, `StandardCopyOption`, `java.nio.charset.StandardCharsets`:

```java
Path absolute = target.toAbsolutePath();
Path directory = absolute.getParent();
Path temporary = Files.createTempFile(directory, ".staging-", ".tmp");
try {
    Files.writeString(temporary, newContent, StandardCharsets.UTF_8);
    Files.move(temporary, absolute,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

Đây là **mảnh minh họa**, không phải chương trình độc lập. `ATOMIC_MOVE` có thể không được filesystem hỗ trợ và có thể ném `AtomicMoveNotSupportedException`; hành vi thay file đã tồn tại khi move nguyên tử còn phụ thuộc implementation. *Atomic visibility* cũng **khác durability sau mất điện**; hệ thống yêu cầu durability cao phải cân nhắc flush/sync file và directory theo nền tảng. Dọn file tạm trong `finally` cũng có thể thất bại. Không âm thầm fallback sang copy không nguyên tử nếu hợp đồng đòi bảo đảm mạnh.

Ngay cả khi thay file thành công nguyên tử, nó vẫn **không cùng transaction** với một DB hoặc HTTP service mà phương thức có thể đã gọi.

## 9. Vì sao rollback không bao quát hệ thống phân tán?

Mỗi hệ thống có một trạng thái và ranh giới commit riêng. Nếu A đã commit rồi B lỗi, rollback B không thể tự đảo kết quả A. Những sự kiện đã được bên ngoài quan sát cũng không thể “chưa từng xảy ra”.

| Thao tác ngoài JVM | Điều rollback cục bộ không giải quyết | Cơ chế cân nhắc |
| --- | --- | --- |
| Gửi email/SMS/push | Người nhận có thể đã thấy thông báo | Outbox, trạng thái gửi, đính chính khi cần |
| Gọi API thanh toán | Bên nhận có thể đã xử lý nhưng ACK bị mất | Idempotency key, tra cứu trạng thái, bù trừ nghiệp vụ |
| DB A commit rồi DB B lỗi | Hai DB không tự dùng chung transaction | Distributed transaction khi được hỗ trợ, hoặc Saga/outbox |
| Ghi file rồi rollback DB | File ngoài phạm vi transaction DB | Kế hoạch commit, khôi phục và reconciliation |
| Gửi message rồi lỗi | Consumer có thể đã nhận/xử lý | Bảo đảm gửi, deduplication, idempotent consumer |

**Timeout không đồng nghĩa thất bại.** Client có thể đã gửi lệnh; server commit; đường truyền đứt trước phản hồi. Nếu client gửi lại **lệnh mới** vì nghĩ chưa thực hiện, có thể tạo tác dụng phụ hai lần. Với nghiệp vụ quan trọng, cần trạng thái “**chưa rõ kết quả**”, mã request/transaction ổn định và cách tra cứu trạng thái.

### Saga và compensation

Saga chia luồng nhiều hệ thống thành các giao dịch cục bộ và hành động bù trừ tương ứng. Ví dụ đặt chỗ: **giữ chỗ → thu tiền → xác nhận**. Nếu thu tiền không thành công, có thể giải phóng chỗ; nếu đã thu tiền nhưng bước xác nhận lỗi, có thể cần hoàn tiền. Mỗi hành động bù trừ cũng có thể thất bại, nên cần quy tắc retry có giới hạn, ghi tiến độ bền vững, idempotency, giám sát và đối soát. Saga thường dẫn đến *eventual consistency*, **không tự tạo ACID toàn hệ thống**.

Hoàn tiền **không xóa lịch sử thu tiền**; nó là giao dịch mới, có thể phát sinh phí và sự kiện khác. Không nên gọi compensation là “rollback nguyên tử” nếu các bên ngoài vẫn thấy trạng thái trung gian.

### Transactional outbox

Nếu nghiệp vụ cần vừa cập nhật DB vừa phát sự kiện, một cách là ghi **dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction DB**. Sau commit, một tiến trình đọc outbox và gửi message. Cách này giúp tránh trường hợp DB commit nhưng chương trình chết trước khi ghi ý định gửi; tuy nhiên consumer vẫn có thể nhận cùng message nhiều lần nếu phía gửi mất ACK. Vì vậy cần consumer idempotent và xử lý trùng. Outbox là cơ chế phối hợp có phạm vi cụ thể, **không phải exactly-once end-to-end mặc định**.

## 10. Khi rollback cũng ném lỗi: giữ nguyên nhân gốc

Một lỗi thường gặp là đang xử lý `IOException` thì tác vụ undo cũng ném `IOException` và làm mất lỗi ban đầu. Có thể giữ thông tin bằng `addSuppressed`:

```java
try {
    performOperation();
} catch (IOException original) {
    try {
        undoOperation();
    } catch (IOException undoFailure) {
        original.addSuppressed(undoFailure);
    }
    throw original;
}
```

Đây là **đoạn trong phương thức khai báo `throws IOException`** với hai hàm `performOperation()` và `undoOperation()` đã được định nghĩa. `addSuppressed` chỉ giữ thông tin điều tra, không tự phục hồi dữ liệu. Nếu rollback không thành công, trạng thái phải được ghi nhận **chưa xác minh hoặc cần xử lý tiếp** theo hợp đồng; không được âm thầm báo “đã khôi phục”.

`try-with-resources` cũng có thể gắn exception khi `close()` thất bại vào lỗi chính thông qua cơ chế `getSuppressed()`. Điều này giúp chẩn đoán, nhưng đóng tài nguyên không đồng nghĩa thao tác nghiệp vụ đã được hoàn tác.

Nếu cần thao tác với `InterruptedException`, giữ hoặc khôi phục trạng thái interrupt đúng hợp đồng; đừng gom mọi exception và error thành một “rollback failed” chung làm mất nguyên nhân quan trọng.

## 11. Retry sau lỗi: phân biệt trước commit, sau commit và chưa rõ

| Thời điểm phát sinh lỗi | Điều thường biết | Hành động phù hợp |
| --- | --- | --- |
| Sai tham số trước khi sửa dữ liệu | Chưa thực hiện nghiệp vụ | Sửa đầu vào; không retry nguyên dữ liệu |
| Validation lỗi trên bản staged | Trạng thái công bố không đổi | Sửa nguyên nhân; retry có điều kiện |
| Lỗi DB trước commit, rollback xác nhận thành công | Transaction được hủy trong phạm vi DB đó | Retry nếu lỗi tạm thời và thao tác an toàn |
| Lỗi trong lúc commit/mất phản hồi | Kết quả có thể không rõ | Đối chiếu trạng thái theo transaction/request ID |
| Lỗi notify sau commit | Nghiệp vụ chính đã thực hiện | Không tự gọi lại cả quy trình; phục hồi riêng bước notify |
| Lỗi trong lúc compensation | Hiệu ứng bù trừ có thể chưa rõ | Ghi tiến độ, kiểm tra, retry có giới hạn hoặc can thiệp |

Đặt timeout hợp lý, retry budget, backoff/jitter và idempotency trong các tác vụ có tác dụng phụ. Với thanh toán/chuyển tiền, tránh retry bằng một lệnh mới nếu chưa biết lệnh cũ đã được ghi nhận hay chưa. Không có chính sách retry “an toàn cho mọi exception”.

## 12. Thiết kế tài liệu hợp đồng khi phương thức ném exception

Bên cạnh `@throws`, API cần ghi rõ **trạng thái sau lỗi**. Chẳng hạn:

> Nếu lỗi xuất hiện trước khi cập nhật trạng thái sổ, số dư được công bố không thay đổi. Nếu cập nhật thành công rồi gửi thông báo lỗi, số dư đã đổi; caller phải kiểm tra trạng thái trước khi thử lại.

Nội dung hợp đồng cần trả lời được:

1. **Phạm vi phục hồi** là object, collection, DB transaction hay nhiều hệ thống?
2. **Điểm commit** cụ thể là gì? Có nhiều điểm commit ở các phụ thuộc khác nhau không?
3. Điều gì có thể bị caller hoặc luồng khác quan sát trước commit?
4. Khi lỗi, trạng thái được bảo đảm **không đổi**, **vẫn hợp lệ nhưng có thể thay đổi**, hay **chưa xác định**?
5. Ai là bên sở hữu transaction và có quyền quyết định rollback?
6. Bằng cách nào caller biết nên retry, tra cứu trạng thái hay thực hiện compensation?

Một exception có tên chính xác là hữu ích, nhưng **không thay thế mô tả trạng thái thực**. Nếu bọc ngoại lệ ở ranh giới tầng, giữ `cause` để truy vết và không biến mọi lỗi hạ tầng thành lỗi tham số hay trạng thái.

## 13. Kiểm thử điều kiện phục hồi, không chỉ kiểm tra exception

Một test chỉ assert `assertThrows` chưa chứng minh sự an toàn. Test nên kiểm tra **trạng thái trước/sau**, số lần gọi phụ thuộc, tài nguyên còn mở, dấu vết transaction và các tác dụng phụ.

| Tình huống | Kỳ vọng quan sát |
| --- | --- |
| Tham số không hợp lệ | Không đổi trạng thái, không gọi phụ thuộc |
| Lỗi khi tính bản staged | Bản công bố giữ nguyên, không rò reference bản dở |
| Lỗi giữa hai bước thay đổi có transaction | Rollback đủ những cập nhật cùng transaction; invariant DB giữ đúng |
| Rollback cũng lỗi | Giữ lỗi chính, có thông tin lỗi rollback; trạng thái chưa xác minh |
| Mất kết nối trong `commit()` | Không tự kết luận chưa commit; có quy trình đối chiếu |
| Gửi message lỗi sau commit | Transaction chính vẫn tồn tại, retry không gây cập nhật lặp |
| Hai request đồng thời thay đổi dữ liệu | Không lost update, invariant không bị phá |
| JVM chết ở các thời điểm khác nhau | Phục hồi từ dữ liệu bền vững, không dựa vào biến RAM |

Với chương trình `StateRollbackDemo`, hai assertion trọng tâm là: sau lỗi tiêm **trước commit** vẫn thấy `A=100, B=50`; sau exception notifier thì thấy `A=75, B=75`. Điều này tách rõ **lỗi của bước tổng thể** khỏi **trạng thái phần việc đã commit**.

Trong kiểm thử tích hợp, tiêm lỗi ở đúng ranh giới: trước ghi, sau ghi nhưng trước commit, trong commit, sau commit trước ACK, lúc rollback và khi khởi động lại. Mock exception trong cùng JVM không đủ chứng minh khả năng phục hồi sau mất điện hoặc mất kết nối thật.

## 14. Lỗi phổ biến khi triển khai rollback

- **Tin rằng `catch` tự đảo phép gán:** exception chỉ chuyển luồng điều khiển.
- **Dùng `finally` để phục hồi mọi thứ:** thường chỉ nên dùng cho cleanup; undo có điều kiện và khả năng lỗi riêng.
- **Chụp shallow copy rồi sửa object con:** snapshot không thật sự tách biệt.
- **Gán giá trị cũ khi đa luồng cùng sửa:** dễ ghi đè cập nhật hợp lệ của luồng khác.
- **Rollback một DB rồi tuyên bố toàn bộ request được hoàn tác:** phụ thuộc ngoài transaction không bị ảnh hưởng.
- **Nuốt exception khi rollback thất bại:** làm mất dấu vết, gây kết luận sai về dữ liệu.
- **Coi timeout `commit()` là chắc chắn chưa commit:** có thể gây transaction lặp.
- **Coi compensation là xóa toàn bộ lịch sử:** bù trừ là tác vụ mới, có rủi ro riêng.
- **Retry toàn bộ quy trình sau lỗi gửi thông báo:** có thể thực hiện nghiệp vụ chính thêm lần nữa.
- **Chỉ test happy path:** những bảo đảm rollback cần được thử ở điểm lỗi cụ thể.

## 15. Checklist triển khai thực tế

1. Vẽ thứ tự các bước có tác dụng phụ và các resource tham gia.
2. Ghi rõ **mức bảo đảm sau lỗi** cho từng resource và phạm vi quan sát.
3. Đẩy những thao tác có thể thất bại về trước điểm commit khi có thể.
4. Với trạng thái Java, ưu tiên copy/staging + công bố một lần; bảo vệ đồng thời và object con mutable.
5. Với DB, định nghĩa transaction boundary, isolation, locking và rollback đủ rõ.
6. Với file, xác định yêu cầu atomicity, durability và kế hoạch xử lý file tạm.
7. Với nhiều dịch vụ, thiết kế outbox, idempotency, compensation hoặc cơ chế coordination phù hợp.
8. Giữ lỗi gốc và thông tin lỗi phục hồi; ghi nhận trạng thái khi kết quả chưa rõ.
9. Đối chiếu trước retry trong trường hợp commit hoặc ACK không chắc chắn.
10. Kiểm thử cả trạng thái và side effect ở các mốc trước/sau commit, khi undo lỗi và khi ứng dụng crash.

**Nguyên tắc then chốt:** xử lý exception đúng phải bảo đảm **trạng thái sau lỗi đúng hợp đồng**. Rollback chỉ có ý nghĩa trong phạm vi có thể kiểm soát; sau khi một tác dụng phụ đã được hệ thống ngoài ghi nhận, giải pháp thường là đối chiếu và bù trừ có kiểm soát, không phải một lệnh `catch` có thể “quay ngược thời gian”.
