# Phân biệt kiểm tra của compiler với xác minh bytecode của JVM

Một tệp Java **biên dịch thành công** chưa có nghĩa mọi lớp sẽ được JVM chấp nhận, và việc JVM **xác minh bytecode thành công** cũng chưa bảo đảm chương trình không gặp exception hoặc chạy đúng yêu cầu nghiệp vụ. Hai hệ thống kiểm tra này làm việc ở **những thời điểm và trên những dạng dữ liệu khác nhau**:

- **Compiler, ví dụ `javac`:** phân tích **mã nguồn Java** theo quy tắc ngôn ngữ, kiểm tra kiểu, tên, quyền truy cập, luồng điều khiển và phát ra tệp `.class`.
- **JVM:** đọc **classfile/bytecode** (có thể từ `javac` hoặc một trình sinh/chỉnh sửa bytecode khác), kiểm tra định dạng classfile và xác minh các ràng buộc an toàn tĩnh của bytecode trong quá trình tải/liên kết lớp.
- **Runtime:** khi code đã được nạp, liên kết và thực thi, JVM tiếp tục thực hiện các kiểm tra động như cast, truy cập phần tử mảng, kiểm tra `null` và resolution của tham chiếu ký hiệu khi cần. Các lỗi này không đồng nhất với lỗi verifier.

Ví dụ, `javac` từ chối một phương thức Java khai báo trả về `int` nhưng lại viết `return "hello";`. Nếu một công cụ khác **tạo thẳng classfile sai kiểu stack** mà không đi qua `javac`, JVM verifier có thể từ chối classfile bằng `VerifyError`. Trái lại, classfile hoàn toàn hợp lệ và được verifier chấp nhận vẫn có thể ném `ArithmeticException` do chia cho 0 khi chạy.

Đây là bài học thuộc chủ đề **kiểm chứng đầu ra biên dịch**: hiểu giới hạn từng tầng để kiểm thử, chẩn đoán, triển khai và xử lý bytecode một cách chính xác trên Java 17+.

## 1. Ba câu hỏi ở ba giai đoạn

| Giai đoạn | Dữ liệu đầu vào | Câu hỏi tiêu biểu | Kết quả/lỗi điển hình |
| --- | --- | --- | --- |
| Compile-time | `.java` và dependency mà compiler nhìn thấy | Mã nguồn có hợp lệ theo ngôn ngữ và kiểu tĩnh không? | `javac` sinh `.class` hoặc báo lỗi compile |
| Class loading và linking | Bytecode trong `.class`, metadata và các lớp liên quan | Classfile có hợp lệ, bytecode có thỏa các ràng buộc verifier không? | Lớp được nạp/liên kết hoặc có `ClassFormatError`, `VerifyError`... |
| Resolution và execution | Các lớp đã được nạp/đang được liên kết, dữ liệu chạy thật | Tham chiếu có khớp dependency hiện tại? Giá trị tại runtime có hợp lệ? | Thành công, `NoSuchMethodError`, `ClassCastException`, `NullPointerException`, kết quả nghiệp vụ sai... |

**Chú ý về thời điểm:** JVM specification mô tả việc *loading, linking (verification, preparation, resolution), initialization* và execution. JVM có thể **thực hiện resolution muộn** hoặc tiến hành một số công việc khi lớp được sử dụng. Vì thế không nên khẳng định mọi lỗi JVM đều xuất hiện ngay tại câu lệnh bắt đầu `java` hay ngay khi `ClassLoader#defineClass` trả về.

### Sơ đồ tổng thể

~~~text
Mã nguồn Java
      |
      | javac: parse, name/type checking,
      |        definite assignment, access rules...
      v
Tệp .class
      |
      | JVM loading: định vị/đọc classfile
      v
Đọc định dạng classfile
      |
      | sai cấu trúc, constant pool, magic...
      +---------------------> ClassFormatError (tùy lỗi)
      |
      v
Linking / verification
      |
      | quy tắc kiểu của bytecode, stack/local,
      | nhánh, frames và các bất biến của mã máy ảo
      +---------------------> VerifyError (tùy lỗi)
      |
      v
Resolution / initialization / execution
      |
      +---------------------> LinkageError khác,
      |                        exceptions hoặc bug logic
      v
Hành vi chương trình
~~~

Sơ đồ là **mô hình tư duy**, không phải cam kết rằng mọi JVM triển khai từng thao tác thành một bước tuyến tính đúng như hình. Điều quan trọng là phân biệt **nguyên nhân của từng lỗi**, thay vì dựa duy nhất vào thời điểm quan sát exception.

## 2. `javac` kiểm tra những gì?

Với một chương trình Java nguồn, compiler thường:

1. **Phân tích từ vựng và cú pháp:** token, dấu ngoặc, khai báo, cấu trúc câu lệnh.
2. **Phân giải tên và kiểu:** các biến, package, method, overload, generic types và conversion có phù hợp?
3. **Kiểm tra phạm vi truy cập:** `private`, `protected`, package-private, `public`; với JPMS còn có module readability và exports trong cấu hình compile.
4. **Phân tích luồng điều khiển:** các trường hợp biến cục bộ chưa được gán trước khi đọc (*definite assignment*), nhánh không có đường hoàn thành hợp lệ, exception được kiểm tra...
5. **Áp dụng thông tin compile-time khác:** hằng, annotation processing nếu được bật và được cấu hình.
6. **Tạo classfile:** ghi metadata, constant pool, bytecode, exception table, thông tin frame/stack map khi cần và các attribute thích hợp.

Compiler dùng thông tin **đang có tại lần biên dịch đó**. Một ứng dụng sau này có thể được chạy với dependency khác phiên bản, trên runtime khác, hoặc bytecode bị công cụ bên thứ ba biến đổi. Vì vậy thành công của `javac` là bằng chứng **mã nguồn hợp lệ trong môi trường compile**, không phải chứng thư về mọi môi trường runtime có thể xảy ra.

### Ví dụ: lỗi kiểu được chặn trước khi có classfile

Tệp **`SourceTypeError.java`**:

~~~java
public class SourceTypeError {
    static int value() {
        return "hello";
    }
}
~~~

Biên dịch:

~~~sh
javac -encoding UTF-8 SourceTypeError.java
~~~

`javac` thất bại vì kiểu trả về là `int` nhưng biểu thức `"hello"` có kiểu `String`. Nội dung diagnostic thường gồm ý:

~~~text
incompatible types: String cannot be converted to int
~~~

Thông báo đầy đủ, dòng, cột và định dạng có thể khác theo JDK. **Không có phép thử bytecode verifier nào ở đây**: nguồn chưa vượt qua kiểm tra ngôn ngữ.

Nếu sửa `return "hello";` thành `return 42;` thì method hợp lệ về kiểu và có thể được biên dịch.

### Ví dụ khác: kiểm tra definite assignment

Đoạn sau **cố ý không hợp lệ**, không phải chương trình chạy độc lập:

~~~java
static int read(boolean condition) {
    int number;
    if (condition) {
        number = 10;
    }
    return number; // variable number might not have been initialized
}
~~~

Compiler phải xét đường chạy khi `condition == false`; ở nhánh đó `number` chưa được gán. Đây là **kiểm tra nguồn/luồng điều khiển của compiler**, không phải lỗi `VerifyError` sau khi vào JVM.

## 3. JVM không nhất thiết nhận classfile từ `javac`

Tệp `.class` có thể do:

- `javac` tạo từ source Java;
- trình biên dịch của một ngôn ngữ JVM khác tạo;
- framework tạo proxy hoặc class động;
- trình sinh/biến đổi bytecode (instrumentation, weaving, code generation) chỉnh sửa;
- artifact trên đĩa bị hỏng, bị thay thế hoặc không hoàn chỉnh.

Do đó JVM không thể chỉ nói “nếu có `.class` thì chắc compiler đã kiểm tra hết”. Nó phải kiểm tra **định dạng và các ràng buộc của chính classfile** khi tải/liên kết.

Một classfile chứa cấu trúc như:

~~~text
magic = 0xCAFEBABE
minor_version, major_version
constant_pool
access_flags, this_class, super_class
interfaces, fields, methods
attributes (trong đó method có thể có Code attribute)
~~~

Đây là **sơ đồ cấu trúc** chứ không phải một tệp nhị phân hợp lệ để sao chép trực tiếp. Trong `Code` attribute có bytecode instructions, `max_stack`, `max_locals`, exception handlers và có thể có `StackMapTable`.

Hai loại kiểm tra thường được phân biệt:

- **Kiểm tra định dạng classfile:** bytes có biểu diễn một classfile đúng cấu trúc/phiên bản không? Hỏng header, constant pool, chỉ số hoặc thuộc tính có thể dẫn tới `ClassFormatError` hay lỗi liên quan.
- **Bytecode verification:** bytecode đã đọc có thỏa các quy tắc an toàn tĩnh của JVM không? Chẳng hạn không thể sử dụng tham chiếu object như một `int` trên operand stack; luồng điều khiển/kiểu local phải nhất quán tại các điểm giao nhau. Vi phạm có thể dẫn tới `VerifyError`.

`ClassFormatError` và `VerifyError` đều là những loại `LinkageError`, nhưng **không thể dùng thay nhau**. Sai cấu trúc classfile không đồng nghĩa verifier đã phân tích và phát hiện lỗi kiểu bytecode.

## 4. Verifier quan tâm tới operand stack, local variables và control flow

Trong bytecode JVM, nhiều instruction không mang thông tin kiểu nguồn Java rõ ràng như câu lệnh cấp cao. Verifier kiểm tra kiểu của dữ liệu qua luồng instruction.

Ví dụ ý nghĩa một vài instruction:

| Instruction | Ý nghĩa khái quát |
| --- | --- |
| `iconst_1` | Đưa giá trị kiểu `int` bằng 1 lên operand stack |
| `aconst_null` | Đưa tham chiếu `null` lên operand stack |
| `iadd` | Lấy hai giá trị `int` từ stack, cộng và đẩy `int` |
| `ireturn` | Trả về `int` từ phương thức có kiểu trả về phù hợp |
| `areturn` | Trả về tham chiếu có kiểu phù hợp |
| `iload_0` | Đọc giá trị `int` từ local slot 0 |
| `aload_0` | Đọc tham chiếu từ local slot 0 |

