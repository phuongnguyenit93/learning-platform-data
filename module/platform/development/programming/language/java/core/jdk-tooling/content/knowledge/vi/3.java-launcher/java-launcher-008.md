# System property trong runtime Java

**System property** là một cặp khóa–giá trị dạng chuỗi mà Java lưu trong tập thuộc tính của tiến trình JVM hiện tại. JVM, thư viện JDK và ứng dụng có thể đọc các giá trị này để biết thông tin môi trường hoặc nhận cấu hình lúc khởi chạy. Ví dụ: phiên bản Java, hệ điều hành, thư mục làm việc và chế độ chạy của ứng dụng.

Java launcher cho phép thiết lập thuộc tính ngay khi tạo JVM bằng tùy chọn `-Dkey=value`. Mã ứng dụng cũng có thể đọc, thêm, thay đổi hoặc xóa thuộc tính trong thời gian chạy thông qua lớp `java.lang.System`. System property phù hợp với các cấu hình dạng chuỗi cần truyền cho một tiến trình Java, chẳng hạn chế độ chạy, URL dịch vụ, giới hạn timeout hoặc cờ bật/tắt tính năng.

## 1. Phân biệt System property, environment variable và application argument

Ba loại giá trị này thường xuất hiện cùng lúc trong lệnh khởi chạy Java nhưng có cách truy cập và vòng đời khác nhau.

| Loại dữ liệu | Thiết lập ở đâu | Đọc trong Java | Phạm vi |
|---|---|---|---|
| System property | Tùy chọn JVM như `-Dapp.mode=production`, hoặc API `System.setProperty` | `System.getProperty("app.mode")` | Một tiến trình JVM |
| Environment variable | Môi trường hệ điều hành, ví dụ `APP_MODE=production` | `System.getenv("APP_MODE")` | Tiến trình và các tiến trình con kế thừa môi trường |
| Application argument | Phần tham số sau tên class, `-jar` hoặc module đích | Mảng `String[] args` của `main` | Lần chạy ứng dụng đó |

Ví dụ:

~~~sh
java -Dapp.mode=production -jar service.jar --port=8080
~~~

- `-Dapp.mode=production` là tùy chọn JVM, tạo system property có khóa `app.mode`.
- `service.jar` là ứng dụng được khởi chạy.
- `--port=8080` nằm sau tên JAR nên là tham số ứng dụng, được chuyển vào `main(String[] args)`.

`System.getenv()` chỉ đọc môi trường được tiến trình kế thừa. Java không cung cấp API chuẩn để thay đổi environment variable của tiến trình hệ điều hành hiện tại. Ngược lại, `System.setProperty()` chỉ thay đổi system property trong JVM đang chạy, không sửa môi trường hệ điều hành và cũng không truyền ngược thay đổi đó sang tiến trình khác.

## 2. Thiết lập property từ Java launcher bằng -D

Cú pháp cơ bản:

~~~sh
java -D<property-name>=<value> <class-name>
~~~

Ví dụ:

~~~sh
java -Dapp.mode=production -Dapp.region=ap-southeast-1 com.example.Main
~~~

JVM được khởi chạy với hai system property: `app.mode=production` và `app.region=ap-southeast-1`. Tùy chọn `-D` phải được đặt trong phần tùy chọn của Java launcher, trước class, `-jar` hoặc module đích. Vị trí này rất quan trọng:

~~~sh
# Đúng: -D thuộc tùy chọn JVM
java -Dapp.mode=production -jar service.jar

# Sai nếu mục đích là đặt system property:
java -jar service.jar -Dapp.mode=production
~~~

Ở lệnh thứ hai, chuỗi `-Dapp.mode=production` nằm sau tên JAR nên được chuyển cho ứng dụng như một application argument. Nó không thiết lập system property.

Các dạng khởi chạy phổ biến:

~~~sh
# Chạy class
java -Dapp.mode=production -cp app.jar com.example.Main

# Chạy executable JAR
java -Dapp.mode=production -jar app.jar

