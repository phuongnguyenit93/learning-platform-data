# ClassFormatError, VerifyError và ClassCircularityError trong Java ClassLoader

## 1. Ba lỗi đều liên quan đến JVM loading/linking, nhưng không đồng nghĩa

Khi JVM nạp một Java class, vấn đề không dừng ở việc tìm được tệp `.class`. JVM còn phải đọc cấu trúc class file, kiểm tra phiên bản, xác định quan hệ superclass/superinterface, xác minh bytecode và liên kết các tham chiếu. Ba lỗi sau thường bị gộp nhầm thành “class không load được”:

- **`ClassFormatError`:** dữ liệu class file **không có định dạng hợp lệ** hoặc không thể được JVM diễn giải thành class file hợp lệ.
- **`VerifyError`:** JVM phát hiện class file **không qua được bước bytecode verification**: các quy tắc an toàn kiểu, operand stack, local variables hoặc control flow không được thỏa mãn.
- **`ClassCircularityError`:** JVM phát hiện **vòng trong quan hệ kế thừa superclass hoặc superinterface** khi đang nạp/định nghĩa class hoặc interface.

Đây là **ba loại `Error` thuộc nhánh `LinkageError`**, không phải `ClassNotFoundException`. Nếu gặp chúng, cách xử lý thường là **sửa class file, phiên bản compiler/transformer hoặc đồ thị kế thừa**, thay vì chỉ thêm JAR vào classpath.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt lỗi cấu trúc class file, lỗi verifier và lỗi circular inheritance.
2. Hiểu lỗi có thể xuất hiện ở những thời điểm khác nhau trong loading/linking, không chỉ ngay tại lệnh `loadClass`.
3. Tái hiện **cả ba lỗi** bằng Java 17+ mà không cần thư viện ngoài.
4. Phân biệt `ClassCircularityError` với **vòng khởi tạo static**, **chu trình tham chiếu object**, và **deadlock giữa class loaders**.
5. Debug lỗi đúng theo runtime JDK, bytes đã triển khai, ClassLoader, bytecode transformation và dependency graph.

## 2. Cây kế thừa exception: vị trí của từng lỗi

```text
java.lang.Throwable
├── java.lang.Exception
│   └── ClassNotFoundException              [checked]
└── java.lang.Error
    └── LinkageError
        ├── ClassFormatError
        │   └── UnsupportedClassVersionError
        ├── VerifyError
        ├── ClassCircularityError
        ├── NoClassDefFoundError
        ├── IncompatibleClassChangeError
        │   ├── NoSuchMethodError
        │   ├── NoSuchFieldError
        │   └── IllegalAccessError
        └── ExceptionInInitializerError
```

Các nhánh trong sơ đồ chỉ liệt kê những loại liên quan tới bài; đây **không phải toàn bộ** các subclass của `LinkageError`.

Điều quan trọng:
- `ClassFormatError`, `VerifyError` và `ClassCircularityError` là **ba nhánh độc lập trực tiếp dưới `LinkageError`**.
- `UnsupportedClassVersionError` là **subclass của `ClassFormatError`**, dùng khi major/minor class-file version không được runtime hỗ trợ.
- `ClassNotFoundException` là một **checked exception** ở nhánh `Exception`: thể hiện yêu cầu tìm lớp không thành công theo API ClassLoader.
- `NoClassDefFoundError` thường xuất hiện khi JVM cần một định nghĩa không khả dụng hoặc một class đã khởi tạo thất bại; **không phải tên gọi thay thế** của cả ba lỗi đang xét.
- Các `Error` này bình thường **không nên bị bắt rồi nuốt** ở code nghiệp vụ; có thể phân loại tại boundary của plugin/container để báo lỗi artifact và từ chối kích hoạt plugin.

## 3. Lỗi phát sinh ở giai đoạn nào?

Một cách khái quát:

```text
Yêu cầu nạp: loadClass("plugin.Greeter")
                  │
                  ▼
      ClassLoader tìm bytecode
                  │
                  ├─ không tìm thấy ──► ClassNotFoundException
                  │
                  ▼
           defineClass(bytes)
                  │
                  ├─ cấu trúc class file hỏng
                  │      └──► ClassFormatError
                  │
                  ├─ major/minor version không hỗ trợ
                  │      └──► UnsupportedClassVersionError
                  │
                  ├─ vòng superclass/superinterface
                  │      └──► ClassCircularityError
                  │
                  └─ định nghĩa class
                         │
                         ▼
                Linking / verification
                         │
                         ├─ bytecode vi phạm verifier
                         │      └──► VerifyError
                         │
                         └─ class được dùng
                                 │
                                 ▼
                       initialization khi cần
```

Đây là **sơ đồ tư duy**, không phải thứ tự thời gian cố định mà mọi JVM phải thực hiện một cách đầy đủ trước mỗi lệnh. JVMS cho phép nhiều hoạt động liên kết/đặc biệt là resolution diễn ra **lười** trong giới hạn đặc tả.

Một `ClassLoader.loadClass(name)` trả được `Class<?>` không bảo đảm:
- toàn bộ method bytecode đã được sử dụng;
- mọi symbolic reference đã được resolution;
- static initializer đã chạy;
- mọi dependency sẽ tải thành công về sau.

Trong thử nghiệm Java ở mục 8, `VerifyError` được kích hoạt chắc chắn bằng cách **dùng reflection gọi method chứa bytecode hỏng**, chứ không suy rằng chỉ gọi `loadClass` đã bắt buộc verification mọi thứ.

## 4. ClassFormatError: class file không hợp lệ về cấu trúc

### 4.1. Class file là một định dạng nhị phân có quy tắc

Theo JVM Specification, phần đầu của class file có dạng:

```text
u4 magic                 // 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
cp_info constant_pool[constant_pool_count - 1]
u2 access_flags
u2 this_class
u2 super_class
...
```

Class file còn có tables interfaces, fields, methods và attributes; các constant-pool entries tham chiếu nhau bằng indices có quy tắc. File mang đuôi `.class` nhưng thực chất là HTML response, ZIP/JAR, text, tệp tải dở hoặc bytes từ transformer bị lỗi không trở thành class hợp lệ nhờ tên file.

**Ví dụ nguyên nhân thường gặp:**

