# Không bỏ qua warning compiler trong Java

Compiler warning là tín hiệu cho biết source code có điểm đáng xem lại: dùng API cũ, ép kiểu không an toàn, khai báo raw type, thiếu thông tin serialization hoặc có cấu trúc dễ gây lỗi. Một warning không nhất thiết làm chương trình chạy sai ngay, nhưng nó thường chỉ ra rủi ro mà compiler có thể phát hiện trước khi code được chạy.

Anti-pattern “bỏ qua warning compiler” xuất hiện khi developer tắt warning hàng loạt, thêm suppression quá rộng, hoặc để build thành công mà không đọc các cảnh báo. Cách làm đó khiến lỗi tiềm ẩn tồn tại lâu, làm warning mới bị chìm trong log và khiến việc nâng JDK khó khăn hơn.

Quy trình tốt là bật các cảnh báo hữu ích, đọc và phân loại từng warning, sửa nguyên nhân, chỉ suppression ở phạm vi nhỏ khi có lý do kỹ thuật rõ ràng, rồi đưa kiểm tra vào CI. Bài này dùng javac, Maven Compiler Plugin và Gradle để minh họa cách làm đó.

## 1. Compiler warning là gì?

Compiler warning là thông báo từ compiler rằng code có một cấu trúc đáng ngờ, một API không còn được khuyến nghị hoặc một thao tác có thể gây lỗi trong một số tình huống.

Compiler thường vẫn tạo class file khi chỉ có warning. Vì vậy:

- Build có thể trả exit code 0 dù có warning.
- Chương trình có thể chạy bình thường trong test hiện tại.
- Warning vẫn có thể chỉ ra lỗi xuất hiện khi dữ liệu, runtime hoặc dependency thay đổi.
- Warning có thể trở thành lỗi khi bật chế độ coi warning là error.

Warning khác error. Error ngăn compiler tạo output hợp lệ cho compilation đó; warning thông báo rủi ro nhưng mặc định không nhất thiết dừng build.

## 2. Vì sao bỏ qua warning là anti-pattern?

Bỏ qua warning tạo ra một khoản nợ kỹ thuật khó quan sát. Khi dự án liên tục build với hàng trăm warning, developer dần quen với chúng và không nhận ra cảnh báo mới có thể chỉ ra lỗi nghiêm trọng.

Các hậu quả thường gặp:

- Dùng API deprecated lâu ngày, đến khi API bị loại bỏ mới phải sửa gấp.
- Raw type và unchecked cast làm mất kiểm tra kiểu tại compile time.
- Warning serialization khiến dữ liệu lưu trữ khó tương thích giữa các phiên bản.
- Code có fall-through hoặc static access không rõ ràng, dễ tạo lỗi khi refactor.
- CI báo build xanh dù source mới thêm warning.
- Log bị nhiễu, làm giảm khả năng tìm warning quan trọng.
- Nâng JDK hoặc compiler plugin tạo thêm warning khiến dự án khó nâng cấp.

Một warning không tự chứng minh có bug. Nó là bằng chứng để developer kiểm tra một rủi ro cụ thể. Đọc, hiểu và xử lý warning giúp giữ chất lượng code theo thời gian.

## 3. Phân biệt warning của compiler và warning của công cụ khác

Không phải mọi dòng có chữ WARNING đều đến từ javac.

| Nguồn | Ví dụ |
|---|---|
| Java compiler | deprecated API, unchecked conversion, raw type |
| Maven/Gradle | plugin cũ, cấu hình build không còn được khuyến nghị |
| Annotation processor | processor không nhận annotation hoặc sinh code có vấn đề |
| Static analysis | Checkstyle, SpotBugs, PMD, Error Prone |
| IDE | inspection, code style hoặc API usage warning |
| Runtime | log cảnh báo từ thư viện hoặc JVM |

Cần xác định đúng công cụ phát warning trước khi sửa. Tắt javac lint không xử lý warning từ Maven plugin; tắt IDE inspection cũng không làm javac ngừng cảnh báo.

Khi điều tra, ghi lại tên tool, rule/category, file, dòng code và command build đã tạo ra thông báo.

## 4. Các warning javac thường gặp

