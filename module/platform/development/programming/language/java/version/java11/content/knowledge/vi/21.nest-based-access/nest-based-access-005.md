# Class.getNestHost, getNestMembers, isNestmateOf (Nest-based access, Java 11+)

**Chủ đề cha: Nest-based access.** Java cho phép các lớp lồng nhau và lớp bao ngoài truy cập những thành viên `private` của nhau theo quy tắc ngôn ngữ. Từ **Java 11**, JVM có khái niệm **nest** (*ổ lớp*) để biểu diễn quan hệ này trực tiếp ở mức bytecode, thay vì buộc trình biên dịch tạo những phương thức trung gian mở rộng quyền truy cập. Ba phương thức của `java.lang.Class` giúp quan sát nest ở runtime là **`getNestHost()`, `getNestMembers()` và `isNestmateOf(Class<?>)`**.

Bài học giải thích hợp đồng của từng API, cơ chế `NestHost`/`NestMembers`, quyền truy cập `private`, khác biệt giữa nest và package/kế thừa, trường hợp lớp cục bộ/lớp vô danh, reflection và MethodHandles, cách quan sát bằng `javap`, các ví dụ biên dịch **Java 11+** và bộ regression test. Đây là các API còn được hỗ trợ trong Java hiện đại. Không cần thay đổi cú pháp khai báo nested class quen thuộc để sử dụng tính năng này.

## 1. Nest-based access giải quyết vấn đề gì?

Trong Java, một nested class có thể truy cập thành viên `private` của outer class, và các nested class cùng outer cũng có thể truy cập private members của nhau nếu mã nguồn cho phép.

Ví dụ:

```java
public class Demo {
    private int secret = 42;

    class Reader {
        int read() {
            return secret; // Hợp lệ ở cấp ngôn ngữ Java.
        }
    }
}
```

Về mặt JVM, `Demo` và `Demo$Reader` được biên dịch thành **hai tệp .class riêng**. Trước khi JVM hỗ trợ nest trực tiếp, trình biên dịch phải có cách trung gian để cho phép truy cập private giữa hai class files.

Từ **JEP 181 (Java 11)**:

- JVM hiểu tập các lớp/interface thuộc **cùng một nest**.
- Nestmates được phép truy cập trực tiếp những **private field, method và constructor** của nhau khi việc truy cập hợp lệ.
- Class file của nest host có thể chứa thuộc tính `NestMembers`; các class file thành viên khác có thể chứa `NestHost`.
- `javac` khi biên dịch theo mục tiêu Java 11+ sử dụng những thuộc tính này để biểu diễn quan hệ, không cần tạo access bridge chỉ để vượt rào private giữa các nestmates.
- Quy tắc **cú pháp và kiểm tra quyền truy cập ở mã nguồn Java không thay đổi**: đây chủ yếu là thay đổi ở **JVM/class file** cùng những API quan sát ở runtime.

**Lưu ý:** “Có chung nest” không đồng nghĩa “mọi lớp đều truy cập được private members”. Chỉ các lớp được JVM xác nhận **là nestmates** mới được hưởng cơ chế đó; hai top-level classes cùng package **không tự trở thành nestmates**.

## 2. Nest host và các nest members

Một **nest** có đúng **một nest host**, có thể hiểu là điểm đại diện cho nhóm các class/interface đã được liên kết qua metadata. Với code Java thông thường do `javac --release 11` tạo ra, **top-level class hoặc interface** đóng vai trò host cho các kiểu lồng bên trong nó.

Sơ đồ khái niệm:

```text
TopLevel.class                  <-- nest host
  |
  +-- TopLevel$Reader.class     <-- member, NestHost -> TopLevel
  |
  +-- TopLevel$Writer.class     <-- member, NestHost -> TopLevel
  |
  +-- TopLevel$Nested.class     <-- member, NestHost -> TopLevel
  |
  +-- một số local/anonymous class do compiler sinh
        (nếu được ghi nhận trong NestMembers)
```

Một nest không bắt buộc phải có nhiều lớp:

- Top-level class không có nest members khác tạo thành **singleton nest**: chính nó là host và member duy nhất.
- Nested type thuộc nest có host là outer top-level type tương ứng, theo metadata được JVM xác thực.
- Mọi class/interface đều thuộc **đúng một nest**.
- Một kiểu nguyên thủy (`int.class`, `boolean.class`), `void.class`, hoặc một **array class** (`String[].class`, `Reader[].class`) được coi là singleton nest với chính nó làm host theo API `Class`.

Với reflection, có thể tìm nest host từ **bất kỳ thành viên** nào, không chỉ gọi từ outer class. Sau đó `getNestMembers()` cho ta danh sách members của cùng nest theo runtime.

## 3. API thứ nhất: Class.getNestHost()

Chữ ký, từ Java 11:

```java
public Class<?> getNestHost()
```

**Ý nghĩa:** trả `Class<?>` đại diện cho nest host của class/interface hiện tại.

Ví dụ:

```java
Class<?> host = SomeNestedClass.class.getNestHost();
System.out.println(host.getName());
```

