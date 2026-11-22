# Cảnh báo biên dịch và chính sách coi cảnh báo là lỗi

Trình biên dịch Java không chỉ báo lỗi khiến mã nguồn không thể tạo bytecode. Nó còn có thể phát hiện những cách viết hợp lệ nhưng dễ gây lỗi, khó bảo trì hoặc có khả năng không tương thích trong tương lai. Những thông tin đó được gọi là **compiler warnings** (cảnh báo biên dịch).

Ví dụ, chương trình có thể gọi một API đã bị đánh dấu deprecated, dùng kiểu generic thô (*raw type*), ép kiểu không an toàn hoặc khai báo một lớp `Serializable` mà không có `serialVersionUID`. Trong nhiều trường hợp, compiler vẫn tạo được file `.class`, nhưng cảnh báo cho biết mã nguồn cần được xem xét.

Một dự án có thể thiết lập chính sách nghiêm ngặt: mọi cảnh báo biên dịch được xem là lỗi và build phải thất bại cho đến khi cảnh báo được xử lý. Cách này giúp ngăn cảnh báo mới tích lũy theo thời gian. Tuy nhiên, để áp dụng hiệu quả, nhóm cần hiểu nguồn phát cảnh báo, phạm vi cấu hình và cách xử lý cảnh báo có chủ đích.

## 1. Phân biệt lỗi biên dịch, cảnh báo và thông tin

Compiler phát ra các chẩn đoán (*diagnostics*) khi phân tích mã nguồn. Có thể phân biệt khái quát:

| Loại thông báo | Ý nghĩa | Kết quả biên dịch thường gặp |
|---|---|---|
| Error | Mã nguồn vi phạm quy tắc khiến compiler không thể biên dịch thành công | Không tạo được đầu ra hợp lệ cho lần biên dịch đó |
| Warning | Mã nguồn vẫn có thể hợp lệ nhưng có rủi ro hoặc cách dùng đáng xem xét | Thường vẫn tạo được bytecode nếu chưa bật chính sách fail-on-warning |
| Note/Information | Thông tin bổ sung, ví dụ ghi chú về annotation processor hoặc thao tác compiler | Thường không làm build thất bại |

Ví dụ lỗi biên dịch:

```java
public class Example {
    public static void main(String[] args) {
        int count = "five";
    }
}
```

Compiler không thể gán một `String` cho biến `int`, nên đây là lỗi.

Ví dụ cảnh báo khi dùng API deprecated:

```java
@Deprecated
class OldFormatter {
    static String format(String value) {
        return value;
    }
}

class Example {
    String render() {
        return OldFormatter.format("hello");
    }
}
```

Nếu compiler được yêu cầu phát cảnh báo deprecation, nó có thể cảnh báo khi mã sử dụng `OldFormatter`. Mã vẫn có thể biên dịch vì API chưa bị loại bỏ.

Một cảnh báo không khẳng định chương trình chắc chắn sai. Nó chỉ ra một điểm có rủi ro, một quy ước nên tuân thủ hoặc một thay đổi API cần được theo dõi. Người phát triển cần đọc nội dung và quyết định cách xử lý.

## 2. Vì sao nên quan tâm đến compiler warnings?

Cảnh báo thường xuất hiện trước khi một vấn đề trở thành lỗi nghiêm trọng. Xử lý sớm giúp giảm chi phí sửa chữa và làm cho codebase dễ nâng cấp hơn.

**Phát hiện lỗi tiềm ẩn.** Cảnh báo unchecked hoặc raw type có thể che giấu lỗi kiểu dữ liệu mà compiler không thể xác minh đầy đủ.

**Theo dõi API sắp thay đổi.** Cảnh báo deprecated cho biết API không còn được khuyến nghị và có thể bị loại bỏ trong phiên bản tương lai.

**Giữ mã nguồn rõ ràng.** Cảnh báo về tài nguyên, serialization hoặc cấu trúc điều khiển có thể giúp tránh lỗi khó phát hiện trong runtime.

