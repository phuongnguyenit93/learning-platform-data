# Thực hành: Quan sát cấu trúc nest và dynamic constant bằng bytecode (Java 11+)

**Chủ đề:** Java 11 — Thực hành. **Mục tiêu:** tự tạo tệp `.class`, đọc bytecode bằng `javap`, nhận diện hai cơ chế ở mức JVM: *nest-based access control* (nhóm các lớp được quyền truy cập thành viên `private` của nhau) và *dynamic constant / condy* (hằng được JVM phân giải qua bootstrap method). Đây là các cơ chế vẫn được JVM hiện đại hỗ trợ; bài tập sử dụng class-file version 55 của Java 11 để quan sát rõ ràng.

## 1. Chuẩn bị và tiêu chí quan sát

Cần JDK 11 trở lên có `java`, `javac`, `javap`. Với phần tạo dynamic constant, cần Maven 3.6.3+ và thư viện ASM công khai (`org.ow2.asm:asm:9.11.1`). Thực hành trên JDK mới vẫn biên dịch mã nguồn cho Java 11 bằng `--release 11` hoặc cấu hình Maven tương đương. Chạy các lệnh trong thư mục chứa tệp của bài tương ứng.

Sau bài học, bạn cần tự chỉ ra được:

1. Class nào là *nest host*, class nào là *nest member* và tìm `NestMembers` / `NestHost` trong `javap -v`.
2. Lệnh bytecode nào gọi trực tiếp một phương thức `private` của nestmate, và vì sao truy cập đó hợp lệ.
3. Mục `CONSTANT_Dynamic`, `BootstrapMethods` và lệnh `ldc` trong tệp `.class` được tạo.
4. Tại sao bootstrap của một constant được phân giải một lần cho cùng mục trong runtime constant pool, dù mã gọi phương thức chứa `ldc` nhiều lần.

`javap -v -p` hiển thị constant pool, phiên bản class, attributes và phương thức riêng tư; `javap -c -p` tập trung vào mã lệnh. Số thứ tự dạng `#7`, `#17` trong constant pool có thể thay đổi theo công cụ biên dịch: hãy so sánh **tên thuộc tính, loại mục, descriptor và opcode**, không dựa vào chỉ số cố định.

## 2. Nest là gì và JVM kiểm tra ra sao?

Trong Java, lớp lồng nhau thường được biên dịch thành các tệp `.class` riêng. Từ Java 11 (JEP 181), JVM có khái niệm **nest**: một nhóm lớp/interface có cùng nest host và có thể truy cập trực tiếp các thành viên `private` của nhau theo kiểm tra truy cập ở JVM. Quy tắc truy cập `private` của ngôn ngữ Java không đổi; JVM hiểu quan hệ giữa các class file thay vì buộc compiler tạo phương thức cầu nối cho truy cập của lớp lồng nhau.

Một nest được mô tả bằng hai class-level attributes (class-file major version **55**, tức Java 11):

- **`NestMembers`**: xuất hiện trên **host**, liệt kê các class/interface được host cho phép tuyên bố là thành viên.
- **`NestHost`**: xuất hiện trên **member**, chỉ tên host mà class đó tuyên bố thuộc về. Host chính là thành viên trong nest của mình, không có đồng thời cả `NestHost` và `NestMembers` trên cùng class.

JVM chỉ công nhận quan hệ hợp lệ khi member trỏ đúng host, host cho phép member, và các lớp có cùng *runtime package* (cùng tên package **và** class loader xác định package lúc chạy). Trường hợp không có `NestHost`, lớp tự làm host của mình; quan hệ riêng lẻ này vẫn hợp lệ. `InnerClasses` chỉ mô tả thông tin lớp lồng nhau ở mức class file, **không tự cấp quyền truy cập private**.

Java có API phản chiếu hữu ích từ Java 11: `Class.getNestHost()`, `Class.getNestMembers()`, `Class.isNestmateOf(Class<?>)`. Chúng giúp kiểm chứng nest mà không cần suy đoán từ tên tệp có dấu `$`.

## 3. Lab A — Biên dịch lớp lồng nhau rồi đọc bytecode

Tạo tệp **`NestBytecodeLab.java`** tại thư mục mới:

~~~java
public class NestBytecodeLab {
    private static int secret = 42;

    private static String secretText() {
        return "nest=" + secret;
    }

    static class Inner {
        static String readHost() {
            return secretText();
        }
    }

