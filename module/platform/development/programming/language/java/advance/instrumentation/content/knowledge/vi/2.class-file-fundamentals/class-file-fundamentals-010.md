# Dùng `javap` để đọc bytecode trước và sau khi chèn mã

Trong Java instrumentation, một biến đổi bytecode có thể làm chương trình ghi thêm log, đo thời gian, gọi hook hoặc thay đổi logic. Cách đầu tiên để xác minh **thực sự có lệnh được chèn** là lấy hai bản `.class` — **trước** và **sau** biến đổi — rồi dùng công cụ chuẩn của JDK là **`javap`** để giải mã và đối chiếu.

Bài thực hành này dùng **Java 17+**, `javap` và thư viện **ASM** để tạo một lớp `.class` mới theo cách có thể tái lập. Trọng tâm là **đọc, so sánh và diễn giải kết quả `javap`**. Không cần Java agent chạy trong JVM ở ví dụ chính: biến đổi **offline** giúp lưu hai bản class file rõ ràng, dễ kiểm chứng.

## 1. Bạn cần hiểu và kiểm tra được gì?

Sau bài này, bạn có thể:

1. Xác định **đúng tệp `.class`** mà `javap` đang đọc, tránh nhầm bản được biên dịch, bản trong JAR hoặc bản đã instrument.
2. Đọc **method descriptor**, lệnh JVM, bytecode offset, tham chiếu constant pool và các thông tin `stack`/`locals`/`args_size`.
3. Giải thích việc chèn lệnh làm thay đổi **operand stack**, `max_stack`, độ dài mã và các offsets thế nào.
4. So sánh **trước/sau** với một ví dụ bytecode có hành vi quan sát được, đồng thời kiểm tra chương trình **vẫn trả đúng giá trị**.
5. Nhận ra giới hạn của `javap`: nó đọc **class file hoặc class được cung cấp qua classpath/module**, không tự nhìn thấy bytecode chỉ tồn tại trong bộ nhớ JVM sau khi một Java agent biến đổi lúc tải lớp.

> Trong bài, từ **chèn mã** chỉ việc thêm **lệnh JVM** vào một phương thức đã biên dịch. Việc thêm `System.out.println(...)` vào **mã nguồn rồi biên dịch lại** cũng làm bytecode thay đổi, nhưng chưa chứng minh được một transformer đã sửa trực tiếp `.class`.

## 2. `javap` đọc gì, và output có ý nghĩa gì?

`javap` là **class file disassembler** đi kèm JDK. Nó hiển thị cấu trúc lớp và, với `-c`, các chỉ thị JVM nằm trong `Code` attribute của từng phương thức có thân. Công cụ này **không decompile chính xác về Java source**; mã nguồn nhiều cấu trúc cao cấp có thể tạo ra cùng kiểu bytecode, và debug metadata có thể bị lược bỏ.

### 2.1. Các tùy chọn nên biết

| Tùy chọn | Dùng để xem | Lưu ý |
| --- | --- | --- |
| `-c` | Liệt kê chỉ thị bytecode của các phương thức | Offset là **vị trí byte**, không phải số thứ tự lệnh |
| `-v` hoặc `-verbose` | Header class, constant pool, `Code` chi tiết, `stack`, `locals`, attributes | Output dài; rất hữu ích để đối chiếu trước/sau |
| `-p` hoặc `-private` | Hiển thị cả thành viên `private` | Có ích để không bỏ sót helper/constructor được biến đổi |
| `-l` | Bảng dòng nguồn và biến cục bộ nếu được ghi trong class file | `LocalVariableTable` không bắt buộc phải có |
| `-s` | Descriptor ở định dạng JVM | Ví dụ `(II)I`: hai tham số `int`, trả `int` |
| `-classpath` hoặc `-cp` | Chọn đường dẫn tìm `.class`/JAR | Thường là điểm mấu chốt khi so sánh nhiều bản |
| `-sysinfo` | Đường dẫn, kích thước, thời gian và SHA-256 của class được đọc | Giúp đối chiếu nguồn gốc/snapshot |
| `--multi-release 17` | Chọn class version phù hợp trong multi-release JAR | Dùng khi so sánh các mục `META-INF/versions/...` |
| `-version` | In phiên bản `javap` | Hữu ích khi các máy có nhiều JDK |

Một lệnh xem tổng quan:

