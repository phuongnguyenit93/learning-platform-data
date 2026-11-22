# Property file trong Java

## 1. Property file là gì?

Property file là tệp cấu hình dạng văn bản, thường có phần mở rộng **.properties**, dùng để lưu các cặp khóa và giá trị. Java cung cấp lớp **java.util.Properties** để đọc, truy xuất, cập nhật và ghi loại cấu hình này.

Ví dụ một file **app.properties**:

~~~properties
# Application settings
app.name=Ứng dụng học Java
app.timeout.seconds=30
app.audit.enabled=true
server.host=localhost
server.port=8080
~~~

Mỗi khóa đại diện cho một thuộc tính cấu hình, chẳng hạn tên ứng dụng, thời gian chờ, trạng thái một tính năng hoặc địa chỉ máy chủ. Chương trình đọc giá trị theo khóa thay vì phải sửa mã nguồn mỗi khi thay đổi môi trường chạy.

Property file phù hợp với cấu hình đơn giản có cấu trúc phẳng. Nó lưu giá trị dưới dạng chuỗi; việc chuyển chuỗi thành số, boolean, enum, đường dẫn hoặc kiểu dữ liệu khác là trách nhiệm của chương trình. Định dạng này không tự cung cấp cấu trúc object lồng nhau, danh sách hay kiểm tra kiểu như một schema.

Cần phân biệt ba khái niệm thường bị gọi chung là “property”:

- **Property file:** file văn bản chứa các cặp khóa và giá trị.
- **Properties object:** đối tượng Java của lớp java.util.Properties, thường được dùng để giữ nội dung đã đọc từ file.
- **Java system property:** thuộc tính toàn cục của JVM, truy cập qua System.getProperty và System.setProperty. Đây là một cơ chế riêng; đọc một file .properties không tự động đưa các khóa vào system properties.

## 2. Cấu trúc và cú pháp của file .properties

Một file .properties thường gồm các dòng trống, dòng chú thích và các dòng khai báo thuộc tính.

### Khóa và giá trị

Các dạng phân tách hợp lệ phổ biến:

~~~properties
server.host=localhost
server.port:8080
app.mode production
~~~

Dấu bằng, dấu hai chấm hoặc khoảng trắng có thể phân tách khóa và giá trị. Trong thực tế, nên thống nhất dùng dấu bằng để file dễ đọc và ít gây nhầm lẫn.

Tên khóa thường dùng chữ thường, dấu chấm để phân nhóm và tên có ý nghĩa rõ ràng:

~~~properties
database.url=jdbc:postgresql://localhost:5432/app
database.pool.maximum-size=20
feature.audit.enabled=true
http.client.connect-timeout-ms=3000
~~~

Tên khóa là định danh do ứng dụng quy ước. Java không tự hiểu rằng hậu tố **.enabled** phải là boolean hoặc **.timeout-ms** phải là số nguyên.

### Chú thích và dòng trống

Dòng bắt đầu bằng dấu **#** hoặc **!** sau phần khoảng trắng đầu dòng là chú thích. Dòng trống được bỏ qua.

~~~properties
# HTTP server configuration
server.host=127.0.0.1

! The port used by the local server
server.port=8080
~~~

Chú thích giúp giải thích mục đích, đơn vị, giá trị hợp lệ và ảnh hưởng khi thay đổi cấu hình. Nên ghi rõ đơn vị trong tên khóa hoặc chú thích, ví dụ timeout tính bằng mili giây hay giây.

### Ký tự đặc biệt và escape

Trong file .properties, dấu phân tách đầu tiên chưa được escape (dấu bằng, dấu hai chấm hoặc khoảng trắng) kết thúc khóa và bắt đầu giá trị. Sau khi parser đã chuyển sang phần giá trị, dấu bằng và dấu hai chấm là ký tự thông thường; không cần escape chúng trong value. Nếu muốn dấu bằng hoặc dấu hai chấm thuộc chính tên khóa, hãy escape chúng trong key.

