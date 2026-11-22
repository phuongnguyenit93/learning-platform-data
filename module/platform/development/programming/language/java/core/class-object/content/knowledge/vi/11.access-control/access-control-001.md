# `public`, `protected`, truy cập trong gói và `private` trong Java

**Kiểm soát truy cập (*access control*)** là một phần quan trọng của thiết kế class Java: nó quyết định **đoạn mã nào được phép tham chiếu đến kiểu, field, constructor và method nào**. Bốn mức truy cập quen thuộc khi học Java Core là **`public`**, **`protected`**, **truy cập trong gói (*package-private*)** và **`private`**.

Chọn mức truy cập phù hợp giúp class bảo vệ các bất biến (*invariants*), giảm phụ thuộc giữa các phần của chương trình và xác định ranh giới API. Không phải cứ có một object tham chiếu được là có quyền đọc mọi field của object đó: **kiểu và thành viên vẫn phải truy cập được từ vị trí mã nguồn đang viết**.

Bài học dành cho **Java 17+**, tập trung vào khai báo class và thành viên, phân biệt package với kế thừa, các điểm khó của `protected`, constructor, ghi đè method, nested classes, interface, modules và những lỗi biên dịch phổ biến. Những ví dụ có `main` đều kèm lệnh biên dịch và stdout dự kiến.

## 1. Bốn mức truy cập cơ bản

Với **field, method và constructor của một class thông thường**, có thể hình dung phạm vi truy cập từ rộng đến hẹp:

1. **`public`:** mã nguồn ở những vị trí có thể truy cập đến kiểu khai báo thành viên có thể sử dụng thành viên đó, với các điều kiện khác như Java module system.
2. **`protected`:** có thể sử dụng trong **cùng package**, và trong các **subclass ở package khác** theo những quy tắc chặt hơn về vị trí truy cập và kiểu receiver.
3. **Package-private (không ghi modifier truy cập):** các lớp và kiểu trong **cùng package** có thể sử dụng; không mở cho code ở package khác chỉ nhờ quan hệ kế thừa.
4. **`private`:** chỉ được sử dụng trong phạm vi khai báo được Java cho phép, về cơ bản là class/kiểu chứa khai báo và các ngữ cảnh nested liên quan; không phải mọi class cùng package đều truy cập được.

Ví dụ:

~~~java
package learning.model;

public class Profile {
    public String displayName;
    protected int score;
    String internalCode; // package-private
    private String passwordHash;

    public Profile() {
        displayName = "Khách";
        score = 0;
        internalCode = "NEW";
        passwordHash = "not-a-real-hash";
    }
}
~~~

Đây là **đoạn khai báo minh họa**, chưa có `main`. Bốn field khác nhau về phạm vi truy cập, nhưng tất cả thuộc cùng object `Profile`. Không modifier ở `internalCode` chính là **package-private**; **không viết `default String internalCode;`** để biểu diễn quyền truy cập mặc định.

### 1.1. Bảng quyền truy cập thường dùng

| Nơi viết code muốn truy cập một thành viên | `public` | `protected` | Package-private | `private` |
| --- | :---: | :---: | :---: | :---: |
| Trong chính class khai báo | Có | Có | Có | Có |
| Class khác cùng package, không cần kế thừa | Có | Có | Có | Không |
| Subclass thuộc package khác | Có | **Có điều kiện** | Không | Không |
| Class khác package, không phải subclass | Có | Không | Không | Không |

Dấu **“có điều kiện”** là điểm đặc biệt nhất của `protected`: một subclass ở package khác **không được dùng một tham chiếu superclass tùy ý để gọi protected instance member**. Phần riêng bên dưới sẽ có ví dụ biên dịch đúng và ví dụ sai.

Bảng này mô tả **quyền truy cập thành viên thông thường**, giả sử class chứa thành viên cũng có thể truy cập được và không bị giới hạn thêm bởi module. Quyền truy cập thành viên **không thể rộng hơn khả năng sử dụng kiểu chứa thành viên** từ vị trí caller.

## 2. Phân biệt `public`, `protected` và `private` với package-private

Giả sử có một class:

~~~java
package school.core;

public class Student {
    public String name = "Lan";
    protected int grade = 8;
    String schoolCode = "SCH-01";
    private String personalNote = "Riêng tư";
}
~~~

Những modifier ở đây điều khiển **ai được đọc hoặc gán field trực tiếp**. Việc một field `public` không có nghĩa nên công khai mutable state một cách tùy ý. Trong domain model, thường tốt hơn nếu dùng `private` field và một API phương thức có hợp đồng rõ ràng.

### 2.1. `public` không đồng nghĩa “mọi nơi đều gọi được bất kể hoàn cảnh”

Một thành viên `public` là thành viên được công khai theo quy tắc Java. Tuy nhiên:

- **Kiểu khai báo phải truy cập được:** một public method của một package-private top-level class không đột nhiên làm top-level class đó thành public.
- **Java Platform Module System (JPMS):** với code ở **named module** khác, package của public class còn cần được export thích hợp và module đọc được theo cấu hình.
- **Các điều kiện còn lại vẫn có hiệu lực:** method instance cần receiver hợp lệ, cú pháp/kiểu argument đúng, exception/contract và điều kiện chạy thực tế vẫn cần được đáp ứng.

Với ứng dụng Java đơn giản chạy trên classpath không dùng named modules, có thể hiểu gần đúng rằng public class/public member được truy cập từ các package khác.

### 2.2. `protected` không chỉ có nghĩa “chỉ subclass”

Một quan niệm phổ biến nhưng sai là “`protected` chỉ cho class con gọi”. Trong Java, **bất kỳ class nào cùng package** cũng có thể sử dụng protected member khi các điều kiện thông thường thỏa mãn, **dù không kế thừa** class khai báo.

Ngược lại, subclass ở package khác có quyền truy cập protected theo cơ chế kế thừa nhưng có **giới hạn receiver đặc biệt**. Đây là nguyên nhân nhiều ví dụ `protected` biên dịch đúng trong một package nhưng báo lỗi sau khi chuyển subclass sang package khác.

### 2.3. Package-private không phải `protected`

