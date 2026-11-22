# Điều chỉnh độ chi tiết chẩn đoán của javac mà không phụ thuộc định dạng thông báo cố định

Khi Java không biên dịch được, `javac` phát ra **diagnostic**: thông tin về lỗi, cảnh báo hoặc ghi chú trong quá trình phân tích và biên dịch chương trình. Người học thường chỉ nhìn dòng chữ `error:` hoặc `warning:` trên terminal, nhưng với hệ thống build, IDE hoặc CI, cần phân biệt **nội dung dành cho con người đọc** với **tín hiệu có thể xử lý ổn định bằng chương trình**.

`javac` cho phép thay đổi mức độ chi tiết của các thông báo bằng nhiều tùy chọn: `-Xdiags:compact`, `-Xdiags:verbose`, `-Xlint`, `-Xmaxerrs`, `-Xmaxwarns`, `-verbose` và `-Werror`. Chúng phục vụ các mục đích khác nhau; một số tác động tới lượng cảnh báo được sinh ra, số thông báo hiển thị hoặc chính sách build thất bại. Không tùy chọn nào biến toàn bộ văn bản diagnostic thành một định dạng máy đọc ổn định giữa mọi JDK, locale và compiler implementation.

Bài này trình bày cách dùng các tùy chọn để debug và cách xây công cụ **không kiểm tra lỗi bằng regex trên stderr**. Ví dụ dùng Java 17+, áp dụng trực tiếp cho JDK 21. Khi tích hợp programmatic compiler, ta tận dụng `javax.tools.JavaCompiler` và `DiagnosticCollector` thay vì cố đoán cấu trúc từng dòng chữ.

## 1. Diagnostic là gì?

Một diagnostic có thể mô tả:

- **Lỗi biên dịch** (*error*): chương trình không thỏa quy tắc Java, chẳng hạn biến không tồn tại, sai kiểu hoặc sai cú pháp.
- **Cảnh báo** (*warning*): compiler vẫn có thể sinh class file, nhưng phát hiện vấn đề đáng chú ý như raw type, unchecked conversion hay dùng API deprecated.
- **Ghi chú** (*note*): thông tin bổ sung từ compiler hoặc annotation processor.
- **Vị trí liên quan**: tên source, dòng, cột hoặc offset, nếu diagnostic có vị trí xác định được.
- **Nội dung diễn giải**: lời giải thích cho người đọc, có thể thay đổi theo locale, lựa chọn verbose/compact, phiên bản JDK và loại compiler.

Ví dụ, Java sau cố ý sai kiểu:

```java
class BadAssignment {
    int count = "ten";
}
```

`javac` thường báo một lỗi không thể chuyển `String` sang `int`. Thông báo có thể bao gồm đường dẫn file, số dòng, vị trí mũi tên, giải thích `incompatible types` và số lỗi. Những yếu tố này **không nên bị coi là giao thức ổn định** cho ứng dụng tự động.

Một công cụ có thể cần biết “biên dịch thành công hay không”, “có bao nhiêu diagnostic loại ERROR”, “diagnostic thuộc source nào” và “line/column là bao nhiêu”. Các thông tin ấy có cách lấy phù hợp qua API, không cần cắt chuỗi stderr dựa trên một mẫu cố định.

## 2. Phân biệt thay đổi độ chi tiết và thay đổi chính sách

Tùy chọn `javac` phục vụ các mục đích không giống nhau:

| Tùy chọn | Tác động chính | Điều không nên suy ra |
| --- | --- | --- |
| `-Xdiags:compact` | Chọn chế độ trình bày diagnostic ngắn gọn | Không làm chương trình hợp lệ hơn hoặc đảm bảo định dạng output cố định |
| `-Xdiags:verbose` | Chọn chế độ diagnostic chi tiết hơn | Không biến text thông báo thành schema/API |
| `-Xlint`, `-Xlint:<keys>` | Bật các nhóm cảnh báo lint | Không đồng nghĩa in thêm mọi chi tiết của một lỗi đã có |
| `-Xmaxerrs N` | Giới hạn số **lỗi được in** | Không cho biết tổng số lỗi của mã nguồn bằng cách đếm dòng đã in |
| `-Xmaxwarns N` | Giới hạn số **cảnh báo được in** | Không bảo đảm không còn cảnh báo khác |
| `-verbose` | In hoạt động của compiler, như các class được tải và source được biên dịch | Không phải dạng verbose riêng của diagnostic |
| `-Werror` | Khi có cảnh báo, compilation thất bại theo chính sách này | Không làm cảnh báo tự biến thành một source error cụ thể |
| `-nowarn` / `-Xlint:none` | Tắt thông báo cảnh báo tương ứng | Không sửa mã không an toàn và không tắt lỗi thực |
| `-deprecation` | Yêu cầu diagnostic chi tiết hơn về các cách dùng API deprecated theo cơ chế javac | Không thay thế `-Xlint` cho những nhóm cảnh báo khác |

