# Áp dụng `javac -Werror` và xây dựng chính sách cảnh báo phù hợp

## 1. Vì sao cảnh báo cần một chính sách?

`javac` phát **error** khi chương trình không thể biên dịch hợp lệ và có thể phát **warning** khi mã vẫn biên dịch được nhưng tiềm ẩn rủi ro, dùng API cũ, thao tác kiểu không an toàn, cấu hình compiler đáng ngờ hoặc có cấu trúc cần xem xét. Ví dụ: dùng raw generic type, unchecked conversion, API bị đánh dấu deprecated, API sắp bị loại bỏ và switch vô tình fall through.

Nếu chỉ xem warning là dòng log, một codebase lớn dễ tích lũy hàng nghìn cảnh báo. Khi đó nhóm phát triển không phân biệt được cảnh báo mới đáng chú ý với cảnh báo cũ. `-Werror` cho phép biến **warning do compiler phát ra thành lỗi biên dịch**, từ đó đưa chính sách chất lượng vào build và CI.

Tuy nhiên, `-Werror` tự nó không quyết định warning nào nên được phát. Nó phối hợp với `-Xlint` và các lựa chọn compiler khác. Một chính sách bền vững cần trả lời:

1. Nhóm warning nào cần bật, nhóm nào cần xử lý ngay?
2. Module hoặc source set nào nằm trong phạm vi áp dụng?
3. Làm gì với cảnh báo cũ khi bắt đầu triển khai?
4. Khi nào được suppress, ai chịu trách nhiệm và bao giờ xem lại?
5. Làm sao để JDK, Maven/Gradle, annotation processor và CI không đưa ra kết quả khác nhau?

**Mục tiêu** là giữ luồng thay đổi mới không tạo thêm cảnh báo có ý nghĩa, đồng thời xử lý warning cũ theo lộ trình rõ ràng. Không nên bắt toàn bộ dự án lập tức đạt `-Xlint:all -Werror` nếu việc đó chỉ dẫn đến tắt mọi warning hoặc thêm suppress vô tội vạ.

## 2. Phân biệt `-Werror`, `-Xlint`, `-nowarn` và diagnostic

| Tùy chọn | Tác dụng |
| --- | --- |
| `-Werror` | Biến việc có bất kỳ warning được compiler phát ra thành **lỗi compile**; có thể áp dụng cả warning không thuộc lint category. |
| `-Xlint` | Bật các lint warnings được phiên bản `javac` khuyến nghị. |
| `-Xlint:all` | Bật tất cả lint categories mà phiên bản compiler hiện tại hỗ trợ. |
| `-Xlint:deprecation,unchecked` | Bật những nhóm cảnh báo được chỉ định. |
| `-Xlint:all,-deprecation` | Bật toàn bộ lint categories trừ nhóm `deprecation`. |
| `-Xlint:none` hoặc `-nowarn` | Tắt các lint warnings tương ứng; có thể vẫn có diagnostic khác, tùy compiler. Không nên dùng để che vấn đề. |
| `-Xmaxwarns 100` | Giới hạn **số warning được in ra**, không phải ngân sách cảnh báo được phép xuất hiện. |
| `-Xdiags:verbose` | Hiển thị chẩn đoán chi tiết, giúp hiểu symbol/type liên quan. |

Ví dụ bật nhóm cảnh báo liên quan trực tiếp đến Java source:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation,removal,unchecked,rawtypes \
  -Werror -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

