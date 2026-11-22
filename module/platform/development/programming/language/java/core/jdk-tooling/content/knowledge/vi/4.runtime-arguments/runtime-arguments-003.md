# System properties trong Java

**System properties** là tập hợp các cặp khóa–giá trị dạng chuỗi mà JVM và ứng dụng Java dùng để trao đổi cấu hình ở cấp tiến trình. Chúng cung cấp thông tin về runtime, hệ điều hành, thư mục làm việc và cho phép truyền cấu hình vào ứng dụng ngay khi khởi chạy.

Trong Java, đọc và quản lý system properties chủ yếu thông qua lớp `java.lang.System` và lớp `java.util.Properties`.

Ví dụ, có thể khởi chạy ứng dụng với chế độ production:

```bash
java -Dapp.mode=production -jar app.jar
```

Trong đó, `app.mode` là một system property do người chạy ứng dụng truyền vào JVM.

## 1. System properties là gì?

System properties là một tập hợp các thuộc tính toàn cục trong một JVM. Mỗi thuộc tính có:

- **Key:** tên thuộc tính, ví dụ `app.mode`.
- **Value:** giá trị dạng `String`, ví dụ `production`.

Một số thuộc tính do JVM hoặc Java launcher thiết lập khi khởi chạy. Ứng dụng cũng có thể đọc, thêm, thay đổi hoặc xóa thuộc tính trong lúc chạy.

Các đặc điểm cần nhớ:

- System properties thuộc phạm vi một tiến trình JVM.
- Giá trị được biểu diễn dưới dạng chuỗi; ứng dụng tự chuyển sang số, boolean hoặc kiểu dữ liệu cần thiết.
- Có thể truyền thuộc tính lúc khởi chạy bằng tùy chọn `-Dkey=value`.
- Có thể truy cập bằng `System.getProperty()`, `System.setProperty()` và `System.getProperties()`.
- Thay đổi trong bộ nhớ không tự động ghi ngược vào file cấu hình hoặc lưu lại cho lần chạy tiếp theo.

System properties thường được dùng cho cấu hình ứng dụng, tùy chọn runtime và thông tin môi trường. Chúng không phải cơ chế lưu trữ dữ liệu lâu dài.

## 2. Phân biệt system properties và environment variables

System properties và biến môi trường (environment variables) đều có thể truyền thông tin cấu hình vào ứng dụng, nhưng chúng là hai cơ chế khác nhau.

| Tiêu chí | System properties | Environment variables |
| --- | --- | --- |
| Truy cập trong Java | `System.getProperty()` | `System.getenv()` |
| Cách truyền phổ biến | Tùy chọn JVM `-Dkey=value` | Môi trường của tiến trình trước khi khởi chạy |
| Phạm vi | JVM hiện tại | Tiến trình và các tiến trình con theo cơ chế của hệ điều hành |
| Cập nhật trong Java | Có thể thay đổi bằng API System | Java API chỉ đọc; không có API chuẩn để sửa môi trường tiến trình |
| Quy ước tên | Thường dùng dạng `app.feature.option` | Thường dùng chữ hoa và dấu gạch dưới, ví dụ `APP_MODE` |
| Ví dụ | `app.mode=production` | `APP_MODE=production` |

Đọc system property:

```java
String mode = System.getProperty("app.mode");
```

Đọc environment variable:

```java
String mode = System.getenv("APP_MODE");
```

Hai lệnh trên đọc hai không gian tên riêng biệt. Đặt biến môi trường `APP_MODE` không tự động tạo system property `app.mode`; ứng dụng cần đọc biến môi trường và tự quyết định cách sử dụng nó.

Khi thiết kế cấu hình, hãy ghi rõ nguồn nào được ưu tiên. Ví dụ, một ứng dụng có thể quy định system property ghi đè environment variable, nhưng đây là quy tắc do ứng dụng xây dựng, không phải thứ tự ưu tiên tự động của JVM.

## 3. Các system properties thường gặp