Ví dụ một method Java:

~~~java
static int answer() {
    return 42;
}
~~~

thường được biên dịch thành bytecode có dạng tương đương:

~~~text
bipush 42
ireturn
~~~

Trong khi đó, chuỗi instruction dưới đây **cố ý sai** nếu method có descriptor trả về `int`:

~~~text
aconst_null
ireturn
~~~

`aconst_null` đưa một **reference**, còn `ireturn` yêu cầu **int**. Nếu một classfile có phương thức kiểu `()I` với đúng chuỗi instruction không hợp lệ này, verifier phải từ chối khi xác minh phương thức. Đây là vấn đề **kiểu của bytecode**, khác với code Java nguồn vốn đã bị `javac` chặn trước đó.

Verifier còn xử lý các điều kiện như:

- Không sử dụng stack khi không đủ toán hạng (*stack underflow*).
- Kết hợp kiểu operand/local đúng tại các điểm nhiều nhánh hợp lưu.
- Không truy cập local vượt `max_locals` hay dùng local với kiểu chưa hợp lệ.
- Tuân thủ quy tắc khởi tạo object/constructor và kiểu reference.
- Chỉ thực hiện nhảy tới instruction boundary hợp lệ.
- Kiểm tra các stack-map frames theo quy tắc áp dụng cho classfile version phù hợp.

**StackMapTable** cung cấp thông tin trạng thái kiểu tại những vị trí luồng điều khiển trong nhiều classfile hiện đại. Verifier dùng thông tin này theo cơ chế của Java Virtual Machine Specification. Không nên mặc định mọi classfile từ mọi phiên bản Java có cùng cấu trúc stack map; cách xác minh thay đổi theo version và trường hợp.

## 5. Chạy ví dụ Java 17+: nguồn hợp lệ, verifier chấp nhận, runtime vẫn có thể lỗi

Tệp **`RuntimeBehaviorDemo.java`**:

~~~java
public class RuntimeBehaviorDemo {
    static int divide(int numerator, int denominator) {
        return numerator / denominator;
    }