Dấu gạch chéo ngược có ý nghĩa riêng. Dùng hai dấu gạch chéo ngược để lưu một dấu gạch chéo ngược thực tế; các escape điều khiển thường gặp là \t, \n, \r, \f và escape Unicode \uXXXX. Dấu cách ở đầu value có thể được giữ bằng cách escape dấu cách đó. Dấu gạch chéo ngược ở cuối dòng biểu thị nối dòng, vì vậy cần cẩn thận khi lưu đường dẫn hoặc chuỗi kết thúc bằng dấu gạch chéo ngược.

Ví dụ:

~~~properties
message=Hello World
display.label=Java: Runtime
endpoint=https://example.test:8443/api?mode=a=b
path=C:\\apps\\java
key\:with\:colon=value
key\=with\=equals=value
leading.space=\ value
~~~

Sau khi nạp, các giá trị tương ứng là Java: Runtime, https://example.test:8443/api?mode=a=b, C:\apps\java và value có dấu cách đầu. Hai khóa cuối lần lượt chứa dấu hai chấm và dấu bằng trong tên khóa. Khi xử lý dữ liệu do người dùng nhập, hãy kiểm tra giá trị sau khi load bằng Properties.getProperty thay vì đoán cách parser diễn giải chuỗi escape.

## 3. Lớp java.util.Properties

**Properties** nằm trong package java.util và kế thừa Hashtable. Lớp này được thiết kế cho các bảng thuộc tính với khóa và giá trị dạng chuỗi.

Các phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| Properties() | Tạo bảng thuộc tính rỗng. |
| Properties(Properties defaults) | Tạo bảng có một bảng mặc định để tra cứu khi khóa không tồn tại trong bảng chính. |
| setProperty(key, value) | Đặt một thuộc tính với khóa và giá trị String. |
| getProperty(key) | Lấy giá trị String; trả về null nếu không tìm thấy. |
| getProperty(key, defaultValue) | Lấy giá trị hoặc trả về giá trị mặc định nếu không tìm thấy. |
| load(Reader) | Đọc nội dung từ luồng ký tự. |
| load(InputStream) | Đọc nội dung từ luồng byte theo quy tắc encoding của API này. |
| store(Writer, comments) | Ghi thuộc tính ra luồng ký tự. |
| store(OutputStream, comments) | Ghi thuộc tính ra luồng byte theo quy tắc encoding của API này. |
| stringPropertyNames() | Lấy tập các khóa có cả khóa và giá trị là String, bao gồm khóa mặc định chưa bị ghi đè. |
| propertyNames() | Trả về Enumeration các khóa trong bảng và các khóa mặc định chưa bị ghi đè. |

Nên dùng **setProperty** và **getProperty** cho cấu hình thông thường. Properties kế thừa các phương thức put/get của Hashtable nên về mặt kỹ thuật có thể chứa đối tượng không phải String, nhưng dữ liệu đó không phù hợp với các thao tác property tiêu chuẩn. getProperty chỉ trả về giá trị String; stringPropertyNames chỉ liệt kê các mục có cả khóa và giá trị dạng String.

### Giá trị mặc định

Có hai cách phổ biến để cung cấp giá trị mặc định:

Cách thứ nhất là dùng overload của getProperty:

~~~java
String host = properties.getProperty("server.host", "localhost");
~~~

Cách thứ hai là tạo một bảng mặc định:

~~~java
Properties defaults = new Properties();
defaults.setProperty("server.host", "localhost");
defaults.setProperty("server.port", "8080");

Properties properties = new Properties(defaults);
~~~

Khi gọi getProperty, nếu bảng chính không có khóa thì Properties tra cứu tiếp trong bảng defaults. Nếu đặt khóa trong bảng chính, giá trị ở bảng chính được ưu tiên. Bảng mặc định có thể được xâu chuỗi qua các đối tượng Properties khác.

