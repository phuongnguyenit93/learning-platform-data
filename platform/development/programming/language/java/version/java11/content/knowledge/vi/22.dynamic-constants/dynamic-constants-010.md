# Java 11+ — Hằng số động: Giới hạn giữa khả năng class file với cú pháp Java

## 1. Vấn đề chính: JVM làm được không có nghĩa Java source viết trực tiếp được

Java 11 triển khai **JEP 309 — Dynamic Class-File Constants**, thường gọi tắt là **dynamic constant** hoặc **condy**. Đây là **tính năng của định dạng tệp `.class`, constant pool và cơ chế liên kết của JVM**, không phải một từ khóa hay biểu thức mới của ngôn ngữ Java.

Hai câu sau **khác nhau**:

1. **“JVM Java 11 có thể nạp một `.class` chứa `CONSTANT_Dynamic`.”** — Đúng, nếu class file hợp lệ, đúng version và các điều kiện liên kết/kiểu được thỏa.
2. **“Java 11 có cú pháp như `dynamic const X = ...` để lập trình viên Java tạo trực tiếp entry đó.”** — Sai. Ngôn ngữ Java không có một cú pháp `condy` trực tiếp tương ứng.

Vì vậy, khi thấy tài liệu nói “Java 11 hỗ trợ dynamic constants”, phải hiểu đó là **khả năng của JVM và class file**, không phải thay đổi cú pháp Java trong `javac`.

Bài này phân biệt **compile-time constant của Java**, **trường `final`**, **hằng số động của JVM**, **`invokedynamic`**, trình bày layout `CONSTANT_Dynamic_info` và đưa ví dụ **thực sự tạo `.class` version 55**, không chỉ giả lập bootstrap bằng một lời gọi Java thông thường. Mọi ví dụ dựa trên API và cơ chế vẫn được hỗ trợ trong các JDK hiện đại, không sử dụng thư viện nội bộ `jdk.internal.*`.

## 2. Ba tầng phải phân biệt

| Tầng | Định nghĩa cái gì? | Có gì trong bài này? |
| --- | --- | --- |
| **Java language / Java source** | Cú pháp, kiểu, biểu thức, `final`, điều kiện một biến là *constant variable*, quy tắc biểu thức hằng tại compile time. | `static final String TEXT = "hello";` hoặc `static final String TEXT = new String("hello");` là mã Java hợp lệ, nhưng hai cách có đặc tính khác nhau. |
| **Java compiler / build tools** | Dịch source hoặc sinh/chỉnh bytecode theo target class file; trình biên dịch có quyền chọn biểu diễn phù hợp đặc tả. | `javac --release 11` tạo class file dành cho Java 11, **không** cho phép cú pháp condy mới. Một bytecode generator có thể tạo `CONSTANT_Dynamic`. |
| **JVM / JVMS class-file format** | Constant pool entries, bytecode `ldc`/`ldc_w`/`ldc2_w`, `BootstrapMethods`, resolution và caching. | `CONSTANT_Dynamic` **tag 17**, bắt đầu từ **class file 55.0 / Java 11**. |

**Class file không phải mã nguồn Java đã được viết lại dưới dạng nhị phân một-một.** Định dạng JVM có những khả năng mà Java source không đặt một cú pháp trực tiếp vào tay lập trình viên; một class file hợp lệ có thể được tạo bởi Kotlin, Scala, công cụ sinh bytecode, compiler optimization hoặc một chương trình ghi bytes đúng JVMS.

Ngược lại, dù class file có thể chứa một cấu trúc, không có nghĩa `javac` sẽ tự sinh cấu trúc đó cho một đoạn source Java cụ thể. Chi tiết biểu diễn mà không được Java Language Specification bảo đảm không nên trở thành “hợp đồng” ứng dụng.

## 3. `final`, *constant variable* và `CONSTANT_Dynamic` không tương đương

### 3.1. `final` là quy tắc ngôn ngữ, không phải condy

Ví dụ:

```java
public class SourceConstantDemo {
    public static final String COMPILE_TIME = "Hello " + "Java";
    public static final String RUNTIME = new String("Hello Java");

    public static void main(String[] args) {
        System.out.println("compile-time=" + COMPILE_TIME);
        System.out.println("run-time=" + RUNTIME);
    }
}
```

Cả hai trường đều `static final`, nhưng chúng không cùng là **constant variable** theo JLS:

- `COMPILE_TIME` có kiểu `String`, được khai báo `final` và khởi tạo bằng một **constant expression** (`"Hello " + "Java"`). Đây là **constant variable** theo định nghĩa của Java.
- `RUNTIME` khởi tạo bằng `new String(...)`. Đây **không** phải constant expression nên **không** là constant variable, dù tham chiếu field sau khi khởi tạo không thể gán lại từ Java thông thường.