JVM cung cấp nhiều thuộc tính tiêu chuẩn. Có thể đọc từng thuộc tính bằng `System.getProperty()`.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản Java runtime |
| `java.vendor` | Nhà cung cấp bản phân phối Java |
| `java.home` | Thư mục cài đặt Java runtime |
| `java.vm.name` | Tên máy ảo Java |
| `java.vm.version` | Phiên bản triển khai JVM |
| `java.specification.version` | Phiên bản đặc tả Java |
| `java.class.path` | Classpath của ứng dụng |
| `java.io.tmpdir` | Thư mục tạm mặc định |
| `os.name` | Tên hệ điều hành |
| `os.version` | Phiên bản hệ điều hành |
| `os.arch` | Kiến trúc hệ điều hành/môi trường chạy |
| `user.name` | Tên người dùng của môi trường chạy |
| `user.home` | Thư mục home của người dùng |
| `user.dir` | Thư mục làm việc hiện tại |
| `file.separator` | Ký tự phân cách đường dẫn tệp |
| `path.separator` | Ký tự phân cách các mục classpath |
| `line.separator` | Chuỗi ký tự xuống dòng của môi trường |
| `file.encoding` | Charset mặc định được dùng trong một số API I/O |

Ví dụ đọc một số thuộc tính:

```java
System.out.println("Java version: " + System.getProperty("java.version"));
System.out.println("Java home: " + System.getProperty("java.home"));
System.out.println("OS: " + System.getProperty("os.name"));
System.out.println("Architecture: " + System.getProperty("os.arch"));
System.out.println("Working directory: " + System.getProperty("user.dir"));
```

Các giá trị phụ thuộc vào JDK, hệ điều hành, cách khởi chạy và cấu hình tiến trình. Ví dụ, `user.dir` là thư mục làm việc hiện tại, không nhất thiết là thư mục chứa tệp mã nguồn. `java.class.path` mô tả classpath, không phải danh sách đầy đủ mọi module trên module path.

**Lưu ý về `file.encoding`:** từ JDK 18, UTF-8 là charset mặc định theo JEP 400 trong các cấu hình thông thường. Trên các JDK cũ hơn, charset mặc định có thể phụ thuộc môi trường. Khi cần đọc/ghi dữ liệu có yêu cầu mã hóa cụ thể, hãy chỉ định charset rõ ràng trong API I/O thay vì giả định giá trị mặc định.

## 4. Truyền system properties bằng tùy chọn -D

Tùy chọn `-D` cho phép thiết lập system property ngay khi JVM khởi chạy:

```bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 -cp . SystemPropertiesDemo
```

Cú pháp tổng quát:

```text
java -Dten.thuoc.tinh=gia_tri TenLop
```

Có thể truyền nhiều tùy chọn `-D` trong cùng một lệnh. Mỗi tùy chọn tạo một thuộc tính cho JVM đang chạy.

Với ứng dụng đóng gói thành JAR:

```bash
java -Dapp.mode=production -Dapp.debug=true -jar app.jar
```

**Vị trí của `-D` rất quan trọng:** các tùy chọn JVM phải đứng trước tên lớp chính hoặc trước `-jar`. Nếu viết `-Dapp.mode=production` sau tên lớp hoặc sau `-jar app.jar`, chuỗi đó được chuyển cho chương trình như đối số dòng lệnh, không được Java launcher xử lý như tùy chọn JVM.

Nếu giá trị có khoảng trắng, hãy đặt toàn bộ cặp `-Dkey=value` trong dấu nháy theo cú pháp của shell đang dùng, ví dụ:

```bash
java '-Dapp.display-name=Development Environment' -cp . SystemPropertiesDemo
```

## 5. Đọc system properties trong Java

Lớp `System` cung cấp các phương thức thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `System.getProperty(key)` | Lấy giá trị; trả về `null` nếu key không tồn tại |
| `System.getProperty(key, defaultValue)` | Lấy giá trị hoặc trả về giá trị mặc định |
| `System.getProperties()` | Lấy đối tượng `Properties` chứa các thuộc tính hệ thống |
| `System.setProperty(key, value)` | Thêm hoặc thay đổi một thuộc tính |
| `System.clearProperty(key)` | Xóa một thuộc tính |

### Lấy giá trị và giá trị mặc định

```java
String mode = System.getProperty("app.mode");
String region = System.getProperty("app.region", "local");
```

- Nếu `app.mode` chưa được thiết lập, biến `mode` nhận `null`.
- Nếu `app.region` chưa được thiết lập, biến `region` nhận `local`.

