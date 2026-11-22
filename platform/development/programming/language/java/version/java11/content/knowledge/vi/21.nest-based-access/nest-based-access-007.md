# Ranh giới package, class loader và nest hợp lệ — Java 11 Nest-Based Access

## Mục tiêu

Từ **Java 11**, JVM hỗ trợ **nest-based access control** theo **JEP 181**. Một *nest* là tập hợp các lớp và interface được JVM công nhận là có quan hệ thân cận, nên có thể truy cập các thành viên **`private`** của nhau khi kiểm tra quyền truy cập ở cấp bytecode. Ví dụ thường gặp nhất là một lớp ngoài và các lớp/interface lồng bên trong được `javac` biên dịch cùng nhau.

Chủ đề quan trọng của bài này không chỉ là «nested class đọc được private», mà là **ranh giới làm nest có hiệu lực**: tên package ở source, **defining class loader**, runtime package, metadata hai chiều `NestHost`/`NestMembers`, và tác động của module/lỗi linkage. Một class có tên trông giống `Outer$Inner` **không tự động** là nestmate nếu JVM không xác minh được quan hệ.

Sau bài học, bạn có thể:

1. Phân biệt **nest host**, **nest member**, *nestmate*, nested class và top-level class cùng package.
2. Giải thích điều kiện **runtime package = (package name, defining class loader)** trong JVM, khác với chuỗi tên package đơn thuần.
3. Hiểu metadata classfile `NestHost` và `NestMembers`, và vì sao **cả host và member phải khai báo nhất quán**.
4. Phân biệt phạm vi **`private`** theo nest với **package-private**, `protected`, module **`exports`/`opens`** và quyền của Java reflection.
5. Dùng `Class.getNestHost()`, `Class.getNestMembers()` và `Class.isNestmateOf(...)` (**Since 11**) để chẩn đoán.
6. Nhận diện khi hai Class có **cùng binary name nhưng do hai class loader khác nhau định nghĩa** nên không phải cùng nest và không có cùng danh tính runtime.
7. Phân tích `IllegalAccessError`, `IncompatibleClassChangeError`, `LinkageError` khi host/member sai, host bị thiếu hoặc bytecode được nạp không đồng nhất.
8. Kiểm tra metadata bằng `javap -v -p` và chạy ví dụ thực tế Java 11 chứng minh cả quyền hợp lệ lẫn hành vi JVM từ chối một member nạp qua loader khác.

**Phạm vi hiện hành:** JEP 181 được đưa vào Java 11 và các API trên vẫn có ở JDK hiện đại. Không cần tự phát sinh **synthetic accessor** trong source để cho phép các nested types hợp lệ truy cập private; đó không phải hướng triển khai Java 11 được khuyến nghị. Bài không dùng cơ chế SecurityManager cũ như cách thiết kế ranh giới bảo mật.

## 1. Nest là gì và khác lexical nesting ra sao?

### 1.1. Ví dụ cơ bản

~~~java
package example;

public class Outer {
    private int secret = 7;

    class Inner {
        int read() {
            return secret; // Hợp lệ theo ngôn ngữ Java.
        }
    }

    static class Helper {
        static int inspect(Outer outer) {
            return outer.secret; // Cũng hợp lệ.
        }
    }
}
~~~

Đây là **đoạn minh họa**, chưa có `main`. Khi dùng `javac --release 11`, compiler có thể phát sinh các classfile:

~~~text
example/Outer.class
example/Outer$Inner.class
example/Outer$Helper.class
~~~

Các file được đánh dấu thành một **nest**. Thông thường:

- `example.Outer` là **nest host**.
- `example.Outer$Inner` và `example.Outer$Helper` là **nest members**.
- Host tự là một thành viên của nest mình chủ trì.
- Các nestmates có thể truy cập private members lẫn nhau theo quy tắc JVM.
- Tên có dấu `$` chỉ là cách compiler thường đặt binary name cho nested classes; **không phải bằng chứng đủ** về membership.

Một nested **interface**, local class hoặc anonymous class được compiler tạo trong phạm vi top-level cũng có thể được liệt kê vào nest phù hợp. Không suy đoán dựa trên tên `$1`/`$2` hay chỉ từ hình dạng source: khi cần kiểm, dùng metadata thực tế hoặc reflection.

### 1.2. Nest không đồng nghĩa «mọi class cùng package»

~~~java
package example;

class First {
    private static int hidden = 5;
}

class Second {
    // int value = First.hidden; // LỖI BIÊN DỊCH: hidden là private.
}
~~~

Hai top-level class trên **cùng tên package** và có thể cùng defining loader, nhưng compiler không tự đặt chúng vào cùng nest. Theo mặc định, mỗi class top-level không có metadata tham gia nest khác là **host của nest riêng**.

So sánh:

| Quan hệ | Package text | Defining loader | Có tự là nestmate? | Quyền `private` |
| --- | --- | --- | --- | --- |
| `Outer` và `Outer$Inner` do `javac 11` phát sinh đúng | Giống nhau | Giống nhau | Có, khi metadata hai chiều hợp lệ | Được phép theo JVM |
| Hai top-level classes cùng package, cùng loader | Giống nhau | Giống nhau | **Không tự động** | Vẫn bị chặn |
| Hai classes cùng tên package nhưng khác defining loader | Giống nhau | **Khác nhau** | **Không** | Bị chặn |
| Hai classes ở hai package khác nhau, cùng loader | **Khác nhau** | Giống nhau | **Không thể là nest hợp lệ** | Bị chặn |
| Hai classes khác module có `exports` | Có thể khác nhau | Bất kỳ | Không chỉ vì `exports` | Không có quyền private nest |
| Một class không khai `NestHost`, không khai `NestMembers` | — | — | Singleton nest | Chỉ tự truy cập private |

