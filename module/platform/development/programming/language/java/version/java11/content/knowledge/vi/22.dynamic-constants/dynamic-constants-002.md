# Phân biệt `CONSTANT_Dynamic` (dynamic constant) và `invokedynamic` trong JVM (Java 11+)

## 1. Mục tiêu bài học

Hai tính năng JVM dễ bị nhầm vì **đều dùng bootstrap method** và đều trì hoãn việc liên kết/phân giải cho đến khi cần:

- **Dynamic constant (condy):** mục `CONSTANT_Dynamic_info` trong *constant pool*. JVM dùng bootstrap để tạo **một giá trị** thuộc kiểu được khai báo, sau đó có thể đưa giá trị đó lên operand stack bằng `ldc`, `ldc_w` hoặc `ldc2_w`. Condy trở thành chuẩn ở **Java 11**, theo **JEP 309**.
- **Dynamic call site (indy):** mục `CONSTANT_InvokeDynamic_info` trong constant pool được tham chiếu bởi lệnh **`invokedynamic`**. JVM dùng bootstrap để tạo **một `CallSite`**, liên kết lệnh gọi với một `MethodHandle` làm target. `invokedynamic` đã xuất hiện từ **Java 7**, theo JSR 292, và vẫn được dùng rộng rãi trong JDK hiện đại.

**Câu nhớ nhanh:** *condy phân giải ra dữ liệu*, còn *indy liên kết ra hành vi gọi hàm*. Có chung cơ chế bootstrap, nhưng **kết quả, kiểu descriptor, opcode và đặc điểm thời gian chạy hoàn toàn khác nhau**.

Bài học đi từ khái niệm đến classfile thực tế, kèm chương trình Java 11 **tự tạo một classfile phiên bản 55** có cả tag 17 và tag 18, chạy chúng và dùng `javap -v` để kiểm chứng. Không cần thư viện ASM, không tải dữ liệu mạng và không chỉnh tùy chọn module nội bộ.

**Phạm vi hiện hành:** các quy tắc JVMS về `CONSTANT_Dynamic`/`CONSTANT_InvokeDynamic`, `BootstrapMethods`, `CallSite` và `MethodHandle` **vẫn còn áp dụng trong những JDK mới**; không dựa vào API đã legacy hay cấu trúc classfile lỗi thời.

## 2. Trước tiên: constant pool là gì?

File `.class` chứa bảng **`constant_pool`**, trong đó có những entry biểu diễn tên class/method/field, chuỗi, số, phương thức, method handles và các thông tin phục vụ liên kết bytecode. Có loại chứa **giá trị tĩnh**, có loại là **symbolic reference** cần resolution.

Ví dụ:

```text
ClassFile:
  magic             0xCAFEBABE
  major_version     55 (Java 11)
  constant_pool:
      #1   Utf8 ...
      #... Class ...
      #... NameAndType ...
      #... MethodHandle ...
      #20  Dynamic       #0:greeting:Ljava/lang/String;
      #24  Dynamic       #0:answer:J
      #28  InvokeDynamic #1:calculate:(I)I
  methods:
      getString() : String   -> ldc_w #20; areturn
      getLong()   : long     -> ldc2_w #24; lreturn
      call(int)   : int      -> iload_0; invokedynamic #28; ireturn
  attributes:
      BootstrapMethods:
          0 -> bootstrap tạo giá trị constant
          1 -> bootstrap tạo CallSite
```

Đây là cấu trúc **rút gọn**, không phải source Java biên dịch trực tiếp. Phần 8 cung cấp generator chạy độc lập và `javap` thật.

Lệnh `ldc` nạp giá trị từ constant pool. Lệnh `invokedynamic` liên kết một call site rồi gọi target. Cả hai đều có thể kích hoạt bootstrap, nhưng mục đích của các bootstrap khác nhau.

**Không nhầm:** tên “constant pool” không có nghĩa mọi entry đều là literal được xác định khi `javac` chạy. Với condy, giá trị có thể **tính trong JVM ở runtime** khi resolution diễn ra. Với indy, constant pool lưu **mô tả call site** để JVM liên kết lệnh gọi.

## 3. Bảng so sánh cốt lõi

| Tiêu chí | Dynamic constant — condy | `invokedynamic` — indy |
| --- | --- | --- |
| Constant-pool tag | **`CONSTANT_Dynamic` = 17** | **`CONSTANT_InvokeDynamic` = 18** |
| Có từ | **Java 11** (JEP 309, classfile 55.0) | **Java 7** (JSR 292, classfile 51.0) |
| Ý nghĩa | **Một hằng số/giá trị tính động** | **Một điểm gọi phương thức được liên kết động** |
| `NameAndType` descriptor | **Field descriptor**, ví dụ `Ljava/lang/String;`, `I`, `J` | **Method descriptor**, ví dụ `(I)I`, `(Ljava/lang/String;)V` |
| Bootstrap tham số kiểu | `(Lookup, String, Class<?>, ...)` | `(Lookup, String, MethodType, ...)` |
| Bootstrap kết quả | Một **giá trị** tương thích với kiểu constant | Một **`CallSite`** có target khớp method type |
| Bytecode tiêu biểu | `ldc`, `ldc_w`, `ldc2_w`; hoặc static bootstrap argument | `invokedynamic` |
| Mỗi lần thực thi bytecode | Nạp lại **giá trị đã phân giải** lên operand stack | **Gọi** target MethodHandle qua call site đã liên kết |
| Cache trạng thái | Giá trị được resolution chọn **ổn định** cho symbolic reference tương ứng | Liên kết **`CallSite`** được giữ; target có thể cố định hoặc thay đổi theo loại CallSite |
| Có thể nhận primitive? | Có: ví dụ `int`, `long`, `double` | Method descriptor có thể nhận/trả primitive như method bình thường |
| Dùng để làm gì? | Tạo literal phức tạp, constant từ metadata, static bootstrap arguments | Lambda, dynamic language dispatch, string concatenation, runtime linkage |
| Kết quả mô tả | `String`, `long`, `Class`, `MethodHandle`, ... | Invocation `MethodHandle` trả kiểu theo method descriptor |

**Đặc biệt:** tên `CONSTANT_InvokeDynamic` có từ “CONSTANT” vì đó là **dạng entry của constant pool**, **không** có nghĩa kết quả của lệnh gọi là một giá trị constant. Lệnh `invokedynamic` có thể trả kết quả khác nhau ở mỗi lần gọi, tùy input và target.