**Ngăn nợ kỹ thuật tăng dần.** Nếu mỗi thay đổi mới đều thêm vài cảnh báo mà không được xử lý, sau một thời gian nhóm khó biết cảnh báo nào quan trọng và cảnh báo nào đã tồn tại từ lâu.

**Chuẩn bị cho nâng cấp JDK.** JDK mới có thể bổ sung cảnh báo hoặc thay đổi mức cảnh báo. Xử lý cảnh báo thường xuyên giúp việc nâng cấp compiler ít bất ngờ hơn.

## 3. Các nhóm cảnh báo thường gặp của javac

`javac` hỗ trợ các nhóm lint để kiểm tra những vấn đề cụ thể. Tùy phiên bản JDK, danh sách và chi tiết cảnh báo có thể khác nhau.

| Nhóm | Tình huống thường gặp | Điều cần xem xét |
|---|---|---|
| `deprecation` | Sử dụng API được đánh dấu `@Deprecated` | Tìm API thay thế hoặc xác nhận lý do tiếp tục dùng |
| `unchecked` | Thao tác generic mà compiler không thể kiểm tra an toàn | Bổ sung kiểu, kiểm tra dữ liệu hoặc giới hạn cast |
| `rawtypes` | Dùng kiểu generic mà bỏ tham số kiểu, ví dụ `List` thay vì `List<String>` | Khai báo type parameter rõ ràng |
| `serial` | Lớp serializable thiếu `serialVersionUID` hoặc có vấn đề serialization liên quan | Xác định chính sách tương thích dữ liệu đã serialize |
| `fallthrough` | Một `case` trong switch có thể rơi xuống `case` tiếp theo | Thêm `break`, `return` hoặc chú thích chủ đích |
| `cast` | Cast dư thừa hoặc có dấu hiệu không cần thiết | Loại bỏ cast hoặc kiểm tra kiểu thực tế |
| `try` | Tài nguyên hoặc cấu trúc try-with-resources có vấn đề | Đóng tài nguyên đúng cách và xem xét cấu trúc xử lý |
| `rawtypes`/`unchecked` | Dùng collection không có kiểu cụ thể hoặc cast không được kiểm tra | Dùng generic và API có kiểu an toàn |

Ví dụ raw type:

```java
import java.util.ArrayList;
import java.util.List;

class Names {
    List names = new ArrayList();

    void addName(String name) {
        names.add(name);
    }
}
```

Danh sách không chỉ rõ kiểu phần tử. Một đoạn mã khác có thể thêm đối tượng không phải `String`, sau đó việc ép kiểu khi đọc sẽ gây lỗi runtime.

Nên viết:

```java
import java.util.ArrayList;
import java.util.List;

class Names {
    private final List<String> names = new ArrayList<>();

    void addName(String name) {
        names.add(name);
    }
}
```

Khai báo generic giúp compiler kiểm tra kiểu phần tử và làm rõ ý định của mã nguồn.

## 4. Bật cảnh báo với javac

`javac` cung cấp tùy chọn `-Xlint` để bật các nhóm cảnh báo bổ sung.

### Bật tất cả cảnh báo lint

```bash
javac -Xlint:all -d out/classes src/com/example/Main.java
```

`-Xlint:all` yêu cầu compiler phát các cảnh báo lint thuộc những nhóm được phiên bản compiler hỗ trợ. Đây là cách hữu ích để xem codebase đang có những vấn đề nào trước khi áp dụng chính sách fail-on-warning.

### Chỉ bật một số nhóm

```bash
javac -Xlint:deprecation,unchecked,rawtypes -d out/classes src/com/example/Main.java
```

Lệnh trên tập trung vào việc sử dụng API deprecated, thao tác unchecked và raw type. Cách này phù hợp khi nhóm muốn áp dụng từng bước hoặc chỉ quan tâm một số nhóm cảnh báo.

### Tắt một nhóm cụ thể