**Ghi nhớ:** quyền package-private có thể dùng cho các top-level classes cùng **runtime package**. Quyền private theo nest cần **thêm metadata nest hợp lệ**, không được suy ra chỉ từ package-private visibility hoặc cùng file `.java`.

## 2. Runtime package: tên package chưa đủ

### 2.1. Công thức từ JVMS 5.3

Theo **Java Virtual Machine Specification, Java SE 11 `5.3**:

~~~text
Class identity  ~= (binary name, defining class loader)
Runtime package = (package name, defining class loader)
~~~

Ký hiệu trên là **mô hình giải thích**, không phải Java code. Tên package trong source chỉ là **một vế** của runtime package.

Ví dụ:

~~~text
Loader L1 defines demo.nest.Host
Loader L1 defines demo.nest.Host$Member
    -> cùng runtime package demo.nest + L1

Loader L2 independently defines demo.nest.Host$Member
Loader L1 defines demo.nest.Host
    -> package text giống nhau, runtime package khác nhau
       vì defining loader L2 != L1
~~~

Hai `Class<?>` có thể cùng `getName()` và cùng `getPackageName()` nhưng **không phải cùng class runtime** nếu defining loader khác nhau. Việc L2 *có parent là L1* cũng không biến hai class do L1/L2 định nghĩa thành một class. **Initiating loader** (loader khởi đầu yêu cầu nạp và có thể delegate) phải được phân biệt với **defining loader** (loader thực sự gọi định nghĩa class); JVM sử dụng **defining loader** trong định nghĩa runtime package.

### 2.2. Vì sao ranh giới này ngăn giả mạo nest?

Nếu chỉ cần package string giống nhau, một plugin không đáng tin có thể tự đặt package `com.example.internal` rồi khai `NestHost` trỏ đến class chính của ứng dụng để đọc private fields. JVM **không cho phép** điều đó chỉ dựa trên tên. Member phải cùng runtime package với host, trong đó có defining loader giống nhau, và host còn phải xác nhận membership.

Đây là lý do test ở cuối bài cố ý nạp **chính bytes của `Host$Member.class` bằng một class loader mới**, trong khi `Host.class` vẫn do loader ban đầu định nghĩa. Dù tên đầy đủ `demo.nest.NestBoundaryDemo$Member` không đổi, JVM không coi member từ loader mới là nestmate hợp lệ.

**Không** xem nest là security sandbox toàn diện. Một class loader có quyền định nghĩa bytecode và được cấp quyền/truy cập tài nguyên vẫn phải được quản trị bằng cơ chế bảo mật hệ thống; nest access chỉ là **một phần của JVM access control**, không thay thế kiểm soát nguồn code/plugin, class path, module boundaries hoặc authorization.

## 3. NestHost và NestMembers: điều kiện hai chiều

### 3.1. Thuộc tính trong classfile

Từ classfile version **55.0 (Java 11)**, JVMS `4.7.28` và `4.7.29` mô tả:

- **`NestHost`:** một class/interface thành viên tuyên bố tên host. Thường có trên `Outer$Inner.class`, `Outer$Helper.class`.
- **`NestMembers`:** host liệt kê các class/interface được phép tuyên bố là thành viên của nest. Thường có trên `Outer.class`.
- **Host không chứa `NestHost` của host khác**; bản thân host là một member ngầm định của nest mà nó chủ trì.
- Một classfile **không được có đồng thời** `NestHost` và `NestMembers`.
- Một member muốn thuộc host phải có `NestHost` trỏ đúng host **và** host có `NestMembers` liệt kê binary name của member.

Sơ đồ:

~~~text
demo/nest/NestBoundaryDemo.class
    NestMembers:
        demo/nest/NestBoundaryDemo$Member
        demo/nest/NestBoundaryDemo$Sibling
        demo/nest/NestBoundaryDemo$NestedTag
        demo/nest/NestBoundaryDemo$ChildOnlyLoader

demo/nest/NestBoundaryDemo$Member.class
    NestHost: demo/nest/NestBoundaryDemo

demo/nest/NestBoundaryDemo$Sibling.class
    NestHost: demo/nest/NestBoundaryDemo
~~~

Danh sách trên là **minh họa từ source của bài thực hành**; compiler có thể phát sinh thêm các local/anonymous classes trong những chương trình khác. Chỉ dựa vào tên hiển thị khi đọc `javap` **không** chứng minh tính hợp lệ tại runtime nếu các classfile bị trộn phiên bản, loader khác hoặc bị chỉnh sửa.

### 3.2. Điều kiện công nhận một nest member

Đối với một class/interface `M` có `NestHost=H`, JVM cần:

1. **Resolve/load được H** theo quy tắc class loading.
2. **H và M cùng runtime package**, tức package name **và defining loader** giống nhau.
3. **H có `NestMembers`**.
4. `NestMembers` của H **có entry trỏ đến binary name của M**.
5. Các classfile/metadata có cấu trúc hợp lệ theo JVMS; host/member không mâu thuẫn theo định dạng.
6. Khi hai classes muốn truy cập `private` của nhau, JVM xác minh cả hai có **cùng nest host runtime đã được xác định hợp lệ**.

Nếu `M` **không có `NestHost`**, M tự làm host của mình. Nếu M có `NestHost` nhưng host không cùng runtime package/không có `NestMembers`/không liệt kê M, **JVMS 11 `5.4.4`** nêu rằng việc xác định nest host phục vụ access check có thể ném **`IncompatibleClassChangeError`**. Nếu hai lớp có host hợp lệ nhưng không cùng host, `private` access có thể thất bại với **`IllegalAccessError`**. Nếu class/host không thể được resolve/load, có thể thấy **`NoClassDefFoundError`** hoặc lỗi linkage khác.

**Không đồng nhất các API chẩn đoán:** `Class.getNestHost()` Java 11 có chính sách **trả về chính class đang hỏi** nếu xác định host gặp linkage/validation error, trong khi `getNestMembers()` có thể ném **`LinkageError`** khi nạp/xác minh danh sách. Việc một lời gọi reflection trả về singleton không biến metadata sai thành quyền truy cập private hợp lệ.

### 3.3. Metadata được kiểm tại runtime, không chỉ tại compile time

`javac` trên một source tree đồng bộ thường tạo các khai báo hai chiều nhất quán. Tuy nhiên packaging/shading/instrumentation/hot reload có thể tạo các tình huống:

- `Host.class` được thay bằng bản khác **không còn liệt kê Member**.
- `Host.class` bị loại khỏi JAR vì «không có code được gọi trực tiếp».
- Member bị sửa `NestHost` trỏ host khác nhưng host không xác nhận.
- Classfiles vẫn mang cùng tên package, nhưng bị chia cho **hai defining class loaders**.
- Một bytecode tool thay đổi tên class/package mà không cập nhật `NestHost/NestMembers` tương ứng.

JVM xác minh theo **bytecode và runtime identities thực**, không theo ý định ở source file. Oracle Java 11 Release Notes lưu ý rằng nếu xóa classfile host top-level chỉ dùng để chứa nested types, những member cần private access có thể không còn hoạt động đúng; không nên coi host classfile là «dead code» chỉ vì nó không được instantiation.

**Khuyến nghị packaging:** giữ cùng bộ host/member classfiles tương thích, giữ nguyên semantics của nest attributes khi relocate/obfuscate, và test sau khi bundling vào fat JAR/agent/plugin thật.

## 4. Nest và các cấp truy cập khác

### 4.1. `private` trong cùng nest

~~~java
class Host {
    private int value = 9;

    class Inner {
        int read(Host host) {
            return host.value; // Được phép khi là nestmate.
        }
    }
}
~~~

Việc access hợp lệ **không phải vì `Inner` vô tình cùng package**: member có metadata nest, và source Java cũng cho phép nested types truy cập thành viên private trong phạm vi lexical tương ứng.

### 4.2. Package-private không cho quyền private

~~~java
package demo.nest;

class A {
    private int onlyA = 1;
    int packageValue = 2;
}

class B {
    int allowed(A x) { return x.packageValue; }
    // int notAllowed(A x) { return x.onlyA; } // javac error
}
~~~

Hai top-level classes cùng runtime package có thể truy cập **package-private** (`packageValue`). **`onlyA` vẫn private** vì không có nest membership của B. Đừng nhầm «trong cùng file nguồn» với «trong cùng nest» — nhiều top-level classes trong cùng file vẫn là các top-level classes độc lập trừ khi metadata thực sự thiết lập quan hệ hợp lệ.

### 4.3. `protected` và module exports/opens là quy tắc khác

- **`protected`** còn phụ thuộc quan hệ subclass và quy tắc package/receiver; không dùng nest làm lý do để bỏ qua kiểm tra protected bình thường.
- **JPMS `exports`** quyết định package public API nào được module khác truy cập theo cách thông thường.
- **JPMS `opens`** cho phép deep reflection theo module policy, **không** đưa hai classes ở hai module vào cùng một nest.
- Cùng **runtime package** thuộc về **một runtime module** theo JVMS `5.3.6; module không có cơ chế «cho phép hai lớp ở hai runtime packages trở thành nestmates» bằng `requires/exports/opens`.
- **`MethodHandles.privateLookupIn(...)`** có các điều kiện quyền lookup và module opens riêng; việc có thể deep-reflect một member **không chứng minh** caller và target là nestmates.

