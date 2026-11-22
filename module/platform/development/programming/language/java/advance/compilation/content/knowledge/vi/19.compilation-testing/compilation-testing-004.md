# Kiểm tra cảnh báo, `-Werror` và phạm vi `@SuppressWarnings` trong Java

## 1. Vai trò của cảnh báo trong kiểm thử biên dịch

Trình biên dịch Java `javac` không chỉ kiểm tra cú pháp và kiểu để quyết định mã có biên dịch được hay không. Nó còn phát ra **cảnh báo** (*warning*) khi phát hiện những trường hợp mã vẫn hợp lệ nhưng có rủi ro: chuyển kiểu generic không được kiểm tra đầy đủ, dùng raw type, gọi API đã lỗi thời, xử lý tài nguyên đáng ngờ hoặc thao tác có thể gây hiểu nhầm.

Trong kiểm thử biên dịch, ta cần kiểm tra cả ba kết quả:

- **Lỗi biên dịch (error):** mã không đáp ứng quy tắc ngôn ngữ hoặc điều kiện compile; `javac` báo thất bại.
- **Cảnh báo (warning):** mã có thể được biên dịch, nhưng cần xem xét rủi ro hoặc quyết định tương thích.
- **Thông báo (note):** lời nhắc hoặc chi tiết bổ sung, ví dụ nhắc dùng `-Xlint:unchecked` để xem cảnh báo cụ thể. Đừng mặc định một dòng bắt đầu bằng `Note:` là một warning được `-Werror` nâng thành lỗi.

Ví dụ `List<String> names = new ArrayList();` có thể biên dịch, nhưng phía bên phải sử dụng kiểu thô `ArrayList`, bỏ mất thông tin tham số kiểu. Cảnh báo về raw type và unchecked conversion giúp phát hiện vị trí cần sửa trước khi lỗi kiểu dữ liệu chỉ xuất hiện muộn hơn trong lúc chạy.

Mục tiêu của quy trình kiểm thử biên dịch là **phát hiện, phân loại, sửa và quản lý cảnh báo một cách có chủ đích**. Không nên xóa cảnh báo hàng loạt chỉ để build có màu xanh; ngược lại, không phải mọi warning đều chứng minh chương trình sai ngay lúc chạy.

## 2. Ba công cụ chính: `-Xlint`, `-Werror`, `@SuppressWarnings`

| Công cụ | Phạm vi tác động | Mục đích | Điểm cần nhớ |
| --- | --- | --- | --- |
| `-Xlint` hoặc `-Xlint:<key>` | Một lần gọi `javac` | Bật các nhóm cảnh báo được chỉ định | Không tự biến warning thành error |
| `-Werror` | Một lần gọi `javac` | Cho biên dịch thất bại khi có warning phát sinh | Không tự động bật tất cả nhóm `-Xlint` |
| `@SuppressWarnings("key")` | Khai báo/phần mã được annotation bao phủ | Giấu đúng nhóm warning được hỗ trợ tại phạm vi đó | Không sửa nguyên nhân; không thay đổi hành vi runtime |

Lệnh kiểm tra cụ thể:

```powershell
javac --help-lint
javac -Xlint:all -d out WarningDemo.java
javac -Xlint:unchecked,rawtypes -d out WarningDemo.java
javac -Xlint:all -Werror -d out WarningDemo.java
```

`--help-lint` hiển thị danh sách khóa hỗ trợ bởi **JDK đang dùng**, rất hữu ích vì các khóa và hành vi cảnh báo có thể thay đổi theo phiên bản javac. `-d out` chỉ định nơi chứa `.class`; hãy tạo thư mục `out` trước hoặc bảo đảm parent output hợp lệ theo môi trường của bạn.

**Quy tắc quan trọng:** `-Xlint` quyết định loại chẩn đoán nào được bật; `-Werror` quyết định warning đã được phát ra sẽ làm bước compile thất bại. Hai tùy chọn bổ sung cho nhau. Ví dụ `-Werror` đứng một mình không bảo đảm phát hiện `rawtypes` hoặc `unchecked` nếu trình biên dịch không đang bật những nhóm cảnh báo đó.

