# Chọn quyền truy cập nhỏ nhất đáp ứng nhu cầu trong Java

## 1. Nguyên tắc: chỉ mở phần chương trình thật sự cần được dùng

Trong Java, **access modifier** quyết định phần mã nào được phép truy cập một lớp, constructor, field hoặc method theo quy tắc ngôn ngữ. Khi thiết kế lớp, không nên đánh dấu mọi thứ `public` chỉ để biên dịch thuận tiện. Thay vào đó, hãy bắt đầu từ **phạm vi hẹp nhất cho phép các bên sử dụng hợp lệ** rồi chỉ mở rộng khi có nhu cầu cụ thể.

Đây là nguyên tắc **least privilege / least visibility** trong thiết kế API: một chi tiết triển khai chỉ nên được nhìn thấy bởi những thành phần thực sự cần nó.

- Field trạng thái nội bộ của object thường là `private`.
- Helper method chỉ dùng trong lớp thường là `private`.
- Helper type hoặc method mà **các lớp trong cùng package** phải chia sẻ có thể là **package-private**.
- Thành phần dành cho **subclass tùy biến** có thể là `protected` khi có hợp đồng mở rộng thực sự.
- Thành phần làm nên **hợp đồng công khai của API** mới nên là `public`.

Chọn access nhỏ nhất không phải mẹo rút ngắn code, mà là cách **giảm phụ thuộc, bảo vệ bất biến (*invariant*) và giữ quyền thay đổi implementation** mà không buộc mọi caller sửa theo.

### Một câu hỏi quan trọng hơn “modifier nào làm code chạy được?”

> **Ai cần dùng thành viên này — chính lớp, các lớp cùng package, subclass ở package khác, hay mọi client của API?** Trả lời bằng nhu cầu thực tế, rồi chọn mức truy cập phù hợp.

Ví dụ đơn giản:

```java
public class Wallet {
    private int balance;

    public Wallet(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balance = openingBalance;
    }

    public void deposit(int amount) {
        validatePositive(amount);
        balance += amount;
    }

    public int getBalance() {
        return balance;
    }

    private static void validatePositive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
```

Đây là **lớp biên dịch được**, chưa có `main`. Trong thiết kế này:

- `Wallet` và constructor là `public` vì caller cần tạo ví.
- `deposit` và `getBalance` là `public` vì caller cần thao tác hợp lệ và đọc kết quả.
- `balance` là `private` để caller **không thể trực tiếp gán số âm** hoặc bỏ qua quy trình kiểm tra.
- `validatePositive` là `private static` vì chỉ implementation cần nó. Việc `static` ở đây không quyết định access, mà cho thấy helper không cần receiver state.

Không có lý do biến `balance` hoặc `validatePositive` thành `public` chỉ vì một lớp khác “có thể sẽ cần” chúng sau này.

## 2. Bốn mức truy cập và phạm vi sử dụng

Bảng dưới áp dụng cho **members của một class** trong ngữ cảnh Java thông thường:

| Access | Trong chính class/nest hợp lệ | Class khác cùng package | Subclass khác package | Client khác package không kế thừa |
| --- | --- | --- | --- | --- |
| `private` | Có | Không | Không theo quan hệ subclass thông thường | Không |
| Không ghi modifier (*package-private*) | Có | Có | Không chỉ nhờ kế thừa | Không |
| `protected` | Có | Có | Có, theo các **quy tắc protected đặc biệt** | Không |
| `public` | Có | Có | Có | Có, nếu enclosing type/package/module accessible |

**Thứ tự phạm vi thường dùng khi suy luận:** `private` → package-private → `protected` → `public`. Tuy nhiên đây **không phải** mô hình tập con tuyến tính đơn giản cho mọi biểu thức: đặc biệt `protected` ở **package khác** có ràng buộc ngữ cảnh subclass và kiểu receiver. Khi phân tích một dòng cụ thể, phải áp dụng quy tắc Java chứ không chỉ dựa vào sơ đồ “rộng hơn”.

### Hai lưu ý không thể bỏ qua

1. **Top-level class** chỉ được dùng `public` hoặc **package-private**. Viết `private class X` hoặc `protected class X` ở cấp cao nhất là lỗi biên dịch. **Member class** trong một class có thể dùng cả bốn mức.
2. **Access của lớp, constructor và method/field là ba bước khác nhau.** Một class `public` có thể khai báo constructor `private`, hoặc method `private`; nhìn thấy tên class **không** đồng nghĩa được tạo object hoặc gọi mọi method của nó.

Access modifier không phải cơ chế mã hóa hoặc hàng rào chống mọi hình thức reflection. Nó là **một phần hợp đồng quyền truy cập của ngôn ngữ**, rất quan trọng cho kiến trúc và tính ổn định API.

## 3. Quy trình chọn access modifier theo nhu cầu thật

Mỗi khi thêm một declaration, hãy lần lượt hỏi:

1. **Thành viên này phục vụ implementation của một lớp duy nhất?** Nếu có, ưu tiên `private`.
2. **Có các lớp cùng package cần gọi/chia sẻ?** Nếu có và chúng chủ động hợp thành cùng module chức năng, cân nhắc **package-private**.
3. **Có hợp đồng cho subclass ở package khác ghi đè hoặc truy cập?** Chỉ khi có nhu cầu mở rộng rõ, cân nhắc `protected`.
4. **Code ngoài package phải dùng trực tiếp?** Nếu có, cân nhắc `public`, thường qua API ổn định và hành vi có kiểm tra.
5. **Là top-level class hay member class?** Top-level không được `private`/`protected`; nếu thực sự muốn private helper type, có thể chuyển nó thành **private nested class**.
6. **Cần truy cập class nhưng không cần tạo instance?** Xem constructor `private` hoặc package-private, kèm factory tường minh.
7. **Có thể thay public field bằng method mô tả nghiệp vụ?** Nếu có, nên bảo vệ field và chỉ mở hành vi cần thiết.
8. **Access rộng hơn có khiến caller phụ thuộc implementation?** Nếu có, giữ lại sau internal boundary.
9. **Đã thử biên dịch client đúng package và subclass cần hỗ trợ chưa?** Đừng đoán từ trực giác.
10. **Nếu dùng named modules (JPMS), package được export chưa?** `public` vẫn chịu ranh giới module.

