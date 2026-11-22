# Phân giải lười và lệnh ldc với hằng số động (Java 11+)

**Chủ đề cha: Hằng số động.** Từ Java 11, JVM hỗ trợ một dạng constant-pool entry mới là `CONSTANT_Dynamic_info`, thường gọi ngắn là **dynamic constant** hoặc **condy** (JEP 309). Thay vì luôn ghi sẵn giá trị trong class file, entry này mô tả **cách tính giá trị qua một bootstrap method**. Khi bytecode thật sự cần giá trị, JVM phân giải tham chiếu và lưu kết quả để những lần sử dụng sau không phải tính lại. Các opcode `ldc`, `ldc_w`, `ldc2_w` là con đường điển hình để đưa giá trị từ run-time constant pool lên operand stack.

Trọng tâm của bài là hiểu chính xác **“lười” (lazy) ở đâu**, **lúc nào bootstrap được gọi**, **kết quả/lỗi được lưu như thế nào**, và tại sao không thể đồng nhất một dynamic constant với lời gọi phương thức bình thường. Tất cả cơ chế cốt lõi được giới thiệu trong Java 11 và vẫn có hiệu lực trên các JVM Java hiện đại.

## 1. Từ literal đến hằng số động

Trong Java thông thường:

```java
String label = "hello";
int number = 42;
Class<?> type = String.class;
```

Đoạn trên chỉ minh họa source; trình biên dịch có thể chọn những bytecode khác nhau tùy giá trị và ngữ cảnh. Ví dụ `String "hello"` thường được nạp từ constant pool bằng `ldc`, còn số nguyên nhỏ có thể dùng `bipush` hoặc `iconst_*`. **Không phải mọi hằng trong source đều trở thành một lệnh `ldc`**.

Với dynamic constant, class file lưu **công thức phân giải**, không lưu sẵn giá trị cuối cùng:

```text
Constant pool của một class (class file version 55+)
        |
        +-- CONSTANT_Dynamic_info
        |       bootstrap_method_attr_index
        |       name_and_type_index
        |
        +-- BootstrapMethods attribute
                |
                +-- bootstrap method handle
                +-- zero or more static bootstrap arguments

Bytecode: ldc #dynamic_constant
              |
              v
        resolve symbolic reference (khi thực sự cần)
              |
              v
        gọi bootstrap method, kiểm tra kiểu kết quả
              |
              v
        ghi nhận kết quả trong run-time constant pool
              |
              v
        đẩy giá trị lên operand stack
```

Điểm mới là giá trị có thể là **kiểu tham chiếu** hoặc một kiểu nguyên thủy được hỗ trợ, không chỉ những dạng literal truyền thống. Ví dụ có thể mô tả một đối tượng bất biến, `Class` mirror cho kiểu nguyên thủy, enum constant, hoặc `VarHandle` thông qua bootstrap phù hợp.

**Đừng nhầm:** `CONSTANT_Dynamic_info` không phải API “biến `final` thành giá trị tính lười” cho toàn bộ mã Java. Nó là **cấu trúc của class file/JVM**. Mã Java bình thường thường không có cú pháp trực tiếp để khai báo “`CONSTANT_Dynamic`”; công cụ sinh bytecode hoặc compiler/framework có thể tạo entry này.

## 2. Hai bộ phận của một dynamic constant

Một entry `CONSTANT_Dynamic_info` có:

1. **`bootstrap_method_attr_index`**: chỉ vào một dòng trong `BootstrapMethods` attribute của class.
2. **`name_and_type_index`**: chỉ một `CONSTANT_NameAndType_info`, chứa *tên* và **field descriptor** của hằng số.

Ví dụ mang tính mô tả:

```text
#27 = Dynamic #0:FEATURE:Ljava/lang/String;

BootstrapMethods:
  0: REF_invokeStatic DemoBootstrap.make
       (Lookup, String, Class)Object
       Method arguments: (none)
```

Đây là **minh họa cấu trúc**, không phải đoạn javap đảm bảo đúng chỉ số. `#27` là **chỉ số constant pool**, còn `#0` sau chữ `Dynamic` là **chỉ số bootstrap method trong attribute**. Hai con số có ý nghĩa khác nhau.

**Field descriptor** của hằng có thể là:

| Descriptor | Kiểu kết quả |
| --- | --- |
| `Ljava/lang/String;` | `java.lang.String` |
| `Ljava/lang/Object;` | `java.lang.Object` |
| `I` | `int` |
| `J` | `long` |
| `D` | `double` |
| `Ljava/lang/invoke/VarHandle;` | `VarHandle` |

Bootstrap phải trả một giá trị tương thích với kiểu được mô tả. Nếu kiểu là primitive thì phải thực hiện chuyển/giải hộp phù hợp; một giá trị không thể chuyển thành kiểu yêu cầu sẽ khiến quá trình phân giải thất bại.

Có thể truyền **static bootstrap arguments** từ constant pool vào bootstrap. Một static argument cũng có thể là **một dynamic constant khác**; nếu vậy, nó cần được phân giải khi bootstrap của hằng bên ngoài được chuẩn bị gọi.

## 3. Vai trò của ldc, ldc_w và ldc2_w

Ba opcode thuộc nhóm “load constant” đều tham chiếu một entry trong **run-time constant pool**, sau đó đẩy giá trị lên operand stack. Chúng **không** dùng để ghi kết quả vào một trường static hay gọi trực tiếp phương thức nghiệp vụ.

| Bytecode | Opcode (hex) | Độ rộng index | Những dạng dynamic constant hợp lệ |
| --- | --- | --- | --- |
| `ldc` | `0x12` | 1 byte, index 0..255 | Giá trị không thuộc dạng `long/double` |
| `ldc_w` | `0x13` | 2 byte, index 0..65535 | Cùng nhóm kiểu với `ldc`; khác độ rộng **index** |
| `ldc2_w` | `0x14` | 2 byte, index 0..65535 | Dynamic constant có descriptor `J` hoặc `D`, và numeric long/double |

**Hai điều dễ nhầm:**

- Chữ `w` trong `ldc_w` nghĩa là **wide constant-pool index**. Nó **không** có nghĩa nạp số 64-bit. Nếu hằng là `long` hoặc `double`, opcode phù hợp là **`ldc2_w`**.
- Dynamic constant descriptor `J` hoặc `D` không hợp lệ với `ldc`/`ldc_w`, ngay cả khi index có thể mã hóa vừa một byte. Kiểu của hằng và độ rộng tham chiếu là hai ràng buộc độc lập.

