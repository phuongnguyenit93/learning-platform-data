# Mã hóa UTF-8, locale, múi giờ và tác động đến kết quả build

Một dự án Java có thể biên dịch thành công trên máy của bạn nhưng tạo ra kết quả khác khi chạy trên máy đồng nghiệp hoặc trên CI. Nguyên nhân đôi khi không nằm ở mã nguồn hay phiên bản thư viện, mà ở môi trường thực thi: cách đọc byte thành ký tự, locale mặc định, múi giờ, bảng mã của Terminal hoặc cách công cụ build ghi metadata vào artifact.

Các thiết lập này có thể ảnh hưởng đến nhiều bước:

- Trình biên dịch đọc tệp `.java` và các tài nguyên văn bản.
- Build script xử lý tên, ngày tháng, số thập phân và dữ liệu theo locale.
- Kiểm thử chạy với charset, locale và múi giờ mặc định của JVM.
- Tác vụ sinh báo cáo, tài liệu hoặc tệp cấu hình ghi nội dung phụ thuộc môi trường.
- Tác vụ đóng gói tạo JAR/WAR có metadata hoặc thứ tự tệp khác nhau.

Để kết quả build có thể tái hiện trên nhiều máy, cần hiểu từng thiết lập, khai báo rõ những giá trị quan trọng và kiểm tra môi trường của cả máy phát triển lẫn CI.

## 1. Phân biệt mã hóa ký tự với locale và múi giờ

Ba khái niệm này liên quan đến văn bản và thời gian nhưng giải quyết những vấn đề khác nhau.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Character encoding (mã hóa ký tự) | Các byte trong tệp được chuyển thành ký tự như thế nào? | UTF-8, UTF-16, ISO-8859-1 |
| Locale (thiết lập vùng/ngôn ngữ) | Ngôn ngữ, cách định dạng và quy tắc theo vùng nào được sử dụng? | `vi-VN`, `en-US`, `tr-TR` |
| Time zone (múi giờ) | Một thời điểm được hiển thị theo vùng giờ nào? | `UTC`, `Asia/Ho_Chi_Minh`, `America/New_York` |

Ví dụ, chuỗi `Xin chào` được lưu thành các byte UTF-8. Locale `vi-VN` có thể quyết định cách định dạng số hoặc ngày tháng theo tiếng Việt. Múi giờ `Asia/Ho_Chi_Minh` quyết định cách hiển thị một thời điểm theo giờ Việt Nam. Thay đổi một thiết lập không tự động thay đổi hai thiết lập còn lại.

## 2. UTF-8 và dữ liệu văn bản trong dự án Java

Máy tính lưu tệp dưới dạng byte. Khi một công cụ đọc tệp văn bản, nó cần biết bảng mã để giải mã các byte thành ký tự. Nếu lúc lưu và lúc đọc dùng hai bảng mã khác nhau, ký tự có thể bị lỗi hoặc nội dung có thể không được hiểu đúng.

UTF-8 là lựa chọn phù hợp cho phần lớn dự án Java hiện đại vì hỗ trợ Unicode, tương thích với ASCII và được sử dụng rộng rãi trong hệ sinh thái công cụ phát triển. Nên thống nhất UTF-8 cho mã nguồn, tài nguyên văn bản, cấu hình và các tệp được sinh ra.

### Mã hóa tệp nguồn và `javac`

