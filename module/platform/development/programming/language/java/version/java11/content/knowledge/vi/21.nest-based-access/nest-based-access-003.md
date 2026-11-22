# Quan hệ giữa nest-based access, nested class, inner class và interface (Java 11+)

## 1. Vấn đề mà nest-based access giải quyết

Khi học Java, ta thường thấy một lớp bên trong lớp khác có thể truy cập trường/phương thức `private` của lớp bao ngoài, và lớp bao ngoài cũng có thể truy cập `private` của lớp lồng bên trong:

```java
class Box {
    private int number = 42;

    class Reader {
        int read() {
            return number; // Hợp lệ trong Java.
        }
    }
}
```

Đây là **mảnh mã minh họa**, không phải chương trình có `main`. Các quy tắc truy cập ở **ngôn ngữ Java** đã cho phép những trường hợp lồng kiểu hợp lệ từ lâu. Nhưng khi biên dịch, `Box` và `Box.Reader` thường là **hai class file riêng**. Ở tầng JVM, `private` vốn được kiểm soát theo lớp, nên một class file khác không thể tự nhiên truy cập trực tiếp private member.

**Java 11 bổ sung JEP 181 — Nest-Based Access Control.** JVM nhận biết một nhóm class/interface thuộc cùng một **nest** (*nestmates*), cho phép chúng truy cập private member của nhau ở tầng bytecode. Compiler Java 11+ có thể phát lệnh truy cập trực tiếp thay vì phải tạo các phương thức cầu nối mở rộng quyền truy cập chỉ để xử lý private access của các kiểu lồng nhau.

**Điểm quan trọng nhất:** nest-based access là **cơ chế JVM**, không phải modifier mới và **không thay đổi các quy tắc Java source về quyền truy cập**. Đừng hiểu “cùng nest” là có thể viết bất kỳ cú pháp truy cập nào không hợp lệ hoặc tự động có một object bao ngoài.

Bài này làm rõ quan hệ của cơ chế đó với:

1. `static nested class` — lớp thành viên lồng `static`.
2. `inner class` — đặc biệt là non-static member class có đối tượng bao ngoài.
3. `local class` và `anonymous class`.
4. `nested interface`, interface có private methods, và class lồng trong interface.
5. `Class.getNestHost()`, `getNestMembers()`, `isNestmateOf()` cùng các thuộc tính class file `NestHost`/`NestMembers`.

Những API và quy tắc này vẫn áp dụng trong Java hiện đại. Các ví dụ dùng tính năng sẵn có ở Java 11 và được kiểm tra bằng `javac --release 11`.

## 2. Nestmates và nested types: hai khái niệm liên quan nhưng không đồng nhất

**Nested type** là khái niệm của **ngôn ngữ Java**: một khai báo class hoặc interface nằm trong khai báo class/interface khác, hay một local/anonymous class được khai báo ở ngữ cảnh phù hợp.

**Nest** là khái niệm của **JVM**: tập hợp những class/interface có cùng một **nest host**, được nhận biết qua metadata của class file. Các member trong cùng nest có thể truy cập private member của nhau theo kiểm tra quyền ở JVM.

Trong trường hợp thông thường, `javac --release 11` nhóm một **top-level class/interface** với các kiểu lồng tương ứng (kể cả local/anonymous class được biên dịch) vào cùng một nest.

```text
Một tệp nguồn Java
|
+-- class Outer                 <-- nest host (class file Outer.class)
|   |
|   +-- static class Tool      <-- nest member (Outer$Tool.class)
|   |
|   +-- class Inner            <-- nest member (Outer$Inner.class)
|   |
|   +-- interface Rule         <-- nest member (Outer$Rule.class)
|   |    |
|   |    +-- class Impl        <-- nest member (Outer$Rule$Impl.class)
|   |
|   +-- method() {
|           class Local { ... } <-- nest member (class file riêng)
|           new Runnable() {...} <-- nest member (class file riêng)
|       }
|
+-- class OtherTopLevel         <-- nest riêng, dù cùng tệp nguồn
```

Sơ đồ mô tả **trường hợp compiler Java 11 thường tạo**; nó không có nghĩa mọi class có tên chứa ký tự `$` đều là nestmate. Quyền truy cập được quyết định bằng **thuộc tính class file hợp lệ**, không phải việc tên lớp “trông giống” lớp lồng.

### 2.1. Một nest có một host

- `Outer` là **nest host**.
- `Outer$Tool`, `Outer$Inner` và các member khác ghi host tương ứng.
- Các member của cùng host là **nestmates**, kể cả hai member không nằm trực tiếp trong nhau.
- Một class/interface không ghi thuộc nest nào thì thuộc **nest chỉ có chính nó**, và tự làm host.

Chẳng hạn `Outer.Tool` và `Outer.Inner` có thể là nestmates dù chúng là **hai loại member khác nhau**: một class `static`, một inner class. Quan hệ nest không quyết định chuyện một đối tượng có tham chiếu đến đối tượng bao ngoài hay không.

### 2.2. Bảng so sánh phạm vi

| Loại khai báo | Có thể là nestmate của top-level enclosing type? | Có ngay một enclosing instance không? | Điều cần hiểu |
| --- | --- | --- | --- |
| `static class Nested` trong class | Có, khi biên dịch thành cùng nest | **Không** | Truy cập private static của outer; private instance cần **object outer tường minh**. |
| `class Inner` non-static trong class | Có | **Có**, theo ngữ nghĩa inner member class | Có thể dùng `Outer.this` và private instance member của outer. |
| `class Local` trong method | Có trong mô hình javac Java 11 | Phụ thuộc ngữ cảnh khai báo | Có thể truy cập thành viên hợp lệ và biến local **final/effectively final**. |
| Anonymous class | Có trong mô hình javac Java 11 | Phụ thuộc ngữ cảnh tạo | Thường dùng để triển khai interface/lớp; vẫn chịu luật scope/capture. |
| `interface Rule` trong class | Có | **Không** (nested interface implicitly static) | Private method trong interface và các nestmate có thể tương tác hợp lệ. |
| Class/interface là member của interface | Có | **Không** (member type của interface implicitly static) | Không tự giữ một instance của interface. |
| Subclass chỉ vì `extends Outer` | **Không tự động** | Quan hệ kế thừa, không phải enclosing instance | `extends` không tạo nest membership. |
| Class khác trong cùng package/tệp nguồn | **Không tự động** | Không | Cùng package/file không mở quyền `private`. |
| Class chỉ `implements Interface` | **Không tự động** | Không | Implement interface không tự cho quyền đọc private method của interface. |