### Minh họa operand stack

```text
Trước:  ...                (operand stack)
Bytecode: ldc #18           (#18 -> Dynamic name="LABEL", type=String)
Sau:    ..., "ready"

Trước:  ...
Bytecode: ldc_w #300        (#300 -> Dynamic name="MODE", type=Object)
Sau:    ..., someObject

Trước:  ...
Bytecode: ldc2_w #60        (#60 -> Dynamic name="COUNT", type=long)
Sau:    ..., 99L
```

Các giá trị trên là **sơ đồ giả định** để hiểu cơ chế. Chỉ một class file được tạo đúng cấu trúc và bootstrap hợp lệ mới chạy được; không thể chép ba dòng trên vào file `.java` rồi mong `javac` hiểu chúng.

## 4. Phân giải lười: thời điểm nào bootstrap được gọi?

Đặc tả **JVMS Java 11 §5.4 (Linking)** đặt ra giới hạn quan trọng:

> Một symbolic reference đến dynamic constant **không được phân giải** cho đến khi (a) một lệnh `ldc`, `ldc_w` hoặc `ldc2_w` tham chiếu đến nó được **thực thi**, hoặc (b) một bootstrap method được gọi mà cần nó làm **static argument**.

Điều này nghĩa là:

1. **Class đã được load** chưa đủ để bắt buộc bootstrap của dynamic constant chạy.
2. **Class được verify/link/initialize** cũng không đồng nghĩa mọi dynamic constant trong constant pool đều đã tính xong.
3. Một method có `ldc #C` trong bytecode nhưng **chưa từng chạy đến lệnh đó** thì không phải tự động gọi bootstrap cho `C`.
4. Nếu `C` được sử dụng gián tiếp như static argument của một bootstrap khác, nó có thể được phân giải do việc **giải tham số** đó, dù chưa chạy trực tiếp đến `ldc #C`.
5. Sau lần phân giải thành công, các lần sử dụng cùng **symbolic reference** từ run-time constant pool nhận lại kết quả đã lưu.

JVMS cho phép nhiều chiến lược linking ở những loại symbolic references khác. Riêng **dynamic constant**, ranh giới **không phân giải sớm trước nhu cầu** được đặc tả rõ. Vì thế không nên nói chung chung “JVM thích lúc nào thì gọi bootstrap của condy cũng được”.

### Đường thời gian

```text
t0: load class có CONSTANT_Dynamic #C
    -> chưa cần resolve C

t1: gọi method không chạm đến C
    -> vẫn chưa cần resolve C

t2: lần đầu thực thi ldc #C
    -> resolve bootstrap handle, name/type/static args
    -> invoke bootstrap, kiểm tra kết quả, lưu trạng thái

t3: lần sau thực thi ldc_w #C trong cùng class
    -> dùng kết quả đã được phân giải, không gọi lại bootstrap

t4: thực thi ldc #D với CONSTANT_Dynamic khác
    -> có thể phải gọi bootstrap riêng cho D
```

**Phân giải lười** khác **khởi tạo lười của một đối tượng trong code**. Bootstrap có thể tạo một đối tượng, nhưng cache ở đây là **một symbolic reference trong constant pool** (phụ thuộc class và runtime representation), không phải một global singleton áp dụng cho mọi class loader hoặc mọi entry ở các class khác nhau.

## 5. Những kết quả được cache và ranh giới cache

JVM ghi nhận kết quả của việc phân giải một entry:

- **Thành công:** những lần sau tham chiếu cùng entry nhận **cùng thực thể kết quả**; bootstrap không chạy lại để tạo giá trị mới cho chúng.
- **Thất bại:** những lần resolve sau cũng thất bại với **cùng lỗi đã ghi nhận**, không thử lại bootstrap như một cơ chế retry.
- **Hai entry khác nhau:** dù dùng cùng bootstrap method, cùng tên hoặc cùng kiểu mô tả, chúng vẫn có thể mang kết quả/chu kỳ phân giải **khác nhau** nếu là hai symbolic references khác nhau.
- **Hai class loader:** việc định nghĩa các lớp khác nhau tạo ra các run-time constant pools khác nhau; không suy rằng cache của một loader là cache toàn JVM.
- **`ldc` và `ldc_w`:** nếu cả hai cùng trỏ **đúng một constant-pool entry**, chúng chia sẻ trạng thái phân giải của entry ấy.
- **`invokedynamic` khác:** phần cache của dynamically-computed call site được đặc tả theo *instruction site*, không được suy luận y hệt cơ chế của `CONSTANT_Dynamic`. Hai cấu trúc cùng có BootstrapMethods nhưng mục đích và đơn vị liên kết khác.

### Cạnh tranh khi nhiều thread cùng chạm một entry lần đầu

Một ngoại lệ quan trọng với cách nói “bootstrap được gọi đúng một lần”:

JVMS cho phép **nhiều thread cùng bắt đầu phân giải** cùng một symbolic reference khi nó còn unresolved. Trong trường hợp đó, bootstrap method có thể được **gọi đồng thời nhiều lần**. JVM chọn kết quả của **một lần gọi** và công bố nhất quán cho các thread; kết quả các lời gọi khác bị bỏ qua.

Do đó:

- Không viết bootstrap làm **side effect không thể lặp**, như trừ tiền, gửi email, tạo transaction không idempotent.
- Nếu bootstrap dùng state toàn cục, cần **thread-safety** hoặc cơ chế riêng để chống race.
- **Sau khi một kết quả/lỗi đã được chọn và cài đặt**, các lần resolution sau không thực thi bootstrap lại.
- Các test tuần tự có thể thấy “calls = 1” cho một entry; **không biến kỳ vọng này thành hợp đồng chính xác trong trường hợp concurrent first-use**.

**Tóm tắt:** Cache là một bảo đảm quan trọng; *exactly-once side effect* của bootstrap thì **không**.

## 6. Bootstrap method nhận gì?

Đối với dynamic constant không có static bootstrap arguments, mô hình thông dụng là:

```java
public static Object bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type) {
    // Tính/tra cứu hằng được yêu cầu.
    return ...;
}
```

