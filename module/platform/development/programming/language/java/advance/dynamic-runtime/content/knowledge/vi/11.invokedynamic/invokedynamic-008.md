# 11.8 BootstrapMethodError, lỗi liên kết và hành vi khi thử sử dụng lại

## 1. Mục tiêu bài học và phạm vi

Trong Java Virtual Machine, `invokedynamic` là một bytecode instruction có **target được xác định tại thời điểm liên kết (linkage)** thông qua một **bootstrap method (BSM)**. BSM không phải logic nghiệp vụ chạy lại mỗi lần gọi. Nó được sử dụng để tạo một `java.lang.invoke.CallSite` cho một vị trí `invokedynamic` cụ thể; sau khi liên kết thành công, những lần thực thi instruction đó đi tới target của call site.

Bài này trả lời bốn câu hỏi dễ gây nhầm lẫn:

1. Khi nào JVM ném **`BootstrapMethodError`**, và khi nào ta gặp một `Error`/`LinkageError` khác?
2. Điều gì xảy ra nếu BSM ném exception, trả `null` hoặc trả `CallSite` có target sai `MethodType`?
3. **Gọi lại đúng vị trí `invokedynamic` đã liên kết thất bại có chạy BSM lần nữa không?** Việc sửa một cờ cấu hình hoặc trạng thái Java có cứu được site ấy không?
4. Hai instruction cùng tham chiếu **một mục `CONSTANT_InvokeDynamic`** trong constant pool có dùng chung trạng thái liên kết không? Nếu nạp lại class bằng class loader khác thì sao?

Ta sẽ kiểm chứng bằng chương trình Java 17+ **tự phát sinh một class file cực nhỏ có bytecode `invokedynamic`**, không cần thư viện ASM/Javassist hay `--add-exports`. Mã thí nghiệm phân biệt được **liên kết thất bại**, **liên kết thành công** và **ngoại lệ xảy ra trong target sau khi đã liên kết**.

> **Kết luận cần ghi nhớ:** Ở một lần dùng **tuần tự**, nếu việc resolve của một instruction `invokedynamic` đã thất bại, lần dùng tiếp theo của **chính instruction đó** tiếp tục báo lỗi và **không thử gọi lại BSM**. Trạng thái liên kết thuộc về từng **lexical occurrence của instruction**, không chỉ dựa trên tên method hay số thứ tự mục constant pool. Với các lần liên kết đầu tiên **đồng thời**, BSM có thể chạy song song nhiều lần; JVM sẽ chọn một kết quả để công bố.

## 2. Cơ chế liên kết của `invokedynamic`

### 2.1. Từ bytecode đến target

Một instruction `invokedynamic` trong class file có liên kết đến mục `CONSTANT_InvokeDynamic`, nơi chỉ ra:

- **Bootstrap method** thông qua thuộc tính `BootstrapMethods` và một `CONSTANT_MethodHandle`.
- **Tên gọi động** (`String name`) và **method descriptor** (`MethodType type`).
- **Các static bootstrap arguments** nếu có, ví dụ chuỗi, số, method type, method handle hoặc dynamically-computed constant phù hợp.

Luồng ý tưởng:

```text
Lần đầu thực thi một lexical invokedynamic instruction
    |
    v
Resolve bootstrap MethodHandle + tên, MethodType, static args
    |
    v
Gọi BSM với (Lookup caller, String name, MethodType type, ...)
    |
    v
Kiểm tra kết quả:
  - phải là một CallSite khác null
  - callSite.type() phải đúng MethodType mà instruction yêu cầu
    |
    +-- không hợp lệ / BSM lỗi --> liên kết thất bại --> báo lỗi
    |
    +-- hợp lệ --> gắn CallSite cho instruction --> gọi target
                                               |
                            Những lần sau dùng lại liên kết đã có
```

BSM thường có dạng:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) throws Throwable {
    // Tạo một CallSite đúng kiểu.
}
```

Đây chỉ là **chữ ký minh họa**, chưa phải chương trình chạy độc lập. Một số bootstrap method nhận thêm static arguments hoặc có chữ ký được Method Handle conversion cho phép.

`caller` không phải một đối tượng nghiệp vụ: đó là `Lookup` gắn với class chứa instruction. `name` và `type` được lấy từ mô tả tĩnh của instruction trong class file. Ví dụ một site gọi không đối số, trả `String` sẽ có `type == MethodType.methodType(String.class)`, được hiển thị dạng `()String`.

### 2.2. `CallSite` và `target` phải khớp kiểu

Kết quả hợp lệ có thể là `ConstantCallSite`, `MutableCallSite` hoặc `VolatileCallSite`, miễn là type của call site **bằng đúng** method descriptor mà instruction yêu cầu.

Ví dụ đúng cho `()String`:

```java
// Trích đoạn bên trong bootstrap, giả sử biến type là ()String.
MethodHandle target =
        MethodHandles.constant(String.class, "linked");
return new ConstantCallSite(target.asType(type));
```

`MethodHandles.constant(String.class,"linked")` là MethodHandle không đối số, trả `String`. `ConstantCallSite` cố định target tương ứng với instruction.

Ví dụ sai:

```java
// Trích đoạn: target có type ()int, nhưng invokedynamic đòi ()String.
return new ConstantCallSite(
        MethodHandles.constant(int.class, 123));
```

`ConstantCallSite` có thể được tạo hợp lệ cho `()int`; nhưng **JVM kiểm tra nó với descriptor `()String` của `invokedynamic`**. Không khớp nên linkage thất bại bằng `BootstrapMethodError`. Đây là lỗi **kết quả bootstrap** chứ chưa có lời gọi nghiệp vụ nào được chạy.

### 2.3. Liên kết và thực thi là hai giai đoạn khác nhau

Tách riêng:

- **Linkage:** resolve các symbolic references, gọi bootstrap, kiểm tra/đặt `CallSite`.
- **Invocation:** chạy `CallSite` target khi instruction được thực thi sau khi đã liên kết.

Nếu target sau đó ném `IllegalStateException`, lỗi đó thuộc **logic target**. Không vì thế mà trạng thái liên kết thành failed hay BSM tự chạy lại. Một target có thể ném exception một nghìn lần sau khi được link thành công, trong khi BSM chỉ cần tạo site cho instruction đó.

Tương tự, thay target của một `MutableCallSite` bằng `setTarget` là **thay hành vi của site đã liên kết**, không phải liên kết lại instruction từ đầu.

## 3. `BootstrapMethodError` là gì?

`java.lang.BootstrapMethodError` là subclass của `java.lang.LinkageError`, mà `LinkageError` là subclass của `java.lang.Error`:

```text
Throwable
  └── Error
       └── LinkageError
            └── BootstrapMethodError
