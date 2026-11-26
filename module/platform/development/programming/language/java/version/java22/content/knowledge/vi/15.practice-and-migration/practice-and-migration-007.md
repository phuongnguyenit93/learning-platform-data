# Bài tập Class File API: phân tích phương thức và xác minh bytecode sau biến đổi

## 1. Mục tiêu và lựa chọn API còn phù hợp

Bài thực hành thuộc chương **Vận dụng và nâng cấp** của module **JAVA_VERSION_JAVA22 — Học các tính năng được giới thiệu trong Java 22 còn hữu ích ở Java hiện đại**. Bạn sẽ xây dựng một công cụ đọc tệp `.class`, phân tích các phương thức, thay đổi có giới hạn một phép toán và kiểm tra kết quả trước khi ghi thành tệp mới.

Class-File API được giới thiệu ở dạng preview trong Java 22 theo JEP 457. API đã trở thành API chuẩn ở JDK 24 theo JEP 484. Bài dùng cách viết của API chuẩn trong `java.lang.classfile` trên **JDK 24 trở lên**, đồng thời dùng một lớp mẫu có thể biên dịch cho Java 22 để giữ liên hệ với phạm vi module. Xem [thay đổi của JDK 22](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-22.html) và [thay đổi của JDK 24](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-24.html).

Không cần khôi phục chữ ký preview cũ để học các thao tác này. Mã công cụ trong bài không cần `--enable-preview`, `--add-exports` hay thư viện bytecode bên ngoài.

Sau bài học, bạn cần làm được:

- Liệt kê tên, descriptor, access flags, sự hiện diện của thân phương thức và các opcode.
- Chọn đúng phương thức khi có overload.
- Dùng `ClassTransform` và `CodeTransform` để thay đổi đúng phạm vi.
- Xác minh bytecode ở mức API và nạp thử bằng JVM.
- Kiểm tra hành vi để phân biệt “bytecode hợp lệ” với “biến đổi đúng yêu cầu”.

Các API và lệnh trong bài được đối chiếu với tài liệu Java hiện hành tại ngày **25/11/2026**. Không có kết quả chạy thử nào được giả định sẵn cho máy người học.

## 2. Đề bài

### 2.1. Lớp đầu vào

Tạo `src/demo/Calculator.java`:

```java
package demo;

public final class Calculator {
    public Calculator() {
    }

    public static int adjust(int amount, int adjustment) {
        int result = amount + adjustment;
        if (result < 0) {
            return 0;
        }
        return result;
    }

    public static int adjust(int amount) {
        return amount + 1;
    }
}
```

Lớp này có hai phương thức cùng tên `adjust`. Phương thức hai tham số có nhánh điều kiện để bài thực hành bao phủ cả luồng điều khiển, thay vì chỉ đổi một hàm trả về hằng số.

### 2.2. Phép biến đổi được phép

Chỉ trong `adjust(int, int)`, đổi phép cộng thành phép trừ:

```text
Trước: result = amount + adjustment
Sau:   result = amount - adjustment
```

Giữ nguyên bước chặn kết quả âm về zero. Không đổi overload `adjust(int)`, constructor, tên lớp hoặc chữ ký phương thức.

Đây là phép thay đổi hành vi **có chủ đích** để quan sát bytecode. Yêu cầu không phải giữ tương đương chức năng với bản gốc.

| Lời gọi | Bản gốc | Bản sau biến đổi |
|---|---:|---:|
| `adjust(10, 3)` | 13 | 7 |
| `adjust(2, 5)` | 7 | 0 |
| `adjust(-5, 2)` | 0 | 0 |
| `adjust(0, 0)` | 0 | 0 |
| `adjust(4)` | 5 | 5 |

Với các giá trị biên, dùng đúng ngữ nghĩa `int` của Java. Phép cộng hoặc trừ có thể tràn theo biểu diễn 32 bit; bài không thay chúng bằng `Math.addExact` hay `Math.subtractExact`.

### 2.3. Điều kiện chấp nhận

Công cụ chỉ được xuất tệp mới khi:

1. Đầu vào được kiểm tra và tìm thấy đúng phương thức đích.
2. Phương thức đích có đúng một `IADD` theo lớp mẫu đã cho.
3. Sau biến đổi, đúng vị trí đó trở thành `ISUB`.
4. Bộ phương thức, descriptor, access flags và sự có mặt của `Code` vẫn phù hợp.
5. `ClassFile.verify` không báo lỗi cho đầu ra.
6. JVM nạp được hai phiên bản và các phép thử hành vi đều đạt.
7. Tệp đầu vào được giữ nguyên, đầu ra được ghi ở đường dẫn khác.

Nếu không tìm thấy opcode mong đợi hoặc lớp đầu vào đã thay đổi hình dạng, phải báo lỗi. Không được im lặng xuất một tệp chưa thực hiện yêu cầu.

## 3. Những khái niệm cần dùng

