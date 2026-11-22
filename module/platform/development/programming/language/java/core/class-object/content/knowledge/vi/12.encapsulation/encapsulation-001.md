# Đóng gói để bảo vệ trạng thái và quy tắc hợp lệ trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **encapsulation (đóng gói)** như việc đặt dữ liệu và thao tác lên dữ liệu sau một giao diện có kiểm soát, thay vì chỉ “đổi mọi field thành `private`”.
- Phân biệt **trạng thái của đối tượng**, **quy tắc hợp lệ/bất biến đối tượng** (*invariant*) và những **điều kiện trước/sau** của một thao tác.
- Thiết kế constructor/factory bảo đảm đối tượng bắt đầu ở trạng thái hợp lệ và các public methods duy trì trạng thái hợp lệ sau khi hoàn thành.
- Dùng các phương thức mang ý nghĩa nghiệp vụ như `deposit`, `withdraw`, `pay` thay vì cho mã ngoài tùy ý sửa fields bằng setters không kiểm soát.
- Phân biệt validation tại ranh giới API với kiểm tra các quy tắc phối hợp giữa nhiều fields.
- Sử dụng **defensive copying**, immutable values, unmodifiable collections và API chỉ đọc để tránh lộ tham chiếu mutable.
- Xử lý thao tác thất bại bằng exception mà không để lại đối tượng ở trạng thái nửa cập nhật.
- Hiểu vai trò của `final`, `static`, visibility, inheritance, concurrent access và Java records; biết những gì chúng **không** tự bảo đảm.
- Chạy và kiểm thử các ví dụ Java 17+, bao gồm trường hợp hợp lệ, không hợp lệ và các yêu cầu trạng thái.

## 1. Đóng gói là gì?

Trong lập trình hướng đối tượng, một lớp thường chịu trách nhiệm về:

1. **Trạng thái (state):** dữ liệu mô tả object, thường lưu trong instance fields.
2. **Hành vi (behavior):** các operations cho phép đọc, tính toán hoặc thay đổi trạng thái.
3. **Quy tắc hợp lệ (invariants):** những điều kiện trạng thái phải thỏa tại các thời điểm được hợp đồng lớp quy định, đặc biệt sau khi constructor hoặc public operation hoàn tất bình thường.

**Đóng gói** đưa dữ liệu và các thao tác liên quan về cùng một abstraction, đồng thời **hạn chế việc sửa dữ liệu không qua kiểm soát**. Code bên ngoài giao tiếp qua một API có ý nghĩa và chịu các kiểm tra do lớp định nghĩa.

Ví dụ số dư tài khoản phải không âm:

~~~java
class Account {
    public long balance;
}
~~~

Nếu `balance` là public và thay đổi được, caller có thể viết:

~~~java
Account account = new Account();
account.balance = -500;
~~~

Các đoạn này là **minh họa**, biên dịch được khi đặt đúng cấu trúc class/method, nhưng cho thấy một lỗi thiết kế: không có rào chắn ở ranh giới API để ngăn số dư âm.

Một thiết kế tốt hơn:

~~~java
class Account {
    private long balance;

    Account(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.balance = openingBalance;
    }

    long balance() {
        return balance;
    }

    void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance = Math.addExact(balance, amount);
    }

    void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("invalid withdrawal");
        }
        balance -= amount;
    }
}
~~~

Ở đây:

- Field `balance` được khai báo `private` nên caller ngoài quyền không tự viết `account.balance = -500`.
- Constructor kiểm tra trạng thái ban đầu.
- `deposit` yêu cầu khoản nạp dương và dùng `Math.addExact` để tránh tràn số âm thầm.
- `withdraw` yêu cầu số tiền dương và không vượt số dư.
- `balance()` cho phép đọc nhưng không cung cấp đường ghi tùy tiện.

**Điểm cốt lõi:** `private` chỉ là **cơ chế hạn chế truy cập**; đóng gói có hiệu lực thực tế khi các đường tạo/sửa object đều **giữ đúng hợp đồng của lớp**.

## 2. Phân biệt trạng thái, invariant và điều kiện của thao tác

Với `BankAccount`:

- **State:** `owner`, `balance`.
- **Invariant:** `owner` có ý nghĩa hợp lệ; `balance >= 0`.
- **Precondition** của `withdraw(amount)`: `amount > 0` và `amount <= balance`.
- **Postcondition** khi `withdraw` thành công: `balanceAfter == balanceBefore - amount`, chủ sở hữu không đổi, invariant vẫn đúng.
- **Behavior on failure:** ném exception phù hợp và **không để lại thay đổi nửa chừng** đối với state mà method quản lý.

Một invariant thường liên quan **nhiều fields**, không thể bảo vệ chỉ bằng cách validate riêng từng setter. Ví dụ khoảng ngày phải thỏa `start <= end`; nếu có hai setters độc lập `setStart` và `setEnd` thì có thể xuất hiện trạng thái trung gian trái quy tắc, hoặc một setter không thể được gọi theo thứ tự hợp lý.

Cần phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Field | `long balance` | Nơi lưu dữ liệu |
| Access modifier | `private` | Giới hạn nơi truy cập trực tiếp |
| Invariant | `balance >= 0` | Thuộc tính trạng thái mà class cam kết |
| Precondition | `amount > 0` | Điều kiện của một lời gọi |
| Postcondition | `balance mới = balance cũ + amount` | Kết quả của thao tác thành công |
| Validation | `if (amount <= 0) throw ...` | Kiểm tra input/điều kiện |
| Encapsulation | Chỉ công bố `deposit`/`withdraw` | Quyền kiểm soát thao tác được tập trung trong abstraction |
| Immutability | Không cho đổi state sau khi tạo | Một lựa chọn thiết kế mạnh hơn; không đồng nghĩa đóng gói |

Một class có private fields nhưng setters tự do vẫn có thể vi phạm invariants. Một immutable class không có thao tác thay đổi trạng thái sau khi tạo lại càng dễ suy luận về invariant, nhưng constructor vẫn cần validate input.

## 3. Ví dụ hoàn chỉnh: tài khoản giữ số dư hợp lệ

Lưu file **`EncapsulatedAccountDemo.java`**:

~~~java
public class EncapsulatedAccountDemo {
    static final class BankAccount {
        private final String owner;
        private long balance;

        BankAccount(String owner, long openingBalance) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner is required");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening balance");
            }
            this.owner = owner;
            this.balance = openingBalance;
        }

        String owner() {
            return owner;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit must be positive");
            }
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            balance -= amount;
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount("Lan", 100);

        System.out.println(account.owner() + ":" + account.balance());
        account.deposit(50);
        account.withdraw(30);
        System.out.println("after operations=" + account.balance());

        try {
            account.withdraw(500);
        } catch (IllegalArgumentException expected) {
            System.out.println("withdraw rejected");
        }

        System.out.println("balance remains=" + account.balance());

        try {
            account.deposit(0);
        } catch (IllegalArgumentException expected) {
            System.out.println("zero deposit rejected");
        }

        System.out.println("valid balance=" + (account.balance() >= 0));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 EncapsulatedAccountDemo.java