Đây là đoạn minh họa, giả định `SomeNestedClass` là lớp có tồn tại. `getNestHost()` **không trả về `null`** để biểu diễn một class không có outer: trường hợp singleton nest, nó trả về **chính `Class<?>` đang gọi**.

Các trường hợp đáng nhớ:

| Kiểu gọi | Kết quả |
| --- | --- |
| Một top-level class là host | Trả chính top-level class |
| Nested class đã được ghi nhận trong nest | Trả nest host |
| Top-level class không có members khác | Trả chính class đó |
| Array class, ví dụ `String[].class` | Trả chính array class |
| Primitive, ví dụ `int.class` | Trả `int.class` |
| `void.class` | Trả chính `void.class` |

Theo Javadoc Java 11, nếu gặp lỗi linkage khi truy cập nest host hoặc host không liệt kê class đang hỏi là thành viên, `getNestHost()` có thể coi nó là singleton nest và trả chính class đó. Vì vậy **không dùng kết quả suy đoán đơn giản từ tên `$` để thay thế việc xác minh metadata ở runtime**.

Cũng không nên nhầm `getNestHost()` với:

- `getSuperclass()`: quan hệ kế thừa.
- `getEnclosingClass()`: lớp bao ở mức khai báo/lexical.
- `getDeclaringClass()`: lớp/interface trực tiếp khai báo một member class/interface.
- `getPackageName()`: tên package.

Các quan hệ này **không đồng nghĩa** nhau.

## 4. API thứ hai: Class.getNestMembers()

Chữ ký, từ Java 11:

```java
public Class<?>[] getNestMembers()
```

Trả về **mảng các đối tượng `Class<?>`** đại diện cho tất cả thành viên của nest hiện tại, bao gồm **nest host**.

Hợp đồng Java SE 11 có các điểm cần lưu ý:

1. **Phần tử đầu tiên (index 0) là nest host**.
2. Các phần tử sau tương ứng với members đã được host liệt kê; **không có bảo đảm về thứ tự** của những phần tử này.
3. Theo Javadoc 11, **có thể có các phần tử trùng lặp**. Nếu kiểm tra danh sách bằng logic đặc thù, không mặc định mọi member xuất hiện đúng một lần.
4. Gọi `getNestMembers()` trên **một member** vẫn truy xuất danh sách members của **toàn nest**, không chỉ các lớp trực tiếp lồng bên trong member đó.
5. Với singleton nest (bao gồm array/primitive/void), kết quả là mảng **một phần tử** chứa chính class tương ứng.
6. Việc tải/kiểm tra các class được ghi trong thuộc tính nest có thể phát sinh **`LinkageError`** nếu classfile hoặc dependencies không đồng bộ. Javadoc công bố khả năng lỗi này; không coi việc enumerate metadata là hoàn toàn không thể thất bại.

Điều quan trọng: **không viết test** `getNestMembers()[1] == Expected.class` chỉ vì trên máy mình thành viên đó đứng thứ hai. Nếu cần in danh sách có thứ tự, tự **sắp xếp theo tên**; nếu kiểm tra membership, dùng điều kiện chứa phần tử.

### getNestMembers và getDeclaredClasses khác nhau

| API | Nội dung quan sát |
| --- | --- |
| `getDeclaredClasses()` | Member classes/interfaces **được khai báo trực tiếp** bên trong lớp đang xét |
| `getNestMembers()` | Nest host và các class/interface trong **toàn nest** theo metadata |
| `getNestHost()` | Một `Class<?>` là host, không phải danh sách |
| `getEnclosingClass()` | Lớp khai báo bao ngoài của một loại nested/local/anonymous type theo metadata tương ứng |

Ví dụ, `getDeclaredClasses()` không dùng để liệt kê local/anonymous classes được tạo trong phương thức; còn `getNestMembers()` phản ánh các thành viên được javac ghi vào nest, **không phải cây cấu trúc source code hoặc danh sách subclasses**.

## 5. API thứ ba: Class.isNestmateOf(Class<?> c)

Chữ ký, từ Java 11:

```java
public boolean isNestmateOf(Class<?> c)
```

Trả `true` nếu class/interface hiện tại và `c` có **cùng nest host**.

```text
a.isNestmateOf(b)
    -> true  khi a và b thuộc cùng một nest
    -> false nếu thuộc hai nest khác nhau
```

Các tính chất:

- Một class là nestmate của **chính nó**: `A.class.isNestmateOf(A.class) == true`.
- Hai nested classes dưới cùng host có thể là nestmates của nhau dù **không có quan hệ kế thừa**.
- Một nested class và outer host của nó có thể là nestmates.
- Hai top-level classes khác nhau **không tự thành nestmates** chỉ vì nằm cùng package.
- Một subclass **không tự trở thành nestmate** của superclass. Inheritance và nest membership là hai cơ chế khác nhau.
- Một array class được xem là singleton nest. Ví dụ `Box[].class.isNestmateOf(Box.class)` là `false` dù tên array chứa tên component.
- Kiểu nguyên thủy và array phản ánh chính `Class<?>` của chúng; không suy từ kiểu phần tử hay tên package.