```bash
javap -version
javap -classpath target/classes -p -c -l demo.Calculator
javap -classpath target/classes -p -s demo.Calculator
javap -classpath target/classes -p -v demo.Calculator
javap -classpath target/classes -sysinfo demo.Calculator
```

**Cách đọc một dòng bytecode**:

```text
4: iload_2
5: ireturn
```

`4` và `5` là offset trong mảng bytecode `code[]`, `iload_2` đọc local variable slot `2` rồi đẩy số nguyên lên operand stack, còn `ireturn` lấy số nguyên trên đỉnh stack và kết thúc phương thức với kết quả đó. Một lệnh như `invokestatic` thường dài 3 byte, nên offsets **không nhất thiết tăng từng 1**.

### 2.2. Descriptor, constant pool và frame

Với phương thức `static int add(int a, int b)`:

- Descriptor JVM là **`(II)I`**. `I` là kiểu `int`; dấu ngoặc chứa các tham số, ký hiệu cuối là kiểu trả về. `V` biểu diễn `void`, `J` là `long`, `Ljava/lang/String;` là reference tới `String`.
- `javap -v` có thể in `stack=2, locals=3, args_size=2` cho thân phương thức ta sắp biên dịch: operand stack đạt tối đa **2 đơn vị**; local array có **3 slot** (hai tham số và một biến tạm); có hai tham số tính theo số local slots cho static method này.
- Operand stack và local array là hai phần của **frame cho một lần gọi phương thức**. `iload`/`istore` chuyển giá trị giữa hai nơi. `getstatic`, `invokevirtual` và `ireturn` tác động lên operand stack theo descriptor.
- Các chú thích như `#7 // Method java/io/PrintStream.println:(I)V` tham chiếu constant pool; **chỉ số `#7` không phải ID cố định** khi tái tạo class. Cần so **ý nghĩa lệnh + owner/name/descriptor**, không chỉ so số `#n`.

`javap -l` chỉ có `LineNumberTable`/`LocalVariableTable` nếu compiler ghi chúng. Đừng coi vắng tên biến hoặc thay đổi số dòng là bằng chứng lỗi biến đổi bytecode.

## 3. Quy trình so sánh không bị nhầm phiên bản

```text
Mã Java ban đầu
      │ javac (Java 17 target)
      ▼
target/classes/demo/Calculator.class          ← BEFORE
      │ đọc ClassReader, chèn các JVM instructions, xuất ClassWriter
      ▼
target/modified/demo/Calculator.class         ← AFTER
      │
      ├── javap -classpath target/classes  ... demo.Calculator
      └── javap -classpath target/modified ... demo.Calculator
                           │
                           ▼
                  So opcode + Code + metadata
                           │
                           ▼
               Chạy before/after để đối chiếu hành vi
```

Giữ hai thư mục đầu ra **khác nhau** và không ghi đè `target/classes/demo/Calculator.class`. Khi chẩn đoán kết quả, trình tự quan trọng là: **chọn đúng class file → so `javap` → chạy thực tế → giải thích khác biệt**. Lệnh `javap` không chạy phương thức đang giải mã.

Ở dự án thực, có thể dùng bytecode snapshot từ build pipeline hay kết quả `ClassFileTransformer`; điểm cốt lõi là xác định chính xác nguồn bytes của bản BEFORE và AFTER.

## 4. Thực hành đầy đủ: chèn log bằng ASM rồi đọc `javap`

### 4.1. Chuẩn bị công cụ và cấu trúc tệp

Cần **JDK 17 trở lên** (`javac`, `java`, `javap`) và **Apache Maven** để tải ASM. Dự án này nhắm **class file Java 17** bằng `<maven.compiler.release>17</maven.compiler.release>`, nên chạy được bằng JDK 17+.

```text
javap-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── Calculator.java
                ├── DemoMain.java
                └── BytecodePatch.java
```

Trong thư mục `javap-demo`, tạo đúng bốn tệp sau.

**`pom.xml`** — khai báo dependency ASM 9.7.1 và cấu hình build:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>javap-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/Calculator.java`** — phương thức cần instrument:

```java
package demo;

public final class Calculator {
    private Calculator() {}

    public static int add(int a, int b) {
        int sum = a + b;
        return sum;
    }
}
```

**`src/main/java/demo/DemoMain.java`** — chương trình gọi phương thức:

```java
package demo;