Xét một tệp `Hello.java` có nội dung tiếng Việt:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Việt Nam!");
    }
}
```

Hãy lưu tệp bằng UTF-8 và biên dịch với:

```shell
javac -encoding UTF-8 Hello.java
```

Tùy chọn `-encoding UTF-8` yêu cầu trình biên dịch đọc tệp nguồn bằng UTF-8. Nếu tệp thực tế được lưu bằng một bảng mã khác, cần chuyển tệp về UTF-8 hoặc dùng đúng bảng mã đầu vào. Chỉ thêm tùy chọn UTF-8 không thể sửa nội dung đã bị mã hóa sai từ trước.

Nếu bỏ `-encoding`, `javac` sử dụng charset mặc định của môi trường Java đang chạy. Hành vi này từng dễ khác nhau giữa các hệ điều hành và cấu hình. Từ JDK 18, UTF-8 là charset mặc định của Java theo JEP 400, nhưng khai báo rõ encoding trong cấu hình build vẫn giúp thể hiện ý định của dự án và giữ tính nhất quán với các công cụ xử lý văn bản khác.

### Cấu hình encoding trong Gradle

Với Gradle Java plugin, cấu hình encoding cho tất cả tác vụ biên dịch Java bằng `options.encoding`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Khi đó, các tác vụ `compileJava`, `compileTestJava` và các tác vụ `JavaCompile` tương ứng sẽ đọc mã nguồn theo UTF-8. Nếu dự án có tác vụ tự viết để đọc tệp văn bản, tác vụ đó cũng cần khai báo encoding riêng; cấu hình `JavaCompile` không tự áp dụng cho mọi plugin hay mọi thao tác đọc file.

### Cấu hình encoding trong Maven

Khai báo encoding chung trong `pom.xml`:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Với Maven Compiler Plugin, có thể truyền rõ encoding:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <encoding>${project.build.sourceEncoding}</encoding>
    </configuration>
</plugin>
```

`project.build.sourceEncoding` thường được các plugin Maven dùng làm encoding mặc định cho tài nguyên nguồn, nhưng cần xem cấu hình của plugin cụ thể. Compiler, resource filtering, reporting và plugin sinh code là những thành phần khác nhau; cấu hình encoding ở một plugin không nhất thiết điều khiển tất cả thành phần còn lại.

### Encoding của tài nguyên

Mã nguồn Java không phải loại văn bản duy nhất trong dự án. Tệp `.properties`, `.yml`, `.xml`, `.json`, `.html`, SQL hoặc template cũng có thể chứa tiếng Việt và ký tự Unicode.

Ví dụ, khi một tác vụ resource filtering thay thế placeholder trong tệp cấu hình, cả encoding lúc đọc lẫn encoding lúc ghi đều cần được xác định. Nếu mã nguồn được đọc bằng UTF-8 nhưng resource filtering đọc tệp bằng bảng mã khác, artifact có thể chứa văn bản sai dù bước biên dịch Java thành công.

