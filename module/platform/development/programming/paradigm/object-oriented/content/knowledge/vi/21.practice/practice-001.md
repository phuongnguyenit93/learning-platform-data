# Bài tập lớp và đối tượng qua tài khoản ngân hàng — Java OOP

## 1. Mục tiêu thực hành

Bài tập mô phỏng một tài khoản ngân hàng đơn giản để luyện cách biến yêu cầu nghiệp vụ thành **lớp (class)**, **đối tượng (object)**, **thuộc tính**, **phương thức**, **constructor** và **đóng gói dữ liệu (encapsulation)** trong Java.

Sau khi hoàn thành, bạn có thể:
- Mô tả một tài khoản bằng lớp BankAccount và tạo nhiều đối tượng độc lập bằng từ khóa new.
- Dùng các trường private để bảo vệ số dư, final cho thông tin không đổi sau khi khởi tạo.
- Viết constructor kiểm tra trạng thái đầu vào; cung cấp phương thức nạp, rút, chuyển tiền.
- Phân biệt biến tham chiếu, đối tượng thực tế, trạng thái và hành vi.
- Kiểm tra điều kiện biên, giao dịch bị từ chối và nguy cơ tràn số.
- Viết unit test để chứng minh quy tắc mà không cần kết nối ngân hàng thật.

Đây là chương trình **mô phỏng phục vụ học OOP**, không phải hệ thống ngân hàng thực. Dữ liệu chỉ ở bộ nhớ, không có đăng nhập, phân quyền, cơ sở dữ liệu, ghi sổ kế toán hay giao dịch phân tán.

## 2. Từ yêu cầu sang lớp và đối tượng

Giả sử cần quản lý hai tài khoản:

- Tài khoản A: mã TK001, chủ sở hữu An, số dư ban đầu 1.000.000 VND.
- Tài khoản B: mã TK002, chủ sở hữu Bình, số dư ban đầu 200.000 VND.
- Cho phép nạp tiền, rút tiền và chuyển tiền từ A sang B.
- Không cho số dư âm, không cho nạp/rút/chuyển số tiền bằng 0 hoặc âm.
- Phép toán làm số dư vượt miền long phải báo lỗi, không để tràn số âm thầm.

Các khái niệm:

| Khái niệm OOP | Áp dụng trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Class | BankAccount | Bản thiết kế chung cho một tài khoản |
| Object | accountA, accountB | Hai tài khoản cụ thể với trạng thái riêng |
| Field | accountNumber, ownerName, balanceVnd | Dữ liệu của mỗi đối tượng |
| Constructor | BankAccount(number, owner, initialBalance) | Khởi tạo đối tượng với trạng thái hợp lệ |
| Method | deposit, withdraw, transferTo | Hành vi được phép thao tác với số dư |
| Encapsulation | private balanceVnd và các phương thức public | Không cho mã bên ngoài gán số dư tùy ý |
| Reference | Biến accountA kiểu BankAccount | Tham chiếu đến đối tượng trong bộ nhớ |
| final field | accountNumber, ownerName | Không gán lại được từ sau constructor |

Mô hình lớp:

~~~mermaid
classDiagram
    class BankAccount {
        -String accountNumber
        -String ownerName
        -long balanceVnd
        +BankAccount(accountNumber, ownerName, initialBalanceVnd)
        +getAccountNumber() String
        +getOwnerName() String
        +getBalanceVnd() long
        +deposit(amountVnd) void
        +withdraw(amountVnd) void
        +transferTo(receiver, amountVnd) void
    }
    class BankDemo {
        +main(args) void
    }
    BankDemo --> BankAccount : tạo và gọi phương thức
    BankAccount --> BankAccount : transferTo(receiver)
~~~

Điểm quan trọng: **accountA và accountB được tạo từ cùng lớp BankAccount nhưng là hai đối tượng riêng**. Khi accountA.deposit(...), số dư của accountB không tự thay đổi.

## 3. Xác định hợp đồng cho từng thao tác