Chạy bằng JDK 11 trở lên:

```bash
javac --release 11 SourceConstantDemo.java
java SourceConstantDemo
javap -v SourceConstantDemo
```

**Stdout từ `java SourceConstantDemo` đã kiểm chứng:**

```text
compile-time=Hello Java
run-time=Hello Java
```

`javap -v` đã xác nhận class file version **55** và:

- Trường `COMPILE_TIME` có attribute **`ConstantValue: String Hello Java`**.
- Trường `RUNTIME` được gán trong mã khởi tạo lớp bằng bytecode như `putstatic`; nó không có cùng attribute `ConstantValue`.
- Class được `javac` sinh ra có thể chứa **`InvokeDynamic`** cho nối chuỗi runtime; điều đó **không phải** `CONSTANT_Dynamic`. Hai tag này khác nhau.

Đừng dùng `final` như một tín hiệu suy ra constant pool sẽ có `CONSTANT_Dynamic`. **`ConstantValue`**, `CONSTANT_String` và `CONSTANT_Dynamic` là những cấu trúc khác nhau với quy tắc riêng. Một số *constant variable* có thể được inline vào bytecode của lớp sử dụng; việc thay giá trị sau khi compile có rủi ro tương thích nhị phân — đây là vấn đề ngôn ngữ/biên dịch khác với condy.

### 3.2. Gọi hàm tính giá trị lúc chạy vẫn chưa phải condy

Ví dụ:

```java
static final String TOKEN = computeToken();

static String computeToken() {
    return "T-001";
}
```

Đây chỉ là **một field `static final` khởi tạo lúc class initialization**, không phải một entry `CONSTANT_Dynamic`. Tương tự, gọi `ConstantBootstraps.nullConstant(...)` trực tiếp trong source Java cũng chỉ là **method invocation Java thông thường**, không chứng minh JVM đã resolution một condy từ constant pool.

**Tiêu chuẩn xác nhận condy:** dùng `javap -v` hoặc công cụ class-file reader để thấy entry `Dynamic`/`CONSTANT_Dynamic`, cùng `BootstrapMethods`, rồi quan sát bytecode tham chiếu entry đó.

## 4. Cấu trúc của `CONSTANT_Dynamic_info` trong class file

Theo JVMS `4.4.10`:

```text
CONSTANT_Dynamic_info {
    u1 tag;                            // 17
    u2 bootstrap_method_attr_index;    // Index trong BootstrapMethods
    u2 name_and_type_index;           // Index CONSTANT_NameAndType
}
```

Ý nghĩa:

- **`tag = 17`** là `CONSTANT_Dynamic`, bắt đầu hợp lệ từ **major version 55** (Java 11).
- **`bootstrap_method_attr_index`** là **chỉ số 0-based** vào mảng `bootstrap_methods[]` của attribute `BootstrapMethods`, **không phải** index trực tiếp tới một method trong Java.
- **`name_and_type_index`** trỏ đến `CONSTANT_NameAndType`, chứa tên được dùng cho bootstrap và **field descriptor** biểu diễn **kiểu của giá trị hằng**. Ví dụ `GREETING:Ljava/lang/String;`.
- `BootstrapMethods` chứa tham chiếu `CONSTANT_MethodHandle` tới bootstrap method và các **static bootstrap arguments** có thể có.
- Khi JVM resolve entry `Dynamic`, nó gọi bootstrap method để tính ra một giá trị khớp kiểu đã khai báo.

Giá trị dynamic constant có thể là kiểu nguyên thủy hoặc kiểu tham chiếu theo field descriptor thích hợp; không giới hạn chỉ `String`. Nếu descriptor `J` hoặc `D` tương ứng `long`/`double`, bytecode phải dùng **`ldc2_w`** thay vì `ldc`/`ldc_w`. Đối với các kiểu khác, `ldc` hoặc `ldc_w` phụ thuộc độ rộng chỉ số constant pool. `ldc` mang một index một byte, `ldc_w` mang index hai byte.

Một entry `CONSTANT_Dynamic` cũng có thể được dùng làm **static argument** cho một bootstrap method khác, không chỉ từ `ldc`. Đây là nền tảng cho cách tổ chức hằng số được tính khi resolve, nhưng không phải một tính năng mà Java source có cách ghi trực tiếp.

### `BootstrapMethods` phải có và được tạo đúng

Theo JVMS `4.7.23`, một class file chứa `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic` phải có đúng một attribute `BootstrapMethods` ở cấp class. Một entry đơn giản có thể được biểu diễn:

```text
BootstrapMethods:
  0: REF_invokeStatic CondyBootstrap.resolve(...)
     Method arguments: (none)
```

Ở đây, `REF_invokeStatic` là loại method handle trỏ tới static bootstrap method. Ví dụ ở mục 8 viết một entry với **0 static arguments**; ba tham số `Lookup, String, Class` vẫn được JVM tự cung cấp.

