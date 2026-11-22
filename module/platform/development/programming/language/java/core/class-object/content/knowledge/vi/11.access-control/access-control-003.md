# Quyền truy cập trường, phương thức và hàm khởi tạo trong Java

**Kiểm soát truy cập (access control)** là tập quy tắc Java quyết định đoạn mã nào được phép sử dụng một **trường dữ liệu (field)**, gọi một **phương thức (method)** hay gọi một **hàm khởi tạo (constructor)**. Các quy tắc này được kiểm tra chủ yếu ở **thời điểm biên dịch**, dựa vào vị trí mã gọi, package, quan hệ kế thừa và kiểu biểu thức nhận (*receiver*).

Java có bốn **mức truy cập** thường gặp đối với thành viên của lớp thông thường:

1. `public` — cho phép truy cập rộng nhất, nhưng vẫn phụ thuộc vào khả năng truy cập **lớp chứa thành viên**, module và những quy tắc liên quan.
2. `protected` — cho phép mã trong **cùng package**, đồng thời cung cấp quyền truy cập đặc biệt cho **lớp con ở package khác** với những điều kiện cụ thể.
3. **Package-private** — không ghi modifier; chỉ cho phép truy cập trong **cùng package** theo quy tắc Java.
4. `private` — giới hạn truy cập vào phạm vi khai báo và những ngữ cảnh hợp lệ như các thành viên cùng *nest*; mã lớp độc lập bên ngoài thông thường không thể truy cập.

Ví dụ:

```java
public class Account {
    public String currency = "VND";
    protected String owner = "An";
    int level = 1;                     // package-private
    private long balance = 100;

    public Account() { }

    public void deposit(long amount) {
        balance += amount;
    }

    protected void audit() { }

    void updateLevel() {
        level++;
    }

    private void validate() { }
}
```

Mỗi field, method và constructor ở đây có quyền truy cập riêng. Một class `public` **không tự làm tất cả thành viên của nó thành public**.

> Mục tiêu không phải đưa mọi thứ thành `public` cho “hết lỗi”, mà là tạo ra **API tối thiểu vừa đủ**: mã khác được phép làm những việc cần thiết, trong khi chi tiết triển khai và bất biến dữ liệu được bảo vệ.

Bài học sử dụng cú pháp và hành vi **Java 17+**, phân biệt rõ những đoạn khai báo minh họa với chương trình hoàn chỉnh có thể biên dịch và chạy.

## 1. Phạm vi và bốn mức truy cập

Hãy bắt đầu với bảng tổng quát dưới đây. Bảng xét các **lớp thông thường không lồng nhau** và các trường hợp thành viên instance, constructor phổ biến; `protected` từ package khác được phân tích chi tiết ở phần sau.

| Vị trí mã muốn sử dụng thành viên | `public` | `protected` | Package-private | `private` |
| --- | --- | --- | --- | --- |
| Bên trong chính lớp khai báo | Có | Có | Có | Có |
| Lớp độc lập khác trong cùng package | Có | Có | Có | Không |
| Lớp độc lập không liên quan ở package khác | Có nếu lớp và API nhìn thấy được | Không | Không | Không |
| Lớp con ở package khác | Có nếu hợp lệ | **Có điều kiện** | Không | Không |
| Code không phải subclass ở package khác | Có nếu hợp lệ | Không | Không | Không |

**Lưu ý quan trọng về `private`:** Java hiện đại có quy tắc truy cập dành cho các **nested classes thuộc cùng nest**, vì thế câu “private chỉ đọc được từ đúng một lớp và tuyệt đối không có ngoại lệ” là quá đơn giản. Với lớp độc lập, ví dụ trong bảng phản ánh tình huống thực hành cơ bản.

**Lưu ý về `protected`:** không thể đơn giản kết luận “ở trong subclass nên được đọc mọi `protected` field của mọi object kiểu superclass”. Java có **điều kiện về kiểu của receiver** ở một số cách truy cập từ package khác.

### 1.1. Package là đơn vị truy cập, không phải thư mục tùy ý

`package store;` khai báo một lớp thuộc package `store`. Hai lớp khác tệp nhưng có **cùng tên package** được áp dụng quyền package-private như mã trong cùng package.

`store` và `store.inventory` **không phải cùng package**: quan hệ tên có dấu chấm **không** cấp quyền package-private hay protected của package cha cho package con.

Ví dụ:

```java
package store;
class Product {
    int stock = 10;
}
```

Một lớp ở `package store;` có thể dùng `Product` và field `stock` nếu đáp ứng quy tắc khác. Nhưng một lớp ở `package store.inventory;` **không** tự có quyền vì tên trông giống “package con”.

Việc hai tệp đặt cạnh nhau trên ổ đĩa cũng không thay thế khai báo package và classpath/module structure.

### 1.2. Từ khóa `default` không phải modifier “quyền mặc định”

**Package-private** có nghĩa **không viết modifier truy cập**, ví dụ:

```java
class Student {
    String name;                  // package-private field

    void printName() {            // package-private method
        System.out.println(name);
    }

    Student(String name) {        // package-private constructor
        this.name = name;
    }
}
```

Không viết `default String name;` hoặc `default Student() { }` với ý định package-private. Từ khóa `default` có ý nghĩa khác khi khai báo **default method trong interface**.

## 2. Quyền truy cập của field

**Field** là biến thành viên thuộc một đối tượng (instance field) hoặc thuộc lớp (`static` field). Một field có thể có modifier riêng biệt:

```java
class Profile {
    public String nickname;
    protected int rank;
    boolean active;              // package-private
    private String passwordHash;
}
```

Điều kiện truy cập được áp dụng cho chính **field được chọn theo biểu thức**. Không phải vì caller có tham chiếu đến object `Profile` thì caller được phép đọc mọi field.

### 2.1. `public` field

`public String nickname;` cho phép mã từ nơi có thể truy cập tới kiểu chứa field sử dụng `profile.nickname`.

Tuy nhiên, **public field mutable** thường mở rộng khả năng thay đổi trạng thái ngoài dự kiến:

```java
profile.nickname = null;
```

Bên ngoài có thể bỏ qua các bước xác thực nghiệp vụ nếu field được mở công khai. Vì vậy đối với state cần bảo đảm hợp lệ, thường nên chọn **`private` field + method công khai phù hợp**, thay vì để mọi field public.

Không phải mọi public field đều là thiết kế kém: các hằng số có nghĩa và ổn định thường được khai báo `public static final` khi thích hợp, ví dụ:

```java
public static final int MAX_ATTEMPTS = 3;
```

Đây là hằng kiểu primitive. Nếu public static final field trỏ đến **object mutable**, `final` chỉ ngăn gán lại tham chiếu field, **không** tự cấm sửa object đó.

### 2.2. `private` field và đóng gói

Lưu thành **`PrivateFieldDemo.java`**:

```java
class Wallet {
    private int balance;

    Wallet(int balance) {
        if (balance < 0) {
            throw new IllegalArgumentException("Negative balance");
        }
        this.balance = balance;
    }

    int getBalance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance += amount;
    }
}

public class PrivateFieldDemo {
    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.deposit(50);

        System.out.println(wallet.getBalance());

        // wallet.balance = -999;
        // SAI nếu bỏ comment: balance là private.
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PrivateFieldDemo.java
java PrivateFieldDemo
```

**Stdout:**

```text
150
```

Trong ví dụ:
- `Wallet.balance` là `private` nên `PrivateFieldDemo` không truy cập trực tiếp, dù hai lớp cùng nằm trong một tệp nguồn.
- `deposit` kiểm soát việc tăng số dư qua điều kiện nghiệp vụ.
- `getBalance` chỉ cung cấp giá trị để đọc. Ở đây method không có modifier nên là **package-private**, vì hai lớp cùng package mặc định.
- Nếu `Wallet` là public API từ package khác, cần chọn quyền truy cập thích hợp cho constructor/method mà caller dùng.

**Đóng gói** không đồng nghĩa field bắt buộc có getter/setter cho mọi trường hợp. Chỉ công bố những thao tác thực sự cần: có field nên chỉ được đọc, có field không cần lộ ra, có field cần kiểm tra khi thay.

## 3. Quyền truy cập của instance method

**Instance method** có thể đọc/sửa trạng thái object hiện tại hoặc thực hiện hành vi. Các access modifier quyết định **nơi có thể gọi method**:

```java
class Order {
    public void submit() {
        validate();
        markSubmitted();
    }

    protected void markSubmitted() {
        System.out.println("Submitted");
    }

    void recordAudit() {
        System.out.println("Audit");
    }

    private void validate() {
        // Kiểm tra logic nội bộ.
    }
}
```

- `submit()` public: một điểm vào dự kiến cho caller được quyền dùng `Order`.
- `markSubmitted()` protected: cùng package và subclass hợp lệ có quyền truy cập theo quy tắc.
- `recordAudit()` package-private: dành cho mã cùng package.
- `validate()` private: chi tiết triển khai nội bộ.

Việc `submit()` **gọi method private `validate()` hoàn toàn hợp lệ**: mã đang ở bên trong lớp `Order`, nơi có quyền gọi `validate()`.

### 3.1. Phương thức công khai vẫn có thể gọi thành viên kín

Một method public là **cửa vào**, không đồng nghĩa các hành động nội bộ mà nó gọi cũng phải public. Ví dụ:

```java
public void process() {
    checkInvariant();       // private
    executeInternal();      // private
}
```

Đây là cách thiết kế giữ API nhỏ, giảm sự phụ thuộc của mã ngoài vào chi tiết triển khai. Khi thay cách `checkInvariant()` hoặc `executeInternal()` hoạt động, caller chỉ cần biết hợp đồng `process()`.

### 3.2. Method private không được override theo nghĩa đa hình

`private` method không được kế thừa theo cách tạo thành một phương thức có thể override từ lớp con. Một lớp con có thể khai báo method **trùng tên và danh sách tham số** với private method của lớp cha, nhưng đây **không** phải một override của method private ấy.

Ví dụ:

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void callSecret() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}
```

Nếu `new Child().callSecret()` được gọi, `Parent.callSecret()` gọi **`Parent.secret()`**, không dispatch sang `Child.secret()`.

Điều này khác với một method `protected` hoặc `public` phù hợp được override: trường hợp đó runtime dispatch có thể chọn implementation của lớp con.

## 4. Quyền truy cập của constructor

**Constructor** được gọi khi tạo instance với `new` hoặc thông qua constructor chaining `this(...)`/`super(...)`. Quyền truy cập của constructor có thể khác quyền truy cập của các field và method trong cùng lớp:

```java
public class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        return new Token(value);
    }

    public String value() {
        return value;
    }
}
```

Với lớp này (lưu trong **`Token.java`**):
- **Lớp** `Token` là `public`.
- **Constructor** `Token(String)` là `private`.
- **Method** `Token.of(String)` là `public static` và được quyền gọi constructor private **từ bên trong `Token`**.
- **Field** `value` là `private final`.
- **Getter** `value()` là public.

Mã bên ngoài có thể:

```java
Token token = Token.of("abc");
System.out.println(token.value()); // abc
```

Nhưng không thể viết `new Token("abc")` từ một lớp không có quyền truy cập constructor private.

**Quan trọng:** constructor không phải instance method. Constructor **không được kế thừa hoặc override**; quyền truy cập và cơ chế `super(...)` phải xét riêng với method overriding.

### 4.1. Constructor public, protected, package-private, private

| Khai báo | Trường hợp sử dụng thường gặp |
| --- | --- |
| `public Account()` | Cho phép mã ngoài trực tiếp tạo một `Account` |
| `protected Base()` | Cho phép các subclass phù hợp gọi constructor cha; cùng package cũng được truy cập |
| `Account()` | Chỉ mở đường tạo cho mã trong cùng package |
| `private Account()` | Kiểm soát việc tạo qua factory hoặc ngăn khởi tạo utility class từ bên ngoài |

Nếu chỉ một constructor là private nhưng lớp còn một overload public, caller vẫn có thể gọi overload public nếu phù hợp:

```java
class Job {
    public Job(String name) {
    }

    private Job() {
    }
}
```

`new Job("A")` hợp lệ trong ngữ cảnh nhìn thấy `Job`; `new Job()` từ lớp độc lập khác bị chặn. **Quyền truy cập gắn với từng constructor**, không áp dụng đồng loạt cho mọi overload.

## 5. Ví dụ nhiều package: `public` và package-private

Để quan sát phạm vi qua package thật, tạo cấu trúc tệp sau:

```text
src/
├── catalog/
│   ├── Product.java
│   └── CatalogDemo.java
└── app/
    └── Main.java
```

**Tệp `src/catalog/Product.java`:**

```java
package catalog;

public class Product {
    public String name;
    int stock;
    private int secretCode;

    public Product(String name, int stock) {
        this.name = name;
        this.stock = stock;
        this.secretCode = 7;
    }

    public String label() {
        return name;
    }

    int stock() {
        return stock;
    }

    private int secretCode() {
        return secretCode;
    }

    public boolean hasSecretCode() {
        return secretCode() > 0;
    }
}
```

**Tệp `src/catalog/CatalogDemo.java`:**

```java
package catalog;

public class CatalogDemo {
    public static void show(Product product) {
        System.out.println(product.stock);
        System.out.println(product.stock());
        // System.out.println(product.secretCode);
        // SAI nếu bỏ comment: private field thuộc Product.
    }
}
```

**Tệp `src/app/Main.java`:**

```java
package app;