Ta dùng kiểu **long** để lưu số tiền nguyên theo VND, tránh dùng float/double cho ví dụ tính tiền nguyên. Nếu làm việc với tiền có phần thập phân hoặc nhiều loại tiền tệ, nên cân nhắc BigDecimal cùng mã đơn vị tiền; không dùng double để mô hình hóa số tiền chính xác.

| Thao tác | Điều kiện hợp lệ | Kết quả | Trường hợp sai |
| --- | --- | --- | --- |
| Tạo tài khoản | Mã và tên không trống, số dư đầu >= 0 | Đối tượng được tạo | IllegalArgumentException |
| deposit(amount) | amount > 0; tổng không tràn long | balance tăng amount | IllegalArgumentException hoặc ArithmeticException |
| withdraw(amount) | amount > 0 và amount <= balance | balance giảm amount | IllegalArgumentException hoặc IllegalStateException |
| transferTo(receiver, amount) | receiver khác null và không phải chính tài khoản; amount > 0; đủ tiền; người nhận không tràn | Bên gửi giảm, bên nhận tăng cùng amount | NullPointerException, IllegalArgumentException, IllegalStateException hoặc ArithmeticException |
| getBalanceVnd() | Không cần điều kiện | Trả số dư hiện tại | Không thay đổi trạng thái |

Quy ước của bài: thao tác không hợp lệ **ném exception và không thay đổi số dư**; phương thức giao dịch hợp lệ hoàn tất bình thường. Các điều kiện được kiểm tra trước khi sửa trạng thái.

Quy trình chuyển tiền trong một luồng:

~~~mermaid
flowchart TD
    A["accountA.transferTo(accountB, amount)"] --> B{"Người nhận hợp lệ và khác người gửi?"}
    B -->|Không| E["Ném lỗi, không đổi số dư"]
    B -->|Có| C{"Số tiền > 0 và bên gửi đủ tiền?"}
    C -->|Không| E
    C -->|Có| D{"Số dư bên nhận cộng amount có tràn long?"}
    D -->|Có| E
    D -->|Không| F["Giảm số dư bên gửi"]
    F --> G["Tăng số dư bên nhận"]
    G --> H["Hoàn tất"]
~~~

**Giới hạn có chủ đích:** phép chuyển tiền ở đây là thao tác đồng bộ trên hai đối tượng cùng tiến trình, giả định một luồng truy cập. Nó **không bảo đảm an toàn khi nhiều luồng thực hiện đồng thời** và không có giao dịch cơ sở dữ liệu; không được dùng logic này thay cơ chế giao dịch tài chính thực.

## 4. Viết chương trình hoàn chỉnh

Cấu trúc dự án Java 17 + Maven:

~~~text
bank-account-oop/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── BankAccount.java
    │   └── BankDemo.java
    └── test/java/vn/example/
        └── BankAccountTest.java
~~~

### 4.1. Cấu hình Maven

Tạo tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>bank-account-oop</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Lớp BankAccount

Tạo tệp src/main/java/vn/example/BankAccount.java:

~~~java
package vn.example;

import java.util.Objects;

/**
 * Mô phỏng một tài khoản với tiền nguyên VND.
 * Phiên bản học tập: sử dụng trong một luồng, không lưu dữ liệu bền vững.
 */
public final class BankAccount {

    private final String accountNumber;
    private final String ownerName;
    private long balanceVnd;

    public BankAccount(
            String accountNumber,
            String ownerName,
            long initialBalanceVnd) {

        this.accountNumber = requireText(
                accountNumber, "accountNumber");
        this.ownerName = requireText(ownerName, "ownerName");

        if (initialBalanceVnd < 0) {
            throw new IllegalArgumentException(
                    "Initial balance must not be negative");
        }

        this.balanceVnd = initialBalanceVnd;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return value.trim();
    }

    private static void requirePositive(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public long getBalanceVnd() {
        return balanceVnd;
    }

    public void deposit(long amountVnd) {
        requirePositive(amountVnd);
        // Tính trước; nếu tràn long thì ném ArithmeticException.
        long newBalance = Math.addExact(balanceVnd, amountVnd);
        balanceVnd = newBalance;
    }

    public void withdraw(long amountVnd) {
        requirePositive(amountVnd);

        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Insufficient balance");
        }

        balanceVnd -= amountVnd;
    }