Không được xem `BootstrapMethods` như một danh sách lệnh Java sẽ chạy khi nạp mọi class: bootstrap của dynamic constant được resolve khi cần, **không mặc nhiên chạy khi class được load**.

## 5. Bootstrap method: Java source định nghĩa hành vi, class file kích hoạt nó

Với một dynamic constant kiểu `String`, bootstrap method có thể có chữ ký:

```java
public static String resolve(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type) {
    return "Hello from condy";
}
```

Đây chỉ là **phương thức Java bình thường**. JVM biết dùng nó làm condy bootstrap vì **class file `CondyGenerated.class` tham chiếu method handle của nó trong `BootstrapMethods` và `CONSTANT_Dynamic`**.

Ba tham số quan trọng:

1. **`MethodHandles.Lookup`**: ngữ cảnh truy cập của **class đang resolution constant**; không nên dùng tùy tiện để bypass access control.
2. **`String name`**: tên từ entry `CONSTANT_NameAndType`; ví dụ `GREETING`.
3. **`Class<?> type`**: kiểu mà descriptor dynamic constant yêu cầu; ở đây là `String.class`.
4. Nếu có static bootstrap arguments, JVM đặt thêm các giá trị đó sau các tham số trên. Bootstrap method handle phải thích nghi được với danh sách đối số theo quy tắc của `MethodHandle`.

Với `CONSTANT_InvokeDynamic`, tham số thứ ba của bootstrap thông thường là **`MethodType`**, và kết quả phải tạo được **`CallSite`**. Với `CONSTANT_Dynamic`, tham số thứ ba là **`Class`** và kết quả là **giá trị của constant**, không phải call site. Đừng copy chữ ký bootstrap cho `invokedynamic` sang condy mà không điều chỉnh.

Khi bootstrap trả kiểu không phù hợp với descriptor, trả giá trị không hợp lệ hoặc resolution thất bại, JVM báo lỗi liên kết phù hợp, thường có **`BootstrapMethodError`** đối với ngoại lệ không phải `Error` được bootstrap ném. Bootstrap có tham số/handle không đúng hay class file hỏng có thể gây các lỗi liên kết, format hoặc verification khác nhau; không cần catch tất cả như lỗi nghiệp vụ rồi bỏ qua.

## 6. Caching và thời điểm tính: “hằng” không phải “tính ở compile time”

Một dynamic constant ban đầu là symbolic reference **chưa resolve**. Khi mã bytecode cần dùng giá trị, JVM thực hiện resolution:

```text
Class file có CONSTANT_Dynamic
                 |
                 | class load / verify / link theo JVM
                 v
    Entry dynamic chưa được resolve
                 |
                 | ldc (hoặc làm bootstrap argument)
                 v
  Resolve method handle + name/type + static args
                 |
                 v
         Gọi bootstrap method
                 |
                 v
     Kiểm tra kiểu kết quả phù hợp
                 |
                 v
    Cache kết quả resolution tại JVM
                 |
            Sử dụng lại
```

**Phân biệt ba thời điểm:**

- **Compile time của Java:** `javac` xử lý source/constant expression và sinh bytecode. Bootstrap condy **không** phải cú pháp Java nên không do `javac` tính “hộ” từ một biểu thức condy viết trong source.
- **Class loading/verification:** JVM đọc và kiểm tra class file; nhìn thấy `CONSTANT_Dynamic` **không** có nghĩa bootstrap nhất định chạy ngay.
- **Resolution/first use:** khi cần giá trị dynamic, JVM resolve entry; kết quả được **cache** làm giá trị hằng cho symbolic reference của runtime constant pool đó.

### Một lưu ý quan trọng về concurrency

Đừng phát biểu “bootstrap method **luôn** được gọi đúng một lần trên toàn chương trình”. JVMS cho phép **nhiều thread đồng thời cùng thực hiện resolution** một dynamic constant chưa được resolve: bootstrap **có thể bị gọi đồng thời nhiều lần**, nhưng JVM chọn **một kết quả** làm giá trị resolution dùng chung và bỏ qua những kết quả khác. Vì vậy:

- Bootstrap nên **an toàn với concurrency**, ưu tiên tính toán không có side effect hoặc idempotent.
- Không dùng bootstrap làm hệ thống phát hành giao dịch phải “exactly once”.
- Kết quả đã được chọn và cache sẽ được tái sử dụng cho lần dùng tiếp theo của cùng symbolic reference.
- Nếu lần resolution thất bại, các lần thử tiếp theo cũng thất bại theo quy tắc cache resolution; không dựa vào việc sửa biến môi trường rồi `ldc` tự “thử lại”.
- Giá trị cache là **constant value**, không phải lời hứa object được bootstrap trả ra là immutable. Nếu trả một đối tượng mutable, code ứng dụng vẫn có thể sửa **trạng thái của đối tượng đó** qua tham chiếu.