Đây là **mã minh họa** (dấu `...` chỉ thay bằng biểu thức trả kết quả thực trong ứng dụng). Ba tham số bắt buộc về ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| `lookup` | Ngữ cảnh class đang tham chiếu dynamic constant, dùng để kiểm soát truy cập |
| `name` | Tên không định danh đầy đủ của dynamic constant, lấy từ NameAndType |
| `type` | Đối tượng `Class<?>` của kiểu kết quả mà descriptor yêu cầu |

Các static bootstrap arguments khác (nếu có) được truyền **sau ba đối số** này và được phân giải theo thứ tự do constant pool/BootstrapMethods mô tả.

**Kiểu trả về có thể là `Object`**, miễn giá trị thực có thể được chuyển thành kiểu trong descriptor. Ví dụ kiểu kết quả `String` cần một `String` (hoặc `null`); kiểu `long` cần đối tượng/mô hình chuyển đổi hợp lệ về primitive `long`.

JVM thực hiện phân giải bootstrap handle trước khi gọi. Những lỗi về tên lớp, quyền truy cập, method type, static args và vòng tham chiếu có thể khiến việc liên kết thất bại **trước khi thân bootstrap chạy**.

## 7. Ví dụ Java 11 đơn giản: ldc thông thường chưa phải condy

Tệp **`PlainLdcDemo.java`**:

```java
public class PlainLdcDemo {
    public static void main(String[] args) {
        String message = "hello-ldc";
        long count = 1234567890123L;
        System.out.println(message);
        System.out.println(count);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PlainLdcDemo.java
java PlainLdcDemo
javap -c -p PlainLdcDemo
```

Stdout khi chạy `java PlainLdcDemo`:

```text
hello-ldc
1234567890123
```

Trong kết quả `javap -c`, bạn sẽ thấy bytecode tương tự:

```text
ldc    #...    // String hello-ldc
ldc2_w #...    // long 1234567890123l
```

Ví dụ này chỉ minh họa **cách nạp từ constant pool**. `String` literal và `long` numeric constant ở đây là **hằng thông thường**, **không phải** `CONSTANT_Dynamic_info`. Chạy `javap -v` sẽ phân biệt tag `String`/`Long` với tag `Dynamic`.

**Lưu ý biên dịch:** Nếu đổi `long` thành `0L` hoặc `1L`, javac có thể chọn `lconst_0`/`lconst_1` thay vì `ldc2_w`. Đừng viết test phụ thuộc opcode nếu đầu vào chưa cố định.

## 8. Ví dụ thật: tạo class file Java 11 chứa CONSTANT_Dynamic

**Vì Java 11 không cung cấp cú pháp source để viết condy trực tiếp**, phần này tạo một class file tối thiểu bằng những API chuẩn của Java SE: `ByteArrayOutputStream` và `DataOutputStream`. Không sử dụng ASM nội bộ, không cần dependency Maven, không cần cờ `--add-exports`.

Generator viết class **`GeneratedCondy`** (class-file version **55**, Java 11) với các phương thức:

| Method của GeneratedCondy | Instruction | Constant pool | Kỳ vọng |
| --- | --- | --- | --- |
| `first()` | `ldc` | Dynamic `FIRST:String` | Lần đầu kích hoạt bootstrap |
| `again()` | `ldc_w` | **Cùng entry FIRST** | Dùng kết quả đã cache |
| `second()` | `ldc_w` | Dynamic `SECOND:String` khác | Bootstrap chạy cho entry mới |
| `number()` | `ldc2_w` | Dynamic `LONG:long` | Tạo giá trị long 99 |
| `broken()` | `ldc_w` | Dynamic `BROKEN:String` | Bootstrap ném exception; lỗi được ghi nhận |

Tất cả dynamic constants dùng **một bootstrap method** nằm trong chương trình test. Ví dụ là *bytecode fixture* phục vụ học JVM, **không** phải template để tự ghi classfile ở môi trường production.