Các cờ bắt đầu bằng `-X` là **tùy chọn mở rộng của `javac`**. Hãy kiểm tra phiên bản compiler bằng `javac -version` và danh sách cờ bằng `javac -X` hoặc tài liệu JDK tương ứng. Tùy chọn, danh sách lint key và mức độ trình bày có thể thay đổi theo phiên bản.

**Phân biệt kết quả build với văn bản diagnostic:** một compilation hợp lệ về kiểu có thể thất bại khi dùng `-Werror` nếu có cảnh báo; ngược lại, giảm lượng cảnh báo hiển thị không làm một lỗi kiểu biến mất. Nếu cần CI ổn định, dùng **trạng thái thành công/thất bại**, chính sách warning rõ ràng và dữ liệu diagnostic có cấu trúc.

## 3. Điều chỉnh cách hiển thị với -Xdiags

Hai giá trị được hỗ trợ trong tài liệu `javac` JDK 21 là:

```bash
javac -Xdiags:compact BadAssignment.java
javac -Xdiags:verbose BadAssignment.java
```

Cả hai lời gọi cố ý thất bại vì `BadAssignment.java` gán `String` vào `int`. Chúng khác ở **mức độ chi tiết thông tin lỗi** được trình bày; không đổi quy tắc Java, source input hoặc tên class được biên dịch.

Khi điều tra lỗi:

1. Bắt đầu với cách trình bày thông thường/compact để dễ đọc.
2. Nếu compiler báo lỗi inference, overload, conversion hoặc generic bounds khó hiểu, thử `-Xdiags:verbose` để có thêm bối cảnh.
3. Đọc đầy đủ lý do lỗi và vị trí trên source, thay vì chỉ copy dòng đầu ra.
4. Ghi lại JDK/toolchain thực tế vì diagnostic thay đổi khi compiler thay đổi.

Không viết chương trình:

```text
if (stderr.includes("incompatible types: String cannot be converted to int")) {
    // Gắn nhãn lỗi loại X...
}
```

Đây là **mã giả minh họa cách làm dễ vỡ**, không phải Java runnable. Chữ trong thông báo có thể khác do verbose/compact, locale, phiên bản JDK, kiểu biểu thức, ràng buộc inference hoặc vị trí lỗi.

Nếu công cụ cần nhận biết nguồn lỗi theo taxonomy riêng, nó phải dùng API structured diagnostic và ánh xạ những loại/thuộc tính đã định nghĩa rõ, kèm khả năng xử lý trường hợp chưa biết.

## 4. Tăng cảnh báo hữu ích bằng -Xlint

`-Xlint` bật các cảnh báo được compiler khuyến nghị. Khi muốn tập trung vào một nhóm, dùng danh sách lint key:

```bash
javac -Xlint:rawtypes,unchecked RawTypeWarning.java
```