import catalog.CatalogDemo;
import catalog.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Java Book", 3);

        System.out.println(product.name);
        System.out.println(product.label());
        System.out.println(product.hasSecretCode());

        CatalogDemo.show(product);

        // System.out.println(product.stock);
        // System.out.println(product.stock());
        // SAI nếu bỏ comment: package-private trong catalog.
    }
}
```

Từ thư mục chứa `src`, biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 -d out src/catalog/Product.java src/catalog/CatalogDemo.java src/app/Main.java
java -cp out app.Main
```

**Stdout chính xác:**

```text
Java Book
Java Book
true
3
3
```

Giải thích:
- `Product` là public top-level class, có constructor public, nên `app.Main` được tạo đối tượng qua `new Product(...)`.
- `name` và `label()` public nên truy cập từ `app` hợp lệ.
- `stock` và `stock()` package-private nên `CatalogDemo` cùng package `catalog` được dùng, còn `Main` ở package `app` không được.
- `secretCode` và `secretCode()` private nên **`CatalogDemo` dù cùng package** cũng không truy cập trực tiếp.
- Method public `hasSecretCode()` bên trong `Product` được phép gọi `secretCode()` private rồi trả kết quả boolean cho caller. Caller vẫn không được phép gọi method private trực tiếp.

**Chú ý:** quyền truy cập thành viên **độc lập** với việc cùng tệp nguồn hay khác tệp; Java dựa vào loại khai báo, package, nest và quan hệ kiểu.

## 6. `protected` đối với field và method: quy tắc dễ nhầm nhất

`protected` không đơn thuần là mức “chỉ subclass”. Một `protected` member có thể được truy cập:

- **Từ cùng package** theo quyền package, kể cả không có quan hệ kế thừa.
- **Từ lớp con ở package khác**, nhưng các trường hợp truy cập instance member còn chịu **ràng buộc về receiver**.

Giả sử `Base` ở package `core` có `protected int value`.

Trong một subclass `Derived` ở package `client`, đoạn:

```java
this.value = 10;               // Hợp lệ trong instance method của Derived
```

có thể hợp lệ; nhưng:

```java
Base base = new Base();
base.value = 10;                // Không hợp lệ trong subclass ở package khác
```

**Tại sao?** Khi truy cập protected instance member từ ngoài package khai báo, Java không cho subclass tự do can thiệp trạng thái protected của **mọi** object superclass. Với các truy cập bằng `receiver.member`, kiểu tĩnh của receiver phải thỏa quy tắc liên quan đến subclass mà mã đang đứng trong đó.

### 6.1. Ví dụ nhiều package chạy được

**Tệp `src/core/Base.java`:**

```java
package core;

public class Base {
    protected int value = 1;

    protected void increase() {
        value++;
    }

    public int getValue() {
        return value;
    }
}
```

**Tệp `src/client/Derived.java`:**

```java
package client;

import core.Base;

public class Derived extends Base {
    public void updateSelf() {
        this.value += 2;       // Hợp lệ: receiver là Derived
        this.increase();       // Hợp lệ: gọi protected method kế thừa
    }

    public void updatePeer(Derived peer) {
        peer.value += 3;       // Hợp lệ: peer có kiểu tĩnh Derived
    }

    public void invalidExample(Base base) {
        // base.value = 10;
        // base.increase();
        // SAI nếu bỏ comment: receiver kiểu Base qua package khác.
    }
}
```

**Tệp `src/client/Main.java`:**

```java
package client;

public class Main {
    public static void main(String[] args) {
        Derived first = new Derived();
        Derived second = new Derived();

        first.updateSelf();
        first.updatePeer(second);

        System.out.println(first.getValue());
        System.out.println(second.getValue());

        // System.out.println(first.value);
        // SAI nếu bỏ comment: Main không là subclass và khác package core.
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 -d out src/core/Base.java src/client/Derived.java src/client/Main.java
java -cp out client.Main
```

Stdout:

```text
4
4
```

Phân tích:
- `first` bắt đầu `value = 1`, `updateSelf()` thêm `2` rồi `increase()` thêm `1` → **4**.
- `second` bắt đầu `value = 1`, `updatePeer(second)` thêm `3` → **4**.
- Code `peer.value` nằm **trong subclass `Derived`** và `peer` có kiểu tĩnh `Derived`, vì vậy được phép theo quy tắc protected.
- `client.Main` không tự được truy cập `first.value` chỉ vì nó dùng một `Derived`; `Main` không là subclass của `core.Base`.
- `Base base` trong `Derived.invalidExample` không đủ điều kiện để truy cập `base.value` và `base.increase()` trực tiếp từ ngoài package `core`.

**Mẹo:** nếu mã subclass cần một thao tác công khai trên object superclass tùy ý, cung cấp API public phù hợp hoặc thiết kế một method chung thay vì lạm dụng `protected`.

### 6.2. `protected static` cũng có quy tắc riêng

Với **protected static field/method**, subclass ở package khác có thể truy cập thành viên kế thừa qua ngữ cảnh hợp lệ như tên subclass hoặc tên đơn giản theo quy tắc. Đừng suy ra rằng mọi lớp khác ở package đó cũng được truy cập chỉ vì có import.

Để dễ đọc và tránh nhầm static member với instance member, **nên gọi static method qua tên lớp** khi quyền truy cập và khai báo cho phép. Đối với câu hỏi học phần này, hãy nắm vững khác biệt **cùng package** và **subclass ngoài package** trước.

## 7. `protected` đối với constructor không giống `protected` field

Constructor của superclass có thể được lớp con ở package khác gọi bằng `super(...)`:

**Tệp `src/core/Vehicle.java`:**

```java
package core;

public class Vehicle {
    private final String brand;

    protected Vehicle(String brand) {
        this.brand = brand;
    }

    public String brand() {
        return brand;
    }
}
```

**Tệp `src/garage/Car.java`:**

```java
package garage;

public class Car extends core.Vehicle {
    public Car(String brand) {
        super(brand);               // Hợp lệ: constructor cha protected
    }
}
```

**Tệp `src/garage/Main.java`:**

```java
package garage;

public class Main {
    public static void main(String[] args) {
        Car car = new Car("Toyota");
        System.out.println(car.brand());

        // core.Vehicle v = new core.Vehicle("Honda");
        // SAI: protected constructor không mở quyền new cho Main.
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 -d out src/core/Vehicle.java src/garage/Car.java src/garage/Main.java
java -cp out garage.Main
```

Stdout:

```text
Toyota
```

Tại sao khác với field?
- `super(brand)` là **explicit superclass constructor invocation** được đặt ở đầu thân constructor `Car` theo quy tắc Java 17.
- Mã bên ngoài package `core` không tự được tạo một `Vehicle` độc lập bằng `new Vehicle(...)` chỉ vì nó nhìn thấy public class `Vehicle`.
- `Car` có constructor public, vì vậy `garage.Main` có thể tạo **Car**, rồi constructor Car gọi constructor superclass protected theo quy tắc.

Đối với constructor protected còn có vài trường hợp chuyên biệt như tạo anonymous subclass; đây là ngoại lệ theo cú pháp ngôn ngữ, không nên diễn giải protected constructor là công khai toàn bộ.