    public static void main(String[] args) {
        System.out.println(Inner.readHost());
        System.out.println(Inner.class.getNestHost() == NestBytecodeLab.class);
        System.out.println(NestBytecodeLab.class.isNestmateOf(Inner.class));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 11 NestBytecodeLab.java
java NestBytecodeLab
~~~

**Kết quả stdout đã kiểm chứng:**

~~~text
nest=42
true
true
~~~

Các class file được sinh ra là `NestBytecodeLab.class` và `NestBytecodeLab$Inner.class`. Để tránh shell hiểu dấu `$` trong tên lớp, đặt tên lớp thứ hai trong dấu nháy đơn trên Bash/PowerShell (nếu dùng Windows `cmd.exe`, thay bằng nháy kép):

~~~bash
javap -v -p NestBytecodeLab
javap -v -p 'NestBytecodeLab$Inner'
javap -c -p 'NestBytecodeLab$Inner'
~~~

**Điểm phải tìm trong kết quả** (đây là phần trích đại diện, không phải toàn bộ đầu ra của `javap`):

~~~text
// NestBytecodeLab.class
major version: 55
NestMembers:
  NestBytecodeLab$Inner

// NestBytecodeLab$Inner.class
major version: 55
NestHost: class NestBytecodeLab

// Phương thức Inner.readHost()
0: invokestatic #... // Method NestBytecodeLab.secretText:()Ljava/lang/String;
~~~

Ý nghĩa của từng dấu hiệu:

- Major 55 chứng minh class file dùng định dạng Java 11. JDK mới có thể tạo major khác nếu bỏ `--release 11`.
- `NestMembers` nằm trong host; `NestHost` nằm trong member. Quan hệ này là dữ liệu class file mà JVM dùng khi kiểm tra truy cập.
- `invokestatic` gọi **trực tiếp** `NestBytecodeLab.secretText()`, dù phương thức đó khai báo `private` ở host. Đây là kết quả quan sát quan trọng nhất về nestmate.
- Dòng trong constant pool kiểu `Methodref` trỏ tới phương thức gọi; nó không phải lời gọi thông qua một phương thức `access$...` trung gian.

Thử mở rộng bằng cách thêm `static class AnotherInner` vào host, biên dịch lại và quan sát danh sách `NestMembers` thay đổi. Sau đó in `NestBytecodeLab.class.getNestMembers()` để đối chiếu dữ liệu phản chiếu với thông tin class file. Không cần thay đổi quyền truy cập `private` chỉ để lớp lồng nhau đọc được thành viên hợp lệ trong cùng nest.

## 4. Dynamic constant là gì?

**Dynamic constant (condy, JEP 309)** là một mục trong constant pool kiểu **`CONSTANT_Dynamic` (tag 17)**, được JVM phân giải thành giá trị qua một *bootstrap method* khi có yêu cầu sử dụng. Trong `javap -v`, mục `Dynamic` tham chiếu tới:

- Chỉ số của bootstrap method trong bảng thuộc tính **`BootstrapMethods`**.
- Một `NameAndType` chứa **tên** và **field descriptor** của hằng, ví dụ `GREETING:Ljava/lang/String;`.
- Bootstrap method handle; bootstrap có thể nhận thêm các đối số tĩnh nếu class file mô tả chúng.

Đối với ví dụ dùng `ldc`, luồng xử lý có thể hình dung:

~~~text
bytecode: ldc #k
     |
     v
runtime constant pool: CONSTANT_Dynamic (tag 17)
     |
     v
BootstrapMethods -> method handle + optional static arguments
     |
     v
JVM gọi bootstrap để phân giải -> kiểm tra kiểu -> giữ kết quả phân giải
     |
     v
ldc đẩy giá trị lên operand stack
~~~

Bootstrap thông dụng nhận ba tham số do JVM cung cấp: `MethodHandles.Lookup` của class yêu cầu phân giải, `String` tên hằng, và `Class<?>` kiểu hằng cần tạo. Bootstrap trả về giá trị tương thích với descriptor; ví dụ dưới đây trả về `String`. Các đối số bổ sung, nếu có, đứng sau ba tham số đó. JDK còn cung cấp `java.lang.invoke.ConstantBootstraps` với các bootstrap chuẩn như `nullConstant`, `primitiveClass`, `enumConstant` và `getStaticFinal`.

**Không nhầm ba khái niệm:**

| Khái niệm | Trong class file / bytecode | Tác dụng |
| --- | --- | --- |
| `CONSTANT_String` hoặc hằng số thông thường | Mục constant pool có giá trị đã được biểu diễn tĩnh | `ldc` nạp hằng có sẵn |
| `CONSTANT_Dynamic` (tag 17) | Mục `Dynamic` + `BootstrapMethods`; thường được nạp bằng `ldc` (hoặc `ldc_w`, `ldc2_w` tùy kiểu/độ lớn chỉ số) | Phân giải **giá trị** hằng qua bootstrap |
| `CONSTANT_InvokeDynamic` (tag 18) | Mục `InvokeDynamic` + opcode `invokedynamic` | Phân giải **call site** để thực hiện lời gọi động |

Condy **không đồng nghĩa** với một trường `static final`, không đồng nghĩa với `invokedynamic`, và không có nghĩa bootstrap được chạy lại mỗi lần thực thi `ldc`. Cùng một mục trong runtime constant pool được phân giải rồi tái sử dụng trong phạm vi class tương ứng; cơ chế phân giải cũng ghi nhận lỗi nếu phân giải thất bại. Một class được nạp riêng bởi class loader khác sẽ có runtime constant pool riêng.

Trình biên dịch `javac` **không tự sinh ví dụ condy đơn giản từ một chuỗi Java thông thường**. Vì mục tiêu là xem chính xác `CONSTANT_Dynamic`, ta sẽ dùng ASM để tạo class file hợp lệ, sau đó dùng `javap` và JVM quan sát.

## 5. Lab B — Tự tạo `CONSTANT_Dynamic` bằng ASM rồi quan sát `ldc`

Tạo dự án Maven nhỏ có cấu trúc:

~~~text
condy-lab/
├── pom.xml
└── src/main/java/CondyLab.java
~~~

Nội dung **`pom.xml`**: biên dịch nguồn tương thích Java 11 và dùng ASM 9.11.1 (phiên bản phát hành tháng 10/2026). Đây là API ASM công khai; không dùng các package `jdk.internal.*`.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>condy-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>11</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.11.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung **`src/main/java/CondyLab.java`**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.ConstantDynamic;
import org.objectweb.asm.Handle;
import org.objectweb.asm.MethodVisitor;

import static org.objectweb.asm.Opcodes.*;

public class CondyLab {
    private static int calls;

    // Bootstrap method public, có chữ ký khớp handle trong class file.
    public static String resolve(MethodHandles.Lookup caller, String name, Class<?> type) {
        calls++;
        System.out.println("bootstrap: " + name + ", type=" + type.getSimpleName()
                + ", count=" + calls);
        return "Hello from " + name;
    }

    public static void main(String[] args) throws Exception {
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        writer.visit(V11, ACC_PUBLIC | ACC_SUPER,
                "GeneratedCondy", null, "java/lang/Object", null);

        Handle bootstrap = new Handle(
                H_INVOKESTATIC,
                "CondyLab",
                "resolve",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;",
                false
        );

        ConstantDynamic constant = new ConstantDynamic(
                "GREETING", "Ljava/lang/String;", bootstrap);

        MethodVisitor method = writer.visitMethod(
                ACC_PUBLIC | ACC_STATIC, "message", "()Ljava/lang/String;", null, null);
        method.visitCode();
        method.visitLdcInsn(constant);
        method.visitInsn(ARETURN);
        method.visitMaxs(0, 0);  // ASM tự tính kích thước stack/local vì COMPUTE_MAXS.
        method.visitEnd();
        writer.visitEnd();

        Path output = Path.of("generated");
        Files.createDirectories(output);
        Files.write(output.resolve("GeneratedCondy.class"), writer.toByteArray());

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{output.toUri().toURL()}, CondyLab.class.getClassLoader())) {
            Class<?> generated = Class.forName("GeneratedCondy", true, loader);
            Method message = generated.getMethod("message");
            System.out.println("call1: " + message.invoke(null));
            System.out.println("call2: " + message.invoke(null));
        }
    }
}
~~~