    public void transferTo(BankAccount receiver, long amountVnd) {
        Objects.requireNonNull(receiver, "receiver");

        if (receiver == this) {
            throw new IllegalArgumentException(
                    "Cannot transfer to the same object");
        }

        requirePositive(amountVnd);

        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Insufficient balance");
        }

        // Kiểm tra tràn số phía người nhận trước khi thay đổi hai tài khoản.
        long receiverNewBalance = Math.addExact(
                receiver.balanceVnd, amountVnd);

        balanceVnd -= amountVnd;
        receiver.balanceVnd = receiverNewBalance;
    }
}
~~~

**Đọc và giải thích từng thành phần quan trọng:**

- **private final String accountNumber, ownerName:** mã và tên gắn với tài khoản không được gán lại sau khi khởi tạo. final ở đây không bảo đảm tính duy nhất toàn hệ thống; ứng dụng thực cần nơi quản lý mã tài khoản.
- **private long balanceVnd:** trạng thái có thể thay đổi, nhưng lớp khác không thể gán trực tiếp một số âm hoặc một số bất kỳ.
- **constructor:** kiểm tra tất cả dữ liệu khởi tạo trước khi đối tượng được dùng.
- **getBalanceVnd:** cho phép đọc số dư nhưng không cung cấp phương thức setBalanceVnd tùy ý.
- **deposit:** gọi Math.addExact để lỗi tràn số được phát hiện trước khi cập nhật.
- **withdraw:** kiểm tra số tiền dương và đủ số dư trước khi trừ.
- **transferTo:** nhận một **đối tượng BankAccount khác**. Vì đang ở trong mã nguồn của cùng lớp, Java cho phép truy cập trường private balanceVnd của một instance BankAccount khác.
- **receiver == this:** so sánh danh tính đối tượng. Hai tham chiếu có thể cùng trỏ đến một đối tượng; kiểm tra này ngăn tài khoản tự chuyển cho chính mình.

Lưu ý: two objects cùng accountNumber vẫn có thể được tạo ra trong phiên bản này vì constructor chỉ xác thực định dạng không trống. Đó là giới hạn của mô hình học tập, cần repository/service quản lý danh tính và ràng buộc duy nhất trong hệ thống thực.

### 4.3. Lớp thực thi và tạo hai đối tượng

Tạo tệp src/main/java/vn/example/BankDemo.java:

~~~java
package vn.example;

public final class BankDemo {

    public static void main(String[] args) {
        BankAccount accountA =
                new BankAccount("TK001", "An", 1_000_000L);
        BankAccount accountB =
                new BankAccount("TK002", "Binh", 200_000L);

        accountA.deposit(200_000L);
        accountA.withdraw(50_000L);
        accountA.transferTo(accountB, 300_000L);

        System.out.println(
                accountA.getAccountNumber()
                + " - " + accountA.getOwnerName()
                + ": " + accountA.getBalanceVnd() + " VND");

        System.out.println(
                accountB.getAccountNumber()
                + " - " + accountB.getOwnerName()
                + ": " + accountB.getBalanceVnd() + " VND");
    }
}
~~~

Cách đọc biểu thức:

~~~java
BankAccount accountA = new BankAccount("TK001", "An", 1_000_000L);
~~~

- **BankAccount** bên trái là kiểu biến tham chiếu.
- **accountA** là tên biến, không phải toàn bộ đối tượng.
- **new BankAccount(...)** tạo một đối tượng BankAccount và gọi constructor.
- Dấu chấm trong **accountA.deposit(...)** dùng để gửi yêu cầu hành vi cho đối tượng mà biến đang tham chiếu.
- Hai đối tượng có số dư riêng; phép chuyển tiền cho thấy chúng có thể tương tác thông qua phương thức.

Chạy trong thư mục có pom.xml:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.BankDemo
~~~

Kết quả dự kiến:

~~~text
TK001 - An: 850000 VND
TK002 - Binh: 500000 VND
~~~

Kiểm tra bằng tay:

| Bước | Tài khoản A (VND) | Tài khoản B (VND) |
| --- | ---: | ---: |
| Ban đầu | 1.000.000 | 200.000 |
| A nạp 200.000 | 1.200.000 | 200.000 |
| A rút 50.000 | 1.150.000 | 200.000 |
| A chuyển B 300.000 | **850.000** | **500.000** |

Trong lần chuyển tiền, tổng số dư hai tài khoản trước và sau chuyển bằng nhau: 1.350.000 VND. Chuyển tiền không tạo thêm tiền hoặc làm mất tiền **khi thao tác hợp lệ hoàn tất trong mô hình đơn luồng này**.

## 5. Kiểm thử hành vi và bất biến bằng JUnit 5

Không chỉ chạy main một lần: mã hướng đối tượng tốt phải được kiểm tra với nhiều trạng thái, đặc biệt thao tác bị từ chối.

Tạo tệp src/test/java/vn/example/BankAccountTest.java:

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class BankAccountTest {

    @Test
    void newlyCreatedAccountsHaveIndependentState() {
        BankAccount a = new BankAccount("TK001", "An", 100L);
        BankAccount b = new BankAccount("TK002", "Binh", 50L);

        a.deposit(20L);

        assertEquals(120L, a.getBalanceVnd());
        assertEquals(50L, b.getBalanceVnd());
        assertEquals("TK001", a.getAccountNumber());
        assertEquals("Binh", b.getOwnerName());
    }

    @Test
    void depositIncreasesBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        account.deposit(25L);

        assertEquals(125L, account.getBalanceVnd());
    }

    @Test
    void withdrawDecreasesBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        account.withdraw(100L);

        assertEquals(0L, account.getBalanceVnd());
    }

    @Test
    void cannotWithdrawMoreThanAvailableBalance() {
        BankAccount account = new BankAccount("A", "An", 100L);

        assertThrows(IllegalStateException.class,
                () -> account.withdraw(101L));

        assertEquals(100L, account.getBalanceVnd());
    }

    @Test
    void transactionsRejectZeroAndNegativeAmounts() {
        BankAccount a = new BankAccount("A", "An", 100L);
        BankAccount b = new BankAccount("B", "Binh", 50L);

        assertThrows(IllegalArgumentException.class,
                () -> a.deposit(0L));
        assertThrows(IllegalArgumentException.class,
                () -> a.deposit(-2L));
        assertThrows(IllegalArgumentException.class,
                () -> a.withdraw(0L));
        assertThrows(IllegalArgumentException.class,
                () -> a.transferTo(b, -10L));

        assertEquals(100L, a.getBalanceVnd());
        assertEquals(50L, b.getBalanceVnd());
    }

    @Test
    void transferMovesMoneyBetweenTwoObjects() {
        BankAccount a = new BankAccount("A", "An", 200L);
        BankAccount b = new BankAccount("B", "Binh", 50L);

        a.transferTo(b, 80L);

        assertEquals(120L, a.getBalanceVnd());
        assertEquals(130L, b.getBalanceVnd());
        assertEquals(250L,
                a.getBalanceVnd() + b.getBalanceVnd());
    }

    @Test
    void failedTransferPreservesBothBalances() {
        BankAccount a = new BankAccount("A", "An", 40L);
        BankAccount b = new BankAccount("B", "Binh", 70L);

        assertThrows(IllegalStateException.class,
                () -> a.transferTo(b, 41L));

        assertEquals(40L, a.getBalanceVnd());
        assertEquals(70L, b.getBalanceVnd());
    }

    @Test
    void cannotTransferToSameAccountOrNull() {
        BankAccount account =
                new BankAccount("A", "An", 100L);

        assertThrows(IllegalArgumentException.class,
                () -> account.transferTo(account, 10L));
        assertThrows(NullPointerException.class,
                () -> account.transferTo(null, 10L));

        assertEquals(100L, account.getBalanceVnd());
    }

    @Test
    void overflowFailsWithoutChangingBalances() {
        BankAccount a = new BankAccount("A", "An", 100L);
        BankAccount b =
                new BankAccount("B", "Binh", Long.MAX_VALUE);

        assertThrows(ArithmeticException.class,
                () -> a.transferTo(b, 1L));

        assertEquals(100L, a.getBalanceVnd());
        assertEquals(Long.MAX_VALUE, b.getBalanceVnd());

        assertThrows(ArithmeticException.class,
                () -> b.deposit(1L));
        assertEquals(Long.MAX_VALUE, b.getBalanceVnd());
    }

    @Test
    void constructorRejectsInvalidInitialState() {
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("", "An", 10L));
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("A", " ", 10L));
        assertThrows(IllegalArgumentException.class,
                () -> new BankAccount("A", "An", -1L));
    }
}
~~~