**Nhớ:** nestmate access là một điều kiện của kiểm tra private access ở **runtime**. Nó không vượt qua các điều kiện tên, lexical scope, instance/static context và visibility của **source language**.

## 3. Static nested class: cùng nest nhưng không có Outer.this

Ví dụ:

```java
class Account {
    private int balance = 100;
    private static String category = "basic";

    static class Inspector {
        String inspect(Account account) {
            return account.balance + ":" + category;
        }
    }
}
```

Đây là một **mảnh mã Java hợp lệ**. `Inspector` là **static nested class**:
- Nó là kiểu thành viên lồng trong `Account`.
- Nó **không cần `Account` instance để được khởi tạo**: về mặt cú pháp, có thể tạo `new Account.Inspector()` nếu đủ quyền truy cập.
- Nó **không có `Account.this`** và không thể đọc `balance` như một trường instance của outer nếu không có đối tượng nào.
- Nó có thể đọc `category` vì đây là static member.
- Nó có thể đọc `account.balance` mặc dù `balance` là private, vì quan hệ lồng kiểu cho phép cú pháp này và JVM Java 11 hỗ trợ truy cập private giữa nestmates.

### 3.1. Lỗi thường gặp: nghĩ nestmate tạo enclosing instance

**Sai (mã cố ý không biên dịch):**

```java
class Container {
    private int value = 10;
    static class Nested {
        int read() {
            return value; // ERROR: không có enclosing instance.
        }
    }
}
```

Đây là **phản ví dụ**, không đưa vào chương trình chạy. Lỗi không phải vì JVM thiếu nestmate permission; lỗi là thiếu **một đối tượng** cho trường instance.

**Đúng:**

```java
class Container {
    private int value = 10;
    static class Nested {
        int read(Container outer) {
            return outer.value;
        }
    }
}
```

Nestmates giúp truy cập **private member**, nhưng không tự tạo tham chiếu `outer`. Khi cần state từ outer, hãy truyền đối tượng rõ ràng qua constructor/phương thức thay vì tìm cách truy cập `Outer.this` trong static context.

### 3.2. Static nested class vẫn có lexical enclosing class

`StaticNested.class.getEnclosingClass()` có thể trả outer class, dù static nested class **không có enclosing instance**. Hai khái niệm phải tách rời:

- **Enclosing class**: mối quan hệ của **khai báo kiểu**.
- **Enclosing instance**: quan hệ của **đối tượng runtime**.
- **Nest host**: quan hệ **cấp class file/JVM** cho private access.

Không dùng riêng `getEnclosingClass() != null` để kết luận một nested class giữ tham chiếu đến object outer.

## 4. Non-static inner class: có enclosing instance và là nestmate

Trong Java, một **inner member class** là class thành viên không khai báo `static`:

```java
class Wallet {
    private int balance = 25;

    class Printer {
        String print() {
            return String.valueOf(balance); // Ngầm hiểu Wallet.this.balance.
        }
    }

    String run() {
        Printer printer = new Printer();
        return printer.print();
    }
}
```

Đây là mảnh mã hợp lệ trong Java 11. `Printer` là **inner class**, có thể truy cập `balance` của một `Wallet` instance đang bao chứa nó.

Có thể tạo từ bên ngoài nơi có quyền sử dụng kiểu:

```java
Wallet wallet = new Wallet();
Wallet.Printer printer = wallet.new Printer();
```

Mảnh mã thứ hai giả định hai lớp được khai báo và phạm vi truy cập cho phép.

### 4.1. Điều gì là của inner class, điều gì là của nestmate?

| Hành vi | Cơ chế chính |
| --- | --- |
| `new Wallet().new Printer()` | Ngữ nghĩa **inner class / enclosing instance**. |
| Dùng `Wallet.this.balance` trong `Printer` | Có **enclosing instance** trong ngữ nghĩa source. |
| JVM cho class file `Wallet$Printer` truy cập trực tiếp private field của `Wallet` | **Nest-based access** trên Java 11+. |
| Class outer đọc private field/constructor của `Printer` | Quy tắc truy cập source của các kiểu lồng + **nest-based access** ở JVM. |
| `Printer` được dùng làm subclass hoặc implements interface | Kế thừa/triển khai **độc lập** với nest membership. |

**Không suy ngược rằng mọi nestmate đều có enclosing instance.** `Wallet.Printer` có, nhưng `Wallet.StaticMember` không.

### 4.2. Outer và inner có thể đọc private member lẫn nhau

```java
class Outer {
    private String secret = "from-outer";

    class Inner {
        private String label = "from-inner";

        String read() {
            return Outer.this.secret;
        }
    }

    String readInner() {
        Inner inner = new Inner();
        return inner.label;
    }
}
```

Cả hai hướng truy cập trên đều hợp lệ trong Java. `private` không biến thành `public`; code ngoài nest và ngoài phạm vi được cho phép vẫn không thể tự truy cập những trường ấy.

**Vòng đời bộ nhớ:** một instance inner có thể giữ quan hệ với outer instance. Nếu đặt inner object ở cấu trúc sống lâu (callback, listener, cache), phải cân nhắc việc nó giữ outer state sống lâu hơn dự kiến. Khi không cần enclosing instance, dùng static nested class hoặc tách một lớp độc lập có dependency truyền tường minh sẽ đơn giản hơn.