Một phương pháp thực tế là **tạm viết phạm vi hẹp** rồi biên dịch các client dự định được phép truy cập. Khi có lỗi access, xem **client có thực sự nên phụ thuộc declaration ấy không**, thay vì lập tức tăng thành `public`.

## 4. Vì sao `private field` thường tốt hơn `public field`?

Xét thiết kế nguy hiểm:

```java
public class BankAccount {
    public int balance;
}
```

Nếu các lớp khác có thể gán `account.balance = -100000;`, lớp `BankAccount` khó bảo đảm invariant “số dư không âm”. Sau này muốn thêm log, phí giao dịch, validation hoặc quyền truy cập, mọi nơi đang ghi field trực tiếp đều có thể phải chỉnh sửa.

Thiết kế theo encapsulation:

```java
public class BankAccount {
    private int balance;

    public BankAccount(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("opening balance is negative");
        }
        balance = openingBalance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balance += amount;
    }

    public int balance() {
        return balance;
    }
}
```

**Vì sao hợp lý?**

- Caller nhìn thấy **hành vi** `deposit` chứ không cần biết field được lưu như thế nào.
- `private int balance` giúp giới hạn các nơi có thể sửa field trực tiếp trong nguồn Java.
- Validation có một chỗ để kiểm soát.
- Có thể chuyển implementation sau này sang cấu trúc khác mà vẫn duy trì `deposit(int)` và `balance()` nếu hợp đồng API không thay đổi.

**Không phải mọi class đều cần getter/setter cho mọi field.** Một setter `setBalance(int x)` public không kiểm tra điều kiện có thể **làm hỏng chính mục tiêu** của private field. Hãy công khai **hành vi nghiệp vụ cần thiết**, không tự động công khai mọi khả năng gán.

### Chương trình độc lập xác nhận phạm vi bảo vệ

Tạo tệp **`MinimalVisibilityDemo.java`**:

```java
class BankAccount {
    private int balance;

    BankAccount(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        balance = openingBalance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }

    private void resetForInternalTest() {
        balance = 0;
    }
}

public class MinimalVisibilityDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);
        account.deposit(25);

        System.out.println(account.balance());

        // account.balance = -20;  // Lỗi: field balance private.
        // account.resetForInternalTest(); // Lỗi: private method.
    }
}
```

Biên dịch và chạy:

```bash
javac MinimalVisibilityDemo.java
java MinimalVisibilityDemo
```

**Standard output:**

```text
125
```

Các dòng cố ý sai đã được comment nên chương trình hợp lệ. Ở đây `BankAccount` là top-level **package-private**, constructor/method `deposit`/`balance` cũng package-private vì chương trình client `MinimalVisibilityDemo` nằm **cùng package mặc định** và không cần API công khai. Trong ứng dụng thực có client thuộc package khác, mức `public` có thể cần cho type, constructor và phương thức nghiệp vụ.

**Bài học:** ngay cả cùng một thiết kế lớp, phạm vi truy cập cần chọn theo **vị trí sử dụng thật**, không phụ thuộc máy móc rằng constructor hoặc mọi getter đều phải public.

## 5. `private method`: bắt đầu từ helper chỉ phục vụ implementation

Giả sử các bước tính điểm, chuẩn hóa và kiểm tra chỉ được gọi trong một lớp. Các bước đó không phải lời hứa công khai cho client.

```java
class RegistrationService {
    String register(String rawName) {
        String name = normalize(rawName);
        checkName(name);
        return "registered:" + name;
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim();
    }

    private static void checkName(String name) {
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name required");
        }
    }
}
```

Đây là **khai báo lớp hợp lệ**, không có `main`. `register` là **package-private** vì ở ví dụ giả định chỉ cùng package cần gọi. Hai helper `normalize` và `checkName` là private: caller không được phụ thuộc vào các bước nội bộ ấy.

### Khi nào cân nhắc nới từ private sang package-private?

Chỉ khi có một client cùng package **thật sự** cần behavior ấy, và việc chia sẻ phản ánh ranh giới module chức năng hợp lý. Nếu nhiều lớp cần cùng một phép chuẩn hóa, bạn có thể:

- Giữ private nếu chia sẻ sẽ làm lộ detail sai kiến trúc và các lớp nên gọi API cấp cao.
- Tách thành một **package-private helper class/method** nếu đó thực sự là utility của cùng package.
- Đưa thành `public` chỉ khi là API công khai có hợp đồng ổn định và client bên ngoài cần.

Đừng nới access chỉ vì một test ngẫu nhiên đang ở package khác; ưu tiên kiểm tra hành vi qua public API, hoặc thiết kế phạm vi test phù hợp, trước khi mở implementation.

## 6. Package-private: chia sẻ trong một package mà không mở API ra ngoài

Mức package-private đặc biệt hữu ích khi một package đóng vai trò **một đơn vị hợp tác** giữa vài lớp:

```text
src/
  shipping/
    ShippingService.java
    FeeCalculator.java
  app/
    Main.java
```

**Tệp `src/shipping/FeeCalculator.java`:**

```java
package shipping;

final class FeeCalculator {
    private FeeCalculator() {
    }

    static int feeFor(int weight) {
        if (weight < 0) {
            throw new IllegalArgumentException("negative weight");
        }
        return weight <= 5 ? 10 : 20;
    }
}
```

`FeeCalculator` là top-level **package-private**. Method `feeFor` cũng package-private. Constructor private vì helper chỉ có static method, không cần tạo instance. `final` ngăn lớp bị kế thừa, **không làm class thành private**.

**Tệp `src/shipping/ShippingService.java`:**

```java
package shipping;

public class ShippingService {
    public int quote(int weight) {
        return FeeCalculator.feeFor(weight);
    }
}
```

`ShippingService` là public API. Nó dùng helper cùng package mà không cần mở tên `FeeCalculator` ra ngoài.

**Tệp `src/app/Main.java`:**

```java
package app;

import shipping.ShippingService;
// import shipping.FeeCalculator; // Không hợp lệ: package-private.

public class Main {
    public static void main(String[] args) {
        ShippingService service = new ShippingService();
        System.out.println(service.quote(3));
        System.out.println(service.quote(8));

        // FeeCalculator.feeFor(3); // Không accessible từ package app.
    }
}
```

Biên dịch/chạy từ thư mục gốc có `src`:

```bash
javac -encoding UTF-8 -d out src/shipping/FeeCalculator.java src/shipping/ShippingService.java src/app/Main.java
java -cp out app.Main
```

```text
10
20
```

Kết quả thiết kế: code `app.Main` chỉ phụ thuộc vào `ShippingService` public API; chi tiết tính phí `FeeCalculator` có thể đổi tên, cấu trúc hoặc implementation mà không yêu cầu client import type ấy.

### Package không đồng nghĩa folder cha hay subpackage

`shipping` và `shipping.internal` là **hai package khác nhau**. Nếu chuyển `FeeCalculator` sang `shipping.internal`, `ShippingService` không tự còn truy cập được package-private type, dù hai package có tên chung tiền tố. Khi tổ chức package, hãy tính trước **ranh giới chia sẻ** mình mong muốn.

**Package-private không dành riêng cho top-level class.** Method, constructor, instance field và member class không ghi modifier cũng package-private. Hãy dùng đúng nơi cần thiết, không biến mọi helper thành top-level class theo thói quen.

## 7. `protected`: chỉ mở cho thiết kế có ý định hỗ trợ kế thừa

`protected` có vẻ là một lựa chọn “giữa private và public”, nhưng dùng nó tùy tiện có thể khiến subclass phụ thuộc vào implementation nội bộ. Vì thế `protected` chỉ nên chọn nếu class **cố ý thiết kế cho việc mở rộng**.

Ví dụ một template method:

```java
abstract class ReportGenerator {
    public final String generate() {
        String data = loadData();
        return "Report: " + data;
    }

    protected abstract String loadData();
}
```

Ở đây `generate()` là public API ổn định và `final` giữ quy trình không bị override; `loadData()` là **extension point** được thiết kế để subclass cung cấp. `protected` có ý nghĩa vì client không nên gọi trực tiếp bước nội bộ, nhưng subclass cần triển khai nó.

### Ví dụ biên dịch/chạy trong một package

Tệp **`ProtectedExtensionDemo.java`**:

```java
abstract class ReportGenerator {
    public final String generate() {
        String data = loadData();
        return "Report: " + data;
    }

    protected abstract String loadData();
}

class MonthlyReport extends ReportGenerator {
    @Override
    protected String loadData() {
        return "October";
    }
}

public class ProtectedExtensionDemo {
    public static void main(String[] args) {
        ReportGenerator report = new MonthlyReport();
        System.out.println(report.generate());
    }
}
```

```bash
javac ProtectedExtensionDemo.java
java ProtectedExtensionDemo
```

```text
Report: October
```

**Ý nghĩa quyền truy cập:**

- `generate` public vì caller cần nhận report; nó `final` để bảo vệ thứ tự xử lý được thiết kế.
- `loadData` protected vì subclass phải override; caller chỉ cần `generate()`.
- `MonthlyReport.loadData` giữ `protected`, không giảm xuống package-private hoặc private.
- `MonthlyReport` là top-level package-private trong tệp ví dụ; trong thư viện thực, nếu client ngoài package cần tạo, có thể cung cấp concrete public type/factory thích hợp.

**Không tự thay `private` bằng `protected` chỉ để subclass đọc mọi field.** Khi một subclass thật sự cần dữ liệu, thường tốt hơn dùng protected **behavioral method** có contract rõ thay vì protected mutable field khiến subclass gắn chặt với layout/state của superclass.

### Protected ở package khác có quy tắc receiver

Giả sử superclass khai báo `protected int number`. Một subclass ở package khác có thể truy cập `this.number` trong ngữ cảnh phù hợp, nhưng **không** được dùng bất cứ receiver kiểu superclass nào để đọc `other.number` nếu các điều kiện đặc biệt của protected cross-package không thỏa.

Vì vậy, khi thiết kế protected API cho subclass, nên thử biên dịch ví dụ **subclass nằm package khác**, đúng như đối tượng mở rộng dự kiến; đừng chỉ thử trong cùng package rồi suy rộng.

## 8. Public API: chỉ phần cam kết cho client bên ngoài

Một declaration nên được `public` khi client ở package khác có lý do hợp lệ để sử dụng **trực tiếp**. Đây là cam kết giao tiếp, không phải một cách giúp compiler “không còn lỗi access”.

Ví dụ một API order:

```java
public final class Order {
    private final String id;
    private boolean paid;

    public Order(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    public String id() {
        return id;
    }

    public void markPaid() {
        if (paid) {
            throw new IllegalStateException("already paid");
        }
        paid = true;
    }

    public boolean isPaid() {
        return paid;
    }

    private void clearInternalCache() {
        // Chỉ phục vụ implementation khi thật sự cần.
    }
}
```

Trong ví dụ:

- `Order` là public vì client cần đặt tên kiểu.
- Constructor public để client tạo order hợp lệ; nếu muốn kiểm soát tạo object chặt hơn, factory có thể thay thế.
- Các method `id`, `markPaid`, `isPaid` là public vì là **hành vi/API được hứa hẹn**.
- `id` và `paid` private vì client không nên sửa trực tiếp.
- `clearInternalCache` private vì không phải chức năng client cần.

Mã ví dụ là **khai báo lớp hợp lệ**, lưu trong `Order.java` nếu được dùng. `clearInternalCache` hiện không được gọi; trong code thật nếu helper không còn cần thiết thì xóa bỏ nó thay vì duy trì một method vô ích.

**Đặt một method public sẽ tạo kỳ vọng về tính ổn định**: caller ngoài package có thể phụ thuộc vào tên, chữ ký, ngoại lệ và hành vi. Thu hẹp quyền về sau có thể làm mã khách hàng không biên dịch hoặc làm vỡ liên kết ở runtime tùy bối cảnh. Vì vậy public surface cần được quản lý như một sản phẩm API.

## 9. Constructor: có quyền nhìn thấy type chưa chắc được phép `new`

Constructor có access level riêng và không kế thừa như instance method.

### Utility class không cần instance

```java
public final class MathHelpers {
    private MathHelpers() {
    }

    public static int square(int value) {
        return value * value;
    }
}
```

`MathHelpers` là public top-level class; `square` là public static API; constructor private để caller không cần và không thể tạo object `MathHelpers` ngoài phạm vi cho phép. `final` ngăn subclass, không phải quyền truy cập.

### Controlled creation qua factory