Một điểm cần nhớ: store ghi các thuộc tính được đặt trực tiếp trong bảng chính; các giá trị chỉ có trong bảng defaults không được tự động ghi ra file. Nếu cần lưu cấu hình sau khi hợp nhất, hãy quyết định rõ những giá trị nào cần được materialize vào bảng chính.

## 4. Đọc property file từ hệ thống file

Cách đọc file bên ngoài thường dùng khi người vận hành cần thay đổi cấu hình mà không đóng gói lại ứng dụng. Dùng Path, Files và Reader để kiểm soát đường dẫn cũng như encoding.

Ví dụ đọc file UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertyFileDemo {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        Path configFile = Path.of("app.properties");
        try (var reader = Files.newBufferedReader(
                configFile, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        String appName = properties.getProperty("app.name", "Unnamed");
        int timeoutSeconds = Integer.parseInt(
                properties.getProperty("app.timeout.seconds", "10"));

        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException(
                    "app.timeout.seconds must be positive");
        }

        String auditText = properties.getProperty(
                "app.audit.enabled", "false");
        if (!auditText.equalsIgnoreCase("true")
                && !auditText.equalsIgnoreCase("false")) {
            throw new IllegalArgumentException(
                    "app.audit.enabled must be true or false");
        }
        boolean auditEnabled = Boolean.parseBoolean(auditText);

        System.out.println("Application: " + appName);
        System.out.println("Timeout seconds: " + timeoutSeconds);
        System.out.println("Audit enabled: " + auditEnabled);
    }
}
~~~

Đặt file app.properties ở thư mục làm việc hiện tại:

~~~properties
app.name=Ứng dụng học Java
app.timeout.seconds=30
app.audit.enabled=true
~~~

Biên dịch và chạy từ thư mục chứa cả hai file:

~~~bash
javac PropertyFileDemo.java
java PropertyFileDemo
~~~

Kết quả:

~~~text
Application: Ứng dụng học Java
Timeout seconds: 30
Audit enabled: true
~~~

Ví dụ dùng Files.newBufferedReader với UTF-8 nên đọc được tiếng Việt trực tiếp. Path.of với đường dẫn tương đối được phân giải dựa trên thư mục làm việc hiện tại của tiến trình, thường quan sát qua system property user.dir. Nếu ứng dụng được khởi chạy từ IDE, service manager hoặc container, thư mục làm việc có thể khác thư mục chứa file JAR. Với cấu hình production, nên truyền đường dẫn rõ ràng hoặc dùng một vị trí cấu hình được quy ước.

Try-with-resources tự đóng Reader kể cả khi load phát sinh lỗi. IOException được truyền ra main trong ví dụ; ứng dụng thực tế có thể bắt lỗi tại ranh giới khởi động để bổ sung tên file, môi trường và hướng dẫn khắc phục. Không nên âm thầm tiếp tục chạy với cấu hình rỗng khi file bắt buộc bị thiếu hoặc không đọc được.

### Encoding: InputStream và Reader khác nhau

Đây là điểm rất dễ gây lỗi với file có dấu tiếng Việt:

- **load(InputStream)** diễn giải byte theo ISO-8859-1. Ký tự ngoài tập này phải được biểu diễn bằng escape Unicode theo định dạng properties.
- **load(Reader)** nhận dữ liệu ký tự đã được giải mã. Ứng dụng chọn encoding khi tạo Reader, ví dụ UTF-8.
- **store(OutputStream, comments)** ghi theo định dạng tương thích với load(InputStream), sử dụng ISO-8859-1 và escape những ký tự không biểu diễn được.
- **store(Writer, comments)** ghi ký tự ra Writer; encoding phụ thuộc Writer mà ứng dụng cung cấp.