## 5. Local class và anonymous class: cũng có thể thuộc cùng nest

### 5.1. Local class

Local class được khai báo bên trong block/method:

```java
class Service {
    private String token = "safe";

    String run() {
        String suffix = "ready"; // effectively final

        class LocalFormatter {
            String format() {
                return token + "-" + suffix;
            }
        }

        return new LocalFormatter().format();
    }
}
```

Đây là mảnh mã hợp lệ. `LocalFormatter` có thể đọc private field `token` của `Service` (tùy ngữ cảnh enclosing instance) và biến local `suffix` vì nó **effectively final**.

Các ràng buộc:
- Local class là kiểu được khai báo trong block, **không phải member class** của enclosing class.
- Không viết `private class LocalFormatter` trong block để thay thế quy tắc phạm vi; local class không khai báo access modifier như member class.
- `getDeclaringClass()` của local class thường trả **null**, vì nó không phải **member class**.
- `getEnclosingClass()` trả enclosing class tương ứng.
- `getNestHost()` của class được `javac --release 11` tạo thông thường có thể trả **top-level nest host** chung.

### 5.2. Anonymous class

```java
class Service {
    private String token = "safe";

    Runnable task() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(token);
            }
        };
    }
}
```

Đây là mảnh mã Java hợp lệ. Anonymous class có thể truy cập private member của enclosing class; compiler Java 11 có thể đưa class file anonymous vào nest của host.

**Không nhầm anonymous class với lambda:**
- `new Runnable() { ... }` biểu diễn một **anonymous class**.
- `() -> ...` là **lambda expression**, có cơ chế triển khai riêng và không nên suy luận về classfile nest membership chỉ từ tên runtime của lambda.
- Nestmate là quan hệ xác định qua metadata/class semantics, không phải “được khai báo gần nhau trong một method”.

### 5.3. Tên lớp không phải bằng chứng của nest

Class file của local/anonymous thường có tên chứa `$` và chữ số do compiler sinh ra, nhưng **đừng dựa vào mẫu tên** `Outer$1`/`Outer$1Local` làm kiểm tra bảo mật. Tên có thể khác giữa compiler, phiên bản và cách sắp xếp source. Dùng `Class.isNestmateOf(...)` hoặc xem metadata khi cần chẩn đoán.

## 6. Nested interface: implicitly static nhưng vẫn tham gia nest

### 6.1. Interface lồng bên trong class

```java
class Outer {
    private interface Strategy {
        int calculate(int input);
    }
}
```

`Strategy` là một **member interface** của `Outer`, có mức truy cập `private` (chỉ dùng hợp lệ trong ngữ cảnh member interface của một class). **Nested interface là implicitly static**, nên không có `Outer.this` và không tự giữ một instance `Outer`.

Tuy nhiên, nếu compiler Java 11 đặt `Outer.Strategy` trong cùng nest với `Outer`, quan hệ nest cho phép kiểm tra private access giữa các class/interface member hợp lệ.

### 6.2. Class thành viên bên trong interface

Trong Java 11, member class/interface được khai báo trong interface là **implicitly `public static`**:

```java
interface Registry {
    class Entry {
        static String kind() {
            return "entry";
        }
    }
}
```

Đoạn minh họa hợp lệ. Có thể gọi `Registry.Entry.kind()` từ nơi có quyền truy cập `Registry`. **`Registry.Entry` không có một instance `Registry`**, vì interface không được tạo đối tượng trực tiếp và member class implicitly static.

**Điểm thường nhầm:** `Entry` là class lồng trong interface nhưng không phải non-static inner class. Mọi **nested interface** cũng implicitly static; không có “inner interface” theo nghĩa một interface giữ đối tượng outer.

### 6.3. Private methods trong interface và nestmates

Java 11 hỗ trợ **private methods trong interface**. Một member class thuộc cùng nest có thể gọi private static helper trong interface khi ngữ cảnh source cho phép:

```java
interface Policy {
    private static String rule() {
        return "internal";
    }

    class Member {
        static String read() {
            return Policy.rule();
        }
    }
}
```

Đây là **mảnh mã hợp lệ trong Java 11**. `Policy.Member` là member class implicitly public static. Nhờ ngữ nghĩa truy cập của kiểu lồng và cơ chế nestmates, lời gọi private helper có thể thực hiện mà không cần công khai helper.

Nhưng một class **khác**, chỉ `implements Policy` ở bên ngoài, **không tự thành nestmate** và **không có quyền truy cập `Policy.rule()`**. `implements` là quan hệ thực thi contract, không phải bằng chứng same nest.

### 6.4. Các member nằm sâu trong nhiều tầng

```java
class Top {
    interface A {
        class B { }
    }
}
```

Khi `javac --release 11` tạo class files, `Top`, `Top.A` và `Top.A.B` có thể thuộc **một nest có host `Top`**. Nest host không nhất thiết là `getDeclaringClass()` trực tiếp của B:

- `Top.A.B.class.getDeclaringClass()` → `Top.A.class`.
- `Top.A.B.class.getNestHost()` → `Top.class` (với metadata bình thường do compiler Java 11 tạo).

Điều này cho thấy **nest host** và **immediate declaring/enclosing class** không đồng nhất.

## 7. Cơ chế JVM của Java 11: NestHost, NestMembers và private access

### 7.1. JEP 181 thay đổi tầng nào?

Java 11 đưa vào hai thuộc tính class file:

- **`NestMembers`** nằm trên **nest host**, liệt kê các class/interface được phép tuyên bố thuộc nest này.
- **`NestHost`** nằm trên **member**, ghi class/interface làm host mà member tham gia.

Quy tắc phải được **xác nhận nhất quán**: member tự khai là thuộc host, còn host phải liệt kê member, và chúng phải thỏa ràng buộc runtime package. Không thể tự tạo tên class chứa `$` hoặc sửa một thuộc tính tùy ý rồi mặc định đã được JVM trao quyền private access.