Có thể kết hợp các nhóm được bật và tắt:

```bash
javac -Xlint:all,-serial -d out/classes src/com/example/Main.java
```

Ví dụ này bật các nhóm lint rồi tắt riêng nhóm `serial`. Việc tắt nhóm nên có lý do và phạm vi rõ ràng. Không nên tắt hàng loạt chỉ để build không còn hiển thị cảnh báo.

### Xem chi tiết cảnh báo

Một số cảnh báo mặc định chỉ hiển thị vị trí và thông điệp ngắn. Có thể dùng:

```bash
javac -Xlint:deprecation -Xdiags:verbose -d out/classes src/com/example/Main.java
```

`-Xdiags:verbose` yêu cầu định dạng chẩn đoán chi tiết hơn. Tùy phiên bản JDK, thông tin cụ thể có thể khác.

## 5. Coi cảnh báo là lỗi với javac

Tùy chọn `-Werror` yêu cầu compiler thất bại nếu phát sinh cảnh báo:

```bash
javac -Xlint:all -Werror -d out/classes src/com/example/Main.java
```

Với cấu hình này, cảnh báo lint cũng có thể khiến lần biên dịch thất bại. Nhóm có thể dùng nó để thiết lập quy tắc: code mới không được đưa thêm cảnh báo vào build.

Không nên bật `-Werror` một cách bất ngờ trên một codebase đang có nhiều cảnh báo cũ. Trước tiên, hãy chạy với `-Xlint:all`, thu thập danh sách cảnh báo, xử lý hoặc lập kế hoạch cho phần nợ kỹ thuật hiện hữu, rồi mới bật fail-on-warning.

### `-nowarn` không phải cách xử lý cảnh báo tốt

`-nowarn` yêu cầu compiler không phát thông báo cảnh báo. Nó có thể làm log sạch hơn nhưng cũng che khuất vấn đề. Khi nhóm muốn giữ cảnh báo hữu ích và chỉ ngăn một số nhóm cụ thể, hãy cấu hình `-Xlint` có chọn lọc hoặc sửa mã nguồn.

## 6. Xử lý cảnh báo trong mã nguồn

Thứ tự ưu tiên nên là:

1. Sửa nguyên nhân để mã nguồn không còn cảnh báo.
2. Dùng API thay thế nếu API cũ đã deprecated.
3. Bổ sung kiểu dữ liệu hoặc kiểm tra an toàn nếu cảnh báo liên quan đến generic/cast.
4. Chỉ suppress khi có lý do kỹ thuật rõ ràng và phạm vi suppress nhỏ nhất.

Ví dụ, nếu dùng API deprecated, hãy tìm API thay thế được tài liệu đề xuất. Nếu vẫn phải tương thích với thư viện cũ, có thể cô lập việc gọi API cũ trong một adapter thay vì để cảnh báo lan khắp codebase.

### Dùng `@SuppressWarnings` có phạm vi hẹp

Java cho phép suppress một số cảnh báo tại declaration:

```java
@SuppressWarnings("deprecation")
String legacyFormat(String value) {
    return OldFormatter.format(value);
}
```

Chỉ method gọi API cũ bị suppress. Các method khác vẫn chịu chính sách cảnh báo bình thường.

Với unchecked cast, cần giải thích vì sao cast an toàn:

```java
@SuppressWarnings("unchecked")
static <T> T readValue(Object value) {
    return (T) value;
}
```

Đoạn code này chỉ minh họa cú pháp. Trong thực tế, nếu không có kiểm tra hoặc hợp đồng kiểu dữ liệu đáng tin cậy, suppress không làm cast trở nên an toàn. Nên cân nhắc thiết kế API có kiểu rõ ràng hoặc kiểm tra kiểu trước khi cast.

Không nên đặt `@SuppressWarnings("all")` ở cấp package, class hoặc module chỉ để làm mất cảnh báo. Cách đó làm giảm khả năng phát hiện vấn đề mới.