Một số nhóm warning quan trọng:

| Category | Ý nghĩa | Rủi ro thường gặp |
|---|---|---|
| deprecation | Đang gọi API deprecated | API có thể thay đổi hoặc bị loại bỏ |
| removal | Đang gọi API được đánh dấu để loại bỏ | Mã nguồn phụ thuộc API có vòng đời kết thúc |
| unchecked | Thao tác generic không được kiểm tra đầy đủ | ClassCastException khi chạy |
| rawtypes | Dùng generic type mà bỏ tham số kiểu | Mất type safety |
| serial | Serializable class thiếu serialVersionUID hoặc vấn đề serialization | Khó kiểm soát tương thích dữ liệu |
| fallthrough | Switch có thể chạy tiếp sang case sau | Logic chạy nhầm nhánh |
| static | Truy cập static member qua object instance | Code gây hiểu nhầm về đối tượng |
| cast | Có cast dư thừa hoặc không cần thiết | Code khó đọc, che giấu giả định kiểu |
| try | Cách sử dụng try-with-resources đáng xem lại | Tài nguyên hoặc exception có thể bị xử lý sai |
| processing | Vấn đề liên quan annotation processing | Generated code hoặc processor không như dự kiến |

Danh sách category và mức hỗ trợ phụ thuộc JDK. Xem javac --help và tài liệu đúng phiên bản compiler đang dùng để biết các nhóm cảnh báo hiện có.

## 5. Bật warning có chủ đích với javac

Tùy chọn -Xlint bật các nhóm warning chi tiết của javac. Dùng -Xlint:all để yêu cầu compiler hiển thị tất cả nhóm warning được hỗ trợ.

Ví dụ:

~~~powershell
javac --release 17 -Xlint:all -encoding UTF-8 -d out src\main\java\demo\App.java
~~~

Ý nghĩa:

- --release 17 đặt Java release mục tiêu.
- -Xlint:all bật các nhóm cảnh báo.
- -encoding UTF-8 cố định encoding source.
- -d out đặt thư mục output class file.

Nếu chỉ muốn bật một số nhóm, có thể chỉ định category:

~~~powershell
javac --release 17 -Xlint:deprecation,unchecked,rawtypes App.java
~~~

Có thể tắt riêng một category bằng cú pháp loại trừ, ví dụ -Xlint:all,-serial. Chỉ làm vậy khi đã hiểu warning đó, có lý do cụ thể và có kế hoạch xử lý phù hợp. Loại trừ category toàn dự án có thể che warning mới ở mọi file.

Tránh dùng -nowarn hoặc -Xlint:none như cấu hình build lâu dài. Chúng làm mất thông tin compiler có thể cung cấp cho cả nhóm.

## 6. Dùng -Werror để ngăn warning mới

Tùy chọn -Werror yêu cầu javac kết thúc compilation với lỗi nếu có warning. Kết hợp với -Xlint:all:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out src\main\java\demo\App.java
~~~

Khi source không có warning, compilation thành công. Khi compiler phát warning, build thất bại để developer xử lý trước khi thay đổi được chấp nhận.

Không bật -Werror một cách đột ngột trên codebase đang có nhiều warning chưa xử lý. Việc đó có thể làm mọi build thất bại cùng lúc, kể cả thay đổi không liên quan. Hãy thống kê baseline, sửa warning hiện có, rồi bật chế độ fail-on-warning theo module hoặc toàn dự án khi đã sẵn sàng.

-Werror áp dụng cho warning do compiler phát ra trong compilation đó. Nó không tự biến mọi warning từ IDE, Maven plugin hay static analysis thành compiler error.

## 7. Ví dụ tạo warning: raw type, unchecked và deprecated API

Tạo file WarningDemo.java:

~~~java
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class WarningDemo {
    private WarningDemo() {
    }

    public static void main(String[] args) {
        List names = new ArrayList();
        names.add("Java");

        List<String> typedNames = names;
        String first = typedNames.get(0);

        int legacyYear = new Date().getYear();

        System.out.println(first);
        System.out.println("Legacy year offset: " + legacyYear);
    }
}
~~~

Biên dịch để xem warning:

~~~powershell
javac --release 17 -Xlint:all -encoding UTF-8 WarningDemo.java
~~~