Khi không viết `public`, `protected` hoặc `private` trên một thành viên class thông thường, quyền truy cập của thành viên đó thường là **package access**. Các class khác **đúng cùng package** có thể truy cập, nhưng class con ở package khác **không được truy cập chỉ vì quan hệ `extends`**.

### 2.4. `private` không có nghĩa “chỉ cùng một object mới truy cập được”

Method trong **cùng class** có thể truy cập private field của **một instance khác thuộc chính class đó**:

~~~java
class PairNode {
    private int value;

    PairNode(int value) {
        this.value = value;
    }

    boolean sameValue(PairNode other) {
        return this.value == other.value;
    }
}
~~~

`other.value` hợp lệ trong `PairNode` dù `other` tham chiếu đến object khác. Quyền truy cập **được kiểm tra theo vị trí khai báo code**, không theo câu hỏi “object nhận lời gọi có phải là `this` không?”.

## 3. Package là ranh giới truy cập, không phải đường thư mục tùy ý

Khai báo package:

~~~java
package com.example.library;
~~~

Hai class khai báo trong **cùng package `com.example.library`** có thể truy cập package-private members của nhau theo quy tắc. Nhưng **`com.example.library.internal` không phải cùng package** với `com.example.library` — chỉ là một tên package có phần tiền tố giống nhau.

Ví dụ:

~~~text
com.example.library             (package A)
com.example.library.internal    (package B, KHÁC A)
com.example.app                 (package C, KHÁC A và B)
~~~

Các package trong Java không hình thành cây quyền truy cập theo kiểu “package cha tự cho phép subpackage truy cập”. Dấu chấm trong tên tạo ra cách đặt tên có phân cấp, **không cấp thêm quyền truy cập**.

### 3.1. Package-private áp dụng cho các class cùng package

~~~java
package com.example.library;

class CatalogIndex {
    static String normalize(String title) {
        return title.trim().toLowerCase(java.util.Locale.ROOT);
    }
}

public class Catalog {
    public String normalized(String title) {
        return CatalogIndex.normalize(title);
    }
}
~~~

Hai class được hiển thị chung để dễ học. Nếu lưu thành source Java thực tế, nên dùng hai tệp tương ứng hoặc giữ `CatalogIndex` là top-level package-private cùng tệp `Catalog.java` (hợp lệ vì chỉ `Catalog` là public top-level class).

`Catalog` và `CatalogIndex` cùng package nên `Catalog` sử dụng được class `CatalogIndex` và method package-private của nó. Trong một package khác, code không thể trực tiếp dùng `CatalogIndex` chỉ vì biết tên class và `import`.

**`import` không cấp quyền truy cập.** Nó chỉ giúp sử dụng tên kiểu theo quy tắc lookup; một class package-private vẫn không thể được sử dụng từ package khác dù đã cố import.

### 3.2. Package mặc định (unnamed package) không nên dùng cho mã nhiều package

Những tệp Java demo không có khai báo `package` thường được xem là thuộc **unnamed package** theo ngữ cảnh biên dịch. Điều này tiện cho ví dụ một tệp nhưng không phù hợp tổ chức ứng dụng nhiều package và có các giới hạn trong sử dụng từ named packages.

Với code dự án, hãy khai báo package rõ ràng và bố trí source path phù hợp, đặc biệt khi học về access control. Không dùng default package như cách “vượt” ranh giới visibility.

## 4. Ví dụ nhiều package: kiểm tra chính xác bốn mức truy cập

Đây là ví dụ Java 17+ có **bốn file nguồn trong hai package**, cố tình giữ các lời gọi không hợp lệ ở dạng comment để chương trình biên dịch và chạy được.

Cấu trúc tệp:

~~~text
src/
└── academy/
    ├── core/
    │   ├── Account.java
    │   └── Classmate.java
    └── app/
        ├── SpecialAccount.java
        └── Viewer.java
~~~

### 4.1. Tệp `src/academy/core/Account.java`

~~~java
package academy.core;

public class Account {
    private String secretCode() {
        return "PRIVATE";
    }

    String packageCode() {
        return "PACKAGE";
    }

    protected String protectedCode() {
        return "PROTECTED";
    }

    public String publicCode() {
        return "PUBLIC";
    }

    public String insideAccount() {
        return secretCode() + "/" + packageCode()
                + "/" + protectedCode() + "/" + publicCode();
    }
}
~~~

Trong **chính class `Account`**, method `insideAccount()` được phép gọi cả bốn member. `private` không ngăn code **của chính class** sử dụng member private.

### 4.2. Tệp `src/academy/core/Classmate.java`

~~~java
package academy.core;

import academy.core.Account;

public class Classmate {
    public static String inspect(Account account) {
        // account.secretCode(); // Lỗi: private

        return account.packageCode() + "/"
                + account.protectedCode() + "/"
                + account.publicCode();
    }
}
~~~

`Classmate` không kế thừa `Account` nhưng **cùng package `academy.core`**, vì vậy có thể gọi package-private, protected và public methods. Nó **không** được gọi private `secretCode()`.

### 4.3. Tệp `src/academy/app/SpecialAccount.java`

~~~java
package academy.app;

import academy.core.Account;

public class SpecialAccount extends Account {
    public String inheritedAccess() {
        // packageCode();      // Lỗi: package-private của package khác
        // secretCode();       // Lỗi: private

        return this.protectedCode() + "/" + this.publicCode();
    }

    public String inspectPeer(SpecialAccount other) {
        return other.protectedCode(); // Hợp lệ: receiver kiểu subclass
    }

    public String invalidReceiver(Account other) {
        // return other.protectedCode(); // Lỗi: receiver có kiểu Account
        return "Không truy cập qua Account reference";
    }
}
~~~

`SpecialAccount` nằm ở **package `academy.app`**, khác `academy.core` nhưng `extends Account`, vì vậy:

- `this.protectedCode()` hợp lệ từ code của subclass.
- `this.publicCode()` hợp lệ.
- `this.packageCode()` không hợp lệ vì method package-private ở package khác không được mở bởi việc kế thừa.
- `this.secretCode()` không hợp lệ vì private member không truy cập được trong subclass chỉ nhờ `extends`.
- `other.protectedCode()` trong `inspectPeer(SpecialAccount other)` hợp lệ vì `other` có **kiểu được phép theo protected receiver rule** tại ngữ cảnh `SpecialAccount`.
- `other.protectedCode()` trong `invalidReceiver(Account other)` **không hợp lệ**: mặc dù method đang nằm trong subclass, biểu thức receiver có compile-time type `Account`, không phải `SpecialAccount` hoặc subtype phù hợp.