```java
public final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    public static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("invalid user id");
        }
        return new UserId(value);
    }

    public String value() {
        return value;
    }
}
```

Ở đây client không được gọi `new UserId("...")` từ code ngoài lớp, nhưng có thể gọi `UserId.of("U01")`. Factory cho phép validate, chuẩn hóa, cache hoặc đổi chiến lược tạo object mà không lộ constructor.

### Ví dụ chạy độc lập

Tệp **`FactoryVisibilityDemo.java`**:

```java
final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("invalid id");
        }
        return new UserId(value.trim());
    }

    String value() {
        return value;
    }
}

public class FactoryVisibilityDemo {
    public static void main(String[] args) {
        UserId id = UserId.of(" A7 ");

        System.out.println(id.value());
        // UserId other = new UserId("A7"); // Lỗi: constructor private.
    }
}
```

```bash
javac FactoryVisibilityDemo.java
java FactoryVisibilityDemo
```

```text
A7
```

`UserId` top-level package-private trong chương trình minh họa vì chỉ client cùng tệp/package sử dụng; factory `of` cũng package-private cho cùng lý do. Nếu tách thành thư viện cho package khác, công khai `UserId` và `of` nhưng vẫn giữ constructor `private`.

### Constructor mặc định có thể vô tình mở cửa tạo object

Nếu một class không khai báo constructor nào, compiler có thể cung cấp **default constructor**. Với `public class Utility { }` bình thường, default constructor có mức truy cập tương ứng là public. Nếu class chỉ chứa static helpers và không cần instance, viết private constructor tường minh tránh tình huống client tạo những object vô nghĩa.

Mặt khác, đừng tạo private constructor trong một class cố ý hỗ trợ kế thừa nếu điều đó làm subclass không thể gọi constructor superclass. Đối với framework extension point, có thể dùng `protected` constructor với hợp đồng rõ.

## 10. Top-level class và member class: mức truy cập có thể khác nhau

Với **top-level class**, Java chỉ cho phép:

- `public class X { }`
- `class X { }` — package-private.

Không được:

```java
// private class X { }   // Không hợp lệ ở top-level.
// protected class Y { } // Không hợp lệ ở top-level.
```

Với **member class** bên trong class:

```java
public class DocumentService {
    public static class Result {
        public final String message;

        public Result(String message) {
            this.message = message;
        }
    }

    protected static class ExtensionHook {
    }

    static class PackageHelper {
    }

    private static class InternalParser {
    }
}
```

Bốn mức access đều **có thể hợp lệ**, miễn đáp ứng các quy tắc khác của class. Tại đây các loại nested class được khai báo `static` vì không cần enclosing `DocumentService` instance; việc static hay non-static không quyết định modifier truy cập.

**Cách chọn:**

- `Result` public nếu client phải sử dụng kiểu kết quả cụ thể đó.
- `ExtensionHook` protected nếu API thực sự dành cho subclass extension và các điều kiện constructor/method accessibility đã được tính.
- `PackageHelper` package-private nếu chỉ đồng nghiệp cùng package cần.
- `InternalParser` private nếu hoàn toàn là chi tiết implementation của enclosing class.

Không mở tất cả member classes ra public chỉ vì outer class public. Và nếu outer class bản thân package-private, việc một member class public không tự làm tên `Outer.Member` trở nên accessible từ package khác.

## 11. Access của kiểu, constructor và method là ba bước riêng

Một lỗi API phổ biến là công khai nested type nhưng quên mức truy cập constructor:

```java
package example;

public class Catalog {
    public static class Entry {
        Entry() {
        }

        public String name() {
            return "entry";
        }
    }
}
```

Từ package khác, code có thể **đặt tên kiểu** `Catalog.Entry` nhưng không tạo bằng `new Catalog.Entry()` vì constructor explicit `Entry()` là package-private.

Nếu client cần được tạo `Entry`, hãy khai báo `public Entry()` hoặc cung cấp factory accessible. Nếu client chỉ được phép **đọc Entry do Catalog cung cấp**, giữ constructor hẹp có thể là chủ đích đúng.

Tương tự, một instance method không ghi modifier trong class public vẫn là **package-private**. Modifier của enclosing type không tự áp cho tất cả thành viên.

### Một checklist trước khi đặt `public`

Hãy kiểm tra:

1. Client có thật cần biết **tên concrete class** hay chỉ cần interface/supertype?
2. Có cần client trực tiếp gọi **constructor** hay factory là đủ?
3. Có cần client gọi **method** hay chỉ cần kết quả method cấp cao?
4. Nếu member trả về một type inaccessible, client có cần đặt tên type đó không? Có thể thay bằng một public interface hoặc DTO thích hợp.
5. Khi mở rộng API, có hợp đồng ổn định cho client dựa vào không?

Ba tầng riêng này giúp chọn đúng mức truy cập mà không lộ toàn bộ implementation.

## 12. Không tạo public setter cho mọi private field

Một class có field private nhưng setter public vô điều kiện vẫn có thể để caller phá bất biến:

```java
class Product {
    private int quantity;

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

Nếu số lượng âm là bất hợp lệ, setter trên cho phép caller tạo trạng thái sai. Thiết kế tốt hơn có thể là:

```java
class Product {
    private int quantity;

    Product(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        this.quantity = quantity;
    }

    void addStock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        quantity += amount;
    }

    int quantity() {
        return quantity;
    }
}
```

Hai phiên bản `Product` là **hai khai báo độc lập để so sánh**, không đặt đồng thời trong một source set. Ở bản sau, caller chỉ thực hiện các hành vi có ý nghĩa; class tự bảo vệ invariant.

**Least visibility là chọn cả phạm vi lẫn loại hành vi công khai**, không phải chỉ thêm từ khóa `private` vào mọi field rồi sinh getter/setter một cách máy móc.

## 13. Encapsulation và object references: private field vẫn có thể lộ mutable state

Giữ một field `private` chưa đủ nếu một public getter trả trực tiếp mutable object mà field đang tham chiếu.

Ví dụ rủi ro:

```java
import java.util.List;

class UnsafeGroup {
    private final List<String> names;

    UnsafeGroup(List<String> names) {
        this.names = names;
    }