### Tệp hoàn chỉnh `CondyLazyDemo.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class CondyLazyDemo {
    private static int calls;

    // Bootstrap method cho các CONSTANT_Dynamic của GeneratedCondy.
    public static Object bootstrap(
            MethodHandles.Lookup caller, String name, Class<?> type) {
        int n = ++calls;
        if ("BROKEN".equals(name)) {
            throw new IllegalArgumentException("demo bootstrap failure");
        }
        if ("LONG".equals(name)) {
            return Long.valueOf(99L);
        }
        return name + "#" + n;
    }

    static final class Pool {
        final List<byte[]> entries = new ArrayList<>();

        int add(byte[] bytes) {
            entries.add(bytes);
            return entries.size(); // Constant pool index bắt đầu từ 1.
        }

        int utf(String value) throws IOException {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeByte(1);            // CONSTANT_Utf8
            out.writeUTF(value);         // Modified UTF-8 của class file
            return add(bytes.toByteArray());
        }

        int twoShorts(int tag, int first, int second)
                throws IOException {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeByte(tag);
            out.writeShort(first);
            out.writeShort(second);
            return add(bytes.toByteArray());
        }

        int clazz(String internalName) throws IOException {
            return oneShort(7, utf(internalName)); // CONSTANT_Class
        }

        int oneShort(int tag, int index) throws IOException {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeByte(tag);
            out.writeShort(index);
            return add(bytes.toByteArray());
        }

        int nameType(String name, String descriptor)
                throws IOException {
            return twoShorts(12, utf(name), utf(descriptor));
        }

        int methodRef(int owner, int nameType) throws IOException {
            return twoShorts(10, owner, nameType);
        }

        int methodHandle(int methodRef) throws IOException {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeByte(15);           // CONSTANT_MethodHandle
            out.writeByte(6);            // REF_invokeStatic
            out.writeShort(methodRef);
            return add(bytes.toByteArray());
        }

        int dynamic(int bootstrapIndex, int nameType)
                throws IOException {
            return twoShorts(17, bootstrapIndex, nameType);
        }

        void writeTo(DataOutputStream out) throws IOException {
            out.writeShort(entries.size() + 1);
            for (byte[] entry : entries) {
                out.write(entry);
            }
        }
    }

    static void method(DataOutputStream out, int flags,
                       int name, int desc, int codeName,
                       int maxStack, int maxLocals, byte[] code)
            throws IOException {
        out.writeShort(flags);
        out.writeShort(name);
        out.writeShort(desc);
        out.writeShort(1);            // attributes_count = Code
        out.writeShort(codeName);
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(maxLocals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0);            // exception_table_length
        out.writeShort(0);            // Code.attributes_count
    }

    static byte[] generate() throws IOException {
        Pool pool = new Pool();

        int self = pool.clazz("GeneratedCondy");
        int object = pool.clazz("java/lang/Object");
        int code = pool.utf("Code");
        int bootstrapAttribute = pool.utf("BootstrapMethods");

        int initName = pool.utf("<init>");
        int voidDesc = pool.utf("()V");
        int objectInit = pool.methodRef(object,
                pool.nameType("<init>", "()V"));

        int support = pool.clazz("CondyLazyDemo");
        int supportMethod = pool.methodRef(support, pool.nameType(
                "bootstrap",
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;)"
                + "Ljava/lang/Object;"));
        int handle = pool.methodHandle(supportMethod);

        // BootstrapMethods index là 0, khác với CP index.
        int first = pool.dynamic(0,
                pool.nameType("FIRST", "Ljava/lang/String;"));
        int second = pool.dynamic(0,
                pool.nameType("SECOND", "Ljava/lang/String;"));
        int number = pool.dynamic(0, pool.nameType("LONG", "J"));
        int broken = pool.dynamic(0,
                pool.nameType("BROKEN", "Ljava/lang/String;"));

        int firstName = pool.utf("first");
        int againName = pool.utf("again");
        int secondName = pool.utf("second");
        int numberName = pool.utf("number");
        int brokenName = pool.utf("broken");
        int stringDesc = pool.utf("()Ljava/lang/String;");
        int longDesc = pool.utf("()J");

        if (first > 255) {
            throw new IOException("ldc index must fit one byte");
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);            // minor_version
        out.writeShort(55);           // major_version: Java 11
        pool.writeTo(out);

        out.writeShort(0x0021);       // ACC_PUBLIC | ACC_SUPER
        out.writeShort(self);
        out.writeShort(object);
        out.writeShort(0);            // interfaces_count
        out.writeShort(0);            // fields_count
        out.writeShort(6);            // methods_count

        // public GeneratedCondy() { super(); }
        method(out, 0x0001, initName, voidDesc, code, 1, 1,
                new byte[] {
                        0x2a, (byte) 0xb7,
                        (byte) (objectInit >>> 8),
                        (byte) objectInit,
                        (byte) 0xb1
                });

        // first(): ldc #FIRST; areturn
        method(out, 0x0009, firstName, stringDesc, code, 1, 0,
                new byte[] {
                        0x12, (byte) first, (byte) 0xb0
                });

        // again(): ldc_w #FIRST; areturn (cùng CP entry)
        method(out, 0x0009, againName, stringDesc, code, 1, 0,
                new byte[] {
                        0x13, (byte) (first >>> 8),
                        (byte) first, (byte) 0xb0
                });

        // second(): ldc_w #SECOND; areturn
        method(out, 0x0009, secondName, stringDesc, code, 1, 0,
                new byte[] {
                        0x13, (byte) (second >>> 8),
                        (byte) second, (byte) 0xb0
                });

        // number(): ldc2_w #LONG; lreturn
        method(out, 0x0009, numberName, longDesc, code, 2, 0,
                new byte[] {
                        0x14, (byte) (number >>> 8),
                        (byte) number, (byte) 0xad
                });

        // broken(): ldc_w #BROKEN; areturn
        method(out, 0x0009, brokenName, stringDesc, code, 1, 0,
                new byte[] {
                        0x13, (byte) (broken >>> 8),
                        (byte) broken, (byte) 0xb0
                });

        // Một bootstrap entry, không có static bootstrap args.
        out.writeShort(1);            // class.attributes_count
        out.writeShort(bootstrapAttribute);
        out.writeInt(6);              // attribute_length
        out.writeShort(1);            // num_bootstrap_methods
        out.writeShort(handle);       // bootstrap_method_ref
        out.writeShort(0);            // num_bootstrap_arguments

        out.flush();
        return bytes.toByteArray();
    }

    static final class Loader extends ClassLoader {
        Loader() {
            super(CondyLazyDemo.class.getClassLoader());
        }

        Class<?> define(byte[] classFile) {
            return defineClass(
                    "GeneratedCondy", classFile, 0, classFile.length);
        }
    }

    static Object call(Class<?> type, String method) throws Exception {
        return type.getMethod(method).invoke(null);
    }

    static String brokenCall(Class<?> type) throws Exception {
        try {
            call(type, "broken");
            return "UNEXPECTED_SUCCESS";
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            return cause.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] classFile = generate();
        Files.write(Path.of("GeneratedCondy.class"), classFile);

        // Định nghĩa class bằng loader riêng, không gọi method ldc nào.
        Class<?> generated = new Loader().define(classFile);
        System.out.println("after define: " + calls);

        System.out.println("first: " + call(generated, "first"));
        System.out.println("after first: " + calls);

        System.out.println("again: " + call(generated, "again"));
        System.out.println("after again: " + calls);

        System.out.println("second: " + call(generated, "second"));
        System.out.println("after second: " + calls);

        System.out.println("long: " + call(generated, "number"));
        System.out.println("after long: " + calls);

        System.out.println("broken 1: " + brokenCall(generated));
        System.out.println("after broken 1: " + calls);

        System.out.println("broken 2: " + brokenCall(generated));
        System.out.println("after broken 2: " + calls);
    }
}
```

Biên dịch/chạy bằng JDK 11+:

```bash
javac --release 11 -encoding UTF-8 CondyLazyDemo.java
java CondyLazyDemo
javap -v -c -p GeneratedCondy
```

**Stdout của lệnh `java CondyLazyDemo`** trong một lần chạy tuần tự với JVM tuân theo JVMS:

```text
after define: 0
first: FIRST#1
after first: 1
again: FIRST#1
after again: 1
second: SECOND#2
after second: 2
long: 99
after long: 3
broken 1: BootstrapMethodError
after broken 1: 4
broken 2: BootstrapMethodError
after broken 2: 4
```

Lệnh `javap` tiếp theo in bytecode và constant pool; **nó không nằm trong stdout cố định ở trên**, do output `javap -v` rất dài.

### Đọc ví dụ theo từng mốc

- **Sau define: 0:** class file đã được tạo/định nghĩa, nhưng chưa chạy lệnh nào nạp dynamic constant.
- **first: FIRST#1:** `ldc #FIRST` yêu cầu giá trị; JVM gọi `CondyLazyDemo.bootstrap`, tăng `calls` từ 0 thành 1 và trả một String.
- **again: FIRST#1:** `ldc_w` tham chiếu **chính entry FIRST**, nên không chạy bootstrap lần nữa. Khác opcode nhưng **cùng constant-pool index**.
- **second: SECOND#2:** entry SECOND độc lập, được giải riêng. Dù cùng bootstrap method handle, nó có tên khác và một giá trị được cache riêng.
- **long: 99:** entry LONG có descriptor `J`; dùng `ldc2_w` và `lreturn`. Bootstrap trả một `Long` hợp lệ để JVM lấy giá trị primitive.
- **broken lần 1:** bootstrap ném `IllegalArgumentException`; vì đây là exception không phải `Error`, JVM báo `BootstrapMethodError` trong quá trình resolution.
- **broken lần 2:** không gọi lại bootstrap; lỗi đã chọn được ghi nhận cho cùng entry. `calls` vẫn là 4.
- **Thứ tự được kiểm soát:** chương trình chỉ dùng **một thread** thực hiện các lệnh nạp, nên ở đây số lượt bootstrap chính xác và dễ quan sát. Đừng suy rộng ra yêu cầu exactly-once dưới concurrency.