**Câu hỏi tự kiểm tra:** Nếu `A.class.isNestmateOf(B.class)` là `true`, có đủ chứng minh `A` được JVM cho phép truy cập private members của `B` theo quy tắc nestmate không? Về mặt **nest membership**, có. Tuy nhiên **không có nghĩa** chương trình có thể tùy tiện truy cập thành viên qua bất kỳ cách gọi nào mà bỏ qua các điều kiện khác như access to class, module visibility, khả năng xác minh bytecode hay điều kiện của API reflection.

## 6. Chương trình chạy được: ba API và truy cập private

Tạo tệp **`NestApiBasics.java`** với đúng tên public class:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestApiBasics {
    static final class Vault {
        private int secret = 7;
    }

    static final class Auditor {
        static int read(Vault box) {
            return box.secret;      // Truy cập private của sibling.
        }

        static void increase(Vault box) {
            box.secret += 4;        // Có thể ghi private field.
        }
    }

    public static void main(String[] args) {
        Vault box = new Vault();

        System.out.println("host itself: "
                + (NestApiBasics.class.getNestHost()
                   == NestApiBasics.class));
        System.out.println("vault host: "
                + Vault.class.getNestHost().getSimpleName());
        System.out.println("siblings: "
                + Auditor.class.isNestmateOf(Vault.class));
        System.out.println("member and host: "
                + Vault.class.isNestmateOf(NestApiBasics.class));
        System.out.println("self: "
                + Vault.class.isNestmateOf(Vault.class));

        Class<?>[] members = Vault.class.getNestMembers();
        System.out.println("host first: "
                + (members[0] == NestApiBasics.class));

        String sorted = Arrays.stream(members)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println("members sorted: " + sorted);

        System.out.println("private before: " + Auditor.read(box));
        Auditor.increase(box);
        System.out.println("private after: " + Auditor.read(box));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 -encoding UTF-8 NestApiBasics.java
java NestApiBasics
```

Stdout với chương trình như trên:

```text
host itself: true
vault host: NestApiBasics
siblings: true
member and host: true
self: true
host first: true
members sorted: Auditor, NestApiBasics, Vault
private before: 7
private after: 11
```

**Diễn giải:**

- `Vault` và `Auditor` là hai static nested classes nhưng có **cùng host** `NestApiBasics`.
- Phương thức `Auditor.read` truy cập trực tiếp private field của `Vault`, không cần biến field thành `public` hay `protected`.
- Gọi `Vault.class.getNestMembers()` vẫn trả danh sách của **toàn nest**.
- Chúng ta sắp xếp tên trước khi in, vì chỉ có **host ở index 0** được bảo đảm; thứ tự những thành viên khác không cố định theo contract.
- Kết quả chỉ phụ thuộc cấu trúc các lớp được biên dịch từ **đúng tệp ví dụ**. Nếu công cụ weaving/instrumentation tạo thêm thành viên nest, danh sách có thể khác.
- Mã dùng `Collectors.joining(", ")` vì tương thích với Java 11; không dùng `Stream.toList()` vốn được thêm sau Java 11.

## 7. Nest không phải package, subclass hay array component

Chương trình sau cố ý tạo **hai top-level classes** trong cùng một source file và cùng default package: `NestBoundaries` và `Peer`. Chúng **không cùng nest**, dù chia sẻ một số điều kiện biên dịch/package.

### Tệp `NestBoundaries.java`

```java
import java.util.Arrays;

public class NestBoundaries {
    static final class Member {
    }

    public static void main(String[] args) {
        System.out.println("nested with host: "
                + Member.class.isNestmateOf(NestBoundaries.class));

        System.out.println("same package, different host: "
                + Member.class.isNestmateOf(Peer.class));

        System.out.println("peer singleton host: "
                + (Peer.class.getNestHost() == Peer.class));

        System.out.println("array singleton host: "
                + (Member[].class.getNestHost() == Member[].class));

        System.out.println("member and array nestmates: "
                + Member[].class.isNestmateOf(Member.class));

        System.out.println("primitive singleton host: "
                + (int.class.getNestHost() == int.class));

        System.out.println("nest includes host: "
                + Arrays.asList(NestBoundaries.class.getNestMembers())
                        .contains(NestBoundaries.class));

        System.out.println("declared classes versus nest: "
                + (NestBoundaries.class.getDeclaredClasses().length == 1
                   && NestBoundaries.class.getNestMembers().length == 2));
    }
}

class Peer {
}
```

```bash
javac --release 11 -encoding UTF-8 NestBoundaries.java
java NestBoundaries
```

```text
nested with host: true
same package, different host: false
peer singleton host: true
array singleton host: true
member and array nestmates: false
primitive singleton host: true
nest includes host: true
declared classes versus nest: true
```

**Vì sao ví dụ có giá trị?**

1. `Peer` và `NestBoundaries` là hai top-level classes, dù trong cùng file và package: **khác host**.
2. `Member[].class` là **array type riêng**, không được coi là `Member.class` khi kiểm tra nestmate.
3. `getDeclaredClasses()` của `NestBoundaries` chỉ có `Member`, còn `getNestMembers()` gồm **host và Member**. Hai tập này khác nhau ngay cả với ví dụ đơn giản.
4. `getNestHost()` của kiểu nguyên thủy luôn là kiểu đó; không có outer host theo tên hay một “package mặc định” của primitive.

Mở rộng: nếu một class ngoài nest `extends` `Peer` hoặc `Member` (nếu không final), việc kế thừa **không khiến class con tự động chung host** với class cha. Quyền truy cập `private` không tự kế thừa chỉ vì quan hệ extends.

## 8. Lớp thường, lớp cục bộ và lớp vô danh cùng nest

Ngoài static member class, javac Java 11 cũng tạo nest metadata cho **non-static inner class**, **local class** và **anonymous class** được khai báo bên trong top-level type. Tên nhị phân của local/anonymous classes do compiler tạo (ví dụ có chữ số hoặc ký tự `$`) không phải thứ nên hard-code để nhận diện nest.

### Tệp `LocalNestDemo.java`

```java
public class LocalNestDemo {
    private final int pin = 42;

    class Inner {
        int readPin() {
            return pin;
        }
    }

    Object makeLocal() {
        class Local {
            @Override
            public String toString() {
                return "local-" + pin;
            }
        }
        return new Local();
    }

    Object makeAnonymous() {
        return new Object() {
            @Override
            public String toString() {
                return "anonymous-" + pin;
            }
        };
    }

    public static void main(String[] args) {
        LocalNestDemo outer = new LocalNestDemo();
        Inner inner = outer.new Inner();
        Object local = outer.makeLocal();
        Object anonymous = outer.makeAnonymous();

        System.out.println("inner reads private: " + inner.readPin());
        System.out.println("inner host: "
                + (inner.getClass().getNestHost() == LocalNestDemo.class));
        System.out.println("local host: "
                + (local.getClass().getNestHost() == LocalNestDemo.class));
        System.out.println("anonymous host: "
                + (anonymous.getClass().getNestHost()
                   == LocalNestDemo.class));
        System.out.println("local and anonymous nestmates: "
                + local.getClass().isNestmateOf(anonymous.getClass()));
        System.out.println(local);
        System.out.println(anonymous);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 LocalNestDemo.java
java LocalNestDemo
```

```text
inner reads private: 42
inner host: true
local host: true
anonymous host: true
local and anonymous nestmates: true
local-42
anonymous-42
```

Chương trình không phụ thuộc tên sinh ra như `LocalNestDemo$1Local` hoặc `LocalNestDemo$1`. Kiểm tra bằng **Class object** và `getNestHost/isNestmateOf` mới là cách đáng tin.

**Điểm dễ nhầm:** `getNestMembers` không phải một API để lấy toàn bộ instance nội bộ của outer object. Nó chỉ mô tả **các kiểu (class/interface)** theo metadata của JVM, không chứa danh sách object được tạo. Một nested type trong cùng nest có thể có nhiều instance, hoặc không có instance nào.

## 9. Reflection: private access giữa nestmates

JEP 181 cũng đưa quan hệ nest vào cơ chế kiểm tra quyền truy cập của **core reflection** và `MethodHandles.Lookup`. Trong một nest hợp lệ, mã của một nestmate có thể truy cập private member của nestmate khác theo luật quyền truy cập của Java.

Quan trọng: `getDeclaredField("secret")` **chỉ tìm thấy field**, không tự bỏ qua mọi kiểm soát access. Lời gọi `Field.get(...)` còn kiểm tra quyền của caller. Caller khác nest có thể bị từ chối. `setAccessible(true)` là một cơ chế reflection riêng, chịu giới hạn của modules và các chính sách; **không cần dùng** để minh họa nestmate access hợp lệ.

### Ví dụ hoàn chỉnh: `NestReflectionDemo.java`

```java
import java.lang.reflect.Field;

public class NestReflectionDemo {
    static final class SecretBox {
        private final String value = "ok";
    }

    static final class Auditor {
        static String readPrivate(SecretBox box) throws Exception {
            Field field = SecretBox.class.getDeclaredField("value");
            // Không cần field.setAccessible(true):
            // Auditor và SecretBox là nestmates.
            return (String) field.get(box);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretBox box = new SecretBox();
        System.out.println("nestmates: "
                + Auditor.class.isNestmateOf(SecretBox.class));
        System.out.println("nested reflection: "
                + Auditor.readPrivate(box));
        System.out.println("outside access denied: "
                + OutsideReader.denied(box));
    }
}

class OutsideReader {
    static boolean denied(NestReflectionDemo.SecretBox box)
            throws Exception {
        Field field = NestReflectionDemo.SecretBox.class
                .getDeclaredField("value");
        try {
            field.get(box);
            return false;
        } catch (IllegalAccessException expected) {
            return true;
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NestReflectionDemo.java
java NestReflectionDemo
```

```text
nestmates: true
nested reflection: ok
outside access denied: true
```

Vì `Auditor` nằm trong cùng nest với `SecretBox`, việc đọc private field qua reflection từ Auditor là hợp lệ, **không cần bật suppression của Java language access check**. `OutsideReader` là một top-level class khác, ở cùng package nhưng **không phải nestmate**, nên lời gọi `Field.get` của nó bị từ chối bởi `IllegalAccessException`.

Một vài lưu ý:

- Kết quả này áp dụng với classfiles **được javac biên dịch theo Java 11** như lệnh trong bài.
- Nếu class bên ngoài cố gọi `setAccessible(true)`, đó là chủ đề **deep reflection** với các quy tắc module riêng; không coi nó như bằng chứng class ấy là nestmate.
- Không đưa mẫu reflection vào sản phẩm chỉ để thay một lời gọi Java bình thường khi không cần thiết. Nếu có quyền truy cập qua mã nguồn, cách thông thường đơn giản và dễ bảo trì hơn.

## 10. MethodHandles.Lookup cũng nhận biết quyền nestmate

Với `java.lang.invoke.MethodHandles.Lookup`, khả năng tìm handle tới private member phụ thuộc vào **lookup class và quyền truy cập**. Lookup do mã trong một nestmate tạo ra có thể truy cập private method của nestmate khác khi điều kiện lookup hợp lệ.

### Tệp `NestMethodHandleDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class NestMethodHandleDemo {
    static final class Target {
        private String message() {
            return "secret-method";
        }
    }

    static final class Accessor {
        static String call(Target target) throws Throwable {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodHandle handle = lookup.findVirtual(
                    Target.class, "message",
                    MethodType.methodType(String.class));
            return (String) handle.invokeExact(target);
        }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("nestmate lookup: "
                + Accessor.class.isNestmateOf(Target.class));
        System.out.println("private method: "
                + Accessor.call(new Target()));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NestMethodHandleDemo.java
java NestMethodHandleDemo
```

```text
nestmate lookup: true
private method: secret-method
```

**Giải thích:** `MethodHandles.lookup()` được gọi **bên trong `Accessor`**, nên lookup mang quyền của class đó. Do `Accessor` và `Target` cùng nest, `findVirtual` có thể tìm private method hợp lệ. `invokeExact` yêu cầu kiểu tham số/trả về chính xác theo descriptor; ví dụ dùng `Target` và `String` đúng kiểu.

Đừng chuyển kết luận thành “mọi `MethodHandles.lookup()` đều truy cập private của mọi class”. Một lookup được tạo ở class khác (không cùng nest) không có quyền tương đương; lookup còn có các giới hạn access/module riêng.

## 11. NestHost và NestMembers trong .class: xem bằng javap

Nền tảng cơ chế là **hai attributes** của class file Java 11+:

- **`NestHost`:** class/interface thành viên chỉ ra nest host của nó.
- **`NestMembers`:** nest host liệt kê các class/interface được ghi nhận là members của nest.
- JVM sử dụng metadata này để kiểm tra quyền private. Tên chứa `$`, cùng tên package hoặc chỉ có khai báo lồng trong source **không tự là chứng chỉ hợp lệ** nếu metadata và runtime không thống nhất.

Lệnh quan sát với **ví dụ `NestApiBasics.java`** đã tạo ở mục 6:

```bash
javac --release 11 -encoding UTF-8 NestApiBasics.java
javap -v -p NestApiBasics
javap -v -p 'NestApiBasics$Vault'
javap -c -p 'NestApiBasics$Auditor'
```

Gợi ý đọc output (không phải bản chép nguyên văn đầy đủ của javap):

```text
NestApiBasics.class:
    ... NestMembers: ...
    ... NestApiBasics$Auditor ...
    ... NestApiBasics$Vault ...

NestApiBasics$Vault.class:
    ... NestHost: class NestApiBasics ...

NestApiBasics$Auditor.class:
    ... getfield NestApiBasics$Vault.secret ...
```

Một số chi tiết của bản in `javap` như thứ tự constant pool, index, descriptor hay cú pháp annotation có thể khác giữa các JDK. Bạn nên tìm **tên attribute và quyền truy cập thực tế**, không so sánh toàn bộ output thành chuỗi cố định.

**Vì sao có dấu `$`?** Đây là quy ước thường thấy trong *binary name* của nested classes do javac tạo, không phải công thức xác định nestmate trong Java. Nest membership là quan hệ được JVM xác thực từ classfile attributes.

### Bytecode mới và các artifact cũ

JEP 181 áp dụng cho **class file version 55.0 trở lên** (tương ứng Java 11). Nếu một thư viện vẫn chứa classfiles được biên dịch với target cũ, có thể không có `NestHost/NestMembers` và JVM quan sát nó là **singleton nest**, dù Java source trước đây có inner/outer relationship. Mã kiểu cũ có thể vẫn hoạt động nhờ những phương thức do compiler tạo khi biên dịch trước đó.

Điều này vẫn đáng biết hiện nay khi:

- Phân tích một JAR chứa các classfiles được build bằng nhiều target khác nhau.
- Chạy code đã được compiler/plugin bytecode transform.
- Chẩn đoán lỗi giữa nested classes được đóng gói và triển khai không đồng bộ.
- Di chuyển công cụ phân tích bytecode/coverage/obfuscation sang runtime Java mới.

Không có nghĩa phải quay lại dùng kỹ thuật synthetic accessor của các compiler cũ cho code mới. **Với source code Java 11+ và toolchain được hỗ trợ, để compiler/JVM quản lý nest metadata.**

## 12. Class loader, module và tính hợp lệ của nest

Một nest hợp lệ ở runtime không được tạo ra chỉ bằng cách viết lại tên tùy ý:

1. Nest host và members phải có **metadata phù hợp và nhất quán**: member chỉ host, host liệt kê member.
2. Nestmates phải nằm trong cùng **runtime package**; theo JVM, runtime package bao gồm **tên package và defining class loader** phù hợp. Một class tải bởi class loader khác không tự được xem là nestmate chỉ vì có tên package giống nhau.
3. Việc load và xác thực nest membership có thể dẫn đến **lỗi linkage** nếu attributes không hợp lệ hoặc class tương ứng không thể load/validate.
4. Private nestmate access không mở rộng tùy ý ranh giới module hoặc export/open packages. Các quy tắc module và lookup/reflection khác vẫn có hiệu lực.
5. Obfuscator/shader/bytecode enhancer/agent cần giữ hoặc cập nhật **cả hai phía** của metadata nest khi đổi tên class, di chuyển package, đổi loader hay sửa classfiles.

Ví dụ, nếu một tool đổi tên `Outer$Inner` nhưng quên cập nhật `NestMembers` của `Outer` hoặc `NestHost` của Inner, runtime có thể không xác nhận được hai class là nestmates. Hệ quả không chỉ là tên in ra khác: có thể có `LinkageError` hoặc lỗi access khi JVM phải resolve private field/method.

**Không** xây “friend class” để vượt module/package bằng cách thủ công sửa `NestHost` từ một JAR bên ngoài rồi cho rằng JVM sẽ chấp nhận. Mối quan hệ nest có các điều kiện xác minh, không chỉ là một chuỗi tên trong file.

## 13. Các trường hợp đặc biệt và giới hạn quan sát

### 13.1. Primitive, void và array là singleton nests

Các kiểu sau không là nestmate chỉ vì có liên hệ phần tử/component:

```java
int.class.getNestHost() == int.class
String[].class.getNestHost() == String[].class
String[].class.isNestmateOf(String.class) == false
```

Đây là các biểu thức minh họa. `getNestMembers()` của primitive/void/array trả một mảng chứa chính `Class<?>` đó. Tương tự, `int.class.isNestmateOf(long.class)` là `false`.

### 13.2. Local/anonymous classes không nên kiểm tra theo tên

Javac có thể tạo nhiều classfiles cho local/anonymous implementations. Thứ tự `getNestMembers()` và phần tên sinh ra không nên bị dùng làm API business logic.

Để kiểm tra một class cụ thể có thuộc nest nào, dùng:

```java
boolean sameNest = instance.getClass()
        .isNestmateOf(Outer.class);
```

Đây là đoạn minh họa, biến `instance` và type `Outer` được khai báo ở phạm vi tương ứng.

### 13.3. Hidden classes (Java 15+) khác với NestMembers có sẵn trong classfile

Trên Java mới hơn, `MethodHandles.Lookup.defineHiddenClass(...)` có thể tạo hidden class và tùy chọn `ClassOption.NESTMATE` để tham gia nest theo những điều kiện của API. Nhưng một hidden class được **định nghĩa động** không nhất thiết được liệt kê trong thuộc tính `NestMembers` tĩnh của host. Không dùng `getNestMembers()` để suy ra *mọi class đã từng được định nghĩa động tại runtime*.

Lưu ý phiên bản: `defineHiddenClass` là API bổ sung từ **Java 15**, không có trong source tương thích `--release 11`. Vấn đề này chỉ có ích khi phân tích framework/runtime hiện đại dùng lambda proxies hoặc công cụ bytecode động.

### 13.4. Không dùng getNestMembers làm công cụ quét toàn classpath

`getNestMembers()` chỉ trả những members của **một nest xác định**, không liệt kê package/module/classpath, không tìm tất cả subclasses và cũng không liệt kê toàn bộ classfiles đã load vào JVM. Nó có thể kích hoạt việc tải/validate thêm classfiles; trong code framework có thể cần xử lý `LinkageError` theo chính sách.

## 14. Ứng dụng thực tế của ba API

- **Công cụ reflection / debug:** xác định vì sao mã từ một nested class truy cập private của sibling được JVM cho phép hoặc bị từ chối.
- **Phân tích bytecode:** liên hệ `NestHost` và `NestMembers` khi đọc output của `javap`, ASM hoặc Byte Buddy; xác thực tool không làm hỏng metadata.
- **Kiểm thử build target:** kiểm tra classfiles Java 11+ được build bằng flags đúng và list members hợp lệ.
- **Chẩn đoán `IllegalAccessError`:** khi lỗi chỉ xuất hiện sau obfuscation hoặc đóng gói lại JAR, kiểm tra nest attributes, class loader và phiên bản classfile.
- **Cơ chế MethodHandles/reflection:** giải thích những lookup hợp lệ giữa nestmates và những lookup bị hạn chế bởi class/module.
- **Giáo dục Java language vs JVM:** phân biệt kiểm tra truy cập ở source level với classfile access control và các API quan sát runtime.

Ngược lại, **không nên** sử dụng `isNestmateOf` như một cơ chế **authorization người dùng** hay kiểm tra tin cậy mã nguồn từ bên ngoài. Nest là khái niệm **quan hệ các class nội bộ trong JVM**, không trả lời ai được phép truy cập một tài khoản, dữ liệu khách hàng hay endpoint.

## 15. Bộ regression test Java 11 không cần thư viện

Bộ test xác minh nhiều loại nest member (static class, inner class, interface), tính đối xứng của quan hệ host, khác biệt với class không liên quan và singleton nests. Dùng `AssertionError` trực tiếp để tất cả các điều kiện luôn chạy; không phụ thuộc cờ JVM `-ea`.

### Tệp `NestApiRegression.java`

```java
import java.util.Arrays;

public class NestApiRegression {
    private int secret = 5;

    static final class A {
        static int read(NestApiRegression owner) {
            return owner.secret;
        }
    }

    static final class B {
    }

    class C {
    }

    interface Marker {
    }

    private static int count;

    static void check(String label, boolean success) {
        count++;
        if (!success) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        NestApiRegression owner = new NestApiRegression();

        check("host itself",
                NestApiRegression.class.getNestHost()
                        == NestApiRegression.class);
        check("A host",
                A.class.getNestHost() == NestApiRegression.class);
        check("B host",
                B.class.getNestHost() == NestApiRegression.class);
        check("C host",
                C.class.getNestHost() == NestApiRegression.class);
        check("interface host",
                Marker.class.getNestHost() == NestApiRegression.class);

        check("A and B",
                A.class.isNestmateOf(B.class));
        check("A and C",
                A.class.isNestmateOf(C.class));
        check("A and host",
                A.class.isNestmateOf(NestApiRegression.class));
        check("self",
                A.class.isNestmateOf(A.class));
        check("unrelated class",
                !A.class.isNestmateOf(String.class));

        check("private access",
                A.read(owner) == 5);

        Class<?>[] members =
                NestApiRegression.class.getNestMembers();
        check("host index 0",
                members[0] == NestApiRegression.class);
        check("member A",
                Arrays.asList(members).contains(A.class));
        check("member B",
                Arrays.asList(members).contains(B.class));
        check("member C",
                Arrays.asList(members).contains(C.class));
        check("member interface",
                Arrays.asList(members).contains(Marker.class));
        check("member can list host",
                Arrays.asList(A.class.getNestMembers())
                        .contains(NestApiRegression.class));

        check("array is singleton",
                A[].class.getNestHost() == A[].class
                && A[].class.getNestMembers().length == 1);
        check("primitive is singleton",
                int.class.getNestHost() == int.class
                && int.class.getNestMembers().length == 1);

        System.out.println("PASS: " + count + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NestApiRegression.java
java NestApiRegression
```

```text
PASS: 19 checks
```

**Đếm:** 5 điều kiện host, 5 điều kiện nestmate (A/B, A/C, A/host, self, unrelated), 1 kiểm tra private access, 6 điều kiện host/members (host index, A, B, C, Marker, truy xuất từ A), 2 điều kiện singleton = **19**.

Nếu có điều kiện sai, `check` ném `AssertionError` kèm nhãn, không báo `PASS`. Bộ test cố ý không so sánh thứ tự members ngoài index 0; cách đó đúng với Javadoc.

**Giới hạn:** Test này chạy với các classfiles **do cùng một lệnh `javac --release 11` tạo ra** và một class loader thông thường. Nó không kiểm tra bytecode bị thao tác sai, loader khác nhau, hidden classes, module boundaries hoặc mọi lỗi linkage. Với dự án dùng shading/obfuscation, hãy bổ sung integration tests trên artifact **sau đóng gói**, không chỉ trên classfiles từ thư mục build.

## 16. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `getNestHost()` không có host thì trả `null` | Singleton nest có host chính nó | So sánh `cls.getNestHost() == cls` |
| `getNestMembers()` chỉ trả nested classes, không có host | Phần tử 0 chính là host | Bao gồm host khi thống kê |
| Tất cả members có thứ tự cố định | Sau host, thứ tự không bảo đảm | Sắp xếp theo tên hoặc dùng membership check |
| Hai class cùng package sẽ là nestmates | Package ≠ nest | Dùng `isNestmateOf` và metadata |
| Subclass tự hưởng private access của nest | Inheritance ≠ nest membership | Phân biệt hai quan hệ |
| `String[].class` và `String.class` là nestmates | Array là singleton nest riêng | Kiểm tra kiểu `Class<?>` thực |
| Tên có `$` chắc chắn là nestmate | Tên không chứng minh metadata hợp lệ | `getNestHost/isNestmateOf` |
| `getNestMembers` trả tất cả subclasses | API chỉ trả nest members | Dùng cơ chế quét hierarchy riêng khi thật sự cần |
| `getDeclaredClasses` tương đương `getNestMembers` | Một bên là direct member types, bên kia là nest | Chọn API đúng ý định |
| Reflection thấy private là được đọc ngay từ mọi nơi | Quyền truy cập vẫn được kiểm tra theo caller | Tôn trọng access/module rules |
| Đổi tên classfiles nhưng không sửa nest attributes | Có thể tạo lỗi linkage/access | Dùng build/bytecode tooling tương thích |
| Test dựa vào tên local/anonymous do compiler sinh | Tên có thể khác giữa toolchains | So sánh Class objects và host |
| Dùng nest như xác thực user/tenant | Nest là cấu trúc JVM, không phải auth policy | Kiểm soát quyền ở tầng ứng dụng |

## 17. Câu hỏi tự luyện và đáp án

**1.** Nếu `Inner.class.getNestHost() == Outer.class`, có thể nói `Inner` thuộc nest do `Outer` làm host không?

**2.** `Outer.class.getNestMembers()` có bao gồm chính `Outer.class` không? Nó nằm ở vị trí nào theo Java 11?

**3.** Hai nested classes khác nhau cùng host có nhất thiết là quan hệ subclass/superclass không?

**4.** Hai top-level classes trong cùng package và cùng JAR có tự là nestmates không?

**5.** `int.class.getNestHost()` và `int[].class.getNestHost()` trả gì?

**6.** Khi một local class được compiler đặt tên nhị phân chứa `$1Local`, chỉ nhìn tên này có đủ chứng minh nó là nestmate không?

**7.** `getNestMembers()[1]` có được bảo đảm luôn là static nested class khai báo đầu tiên không?

**8.** Một `Field.get(...)` đối với private field khác nest có tự được phép chỉ nhờ `getDeclaredField(...)` không?

**9.** Từ Java 11, vì sao compiler không cần thêm phương thức trung gian chỉ để nested class gọi private member của outer class?

**10.** `getNestMembers()` có thể phát sinh lỗi khi classfiles ghi nhận thành viên bị thiếu hoặc không hợp lệ không?

**Đáp án:**

1. **Có**, với metadata/runtime đã được JVM xác định như thế.
2. **Có**; host là **phần tử 0**.
3. **Không**; cùng nest là quan hệ quyền access, không phải inheritance.
4. **Không**; cùng package/JAR không tự tạo nest.
5. `int.class` trả **chính int.class**, còn `int[].class` trả **chính int[].class**; đó là các singleton nests riêng.
6. **Không**; dùng `getNestHost()`/`isNestmateOf()`.
7. **Không**; chỉ index 0 được cố định, thứ tự thành viên sau đó không bảo đảm.
8. **Không**; reflection vẫn kiểm tra quyền truy cập, trừ khi dùng cơ chế truy cập riêng hợp lệ theo module/policy.
9. **JEP 181** cho phép JVM xác thực và cấp quyền private giữa nestmates qua `NestHost/NestMembers`.
10. **Có**; Javadoc cho phép `LinkageError` khi load/validate nest member có vấn đề.

## 18. Checklist áp dụng

- **Chọn đúng API:** host → `getNestHost()`; danh sách → `getNestMembers()`; quan hệ giữa hai kiểu → `isNestmateOf(...)`.
- **Nhớ singleton:** primitive/void/array/top-level độc lập có host là chính mình.
- **Nhớ thứ tự:** host ở phần tử 0, phần còn lại không được hứa thứ tự và có thể có phần tử trùng.
- **Nhớ phạm vi:** cùng package, cùng JAR, cùng superclass hoặc tên có `$` không chứng minh nest.
- **Đọc classfile khi cần:** `javap -v -p` để xem `NestHost`/`NestMembers`; `javap -c` để quan sát private field/method access.
- **Giữ build đồng bộ:** không kết hợp classfiles bị obfuscate/rewrite không tương thích; kiểm tra sau đóng gói.
- **Không lạm dụng reflection:** nestmate access giúp giải thích quyền private, không phải một cách để bỏ kiểm soát modules.
- **Không dùng nest như auth:** đây là cơ chế quan hệ lớp trong JVM.
- **Test đa cấp:** có lớp host, member, local/anonymous, unrelated same package, singleton arrays/primitive và test chạy trong artifact cuối.
- **Tính tương thích:** API tồn tại từ Java 11 và tiếp tục được hỗ trợ trong Java hiện đại; mã Java 11 có thể dùng chúng trực tiếp với `javac --release 11`.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 181 — Nest-Based Access Control (Java 11)](https://openjdk.org/jeps/181).
- [Java SE 11 — java.lang.Class: getNestHost, getNestMembers, isNestmateOf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html).
- [Java SE 26 — Class: các API nest tiếp tục được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html).
- [Java SE 11 — Java Virtual Machine Specification: NestHost, NestMembers, access control](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html).
- [Java SE 11 — JVMS §5.4.4: Access Control](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4).
- [Java SE 11 — javap command](https://docs.oracle.com/en/java/javase/11/tools/javap.html).
- [Java SE 11 — MethodHandles.Lookup: private/member access](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