## 3. Đọc và chọn nhóm `-Xlint`

Một số nhóm thường gặp khi biên dịch mã Java:

| Khóa | Cảnh báo ví dụ | Hướng xử lý thường ưu tiên |
| --- | --- | --- |
| `unchecked` | Cast/chuyển đổi generic không được kiểm chứng đầy đủ | Sửa kiểu, kiểm tra dữ liệu hoặc cô lập ranh giới cast |
| `rawtypes` | Dùng `List` thay cho `List<String>` / `List<?>` | Dùng generic có tham số kiểu |
| `deprecation` | Gọi API `@Deprecated` thông thường | Chuyển sang API thay thế và kiểm thử |
| `removal` | Gọi API `@Deprecated(forRemoval = true)` | Lên kế hoạch loại bỏ phụ thuộc sớm |
| `serial` | Lớp tuần tự hóa không khai báo `serialVersionUID` khi phù hợp | Xác định hợp đồng serialization |
| `fallthrough` | Một nhánh `switch` có khả năng rơi sang nhánh khác | Làm rõ luồng điều khiển |
| `cast` | Ép kiểu dư thừa | Bỏ ép kiểu nếu không có ý nghĩa |
| `static` | Truy cập thành viên static bằng tham chiếu instance | Sử dụng tên lớp |
| `try` | Vấn đề liên quan `try-with-resources` | Kiểm tra vòng đời đóng tài nguyên |
| `path` | Thành phần đường dẫn compile không hợp lệ | Sửa classpath/module path và cấu hình build |

Không phải mọi khóa trên đều được bật mặc định. Ví dụ có những cảnh báo deprecation hoặc unchecked chỉ hiện chi tiết khi yêu cầu `-Xlint` tương ứng, trong khi cảnh báo removal có thể được bật sẵn trên JDK hiện đại.

Cú pháp thông dụng:

```powershell
# Bật tất cả các nhóm được javac hỗ trợ
javac -Xlint:all -d out WarningDemo.java

# Chỉ yêu cầu hai nhóm liên quan đến generics
javac -Xlint:unchecked,rawtypes -d out WarningDemo.java

# Bật toàn bộ rồi bỏ nhóm serial khỏi lần compile này
javac -Xlint:all,-serial -d out WarningDemo.java

# Xem cảnh báo và thất bại nếu phát sinh warning
javac -Xlint:all -Werror -d out WarningDemo.java
```

Việc tắt một nhóm ở dòng lệnh áp dụng cho **tất cả nguồn của lượt biên dịch ấy**. Nó khác với suppression cục bộ, nơi ta giữ nguyên cấu hình kiểm tra cho các vị trí khác trong dự án.

Các cảnh báo do Java compiler phát ra không phải toàn bộ công cụ kiểm thử tĩnh. `-Xlint:all` không thay thế phân tích NullPointerException, kiểm tra style, security analysis hoặc unit/integration tests từ công cụ chuyên biệt.

## 4. Thí nghiệm 1: cảnh báo trở thành lỗi build

Ví dụ sau chạy độc lập với Java 17 trở lên, không cần dependency bên ngoài.

**Tệp `WarningDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;

public class WarningDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList();
        words.add("Java");
        System.out.println(words.get(0));
    }
}
```

