# Nest-based access: Tương thích công cụ sinh lớp, instrument và thu gọn artifact (Java 11+)

## Mục tiêu và phạm vi

**Nest-based access control** (JEP 181) được đưa vào Java 11 để các lớp thuộc cùng một *nest* có thể truy cập trực tiếp những thành viên `private` của nhau ở cấp JVM. Thay vì phụ thuộc các accessor synthetic do compiler sinh để lớp lồng nhau gọi tới field/method private của lớp bao ngoài, bytecode Java 11 có thể sử dụng quan hệ nest được mô tả trong class file.

Tính năng này vẫn hiện hành ở những JDK mới, nhưng tạo ra trách nhiệm quan trọng cho **công cụ sinh lớp, bytecode instrumentation, agent, minifier/obfuscator, shrinker và shader**: các công cụ phải đọc, ghi, đổi tên, loại bỏ hoặc bảo toàn cấu trúc nest một cách chính xác.

Bài học giúp bạn:

- Hiểu hai attribute `NestHost` và `NestMembers`, yêu cầu **khai báo hai chiều**, cùng runtime package và class-file major version **55** của Java 11.
- Phân biệt class nested thực sự với một class do generator tạo có tên chứa ký tự `$` hoặc ở cùng package.
- Kiểm tra nestmate bằng `Class.getNestHost()`, `getNestMembers()`, `isNestmateOf(Class<?>)` và `javap -v -p`.
- Thiết kế generator/transformer mà không phá vỡ quyền truy cập private, stack map frames và class-loader identity.
- Nắm giới hạn của `java.lang.instrument.Instrumentation`: **không được thay đổi `NestHost`/`NestMembers` của class đã load qua retransform/redefine**.
- Thực hiện relocation, shading, shrink và đóng JAR với metadata cùng các class được tham chiếu còn nhất quán.
- Chạy chương trình **Java 11 thực sự biên dịch với `--release 11`**, kiểm tra kết quả khi chạy từ thư mục class và từ JAR.
- Thiết kế smoke tests và CI matrix để phát hiện lỗi trong **artifact sau biến đổi**, không chỉ trong source ban đầu.

**Special Note:** chỉ dùng kiến thức hiện vẫn có giá trị. Ví dụ tương thích Java 11, tài liệu tham chiếu có cả đặc tả JVM hiện đại. Không hướng dẫn lách verifier hoặc tự động đổi private sang public.

## 1. Nest là gì trong Java Virtual Machine?

Một nest là nhóm các class hoặc interface được phép truy cập private members của nhau. Một class đóng vai trò **nest host**; những class còn lại thuộc nest là **members**. Có thể xem nhóm này là một đơn vị quyền truy cập private, nhưng JVM vẫn định nghĩa **mỗi class trong một class file riêng**.

Ví dụ minh họa:

```java
public class Outer {
    private int secret = 42;

    private static class Reader {
        static int read(Outer outer) {
            return outer.secret;
        }
    }
}
```

Đây chỉ là **source minh họa** và không chứa method main. Với `javac --release 11`, compiler tạo `Outer.class` và `Outer$Reader.class`. Quan hệ được biểu diễn tương tự:

```text
Outer.class                        Outer$Reader.class
  class-file 55                      class-file 55
  NestMembers:                       NestHost:
    Outer$Reader                       Outer
         |                              |
         +------ xác nhận hai chiều ----+
                  private access
```

Từ Java 11, `NestHost` và `NestMembers` là các attribute thuộc class-file version 55 trở lên. Quyền truy cập không được cấp chỉ dựa trên cú pháp tên hay việc lớp con nằm cùng package ở source code.

### Hai thuộc tính có ý nghĩa khác nhau

| Attribute | Vị trí | Vai trò |
| --- | --- | --- |
| `NestMembers` | Class là host | Liệt kê những lớp được host thừa nhận là thành viên nest |
| `NestHost` | Class là member | Chỉ ra host mà member yêu cầu được nhận là nestmate |

Host tự thuộc nest của mình. Một class không có `NestHost` được xem là host của chính mình; nếu cũng không có `NestMembers` thì nest chỉ có **một class**.

**JVM yêu cầu mối quan hệ phù hợp hai chiều:** member chỉ về host và host công bố member trong danh sách. Member cũng phải thuộc **cùng runtime package** với host, tức không chỉ trùng chữ trong `package demo.example;` mà còn phải phù hợp identity của defining class loader.

### Không nhầm với metadata nested class khác