public final class DemoMain {
    private DemoMain() {}

    public static void main(String[] args) {
        System.out.println("result=" + Calculator.add(3, 4));
    }
}
```

Biên dịch từ thư mục `javap-demo`:

```bash
mvn -q -DskipTests package
java -cp target/classes demo.DemoMain
javap -classpath target/classes -p -c -l demo.Calculator
javap -classpath target/classes -p -v demo.Calculator
```

Stdout **chính xác của lệnh `java -cp target/classes demo.DemoMain`**:

```text
result=7
```

Trong `javap -c`, đoạn bytecode của **`add`** do `javac` phát sinh ở trường hợp này là:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: ireturn
```

Đây là **trích đoạn** phương thức `add`, không phải toàn bộ stdout `javap`: class còn constructor và các phần metadata khác.

Theo vết:

| Offset | Lệnh | Operand stack sau lệnh | Local slots chính |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `[a]` | `0=a, 1=b, 2=chưa gán` |
| 1 | `iload_1` | `[a, b]` | Không đổi |
| 2 | `iadd` | `[a+b]` | Không đổi |
| 3 | `istore_2` | `[]` | `2=a+b` |
| 4 | `iload_2` | `[a+b]` | Không đổi |
| 5 | `ireturn` | Kết thúc frame | Trả `a+b` |

Vì hai toán hạng `int` cùng xuất hiện trước `iadd`, **`max_stack` là 2**. Có hai tham số và một biến tạm, nên **`max_locals` là 3**. `javap -v` thể hiện chúng tương ứng bằng `stack=2` và `locals=3`.

### 4.2. Tạo transformer chèn log mà vẫn bảo toàn kết quả

**`src/main/java/demo/BytecodePatch.java`** — chương trình Java độc lập chạy offline, **không sửa file input**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class BytecodePatch {
    private BytecodePatch() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: BytecodePatch <input.class> <output.class>");
        }

        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);
        ClassReader reader = new ClassReader(Files.readAllBytes(input));
        ClassWriter writer = new ClassWriter(
            ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);

        final boolean[] found = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {
                MethodVisitor next = super.visitMethod(
                    access, name, descriptor, signature, exceptions);

                if (next == null || !name.equals("add")
                        || !descriptor.equals("(II)I")) {
                    return next;
                }
                found[0] = true;

                return new MethodVisitor(Opcodes.ASM9, next) {
                    @Override
                    public void visitCode() {
                        super.visitCode();

                        // System.out.println(">> add"); lúc bắt đầu method
                        super.visitFieldInsn(
                            Opcodes.GETSTATIC, "java/lang/System",
                            "out", "Ljava/io/PrintStream;");
                        super.visitLdcInsn(">> add");
                        super.visitMethodInsn(
                            Opcodes.INVOKEVIRTUAL, "java/io/PrintStream",
                            "println", "(Ljava/lang/String;)V", false);
                    }

                    @Override
                    public void visitInsn(int opcode) {
                        if (opcode == Opcodes.IRETURN) {
                            // Stack ban đầu: [result:int]
                            super.visitInsn(Opcodes.DUP);
                            // Stack: [result, result]
                            super.visitFieldInsn(
                                Opcodes.GETSTATIC, "java/lang/System",
                                "out", "Ljava/io/PrintStream;");
                            // Stack: [result, result, PrintStream]
                            super.visitInsn(Opcodes.SWAP);
                            // Stack: [result, PrintStream, result]
                            super.visitMethodInsn(
                                Opcodes.INVOKEVIRTUAL,
                                "java/io/PrintStream", "println",
                                "(I)V", false);
                            // Stack: [result] để IRETURN sử dụng
                        }
                        super.visitInsn(opcode);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.SKIP_FRAMES);
        if (!found[0]) {
            throw new IllegalStateException("Method add(II)I not found");
        }
        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.write(output, writer.toByteArray());
    }
}
```

**Cơ chế cần hiểu trước khi đọc kết quả:**

- `ClassReader` phát ra các sự kiện khi đọc cấu trúc `.class`; `ClassVisitor` duyệt phương thức; `MethodVisitor` thêm lệnh chỉ khi **tên `add` và descriptor `(II)I`** khớp. Các phương thức khác được chuyển tiếp nguyên logic.
- `visitCode()` chèn `System.out.println(">> add")` **ở đầu thân phương thức**. Nó dùng `getstatic` để đẩy `System.out`, `ldc` để đẩy chuỗi và `invokevirtual PrintStream.println(String)` để tiêu thụ hai toán hạng.
- `visitInsn(IRETURN)` gặp lệnh trả `int` và chèn `dup`, `getstatic`, `swap`, `invokevirtual PrintStream.println(int)` **trước** `ireturn`. `dup` giữ lại một bản kết quả để `ireturn` vẫn có `int` cần trả.
- `COMPUTE_MAXS | COMPUTE_FRAMES` yêu cầu ASM tính lại độ sâu stack/locals và stack-map frames. `SKIP_FRAMES` bỏ qua các frame cũ trong khi đọc để ASM dựng lại. Ví dụ chỉ có các kiểu JDK rất đơn giản; với class phức tạp, việc tính frames vẫn cần phân giải kiểu/class hierarchy phù hợp.
- Đây là minh họa **không idempotent**: chạy transformer lên chính bản đã instrument sẽ thêm log lần nữa. Luôn lấy bản BEFORE làm input và ghi ra một path khác.

### 4.3. Ghi bản AFTER và kiểm tra output bằng `javap`

Sau khi lưu đủ ba tệp Java và biên dịch ở mục 4.1, chạy:

```bash
mvn -q exec:java -Dexec.mainClass=demo.BytecodePatch -Dexec.args="target/classes/demo/Calculator.class target/modified/demo/Calculator.class"