### Constructor cha không được kế thừa

`class Car extends Vehicle` **không thừa hưởng constructor `Vehicle(String)`** như một overload của `Car`. Muốn viết `new Car("Toyota")`, lớp `Car` phải có constructor phù hợp của **chính `Car`**, sau đó có thể gọi `super("Toyota")`.

Nếu superclass không có no-arg constructor truy cập được và subclass không gọi `super(arguments)` phù hợp, việc chèn `super()` ngầm định có thể làm code **không biên dịch**.

## 8. `private` với constructor: giới hạn đường tạo đối tượng

**Private constructor** rất hữu ích khi muốn:
- Caller không được tự chọn đường khởi tạo;
- Áp dụng validation/factory trước khi tạo;
- Tạo utility class chỉ chứa static functionality;
- Quản lý một số instance theo chính sách thiết kế.

### 8.1. Static factory method

Lưu thành **`FactoryAccessDemo.java`**:

```java
final class Session {
    private final String id;

    private Session(String id) {
        this.id = id;
    }

    public static Session create(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return new Session(id);
    }

    public String id() {
        return id;
    }
}

public class FactoryAccessDemo {
    public static void main(String[] args) {
        Session session = Session.create("S-01");
        System.out.println(session.id());

        // Session direct = new Session("S-02");
        // SAI nếu bỏ comment: constructor private.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 FactoryAccessDemo.java
java FactoryAccessDemo
```

Stdout:

```text
S-01
```

`Session.create(...)` là **static method** có kiểu trả về `Session`, **không phải constructor**. Nó được gọi từ bên ngoài, nhưng câu lệnh `new Session(id)` xảy ra **bên trong `Session`**, nơi constructor private truy cập được.

Đoạn ví dụ đặt các lớp cùng tệp để tiện chạy. Nếu muốn `Session` trở thành kiểu public cho package khác, đưa `public final class Session` vào tệp `Session.java` và công bố những API phù hợp; **không cần biến constructor thành public**.

### 8.2. Utility class không cần tạo instance

```java
public final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No instances");
    }

    public static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
```

Đây là lớp tiện ích có constructor private. Caller dùng `TextUtils.isBlank(" ")` mà **không cần `new TextUtils()`**.

`final class` cấm kế thừa, còn `private constructor` cấm các lời gọi tạo instance thông thường từ lớp độc lập bên ngoài. Việc ném `AssertionError` chỉ là lớp phòng vệ nếu constructor bị gọi từ mã có quyền; bản thân `private` đã kiểm soát compile-time access.

Không nên mô tả private constructor như “bảo mật tuyệt đối”: reflection, serialization, instrumentation hoặc framework có cơ chế riêng, còn những ngữ cảnh cùng nest có thể được truy cập theo quy tắc Java. Nó là **ranh giới API/ngôn ngữ**, không phải sandbox cho mã không tin cậy.

## 9. Default constructor có mức truy cập nào?

Đối với lớp thông thường **không khai báo bất kỳ constructor nào**, Java cung cấp một **default constructor không tham số** theo quy tắc ngôn ngữ.

```java
public class Empty {
    int value;
}
```

Nếu superclass cung cấp constructor zero-argument truy cập được như mong đợi, `Empty` nhận default constructor. Với `public class Empty`, default constructor có mức truy cập tương ứng **public**.

Vì thế:

```java
Empty empty = new Empty();
System.out.println(empty.value); // 0 nếu caller cùng package để đọc field
```

Nếu lớp là **package-private top-level class**, default constructor tương ứng có mức truy cập package-private; bản thân lớp cũng không thể được dùng tự do từ package khác.

**Quan trọng:** chỉ cần khai báo **một constructor tường minh**, kể cả private, compiler **không tự thêm** default no-arg constructor nữa.

```java
public class User {
    private final String name;

    private User(String name) {
        this.name = name;
    }

    public static User of(String name) {
        return new User(name);
    }
}
```

Với `User`:
- `new User()` không biên dịch vì **không có constructor no-arg**.
- `new User("An")` từ lớp khác không biên dịch vì constructor này **private**.
- `User.of("An")` hợp lệ từ nơi có quyền truy cập public API.

Đừng gọi constructor `private User(String)` là “default constructor”. Nó được người viết khai báo tường minh, nhận một tham số và không phải mặc định compiler tạo.

### 9.1. No-arg constructor do người viết khai báo

`public User() { }` là một **public no-arg constructor tường minh**. `User() { }` không modifier là **package-private no-arg constructor tường minh**. Từ “không tham số” chỉ nói đến **danh sách tham số**, còn quyền truy cập là thuộc tính **độc lập**.

## 10. Một class public vẫn có thể không được khởi tạo từ bên ngoài

Hãy phân tích độc lập:

```java
public final class Catalog {
    private Catalog() { }

    public static Catalog instance() {
        return new Catalog();
    }
}
```

- Public class: caller có thể **nhìn thấy kiểu `Catalog`** theo điều kiện truy cập.
- Private constructor: caller **không được gọi trực tiếp `new Catalog()`** từ một lớp độc lập không có quyền.
- Public static method: caller có thể **nhận thể hiện** qua `Catalog.instance()`.

Sự tồn tại của một tham chiếu đến đối tượng `Catalog` bên ngoài **không chứng minh** bên ngoài được quyền gọi constructor.

Tương tự, class có thể có **field private** nhưng **method public**, hoặc constructor public nhưng **method private**. Mỗi khai báo được kiểm tra riêng.

## 11. Mức truy cập của lớp chứa thành viên luôn quan trọng

Một top-level class không public sẽ giới hạn khả năng sử dụng kiểu từ package khác:

```java
package internal;

class InternalEngine {
    public void run() {
        System.out.println("Run");
    }
}
```

Method `run()` là public, nhưng **kiểu top-level `InternalEngine` là package-private**. Một file thuộc package `external` không thể chỉ `import internal.InternalEngine;` rồi tự do tạo/nhận biến kiểu đó theo cách thông thường.

**Phạm vi hiệu dụng** của một thành viên không thể vượt qua rào cản khả năng truy cập đến **kiểu chứa nó**.

### 11.1. Top-level class có những modifier truy cập nào?

Top-level class thường chỉ được khai báo:
- `public class Name`, hoặc
- `class Name` (package-private).

Không được viết `private class TopLevel` hay `protected class TopLevel` ở cấp top-level.

Ngược lại, **member nested class** trong class có thể khai báo `public`, `protected`, package-private hoặc `private` phù hợp. Đây là lý do không được áp dụng nguyên xi bảng modifier của **field/method/constructor** cho mọi **top-level type**.

### 11.2. Module system trong Java 17

Từ Java 9, **Java Platform Module System** cung cấp mức giới hạn bổ sung. Một `public class` trong package không được **export** cho module khác có thể không truy cập được từ module tiêu thụ, dù các thành viên trong nó được ghi `public`.