Thí nghiệm trong mục 8 chỉ thực hiện **một luồng tuần tự**, nên dòng `bootstrap-calls=1` là kết quả chính xác **của thí nghiệm**, không phải luật tổng quát tuyệt đối cho tất cả tình huống cạnh tranh.

## 7. Ranh giới với `invokedynamic`, `ConstantValue` và string concatenation

| Đặc điểm | `CONSTANT_Dynamic` / condy | `CONSTANT_InvokeDynamic` | `ConstantValue` của field |
| --- | --- | --- | --- |
| Nằm ở đâu? | Entry trong constant pool (tag **17**). | Entry trong constant pool (tag **18**). | Attribute của `field_info`. |
| Ra đời | Java 11 / class file **55.0**. | Java 7 / class file **51.0**. | Đã có từ class file cổ điển. |
| Mục đích | Resolve **một giá trị hằng** dựa trên bootstrap. | Liên kết **một call site** qua bootstrap. | Gán giá trị constant expression vào `static` field. |
| Tham số thứ ba bootstrap thông thường | `Class<?>` cho field descriptor. | `MethodType` cho method descriptor. | Không dùng bootstrap. |
| Kết quả | Một giá trị của kiểu đã khai báo. | `CallSite` thích hợp. | Giá trị hằng thuộc các loại JVMS cho phép. |
| Bytecode liên quan | `ldc`/`ldc_w`/`ldc2_w` hoặc bootstrap arguments. | `invokedynamic`. | Không cần một `ldc` condy để định nghĩa attribute đó. |
| Có cú pháp Java condy trực tiếp? | **Không**. | Không có từ khóa trực tiếp, nhưng `javac` có thể dùng `invokedynamic` để triển khai biểu thức Java. | Java có cú pháp literal/constant expression, nhưng attribute là kết quả dịch. |

**Ví dụ dễ gây nhầm:** từ Java 9 trở đi, `javac` có thể dùng `invokedynamic` với `StringConcatFactory` để thực hiện phép nối chuỗi lúc chạy. Vì thế thấy từ **`InvokeDynamic`** trong `javap -v` của một Java class **không** chứng minh class đó có condy. Ngược lại, `CONSTANT_Dynamic` không phải lệnh gọi động và không yêu cầu phương thức có `CallSite`.

**Giới hạn của `ConstantValue`:** JVMS `4.7.2` chỉ cho phép các constant pool entry theo danh sách kiểu cho field được định nghĩa trong attribute này; không tự thay một entry trong `ConstantValue` bằng `CONSTANT_Dynamic` rồi mong JVM khởi tạo field. Nếu một bytecode generator muốn lưu kết quả condy vào `static` field, nó có thể sinh **mã `<clinit>`** dùng `ldc` condy rồi `putstatic` theo đúng quy tắc verifier.

## 8. Ví dụ Java 11 chạy được: tự sinh class file chứa `CONSTANT_Dynamic`

Đây là phần chứng minh trực tiếp **“class file làm được, Java source không có cú pháp tương đương”**. Ta viết hai tệp **Java source hợp lệ**:

- `CondyBootstrap.java`: định nghĩa bootstrap method bằng Java thuần.
- `CondyWriter.java`: dùng `DataOutputStream` ghi **class file version 55** với một constant pool entry **tag 17**, method handle tới bootstrap và hai bytecode `ldc` đều tham chiếu **cùng một entry**.

Sau khi chạy writer sẽ có **`CondyGenerated.class`**. Không có `CondyGenerated.java`: class này được tạo trực tiếp theo **định dạng JVM**, không phải bằng một cú pháp source condy. `java CondyGenerated` chạy bytecode đó; `javap -v CondyGenerated` dùng để kiểm tra.

**Giới hạn ví dụ:** viết class file bằng tay chỉ dành cho học format. Trong dự án thật, nên dùng một **bytecode library được duy trì/được dự án phê duyệt**, cung cấp API tạo `ConstantDynamic` tương ứng, và test compatibility của class file. Không dùng các lớp `jdk.internal.org.objectweb.asm.*` để viết sản phẩm vì chúng là API nội bộ không được bảo đảm.

### 8.1. Tệp thứ nhất — `CondyBootstrap.java`

```java
import java.lang.invoke.MethodHandles;

public final class CondyBootstrap {
    private static int count;

    public static String resolve(
            MethodHandles.Lookup caller, String name, Class<?> type) {
        if (type != String.class || !"GREETING".equals(name)) {
            throw new IllegalArgumentException("Unexpected constant");
        }
        count++;
        System.out.println("bootstrap-calls=" + count);
        return "Hello from condy";
    }
}
```