Đây là một khác biệt cốt lõi so với câu đơn giản hóa “subclass truy cập được tất cả protected member của superclass”.

### 4.4. Tệp `src/academy/app/Viewer.java`

~~~java
package academy.app;

import academy.core.Account;
import academy.core.Classmate;

public class Viewer {
    public static void main(String[] args) {
        Account account = new Account();
        SpecialAccount special = new SpecialAccount();

        System.out.println("Inside = " + account.insideAccount());
        System.out.println("Same package = "
                + Classmate.inspect(account));

        System.out.println("Subclass = " + special.inheritedAccess());
        System.out.println("Peer = " + special.inspectPeer(
                new SpecialAccount()));

        System.out.println("Outside = " + account.publicCode());

        // account.packageCode();  // Lỗi: khác package
        // account.protectedCode(); // Lỗi: không phải subclass context
        // account.secretCode();    // Lỗi: private
    }
}
~~~

`Viewer` thuộc `academy.app`, không phải subclass của `Account`. Nó không được truy cập trực tiếp protected hoặc package-private member trong `Account`; tuy nhiên nó có thể gọi **public methods** của `Account` và `SpecialAccount`. Khi `Viewer` gọi `special.inheritedAccess()`, method **nằm trong subclass** tự thực hiện truy cập protected hợp lệ rồi trả dữ liệu cho caller — không phải `Viewer` được cấp quyền truy cập protected trực tiếp.

### 4.5. Biên dịch và chạy

Đứng tại thư mục chứa `src`, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 -d out src/academy/core/Account.java src/academy/core/Classmate.java src/academy/app/SpecialAccount.java src/academy/app/Viewer.java
java -cp out academy.app.Viewer
~~~

**Stdout chính xác:**

~~~text
Inside = PRIVATE/PACKAGE/PROTECTED/PUBLIC
Same package = PACKAGE/PROTECTED/PUBLIC
Subclass = PROTECTED/PUBLIC
Peer = PROTECTED
Outside = PUBLIC
~~~

Giải thích kết quả:

1. `Account.insideAccount()` được viết trong cùng class với tất cả member nên gọi được cả private, package-private, protected và public.
2. `Classmate.inspect(...)` ở cùng package gọi được package-private và protected, nhưng không private.
3. `SpecialAccount.inheritedAccess()` gọi protected trên `this` và public method, dù subclass khác package.
4. `inspectPeer(...)` gọi protected thông qua receiver có kiểu `SpecialAccount` phù hợp.
5. `Viewer` khác package và không kế thừa `Account`, nên trực tiếp gọi được method public `publicCode()`, chứ không được gọi ba method còn lại.

**Chú ý quan trọng về tính xác thực:** Những lời gọi gây lỗi được comment có chủ đích. Chỉ bỏ comment **một lời gọi cần thử** rồi chạy lại `javac` để quan sát compiler từ chối; nội dung lỗi chi tiết có thể khác theo phiên bản JDK.

## 5. `protected` khi lớp con nằm ở package khác

`protected` cho phép truy cập trong **cùng package** mà không cần kế thừa. Khi code truy cập nằm ở **package khác**, phải có **ngữ cảnh subclass hợp lệ**. Với protected **instance field/method** được khai báo trong superclass `C` và truy cập từ subclass `S` ở package khác, receiver của biểu thức có dấu chấm phải có kiểu tĩnh là `S` hoặc subtype của `S` theo quy tắc Java; không thể dùng một biến kiểu `C` tùy ý.

~~~java
// File pet/model/Animal.java
package pet.model;
public class Animal {
    protected void breathe() { System.out.println("Breathing"); }
}
~~~

~~~java
// File pet/client/Dog.java
package pet.client;
import pet.model.Animal;
public class Dog extends Animal {
    void demonstrate(Dog peer, Animal base) {
        this.breathe();       // Hợp lệ: receiver hiện tại.
        peer.breathe();       // Hợp lệ: peer có kiểu Dog.
        // base.breathe();    // Lỗi: receiver có kiểu Animal.
        super.breathe();      // Hợp lệ: gọi trên superclass part của this.
    }
}
~~~

Các khối trên mô tả **hai file Java riêng**, không đặt hai khai báo `package` trong cùng một file. Quan sát quan trọng: quyền `protected` không trao cho Dog quyền gọi `breathe` trên mọi Animal object từ package khác; Java kiểm tra ngữ cảnh code và **kiểu tĩnh receiver**, không suy đoán object runtime là Dog.

**Ngoại lệ cần phân biệt:** `protected static` members và `protected constructors` có điều kiện riêng, không áp dụng máy móc điều kiện receiver của instance members. Subclass có thể gọi protected superclass constructor qua `super(...)` khi hợp lệ; điều đó không cho phép gọi `new Animal(...)` tùy ý từ package khác. Phần protected receiver, casting, sibling subclasses và constructor edge cases được phân tích sâu trong bài chuyên đề về `protected` khác package.

## 6. Package-private member không mở cho subclass ở package khác

Ví dụ:

~~~java
// File: package-a/Base.java
package a;

public class Base {
    void internal() {
        System.out.println("Base internal");
    }

    protected void extendable() {
        System.out.println("Base protected");
    }
}
~~~

~~~java
// File: package-b/Derived.java
package b;

import a.Base;

public class Derived extends Base {
    public void run() {
        // internal(); // Không truy cập được: khác package
        this.extendable(); // Hợp lệ
    }
}
~~~

`internal()` là package-private, không được nhìn thấy từ `Derived` chỉ vì `Derived extends Base`. Nó không phải một method có quyền truy cập “giống protected nhưng không viết keyword”.

Nếu một subclass khác package khai báo một method mới tên `internal()` có cùng danh sách tham số, nó không đương nhiên ghi đè một package-private method không được kế thừa theo quy tắc overriding liên quan; đây có thể là một **method riêng**. Cẩn thận với annotation `@Override` và các rule về visibility khi làm việc với package-private members trong hierarchy nhiều package.