    List<String> names() {
        return names;
    }
}
```

Dù field private, các caller có tham chiếu list qua constructor/getter có thể tiếp tục mutate **cùng list object**. Access control giới hạn **đường truy cập cú pháp tới field**, nhưng không tự làm object được tham chiếu trở thành immutable.

### Chương trình độc lập: defensive copy

Tệp **`EncapsulationCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Group {
    private final List<String> names;

    Group(List<String> input) {
        this.names = new ArrayList<>(input);
    }

    List<String> names() {
        return List.copyOf(names);
    }

    void add(String name) {
        names.add(name);
    }
}

public class EncapsulationCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Group group = new Group(source);
        source.add("Binh");

        System.out.println("source=" + source);
        System.out.println("group=" + group.names());

        group.add("Chi");
        System.out.println("group=" + group.names());
    }
}
```

```bash
javac EncapsulationCopyDemo.java
java EncapsulationCopyDemo
```

```text
source=[An, Binh]
group=[An]
group=[An, Chi]
```

Constructor tạo `ArrayList` riêng, giúp tách thay đổi cấu trúc list ở caller khỏi list nội bộ. Getter trả `List.copyOf(names)` thay vì trao trực tiếp mutable list gốc. Đây là bản sao nông về phần tử; với `String` immutable trong ví dụ thì phù hợp, nhưng với mutable element objects vẫn phải xem có cần copy từng phần tử không.

**Liên hệ với access level:** private field và defensive copying cùng phục vụ đóng gói, nhưng giải quyết **hai vấn đề khác nhau**: quyền đặt tên field trong source và aliasing của mutable objects.

## 14. Public interface và implementation: công khai hợp đồng, giấu chi tiết

Khi các client không cần phụ thuộc concrete class, một interface public có thể là ranh giới API tốt:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("sent:" + message);
    }
}
```

Đây là **khai báo class/interface hợp lệ** trong cùng package, chưa có `main`. Trong chương trình lớn có client ở package khác, interface sẽ được khai báo `public` trong file riêng (theo quy tắc tên file), còn concrete implementation có thể để **package-private** nếu được cung cấp thông qua factory.

Khi implement method public của interface, implementation method phải **public**, không được thu hẹp thành package-private hoặc protected. `@Override` giúp compiler kiểm tra ý định.

### Ví dụ runnable minh họa factory trả về interface

Tạo tệp **`NotifierDemo.java`**:

```java
interface Notifier {
    void send(String text);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("notify:" + text);
    }
}

final class NotifierFactory {
    private NotifierFactory() {
    }

    static Notifier create() {
        return new ConsoleNotifier();
    }
}

public class NotifierDemo {
    public static void main(String[] args) {
        Notifier notifier = NotifierFactory.create();
        notifier.send("ready");

        // Client không cần tự tạo ConsoleNotifier.
    }
}
```

```bash
javac NotifierDemo.java
java NotifierDemo
```

```text
notify:ready
```

Ở đây tất cả helper top-level types package-private vì ví dụ một tệp chỉ có client cùng package. Trong thư viện đa package, có thể đặt `Notifier` là public interface, cung cấp một public factory API, nhưng giữ `ConsoleNotifier` package-private như implementation detail.

Việc chọn **public interface + hidden implementation** cho phép thay cách thông báo (console, file, network) mà caller vẫn chỉ biết `Notifier.send`. Không nên tạo interface chỉ để “có interface”; nó hữu ích khi thực sự cần abstraction/đa implementation hoặc ổn định ranh giới phụ thuộc.

## 15. `protected field` thường là lựa chọn dễ làm API khó bảo trì

Giả sử superclass có:

```java
class BaseCounter {
    protected int count;
}
```

Các subclass có thể phụ thuộc trực tiếp vào cách lưu `count`. Nếu sau này đổi lưu thành `AtomicInteger`, computed property hoặc dữ liệu tách nhiều field, có thể phải sửa subclass.

Một phương án tốt hơn:

```java
abstract class BaseCounter {
    private int count;

    protected final void addCount(int delta) {
        if (delta < 0) {
            throw new IllegalArgumentException("negative delta");
        }
        count += delta;
    }

    public final int count() {
        return count;
    }
}
```

Giờ subclass được cấp **hành vi mở rộng có kiểm soát** `addCount` chứ không được gán trực tiếp field. Method `protected final` là một phần hợp đồng mở rộng: subclass gọi được khi access hợp lệ, nhưng không override nó để bỏ qua validation.

Tất nhiên, thêm một protected method vẫn làm tăng API surface cho subclass. Nếu ngay cả subclass cũng không cần quyền đó, hãy giữ method `private` thay vì “mở trước phòng khi cần”.

## 16. `private` không ngăn truy cập hợp lệ trong enclosing class và nest

Một private nested class có thể được class bao ngoài sử dụng bình thường:

Tệp **`PrivateHelperDemo.java`**:

```java
public class PrivateHelperDemo {
    private static class Formatter {
        private static String format(int value) {
            return "[" + value + "]";
        }
    }

    public static String display(int value) {
        return Formatter.format(value);
    }

    public static void main(String[] args) {
        System.out.println(display(42));
    }
}
```

```bash
javac PrivateHelperDemo.java
java PrivateHelperDemo
```

```text
[42]
```

`Formatter` là private member class; mã của enclosing `PrivateHelperDemo` được phép gọi private helper theo các quy tắc liên quan. Nhưng client ngoài không được dùng `PrivateHelperDemo.Formatter` như một public type.

**Đừng nhầm `private` với “chỉ code trong chính phần thân lớp con đó mới truy cập được”.** Trong Java, các quan hệ enclosing/nestmates có quy tắc truy cập private phù hợp; điều này cho phép một class công khai sử dụng private nested helpers mà không phải mở API cho caller ngoài.

Một static nested class không cần enclosing instance; member inner class không static có một enclosing instance thích hợp. Quy tắc về **static vs inner** độc lập với **private vs public**.

## 17. `public` ở cấp module: vẫn cần ranh giới package exports

Với Java 9+ có named modules, một top-level class `public` trong **package chưa export** có thể không accessible từ module khác khi dùng module path.

Ví dụ cấu hình:

```java
module store.core {
    exports store.api;
}
```

Module `store.core` chỉ export `store.api`. Lớp `public class StoreService` trong `store.api` có thể tạo API cho module client phụ thuộc thích hợp; một class public trong `store.internal` **không tự trở thành API ngoài module** khi package ấy không export.

Module khách hàng có thể khai báo:

```java
module store.client {
    requires store.core;
}
```