Bootstrap này kiểm tra name/type, tăng biến đếm và trả về chuỗi. **Không dùng biến đếm không đồng bộ này trong bootstrap production**: nó chỉ giúp quan sát số lần gọi của demo **chạy tuần tự**.

### 8.2. Tệp thứ hai — `CondyWriter.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class CondyWriter {
    interface Entry { void write(DataOutputStream out) throws IOException; }
    static final List<byte[]> POOL = new ArrayList<>();

    static int add(Entry entry) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream d = new DataOutputStream(bytes)) {
            entry.write(d);
        }
        POOL.add(bytes.toByteArray());
        return POOL.size();
    }

    static int utf(String s) throws IOException {
        return add(d -> { d.writeByte(1); d.writeUTF(s); });
    }
    static int clazz(int name) throws IOException {
        return add(d -> { d.writeByte(7); d.writeShort(name); });
    }
    static int nat(int name, int desc) throws IOException {
        return add(d -> {
            d.writeByte(12); d.writeShort(name); d.writeShort(desc);
        });
    }
    static int methodRef(int owner, int nat) throws IOException {
        return add(d -> {
            d.writeByte(10); d.writeShort(owner); d.writeShort(nat);
        });
    }
    static int fieldRef(int owner, int nat) throws IOException {
        return add(d -> {
            d.writeByte(9); d.writeShort(owner); d.writeShort(nat);
        });
    }
    static int methodHandle(int kind, int reference) throws IOException {
        return add(d -> {
            d.writeByte(15); d.writeByte(kind); d.writeShort(reference);
        });
    }
    static int dynamic(int bootstrapIndex, int nat) throws IOException {
        return add(d -> {
            d.writeByte(17); d.writeShort(bootstrapIndex); d.writeShort(nat);
        });
    }

    static void writeMethod(DataOutputStream out, int flags, int name,
                            int descriptor, int codeName, int maxStack,
                            int maxLocals, byte[] code) throws IOException {
        out.writeShort(flags);
        out.writeShort(name);
        out.writeShort(descriptor);
        out.writeShort(1);            // attributes_count
        out.writeShort(codeName);     // Code attribute name
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(maxLocals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0);            // exception_table_length
        out.writeShort(0);            // Code attributes_count
    }

    static byte[] initCode(int objectInit) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream d = new DataOutputStream(bytes);
        d.writeByte(0x2a);            // aload_0
        d.writeByte(0xb7);            // invokespecial
        d.writeShort(objectInit);
        d.writeByte(0xb1);            // return
        return bytes.toByteArray();
    }

    static byte[] mainCode(int outField, int constant, int printMethod)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream d = new DataOutputStream(bytes);
        for (int i = 0; i < 2; i++) {
            d.writeByte(0xb2);        // getstatic System.out
            d.writeShort(outField);
            d.writeByte(0x12);        // ldc: constant-pool index one byte
            d.writeByte(constant);
            d.writeByte(0xb6);        // invokevirtual println(String)
            d.writeShort(printMethod);
        }
        d.writeByte(0xb1);            // return
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        int thisName = utf("CondyGenerated");
        int thisClass = clazz(thisName);
        int objectName = utf("java/lang/Object");
        int objectClass = clazz(objectName);
        int constructorName = utf("<init>");
        int constructorDesc = utf("()V");
        int initNt = nat(constructorName, constructorDesc);
        int objectInit = methodRef(objectClass, initNt);
        int codeName = utf("Code");
        int mainName = utf("main");
        int mainDesc = utf("([Ljava/lang/String;)V");
        int systemName = utf("java/lang/System");
        int systemClass = clazz(systemName);
        int outName = utf("out");
        int outDesc = utf("Ljava/io/PrintStream;");
        int outNt = nat(outName, outDesc);
        int outField = fieldRef(systemClass, outNt);
        int streamName = utf("java/io/PrintStream");
        int streamClass = clazz(streamName);
        int printName = utf("println");
        int printDesc = utf("(Ljava/lang/String;)V");
        int printNt = nat(printName, printDesc);
        int printMethod = methodRef(streamClass, printNt);
        int bootstrapClassName = utf("CondyBootstrap");
        int bootstrapClass = clazz(bootstrapClassName);
        int resolveName = utf("resolve");
        int resolveDesc = utf("(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;");
        int resolveNt = nat(resolveName, resolveDesc);
        int resolveMethod = methodRef(bootstrapClass, resolveNt);
        int handle = methodHandle(6, resolveMethod); // REF_invokeStatic
        int constantName = utf("GREETING");
        int constantDesc = utf("Ljava/lang/String;");
        int constantNt = nat(constantName, constantDesc);
        int constant = dynamic(0, constantNt);
        int bootstrapAttr = utf("BootstrapMethods");

        if (constant > 255) throw new IllegalStateException("Use ldc_w");

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream d = new DataOutputStream(bytes);
        d.writeInt(0xCAFEBABE);
        d.writeShort(0);             // minor version
        d.writeShort(55);            // major version: Java 11
        d.writeShort(POOL.size() + 1);
        for (byte[] entry : POOL) d.write(entry);
        d.writeShort(0x0021);        // public, super
        d.writeShort(thisClass);
        d.writeShort(objectClass);
        d.writeShort(0);             // interfaces
        d.writeShort(0);             // fields
        d.writeShort(2);             // methods
        writeMethod(d, 0x0001, constructorName, constructorDesc,
                codeName, 1, 1, initCode(objectInit));
        writeMethod(d, 0x0009, mainName, mainDesc,
                codeName, 2, 1, mainCode(outField, constant, printMethod));
        d.writeShort(1);             // class-level attributes_count
        d.writeShort(bootstrapAttr);
        d.writeInt(6);
        d.writeShort(1);             // num_bootstrap_methods
        d.writeShort(handle);
        d.writeShort(0);             // no static bootstrap arguments
        d.flush();

        Files.write(Path.of("CondyGenerated.class"), bytes.toByteArray());
        System.out.println("classfile-major=55");
    }
}
```

Cấu trúc này **cố ý có số ít entries** để chỉ số của `ldc` nhỏ hơn 256, không cần xử lý index rộng trong demo. Các giá trị tag 1/7/9/10/12/15/17 và opcode 0x12/0xb2/0xb6 đều thuộc class-file/bytecode format do JVMS quy định. `DataOutputStream.writeUTF` được dùng cho các entry UTF8 trong ví dụ vì mọi chuỗi constant pool ở đây đều là ASCII, tương thích cách ghi cần thiết của entry đó.

### 8.3. Lệnh chạy

Đặt **hai tệp source** vào cùng một thư mục thử nghiệm trống và chạy:

```bash
javac -encoding UTF-8 --release 11 CondyBootstrap.java CondyWriter.java
java CondyWriter
javap -v CondyGenerated
java CondyGenerated
```

Lệnh `java CondyWriter` ghi thêm `CondyGenerated.class` ở thư mục hiện tại. `javap -v` đọc class đó; `java CondyGenerated` thực thi generated class bằng JVM.

**Stdout xác định từ hai lệnh chạy Java, đã kiểm chứng:**

```text
classfile-major=55
bootstrap-calls=1
Hello from condy
Hello from condy
```

Dòng đầu do `java CondyWriter` in; ba dòng cuối do `java CondyGenerated` in. `javap -v` có output cấu trúc dài hơn và không nằm trong khối stdout bốn dòng trên.

**Các dấu hiệu từ `javap -v CondyGenerated` đã được kiểm chứng:**

```text
major version: 55
#34 = Dynamic  #0:#33  // #0:GREETING:Ljava/lang/String;
3: ldc  #34             // Dynamic #0:GREETING:Ljava/lang/String;
11: ldc #34             // Dynamic #0:GREETING:Ljava/lang/String;
BootstrapMethods:
```

Số index có thể thay đổi nếu thay thứ tự constant pool trong generator, nhưng với source này, hai lệnh `ldc` đều tham chiếu **`#34`**. Kết quả runtime tuần tự là:

1. Lần `ldc #34` đầu kích hoạt resolution `CONSTANT_Dynamic`.
2. JVM tìm bootstrap method handle `CondyBootstrap.resolve` từ `BootstrapMethods[0]`.
3. JVM truyền `Lookup` của class yêu cầu, tên `"GREETING"` và kiểu `String.class` cho bootstrap.
4. Bootstrap in `bootstrap-calls=1` và trả `"Hello from condy"`.
5. JVM cache kết quả; cả hai `println` in cùng chuỗi và không cần tính lại khi đọc cùng entry tuần tự lần hai.

Đây là ví dụ **condy thật**: `javac` chỉ biên dịch **bootstrap** và **writer** Java bình thường; writer mới tạo một **class file tag 17**. Không có một dòng Java source kiểu `dynamic const` được `javac` hiểu.

## 9. Khả năng class file cho phép nhiều hơn demo

Ví dụ dùng `String` vì dễ quan sát, nhưng khả năng JVMS rộng hơn:

| Khả năng | Trường hợp thực tế |
| --- | --- |
| Kiểu nguyên thủy hoặc tham chiếu | Condy descriptor có thể là field descriptor của `int`, `long`, `String`, class/array... Kết quả bootstrap phải tương thích kiểu. |
| Giá trị tham chiếu `null` | Dynamic constant kiểu tham chiếu có thể resolve thành `null`, khác với một literal keyword `null` trong Java source; `ConstantBootstraps.nullConstant` là helper chuẩn. |
| Static bootstrap arguments | Metadata, class/method handle, dynamic constants khác có thể tham gia tính giá trị khi resolve. |
| Hằng số làm bootstrap argument | Một condy có thể là đối số tĩnh cho bootstrap của condy/`invokedynamic` khác, theo quy tắc resolution. |
| Bootstrap helpers chính thức | `java.lang.invoke.ConstantBootstraps` cung cấp `nullConstant`, `primitiveClass`, `enumConstant`, `getStaticFinal`, các helper `VarHandle`/`invoke` được tài liệu hóa trong Java 11. |
| Lazy resolution | Giá trị được tạo khi JVM cần resolve symbolic reference; không bắt buộc tính khi compile hoặc load class. |
| Cache thành công/thất bại | Resolution được JVM duy trì; không coi việc nhiều lần `ldc` là nhiều lần chạy nghiệp vụ bootstrap. |

