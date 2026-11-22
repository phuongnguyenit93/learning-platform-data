# Truy cập từ cùng lớp, cùng gói và khác gói trong Java

Khi viết một class Java, các field, method và constructor không nhất thiết được sử dụng tự do từ mọi vị trí. Java kiểm soát việc truy cập thông qua **access modifiers** và quan hệ giữa mã đang truy cập với mã khai báo thành viên: có nằm trong **cùng class**, **cùng package**, hay **khác package**? Nếu khác package, mã đó có phải **subclass** hay không?

Ví dụ:

~~~java
class Account {
    private String password;
    String internalNote;
    protected int rewardPoints;
    public String accountId;
}
~~~

Bốn field trên có **bốn mức truy cập khác nhau**. Một class khác nằm trong cùng package có thể truy cập `internalNote` và `rewardPoints`, nhưng không thể trực tiếp đọc `password`. Một class ở package khác không phải subclass thường chỉ dùng được `accountId`, với điều kiện bản thân `Account` là một kiểu có thể truy cập.

Điểm dễ nhầm nhất là **`protected`**: từ package khác, subclass không được tùy ý đọc protected member qua *mọi tham chiếu mang kiểu superclass*. Java còn có quy tắc về **kiểu của biểu thức dùng làm receiver**.

Bài này hướng dẫn đầy đủ cách phân biệt **`public`**, **`protected`**, **package-private** (không ghi modifier) và **`private`**, cơ chế kiểm tra quyền truy cập giữa các package, constructor, kế thừa, nested classes và module. Các ví dụ ưu tiên **Java 17+**, có bố trí thư mục, lệnh biên dịch và kết quả cụ thể.

## 1. Học xong cần trả lời được điều gì?

1. Một **class** và một **package** có quan hệ thế nào trong Java?
2. Bốn mức quyền truy cập cho phép ai đọc/gọi một member?
3. Vì sao **package-private** không phải cùng nghĩa với `protected`?
4. Vì sao class ở **cùng package** có thể truy cập member package-private mà không cần kế thừa?
5. Vì sao subclass ở package khác có thể dùng `this.protectedField` nhưng thường không dùng được `baseReference.protectedField`?
6. Những quy tắc này áp dụng ra sao cho **field**, **instance method**, **static method** và **constructor**?
7. Tại sao `public` member chưa đủ nếu **kiểu chứa member** không thể được nhìn thấy?
8. Quyền truy cập ảnh hưởng thế nào khi **override**, tạo object, thiết kế API và tách package?
9. Vì sao `import` không cấp thêm quyền?
10. Java modules (**JPMS**) có thể giới hạn việc dùng public API qua ranh giới module thế nào?

## 2. Package là gì và “cùng gói” được hiểu ra sao?

Package là cơ chế nhóm các kiểu liên quan trong Java. Một file có thể khai báo:

~~~java
package learn.access.base;

public class Account {
}
~~~

Đây là mã class minh họa, lưu trong file `Account.java`. Theo quy ước dự án, đường dẫn source thường tương ứng:

~~~text
src/
└── learn/
    └── access/
        └── base/
            └── Account.java
~~~

Hai top-level classes khai báo cùng package `learn.access.base` có quan hệ **cùng gói** trong ngữ cảnh biên dịch thông thường, dù nằm ở **hai file khác nhau**. Chỉ vì hai folder vật lý gần nhau, có tên giống nhau hoặc một package là tiền tố của package khác **không tự tạo** quan hệ cùng gói.

Ví dụ:

| Package của A | Package của B | Có cùng package không? |
| --- | --- | --- |
| `learn.access.base` | `learn.access.base` | Có |
| `learn.access.base` | `learn.access.child` | Không |
| `learn.access` | `learn.access.base` | Không |
| `app` | `app.internal` | Không |
| `app.model` | `app.model.sub` | Không |

**Package con không được “thừa kế” quyền package-private từ package cha.** `app.internal` và `app` là hai package khác nhau dù tên thể hiện quan hệ phân cấp. Dấu chấm trong package name chỉ tổ chức tên, không tạo đặc quyền truy cập.

### Package không đồng nghĩa với class

Hai class trong cùng package là **hai class khác nhau**. Chúng có thể đọc những thành viên package-private của nhau, nhưng **không thể trực tiếp đọc private member của class kia** chỉ vì cùng package.

Ví dụ:

~~~java
package sample;

class First {
    private int pin = 7;
    int amount = 10;
}

class Second {
    void inspect(First first) {
        System.out.println(first.amount); // Hợp lệ: cùng package.
        // System.out.println(first.pin); // Lỗi: private.
    }
}
~~~

Đây là đoạn mã minh họa hợp lệ nếu để dòng lỗi được chú thích. Cả hai class thuộc package `sample` và không cần quan hệ kế thừa.

## 3. Bảng quyền truy cập quan trọng nhất

Trong ngữ cảnh Java class thông thường trên classpath, bảng sau là nền tảng:

| Mức truy cập của member | Trong chính class khai báo | Class khác cùng package | Subclass ở package khác | Class không phải subclass ở package khác |
| --- | --- | --- | --- | --- |
| `public` | Có | Có | Có | Có |
| `protected` | Có | Có | Có, **có điều kiện** | Không |
| *Không có modifier* (package-private) | Có | Có | Không | Không |
| `private` | Có | Không theo quan hệ package thông thường | Không | Không |

Đọc bảng cùng ba lưu ý:

- Với **`protected` từ package khác**, có quy tắc về subclass và receiver type, được giải thích riêng ở phần sau. Không chỉ cần “có `extends`” là đủ cho mọi biểu thức truy cập.
- Bảng mô tả **member của một kiểu đã truy cập được**. Nếu class chứa member không thể truy cập từ bên ngoài, một method `public` bên trong không tự mở đường truy cập qua tên class đó.
- Với **nested classes/nestmates**, Java cho phép một số truy cập private giữa các kiểu trong cùng một top-level declaration; đây là ngoại lệ dựa trên *nest*, **không phải vì chúng cùng package**.