Hai đoạn trên là **nội dung minh họa của `module-info.java`**, không phải class Java có `main`. Chúng cho thấy cần thiết kế **hai tầng visibility**:

1. Java access modifier trên type/member.
2. Ranh giới module và package exports/requires, nếu dùng JPMS.

`exports` không biến các type package-private thành public; nó cho phép các **public types** trong package được truy cập theo quy tắc module. `opens` chủ yếu liên quan deep reflection; nó không phải từ khóa thay thế cho `public` trong mã nguồn thường.

**Mẹo thiết kế:** package nội bộ không cần cho các module khác sử dụng thì không export. Đừng mở rộng export chỉ để “mọi class public đều dùng được” nếu không phải chủ đích API.

## 18. Test có phải lý do hợp lệ để tăng visibility không?

Đây là câu hỏi thực tế: một helper private khó kiểm thử trực tiếp, có nên đổi thành public không?

**Thường không nên tăng thành public chỉ để test một implementation detail.** Thay vào đó hãy cân nhắc:

- **Kiểm thử qua public/protected contract**: test hành vi mà người dùng API được phép quan sát, không gắn chặt test với chi tiết helper.
- **Package-private seam**: nếu một phần logic có vai trò độc lập và nhiều class cùng package thực sự cần dùng, package-private helper có thể vừa hợp thiết kế vừa dễ test trong package phù hợp.
- **Tách trách nhiệm ra type riêng**: nếu private helper lớn đến mức cần nhiều test độc lập, có thể class đang đảm nhiệm quá nhiều việc.
- **Dependency injection/strategy**: nếu cần thay dependency trong test, hãy tạo abstraction thích hợp thay vì công khai mọi state.
- **Tránh reflection để gọi private chỉ vì tiện**: test phụ thuộc quá sâu implementation sẽ dễ gãy khi refactor.

Không có quy tắc rằng mọi private method phải có unit test trực tiếp. Đối tượng cần kiểm thử thường là **hợp đồng hành vi** của lớp; chi tiết triển khai có thể được kiểm tra gián tiếp nếu đủ độ phủ.

### Test trong cùng package chưa hẳn là lỗi thiết kế

Với package-private class/method, test có thể khai báo cùng package để truy cập. Điều này có thể hợp lý khi package là một đơn vị implementation cần kiểm tra. Nhưng nếu module thực tế còn áp hạn chế khác, cấu hình test/runtime phải được cân nhắc; không tự thay đổi mọi modifier chỉ để vượt qua cấu hình build.

## 19. Khi nào không nên dùng `private` bằng mọi giá?

“Nhỏ nhất đáp ứng nhu cầu” không phải “mọi thứ đều private”. Có những nhu cầu hợp lệ đòi scope rộng hơn:

- **Phương thức implement public interface** phải accessible theo hợp đồng, thường là `public`.
- **Subclass thực sự được hỗ trợ** cần extension points có scope thích hợp, có thể `protected`.
- **Các lớp đồng nghiệp cùng package** cần dùng một helper cấp package thì package-private hợp lý.
- **Public API** cần cho client bên ngoài dùng type, constructor, method đúng mục đích.
- **Framework/serializer/DI** có thể có yêu cầu truy cập riêng; cần đọc contract của framework rồi chọn mức vừa đủ, không mặc định mở toàn bộ dữ liệu.
- **Các mô hình dữ liệu đơn giản** như record công khai có thể chủ động phơi bày các component accessors theo contract; không có lý do phải cất tất cả sau một lớp wrapper phức tạp.

**Điểm quyết định:** phạm vi rộng hơn phải có **lý do sử dụng được nêu rõ**. Nếu viết `protected` hoặc `public` mà không giải thích được client hoặc subclass nào cần dùng, hãy xem lại thiết kế.

## 20. Access modifiers và override: không được thu hẹp quyền tùy ý

Nếu superclass có method `public` và subclass override, method override **không được giảm** xuống `protected`, package-private hoặc `private`.

Ví dụ:

```java
class Parent {
    public String title() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String title() {
        return "child";
    }
}
```

Lớp con hợp lệ vì giữ `public`. Nếu đổi method ở `Child` thành `protected String title()`, compiler báo lỗi giảm visibility. Với protected method superclass, subclass có thể giữ `protected` hoặc **mở rộng `public`** nếu phù hợp, nhưng không giảm mức xuống package-private/private.

**Vì sao?** Client có biến kiểu `Parent` phải tiếp tục gọi được method public theo hợp đồng supertype, bất kể object runtime thuộc subclass nào. Nếu override được quyền thu hẹp, substitutability của API sẽ bị phá.

### `private` method của superclass không phải extension point

`private void work()` không được override thông thường bởi subclass. Một subclass tự khai báo `void work()` cùng tên/chữ ký có thể là **method mới**, không phải override private method cha. Annotation `@Override` giúp phát hiện nhầm lẫn này.

Khi thiết kế base class, **đừng mở method private thành protected chỉ vì “muốn subclass override cho linh hoạt”** nếu quy trình không thực sự hỗ trợ thay đổi hành vi đó. Mỗi protected overridable method là một extension contract cần duy trì.

## 21. Read-only field, constants và access tối thiểu

Đối với constant thực sự là một phần công khai của API, có thể dùng `public static final`:

```java
public final class Protocol {
    public static final int VERSION = 2;

    private Protocol() {
    }
}
```

Nhưng không nên công khai mutable static field:

```java
// public static int retryCount = 3;
// Mã ngoài có thể gán bất kỳ giá trị nào nếu class accessible.
```

Với tham chiếu mutable, `public static final List<String> NAMES` **không** đảm bảo list bất biến: `final` chỉ cấm gán lại field, các phần tử/structure có thể vẫn thay đổi nếu list hỗ trợ mutation.

Thường tốt hơn:

```java
public final class Defaults {
    private static final java.util.List<String> INTERNAL =
            java.util.List.of("A", "B");

    private Defaults() {
    }

    public static java.util.List<String> names() {
        return INTERNAL;
    }
}
```

`List.of` trả unmodifiable list theo contract. Trong ví dụ thành phần là String immutable nên API này có thể trả thẳng list ấy mà không cho caller thay đổi structure. Tuy nhiên một list unmodifiable chứa mutable objects **không tự làm các phần tử immutable**.