1. Magic number không phải `CAFEBABE`.
2. File thiếu bytes, bị truncate, đọc nhầm offset hoặc còn dữ liệu ở định dạng nén khác.
3. Constant pool tag/count/index không hợp lệ.
4. Các bảng/attributes có độ dài hoặc cấu trúc sai.
5. Tên descriptor, field/method attributes hoặc class-file constraints không thỏa mãn.
6. Bytecode generator/shader/obfuscator/agent làm hỏng phần class file.
7. Loader đọc nhầm resource vì map từ binary name sang file path sai.

`ClassFormatError` biểu thị **dữ liệu có vấn đề**, không phải `ClassLoader` chắc chắn không tìm được dữ liệu.

### 4.2. ClassFormatError và UnsupportedClassVersionError

`UnsupportedClassVersionError` là lỗi con của `ClassFormatError`, khi version trong class file không được JVM hỗ trợ. Các mốc thường gặp:

| Java source/runtime release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Một ứng dụng chạy Java 17 mà đọc bytes class được build cho Java 21 (major 65) có thể gặp `UnsupportedClassVersionError`. Không nên chẩn đoán thành lỗi “thiếu JAR”.

**Cách xử lý:** so `java -version` với `javac -version`, kiểm tra đúng class file đang deploy, biên dịch `javac --release 17` khi mã và dependencies cho phép, hoặc nâng runtime.

`minor_version` cũng có ý nghĩa, nhất là class files gắn **preview features**. Đừng đổi vài bytes version trong file để “tương thích” runtime cũ: opcode, constant pool, API và semantics có thể khác.

### 4.3. Ví dụ phản trực giác

Một custom loader:

```java
// Trích đoạn trong findClass(String name):
byte[] bytes = Files.readAllBytes(classFile);
return defineClass(name, bytes, 0, bytes.length);
```

Nếu path tồn tại và `bytes.length > 0`, chỉ chứng minh đã đọc được bytes. **Không chứng minh** dữ liệu hợp lệ, thuộc đúng binary name, có đúng version hoặc qua verifier.

Kiểm tra magic `CAFEBABE` là một precheck tốt nhưng **không thay thế** JVM verification/format validation.

## 5. VerifyError: class file có thể parse được nhưng bytecode không hợp lệ

### 5.1. Verifier kiểm tra điều gì?

Bytecode verifier xác minh các điều kiện an toàn của code bên trong methods, liên quan:

- Loại giá trị trên **operand stack** tương thích với opcode đang sử dụng.
- Độ sâu stack không âm và không vượt các giới hạn hợp lệ.
- Các giá trị trong **local variables** được sử dụng đúng kiểu/trạng thái.
- Các nhánh `if`, `goto` và exception handler có trạng thái stack/local variables phù hợp tại nơi giao nhau.
- Các quy tắc liên quan `StackMapTable` của class-file versions áp dụng được đáp ứng.
- Constructor và giá trị `uninitializedThis`/`uninitialized` không bị sử dụng sai.
- Giá trị trả về có kiểu đúng với method descriptor, ví dụ method `()I` phải trả `int`.
- Các điều kiện verification khác theo JVMS.

### 5.2. Ví dụ bytecode sai kiểu trả về

Java source hợp lệ:

```java
public class VerifyTarget {
    public static int value() {
        return 1;
    }
}
```

Compiler có thể sinh bytecode cho method `value`:

```text
iconst_1  // đưa int 1 lên stack
ireturn   // trả int từ operand stack
```

Nếu một transformer cố ý đổi opcode `iconst_1` thành `aconst_null` nhưng giữ nguyên `ireturn`, stack chứa **reference null** trong khi `ireturn` đòi **int**:

```text
aconst_null  // reference
ireturn      // yêu cầu int
             // → verifier phát hiện xung đột kiểu
```

`VerifyError` là lỗi đúng bản chất ở đây: phần cấu trúc class file có thể vẫn parse được, nhưng **method instructions vi phạm typing constraints**.

Đây **không phải lỗi compiler Java nguồn thông thường**. `javac` tự kiểm tra type safety và sinh bytecode hợp lệ. Các trường hợp VerifyError trong production thường gợi ý:
- class file bị chỉnh sửa sau compilation;
- bytecode instrumentation không cập nhật stack map frames;
- công cụ code generation/obfuscation làm sai control flow;
- mismatch version của agent/framework với class-file version được xử lý.

### 5.3. Không “sửa” bằng cách bỏ verifier

Không khuyến nghị dùng option cũ để vô hiệu hóa verification hoặc sửa sai bytecode bằng việc bỏ các checks. Một số flags đã bị loại bỏ hoặc không còn được hỗ trợ ở JDK mới. Việc tắt verifier có thể gây crash hoặc hành vi không an toàn; cần sửa bytes/transformer.

## 6. ClassCircularityError: quan hệ kế thừa bị vòng

`ClassCircularityError` được JVM ném khi **phát hiện vòng trong superclass/superinterface hierarchy** trong quá trình load/derive một class hoặc interface.

Ví dụ không hợp lệ ở mức đồ thị:

```text
class A extends B
class B extends A

A ──superclass──▶ B
▲                 │
└────superclass───┘

→ ClassCircularityError
```

Hoặc một interface graph vòng:

```text
interface X extends Y
interface Y extends X

X ──superinterface──▶ Y
▲                    │
└────superinterface──┘
```

**Java source compiler bình thường từ chối các chu trình kế thừa**. Vì vậy lỗi này thường liên quan tới:
- bytecode đã bị chỉnh sửa/sinh động, không đi qua kiểm tra Java source bình thường;
- transformer thao tác sai `super_class` hoặc `interfaces` trong class file;
- class-loader setup và các class definitions phối hợp không đúng khi load graph;
- artifact hỏng hoặc generator tạo quan hệ type hierarchy không hợp lệ.

### 6.1. Dòng nào trong class file quyết định superclass?

Sau constant pool và `access_flags`, class file có:

```text
u2 this_class      // index của class đang được định nghĩa
u2 super_class     // index của superclass (0 chỉ trong trường hợp đặc biệt)
```

`this_class` và `super_class` tham chiếu tới các `CONSTANT_Class_info` entries. Nếu sửa `super_class` của `CycleTarget` để tham chiếu **chính `this_class`**, class file mô tả một lớp **extends chính nó**. JVM phát hiện vòng đó khi tạo class và ném `ClassCircularityError`.

### 6.2. Đừng nhầm với circular dependency thông thường

Những tình huống sau **không mặc nhiên gây `ClassCircularityError`**:

- Class A giữ field kiểu B, và B giữ field kiểu A.
- Hai object tham chiếu lẫn nhau.
- Method A gọi method B và B gọi lại A.
- Static initializer A đọc static field của B, B đọc lại A.
- Hai class loaders ủy quyền chéo và các threads bị deadlock.
- Hai classes cùng tên được định nghĩa bởi hai loaders khác nhau.

Lỗi cần **vòng trong quan hệ superclass/superinterface tại quá trình nạp/định nghĩa**. Việc hai class có phụ thuộc lẫn nhau về fields, methods hoặc data **không phải quan hệ kế thừa**.

## 7. Tổng hợp ba lỗi: dấu hiệu và hướng xử lý

| Lỗi | JVM phát hiện | Ví dụ nguồn gốc | Kiểm tra đầu tiên |
|---|---|---|---|
| `ClassFormatError` | Class file sai định dạng/ràng buộc cấu trúc | Magic sai, constant pool lỗi, truncate | Header, bytes thực, transformer |
| `VerifyError` | Method bytecode không thỏa verification | `ireturn` khi stack là reference; frames sai | `javap -v -c`, StackMapTable, instrumentation |
| `ClassCircularityError` | Vòng superclass/superinterface hierarchy | A extends B extends A, self-superclass | `super_class`, interfaces, type graph |
| `UnsupportedClassVersionError` | Major/minor không được JVM hỗ trợ | JDK runtime cũ hơn target | `java -version`, `javap -verbose` |
| `ClassNotFoundException` | Loader không tìm thấy requested class | Tên sai, URL/path thiếu JAR | ClassLoader hierarchy, classpath |
| `NoClassDefFoundError` | JVM cần class definition không khả dụng hoặc class init từng lỗi | Thiếu dependency, wrong name, erroneous class | Cause chain, loader, init log |

Có thể có **nhiều lỗi nối tiếp**: class file bị hỏng khiến một class không thể load; về sau class phụ thuộc vào nó có thể báo một `LinkageError` khác. Luôn tìm **lỗi đầu tiên và artifact thực tế**, không chỉ đọc message ở cuối log.

## 8. Thí nghiệm Java 17+ tái hiện chính xác cả ba lỗi

Thí nghiệm này cố ý thay đổi bytes **trong bộ nhớ**; **không** ghi đè file `.class` thật của dự án và **không cần ASM/Byte Buddy**. Ta biên dịch hai class hoàn toàn hợp lệ:

1. `VerifyTarget` có method trả về `int 1`.
2. `CycleTarget` extends `Object`.

Sau đó một host loader dùng bytes biến đổi:
- bytes ngẫu nhiên → `ClassFormatError`;
- opcode `iconst_1` bị đổi thành `aconst_null` → `VerifyError`;
- `super_class` được đổi thành `this_class` → `ClassCircularityError`.

Demo dùng **ClassLoader khác cho mỗi trường hợp**, tránh trạng thái `findLoadedClass` từ lượt trước. Chương trình chạy trên **Java 17+**; kết quả bên dưới được kiểm chứng khi dùng `javac --release 17` và chạy trên OpenJDK 21.

### 8.1. File VerifyTarget.java

```java
public class VerifyTarget {
    public static int value() {
        return 1;
    }
}
```

### 8.2. File CycleTarget.java

```java
public class CycleTarget {
}
```

Cả hai là classes ở **default package** chỉ để tối giản demo. Trong hệ thống thật, dùng package rõ ràng cho plugin và tránh default package.