# Chạy main class trong module
java -Dapp.mode=production -m com.example.app/com.example.Main
~~~

Khi có nhiều thuộc tính, đặt mỗi thuộc tính bằng một tùy chọn `-D` riêng. Nếu giá trị có dấu cách, hãy dùng dấu nháy theo cú pháp shell của hệ điều hành để toàn bộ biểu thức `-Dkey=value` được truyền thành một đối số:

~~~sh
java "-Dapp.display-name=Java Learning Service" -jar app.jar
~~~

PowerShell, Command Prompt, Bash và Zsh có quy tắc trích dẫn khác nhau. Nếu giá trị chứa ký tự đặc biệt như dấu nháy, dấu `$` hoặc dấu `;`, hãy kiểm tra cách shell diễn giải trước khi kết luận JVM nhận sai property.

`-D` là tùy chọn của Java launcher/JVM, không phải cú pháp riêng của Java source code. Giá trị được cung cấp dưới dạng chuỗi; nếu ứng dụng cần số, boolean, danh sách hoặc kiểu dữ liệu khác, mã ứng dụng phải chuyển đổi và xác thực.

## 3. Đọc và thao tác với System property trong Java

Lớp `java.lang.System` cung cấp các API chính:

| API | Tác dụng |
|---|---|
| `System.getProperty(key)` | Lấy giá trị của khóa; trả về `null` nếu không tồn tại |
| `System.getProperty(key, defaultValue)` | Lấy giá trị hoặc dùng giá trị mặc định nếu khóa không tồn tại |
| `System.setProperty(key, value)` | Thêm hoặc thay đổi giá trị; trả về giá trị cũ nếu có |
| `System.clearProperty(key)` | Xóa khóa; trả về giá trị cũ nếu có |
| `System.getProperties()` | Lấy tập `Properties` hiện tại của JVM |
| `System.setProperties(properties)` | Thay thế tập system properties hiện tại |

Ví dụ đọc giá trị có mặc định:

~~~java
String mode = System.getProperty("app.mode", "development");
~~~

Nếu Java launcher không truyền `-Dapp.mode=...`, biến `mode` nhận `development`. Nếu đã truyền, nó nhận giá trị được cung cấp lúc khởi chạy.

Có thể cập nhật một thuộc tính trong thời gian chạy:

~~~java
String previous = System.setProperty("app.mode", "maintenance");
String current = System.getProperty("app.mode");
~~~

Sau lệnh `setProperty`, các lần đọc tiếp theo trong cùng JVM nhận giá trị mới, trừ khi thư viện hoặc thành phần đã đọc và lưu giá trị cũ vào cache riêng. Thay đổi này không tự khởi động lại thư viện, không cập nhật tiến trình khác và không ghi cấu hình vào file để dùng ở lần chạy sau.

Khi gọi `System.setProperty`, cả khóa và giá trị phải khác `null`; khóa rỗng không hợp lệ. Các API có thể phát sinh `SecurityException` trong môi trường còn áp dụng chính sách bảo mật giới hạn quyền truy cập system properties. Không nên dựa vào khả năng sửa mọi property của JVM.

### Đọc toàn bộ tập thuộc tính

`System.getProperties()` trả về đối tượng `java.util.Properties` chứa các thuộc tính hiện tại:

~~~java
Properties properties = System.getProperties();
String javaVersion = properties.getProperty("java.version");
~~~

Cần import `java.util.Properties` nếu dùng tên lớp `Properties` trực tiếp. Có thể duyệt các khóa để chẩn đoán, nhưng không nên in toàn bộ properties vào log sản xuất một cách tùy tiện: một số giá trị có thể tiết lộ đường dẫn, tên tài khoản, cấu hình nội bộ hoặc thông tin môi trường.