**Cẩn thận với version API:** tập phương thức của `ConstantBootstraps` có thể được bổ sung giữa các phiên bản Java. Khi viết code có `--release 11`, chỉ dùng các overload **thật sự có trong Java 11**, không nhìn Javadoc mới rồi mặc định compile được trên 11.

**Không đặt bí mật vào constant pool:** data trong class file có thể bị trích xuất, và bootstrap có thể ghi log, có side effect hoặc không được kiểm soát. Condy không phải trình quản lý secrets, không cấp tính bất biến sâu, không phải mã hóa dữ liệu và không cho phép bypass access checks.

### Giới hạn với constant phụ thuộc môi trường

Một bootstrap đọc `System.getenv(...)` hoặc file cấu hình có thể tạo một giá trị **được cache khi resolution**, không phải một biến “sống” tự cập nhật khi môi trường thay đổi. Nếu ứng dụng cần config refresh, feature flags động hoặc key rotation, nên dùng một cấu hình runtime được quản lý thay vì giấu logic đó trong condy.

Bootstrap lỗi sẽ khiến lần sử dụng constant thất bại; class file vẫn có thể load trước đó. Vì vậy bootstrap phải dễ chẩn đoán và không thực hiện network I/O/blocking dài trong đường liên kết lớp nếu không có thiết kế rõ ràng.

## 10. Những giới hạn thực tế của việc sinh/chỉnh bytecode

Người tạo condy không chỉ viết một số tag vào class file:

1. **Đúng major version**: `CONSTANT_Dynamic` yêu cầu class file **55.0 trở lên**. Nếu cần chạy Java 8 hoặc Java 10, không thể dùng trực tiếp class này; đổi `--release` cho một Java file khác không “hạ cấp” được một class chứa tag 17.
2. **Đúng `BootstrapMethods`** và method handle hợp lệ. Class file có entries dynamic/invokedynamic phải tuân theo quy định về một attribute này.
3. **Đúng NameAndType**: condy cần **field descriptor**, không phải method descriptor.
4. **Đúng bytecode**: dùng `ldc`/`ldc_w`/`ldc2_w` theo kiểu dữ liệu và độ rộng index; giá trị trên operand stack phải khớp verifier.
5. **Đúng quyền truy cập**: bootstrap method, kiểu liên quan và những members được lookup phải đáp ứng access control.
6. **Đúng kiểu kết quả**: `Class<?>` mà JVM cung cấp là kiểu của constant; handle/bootstrap phải tạo được giá trị tương thích.
7. **Đúng lifecycle/resolution**: không chạy side effects phụ thuộc “bootstrap đúng một lần toàn JVM” trong trường hợp concurrency hoặc nhiều class loaders.
8. **Đúng error handling**: khi class file sai format, JVM có thể ném `ClassFormatError`; bytecode/stack type không hợp lệ có thể dẫn đến `VerifyError`; bootstrap/linkage sai có thể dẫn đến `BootstrapMethodError` hoặc lỗi phù hợp.
9. **Kiểm tra bằng `javap -v` và runtime thật**: chỉ có một tệp `.class` tồn tại hoặc một method `resolve` trong source **chưa** phải bằng chứng condy.
10. **Không phụ thuộc API nội bộ của JDK** để sinh bytecode. Dùng công cụ bytecode hiện hành do dự án quản lý, version hỗ trợ tag 17 và kiểm thử thực tế.

Nếu cần chạy trên cả Java 8/11, dùng packaging theo chiến lược tương thích (ví dụ build variants/multi-release JAR khi phù hợp) và luôn kiểm tra base classes có format chạy được trên runtime tối thiểu. Không đưa một class file 55 vào đường chạy của Java 8 rồi kỳ vọng JVM cũ bỏ qua entry tag 17.