### 3.1. Tên phương thức chưa đủ để chọn đích

Trong lớp mẫu:

| Phương thức | Tên trong class file | Descriptor |
|---|---|---|
| Constructor | `<init>` | `()V` |
| `int adjust(int, int)` | `adjust` | `(II)I` |
| `int adjust(int)` | `adjust` | `(I)I` |

Descriptor ghi kiểu tham số trong cặp ngoặc và kiểu trả về sau dấu `)`. `I` là `int`, `V` là `void`. Với một lớp xác định, công cụ chọn phương thức bằng cặp **tên + descriptor**, tránh áp dụng nhầm cho overload. Quy tắc descriptor được quy định trong [JVMS, mục 4.3.3](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.3.3).

`MethodModel.methodTypeSymbol()` cung cấp `MethodTypeDesc`, thuận tiện để so sánh bằng descriptor có kiểu thay vì ghép chuỗi thủ công. `MethodModel.code()` trả về `Optional<CodeModel>` vì phương thức abstract hoặc native không có thân bytecode. Xem [MethodModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html).

### 3.2. Model, builder và transform

Luồng xử lý chính:

```text
byte[] đầu vào
    |
    v
ClassModel --> phân tích MethodModel và CodeModel
    |
    v
ClassTransform chọn thân phương thức
    |
    v
CodeTransform thay IADD bằng ISUB
    |
    v
byte[] đầu ra
    |
    +--> xác minh bằng API
    +--> kiểm tra phạm vi biến đổi
    +--> nạp và chạy kiểm tra bằng JVM
    |
    v
ghi tệp mới
```

Model mô tả đầu vào; transform chuyển các phần tử sang builder để tạo đầu ra. Model không bị sửa trực tiếp tại chỗ. Với mỗi phần tử, transform có thể giữ lại, thay thế hoặc bỏ đi.