## 7. Cấu hình cảnh báo trong Gradle

Với dự án dùng plugin Java, Gradle tạo các task kiểu `JavaCompile`. Có thể cấu hình compiler options cho tất cả task biên dịch Java.

### Groovy DSL

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
```

`withType(JavaCompile)` chọn các task biên dịch Java. `configureEach` cấu hình theo cơ chế lazy, phù hợp với Gradle task configuration. Hai đối số được chuyển cho `javac` khi task biên dịch thực thi.

Nếu muốn chỉ bật cảnh báo mà chưa fail build:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-Xlint:all')
}
```

Sau khi xử lý cảnh báo hiện có, thêm `-Werror` để nâng chính sách lên mức nghiêm ngặt.

### Kotlin DSL

Trong `build.gradle.kts`:

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}
```

Kotlin DSL dùng cú pháp generic của Kotlin, còn compiler arguments vẫn là tùy chọn của `javac`.

### Cấu hình theo task hoặc module

Không phải lúc nào cũng nên áp dụng chính sách giống nhau cho mọi source set. Ví dụ, dự án có mã nguồn chính, mã kiểm thử và mã được sinh tự động. Có thể cấu hình riêng:

```groovy
tasks.named('compileJava', JavaCompile) {
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}

tasks.named('compileTestJava', JavaCompile) {
    options.compilerArgs.add('-Xlint:all')
}
```

Ví dụ này áp dụng `-Werror` cho mã chính nhưng chỉ bật lint cho mã kiểm thử. Cần dùng chính sách nhất quán theo mục tiêu của tổ chức; việc cấu hình khác nhau chỉ nên phản ánh lý do thực tế như mã legacy hoặc generator chưa thể sửa.

Trong build nhiều project, cấu hình ở root không tự động áp dụng cho mọi subproject trừ khi logic được đặt trong convention plugin hoặc được cấu hình rõ cho từng project. Nên tránh giả định rằng một đoạn `tasks.withType` ở root đã điều khiển tất cả project con.

## 8. Cấu hình cảnh báo trong Maven

Maven Compiler Plugin cung cấp các tham số cấu hình compiler. Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>21</release>
                <showWarnings>true</showWarnings>
                <failOnWarning>true</failOnWarning>
                <compilerArgs>
                    <arg>-Xlint:all</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ý nghĩa:

- `release`: chọn phiên bản Java API và bytecode đích.
- `showWarnings`: yêu cầu Maven Compiler Plugin hiển thị cảnh báo compiler.
- `failOnWarning`: làm build thất bại khi compiler phát cảnh báo.
- `compilerArgs`: truyền thêm tùy chọn trực tiếp cho compiler, ở đây là `-Xlint:all`.

`failOnWarning` là tùy chọn của Maven Compiler Plugin. Có thể dùng nó để thể hiện chính sách ở cấp plugin. Một cách khác là truyền `-Werror` trực tiếp cho `javac` qua `compilerArgs`:

```xml
<compilerArgs>
    <arg>-Xlint:all</arg>
    <arg>-Werror</arg>
