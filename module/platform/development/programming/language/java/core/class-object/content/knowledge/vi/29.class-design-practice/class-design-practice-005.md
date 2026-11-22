# Xây dựng lớp tài khoản với tạo mới, nạp tiền và rút tiền — Java 17+

Bài thực hành này xây dựng một lớp `BankAccount` có thể **tạo mới tài khoản**, **nạp tiền**, **rút tiền** và **xem số dư**. Đây là bài tập hướng đối tượng về **đóng gói dữ liệu**, **constructor**, **instance methods**, **invariant**, **exception handling** và **kiểm thử**, không phải ứng dụng ngân hàng dùng trong sản xuất.

Các quy tắc của ví dụ:

- Mỗi tài khoản có mã số và tên chủ sở hữu không rỗng, không thay đổi sau khởi tạo.
- Mỗi tài khoản có số dư riêng, lưu bằng `long` theo đơn vị **cents** của một loại tiền giả định có hai chữ số thập phân.
- Số dư ban đầu không được âm; tài khoản có thể mở với số dư bằng 0.
- Nạp/rút phải có số tiền dương.
- Không được rút quá số dư.
- Không để cộng tiền bị overflow.
- Nếu thao tác thất bại, số dư phải giữ nguyên.
- Không có public setter cho balance; chỉ thay đổi qua các nghiệp vụ được kiểm tra.

**Môi trường:** Java 17+. Các ví dụ có filename, lệnh biên dịch/chạy và stdout dự kiến. Mọi chương trình sử dụng lớp BankAccount chính đều biên dịch cùng file `BankAccount.java` được trình bày ở phần 5. Ví dụ độc lập được ghi rõ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định trường dữ liệu và hành vi của tài khoản.
2. Viết constructor bảo vệ dữ liệu đầu vào.
3. Sử dụng `private`, `final`, `this` và methods theo đúng ngữ nghĩa.
4. Viết `deposit`/`withdraw` và giữ invariant `balance >= 0`.
5. Phân biệt lỗi invalid amount, thiếu số dư và overflow.
6. Hiểu exception safety: kiểm tra trước, cập nhật sau.
7. Biết vì sao không dùng `double` tùy tiện để lưu tiền.
8. Test các trường hợp thành công, boundary và thất bại.
9. Phân biệt hai tài khoản với hai references tới cùng tài khoản.
10. Hiểu mức độ bảo vệ của `synchronized` và giới hạn của nó.
11. Nêu những yêu cầu thêm cho ứng dụng thực như ledger, persistence và transfer transactions.

## 2. Phân tích từ yêu cầu thành class

Giả sử user story: “Tôi muốn mở tài khoản bằng mã, tên, số dư đầu; nạp thêm một khoản tiền, rút một khoản khi đủ số dư và tra cứu số dư còn lại.”

| Yêu cầu | Thành phần | Điều kiện |
| --- | --- | --- |
| Mã | `accountNumber` | Không null/blank |
| Chủ | `ownerName` | Không null/blank |
| Số dư | `balanceCents` | Không âm |
| Mở tài khoản | Constructor | Kiểm tra toàn bộ input |
| Nạp | `deposit(amount)` | Amount > 0, không overflow |
| Rút | `withdraw(amount)` | Amount > 0 và amount <= balance |
| Đọc số dư | `balanceCents()` | Không sửa state |
| Hiển thị | `balanceText()` | Định dạng cents thành chuỗi decimal |

Định nghĩa **invariant** của class: các điều kiện mà mọi đối tượng được xây dựng thành công và mọi public operation hợp lệ đều phải bảo vệ. Ở đây, tài khoản không có tên/mã blank và balance không âm.

## 3. Vì sao dùng class và đóng gói fields?

Nếu chỉ khai báo:

~~~java
String id = "ACC-001";
String name = "Mai";
long balance = 10_000;
~~~

người gọi có thể viết `balance = -500` mà không qua kiểm tra.

Một class có fields private và methods diễn đạt nghiệp vụ:

~~~java
class BankAccount {
    private long balanceCents;

    void deposit(long cents) {
        // kiểm tra trước khi cộng
    }

