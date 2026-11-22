# Viết kiểm thử cho khởi tạo, cập nhật, trường hợp biên và lỗi đầu vào — Java 17+

## Mục tiêu

Bài học thuộc chủ đề **Thiết kế và thực hành** của Java core. Sau khi hoàn thành, bạn biết:

- Xác định **đầu vào hợp lệ, giá trị ban đầu, các bất biến (invariants)** và hành vi có thể quan sát của một class.
- Viết test cho constructor/factory: default values, normalization, mọi giá trị ở ranh giới và trường hợp không thể khởi tạo.
- Viết test cho methods thay đổi state: thao tác thành công, chuỗi thao tác, rejected command, rollback/strong exception guarantee khi được yêu cầu.
- Chọn **equivalence partitions** và **boundary values**: min-1, min, min+1, max-1, max, max+1; null, empty, blank; số 0, overflow, dữ liệu thời gian.
- Sử dụng **Arrange–Act–Assert**, test fixture riêng, assertion có ý nghĩa, error labels dễ chẩn đoán.
- Phân biệt kiểm **giá trị trả về**, **trạng thái đối tượng**, **exception type** và **external side effects**; không bỏ sót state sau exception.
- Tránh test giả: chỉ gọi method, dùng `catch(Exception)` rồi PASS, dùng Java `assert` nhưng quên `-ea`.
- Kiểm defensive copy, immutable value objects và derived values sau một update.
- Dùng table-driven/property testing cho nhiều cases cùng logic và state-transition matrix cho workflow.
- Biết tổ chức test bằng JUnit Jupiter 5, `@Test`, `@BeforeEach`, `assertThrows`, `assertAll`, `@ParameterizedTest`, cùng Maven Surefire.
- Viết unit tests ổn định: input cố định, clock được kiểm soát, không dựa vào network, thread sleeps, GC timing hoặc thứ tự HashMap.
- Tự biên dịch/chạy các bộ test Java 17+ **không cần thư viện bên ngoài**, xác nhận stdout kỳ vọng và tìm lỗi thực.

> **Phạm vi và phiên bản:** JDK 17 trở lên. Các chương trình có `public class FileName`, lệnh `javac --release 17` và `java` có thể chạy **độc lập**. Những snippet không có main chỉ minh họa. Ví dụ JUnit Maven ở phần sau cần dependency được khai báo rõ.

## 1. Kiểm thử không chỉ là gọi thử method

Giả sử có `Account` với balance ban đầu 100:

~~~java
Account account = new Account(100); // Arrange
account.deposit(50);                // Act
check(account.balance() == 150, "deposit"); // Assert
~~~

Nếu không có assertion cuối, test sẽ pass ngay cả khi `deposit` là method rỗng. Một test có giá trị phải mô tả **hành vi đúng có thể quan sát**.

Mỗi contract nên có:

1. **Input/precondition:** giá trị ban đầu, object state, collaborator.
2. **Operation:** constructor, method, state transition.
3. **Expected value/state:** điều gì phải thay đổi, điều gì giữ nguyên.
4. **Invalid path:** khi không thể xử lý, lỗi nào được báo và state ra sao.
5. **Invariant:** thuộc tính phải tiếp tục đúng sau các operations.

Ví dụ Account:

~~~text
opening >= 0
deposit amount > 0
withdraw amount > 0 and <= balance
balance never negative
invalid input must not change balance
arithmetic overflow must be rejected
~~~

### 1.1. Bốn nhóm test bắt buộc

| Nhóm | Ví dụ | Điều cần kiểm |
| --- | --- | --- |
| Khởi tạo | Account(0), Account(-1) | Initial state đúng, invalid bị reject |
| Cập nhật | deposit(50), withdraw(20) | Trước/sau và invariant |
| Trường hợp biên | withdraw(balance), quantity 1/100 | Không lỗi off-by-one |
| Lỗi đầu vào | null, blank, negative, overflow | Exception đúng, state không hỏng |

Một bộ test chỉ có happy path không bảo đảm invariants. Một bộ chỉ dùng exceptions không bảo đảm operation hợp lệ hoạt động.

## 2. Assertions phải chạy thật

Java keyword `assert` mặc định bị disable nếu chạy `java Main` không có `-ea`. Để test không thể âm thầm bị bỏ qua, dùng JUnit hoặc một helper:

~~~java
static void check(boolean ok, String label) {
    if (!ok) {
        throw new AssertionError(label);
    }
}
~~~

Với exception, pattern:

~~~java
static void expectThrows(
        Class<? extends Throwable> kind, Runnable operation) {
    try {
        operation.run();
    } catch (Throwable caught) {
        if (kind.isInstance(caught)) {
            return;
        }
        throw new AssertionError("wrong exception", caught);
    }
    throw new AssertionError("missing exception");
}
~~~

Các helper nhỏ chỉ dùng trong chương trình độc lập. JUnit `assertThrows` báo lỗi tốt hơn và dùng functional interface `Executable` hỗ trợ checked exceptions. `catch(Throwable)` chỉ phục vụ kiểm đúng loại trong helper demo, không phải pattern xử lý mọi lỗi production.

**Đừng bao giờ:**

~~~java
try {
    account.withdraw(-1);
} catch (Exception ignored) {
    // PASS? Sai: có thể nuốt NPE do bug.
}
~~~

Nó không báo fail khi operation không throw, và có thể chấp nhận loại exception khác contract.

## 3. Constructor tests: hợp lệ, normalization, null và biên

Yêu cầu ví dụ: Customer có name sau `strip()` không rỗng, age trong khoảng [0,150].

Case classes:
- age=0 và 150 hợp lệ;
- age=-1 và 151 bị từ chối;
- name=null → NPE;
- name="" và name="   " → IllegalArgumentException;
- name="  Lan  " → canonical value "Lan".

