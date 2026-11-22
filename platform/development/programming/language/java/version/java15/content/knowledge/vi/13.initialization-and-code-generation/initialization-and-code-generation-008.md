# Java 15 — Ranh giới giữa dữ liệu bên ngoài và mã có quyền thực thi khi khởi tạo, sinh mã runtime

## 1. Vấn đề cốt lõi: dữ liệu không được tự biến thành quyền thực thi

Trong Java, **dữ liệu từ bên ngoài** như HTTP request, cấu hình do khách hàng nhập, file tải lên, nội dung cơ sở dữ liệu, biểu thức do người dùng định nghĩa hoặc kết quả của một dịch vụ khác **không tự động trở thành dữ liệu đáng tin**. Khi ứng dụng biến dữ liệu ấy thành **classfile bytes**, mã nguồn để biên dịch, một đoạn script hoặc một lời gọi có quyền truy cập tài nguyên, ứng dụng đã đi qua **ranh giới từ dữ liệu sang mã thực thi**.

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` cho phép runtime định nghĩa **hidden class** từ bytecode. Tính năng này rất hữu ích cho framework sinh adapter, lambda implementation, rule engine và những đoạn mã nội bộ ngắn hạn. Nhưng **Hidden Class không phải sandbox**: chữ “hidden” chỉ biểu thị đặc tính về danh tính tên/liên kết và vòng đời của lớp; nó **không hạn chế** các hành động mà bytecode có thể thực hiện trong tiến trình Java.

### Mục tiêu sau bài

- Nhận diện chính xác thời điểm **untrusted data** đi vào thành phần có khả năng **sinh hoặc thực thi mã**.
- Phân biệt các vai trò: **parser**, **validator**, mô hình lệnh/AST đã kiểm tra, **code generator đáng tin**, `Lookup` có đặc quyền và code được chạy.
- Áp dụng **allowlist** và các giới hạn đầu vào **trước khi sinh classfile**; không ghép dữ liệu thô thành Java source hoặc bytecode tùy ý.
- Hiểu vì sao một bytecode verifier, hidden class, module Java hoặc `Lookup` không thay thế **ranh giới cô lập thực thi**.
- Viết và chạy ví dụ dùng **classfile mẫu thuộc ứng dụng**, đưa dữ liệu đã kiểm tra qua constructor và từ chối lệnh không hỗ trợ.
- Thiết kế cô lập thích hợp nếu buộc phải chạy mã **do bên ngoài kiểm soát**, dựa trên tiến trình/tài nguyên/quyền thực tế chứ không dựa vào cơ chế Security Manager đã lỗi thời.

Bài áp dụng kiến thức còn phù hợp với Java 17+ và JDK hiện đại. Phần Hidden Class được chuẩn hóa ở Java 15 theo **JEP 371**; các ví dụ dùng `record` và `Stream` hiện đại nếu thích hợp, không dùng preview.

## 2. Sơ đồ ranh giới: nơi dữ liệu có thể trở thành mã

~~~text
Không tin cậy                                  Tin cậy / được kiểm soát
+-------------------+
| HTTP / file / DB  |     ranh giới #1
| cấu hình / plugin | ------------------------+
+-------------------+                         |
                                              v
                                  +---------------------------+
                                  | Kiểm tra size / encoding  |
                                  | Phân tích cú pháp rõ ràng  |
                                  | Xác thực allowlist &      |
                                  | quyền của người yêu cầu   |
                                  +---------------------------+
                                              |
                                              v
                                  +---------------------------+
                                  | AST / command typed        |
                                  | không còn source thô       |
                                  +---------------------------+
                                              |
                                 ranh giới #2: quyết định thực thi
                                              |
                        +---------------------+------------------+
                        |                                        |
                        v                                        v
             Interpreter có hạn mức                  Generator đáng tin
             chỉ thao tác được phép                  với classfile hợp lệ
                        |                                        |
                        v                                        v
             Kết quả nghiệp vụ                     Lookup.defineHiddenClass
                                                                 |
                                                                 v
                                                      Instance / MethodHandle
                                                                 |
                                                                 v
                                                 JVM thực thi với quyền process
~~~

**Hai điểm mấu chốt:**

1. **Không tin cậy đầu vào chỉ vì nó đã được xác thực.** Một tài khoản đăng nhập hợp lệ, file nằm trong DB nội bộ hoặc phản hồi của một mô hình AI vẫn có thể chứa dữ liệu sai định dạng, quá lớn hoặc tìm cách thay đổi luồng điều khiển. Xác thực danh tính và **ủy quyền thao tác cụ thể** là những kiểm tra khác nhau.
2. **Sự kiện “parser đã đọc được chuỗi” không đồng nghĩa chuỗi được phép thực thi.** Parser phải tạo cấu trúc có kiểu với tập operation hữu hạn; validator và lớp ủy quyền phải quyết định mỗi operation có được phép hay không; executor chỉ làm đúng những thao tác đã được định nghĩa.

Nếu đầu vào có thể chứa **classfile bytes tùy ý** hoặc Java source tùy ý, ranh giới bảo vệ ở ví dụ trên đã bị phá: người gửi có thể quyết định hành vi bytecode, không chỉ dữ liệu tham số.

## 3. Khái niệm tin cậy trong một runtime sinh mã Java

| Thành phần | Có thể nhận dữ liệu bên ngoài? | Có được tự quyết định hành vi thực thi? | Nguyên tắc |
| --- | --- | --- | --- |
| HTTP body / JSON / config / file tải lên | Có | Không | Mặc định không tin cậy, giới hạn kích thước và quyền |
| Parser | Có | Không | Chuyển đúng cú pháp sang kiểu dữ liệu hạn chế, từ chối cú pháp lạ |
| AST hoặc command đã kiểm tra | Có, dưới dạng đã phân tích | Chỉ trong allowlist | Không giữ source thô để chạy lại như code |
| Code generator của ứng dụng | Chỉ nhận mô hình đã kiểm tra | Có, theo bộ template được tin cậy | Không chuyển chuỗi tự do thành class/method tùy ý |
| `MethodHandles.Lookup` đầy đủ quyền | Không nên trao cho bên ngoài | **Có khả năng tạo handle/định nghĩa class** | Xem như một *capability* đặc quyền |
| `defineHiddenClass(byte[], ...)` | Nhận classfile bytes | Tạo lớp có thể thực thi | Không phải API đánh giá an toàn nghiệp vụ của bytecode |
| Instance / `MethodHandle` trả cho phần khác | Có thể nhận tham số nghiệp vụ | Trong hợp đồng được cấp | Chỉ lộ interface/handle cần thiết, không lộ Lookup dư quyền |
| OS process hoặc container cô lập | Chỉ khi thiết kế cho phép chạy mã chưa tin cậy | Có, nhưng dưới các hạn mức | Là một lớp bảo vệ bên ngoài JVM; vẫn cần hardening |

### 3.1. “Bytecode hợp lệ” khác với “hành vi được phép”

JVM verifier kiểm tra nhiều yêu cầu của định dạng và tính an toàn kiểu của classfile, chẳng hạn stack map và quy tắc truy cập bytecode. Nó **không** thể quyết định một chương trình có nên đọc dữ liệu riêng tư, tạo tiến trình, kết nối mạng hoặc tính toán vô hạn hay không.

Bytecode **hợp lệ về kỹ thuật** vẫn có thể chứa hành vi nguy hiểm trong ngữ cảnh tiến trình hiện tại. `Lookup.defineHiddenClass(...)` không tự biến nguồn byte đó thành “chỉ được tính toán” hoặc “không được làm IO”.

### 3.2. “Không tra được bằng tên” khác với “không có quyền”

Hidden class không có binary name để code khác tìm lại bằng `Class.forName(...)`, nhưng nó vẫn là **lớp Java thực**: có constructor, field, method, static initializer, có thể dùng các API Java được phép trong tiến trình. Nếu code đã được trao khả năng chạy, tính chất ẩn **không phải ranh giới quyền hoặc sandbox**.

### 3.3. Các nguồn dữ liệu cần cùng mức nghi ngờ

Không chỉ các chuỗi có vẻ “giống code” mới nguy hiểm. Những đường đi phải xem xét gồm:

- Tên class/method do request cung cấp rồi truyền vào reflection hoặc `Lookup.findStatic(...)`;
- Một chuỗi “rule” ghép thẳng thành source hoặc fragment classfile;
- File `.class`, JAR hoặc plugin do người dùng tải lên;
- Biểu thức SQL, câu lệnh shell hoặc tên file/path mà code thực thi nội bộ sử dụng;
- Dữ liệu đầu vào được chuyển thành một object có callback, class loader hoặc method handle có đặc quyền;
- Giá trị âm, số cực lớn, biểu thức lặp sâu hay điều kiện luôn đúng dẫn tới **cạn CPU, bộ nhớ hoặc metaspace**.

Cần một threat model cụ thể: **ai gửi**, **gửi được gì**, **bước nào diễn giải dữ liệu**, **được gọi API gì**, **tài nguyên nào có thể bị ảnh hưởng** và **lỗi xuất hiện ở tầng nào**.

## 4. Hướng thiết kế: biến đầu vào thành lệnh có kiểu, không thành mã tùy ý

Một cách thiết kế phù hợp cho nhiều rule engine là định nghĩa **DSL nhỏ** (*domain-specific language*) với grammar rõ ràng. Ví dụ cho phép đúng hai lệnh:

~~~text
ADD:<số nguyên từ 0 đến 100>
MUL:<số nguyên từ 0 đến 100>
~~~

Ở đây, `<...>` trong grammar là ký hiệu mô tả, không phải Java code. Các chuỗi hợp lệ ví dụ `ADD:7` và `MUL:3`. Những chuỗi như `EXEC:99`, `ADD:7;X`, `ADD:999` phải bị **từ chối** — chúng không thuộc grammar/giới hạn.

Quy trình an toàn trong phạm vi bài:

1. **Giới hạn đầu vào:** độ dài tối đa, encoding và số lượng request/operation.
2. **Phân tích chính xác grammar:** không cắt lấy một phần rồi bỏ qua phần thừa; không tự động chấp nhận phần suffix.
3. **Đưa vào kiểu dữ liệu hữu hạn:** mã operation chỉ có `ADD` hoặc `MUL`; toán hạng là `int` trong khoảng được phép.
4. **Phân quyền:** bên gọi có thật sự được thực hiện operation này không, có thuộc tenant/user tương ứng không?
5. **Dùng implementation hoặc bytecode mẫu đáng tin:** dữ liệu đầu vào chỉ thành **tham số của constructor/method**, không được cung cấp mảng `byte[]` của classfile.
6. **Giới hạn tài nguyên/thi hành:** hạn mức tính toán, số lần chạy, timeout ở tầng phù hợp; xử lý overflow bằng quy tắc có chủ đích.
7. **Trả kết quả qua interface đã biết:** không trao `Lookup` đầy quyền hoặc đối tượng hạ tầng không cần thiết cho code bên ngoài.

Một grammar nhỏ giúp **loại bỏ khả năng biểu đạt thao tác không được định nghĩa**. Tuy nhiên, parser/validator không thay thế phân quyền và không ngăn mọi dạng DoS; hệ thống còn phải giới hạn tài nguyên.

## 5. Chương trình chạy được Java 17+: dữ liệu được kiểm tra, bytecode là mẫu tin cậy

Ví dụ sau dùng API Hidden Class thật để minh họa ranh giới. **Không lấy bytecode từ người dùng**: tệp classfile được đọc từ nested class do chính ứng dụng biên dịch. Người dùng chỉ được chọn hai phép toán và một toán hạng trong phạm vi nhỏ.

Lưu trọn chương trình thành **`SafeBoundaryDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.IntUnaryOperator;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class SafeBoundaryDemo {
    private static final Pattern GRAMMAR =
            Pattern.compile("(ADD|MUL):([0-9]{1,3})");

    public static final class TrustedTemplate implements IntUnaryOperator {
        private final int mode;
        private final int operand;

        private TrustedTemplate(int mode, int operand) {
            if (mode != 0 && mode != 1) {
                throw new IllegalArgumentException("Invalid mode");
            }
            this.mode = mode;
            this.operand = operand;
        }

        @Override
        public int applyAsInt(int value) {
            return mode == 0
                    ? Math.addExact(value, operand)
                    : Math.multiplyExact(value, operand);
        }
    }

    private record Command(int mode, int operand) {}

    private static Command parse(String input) {
        if (input == null || input.length() > 7) {
            throw new IllegalArgumentException("Input length");
        }
        Matcher matcher = GRAMMAR.matcher(input);
        if (!matcher.matches()) {
            throw new IllegalArgumentException("Unsupported syntax");
        }
        int operand = Integer.parseInt(matcher.group(2));
        if (operand > 100) {
            throw new IllegalArgumentException("Operand limit");
        }
        int mode = matcher.group(1).equals("ADD") ? 0 : 1;
        return new Command(mode, operand);
    }

    private static IntUnaryOperator createFromTrustedTemplate(
            Command command) throws Throwable {
        byte[] bytes;
        try (InputStream in = SafeBoundaryDemo.class
                .getResourceAsStream(
                        "SafeBoundaryDemo$TrustedTemplate.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing trusted classfile");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup generated =
                MethodHandles.lookup().defineHiddenClass(bytes, false);
        Class<?> type = generated.lookupClass();
        MethodHandle constructor = generated.findConstructor(
                type,
                MethodType.methodType(
                        void.class, int.class, int.class));
        return (IntUnaryOperator) constructor.invoke(
                command.mode(), command.operand());
    }

    public static void main(String[] args) throws Throwable {
        for (String input : new String[] {
                "ADD:7", "MUL:3", "EXEC:99", "ADD:7;X", "ADD:999"
        }) {
            try {
                Command command = parse(input);
                IntUnaryOperator operation =
                        createFromTrustedTemplate(command);
                System.out.println(input + " -> " +
                        operation.applyAsInt(5));
            } catch (IllegalArgumentException rejected) {
                System.out.println(input + " -> rejected");
            }
        }
    }
}
~~~

Biên dịch và chạy **trong thư mục có file nguồn**:

~~~bash
javac --release 17 -Xlint:all SafeBoundaryDemo.java
java SafeBoundaryDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
ADD:7 -> 12
MUL:3 -> 15
EXEC:99 -> rejected
ADD:7;X -> rejected
ADD:999 -> rejected
~~~

### 5.1. Phân tích cơ chế bảo vệ của ví dụ

- `GRAMMAR` chỉ chấp nhận toàn chuỗi theo mẫu `(ADD|MUL):([0-9]{1,3})`. Vì `matcher.matches()` yêu cầu khớp hết đầu vào nên `ADD:7;X` không được âm thầm hiểu thành `ADD:7`.
- Kiểm tra `input.length() > 7` từ chối đầu vào dài quá mức trước khi chạy regex; ứng dụng thực cần giới hạn kích thước **từ tầng đọc request** trước khi cấp phát chuỗi quá lớn, không chỉ ở parser.
- `Integer.parseInt` biến chuỗi số thành `int`; điều kiện `operand > 100` ràng buộc giới hạn nghiệp vụ. Các ký tự không thuộc grammar không trở thành Java source, tên class hoặc phương thức.
- `record Command(int mode, int operand)` lưu **dữ liệu đã có kiểu**; input không còn nắm quyền thay bytecode.
- `SafeBoundaryDemo$TrustedTemplate.class` là **classfile thuộc gói ứng dụng**, không phải file mà client có thể upload. `defineHiddenClass` chỉ sử dụng bytecode này.
- `generated.findConstructor(...)` tạo instance từ **returned Lookup của hidden class**; giá trị client chỉ đi vào hai tham số constructor.
- `IntUnaryOperator` là hợp đồng được ứng dụng biết trước. Code bên ngoài không cần biết hidden class có tên gì.
- `Math.addExact` và `Math.multiplyExact` ném `ArithmeticException` khi tràn số nguyên thay vì âm thầm wrap. Trong chương trình demo, các đầu vào thử không tràn.
- Các chuỗi không hợp lệ bị từ chối trước khi `createFromTrustedTemplate` chạy.

**Ranh giới bảo vệ của ví dụ:** người dùng không thể yêu cầu tạo lớp mang bytecode bất kỳ qua input `"ADD:7"`. Nhưng nếu nguồn `TrustedTemplate.class` trong gói triển khai bị thay thế, hoặc hàm parser bị sửa để lấy file class do người dùng chỉ định, giả định bảo mật đã thay đổi. Kiểm tra toàn vẹn artifact và kiểm soát deployment vẫn cần thiết.

### 5.2. Không nhầm ví dụ minh họa với kiến trúc production

Ví dụ cố ý gọi `defineHiddenClass` cho mỗi lệnh hợp lệ để người học nhìn thấy API. **Đây không phải mẫu tối ưu cho hệ thống có nhiều request.** Với hai phép toán cố định, cách đơn giản hơn là dùng luôn `Math.addExact`/`Math.multiplyExact` hoặc một interpreter theo enum. Không có lý do hiệu năng mặc định để tạo một hidden class cho mỗi request.

Khi framework thực sự cần code generation, nên cache **factory/handle** theo key cấu hình đã chuẩn hóa, có giới hạn kích thước và chính sách hết hạn. Sinh class liên tục có thể tạo áp lực lên class metadata/metaspace, kể cả khi mỗi instance rất nhỏ.

### 5.3. Những chi tiết cần kiểm tra khi chuyển lên production

- `record` được đưa vào ngôn ngữ chính thức từ Java 16, vì vậy ví dụ này dùng `--release 17`. API `defineHiddenClass` có từ Java 15; không cần preview.
- Trong ví dụ, dữ liệu chỉ có tối đa bảy ký tự và các operation hữu hạn. Với grammar phức tạp, dùng parser thích hợp, tránh regex dễ gây backtracking vô hạn hoặc đầu vào đệ quy quá sâu.
- Không trả nguyên exception internal/stack trace cho client; log có kiểm soát, trả lỗi theo contract và không lộ secret.
- Nếu `createFromTrustedTemplate` gặp lỗi classfile, `Lookup` hoặc method handle, đó là **lỗi triển khai/nội bộ**, không nên gắn nhãn “request không hợp lệ” và che giấu nguyên nhân.
- `catch (IllegalArgumentException)` trong demo phục vụ ví dụ đầu vào đơn giản. Hệ thống thực nên tách rõ **lỗi parse/validation**, **lỗi authorization**, **lỗi thực thi** và **lỗi hạ tầng**, tránh một catch quá rộng.
- Đừng dùng dữ liệu từ request để quyết định arbitrary class name, package, module hoặc method name trong bước tạo Lookup. Nếu phải định tuyến động, kiểm tra qua registry hữu hạn đã được đăng ký/ủy quyền.

## 6. `MethodHandles.Lookup` là capability, không phải utility vô hại

Một `Lookup` được tạo từ `MethodHandles.lookup()` trong class tin cậy có thể chứa **quyền tạo method handle** cho các member không public, và `defineHiddenClass(...)` yêu cầu **full privilege access**. Trả đối tượng Lookup ấy cho mã/plugin chưa tin cậy có thể **trao thêm khả năng** mà bên nhận không được phép có.

Đây là khác biệt quan trọng:

| Giá trị đưa ra ngoài | Khả năng được trao | Cần cẩn trọng ở đâu? |
| --- | --- | --- |
| Một `int` hoặc `String` đã xác thực | Dữ liệu | Giới hạn kích thước, nội dung, quyền nghiệp vụ |
| `IntUnaryOperator` hoặc interface giới hạn | Hành vi qua API đã định nghĩa | Implementation vẫn có thể có side effect; audit contract |
| Một `MethodHandle` đã chọn | Khả năng gọi một member cụ thể | Handle bản thân là capability, không đưa nhầm handle nhạy cảm |
| `Lookup` đầy đủ quyền | Khả năng tiếp tục **tạo handles** cho những member có quyền truy cập | Không trao cho code chưa tin cậy; kiểm soát privilege & module |
| `byte[]` classfile không đáng tin đưa vào `defineHiddenClass` | Khả năng đưa mã mới vào JVM | **Không được xem là an toàn chỉ nhờ verifier/hidden name** |

Khi API cần cấp hành vi cho một thành phần khác, chọn **giao diện tối thiểu** hoặc handle được xác định từ trước; không trao toàn bộ `Lookup` nếu bên nhận không có nhiệm vụ tạo handles.

### 6.1. Ví dụ chạy được: giảm quyền Lookup bằng `dropLookupMode`

Lưu file **`LookupCapabilityDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class LookupCapabilityDemo {
    private static final class Secret {
        private static String value() {
            return "internal";
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup trusted = MethodHandles.lookup();
        MethodHandles.Lookup limited =
                trusted.dropLookupMode(MethodHandles.Lookup.PRIVATE);

        System.out.println("trustedFull=" +
                trusted.hasFullPrivilegeAccess());
        System.out.println("limitedFull=" +
                limited.hasFullPrivilegeAccess());

        try {
            limited.findStatic(
                    Secret.class,
                    "value",
                    MethodType.methodType(String.class));
            System.out.println("limitedPrivateAccess=true");
        } catch (IllegalAccessException denied) {
            System.out.println("limitedPrivateAccess=false");
        }

        MethodHandle method = trusted.findStatic(
                Secret.class,
                "value",
                MethodType.methodType(String.class));
        System.out.println("trustedValue=" +
                (String) method.invokeExact());
    }
}
~~~

~~~bash
javac --release 17 -Xlint:all LookupCapabilityDemo.java
java LookupCapabilityDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
trustedFull=true
limitedFull=false
limitedPrivateAccess=false
trustedValue=internal
~~~

**Giải thích:** `trusted` là lookup được tạo trong `LookupCapabilityDemo`, cùng nest với `Secret` nên có thể tạo handle tới private method. `dropLookupMode(PRIVATE)` tạo **lookup mới bị giảm quyền**; `limited` không tạo được handle tới `Secret.value()`, còn `trusted` ban đầu không bị đổi.

**Giới hạn của kỹ thuật này:** giảm quyền của một `Lookup` **không tạo sandbox cho toàn bộ JVM**. Nếu bên nhận đã có handle đặc quyền, object nhạy cảm, quyền hệ điều hành hoặc đường gọi khác, giảm quyền một lookup không thu hồi các khả năng đó. Đừng dùng `dropLookupMode` như lời bảo đảm có thể chạy mã không tin cậy trong cùng tiến trình.

### 6.2. Ranh giới nest và module

Trong Java Module System, quyền của `Lookup` chịu ảnh hưởng bởi class, package, module và các quyền đọc/mở tương ứng. `MethodHandles.privateLookupIn(...)` có thể tạo lookup phù hợp cho một class đích khi các điều kiện quyền được đáp ứng; việc mở package rộng rãi để runtime khác truy cập private không phải một giải pháp bảo mật.

Với hidden class, `ClassOption.NESTMATE` cho phép class được định nghĩa tham gia nest của lookup class, có thể dùng private access theo quy tắc nest. Chỉ sử dụng khi generator **thật sự cần** quyền đó. Thêm `NESTMATE` nhằm “chạy được bất kỳ bytecode nào” là sai hướng thiết kế; nó **mở rộng khả năng truy cập trong nest**, không giới hạn mã.

## 7. Những điều Hidden Class không bảo vệ

**Không cách ly hệ điều hành.** Một lớp ẩn chạy trong **cùng tiến trình JVM**, thường với cùng user, environment, file descriptor, khả năng mạng và tài nguyên được cấp cho tiến trình đó. Nếu bytecode đủ quyền gọi một API, nó có thể gây tác dụng phụ tương ứng. Tên lớp ẩn hay việc class có thể unload không tước quyền IO.

**Không phân biệt “mã xấu” dựa vào classfile format.** Verifier bảo đảm những thuộc tính hợp lệ của bytecode và luật JVM, không định nghĩa business-policy cho nội dung được phép. Class hợp lệ vẫn có thể tạo vòng lặp tốn CPU, lưu giữ bộ nhớ, khởi tạo thread hoặc đọc dữ liệu.

**Không ngăn tác dụng phụ của static initializer.** Với `defineHiddenClass(bytes, true)`, JVM có thể thực thi `<clinit>` trong quá trình khởi tạo class. Với `false`, một lần sử dụng tích cực sau đó vẫn có thể khởi tạo. Không định nghĩa/khởi tạo classfile chưa tin cậy rồi hy vọng có cơ hội “kiểm tra an toàn sau”.

**Không chuyển classfile tùy ý thành “data only”.** Một `byte[]` đưa vào `defineHiddenClass` là **đầu vào mã**, không phải một blob dữ liệu vô hại chỉ vì nó là mảng byte. Ranh giới phải được kiểm soát **trước API**.

**Không thay thế xác thực đầu vào và phân quyền nghiệp vụ.** Ngay cả khi bytecode là template của ứng dụng, dữ liệu có thể làm task chạy quá lâu, truy cập sai tenant, chọn nhầm tài nguyên hoặc tiêu tốn bộ nhớ. Kiểm tra quyền của request, giới hạn tài nguyên và validate input vẫn là trách nhiệm của kiến trúc.

**Không bảo đảm class unload đúng thời điểm.** Hidden class mặc định có thể unload độc lập với defining loader khi không còn tham chiếu phù hợp, nhưng GC quyết định thời gian. Tạo mã động quá nhiều vẫn có thể gây áp lực class metadata.

## 8. Java Security Manager không phải phương án bảo vệ hiện đại

Những bài hướng dẫn Java cũ đôi khi đề xuất `SecurityManager`, `Policy` hoặc `AccessController` để chạy một JAR/classfile chưa tin cậy trong cùng JVM với quyền “hạn chế”. **Không áp dụng cách này như một giải pháp mới**:

- Security Manager đã bị deprecated for removal trong **Java 17 (JEP 411)**.
- Từ **JDK 24 (JEP 486)**, Security Manager **bị vô hiệu hóa vĩnh viễn**, không thể bật lại lúc khởi động hoặc cài lúc runtime để cô lập plugin.
- Các API cũ có thể vẫn tồn tại ở một số phiên bản vì tương thích nguồn/binary, nhưng không còn là cơ chế sandbox được hỗ trợ cho kiến trúc mới.

Vì bài chỉ giữ kiến thức còn áp dụng hiện nay, **không** đưa ví dụ cấu hình Security Manager làm biện pháp bảo vệ. Ranh giới thực thi code chưa tin cậy cần được thiết kế ở **tầng tiến trình/hệ điều hành/triển khai**, cùng với hạn chế quyền và tài nguyên.

Nguồn chính thức: [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486) và [Oracle JDK 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html).

## 9. Khi thật sự phải chạy mã do bên ngoài kiểm soát

Có những yêu cầu sản phẩm cho phép người dùng viết **Java code, JAR, bytecode hoặc plugin với ngôn ngữ tổng quát**. Trong trường hợp đó, một parser DSL allowlist như phần 4 không còn đủ, vì **người dùng được phép định nghĩa hành vi mới**. Không nên nạp và chạy các artifact đó trực tiếp trong cùng JVM chứa secrets, database connection và hệ thống nghiệp vụ.

Kiến trúc giảm rủi ro phổ biến:

~~~text
               SERVER CHÍNH (tin cậy)
             +--------------------------+
             | Xác thực / phân quyền     |
             | Hạn mức & kiểm tra input  |
             | Job queue với id riêng    |
             +--------------------------+
                         |
                         | Giao job tối thiểu;
                         | không chuyển secret
                         v
              TIẾN TRÌNH/WORKER CÔ LẬP
             +--------------------------+
             | Danh tính OS riêng       |
             | File system tối thiểu    |
             | Network mặc định hạn chế |
             | Giới hạn CPU / RAM / IO  |
             | Deadline & quota job     |
             | Audit & cleanup          |
             +--------------------------+
                         |
                         | Trả kết quả đã kiểm tra
                         v
               SERVER CHÍNH (tin cậy)
~~~

### 9.1. Những biện pháp phối hợp

- **Tách process hoặc môi trường thực thi:** không cho mã khách hàng chạy trong cùng address space với server chính nếu yêu cầu bảo vệ chống mã độc.
- **Giảm quyền OS:** tài khoản/quyền file riêng, không chạy dưới identity có quyền đọc secrets, database credential hoặc khóa ký của server.
- **Giới hạn tài nguyên:** CPU, RAM, số process/thread, dung lượng file, output và số lượng job đồng thời; bảo đảm task bị chặn khi vượt budget.
- **Giới hạn network:** mặc định không cấp kết nối ra ngoài nếu không cần; chỉ mở những đích thật sự được phép.
- **Môi trường đầu vào tối thiểu:** không mount thư mục nhạy cảm hoặc truyền environment chứa secrets; dùng thư mục tạm riêng, dọn dẹp khi hoàn thành.
- **Deadline thực thi:** timeout ở **tầng giám sát tiến trình** có khả năng hủy worker nếu cần. Không dựa duy nhất vào `Future.cancel(true)` hay interrupt một Java thread để cam kết dừng mã không hợp tác.
- **Giao tiếp có schema:** truyền job qua giao thức dữ liệu, không serialize object tùy ý từ client rồi tin rằng quá trình deserialization an toàn.
- **Giám sát và cleanup:** log có id job, giới hạn tần suất, cô lập lỗi, làm sạch worker và xem xét việc tái sử dụng worker khi có untrusted code.

**Lưu ý:** container/VM hay namespace chỉ an toàn trong phạm vi cấu hình và threat model thực tế. Không có một cờ đơn lẻ nào biến execution thành “an toàn tuyệt đối”. Isolation, quyền OS, cập nhật runtime và kiểm tra đầu vào cần đi cùng nhau.

### 9.2. Compiling không phải là executing, nhưng vẫn có rủi ro

Nếu người dùng upload Java source và server **biên dịch** source, đó chưa nhất thiết là **chạy `main`** của chương trình người dùng. Tuy nhiên, pipeline compiler/plugin/annotation processor, việc xử lý file và classpath có thể tự tạo bề mặt tấn công, tiêu tốn tài nguyên hoặc kích hoạt code trong một build không được kiểm soát.

Với môi trường xử lý source chưa tin cậy, cần tổ chức **bước compile** trong execution environment được hạn chế và thiết kế classpath/toolchain phù hợp. Không gom “compile” và “run” vào cùng quyền với dịch vụ chính rồi coi rủi ro chỉ xảy ra lúc gọi `java`.

## 10. Các lớp phòng vệ cụ thể cho input và codegen

### 10.1. Input validation: rõ nghĩa, đủ sớm và fail closed

Một số tiêu chí cần làm rõ:

| Kiểm tra | Ví dụ áp dụng | Lỗi nếu bỏ qua |
| --- | --- | --- |
| Kích thước/độ dài | Giới hạn body, chuỗi, số node AST | Tốn memory/CPU trước cả bước validate |
| Encoding/canonicalization | UTF-8, quy tắc Unicode/case được định nghĩa | Nhiều biểu diễn của “cùng” một lệnh, bypass logic |
| Grammar khép kín | `ADD` hoặc `MUL`, khớp toàn bộ | Chèn suffix/câu lệnh ngoài dự kiến |
| Giá trị/range | Toán hạng `0..100` | Vượt giới hạn nghiệp vụ |
| Ủy quyền thao tác | Phép nào được phép trên tenant này? | Người hợp lệ làm việc vượt quyền |
| Giới hạn cấu trúc | Độ sâu/độ dài AST, số bước | Cạn stack, vòng lặp, DoS |
| Giới hạn runtime | CPU/time/memory/output/metaspace | Cạn tài nguyên khi code đã chạy |
| Xử lý lỗi | Tách lỗi khách hàng và lỗi nội bộ | Lộ stack trace, che lỗi hạ tầng |

**Fail closed** nghĩa là cú pháp không nhận diện được phải **bị từ chối**, thay vì đoán một fallback hoặc cố chạy chuỗi còn lại. Trong ví dụ, `EXEC:99` và `ADD:7;X` không được phép chuyển thành một operation khác.

**Không coi escaping là mọi thứ.** Escaping đúng ngữ cảnh có ích ở HTML, SQL và các sink cụ thể, nhưng không biến Java bytecode tùy ý thành một DSL hữu hạn. Bảo vệ codegen phải bắt đầu từ **giới hạn khả năng biểu đạt của input** và chính sách quyền.

### 10.2. Giới hạn số lượng class sinh

Ngay cả nếu tất cả classfile là từ generator đáng tin, input có thể gây **bùng nổ cardinality**: mỗi tổ hợp tham số tạo ra một class mới. Điều này có thể làm tăng thời gian class loading, heap, JIT cost và metaspace.

Ví dụ với bài toán chỉ có `ADD:n` và `MUL:n`, không cần một class riêng cho từng request; việc đưa `n` vào field của instance được chọn chính là cách tránh sinh bytecode từ giá trị bên ngoài. Một hệ thống thực nên cân nhắc:

- Cache có kích thước và vòng đời xác định theo **mẫu code**, không theo mọi giá trị runtime.
- Reuse một instance/factory khi các tham số có thể thay đổi.
- Mức trần số class được sinh cho từng tenant/job.
- Theo dõi số class load/unload, metaspace và latency trong stress test.
- Không cho phép input đặt tên phương thức/class không giới hạn để tạo vô số định nghĩa động.

### 10.3. Giá trị số và lỗi overflow

`Math.addExact`/`Math.multiplyExact` phát hiện tràn `int` và ném `ArithmeticException`. Nhưng **phát hiện overflow không phải giới hạn thời gian chạy**. Nếu DSL cho phép loop, recursion hoặc phép tính chi phí cao thì phải ràng buộc số bước/tổng resource riêng.

Khi xử lý phép tính lớn, quyết định rõ có dùng `long`, `BigInteger` hay giới hạn độ lớn. Không tự động cho phép arbitrary precision với dữ liệu không giới hạn vì nó có thể tăng chi phí CPU và memory.

### 10.4. Đầu ra cũng có thể là một điểm nguy hiểm

Kết quả của generated code chưa chắc đáng tin chỉ vì nó do JVM trả về. Kiểm tra kiểu, kích thước, định dạng và quyền trước khi:

- Ghi vào database dưới quyền server;
- Trả cho người dùng khác;
- Sử dụng làm đường dẫn hoặc tên tài nguyên;
- Đưa vào shell command, SQL, HTML hoặc một trình thông dịch khác.

Ranh giới dữ liệu sang mã có thể **lặp lại nhiều lần**: một kết quả trông như dữ liệu bình thường có thể trở thành input nguy hiểm ở bước tiếp theo.

## 11. Tình huống lỗi thiết kế và cách sửa

**Tình huống A — “Input là Java source, ta cứ ghép vào template rồi biên dịch.”**  
Rủi ro: chuỗi bên ngoài có thể thay đổi cấu trúc chương trình. Sửa: nếu chỉ cần vài phép toán, chuyển thành AST/enum allowlist và truyền tham số cho implementation đáng tin. Nếu cần chạy Java source tùy ý, dùng execution worker được cô lập và hạn chế tài nguyên.

**Tình huống B — “Bytecode từ request đã qua JVM verifier nên an toàn.”**  
Rủi ro: verifier không đánh giá permission policy, IO, vòng lặp hoặc business intent. Sửa: không tải bytecode từ request vào JVM tin cậy; kiểm soát nguồn artifact hoặc cách ly thực thi.

**Tình huống C — “Dùng hidden class để không ai tìm thấy mã độc.”**  
Rủi ro: tên ẩn không cắt quyền thực thi; còn có thể tăng khó khăn khi debug. Sửa: coi hidden class là cơ chế triển khai nội bộ, không phải sandbox hay biện pháp ẩn mã.

**Tình huống D — “Cho plugin full Lookup để nó tự tạo các handle cần dùng.”**  
Rủi ro: plugin có thêm khả năng truy cập member mà framework không dự định. Sửa: trả interface hoặc những method handle được chọn và kiểm tra; tách môi trường nếu plugin không tin cậy. `dropLookupMode` có thể giới hạn **một capability**, nhưng không bảo vệ toàn bộ tiến trình.

**Tình huống E — “Đổi `initialize=false` là không còn tác dụng phụ.”**  
Rủi ro: static initializer sẽ chạy khi class được sử dụng theo quy tắc Java; code bên trong method cũng có tác dụng phụ. Sửa: không định nghĩa bytecode chưa tin cậy trong process; hiểu rõ cả bước define/link/init/invoke.

**Tình huống F — “Có Security Manager là xong.”**  
Rủi ro: từ JDK 24 không thể dùng Security Manager làm sandbox. Sửa: thiết kế process isolation, least privilege và quotas theo JEP 486.

**Tình huống G — “Mọi request đều được tạo hidden class mới, rồi GC lo phần còn lại.”**  
Rủi ro: metadata và cache có thể tích tụ, JVM không đảm bảo thời điểm unload. Sửa: reuse fixed templates, cache bounded, instrument class loading/metaspace, tránh `STRONG` nếu vòng đời ngắn.

**Tình huống H — “Kiểm tra role rồi khỏi kiểm tra tenant.”**  
Rủi ro: người dùng có role hợp lệ vẫn có thể tác động tài nguyên tenant khác. Sửa: authorization gắn với **operation, resource và ownership**; dữ liệu đã parse cũng không được bỏ qua quyền nghiệp vụ.

**Tình huống I — “Dùng thread interrupt là timeout tuyệt đối.”**  
Rủi ro: code không hợp tác có thể không chấm dứt theo kỳ vọng. Sửa: với code không tin cậy, theo dõi ở cấp process có thể hủy worker và giới hạn tài nguyên qua OS.

## 12. Checklist review code sinh class từ dữ liệu bên ngoài

- [ ] Nguồn input được đánh dấu **không tin cậy**, kể cả dữ liệu từ tài khoản xác thực.
- [ ] Body, chuỗi, số command, AST node và độ sâu được giới hạn ngay tại ingestion.
- [ ] Parser dùng grammar hoàn chỉnh, match toàn bộ, từ chối unknown operation/suffix.
- [ ] Sau parse, dữ liệu ở dạng typed command/AST; không truyền lại source string cho compiler/evaluator như code tự do.
- [ ] Có authorization cho operation **và** resource/tenant.
- [ ] Generator sử dụng template/bytecode đáng tin; không chấp nhận classfile bytes hoặc class name arbitrary từ client.
- [ ] `MethodHandles.Lookup` có đặc quyền được giữ trong thành phần tin cậy; bên ngoài chỉ nhận interface/handle tối thiểu.
- [ ] `NESTMATE`/module opens không được bật chỉ để tránh kiểm tra quyền.
- [ ] Tác dụng phụ từ `<clinit>`, constructor và method đều nằm trong threat model.
- [ ] Có hạn mức công việc, hạn mức số class, timeout và quota resource thích hợp.
- [ ] Trường hợp thực sự chạy code bên ngoài có ranh giới process/OS và least privilege, không dùng Security Manager.
- [ ] Không trả stack trace/secret qua lỗi validation; log có request/job id và bảo vệ dữ liệu nhạy cảm.
- [ ] Có test trường hợp hợp lệ, giá trị biên, null, input quá lớn, syntax injection, overflow và lặp nhiều request.
- [ ] Có quan sát metaspace/class loading, CPU, memory và thời gian chạy để phát hiện DoS.

## 13. Bài tập tự kiểm tra

**Câu 1.** Tại sao `defineHiddenClass(userBytes, true)` không an toàn chỉ vì lớp có tên ẩn?  
**Đáp án:** Vì bytecode từ user vẫn là mã thực thi trong JVM, không bị sandbox bởi Hidden Class; tên ẩn và verifier không hạn chế hành vi IO/CPU/quyền.

**Câu 2.** Nếu sản phẩm chỉ hỗ trợ `ADD:n` và `MUL:n`, có cần cho user gửi Java source?  
**Đáp án:** Không. Nên parse một grammar hữu hạn thành typed command, kiểm tra hạn mức và dùng implementation đáng tin.

**Câu 3.** Vì sao `ADD:7;X` trong ví dụ bị từ chối?  
**Đáp án:** `Matcher.matches()` yêu cầu khớp **toàn bộ input** theo grammar, nên không chấp nhận phần suffix ngoài mẫu.

**Câu 4.** Ai quyết định phép toán được phép cho tenant hiện tại?  
**Đáp án:** Lớp authorization nghiệp vụ của dịch vụ; parser chỉ kiểm tra syntax/range, không thay thế quyền thao tác.

**Câu 5.** `Lookup` đầy đủ quyền có thể được chia sẻ như một chuỗi dữ liệu thông thường không?  
**Đáp án:** Không nên. Nó là capability có khả năng tạo method handles và định nghĩa lớp trong ngữ cảnh quyền; cấp cho thành phần tin cậy thật sự cần, ưu tiên interface/handle tối thiểu.

**Câu 6.** `dropLookupMode(PRIVATE)` có tạo một sandbox cho plugin không?  
**Đáp án:** Không. Nó chỉ giới hạn một Lookup mới, không thu hồi quyền OS, handle đã có hay mọi đường thực thi khác.

**Câu 7.** Vì sao `initialize=false` không có nghĩa “bytecode sẽ không chạy”?  
**Đáp án:** Class vẫn có thể được khởi tạo sau này khi dùng tích cực, và method/constructor có thể chạy hành vi có side effect.

**Câu 8.** Security Manager có còn là kiến trúc sandbox được hỗ trợ từ JDK 24 không?  
**Đáp án:** Không. JEP 486 đã vô hiệu hóa vĩnh viễn Security Manager; cần cơ chế cô lập tiến trình/quyền/tài nguyên khác.

**Câu 9.** Trong demo, bytecode tới từ đâu? User có được chọn một classfile tùy ý không?  
**Đáp án:** Từ classfile `TrustedTemplate` do chính ứng dụng biên dịch và đóng gói; user chỉ chọn operation và toán hạng đã kiểm tra.

**Câu 10.** Nếu chỉ có hai phép toán, có nên tạo hidden class mới cho mỗi request ở production?  
**Đáp án:** Thường không. Có thể dùng interpreter/class thường, hoặc tái sử dụng factory; việc tạo class liên tục gây thêm class metadata và chi phí runtime.

## 14. Tài liệu tham khảo chính thức còn hiệu lực

- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu của Hidden Class, tính không tra theo tên, vòng đời và trường hợp sinh mã.
- [Oracle Java SE 26 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền của Lookup, `defineHiddenClass(...)`, `dropLookupMode(...)`, method handles và giới hạn package/module.
- [Oracle Java SE 26 — `MethodHandles`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()` như một capability và các lưu ý về trao quyền cho code tin cậy.
- [OpenJDK JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): quyết định JDK 24 vô hiệu hóa Security Manager.
- [Oracle JDK 24 — Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): hành vi đã thay đổi và lý do không dùng cho thiết kế sandbox mới.
- [Oracle Java SE 26 — `Math.addExact`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): cách phát hiện overflow có chủ đích khi phép toán được cho phép.