Class file Java 11 có **major version 55**. Trong chương trình Java thông thường biên dịch `--release 11`, các thuộc tính mới cho phép JVM kiểm tra quyền private giữa nestmates mà compiler không cần tạo thêm synthetic accessor chỉ vì hai member cần truy cập private của nhau.

### 7.2. Vì sao trước đây người ta nói đến synthetic accessor?

Ở mô hình class file thiếu nest metadata, compiler có thể dùng các **cầu nối tổng hợp** với mức truy cập rộng hơn private để hỗ trợ cú pháp Java cho phép các kiểu lồng đọc private member của nhau. Java 11/JEP 181 giải quyết việc này ở JVM để compiler có thể tạo **direct private access**.

Ví dụ khi biên dịch mã trong mục 8 theo Java 11, lệnh `javap` xác nhận:

```text
major version: 55
NestMembers: ...        (trên nest host)
NestHost: ...           (trên các member)
```

Đây là **mô tả những thông tin cần tìm**, không phải output đầy đủ của `javap -v` (vì output dài và các index constant pool thay đổi theo compiler).

**Lưu ý:** không nói “mọi synthetic member trong mọi Java class đã biến mất”. Các synthetic constructs có thể còn xuất hiện vì nhiều mục đích khác. Điều chính xác là: với mã private access giữa nestmates được biên dịch theo Java 11, compiler **không cần** accessor mở rộng quyền truy cập chỉ để vượt qua ranh giới class file.

### 7.3. JVM private access khác với Java source access

JVM quyết định việc một member có quyền đọc private member khác **sau khi bytecode đã được tạo**. Compiler Java vẫn kiểm tra cú pháp và quy tắc scope của Java:

- Static nested class không có `Outer.this`.
- Non-static inner class có enclosing instance theo ngữ nghĩa source.
- Một class khác không được phép đọc private field chỉ vì **cùng package** hoặc **cùng file .java**.
- Không thể tạo nest bằng một từ khóa `nest` trong Java source.
- Quan hệ `extends`/`implements` không làm hai type trở thành nestmates.

**Nest-based access không biến private thành package-private hoặc public.** Nó bảo toàn private khi cho các classfile được khai báo cùng nest truy cập nhau ở mức JVM.

## 8. Chương trình Java 11 đầy đủ: class, inner, interface, local, anonymous

Ví dụ sau kiểm tra **cả truy cập private lẫn quan hệ class metadata**:

- `StaticMember` đọc private state và private method của `NestRelationsDemo` qua **đối tượng outer được truyền vào**.
- `InnerMember` truy cập private state của outer qua enclosing instance, và đọc private state từ nested class khác.
- Outer đọc private field của inner; truy cập private constructor nested.
- `Policy` là private nested interface; `Policy.Member` là class implicitly public static bên trong interface, truy cập private static method của `Policy`.
- Anonymous implementation có thể gọi helper private của nested interface `Handler` và private method outer.
- Local/anonymous class và nested interface đều được kiểm tra qua `Class.isNestmateOf`.
- Hai class top-level khác, kể cả một subclass, **không tự là nestmates**.

Lưu file **`NestRelationsDemo.java`**:

```java
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class NestRelationsDemo {
    private final int points = 7;
    private static final String TOKEN = "TOP";

    private String secret() {
        return "outer";
    }

    private static class StaticMember {
        private static final String LABEL = "static";
        private StaticMember() {}

        private static String view(NestRelationsDemo outer) {
            return outer.points + ":" + outer.secret()
                    + ":" + outer.new InnerMember().own;
        }
    }

    private class InnerMember {
        private final String own = "inner";
        private InnerMember() {}

        private String view() {
            return points + ":" + secret() + ":" + StaticMember.LABEL;
        }
    }

    private interface Policy {
        private static String privateRule() {
            return "policy";
        }

        class Member {
            static String readRule() {
                return Policy.privateRule();
            }
        }
    }

    private interface Handler {
        String handle();

        private static String format() {
            return "interface";
        }
    }

    private String localAndAnonymous() {
        class Local {
            String read() {
                return secret() + ":" + points;
            }
        }
        Local local = new Local();
        Handler anonymous = new Handler() {
            @Override
            public String handle() {
                return Handler.format() + ":" + secret();
            }
        };

        System.out.println("localResult=" + local.read());
        System.out.println("anonymousResult=" + anonymous.handle());
        System.out.println("localNestmate=" +
                local.getClass().isNestmateOf(NestRelationsDemo.class));
        System.out.println("anonymousNestmate=" +
                anonymous.getClass().isNestmateOf(NestRelationsDemo.class));
        System.out.println("localDeclaringNull=" +
                (local.getClass().getDeclaringClass() == null));
        System.out.println("localEnclosingOuter=" +
                (local.getClass().getEnclosingClass() == NestRelationsDemo.class));
        return "localDone";
    }

    public static void main(String[] args) {
        NestRelationsDemo outer = new NestRelationsDemo();
        StaticMember nested = new StaticMember();
        InnerMember inner = outer.new InnerMember();

        System.out.println("staticAccess=" + StaticMember.view(outer));
        System.out.println("innerAccess=" + inner.view());
        System.out.println("outerReadsInner=" + inner.own);
        System.out.println("outerReadsNested=" + nested.LABEL);
        System.out.println("interfaceMember=" + Policy.Member.readRule());
        System.out.println("outerReadsInterface=" + Policy.privateRule());

        System.out.println("host=" +
                InnerMember.class.getNestHost().getSimpleName());
        System.out.println("staticNestmate=" +
                StaticMember.class.isNestmateOf(InnerMember.class));
        System.out.println("policyNestmate=" +
                Policy.class.isNestmateOf(NestRelationsDemo.class));
        System.out.println("policyMemberNestmate=" +
                Policy.Member.class.isNestmateOf(InnerMember.class));
        System.out.println("interfaceStatic=" +
                Modifier.isStatic(Policy.Member.class.getModifiers()));
        System.out.println("innerNonStatic=" +
                !Modifier.isStatic(InnerMember.class.getModifiers()));
        System.out.println("staticEnclosingClassOuter=" +
                (StaticMember.class.getEnclosingClass() == NestRelationsDemo.class));
        System.out.println("differentTopLevelNestmate=" +
                NestRelationsDemo.class.isNestmateOf(OtherTopLevel.class));
        System.out.println("subclassNestmate=" +
                NestRelationsDemo.class.isNestmateOf(SubclassOutside.class));
        System.out.println("nestedDeclaringOuter=" +
                (InnerMember.class.getDeclaringClass() == NestRelationsDemo.class));
        System.out.println("membersContainPolicy=" +
                Arrays.asList(NestRelationsDemo.class.getNestMembers())
                    .contains(Policy.class));
        outer.localAndAnonymous();
    }
}

class OtherTopLevel {}

class SubclassOutside extends NestRelationsDemo {}
```

