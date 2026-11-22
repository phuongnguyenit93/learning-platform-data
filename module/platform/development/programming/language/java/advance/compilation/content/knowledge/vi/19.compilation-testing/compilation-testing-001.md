# Thiết kế ca phải biên dịch thành công và ca phải bị từ chối trong Java

## 1. Mục tiêu học tập

Một bài kiểm thử biên dịch (compile-time test) kiểm tra xem **trình biên dịch Java có chấp nhận hoặc từ chối một đoạn mã theo quy tắc ngôn ngữ hay không**. Hai kỳ vọng có vai trò ngang nhau:

- **Ca dương (positive/acceptance case):** mã hợp lệ phải được biên dịch thành công. Nếu trình biên dịch từ chối, đây là lỗi của ca kiểm thử, cấu hình hoặc trình biên dịch.
- **Ca âm (negative/rejection case):** mã vi phạm có chủ đích một quy tắc phải bị trình biên dịch từ chối. Nếu nó biên dịch được, ca kiểm thử thất bại; nếu bị từ chối vì một lỗi hoàn toàn khác, ca đó cần được điều tra, không nên tự động coi là chứng minh đúng quy tắc cần kiểm tra.

Sau bài này, người học có thể thiết kế một cặp ca hợp lệ/bất hợp lệ cho cùng một quy tắc, chạy bằng **javac** hoặc **JavaCompiler API**, kiểm tra kết quả biên dịch và chẩn đoán lỗi, đồng thời tổ chức dữ liệu thử nghiệm để tránh phụ thuộc vào lớp đã biên dịch trước đó.

**Giới hạn phạm vi:** đây là kiểm thử *mã nguồn có được chấp nhận khi biên dịch hay không*. Nó khác với kiểm thử đầu ra, logic nghiệp vụ, hiệu năng hoặc ngoại lệ phát sinh khi chương trình đã chạy.

## 2. Hợp đồng của một ca kiểm thử biên dịch

Để ca kiểm thử có thể lặp lại và có ý nghĩa, cần ghi rõ:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Quy tắc | Đang kiểm tra ràng buộc ngôn ngữ nào? | Không gán giá trị String cho biến int |
| Nguồn đầu vào | Tệp/lớp và toàn bộ mã nguồn là gì? | InvalidType.java |
| Môi trường | JDK, phiên bản ngôn ngữ, classpath/module path, tùy chọn nào? | JDK 17+, --release 17, UTF-8 |
| Kỳ vọng | Chấp nhận hay từ chối? | REJECT |
| Tiêu chí quan sát | Trạng thái javac, số lỗi, hiện vật đầu ra? | javac thất bại và có chẩn đoán ERROR |
| Nguyên nhân dự kiến | Vì sao phải từ chối? | Không tương thích kiểu |
| Cô lập | Làm sao đảm bảo không dùng lại mã đã biên dịch? | Thư mục đầu ra mới cho mỗi ca |

Với lệnh **javac**, thoát thành công thường có mã **0**; thất bại có mã khác **0**. Trong **JavaCompiler API**, giá trị trả về của tác vụ biên dịch là **true** hoặc **false**, và **DiagnosticCollector** cho phép phân biệt chẩn đoán loại **ERROR**, **WARNING** và các loại khác. Một cảnh báo tự nó không đồng nghĩa thất bại biên dịch, trừ khi ta chủ động bật chính sách biến cảnh báo thành lỗi như **-Werror**.

Một ca âm tốt **không chỉ** khẳng định “có lỗi bất kỳ”: phải bảo đảm mã nền hợp lệ, lỗi được đưa vào có chủ đích, và kiểm tra nhóm chẩn đoán hoặc xem lại thông báo để chắc chắn lỗi đúng nguyên nhân. Chuỗi thông báo tiếng Anh/tiếng Việt, số dòng và thứ tự chẩn đoán có thể khác theo phiên bản JDK, locale và trình biên dịch.

## 3. Thiết kế cặp ca đối chứng trước khi viết tự động hóa

Cách đơn giản nhất là bắt đầu từ một ví dụ phải biên dịch được, sau đó thay đổi **một điểm duy nhất** để tạo ví dụ phải bị từ chối. Ví dụ:

**ValidAssignment.java — chấp nhận**

~~~java
public class ValidAssignment {
    int count = 5;
}
~~~

**InvalidAssignment.java — từ chối**

~~~java
public class InvalidAssignment {
    int count = "five";
}
~~~