## 4. Hai cấu trúc trong classfile: giống hình dạng nhưng khác kiểu descriptor

Cả `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info` đều gồm tag, chỉ số đến `BootstrapMethods` và chỉ số `NameAndType`:

```text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}

CONSTANT_InvokeDynamic_info {
    u1 tag;                         // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

Mặc dù *cấu trúc byte tương tự*, `name_and_type_index` phải trỏ đến các descriptor khác:

```text
Dynamic:
  name = "greeting"
  descriptor = "Ljava/lang/String;"    // FIELD descriptor

InvokeDynamic:
  name = "calculate"
  descriptor = "(I)I"                  // METHOD descriptor: int -> int
```

Field descriptor xác định một kiểu dữ liệu JVM (trừ `void`). Method descriptor xác định **danh sách tham số và kiểu trả về**. Do đó sẽ sai nếu dùng `(I)I` cho một `CONSTANT_Dynamic` hoặc `Ljava/lang/String;` cho một `CONSTANT_InvokeDynamic`.

Một entry `BootstrapMethods` thường có:

```text
BootstrapMethods:
  bootstrap_method_ref    -> MethodHandle đến bootstrap method
  bootstrap_arguments[]   -> 0 hoặc nhiều loadable constants
```

Điểm cần hiểu:

- **Chỉ số bootstrap là chỉ số vào bảng `BootstrapMethods`, không phải constant-pool index trực tiếp.**
- Bootstrap method handle có thể trỏ tới static method phù hợp, thường được biểu diễn với `REF_invokeStatic` (reference kind 6).
- Nhiều condy/indy entries có thể **cùng tham chiếu một entry BootstrapMethods**, nhưng chúng vẫn là **các symbolic references khác nhau**. Nếu cùng một bootstrap được gọi cho hai condy entries, **giá trị không phải một cache dùng chung theo tên bootstrap**.
- Các **static bootstrap arguments** có thể truyền thêm loadable constants, bao gồm cả `CONSTANT_Dynamic`; JVM sẽ giải quyết những đối số cần thiết theo quy tắc resolution trước khi gọi bootstrap liên quan.

### 4.1. Classfile version quan trọng thế nào?

`CONSTANT_Dynamic` chỉ hợp lệ trong classfile **major version 55 trở lên** (Java 11+). `CONSTANT_InvokeDynamic` đã hợp lệ từ classfile **major 51** (Java 7+). Nếu đưa tag 17 vào file version cũ hơn, `ClassFormatError`/lỗi verify hoặc load là điều có thể xảy ra tùy trường hợp.

`javac --release 11` **không có cú pháp Java source để viết trực tiếp** một dòng `CONSTANT_Dynamic`. Để chủ động tạo condy, compiler/tool cần **sinh bytecode/classfile** (ví dụ ASM với phiên bản hỗ trợ condy hoặc generator chương trình tự viết). Ngược lại, `javac` có thể tự sinh `invokedynamic` cho lambda và phép nối chuỗi phù hợp.

## 5. Bootstrap method: tham số và kết quả khác nhau

### 5.1. Bootstrap cho condy

Mẫu thường gặp:

```java
public static Object constantBootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type) {
    if (type == String.class && name.equals("greeting")) {
        return "hello-condy";
    }
    if (type == long.class && name.equals("answer")) {
        return Long.valueOf(42);
    }
    throw new IllegalArgumentException(name + " : " + type);
}
```

Ba tham số chuẩn:

1. **`Lookup`:** năng lực lookup trong ngữ cảnh lớp chứa symbolic reference, có điều kiện truy cập tương ứng.
2. **`String name`:** tên logic trong `NameAndType`, ví dụ `greeting` hoặc `answer`.
3. **`Class<?> type`:** kiểu giá trị constant được khai báo. Với descriptor `J`, `type == long.class`.

Bootstrap có thể nhận thêm static arguments sau ba tham số đầu. Trả về giá trị phải tương thích với kiểu mong đợi; một constant reference có thể hợp lệ với `null` (theo kiểu reference), còn primitive phải có giá trị tương thích để JVM chuyển đổi/unbox theo quy tắc resolution.

**Không yêu cầu bắt buộc bootstrap là hàm không tham số**; dấu hiệu chính của condy là **`Class<?>`** của kiểu constant và **giá trị** trả về, không phải việc bootstrap method có tên gì.

Nếu bootstrap ném lỗi, trả sai kiểu hoặc recursion resolution không hợp lệ, resolution có thể thất bại, thường biểu hiện qua **`BootstrapMethodError`** hay một `LinkageError` khác theo trường hợp. Không giả định mọi lỗi bootstrap đều được bọc giống nhau: JVMS có những quy tắc riêng cho `Error` và exception.

### 5.2. Bootstrap cho indy

Mẫu tương ứng:

```java
public static CallSite callBootstrap(
        MethodHandles.Lookup lookup,
        String name,
        MethodType type) throws ReflectiveOperationException {
    MethodHandle target = lookup.findStatic(
            MyBootstrap.class, "twice", type);
    return new ConstantCallSite(target);
}
```

Đoạn trên là **minh họa**, yêu cầu định nghĩa `MyBootstrap.twice` và import đầy đủ; chương trình mục 8 có bootstrap runnable khác với `MutableCallSite`.

Ba tham số chuẩn:

1. **`Lookup`:** quyền truy cập của nơi thực hiện call site.
2. **`String name`:** tên logic của call site.
3. **`MethodType type`:** kiểu phương thức của call site, ví dụ `(int)int` tương ứng descriptor `(I)I`.

Bootstrap **phải trả `CallSite`** có target tương thích với descriptor của `invokedynamic`. Một `CallSite` thường bao quanh một `MethodHandle` và đại diện trạng thái liên kết của lệnh gọi. Nếu bootstrap chỉ trả một `String` hoặc `Integer` thì sai contract.

`CallSite` có các biến thể quan trọng:

- **`ConstantCallSite`:** target cố định sau khi tạo, hợp khi hành vi không cần đổi.
- **`MutableCallSite`:** target có thể đổi bằng `setTarget`; dùng `MutableCallSite.syncAll(...)` để thiết lập điều kiện nhìn thấy thay đổi theo cơ chế đã quy định.
- **`VolatileCallSite`:** target thay đổi với ngữ nghĩa volatile phù hợp cho trường hợp cần visibility khác.

**Đừng nhầm “constant” trong `ConstantCallSite` với `CONSTANT_Dynamic`.** `ConstantCallSite` vẫn đại diện **một lệnh gọi**, chỉ có target method handle ổn định; nó không tạo một giá trị condy.

## 6. Quá trình resolution, cache và thời điểm chạy

### 6.1. Con đường của một condy

```text
bytecode: ldc_w #CONSTANT_Dynamic
                   |
                   v
 symbolic reference chưa resolved?
                   |
                 Có
                   |
          resolve bootstrap handle
          resolve static bootstrap args
          call BSM(Lookup, String, Class, ...)
                   |
          xác minh kiểu giá trị trả về
                   |
          chọn/cache một resolved value
                   |
                   v
          đẩy value lên operand stack