Một điểm cần chú ý với Java Properties: `Properties.load(InputStream)` diễn giải byte theo ISO-8859-1 theo hợp đồng API, trong khi `Properties.load(Reader)` dùng ký tự mà `Reader` cung cấp. Nếu muốn đọc tệp `.properties` bằng UTF-8 một cách tường minh, có thể dùng:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties properties = new Properties();
try (Reader reader = Files.newBufferedReader(
        Path.of("application.properties"), StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

`ResourceBundle` có quy tắc riêng: từ Java 9, tệp properties của resource bundle mặc định được đọc theo UTF-8, với cơ chế fallback tương thích ISO-8859-1 khi giải mã UTF-8 thất bại. Không nên suy rộng quy tắc của `ResourceBundle` cho mọi API đọc `.properties`.

## 3. Charset mặc định của JVM và cách đọc/ghi file an toàn

JVM có charset mặc định, có thể xem bằng `Charset.defaultCharset()`. Trên JDK 18 trở lên, giá trị mặc định là UTF-8 theo JEP 400, trừ khi môi trường sử dụng chế độ tương thích hoặc cấu hình đặc biệt. Tuy vậy, mã ứng dụng nên chỉ rõ charset ở những nơi giao tiếp với dữ liệu văn bản có định dạng xác định.

Không nên dựa vào charset mặc định khi đọc hoặc ghi tệp mà định dạng của tệp đã quy định UTF-8. Hãy dùng các API nhận `Charset`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");

Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
```

Với dữ liệu byte nhận từ HTTP, message queue hoặc một hệ thống khác, hãy tuân theo encoding của giao thức hoặc header tương ứng. Không phải mọi chuỗi byte đều là UTF-8.

Có thể kiểm tra một số thông tin của JVM bằng chương trình nhỏ:

```java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;

public class EnvironmentInfo {
    public static void main(String[] args) {
        System.out.println("Default charset: " + Charset.defaultCharset());
        System.out.println("Default locale: " + Locale.getDefault());
        System.out.println("Default time zone: " + TimeZone.getDefault().getID());
        System.out.println("System zone: " + ZoneId.systemDefault());
    }
}
```

Kết quả cho biết mặc định mà ứng dụng nhìn thấy tại thời điểm chạy. Nó không chứng minh rằng tất cả tệp trong repository đều dùng cùng encoding; muốn biết encoding thực tế của một tệp, cần xem cấu hình editor, công cụ tạo tệp hoặc kiểm tra byte của chính tệp đó.

## 4. Locale ảnh hưởng đến kết quả như thế nào?

Locale biểu diễn các quy tắc theo ngôn ngữ và vùng. Java dùng locale mặc định trong một số API định dạng, phân tích, so sánh và hiển thị dữ liệu.

Ví dụ, cùng một giá trị số có thể được hiển thị khác nhau:

```java
import java.text.NumberFormat;
import java.util.Locale;

double amount = 12345.67;

System.out.println(NumberFormat.getNumberInstance(Locale.US).format(amount));
System.out.println(NumberFormat.getNumberInstance(Locale.GERMANY).format(amount));
```

Kết quả thường có dạng:

```text
12,345.67
12.345,67
```

Nếu chương trình gọi `NumberFormat.getNumberInstance()` mà không truyền locale, kết quả phụ thuộc locale mặc định của JVM. Điều đó có thể làm thay đổi chuỗi được ghi vào tệp, kết quả kiểm thử hoặc dữ liệu sinh trong quá trình build.

### Định dạng số và ngày tháng

Đối với nội dung hướng đến người dùng, hãy chọn locale theo ngôn ngữ hoặc cấu hình của người dùng. Đối với nội dung máy đọc, định dạng giao tiếp hoặc tệp cần giống nhau trên mọi máy, hãy dùng định dạng chuẩn và locale tường minh.

Ví dụ định dạng ngày theo locale cụ thể:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 11, 13);

DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(Locale.US);

System.out.println(formatter.format(date));
```

Locale `US` được truyền trực tiếp nên kết quả không phụ thuộc locale mặc định của máy chạy. Nếu mục tiêu là định dạng trao đổi dữ liệu, nên dùng định dạng ISO như `LocalDate.toString()` hoặc formatter ISO thay vì định dạng ngày phụ thuộc ngôn ngữ.

### Chuyển chữ hoa/chữ thường và sắp xếp

Locale có thể ảnh hưởng đến việc chuyển chữ hoa/chữ thường. Một ví dụ nổi tiếng là chữ `i` trong locale tiếng Thổ Nhĩ Kỳ. Nếu dùng `toLowerCase()` không truyền locale để chuẩn hóa mã định danh, kết quả có thể khác trên máy có locale mặc định khác nhau.

Với các chuỗi mang tính kỹ thuật như key, tên thuộc tính, token hoặc mã định danh không phụ thuộc ngôn ngữ, hãy dùng `Locale.ROOT`:

```java
String normalized = input.toLowerCase(Locale.ROOT);
```

Đối với văn bản hiển thị cho người dùng, hãy dùng quy tắc locale thích hợp. Tương tự, nếu build tạo danh sách tệp hoặc metadata cần có thứ tự ổn định, hãy dùng comparator có quy tắc rõ ràng thay vì dựa vào thứ tự sắp xếp phụ thuộc locale hoặc hệ thống tệp.

### Đặt locale cho JVM

Locale mặc định có thể được điều khiển bằng các system property khi khởi chạy JVM:

```shell
java -Duser.language=en -Duser.country=US -cp build/classes/java/main com.example.Main
```

Trong ví dụ này, JVM bắt đầu với locale mặc định tương ứng `en-US`. Các property phải được đặt trước tên lớp hoặc tùy chọn chạy ứng dụng. Nếu đặt sau tên lớp, chúng sẽ được truyền như đối số cho `main` chứ không còn là JVM system property.

Trong ứng dụng, có thể đọc locale mặc định bằng `Locale.getDefault()`. Không nên tùy tiện thay đổi locale mặc định toàn cục giữa lúc chương trình đang chạy, vì các thành phần khác có thể đang dựa vào giá trị đó. Thường an toàn và rõ ràng hơn khi truyền `Locale` vào API định dạng cần dùng.

## 5. Múi giờ và tác động đến thời gian

Một thời điểm tuyệt đối và cách hiển thị thời điểm đó là hai việc khác nhau. `Instant` biểu diễn một thời điểm trên dòng thời gian, không gắn với múi giờ hiển thị. `ZonedDateTime` biểu diễn ngày giờ trong một `ZoneId` cụ thể. `LocalDateTime` chỉ chứa ngày và giờ trên đồng hồ, không tự xác định được thời điểm tuyệt đối nếu thiếu múi giờ hoặc offset.

Ví dụ, cùng một `Instant` có thể được hiển thị ở UTC hoặc giờ Việt Nam:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-13T06:00:00Z");

ZonedDateTime utc = instant.atZone(ZoneId.of("UTC"));
ZonedDateTime vietnam = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utc);
System.out.println(vietnam);
```

Hai giá trị mô tả cùng một thời điểm nhưng có giờ hiển thị khác nhau. Nếu build tạo tên tệp, báo cáo hoặc nội dung có ngày giờ theo múi giờ mặc định, kết quả có thể khác khi chạy ở hai khu vực.

### Chọn múi giờ tường minh

Đối với timestamp dùng trong log, metadata hoặc dữ liệu trao đổi giữa hệ thống, UTC thường là lựa chọn thuận tiện vì không phụ thuộc vị trí máy chạy. Đối với lịch làm việc hoặc thời điểm có ý nghĩa theo địa phương, hãy dùng `ZoneId` của địa điểm nghiệp vụ, ví dụ `Asia/Ho_Chi_Minh`.

Không nên lưu một `LocalDateTime` rồi giả định có thể khôi phục chính xác thời điểm ban đầu mà không biết múi giờ. Khi cần biểu diễn một thời điểm tuyệt đối, lưu `Instant` hoặc timestamp có offset; khi cần quy tắc lịch địa phương, lưu thêm `ZoneId` phù hợp.

### Đặt múi giờ mặc định cho JVM

Có thể đặt múi giờ mặc định bằng system property:

```shell
java -Duser.timezone=UTC -cp build/classes/java/main com.example.Main
```

Property này được đọc khi JVM khởi chạy. Đặt rõ trong môi trường kiểm thử giúp tránh kết quả khác nhau do máy phát triển đặt múi giờ địa phương còn CI đặt UTC.

Nếu ứng dụng cần xử lý lịch địa phương, không nên ép toàn bộ nghiệp vụ về UTC rồi bỏ mất vùng giờ ban đầu. Hãy truyền `ZoneId` theo yêu cầu nghiệp vụ; chỉ dùng UTC cho những dữ liệu cần một quy ước thời gian chung.

## 6. Cấu hình locale và múi giờ cho tác vụ kiểm thử

Kiểm thử có thể thất bại trên CI nếu giả định locale hoặc múi giờ của máy phát triển. Ví dụ, test so sánh chuỗi ngày tháng được định dạng theo locale mặc định hoặc test kỳ vọng giờ địa phương có thể cho kết quả khác nhau trên máy khác.

Với Gradle, có thể truyền system property cho JVM chạy test:

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'user.language', 'en'
    systemProperty 'user.country', 'US'
    systemProperty 'user.timezone', 'UTC'
}
```

Các thuộc tính này áp dụng cho process JVM do tác vụ test khởi chạy. Chúng không tự thay đổi locale và múi giờ của Gradle daemon hoặc các process bên ngoài khác.

Với Maven Surefire, cấu hình trong `pom.xml`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <user.language>en</user.language>
            <user.country>US</user.country>
            <user.timezone>UTC</user.timezone>
        </systemPropertyVariables>
    </configuration>
</plugin>
```

Điều này đặt system property trong JVM chạy test. Nếu một tác vụ khác cũng phụ thuộc locale hoặc múi giờ, hãy cấu hình riêng cho process đó.

### Khi nào nên kiểm thử nhiều locale?

Nếu ứng dụng có người dùng ở nhiều quốc gia, nên có kiểm thử riêng cho các locale quan trọng thay vì chỉ cố định một locale duy nhất. Ví dụ, kiểm thử định dạng số cho `vi-VN`, `en-US` và `de-DE`, hoặc kiểm thử chuyển chữ hoa/chữ thường với `tr-TR`.

Đối với build cần tạo cùng một artifact ở mọi môi trường, nên dùng các quy tắc định dạng độc lập locale và cố định môi trường của tác vụ build. Hai mục tiêu này có thể cùng tồn tại: kiểm thử chức năng nhiều locale để xác nhận hỗ trợ quốc tế hóa, đồng thời dùng một cấu hình build ổn định cho artifact phát hành.

## 7. Đặt cấu hình cho Gradle daemon và Maven

Không phải mọi đoạn code chạy trong quá trình build đều chạy trong JVM của ứng dụng. Gradle có daemon riêng; các tác vụ `Test` hoặc tác vụ fork có thể khởi chạy JVM khác. Maven cũng chạy trong JVM của Maven process và plugin có thể tạo process con.

### Gradle JVM arguments

Có thể cấu hình system property cho Gradle daemon trong `gradle.properties`:

```properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -Duser.language=en -Duser.country=US -Duser.timezone=UTC
```

Nếu tệp đã có `org.gradle.jvmargs`, hãy bổ sung các tùy chọn cần thiết vào giá trị hiện tại thay vì tạo một dòng trùng khóa. Các tùy chọn này điều khiển JVM chạy Gradle daemon; chúng không thay thế cấu hình riêng cho test JVM hoặc process do plugin tạo.

Gradle daemon là process chạy lâu. Nếu bạn thay đổi biến môi trường hoặc cấu hình JVM mà daemon đang sử dụng, hãy dừng daemon cũ rồi chạy lại build để đảm bảo process mới nhận cấu hình:

```shell
./gradlew --stop
./gradlew clean build
```

Trên Windows:

```powershell
.\gradlew.bat --stop
.\gradlew.bat clean build
```

### Maven JVM options

Maven chạy trong JVM được khởi tạo bởi lệnh `mvn`. Có thể truyền JVM option qua `MAVEN_OPTS`:

PowerShell:

```powershell
$env:MAVEN_OPTS = '-Dfile.encoding=UTF-8 -Duser.language=en -Duser.country=US -Duser.timezone=UTC'
mvn clean verify
```

Linux hoặc macOS:

```shell
MAVEN_OPTS='-Dfile.encoding=UTF-8 -Duser.language=en -Duser.country=US -Duser.timezone=UTC' mvn clean verify
```

`MAVEN_OPTS` áp dụng cho JVM khởi chạy Maven. Nếu Surefire hoặc plugin khác fork JVM riêng, cấu hình `systemPropertyVariables`, `argLine` hoặc tùy chọn tương ứng của plugin có thể vẫn cần thiết.

Không phải dự án nào cũng cần đặt tất cả property trên toàn bộ build. Hãy xác định phần nào thực sự phụ thuộc vào charset, locale hoặc múi giờ rồi cấu hình đúng process.

## 8. Kiểm tra môi trường trên máy phát triển và CI

Khi hai môi trường tạo kết quả khác nhau, hãy thu thập thông tin thay vì đoán.

### Kiểm tra Java system properties

Lệnh sau hiển thị các system property liên quan đến môi trường JVM:

```shell
java -XshowSettings:properties -version
```

Tìm các thuộc tính như:

- `file.encoding`: charset mặc định mà Java sử dụng.
- `native.encoding`: encoding gốc của môi trường, nếu runtime cung cấp thuộc tính này.
- `user.language` và `user.country`: thành phần locale mặc định.
- `user.timezone`: múi giờ mặc định được cấu hình hoặc phát hiện.

Tên và giá trị property có thể khác theo phiên bản JDK và cách khởi chạy. Chương trình kiểm tra ở phần trước cũng có thể in trực tiếp `Charset.defaultCharset()`, `Locale.getDefault()` và `ZoneId.systemDefault()`.

### Kiểm tra môi trường shell

Trên Linux hoặc macOS:

```shell
locale
date +%Z
date +%z
```

`locale` cho biết các thiết lập locale của shell; `date` hiển thị thông tin múi giờ mà hệ điều hành đang sử dụng. Các biến như `LANG`, `LC_ALL`, `LC_CTYPE` và `TZ` có thể ảnh hưởng đến process được khởi chạy.

Trên Windows PowerShell:

```powershell
[System.Globalization.CultureInfo]::CurrentCulture.Name
[System.TimeZoneInfo]::Local.Id
chcp
```

`CurrentCulture` và `TimeZoneInfo.Local` cho biết thiết lập của process/hệ điều hành .NET; `chcp` hiển thị code page của console hiện tại. Code page của Terminal có thể ảnh hưởng cách hiển thị output, nhưng không nhất thiết giống charset mặc định của JVM.

### Phân biệt lỗi hiển thị với lỗi dữ liệu

Nếu chữ tiếng Việt hiển thị sai trong Terminal, dữ liệu trong tệp hoặc artifact chưa chắc đã sai. Có thể Terminal đang giải mã output bằng code page khác. Hãy kiểm tra theo từng chặng:

1. Tệp nguồn có được lưu bằng UTF-8 không?
2. Compiler hoặc resource processor có đọc tệp bằng UTF-8 không?
3. Tệp trong artifact có chứa byte đúng không?
4. JVM có giải mã dữ liệu theo đúng charset không?
5. Terminal có hiển thị output theo encoding phù hợp không?

Việc kiểm tra riêng từng chặng giúp xác định lỗi xảy ra khi đọc, xử lý, ghi hay chỉ khi hiển thị.

## 9. Tác động đến tính tái lập của build

Một build có tính tái lập (reproducible build) khi cùng đầu vào và cấu hình được kiểm soát tạo ra kết quả giống nhau theo tiêu chí đã đặt ra, thường là cùng nội dung artifact hoặc cùng checksum. Để đạt điều đó, không chỉ cần khóa dependency; môi trường và metadata do build sinh ra cũng cần ổn định.

### Nội dung văn bản được sinh tự động

Giả sử một tác vụ tạo tệp `build-info.txt` bằng cách ghi ngày hiện tại theo locale mặc định. Máy phát triển có thể ghi:

```text
13/11/2026
```

Trong khi CI có thể ghi:

```text
11/13/2026
```

Hai build có thể dùng cùng mã nguồn nhưng nội dung đầu ra khác nhau vì locale khác nhau. Tương tự, nếu tệp chứa giờ địa phương, múi giờ có thể làm thay đổi nội dung.

Để ổn định, hãy:

- Dùng UTF-8 rõ ràng khi đọc và ghi tệp văn bản.
- Dùng `Locale.ROOT` hoặc locale đã chọn khi định dạng dữ liệu máy đọc.
- Dùng định dạng ISO cho ngày tháng trao đổi và `Instant`/UTC cho timestamp cần chuẩn hóa.
- Sắp xếp danh sách đầu vào bằng comparator xác định trước khi sinh nội dung.
- Tránh đưa thời điểm hiện tại hoặc đường dẫn tuyệt đối của máy build vào artifact nếu không cần thiết.

### Timestamp và thứ tự tệp trong archive

JAR và ZIP có metadata như thời gian của mục lưu trữ. Nếu thời gian lấy trực tiếp từ thời điểm file được tạo hoặc sửa trên từng máy, hai archive có thể khác checksum dù bytecode giống nhau. Thứ tự các mục trong archive cũng có thể ảnh hưởng đến byte của tệp gói.

Với Gradle, các tác vụ archive có thể được cấu hình để không giữ timestamp gốc của từng tệp và dùng thứ tự nội dung có thể tái lập:

```groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Hãy kiểm tra phiên bản Gradle và plugin đang dùng, vì cấu hình archive và mặc định có thể thay đổi theo phiên bản. Tác vụ đóng gói do plugin bên ngoài quản lý cũng cần được kiểm tra riêng.

Với Maven, các phiên bản plugin hỗ trợ reproducible archive có thể dùng thuộc tính `project.build.outputTimestamp`. Ví dụ:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Giá trị cố định ở đây chỉ minh họa cách khai báo. Trong pipeline thực tế, hãy chọn timestamp ổn định theo chính sách phát hành của dự án và xác nhận plugin đóng gói đang dùng có hỗ trợ thuộc tính này. Chỉ đặt property không bảo đảm mọi plugin trong build đều tuân theo nó.

### Môi trường CI nhất quán

Một pipeline có thể kiểm soát các yếu tố sau:

| Yếu tố | Cách kiểm soát |
|---|---|
| JDK | Chọn phiên bản JDK cụ thể hoặc Java toolchain phù hợp. |
| Gradle/Maven | Dùng Gradle Wrapper hoặc phiên bản Maven được pin trong môi trường CI. |
| Dependency | Khai báo phiên bản rõ ràng và dùng dependency locking/verification khi phù hợp. |
| Encoding | Lưu tệp văn bản bằng UTF-8 và cấu hình compiler/resource plugin rõ ràng. |
| Locale | Đặt locale cho process build và test nếu kết quả phụ thuộc locale. |
| Time zone | Dùng UTC cho tác vụ cần timestamp ổn định; truyền `ZoneId` cụ thể cho logic địa phương. |
| Archive metadata | Cấu hình timestamp và thứ tự tệp có thể tái lập. |
| Generated files | Tránh dữ liệu phụ thuộc máy, đường dẫn tuyệt đối hoặc thời điểm chạy không được kiểm soát. |

Build reproducible không có nghĩa mọi ứng dụng phải dùng locale `en-US` hoặc múi giờ UTC trong mọi logic. Ý nghĩa là các đầu vào môi trường có ảnh hưởng đến kết quả phải được xác định rõ, và logic nghiệp vụ cần vùng giờ/ngôn ngữ cụ thể phải nhận chúng như dữ liệu đầu vào.

## 10. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Tiếng Việt thành ký tự lỗi sau khi biên dịch | Tệp nguồn không phải UTF-8 hoặc compiler đọc sai encoding. | Kiểm tra encoding trong editor và cấu hình `javac -encoding UTF-8`/`JavaCompile.options.encoding`. |
| Source compile thành công nhưng resource trong JAR bị lỗi | Resource filtering hoặc plugin đọc/ghi bằng encoding khác. | Kiểm tra encoding của resource plugin và nội dung resource bên trong JAR. |
| Test định dạng số thất bại trên CI | Locale mặc định khác máy phát triển. | Truyền `Locale` tường minh hoặc cấu hình locale cho test JVM. |
| Test ngày giờ lệch vài tiếng | Múi giờ mặc định khác nhau. | Kiểm tra `user.timezone`, dùng `Instant` và `ZoneId` rõ ràng. |
| Tên hoặc thứ tự file sinh ra khác nhau | Sắp xếp phụ thuộc locale hoặc thứ tự liệt kê đầu vào không ổn định. | Dùng comparator xác định và sắp xếp đầu vào trước khi sinh output. |
| JAR có checksum khác giữa hai lần build | Timestamp, thứ tự archive, nội dung sinh từ thời điểm hiện tại hoặc metadata môi trường khác nhau. | So sánh nội dung archive và cấu hình reproducible archive. |
| Log tiếng Việt bị lỗi nhưng file đúng | Code page hoặc cấu hình hiển thị Terminal không phù hợp. | Kiểm tra riêng encoding output và code page của Terminal. |
| Thay đổi biến môi trường nhưng Gradle vẫn dùng giá trị cũ | Gradle daemon cũ còn chạy với môi trường trước đó. | Chạy `gradlew --stop`, sau đó khởi động build mới. |

Khi xử lý lỗi, hãy tìm điểm đầu tiên mà dữ liệu thay đổi. Ví dụ, nếu resource đã sai ngay trong thư mục output sau `processResources`, vấn đề nằm ở bước xử lý resource. Nếu resource đúng trong JAR nhưng hiển thị sai khi ứng dụng chạy, hãy kiểm tra API giải mã và môi trường runtime.

## 11. Quy ước thực tế cho một dự án Java

Một bộ quy ước đơn giản có thể giúp các thành viên tạo kết quả build nhất quán:

1. Lưu mã nguồn, build script và tài nguyên văn bản bằng UTF-8.
2. Khai báo UTF-8 rõ ràng cho Java compiler và các plugin xử lý văn bản.
3. Khi đọc/ghi tệp trong code, truyền `StandardCharsets.UTF_8` nếu định dạng yêu cầu UTF-8.
4. Dùng `Locale.ROOT` cho chuẩn hóa định danh kỹ thuật; truyền locale cụ thể cho nội dung hướng người dùng.
5. Dùng `Instant` hoặc timestamp có offset cho thời điểm tuyệt đối; dùng `ZoneId` cụ thể cho lịch địa phương.
6. Cố định locale và múi giờ của test JVM khi test cần một môi trường ổn định.
7. Kiểm tra locale, timezone, JDK và build tool trong CI.
8. Cấu hình archive reproducible nếu dự án cần so sánh checksum giữa các lần build.
9. Không đưa thời gian hiện tại, đường dẫn máy cá nhân hoặc dữ liệu phụ thuộc môi trường vào artifact nếu không cần thiết.
10. Ghi lại các giả định môi trường quan trọng trong tài liệu build để người khác có thể tái hiện.

Không cần áp đặt một locale duy nhất lên toàn bộ ứng dụng nếu sản phẩm hỗ trợ nhiều ngôn ngữ. Hãy tách quy ước build ổn định khỏi lựa chọn locale và múi giờ của từng người dùng.

## 12. Bài thực hành

Thực hiện các bài tập sau trong một dự án Java nhỏ có Gradle hoặc Maven:

1. Tạo một lớp Java in ra câu tiếng Việt, lưu tệp bằng UTF-8 và biên dịch bằng `javac -encoding UTF-8`.
2. Cấu hình Java compiler trong Gradle hoặc Maven để sử dụng UTF-8, sau đó build mã nguồn có ký tự tiếng Việt.
3. Tạo một tệp resource chứa tiếng Việt, đưa nó vào JAR và kiểm tra nội dung resource trong artifact.
4. Viết chương trình in `Charset.defaultCharset()`, `Locale.getDefault()` và `ZoneId.systemDefault()`. Chạy chương trình với các JVM property khác nhau để quan sát kết quả.
5. Định dạng cùng một số bằng `Locale.US` và `Locale.GERMANY`, sau đó so sánh với API sử dụng locale mặc định.
6. Chuyển một chuỗi kỹ thuật sang chữ thường bằng `toLowerCase()` và `toLowerCase(Locale.ROOT)`. Thử chạy với locale `tr-TR` để thấy khác biệt.
7. Tạo một `Instant`, hiển thị nó ở `UTC` và `Asia/Ho_Chi_Minh`. Giải thích vì sao hai chuỗi có giờ khác nhau nhưng cùng một thời điểm.
8. Cấu hình test JVM dùng locale và timezone cố định, rồi chạy test trên máy phát triển.
9. Build JAR hai lần sau khi clean. So sánh checksum và kiểm tra metadata nếu dự án đặt mục tiêu reproducible build.
10. Ghi lại các thiết lập môi trường mà CI cần có để tạo cùng kết quả với máy phát triển.

Sau bài thực hành, bạn cần phân biệt được encoding, locale và timezone; biết cấu hình UTF-8 cho compiler và resource; hiểu cách locale ảnh hưởng đến định dạng và chuẩn hóa chuỗi; biết dùng `ZoneId` và `Instant` đúng mục đích; đồng thời giải thích được vì sao metadata hoặc dữ liệu sinh theo môi trường có thể làm artifact khác nhau giữa hai lần build.