Hai đoạn chỉ khác biểu thức gán. Trình biên dịch phải chấp nhận số nguyên **5**, nhưng không thể gán **String** cho **int**. Nếu sửa nhiều thứ cùng lúc (tên lớp, dấu ngoặc, import và kiểu), khi ca âm thất bại sẽ khó xác định lỗi nào là nguyên nhân.

Chạy thủ công trong hai thư mục đầu ra **riêng biệt** (sau khi lưu mỗi ví dụ vào tệp đúng tên):

~~~text
javac --release 17 -encoding UTF-8 -d out-valid ValidAssignment.java
javac --release 17 -encoding UTF-8 -d out-invalid InvalidAssignment.java
~~~

Lệnh thứ nhất phải thành công; lệnh thứ hai phải thất bại với lỗi kiểu dữ liệu. Cần **kiểm tra trạng thái trả về** của từng lệnh ngay sau khi chạy. Đừng kết luận chỉ dựa vào việc màn hình có/không có thông báo; biên dịch thành công thường không in gì. Không cần chạy **java ValidAssignment** vì ví dụ này không có **main**: mục tiêu là biên dịch, không phải thực thi.

Đầu ra **-d** phải là thư mục mới hoặc được dọn trước mỗi lần thử. Sự tồn tại của tệp **.class** cũ không chứng minh lần biên dịch hiện tại thành công. Trái lại, một lượt biên dịch thất bại với nhiều tệp nguồn cũng không bảo đảm không có bất kỳ **.class** nào được sinh ra; đừng lấy quy tắc “thư mục đầu ra rỗng” làm tiêu chí từ chối tổng quát.

## 4. Ma trận các loại ca nên có

| ID | Kịch bản | Kỳ vọng | Điểm quan sát chính |
| --- | --- | --- | --- |
| P01 | Lớp Java hợp lệ, khai báo phương thức đúng kiểu | Chấp nhận | Tác vụ biên dịch thành công, không có ERROR |
| P02 | Dùng generic đúng tham số kiểu | Chấp nhận | List<String> chứa các giá trị String |
| N01 | Sai cú pháp (thiếu biểu thức sau dấu =) | Từ chối | Lỗi phân tích cú pháp |
| N02 | Gán String cho int | Từ chối | Lỗi kiểm tra kiểu |
| N03 | Truy cập phương thức private từ lớp khác | Từ chối | Lỗi kiểm tra quyền truy cập |
| N04 | Gọi phương thức khai báo checked exception nhưng không bắt/khai báo | Từ chối | Lỗi kiểm tra ngoại lệ có kiểm tra |
| N05 | Gán List<Integer> cho List<String> | Từ chối | Lỗi ràng buộc kiểu generic |

Tùy mục tiêu module, có thể bổ sung ca với **tên symbol không tồn tại**, xung đột overload, giới hạn phạm vi biến, quy tắc **sealed class**, hay mã không hợp lệ với mức **--release** đã chọn. Mỗi nhánh cần đối chứng dương và nguyên nhân thất bại riêng; không cần đưa tất cả tính năng Java vào một ca.

**Lưu ý quan trọng:** chia cho 0 với mẫu số là biến ở runtime, truy cập phần tử mảng sai chỉ số khi chạy, hoặc lỗi logic trả về sai kết quả không tự động là ca âm biên dịch. Trong một số biểu thức hằng, Java có quy định compile-time riêng; muốn kiểm thử quy định nào phải xác định nó chính xác trước khi viết kỳ vọng.

## 5. Bộ kiểm thử tự động chạy được với Java 17+

Bộ chạy sau đây dùng **javax.tools.JavaCompiler** thuộc JDK để biên dịch trực tiếp các chuỗi mã nguồn. Nó không đặt mã cố ý sai vào cây **src/main/java** hoặc **src/test/java** vốn bị build system biên dịch trước khi test chạy.