**Nguyên tắc chọn:** public constant chỉ khi nó thuộc hợp đồng thật; mutable state nên giữ private và kiểm soát thay đổi qua API thích hợp. Tên constant “viết hoa” không mang lại access control.

## 22. Ưu và nhược điểm khi thay đổi phạm vi về sau

Nếu một declaration từ `private` được nâng thành `public`, nhiều code client có thể bắt đầu phụ thuộc vào nó. Khi cần thu hẹp lại, thay đổi đó có thể phá vỡ source compatibility hoặc binary compatibility của thư viện.

| Quyết định | Lợi ích | Cái giá cần cân nhắc |
| --- | --- | --- |
| Giữ `private` | Dễ refactor detail, bảo vệ invariant | Những client cần thật sự phải qua API |
| Dùng package-private | Hợp tác trong package, tránh mở rộng API ngoài | Phụ thuộc giữa các class cùng package vẫn cần quản lý |
| Dùng `protected` | Hỗ trợ subclass extension có chọn lọc | Gia tăng hợp đồng kế thừa; khó đổi implementation |
| Dùng `public` | Dễ dùng từ mọi client accessible | Hợp đồng API rộng, có thể khó thu hẹp về sau |

**Thực hành tốt:** khi mở một declaration, xem nó như một quyết định kiến trúc cần lý do. Khi thu hẹp, rà soát tất cả caller hợp lệ và tương thích API; trong thư viện đã phát hành, cần cân nhắc migration thay vì sửa modifier đột ngột.

## 23. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Cho mọi method public là tiện nhất” | Làm tăng coupling và hợp đồng phải duy trì |
| “Mọi field private thì bắt buộc phải có getter/setter” | Chỉ công khai những hành vi cần thiết; setter có thể phá invariant |
| “Không ghi modifier nghĩa là private” | Không: đó là package-private |
| “Package-private chỉ dùng trong một tệp” | Dùng được bởi code thích hợp trong **cùng package** |
| “Subpackage là cùng package” | `x.y` khác `x.y.z` |
| “Protected chỉ code subclass truy cập được” | Code cùng package cũng có thể truy cập protected |
| “Protected cho subclass ở package khác dùng qua mọi Base receiver” | Có ràng buộc cross-package/receiver riêng |
| “Top-level class có thể private nếu muốn giấu” | Không; top-level chỉ public hoặc package-private |
| “Public class có constructor public tự động dù đã viết no-arg constructor” | Constructor explicit không có modifier là package-private |
| “Public nested class tự accessible dù outer không accessible” | Phải xét cả chuỗi enclosing types |
| “Private nested class vô dụng vì outer cũng không dùng được” | Enclosing class/nestmates có quyền private access phù hợp |
| “`static` là mức truy cập” | `static` không phải access modifier |
| “`final` trên tham chiếu khiến mutable object bất biến” | Chỉ ngăn gán lại biến/field; cần thiết kế immutability riêng |
| “Public field an toàn nếu đặt tên rõ” | Caller vẫn có thể sửa bypass validation |
| “`private final List` không thể bị thay đổi từ caller” | Nếu chia sẻ mutable list qua alias, caller vẫn có thể mutate object đó |
| “Đổi thành protected để test trực tiếp là luôn đúng” | Test là một yếu tố, không phải lý do tự động mở extension surface |
| “Interface implementation có thể thu hẹp public method” | Override/implementation phải giữ access hợp lệ |
| “Public type trong unexported JPMS package tự được module khác dùng” | Ranh giới exports/requires vẫn áp dụng |
| “Access modifier đảm bảo bảo mật trước mọi reflection” | Đây chủ yếu là access kiểm tra theo ngôn ngữ; reflection/module có quy tắc riêng |
| “Ít public nhất bằng mọi giá là thiết kế tốt nhất” | Cần cân đối với nhu cầu client/subclass thực sự |

## 24. Bài thực hành tổng hợp: đóng gói theo nhu cầu

Hãy đọc bài toán: một hệ thống quản lý đơn hàng có:

- Một kiểu `Order` mà code ở các package khác phải tạo và thanh toán.
- Một logic kiểm tra mã đơn chỉ cần trong `Order`.
- Một class `OrderFormatter` chỉ được lớp khác **cùng package** sử dụng.
- Không có yêu cầu subclass ghi đè quy trình thanh toán.
- Một kiểu kết quả `Receipt` mà caller bên ngoài được đặt tên và đọc thông tin.

Đề xuất:

1. `Order` là **public top-level class**.
2. Field state của `Order` là **private**.
3. Constructor và method `pay` là **public** nếu caller cần.
4. Method kiểm tra nội bộ là **private**.
5. `OrderFormatter` là **package-private top-level class** nếu nhiều class cùng package cần; nếu chỉ `Order` cần thì có thể dùng private nested helper.
6. `Receipt` là **public static nested class** (hoặc public top-level type) nếu caller phải dùng tên; constructor có thể thu hẹp khi chỉ `Order` tạo.
7. Không cần `protected` khi class không thiết kế cho subclass.

### Ví dụ runnable một tệp cho core behavior

Tệp **`OrderAccessDemo.java`**:

```java
import java.util.Objects;

final class Order {
    private final String code;
    private boolean paid;

    Order(String code) {
        this.code = requireCode(code);
    }

    private static String requireCode(String raw) {
        Objects.requireNonNull(raw, "code");
        if (raw.isBlank()) {
            throw new IllegalArgumentException("blank code");
        }
        return raw;
    }

    Receipt pay() {
        if (paid) {
            throw new IllegalStateException("already paid");
        }
        paid = true;
        return new Receipt(code);
    }

    static final class Receipt {
        private final String code;

        private Receipt(String code) {
            this.code = code;
        }

        String display() {
            return "paid:" + code;
        }
    }
}

public class OrderAccessDemo {
    public static void main(String[] args) {
        Order order = new Order("O-1");
        Order.Receipt receipt = order.pay();

        System.out.println(receipt.display());
        // order.paid = false; // Lỗi: field private.
        // Order.Receipt r = new Order.Receipt("x"); // Lỗi: private constructor.
    }
}
```

```bash
javac OrderAccessDemo.java
java OrderAccessDemo
```

```text
paid:O-1
```