Dùng giá trị mặc định giúp ứng dụng có thể khởi chạy trong môi trường chưa truyền đủ cấu hình. Tuy nhiên, với thuộc tính bắt buộc như endpoint production hoặc chế độ bảo mật, ứng dụng nên kiểm tra và báo lỗi rõ ràng thay vì âm thầm dùng giá trị không phù hợp.

### Đọc boolean và số

Giá trị system property luôn là chuỗi, vì vậy cần chuyển đổi:

```java
boolean debug = Boolean.parseBoolean(
    System.getProperty("app.debug", "false")
);

int port = Integer.parseInt(
    System.getProperty("app.port", "8080")
);
```

`Boolean.parseBoolean()` trả về `true` nếu chuỗi bằng `true` không phân biệt chữ hoa/chữ thường; các giá trị khác, kể cả chuỗi gõ sai, đều cho kết quả `false`. Với cấu hình quan trọng, nên xác thực giá trị đầu vào rõ ràng.

`Integer.parseInt()` có thể ném `NumberFormatException` nếu giá trị không phải số nguyên hợp lệ. Ứng dụng nên kiểm tra định dạng và miền giá trị, ví dụ cổng mạng phải nằm trong khoảng hợp lệ.

## 6. Ví dụ hoàn chỉnh: đọc cấu hình từ -D

Tạo tệp **`SystemPropertiesDemo.java`**:

```java
public class SystemPropertiesDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "development");
        String region = System.getProperty("app.region", "local");
        boolean debug = Boolean.parseBoolean(
            System.getProperty("app.debug", "false")
        );

        System.out.println("app.mode=" + mode);
        System.out.println("app.region=" + region);
        System.out.println("app.debug=" + debug);
    }
}
```

Biên dịch:

```bash
javac SystemPropertiesDemo.java
```

Chạy với các system properties:

```bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 -Dapp.debug=true -cp . SystemPropertiesDemo
```

Kết quả chính xác:

```text
app.mode=production
app.region=ap-southeast-1
app.debug=true
```

Nếu chạy không truyền `-D`:

```bash
java -cp . SystemPropertiesDemo
```

Kết quả:

```text
app.mode=development
app.region=local
app.debug=false
```

Ví dụ cho thấy `System.getProperty(key, defaultValue)` sử dụng giá trị mặc định khi thuộc tính chưa được truyền vào JVM.

## 7. Thay đổi và xóa system properties khi chương trình đang chạy

Có thể thay đổi thuộc tính bằng `System.setProperty()`:

```java
String previous = System.setProperty("app.mode", "test");
System.out.println("Current mode: " + System.getProperty("app.mode"));
```

Phương thức trả về giá trị cũ nếu thuộc tính đã tồn tại; nếu chưa tồn tại, kết quả trả về là `null`.

Xóa thuộc tính:

```java
String previous = System.clearProperty("app.mode");
```

Sau khi xóa, `System.getProperty("app.mode")` trả về `null`, trừ khi ứng dụng thiết lập lại thuộc tính đó.

Những thay đổi này có phạm vi toàn JVM. Mã nguồn, thư viện hoặc thread khác trong cùng tiến trình có thể đọc được giá trị mới. Vì vậy:

- Chỉ thay đổi thuộc tính khi có lý do rõ ràng.
- Tránh dùng system properties làm nơi lưu trạng thái riêng của từng request hoặc từng thread.
- Không thay đổi các thuộc tính chuẩn của JVM để giả lập hệ điều hành hoặc phiên bản Java khác.
- Nếu nhiều thành phần cùng đọc một thuộc tính, cần quy định rõ thời điểm và quyền thay đổi.

`System.getProperties()` trả về đối tượng `Properties` đang dùng làm bộ thuộc tính hệ thống. Có thể duyệt tên thuộc tính bằng:

```java
for (String key : System.getProperties().stringPropertyNames()) {
    System.out.println(key + "=" + System.getProperty(key));
}
```

Không nên in toàn bộ system properties trong log production vì giá trị có thể chứa đường dẫn nội bộ, tên tài khoản hoặc thông tin môi trường nhạy cảm.