Khi làm việc với module:
- Kiểm tra `module-info.java`, đặc biệt `exports package.name;`.
- Phân biệt truy cập Java thông thường với khả năng **deep reflection**, có thể liên quan `opens`.
- Đừng hiểu `public` là luôn “truy cập được từ mọi nơi trong toàn JVM” bất chấp module.

Đối với các ví dụ chạy bằng classpath trong bài này, không cần khai báo module để quan sát cơ chế cơ bản.

## 12. Quyền truy cập và overriding trong kế thừa

Quyền truy cập cũng ảnh hưởng **phương thức nào có thể được override** và **mức truy cập hợp lệ của override**.

Nguyên tắc:
- Một method `public` được override thì implementation override cũng phải **public**.
- Một method `protected` được override có thể giữ `protected` hoặc **mở rộng lên `public`**, nhưng không hạ thành package-private hay `private`.
- Một method package-private có thể được override theo quy tắc của các lớp có quan hệ phù hợp **trong cùng package**; qua package khác, việc method package-private không được kế thừa/truy cập như protected cần được xét cẩn thận.
- `private` method không override.
- `static` method không override động: tên method static có thể bị **hiding** theo điều kiện ngôn ngữ.

### 12.1. Overriding không được giảm visibility

Ví dụ hợp lệ:

```java
class Parent {
    protected void work() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    @Override
    public void work() {
        System.out.println("Child");
    }
}
```

`Child.work()` mở quyền từ protected lên public, hợp lệ.

Ví dụ không hợp lệ nếu cùng hierarchy:

```java
class Parent {
    public void work() { }
}

class Child extends Parent {
    // protected void work() { } // SAI: không được giảm từ public
}
```

**Vì sao?** Caller được phép dùng public method thông qua một tham chiếu kiểu cha không được mất khả năng đó chỉ vì runtime object thuộc lớp con.

### 12.2. Chương trình chạy được: public override của protected method

Lưu thành **`OverrideAccessDemo.java`**:

```java
class Parent {
    protected String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    public String identify() {
        return "Child";
    }
}

public class OverrideAccessDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.identify());

        Child child = new Child();
        System.out.println(child.identify());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OverrideAccessDemo.java
java OverrideAccessDemo
```

Stdout:

```text
Child
Child
```

Tại `main`, cả ba class thuộc **cùng package mặc định**, nên mã được phép gọi `Parent.identify()` protected. Phương thức đã bị override và runtime object là `Child`, do đó implementation `Child.identify()` được chạy ở cả hai lời gọi.

**Mấu chốt:** truy cập được method **không có nghĩa method của cha được thực thi**. Với instance method bị override, runtime dispatch còn chọn implementation tương ứng sau khi lời gọi đã vượt qua kiểm tra kiểu và quyền truy cập.

### 12.3. Package-private method và kế thừa qua package

Giả sử `core.Base` có:

```java
package core;

public class Base {
    void internal() {
        System.out.println("Base");
    }
}
```

Ở package `client`, lớp `Derived extends core.Base` **không được truy cập `internal()` như một method kế thừa thông thường từ ngoài `core`**, vì method này package-private.

Nếu `client.Derived` khai báo method `void internal()` của riêng nó, **không nên mặc định đó là override** của `core.Base.internal()`. Vì superclass method package-private không được kế thừa/override từ package khác theo cách method protected/public được xử lý.

Điều này cho thấy **quan hệ `extends` không tự mở mọi thành viên superclass** cho subclass.

## 13. Quyền truy cập của field và phương thức static

Field `static` thuộc kiểu, còn field instance thuộc từng object; **cả hai vẫn chịu kiểm soát truy cập**:

```java
class Configuration {
    private static int retries = 3;

    public static int retries() {
        return retries;
    }
}
```

Một lớp khác không được đọc `Configuration.retries` nếu field private, nhưng có thể gọi `Configuration.retries()` khi có quyền truy cập method public.

Với method:
- `public static` method có thể dùng làm API công khai.
- `private static` method phù hợp với chức năng trợ giúp nội bộ.
- `protected static` và package-private static vẫn chịu các quy tắc package/kế thừa tương ứng.
- Static method **không có `this`**, nên không trực tiếp tham chiếu instance field/method chỉ vì field/method đó có mức public hay protected.

### 13.1. Static method hiding khác override

```java
class Parent {
    public static String label() {
        return "Parent";
    }
}

class Child extends Parent {
    public static String label() {
        return "Child";
    }
}
```

Với:

```java
Parent variable = new Child();
System.out.println(variable.label());  // Parent
System.out.println(Child.label());     // Child
```

Phương thức static được chọn theo **kiểu khai báo/kiểu tĩnh trong cách gọi hợp lệ**, không dispatch động theo runtime object như instance method được override.

Nên viết qua **tên lớp** như `Parent.label()` để rõ ý định; không nên gọi static method thông qua biến object.

**`private static` field/method cũng không được mở cho lớp khác** chỉ vì có thể gọi `ClassName.member`; quyền truy cập vẫn được compiler kiểm tra.

## 14. `final`, tính bất biến và quyền truy cập là các vấn đề khác nhau

Một field:

```java
private final java.util.List<String> names = new java.util.ArrayList<>();
```

có **hai quy tắc độc lập**:

- `private`: những nơi nào có quyền truy cập trực tiếp field `names`.
- `final`: field tham chiếu không được **gán lại** sau khi khởi tạo hợp lệ.

Nhưng đối tượng `ArrayList` vẫn mutable; một method trong lớp có thể gọi `names.add("An")`, sửa dữ liệu bên trong list.

`public final int value = 3;` cũng không phải static field trừ khi có `static`. `final` không tự biến thành hằng toàn cục hay thay đổi access level.

### 14.1. Bảng nhanh: access modifier vs modifier khác

| Modifier | Câu hỏi nó giải quyết |
| --- | --- |
| `private`/`protected`/`public` hoặc không ghi | **Ai được phép truy cập?** |
| `static` | Thành viên thuộc lớp hay instance? |
| `final` trên field | Field/biến có thể được gán lại hay không? |
| `final` trên class | Có được extends lớp này không? |
| `final` trên instance method | Có được override method này không? |
| `abstract` trên method/class | Thành viên/lớp có yêu cầu subclass triển khai hoặc không tạo trực tiếp? |
| `synchronized` trên method | Có cơ chế đồng bộ hóa lời gọi method như thế nào? |

**Không dùng access modifier như thay thế cho kiểm tra dữ liệu hay concurrency.** Field private với setter public cho phép ghi tùy ý vẫn có thể phá invariant nếu setter không validate. Một method public không tự thread-safe chỉ vì công khai.

## 15. Interface: những quy tắc truy cập đặc biệt

Trong **interface**, một số modifier được hiểu ngầm khác với member của class.

Ví dụ:

```java
interface Named {
    String name();                    // public abstract (ngầm định)

    int MAX_LENGTH = 100;             // public static final (ngầm định)

    default String title() {          // public default method
        return name().toUpperCase(java.util.Locale.ROOT);
    }

    static boolean valid(String value) { // public static method
        return value != null && !value.isBlank();
    }

    private String helper() {         // private helper method (Java 9+)
        return name().trim();
    }

    default String normalized() {
        return helper();
    }
}
```

Các điều cần nhớ:

1. **Field khai báo trong interface** luôn là `public static final` theo quy tắc Java, kể cả khi người viết không ghi đủ ba từ khóa. Không khai báo instance field trong interface giống class.
2. **Abstract method thông thường trong interface** là `public abstract` ngầm định; không thể biến thành package-private bằng cách bỏ `public`.
3. **Default method** và **static method** của interface phục vụ API public trong ngữ cảnh phù hợp; phương thức helper có thể là `private` từ Java 9.
4. Interface **không có constructor** để `new InterfaceName()` trực tiếp.
5. Một class triển khai interface phải cung cấp method triển khai public đối với abstract method public của interface.

### 15.1. Không được giảm visibility khi implements interface

```java
interface Named {
    String name();
}
```

Cách triển khai sau không hợp lệ:

```java
class BadNamed implements Named {
    // String name() { return "bad"; }
    // SAI nếu bỏ comment và không có method public: visibility yếu hơn public.
}
```

Bản hợp lệ:

```java
class GoodNamed implements Named {
    @Override
    public String name() {
        return "good";
    }
}
```

Phần interface và các class ở trên là **các đoạn khai báo minh họa**, không yêu cầu chạy như một tệp độc lập. Lưu ý `BadNamed` nếu không triển khai method `name()` vẫn phải được khai báo `abstract`; lời bình trong code minh họa ý định sai về access khi triển khai.

### 15.2. Method private trong interface không phải API bên ngoài

`private String helper()` trong interface chỉ dùng cho logic bên trong interface phù hợp, ví dụ được gọi bởi một `default method`. Caller không được gọi `object.helper()`, dù object triển khai interface.

Điều này cho phép tái sử dụng logic ở các default methods mà không làm API public phình ra.

## 16. Nested class và quyền `private`: ngoại lệ phạm vi hợp lệ

Java cho phép các member nested classes truy cập một số private members của enclosing type và ngược lại nhờ quy tắc truy cập cùng *nest*.

Ví dụ chạy được **`NestAccessDemo.java`**:

```java
public class NestAccessDemo {
    private int secret = 7;

    private static class Reader {
        static int read(NestAccessDemo owner) {
            return owner.secret;
        }
    }

    public static void main(String[] args) {
        NestAccessDemo owner = new NestAccessDemo();
        System.out.println(Reader.read(owner));
    }
}
```

```bash
javac -encoding UTF-8 NestAccessDemo.java
java NestAccessDemo
```

**Stdout:**

```text
7
```

`Reader` là một private static nested class thuộc `NestAccessDemo`. Dù `secret` là private, việc `Reader.read` truy cập `owner.secret` là hợp lệ theo quy tắc thành viên nested/nest.

Từ đây không thể suy ra một **lớp top-level độc lập cùng package** cũng được truy cập private field. Hai ngữ cảnh khác nhau.

**Constructor private cũng có các tình huống nested class truy cập được**. Vì vậy mô tả chính xác là “ngăn mã bên ngoài **không có quyền** gọi trực tiếp”, chứ không phải “không có bất kỳ mã nào khác có thể gọi”.

## 17. Đọc và ghi field: khả năng truy cập không đồng nghĩa quyền sửa

Giả sử:

```java
class Example {
    public final int fixed = 10;
    public int mutable = 20;
    private int hidden = 30;
}
```

Trong mã có thể truy cập lớp:
- Có thể **đọc** `example.fixed` vì field public.
- **Không thể gán lại** `example.fixed = 99;` do field final.
- Có thể đọc/ghi `example.mutable` vì public và không final.
- Không được trực tiếp đọc/ghi `example.hidden` từ lớp độc lập khác do private.

Đây là **hai tầng điều kiện khác nhau**: access control quyết định có quyền dùng member, còn `final` và các quy tắc kiểu quyết định thao tác cụ thể có hợp lệ hay không.

Một public getter cũng không biến private field thành public; getter chỉ trả một giá trị hoặc tham chiếu theo hợp đồng. Nếu getter trả tham chiếu tới object mutable bên trong, caller có thể thay trạng thái object đó **qua API được trả về**, dù field giữ tham chiếu là private.

## 18. Kiểm tra truy cập tại compile time và kiểu tĩnh của receiver

Quyền truy cập không được tính bằng cách JVM nhìn object thực tế rồi tự “mở khóa” member ở runtime.

Giả sử:

```java
class Parent {
    public void common() {
    }
}

class Child extends Parent {
    public void childOnly() {
    }
}
```

Với:

```java
Parent value = new Child();
value.common();           // Hợp lệ

// value.childOnly();     // SAI: kiểu tĩnh Parent không có childOnly()
```

Lỗi `value.childOnly()` trước hết là **không tìm thấy method phù hợp qua kiểu tĩnh**, chưa phải do `childOnly` private. Dù method được khai báo public ở `Child`, compiler không thể gọi qua receiver kiểu tĩnh `Parent` nếu `Parent` không có method đó.

Nếu caller kiểm tra subtype rồi cast hợp lệ:

```java
if (value instanceof Child child) {
    child.childOnly();
}
```

thì compiler thấy biến `child` có kiểu `Child`, method public được dùng hợp lệ.

**Quy trình kiểm tra thực tế:** hãy xác định **kiểu biểu thức nhận**, **member được chọn**, rồi mới kiểm tra **member có truy cập được từ vị trí lời gọi không**. Tránh kết luận chỉ từ class runtime.

## 19. Phương thức và constructor: `this(...)`, `super(...)` không tự vượt access

Trong constructor của lớp con, có thể gọi constructor cha bằng `super(...)` nếu **constructor cha đó truy cập được theo quy tắc Java**.

```java
class Parent {
    private Parent(int code) {
    }
}

class Child extends Parent {
    Child() {
        // super(1); // SAI nếu bỏ comment: Parent(int) private
    }
}
```

Đoạn lớp `Child` trên **không thể biên dịch ngay cả khi dòng `super(1)` đang comment**, vì compiler cố chèn `super()` ngầm định nhưng `Parent` không có constructor zero-argument truy cập được. Đây là **ví dụ cố ý minh họa lỗi**, không phải chương trình runnable.

Nếu superclass cần được subclass từ mã ngoài, chọn constructor `protected` hoặc `public` phù hợp (và cân nhắc `abstract` đối với superclass không nên được khởi tạo trực tiếp).

### 19.1. `this(...)` gọi constructor khác trong cùng lớp

