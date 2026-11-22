# `CONSTANT_Dynamic` và nhu cầu vật chất hóa hằng số trong Java 11+

## 1. Bài toán: hằng số không phải lúc nào cũng ghi sẵn được thành byte

Từ **Java 11**, JVM hỗ trợ **dynamic class-file constants**, thường được gọi ngắn là **`condy`**, theo **JEP 309**. Cơ chế cốt lõi là entry **`CONSTANT_Dynamic` (tag 17)** trong constant pool của class file. Entry này mô tả **cách tính ra một giá trị** khi JVM cần sử dụng hằng số, thay vì phải nhét sẵn mọi byte/đối tượng Java vào class file.

Ở đây, “**vật chất hóa hằng số**” (materialization) nghĩa là **chuyển mô tả hằng số dạng symbolic trong class file thành một giá trị runtime cụ thể**: có thể là một số nguyên, `String`, một đối tượng tham chiếu, `Class`, `MethodHandle`, `VarHandle` hoặc giá trị thuộc một kiểu thích hợp khác. JVM thực hiện việc này bằng **bootstrap method**, xác minh kiểu kết quả rồi **ghi nhớ kết quả resolution** cho entry liên quan.

Ví dụ nhu cầu:

- Compiler cần nhúng một **đối tượng hằng theo logic ngôn ngữ** nhưng class-file constant pool truyền thống chỉ biểu diễn trực tiếp được một nhóm kiểu giới hạn.
- Runtime của một ngôn ngữ chạy trên JVM cần tạo một giá trị **chỉ tính một lần khi cần**, rồi sử dụng lại ở các lệnh nạp sau.
- Một thư viện/compiler muốn liên kết tượng trưng tới một `VarHandle`, enum constant, class mirror hoặc đối tượng phụ trợ được dựng từ các **tham số có sẵn trong class file**.
- Hệ thống phát sinh bytecode muốn mô tả việc tính giá trị ở mức constant pool **thay vì tự viết chuỗi lệnh Java trong `<clinit>` cho mọi trường hợp**.

**Không có từ khóa Java `condy`** trong mã nguồn ứng dụng thông thường. Đây là khả năng ở **class-file/JVM level**, hữu ích nhất cho compiler, bytecode tools, JVM language runtime và người phân tích bytecode. Bạn có thể **sử dụng Java 11 bình thường mà không tự tạo `CONSTANT_Dynamic`**.

Tính năng này **không lỗi thời**: JVM hiện đại vẫn hỗ trợ, và các API class-file mới cũng có cách mô hình hóa dynamic constants. Bài này tập trung vào quy tắc Java 11 vẫn còn đúng hiện nay, không dựa vào API nội bộ không được bảo đảm.

## 2. Phân biệt ba kiểu “hằng số” thường bị đánh đồng

| Cơ chế | Ví dụ | Khi/đâu giá trị được tạo | Đặc tính chính |
| --- | --- | --- | --- |
| **Compile-time constant** của Java | `static final int LIMIT = 100;`, `static final String LABEL = "ok";` | Giá trị biểu thức hằng đã biết ở compile time; có thể biểu diễn bằng các entry/attribute constant truyền thống | Có thể được compiler **inline** tại nơi sử dụng; không cần bootstrap động. |
| **`static final` nhưng không phải constant variable** | `static final Object TOKEN = new Object();` | Biểu thức khởi tạo thường chạy trong `<clinit>` của class chứa field khi class được khởi tạo | Giá trị được giữ trong **field**; tạo đối tượng tại class initialization, không đồng nghĩa condy. |
| **`CONSTANT_Dynamic` trong class file** | Constant-pool entry mô tả `bootstrap + name + field descriptor` | JVM thực hiện **resolution** bằng bootstrap khi giá trị cần được load/resolve | Kết quả resolution được dùng lại đối với **cùng symbolic constant-pool entry**. |

Đừng suy ra rằng mọi biến `final` hoặc mọi đối tượng chỉ tạo một lần là một `CONSTANT_Dynamic`. Ngược lại, một giá trị có thể được materialize qua condy **mà không có field `static final` nào**.

Ví dụ minh họa, **không sinh condy chỉ từ cú pháp này**:

```java
public class OrdinaryConstants {
    static final int ANSWER = 42;              // Compile-time constant.
    static final Object TOKEN = new Object();  // <clinit>, không phải condy.

    public static void main(String[] args) {
        System.out.println(ANSWER);
        System.out.println(TOKEN != null);
    }
}
```

Đây là chương trình Java độc lập, nhưng mục đích chỉ là **đối chiếu khái niệm**. Chạy:

```bash
javac --release 11 OrdinaryConstants.java
java OrdinaryConstants
```

**Stdout:**

```text
42
true
```

