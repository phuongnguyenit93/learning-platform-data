# Quyền truy cập của lớp cấp cao nhất và lớp thành viên trong Java

## 1. Vì sao phải phân biệt top-level class và member class?

Trong Java, từ khóa `public`, `protected`, `private` và trường hợp **không ghi access modifier** ảnh hưởng đến nơi mã nguồn được phép **nhắc tên một kiểu, gọi constructor và truy cập thành viên**. Tuy nhiên, không phải mọi vị trí khai báo kiểu đều dùng được cả bốn mức truy cập.

Hai trường hợp cần phân biệt:

- **Lớp cấp cao nhất** (*top-level class*): lớp được khai báo trực tiếp ở cấp đơn vị biên dịch, không nằm trong thân một lớp hoặc interface khác.
- **Lớp thành viên** (*member class*): lớp được khai báo trực tiếp trong thân một lớp khác, chẳng hạn `Outer.Inner` hoặc `Outer.Nested`. Nó có thể là **non-static inner class** hoặc **static nested class**.

**Quy tắc quan trọng nhất:**

> **Top-level class chỉ được dùng `public` hoặc package-private (không ghi modifier truy cập). Member class khai báo trong class có thể dùng `public`, `protected`, package-private hoặc `private`.**

Do đó, `protected class Account { }` và `private class Account { }` là **sai nếu `Account` được khai báo cấp cao nhất**; nhưng `protected class Helper { }` hoặc `private class Helper { }` có thể hợp lệ khi `Helper` là **member class** trong một lớp thích hợp.

### Hình dung cấu trúc khai báo

```text
Tệp Outer.java
┌─────────────────────────────────────────────────────────┐
│ package sample;                                         │
│                                                         │
│ public class Outer {         ← top-level class          │
│     public class A { }       ← public member class      │
│     protected class B { }    ← protected member class   │
│     class C { }              ← package-private member   │
│     private class D { }      ← private member class     │
│                                                         │
│     public static class E { } ← static member class     │
│ }                                                       │
│                                                         │
│ class PackageHelper { }      ← package-private top-level│
└─────────────────────────────────────────────────────────┘
```

Đây là **một mảnh mã Java hợp lệ**. `Outer` và `PackageHelper` đều là top-level classes, dù nằm cùng tệp; các lớp `A`, `B`, `C`, `D`, `E` mới là member classes của `Outer`.

**Từ “thành viên” không đồng nghĩa “static”.** Một `static nested class` là member class, nhưng một `inner member class` không static cũng là member class. Modifier truy cập của kiểu và modifier `static` phục vụ **hai mục đích khác nhau**.

## 2. Bảng đối chiếu bốn mức truy cập theo vị trí khai báo

| Modifier khai báo | Top-level class | Member class trong một class | Ý nghĩa khái quát |
| --- | --- | --- | --- |
| `public` | **Hợp lệ** | **Hợp lệ** | Có thể được truy cập từ nơi khác theo điều kiện nhìn thấy enclosing type và module/package |
| `protected` | **Không hợp lệ** | **Hợp lệ** | Truy cập trong cùng package và một số ngữ cảnh subclass ở package khác |
| Không ghi modifier | **Hợp lệ** | **Hợp lệ** | **Package-private**: truy cập từ trong cùng package |
| `private` | **Không hợp lệ** | **Hợp lệ** | Giới hạn trong ngữ cảnh enclosing top-level type / nest phù hợp |
| `static` | **Không hợp lệ cho top-level class** | Có thể dùng cho static nested class | Không tạo quan hệ enclosing instance ngầm |
| `final` | Có thể dùng | Có thể dùng | Không cho lớp bị kế thừa; **không phải access modifier** |
| `abstract` | Có thể dùng | Có thể dùng | Không thể khởi tạo trực tiếp; **không phải access modifier** |

Với **member interface, member enum, member record** còn có quy tắc riêng về trạng thái `static`; trong phạm vi bài này, hãy tập trung vào **member classes** khai báo bên trong một class.

Cần tách ba câu hỏi:

1. **Tên kiểu có truy cập được không?** Ví dụ từ package khác có được viết `Outer.PublicNested` không?
2. **Constructor có truy cập được không?** Có quyền nhắc tên kiểu **chưa chắc** có quyền viết `new` với constructor của nó.
3. **Member bên trong kiểu có truy cập được không?** Kiểu `public` **không tự làm mọi field và method của nó thành `public`**.

## 3. Lớp cấp cao nhất (*top-level class*) là gì?

Lớp cấp cao nhất được khai báo trực tiếp trong compilation unit, nằm ngoài thân mọi lớp hoặc interface khác:

```java
package school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

Nếu lưu lớp công khai này trong **`Student.java`**, code thuộc package `school`. Modifier `public` nói rằng tên kiểu `school.Student` có thể được truy cập từ những ngữ cảnh bên ngoài package theo các điều kiện của Java.

Một top-level class khác có thể **không ghi modifier truy cập**:

```java
package school;