Trong một transform tự viết, `builder.with(element)` là thao tác chuyển tiếp phần tử cần giữ. Bỏ quên nhánh này có thể làm mất cả những phần tử không phải lệnh, chẳng hạn nhãn hoặc thông tin dòng. Xem [mô hình biến đổi của Class-File API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html#transforming-classfiles).

### 3.3. Instruction không phải toàn bộ CodeElement

`CodeModel` chứa một chuỗi `CodeElement` có thứ tự. Một phần tử có thể là lệnh JVM hoặc thông tin khác phục vụ biểu diễn thân phương thức.

Khi đếm opcode:

```java
for (CodeElement element : code) {
    if (element instanceof Instruction instruction) {
        System.out.println(instruction.opcode());
    }
}
```

Chỉ đếm các phần tử là `Instruction`. Không dùng số phần tử trong `CodeModel` như số lệnh bytecode. Xem [CodeModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html) và [Instruction](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/Instruction.html).

## 4. Tại sao thay IADD bằng ISUB có thể vượt qua verifier?

Cả hai lệnh đều lấy hai giá trị `int` trên operand stack và đẩy lại một giá trị `int`:

```text
Trước IADD hoặc ISUB: ..., value1:int, value2:int
Sau IADD:            ..., (value1 + value2):int
Sau ISUB:            ..., (value1 - value2):int
```

Tác động lên kiểu và số phần tử stack giống nhau, nhưng giá trị được tính khác nhau. Trong lớp mẫu, lệnh lưu kết quả vào biến cục bộ và các nhánh sau đó vẫn nhận một `int` hợp lệ.

Vì vậy, verifier có thể chấp nhận cả hai phiên bản. Nó không biết hợp đồng nghiệp vụ đang yêu cầu cộng hay trừ. Cũng cần chú ý thứ tự toán hạng: `ISUB` tính `value1 - value2`, không đảo ngược hai giá trị. Xem [ngữ nghĩa IADD và ISUB trong JVMS](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-6.html#jvms-6.5.isub).

Trong phép đổi này, hai opcode có cùng độ dài và không thêm nhãn mới. Dù vậy, công cụ vẫn giao việc tạo class file và xử lý dữ liệu dẫn xuất cho API, thay vì sửa thẳng các byte có giá trị trùng với mã lệnh.

Tìm và thay byte thô không đủ an toàn về mặt thuật toán: cùng giá trị byte có thể nằm trong operand, constant pool hoặc attribute. Bài yêu cầu nhận diện instruction trong đúng phương thức.

## 5. Lời giải tham khảo hoàn chỉnh

Lưu thành `src/lab/ClassFileLab.java`. Chương trình nhận hai đường dẫn: tệp `.class` gốc và tệp `.class` kết quả.

```java
package lab;

import static java.lang.constant.ConstantDescs.CD_int;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.Instruction;
import java.lang.classfile.MethodModel;
import java.lang.classfile.Opcode;
import java.lang.constant.MethodTypeDesc;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ClassFileLab {
    private static final ClassFile CLASS_FILE = ClassFile.of();
    private static final String BINARY_NAME = "demo.Calculator";
    private static final MethodTypeDesc TARGET_TYPE =
            MethodTypeDesc.of(CD_int, CD_int, CD_int);

    public static void main(String[] args) throws Exception {
        require(args.length == 2,
                "Usage: ClassFileLab <input.class> <output.class>");

        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        require(!input.equals(output), "Input and output must differ");
        if (Files.exists(output)) {
            require(!Files.isSameFile(input, output),
                    "Input and output refer to the same file");
        }

        byte[] originalBytes = Files.readAllBytes(input);
        verifyOrThrow("before", originalBytes);
        ClassModel original = CLASS_FILE.parse(originalBytes);
        require(original.thisClass().asInternalName()
                        .equals("demo/Calculator"),
                "Expected demo/Calculator");
        report("BEFORE", original);

        List<MethodModel> targets = original.methods().stream()
                .filter(ClassFileLab::isTarget)
                .toList();
        require(targets.size() == 1,
                "Expected exactly one adjust(II)I");
        MethodModel target = targets.get(0);
        require(target.code().isPresent(), "Target has no code");
        long additions = opcodes(target).stream()
                .filter(op -> op == Opcode.IADD)
                .count();
        require(additions == 1, "Expected exactly one target IADD");

        CodeTransform addToSubtract = (builder, element) -> {
            if (element instanceof Instruction instruction
                    && instruction.opcode() == Opcode.IADD) {
                builder.isub();
            } else {
                builder.with(element);
            }
        };

        byte[] transformedBytes = CLASS_FILE.transformClass(
                original,
                ClassTransform.transformingMethodBodies(
                        ClassFileLab::isTarget, addToSubtract));

        verifyOrThrow("after", transformedBytes);
        ClassModel transformed = CLASS_FILE.parse(transformedBytes);
        checkScope(original, transformed);
        report("AFTER", transformed);
        checkBehavior(originalBytes, transformedBytes);

        Files.createDirectories(output.getParent());
        Files.write(output, transformedBytes);
        require(Arrays.equals(transformedBytes, Files.readAllBytes(output)),
                "Output readback differs");
        require(Arrays.equals(originalBytes, Files.readAllBytes(input)),
                "Input file was modified");
        System.out.println("PASS: wrote " + output);
    }

    private static boolean isTarget(MethodModel method) {
        return method.methodName().stringValue().equals("adjust")
                && method.methodTypeSymbol().equals(TARGET_TYPE);
    }

    private static String key(MethodModel method) {
        return method.methodName().stringValue()
                + method.methodTypeSymbol().descriptorString();
    }

    private static List<Opcode> opcodes(MethodModel method) {
        List<Opcode> result = new ArrayList<>();
        method.code().ifPresent(code -> {
            for (CodeElement element : code) {
                if (element instanceof Instruction instruction) {
                    result.add(instruction.opcode());
                }
            }
        });
        return List.copyOf(result);
    }

    private static void report(String stage, ClassModel model) {
        System.out.printf("%s class=%s version=%d.%d%n",
                stage, model.thisClass().asInternalName(),
                model.majorVersion(), model.minorVersion());

        for (MethodModel method : model.methods()) {
            List<Opcode> operations = opcodes(method);
            System.out.printf(
                    "  %s flags=%s code=%s instructions=%d%n",
                    key(method), method.flags().flags(),
                    method.code().isPresent(), operations.size());
            System.out.println("    " + operations);
        }
    }

    private static Map<String, MethodModel> index(ClassModel model) {
        Map<String, MethodModel> methods = new LinkedHashMap<>();
        for (MethodModel method : model.methods()) {
            require(methods.put(key(method), method) == null,
                    "Duplicate method key: " + key(method));
        }
        return methods;
    }

    private static void checkScope(
            ClassModel before, ClassModel after) {
        require(before.thisClass().asInternalName()
                        .equals(after.thisClass().asInternalName()),
                "Class name changed");
        require(before.majorVersion() == after.majorVersion()
                        && before.minorVersion() == after.minorVersion(),
                "Class file version changed");
        require(before.flags().flagsMask() == after.flags().flagsMask(),
                "Class access flags changed");

        Map<String, MethodModel> left = index(before);
        Map<String, MethodModel> right = index(after);
        require(left.keySet().equals(right.keySet()),
                "Method set or descriptors changed");

        for (Map.Entry<String, MethodModel> entry : left.entrySet()) {
            MethodModel oldMethod = entry.getValue();
            MethodModel newMethod = right.get(entry.getKey());
            require(oldMethod.flags().flagsMask()
                            == newMethod.flags().flagsMask(),
                    "Method flags changed: " + entry.getKey());
            require(oldMethod.code().isPresent()
                            == newMethod.code().isPresent(),
                    "Code presence changed: " + entry.getKey());

            List<Opcode> expected = new ArrayList<>(opcodes(oldMethod));
            if (isTarget(oldMethod)) {
                expected.replaceAll(op ->
                        op == Opcode.IADD ? Opcode.ISUB : op);
            }
            require(expected.equals(opcodes(newMethod)),
                    "Unexpected opcode sequence: " + entry.getKey());
        }
    }

    private static void verifyOrThrow(String stage, byte[] bytes) {
        List<VerifyError> errors = CLASS_FILE.verify(bytes);
        if (!errors.isEmpty()) {
            errors.forEach(error ->
                    System.err.println(stage + ": " + error));
            throw new IllegalStateException(
                    stage + ": verification errors=" + errors.size());
        }
        System.out.println(stage + ": API verification errors=0");
    }

    private static void checkBehavior(
            byte[] beforeBytes, byte[] afterBytes) throws Exception {
        Class<?> beforeClass = new ByteLoader().define(beforeBytes);
        Class<?> afterClass = new ByteLoader().define(afterBytes);
        require(beforeClass != afterClass,
                "Expected distinct class definitions");

        beforeClass.getDeclaredConstructor().newInstance();
        afterClass.getDeclaredConstructor().newInstance();
        Method oldPair = beforeClass.getMethod(
                "adjust", int.class, int.class);
        Method newPair = afterClass.getMethod(
                "adjust", int.class, int.class);

        int[][] cases = {
                {10, 3}, {2, 5}, {-5, 2}, {0, 0},
                {Integer.MAX_VALUE, 1}, {Integer.MIN_VALUE, 1}
        };
        for (int[] test : cases) {
            int amount = test[0];
            int adjustment = test[1];
            int actualBefore = (int) oldPair.invoke(
                    null, amount, adjustment);
            int actualAfter = (int) newPair.invoke(
                    null, amount, adjustment);
            require(actualBefore == Math.max(0, amount + adjustment),
                    "Original behavior mismatch");
            require(actualAfter == Math.max(0, amount - adjustment),
                    "Transformed behavior mismatch");
        }

        Method oldSingle = beforeClass.getMethod("adjust", int.class);
        Method newSingle = afterClass.getMethod("adjust", int.class);
        for (int amount : new int[]{-1, 0, 4, Integer.MAX_VALUE}) {
            require((int) oldSingle.invoke(null, amount) == amount + 1,
                    "Original overload mismatch");
            require((int) newSingle.invoke(null, amount) == amount + 1,
                    "Untargeted overload changed");
        }
        System.out.println("JVM loading and behavior checks passed");
    }

    private static final class ByteLoader extends ClassLoader {
        ByteLoader() {
            super(ClassFileLab.class.getClassLoader());
        }

        Class<?> define(byte[] bytes) {
            Class<?> type = defineClass(
                    BINARY_NAME, bytes, 0, bytes.length);
            resolveClass(type);
            return type;
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
```

### 5.1. Phạm vi của transform

`ClassTransform.transformingMethodBodies(predicate, transform)` áp dụng biến đổi cho thân những phương thức thỏa predicate và chuyển tiếp các phần tử khác. Lambda `addToSubtract` không tự chọn phương thức; predicate `isTarget` thực hiện việc đó.

`builder.isub()` phát lệnh thay thế. Nhánh `else` chuyển tiếp mọi phần tử còn lại. Xem [ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html) và [CodeBuilder.isub](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html#isub()).

### 5.2. Báo cáo phương thức chứng minh điều gì?

Báo cáo cho biết tên, descriptor, flags, thân bytecode có tồn tại hay không, số instruction và chuỗi opcode. Đầu vào mẫu có hai `IADD` nếu xét cả hai overload; chỉ `IADD` trong `adjust(II)I` được đổi.

Kiểm tra `checkScope` so sánh tập phương thức, access flags, sự có mặt của thân và chuỗi opcode. Đây là kiểm tra phạm vi phù hợp với phép đổi nhỏ trong bài. Nó chưa phải phép so sánh đầy đủ mọi operand, constant pool, annotation hay attribute tùy biến.

Vì vậy, không thể dùng riêng `checkScope` để tuyên bố hai class file bất kỳ tương đương. Khi mở rộng transformer, cần mở rộng cả phép kiểm tra tương ứng với những dữ liệu có thể bị tác động.

## 6. Biên dịch và chạy bài thực hành

### 6.1. Cấu trúc thư mục

Trong một thư mục thực hành riêng, đặt hai tệp nguồn theo cấu trúc:

```text
classfile-lab/
  src/
    demo/
      Calculator.java
    lab/
      ClassFileLab.java
  out/
    original/
    tool/
    transformed/
```

Dùng `java -version` và `javac -version` để kiểm tra bộ công cụ. Ví dụ dưới dùng JDK 24 trở lên có hỗ trợ các giá trị `--release` được ghi trong lệnh.

Từ thư mục `classfile-lab`:

```powershell
New-Item -ItemType Directory -Force -Path out/original, out/tool | Out-Null

javac --release 22 -g -encoding UTF-8 -d out/original src/demo/Calculator.java
javac --release 24 -g -encoding UTF-8 -d out/tool src/lab/ClassFileLab.java

java -cp out/tool lab.ClassFileLab out/original/demo/Calculator.class out/transformed/demo/Calculator.class
```

Hai giá trị `--release` có mục đích khác nhau:

- `--release 22` tạo lớp đầu vào phù hợp với Java 22 vì mã `Calculator` chỉ dùng cú pháp và API thông thường.
- `--release 24` biên dịch công cụ theo API chuẩn từ Java 24.
- JVM chạy công cụ phải là JDK 24 trở lên. Việc đọc lớp đầu vào Java 22 không làm công cụ tự tương thích ngược với runtime Java 22.

`--release` kiểm soát mức ngôn ngữ, đích class file và API nền tảng được phép dùng khi biên dịch. Nó không chuyển API mới thành API có sẵn trên JDK cũ. Xem [tùy chọn javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

Không thêm `out/original` hoặc `out/transformed` vào classpath chạy công cụ. `ByteLoader` nhận trực tiếp mảng byte cần kiểm tra nên không cần tìm `demo.Calculator` từ classpath.

### 6.2. Kết quả cần quan sát

Chương trình phải in được:

```text
before: API verification errors=0
BEFORE class=demo/Calculator version=...
  <init>()V ...
  adjust(II)I ...
  adjust(I)I ...
after: API verification errors=0
AFTER class=demo/Calculator version=...
  ...
JVM loading and behavior checks passed
PASS: wrote ...
```

Đây là hình dạng đầu ra dự kiến, không phải log thực thi đã thu thập. Số instruction cụ thể, cách trình bày flags và đường dẫn đầy đủ phụ thuộc tệp biên dịch và môi trường.

Ở báo cáo sau biến đổi:

- `adjust(II)I` có `ISUB` tại vị trí trước đó là `IADD`.
- `adjust(I)I` vẫn có `IADD`.
- Tên, descriptor và access flags của các phương thức không đổi.
- Constructor vẫn được giữ và có thể gọi.

Nếu `IADD` dự kiến không có đúng một lần, công cụ dừng ở precondition. Điều này thường có nghĩa bạn đã dùng lớp khác, thay mã nguồn hoặc đưa đầu ra đã biến đổi trở lại làm đầu vào.

### 6.3. Đối chiếu bằng javap

Chạy:

```powershell
javap -p -s -c -v out/original/demo/Calculator.class
javap -p -s -c -v out/transformed/demo/Calculator.class
```

Các tùy chọn giúp quan sát:

| Tùy chọn | Thông tin |
|---|---|
| `-p` | Tất cả các thành viên |
| `-s` | Descriptor nội bộ |
| `-c` | Disassembly của bytecode |
| `-v` | Thông tin chi tiết như version, stack, locals và attributes |

Xem [tài liệu javap](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html).

Đọc đúng khối descriptor `(II)I` trước khi tìm `iadd` hoặc `isub`. Tìm kiếm toàn bộ đầu ra rồi thấy vẫn còn `iadd` không chứng minh phép đổi thất bại: overload một tham số phải giữ phép cộng.

Không dùng việc toàn bộ mảng byte đầu ra khác đầu vào làm bằng chứng đủ mạnh. Builder có thể tạo khác biệt ở cách biểu diễn hoặc metadata mà không tương ứng với yêu cầu nghiệp vụ. Trong bài này, bằng chứng chính là thay đổi opcode có giới hạn và kiểm tra hành vi.

## 7. Xác minh sau biến đổi theo từng tầng

### 7.1. Parse không đồng nghĩa verify

`ClassFile.parse` tạo mô hình để truy cập class file. Việc phân tích có tính lazy: lỗi có thể chỉ xuất hiện khi truy cập sâu vào một cấu trúc, thay vì ngay tại lời gọi `parse`.

Do đó, câu lệnh sau chưa phải một phép xác minh bytecode hoàn chỉnh:

```java
ClassModel model = ClassFile.of().parse(bytes);
```

`ClassFile.verify(bytes)` trả danh sách `VerifyError`; danh sách rỗng nghĩa là bộ kiểm tra không tìm thấy lỗi xác minh. Nếu đầu vào hỏng khiến quá trình phân tích hoặc truy cập model ném ngoại lệ, đó vẫn là thất bại cần ghi nhận. Không biến ngoại lệ thành một danh sách rỗng rồi báo thành công. Xem [ClassFile.parse và verify](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html).

Hàm `verifyOrThrow` in từng chẩn đoán và dừng trước khi ghi tệp khi danh sách không rỗng. Kiểu phần tử ở đây là `java.lang.VerifyError`.

### 7.2. Verifier kiểm tra tính hợp lệ, không kiểm tra ý định

| Tầng kiểm tra | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| Đọc và duyệt model | Có đọc được các cấu trúc cần phân tích không? | Chưa chứng minh các luồng bytecode đều hợp lệ |
| `ClassFile.verify` | Có tìm thấy lỗi xác minh class file không? | Không biết yêu cầu nghiệp vụ |
| Kiểm tra phạm vi | Đã thay đúng phương thức và opcode dự kiến chưa? | Chỉ bao phủ các bất biến đã viết |
| Nạp, liên kết và gọi bằng JVM | Định nghĩa lớp có dùng được trong môi trường thử không? | Một lần chạy không bao phủ mọi tình huống |
| Kiểm thử hành vi | Các ví dụ và biên đã chọn có đúng hợp đồng không? | Không phải chứng minh đúng cho mọi đầu vào |

Ví dụ, nếu vô tình biến cả hai overload từ cộng sang trừ, `ClassFile.verify` vẫn có thể trả danh sách rỗng. `checkScope` và kiểm tra `adjust(4) == 5` mới phát hiện việc sửa vượt phạm vi.

Ngược lại, nếu không thực hiện biến đổi mà chỉ copy lớp gốc, verifier cũng không phản đối. Kiểm tra chuỗi opcode và kỳ vọng `adjust(10, 3) == 7` phải phát hiện lỗi này.

Các ràng buộc xác minh kiểu và luồng điều khiển được mô tả trong [JVMS, mục 4.10](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.10).

### 7.3. Vì sao cần hai class loader?

Bản gốc và bản sau biến đổi đều có binary name `demo.Calculator`. Để so sánh chúng trong cùng một JVM, chương trình định nghĩa mỗi bản bằng một `ByteLoader` mới.

Ở JVM, danh tính lớp gắn với tên và defining class loader. Hai định nghĩa có cùng tên nhưng loader khác nhau là hai kiểu khác nhau. Không định nghĩa cả hai lần trong cùng một loader, và không dùng `Class.forName("demo.Calculator")` để hy vọng nó tự chọn đúng mảng byte. Xem [JVMS về tạo và nạp lớp](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-5.html#jvms-5.3).

`ByteLoader.define` gọi `defineClass` trực tiếp trên mảng byte, sau đó `resolveClass`. Chương trình tiếp tục tìm constructor, tìm phương thức và gọi chúng. Như vậy, phép thử không dừng ở việc thu được một đối tượng `Class<?>`. Xem [ClassLoader.defineClass và resolveClass](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassLoader.html).

Bài dùng phương thức public static với tham số và giá trị trả về là `int`, nên có thể so sánh kết quả mà không cần truyền các đối tượng `Calculator` qua ranh giới hai loader.

Nếu mở rộng sang kiểu tự định nghĩa, đừng ép một đối tượng được tạo từ loader thứ nhất sang lớp cùng tên của loader thứ hai. Đó là hai kiểu khác nhau.

## 8. Bài đối chứng: cố ý tạo bytecode sai

Một bài thực hành xác minh nên có ít nhất một ca mà pipeline phải từ chối.

### 8.1. Làm mất giá trị trên operand stack

Thử thay đoạn xử lý `IADD` bằng:

```java
builder.iadd();
builder.pop();
```

Sau `IADD` có một kết quả `int`. `POP` loại kết quả đó. Ở lớp mẫu, lệnh tiếp theo cần lưu giá trị vào biến cục bộ nhưng stack đã rỗng:

```text
iload_0       stack: [amount]
iload_1       stack: [amount, adjustment]
iadd          stack: [result]
pop           stack: []
istore_2      cần một int để lấy ra --> lỗi
```

Đây là lỗi cấu trúc luồng dữ liệu, khác với việc chọn nhầm cộng hay trừ. Phép đổi vẫn có thể tạo ra các byte có hình dạng là instruction, nhưng chuỗi đó không hợp lệ để thực thi.

### 8.2. Đoạn kiểm tra đối chứng

Có thể thêm phương thức dưới đây vào `ClassFileLab` và gọi `demonstrateInvalidTransformation(original)` sau kiểm tra hành vi, trước bước ghi đầu ra hợp lệ:

```java
private static void demonstrateInvalidTransformation(
        ClassModel source) {
    ClassFile strict = ClassFile.of(
            ClassFile.StackMapsOption.GENERATE_STACK_MAPS);

    CodeTransform broken = (builder, element) -> {
        if (element instanceof Instruction instruction
                && instruction.opcode() == Opcode.IADD) {
            builder.iadd();
            builder.pop();
        } else {
            builder.with(element);
        }
    };

    byte[] invalidBytes;
    try {
        invalidBytes = strict.transformClass(
                source,
                ClassTransform.transformingMethodBodies(
                        ClassFileLab::isTarget, broken));
    } catch (IllegalArgumentException failure) {
        System.out.println(
                "Negative case rejected during build: " + failure);
        return;
    }

    List<VerifyError> errors = strict.verify(invalidBytes);
    if (errors.isEmpty()) {
        throw new IllegalStateException(
                "Broken bytecode was unexpectedly accepted by verify");
    }
    System.out.println("Negative case rejected during verification");
    errors.forEach(System.out::println);
}
```

Ca đối chứng có thể bị từ chối ngay khi sinh stack map hoặc chỉ được báo lỗi ở bước xác minh nếu tạo được mảng byte. Không yêu cầu lúc nào cũng phải nhận một `byte[]` hỏng rồi mới gọi verifier.

Khi ghi báo cáo, lưu **giai đoạn và thông báo thực tế**. Nếu gặp lỗi thiếu dependency hoặc sai phiên bản class file, phải giải quyết lỗi môi trường; không tính lỗi đó là bằng chứng đã phát hiện đúng stack underflow.

Tùy chọn sinh stack map và khả năng thất bại trong quá trình tạo mã được mô tả tại [ClassFile.StackMapsOption](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html).

### 8.3. Ca sai ngữ nghĩa nhưng vẫn hợp lệ

Thử bỏ predicate và áp dụng transform cho mọi thân phương thức:

```java
ClassTransform.transformingMethodBodies(addToSubtract)
```

Khi đó overload `adjust(I)I` cũng có thể bị đổi. Hãy dự đoán:

- Verifier có phát hiện việc đổi sai yêu cầu này không?
- `checkScope` dừng ở đâu?
- Nếu bỏ `checkScope`, kiểm tra overload nào sẽ thất bại?

Ca này cho thấy pipeline cần cả xác minh bytecode và kiểm tra yêu cầu biến đổi. Không xem mọi ca thất bại là cùng một loại lỗi.

## 9. Stack map, nhãn và phụ thuộc lớp khi mở rộng

### 9.1. Giữ phần tử không bị biến đổi

Mọi nhãn, thông tin dòng và phần tử khác không được sửa phải đi qua nhánh `builder.with(element)`. Chỉ chuyển tiếp các `Instruction` rồi bỏ các phần tử khác có thể làm hỏng nhánh nhảy hoặc thông tin liên quan đến vùng mã.

Giải pháp tham khảo không tự tính offset nhảy hay viết lại `max_stack` và `StackMapTable` bằng tay. Stack map là dữ liệu dẫn xuất mà builder có thể tạo hoặc tái sử dụng khi tương thích.

Cần phân biệt hai việc:

- Giữ các phần tử mô hình cần thiết để mô tả đúng thân phương thức.
- Để API xử lý dữ liệu dẫn xuất theo tùy chọn đã chọn.

Điều đó không có nghĩa mọi attribute tùy biến đều tự động được sửa đúng sau mọi phép biến đổi. Khi transformer tác động tới cấu trúc phức tạp hơn, phải xem lại chính sách xử lý attribute và bổ sung kiểm tra.

### 9.2. Reference type và class hierarchy resolver

Lớp mẫu chủ yếu thao tác `int`, nên không có bài toán hợp nhất các kiểu tham chiếu phức tạp ở nhánh điều khiển.

Nếu thêm logic với các lớp ứng dụng, interface hoặc nhiều nhánh tạo kiểu tham chiếu khác nhau, quá trình sinh stack map hoặc verify có thể cần thông tin quan hệ kế thừa. Resolver phải nhìn thấy đúng các kiểu của môi trường đích, nhất là khi công cụ phân tích chạy khác classpath hoặc class loader với ứng dụng.

Sử dụng `ClassFile.ClassHierarchyResolverOption` và `ClassHierarchyResolver` phù hợp khi có nhu cầu đó. Không chữa lỗi thiếu thông tin hierarchy bằng cách tắt mọi kiểm tra rồi coi đầu ra là hợp lệ. Xem [ClassHierarchyResolver](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html).

### 9.3. Thêm lời gọi phương thức là một bài toán lớn hơn

Nếu thay phép cộng bằng một lời gọi helper, bạn cần kiểm tra thêm owner, descriptor, loại invocation, khả năng truy cập và dependency runtime của helper. Một helper tồn tại ở classpath của transformer chưa chắc tồn tại trong loader chạy lớp đã biến đổi.

Bài hiện tại tránh các yếu tố này để tập trung vào phân tích phương thức và xác minh một thay đổi nhỏ. Khi thêm chúng vào phạm vi transformer, hãy thêm cả ca kiểm thử liên kết và thực thi tương ứng.

## 10. Bộ trường hợp kiểm tra cần nộp

| Nhóm | Trường hợp | Kỳ vọng |
|---|---|---|
| Luồng chính | Đầu vào đúng lớp mẫu | Xuất tệp mới sau khi các bước kiểm tra đạt |
| Chọn đích | Có hai overload cùng tên | Chỉ `adjust(II)I` thay đổi |
| Nhánh dương | `adjust(10, 3)` | Gốc 13, mới 7 |
| Nhánh bị chặn | `adjust(2, 5)` | Gốc 7, mới 0 |
| Kết quả âm | `adjust(-5, 2)` | Cả hai trả 0 |
| Biên zero | `adjust(0, 0)` | Cả hai trả 0 |
| Biên số nguyên | `MAX_VALUE` và `MIN_VALUE` với tham số thứ hai là 1 | Khớp phép toán `int` và chặn âm |
| Phương thức ngoài phạm vi | `adjust(4)` và constructor | Hành vi giữ như cũ |
| Đích không phù hợp | Lớp không có descriptor đích hoặc không đúng một `IADD` | Dừng rõ ràng trước khi xuất |
| Bytecode sai | Thêm `POP` sau `IADD` | Bị từ chối khi tạo mã hoặc xác minh |
| Biến đổi vượt phạm vi | Áp dụng cho mọi overload | Scope check hoặc kiểm tra hành vi thất bại |
| Tệp vào và ra trùng nhau | Cùng đường dẫn hoặc cùng tệp đã tồn tại | Dừng trước khi ghi |

Không chỉ kiểm tra một cặp giá trị mà cả bản gốc lẫn bản biến đổi đều trả zero. Những trường hợp đó không phân biệt được phép cộng với phép trừ.

Với phương thức không có `Code`, bộ phân tích phải báo `code=false` mà không ném lỗi vì gọi `Optional.get()` vô điều kiện. Có thể thêm một lớp abstract hoặc native riêng làm đầu vào cho phần **phân tích**, nhưng lớp đó không phải đầu vào hợp lệ của phép biến đổi chuyên biệt `Calculator` trong lời giải.

## 11. Những lỗi thường gặp

| Hiện tượng | Cần xem lại |
|---|---|
| Chỉ lọc theo tên `adjust` | Chưa phân biệt descriptor |
| Verify trả danh sách rỗng nhưng kết quả sai | Thiếu kiểm tra hành vi hoặc thay sai phạm vi |
| Bản sau vẫn chạy như bản trước | Chưa đổi opcode, chọn nhầm overload hoặc đã nạp nhầm định nghĩa lớp |
| Gặp lỗi định nghĩa lớp hai lần | Dùng lại một defining class loader |
| Nhãn hoặc nhánh điều kiện bị hỏng | Bỏ quên chuyển tiếp `CodeElement` không phải instruction |
| Parse ban đầu thành công nhưng duyệt thân mới lỗi | Chưa tính đến việc parse lazy |
| Không biên dịch được `java.lang.classfile` với `--release 22` | Công cụ đang dùng API chuẩn từ Java 24 |
| Đọc được class file nhưng không chạy được công cụ trên JDK 22 | Nhầm phiên bản tệp đầu vào với phiên bản runtime của transformer |
| Chạy lần hai trên đầu ra thì precondition thất bại | Phép đổi là một lần: đích không còn `IADD` dự kiến |
| Dùng byte diff để kết luận mọi metadata đều giữ nguyên | Chưa chọn phép so sánh cấu trúc và hành vi phù hợp |

Phép đổi tham khảo cố ý báo lỗi nếu áp dụng lại trên đầu ra. Nó không được thiết kế như một transform idempotent tự bỏ qua lớp đã xử lý. Nếu cần tính chất đó, hãy định nghĩa dấu hiệu nhận diện và hành vi lần chạy tiếp theo một cách tường minh.

## 12. Bài tập mở rộng và tiêu chí hoàn thành

Sau khi hoàn tất luồng chính, chọn một hướng mở rộng:

1. **Báo cáo chi tiết hơn:** thống kê opcode theo từng phương thức, tách constructor và xử lý phương thức không có thân.
2. **Kiểm tra operand:** mở rộng scope check để so sánh slot biến cục bộ, đích nhảy hoặc thông tin lời gọi khi biến đổi có thể tác động tới các dữ liệu này.
3. **Chèn theo dõi thực thi:** thêm lời gọi một helper public static và kiểm tra dependency của helper trong loader thực thi.
4. **Xử lý nhiều lớp:** ghi riêng trạng thái parse, build, verify và kiểm tra hành vi cho từng lớp; một lớp lỗi không được nhận nhãn thành công.
5. **Kiểm tra tính lặp:** thiết kế rõ lần chạy thứ hai phải từ chối hay bỏ qua một lớp đã biến đổi, rồi viết ca kiểm tra cho lựa chọn đó.

Sản phẩm nộp gồm hai tệp nguồn, lớp gốc, lớp sau biến đổi, báo cáo phương thức trước và sau, chẩn đoán verify và kết quả các ca hành vi. Ghi phiên bản JDK biên dịch/chạy, các giá trị `--release`, lệnh đã dùng và kết quả ca đối chứng.

Bài đạt yêu cầu khi bạn giải thích được vì sao phép đổi `IADD → ISUB` vẫn có thể hợp lệ với JVM, chứng minh đã chọn đúng phương thức, và cho thấy các kiểm tra hành vi phát hiện được những lỗi mà verifier không thể hiểu theo yêu cầu nghiệp vụ.
