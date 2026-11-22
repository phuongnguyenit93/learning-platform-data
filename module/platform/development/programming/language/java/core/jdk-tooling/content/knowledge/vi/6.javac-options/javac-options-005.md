# Bật lint trong javac

Lint là cơ chế phân tích cảnh báo của trình biên dịch Java. Khi bật lint, javac kiểm tra thêm những mẫu mã có thể gây lỗi, khó bảo trì hoặc che giấu vấn đề, ngay cả khi mã nguồn vẫn hợp lệ về cú pháp và kiểu dữ liệu. Các cảnh báo có thể chỉ ra việc dùng raw generic type, gọi API đã deprecated, phép ép kiểu thừa, switch có khả năng fall-through, hoặc cấu hình classpath có vấn đề.

Lint giúp nhóm phát hiện rủi ro ngay ở bước biên dịch. Nó đặc biệt hữu ích trong code review, dự án nhiều thành viên và pipeline CI, nơi một cảnh báo nhỏ nếu bị bỏ qua lâu ngày có thể trở thành lỗi khó truy tìm.

## 1. Lint warning khác compile error như thế nào?

Trình biên dịch Java kiểm tra nhiều quy tắc ở các mức khác nhau:

- **Compile error:** mã nguồn vi phạm quy tắc bắt buộc của ngôn ngữ hoặc không thể phân giải kiểu/thành viên. Javac không thể hoàn thành lần biên dịch bình thường.
- **Lint warning:** mã vẫn có thể biên dịch, nhưng javac nhận thấy một cấu trúc đáng ngờ hoặc có nguy cơ gây lỗi. Cảnh báo giúp lập trình viên xem xét và quyết định có cần sửa hay không.
- **Runtime error:** vấn đề chỉ xuất hiện khi chương trình chạy, chẳng hạn dữ liệu không hợp lệ, thiếu cấu hình hoặc lỗi logic. Lint không thể phát hiện mọi lỗi runtime.

Ví dụ, dùng raw type với collection vẫn hợp lệ trong Java vì ngôn ngữ duy trì khả năng tương thích với mã Java cũ. Tuy nhiên, cách dùng này làm mất kiểm tra kiểu generic và có thể dẫn tới ClassCastException. Lint có thể cảnh báo để lập trình viên chuyển sang kiểu generic cụ thể.

Mặc định, nhiều cảnh báo lint không làm javac thất bại. Nếu muốn coi warning như lỗi build, có thể kết hợp tùy chọn -Werror.

## 2. Bật lint bằng -Xlint

Tùy chọn chính là:

~~~bash
javac -Xlint SourceFile.java
~~~

Để bật các nhóm lint:

~~~bash
javac -Xlint:all SourceFile.java
~~~

- **-Xlint** bật các cảnh báo lint được khuyến nghị.
- **-Xlint:all** bật toàn bộ các nhóm lint mà phiên bản javac hiện tại hỗ trợ.
- **-Xlint:<category>** bật một nhóm cảnh báo cụ thể.
- **-Xlint:-<category>** tắt một nhóm cảnh báo cụ thể.
- **-Xlint:none** tắt các nhóm lint.

Ví dụ chỉ bật cảnh báo về generic không an toàn:

~~~bash
javac -Xlint:unchecked SourceFile.java
~~~

Bật cả raw type và unchecked operation:

~~~bash
javac -Xlint:rawtypes,unchecked SourceFile.java
~~~

Bật hầu hết các cảnh báo nhưng loại trừ nhóm serial:

~~~bash
javac -Xlint:all,-serial SourceFile.java
~~~

Tên category và phạm vi cảnh báo có thể thay đổi giữa các phiên bản JDK. Để xem danh sách được hỗ trợ bởi javac đang cài trên máy:

~~~bash
javac --help-lint
~~~

Không nên giả định mọi máy lập trình viên và CI đều có cùng danh sách cảnh báo nếu chúng dùng các phiên bản JDK khác nhau.

## 3. Những nhóm lint thường gặp

Các nhóm dưới đây thường hữu ích khi làm việc với mã Java:

| Category | Cảnh báo về điều gì? |
|---|---|
| deprecation | Sử dụng API đã được đánh dấu deprecated. |
| removal | Sử dụng API đã được đánh dấu dự kiến loại bỏ. |
| unchecked | Phép chuyển đổi, lời gọi hoặc thao tác generic không được kiểm tra kiểu đầy đủ tại compile time. |
| rawtypes | Dùng kiểu generic mà không cung cấp type argument, ví dụ List thay vì List<String>. |
| serial | Các vấn đề liên quan tới serialization, chẳng hạn lớp Serializable thiếu serialVersionUID. |
| cast | Phép ép kiểu có thể thừa hoặc không cần thiết. |
| fallthrough | Nhánh switch có thể rơi tiếp sang case kế tiếp mà không có break/yield phù hợp. |
| finally | Một số cấu trúc finally đáng ngờ, có thể làm mất luồng điều khiển dự kiến. |
| static | Truy cập thành viên static thông qua biểu thức đối tượng thay vì tên lớp. |
| try | Một số vấn đề liên quan tới try-with-resources hoặc tài nguyên được khai báo nhưng không được sử dụng như dự kiến. |
| varargs | Cách dùng varargs có thể không an toàn, đặc biệt với generic varargs. |
| path | Thành phần đường dẫn tìm lớp hoặc mã nguồn có vấn đề. |
| processing | Cảnh báo liên quan tới annotation processing. |

Đây là những nhóm phổ biến để bắt đầu. Danh sách chính xác và mô tả chi tiết phụ thuộc JDK; dùng javac --help-lint để xem thông tin của phiên bản hiện tại.

## 4. Ví dụ: raw type và unchecked warning

Generic giúp trình biên dịch kiểm tra kiểu phần tử của collection. Khi bỏ type argument, mã sử dụng raw type và mất một phần kiểm tra kiểu.

Tạo tệp RawTypeWarning.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawTypeWarning {
    public static void main(String[] args) {
        List names = new ArrayList();
        names.add("Linh");

        String first = (String) names.get(0);
        System.out.println(first);
    }
}
~~~

Biên dịch với lint:

~~~bash
javac -Xlint:rawtypes,unchecked RawTypeWarning.java
~~~

Javac có thể cảnh báo tại khai báo List và ArrayList vì thiếu type argument, đồng thời cảnh báo lời gọi add trên raw type vì thao tác không được kiểm tra kiểu generic đầy đủ. Cách trình bày warning, vị trí dòng và nội dung chi tiết phụ thuộc phiên bản JDK.

Chương trình vẫn có thể chạy và in:

~~~text
Linh
~~~

Nhưng kiểu dữ liệu không được kiểm tra đầy đủ. Nếu vô tình thêm một đối tượng không phải String vào collection rồi ép kiểu sang String, chương trình có thể lỗi lúc chạy.

### Cách sửa bằng generic

Dùng type argument để khai báo kiểu phần tử:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericListDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Linh");

        String first = names.get(0);
        System.out.println(first);
    }
}
~~~

Biên dịch với tất cả lint và coi warning là lỗi:

~~~bash
javac -Xlint:all -Werror GenericListDemo.java
java GenericListDemo
~~~

Output:

~~~text
Linh
~~~

Ví dụ này biên dịch sạch trên JDK 17+ mà không cần ép kiểu thủ công. Nếu mã nguồn có warning thuộc các nhóm lint đang bật, -Werror sẽ làm lần biên dịch thất bại.

## 5. Kết hợp -Xlint với -Werror

Tùy chọn -Werror yêu cầu javac kết thúc với lỗi khi phát hiện warning. Khi dùng cùng lint, nhóm có thể đặt quy tắc: mọi warning lint mới đều phải được xử lý trước khi build thành công.

~~~bash
javac -Xlint:all -Werror -d out src/main/java/com/example/Main.java
~~~

Ý nghĩa:

- -Xlint:all bật các nhóm cảnh báo.
- -Werror biến warning thành điều kiện làm build thất bại.
- -d out chọn thư mục chứa bytecode đầu ra.

Nếu out chưa tồn tại, hãy tạo thư mục trước khi chạy javac:

~~~bash
mkdir -p out
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Sau đó chạy lệnh javac tương ứng. Với dự án nhiều tệp, source path, classpath hoặc module path vẫn cần cấu hình riêng; -Xlint không tự tìm dependency thay cho các tùy chọn đó.

### Khi nào nên dùng -Werror?

- Trong thư viện dùng chung, nơi API và cảnh báo ảnh hưởng nhiều dự án.
- Trong CI, để ngăn warning mới lọt vào nhánh chính.
- Trong dự án mới, khi nhóm có thể giữ mã nguồn sạch ngay từ đầu.
- Khi nâng cấp JDK, sau khi đã rà soát các warning mới do compiler thay đổi.

Không nên bật -Werror một cách bất ngờ cho một codebase cũ đang có nhiều warning chưa xử lý. Khi đó, một thay đổi cấu hình có thể làm toàn bộ build thất bại dù không có lỗi chức năng mới. Nên bật lint, thu thập warning, xử lý theo nhóm và chỉ chuyển sang -Werror khi baseline đã sạch hoặc nhóm đã có kế hoạch kiểm soát rõ ràng.

## 6. Chọn và loại trừ từng category

Không phải dự án nào cũng muốn bật mọi category ngay lập tức. Có thể bật một nhóm cụ thể để điều tra:

~~~bash
javac -Xlint:deprecation -d out src/main/java/com/example/Main.java
~~~

Lệnh này tập trung vào việc sử dụng API deprecated.

Nếu đã bật tất cả nhưng cần tạm loại trừ một nhóm đã được đánh giá:

~~~bash
javac -Xlint:all,-serial -d out src/main/java/com/example/Main.java
~~~

Có thể tắt riêng unchecked:

~~~bash
javac -Xlint:all,-unchecked -d out src/main/java/com/example/Main.java
~~~

Cách loại trừ chỉ nên dùng khi có lý do rõ ràng, chẳng hạn một phần mã tương thích cũ đang chờ được sửa. Ghi lại lý do và phạm vi để nhóm có thể xem xét lại. Tắt warning diện rộng sẽ làm mất tín hiệu hữu ích trong các lần build sau.

## 7. Dùng @SuppressWarnings đúng phạm vi

Đôi khi warning là có chủ đích hoặc không thể loại bỏ ngay, ví dụ khi tích hợp với API cũ không dùng generic. Java cung cấp annotation SuppressWarnings để bỏ qua một số nhóm cảnh báo tại phạm vi cụ thể.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LegacyAdapter {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List legacyValues() {
        List values = new ArrayList();
        values.add("Linh");
        return values;
    }

    public static void main(String[] args) {
        System.out.println(legacyValues().get(0));
    }
}
~~~

Annotation trên phương thức yêu cầu compiler bỏ qua các warning rawtypes và unchecked trong phạm vi phương thức đó. Nó không làm mã an toàn hơn và không thay thế việc hiểu vì sao warning xuất hiện.

Nguyên tắc sử dụng:

1. Ưu tiên sửa nguyên nhân, chẳng hạn thêm generic type thay vì suppress.
2. Nếu bắt buộc suppress, đặt annotation ở phạm vi nhỏ nhất có thể.
3. Chỉ nêu category thực sự cần suppress, không suppress mọi warning.
4. Viết comment giải thích vì sao thao tác không thể tránh và điều kiện an toàn được bảo đảm.
5. Kiểm tra lại khi nâng cấp API hoặc thay đổi cấu trúc mã.

Ví dụ với một phép chuyển đổi unchecked có chủ đích:

~~~java
@SuppressWarnings("unchecked")
static <T> T castLegacyValue(Object value) {
    return (T) value;
}
~~~

Đây chỉ là minh họa cho vị trí annotation. Phép ép kiểu vẫn có thể gây ClassCastException nếu kiểu thực tế không tương thích. Người gọi phải bảo đảm hợp đồng kiểu dữ liệu; annotation chỉ tắt cảnh báo compiler tại phạm vi đã đánh dấu.

Không nên đặt @SuppressWarnings("unchecked") ở cấp toàn bộ package hoặc toàn dự án chỉ để build qua. Làm như vậy khiến warning mới bị che khuất và khó tìm nguyên nhân hơn.