Khi kiểm quyền `private` trong bytecode, hãy xem **nest identity**; khi kiểm class visibility qua module boundary, hãy xem **module readability/exports**; khi kiểm deep reflection, xem **opens/lookup modes**. Đây là ba câu hỏi liên quan nhưng **không thể thay thế cho nhau**.

## 5. Ba phương thức reflection dùng để kiểm tra nest (Java 11)

### 5.1. `Class.getNestHost()`

~~~java
Class<?> host = SomeClass.class.getNestHost();
~~~

Trả về nest host được JVM xác định. Với một top-level class không tham gia nest khác, host là chính class đó. Với `int.class`, `void.class` hoặc `String[].class`, giá trị cũng là chính `Class` đó (singleton nest đặc biệt).

**Lưu ý Java 11:** nếu khai `NestHost` không thể resolve hoặc không được host xác minh, `getNestHost()` có thể trả về chính M thay vì ném ngay ngoại lệ. Đó là hành vi chẩn đoán theo API, **không** có nghĩa khai báo sai đã trở thành hợp lệ.

### 5.2. `Class.getNestMembers()`

~~~java
Class<?>[] members = SomeClass.class.getNestMembers();
~~~

Danh sách **bao gồm host ở vị trí đầu tiên**; các thành viên còn lại **không được bảo đảm thứ tự**, có thể có duplicates theo API. Nếu muốn kiểm một member cụ thể, dùng `Arrays.asList(members).contains(target)`, **không** hardcode `members[2]`.