Compiler có thể cảnh báo các điểm sau:

- List và ArrayList được dùng dưới dạng raw type.
- Gán raw List vào List<String> tạo unchecked conversion.
- Date.getYear() là API deprecated.

Vì warning mặc định không phải error, compiler vẫn có thể tạo WarningDemo.class. Đây là lý do build xanh không đồng nghĩa code không có vấn đề.

Thử bật -Werror:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WarningDemo.java
~~~

Lần này compilation thất bại vì warning được nâng thành error. Exit code khác 0 giúp CI nhận biết vấn đề.

Tên warning và số lượng warning có thể khác theo JDK/compiler version; điều quan trọng là compiler chỉ ra raw type, unchecked conversion và deprecated API trong ví dụ.

## 8. Sửa raw type và unchecked conversion bằng generics

Đoạn code cũ:

~~~java
List names = new ArrayList();
names.add("Java");
List<String> typedNames = names;
~~~

Dùng generic type đầy đủ:

~~~java
List<String> names = new ArrayList<>();
names.add("Java");
~~~

Diamond operator <> cho phép compiler suy ra tham số kiểu từ phía trái. Collection giờ chỉ nhận String theo kiểu đã khai báo, compiler có thể kiểm tra các thao tác thêm và đọc.

Nếu dữ liệu đến từ API legacy trả về Object hoặc raw collection, hãy kiểm tra từng phần tử trước khi chuyển:

~~~java
static List<String> copyStrings(Object value) {
    if (!(value instanceof List<?> values)) {
        throw new IllegalArgumentException("Expected a List");
    }

    List<String> result = new ArrayList<>();
    for (Object item : values) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Expected String elements");
        }
        result.add(text);
    }
    return result;
}
~~~

Cách này xác minh cả kiểu container lẫn kiểu phần tử tại runtime. Ép trực tiếp List<?> thành List<String> không thể kiểm tra kiểu phần tử do type erasure.

## 9. Xử lý deprecated và removal warning

Deprecated nghĩa là API không còn được khuyến nghị sử dụng. API vẫn có thể hoạt động, nhưng thư viện hoặc nền tảng có thể hướng developer sang API khác.

Removal warning cảnh báo API được đánh dấu để loại bỏ. Mức độ cần xử lý thường cao hơn vì mã nguồn có thể không biên dịch được trên JDK tương lai.

Quy trình xử lý:

1. Đọc Javadoc của method/class bị deprecated.
2. Tìm API thay thế được tài liệu chính thức khuyến nghị.
3. Kiểm tra khác biệt về semantics, timezone, null behavior và exception.
4. Viết test cho hành vi cũ và mới.
5. Chuyển caller sang API mới.
6. Xóa adapter cũ khi không còn caller.

Ví dụ, nếu code cần lấy năm hiện tại theo UTC, có thể dùng java.time:

~~~java
import java.time.LocalDate;
import java.time.ZoneOffset;

int currentYear = LocalDate.now(ZoneOffset.UTC).getYear();
~~~

Đây là ví dụ cho nghiệp vụ lấy năm hiện tại. Không thay Date.getYear() bằng một biểu thức mới mà bỏ qua semantics cũ: Date.getYear() trả về năm trừ 1900, nên việc thay thế phải dựa trên mục đích thực tế của code.

Nếu phải gọi API deprecated để tương thích với hệ thống cũ, cô lập việc gọi trong một adapter nhỏ, ghi rõ lý do và theo dõi thời điểm loại bỏ.

## 10. Xử lý warning serialization

Class triển khai Serializable thường nên khai báo serialVersionUID tường minh:

~~~java
import java.io.Serializable;

public final class UserSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String username;

    public UserSnapshot(String username) {
        this.username = username;
    }

    public String getUsername() {
        return username;
    }
}
~~~

serialVersionUID giúp kiểm soát việc tương thích khi deserialize object đã được serialize từ phiên bản class khác.

Không chọn một giá trị tùy ý rồi cho rằng mọi thay đổi class đều tương thích. Khi thay đổi cấu trúc dữ liệu, cần xem xét compatibility của serialized form, test dữ liệu cũ và quyết định có giữ hay đổi version UID.