</compilerArgs>
```

Nên chọn một cách thể hiện chính sách fail-on-warning phù hợp với phiên bản plugin và compiler của dự án, tránh cấu hình trùng lặp không cần thiết. Khi dùng compiler không phải `javac`, cần kiểm tra tùy chọn tương ứng có được hỗ trợ hay không.

### Quản lý cấu hình Maven ở POM cha

Với Maven multi-module, có thể đặt cấu hình plugin trong `pluginManagement` của parent POM để các module con kế thừa phiên bản và cấu hình. Tuy nhiên, `pluginManagement` chủ yếu cung cấp cấu hình quản lý; plugin chỉ được thực thi trong module khi được khai báo/áp dụng theo cấu trúc build tương ứng.

Ví dụ:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>21</release>
                    <showWarnings>true</showWarnings>
                    <failOnWarning>true</failOnWarning>
                    <compilerArgs>
                        <arg>-Xlint:all</arg>
                    </compilerArgs>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Các module có thể khai báo plugin trong `<build><plugins>` để sử dụng cấu hình được quản lý. Cách tổ chức này giúp giữ version và warning policy nhất quán trong reactor.

## 9. Phân biệt cảnh báo javac với cảnh báo của Gradle

Gradle có hệ thống cảnh báo riêng. Ví dụ, Gradle có thể cảnh báo một API build script sắp bị loại bỏ, một plugin dùng API deprecated hoặc một tính năng build không còn được khuyến nghị.

Đây là cảnh báo của build tool, không phải compiler warning do `javac` phát ra.

Có thể điều khiển mức hiển thị cảnh báo Gradle bằng:

```bash
./gradlew build --warning-mode=all
```

Hoặc:

```bash
./gradlew build --warning-mode=fail
```

Các chế độ phổ biến:

| Warning mode | Hành vi |
|---|---|
| `all` | Hiển thị tất cả cảnh báo Gradle |
| `summary` | Tổng hợp cảnh báo theo mặc định thông thường |
| `none` | Không hiển thị cảnh báo Gradle |
| `fail` | Hiển thị cảnh báo và làm build thất bại nếu Gradle phát cảnh báo thuộc hệ thống warning của nó |

Có thể cấu hình trong `gradle.properties`:

```properties
org.gradle.warning.mode=all
```

`--warning-mode=fail` không thay thế `-Werror` cho compiler. Ngược lại, `-Werror` không tự làm build thất bại vì mọi cảnh báo deprecation do Gradle hoặc plugin Gradle phát ra. Nếu tổ chức muốn kiểm soát cả hai, cần cấu hình riêng cho compiler và Gradle.

## 10. Cảnh báo từ annotation processor và mã được sinh

Một số dự án dùng annotation processor để sinh mã hoặc kiểm tra source, ví dụ processor tạo metamodel, mapper hoặc mã serialization. Compiler có thể phát cảnh báo từ:

- Mã nguồn do lập trình viên viết.
- Annotation processor.
- Mã nguồn được sinh tự động.
- Tùy chọn compiler hoặc cấu hình processing.

Khi bật `-Werror`, một cảnh báo từ processor cũng có thể làm compilation thất bại nếu nó được báo như compiler warning. Vì vậy, khi build bắt đầu fail sau khi bật chính sách, hãy xác định warning đến từ file nào và thành phần nào phát ra.

Nếu mã được sinh có cảnh báo, nên xem có thể nâng cấp hoặc cấu hình generator để tạo mã sạch hơn không. Nếu chưa thể sửa ngay, có thể tách source set hoặc task để áp dụng chính sách phù hợp, nhưng cần tránh làm cho mã ứng dụng do con người viết mất kiểm soát cảnh báo.

Không nên dùng một cấu hình suppress toàn cục để che mọi cảnh báo từ generated source nếu việc đó cũng che cảnh báo của mã nguồn chính.

## 11. Chính sách fail-on-warning nên được triển khai theo giai đoạn

Một codebase lâu năm có thể có hàng trăm cảnh báo. Nếu bật `-Werror` ngay, build có thể thất bại trên diện rộng và nhóm khó phân biệt cảnh báo mới với nợ kỹ thuật cũ.

Một lộ trình thực tế:

### Giai đoạn 1: quan sát

Bật `-Xlint:all` hoặc các nhóm cảnh báo phù hợp nhưng chưa bật `-Werror`. Thu thập log trên máy phát triển và CI để biết loại cảnh báo nào xuất hiện, module nào phát ra và tần suất ra sao.

### Giai đoạn 2: lập baseline

Ghi nhận các cảnh báo hiện hữu. Có thể xử lý theo nhóm hoặc module, ưu tiên cảnh báo có nguy cơ runtime cao, API bị loại bỏ và cảnh báo liên quan đến kiểu không an toàn.

### Giai đoạn 3: ngăn cảnh báo mới

Đặt chính sách cho phần mã mới hoặc module đã được làm sạch. CI phải thất bại khi thay đổi mới đưa thêm cảnh báo vào phạm vi kiểm soát. Nếu công cụ không hỗ trợ baseline trực tiếp theo cách nhóm cần, có thể chia phạm vi compiler task hoặc dùng quy trình kiểm tra riêng.

### Giai đoạn 4: mở rộng

Khi các module đã sạch, áp dụng `-Werror` rộng hơn và thống nhất policy trong convention plugin hoặc parent POM.

### Giai đoạn 5: duy trì

Khi nâng JDK hoặc plugin, xem xét cảnh báo mới, xử lý thay đổi API và cập nhật baseline có kiểm soát. Không nên hạ warning policy chỉ vì một lần nâng cấp tạo ra cảnh báo mới mà chưa phân tích nguyên nhân.

## 12. Nên xử lý cảnh báo mới hay suppress?

Hãy phân loại cảnh báo trước khi quyết định:

| Tình huống | Hướng xử lý ưu tiên |
|---|---|
| API deprecated có API thay thế | Chuyển sang API mới |
| Raw type hoặc unchecked cast do code tự viết | Bổ sung generic, kiểm tra kiểu hoặc thay đổi API |
| Thiếu `serialVersionUID` | Xác định nhu cầu serialization và khai báo version phù hợp |
| Cảnh báo từ thư viện bên ngoài | Nâng phiên bản hoặc kiểm tra cách gọi API; không sửa code thư viện trong dependency cache |
| Cảnh báo từ generated source | Cập nhật generator hoặc cô lập source set nếu cần |
| Cảnh báo là chủ đích và không thể loại bỏ | Suppress ở phạm vi hẹp, kèm giải thích và kiểm thử |

Một suppress hợp lý nên giúp người đọc hiểu vì sao cảnh báo được chấp nhận. Ví dụ:

```java
@SuppressWarnings("unchecked") // Kiểu được kiểm tra tại boundary khi đọc dữ liệu.
Map<String, Object> asMap(Object value) {
    return (Map<String, Object>) value;
}
```

Comment không thay thế kiểm tra thực tế. Nếu dữ liệu không được xác thực trước, cast vẫn có thể sai. Nên đặt suppress càng gần thao tác gây cảnh báo càng tốt và bảo đảm có test cho điều kiện an toàn.

## 13. Không nhầm warning policy với static analysis

Compiler warnings là một lớp kiểm tra. Dự án có thể cần thêm công cụ static analysis như Checkstyle, PMD, SpotBugs hoặc Error Prone để kiểm tra quy tắc phong cách, lỗi logic tiềm ẩn và mẫu code nguy hiểm.

| Công cụ/cơ chế | Phạm vi chính |
|---|---|
| `javac -Xlint` | Các cảnh báo do Java compiler hỗ trợ |
| `javac -Werror` | Nâng compiler warnings thành lỗi biên dịch |
| Gradle warning mode | Cảnh báo do Gradle/build logic phát ra |
| Maven Compiler Plugin `failOnWarning` | Chính sách fail khi compiler phát cảnh báo trong plugin |
| Checkstyle | Quy tắc định dạng, naming và style |
| PMD | Mẫu code và một số vấn đề thiết kế/logic |
| SpotBugs | Phân tích bytecode để tìm lỗi tiềm ẩn |
| Error Prone | Kiểm tra bổ sung trong quá trình biên dịch Java |

Một build có thể sạch compiler warnings nhưng vẫn có lỗi mà static analysis phát hiện. Ngược lại, bật nhiều công cụ cùng lúc không có nghĩa tất cả cảnh báo đều có cùng mức độ nghiêm trọng. Mỗi công cụ nên có policy và cách xử lý riêng.

## 14. Tác động của JDK và compiler version

Danh sách cảnh báo phụ thuộc vào compiler đang được dùng. Nếu máy phát triển dùng JDK 17 nhưng CI dùng JDK 21, hai môi trường có thể phát ra tập cảnh báo khác nhau.

Với Gradle, cần phân biệt JVM chạy Gradle với Java toolchain dùng để biên dịch. Một Gradle daemon có thể chạy trên JDK khác với JDK compiler được toolchain chọn. Vì vậy, hãy xác định toolchain của task `JavaCompile` khi điều tra warning khác nhau.

Với Maven, kiểm tra Java home chạy Maven và cấu hình compiler/toolchain nếu dự án sử dụng Maven Toolchains. `mvn -version` cho biết JVM chạy Maven; cấu hình compiler có thể chọn một JDK khác.

Để build ổn định, nên thống nhất JDK/compiler version trong IDE, local script và CI. Dùng `--release` hoặc cấu hình `<release>` để xác định Java API và bytecode đích; lựa chọn này không tự đảm bảo mọi máy dùng cùng compiler version, vì vậy vẫn cần toolchain hoặc môi trường JDK được quản lý.

## 15. Ví dụ một lỗi xuất hiện sau khi bật `-Werror`

Giả sử trước đây build chạy thành công. Sau khi thêm:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
```