Một cách nhớ phạm vi tăng dần, bỏ qua những điều kiện chi tiết của `protected`:

~~~text
private ⊂ package-private ⊂ protected ⊂ public
           ^                  ^
           |                  |
      cùng package      thêm quan hệ subclass
                        qua package khác
~~~

Đây là sơ đồ trực giác về phạm vi **không phải một phép so sánh cơ học cho mọi receiver**. `protected` có phần đặc biệt khi vượt ranh giới package, nên không được suy ra rằng tất cả cú pháp cho phép trong cùng package cũng hợp lệ trong subclass khác package.

## 4. `private`: giới hạn truy cập của member

Field hoặc method khai báo `private` thường được truy cập bởi mã **bên trong class khai báo** (và các ngữ cảnh cùng nest hợp lệ), chứ không bởi một class độc lập chỉ cùng package.

~~~java
public class BankAccount {
    private long balanceCents;

    public BankAccount(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }
}
~~~

Đây là một class hoàn chỉnh nhưng chưa có `main`. Class gọi ở package khác có thể dùng `new BankAccount(100)` và `account.balanceCents()` nếu class/method là public và có thể truy cập, nhưng **không** thể dùng `account.balanceCents` nếu field vẫn `private`.

`private` giúp duy trì **đóng gói (encapsulation)**. Nó cho phép class kiểm soát những thao tác làm đổi trạng thái object, thay vì để caller sửa field tùy ý.

### Trong chính class, có thể đọc private field của object khác cùng class

Một nhầm lẫn phổ biến: “`private` chỉ cho phép dùng `this.privateField`, không cho đọc privateField của *object khác*.” Đây là cách hiểu sai.

Trong thân class `BankAccount`, bạn có thể viết:

~~~java
boolean sameBalance(BankAccount other) {
    return this.balanceCents == other.balanceCents;
}
~~~

Vì code ở trong **class khai báo field**, nó được quyền truy cập private member trên những instance `BankAccount` phù hợp, không chỉ instance được gọi qua `this`.

### Chương trình chạy độc lập

Tạo file **`PrivateAccessDemo.java`**:

~~~java
public class PrivateAccessDemo {
    static final class Box {
        private final int secret;

        Box(int secret) {
            this.secret = secret;
        }

        boolean sameSecret(Box other) {
            return this.secret == other.secret;
        }
    }