```java
class Rectangle {
    private final int width;
    private final int height;

    public Rectangle() {
        this(1, 1);
    }

    private Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }
}
```

`public Rectangle()` **được phép gọi private constructor `Rectangle(int, int)`**, vì lời gọi `this(1, 1)` diễn ra trong chính `Rectangle`. Constructor private không đồng nghĩa code nội bộ không sử dụng được.

Trong **Java 17**, explicit constructor invocation `this(...)` hoặc `super(...)` phải ở đầu thân constructor. Kiểm soát truy cập không xóa bỏ quy tắc cú pháp này.

### 19.2. Constructor không override

Một subclass không thể thêm `@Override` lên constructor, vì constructor **không được kế thừa**. Nếu tên constructor không trùng tên lớp con, khai báo có thể trở thành một method (nếu có return type) hoặc gây lỗi cú pháp.

Không áp dụng quy tắc “override phải giữ hoặc mở quyền truy cập” cho constructor cha và constructor con: chúng **không tạo quan hệ overriding**.

## 20. Quy tắc lựa chọn mức truy cập khi thiết kế API

Một bảng định hướng:

| Thành phần | Mức thường cân nhắc đầu tiên | Vì sao |
| --- | --- | --- |
| Field chứa trạng thái nghiệp vụ | `private` | Tránh caller phá invariant |
| Field hằng public có nghĩa ổn định | `public static final` | Công bố giá trị dùng chung rõ ràng |
| Helper method chỉ được dùng trong lớp | `private` | Giảm bề mặt API |
| Helper cho mã nội bộ cùng package | Package-private | Hợp tác trong package mà không public ra ngoài |
| Điểm vào API cho caller | `public` | Công bố hành vi cần hỗ trợ |
| Hook dự định cho subclass | `protected` | Cho phép extension có chủ đích |
| Constructor cho kiểu được tạo trực tiếp | `public` hoặc package-private | Phù hợp nhóm caller dự kiến |
| Constructor lớp cơ sở phục vụ subclass | `protected` | Cho lớp con khởi tạo superclass |
| Constructor đi cùng factory/utility | `private` | Kiểm soát đường tạo |

Không phải quy tắc cứng. Mức truy cập phụ thuộc hợp đồng API và việc lớp sẽ được dùng trong cùng module, nhiều module, cùng package hay framework yêu cầu gì.

### 20.1. “Ưu tiên private” không có nghĩa tất cả đều private

Nguyên tắc **least privilege**: cấp đủ quyền cho tác vụ hợp lệ, không mở rộng không cần thiết.

- Nếu subclass cần thay hành vi, `protected` method có thể hợp lý hơn private.
- Nếu một phần ứng dụng khác cần gọi method, dùng public API phù hợp thay vì ép caller dùng reflection.
- Nếu helper chỉ dành cho cùng package, package-private có thể tránh phơi bày contract công khai.
- Nếu lớp là thư viện công khai, chú ý thay access modifier trong phiên bản sau có thể **phá code phụ thuộc**, đặc biệt khi thu hẹp quyền truy cập.

Một API public đã được sử dụng rộng rãi cần được thay đổi cẩn thận; không nên “sửa lỗi bảo mật” bằng cách tùy tiện đổi mọi public member thành private mà không xem contract.

## 21. Những lỗi biên dịch thường gặp

| Tình huống | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| `field has private access` | Caller đọc/ghi private field từ ngoài ngữ cảnh hợp lệ | Dùng method công khai theo hợp đồng, không mở field tùy tiện |
| `method is not public ... cannot be accessed from outside package` | Method package-private bị gọi từ package khác | Công bố API thật sự cần, hoặc đặt caller trong đúng package kiến trúc |
| `constructor ... has private access` | Caller gọi constructor private | Dùng factory; chỉ mở constructor nếu mong muốn |
| `constructor ... has protected access` | Caller không là ngữ cảnh kế thừa hợp lệ hoặc khác package | Gọi qua `super(...)` trong subclass phù hợp, hoặc thiết kế factory |
| `cannot find symbol` khi method có ở runtime subclass | Biến có kiểu tĩnh superclass không khai báo method | Dùng interface chung, cast an toàn hoặc kiểu tĩnh phù hợp |
| Subclass override public method bằng protected | Giảm visibility | Giữ public |
| Class implements interface nhưng method package-private | Interface abstract method là public | Khai báo `public` ở implementation |
| `private class Foo` ở top-level | Top-level class không nhận private/protected | Dùng package-private hoặc public; nested class có quy tắc khác |
| `default void work()` trong class thường | Nhầm keyword interface default method với package-private | Bỏ modifier `default` trong class |
| Caller cùng thư mục nhưng khác package vẫn không truy cập được | Quyền package dựa vào khai báo `package`, không phải vị trí nhìn thấy trên ổ đĩa | Kiểm tra package name chính xác |
| `store.internal` tưởng là “con” của `store` nên được package-private | Hai tên package khác nhau | Thiết kế public/protected API nếu cần |
| `public class` nhưng từ module khác không dùng được | Package của module có thể không được export | Kiểm tra `module-info.java` và `exports` |
| `super()` lỗi vì constructor cha private/không tồn tại | Lớp con không thể gọi superclass constructor cần thiết | Khai báo `super(args)` tới constructor được truy cập; sửa API cha nếu hợp lý |
| Field `public final` đọc được nhưng không gán được | `final` chặn reassignment sau khởi tạo | Phân biệt access với khả năng ghi |
| Static helper dùng `this.privateField` báo lỗi | Static context không có `this` | Chuyển sang instance method hoặc nhận object làm tham số |
| Public getter trả mutable list và caller sửa được dữ liệu nội bộ | Getter làm lộ object mutable qua giá trị trả về | Trả snapshot/immutable view phù hợp hoặc điều chỉnh contract |

Thông báo cụ thể của `javac` có thể khác nhau giữa các phiên bản, nhưng cách chẩn đoán vẫn gồm **kiểu khai báo**, **package**, **quan hệ kế thừa**, **mức truy cập của thành viên** và **ngữ cảnh lời gọi**.

## 22. Bài tập tự luyện với đáp án

### Bài 1 — Field private và method public

```java
class Student {
    private int score;

    public void setScore(int score) {
        if (score < 0) {
            throw new IllegalArgumentException("Invalid score");
        }
        this.score = score;
    }

    public int getScore() {
        return score;
    }
}
```

Với `Student student = new Student();` trong một class khác cùng package:

- `student.setScore(10);` → **hợp lệ**.
- `System.out.println(student.getScore());` → **hợp lệ**, in `10`.
- `student.score = -5;` → **không hợp lệ**, vì `score` là private.

**Bài học:** caller có quyền gọi method công khai, không được bỏ qua kiểm tra bằng cách truy cập field private.

### Bài 2 — Package-private từ package khác

```java
package model;

public class User {
    int level = 1;

    void promote() {
        level++;
    }

    public int level() {
        return level;
    }
}
```