class StudentValidator {
    static boolean valid(String name) {
        return name != null && !name.isBlank();
    }
}
```

`StudentValidator` là **package-private top-level class**: những type ở package `school` có thể dùng nó, nhưng code ở package `app` không được nhắc tên `school.StudentValidator` theo cách thông thường.

### Không phải mọi modifier đều là access modifier

`final class Utility { }` là một top-level class **package-private và final**; `final` ảnh hưởng khả năng kế thừa, **không** khiến tên lớp thành public.

`public abstract class Shape { }` là top-level class **public và abstract**; `abstract` ảnh hưởng khả năng khởi tạo instance, **không** biến quyền truy cập thành protected.

**Điều cần nhớ:** khi xem mức truy cập top-level class, chỉ hai lựa chọn là `public` hoặc **không ghi access modifier**.

## 4. Tại sao top-level class không được `private` hoặc `protected`?

Hai khai báo sau **cố ý sai và không được biên dịch** khi đặt ở cấp tệp:

```java
// private class Secret {
// }
//
// protected class ProtectedSecret {
// }
```

`private` trong Java mô tả mức truy cập gắn với ngữ cảnh bao chứa có thể giới hạn từ bên ngoài; còn top-level class không có **lớp bao ngoài** để áp dụng modifier ấy như một member class. `protected` phục vụ quy tắc truy cập member trong quan hệ package và kế thừa, không phải lựa chọn khai báo top-level class.

Nếu muốn ẩn một lớp ở cấp package, thường dùng:

```java
class InternalCodec {
}
```

Nếu muốn ẩn một lớp bên trong một API class, dùng **private member class**:

```java
public class CodecService {
    private static class InternalCodec {
    }
}
```

Đây là **hai phương án thiết kế khác nhau**:

- `InternalCodec` top-level package-private vẫn có thể được **mọi class cùng package** truy cập.
- `CodecService.InternalCodec` private member type không trở thành một type công khai chỉ vì `CodecService` public.

Ngoài quyền truy cập trong Java, việc phân phối thư viện còn phụ thuộc package/module boundary; **package-private không phải cơ chế bảo mật chống mọi dạng reflection hoặc truy cập phi chuẩn**, mà là quy tắc kiểm tra truy cập của ngôn ngữ.

## 5. Top-level `public`: tên lớp thấy được không đồng nghĩa mọi thứ đều public

Xét tệp `src/catalog/Item.java`:

```java
package catalog;

public class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    private String secret() {
        return "hidden";
    }
}
```

Một lớp khác ở package `client` có thể **nhắc tên kiểu** `catalog.Item` nếu package/module thích hợp cho phép. Nhưng nó **không thể** gọi `new Item("A")` vì constructor `Item(String)` là **package-private**. Nó cũng không thể gọi `item.secret()` vì method ấy private.

Lớp `public` **không làm constructor và field/method thành public một cách tự động**. Nếu muốn khách hàng của API tự tạo Item ở package khác, cần constructor hoặc factory accessible:

```java
package catalog;

public class Item {
    private final String code;