javap -classpath target/modified -p -c -l demo.Calculator
javap -classpath target/modified -p -v demo.Calculator
javap -classpath target/modified -sysinfo demo.Calculator
```

`target/classes/demo/Calculator.class` **vẫn là BEFORE**, còn `target/modified/demo/Calculator.class` là **AFTER**. Trong kết quả `javap -c`, các chuỗi lệnh mới xuất hiện trong `add` theo thứ tự này (bỏ qua một số offset và chỉ số `#n` vì chúng do writer đánh lại):

```text
getstatic     java/lang/System.out:Ljava/io/PrintStream;
ldc           ">> add"
invokevirtual java/io/PrintStream.println:(Ljava/lang/String;)V

iload_0
iload_1
iadd
istore_2
iload_2

dup
getstatic     java/lang/System.out:Ljava/io/PrintStream;
swap
invokevirtual java/io/PrintStream.println:(I)V
ireturn
```

**Đây là sơ đồ opcode đã giản lược để thấy trình tự**, không phải nguyên văn output `javap`. Trong output thật, `getstatic` và `invokevirtual` đi kèm constant-pool index như `#12`; `ldc` có chú thích `// String >> add`; offsets dịch chuyển sau khi chèn lệnh.

Với ví dụ cụ thể, `javap -v` sẽ cho thấy **`locals=3` vẫn giữ nguyên**, còn **`stack=3` thay cho `stack=2`**. Lý do là ngay trước `swap`, stack chứa **ba giá trị category 1**: kết quả gốc, bản sao của kết quả và `PrintStream`. Đây là thay đổi hợp lý của `max_stack` do transformer bổ sung.

### 4.4. Chạy BEFORE và AFTER để kiểm tra ngữ nghĩa

Chạy bản **BEFORE**:

```bash
java -cp target/classes demo.DemoMain
```

Stdout:

```text
result=7
```

Chạy bản **AFTER** trên Linux/macOS (đặt thư mục đã biến đổi **trước** thư mục gốc trong classpath):

```bash
java -cp "target/modified:target/classes" demo.DemoMain
```

Trên Windows PowerShell/CMD, dấu phân cách classpath là dấu **`;`**:

```powershell
java -cp "target/modified;target/classes" demo.DemoMain
```

Stdout **chính xác từ `DemoMain` trên bản AFTER**:

```text
>> add
7
result=7
```

Ba dòng chứng minh (1) lệnh log đầu phương thức được thực thi, (2) lệnh log trước `ireturn` in đúng giá trị `7` và (3) caller vẫn nhận `7`. Khi kiểm tra một biến đổi production, hãy mở rộng sang nhiều bộ tham số, nhiều đường return, exception và hành vi đa luồng; một đầu vào đúng chưa đủ kết luận transformer luôn đúng.

## 5. Đọc từng thay đổi trong `javap` một cách có hệ thống

Với cùng một target method `add(II)I`, so theo các mục sau:

| Cần xem | BEFORE | AFTER | Điều cần suy luận |
| --- | --- | --- | --- |
| Method name và descriptor | `add(II)I` | `add(II)I` | Chữ ký không bị đổi |
| Mã đầu phương thức | `iload_0` | `getstatic → ldc → invokevirtual` rồi `iload_0` | Đã chèn log vào entry |
| Vùng tính tổng | `iload_0, iload_1, iadd, istore_2, iload_2` | Cùng logic, offsets lớn hơn | Phép cộng/biến tạm không đổi |
| Ngay trước trả về | `iload_2 → ireturn` | `iload_2 → dup → getstatic → swap → invokevirtual → ireturn` | Log kết quả nhưng để lại một `int` |
| `max_stack` | `2` | `3` | Độ sâu stack tăng hợp lệ |
| `max_locals` | `3` | `3` | Không thêm biến cục bộ |
| `args_size` | `2` | `2` | Số slot tham số giữ nguyên |
| Constant pool | Đủ cho phép cộng và constructor | Thêm tham chiếu `System.out`, chuỗi log và `println` | Các chỉ số `#n` có thể đổi |
| `LineNumberTable` | Trỏ tới offset cũ | Có thể được dời offset | Debug metadata phải gắn với code mới |
| Class name / major version | `demo.Calculator`, Java 17 class file | Giữ class name và target version | Không vô tình đổi ABI/bytecode level |
| Hành vi chạy | `result=7` | Ba dòng log, cuối cùng `result=7` | Side effect dự kiến, giá trị trả về giữ nguyên |

### 5.1. Vì sao offset thay đổi?

`Code.code[]` là **mảng byte**, không phải mảng các object Instruction. Một số opcode chiếm một byte (như `iadd`, `dup`, `swap`, `ireturn`), còn `getstatic` và `invokevirtual` mã hóa opcode và constant-pool index, thường chiếm **3 byte**. `ldc` ở ví dụ thường chiếm **2 byte** khi chỉ số pool vừa `u1`; trong trường hợp chỉ số lớn, writer có thể dùng `ldc_w`. Vì thế, không nên cố định số offset cuối cùng vào bài test.

Để so trước/sau, ưu tiên **mẫu opcode và tác động lên stack**. Nếu cần dùng offsets chính xác (ví dụ branch/exception handler), hãy lấy **offset thật từ output hiện tại**, không lấy từ chú thích hay ví dụ trước đó.

### 5.2. Theo vết operand stack tại `ireturn`

Ngay sau `iload_2`: `[result]`, đỉnh ở bên phải.

```text
[ result ]                    ; sau iload_2
[ result, result ]            ; dup
[ result, result, out ]       ; getstatic System.out
[ result, out, result ]       ; swap
[ result ]                    ; invokevirtual println(int)
[ ]                           ; ireturn, frame của callee kết thúc
```

`invokevirtual println(int)` tiêu thụ `out` và bản sao `result`, trả về `void` nên không đẩy giá trị mới. `ireturn` sử dụng **bản gốc** còn lại. Nếu bỏ `dup`, lệnh log sẽ tiêu thụ kết quả, khiến `ireturn` không còn operand hợp lệ và class có thể bị JVM verifier từ chối.

Phép biến đổi này chỉ dành cho **`IRETURN`** (giá trị kiểu `int`). `LRETURN`/`DRETURN` cần thao tác phù hợp cho giá trị category 2 (ví dụ `dup2` với bố cục thích hợp), `ARETURN` cần descriptor logger dùng reference, còn opcode `RETURN` của phương thức `void` không có giá trị trả về để sao chép. `ATHROW` là đường kết thúc bất thường và cần thiết kế xử lý riêng.

## 6. Kỹ thuật đối chiếu output và phát hiện classpath sai

Với file output lớn, tạo **hai snapshot `javap`** rồi diff:

```bash
javap -classpath target/classes  -p -c -v demo.Calculator > before.javap.txt
javap -classpath target/modified -p -c -v demo.Calculator > after.javap.txt
diff -u before.javap.txt after.javap.txt
```

Trên PowerShell có thể xuất hai file và so sánh:

```powershell
javap -classpath target/classes -p -c -v demo.Calculator > before.javap.txt
javap -classpath target/modified -p -c -v demo.Calculator > after.javap.txt
Compare-Object (Get-Content before.javap.txt) (Get-Content after.javap.txt)
```