Muốn quan sát một **`CONSTANT_Dynamic` thực sự**, cần class file có entry tag 17. Chương trình đầy đủ ở mục 6 tạo class file đó bằng các API Java chuẩn và kiểm thử nó ở runtime.

## 3. Lý do cần “vật chất hóa” thay vì ghi sẵn giá trị

Một file `.class` là **mô tả tĩnh**: nó chứa bytecode, metadata, constant-pool entries và các thuộc tính. Nó không thể chèn trực tiếp một object tùy ý trong heap Java, chẳng hạn một `VarHandle` đã liên kết với field của một class, vào vài byte mà JVM hiểu là “đối tượng có sẵn”.

Trước hết cần **mô tả cách dựng/tra cứu giá trị**. JEP 309 cho phép entry constant pool mang một **bootstrap method handle**, một **name**, một **field descriptor** và có thể thêm các **static bootstrap arguments**. JVM dùng thông tin đó như “công thức” để tạo giá trị:

```text
CONSTANT_Dynamic trong .class
   |  +-- name ("MESSAGE")
   |  +-- descriptor ("Ljava/lang/String;")
   |  +-- bootstrap method reference
   |  +-- static arguments (nếu có)
   v
JVM resolution:
   resolve method handle và các đối số
   invoke bootstrap method
   kiểm tra/convert kết quả theo field descriptor
   lưu kết quả đã resolve cho entry
   |
   v
ldc / ldc_w / ldc2_w nhận giá trị runtime
   |
   +-- dùng lại kết quả đã resolve khi nạp cùng entry về sau
```

**Đây là constant về mặt cơ chế liên kết**, không phải khẳng định đối tượng bất biến về nội dung. Nếu bootstrap trả một `ArrayList` thay đổi được, các lần load sau có thể nhận lại **cùng object có state bị thay đổi**. Khi thiết kế bootstrap, nên ưu tiên **giá trị immutable hoặc effectively immutable**, tính toán xác định và tránh các side effect.

Một điểm nữa: mô tả condy trong **constant pool** có thể tồn tại trước khi giá trị vật chất hóa. Tạo hoặc load một class **không đồng nghĩa** mọi dynamic constant được tạo hết ngay lập tức. Thời điểm resolve phụ thuộc nhu cầu sử dụng và quy tắc linking; ví dụ ở mục 6 cho thấy `bootstrap` chưa chạy sau khi định nghĩa class nhưng chạy khi `ldc` thực sự được thực thi.

## 4. Cấu trúc `CONSTANT_Dynamic_info` trong class file

Theo **JVMS `4.4.10**, format là:

```text
CONSTANT_Dynamic_info {
    u1 tag;                          // 17
    u2 bootstrap_method_attr_index;  // Index 0-based trong BootstrapMethods
    u2 name_and_type_index;          // Trỏ tới CONSTANT_NameAndType_info
}
```

| Thành phần | Ý nghĩa và ràng buộc |
| --- | --- |
| `tag = 17` | Phân biệt với `CONSTANT_InvokeDynamic`, vốn dùng tag `18`. |
| `bootstrap_method_attr_index` | Chỉ vào **một phần tử** của mảng `bootstrap_methods` trong class attribute `BootstrapMethods`; chỉ số ở đây **bắt đầu từ 0**, không phải chỉ số constant pool. |
| `name_and_type_index` | Chỉ vào `CONSTANT_NameAndType_info` của constant pool; chứa **tên hằng** và **field descriptor**. |
| `BootstrapMethods` | Từng phần tử chứa `bootstrap_method_ref` tới `CONSTANT_MethodHandle`, cộng danh sách `bootstrap_arguments` (có thể rỗng). |
| `field descriptor` | Mô tả kiểu **giá trị hằng**, như `I`, `J`, `Ljava/lang/String;`, `Ljava/lang/Object;`. Đây **không phải method descriptor**. |

**Ví dụ symbolic**:

```text
#19 = Dynamic #0:#18  // bootstrap #0, name-and-type #18
#18 = NameAndType #16:#17
#16 = Utf8 "MESSAGE"
#17 = Utf8 "Ljava/lang/String;"
BootstrapMethods:
  0: REF_invokeStatic CondyMaterializationDemo.bootstrap(...)
```

`#19` là **chỉ số constant pool** 1-based, còn `#0` trong cú pháp dynamic là **chỉ số bảng bootstrap methods** 0-based. Hai hệ chỉ số khác nhau. Đoạn text trên là sơ đồ đọc classfile, không phải mã Java.

Để JVM công nhận `CONSTANT_Dynamic`, **major version của class file ít nhất là 55**, tương ứng **Java 11**. Java 8 (major 52) không đọc được classfile chứa format này; không thể “bật condy” chỉ bằng việc chạy compiler cũ hoặc đổi source level.

### `ldc`, `ldc_w` và `ldc2_w`

Một `CONSTANT_Dynamic` là **loadable constant**. JVM có thể đưa giá trị lên operand stack qua:

- `ldc`: nạp entry dùng chỉ số constant pool vừa trong operand một byte, với loại giá trị thích hợp.
- `ldc_w`: tương tự nhưng chỉ số constant pool dùng hai byte.
- `ldc2_w`: dùng khi dynamic constant có kiểu `long` (`J`) hoặc `double` (`D`).

Không đưa `long`/`double` vào `ldc` thường rồi hy vọng verifier tự điều chỉnh. Tương tự, đừng nhầm `ldc #19` với `invokedynamic`: `ldc` cần **một giá trị**, `invokedynamic` cần **một call site** (thường một `CallSite` được bootstrap tạo ra).

## 5. Bootstrap method: chữ ký, tham số và kiểu kết quả

Với dynamic constant, bộ tham số được JVM cung cấp cho bootstrap bắt đầu bằng:

```java
public static String bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type) {
    return "value-for:" + name;
}
```

Đây là **đoạn minh họa phương thức** cần import `java.lang.invoke.MethodHandles` và đặt trong một class cụ thể. Chương trình thực tế ở mục 6 dùng signature này.

Ba tham số “chuẩn”:

1. **`lookup`**: ngữ cảnh `MethodHandles.Lookup` của class **chứa `CONSTANT_Dynamic`**, dùng để áp dụng quy tắc truy cập.
2. **`name`**: tên chưa được qualified từ entry `NameAndType`, ví dụ `MESSAGE`.
3. **`type`**: `Class<?>` mô tả **field descriptor** của kết quả, ví dụ `String.class` hoặc `int.class`.

Bootstrap có thể nhận **các static arguments bổ sung** khai báo trong `BootstrapMethods`. JVM resolve những đối số đó rồi truyền vào sau ba tham số đầu. Đối số có thể là constant loadable khác, kể cả một `CONSTANT_Dynamic` khác; điều này cho phép **tổ hợp các mô tả hằng số**.

**Chữ ký được JVM gọi qua method handle**, không phải cơ chế “tên phương thức bắt buộc là `bootstrap`”. Chỉ yêu cầu bootstrap handle/tham số/kết quả phù hợp với hợp đồng JVM. Tên có thể khác và bootstrap không nhất thiết nằm trong class chứa dynamic constant, nhưng phải khả dụng với các quy tắc lookup/linking/visibility liên quan.

Kết quả được chuyển theo kiểu `type`. Ví dụ:

- Với descriptor `Ljava/lang/String;`, giá trị cuối phải tương thích với `String`; một `Integer` không thể trở thành `String`.
- Với descriptor nguyên thủy như `I`, JVM cần giá trị có thể convert/unbox theo quy tắc của method-handle invocation; `null` không hợp lệ.
- Với kiểu tham chiếu, **`null` có thể là một dynamic constant hợp lệ**. JDK cung cấp bootstrap chuẩn `ConstantBootstraps.nullConstant` cho trường hợp này.

Nếu bootstrap ném một exception không phải `Error`, JVM thường báo **`BootstrapMethodError`** bao nguyên nhân. Nếu bootstrap trả sai kiểu (hoặc `null` cho primitive), quá trình resolution cũng thất bại theo JVMS. Mục 9 nói rõ cách xử lý và caching của lỗi.

## 6. Chương trình Java 11 đầy đủ: tạo `CONSTANT_Dynamic` thật, quan sát materialization

**Bài demo này chạy được và không cần thư viện ngoài/JDK internal API.** Vì Java source thông thường không cung cấp cú pháp khai báo trực tiếp `CONSTANT_Dynamic`, chương trình dùng `DataOutputStream` để tạo **một class file version 55 trong bộ nhớ**, chứa phương thức `GeneratedCondy.value()` có bytecode:

```text
0: ldc #19  // CONSTANT_Dynamic MESSAGE : java.lang.String
2: areturn
```

`GeneratedCondy` không có constructor vì chỉ gọi phương thức static `value`. `bootstrap` nằm trong class `CondyMaterializationDemo`, tạo một `String` và tăng bộ đếm. Chương trình load class được sinh qua một `ClassLoader` tự định nghĩa rồi gọi `value()` **hai lần liên tiếp**.

