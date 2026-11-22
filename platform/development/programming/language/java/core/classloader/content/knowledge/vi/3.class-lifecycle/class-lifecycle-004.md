# Verification: kiểm tra cấu trúc và tính hợp lệ của bytecode Java

**Verification** (xác minh bytecode) là công đoạn trong **linking** của vòng đời lớp trên JVM. Nó kiểm tra rằng biểu diễn nhị phân của một lớp hoặc interface phù hợp các ràng buộc của Java Virtual Machine Specification (JVMS), đặc biệt là các quy tắc về **kiểu của giá trị, operand stack, biến cục bộ và luồng điều khiển**. Mục tiêu là ngăn bytecode không hợp lệ thực hiện những thao tác phá vỡ các giả định an toàn kiểu của JVM.

Điểm quan trọng: tệp `.class` *có thể được đọc và có cấu trúc nhận diện được* nhưng vẫn bị từ chối vì nội dung lệnh không hợp lệ. Ngược lại, một lớp qua được verification vẫn có thể ném exception khi chạy hoặc có lỗi nghiệp vụ.

## 1. Verification nằm ở đâu trong vòng đời lớp?

Sơ đồ khái quát:

```text
Loading (tìm/đọc dữ liệu lớp, tạo Class)
    |
    v
Linking
    |-- Verification  : kiểm tra ràng buộc cấu trúc và an toàn kiểu của bytecode
    |-- Preparation   : cấp và khởi tạo giá trị mặc định cho static fields
    '-- Resolution    : chuyển symbolic references thành liên kết trực tiếp (*)
    |
    v
Initialization        : chạy <clinit> khi điều kiện khởi tạo được kích hoạt
    |
    v
Sử dụng lớp             : gọi phương thức, tạo đối tượng, truy cập trường...
```

`(*)` **Resolution có thể diễn ra dần (lazy)** theo từng tham chiếu, tùy quy tắc của JVM; sơ đồ thể hiện các phần việc thuộc linking, không cam kết thứ tự thực hiện mọi thao tác hoặc thời điểm xuất hiện lỗi trong mọi triển khai.

Cần phân biệt:

- **Loading:** bộ nạp tìm bytecode và định nghĩa lớp. Lớp có thể đến từ directory, JAR, module, mạng hoặc mảng byte do custom `ClassLoader` cung cấp.
- **Verification:** JVM đánh giá lớp có đáp ứng các ràng buộc class file và bytecode hay không. Không cần thực thi logic nghiệp vụ để kiểm tra.
- **Preparation:** chuẩn bị `static` fields với giá trị mặc định (không đồng nghĩa chạy các phép gán trong mã `static` của lớp).
- **Resolution:** giải quyết symbolic references tới class, field, method. Một số lỗi liên kết khác có thể phát sinh tại đây hoặc khi sử dụng.
- **Initialization:** chạy bộ khởi tạo lớp `<clinit>` khi cần. Verification hoàn tất trước khi lớp được khởi tạo, nhưng không nên suy diễn rằng mọi lỗi liên quan đến một dependency sẽ xuất hiện ngay khi lớp đầu tiên được load.

Ví dụ, `Class.forName(name, false, loader)` yêu cầu tải và liên kết lớp mà **không yêu cầu khởi tạo lớp**. Thời điểm một verifier thực sự phân tích từng phương thức có thể phụ thuộc cách triển khai và thao tác đang thực hiện. Việc chỉ thấy đối tượng `Class<?>` không phải bằng chứng về thời điểm mọi bước kiểm tra đã diễn ra.

## 2. JVM kiểm tra những gì?

Verification không phải một lệnh duy nhất mà là tập kiểm tra trên thông tin của class file và bytecode. Có thể chia để học thành hai nhóm:

| Nhóm kiểm tra | Câu hỏi điển hình | Ví dụ bị từ chối |
|---|---|---|
| Định dạng/cấu trúc class file | Header, constant pool, bảng phương thức, thuộc tính, chỉ số và cấu trúc có hợp lệ? | Magic bytes `CAFEBABE` bị hỏng hoặc constant-pool entry sai định dạng |
| Ràng buộc ngữ nghĩa và an toàn kiểu | Các bytecode instructions, stack, locals, nhánh và kiểu trả về có nhất quán? | Phương thức khai báo trả `int` nhưng dùng `areturn` với giá trị `int` |

Một số chi tiết quan trọng:

1. **Định dạng lớp:** kiểm tra cấu trúc class file (magic, phiên bản hỗ trợ, constant pool, field/method metadata, Code attribute và các ràng buộc tương ứng). Không phải mọi lỗi định dạng đều được báo bằng `VerifyError`; lỗi cấu trúc thường dẫn đến `ClassFormatError` hoặc một lớp lỗi liên kết phù hợp.
2. **Operand stack:** xác định kiểu và số phần tử trên stack ở từng điểm chương trình; không được pop một giá trị chưa có hoặc dùng sai loại toán hạng.
3. **Local variables:** dùng biến local phải phù hợp kiểu đang lưu; đọc biến chưa được gán trạng thái hợp lệ hoặc sử dụng nhầm slot làm loại khác có thể bị từ chối.
4. **Return/argument typing:** `ireturn` chỉ dùng trong ngữ cảnh kiểu kết quả integer phù hợp; `areturn` dành cho giá trị tham chiếu; đối số của lời gọi method phải phù hợp descriptor của method.
5. **Luồng điều khiển:** nhảy tới offset lệnh hợp lệ; tại các điểm nhiều nhánh nhập lại, các kiểu và trạng thái stack/locals phải có quan hệ hợp lệ. Exception handlers cũng có điểm vào và trạng thái stack riêng.
6. **Đối tượng chưa khởi tạo:** verifier theo dõi các giá trị tạo bằng `new` trước lời gọi constructor `<init>`; không cho sử dụng đối tượng chưa khởi tạo như đối tượng bình thường theo cách trái quy tắc.
7. **Khả năng truy cập và tham chiếu:** class/interface, method/field reference và một số ràng buộc kế thừa phải hợp lệ; tuy nhiên **resolution và access checks tại runtime** là phần riêng của cơ chế liên kết/thực thi, nên không quy mọi `IllegalAccessError` hay `NoSuchMethodError` cho verification.

Verification kiểm tra **kiểu trừu tượng** của giá trị chứ không cần biết kết quả số học thực tế hoặc nội dung đối tượng tại runtime. Việc `int` có giá trị 42 hay 100 thường không liên quan đến việc `ireturn` có hợp kiểu hay không.

## 3. Theo dõi operand stack qua bytecode

Xét phương thức Java:

```java
static int add(int a, int b) {
    return a + b;
}
```

Trong bytecode thường xuất hiện trình tự:

```text
0: iload_0
1: iload_1
2: iadd
3: ireturn
```

Verifier suy luận trạng thái kiểu:

| Lệnh | Operand stack trước | Operand stack sau |
|---|---|---|
| `iload_0` | `[]` | `[int]` |
| `iload_1` | `[int]` | `[int, int]` |
| `iadd` | `[int, int]` | `[int]` |
| `ireturn` | `[int]` | Trả `int` ra khỏi phương thức |

Các local đầu vào tương ứng hai tham số `int`, với phương thức `static` không có slot `this`. `max_stack` và `max_locals` là metadata trong `Code` attribute mô tả giới hạn tài nguyên cho phương thức; verifier cũng kiểm tra việc sử dụng thực tế có nhất quán với chúng.

Nếu thay `ireturn` bằng `areturn`, JVM không thể chấp nhận một `int` trên stack như tham chiếu trả về. Đây là lỗi an toàn kiểu, dù chuỗi byte mã lệnh vẫn nằm trong một class file có định dạng hợp lệ.

### Khi có nhiều nhánh

Với `if`, `switch`, `goto` hoặc exception handler, các luồng điều khiển có thể hội tụ. Kiểu của local variables và operand stack tại điểm hội tụ phải hợp lệ cho **mọi nhánh có thể đi tới**. JVM dùng quy tắc phân tích luồng dữ liệu dựa trên trạng thái kiểu.

Trong class file hiện đại, thuộc tính **`StackMapTable`** cung cấp các *stack-map frames* mô tả trạng thái kiểm tra kiểu ở những offset quan trọng. Với các phiên bản class file áp dụng cơ chế type checking này, verifier dùng những frame và quy tắc chuyển trạng thái để kiểm tra tính nhất quán; không đơn thuần tin rằng compiler luôn phát đúng. Không phải mọi phương thức bắt buộc chứa một danh sách frame dài: phương thức tuyến tính đơn giản có thể không có entry tường minh trong `StackMapTable`.

Ví dụ bytecode giả định **sai kiểu** (đây không phải class file hoàn chỉnh):

```text
method: public static int answer()
    bipush 42   // stack: [int]
    areturn     // sai: areturn đòi hỏi reference và kiểu kết quả phù hợp
```

## 4. Thực hành Java 17+: làm hỏng bytecode để quan sát verifier