**Vì sao dùng class loader riêng?** Ta tạo bytecode và `defineClass` trực tiếp, không cần tham chiếu `GeneratedCondy` trong source. File `GeneratedCondy.class` được ghi ra để `javap` có thể đọc. Khi chạy `java CondyLazyDemo` ở thư mục có quyền ghi, bạn sẽ thấy file được tạo; vì vậy hãy chạy trong **thư mục test** và không ghi đè file cùng tên của dự án khác.

### Xem đúng những gì javap sẽ cho biết

Trong `javap -v -c -p GeneratedCondy`, tìm:

```text
major version: 55
...
Dynamic    #0:FIRST:Ljava/lang/String;
Dynamic    #0:SECOND:Ljava/lang/String;
Dynamic    #0:LONG:J
Dynamic    #0:BROKEN:Ljava/lang/String;
...
public static java.lang.String first();
    ldc ...
...
public static java.lang.String again();
    ldc_w ...
...
public static long number();
    ldc2_w ...
...
BootstrapMethods:
    ... CondyLazyDemo.bootstrap ...
```

Đây là **trích lược định dạng**, không phải toàn bộ output cố định với các chỉ số `#N`. Hãy kiểm tra nội dung metadata quan trọng: tag Dynamic, bootstrap index, descriptor, opcode và class-file version. `javap` chỉ **đọc bytecode**, không phải trình thực thi bootstrap của chương trình.

## 9. Vì sao ví dụ sinh class file bằng tay thay vì javac tự tạo condy?

Người học dễ tạo một class Java có:

```java
static final String VALUE = expensive();
```

rồi nghĩ `VALUE` là dynamic constant. Thực tế, biểu thức trên thường được thực hiện trong quá trình **class initialization** (`<clinit>`) và lưu vào static field. Nó **không** phải một entry `CONSTANT_Dynamic_info` chỉ vì có tính toán.

So sánh:

| Đặc điểm | Static field initialized by code | Dynamic constant / condy |
| --- | --- | --- |
| Nơi giá trị sống | Trường static của class | Giá trị symbolic reference đã phân giải trong run-time constant pool |
| Mốc tính | Khi khởi tạo class nếu đường code chạy | Khi entry được lệnh `ldc*` hoặc bootstrap argument yêu cầu |
| Cách biểu diễn | `putstatic` / `getstatic` và bytecode khởi tạo | `CONSTANT_Dynamic_info` và `BootstrapMethods` |
| Cache | Field của class | Resolution state của constant-pool entry |
| Trường hợp lỗi | ExceptionInInitializerError có thể liên quan `<clinit>` | BootstrapMethodError và linking/resolution errors theo JVMS |
| Cách xem | `javap -c -v` thấy `<clinit>`/fields | `javap -c -v` thấy `Dynamic`/`BootstrapMethods` |

**Cũng không đồng nhất `condy` với `invokedynamic`:** `invokedynamic` tính ra **CallSite** để xác định đích gọi, còn `CONSTANT_Dynamic` tính ra **giá trị hằng** nạp vào stack. Chúng dùng chung cơ chế bootstrap ở mức JVM nhưng phục vụ mục đích khác.

Các API mô tả hằng như `java.lang.constant.DynamicConstantDesc` và `ConstantDesc` được bổ sung từ **Java 12**, **không có trong API Java 11**. Chúng có thể dùng khi viết công cụ bytecode trên JDK mới, nhưng phần cốt lõi của condy là **classfile feature Java 11**. Không đưa `import java.lang.constant.DynamicConstantDesc` vào chương trình biên dịch với `javac --release 11`.

## 10. Failure path: exception, type mismatch và retry

Phân giải hằng động có ba giai đoạn khái niệm:

1. **Chuẩn bị:** phân giải bootstrap handle, xác định tên và kiểu kết quả, phân giải các static args.
2. **Gọi bootstrap:** đưa `Lookup`, `String name`, `Class<?> type` và các args bổ sung cho method handle.
3. **Kiểm tra kết quả:** chuyển kết quả về kiểu được mô tả bởi field descriptor và ghi nhận thành công/lỗi.

| Tình huống | Hệ quả |
| --- | --- |
| Bootstrap trả một `String` cho descriptor String | Phân giải thành công |
| Bootstrap trả `Long.valueOf(99)` cho descriptor `J` | Chuyển hợp lệ sang `long`, thành công |
| Bootstrap trả sai kiểu, không thể cast/unbox | `BootstrapMethodError` |
| Bootstrap trả `null` khi descriptor là reference | Có thể là hằng `null` hợp lệ |
| Bootstrap trả `null` cho primitive | `BootstrapMethodError` vì không thể unbox |
| Bootstrap tự ném checked/unchecked exception không thuộc `Error` | JVM bọc thành `BootstrapMethodError`, lưu thất bại |
| Bootstrap tự ném `Error` | Resolution thất bại với `Error` tương ứng |
| Một static bootstrap arg phụ thuộc chu trình vào chính dynamic constant | Lỗi resolution, theo JVMS có thể là `StackOverflowError` |
| Cùng entry được dùng sau khi thất bại | Phát lại **lỗi đã ghi nhận**, không tự retry bootstrap |
| Entry khác dù dùng chung bootstrap | Có resolution state riêng |