## 8. Một số warning khác và cách xử lý

### Deprecated API

Khi một API được đánh dấu deprecated, compiler có thể cảnh báo rằng mã nguồn đang dùng API cũ. API đó vẫn có thể hoạt động, nhưng nhà phát triển nên tìm phương án thay thế được tài liệu hóa.

~~~bash
javac -Xlint:deprecation OldClient.java
~~~

Nếu API còn được đánh dấu for removal, có thể bật thêm:

~~~bash
javac -Xlint:removal OldClient.java
~~~

Không nên suppress warning chỉ vì muốn output build sạch. Hãy kiểm tra Javadoc của API, phiên bản thay thế và thời điểm dự kiến loại bỏ.

### Serializable và serialVersionUID

Một lớp triển khai Serializable thường nên khai báo serialVersionUID rõ ràng để kiểm soát tương thích serialization giữa các phiên bản lớp.

~~~java
import java.io.Serializable;

public class UserRecord implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;

    public UserRecord(String name) {
        this.name = name;
    }
}
~~~

Dùng lint serial để kiểm tra nhóm cảnh báo serialization:

~~~bash
javac -Xlint:serial UserRecord.java
~~~

Giá trị serialVersionUID phải được quản lý theo chiến lược tương thích dữ liệu của ứng dụng; không nên sao chép một giá trị tùy tiện mà không xem xét thay đổi cấu trúc lớp.

### Switch fall-through

Một switch truyền thống có thể chạy tiếp sang case kế tiếp nếu không có break hoặc câu lệnh kết thúc phù hợp. Nếu đây là chủ ý, hãy làm cho ý định rõ ràng bằng comment hoặc cấu trúc switch phù hợp.

~~~java
public class SwitchDemo {
    public static void main(String[] args) {
        int day = 6;

        switch (day) {
            case 6:
            case 7:
                System.out.println("Weekend");
                break;
            default:
                System.out.println("Weekday");
        }
    }
}
~~~

Hai nhãn case 6 và case 7 cùng thực hiện một nhánh. Đây là cách gom case hợp lệ, không phải lỗi fall-through vô tình. Nếu một case có xử lý riêng rồi để luồng rơi tiếp sang case khác, hãy kiểm tra kỹ và dùng break, return hoặc cấu trúc switch expression phù hợp.

## 9. Đưa lint vào Maven

Với dự án Maven, có thể cấu hình Maven Compiler Plugin để truyền tùy chọn cho javac:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Đặt cấu hình trong phần build/plugins của pom.xml. Phiên bản plugin và cấu hình release/toolchain cần được quản lý riêng theo chuẩn dự án. Khi Maven chạy, plugin biên dịch sẽ truyền các compilerArgs tới javac nếu đang dùng compiler theo cơ chế tương ứng.

Có thể chạy build:

~~~bash
mvn clean compile
~~~

Nếu warning được bật và -Werror được áp dụng, warning có thể làm compile goal thất bại. Hãy kiểm tra log Maven để phân biệt warning do javac, warning do plugin và lỗi ở các goal khác.

## 10. Đưa lint vào Gradle

Với Gradle Groovy DSL, cấu hình JavaCompile tasks trong build.gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
~~~

Nếu dự án có nhiều source set hoặc module, cấu hình trên áp dụng cho các task biên dịch Java tương ứng. Có thể kiểm tra task bằng:

~~~bash
./gradlew compileJava
~~~

Trên Windows:

~~~powershell
.\gradlew.bat compileJava
~~~

Đảm bảo Gradle chạy bằng JDK tương thích với phiên bản Gradle của dự án. Toolchain có thể chọn JDK biên dịch riêng; việc chọn toolchain và việc bật lint là hai cấu hình khác nhau.

## 11. Chiến lược áp dụng lint trong nhóm và CI

Một quy trình thực tế có thể triển khai theo từng bước:

1. **Kiểm tra JDK:** thống nhất phiên bản JDK dùng cho máy phát triển và CI, vì category và nội dung warning có thể thay đổi theo phiên bản compiler.
2. **Bật lint:** bắt đầu với -Xlint:all hoặc những category quan trọng đối với dự án.
3. **Thu thập warning:** phân loại warning theo mức độ, package, module hoặc người phụ trách.
4. **Sửa nguyên nhân:** ưu tiên type safety, API mới, quản lý tài nguyên và luồng điều khiển rõ ràng.
5. **Suppress có kiểm soát:** chỉ dùng khi có lý do kỹ thuật và phạm vi hẹp.
6. **Bật -Werror:** khi baseline đã đủ sạch, để warning mới làm CI thất bại.
7. **Duy trì:** xem warning là một phần của review và kiểm tra lại khi nâng cấp JDK.

Một cảnh báo mới xuất hiện sau khi nâng cấp JDK chưa chắc do mã nguồn vừa thay đổi. Compiler mới có thể bổ sung category hoặc cải thiện khả năng phát hiện. Hãy đọc nội dung warning, xác định API/cấu trúc liên quan và kiểm tra ghi chú phát hành của JDK trước khi quyết định sửa hoặc suppress.

Không nên tùy tiện thêm -Werror vào một module mà không kiểm tra các module phụ thuộc, annotation processor hoặc generated source. Các nguồn mã được sinh tự động cũng có thể tạo warning. Cần xác định warning xuất phát từ mã do nhóm viết, mã sinh tự động hay công cụ bên ngoài rồi chọn cách xử lý phù hợp.

## 12. Lỗi và nhầm lẫn thường gặp

| Nhầm lẫn hoặc hiện tượng | Giải thích và cách xử lý |
|---|---|
| Bật -Xlint nhưng không thấy warning. | Có thể mã không kích hoạt category đang bật, hoặc compiler không phát hiện vấn đề đó. Dùng -Xlint:all và kiểm tra bằng ví dụ có warning. |
| -Xlint làm build thất bại. | Thường do kết hợp -Werror hoặc build tool cấu hình warning thành lỗi. Kiểm tra toàn bộ compilerArgs. |
| Dùng -Xlint:unchecked nhưng không thấy raw type warning. | rawtypes là category riêng. Dùng -Xlint:rawtypes,unchecked hoặc -Xlint:all. |
| SuppressWarnings làm mã an toàn hơn. | Annotation chỉ ẩn warning; không thêm kiểm tra runtime hoặc bảo đảm type safety. |
| Warning biến mất sau khi nâng cấp JDK. | Compiler có thể thay đổi category hoặc cách phát hiện. Xác minh phiên bản và danh sách lint hiện tại. |
| Build cũ thất bại ngay sau khi thêm -Werror. | Codebase có thể đang có warning tồn tại từ trước. Thu thập và xử lý baseline trước khi áp dụng quy tắc nghiêm ngặt. |
| IDE không hiển thị warning giống CI. | IDE có thể dùng compiler, JDK hoặc inspection riêng. Kiểm tra build chính thức bằng javac/Maven/Gradle trong CI. |

## 13. Checklist trước khi bật lint bắt buộc

- Xác định JDK và phiên bản compiler đang dùng.
- Dùng javac --help-lint để xem category được hỗ trợ.
- Bật -Xlint:all hoặc chọn category phù hợp.
- Xem warning được ghi trên standard error và xác định tệp/dòng liên quan.
- Sửa warning bằng cách cải thiện mã nguồn trước khi suppress.
- Nếu cần suppress, dùng category cụ thể và phạm vi hẹp.
- Chạy build sạch sau khi sửa.
- Chỉ bật -Werror khi warning baseline đã được xử lý hoặc có quy trình chấp nhận rõ ràng.
- Đảm bảo IDE, Maven/Gradle và CI sử dụng cấu hình tương thích.
- Kiểm tra lại warning sau mỗi lần nâng cấp JDK hoặc annotation processor.

Lint làm javac trở thành một lớp kiểm tra chất lượng ngay trong quá trình biên dịch. Bật đúng category giúp phát hiện sớm mã dễ lỗi, còn -Werror biến tiêu chuẩn đó thành quy tắc có thể thực thi trong build. Kết hợp với generic type rõ ràng, suppression có kiểm soát và cấu hình nhất quán giữa IDE với CI, nhóm có thể duy trì mã Java an toàn và dễ bảo trì hơn.