Có **10 phương thức @Test**. Khi chạy mvn test, kỳ vọng 10 test chạy thành công trên đúng các tệp đã nêu, với 0 failures và 0 errors.

### Vì sao phải kiểm tra cả trạng thái sau khi thất bại?

Một triển khai sai có thể làm:

~~~java
// Ví dụ cố tình SAI, không dùng thay phương thức transferTo thật:
balanceVnd -= amountVnd;
receiver.deposit(amountVnd);
~~~

Nếu receiver.deposit(...) thất bại vì tràn long, bên gửi đã bị trừ trước đó. Kết quả là một nửa giao dịch được thực hiện. Mã đúng **tính trước số dư mới của người nhận, rồi mới thay đổi cả hai số dư** trong một luồng.

Bộ test overflowFailsWithoutChangingBalances bảo vệ chính bất biến này. Tuy nhiên, thao tác gồm hai phép gán vẫn chưa atomic trước truy cập đồng thời hoặc lỗi tiến trình; muốn giải quyết phải dùng đồng bộ hóa/transaction và thiết kế sổ cái phù hợp.

## 6. Câu hỏi tư duy OOP qua bài thực hành

**Lớp khác có thể gán account.balanceVnd = -5 không?** Không, vì trường private. Lớp khác phải sử dụng API public, nơi BankAccount kiểm tra các bất biến. Getter đọc số dư không trao quyền sửa trực tiếp.

**Tại sao không dùng static cho balanceVnd?** static tạo một trường chung ở cấp lớp, khiến các đối tượng có thể dùng chung số dư. Ở đây mỗi BankAccount có trạng thái riêng, nên balanceVnd là trường instance.

**Hai biến có thể trỏ cùng đối tượng không?** Có:

~~~java
BankAccount first = new BankAccount("A", "An", 100L);
BankAccount alias = first;
alias.deposit(50L);
System.out.println(first.getBalanceVnd()); // 150
~~~

Phép gán alias = first sao chép **tham chiếu**, không tạo đối tượng mới. Vì vậy cả hai biến cùng quan sát một số dư 150 VND.

**Vì sao không tạo setBalanceVnd?** Một setter tự do có thể bỏ qua kiểm tra nguồn tiền. Phương thức deposit, withdraw, transferTo biểu đạt ý nghĩa hành vi và kiểm soát các điều kiện trước khi cập nhật trạng thái.

**Vì sao transferTo có thể thay đổi balanceVnd của receiver dù là private?** Quyền private trong Java áp dụng ở cấp lớp. Mã bên trong lớp BankAccount có thể truy cập trường private của bất kỳ instance BankAccount nào. Mã trong BankDemo vẫn không thể làm vậy.

**Nạp/rút và chuyển tiền có cùng độ an toàn không?** Không. Nạp và rút thay trạng thái một đối tượng; chuyển tiền cần cập nhật hai đối tượng liên quan. Trong hệ thống đa luồng/phân tán, cần xử lý tranh chấp và trạng thái giao dịch bền vững.

## 7. Nhận diện lỗi phổ biến