```

Thông điệp cốt lõi của `BootstrapMethodError`: quá trình bootstrap cho `invokedynamic` hoặc dynamic constant không thể hoàn tất đúng yêu cầu, chẳng hạn resolve BSM/arguments thất bại hoặc bootstrap không trả về kết quả đúng kiểu.

**Đừng nhầm `BootstrapMethodError` với exception do target business method ném ra.** Nó liên quan đến quá trình xây dựng/resolve call site; target có thể chưa bao giờ chạy.

### 3.1. Những nguyên nhân thường gặp

| Tình huống | Giai đoạn | Hành vi / dạng lỗi đáng chú ý |
| --- | --- | --- |
| BSM ném `IllegalStateException` hoặc checked exception khác **không thuộc Error** | Đang chạy BSM | JVM tạo `BootstrapMethodError` và gắn exception ban đầu làm `cause` |
| BSM trả `null` thay vì `CallSite` | Kiểm tra kết quả BSM | `BootstrapMethodError` |
| BSM trả `CallSite` có `type()` khác descriptor của `invokedynamic` | Kiểm tra type | `BootstrapMethodError` |
| Không resolve được một bootstrap method handle hoặc phụ thuộc của nó | Trước/đang resolve BSM | Có thể là `LinkageError` phù hợp, không nên giả định mọi lỗi đều cùng một loại |
| BSM trực tiếp ném một `Error`, chẳng hạn `AssertionError`/`LinkageError` | Trong BSM | Theo quy tắc JVMS, `Error` đó được dùng làm lỗi resolution, không bắt buộc bọc lại bằng `BootstrapMethodError` |
| Target được link thành công, nhưng khi chạy ném `IllegalStateException` | **Sau linkage** | Caller nhận lỗi của target; không phải `BootstrapMethodError` do BSM |
| Bytecode sai cấu trúc hoặc verification thất bại | Nạp/verify class | Có thể là `ClassFormatError` hoặc `VerifyError`, không phải bằng chứng BSM đã chạy |

Bảng này trình bày **nhóm nguyên nhân**, không phải khẳng định mọi tổ hợp sai đều nhất định sinh ra cùng một subclass. Khi chẩn đoán, quan sát **error thực tế**, `getCause()`, stack trace và điểm xảy ra lỗi.

### 3.2. Vì sao checked/Runtime exception thường bị bọc?

Giả sử BSM ném:

```java
throw new IllegalStateException("not ready");
```

`IllegalStateException` là `RuntimeException`, **không phải** `Error`. Quy tắc JVMS biến sự cố bootstrap này thành `BootstrapMethodError`, với `cause` là `IllegalStateException`.

Nếu BSM trực tiếp ném:

```java
throw new AssertionError("broken bootstrap");
```

thì đây đã là subclass của `Error`; JVM không cần bọc nó thành `BootstrapMethodError` theo cùng quy tắc. Vì vậy câu phát biểu **“mọi lỗi trong BSM đều thành BootstrapMethodError”** là không chính xác.

### 3.3. Khi nào không phải lỗi liên kết?

Nếu một `CallSite` hợp lệ trỏ tới target:

```java
public static String alwaysFails() {
    throw new IllegalStateException("target failed");
}
```

mà `invokedynamic` được liên kết thành công, thì ngoại lệ ném khi chạy target vẫn là `IllegalStateException`. Lần gọi sau có thể vào target lần nữa. **Lỗi invocation sau linkage không làm JVM tự đánh dấu instruction là lỗi resolution**.

Ví dụ đầy đủ bên dưới dùng một site riêng tên `targetThrows` để kiểm chứng sự khác biệt này bằng số lần chạy của bootstrap và target.

## 4. Hành vi khi thử sử dụng lại: phạm vi cache chính xác

### 4.1. Sau một lần link thành công

Đối với **cùng lexical instruction `invokedynamic`**:

1. Lần đầu cần thực thi: JVM tiến hành linkage.
2. BSM trả một `CallSite` hợp lệ; JVM gắn call site đó cho instruction.
3. Lần thực thi tiếp theo: instruction dùng **liên kết đã có**; không gọi lại BSM.
4. Với `ConstantCallSite`, target giữ nguyên. Với `MutableCallSite`/`VolatileCallSite`, target có thể được cập nhật theo hợp đồng API, nhưng điều đó **không tái chạy bootstrap**.

Thay đổi biến Java `ready` sau khi site đã liên kết thành công không làm JVM tự lựa chọn BSM khác. Chỉ logic target hoặc cơ chế thay target của mutable/volatile call site mới có thể làm hành vi thực thi đổi theo thiết kế.

### 4.2. Sau một lần link thất bại

Nếu một lần thử đầu tiên của một instruction `invokedynamic` kết thúc bằng lỗi linkage:

1. JVM đánh dấu **kết quả resolution là thất bại cho instruction đó**.
2. Các lần thực thi sau của **chính instruction đó** tiếp tục thất bại theo lỗi resolution đã ghi nhận.
3. **BSM không được thử lại** chỉ vì caller đã `catch` exception.
4. Sửa một cờ `ready` hoặc cập nhật cấu hình sau lần thất bại **không cứu được site đã thất bại** trong class đã load.

**Không nên viết retry loop quanh `BootstrapMethodError` với kỳ vọng nó sẽ tái gọi BSM.** Đó không phải một API retry transient I/O. Nếu muốn cơ chế phục hồi, hãy thiết kế trước một CallSite được link thành công tới target có khả năng fallback/retry, hoặc nạp một **class mới trong loader mới** khi phù hợp.

### 4.3. Cache theo instruction, không chỉ theo constant pool entry

Hai instruction `invokedynamic` khác nhau trong một class file **có thể cùng tham chiếu một `CONSTANT_InvokeDynamic`**. JVM vẫn resolve từng **lexical occurrence** riêng biệt:

```text
IndyGenerated.fire()  : invokedynamic #19  ---> lần đầu BSM lỗi
IndyGenerated.other() : invokedynamic #19  ---> lần đầu BSM thành công
                                             (cùng mục #19, khác opcode site)
```

Lỗi của `fire()` **không làm `other()` bị đánh dấu lỗi** chỉ vì cả hai instruction trỏ tới `#19`. Trong thí nghiệm, `fire()` thất bại khi `ready=false`, sau đó `ready=true` và `other()` liên kết thành công. Điều này không mâu thuẫn với quy tắc cache: chúng là **hai instruction**, nên có hai trạng thái liên kết độc lập.

### 4.4. Nạp lại class bằng class loader khác

Trong JVM, danh tính class gắn với **tên class + defining class loader**. Cùng các byte `IndyGenerated.class` được định nghĩa bởi một `ClassLoader` khác tạo **một class khác**, mang các instruction/runtime linkage state riêng.

Thử nghiệm sẽ sử dụng:

```java
Class<?> c1 = new Definer().create(bytes);
Class<?> c2 = new Definer().create(bytes);
```

Đây là **trích đoạn** của chương trình hoàn chỉnh, không phải code chạy độc lập. Hai lần `new Definer()` tạo hai defining loaders khác nhau. `c1` và `c2` có cùng tên nhị phân nhưng **không cùng class identity**, vì vậy call site ở `c2` có thể liên kết lại từ đầu. Đây không phải “retry thành công trên site cũ” mà là **site mới của một class mới**.

### 4.5. Cảnh báo về concurrency

Quy tắc “bootstrap chạy một lần” phải hiểu trong ngữ cảnh **lần dùng tuần tự đã hoàn tất linkage**. JVMS cho phép nhiều thread cùng cố liên kết một site đang chưa resolve, nên **BSM có thể bị gọi đồng thời nhiều lần** cho cùng symbolic reference. JVM chọn một kết quả liên kết được công bố; các kết quả đồng thời khác bị bỏ qua.

Do đó:

- BSM có side effect dùng chung phải được thiết kế thread-safe.
- Đừng chứng minh correctness bằng giả định `bootstrapRuns == 1` trong mọi stress test đa luồng.
- Thí nghiệm bên dưới **cố ý chạy tuần tự**, nên số đếm deterministic và rõ quan hệ nhân quả.
- Với một site đã resolve thất bại, những lần gọi tiếp theo sau đó không tạo ra retry mới chỉ vì trước đó có nhiều thread tham gia liên kết.

## 5. Thực nghiệm Java 17+: tạo `invokedynamic` thật, không dùng thư viện ngoài

### 5.1. Vì sao không chỉ viết lambda trong Java source?

`javac` thường phát sinh `invokedynamic` cho lambda/method reference và có thể cho nối chuỗi tùy phiên bản/cách biên dịch. Nhưng bootstrap của các ví dụ compiler sinh thường là `LambdaMetafactory` hoặc `StringConcatFactory` được compiler cấu hình hợp lệ. Khó chủ động làm bootstrap đó **ném lỗi đúng thời điểm** mà không dựa vào biến đổi classfile.

Để kiểm chứng chính xác “BSM lỗi lần đầu rồi thử lại”, ta sẽ **tự ghi một class file JVM tối giản** bằng `DataOutputStream`. Nó có bốn method `public static`:

| Method trong class sinh ra | Mục constant pool | Bootstrap behavior | Mục đích |
| --- | --- | --- | --- |
| `fire()` | `#19` | BSM sẽ ném exception khi `ready=false` | Thử cache một failed site |
| `other()` | **`#19`** | BSM thành công khi `ready=true` | Chứng minh cùng CP entry nhưng khác instruction |
| `wrong()` | `#22` | BSM trả `ConstantCallSite` kiểu `()int` thay vì `()String` | Chứng minh kiểm tra type lúc linkage |
| `unstable()` | `#26` | BSM thành công; target luôn ném `IllegalStateException` | Phân biệt lỗi target với lỗi bootstrap |

Cả bốn instruction có descriptor `()Ljava/lang/String;` tương đương MethodType `()String`. Chúng dùng **cùng một bootstrap method handle** trong thuộc tính `BootstrapMethods`, nhưng truyền tên symbolic khác nhau cho những site tương ứng.

### 5.2. Mã nguồn đầy đủ

Lưu nguyên nội dung sau thành file **`IndyFailureLab.java`**. Chương trình chạy được trên **JDK 17 trở lên**; phần classfile được tạo sử dụng **major version 51** (Java 7), là định dạng JVM hỗ trợ `invokedynamic`.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;

public class IndyFailureLab {
    private static int bootstrapRuns;
    private static int targetRuns;
    private static boolean ready;

    public static String throwFromTarget() {
        targetRuns++;
        throw new IllegalStateException("target failed");
    }

    // BSM được tham chiếu bằng MethodHandle từ class sinh ra.
    public static CallSite bootstrap(
            MethodHandles.Lookup lookup, String name, MethodType type)
            throws ReflectiveOperationException {
        bootstrapRuns++;

        if ("badType".equals(name)) {
            // CallSite này có type ()int, khác ()String mà site yêu cầu.
            return new ConstantCallSite(
                    MethodHandles.constant(int.class, 123));
        }
        if ("targetThrows".equals(name)) {
            // Link thành công; chỉ lúc CHẠY target mới ném exception.
            return new ConstantCallSite(MethodHandles.lookup().findStatic(
                    IndyFailureLab.class, "throwFromTarget", type));
        }
        if (!ready) throw new IllegalStateException("not ready");

        return new ConstantCallSite(
                MethodHandles.constant(String.class, "linked").asType(type));
    }

    static final class Definer extends ClassLoader {
        Definer() {
            super(IndyFailureLab.class.getClassLoader());
        }

        Class<?> create(byte[] bytes) {
            return defineClass("IndyGenerated", bytes, 0, bytes.length);
        }
    }

    private static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static byte[] bytecode() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(51); // Class file Java 7; JDK 17+ đọc được.
        out.writeShort(28); // Constant pool: các entry #1..#27.

        utf8(out, "IndyGenerated");                // #1
        out.writeByte(7); out.writeShort(1);       // #2 Class
        utf8(out, "java/lang/Object");             // #3
        out.writeByte(7); out.writeShort(3);       // #4 Class
        utf8(out, "Code");                         // #5
        utf8(out, "fire");                         // #6
        utf8(out, "()Ljava/lang/String;");         // #7
        utf8(out, "other");                        // #8
        utf8(out, "BootstrapMethods");             // #9
        utf8(out, "IndyFailureLab");               // #10
        out.writeByte(7); out.writeShort(10);      // #11 Class
        utf8(out, "bootstrap");                    // #12
        utf8(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/invoke/MethodType;)"
                + "Ljava/lang/invoke/CallSite;");  // #13
        out.writeByte(12);                        // #14 NameAndType
        out.writeShort(12); out.writeShort(13);
        out.writeByte(10);                        // #15 Methodref
        out.writeShort(11); out.writeShort(14);
        out.writeByte(15);                        // #16 MethodHandle
        out.writeByte(6); out.writeShort(15);     // REF_invokeStatic
        utf8(out, "dynamicName");                 // #17
        out.writeByte(12);                        // #18 NameAndType
        out.writeShort(17); out.writeShort(7);
        out.writeByte(18);                        // #19 InvokeDynamic
        out.writeShort(0); out.writeShort(18);    // BootstrapMethods[0]
        utf8(out, "badType");                     // #20
        out.writeByte(12);                        // #21 NameAndType
        out.writeShort(20); out.writeShort(7);
        out.writeByte(18);                        // #22 InvokeDynamic
        out.writeShort(0); out.writeShort(21);    // BootstrapMethods[0]
        utf8(out, "wrong");                       // #23
        utf8(out, "targetThrows");                // #24
        out.writeByte(12);                        // #25 NameAndType
        out.writeShort(24); out.writeShort(7);
        out.writeByte(18);                        // #26 InvokeDynamic
        out.writeShort(0); out.writeShort(25);    // BootstrapMethods[0]
        utf8(out, "unstable");                    // #27

        out.writeShort(0x0021); // ACC_PUBLIC | ACC_SUPER
        out.writeShort(2);      // this_class
        out.writeShort(4);      // superclass java.lang.Object
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(4);      // methods_count

        int[] names = {6, 8, 23, 27};
        int[] indyIndexes = {19, 19, 22, 26};
        for (int i = 0; i < names.length; i++) {
            out.writeShort(0x0009); // ACC_PUBLIC | ACC_STATIC
            out.writeShort(names[i]);
            out.writeShort(7);      // descriptor ()String
            out.writeShort(1);      // one Code attribute
            out.writeShort(5);      // UTF8 "Code"
            out.writeInt(18);       // Code attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(0);      // max_locals
            out.writeInt(6);        // code_length
            out.writeByte(0xba);    // invokedynamic
            out.writeShort(indyIndexes[i]);
            out.writeShort(0);      // two mandated zero bytes
            out.writeByte(0xb0);    // areturn
            out.writeShort(0);      // exception_table_length
            out.writeShort(0);      // nested attributes_count
        }

        out.writeShort(1);   // class attributes_count
        out.writeShort(9);   // "BootstrapMethods"
        out.writeInt(6);
        out.writeShort(1);   // one BSM entry
        out.writeShort(16);  // bootstrap MethodHandle
        out.writeShort(0);   // no static bootstrap arguments
        out.flush();
        return bytes.toByteArray();
    }

    // Reflection bọc exception do method target/bytecode ném.
    // Unwrap để nhìn thấy BootstrapMethodError/IllegalStateException thật.
    private static String invoke(Method method) throws Throwable {
        try {
            return (String) method.invoke(null);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = bytecode();
        Files.write(Path.of("IndyGenerated.class"), bytes);

        Class<?> firstClass = new Definer().create(bytes);
        Method fire = firstClass.getMethod("fire");
        Method other = firstClass.getMethod("other");
        Method wrong = firstClass.getMethod("wrong");
        Method unstable = firstClass.getMethod("unstable");

        // Site #1: BSM ném exception vì ready=false.
        try {
            invoke(fire);
        } catch (BootstrapMethodError ex) {
            System.out.println("first=" + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("calls after first=" + bootstrapRuns);

        // Sửa trạng thái sau thất bại: KHÔNG làm BSM site #1 chạy lại.
        ready = true;
        try {
            invoke(fire);
        } catch (BootstrapMethodError ex) {
            System.out.println("retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after retry=" + bootstrapRuns);

        // Site #2: instruction khác dùng cùng CP entry #19.
        System.out.println("other=" + invoke(other));
        System.out.println("calls after other=" + bootstrapRuns);

        ready = false;
        System.out.println("other again=" + invoke(other));
        System.out.println("calls after reused success=" + bootstrapRuns);

        // Site #3: BSM trả CallSite có MethodType không phù hợp.
        try {
            invoke(wrong);
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong type=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after wrong type=" + bootstrapRuns);
        try {
            invoke(wrong);
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after wrong retry=" + bootstrapRuns);

        // Site #4: liên kết thành công, TARGET ném exception hai lần.
        for (int i = 1; i <= 2; i++) {
            try {
                invoke(unstable);
            } catch (IllegalStateException ex) {
                System.out.println("target " + i + "="
                        + ex.getClass().getSimpleName());
            }
        }
        System.out.println("calls after target invokes=" + bootstrapRuns);
        System.out.println("target body runs=" + targetRuns);

        // Cùng bytecode nhưng định nghĩa class dưới loader MỚI.
        ready = true;
        Class<?> freshClass = new Definer().create(bytes);
        System.out.println("fresh=" + invoke(freshClass.getMethod("fire")));
        System.out.println("calls after new class=" + bootstrapRuns);
    }
}
```

### 5.3. Biên dịch và chạy

Trong thư mục chứa `IndyFailureLab.java`, dùng:

```bash
javac IndyFailureLab.java
java IndyFailureLab
```

Chương trình sẽ sinh thêm file `IndyGenerated.class` trong thư mục hiện hành. File này là **class file tạo bằng code**, không phải class Java source cần biên dịch lần hai. Nó không có constructor mặc định nhưng có bốn `public static` methods; chương trình chỉ sử dụng các method đó thông qua Reflection.

**Stdout chính xác của chương trình đã kiểm tra:**

```text
first=BootstrapMethodError
cause=IllegalStateException
calls after first=1
retry=BootstrapMethodError
calls after retry=1
other=linked
calls after other=2
other again=linked
calls after reused success=2
wrong type=BootstrapMethodError
calls after wrong type=3
wrong retry=BootstrapMethodError
calls after wrong retry=3
target 1=IllegalStateException
target 2=IllegalStateException
calls after target invokes=4
target body runs=2
fresh=linked
calls after new class=5
```

Đoạn stdout này được quan sát khi chạy **tuần tự**, không có thread cạnh tranh. Số đếm dựa trên `bootstrapRuns++`, `targetRuns++`, không phụ thuộc địa chỉ bộ nhớ, tên class loader hoặc nội dung stack trace.

### 5.4. Đọc bytecode để xác nhận không “giả lập” invokedynamic

Sau khi chạy chương trình, gõ:

```bash
javap -v -c IndyGenerated.class
```

Trong output dài của `javap`, tìm `InvokeDynamic`, `BootstrapMethods` và opcode `invokedynamic`. Các dòng cốt lõi có dạng:

```text
major version: 51
#19 = InvokeDynamic ... // dynamicName:()Ljava/lang/String;
#22 = InvokeDynamic ... // badType:()Ljava/lang/String;
#26 = InvokeDynamic ... // targetThrows:()Ljava/lang/String;

fire():     invokedynamic #19
other():    invokedynamic #19
wrong():    invokedynamic #22
unstable(): invokedynamic #26
```

Đoạn trên là **trích yếu các dòng liên quan**, không phải output nguyên khối của `javap`. Bản dump thật còn có flags, method descriptors, constant-pool indices, `BootstrapMethods` và nhiều dòng phụ trợ. Chính sự lặp lại của **`invokedynamic #19` trong hai method khác nhau** chứng minh chúng chung constant-pool entry nhưng là hai instruction độc lập.

Chương trình thực sự chứa mã bytecode `0xba`, là opcode của `invokedynamic`, theo sau là **chỉ số constant pool 2 byte** và **2 byte zero**. `0xb0` là opcode `areturn` cho kết quả tham chiếu `String`. Vì classfile generator cố tình ngắn, mỗi method chỉ có một `invokedynamic` rồi `areturn`.

## 6. Đọc kết quả thí nghiệm theo từng nhóm

### 6.1. Site `fire()`: thất bại một lần, gọi lại vẫn lỗi

Ở lần đầu `fire()`:

- BSM nhận `name="dynamicName"` và `type=()String`.
- `bootstrapRuns` tăng từ 0 lên 1.
- `ready=false`, BSM ném `IllegalStateException("not ready")`.
- JVM báo `BootstrapMethodError`; `getCause()` của lỗi đầu tiên là `IllegalStateException`.

Sau đó chương trình đặt `ready=true` và gọi lại **cùng `fire()`**:

- Output vẫn `retry=BootstrapMethodError`.
- `bootstrapRuns` vẫn là **1**.
- Không có cơ hội cho BSM quan sát trạng thái `ready=true` ở instruction ấy, vì resolution đã thất bại và kết quả được ghi nhận.

Đây là minh chứng trực tiếp cho câu hỏi “thử sử dụng lại” của đề bài. **Catch rồi gọi lại không phải retry BSM.**

Lưu ý: Không dùng so sánh `error1 == error2` như phép thử chính của cache. Điều cần kiểm tra là **cùng site tiếp tục nhận lỗi resolution và BSM không được gọi lại**; chi tiết identity của các đối tượng exception được JVM ném qua từng đường gọi không phải cách đáng tin để mô tả cơ chế liên kết.

### 6.2. Site `other()`: cùng CP entry, khác instruction

`other()` dùng **cùng mục constant pool `#19`** với `fire()`, nhưng nằm ở lexical instruction khác:

- Khi `ready=true`, lần gọi `other()` tạo một `CallSite` hợp lệ, trả `linked`.
- `bootstrapRuns` tăng lên **2**.
- Đặt lại `ready=false` rồi gọi `other()` lần nữa vẫn nhận `linked`; số đếm giữ **2**.

Vậy **cache của `fire()` không làm hỏng `other()`**. Sau khi `other()` được link thành công, sự thay đổi trạng thái bên ngoài không làm BSM của `other()` chạy lại.

Đừng mở rộng kết luận này thành “mỗi lần gọi method `other` đều link mới”: đó là **một instruction trong body của method**; mỗi lần method được gọi lặp lại **cùng một instruction** nên tái sử dụng site đã link.

### 6.3. Site `wrong()`: BSM trả đúng loại đối tượng nhưng sai target type

`wrong()` có descriptor `()String`, nhưng BSM (khi tên là `badType`) trả:

```java
return new ConstantCallSite(MethodHandles.constant(int.class, 123));
```

`ConstantCallSite` có target type `()int`, không bằng `()String`. JVM ném `BootstrapMethodError` **ngay khi validate bootstrap result**. Lúc này không hề xảy ra việc target `()int` bị gọi rồi “không cast được kết quả” — nó **chưa vượt qua giai đoạn linkage**.

Output:

```text
wrong type=BootstrapMethodError
calls after wrong type=3
wrong retry=BootstrapMethodError
calls after wrong retry=3
```

Vì BSM trả sai `MethodType`, gọi lại `wrong()` không làm JVM kiểm tra lần nữa với một target mới.

### 6.4. Site `unstable()`: target ném exception nhưng linkage vẫn tốt

BSM của `unstable()` tạo `ConstantCallSite` trỏ đến method Java `throwFromTarget()` có **đúng `()String`**. Method này mỗi lần chạy đều tăng `targetRuns` rồi ném `IllegalStateException`.

Sau hai lần gọi:

```text
target 1=IllegalStateException
target 2=IllegalStateException
calls after target invokes=4
target body runs=2
```

Ý nghĩa:

- BSM của site này **chỉ cần chạy một lần** trong thí nghiệm tuần tự: số đếm bootstrap tăng từ 3 lên 4.
- Target được **gọi hai lần**, nên `targetRuns=2`.
- Lỗi hiện ra là `IllegalStateException` từ target, **không phải** `BootstrapMethodError`.
- Linkage thành công được giữ nguyên sau mỗi exception của target.

Như vậy **thử gọi lại một target thất bại** khác hoàn toàn với **thử resolve lại một site mà BSM đã thất bại**.

### 6.5. Class loader mới: một site mới có thể link thành công

Ở cuối chương trình, `ready=true` và một `Definer` mới định nghĩa class `IndyGenerated` từ cùng mảng `bytes`:

```text
fresh=linked
calls after new class=5
```

`freshClass` khác `firstClass` về danh tính class dù cùng binary name. Instruction `fire()` trong class mới chưa từng liên kết nên BSM có thể chạy (tăng `bootstrapRuns` lên 5) và thành công.

**Đây không phải “sửa thành công lỗi của site cũ”.** Site cũ trong `firstClass` vẫn có lịch sử failed resolution; class mới có trạng thái riêng.

## 7. Những lỗi liên kết khác cần phân biệt

Một exception quan sát được ở thời điểm chạy `invokedynamic` có thể đến từ các lớp kiểm tra khác nhau:

| Lỗi / tình huống | Gợi ý nguyên nhân | Điều cần điều tra |
| --- | --- | --- |
| `BootstrapMethodError` với `cause=IllegalStateException` | BSM ném non-`Error` exception | Code BSM, static config, khởi tạo phụ thuộc, `cause` và stack trace |
| `BootstrapMethodError` khi BSM trả `null` hoặc sai type | Bootstrap result không thỏa hợp đồng JVM | `CallSite` có null không? `callSite.type()` có đúng descriptor không? |
| `NoSuchMethodError` hoặc `IllegalAccessError` | Có thể là lỗi resolve method/handle/phụ thuộc trong linkage | Tên/descriptor/class loader/module/access thay đổi? |
| `ClassFormatError` / `VerifyError` | Class file sai cấu trúc hoặc bytecode không hợp lệ | Sinh bytecode/transformer, stack maps, constant pool, JVM version |
| `ExceptionInInitializerError` | Class initializer của phụ thuộc thất bại | `<clinit>` và nguyên nhân bên trong, có nằm trong đường bootstrap hay không |
| `UndeclaredThrowableException` / `InvocationTargetException` | Wrapper của Reflection/proxy ở lớp caller | Unwrap đúng tầng; không kết luận BSM sai chỉ từ wrapper |
| `WrongMethodTypeException` khi gọi `MethodHandle.invokeExact` | Call site Java của Method Handle sai chữ ký | Khác với JVM reject `CallSite` target type trong `invokedynamic` linkage |
| `ClassCastException` / `NullPointerException` từ target | Logic thực thi sau linkage | Có phải BSM đã trả CallSite hợp lệ và target đang chạy? |

Cần đọc **lỗi gốc chứ không chỉ class ngoài cùng**. Trong chương trình thí nghiệm, `Method.invoke` bọc lỗi do method được gọi ném trong `InvocationTargetException`. Helper:

```java
try {
    return (String) method.invoke(null);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

là để bỏ **Reflection wrapper** và quan sát chính xác lỗi ở tầng `invokedynamic`/target. Nó **không** tạo ra hay chữa `BootstrapMethodError`.

### 7.1. Vì sao không nên luôn `catch (BootstrapMethodError)` rồi tiếp tục?

`BootstrapMethodError` là một `Error` liên quan đến JVM linkage. Nếu production code bắt rồi gọi lại ngay cùng site, rất có thể chỉ nhận lại tình trạng lỗi cũ. Việc bắt chỉ hợp lý khi:

- Viết test/thí nghiệm tái hiện.
- Thu thập diagnostics rồi báo lỗi có ngữ cảnh.
- Có chiến lược fallback **không dựa vào instruction đã failed**.

Đừng nuốt lỗi rồi trả một giá trị giả khiến những phần còn lại của ứng dụng tưởng hệ thống đã khởi tạo hợp lệ. Một site failed sau một cấu hình sai thường cần sửa nguyên nhân, rồi **khởi tạo JVM/class identity mới** ở mức triển khai; đôi khi cần thay đổi cách framework thiết kế BSM.

### 7.2. Không gộp mọi `LinkageError` thành lỗi bootstrap

Một `NoSuchMethodError` có thể do binary incompatibility: caller tham chiếu method descriptor không còn tồn tại. Một `IllegalAccessError` có thể do thay đổi visibility/module boundary. Một `VerifyError` có thể đến từ bytecode transformer xuất sai instruction. Những lỗi ấy **không phải lúc nào cũng là kết quả BSM đã được gọi**, nên chẩn đoán cần phân biệt:

1. Class có được load/verify không?
2. Bootstrap method handle và các static arguments có resolve được không?
3. BSM có thực sự bắt đầu chạy không (log/counter)?
4. BSM ném exception hay trả kết quả?
5. JVM có chấp nhận CallSite type không?
6. Target có đang thực thi khi exception xảy ra không?

## 8. Vì sao các quy tắc này quan trọng với lambda và string concat?

### 8.1. Lambda / method reference

Trên các phiên bản Java hiện đại, compiler có thể phát sinh `invokedynamic` cho một lambda hoặc method reference, thường tham chiếu `java.lang.invoke.LambdaMetafactory` hoặc `altMetafactory` trong `BootstrapMethods`.

Nếu bootstrap của lambda không resolve được method handle, class liên quan bị đổi binary signature, hoặc các điều kiện metafactory không thỏa, caller có thể thấy linkage error. **Đừng kết luận do nội dung lambda chạy sai** trước khi kiểm tra xem lỗi xảy ra lúc tạo lambda object (linkage) hay khi gọi method của functional interface (target execution).

Có thể xem bytecode của một Java class thông thường:

```bash
javac MyLambdaDemo.java
javap -c -v MyLambdaDemo.class
```

Đây là **mẫu lệnh**: `MyLambdaDemo.java` phải là source code có lambda do bạn tạo, không phải file đi kèm thí nghiệm chính. Tìm `InvokeDynamic`, `BootstrapMethods` và owner `LambdaMetafactory` nếu compiler dùng chiến lược đó.

### 8.2. String concatenation

`javac` trên Java 9+ thường biên dịch nối chuỗi theo chiến lược dựa trên `invokedynamic` và `StringConcatFactory`. Đây là tối ưu hóa của compiler/runtime, không phải một lý do để ứng dụng bình thường tự xử lý BSM.

Nếu hệ thống dùng bytecode enhancer, agent, obfuscator hoặc classloader custom, những thành phần đó có thể làm sai bootstrap arguments hoặc descriptor mà compiler dự kiến. Hãy xem cả bytecode **trước và sau transformer**, vì code Java source có thể hoàn toàn hợp lệ nhưng classfile đã bị sửa không còn phù hợp.

**Không** suy luận rằng mọi chuỗi `"a" + value` ở mọi compiler/JDK đều tạo `invokedynamic`: constant folding có thể loại bỏ phép gọi, và compiler flags/chiến lược có thể khác.

### 8.3. Dynamic constant (`CONSTANT_Dynamic`) có quan hệ nhưng không trùng

Java classfile còn có `CONSTANT_Dynamic` cho giá trị constant được tính qua bootstrap. Nó có quy tắc resolve/cached result tương tự về mặt ý tưởng, nhưng:

- `invokedynamic` bootstrap nhận `MethodType` và phải cung cấp `CallSite` có type phù hợp.
- Dynamic constant bootstrap nhận kiểu constant (một `Class<?>`) và phải cung cấp **giá trị tương thích**.
- `BootstrapMethodError` cũng có thể báo lỗi của dynamic constant.

Đề bài này tập trung vào **linkage của invokedynamic instruction**. Đừng dùng thí nghiệm `ldc CONSTANT_Dynamic` làm bằng chứng thay thế cho phạm vi cache **theo lexical invokedynamic instruction**.

## 9. Các biện pháp thiết kế bootstrap có thể bảo trì

### 9.1. BSM nên ít phụ thuộc trạng thái tạm thời

Một BSM phụ thuộc vào service discovery, network, file config hoặc service chưa sẵn sàng có thể gây **poisoned call site** nếu thất bại trong lần link đầu. Khi cần khởi tạo chậm hoặc retry thực sự, một chiến lược tốt hơn là:

1. BSM **trả về một CallSite hợp lệ** có target type chính xác.
2. Target này chịu trách nhiệm kiểm tra điều kiện/ủy quyền và có thể retry logic nghiệp vụ.
3. Nếu cần đổi target, dùng `MutableCallSite` hoặc `VolatileCallSite` đúng hợp đồng về type và visibility.
4. Thất bại ngắn hạn của nghiệp vụ được báo như exception từ target, không biến thành BSM linkage failure vĩnh viễn.

Không có nghĩa mọi BSM phải “nuốt” lỗi cấu hình: nếu cấu hình bất hợp lệ là lỗi không thể hồi phục, fail-fast bằng linkage error có thể có chủ đích. Cần phân biệt **transient failure** và **invalid linkage contract**.

### 9.2. Kiểm tra đúng `MethodType` trước khi trả `CallSite`

Dù JVM sẽ validate, BSM có thể chủ động:

```java
// Trích đoạn minh họa bên trong một bootstrap.
MethodHandle target = ...; // Được tạo ở nơi có đủ ngữ cảnh.
if (!target.type().equals(type)) {
    target = target.asType(type); // Chỉ hợp lệ nếu có conversion hỗ trợ.
}
return new ConstantCallSite(target);
```

`asType` có thể ném `WrongMethodTypeException` hoặc lỗi chuyển đổi khác nếu không thể chuyển đổi. Code cần quyết định fail-fast hoặc báo lỗi rõ ràng, không mặc định mọi target type đều tự thích nghi được.

Không nên “giả” một CallSite kiểu `()String` bằng target `()int` rồi hy vọng JVM tự cast hộ. Thí nghiệm `wrong()` cho thấy lỗi xuất hiện **trong linkage**.

### 9.3. Quan sát BSM một cách có kiểm soát

BSM là đường code runtime nhạy cảm. Nếu thêm log/counter để chẩn đoán:

- Ghi `caller.lookupClass()`, `name`, `type` và static args **khi được phép**, nhưng tránh rò rỉ dữ liệu nhạy cảm.
- Ghi riêng các giai đoạn bắt đầu BSM, tạo target, tạo CallSite và trả về.
- Nếu có concurrent linkage, counter cần thread-safe (`AtomicInteger` thay cho `int++`). Đừng dùng side effect của BSM làm kết quả nghiệp vụ vì BSM có thể chạy nhiều lần cạnh tranh.
- Ghi exception class + cause, không chỉ message. Tránh giả định lớp ngoài cùng trong log là lỗi gốc.

Các log của JVM/đặc tả có thể khác nhau giữa các bản JDK; ưu tiên **lỗi, cause và kết quả chạy** thay vì so khớp toàn bộ stack trace với ví dụ trên mạng.

## 10. Quy trình điều tra một lỗi thực tế

Khi gặp `BootstrapMethodError` hoặc nghi lỗi `invokedynamic`, thực hiện theo thứ tự:

1. **Thu thập Java version và class loader.** Ghi `java -version`, cách tạo JVM, loader của class chứa site, framework/agent có chỉnh bytecode không.
2. **Lấy cause chain.** Nếu lỗi xuất hiện qua `Method.invoke`, unwrap `InvocationTargetException`. Nếu lỗi được proxy/wrapper bọc, xem chuỗi nguyên nhân thay vì chỉ lớp ngoài.
3. **Xác định site thực sự thất bại.** Dùng stack trace, tên method và `javap -v -c <class>` để tìm opcode `invokedynamic` và mục `BootstrapMethods`.
4. **Phân biệt before/after linkage.** BSM có được chạy chưa? Nó trả `CallSite` chưa? Có method type mismatch không? Hay chính target đã chạy và ném exception?
5. **Kiểm tra name/descriptor.** `CallSite.type()` phải khớp `MethodType` của instruction. Với dynamic arguments/condy, xem static argument resolution.
6. **Tái hiện trong lần đầu mới.** Một site đã failed không tái link khi gọi lại trong cùng class. Để xác nhận sau khi sửa nguyên nhân, dùng **JVM mới hoặc class được định nghĩa dưới loader mới** nếu kiến trúc cho phép; đừng chỉ gọi method lặp lại.
7. **Loại trừ concurrency.** Một bootstrap counter lớn hơn 1 trong lần khởi tạo cạnh tranh không nhất thiết chứng minh JVM "retry sau khi failed"; có thể có nhiều thread đồng thời.
8. **Lập test riêng cho target.** Nếu CallSite đã hợp lệ, test exception từ target độc lập; không gộp với lỗi BSM.
9. **Sửa ở đúng tầng.** Nếu bytecode bị sai, sửa transformer/generator. Nếu BSM trả sai type, sửa BSM. Nếu phụ thuộc không tìm thấy, sửa binary/module graph. Nếu lỗi nghiệp vụ transient, cân nhắc target có retry hợp lệ.
10. **Kiểm chứng lại từ trạng thái mới.** So sánh kết quả tại site mới/JVM mới, không dùng site cũ làm thước đo duy nhất sau khi đã lỗi resolution.

Bảng nhanh:

| Triệu chứng | Diễn giải phù hợp | Hành động |
| --- | --- | --- |
| Gọi lại cùng site luôn `BootstrapMethodError` và BSM counter đứng yên | Failure cached theo instruction | Đừng retry tại đó; sửa nguyên nhân và kiểm tra trên class/JVM mới |
| Hai method cùng `InvokeDynamic #19` nhưng kết quả khác nhau | Hai lexical occurrences độc lập | Kiểm tra từng opcode, không nhóm chỉ theo CP index |
| BSM counter tăng một lần nhưng target ném exception nhiều lần | Linkage thành công, invocation thất bại | Chẩn đoán target |
| `BootstrapMethodError` có cause là exception từ BSM | BSM ném non-`Error` | Sửa logic/cấu hình BSM |
| BSM trả CallSite target sai type | Validate link thất bại | Tạo/cast MethodHandle đúng `MethodType` |
| Site mới ở class loader mới chạy được | Linkage state khác | Xác nhận identity loader, không gọi đó là phục hồi site cũ |

## 11. Câu hỏi và bài tập có đáp án

**Câu 1.** BSM `bootstrap(...)` ném `IllegalStateException` ở lần gọi đầu của `invokedynamic`. JVM báo loại lỗi nào?  
**Đáp án:** Thường là `BootstrapMethodError` với `cause` là `IllegalStateException` vì exception này không phải subclass của `Error`.

**Câu 2.** Sau khi lỗi linkage, bạn sửa một biến `ready=false` thành `ready=true` rồi gọi lại cùng instruction. BSM có được chạy lại không?  
**Đáp án:** Không. Với lần dùng tuần tự sau failed resolution của **cùng site**, JVM giữ kết quả lỗi và không thử gọi bootstrap lần nữa.

**Câu 3.** Hai instruction trong cùng class cùng tham chiếu mục `CONSTANT_InvokeDynamic #19`. Một site thất bại có bắt buộc site kia thất bại không?  
**Đáp án:** Không. Resolution của call site `invokedynamic` có phạm vi **từng lexical instruction**, dù dùng chung CP entry. Ví dụ `fire` và `other` minh họa.

**Câu 4.** BSM trả `new ConstantCallSite(MethodHandles.constant(int.class,1))` cho instruction `()String`. Lỗi xuất hiện ở giai đoạn nào?  
**Đáp án:** Kiểm tra bootstrap result trong **linkage**, vì target type `()int` không bằng descriptor `()String`; JVM báo `BootstrapMethodError`.

**Câu 5.** BSM trả `CallSite` hợp lệ; target ném `IllegalStateException` mỗi lần chạy. Những lần sau có tự link lại không?  
**Đáp án:** Không. Site đã link thành công. Target có thể tiếp tục được gọi và ném exception mỗi lần; đây là lỗi target, không phải lỗi BSM. Ví dụ `unstable()` có BSM một lần, target hai lần.

**Câu 6.** Đã `catch (BootstrapMethodError)`, có nên đặt `Thread.sleep(1000)` rồi gọi lại site cũ để “thử BSM lần hai” không?  
**Đáp án:** Không. Nghỉ một giây không xóa failed resolution state. Sửa nguyên nhân ở bước linkage và kiểm chứng trên site/class identity mới khi cần.

**Câu 7.** Vì sao class loader mới có thể tạo lại `fire()` thành công dù site cũ đã failed?  
**Đáp án:** Class có cùng binary name nhưng **defining loader khác** là một class identity khác với site linkage state mới; không phải reset site cũ.

**Câu 8.** Nếu nhiều thread cùng chạm site chưa link, bootstrap counter có thể lớn hơn 1 không?  
**Đáp án:** Có. JVMS cho phép BSM được thực thi đồng thời, rồi chọn một kết quả công bố. Đừng dùng `int++` không đồng bộ để khẳng định tính chính xác trong tình huống đó.

**Câu 9.** BSM trực tiếp ném `AssertionError`. Có luôn bị bọc vào `BootstrapMethodError` không?  
**Đáp án:** Không. Theo quy tắc JVMS, một `Error` ném trong BSM được dùng làm lỗi resolution thay vì luôn tạo BME wrapper cho nó.

**Câu 10.** Vì sao cần `javap -v -c` thay vì chỉ đọc source Java khi chẩn đoán `invokedynamic`?  
**Đáp án:** Compiler/transformer quyết định các `InvokeDynamic`, bootstrap arguments và method descriptors trong classfile. Source có thể không mô tả trực tiếp instruction hoặc đã bị enhancer chỉnh sửa.

**Câu 11.** Một site đã link tới `MutableCallSite`. Gọi `setTarget` làm bootstrap chạy lại hay không?  
**Đáp án:** Không. `setTarget` đổi target của **site đã link**, với type phù hợp và theo memory visibility contract; không tái resolution của instruction.

**Câu 12.** Cách phân biệt `BootstrapMethodError` quan sát qua Reflection với `InvocationTargetException`?  
**Đáp án:** `Method.invoke` bọc exception do method được gọi ném. Lấy `InvocationTargetException.getCause()` để xem lỗi thật; việc unwrap không làm thay đổi kết quả linkage.

## 12. Tóm tắt và tài liệu tham khảo

- `invokedynamic` được link thông qua bootstrap để nhận `CallSite` phù hợp với descriptor.
- **`BootstrapMethodError`** phản ánh các lỗi bootstrap hoặc kết quả call site không hợp lệ; một `Error` do BSM trực tiếp ném có quy tắc truyền lỗi riêng.
- **Một instruction failed resolution không bootstrap lại khi gọi lại**, kể cả khi điều kiện bên ngoài đã thay đổi.
- **Hai instruction khác nhau** có thể liên kết độc lập dù cùng constant-pool entry; **class loader mới** tạo class/linkage state mới.
- **Lỗi từ target sau linkage** không phải linkage failure và không biến site thành failed.
- **Concurrency** có thể làm BSM chạy nhiều lần cạnh tranh ở lần link đầu, nhưng không làm cho retry tuần tự sau failure trở thành hợp lệ.
- Khi chẩn đoán, xem **cause chain, bytecode, bootstrap descriptor, CallSite type và class loader** thay vì chỉ lặp lại lời gọi.

**Tài liệu chính thức:**

- [JVMS Java SE 17 — `5.4.3 Resolution` và `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): định nghĩa lỗi resolution, hành vi sau khi resolve thất bại, tính độc lập của các `invokedynamic` instructions và cạnh tranh bootstrap.
- [Oracle Java SE 17 — `java.lang.invoke` package overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html): liên kết call site, timing, types, hành vi khi bootstrap ném exception và static arguments.
- [Oracle Java SE 17 — `BootstrapMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html): ý nghĩa lỗi và quan hệ với `LinkageError`.
- [Oracle Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): call site type, dynamic invoker và target.
- [Oracle Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html) và [`MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): phân biệt target bất biến và khả năng cập nhật target sau khi đã link.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-c` hiển thị bytecode, `-v` hiển thị thông tin constant pool và bootstrap metadata.