**Không sử dụng BootstrapMethodError làm lỗi nghiệp vụ có thể retry vô hạn.** Nếu bootstrap phụ thuộc hệ thống bên ngoài không ổn định, lần lỗi đầu có thể **poison** entry đối với vòng đời đó. Cơ chế condy phù hợp hơn với giá trị có thể tính **ổn định** từ metadata và trạng thái runtime thích hợp, không phải truy vấn API có thể mất mạng tại mỗi lần sử dụng.

### Null và primitive

`ConstantBootstraps.nullConstant(...)` có từ Java 11 để biểu diễn một reference constant có giá trị `null`. Trường hợp này **khác** bootstrap trả null cho descriptor primitive, vì primitive không chấp nhận null.

Vì `ldc` có thể đẩy `null` lên stack khi đó là kết quả condy tham chiếu, đừng suy ra mọi `ldc` luôn trả reference khác null.

## 11. ConstantBootstraps trong JDK 11

Java 11 cung cấp lớp `java.lang.invoke.ConstantBootstraps` với những bootstrap có sẵn:

| Phương thức | Công dụng |
| --- | --- |
| `nullConstant(Lookup,String,Class<?>)` | Hằng reference `null` |
| `primitiveClass(Lookup,String,Class<?>)` | Lấy `Class` mirror của primitive theo descriptor |
| `enumConstant(Lookup,String,Class<E>)` | Lấy một enum constant theo tên |
| `getStaticFinal(...)` | Đọc một static final field hợp lệ |
| `invoke(...)` | Gọi một MethodHandle để tính kết quả |
| `fieldVarHandle(...)` | Tìm VarHandle cho instance field |
| `staticFieldVarHandle(...)` | Tìm VarHandle cho static field |
| `arrayVarHandle(...)` | Tìm VarHandle cho array element |

Các phương thức này **có thể được gọi trực tiếp** từ Java, nhưng gọi trực tiếp chỉ là **method invocation thông thường**. Chúng thực sự hoạt động như *bootstrap of a dynamic constant* khi được tham chiếu qua class-file metadata và khi JVM thực hiện resolution.

### Demo riêng: gọi API mà không giả vờ tạo condy

Tệp **`ConstantBootstrapsApiDemo.java`**:

```java
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;

public class ConstantBootstrapsApiDemo {
    enum Mode { FAST, SAFE }

    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Class<?> intType =
                ConstantBootstraps.primitiveClass(
                        lookup, "I", Class.class);

        Mode mode = ConstantBootstraps.enumConstant(
                lookup, "FAST", Mode.class);

        Object absent = ConstantBootstraps.nullConstant(
                lookup, "NOT_USED", String.class);

        System.out.println("primitive: " + (intType == int.class));
        System.out.println("enum: " + (mode == Mode.FAST));
        System.out.println("null: " + (absent == null));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ConstantBootstrapsApiDemo.java
java ConstantBootstrapsApiDemo
```

```text
primitive: true
enum: true
null: true
```

Đây là demo về **phương thức bootstrap có sẵn**, **không** phải ví dụ kích hoạt `ldc #Dynamic`. Bài `CondyLazyDemo` mới tạo classfile với dynamic constant thật. Phân biệt hai loại demo để không rút ra kết luận sai về cache/lazy chỉ từ việc gọi trực tiếp phương thức Java.

## 12. Tách rõ các cấp “lười”: class loading, init, bootstrap và JIT

| Tầng | Việc xảy ra | Tại sao không phải cùng một hành vi? |
| --- | --- | --- |
| **Class loading** | Đọc/định nghĩa class file và constant pool | Chưa bắt buộc tính mọi dynamic constant |
| **Verification/preparation** | Xác minh format, chuẩn bị fields | Không tương đương gọi bootstrap của condy chưa dùng |
| **Class initialization** | Chạy `<clinit>`, gán static fields | Có thể thực hiện logic bất kỳ, nhưng là cơ chế khác |
| **Dynamic constant resolution** | Tính và cache giá trị một CP symbolic reference | Kích hoạt khi lệnh ldc* hoặc bootstrap arg yêu cầu |
| **JIT optimization** | Có thể tối ưu execution sau khi semantics được xác lập | Không được phá ranh giới quan sát của JVM resolution |
| **Application lazy field** | Code tự trì hoãn tạo object qua supplier/holder | Không tạo `CONSTANT_Dynamic_info` nếu không sinh bytecode |

**Không phải mọi thứ chứa chữ “constant” đều bất biến sâu.** Một bootstrap có thể trả một **đối tượng mutable**; JVM cache reference, nhưng nội dung bên trong object có thể thay đổi do code của ứng dụng. Do đó “hằng” ở đây là **kết quả phân giải của entry**, không phải bảo đảm đối tượng luôn bất biến hay thread-safe.

Nếu bootstrap tạo cấu trúc dữ liệu chia sẻ, nên dùng đối tượng immutable hoặc có chính sách đồng bộ rõ ràng. Tránh dùng condy để che dấu side effects nguy hiểm chỉ vì giá trị có vẻ được tính một lần.

## 13. Static bootstrap arguments cũng có thể dùng condy

Một `BootstrapMethods` entry có thể khai báo danh sách static args. Ví dụ khái niệm:

```text
#18 = Dynamic #0:BASE:Ljava/lang/String;
#23 = Dynamic #1:DERIVED:Ljava/lang/String;

BootstrapMethods:
  0 -> bootstrapBase()
  1 -> bootstrapDerived(staticArg = #18)
```

Nếu JVM cần `#23` trước `#18`:

1. JVM bắt đầu resolution của `#23`.
2. Để gọi bootstrapDerived, nó phải **resolve staticArg #18**.
3. Việc phân giải `#18` có thể gọi bootstrapBase **ngay lúc này**.
4. Khi #18 có giá trị, bootstrapDerived nhận giá trị đó để tính #23.
5. Sau đó, một `ldc #18` độc lập dùng kết quả đã cache của #18.

Đây là sơ đồ diễn giải, không phải lệnh Java/asm có thể chạy. Nó giải thích vì sao cách diễn đạt “condy chỉ lười tới `ldc` trực tiếp của chính nó” là **thiếu**: bootstrap argument cũng là đường kích hoạt được đặc tả.

**Chống vòng lặp:** Nếu `#18` lại phụ thuộc `#23` qua static args, JVM không thể tạo một kết quả hợp lệ bằng cách resolve vòng mãi. JVMS yêu cầu phát hiện/sinh `StackOverflowError` ở trường hợp tự phụ thuộc, không trả một giá trị giả định hoặc loop vô hạn như một hành vi bình thường.