build thất bại với cảnh báo unchecked:

```text
warning: [unchecked] unchecked conversion
error: warnings found and -Werror specified
```

Nguyên nhân có thể là một method trả về collection raw type:

```java
List values() {
    return new ArrayList();
}
```

Sửa bằng cách khai báo kiểu rõ ràng:

```java
List<String> values() {
    return new ArrayList<>();
}
```

Nếu method phải giữ API cũ vì tương thích, hãy cô lập phần chuyển đổi và thêm kiểm tra. Chỉ suppress khi có cơ sở chứng minh thao tác an toàn.

Khi sửa xong, chạy lại đúng task biên dịch. Nếu warning vẫn còn, xem file và dòng mà compiler chỉ ra; có thể warning đến từ một source khác hoặc annotation processor.

## 16. Cách điều tra warning trong Gradle

Khi build fail vì compiler warning:

1. Xác định task thất bại, ví dụ `:app:compileJava` hoặc `:domain:compileTestJava`.
2. Đọc dòng cảnh báo đầu tiên, xác định category trong dấu ngoặc vuông nếu có.
3. Xác định compiler arguments đang được truyền vào task.
4. Kiểm tra JDK/toolchain thực tế.
5. Xác định warning đến từ source, generated source hay processor.
6. Sửa mã hoặc suppress có chủ đích.
7. Chạy lại task và kiểm tra các task liên quan.