| Attribute | Chức năng | Thay thế NestHost/NestMembers? |
| --- | --- | --- |
| `InnerClasses` | Mô tả nested/inner classes, class modifiers và thông tin dùng cho reflection | **Không** |
| `EnclosingMethod` | Ghi enclosing method/constructor của local hoặc anonymous class | **Không** |
| `Signature` | Mô tả generic signatures dùng bởi reflection/tooling | **Không** |
| `RuntimeVisibleAnnotations` | Giữ annotation runtime cho framework | **Không** |
| `NestHost/NestMembers` | Quy tắc membership của nest và quyền private | **Có, chính chúng là thông tin cần thiết** |

Một công cụ có thể cần giữ nhiều attribute vì lý do reflection, DI hoặc serialization. Nhưng **giữ InnerClasses không đủ để thay cho NestHost/NestMembers** nếu bytecode dựa trên private access của nestmates.

## 2. Vì sao công cụ sinh class hoặc transformer dễ gây lỗi?

Pipeline điển hình:

```text
Java source / generator
       |
       v
.class (constant pool, methods, NestHost/NestMembers, ...)
       |
       +--> instrument bytecode / javaagent
       |
       +--> obfuscate / relocate / shade
       |
       +--> shrink unused classes
       |
       +--> package JAR / application image
       |
       v
JVM load + link + verify + access checks
       |
       v
application + framework reflection
```

Nếu transformer không hiểu class-file version mới, nó có thể:

- Không đọc nổi class-file 55 hoặc cao hơn.
- Chỉ sao chép method body mà vô tình **mất nest attributes**.
- Đổi tên class trong constant pool nhưng không cập nhật tên host/member.
- Chuyển một member sang package khác, khiến nest không còn cùng runtime package.
- Viết lại bytecode nhưng không duy trì `StackMapTable` đúng.
- Thu gọn nhầm class được gọi qua reflection hoặc được liệt kê trong metadata.
- Định nghĩa proxy bằng classloader khác rồi giả định tên cùng package mang lại private access.
- Thử thay đổi nest topology khi class **đã load**, điều mà Instrumentation không hỗ trợ.

**Biên dịch thành công không đồng nghĩa artifact an toàn.** Một số lỗi phát sinh **khi load class, resolve private method, gọi reflection hoặc chạy trong classloader khác**. Bởi vậy phải kiểm thử artifact cuối sau khi bytecode được biến đổi.

## 3. Tên có dấu `$` và cùng package không tạo nestmate

Một lớp do generator đặt tên `Outer$Proxy` chưa chắc là nested class của `Outer`. Trong Java, ký tự `$` là ký tự hợp lệ của identifier/binary name; nó **không tự cấp private access**.

Ví dụ hai trường hợp:

```text
Case A: Outer.class + Outer$Reader.class
  - Reader được compiler sinh từ class lồng nhau.
  - Có NestHost, host có NestMembers tương ứng.
  - Có thể là nestmates.

Case B: Outer.class + Outer$Proxy.class
  - Proxy được định nghĩa là top-level class độc lập.
  - Chỉ đặt tên có '$', không có membership đúng.
  - KHÔNG tự thành nestmate.
```

Ngay cả khi A và B cùng package trên đĩa, classloader thực tế và metadata vẫn quyết định.

### `MethodHandles.Lookup.defineClass(byte[])` trong Java 11

API `Lookup.defineClass` định nghĩa class vào cùng runtime package, class loader và protection domain với lookup class trong các điều kiện quyền `PACKAGE` cho phép. Điều này hữu ích cho generator cần class trong cùng package, **nhưng không tự thêm class đó vào nest**.

Một class được định nghĩa đúng package có thể có quyền package-private phù hợp, nhưng **private access tới một nest khác** là chuyện riêng. Không lấy kết quả thành công của `defineClass` làm bằng chứng có nestmate access.

Ở JDK mới hơn có API hidden class với tùy chọn `NESTMATE`; nó **không thuộc Java 11**, nên không được dùng trong ví dụ yêu cầu compile `--release 11`. Nếu một thư viện muốn dùng API JDK mới, phải tách rõ baseline runtime.

### Cách tạo một member đúng quyền

Một generator làm việc với class files cần:

1. Xác định host thật và tất cả members dự kiến.
2. Ghi `NestMembers` nhất quán trên host.
3. Ghi `NestHost` trỏ đúng host trên member.
4. Giữ class names/package/loading context phù hợp.
5. Sinh bytecode, descriptors và access flags đúng đặc tả.
6. Đảm bảo host/member được định nghĩa vào JVM trong trạng thái hợp lệ.
7. Không dùng khả năng tạo nest để bỏ qua chính sách bảo mật của ứng dụng.