Vì vậy, nếu file cấu hình được lưu UTF-8 và có tiếng Việt, hãy dùng Reader UTF-8 khi đọc. Khi ghi file UTF-8, hãy tạo Writer UTF-8 rồi gọi store(Writer, comments). Đừng giả định rằng load(InputStream) tự nhận diện UTF-8.

## 5. Đọc file .properties từ classpath

Cấu hình mặc định thường được đóng gói cùng ứng dụng trong resources, ví dụ **src/main/resources/app.properties**. Khi build, file này được đưa vào classpath và có thể đọc qua Class hoặc ClassLoader.

Ví dụ đọc resource ở gốc classpath:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class ClasspathProperties {
    public static Properties loadDefaults() throws IOException {
        Properties properties = new Properties();

        try (InputStream input = ClasspathProperties.class
                .getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: /app.properties");
            }

            try (var reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {
                properties.load(reader);
            }
        }

        return properties;
    }
}
~~~

Với getResourceAsStream trên Class, dấu gạch chéo ở đầu đường dẫn biểu thị đường dẫn tính từ gốc classpath. Nếu bỏ dấu gạch chéo, đường dẫn được tính tương đối với package của class. Với ClassLoader, đường dẫn resource thường không bắt đầu bằng dấu gạch chéo.

Classpath resource phù hợp với cấu hình mặc định hoặc tài nguyên chỉ đọc. Khi ứng dụng đã đóng gói thành JAR, resource nằm bên trong JAR không phải file hệ thống thông thường để ghi đè tại chỗ. Nếu người vận hành cần thay đổi cấu hình theo môi trường, hãy đặt file bên ngoài và cho phép ứng dụng nhận đường dẫn file đó.

Một cách tổ chức thường gặp:

- File đóng gói trong classpath cung cấp giá trị mặc định an toàn.
- File bên ngoài cung cấp cấu hình riêng của môi trường triển khai.
- JVM system properties hoặc environment variables cung cấp các giá trị cần override khi khởi chạy.

## 6. Hợp nhất nhiều nguồn cấu hình

Java không tự áp đặt thứ tự ưu tiên chung giữa property file, system properties và environment variables. Ứng dụng phải định nghĩa thứ tự này.

Ví dụ, một chính sách có thể là:

1. Giá trị mặc định trong mã hoặc bảng defaults có độ ưu tiên thấp nhất.
2. File app.properties được đóng gói trong classpath ghi đè giá trị mặc định.
3. File cấu hình bên ngoài ghi đè file classpath.
4. JVM system property được truyền bằng tùy chọn -D ghi đè file.
5. Environment variable được ánh xạ rõ ràng vào khóa cấu hình có độ ưu tiên cao nhất.

Đây là chính sách do ứng dụng chọn, không phải hành vi tự động của lớp Properties. Khi áp dụng, cần ghi rõ quy ước ánh xạ tên biến môi trường sang khóa, cách xử lý giá trị rỗng và nguồn nào được phép cung cấp secret.

Ví dụ hợp nhất hai nguồn file và một system property:

~~~java
Properties config = new Properties();
config.setProperty("service.timeout.seconds", "10");