Đây là lệnh cho **Bash**; dấu `\` ở cuối dòng là ký hiệu nối dòng của shell. Trên PowerShell/cmd có thể đặt tất cả tham số trên một dòng.

**Cơ chế:** `-Xlint` chọn nhóm kiểm tra và phát warning, `-Werror` khiến invocation thất bại nếu có warning còn được phát. `-Werror` không tự sửa mã, không tự phát hiện tất cả vấn đề logic và không biến mọi `Note:` thành error.

Một số cảnh báo được bật mặc định ngay cả khi không viết `-Xlint` (phụ thuộc phiên bản `javac`), nên một project vẫn có thể thất bại với `-Werror` đơn lẻ. Ngược lại, nhiều vấn đề chỉ hiện ra dưới dạng warning cụ thể khi chọn `-Xlint:<category>`.

Kiểm tra danh sách category thực sự được hỗ trợ bởi compiler trên máy:

~~~bash
javac --help-lint
javac --help
javac -version
~~~

Không sao chép category từ một bản JDK mới nếu compiler của dự án chưa hỗ trợ. Danh sách lint categories có thể mở rộng theo JDK; `-Xlint:all` vì vậy cũng có thể phát nhiều warning hơn sau khi nâng toolchain.

## 3. Thực nghiệm: warning thường, `-Werror` và exit code

Tạo hai tệp nguồn UTF-8 trong cấu trúc:

~~~text
project/
  src/demo/LegacyApi.java
  src/demo/WarningDemo.java
  out/
~~~

**`src/demo/LegacyApi.java`:**

~~~java
package demo;

public final class LegacyApi {
    @Deprecated(since = "17", forRemoval = false)
    public static String legacy() {
        return "old";
    }

    public static String modern() {
        return "new";
    }
}
~~~

**`src/demo/WarningDemo.java`:**

~~~java
package demo;

public final class WarningDemo {
    public static void main(String[] args) {
        System.out.println(LegacyApi.legacy());
    }
}
~~~

Hai tệp trên là mã Java 17 hợp lệ. Annotation `@Deprecated` khai báo phương thức `legacy()` đã cũ nhưng chưa nhất thiết sẽ bị loại bỏ. Phương thức vẫn gọi được, nên compiler có thể phát cảnh báo thay vì lỗi về cú pháp hoặc kiểu.

### 3.1. Không bật lint chi tiết

Tại thư mục `project`, tạo thư mục `out` rồi chạy:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
java -cp out demo.WarningDemo
~~~

Với `javac 24.0.2` thử nghiệm, compile **thành công (exit code 0)**; compiler in thông báo ngắn kiểu:

~~~text
Note: .../WarningDemo.java uses or overrides a deprecated API.
Note: Recompile with -Xlint:deprecation for details.
~~~

Dấu `...` trong hai dòng trên biểu thị đường dẫn source cụ thể phụ thuộc hệ thống. **Đây là trích đoạn diagnostic minh họa**, không phải một lệnh hoặc đường dẫn để sao chép nguyên văn. Stdout khi chạy ứng dụng:

~~~text
old
~~~

Không nên suy ra rằng mọi `Note` là warning được `-Werror` đếm. Trong trường hợp này, compiler chỉ nhắc cần bật `-Xlint:deprecation` để xem vị trí chi tiết.

### 3.2. Bật `-Xlint:deprecation` nhưng chưa `-Werror`

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:deprecation \
  -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

Kết quả quan trọng:

~~~text
WarningDemo.java:5: warning: [deprecation] legacy() in LegacyApi has been deprecated
        System.out.println(LegacyApi.legacy());
                                    ^
1 warning
~~~

Dòng chứa absolute path có thể khác. `javac` vẫn trả **exit code 0** và tạo class vì compiler chưa được yêu cầu coi warning là lỗi.

### 3.3. Bật cả `-Werror`

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation -Werror -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

Với `javac 24.0.2`, phần kết thúc diagnostic:

~~~text
warning: [deprecation] legacy() in LegacyApi has been deprecated
error: warnings found and -Werror specified
1 error
1 warning
~~~

Lệnh trả **exit code 1**. Phần code vi phạm vốn vẫn hợp lệ; chính **chính sách cảnh báo** đã khiến compile task không thành công. Đây là tín hiệu mà shell, Maven, Gradle và CI có thể dùng để dừng build.

**Cẩn thận với artifact cũ:** sau một lần compile thất bại, thư mục `out` có thể vẫn chứa `.class` từ lần build thành công trước. Đừng chạy `java -cp out ...` rồi xem ứng dụng chạy được là bằng chứng lần `-Werror` vừa thành công. Khi cần chứng minh chính xác, compile vào thư mục đầu ra mới và kiểm tra exit code.

### 3.4. Vì sao tắt deprecation lại khiến `-Werror` qua?

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:all,-deprecation -Werror -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

Với **hai tệp trên**, `javac 24.0.2` trả exit code **0** dù vẫn có thể in `Note` về API deprecated, vì warning deprecation đã không được phát như lint warning. Đây là minh họa cú pháp `-Xlint:all,-deprecation`, **không phải khuyến nghị** tắt deprecation trong toàn dự án. Nếu có warning thuộc category khác, `-Werror` vẫn làm compile fail.

## 4. Những lint categories nên hiểu trước khi chọn chính sách

Mỗi nhóm có tác động khác nhau; không phải mọi warning đều có mức độ ưu tiên giống nhau.

| Category | Cảnh báo về điều gì? | Cách xử lý thường hợp lý |
| --- | --- | --- |
| `unchecked` | Chuyển đổi/call generic không kiểm tra đủ an toàn kiểu khi chạy | Dùng generic types đúng, cô lập adapter legacy, kiểm chứng cast |
| `rawtypes` | Dùng raw generic type như `List` thay cho `List<String>` | Khai báo type parameters hoặc `List<?>` nếu chỉ cần kiểu chưa biết |
| `removal` | Tham chiếu API có `@Deprecated(forRemoval=true)` | Ưu tiên lên kế hoạch thay API, vì nguy cơ bị xóa cao |
| `deprecation` | Dùng API đã deprecated (không nhất thiết for removal) | Tìm API thay thế; ghi lý do tồn tại tạm nếu chưa thể sửa |
| `serial` | Một số vấn đề với serializable classes, như thiếu `serialVersionUID` | Xác định serialization contract, thêm UID phù hợp nếu cần |
| `fallthrough` | `switch` statement có nhánh tiếp tục sang case kế tiếp đáng nghi | Thêm `break`, `return` hoặc mô tả chủ đích theo quy ước phù hợp |
| `cast` | Cast không cần thiết | Loại bỏ cast không mang ý nghĩa |
| `try` | Cấu trúc `try` / try-with-resources có điều đáng chú ý | Kiểm tra việc đóng resource và semantics |
| `options` | Tùy chọn compiler thiếu nhất quán hoặc có nguy cơ sai | Sửa compiler flags/toolchain, ví dụ dùng `--release` |
| `processing` | Một số vấn đề khi xử lý annotation | Kiểm tra annotation processor path, supported versions, options |
| `path` | Path elements không hợp lệ | Sửa classpath/sourcepath/module path bị sai |
| `exports`, `module` | Những vấn đề liên quan API xuất ra từ module hoặc module system | Đánh giá module descriptor và public API |

`deprecation` và `removal` không nên nhập thành một hạng mục duy nhất: một API đã deprecated nhưng vẫn được duy trì nhiều năm có mức độ cấp thiết khác API đã đánh dấu sẽ bị loại bỏ. Khi dùng `@SuppressWarnings`, khóa suppression cũng cần khớp loại warning thực tế.

Không phải category nào cũng có ở mọi JDK. Ví dụ danh sách mở rộng thêm các nhóm kiểm tra qua các bản compiler. Dùng `javac --help-lint` của toolchain thực tế và giữ tài liệu version tối thiểu mà dự án hỗ trợ.

## 5. Phân loại mức độ xử lý theo rủi ro

Một chính sách thực tiễn có thể chia warning thành các lớp theo rủi ro và khả năng sửa:

| Nhóm | Ví dụ | Đề xuất hành động |
| --- | --- | --- |
| **Chặn ngay trên code mới** | `unchecked`, `rawtypes`, `removal` trong module đang sở hữu | Sửa trực tiếp hoặc có suppression cục bộ được review; build fail nếu warning được bật và còn tồn tại |
| **Cần xử lý nhưng có thể chuyển tiếp** | `deprecation` do API bên thứ ba, `serial` ở mã legacy | Ghi nguyên nhân, phạm vi và thời hạn; không để số warning mới tăng |
| **Cấu hình/môi trường** | `options`, `path`, `processing` | Điều chỉnh build, compiler JDK, processor path; không giấu bằng suppress trong source |
| **Đặc thù generated/external code** | Source do generator tạo hoặc mẫu code nằm ngoài quyền sửa | Sửa generator, tách compile task hoặc quản lý một ngoại lệ có phạm vi rõ ràng |

Đây là **một mẫu chính sách**, không phải bảng mức độ nghiêm trọng do `javac` chính thức quy định. Mức ưu tiên cần phản ánh loại dự án: thư viện public API nhạy với deprecation và binary compatibility; ứng dụng nội bộ có thể ưu tiên lỗi generic/serialization; hệ thống lớn dùng annotation processing cần chú ý processor warnings.

**Không dùng `-Werror` như thước đo chất lượng duy nhất.** Compiler warning không thay cho test, static analyzer (Error Prone, SpotBugs, Checkstyle...), security scan hoặc review. Ngược lại, các công cụ ngoài compiler có mức “warning/error” và cờ fail riêng, không nhất thiết bị `javac -Werror` chi phối.

## 6. Một lộ trình áp dụng không làm CI tê liệt

### Giai đoạn A — Quan sát trước khi chặn

- Chốt **compiler JDK và `--release`**. Dùng cùng toolchain trên local và CI để tránh khác biệt warning categories.
- Bật một tập lint có ích, ví dụ `-Xlint:deprecation,removal,unchecked,rawtypes`, **chưa thêm `-Werror`**.
- Chạy **clean compile** và thu thập diagnostic: category, tệp/dòng, module, người phụ trách, khả năng sửa. Đừng chỉ đếm tổng số `Note` hay gom mọi log line có chữ warning.
- Xác định warning thuộc code do nhóm sở hữu, generated source, dependency/plugin hoặc cấu hình compiler.
- Ưu tiên sửa những warning rõ ràng, chi phí thấp và có ảnh hưởng lớn.

### Giai đoạn B — Chặn warning mới ở phạm vi hẹp

Bắt đầu với module sạch hoặc source set kiểm soát tốt, bật `-Werror` cho chính compile task đó. Nếu toàn bộ module vẫn có warning cũ, không thể chỉ thêm `-Werror` rồi cho phép “N warning”: **`javac -Werror` là cơ chế fail nếu có warning, không hỗ trợ warning budget bằng số**.

Một dashboard so sánh baseline có thể tạm cho phép số warning hiện hữu mà không tăng, nhưng cơ chế so sánh log/baseline đó cần triển khai **ngoài `javac`**, và phải giữ compiler/output format ổn định. Một cách khác là sửa warning cũ, tách module/task, hoặc dùng suppression có căn cứ. Tránh che hoàn toàn một category trên toàn codebase chỉ để CI qua.

### Giai đoạn C — Mở rộng và duy trì

Khi module sạch:
- Bật `-Werror` trên CI bắt buộc và cùng cấu hình khi chạy local.
- Mở rộng tuần tự sang các module còn lại, theo thứ tự ưu tiên.
- Theo dõi warning khi nâng JDK/compiler plugin và annotation processor.
- Review suppression mới như thay đổi kỹ thuật có lý do và thời hạn.
- Chạy build sạch định kỳ; incremental compiler có thể không biên dịch lại toàn bộ source trong mỗi lần chạy.

Một chính sách có hiệu lực cần có **ownership**: ai sửa warning trong code, ai cập nhật generator, ai xử lý build flags và ai phê duyệt ngoại lệ. Nếu warning mới bắt đầu xuất hiện sau một nâng cấp JDK, nhóm phụ trách build cần xác định nó do compiler mới phát hiện rủi ro hay do toolchain chưa đồng bộ.

## 7. Suppression đúng phạm vi: `@SuppressWarnings`

`@SuppressWarnings` là cách cho compiler biết một warning category có thể được bỏ qua **trong phạm vi khai báo được gắn annotation**, nếu compiler hỗ trợ category đó.

Ví dụ một adapter legacy hợp lệ:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SuppressDemo {
    @Deprecated
    static String legacy() {
        return "old";
    }

    @SuppressWarnings("deprecation")
    static String permittedUntilMigrated() {
        return legacy();
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> oldApi() {
        List raw = new ArrayList();
        raw.add("x");
        return raw;
    }

    public static void main(String[] args) {
        System.out.println(permittedUntilMigrated() + ":" + oldApi().get(0));
    }
}
~~~

Lưu file `SuppressDemo.java` và chạy:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation,rawtypes,unchecked -Werror \
  SuppressDemo.java
java SuppressDemo
~~~

Với **`javac 24.0.2`** và source này, compiler trả **exit code 0**, stdout:

~~~text
old:x
~~~

Diễn giải: warning chỉ bị suppress tại nơi được cho phép; việc suppress không làm `legacy()` hết deprecated hoặc biến raw `List` thành an toàn kiểu. Ở đây raw/unchecked code được cố ý cô lập trong một method; nếu dữ liệu hoặc cast từ API ngoài không được kiểm soát, việc suppress có thể che một `ClassCastException` thật.

Thực hành tốt:
- Đặt `@SuppressWarnings` lên **method, local variable hoặc khai báo nhỏ nhất** mà compiler cho phép và giải thích vì sao an toàn.
- Thêm comment lý do và điều kiện bỏ suppression; không nhất thiết gắn vào toàn class/package.
- Xem đúng warning key trong diagnostic, ví dụ `[unchecked]`, `[deprecation]` hoặc `[removal]`.
- Ưu tiên sửa căn nguyên trước: dùng generics, cập nhật API, sửa compiler options; suppression chỉ là ngoại lệ có chủ đích.
- Không giả định mọi warning đều suppress được bằng annotation: `options`, `path`, `processing` và những diagnostic cấu hình ở cấp invocation có phạm vi khác, cần xử lý ở build.

Ví dụ ngoại lệ nên kèm ghi chú phù hợp như: “Adapter tương thích phiên bản cũ của thư viện X; đã kiểm tra type ở boundary; sẽ xóa khi nâng thư viện theo issue được theo dõi”. Không cần tạo annotation hoặc cơ chế nội bộ riêng khi `@SuppressWarnings` của Java đủ dùng.

## 8. `-Werror` với `-Xlint:all`: khi nào hữu ích, khi nào quá gắt?

Cấu hình:

~~~bash
javac --release 17 -Xlint:all -Werror -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

làm mọi lint warning đang bật trở thành lý do fail build. Ưu điểm: chương trình mới hoặc module đã sạch giữ được tiêu chuẩn rộng. Nhược điểm: sau khi nâng JDK, `-Xlint:all` có thể thêm loại warning mới (hoặc thay đổi điều kiện phát), khiến build fail ở mã không đổi. Các warnings do annotation processing hoặc module metadata cũng có thể khó xử lý đồng loạt.

Giải pháp vận hành:
- Dùng toolchain version **có kiểm soát**, nâng theo kế hoạch và kiểm tra breaking changes.
- Với codebase đã sạch, có thể dùng `-Xlint:all -Werror` và chỉnh policy khi JDK thay đổi.
- Với codebase lớn đang chuyển tiếp, bắt đầu bằng **category allowlist tường minh**, ví dụ `-Xlint:deprecation,removal,unchecked,rawtypes -Werror`.
- Nếu có category thực sự không phù hợp toàn dự án, cân nhắc `-Xlint:all,-<category>`; ghi lý do và bảo đảm không bỏ nhóm rủi ro cao.
- Khi một warning là lỗi của generator/plugin bên ngoài, ưu tiên cập nhật generator hoặc điều chỉnh đúng compile task thay vì tắt toàn bộ warnings.

**Lưu ý:** `-Werror` có thể fail vì warning nằm ngoài các category được liệt kê trong `-Xlint`. Việc chỉ bật vài lint categories **không đảm bảo** đó là danh sách đầy đủ mọi lý do build có thể fail. Hãy đọc diagnostic thực tế và đặt policy ở compiler/task-level phù hợp.

## 9. Cấu hình Maven Compiler Plugin

Với dự án Maven có Java 17 target, ví dụ phần cấu hình trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
                <showWarnings>true</showWarnings>
                <failOnWarning>true</failOnWarning>
                <compilerArgs>
                    <arg>-Xlint:deprecation,removal,unchecked,rawtypes</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn của POM đã có** chứ không phải POM độc lập. Version `3.14.1` là ví dụ cho dòng plugin 3.x; kiểm tra version plugin/toolchain mà dự án đang dùng khi triển khai.

- `<failOnWarning>true</failOnWarning>` yêu cầu Maven Compiler Plugin chuyển chính sách fail khi có warning thành `-Werror` trong compiler arguments ở các bản plugin hỗ trợ.
- `<showWarnings>true</showWarnings>` giữ các diagnostic hữu ích hiện ra trong log, thay vì làm mất căn cứ điều tra.
- `<compilerArgs>` chọn category compiler cần bật; không thêm `-Werror` lần nữa nếu đã chọn `failOnWarning`.
- `<release>17</release>` đồng bộ source, target bytecode và API nền tảng Java 17, tránh một số warning cấu hình `-source/-target` khi dùng compiler mới.

Chạy kiểm chứng:

~~~bash
mvn clean compile
mvn -X compile
~~~

`mvn -X` giúp quan sát compiler flags và JDK liên quan, nhưng log có thể dài; không cần lưu secrets/config cá nhân từ log vào bài review. Nếu dự án đa module, xác định plugin configuration đặt trong parent `pluginManagement` đã thật sự được áp dụng ở từng module chưa. Một plugin chỉ nằm trong `pluginManagement` chưa chắc đã chạy nếu không có plugin binding tương ứng.

Maven có lifecycle compile/testCompile và nhiều compiler execution; thống nhất policy cho source/test source theo nhu cầu. Một project dùng generated sources có thể cần điều chỉnh processor path và plugin version trước khi bật gate.

## 10. Cấu hình Gradle JavaCompile

Với Groovy DSL **`build.gradle`**:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += [
        '-Xlint:deprecation,removal,unchecked,rawtypes',
        '-Werror'
    ]
}
~~~

Với Kotlin DSL **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.addAll(
        listOf("-Xlint:deprecation,removal,unchecked,rawtypes", "-Werror")
    )
}
~~~

Các đoạn này là **cấu hình Gradle**, không phải Java source. Chúng áp dụng cho các task kiểu `JavaCompile`, thường gồm `compileJava` và `compileTestJava`. Nếu muốn áp dụng từng bước, cấu hình một task cụ thể trước, chẳng hạn chỉ `tasks.named('compileJava', JavaCompile) { ... }` trong Groovy DSL; đó là **đoạn minh họa** cần đặt trong build script có Java plugin.

Chạy:

~~~bash
./gradlew clean compileJava
./gradlew compileTestJava
~~~

Trên Windows có thể dùng `gradlew.bat`. Gradle Java toolchain nếu đã cấu hình sẽ chọn JDK cho `JavaCompile`; `options.release` kiểm soát target. Hãy xác minh các tasks đều nhận đúng arguments và version compiler.

**Điểm thực tế:** chỉ đặt `options.warnings = true` (nếu API phiên bản Gradle hỗ trợ) không đồng nghĩa bật `-Werror`. Cần compiler arguments hoặc cơ chế tương đương thực sự làm build thất bại khi warning được phát.

## 11. Annotation processing, generated source và warning policy

Trong các dự án dùng JSR 269, Lombok, MapStruct hoặc các code generator, cảnh báo có thể đến từ nhiều nơi:

- **Processor diagnostics** qua `Messager.printMessage(Diagnostic.Kind.WARNING, ...)` có thể trở thành nguyên nhân compile fail dưới `-Werror`.
- **Generated Java source** được compiler biên dịch, và do đó có thể tạo lint warnings giống source viết tay.
- **Processor path khác compile classpath**: thiếu dependency, processor chạy trên JDK không tương thích hoặc processor báo warning cấu hình cần được xử lý tại build.
- **Source được sinh từ phiên bản generator cũ**: warning không nên được giải quyết bằng sửa thủ công file dưới `build/generated` hay `target/generated-sources` vì lần build sau sẽ sinh lại.

Hướng xử lý ưu tiên:
1. Xác định warning do source viết tay hay do generator/processor phát.
2. Nâng hoặc cấu hình processor/generator nếu nó tạo code không đáp ứng policy.
3. Nếu processor có cơ chế suppression chính thức và kiểm soát được phạm vi, dùng có lý do; kiểm tra nó còn phát warning gì.
4. Khi cần tách policy cho generated sources, cấu hình compile task riêng với đường dẫn và ownership rõ ràng; không vô hiệu hóa warning của toàn ứng dụng.
5. Test trên build **clean** vì source được sinh và số processing rounds có thể khác khi incremental build.

**Đừng lẫn thông báo `Note:` và `warning:`**. `Diagnostic.Kind.NOTE` thường không tương đương `Diagnostic.Kind.WARNING`. Quyết định fail dựa trên diagnostic thật mà compiler phát.

## 12. Những lỗi điển hình khi kích hoạt `-Werror`

### 12.1. Chuyển mọi warning sang lỗi ngay trong codebase lớn

Hàng trăm warnings legacy khiến CI không thể merge; mọi người bắt đầu thêm `@SuppressWarnings` bừa bãi. Cách tốt hơn là dọn dần từng module, phân loại risk và áp dụng gate khi module đã sạch.

### 12.2. Tắt warning bằng `-nowarn` nhưng vẫn giữ `-Werror`

Điều này có thể khiến gate trở nên vô nghĩa với những lint warnings đã bị tắt; cũng không bảo đảm mọi warning phi-lint biến mất. Đừng đánh đồng “build xanh” với “không có vấn đề”.

### 12.3. Chỉ nhìn exit code khi có artifact cũ

Khi compiler fail, các `.class` cũ vẫn có thể chạy. Cần kiểm tra exit code, compiler output và build sạch; `java` chạy được sau compile fail không chứng minh compile mới thành công.

### 12.4. Chỉ thêm `-Werror` trên một máy

Compiler plugin hoặc IDE khác không dùng flags đó, nên CI và local cho kết quả lệch. Cấu hình trong repository, dùng wrapper/toolchain và chạy gate trên CI.

### 12.5. Nâng JDK mà không kiểm tra tập warning

Một bản compiler mới có thể thêm lint categories và thay ngưỡng chẩn đoán. Chạy build thử với JDK mới, đọc `javac --help-lint` rồi cập nhật policy/suppression theo đánh giá kỹ thuật.

### 12.6. Dùng `@SuppressWarnings("all")` trên cả package/class

Dù một compiler có thể hiểu một số key rộng, cách này giảm khả năng phát hiện lỗi mới và không là giải pháp đáng tin cho mọi diagnostic. Suppress đúng key ở phạm vi nhỏ nhất, có lý do và xem lại định kỳ.

### 12.7. Trộn warning của javac với warning của các công cụ khác

`-Werror` thuộc `javac`. Warnings của compiler Kotlin, linter, formatter, tests hoặc quality plugin có flag và failure policy riêng. Nếu CI vẫn pass sau lỗi linter, hãy chỉnh task linter; nếu CI fail vì `javac` warning, hãy đọc compiler diagnostic.

## 13. Chính sách mẫu dành cho nhóm phát triển

Một dự án Java 17 có thể thống nhất quy tắc:

**Phạm vi:** Java source do nhóm sở hữu, được biên dịch bởi toolchain JDK đã chốt; mỗi module sạch phải có cùng lint flags trong local build và CI.

**Cảnh báo mặc định:** bật `deprecation`, `removal`, `unchecked`, `rawtypes`; xem xét bổ sung `serial`, `fallthrough`, `try`, `path`, `options`, `processing` sau khi đánh giá codebase. Cảnh báo thuộc compiler/toolchain phải được đưa vào nhóm phụ trách build.

**Chặn CI:** module đã sạch dùng `-Werror`; không được merge thay đổi khiến compile task của module phát warning mới. Một số warning tồn tại ở module chưa sạch được theo dõi trong bảng remediation có owner và kỳ review, đồng thời tránh bỏ qua warning mới.

**Ngoại lệ:** chỉ cho phép suppression tại phạm vi nhỏ nhất, ghi lý do an toàn hoặc ràng buộc thư viện, yêu cầu reviewer kiểm chứng và theo dõi thời hạn xóa. Không tắt `unchecked` toàn dự án chỉ vì một adapter legacy.

**Nâng cấp:** mọi lần nâng JDK, Maven Compiler Plugin, Gradle hoặc annotation processor phải chạy job test trên compiler mới, so sánh warning theo category và xác minh thời điểm áp dụng gate.

**Kết quả mong muốn:** nếu một developer đưa lời gọi deprecated mới vào module đã khóa warning, build fail sớm với vị trí cụ thể; người đó sửa API hoặc đề xuất ngoại lệ nhỏ có thể review. Khi warning xuất phát từ compiler options như `-source/-target` không nhất quán, nhóm sửa cấu hình build.

## 14. Checklist trước khi chuyển gate sang bắt buộc

- [ ] `javac -version` và toolchain thực tế trên CI/local đã xác định.
- [ ] `--release`/encoding được cấu hình nhất quán.
- [ ] Lint categories đã chọn có trong `javac --help-lint` của compiler.
- [ ] Build sạch đã thống kê warning theo category, module và source owner.
- [ ] Đã phân biệt warning source với warning processor/generated code.
- [ ] Module bật `-Werror` **không còn warning chưa được xử lý**.
- [ ] Ngoại lệ có phạm vi, lý do và quy trình xóa suppression.
- [ ] Maven/Gradle thực sự truyền `-Werror` và `-Xlint` vào compile tasks cần bảo vệ.
- [ ] CI fail khi cố ý thêm một warning thử nghiệm và pass sau khi sửa.
- [ ] Khi nâng compiler JDK, có quy trình review warning category mới.

## 15. Tự kiểm tra

**Câu 1.** `-Werror` có tự bật tất cả `-Xlint` categories không?  
**Đáp án:** Không. Nó biến warning **được compiler phát ra** thành lỗi; chọn category bằng `-Xlint` và các compiler options liên quan.

**Câu 2.** Khi không dùng `-Xlint:deprecation`, compiler in `Note: ... uses or overrides a deprecated API`. Chỉ riêng dòng `Note` này có nhất thiết làm `-Werror` fail không?  
**Đáp án:** Không. Cần phân biệt diagnostic `Note` với warning; thí nghiệm phần 3 cho thấy trường hợp này compiler vẫn thành công.

**Câu 3.** `-Xmaxwarns 20 -Werror` có cho phép tối đa 20 warning không?  
**Đáp án:** Không. `-Xmaxwarns` chỉ giới hạn số warning được **hiển thị**, `-Werror` vẫn fail khi có warning được phát.

**Câu 4.** `@SuppressWarnings("unchecked")` có làm generic cast thật sự an toàn không?  
**Đáp án:** Không. Nó chỉ tắt diagnostic ở phạm vi được annotate; programmer phải chứng minh type boundary an toàn bằng thiết kế và test.

**Câu 5.** Vì sao `-Xlint:all -Werror` dễ fail sau khi nâng JDK dù source không đổi?  
**Đáp án:** Bản `javac` mới có thể thêm lint categories hoặc phát hiện thêm tình huống đáng cảnh báo.

**Câu 6.** Khi warning đến từ `target/generated-sources`, nên sửa file được sinh bằng tay?  
**Đáp án:** Không. Hãy sửa generator, cấu hình processor hoặc quản lý compile task/generator version; file sinh ra sẽ bị ghi lại.

**Câu 7.** Tại sao `-source 17 -target 17 -Werror` trên compiler mới có thể fail do `[options]`?  
**Đáp án:** Compiler có thể cảnh báo về system modules không được chọn theo release mục tiêu. Với ứng dụng cần Java 17, dùng `--release 17` để ràng buộc thêm API nền tảng và giảm sai cấu hình.

**Câu 8.** Một module còn 60 warnings legacy thì thêm `-Werror` nhưng cho “budget 60” được không?  
**Đáp án:** `javac -Werror` không có cơ chế budget. Cần dọn warning, tách phạm vi hoặc một cơ chế baseline bên ngoài compiler trong giai đoạn chuyển tiếp.

## 16. Tài liệu chính thức

- [Oracle javac Command — `-Werror`, `-Xlint`, `--help-lint`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Maven Compiler Plugin — compile goal và `failOnWarning`](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Gradle CompileOptions — `compilerArgs`](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html)
- [Java `@SuppressWarnings` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html)

**Ghi nhớ:** `-Werror` là **cổng chặn** warning đã được compiler phát ra, còn `-Xlint` quyết định nhiều nhóm warning cần kiểm tra. Muốn gate thực sự có ích, phải chọn category có mục đích, giữ toolchain ổn định, xử lý warning cũ theo ownership và dùng suppression nhỏ, có lý do. Khi đó CI giúp phát hiện rủi ro mới thay vì chỉ tạo ra build đỏ hoặc warning bị tắt hàng loạt.