Trên PowerShell, ở thư mục chứa tệp:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -Xlint:rawtypes,unchecked -d out WarningDemo.java
java -cp out WarningDemo
```

Với OpenJDK 21, `javac` nêu hai nhóm cảnh báo tại dòng khởi tạo `words`: `[rawtypes]` cho `new ArrayList()` và `[unchecked]` cho việc gán kết quả raw type vào `List<String>`. Dạng trình bày, số dòng và phần giải thích có thể khác theo JDK; ý nghĩa chẩn đoán là ổn định.

Sau lần compile không có `-Werror`, chương trình in:

```text
Java
```

Bây giờ thử:

```powershell
javac -Xlint:rawtypes,unchecked -Werror -d out WarningDemo.java
```

Với cùng mã nguồn và JDK 21, compiler phát sinh hai warning và **trả trạng thái thất bại (exit code khác 0)**. Phần chẩn đoán có dòng tương tự:

```text
error: warnings found and -Werror specified
1 error
2 warnings
```

Không nhầm lỗi này với việc Java không chấp nhận generic syntax: nguồn vẫn hợp lệ về mặt ngôn ngữ, nhưng chính sách build yêu cầu không còn warning. Không nên dựa vào `.class` cũ có thể còn trong `out` sau lệnh thất bại để kết luận build đã thành công.

### Sửa nguyên nhân thay vì giấu cảnh báo

Thay dòng khởi tạo trong `WarningDemo.java` bằng:

```java
List<String> words = new ArrayList<>();
```

Dấu kim cương `<>` giữ thông tin tham số kiểu; `javac` có thể suy luận `String` từ bên trái phép gán. Khi phần còn lại giữ nguyên, chạy lại:

```powershell
javac -Xlint:all -Werror -d out WarningDemo.java
java -cp out WarningDemo
```

Kết quả stdout vẫn là:

```text
Java
```

Lần này compile thành công mà không cần `@SuppressWarnings`, bởi vì đã giải quyết cách dùng raw type/unchecked conversion. Đây là kết quả nên ưu tiên trong code có thể sửa được.

## 5. `@SuppressWarnings` hoạt động như thế nào?

`@SuppressWarnings` là annotation chuẩn Java dùng để yêu cầu compiler bỏ qua **loại cảnh báo được nêu tên** phát sinh bên trong khai báo được đánh dấu. Nó có `RetentionPolicy.SOURCE`: phục vụ quá trình biên dịch, không phải cờ cấu hình runtime và không làm JVM tự cho phép một cast không an toàn.

Ví dụ cú pháp:

```java
@SuppressWarnings("unchecked")
@SuppressWarnings({"unchecked", "rawtypes"})
```

Hai dòng trên là **hai hình thức minh họa riêng**, không đặt cạnh nhau trên cùng một khai báo. Một annotation có thể nhận một chuỗi hoặc một mảng chuỗi; chỉ dùng các khóa cần thiết. Ví dụ `@SuppressWarnings({"unchecked", "rawtypes"})` che cả hai loại warning tại cùng phạm vi, nhưng không đồng nghĩa đã bảo đảm an toàn kiểu.

Theo đặc tả, suppression tác động lên phần khai báo được annotation và các thành phần chứa bên trong phần khai báo đó. Một annotation đặt ở lớp có thể ảnh hưởng đến toàn bộ các phương thức trong lớp, trong khi annotation đặt trên khai báo biến cục bộ chỉ xử lý một vị trí nhỏ. Khi suppression lồng nhau, các nhóm warning được suppression của phần bao ngoài vẫn áp dụng cho thành phần bên trong.

**Nguyên tắc phạm vi hẹp:** chỉ annotate đúng khai báo nhỏ nhất có thể cô lập chỗ tạo warning. Nếu chỉ một cast cần kiểm soát, đặt annotation trên biến nhận kết quả cast hoặc một helper riêng có tiền điều kiện rõ ràng. Tránh che cả lớp hoặc package chỉ vì một dòng cũ.

### Phạm vi ví dụ

```java
@SuppressWarnings("unchecked")
class WholeClass {
    // Phạm vi rộng: mọi khai báo bên trong lớp có thể hưởng suppression.
}
```

Đây là **mã minh họa phạm vi**, không phải lời khuyên áp dụng toàn lớp. Phương án thường tốt hơn:

```java
class NarrowScope {
    @SuppressWarnings("unchecked")
    static <T> T convert(Object raw) {
        return (T) raw;
    }
}
```

Đoạn `NarrowScope` chỉ minh họa nơi đặt annotation; bản thân cast generic chưa được kiểm tra vẫn có rủi ro tại điểm sử dụng. Không coi helper này là một cách chuyển kiểu an toàn. Ví dụ kế tiếp cho thấy cách thêm kiểm tra runtime trước cast.

## 6. Thí nghiệm 2: cô lập một unchecked cast đã kiểm tra dữ liệu

Trong môi trường legacy hoặc tích hợp API trả `Object`, đôi khi compiler không thể chứng minh một giá trị là `List<String>` vì *type erasure*: tại runtime, generic type argument `String` không được lưu để cast trực tiếp có thể kiểm tra từng phần tử.

Có thể xử lý bằng cách xác minh các phần tử trước, rồi giới hạn suppression vào cast duy nhất.

**Tệp `CheckedBoundary.java`:**

```java
import java.util.List;