Công cụ diff thô sẽ thấy cả constant-pool indexes, SHA, kích thước và offsets thay đổi. Khi đánh giá tính đúng, hãy nhóm chênh lệch theo **chữ ký → lệnh mới → stack effect → các nhánh/handler → attributes**. Không coi tất cả các thay đổi số thứ tự/offset là lỗi.

**Xác minh đang nhìn đúng class:** chạy hai lệnh `-sysinfo` theo hai classpath. Với hai class khác bytes, kích thước và SHA-256 thường khác nhau; đường dẫn trong `-sysinfo` giúp nhận ra sự trỏ nhầm đường dẫn. Nếu output BEFORE và AFTER giống hệt, hãy kiểm tra lần lượt đường ra transformer, thứ tự classpath, việc chọn đúng tên class và việc một bước build đã ghi lại file output. Thư mục có bản AFTER phải đứng **trước** bản BEFORE trong runtime classpath khi chạy bản biến đổi.

**Một vài lưu ý đối với classpath và module:**

- Với JAR, chỉ định đường dẫn JAR trong `-classpath`, ví dụ `javap -classpath target/app.jar -c -p demo.Calculator`; class phải có entry đúng package.
- Với chương trình modular, chọn đúng `--module-path` / `--module` để xác định module chứa class; đừng suy luận chỉ từ classpath.
- Với multi-release JAR, dùng `--multi-release` để chọn đúng class file theo phiên bản cần đối chiếu, và kiểm tra JDK `javap` hiện dùng.
- Nếu nhiều JDK cùng tồn tại, lệnh `javac` tạo class version mới hơn `javap` đang chạy có thể khiến kết quả không như dự kiến. Kiểm tra `java -version`, `javac -version` và `javap -version`; mục tiêu Maven ở ví dụ là Java 17.
- Mã Java sinh ra từ compiler khác hoặc option tối ưu/debug khác có thể cho bytecode khác (nhiều/ít local, tên biến, offsets, synthetic methods); luôn so các bản được xây từ **cùng điều kiện đầu vào**.

## 7. Khi chèn lúc chạy bằng Java agent: giới hạn rất quan trọng của `javap`

Ở ví dụ trên, ASM ghi ra **`target/modified/demo/Calculator.class`** nên `javap` đọc được bản AFTER. Với Java agent sử dụng `Instrumentation.addTransformer` và `ClassFileTransformer.transform`, biến đổi có thể chỉ tồn tại **trong quá trình tải hoặc retransformation bên trong JVM**. Tệp `target/classes/demo/Calculator.class` trên ổ đĩa **không tự thay đổi**.

```text
   classfileBuffer (bytes đầu vào trong transformer)
                │
                ▼
       ClassFileTransformer.transform(...)
                │
                ├─ trả về modifiedBytes → JVM định nghĩa/retransform class
                │
                └─ khi cần debug, ghi modifiedBytes → snapshot/demo/Calculator.class
                                              │
                                              ▼
                                javap -classpath snapshot -c -v demo.Calculator
```

Do đó, **`javap` chạy ngoài JVM không tự đọc nội dung của class đã được agent biến đổi trong bộ nhớ**. Nếu cần so AFTER của agent, hãy lấy **bytes thật mà transformer trả về**, lưu dưới đường dẫn phù hợp với package hoặc đưa vào một JAR snapshot, rồi chạy `javap` trên snapshot. Với retransformation, bytes đầu vào có thể không phải bản đã từng instrument trước đó; cần ghi rõ mỗi snapshot thuộc thời điểm và lần biến đổi nào.

Một đoạn **minh họa bên trong `transform` (không phải chương trình độc lập)** sau thể hiện ý tưởng ghi bytes ra đĩa; nó giả định biến `modifiedBytes` là mảng bytes đã được tính xong và đã chọn đúng class:

```java
// Nằm trong code của ClassFileTransformer, chỉ dành cho class đã chọn:
Path dump = Path.of("snapshots/after/demo/Calculator.class");
Files.createDirectories(dump.getParent());
Files.write(dump, modifiedBytes);
return modifiedBytes;
```

Trong agent thật, không ghi tất cả lớp bừa bãi vào cùng một tên file: cùng binary class name có thể được nạp bởi nhiều `ClassLoader`, có nhiều lượt transform, hoặc được tạo bằng module khác. Chọn tên snapshot có loader/lượt biến đổi và đảm bảo việc ghi file không gây I/O blocking hoặc ngoại lệ không kiểm soát trong transformer.