Lưu thành **`CondyMaterializationDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicInteger;

public class CondyMaterializationDemo {
    private static final AtomicInteger BOOTSTRAP_CALLS = new AtomicInteger();

    public static String bootstrap(
            MethodHandles.Lookup lookup, String name, Class<?> type) {
        BOOTSTRAP_CALLS.incrementAndGet();
        if (type != String.class) {
            throw new IllegalArgumentException("Expected String");
        }
        return new String("value-for:" + name);
    }

    public static void main(String[] args) throws Exception {
        byte[] classBytes = generatedClassBytes();
        Class<?> generated = new BytecodeLoader().define(classBytes);
        Method value = generated.getMethod("value");

        System.out.println("classfileVersion=" +
                (((classBytes[6] & 0xff) << 8) | (classBytes[7] & 0xff)));
        System.out.println("beforeFirstLdc=" + BOOTSTRAP_CALLS.get());

        String first = (String) value.invoke(null);
        System.out.println("firstValue=" + first);
        System.out.println("afterFirstLdc=" + BOOTSTRAP_CALLS.get());

        String second = (String) value.invoke(null);
        System.out.println("secondValue=" + second);
        System.out.println("sameObject=" + (first == second));
        System.out.println("afterSecondLdc=" + BOOTSTRAP_CALLS.get());
    }

    private static byte[] generatedClassBytes() throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0); out.writeShort(55);
        out.writeShort(20);  // 19 constant-pool entries, indexed 1..19

        utf(out, "GeneratedCondy");                        // #1
        tag2(out, 7, 1);                                    // #2 Class
        utf(out, "java/lang/Object");                       // #3
        tag2(out, 7, 3);                                    // #4 Class
        utf(out, "value");                                  // #5
        utf(out, "()Ljava/lang/String;");                   // #6
        utf(out, "Code");                                   // #7
        utf(out, "BootstrapMethods");                       // #8
        utf(out, "CondyMaterializationDemo");               // #9
        tag2(out, 7, 9);                                    // #10 Class
        utf(out, "bootstrap");                              // #11
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;" +
                "Ljava/lang/String;Ljava/lang/Class;)" +
                "Ljava/lang/String;");                     // #12
        tag22(out, 12, 11, 12);                             // #13 NameAndType
        tag22(out, 10, 10, 13);                             // #14 Methodref
        out.writeByte(15); out.writeByte(6); out.writeShort(14); // #15 MethodHandle REF_invokeStatic
        utf(out, "MESSAGE");                                // #16
        utf(out, "Ljava/lang/String;");                     // #17
        tag22(out, 12, 16, 17);                             // #18 NameAndType
        tag22(out, 17, 0, 18);                              // #19 Dynamic

        out.writeShort(0x0021); // ACC_PUBLIC | ACC_SUPER
        out.writeShort(2); out.writeShort(4); // this/super
        out.writeShort(0); // interfaces_count
        out.writeShort(0); // fields_count
        out.writeShort(1); // methods_count

        out.writeShort(0x0009); // value: public static
        out.writeShort(5); out.writeShort(6); // name/descriptor
        out.writeShort(1); // method attributes
        out.writeShort(7); // Code
        out.writeInt(15); // Code attribute length
        out.writeShort(1); out.writeShort(0); // max_stack, max_locals
        out.writeInt(3); // code_length
        out.writeByte(0x12); out.writeByte(19); // ldc #19
        out.writeByte(0xb0);                   // areturn
        out.writeShort(0); // exception table
        out.writeShort(0); // Code attributes

        out.writeShort(1); // class attributes
        out.writeShort(8); // BootstrapMethods
        out.writeInt(6); // attribute length
        out.writeShort(1); // num_bootstrap_methods
        out.writeShort(15); // bootstrap_method_ref
        out.writeShort(0); // num_bootstrap_arguments
        out.flush();
        return bytes.toByteArray();
    }

    private static void utf(DataOutputStream out, String s) throws Exception {
        out.writeByte(1);
        out.writeUTF(s);
    }

    private static void tag2(DataOutputStream out, int tag, int value)
            throws Exception {
        out.writeByte(tag);
        out.writeShort(value);
    }

    private static void tag22(
            DataOutputStream out, int tag, int first, int second)
            throws Exception {
        out.writeByte(tag);
        out.writeShort(first);
        out.writeShort(second);
    }

    private static final class BytecodeLoader extends ClassLoader {
        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }
}
```

**Biên dịch và chạy** với JDK 17+ (các API và classfile target tương thích Java 11):

```bash
javac --release 11 CondyMaterializationDemo.java
java CondyMaterializationDemo
```

**Stdout chính xác:**

```text
classfileVersion=55
beforeFirstLdc=0
firstValue=value-for:MESSAGE
afterFirstLdc=1
secondValue=value-for:MESSAGE
sameObject=true
afterSecondLdc=1
```

Ví dụ trên đã được **biên dịch bằng `javac --release 11` và chạy thành công trên OpenJDK 24**, khớp toàn bộ bảy dòng stdout. Nó không gửi HTTP request, không kết nối mạng và không ghi lại class file ra đĩa: `GeneratedCondy` chỉ tồn tại trong bộ nhớ của tiến trình chạy.

### Giải thích chính xác tại sao materialization chỉ xảy ra khi cần