    public static void main(String[] args) {
        System.out.println("Before division");

        try {
            System.out.println(divide(12, 0));
        } catch (ArithmeticException ex) {
            System.out.println("Runtime exception: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("After division");
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~sh
javac --release 17 -encoding UTF-8 RuntimeBehaviorDemo.java
java RuntimeBehaviorDemo
~~~

**Stdout chính xác:**

~~~text
Before division
Runtime exception: ArithmeticException
After division
~~~

Chương trình hợp lệ về cú pháp và kiểu: phương thức trả `int` và thực hiện phép chia integer đúng kiểu. JVM có thể xác minh bytecode của lớp vì instruction hợp lệ. Nhưng khi `denominator == 0`, phép chia số nguyên gây `ArithmeticException` **trong lúc chạy**.

Đây không phải lỗi compiler hay verifier. `javac` không thể chứng minh mọi giá trị runtime có thể khác 0 trong mọi chương trình. Bytecode verifier cũng không có nhiệm vụ kiểm tra logic nghiệp vụ hay mọi input runtime.

### Quan sát bytecode do `javac` sinh

Sau khi biên dịch tệp trên:

~~~sh
javap -c -p RuntimeBehaviorDemo
~~~

`javap -c` giải mã các instruction trong phương thức. Bạn sẽ thấy trong `divide` có các instruction load tham số integer và `idiv`; trong `main` có phần tạo/catch exception. Tên tệp, nhãn nhảy, số offset và hình thức in phụ thuộc classfile/compiler, nên **không chép một đoạn output cố định làm tiêu chí đúng**.

Khi cần xem thông tin classfile và frame chi tiết hơn:

~~~sh
javap -v RuntimeBehaviorDemo
~~~

`javap` là công cụ **hiển thị/phân tích classfile**, không phải lệnh “chạy verifier và bảo đảm toàn bộ chương trình an toàn”. Việc `javap` có thể đọc một tệp không đồng nghĩa JVM đã xác minh thành công mọi method hoặc sẽ chạy đúng.

## 6. Thí nghiệm 1: lớp sai định dạng và `ClassFormatError`

Ta sẽ đưa một mảng bytes **cố ý không phải classfile hợp lệ** cho `ClassLoader#defineClass(...)`. Đây là thí nghiệm lỗi **định dạng**, không phải lỗi kiểu của bytecode.

Tệp **`MalformedClassDemo.java`**:

~~~java
public class MalformedClassDemo {
    private static final class BytesLoader extends ClassLoader {
        Class<?> defineBadClass() {
            byte[] notAClassFile = {0, 0, 0, 0};
            return defineClass("Broken", notAClassFile,
                    0, notAClassFile.length);
        }
    }

    public static void main(String[] args) {
        try {
            new BytesLoader().defineBadClass();
            System.out.println("Unexpected success");
        } catch (ClassFormatError err) {
            System.out.println("Rejected: "
                    + err.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 -encoding UTF-8 MalformedClassDemo.java
java MalformedClassDemo
~~~

**Stdout dự kiến trên JVM chuẩn:**

~~~text
Rejected: ClassFormatError
~~~

Mảng chỉ có bốn byte 0x00, không mang magic number `0xCAFEBABE` hay cấu trúc classfile. JVM không thể nạp nó như một classfile Java hợp lệ; `ClassFormatError` là tín hiệu phù hợp cho lỗi định dạng.

Đừng kết luận “JVM đã chạy verifier của method và phát hiện sai kiểu” trong thí nghiệm này: **chưa hề có method bytecode hợp lệ để verifier phân tích**.

### Tránh cách thử phá classfile thật

Đừng sửa hay xóa byte ngẫu nhiên trong JAR/classfile production để “thử verifier”. Những lỗi phát sinh có thể là lỗi cấu trúc, checksum, classpath hoặc class loader — không minh họa chính xác việc kiểm tra kiểu bytecode. Dùng dữ liệu thử riêng, không ghi đè artifact đang dùng.

## 7. Thí nghiệm 2: classfile có cấu trúc cơ bản nhưng code sai kiểu

Để phân biệt rõ `VerifyError` với `ClassFormatError`, có thể **sinh một classfile tối giản trong bộ nhớ** có method trả `int` nhưng nội dung instruction lại dùng `aconst_null; ireturn`. Mục đích chỉ để học verifier. Không dùng đoạn sinh bytecode kiểu này trong ứng dụng production; hãy dùng thư viện/classfile tooling phù hợp và kiểm thử nghiêm ngặt nếu thực sự cần biến đổi class.

Ở ví dụ, classfile giả lập dùng **classfile major version 49 (Java 5)**, chỉ vì dạng cũ này cho phép thể hiện ví dụ tối giản mà không phải thêm `StackMapTable`. **Chương trình tạo nó vẫn biên dịch/chạy bằng JDK 17+.** Không nên suy ra classfile version 49 là target khuyến nghị cho dự án hiện đại.

Tệp độc lập **`VerifyErrorDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;

public class VerifyErrorDemo {
    private static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);          // CONSTANT_Utf8
        out.writeUTF(value);
    }

    private static byte[] invalidClass() throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);     // minor version
            out.writeShort(49);    // major version: Java 5

            out.writeShort(9);     // constant_pool_count
            utf8(out, "Broken");   // #1
            out.writeByte(7);      // #2 CONSTANT_Class
            out.writeShort(1);
            utf8(out, "java/lang/Object"); // #3
            out.writeByte(7);      // #4 CONSTANT_Class
            out.writeShort(3);
            utf8(out, "value");    // #5
            utf8(out, "()I");      // #6
            utf8(out, "Code");     // #7
            utf8(out, "SourceFile"); // #8 (unused by attributes)

            out.writeShort(0x0021); // public + ACC_SUPER
            out.writeShort(2);      // this_class = Broken
            out.writeShort(4);      // super_class = Object
            out.writeShort(0);      // interfaces_count
            out.writeShort(0);      // fields_count
            out.writeShort(1);      // methods_count

            out.writeShort(0x0009); // public static
            out.writeShort(5);      // name: value
            out.writeShort(6);      // descriptor: ()I
            out.writeShort(1);      // method attributes_count

            out.writeShort(7);      // attribute name: Code
            out.writeInt(14);       // Code attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(0);      // max_locals
            out.writeInt(2);        // code_length
            out.writeByte(0x01);    // aconst_null
            out.writeByte(0xAC);    // ireturn: expects int
            out.writeShort(0);      // exception_table_length
            out.writeShort(0);      // Code attributes_count
            out.writeShort(0);      // class attributes_count
        }

        return buffer.toByteArray();
    }

    private static final class BytesLoader extends ClassLoader {
        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            Class<?> broken = new BytesLoader().define(invalidClass());
            // Verifier may run during loading/linking or before use.
            broken.getDeclaredMethod("value").invoke(null);
            System.out.println("Unexpected success");
        } catch (VerifyError err) {
            System.out.println("Rejected: "
                    + err.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy **chương trình sinh bytecode**, không phải biên dịch class `Broken` từ Java nguồn:

~~~sh
javac --release 17 -encoding UTF-8 VerifyErrorDemo.java
java VerifyErrorDemo
~~~

**Stdout dự kiến với JVM Java 17 kiểm tra bytecode theo đặc tả:**

~~~text
Rejected: VerifyError
~~~

Giải thích:

1. Mảng bytes có magic/version/constant pool, metadata lớp `Broken` và một method `public static int value()`.
2. `Code` attribute có hai instruction. `aconst_null` đẩy reference lên stack, nhưng `ireturn` cần int.
3. Đây là **lỗi type state của operand stack**. `javac` chưa từng kiểm tra source Java cho method `Broken`, vì method này được viết trực tiếp bằng binary.
4. Khi JVM tiến hành verification theo quy tắc áp dụng, kiểu trên stack không phù hợp với `ireturn`, gây `VerifyError`.
5. Chương trình chỉ hiển thị **tên class lỗi**, không chép cứng nội dung diagnostic chi tiết, vì thông điệp verifier và thời điểm ném có thể khác giữa JVM.

Ví dụ tạo classfile tối giản có chủ đích; nó **không phải hướng dẫn viết compiler hay bytecode transformer hoàn chỉnh**. Nếu bạn cần tạo classfile từ code thực tế, một library hỗ trợ classfile và kiểm tra cùng JVM đích là phương án phù hợp hơn so với viết các byte magic thủ công.

### Vì sao hai ví dụ khác nhau?

- `MalformedClassDemo` đưa vào bytes không có định dạng classfile: lỗi **định dạng**.
- `VerifyErrorDemo` đưa vào cấu trúc classfile cơ bản, nhưng **method bytecode không hợp lệ về kiểu stack**: lỗi **verification**.

Một lớp có thể bị từ chối vì một trong nhiều lý do, nên cần xem **loại lỗi cụ thể và toàn bộ cause** trước khi kết luận. Đừng gọi chung mọi `LinkageError` là `VerifyError`.

## 8. Khi `javac` thành công nhưng runtime bị thay dependency

Không phải mọi lỗi sau biên dịch đều do verifier. Một trường hợp phổ biến là **binary compatibility**: mã ứng dụng được biên dịch dựa trên API cũ, nhưng JVM chạy với phiên bản thư viện khác.

Ta thử ba file/bước sau trong một thư mục thử nghiệm riêng; chỉ giữ mỗi phiên bản `Api.java` tại một thời điểm.

**`Api.java` phiên bản 1:**

~~~java
public class Api {
    public static String value() {
        return "v1";
    }
}
~~~

**`Consumer.java`:**

~~~java
public class Consumer {
    public static void main(String[] args) {
        System.out.println(Api.value());
    }
}
~~~

Biên dịch cả hai, chạy:

~~~sh
javac --release 17 -encoding UTF-8 Api.java Consumer.java
java Consumer
~~~

Stdout:

~~~text
v1
~~~

Bây giờ thay **chỉ `Api.java`** bằng phiên bản 2:

~~~java
public class Api {
    public static String renamed() {
        return "v2";
    }
}
~~~

Chỉ biên dịch lại thư viện, **không** biên dịch lại `Consumer.java`:

~~~sh
javac --release 17 -encoding UTF-8 Api.java
java Consumer
~~~

Lúc chạy, `Consumer.class` vẫn tham chiếu symbol `Api.value:()Ljava/lang/String;` đã được biên dịch từ trước. Nhưng `Api.class` mới không còn method `value()` ấy, nên JVM có thể ném:

~~~text
java.lang.NoSuchMethodError: 'java.lang.String Api.value()'
~~~

Thông báo đầy đủ/stack trace có thể khác theo phiên bản JDK; loại lỗi quan trọng là **`NoSuchMethodError`**, một lỗi **linking/resolution** về method symbol. Lỗi này **không có nghĩa bytecode của `Consumer` sai kiểu operand stack**; bytecode từng được biên dịch hợp lệ, nhưng hợp đồng binary của dependency runtime thay đổi.

Nếu biên dịch lại `Consumer.java` sau khi xóa `Api.value()`, compiler sẽ bắt lỗi ở **compile-time** trước khi chạy. Ví dụ cho thấy cùng một vấn đề thiếu method có thể được phát hiện ở giai đoạn khác nhau tùy artifact đang dùng.

### Những lỗi liên quan cần phân biệt

| Lỗi/symptom | Ý nghĩa thường gặp |
| --- | --- |
| `VerifyError` | Bytecode vi phạm ràng buộc verifier |
| `ClassFormatError` | Tệp class có định dạng/cấu trúc không hợp lệ |
| `UnsupportedClassVersionError` | Classfile có phiên bản không được JVM hiện tại hỗ trợ |
| `NoSuchMethodError` | Method symbol được tham chiếu không tồn tại trong class runtime đã resolve |
| `NoSuchFieldError` | Field symbol được tham chiếu không tồn tại trong class runtime |
| `IllegalAccessError` | Truy cập ở mức linking/runtime không được phép |
| `NoClassDefFoundError` | Lớp cần dùng không thể có mặt/nạp hoặc có vấn đề khởi tạo trước đó |
| `ClassCastException` | Phép ép kiểu động thất bại khi thực thi |
| `NullPointerException` | Code thao tác không hợp lệ với tham chiếu null khi thực thi |
| `ArithmeticException` | Một phép toán không hợp lệ tại runtime, ví dụ chia số nguyên cho 0 |

Các lỗi kể trên có thể có nguyên nhân sâu hơn, như classpath sai, module path sai, phiên bản dependency trùng, file hỏng hoặc code generator lỗi. Luôn đọc cả tên lỗi, vị trí stack trace và nguồn classfile thực sự được tải.

## 9. `javac` có tự bảo đảm output của mình vượt qua verifier không?

Trình biên dịch Java đạt chuẩn được kỳ vọng tạo classfile phù hợp với JVM khi mã nguồn hợp lệ và cấu hình hỗ trợ. Trong điều kiện bình thường, một output chuẩn của `javac` **nên được JVM đích chấp nhận ở cấp định dạng và verification**.

Nhưng câu “`javac` thành công = chắc chắn chạy được” là kết luận quá mạnh vì:

- Compiler có thể biên dịch với một **phiên bản JDK** khác JVM đích.
- Classfile có thể bị **biến đổi sau compile** bởi instrumentation hoặc công cụ đóng gói.
- Compile classpath có thể khác runtime classpath; API binary có thể bị đổi.
- Lỗi load/link của lớp khác chỉ xảy ra khi thực sự cần lớp ấy.
- Exception và logic runtime vẫn có thể xảy ra dù bytecode hợp lệ.
- Một bug trong compiler, transformer hoặc runtime cũng là khả năng thực tế, dù không phải giả định mặc định.

**Không phải cứ `javac` thành công thì cần nghi ngờ `VerifyError`.** Nếu chạy một chương trình Java thông thường gặp lỗi, hãy đọc exception thật. Lỗi `NoSuchMethodError` hoặc `ClassNotFoundException` nên dẫn hướng tới phụ thuộc/linking; lỗi `VerifyError` mới gợi ý bytecode hỏng hoặc transformer/generator bất thường.

### Vai trò của `StackMapTable`

Với bytecode sinh cho các phiên bản Java hiện đại, compiler thường cung cấp thông tin stack-map frames thích hợp giúp verification. Nếu một transformer thay đổi luồng điều khiển hoặc kiểu stack mà **không cập nhật các frame cần thiết**, JVM có thể từ chối classfile bằng `VerifyError`.

Điều này giải thích vì sao **chỉnh sửa bytecode bằng thao tác thay byte đơn giản** có thể làm hỏng classfile dù câu lệnh Java gốc hoàn toàn hợp lệ. Thay đổi bytecode cần cân nhắc constant pool, offsets, exception table, stack map, classfile version và các attribute liên quan.

Không nên tự “sửa” lỗi verifier bằng cách bỏ bừa `StackMapTable` hoặc ép classfile về phiên bản cũ: các bước như vậy có thể gây lỗi khác hoặc làm mất hỗ trợ tính năng ngôn ngữ/classfile.

## 10. Kiểm chứng output theo nhiều lớp

Một pipeline kiểm tra có chất lượng có thể tách bốn tầng:

**Tầng A — Compile:** dùng `javac`/Compiler API, kiểm tra exit status, diagnostics, type warnings và tính đầy đủ các source units/dependencies. Một codebase sạch warning không tự chứng minh logic đúng.

**Tầng B — Inspect artifact:** dùng `jar --list`, `javap -v`, kiểm tra manifest, classfile version, package/module names và cấu trúc phân phối. Đây là kiểm tra tĩnh hỗ trợ chẩn đoán, **không thay thế JVM verification**.

**Tầng C — Load/link trên runtime đích:** chạy smoke tests với đúng JDK, classpath, module path và dependency sẽ triển khai; phát hiện classfile version, binary compatibility, missing classes hoặc verifier problems. JVM có thể link/resolve một số tham chiếu muộn, nên một lần launch không bao phủ mọi đường chạy.

**Tầng D — Execute và test logic:** chạy unit/integration tests, nhiều input, nhánh và ngoại lệ. Một verifier thành công chỉ cho biết bytecode đáp ứng các ràng buộc bytecode, **không cho biết kết quả nghiệp vụ đúng**.

Ví dụ checklist:

~~~text
[ ] javac/build thành công với warnings được xem xét
[ ] Artifact chứa đúng classes/resources/modules
[ ] Classfile version phù hợp runtime deploy
[ ] Không còn dependency bị thay ngoài ý muốn
[ ] Ứng dụng nạp/lien kết được các entrypoints quan trọng
[ ] Smoke tests chạy trên JVM đích, không chỉ JVM dev
[ ] Unit/integration tests kiểm tra hành vi và exception
[ ] Nếu có bytecode instrumentation: thử verifier trên JVM đích
~~~

### `javap` không phải trình biên dịch

Lệnh:

~~~sh
javap -c -v RuntimeBehaviorDemo
~~~

chỉ **phân tích/in metadata và instruction của classfile** đã có. Nó hữu ích để nhìn descriptor, bytecode, stack/locals, version, constant pool, frame attributes. Nhưng output đẹp không chứng minh mọi đường runtime đều an toàn hoặc chương trình không gặp exception. Nếu cần xác nhận JVM thực sự tải/xác minh class, phải **thử trên JVM**.

## 11. Thời điểm phát hiện lỗi có thể muộn

JVM có thể không cần resolve mọi symbolic reference ngay lập tức, và có thể tải các lớp theo nhu cầu. Vì vậy:

- Chạy được `main` **không chứng minh** mọi class/method hiếm dùng đều đã được nạp/link.
- Một lỗi `NoSuchMethodError` có thể chỉ phát lộ khi thực thi đúng lệnh gọi method liên quan.
- Một classfile bị lỗi verifier có thể bị từ chối khi loader/linker xử lý nó, nhưng **không cần khẳng định một thời điểm cố định** giữa `defineClass`, `getDeclaredMethod` và lần gọi đầu tiên.
- Đưa classfile vào JAR **không phải** một lần verify thực tế tất cả bytecode trong archive.

Khi kiểm thử binary compatibility, cần chạy những entrypoints/feature paths có dùng dependency, không chỉ gọi `java -version` hoặc khởi động ứng dụng rồi tắt ngay.

### Cẩn thận với ngoại lệ bọc lỗi

Reflection có thể bọc exception xảy ra **bên trong method được gọi** thành `InvocationTargetException`; framework và class loader cũng có thể bọc nguyên nhân bằng các exception riêng. Khi điều tra, hãy xem **cause chain**. Riêng `VerifyError` là một `LinkageError`, không phải exception nghiệp vụ thông thường; bắt rộng `Throwable` để giấu lỗi verifier là cách xử lý nguy hiểm.

Trong code ứng dụng production, thay vì nuốt `LinkageError` rồi tiếp tục dùng state nửa khởi tạo, thường nên báo lỗi deployment/artifact và dừng luồng liên quan.

## 12. Compiler warnings, generics và kiểm tra runtime

Một ví dụ khác giúp hiểu giới hạn compiler:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    public static void main(String[] args) {
        List raw = new ArrayList<String>();
        raw.add(123);

        @SuppressWarnings("unchecked")
        List<String> strings = raw;

        try {
            String first = strings.get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("Runtime: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked ErasureDemo.java
java ErasureDemo
~~~

**Stdout:**

~~~text
Runtime: ClassCastException
~~~

Compiler có thể cảnh báo về raw type và unchecked operations. `@SuppressWarnings("unchecked")` ở biến chỉ suppress một phần cảnh báo; nó **không đảm bảo phần tử danh sách là `String`**. Generic type arguments bị erasure ở runtime; compiler có thể chèn `checkcast String` tại lần lấy phần tử, và khi gặp `Integer` sẽ ném `ClassCastException`.

Verifier kiểm tra rằng instruction `checkcast` là hợp lệ, chứ **không chứng minh trước giá trị nào sẽ được cast thành công**. Không nên lẫn lộn `ClassCastException` với `VerifyError`.

Trong code thật, cách tốt hơn là tránh raw type, dùng `List<String>` và kiểm tra dữ liệu ở ranh giới tích hợp. Ví dụ trên cố ý dùng raw type để minh họa rủi ro, **không phải mẫu thiết kế khuyến nghị**.

## 13. Những nhầm lẫn phổ biến

| Nhận định sai | Điều đúng |
| --- | --- |
| “`javac` kiểm tra bytecode của mọi thư viện runtime.” | Compiler kiểm tra nguồn/thông tin dependency theo compile environment; JVM kiểm tra classfile được tải theo runtime environment. |
| “Một `.class` bất kỳ đều từng qua `javac`.” | Bytecode có thể được tạo/chỉnh sửa bằng nhiều công cụ khác. |
| “`ClassFormatError` chính là `VerifyError`.” | Một lỗi cấu trúc classfile, một lỗi ràng buộc verification bytecode. |
| “Verifier nhận class nghĩa là thuật toán đúng.” | Verifier không kiểm tra yêu cầu nghiệp vụ hoặc mọi giá trị input runtime. |
| “`ClassCastException` là lỗi verifier.” | Phần lớn là lỗi kiểm tra kiểu động trong lúc chạy. |
| “`NoSuchMethodError` là bytecode sai kiểu.” | Thường do symbolic reference không khớp dependency runtime. |
| “Không lỗi khi khởi động nghĩa là mọi lớp đã verify.” | Loading/linking/resolution có thể được trì hoãn, code hiếm dùng chưa được kích hoạt. |
| “`javap -v` thành công nghĩa là JVM sẽ chạy được.” | `javap` chỉ inspect; cần kiểm tra JVM và runtime dependency thật. |
| “Annotation/bytecode transform không ảnh hưởng verifier.” | Transform sai instruction/frame/metadata có thể tạo `VerifyError`. |
| “`@SuppressWarnings` sửa được `VerifyError`.” | Annotation này tác động compiler warnings có hỗ trợ, không sửa bytecode hỏng ở runtime. |
| “Mọi `LinkageError` có thể được retry như lỗi mạng.” | Nhiều lỗi liên kết phản ánh artifact/dependency không hợp lệ, cần sửa deployment. |

## 14. Quy trình chẩn đoán theo tín hiệu

Khi một chương trình Java không hoạt động, làm theo trình tự:

1. **Lỗi xảy ra ở `javac` hay ở `java`?** Nếu là compile error, sửa nguồn, dependency và lựa chọn compiler; đừng tìm verifier log.
2. **Nếu `java` lỗi, đọc class lỗi cụ thể.** `ClassFormatError`, `VerifyError`, `NoSuchMethodError`, `UnsupportedClassVersionError` và `ClassCastException` chỉ các hướng khác nhau.
3. **Kiểm tra artifact thật đang được nạp.** Có JAR/classes trùng phiên bản? Có transformer hoặc bytecode generation? Classfile đã được đóng gói đúng chưa?
4. **Đối chiếu compile/runtime dependency.** Cùng tên class nhưng method/field/signature đã đổi có thể tạo lỗi resolution/linking.
5. **Kiểm tra phiên bản classfile và JVM.** Dùng `javap -verbose` hoặc metadata build; chạy smoke test trên runtime đích.
6. **Nếu nghi verifier, kiểm tra instruction/frames.** Dùng `javap -v -c` hoặc công cụ classfile phù hợp, nhìn luồng stack/local/StackMapTable và transformations mới áp dụng.
7. **Nếu lớp chạy được nhưng logic sai, kiểm thử dữ liệu.** Verifier không thay thế test của ứng dụng.
8. **Đừng sửa artifact production trực tiếp.** Tái hiện bằng bản thử, lưu lại diagnostic và quy trình build có thể lặp lại.

## 15. Bài tập thực hành

**Bài 1 — Compiler error.** Biên dịch `SourceTypeError.java`. Xác định vì sao compiler từ chối `return "hello";` khi method trả `int` và vì sao ở đây không có `VerifyError`.

**Bài 2 — Bytecode hợp lệ, runtime lỗi.** Chạy `RuntimeBehaviorDemo.java`. Giải thích vì sao phép chia số nguyên cho 0 được biên dịch và xác minh bytecode, nhưng khi chạy vẫn ném `ArithmeticException`.

**Bài 3 — Xem bytecode.** Dùng `javap -c -p RuntimeBehaviorDemo` rồi tìm `idiv`. Nó kiểm tra zero divisor ở compile-time hay thực hiện phép chia khi chạy?

**Bài 4 — Classfile format.** Chạy `MalformedClassDemo.java`. Xác định dữ liệu đầu vào có thật là một classfile hợp lệ chưa, và vì sao loại lỗi là `ClassFormatError`.

**Bài 5 — Verification.** Chạy `VerifyErrorDemo.java` trên JVM Java 17. Giải thích kiểu operand do `aconst_null` đẩy lên và kiểu `ireturn` yêu cầu, nêu lý do verifier từ chối.

**Bài 6 — Binary compatibility.** Compile `Consumer` dựa trên `Api.value()`, sau đó thay `Api.class` bằng phiên bản không có method mà không biên dịch lại `Consumer`. Tại sao lỗi quan sát là `NoSuchMethodError` thay vì lỗi compile?

**Bài 7 — Generics.** Chạy `ErasureDemo.java`. Phân biệt raw type warning, `@SuppressWarnings`, `checkcast` runtime và lỗi `ClassCastException`.

**Bài 8 — Triển khai.** Lập kế hoạch kiểm chứng một thư viện có bytecode instrumentation: compiler output check, classfile inspection, JVM target smoke test, regression tests và xác minh artifact/dependency version.

### Câu hỏi tự kiểm tra

1. **`javac` kiểm tra dạng dữ liệu nào?** — Mã nguồn Java và các thông tin kiểu/phụ thuộc cần thiết cho compilation.
2. **Verifier JVM kiểm tra dạng dữ liệu nào?** — Classfile/bytecode được tải để bảo đảm các ràng buộc bytecode hợp lệ.
3. **`ClassFormatError` khác `VerifyError` ở đâu?** — Một bên báo cấu trúc/định dạng classfile sai; bên kia báo bytecode không thỏa verification.
4. **Classfile do công cụ khác `javac` tạo có cần verifier không?** — Có, nó phải được JVM chấp nhận theo quy tắc class loading/linking.
5. **`VerifyError` có chứng minh bug nghiệp vụ không?** — Nó phản ánh bytecode invalid, không phải kiểm tra yêu cầu nghiệp vụ.
6. **Một method có `idiv` có thể vượt verifier nhưng chia cho 0 không?** — Có; chia cho 0 gây `ArithmeticException` khi runtime.
7. **`NoSuchMethodError` thường gợi ý điều gì?** — Dependency/runtime API không khớp tham chiếu đã biên dịch hoặc vấn đề resolution tương tự.
8. **`javap` có đảm bảo mọi bytecode sẽ chạy đúng không?** — Không; nó giúp inspect classfile.
9. **Vì sao không thể xem “launch không lỗi” như kiểm tra mọi class?** — Các lớp/tham chiếu có thể được nạp hoặc resolve muộn.
10. **Sau compiler + verifier, cần kiểm thử gì?** — Runtime linking, compatibility, exceptions và hành vi logic với input thực tế.

**Tổng kết:** `javac` xác nhận **mã nguồn Java hợp lệ theo môi trường compile**, còn JVM kiểm tra **classfile/bytecode thực tế** để bảo vệ các ràng buộc của máy ảo. Dù qua cả hai, code vẫn có thể vướng lỗi binary compatibility hoặc runtime logic. Vì vậy kiểm chứng đầu ra Java cần kết hợp **compile diagnostics, artifact inspection, JVM loading/linking và kiểm thử hành vi** trên đúng môi trường triển khai.