public class CheckedBoundary {
    public static List<String> requireStrings(Object value) {
        if (!(value instanceof List<?> items)) {
            throw new IllegalArgumentException("Expected a list");
        }

        for (Object item : items) {
            if (!(item instanceof String)) {
                throw new IllegalArgumentException("Expected strings");
            }
        }

        @SuppressWarnings("unchecked")
        List<String> typed = (List<String>) items;
        return typed;
    }

    public static void main(String[] args) {
        System.out.println(requireStrings(List.of("alpha", "beta")).get(1));
    }
}
```

Chạy:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -Xlint:all -Werror -d out CheckedBoundary.java
java -cp out CheckedBoundary
```

Kết quả stdout:

```text
beta
```

Mã trên đã được đối chiếu với `javac` và `java` 21: compile với `-Xlint:all -Werror` thành công, và chương trình in `beta`.

Giải thích:

1. `instanceof List<?>` xác nhận đối tượng là một `List` mà không dùng raw type.
2. Vòng lặp kiểm tra mọi phần tử đều là `String`. Nếu danh sách có phần tử không đúng kiểu, phương thức ném `IllegalArgumentException` trước cast.
3. Phép cast `(List<String>) items` vẫn bị Java coi là *unchecked*, vì JVM không thể tự kiểm tra `String` trong tham số generic ngay tại phép cast.
4. `@SuppressWarnings("unchecked")` đặt trên biến `typed` làm ẩn warning chỉ tại khai báo này. Những warning không liên quan ở phương thức/lớp vẫn có thể xuất hiện.
5. Hàm trả về cùng đối tượng danh sách đã kiểm tra; nếu dữ liệu là danh sách có thể bị thay đổi bởi code khác sau kiểm tra, việc bảo đảm về kiểu không còn tuyệt đối theo thời gian. Khi cần bất biến hoặc cô lập alias, có thể tạo danh sách mới sau khi đã kiểm tra các phần tử.

Đây là một suppression có lập luận kỹ thuật cụ thể. Nếu thay vòng lặp kiểm tra bằng cast trần `(List<String>) value`, việc thêm annotation chỉ ẩn triệu chứng và có thể để lỗi `ClassCastException` xuất hiện muộn khi đọc phần tử sai kiểu.

## 7. Phân biệt `deprecation` và `removal`

Hai nhóm này liên quan nhưng **không đồng nhất**:

- `@Deprecated(forRemoval = false)` (hoặc `@Deprecated` thông thường) biểu thị API không còn được khuyến nghị; cảnh báo thuộc nhóm `deprecation`.
- `@Deprecated(forRemoval = true)` biểu thị API dự kiến có thể bị xóa trong tương lai; cảnh báo thuộc nhóm `removal`, cần mức ưu tiên xử lý cao hơn.

Đối với Java 21, `-Xlint:deprecation` và `-Xlint:removal` là hai cờ độc lập. `-Xlint:removal` nằm trong các nhóm được bật mặc định; `-Xlint:all` bật cả hai.

Nếu thực sự cần sử dụng API đã deprecated tại một điểm tích hợp chưa thể nâng cấp, các hình thức phù hợp là:

```java
@SuppressWarnings("deprecation")
// Khai báo sử dụng API deprecated thông thường.

@SuppressWarnings("removal")
// Khai báo sử dụng API đã đánh dấu forRemoval=true.

@SuppressWarnings({"deprecation", "removal"})
// Khai báo cần xử lý cả hai nhóm.
```

Ba đoạn trên chỉ minh họa annotation/khóa và **chưa phải chương trình độc lập**; khi áp dụng cần đặt annotation ngay trước một khai báo hợp lệ. Đặc biệt, `@SuppressWarnings("deprecation")` **không** thay cho `@SuppressWarnings("removal")`, và việc dùng suppression không ngăn API bị xóa trong JDK/thư viện mới.