Khi kiểm các members do host khai báo, phương thức có thể ném **`LinkageError`** do class/member/host không tải hoặc xác minh được. Trong công cụ kiểm JAR/classfile, nên bắt lỗi này để báo chất lượng packaging thay vì biến nó thành mảng rỗng và tuyên bố «không có members».

### 5.3. `Class.isNestmateOf(Class<?> candidate)`

~~~java
boolean related =
        SomeClass.class.isNestmateOf(AnotherClass.class);
~~~

Trả về `true` nếu hai `Class` có cùng nest host được xác định hợp lệ. Kết quả nên được **đối chiếu với loader**, metadata hoặc lỗi khi cần chẩn đoán một JAR bị biến đổi. Không dùng riêng `String.equals(classA.getName(), classB.getName())` hoặc `getPackageName()` để thay cho phương thức này.

Các API này có **Since: 11** và nằm trong `java.lang.Class`; không cần Java Agent, sửa runtime flags hay mở internal JDK packages chỉ để dùng chúng.

### 5.4. Những giá trị không phải bằng chứng đủ

| Kiểm tra đơn lẻ | Tại sao chưa đủ |
| --- | --- |
| `A.class.getPackageName().equals(B.class.getPackageName())` | Chỉ so sánh **chuỗi tên package**, bỏ qua defining loader. |
| `A.class.getClassLoader() == B.class.getClassLoader()` | Cùng loader nhưng có thể khác package và khác nest. |
| `A.class.getName().equals(B.class.getName())` | Hai loader khác nhau có thể định nghĩa cùng binary name. |
| `A.class.getModule() == B.class.getModule()` | Cùng module không tự cấp private access. |
| `B.class.getSimpleName().contains("$")` | Tên có ký tự `$` không chứng minh nesting hoặc NestHost hợp lệ. |
| `javap` cho thấy member khai `NestHost` | Còn phải kiểm host, defining loader và `NestMembers` chiều ngược. |
| `getNestHost() == B.class` trên bytecode đáng ngờ | Có thể là singleton hợp lệ **hoặc** fallback vì host claim không hợp lệ. |
| `setAccessible(true)` thành công | Deep reflection không có nghĩa bytecode gọi trực tiếp private member giữa hai class là hợp lệ. |

## 6. Chương trình kiểm thử Java 11: package, loader và nest hợp lệ

Ví dụ gồm **hai source files**, để kiểm **rõ ràng** cả package khác nhau nhưng cùng loader. Đặc biệt, chương trình tự nạp lại đúng `Member.class` qua một class loader mới **không delegate đúng class đó cho parent**; host vẫn do parent loader định nghĩa. Điều này mô phỏng lỗi packaging/plugin loader và cho phép thấy JVM từ chối truy cập `private` bất hợp lệ.

Chương trình không cần dependency thứ ba, không dùng internal APIs, không yêu cầu `--add-opens`. Class có phương thức `readHost` được khai **public** để reflection có thể gọi mà **không cần `setAccessible`**; lỗi liên kết phát sinh do chính bytecode bên trong cố đọc private field/method của host khác loader.

### 6.1. Thư mục và source files

~~~text
src/
  demo/
    nest/
      NestBoundaryDemo.java
    other/
      Foreign.java
out/
  (javac tạo các .class tại đây)
~~~

**Tạo file `src/demo/nest/NestBoundaryDemo.java`:**

~~~java
package demo.nest;