## 14. Caching trong hai class loader

Giả sử:

```text
Loader A -> GeneratedCondy.class -> runtime constant pool A -> #FIRST
Loader B -> GeneratedCondy.class -> runtime constant pool B -> #FIRST
```

Hai lần định nghĩa class bằng hai loaders khác nhau tạo **hai class objects riêng**, với các vùng trạng thái resolution tương ứng. Vì vậy, mỗi bên có thể gọi bootstrap riêng cho entry `#FIRST` khi lần đầu cần.

Điều này liên quan tới:

- Test chạy cùng một đoạn bytecode nhưng định nghĩa qua loader khác.
- Framework dùng plugin/reloadable classloader.
- Ứng dụng dạng container chạy nhiều modules/tenants với loader riêng.
- Công cụ bytecode so sánh hai bản class dù tên binary giống nhau.

**Không dùng `static int counter` chung của lớp bootstrap như cách chứng minh cache toàn VM**: counter đó chỉ là biến quan sát thuộc lớp bootstrap. Cache condy vẫn là trạng thái resolution theo entry của class được định nghĩa, không nhất thiết có cùng vòng đời với counter.

Khi chạy bài demo với generated class mới từ loader khác, bootstrap có thể lại chạy cho entry FIRST ở class mới, kể cả khi lớp bootstrap gốc vẫn tồn tại và counter của nó chưa reset.

## 15. Kiểm thử độ đúng: nên kiểm tra gì?

| Kịch bản | Kỳ vọng |
| --- | --- |
| Định nghĩa class nhưng chưa thực thi `ldc #C` | Bootstrap cho #C chưa bị kích hoạt vì direct ldc |
| Lần đầu chạy `ldc #C` | Resolution tạo giá trị hoặc báo lỗi |
| Lần tiếp theo chạy `ldc_w #C` | Dùng cùng kết quả/lỗi của entry #C |
| Chạm entry #D khác | Phân giải #D riêng khi cần |
| `ldc2_w` với descriptor J/D | Đẩy giá trị long/double hợp lệ |
| BSM ném exception không thuộc Error | Nhận BootstrapMethodError |
| Cùng entry thất bại được gọi lần nữa | Không chạy lại bootstrap như retry |
| Bootstrap trả kết quả sai kiểu | Resolution thất bại |
| BSM trả null cho reference | Có thể thành công với giá trị null |
| BSM trả null cho primitive | Resolution thất bại |
| Static argument là condy #A | #A được resolve trước khi truyền vào bootstrap ngoài |
| Hai luồng chạm cùng unresolved entry | Có thể có **nhiều** BSM invocations đồng thời; một kết quả được chọn |
| Hai class loaders định nghĩa cùng bytes | Mỗi class có resolution state riêng |

Bài `CondyLazyDemo` kiểm tra đa số trường hợp cơ bản **theo thứ tự một luồng**, dùng classfile thực tế. Đối với concurrency, **không** đặt assertion “bootstrap được gọi đúng 1 lần” trong test nhiều luồng: JVMS cho phép hơn một invocation trong tranh chấp.

### Bộ assertion tự chạy để phát hiện regression

Có thể bổ sung các kiểm tra vào `main` của `CondyLazyDemo` sau mỗi mốc (đây là **đoạn minh họa**, không phải tệp độc lập):

```java
if (calls != 0) {
    throw new AssertionError("Condy resolved before use");
}

String firstValue = (String) call(generated, "first");
if (!"FIRST#1".equals(firstValue) || calls != 1) {
    throw new AssertionError("First lazy resolution failed");
}

String againValue = (String) call(generated, "again");
if (firstValue != againValue || calls != 1) {
    throw new AssertionError("Cached constant not reused");
}
```

Ở đây `firstValue != againValue` so sánh **cùng object reference**, bởi vì hai lệnh nạp cùng entry đã có kết quả resolution. Nếu chọn các entry khác nhau nhưng bootstrap trả hai String cùng nội dung, không được yêu cầu reference identity giữa hai entry.

**Lưu ý vị trí:** Khi chèn test, đặt chúng **ngay sau bước định nghĩa class và trước phần main in output** hoặc tự tạo một chương trình test riêng; không chèn sau khi main đã chạy hết mà kiểm tra `calls == 0`. Ví dụ có tính chất minh họa quy tắc hơn là yêu cầu copy nguyên block vào cuối file.

## 16. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| “Lúc load class là bootstrap của mọi condy chạy” | Hiểu sai lazy resolution | Chỉ khi ldc* hoặc static argument cần |
| “Một bootstrap method chỉ gọi đúng một lần toàn VM” | Sai về nhiều entry, loader, thread | Cache theo symbolic reference; concurrency có thể gọi nhiều lần |
| “`ldc_w` nạp long/double” | Nhầm kích thước index với kiểu value | long/double dùng `ldc2_w` |
| “Cứ có `static final` là `CONSTANT_Dynamic`” | Nhầm class init với constant-pool resolution | Kiểm tra `javap -v` |
| “Condy chính là invokedynamic” | Sai về kết quả và đơn vị liên kết | Condy tính value; invokedynamic tính CallSite |
| “Bootstrap hỏng sẽ được JVM thử lại lần sau” | Lỗi bị cache, retry vô ích | Sửa class/runtime, không dựa vào retry |
| “Có cache thì BSM có side effects exactly-once” | Race có thể tạo side effects lặp | BSM cần thread-safe, side-effect-safe |
| “Dynamic constant phải trả object bất biến” | Runtime chỉ cache value/reference | Tự thiết kế object immutable nếu cần |
| “Condy primitive có thể trả null” | Không thể unbox null | Trả đúng wrapper/giá trị tương thích |
| “Dùng DynamicConstantDesc trên Java 11” | API này là Java 12+ | Java 11 dùng classfile/bytecode hoặc API phù hợp |
| “Bấm javap là đã kích hoạt bootstrap” | javap đọc classfile chứ không chạy mã | Thực thi class mới phân giải |
| “Có thể dùng ASM nội bộ không giới hạn trên mọi JDK” | Không ổn định và đụng encapsulation modules | Dùng API/thư viện classfile chính thức và tương thích |
| “Cache condy là global theo tên hằng” | Hai classes/loaders có pools khác | Ranh giới theo class và symbolic reference |

## 17. Hướng áp dụng vào code thật

