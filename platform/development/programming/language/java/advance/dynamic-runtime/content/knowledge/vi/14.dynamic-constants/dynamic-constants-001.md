# 14.1 CONSTANT_Dynamic và khác biệt với điểm gọi invokedynamic

**Ngữ cảnh:** Java Advance → dynamic-runtime → 14. Hằng động.

Java Virtual Machine (JVM) có hai cơ chế liên kết runtime dễ bị nhầm vì đều dùng **bootstrap method** và cùng xuất hiện trong constant pool:

- **`CONSTANT_Dynamic` (condy, constant pool tag 17)** là một *dynamically-computed constant*: JVM thực thi bootstrap để **tính một giá trị có kiểu cụ thể**, sau đó ghi nhớ giá trị đã resolve.
- **`CONSTANT_InvokeDynamic` (tag 18)** là một *dynamically-computed call site*: JVM thực thi bootstrap để **liên kết một điểm gọi `invokedynamic` với đối tượng `CallSite`**, rồi thực thi target của call site mỗi lần instruction chạy.

Chúng có chung **cơ chế resolution qua bootstrap**, nhưng có kết quả khác hẳn: **giá trị** đối với condy và **điểm gọi có hành vi** đối với indy. Bài này trình bày cấu trúc class file, ký hiệu type, bootstrap signatures, cache semantics, khi nào dùng từng cơ chế, lỗi thường gặp và một chương trình **Java 17 thực sự phát sinh cả hai entry để kiểm chứng bằng `javap -v`**.

## 1. Hình dung khác nhau qua một sơ đồ

### Condy: load một constant đã giải

```text
                    CONSTANT_Dynamic (tag 17)
                    name = "configValue"
                    descriptor = Ljava/lang/String;
                    bootstrap = bootstrapConstant
                                |
                                v
                          instruction ldc
                                |
                         JVM resolve symbol
                                |
                         bootstrap(Lookup,
                          "configValue",
                          String.class)
                                |
                           "value-1"
                                |
                   cache kết quả resolution
                                |
       những lần ldc cùng tham chiếu sau: "value-1"
```

Cái "dynamic" là **giá trị được tính khi resolution**, không phải "mỗi lần đọc đều gọi bootstrap". Nếu bootstrap tạo một object mutable, JVM cache **reference đến object**, không đóng băng nội trạng object ấy.

### Indy: tạo một call site rồi dispatch nhiều lần

```text
                   CONSTANT_InvokeDynamic (tag 18)
                   name = "call"
                   descriptor = (String)String
                   bootstrap = bootstrapInvocation
                                |
                         instruction invokedynamic
                                |
                          JVM link instruction
                                |
                bootstrap(Lookup, "call", MethodType)
                                |
                  VolatileCallSite(target=first)
                                |
                    first("A") -> "first:A"
                                |
                   setTarget(second)   [sau đó]
                                |
                    second("C") -> "second:C"
```

Ở đây bootstrap trả một **`CallSite`**, không phải `"first:A"`. Lời gọi nghiệp vụ do target của call site thực hiện. Vì `VolatileCallSite` có thể đổi target nên kết quả lần gọi sau có thể khác, **dù bootstrap không chạy lại**. Nếu bootstrap trả `ConstantCallSite`, target không được đổi; bản chất indy vẫn là **điểm gọi**, không phải condy.

## 2. Constant-pool structure và bộ ký hiệu kiểu