Một lớp `app.Main` thuộc package `app`:

- `User user = new User();` → hợp lệ nếu constructor mặc định công khai và các điều kiện truy cập khác thỏa.
- `user.level;` → **không hợp lệ** từ package khác.
- `user.promote();` → **không hợp lệ** từ package khác.
- `user.level();` → **hợp lệ**, vì method public.

**Bài học:** lớp public không làm field/method package-private thành public.

### Bài 3 — Protected field từ subclass ngoài package

Giả sử `core.Base` có `protected int count;` và `client.Child extends Base`. Trong instance method của `Child`:

```java
this.count = 1;       // Hợp lệ
Child peer = new Child();
peer.count = 2;       // Hợp lệ
Base base = new Base();
// base.count = 3;    // Không hợp lệ qua receiver Base từ package khác
```

**Bài học:** protected access ngoài package có ràng buộc về receiver; không thể sử dụng mọi superclass object tùy ý.

### Bài 4 — Constructor private và factory

```java
public final class Ticket {
    private Ticket() {
    }

    public static Ticket create() {
        return new Ticket();
    }
}
```

Từ lớp độc lập khác:

- `new Ticket()` → **không hợp lệ**.
- `Ticket.create()` → **hợp lệ**, nhận được một đối tượng `Ticket` nếu method chạy thành công.

**Bài học:** quyền **nhận/sử dụng** một object khác quyền **gọi trực tiếp constructor** của nó.

### Bài 5 — Default constructor có tự sinh không?

```java
class Box {
    private Box(int size) {
    }
}
```

`new Box()` từ một lớp khác có hợp lệ không?

**Không.** Vì đã có constructor tường minh `Box(int)`, compiler không tự thêm no-arg constructor. Cũng không thể gọi `new Box(1)` từ lớp không có quyền vì constructor ấy private.

### Bài 6 — Interface method visibility

```java
interface RunnableTask {
    void run();
}

class Task implements RunnableTask {
    // void run() { } // Không hợp lệ nếu đây là implementation.
}
```

Để triển khai đúng:

```java
class Task implements RunnableTask {
    @Override
    public void run() {
        System.out.println("Run");
    }
}
```

Hai đoạn `Task` là **phiên bản thay thế**, không đặt đồng thời trong cùng package. Interface method `run()` public theo quy tắc, nên implementation phải public.

### Bài 7 — Overriding được phép mở quyền không?

```java
class Parent {
    protected void work() {
    }
}

class Child extends Parent {
    @Override
    public void work() {
    }
}
```

**Đáp án:** hợp lệ. Override từ protected lên public là **mở rộng** quyền truy cập. Ngược lại, override public method bằng protected method bị từ chối.

### Bài 8 — Nested class đọc private field

Trong cùng outer class:

```java
class Outer {
    private int value = 5;

    class Inner {
        int read() {
            return value;
        }
    }
}
```

**Đáp án:** `Inner.read()` được phép đọc `Outer.value` theo quy tắc nested class. Một class top-level độc lập khác chỉ vì cùng package không tự được đọc field private.

### Bài 9 — Truy cập field public final

```java
class Settings {
    public final int limit = 10;
}
```

Với `Settings settings = new Settings();`:

- `System.out.println(settings.limit);` → hợp lệ.
- `settings.limit = 20;` → **không hợp lệ**, vì `limit` là final, dù field public.

**Bài học:** access control và quyền gán giá trị không phải một.

## 23. Checklist trước khi khai báo field, method hoặc constructor

1. **Xác định ai là caller dự kiến:** cùng lớp, cùng package, subclass ngoài package hay mã công khai từ package/module khác?
2. **Kiểm tra lớp chứa thành viên có nhìn thấy được không:** top-level class public/package-private, nested class hoặc module export.
3. **Chọn access modifier cho từng thành viên**, không dựa vào modifier của class để đoán.
4. **Field có cần cho caller sửa trực tiếp không?** Nếu không, cân nhắc private và method công khai phù hợp.
5. **Method nào là hợp đồng API thực sự?** Cho public những method cần thiết; giữ helper private hoặc package-private khi phù hợp.
6. **Có cần extension point cho subclass không?** Dùng protected có chủ đích, tránh cho subclass thấy state quá rộng.
7. **Nếu protected từ package khác**, kiểm tra kiểu receiver và quy tắc truy cập tương ứng.
8. **Nếu constructor là protected**, subclass có thể cần `super(...)`; protected constructor không mở quyền `new Base(...)` cho mọi caller.
9. **Nếu constructor là private**, đã có factory/API cung cấp instance theo yêu cầu chưa? Đã rà soát những overload constructor khác chưa?
10. **Nếu không khai báo constructor**, nhớ default constructor có thể được sinh; muốn kiểm soát tạo object phải khai báo tường minh.
11. **Nếu override**, không giảm access so với method được override; method private không phải mục tiêu override.
12. **Nếu implements interface**, implementation của abstract method public cũng phải public.
13. **Nếu có `static` và `final`**, phân biệt quyền truy cập, khả năng reassignment và dynamic dispatch.
14. **Nếu dùng nested class**, đừng áp dụng máy móc quy tắc “một lớp khác không bao giờ đọc được private” cho các ngữ cảnh cùng nest.
15. **Nếu xây thư viện module**, xem thêm exports/opens; `public` không đủ nếu package không được công bố cho module khác.
16. **Dùng compiler và ví dụ nhiều package** để kiểm tra dự đoán; đặc biệt tránh “sửa lỗi” bằng cách biến mọi thành viên thành public.

## Ghi nhớ

- Java kiểm soát **khả năng truy cập** của **field**, **method** và **constructor** theo modifier khai báo và ngữ cảnh sử dụng.
- **`public`:** cho phép truy cập rộng nhất khi kiểu/module cũng truy cập được; **package-private:** chỉ cùng package; **`protected`:** cùng package và quyền đặc biệt cho subclass; **`private`:** giới hạn mạnh, với các ngữ cảnh cùng nest hợp lệ.
- **Field private + method công khai có kiểm soát** là mẫu đóng gói phổ biến; private không tự làm object immutable.
- **Constructor có quyền truy cập riêng**: một public class vẫn có thể cấm `new` từ bên ngoài qua private constructor, nhưng cung cấp public static factory.
- **`protected` ngoài package cần xem receiver** khi truy cập field/method; protected constructor cho subclass gọi `super(...)` không phải cho mọi mã viết `new Base(...)`.
- **Không có constructor tường minh** thì compiler có thể sinh default no-arg constructor; **đã có một constructor** thì compiler không tự thêm no-arg.
- **Override instance method không được giảm visibility**; private method không bị override theo đa hình; interface abstract method ngầm định là public.
- **Access modifier không thay thế `final`, kiểm tra dữ liệu hay thread safety**. Thiết kế đúng phải đồng thời xét quyền nhìn thấy, cách thay trạng thái và hợp đồng của đối tượng.