Một công cụ đáng tin có thể làm điều đó **trước khi class được định nghĩa**. Không nên tạo quyền private rộng hơn nhu cầu thực tế, hoặc sửa member public/private bất hợp lý chỉ để chạy qua verification.

## 4. Ví dụ Java 11 đầy đủ: nestmates thật và class giống tên generated

Chương trình `NestToolingDemo.java` kiểm tra ba private-access paths:

- `Reader`, là thành viên thật, đọc private field của host.
- `Bridge`, là thành viên thật, gọi private method của member `Calculator`.
- `NestToolingDemo$Generated`, là **top-level class** cùng package có ký tự `$` trong tên, **không** là nestmate.

Ngoài ra chương trình lấy `getNestMembers()` và đếm các method được đặt tên kiểu accessor `access$...`. Kết quả đếm là đặc tính của **fixture biên dịch bởi javac**, không phải quy tắc rằng mọi synthetic method trên Java 11 đều biến mất.

### 4.1. Tệp `NestToolingDemo.java`

```java
package demo.nest;

import java.lang.reflect.Method;
import java.util.Arrays;

public final class NestToolingDemo {
    private final String label = "nested-ok";
    private static final int SECRET = 41;

    private static final class Reader {
        static String read(NestToolingDemo host) {
            return host.label;
        }
    }

    private static final class Calculator {
        private static int plusOne() {
            return SECRET + 1;
        }
    }

    private static final class Bridge {
        static int readOtherNestedPrivate() {
            return Calculator.plusOne();
        }
    }

    public static void main(String[] args) {
        Class<?> host = NestToolingDemo.class;
        Class<?> reader = Reader.class;
        Class<?> generatedLooking =
                NestToolingDemo$Generated.class;

        if (!reader.isNestmateOf(host)
                || generatedLooking.isNestmateOf(host)) {
            throw new AssertionError(
                    "Unexpected nest relationship");
        }
        if (!"nested-ok".equals(
                Reader.read(new NestToolingDemo()))) {
            throw new AssertionError(
                    "Private access failed");
        }
        if (Bridge.readOtherNestedPrivate() != 42) {
            throw new AssertionError(
                    "Sibling private access failed");
        }

        Class<?>[] members = host.getNestMembers();
        long accessors = Arrays.stream(
                new Class<?>[] {
                    host, Reader.class,
                    Calculator.class, Bridge.class
                })
                .flatMap(c -> Arrays.stream(
                        c.getDeclaredMethods()))
                .map(Method::getName)
                .filter(name -> name.startsWith("access$"))
                .count();

        System.out.println(
                "host=" + reader.getNestHost().getSimpleName());
        System.out.println("nestedIsNestmate="
                + reader.isNestmateOf(host));
        System.out.println("generatedLookingIsNestmate="
                + generatedLooking.isNestmateOf(host));
        System.out.println("privateValue="
                + Reader.read(new NestToolingDemo()));
        System.out.println("siblingPrivateResult="
                + Bridge.readOtherNestedPrivate());
        System.out.println("memberCount=" + members.length);
        System.out.println("syntheticAccessors=" + accessors);
    }
}

// Top-level class riêng biệt, chỉ có tên chứa '$'.
final class NestToolingDemo$Generated {
    private NestToolingDemo$Generated() { }
}
```

**Chú ý dấu đóng `}` của host:** `NestToolingDemo$Generated` được khai báo **bên ngoài** host nên **không** là nested class, dù cùng file source và cùng package. Mục đích là mô phỏng **cách đặt tên** của một generator; chương trình không gọi ASM/Byte Buddy.

### 4.2. Biên dịch và chạy

Lưu tệp đúng tên `NestToolingDemo.java`, sau đó:

```bash
javac --release 11 -encoding UTF-8 -d out NestToolingDemo.java
java -cp out demo.nest.NestToolingDemo
```

**Stdout đã kiểm tra thực tế sau khi biên dịch bằng `--release 11`:**

```text
host=NestToolingDemo
nestedIsNestmate=true
generatedLookingIsNestmate=false
privateValue=nested-ok
siblingPrivateResult=42
memberCount=4
syntheticAccessors=0
```

**Diễn giải:**

1. `getNestHost()` trên `Reader` trả `NestToolingDemo`.
2. `Reader.class.isNestmateOf(host)` là `true`.
3. Class `NestToolingDemo$Generated` có tên giống nested nhưng `isNestmateOf` là `false`.
4. `Reader` truy cập được `label` private của host.
5. `Bridge` gọi được method private `Calculator.plusOne()`; kết quả `42`.
6. Nest chứa host và ba lớp thành viên: `Reader`, `Calculator`, `Bridge`, tổng `4`.
7. Compiler không sinh method bắt đầu bằng `access$` trong fixture này.