    public static void main(String[] args) {
        Box a = new Box(7);
        Box b = new Box(7);
        Box c = new Box(9);

        System.out.println("a/b=" + a.sameSecret(b));
        System.out.println("a/c=" + a.sameSecret(c));
        // System.out.println(a.secret); // Ở ví dụ nested cùng nest,
        // Java 17 có thể cho phép: xem mục nested class bên dưới.
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
~~~

Stdout:

~~~text
a/b=true
a/c=false
~~~

`sameSecret` nằm trong chính class `Box` nên đọc private field của `other` hợp lệ. `Box` là nested class của `PrivateAccessDemo`; Java 17 cũng có cơ chế truy cập private giữa các **nestmates**, vì vậy không nên dùng riêng ví dụ nested này để kết luận một top-level class bất kỳ khác package cũng được đọc `secret`.

## 5. Package-private: không viết access modifier

Trong Java, **không ghi `public`, `protected` hay `private`** ở một member có thể khiến nó có quyền **package-private** (còn gọi là *default access* trong cách diễn đạt thông thường).

~~~java
package sample.orders;

class OrderHelper {
    static String tag() {
        return "internal";
    }
}
~~~

`OrderHelper` là một **top-level class package-private**; `tag()` cũng package-private. Class khác trong `sample.orders` có thể truy cập chúng theo những quy tắc thông thường. Class ở `sample.app` không được dùng `OrderHelper` trực tiếp qua tên kiểu này dù viết `import sample.orders.OrderHelper;`.

**Không viết từ khóa `default` để biểu thị package-private:**

~~~java
// default class OrderHelper {} // Không phải cú pháp access modifier.
class OrderHelper {}             // Đúng: package-private.
~~~

Từ `default` còn được dùng ở **default method của interface** và nhánh `default` của `switch`, nhưng không phải từ khóa truy cập tương đương “package-private”.

### Khi nên dùng package-private?

- Helper class chỉ dành cho một package.
- Các method nội bộ cần cộng tác giữa nhiều class cùng package nhưng không muốn trở thành API công khai.
- Logic hỗ trợ kiểm thử nội bộ hoặc triển khai chi tiết mà chưa cần xuất ra ngoài package.

Không nên mở toàn bộ member thành `public` chỉ để một class khác gọi thuận tiện, nếu quan hệ thiết kế thực sự nên giữ bên trong package.

## 6. `protected`: cùng package được phép, khác package cần quan hệ subclass

`protected` kết hợp hai nhóm được phép truy cập:

1. **Trong cùng package:** class khác có thể truy cập protected member theo quy tắc package, **không cần** là subclass.
2. **Khác package:** class đang truy cập cần nằm trong ngữ cảnh subclass hợp lệ của class khai báo member, và với nhiều loại qualified access còn phải thỏa **điều kiện về receiver**.

Ví dụ:

~~~java
package sample.base;

public class Base {
    protected int score = 10;
}
~~~

Một class khác **cùng `sample.base`** có thể viết:

~~~java
package sample.base;

class SamePackage {
    int read(Base base) {
        return base.score; // Hợp lệ vì cùng package.
    }
}
~~~

Nhưng class không phải subclass ở package khác không thể truy cập `base.score`:

~~~java
package sample.client;

import sample.base.Base;

class External {
    int read(Base base) {
        // return base.score; // Lỗi: protected không mở cho client này.
        return 0;
    }
}
~~~

Những file trên là ví dụ minh họa nhiều package; không ghép các khai báo `package` vào cùng một file.

### `protected` khác package-private ra sao?

Một member package-private chỉ dựa trên ranh giới package. Một member `protected` được phép truy cập trong package **và** có thể được subclass ở package khác sử dụng trong những điều kiện được JLS quy định.

Tuy nhiên **`protected` không có nghĩa “bất kỳ subclass nào được đọc member đó qua mọi Base object”**. Đây là điểm cần phân tích kỹ ở phần sau.

## 7. Receiver của `protected` khi truy cập từ package khác

Với `Derived extends Base` và hai class ở hai package, subclass có thể dùng protected instance field `score` qua `this` hoặc một expression có kiểu tĩnh `Derived`/subtype của `Derived`; chỉ biết reference có kiểu `Base` là **chưa đủ**.

~~~java
// Trong class Derived extends Base, khác package khai báo score:
int own() { return this.score; }         // Hợp lệ.
int peer(Derived other) { return other.score; } // Hợp lệ.
int arbitrary(Base base) {
    // return base.score;                 // Lỗi compile time.
    return this.score;
}
~~~

Đây là **method fragments** được đặt trong subclass phù hợp, không phải chương trình Java độc lập. So nhanh từ body của Derived:

| Biểu thức | Có hợp lệ? | Vì sao |
| --- | --- | --- |
| `this.score` | Có | Current subclass receiver |
| `other.score` với `Derived other` | Có | Receiver kiểu Derived |
| `base.score` với `Base base` | Không | Kiểu Base quá rộng |
| `new Base().score` | Không | Receiver kiểu Base |
| `((Derived) base).score` | Có thể biên dịch | Cast khiến kiểu tĩnh phù hợp nhưng có thể ném ClassCastException lúc chạy |

**Cast không phải phép cấp quyền truy cập** và không chuyển một Base object thành Derived object. Cũng không áp dụng bảng receiver instance này cho protected constructor/static member một cách máy móc. Bài chuyên `protected` qua lớp con khác package phân tích kỹ receiver, `super`, casts, sibling subclasses và các ngoại lệ.

## 8. Dự án nhiều package hoàn chỉnh: kiểm chứng bốn mức truy cập

Các ví dụ riêng có thể dễ hiểu, nhưng để **thực sự thấy ranh giới package**, hãy tạo một dự án nhỏ với năm file Java. Ví dụ này được thiết kế để **biên dịch và chạy trực tiếp trên JDK 17+**.

### Cấu trúc thư mục

~~~text
access-lab/
└── src/
    └── learn/
        └── access/
            ├── App.java
            ├── base/
            │   ├── Vault.java
            │   └── Neighbor.java
            ├── child/
            │   └── ChildVault.java
            └── client/
                └── Visitor.java
~~~

Mỗi file có **một khai báo `package`** khớp thư mục trong dự án này.

### File 1: `src/learn/access/base/Vault.java`

~~~java
package learn.access.base;

public class Vault {
    private final int pin = 7;
    String packageNote = "package";
    protected int points = 5;
    public int id = 9;

    public Vault() {
    }

    private String privateInfo() {
        return "pin=" + pin;
    }

    public String inspectOwnMembers() {
        return pin + "|" + packageNote + "|" + points + "|" + id;
    }

    public String callPrivateMethod() {
        return privateInfo();
    }

    protected String kind() {
        return "base";
    }
}
~~~

Trong chính `Vault`, method `inspectOwnMembers` có thể đọc cả bốn field vì chúng được khai báo trong chính class. `callPrivateMethod` có thể gọi private method `privateInfo`.

### File 2: `src/learn/access/base/Neighbor.java`

~~~java
package learn.access.base;

public class Neighbor {
    public static String inspect(Vault vault) {
        return vault.packageNote + "|" + vault.points + "|" + vault.id;
    }
}
~~~

`Neighbor` **không extends Vault**. Nhưng vì cùng package `learn.access.base`, nó đọc được `packageNote` (package-private) và `points` (protected). Nó không thể trực tiếp đọc `pin` vì private.

### File 3: `src/learn/access/child/ChildVault.java`

~~~java
package learn.access.child;

import learn.access.base.Vault;

public class ChildVault extends Vault {
    public ChildVault() {
        super();
    }

    @Override
    protected String kind() {
        return "child";
    }

    public String inspectSelf() {
        return this.points + "|" + this.id + "|" + this.kind();
    }

    public String inspectPeer(ChildVault another) {
        return another.points + "|" + another.id;
    }

    public String inspectArbitraryBase(Vault another) {
        // return another.points; // Sai: kiểu receiver Vault.
        // return another.packageNote; // Sai: package-private.
        // return another.pin; // Sai: private.
        return String.valueOf(another.id);
    }
}
~~~

`ChildVault` ở **package khác** với `Vault` nhưng là subclass. Nó dùng được `this.points` và `another.points` khi `another` có kiểu `ChildVault`. Nó không thể đọc `packageNote` vì member chỉ package-private ở `learn.access.base`. Nó cũng không được đọc `pin` dù kế thừa từ Vault về quan hệ kiểu.

### File 4: `src/learn/access/client/Visitor.java`

~~~java
package learn.access.client;

import learn.access.base.Vault;

public class Visitor {
    public static int readPublic(Vault vault) {
        // vault.pin;         // Sai: private.
        // vault.packageNote; // Sai: package-private.
        // vault.points;      // Sai: protected ngoài package, không subclass.
        return vault.id;
    }
}
~~~

`Visitor` ở package khác và **không phải subclass**, nên trực tiếp đọc được field public `id` của public class `Vault`, không được đọc ba field còn lại.

### File 5: `src/learn/access/App.java`

~~~java
package learn.access;

import learn.access.base.Neighbor;
import learn.access.base.Vault;
import learn.access.child.ChildVault;
import learn.access.client.Visitor;

public class App {
    public static void main(String[] args) {
        Vault base = new Vault();
        ChildVault child = new ChildVault();

        System.out.println("own=" + base.inspectOwnMembers());
        System.out.println("private method=" + base.callPrivateMethod());
        System.out.println("neighbor=" + Neighbor.inspect(base));
        System.out.println("child=" + child.inspectSelf());
        System.out.println("peer=" + child.inspectPeer(new ChildVault()));
        System.out.println("visitor=" + Visitor.readPublic(base));
    }
}
~~~

### Biên dịch và chạy

Tại thư mục `access-lab`, thực thi:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/learn/access/App.java
java -cp out learn.access.App
~~~

`-sourcepath src` cho compiler biết nơi tìm các source classes tham chiếu khi cần; `-d out` lưu kết quả class files theo package path dưới thư mục `out`. Tên main class khi chạy là **fully qualified class name** `learn.access.App`, không phải `App` đơn lẻ từ thư mục dự án.

Stdout:

~~~text
own=7|package|5|9
private method=pin=7
neighbor=package|5|9
child=5|9|child
peer=5|9
visitor=9
~~~

### Những kết quả được chứng minh

1. **Cùng class (`Vault`):** truy cập được private, package-private, protected và public field.
2. **Cùng package (`Neighbor`):** đọc package-private/protected/public của `Vault`, dù không phải subclass.
3. **Khác package, subclass (`ChildVault`):** dùng `protected points` qua `this` và qua `ChildVault` receiver; không dùng package-private field của Base.
4. **Khác package, không subclass (`Visitor`):** chỉ dùng public member trên kiểu `Vault` có thể truy cập.
5. **Package con (`learn.access`):** `App` là **khác package** so với `learn.access.base`, dù tên package có tiền tố chung.

Các dòng truy cập không hợp lệ được **đặt trong comment**. Khi học compiler error, bạn có thể bỏ comment **mỗi dòng một lần** và thử `javac` để quan sát lỗi, rồi comment lại để chương trình chạy.

## 9. Chỉ `import` không cấp thêm quyền

`import` giúp code dùng tên ngắn của class hoặc static member theo các quy tắc Java; nó **không sửa mức truy cập**.

Ví dụ:

~~~java
package external.app;

import learn.access.base.Vault;

class Demo {
    void show(Vault vault) {
        System.out.println(vault.id); // Public: hợp lệ.
        // System.out.println(vault.points); // Protected: lỗi.
    }
}
~~~

Một class `import` được `Vault` thành công không có nghĩa nó được đọc mọi field trong Vault. Tương tự, viết tên đầy đủ `learn.access.base.Vault` thay vì `Vault` **cũng không vượt quyền**.

Nếu một top-level class là package-private:

~~~java
package learn.access.base;

class InternalHelper {}
~~~

thì ở một package khác, việc cố `import learn.access.base.InternalHelper;` sẽ bị từ chối do kiểu không truy cập được. Không thể dùng import để “mở khóa” một top-level class.

### `import static` cũng không bypass access checks

~~~java
import static java.lang.Math.max;
~~~

Chỉ cho phép dùng tên `max` theo các quy tắc import; member vẫn phải có quyền truy cập hợp lệ. Nếu static member là private hoặc protected không đáp ứng điều kiện, không phải cứ viết `import static` là truy cập được.

## 10. Mức truy cập của top-level class

Khi khai báo **top-level class** (không nằm bên trong một kiểu khác), chỉ có hai lựa chọn access thông dụng:

- `public class Example`.
- `class Example` — package-private.

Không khai báo:

~~~java
// private class TopLevel {}   // Lỗi khi là top-level class.
// protected class TopLevel {} // Lỗi khi là top-level class.
~~~

`private` và `protected` có thể áp dụng cho **nested classes**, nhưng không áp dụng trực tiếp cho top-level class.

### Quyền của member không mở rộng quyền của kiểu bao ngoài

~~~java
package lab.hidden;

class HiddenService {
    public void execute() {
        System.out.println("running");
    }
}
~~~

Đây là class package-private. Một class ở `lab.client` thường **không thể dùng trực tiếp kiểu `HiddenService`** chỉ vì `execute` là public. Trước hết, kiểu bao ngoài phải truy cập được tại vị trí dùng.

Ngược lại, trong package `lab.hidden`, các class khác có thể dùng `HiddenService` và gọi public method, miễn những điều kiện còn lại được đáp ứng.

## 11. Access của constructor ảnh hưởng khả năng tạo object

Constructor cũng có thể là `public`, `protected`, package-private hoặc `private`.

~~~java
public class Resource {
    public Resource() { }

    protected Resource(int capacity) { }

    Resource(String key) { }

    private Resource(boolean internal) { }
}
~~~

Đây là class minh họa với bốn constructor khác chữ ký.

| Constructor | Cùng class | Class khác cùng package | Subclass khác package | Client không phải subclass khác package |
| --- | --- | --- | --- | --- |
| `public Resource()` | Có | Có | Có | Có |
| `protected Resource(int)` | Có | Có | Được gọi trong ngữ cảnh constructor kế thừa thích hợp | Không gọi tạo Base object trực tiếp theo cách thông thường |
| `Resource(String)` | Có | Có | Không | Không |
| `private Resource(boolean)` | Có | Không theo package thông thường | Không | Không |

**Constructor không được kế thừa**: khi subclass viết `super(...)`, đó là lời gọi constructor của superclass trong quá trình khởi tạo **một subclass instance**, chứ không phải “thừa kế constructor như một method”.

### Ví dụ Java 17+ với protected constructor

Tạo ba file:

~~~text
constructor-lab/
└── src/
    └── lab/
        ├── App.java
        ├── base/
        │   └── Device.java
        └── child/
            └── Phone.java
~~~

`src/lab/base/Device.java`:

~~~java
package lab.base;

public class Device {
    private final int code;

    protected Device(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
~~~

`src/lab/child/Phone.java`:

~~~java
package lab.child;

import lab.base.Device;

public class Phone extends Device {
    public Phone() {
        super(42);
    }
}
~~~

`src/lab/App.java`:

~~~java
package lab;

import lab.child.Phone;

public class App {
    public static void main(String[] args) {
        Phone phone = new Phone();
        System.out.println("code=" + phone.code());
    }
}
~~~

Biên dịch/chạy trong thư mục `constructor-lab`:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/lab/App.java
java -cp out lab.App
~~~

Stdout:

~~~text
code=42
~~~

`Phone` ở package khác nhưng có quyền gọi `super(42)` tới protected constructor của `Device` trong ngữ cảnh kế thừa hợp lệ. Nhưng một client bình thường trong `lab` không được tự viết `new Device(42)` như gọi public constructor; ví dụ còn bị hạn chế bởi protected access.

### Constructor `private` và static factory

Class có thể muốn kiểm soát hoàn toàn đường tạo object:

~~~java
public final class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value required");
        }
        return new Token(value);
    }
}
~~~

Class minh họa này có constructor private, nhưng public factory `Token.of(...)` có thể tạo object bằng constructor ấy **từ trong class Token** rồi trả reference. Client gọi `Token.of("ABC")` chứ không gọi `new Token("ABC")`.

## 12. Access của static field và static method

Các modifier áp dụng cho **static members** với những quy tắc tiếp cận tương tự, nhưng static member thuộc class chứ không thuộc từng instance.

~~~java
package sample.base;

public class Settings {
    private static int secretCode = 1;
    static int packageSetting = 2;
    protected static int protectedSetting = 3;
    public static int publicSetting = 4;
}
~~~

Một class cùng package có thể dùng `Settings.packageSetting`, `Settings.protectedSetting` và `Settings.publicSetting`, nhưng không đọc `secretCode` trực tiếp.

Ở subclass khác package, `protected static` có quy tắc protected access đối với **kiểu làm qualifier**. Ví dụ subclass `DerivedSettings extends Settings` có thể dùng `DerivedSettings.protectedSetting` trong ngữ cảnh hợp lệ. Không nên nghĩ rằng cứ đặt tên superclass `Settings.protectedSetting` trong package khác thì luôn hợp lệ.

### Đừng truy cập static member qua object khi có tên class rõ

Java có thể chấp nhận `instance.staticMethod()` trong một số trường hợp, nhưng điều đó dễ gây hiểu nhầm rằng method phụ thuộc trạng thái instance. Ưu tiên:

~~~java
Settings.publicSetting
~~~

thay vì dùng biến instance làm qualifier. Quyền truy cập vẫn được kiểm tra theo khai báo của static member và vị trí truy cập, không biến static member thành instance member.

## 13. Quy tắc đặc biệt của protected static access từ package khác

Giả sử:

~~~java
package sample.base;

public class Base {
    protected static int counter = 1;
}
~~~

Một subclass `Child extends Base` ở package khác có thể dùng tên static member kế thừa trong ngữ cảnh hợp lệ:

~~~java
package sample.child;

import sample.base.Base;

public class Child extends Base {
    public static int read() {
        return Child.counter;
    }
}
~~~

Nhưng một class khác trong package `sample.child` không tự được truy cập `Child.counter` nếu member vẫn là protected được khai báo trong `sample.base.Base`; chỉ cùng package với subclass **không** biến member protected của superclass thành package-private tại package subclass.

**Kết luận:** Với inherited protected member, hãy hỏi nó **được khai báo ở class/package nào**, không chỉ nhìn class được dùng làm qualifier. Điều kiện package được xét theo **package của class khai báo member**, không tự dịch chuyển sang package của mỗi subclass.

## 14. Nested class và private access: ngoại lệ cần biết

Từ góc nhìn cơ bản, `private` chỉ dùng trong class khai báo. Tuy nhiên Java còn có **nested classes** thuộc một nhóm *nestmates*, có thể truy cập các private members của nhau theo quy tắc ngôn ngữ và JVM (Java 11+ có mô hình nestmate trực tiếp ở bytecode).

Ví dụ file **`NestmateAccessDemo.java`**:

~~~java
public class NestmateAccessDemo {
    private int outerSecret = 7;