### 3.1. Chương trình 1 — constructor validation

Lưu **`ConstructorTest.java`**:

~~~java
import java.util.Objects;

public class ConstructorTest {
    static final class Customer {
        private final String name;
        private final int age;

        Customer(String name, int age) {
            Objects.requireNonNull(name, "name");
            String cleaned = name.strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
            this.name = cleaned;
            this.age = age;
        }

        String name() {
            return name;
        }

        int age() {
            return age;
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void expect(Class<? extends Throwable> kind,
                       Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong error", caught);
        }
        throw new AssertionError("expected error");
    }

    public static void main(String[] args) {
        Customer baby = new Customer(" Lan ", 0);
        Customer elder = new Customer("Minh", 150);
        check(baby.name().equals("Lan"), "normalized");
        check(baby.age() == 0, "lower bound");
        check(elder.age() == 150, "upper bound");

        expect(NullPointerException.class,
                () -> new Customer(null, 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("", 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("   ", 20));
        expect(IllegalArgumentException.class,
                () -> new Customer("A", -1));
        expect(IllegalArgumentException.class,
                () -> new Customer("A", 151));

        System.out.println("constructor tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConstructorTest.java
java ConstructorTest
~~~

Stdout:

~~~text
constructor tests passed
~~~

**Điểm cần nhớ:** Test không chỉ xem constructor có throw hay không. Nó kiểm cả object state hợp lệ và normalization. Khi constructor thất bại, caller không nhận được một instance khởi tạo đầy đủ; nếu constructor còn gọi external dependency, test cần đảm bảo không có side effect ngoài ý muốn.

## 4. Constructor overload và default values

Nếu class có:

~~~java
class Timer {
    private final int seconds;

    Timer() {
        this(30);
    }

    Timer(int seconds) {
        if (seconds <= 0) {
            throw new IllegalArgumentException("seconds");
        }
        this.seconds = seconds;
    }
}
~~~

Các paths phải cùng invariant seconds>0. Test một constructor hợp lệ không chứng minh overload còn lại đúng. Nên test default=30, minimum=1, invalid 0, và explicit value thông thường.

### 4.1. Chương trình 2 — overload tests

Lưu **`OverloadTest.java`**:

~~~java
public class OverloadTest {
    static final class Timer {
        private final int seconds;

        Timer() {
            this(30);
        }

        Timer(int seconds) {
            if (seconds <= 0) {
                throw new IllegalArgumentException("seconds");
            }
            this.seconds = seconds;
        }

        int seconds() {
            return seconds;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(new Timer().seconds() == 30, "default");
        check(new Timer(1).seconds() == 1, "min");
        check(new Timer(60).seconds() == 60, "explicit");

        try {
            new Timer(0);
            throw new AssertionError("zero accepted");
        } catch (IllegalArgumentException expected) {
            // Validation works.
        }

        System.out.println("overload tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OverloadTest.java
java OverloadTest
~~~

Stdout:

~~~text
overload tests passed
~~~

## 5. Update tests: before, act, after và rejected action

Một Account có thể deposit/withdraw, nhưng phải giữ balance≥0. Ta cần:

- initial balance;
- deposit success;
- withdraw success;
- withdraw chính xác balance về 0;
- deposit 0/negative reject;
- withdraw quá số dư reject;
- overflow reject thay vì wraparound;
- mọi rejected command giữ balance như trước.

Nếu method update nhiều fields, kiểm **tất cả canonical fields** sau rejection chứ không chỉ một field.

### 5.1. Chương trình 3 — update và không đổi trạng thái khi thất bại

Lưu **`AccountTest.java`**:

~~~java
public class AccountTest {
    static final class Account {
        private long balance;

        Account(long opening) {
            if (opening < 0) {
                throw new IllegalArgumentException("opening");
            }
            balance = opening;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("withdraw");
            }
            balance -= amount;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void expect(Class<? extends Throwable> kind,
                       Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("no exception");
    }

    public static void main(String[] args) {
        Account account = new Account(100);
        check(account.balance() == 100, "initial");

        account.deposit(50);
        check(account.balance() == 150, "deposit");

        account.withdraw(25);
        check(account.balance() == 125, "withdraw");

        long beforeError = account.balance();
        expect(IllegalArgumentException.class,
                () -> account.deposit(0));
        expect(IllegalArgumentException.class,
                () -> account.deposit(-1));
        expect(IllegalArgumentException.class,
                () -> account.withdraw(0));
        expect(IllegalArgumentException.class,
                () -> account.withdraw(126));

        check(account.balance() == beforeError,
                "invalid commands preserve balance");

        Account nearMax = new Account(Long.MAX_VALUE - 1);
        expect(ArithmeticException.class,
                () -> nearMax.deposit(2));
        check(nearMax.balance() == Long.MAX_VALUE - 1,
                "overflow must not mutate balance");

        Account exact = new Account(100);
        exact.withdraw(100);
        check(exact.balance() == 0, "exact full withdrawal");

        System.out.println("account tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AccountTest.java
java AccountTest
~~~

Stdout:

~~~text
account tests passed
~~~

Ở `balance = Math.addExact(balance, amount)`, nếu Math.addExact throw, RHS không trả giá trị nên assignment chưa hoàn tất. Điều đó giúp giữ balance ở case overflow. Không suy ra mọi method có nhiều assignments đều atomic; với DB/concurrency còn cần transactions hoặc synchronization phù hợp.

## 6. Equivalence partitioning và boundary-value analysis

Với một field quantity thuộc [1,100]:

| Nhóm | Giá trị tiêu biểu | Kỳ vọng |
| --- | --- | --- |
| Bên dưới | -1, 0 | Reject |
| Min | 1 | Accept |
| Trong khoảng | 2, 50, 99 | Accept |
| Max | 100 | Accept |
| Bên trên | 101, 1000 | Reject |

Trọng tâm là những điểm **min-1 / min / min+1 / max-1 / max / max+1** để phát hiện off-by-one. Bổ sung kiểu dữ liệu đặc biệt: null, empty, whitespace, min/max số nguyên, overflow, và boundaries theo ngày giờ.

### 6.1. Chương trình 4 — quantity boundary

Lưu **`QuantityTest.java`**:

~~~java
public class QuantityTest {
    record Line(long cents, int quantity) {
        Line {
            if (cents < 0) {
                throw new IllegalArgumentException("price");
            }
            if (quantity < 1 || quantity > 100) {
                throw new IllegalArgumentException("quantity");
            }
        }

        long total() {
            return Math.multiplyExact(cents, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void reject(int quantity) {
        try {
            new Line(50, quantity);
            throw new AssertionError("accepted " + quantity);
        } catch (IllegalArgumentException expected) {
            // Rejected.
        }
    }

    public static void main(String[] args) {
        check(new Line(50, 1).total() == 50, "min");
        check(new Line(50, 2).total() == 100, "min+1");
        check(new Line(50, 99).total() == 4950, "max-1");
        check(new Line(50, 100).total() == 5000, "max");
        reject(-1);
        reject(0);
        reject(101);
        System.out.println("quantity tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 QuantityTest.java
java QuantityTest
~~~

Stdout:

~~~text
quantity tests passed
~~~

## 7. Table-driven tests cho nhiều inputs cùng một behavior

Nếu input→expected dễ thể hiện bằng bảng, dùng record/array thay vì hàng chục methods lặp lại.

Chính sách ví dụ:
- Score ngoài [0,100] reject.
- A nếu ≥90, B nếu ≥80, C nếu ≥50, D còn lại.

~~~text
score:      0  49  50  79  80  89  90 100
expected:   D   D   C   C   B   B   A   A
~~~

### 7.1. Chương trình 5 — table-driven grade test

Lưu **`GradeTest.java`**:

~~~java
public class GradeTest {
    record Case(int score, String expected) {
    }

    static String grade(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score");
        }
        if (score >= 90) {
            return "A";
        }
        if (score >= 80) {
            return "B";
        }
        if (score >= 50) {
            return "C";
        }
        return "D";
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Case[] tests = {
                new Case(0, "D"), new Case(49, "D"),
                new Case(50, "C"), new Case(79, "C"),
                new Case(80, "B"), new Case(89, "B"),
                new Case(90, "A"), new Case(100, "A")
        };

        for (Case test : tests) {
            check(test.expected().equals(grade(test.score())),
                    "score=" + test.score());
        }

        for (int invalid : new int[] {-1, 101}) {
            try {
                grade(invalid);
                throw new AssertionError("accepted " + invalid);
            } catch (IllegalArgumentException expected) {
                // Outside score domain.
            }
        }

        System.out.println("table cases=" + tests.length);
        System.out.println("grade tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GradeTest.java
java GradeTest
~~~

Stdout:

~~~text
table cases=8
grade tests passed
~~~

Bảng trên chỉ là policy minh họa, không phải thang điểm bắt buộc. Một test tốt diễn đạt đúng **business requirement** thay vì assumption ngầm của người viết test.

## 8. State-transition tests: constructor + update theo workflow

Object Order có thể có trạng thái:

~~~text
DRAFT ──pay────► PAID
   |
   └──cancel───► CANCELLED
~~~

Các transitions khác bị cấm trong demo. Tests nên kiểm:
- New Order ở DRAFT.
- Pay từ DRAFT sang PAID.
- Cancel từ DRAFT sang CANCELLED.
- Không pay hai lần, không cancel PAID, không pay CANCELLED.
- Rejected transition phải giữ original state.

### 8.1. Chương trình 6 — order lifecycle tests

Lưu **`OrderStateTest.java`**:

~~~java
public class OrderStateTest {
    enum State {
        DRAFT, PAID, CANCELLED
    }

    static final class Order {
        private State state = State.DRAFT;

        State state() {
            return state;
        }

        void pay() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("pay");
            }
            state = State.PAID;
        }

        void cancel() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("cancel");
            }
            state = State.CANCELLED;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejected(Runnable action) {
        try {
            action.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("invalid transition accepted");
    }

    public static void main(String[] args) {
        Order paid = new Order();
        check(paid.state() == State.DRAFT, "initial");
        paid.pay();
        check(paid.state() == State.PAID, "paid");

        rejected(paid::pay);
        rejected(paid::cancel);
        check(paid.state() == State.PAID, "paid remains");

        Order cancelled = new Order();
        cancelled.cancel();
        check(cancelled.state() == State.CANCELLED, "cancelled");
        rejected(cancelled::pay);
        check(cancelled.state() == State.CANCELLED,
                "cancelled remains");

        System.out.println("state transition tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OrderStateTest.java
java OrderStateTest
~~~

Stdout:

~~~text
state transition tests passed
~~~

Mỗi test scenario có fixture Order mới. Một test không nên dựa việc một test khác đã pay trên object dùng chung.

## 9. Exception safety: validate trước khi thay nhiều fields

Anti-pattern:

~~~java
void change(int nextQuantity, long nextPrice) {
    quantity = nextQuantity;
    validate(nextPrice); // Có thể throw.
    price = nextPrice;
}
~~~

Nếu validate throw thì quantity đã bị đổi; vậy một lỗi đầu vào có thể làm object inconsistent. Khi contract yêu cầu **all-or-nothing**, test phải snapshot cả quantity và price.

Sửa: validate các inputs, tính derived constraints **trước** các assignments. Điều này không tự thay thế database transaction hoặc concurrency lock khi có nhiều threads, nhưng đủ để minh họa single-thread object.

### 9.1. Chương trình 7 — atomic update tests

Lưu **`AtomicUpdateTest.java`**:

~~~java
public class AtomicUpdateTest {
    static final class Line {
        private int quantity;
        private long price;

        Line(int quantity, long price) {
            change(quantity, price);
        }

        void change(int nextQuantity, long nextPrice) {
            if (nextQuantity <= 0 || nextPrice < 0) {
                throw new IllegalArgumentException("line");
            }
            Math.multiplyExact(nextQuantity, nextPrice);
            quantity = nextQuantity;
            price = nextPrice;
        }

        int quantity() {
            return quantity;
        }

        long price() {
            return price;
        }

        long total() {
            return Math.multiplyExact(quantity, price);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejected(Class<? extends Throwable> kind,
                         Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("missing exception");
    }

    public static void main(String[] args) {
        Line line = new Line(2, 100);
        line.change(3, 150);
        check(line.total() == 450, "valid update");

        rejected(IllegalArgumentException.class,
                () -> line.change(0, 200));
        check(line.quantity() == 3 && line.price() == 150,
                "after invalid");

        rejected(ArithmeticException.class,
                () -> line.change(2, Long.MAX_VALUE));
        check(line.quantity() == 3 && line.price() == 150,
                "after overflow");
        check(line.total() == 450, "derived total");

        System.out.println("atomic update tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AtomicUpdateTest.java
java AtomicUpdateTest
~~~

Stdout:

~~~text
atomic update tests passed
~~~

## 10. Null, empty và blank là các loại dữ liệu riêng

Đối với input String:
- Null: không có object, có thể NPE nếu contract dùng `requireNonNull`.
- Empty: `""` có length 0.
- Blank: `"   "` có length>0 nhưng `isBlank()` true.
- Normalized: `"  Lan  "` có thể strip thành "Lan".
- Unicode: `String.length()` đếm UTF-16 code units, không mặc nhiên bằng số grapheme clusters; domain phải xác định thước đo nếu user-facing limit.

### 10.1. Chương trình 8 — text input tests

Lưu **`TextInputTest.java`**:

~~~java
import java.util.Objects;

public class TextInputTest {
    record UserName(String value) {
        UserName {
            value = Objects.requireNonNull(value).strip();
            if (value.isBlank() || value.length() > 12) {
                throw new IllegalArgumentException("username");
            }
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void rejects(Class<? extends Throwable> kind,
                        Runnable operation) {
        try {
            operation.run();
        } catch (Throwable caught) {
            if (kind.isInstance(caught)) {
                return;
            }
            throw new AssertionError("wrong exception", caught);
        }
        throw new AssertionError("not rejected");
    }

    public static void main(String[] args) {
        check(new UserName(" Lan ").value().equals("Lan"),
                "normalized");
        check(new UserName("A").value().length() == 1, "min");
        check(new UserName("123456789012").value().length() == 12,
                "max");

        rejects(NullPointerException.class,
                () -> new UserName(null));
        rejects(IllegalArgumentException.class,
                () -> new UserName(""));
        rejects(IllegalArgumentException.class,
                () -> new UserName("    "));
        rejects(IllegalArgumentException.class,
                () -> new UserName("1234567890123"));

        System.out.println("text input tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TextInputTest.java
java TextInputTest
~~~

Stdout:

~~~text
text input tests passed
~~~

Nếu spec giới hạn 12 code points thay vì UTF-16 units, phải thay rule và tests phù hợp; đừng sử dụng ví dụ như một policy username phổ quát.

## 11. Kiểm thử defensive copy và không expose mutable state

Một record với component List có final reference nhưng **chưa chắc bất biến sâu**. Nếu giữ input mutable List trực tiếp, caller có thể add/remove sau khi constructor xong.

Dùng `List.copyOf` để tạo unmodifiable snapshot cấu trúc List; với nested mutable elements, nó vẫn là shallow copy. Test nên kiểm:
- caller mutate original list không ảnh hưởng object;
- getter không cho mutate;
- null list và null elements bị xử lý theo contract;
- derived count/sum không stale.

### 11.1. Chương trình 9 — defensive copy tests

Lưu **`DefensiveCopyTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class DefensiveCopyTest {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);
        source.add("B");

        check(basket.count() == 1, "snapshot size");
        check(basket.items().equals(List.of("A")),
                "snapshot contents");

        try {
            basket.items().add("C");
            throw new AssertionError("mutable getter");
        } catch (UnsupportedOperationException expected) {
            // Correctly unmodifiable.
        }

        try {
            new Basket(null);
            throw new AssertionError("null list accepted");
        } catch (NullPointerException expected) {
            // Rejected.
        }

        try {
            new Basket(Arrays.asList("A", null));
            throw new AssertionError("null element accepted");
        } catch (NullPointerException expected) {
            // List.copyOf rejects null elements.
        }

        System.out.println("defensive copy tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DefensiveCopyTest.java
java DefensiveCopyTest
~~~

Stdout:

~~~text
defensive copy tests passed
~~~

## 12. Derived state sau immutable update

Một immutable Line nên giữ source fields, tính total khi cần. Test old object phải **unchanged** sau tạo bản mới và sau một attempt invalid.

### 12.1. Chương trình 10 — immutable update tests

Lưu **`ImmutableUpdateTest.java`**:

~~~java
public class ImmutableUpdateTest {
    record Line(long cents, int quantity) {
        Line {
            if (cents < 0 || quantity <= 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(cents, quantity);
        }

        Line withQuantity(int next) {
            return new Line(cents, next);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Line original = new Line(100, 2);
        Line updated = original.withQuantity(3);

        check(original.quantity() == 2, "old quantity");
        check(original.total() == 200, "old total");
        check(updated.quantity() == 3, "new quantity");
        check(updated.total() == 300, "new total");

        try {
            original.withQuantity(-1);
            throw new AssertionError("negative accepted");
        } catch (IllegalArgumentException expected) {
            // Old value unchanged.
        }

        check(original.total() == 200, "after rejection");

        System.out.println("immutable update tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ImmutableUpdateTest.java
java ImmutableUpdateTest
~~~

Stdout:

~~~text
immutable update tests passed
~~~

Nếu class dùng cached total field, test này sẽ bắt regression “quantity đổi nhưng total cũ vẫn hiện”.

## 13. Numeric extremes và overflow

Cần thử:
- min/max của domain;
- zero và negative nếu cấm;
- những phép toán dẫn xuất như `quantity * price` gần giới hạn;
- BigDecimal precision/rounding nếu tiền có fractions;
- integer divide/units sai (cents so với dollars).

`Math.multiplyExact` và `Math.addExact` là công cụ phát hiện long overflow thay vì silent wraparound.

### 13.1. Chương trình 11 — overflow boundary tests

Lưu **`OverflowTest.java`**:

~~~java
public class OverflowTest {
    record Line(long priceCents, int quantity) {
        Line {
            if (priceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(priceCents, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(new Line(0, 10).total() == 0, "zero");
        check(new Line(125, 3).total() == 375, "normal");
        check(new Line(Long.MAX_VALUE, 1).total()
                == Long.MAX_VALUE, "max");

        try {
            new Line(Long.MAX_VALUE, 2).total();
            throw new AssertionError("overflow accepted");
        } catch (ArithmeticException expected) {
            // Exact arithmetic rejects overflow.
        }

        System.out.println("overflow tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OverflowTest.java
java OverflowTest
~~~

Stdout:

~~~text
overflow tests passed
~~~

Đừng pin exact message của ArithmeticException do JDK nếu contract chỉ đòi exception type.

## 14. Time boundary tests phải deterministic

Dùng `LocalDate.of(...)` hoặc inject `Clock`, không dựa `LocalDate.now()` trong test có expected cố định. Ví dụ subscription active trên **[start, end)** (start inclusive, end exclusive).

Test:
- ngày trước start → false;
- ngày start → true;
- ngày cuối trước end → true;
- ngày end → false;
- end<=start → constructor reject.

### 14.1. Chương trình 12 — period boundary tests

Lưu **`PeriodTest.java`**:

~~~java
import java.time.LocalDate;

public class PeriodTest {
    record Subscription(LocalDate start, LocalDate end) {
        Subscription {
            if (start == null || end == null ||
                    !start.isBefore(end)) {
                throw new IllegalArgumentException("period");
            }
        }

        boolean activeAt(LocalDate day) {
            if (day == null) {
                throw new IllegalArgumentException("day");
            }
            return !day.isBefore(start) && day.isBefore(end);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Subscription s = new Subscription(
                LocalDate.of(2026, 10, 1),
                LocalDate.of(2026, 11, 1));

        check(!s.activeAt(LocalDate.of(2026, 9, 30)),
                "before start");
        check(s.activeAt(LocalDate.of(2026, 10, 1)),
                "inclusive start");
        check(s.activeAt(LocalDate.of(2026, 10, 31)),
                "last active day");
        check(!s.activeAt(LocalDate.of(2026, 11, 1)),
                "exclusive end");

        try {
            new Subscription(LocalDate.of(2026, 11, 1),
                    LocalDate.of(2026, 11, 1));
            throw new AssertionError("empty period accepted");
        } catch (IllegalArgumentException expected) {
            // Zero duration not allowed.
        }

        System.out.println("period tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PeriodTest.java
java PeriodTest
~~~

Stdout:

~~~text
period tests passed
~~~

Trong domain timestamp, cần `Instant` và timezone/DST contract, không tự quy tất cả “expiry” về LocalDate.

## 15. Property/invariant testing trên miền nhỏ

Thay vì một input riêng, dùng loops để kiểm tính chất:

~~~text
price>=0, quantity>=0
total=price×quantity
total>=0 trong miền không overflow
quantity=0 ⇒ total=0
~~~

Loop price=0..20, quantity=0..20 kiểm 21×21=441 cases. Không chứng minh mọi long values, nhưng tìm regression tốt.

### 15.1. Chương trình 13 — property test

Lưu **`PropertyTest.java`**:

~~~java
public class PropertyTest {
    record Line(long price, int quantity) {
        Line {
            if (price < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(price, quantity);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int cases = 0;
        for (int price = 0; price <= 20; price++) {
            for (int quantity = 0; quantity <= 20; quantity++) {
                Line line = new Line(price, quantity);
                check(line.total() == (long) price * quantity,
                        "formula");
                check(line.total() >= 0, "nonnegative");
                if (quantity == 0) {
                    check(line.total() == 0, "zero quantity");
                }
                cases++;
            }
        }
        System.out.println("property cases=" + cases);
        System.out.println("property tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PropertyTest.java
java PropertyTest
~~~

Stdout:

~~~text
property cases=441
property tests passed
~~~

Trong dự án lớn có thể dùng property-based libraries sinh dữ liệu và shrink failures, nhưng cần dependency riêng. Nếu random inputs, lưu seed để tái hiện lỗi.

## 16. Test isolation: không shared mutable fixture

Test B không được phụ thuộc test A chạy trước. Lỗi tiêu biểu:

~~~java
// static Account shared = new Account(100);
// testA deposit(50), testB mong initial=100.
// Kết quả phụ thuộc order và gây flaky suite.
~~~

Mỗi test nên tự tạo object hoặc dùng `@BeforeEach`. Không phụ thuộc vào một static collection chưa reset, timezone máy, network, thread scheduling hoặc GC timing.

### 16.1. Chương trình 14 — independent fixtures

Lưu **`IsolationTest.java`**:

~~~java
public class IsolationTest {
    static class Counter {
        private int value;

        Counter(int initial) {
            value = initial;
        }

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void testIncrement() {
        Counter counter = new Counter(10);
        counter.increment();
        check(counter.value() == 11, "increment");
    }

    static void testInitial() {
        Counter counter = new Counter(10);
        check(counter.value() == 10, "initial");
    }

    public static void main(String[] args) {
        testIncrement();
        testInitial();
        testInitial();
        testIncrement();

        System.out.println("isolation tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 IsolationTest.java
java IsolationTest
~~~

Stdout:

~~~text
isolation tests passed
~~~

## 17. Kiểm thử side effect bằng fake dependency

Nếu class gửi notification khi đăng ký thành công, test không nên gửi email thật. Inject interface và fake ghi messages trong memory. Kiểm **có thông báo khi hợp lệ** và **không thông báo khi input lỗi**.

### 17.1. Chương trình 15 — notifier fake

Lưu **`NotifierTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NotifierTest {
    interface Notifier {
        void send(String message);
    }

    static final class FakeNotifier implements Notifier {
        private final List<String> sent = new ArrayList<>();

        @Override
        public void send(String message) {
            sent.add(message);
        }

        List<String> sent() {
            return List.copyOf(sent);
        }
    }

    static final class Registration {
        private final Notifier notifier;

        Registration(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier);
        }

        void register(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            notifier.send("registered:" + name);
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        FakeNotifier fake = new FakeNotifier();
        Registration service = new Registration(fake);
        service.register("Lan");

        check(fake.sent().equals(List.of("registered:Lan")),
                "valid notification");

        try {
            service.register(" ");
            throw new AssertionError("blank accepted");
        } catch (IllegalArgumentException expected) {
            // Validation should have no side effect.
        }

        check(fake.sent().size() == 1,
                "error must not notify");

        System.out.println("notifier tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NotifierTest.java
java NotifierTest
~~~

Stdout:

~~~text
notifier tests passed
~~~

## 18. Sequence tests và idempotence

Một stateful object có thể đúng khi test từng call nhưng sai sau nhiều thao tác. Ví dụ:

~~~text
new Counter(0)
increase → 1
increase → 2
decrease → 1
reset → 0
decrease → exception và vẫn 0
~~~

Test sequence nên xác minh cả các intermediate states; nếu nghiệp vụ yêu cầu idempotent command, gọi lặp và so kết quả tương ứng. Không mặc định mọi command phải idempotent: `increment` đương nhiên không idempotent, còn `setStatus(PAID)` có thể có contract khác.

### 18.1. Chương trình 16 — counter sequence test

Lưu **`SequenceTest.java`**:

~~~java
public class SequenceTest {
    static final class Counter {
        private int value;

        Counter(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial");
            }
            value = initial;
        }

        int value() {
            return value;
        }

        void increase() {
            value = Math.addExact(value, 1);
        }

        void decrease() {
            if (value == 0) {
                throw new IllegalStateException("zero");
            }
            value--;
        }

        void reset() {
            value = 0;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Counter c = new Counter(0);
        check(c.value() == 0, "initial");
        c.increase();
        c.increase();
        check(c.value() == 2, "two increases");
        c.decrease();
        check(c.value() == 1, "decrease");
        c.reset();
        check(c.value() == 0, "reset");

        try {
            c.decrease();
            throw new AssertionError("negative allowed");
        } catch (IllegalStateException expected) {
            check(c.value() == 0, "state unchanged");
        }

        System.out.println("sequence tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SequenceTest.java
java SequenceTest
~~~

Stdout:

~~~text
sequence tests passed
~~~

## 19. JUnit Jupiter 5 trong dự án Maven

Helper tự viết tốt cho các bài Java 17 độc lập. Dự án thực tế nên dùng JUnit Jupiter:

- `@Test`: một test method.
- `@BeforeEach`: fixture mới trước mỗi invocation.
- `assertEquals(expected,actual)`, `assertTrue/False`: giá trị.
- `assertThrows(Expected.class, executable)`: exception type.
- `assertAll(...)`: assertions liên quan.
- `@ParameterizedTest` và `@ValueSource`/`@CsvSource`: nhiều test cases.
- `assertIterableEquals`: các iterable theo thứ tự.

JUnit không thuộc thư viện chuẩn JDK. Maven cần dependency phù hợp.

### 19.1. Project layout

~~~text
account-junit/
├── pom.xml
└── src/
    ├── main/java/example/Account.java
    └── test/java/example/AccountTest.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>account-junit</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version 5.10.2 là bản pin minh họa để build có thể tái lập, không khẳng định “mới nhất” năm hiện tại. Khi Maven chưa có dependencies trong cache cần kết nối Maven repositories ở lần build đầu.

**`src/main/java/example/Account.java`:**

~~~java
package example;

public final class Account {
    private long balance;

    public Account(long opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("opening");
        }
        balance = opening;
    }

    public long balance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        balance = Math.addExact(balance, amount);
    }

    public void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("amount");
        }
        balance -= amount;
    }
}
~~~

**`src/test/java/example/AccountTest.java`:**

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.*;

class AccountTest {
    private Account account;

    @BeforeEach
    void setUp() {
        account = new Account(100);
    }

    @Test
    void constructorInitializesCorrectly() {
        assertEquals(100, account.balance());
        assertThrows(IllegalArgumentException.class,
                () -> new Account(-1));
    }

    @Test
    void updatesChangeBalance() {
        account.deposit(50);
        assertEquals(150, account.balance());
        account.withdraw(25);
        assertEquals(125, account.balance());
    }

    @ParameterizedTest
    @ValueSource(longs = {0, -1, Long.MIN_VALUE})
    void invalidDepositsPreserveBalance(long amount) {
        long before = account.balance();
        assertThrows(IllegalArgumentException.class,
                () -> account.deposit(amount));
        assertEquals(before, account.balance());
    }

    @Test
    void withdrawalBeyondBalanceIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> account.withdraw(101));
        assertEquals(100, account.balance());
    }

    @Test
    void overflowPreservesPreviousBalance() {
        Account large = new Account(Long.MAX_VALUE - 1);
        assertThrows(ArithmeticException.class,
                () -> large.deposit(2));
        assertEquals(Long.MAX_VALUE - 1, large.balance());
    }

    @Test
    void exactWithdrawalReachesZero() {
        account.withdraw(100);
        assertAll(
                () -> assertEquals(0, account.balance()),
                () -> assertThrows(IllegalArgumentException.class,
                        () -> account.withdraw(1)));
    }
}
~~~

### 19.2. Chạy JUnit bằng Maven

Đứng trong `account-junit`:

~~~bash
mvn test
~~~

Maven build và chạy **8 invocations**: năm methods `@Test`, cộng ba invocations của một `@ParameterizedTest`. JUnit `@BeforeEach` tạo Account(100) mới cho từng invocation.

Output chi tiết Maven/Surefire phụ thuộc version và hệ thống, nên không cố định stdout console của Maven. Kỳ vọng build **PASS**, tests không fail. Nếu thiếu Maven/dependency network, đó là vấn đề môi trường, không thể giải quyết chỉ bằng `javac` JDK.

### 19.3. Assertion đúng loại

`assertThrows(IllegalArgumentException.class, action)` chấp nhận IllegalArgumentException và các subclasses. Nếu chỉ kiểm RuntimeException, lỗi NullPointerException không liên quan có thể bị nhận nhầm như expected. Chọn type cụ thể theo contract. Nếu yêu cầu chính xác loại, JUnit có `assertThrowsExactly` trong phiên bản phù hợp.

## 20. Unit test, integration test và external state

Một unit test cho Account/Line nên không phụ thuộc:
- DB production và production data;
- network hoặc payment/email service thật;
- filesystem shared path chưa cleanup;
- `LocalDate.now()` và timezone khác giữa máy;
- `Math.random()` không seed;
- thread scheduling chờ bằng `Thread.sleep`;
- `HashMap` iteration order không có contract;
- GC và finalizer timing.

Nếu test thực sự cần DB/service, phân loại thành integration test, dùng sandbox/test DB và cleanup rõ. Thay external dependency trong unit tests bằng fake/stub hoặc thiết kế injection.

## 21. Mutation testing: assertions có bắt bug thật không?

Một suite có thể đạt line coverage cao mà vẫn không phát hiện lỗi. Hãy tự tưởng tượng người khác “mutate” code:

- Đổi `amount > balance` thành `amount >= balance`: test withdraw đúng bằng balance phải fail.
- Đổi `quantity < 1` thành `quantity < 0`: test quantity=0 phải fail.
- Xóa `balance -= amount`: state assertion phải fail.
- Đổi `Math.addExact` thành `+`: overflow test phải fail.
- Bỏ `List.copyOf`: defensive-copy test phải fail.
- Gọi notifier trước validation: fake test phải fail.
- Đổi `day.isBefore(end)` thành inclusive end: boundary test phải fail.

Nếu test chỉ “gọi code” mà không fail với các lỗi này, hãy làm assertions mạnh hơn. Các tools mutation-testing như PIT có thể giúp ở dự án có build system; không phải requirement của bài Java core.

## 22. Các mẫu kiểm thử sai cần tránh

| Anti-pattern | Hậu quả | Thay bằng |
| --- | --- | --- |
| Chỉ happy path | Bỏ qua edge/error | Ma trận bốn nhóm |
| Call method không assert | False PASS | Assert state/result |
| `catch(Exception)` rồi PASS | Che unexpected NPE | Exact contract type |
| Không fail nếu không throw | Invalid accepted vẫn PASS | `assertThrows`/helper |
| Java `assert` không -ea | Test có thể không chạy | JUnit/helper |
| `==` cho String content | Nhầm identity/value | `equals` |
| Chỉ check exception | Partial state mutation lọt | Check state sau error |
| Dùng static fixture chung | Test-order dependence | Fresh per test |
| `LocalDate.now()` | Flaky qua ngày/timezone | Fixed input date/Clock |
| HashMap order assertion | Nondeterminism | Map equality/keys |
| `Thread.sleep(100)` | Race/flaky | Test scheduler/latch |
| Real network trong unit test | Chậm/flaky/tác động ngoài | Fake/stub |
| Hardcode JDK error message | Brittle | Check type/code contract |
| Không thử min/max | Off-by-one | Boundary-value analysis |
| Không thử overflow | Silent wrap | Exact math tests |
| Expose backing ArrayList | External mutation | Defensive-copy test |
| Reflect vào private methods | Test coupling | Public behavior |
| Chỉ nhìn coverage % | Chưa kiểm correctness | Mutation/invariants |

## 23. Checklist thực hành

- [ ] Mọi constructor/factory được thử valid/default/invalid?
- [ ] Các invariant của lớp viết rõ trước khi chọn cases?
- [ ] Assert trạng thái ngay sau khởi tạo?
- [ ] Update test có before/after và các fields không đổi?
- [ ] Invalid update có exception **và** state unchanged?
- [ ] Boundary inclusive/exclusive có test min-1/min/min+1, max-1/max/max+1?
- [ ] Null, blank, empty, length và Unicode policy được hiểu đúng?
- [ ] Overflow/precision được kiểm nếu domain có tiền/số lớn?
- [ ] Có sequence/state transition tests?
- [ ] Có defensive-copy tests cho mutable input?
- [ ] Có table-driven/property cases?
- [ ] Assertions chắc chắn chạy, không dựa `assert` disable?
- [ ] Test fixtures độc lập, không ảnh hưởng chạy lại/đảo thứ tự?
- [ ] Có fake để kiểm external side effects?
- [ ] Tests deterministic về clock/timezone/random/order?
- [ ] Phân biệt unit vs integration đúng không?
- [ ] Có test bảo vệ bug đã từng xuất hiện?
- [ ] JUnit/Maven dependencies đã khai đầy đủ?
- [ ] Assertions có khả năng bắt những mutations phổ biến?
- [ ] Code có thể compile/chạy trên JDK 17+ đúng filename?

## 24. Bài tập có đáp án

**1.** Age cho phép [0,150], chọn sáu ranh giới?  
**Đáp án:** -1,0,1,149,150,151.

**2.** Account balance=100, withdraw(100) và withdraw(101)?  
**Đáp án:** 100 hợp lệ, balance=0; 101 throw và state không đổi trên account ban đầu 100.

**3.** `catch(RuntimeException)` có đủ kiểm invalid input?  
**Đáp án:** Không, có thể che bug NPE hay sai exception type.

**4.** Method đổi quantity trước khi validate price; invalid price throw. Test?  
**Đáp án:** Assert exception và cả quantity/price cũ không đổi.

**5.** List constructor chỉ gán reference input. Test nào bắt lỗi?  
**Đáp án:** Sửa input list sau constructor rồi kiểm object không đổi nếu contract snapshot.

**6.** Subscription [start,end) ở ngày end còn active?  
**Đáp án:** Không; thử trước start, start, trước end, end.

**7.** `Long.MAX_VALUE * 2` cho total money?  
**Đáp án:** Dùng Math.multiplyExact và kỳ vọng ArithmeticException theo contract.

**8.** Test chỉ fail sau test khác?  
**Đáp án:** Shared mutable state; tạo fixture mới mỗi case.

**9.** `@ParameterizedTest` nhận ba inputs chạy mấy lần?  
**Đáp án:** Ba invocations.

**10.** Registration invalid throw nhưng notifier nhận thêm message, test PASS?  
**Đáp án:** Không; external side effect đã xảy ra sai.

**11.** Java `assert` chạy mặc định ở `java App`?  
**Đáp án:** Không; cần `-ea` hoặc JUnit/helper.

**12.** Hai String khác object nhưng cùng content so `==`?  
**Đáp án:** Không bảo đảm true; dùng equals.

**13.** Quantity [1,100], thử sát ranh giới?  
**Đáp án:** 0,1,2,99,100,101.

**14.** Quantity đổi từ 2→3, total cũ vẫn 200?  
**Đáp án:** Bug nếu price=100; test total phải thành 300.

**15.** `Thread.sleep(100)` bảo đảm async done?  
**Đáp án:** Không; dùng synchronization/test clock/scheduler phù hợp.

**16.** Property loop price=0..20 và quantity=0..20?  
**Đáp án:** 441 cases.

**17.** Có phải dùng reflection để test private method?  
**Đáp án:** Không; ưu tiên observable contract qua public methods.

**18.** Line coverage 100% chứng minh class đúng?  
**Đáp án:** Không; còn cần assertions và boundary/error scenarios.

## 25. Tài liệu tham khảo

- [JLS 17 `8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor và khởi tạo.
- [JLS 17 `11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): throw/catch và exception semantics.
- [JLS 17 `14.10 — assert Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.10): điều kiện chạy Java assertions.
- [JLS 17 `15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): evaluation/assignments.
- [Java SE 17 Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): null input checks.
- [Java SE 17 Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)) và [multiplyExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): overflow detection.
- [Java SE 17 List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable collection copies.
- [Java SE 17 LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): deterministic dates.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter annotations/assertions, lifecycle và parameterized tests.
- [JUnit Jupiter 5.10.2 Assertions API](https://junit.org/junit5/docs/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): `assertEquals`/`assertThrows`/`assertAll`.
- [JUnit Jupiter 5.10.2 ParameterizedTest API](https://junit.org/junit5/docs/5.10.2/api/org.junit.jupiter.params/org/junit/jupiter/params/ParameterizedTest.html): parameterized invocations.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): chạy test suites.

## Tổng kết

Đối với một lớp Java có trạng thái, bài test tốt phải trả lời:

- **Khởi tạo:** Object mới có đúng fields, defaults, invariants, validation không?
- **Cập nhật:** Method thành công đổi đúng state; những gì không liên quan vẫn giữ nguyên?
- **Biên:** Có off-by-one, overflow, ranh giới thời gian hoặc empty/null corner case?
- **Lỗi:** Exception có đúng contract, có để lại partial mutation hoặc side effect không?

Hãy tổ chức test bằng **Arrange–Act–Assert**, chọn ranh giới từ spec, dùng fixtures độc lập, và kiểm giá trị/state/side effect chứ không chỉ “không throw”. Dùng JUnit 5 để tổ chức dự án thật; dùng helper JDK 17 cho các chương trình học độc lập. Đặt mục tiêu test có thể phát hiện **một implementation sai**, chứ không chỉ tăng coverage.