Khi dùng `Class.getNestMembers()` trong code thật, **không dựa vào thứ tự members**. Javadoc chỉ xác định host ở vị trí đầu; thứ tự các member khác không được bảo đảm. Nếu cần kiểm tra membership cụ thể, hãy dùng `isNestmateOf(...)` hoặc so tập hợp class.

## 5. Kiểm tra classfile bằng `javap -v -p`

Sau khi build:

```bash
javap -v -p -classpath out demo.nest.NestToolingDemo
javap -v -p -classpath out 'demo.nest.NestToolingDemo$Reader'
```

Dấu nháy đơn quanh binary name có `$` an toàn trong Bash/PowerShell. Với Windows CMD, có thể dùng nháy kép. Output đầy đủ của `javap` dài; các **mục quan trọng** là:

```text
// Trích yếu mô tả mục cần thấy, không phải toàn bộ javap.
major version: 55

// Host:
NestMembers:
  demo/nest/NestToolingDemo$Reader
  demo/nest/NestToolingDemo$Calculator
  demo/nest/NestToolingDemo$Bridge

// Reader member:
NestHost: class demo/nest/NestToolingDemo
```

Thứ tự members trong minh họa **không phải cam kết của JVMS**. Kết quả kiểm thử thực tế đã xác nhận:

- Class major version = **55**.
- Host có attribute `NestMembers`.
- Member Reader có attribute `NestHost`.

Một lệnh grep `NestHost` trong constant pool **không đủ** để chứng minh membership. Cần xem attribute của class được inspect và **kiểm tra chạy thật**.

### Runtime reflection API Java 11

| API | Kết quả/ý nghĩa |
| --- | --- |
| `getNestHost()` | Class host của nest mà đối tượng Class thuộc về |
| `getNestMembers()` | Danh sách các member Class thuộc cùng nest; có thể gặp linkage lỗi nếu metadata sai |
| `isNestmateOf(otherClass)` | Hai class có cùng nest host hợp lệ hay không |

Đây là API còn hiện hành ở JDK mới. Nó **không** chứng minh một class là nested lexical theo source; những thông tin đó cần API khai báo class phù hợp và metadata khác.

## 6. Đóng JAR và kiểm tra bản phân phối

Một lỗi thường gặp: unit test chạy trong IDE/target classes tốt nhưng JAR phát hành thiếu nested class, mất attribute sau shrink hoặc đổi tên không đồng bộ.

Sau khi biên dịch:

```bash
jar --create --file demo.jar -C out .
jar tf demo.jar
java -cp demo.jar demo.nest.NestToolingDemo
```

Trong thử nghiệm, bản **JAR đã chạy cho đúng toàn bộ 7 dòng stdout** như chương trình chạy từ thư mục classes. Điều này xác nhận riêng pipeline đóng gói đơn giản của fixture.

Inspect JAR cuối:

```bash
javap -v -p -classpath demo.jar demo.nest.NestToolingDemo
javap -v -p -classpath demo.jar 'demo.nest.NestToolingDemo$Reader'
```

**Kiểm tra trong JAR:**

- `demo/nest/NestToolingDemo.class`.
- `demo/nest/NestToolingDemo$Reader.class`.
- `demo/nest/NestToolingDemo$Calculator.class`.
- `demo/nest/NestToolingDemo$Bridge.class`.
- Metadata host/member nhất quán trong **bản phân phối cuối cùng**.
- Các class thật sự chạy và private access không gặp linkage/access error.

Đừng chỉ kiểm tra `jar tf`: có đủ tên file class chưa chắc đã có Nest attributes đúng. Ngược lại, một host có `NestMembers` trỏ đến class đã bị xóa sau shrinking có thể làm một số đường phản chiếu như `getNestMembers()` thất bại. Chạy `javap` và smoke test là cần thiết.

## 7. Java agents và instrumentation: thời điểm thay đổi là quyết định

### 7.1. Load-time transformer

Một `ClassFileTransformer` được gọi khi JVM chuẩn bị định nghĩa class có thể tạo/biến đổi class bytes. Nếu một tool **đổi tên, sinh hoặc bỏ class**, nó phải bảo đảm những metadata nest của host/member vẫn đúng trước thời điểm JVM cần đến chúng.

Cần kiểm soát:

1. Classfile version của input/output, tối thiểu major 55 nếu dùng Nest attrs.
2. `NestHost` trên member, `NestMembers` trên host.
3. Tên class trong constant pool, method/field descriptors và references.
4. Runtime package, classloader và module constraints.
5. `StackMapTable`, frames và invokes nếu body method đổi.
6. Khả năng host/member bị define ở các thời điểm khác nhau.
7. Lỗi classfile/linkage phải được test như lỗi build/runtime, không che bằng catch rộng rồi dùng bytecode hỏng.

**Không có quyền bất biến “muốn thêm class vào nest nào cũng được”**. Quan hệ nest cấp quyền private mạnh; chỉ generator/agent đáng tin được thao tác metadata này.

### 7.2. Class đã load: `retransformClasses` và `redefineClasses`

Theo Javadoc `java.lang.instrument.Instrumentation` của **Java 11**, khi class đã được định nghĩa, hai phương thức:

- `Instrumentation.retransformClasses(...)`
- `Instrumentation.redefineClasses(...)`

**không được thay đổi `NestHost` hoặc `NestMembers`**. Chúng cũng không phải công cụ tùy tiện thêm/xóa/đổi tên field và method hoặc đổi inheritance.

Vì vậy:

- Không thể load class rồi dùng retransform để thêm một nest member mới vào host.
- Không thể “hotfix” một JAR bị relocate sai nest bằng cách sửa nest attrs trên class đã load.
- Có thể instrument **method body** nếu giữ nest metadata và tuân thủ ràng buộc retransform/redefine, bytecode verifier và capability của JVM.
- Nếu cần topology khác, sửa tại **build/load-time trước định nghĩa class** hoặc thiết kế lại API/proxy.

Không đánh đồng giới hạn này với load-time transformer. Kết quả không được chấp nhận có thể dẫn đến `UnsupportedOperationException`, `UnmodifiableClassException`, `ClassFormatError` hoặc lỗi linkage khác tùy bối cảnh; không assert một exception message cố định.

### 7.3. Agent cũ và classfile version 55

Nếu thư viện bytecode của agent không hiểu NestHost/NestMembers:

- Có thể không parse/viết được class.
- Có thể bỏ attribute nó không biết.
- Có thể tính lại frames sai khi chèn nhánh/instruction.
- Có thể đổi private invocation sai.
- Có thể tạo proxy trong loader khác, dẫn đến thay đổi runtime package.

Khắc phục là **nâng cấp bytecode library/agent** có khả năng đọc/ghi target classfile của sản phẩm và test với agent thật. Không tắt verifier, không sửa private thành public và không ép dùng công cụ chỉ tương thích classfile cũ.

## 8. ASM, Byte Buddy, Javassist và generator hiện đại

Đối với bất kỳ framework biến đổi bytecode, hãy xác minh:

- Nó hỗ trợ **major version 55** khi nhận Java 11 bytecode, và các major version cao hơn nếu sản phẩm đang compile bằng JDK mới.
- Nó hiểu và bảo toàn `NestHost`/`NestMembers`, không chỉ `InnerClasses`.
- Nó có cách nhất quán cập nhật các tên class khi relocate.
- Nó kiểm tra method bytecode và `StackMapTable` sau khi thêm instruction.
- Nó quản lý quyền/lookup phù hợp với classloader/module target.

Ví dụ trong API visitor kiểu ASM có tên callback:

```text
visitNestHost(hostInternalName)
visitNestMember(memberInternalName)
```

Đây là tên API minh họa của bytecode toolkit, **không phải chương trình Java SE tự chạy**. Thư viện và phiên bản được chọn phải hỗ trợ các callback này cùng classfile target.

### Không nên hardcode một phiên bản toolkit cũ

Khi dự án target Java 11 nhưng chạy JDK mới, một tool có thể gặp bytecode mới hơn do dependency được build trên JDK cao hơn. Test chỉ input của một project nhỏ ở classfile 55 chưa đủ để đảm bảo agent đọc mọi dependency. Nên có test matrix theo **classfile major cao nhất có thể gặp trong dependency tree** và runtime thật.

**Class-File API của JDK mới** có thể là lựa chọn cho một công cụ được build cho runtime mới, nhưng không tồn tại trong baseline Java 11. Nếu cần code `javac --release 11`, đừng đưa nó vào source chính mà không có cách tách version tương ứng.

## 9. Shading/relocation: sửa đồng bộ mọi tham chiếu tên lớp

Giả sử ban đầu:

```text
lib.core.Outer
lib.core.Outer$Reader
```

Sau khi shade:

```text
app.shaded.lib.core.Outer
app.shaded.lib.core.Outer$Reader
```

Nếu chỉ đổi `Outer` mà giữ member ở package cũ, runtime package không còn phù hợp. Nếu đổi tên cả hai file nhưng không sửa attribute nest, member có thể trỏ tới host cũ không tồn tại hoặc host không công bố member mới.