Có thể dùng:

```bash
./gradlew :app:compileJava --info
```

Log `--info` có thể cung cấp thêm thông tin về task và quá trình thực thi. Với cấu hình compiler, xem `options.compilerArgs` trong build logic hoặc convention plugin áp dụng cho module.

Nếu warning xuất hiện ở nhiều module, hãy kiểm tra cấu hình tập trung trong root build hoặc convention plugin để xác định policy được áp dụng từ đâu.

## 17. Cách điều tra warning trong Maven

Với Maven, xác định module và goal compiler bị lỗi. Có thể chạy:

```bash
mvn -pl app -am -DskipTests compile
```

Lệnh trên yêu cầu Maven build module `app` cùng các module cần thiết trong reactor, dừng ở giai đoạn compile. `-DskipTests` bỏ qua thực thi test nhưng không nhất thiết bỏ qua test compilation trong mọi cấu hình; nếu chỉ cần compile mã chính, gọi goal `compile` như ví dụ.

Kiểm tra cấu hình compiler hiệu lực bằng:

```bash
mvn help:effective-pom
```

Để xác nhận compiler version và Java home của Maven:

```bash
mvn -version
```

Đọc log compiler để phân biệt cảnh báo do `javac`, cảnh báo do plugin Maven hoặc cảnh báo từ plugin khác trong lifecycle. Không nên suppress một cảnh báo compiler bằng cách tắt warning của toàn Maven build.