Ví dụ dưới đây tạo một class **hợp lệ** bằng `javac`, đọc chính tệp `.class` đã biên dịch, sau đó thử hai thay đổi **chỉ trên bản sao `byte[]` trong bộ nhớ**:

- Đổi một byte ở đầu class file để quan sát lỗi **`ClassFormatError`** (định dạng hỏng).
- Đổi opcode trả về `ireturn` thành `areturn` để quan sát **`VerifyError`** (mã có cấu trúc đọc được nhưng không an toàn kiểu).

Việc tạo class loader riêng cho phép `defineClass` cùng tên nhị phân trong một namespace lớp khác; JVM xác định danh tính lớp bằng **(binary name, defining class loader)**. Chương trình không ghi đè tệp `.class` trên đĩa và không phụ thuộc thư viện bytecode ngoài.

Tạo tệp **`VerificationExample.java`**:

```java
import java.io.InputStream;
import java.util.Objects;

public final class VerificationExample {
    private static final class ByteArrayLoader extends ClassLoader {
        ByteArrayLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] data) {
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] original;
        try (InputStream in = VerificationExample.class
                .getResourceAsStream("/ExampleTarget.class")) {
            original = Objects.requireNonNull(
                    in, "ExampleTarget.class").readAllBytes();
        }

        byte[] modified = original.clone();
        int found = 0;
        for (int i = 0; i < modified.length - 2; i++) {
            if ((modified[i] & 0xff) == 0x10
                    && (modified[i + 1] & 0xff) == 0x2a
                    && (modified[i + 2] & 0xff) == 0xac) {
                modified[i + 2] = (byte) 0xb0;
                found++;
            }
        }
        if (found != 1) {
            throw new IllegalStateException(
                    "Expected exactly one opcode sequence, got " + found);
        }

        System.out.println("Original: " + ExampleTarget.answer());

        byte[] malformed = original.clone();
        malformed[0] = 0;
        try {
            new ByteArrayLoader(VerificationExample.class.getClassLoader())
                    .define("ExampleTarget", malformed);
            System.out.println("Unexpected acceptance");
        } catch (ClassFormatError expected) {
            System.out.println("Malformed header: ClassFormatError");
        }

        try {
            Class<?> changed =
                    new ByteArrayLoader(VerificationExample.class.getClassLoader())
                            .define("ExampleTarget", modified);
            changed.getMethod("answer").invoke(null);
            System.out.println("Unexpected acceptance");
        } catch (VerifyError expected) {
            System.out.println("Modified: VerifyError");
        }
    }
}

class ExampleTarget {
    public static int answer() {
        return 42;
    }
}
```

Biên dịch bằng JDK 17+ (cờ `--release 17` khiến class file có phiên bản mục tiêu Java 17), rồi chạy từ thư mục chứa tệp nguồn:

```bash
javac --release 17 -d out VerificationExample.java
java -cp out VerificationExample
```

Với `javac` tiêu chuẩn trên JDK 17+ và HotSpot, đầu ra là:

```text
Original: 42
Malformed header: ClassFormatError
Modified: VerifyError
```

**Giải thích chính xác ví dụ:**

- `ExampleTarget.answer()` là phương thức `static int` trả 42. Trình biên dịch `javac` sinh chuỗi lệnh thường gặp `bipush 42` (`10 2a` theo mã byte hex) và `ireturn` (`ac`). Chương trình tìm đúng chuỗi `10 2a ac` trong bản class file thử nghiệm; nếu không tìm được **đúng một** vị trí, nó chủ động dừng để tránh minh họa sai.
- `areturn` có opcode `b0`; sau khi thay, stack vẫn chứa `int` do `bipush` sinh ra. Vì thế phương thức không tuân thủ yêu cầu kiểu trả về. JVM có thể phát hiện lỗi khi định nghĩa/liên kết lớp hoặc khi thao tác tiếp theo buộc kiểm tra, nhưng trong cả hai trường hợp phần `catch (VerifyError ...)` thể hiện lỗi cần quan sát.
- `malformed[0] = 0` phá magic `CA FE BA BE` tại đầu class file, nên báo lỗi định dạng. Không gọi lỗi này là “verifier phát hiện return type sai”.
- Một `ByteArrayLoader` khác được tạo cho mỗi lần `define`. Class đã nạp qua system loader và class định nghĩa bởi loader con có thể cùng binary name nhưng là **hai lớp khác nhau** đối với JVM.