1. `DataOutputStream` tạo binary class file theo big-endian đúng JVMS: magic `0xCAFEBABE`, minor `0`, major `55`.
2. `#19` là một `CONSTANT_Dynamic`: tag `17`, bootstrap index `0`, `NameAndType #18` có `MESSAGE:Ljava/lang/String;`.
3. `#15` là `CONSTANT_MethodHandle`, `reference_kind=6` tương ứng `REF_invokeStatic`; nó trỏ tới `CondyMaterializationDemo.bootstrap(...)`.
4. Attribute `BootstrapMethods` có một entry, chỉ tới method handle `#15` và **không có đối số tĩnh bổ sung**.
5. Phương thức static `GeneratedCondy.value()` chỉ có `ldc #19` rồi `areturn`. `ldc` bắt buộc JVM resolve `#19` nếu chưa được resolve.
6. Sau khi `defineClass(...)` và `getMethod("value")`, `BOOTSTRAP_CALLS` vẫn bằng 0 trong ví dụ này. Lần gọi `value.invoke(null)` đầu khiến JVM gọi bootstrap để tạo `"value-for:MESSAGE"`.
7. Lần gọi thứ hai của **cùng phương thức và cùng entry `#19`** dùng kết quả đã được resolution; `BOOTSTRAP_CALLS` vẫn bằng 1 và `first == second` là `true`, tức cùng object tham chiếu.
8. `new String(...)` trong bootstrap cố ý tạo một đối tượng thay vì chỉ trả string literal. Vì vậy phép so sánh identity `==` minh họa việc tái sử dụng chính object đã materialize, không phải chỉ do string interning.

**Cảnh báo phạm vi thử nghiệm:** ví dụ gọi tuần tự một luồng. Nó chứng minh bootstrap **không chạy lại sau khi một entry đã resolve thành công**. Trong tình huống **nhiều thread đồng thời resolve lần đầu**, JVMS cho phép **bootstrap chạy nhiều lần cạnh tranh** và chọn một kết quả chung; không được khái quát `BOOTSTRAP_CALLS==1` thành bảo đảm tuyệt đối trong mọi cuộc đua đa luồng.

### Đây có phải một ví dụ viết bytecode “được khuyến nghị” không?

Không. Việc ghi thủ công constant-pool indexes bằng `DataOutputStream` chỉ để học **format thật và hành vi JVM**, giúp chạy được ngay cả khi chỉ có các API Java 11 công khai. Ở dự án phát sinh bytecode thực tế, nên dùng **API class-file chính thức có trong JDK phù hợp** (ví dụ `java.lang.classfile` từ JDK 24+) hoặc một công cụ bytecode được duy trì tốt. **Không** phụ thuộc lâu dài vào `jdk.internal.*`/API ASM nội bộ chỉ vì máy hiện tại chạy được với `--add-exports`.

## 7. Thời điểm resolve, caching, lỗi và cạnh tranh giữa các thread