Cần xem xét:

- Binary class names và class references trong constant pool.
- `NestHost` và `NestMembers`.
- `InnerClasses`/`EnclosingMethod`, metadata generic/annotations cần thiết.
- Field/method descriptors, method handles, invokedynamic/condy references khi có.
- Chuỗi class names được framework đọc qua reflection hoặc config, nếu có.
- `META-INF/services` và resources cho ServiceLoader.
- `module-info.class`/module descriptors khi jar có module.
- Các biến thể của multi-release JAR trong `META-INF/versions/11` hoặc bản khác.
- JAR signatures và manifest nếu có ký artifact.

Đừng nghĩ “đổi tên file class” là relocation đầy đủ. Bytecode phải được cập nhật **ở tất cả nơi mang tham chiếu tới class** theo contract. Artifact có chữ ký số cũng cần kiểm tra lại chữ ký sau khi đổi bytecode; không giữ chữ ký cũ như bằng chứng artifact mới vẫn nguyên vẹn.

### Multi-release JAR

Với một JAR chứa nhiều phiên bản cùng binary name, runtime có thể chọn classfile khác nhau tùy JDK và cờ manifest. Tooling phải xử lý nest metadata ở **các biến thể thực sự được chạy**, không chỉ class mặc định ở root JAR. Đặc biệt, một pipeline build target Java 11 và Java mới cần test đúng phiên bản được classloader chọn.

## 10. Shrinking/obfuscation: giữ topology hoặc cập nhật chính xác

Shrinker được phép loại class không dùng, nhưng có nhiều đường sử dụng **không thể nhìn thấy bằng static call graph**, như reflection, dependency injection, serialization, JNI, annotation scanning hoặc service loading.

Khi xử lý nest, phải bảo đảm:

1. Class còn được gọi thực tế không bị xóa.
2. Nếu class bị xóa hợp lệ, metadata nest của host không còn tham chiếu sai tới member đó khi contract yêu cầu.
3. Các member còn tồn tại có `NestHost` đúng, host còn có `NestMembers` tương ứng.
4. Rename/obfuscate cập nhật references trong attribute cùng bytecode khác.
5. Metadata `InnerClasses`, `EnclosingMethod`, `Signature` và annotations liên quan được giữ/tái tạo nếu framework yêu cầu.
6. Các reflection keep rules dựa trên **cách sử dụng thật**, không theo quy tắc “giữ mọi class có dấu `$`”.

Theo tài liệu ProGuard hiện hành, `NestHost` và `NestMembers` là những **essential class-file attributes** mà ProGuard tự giữ và xử lý nếu cần. Tuy vậy, không suy ra mọi phiên bản hay mọi shrinker khác đều có tính chất đó; phải kiểm tra output thật của công cụ đã chọn.

**Giữ attribute ≠ giữ class.** Một shrinker có thể giữ nest metadata nhưng vẫn loại class không dùng; nếu danh sách host không được cập nhật, reflection có thể lỗi. Ngược lại, giữ tất cả class nhưng bỏ NestHost/NestMembers có thể phá private access.

**Không giữ mọi class tên có dấu `$` chỉ để tránh lỗi**: ngoài nested classes còn có những tên được generator tạo, và giữ tất cả có thể làm artifact phình to. Tạo keep rules theo contract DI/serialization/proxy và thực hiện smoke test sau shrink.

## 11. ClassLoader, JPMS và reflection

### Runtime package thực sự

Hai class có tên `demo.nest.Outer` và `demo.nest.Outer$Member` nhưng do **hai defining class loader khác nhau** định nghĩa sẽ không tự có nestmate access:

```text
ParentLoader:
  demo.nest.Outer

ChildLoader:
  demo.nest.Outer$Member

Tên package giống nhau != cùng runtime package
```

Với ứng dụng plugin hoặc hot loading, đây là nguồn lỗi thường gặp. Ghi classloader identity (và module context nếu cần) trong log chẩn đoán; không log secret.

### JPMS khác nest membership

- `exports` một package cho module khác điều khiển việc truy cập API public theo JPMS.
- `opens` cho phép một số tình huống deep reflection theo chính sách module.
- Một `MethodHandles.Lookup` có quyền phù hợp có thể truy cập các members được phép.

Nhưng **không điều nào tự tạo nestmate relationship**. Một công cụ không được dùng `setAccessible(true)` như giải pháp thay cho việc metadata/classloader sai, nhất là khi module không mở.

### Phản chiếu có thể gặp LinkageError