java EncapsulatedAccountDemo
~~~

**Stdout chính xác:**

~~~text
Lan:100
after operations=120
withdraw rejected
balance remains=120
zero deposit rejected
valid balance=true
~~~

**Phân tích:**

1. Constructor nhận `owner="Lan"`, `openingBalance=100` và kiểm tra trước khi gán.
2. `deposit(50)` tăng số dư từ 100 thành 150.
3. `withdraw(30)` giảm xuống 120 vì 30 dương và không vượt 150.
4. `withdraw(500)` bị từ chối **trước phép trừ**, nên số dư vẫn 120.
5. `deposit(0)` bị từ chối theo precondition; số dư vẫn không đổi.
6. Invariant `balance >= 0` tiếp tục đúng qua tất cả các lời gọi đã chạy.

Trong ví dụ, `long` biểu diễn một số lượng nguyên không âm, không phải hệ thống tiền tệ hoàn chỉnh. Một ứng dụng ngân hàng thật cần cân nhắc đơn vị tiền, số lẻ, concurrency, durability, transactions, authorization và audit logs; đóng gói ở cấp một object chỉ là một phần.

### 3.1. Vì sao không có `setBalance(long)`?

Nếu class công bố:

~~~java
public void setBalance(long balance) {
    this.balance = balance;
}
~~~

mã bên ngoài có thể bỏ qua `deposit`/`withdraw`, tự thay đổi số dư không kèm lý do hoặc vi phạm nghiệp vụ. Thêm `if (balance < 0)` chỉ ngăn số âm, **không** đủ để bảo đảm mọi thay đổi số dư đại diện cho giao dịch hợp lệ.

Với state có ý nghĩa nghiệp vụ, ưu tiên **command methods**:

- `deposit(amount)`: khoản nạp.
- `withdraw(amount)`: khoản rút.
- `close()`: đóng tài khoản khi thỏa điều kiện.
- `applyInterest(rate)`: áp dụng nghiệp vụ lãi suất được định nghĩa rõ.

Một setter đơn giản vẫn có thể phù hợp với dữ liệu cấu hình không có invariant phức tạp. Mục tiêu không phải “cấm tất cả setter”, mà là **không tạo đường đi phá vỡ quy tắc của đối tượng**.

### 3.2. Tràn số cũng phá invariant

Nếu code viết `balance += amount` và `balance` gần `Long.MAX_VALUE`, phép cộng có thể overflow và tạo số âm. Khi class tuyên bố `balance >= 0`, nó phải cân nhắc cả arithmetic overflow, không chỉ kiểm tra `amount > 0`.

`Math.addExact(balance, amount)` ném `ArithmeticException` nếu phép cộng kiểu `long` tràn. Ở chương trình trên, kết quả chỉ gán vào field **sau khi biểu thức bên phải thành công**, nên field không bị cập nhật khi phép cộng ném exception.

## 4. Constructor là ranh giới đầu tiên bảo vệ invariant

Nếu constructor có thể tạo object ở trạng thái sai, mọi method phía sau phải phòng vệ trước nhiều trường hợp bất thường.

Ví dụ không nên:

~~~java
class UserProfile {
    private String username;

    UserProfile() {
        // username mặc định null; object có thể chưa dùng được.
    }

    void setUsername(String username) {
        this.username = username;
    }
}
~~~

Nếu nghiệp vụ bắt buộc username không null/blank, caller có thể quên gọi setter hoặc truyền `null`. Đây là một **mô hình có khả năng tạo object chưa hợp lệ**.

Thiết kế khác:

~~~java
class UserProfile {
    private final String username;

    UserProfile(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("invalid username");
        }
        this.username = username;
    }

    String username() {
        return username;
    }
}
~~~

Constructor đòi dữ liệu cần thiết; khi hoàn tất bình thường, `username` luôn hợp lệ trong model đơn giản này.

**Một lưu ý quan trọng:** constructor có thể ném exception trước khi kết thúc. Caller không nhận reference từ biểu thức `new` trên đường đó; tuy nhiên side effects mà constructor đã thực hiện trên các objects khác, static fields, logs... không tự động rollback.

### 4.1. Không bắt buộc dùng constructor public

Static factory có tên cũng có thể làm đường vào được kiểm soát:

~~~java
public final class Percentage {
    private final int value;

    private Percentage(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("percentage out of range");
        }
        this.value = value;
    }

    public static Percentage of(int value) {
        return new Percentage(value);
    }

    public int value() {
        return value;
    }
}
~~~

Đây là file `Percentage.java` hợp lệ. Caller dùng `Percentage.of(70)` thay vì `new Percentage(70)`. Nhưng **factory method không tự động validate**: validation có hiệu lực vì implementation thực sự gọi constructor kiểm tra dữ liệu.

### 4.2. Xác nhận mọi constructor overload

Nếu một lớp có nhiều constructors, cần bảo đảm **mọi đường tạo** cùng giữ invariant. Một cách là dùng constructor chaining:

~~~java
class TimerSettings {
    private final int timeoutSeconds;

    TimerSettings() {
        this(30);
    }

    TimerSettings(int timeoutSeconds) {
        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.timeoutSeconds = timeoutSeconds;
    }
}
~~~

`TimerSettings()` ủy quyền cho `TimerSettings(30)` để tận dụng validation chung. Mã hợp lệ trong một tệp class thích hợp. Nếu một overload bỏ kiểm tra cần thiết, toàn bộ invariant của lớp vẫn có thể bị phá ở đường tạo đó.

## 5. Trạng thái phụ thuộc lẫn nhau: đừng kiểm tra từng field riêng lẻ

Ví dụ một khoảng ngày gồm `start` và `end` phải luôn thỏa `start <= end`.

Nếu cho phép sửa từng field tự do, caller có thể lần lượt tạo trạng thái trung gian không hợp lệ. Dùng một operation có ý nghĩa trên **cả cặp** dễ duy trì invariant hơn.