Một entry condy được xem là **symbolic reference** trong run-time constant pool. Khi cần load, JVM thực hiện resolution theo **JVMS `5.4.3.6**.

### 7.1. Khi resolution thành công

**Kết quả được liên kết với đúng symbolic constant-pool entry**, không phải cache toàn JVM theo tên chuỗi. Đối với cùng entry:

- Lần dùng đầu cần giá trị: JVM resolve bằng bootstrap nếu entry chưa resolve.
- Các lần dùng sau: kết quả resolution đã tồn tại, không cần chạy lại bootstrap.
- Nếu kết quả là một object reference, các lần load cùng entry tham chiếu cùng object đã chọn; object ấy **có thể mutable**, nên code không được mặc định dữ liệu tự bất biến.
- Class khác, class loader khác hoặc một dynamic entry khác có “công thức” tương tự **không tự động chia sẻ cùng instance**. Đơn vị định danh của constant pool gắn với class/runtime context, không phải chỉ tên của hằng.

**Resolution có thể xảy ra trước thời điểm bạn đo được trong một phép thử cụ thể**, tùy cách JVM load/link/verify, nhưng lỗi resolution phải được báo ở điểm sử dụng tham chiếu theo JVMS. Cách đúng để tư duy là **resolution theo nhu cầu và trạng thái từng entry**, không đặt yêu cầu bootstrap nhất định chạy tại một timestamp hoặc thread cố định.

### 7.2. Bootstrap method có thể được gọi đồng thời

Đây là chi tiết đặc biệt cần nắm:

> Nếu hai thread cùng cố resolve một entry chưa có kết quả, JVM **có thể gọi bootstrap trên cả hai thread**; JVM chọn **một** kết quả để cài đặt cho các thread, còn những kết quả khác có thể bị bỏ qua.

Vì thế:

- **Không** để bootstrap có side effect như tạo đơn hàng, tính tiền, gửi email hay tăng counter nghiệp vụ với giả định chắc chắn “chỉ một lần”.
- Nếu bootstrap dùng state chung, phải thiết kế thread-safe, kiểm soát race và idempotency của chính bước khởi tạo.
- Không dựa vào thứ tự thread hoặc số lần bootstrap được gọi trong các cuộc đua. Điều JVM bảo đảm là **giá trị resolution được chọn và dùng ổn định** đối với entry sau khi thành công.

### 7.3. Khi resolution thất bại

- Nếu bootstrap ném một `Error`, lỗi tương ứng có thể được dùng làm kết quả thất bại của resolution.
- Nếu bootstrap ném một exception khác, quá trình resolution có thể thất bại bằng `BootstrapMethodError` có nguyên nhân là exception gốc.
- Nếu bootstrap trả kết quả không thể chuyển thành kiểu field descriptor (ví dụ `String` khi yêu cầu `int`, hoặc `null` cho primitive), JVM báo lỗi theo quy tắc bootstrap resolution.
- Nếu một constant A phụ thuộc vào chính A qua danh sách static bootstrap arguments (trực tiếp hoặc gián tiếp), JVM phải thất bại theo quy tắc phụ thuộc vòng, có thể bằng `StackOverflowError`. Đừng tạo cycle rồi mong JVM trả placeholder `null`.
- **Sau khi một symbolic condy entry đã resolve thất bại**, các lần dùng sau **tiếp tục thất bại**, bootstrap không được chạy lại chỉ để thử lần nữa. Vì thế không thiết kế bootstrap dựa vào một dịch vụ ngoài đang có thể sẵn sàng “lần thứ hai”.

Tránh bắt `BootstrapMethodError` rồi âm thầm coi như đã có constant mặc định hợp lệ. Ở compiler/runtime, đây thường là lỗi liên kết/định nghĩa công thức, cần diagnostic rõ class, dynamic name, expected type, bootstrap signature và cause chain. Đừng in hoặc lộ dữ liệu bí mật trong logs.

## 8. `CONSTANT_Dynamic` khác `CONSTANT_InvokeDynamic` như thế nào?

Hai entry có cấu trúc bytecode trông giống nhau nhưng **không cùng ý nghĩa**:

| Đặc tính | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Constant-pool tag | **17** | **18** |
| Xuất hiện | Java 11 / class file major 55 | Có từ Java 7 / class file major 51 |
| Phần `NameAndType` | **Field descriptor** (kiểu giá trị) | **Method descriptor** (kiểu call site) |
| Mục tiêu bootstrap | Tạo một **giá trị constant** phù hợp với type | Tạo một **`CallSite`** có method type phù hợp |
| Lệnh sử dụng | `ldc`, `ldc_w`, `ldc2_w` hoặc làm static bootstrap argument | Lệnh `invokedynamic` |
| Kết quả liên kết | Một giá trị primitive hoặc reference được resolve | Một call site để thực hiện lời gọi |

Ví dụ `StringConcatFactory` hoặc cơ chế dynamic call sites thuộc chủ đề `invokedynamic`, không phải chứng minh trong class file có `CONSTANT_Dynamic`. Nếu thấy cả hai trong cùng class, phải kiểm tra **tag, descriptor và instruction** để phân biệt.

Một dynamic constant còn có thể là **static bootstrap argument của một condy khác hoặc của invokedynamic**, cho phép vật chất hóa các dữ liệu cấu hình/đối tượng cần thiết để liên kết lời gọi. Điều này giúp diễn tả nhiều “công thức tạo hằng số” có thể tổ hợp, nhưng vẫn cần tránh dependency cycles.

## 9. Bootstrap chuẩn do JDK cung cấp: `ConstantBootstraps`

Java 11 có class `java.lang.invoke.ConstantBootstraps` để hỗ trợ một số dạng giá trị được tính động. Không phải mọi ứng dụng cần tự viết bootstrap riêng.

| Bootstrap trong Java 11 | Giá trị được tạo hoặc tra cứu |
| --- | --- |
| `nullConstant(lookup, name, type)` | Giá trị `null` cho một **reference type**. |
| `primitiveClass(lookup, name, type)` | `Class` mirror của primitive theo descriptor, ví dụ `"I"` cho `int.class`. |
| `enumConstant(lookup, name, type)` | Enum constant có tên tương ứng. |
| `getStaticFinal(...)` | Giá trị của một static final field được mô tả, với kiểm tra truy cập thích hợp. |
| `fieldVarHandle(...)` | `VarHandle` truy cập instance field. |
| `staticFieldVarHandle(...)` | `VarHandle` cho static field. |
| `arrayVarHandle(...)` | `VarHandle` để truy cập phần tử mảng. |
| `invoke(...)` | Gọi một method handle đã được mô tả cùng các đối số thích hợp để trả ra giá trị. |

**Không hiểu lầm:** gọi trực tiếp `ConstantBootstraps.nullConstant(...)` như một method Java **không tự tạo** entry `CONSTANT_Dynamic` trong class file. Để áp dụng cơ chế constant resolution, classfile phải **tham chiếu bootstrap qua `CONSTANT_Dynamic` và `BootstrapMethods`**.

Thí dụ **minh họa lời gọi trực tiếp** để hiểu contract, không phải chương trình phát sinh condy:

```java
Object absent = ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "ANY", String.class);
Class<?> primitive = ConstantBootstraps.primitiveClass(
        MethodHandles.lookup(), "I", Class.class);