Lưu toàn bộ chương trình sau vào **CompilationCases.java** với mã hóa UTF-8. Chương trình tạo một thư mục biên dịch tạm **riêng cho từng ca**, giới hạn ngôn ngữ bằng **--release 17**, tắt annotation processing vì bài học đang tập trung vào quy tắc Java thuần, đếm chẩn đoán loại **ERROR**, và xóa thư mục tạm sau khi hoàn tất.

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CompilationCases {
    record Case(String name, String className, String code, boolean shouldCompile) {}

    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Cần chạy bằng JDK 17+ (có javac).");
        }

        List<Case> cases = List.of(
            new Case("valid-basic", "ValidBasic", """
                public class ValidBasic {
                    public static int square(int x) { return x * x; }
                }
                """, true),
            new Case("valid-generic", "ValidGeneric", """
                import java.util.List;
                public class ValidGeneric {
                    List<String> names = List.of("A", "B");
                }
                """, true),
            new Case("invalid-syntax", "InvalidSyntax", """
                public class InvalidSyntax { int count = ; }
                """, false),
            new Case("invalid-type", "InvalidType", """
                public class InvalidType { int count = "five"; }
                """, false),
            new Case("invalid-access", "InvalidAccess", """
                class Vault { private static void close() {} }
                public class InvalidAccess { void run() { Vault.close(); } }
                """, false),
            new Case("invalid-checked-exception", "InvalidCheckedException", """
                import java.io.IOException;
                public class InvalidCheckedException {
                    static void risky() throws IOException {}
                    void run() { risky(); }
                }
                """, false),
            new Case("invalid-generic", "InvalidGeneric", """
                import java.util.List;
                public class InvalidGeneric {
                    List<String> names = List.of(1, 2);
                }
                """, false)
        );

        Path root = Files.createTempDirectory("compile-tests-");
        try {
            for (Case c : cases) {
                Path output = Files.createDirectory(root.resolve(c.name()));
                DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
                try (var files = compiler.getStandardFileManager(diagnostics, null, null)) {
                    List<String> options = List.of(
                        "--release", "17", "-encoding", "UTF-8", "-proc:none",
                        "-classpath", output.toString(), "-d", output.toString()
                    );
                    boolean success = Boolean.TRUE.equals(compiler.getTask(
                        null, files, diagnostics, options, null,
                        List.of(new Source(c.className(), c.code()))
                    ).call());
                    long errorCount = diagnostics.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
                    if (success != c.shouldCompile() || (!success && errorCount == 0)) {
                        throw new AssertionError(c.name() + ": unexpected result; errors=" + errorCount);
                    }
                    System.out.println(c.name() + ": PASS (" + (success ? "compiled" : "rejected") + ")");
                }
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Chạy từ thư mục chứa tệp **CompilationCases.java**:

~~~text
javac -encoding UTF-8 CompilationCases.java
java CompilationCases
~~~

Trên JDK 17 hoặc mới hơn hỗ trợ **--release 17**, kết quả mong đợi (đã kiểm chứng trên JDK 21) là:

~~~text
valid-basic: PASS (compiled)
valid-generic: PASS (compiled)
invalid-syntax: PASS (rejected)
invalid-type: PASS (rejected)
invalid-access: PASS (rejected)
invalid-checked-exception: PASS (rejected)
invalid-generic: PASS (rejected)
~~~

**Giải thích cơ chế:**

1. **Source** là một **SimpleJavaFileObject** biểu diễn tệp nguồn trong bộ nhớ; đường dẫn ảo dạng **string:///InvalidType.java** phải khớp tên lớp **public** trong nguồn.
2. **getTask(...).call()** thực hiện đúng một lượt biên dịch; mỗi lượt có bộ quản lý tệp và thư mục đầu ra riêng để không lấy nhầm kết quả của ca khác.
3. **shouldCompile=true** yêu cầu tác vụ thành công. **shouldCompile=false** yêu cầu tác vụ thất bại **và** có ít nhất một **Diagnostic.Kind.ERROR**; lỗi nghiêm trọng ném exception khiến toàn bộ bộ chạy thất bại, không bị coi là ca từ chối hợp lệ.
4. Bốn ca âm về cú pháp, kiểu, quyền truy cập và checked exception cùng ca generic kiểm chứng các ràng buộc khác nhau. Bộ chạy kiểm tra kết quả biên dịch; để kiểm chứng chính xác *nguyên nhân* từ chối, bổ sung việc kiểm tra nhóm diagnostic như mục tiếp theo.
5. Khối **finally** dọn tất cả tệp được tạo tạm ngay cả khi một khẳng định thất bại.

## 6. Chẩn đoán nguyên nhân lỗi và tránh ca âm “đậu giả”

Một ca âm có thể bị từ chối vì **thiếu import**, **tên tệp/lớp sai**, **classpath thiếu**, **source encoding sai**, hoặc **cú pháp khác hỏng trước khi compiler đến được quy tắc cần thử**. Khi đó phép thử thoạt nhìn PASS nhưng chưa chứng minh được điều cần chứng minh.

Đối với kiểm thử cần độ tin cậy cao:

1. **Giữ một bản hợp lệ làm đối chứng.** Ví dụ chuyển riêng khai báo **int count = 5;** thành **int count = "five";**; mọi thành phần khác giữ nguyên.
2. **Xác nhận diagnostic là ERROR,** không phải chỉ warning hoặc note. Với **DiagnosticCollector**, lấy **Diagnostic.getKind()**, **getCode()**, **getSource()**, **getLineNumber()** và **getMessage(locale)** để phục vụ điều tra.
3. **Khớp nguyên nhân ở mức phù hợp.** Có thể phân loại bằng mã diagnostic của **javac** nếu đã ghim phiên bản compiler; đây là chi tiết triển khai của compiler, không phải API chẩn đoán ổn định cho mọi JDK/vendor. Với test chạy trên nhiều JDK, ưu tiên kiểm tra nhóm lỗi/kỳ vọng ngữ nghĩa và review phần thông báo thay vì so sánh nguyên văn toàn bộ tiếng Anh, dòng/cột hoặc thứ tự lỗi.
4. **Khác biệt giữa “source bị reject” và “hạ tầng test hỏng”.** Không coi **compiler==null**, I/O exception, sai tùy chọn, thư mục không tạo được hoặc tiến trình bị dừng là một negative pass. Các tình huống đó phải báo lỗi hạ tầng.
5. **Đối chiếu với target release.** Nguồn hợp lệ trên JDK 21 có thể không hợp lệ khi dùng **--release 17** nếu dùng cú pháp/API ra đời sau Java 17; đây là từ chối do target compatibility, phải ghi rõ trong ca chứ không gọi là lỗi cú pháp bất ngờ.

Ví dụ một mẫu kiểm tra *nhóm* chẩn đoán, bổ sung vào vòng lặp của bộ chạy (đoạn sau là trích đoạn, không phải chương trình Java độc lập):

~~~java
var errors = diagnostics.getDiagnostics().stream()
    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
    .toList();

for (var error : errors) {
    System.err.println(c.name() + ": " + error.getCode()
        + " at line " + error.getLineNumber()
        + " — " + error.getMessage(java.util.Locale.ROOT));
}
~~~

Đoạn này **in** chứng cứ để phân tích, chưa tự chứng minh chẩn đoán khớp quy tắc. Nếu yêu cầu hệ thống tự động xác nhận mã diagnostic, hãy khai báo các mã được chấp nhận **theo phiên bản javac được test**, và tạo ca đối chứng có thể làm phép kiểm tra mã diagnostic thất bại. Tránh thử một cụm từ thông báo thiếu đặc trưng như “error” vì nó không phân biệt nguyên nhân.

## 7. Tổ chức tập dữ liệu và kiểm thử hồi quy

Nếu chuyển ví dụ trên thành một bộ test lớn hơn, nên quản lý mỗi ca bằng manifest/metadata với **ID**, tệp nguồn, quy tắc, **ACCEPT/REJECT**, phiên bản Java, compiler options, kỳ vọng về chẩn đoán và một ca đối chứng. Những tệp Java *cố ý không hợp lệ* nên lưu dưới **resources/compile-fixtures**, ngoài mọi source set mà Gradle/Maven tự biên dịch. Test harness đọc chúng như dữ liệu, sau đó chủ động gọi compiler.

Một quy trình hồi quy thực tế:

1. **Khóa cấu hình môi trường:** ghi JDK vendor/version thực chạy; đặt **--release** để xác định mức ngôn ngữ và API đích, **-encoding UTF-8**, classpath/module path cần thiết, và chỉ bật annotation processor nếu đó là thứ đang được kiểm thử.
2. **Thiết kế ca đối chứng dương trước:** đảm bảo mã gốc được chấp nhận với đúng các tùy chọn đó; không phát triển ca âm bằng cách sửa một chương trình vốn đã có lỗi.
3. **Tạo một sai lệch có chủ đích:** ghi rõ ngữ nghĩa bị vi phạm và loại chẩn đoán mong đợi. Nếu bài toán yêu cầu nhiều quy tắc cùng lúc, tách thành nhiều ca.
4. **Chạy cô lập:** mỗi ca có bộ nguồn tối thiểu, cùng phụ thuộc đã khai báo, thư mục đầu ra sạch và timeout thích hợp nếu chạy compiler qua tiến trình ngoài.
5. **Đánh giá cả hai chiều:** dương bắt buộc thành công, âm bắt buộc thất bại đúng nguyên nhân; kết quả khó hiểu hoặc lỗi hạ tầng phải báo riêng, không nuốt ngoại lệ.
6. **Lưu chứng cứ hữu ích:** ca ID, phiên bản compiler, tùy chọn, trạng thái, loại/mã diagnostic và nguồn liên quan; khi thay JDK, xem lại các chẩn đoán trước khi cập nhật kỳ vọng.
7. **Tự kiểm tra hiệu lực của harness:** cố tình đổi một ca âm thành mã hợp lệ; bộ test **phải fail**. Đổi một ca dương thành mã sai; bộ test **cũng phải fail**. Đây là kiểm tra xem oracle có thực sự phát hiện kết quả sai.

Không nên ghi cố định toàn bộ log của **javac** làm “snapshot” bắt buộc khi không cần thiết: đường dẫn tệp tạm, số dòng, ngôn ngữ bản địa và cách diễn đạt chẩn đoán dễ thay đổi mà quy tắc Java vẫn giữ nguyên.

## 8. Những lỗi thiết kế phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra ca hợp lệ | Không phát hiện compiler/chính sách cho phép mã cần bị cấm | Thêm cặp ca âm với khác biệt tối thiểu |
| Ca âm hỏng vì nhiều lỗi không liên quan | Test “pass” sai mục tiêu | Bắt đầu từ bản hợp lệ, thay một yếu tố, kiểm tra nhóm ERROR |
| Dùng kết quả chạy **java** để đánh giá kiểm tra biên dịch | Trộn lỗi runtime với compile-time | Xác định pass/fail tại bước compiler |
| Đặt fixture lỗi dưới source set mặc định | Cả dự án không biên dịch được, test không kịp chạy | Lưu fixture như dữ liệu và nạp bằng harness |
| Tái sử dụng output/classpath không kiểm soát | Dễ dùng nhầm tệp cũ hoặc phụ thuộc ngoài | Thư mục output mới, classpath khai báo rõ |
| Coi mọi mã trả về khác 0 là “reject hợp lệ” | Compiler crash, I/O, tùy chọn sai cũng được tính pass | Tách lỗi hạ tầng và xác nhận có ERROR về nguồn |
| So khớp thông báo lỗi nguyên văn | Test mỏng manh trước JDK/locale | Dùng diagnostic kind, mã gắn với compiler hoặc phân loại ngữ nghĩa |
| Quên tên tệp phải khớp lớp **public** | Reject do tên sai thay vì quy tắc đích | Kiểm tra đường dẫn fixture và tên lớp trước |
| Mong tất cả ca âm đều không sinh **.class** | Báo sai cho biên dịch nhiều nguồn | Đánh giá trạng thái compilation và diagnostic; luôn dùng output sạch |

## 9. Bài thực hành và tiêu chí hoàn thành

**Bài tập:** thêm hai cặp ca vào bộ kiểm thử:

- **Tên không tồn tại:** từ một khai báo dùng lớp hợp lệ, chỉ đổi tên kiểu sang một tên không định nghĩa. Ca dương phải được chấp nhận; ca âm phải có lỗi không tìm thấy ký hiệu tương ứng.
- **Checked exception:** từ một phương thức gọi **risky() throws IOException** có **throws IOException** hoặc **try/catch** đúng, bỏ riêng phần xử lý/khai báo ngoại lệ. Ca dương được chấp nhận; ca âm bị từ chối vì exception chưa được xử lý/khai báo.

**Chấp nhận kết quả khi:** (1) mỗi ca ghi rõ kỳ vọng ACCEPT hoặc REJECT và nguyên nhân; (2) các ca dương đều biên dịch thành công; (3) các ca âm đều bị từ chối bởi quy tắc dự kiến, có chẩn đoán ERROR; (4) khi đảo chiều kỳ vọng hoặc sửa ca âm thành mã hợp lệ thì harness báo fail; (5) chạy lại từ thư mục output sạch cho cùng kết quả; (6) toàn bộ nội dung được thực hiện với mức Java được khai báo rõ.

Một bộ kiểm thử biên dịch tốt chứng minh được **ranh giới** của quy tắc: ví dụ gần nhất còn hợp lệ **được chấp nhận**, và ví dụ chỉ vượt qua ranh giới đó **bị từ chối vì đúng lý do**.