Đây là **bài thử có chủ đích gắn với bytecode cụ thể mà `javac` sinh ra**, không phải bộ chỉnh sửa class file tổng quát: tìm chuỗi byte trên toàn tệp không phân tích `Code` attribute. Với compiler khác, bytecode khác hoặc tối ưu hóa khác, chuỗi có thể không xuất hiện/không duy nhất; khi đó bài thử dừng với `IllegalStateException`. Khi thao tác bytecode thực tế, nên dùng thư viện hiểu cấu trúc class file như ASM và kiểm tra kết quả bằng JVM.

### Xem bytecode và metadata trước khi sửa

Sau khi biên dịch, dùng:

```bash
javap -classpath out -c ExampleTarget
javap -classpath out -v ExampleTarget
```

`-c` hiển thị các instruction/offset, ví dụ thân method `answer` gồm `bipush 42` rồi `ireturn`. `-v` giúp xem version, constant pool, `Code`, `stack`/`locals` và các thuộc tính khác (nếu có). Toàn bộ đầu ra `javap -v` còn chứa thông tin compiler và môi trường nên không nên dùng làm stdout cố định trong kiểm thử.

## 5. `ClassFormatError`, `VerifyError` và các lỗi liên kết khác

**`VerifyError`** là subclass của `LinkageError`; nó biểu thị JVM đã thấy sự thiếu nhất quán trong class file về các ràng buộc xác minh thích hợp. Tuy nhiên không phải mọi lỗi xảy ra khi load/link một lớp đều là `VerifyError`.

| Lỗi | Ý nghĩa điển hình | Phân biệt |
|---|---|---|
| `ClassFormatError` | Class file sai định dạng hoặc vi phạm quy tắc cấu trúc | Có thể lỗi trước khi phân tích luồng kiểu của mã lệnh |
| `UnsupportedClassVersionError` | Class file dùng phiên bản không được JVM hiện tại hỗ trợ | Là một subtype của `ClassFormatError` |
| `VerifyError` | Bytecode/metadata không thỏa các ràng buộc kiểm chứng kiểu hoặc tính hợp lệ liên quan | Ví dụ dùng sai opcode return theo kiểu stack |
| `NoClassDefFoundError` | Không thể tìm/hoàn thành định nghĩa lớp phụ thuộc cần thiết trong hoàn cảnh sử dụng | Thường gắn với loading/linkage, không tự động là lỗi verifier |
| `NoSuchMethodError`, `NoSuchFieldError` | Symbolic reference không giải quyết được tới member được tham chiếu | Gắn với resolution/compatibility; thường do thay đổi binary dependency |
| `IncompatibleClassChangeError` | Thay đổi không tương thích ở mối quan hệ binary của các lớp/member | Lỗi liên kết, không đồng nghĩa mã bytecode sai kiểu stack |
| `ExceptionInInitializerError` | Initializer tĩnh gây exception theo quy tắc JVM | Thuộc initialization, sau giai đoạn verification cần thiết |

Sửa nhanh theo đúng nguyên nhân: nếu `ClassFormatError`, kiểm tra bytecode, tooling và file nguồn; nếu `VerifyError`, tìm đoạn bytecode hoặc transformation tạo trạng thái stack/locals không hợp lệ; nếu lỗi resolution, kiểm tra JAR/classpath/module và phiên bản dependency. Không “sửa” `VerifyError` bằng cách bắt nó rồi tiếp tục dùng lớp bị từ chối.

## 6. Trường hợp hay gặp trong dự án thực tế

### 6.1. Bytecode được tạo/chỉnh sửa bởi công cụ

Các thư viện proxy, instrumentation, weaving, code generation hoặc agent có thể sinh bytecode lúc build/runtime. Một thay đổi trong method descriptor, điều khiển nhánh, stack map frames hay thứ tự hướng constructor có thể làm mã biến đổi bị từ chối dù nguồn Java ban đầu biên dịch được.

Quy trình kiểm tra hữu ích:

1. Xác định binary name của lớp lỗi và **defining class loader** liên quan.
2. Lưu/thu thập chính **bytes sau transformation** nếu hệ thống cho phép, không chỉ file `.class` nguồn.
3. Dùng `javap -v -c` (hoặc công cụ class-file/ASM tương đương) trên class file tương ứng để soi descriptor, instruction, `Code` và `StackMapTable`.
4. Kiểm tra chỗ nhánh hội tụ, stack height, kiểu return, method calls và ràng buộc constructor.
5. Tái hiện dưới cùng Java version và bộ loader/agent, rồi sửa logic sinh bytecode. Không bỏ verification để che lỗi.