Nên ghi rõ lý do tương thích, phương án thay thế và thời điểm dự kiến bỏ suppression. Với API đánh dấu sắp bị xóa, cần theo dõi phiên bản JDK và kiểm thử trước khi nâng cấp.

## 8. Giới hạn của `@SuppressWarnings`

### 8.1. Không phải mọi chẩn đoán đều có thể giấu bằng annotation

Annotation chỉ có thể ảnh hưởng tới những warning mà compiler nhận diện và gắn với phạm vi khai báo thích hợp. Một số vấn đề nằm ở cấu hình toàn lượt biên dịch như đường dẫn classpath sai, tùy chọn compiler không tương thích hoặc annotation processing, nên phải sửa ở lệnh build/cấu hình thay vì trông đợi annotation trong một method.

Các khóa `unchecked`, `deprecation`, `removal` và `preview` được Java chuẩn quy định. Các khóa bổ sung như `rawtypes`, `serial`, `cast` là chi tiết compiler/toolchain; hãy kiểm tra `javac --help-lint` và tài liệu của JDK mục tiêu.

Compiler có thể bỏ qua khóa warning không biết đến. Không xem một annotation viết sai chính tả là bằng chứng đã suppression thành công; hãy bật lint và chạy một bài kiểm tra thực sự.

### 8.2. Không sửa lỗi biên dịch, lỗi runtime hay cảnh báo của công cụ khác

`@SuppressWarnings("unchecked")` không biến cast không đúng kiểu thành an toàn, không sửa mã thiếu dấu `;`, không loại bỏ `NullPointerException`, và không tự tắt cảnh báo từ mọi công cụ như Checkstyle, PMD, SpotBugs hoặc Error Prone. Các công cụ đó có bộ quy tắc/suppression riêng, dù có thể hỗ trợ một số tên annotation chung.

`-Werror` cũng chỉ áp dụng cho warning mà `javac` phát ra trong chính lần biên dịch. Nó không tự xét kết quả test runtime hay phân tích bảo mật bên ngoài.

### 8.3. Phạm vi ở `module-info.java` và `package-info.java`

Tài liệu `@SuppressWarnings` của Java 21 nói rõ: khi annotation đặt trong `module-info.java` hoặc `package-info.java`, suppression áp dụng cho các phần tử trong **chính tệp đó**, không mặc nhiên lan tới mọi lớp thuộc module/package. Vì vậy, đừng dùng annotation tại các tệp mô tả này làm cách tắt warning hàng loạt cho cả thư viện.

### 8.4. Không dùng suppression quá rộng

Tránh dùng:

```java
@SuppressWarnings("all")
public class LegacyService {
    // Toàn bộ lớp có thể mất tín hiệu từ các nhóm cảnh báo hữu ích.
}
```

Đây là đoạn **minh họa một anti-pattern**, không có nghĩa mọi compiler đều công nhận khóa `"all"` theo cùng một cách. Để quản lý build, cấu hình những nhóm lint cụ thể và tách phạm vi code cần ngoại lệ. Suppression diện rộng có thể che warning mới phát sinh sau khi người khác sửa code, khiến việc review bỏ sót rủi ro.

## 9. Chính sách `-Werror` cho build và CI

Một cấu hình thực tiễn cho module còn ít nợ kỹ thuật:

1. **Bật lint trước.** Chạy `-Xlint:all` (hoặc các nhóm được đội ngũ thống nhất), lưu và phân loại những warning hiện có.
2. **Sửa warning có thể sửa.** Ưu tiên thay raw type bằng generic, xóa cast thừa, nâng API deprecated và sửa cấu hình build.
3. **Cô lập trường hợp bắt buộc.** Với tích hợp legacy không thể loại bỏ ngay, thêm suppression ở vị trí hẹp nhất và mô tả lý do.
4. **Bật `-Werror`.** Chỉ sau khi danh sách warning đã được xử lý/cô lập, buộc mã mới không làm cảnh báo gia tăng.
5. **Chạy trong CI với JDK thống nhất.** Pin hoặc công bố toolchain; khi nâng JDK, kiểm tra nhóm warning mới, thay đổi hỗ trợ lint và các dependency/generator liên quan.
6. **Giữ chẩn đoán có thể đọc.** Lưu log compiler, đường dẫn nguồn, category warning và exit status khi CI thất bại; sửa nguyên nhân ở đúng module.

