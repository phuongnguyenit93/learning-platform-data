# Kết hợp tài khoản, giao dịch và chủ tài khoản bằng tham chiếu trong Java 17+

## 1. Bài toán thực hành: các đối tượng có quan hệ với nhau

Trong một ứng dụng quản lý tài khoản, ba khái niệm dễ nhận thấy là **chủ tài khoản** (`Customer` hoặc `AccountHolder`), **tài khoản** (`BankAccount`) và **giao dịch** (`Transaction`). Thay vì nhồi mọi thông tin vào một class khổng lồ, thiết kế hướng đối tượng biểu diễn chúng bằng **những đối tượng độc lập, được liên kết bằng references có kiểu**.

Ví dụ về mô hình khái niệm:

~~~text
 Customer C01 ("Lan")
       ^
       | owner
       |
 Account A100 ---------> Transaction TX1
       |                      |
       |                      +-- account ------> Account A100
       |
       +-- balance = 125.00

 Customer C01 ("Lan")
       ^
       | owner
 Account A200 ---------> Transaction TX2
~~~

Hai `Account` khác nhau có thể cùng tham chiếu **một đối tượng Customer**. Một `Transaction` có thể tham chiếu account mà nó tác động; với chuyển khoản, giao dịch có thể giữ **hai account references**: tài khoản gửi và tài khoản nhận. Đây là việc **liên kết objects**, không phải tự động tạo bản sao dữ liệu hay bản ghi cơ sở dữ liệu.

~~~java
final class Customer {
    final String id;
    final String name;

    Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }
}

final class BankAccount {
    final String accountNumber;
    final Customer owner;

    BankAccount(String accountNumber, Customer owner) {
        this.accountNumber = accountNumber;
        this.owner = owner;
    }
}
~~~

Hai declarations trên **hợp lệ**, chưa có `main`. Nếu tạo một Customer object rồi truyền reference đó vào hai constructor BankAccount, cả hai account cùng `owner == customer`. Java không nhân bản Customer khi truyền argument: object reference được **truyền theo giá trị**.

**Trọng tâm bài:** hiểu object graph, tính đồng nhất của object, quan hệ một–nhiều, nghiệp vụ giao dịch, invariant giữa objects, snapshot dữ liệu và ranh giới giữa mô hình trong bộ nhớ với ngân hàng thật.

Bài thuộc **Java core – class-object**, nhóm **Thiết kế và thực hành**, chủ đề **Kết hợp tài khoản, giao dịch và chủ tài khoản bằng tham chiếu**. Các chương trình độc lập dùng **Java 17+**, có tên file, lệnh `javac`/`java` và stdout xác định. Ví dụ mô phỏng tài chính chỉ phục vụ **học thiết kế hướng đối tượng**, không phải một core-banking system có xác thực, tính bền vững, audit chuẩn và tính nguyên tử phân tán.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân tích ba thực thể Customer, Account, Transaction và trách nhiệm của từng class.
2. Thể hiện quan hệ bằng **trường object reference** thay vì chỉ chuỗi diễn giải.
3. Giải thích khác biệt giữa **chung reference**, **cùng business ID**, và **tạo bản sao object**.
4. Hiểu Java truyền reference **theo giá trị**, không truyền object hoặc biến theo tham chiếu theo nghĩa C++.
5. Mô hình hóa một Customer sở hữu nhiều Accounts, Account có nhiều Transactions.
6. Chọn quan hệ **đơn hướng** hay **hai chiều** và biết cách duy trì tính nhất quán.
7. Xây dựng methods `deposit`, `withdraw`, `transfer` với kiểm tra điều kiện.
8. Biết dùng `BigDecimal` thay vì `double` cho tiền và giữ scale/currency theo policy.
9. Hiểu transaction tham chiếu live Account khác với transaction lưu snapshot.
10. Phòng tránh lộ mutable collections, mutable identity fields và aliasing ngoài ý muốn.
11. Phân biệt object identity `==` với business equality theo account ID.
12. Phân tích vòng tham chiếu, retention và garbage collection trong object graph.
13. Hiểu rằng mô phỏng chuyển khoản với hai lời gọi methods **không tự trở thành ACID database transaction**.
14. Nêu ranh giới giữa in-memory graph và cơ sở dữ liệu/ORM với foreign keys.
15. Thiết kế tests bao phủ quan hệ, số dư, lịch sử, lỗi nghiệp vụ và concurrency.
16. Tự xây dựng một chương trình tích hợp nhỏ có đầu ra kiểm chứng được.

## 3. Tách trách nhiệm đúng chỗ

| Đối tượng | Dữ liệu thường có | Trách nhiệm phù hợp | Không nên ôm |
| --- | --- | --- | --- |
| `Customer` | ID, tên, contact/profile | Nhận diện chủ tài khoản, cập nhật profile hợp lệ | Tự xử lý mọi transaction và database infrastructure |
| `BankAccount` | Account ID, owner reference, balance | Bảo vệ số dư, thực hiện thao tác được phép, cung cấp trạng thái | Lưu toàn bộ field profile như bản sao không kiểm soát |
| `Transaction` | Transaction ID, account references hoặc account IDs, amount, timestamp/status | Mô tả một nghiệp vụ hay một sự kiện đã ghi nhận | Tùy tiện sửa account balance chỉ qua constructor |
| `BankService` | Kho account, quy tắc nghiệp vụ | Điều phối transfer, validation, repository | Giấu những bất biến quan trọng trong UI |
| `LedgerEntry` | Account ID/reference, signed delta, balance snapshot | Ghi nhận một bút toán cụ thể | Làm “nguồn sự thật” nếu không có accounting design |

Đây là một **đề xuất phân chia trách nhiệm để học**, không có một bộ class names cố định bắt buộc mọi hệ thống phải dùng. Một ngân hàng thật thường có nhiều hơn một account holder, chủ sở hữu chung, roles, product types, fees, nhiều currency, ledger double-entry, approvals, event streams và lưu trữ bền vững.

**Nguyên tắc:** cho mỗi class một lý do thay đổi rõ ràng. Tham chiếu sang class khác khi cần liên kết dữ liệu hoặc hành vi, thay vì tạo “God object” chứa tất cả.

## 4. Reference thực chất liên kết cái gì?

Xét:

~~~java
Customer owner = new Customer("C01", "Lan");
BankAccount account = new BankAccount("A100", owner);
~~~

Đây là snippet hợp lệ nếu các class từ mục đầu nằm trong scope. Sau hai lệnh:

- Có **một Customer object** được tạo.
- Có **một BankAccount object** được tạo.
- Local variable `owner` giữ một reference tới Customer.
- Field `account.owner` giữ **một reference khác trỏ tới cùng Customer object**.
- Constructor không sao chép dữ liệu Customer; nó nhận và lưu một **giá trị reference**.

Trong Java, argument được **truyền theo giá trị**. Với parameter kiểu reference, giá trị được truyền là reference; callee có thể sửa object mutable thông qua reference, nhưng **gán lại parameter** không thể thay đổi reference nằm trong biến của caller.

Không nhầm việc “cùng object” với “cùng dữ liệu”: hai Customer objects có thể cùng ID và name nhưng vẫn là hai objects riêng, `a == b` là false.

## 5. Chương trình hoàn chỉnh 1 — transaction tham chiếu account, account tham chiếu owner