## 7. `private` bảo vệ chi tiết triển khai và bất biến

Một pattern thực tế là đặt state ở `private` rồi mở những **hành động hợp lệ** qua public methods:

~~~java
class Wallet {
    private long balance;

    Wallet(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = openingBalance;
    }

    public long balance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }
}
~~~

Ở ví dụ này:

- Caller không thể viết `wallet.balance = -100;` từ code ngoài class vì field `balance` private.
- Caller đọc trạng thái qua `balance()` và gửi yêu cầu cập nhật qua `deposit(...)`.
- `deposit` kiểm tra input trước khi thay đổi field, giúp duy trì invariant “balance không âm”.
- `private` **không tự bảo đảm** nghiệp vụ đúng: nếu chính code bên trong class viết `balance = -100` thì compiler vẫn cho phép. Invariant phải được bảo vệ bằng thiết kế và logic.

### 7.1. Private method và đối tượng cùng class

~~~java
class PasswordToken {
    private final String value;

    PasswordToken(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    private String normalized() {
        return value.trim();
    }

    boolean sameNormalizedValue(PasswordToken other) {
        return this.normalized().equals(other.normalized());
    }
}
~~~

`other.normalized()` hợp lệ vì mã được viết **bên trong chính class `PasswordToken`**, dù receiver là instance `other`. Đây không phải phạm vi truy cập package-wide hay public.

**Không lưu mật khẩu hoặc token thực như ví dụ string đơn giản này trong ứng dụng thật** mà không tuân theo yêu cầu bảo mật tương ứng. Ví dụ chỉ nhằm làm rõ phạm vi truy cập private.

### 7.2. Subclass không được truy cập private member trực tiếp

~~~java
class Parent {
    private int secret = 10;

    public int readSecret() {
        return secret;
    }
}

class Child extends Parent {
    int read() {
        // return secret; // Không hợp lệ: secret private
        return readSecret(); // Hợp lệ qua public API
    }
}
~~~

`Child` không thể gọi/đọc private field chỉ nhờ kế thừa. Nhưng method public/protected/package-access hợp lệ trong `Parent` có thể cung cấp hành vi cần thiết mà không làm lộ state riêng tư.

## 8. Mức truy cập đối với constructor

Constructor cũng có quyền truy cập, và điều đó ảnh hưởng nơi nào được phép viết `new ClassName(...)`.

~~~java
class Document {
    private final String id;

    public Document(String id) {
        this.id = id;
    }

    protected Document() {
        this("NEW");
    }

    Document(int number) {
        this(Integer.toString(number));
    }

    private Document(boolean internal) {
        this(internal ? "INTERNAL" : "EXTERNAL");
    }
}
~~~

Đây là đoạn khai báo minh họa; overload được phân biệt bằng tham số, không phải modifier. Ý nghĩa:

| Modifier của constructor | Ý định sử dụng thông thường |
| --- | --- |
| `public` | Cho phép tạo object từ code ngoài khi class/constructor truy cập được |
| `protected` | Cho phép trong cùng package và các cách gọi hợp lệ của subclass khác package |
| Package-private | Cho code cùng package tạo object |
| `private` | Kiểm soát đường tạo trong class/nested contexts hợp lệ, thường đi với factory |

### 8.1. Private constructor và static factory

~~~java
public final class OrderId {
    private final String text;

    private OrderId(String text) {
        this.text = text;
    }

    public static OrderId of(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return new OrderId(raw);
    }

    public String value() {
        return text;
    }
}
~~~

Đây là đoạn khai báo **public top-level class**; để biên dịch độc lập, lưu trong tệp `OrderId.java`. Code ngoài class không thể gọi `new OrderId("...")` vì constructor private. Thay vào đó, public factory `OrderId.of(...)` kiểm tra đầu vào và chủ động gọi private constructor.

**Private constructor không có nghĩa “không thể có instance”**; chính code có quyền truy cập (như factory trong class) vẫn tạo được instance.

### 8.2. Protected constructor ở package khác

~~~java
// File: api/BaseTask.java
package api;

public class BaseTask {
    protected BaseTask(String name) {
    }
}
~~~

~~~java
// File: app/CustomTask.java
package app;

import api.BaseTask;

public class CustomTask extends BaseTask {
    public CustomTask() {
        super("custom"); // Hợp lệ qua subclass constructor
    }

    public static void demo() {
        // new BaseTask("x"); // Không hợp lệ ở package khác
    }
}
~~~

Đây là hai tệp minh họa. **Cùng package** có cách truy cập protected constructor rộng hơn; **khác package** chỉ có quyền trong những ngữ cảnh khởi tạo subclass mà JLS cho phép. Không được xem `protected BaseTask(...)` tương đương public constructor.

## 9. Mức truy cập đối với top-level class và top-level interface

**Top-level class** và **top-level interface** không dùng được cả bốn mức truy cập. Trong source Java thông thường, chỉ có:

- `public`: kiểu có thể được sử dụng từ package khác nếu các điều kiện truy cập còn lại thỏa mãn.
- **Package-private** (không có access modifier): chỉ truy cập từ cùng package.

Ví dụ hợp lệ:

~~~java
package store.model;

public class Product {
}

class ProductValidator {
}

interface InternalPolicy {
}

public interface NamedProduct {
    String name();
}
~~~

Đoạn trên biểu diễn **nhiều khai báo top-level** để giải thích visibility. Nếu đặt trong source file thật, **không được có hai public top-level types** như `Product` và `NamedProduct` trong cùng một compilation unit `Product.java` theo quy tắc đặt file thông thường. Hãy đặt `Product` vào `Product.java` và `NamedProduct` vào `NamedProduct.java`, các package-private types có thể bố trí thích hợp.

**Không hợp lệ đối với top-level class/interface:**

~~~java
// private class Hidden { }   // Lỗi compile
// protected class Shared { } // Lỗi compile
~~~

`private` và `protected` chỉ được dùng với các **member types** trong những ngữ cảnh hợp lệ, không dùng cho top-level type. Quy tắc này khác với field, constructor và method.

### 9.1. Không có access modifier không phải “public ngầm”

Một top-level class viết `class Helper` (không `public`) có package access; nó **không trở thành public** chỉ vì class nằm trong file có tên `Helper.java`. Tương tự, một method trong class thông thường không ghi modifier truy cập sẽ là package-private, không phải public.

## 10. Nested classes có thể dùng bốn mức truy cập

Một **member class** nằm trong class khác có thể khai báo `public`, `protected`, package-private hoặc `private` nếu ngữ cảnh cho phép.

~~~java
public class Outer {
    public static class PublicNested {
    }