    private static class Nested {
        private int innerSecret = 9;
    }

    public int readNested(Nested nested) {
        return nested.innerSecret;
    }

    public static void main(String[] args) {
        NestmateAccessDemo outer = new NestmateAccessDemo();
        Nested nested = new Nested();

        System.out.println("outer=" + outer.outerSecret);
        System.out.println("nested=" + outer.readNested(nested));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestmateAccessDemo.java
java NestmateAccessDemo
~~~

Stdout:

~~~text
outer=7
nested=9
~~~

`NestmateAccessDemo` đọc private field `innerSecret` của nested class trong cùng nest theo quy tắc Java. Điều này **không** có nghĩa class bất kỳ ở cùng package với `Nested` cũng đọc được `innerSecret`.

### Nested class có thể là `public`, `protected`, package-private, `private`

~~~java
public class Container {
    public static class PublicPart { }
    protected static class ProtectedPart { }
    static class PackagePart { }
    private static class PrivatePart { }
}
~~~

Bốn mức này hợp lệ cho member nested types của một class. Nhưng khi sử dụng chúng từ bên ngoài, **mọi kiểu bao ngoài trong tên** cũng cần truy cập được. Không được bỏ qua việc kiểm tra quyền đối với `Container` hoặc enclosing types khác.

Đối với non-static inner class, còn có enclosing instance; điều đó không tự làm quyền access rộng hơn các modifier.

## 15. Access của interface member khác class thông thường

Member khai báo trong interface có những quy tắc khác so với class:

~~~java
public interface Printable {
    void print(); // Ngầm định public abstract.

    default String title() {
        return "Printable";
    }

    static String category() {
        return "Document";
    }
}
~~~

Đây là interface minh họa. Method trừu tượng `print()` ngầm định **public abstract**, không phải package-private vì thiếu từ khóa `public`. `default` method cũng là public. Static interface method ở đây là public.

Java 9+ còn cho phép **private method trong interface** làm helper nội bộ. Nhưng **không thể dùng protected method theo cách class thông thường trong interface**. Field khai báo trong interface mặc định là **public static final**; không thể coi một interface field không ghi modifier là package-private.

### Khi implement interface, implementation của public method phải public

~~~java
class ConsolePrintable implements Printable {
    @Override
    public void print() {
        System.out.println("print");
    }
}
~~~

`ConsolePrintable.print()` cần public, không thể hạ mức xuống package-private chỉ vì class `ConsolePrintable` không ghi `public`. Việc override/implement không được giảm quyền truy cập so với hợp đồng inherited method public.

**Phân biệt:** top-level interface có thể package-private khi không ghi modifier, nhưng các **interface members** vẫn tuân theo quy tắc riêng của interface.

## 16. Overriding: không được thu hẹp mức truy cập

Giả sử superclass có protected instance method:

~~~java
public class Base {
    protected String label() {
        return "base";
    }
}
~~~

Một subclass có thể override với `protected` hoặc **mở rộng thành `public`**:

~~~java
public class Child extends Base {
    @Override
    public String label() {
        return "child";
    }
}
~~~

Đây là hai class minh họa, đặt trong hai file tên tương ứng hoặc chuyển thành các nested classes hợp lệ. Nhưng override không thể đổi thành `private` hoặc package-private vì như vậy sẽ **giảm quyền truy cập** của inherited method.

Ví dụ cố ý sai:

~~~java
class Parent {
    public void execute() {}
}

class Child extends Parent {
    // void execute() {} // Lỗi: không thể giảm public xuống package-private.
}
~~~

Nếu subclass thật sự override một method, access level phải được giữ phù hợp với quy tắc Java. Ngoài visibility còn có những yêu cầu khác về return type, checked exceptions và method signature.

### Không phải mọi method cùng tên đều override

- **Private method** của superclass không được override theo cách thông thường; subclass có thể khai báo một method cùng tên/chữ ký như một method độc lập nếu quy tắc khác cho phép.
- **Static method** không được override như instance method; có thể xảy ra *method hiding* theo quy tắc.
- **Package-private method** của superclass ở package khác có thể **không được subclass kế thừa/override** theo cách người mới học kỳ vọng, vì member đó không được truy cập từ package subclass.

Đặc biệt, đừng gắn `@Override` rồi suy ra compiler sẽ công nhận override một method package-private vốn không được kế thừa qua ranh giới package.

## 17. Khác package nhưng có cùng tên lớp: access không dựa vào tên đơn giản

Hai package khác nhau có thể có hai class cùng simple name:

~~~text
app.user.Account
app.admin.Account
~~~

`Account` là simple name, còn tên đầy đủ gồm package. Chúng là **hai kiểu khác nhau**, không tự có quan hệ kế thừa hay quyền package-private chung.

Việc ghi:

~~~java
import app.user.Account;
~~~

trong file thuộc `app.admin` chỉ giúp tham chiếu tới kiểu `app.user.Account` bằng tên `Account` khi không xung đột. Nó **không biến file thành thành viên package `app.user`** và không cấp quyền với các field package-private của `app.user.Account`.

Nếu cần sử dụng hai kiểu trùng simple name trong cùng một file, có thể phải dùng tên đầy đủ cho một hoặc cả hai theo quy tắc import và shadowing. Vấn đề tên không thay đổi access checks.

## 18. Compile-time accessibility và runtime behavior

Access control bình thường được compiler kiểm tra dựa trên **khai báo kiểu, vị trí của mã và member được truy cập**. Việc tạo object runtime có kiểu subclass không tự làm mọi protected/private field “công khai”.

Ví dụ:

~~~java
Vault reference = new ChildVault();
// reference.points; // Không hợp lệ ở App thuộc package khác.
~~~

Ngay cả khi object runtime thực tế là ChildVault, biểu thức truy cập ở `App` không nằm trong ngữ cảnh có quyền đọc protected field `points`. Dynamic dispatch của method override không cấp quyền truy cập field bị chặn.

### Nhưng public method có thể dùng private field bên trong

~~~java
System.out.println(base.callPrivateMethod());
~~~

Lời gọi public method hợp lệ từ client. Bên trong `Vault.callPrivateMethod`, code thuộc class `Vault` có quyền gọi `privateInfo()`. Đây là cách thiết kế đóng gói: **caller sử dụng hành vi public**, còn class tự quản lý state private.

Không phải vì caller “gián tiếp đọc private data” mà compiler mở quyền truy cập trực tiếp tới field; method đang thực hiện một hợp đồng do class chủ động công bố.

## 19. Java modules có thể bổ sung một ranh giới truy cập

Từ Java 9, **Java Platform Module System (JPMS)** có thể giới hạn việc package của module này có thể được sử dụng bởi module khác hay không. Một kiểu top-level `public` nằm trong package **không được export** có thể **không truy cập được từ module khác** qua cơ chế module bình thường.

Ví dụ file `module-info.java`:

~~~java
module learning.core {
    exports learning.api;
}
~~~

Điều này cho phép các module đọc `learning.core` sử dụng public API từ package `learning.api` nếu thỏa những điều kiện module khác. Nó **không export** package `learning.internal` nếu package đó không được liệt kê.

Những điểm cần phân biệt:

- `public` giải quyết **accessibility ở cấp kiểu/member** theo quy tắc Java.
- `exports` liên quan **khả năng truy cập package qua module boundary**.
- Một package được export không làm `private` hoặc package-private members trong đó thành public.
- `opens` phục vụ các cơ chế reflective access có điều kiện, khác với quyền gọi code thông thường bằng cách viết `obj.method()`.
- Khi chạy trên **classpath thông thường** với unnamed module, ví dụ trong bài tập không cần tạo `module-info.java`.

Đây là phần mở rộng để tránh kết luận “public luôn truy cập được ở mọi module” một cách tuyệt đối. Với Java core mới học, hãy nắm chắc **class/package access** trước rồi nghiên cứu JPMS sâu hơn khi dự án sử dụng named modules.

## 20. Reflection không phải lý do bỏ qua encapsulation

Reflection có thể cung cấp cách tìm metadata field/method và trong những điều kiện nhất định, code có thể yêu cầu truy cập sâu hơn bằng API như `setAccessible`. Nhưng khả năng reflective access chịu các điều kiện quyền truy cập, module openness, policy và runtime configuration.

**Không coi reflection là cách sửa bình thường** khi compiler báo private/protected member inaccessible. Thường nên:

1. Kiểm tra API có **public method** phù hợp không.
2. Nếu là logic nội bộ, cân nhắc đặt cộng tác viên trong cùng package với package-private contract.
3. Nếu cần kế thừa, thiết kế `protected` một cách có chủ đích.
4. Nếu client có nhu cầu hợp lệ, tạo public getter/operation với hợp đồng rõ hoặc một facade phù hợp.
5. Nếu đang làm việc với serialization/framework reflection, dùng cấu hình module và access API theo tài liệu của framework thay vì tắt tất cả giới hạn tùy tiện.

Quyền truy cập tốt là một phần của **API design và bảo vệ invariant**, không chỉ là cú pháp để vượt qua compiler.

## 21. Thiết kế getter/setter: public API không bắt buộc là public field

Cách cài đặt thiếu đóng gói:

~~~java
public class Account {
    public long balanceCents;
}
~~~

Caller có thể viết `account.balanceCents = -999;`. Nếu invariant yêu cầu số dư không âm, class khó kiểm soát được thay đổi này.

Một phiên bản rõ hơn:

~~~java
public class Account {
    private long balanceCents;

    public Account(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("invalid deposit");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }
}
~~~

Class minh họa này giữ field private, public API chỉ cho đọc số dư hoặc thực hiện deposit qua validation. Không nhất thiết phải tạo setter công khai cho mọi field. **Visibility nên theo nhu cầu sử dụng**, không phải cứ private field là phải có một public setter cho đầy đủ.

### Quy tắc chọn quyền truy cập

- **`private`:** chi tiết cài đặt và trạng thái cần bảo vệ; mặc định tốt cho field nội bộ.
- **Package-private:** cộng tác viên dùng chung trong package khi không cần public API.
- **`protected`:** điểm mở rộng cho subclass được thiết kế rõ, có tài liệu về contract.
- **`public`:** API có chủ đích cho caller bên ngoài; cần cân nhắc ổn định và tương thích khi thay đổi.

Không dùng protected field như một phương án tiện tay thay cho thiết kế subclass API. Protected member cũng là một cam kết cho những subclass phụ thuộc nó.

## 22. Tương thích khi thay đổi access modifier

Nếu một thư viện đã cung cấp public method:

~~~java
public void save() { /* ... */ }
~~~

và phiên bản mới hạ thành package-private, client ở package khác có thể không biên dịch lại được. Những binary đã biên dịch cũng có thể gặp lỗi truy cập khi liên kết/chạy tùy hoàn cảnh.

Ngược lại, mở một member từ package-private thành public thường làm phạm vi code có thể sử dụng tăng lên, nhưng vẫn cần kiểm tra API design và khả năng tương thích tổng thể. Không nên mở rộng quyền tùy tiện chỉ để sửa một lỗi compile time.

**Đặc biệt với protected và kế thừa:** nếu subclass ở package khác đang override protected method, hạ access của method superclass hoặc thay đổi chữ ký có thể phá code ở subclass. Vì vậy API công khai và điểm mở rộng protected phải được quản lý có chủ đích.

## 23. Đọc lỗi compiler “has private access” và “is not public”

Khi compiler báo một biểu thức không truy cập được, hãy thực hiện các bước sau.

**Bước 1:** Xác định **member đang truy cập** — field, method, constructor hay type.

**Bước 2:** Xác định **class khai báo member** và modifier gốc. Đừng chỉ nhìn kiểu của biến nếu member được kế thừa từ superclass ở package khác.

**Bước 3:** Xác định vị trí mã đang truy cập — cùng class/nest hay khác, cùng package hay khác.

**Bước 4:** Nếu khác package và member là protected, xác định code có nằm trong subclass phù hợp không; với instance member, kiểm tra **kiểu biểu thức receiver**.

**Bước 5:** Kiểm tra class chứa member và mọi enclosing type cần thiết có truy cập được không.

**Bước 6:** Nếu dùng modules, kiểm tra package có được export/read hợp lệ không.

**Bước 7:** Chọn cách sửa đúng ngữ nghĩa — public API, đổi thiết kế package, thay protected receiver hợp lệ, hoặc giữ member private và cung cấp operation cần thiết.

### Những thông báo thường gặp

| Dạng lỗi | Vấn đề thường gặp |
| --- | --- |
| `has private access in ...` | Member private, code không thuộc ngữ cảnh được phép |
| `is not public in ...; cannot be accessed from outside package` | Top-level type hoặc member package-private không được truy cập từ package khác |
| `has protected access in ...` | Ngoài package hoặc receiver của subclass không đáp ứng điều kiện protected |
| `cannot be accessed from outside package` | Có thể liên quan member, kiểu hoặc package/module boundary |
| `attempting to assign weaker access privileges` | Override method nhưng hạ mức truy cập |
| `constructor ... cannot be applied to given types` | Chữ ký constructor không phù hợp; có thể đồng thời có vấn đề quyền truy cập |
| `constructor ... has private access` | Caller không được gọi constructor riêng tư |

Thông báo có thể khác giữa phiên bản compiler và cách viết mã. Hãy đọc **chữ ký member, class khai báo và vị trí source** thay vì dựa vào một chuỗi lỗi duy nhất.

## 24. Bài tập 1 — Dự đoán truy cập trong cùng package

Cho:

~~~java
package practice;

public class Alpha {
    private int a = 1;
    int b = 2;
    protected int c = 3;
    public int d = 4;
}
~~~

Một class `Beta` khác nằm trong package `practice` nhưng không kế thừa Alpha:

~~~java
package practice;

class Beta {
    int read(Alpha value) {
        // Những field nào được dùng ở đây?
        return value.b + value.c + value.d;
    }
}
~~~

**Đáp án:** `b` (package-private), `c` (protected) và `d` (public) đều đọc được; `a` không, vì private. Không cần `Beta extends Alpha` cho các quyền cùng package.

## 25. Bài tập 2 — Khác package, không phải subclass

Giả sử `Alpha` ở `practice`, còn `Gamma` ở `client`:

~~~java
package client;

import practice.Alpha;

class Gamma {
    int read(Alpha value) {
        return value.d;
    }
}
~~~

**Đáp án:** `value.d` hợp lệ vì `d` public và `Alpha` public. `value.a`, `value.b` và `value.c` không được phép trong class này. `import practice.Alpha` không mở quyền cho các member còn lại.

## 26. Bài tập 3 — Protected receiver ở khác package

Giả sử `Alpha` ở `practice`, subclass:

~~~java
package child;

import practice.Alpha;

class Delta extends Alpha {
    int readSelf() {
        return this.c;
    }

    int readPeer(Delta other) {
        return other.c;
    }

    int readBase(Alpha other) {
        // return other.c; // Lỗi.
        return this.c;
    }
}
~~~

**Đáp án:** `this.c` và `other.c` khi `other` kiểu `Delta` hợp lệ. `other.c` khi `other` kiểu `Alpha` không hợp lệ trong ngữ cảnh `Delta` khác package. Ép kiểu sang Delta có thể khiến biểu thức compile nếu runtime thực là Delta, nhưng có rủi ro `ClassCastException` và thường không phải cách thiết kế tốt.

## 27. Bài tập 4 — Top-level type và member access

Cho:

~~~java
package library.internal;

class Converter {
    public String format() {
        return "text";
    }
}
~~~

Tại sao class ở `library.app` không thể trực tiếp viết `new Converter().format()`? **Vì `Converter` là top-level class package-private**. Việc `format()` là public không làm bản thân `Converter` trở thành public.

Hãy đề xuất một public facade ở package thích hợp, hoặc đổi converter thành public nếu đúng là API bên ngoài cần dùng.

## 28. Bài tập 5 — Constructor từ package khác

Một superclass có constructor:

~~~java
package library.base;

public class Parent {
    protected Parent(int value) {}
}
~~~

Subclass ở package `library.child`:

~~~java
package library.child;

import library.base.Parent;

public class Child extends Parent {
    public Child() {
        super(1);
    }
}
~~~

**Đáp án:** `super(1)` hợp lệ từ subclass constructor trong trường hợp này. Nhưng client thông thường ở package khác không tự được `new Parent(1)` vì constructor protected không phải public constructor.

Đừng nhầm constructor của superclass với method được thừa kế: constructor không được inherit như một method.

## 29. Bài tập 6 — Hạ access khi override

Cho:

~~~java
class Base {
    protected void calculate() {}
}

class Child extends Base {
    @Override
    // void calculate() {} // Lỗi nếu bỏ comment: giảm protected về package-private.
    protected void calculate() {}
}
~~~

**Đáp án:** Override với protected hợp lệ; override với public cũng hợp lệ. Override giảm xuống package-private/private bị lỗi. Để code chạy được, trong đoạn đã cho chỉ có một triển khai `protected void calculate(){}` không bị chú thích.

## 30. Checklist ôn tập

- [ ] Tôi phân biệt đúng class, package và package con.
- [ ] Tôi biết package con **không** tự là cùng package với package cha.
- [ ] Tôi thuộc bảng quyền private/package-private/protected/public trong class và giữa package.
- [ ] Tôi hiểu package-private nghĩa là **không ghi modifier**, không viết từ khóa `default`.
- [ ] Tôi biết một class khác cùng package có thể truy cập protected member **dù không kế thừa**.
- [ ] Tôi biết một class khác cùng package **không tự** đọc được private member.
- [ ] Tôi hiểu protected ở package khác chỉ mở trong ngữ cảnh subclass hợp lệ.
- [ ] Tôi hiểu khi truy cập protected instance member ở khác package, kiểu receiver có thể làm biểu thức hợp lệ hoặc lỗi.
- [ ] Tôi biết `Base other` và `Derived other` có thể cho quyền truy cập protected khác nhau từ code subclass.
- [ ] Tôi biết `import` và `import static` không cấp thêm quyền.
- [ ] Tôi biết top-level class chỉ có thể public hoặc package-private.
- [ ] Tôi biết quyền của class bao ngoài cũng ảnh hưởng việc dùng member công khai.
- [ ] Tôi biết constructor có access modifier riêng và không được kế thừa.
- [ ] Tôi phân biệt static member và instance member trong kiểm soát truy cập.
- [ ] Tôi biết nested class/nestmate có quy tắc private access riêng.
- [ ] Tôi biết interface method thiếu modifier không phải package-private như class method.
- [ ] Tôi biết override không được giảm khả năng truy cập của method.
- [ ] Tôi hiểu Java modules có thể giới hạn exported package ngoài mức public.
- [ ] Tôi không coi reflection là cách mặc định để vượt compiler access error.
- [ ] Tôi có thể biên dịch dự án năm file nhiều package và giải thích chính xác stdout.
- [ ] Tôi biết chọn modifier dựa trên **hợp đồng API và encapsulation**, không chỉ để code biên dịch.

**Kết luận:** Khi muốn biết một member có được sử dụng hay không, hãy lần lượt hỏi **(1) member được khai báo trong class nào, với modifier nào; (2) mã đang dùng nằm trong class/nest và package nào; (3) nếu protected ở khác package thì có phải subclass và receiver hợp lệ không; (4) kiểu chứa member và module có cho truy cập không?** Cùng class, cùng package và khác package là các ngữ cảnh khác nhau; hiểu ranh giới ấy giúp bạn viết API Java an toàn, tránh lộ chi tiết cài đặt và sửa đúng các lỗi truy cập.
