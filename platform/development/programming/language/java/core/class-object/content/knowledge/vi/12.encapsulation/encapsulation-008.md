# Ví dụ bảo vệ số dư và lịch sử giao dịch bằng đóng gói trong Java

## Mục tiêu

Sau bài này, bạn có thể:

- Thiết kế một lớp tài khoản có **số dư chỉ được thay đổi qua thao tác hợp lệ**, không cho caller ghi trực tiếp vào field.
- Đặt ra và duy trì quy tắc **số dư không âm**, số tiền giao dịch dương, giao dịch thành công được ghi lịch sử và giao dịch thất bại không làm biến đổi dữ liệu.
- Chỉ rõ vì sao `private long balance` **chưa đủ** nếu một setter vẫn cho phép giá trị sai hoặc phương thức ghi lịch sử có lỗ hổng.
- Viết `deposit` và `withdraw` kiểm tra preconditions, chống tràn `long`, rồi ghi **số dư mới và một bản ghi lịch sử nhất quán**.
- Phân biệt **danh sách lịch sử nội bộ mutable** với **snapshot chỉ đọc** cung cấp cho bên ngoài; không lộ reference cho phép caller sửa hoặc xóa lịch sử.
- Dùng Java 17 `record` để tạo bản ghi giao dịch bất biến với trường `sequence`, loại giao dịch, số tiền và số dư sau giao dịch.
- Kiểm thử identity, snapshot, exception safety, audit consistency và vấn đề đa luồng, đồng thời phân biệt mô hình học tập với yêu cầu hệ thống tài chính thực tế.
- Đọc, biên dịch và chạy các ví dụ độc lập với output xác định trước.

## 1. Bài toán: ai có quyền quyết định số dư và lịch sử?

Giả sử bạn quản lý một tài khoản đơn giản:

~~~text
Account
  id: "ACC-01"
  balance: 750
  history:
    #1 DEPOSIT  1000 -> balance 1000
    #2 WITHDRAW 250  -> balance 750
~~~

Trong ví dụ, mọi số tiền được đo bằng **đơn vị nhỏ nhất giả định**, lưu bằng `long` nguyên. Đây không phải mô hình đầy đủ cho tiền tệ đa quốc gia; mục đích là tập trung vào encapsulation và tính nhất quán.

Một API nguy hiểm:

~~~java
class BadAccount {
    public long balanceCents;
    public java.util.List<String> history = new java.util.ArrayList<>();
}
~~~

Caller có thể trực tiếp viết:

~~~java
BadAccount account = new BadAccount();
account.balanceCents = -100;
account.history.add("fake withdrawal");
account.history.clear();
~~~

Các đoạn trên chỉ là **minh họa** cần nằm trong ngữ cảnh Java hợp lệ. Chúng cho phép tạo số dư âm, bịa giao dịch hoặc xóa lịch sử mà không có kiểm soát. Ngay cả khi class có một method `deposit` đúng, caller vẫn có thể đi đường vòng qua public fields.

Để bảo vệ dữ liệu, class phải giữ quyền quyết định:

1. **Đường vào:** số dư ban đầu và các giao dịch được tạo theo cách nào?
2. **Quy tắc:** mỗi amount có hợp lệ không? Có đủ tiền để rút không? Có overflow không?
3. **Chuyển trạng thái:** số dư mới tương ứng giao dịch mới ra sao?
4. **Đường ra:** caller được đọc gì? Có nhận được tham chiếu mutable tới lịch sử nội bộ không?
5. **Thất bại:** khi thao tác bị từ chối, số dư và lịch sử có được giữ nguyên không?
6. **Tương tranh:** nếu nhiều threads cùng thao tác, các bước kiểm tra/ghi có được thực hiện nhất quán không?

**Kết luận đầu tiên:** đóng gói không chỉ là dùng `private`; nó là **bảo vệ hợp đồng trên toàn bộ các con đường tạo, cập nhật và quan sát trạng thái**.

## 2. Đặt invariants rõ ràng trước khi viết code

Trong phiên bản đơn giản với số dư ban đầu bằng 0 và chỉ có hai loại giao dịch `DEPOSIT`, `WITHDRAW`, các invariants hợp lý là:

- **I1:** `balanceCents >= 0` tại mọi thời điểm một public operation đã kết thúc bình thường.
- **I2:** lịch sử chỉ chứa bản ghi giao dịch **thực sự được class chấp nhận**; không có bản ghi từ lần nạp/rút bị từ chối.
- **I3:** mỗi giao dịch có `amountCents > 0` và số dư sau giao dịch không âm.
- **I4:** chuỗi giao dịch có `sequence` tăng lần lượt 1, 2, 3... mà không có số thứ tự dành cho lần giao dịch thất bại.
- **I5:** nếu duyệt lịch sử từ số dư 0, cộng các khoản nạp và trừ các khoản rút theo thứ tự thì kết quả phải bằng số dư hiện tại; `balanceAfterCents` trên từng bản ghi phải khớp kết quả tại bước đó.
- **I6:** caller không thể sửa, thêm, xóa hoặc đổi nội dung bản ghi đã được cung cấp qua lịch sử đọc.
- **I7:** một giao dịch không hợp lệ không làm thay đổi **cả số dư lẫn lịch sử**.

Các invariants này phù hợp với **mô hình một tài khoản, không có lãi suất, phí, hoàn tiền hay điều chỉnh số dư đặc biệt**. Nếu sau này thêm phí hoặc chuyển khoản, phải bổ sung loại giao dịch và cách đối chiếu tương ứng. Không được giữ công thức cũ rồi âm thầm đổi số dư.

### 2.1. Phân biệt precondition và postcondition

| Phương thức | Điều kiện trước khi thực hiện | Kết quả thành công |
| --- | --- | --- |
| `Account("ACC-01")` | ID không null/blank | Balance = 0, history rỗng |
| `deposit(amount)` | Amount dương, phép cộng không overflow | Balance tăng đúng amount; thêm một `DEPOSIT` |
| `withdraw(amount)` | Amount dương và không vượt balance | Balance giảm đúng amount; thêm một `WITHDRAW` |
| `balanceCents()` | Không có input | Trả một `long`, không cho sửa field bằng kết quả |
| `history()` | Không có input | Trả snapshot unmodifiable của các immutable entries |
| `snapshot()` | Không có input | Trả một giá trị chứa balance và history tại một thời điểm quan sát nhất quán trong mô hình phù hợp |

Các preconditions đều được kiểm tra trước khi ghi trạng thái. Đừng đợi đến sau khi trừ số dư mới phát hiện không đủ tiền.

## 3. Ví dụ chính Java 17: bảo vệ đồng thời số dư và lịch sử

Ví dụ này sử dụng:

- `private long balanceCents`: state số dư.
- `private final ArrayList<Transaction> history`: nơi lưu lịch sử **mutable nhưng chỉ nội bộ**.
- `record Transaction(...)`: một bản ghi dạng giá trị; chỉ chứa primitive values và enum nên không có mutable components.
- `List.copyOf(history)`: snapshot không sửa được, không phải reference trực tiếp tới `ArrayList` nội bộ.
- `Math.addExact`: ngăn số dư tràn kiểu `long`.
- Phương thức `appendAndCommit` nội bộ: thêm bản ghi rồi gán balance. Mọi input đã được kiểm tra **trước khi commit**.