Đối với codebase lâu năm có nhiều warning, có thể khởi đầu bằng `-Xlint:unchecked,rawtypes,deprecation` rồi mở rộng dần. Cách này chỉ hiệu quả nếu có kế hoạch giảm warning rõ ràng; tránh duy trì chế độ tắt cảnh báo vô thời hạn.

### Tích hợp Gradle (Groovy DSL)

Trong một dự án đã áp dụng plugin Java, có thể cấu hình các tác vụ biên dịch Java bằng:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
```

Đây là **mảnh cấu hình `build.gradle`**, không phải tệp Java chạy độc lập. Nó áp dụng cho những tác vụ `JavaCompile` thuộc dự án được cấu hình (ví dụ compile nguồn chính và test tương ứng). Với multi-project build, cần xác định đúng nơi áp dụng cấu hình, tránh vô tình áp dụng quy tắc lên module/generator chưa được rà soát.

### Tích hợp Maven

Trong `pom.xml`, cấu hình `maven-compiler-plugin` tương ứng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Đây là **mảnh XML đặt trong phần `<plugins>` thích hợp** của dự án, không phải một POM hoàn chỉnh. Trong dự án thật, cần quản lý plugin version, Java release/toolchain và cấu hình riêng cho compiler nếu cần.

Ở cả Gradle lẫn Maven, đừng chỉ đọc log `BUILD SUCCESS` từ bước khác. Kiểm tra xem tác vụ biên dịch nguồn mục tiêu có thật sự chạy, dùng flags nào, và CI có propagate exit code thất bại hay không.

## 10. Các tình huống chẩn đoán thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `javac` báo `Note: uses unchecked or unsafe operations` nhưng không thấy dòng warning cụ thể | Chưa bật lint chi tiết | Biên dịch lại với `-Xlint:unchecked` |
| Bật `-Werror` mà raw type vẫn lọt qua | Chưa bật `-Xlint:rawtypes` hoặc cấu hình không áp dụng lên tác vụ đó | Xem compiler args thực tế, bật `-Xlint:rawtypes` |
| Có `@SuppressWarnings("deprecation")` nhưng vẫn cảnh báo API sắp xóa | Diagnostic là `removal` | Xem loại warning; ưu tiên chuyển API, suppression đúng key nếu cần |
| Chỉ một phương thức dùng legacy API nhưng cả lớp được suppression | Annotation có phạm vi quá rộng | Chuyển annotation vào khai báo hẹp nhất |
| Build với JDK mới đột nhiên thất bại dù source không đổi | Bộ lint, API deprecation, dependency hoặc plugin đã thay đổi | So sánh JDK/toolchain, flags, warning log |
| `-Xlint:all -Werror` thất bại trong source được sinh | Generator/annotation processor tạo code có warning, hoặc cấu hình compile chứa cảnh báo khác | Tách nguồn của diagnostic, cập nhật generator hoặc cấu hình đúng phạm vi |
| CI chạy thành công nhưng local báo warning | Khác compiler arguments/toolchain/compile task | Đối chiếu lệnh thật và đầu ra log |
| Suppression đã thêm nhưng warning của công cụ phân tích vẫn hiện | Warning không do `javac` xử lý hoặc tên key riêng | Tra tài liệu và cấu hình của công cụ đã phát diagnostic |

Một quy trình điều tra gọn: **ghi warning chính xác → xác định công cụ phát ra → kiểm tra flag bật category → định vị dòng nguồn/phạm vi annotation → sửa nguyên nhân → chạy lại compile với cùng toolchain và `-Werror`**.

Tránh biện pháp `-nowarn` hoặc `-Xlint:none` chỉ để vượt CI mà không phân loại nguyên nhân. Chúng có thể khiến nhóm không thấy warning mới; dù vậy, compiler vẫn có thể báo những lỗi thực sự hoặc những loại chẩn đoán khác, nên không xem việc ẩn warning là thay thế cho việc đạt tiêu chuẩn chất lượng.

## 11. Bài tập thực hành

**Bài 1 — Đọc warning.** Từ `WarningDemo.java` ban đầu, hãy giải thích vì sao cùng một dòng có cả `rawtypes` lẫn `unchecked`.  
*Gợi ý/đáp án:* `new ArrayList()` là dạng raw type; đưa đối tượng raw vào `List<String>` cần unchecked conversion vì compiler không xác minh được tham số kiểu. Dùng `new ArrayList<>()` để giữ đúng kiểu từ điểm tạo.

**Bài 2 — Thử chính sách.** Vì sao `javac -Werror WarningDemo.java` chưa đủ để khẳng định dự án “không có raw type”?  
*Đáp án:* `-Werror` chỉ xử lý warning đã phát sinh; cần bật đúng category, ví dụ `-Xlint:rawtypes,unchecked`, và xác nhận lệnh compile đang chạy trên nguồn cần kiểm tra.

**Bài 3 — Chọn phạm vi.** Một helper trong lớp chứa một cast unchecked đã được kiểm tra dữ liệu. Đặt `@SuppressWarnings("unchecked")` ở lớp hay helper?  
*Đáp án:* Ưu tiên ở chính khai báo biến hoặc helper gây warning, kèm giải thích bất biến/tiền điều kiện, để code còn lại vẫn được kiểm tra.

**Bài 4 — Deprecated API.** Vì sao `@SuppressWarnings("deprecation")` không phải cách xử lý đủ khi API được đánh dấu `forRemoval=true`?  
*Đáp án:* Cảnh báo là nhóm `removal`; cần kế hoạch chuyển API và dùng suppression đúng nhóm trong trường hợp thực sự cần ngoại lệ có thời hạn.

**Bài 5 — Đọc CI.** CI mới thất bại sau khi nâng JDK, log báo warning ở một file Java sinh tự động. Nên làm gì?  
*Đáp án:* Ghi category/vị trí warning và phiên bản toolchain; kiểm tra generator/processor và cấu hình compile; xử lý tại nguồn sinh hoặc bước cấu hình liên quan trước khi quyết định có được suppression cục bộ hay không.

## 12. Checklist áp dụng cho mỗi thay đổi

- [ ] Đã biết `javac` và JDK/toolchain nào thực hiện compile, nguồn nào thực sự được biên dịch?
- [ ] Đã bật nhóm lint đủ để nhìn rõ loại warning cần kiểm thử?
- [ ] Đã sửa nguyên nhân trước khi cân nhắc suppression?
- [ ] Nếu dùng `@SuppressWarnings`, khóa có đúng compiler và phạm vi có hẹp nhất?
- [ ] Mỗi ngoại lệ có lý do tương thích/điều kiện kiểm tra và hướng loại bỏ?
- [ ] `-Werror` đã chạy trên đúng module/task trong CI?
- [ ] Build chỉ được coi là đạt khi compile thành công trên artifact/toolchain đã xác minh, không dựa vào class cũ còn trong thư mục output?

**Kết luận kỹ thuật:** `-Xlint` giúp nhìn thấy những rủi ro mà Java vẫn cho phép biên dịch; `-Werror` biến các warning được bật thành rào cản chất lượng của build; `@SuppressWarnings` là cơ chế ngoại lệ cục bộ cần chứng minh, không phải cách chữa lỗi tự động. Kết hợp đúng ba công cụ giúp giữ tín hiệu cảnh báo đáng tin trong quá trình phát triển và CI.

## Tài liệu tham khảo chuẩn

- [Oracle JDK 21 — The javac Command: -Xlint, -Werror, --help-lint](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 API — @SuppressWarnings](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SuppressWarnings.html)
- [Java Language Specification §9.6.4.5 — @SuppressWarnings](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.5)
- [Oracle JDK 21 — Notifications and Warnings (deprecation/removal)](https://docs.oracle.com/en/java/javase/21/core/notifications-and-warnings.html)