## 8. Checklist kỹ thuật khi bytecode có nhánh, ngoại lệ hoặc constructor

Một transformer vượt ngoài ví dụ đơn giản có thể **chạy được ở một đường đi nhưng hỏng ở đường khác**. Khi đọc `javap -v` của một biến đổi phức tạp, cần xét:

1. **Descriptor và kiểu trên operand stack:** lệnh `invoke*` phải tiêu thụ đúng reference/đối số, và kết quả phải khớp kiểu. Return opcodes phải khớp kiểu trả về.
2. **Đường rẽ nhánh và vòng lặp:** `if*`, `goto`, `tableswitch` và `lookupswitch` có branch targets theo offset. Khi chèn lệnh, offset nhánh và padding của switch có thể thay đổi; dùng writer để tính lại.
3. **Exception table:** mỗi entry có `start_pc`, `end_pc`, `handler_pc`, `catch_type`. Chèn lệnh trước/trong vùng bảo vệ có thể làm thay đổi phạm vi bắt exception hoặc thứ tự thực thi.
4. **`StackMapTable`:** verifier cần trạng thái kiểu nhất quán tại các điểm điều khiển tương ứng. `COMPUTE_FRAMES` hỗ trợ tính lại nhưng không bảo đảm mọi transformer đúng ngữ nghĩa; đặc biệt khi ASM phải xác định common superclass từ môi trường class loader khác.
5. **`LineNumberTable` và `LocalVariableTable`:** offsets có thể di chuyển; giữ/điều chỉnh debug metadata, đồng thời nhớ rằng các bảng này có thể vắng mặt mà class vẫn hợp lệ.
6. **`max_stack` và `max_locals`:** `COMPUTE_MAXS` giúp tính giới hạn, nhưng không thể sửa logic stack sai. Thêm biến tạm mới có thể đòi hỏi slot local mới; hai slot cho `long`/`double`.
7. **Constructor `<init>`:** đối tượng `this` chưa được khởi tạo hoàn toàn trước lời gọi constructor cha hoặc constructor khác; không tùy tiện thao tác với reference đó tại entry.
8. **Tác động của mã chèn:** logger có thể ném ngoại lệ, gây re-entrancy, đổi thứ tự side effects, tăng latency hoặc gây deadlock. Một bản biến đổi hợp lệ theo verifier vẫn có thể làm sai ứng dụng.
9. **Lỗi xác minh:** `VerifyError`, `ClassFormatError`, `NoClassDefFoundError` hoặc `UnsupportedClassVersionError` cần phân biệt; `javap` cho thấy bytes nhưng **không chứng minh** class được JVM chấp nhận trong mọi cấu hình. Chạy ứng dụng và kiểm thử là bước bổ sung cần thiết.

Ví dụ cụ thể ở mục 4 chỉ chèn vào một static method không có nhánh hoặc handler, vì vậy việc suy luận stack đơn giản và kết quả có thể quan sát rõ ràng.

## 9. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Không thấy log trong `javap` AFTER | Đọc nhầm BEFORE hoặc classpath sai | So đường dẫn `-sysinfo`; trỏ `-classpath` tới `target/modified` |
| `javap` có opcode mới nhưng chạy không thấy log | JVM tải BEFORE do classpath order, JAR khác hoặc class loader khác | Đặt AFTER trước; kiểm tra nguồn class được tải và classpath |
| Lệnh `javap -c` chỉ hiện public method | Thành viên cần xem là private hoặc package-private | Dùng `-p` |
| Không thấy tên biến `sum` | Không có `LocalVariableTable`/debug info | Biên dịch với `javac -g` hoặc xem `iload_2`/`istore_2`; không suy ra biến mất |
| Diff có nhiều `#n` khác nhau | Constant pool được tổ chức/tạo lại | So symbol owner/name/descriptor thay vì chỉ số |
| Offsets tăng không đều | Lệnh có độ dài khác nhau, `ldc_w`, `tableswitch` padding | Dựa vào opcode/targets thực tế trong `javap` |
| `VerifyError` ngay sau biến đổi | Stack type, frame, branch target hoặc return sai | Theo vết stack, xem `StackMapTable`, dùng verifier và test |
| Log kết quả in đúng nhưng caller nhận sai | Không bảo toàn return value hoặc thay đổi toán hạng | Theo vết `dup`/`swap` và descriptor `println` |
| `-v` báo `stack`/`locals` khác dự kiến | Transformer thêm stack/local hoặc compiler thay đổi | Tính stack theo đường thực thi, xem opcode/descriptor |
| `NoSuchMethodError` khi chạy patch tool | ASM/plugin bị nạp nhầm phiên bản | Xem dependency tree và phiên bản ASM trên classpath |
| Chạy patch nhiều lần bị log lặp | Biến đổi offline không idempotent | Luôn dùng bản BEFORE nguyên gốc; quản lý snapshot |
| Tưởng `javap` đã thấy agent runtime | Agent chỉ sửa bytes trong JVM | Dump bytes mà transformer thực sự trả về rồi mới chạy `javap` |