Nếu class không cần serialization, bỏ implements Serializable thay vì thêm UID chỉ để làm warning biến mất.

## 11. SuppressWarnings: chỉ dùng khi có lý do

Java có annotation SuppressWarnings để tắt một warning đã hiểu rõ ở phạm vi khai báo cụ thể.

Ví dụ:

~~~java
@SuppressWarnings("deprecation")
static int readLegacyValue(LegacyRecord record) {
    return record.oldValue();
}
~~~

Annotation này có thể phù hợp khi một adapter buộc phải gọi API cũ để giữ tương thích. Cần ghi rõ lý do và theo dõi kế hoạch loại bỏ adapter.

Với unchecked cast, chỉ suppression tại method nhỏ nhất có thể:

~~~java
@SuppressWarnings("unchecked")
static List<String> adaptLegacyList(Object value) {
    // The caller contract guarantees that value contains only String elements.
    return (List<String>) value;
}
~~~

Đoạn trên chỉ an toàn nếu contract bên ngoài thật sự bảo đảm mọi phần tử là String. Nếu không có bảo đảm đó, hãy kiểm tra từng phần tử và tạo collection mới như ví dụ ở phần generics.

Không dùng @SuppressWarnings("all") trên cả class/package chỉ để làm log sạch. Không thêm suppression trước khi đọc warning và hiểu vì sao thao tác đó an toàn.

## 12. Phân biệt suppression với sửa lỗi

Suppression chỉ ẩn thông báo compiler trong phạm vi annotation. Nó không sửa logic, không thêm runtime validation và không làm thao tác unsafe trở nên an toàn.

Trước khi suppression, cần trả lời:

- Warning cụ thể nào đang được tắt?
- Vì sao code hiện tại vẫn đúng?
- Contract hoặc invariant nào bảo đảm điều đó?
- Có cách sửa để compiler kiểm tra được hay không?
- Phạm vi suppression đã nhỏ nhất chưa?
- Có test bảo vệ giả định đó không?
- Ai sẽ xem xét lại khi API/dependency thay đổi?

Nếu không trả lời được những câu hỏi này, chưa nên suppression.

## 13. Cấu hình Maven Compiler Plugin

Pin Maven Compiler Plugin version và bật warning trong POM:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>${maven.compiler.release}</release>
        <encoding>${project.build.sourceEncoding}</encoding>
        <showWarnings>true</showWarnings>
        <compilerArgs>
          <arg>-Xlint:all</arg>
        </compilerArgs>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Cấu hình trên hiển thị lint warnings khi compile main source và test source. Để yêu cầu compilation thất bại khi có warning, thêm -Werror:

~~~xml
<compilerArgs>
  <arg>-Xlint:all</arg>
  <arg>-Werror</arg>
</compilerArgs>
~~~

Dùng Maven Wrapper để mọi developer và CI chạy cùng Maven distribution. Pin JDK/compiler version khi cần kết quả warning ổn định vì category và nội dung warning có thể thay đổi giữa các JDK.

Chạy:

~~~powershell
.\mvnw.cmd clean verify
~~~

Hoặc trên Linux/macOS:

~~~bash
./mvnw clean verify
~~~

Nếu build thất bại sau khi bật -Werror, đọc warning đầu tiên và sửa nguyên nhân. Không xóa -Werror ngay lập tức để làm CI xanh mà không ghi nhận rủi ro.

## 14. Cấu hình Gradle JavaCompile

Trong Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:all']
    // Enable after the existing warning baseline is clean.
    options.compilerArgs += ['-Werror']
}
~~~

Trong Gradle Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:all")
    // Enable after the existing warning baseline is clean.
    options.compilerArgs.add("-Werror")
}
~~~

Cấu hình trên áp dụng cho các task JavaCompile, thường gồm compileJava và compileTestJava. Nếu dự án có module riêng hoặc custom task, kiểm tra task thực tế để xác nhận compiler args được kế thừa.

Chạy Gradle Wrapper:

~~~powershell
.\gradlew.bat clean build
~~~

Hoặc:

~~~bash
./gradlew clean build
~~~