```

Sau resolution thành công, các lần `ldc_w` tiếp theo dùng **resolved constant value**, không thực hiện lại phép tính bootstrap để tạo object mới ở mỗi `ldc`.

**Quan trọng về đa luồng:** JVMS cho phép hai thread tranh chấp resolution có thể cùng chạy bootstrap nhiều lần; JVM chọn **một kết quả** để cài đặt, những kết quả khác bị bỏ qua. Vì vậy không dùng bootstrap có side effect không-idempotent rồi giả định “bootstrap method chạy đúng một lần toàn JVM”.

**Đơn vị cache:** gắn với symbolic reference của một lớp/constant pool trong ngữ cảnh runtime, **không phải** giá trị dùng chung toàn bộ JVM chỉ vì tên constant hay code bootstrap giống nhau. Hai lớp có entry condy giống nhau có thể phân giải riêng.

### 6.2. Con đường của một indy

```text
bytecode: invokedynamic #CONSTANT_InvokeDynamic
                         |
                         v
             call site chưa linked?
                         |
                       Có
                         |
               resolve bootstrap handle
               resolve static bootstrap args
               call BSM(Lookup, String, MethodType, ...)
                         |
               kiểm tra CallSite và type
               liên kết CallSite với instruction
                         |
                         v
                CALL target MethodHandle
                         |
                lần gọi tiếp: CALL target
                (không bootstrap mỗi lần)