**Vì sao `Order` và `Receipt` package-private trong bản demo?** Ở chương trình một tệp, không có nhu cầu từ package khác; nên giữ mức vừa đủ. Khi biến ví dụ thành thư viện cho client package khác, cần chuyển `Order` thành `public` top-level trong `Order.java`, đổi access của constructor/`pay`, và nếu client cần đặt tên `Receipt` thì khai báo `public static final class Receipt` với method accessor public. Vẫn nên giữ `code`, `paid` và validation helper private; constructor `Receipt` có thể private để chỉ `Order` tạo.

Bài thực hành này cố ý phân biệt **access tối thiểu của ví dụ trong cùng package** với **access cần thiết của API đa package** — chính cách chọn scope theo consumer thật.

## 25. Tự kiểm tra: 15 câu hỏi kèm đáp án

**Câu 1.** Nếu field chỉ được dùng để lưu state nội bộ của một object, mức nào nên cân nhắc trước?

**Đáp án:** `private`; cung cấp behavior API phù hợp nếu caller cần tương tác.

**Câu 2.** Một helper method chỉ do các method của chính lớp gọi có cần public không?

**Đáp án:** Không. Thường nên `private`.

**Câu 3.** Top-level helper chỉ được nhiều class cùng package dùng nên chọn gì?

**Đáp án:** Package-private top-level class là lựa chọn tự nhiên nếu không cần public API.

**Câu 4.** Có thể viết `private class Parser { }` ở cấp tệp không?

**Đáp án:** Không. Top-level class chỉ được public hoặc package-private. Muốn private helper type, dùng private member class trong một class phù hợp.

**Câu 5.** `protected` có phải lựa chọn mặc định cho mọi class dự kiến “biết đâu sau này có subclass” không?

**Đáp án:** Không. Chỉ mở protected khi có extension contract cụ thể.

**Câu 6.** Tại sao public getter trả thẳng mutable list có thể phá đóng gói?

**Đáp án:** Caller có thể mutate **cùng list object** qua alias dù field chứa tham chiếu được khai báo private.

**Câu 7.** `final List<String> names` có bảo đảm không ai sửa list không?

**Đáp án:** Không. `final` ngăn gán lại biến/field; khả năng mutation phụ thuộc object list.

**Câu 8.** Một public class có `X() {}` nhưng không ghi public; caller package khác có `new X()` được không?

**Đáp án:** Không. Constructor explicit không modifier là package-private.

**Câu 9.** Class implement interface có method public contract; bản implementation có được để protected không?

**Đáp án:** Không. Access không được giảm so với public method contract.

**Câu 10.** `protected field` ở superclass có phải luôn đọc được bằng `other.field` từ subclass khác package không?

**Đáp án:** Không. Có quy tắc receiver đặc thù cho protected access qua subclass ở package khác.

**Câu 11.** Nếu package `shop.internal` không được export từ named module, `public class Helper` có tự accessible từ module khác không?

**Đáp án:** Không theo truy cập module thông thường; còn cần exports/requires phù hợp.

**Câu 12.** Client cần thao tác tạo object nhưng không cần biết constructor, dùng kỹ thuật gì?

**Đáp án:** Public static factory với constructor private/package-private là một lựa chọn.

**Câu 13.** Có nên công khai setter `setBalance(int)` vô điều kiện chỉ vì field `balance` private?

**Đáp án:** Không. Nên công khai hành vi nghiệp vụ có validation phù hợp, ví dụ `deposit(int)`.

**Câu 14.** Vì sao thu hẹp một public API member có thể gây vấn đề?

**Đáp án:** Client đã phụ thuộc vào khả năng truy cập cũ có thể không biên dịch hoặc không liên kết được với phiên bản mới.

**Câu 15.** Tiêu chí cuối cùng để chọn access level là gì?

**Đáp án:** **Nhu cầu sử dụng hợp lệ nhỏ nhất** của caller, package hoặc subclass kết hợp với khả năng bảo vệ invariant và ổn định contract; không phải “modifier nào làm qua lỗi nhanh nhất”.

## 26. Checklist code review: đã mở quá rộng chưa?

Trước khi duyệt class mới hoặc thay access modifier, kiểm tra:

- [ ] Top-level class chỉ public nếu client ngoài package cần trực tiếp dùng?
- [ ] Những helper types không công khai đã được giữ package-private/private member phù hợp?
- [ ] Mọi instance field có cần public/protected không, hay private là đủ?
- [ ] Các getter/setter công khai có thực sự là hợp đồng API, và có bảo vệ invariant?
- [ ] Constructor có cần public không, hay static factory hoặc access hẹp phù hợp hơn?
- [ ] Method private được giữ private nếu chỉ implementation dùng?
- [ ] Method/package helper chỉ mở package-private khi cùng package thật sự cần?
- [ ] Protected method/constructor có documented extension contract và đã thử subclass khác package?
- [ ] Public API có kiểu trả về/tham số accessible cho client dự kiến?
- [ ] Các override tuân thủ quy tắc không giảm visibility?
- [ ] Mutable internal state có bị lộ qua reference, array/list hoặc getter?
- [ ] `final`/`static`/`abstract` có bị nhầm với access modifier?
- [ ] Package-private có bị hiểu nhầm là áp dụng cho subpackage?
- [ ] Nếu là JPMS, chỉ những API packages cần thiết được export?
- [ ] Thay đổi access có cần migration/compatibility review?
- [ ] Có tăng access chỉ để thuận tiện cho test thay vì sửa thiết kế?
- [ ] Có đoạn client nào đáng lẽ gọi API cấp cao nhưng lại phụ thuộc helper implementation?
- [ ] Đã chạy ví dụ/kiểm tra quyền từ góc nhìn consumer thật?

---

**Ghi nhớ cuối bài:** **Chọn quyền truy cập nhỏ nhất đáp ứng nhu cầu** là đặt ra ranh giới của hợp đồng lớp. `private` để giữ implementation và state nội bộ; package-private để phối hợp trong package; `protected` khi có nhu cầu mở rộng hợp lệ cho subclass; `public` khi phải hỗ trợ client bên ngoài. Với top-level class chỉ có public và package-private; với member class có đủ bốn mức. Đừng mở rộng access để giải quyết nhanh lỗi biên dịch nếu việc đó buộc client phụ thuộc chi tiết triển khai hoặc làm mất cơ hội bảo vệ invariant. Thiết kế tốt là **mở đúng hành vi cần thiết, giữ phần còn lại bên trong**.