`System.setProperties()` thay thế cả tập thuộc tính hiện tại. Nếu đưa vào một đối tượng `Properties` thiếu các thuộc tính chuẩn, mã khác trong JVM có thể không còn đọc được các khóa mà nó mong đợi. Phần lớn ứng dụng chỉ nên dùng `System.setProperty()` cho các khóa do chính ứng dụng quản lý; không thay toàn bộ tập thuộc tính nếu không có lý do rõ ràng.

## 4. Các system property thường gặp

Java cung cấp một số thuộc tính chuẩn để truy vấn môi trường runtime. Giá trị cụ thể phụ thuộc JDK, nhà cung cấp, hệ điều hành và cách khởi chạy.

| Property | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.vendor` | Nhà cung cấp bản phân phối Java |
| `java.home` | Thư mục cài đặt Java runtime |
| `java.class.path` | Classpath của ứng dụng |
| `java.library.path` | Các vị trí JVM tìm thư viện native |
| `os.name` | Tên hệ điều hành |
| `os.version` | Phiên bản hệ điều hành |
| `os.arch` | Kiến trúc hệ điều hành |
| `user.name` | Tên tài khoản người dùng của tiến trình |
| `user.home` | Thư mục home của người dùng |
| `user.dir` | Thư mục làm việc hiện tại khi JVM khởi chạy |
| `file.separator` | Ký tự phân tách thư mục trên hệ điều hành |
| `path.separator` | Ký tự phân tách các phần tử trong path |
| `line.separator` | Ký tự xuống dòng theo nền tảng |

Có thể kiểm tra nhanh một vài giá trị trong ứng dụng:

~~~java
System.out.println("Java version: " + System.getProperty("java.version"));
System.out.println("OS: " + System.getProperty("os.name"));
System.out.println("Working directory: " + System.getProperty("user.dir"));
~~~

Không nên giả định các giá trị như đường dẫn, tên hệ điều hành hoặc phiên bản sẽ giống nhau giữa máy phát triển, CI và production. Nếu ứng dụng cần hành vi đa nền tảng, hãy dùng API phù hợp như `Path`, `File.separator` hoặc `System.lineSeparator()` thay vì tự suy luận từ một chuỗi cố định.

Một số property có ý nghĩa đặc biệt:

- `user.dir` mô tả thư mục làm việc mà JVM sử dụng khi khởi chạy. Gọi `System.setProperty("user.dir", "...")` không phải cách đáng tin cậy để đổi working directory thực tế của tiến trình.
- `java.class.path` phản ánh classpath được cung cấp cho ứng dụng classpath. Với ứng dụng module, việc phân giải module còn phụ thuộc module path và cấu hình JPMS.
- `java.library.path` liên quan đến việc tìm thư viện native. Thay đổi giá trị trong lúc chạy không đảm bảo bộ nạp thư viện đã khởi tạo sẽ tìm lại thư viện theo đường dẫn mới.
- `file.encoding` liên quan đến charset mặc định. Từ JDK 18, UTF-8 là charset mặc định theo JEP 400 trong các môi trường thông thường. Không nên gọi `System.setProperty("file.encoding", ...)` trong ứng dụng để cố thay đổi charset mặc định sau khi JVM đã khởi tạo; hãy chỉ định charset tường minh trong API đọc/ghi dữ liệu, ví dụ `StandardCharsets.UTF_8`.

Các property nội bộ có tiền tố như `sun.` hoặc `jdk.` có thể phục vụ triển khai JDK cụ thể. Không coi chúng là API ổn định nếu tài liệu Java SE không cam kết. Ưu tiên các property chuẩn hoặc khóa có namespace riêng của ứng dụng.

## 5. Ví dụ hoàn chỉnh: đọc, thay đổi và xóa property

Tạo file `RuntimePropertiesDemo.java`:

~~~java
public class RuntimePropertiesDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "development");
        String region = System.getProperty("app.region", "local");

        System.out.println("mode.before=" + mode);
        System.out.println("region=" + region);

        System.setProperty("app.mode", "runtime");
        System.out.println("mode.after=" + System.getProperty("app.mode"));

        System.clearProperty("app.region");
        System.out.println(
            "region.after.clear=" + System.getProperty("app.region", "local")
        );

        System.out.println("args.count=" + args.length);
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac RuntimePropertiesDemo.java
java -Dapp.mode=production -Dapp.region=ap-southeast-1 RuntimePropertiesDemo sample
~~~

Kết quả stdout:

~~~text
mode.before=production
region=ap-southeast-1
mode.after=runtime
region.after.clear=local
args.count=1
~~~

Giải thích:

1. `System.getProperty("app.mode", "development")` nhận giá trị `production` từ tùy chọn `-D`.
2. `System.getProperty("app.region", "local")` nhận `ap-southeast-1`.
3. `System.setProperty()` đổi `app.mode` thành `runtime`; lần đọc tiếp theo thấy giá trị mới.
4. `System.clearProperty()` xóa `app.region`; lần đọc với giá trị mặc định trả về `local`.
5. `sample` nằm sau tên class nên được đưa vào `args`, không phải system property.

Nếu bỏ cả hai tùy chọn `-D`, chương trình vẫn chạy và dùng các giá trị mặc định `development` và `local`. Đây là một cách hữu ích để ứng dụng có cấu hình mặc định khi chạy cục bộ nhưng có thể nhận cấu hình riêng từ môi trường triển khai.

## 6. Chuyển đổi và xác thực giá trị

System properties luôn được đọc dưới dạng `String`. Không nên ép kiểu bằng cách giả định đầu vào luôn hợp lệ.

Ví dụ đọc một timeout tính bằng giây:

~~~java
String timeoutText = System.getProperty("app.timeout-seconds", "30");

int timeoutSeconds;
try {
    timeoutSeconds = Integer.parseInt(timeoutText);
} catch (NumberFormatException exception) {
    throw new IllegalArgumentException(
        "app.timeout-seconds must be an integer", exception
    );
}

if (timeoutSeconds <= 0) {
    throw new IllegalArgumentException(
        "app.timeout-seconds must be greater than zero"
    );
}
~~~

Nếu khởi chạy bằng:

~~~sh
java -Dapp.timeout-seconds=45 -jar app.jar
~~~

ứng dụng nhận timeout là 45 giây. Nếu truyền `-Dapp.timeout-seconds=abc`, `Integer.parseInt()` ném `NumberFormatException`; cần báo lỗi cấu hình rõ ràng thay vì âm thầm dùng một giá trị không hợp lệ.

Với boolean, `Boolean.parseBoolean(value)` trả về `true` khi chuỗi không phân biệt hoa thường bằng `true`; các giá trị khác, kể cả chuỗi sai chính tả, đều trả về `false`. Nếu cần phân biệt `false`, giá trị thiếu và giá trị không hợp lệ, hãy tự xác thực chuỗi trước khi chuyển đổi.

Với danh sách, có thể quy định một định dạng đơn giản như dấu phẩy phân tách rồi dùng `String.split()`, nhưng phải xác định cách xử lý khoảng trắng, phần tử rỗng và dấu phẩy nằm trong giá trị. Với cấu hình phức tạp, nhiều cấp hoặc cần reload, file cấu hình và thư viện cấu hình chuyên dụng thường phù hợp hơn một loạt system property.

## 7. Quan sát properties và chẩn đoán runtime

Java launcher có thể in các system properties mà JVM nhìn thấy lúc khởi chạy:

~~~sh
java -XshowSettings:properties -version
~~~

Lệnh này hiển thị nhiều thông tin môi trường cùng phiên bản Java. Kết quả hữu ích khi kiểm tra `java.home`, `java.version`, `os.name`, `user.dir` hoặc các giá trị do launcher nhận vào. Vì đầu ra có thể chứa đường dẫn và tên tài khoản, hãy rà soát trước khi chia sẻ log.

Với một tiến trình Java đang chạy, JDK cung cấp công cụ `jcmd` để truy vấn thuộc tính của JVM nếu tiến trình cho phép attach và người gọi có quyền phù hợp:

~~~sh
jcmd <pid> VM.system_properties
~~~

Thay `<pid>` bằng process ID của JVM cần kiểm tra. Lệnh này trả về tập system properties của tiến trình tại thời điểm truy vấn. Trên môi trường container, máy chủ hoặc môi trường có nhiều user, khả năng attach có thể bị giới hạn; hãy chạy từ đúng tài khoản và namespace phù hợp.

Khi chẩn đoán, nên so sánh ba nguồn:

- Giá trị dự kiến trong lệnh khởi chạy hoặc cấu hình triển khai.
- Giá trị thực tế đọc bằng `System.getProperty()` bên trong ứng dụng.
- Giá trị được công cụ `jcmd` hoặc `-XshowSettings:properties` báo cáo.

Nếu các giá trị khác nhau, kiểm tra vị trí tùy chọn `-D`, script khởi chạy, cấu hình của IDE/build tool và đoạn code gọi `System.setProperty()` sau khi ứng dụng bắt đầu.

## 8. Ảnh hưởng trong thời gian chạy và các giới hạn

System properties thuộc phạm vi của một JVM. Hai tiến trình Java riêng biệt không tự chia sẻ thay đổi property với nhau, kể cả khi chạy cùng một JAR. Khi JVM kết thúc, các thay đổi chỉ tồn tại trong bộ nhớ cũng kết thúc theo.

Thay đổi property trong runtime có thể ảnh hưởng đến mã đọc property sau thời điểm thay đổi. Tuy nhiên, nhiều thư viện chỉ đọc cấu hình một lần khi khởi tạo rồi lưu vào biến hoặc đối tượng cấu hình. Khi đó, đổi system property sau này không tự cập nhật thành phần đã khởi tạo. Nếu cần đổi cấu hình, hãy dùng API reload hoặc cơ chế cấu hình mà thư viện hỗ trợ.

Không phải mọi property đều nên sửa:

- Ưu tiên đặt property ứng dụng bằng `-D` lúc khởi chạy.
- Dùng namespace riêng, ví dụ `com.example.billing.timeout-seconds`, để tránh trùng khóa với thư viện khác.
- Không ghi đè tùy tiện các khóa chuẩn như `java.version`, `java.home`, `os.name` hoặc `file.encoding`.
- Không dùng system property như kho lưu bí mật. Tham số JVM có thể xuất hiện trong danh sách tiến trình, log khởi chạy, báo cáo chẩn đoán hoặc công cụ giám sát.
- Không thay toàn bộ `System.getProperties()` bằng một tập mới nếu chưa hiểu ảnh hưởng tới JVM và thư viện.
- Không giả định property được cập nhật sau khi ứng dụng khởi chạy sẽ tự làm mới cache của thư viện.

Đối với mật khẩu, token hoặc khóa truy cập, hãy dùng secret manager hoặc cơ chế cấp phát bí mật phù hợp của nền tảng. Nếu phải truyền dữ liệu nhạy cảm qua cấu hình, cần đánh giá quyền truy cập, log, dump và khả năng quan sát của tiến trình.

## 9. Tích hợp với Gradle, Maven và IDE

Cần phân biệt system property của JVM chạy công cụ build với system property của JVM chạy ứng dụng.

Ví dụ, khi chạy:

~~~sh
./gradlew -Dorg.gradle.logging.level=info build
~~~

tùy chọn `-D` được gửi đến tiến trình Gradle. Điều đó không có nghĩa mọi JVM được Gradle tạo ra để chạy ứng dụng hoặc test đều tự động nhận cùng tập system properties. Với task chạy ứng dụng, hãy cấu hình JVM arguments của task, chẳng hạn `JavaExec.jvmArgs`; với test, dùng cấu hình system properties của `Test` task.

Tương tự, `mvn -Dname=value` thiết lập user/system property cho tiến trình Maven theo cơ chế của Maven. Khi cần truyền giá trị vào JVM chạy test fork hoặc ứng dụng, hãy dùng cấu hình tương ứng của plugin (ví dụ Maven Surefire/Failsafe hoặc plugin chạy ứng dụng), rồi xác minh từ chính tiến trình đích.

Trong IDE, có thể có nhiều vùng cấu hình riêng:

- **IDE runtime**: JDK dùng để chạy chính IDE.
- **Project SDK**: JDK mà project chọn để phân tích và biên dịch.
- **Gradle JVM / Maven runner**: JDK dùng để chạy build tool.
- **Application run configuration**: VM options được truyền cho JVM của ứng dụng.
- **Test run configuration**: VM options/system properties dành cho tiến trình test.

Nếu mục tiêu là đặt property cho ứng dụng, hãy nhập `-Dapp.mode=production` trong trường **VM options** của cấu hình chạy ứng dụng. Đưa chuỗi đó vào trường **Program arguments** sẽ khiến nó trở thành tham số của `main`, không phải system property.

Sau khi thay đổi cấu hình, hãy xác minh từ đúng tiến trình cần kiểm tra. Việc build thành công chỉ chứng minh tiến trình build chạy được; nó chưa chứng minh ứng dụng nhận đúng system property.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `System.getProperty()` trả về `null` | Chưa đặt property, sai tên khóa hoặc `-D` nằm sau class/JAR/module | Đặt `-Dkey=value` trước đích khởi chạy và kiểm tra đúng tên khóa |
| Ứng dụng nhận chuỗi `-D...` trong `args` | Tùy chọn được đặt sau `-jar` hoặc tên class | Chuyển `-D` sang phần tùy chọn JVM trước đích |
| Giá trị có dấu cách bị tách | Shell chia biểu thức thành nhiều đối số | Trích dẫn toàn bộ biểu thức `-Dkey=value` theo shell |
| Giá trị trong runtime khác lúc khởi chạy | Mã khác đã gọi `System.setProperty()` hoặc cấu hình được nạp lại | Tìm các nơi sửa cùng khóa; đặt namespace rõ ràng và log có chọn lọc |
| Đổi property nhưng thư viện vẫn dùng giá trị cũ | Thư viện đã cache cấu hình khi khởi tạo | Dùng API reload/reconfigure hoặc đặt property trước khi khởi tạo thư viện |
| Build tool nhận property nhưng ứng dụng không nhận | Property được đặt cho JVM của Gradle/Maven, không phải JVM ứng dụng | Truyền VM options vào task hoặc run configuration của tiến trình đích |
| Đọc số hoặc boolean thất bại | Giá trị chuỗi không hợp lệ hoặc không đúng định dạng | Parse, xác thực và thông báo lỗi cấu hình cụ thể |
| Property nội bộ không hoạt động sau khi nâng JDK | Khóa phụ thuộc triển khai JDK hoặc không phải API được đảm bảo | Dùng property chuẩn/API công khai; kiểm tra tương thích phiên bản |

### Checklist sử dụng an toàn

- [ ] Phân biệt system property với environment variable và application argument.
- [ ] Đặt `-Dkey=value` trước class, `-jar` hoặc module đích.
- [ ] Dùng `System.getProperty()` và giá trị mặc định hợp lý.
- [ ] Chuyển đổi và xác thực dữ liệu chuỗi trước khi dùng.
- [ ] Dùng namespace riêng cho property của ứng dụng.
- [ ] Đặt cấu hình trước khi thư viện cần nó được khởi tạo.
- [ ] Truyền property vào đúng JVM của ứng dụng hoặc test.
- [ ] Không lưu bí mật trong command line hoặc system properties.
- [ ] Xác minh giá trị trong chính tiến trình runtime cần kiểm tra.

Khi hiểu đúng vị trí của `-D`, phạm vi của JVM và các API `System`, system properties trở thành cách gọn nhẹ để cung cấp cấu hình cho ứng dụng Java lúc khởi chạy và trong thời gian chạy.