`Class.getNestMembers()` không chỉ đọc chuỗi tên: runtime có thể cần tải/xác minh các members. Nếu member bị thiếu hoặc khai báo host sai, call reflection có thể gặp `LinkageError`. Không kiểm thử bằng cách chỉ in tên host sau khi thu gọn; hãy thử truy cập private method thực tế và kiểm tra membership.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng chẩn đoán |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Bytecode classfile cao hơn JDK/runtime | Kiểm tra major version bằng javap, runtime JDK |
| `ClassFormatError` | Generator viết constant pool/attribute sai | Inspect classfile theo JVMS, kiểm tra tool |
| `VerifyError` | Instrument method/frames không hợp lệ | Kiểm tra StackMapTable, invokes, branch targets |
| `IllegalAccessError` | Private access không còn hợp lệ | Inspect NestHost/NestMembers, runtime package |
| `IncompatibleClassChangeError` | Linkage hoặc nest relationship sai ở một đường thực thi | Check host/member mapping, loader |
| `NoClassDefFoundError` | JAR thiếu member/class được tham chiếu | `jar tf`, classloader, keep rules |
| `LinkageError` từ getNestMembers | Host/member tham chiếu không nhất quán hoặc không load được | Class file và missing classes |
| `ClassNotFoundException` khi framework scan | Reflected class name sai sau shading | Update config/resource/keep rules |
| Agent không thể retransform | Muốn đổi NestHost/NestMembers sau load | Sửa trước khi define, không hotfix |
| Chạy từ IDE tốt nhưng JAR hỏng | Shader/shrinker/package đã sửa class | Chạy integration test từ final artifact |
| Không có quyền private dù cùng package | Không cùng nest hoặc khác classloader | `isNestmateOf`, `getNestHost`, loader identity |
| Framework mất nested class | Reflection/annotation/InnerClasses bị shrink | Giữ metadata và class theo contract |

Ngoại lệ thực tế phụ thuộc **thời điểm JVM load, link, resolve, verify hoặc thực thi**. Không cam kết một classfile hỏng luôn ném đúng một loại lỗi; ghi lại đường gọi và bytes của artifact đã biên dịch.

## 13. Chiến lược kiểm thử tương thích công cụ trong CI/CD

| Lớp kiểm tra | Việc nên làm |
| --- | --- |
| Source → classfile | Biên dịch `--release 11`, chạy unit test private access |
| Classfile metadata | `javap -v -p` kiểm tra major 55 và Nest attrs |
| Transformer | Chạy dưới agent/tool thật, kiểm tra method/verifier/private access |
| Shading | So class names và references sau relocate, classloader hợp lệ |
| Shrinking | Kiểm tra keep rules, class/member tồn tại và host list |
| Packaging | `jar tf` + `javap` từ **JAR cuối** |
| Runtime reflection | `getNestHost/getNestMembers/isNestmateOf` không lỗi |
| Integration | Chạy đường gọi private thật và framework qua artifact phát hành |
| Version matrix | JDK 11 thật và runtime production mới hơn; tool versions đang dùng |
| Security | Không nới private access, không tắt verifier hoặc mở module vô tội vạ |

**Mẫu quy trình cho ví dụ:**

```bash
javac --release 11 -encoding UTF-8 -d out NestToolingDemo.java
java -cp out demo.nest.NestToolingDemo
javap -v -p -classpath out demo.nest.NestToolingDemo
javap -v -p -classpath out 'demo.nest.NestToolingDemo$Reader'
jar --create --file demo.jar -C out .
jar tf demo.jar
java -cp demo.jar demo.nest.NestToolingDemo
javap -v -p -classpath demo.jar 'demo.nest.NestToolingDemo$Reader'
```

**Phân biệt compiler và runtime:** `javac --release 11` trên JDK mới đảm bảo mức API/classfile target 11, **không tự chứng minh** chương trình chạy trên máy có JDK 11 thật. Nếu sản phẩm tuyên bố hỗ trợ runtime Java 11, CI phải chạy một lượt trên JDK 11 thật, đồng thời có thử nghiệm với JDK production mới.

**Không chỉ kiểm tra target/classes:** test artifact sau agent/shade/shrink, bởi những bước đó có thể thay đổi classfiles dù source ban đầu hoàn toàn chính xác.

## 14. Bài tập và tự kiểm tra

**Bài 1.** Một generator tạo `Outer$Proxy` trong cùng package với `Outer`. Có chắc truy cập được private của Outer? **Không**; tên có dấu `$` và package source không xác lập nest.

**Bài 2.** Member có `NestHost=Outer`, nhưng host không liệt kê member trong `NestMembers`. Quan hệ nest có hợp lệ không? **Không**, thiếu xác nhận hai chiều.