import demo.other.Foreign;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public final class NestBoundaryDemo {
    private static int secretNumber = 42;

    private static String privateMethod() {
        return "private-ok";
    }

    public static final class Member {
        private int ownSecret = 7;

        public static String readHost() {
            return privateMethod() + ":" + secretNumber;
        }
    }

    static final class Sibling {
        static int readMember(Member member) {
            return member.ownSecret;
        }
    }

    interface NestedTag {
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static final class ChildOnlyLoader extends ClassLoader {
        private final String target;

        ChildOnlyLoader(ClassLoader parent, String target) {
            super(parent);
            this.target = target;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(target)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";
                    byte[] bytecode;
                    try (InputStream input = getParent()
                            .getResourceAsStream(resource)) {
                        if (input == null) {
                            throw new ClassNotFoundException(resource);
                        }
                        bytecode = input.readAllBytes();
                    } catch (IOException failure) {
                        throw new ClassNotFoundException(name, failure);
                    }
                    result = defineClass(name, bytecode, 0, bytecode.length);
                }
                if (resolve) resolveClass(result);
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        check("private-ok:42".equals(Member.readHost()),
                "Member reads host private method and field");
        check(Sibling.readMember(new Member()) == 7,
                "Sibling reads another member private field");
        System.out.println("PASS private access inside valid nest");

        check(NestBoundaryDemo.class.getNestHost()
                == NestBoundaryDemo.class, "host is itself");
        check(Member.class.getNestHost() == NestBoundaryDemo.class,
                "member NestHost is enclosing host");
        check(Sibling.class.isNestmateOf(Member.class),
                "sibling nest membership");
        check(NestedTag.class.isNestmateOf(Member.class),
                "nested interface also shares host");
        List<Class<?>> members = Arrays.asList(
                NestBoundaryDemo.class.getNestMembers());
        check(members.get(0) == NestBoundaryDemo.class,
                "nest host comes first");
        check(members.contains(Member.class)
                && members.contains(Sibling.class)
                && members.contains(NestedTag.class),
                "NestMembers contains expected classes");
        System.out.println("PASS host and reciprocal nest membership");

        check(SamePackagePeer.class.getPackageName().equals(
                NestBoundaryDemo.class.getPackageName()),
                "same package spelling");
        check(SamePackagePeer.class.getClassLoader()
                == NestBoundaryDemo.class.getClassLoader(),
                "same defining class loader");
        check(!SamePackagePeer.class.isNestmateOf(Member.class),
                "same package alone is not a nest");
        check(SamePackagePeer.class.getNestHost()
                == SamePackagePeer.class, "standalone class is self-hosted");
        System.out.println("PASS same package is not sufficient");

        check(Foreign.class.getClassLoader()
                == NestBoundaryDemo.class.getClassLoader(),
                "other package uses same loader");
        check(!Foreign.class.getPackageName().equals(
                NestBoundaryDemo.class.getPackageName()),
                "different package names");
        check(!Foreign.class.isNestmateOf(Member.class),
                "cross-package classes are not nestmates");
        System.out.println("PASS package boundary");

        String target = Member.class.getName();
        ClassLoader separate = new ChildOnlyLoader(
                NestBoundaryDemo.class.getClassLoader(), target);
        Class<?> shadowMember = Class.forName(target, true, separate);
        check(shadowMember != Member.class,
                "same binary name can denote distinct Class objects");
        check(shadowMember.getName().equals(Member.class.getName()),
                "same binary name spelling");
        check(shadowMember.getPackageName().equals(
                Member.class.getPackageName()),
                "same package text");
        check(shadowMember.getClassLoader()
                != NestBoundaryDemo.class.getClassLoader(),
                "different defining loader");
        check(!shadowMember.isNestmateOf(NestBoundaryDemo.class),
                "different runtime package prevents same nest");
        check(shadowMember.getNestHost() == shadowMember,
                "invalid claimed host results in singleton nest");
        System.out.println("PASS class-loader runtime-package boundary");

        Method read = shadowMember.getDeclaredMethod("readHost");
        boolean failedAtVmAccess = false;
        try {
            read.invoke(null);
        } catch (InvocationTargetException failure) {
            failedAtVmAccess = failure.getCause() instanceof LinkageError;
        } catch (LinkageError failure) {
            failedAtVmAccess = true;
        }
        check(failedAtVmAccess,
                "JVM must reject forged cross-loader nest access");
        System.out.println("PASS JVM rejects invalid private access");

        check(!String.class.isNestmateOf(Member.class),
                "unrelated JDK class is not a nestmate");
        check(int.class.getNestHost() == int.class,
                "primitive is a singleton nest");
        check(String[].class.getNestHost() == String[].class,
                "array is a singleton nest");
        System.out.println("PASS unrelated and special Class cases");

        System.out.println("ALL NEST BOUNDARY TESTS PASSED");
    }
}

final class SamePackagePeer {
    private static int internalOnly = 1;
}
~~~

**Tạo file `src/demo/other/Foreign.java`:**

~~~java
package demo.other;

public final class Foreign {
}
~~~

### 6.2. Lệnh biên dịch và chạy

Ở thư mục chứa `src`, tạo thư mục `out` rồi thực hiện:

~~~bash
javac --release 11 -encoding UTF-8 -d out src/demo/nest/NestBoundaryDemo.java src/demo/other/Foreign.java
java -cp out demo.nest.NestBoundaryDemo
~~~

**Stdout khi bảy nhóm assertion đều thành công:**

~~~text
PASS private access inside valid nest
PASS host and reciprocal nest membership
PASS same package is not sufficient
PASS package boundary
PASS class-loader runtime-package boundary
PASS JVM rejects invalid private access
PASS unrelated and special Class cases
ALL NEST BOUNDARY TESTS PASSED
~~~

`--release 11` kiểm cú pháp và public API baseline Java 11 khi biên dịch; nếu chạy bằng JDK mới, cần lưu ý đây là **kiểm thử chạy trên runtime JDK đang cài**, không thay cho chạy chính runtime Java 11 nếu sản phẩm yêu cầu chứng nhận Java 11. Ví dụ được thiết kế để hoạt động từ Java 11 trở đi và không cần preview feature.

### 6.3. Giải thích từng nhóm kiểm thử

**Nhóm 1 — private hợp lệ:** `NestBoundaryDemo.Member.readHost()` truy cập **private method `privateMethod()`** và **private static field `secretNumber`** của host. `Sibling.readMember(...)` đọc **private instance field `ownSecret`** của member khác. Điều này chứng minh host/member và siblings hợp lệ có quyền private tương ứng.

**Nhóm 2 — host và metadata:** `getNestHost()` của Member trả host; `Sibling.isNestmateOf(Member)` và `NestedTag.isNestmateOf(Member)` trả true. `getNestMembers()` chứa các thành viên dự kiến, nhưng code kiểm **contains** chứ không giả định thứ tự ngoài vị trí host.

**Nhóm 3 — cùng package vẫn không đủ:** `SamePackagePeer` là top-level class được biên dịch cùng file `.java`, cùng tên package và defining loader với Host, nhưng là **nest riêng**. `isNestmateOf` với Member trả false. Đây là trường hợp loại trừ việc «cùng file/source» là điều kiện đủ.

**Nhóm 4 — package khác:** `Foreign` nằm trong `demo.other`, do **cùng application class loader** nạp, nhưng không ở package `demo.nest`. Nó không là nestmate của Member. Trường hợp này giữ loader giống nhau để cô lập ảnh hưởng của **package-name boundary**.

**Nhóm 5 — same name, khác loader:** `ChildOnlyLoader` đặc biệt chỉ định nghĩa lại binary class `demo.nest.NestBoundaryDemo$Member` từ bytes của `.class`; tất cả tên khác được delegate cho parent. Kết quả là shadow member có **cùng binary name và package string**, nhưng **defining loader khác**. `shadowMember.getNestHost()` trả chính shadow class vì claim host không được xác minh trong cùng runtime package; `isNestmateOf(Host)` trả false.

**Nhóm 6 — JVM chặn private access:** `readHost()` là **public** để có thể được gọi qua `Method.invoke` thông thường **không cần nới quyền reflection**. Nhưng **bytecode bên trong** cố gọi private method và đọc private field của Host do loader khác định nghĩa. JVM chặn ở access/linkage check và test xác nhận nguyên nhân là một `LinkageError`. Ở môi trường/JDK cụ thể có thể thấy `IncompatibleClassChangeError` hoặc lỗi linkage liên quan; đừng suy ra chính xác subclass từ cấu trúc tên file. **Không** dùng phản xạ để vượt quá ranh giới: việc gọi được một public method không cấp quyền mới cho bytecode bên trong.

**Nhóm 7 — unrelated/special cases:** `String.class` không là nestmate của Member; primitive `int.class` và array `String[].class` là trường hợp singleton nest của riêng `Class` đó.

**Lưu ý bảo mật:** custom loader này chỉ dùng trong test có chủ đích. Trong ứng dụng production, class loading cần policy và isolation riêng. Không dùng «child-first override cho một class nội bộ» như một kỹ thuật can thiệp quyền private.

## 7. Xác minh classfile bằng javap

Sau khi compile `--release 11`, dùng lệnh:

~~~bash
javap -v -p -classpath out demo.nest.NestBoundaryDemo
javap -v -p -classpath out 'demo.nest.NestBoundaryDemo$Member'
~~~

Các dấu nháy đơn ở lệnh thứ hai giúp shell **không mở rộng ký tự `$`** thành biến môi trường trong các shell có interpolation. Trong PowerShell cũng dùng single quotes; trên Windows cmd.exe có quy tắc quote khác, có thể truyền tên class bằng đường dẫn tương ứng hoặc escaping phù hợp.

Bạn nên tìm các mục:

~~~text
major version: 55

# Trong host:
NestMembers:
  demo/nest/NestBoundaryDemo$Member
  demo/nest/NestBoundaryDemo$Sibling
  ...

# Trong member:
NestHost: class demo/nest/NestBoundaryDemo

# Trong method readHost: truy cập trực tiếp private host method/field
# mà không cần tự tạo public bridge trong source.
~~~

Đây là **trích đoạn định hướng**, không phải toàn bộ output bytecode cố định. Constant pool IDs, thứ tự các thành viên và phần thông tin compiler khác có thể thay đổi. Nếu `javap -v` không có `NestHost/NestMembers` ở classfiles bạn kỳ vọng:

1. Kiểm đã compile đúng source với `--release 11` và đang đọc đúng thư mục `out`.
2. Kiểm mục tiêu có thật sự là nested/local class do cùng compiler tạo không.
3. Kiểm có bước shading, relocation, bytecode weaving, JAR minimization hoặc hot reload nào thay đổi metadata không.
4. Đừng kết luận thiếu attribute là JVM bug trước khi kiểm bản classfile thực được class loader nạp.

### 7.1. JEP 181 giải quyết vấn đề gì?

Ở compiler/JVM cũ trước nestmates, các nested classes truy cập private có thể cần compiler phát sinh **synthetic accessor methods** để đi qua ràng buộc JVM. Với classfile 55.0 và nest metadata hợp lệ, JVM có thể thực hiện private access trực tiếp theo JEP 181.

Đây là **bối cảnh để hiểu khác biệt bytecode**, không phải lời khuyên biên dịch bằng JDK cũ hoặc tự phát sinh accessor thay cho nest metadata. Hãy dùng Java 11+ làm baseline khi bài/ứng dụng yêu cầu Java 11, và kiểm compatibility cho thư viện chạy trên runtime thấp hơn nếu thật sự có yêu cầu hỗ trợ riêng.

## 8. Khi nào lỗi linkage xuất hiện?

Một ứng dụng có thể compile tốt nhưng khi run vẫn lỗi do classpath/classloader và JAR packaging khác lúc compile.

| Lỗi/triệu chứng | Khả năng liên quan đến nest | Cách điều tra |
| --- | --- | --- |
| `IllegalAccessError` khi truy cập private | Hai classes không được xác nhận là cùng nest hoặc target member không accessible | `javap -v` hai bên; so `getNestHost/isNestmateOf`, class loader runtime |
| `IncompatibleClassChangeError` | Host khác runtime package, host thiếu `NestMembers`, host không liệt kê member (JVMS 11) | Kiểm NestHost ↔ NestMembers và defining loader |
| `NoClassDefFoundError`/`ClassNotFoundException` | Host hoặc member bị loại khỏi artifact/không nạp được | Kiểm JAR contents, classloader resource path, deployment dependencies |
| `LinkageError` khi gọi `getNestMembers()` | Lỗi load/validate một member hoặc host được liệt kê | Kiểm classfile bị thiếu, mismatch, relocated |
| `getNestHost()` trả chính Member không mong đợi | Member là singleton thực sự **hoặc** host claim không hợp lệ và API fallback | Kiểm bytecode rồi so loading context |
| Cùng `getName()` nhưng `==` giữa hai `Class` là false | Cùng binary name bị định nghĩa ở hai loaders khác nhau | In `getClassLoader()`/module và call chain của loader |
| `ClassCastException` giữa hai types cùng tên hiển thị | Distinct runtime identities do loader khác nhau | Kiểm loader boundaries, tránh duplicate API classes |
| `InaccessibleObjectException` khi deep reflection | JPMS module `opens`/lookup rules, không nhất thiết do nest | Kiểm module metadata, `opens`/lookup chính xác |

### 8.1. Quy trình điều tra có thứ tự

1. **Giữ nguyên stack trace** và đúng exception/cause; đừng tự chuyển tất cả `LinkageError` thành một thông báo «private denied».
2. Xác định **binary name** của target field/method/class và cặp host/member kỳ vọng.
3. Trên artifact build và artifact deploy, kiểm `javap -v -p` hoặc công cụ bytecode được hỗ trợ để đọc **`NestHost/NestMembers`**.
4. So **runtime `Class.getClassLoader()`** cho host/member; phân biệt **defining loader** và loader gọi `loadClass` có delegation.
5. So `getPackageName()`, `getModule()`; nếu tên package giống nhưng defining loader khác thì **runtime package khác**.
6. Kiểm `getNestHost()/getNestMembers()/isNestmateOf` một cách thận trọng: `getNestMembers()` có thể phát `LinkageError`, `getNestHost()` có thể fallback self.
7. Kiểm module exports/opens nếu lỗi xảy ra ở call site công khai hoặc deep reflection, tránh «chữa» sai bằng flags mở toàn bộ module.
8. Bảo đảm **JAR host không bị xóa**, version của host/member không lệch nhau; kiểm classpath/module path và instrumentation.
9. Reproduce trên JDK baseline, với cùng classloaders, không chỉ bằng một unit test dùng loader hệ thống mặc định.
10. Sửa **nguồn metadata/packaging/loader design**, không blanket-catch `LinkageError` để tiếp tục vận hành một đối tượng không còn bảo đảm đúng identity.

### 8.2. Nguy cơ khi reload plugin/module

Trong ứng dụng plugin, OSGi, application server, hot reload hoặc hệ thống tạo class động:

- Một plugin loader có thể tạo class tên `app.internal.Helper` giống package của host ứng dụng; **không phải** cùng runtime package nếu host do loader khác define.
- Nếu muốn một nest hoạt động, các member cần được define với **cùng runtime package/loader** và classfile metadata đúng chiều. Chỉ delegate một phần classes qua parent rồi tự define phần còn lại có thể phá nest.
- Class loader mới thường tạo **bộ Class identities mới**, kể cả khi file bytes y hệt. Không truyền các instance qua boundary rồi cast như thể hai bản đã cùng loại.
- `getPackageName()` bằng nhau chỉ giúp debug tên, không chứng minh runtime identity. Khi đánh giá quyền, xem `getClassLoader()` và metadata host/member.
- **Shading/relocation** phải cập nhật các symbolic class references/attributes nhất quán. Một tool lỗi thời không hiểu `NestHost/NestMembers` có thể làm hỏng classfile Java 11.

## 9. Thiết kế API và bảo vệ tính đóng gói

Nest-based private access là sự thay đổi **ở JVM level**, không phải cách để mở private data cho mọi code cùng package. Trong source Java, quy tắc lexical access và access modifiers vẫn được áp dụng bởi compiler. Khi phát triển thư viện:

- Tổ chức nested types cho một **abstraction có chủ sở hữu rõ ràng**; không biến mọi class thành nested chỉ để né quyền access.
- Không giả định các plugin cùng tên package có quyền private của host; giữ class loader boundary có chủ ý.
- Không rely vào deep reflection/setAccessible như một lối tắt khi NestHost/NestMembers sai. Với Java module hiện đại, strong encapsulation được quản lý riêng.
- Không xuất `private` qua public bridge chỉ để «sửa nhanh» lỗi packaging: việc đó thay đổi surface quyền truy cập. Trước hết sửa classfile/loader.
- Nếu thư viện được relocate/obfuscate hoặc tối ưu JAR, thêm test runtime như `isNestmateOf` và private call thật sau khi đóng gói.
- Không lấy tên binary `Outer$Member` làm chính sách authorization; tên class không là danh tính người dùng, principal hay credential.
- Với Java bytecode generation dùng ASM/Byte Buddy hoặc library tương đương, phải dùng **phiên bản hỗ trợ classfile Java 11+ và nest attributes** và test kết quả; tránh chép lại metadata ở mức byte mà không xét JVMS.
- Nếu ứng dụng ở môi trường multi-tenant, cần tách quyền ở cấp process/container/service thích hợp và authentication/authorization, vì JVM nest **không phải sandbox** cho mã nguồn bất tín.

## 10. Câu hỏi tự đánh giá

**1.** Hai top-level classes cùng `package demo.nest;` có tự là nestmates không?

**Đáp án:** Không. Cùng package không tự lập một nest; phải có **cùng nest host hợp lệ**. Top-level class riêng thường tự là host của singleton nest.

**2.** Runtime package trong JVMS 11 được xác định bằng gì?

**Đáp án:** Cặp **(package name, defining class loader)**, không phải tên package riêng lẻ. Một class còn được nhận diện theo cặp **(binary name, defining loader)**.

**3.** Hai classes cùng binary name `demo.nest.Host$Member` nhưng do hai defining loaders khác nhau có phải một class không?

**Đáp án:** Không. Đó là hai runtime class identities khác nhau; `Class<?>` objects không bằng nhau và có thể không cùng runtime package với host kỳ vọng.

**4.** Chỉ thêm `NestHost` vào member để chỉ host mà không sửa `NestMembers` của host có đủ không?

**Đáp án:** Không. JVM xác minh hai chiều; host phải liệt kê member và cùng runtime package. Nếu không, quyền `private` không được cấp.

**5.** `Class.getNestHost()` trả Member.class, có nghĩa Member chưa từng khai NestHost không?

**Đáp án:** Không nhất thiết. Member có thể thật sự là singleton, hoặc đã **khai host nhưng claim không được xác minh** và `getNestHost()` Java 11 fallback về chính class.

**6.** `Class.getNestMembers()` có bảo đảm member thứ hai luôn là class bạn viết đầu tiên không?

**Đáp án:** Không. Host là phần tử đầu; các member còn lại không có thứ tự được bảo đảm. Nên kiểm membership bằng `contains`.

**7.** `Class.isNestmateOf(...)` xuất hiện từ Java nào?

**Đáp án:** **Java 11**, cùng với `getNestHost()` và `getNestMembers()`.

**8.** Nếu hai classes ở package khác nhau nhưng dùng một loader và cùng module, chúng có thể là nestmates chỉ nhờ `exports` không?

**Đáp án:** Không. Nest đòi cùng runtime package và metadata hai chiều; `exports` chỉ liên quan truy cập public types qua module boundary.

**9.** Package-private field và private field được quyết định bởi cùng một quy tắc không?

**Đáp án:** Không. Package-private phụ thuộc cùng runtime package; private của một class khác phụ thuộc **nestmate test hợp lệ**.

**10.** Vì sao Java 11 có thể không cần những synthetic accessor methods trước đây cho nested classes?

**Đáp án:** JVM có nest-based access control ở classfile version 55.0, cho phép member truy cập private của nestmates trực tiếp theo metadata.

**11.** Nếu loại Host.class khỏi JAR vì nó chỉ là nơi đặt nested classes, có an toàn không?

**Đáp án:** Không thể giả định. Member cần host để xác minh nest; có thể gặp class loading/linkage errors. Giữ host/member artifact tương thích.

**12.** Vì sao `Method.invoke` gọi được `readHost()` trong custom loader nhưng câu lệnh **bên trong** method vẫn lỗi?

**Đáp án:** Method public có thể được gọi, nhưng bytecode đó vẫn phải qua JVM access check khi cố truy cập **private** của host thuộc runtime package/loader khác.

**13.** Có thể dùng `Method.setAccessible(true)` để làm hai class khác loader trở thành nestmates không?

**Đáp án:** Không. Reflection access override và JVM nest membership là hai cơ chế độc lập; nó không sửa `NestHost/NestMembers` hoặc defining loader.

**14.** Một class loader con delegate host cho parent nhưng tự define member có `NestHost` trỏ host: có hợp lệ không?

**Đáp án:** Không chỉ nhờ cùng package text hoặc quan hệ parent. Host do parent define, member do child define, nên **không cùng runtime package**; JVM từ chối private access.

## Checklist hoàn thành

- [ ] Phân biệt lexical nested class, nest host, nest member và nestmate runtime.
- [ ] Biết **runtime package = (package name, defining loader)**, class identity cũng cần loader.
- [ ] Không suy ra nestmate chỉ từ source package, file `.java`, tên `$` hoặc `getName()`.
- [ ] Hiểu `NestHost` ở member và `NestMembers` ở host cần đúng hai chiều.
- [ ] Biết host tự là member của nest, và class không khai NestHost thường tự là host.
- [ ] Đọc được `javap -v -p` với classfile major version 55 và nest attributes.
- [ ] Dùng `getNestHost`, `getNestMembers` và `isNestmateOf` từ Java 11 đúng ý nghĩa.
- [ ] Phân biệt private nest access với package-private, protected, JPMS exports/opens và deep reflection.
- [ ] Biết các tình huống gây `IllegalAccessError`, `IncompatibleClassChangeError` và `LinkageError`.
- [ ] Có test class loader nạp lại member để chứng minh runtime package boundary.
- [ ] Không bỏ Host.class, không trộn classfile versions hoặc di chuyển package mà quên nest metadata.
- [ ] Compile và chạy được hai source files bằng `javac --release 11`, đạt toàn bộ **7 nhóm PASS**.
- [ ] Chạy regression tests trên runtime Java 11 thật nếu sản phẩm yêu cầu baseline đó, ngoài kiểm tra bytecode tương thích.

## Tài liệu chính thức và hiện hành

1. [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181)
2. [Java SE 11 JVMS `5.3 — Class identity và runtime package](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.3)
3. [Java SE 11 JVMS `5.4.4 — Access Control và nestmate test](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4)
4. [Java SE 11 JVMS `4.7.28 — NestHost attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28)
5. [Java SE 11 JVMS `4.7.29 — NestMembers attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29)
6. [Java SE 11 `java.lang.Class` — getNestHost, getNestMembers, isNestmateOf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html)
7. [Oracle JDK 11 Release Notes — nest-based access và yêu cầu giữ classfile nest host](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html)
8. [Java SE 26 JVM Specification `5.4.4 — Nest-Based Access hiện hành](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-5.html#jvms-5.4.4)
9. [Java SE 26 `java.lang.Class` — kiểm các reflection nest APIs vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html)
