# Phạm vi truy cập `public`, `protected`, package-private và `private` trong Java

Trong Java, **access modifier** quy định mã ở đâu được phép tham chiếu đến một kiểu, constructor, field hoặc method. Chọn đúng phạm vi truy cập là nền tảng của **đóng gói (encapsulation)**: che giấu trạng thái và chi tiết cài đặt, chỉ công bố những thao tác mà lớp khác thực sự cần. Phạm vi truy cập được kiểm tra bởi trình biên dịch và còn chịu các quy tắc kiểm tra truy cập khi liên kết/chạy chương trình.

## 1. Bảng so sánh nhanh

| Nơi truy cập đến thành viên được khai báo | `public` | `protected` | package-private (không ghi modifier) | `private` |
| --- | :---: | :---: | :---: | :---: |
| Bên trong lớp khai báo (kể cả các lớp lồng nhau theo quy tắc nestmate) | ✓ | ✓ | ✓ | ✓ |
| Lớp khác trong **cùng package** | ✓ | ✓ | ✓ | ✗ |
| Lớp con ở **package khác** | ✓ | ✓* | ✗ | ✗ |
| Lớp bất kỳ ở **package khác**, không có quan hệ kế thừa | ✓ | ✗ | ✗ | ✗ |

Dấu ✓* có điều kiện quan trọng: từ package khác, lớp con chỉ truy cập thành viên `protected` trong ngữ cảnh kế thừa và phải tuân theo quy tắc về **kiểu của biểu thức nhận** (xem mục 4). Bảng giả định bản thân kiểu chứa thành viên đã truy cập được; các rào cản của Java module cũng có thể áp dụng.

Thứ tự thường dùng để nhớ mức độ công khai của **thành viên lớp**:

```text
private  →  package-private  →  protected  →  public
ít nơi truy cập hơn                            nhiều nơi truy cập hơn
```

Đây là thứ tự về **tập đối tượng có quyền truy cập**, không phải lời khuyên luôn tăng mức độ công khai.

## 2. Ý nghĩa từng phạm vi

### `public`: công bố giao diện cho mã bên ngoài

Một thành viên `public` có thể được mã ở package khác truy cập nếu kiểu chứa nó và đường dẫn đến kiểu đó cũng truy cập được. Với ứng dụng dùng Java Platform Module System (JPMS), package của kiểu còn phải được module khai báo `exports` cho module đang gọi (trừ các trường hợp đặc biệt như code cùng module).

```java
package shop.api;

public class Product {
    public String name() {
        return "Notebook";
    }
}
```

Mã ở package khác có thể gọi `new Product().name()` khi thư viện được đưa vào classpath/module path phù hợp và package được công khai theo cấu hình module. **Không nên biến field trạng thái thành `public` chỉ để đọc nhanh**: điều đó tạo phụ thuộc vào cấu trúc bên trong và gây khó khăn khi cần kiểm soát bất biến.

### `protected`: chia sẻ cho cùng package và lớp con

Một field/method/constructor `protected` truy cập được bởi mọi lớp trong cùng package với lớp khai báo. Ngoài package đó, quyền truy cập dành cho mã bên trong subclass và chịu quy tắc đặc biệt ở mục 4. `protected` không có nghĩa “chỉ lớp con”: **mọi lớp cùng package**, dù không kế thừa, vẫn có thể truy cập.

```java
package shop.core;

public class Item {
    protected int stock = 5;

    protected int available() {
        return stock;
    }
}
```

Đặt `protected` khi lớp được thiết kế để mở rộng hợp lệ; nếu chỉ muốn công bố chức năng cho người dùng lớp, cân nhắc `public` method với state `private`.

### Package-private: chỉ những kiểu cùng package

Khi khai báo một thành viên hoặc kiểu cấp cao mà **không viết modifier truy cập**, Java dùng quyền truy cập *package-private*, thường gọi là *default access*. Không có từ khóa Java `package-private` hay `default` để khai báo cấp truy cập này.

```java
package shop.core;

class InventoryHelper {  // Kiểu cấp cao: package-private
    static int normalize(int count) { // Thành viên: package-private
        return Math.max(count, 0);
    }
}
```