## 18. Chính sách cảnh báo trong dự án nhiều module

Với build nhiều module, nên xác định policy ở cấp tổ chức hoặc convention plugin thay vì để mỗi module tùy ý cấu hình.

Một chính sách có thể gồm:

- JDK/toolchain được hỗ trợ.
- Nhóm `-Xlint` được bật.
- Module nào bắt buộc `-Werror`.
- Cách xử lý source code được sinh.
- Quy tắc suppress và yêu cầu giải thích.
- Cách cập nhật baseline khi nâng JDK.
- Cách CI thực thi policy.

Ví dụ convention plugin Gradle có thể áp dụng:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
```

Các module áp dụng convention plugin sẽ nhận cùng cấu hình. Nếu module legacy chưa sẵn sàng, có thể tạo lộ trình riêng và ghi rõ phạm vi ngoại lệ, sau đó loại bỏ ngoại lệ khi codebase được làm sạch.

Không nên có nhiều cấu hình compiler rời rạc khiến cùng một source set nhận đối số mâu thuẫn. Hãy có một nơi sở hữu warning policy và kiểm tra các plugin/convention khác có đang bổ sung hoặc loại bỏ compiler argument hay không.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Mọi warning đều chứng minh chương trình sai | Warning chỉ ra rủi ro hoặc cách dùng cần xem xét; cần đọc ngữ cảnh. |
| `-Werror` bật tất cả nhóm lint | `-Werror` nâng warning thành lỗi; `-Xlint` quyết định các nhóm lint cần phát. |
| `-Xlint:all` và `-Werror` là một tùy chọn | Một tùy chọn bật lint; tùy chọn còn lại làm build thất bại khi có warning. |
| `@SuppressWarnings` sửa nguyên nhân | Nó chỉ ẩn cảnh báo ở phạm vi được đánh dấu, không làm code an toàn hơn. |
| Gradle `--warning-mode=fail` giống javac `-Werror` | Một cái kiểm soát cảnh báo của Gradle; cái kia kiểm soát compiler warnings. |
| Build fail vì warning có nghĩa dependency library phát warning | Warning có thể đến từ source của dự án, generated source hoặc annotation processor. |
| JDK mới luôn phát đúng tập warning cũ | Compiler mới có thể bổ sung hoặc thay đổi cảnh báo. |
| Bật fail-on-warning ngay là cách tốt nhất cho mọi codebase | Nên xử lý baseline và triển khai theo giai đoạn để không chặn toàn bộ phát triển. |

## 20. Checklist áp dụng warning policy

Khi thiết lập hoặc thay đổi chính sách cảnh báo, hãy xác định:

1. Compiler và JDK nào thực sự biên dịch mã nguồn?
2. Những nhóm lint nào được bật?
3. Cảnh báo nào được coi là lỗi?
4. Cấu hình áp dụng cho main source, test source và generated source ra sao?
5. Có cảnh báo cũ nào cần baseline hoặc xử lý theo lộ trình không?
6. Suppress có phạm vi hẹp và có lý do kỹ thuật không?
7. IDE, local build và CI có dùng cùng compiler/toolchain không?
8. Cảnh báo Gradle/Maven có được phân biệt với compiler warnings không?
9. Khi nâng JDK, nhóm sẽ xem xét cảnh báo mới như thế nào?

Chính sách coi cảnh báo là lỗi giúp giữ chất lượng mã nguồn khi được áp dụng nhất quán và có lộ trình. `-Xlint` giúp compiler phát hiện thêm vấn đề; `-Werror` biến cảnh báo thành điều kiện thất bại của biên dịch; Gradle và Maven cung cấp nơi cấu hình các tùy chọn đó cho toàn bộ build. Điều quan trọng là xử lý cảnh báo ở đúng nguồn, giữ ngoại lệ nhỏ và bảo đảm mọi môi trường build dùng cùng một chính sách.