```

Một `invokedynamic` **không gọi bootstrap mỗi khi thực thi**; bootstrap được dùng để **liên kết call site**, rồi các lần sau chạy target của `CallSite`. Trong tình huống đồng thời, có thể có bootstrap calls tranh chấp và một kết quả được chọn; không nên viết logic dựa trên **side effect đúng một lần** của bootstrap.

Nếu target là `MutableCallSite`, `setTarget` có thể thay hàm đang được gọi trong những lần dispatch về sau; thay target **không yêu cầu liên kết lại bootstrap**. Chương trình ở mục 8 chứng minh điều đó.

### 6.3. Eager vs lazy: có luôn “bootstrap lần đầu” không?

Ở mức mô hình, condy resolution xảy ra khi symbolic reference được sử dụng và indy call site được liên kết khi thực thi. JVM có thể thực hiện một số bước resolution sớm theo chiến lược triển khai, nhưng **lỗi phải được báo khi chạm tới symbolic reference theo các quy tắc JVMS**. Trong tình huống quan sát thông thường trên HotSpot, bootstrap được gọi ở lần sử dụng đầu tiên.

Không dựa vào mốc thời gian tuyệt đối như “constructor của class đã chạy thì condy chắc chắn resolved” hay “tất cả bootstrap methods chắc chắn chạy lúc class load”. Mỗi symbolic reference có vòng đời resolution riêng.

## 7. Bytecode và bộ mô tả: một ví dụ đặt cạnh nhau

Giả sử cần một constant kiểu `String` và một call site nhận `int` trả `int`:

```text
#20 = Dynamic      #0:greeting:Ljava/lang/String;
#28 = InvokeDynamic #1:calculate:(I)I
```

Lệnh nạp constant:

```text
0: ldc_w          #20             // push String from condy
3: areturn
```

Lệnh gọi qua indy:

```text
0: iload_0
1: invokedynamic  #28, 0          // call target with int argument
6: ireturn
```

**Kích thước instruction:**

- `ldc` dùng opcode + **chỉ số constant pool 1 byte**; `ldc_w` dùng opcode + **chỉ số 2 byte**. Chúng nạp kiểu category 1/reference phù hợp.
- `ldc2_w` dùng opcode + **chỉ số 2 byte**, dành cho constant kiểu **`long`/`double`** (category 2). Trong demo có condy descriptor `J` được nạp bằng `ldc2_w`.
- `invokedynamic` dùng opcode `0xba`, **chỉ số constant pool 2 byte + hai byte 0** theo format bytecode JVM. Nó thực hiện lời gọi với số/thứ tự args và kiểu return từ **method descriptor**.

**Không có opcode riêng tên `dynamic_constant`.** Condy là **loại entry** để các lệnh nạp constant dùng. Ngược lại, `invokedynamic` vừa là tên lệnh bytecode vừa liên quan một loại entry riêng trong constant pool.

### 7.1. Khi nào bootstrap trả `String`, khi nào trả `CallSite`?

Ví dụ condy:

```java
// BSM condy trả Object tương thích kiểu constant.
// NameAndType: greeting:Ljava/lang/String;
return "hello-condy";
```

Ví dụ indy:

```java
// BSM indy trả CallSite chứa target MethodHandle.
// NameAndType: calculate:(I)I
return new MutableCallSite(methodHandleTarget);
```

Chúng **không thể thay thế đơn thuần**: dùng bootstrap indy cho condy sẽ không tạo một `CallSite` tự động chạy như method call; dùng bootstrap condy cho indy không trả đúng contract `CallSite`.

## 8. Chương trình Java 11 hoàn chỉnh: sinh và thực thi cả `CONSTANT_Dynamic` lẫn `invokedynamic`

**Vì sao cần generator?** Trong Java 11, `javac` không có cú pháp Java source để chỉ định trực tiếp `CONSTANT_Dynamic`. Vì vậy để thực sự **kiểm thử condy**, không thể chỉ viết `static final String S = makeString();` rồi gọi đó là condy: nó có thể là field initialization trong `<clinit>` chứ **không phải** constant pool tag 17.

Ví dụ này dùng **`DataOutputStream`** để ghi classfile tối giản theo cấu trúc JVMS, nhằm giữ chương trình **độc lập, không cần ASM/Byte Buddy/Internet**. Nó tạo class `GeneratedCondyIndy` (classfile version **55**, Java 11), có ba static methods:

- `getString() : String` nạp `CONSTANT_Dynamic` descriptor `Ljava/lang/String;` bằng `ldc_w`.
- `getLong() : long` nạp `CONSTANT_Dynamic` descriptor `J` bằng `ldc2_w`.
- `call(int) : int` dùng `invokedynamic` descriptor `(I)I`.

Bootstrap của condy trả chuỗi `"hello-condy"` hoặc `Long.valueOf(42)`. Bootstrap của indy trả một `MutableCallSite` ban đầu trỏ đến `twice(int)`; sau hai lần gọi, chương trình đổi target sang `thrice(int)`.

**Cảnh báo về phạm vi:** generator bytecode thủ công dùng cho **giảng dạy/kiểm thử**, không khuyến nghị tự viết classfile emitter bằng tay cho sản phẩm lớn. Trong hệ thống thật, dùng một thư viện sinh bytecode được duy trì và version tương thích, hoặc dựa vào compiler.

### 8.1. Tệp `DynamicVsInvokeDynamicDemo.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class DynamicVsInvokeDynamicDemo {
    static int condyCalls = 0;
    static int indyCalls = 0;
    static MutableCallSite linkedSite;

    public static Object constantBootstrap(MethodHandles.Lookup lookup,
            String name, Class<?> type) {
        condyCalls++;
        if (type == String.class && name.equals("greeting")) {
            return "hello-condy";
        }
        if (type == long.class && name.equals("answer")) {
            return Long.valueOf(42);
        }
        throw new IllegalArgumentException(name + " : " + type);
    }

    public static CallSite callBootstrap(MethodHandles.Lookup lookup,
            String name, MethodType type) throws ReflectiveOperationException {
        indyCalls++;
        if (!name.equals("calculate") ||
                !type.equals(MethodType.methodType(int.class, int.class))) {
            throw new IllegalArgumentException(name + " : " + type);
        }
        linkedSite = new MutableCallSite(
                lookup.findStatic(DynamicVsInvokeDynamicDemo.class, "twice", type));
        return linkedSite;
    }

    public static int twice(int value) { return value * 2; }
    public static int thrice(int value) { return value * 3; }

    static final class Cp {
        final List<byte[]> values = new ArrayList<>();

        int add(int tag, int... fields) {
            try {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                DataOutputStream out = new DataOutputStream(bytes);
                out.writeByte(tag);
                for (int field : fields) out.writeShort(field);
                values.add(bytes.toByteArray());
                return values.size();
            } catch (IOException error) {
                throw new AssertionError(error);
            }
        }

        int utf(String value) {
            try {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                DataOutputStream out = new DataOutputStream(bytes);
                out.writeByte(1);
                out.writeUTF(value);
                values.add(bytes.toByteArray());
                return values.size();
            } catch (IOException error) {
                throw new AssertionError(error);
            }
        }

        int clazz(String internalName) {
            return add(7, utf(internalName));
        }

        int nat(String name, String descriptor) {
            return add(12, utf(name), utf(descriptor));
        }

        int methodref(int owner, String name, String descriptor) {
            return add(10, owner, nat(name, descriptor));
        }

        int mhStatic(int methodref) {
            try {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                DataOutputStream out = new DataOutputStream(bytes);
                out.writeByte(15);
                out.writeByte(6); // REF_invokeStatic
                out.writeShort(methodref);
                values.add(bytes.toByteArray());
                return values.size();
            } catch (IOException error) {
                throw new AssertionError(error);
            }
        }

        int dynamic(int bootstrap, String name, String descriptor) {
            return add(17, bootstrap, nat(name, descriptor));
        }

        int indy(int bootstrap, String name, String descriptor) {
            return add(18, bootstrap, nat(name, descriptor));
        }

        void write(DataOutputStream out) throws IOException {
            out.writeShort(values.size() + 1);
            for (byte[] value : values) out.write(value);
        }
    }

    static void emitMethod(DataOutputStream out, int nameIndex,
                           int descriptorIndex, int codeName,
                           byte[] code, int maxStack, int maxLocals)
            throws IOException {
        out.writeShort(0x0009); // public static
        out.writeShort(nameIndex);
        out.writeShort(descriptorIndex);
        out.writeShort(1);
        out.writeShort(codeName);
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(maxLocals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0); // exception_table_length
        out.writeShort(0); // Code attributes_count
    }

    static byte[] makeClass() throws IOException {
        Cp cp = new Cp();
        int me = cp.clazz("GeneratedCondyIndy");
        int object = cp.clazz("java/lang/Object");
        int source = cp.clazz("DynamicVsInvokeDynamicDemo");
        int constMethod = cp.methodref(source, "constantBootstrap",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;");
        int indyMethod = cp.methodref(source, "callBootstrap",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;");
        int constHandle = cp.mhStatic(constMethod);
        int indyHandle = cp.mhStatic(indyMethod);
        int stringConstant = cp.dynamic(0, "greeting", "Ljava/lang/String;");
        int longConstant = cp.dynamic(0, "answer", "J");
        int dynamicCall = cp.indy(1, "calculate", "(I)I");
        int code = cp.utf("Code");
        int bootstrapMethods = cp.utf("BootstrapMethods");
        int getString = cp.utf("getString");
        int descString = cp.utf("()Ljava/lang/String;");
        int getLong = cp.utf("getLong");
        int descLong = cp.utf("()J");
        int call = cp.utf("call");
        int descCall = cp.utf("(I)I");

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(55); // Java 11 classfile version
        cp.write(out);
        out.writeShort(0x0021); // ACC_PUBLIC, ACC_SUPER
        out.writeShort(me);
        out.writeShort(object);
        out.writeShort(0); // interfaces
        out.writeShort(0); // fields
        out.writeShort(3); // methods

        emitMethod(out, getString, descString, code,
                new byte[]{0x13, (byte)(stringConstant >>> 8),
                        (byte)stringConstant, (byte)0xb0}, 1, 0);
        emitMethod(out, getLong, descLong, code,
                new byte[]{0x14, (byte)(longConstant >>> 8),
                        (byte)longConstant, (byte)0xad}, 2, 0);
        emitMethod(out, call, descCall, code,
                new byte[]{0x1a, (byte)0xba, (byte)(dynamicCall >>> 8),
                        (byte)dynamicCall, 0, 0, (byte)0xac}, 1, 1);

        out.writeShort(1); // class attributes count
        out.writeShort(bootstrapMethods);
        out.writeInt(10); // 2 + 2*(method_ref + arguments_count)
        out.writeShort(2);
        out.writeShort(constHandle);
        out.writeShort(0);
        out.writeShort(indyHandle);
        out.writeShort(0);
        out.flush();
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        byte[] generated = makeClass();
        if (args.length == 1) {
            Files.write(Path.of(args[0], "GeneratedCondyIndy.class"), generated);
        }
        Class<?> clazz = MethodHandles.lookup().defineClass(generated);
        Method getString = clazz.getMethod("getString");
        Method getLong = clazz.getMethod("getLong");
        Method call = clazz.getMethod("call", int.class);

        System.out.println("classfile major: 55");
        System.out.println("first condy: " + getString.invoke(null));
        System.out.println("second condy: " + getString.invoke(null));
        System.out.println("long condy: " + getLong.invoke(null));
        System.out.println("condy BSM calls: " + condyCalls);

        System.out.println("first indy: " + call.invoke(null, 5));
        System.out.println("second indy: " + call.invoke(null, 6));
        System.out.println("indy BSM calls: " + indyCalls);
        MethodHandle triple = MethodHandles.lookup().findStatic(
                DynamicVsInvokeDynamicDemo.class, "thrice",
                MethodType.methodType(int.class, int.class));
        linkedSite.setTarget(triple);
        MutableCallSite.syncAll(new MutableCallSite[]{linkedSite});
        System.out.println("indy retargeted: " + call.invoke(null, 5));
        System.out.println("indy BSM after retarget: " + indyCalls);
    }
}
```

**Các điểm kỹ thuật của generator:**

- `Cp.add(17,...)` tạo entry tag 17, `Cp.add(18,...)` tạo tag 18. `NameAndType` của hai entry mang field descriptor/method descriptor tương ứng.
- `Cp.mhStatic` ghi `CONSTANT_MethodHandle` tag 15 với reference kind `REF_invokeStatic=6`.
- `BootstrapMethods` có hai entries: index 0 trỏ bootstrap constant, index 1 trỏ bootstrap call site. Cả condy String và condy long **dùng chung bootstrap entry 0 nhưng là hai constant pool entries khác nhau**.
- `emitMethod` tạo `Code` attribute hợp lệ cho ba method **không có branch**, vì vậy generator này không cần phát sinh `StackMapTable`.
- `MethodHandles.lookup().defineClass(generated)` có từ Java 9, định nghĩa class cùng runtime package với lookup class. Ví dụ để **hai class trong cùng unnamed package** và các bootstrap methods public, nên kiểm thử được quyền truy cập.
- File `GeneratedCondyIndy.class` chỉ được ghi nếu truyền đường dẫn thư mục qua tham số `args[0]`. Không đặt tên class trùng với class khác đã có trong cùng loader khi chạy lại trong một JVM.

### 8.2. Biên dịch và chạy

Tại thư mục có `DynamicVsInvokeDynamicDemo.java`, dùng JDK 11+:

```bash
javac --release 11 -encoding UTF-8 DynamicVsInvokeDynamicDemo.java
java DynamicVsInvokeDynamicDemo
```

**Stdout chính xác đã kiểm thử** (10 dòng):

```text
classfile major: 55
first condy: hello-condy
second condy: hello-condy
long condy: 42
condy BSM calls: 2
first indy: 10
second indy: 12
indy BSM calls: 1
indy retargeted: 15
indy BSM after retarget: 1
```

**Vì sao kết quả như vậy?**

1. **`classfile major: 55`**: generator đã viết major version Java 11.
2. **`first condy`/`second condy`**: hai lần gọi `getString()` nạp **cùng resolved value** của một entry `CONSTANT_Dynamic`. Bootstrap không tạo một giá trị mới ở lần `ldc_w` thứ hai.
3. **`long condy: 42`**: entry khác có descriptor `J` được nạp bằng `ldc2_w`. Bootstrap trả `Long.valueOf(42)` để JVM phân giải thành giá trị primitive `long`.
4. **`condy BSM calls: 2`**: trong lần chạy tuần tự đã kiểm thử, một bootstrap cho entry `greeting` và một bootstrap cho entry `answer`. Dù cùng BSM index 0, chúng **không dùng chung cache theo bootstrap**.
5. **`first indy: 10`**: lần đầu call site được liên kết qua bootstrap; target ban đầu là `twice(int)`, nhận 5 trả 10.
6. **`second indy: 12`**: gọi lại target đó với 6 cho 12. **Không chạy bootstrap lần nữa** trong phép gọi tuần tự này.
7. **`indy BSM calls: 1`**: một call site liên kết thành công trong ví dụ đơn luồng.
8. **`indy retargeted: 15`**: `MutableCallSite.setTarget` + `MutableCallSite.syncAll` chuyển target thành `thrice(int)`, nên tham số 5 cho 15.
9. **`indy BSM after retarget: 1`**: đổi target **không yêu cầu bootstrap lại**, dù hành vi call site đã đổi.

**Không khái quát “BSM luôn được gọi đúng một lần” cho chương trình đa luồng:** đặc tả cho phép bootstrap thực hiện cạnh tranh trong race resolution; JVM chỉ cài đặt một kết quả chọn được. Vì vậy ví dụ đếm bootstrap chỉ diễn giải **hành vi tuần tự đã kiểm thử**, không phải hợp đồng exactly-once toàn cục.

### 8.3. Kiểm chứng bytecode bằng `javap -v`

Để `javap` đọc được class đã sinh, tạo một **thư mục kiểm thử trống** và truyền đường dẫn vào `main`. Ví dụ chạy trong thư mục `demo-output` đã tạo sẵn:

```bash
mkdir demo-output
java DynamicVsInvokeDynamicDemo demo-output
javap -v -p -classpath demo-output GeneratedCondyIndy
```

Trên Windows, tạo thư mục bằng PowerShell `New-Item -ItemType Directory -Path demo-output` nếu chưa có. Các lệnh trên minh họa cách dùng tại thư mục có hai class đã biên dịch; `javap` thường nằm trong JDK cùng bộ với `java` và `javac`.

**Trích đoạn đã kiểm chứng từ `javap -v`:**

```text
#20 = Dynamic            #0:#19   // #0:greeting:Ljava/lang/String;
#24 = Dynamic            #0:#23   // #0:answer:J
#28 = InvokeDynamic      #1:#27   // #1:calculate:(I)I

0: ldc_w         #20              // Dynamic #0:greeting:Ljava/lang/String;
0: ldc2_w        #24              // Dynamic #0:answer:J
1: invokedynamic #28,  0         // InvokeDynamic #1:calculate:(I)I
```

Số thứ tự constant pool phụ thuộc **generator đang dùng**, không phải ID cố định của JVM. **Kiểm tra loại entry, descriptor và opcode** mới là mục tiêu.

Trong output đầy đủ, có mục `BootstrapMethods:` liệt kê bootstrap 0 trỏ `DynamicVsInvokeDynamicDemo.constantBootstrap` và bootstrap 1 trỏ `DynamicVsInvokeDynamicDemo.callBootstrap`. Điều này chứng minh classfile thật chứa cả condy và indy, chứ không chỉ mô phỏng bằng lời gọi Java thông thường.

**Lưu ý môi trường:** class generator có thể ghi tệp ra thư mục bạn chỉ định; tạo thư mục lab riêng, không ghi đè class production. Nếu không truyền `args[0]`, ví dụ chỉ `defineClass` và chạy trong memory, không tạo file `GeneratedCondyIndy.class` trên disk.

## 9. So sánh với Java source thông thường và những gì `javac` phát sinh

### 9.1. `static final` không tự có nghĩa là condy

```java
static final String NAME = expensiveComputation();
```

Ở Java source, giá trị này có thể được tính trong **class initialization (`<clinit>`)** rồi lưu vào **static field**, tùy cú pháp và compiler. Đây **không tự động** là `CONSTANT_Dynamic` trong constant pool.

Khác biệt:

| Trường hợp | Dữ liệu sống ở đâu? | Khi nào xử lý? |
| --- | --- | --- |
| `static final String S = "abc";` có compile-time constant expression | Có thể có `ConstantValue`/string constant được `javac` inline | Liên quan compile-time constant, không condy |
| `static final String S = helper();` | Static field, gán ở `<clinit>` | Class initialization chạy gán field |
| `CONSTANT_Dynamic` | **Constant pool entry**, resolution bằng bootstrap | Khi symbolic reference được sử dụng/resolve |
| `CONSTANT_InvokeDynamic` | **Constant pool entry mô tả call site** | Khi lệnh `invokedynamic` liên kết |

Không nên đánh đồng `final` với `CONSTANT_Dynamic`. Một condy cũng **không tạo ra field** trừ khi bytecode có logic lưu giá trị resolved đó vào field riêng.

### 9.2. Lambda thường dùng `invokedynamic`

Mã Java thông thường:

```java
import java.util.function.IntUnaryOperator;

public class LambdaExample {
    public static void main(String[] args) {
        IntUnaryOperator increment = n -> n + 1;
        System.out.println(increment.applyAsInt(4));
    }
}
```

Với Java 11 compiler thông thường, lambda được hỗ trợ bằng `invokedynamic` và bootstrap liên quan **`LambdaMetafactory`**. Đây là ví dụ của **liên kết hành vi** chứ không phải một constant tự tính ra `int 5`. `IntUnaryOperator.applyAsInt(4)` vẫn được thực thi khi gọi.

Để kiểm chứng bytecode bằng công cụ chuẩn:

```bash
javac --release 11 LambdaExample.java
javap -v -c LambdaExample
```

Tìm dòng `InvokeDynamic` và `BootstrapMethods` trong `javap`. Java source không cần trực tiếp chứa từ khóa `invokedynamic`: **compiler phát bytecode tương ứng**.

### 9.3. String concatenation cũng có thể dùng indy

Từ Java 9, `javac` thường dùng chiến lược `invokedynamic` + **`StringConcatFactory`** cho những biểu thức nối chuỗi, thay vì nhất thiết tạo một `StringBuilder` thủ công trong bytecode. Đây là một lựa chọn liên kết phép tính chuỗi; **không có nghĩa kết quả nối chuỗi được cache như một condy**.

Không dựa vào một chiến lược codegen duy nhất cho mọi JDK/compiler/flag. Muốn kết luận classfile cụ thể đang dùng condy hay indy thì **dùng `javap -v` trên file thực tế**.

## 10. Hiệu năng và lý do tồn tại của hai cơ chế

### 10.1. Vì sao có condy?

Trước `CONSTANT_Dynamic`, nhiều cấu trúc constant phức tạp phải được khởi tạo bằng một đoạn code trong `<clinit>` hay các helper fields. **Dynamic constant** cho JVM một cách biểu đạt trực tiếp: một constant pool entry có thể **được tính từ bootstrap** và tái sử dụng ở những nơi cần nạp constant.

Điều này hữu ích cho:

- Compiler/code generator muốn biểu đạt những literal không thể lưu dưới dạng constant pool tĩnh thông thường.
- Tạo constant có phụ thuộc ngữ cảnh `Lookup`, tên, kiểu, static arguments.
- Tạo thành phần metadata/handle/value dạng constant được dùng như bootstrap argument.
- Tái sử dụng resolved value, tránh tính lại cùng phép bootstrap ở mỗi lượt `ldc`.

**Không hứa hiệu năng luôn tốt hơn một static field**: chi phí bootstrap lần đầu, class loading, caching, JIT, escape analysis và pattern truy cập đều có thể ảnh hưởng. Dùng profiling/benchmark đáng tin nếu mục tiêu là performance.

### 10.2. Vì sao có indy?

`invokedynamic` cung cấp điểm gọi linh hoạt cho:

- **Lambda expressions** trong Java.
- **Dynamic languages** hoặc dispatch có thể phụ thuộc kiểu runtime.
- **String concatenation** theo các chiến lược của compiler/JDK.
- Những cơ chế chạy thông qua `MethodHandle` và `CallSite`.

JVM có thể tối ưu call site sau khi được liên kết; với `MutableCallSite` hoặc `VolatileCallSite`, target còn có thể thay đổi trong phạm vi contract và visibility tương ứng.

**Không khẳng định `invokedynamic` luôn gọi chậm vì “dynamic”**: sau liên kết, JIT có thể tối ưu, inline hoặc lập giả định phù hợp. Và cũng không coi mọi indy là một dynamic-language feature: lambda/string concat trong Java hiện đại sử dụng nó.

### 10.3. Một CallSite không phải một function result cache

Nếu target của `invokedynamic` là:

```java
static int twice(int x) { return x * 2; }
```

Gọi call site với `5` trả `10`, với `6` trả `12`. Nếu target đổi sang `thrice`, cùng call site với `5` sẽ trả `15`. Vì vậy **CallSite được liên kết/cache**, **không phải giá trị trả về mỗi lần invocation**. Đây là khác biệt cơ bản nhất với resolved constant.

## 11. Những lỗi thường gặp và cách nhận biết

| Nhầm lẫn / vấn đề | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Condy và indy đều tạo ra constant theo kiểu giống nhau” | Indy tạo `CallSite` để dispatch, không tạo một giá trị constant thay thế kết quả gọi | Phân biệt *value resolution* và *call-site linkage* |
| “Hai tag cùng số vì cùng bootstrap” | `CONSTANT_Dynamic=17`, `CONSTANT_InvokeDynamic=18` | Đọc `javap -v` |
| “Condy dùng `(I)I` descriptor” | Condy `NameAndType` phải có **field descriptor** | Dùng `I`, `J`, `Ljava/lang/String;`... |
| “Indy dùng `Ljava/lang/String;` descriptor” | Indy cần **method descriptor** | Dùng `()Ljava/lang/String;` hoặc `(I)I` |
| “Condy có opcode riêng” | Nó là constant pool entry | Nạp bằng `ldc`/`ldc_w`/`ldc2_w` |
| “Indy được nạp bằng `ldc`” | `invokedynamic` là lệnh gọi | Dùng opcode `invokedynamic` |
| “Condy bootstrap phải trả CallSite” | Cony cần giá trị tương thích kiểu đã khai báo | Return `String`/`Long`/object phù hợp |
| “Indy bootstrap trả String được” | JVM yêu cầu `CallSite` | Return `ConstantCallSite`/`MutableCallSite`... |
| “BSM indy chạy trên từng method call” | BSM dùng để link, không dùng làm target mỗi lần | Theo dõi target invocation riêng |
| “Condy BSM luôn gọi đúng một lần trong mọi thread” | Race resolution có thể tạo nhiều bootstrap invocations | Không có side effect phụ thuộc exactly-once |
| “Hai condy dùng chung BSM sẽ có cùng resolved value” | Cache gắn symbolic reference, không gắn tên BSM | Quan sát hai CP entries trong demo |
| “Đổi MutableCallSite target bắt JVM gọi bootstrap lại” | CallSite đã liên kết; target có thể thay đổi | Dùng `setTarget` + `syncAll`, không rebootstrap |
| “`static final` là condy” | Có thể là field và `<clinit>` | Kiểm tra classfile thực bằng `javap -v` |
| “`invokedynamic` là tính năng mới chỉ có ở Java 11” | Có từ Java 7, còn condy mới ở Java 11 | Phân biệt mốc version 51 và 55 |
| “`javac` có cú pháp `CONSTANT_Dynamic` trong Java source” | Không có cú pháp khai báo trực tiếp | Cần bytecode tool/generator |
| “Constant pool không được có thứ cần resolution” | Symbolic references cần resolution hợp lệ | Phân biệt literal, symbolic refs và BootstrapMethods |
| “Lỗi BSM luôn có cùng loại và message” | `BootstrapMethodError` và các `LinkageError` có quy tắc riêng | Đọc cause, JVMS, không hardcode thông báo |
| “Muốn học condy phải dùng API nội bộ của JVM” | Không nhất thiết | Tạo classfile chuẩn version 55 như demo, hoặc dùng thư viện sinh bytecode |

## 12. Về lỗi liên kết, bootstrap side effects và an toàn

### 12.1. Khi bootstrap trả kết quả sai

Những lỗi thường gặp ở classfile sinh bởi tool:

- Bootstrap condy trả `String` nhưng dynamic constant descriptor là `J` (long).
- Bootstrap indy trả `null` hoặc object không phải `CallSite`.
- `CallSite` có target `MethodType` không khớp descriptor `(I)I`.
- Bootstrap method handle không truy cập được hoặc static arguments không hợp lệ.
- Classfile tag 17 nhưng major version dưới 55.
- Bootstrap dùng lẫn `Class<?>` với `MethodType` ở tham số thứ ba.
- Một bootstrap khác phát sinh error trong quá trình resolve dẫn tới `BootstrapMethodError`/`LinkageError`.

Một classfile có thể **biên dịch/generate bytes thành công** mà **JVM từ chối load hoặc resolution** vì vi phạm format hoặc quy tắc liên kết. Thao tác bytecode generator phải có test chạy thật, không chỉ `javap`.

### 12.2. Tránh side effects trong bootstrap

Bootstrap có thể chạy trong lúc JVM đang resolution, và có thể có race nhiều thread. Vì thế:

- Ưu tiên bootstrap **deterministic**, không phụ thuộc state dễ thay đổi hoặc I/O blocking.
- Không đặt logic gửi tiền, ghi DB, tạo resource không-idempotent chỉ để “đảm bảo chạy đúng một lần”.
- Nếu dùng cache ngoài, dùng đồng bộ hóa/thread-safe primitives đúng cách.
- Cẩn trọng recursion khi condy/indy dùng nhau làm static bootstrap arguments, vì có thể tạo **chu kỳ resolution** và lỗi bootstrap.
- Không để bootstrap ghi log dữ liệu nhạy cảm. Nó có thể chạy trong class-loading/linking context và ảnh hưởng khởi động/lần gọi đầu.

### 12.3. Liên kết và bảo mật

`MethodHandles.Lookup` mang quyền truy cập trong ngữ cảnh caller; bootstrap cần tuân thủ visibility/access, không cố phá encapsulation bằng API nội bộ hoặc `setAccessible(true)` bừa bãi. `defineClass` trong ví dụ chỉ được phép định nghĩa class ở **cùng package với lookup class** và trong class loader phù hợp, không cho phép tùy ý định nghĩa class trong mọi package.

Trong ứng dụng thực tế, bytecode phát ra từ nguồn không đáng tin cậy cần xem là **mã có thể thực thi** sau khi load/verify. Không chạy classfile chưa xác minh chỉ vì constant pool trông giống dữ liệu.

## 13. Những câu hỏi ôn tập

**Câu 1.** `CONSTANT_Dynamic` có tag bao nhiêu và có từ Java mấy?  
**Đáp án:** **17**, từ **Java 11**, classfile major **55**.

**Câu 2.** `CONSTANT_InvokeDynamic` có tag bao nhiêu và gắn với lệnh nào?  
**Đáp án:** **18**, gắn với **`invokedynamic`**; xuất hiện từ Java 7.

**Câu 3.** Condy descriptor là field hay method descriptor?  
**Đáp án:** **Field descriptor**, ví dụ `Ljava/lang/String;` và `J`.

**Câu 4.** Indy descriptor là field hay method descriptor?  
**Đáp án:** **Method descriptor**, ví dụ `(I)I`.

**Câu 5.** Vì sao condy String dùng `ldc_w` còn condy long dùng `ldc2_w` trong demo?  
**Đáp án:** Vì String là reference/category 1 còn long là category 2, cần `ldc2_w`.

**Câu 6.** Bootstrap condy nhận `Class<?>` hay `MethodType` ở tham số thứ ba?  
**Đáp án:** **`Class<?>`** của giá trị constant. Bootstrap indy nhận **`MethodType`** của call site.

**Câu 7.** Tại sao hai lần `getString()` không làm `condyCalls` tăng lên hai lần?  
**Đáp án:** Chúng tham chiếu cùng một condy constant pool entry đã resolution; giá trị được tái sử dụng.

**Câu 8.** Vì sao `condyCalls` lại bằng 2 sau `getLong()`?  
**Đáp án:** `getLong()` dùng một **entry condy thứ hai**. Cùng bootstrap function nhưng là symbolic reference riêng.

**Câu 9.** Vì sao hai lần `call(5)`/`call(6)` không khiến `indyCalls` thành 2?  
**Đáp án:** BSM dùng để **link call site**, không chạy trong mỗi lần dispatch target.

**Câu 10.** Vì sao `call(5)` chuyển từ 10 sang 15 mà `indyCalls` vẫn bằng 1?  
**Đáp án:** `MutableCallSite` đã liên kết có thể được retarget bằng `setTarget` + `syncAll`; không bootstrap lại.

**Câu 11.** Java source `static final S = makeS()` có tự là condy không?  
**Đáp án:** Không. Có thể được khởi tạo trong `<clinit>`/field. Xác minh với `javap`.

**Câu 12.** Bootstrap có thể chạy nhiều lần khi nhiều thread tranh chấp resolution không?  
**Đáp án:** Có. JVM phải chọn một kết quả được cài đặt, nhưng không bảo đảm mọi invocation bootstrap cạnh tranh đều bị loại trước khi chạy.

## 14. Checklist khi phân tích classfile thực tế

- [ ] `javap -v` cho thấy **`Dynamic` (tag 17)** hay **`InvokeDynamic` (tag 18)**?
- [ ] `NameAndType` của Dynamic là **field descriptor**, của InvokeDynamic là **method descriptor**?
- [ ] Bytecode dùng **`ldc`/`ldc_w`/`ldc2_w`** hay **`invokedynamic`**?
- [ ] BootstrapMethods trỏ tới method handle nào, có static args gì?
- [ ] Condy bootstrap nhận `Lookup,String,Class` và trả giá trị đúng kiểu?
- [ ] Indy bootstrap nhận `Lookup,String,MethodType` và trả `CallSite` có target đúng type?
- [ ] Có giả định bootstrap **exactly-once** trong đa luồng không? Nếu có, cần sửa logic.
- [ ] Có nhầm giá trị trả về target với việc cache constant không?
- [ ] Nếu đang generate condy, classfile major version có **>=55**?
- [ ] Thực tế đã **load và chạy** bytecode chứ không chỉ thấy `javap` parse được chưa?
- [ ] Đang dùng API JVM/JDK hiện hành và không dựa vào internal `sun.*`?
- [ ] Bộ test bao gồm lần dùng đầu, lần dùng tiếp theo và nếu cần, retarget `CallSite`?

## 15. Ghi nhớ và tài liệu chính thức

**Tóm tắt:**

- **Dynamic constant:** `CONSTANT_Dynamic` (tag **17**), có từ **Java 11**, dùng **field descriptor**, bootstrap sinh **giá trị** tương thích `Class<?>`, JVM nạp bằng **`ldc`/`ldc_w`/`ldc2_w`** và dùng lại resolved value.
- **Invokedynamic:** `CONSTANT_InvokeDynamic` (tag **18**) + opcode **`invokedynamic`**, có từ Java 7, dùng **method descriptor**, bootstrap sinh **`CallSite`** với `MethodHandle` target. Mỗi lần thực thi lệnh sẽ **gọi target**, không gọi bootstrap; với `MutableCallSite` target có thể đổi.
- Cả hai dùng **`BootstrapMethods` attribute** và method handles; **cùng bootstrap spec không có nghĩa dùng chung resolved value**.
- **Bootstrap không mặc nhiên exactly-once dưới contention**; side effects cần kiểm soát.
- Java source **không có cú pháp trực tiếp** cho condy; cần compiler/bytecode generator. Lambda và string concatenation có thể dùng invokedynamic.
- Chương trình kiểm thử Java 11 thật đã xác nhận classfile major 55, `Dynamic` #20/#24, `InvokeDynamic` #28, `ldc_w`/`ldc2_w`/`invokedynamic` và kết quả retarget call site.

**Nguồn tham khảo chính thức còn áp dụng:**

1. [Java SE 11 JVMS `4.4.10 — CONSTANT_Dynamic và CONSTANT_InvokeDynamic](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10).
2. [Java SE 11 JVMS `5.4.3.6 — Resolution of Dynamic Constants and Call Sites](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6).
3. [Java SE 11 JVMS `6.5 — ldc, ldc_w, ldc2_w, invokedynamic](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html).
4. [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309).
5. [Oracle Java 11 — java.lang.invoke package](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html).
6. [Oracle Java 11 — CallSite](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/CallSite.html).
7. [Oracle Java 11 — MutableCallSite](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MutableCallSite.html).
8. [Oracle Java 26 JVMS `4 — Classfile structures](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html).