    void withdraw(long cents) {
        // kiểm tra trước khi trừ
    }
}
~~~

Đây là **encapsulation**: đối tượng sở hữu số dư và là nơi duy nhất kiểm soát thay đổi. Không expose `public long balance` và không tạo `setBalance` tùy tiện.

Mã số và tên chủ sở hữu được dùng như metadata không đổi trong bài này, nên các fields đó `private final`. Balance phải thay đổi theo nghiệp vụ, nên private nhưng không final.

## 4. Vì sao ví dụ lưu tiền bằng `long` cents?

`double` biểu diễn số theo nhị phân nên không giữ chính xác mọi giá trị thập phân. Ví dụ `0.1 + 0.2` có thể thành `0.30000000000000004`.

Với một loại tiền có hai chữ số thập phân, lưu bằng cents:
- 100.00 → 10.000 cents.
- 12.50 → 1.250 cents.
- 4.00 → 400 cents.

Phép cộng/trừ integer là chính xác **trong miền giá trị**, nhưng `long` vẫn có thể overflow. `Math.addExact` giúp phát hiện overflow thay vì âm thầm wrap.

**Lưu ý:** Đây là quy ước của bài học, không đúng với mọi loại tiền có số chữ số thập phân khác nhau. Với domain thực, cần currency/scale/rounding policies; `BigDecimal` là một lựa chọn phù hợp cho decimal operations.

## 5. Lớp hoàn chỉnh: `BankAccount.java`