```

Các đoạn trên cần import `ConstantBootstraps` và `MethodHandles`. `absent == null` và `primitive == int.class`. Những `ConstantBootstraps` được provider/JDK cung cấp được thiết kế cho việc liên kết hằng số, không phải API “cache mọi lời gọi method” của Java source.

Lưu ý **phiên bản API**: Java 11 không có toàn bộ tiện ích của JDK mới hơn. Nếu dự án phải biên dịch trên Java 11, tra đúng Javadoc phiên bản mục tiêu thay vì sao chép một method mới chỉ có trên JDK hiện đại.

## 10. Góc nhìn hiện đại: mô tả symbol và tạo bytecode an toàn

Bên cạnh classfile tag 17 từ Java 11, JDK phát triển thêm các **API công khai** để mô tả constant ở mức nominal:

- **`java.lang.constant.DynamicConstantDesc`** (từ Java 12): mô tả bằng object Java một **công thức dynamic constant** (`bootstrap + name + type + args`). Đây là descriptor/model, **chưa phải** kết quả materialize trong `.class`.
- **`java.lang.constant.ConstantDesc`** (Java 12+): giao diện cho các nominal descriptors có thể được resolve trong ngữ cảnh lookup. Việc gọi `resolveConstantDesc(...)` một cách phản chiếu có hợp đồng riêng; **không đồng nhất việc đó với JVM cache kết quả của một constant-pool entry**.
- **`java.lang.classfile.constantpool.ConstantDynamicEntry`** và API `java.lang.classfile` (JDK 24+): mô hình hóa entry condy khi đọc, tạo hoặc chuyển đổi classfile bằng API chính thức.

**Khuyến nghị theo môi trường:** nếu sản phẩm chạy Java 11, bytecode target Java 11 vẫn có thể chứa `CONSTANT_Dynamic`; hãy dùng compiler hoặc thư viện bytecode có hỗ trợ JDK/classfile target tương ứng. Nếu công cụ được chạy trên JDK 24+, Class-File API là lựa chọn chính thức phù hợp. Cần phân biệt **JDK chạy công cụ tạo bytecode** với **JDK đích sẽ nạp classfile**.

Ví dụ một bytecode generator chạy trên JDK 24 hoàn toàn có thể xuất classfile major 55 cho Java 11 nếu nó tuân theo đúng format, nhưng **không được** đưa lời gọi `java.lang.classfile` trực tiếp vào source dự kiến biên dịch bằng `javac --release 11`.

## 11. Lỗi thường gặp và cách sửa

| Hiểu lầm / lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `CONSTANT_Dynamic` là keyword Java | Tìm cú pháp source không tồn tại | Hiểu đây là **tag 17 trong classfile**; dùng compiler/bytecode generator. |
| Nghĩ `static final Object X = new Object()` tự tạo condy | Nhầm class initialization với constant-pool resolution | Kiểm tra `javap -v` hoặc bytecode thực tế. |
| Nghĩ mọi dynamic constant chạy bootstrap ngay lúc load class | Có thể chưa cần materialize | Quan sát resolution khi giá trị được dùng, đừng dựa timestamp. |
| Nghĩ bootstrap chắc chắn chạy **đúng một lần** kể cả khi nhiều thread tranh chấp | JVM có thể gọi cạnh tranh nhiều lần | Thiết kế bootstrap thread-safe, tránh side effect. |
| Nghĩ kết quả bootstrap tự immutable | Giá trị reference có thể trỏ tới object mutable | Ưu tiên immutable và không sửa object chung. |
| Nhầm tag **17** với tag **18** | Đọc sai descriptor/instruction | Condy tạo giá trị; invokedynamic tạo call site. |
| Điền **method descriptor** cho condy `NameAndType` | Classfile sai cấu trúc/verification | Dùng **field descriptor**. |
| Nhầm index của `BootstrapMethods` với chỉ số constant pool | Trỏ sai bootstrap | Phân biệt bootstrap index 0-based và CP index 1-based. |
| Trả giá trị sai type hoặc `null` cho primitive | Bootstrap resolution thất bại | Đảm bảo tương thích field descriptor. |
| Nghĩ bootstrap có thể dựa vào mạng rồi retry sau khi fail | Failure of resolution có thể được cache | Giữ bootstrap xác định, độc lập side effect/dịch vụ nhất thời. |
| Tạo vòng phụ thuộc giữa các dynamic constants | Có thể gây `StackOverflowError` | Không tạo cycle trong các static bootstrap args. |
| Cho class file major 55 chạy trên Java 8 | JVM cũ không hiểu classfile/tag mới | Chạy JDK 11+ với đúng version target. |
| Dùng `jdk.internal.org.objectweb.asm` trong production để tạo condy | Internal API không phải hợp đồng public | Dùng bytecode tool được duy trì hoặc Class-File API trên JDK phù hợp. |
| Nghĩ `DynamicConstantDesc` (Java 12+) có trên Java 11 | Lỗi biên dịch | Tách API JVM Java 11 và API nominal descriptor thêm ở Java 12. |
| Nghĩ constant có cùng tên thì chia sẻ cache xuyên class loader | Cache theo entry/runtime context | Không dùng tên hằng làm khóa cache toàn hệ thống. |

## 12. Câu hỏi tự kiểm tra

**Câu 1:** Từ Java version nào JVM hiểu `CONSTANT_Dynamic`? Tag constant pool và major class file tối thiểu là gì?

**Đáp án:** Java **11**, tag **17**, classfile major **55**.

**Câu 2:** `CONSTANT_Dynamic` trả một giá trị hay một `CallSite`?

**Đáp án:** **Một giá trị** primitive hoặc reference theo **field descriptor**. `CallSite` gắn với `CONSTANT_InvokeDynamic` và lệnh `invokedynamic`.

**Câu 3:** Bootstrap cho dynamic constant nhận ba tham số đầu phổ biến nào?

**Đáp án:** `MethodHandles.Lookup` (ngữ cảnh caller), `String` (name), `Class<?>` (type theo field descriptor), sau đó có thể có static bootstrap arguments bổ sung.

**Câu 4:** Vì sao `beforeFirstLdc=0` nhưng `afterFirstLdc=1` trong demo?

**Đáp án:** Class mới được định nghĩa nhưng chưa load dynamic constant trong chương trình. Khi `ldc #19` lần đầu được thực thi, JVM resolve entry và gọi bootstrap.