Lưu **`ProtectedAccountHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ProtectedAccountHistoryDemo {
    enum Kind {
        DEPOSIT, WITHDRAW
    }

    record Transaction(
            long sequence,
            Kind kind,
            long amountCents,
            long balanceAfterCents) {

        Transaction {
            if (sequence <= 0) {
                throw new IllegalArgumentException("sequence must be positive");
            }
            Objects.requireNonNull(kind, "kind");
            if (amountCents <= 0 || balanceAfterCents < 0) {
                throw new IllegalArgumentException("invalid transaction values");
            }
        }

        String describe() {
            return "#" + sequence + " " + kind
                    + " amount=" + amountCents
                    + " balance=" + balanceAfterCents;
        }
    }

    static final class Account {
        private final String id;
        private long balanceCents;
        private final ArrayList<Transaction> history = new ArrayList<>();

        Account(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("account id is required");
            }
            this.id = id;
        }

        String id() {
            return id;
        }

        long balanceCents() {
            return balanceCents;
        }

        List<Transaction> history() {
            return List.copyOf(history);
        }

        void deposit(long amountCents) {
            requirePositive(amountCents);
            long updatedBalance = Math.addExact(balanceCents, amountCents);
            appendAndCommit(Kind.DEPOSIT, amountCents, updatedBalance);
        }

        void withdraw(long amountCents) {
            requirePositive(amountCents);
            if (amountCents > balanceCents) {
                throw new IllegalStateException("insufficient balance");
            }
            long updatedBalance = balanceCents - amountCents;
            appendAndCommit(Kind.WITHDRAW, amountCents, updatedBalance);
        }

        private static void requirePositive(long amountCents) {
            if (amountCents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        }

        private void appendAndCommit(
                Kind kind, long amountCents, long updatedBalance) {
            long sequence = Math.addExact((long) history.size(), 1L);
            Transaction entry = new Transaction(
                    sequence, kind, amountCents, updatedBalance);

            history.add(entry);
            balanceCents = updatedBalance;
        }
    }

    public static void main(String[] args) {
        Account account = new Account("ACC-01");
        System.out.println("initial=" + account.id()
                + " balance=" + account.balanceCents()
                + " entries=" + account.history().size());

        account.deposit(1000);
        account.withdraw(250);

        List<Transaction> earlier = account.history();
        System.out.println("after two=" + account.balanceCents()
                + " entries=" + earlier.size());

        for (Transaction entry : earlier) {
            System.out.println(entry.describe());
        }

        account.deposit(50);
        System.out.println("after new deposit=" + account.balanceCents()
                + " current=" + account.history().size());
        System.out.println("earlier snapshot=" + earlier.size());

        try {
            earlier.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("history cannot be cleared");
        }

        try {
            account.withdraw(1000);
        } catch (IllegalStateException expected) {
            System.out.println("withdraw rejected");
        }

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("overflow rejected");
        }

        System.out.println("final balance=" + account.balanceCents()
                + " entries=" + account.history().size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ProtectedAccountHistoryDemo.java
java ProtectedAccountHistoryDemo
~~~

**Stdout chính xác:**

~~~text
initial=ACC-01 balance=0 entries=0
after two=750 entries=2
#1 DEPOSIT amount=1000 balance=1000
#2 WITHDRAW amount=250 balance=750
after new deposit=800 current=3
earlier snapshot=2
history cannot be cleared
withdraw rejected
overflow rejected
final balance=800 entries=3
~~~

### 3.1. Truy vết hai giao dịch đầu

Khởi đầu:

~~~text
balanceCents = 0
history = []
~~~

Sau `deposit(1000)`:

~~~text
balanceCents = 1000
history = [
  #1 DEPOSIT amount=1000 balanceAfter=1000
]
~~~

Sau `withdraw(250)`:

~~~text
balanceCents = 750
history = [
  #1 DEPOSIT  amount=1000 balanceAfter=1000,
  #2 WITHDRAW amount=250  balanceAfter=750
]
~~~

Không có setter `setBalanceCents`, cũng không có `addTransaction(Transaction)` public. Caller chỉ yêu cầu **hành vi**. Class tự quyết định lúc nào thay đổi số dư và lúc nào ghi bản ghi.

### 3.2. Vì sao lần nạp tiếp theo không sửa snapshot cũ?

`List<Transaction> earlier = account.history()` nhận **list không sửa được** với hai entries tại thời điểm gọi. Khi thực hiện `account.deposit(50)`, lịch sử nội bộ có ba entries, nhưng biến `earlier` vẫn giữ danh sách gồm hai entries.

Đây là **snapshot về cấu trúc danh sách**, khác với một **view** sống của list nội bộ. Trong ví dụ các entries là immutable records nên cả nội dung entries cũng không bị thay đổi tại chỗ.

### 3.3. Vì sao rút 1000 thất bại mà số dư vẫn 800?

Sau ba giao dịch, balance = 800. `withdraw(1000)` gặp `amountCents > balanceCents` và ném `IllegalStateException` **trước** lời gọi `appendAndCommit`. Do đó không có phép trừ và không có thêm transaction.

Nếu method lỡ ghi transaction trước rồi mới kiểm tra đủ tiền, ta có thể để lại một bản ghi giả mạo hoặc làm balance sai. Thứ tự validation trước commit là thiết yếu.

### 3.4. Vì sao nạp `Long.MAX_VALUE` bị từ chối?

`balanceCents` đang là 800, nên `Math.addExact(800, Long.MAX_VALUE)` vượt miền biểu diễn `long` và ném `ArithmeticException`. Chưa có `updatedBalance` hợp lệ, nên `appendAndCommit` **không chạy**. Balance và history giữ nguyên.

Nếu dùng `balanceCents += amountCents` kiểu `long`, phép cộng có thể overflow thành một giá trị sai, thậm chí âm, phá invariant `balanceCents >= 0`.

## 4. Chọn loại tiền và đơn vị: đừng dùng `double` cho số tiền chính xác

Ví dụ trên sử dụng `long` theo đơn vị nhỏ nhất như “cents” minh họa. Không có nghĩa mọi loại tiền có đúng hai chữ số sau dấu thập phân.

### 4.1. Vì sao `double` nguy hiểm?

Các phân số thập phân như 0.1 thường không có biểu diễn nhị phân chính xác trong `double`. Khi thực hiện nhiều phép cộng/trừ, sai số floating-point có thể làm logic so sánh số dư khó tin cậy.

Ví dụ minh họa:

~~~java
double value = 0.1 + 0.2;
System.out.println(value);
~~~

Trên Java thông thường, dòng in là `0.30000000000000004`. Đây là đặc tính biểu diễn nhị phân, không phải lỗi riêng của Java. Với dữ liệu tài chính cần độ chính xác thập phân, nhiều hệ thống dùng **`BigDecimal` với scale/rounding được xác định** hoặc một kiểu money rõ mã tiền tệ/đơn vị.

### 4.2. Cần thống nhất đơn vị của mọi phương thức

Đặt tên tham số `amountCents` giúp caller biết dữ liệu là đơn vị nhỏ nhất giả định. Tránh:

~~~java
deposit(100);
~~~

mà không có tài liệu nêu rõ `100` nghĩa là 100 đồng, 100 cents hay 100 đơn vị khác.

Một API có thể dùng wrapper/value object `Money` để mang theo currency và scale. Đó là cải tiến thiết kế khi nghiệp vụ phức tạp; trong bài này kiểu `long` giúp tập trung vào nguyên tắc đóng gói số dư và lịch sử.

## 5. `private` field chưa đủ nếu getter trả reference mutable

Một thiết kế dễ bị phá:

~~~java
class UnsafeHistory {
    private final java.util.ArrayList<String> history =
            new java.util.ArrayList<>();

    java.util.ArrayList<String> getHistory() {
        return history;
    }
}
~~~

Dù field `history` là `private final`, getter trả **chính reference tới ArrayList nội bộ**. Caller có thể:

~~~java
UnsafeHistory object = new UnsafeHistory();
object.getHistory().add("FAKE TRANSACTION");
object.getHistory().clear();
~~~

Đây là đoạn minh họa đặt trong method. Không cần truy cập trực tiếp field: caller đã có reference đến list mutable và có thể thao tác lên chính object đó. `final` chỉ hạn chế **gán lại field reference**, không khiến object ArrayList bất biến.

### 5.1. Chương trình chạy được: phá lịch sử qua getter

Lưu **`LeakingHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LeakingHistoryDemo {
    static final class Account {
        private long balance = 100;
        private final List<String> history = new ArrayList<>();

        Account() {
            history.add("OPEN balance=100");
        }

        long balance() {
            return balance;
        }

        List<String> history() {
            return history; // Lộ reference mutable!
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        System.out.println("before=" + account.balance()
                + " records=" + account.history().size());

        account.history().clear();
        account.history().add("FAKE withdrawal 999");

        System.out.println("after=" + account.balance()
                + " records=" + account.history().size());
        System.out.println("history=" + account.history().get(0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LeakingHistoryDemo.java
java LeakingHistoryDemo
~~~

Output:

~~~text
before=100 records=1
after=100 records=1
history=FAKE withdrawal 999
~~~

Thao tác `clear` rồi `add` khiến danh sách lịch sử bị thay đổi hoàn toàn; số dư 100 vẫn nguyên. Nếu lớp có invariant lịch sử phản ánh các thay đổi số dư, invariant đã bị caller phá mà không gọi `deposit` hay `withdraw`.

**Điểm học:** không trả trực tiếp mutable collections (hoặc mutable arrays/objects) thuộc representation nội bộ nếu caller không được quyền sửa chúng.

## 6. `List.copyOf`, `Collections.unmodifiableList` và defensive copy

Ba cách thường gặp cần phân biệt:

| Cách trả lịch sử | Caller sửa qua kết quả? | Có theo kịp thay đổi danh sách nguồn? | Ghi chú |
| --- | --- | --- | --- |
| `return history;` | **Có**, nếu history mutable | Chính object đó | Không bảo vệ representation |
| `return Collections.unmodifiableList(history);` | Không thể gọi các thao tác sửa qua view | **Có thể**, vì view bám backing list | Read-only view, không phải snapshot |
| `return List.copyOf(history);` | Không sửa được list kết quả | Không phản ánh thêm/xóa sau đó của mutable source | Snapshot cấu trúc; phần tử có thể vẫn share |
| `return new ArrayList<>(history);` | Có thể sửa list kết quả | Không ảnh hưởng list nguồn nếu chỉ thêm/xóa slot | Mutable shallow copy, có thể phù hợp một số API |

Với lịch sử giao dịch không cho caller sửa, `List.copyOf(history)` phù hợp vì dễ dùng như **read-only snapshot**. Nhưng `List.copyOf` **không deep-copy elements**. Nếu mỗi entry là một mutable `Transaction` class có setter, người nhận vẫn có thể sửa fields của entry mà account cũng giữ reference.

Trong ví dụ chính, `Transaction` là `record` với các components chỉ là primitives và enum; không cung cấp mutable nested object. Do đó caller không sửa được nội dung một entry thông qua accessor thông thường.

### 6.1. Record không đồng nghĩa deep immutable trong mọi trường hợp

~~~java
record Report(java.util.List<String> lines) { }
~~~

Đoạn này hợp lệ nhưng không tự bảo vệ `lines`. Nếu caller truyền mutable list rồi giữ reference, `Report` có thể quan sát list đổi. Muốn record dạng snapshot, có thể chuẩn hóa trong compact constructor:

~~~java
record Report(java.util.List<String> lines) {
    Report {
        lines = java.util.List.copyOf(lines);
    }
}
~~~

Với kiểu `Report` thứ hai, component field được khởi tạo bằng unmodifiable list snapshot. Các phần tử `String` immutable, giúp snapshot vững hơn. Đây là hai phiên bản thay thế cùng tên, không được khai báo đồng thời trong một source file.

**Lưu ý:** ngay cả khi record immutable, không nên trao quyền tạo ra “transaction được xác nhận” qua một public API cho phép caller gửi bất kỳ bản ghi giả vào lịch sử. Lịch sử phải do **Account**, không phải caller, quyết định bản ghi nào là sự kiện đã xảy ra.

## 7. Ghi lịch sử và số dư ở cùng một đường commit

Tình huống rủi ro:

~~~java
void depositBad(long amount) {
    balanceCents += amount;
    history.add(new Transaction(/* ... */));
}
~~~

Đây là **pseudocode minh họa**, không phải method runnable vì thiếu khai báo constructor `Transaction`. Nó dễ gây lỗi nếu:

- Amount không được kiểm tra.
- Phép cộng tràn.
- Tạo Transaction thất bại sau khi số dư đã tăng.
- Caller có đường ghi balance hoặc history khác bỏ qua một trong hai bước.
- Một thread khác đọc giữa hai lần cập nhật khi code không đồng bộ hóa.

### 7.1. Chuỗi an toàn hơn trong mô hình đơn luồng

~~~text
1. Nhận yêu cầu deposit/withdraw
2. Kiểm tra amount hợp lệ
3. Kiểm tra số dư có đủ hoặc cộng có overflow không
4. Tính updatedBalance vào biến local
5. Tạo immutable Transaction dự kiến
6. Thêm Transaction vào history nội bộ
7. Gán balanceCents = updatedBalance
8. Method trả về thành công
~~~

Với mọi lỗi **đã dự liệu trước** về input, trạng thái hoặc overflow, method ném trước bước 6. Trong mô hình Java với instance ArrayList nội bộ không bị alias ra ngoài, đây là một trình tự có thể suy luận và kiểm thử.

Đối với những lỗi ngoài phạm vi hợp đồng như hết bộ nhớ, sự cố hệ thống hoặc nhiều threads đọc/ghi không đồng bộ, **không nên tuyên bố có transaction ACID tuyệt đối**. Phần dưới tách rõ mô hình học tập với yêu cầu hệ thống thật.

### 7.2. Vì sao thêm history trước rồi gán balance?

Trong ví dụ chính, `appendAndCommit` dùng:

~~~java
history.add(entry);
balanceCents = updatedBalance;
~~~

Đến đây đã có `Transaction` hợp lệ và `updatedBalance` được tính trước. Nếu `history.add` không hoàn tất và ném exception, phép gán số dư phía sau **không chạy**. Khi `add` hoàn thành bình thường, phép gán primitive `long` là thao tác không có bước validation hay I/O gây exception trong code.

Vẫn tồn tại **khoảng thời gian giữa hai lệnh**: một thread khác truy cập không đồng bộ có thể quan sát history đã được thêm nhưng balance chưa cập nhật. Do đó các phương thức ở ví dụ chính chỉ bảo đảm trạng thái nhất quán theo hợp đồng **không có truy cập cạnh tranh không đồng bộ**. Muốn thread safety, phải bảo vệ cả chuỗi kiểm tra + commit + snapshot.

### 7.3. Nếu transaction log được ghi ra database?

Khi history ở database và balance cũng được lưu bền vững, đây là hai thay đổi phải phối hợp qua **transaction database** hoặc kiến trúc nhất quán phù hợp. Việc bảo vệ fields trong Java object **không tự rollback database** khi câu lệnh thứ hai thất bại.

Những mẫu như event sourcing, ledger append-only, outbox pattern hoặc transaction manager có thể phù hợp, nhưng cần thiết kế riêng về durability, concurrency, duplicate requests và recovery.

## 8. Đảm bảo số dư và nhật ký khớp nhau bằng replay

Với mô hình không phí/không lãi, bạn có thể **tái tính số dư** từ lịch sử:

~~~text
running = 0
for each transaction in sequence:
    if DEPOSIT  then running = running + amount
    if WITHDRAW then running = running - amount
    verify running == transaction.balanceAfter
verify running == account.balanceCents
~~~

Nếu có một bản ghi sai hoặc số dư bị sửa ngoài giao dịch, kiểm tra đối chiếu có thể phát hiện không khớp.

### 8.1. Chương trình chạy độc lập: kiểm tra invariant từ snapshot

Lưu **`HistoryInvariantDemo.java`**:

~~~java
import java.util.List;

public class HistoryInvariantDemo {
    enum Kind { DEPOSIT, WITHDRAW }

    record Transaction(
            long sequence, Kind kind,
            long amount, long balanceAfter) { }

    static long replayAndVerify(List<Transaction> history) {
        long running = 0;
        long expectedSequence = 1;

        for (Transaction item : history) {
            if (item.sequence() != expectedSequence++) {
                throw new IllegalStateException("sequence mismatch");
            }
            if (item.amount() <= 0) {
                throw new IllegalStateException("invalid amount");
            }

            if (item.kind() == Kind.DEPOSIT) {
                running = Math.addExact(running, item.amount());
            } else if (item.kind() == Kind.WITHDRAW) {
                if (item.amount() > running) {
                    throw new IllegalStateException("overdraft in log");
                }
                running -= item.amount();
            } else {
                throw new IllegalStateException("unknown kind");
            }

            if (item.balanceAfter() != running) {
                throw new IllegalStateException("balance mismatch");
            }
        }
        return running;
    }

    public static void main(String[] args) {
        List<Transaction> valid = List.of(
                new Transaction(1, Kind.DEPOSIT, 1000, 1000),
                new Transaction(2, Kind.WITHDRAW, 250, 750),
                new Transaction(3, Kind.DEPOSIT, 50, 800));

        System.out.println("replayed balance=" +
                replayAndVerify(valid));

        List<Transaction> invalid = List.of(
                new Transaction(1, Kind.DEPOSIT, 1000, 999));

        try {
            replayAndVerify(invalid);
        } catch (IllegalStateException expected) {
            System.out.println("tampered balance detected");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac HistoryInvariantDemo.java
java HistoryInvariantDemo
~~~

Output:

~~~text
replayed balance=800
tampered balance detected
~~~

**Giải thích:**

- Danh sách hợp lệ có ba events: nạp 1000 → rút 250 → nạp 50, kết quả 800.
- Mỗi `balanceAfter` được so với tổng đang chạy.
- Danh sách sai ghi số dư sau nạp là 999 thay vì 1000; replay phát hiện và ném exception.

**Không phải cơ chế phát hiện gian lận an ninh hoàn chỉnh:** nếu kẻ tấn công có quyền sửa **cả số dư và mọi bản ghi**, một phép replay nội bộ vẫn có thể khớp dữ liệu đã bị giả mạo. Với audit thực tế cần bảo vệ truy cập, tính bền vững, chữ ký/hashes, phân quyền và lưu trữ bất biến phù hợp.

## 9. Một đối tượng giao dịch nên chứa những gì?

Một record trong ví dụ chính chứa:

| Trường | Vai trò | Quy tắc gợi ý |
| --- | --- | --- |
| `sequence` | Thứ tự giao dịch trong một account | Dương, tăng liên tiếp trong model |
| `kind` | `DEPOSIT` hoặc `WITHDRAW` | Không null, dùng enum |
| `amountCents` | Số tiền giao dịch | Dương |
| `balanceAfterCents` | Số dư sau thao tác | Không âm; phải khớp thay đổi theo kind |

Một hệ thống lớn có thể thêm `transactionId` duy nhất, timestamp, currency, requestId/idempotency key, trạng thái xử lý, loại phí, nguồn/đích, actor, metadata và dấu vết kiểm toán.

### 9.1. Timestamp có cần không?

Có thể có ích, nhưng **không bắt buộc** trong ví dụ nhỏ để hiểu encapsulation. Nếu ghi thời gian, nên phân biệt:

- **Thời điểm nghiệp vụ** (người dùng tạo yêu cầu).
- **Thời điểm hệ thống chấp nhận/ghi giao dịch**.
- **Thời điểm giao dịch được hoàn tất/settled** (nếu có).

Đừng dùng `LocalDateTime.now()` trong bài yêu cầu stdout cố định rồi viết một timestamp tùy ý như output chính xác. Để test tái lập, nên dùng `Clock.fixed(...)` hoặc truyền clock vào đối tượng.

### 9.2. Sequence không đủ thay transaction ID toàn hệ thống

`sequence` từ 1,2,3 theo một account không phải ID toàn cục. Hai tài khoản đều có thể có transaction #1. Nếu đối chiếu cross-account hay database, cần key có đủ thông tin như `(accountId, sequence)` hoặc ID duy nhất theo thiết kế.

### 9.3. Có nên lưu `balanceAfter` trong record?

Lợi ích: dễ audit/hiển thị trạng thái sau mỗi giao dịch. Bất lợi: thêm một giá trị **có thể không nhất quán** nếu code tạo log sai. Trong ví dụ, `Account` tạo record dựa trên `updatedBalance` đã tính và có thể dùng replay để kiểm tra.

Một phương án khác là chỉ lưu event loại và amount, tính balance bằng replay khi cần. Đây là một lựa chọn trade-off giữa performance, dữ liệu dư thừa, độ tin cậy và kiến trúc logging.

## 10. Ngoại lệ và cam kết không thay đổi dữ liệu khi bị từ chối

Trong lớp `Account` ở ví dụ chính:

| Lời gọi | Kết quả | Balance/history |
| --- | --- | --- |
| `deposit(0)` | `IllegalArgumentException` | Không đổi |
| `deposit(-10)` | `IllegalArgumentException` | Không đổi |
| `withdraw(0)` | `IllegalArgumentException` | Không đổi |
| `withdraw(-5)` | `IllegalArgumentException` | Không đổi |
| `withdraw(1000)` khi balance 800 | `IllegalStateException` | Không đổi |
| `deposit(Long.MAX_VALUE)` khi balance 800 | `ArithmeticException` | Không đổi |
| `new Account(null)` | `IllegalArgumentException` | Không có account được constructor trả về thành công |
| `new Account("  ")` | `IllegalArgumentException` | Không có account được tạo thành công cho caller |
| `history().clear()` | `UnsupportedOperationException` | Không sửa lịch sử nội bộ |

Các loại exception có thể được thay bằng **domain-specific exceptions** trong API nghiệp vụ. Điều quan trọng là hợp đồng rõ, phân biệt input sai, trạng thái không cho phép và lỗi số học.

Không nên bắt rồi bỏ qua tất cả exceptions:

~~~java
try {
    account.withdraw(1000);
} catch (Exception ignored) {
    // Không nên âm thầm làm caller tưởng đã rút tiền thành công.
}
~~~

Caller cần biết thao tác có được chấp nhận không. Trong ví dụ có `catch` để **in minh họa**, không phải khuyến nghị bỏ qua lỗi trong phần mềm thật.

### 10.1. Đừng ghi giao dịch thất bại vào ledger thành công

Nếu gọi `withdraw(1000)` khi balance 800, method phải từ chối trước khi log thành công. Có thể có **nhật ký yêu cầu bị từ chối** riêng phục vụ audit/an ninh, nhưng đó **không phải** giao dịch đã trừ số dư.

Hãy tách:

- **Ledger/successful transactions:** sự kiện thật sự thay đổi balance.
- **Operational/audit attempts:** yêu cầu, xác thực, từ chối, lỗi kỹ thuật; có thể không làm thay đổi balance.

Trộn hai loại mà không có trường status/semantic rõ sẽ làm công thức replay sai.

## 11. Lịch sử trả về nên là snapshot hay live view?

Giả sử caller gọi:

~~~java
List<Transaction> firstRead = account.history();
account.deposit(25);
~~~

Với `List.copyOf(history)` như ví dụ chính, `firstRead` **không tự được bổ sung** giao dịch nạp 25. Caller muốn dữ liệu mới thì gọi `account.history()` lần nữa.

Snapshot có lợi:

- Bên gọi có một kết quả ổn định để hiển thị hoặc xử lý.
- Không thể sửa cấu trúc list nội bộ.
- Tránh việc iterator của một live mutable list nhìn thấy các thay đổi bất ngờ trong lúc duyệt ở mô hình không concurrent.

Nhược điểm:

- Mỗi lần chụp từ ArrayList mutable có chi phí sao chép theo số lượng entries.
- Với lịch sử rất lớn, việc copy toàn bộ có thể tốn CPU/bộ nhớ.
- Snapshot nhiều lần vẫn có thể có tuổi dữ liệu khác nhau.

Một API lớn có thể cung cấp **phân trang**, truy vấn theo sequence hoặc persistence-based history queries. Không vì tối ưu hiệu năng mà tùy tiện trả `ArrayList` nội bộ cho caller sửa.

### 11.1. Không đồng nghĩa “read-only interface” với “immutable state”

Trả về kiểu `List<Transaction>` chỉ quy định những method mà compiler nhìn thấy qua interface; `List` vẫn có `add`, `remove`. Nếu implementation thực tế là `ArrayList` mutable nội bộ, caller có thể dùng các mutating methods.

Phải có **hợp đồng và implementation** tương ứng: unmodifiable snapshot, immutable records hoặc cách bảo vệ khác phù hợp.

## 12. Rủi ro với các entry objects mutable

Giả sử thay `record Transaction` bằng:

~~~java
class MutableTransaction {
    private long amount;

    MutableTransaction(long amount) {
        this.amount = amount;
    }

    void setAmount(long amount) {
        this.amount = amount;
    }

    long amount() {
        return amount;
    }
}
~~~

Nếu history chứa các `MutableTransaction` objects và getter trả `List.copyOf(history)`, caller không thể thêm/xóa phần tử trong list kết quả, **nhưng có thể gọi `setAmount` trên một entry** nếu quyền truy cập cho phép. Nếu đó là cùng entry object được history giữ, lịch sử nội bộ bị sửa.

Cách bảo vệ:

1. Ưu tiên immutable record/value object không chứa mutable references nếu mô hình cho phép.
2. Nếu bắt buộc dùng entry mutable nội bộ, trả **immutable DTO snapshot** được xây dựng từ state entry, không lộ object mutable.
3. Với nested collections, copy tới đúng độ sâu cần thiết và định nghĩa ownership rõ ràng.

**Kết luận:** bất biến của **danh sách** và bất biến của **từng giao dịch** là hai yêu cầu khác nhau. Bài ví dụ chính giải quyết cả hai bằng unmodifiable list snapshot **và** immutable record components.

## 13. Kiểm tra tính bất biến của transaction record

Trong Java 17, record như:

~~~java
record Transaction(
        long sequence,
        Kind kind,
        long amountCents,
        long balanceAfterCents) { }
~~~

được compiler tạo các private final component fields và accessors như `sequence()`, `amountCents()`. Nếu components chỉ gồm primitive values và enum thì người dùng API không có mutating setter thông thường.

Nhưng cần nhớ:

- Record không tự validate rằng `amountCents > 0`; compact constructor trong ví dụ chính làm việc đó.
- Record không tự đảm bảo một entry **đã từng là giao dịch được chấp nhận**; chỉ `Account` kiểm soát việc append vào history mới đảm bảo điều đó.
- Record không tự deep-copy mutable components như `List` hoặc array; với các kiểu đó, cần defensive copying.
- Việc khai báo record không thay thế thiết kế lưu trữ lịch sử bền vững hoặc cơ chế chống chỉnh sửa dữ liệu ở mức hệ thống.

### 13.1. Vì sao dùng enum cho loại giao dịch?

`enum Kind { DEPOSIT, WITHDRAW }` giúp ngăn những string tự do như `"DEPOSITT"`, `"minus"` hoặc `"withdraw!!"`. Mã xử lý theo loại giao dịch rõ ràng hơn. Nhưng method có thể nhận enum `null` nếu không kiểm tra; vì vậy Transaction compact constructor gọi `Objects.requireNonNull(kind)`.

Một lịch sử có nhiều loại event sẽ cần mở rộng enum và logic replay. Nếu thêm `REFUND`/`FEE`, phải quyết định chính xác tác động lên số dư trước khi ghi sự kiện.

## 14. Đóng gói không đồng nghĩa bảo mật nghiệp vụ

Một `private balanceCents` không ngăn caller có quyền gọi `deposit` tự ý tăng balance trong mô hình đơn giản. Đây là bài học kỹ thuật class/object, không phải ngân hàng thật.

Trong hệ thống thực cần xác định:

- **Authorization:** ai được thực hiện loại giao dịch nào?
- **Authentication:** xác định người thực hiện.
- **Idempotency:** yêu cầu bị gửi lặp có bị ghi hai lần không?
- **Persistent transactions:** cập nhật balance và ledger có được ghi bền vững và nhất quán không?
- **Concurrency control:** hai lệnh rút tiền đồng thời có thể cùng đọc số dư cũ không?
- **Auditability:** log có chống sửa/xóa trái phép và có thể đối soát độc lập không?
- **Currency/precision:** đơn vị và làm tròn rõ ràng.
- **Recovery:** crash giữa các bước có thể khôi phục trạng thái không?

Tất cả không thể được giải quyết chỉ bằng `private`, `final` hoặc unmodifiable list trong một Java object.

### 14.1. Vì sao không nên cung cấp `public void addTransaction(...)`?

Nếu caller được tự cung cấp `Transaction` và class chỉ thêm nó vào list, caller có thể bịa lịch sử mà balance không đổi. Cần quy định **chủ sở hữu việc phát sinh sự kiện**: chỉ những operations được class xác nhận như `deposit`, `withdraw` mới append successful transaction.

Ngay cả nếu công bố API đọc lịch sử cho UI, **API ghi lịch sử thành công** không nên là một setter tùy tiện.

## 15. Chuyển khoản giữa hai accounts phức tạp hơn deposit/withdraw

Một lỗi thiết kế dễ xảy ra:

~~~java
source.withdraw(amount);
destination.deposit(amount);
~~~

Giả sử `source.withdraw(amount)` thành công, nhưng `destination.deposit(amount)` bị lỗi overflow hoặc lỗi lưu trữ. Khi đó nguồn đã trừ tiền và ghi lịch sử rút, đích chưa cộng. Hai object có thể **không nhất quán về tổng tài sản**.

### 15.1. Với hai accounts, invariant xuyên object

Nếu chuyển amount `m` từ A sang B, ta muốn:

~~~text
A.balanceAfter = A.balanceBefore - m
B.balanceAfter = B.balanceBefore + m
Cả hai ghi giao dịch tương ứng, hoặc cả hai không thay đổi
~~~

Đây là invariant **giữa hai objects**, không chỉ riêng một account. Việc gọi hai public methods độc lập **không tự bảo đảm atomicity**.

Các lựa chọn thiết kế phụ thuộc bối cảnh:

- Thực hiện kiểm tra trước cho cả hai accounts, rồi có cơ chế lock/transaction bảo vệ toàn bộ commit.
- Dùng một service phụ trách transfer và phối hợp thay đổi của hai accounts.
- Nếu dữ liệu nằm trong DB, dùng transaction và isolation phù hợp; xem cả trường hợp retries.
- Với event-driven/distributed systems, cần chiến lược consistency/idempotency/compensation được thiết kế rõ.

**Không lấy `synchronized` riêng từng method `withdraw`/`deposit` làm bằng chứng một transfer hai objects đã atomic.** Hai lời gọi tuần tự trên hai locks riêng vẫn có thể bị quan sát ở trạng thái chuyển khoản dở dang.

## 16. Thread safety: bảo vệ cả thao tác kiểm tra và commit

Trong ví dụ chính, Account **chưa thread-safe**. Nếu hai threads cùng `withdraw(700)` khi balance 1000, cả hai có thể đọc 1000 trước khi một thread cập nhật, rồi cả hai cùng chấp nhận. Điều này có thể phá việc đối chiếu lịch sử và số dư.

Một cách mô hình hóa đơn giản là đồng bộ hóa trên **cùng một monitor** mọi phương thức đọc/ghi state liên quan. Ví dụ độc lập:

Lưu **`SynchronizedAccountDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SynchronizedAccountDemo {
    record Entry(long amount, long balanceAfter) { }

    static final class Account {
        private long balance;
        private final List<Entry> entries = new ArrayList<>();

        synchronized void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            long next = Math.addExact(balance, amount);
            Entry entry = new Entry(amount, next);
            entries.add(entry);
            balance = next;
        }

        synchronized long balance() {
            return balance;
        }

        synchronized List<Entry> entries() {
            return List.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        account.deposit(100);
        account.deposit(50);

        System.out.println("balance=" + account.balance());
        System.out.println("entries=" + account.entries().size());
    }
}
~~~

Chạy:

~~~bash
javac SynchronizedAccountDemo.java
java SynchronizedAccountDemo
~~~

Output:

~~~text
balance=150
entries=2
~~~

**Giới hạn của ví dụ đồng bộ:**

- Mọi method trong ví dụ truy cập `balance` hoặc `entries` đều synchronized trên **cùng Account object**, giúp bảo vệ những operations hiện có khỏi truy cập cạnh tranh không đồng bộ qua chính API đó.
- Nhưng caller gọi `balance()` rồi `entries()` trong **hai lời gọi riêng** có thể nhận dữ liệu từ **hai thời điểm khác nhau** nếu một thread khác nạp tiền ở giữa. Cần một method `snapshot()` chụp cả balance và history trong **cùng lock** nếu muốn một view nhất quán của hai trường.
- `synchronized` trong memory không tự bảo đảm persistence/DB atomicity hoặc transfer xuyên nhiều accounts.
- Nếu thêm methods khác đọc/ghi state mà không tuân cùng synchronization contract, thread safety có thể lại bị phá.

### 16.1. Snapshot hai thành phần trong cùng lock

Ví dụ ý tưởng có thể đặt trong một class có fields `balance` và `entries`:

~~~java
record AccountSnapshot(long balance, List<Entry> entries) {
    AccountSnapshot {
        entries = List.copyOf(entries);
    }
}

synchronized AccountSnapshot snapshot() {
    return new AccountSnapshot(balance, entries);
}
~~~

Đây là **mảnh minh họa**, cần đặt `record AccountSnapshot` và method trong cấu trúc class thích hợp, với `Entry` immutable. Khi chụp, cả balance và list snapshot được đọc/copy dưới cùng lock, tránh nhận một cặp từ hai thời điểm khác nhau.

Trong hệ thống thật, việc khóa object lâu để sao chép lịch sử lớn có thể ảnh hưởng hiệu năng; cân nhắc phân trang, snapshot versioning hoặc kiến trúc lưu trữ phù hợp.

## 17. Kiểm thử không chỉ happy path

Một class có invariant phải được test **trước, trong và sau** những thao tác không hợp lệ.

### 17.1. Ma trận kiểm thử Account

| Trường hợp | Kỳ vọng |
| --- | --- |
| `new Account("A")` | Balance 0, history rỗng |
| `new Account(null)` hoặc `new Account("  ")` | Bị từ chối |
| `deposit(100)` | Balance 100, history thêm `DEPOSIT 100` |
| `withdraw(40)` sau khi có 100 | Balance 60, history thêm `WITHDRAW 40` |
| `deposit(0)`, `deposit(-1)` | Exception, state không đổi |
| `withdraw(0)`, `withdraw(-1)` | Exception, state không đổi |
| `withdraw(1000)` khi chỉ có 60 | Exception, state không đổi |
| Nạp khiến `long` overflow | Exception, state không đổi |
| Lấy `history()` rồi `clear()` | `UnsupportedOperationException`; internal history không đổi |
| Lấy snapshot cũ, sau đó nạp thêm | Snapshot cũ giữ nguyên entries |
| Replay successful entries | Khớp current balance và từng balanceAfter |
| Nhiều threads rút/nạp cùng Account | Cần concurrency test **nếu** class công bố thread-safe contract |

### 17.2. Test trạng thái sau lỗi

Lưu **`RejectedOperationStateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RejectedOperationStateDemo {
    static final class Account {
        private long balance;
        private final List<Long> deposits = new ArrayList<>();

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }
            long next = Math.addExact(balance, amount);
            deposits.add(amount);
            balance = next;
        }

        long balance() {
            return balance;
        }

        List<Long> deposits() {
            return List.copyOf(deposits);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        account.deposit(10);

        long beforeBalance = account.balance();
        List<Long> beforeHistory = account.deposits();

        try {
            account.deposit(-5);
        } catch (IllegalArgumentException expected) {
            System.out.println("negative rejected");
        }

        System.out.println("balance unchanged=" +
                (beforeBalance == account.balance()));
        System.out.println("history unchanged=" +
                beforeHistory.equals(account.deposits()));

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException expected) {
            System.out.println("overflow rejected");
        }

        System.out.println("final=" + account.balance()
                + " history=" + account.deposits());
    }
}
~~~

Chạy:

~~~bash
javac RejectedOperationStateDemo.java
java RejectedOperationStateDemo
~~~

Output:

~~~text
negative rejected
balance unchanged=true
history unchanged=true
overflow rejected
final=10 history=[10]
~~~

Đây là **ví dụ phụ chỉ quản lý deposits** để cô lập phép kiểm tra trạng thái không đổi khi thất bại. Ví dụ chính mới là mô hình đầy đủ deposit/withdraw với Transaction record.

### 17.3. Tại sao không chỉ so kích thước lịch sử?

Một phương thức sai có thể **sửa nội dung một entry** nhưng giữ nguyên kích thước list. Vì thế test invariant nên kiểm tra:

- Balance.
- Số entries.
- Thứ tự/sequence.
- Loại, amount và balanceAfter của từng entry.
- Bản ghi có bị sửa/xóa qua reference đã trả không.
- Lịch sử replay có khớp số dư không.

Với immutable transaction values và unmodifiable snapshot, việc kiểm tra và suy luận đáng tin cậy hơn nhiều.

## 18. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| `public balanceCents` | Caller tự tăng/giảm tùy ý | `private` field và operations hợp lệ |
| `private balance` nhưng `setBalance(any)` public | Caller vẫn phá invariant qua setter | Ưu tiên `deposit`/`withdraw` và validation |
| Kiểm tra amount sau khi cập nhật balance | Thất bại để lại state sai | Validate trước commit |
| Cộng `long` mà không kiểm tra overflow | Balance có thể tràn thành số âm | `Math.addExact`/kiểu tiền phù hợp |
| Rút khi amount > balance | Có thể tạo số dư âm | Kiểm tra trước khi trừ |
| Cho caller ghi trực tiếp history | Caller thêm giao dịch giả/xóa giao dịch thật | Chỉ Account append khi thao tác được chấp nhận |
| Trả `ArrayList` nội bộ qua getter | Caller sửa/xóa lịch sử | Trả unmodifiable snapshot |
| Dùng `Collections.unmodifiableList(internal)` và nghĩ là snapshot | Live view có thể phản ánh thay đổi sau đó | Dùng `List.copyOf` nếu cần snapshot |
| `List.copyOf` nhưng entry mutable | Caller sửa entry qua reference | Immutable transactions hoặc DTO copies |
| Record chứa mutable list/array rồi coi là immutable sâu | Component reference vẫn trỏ mutable object | Defensive copy constructor/accessor |
| Transaction sai `balanceAfter` | Ledger không tái tạo được số dư | Tạo entry từ updatedBalance và replay check |
| Log giao dịch bị từ chối như giao dịch thành công | Ledger/saldo không khớp | Tách successful ledger khỏi audit attempts |
| Bỏ qua exception rồi báo thành công | Caller hiểu sai kết quả | Propagate/domain error theo contract |
| Cho rằng `private` đủ ngăn truy cập trái phép | Không có authorization/persistence controls | Thiết kế bảo mật tầng ứng dụng và DB |
| Hai thao tác `withdraw`/`deposit` là transfer atomic | Lỗi giữa chừng làm lệch accounts | Phối hợp transaction/locking theo architecture |
| Dùng chung Account nhiều threads mà không sync | Race, inconsistent state/history | Đồng bộ kiểm tra + cập nhật + snapshot |
| Tưởng `final history` làm list immutable | Final chỉ khóa field reference | Chặn lộ mutable list, dùng copy |

## 19. Quy trình thiết kế áp dụng cho bài toán tương tự

Khi xây dựng một class lưu **state chính** và **lịch sử thay đổi state**, làm tuần tự:

1. **Xác định state và đơn vị:** balance theo cents/minor unit; amount phải dùng cùng đơn vị.
2. **Định nghĩa invariants:** balance không âm; history tái tạo state; mỗi event hợp lệ.
3. **Giấu representation:** fields private; không để public setter trực tiếp cho state quan trọng.
4. **Chọn commands hợp lệ:** `deposit`, `withdraw` với tên/contract rõ.
5. **Validate trước:** amount, đủ số dư, overflow, trạng thái hiện tại.
6. **Tính trạng thái ứng viên:** tránh sửa object từng bước rồi phát hiện lỗi.
7. **Tạo immutable event:** từ dữ liệu giao dịch thực tế và state sau thành công.
8. **Commit có kiểm soát:** history và balance phải thay đổi như một thao tác logic; định nghĩa failure semantics.
9. **Chỉ trả read models:** snapshot/unmodifiable collections, không lộ mutable internals.
10. **Kiểm tra đối chiếu:** replay/check sequence/amount/balanceAfter.
11. **Định nghĩa concurrency contract:** không dùng chung giữa threads hoặc đồng bộ đầy đủ; snapshot cả trạng thái liên quan khi cần.
12. **Kiểm thử cả lỗi:** invalid amounts, insufficient funds, overflow, history mutation, concurrent requests nếu có.

Một lớp bảo vệ tốt giúp bên gọi **khó đưa dữ liệu vào trạng thái không nhất quán**, thay vì chỉ hướng dẫn người dùng “đừng sửa balance bằng tay”.

## 20. Câu hỏi tự kiểm tra có lời giải

**Câu 1.** Vì sao không thể đặt `public long balanceCents` và trông chờ caller chỉ gọi `withdraw`?  
**Đáp án:** Vì caller vẫn có thể trực tiếp gán giá trị âm hoặc giá trị không đi kèm event lịch sử.

**Câu 2.** Field `private final ArrayList<Transaction> history` đã đủ bảo vệ lịch sử nếu getter trả `history` chưa?  
**Đáp án:** Chưa. `final` chỉ không cho gán lại field reference; caller nhận cùng ArrayList vẫn có thể `clear` hoặc `add`.

**Câu 3.** Vì sao `deposit(-10)` phải bị từ chối trước khi tính và ghi?  
**Đáp án:** Số tiền nạp không được âm; nếu vẫn xử lý, balance và history có thể phản ánh thao tác sai nghiệp vụ.

**Câu 4.** Vì sao cần `Math.addExact` trong ví dụ dùng `long`?  
**Đáp án:** Để phát hiện overflow và không lưu một balance đã bị tràn số.

**Câu 5.** Khi rút 1000 từ balance 800, history có nên ghi `WITHDRAW 1000` trong ledger successful transactions không?  
**Đáp án:** Không. Thao tác bị từ chối, balance và successful history đều giữ nguyên. Audit attempts là mối quan tâm riêng.

**Câu 6.** Hai fields `balance` và `history` đều private nhưng method chỉ tăng balance mà quên ghi history thì invariant nào bị phá?  
**Đáp án:** Số dư không còn được giải thích đầy đủ bằng lịch sử successful events.

**Câu 7.** `List.copyOf(history)` là live view hay snapshot cấu trúc của mutable history?  
**Đáp án:** Snapshot cấu trúc; các thay đổi thêm/xóa sau đó của mutable history không xuất hiện trong list đã trả.

**Câu 8.** `Collections.unmodifiableList(history)` có thể phản ánh việc Account append thêm giao dịch sau đó không?  
**Đáp án:** Có thể, vì đó là unmodifiable **view** gắn với backing list, không nhất thiết là snapshot.

**Câu 9.** Vì sao record `Transaction(long amount, long balanceAfter)` không tự bảo đảm lịch sử thật?  
**Đáp án:** Record chỉ là kiểu dữ liệu; người dùng có thể tạo record bất kỳ nếu constructor truy cập được. Chỉ logic của Account kiểm soát event nào được append mới bảo đảm sự kiện thành công.

**Câu 10.** Vì sao dùng `List.copyOf` thôi chưa đủ nếu mỗi entry có setter `setAmount`?  
**Đáp án:** List không sửa được nhưng entry objects có thể vẫn mutable và shared. Cần immutable entries hoặc copy elements phù hợp.

**Câu 11.** Sau hai giao dịch tổng balance 750, caller lấy `snapshot = account.history()`; Account nạp thêm 50. Snapshot cũ có tự thành ba entries không?  
**Đáp án:** Không. Với `List.copyOf` nó giữ hai entries tại lúc được tạo.

**Câu 12.** Nếu caller nhận `history()` rồi gọi `clear()`, điều gì xảy ra trong ví dụ chính?  
**Đáp án:** List kết quả không cho sửa nên ném `UnsupportedOperationException`; lịch sử nội bộ vẫn nguyên.

**Câu 13.** Vì sao method cập nhật balance rồi mới cố tạo Transaction là rủi ro?  
**Đáp án:** Nếu bước tạo/gắn event thất bại, balance có thể đã thay đổi mà ledger không ghi nhận.

**Câu 14.** `balanceAfter` có lợi gì và cần kiểm tra gì?  
**Đáp án:** Giúp quan sát trạng thái sau giao dịch, nhưng phải đối chiếu với phép cộng/trừ các events theo thứ tự, tránh chứa dữ liệu dư thừa sai.

**Câu 15.** Hai transactions đều có sequence 1 nhưng thuộc hai accounts khác nhau có phải cùng một event không?  
**Đáp án:** Không. Sequence chỉ tăng trong một account của model; cần account identity hoặc global ID để phân biệt.

**Câu 16.** Khi chuyển tiền giữa hai accounts, gọi `source.withdraw` rồi `destination.deposit` có đủ bảo đảm atomicity không?  
**Đáp án:** Không. Nếu thao tác thứ hai thất bại, nguồn đã bị trừ. Cần cơ chế phối hợp/transaction phù hợp.

**Câu 17.** Vì sao `private` không tự ngăn double-spend khi hai threads cùng rút tiền?  
**Đáp án:** Nó chỉ chặn field access trực tiếp từ caller, không tự đồng bộ hóa phép kiểm tra và cập nhật giữa threads.

**Câu 18.** Nếu Account công bố `balance()` và `history()` đều synchronized nhưng caller gọi riêng rẽ, có luôn nhận hai giá trị của cùng một thời điểm không?  
**Đáp án:** Không. Thread khác có thể cập nhật giữa hai lời gọi. Cần snapshot chung dưới cùng lock nếu muốn một view nhất quán.

**Câu 19.** Với dữ liệu tiền tệ, vì sao `double` thường không được chọn để lưu tiền chính xác?  
**Đáp án:** Một số phân số thập phân không biểu diễn nhị phân chính xác; dùng kiểu money có currency/scale hoặc `BigDecimal` khi yêu cầu nghiệp vụ phù hợp.

**Câu 20.** Một phép replay lịch sử phát hiện `balanceAfter` không khớp giúp bảo đảm điều gì, và không bảo đảm điều gì?  
**Đáp án:** Giúp phát hiện inconsistency trong các events hiện có; không tự bảo đảm lịch sử không bị một tác nhân có quyền chỉnh sửa đồng thời nhiều trường làm giả mạo.

## Tài liệu tham khảo

- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): hạn chế quyền truy cập vào fields và methods.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): khai báo fields, `private` và `final`.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): cung cấp unmodifiable list với các elements hiện tại.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): read-only view của backing list.
- Java Platform API, [`Math.addExact(long,long)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): phát hiện overflow.
- Java Platform API, [`Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): mô hình các giá trị record, kết hợp validation và lựa chọn immutable components.

## Ghi nhớ

Trong một tài khoản có số dư và lịch sử giao dịch, **đóng gói thành công** nghĩa là caller chỉ yêu cầu `deposit`/`withdraw` và **Account tự chịu trách nhiệm** kiểm tra amount, tính balance mới, ghi event thành công, từ chối thao tác sai và duy trì khả năng đối chiếu.

Giấu `balance` và `history` bằng `private` chỉ là bước đầu. Cần ngăn caller sửa lịch sử qua getter, bảo vệ từng transaction entry khỏi mutable aliases, chống overflow và bảo đảm thao tác thất bại không làm thay đổi số dư/ledger. `List.copyOf` cùng immutable `record Transaction` là một giải pháp đơn giản cho **snapshot đọc**. Với đa luồng, persistence hoặc chuyển tiền giữa tài khoản, phải bổ sung synchronization/transaction, authorization, durability và audit controls; `private` không tự thay thế các cơ chế ấy.