Tạo file **`BankAccount.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class BankAccount {
    private final String accountNumber;
    private final String ownerName;
    private long balanceCents;

    public BankAccount(
            String accountNumber,
            String ownerName,
            long openingCents) {
        this.accountNumber =
                requiredText(accountNumber, "accountNumber");
        this.ownerName =
                requiredText(ownerName, "ownerName");

        if (openingCents < 0) {
            throw new IllegalArgumentException(
                    "openingCents must not be negative");
        }
        this.balanceCents = openingCents;
    }

    private static String requiredText(
            String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return normalized;
    }

    private static void requirePositive(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException(
                    "amountCents must be positive");
        }
    }

    public String accountNumber() {
        return accountNumber;
    }

    public String ownerName() {
        return ownerName;
    }

    public synchronized long balanceCents() {
        return balanceCents;
    }

    public synchronized String balanceText() {
        return BigDecimal.valueOf(balanceCents, 2)
                .toPlainString();
    }

    public synchronized void deposit(long amountCents) {
        requirePositive(amountCents);
        long next = Math.addExact(
                balanceCents, amountCents);
        balanceCents = next;
    }

    public synchronized void withdraw(long amountCents) {
        requirePositive(amountCents);
        if (amountCents > balanceCents) {
            throw new InsufficientFundsException(
                    "insufficient funds");
        }
        balanceCents -= amountCents;
    }

    public static final class InsufficientFundsException
            extends RuntimeException {
        public InsufficientFundsException(String message) {
            super(message);
        }
    }
}
~~~

### Vì sao implementation này giữ invariant?

- `accountNumber` và `ownerName` được validate rồi mới gán; `strip` xóa khoảng trắng ở hai đầu.
- `openingCents < 0` ném exception; không trả về instance xây dựng thành công với số dư âm.
- `balanceCents` là field private nên caller không bypass được deposit/withdraw.
- `deposit` kiểm tra amount dương, tính `next` bằng `Math.addExact` rồi **mới gán field**.
- `withdraw` kiểm tra amount dương và có đủ tiền **trước khi trừ**.
- `synchronized` tuần tự hóa các calls đọc/ghi số dư trên cùng instance khi mọi access đi qua các methods này.
- Exception thiếu tiền được phân loại riêng để caller bắt lỗi nghiệp vụ cụ thể.

`BigDecimal.valueOf(balanceCents, 2).toPlainString()` chỉ dùng cho hiển thị; trạng thái lưu vẫn là long cents.

## 6. Chương trình chạy: mở tài khoản, nạp và rút

Tạo **`AccountDemo.java`**:

~~~java
public class AccountDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(
                " ACC-001 ", " Mai ", 10_000);

        System.out.println("account=" +
                account.accountNumber());
        System.out.println("owner=" +
                account.ownerName());
        System.out.println("opening=" +
                account.balanceText());

        account.deposit(1_250);
        System.out.println("after deposit=" +
                account.balanceText());

        account.withdraw(400);
        System.out.println("after withdraw=" +
                account.balanceText());

        try {
            account.withdraw(99_999);
        } catch (BankAccount.InsufficientFundsException ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("remaining=" +
                account.balanceText());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountDemo.java
java AccountDemo
~~~

Stdout:

~~~text
account=ACC-001
owner=Mai
opening=100.00
after deposit=112.50
after withdraw=108.50
error=insufficient funds
remaining=108.50
~~~

Phép tính: 10.000 + 1.250 - 400 = 10.850 cents, tương ứng 108.50. Lần rút 99.999 cents bị từ chối **trước khi thay balance**, nên số dư giữ nguyên.

## 7. Constructor và từ khóa `this`

Constructor mang tên lớp và **không có kiểu trả về**:

~~~java
public BankAccount(
        String accountNumber,
        String ownerName,
        long openingCents) {
    // ...
}
~~~

`this.accountNumber` là field của đối tượng hiện tại; `accountNumber` trong argument của `requiredText` là parameter cùng tên.

Ở call site:

~~~java
BankAccount account =
        new BankAccount("A", "An", 0);
~~~

Nếu constructor hoàn tất bình thường, `new` trả reference tới một tài khoản hợp lệ. Nếu constructor ném exception, biểu thức không trả về một tài khoản đã tạo thành công để gán cho caller.

Không nên publish `this` vào global registry trong khi chưa validate xong: code khác có thể quan sát state khởi tạo dở dang. Không dùng static balance vì static field sẽ được chia sẻ giữa mọi instances.

## 8. Chương trình chạy: constructor rejects invalid inputs

Tạo **`AccountCreationErrorsDemo.java`**:

~~~java
public class AccountCreationErrorsDemo {
    public static void main(String[] args) {
        try {
            new BankAccount("   ", "Mai", 100);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank id rejected");
        }

        try {
            new BankAccount("A", "Mai", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative opening rejected");
        }

        try {
            new BankAccount("A", null, 0);
        } catch (NullPointerException ex) {
            System.out.println("null owner rejected");
        }

        BankAccount valid =
                new BankAccount("A", "Mai", 0);
        System.out.println("balance=" +
                valid.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountCreationErrorsDemo.java
java AccountCreationErrorsDemo
~~~

Stdout:

~~~text
blank id rejected
negative opening rejected
null owner rejected
balance=0
~~~

Null policy và blank policy khác nhau: `Objects.requireNonNull` ném NullPointerException, `strip().isEmpty()` phát hiện blank rồi ném IllegalArgumentException.

## 9. Deposit: kiểm tra trước, cộng sau

Trong lớp chính:

~~~java
public synchronized void deposit(long amountCents) {
    requirePositive(amountCents);
    long next = Math.addExact(balanceCents, amountCents);
    balanceCents = next;
}
~~~

Ba điều cần nhớ:
1. Amount phải dương.
2. Phép cộng phải representable bằng `long`.
3. Chỉ gán state sau khi cả hai điều kiện được thỏa.

Không dùng `deposit(-100)` thay cho rút tiền, vì như thế bỏ qua kiểm tra thiếu số dư ở `withdraw`.

## 10. Chương trình chạy: deposit invalid và overflow

Tạo **`DepositFailuresDemo.java`**:

~~~java
public class DepositFailuresDemo {
    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 1_000);

        try {
            account.deposit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero rejected");
        }

        try {
            account.deposit(-20);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative rejected");
        }

        System.out.println("unchanged=" +
                account.balanceCents());

        BankAccount max = new BankAccount(
                "MAX", "Mai", Long.MAX_VALUE);
        try {
            max.deposit(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow rejected");
        }
        System.out.println("max unchanged=" +
                (max.balanceCents() == Long.MAX_VALUE));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java DepositFailuresDemo.java
java DepositFailuresDemo
~~~

Stdout:

~~~text
zero rejected
negative rejected
unchanged=1000
overflow rejected
max unchanged=true
~~~

`Math.addExact` ném ArithmeticException trước khi assignment. Một phép cộng bình thường với long có thể overflow và wrap, nên không đủ để bảo vệ tiền.

## 11. Withdraw: kiểm tra đủ tiền trước khi trừ

Trong lớp chính:

~~~java
public synchronized void withdraw(long amountCents) {
    requirePositive(amountCents);
    if (amountCents > balanceCents) {
        throw new InsufficientFundsException(
                "insufficient funds");
    }
    balanceCents -= amountCents;
}
~~~

Nếu balance không âm, amount dương và amount <= balance, phép trừ tạo ra balance không âm. **Rút đúng toàn bộ số dư** được phép, đưa balance về 0.

Sai:

~~~java
// balanceCents -= amountCents;
// if (balanceCents < 0) {
//     throw new IllegalArgumentException("insufficient");
// }
~~~

Vì state bị sửa **trước khi throw**, để đối tượng ở trạng thái invalid nếu không rollback đúng.

## 12. Chương trình chạy: rút hết và lỗi thiếu tiền

Tạo **`WithdrawFailuresDemo.java`**:

~~~java
public class WithdrawFailuresDemo {
    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 500);

        account.withdraw(500);
        System.out.println("after full withdraw=" +
                account.balanceCents());

        try {
            account.withdraw(1);
        } catch (BankAccount.InsufficientFundsException ex) {
            System.out.println("insufficient");
        }

        try {
            account.withdraw(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative rejected");
        }

        System.out.println("final=" +
                account.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java WithdrawFailuresDemo.java
java WithdrawFailuresDemo
~~~

Stdout:

~~~text
after full withdraw=0
insufficient
negative rejected
final=0
~~~

Tất cả failures xảy ra trước phép trừ. Đó là **exception safety** mà lớp bảo vệ.

## 13. Exceptions và xử lý lỗi ở caller

| Điều kiện | Lỗi trong thiết kế |
| --- | --- |
| Mã/chủ null | `NullPointerException` |
| Mã/chủ blank | `IllegalArgumentException` |
| Opening balance âm | `IllegalArgumentException` |
| Deposit/withdraw <=0 | `IllegalArgumentException` |
| Withdraw vượt balance | `InsufficientFundsException` |
| Deposit overflow | `ArithmeticException` |

Custom exception giúp phân biệt **invalid input** với **insufficient funds**:

~~~java
try {
    account.withdraw(amountCents);
    System.out.println("withdraw successful");
} catch (BankAccount.InsufficientFundsException ex) {
    System.out.println("not enough balance");
} catch (IllegalArgumentException ex) {
    System.out.println("invalid amount");
}
~~~

Đây là snippet cho caller/controller, không phải chương trình runnable độc lập.

Exception messages phục vụ chẩn đoán; đừng parse message text như protocol. Trong hệ thống thật nên dùng error codes/structured responses và không ghi dữ liệu nhạy cảm vào logs.

## 14. “Validate trước, commit sau” là một thói quen quan trọng

Ta tách:
- **Check:** input có hợp lệ không?
- **Compute:** balance candidate có representable không?
- **Commit:** gán state mới một lần sau các checks.

Với deposit:
- Check positive amount.
- Compute bằng Math.addExact; nếu fail chưa mutate.
- Assign balance.

Với withdraw:
- Check positive amount.
- Check sufficient funds.
- Trừ balance.

Nếu một public method fail, balance giữ nguyên; đó là contract của bản hiện tại.

Nếu sau này còn thêm transaction history hoặc database writes, chỉ một assignment không còn đủ. Việc cập nhật balance và ledger cần transaction boundary riêng.

## 15. Bộ kiểm thử không dùng thư viện ngoài

Tạo **`BankAccountTest.java`**:

~~~java
public class BankAccountTest {
    private static int checks;

    static void check(boolean ok, String label) {
        checks++;
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static void expect(
            Class<? extends Throwable> type,
            Runnable action) {
        checks++;
        try {
            action.run();
        } catch (Throwable caught) {
            if (type.isInstance(caught)) {
                return;
            }
            throw new AssertionError(
                    "unexpected exception: " + caught, caught);
        }
        throw new AssertionError(
                "missing " + type.getSimpleName());
    }

    public static void main(String[] args) {
        BankAccount a =
                new BankAccount(" A ", " Mai ", 1_000);

        check(a.accountNumber().equals("A"), "number");
        check(a.ownerName().equals("Mai"), "owner");
        check(a.balanceCents() == 1_000, "opening");

        a.deposit(250);
        check(a.balanceCents() == 1_250, "deposit");

        a.withdraw(200);
        check(a.balanceCents() == 1_050, "withdraw");

        expect(IllegalArgumentException.class,
                () -> a.deposit(0));
        expect(IllegalArgumentException.class,
                () -> a.withdraw(-1));
        expect(BankAccount.InsufficientFundsException.class,
                () -> a.withdraw(2_000));
        check(a.balanceCents() == 1_050,
                "unchanged on failures");

        expect(IllegalArgumentException.class,
                () -> new BankAccount(" ", "Mai", 0));
        expect(NullPointerException.class,
                () -> new BankAccount("A", null, 0));
        expect(IllegalArgumentException.class,
                () -> new BankAccount("A", "Mai", -1));

        BankAccount max =
                new BankAccount("MAX", "Mai", Long.MAX_VALUE);
        expect(ArithmeticException.class,
                () -> max.deposit(1));
        check(max.balanceCents() == Long.MAX_VALUE,
                "unchanged on overflow");

        BankAccount empty =
                new BankAccount("EMPTY", "An", 500);
        empty.withdraw(500);
        check(empty.balanceCents() == 0, "withdraw all");

        System.out.println("PASS " + checks + " checks");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java BankAccountTest.java
java BankAccountTest
~~~

Stdout:

~~~text
PASS 15 checks
~~~

Cách đếm: 3 checks ban đầu + 1 nạp + 1 rút + 3 expected failures + 1 unchanged + 3 invalid constructors + 1 overflow expected + 1 overflow unchanged + 1 withdraw all = 15.

Bắt `Throwable` trong helper là cách giới hạn cho **test harness** nhằm báo exception khác mong đợi. Trong production tránh catch Throwable bừa vì nó gồm cả `Error`.

## 16. Các trường hợp biên cần kiểm tra

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Opening = 0 | Tạo tài khoản thành công |
| Opening = -1 | Reject |
| Number = blank | Reject |
| Owner = null | Reject |
| Deposit = 1 | Tăng 1 cent |
| Deposit = 0 hoặc âm | Reject và giữ balance |
| Deposit dẫn tới overflow | Reject và giữ balance |
| Withdraw = 1 khi đủ | Giảm 1 cent |
| Withdraw = balance | Balance về 0 |
| Withdraw > balance | Thiếu tiền, balance unchanged |
| Withdraw = 0 hoặc âm | Reject |
| Hai account objects | Số dư riêng |
| Hai aliases cùng object | Cùng thấy một số dư |

Không chỉ kiểm thử happy path. Một class giữ số dư sai sau thao tác bị từ chối là một lỗi nghiêm trọng dù các phép cộng/trừ thông thường chạy đúng.

## 17. Object identity và reference alias

~~~java
BankAccount first =
        new BankAccount("A", "Mai", 100);
BankAccount alias = first;
BankAccount second =
        new BankAccount("A", "Mai", 100);
~~~

- `first == alias` → true, vì là cùng instance.
- `first == second` → false, vì có hai `new` riêng.
- Nạp qua `alias` thay đổi trạng thái mà `first` đọc được.
- `second` không thay đổi.

### Chương trình chạy

Tạo **`AccountIdentityDemo.java`**:

~~~java
public class AccountIdentityDemo {
    public static void main(String[] args) {
        BankAccount first =
                new BankAccount("A", "Mai", 100);
        BankAccount alias = first;
        BankAccount second =
                new BankAccount("A", "Mai", 100);

        alias.deposit(50);

        System.out.println("alias=" + (first == alias));
        System.out.println("same as second=" +
                (first == second));
        System.out.println("first=" + first.balanceCents());
        System.out.println("second=" + second.balanceCents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java AccountIdentityDemo.java
java AccountIdentityDemo
~~~

Stdout:

~~~text
alias=true
same as second=false
first=150
second=100
~~~

Tài khoản là đối tượng có identity, không nên tự động override equals chỉ theo balance. Hai tài khoản cùng số dư không có nghĩa cùng entity.

## 18. Đồng thời: lý do dùng `synchronized`

Nạp tiền gồm nhiều bước read-modify-write. Nếu hai threads đọc balance cũ và cùng tính/gán balance mới mà không đồng bộ, có thể **mất một cập nhật**.

Các methods synchronized của BankAccount dùng monitor thuộc **mỗi instance**:
- Một thread thực hiện deposit/withdraw tại một thời điểm trên cùng account.
- Getter balance synchronized thấy state được bảo vệ bởi monitor đó.
- Không ngăn threads thao tác trên những accounts khác nhau.
- Không giải quyết giao dịch gồm nhiều accounts.

### Chương trình chạy với bốn workers

Tạo **`ConcurrentDepositsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentDepositsDemo {
    public static void main(String[] args) throws Exception {
        BankAccount account =
                new BankAccount("A", "Mai", 0);
        ExecutorService pool =
                Executors.newFixedThreadPool(4);
        List<Future<?>> jobs = new ArrayList<>();

        try {
            for (int worker = 0; worker < 4; worker++) {
                jobs.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        account.deposit(1);
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get();
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cents=" +
                account.balanceCents());
        System.out.println("money=" +
                account.balanceText());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java ConcurrentDepositsDemo.java
java ConcurrentDepositsDemo
~~~

Stdout:

~~~text
cents=4000
money=40.00
~~~

4 workers × 1.000 lần nạp × 1 cent = 4.000 cents. `Future.get()` đợi tasks hoàn tất và ném exception nếu task thất bại.

## 19. Đọc rồi rút không phải giao dịch nguyên tử

Ví dụ:

~~~java
if (account.balanceCents() >= 500) {
    account.withdraw(500);
}
~~~

Hai method calls là **hai critical sections riêng**. Một thread khác có thể rút sau getter nhưng trước withdraw; khi đó withdraw vẫn tự kiểm tra và ném InsufficientFundsException.

**Thiết kế đúng:** caller gọi withdraw và bắt lỗi; không giả định check-then-act ở ngoài account là atomic.

Tương tự:

~~~java
from.withdraw(amount);
to.deposit(amount);
~~~

không phải transfer transaction an toàn. Nếu credit thất bại sau debit, hai balances không nhất quán. Một transfer thực sự cần transaction semantics, lock ordering, rollback/persistence/recovery; nằm ngoài phạm vi bài tạo/nạp/rút một tài khoản.

## 20. Parse chuỗi tiền thành cents an toàn

Bản chính dùng long cents để rõ đơn vị. UI có thể nhận `"12.50"`, sau đó parse bằng BigDecimal và chuyển cents:

Tạo **`MoneyInputDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyInputDemo {
    static long toCents(String input) {
        return new BigDecimal(input.strip())
                .setScale(2, RoundingMode.UNNECESSARY)
                .movePointRight(2)
                .longValueExact();
    }

    public static void main(String[] args) {
        BankAccount account =
                new BankAccount("A", "Mai", 0);
        account.deposit(toCents("12.50"));
        account.withdraw(toCents("2.25"));

        System.out.println("balance=" +
                account.balanceText());

        try {
            toCents("0.001");
        } catch (ArithmeticException ex) {
            System.out.println("fraction rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BankAccount.java MoneyInputDemo.java
java MoneyInputDemo
~~~

Stdout:

~~~text
balance=10.25
fraction rejected
~~~

`setScale(2, RoundingMode.UNNECESSARY)` reject khi cần làm tròn; `longValueExact` reject non-integral/overflow conversion. Controller còn phải xử lý null, NumberFormatException và locale/currency policies.

## 21. BigDecimal làm state: một lựa chọn khác

Khi cần decimal arithmetic, có thể lưu `BigDecimal` nhưng phải định nghĩa scale/rounding. BigDecimal là immutable: `add`/`subtract` trả object mới.

Tạo **`DecimalAccountDemo.java`**, chương trình độc lập không cần BankAccount.java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class DecimalAccountDemo {
    static final class Account {
        private BigDecimal balance;

        Account(BigDecimal opening) {
            balance = normalized(opening);
            if (balance.signum() < 0) {
                throw new IllegalArgumentException("opening");
            }
        }

        private static BigDecimal normalized(BigDecimal raw) {
            Objects.requireNonNull(raw, "raw");
            try {
                return raw.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException("fraction", ex);
            }
        }

        void deposit(BigDecimal raw) {
            BigDecimal amount = normalized(raw);
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("amount");
            }
            balance = balance.add(amount);
        }

        void withdraw(BigDecimal raw) {
            BigDecimal amount = normalized(raw);
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("amount");
            }
            if (amount.compareTo(balance) > 0) {
                throw new IllegalArgumentException("insufficient");
            }
            balance = balance.subtract(amount);
        }

        BigDecimal balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account =
                new Account(new BigDecimal("100.00"));
        account.deposit(new BigDecimal("12.50"));
        account.withdraw(new BigDecimal("2.25"));

        System.out.println(account.balance().toPlainString());

        try {
            account.deposit(new BigDecimal("0.001"));
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DecimalAccountDemo.java
java DecimalAccountDemo
~~~

Stdout:

~~~text
110.25
fraction rejected
~~~

Ví dụ dùng hai decimal places và một thread. Không dùng `new BigDecimal(0.1)` cho literal decimal input nếu muốn chính xác theo chuỗi; ưu tiên `new BigDecimal("0.1")`.

## 22. Những mở rộng không nên làm vội

Một lớp tài khoản thật thường cần:
- Currency và minor unit rules cụ thể.
- Transaction history/ledger và audit events.
- ID uniqueness và persistence identity.
- Phân quyền cho deposit/withdraw.
- Hạn mức và business policies.
- Database transactions, optimistic locking, idempotency.
- Chuyển khoản có debit/credit atomic và recovery.
- Thông báo lỗi/localization, privacy/logging.
- Kiểm thử đa luồng, test persistence và test failures.

Nếu thêm list lịch sử ngay vào BankAccount, một operation phải cập nhật **balance lẫn history** nhất quán; nếu append history thất bại sau khi balance thay đổi, cần transaction/rollback strategy. Vì vậy bản bài học giữ đúng phạm vi **tạo/nạp/rút trong bộ nhớ**.

## 23. Anti-patterns và hướng sửa

| Lỗi | Tại sao sai | Hướng sửa |
| --- | --- | --- |
| `public long balance` | Bypass checks | Private field |
| `static long balance` | Shared balance giữa accounts | Instance field |
| `setBalance` public | Caller sửa tùy tiện | Domain methods |
| Constructor cho opening âm | Object invalid | Validate constructor |
| Nạp amount âm | Bỏ qua rule rút | Reject |
| Trừ tiền rồi mới check | State âm khi throw | Check trước |
| Không check overflow | Arithmetic wrap | Math.addExact |
| Dùng double cho tiền | Decimal precision issue | Long cents/BigDecimal |
| Bắt tất cả exception rồi ignore | Che lỗi | Catch cụ thể |
| Dùng balance để định nghĩa entity equals | Sai identity | Chọn ID/reference policy |
| Cho rằng synchronized đủ cho transfer | Partial failure | Transaction boundary |
| Không test invalid inputs | Invariant bug | Negative tests |
| In sensitive data vào logs | Privacy risk | Logging policy |

## 24. Bài tập có đáp án

**Bài 1.** Mở 20.000 cents, nạp 5.000, rút 3.000. Số dư? **Đáp án:** 22.000 cents = 220.00.

**Bài 2.** Mở 500, rút 501. Điều gì xảy ra? **Đáp án:** InsufficientFundsException, balance vẫn 500.

**Bài 3.** `deposit(0)` có làm đổi balance không? **Đáp án:** Không; IllegalArgumentException.

**Bài 4.** Mở Long.MAX_VALUE, `deposit(1)`? **Đáp án:** ArithmeticException, state không đổi.

**Bài 5.** Tạo a và b bằng hai lần `new BankAccount` có cùng dữ liệu. `a == b`? **Đáp án:** False.

**Bài 6.** `BankAccount alias = a; alias.deposit(100);` thì `a.balanceCents()`? **Đáp án:** Tăng 100 vì cùng object.

**Bài 7.** Vì sao `private static long balance` sai? **Đáp án:** Static state thuộc class, không riêng từng instance.

**Bài 8.** Tại sao constructor phải kiểm tra opening balance? **Đáp án:** Không để một object invalid được tạo thành công.

**Bài 9.** `withdraw(balance)`? **Đáp án:** Hợp lệ nếu balance>0; sau đó bằng 0.

**Bài 10.** Tại sao `from.withdraw(x); to.deposit(x)` không phải transfer an toàn? **Đáp án:** Bước credit có thể fail sau debit, thiếu atomicity/rollback.

**Bài 11.** Vì sao `double` không thích hợp cho exact decimal money? **Đáp án:** Không biểu diễn chính xác mọi phân số thập phân.

**Bài 12.** Nếu gọi getter thấy đủ tiền rồi một thread khác rút trước, phương thức withdraw nên làm gì? **Đáp án:** Tự kiểm tra lại dưới lock và throw nếu thiếu.

## 25. Quy trình hoàn thành bài

1. Xác định fields và invariants.
2. Viết constructor kiểm tra null/blank/opening âm.
3. Dùng private fields và getters cần thiết.
4. Không expose setter cho balance.
5. Viết `deposit` positive-check → Math.addExact → assignment.
6. Viết `withdraw` positive-check → sufficient-check → subtraction.
7. Khai báo exception riêng cho insufficient funds.
8. Viết main tạo tài khoản, nạp/rút và in balance.
9. Test cả happy paths, zero/negative, thiếu tiền, overflow.
10. Đảm bảo state unchanged sau exception.
11. Cân nhắc synchronization cho cùng account instance.
12. Tách UI parsing khỏi domain class.
13. Thiết kế ledger/persistence/transfer ở tầng kiến trúc cao hơn khi cần.

## 26. Checklist cuối bài

- [ ] Tôi tạo được `BankAccount` bằng constructor.
- [ ] Tôi dùng `private` cho state và `final` cho fields cố định.
- [ ] Tôi hiểu `this.field` khác parameter cùng tên.
- [ ] Tôi không dùng static balance.
- [ ] Tôi reject mã/chủ null/blank.
- [ ] Tôi reject opening balance âm.
- [ ] Tôi không expose setBalance công khai.
- [ ] Tôi hiểu invariant balance>=0.
- [ ] Tôi viết deposit positive-only.
- [ ] Tôi dùng Math.addExact chống overflow.
- [ ] Tôi viết withdraw positive-only và đủ-số-dư.
- [ ] Tôi cho phép rút hết số dư.
- [ ] Tôi có exception riêng cho insufficient funds.
- [ ] Tôi không mutate balance trước khi validate.
- [ ] Tôi test state unchanged khi method fail.
- [ ] Tôi hiểu long cents chỉ áp dụng cho currency scale đã chọn.
- [ ] Tôi biết BigDecimal từ String và RoundingMode.UNNECESSARY.
- [ ] Tôi chạy được AccountDemo và BankAccountTest.
- [ ] Tôi phân biệt alias reference với new object.
- [ ] Tôi biết synchronized không tự làm transfer atomic.
- [ ] Tôi tách business logic khỏi input parsing/presentation.
- [ ] Tôi biết model này chưa thay được banking ledger production.

**Kết luận:** Lớp tài khoản là ví dụ điển hình của nguyên lý **đóng gói state và đặt invariant tại điểm cập nhật**. Constructor bảo đảm tài khoản bắt đầu hợp lệ; `deposit` và `withdraw` là những hành vi có kiểm soát; ngoại lệ không làm hỏng state; tests chứng minh cả success và failure. Trên Java 17+, kết hợp **private fields, validation, checked arithmetic, exception handling và synchronization có chủ đích** sẽ cho một mô hình tài khoản trong bộ nhớ rõ ràng, dễ mở rộng và dễ kiểm thử.