Giải thích các phần quan trọng:

1. `writer.visit(V11, ...)` tạo class file major 55. Class `GeneratedCondy` chỉ cần một phương thức tĩnh `message()` trong ví dụ này.
2. `Handle(H_INVOKESTATIC, ...)` định nghĩa bootstrap có thể gọi được: `CondyLab.resolve(Lookup, String, Class) : String`. Chuỗi descriptor dùng định dạng kiểu JVM (`L...;`) và tên nhị phân nội bộ có dấu `/`.
3. `new ConstantDynamic("GREETING", "Ljava/lang/String;", bootstrap)` yêu cầu một giá trị `String` mang tên tượng trưng `GREETING`.
4. `visitLdcInsn(constant)` phát bytecode nạp dynamic constant, không phát opcode `invokedynamic`. `ARETURN` trả `String` vừa nạp.
5. Mã ghi `GeneratedCondy.class` rồi nạp và gọi phương thức của nó bằng một `URLClassLoader`; hai lần gọi giúp kiểm tra số lần bootstrap được thực thi. `caller` là đối số `Lookup` do JVM truyền vào; ví dụ không cần sử dụng nó.

Chạy **tại thư mục chứa `pom.xml`** (dấu nháy kép quanh tham số cuối dùng được trên Bash/PowerShell/Windows cmd):

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=CondyLab"
~~~