    protected static class ProtectedNested {
    }

    static class PackageNested {
    }

    private static class PrivateNested {
    }

    private final PrivateNested helper = new PrivateNested();
}
~~~

Tệp độc lập phù hợp tên `Outer.java`. Đây là khai báo có thể biên dịch trong Java 17.

Lưu ý:

- Mức truy cập của member type giới hạn nơi nào có thể **tham chiếu bằng tên kiểu**.
- Một public nested class trong một enclosing type không truy cập được từ bên ngoài **không tự vượt qua visibility của enclosing type**.
- Nested classes/inner classes có **quy tắc truy cập private giữa các ngữ cảnh nestmates**. Không nên phát biểu quá đơn giản rằng “private chỉ dùng trong một cặp ngoặc nhọn và không có ngoại lệ”.
- Local class và anonymous class có cú pháp/điều kiện riêng; không áp dụng máy móc bảng modifier của member class cho mọi loại class lồng nhau.

### 10.1. Outer và inner có thể truy cập private của nhau

~~~java
public class NestAccessDemo {
    private String text = "Outer";

    private class Inner {
        private String suffix = "Inner";

        private String combine() {
            return text + "+" + suffix;
        }
    }

    public String view() {
        Inner inner = new Inner();
        return inner.combine();
    }

    public static void main(String[] args) {
        System.out.println(new NestAccessDemo().view());
    }
}
~~~

Lưu `NestAccessDemo.java` và chạy:

~~~bash
javac NestAccessDemo.java
java NestAccessDemo
~~~

Stdout:

~~~text
Outer+Inner
~~~

`Outer` sử dụng private member của inner object, và `Inner` truy cập private field của outer object theo các quy tắc nested/nestmate của Java. Đây **không** phải vì chúng chỉ “cùng package”; một class bên ngoài không liên quan trong cùng package vẫn không được truy cập private members ấy.

## 11. Ghi đè phương thức và không được thu hẹp quyền truy cập

Khi một subclass **override** một instance method được kế thừa hợp lệ, nó không được chọn mức truy cập **hẹp hơn** mức cần thiết của method gốc.

~~~java
class Parent {
    protected Number value() {
        return 10;
    }
}

class Child extends Parent {
    @Override
    public Integer value() {
        return 20;
    }
}
~~~

Đây là đoạn khai báo hợp lệ: `protected` được **mở rộng** thành `public`, và return type `Integer` tương thích theo quy tắc covariant return với `Number`.

Các trường hợp:

| Method superclass | Method override ở subclass | Hợp lệ về mức truy cập? |
| --- | --- | --- |
| `public` | `public` | Có |
| `public` | `protected` | Không: thu hẹp |
| `public` | Package-private | Không: thu hẹp |
| `protected` | `public` | Có: mở rộng |
| `protected` | `protected` | Có |
| `protected` | `private` | Không: thu hẹp |
| Package-private cùng package | Package-private hoặc quyền rộng hơn | Có thể, nếu thỏa các quy tắc override khác |
| `private` | Method cùng tên ở subclass | Không phải override private method theo nghĩa thông thường |

Một class ở package khác có thể khai báo method trùng tên/chữ ký với **package-private method không kế thừa được**; đừng gọi đó là override hợp lệ chỉ vì tên giống nhau. Nếu đặt `@Override`, compiler giúp kiểm tra sự tồn tại của method cần override.

### 11.1. Ví dụ lỗi compile: giảm visibility

~~~java
class ParentApi {
    public void execute() {
    }
}

class HiddenApi extends ParentApi {
    // @Override
    // protected void execute() { } // Sai: yếu hơn public
}
~~~

Nếu bỏ comment hai dòng method trong `HiddenApi`, `javac` sẽ từ chối vì method override không thể giảm từ `public` xuống `protected`. Nguyên nhân là code đang được phép gọi `ParentApi.execute()` không được bất ngờ mất quyền đó khi object thực tế là `HiddenApi`.

### 11.2. Private method không được override như một instance method được kế thừa

~~~java
class Base {
    private String secret() {
        return "Base";
    }
}

class Derived extends Base {
    String secret() {
        return "Derived";
    }
}
~~~

`Derived.secret()` là method riêng của subclass, không phải override trực tiếp private method `Base.secret()` vì private member không được kế thừa như method overridable. Không gắn `@Override` với ý định override member private này.

## 12. Abstract classes và interface: quyền truy cập có quy tắc riêng

### 12.1. Abstract method không thể là private khi cần override

~~~java
abstract class Workflow {
    protected abstract void execute();

    public void run() {
        execute();
    }
}
~~~

`execute()` là protected abstract instance method: subclass có thể cung cấp implementation. Một method private không thể được subclass override để thực thi hợp đồng abstract theo cách này, nên `private abstract void execute();` không hợp lệ.

### 12.2. Interface methods không có cùng mặc định package-private như class methods

Trong interface Java:

- Một **abstract interface method** không ghi access modifier được ngầm hiểu là **`public`**, không phải package-private.
- **`default`** và **`static` interface methods** cũng có quy tắc public thích hợp; từ `default` ở đây là keyword cho implementation của interface method, **khác hoàn toàn** với “default access” trong class.
- Từ Java 9, interface có thể định nghĩa **private methods** để dùng chung code nội bộ giữa default/static methods theo điều kiện hợp lệ.
- Không dùng `protected` method trong interface như đối với class.
- Các field của interface được ngầm hiểu là **`public static final`**, không phải package-private hoặc private fields.

Ví dụ:

~~~java
interface Formatter {
    String format(String text); // public abstract (ngầm định)

    default String decorated(String text) {
        return "[" + normalize(text) + "]";
    }