Với phần lớn ứng dụng backend Java, bạn **không cần tự tạo CONSTANT_Dynamic** bằng tay. Nên:

1. **Để compiler/toolchain tạo bytecode hợp lệ** nếu đang xây framework hay runtime.
2. Với công cụ xử lý classfile, nhận diện `CONSTANT_Dynamic_info` (tag 17) và thuộc tính `BootstrapMethods` khi phân tích/transform; không làm mất metadata.
3. Nếu viết bootstrap riêng, dùng signature tương thích với `Lookup,String,Class<?>` và static args bổ sung, kiểm tra kết quả theo descriptor.
4. Tránh side effect, I/O mạng hoặc trạng thái không xác định khi bootstrap chạy; cache cả lỗi khiến tính ổn định rất quan trọng.
5. Xử lý cạnh tranh đồng thời khi class được nhiều threads dùng lần đầu.
6. Không giả định `javac` sẽ tự phát condy cho một biểu thức `final`, lambda hoặc static initializer trong source của bạn.
7. Kiểm tra classfile version: `CONSTANT_Dynamic_info` cần **Java 11 / major 55+**. Runtime cũ hơn không tải được classfile Java 11.
8. Dùng `javap -v -c -p` trên artifact đã build nếu cần chẩn đoán opcode và bootstrap metadata, thay vì dự đoán từ source.
9. Khi nâng cấp JDK, kiểm tra tương thích của bytecode tooling, classloader và bootstrap, không dựa vào các package nội bộ của JDK.
10. Nếu mục tiêu chỉ là lazy initialization của một object trong ứng dụng, sử dụng patterns ở Java source phù hợp (holder, supplier, lazy field) thay vì tự viết bytecode condy.

Từ Java 12 trở đi, họ `java.lang.constant` giúp biểu diễn các **nominal descriptors** của constants để công cụ bytecode thao tác thuận tiện hơn. Một lời gọi `DynamicConstantDesc.resolveConstantDesc(...)` mô phỏng phân giải qua reflection và theo tài liệu **không cache kết quả như JVM runtime constant pool**. Vì vậy trên JDK mới, cũng đừng đồng nhất “resolve descriptor bằng API” với “chạy `ldc` trên một entry được JVM quản lý”.

## 18. Tự kiểm tra

**Câu 1.** Có một classfile chứa `CONSTANT_Dynamic #C` trong constant pool nhưng code chưa chạy đến `ldc #C` và không có bootstrap nào cần nó làm argument. Có bắt buộc BSM đã chạy không?

**Câu 2.** `ldc #C` và `ldc_w #C` trong cùng class có dùng chung cached value không?

**Câu 3.** Một dynamic constant descriptor là `J` (long). Dùng `ldc_w` có hợp lệ nếu index nhỏ không?

**Câu 4.** Nếu bootstrap thất bại lần đầu với `IllegalArgumentException`, lần sau JVM có tự chạy lại bootstrap không?

**Câu 5.** Bootstrap là phương thức chung cho hai entries #C và #D. Có được suy ra chúng là một constant duy nhất không?

**Câu 6.** Nếu hai threads tranh chấp phân giải #C cùng lúc, side effect của bootstrap có bảo đảm đúng một lần không?

**Câu 7.** Viết `static final String X = factory();` trong Java 11 có nghĩa javac chắc chắn sinh `CONSTANT_Dynamic` không?

**Câu 8.** `DynamicConstantDesc` là API có sẵn từ Java 11 hay Java 12?

**Câu 9.** Một dynamic constant có thể được phân giải trước `ldc` trực tiếp của nó nếu nó là static argument của bootstrap khác không?

**Câu 10.** Condy cache reference đến một object mutable thì object đó có tự trở thành bất biến không?

**Đáp án:**

1. **Không.** JVMS yêu cầu chưa resolve trước khi có nhu cầu trực tiếp/gián tiếp như mô tả.
2. **Có**, nếu trỏ cùng symbolic reference/constant-pool entry.
3. **Không.** Descriptor `J` dùng `ldc2_w`.
4. **Không.** Lỗi phân giải được ghi nhận; exception không thuộc `Error` thường bị bọc vào `BootstrapMethodError`.
5. **Không.** Cache gắn với entry/reference; hai entries có thể khác giá trị và thời điểm phân giải.
6. **Không.** Nhiều bootstrap invocations có thể diễn ra đồng thời; JVM chọn một kết quả.
7. **Không.** Thông thường đó là quá trình khởi tạo static field qua `<clinit>`.
8. **Java 12**; condy classfile có từ Java 11.
9. **Có.** Việc phân giải static bootstrap arguments là một nguồn yêu cầu hợp lệ.
10. **Không.** Giá trị tham chiếu được cache, nhưng trạng thái bên trong object mutable không được “đóng băng” bởi JVM.

## 19. Kết luận

- **`CONSTANT_Dynamic_info` (tag 17, Java 11)** mô tả cách tính một giá trị constant bằng bootstrap method.
- **`ldc`/`ldc_w`** dùng cho các giá trị phù hợp không phải long/double; **`ldc2_w`** dùng cho long/double.
- **Lazy resolution là yêu cầu đặc tả:** dynamic constant chưa được phân giải trước khi một `ldc*` thực thi hoặc một bootstrap cần nó làm static argument.
- Kết quả **hoặc lỗi** được ghi nhận theo constant-pool symbolic reference; lần dùng sau không phải invoke lại bootstrap.
- Có **trường hợp bootstrap chạy nhiều lần đồng thời** khi các threads tranh chấp entry chưa phân giải, nên không dựa vào side effects exactly-once.
- Một hằng động không đồng nghĩa `static final`, `invokedynamic`, `DynamicConstantDesc.resolveConstantDesc()` hay giá trị immutable sâu.

## Nguồn tham khảo chính thức

- [OpenJDK JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309).
- [Java SE 11 — JVMS §4.4.10: CONSTANT_Dynamic_info](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10).
- [Java SE 11 — JVMS §4.7.23: BootstrapMethods attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23).
- [Java SE 11 — JVMS §5.4.3: Resolution và §5.4.3.6: Dynamic Constant Resolution](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6).
- [Java SE 11 — JVMS §6.5: ldc, ldc_w, ldc2_w](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html#jvms-6.5.ldc).
- [Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html).
- [Java SE 12 — java.lang.constant (descriptor API được thêm sau Java 11)](https://docs.oracle.com/en/java/javase/12/docs/api/java.base/java/lang/constant/package-summary.html).