### 6.2. Class file phiên bản quá mới

Ví dụ class file target Java 21 chạy trên JVM Java 17 có thể gây `UnsupportedClassVersionError`; đó là vấn đề tương thích **class-file version**, không phải vì verifier chứng minh phép cộng kiểu `int` sai. Cần biên dịch lại với `--release` phù hợp hoặc nâng runtime.

### 6.3. Vấn đề chỉ xuất hiện sau một nâng cấp thư viện

Một class có thể đi qua những kiểm tra bytecode cơ bản nhưng fail khi resolution của phương thức/phụ thuộc diễn ra. Chẳng hạn class vẫn tham chiếu một method đã bị xóa trong phiên bản JAR mới và ném `NoSuchMethodError`. Điều này khác với code bị từ chối vì local/stack type. Thu thập đầy đủ exception chain, loader identity và dependency graph để phân loại đúng.

### 6.4. Cùng tên lớp, khác loader

JVM coi `(binary name, defining class loader)` là danh tính của một runtime class. Hai lớp có tên giống nhau do hai loader khác nhau định nghĩa **không** tự động thay thế được cho nhau. Lỗi `ClassCastException` hoặc `LinkageError` trong bối cảnh đó không đồng nghĩa bytecode mất tính hợp lệ; còn phải phân tích namespace lớp và loader constraints.

## 7. Verification đảm bảo điều gì, và không đảm bảo điều gì?

Verification là lớp bảo vệ thiết yếu cho runtime khi JVM tiếp nhận class file, nhất là bytecode ngoài hoặc bytecode đã biến đổi. Nó duy trì các quy tắc an toàn kiểu được nêu bởi mô hình JVM: method không thể tùy ý dùng một integer như object reference chỉ bằng cách phát lệnh sai kiểu.

Nhưng verification **không chứng minh** rằng:

- Code đáp ứng nghiệp vụ hoặc trả đúng kết quả mong muốn.
- Không thể có `NullPointerException`, `ClassCastException`, `ArrayIndexOutOfBoundsException`, `ArithmeticException` hoặc exception hợp lệ khác khi chạy. Những runtime checks vẫn cần thiết.
- Không có deadlock, data race, lỗi concurrency, resource leak hoặc vòng lặp vô hạn.
- Người dùng hoặc process có quyền truy cập dữ liệu: authorization, sandboxing và chính sách bảo mật ứng dụng là vấn đề khác.
- Native code, JNI, `Unsafe` hoặc cơ chế đặc quyền khác đều bị điều tiết chỉ bởi verifier theo cùng các giả định của bytecode Java thông thường.

**Không cần hiểu verification như một sandbox an ninh toàn diện.** Nó kiểm soát một tập thuộc tính ở cấp bytecode, còn runtime exception, bộ nạp, quyền truy cập và logic ứng dụng vận hành ở các tầng khác.

## 8. Kiểm tra hiểu bài

1. **Vì sao `bipush 42; areturn` sai?** Vì `bipush` đẩy `int` nhưng `areturn` cần toán hạng tham chiếu, đồng thời method khai báo trả về `int`.
2. **Một file có magic `CAFEBABE` đúng có chắc qua verification?** Không. Header đúng chưa chứng minh constant pool, code, stack maps và dataflow hợp lệ.
3. **`StackMapTable` có thay thế mọi kiểm tra runtime?** Không. Nó giúp chứng minh trạng thái kiểu bytecode; các kiểm tra giá trị/điều kiện lúc chạy vẫn diễn ra.
4. **`UnsupportedClassVersionError` có phải `VerifyError`?** Không; nó là một subclass của `ClassFormatError`.
5. **Verification có chạy phương thức `main` của lớp để xem kết quả?** Không. Nó kiểm tra class file và tính hợp lệ kiểu của bytecode, không chạy thuật toán nghiệp vụ để đoán kết quả.
6. **Vì sao một proxy/agent có thể gây `VerifyError` dù mã Java biên dịch được?** Vì bytecode sau transformation khác bytecode `javac` tạo ra và có thể chứa stack frames, descriptor hay instructions không nhất quán.

**Ghi nhớ:** Trong vòng đời lớp, **verification thuộc linking và kiểm tra tính hợp lệ bytecode trước khi lớp được sử dụng theo cách đòi hỏi liên kết hoàn tất**. Phân biệt lỗi định dạng `ClassFormatError` với lỗi xác minh `VerifyError` và lỗi resolution/initialization để tìm đúng nguyên nhân, nhất là khi làm việc với class loader, instrumented classes và bytecode được sinh động.