### 8.3. File ErrorKindsDemo.java

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class ErrorKindsDemo {

    static final class BytesLoader extends ClassLoader {
        private final String target;
        private final byte[] bytes;

        BytesLoader(String target, byte[] bytes) {
            super(ErrorKindsDemo.class.getClassLoader());
            this.target = target;
            this.bytes = bytes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(target)) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static int u2(byte[] bytes, int offset) {
        return ((bytes[offset] & 0xff) << 8)
                | (bytes[offset + 1] & 0xff);
    }

    static byte[] badFormat() {
        // Không phải magic CAFEBABE / class file hợp lệ.
        return new byte[] {0, 1, 2, 3, 4, 5};
    }

    static byte[] badVerify(byte[] input) {
        byte[] bytes = input.clone();
        int match = -1;

        // Với method "return 1;" khi javac --release 17,
        // iconst_1; ireturn được mã hóa là 04 ac.
        for (int i = 0; i + 1 < bytes.length; i++) {
            if ((bytes[i] & 0xff) == 0x04
                    && (bytes[i + 1] & 0xff) == 0xac) {
                if (match != -1) {
                    throw new IllegalStateException(
                            "Not unique sequence");
                }
                match = i;
            }
        }

        if (match == -1) {
            throw new IllegalStateException(
                    "Bytecode sequence missing");
        }

        // iconst_1 (int) -> aconst_null (reference),
        // nhưng ireturn phía sau vẫn yêu cầu int.
        bytes[match] = 0x01;
        return bytes;
    }

    static byte[] badCycle(byte[] input) {
        byte[] bytes = input.clone();
        int pos = 8; // Sau magic, minor_version, major_version.
        int cpCount = u2(bytes, pos);
        pos += 2;

        // Duyệt constant pool để tới access_flags/this/super.
        for (int i = 1; i < cpCount; i++) {
            int tag = bytes[pos++] & 0xff;
            switch (tag) {
                case 1 -> {
                    int length = u2(bytes, pos);
                    pos += 2 + length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                        pos += 4;
                case 5, 6 -> {
                    pos += 8;
                    i++; // long/double chiếm hai CP slots.
                }
                case 7, 8, 16, 19, 20 -> pos += 2;
                case 15 -> pos += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant tag: " + tag);
            }
        }

        pos += 2; // access_flags
        int selfIndex = u2(bytes, pos); // this_class
        pos += 2; // super_class offset

        // Biến superclass thành chính class này.
        bytes[pos] = (byte) (selfIndex >>> 8);
        bytes[pos + 1] = (byte) selfIndex;

        return bytes;
    }

    static void inspect(String title, String className, byte[] bytes)
            throws Exception {
        try {
            Class<?> type = Class.forName(
                    className,
                    true,
                    new BytesLoader(className, bytes)
            );

            // Ép trường hợp VerifyTarget sử dụng method:
            // JVM có thể trì hoãn verification tới khi cần.
            if ("VerifyTarget".equals(className)) {
                type.getMethod("value").invoke(null);
            }
            System.out.println(title + " -> unexpectedly loaded");

        } catch (LinkageError error) {
            System.out.println(
                    title + " -> "
                    + error.getClass().getSimpleName()
            );

        } catch (ClassNotFoundException error) {
            System.out.println(
                    title + " -> ClassNotFoundException"
            );
        }
    }

    public static void main(String[] args) throws Exception {
        inspect(
                "bad format",
                "BrokenFormat",
                badFormat()
        );

        inspect(
                "bad verifier",
                "VerifyTarget",
                badVerify(Files.readAllBytes(
                        Path.of("inputs/VerifyTarget.class")))
        );

        inspect(
                "circular superclass",
                "CycleTarget",
                badCycle(Files.readAllBytes(
                        Path.of("inputs/CycleTarget.class")))
        );
    }
}
```

### 8.4. Tạo thư mục, biên dịch, chạy

Đặt ba source files trong một thư mục làm việc:

```text
classloader-errors/
├── VerifyTarget.java
├── CycleTarget.java
├── ErrorKindsDemo.java
├── inputs/
└── host/
```

Trên Bash/Linux/macOS:

```bash
mkdir -p inputs host
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force inputs,host | Out-Null
```

Biên dịch với JDK 17+ nhưng nhắm class-file target Java 17:

```bash
javac --release 17 -d inputs VerifyTarget.java CycleTarget.java
javac --release 17 -d host ErrorKindsDemo.java
java -cp host ErrorKindsDemo
```

**Không thêm thư mục `inputs` vào `-cp` của host.** Nếu làm vậy, parent application loader có thể định nghĩa `VerifyTarget` hoặc `CycleTarget` trước khi `BytesLoader.findClass` được gọi, khiến demo không sử dụng bytes bị sửa.

### 8.5. Stdout đã kiểm chứng

```text
bad format -> ClassFormatError
bad verifier -> VerifyError
circular superclass -> ClassCircularityError
```

Chương trình chỉ in **simple class name** của error để tránh phụ thuộc vào message chi tiết khác nhau giữa các JDK/runtime.

### 8.6. Tại sao từng nhánh phát sinh lỗi?

**Nhánh bad format:**
- `badFormat()` tạo mảng 6 bytes không có magic `CAFEBABE` và không có cấu trúc class file.
- `BytesLoader.findClass("BrokenFormat")` gọi `defineClass`.
- JVM từ chối bytes, nên `ClassFormatError` được ném.

**Nhánh bad verifier:**
- File `VerifyTarget.class` gốc được `javac --release 17` sinh hợp lệ.
- `badVerify` tìm đúng chuỗi opcode `04 ac` dành cho `iconst_1; ireturn` trong target demo và đổi `04` thành `01` (`aconst_null`).
- File vẫn có header, constant pool và method structure, nhưng instruction sequence trả reference ở vị trí đòi int.
- `Class.forName(..., true, ...)` và reflective invocation khiến JVM phải kiểm tra/sử dụng method; verifier phát hiện bất hợp lệ, ném `VerifyError`.

**Nhánh circular superclass:**
- `badCycle` đọc class-file constant pool đủ để tìm offset của `this_class` và `super_class`.
- Chương trình đổi `super_class` thành cùng index với `this_class`.
- Đây là class-file graph có superclass trỏ vào chính lớp đó, tạo circularity.
- JVM phát hiện lỗi khi tạo class và ném `ClassCircularityError`.

### 8.7. Các giới hạn của demo

- `badVerify` cố ý dựa vào pattern `04 ac` của **class được biên dịch từ source trên với `--release 17`**. Nếu bạn thay method, chạy obfuscator hoặc compiler sinh bytecode khác, chương trình chủ động ném `IllegalStateException` thay vì âm thầm sửa sai bytes. Với production transformer, phải parse Code attributes theo spec bằng công cụ thích hợp, không scan raw bytes kiểu này.
- `badCycle` là parser **rút gọn** chỉ để đi qua constant pool đến `super_class`. Nó xử lý tags cần cho class-file format thông dụng; không phải class-file reader bảo mật/thương mại đầy đủ, không validate mọi độ dài hay dữ liệu đầu vào. Dùng nó trên **input tự biên dịch hợp lệ** như hướng dẫn.
- Reflection có thể gây các ngoại lệ khác như `NoSuchMethodException`/`InvocationTargetException` nếu bạn sửa source để không còn method phù hợp. Đừng dùng ví dụ này làm loader tổng quát cho class bất kỳ.
- `BytesLoader` không định nghĩa package/lớp từ một JAR thật; nó chỉ dùng `defineClass` trên mảng bytes để minh họa ba lỗi.
- Không dùng các tệp bytes đã cố ý phá hỏng trong ứng dụng thật hoặc phát hành chúng như artifacts.

## 9. Thí nghiệm đối chứng: vòng static initialization không phải ClassCircularityError

Java cho phép hai class cùng tham chiếu tới **static fields của nhau**. Điều đó **không** tạo chu trình kế thừa superclass/superinterface.

Tạo `InitializationCycleDemo.java`:

```java
public class InitializationCycleDemo {
    static final class First {
        static int a = Second.b + 1;
    }

    static final class Second {
        static int b = First.a + 1;
    }

    public static void main(String[] args) {
        System.out.println("First.a=" + First.a);
        System.out.println("Second.b=" + Second.b);
    }
}
```

Chạy:

```bash
javac --release 17 InitializationCycleDemo.java
java InitializationCycleDemo
```

Stdout:

```text
First.a=2
Second.b=1
```

Giải thích:

1. Khi `main` đọc `First.a`, JVM bắt đầu initialization của `First`. `First.a` ban đầu có giá trị mặc định `0` trước khi được gán bởi initializer.
2. `First.a = Second.b + 1` kích hoạt initialization của `Second`.
3. `Second.b = First.a + 1` tham chiếu `First.a` trong khi `First` đang được initialized **bởi cùng thread**. JVM không khởi tạo lại First; giá trị `First.a` lúc này vẫn là `0`.
4. `Second.b` được gán `1`, rồi quay lại `First.a` được gán `2`.
5. Hai biến có giá trị `2` và `1`. **Không hề có lớp nào extends chính mình hoặc vòng superclass.**

Đây là trường hợp **trạng thái initialization chưa hoàn tất**, không phải class circularity. Với nhiều threads, circular initialization có thể dẫn đến chờ/deadlock tùy code đồng bộ; nhưng ngay cả deadlock đó cũng không đồng nghĩa `ClassCircularityError`.

## 10. Circular loader delegation khác circular type hierarchy

Một custom loader có thể được cấu hình ủy quyền chéo:

```text
Loader-A.loadClass("x.Service")
    └── Loader-B.loadClass("x.Service")
           └── Loader-A.loadClass("x.Service")
                  └── ...
```

Đây là **chu trình trong thuật toán tìm class**, có thể gây recursion quá sâu, `StackOverflowError` hoặc deadlock do locking, tùy code. Không nhất thiết có circular superclass/superinterface relation.

Ngược lại:

```text
class A extends B
class B extends A
```

là **chu trình trong type hierarchy**. JVM báo `ClassCircularityError` khi phát hiện theo thuật toán class creation/loading.

Phân biệt hai loại graph:
- **Loader delegation graph:** loader nào hỏi loader nào.
- **Superclass/superinterface graph:** class/interface nào extends class/interface nào.

Một chương trình có thể có cả hai vấn đề, nhưng debug phải xác định vòng thực sự nằm ở đâu.

## 11. Trường hợp lỗi xuất hiện sau khi loadClass đã thành công

Trong JVM, **class loading, verification, resolution và initialization** có thể xảy ra ở các thời điểm khác nhau. Do đó:

```java
// Trích đoạn: loader là ClassLoader do ứng dụng quản lý.
Class<?> type = loader.loadClass("demo.Plugin");
System.out.println(type.getName()); // Có thể thành công.

// Lỗi có thể chỉ xuất hiện ở một sử dụng sau đó:
type.getDeclaredMethods();
```

Đây là **đoạn minh họa, không phải file chạy độc lập**. Không cam kết `getDeclaredMethods()` luôn gây `VerifyError` nếu class hỏng; tùy loại vi phạm và JVM timing. Ý chính: **không xác nhận plugin an toàn chỉ từ một lần `loadClass` không ném lỗi**.

Trong hệ plugin:
- Một method được gọi hiếm gặp có thể chỉ được verify/resolve muộn.
- Một dependency mới có thể chỉ được load khi tính năng đó được kích hoạt.
- AOP/agent transformer có thể chỉ áp dụng cho các class lần đầu được yêu cầu sau startup.
- Test chỉ nạp entry-point class chưa bao phủ toàn bộ provider implementations.

Muốn đảm bảo hơn, chạy integration tests theo các code paths quan trọng, không chỉ gọi `Class.forName` lên một class rồi tuyên bố artifact đúng.

## 12. Vai trò của custom ClassLoader đối với ba lỗi

Một custom loader thường đọc bytes rồi định nghĩa class:

```java
// Trích đoạn bên trong ClassLoader subclass:
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    String path = name.replace('.', '/') + ".class";
    byte[] bytes;

    try {
        bytes = Files.readAllBytes(root.resolve(path));
    } catch (IOException cause) {
        throw new ClassNotFoundException(name, cause);
    }

    return defineClass(name, bytes, 0, bytes.length);
}
```

Đây là **trích đoạn**; cần `root`, imports và class loader superclass thích hợp. Ranh giới trách nhiệm:

- `Files.readAllBytes`: giải quyết lỗi I/O của nguồn bytes.
- `defineClass`: yêu cầu JVM đọc cấu trúc class file và tạo runtime class.
- Verification/linking: do JVM thực hiện theo quy tắc.
- ClassLoader không được mặc nhiên bỏ qua `LinkageError` hay “sửa” bytes bằng exception mapping.

**Anti-pattern**:

```java
// KHÔNG dùng trong production:
try {
    return defineClass(name, bytes, 0, bytes.length);
} catch (Throwable ignored) {
    throw new ClassNotFoundException(name);
}
```

Đây là trích đoạn lỗi. Nó xóa thông tin về:
- `ClassFormatError`;
- `VerifyError`;
- `ClassCircularityError`;
- `OutOfMemoryError` và những errors nghiêm trọng khác.

Người debug sẽ tưởng rằng class chỉ thiếu file và thử đổi classpath vô ích. **Chỉ chuyển những lỗi I/O thực sự thuộc lookup path thành `ClassNotFoundException` khi hợp đồng loader phù hợp, giữ original cause.**

## 13. ClassFormatError còn có thể xuất hiện khi magic đúng

Chỉ nhìn `0xCAFEBABE` là chưa đủ.

Ví dụ những dữ liệu vẫn bắt đầu bằng magic hợp lệ nhưng có thể bị JVM từ chối:
- `constant_pool_count` mô tả nhiều entries hơn bytes còn lại.
- Một `CONSTANT_Class_info` tham chiếu đến CP slot không tồn tại hoặc tag sai.
- `Code` attribute khai báo length không khớp nội dung.
- Method signature/descriptor sai grammar.
- Trùng/không hợp lệ ở những class-file structures bị đặc tả cấm.
- Các flags, arrays và attributes không đáp ứng class file constraints.

Một phần lỗi có thể có tên `ClassFormatError` hoặc một lỗi cụ thể khác theo điều kiện mà JVM phát hiện; **đừng khẳng định mọi thao tác sửa bytes đều dẫn đúng một loại Error cố định**.

Muốn kiểm tra:
- Đối chiếu file bytes với artifact gốc từ build output và artifact cuối trên disk/JAR.
- Sử dụng `javap -verbose` để xem CP và attributes nếu tool parse được.
- Nếu có transformer, so sánh **before/after bytes**, không chỉ source Java.
- Dùng checksum để tránh đang debug nhầm JAR hoặc phiên bản đã được container cache.

## 14. VerifyError thường đi cùng StackMapTable như thế nào?

Đối với class files hiện đại, verifier sử dụng thông tin từ `StackMapTable` theo quy tắc JVMS. Bytecode transformers cần giữ các invariants khi:
- thêm/xóa opcode;
- thay branch destinations;
- thêm try/catch handlers;
- thay local variable slots hoặc operand-stack shapes;
- đổi method descriptor/return type;
- thay constructor initialization path.

Ví dụ transformer chèn thêm nhánh:

```text
if (condition) goto L1
...
L1:
   dùng local variable mà một đường trước đó
   chưa xác định đúng type
```

Nếu các control-flow paths hợp nhất với trạng thái stack/local variables không tương thích, JVM có thể ném `VerifyError`. Đó là lỗi **bytecode verification**, dù class file header và CP vẫn hợp lệ.

Một số tool như ASM có công cụ recompute frames (`COMPUTE_FRAMES`) và max stack. Tuy nhiên bật tính năng tính frames không tự sửa một thuật toán transform sai: phải bảo đảm method semantics và exception handlers hợp lệ.

### Không nhầm với lỗi binary API

Nếu method bytecode **qua verifier**, nhưng runtime library thiếu một method từng có lúc compile, lời gọi sau đó có thể ném `NoSuchMethodError`. Nếu method static/instance contract thay đổi, có thể là `IncompatibleClassChangeError`. Nếu access thay đổi, có thể `IllegalAccessError`.

Đây là những **linkage issues khác**, không phải `VerifyError` chỉ vì chúng phát sinh khi dùng method.

## 15. ClassCircularityError và tính đúng đắn của hierarchy

Một JVM runtime class có một superclass chain theo quy tắc, và interfaces có các superinterfaces. Chuỗi/đồ thị này không được tạo vòng bất hợp lệ.

Ví dụ:
- `A extends B`;
- `B extends C`;
- `C extends A`.

Một source compiler bình thường sẽ từ chối quan hệ như vậy nếu toàn bộ source cùng được phân tích. Nhưng công cụ sinh/ghép class files độc lập hoặc deploy mismatched artifacts có thể tạo bytes trình bày một đồ thị kế thừa vòng.

Khi JVM yêu cầu định nghĩa `A`, nó cần xác định các kiểu super liên quan. Nếu phát hiện class đang cần định nghĩa lại trong chính chuỗi super, **`ClassCircularityError`** phản ánh vòng superclass/superinterface.

### Circularity có phải deadlock?

Không. `ClassCircularityError` là một loại `LinkageError` mà JVM ném ra để báo một type hierarchy không hợp lệ; deadlock là các threads khóa/chờ nhau mà có thể không ném exception.

### Object graph có cycle có sai không?

Không. Hai objects giữ reference nhau là tình huống thường gặp và GC hỗ trợ thu gom cả chu trình khi không reachable từ roots:

```java
class Node {
    Node next;
}
```

Đoạn trên hợp lệ. `a.next=b; b.next=a;` **không liên quan** đến `ClassCircularityError`.

## 16. Kỹ thuật chẩn đoán theo bước

### Bước 1 — Lấy error gốc, không chỉ đọc lớp wrapper

Trong plugin manager, exception từ reflection có thể được bọc bởi `InvocationTargetException`, `ExecutionException` hoặc framework-specific exceptions. Log:
- Loại Throwable thực tế;
- message, stack trace;
- cause chain;
- suppressed exceptions khi có;
- class binary name đang được yêu cầu;
- class loader identity và source URL/JAR.

Ví dụ chỉ ghi `"Error loading plugin"` là chưa đủ.

### Bước 2 — Xác định bytes thực tế

Nếu class xuất hiện trong nhiều JARs, classpath/module path hoặc parent/child loaders, phải biết **file nào thực sự được định nghĩa**. Lưu:
- JAR path và entry;
- version/build hash;
- actual class file bytes hoặc checksum khi có;
- bản bytes trước/sau instrumentation;
- defining loader của các classes load thành công liên quan.

Đừng chỉ nhìn `src/` của dự án rồi suy artifact cuối cũng giống source.

### Bước 3 — So JDK compile và runtime

```bash
java -version
javac -version
```

Nếu phiên bản khác nhau, inspect target compilation. Thông tin như major version rất hữu ích:

```bash
javap -verbose -classpath inputs VerifyTarget
```

Với `javac --release 17`, `major version` thông thường là `61`.

### Bước 4 — Phân biệt ba nhánh

**Nếu `ClassFormatError`:**
- Kiểm tra magic/header, size, constant pool, class-file attributes.
- Xem có đọc nhầm JAR/HTML/resource khác không.
- So artifacts trước/sau transformer.
- Kiểm tra `UnsupportedClassVersionError` trước vì nó là subtype cụ thể.

**Nếu `VerifyError`:**
- Dùng `javap -c -v` để xem opcode và `StackMapTable`.
- Xác định method hoặc control-flow location mà JVM báo.
- So bytecode trước/sau agent, shading, obfuscation.
- Kiểm tra phiên bản bytecode tool hỗ trợ class-file target.

**Nếu `ClassCircularityError`:**
- Xác định class/interface được nhắc trong message.
- Truy `super_class`/`interfaces` từ class file.
- Dựng đồ thị superclass/superinterface các artifacts thực tế; tìm vòng.
- Phân biệt vòng trong loader delegation graph với vòng ở type hierarchy.

### Bước 5 — Tái hiện trong loader và runtime sạch

Nếu class đã được định nghĩa thành công trên một loader, `findLoadedClass` có thể trả class cũ thay vì đọc lại file đã được chỉnh sửa. Khi debug bytecode variants:
- tạo **ClassLoader mới** hoặc chạy JVM process mới;
- bảo đảm parent không có sẵn class cùng tên;
- tách riêng classpaths của host và plugin;
- giữ đúng JVM arguments/agent/plugin classpath từ môi trường xảy ra lỗi.

Đừng khẳng định “file đã được sửa nhưng lỗi vẫn y nguyên” nếu JVM thực tế đang dùng runtime class đã load từ trước.

## 17. Log/quan sát JVM bằng công cụ phù hợp

Trên HotSpot hỗ trợ unified logging:

```bash
java -Xlog:class+load=info -cp host ErrorKindsDemo
```

Lệnh giả định đã tạo `host`/`inputs` theo mục 8 và chạy trong đúng thư mục. Log class loading có thể rất dài; nó **không phải** log đầy đủ của verification/resolution hoặc các bước mà custom loader thực hiện.

Có thể dùng:

```bash
javap -verbose -classpath inputs VerifyTarget
javap -c -classpath inputs VerifyTarget
```

`javap` cho thấy **class gốc trước khi chương trình biến đổi bytes trong bộ nhớ**. Nếu cần xem **bytes bị sửa**, hãy dump một bản tạm ở môi trường test rồi inspect bản đó; tránh ghi đè artifact hợp lệ đang được ứng dụng chạy.

Một custom loader có thể log:

```java
// Trích đoạn trong findClass, trước defineClass:
System.out.println(
        "requested=" + name
        + ", loader=" + this.getClass().getName()
        + ", bytes=" + bytes.length
);
```

Không log raw bytecode hoặc đường dẫn chứa secrets/credential ở production nếu không cần. File checksum thường hữu ích hơn việc in toàn bộ bytes.

## 18. Cách bắt lỗi đúng ở plugin boundary

Ở lớp điều phối plugin, đôi khi cần chuyển JVM errors thành **diagnostic report** thay vì để toàn bộ host chết ngay. Đây là đoạn minh họa:

```java
// TRÍCH ĐOẠN: loader và binaryName là biến sẵn có,
// report(...) là method của plugin manager.
try {
    Class<?> type = loader.loadClass(binaryName);
    activatePlugin(type);

} catch (UnsupportedClassVersionError error) {
    report("Unsupported class file version", error);

} catch (ClassFormatError error) {
    report("Malformed class file", error);

} catch (VerifyError error) {
    report("Bytecode verification failed", error);

} catch (ClassCircularityError error) {
    report("Circular superclass/superinterface hierarchy", error);

} catch (ClassNotFoundException error) {
    report("Class not found by configured loader", error);

} catch (LinkageError error) {
    report("Other JVM linkage error", error);
}
```

**Đây không phải source biên dịch độc lập:** `activatePlugin`, `report`, `loader` và `binaryName` thuộc code ứng dụng.

Những quy tắc thiết yếu:
- **Thứ tự catch:** `UnsupportedClassVersionError` trước `ClassFormatError` vì nó là subclass. Những lỗi cụ thể trước `LinkageError`.
- `ClassNotFoundException` là checked exception, giữ original cause từ I/O/lookup khi phù hợp.
- Đừng catch `Error` hay `Throwable` rộng rồi “cho plugin chạy tiếp như không có gì xảy ra”.
- Một plugin đã thất bại loading/linking có thể không an toàn để tiếp tục; hãy đánh dấu failure state và không kích hoạt instance một phần.
- Cleanup các tài nguyên đã đăng ký trong lúc plugin start (listeners, tasks, classloader) theo lifecycle manager; xử lý được error diagnostic không có nghĩa mọi tác dụng phụ trước error được rollback.
- Nếu thấy `OutOfMemoryError`, `StackOverflowError`, `ThreadDeath` hoặc VM errors khác, chúng **không phải** các trường hợp để fallback tùy tiện sang một JAR khác.

**Không convert `ClassFormatError`/`VerifyError`/`ClassCircularityError` thành `ClassNotFoundException`.** Làm vậy che nguyên nhân kỹ thuật và thường dẫn đến sửa classpath sai chỗ.

## 19. Cơ chế nạp class cha-con không được thay thế nguyên nhân

Loader mặc định thực hiện:

```text
findLoadedClass(name)
   ↓ chưa có
parent.loadClass(name)
   ↓ nếu parent không tìm thấy
findClass(name)
   ↓ defineClass(bytes)
```

Lưu ý khi parent loader ném `ClassFormatError`:
- Đây **không phải `ClassNotFoundException`**.
- Thuật toán `loadClass` chuẩn **không tự catch mọi LinkageError của parent rồi chuyển sang child**.
- Nếu custom loader làm vậy, nó có thể che một bản artifact hỏng ở parent và tùy tiện load bản khác, làm tăng rủi ro class identity, package mismatch hoặc binary compatibility.

Trường hợp thật sự cần tìm từ child trước parent phải định nghĩa **delegation policy** rõ ràng theo namespace và tuân ràng buộc JVM. Không dùng child-first như một “thuốc chữa” chung cho bytecode hỏng.

## 20. Một bảng “triage” để đọc stack trace

| Stack trace có gì? | Điều ưu tiên xác nhận | Điều không nên làm |
|---|---|---|
| `ClassFormatError: Incompatible magic value ...` | Dữ liệu class file có đúng nguồn/format? | Chỉ thêm JAR mà không xem bytes |
| `UnsupportedClassVersionError: class file version ...` | Target major/minor và runtime JDK | Sửa vài byte header cho version thấp |
| `VerifyError: Bad type on operand stack` | Method bytecode, frames, transformer | Tắt verification |
| `VerifyError: Expecting a stackmap frame ...` | Branch target, StackMapTable, Java target | Đoán là ClassNotFoundException |
| `ClassCircularityError: ...` | Superclass/interface graph thực tế | Xem mọi reference field như “inheritance cycle” |
| `NoClassDefFoundError: ...` | Missing dependency, wrong name hoặc init cũ thất bại | Mặc định coi là VerifyError |
| `ClassNotFoundException: ...` | Loader search path/binary name/parent | Mặc định coi file hỏng |
| `NoSuchMethodError` | Compile/runtime ABI của dependency | Sửa StackMapTable vô căn cứ |

Message và stack-trace frames cụ thể là **VM/version-specific**. Bảng dùng để gợi ý hướng tra cứu, không khẳng định string message sẽ giống hệt trên mọi JVM.

## 21. Các lỗi phổ biến khi tự tạo hoặc biến đổi bytecode

Ba lỗi chính cần xử lý bằng **bytes nguồn** và **quy tắc JVM phù hợp**:

| Tình huống thực tế | Dạng lỗi cần phân loại | Cách sửa |
| --- | --- | --- |
| Custom loader lấy nhầm HTML/ZIP hoặc class file bị truncate | `ClassFormatError` | Kiểm tra resource URL, magic, constant pool/attributes và bytes đầu vào `defineClass` |
| Transformer thay branches, operand stack hoặc exception handlers nhưng không cập nhật frames | `VerifyError` | Kiểm tra `Code`, `StackMapTable`, paths và dùng generator tương thích với target JDK |
| Transformer viết `super_class` bằng chính `this_class` hoặc tạo A↔B inheritance | `ClassCircularityError` | Phân tích superclass/superinterface graph từ class files thực tế |

Các tình huống liên quan nhưng **không cùng cơ chế**: runtime Java 17 nhận bytecode major 65 là `UnsupportedClassVersionError`; vòng `static` initialization không phải circular superclass; parent/child loader delegation recursion không tự tạo `ClassCircularityError`.

Nếu loader đã định nghĩa một `Class<?>`, thay JAR trên đĩa và gọi `loadClass` lần nữa có thể trả class cũ. Để tái hiện sửa lỗi bytecode cần **fresh defining loader/JVM** và bảo đảm parent không che bytecode cần kiểm thử. Khi thử nghiệm, đừng bắt mọi `Throwable` rồi chuyển thành `ClassNotFoundException`, vì nó làm mất nguyên nhân thật.

## 22. Checklist phát hành artifact Java an toàn

**Tại build:**
- Cố định target JDK (`--release`) và runtime JDK hỗ trợ.
- Verify versions của ASM/Byte Buddy/Javassist/obfuscator phù hợp class-file version.
- Không bỏ qua compiler warnings quan trọng về invalid bytecode transformer.
- Giữ artifact metadata/checksum truy vết được class file thực sự phát hành.
- Với generated classes, chạy kiểm thử JVM loading và invocation trên JDK đích.

**Tại plugin loading:**
- Phân biệt không tìm thấy bytes với bytes không hợp lệ.
- Dùng đúng parent/shared API; tránh định nghĩa trùng runtime types.
- Dùng đúng binary name khi `defineClass`.
- Không nuốt `LinkageError` rồi fallback âm thầm.
- Dừng activation khi class hierarchy/verification thất bại.

**Tại debugging:**
- Thu đủ stack trace và cause chain của **lỗi đầu tiên**.
- Kiểm tra class loader instance, module/layer khi có, source artifact.
- Dùng `javap -verbose`/`-c`, runtime logs và bytecode before/after transformation.
- Tái hiện trong fresh JVM/loader, cùng phiên bản runtime/properties/agent.
- Đối với `ClassCircularityError`, kiểm tra **graph extends**, không chỉ method calls.

**Tại vận hành:**
- Nếu plugin start thất bại, cleanup resources đã tạo trước khi báo lỗi.
- Không để listener/thread/caches của failed plugin giữ loader trong bộ nhớ.
- Nếu muốn thử bản class đã sửa, tạo loader thế hệ mới thay vì tiếp tục dùng runtime class cũ.
- Không yêu cầu GC/unloading xảy ra ngay sau khi gặp `LinkageError` hoặc gọi `URLClassLoader.close()`.

## 23. Bài tập tự kiểm tra

1. **`ClassFormatError` thuộc checked exception không?** Không; nó extends `LinkageError` → `Error`.
2. **`VerifyError` có phải subclass của `ClassFormatError` không?** Không; là sibling dưới `LinkageError`.
3. **`ClassCircularityError` báo vòng kiểu gì?** Vòng superclass/superinterface hierarchy.
4. **Source Java có `A extends B` và `B extends A` hợp lệ không?** Không; compiler bình thường từ chối.
5. **Field `A.b` có kiểu B và `B.a` có kiểu A có tự tạo ClassCircularityError không?** Không.
6. **Một file có magic đúng có bảo đảm không ném ClassFormatError không?** Không; các cấu trúc khác có thể sai.
7. **Method `int f()` thực hiện `aconst_null; ireturn` có thể gây gì?** `VerifyError`.
8. **`UnsupportedClassVersionError` là subclass nào?** `ClassFormatError`.
9. **`loadClass` thành công có bảo đảm mọi method đã được verifier kiểm tra đầy đủ không?** Không nên giả định; verification/resolution timing có thể khác.
10. **Vòng TCCL/delegation giữa loaders có luôn ném `ClassCircularityError` không?** Không; đó là loại graph khác, có thể recursion/deadlock.
11. **Nếu parent ném `VerifyError`, loader child mặc định có tự dùng phiên bản khác không?** Không; không coi LinkageError là ClassNotFoundException.
12. **Khi chạy Java 17 nhưng class file major 65, loại lỗi thường gặp?** `UnsupportedClassVersionError`.
13. **Vì sao demo dùng loader riêng cho mỗi scenario?** Tránh cache class đã loaded và tách trạng thái thử.
14. **Vì sao không catch `Throwable` rồi ném CNFE?** Che lỗi verifier/format/circularity và cả VM errors khác.
15. **Làm thế nào tìm lỗi ClassFormatError gốc?** Kiểm tra bytes nguồn, header/CP/attributes, transformer và artifacts.
16. **Làm thế nào tìm lỗi VerifyError gốc?** Xem method instructions, StackMapTable, frames và bytecode after instrumentation.
17. **Làm thế nào tìm ClassCircularityError gốc?** Dựng graph superclass/superinterface từ class files thực sự.
18. **Vòng khởi tạo static trong ví dụ `First`/`Second` có ném ClassCircularityError không?** Không; đây là initialization, có thể quan sát giá trị static chưa hoàn thiện.
19. **Sửa .class trên đĩa rồi gọi lại loader cũ có chắc nhận bản sửa không?** Không; loader có thể đã định nghĩa runtime class cũ.
20. **Plugin manager nên làm gì với LinkageError khi kích hoạt plugin?** Ghi chẩn đoán, đánh dấu failure, cleanup tài nguyên; không chạy tiếp như plugin hợp lệ.

## 24. Tài liệu tham khảo chính thức

- [Java SE 17 — ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html): lỗi class file malformed hoặc không thể diễn giải hợp lệ.
- [Java SE 17 — VerifyError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html): lỗi xác minh class bytecode.
- [Java SE 17 — ClassCircularityError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCircularityError.html): vòng trong superclass/superinterface hierarchy.
- [Java SE 17 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): lỗi major/minor phiên bản class file.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, class identity/delegation.
- [JVMS 17 — `4 The Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): magic, constant pool, `this_class`, `super_class`, `Code` và `StackMapTable`.
- [JVMS 17 — `5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class/interface creation, circularity checks, linking và verification.
- [JLS 17 — `12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization và yêu cầu về thời điểm lỗi.

**Kết luận:** Khi Java không thể sử dụng một class, cần phân loại đúng: **`ClassFormatError` là class-file structure/format**, **`VerifyError` là bytecode verification**, còn **`ClassCircularityError` là vòng superclass/superinterface hierarchy**. Cả ba đều thuộc **`LinkageError`** nhưng yêu cầu hướng điều tra khác nhau. Dữ liệu điều tra đáng tin nhất là **bytes class file thực sự được JVM nhận, ClassLoader đang định nghĩa, runtime JDK, phương thức/quan hệ type cụ thể và lỗi gốc đầu tiên** — không phải chỉ tên JAR hay chuỗi “class loading failed”.