| Lỗi | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Đặt balanceVnd là public | Mã ngoài có thể phá bất biến | Dùng private, expose hành vi nghiệp vụ |
| Dùng static balanceVnd | Mọi đối tượng có chung số dư | Sử dụng instance field |
| Rút tiền rồi mới kiểm tra đủ tiền | Có thể âm số dư hoặc trạng thái sai | Kiểm tra trước khi trừ |
| Không kiểm tra amount <= 0 | Cho phép rút số âm gây cộng tiền | Kiểm tra số tiền dương ở mọi thao tác |
| Dùng double cho tiền | Có thể sai số nhị phân | Dùng long theo đơn vị nhỏ nhất hoặc BigDecimal |
| Không kiểm tra tràn số | long có thể wrap không cảnh báo | Math.addExact và kiểm thử giới hạn |
| Chuyển tiền cập nhật nguồn trước khi kiểm tra đích | Exception khiến trạng thái một phần | Tính/validate toàn bộ trước khi mutate |
| So sánh String bằng == | So sánh tham chiếu thay vì nội dung | Dùng equals khi kiểm tra giá trị String |
| Chỉ thử happy path | Lỗi phát sinh ở nhánh âm/tràn/thiếu tiền | Test bất biến và nhánh thất bại |
| Kết luận mô phỏng là hệ thống ngân hàng thật | Thiếu transaction, đồng thời, xác thực và audit | Bổ sung kiến trúc chuyên dụng khi triển khai thật |

## 8. Bài tập tự mở rộng

### Bài A — In thông tin tài khoản

Viết phương thức summary() trả một String gồm số tài khoản, tên và số dư. Không cho caller sửa số dư thông qua kết quả trả về. Gọi từ BankDemo để thấy hai đối tượng có thông tin độc lập.

### Bài B — Lịch sử giao dịch

Thêm một kiểu Transaction mô tả loại giao dịch, số tiền và thời điểm. Cân nhắc lưu danh sách giao dịch chỉ đọc với List.copyOf(...), và dùng Clock được tiêm vào constructor nếu muốn test thời gian một cách xác định. Quy định rõ có ghi nhận giao dịch bị từ chối hay không.

### Bài C — Hai loại tài khoản

Thêm SavingsAccount có tính lãi hoặc CheckingAccount có quy tắc rút khác. Cân nhắc dùng kế thừa chỉ khi tồn tại quan hệ is-a thực sự đúng hợp đồng; với chính sách tính phí/lãi thay đổi, có thể dùng composition qua interface InterestPolicy/FeePolicy. Không mở rộng BankAccount chỉ để kế thừa các trường private.

### Bài D — Bài toán chuyển tiền nâng cao

Giả lập nhiều yêu cầu chuyển đồng thời giữa hai tài khoản, phân tích tại sao việc kiểm tra số dư rồi cập nhật có thể sinh race condition. Đề xuất sử dụng locking theo thứ tự khóa ổn định hoặc database transaction; viết test concurrency riêng khi đã thiết kế đúng môi trường.

### Bài E — Tách trách nhiệm

Khi ứng dụng cần tìm tài khoản bằng số tài khoản và bảo đảm mã duy nhất, có nên đưa một danh sách static toàn cục vào BankAccount? Hãy đề xuất AccountRepository/BankService để quản lý kho tài khoản, rồi giải thích vì sao BankAccount vẫn nên tập trung vào bất biến và hành vi của chính tài khoản.

## 9. Checklist tự đánh giá

- [ ] Tạo được ít nhất hai object BankAccount độc lập bằng new.
- [ ] Trình bày được đâu là class, object, instance field, constructor và method.
- [ ] Giải thích được sự khác nhau giữa first và alias cùng trỏ một object.
- [ ] Số dư không thể bị sửa tùy ý từ bên ngoài lớp.
- [ ] Nạp/rút/chuyển tiền đúng số học và từ chối số tiền không hợp lệ.
- [ ] Khi giao dịch thất bại, các số dư liên quan giữ nguyên trong mô hình đơn luồng.
- [ ] Code được tổ chức thành các tệp Java hợp lệ, chạy được BankDemo và bộ test JUnit.
- [ ] Hiểu các giới hạn về đồng thời, tính bền vững và kiểm toán của mô hình.

**Kết quả mong đợi:** Bạn đã tạo một lớp mô tả đúng trách nhiệm của tài khoản, khởi tạo và tương tác giữa các đối tượng, kiểm soát dữ liệu bằng encapsulation, và dùng kiểm thử xác minh bất biến thay vì chỉ quan sát kết quả của một lần chạy main.