**Biên dịch và chạy:**

```bash
javac -encoding UTF-8 --release 11 NestRelationsDemo.java
java NestRelationsDemo
```

**Đầu ra kiểm chứng** (biên dịch bằng `--release 11` trên JDK 24):

```text
staticAccess=7:outer:inner
innerAccess=7:outer:static
outerReadsInner=inner
outerReadsNested=static
interfaceMember=policy
outerReadsInterface=policy
host=NestRelationsDemo
staticNestmate=true
policyNestmate=true
policyMemberNestmate=true
interfaceStatic=true
innerNonStatic=true
staticEnclosingClassOuter=true
differentTopLevelNestmate=false
subclassNestmate=false
nestedDeclaringOuter=true
membersContainPolicy=true
localResult=outer:7
anonymousResult=interface:outer
localNestmate=true
anonymousNestmate=true
localDeclaringNull=true
localEnclosingOuter=true
```

### 8.1. Giải thích phần truy cập private

- `staticAccess=7:outer:inner`: `StaticMember` truy cập `outer.points`, `outer.secret()` và private field `InnerMember.own` qua một **outer instance tường minh**. Static nested class không có `NestRelationsDemo.this`, nhưng vẫn có thể dùng một object outer được truyền vào.
- `innerAccess=7:outer:static`: `InnerMember` truy cập private field/method từ enclosing instance và private static field của sibling nested class.
- `outerReadsInner=inner`: outer code truy cập private field của `InnerMember`.
- `outerReadsNested=static`: outer code đọc field của static nested class.
- `interfaceMember=policy`: class nested trong interface gọi private static method của chính interface.
- `outerReadsInterface=policy`: outer class truy cập private method trong nested interface theo quyền truy cập của các kiểu lồng.

### 8.2. Giải thích phần Class metadata

- `host=NestRelationsDemo`: `InnerMember` thuộc nest có host là top-level class.
- `staticNestmate=true`: `StaticMember` và `InnerMember` là nestmates, dù class thứ nhất static và class thứ hai là inner.
- `policyNestmate=true`, `policyMemberNestmate=true`: nested interface và class nằm bên trong nó thuộc cùng nest với các member khác.
- `interfaceStatic=true`: `Policy.Member` trong interface là implicitly static.
- `innerNonStatic=true`: `InnerMember` là non-static member class.
- `staticEnclosingClassOuter=true`: static nested class vẫn **được khai báo bên trong** outer type. Dòng này **không** có nghĩa nó mang một outer instance.
- `differentTopLevelNestmate=false`: `OtherTopLevel` là top-level class khác, dù được khai báo **trong cùng tệp nguồn**.
- `subclassNestmate=false`: `SubclassOutside extends NestRelationsDemo` nhưng **chỉ kế thừa** không tạo nestmate.
- `nestedDeclaringOuter=true`: member class `InnerMember` có declaring class trực tiếp là `NestRelationsDemo`.
- `membersContainPolicy=true`: `getNestMembers()` của host bao gồm nested interface `Policy`.

### 8.3. Giải thích local/anonymous

- `localResult=outer:7`: local class đọc private members của enclosing class.
- `anonymousResult=interface:outer`: anonymous implementation gọi private helper của nested interface và private method outer.
- `localNestmate=true`, `anonymousNestmate=true`: hai class file do `javac --release 11` sinh ra có cùng nest host.
- `localDeclaringNull=true`: local class không phải member class nên `getDeclaringClass()` là null.
- `localEnclosingOuter=true`: vẫn nhận diện được enclosing class của local type.

**Lưu ý:** việc test chỉ dựa vào các kết quả boolean ổn định, **không dựa vào tên class file tự sinh** của local/anonymous class.

## 9. Dùng javap để kiểm tra nest metadata trong class file

Sau khi biên dịch chương trình ở mục 8, chạy:

```bash
javap -v -p NestRelationsDemo
javap -v -p 'NestRelationsDemo$InnerMember'
javap -v -p 'NestRelationsDemo$Policy$Member'
```

Nếu dùng PowerShell/Bash, dấu nháy đơn quanh tên có `$` giúp shell không diễn giải ký tự đặc biệt. Lệnh `javap -v` hiển thị rất nhiều metadata, nên tập trung các phần:

- `major version: 55` của class file khi biên dịch `--release 11`.
- `NestMembers` trên `NestRelationsDemo.class`.
- `NestHost` trên `NestRelationsDemo$InnerMember.class` và `NestRelationsDemo$Policy$Member.class`.
- Các private methods/fields/constructors vẫn là `private` trong class file.

**Kiểm chứng đã thực hiện:** ví dụ biên dịch bằng `javac -encoding UTF-8 --release 11`; kiểm tra `javap -v -p` xác nhận class file major 55, `NestMembers` trên host, `NestHost` trên inner và nested interface member. Không tìm thấy synthetic accessor tên dạng `access$...` trong các class được kiểm tra của ví dụ này.