Lưu **`DateRangeEncapsulationDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class DateRangeEncapsulationDemo {
    static final class DateRange {
        private LocalDate start;
        private LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            changeRange(start, end);
        }

        void changeRange(LocalDate newStart, LocalDate newEnd) {
            Objects.requireNonNull(newStart, "start");
            Objects.requireNonNull(newEnd, "end");
            if (newStart.isAfter(newEnd)) {
                throw new IllegalArgumentException("start after end");
            }

            // Chỉ commit sau khi mọi validation đã hoàn tất.
            this.start = newStart;
            this.end = newEnd;
        }

        String describe() {
            return start + " -> " + end;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 1, 1),
                LocalDate.of(2026, 1, 31));

        System.out.println("initial=" + range.describe());

        try {
            range.changeRange(
                    LocalDate.of(2026, 2, 10),
                    LocalDate.of(2026, 2, 1));
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid range rejected");
        }

        System.out.println("unchanged=" + range.describe());

        range.changeRange(
                LocalDate.of(2026, 2, 1),
                LocalDate.of(2026, 2, 28));

        System.out.println("updated=" + range.describe());
    }
}
~~~

Chạy:

~~~bash
javac DateRangeEncapsulationDemo.java
java DateRangeEncapsulationDemo
~~~

Output:

~~~text
initial=2026-01-01 -> 2026-01-31
invalid range rejected
unchanged=2026-01-01 -> 2026-01-31
updated=2026-02-01 -> 2026-02-28
~~~

**Vì sao cách này bảo vệ trạng thái?**

- Constructor gọi cùng `changeRange` để kiểm tra cặp dates trước khi object hoàn tất khởi tạo.
- `Objects.requireNonNull` ngăn một ngày bị null.
- `newStart.isAfter(newEnd)` kiểm tra quan hệ giữa hai fields.
- Mọi điều kiện đều được kiểm tra trước khi gán `this.start` và `this.end`. Khi một điều kiện thất bại, hai fields vẫn giữ giá trị cũ.
- `LocalDate` là immutable, nên trả/giữ reference đến nó không cho caller thay đổi nội dung ngày từ bên ngoài.

**Giới hạn quan trọng:** các bước kiểm tra và hai phép gán **không tự là một giao dịch atomic giữa nhiều threads**. Ví dụ bảo đảm tính nhất quán sau public operation trong cách dùng một luồng hoặc có đồng bộ hóa phù hợp; phần concurrency cần giải pháp riêng.

### 5.1. Vì sao `setStart` và `setEnd` đôi khi là API dở?

Giả sử khoảng hiện tại `[2026-01-01, 2026-01-31]` và caller muốn đổi thành `[2026-02-01, 2026-02-28]`:

- Gọi `setStart(2026-02-01)` trước sẽ tạm thời khiến start > end.
- Gọi `setEnd(2026-02-28)` trước có thể vẫn hợp lệ trong ví dụ này, nhưng caller bị ép phải hiểu và nhớ **thứ tự thao tác**.
- Nếu setter không kiểm tra, trạng thái sai có thể tồn tại.
- Nếu setter kiểm tra riêng nhưng không cho phép bất kỳ bước trung gian nào, có những chuyển đổi hợp lệ cuối cùng lại không thực hiện thuận tiện qua API.

`changeRange(newStart,newEnd)` biểu thị rõ **một thao tác logic nguyên khối**. Khi thật sự cần sửa riêng một endpoint, method vẫn có thể kiểm tra dựa trên endpoint còn lại để không phá invariant, nhưng contract nên nói rõ.

## 6. Trạng thái dạng workflow: công bố hành vi, không mở field `status`

Một object thường chỉ được phép thay đổi qua **những chuyển trạng thái đã định nghĩa**.

Ví dụ đơn hàng:

~~~text
CREATED --pay()--> PAID --ship()--> SHIPPED
~~~

Một setter `setStatus(Status)` công khai có thể cho phép code ngoài nhảy trực tiếp từ `CREATED` sang `SHIPPED`, làm mất invariant “đã giao hàng thì trước đó đã thanh toán”.

Lưu **`OrderStateDemo.java`**:

~~~java
public class OrderStateDemo {
    enum Status {
        CREATED, PAID, SHIPPED
    }

    static final class Order {
        private final String id;
        private Status status = Status.CREATED;

        Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
        }

        Status status() {
            return status;
        }

        void pay() {
            if (status != Status.CREATED) {
                throw new IllegalStateException("only created orders can be paid");
            }
            status = Status.PAID;
        }

        void ship() {
            if (status != Status.PAID) {
                throw new IllegalStateException("only paid orders can be shipped");
            }
            status = Status.SHIPPED;
        }

        String summary() {
            return id + ":" + status;
        }
    }

    public static void main(String[] args) {
        Order order = new Order("O-1");
        System.out.println("initial=" + order.summary());

        try {
            order.ship();
        } catch (IllegalStateException expected) {
            System.out.println("ship before payment rejected");
        }

        System.out.println("after rejection=" + order.status());

        order.pay();
        System.out.println("after pay=" + order.summary());
        order.ship();
        System.out.println("after ship=" + order.summary());

        try {
            order.pay();
        } catch (IllegalStateException expected) {
            System.out.println("pay again rejected");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OrderStateDemo.java
java OrderStateDemo
~~~

Output:

~~~text
initial=O-1:CREATED
ship before payment rejected
after rejection=CREATED
after pay=O-1:PAID
after ship=O-1:SHIPPED
pay again rejected
~~~

**Phân tích:**

1. Field `status` là private và khởi tạo `CREATED`.
2. `ship()` kiểm tra trạng thái hiện tại; khi còn `CREATED`, method ném exception **trước khi gán**.
3. `pay()` chỉ cho phép từ `CREATED` sang `PAID`.
4. `ship()` chỉ cho phép từ `PAID` sang `SHIPPED`.
5. Sau `SHIPPED`, gọi lại `pay()` không hợp lệ.
6. Caller có thể đọc `status()` nhưng không trực tiếp thay `status`, vì lớp không mở setter cho trạng thái.

**Điểm thiết kế:** chỉ có enum không tự bảo vệ workflow. Invariant được duy trì bởi **các điều kiện chuyển trạng thái nằm trong methods** và việc chặn sửa field từ bên ngoài.

Ứng dụng thật còn cần kiểm tra thanh toán từ dịch vụ ngoài, transaction, retry và idempotency; object-level state machine là mô hình minh họa quy tắc chuyển trạng thái, không thay thế toàn bộ hệ thống đơn hàng.

## 7. Validation giá trị và validation nghiệp vụ

Các dạng kiểm tra khác nhau:

| Kiểu kiểm tra | Ví dụ | Vị trí thường phù hợp |
| --- | --- | --- |
| Không null | `Objects.requireNonNull(name)` | Constructor, factory, command |
| Không rỗng/blank | `name.isBlank()` | Khi tên bắt buộc |
| Miền giá trị | `quantity > 0`, `0 <= score <= 100` | Ranh giới API tạo/sửa |
| Quan hệ nhiều fields | `start <= end` | Method cập nhật đồng thời/constructor |
| Trạng thái hiện hành | `status == CREATED` trước `pay` | State transition method |
| Chống overflow | `Math.addExact` | Phép toán số nguyên có giới hạn |
| Hợp đồng đặc biệt | `Double.isFinite(x)` trước khi chấp nhận measurement | Type/command dùng floating-point |
| Quyền nghiệp vụ | User có quyền thực hiện operation | Application/service layer, domain rules phù hợp |

Không phải mọi validation đều là công việc của một setter. Nhiều điều kiện phụ thuộc **toàn bộ model**, một hệ thống khác, hoặc thời điểm. Hãy đặt kiểm tra vào tầng chịu trách nhiệm, tránh lặp tùy tiện gây bất đồng giữa các con đường cập nhật.

### 7.1. Kiểm tra NaN và Infinity

Nếu một lớp dùng `double` để lưu nhiệt độ hoặc tỷ lệ, câu `if (value < min || value > max)` **không bác bỏ NaN**, vì các phép so sánh thứ tự với NaN đều `false`.

Lưu **`ValidatedTemperatureDemo.java`**:

~~~java
public class ValidatedTemperatureDemo {
    static final class Temperature {
        private final double celsius;

        Temperature(double celsius) {
            if (!Double.isFinite(celsius) || celsius < -273.15) {
                throw new IllegalArgumentException("invalid temperature");
            }
            this.celsius = celsius;
        }

        double celsius() {
            return celsius;
        }
    }

    public static void main(String[] args) {
        Temperature room = new Temperature(25.0);
        System.out.println("room=" + room.celsius());

        try {
            new Temperature(Double.NaN);
        } catch (IllegalArgumentException expected) {
            System.out.println("NaN rejected");
        }

        try {
            new Temperature(-300.0);
        } catch (IllegalArgumentException expected) {
            System.out.println("below absolute zero rejected");
        }

        try {
            new Temperature(Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException expected) {
            System.out.println("infinity rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac ValidatedTemperatureDemo.java
java ValidatedTemperatureDemo
~~~

Output:

~~~text
room=25.0
NaN rejected
below absolute zero rejected
infinity rejected
~~~

Đây là model đơn giản với nhiệt độ theo độ C. Nó thể hiện **kiểm tra đầy đủ miền giá trị floating-point**, không phải mô hình vật lý/đo lường toàn diện. Nếu cần đơn vị, độ chính xác, rounding hoặc uncertainty, API phải mô tả chúng.

## 8. `private` field vẫn có thể bị sửa gián tiếp qua tham chiếu

Một sai lầm quan trọng là nghĩ “field đã private và final, vậy external code không thể thay đổi trạng thái”.

Ví dụ:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> input) {
        this.members = input;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

Đoạn này biên dịch được nhưng **không bảo vệ danh sách**:

1. Constructor giữ nguyên reference đến list mutable của caller; sau khi tạo Team, caller còn biến `input` có thể `input.add("X")`.
2. Getter trả reference đến **chính list nội bộ**, nên mã nhận getter có thể gọi `team.members().clear()`.
3. `private` ngăn truy cập field qua tên ở lớp khác; `final` ngăn gán lại **field reference** sau khi khởi tạo, nhưng **không** làm list immutable.

Đây là hiện tượng **representation exposure**: trạng thái nội bộ bị lộ qua reference mutable.

## 9. Defensive copying: bảo vệ collection nội bộ

Một cách thiết kế phù hợp cho collection chứa các **immutable elements** như `String` là tạo/cung cấp danh sách không sửa được có nội dung tại thời điểm khởi tạo.

Lưu **`DefensiveTeamDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveTeamDemo {
    static final class Team {
        private final String name;
        private final List<String> members;

        Team(String name, List<String> input) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            this.name = name;
            this.members = List.copyOf(input);
        }

        String name() {
            return name;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> external = new ArrayList<>(List.of("Lan"));
        Team team = new Team("Core", external);

        external.add("Minh");

        System.out.println("external=" + external);
        System.out.println("team=" + team.name() + ":" + team.members());

        try {
            team.members().add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("getter cannot add");
        }

        System.out.println("team remains=" + team.members());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DefensiveTeamDemo.java
java DefensiveTeamDemo
~~~

Output:

~~~text
external=[Lan, Minh]
team=Core:[Lan]
getter cannot add
team remains=[Lan]
~~~

**Vì sao?**

- `List.copyOf(input)` tạo/cung cấp một danh sách **không sửa được**, giữ các phần tử tại thời điểm tạo.
- Thêm `"Minh"` vào `external` sau đó không khiến `team.members()` thêm người.
- Caller nhận `team.members()` cũng không `add` được; collection API ném `UnsupportedOperationException`.
- Vì các phần tử là `String` immutable nên việc giữ reference tới String elements không làm “tên thành viên” bị sửa tại chỗ.

**Chi tiết cần biết:** `List.copyOf` **không chấp nhận phần tử null**, và có thể tái sử dụng một list đầu vào đã là unmodifiable list phù hợp; **đừng giả định lúc nào nó cũng tạo object list mới theo identity**. Điều cần dựa vào là **hợp đồng về dữ liệu và khả năng sửa**, không phải so sánh `==`.

### 9.1. Unmodifiable view khác snapshot độc lập

~~~java
List<String> view = java.util.Collections.unmodifiableList(external);
~~~

Một `unmodifiableList(external)` là **view không cho sửa qua view**, nhưng nếu code khác vẫn sửa `external`, view có thể **phản ánh thay đổi** đó. Nó không tự bảo vệ trạng thái khỏi nguồn tham chiếu mutable đã tồn tại.

Với `List.copyOf(external)`, cấu trúc phần tử thu được không thay đổi theo các phép thêm/xóa/sửa slot của `external` sau khi gọi. Nhưng nếu **element objects mutable**, cả hai vẫn có thể chia sẻ chính elements ấy.

**Không đồng nhất “read-only interface”, “unmodifiable collection”, “snapshot” và “deep immutability”.** Chúng bảo đảm các điều khác nhau.

## 10. Defensive copying cho mảng

Mảng là object mutable trong Java. Nếu getter trả thẳng mảng nội bộ, caller có thể sửa phần tử và phá quy tắc dù field chứa nó được `private final`.

Lưu **`EncapsulatedScoresDemo.java`**:

~~~java
import java.util.Arrays;

public class EncapsulatedScoresDemo {
    static final class Scores {
        private final int[] values;

        Scores(int[] input) {
            if (input == null || input.length == 0) {
                throw new IllegalArgumentException("scores required");
            }
            for (int score : input) {
                if (score < 0 || score > 100) {
                    throw new IllegalArgumentException("score out of range");
                }
            }
            this.values = input.clone();
        }

        int[] values() {
            return values.clone();
        }

        int highest() {
            return Arrays.stream(values).max().orElseThrow();
        }
    }

    public static void main(String[] args) {
        int[] external = {60, 90};
        Scores scores = new Scores(external);

        external[0] = -100;
        System.out.println("after input changed=" +
                Arrays.toString(scores.values()));

        int[] received = scores.values();
        received[1] = 500;
        System.out.println("after getter changed=" +
                Arrays.toString(scores.values()));

        System.out.println("highest=" + scores.highest());

        try {
            new Scores(new int[] {10, 120});
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid input rejected");
        }
    }
}
~~~

Lệnh:

~~~bash
javac EncapsulatedScoresDemo.java
java EncapsulatedScoresDemo
~~~

Output:

~~~text
after input changed=[60, 90]
after getter changed=[60, 90]
highest=90
invalid input rejected
~~~

Ở đây constructor **kiểm tra mọi phần tử trước**, sau đó `clone()` mảng `int[]`; getter `values()` cũng `clone()`. Caller không thể sửa mảng nội bộ bằng việc giữ input array hoặc sửa output array.

Đối với `int[]` một chiều, các phần tử primitive values được copy riêng. Nếu là `Student[]` và `Student` mutable, `clone()` chỉ copy **tham chiếu tới các Student objects**; muốn tránh thay đổi gián tiếp phải bảo vệ element objects hoặc dùng immutable representation phù hợp.

### 10.1. Vì sao validate trước copy có thể cần xem thêm concurrency?

Ví dụ trên kiểm tra `input` rồi mới `clone()`. Nếu một thread khác sửa **cùng input array** đồng thời trong khoảng giữa hai bước, bản clone có thể chứa dữ liệu chưa được kiểm tra.

Một thiết kế vững hơn khi **caller có thể chia sẻ/mutate đầu vào đồng thời** cần xác định contract sở hữu và phối hợp synchronization phù hợp; có thể **copy trước, validate trên bản copy rồi lưu chính bản copy**:

~~~java
int[] candidate = input.clone();
for (int score : candidate) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("invalid score");
    }
}
this.values = candidate;
~~~