JVMS `4.4.10 quy định:

```text
CONSTANT_Dynamic_info {
    u1 tag;                          // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}

CONSTANT_InvokeDynamic_info {
    u1 tag;                          // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

Hai cấu trúc gần giống nhau về byte, nhưng `name_and_type_index` trỏ đến **hai loại descriptor khác nhau**:

| Đặc tính | Condy | Indy |
| --- | --- | --- |
| Tag | `CONSTANT_Dynamic = 17` | `CONSTANT_InvokeDynamic = 18` |
| `NameAndType` | Tên và **field descriptor** | Tên và **method descriptor** |
| Ví dụ | `configValue:Ljava/lang/String;` | `call:(Ljava/lang/String;)Ljava/lang/String;` |
| Ý nghĩa type | Một kiểu giá trị, ví dụ `String` | Chữ ký lời gọi: các kiểu tham số và kiểu trả về |
| Opcode sử dụng | `ldc`/`ldc_w`; `ldc2_w` cho kiểu category 2 `long`/`double` | `invokedynamic` |
| Bootstrap type argument điển hình | `Class<?>` | `MethodType` |
| Bootstrap trả | Giá trị được chuyển thành kiểu field descriptor | `CallSite` có `type()` bằng method descriptor |
| Tái sử dụng sau linkage | Dùng lại resolved value | Reuse liên kết của instruction; mỗi lần vẫn thực thi target |

**Field descriptor** khác **method descriptor**:

- `Ljava/lang/String;` là một field descriptor: biểu diễn kiểu reference `java.lang.String`.
- `I` là kiểu primitive `int`; `J` là `long`.
- `(Ljava/lang/String;)Ljava/lang/String;` là method descriptor: nhận một `String` và trả một `String`.
- `()V` là method descriptor của method không có tham số, trả `void`; condy **không** có "giá trị `void`" vì nó phải resolve thành value.

Cột `bootstrap_method_attr_index` **không phải chỉ số trực tiếp của method Java**. Nó là chỉ số trong mảng bootstrap specs thuộc **`BootstrapMethods` class-file attribute**. Mỗi bootstrap spec chứa một tham chiếu tới `CONSTANT_MethodHandle` và danh sách static bootstrap arguments.

```text
constant_pool:
  #26 = CONSTANT_Dynamic,       bootstrap spec 0
  #29 = CONSTANT_InvokeDynamic, bootstrap spec 1

BootstrapMethods attribute:
  [0] -> MethodHandle của bootstrapConstant, 0 static args
  [1] -> MethodHandle của bootstrapInvocation, 0 static args

bytecode:
  readConstant():  ldc #26; areturn
  dynamicCall(s):  aload_0; invokedynamic #29; areturn
```

Các index trên là **số thứ tự của ví dụ mục 7**, không phải định dạng cố định cho mọi class. `BootstrapMethods` cũng hỗ trợ static bootstrap arguments khác nhau như string, method handle, method type, class hoặc những condy đã resolve phù hợp; hai entry trong demo chỉ sử dụng ba tham số bắt buộc.

### Phiên bản JVM

- `invokedynamic`/`CONSTANT_InvokeDynamic` có từ **Java 7 (class-file major version 51)**.
- `CONSTANT_Dynamic` có từ **Java 11 (major 55; JEP 309)**.
- Demo bên dưới tạo file có **major version 61 (Java 17)**, chạy trên JDK 17+.
- Java source không có một keyword trực tiếp để tạo arbitrary `CONSTANT_Dynamic`. Viết `static final` không đồng nghĩa sinh ra condy. Vì thế muốn thấy entry `Dynamic` thật, ta cần phát sinh bytecode hoặc dùng một bytecode library.
- Một số cấu trúc được `javac` biên dịch bằng `invokedynamic` (ví dụ lambdas hay string concatenation ở các phiên bản Java thích hợp), nhưng **không phải mọi lời gọi Java** đều dùng opcode này.

## 3. Bootstrap của condy: trả về một giá trị, không phải một target call

Mẫu chữ ký thường gặp:

```java
public static String bootstrapConstant(
        MethodHandles.Lookup lookup, String name, Class<?> type) {
    return "computed-value";
}
```

Đây là **snippet**, không phải chương trình độc lập. Khi resolve condy, JVM cung cấp:

1. `Lookup` với ngữ cảnh class chứa symbolic reference.
2. Tên symbol `name` từ `NameAndType`.
3. Đối tượng `Class<?>` tương ứng **kiểu giá trị được yêu cầu** bởi field descriptor.
4. Các static arguments bổ sung nếu `BootstrapMethods` entry khai báo.

Trong ví dụ thật, `name` là `"configValue"` và `type` là `String.class`; bootstrap trả chuỗi `"value-1"`. JVM xác thực/chuyển kết quả về kiểu `T` đã khai báo. Nếu incompatible (ví dụ object không cast được sang `String`, hoặc `null` cho primitive), resolution gây lỗi thường là `BootstrapMethodError`.

**Condy không bắt buộc trả mỗi String.** Nó có thể trả object reference, `Class`, `MethodHandle`, `VarHandle` hoặc giá trị primitive phù hợp với field descriptor. Thư viện `java.lang.invoke.ConstantBootstraps` cung cấp những bootstrap có sẵn như `nullConstant`, `enumConstant`, `primitiveClass`, `getStaticFinal`, `fieldVarHandle`, `staticFieldVarHandle`, `arrayVarHandle` và `invoke`.

### Vì sao `Lookup` cần thiết?

BSM có thể cần đọc field, tạo method handle, truy cập class hoặc tham chiếu tới tài nguyên liên kết. `Lookup` phản ánh access context của class chứa entry: **bootstrap không được phép tự vượt mọi rào chắn `private` hoặc JPMS**. Trong một ứng dụng modular, access checks khi tìm target/field vẫn áp dụng.

Mặc dù nhiều ví dụ Java sử dụng chính xác chữ ký `(Lookup, String, Class) -> Object/String`, **JVMS cho phép các bootstrap method handles có kiểu tham số tương thích theo `invokeWithArguments`**. Riêng condy có ràng buộc quan trọng: tham số đầu của BSM handle phải có type `MethodHandles.Lookup`. Dạng mẫu trên dễ đọc và phù hợp cho ví dụ cơ bản.

### Giá trị condy có luôn bất biến?

Không. Một bootstrap trả `ArrayList` mutable tạo ra **một reference được ghi nhớ**. Các lần `ldc` cùng entry có thể lấy lại chính object ấy, nhưng object bên trong vẫn có thể bị sửa. Muốn giá trị không biến đổi, hãy dùng immutable object hoặc quy ước concurrency đúng. "Constant" nghĩa là JVM không **lại resolve giá trị ấy** sau successful resolution, không phải nó biến mutable object thành immutable.

### Phạm vi cache của giá trị

Mỗi class được một defining class loader tạo ra có run-time constant pool tương ứng. Condy result được tái sử dụng theo **symbolic reference đã resolve trong run-time constant pool**, chứ không phải một cache toàn JVM theo tên `configValue`. Hai class khác nhau dùng tên/descriptor giống nhau vẫn có thể có kết quả và số lần bootstrap khác nhau.

Không nên gắn giao dịch không idempotent (như thu tiền) vào condy BSM chỉ vì kỳ vọng nó "luôn đúng một lần": khi có nhiều thread cùng đua resolution ban đầu, **JVM có thể gọi bootstrap đồng thời nhiều lần rồi chọn một kết quả**. Ý này sẽ được giải thích ở mục 9.

## 4. Bootstrap của indy: trả về `CallSite` và một `MethodType`

Dạng đơn giản:

```java
public static CallSite bootstrapInvocation(
        MethodHandles.Lookup lookup, String name, MethodType type)
        throws ReflectiveOperationException {

    MethodHandle target = MethodHandles.lookup().findStatic(
            SomePublicClass.class, "implementation", type);
    return new ConstantCallSite(target);
}
```

Đây cũng là **snippet minh họa**; `SomePublicClass`/`implementation` cần được thay bằng method thật trong chương trình khác. JVM thường cung cấp:

1. `Lookup` ứng với class chứa indy instruction.
2. Tên dynamic call site như `"call"`.
3. `MethodType` ứng với **method descriptor** gồm tham số và return type.
4. Tùy chọn static bootstrap arguments.

**Kết quả phải là một `CallSite` khác null**, có `type()` bằng signature mà indy instruction yêu cầu. Không được trả thẳng `MethodHandle` hoặc `String` rồi hy vọng JVM tự tạo call site. Nếu dùng `ConstantCallSite`, target cố định; nếu dùng `MutableCallSite` hoặc `VolatileCallSite`, code khác có thể cập nhật target với các quy tắc memory visibility tương ứng.

### Phạm vi liên kết đặc biệt của `invokedynamic`

Theo JVMS `5.4.3, khi resolution của một indy instruction thành công, JVM ghi nhớ **CallSite cho chính instruction ấy**. Những lần chạy lại **cùng vị trí instruction** dùng lại call site đã link. Tuy nhiên nếu **hai indy instructions khác nhau trỏ cùng constant-pool entry**, chúng vẫn được phép/đòi hỏi liên kết riêng theo từng instruction; không nên nói "một CP entry indy luôn nghĩa là một call site duy nhất".

So sánh với condy: khi một `CONSTANT_Dynamic` symbolic reference resolve thành giá trị, các `ldc` khác cùng tham chiếu đó dùng lại resolved constant. Đây là khác biệt quan trọng dù cả hai structure đều có bootstrap index và `NameAndType`.

### Không nhầm linkage với mỗi lần invocation

```text
First time at instruction N:
    BSM -> CallSite(target=first)
    first("A") -> "first:A"

Second time, same instruction N:
    [không cần BSM nữa]
    first("B") -> "first:B"

Update:
    site.setTarget(second)

Third time, same instruction N:
    [vẫn cùng CallSite]
    second("C") -> "second:C"
```

Điểm gọi `invokedynamic` hoạt động qua liên kết đã lưu, nhưng **target được thực thi ở mỗi lượt gọi**. Condy thì đẩy một giá trị đã resolve lên operand stack mà không có "target method invocation" ngầm mỗi lần load.

## 5. Khi nào JVM thực sự resolve?

Một mô hình sư phạm tiện lợi là "lần đầu dùng sẽ gọi bootstrap" vì các JVM thường lazy-resolve symbolic references khi cần. Nhưng với condy, ứng dụng **không nên dựa vào một thời điểm wall-clock cố định** cho side effects của BSM: đặc tả có quy tắc về khi nào resolution được phép và JVM có thể có quyền thực hiện resolution sớm hợp lệ. Điều bền vững là: **successful resolution được ghi nhớ** và không tự thực thi lại BSM ở những lần dùng tiếp theo cùng reference.

Với indy, linking gắn với việc thực thi **một indy instruction cụ thể**; code chỉ nạp class hoặc lookup `Method` chưa có nghĩa đã chạy target. Ví dụ chạy dưới đây cho kết quả trước/linkage phù hợp với một JVM Java 17 đã thử nghiệm, nhưng không phải lời cam kết scheduling chung cho mọi thực thi.

### Một ví dụ về cache và version

```text
condy resolution:
    configValue => "value-1"
    10 lần ldc cùng resolved ref -> cùng "value-1"

indy resolution:
    instruction N => CallSite S
    10 lần invoke N -> 10 lần chạy current target của S
    setTarget(H2) -> những lần gọi sau có thể dùng H2

Không thể:
    gọi "condy.setTarget(H2)"  // không có API này
```

Nếu condy **tình cờ trả một `CallSite` object làm value**, `ldc` chỉ trả **object đó**. Nó không tự thực hiện opcode `invokedynamic`, không tự gọi target. Consumer muốn gọi phải viết code tương ứng. Kết quả kiểu `CallSite` không khiến constant pool entry biến từ tag 17 thành tag 18.

## 6. Bảng đối chiếu cô đọng

| Tiêu chí | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Tag | 17 | 18 |
| Purpose | Resolve value | Resolve call site |
| Descriptor | Field descriptor | Method descriptor |
| Opcode | `ldc`/`ldc_w`/`ldc2_w` | `invokedynamic` |
| Bootstrap type arg | `Class<?>` | `MethodType` |
| Bootstrap result | Typed constant value | `CallSite` |
| Sau successful linkage | Dùng lại giá trị | Invoke target mỗi lần |
| Có thể thay kết quả bằng `setTarget`? | Không có API thay resolved value | Có thể trên mutable/volatile call site |
| Đơn vị cache chính | Symbolic reference trong run-time constant pool | Mỗi instruction indy đã liên kết |
| Tối thiểu | Java 11 / major 55 | Java 7 / major 51 |
| Lỗi bootstrap | Thường `BootstrapMethodError` | Thường `BootstrapMethodError` |
| Sử dụng | Runtime-computed metadata/value/handle | Runtime dispatch/language linkage |

## 7. Demo Java 17: tự sinh class file chứa **cả hai entry thật**

Để bảo đảm `javap -v` hiển thị đúng hai loại constant pool, ví dụ này dùng API **thuần JDK `DataOutputStream`** tạo một classfile Java 17 tối giản. Không cần ASM, không cần dependency ngoài và **không cần flags truy cập API nội bộ JDK**.

Chương trình có hai class:

- `ConstantBridgeDemo`: Java source bạn biên dịch; chứa bootstrap methods, hai method nghiệp vụ, và code phát sinh bytecode.
- `GeneratedLinkageDemo`: class được phát sinh từ byte[], có `readConstant()` chứa `ldc #26` và `dynamicCall(String)` chứa `invokedynamic #29`. Không có file nguồn Java riêng cho nó.

Trong production, không nên tự hard-code constant pool index như demo; hãy dùng bytecode library có hỗ trợ classfile version hoặc cơ chế compiler phù hợp. Ví dụ chỉ nhằm giúp người học **đọc được class file thật**.

### 7.1 Mã nguồn duy nhất: `ConstantBridgeDemo.java`

Lưu **toàn bộ** mã dưới đây vào file `ConstantBridgeDemo.java` trong thư mục thực nghiệm:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConstantBridgeDemo {
    private static int constantLinks;
    private static int invocationLinks;
    private static VolatileCallSite callSite;

    public static String bootstrapConstant(MethodHandles.Lookup lookup,
                                           String name, Class<?> type) {
        constantLinks++;
        System.out.println("condy.bootstrap:" + name + ":" + type.getSimpleName());
        return "value-" + constantLinks;
    }

    public static CallSite bootstrapInvocation(MethodHandles.Lookup lookup,
                                               String name, MethodType type)
            throws ReflectiveOperationException {
        invocationLinks++;
        System.out.println("indy.bootstrap:" + name + ":" + type);
        MethodHandle target = MethodHandles.lookup()
                .findStatic(ConstantBridgeDemo.class, "first", type);
        callSite = new VolatileCallSite(target);
        return callSite;
    }

    public static String first(String input) {
        return "first:" + input;
    }

    public static String second(String input) {
        return "second:" + input;
    }

    static final class Loader extends ClassLoader {
        Loader(ClassLoader parent) { super(parent); }
        Class<?> defineGenerated(byte[] binary) {
            return defineClass("GeneratedLinkageDemo", binary, 0, binary.length);
        }
    }

    private static void utf(DataOutputStream out, String value) throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static void clazz(DataOutputStream out, int name) throws IOException {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void nameAndType(DataOutputStream out, int name, int desc)
            throws IOException {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(desc);
    }

    private static void methodRef(DataOutputStream out, int owner, int signature)
            throws IOException {
        out.writeByte(10);
        out.writeShort(owner);
        out.writeShort(signature);
    }

    private static void staticHandle(DataOutputStream out, int reference)
            throws IOException {
        out.writeByte(15);
        out.writeByte(6); // REF_invokeStatic
        out.writeShort(reference);
    }

    private static void codeMethod(DataOutputStream out, int name, int descriptor,
                                   int maxStack, int locals, byte[] code)
            throws IOException {
        out.writeShort(0x0009); // public static
        out.writeShort(name);
        out.writeShort(descriptor);
        out.writeShort(1); // Code attribute
        out.writeShort(7); // #7 = "Code"
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(locals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0); // no exception handlers
        out.writeShort(0); // no nested Code attributes
    }

    static byte[] buildClass() throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);   // minor
        out.writeShort(61);  // Java 17 class-file version
        out.writeShort(30);  // constant_pool_count: 29 entries

        utf(out, "GeneratedLinkageDemo");                            // #1
        clazz(out, 1);                                                // #2
        utf(out, "java/lang/Object");                                 // #3
        clazz(out, 3);                                                // #4
        utf(out, "readConstant");                                     // #5
        utf(out, "()Ljava/lang/String;");                            // #6
        utf(out, "Code");                                             // #7
        utf(out, "dynamicCall");                                      // #8
        utf(out, "(Ljava/lang/String;)Ljava/lang/String;");          // #9
        utf(out, "BootstrapMethods");                                 // #10
        utf(out, "ConstantBridgeDemo");                               // #11
        clazz(out, 11);                                               // #12
        utf(out, "bootstrapConstant");                                // #13
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;"); // #14
        nameAndType(out, 13, 14);                                     // #15
        methodRef(out, 12, 15);                                       // #16
        staticHandle(out, 16);                                        // #17
        utf(out, "bootstrapInvocation");                              // #18
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;"); // #19
        nameAndType(out, 18, 19);                                     // #20
        methodRef(out, 12, 20);                                       // #21
        staticHandle(out, 21);                                        // #22
        utf(out, "configValue");                                      // #23
        utf(out, "Ljava/lang/String;");                              // #24
        nameAndType(out, 23, 24);                                     // #25
        out.writeByte(17); out.writeShort(0); out.writeShort(25);     // #26 CONSTANT_Dynamic
        utf(out, "call");                                             // #27
        nameAndType(out, 27, 9);                                      // #28
        out.writeByte(18); out.writeShort(1); out.writeShort(28);     // #29 CONSTANT_InvokeDynamic

        out.writeShort(0x0021); // public, super
        out.writeShort(2);      // this class
        out.writeShort(4);      // java/lang/Object
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(2);      // methods_count

        codeMethod(out, 5, 6, 1, 0, new byte[]{
            0x12, 0x1a,             // ldc #26 (CONSTANT_Dynamic)
            (byte) 0xb0            // areturn
        });
        codeMethod(out, 8, 9, 1, 1, new byte[]{
            0x2a,                  // aload_0
            (byte) 0xba, 0, 29, 0, 0,  // invokedynamic #29
            (byte) 0xb0            // areturn
        });

        out.writeShort(1);   // class attributes_count
        out.writeShort(10);  // "BootstrapMethods"
        out.writeInt(10);    // attribute_length
        out.writeShort(2);   // two bootstrap specs
        out.writeShort(17); out.writeShort(0); // condy BSM handle, no static args
        out.writeShort(22); out.writeShort(0); // indy BSM handle, no static args
        out.flush();
        return buffer.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        byte[] binary = buildClass();
        Files.write(Path.of("GeneratedLinkageDemo.class"), binary);
        Class<?> generated = new Loader(ConstantBridgeDemo.class.getClassLoader())
                .defineGenerated(binary);
        Method read = generated.getMethod("readConstant");
        Method call = generated.getMethod("dynamicCall", String.class);

        System.out.println("before:condy=" + constantLinks + ",indy=" + invocationLinks);
        System.out.println("condy.1=" + read.invoke(null));
        System.out.println("condy.2=" + read.invoke(null));
        System.out.println("indy.1=" + call.invoke(null, "A"));
        System.out.println("indy.2=" + call.invoke(null, "B"));
        MethodHandle next = MethodHandles.lookup()
                .findStatic(ConstantBridgeDemo.class, "second",
                            MethodType.methodType(String.class, String.class));
        callSite.setTarget(next);
        System.out.println("indy.3=" + call.invoke(null, "C"));
        System.out.println("after:condy=" + constantLinks + ",indy=" + invocationLinks);
    }
}
```

### 7.2 Biên dịch và chạy

Đứng tại thư mục chứa file Java:

```bash
javac --release 17 -encoding UTF-8 ConstantBridgeDemo.java
java ConstantBridgeDemo
javap -v GeneratedLinkageDemo
```

`java ConstantBridgeDemo` sinh thêm file `GeneratedLinkageDemo.class` ở thư mục hiện tại. `javap -v` sẽ đọc file class phát sinh, giúp nhìn rõ hai constant-pool entries mà source Java không trực tiếp diễn tả.

**Output thực tế từ `java ConstantBridgeDemo` (một luồng):**

```text
before:condy=0,indy=0
condy.bootstrap:configValue:String
condy.1=value-1
condy.2=value-1
indy.bootstrap:call:(String)String
indy.1=first:A
indy.2=first:B
indy.3=second:C
after:condy=1,indy=1
```

Giải nghĩa:

1. Sau khi driver đã tạo `GeneratedLinkageDemo` và lấy `Method` qua Reflection, trong lần chạy đã thử, chưa bootstrap nào chạy: `before:condy=0,indy=0`.
2. `read.invoke(null)` làm method `readConstant` thực thi **`ldc #26`**. BSM `bootstrapConstant` nhận tên `configValue` và `String.class`, trả `"value-1"`.
3. Gọi `readConstant` lần hai vẫn dùng `"value-1"` đã resolve; `constantLinks` không tăng.
4. `call.invoke(null,"A")` làm method `dynamicCall` thực thi **`invokedynamic #29`**. BSM `bootstrapInvocation` tạo `VolatileCallSite` với target `first`. Đây là lý do có `indy.bootstrap:call:(String)String` rồi `indy.1=first:A`.
5. Gọi `dynamicCall` lần hai tại **cùng instruction** dùng site đã link, nhưng vẫn gọi target với input `B`: `indy.2=first:B`. BSM không chạy lại.
6. Code `callSite.setTarget(next)` đổi target từ `first` sang `second` nhưng **không sửa CP entry và không resolve lại indy instruction**. Lượt gọi sau trả `indy.3=second:C`.
7. `after:condy=1,indy=1` xác nhận trong **kịch bản đơn luồng đã kiểm chứng** mỗi bootstrap chạy một lần; không nên nâng kết quả thành bảo đảm số lần callback trong cuộc đua resolution nhiều thread.

**Phân biệt Reflection và bytecode cần học:** `Method.invoke` xuất hiện trong **driver** để gọi những phương thức được sinh. Nó không phải bản thân `invokedynamic` opcode. Opcode `ldc` và `invokedynamic` nằm **trong bytecode của `GeneratedLinkageDemo`** và có thể xem bằng `javap -v`.

### 7.3 Bằng chứng từ `javap -v`

Trong output dài của `javap -v GeneratedLinkageDemo`, những đoạn đáng chú ý là (trích các dòng liên quan, không phải output nguyên văn trọn vẹn):

```text
major version: 61
#26 = Dynamic            #0:#25     // #0:configValue:Ljava/lang/String;
#29 = InvokeDynamic      #1:#28     // #1:call:(Ljava/lang/String;)Ljava/lang/String;

public static java.lang.String readConstant();
    ...
    0: ldc           #26          // Dynamic #0:configValue:Ljava/lang/String;
    2: areturn

public static java.lang.String dynamicCall(java.lang.String);
    ...
    0: aload_0
    1: invokedynamic #29,  0      // InvokeDynamic #1:call:(Ljava/lang/String;)Ljava/lang/String;
    6: areturn

BootstrapMethods:
  0: #17 REF_invokeStatic ConstantBridgeDemo.bootstrapConstant:(...)
  1: #22 REF_invokeStatic ConstantBridgeDemo.bootstrapInvocation:(...)
```

Các dấu `...` trong trích đoạn này biểu thị **metadata/descriptor dài được lược bớt** để dễ đọc, không phải cú pháp của `javap`. Khi chạy sẽ thấy descriptor đầy đủ của BSM và các constant-pool entries liên quan.

Chú ý ba đường nối:

- `#26` có tag **17**, bootstrap spec index `0`, descriptor **`Ljava/lang/String;`**, được nạp bằng **`ldc`**.
- `#29` có tag **18**, bootstrap spec index `1`, descriptor **`(Ljava/lang/String;)Ljava/lang/String;`**, được dùng bởi **`invokedynamic`**.
- `BootstrapMethods[0]` chứa `#17` method handle cho `bootstrapConstant`; `BootstrapMethods[1]` chứa `#22` cho `bootstrapInvocation`.

### 7.4 Vì sao class generator nhỏ này hợp lệ?

Trong `buildClass()`:

- `0xCAFEBABE` đánh dấu class file; major **61** biểu thị Java 17.
- `constant_pool_count = 30`, nhưng chỉ có 29 entry thực từ `#1` đến `#29` (index `0` không dùng).
- `staticHandle(...)` ghi constant-pool tag **15** cho MethodHandle và reference kind **6 = REF_invokeStatic**.
- `out.writeByte(17)` phát entry **CONSTANT_Dynamic** (có bootstrap index 0).
- `out.writeByte(18)` phát entry **CONSTANT_InvokeDynamic** (có bootstrap index 1).
- Hai methods generated chỉ chứa đủ bytecodes cho `ldc/areturn` và `aload_0/invokedynamic/areturn`.
- Class attribute `BootstrapMethods` chứa 2 bootstrap specs, mỗi spec có 0 static args.

Class `GeneratedLinkageDemo` **không có constructor** vì demo chỉ gọi hai static methods; không có instance nào cần tạo. `Code` attribute không có branches hay exception handlers, nên cấu trúc tối giản đủ cho Java verifier. Việc tự viết từng chỉ số constant pool ở đây **chỉ phục vụ học tập**; codegen production cần library đáng tin để xử lý descriptor, stack maps, class loader và nhiều loại opcode hơn.

## 8. Những khác biệt dễ bị bỏ qua

### Condy cache *giá trị*, indy cache *liên kết*

Giả sử condy BSM nhận một timestamp và trả `Instant.now()`. Sau successful resolution, những lần `ldc` cùng entry trả lại **cùng reference đã resolve**, không tự gọi `Instant.now()` mỗi lần. Ngược lại, indy target có thể chứa code gọi `Instant.now()` và trả timestamp mới mỗi lần target được invoke. "Dynamic" không đồng nghĩa "recompute on each use".

### Indy bootstrap không trả kết quả nghiệp vụ

Nếu BSM indy trả `"ok"` hoặc `MethodHandle`, đó là sai hợp đồng; kết quả phải là `CallSite`. Nhưng target bên trong `CallSite` có thể trả `String`, `int`, `void`... tùy `MethodType` của indy site. Nhớ **two-stage model**: linking (`BSM -> CallSite`) và invoking (`CallSite.target -> business result`).

### Cả hai có thể xuất hiện chung một class file

Demo tạo cả tag 17 và 18 cùng trong `GeneratedLinkageDemo.class`. Hơn nữa, condy có thể được dùng làm **static argument** cho indy BSM. Khi đó JVM resolve condy để lấy metadata hoặc handle trước/đồng thời với quá trình liên kết indy theo dependency order. Nhưng điều đó không biến condy thành indy; nó chỉ là **dữ liệu cung cấp cho bootstrap của lời gọi**.

### Condy không phải `static final`

Java `static final` field có các quy tắc về class initialization và compile-time constant variables. Condy là **symbolic reference trong run-time constant pool**. Một `static final` object có thể được tạo trong `<clinit>`, không nhất thiết liên quan đến `CONSTANT_Dynamic`. Một `CONSTANT_Dynamic` có thể tồn tại dù không có Java field ứng với tên đó.

### Lỗi bootstrap khác lỗi khi target được thực thi

Nếu BSM indy chạy và liên kết thành công, nhưng **target** về sau ném `IllegalArgumentException`, `IOException` hoặc một exception khác, đó là lỗi của target invocation, không phải lý do tự động `BootstrapMethodError`. Chỉ khi việc **resolution/linkage** gặp vấn đề mới thuộc nhóm bootstrap/linkage errors. Điều này hữu ích khi đọc stack trace qua dynamic language frameworks.

## 9. Lỗi liên kết, caching thất bại và concurrency nuance

| Trường hợp | Kết quả |
| --- | --- |
| Condy BSM trả object đúng kiểu yêu cầu | Resolution thành công, value được lưu lại |
| Condy kiểu `int` nhưng BSM trả `null` | Không convert thành primitive → `BootstrapMethodError` |
| Condy BSM trả reference không convert được về declared field type | `BootstrapMethodError` |
| Indy BSM trả `null` | `BootstrapMethodError` |
| Indy BSM trả `String` hoặc `MethodHandle` trần thay vì `CallSite` | `BootstrapMethodError` |
| Indy BSM trả `CallSite` sai `MethodType` | `BootstrapMethodError` |
| BSM ném runtime/checked exception không phải `Error` | JVM bọc lỗi từ BSM invocation thành `BootstrapMethodError` với cause |
| BSM ném subclass của `Error` | Resolution có thể thất bại bằng chính `Error` đó |
| Condy có static-argument dependency cycle đến chính nó | JVMS quy định thất bại tại re-resolution, có thể là `StackOverflowError` |
| Condy reference đã resolve thất bại | Lỗi resolution được ghi nhớ cho những lần dùng lại reference ấy; bootstrap không tự retry |
| Indy instruction đã linkage thất bại | Những lượt dùng lại chính instruction ấy vẫn thất bại, không tự gọi lại BSM |

**Concurrency nuance (quan trọng):** JVMS cho phép **nhiều thread cùng cố resolve một symbolic reference** và bootstrap method handle **có thể được invoke đồng thời**. JVM chọn kết quả của một lần invocation và công bố cho các thread; những lần khác được phép hoàn tất nhưng kết quả bị bỏ. Vì thế counter bootstrap trong demo đơn luồng tăng 1 là hành vi được quan sát, **không phải lời hứa mọi BSM toàn hệ thống chỉ chạy đúng một lần và tuyệt đối không có duplicate side effects**.

Nếu bootstrap có đọc/ghi shared mutable state, phải thread-safe hoặc idempotent. Đừng làm nghiệp vụ như charge payment, gửi email, hay ghi dữ liệu không thể đảo ngược trong BSM với giả định không thể bị chạy đồng thời. Đồng thời nên tránh circular dependency của các condy static arguments: JVM không hỗ trợ việc resolve một condy phụ thuộc vòng về chính symbolic reference đó.

## 10. Khi nào dùng condy, khi nào dùng indy?

### Chọn condy khi cần một **value** được resolve tại runtime

Các ví dụ phù hợp:

- Giá trị metadata đặc biệt được tính từ `Lookup`, tên và static arguments.
- Một reference đến `MethodHandle`, `VarHandle`, `Class` hoặc immutable domain descriptor.
- Một object cấu hình không dễ biểu diễn bằng simple constant-pool literal nhưng chỉ cần resolve **một lần theo reference**.
- Một literal-like value cho compiler sinh bytecode mà không muốn tạo lại object ở mỗi lần dùng.

Nếu business requirements cần giá trị luôn cập nhật từ external service **mỗi lần đọc**, condy không tự giải bài toán đó; value đã resolve được cache. Bạn có thể trả một object tự quản lý refresh, nhưng refresh là hành vi **của object**, không phải chạy lại condy BSM.

### Chọn indy khi cần một **call site**

Phù hợp khi compiler/runtime cần:

- Link một lời gọi dựa trên lookup context và method signature.
- Hỗ trợ dynamic language dispatch hoặc call adapters.
- Dùng `ConstantCallSite` cho dispatch đã cố định sau link.
- Dùng `MutableCallSite`/`VolatileCallSite` khi cần thay target tại runtime với memory semantics phù hợp.

**Đừng nghĩ indy bắt buộc phải có mutable target.** `invokedynamic` có thể link đến `ConstantCallSite`; điều "dynamic" là **liên kết tại runtime**, không đồng nghĩa target phải đổi sau đó.

### Hai cơ chế có thể phối hợp

```text
CONSTANT_Dynamic metadata
         |
   resolve một lần
         |
         v
    static bootstrap argument
         |
         v
 invokedynamic bootstrap
         |
         v
       CallSite
         |
         v
  repeated target invocations
```

Trường hợp này rất hữu ích cho compiler/language runtime muốn đưa metadata đã resolve vào quá trình tạo call site. Nhưng vẫn cần tôn trọng điều kiện type, class loader, package/module và không tạo cycles trong condy dependencies.

## 11. Checklist đọc `javap` khi debug

1. **Xác minh class major version**: condy cần ≥ 55 (Java 11); indy cần ≥ 51.
2. **Phân biệt tag 17/18**: `Dynamic` biểu thị value; `InvokeDynamic` biểu thị call site.
3. **Kiểm tra `NameAndType` descriptor**: condy phải là field descriptor; indy phải là method descriptor.
4. **Tìm BootstrapMethods index**, đừng nhầm CP index với bootstrap index.
5. **Kiểm tra BSM `MethodHandle`**: reference kind, method name và descriptor phải khớp contract gọi BSM.
6. **Kiểm tra Lookup access và module** nếu việc resolve member gặp `IllegalAccessError` hoặc `BootstrapMethodError`.
7. **Kiểm tra giá trị trả về của BSM**: value tương thích với condy field type, `CallSite` có đúng type với indy descriptor.
8. **Xác định phạm vi cache**: condy symbolic reference vs indy instruction site. Đừng tự đặt toàn JVM cache theo tên.
9. **Phân biệt BSM exception và target exception**: lỗi khi linking có thể sticky; target exception sau link không phải lý do gọi lại bootstrap.
10. **Test concurrency** nếu bootstrap có side effect: nhiều initial invocations có thể chạy song song.
11. **Đừng nhầm đầu ra từ `Method.invoke` driver** với opcode do `javap` chứng minh trong generated class.
12. **Đối chiếu với JVMS `5.4.3.6`** thay vì đoán rằng mỗi lần thực thi `ldc`/`invokedynamic` đều chạy lại BSM.

## 12. Tự kiểm tra có đáp án

**Câu 1.** `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic` là hai tag nào?

**Đáp án:** 17 và 18. Cả hai trong CP nhưng biểu thị **value resolution** và **call-site linkage** khác nhau.

**Câu 2.** Một condy có descriptor `Ljava/lang/String;` thì tham số type mà JVM truyền cho BSM thường là `Class<?>` nào?

**Đáp án:** `String.class`; đó là field type của constant.

**Câu 3.** Indy có descriptor `(I)Ljava/lang/String;` thì BSM nhận `Class<?>` hay `MethodType`?

**Đáp án:** Thông thường `MethodType` mô tả method nhận `int` và trả `String`.

**Câu 4.** Condy BSM trả `"v1"`. Cùng `ldc` entry được thực thi 100 lần thì BSM có bị gọi 100 lần không?

**Đáp án:** Không. Sau successful resolution, JVM tái sử dụng resolved value. Ngoại lệ cần lưu ý là nhiều thread có thể **đua gọi bootstrap trong resolution ban đầu**, không phải một lần bootstrap cho mỗi `ldc`.

**Câu 5.** `CONSTANT_InvokeDynamic` BSM trả một `MethodHandle` nhưng không tạo `CallSite`. Hợp lệ không?

**Đáp án:** Không. BSM phải trả `CallSite` khác null, có `MethodType` khớp indy entry.

**Câu 6.** Sau khi indy đã link `VolatileCallSite`, code gọi `setTarget(newHandle)`. Có cần gọi BSM lần nữa không?

**Đáp án:** Không. Call site hiện hữu đổi target; instruction tiếp tục dùng chính site đã linked.

**Câu 7.** Hai indy instructions ở hai offset khác nhau cùng trỏ một CP entry tag 18. Có bắt buộc chung một `CallSite` không?

**Đáp án:** Không. Quy tắc indy linkage tính **theo instruction site**.

**Câu 8.** Condy BSM trả một mutable list. Giá trị của list có tự được đóng băng không?

**Đáp án:** Không. Reference được cache, object có thể thay đổi. Cần kiểm soát concurrency/state riêng.

**Câu 9.** Condy BSM trả `null` cho field descriptor `I`. JVM có dùng `0` mặc định không?

**Đáp án:** Không. `null` không convert thành primitive `int`; sẽ lỗi resolution (thường `BootstrapMethodError`).

**Câu 10.** Tại sao `javap -v` trong demo hiển thị `ldc #26` khác `invokedynamic #29`?

**Đáp án:** `ldc` load một giá trị resolved từ tag 17; `invokedynamic` thực thi call site đã liên kết bởi tag 18. Hai opcodes có stack behavior khác nhau.

**Câu 11.** Một bootstrap có counter static thông thường, hai thread cùng resolve. Counter luôn tăng chính xác một lần không?

**Đáp án:** Không. Bootstrap có thể được invoke đồng thời nhiều lần trong cuộc đua resolution, và counter unsynchronized có data race. Chỉ một kết quả liên kết được JVM chọn.

**Câu 12.** Exception được ném từ target `first(String)` của indy sau khi linkage có mặc định trở thành `BootstrapMethodError` không?

**Đáp án:** Không. Đây là exception của **target invocation**, không phải lỗi bootstrap resolution.

**Câu 13.** Cần tính một giá trị `Class<?>` tương ứng tên enum field khi runtime resolve, nên nghĩ tới API nào?

**Đáp án:** Condy cùng bootstrap có thể phù hợp; `ConstantBootstraps` có các phương thức như `enumConstant` và `primitiveClass` tùy mục tiêu, cần kiểm tra Javadoc/chữ ký chính xác.

**Câu 14.** Nếu một Java method khai báo `static final String x`, có chắc `javac` tạo `CONSTANT_Dynamic` không?

**Đáp án:** Không. Đó là cơ chế Java field khác; condy là một kind of constant-pool entry riêng.

**Câu 15.** Vì sao `CONSTANT_Dynamic` không phải "invokedynamic dạng trả về hằng"?

**Đáp án:** Khác tag, descriptor, opcode, loại type argument BSM, result validation và cache scope; condy không tạo một `CallSite` chỉ vì nó có bootstrap.

## 13. Ghi nhớ

- **Condy = tag 17 + field descriptor + `ldc` + typed value**, được JVM cache sau resolution.
- **Indy = tag 18 + method descriptor + `invokedynamic` + `CallSite`**, có target được gọi ở mỗi lần chạy instruction.
- **Cả hai dùng `BootstrapMethods` và `MethodHandle` bootstrap**, nhưng tham số type lần lượt thường là `Class<?>` và `MethodType`.
- **Cache scope khác:** Condy theo symbolic reference trong run-time CP; indy theo từng instruction `invokedynamic`.
- **Có thể relink indy target mà không chạy BSM lại** nếu dùng mutable/volatile call site; condy value không có `setTarget`.
- **"Dynamic" không đồng nghĩa "chạy bootstrap mỗi lần dùng".** Sau successful resolution, JVM tái sử dụng value hoặc linkage tương ứng.
- **Bootstrap có thể bị invoke đồng thời trong cuộc đua resolution**, vì vậy cần tránh side effects không thread-safe.
- **Đọc `javap -v` để kiểm chứng thật:** constant-pool tags, name/descriptor, BSM indexes, bytecode `ldc`/`invokedynamic` và JVM stdout.

### Nguồn chuẩn Java SE 17

- [JVMS `4.4.10 — `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10)
- [JVMS `4.7.23 — `BootstrapMethods` class-file attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23)
- [JVMS `5.4.3 và `5.4.3.6 — Resolution, bootstrap, caching và lỗi](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS `6.5 — `ldc`, `ldc_w`, `ldc2_w` và `invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html)
- [Oracle API — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html)
- [Oracle API — `CallSite`, `MutableCallSite`, `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [OpenJDK JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309)