    private String normalize(String text) {
        return text.trim();
    }
}

class UpperFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là khai báo Java 17 hợp lệ. Method `format` trong class triển khai **phải public** vì nó thực hiện interface method public; không thể giảm thành package-private chỉ bằng cách bỏ modifier. Method `normalize` là private helper của interface, không phải một phần API để class triển khai override.

**Đừng viết `private` trên một interface abstract method cần các lớp triển khai cung cấp implementation**; private interface method phải có thân code thích hợp và không là method abstract theo cơ chế đó.

## 13. Access control và đóng gói (*encapsulation*) không hoàn toàn giống nhau

`private`, package-private, `protected` và `public` là **cơ chế ngôn ngữ** để giới hạn nơi code có thể truy cập khai báo. **Encapsulation** là cách thiết kế API để che chi tiết và bảo vệ bất biến nghiệp vụ. Dùng modifier đúng là công cụ hỗ trợ, nhưng chưa đủ.

Ví dụ kém đóng gói:

~~~java
public class Cart {
    public java.util.List<String> items =
            new java.util.ArrayList<>();
}
~~~

Code khác có thể gọi `cart.items.clear()` hoặc `cart.items.add(null)` mà class không kiểm soát invariant. Đổi field thành `private` nhưng trả thẳng mutable list cũng còn vấn đề:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafeCart {
    private final List<String> items = new ArrayList<>();

    public List<String> getItems() {
        return items; // Caller vẫn có thể sửa object List nội bộ
    }
}
~~~

Một hướng thiết kế tốt hơn:

~~~java
import java.util.ArrayList;
import java.util.List;

class Cart {
    private final List<String> items = new ArrayList<>();

    public List<String> items() {
        return List.copyOf(items);
    }

    public void addItem(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("Tên item trống");
        }
        items.add(item);
    }
}
~~~

Caller chỉ nhận snapshot list không sửa được (với các phần tử `String` immutable), còn mọi thay đổi danh sách đi qua `addItem` có validation. **`private` bảo vệ quyền truy cập field, còn defensive copying bảo vệ khỏi aliasing mutable object**.

Không phải mọi class đều cần getter/setter cho mỗi field. Nếu một field phải tuân theo invariant, các **hành động nghiệp vụ cụ thể** thường an toàn hơn setter tùy ý.

## 14. Quyền truy cập không thay đổi đối tượng nào đang được xử lý

Modifier không phải cơ chế copy hoặc kiểm soát identity:

~~~java
class Counter {
    private int value;

    public void increment() {
        value++;
    }

    public int current() {
        return value;
    }
}
~~~

Nếu có:

~~~java
Counter first = new Counter();
Counter alias = first;
alias.increment();

System.out.println(first.current()); // 1
~~~

`first` và `alias` cùng trỏ một object, nên caller vẫn nhìn thấy thay đổi. `private int value` chỉ ngăn **code bên ngoài class trực tiếp viết `alias.value = ...`**, chứ không ngăn thay đổi hợp lệ qua public method `increment`.

Đồng thời, `private` không làm `value++` trở thành **thread-safe**. Nếu nhiều thread cùng dùng một instance, việc đồng bộ là trách nhiệm riêng; access modifiers không thay thế `synchronized`, lock hoặc atomic variable.

## 15. Quy tắc kiểm tra truy cập ở thời điểm biên dịch và runtime

Thông thường, compiler `javac` kiểm tra quyền truy cập khi bạn viết mã nguồn:

~~~java
package outside;

import academy.core.Account;

class UseAccount {
    void test(Account account) {
        account.publicCode();   // Hợp lệ
        // account.packageCode(); // Lỗi biên dịch
        // account.protectedCode(); // Lỗi biên dịch
        // account.secretCode(); // Lỗi biên dịch
    }
}
~~~

Đây là đoạn minh họa trong package thứ ba, giả sử class `academy.core.Account` từ ví dụ nhiều package đã được biên dịch.

Tuy nhiên, hệ thống JVM cũng có các kiểm tra linkage/access ở runtime. Nếu bytecode và các class bị thay đổi không tương thích (ví dụ một thư viện đổi member public thành private sau khi client đã biên dịch), có thể phát sinh lỗi như `IllegalAccessError` khi liên kết/chạy, không nhất thiết lỗi mã nguồn ở lúc bạn vừa viết file.

### 15.1. Reflection không có nghĩa là access modifier vô hiệu

Các API reflection có cơ chế tìm kiếm hoặc cố gắng truy cập non-public members, nhưng khả năng thành công phụ thuộc vào Java access checks, module boundaries, cấu hình runtime và các điều kiện bảo mật liên quan. Trên Java hiện đại, đặc biệt với named modules, không thể kết luận rằng cứ `setAccessible(true)` là luôn truy cập được mọi private member.

Để thiết kế class Java Core, hãy coi access modifiers là **hợp đồng API chuẩn**; không dùng reflection để né quy tắc của class nếu không có lý do kỹ thuật rõ và quyền truy cập phù hợp.

## 16. Java modules: `public` có thể chưa đủ qua module boundary

Với Java 9+ và Java 17, Java Platform Module System đưa thêm một ranh giới bên ngoài package. Ví dụ:

~~~java
// module-info.java của module chứa API
module academy.model {
    exports academy.api;
}
~~~

Điều này cho phép package `academy.api` được export ra bên ngoài module theo cấu hình. Một class `public` ở package `academy.internal` **không tự động truy cập được từ module khác** nếu package này không được export thích hợp.

Module client cần khai báo dependency khi dùng named modules:

~~~java
module academy.client {
    requires academy.model;
}
~~~

Hai đoạn là ví dụ cú pháp `module-info.java`, không phải ứng dụng độc lập. Với code trên **classpath/unnamed module**, hành vi thông thường đơn giản hơn; với named modules, cần đồng thời xét:

1. Package chứa type được **export** phù hợp hoặc quyền đọc/module accessibility tương ứng.
2. Top-level/member type có thể truy cập từ điểm gọi.
3. Member có visibility thích hợp (`public`, `protected`, package-private, `private`).
4. Các quy tắc compiler/JVM khác vẫn thỏa.