// Nạp file cấu hình mặc định trước.
try (var reader = Files.newBufferedReader(
        Path.of("app-defaults.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}

// Nạp file ngoài sau; cùng khóa sẽ ghi đè giá trị trước.
try (var reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}

// Chỉ override khóa mà ứng dụng chủ động hỗ trợ.
String timeoutOverride = System.getProperty("service.timeout.seconds");
if (timeoutOverride != null) {
    config.setProperty("service.timeout.seconds", timeoutOverride);
}
~~~

Environment variable có thể được đọc qua System.getenv. Ví dụ, ứng dụng tự quy định SERVICE_TIMEOUT_SECONDS sẽ ghi đè khóa service.timeout.seconds. Không có quy tắc chung tự chuyển dấu gạch dưới thành dấu chấm trong Java; việc ánh xạ phải được viết rõ.

Đừng đưa toàn bộ System.getProperties vào bảng cấu hình ứng dụng một cách thiếu chọn lọc. JVM có nhiều system property nội bộ và thuộc về thư viện khác. Chỉ đọc hoặc chuyển các khóa mà ứng dụng chủ động hỗ trợ.

Khi nhiều nguồn có cùng khóa, nguồn được nạp sau hoặc thao tác setProperty sau cùng sẽ giữ giá trị trong bảng chính. Hãy giữ thứ tự nạp dễ hiểu và có thể kiểm thử.

## 7. Java system properties và tùy chọn -D

Java system properties là các giá trị gắn với JVM hiện tại. Có thể đọc chúng qua System.getProperty:

~~~java
String javaVersion = System.getProperty("java.version");
String userHome = System.getProperty("user.home");
~~~

Có thể truyền thuộc tính khi khởi chạy JVM bằng tùy chọn -D, đặt trước tên class hoặc tùy chọn khởi chạy ứng dụng:

~~~bash
java -Dservice.timeout.seconds=45 -Dservice.mode=production Main
~~~

Trong chương trình, đọc bằng:

~~~java
String mode = System.getProperty("service.mode", "development");
~~~

System.setProperty cho phép đặt một system property trong lúc chạy. Thay đổi này ảnh hưởng đến các phần của ứng dụng và thư viện cùng dùng JVM đó, nên chỉ nên dùng khi có chủ đích. System.clearProperty xóa một khóa. System.setProperties thay thế toàn bộ bảng system properties và có thể làm hỏng giả định của thư viện khác; thông thường không nên dùng nó để nạp file cấu hình ứng dụng.

Các system properties không tự động được lưu lại sau khi JVM kết thúc. Chúng cũng không đồng nghĩa với biến môi trường của hệ điều hành: System.getenv đọc environment variables, còn System.getProperty đọc system properties.

## 8. Ghi và cập nhật property file

Properties có thể ghi nội dung ra file bằng store. Ví dụ ghi UTF-8:

~~~java
try (var writer = Files.newBufferedWriter(
        Path.of("app-generated.properties"), StandardCharsets.UTF_8)) {
    properties.store(writer, "Generated application settings");
}
~~~

Với Writer UTF-8, nội dung ký tự được ghi theo encoding của Writer. Nếu dùng store(OutputStream), định dạng tương thích load(InputStream) và quy tắc ISO-8859-1/escape được áp dụng.

Cần hiểu các đặc điểm sau trước khi ghi:

- store thêm phần chú thích và thời điểm ghi ở đầu file.
- Properties không cam kết giữ thứ tự ban đầu của các khóa.
- Các chú thích và cách trình bày gốc của file không được bảo toàn như một trình soạn thảo cấu hình.
- Giá trị trong bảng defaults không được tự động ghi như giá trị trực tiếp.
- Ghi file thường thay thế nội dung đích; cần xử lý backup, quyền file và lỗi ghi nếu file là cấu hình đang được vận hành.

Vì vậy, store phù hợp để sinh file cấu hình do chương trình sở hữu. Nếu cần sửa một file do con người quản lý mà vẫn giữ nguyên chú thích, thứ tự và định dạng, Properties không phải công cụ chỉnh sửa văn bản bảo toàn cấu trúc. Hãy dùng quy trình cập nhật có kiểm soát hoặc một parser phù hợp với yêu cầu đó.

Java cũng hỗ trợ loadFromXML và storeToXML cho định dạng XML của Properties. Đây là một lựa chọn khác nếu hệ thống đã dùng XML; với file cấu hình đơn giản, dạng .properties thường ngắn gọn và dễ thao tác hơn.

## 9. Chuyển đổi kiểu và kiểm tra cấu hình

Properties lưu giá trị dạng String, do đó cần chuyển đổi và kiểm tra trước khi dùng.

Một số cách chuyển đổi phổ biến:

- Số nguyên: Integer.parseInt.
- Số dài: Long.parseLong.
- Số thực: Double.parseDouble.
- Boolean: Boolean.parseBoolean.
- Enum: Enum.valueOf sau khi chuẩn hóa giá trị theo quy ước.
- Đường dẫn: Path.of.
- Thời lượng: parse số kèm đơn vị hoặc dùng Duration theo một định dạng đã quy định.

Boolean.parseBoolean chỉ trả về true nếu chuỗi bằng true, không phân biệt chữ hoa chữ thường; các chuỗi khác, kể cả lỗi chính tả, đều trả về false. Nếu cấu hình chỉ chấp nhận true hoặc false, hãy kiểm tra chuỗi trước khi chuyển đổi.

Nên kiểm tra cấu hình ngay khi ứng dụng khởi động:

1. Xác nhận khóa bắt buộc tồn tại.
2. Chuyển đổi sang kiểu mong muốn và báo lỗi nếu không hợp lệ.
3. Kiểm tra miền giá trị, ví dụ port trong khoảng hợp lệ hoặc timeout phải lớn hơn 0.
4. Kiểm tra quan hệ giữa các khóa, ví dụ bật TLS thì phải có cấu hình chứng thư.
5. Tạo một đối tượng cấu hình bất biến để các thành phần khác sử dụng.

Không nên để lỗi cấu hình chỉ xuất hiện ở giữa một request hoặc sau khi ứng dụng đã nhận traffic. Thông báo lỗi nên chỉ rõ tên khóa và điều kiện cần đáp ứng, nhưng không đưa giá trị secret vào log.

## 10. Vòng đời, chia sẻ và đồng thời

Properties kế thừa Hashtable nên các thao tác cơ bản trên bảng được đồng bộ hóa. Tuy nhiên, một chuỗi thao tác gồm nhiều bước không tự động trở thành một giao dịch nguyên tử. Ví dụ, kiểm tra khóa rồi mới cập nhật giá trị có thể bị một thread khác xen vào giữa hai thao tác.

Nếu nhiều thread cùng đọc cấu hình, cách đơn giản là nạp và kiểm tra cấu hình một lần khi khởi động, sau đó chia sẻ một snapshot chỉ đọc hoặc một đối tượng cấu hình bất biến. Nếu ứng dụng hỗ trợ reload, hãy tạo bảng mới, kiểm tra toàn bộ, rồi thay thế tham chiếu cấu hình bằng một thao tác đồng bộ phù hợp. Tránh sửa từng khóa trong một bảng đang được nhiều thành phần sử dụng nếu chúng có thể nhìn thấy trạng thái cập nhật dở dang.

Properties không tự theo dõi thay đổi file và không tự reload khi file được sửa. Nếu cần reload tự động, ứng dụng phải triển khai cơ chế theo dõi, lịch kiểm tra hoặc nhận tín hiệu cập nhật, đồng thời định nghĩa cách xử lý khi file mới không hợp lệ.

## 11. Bảo mật khi dùng file cấu hình

File cấu hình có thể chứa thông tin nhạy cảm như mật khẩu database, token, private key path hoặc thông tin kết nối nội bộ. Hãy coi quyền đọc file cấu hình là một phần của bảo mật ứng dụng.

- Không commit secret vào repository công khai hoặc file cấu hình mẫu.
- Dùng secret manager hoặc cơ chế cấp phát secret của nền tảng triển khai cho dữ liệu nhạy cảm.
- Nếu phải lưu secret trên đĩa, giới hạn quyền truy cập file và bảo vệ backup.
- Không in toàn bộ Properties object hoặc toàn bộ system properties ra log.
- Không đưa secret vào tên tham số, thông báo lỗi hay output chẩn đoán.
- Tránh truyền mật khẩu qua command line nếu môi trường có thể để lộ danh sách tiến trình hoặc lịch sử lệnh.
- Chỉ nạp file từ đường dẫn và nguồn đã được tin cậy; kiểm soát quyền ghi để người không có thẩm quyền không thể thay đổi cấu hình.

Environment variable cũng không mặc nhiên là nơi lưu secret an toàn. Chọn cơ chế dựa trên khả năng bảo vệ, quyền truy cập, audit và cách nền tảng cấp phát secret.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| getProperty trả về null | Sai tên khóa, file chưa được load hoặc đường dẫn resource không đúng. | Kiểm tra khóa, vị trí file và kết quả mở resource. |
| Tiếng Việt bị lỗi ký tự | Dùng load(InputStream) cho file UTF-8 hoặc Reader sai encoding. | Dùng Reader UTF-8 với load(Reader). |
| Giá trị luôn là giá trị mặc định | Khóa trong file sai chính tả hoặc nguồn ghi đè chưa được nạp. | Kiểm tra thứ tự nạp và tên khóa. |
| File không tìm thấy | Đường dẫn tương đối được tính từ working directory khác dự kiến. | In user.dir khi chẩn đoán hoặc truyền đường dẫn tuyệt đối/đã cấu hình. |
| NumberFormatException | Giá trị số có chữ, sai định dạng hoặc vượt giới hạn kiểu. | Kiểm tra đầu vào và báo tên khóa bị lỗi. |
| Boolean luôn false | Boolean.parseBoolean chỉ nhận true, các giá trị khác đều thành false. | Validate rõ true/false trước khi chuyển đổi. |
| Cấu hình cũ vẫn được dùng | Properties không tự reload file. | Triển khai cơ chế reload hoặc khởi động lại theo quy trình. |
| Mất chú thích sau khi ghi | store chỉ ghi các cặp thuộc tính và chú thích sinh ra, không bảo toàn chú thích gốc. | Tránh dùng Properties để chỉnh file do con người sở hữu nếu cần giữ định dạng. |
| Khóa bị ghi đè ngoài dự kiến | Nạp nhiều file hoặc setProperty theo thứ tự không rõ ràng. | Định nghĩa và kiểm thử precedence. |

Khi chẩn đoán, có thể in danh sách tên khóa thay vì in giá trị:

~~~java
properties.stringPropertyNames().stream()
        .sorted()
        .forEach(System.out::println);
~~~

Không dùng cách này để log các giá trị có thể chứa thông tin nhạy cảm.

## 13. Checklist khi thiết kế cấu hình bằng Properties

- [ ] Tên khóa rõ nghĩa, nhất quán và có đơn vị khi cần.
- [ ] Đã xác định file nằm trên classpath hay bên ngoài ứng dụng.
- [ ] Đã chọn encoding rõ ràng; file UTF-8 được đọc bằng Reader UTF-8.
- [ ] Đã xác định giá trị mặc định và khóa bắt buộc.
- [ ] Đã định nghĩa thứ tự ưu tiên giữa file, system property và environment variable.
- [ ] Đã chuyển đổi kiểu và kiểm tra miền giá trị khi khởi động.
- [ ] Đã xử lý trường hợp file thiếu, sai encoding hoặc không có quyền đọc.
- [ ] Đã tránh ghi secret và giá trị nhạy cảm vào log hoặc repository.
- [ ] Đã quyết định cách cập nhật, reload và chia sẻ cấu hình giữa các thread.
- [ ] Đã xác định file do chương trình sinh hay do con người quản lý trước khi dùng store.

Property file và java.util.Properties cung cấp một cách đơn giản để tách cấu hình khỏi mã nguồn. Khi kiểm soát rõ encoding, đường dẫn, giá trị mặc định, thứ tự ghi đè, kiểm tra kiểu và bảo mật, cấu hình sẽ dễ triển khai nhất quán giữa máy phát triển, CI và production.