**Stdout đã kiểm chứng** với JDK hiện đại, biên dịch ở `--release 11`:

~~~text
bootstrap: GREETING, type=String, count=1
call1: Hello from GREETING
call2: Hello from GREETING
~~~

Dòng `bootstrap` chỉ xuất hiện **một lần**, dù `message()` được gọi hai lần: mỗi lần gọi phương thức vẫn đi qua `ldc`, nhưng tham chiếu `CONSTANT_Dynamic` tương ứng đã được phân giải. Đây là caching tại mức symbolic reference của JVM, không phải do biến `calls` tự nhớ giá trị. Counter chỉ là dụng cụ quan sát.

Giờ đọc class file thực sự đã sinh ra:

~~~bash
javap -v -p generated/GeneratedCondy.class
javap -c -p generated/GeneratedCondy.class
~~~

Trong đầu ra `-v`, tìm các mốc sau (chỉ số `#...` và cách trình bày chú thích có thể khác):

~~~text
major version: 55
#... = Dynamic       #0:#...  // #0:GREETING:Ljava/lang/String;
...
public static java.lang.String message();
  Code:
     0: ldc           #...    // Dynamic #0:GREETING:Ljava/lang/String;
     2: areturn
...
BootstrapMethods:
  0: #... REF_invokeStatic CondyLab.resolve:(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;
~~~

Cách lần dấu theo thứ tự: từ opcode **`ldc`** → chỉ số mục **`Dynamic`** trong constant pool → `NameAndType` (`GREETING`, `Ljava/lang/String;`) → mục số 0 trong **`BootstrapMethods`** → method handle **`REF_invokeStatic`** trỏ tới `CondyLab.resolve`. Chính chuỗi bằng chứng này chứng minh đây là dynamic constant, thay vì một literal String.

## 6. So sánh kết quả hai lab và những điều không được suy diễn

| Câu hỏi | Nest (Lab A) | Dynamic constant (Lab B) |
| --- | --- | --- |
| Dữ liệu xác nhận trong `javap -v` | `NestMembers` của host và `NestHost` của member | `Dynamic` trong constant pool và `BootstrapMethods` |
| Hành vi bytecode nổi bật | `invokestatic` gọi phương thức `private` của nestmate | `ldc` nạp giá trị đã/đang được phân giải từ bootstrap |
| Cơ chế JVM liên quan | Kiểm tra quyền truy cập giữa các class trong nest | Phân giải symbolic reference và kiểm tra kiểu giá trị |
| Cách kiểm chứng khi chạy | `getNestHost()` / `isNestmateOf()` trả đúng; gọi private thành công | Log bootstrap một lần; hai lời gọi trả cùng giá trị |
| Ranh giới cần nhớ | Host/member phải được xác thực và cùng runtime package | Hằng được phân giải theo từng mục runtime constant pool, không theo số lần thực thi `ldc` |

**Các ngộ nhận hay gặp:**

- “Tên `Outer$Inner` tự chứng minh cùng nest”: sai; tên chỉ gợi ý cấu trúc. Kiểm tra hai attributes và, nếu cần, API phản chiếu.
- “Chỉ cần `InnerClasses` là có quyền `private`”: sai; JVM dựa vào quy tắc nest khi cấp quyền nestmate.
- “`CONSTANT_Dynamic` gọi bootstrap mỗi lần lấy hằng”: sai; phân giải kết quả của cùng mục runtime constant pool được dùng lại.
- “`Dynamic` và `InvokeDynamic` giống nhau”: sai; một bên tạo **giá trị** dùng bởi `ldc`, bên kia phân giải **call site** cho `invokedynamic`.
- “Cứ khai báo `static final` trong Java thì `javap` phải hiện `Dynamic`”: sai; nhiều giá trị được biên dịch bằng literal, `ConstantValue` hoặc bytecode khởi tạo thông thường.
- “Java 11 là runtime tối đa dùng cho class 55”: sai; JVM mới vẫn có thể nạp class file Java 11 phù hợp. Ngược lại, JVM không hỗ trợ major 55 không thể chạy class file đó.