Đoạn minh họa này giảm khe hở “validate một array rồi lưu một snapshot khác”, nhưng **không tự cung cấp snapshot nguyên tử** nếu bên khác ghi mảng đồng thời trong khi clone; vẫn phải bảo đảm caller không sửa đồng thời hoặc áp dụng đồng bộ phù hợp. Điểm quan trọng là **kiểm tra đúng dữ liệu bạn thực sự định lưu**, chứ không chỉ kiểm tra nguồn rồi tin nó bất biến.

## 11. Lớp có mutable nested objects: chỉ copy collection là chưa đủ

Nếu một class giữ `List<Address>` và `Address` có `setCity(...)`, `List.copyOf` sẽ làm cấu trúc list không sửa được, nhưng **không clone Address elements**. Caller có thể giữ `Address` cũ rồi sửa city; object nội bộ Team/Customer có thể quan sát thay đổi gián tiếp.

### 11.1. Thiết kế với immutable value object

Lưu **`ImmutableAddressBookDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableAddressBookDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("blank city");
            }
        }
    }

    static final class AddressBook {
        private final List<Address> addresses;

        AddressBook(List<Address> source) {
            this.addresses = List.copyOf(source);
        }

        List<Address> addresses() {
            return addresses;
        }
    }

    public static void main(String[] args) {
        List<Address> external =
                new ArrayList<>(List.of(new Address("Ha Noi")));

        AddressBook book = new AddressBook(external);
        external.set(0, new Address("Hue"));

        System.out.println("external=" + external.get(0).city());
        System.out.println("book=" + book.addresses().get(0).city());

        try {
            new Address("");
        } catch (IllegalArgumentException expected) {
            System.out.println("blank address rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac ImmutableAddressBookDemo.java
java ImmutableAddressBookDemo
~~~

Output:

~~~text
external=Hue
book=Ha Noi
blank address rejected
~~~

**Phân tích:**

- `Address` là Java record có một component `String city`, mà String immutable.
- Compact constructor `Address { ... }` validate trước khi record initialization hoàn tất.
- Không có setter hay mutable component ở `Address`, nên Address objects có nội dung bất biến theo design đơn giản này.
- `List.copyOf` bảo vệ cấu trúc danh sách trước sửa đổi sau đó của `external`.
- Kết hợp **immutable elements + unmodifiable list snapshot** giúp API dễ bảo vệ state hơn.

**Record không tự tạo deep immutability.** Nếu record chứa `List<String>` hoặc `int[]`, reference tới object mutable có thể bị chia sẻ; cần defensive copies trong constructor/accessors thích hợp. Record là một công cụ mô hình hóa dữ liệu, không tự bảo đảm mọi invariant.

## 12. `final` bảo vệ điều gì và không bảo vệ điều gì?

Bảng:

| Khai báo | Bảo đảm ở cấp Java | Không tự bảo đảm |
| --- | --- | --- |
| `private int count` | Caller ngoài quyền không truy cập trực tiếp theo API | Các public methods không làm count âm |
| `private final int id` | Field chỉ được gán theo quy tắc khởi tạo final, không gán lại tùy ý | ID có hợp lệ về nghiệp vụ không |
| `private final List<String> members` | Không được gán lại **field reference** sau khởi tạo hợp lệ | List object có mutable không |
| `public final class Config` | Không thể tạo subclass của class này | Instance Config tự động bất biến |
| `static final List<?> CACHED` | Field reference được chia sẻ và không gán lại sau khởi tạo | Nội dung list có thread-safe/immutable không |

`final` hữu ích để diễn đạt phần state không được thay thế và giảm đường cập nhật, nhưng class vẫn cần validation, visibility hợp lý và ownership của mutable subobjects.

### 12.1. Immutable object có thể đơn giản hóa invariant

Nếu trạng thái không cần đổi, hãy cân nhắc **immutable class**:

~~~java
final class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height;
    }
}
~~~

Đây là class hợp lệ. `width`, `height` đều private final primitives; sau khi tạo không có đường sửa chúng. Constructor bảo đảm mỗi kích thước dương, nên mọi lần gọi `area()` có thể dựa trên invariant đó.

Phép nhân ép sang `long` trước khi nhân để tránh overflow kiểu `int` với kích thước lớn hợp lệ. Nếu cần bảo đảm không overflow cả `long`, phải đặt thêm giới hạn hoặc dùng phép toán kiểm tra khác.

## 13. Không để object thay đổi nửa chừng khi thao tác thất bại

Một public method có thể phải cập nhật **nhiều fields**. Nếu nó gán một field rồi mới validate field khác, khi ném exception, object có thể ở trạng thái không nhất quán.

**Thiết kế dễ lỗi:**

~~~java
class Rectangle {
    private int width = 2;
    private int height = 3;

    void resizeBad(int newWidth, int newHeight) {
        width = newWidth;
        if (newWidth <= 0 || newHeight <= 0) {
            throw new IllegalArgumentException("invalid dimensions");
        }
        height = newHeight;
    }
}
~~~

Với `resizeBad(-5,3)`, `width` đã trở thành -5 **trước** khi method ném exception. Nếu invariant `width > 0`, đối tượng bị để lại ở trạng thái sai.

**Sửa:** validate mọi input trước khi sửa state:

~~~java
class Rectangle {
    private int width = 2;
    private int height = 3;

    void resize(int newWidth, int newHeight) {
        if (newWidth <= 0 || newHeight <= 0) {
            throw new IllegalArgumentException("invalid dimensions");
        }
        width = newWidth;
        height = newHeight;
    }
}
~~~

Đây là **hai phương án thay thế** của class `Rectangle`, không được đồng thời khai báo hai class cùng tên trong một package. Ở phiên bản thứ hai, validation thất bại trước khi gán field, nên trạng thái cũ được giữ lại.

Đối với các thao tác phức tạp hơn (gọi dịch vụ bên ngoài, ghi file/DB, nhiều side effects), “validate trước rồi gán” có thể **chưa đủ** để có transaction/rollback thực sự. Nhưng đây là nguyên tắc nền tảng ở cấp object: **tính toán và kiểm tra một trạng thái ứng viên, chỉ commit khi hợp lệ**.

### 13.1. Exception cho input và state

- `IllegalArgumentException` thường phù hợp khi **giá trị đối số** không thỏa điều kiện phương thức.
- `NullPointerException` do `Objects.requireNonNull` có thể dùng rõ hợp đồng non-null.
- `IllegalStateException` phù hợp khi **trạng thái hiện hành** của object không cho phép thao tác (`ship` trước `pay`).
- `ArithmeticException` từ `Math.addExact` thông báo overflow; có thể chuyển thành ngoại lệ domain rõ hơn nếu API đã xác định contract.

Đừng bắt mọi exception rồi bỏ qua: caller sẽ tưởng thao tác đã thành công dù thực tế không thay đổi. Hãy mô tả rõ **đường thành công** và **đường thất bại**.

## 14. Cập nhật bất biến và tương tranh: encapsulation chưa bảo đảm thread safety

Bảo vệ field bằng `private` không tự làm các thao tác cập nhật an toàn khi **nhiều threads** cùng chia sẻ object.

Ví dụ một counter:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
~~~

Dù field private và caller chỉ đi qua methods, `value++` không là một thao tác atomic theo Java Memory Model. Nếu nhiều threads đồng thời gọi `increment`, có thể xảy ra race và mất increments.

Một cách đơn giản khi cần bảo vệ một object counter khỏi concurrent updates là dùng synchronization phù hợp:

~~~java
class Counter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int value() {
        return value;
    }
}
~~~

Đây là **một phương án thay thế** của class `Counter`. Cả read/write trong ví dụ đều dùng cùng intrinsic monitor của instance. Tùy bài toán có thể chọn `AtomicInteger`, locks hoặc immutable state được thay nguyên khối.

Với object có nhiều fields và invariants phối hợp, cần bảo đảm **toàn bộ thao tác kiểm tra + cập nhật** được đồng bộ hóa như một đơn vị khi chia sẻ đa luồng; chỉ synchronized riêng getter hoặc chỉ final references có thể không đủ.

**Đừng hiểu “đóng gói” là “tự động thread-safe” hoặc “tự bảo vệ trước reflection, serialization hay mã chạy với đặc quyền khác”.** Nó là ranh giới thiết kế/API ở cấp ngôn ngữ, không phải giải pháp an ninh hay concurrency toàn diện.

## 15. Khi nào nên cung cấp getter, setter và command method?

Không cần biến mọi field thành `getX()/setX()` một cách máy móc.

**Getter** phù hợp nếu caller thực sự cần biết một phần state. Nhưng hãy cân nhắc:

- Trả giá trị primitive hoặc immutable object thường ít rủi ro.
- Trả reference đến mutable collection/array nội bộ có thể phá encapsulation.
- Một getter tổng hợp như `availableBalance()` đôi khi phù hợp hơn việc lộ nhiều fields riêng lẻ.
- Getter có thể tính kết quả từ state, không nhất thiết trả thẳng field.

**Setter** phù hợp khi việc gán một giá trị **độc lập và an toàn**, ví dụ thay một ghi chú tùy chọn theo hợp đồng. Nhưng:

- Với số dư, dùng `deposit`/`withdraw` thay vì `setBalance`.
- Với khoảng ngày, dùng `changeRange(start,end)` để validate quan hệ hai fields.
- Với workflow, dùng `pay`/`ship` thay vì `setStatus` tùy ý.

**Command method** mô tả hành động hợp lệ: caller yêu cầu điều gì, class tự chịu trách nhiệm làm thế nào, kiểm tra những gì và giữ invariant nào.

### 15.1. Thiết kế API theo hành vi chứ không phải cấu trúc lưu trữ

Ví dụ thay vì công bố:

~~~java
public int quantity;
public boolean reserved;
~~~

một object kho hàng có thể công bố `reserve(int amount)`, `release(int amount)`, `availableQuantity()` và kiểm tra `0 <= reservedQuantity <= stockQuantity` theo hợp đồng.

Khi class nội bộ đổi từ `int` fields sang một value object hoặc cấu trúc khác, API nghiệp vụ có thể vẫn giữ nguyên. Đây là lợi ích bảo trì quan trọng của encapsulation: **caller phụ thuộc vào hành vi, không phụ thuộc vào layout các fields**.

## 16. Kế thừa và nguy cơ phá invariant từ subclass

Một class có `protected` fields cho subclass sửa trực tiếp thì subclass có thể bỏ qua validation của superclass.

Ví dụ dễ rủi ro:

~~~java
class BaseAccount {
    protected long balance;
}
~~~

Subclass ở ngữ cảnh truy cập hợp lệ có thể ghi `balance = -100`, phá invariant mà superclass dự định duy trì.

Một thiết kế an toàn hơn là:

- Giữ fields `private`.
- Cung cấp protected/public **operations có validation rõ** nếu subclass cần extension points.
- Tránh gọi overridable instance methods từ constructor khi đối tượng subclass chưa khởi tạo đầy đủ, trừ khi thiết kế có cơ chế bảo vệ thật rõ.
- Xem xét `final class` hoặc composition nếu inheritance không mang lại giá trị.

**Không nhất thiết cấm kế thừa:** cần chọn extension points cẩn thận để mọi subclass vẫn tôn trọng hợp đồng superclass. Liskov substitution là một nguyên tắc rộng hơn: nếu subclass thay đổi behavior khiến invariant/hợp đồng bị phá, abstraction chung sẽ mất tin cậy.

## 17. Public API, serialization và reflection

Một class có fields private **không bảo đảm** rằng mọi framework hoặc mọi cơ chế runtime không thể khởi tạo/sửa trạng thái theo con đường đặc biệt:

- Một số serializer/ORM có thể tạo instance và khôi phục state theo cơ chế riêng, có thể không đi qua constructor public thông thường.
- Reflection với quyền truy cập/module configuration thích hợp có thể tiếp cận non-public members trong những điều kiện cụ thể.
- Deserialization hoặc framework-driven population có thể cần validation sau khi khôi phục dữ liệu.

Vì vậy, với đối tượng có invariant quan trọng, cần xem **toàn bộ các đường tạo/khôi phục** trong môi trường sử dụng, không chỉ cách gọi `new` trong mã nguồn ứng dụng.

Ngược lại, cũng không nên phóng đại rằng private hoàn toàn vô dụng: nó vẫn là công cụ mạnh để giữ phần lớn caller ở API được thiết kế, hỗ trợ khả năng bảo trì và kiểm tra compile-time.

## 18. Cách kiểm thử invariant và API đóng gói

Với một class bảo vệ trạng thái, hãy kiểm tra **cả thành công và thất bại**.

### 18.1. Bảng tình huống cho `BankAccount`

| Tình huống | Mong đợi |
| --- | --- |
| Tạo với số dư ban đầu 100 | Thành công, balance = 100 |
| Tạo với số dư âm | Ném exception |
| `deposit(50)` | Balance tăng đúng 50 |
| `deposit(0)` hoặc âm | Bị từ chối, balance giữ nguyên |
| `withdraw(30)` từ 150 | Balance = 120 |
| `withdraw(500)` từ 120 | Bị từ chối, balance vẫn 120 |
| Deposit làm overflow `long` | Ném exception, không có phép gán field sau overflow |
| Caller muốn `account.balance = -1` | Không biên dịch từ mã ngoài quyền private |
| Gọi method đọc state | Cho giá trị nhất quán theo contract |

### 18.2. Bảng tình huống cho mutable references

| Tình huống | Mong đợi với API được bảo vệ |
| --- | --- |
| Caller sửa list đã truyền vào constructor | State nội bộ không tự bị ảnh hưởng nếu lưu snapshot phù hợp |
| Caller gọi `getterList().add(...)` | Không thể sửa nội bộ qua getter nếu trả list unmodifiable |
| Caller sửa mảng input sau constructor | Mảng nội bộ giữ snapshot độc lập |
| Caller sửa mảng getter trả về | Không đổi mảng nội bộ nếu getter clone |
| List chứa element mutable còn được caller giữ | **Có nguy cơ chia sẻ** trừ khi element immutable hoặc được defensive-copy |
| Gọi update với hai field không thỏa quan hệ | Thao tác bị từ chối trước khi commit |
| Nhiều threads cập nhật cùng object | Cần kiểm tra concurrency contract riêng |

### 18.3. Assertions và test tự động

Java có `assert` nhưng mặc định assertion có thể **không được bật** khi chạy nếu thiếu `-ea`. Không nên dùng `assert` thay validation của public API cho dữ liệu có thể không hợp lệ đến từ người dùng/hệ thống.

Ví dụ:

~~~java
if (amount <= 0) {
    throw new IllegalArgumentException("amount must be positive");
}
~~~

hợp lý để bảo vệ invariant **dù assertion mode tắt**.

Trong project thực, có thể dùng JUnit để kiểm thử:

- Các đường khởi tạo.
- Mọi method có thể sửa state.
- Input ở biên `0`, âm, lớn, null, blank, NaN, overflow.
- State trước và sau exception.
- Defensive copies và aliases ngoài ý muốn.
- Sequencing/transitions không hợp lệ.
- Các tình huống concurrency nếu object cam kết thread safety.

## 19. Lỗi phổ biến cần tránh

| Lỗi/hiểu nhầm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “Đóng gói = thêm private vào fields là xong.” | Public methods vẫn có thể làm state sai | Thiết kế invariants và validate mọi đường tạo/cập nhật |
| Tạo object bắt buộc có tên nhưng constructor để tên null | Object chưa hợp lệ ngay sau khởi tạo | Yêu cầu dữ liệu/validate trong constructor/factory |
| Mọi field đều có public setter | Caller có thể bỏ qua hành vi nghiệp vụ | Dùng command methods với ý nghĩa và preconditions rõ |
| Setter của một field phá quan hệ với field khác | Invariant liên-field có thể bị mất | Cập nhật phối hợp hoặc immutable replacement |
| Validate sau khi đã gán field thứ nhất | Exception để lại state nửa cập nhật | Validate candidate trước khi commit |
| `balance += amount` mà không xét overflow | Field có thể tràn thành số âm | Dùng `Math.addExact`/giới hạn có chủ đích |
| `private final List` rồi trả getter mutable list | Lộ representation mutable | Snapshot/unmodifiable API/defensive copy |
| `List.copyOf` với mutable elements và tưởng deep copy | Elements vẫn có thể bị sửa qua alias | Immutable elements hoặc sao chép sâu cần thiết |
| Mảng `int[]` getter trả mảng gốc | Caller thay dữ liệu vượt validation | Clone khi nhận và trả, nếu contract cần độc lập |
| Validate array rồi lưu clone từ nguồn concurrent mutable | Có khoảng thời gian nguồn có thể bị sửa | Copy và validate dữ liệu sẽ lưu; xác định concurrency contract |
| Dùng `final` cho field rồi cho rằng object immutable | Final chỉ bảo vệ phép gán field reference | Bảo vệ mutable referents hoặc thiết kế immutable |
| Enum `status` private nhưng mở `setStatus(any)` | Caller vượt qua workflow | Dùng phương thức chuyển trạng thái có validation |
| Method bắt exception rồi lặng lẽ bỏ qua | Caller tưởng thao tác đã thành công | Báo lỗi theo contract hoặc trả result rõ |
| Dùng `protected` mutable fields cho subclass tùy ý | Subclass phá invariant | Private fields, protected validated hooks |
| Cho rằng private làm object thread-safe | Mutations vẫn có thể race | Thiết kế synchronization/atomicity theo hợp đồng |
| Dùng `assert` thay validation public method | Assertions có thể tắt | Dùng các kiểm tra luôn hoạt động và exception phù hợp |
| Chỉ test happy path | Không chứng minh invariant khi thất bại | Test invalid input và state trước/sau exception |

## 20. Checklist thiết kế một class có invariant

Khi bắt đầu tạo một class Java mới, trả lời lần lượt:

1. **Đối tượng đại diện cho điều gì?** Có một abstraction rõ không?
2. **State tối thiểu cần lưu là gì?** Có field nào dư thừa hoặc dẫn đến hai nguồn sự thật không?
3. **Invariants nào phải luôn đúng** sau khi constructor/public command hoàn tất bình thường?
4. **Input nào không hợp lệ?** Null, blank, âm, out-of-range, NaN, overflow, inconsistent combination?
5. **Có bao nhiêu đường tạo object?** Mọi constructors/factories có gọi validation chung không?
6. **Ai được sửa state?** Có thể giữ fields private và chỉ cung cấp domain operations không?
7. **Các operations có thể fail ở bước nào?** Có thể kiểm tra/tính candidate trước khi gán fields không?
8. **Có trường hợp chuyển nhiều fields cùng lúc?** Nên dùng command cập nhật nguyên một nhóm thay vì setters độc lập?
9. **Có mutable reference nào đi vào/đi ra object không?** Collection, array, Date, builder, user-defined mutable type?
10. **Ownership ra sao?** Class giữ snapshot hay chủ đích chia sẻ instance? Caller có được sửa dữ liệu được trả không?
11. **Có cần immutable object không?** Có thể dùng private final primitives/immutable values, records hoặc methods trả object mới?
12. **Subclass có thể làm vỡ invariant không?** Có nên final class hoặc thiết kế protected API kiểm soát?
13. **Object có dùng chung giữa threads không?** Nếu có, các kiểm tra và cập nhật liên-field cần synchronization/atomicity ra sao?
14. **Có đường tạo bằng framework/serialization không?** Đảm bảo dữ liệu khôi phục được validate theo cơ chế phù hợp.
15. **Test đã bao phủ hành vi sai và state sau lỗi chưa?** Không chỉ in output khi gọi đúng.

Một class có encapsulation tốt giúp caller **dùng API đúng tự nhiên** và **khó đưa object vào trạng thái sai**. Tài liệu và tên methods quan trọng không kém access modifiers.

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Class `Account` có `public long balance;`. Vì sao việc có method `withdraw` kiểm tra số dư vẫn chưa bảo đảm invariant?  
**Đáp án:** Caller vẫn có thể ghi trực tiếp `account.balance = -100`, bỏ qua method kiểm tra.

**Câu 2.** Nếu đổi `balance` thành `private` nhưng thêm setter `setBalance(long)` không kiểm tra gì, class đã bảo vệ invariant chưa?  
**Đáp án:** Chưa. Caller vẫn tạo số dư âm qua API được công bố. `private` chỉ chặn field access trực tiếp.

**Câu 3.** Vì sao constructor cần validate dữ liệu cần thiết?  
**Đáp án:** Để object hoàn tất khởi tạo ở trạng thái hợp lệ, không buộc mọi caller nhớ các bước sửa chữa sau khi tạo.

**Câu 4.** `final List<String> members` có khiến list immutable không?  
**Đáp án:** Không. `final` chỉ ngăn gán lại reference của field; nếu list mutable thì các phần tử vẫn thêm/xóa được qua alias.

**Câu 5.** Vì sao `List.copyOf(input)` giúp bảo vệ list String trước việc caller thêm phần tử vào `input` sau constructor?  
**Đáp án:** Nó cung cấp unmodifiable list với elements tại thời điểm gọi; thay đổi cấu trúc input list sau đó không tự đổi danh sách được lưu.

**Câu 6.** Nếu list chứa `Address` mutable, `List.copyOf` đã tạo deep copy chưa?  
**Đáp án:** Chưa. Reference tới Address elements có thể được chia sẻ. Cần immutable elements hoặc defensive copies sâu nếu muốn tách trạng thái.

**Câu 7.** Với `int[] input`, vì sao nên clone ở constructor và ở getter của class cần giữ snapshot riêng?  
**Đáp án:** Vì mảng mutable; caller có thể giữ/sửa input hoặc sửa mảng nhận từ getter nếu không copy.

**Câu 8.** Tại sao hai setters `setStart`/`setEnd` có thể khó bảo đảm invariant `start <= end`?  
**Đáp án:** Chúng cho phép sửa từng field, có thể tạo trạng thái trung gian sai. Method cập nhật cặp ngày có thể validate cả quan hệ trước khi commit.

**Câu 9.** `ship()` của Order nên làm gì khi status vẫn `CREATED`?  
**Đáp án:** Từ chối trước khi đổi state (ví dụ `IllegalStateException`); Order vẫn `CREATED` theo contract.

**Câu 10.** Nếu `deposit` validate số dương nhưng cộng `long` bị overflow, invariant `balance >= 0` có thể bị phá không?  
**Đáp án:** Có nếu dùng phép `+` thông thường không kiểm tra. `Math.addExact` ném exception khi overflow, không cho gán giá trị tính sai vào balance.

**Câu 11.** Vì sao `Double.isFinite` hữu ích khi validate số đo?  
**Đáp án:** Nó loại NaN và vô cực, những giá trị có thể đi qua các so sánh miền giá trị theo cách không mong muốn.

**Câu 12.** `final class` có tự bảo đảm tất cả objects của class immutable không?  
**Đáp án:** Không. `final class` ngăn kế thừa, không ngăn sửa fields hoặc mutable referenced objects.

**Câu 13.** Vì sao check input trước rồi mới cập nhật fields có ích cho exception safety?  
**Đáp án:** Nếu input không hợp lệ, method ném exception trước khi thay đổi state. Nhưng với side effects ngoài object hoặc concurrency, cần giải pháp bổ sung.

**Câu 14.** `private int count` và method `increment() { count++; }` có tự thread-safe không?  
**Đáp án:** Không. `count++` không atomic khi nhiều threads cùng thao tác; private không cung cấp synchronization.

**Câu 15.** Vì sao giữ fields private có thể giúp cải tiến implementation mà ít phá caller?  
**Đáp án:** Caller phụ thuộc public behavior thay vì layout fields; class có thể đổi cách lưu dữ liệu mà vẫn giữ hợp đồng method.

**Câu 16.** Khi nào setter đơn giản vẫn phù hợp?  
**Đáp án:** Khi việc gán trực tiếp một thuộc tính là operation hợp lệ, có validation rõ và không bỏ qua invariant; không phải mọi class đều cần domain command phức tạp.

**Câu 17.** Tại sao một framework tạo object bằng đường không bình thường có thể cần validation riêng?  
**Đáp án:** Vì một số cơ chế khôi phục object có thể không sử dụng constructor API theo cách caller thường dùng; invariant vẫn cần được bảo vệ theo contract/framework.

**Câu 18.** Nên kiểm tra những gì sau khi một command bị từ chối?  
**Đáp án:** Ngoại lệ/kết quả báo lỗi đúng và **trạng thái object vẫn hợp lệ**, lý tưởng không đổi với các operations đã cam kết fail-without-state-change.

## Tài liệu tham khảo

- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): quyền truy cập class và thành viên.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): field modifiers, `final`.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): khởi tạo đối tượng qua constructors.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list snapshot theo hợp đồng.
- Java Platform API, [`Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): kiểm tra tràn phép cộng nguyên.
- Java Platform API, [`Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): kiểm tra non-null.

## Ghi nhớ

**Đóng gói hiệu quả = giữ state trong một abstraction có ranh giới rõ + chỉ công bố những operations duy trì quy tắc hợp lệ**. Field `private` là bước đầu, nhưng chưa đủ: constructor phải tạo object hợp lệ; public commands phải validate và duy trì invariants; getters và constructors không được lộ mutable representation ngoài ý muốn. Khi cập nhật nhiều fields, hãy **validate ứng viên trước khi commit**; khi chia sẻ mảng/collection, xét **defensive copy**, shallow/deep sharing và ownership.

Không đồng nhất `private`, `final`, immutability, thread safety hay bảo mật hệ thống. Chúng giải quyết những yêu cầu khác nhau. Lớp Java được thiết kế tốt khiến caller dễ làm đúng và khó làm sai: **điều quan trọng nhất không phải dữ liệu bị giấu bao nhiêu, mà là mọi con đường công khai đều tôn trọng hợp đồng của đối tượng**.