Tệp **`AccountReferencesDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id, String name) {
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

record Transaction(String id, Account account,
                   BigDecimal amount) {
}

public class AccountReferencesDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01", "Lan");
        Account savings = new Account("A100", lan);
        Transaction entry = new Transaction(
                "TX1", savings, new BigDecimal("25.00"));

        System.out.println("owner=" + savings.owner().name());
        System.out.println("account=" + entry.account().number());
        System.out.println("amount=" + entry.amount().toPlainString());
        System.out.println("same account="
                + (entry.account() == savings));
        System.out.println("same owner="
                + (entry.account().owner() == lan));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AccountReferencesDemo.java
java AccountReferencesDemo
~~~

**Stdout:**

~~~text
owner=Lan
account=A100
amount=25.00
same account=true
same owner=true
~~~

`Transaction.account()` trả chính reference đã được truyền vào. Gọi `entry.account().owner()` dẫn qua **hai cạnh tham chiếu** trong graph. Hai kiểm tra `==` đều true vì cùng object instance. Đây là mô hình mối liên hệ; bản thân Transaction record **không tự cộng 25.00 vào số dư**.

## 6. Một đối tượng chủ, nhiều tài khoản: aliasing

Một khách hàng có thể mở hai tài khoản. Nếu cả hai Account fields trỏ tới cùng Customer object, thay đổi **mutable profile** của Customer sẽ được cả hai accounts nhìn thấy, vì chúng **không giữ bản sao**.

~~~text
accountA.owner -----+
                    |
                    v
                Customer C01
                    ^
                    |
accountB.owner -----+
~~~

Điều này có thể là ưu điểm: đổi tên hiển thị một nơi, mọi account views đọc profile mới nhất. Nhưng cũng có thể là rủi ro: Transaction lịch sử cần lưu tên chủ tại thời điểm phát hành chứng từ; đọc profile live hôm nay không tái hiện đúng thông tin lúc đó.

**Quy tắc thiết kế:** khi cần **live shared entity**, giữ reference. Khi cần **historical immutable value**, lưu snapshot/ID theo hợp đồng riêng. Không dùng reference một cách vô thức cho cả hai nhu cầu.

## 7. Chương trình hoàn chỉnh 2 — cập nhật Customer được phản ánh qua hai Account

Tệp **`SharedOwnerDemo.java`**:

~~~java
final class Customer {
    private final String id;
    private String displayName;

    Customer(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    String displayName() {
        return displayName;
    }

    void rename(String next) {
        if (next == null || next.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        displayName = next;
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    Customer owner() {
        return owner;
    }
}

public class SharedOwnerDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "Lan");
        Account a = new Account("A100", customer);
        Account b = new Account("A200", customer);

        System.out.println("before="
                + a.owner().displayName() + "/"
                + b.owner().displayName());

        customer.rename("Mai");

        System.out.println("after="
                + a.owner().displayName() + "/"
                + b.owner().displayName());
        System.out.println("same owner="
                + (a.owner() == b.owner()));
        System.out.println("different accounts=" + (a != b));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SharedOwnerDemo.java
java SharedOwnerDemo
~~~

**Stdout:**

~~~text
before=Lan/Lan
after=Mai/Mai
same owner=true
different accounts=true
~~~

Các Accounts vẫn là hai objects khác nhau; Customer là một object được chia sẻ. Vì `displayName` có thể đổi, các views hiển thị tên mới. Field `id` giữ identity nghiệp vụ ổn định nhưng chưa được dùng để áp bất kỳ quy tắc cơ sở dữ liệu nào trong demo.

## 8. Java truyền tham chiếu theo giá trị, không thể thay reference biến caller bằng gán parameter

Một hiểu lầm thường gặp: “Object là truyền tham chiếu nên method có thể thay biến account bên ngoài”.

Ví dụ:

~~~java
static void replace(Account account) {
    account = new Account("A999", account.owner());
}
~~~

Đây là **snippet method** hợp lệ nếu Account đã có constructor và owner accessor. Việc gán lại parameter `account` chỉ thay **biến local của method**, không thay biến của caller.

Ngược lại, nếu `account` tham chiếu một object mutable và method gọi `account.deposit(...)`, thì nội dung object ấy có thể thay đổi và caller quan sát được.

Phân biệt ba hành động:
1. **Đọc field qua reference:** caller/callee cùng thấy giá trị liên quan tới object.
2. **Mutate referenced object:** thay state của object chung nếu API cho phép.
3. **Reassign reference variable:** chỉ thay biến tương ứng, không tự thay các alias khác.

## 9. Chương trình hoàn chỉnh 3 — reassign parameter không thay alias bên ngoài

Tệp **`ReferenceParameterDemo.java`**:

~~~java
final class Holder {
    int value;

    Holder(int value) {
        this.value = value;
    }
}

public class ReferenceParameterDemo {
    static void mutate(Holder item) {
        item.value = 7;
    }

    static void reassign(Holder item) {
        item = new Holder(99);
        System.out.println("inside=" + item.value);
    }

    public static void main(String[] args) {
        Holder original = new Holder(1);

        mutate(original);
        System.out.println("after mutate=" + original.value);

        reassign(original);
        System.out.println("after reassign=" + original.value);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

**Stdout:**

~~~text
after mutate=7
inside=99
after reassign=7
~~~

Ví dụ dùng Holder thay vì Account để cô lập semantics của Java. `mutate` thay object chung, còn `reassign` chỉ làm tên parameter trỏ object khác. Quy tắc tương tự với Customer, BankAccount và Transaction.

## 10. Quan hệ một–nhiều: chủ tài khoản giữ danh sách Accounts

Một Customer có thể liên quan nhiều accounts, nên có thể thiết kế:

~~~java
final class Customer {
    private final java.util.List<Account> accounts =
            new java.util.ArrayList<>();
}
~~~

Đây là **snippet class**, chỉ minh họa field. Nhưng để model nhất quán, cần quyết định ai có quyền thêm một Account:

- Customer tạo account qua factory method riêng?
- BankService tạo account, rồi register vào Customer?
- Một Account có bao giờ được chuyển sang Customer khác?
- Những Accounts trong `Customer.accounts` có thực sự có `account.owner() == customer` không?
- Có cho duplicate account numbers?
- Có hỗ trợ joint accounts không?

Với bài học, ta chọn policy đơn giản: Customer tạo Accounts của mình và giữ danh sách; mỗi Account có `owner` final. Đây là một **quan hệ một–nhiều một chủ** minh họa, chưa giải quyết joint ownership của ngân hàng thật.

## 11. Chương trình hoàn chỉnh 4 — Customer tạo và liệt kê accounts

Tệp **`CustomerAccountsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Customer {
    private final String id;
    private final List<Account> accounts = new ArrayList<>();

    Customer(String id) {
        this.id = id;
    }

    Account openAccount(String number) {
        if (number == null || number.isBlank()) {
            throw new IllegalArgumentException("number");
        }
        for (Account current : accounts) {
            if (current.number().equals(number)) {
                throw new IllegalArgumentException("duplicate account");
            }
        }

        Account result = new Account(number, this);
        accounts.add(result);
        return result;
    }

    List<Account> accounts() {
        return List.copyOf(accounts);
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

public class CustomerAccountsDemo {
    public static void main(String[] args) {
        Customer owner = new Customer("C01");
        Account checking = owner.openAccount("A100");
        Account saving = owner.openAccount("A200");

        System.out.println("accounts=" + owner.accounts().size());
        System.out.println("first=" + owner.accounts().get(0).number());
        System.out.println("second=" + saving.number());
        System.out.println("same owner="
                + (checking.owner() == saving.owner()));
        System.out.println("owner points back="
                + (saving.owner() == owner));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CustomerAccountsDemo.java
java CustomerAccountsDemo
~~~

**Stdout:**

~~~text
accounts=2
first=A100
second=A200
same owner=true
owner points back=true
~~~

`accounts()` trả `List.copyOf`: caller không được sửa cấu trúc danh sách qua accessor này. Tuy nhiên, đây là **shallow copy**: Account objects trong list vẫn là chính những references đã được lưu, không phải deep clones.

**Giới hạn của ví dụ:** duplicate check chỉ xét Accounts đã mở qua **Customer instance này**. Ngân hàng thật phải kiểm tra account-number uniqueness bằng registry/database với transaction constraints, không thể coi một danh sách ở Customer là authority toàn hệ thống.

## 12. Quan hệ đơn hướng hay hai chiều?

**Đơn hướng**: Account có `owner`, nhưng Customer không lưu `accounts`. Muốn tìm accounts của Customer có thể hỏi repository/service.

~~~text
Account ----owner----> Customer
~~~

**Hai chiều**: Customer có collection Accounts và mỗi Account cũng có owner.

~~~text
Customer ----accounts----> Account
    ^                        |
    +----------owner---------+
~~~

Thiết kế hai chiều giúp navigation thuận tiện, nhưng tạo **invariant quan hệ** phải giữ đúng:

> Nếu `account` nằm trong `customer.accounts()`, thì `account.owner() == customer` theo policy một chủ của model.

Nếu code cho phép `customerA.accounts.add(accountOwnedByB)`, graph không còn nhất quán. Đây không phải lỗi GC; đây là lỗi dữ liệu mô hình.

Chọn đơn hướng khi:
- Một phía hiếm khi cần navigation.
- Việc tìm collection do repository/query đảm nhận.
- Muốn giảm coupling và chi phí đồng bộ hai phía.

Chọn hai chiều khi:
- Cả hai hướng navigation có ý nghĩa domain.
- Có một service/factory duy nhất kiểm soát cập nhật quan hệ.
- Có test invariant rõ ràng.

## 13. Một quan hệ tham chiếu không tự tạo dữ liệu nghiệp vụ

Nếu một Transaction record chỉ có field `Account account` và `BigDecimal amount`, việc tạo record **không cộng/trừ số dư**:

~~~java
Transaction entry =
        new Transaction("TX1", account,
                new java.math.BigDecimal("10.00"));
~~~

Đây là snippet dựa vào declarations tương ứng. Nó chỉ tạo một object ghi nhận dữ liệu.

Để phát sinh giao dịch đúng nghĩa, phải có **business operation** thực hiện validation và cập nhật account/ledger theo một protocol:

1. Kiểm tra số tiền hợp lệ.
2. Kiểm tra account tồn tại và trạng thái cho phép thao tác.
3. Kiểm tra số dư/limits nếu rút tiền.
4. Áp dụng thay đổi số dư/ledger trong một transaction boundary thích hợp.
5. Ghi nhận record/entry có identity và timestamp/status theo yêu cầu.
6. Công bố result theo API.
7. Nếu có persistence, thực hiện commit/rollback hoặc recovery đúng nghĩa.

Trong ví dụ memory nhỏ, ta chỉ mô phỏng một tập con của quy trình, và phải nói rõ giới hạn.

## 14. Dùng `BigDecimal` cho tiền và chính sách scale

Tránh dùng `double` như đơn vị lưu số dư vì biểu diễn nhị phân floating-point có thể không diễn đạt chính xác nhiều phần thập phân.

~~~java
java.math.BigDecimal amount =
        new java.math.BigDecimal("10.50");
~~~

Đây là statement hợp lệ. Constructor nhận **chuỗi thập phân** giữ giá trị và scale dự kiến. Nên tránh `new BigDecimal(0.1)` khi muốn đúng số thập phân 0.1; constructor từ double mang chính xác giá trị nhị phân được truyền, vốn thường không phải decimal 0.1 lý tưởng.

**Nhưng BigDecimal không tự giải quyết toàn bộ bài toán tiền:**

- **Currency:** USD và VND không thể cộng tùy tiện chỉ vì cả hai là BigDecimal.
- **Scale:** một số đơn vị có 2 chữ số phần thập phân; đồng tiền khác có quy tắc khác.
- **Rounding:** phép chia, tỷ giá, thuế, phí cần `RoundingMode` và policy nhất quán.
- **Precision:** arithmetic trong BigDecimal chính xác khi các operations và context được chọn phù hợp.
- **Equality:** `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là false do scale khác, còn `compareTo` coi chúng có cùng giá trị số học.
- **Nonnegative amounts:** validate bằng `signum() > 0` nếu nghiệp vụ yêu cầu.

Các chương trình demo dùng một currency giả định, tất cả amounts được nhập với scale 2 và không thực hiện chuyển đổi ngoại tệ.

## 15. Chương trình hoàn chỉnh 5 — deposit, withdraw và lịch sử entry tham chiếu account

Tệp **`AccountLedgerDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

record Customer(String id, String name) {
}

record Entry(int sequence, Account account,
             BigDecimal change, BigDecimal balanceAfter) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance = new BigDecimal("0.00");
    private final List<Entry> history = new ArrayList<>();

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    BigDecimal balance() {
        return balance;
    }

    Customer owner() {
        return owner;
    }

    List<Entry> history() {
        return List.copyOf(history);
    }

    void deposit(BigDecimal amount) {
        requirePositive(amount);
        balance = balance.add(amount);
        history.add(new Entry(
                history.size() + 1, this, amount, balance));
    }

    void withdraw(BigDecimal amount) {
        requirePositive(amount);
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
        history.add(new Entry(
                history.size() + 1, this, amount.negate(), balance));
    }

    private static void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
    }
}

public class AccountLedgerDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01", "Lan");
        Account account = new Account("A100", lan);

        account.deposit(new BigDecimal("100.00"));
        account.withdraw(new BigDecimal("30.00"));

        System.out.println("owner=" + account.owner().name());
        System.out.println("balance=" + account.balance());
        System.out.println("entries=" + account.history().size());
        System.out.println("first delta="
                + account.history().get(0).change());
        System.out.println("second delta="
                + account.history().get(1).change());
        System.out.println("entry points back="
                + (account.history().get(0).account() == account));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AccountLedgerDemo.java
java AccountLedgerDemo
~~~

**Stdout:**

~~~text
owner=Lan
balance=70.00
entries=2
first delta=100.00
second delta=-30.00
entry points back=true
~~~

Account giữ `List<Entry>`; mỗi Entry giữ **reference tới cùng Account**. Đây là hai chiều Account→Entry→Account. Vì Account giữ history, graph có cycle. **Một cycle không tự là memory leak** nếu toàn bộ graph không còn reachable từ roots; tuy nhiên giữ Account lâu sẽ giữ Entries lâu theo chiều tham chiếu này.

`balanceAfter` được ghi bằng BigDecimal immutable tại thời điểm operation, vì vậy một Entry quá khứ có một **snapshot số dư**, dù `entry.account().balance()` sau đó tiếp tục thay đổi.

**Giới hạn tài chính:** số thứ tự bằng `history.size()+1` chỉ minh họa trong một Account instance; không phải transaction ID duy nhất toàn hệ thống, không thread-safe hoặc durable. Rút và ghi entry ở đây không có database transaction/rollback.

## 16. Vì sao lưu history trong Account cần quy tắc ownership?

Nếu Account cho code ngoài tự ý sửa `history`, caller có thể xóa entry quá khứ, thêm entry giả hoặc thay đổi thứ tự:

~~~java
// API thiết kế kém (minh họa ý tưởng):
// public List<Entry> getHistory() { return history; }
~~~

Đây là snippet được comment, không phải một declaration runnable. Thay vào đó:

~~~java
List<Entry> history() {
    return List.copyOf(history);
}
~~~

Method này **ngăn caller thêm/xóa elements qua list trả về**, nhưng không deep-copy các object elements. Nếu Entry là record với immutable components như BigDecimal, việc trả một shallow structural snapshot thường có thể chấp nhận trong ví dụ.

**Cần phân biệt:**
- `List.copyOf` tạo list mới hoặc tái sử dụng list immutable đủ điều kiện theo contract, không hứa deep clone.
- `Entry` record có component references final, không làm object Account mà nó trỏ tới trở nên immutable.
- Nếu history chỉ nên chứa **immutable audit snapshots**, tốt hơn lưu Account ID hoặc snapshot fields thay vì reference live Account.

Với hệ thống có yêu cầu audit pháp lý, nên dùng một append-only persisted ledger/event store có controls, chứ không xem list trong heap là đủ.

## 17. Mô hình giao dịch chuyển tiền: một giao dịch có hai đầu tham chiếu

Một chuyển khoản kết nối:

~~~text
             Transaction T9
              /          \
       sourceAccount   targetAccount
            |               |
            v               v
        Account A        Account B
            |               |
            v               v
        Owner C1          Owner C2
~~~

Ở mức OOP, một record:

~~~java
record Transfer(String id,
                Account source,
                Account target,
                java.math.BigDecimal amount) {
}
~~~

là một cách ghi nhận **tham chiếu tới hai accounts**. Nhưng constructor record chỉ lưu các components, **không tự cập nhật số dư** và không bảo đảm rằng source/target thuộc owner được phép.

Một transfer service cần kiểm tra:
- Source/target không null và là hai account khác nhau theo identity nghiệp vụ.
- Số tiền dương và currency/scale hợp lệ.
- Source có số dư hoặc hạn mức thích hợp.
- Request có quyền chuyển tiền và anti-fraud checks (ngoài demo).
- Hai thay đổi số dư và ghi ledger nằm trong một transaction boundary atomic/durable khi là hệ thống thực.

Không thể thay những trách nhiệm này bằng việc khai hai reference fields.

## 18. Chương trình hoàn chỉnh 6 — chuyển khoản trong bộ nhớ

Tệp **`TransferReferencesDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id, String name) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance;

    Account(String number, Customer owner, BigDecimal opening) {
        if (number == null || owner == null
                || opening == null || opening.signum() < 0) {
            throw new IllegalArgumentException("invalid account");
        }
        this.number = number;
        this.owner = owner;
        this.balance = opening;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }

    BigDecimal balance() {
        return balance;
    }

    void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
    }

    void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}

record Transfer(String id, Account source,
                Account target, BigDecimal amount) {
}

public class TransferReferencesDemo {
    static Transfer transfer(String id, Account from,
                             Account to, BigDecimal amount) {
        if (from == null || to == null
                || from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("invalid transfer");
        }
        if (from.balance().compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }

        from.debit(amount);
        to.credit(amount);
        return new Transfer(id, from, to, amount);
    }

    public static void main(String[] args) {
        Account source = new Account("A100",
                new Customer("C01", "Lan"),
                new BigDecimal("80.00"));
        Account target = new Account("A200",
                new Customer("C02", "Minh"),
                new BigDecimal("10.00"));

        Transfer record = transfer("T9", source, target,
                new BigDecimal("30.00"));

        System.out.println("source=" + source.balance());
        System.out.println("target=" + target.balance());
        System.out.println("total="
                + source.balance().add(target.balance()));
        System.out.println("from reference="
                + (record.source() == source));
        System.out.println("to owner="
                + record.target().owner().name());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 TransferReferencesDemo.java
java TransferReferencesDemo
~~~

**Stdout:**

~~~text
source=50.00
target=40.00
total=90.00
from reference=true
to owner=Minh
~~~

Một Transfer record kết nối chính **hai Account objects đã thay đổi**. Tổng số dư 80.00+10.00 trước và 50.00+40.00 sau đều là 90.00 trong mô hình không phí.

**Đây không phải implementation transfer an toàn để đưa vào ngân hàng thật.** Hai lời gọi `debit` và `credit` là hai mutation tách rời, không có transaction rollback nếu failure giữa chừng và không có synchronization giữa threads. Việc kiểm tra số dư trước khi debit **không đủ** chống race condition. Cần transaction/locking/persistence/idempotency cho môi trường thực.

## 19. Khi đối tượng có ID giống nhau nhưng reference khác nhau

Java phân biệt:

- **Object identity:** `a == b` kiểm tra có cùng object reference không.
- **Business identity:** `a.accountNumber().equals(b.accountNumber())` so key nghiệp vụ.
- **Value equality:** `a.equals(b)` phụ thuộc implementation của `equals`, với record thường so các components.

Ví dụ:

~~~java
Account a = new Account("A100", owner);
Account b = new Account("A100", owner);
~~~

Snippet dựa vào constructor phù hợp. Có thể `a != b` dù accountNumber cùng chuỗi.

Trong domain ngân hàng, hai objects cùng account number có thể đại diện **một business entity ở hai lần load khác nhau từ database**. Một process không nên dựa vào `==` giữa entities tải từ repository khác nhau để quyết định chúng là cùng account nghiệp vụ.

**Nhưng** cũng không nên tự định nghĩa equals/hashCode chỉ dựa vào một ID mutable có thể đổi: việc mutate key đang nằm trong HashMap/HashSet gây lỗi khó tìm. Identity fields cần ổn định theo policy.

## 20. Chương trình hoàn chỉnh 7 — identity reference khác business ID

Tệp **`AccountIdentityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Set;

final class Account {
    private final String number;

    Account(String number) {
        this.number = number;
    }

    String number() {
        return number;
    }
}

public class AccountIdentityDemo {
    public static void main(String[] args) {
        Account a = new Account("A100");
        Account b = new Account("A100");

        Set<Account> objects = new HashSet<>();
        objects.add(a);
        objects.add(b);

        System.out.println("same object=" + (a == b));
        System.out.println("same account number="
                + a.number().equals(b.number()));
        System.out.println("set size=" + objects.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AccountIdentityDemo.java
java AccountIdentityDemo
~~~

**Stdout:**

~~~text
same object=false
same account number=true
set size=2
~~~

Class Account không override equals/hashCode, nên Set phân biệt hai Account instances theo Object equality. Một repository không được cho phép hai business records trùng account number chỉ vì chúng là objects khác nhau.

Nếu định nghĩa equals theo account number, hãy cân nhắc uniqueness, phạm vi ngân hàng/tenant, lifecycle ID chưa được gán, consistency với hashCode và các ORM proxy types trước khi áp dụng.

## 21. Live reference khác historical snapshot

Một lịch sử giao dịch thường phải thể hiện **trạng thái tại thời điểm giao dịch**, không phải những thuộc tính live luôn thay đổi.

Giả sử Customer đổi display name từ Lan sang Mai. Nếu Transaction chỉ lưu `Customer customer`, một trang lịch sử dựng lại tên bằng `transaction.customer().displayName()` sẽ hiển thị **Mai**, dù thời điểm phát sinh chứng từ chủ có tên Lan.

Hai nhu cầu khác nhau:

| Nhu cầu | Lưu reference live | Lưu snapshot |
| --- | --- | --- |
| Hiển thị hồ sơ hiện tại của chủ | Phù hợp | Có thể bị cũ |
| Kiểm tra account hiện đang thuộc customer nào | Có thể phù hợp nếu authoritative graph | Snapshot không tự cập nhật |
| In chứng từ lịch sử đúng thời điểm | Không đủ nếu fields mutable | Phù hợp với audit snapshot |
| Giữ account IDs liên kết dài hạn | Có thể giữ object graph lớn | IDs/immutable values gọn hơn |
| Ghi dữ liệu bền vững/tra cứu ngoài process | Cần persistence mapping | Snapshot fields có thể dễ serialize hơn |

Không có lựa chọn chung cho mọi tình huống. Nhiều thiết kế dùng **cả accountId/customerId** và **snapshot fields** trong transaction event, rồi lấy live profile từ repository khi cần.

## 22. Chương trình hoàn chỉnh 8 — snapshot không thay khi đổi tên Customer

Tệp **`OwnerSnapshotDemo.java`**:

~~~java
final class Customer {
    private final String id;
    private String name;

    Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    String id() {
        return id;
    }

    String name() {
        return name;
    }

    void rename(String value) {
        name = value;
    }
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }
}

record ReceiptSnapshot(String accountNumber,
                       String customerId,
                       String ownerNameAtIssue) {
}

public class OwnerSnapshotDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "Lan");
        Account account = new Account("A100", customer);

        ReceiptSnapshot receipt = new ReceiptSnapshot(
                account.number(), customer.id(), customer.name());

        customer.rename("Mai");

        System.out.println("live name=" + account.owner().name());
        System.out.println("receipt name=" + receipt.ownerNameAtIssue());
        System.out.println("receipt owner ID=" + receipt.customerId());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 OwnerSnapshotDemo.java
java OwnerSnapshotDemo
~~~

**Stdout:**

~~~text
live name=Mai
receipt name=Lan
receipt owner ID=C01
~~~

Account liên kết tới Customer live, trong khi ReceiptSnapshot lưu ba String immutable. Đây là một ví dụ đơn giản về **tách live entity reference khỏi historical value**.

Mô hình thực tế cần timestamp, timezone policy, văn bản pháp lý, tiền tệ, transaction ID, dữ liệu đã được chứng thực và storage bền vững. Record trong heap không tự trở thành audit trail không thể sửa.

## 23. Record Transaction có final fields nhưng không làm Account bất biến

Với:

~~~java
record Transaction(String id, Account account) {
}
~~~

Transaction record là implicitly final và các component fields là final. Nhưng `account` vẫn là reference tới một **Account mutable**.

Nếu Account tăng số dư từ 10.00 lên 20.00, lệnh `transaction.account().balance()` sau đó đọc **20.00**, không phải 10.00 tại thời điểm tạo transaction.

**Đây là shallow immutability:** component reference trong record không thể bị gán lại qua record accessor, nhưng referenced object vẫn có thể mutate. Nếu lịch sử cần cố định `balanceAfter`, lưu BigDecimal immutable tại thời điểm event:

~~~java
record TransactionSnapshot(String id,
                           String accountNumber,
                           java.math.BigDecimal balanceAfter) {
}
~~~

Đây là khai báo record hợp lệ. BigDecimal là immutable, nhưng validation để chống null/currency sai vẫn thuộc constructor/service.

## 24. Chương trình hoàn chỉnh 9 — record giữ live Account và immutable balance snapshot

Tệp **`TransactionSnapshotDemo.java`**:

~~~java
import java.math.BigDecimal;

final class Account {
    private BigDecimal balance = new BigDecimal("0.00");

    void deposit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
        balance = balance.add(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}

record Transaction(String id, Account account,
                   BigDecimal balanceAfter) {
}

public class TransactionSnapshotDemo {
    public static void main(String[] args) {
        Account account = new Account();

        account.deposit(new BigDecimal("10.00"));
        Transaction first =
                new Transaction("T1", account, account.balance());

        account.deposit(new BigDecimal("5.00"));

        System.out.println("snapshot=" + first.balanceAfter());
        System.out.println("live=" + first.account().balance());
        System.out.println("same account="
                + (first.account() == account));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 TransactionSnapshotDemo.java
java TransactionSnapshotDemo
~~~

**Stdout:**

~~~text
snapshot=10.00
live=15.00
same account=true
~~~

`balanceAfter` là một BigDecimal value đã lưu và không thay đổi; Account mutable vẫn phản ánh số dư mới. Đây là lý do transaction history cần **phân biệt reference state và event-time state**.

## 25. Biến field `final` bảo vệ gì trong object graph?

Nếu khai:

~~~java
private final Customer owner;
~~~

trong BankAccount, trường reference `owner` **không thể bị gán lại** sau construction hợp lệ. Nhưng:
- Customer object có thể có mutable profile fields.
- Một Customer có thể sở hữu nhiều Accounts.
- Nếu muốn thay ownership theo nghiệp vụ, phải có thiết kế riêng thay vì lén sửa final field.
- Final reference **không đảm bảo owner không thể bị GC**: reachability phụ thuộc vào graph roots.
- Một account có thể được lưu ở repository dưới account ID; cùng business entity có thể được materialize thành objects mới.

`final` giúp duy trì cấu trúc ownership cố định trong mô hình nhỏ, nhưng không thay thế domain invariants: owner tồn tại, account ID unique, customer active, currency compatible.

Khi business hỗ trợ joint owners hoặc chuyển quyền, mô hình `Account.owner` duy nhất có thể không còn phù hợp. Cần chuyển sang quan hệ membership/authorization records thay vì cố “hack” một reference field.

## 26. Quan hệ hai chiều đòi một cửa cập nhật

Nếu Account và Customer mỗi bên đều giữ reference/list đến bên kia, việc mở account nên thực hiện qua **một method bảo vệ invariant**.

Một thiết kế yếu cho phép:

~~~java
// Ý tưởng kém: để code ngoài thao tác riêng từng hướng
// customer.accounts.add(account);
// account.owner = anotherCustomer;
~~~

Các dòng được comment là minh họa nguy cơ, không phải API được khuyến nghị.

Thiết kế an toàn hơn:
1. Customer hoặc AccountService là entry point tạo Account.
2. Constructor Account kiểm tra owner nonnull và account number.
3. Entry point thêm Account vào collection đúng Customer.
4. Không công khai mutable collection.
5. Không công khai setter owner tùy ý.
6. Khi cần transfer ownership, sử dụng **một domain operation** thay đổi đồng bộ mọi quan hệ liên quan và kiểm tra policy.

Ngay cả với một hàm tạo đơn giản, nếu chương trình chạy multi-thread, cần ràng buộc concurrency để tránh hai requests tạo cùng account number cùng lúc.

## 27. Chương trình hoàn chỉnh 10 — kiểm tra quan hệ owner khi tạo payment request

Tệp **`OwnerValidationDemo.java`**:

~~~java
import java.math.BigDecimal;

record Customer(String id) {
}

final class Account {
    private final String number;
    private final Customer owner;

    Account(String number, Customer owner) {
        if (number == null || owner == null) {
            throw new IllegalArgumentException("account");
        }
        this.number = number;
        this.owner = owner;
    }

    Customer owner() {
        return owner;
    }

    String number() {
        return number;
    }
}

record PaymentRequest(Account account, Customer requestedBy,
                      BigDecimal amount) {
    PaymentRequest {
        if (account == null || requestedBy == null
                || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("invalid payment");
        }
        if (account.owner() != requestedBy) {
            throw new IllegalArgumentException("owner mismatch");
        }
    }
}

public class OwnerValidationDemo {
    public static void main(String[] args) {
        Customer lan = new Customer("C01");
        Customer minh = new Customer("C02");
        Account account = new Account("A100", lan);

        PaymentRequest valid =
                new PaymentRequest(account, lan,
                        new BigDecimal("2.00"));
        System.out.println("valid reference="
                + (valid.account().owner() == valid.requestedBy()));

        try {
            new PaymentRequest(account, minh,
                    new BigDecimal("2.00"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OwnerValidationDemo.java
java OwnerValidationDemo
~~~

**Stdout:**

~~~text
valid reference=true
rejected=owner mismatch
~~~

Ví dụ kiểm tra một **in-memory reference consistency invariant**. Nó **không phải** authorization thực tế. Trong hệ thống thật, một caller có thể gửi một customerId giả; service phải xác thực principal, kiểm tra quyền thực hiện thao tác trên account, kiểm soát joint ownership và các chính sách khác. Nếu hai Customer objects cùng business ID nhưng khác instances, `!=` ở đây sẽ từ chối; đó là hệ quả của demo dùng object identity, không phải luật nghiệp vụ toàn cầu.

## 28. Tham chiếu ngược và vòng object graph không tự gây memory leak

Khi Account giữ List<Transaction> và Transaction giữ Account, graph có cycle:

~~~text
GC Root ---> Account ---> List<Transaction> ---> Transaction
                 ^                              |
                 +--------- account ------------+
~~~

Java GC có thể xử lý cycles khi **toàn bộ graph trở thành unreachable** từ GC roots. Cái khiến bộ nhớ bị giữ quá lâu thường là một **root còn giữ graph**, ví dụ static registry, cache không giới hạn, event listener hoặc active session.

Ví dụ một `static Map<String,Account>` giữ Account lâu dài; Account giữ toàn bộ history và mỗi Transaction giữ Account. Khi đó history tiếp tục reachable theo registry. Dù các local variables đã ra khỏi scope, objects không phải garbage nếu còn đường mạnh từ Map.

**Thiết kế với history lớn:** có thể chỉ giữ phần gần nhất trong memory, phân trang từ database, hoặc lưu IDs/snapshots thay vì references tới toàn bộ entities. GC không thay eviction và retention policy.

## 29. Chương trình hoàn chỉnh 11 — thấy vòng tham chiếu và cắt quan hệ dài hạn

Tệp **`RelationshipLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Account {
    private final String id;
    private final List<Transaction> transactions =
            new ArrayList<>();

    Account(String id) {
        this.id = id;
    }

    void add(String transactionId) {
        transactions.add(new Transaction(transactionId, this));
    }

    List<Transaction> transactions() {
        return List.copyOf(transactions);
    }

    void clearInMemoryHistory() {
        transactions.clear();
    }
}

record Transaction(String id, Account account) {
}

public class RelationshipLifecycleDemo {
    public static void main(String[] args) {
        Account account = new Account("A100");
        account.add("T1");
        account.add("T2");

        Transaction first = account.transactions().get(0);

        System.out.println("count=" + account.transactions().size());
        System.out.println("back reference="
                + (first.account() == account));

        account.clearInMemoryHistory();
        System.out.println("count after clear="
                + account.transactions().size());
        System.out.println("first ID still=" + first.id());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RelationshipLifecycleDemo.java
java RelationshipLifecycleDemo
~~~

**Stdout:**

~~~text
count=2
back reference=true
count after clear=0
first ID still=T1
~~~

`clearInMemoryHistory()` loại bỏ references khỏi Account list, nhưng local variable `first` vẫn giữ Transaction, và Transaction lại giữ Account. Vì vậy không được kết luận “hai objects đã được GC thu gom sau clear”.

Ví dụ làm rõ **các đường tham chiếu**. Trong sản phẩm tài chính, xóa lịch sử chỉ để giải phóng memory không được đồng nghĩa xóa dữ liệu audit bền vững bắt buộc lưu.

## 30. Composition, aggregation và association trong mô hình

Ba cách nói phổ biến của UML/OOP:

- **Association**: Transaction biết Account và có thể điều hướng sang Account.
- **Aggregation (khái niệm chia sẻ)**: Customer được liên kết với một tập Accounts nhưng Accounts có thể được quản lý độc lập bởi registry/database.
- **Composition (ownership vòng đời mạnh hơn)**: một object sở hữu subobjects và quyết định lifecycle của chúng; ví dụ một Account trong mô hình thuần heap tạo và giữ các LedgerEntries nội bộ.

Java không có keyword riêng `aggregation` hoặc `composition`. Cả hai có thể dùng **reference fields và collections**; sự khác nhau chủ yếu ở **hợp đồng ownership, tạo/hủy, visibility và invariant**.

Nên mô tả:
1. Ai tạo Account?
2. Account có thể tồn tại nếu Customer object trong memory không còn không?
3. Transaction lịch sử có phải tiếp tục tồn tại sau khi Account đóng?
4. Ai được phép xóa/đổi quan hệ?
5. Data có được lưu ở DB không?
6. Nếu cùng một business account được load nhiều lần, object identity được xử lý ra sao?

Chỉ nhìn vào `private Customer owner;` thì chưa biết hết các câu trả lời.

## 31. Tài khoản đóng khác đối tượng Account hết vòng đời

Đóng tài khoản theo nghiệp vụ có thể chuyển status từ ACTIVE sang CLOSED, nhưng Java Account object vẫn còn được tham chiếu trong history, reports hoặc services.

~~~java
enum AccountStatus {
    ACTIVE, CLOSED
}
~~~

Đây là declaration hợp lệ. Một Account model có thể có:

~~~java
private AccountStatus status = AccountStatus.ACTIVE;
~~~

Đây là field snippet hợp lệ trong Account class. Khi close business account, code đổi status và từ chối future withdrawals, nhưng **không** xóa hồ sơ, lịch sử và pháp lý chỉ vì account không active.

Ngược lại, `AutoCloseable.close()` của một file/database resource là cleanup một native/managed resource. **Không nhầm** `account.close()` (đóng sản phẩm ngân hàng) với `Connection.close()` hoặc garbage collection của Account object.

Domain naming cần làm rõ semantics: `closeAccount()`, `deactivate()` hoặc `changeStatus()` có thể diễn đạt tốt hơn một method `close()` mơ hồ trong model.

## 32. Một ledger thật khác collection Transaction trong memory

Một `List<Transaction>` trong Account phù hợp để học object references. Nhưng trong hệ thống cần audit/durability, một ledger phải giải quyết thêm:

- Mỗi entry có unique ID và thứ tự đáng tin.
- Amount/currency/precision được validate nhất quán.
- Các postings debit/credit cần cân đối theo mô hình kế toán.
- Entries được persist bền vững và không bị sửa/xóa tùy ý.
- Transfer có **idempotency key** để tránh lặp khi request retry.
- Có trạng thái pending/posted/reversed thay vì tự “sửa transaction quá khứ”.
- Có trace/audit, principal đã ủy quyền, timestamp do hệ thống cấp và versioning.
- Các thao tác account balances và ledger records được commit atomic hoặc dùng recovery protocol.
- Có constraints DB ngăn cùng account number/transaction ID được tạo trùng.

`record Transaction(...)` trong Java chỉ là **data carrier**, không tự đảm bảo ACID, audit hoặc nonrepudiation. Những đảm bảo ấy đến từ service, persistence, access control, infrastructure và quy trình vận hành.

## 33. Thread safety: hai threads cùng thay đổi số dư

Một Account có mutable `BigDecimal balance`. Nếu hai threads gọi `deposit()` cùng lúc mà không đồng bộ, cả hai có thể đọc cùng số dư cũ rồi ghi kết quả mới, làm mất một update.

Ví dụ conceptual:

~~~text
balance ban đầu = 10
Thread A đọc 10, muốn +5
Thread B đọc 10, muốn +7
Thread A ghi 15
Thread B ghi 17
Kết quả là 17 thay vì 22
~~~

Đây là một **interleaving có thể xảy ra** với code không đồng bộ, không phải output duy nhất của mọi execution.

`BigDecimal` immutable không làm field `balance` tự atomic. Việc tạo BigDecimal mới rồi gán lại field vẫn là một read-modify-write operation cần kiểm soát concurrency.

**Một cách học đơn giản:** đặt một **service duy nhất** sở hữu các Accounts và đồng bộ toàn bộ operations đọc/ghi qua cùng monitor. Cách đó minh họa nguyên tắc bảo vệ invariants, không phải architecture hiệu quả cho production throughput/distributed services.

## 34. Chương trình hoàn chỉnh 12 — một service đồng bộ operations trong bộ nhớ

Tệp **`SynchronizedLedgerDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

final class LedgerService {
    static final class Account {
        private final String number;
        private BigDecimal balance;

        private Account(String number, BigDecimal opening) {
            this.number = number;
            this.balance = opening;
        }
    }

    private final Map<String, Account> accounts =
            new LinkedHashMap<>();

    synchronized Account open(String number, BigDecimal opening) {
        if (number == null || number.isBlank()
                || opening == null || opening.signum() < 0
                || accounts.containsKey(number)) {
            throw new IllegalArgumentException("account");
        }
        Account account = new Account(number, opening);
        accounts.put(number, account);
        return account;
    }

    synchronized void transfer(Account from, Account to,
                               BigDecimal amount) {
        if (from == null || to == null || from == to
                || amount == null || amount.signum() <= 0
                || accounts.get(from.number) != from
                || accounts.get(to.number) != to) {
            throw new IllegalArgumentException("transfer");
        }
        if (from.balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }

        from.balance = from.balance.subtract(amount);
        to.balance = to.balance.add(amount);
    }

    synchronized BigDecimal balance(Account account) {
        if (account == null
                || accounts.get(account.number) != account) {
            throw new IllegalArgumentException("unknown account");
        }
        return account.balance;
    }
}

public class SynchronizedLedgerDemo {
    public static void main(String[] args) {
        LedgerService service = new LedgerService();
        LedgerService.Account a =
                service.open("A100", new BigDecimal("40.00"));
        LedgerService.Account b =
                service.open("A200", new BigDecimal("10.00"));

        service.transfer(a, b, new BigDecimal("15.00"));

        System.out.println("A=" + service.balance(a));
        System.out.println("B=" + service.balance(b));
        System.out.println("total="
                + service.balance(a).add(service.balance(b)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SynchronizedLedgerDemo.java
java SynchronizedLedgerDemo
~~~

**Stdout:**

~~~text
A=25.00
B=25.00
total=50.00
~~~

`LedgerService` kiểm soát mọi mutation và reads trong ví dụ bằng **cùng monitor** (`synchronized` instance methods). Mutable balance fields của nested Account là private; caller không được thao tác trực tiếp. Khi tất cả access thật sự đi qua service này, các thao tác transfer/reads không xen vào nhau giữa chừng.

**Giới hạn:** không bảo đảm tính nguyên tử bền vững với database/process crash; không xử lý nhiều JVM instances, distributed transactions, overdraft/fees/currency và các tác động bên ngoài. Một monitor toàn cục cũng hạn chế throughput; ở production có thể cần database transactions, row locks, optimistic locking, event sourcing hoặc các chiến lược concurrency phù hợp.

## 35. Tham chiếu Customer có thay được foreign key trong database không?

Trong một JVM process:

~~~java
Account account = new Account("A100", owner);
~~~

Account có thể giữ object reference tới owner. Nhưng khi lưu xuống relational database, quan hệ thường được biểu diễn bằng **ID/foreign key**:

~~~text
CUSTOMER
  id     name
  C01    Lan

ACCOUNT
  account_no  customer_id  balance
  A100        C01          50.00

TRANSACTION
  id   source_account_no   target_account_no   amount
  T9   A100                A200                10.00
~~~

Đây là **bảng dữ liệu minh họa**, không phải SQL DDL. Trong database:
- Foreign keys thể hiện quan hệ theo business IDs.
- ORM có thể load cùng một entity thành một managed object trong một persistence context, nhưng identity qua contexts/sessions khác nhau **không nên mặc định là cùng Java reference**.
- Lazy loading/proxies có thể tác động behavior truy cập và `equals`.
- Transaction records lưu IDs giúp giảm coupling với live object graphs và hỗ trợ lịch sử.
- Thay đổi trong heap không được coi là durable cho tới khi persistence layer cam kết thành công.

**Quan trọng:** `==` trên entity objects không phải thay thế duy nhất cho việc đối chiếu foreign keys/business identity.

## 36. Khi nào chỉ lưu account ID, khi nào giữ object reference?

| Nhu cầu | Reference Account trực tiếp | Account ID |
| --- | --- | --- |
| Demo OOP trong cùng JVM | Đơn giản, dễ điều hướng | Cần lookup thêm |
| Domain service xử lý entity đã load | Có thể tiện | Vẫn hữu ích để xác thực identity |
| Dữ liệu truyền qua network | Không phù hợp để serialize object graph tùy ý | ID/DTO thường tốt hơn |
| Ledger lịch sử lâu dài | Live state có thể đổi, graph nặng | ID + snapshot value rõ hơn |
| ORM entity association | Mapping hỗ trợ reference | Cơ sở dữ liệu vẫn dùng foreign keys |
| Cache dài hạn | Có thể giữ quá nhiều objects | ID và bounded cache giúp kiểm soát |
| Hai JVM/processes khác nhau | Không có Java reference chung giữa processes | Dùng persistent identifier |
| Authorization | Reference thôi không đủ | Principal/resource policy vẫn cần |

Lựa chọn phụ thuộc layer. Một request DTO có thể chỉ mang account number; domain service kiểm tra, resolve ID sang entity trong một transaction context, rồi thao tác trên entities. Mỗi layer có trách nhiệm riêng, không phải chọn “chỉ references” hay “chỉ IDs” ở toàn bộ ứng dụng.

## 37. Quản lý quan hệ khi Account có nhiều chủ

Bài demo dùng `Account.owner` một Customer. Trong nghiệp vụ thật, joint account hoặc người được ủy quyền có thể cần nhiều người với roles:

~~~text
Account A100
  |
  +-- Membership(customer=C01, role=PRIMARY_OWNER)
  |
  +-- Membership(customer=C02, role=JOINT_OWNER)
  |
  +-- Authorization(customer=C03, scope=VIEW_ONLY)
~~~

Một model tốt khi ấy có thể dùng:
- `Customer` và `Account` là hai entities.
- `AccountMembership` liên kết Customer–Account kèm role, effective dates và status.
- Một service quyết định ai được transfer/withdraw.
- Transaction record lưu actor identity riêng với chủ sở hữu tài khoản.
- Tất cả quan hệ được kiểm tra ở database/application layers.

**Không dùng `account.owner() == request.customer()` làm kiểm tra quyền duy nhất** khi hệ thống có delegated permissions hoặc objects load từ repositories khác nhau.

## 38. Chọn object identity/equality đúng cho model

Ba lựa chọn với Account:

**A. Mặc định Object identity:** `equals` không override. Phù hợp trong mô phỏng nơi mỗi instance là entity riêng; hai bản load cùng ID không bằng nhau về Object.equals.

**B. Equality theo business ID bất biến:** hữu ích ở một số domain, nhưng phải định nghĩa uniqueness scope, lúc ID được cấp và consistency của hashCode. Nếu ID ban đầu null rồi được gán sau khi đưa object vào HashSet, thiết kế rất dễ sai.

**C. Equality theo toàn bộ value:** phù hợp với **value objects/records**, ít phù hợp với mutable account entity có balance/history thay đổi. Nếu equals/hashCode phụ thuộc balance, object có thể “mất tích” trong HashSet sau deposit.

Đừng chọn B/C chỉ vì IDE có chức năng generate equals/hashCode. Hãy quyết định **identity semantics** trước, rồi triển khai với immutable keys và các tests đối xứng/bắc cầu/nhất quán.

## 39. Cập nhật số dư không nên là public setter

Một thiết kế yếu:

~~~java
class Account {
    public java.math.BigDecimal balance;
}
~~~

Đây là class hợp lệ nhưng mô hình nghiệp vụ kém: caller có thể ghi số dư âm hoặc thay giá trị mà không có giao dịch tương ứng.

Một thiết kế tốt hơn:
- Field `private`.
- Đọc qua accessor hoặc snapshot.
- Thay đổi qua domain methods có validation.
- Điều phối transfer trong service với transaction boundary.
- Ghi ledger entries có ID, timestamp/status khi phù hợp.
- Cấm UI/generic serialization code tự ý sửa balance.

**Encapsulation không đồng nghĩa security**: nếu service dùng account private fields nhưng cho mọi caller gọi `withdraw` không xác thực, hệ thống vẫn không được bảo vệ. Ngôn ngữ Java chỉ giúp bảo vệ các đường thao tác hợp lệ trong chương trình; authorization là trách nhiệm ứng dụng.

## 40. Kiểm thử những invariants quan trọng

Với mỗi thao tác, hãy kiểm tra ít nhất:

| Tình huống | Kỳ vọng |
| --- | --- |
| Customer mở hai Accounts | Account references trỏ đúng Customer object |
| Đổi tên Customer | Live views thấy tên mới nếu cố tình chia sẻ reference |
| Tạo ReceiptSnapshot | Historical name không đổi sau profile update |
| Deposit amount dương | Balance tăng và entry được ghi |
| Withdraw vượt số dư | Bị từ chối, balance/history không đổi |
| Amount null hoặc âm/zero | Bị từ chối |
| Transfer giữa hai accounts | Source giảm, target tăng, tổng giữ nguyên nếu không phí |
| Transfer từ Account sang chính nó | Bị từ chối theo policy |
| Cùng account ID nhưng objects khác | Không suy luận `==` là true |
| Lấy history list | Không thể thêm/xóa trực tiếp qua returned list |
| Request owner không đúng | Bị từ chối theo demo reference policy |
| Concurrent mutations | Phải có service/DB synchronization thích hợp |
| History giữ references | Không giả định tự được GC dọn dù scope biến local hết |
| Repository persist | Có uniqueness, foreign-key và transaction constraints |

Một test cho **rejection path** cần xác nhận không có partial mutation. Một test cho **transfer success** cũng nên xác nhận hai account references trong Transfer result đúng objects đã xử lý.

## 41. Chương trình hoàn chỉnh 13 — rút vượt số dư không làm thay đổi Account

Tệp **`WithdrawalInvariantDemo.java`**:

~~~java
import java.math.BigDecimal;

final class Account {
    private BigDecimal balance;

    Account(BigDecimal opening) {
        if (opening == null || opening.signum() < 0) {
            throw new IllegalArgumentException("opening");
        }
        this.balance = opening;
    }

    void withdraw(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
        if (balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = balance.subtract(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}

public class WithdrawalInvariantDemo {
    public static void main(String[] args) {
        Account account = new Account(new BigDecimal("20.00"));

        try {
            account.withdraw(new BigDecimal("30.00"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("unchanged=" + account.balance());
        account.withdraw(new BigDecimal("5.00"));
        System.out.println("after valid=" + account.balance());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 WithdrawalInvariantDemo.java
java WithdrawalInvariantDemo
~~~

**Stdout:**

~~~text
rejected=insufficient funds
unchanged=20.00
after valid=15.00
~~~

Kiểm tra balance trước mutation đảm bảo thao tác **rút vượt số dư ở môi trường single-thread** không làm thay đổi state. Không suy ra đã giải quyết concurrency: nếu có nhiều threads, precondition và update cần được thực hiện trong cùng synchronization/transaction boundary.

## 42. Bài toán tích hợp: hai khách hàng, ba tài khoản, nhiều giao dịch

Thiết kế tổng hợp nhỏ:

1. `Customer` có ID và display name.
2. `Account` có account number, owner reference, mutable balance, history.
3. `LedgerEvent` là immutable record ghi transaction code, account ID và delta/snapshot.
4. `Bank` quản lý account number uniqueness trong một registry.
5. `Bank.deposit` và `Bank.transfer` kiểm tra preconditions và cập nhật entities.
6. In tổng balances và kiểm tra owner links.

Trong mô hình này, **BankService là điểm phối hợp duy nhất**. Cả hai bên chuyển khoản được xử lý bởi cùng một service instance; không có threads/persistence. Đây là cách sắp xếp trách nhiệm dễ mở rộng để học, không phải thay cho database transaction.

## 43. Chương trình hoàn chỉnh 14 — ứng dụng ngân hàng trong bộ nhớ

Tệp **`BankObjectGraphDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

record Customer(String id, String name) {
}

record LedgerEvent(String code, String accountNumber,
                   String kind, BigDecimal amount,
                   BigDecimal balanceAfter) {
}

final class Account {
    private final String number;
    private final Customer owner;
    private BigDecimal balance = new BigDecimal("0.00");
    private final List<LedgerEvent> history = new ArrayList<>();

    Account(String number, Customer owner) {
        this.number = number;
        this.owner = owner;
    }

    String number() {
        return number;
    }

    Customer owner() {
        return owner;
    }

    BigDecimal balance() {
        return balance;
    }

    List<LedgerEvent> history() {
        return List.copyOf(history);
    }

    void apply(String code, String kind, BigDecimal delta) {
        BigDecimal next = balance.add(delta);
        if (next.signum() < 0) {
            throw new IllegalArgumentException("insufficient funds");
        }
        balance = next;
        history.add(new LedgerEvent(
                code, number, kind, delta, balance));
    }
}

final class Bank {
    private final Map<String, Account> accounts =
            new LinkedHashMap<>();

    Account open(String number, Customer customer) {
        if (number == null || number.isBlank()
                || customer == null || accounts.containsKey(number)) {
            throw new IllegalArgumentException("account");
        }
        Account account = new Account(number, customer);
        accounts.put(number, account);
        return account;
    }

    void deposit(String code, Account account, BigDecimal amount) {
        requireMember(account);
        requirePositive(amount);
        account.apply(code, "DEPOSIT", amount);
    }

    void transfer(String code, Account source,
                  Account target, BigDecimal amount) {
        requireMember(source);
        requireMember(target);
        requirePositive(amount);
        if (source == target || source.balance().compareTo(amount) < 0) {
            throw new IllegalArgumentException("invalid transfer");
        }

        source.apply(code + "-D", "TRANSFER_OUT", amount.negate());
        target.apply(code + "-C", "TRANSFER_IN", amount);
    }

    private void requireMember(Account account) {
        if (account == null
                || accounts.get(account.number()) != account) {
            throw new IllegalArgumentException("unknown account");
        }
    }

    private static void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class BankObjectGraphDemo {
    public static void main(String[] args) {
        Bank bank = new Bank();
        Customer lan = new Customer("C01", "Lan");
        Customer minh = new Customer("C02", "Minh");

        Account a = bank.open("A100", lan);
        Account b = bank.open("A200", minh);
        Account c = bank.open("A300", lan);

        bank.deposit("T1", a, new BigDecimal("100.00"));
        bank.deposit("T2", b, new BigDecimal("20.00"));
        bank.transfer("T3", a, b, new BigDecimal("25.00"));

        System.out.println("A100=" + a.balance());
        System.out.println("A200=" + b.balance());
        System.out.println("A300=" + c.balance());
        System.out.println("owner A and C same="
                + (a.owner() == c.owner()));
        System.out.println("A entries=" + a.history().size());
        System.out.println("B entries=" + b.history().size());
        System.out.println("A last kind="
                + a.history().get(1).kind());
        System.out.println("total="
                + a.balance().add(b.balance()).add(c.balance()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BankObjectGraphDemo.java
java BankObjectGraphDemo
~~~

**Stdout:**

~~~text
A100=75.00
A200=45.00
A300=0.00
owner A and C same=true
A entries=2
B entries=2
A last kind=TRANSFER_OUT
total=120.00
~~~

**Vì sao đúng:** hai deposits đưa tổng hệ thống từ 0 lên 120.00. Chuyển 25.00 từ A sang B giữ tổng 120.00; A còn 75.00, B thành 45.00. Account A và C cùng tham chiếu Customer Lan. Hai ledger entries từ chuyển khoản ghi hai hướng `TRANSFER_OUT` và `TRANSFER_IN`.

**Giới hạn cần nói rõ:** hai lệnh `source.apply`/`target.apply` không phải atomic database transaction, không có rollback nếu có exception ngoài dự kiến ở giữa, không có synchronization, idempotency hay persisted ledger. Trong demo, input hợp lệ và `apply` không có external I/O, nên output xác định; trong hệ thống thực phải thiết kế atomicity/durability rõ ràng.

## 44. Những lỗi thiết kế thường gặp

| Lỗi | Vấn đề | Điều chỉnh |
| --- | --- | --- |
| Lưu owner name riêng trong mỗi account rồi quên cập nhật | Dữ liệu profile bị lệch | Reference live Customer hoặc snapshot có chủ ý |
| Dùng reference live trong audit receipt | Lịch sử “đổi tên” theo profile mới | Lưu immutable event-time snapshot |
| Dùng `==` so hai Account loaded từ DB | Cùng business entity có thể có nhiều Java instances | So stable business IDs theo policy |
| Hai objects trùng account number trong registry | Vi phạm uniqueness | Constraint tại service/database |
| Public `balance` setter/field | Không bảo vệ nghiệp vụ | Encapsulate và validate operations |
| Dùng double biểu diễn money | Sai khác floating-point | BigDecimal từ String, currency/scale policy |
| Chuyển khoản bằng hai updates không transaction | Partial failure/concurrency | Transaction boundary/locks/ledger |
| Không kiểm tra amount âm/null | Số dư sai hoặc exceptions không rõ | Kiểm tra trước mutation |
| Trả mutable history list | Caller sửa/xóa dữ liệu | Read-only snapshot, persisted ledger |
| Record Transaction giữ Account rồi tưởng immutable sâu | Account vẫn mutable | Phân biệt references với event snapshots |
| Hai chiều quan hệ update tùy ý | Owner/collections mâu thuẫn | Một factory/service làm entry point |
| Giữ graph history vĩnh viễn trong static cache | Retention/memory pressure | Pagination, eviction, persistence |
| Không phân biệt actor và account owner | Ủy quyền sai | Identity, roles, authorization service |
| Nhầm “đóng account” với object disposal | Lifecycle nghiệp vụ khác GC | Status model, history retention |
| Coi constructor Transaction là commit | Tạo object chưa persist | Service/repository/transaction rõ |

## 45. Lộ trình xây dựng sản phẩm nhỏ từ mô hình bài học

Một cách triển khai theo từng bước:

1. **Bắt đầu với hai immutable values:** `CustomerId` và `AccountNumber` hoặc chỉ String có validation.
2. **Định nghĩa Customer:** ID bất biến, profile fields theo rules.
3. **Định nghĩa Account:** account ID, owner/memberships, currency, balance và status.
4. **Tạo factory/service:** account number uniqueness trong in-memory registry hoặc DB.
5. **Tạo Transaction/LedgerEntry:** ID, account links/IDs, signed amounts, event-time snapshots.
6. **Định nghĩa operations:** deposit, withdraw, transfer rõ tiền điều kiện và hậu điều kiện.
7. **Thêm tests:** aliasing, validation, balances, history, duplicate IDs.
8. **Không lộ mutable internals:** defensive collection API; hạn chế setters.
9. **Tách DTO khỏi entities:** external API chỉ mang dữ liệu được phép và stable IDs.
10. **Thêm persistence:** foreign keys, unique constraints, transactions, migrations.
11. **Thêm security:** xác thực người gọi, phân quyền theo account, rate limit/audit.
12. **Thêm concurrency:** optimistic/pessimistic locking hoặc ledger-centric design phù hợp.
13. **Thêm observability:** logs/metrics không lộ thông tin nhạy cảm.
14. **Thêm idempotency và recovery:** retry requests không trừ tiền hai lần.
15. **Kiểm tra domain phức tạp:** nhiều currency, joint owners, fees, reversal và reconciliation.

Bài này dừng ở lớp **Java core object relationships**: làm rõ references/invariants. Những công nghệ phía sau được nhắc tới để người học không hiểu sai phạm vi đảm bảo của code trong memory.

## 46. Bài tập tự luyện

**Câu 1.** Một Account giữ `Customer owner`. Khi truyền Customer vào constructor, Java có tạo bản sao Customer không?

**Câu 2.** Hai Accounts cùng trỏ tới một Customer. `a.owner() == b.owner()` có kết quả gì?

**Câu 3.** Nếu Customer mutable và bị đổi tên, Account đọc `owner.name()` theo reference live sẽ thấy tên cũ hay mới?

**Câu 4.** Nếu Transaction cần lưu tên chủ tại thời điểm in chứng từ, nên dùng reference live hay snapshot?

**Câu 5.** Nếu hai Account objects có cùng `accountNumber` nhưng được `new` hai lần, `a == b` có mặc nhiên true không?

**Câu 6.** `equals` của Account class không override mang semantics gì?

**Câu 7.** Vì sao một List<Account> do Customer trả ra không nên mặc nhiên là mutable list nội bộ?

**Câu 8.** `List.copyOf(accounts)` có clone sâu từng Account object không?

**Câu 9.** Nêu một invariant của quan hệ Customer↔Account hai chiều.

**Câu 10.** Nếu Customer.accounts chứa Account của Customer khác, vấn đề gì phát sinh?

**Câu 11.** Một Transaction record có Account reference final thì Account.balance có bất biến không?

**Câu 12.** Tại sao BigDecimal từ String phù hợp cho amounts hơn `double` trong ví dụ?

**Câu 13.** `BigDecimal("10.0").equals(BigDecimal("10.00"))` có true không? `compareTo` thì sao?

**Câu 14.** Deposit amount âm cần được xử lý ở đâu?

**Câu 15.** Với balance=20.00, withdraw=30.00, hậu điều kiện mong muốn là gì?

**Câu 16.** Một Transfer giữ source và target Account references nhưng không gọi business operation thì có tự chuyển số dư không?

**Câu 17.** Sau transfer 30.00 từ account 80.00 sang account 10.00, hai balances là gì?

**Câu 18.** Vì sao tổng balances được giữ nguyên trong ví dụ transfer không phí?

**Câu 19.** Hai lời gọi `debit` và `credit` có tự là một atomic database transaction không?

**Câu 20.** Nếu có hai threads deposit cùng account mà không lock, lỗi nào có thể xảy ra?

**Câu 21.** Vì sao BigDecimal immutable vẫn không khiến mutable balance field tự thread-safe?

**Câu 22.** Trong service đồng bộ bằng `synchronized`, những thao tác nào phải cùng dùng một monitor để không thấy trạng thái transfer giữa chừng?

**Câu 23.** Nếu Account→Transaction→Account tạo reference cycle, JVM có tự động coi đó là memory leak không?

**Câu 24.** Nếu một static registry giữ Account và history mãi, tại sao GC không thu gom các entries?

**Câu 25.** `TransactionSnapshot(balanceAfter)` khác `transaction.account().balance()` như thế nào?

**Câu 26.** Khi Customer đổi tên sau khi snapshot được tạo, receipt snapshot có nên thay không?

**Câu 27.** Tại sao cần stable IDs/foreign keys khi lưu dữ liệu trên database?

**Câu 28.** Có thể truyền Java object reference trực tiếp giữa hai JVM processes và dùng như một địa chỉ shared memory không?

**Câu 29.** Tại sao kiểm tra `account.owner() == requester` không đủ làm authorization thực tế?

**Câu 30.** Khi có joint owners, field `Customer owner` đơn lẻ có thể gây giới hạn gì?

**Câu 31.** Account có trạng thái CLOSED theo nghiệp vụ nghĩa là Java object đã bị GC thu hồi chưa?

**Câu 32.** Có nên lưu toàn bộ lịch sử audit duy nhất trong một ArrayList không persisted không?

**Câu 33.** Vì sao mutation của account ID có thể nguy hiểm nếu Account đã nằm trong HashMap?

**Câu 34.** Nếu một service trả live Account object ra UI, cần cân nhắc rủi ro gì?

**Câu 35.** Đưa ra ba tests cần có khi xây dựng mini-bank OOP.

### Đáp án và giải thích

1. Không; constructor nhận reference value tới cùng Customer object.
2. True nếu cả hai lưu cùng exact Customer object.
3. Tên mới, vì reference trỏ tới live mutable Customer.
4. Lưu snapshot immutable/event-time fields và stable IDs.
5. Không; `==` so object identity, không so account number.
6. Object identity semantics, trừ khi có implementation khác kế thừa/override.
7. Caller có thể xóa/thêm Accounts gây sai quan hệ và history.
8. Không; list structure bất biến, elements vẫn là references gốc.
9. Account thuộc Customer.accounts thì Account.owner phải là Customer đó theo policy một chủ.
10. Object graph tự mâu thuẫn; navigation hai chiều không nhất quán.
11. Không; final giữ reference, Account có thể mutable.
12. Tránh sai khác biểu diễn binary floating point cho decimal amounts.
13. Equals false vì khác scale; compareTo trả 0 vì cùng giá trị số học.
14. Ở domain operation/constructor có trách nhiệm bảo vệ invariants, trước khi mutation.
15. Throw/reject và giữ nguyên balance/history.
16. Không; record constructor không tự chạy nghiệp vụ.
17. Source 50.00, target 40.00.
18. Không có phí, source giảm đúng amount mà target tăng đúng amount.
19. Không; cần transaction/locking/recovery khi nghiệp vụ thực.
20. Lost update, stale read hoặc invariant bị vi phạm.
21. Đọc–tính–gán là nhiều bước và có thể bị interleaving.
22. Các mutations và reads cần được đồng bộ trong cùng service/transaction policy.
23. Không; cycle collectible nếu không còn reachable từ roots.
24. Registry giữ strong references, entries vẫn reachable.
25. Snapshot giữ value tại event time; live accessor đọc số dư hiện tại.
26. Không; lịch sử phải giữ snapshot theo hợp đồng.
27. Để định danh entity qua sessions/processes và áp referential integrity/uniqueness.
28. Không; phải dùng serialization/IDs/network APIs chứ không chia sẻ reference heap trực tiếp.
29. Không xác thực principal, roles/delegation và business permissions; reference identity cũng khác qua repository loads.
30. Không mô tả nhiều roles/owners; cần association/membership model.
31. Không; business status khác object reachability.
32. Không đủ cho audit/durability; cần persisted ledger phù hợp.
33. Mutable keys/equality/hashCode có thể làm lookups thất bại, phá invariants.
34. Caller có thể thấy/mutate shared state ngoài boundary, leak dữ liệu hoặc thiếu authorization.
35. Ví dụ: cùng Customer reference qua hai Accounts; transfer giữ tổng balances; withdraw vượt hạn mức không mutate state.

## 47. Checklist thiết kế và code review

- [ ] Customer, Account và Transaction có trách nhiệm riêng?
- [ ] Quan hệ được biểu diễn bằng reference hoặc IDs theo layer thích hợp?
- [ ] Hiểu khác biệt reference alias và bản sao object?
- [ ] Có phân biệt `==` với business identity `accountNumber`?
- [ ] Owner/account IDs không thay đổi tùy tiện?
- [ ] Nếu Customer sở hữu nhiều Accounts, có entry point giữ quan hệ nhất quán?
- [ ] Nếu có navigation hai chiều, có invariant/test cho cả hai phía?
- [ ] Mutable account balance là private, chỉ đổi qua domain operation?
- [ ] Amount được validate null/positive và currency/scale phù hợp?
- [ ] Dùng BigDecimal từ String thay vì double cho ví dụ tiền?
- [ ] Withdraw lỗi không gây partial update/history?
- [ ] Transfer đúng hai account references và giữ conservation khi không phí?
- [ ] Có tránh dùng identity reference `==` như authorization duy nhất?
- [ ] Có tính đến cùng business entity qua nhiều ORM sessions?
- [ ] Có snapshot immutable cho lịch sử thay vì dựa hoàn toàn vào profile live?
- [ ] Có hiểu record component reference final chỉ bảo đảm immutability nông?
- [ ] History getter không làm lộ mutable list nội bộ?
- [ ] History/ledger có ID, ordering, persistence phù hợp khi là hệ thống thực?
- [ ] Cache/static registry có retention policy?
- [ ] Không suy GC sẽ thu gom object graphs vẫn strongly reachable?
- [ ] Concurrency của deposit/withdraw/transfer được bảo vệ theo scope?
- [ ] Có tránh tuyên bố hai mutations là một ACID transaction?
- [ ] Có test ID uniqueness, invalid inputs và transfer failure?
- [ ] Có xem xét joint ownership/roles nếu domain yêu cầu?
- [ ] Không nhầm status CLOSED của account với resource close/GC?
- [ ] Có documentation ownership/reference vs snapshot ở API boundary?
- [ ] Không đưa dữ liệu nhạy cảm vào toString/logging nếu sản phẩm thật?

## 48. Tài liệu Java 17 chính thức

- [JLS 17 §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types và tham chiếu object.
- [JLS 17 §4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): variables, field values và references.
- [JLS 17 §15.9 — Class Instance Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): tạo object bằng new.
- [JLS 17 §15.21.3 — Reference Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.3): ý nghĩa `==` với references.
- [JLS 17 §8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final reference fields.
- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record payload và component accessors.
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic và scale.
- [Java SE 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copy của collection structure.
- [Java SE 17 — `Map`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): key/value associations.
- [Java SE 17 — `HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): set dựa trên equals/hashCode.
- [Java SE 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): constructor input checks.
- [Java SE 17 — `Object.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): mặc định identity equality.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): concurrency và multi-threaded program.
- [JLS 17 §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java memory model/synchronization.
- [Java SE 17 — `Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC lifecycle/commit/rollback.
- [Java SE 17 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): prepared SQL operations.
- [Java SE 17 — `ResultSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): SQL result cursor và resource lifecycle.

## 49. Tổng kết

**Một mô hình Java hướng đối tượng có thể liên kết Customer, Account và Transaction bằng những reference fields có kiểu.** Hai accounts có thể cùng trỏ tới một Customer object; một transaction có thể trỏ tới account liên quan hoặc cả source/target accounts của một transfer. Điều này cho phép navigation và sharing rõ ràng, nhưng cũng tạo ra trách nhiệm giữ **quan hệ và trạng thái nhất quán**.

Cần luôn tách ba ý niệm: **object identity** (cùng Java instance), **business identity** (cùng account/customer ID), và **historical snapshot** (giá trị đã ghi tại thời điểm sự kiện). Reference live giúp nhìn thấy cập nhật hiện tại; immutable snapshot giúp lịch sử không biến đổi theo một profile hoặc balance mới.

Với tiền, sử dụng BigDecimal và validate amount/currency. Với quan hệ hai chiều, quản lý cập nhật qua một entry point. Với lịch sử, không làm lộ mutable collections và không nhầm record final reference với deep immutability. Với transfer, **hai operations thay số dư không tự tạo transaction atomic/durable**: hệ thống thật cần security, persistence, ledger, concurrency, recovery và tests.

Từ bài học này, điều quan trọng không phải viết thật nhiều references, mà là quyết định **mỗi reference có ý nghĩa gì, ai sở hữu đối tượng, ai được thay đổi nó và điều gì phải giữ đúng sau mỗi nghiệp vụ**.