**`exports` khác `opens`:** `exports` phục vụ truy cập kiểu công khai theo ngôn ngữ, còn `opens` phục vụ một số khả năng reflection/deep reflection. Không dùng `opens` như cách thay thế mặc định cho mọi public API.

## 17. Ví dụ Java chạy được: mở rộng mức truy cập khi override

Tạo file **`VisibilityOverrideDemo.java`**:

~~~java
public class VisibilityOverrideDemo {
    static class Parent {
        protected String label() {
            return "Parent";
        }

        public String display() {
            return "display: " + label();
        }
    }

    static class Child extends Parent {
        @Override
        public String label() {
            return "Child";
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println(parent.display());
        System.out.println(polymorphic.display());
        System.out.println(child.label());

        // parent.label() được phép ở đây vì các lớp nested cùng
        // ngữ cảnh nest và các lớp đều trong cấu trúc này.
        // Trong một class khác ở package khác, protected có
        // các giới hạn đã giải thích ở phần trước.
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 VisibilityOverrideDemo.java
java VisibilityOverrideDemo
~~~

Stdout:

~~~text
display: Parent
display: Child
Child
~~~

Điểm rút ra:

- `Parent.label()` là protected, `Child.label()` được override thành public. Đây là hành vi **mở rộng quyền truy cập**, hợp lệ.
- `Parent.display()` là public; khi receiver runtime là Child, lời gọi `label()` dispatch đến `Child.label()`.
- Access control và dynamic dispatch **khác chức năng**. Modifier trả lời câu hỏi code có được phép gọi member từ vị trí đó không; overriding/dispatch quyết định implementation nào chạy trên object runtime.

*Lưu ý:* Với cả hai nested classes cùng nằm trong một enclosing class ở ví dụ này, quyền truy cập ngoài đời từ các package khác sẽ khác. Bài chạy này chủ yếu chứng minh **override mở rộng visibility và dispatch**, còn ví dụ nhiều package ở mục 4 mới là kiểm tra đầy đủ bốn phạm vi.

## 18. Các lỗi biên dịch thường gặp

### 18.1. Gọi private member từ class khác cùng package

~~~java
package example;

class A {
    private int secret = 1;
}

class B {
    int read(A a) {
        // return a.secret; // Lỗi: private access
        return 0;
    }
}
~~~

Cùng package không cấp quyền private. Nếu B thật sự cần đọc dữ liệu, A phải chủ động cung cấp một method/contract với visibility phù hợp, hoặc thiết kế lại phân chia trách nhiệm.

### 18.2. Thử `default` như access modifier

~~~java
class Wrong {
    // default int count; // Sai cú pháp field access modifier
    int count;            // package-private
}
~~~

Trong tài liệu, package-private đôi khi được gọi là *default access*, nhưng không có nghĩa cú pháp field là `default int`. Keyword `default` dùng cho mục đích khác như `switch` labels và default methods trong interface.

### 18.3. `private` hoặc `protected` trên top-level type

~~~java
// private class Utility { }   // Lỗi
// protected class Store { }   // Lỗi

class Utility { }             // Hợp lệ: package-private
public class Store { }        // Hợp lệ nếu tệp/phạm vi phù hợp
~~~

Đoạn này minh họa cách khai báo; nếu dùng cả hai top-level classes cùng tệp, đặt tên tệp `Store.java` theo public top-level class `Store`.

### 18.4. Override public method bằng protected

~~~java
class Parent {
    public void render() {
    }
}

class Child extends Parent {
    // @Override
    // protected void render() {} // Lỗi: weaker access
}
~~~

Method override không được thu hẹp visibility của method công khai.

### 18.5. Nghĩ import làm package-private trở nên public

~~~java
// Trong package a:
class InternalHelper { }

// Trong package b:
// import a.InternalHelper; // Không truy cập được
~~~

`import` chỉ tham gia quá trình dùng tên, không sửa quyền truy cập của type.

### 18.6. Subclass package khác gọi protected qua superclass receiver

~~~java
// Trong subclass khác package:
void inspect(Base base) {
    // base.protectedMethod(); // Có thể bị từ chối do receiver type
}
~~~

Khi dùng protected instance member từ subclass package khác, phải xét kiểu tĩnh của receiver theo JLS, không chỉ câu “method đang viết trong subclass”.

## 19. So sánh bốn mức theo mục tiêu thiết kế

| Mức truy cập | Khi nào nên cân nhắc | Lợi ích | Rủi ro nếu lạm dụng |
| --- | --- | --- | --- |
| `private` | Field, helper, implementation details không cần công khai | Đóng gói mạnh, dễ thay đổi nội bộ | Dùng sai có thể khiến cộng tác giữa các class khó khăn, dẫn đến API wrapper không cần thiết |
| Package-private | Các class cùng một package cần phối hợp nội bộ | Giấu implementation khỏi package ngoài, không cần public | Package quá lớn dễ khiến nhiều class vô tình phụ thuộc chi tiết |
| `protected` | API mở rộng cho subclass có chủ đích | Cho phép subclass tùy biến/tiếp cận một số hành vi | Coupling với inheritance; khó giữ invariant nếu expose mutable state |
| `public` | Hợp đồng thật sự cần cho caller ngoài package | API rõ ràng, tái sử dụng rộng | Khó thay đổi sau này; public mutable fields phá đóng gói |

**Nguyên tắc thực dụng:** bắt đầu từ mức truy cập **hẹp nhất vẫn đáp ứng được yêu cầu hợp lệ**. Chỉ mở rộng khi có use case rõ:

- Một **private helper** không cần public chỉ vì muốn test trực tiếp mọi câu lệnh của nó; có thể kiểm thử qua public behavior hoặc tách logic thực sự cần tái sử dụng.
- Một **package-private collaborator** phù hợp khi nhiều class trong package cần phối hợp nhưng code bên ngoài không cần biết.
- Một **protected extension point** nên có tài liệu và contract rõ, tránh đơn giản hóa thành “field nào subclass có thể cần thì protected”.
- Một **public API** là cam kết dành cho caller; giảm public không chủ đích giúp code dễ tiến hóa.

Không dùng access modifier để che lỗi thiết kế: ví dụ field private nhưng public setter cho phép mọi giá trị bất hợp lệ vẫn là một API kém bảo vệ invariant.

## 20. Kiểm tra hiểu biết với câu hỏi và đáp án

**Câu 1.** Trong một class thông thường, field `int x;` có mức truy cập gì?

**Đáp án:** Package-private vì không ghi `public`, `protected` hoặc `private`. Class khác trong cùng package có thể truy cập nếu các điều kiện còn lại thỏa mãn.

**Câu 2.** Class khác cùng package có thể truy cập `protected` field mà không `extends` class khai báo không?

**Đáp án:** Có. Trong Java, protected mở quyền theo **cùng package** và thêm đường truy cập cho subclass ở package khác với điều kiện đặc biệt.

**Câu 3.** Subclass khác package có được truy cập package-private method của superclass chỉ vì `extends` không?

**Đáp án:** Không. Package-private không mở qua package boundary bằng quan hệ kế thừa.

**Câu 4.** Subclass `Dog extends Animal` ở package khác có thể gọi `animal.protectedMethod()` với parameter khai báo kiểu `Animal` không?

**Đáp án:** Không phải mặc định. Protected instance receiver rule yêu cầu kiểu receiver thích hợp với subclass nơi truy cập được khai báo; `Animal` thường quá rộng nếu `Dog` đang sử dụng protected member của superclass từ package khác.

**Câu 5.** Method của `Person` có truy cập `other.privateField` khi `other` cũng là instance `Person` không?

**Đáp án:** Có, nếu code nằm trong ngữ cảnh class `Person` được phép truy cập private member đó. Private giới hạn theo nơi code được khai báo, không giới hạn duy nhất `this` object.

**Câu 6.** Có thể khai báo `protected class Service` ở top-level không?

**Đáp án:** Không. Top-level class thông thường chỉ có thể `public` hoặc package-private; `protected` áp dụng ở member type contexts thích hợp.

**Câu 7.** `import com.example.Hidden;` có giúp dùng package-private class `Hidden` từ package khác không?

**Đáp án:** Không. Import không nâng visibility.

**Câu 8.** Interface method `void run();` không ghi modifier có package-private như class method không?

**Đáp án:** Không. Abstract interface method kiểu này ngầm `public abstract`; implementation trong class phải `public` khi override.

**Câu 9.** Parent có `protected String name()`, subclass override thành `public String name()` có hợp lệ không?

**Đáp án:** Có, vì mở rộng visibility. Nếu subclass giảm protected thành private sẽ không hợp lệ.

**Câu 10.** Một field `private final List<String> items` và getter public trả thẳng list mutable có bảo vệ tốt không?

**Đáp án:** Chưa. Private giới hạn truy cập field; final ngăn gán lại tham chiếu, nhưng getter trả mutable object nội bộ có thể cho caller sửa list. Cân nhắc snapshot/view và command có validation.

**Câu 11.** Public class trong package không được `exports` từ một named module có mặc nhiên dùng được ở module khác không?

**Đáp án:** Không. Module boundary và readability/export cũng tham gia kiểm tra khả năng truy cập.

**Câu 12.** Private constructor có nghĩa class không thể có instance không?

**Đáp án:** Không. Code có quyền truy cập trong class có thể gọi private constructor, ví dụ static factory trả object hợp lệ.

**Câu 13.** `protected` member trong cùng package có cần receiver thuộc subclass không?

**Đáp án:** Không cần quy tắc receiver đặc biệt của subclass package khác; đường truy cập same-package áp dụng.

**Câu 14.** Class có `private void helper()`. Subclass khai báo `void helper()` cùng chữ ký có phải đang override private method không?

**Đáp án:** Không theo nghĩa ghi đè instance method được kế thừa. Private method của superclass không được override chỉ bằng khai báo method cùng tên ở subclass.

**Câu 15.** Method package-private nằm trong class thuộc `a.b` có truy cập được trực tiếp từ `a.b.test` không?

**Đáp án:** Không. `a.b` và `a.b.test` là hai package khác nhau; tiền tố tên không tạo quan hệ quyền truy cập.

## 21. Checklist khi chọn và kiểm tra access modifier

1. **Xác định thành phần:** bạn đang khai báo top-level type, member type, field, constructor hay method? Không phải mọi loại khai báo đều cho cả bốn modifier.
2. **Xác định caller:** code sử dụng nằm trong chính class, class khác cùng package, subclass ở package khác hay code khác package không kế thừa?
3. **Xác định package thật:** `a.b` và `a.b.c` là các package khác nhau.
4. **Nếu dùng protected từ package khác:** kiểm tra quan hệ subclass và **compile-time receiver type**; đừng dựa chỉ vào runtime type.
5. **Nếu subclass override:** không được giảm visibility của method gốc.
6. **Nếu member là private:** nhớ same-class code có thể thao tác với private member của **instance khác cùng class**; private không mở tùy ý cho class khác cùng package.
7. **Nếu top-level type không có public:** đừng kỳ vọng import từ package khác làm nó có thể truy cập.
8. **Nếu code dùng interface:** abstract/default/static interface methods và fields có quy tắc public riêng; `default` ở interface không phải package-private.
9. **Nếu dùng named modules:** kiểm tra `requires`, `exports` và các điều kiện accessibility thích hợp.
10. **Nếu muốn bảo vệ state:** kết hợp private field, validation, API hợp lệ và defensive copying; modifier không tự làm object immutable hoặc thread-safe.
11. **Nếu API là public/protected:** cân nhắc khả năng mở rộng, backward compatibility và hợp đồng cho subclass/caller.
12. **Khi gặp lỗi compile:** đọc chính xác “has private access”, “is not public”, “has protected access” hoặc “attempting to assign weaker access privileges”; kiểm tra từ vị trí caller thay vì chỉ nhìn modifier của member.

**Ghi nhớ:** `public` mở API rộng, `private` giữ chi tiết bên trong, **package-private** dành cho mã cùng package, còn `protected` hỗ trợ **cả same-package access lẫn subclass access với giới hạn đặc thù khi khác package**. Một thiết kế tốt dùng mức truy cập hẹp nhất hợp lý và mở quyền có chủ đích, để class bảo vệ dữ liệu và cung cấp đúng những hành vi mà bên ngoài cần.