    public Item(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Hai đoạn `Item` trên là **hai phiên bản thay thế**, không đặt đồng thời trong một source set. Ở bản thứ hai, `new Item("A")` hợp lệ từ package khác nếu class/package/module accessible.

### Constructor mặc định cũng có modifier truy cập

Nếu top-level `public class A { }` không khai báo constructor nào, Java ngầm khai báo **default constructor** có access level phù hợp với class, là `public` trong ví dụ này.

Ngược lại:

```java
public class A {
    A() {
    }
}
```

Dòng `A() { }` là **constructor do người viết khai báo**, package-private vì không ghi `public`. Từ package khác, có thể thấy tên `A` nhưng **không gọi được `new A()`**.

Vì vậy đừng mặc định rằng constructor không tham số nào cũng public.

## 6. Package-private top-level class: quyền cùng package

Khái niệm **package-private** không có từ khóa `package-private` riêng. Nó xuất hiện khi **không ghi modifier truy cập** cho kiểu hoặc member trong ngữ cảnh phù hợp.

Ví dụ:

```java
package store.core;

class LocalParser {
    static String parse(String input) {
        return input.trim();
    }
}
```

Trong cùng package `store.core`, lớp khác được phép tham chiếu `LocalParser`. Nhưng ở package `store.app`, dù mã nằm trong **cùng dự án**, cũng **không được** trực tiếp dùng `LocalParser` vì hai package khác nhau.

### Package con không được tính là cùng package

- `store.core` là **một package**.
- `store.core.tools` là **package khác**.
- `store.app` là **package khác**.

Việc các tên package có tiền tố giống nhau **không làm quyền package-private được kế thừa sang subpackage**.

Đặt hai tệp trong cùng thư mục vật lý nhưng khai báo package khác nhau cũng không tự cấp quyền truy cập. Quy tắc dựa vào **package declaration và ngữ cảnh biên dịch**, không dựa trên “các file ở gần nhau”.

## 7. Ví dụ đa package: top-level public và package-private

Tạo cấu trúc tệp:

```text
project/
└── src/
    └── sample/
        ├── core/
        │   ├── PublicGate.java
        │   └── InternalClient.java
        └── app/
            └── ExternalClient.java
```

**Tệp `src/sample/core/PublicGate.java`:**

```java
package sample.core;

public class PublicGate {
    public static String greet() {
        return "public gate";
    }
}

class PackageHelper {
    static String message() {
        return "package helper";
    }
}
```

`PublicGate` là top-level public class. `PackageHelper` cũng là top-level class nhưng **package-private**. Cả hai cùng nằm trong một compilation unit; chỉ `PublicGate` là public top-level class của tệp.

**Tệp `src/sample/core/InternalClient.java`:**

```java
package sample.core;

public class InternalClient {
    public static void main(String[] args) {
        System.out.println(PublicGate.greet());
        System.out.println(PackageHelper.message());
    }
}
```

Vì `InternalClient` ở **cùng package `sample.core`**, nó có thể nhắc tên `PackageHelper`.

**Tệp `src/sample/app/ExternalClient.java`:**

```java
package sample.app;

import sample.core.PublicGate;
// import sample.core.PackageHelper; // Lỗi nếu bỏ comment: class không public.

public class ExternalClient {
    public static void main(String[] args) {
        System.out.println(PublicGate.greet());

        // System.out.println(PackageHelper.message());
        // Không truy cập được PackageHelper từ package khác.
    }
}
```

Biên dịch cả ba tệp từ thư mục `project`:

```bash
javac -encoding UTF-8 -d out src/sample/core/PublicGate.java src/sample/core/InternalClient.java src/sample/app/ExternalClient.java
java -cp out sample.core.InternalClient
java -cp out sample.app.ExternalClient
```

Kết quả của lần chạy `InternalClient`:

```text
public gate
package helper
```

Kết quả của lần chạy `ExternalClient`:

```text
public gate
```

Lệnh `javac -d out` ghi class files theo package path. Mỗi `java -cp out ...` chạy một main class độc lập. Dòng lỗi đã comment trong `ExternalClient` nhằm cho thấy giới hạn package-private, không phải mã cần bỏ comment để chạy ví dụ.

## 8. Quy tắc tên tệp đối với top-level `public class`

Trong cấu trúc dự án Java điển hình, một compilation unit được đặt tên theo top-level public class của nó:

```java
public class Report {
}
```

Lưu trong **`Report.java`**. Nếu tệp tên `Other.java` nhưng khai báo `public class Report`, `javac` thông thường báo rằng public class `Report` phải được khai báo trong `Report.java`.

Có thể có thêm các **top-level package-private classes** trong cùng source file:

```java
public class Report {
}

class ReportFormatter {
}
```

Đây là nội dung hợp lệ cho `Report.java`. `ReportFormatter` không phải member class của `Report` vì nó được khai báo **ngoài dấu ngoặc nhọn của `Report`**.

Không nên nhầm “trong cùng file” với “trong cùng class”. Cấu trúc dấu `{ ... }` mới quyết định một kiểu là top-level hay member.

## 9. Member class: bốn mức truy cập trong một lớp bao ngoài

Xét:

```java
public class Library {
    public static class PublicShelf {
    }

    protected static class ProtectedShelf {
    }

    static class PackageShelf {
    }

    private static class PrivateShelf {
    }
}
```

Tất cả `PublicShelf`, `ProtectedShelf`, `PackageShelf` và `PrivateShelf` là **member classes** của `Library`.

- `PublicShelf` có mức truy cập **public**, khi tên `Library` cũng truy cập được và các điều kiện khác cho phép.
- `ProtectedShelf` có mức truy cập **protected**, cho code cùng package và các subclass trong package khác theo quy tắc protected.
- `PackageShelf` không ghi access modifier, nên **package-private**.
- `PrivateShelf` có mức truy cập **private**, không phải một kiểu mà lớp ngoài unrelated có thể tự ý đặt tên.

Modifier `static` ở cả bốn khai báo chỉ có nghĩa đây là **static nested classes**, không phụ thuộc một `Library` instance bao ngoài khi tạo đối tượng. Nếu bỏ `static` ở một member class được phép, class ấy sẽ là **non-static inner member class**, nhưng **mức truy cập vẫn theo modifier đã khai báo**.

## 10. Ví dụ đầy đủ: cả bốn access modifiers trên member classes

Ta dùng một ví dụ đa tệp để quan sát cùng package, package khác và subclass.

```text
project/
└── src/
    └── demo/
        ├── api/
        │   ├── Outer.java
        │   └── PackageFriend.java
        └── client/
            ├── Outside.java
            └── OuterChild.java
```

**Tệp `src/demo/api/Outer.java`:**

```java
package demo.api;

public class Outer {
    public static class PublicMember {
        public PublicMember() {
        }

        public String name() {
            return "public member";
        }
    }

    protected static class ProtectedMember {
        public ProtectedMember() {
        }

        public String name() {
            return "protected member";
        }
    }

    static class PackageMember {
        PackageMember() {
        }

        String name() {
            return "package member";
        }
    }

    private static class PrivateMember {
        private String name() {
            return "private member";
        }
    }

    public class InnerMember {
        public InnerMember() {
        }

        public String name() {
            return "inner member";
        }
    }

    public String describePrivate() {
        return new PrivateMember().name();
    }
}
```

Trong file này:

- Bốn static nested classes có bốn access levels khác nhau.
- `InnerMember` là **public non-static member class**, cần enclosing `Outer` instance khi tạo từ ngoài.
- `Outer.describePrivate()` được phép dùng `PrivateMember` và method `name()` private vì code nằm trong phạm vi enclosing type thích hợp.

**Tệp `src/demo/api/PackageFriend.java`:**

```java
package demo.api;

public class PackageFriend {
    public static void main(String[] args) {
        System.out.println(new Outer.PublicMember().name());
        System.out.println(new Outer.ProtectedMember().name());
        System.out.println(new Outer.PackageMember().name());

        Outer outer = new Outer();
        System.out.println(outer.describePrivate());

        Outer.InnerMember inner = outer.new InnerMember();
        System.out.println(inner.name());
    }
}
```

`PackageFriend` nằm **cùng package `demo.api`** với `Outer`, nên truy cập được public, protected và package-private member classes. Tuy nhiên, nó **không đặt tên trực tiếp `Outer.PrivateMember`** vì class ấy private; nó gọi public method `describePrivate()` của `Outer` để nhận kết quả.

**Tệp `src/demo/client/Outside.java`:**

```java
package demo.client;

import demo.api.Outer;

public class Outside {
    public static void main(String[] args) {
        Outer.PublicMember shelf = new Outer.PublicMember();
        System.out.println(shelf.name());

        Outer outer = new Outer();
        Outer.InnerMember inner = outer.new InnerMember();
        System.out.println(inner.name());

        // new Outer.ProtectedMember(); // Không hợp lệ ở đây.
        // new Outer.PackageMember();   // Không hợp lệ ở đây.
        // new Outer.PrivateMember();   // Không hợp lệ ở đây.
    }
}
```

`Outside` ở package khác, **không phải subclass** của `Outer`, nên trong các nested types ví dụ nó chỉ dùng được những **public member classes** có constructor và member thích hợp.

**Tệp `src/demo/client/OuterChild.java`:**

```java
package demo.client;

import demo.api.Outer;

public class OuterChild extends Outer {
    public static void main(String[] args) {
        ProtectedMember item = new ProtectedMember();
        System.out.println(item.name());
    }
}
```

`OuterChild` là **subclass** của `Outer` ở package khác. Tại ngữ cảnh subclass phù hợp, nó có thể truy cập **protected member type** được kế thừa theo tên `ProtectedMember`. Constructor của `ProtectedMember` được khai báo **`public` tường minh** để tránh trộn lỗi truy cập tên lớp với lỗi truy cập constructor.

Biên dịch:

```bash
javac -encoding UTF-8 -d out src/demo/api/Outer.java src/demo/api/PackageFriend.java src/demo/client/Outside.java src/demo/client/OuterChild.java
```

Chạy các chương trình:

```bash
java -cp out demo.api.PackageFriend
java -cp out demo.client.Outside
java -cp out demo.client.OuterChild
```

Kết quả của `PackageFriend`:

```text
public member
protected member
package member
private member
inner member
```

Kết quả của `Outside`:

```text
public member
inner member
```

Kết quả của `OuterChild`:

```text
protected member
```

**Ý nghĩa cần rút ra:** protected member class có quyền truy cập **khác** public member class và package-private member class. Không thể nói đơn giản “protected là public nhưng nhỏ hơn” hay “protected nghĩa chỉ subclass dùng được”; **code cùng package cũng truy cập được protected member**, còn quyền ở package khác có các điều kiện kế thừa cụ thể.

## 11. `protected` ở package khác: chú ý ngữ cảnh subclass

`protected` là phần dễ nhầm nhất của Java access control.

Một **protected member** nói chung:

1. Có thể được truy cập từ code thích hợp ở **cùng package** với class khai báo nó.
2. Ở **package khác**, việc truy cập gắn với **ngữ cảnh subclass** theo quy tắc JLS; không phải mọi code có một biến tham chiếu superclass đều tự được truy cập protected member.
3. Với **protected instance fields/methods**, các biểu thức receiver ở package khác còn chịu hạn chế kiểu receiver đặc thù. Quy tắc này **không thể rút gọn** thành “hễ đang ở subclass thì gọi qua bất kỳ object superclass nào cũng được”.
4. Với **protected member class**, ngoài quyền truy cập **tên kiểu** còn phải kiểm tra riêng **constructor** và các members bên trong kiểu.

### Ví dụ protected instance member để phân biệt

Tệp `Base.java`:

```java
package access.base;

public class Base {
    protected int number = 7;
}
```

Tệp `Child.java` ở package khác:

```java
package access.child;

import access.base.Base;

public class Child extends Base {
    public int valid() {
        return this.number;
    }

    public int invalid(Base other) {
        // return other.number; // Không hợp lệ từ package khác.
        return this.number;
    }
}
```

Đây là **hai file lớp biên dịch được** vì dòng truy cập sai đã được comment. `Child` được quyền đọc `this.number` của phần superclass trên chính subclass object phù hợp. Nhưng `other.number` với receiver có kiểu tĩnh `Base` không tự hợp lệ chỉ vì method nằm trong `Child`; protected access ngoài package có quy tắc receiver riêng.

Ví dụ này nói về **protected field**, dùng để giúp hiểu quan hệ subclass. Khi đọc `protected class Member` trong ví dụ `OuterChild`, hãy vẫn xét đúng quy tắc truy cập **member type** và constructor riêng của nó; đừng áp mọi chi tiết receiver của instance field sang truy cập một static nested type.

### Vì sao `protected static class Nested` không nhất thiết cho mọi nơi tạo object?

Với:

```java
public class Host {
    protected static class Nested {
        protected Nested() {
        }
    }
}
```

Một subclass của `Host` ở package khác có thể truy cập tên protected member type trong ngữ cảnh phù hợp, nhưng `new Nested()` còn chịu **quy tắc access tới constructor protected** của `Nested`, vốn là **một constructor riêng**. Nếu subclass của `Host` không phải subclass của `Nested`, việc gọi constructor protected của Nested ở package khác có thể bị từ chối. Đây là lý do ví dụ đầy đủ ở mục 10 sử dụng **`public ProtectedMember()`**.

**Quy trình chẩn đoán:** kiểm tra “truy cập được class?” trước, sau đó kiểm tra “truy cập được constructor?”; không suy hai câu trả lời là một.

## 12. `private member class`: ẩn chi tiết bên trong kiểu bao ngoài

Một **private member class** thường dùng để che giấu implementation, helper, state machine hoặc đối tượng chỉ phục vụ class bao ngoài.

Tạo tệp **`PrivateNestedDemo.java`**:

```java
public class PrivateNestedDemo {
    private final String prefix;

    public PrivateNestedDemo(String prefix) {
        this.prefix = prefix;
    }

    private static class Token {
        private final String text;

        private Token(String text) {
            this.text = text;
        }
    }

    private class Renderer {
        private String render(Token token) {
            return prefix + ":" + token.text;
        }
    }

    public String render(String text) {
        Token token = new Token(text);
        Renderer renderer = new Renderer();
        return renderer.render(token);
    }

    public static void main(String[] args) {
        PrivateNestedDemo demo = new PrivateNestedDemo("item");
        System.out.println(demo.render("42"));

        // Token token = new Token("x"); // Trong main của enclosing class
        // việc truy cập này có thể hợp lệ, vì vẫn thuộc enclosing type.
    }
}
```

```bash
javac PrivateNestedDemo.java
java PrivateNestedDemo
```

```text
item:42
```

Trong cùng enclosing top-level class `PrivateNestedDemo`:

- `render` tạo được `Token` và `Renderer`, dù các member classes ấy là private.
- `Renderer` là non-static inner class, có enclosing `PrivateNestedDemo` instance nên dùng được field `prefix`.
- `Token` là static nested class, **không** có enclosing instance ngầm; nó chỉ giữ dữ liệu `text` được truyền vào.
- Private member `Token.text` vẫn được truy cập hợp lệ từ `Renderer` trong cùng **nest** phù hợp.

**Quan trọng:** `private` không có nghĩa “chỉ chính dòng bên trong lớp private mới được nhắc tên nó”. Enclosing class và các nestmates trong quan hệ được ngôn ngữ cho phép có thể truy cập private members lẫn nhau. Ở Java hiện đại, JVM có cơ chế *nestmates* phục vụ những quan hệ truy cập này; đối với người học Java source, chỉ cần nhớ quy tắc lexical/enclosing thích hợp.

Bên ngoài phạm vi được phép, một lớp unrelated không thể viết `new PrivateNestedDemo.Token("x")` do `Token` private, kể cả vì `PrivateNestedDemo` là public.

## 13. Static member class khác non-static inner member class

Hãy tách **access modifier** khỏi **static**:

| Đặc điểm | `public static class Nested` | `public class Inner` |
| --- | --- | --- |
| Có phải member class? | Có | Có |
| Quyền truy cập tên kiểu | Theo `public`, enclosing type, module | Theo `public`, enclosing type, module |
| Có enclosing outer instance ngầm? | Không | Có |
| Tạo từ code ngoài | `new Outer.Nested()` khi constructor accessible | `outer.new Inner()` khi constructor accessible |
| `this` trong instance method | Chỉ Nested instance | Chỉ Inner instance |
| `Outer.this` | Không có outer instance ngầm | Có thể dùng trong ngữ cảnh inner phù hợp |
| Truy cập private outer state | Qua tham chiếu Outer cụ thể hoặc static member phù hợp | Có thể dùng enclosing instance |
| Mục đích điển hình | Helper type gắn tên API, không gắn outer object | Type gắn mỗi instance outer |

### Ví dụ chạy: cùng public nhưng cách khởi tạo khác

Tệp **`NestedVsInnerDemo.java`**:

```java
public class NestedVsInnerDemo {
    private final String title;

    public NestedVsInnerDemo(String title) {
        this.title = title;
    }

    public static class Id {
        private final int value;

        public Id(int value) {
            this.value = value;
        }

        public String display() {
            return "ID=" + value;
        }
    }

    public class Description {
        private final String detail;

        public Description(String detail) {
            this.detail = detail;
        }

        public String display() {
            return NestedVsInnerDemo.this.title + "/" + detail;
        }
    }

    public static void main(String[] args) {
        Id id = new NestedVsInnerDemo.Id(3);

        NestedVsInnerDemo outer = new NestedVsInnerDemo("Java");
        NestedVsInnerDemo.Description description =
                outer.new Description("access");

        System.out.println(id.display());
        System.out.println(description.display());
    }
}
```

```bash
javac NestedVsInnerDemo.java
java NestedVsInnerDemo
```

```text
ID=3
Java/access
```

`Id` và `Description` cùng **public**, nhưng chỉ `Description` là inner class cần một `NestedVsInnerDemo` instance. Do đó cú pháp `new NestedVsInnerDemo.Description(...)` từ một static method không tự hợp lệ nếu thiếu enclosing instance.

Ngược lại, việc `Id` là static nested **không** làm `Id.display()` thành static method: mỗi `Id` instance vẫn có giá trị `value` của nó và có thể dùng `this` trong instance method.

## 14. Outer class package-private: public nested type chưa chắc dùng được ngoài package

Xét:

```java
package internal;

class HiddenOuter {
    public static class VisibleInside {
        public String value() {
            return "visible name inside hidden outer";
        }
    }
}
```

`VisibleInside` được khai báo **public**, nhưng `HiddenOuter` là **top-level package-private class**. Từ package khác, code không thể nhắc tên `internal.HiddenOuter` bằng truy cập Java thông thường, do đó cũng **không thể trực tiếp đặt tên `internal.HiddenOuter.VisibleInside`**.

Nói cách khác:

> Muốn viết `Outer.Member` từ một chỗ bên ngoài, phải thỏa các điều kiện truy cập của **cả `Outer` lẫn `Member`**, và các yếu tố như constructor/module/package liên quan.

Modifier của member không “đi xuyên qua” một lớp bao ngoài inaccessible để tự trở thành API public qua tên đủ điều kiện ấy.

### Nested nhiều tầng

```java
public class PublicOuter {
    private static class PrivateMiddle {
        public static class PublicLeaf {
        }
    }
}
```

`PublicLeaf` có thể là public **so với khai báo bên trong `PrivateMiddle`**, nhưng code unrelated bên ngoài không thể dùng `PublicOuter.PrivateMiddle.PublicLeaf` khi `PrivateMiddle` là private. Tên của từng bước trong chuỗi qualification đều phải accessible.

**Lưu ý nâng cao:** Vẫn có thể cung cấp object theo một **supertype public** hoặc thông qua một public API khác mà không để client nhắc tên runtime implementation private. Điều đó không biến implementation type thành accessible class.

## 15. Member class public nhưng constructor package-private: lỗi thường gặp

Ví dụ:

```java
package library;

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

Từ package `app`, caller có thể **viết kiểu `Catalog.Entry`** vì `Catalog` và `Entry` đều public, nhưng:

```java
// Catalog.Entry entry = new Catalog.Entry();
// Lỗi nếu đang ở package khác: Entry() không public.
```

Constructor `Entry()` được **người lập trình khai báo** nhưng không ghi `public`, nên package-private. Cách sửa (nếu API có chủ đích cho caller tạo object):

```java
public static class Entry {
    public Entry() {
    }
}
```

Đây là **phiên bản thay thế** của inner declaration, không đặt trùng vào cùng class.

Nếu **không tự khai báo constructor nào** cho public member class, default constructor có mức truy cập theo quy tắc tương ứng. Tuy nhiên, khi library API cần bảo đảm quyền gọi constructor rõ ràng, viết constructor public tường minh giúp người đọc nhìn thấy hợp đồng.

### Quyền truy cập của method còn là bước riêng

```java
public static class Entry {
    public Entry() {
    }

    String internalName() {
        return "hidden to other package";
    }

    public String name() {
        return "public name";
    }
}
```

Bên ngoài package, người gọi có thể tạo `Entry` và gọi `name()` nhưng không gọi được `internalName()` (vì method package-private). Quyền của type, constructor và method phải được xem **từng cấp**.

## 16. Kế thừa public/protected nested type không đồng nghĩa kế thừa enclosing instance

Nếu `Child extends Outer`, các member types có thể tham gia thừa hưởng/phân giải tên theo quy tắc Java, nhưng điều đó **không biến object `Child` thành object `Outer.Nested`**.

Ví dụ:

```java
class Outer {
    protected static class Helper {
        static String name() {
            return "helper";
        }
    }
}

class Child extends Outer {
    String call() {
        return Helper.name();
    }
}
```

Hai lớp cùng package, là **khai báo hợp lệ**. `Helper` là static nested class của `Outer`; `Child` có thể truy cập tên member type theo quan hệ kế thừa và quyền protected thích hợp. Nhưng `Helper` không phải superclass của `Child`; vì thế:

- `new Child()` **không** tự tạo instance `Helper`.
- `Helper` có thể được instantiate riêng nếu có constructor accessible và cần thiết.
- `Child` không có quan hệ “is-a Helper”.
- `Helper` là **member type**, không phải instance field hoặc object tự động nằm trong mỗi `Outer`.

Đối với **non-static inner class**, câu chuyện về enclosing instance là riêng: mỗi inner instance gắn với một outer instance thích hợp; quyền truy cập public/protected/private không tự thay đổi sự gắn kết đó.

## 17. Lớp thành viên trong interface có quy tắc khác

Một kiểu member được khai báo trong **interface** có các quy tắc modifier riêng; không nên áp nguyên bảng member class của class bao ngoài cho interface.

Ví dụ:

```java
interface Api {
    class Result {
        public String status() {
            return "ok";
        }
    }
}
```

`Api.Result` là **member class của interface**, mang đặc điểm **public static** theo quy tắc ngôn ngữ. Nó **không** cần một enclosing `Api` instance để được tạo (và interface thường không tự có instance để cung cấp như outer class).

Một class trong interface không thể tùy tiện khai báo `private` hoặc `protected` như member class trong thân một class. Quy tắc về nested types của interface phục vụ API contract và khác với inner member classes thường.

Để tránh nhầm, trong bài tập hãy kiểm tra nơi khai báo có thực sự là:

1. **Top-level class**.
2. **Member class bên trong class**.
3. **Member type bên trong interface**.
4. **Local class** bên trong block/method.
5. **Anonymous class**.

Các vị trí này **không chia sẻ một bộ access modifiers giống hệt nhau**.

## 18. Local class và anonymous class không phải member class

Một **local class** được khai báo trong một block, thường trong method:

```java
class Service {
    void run() {
        class LocalTask {
            void execute() {
                System.out.println("run");
            }
        }

        new LocalTask().execute();
    }
}
```

`LocalTask` **không** phải member class của `Service`; nó là local class, có phạm vi tên gắn với block. Không được dùng `public class LocalTask`, `protected class LocalTask` hay `private class LocalTask` tại vị trí local class như access modifiers member class. Các ràng buộc khác về local variables capture cũng có thể áp dụng.

**Anonymous class** không có tên source tương tự `Outer.Nested`:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
```

Đây là **mảnh mã trong method**. Anonymous class không được gán một access modifier khai báo class theo kiểu `private class ...` vì nó không có declaration cùng hình thức member class.

Như vậy, xác định **cấu trúc cú pháp** (top-level/member/local/anonymous) là bước đầu tiên trước khi quyết định một modifier có hợp lệ.

## 19. Package, module và khả năng truy cập ở Java 9+

Với dự án sử dụng **Java Platform Module System (JPMS)**, một top-level class `public` có thể vẫn **không accessible từ module khác** nếu package chứa nó không được export phù hợp.

Ví dụ module khai báo:

```java
module academy.core {
    exports academy.api;
}
```

Giả sử module này chứa:

- `academy.api.PublicCourse`: public top-level class trong package được export.
- `academy.internal.InternalService`: public top-level class trong package **không export**.

Một module khách hàng:

```java
module academy.client {
    requires academy.core;
}
```

Mã trong `academy.client` có thể tham chiếu `academy.api.PublicCourse` nếu đủ điều kiện, nhưng **không tự được** truy cập `academy.internal.InternalService` chỉ vì lớp ấy mang modifier `public`. Lý do là package `academy.internal` không được export tới module khách hàng.

Hai đoạn `module-info.java` trên là **mảnh cấu hình minh họa**, không phải chương trình Java chạy độc lập. Với classpath không có named-module boundary tương ứng, cách phân giải package visibility khác. Khi gặp lỗi module access, hãy kiểm tra `module-info.java`, `requires`, `exports` và compile/run mode thực tế.

### `exports` khác `opens`

- `exports` chủ yếu cho phép truy cập các **public types/public members** của package từ module khác theo quy tắc module.
- `opens` chủ yếu phục vụ **deep reflection** trong các điều kiện module thích hợp, không phải cách làm mọi package-private/private type thành public trong mã nguồn thường.
- Reflection có các kiểm tra truy cập và module riêng; sự tồn tại của kỹ thuật reflection **không thay đổi** quy tắc source-level access modifiers đang học.

Đừng gán nhãn “Java không thấy class public” là lỗi modifier ngay khi chưa xem **package/module** trong dự án dùng JPMS.

## 20. Khi nào nên dùng mức truy cập nào?

### Public top-level class

Dùng khi kiểu đại diện **API công khai**, người dùng thuộc package khác cần đặt tên trực tiếp, ví dụ `public class Order` hoặc `public interface PaymentGateway`. Nhưng không có nghĩa mọi method/field đều phải public.

### Package-private top-level class

Dùng với implementation chỉ phục vụ **các class cùng package**, chẳng hạn parser, mapper hoặc helper nội bộ. Có thể kiểm soát bề mặt API tốt hơn thay vì công khai mọi kiểu chỉ để chúng được dùng trong dự án.

### Public member class

Dùng khi kiểu phụ thực sự là một phần mô hình công khai gắn với enclosing type, ví dụ `Map.Entry` hoặc một result/configuration type theo thiết kế phù hợp. Xem thêm static hay inner để người dùng có cách tạo object rõ ràng.

### Protected member class

Dùng khi thiết kế **extension point** cho subclass được chủ động hỗ trợ. Phải viết contract kế thừa rõ ràng, và suy nghĩ về constructor/method visibility của nested type; không tự mặc định đây là API phổ thông cho mọi client.

### Package-private member class

Dùng cho helper type gắn với enclosing type nhưng **chỉ những class cùng package** cần thấy. Tránh phơi ra code khác package trong public signatures nếu caller không thể nhắc tên.

### Private member class

Dùng để ẩn **implementation detail**, helper class, iterator nội bộ hoặc state chỉ phục vụ lớp bao ngoài. Nó giúp client không phụ thuộc vào kiểu bên trong, nhưng không tự làm dữ liệu an toàn trước mọi hình thức reflection/serialization/thư viện khác.

**Nguyên tắc thiết kế:** chọn **mức truy cập nhỏ nhất phù hợp với hợp đồng thật**, rồi mở rộng có chủ đích khi cần. Một kiểu `public` đã được thư viện bên ngoài sử dụng có thể khó thu hẹp quyền truy cập mà không phá vỡ khả năng biên dịch của client.

## 21. Những lỗi biên dịch và suy luận thường gặp

| Lỗi hoặc ngộ nhận | Giải thích đúng |
| --- | --- |
| “Top-level class dùng được cả `private`, `protected`” | Không; chỉ `public` hoặc package-private |
| “Không ghi modifier là `public`” | Không; trường hợp đó là package-private |
| “Package con là cùng package” | Không; `a.b` và `a.b.c` là hai package khác |
| “Hai file cùng thư mục được quyền package-private” | Cần xét khai báo package, không chỉ đường dẫn |
| “Mọi nested class đều là inner class” | Static nested class **không** có enclosing instance ngầm |
| “`static` trên nested class là mức truy cập” | `static` không phải access modifier |
| “Public outer nghĩa mọi member class đều public” | Mỗi member class có access modifier riêng |
| “Public member class nhìn được dù enclosing class private” | Cần xem cả chuỗi enclosing type accessibility |
| “Có quyền đặt tên nested type nghĩa có quyền gọi constructor” | Constructor còn có access level riêng |
| “`protected` chỉ dành cho subclass, cùng package không dùng được” | Code cùng package cũng có protected access thích hợp |
| “Hễ extends là gọi mọi protected member qua bất kỳ Base receiver” | Protected cross-package còn quy tắc subclass/receiver riêng |
| “Private member class không bao giờ được outer truy cập” | Enclosing type/nestmates có quyền private access thích hợp |
| “Local class trong method là member class” | Local class có quy tắc phạm vi và modifier khác |
| “Public top-level class tự tạo được bằng `new` ở mọi nơi” | Phải xét constructor, abstract, package và module |
| “Member class và top-level class khác nhau chỉ ở tên có dấu chấm” | Còn có quy tắc access, enclosing instance và naming |
| “Protected member class có default constructor công khai cho client” | Quyền constructor cần xét riêng; có thể không accessible |
| “`public` class trong unexported module package tự accessible” | JPMS có thêm module exports boundary |
| “`final`, `abstract` là access modifiers” | Chúng ảnh hưởng kế thừa/khởi tạo, không quyết định public/private |
| “Một compilation unit chỉ được có một top-level class” | Có thể thêm package-private top-level types phù hợp |
| “Một file `Outer.java` có class `Helper` ở cuối tức Helper nested trong Outer” | Chỉ nested nếu khai báo nằm bên trong braces của Outer |

## 22. Checklist chẩn đoán “class is not public” hoặc “has private access”

Khi compiler báo lỗi truy cập kiểu/constructor, thực hiện theo thứ tự:

1. **Xác định class cần dùng là top-level, member, local hay anonymous**. Với member, enclosing declaration là class hay interface?
2. **Kiểm tra tên package của cả hai phía**. Trùng package thật sự hay chỉ chung tiền tố?
3. **Kiểm tra access modifier của top-level/enclosing types**. Mọi đoạn tên `Outer.Inner` liên quan có truy cập được không?
4. **Kiểm tra access modifier của member class**: `public`, `protected`, package-private, `private`.
5. **Nếu là `protected` ở package khác**, xác minh mã ở ngữ cảnh subclass hợp lệ và xem các điều kiện receiver/qualification tương ứng.
6. **Kiểm tra constructor đích**: có tồn tại đúng tham số và có truy cập được không? Class accessible chưa đủ.
7. **Kiểm tra field/method bên trong class**: chúng có thể private hoặc package-private ngay cả khi class public.
8. **Nếu member class non-static**, kiểm tra enclosing instance và cú pháp `outer.new Inner()` trong ngữ cảnh phù hợp.
9. **Nếu member class static**, dùng cú pháp `new Outer.Nested()` khi hợp lệ; không cần outer object.
10. **Kiểm tra public top-level class và tên file nguồn**, nhất là khi compiler báo public class phải ở tệp tương ứng.
11. **Nếu dùng named modules**, kiểm tra `requires` và `exports`, tránh nhầm module boundary với access modifier.
12. **Chọn cách sửa phù hợp với thiết kế**: không tự động biến mọi class/method/constructor thành `public` chỉ để qua lỗi compile.

### Lỗi truy cập và lỗi tạo instance là hai loại khác nhau

Ví dụ:

```java
public abstract class AbstractService {
}
```

Class này có thể **public**, nhưng `new AbstractService()` vẫn **không hợp lệ** vì abstract. Nếu constructor `private` hoặc package-private không accessible, lỗi lại là truy cập constructor. Nếu top-level class package-private ở package khác, có thể lỗi ở **truy cập tên kiểu**.

Các thông báo compiler thường như `is not public in ...; cannot be accessed from outside package`, `has private access`, `has protected access` hoặc `constructor ... is not applicable`. Nội dung chính xác có thể thay đổi theo JDK/ngữ cảnh, nhưng cách chẩn đoán cần xác định **bước truy cập nào thất bại**.

## 23. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** `private class X {}` ở cấp đầu tệp Java có hợp lệ không?

**Đáp án:** Không. Top-level class chỉ cho `public` hoặc package-private.

**Câu 2.** `class X {}` ở đầu tệp có mức truy cập gì?

**Đáp án:** Package-private, vì không có access modifier.

**Câu 3.** `public class Outer { private static class Hidden {} }` có hợp lệ không?

**Đáp án:** Có. `Hidden` là **private member class**, không phải top-level class.

**Câu 4.** Một class ở `app.client` có dùng được class package-private ở `app.core` không?

**Đáp án:** Không theo truy cập nguồn Java thông thường. Đây là hai package khác nhau, dù cùng tiền tố `app`.

**Câu 5.** Trong cùng package với `Outer`, có được dùng `protected static class Helper` của `Outer` không?

**Đáp án:** Có, nếu các điều kiện phù hợp khác như constructor/member access được thỏa; protected cho truy cập từ cùng package.

**Câu 6.** Subclass ở package khác có tự được gọi mọi protected constructor của nested type không?

**Đáp án:** Không. Quyền truy cập **member type** và quyền gọi **constructor** là hai bước riêng, với quy tắc protected constructor đặc thù.

**Câu 7.** `public static class Id` và `public class Description` đặt trong `Outer` khác gì về quyền truy cập?

**Đáp án:** Chúng đều public member classes, nhưng `Id` static nested không cần enclosing instance; `Description` là non-static inner class cần outer instance phù hợp.

**Câu 8.** `Outer.Nested` có public nhưng `Outer` không accessible từ nơi gọi, có được trực tiếp dùng tên đủ điều kiện đó không?

**Đáp án:** Không; điều kiện truy cập enclosing type cũng phải được thỏa.

**Câu 9.** Lớp `public class A { A(){} }` có được `new A()` từ package khác không?

**Đáp án:** Không; constructor explicit `A()` là package-private do không ghi `public`.

**Câu 10.** Trong một public class, một private member class có thể chứa public method không?

**Đáp án:** Có về cú pháp. Nhưng code bên ngoài không tự đặt tên/khởi tạo private nested type được; public method của nó không làm chính nested type trở thành public API.

**Câu 11.** Top-level public class có thể được khai báo cùng một top-level package-private class trong cùng tệp không?

**Đáp án:** Có; chúng vẫn là **hai top-level types**, không phải quan hệ member class.

**Câu 12.** Static nested class có thể dùng `this` trong instance method của chính nó không?

**Đáp án:** Có. `this` đó là instance của static nested class. Nó không có `Outer.this` ngầm như non-static inner class.

**Câu 13.** Nếu một public type nằm trong unexported package của named module, module khác có tự nhắc tên được không?

**Đáp án:** Không theo cách truy cập module thông thường, vì package chưa được export thích hợp.

**Câu 14.** `protected` và `final` có cùng loại modifier không?

**Đáp án:** Không. `protected` điều khiển quyền truy cập member; `final` giới hạn kế thừa/ghi đè hoặc phép gán tùy nơi dùng.

**Câu 15.** Một local class bên trong method có được khai báo `private class Local {}` không?

**Đáp án:** Không. Local classes không dùng bốn access modifiers như member class.

## 24. Mẫu tổ chức API dễ bảo trì

Một cách tổ chức phổ biến là để **top-level public API** làm điểm tiếp xúc bên ngoài, còn helper types chỉ được mở theo nhu cầu.

Ví dụ một tệp đơn **`OrderService.java`**:

```java
public class OrderService {
    public static final class Result {
        private final String message;

        public Result(String message) {
            this.message = message;
        }

        public String message() {
            return message;
        }
    }

    private static final class Validator {
        private Validator() {
        }

        static void requireNonBlank(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text required");
            }
        }
    }

    public Result create(String code) {
        Validator.requireNonBlank(code);
        return new Result("created:" + code);
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        Result result = service.create("A1");
        System.out.println(result.message());
    }
}
```

```bash
javac OrderService.java
java OrderService
```

```text
created:A1
```

**Điều đáng chú ý:**

- `OrderService` là public top-level class, làm điểm vào API.
- `Result` là public static member class để caller nhận một kiểu kết quả có tên rõ ràng. `final` ngăn kế thừa `Result`, không ảnh hưởng `public`.
- `Validator` là private static member class; client không cần biết hoặc phụ thuộc trực tiếp vào tên kiểu này.
- `create` là public instance method, dùng private helper để validate và trả public result.
- Không cần tạo outer instance chỉ để tạo `Result` ở nơi khác, vì Result static nested; ngược lại, để gọi `create` cần một `OrderService` instance trong ví dụ.
- Cách thiết kế bề mặt public API và helper private giúp thay đổi implementation sau này mà ít làm ảnh hưởng client.

**Lưu ý thiết kế:** việc private helper nằm trong public outer class không phải lúc nào cũng tối ưu. Nếu nhiều classes trong package cần tái sử dụng helper, có thể cân nhắc một top-level package-private helper thay vì cố đặt mọi logic lồng vào một lớp.

---

**Ghi nhớ cuối bài:** Quyền truy cập của **top-level class** có đúng hai lựa chọn **`public`** hoặc **package-private**. **Member class nằm trong một class** có thể mang **`public`, `protected`, package-private hoặc `private`**; `static` quyết định việc có enclosing instance ngầm hay không, **không phải** mức truy cập. Để sử dụng một nested type từ nơi khác, phải kiểm tra **enclosing type → member type → constructor → method/field**, cùng package, subclass và module boundary. Chọn phạm vi nhỏ nhất đáp ứng API để vừa biên dịch đúng vừa tránh làm lộ implementation không cần thiết.