## 7. Xử lý lỗi khi tự chạy

- **`javap` không tìm thấy class:** kiểm tra tên tệp, thư mục chạy và classpath; với tên có `$` hãy đặt dấu nháy phù hợp shell. Cần cài **JDK** để có `javap`, chỉ JRE có thể không đủ.
- **Không thấy major 55:** kiểm tra lệnh `javac --release 11` hoặc `maven.compiler.release`. Đừng nhầm version của JDK đang chạy với version của class file.
- **Không thấy `NestHost` / `NestMembers`:** chắc chắn đang xem cả hai tệp `.class` của Lab A được biên dịch lại, không phải tệp khác tên hoặc build cũ.
- **Không thấy `Dynamic`:** bạn phải xem `generated/GeneratedCondy.class` do ASM ghi, không phải `CondyLab.class` (chỉ chứa mã *tạo* class). Sự xuất hiện của `invokedynamic` cho string concatenation trong một class khác không thay thế bằng chứng condy.
- **`BootstrapMethodError` hoặc `IllegalAccessError`:** kiểm tra descriptor, kiểu giá trị trả về, tính truy cập của bootstrap method, và quan hệ host/member. Khi gọi bằng reflection, lỗi trong phương thức có thể được bọc trong `InvocationTargetException`; đọc `getCause()` để tìm lỗi gốc. Không sửa bằng cách vô hiệu hóa kiểm tra truy cập hoặc dùng API nội bộ JDK.
- **Maven không tải được ASM:** kiểm tra kết nối tới Maven Central và phiên bản artifact, rồi chạy lại khi dependency có sẵn.

## 8. Tự kiểm tra hiểu bài

1. Trong Lab A, bạn tìm `NestMembers` ở tệp nào, `NestHost` ở tệp nào? Opcode nào chứng tỏ `Inner` gọi trực tiếp `private secretText()`?
2. Vì sao `InnerClasses` và tên tệp có dấu `$` chưa đủ để kết luận hai class là nestmates?
3. Trong Lab B, hãy chỉ ra đồng thời dòng `Dynamic`, opcode `ldc` và bảng `BootstrapMethods`; ba dấu hiệu liên kết với nhau bằng những chỉ số nào?
4. Thay tên `GREETING` thành `TITLE` trong constructor `ConstantDynamic`, chạy lại và dự đoán chính xác các dòng stdout. Sau đó giải thích tại sao vẫn chỉ có một dòng log bootstrap.
5. Nếu tạo **hai mục `ConstantDynamic` khác nhau** và dùng cả hai, nên dự đoán gì về số lần bootstrap? (Gợi ý: việc phân giải được gắn với từng mục runtime constant pool; những mục khác nhau có thể được phân giải riêng.)

**Tiêu chí hoàn thành:** có đủ hai cặp bằng chứng, gồm (a) `NestMembers` + `NestHost` và direct `invokestatic`; (b) `Dynamic` + `BootstrapMethods` + `ldc`, cùng stdout chứng minh bootstrap chỉ chạy một lần cho ví dụ hai lời gọi. Bạn phải giải thích được *vì sao* JVM xử lý như vậy, không chỉ nhận ra từ khóa.

## 9. Tài liệu tham chiếu đang áp dụng

- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): mục đích và cơ chế truy cập giữa nestmates.
- [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309): mục tiêu và thiết kế condy.
- [Java Virtual Machine Specification, `4.7.28 và `4.7.29](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.7.28): thuộc tính `NestHost` / `NestMembers`.
- [Java Virtual Machine Specification, `4.4.10](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.4.10): cấu trúc `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`.
- [JDK 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): bootstrap chuẩn từ Java 11.
- [ASM — release versions](https://asm.ow2.io/versions.html): phiên bản thư viện tạo/phân tích bytecode; mẫu dùng ASM 9.11.1.

Các thuộc tính nest và condy được giới thiệu ở Java 11 và tiếp tục là thành phần của định dạng class file/JVM hiện đại. Các ví dụ dùng công cụ và API công khai, tránh các giải pháp đã lỗi thời hoặc chỉ dành cho nội bộ JDK.