**Đừng so sánh toàn bộ output của `javap -v` từng ký tự** giữa các JDK, vì constant-pool indexes, thứ tự/member metadata và cách compiler mô tả dữ liệu có thể khác nhau.

### 9.1. Nest metadata khác InnerClasses và EnclosingMethod

Class file có thể chứa cả:

| Thuộc tính / API | Phục vụ điều gì? |
| --- | --- |
| `InnerClasses` | Thông tin khai báo class/interface lồng; hỗ trợ mô tả quan hệ source/member. |
| `EnclosingMethod` | Thông tin enclosing method/constructor của local/anonymous class khi phù hợp. |
| `NestHost` | Class/interface này tuyên bố thuộc nest nào. |
| `NestMembers` | Host cho phép những member nào nằm trong nest của nó. |
| `Class.getDeclaringClass()` | Quan hệ khai báo **member type** trực tiếp. |
| `Class.getEnclosingClass()` | Enclosing class của kiểu lồng/local/anonymous. |
| `Class.getNestHost()` | Host của nhóm kiểm tra **private access**. |

**Không suy luận `getNestHost()==getDeclaringClass()`**: với kiểu lồng nhiều tầng như `Top.A.B`, declaring class trực tiếp là `A` nhưng nest host thường là `Top`.

## 10. Reflection API Java 11: kiểm tra nest một cách đúng đắn

`java.lang.Class` có ba API từ Java 11:

### 10.1. getNestHost()

```java
Class<?> host = SomeNestedType.class.getNestHost();
```

Trả về nest host của class/interface đó. Nếu loại không có thông tin nest hợp lệ, nó có thể thuộc nest đơn phần tử của **chính nó**. `getNestHost()` cũng có hành vi riêng với primitive/array type — thường trả chính `Class` tương ứng.

**Không dùng `getEnclosingClass()` thay thế**, vì đó là quan hệ khai báo/source chứ không phải nhóm quyền private access.

### 10.2. getNestMembers()

```java
Class<?>[] members = NestRelationsDemo.class.getNestMembers();
```

Trả danh sách các member của nest chứa class đó. Phần tử đầu là **nest host**; các phần tử sau **không được bảo đảm thứ tự ổn định**. Khi cần kiểm tra có member nhất định:

```java
boolean contains = Arrays.asList(
        NestRelationsDemo.class.getNestMembers()
).contains(NestRelationsDemo.InnerMember.class);
```

Đây là mảnh mã minh họa với các class như trong chương trình mục 8. Không hardcode index như `members[2]` để đại diện một nested type. Khi metadata bị lỗi, việc kiểm tra/tải member có thể phát sinh `LinkageError`; đừng che mọi lỗi liên kết bằng cách tự tin giả tạo rằng “không có nest”.

### 10.3. isNestmateOf(Class<?>)

```java
boolean sameNest =
        NestRelationsDemo.InnerMember.class.isNestmateOf(
                NestRelationsDemo.StaticMember.class);
```

Trong ví dụ, kết quả `true`. `isNestmateOf` cho biết **hai class/interface có cùng nest host**. Nó không kiểm tra:
- Hai **đối tượng** có cùng outer instance hay không.
- Có cùng superclass hoặc implement cùng một interface không.
- Hai class nằm trong cùng source file/package/module không.
- Một caller cụ thể có quyền truy cập một API `public`/`private` theo mọi luật Java source hay không.

Một class luôn cùng nest với **chính nó**. Một top-level class không có thành viên lồng có thể là nest đơn phần tử.

## 11. Nestmate không xóa ranh giới đóng gói và module

### 11.1. Cùng tệp không có nghĩa cùng nest

```java
class First {
    private int value = 1;
}

class Second {
    int read(First first) {
        return first.value; // Không biên dịch: value là private.
    }
}
```

Đây là **mã cố ý sai**, dù `First` và `Second` có thể ở cùng package và cùng file. Hai **top-level classes độc lập** không tự chia sẻ nest host.

### 11.2. Kế thừa không tạo nestmate

```java
class Parent {
    private int secret = 5;
}

class Child extends Parent {
    int read() {
        return secret; // Không hợp lệ: private của Parent không được kế thừa theo cách này.
    }
}
```

Đây cũng là **mã cố ý không biên dịch**. Một subclass bên ngoài nest không được đọc private của superclass chỉ vì `extends`. Ngược lại, một nested subclass được khai báo **bên trong cùng nest** có thể có một số quyền private access nhờ **nest membership**, chứ không phải do kế thừa tự mang lại.

### 11.3. Cùng module hoặc package cũng chưa đủ

Nest là nhóm do JVM công nhận với host/member hợp lệ. Không thể đặt hai class độc lập vào cùng package rồi mong Java tự cấp quyền private. Với bytecode tự sinh, metadata phải nhất quán và thỏa yêu cầu runtime package; việc thay đổi class loader, đóng gói hoặc thiếu class file có thể ảnh hưởng xác nhận nest membership và dẫn đến lỗi truy cập/liên kết.

**Đừng dùng nest metadata để phá ranh giới module hay tạo bypass cho code không tin cậy.** Class loader, module accessibility và runtime package vẫn là những khái niệm có ý nghĩa; nest không biến các type tùy ý thành một đối tượng có mọi quyền.

### 11.4. Nestmates và reflection

JVM Java 11 cũng sử dụng nest membership trong một số kiểm tra access của core reflection và method handles. Tuy nhiên:

- `Class.isNestmateOf` chỉ **hỏi về mối quan hệ nest**, không phải phép bật quyền reflection `setAccessible(true)` toàn cục.
- Không suy luận mọi lớp cùng module đều có thể truy cập private qua reflection.
- Nếu dùng `MethodHandles.Lookup`, phải phân biệt lookup context và các mức quyền được cấp; đừng coi nestmate là quyền reflection không giới hạn với mọi type.
- Tránh dùng deep reflection chỉ để đọc private members của thư viện bên thứ ba; giữ API rõ ràng và tuân thủ module encapsulation.