**Câu 5:** Vì sao `sameObject=true` trong demo? Có phải mọi string Java đều cùng instance không?

**Đáp án:** Không. Hai lần `ldc` của **cùng đã-resolve condy entry** dùng cùng object được JVM chọn. Bootstrap cố ý `new String(...)` để phân biệt với string interning.

**Câu 6:** Khi hai thread đồng thời resolve lần đầu, có thể thấy bootstrap được gọi hơn một lần không?

**Đáp án:** **Có.** JVM có thể chạy bootstrap đồng thời, chọn một kết quả được công bố cho các thread; vì thế bootstrap không nên có side effect không thể lặp.

**Câu 7:** Nếu bootstrap lần đầu ném exception và resolution thất bại, lần `ldc` sau có tự chạy lại bootstrap để “thử may mắn” không?

**Đáp án:** **Không.** Thất bại resolution của symbolic reference được ghi nhớ; việc dùng lại báo lỗi tương ứng thay vì retry bootstrap.

**Câu 8:** `static final` và condy có bắt buộc xuất hiện cùng nhau không?

**Đáp án:** Không. `static final` là field/modifier của Java source và cơ chế class initialization; `CONSTANT_Dynamic` là một entry trong class file được nạp bằng bytecode constant-loading.

**Câu 9:** Nếu dùng `DynamicConstantDesc` trên JDK 24, đối tượng descriptor đó có tự chứng minh JVM đã cache giá trị của một `CONSTANT_Dynamic` không?

**Đáp án:** Không. `DynamicConstantDesc` là mô tả nominal (có từ Java 12). Chỉ khi nó được dùng để tạo entry classfile thực và JVM resolve entry theo hợp đồng condy, mới có caching của constant-pool resolution.

**Ghi nhớ:** **`CONSTANT_Dynamic` (tag 17, Java 11/classfile 55)** là công thức **vật chất hóa một giá trị tại resolution**: `bootstrap method handle + name + field descriptor + optional static arguments`. Lệnh `ldc` có thể kích hoạt resolution, JVM kiểm tra type và **dùng lại kết quả cho cùng entry**. Không nhầm với `static final`, `<clinit>` hoặc `invokedynamic`. Trong bootstrap, tránh side effect, xử lý concurrency và lỗi cẩn thận; dùng công cụ bytecode/API công khai phù hợp với JDK target.

**Tài liệu chuẩn:** [OpenJDK — JEP 309: Dynamic Class-File Constants](https://openjdk.org/jeps/309); [JVMS Java SE 11 — `4.4.10, CONSTANT_Dynamic](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10); [JVMS Java SE 11 — `5.4.3.6, resolution và bootstrap](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6); [Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html); [Java SE 24 — ConstantDynamicEntry](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/constantpool/ConstantDynamicEntry.html).