**Bài 3.** Agent đã load `Outer.class` rồi gọi `retransformClasses` để thêm member mới vào NestMembers. Có hợp lệ không? **Không**, API cấm thay đổi nest attributes theo cách này.

**Bài 4.** Load-time transformer có thể tái tạo NestHost/NestMembers trước class definition không? **Có thể**, nếu kết quả hợp lệ và host/member đồng bộ; không dùng kết luận này cho retransform class đã load.

**Bài 5.** Sau shrinking `getNestMembers()` lỗi vì một member đã bị xóa. Nên sửa bằng cách tạo member giả có tên giống không? **Không**. Xác minh giữ class cần thiết, hoặc shrinker cập nhật topology và test đúng contract.

**Bài 6.** Relocate host sang `app.shaded` nhưng để member ở package cũ. Rủi ro? **Mất quan hệ cùng runtime package**, private access có thể lỗi.

**Bài 7.** Hai class tên package giống hệt nhau nhưng được định nghĩa bởi hai class loader khác nhau. Có chắc cùng nest không? **Không**.

**Bài 8.** Tool giữ `InnerClasses` nhưng xóa `NestHost/NestMembers`. Private access của Java 11 còn bảo đảm? **Không**, chúng là hai loại metadata khác nhau.

**Bài 9.** `javap -v` hiển thị major **55** tương ứng target nào? **Java 11**.

**Bài 10.** Vì sao chạy unit test từ thư mục classes chưa đủ? Vì shading/shrinking/packaging có thể đổi classnames/attributes; phải test **JAR sau biến đổi**.

**Bài 11.** `syntheticAccessors=0` chứng minh không còn mọi synthetic method trên Java 11? **Không**, chỉ thấy không có accessor mang prefix đó trong fixture này.

**Bài 12.** Ba API phản chiếu về nest là gì? `getNestHost()`, `getNestMembers()`, `isNestmateOf(...)`.

### Checklist trước khi phát hành

1. Classfile version được bytecode library hỗ trợ?
2. NestHost và NestMembers hai chiều nhất quán?
3. Generated class không dựa vào ký tự `$` để xin quyền private?
4. Host/member trong cùng runtime package/classloader đúng?
5. Agent không đổi nest topology sau load?
6. Relocation sửa references trong class attrs và bytecode?
7. Shrinker giữ classes/metadata cần thiết, loại bỏ tham chiếu không hợp lệ?
8. Các API reflection và framework scanning vẫn hoạt động?
9. Final artifact chạy trên runtime JDK thuộc phạm vi hỗ trợ?
10. Không dùng workaround mở rộng private/module access trái chính sách?

## Tài liệu tham khảo

- [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): thiết kế và động cơ nest-based access từ Java 11.
- [Oracle Java SE 11 — java.lang.Class](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getNestHost`, `getNestMembers`, `isNestmateOf`.
- [JVMS Java SE 25 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): `NestHost`/`NestMembers` và điều kiện classfile.
- [JVMS Java SE 25 — Loading, Linking, Access Control](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): runtime nest membership và private access.
- [Oracle Java SE 11 — Instrumentation](https://docs.oracle.com/en/java/javase/11/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): giới hạn redefine/retransform với Nest attributes.
- [Oracle Java SE 11 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineClass(byte[])`, lookup capabilities và package.
- [Oracle Java SE 25 — java.lang.Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): các API nest vẫn hiện hành.
- [ProGuard Manual — Attributes](https://www.guardsquare.com/manual/configuration/attributes): NestHost và NestMembers thuộc essential attributes trong ProGuard.
- [Oracle Java SE 11 — javap](https://docs.oracle.com/en/java/javase/11/tools/javap.html): disassemble và inspect classfile.
- [Oracle Java SE 11 — jar](https://docs.oracle.com/en/java/javase/11/tools/jar.html): đóng gói và xem JAR.
- [OpenJDK JEP 238 — Multi-Release JAR](https://openjdk.org/jeps/238): biến thể class theo JDK trong cùng artifact.

**Kết luận:** nest-based private access phụ thuộc **metadata của classfile và class identity khi JVM load**, không chỉ source hoặc tên chứa `$`. Công cụ sinh lớp, javaagent, shader và shrinker phải bảo toàn hoặc tái tạo hợp lệ `NestHost/NestMembers` cùng các tham chiếu liên quan. Hãy dùng `javap`, reflection và private-access smoke test, đặc biệt **sau đóng artifact**, để chứng minh ứng dụng Java 11+ còn hoạt động đúng.