## 12. Ảnh hưởng đến thiết kế code thực tế

### 12.1. Khi nào dùng static nested class?

Dùng nếu class là chi tiết triển khai gắn với một loại outer nhưng **không cần tự động giữ enclosing instance**. Ví dụ: builder, DTO chỉ dùng nội bộ, validator/helper.

```java
class Config {
    private final String name;

    Config(String name) {
        this.name = name;
    }

    static class View {
        String read(Config config) {
            return config.name; // Dùng outer instance tường minh.
        }
    }
}
```

Dù `name` private, `View` có thể đọc qua `config` vì cùng nest trong mô hình javac Java 11. Điều này **không** phải lý do để phơi private key hoặc secrets ra API công cộng.

### 12.2. Khi nào dùng inner class?

Dùng nếu class thật sự cần **state của một outer instance** và quan hệ sống/chết được quản lý rõ. Trong các callback/cache sống lâu, cân nhắc inner class có thể giữ outer instance không cần thiết; static nested class với dependency truyền tường minh thường dễ kiểm soát bộ nhớ hơn.

### 12.3. Khi nào dùng nested interface?

Dùng khi contract nhỏ chỉ thuộc một thành phần, có thể đặt interface trong class/interface bao ngoài để làm rõ phạm vi tên. **Nested interface implicitly static**; không kỳ vọng nó đọc trực tiếp một trường instance outer qua `Outer.this`.

Private static helper trong interface có thể dùng để chia sẻ logic trong phạm vi interface/nest hợp lệ. Nhưng implementing class bên ngoài **không có quyền** gọi helper private chỉ vì triển khai contract.

### 12.4. Khi nào dùng local/anonymous class?

Dùng cho logic nhỏ, gắn trực tiếp với một method và không cần type name bên ngoài. Phải để ý capture biến local final/effectively final và việc giữ enclosing instance khi cần. Nếu code tăng kích thước hoặc có vòng đời độc lập, cân nhắc tách thành class/interface có tên.

### 12.5. Nest access không thay thế thiết kế API

Dù compiler/JVM có thể truy cập private giữa nested types, nên giữ:
- Public API nhỏ và có hợp đồng rõ.
- Private data thực sự chỉ được dùng trong thành phần tin cậy.
- Không dùng `static nested` chỉ để “lách” ranh giới bảo mật của lớp lớn.
- Không tự chỉnh class files để kết nối những class không liên quan.
- Test dựa trên hành vi, không phụ thuộc compiler-generated names hay giả định “không bao giờ có synthetic fields”.

## 13. Những lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| Nest là một từ khóa Java 11. | Không có từ khóa `nest` trong Java source. | Nest là cơ chế JVM/class file. |
| Nestmates xuất hiện vì cùng tên có `$`. | Tên có `$` không chứng minh metadata hợp lệ. | Kiểm tra `getNestHost`/`isNestmateOf` hoặc `javap`. |
| Static nested class không đọc được bất cứ private field nào của outer. | Nó có thể dùng **outer object tường minh**. | Phân biệt private access với enclosing instance. |
| Static nested class luôn có `Outer.this`. | Nó không có enclosing instance. | Truyền `Outer` qua tham số nếu cần. |
| Inner class và static nested class đều cần `outer.new Inner()`. | Chỉ non-static member inner mới cần outer instance theo cú pháp đó. | Static nested dùng `new Outer.Nested()` khi được phép. |
| Nestmate có nghĩa luôn cùng object outer. | Nest là quan hệ **cấp class**, không phải object. | Hai inner objects có outer instance khác nhau vẫn thuộc cùng nest. |
| `extends` hoặc `implements` tự tạo nestmates. | Kế thừa và triển khai interface là quan hệ khác. | Nest dựa trên host/member metadata. |
| Tất cả top-level classes trong cùng file cùng nest. | Mỗi top-level type thường là host riêng. | Cùng tệp/package không cấp private access. |
| Nested interface là non-static inner interface. | Nested interfaces implicitly static. | Không có enclosing interface instance. |
| Class trong interface không thuộc nest vì implicit static. | Staticness không ngăn nest membership. | Member class/interface vẫn có thể cùng nest host. |
| Implement interface thì đọc được private methods của interface. | Không phải mọi implementation đều là nestmate. | Chỉ những quyền source/runtime hợp lệ mới được cấp. |
| `getDeclaringClass` luôn bằng `getNestHost`. | Deep nested member có declaring trực tiếp khác host. | Dùng đúng API cho mục đích. |
| `getEnclosingClass` có nghĩa object giữ enclosing instance. | Static nested type vẫn có enclosing class. | Phân biệt declaration và instance. |
| `getNestMembers` có thứ tự ổn định. | Các member sau host không bảo đảm thứ tự. | Kiểm tra bằng tập hợp/contains. |
| Java 11 làm private thành public trong bytecode. | Nestmates được JVM cho private access trực tiếp. | Private vẫn private với code ngoài nest. |
| Java 11 đã xóa mọi synthetic members. | Cơ chế synthetic còn có những mục đích khác. | JEP 181 loại nhu cầu bridge accessor cho private nestmate access. |
| Cùng module là đủ để đọc private. | Module không đồng nghĩa nest. | Module access và nest access có chức năng khác nhau. |

## 14. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Nest-based access trong Java 11 là tính năng của Java source hay JVM?

**Đáp án:** Chủ yếu là **JVM/class file mechanism** (JEP 181). Ngữ nghĩa Java source đối với truy cập private trong các kiểu lồng đã tồn tại; Java 11 cho phép JVM thực hiện kiểm tra trực tiếp theo nest metadata.

**Câu 2.** Static nested class có thể đọc private instance field của outer không?