Ví dụ file `RawTypeWarning.java` hoàn chỉnh:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeWarning {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("Java");
        System.out.println(raw.size());
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked RawTypeWarning.java
java RawTypeWarning
```

Stdout chương trình chạy:

```text
1
```

Phần cảnh báo biên dịch xuất hiện riêng khi chạy `javac`, thông thường trên stderr; **không cố định nguyên văn cảnh báo, số dòng gạch chân hay thứ tự diagnostic**. `rawtypes` liên quan việc dùng `List` và `ArrayList` thiếu type argument; `unchecked` có thể báo thao tác `add` qua raw reference. Code có thể biên dịch và chạy, nhưng compiler không đảm bảo kiểu phần tử như khi dùng `List<String>`.

Sửa thiết kế bằng generics:

```java
List<String> words = new ArrayList<>();
words.add("Java");
System.out.println(words.size());
```

Đoạn này là snippet **nằm trong phương thức có import `java.util.List` và `java.util.ArrayList`**, không phải một file độc lập. Nếu thay logic của `main` trong `RawTypeWarning.java` bằng đoạn này thì stdout vẫn là `1` và những cảnh báo rawtypes/unchecked của ví dụ không còn.

Có thể dùng:

```bash
javac -Xlint:all RawTypeWarning.java
javac -Xlint:all,-rawtypes RawTypeWarning.java
javac -Xlint:none RawTypeWarning.java
```

Chế độ `all` bật những nhóm cảnh báo lint được compiler hỗ trợ; ký hiệu `-rawtypes` sau dấu phẩy là **loại riêng nhóm rawtypes khỏi lựa chọn all**. `none` tắt nhóm lint. Cụ thể lint keys nào tồn tại cần được kiểm tra theo bản JDK; `-Xlint:all` không hứa phát hiện mọi lỗi nghiệp vụ.

Có thể bỏ qua đúng một cảnh báo ở vị trí xác định bằng `@SuppressWarnings` khi có lý do kỹ thuật và biết chính xác lint key mà compiler hỗ trợ. Không nên đặt `@SuppressWarnings("all")` lên cả hệ thống chỉ để đạt CI xanh.

## 5. -Werror: cảnh báo trở thành điều kiện khiến build thất bại

Trong môi trường CI, đôi khi nhóm phát triển muốn **không cho phép cảnh báo compiler xuất hiện**. Dùng:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked -Werror RawTypeWarning.java
```

Với source còn sử dụng raw types như mục 4, compiler có cảnh báo; `-Werror` làm toàn bộ compilation thất bại. Cách diễn đạt diagnostic tùy JDK, nhưng hệ thống build nên dựa trên **exit status khác 0** hoặc `CompilationTask.call() == false` khi gọi API.

Sửa code để loại cảnh báo hoặc điều chỉnh chính sách lint có chủ đích; `-Werror` không tự chuyển phép gọi raw thành type-safe. Ngược lại, `-nowarn` không phải giải pháp thay thế việc sửa code nếu cảnh báo chỉ ra rủi ro runtime.

Một lưu ý thực tế: khi nâng JDK, tập cảnh báo hỗ trợ có thể thay đổi. Nếu dự án dùng `-Werror`, cần kiểm tra cả toolchain và lint policy trên CI. Hãy lưu compiler version và các compiler arguments để truy nguyên thay đổi trong điều kiện build thành công.

## 6. -Xmaxerrs và -Xmaxwarns: giới hạn lượng chữ in ra

Một source có nhiều lỗi có thể tạo log lớn. Trong tình huống muốn xem nhanh, có thể dùng:

```bash
javac -Xmaxerrs 3 BadAssignment.java
javac -Xmaxwarns 5 -Xlint:all RawTypeWarning.java
```

**Cảnh báo:** `-Xmaxerrs` và `-Xmaxwarns` giới hạn số thông báo **được in** theo tài liệu JDK; chúng không tạo báo cáo chuẩn rằng chương trình chỉ có đúng N lỗi/cảnh báo. Khi giới hạn bị chạm, còn diagnostic khác có thể chưa được in đầy đủ.

Vì vậy, không được dùng thuật toán “đếm số dòng chứa `error:` trong stderr” làm số lỗi chuẩn của một repo. Bộ đếm này có thể chịu ảnh hưởng của số lượng in tối đa, nội dung các diagnostic nhiều dòng, phần tóm tắt, các tool/plugin và cách compiler định dạng output.

Mẹo vận hành: log CI hằng ngày có thể chọn mức vừa phải để dễ đọc; khi có lỗi khó tái hiện, chạy lại một lần trong môi trường chẩn đoán với giới hạn lớn hơn. Tuy nhiên, **trạng thái build** và các quyết định kiểm thử tự động vẫn cần dựa trên tín hiệu thực, không dựa trên số dòng in.

## 7. -verbose là hoạt động compiler, không phải -Xdiags:verbose

Hai lệnh dưới đây khác mục đích:

```bash
javac -verbose RawTypeWarning.java
javac -Xdiags:verbose RawTypeWarning.java
```

`-verbose` in hoạt động như việc parse file, load class, compile/write output theo cơ chế compiler. Nó hữu ích khi cần hiểu **compiler đã đọc source hoặc class nào** và giúp chẩn đoán khác biệt ở classpath/sourcepath.

`-Xdiags:verbose` yêu cầu chi tiết hơn cho **lời giải thích diagnostic**; khi không có lỗi/cảnh báo, khác biệt có thể ít hoặc không đáng kể.

Không nên bật `-verbose` mặc định trên dự án lớn chỉ để “ghi nhiều lỗi hơn” vì lượng log rất lớn và thường không trả lời câu hỏi về loại lỗi. Khi đang tra cứu một dependency thiếu, `-verbose` có thể hữu ích; khi đang xử lý generic inference, `-Xdiags:verbose` thường là hướng thích hợp hơn.

## 8. Vì sao không được phụ thuộc định dạng diagnostic cố định?

Có ít nhất sáu nguyên nhân:

1. **JDK/toolchain:** phiên bản `javac` khác có thể cải thiện thông báo, đổi thứ tự lý do hoặc bổ sung gợi ý.
2. **Locale:** cùng lỗi có thể được biểu diễn bằng các thông điệp đã localize khác nhau, tùy bản phân phối và cấu hình compiler.
3. **Chế độ trình bày:** compact/verbose và các tùy chọn liên quan thay đổi cách giải thích.
4. **Vị trí và đường dẫn:** đường dẫn tương đối/tuyệt đối, dấu phân cách file, tab/newline/Unicode trong source làm chuỗi hiển thị khác nhau.
5. **Diagnostic nhiều dòng:** vị trí mũi tên, bản trích source, loại lỗi generic và phần tóm tắt có thể trải trên nhiều dòng.
6. **Implementation:** công cụ `javac`, ECJ hoặc một compiler khác không phải lúc nào cũng chia sẻ cùng định dạng/cụm từ.

Ví dụ regex dễ hỏng:

```text
^(.+\.java):(\d+): error: (.*)$
```

Đây là biểu thức quy tắc minh họa **cách parse không đáng tin**, không phải grammar chính thức của mọi diagnostic Java. Với lời nhắn nhiều dòng, tên file chứa dấu hai chấm (Windows), locale khác hoặc chế độ diagnostic khác, nó có thể mất thông tin hoặc diễn giải sai.

Khi cần dữ liệu có cấu trúc, dùng `javax.tools.Diagnostic`; nếu chỉ chạy lệnh `javac` từ shell, lấy **exit code** để biết thành công/thất bại và lưu toàn bộ log làm dữ liệu phục vụ con người, không đặt nghiệp vụ lên từng câu chữ.

## 9. Java Compiler API và DiagnosticCollector

Module chuẩn `java.compiler` cung cấp API dùng compiler trong tiến trình Java:

- `javax.tools.ToolProvider.getSystemJavaCompiler()` lấy system compiler nếu môi trường có JDK compiler thích hợp.
- `JavaCompiler.getTask(...)` tạo một compilation task với options, source files và diagnostic listener.
- `DiagnosticCollector<JavaFileObject>` thu thập `Diagnostic` để duyệt dưới dạng đối tượng.
- `Diagnostic.Kind` là enum như `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
- `Diagnostic.getSource()`, `getLineNumber()`, `getColumnNumber()`, `getPosition()` cung cấp vị trí nếu có.
- `Diagnostic.getMessage(Locale)` trả văn bản để hiển thị; văn bản vẫn implementation-dependent.
- `Diagnostic.getCode()` trả mã diagnostic, có thể là `null`; **mã này không được JDK cam kết ổn định giữa các compiler/phiên bản**.

Đây là khác biệt cốt lõi giữa dùng một giao diện lập trình và parse log.

### Ví dụ Java 17+ độc lập: thu thập lỗi có cấu trúc

Lưu nguyên file `StructuredDiagnosticDemo.java`:

```java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class StructuredDiagnosticDemo {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        JavaFileObject source = new SimpleJavaFileObject(
                URI.create("string:///BadSource.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return "class BadSource { int count = \"ten\"; }\n";
            }
        };

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        JavaCompiler.CompilationTask task = compiler.getTask(
                null,
                null,
                collector,
                List.of("-proc:none", "-Xdiags:verbose"),
                null,
                List.of(source)
        );

        boolean success = Boolean.TRUE.equals(task.call());
        boolean hasError = collector.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        System.out.println("success=" + success);
        System.out.println("hasError=" + hasError);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StructuredDiagnosticDemo.java
java StructuredDiagnosticDemo
```

Stdout chính xác trên compiler tuân thủ Java:

```text
success=false
hasError=true
```

Chương trình tạo một file nguồn **trong bộ nhớ** có lỗi gán `String` cho `int`. `JavaCompiler` phát hiện lỗi, `task.call()` trả `false` và `DiagnosticCollector` chứa ít nhất một diagnostic kind `ERROR`. Ta chỉ in **tín hiệu có ngữ nghĩa ổn định**; không so sánh từng chữ của lỗi.

`-proc:none` được dùng để tránh việc thực thi annotation processor tình cờ trong demo; nó không thay đổi nguyên nhân lỗi kiểu. `-Xdiags:verbose` được truyền như option để thấy rằng lựa chọn cách hiển thị không buộc chương trình phải parse stderr. Trên môi trường chỉ có runtime không cung cấp compiler, `getSystemJavaCompiler()` có thể trả `null`; cần chạy bằng JDK thích hợp.

Mặc dù source được giữ trong bộ nhớ, compiler có thể tạo file đầu ra nếu một compilation thành công và không chỉ định file manager/destination; ở demo này nguồn sai kiểu nên không có class output cho `BadSource`. Khi xây công cụ thật, hãy dùng file manager/output location được thiết lập rõ ràng.

## 10. Sử dụng Diagnostic mà không biến message thành khóa nghiệp vụ

Trong code xử lý `Diagnostic<? extends JavaFileObject> diagnostic` có thể truy xuất các trường:

```java
Diagnostic.Kind kind = diagnostic.getKind();
long line = diagnostic.getLineNumber();
long column = diagnostic.getColumnNumber();

if (line != Diagnostic.NOPOS && column != Diagnostic.NOPOS) {
    // Có vị trí dòng/cột; có thể liên kết tới editor.
}

String displayMessage = diagnostic.getMessage(java.util.Locale.ROOT);
String compilerSpecificCode = diagnostic.getCode();
```

Đây là **snippet trong phương thức nhận biến `diagnostic`**, không phải file runnable độc lập.

Cần tuân thủ những ranh giới API:

| Trường | Có thể sử dụng | Lưu ý |
| --- | --- | --- |
| `getKind()` | Phân loại error/warning/note | Đây là enum API; phù hợp để đếm và lọc |
| `getSource()` | Gắn diagnostic với file nguồn | Có thể trả `null` |
| `getLineNumber()`, `getColumnNumber()` | Hiển thị vị trí trong editor | Đánh số từ **1**, có thể là `Diagnostic.NOPOS` |
| `getPosition()` | Offset ký tự trong source | Offset từ **0**, có thể là `NOPOS` |
| `getStartPosition()`, `getEndPosition()` | Mô tả vùng liên quan | Có thể không biết vị trí; kiểm tra `NOPOS` |
| `getCode()` | Hiển thị/ghi log mã compiler | Mã implementation-dependent, có thể `null` |
| `getMessage(Locale)` | Hiển thị văn bản cho người đọc | Văn bản implementation-dependent; không dùng làm protocol |

Ngay cả khi API trả một mã `compiler.err.*` từ `javac`, mã đó vẫn thuộc implementation; đừng tuyên bố nó là danh mục lỗi chuẩn ổn định của Java SE. Nếu sản phẩm muốn có error taxonomy ổn định, hãy tự định nghĩa taxonomy của mình, công khai phạm vi hỗ trợ và có nhánh fallback cho diagnostic chưa được ánh xạ.

Ví dụ report machine-readable có thể có các trường do **ứng dụng** đặt ra: `severity`, `sourceUri`, `line`, `column`, `messageForDisplay`, `compilerId`, `toolchainVersion`. Chỉ `severity` và vị trí theo API được lấy làm cơ sở tổng quát; `messageForDisplay` là chuỗi để người đọc, không làm khóa quyết định.

## 11. Kiểm thử compiler theo hành vi thay vì snapshot stderr

Một bài kiểm thử compiler tốt nên tách:

**Tín hiệu hợp lệ tương đối bền:** code biên dịch thành công hay thất bại, có error hay không, có cảnh báo kiểu `WARNING`/`MANDATORY_WARNING` không, compiler có sinh artifact mong đợi hay không, API semantics của ví dụ có đúng không.

**Tín hiệu phù hợp làm thông tin bổ sung:** source/line/column nếu bài toán thực sự quan tâm tới vị trí, code diagnostic mang tính compiler-specific, thông điệp giải thích đầy đủ.

**Tín hiệu dễ vỡ nếu kiểm thử exact:** toàn bộ stderr, số khoảng trắng, chữ “error”, bản trích một dòng source, số dấu mũ `^`, câu diễn giải tiếng Anh, thứ tự diagnostic, path đầy đủ, tiền tố note hoặc số lỗi tóm tắt.

Ví dụ, với `StructuredDiagnosticDemo`, kiểm thử nên kỳ vọng hai dòng `success=false` và `hasError=true`. Nếu sau đó ứng dụng in một `getMessage(Locale.ENGLISH)`, không nên ghi nguyên thông điệp ấy thành snapshot bắt buộc trên mọi JDK.

Trường hợp cần kiểm tra một diagnostic cụ thể ở một phiên bản compiler cụ thể (ví dụ một plugin chỉ hỗ trợ JDK 21.0.x), có thể có kiểm thử integration chuyên biệt để phát hiện regression của plugin. Khi ấy phải **cố định toolchain và nói rõ đó là kiểm thử implementation-specific**, không quảng bá format thành tiêu chuẩn Java nói chung.

## 12. Khi dùng CLI, hãy đọc exit code đúng cách

Với shell, `javac` hoàn tất thành công thường trả mã thoát `0`. Khi có lỗi biên dịch hoặc `-Werror` làm build thất bại, mã thoát khác `0`. Sử dụng trạng thái tiến trình thay vì kiểm tra chuỗi:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked -Werror RawTypeWarning.java
if [ $? -ne 0 ]; then
    echo "Compilation failed"
fi
```

Đoạn trên dành cho **Bash**. Trong shell khác, cú pháp lấy exit code khác nhau; PowerShell có `$LASTEXITCODE` cho tiến trình native. Lưu ý trên Bash thật, `$?` phải được đọc **ngay sau lệnh `javac`** trước khi có lệnh khác thay đổi trạng thái.

Với Gradle/Maven, nên dựa vào kết quả task/build (success/failure) do công cụ cung cấp; không nên grep log compiler để tự “xác định build xanh”. Các plugin có thể gom/định dạng lại diagnostic hoặc chạy incremental compilation, làm việc parse text càng kém ổn định.

## 13. Khi nào tăng log, khi nào giảm log?

| Mục tiêu | Cách tiếp cận nên dùng |
| --- | --- |
| Lỗi generics/overload khó hiểu | Thử `-Xdiags:verbose` và thu nhỏ ví dụ |
| Muốn tìm source/class compiler đã đọc | Dùng `-verbose` cho lượt chẩn đoán cụ thể |
| Muốn phát hiện code dễ gây runtime type error | `-Xlint:unchecked,rawtypes`, sau đó sửa code |
| Muốn xử lý deprecated API | `-Xlint:deprecation` hoặc `-deprecation` |
| CI muốn không chấp nhận cảnh báo | Bật lint policy phù hợp và `-Werror` |
| Terminal in quá nhiều lỗi | `-Xmaxerrs` để hạn chế phần in, nhưng không dùng số dòng làm tổng lỗi |
| IDE muốn tô đỏ đoạn source | `Diagnostic` cùng source/line/column/position qua API |
| Báo cáo cho con người | Ghi message có ngữ cảnh, compiler version, options, file và vị trí |
| Báo cáo tự động | Dùng kind/status/schema do ứng dụng định nghĩa; message chỉ mang tính giải thích |

Mức độ chi tiết phù hợp phụ thuộc người nhận. Người lập trình sửa lỗi cần **lý do đủ sâu**; CI cần kết quả **dễ phân loại và theo dõi**; dashboard cần dữ liệu **có cấu trúc và có giới hạn tính ổn định**. Không một chế độ verbose nào thay thế được thiết kế giao diện dữ liệu rõ ràng.

## 14. Các tình huống dễ gây hiểu lầm

### Một: “Thêm -Xdiags:verbose làm xuất hiện lỗi mới”

Chế độ verbose có thể làm một diagnostic hiện rõ các ràng buộc, candidate method, kiểu yêu cầu/kiểu có thực. Điều đó **không nhất thiết** chứng minh compiler có thêm lỗi ngữ nghĩa mới. So sánh status, vị trí và bản chất chương trình; đừng đồng nhất số dòng log với số diagnostic.

### Hai: “-Xmaxerrs 1 nghĩa là source chỉ có một lỗi”

Không đúng. Đây là giới hạn số lỗi **in ra**. Sửa lỗi đầu tiên có thể làm lộ lỗi tiếp theo. Dùng nó để quản lý kích thước log, không làm thống kê chất lượng tổng quát.

### Ba: “Không còn warning thì code an toàn tuyệt đối”

Không đúng. Tắt warning hoặc thay đổi lint policy chỉ ảnh hưởng khả năng quan sát một số vấn đề compile time. Compiler không chứng minh tất cả logic nghiệp vụ, concurrency, null safety hoặc data validation đều đúng.

### Bốn: “Diagnostic code là mã chuẩn Java SE”

`Diagnostic.getCode()` được Java SE định nghĩa là phương thức API, nhưng giá trị code **implementation-dependent và có thể null**. Đừng viết logic portable bắt buộc một code nội bộ cụ thể của `javac`.

### Năm: “Có số dòng/cột cho mọi diagnostic”

API cho phép `NOPOS`, và `getSource()` có thể `null`. Ví dụ lỗi cấu hình compiler, option hoặc một vấn đề không gắn với một vị trí source cụ thể có thể không có tọa độ nguồn phù hợp. Công cụ nên hiển thị “không xác định” thay vì giả làm dòng `0`.

### Sáu: “-verbose và -Xdiags:verbose tương đương”

Không đúng: `-verbose` mô tả hoạt động compiler; `-Xdiags:verbose` điều chỉnh cách compiler giải thích diagnostic. Chúng phục vụ hai câu hỏi debug khác nhau.

### Bảy: “Một regexp stderr chạy trên JDK 17 sẽ ổn trên mọi phiên bản”

Không thể bảo đảm. Thông báo, ngôn ngữ, đường dẫn, số cột, dạng multiline và compiler implementation đều có thể đổi. Dùng API nếu cần dữ liệu có cấu trúc hoặc kiểm tra exit status nếu chỉ cần pass/fail.

## 15. Hướng dẫn xây báo cáo chẩn đoán cho một dự án thật

Một quy trình triển khai thực tế:

1. **Chốt toolchain**: nêu JDK version/vendor, `--release`, classpath/module path, compiler flags và các plugin/processor có liên quan.
2. **Chọn lint policy**: xác định loại cảnh báo nào nên bật ở local/CI, có dùng `-Werror` hay không.
3. **Đặt mức in hợp lý**: compact bình thường; verbose khi phân tích ca khó; `-Xmaxerrs`/`-Xmaxwarns` chỉ nhằm quản lý log.
4. **Lấy trạng thái kết quả rõ ràng**: process exit code hoặc `CompilationTask.call()`.
5. **Nếu tích hợp compiler**, dùng `DiagnosticCollector`; lưu các trường kind, source và tọa độ khi có, message để người đọc.
6. **Không khóa logic vào message/code nội bộ**: nếu cần phân loại sâu, công khai compiler-specific adapters kèm fallback và kiểm thử theo đúng toolchain.
7. **Lưu log đầy đủ khi cần**: dành cho debugging, không giả định đó là dữ liệu cấu trúc portable.
8. **Kiểm thử trên một ca lỗi đã biết**: tạo nguồn thiếu symbol hoặc sai kiểu rồi kiểm tra pass/fail và kind; không so từng dấu cách của stderr.
9. **Giữ tác động của annotation processing tách bạch**: processor có thể phát thêm warning/note; kết quả CI và thứ tự log cần tính tới processor được cấu hình.
10. **Đọc lại khi nâng JDK**: tên lint key, diagnostic text và warning behavior có thể thay đổi; cập nhật chính sách dựa trên JDK thật đang chạy.

Nếu muốn tạo UI đẹp cho diagnostic, formatter của **ứng dụng** nên chịu trách nhiệm trình bày dựa trên object đã phân tích, chẳng hạn “Lỗi — BadSource.java — dòng 1”, rồi in message bên dưới. Khi thay đổi UI, dữ liệu lõi vẫn có thể giữ các field có nghĩa và không cần sửa regex phụ thuộc compiler output.

## 16. Bài tập thực hành và đáp án

**Bài 1.** Chạy `javac -Xdiags:compact BadAssignment.java` và `javac -Xdiags:verbose BadAssignment.java`. Cả hai có hợp lệ không? **Không**; lỗi gán String vào int vẫn tồn tại. Thứ thay đổi là phần trình bày chi tiết.

**Bài 2.** Với `RawTypeWarning.java`, bật `-Xlint:rawtypes,unchecked`. Code có thể chạy không? **Có thể**, và ví dụ in `1`. Cảnh báo cho thấy generic type safety bị suy yếu, dù chương trình cụ thể không ném lỗi khi chạy.

**Bài 3.** Thêm `-Werror` vào lệnh biên dịch có cảnh báo. Có cần đoán dòng stderr chứa từ “error” để biết thất bại? **Không**. Kiểm tra mã thoát hoặc kết quả compilation task.

**Bài 4.** `-Xmaxerrs 2` làm terminal in hai lỗi. Có thể kết luận cả chương trình chỉ có hai lỗi không? **Không**. Nó giới hạn số lỗi được in; nguồn có thể có lỗi khác.

**Bài 5.** Trong `Diagnostic`, cách nào portable hơn để biết diagnostic là lỗi: `getKind() == ERROR` hay `getMessage(Locale.US).contains("error")`? **`getKind()`**, vì nó là enum của API.

**Bài 6.** Diagnostic không gắn với một file. `getSource()` và `getLineNumber()` phải được xử lý thế nào? **Cho phép null và `NOPOS`**, không giả mạo đường dẫn hay số dòng bằng chuỗi mặc định.

**Bài 7.** Vì sao không dùng `getCode()` làm danh mục lỗi chuẩn giữa JDK và ECJ? Vì code implementation-dependent và có thể null; chỉ dùng theo contract riêng nếu đã khóa compiler/toolchain và có fallback.

**Bài 8.** Khi điều tra compiler đang nạp những class nào, chọn `-verbose` hay `-Xdiags:verbose`? **`-verbose`** giúp quan sát hoạt động nạp/compile; `-Xdiags:verbose` giúp thấy diễn giải diagnostic chi tiết hơn.

## 17. Kết luận và tài liệu chính thức

Độ chi tiết chẩn đoán và tính ổn định của giao diện dữ liệu là hai bài toán riêng. Dùng `-Xdiags:verbose` để đọc lý do lỗi, `-Xlint` để chọn cảnh báo, `-Xmaxerrs`/`-Xmaxwarns` để khống chế lượng log, `-verbose` để quan sát compiler, `-Werror` để đặt chính sách. Với automation, hãy sử dụng **kết quả compile** và **Diagnostic API** theo ngữ nghĩa, không phụ thuộc một chuỗi lỗi được format theo cách nhất định.

Tài liệu để kiểm tra chính xác theo JDK:

- [JDK 21 javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — liệt kê `-Xdiags`, `-Xlint`, `-Werror`, `-Xmaxerrs` và `-Xmaxwarns`.
- [Java SE 21 Diagnostic API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html) — mô tả `Kind`, `NOPOS`, vị trí, code và message implementation-dependent.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — thu thập diagnostic qua listener.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — giao diện `CompilationTask` và lập trình với compiler.