## 11. Hỏi đáp và những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Java 11 có cú pháp `condy`.” | Không: đây là tính năng **class file/JVM**, không có từ khóa source tương ứng. |
| “`--release 11` nghĩa là mọi class do `javac` tạo đều chứa condy.” | Không: chỉ định mục tiêu tương thích của compiler, không buộc sử dụng `CONSTANT_Dynamic`. |
| “`static final` luôn là dynamic constant.” | Không: `final`/constant variable/`ConstantValue` khác condy. |
| “Gọi `ConstantBootstraps.nullConstant()` trực tiếp là test condy.” | Không: chỉ là gọi phương thức; phải có entry tag 17 trong class file. |
| “`CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic` là hai tên một tính năng.” | Sai: tag **17** resolve **giá trị**; tag **18** resolve **call site**. |
| “Vì class có `invokedynamic`, Java source đã sử dụng condy.” | Không: nối chuỗi runtime hoặc lambda có thể dùng `invokedynamic` mà không có tag 17. |
| “Bootstrap chạy khi nạp class và chạy lại mỗi khi `ldc`.” | Không: resolution theo nhu cầu, kết quả được cache. |
| “Bootstrap luôn gọi đúng một lần ở mọi thread/class loader.” | Không: concurrent resolution có thể gọi bootstrap nhiều lần, chỉ một kết quả được chọn/cached cho reference. |
| “Dùng condy là có một object bất biến.” | Không: reference đã resolve ổn định, trạng thái object trả về vẫn có thể mutable. |
| “Một condy chỉ dùng để tải chuỗi.” | Không: dùng được nhiều field descriptor và bootstrap arguments theo JVMS. |
| “`BootstrapMethods` là bytecode Java tự chạy như `main`.” | Không: đó là metadata cho JVM resolution theo nhu cầu. |
| “Tham số thứ ba của mọi bootstrap đều là `MethodType`.” | Condy thường nhận `Class<?>`; `invokedynamic` nhận `MethodType`. |
| “Class file 55 chạy bình thường trên Java 8.” | Không: runtime cũ không hỗ trợ class format/constant tag đó. |
| “Có thể dùng `CONSTANT_Dynamic` như `ConstantValue` field attribute.” | Hai cấu trúc khác nhau; field có thể được gán trong `<clinit>` bằng `ldc` condy. |
| “Một bootstrap đọc config sẽ tự reload khi file config đổi.” | Không: kết quả resolution được cache, không phải live value. |
| “Không có cú pháp Java nghĩa là JVM không có tính năng đó.” | Không: bytecode generator hoặc compiler ngôn ngữ khác có thể tận dụng nó. |

## 12. Checklist thực hành

1. Khi nghe “Java 11 có hằng số động”, hỏi rõ **source Java**, **compiler** hay **class file/JVM** đang được nói đến.
2. Nhớ **JEP 309**, `CONSTANT_Dynamic` **tag 17**, class file **55.0**, `BootstrapMethods` và `ldc`.
3. Phân biệt `CONSTANT_Dynamic` với `CONSTANT_InvokeDynamic` **tag 18**, `ConstantValue` và `final` của Java.
4. Kiểm tra bootstrap method nhận `MethodHandles.Lookup`, `String`, `Class<?>` cùng static args thích hợp, trả kiểu khớp descriptor.
5. Khi sinh bytecode, dùng công cụ được hỗ trợ hoặc generator thử nghiệm theo JVMS, không đưa code bằng tay của mục 8 vào production.
6. Biên dịch/test với target Java 11; chạy `javap -v` để thấy entry `Dynamic`, không suy ra từ tên phương thức hoặc keyword Java.
7. Kiểm tra kết quả và caching ở runtime, hiểu **concurrent resolution** có thể invoke bootstrap hơn một lần.
8. Đừng dùng bootstrap để quản lý secrets, live config, transactions exactly once hoặc thao tác blocking không được kiểm soát.
9. Có test class loader, quyền truy cập, kiểu constant, lỗi bootstrap và runtime tương thích.
10. Nếu mục tiêu chỉ là viết code ứng dụng thông thường với cấu hình/lazy init, dùng cấu trúc Java phù hợp (field, static initializer, lazy holder, supplier) thay vì ép dùng condy.

### Tài liệu tham khảo chính thức và hiện hành

- [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309)
- [JVMS Java SE 11 `4.4.10 — `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10)
- [JVMS Java SE 11 `4.7.23 — `BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23)
- [JVMS Java SE 11 `5.4.3.6 — resolution và bootstrap invocation](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS Java SE 11 `4.7.2 — `ConstantValue` field attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.2)
- [Java SE 11 `java.lang.invoke` package summary — dynamic constants và caching](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html)
- [Java SE 11 `ConstantBootstraps` — các bootstrap helpers](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html)
- [JVMS Java SE 25 `4 — constant pool tag 17 vẫn được hỗ trợ](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.4.10)