## 10. Thực hành nâng cao và câu hỏi tự kiểm tra

**Bài 1.** Thêm hai lệnh `System.out.println` vào đầu và cuối một `void` method: cần thay `IRETURN` bằng logic nhận diện opcode gì?

**Đáp án:** `RETURN`. Không có giá trị trên stack cần `dup`; nếu ghi log ở mọi điểm thoát, còn phải xét exception/`ATHROW` và các handler.

**Bài 2.** Với phương thức `static long total(long x)`, vì sao không thể sao chép kết quả bằng `dup` trước `lreturn`?

**Đáp án:** `long` là category 2, chiếm hai đơn vị stack. `dup` chỉ áp dụng cho giá trị category 1; trường hợp này có thể dùng `dup2` với đúng stack shape và logger descriptor `(J)V`.

**Bài 3.** Sau chèn `getstatic; ldc; invokevirtual` vào đầu phương thức, tại sao các offsets của `iload`/`ireturn` lớn hơn nhưng `locals` không đổi?

**Đáp án:** code có thêm byte instruction, nhưng không cấp biến cục bộ mới. Những lệnh log dùng operand stack.

**Bài 4.** Công cụ `javap -classpath target/classes ...` có nhất thiết thấy được biến đổi do `-javaagent` áp dụng tại runtime không?

**Đáp án:** không. `javap` đọc bytes theo đường dẫn bạn đưa; muốn đọc phiên bản sau biến đổi phải có snapshot của bytes tương ứng.

**Bài 5.** Hai output `javap` có `#17` và `#21` cho cùng một lời gọi `println:(I)V`. Đây có tự động là thay đổi hành vi không?

**Đáp án:** không. Constant pool index là vị trí trong từng class file; điều quyết định ở đây là target method và descriptor của lệnh gọi.

### Checklist tự nghiệm thu với ví dụ

- [ ] `mvn -q -DskipTests package` thành công trên JDK 17+.
- [ ] `javap` BEFORE chứa `iload_0, iload_1, iadd, istore_2, iload_2, ireturn` trong `add`.
- [ ] Bytecode transformer tạo `target/modified/demo/Calculator.class`, không ghi đè BEFORE.
- [ ] `javap` AFTER chứa log entry và log result đúng vị trí; `add(II)I` vẫn giữ tên/descriptor.
- [ ] `javap -v` cho thấy `stack` thay từ **2 → 3**, `locals` vẫn **3** trong method `add`.
- [ ] Chạy BEFORE in `result=7`; chạy AFTER in ba dòng `>> add`, `7`, `result=7`.
- [ ] Có thể giải thích operand stack qua `dup`, `getstatic`, `swap`, `println(int)` và `ireturn` mà không suy đoán.
- [ ] Đã đối chiếu đúng classpath và hiểu giới hạn của `javap` đối với Java agent runtime.

## Tài liệu tham khảo

1. Oracle JDK 17, **The `javap` Command** — cú pháp và các tùy chọn `-c`/`-l`/`-p`/`-v`/`-s`/`-sysinfo`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
2. Java Virtual Machine Specification, **Frames (`2.6)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6
3. Java Virtual Machine Specification, **Code attribute (`4.7.3), StackMapTable (`4.7.4)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3
4. Java Virtual Machine Specification, **Instructions (`6)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
5. ASM Javadoc, **ClassReader, ClassWriter, MethodVisitor**: https://asm.ow2.io/javadoc/
6. ASM, **Developer Guide**: https://asm.ow2.io/developer-guide.html