Gradle Java toolchain có thể pin JDK dùng để compile. Compiler release, JDK toolchain và JVM chạy Gradle là các cấu hình riêng; kiểm tra cả ba khi warning thay đổi giữa local và CI.

## 15. Warning từ annotation processor và generated source

Annotation processor có thể phát warning khi xử lý annotation hoặc tạo source. Generated source cũng có thể tạo warning ở lần compile tiếp theo.

Cách xử lý:

- Xác định warning đến từ source do developer viết hay file generated.
- Pin version processor và dependency.
- Nâng processor nếu version mới sửa warning hoặc tương thích JDK tốt hơn.
- Sửa cấu hình processor và generated source nếu có thể.
- Không sửa file generated trực tiếp nếu nó sẽ bị tạo lại.
- Nếu warning không thể sửa ngay, cô lập processor/module và ghi nhận nguyên nhân.

Tùy chọn -Xlint:processing giúp kiểm tra một số vấn đề liên quan annotation processing. Warning của processor có thể có định dạng riêng, nên đọc cả tên processor và vị trí generated source.

## 16. Warning trong dependency và thư viện bên ngoài

Một thư viện cũ có thể phát warning khi source của nó được compile trong build. Tuy nhiên, javac thường không biên dịch lại source của dependency đã đóng gói thành JAR; warning có thể đến từ annotation, processor, plugin hoặc code adapter của dự án.

Đừng thêm suppression toàn cục chỉ vì dependency có warning. Hãy:

1. Xác định warning thuộc source nào.
2. Kiểm tra dependency version và release notes.
3. Nâng version nếu có bản sửa tương thích.
4. Cô lập API legacy trong adapter.
5. Ghi rõ ngoại lệ nếu chưa thể nâng cấp.
6. Theo dõi ngày hoặc điều kiện loại bỏ ngoại lệ.

Nếu warning đến từ plugin Maven/Gradle, xử lý plugin version và cấu hình plugin. -Xlint chỉ điều khiển warning javac, không xử lý mọi warning của build tool.

## 17. Chiến lược đưa warning policy vào dự án đang có nợ kỹ thuật

Với dự án đã có warning, bật -Werror ngay cho toàn bộ codebase có thể khiến mọi nhánh build thất bại. Có thể triển khai theo giai đoạn:

1. Chạy -Xlint:all và lưu log đầy đủ.
2. Gom warning theo category, module và file.
3. Ưu tiên unchecked, removal, deprecation và warning có khả năng gây lỗi runtime.
4. Sửa warning trong source do team quản lý.
5. Nâng dependency/processor khi warning đến từ version cũ.
6. Tạo baseline rõ ràng cho phần chưa thể xử lý.
7. Ngăn warning mới trong module đã sạch.
8. Mở rộng phạm vi kiểm soát theo từng đợt.
9. Bật -Werror toàn dự án khi baseline đã được xử lý.

Baseline cần có owner, lý do, phạm vi và tiêu chí xóa. Tránh tạo danh sách suppression không thời hạn hoặc bỏ qua warning mới bằng cách cập nhật baseline tự động mà không review.

## 18. Ví dụ hoàn chỉnh: sửa warning rồi build với -Werror

Tạo file WarningFreeDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class WarningFreeDemo {
    private WarningFreeDemo() {
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Java");
        names.add("Maven");

        for (String name : names) {
            System.out.println(name);
        }
    }
}
~~~

Biên dịch với lint và fail-on-warning:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out WarningFreeDemo.java
~~~

Chạy:

~~~powershell
java -cp out WarningFreeDemo
~~~

Stdout chính xác:

~~~text
Java
Maven
~~~

Ví dụ dùng generic type, không gọi API deprecated và không có unchecked cast. Với JDK 17+ tương thích release 17, compilation sạch phải hoàn thành với exit code 0.

Kiểm tra class-file version nếu cần:

~~~powershell
javap -verbose out\WarningFreeDemo.class | Select-String "major version"
~~~

Với release 17, major version mong đợi là 61. Đây là kiểm tra bytecode target; nó không thay thế việc đọc warning và chạy test.

## 19. Quy trình điều tra một warning trong code thật

Khi compiler báo warning:

1. Đọc toàn bộ message, category và file/line.
2. Xác định source, generated code, dependency hay plugin tạo ra warning.
3. Mở code quanh dòng được báo và tìm contract liên quan.
4. Đọc Javadoc/spec của API nếu warning liên quan deprecated/removal.
5. Viết test nhỏ hoặc tái hiện compile nếu nguyên nhân chưa rõ.
6. Sửa nguyên nhân ở source hoặc cấu hình đúng công cụ.
7. Compile lại với category warning tương ứng.
8. Chạy test và kiểm tra output.
9. Nếu phải suppression, thu hẹp annotation và ghi lý do.
10. Kiểm tra CI để bảo đảm warning không quay lại.

Không chỉ xóa dòng warning khỏi log. Kết quả cần là source an toàn hơn hoặc một ngoại lệ được hiểu rõ và có thể xem xét lại.

## 20. Những cách xử lý sai thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách làm tốt hơn |
|---|---|---|
| Tắt toàn bộ warning bằng -nowarn | Mất tín hiệu lỗi tiềm ẩn | Bật -Xlint:all |
| Không đọc warning vì build xanh | Warning mới bị bỏ qua | Review warning trong build log |
| Thêm @SuppressWarnings("all") cho class | Che nhiều vấn đề không liên quan | Suppress đúng category ở method nhỏ |
| Dùng raw List để tránh generic error | Mất kiểm tra kiểu | Khai báo List<T> và diamond operator |
| Ép unchecked cast không có contract | Có thể lỗi ClassCastException | Validate dữ liệu hoặc ghi rõ invariant |
| Giữ API deprecated không có kế hoạch | Nâng JDK khó hơn | Tạo migration plan và adapter |
| Bật -Werror mà không có baseline | Build cũ có thể thất bại hàng loạt | Sửa warning theo giai đoạn |
| Cập nhật warning baseline tự động | Warning mới lọt qua review | Review thay đổi baseline như code |
| Sửa generated source bằng tay | Thay đổi bị ghi đè lần build sau | Sửa generator/processor hoặc cấu hình |
| Cho rằng IDE sạch nghĩa là javac sạch | IDE và compiler có rule khác nhau | Chạy compiler lint trong CI |

## 21. Checklist quản lý compiler warning

- [ ] Biết warning đến từ javac, build plugin, processor hay IDE.
- [ ] Đã bật các warning hữu ích bằng -Xlint:all.
- [ ] Không tắt warning toàn cục chỉ để làm log sạch.
- [ ] Raw type và unchecked conversion đã được sửa bằng generics khi có thể.
- [ ] Deprecated/removal API có kế hoạch thay thế.
- [ ] Serialization warning được xử lý theo compatibility thực tế.
- [ ] SuppressWarnings chỉ dùng cho category cụ thể và phạm vi nhỏ.
- [ ] Mỗi suppression có lý do và contract bảo đảm tính an toàn.
- [ ] Generated source và annotation processor được kiểm tra riêng.
- [ ] Maven Compiler Plugin hoặc Gradle JavaCompile được cấu hình rõ.
- [ ] JDK/compiler version được pin phù hợp với dự án.
- [ ] CI hiển thị warning và ngăn warning mới.
- [ ] -Werror chỉ bật khi baseline đã sẵn sàng.
- [ ] Build sạch, test pass và exit code được kiểm tra.
- [ ] Warning baseline có owner và tiêu chí loại bỏ.

Không bỏ qua compiler warning giúp dự án phát hiện sớm API lỗi thời, thao tác kiểu không an toàn và cấu trúc code dễ gây bug. Bật lint, sửa nguyên nhân, suppression thật hẹp khi có lý do, và đưa chính sách warning vào CI. Khi baseline đã sạch, -Werror biến việc xử lý warning thành một phần ổn định của quy trình review và build.

## Tài liệu tham khảo

- Oracle Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17 — Suppressing Warnings: https://docs.oracle.com/javase/tutorial/java/annotations/predefined.html
- Java Language Specification — SuppressWarnings: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.5
- Apache Maven Compiler Plugin 3.13.0 — Compiler Plugin Documentation: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/
- Apache Maven Compiler Plugin 3.13.0 — compile parameters: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html
- Gradle — JavaCompile: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html