**Đáp án:** Có, **nếu có tham chiếu outer instance tường minh** và quyền source hợp lệ. Nó không tự có `Outer.this`.

**Câu 3.** Một non-static member inner class có bắt buộc cùng object outer với mọi instance khác của nó không?

**Đáp án:** Không. Các instance inner có thể gắn với các outer objects khác nhau. Nest membership của **kiểu class** không phụ thuộc object cụ thể.

**Câu 4.** Hai member `Outer.A` và `Outer.B` có thể là nestmates nếu A là static nested, B là inner class không?

**Đáp án:** Có. `static`/non-static không phải tiêu chí xác định nest host.

**Câu 5.** Một local class có `getDeclaringClass()==null`. Điều đó có nghĩa không thể là nestmate của outer không?

**Đáp án:** Không. Local class không phải member class nên declaring class null, nhưng có enclosing class và có thể cùng nest host.

**Câu 6.** Tại sao `Policy.Member` trong ví dụ được báo `interfaceStatic=true`?

**Đáp án:** Class là member của interface, nên **implicitly public static** theo JLS Java 11; không cần một instance interface bao ngoài.

**Câu 7.** Class bên ngoài `implements Policy` có tự được đọc `Policy.privateRule()` không?

**Đáp án:** Không. `implements` không tạo nestmate; private method cũng không là API công khai cho implementing class.

**Câu 8.** Hai top-level classes ở cùng source file có tự là nestmates không?

**Đáp án:** Không. Trong mô hình biên dịch Java thông thường, chúng thuộc các nests riêng, trừ trường hợp bytecode đặc biệt được cấu trúc hợp lệ theo các ràng buộc JVMS.

**Câu 9.** `Class.getNestMembers()` có phải luôn trả các member theo thứ tự chúng xuất hiện trong source không?

**Đáp án:** Không. Host đứng đầu; thứ tự còn lại không được bảo đảm. Không dựa vào index.

**Câu 10.** Hai type có cùng superclass thì `isNestmateOf` có luôn true không?

**Đáp án:** Không. Quan hệ subclass/superclass không tự tạo nestmates.

**Câu 11.** Trong Java 11, hai thuộc tính class file chính để ghi nest là gì?

**Đáp án:** **`NestHost`** (ghi host trên member) và **`NestMembers`** (ghi các member được host công nhận).

**Câu 12.** `Class.getEnclosingClass()` trả outer cho static nested class. Có nghĩa nó giữ một outer instance không?

**Đáp án:** Không. Nó chỉ mô tả **kiểu bao ngoài ở cấp khai báo**, không phải state của một object.

**Câu 13.** Nếu chưa thấy synthetic accessor trong `javap` Java 11, có thể suy ra mọi synthetic member đều không tồn tại nữa không?

**Đáp án:** Không. JVM nest-based access giúp không cần bridge accessor cho private nestmate access; các synthetic structures khác vẫn có thể tồn tại.

**Câu 14.** Tại sao bytecode tự sửa `NestHost` không tự động có mọi quyền private?

**Đáp án:** JVMS yêu cầu host/member đồng thuận, cùng runtime package và các điều kiện liên kết/truy cập khác. Không thể giả mạo mối quan hệ bằng cách viết tên host bất kỳ.

**Câu 15.** Khi lựa chọn giữa static nested class và inner class, câu hỏi thực dụng nhất là gì?

**Đáp án:** Class mới có thật sự cần **enclosing instance** không? Nếu không, static nested class/dependency tường minh thường dễ kiểm soát vòng đời hơn. Nestmate private access không quyết định câu hỏi này.

## 15. Tổng kết và tài liệu tham khảo

- Java 11 (JEP 181) cho phép JVM nhận biết **nest host + nest members** để xử lý private access trực tiếp giữa class/interface cùng nest. Quy tắc Java source về nested types **không bị nới rộng**.
- **Static nested class** và **inner member class** đều có thể là nestmates; khác biệt cốt lõi là **enclosing instance**, không phải quyền private do nest.
- **Local/anonymous classes** có thể được `javac --release 11` đưa vào nest của top-level host, dù `getDeclaringClass()` của local/anonymous không như member class.
- **Nested interface** và class/interface bên trong interface **implicitly static** theo JLS. Chúng vẫn có thể là thành viên của cùng nest, và Java 11 hỗ trợ private methods trong interface.
- `extends`, `implements`, cùng package/tệp/module **không tự tạo** nestmates.
- Class file Java 11 (major version 55) có thể dùng **`NestHost`** trên member và **`NestMembers`** trên host. Các thuộc tính này khác `InnerClasses`/`EnclosingMethod`.
- Dùng `Class.getNestHost()`, `getNestMembers()` và `isNestmateOf()` để kiểm tra ở runtime; không suy luận qua tên class chứa `$`.
- Không giả định `getEnclosingClass` nói lên quan hệ object, hoặc `getNestHost` luôn trùng `getDeclaringClass`.
- Nest-based access giúp **giữ private thực sự ở JVM** mà không cần mở rộng quyền bằng bridge accessor cho trường hợp nested private access. Nó không thay thế API design, validation và module encapsulation.

**Tài liệu chính thức, còn áp dụng:**

- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181).
- [Oracle Java SE 11 — Class.getNestHost/getNestMembers/isNestmateOf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html).
- [Java SE 11 — Java Language Specification, `8.1.3 Inner Classes](https://docs.oracle.com/javase/specs/jls/se11/html/jls-8.html#jls-8.1.3).
- [Java SE 11 — JLS `8.5 Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se11/html/jls-8.html#jls-8.5).
- [Java SE 11 — JLS `9.5 Member Type Declarations in Interfaces](https://docs.oracle.com/javase/specs/jls/se11/html/jls-9.html#jls-9.5).
- [Java SE 11 — JVM Specification `4.7.28 NestHost](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28).
- [Java SE 11 — JVM Specification `4.7.29 NestMembers](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29).
- [Oracle JDK 11 Release Notes — JEP 181](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html).