`System.setProperties(properties)` thay thế toàn bộ đối tượng system properties. Đây là thao tác có phạm vi ảnh hưởng lớn và thường không cần thiết trong ứng dụng thông thường. Khi chỉ muốn thay đổi một giá trị, ưu tiên `System.setProperty()`.

## 8. Đọc cấu hình từ tệp Properties

System properties không phải là tệp cấu hình. Nếu ứng dụng cần lưu nhiều thiết lập trong tệp, có thể dùng lớp `java.util.Properties` với một đối tượng riêng.

Ví dụ tệp **`app.properties`**:

```properties
app.mode=staging
app.region=ap-southeast-1
app.timeout.seconds=30
```

Đọc tệp bằng UTF-8 trong Java 17:

```java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesFileDemo {
    public static void main(String[] args) throws IOException {
        Properties config = new Properties();

        try (Reader reader = Files.newBufferedReader(
                Path.of("app.properties"), StandardCharsets.UTF_8)) {
            config.load(reader);
        }

        String mode = config.getProperty("app.mode", "development");
        System.out.println("Mode: " + mode);
    }
}
```

Nếu tệp có nội dung như ví dụ trên, kết quả là:

```text
Mode: staging
```

Ở đây, `config` là đối tượng cấu hình riêng của ứng dụng. Việc gọi `config.load(reader)` không tự động thay đổi `System.getProperty()`.

Một lưu ý về mã hóa:

- `Properties.load(InputStream)` dùng quy tắc ISO-8859-1 và hỗ trợ escape Unicode.
- `Properties.load(Reader)` đọc ký tự từ Reader mà ứng dụng cung cấp.
- Với tệp UTF-8, có thể dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` rồi truyền Reader vào `load()`.

Nếu muốn nạp tệp vào system properties, có thể thao tác trên đối tượng trả về từ `System.getProperties()`, nhưng điều đó sẽ đưa cấu hình vào phạm vi toàn JVM. Chỉ làm vậy khi thiết kế ứng dụng thực sự yêu cầu; thông thường nên giữ cấu hình ứng dụng trong đối tượng riêng để dễ kiểm soát.

## 9. Thứ tự ưu tiên cấu hình

JVM không áp đặt một thứ tự ưu tiên chung cho mọi nguồn cấu hình của ứng dụng. Một ứng dụng có thể nhận cấu hình từ:

1. Giá trị mặc định trong mã nguồn.
2. Tệp cấu hình.
3. Environment variables.
4. System properties truyền bằng `-D`.
5. Đối số dòng lệnh.
6. Giá trị được thiết lập trực tiếp trong lúc chạy.

Ứng dụng phải tự định nghĩa cách hợp nhất các nguồn này. Một quy ước phổ biến là giá trị truyền rõ ràng lúc chạy sẽ ghi đè giá trị mặc định, nhưng thứ tự cụ thể phải được ghi trong tài liệu của ứng dụng.

Ví dụ, nếu ứng dụng quy định system property ưu tiên hơn tệp cấu hình, có thể viết:

```java
String mode = System.getProperty(
    "app.mode",
    config.getProperty("app.mode", "development")
);
```

Cách viết này có nghĩa:

- Nếu system property `app.mode` tồn tại, dùng nó.
- Nếu không, dùng giá trị trong đối tượng `config`.
- Nếu cả hai đều không có, dùng `development`.

Lưu ý: ví dụ trên chỉ minh họa thứ tự do ứng dụng chọn. JVM không tự động đọc mọi tệp `app.properties` rồi hợp nhất với `-D`.

## 10. Quy ước đặt tên và thiết kế cấu hình

Nên đặt tên system properties theo dạng phân cấp, chữ thường và phân tách bằng dấu chấm:

```text
app.mode
app.http.port
app.http.connect-timeout-ms
app.logging.level
app.feature.new-checkout.enabled
```

Một số nguyên tắc hữu ích:

- Dùng tiền tố riêng của ứng dụng hoặc tổ chức để tránh trùng tên.
- Dùng tên thể hiện rõ ý nghĩa và đơn vị của giá trị.
- Xác định giá trị mặc định và hành vi khi thiếu cấu hình.
- Xác thực giá trị khi chuyển chuỗi sang số, boolean hoặc enum.
- Tài liệu hóa thuộc tính nào bắt buộc, thuộc tính nào tùy chọn và ví dụ hợp lệ.
- Tránh dùng tên thuộc tính thuộc namespace của JVM như `java.*` cho cấu hình riêng của ứng dụng.

System properties là cấu hình toàn cục trong một JVM. Nếu cần cấu hình khác nhau cho từng đối tượng, request hoặc thread, hãy dùng đối tượng cấu hình được truyền rõ ràng thay vì thay đổi thuộc tính toàn cục.

## 11. Bảo mật khi sử dụng system properties

Không nên xem system properties là kho lưu trữ bí mật.

Tránh truyền mật khẩu, access token, private key hoặc thông tin xác thực nhạy cảm qua `-D`, vì giá trị dòng lệnh có thể xuất hiện trong danh sách tiến trình, log khởi chạy, công cụ giám sát hoặc dữ liệu chẩn đoán.

Ngoài ra:

- Không ghi toàn bộ `System.getProperties()` vào log production.
- Không đưa bí mật vào file cấu hình được commit lên Git.
- Dùng secret manager hoặc cơ chế quản lý bí mật phù hợp với nền tảng triển khai.
- Kiểm tra và giới hạn quyền truy cập đối với tệp cấu hình.
- Xác thực giá trị cấu hình trước khi dùng trong kết nối mạng, đường dẫn tệp hoặc thao tác hệ thống.

Một system property thường có thể được đọc bởi các thành phần mã chạy trong cùng JVM. Không dùng nó để cô lập dữ liệu bí mật giữa các thư viện hoặc module.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `System.getProperty("app.mode")` trả về `null` | Chưa truyền `-Dapp.mode=...` hoặc ứng dụng chưa thiết lập property | Kiểm tra lệnh khởi chạy và dùng giá trị mặc định nếu phù hợp |
| `-Dapp.mode=production` không có tác dụng | Đặt tùy chọn sau tên lớp hoặc sau `-jar` | Đưa `-D` lên trước tên lớp chính hoặc `-jar` |
| Environment variable không xuất hiện qua `getProperty()` | Đang đọc nhầm cơ chế cấu hình | Dùng `System.getenv()` hoặc ánh xạ biến môi trường sang cấu hình |
| Boolean luôn thành `false` | Giá trị không phải chuỗi `true` hợp lệ | Kiểm tra chính tả và xác thực giá trị trước khi chuyển đổi |
| Chuyển số bị lỗi | Giá trị rỗng hoặc không phải số | Kiểm tra đầu vào và xử lý `NumberFormatException` |
| Ứng dụng không nhận thay đổi từ file | Đang nạp vào đối tượng `Properties` riêng nhưng lại đọc từ `System.getProperty()` | Đọc từ đúng đối tượng cấu hình hoặc thiết kế bước ánh xạ rõ ràng |
| Log chứa thông tin môi trường nhạy cảm | In toàn bộ system properties | Chỉ log các key đã được cho phép và loại bỏ giá trị nhạy cảm |

## 13. Ghi nhớ

- System properties là các cặp key–value dạng chuỗi thuộc phạm vi một JVM.
- Dùng `-Dkey=value` trước tên lớp chính hoặc `-jar` để truyền thuộc tính lúc khởi chạy.
- Dùng `System.getProperty()` để đọc, `System.setProperty()` để thêm/thay đổi và `System.clearProperty()` để xóa.
- Dùng `System.getenv()` để đọc environment variables; hai cơ chế không tự động ánh xạ cho nhau.
- Dùng `java.util.Properties` để quản lý tệp cấu hình; một đối tượng `Properties` riêng không đồng nghĩa với system properties.
- Ứng dụng tự quy định thứ tự ưu tiên giữa file, environment variables, system properties và đối số dòng lệnh.
- Không lưu bí mật hoặc in toàn bộ system properties vào log.

Khi cần cấu hình JVM hoặc truyền một vài giá trị lúc chạy, system properties là cơ chế đơn giản và hữu ích. Với cấu hình lớn, bí mật hoặc cần thay đổi độc lập theo môi trường, hãy chọn cơ chế cấu hình chuyên biệt và xác định rõ cách hợp nhất các nguồn giá trị.