Mọi mã thuộc **cùng package `shop.core`** có thể dùng `InventoryHelper` và `normalize` (nếu không vướng rào cản khác). Package con `shop.core.internal` là package khác; tên có tiền tố giống nhau không tạo quyền truy cập. Package được xác định bởi khai báo `package`, không phải quan hệ thư mục cha–con.

Package-private hữu ích cho các lớp cộng tác nội bộ, helper, mô hình cài đặt mà bạn không muốn đưa vào API công khai.

### `private`: che giấu chi tiết của lớp/nhóm lớp lồng nhau

Field, method hoặc constructor `private` chỉ có thể được mã trong phần khai báo lớp/kiểu chứa nó và các ngữ cảnh lồng nhau được ngôn ngữ cho phép truy cập. Java hỗ trợ truy cập `private` giữa các lớp thuộc cùng **nest** (ví dụ outer class và nested class của nó); đó không phải quyền truy cập của lớp khác cùng package.

```java
public class Wallet {
    private int balance;

    public Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        balance = initialBalance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    public int getBalance() {
        return balance;
    }
}
```

`balance` được bảo vệ bởi quy tắc cập nhật của lớp; mã bên ngoài không thể viết `wallet.balance = -100`. Quyền `private` cũng hữu ích cho constructor của factory, method phụ trợ và hằng số nội bộ. **Access control không thay thế xác thực, phân quyền nghiệp vụ hoặc mã hóa dữ liệu.**

## 3. Ví dụ chạy được: cùng package, khác package, subclass

Tạo bốn file theo cấu trúc:

```text
src/
  demo/
    api/
      Account.java
      SamePackage.java
    app/
      VipAccount.java
      Main.java
```

File `src/demo/api/Account.java`:

```java
package demo.api;

public class Account {
    public String owner = "Lan";
    protected int points = 10;
    String id = "A-01";           // package-private
    private int pin = 1234;

    public String maskedPin() {
        return "****";
    }

    protected String score() {
        return "P" + points;
    }

    String packageLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }

    public String inspect() {
        return id + ":" + secret(); // Được truy cập private trong chính lớp
    }
}
```

File `src/demo/api/SamePackage.java`:

```java
package demo.api;

public class SamePackage {
    public static String read(Account account) {
        return account.owner + " | " + account.points
                + " | " + account.id + " | " + account.maskedPin();
        // account.pin; // Lỗi: pin là private của Account
    }
}
```

`SamePackage` không kế thừa `Account`, nhưng vẫn đọc được `points` (`protected`) và `id` (package-private) vì cả hai lớp ở `demo.api`.

File `src/demo/app/VipAccount.java`:

```java
package demo.app;

import demo.api.Account;

public class VipAccount extends Account {
    public String vipInfo() {
        return owner + " | " + points + " | " + score()
                + " | " + maskedPin();
        // id;  // Lỗi: package-private, không thuộc package demo.app
        // pin; // Lỗi: private, không được kế thừa
    }

    public int pointsOf(VipAccount otherVip) {
        return otherVip.points; // Hợp lệ: kiểu biểu thức là VipAccount
    }

    // Sai nếu bỏ comment:
    // public int pointsOfAny(Account other) {
    //     return other.points; // Lỗi protected: kiểu biểu thức là Account
    // }
}
```

File `src/demo/app/Main.java`:

```java
package demo.app;

import demo.api.Account;
import demo.api.SamePackage;

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        VipAccount vip = new VipAccount();

        System.out.println(account.owner + " / " + account.maskedPin()
                + " / " + account.inspect());
        System.out.println(SamePackage.read(account));
        System.out.println(vip.vipInfo());
        System.out.println(vip.owner);

        // account.points; // Lỗi: protected, Main không là subclass
        // account.id;     // Lỗi: package-private khác package
        // account.pin;    // Lỗi: private
    }
}
```

Chạy trong thư mục dự án, với JDK 17 trở lên:

```bash
mkdir out
javac -d out src/demo/api/Account.java src/demo/api/SamePackage.java src/demo/app/VipAccount.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Kết quả chính xác:

```text
Lan / **** / A-01:hidden
Lan | 10 | A-01 | ****
Lan | 10 | P10 | ****
Lan
```

Các dòng bắt đầu bằng `//` chỉ minh họa những truy cập bị cấm; chúng không được thực thi và không gây lỗi biên dịch. Bỏ comment ở các biểu thức được đánh dấu “Lỗi” sẽ làm `javac` báo lỗi truy cập.

## 4. Bẫy quan trọng của `protected` khi khác package

Quy tắc `protected` thường gây nhầm lẫn nhất. Xét `Account` được khai báo ở `demo.api`, còn `VipAccount extends Account` ở `demo.app`:

- Trong `VipAccount`, `this.points`, `super.score()` hoặc `points` hợp lệ vì đang truy cập thành viên kế thừa từ subclass.
- Trong chính mã khai báo `VipAccount`, `otherVip.points` hợp lệ khi `otherVip` có **kiểu biên dịch** `VipAccount` hoặc một lớp con của nó.
- `otherAccount.points` **không hợp lệ** khi `otherAccount` có kiểu biên dịch `Account`, dù object thực tế có thể là `VipAccount`.
- Một lớp không kế thừa, nằm ở `demo.app`, không được đọc `account.points` chỉ vì cùng package với `VipAccount`.

Có thể nhớ: từ package khác, mã trong subclass được dùng `protected` để thao tác trên “nhánh đối tượng của chính subclass đó”; quyền này không cấp đặc quyền thao tác trên mọi instance của superclass.

**Constructor `protected` có ngoại lệ riêng:** subclass khác package có thể gọi `super(...)` để khởi tạo phần superclass; không vì vậy mà được tự do gọi `new Superclass(...)`. Constructor không được kế thừa. Tránh dùng quy tắc về receiver của field/method để suy luận sai về constructor.

## 5. Phạm vi truy cập áp dụng cho những khai báo nào?

| Loại khai báo | Những mức có thể khai báo trực tiếp | Ghi chú |
| --- | --- | --- |
| Lớp/interface/enum/record **cấp cao** (top-level) | `public` hoặc package-private | `protected` và `private` không hợp lệ cho top-level type. Một top-level public class/kiểu public khác tuân quy tắc tên tệp nguồn của Java. |
| Member field, method, constructor trong class | `public`, `protected`, package-private, `private` | Constructor không được kế thừa; kiểu truy cập của một thành viên còn bị giới hạn bởi khả năng truy cập kiểu bao ngoài. |
| Kiểu thành viên lồng trong class (member class/interface/enum/record) | Các mức được ngôn ngữ cho phép; class có thể dùng cả bốn | Các loại member type trong interface có quy tắc khác class. |
| Biến local, parameter, biến bắt trong `catch` | Không dùng bốn access modifier | Phạm vi của chúng do vị trí khai báo và block quyết định. |
| Thành viên trong interface | Quy tắc riêng | Xem mục 6. |

Ví dụ top-level class `public class Customer` thường được lưu ở `Customer.java`. Một file nguồn có thể chứa các top-level type package-private bổ trợ (tuân giới hạn số kiểu public). `private class Customer` hoặc `protected class Customer` ở cấp cao nhất gây lỗi biên dịch.

Trong một lớp, **kiểu bên ngoài cũng phải truy cập được**. Ví dụ: `public` method của class package-private không làm cho class đó tự động thành API truy cập được từ package khác. Tương tự, public nested class nằm trong private enclosing type vẫn chịu rào cản của enclosing type.

## 6. Interface và các trường hợp mặc định dễ nhầm

Interface có quy tắc chặt hơn class:

- Field khai báo trong interface luôn ngầm định là `public static final`. Không thể khai báo field instance `private` hoặc `protected` trong interface.
- Method abstract thông thường của interface ngầm định là `public abstract` (trừ các loại method đặc biệt hợp lệ theo cú pháp); class triển khai phải dùng `public`, không được giảm xuống package-private.
- Method `default` và `static` thông thường trong interface là `public`. Từ khóa `default` ở đây **không** có nghĩa là quyền package-private.
- Từ Java 9, interface được có **`private` instance method** và **`private static` method** hỗ trợ tái sử dụng logic bên trong interface; chúng không phải API cho class triển khai.
- Kiểu thành viên khai báo trong interface ngầm định `public static`; không khai báo member type `private`/`protected` theo cách của class.

Ví dụ độc lập, lưu file `Greeting.java`:

```java
public interface Greeting {
    String PREFIX = "Hi"; // public static final

    default String greet(String name) {
        return decorate(PREFIX + ", " + name);
    }

    private String decorate(String message) {
        return "[" + message + "]";
    }
}
```

`decorate` chỉ được gọi trong thân `Greeting`; lớp `implements Greeting` có thể gọi `greet` nhưng không được truy cập trực tiếp `decorate`. Với abstract method của interface, `void run();` về quyền truy cập tương đương `public abstract void run();`.

## 7. Kế thừa, override và mức độ truy cập

Khi ghi đè (override) một instance method được kế thừa, subclass **không được thu hẹp** quyền truy cập:

```java
class Parent {
    protected String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() { // Tăng từ protected lên public: hợp lệ
        return "child";
    }
}
```

Đổi `public String label()` của `Child` thành `private` hoặc package-private sẽ gây lỗi biên dịch. Với method `public` của superclass, bản override cũng phải `public`. Nếu một method ở superclass là package-private và subclass nằm ở **package khác**, method ấy không được kế thừa để override theo cơ chế thông thường; khai báo method trùng tên/chữ ký ở subclass có thể là một method riêng, nên không suy luận quyền truy cập bằng cách nhìn tên giống nhau. Dùng `@Override` để compiler phát hiện nhầm lẫn này.

`private` method của class không được kế thừa/override. Một method trùng chữ ký trong subclass là method khác (miễn các quy tắc khác được đáp ứng). `static` method có thể bị *hide* chứ không override; field cũng có thể bị *hide*. Access modifier không biến field thành đa hình.

**Điều kiện override độc lập khác:** `final` method không thể override; return type, checked exception và một số quy tắc chữ ký vẫn phải hợp lệ. Mức truy cập chỉ là một trong các kiểm tra.

## 8. Nested class và ngoại lệ `private`

Nested class giúp tổ chức phần cài đặt. Quyền `private` giữa outer class và member class lồng nhau được Java cho phép theo quy tắc lexical/nestmate; không có nghĩa toàn package được đọc thành viên riêng tư.

```java
public class Container {
    private int count = 7;

    private static class Reader {
        static int read(Container value) {
            return value.count;
        }
    }

    public int readCount() {
        return Reader.read(this);
    }
}
```

`Container.Reader` là kiểu lồng `private`; mã ngoài `Container` không thể gọi trực tiếp `Reader.read(...)`. Tuy vậy, `Reader` vẫn đọc được `count` của `Container`. Các lớp JVM hiện đại (Java 11+) có khái niệm *nestmates* hỗ trợ tình huống này; quyền ở cấp ngôn ngữ đã tồn tại từ trước.

## 9. Access modifier so với package, module và reflection

**Package:** hai class cùng dòng `package demo.api;` thuộc cùng package về mặt tên, nhưng trong hệ module có ràng buộc module/visibility bổ sung; không coi cách đặt trong cùng thư mục hoặc package con là bằng chứng có thể truy cập.

**Module (Java 9+):** `public` là điều kiện cần ở mức kiểu/thành viên, chưa chắc đủ để module khác dùng class đó. Ví dụ `module-info.java`:

```java
module shop.catalog {
    exports shop.api;
}
```

Module khác có quan hệ `requires shop.catalog;` có thể dùng public API trong `shop.api`, nhưng package nội bộ không `exports` không tự động thành API. `opens` chủ yếu phục vụ truy cập reflective ở runtime, không đồng nghĩa xuất API cho code Java thông thường.

**Reflection:** `setAccessible(true)` có thể cho phép một số hình thức truy cập phản chiếu khi môi trường/module cho phép; strong encapsulation của module có thể từ chối và ném `InaccessibleObjectException`. Không dựa vào `private` như rào cản an ninh chống mã độc cùng tiến trình; dùng kiểm tra phân quyền và ranh giới tin cậy thích hợp.

## 10. Cách chọn modifier trong dự án

Một cách ra quyết định thực tế:

1. **Mặc định thử `private`** cho trạng thái có thể thay đổi, helper method và constructor nội bộ; kiểm soát cách đọc/ghi bằng các method có nghĩa nghiệp vụ.
2. Chọn **package-private** cho lớp/cộng tác viên chỉ cần được dùng bởi những thành phần cùng package. Nó giảm bề mặt API mà không phải thêm nhiều getter vô ích.
3. Chọn **`protected`** khi superclass có hợp đồng mở rộng rõ ràng, cần cho subclass. Nên tài liệu hóa invariants và điểm mở rộng; field `protected` mutable dễ khiến subclass phá trạng thái, vì vậy thường ưu tiên method `protected` có kiểm soát.
4. Chọn **`public`** cho các loại và hành vi dự kiến được người dùng thư viện/sản phẩm sử dụng. Cân nhắc tính ổn định của API và khả năng thay đổi sau này.

Ví dụ cải thiện đóng gói:

```java
// Thiết kế dễ bị phá invariant:
public int balance;

// Thiết kế có kiểm soát (đặt trong một class):
private int balance;

public void deposit(int amount) {
    if (amount <= 0) throw new IllegalArgumentException();
    balance += amount;
}

public int balance() {
    return balance;
}
```

Đoạn trên minh họa **hai phương án tách biệt**, không phải chương trình Java độc lập để ghép nguyên xi (không được khai báo `balance` hai lần trong cùng class).

## 11. Lỗi thường gặp và cách kiểm tra

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`protected` chỉ cho subclass” | Mọi class cùng package cũng được truy cập. |
| “Subclass package khác được đọc `baseRef.protectedField` trên mọi `Base`” | Quy tắc receiver/kiểu biên dịch ở mục 4 giới hạn quyền. |
| “Package con thuộc cùng package” | `a.b` và `a.b.c` là hai package khác nhau. |
| “Không ghi modifier tương đương `private`” | Không ghi modifier là package-private, công khai cho cùng package. |
| “`default` method của interface có default access” | `default` là từ khóa của method có thân trong interface; method đó công khai theo quy tắc interface. |
| “`public` thành viên luôn gọi được từ bất kỳ đâu” | Kiểu bao ngoài, module và điều kiện truy cập khác vẫn phải thỏa mãn. |
| “Lớp con override được `private` method” | Method `private` không được kế thừa, nên không override. |
| “Override có thể giảm `public` xuống `protected`” | Java cấm giảm quyền truy cập khi override. |

Khi compiler báo `has private access`, `is not public ... cannot be accessed from outside package` hoặc `has protected access`, hãy xác định lần lượt: **kiểu khai báo thành viên → package của mã gọi → quan hệ subclass → kiểu biên dịch của receiver → khả năng truy cập kiểu bao ngoài/module**. Đừng chữa lỗi bằng cách đổi tất cả thành `public`.

## 12. Tự kiểm tra

**Tình huống A.** `p1.Base` có `protected void run()`; `p2.Child extends Base`. Trong một method của `Child`, `this.run()` có hợp lệ không? `new Base().run()` có hợp lệ không?

**Đáp án:** `this.run()` hợp lệ; `new Base().run()` không hợp lệ từ package khác vì receiver có kiểu `Base`.

**Tình huống B.** `p1.Helper` là top-level class không ghi access modifier; `p1.internal.UseHelper` có dùng được `Helper` không?

**Đáp án:** Không; `p1.internal` khác `p1`, nên không được tham chiếu top-level class package-private.

**Tình huống C.** Interface khai báo `void save();`. Class triển khai có thể định nghĩa `protected void save()` không?

**Đáp án:** Không. `save` trong interface là `public abstract`, vì vậy method triển khai phải là `public`.

**Điểm cần nhớ:** Quyền truy cập là một phần của thiết kế API. Chọn phạm vi nhỏ nhất đáp ứng nhu cầu thật, kiểm tra cẩn thận trường hợp `protected` khác package, và luôn xét đồng thời phạm vi truy cập của chính kiểu bao ngoài.