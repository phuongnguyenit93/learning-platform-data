# Đối chiếu biến môi trường, thuộc tính JVM và tham số dòng lệnh trong Spring Boot

## Mục tiêu

Khi một ứng dụng Spring Boot chạy trên máy lập trình, máy chủ hoặc container, cùng một thuộc tính cấu hình có thể được khai báo ở nhiều nơi. Ví dụ, giá trị của **app.report.timeout** có thể xuất hiện trong application.yml, biến môi trường của hệ điều hành, thuộc tính hệ thống JVM hoặc tham số truyền cho ứng dụng khi khởi động. Để xử lý sự cố cấu hình, cần trả lời được ba câu hỏi: giá trị đến từ đâu, nguồn nào thắng khi trùng khóa, và làm sao xác minh giá trị thực sự mà Spring Boot sử dụng.

Sau bài này, người học có thể:

- Phân biệt biến môi trường (environment variable), thuộc tính hệ thống Java (JVM system property) và tham số dòng lệnh của ứng dụng (Spring Boot command-line argument).
- Dự đoán giá trị có hiệu lực khi các nguồn cùng khai báo một khóa.
- Viết đúng cú pháp truyền cấu hình trên Linux/macOS, Windows PowerShell và môi trường triển khai.
- Hiểu cách Spring Boot ánh xạ tên biến môi trường vào thuộc tính qua relaxed binding.
- Chẩn đoán trường hợp giá trị trong Spring Environment khác với giá trị đọc trực tiếp từ JVM hoặc hệ điều hành.

## 1. Ba nguồn cấu hình là ba cơ chế khác nhau

| Nguồn | Ai sở hữu giá trị? | Cú pháp điển hình | Cách truy cập trực tiếp | Phạm vi |
| --- | --- | --- | --- | --- |
| Biến môi trường | Hệ điều hành, shell, container hoặc bộ điều phối | APP_REPORT_TIMEOUT=30s | System.getenv("APP_REPORT_TIMEOUT") | Tiến trình được cấp biến và các tiến trình con kế thừa |
| JVM system property | Máy ảo Java của tiến trình hiện tại | -Dapp.report.timeout=45s | System.getProperty("app.report.timeout") | Một JVM |
| Tham số dòng lệnh Spring Boot | Đối số ứng dụng nhận sau khi khởi chạy JAR | --app.report.timeout=60s | ApplicationArguments và Spring Environment | Một lần chạy ứng dụng |

**Biến môi trường** được thiết lập trước hoặc khi tạo tiến trình. Các nền tảng như Docker, Kubernetes, CI/CD và dịch vụ chạy ứng dụng thường cung cấp cơ chế truyền chúng mà không phải sửa gói JAR.

**JVM system property** là cặp khóa/giá trị Java quản lý trong tiến trình. Có thể truyền bằng tùy chọn **-D** khi gọi lệnh **java**, hoặc đặt bằng System.setProperty(...) trong chương trình. Đây không phải biến môi trường của hệ điều hành.

**Tham số dòng lệnh của Spring Boot** là đối số dạng **--tên.thuộc.tính=giá-trị** được truyền vào phương thức main(String[] args). Mặc định, SpringApplication chuyển các option arguments này thành một PropertySource để Spring Environment có thể tra cứu.

Điểm quan trọng: **System.getenv**, **System.getProperty** và **Environment.getProperty** không phải ba cách gọi tương đương. Hai cách đầu đọc trực tiếp một loại nguồn; cách cuối tra cứu theo thứ tự ưu tiên của các PropertySource mà Spring đã tập hợp.

## 2. Ví dụ đối chiếu cùng một khóa

Giả sử ứng dụng có cấu hình mặc định:

~~~yaml
# src/main/resources/application.yml
app:
  report:
    timeout: 15s
~~~

Chạy trên Linux/macOS:

~~~bash
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

Cả bốn nguồn đều cung cấp khóa logic **app.report.timeout**. Trong tình huống chạy Spring Boot thông thường, kết quả như sau:

| Nguồn | Giá trị | Kết quả |
| --- | --- | --- |
| application.yml | 15s | Bị ghi đè |
| Biến môi trường APP_REPORT_TIMEOUT | 30s | Bị ghi đè |
| Thuộc tính JVM -Dapp.report.timeout | 45s | Bị ghi đè |
| Tham số ứng dụng --app.report.timeout | 60s | **Giá trị có hiệu lực** |

Nếu bỏ tham số **--app.report.timeout=60s**, giá trị hiệu lực chuyển thành **45s**. Nếu đồng thời bỏ **-Dapp.report.timeout=45s**, giá trị chuyển thành **30s**. Nếu không có cả ba nguồn bên ngoài, ứng dụng lấy **15s** từ application.yml.

Ví dụ cấu hình Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(Duration timeout) {
}
~~~

Khi cấu hình này được đăng ký qua **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(ReportProperties.class)**, thuộc tính timeout được bind thành Duration tương ứng với **60 giây** trong lần chạy ở trên. Tên khóa hợp lệ cũng có thể được truy cập qua **Environment.getProperty("app.report.timeout")**; không cần biết nó đến từ nguồn nào.

Thử nhìn trực tiếp vào Java và Spring:

~~~java
@Component
public class ConfigurationProbe implements ApplicationRunner {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("OS: " + System.getenv("APP_REPORT_TIMEOUT"));
        System.out.println("JVM: " + System.getProperty("app.report.timeout"));
        System.out.println("Spring: " + environment.getProperty("app.report.timeout"));
        System.out.println("CLI: " + args.getOptionValues("app.report.timeout"));
    }
}
~~~

Trong ví dụ đã chạy, bốn dòng lần lượt cho thấy **30s**, **45s**, **60s**, và danh sách chứa **60s**. Điều này giải thích vì sao việc in System.getProperty(...) để “kiểm tra cấu hình Spring” có thể dẫn đến kết luận sai: giá trị thắng cuộc nằm trong Spring Environment, không nhất thiết nằm ở JVM system properties.

## 3. Thứ tự ưu tiên: nguồn nào ghi đè nguồn nào?

Đối với các nguồn chính trong bài này, xét cùng một tên thuộc tính và cùng một lần khởi động Spring Boot thông thường:

~~~text
Tham số dòng lệnh Spring Boot (--key=value)
                  cao hơn
Thuộc tính hệ thống JVM (-Dkey=value)
                  cao hơn
Biến môi trường hệ điều hành (KEY=value)
                  cao hơn
Cấu hình trong application.properties / application.yml
~~~

Spring Boot có nhiều nguồn cấu hình khác ngoài bốn nhóm trên, vì vậy đây là thứ tự **giữa các nguồn đang so sánh**, không phải toàn bộ thứ tự ưu tiên trong mọi ngữ cảnh. Chẳng hạn, **SPRING_APPLICATION_JSON** là nguồn đặc biệt có thể ưu tiên cao hơn system properties và biến môi trường thông thường; các nguồn dành riêng cho kiểm thử hoặc thiết lập DevTools cũng có vị trí riêng. Những file cấu hình profile, file bên ngoài JAR và tài liệu YAML nhiều đoạn còn có quy tắc ưu tiên *bên trong nhóm config data*.

Spring duyệt tập hợp PropertySource theo độ ưu tiên để tìm giá trị của khóa được hỏi. Khi hai nguồn chứa một khóa logic tương đương, nguồn có độ ưu tiên cao hơn quyết định kết quả. Việc ghi đè này không làm thay đổi file application.yml, biến môi trường hoặc JVM system property gốc.

Ví dụ có thể hiểu bằng phép thử loại bỏ từng nguồn:

~~~bash
# Chỉ cấu hình file: mặc định 15s
java -jar demo.jar

# Biến môi trường thắng file: 30s
APP_REPORT_TIMEOUT=30s java -jar demo.jar

# JVM thắng biến môi trường: 45s
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar

# Tham số Spring Boot thắng JVM: 60s
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

**Lưu ý về phạm vi:** Nếu một ứng dụng chủ động thêm PropertySource tùy biến với độ ưu tiên khác, hoặc tắt cơ chế nhận command-line properties, kết quả phải được xét theo cấu hình thực tế của ứng dụng. Các ví dụ phía trên sử dụng hành vi mặc định của Spring Boot.

## 4. Đúng vị trí của -D và -- khi chạy JAR

Lệnh này có ba phần khác nhau:

~~~text
[BIẾN_MÔI_TRƯỜNG] java [TÙY_CHỌN_JVM] -jar [TÊN_JAR] [ĐỐI_SỐ_ỨNG_DỤNG]
~~~

Ví dụ đúng:

~~~bash
SERVER_PORT=8081 java -Dserver.port=8082 -jar demo.jar --server.port=8083
~~~

- **SERVER_PORT=8081** cấp biến môi trường cho tiến trình Java.
- **-Dserver.port=8082** đứng trước **-jar** nên JVM nhận nó là system property.
- **--server.port=8083** đứng sau tên JAR nên Spring Boot nhận nó như application argument.
- Cổng HTTP cuối cùng sẽ là **8083**, giả sử ứng dụng sử dụng web server Spring Boot mặc định và không có nguồn ưu tiên cao hơn can thiệp.

Lệnh sau rất dễ bị hiểu nhầm:

~~~bash
java -jar demo.jar -Dserver.port=8082
~~~

Vì **-Dserver.port=8082** nằm sau JAR, đây là đối số của ứng dụng, không phải tùy chọn JVM. Spring Boot mặc định nhận command-line property từ cú pháp **--server.port=8082** (hai dấu gạch ngang), nên đối số **-D...** ở vị trí này không có tác dụng cấu hình như mong đợi.

Trên Windows PowerShell, cú pháp đặt biến môi trường khác với Bash:

~~~powershell
$env:APP_REPORT_TIMEOUT = "30s"
java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

Biến thiết lập bằng **$env:** tồn tại trong phiên PowerShell hiện tại và được truyền cho tiến trình khởi chạy từ phiên đó. Nếu muốn kiểm chứng lần chạy không có biến ấy, có thể xóa nó khỏi môi trường phiên shell trước lần chạy tiếp theo.

## 5. Tên biến môi trường và relaxed binding

Tên trong application.yml thường dùng chữ thường, dấu chấm và dấu gạch nối, còn tên biến môi trường thường dùng chữ hoa và dấu gạch dưới. Spring Boot hỗ trợ **relaxed binding** để bind các dạng viết tương ứng vào thuộc tính cấu hình.

Với tên cấu hình chuẩn, quy tắc chuyển sang biến môi trường là:

1. Thay dấu chấm **.** bằng dấu gạch dưới **_**.
2. Bỏ dấu gạch nối **-** trong mỗi phần tên.
3. Chuyển tất cả chữ cái thành chữ hoa.

Ví dụ:

| Thuộc tính Spring Boot | Biến môi trường tương ứng |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| app.report.timeout | APP_REPORT_TIMEOUT |
| app.payment.retry-count | APP_PAYMENT_RETRYCOUNT |

Ví dụ cuối cùng rất đáng chú ý: **app.payment.retry-count** chuyển thành **APP_PAYMENT_RETRYCOUNT** theo quy tắc chính thức dành cho environment variables. Không nên tự suy luận rằng mọi dấu gạch nối đều phải biến thành một dấu gạch dưới mới. Với cấu hình tự thiết kế, dùng tên canonical chữ thường và kebab-case để cách bind rõ ràng, nhất quán.

Nếu bind danh sách, chỉ số thường được kẹp bởi dấu gạch dưới; chẳng hạn tên môi trường **MY_SERVICE_0_OTHER** có thể tương ứng với **my.service[0].other** khi bind vào cấu trúc phù hợp.

**Giới hạn cần nhớ:** Relaxed binding hỗ trợ ánh xạ kiểu tên, không biến mọi tên tùy ý thành cùng một thuộc tính. Đặc biệt, tên khóa trong map, chỉ số list và các ký tự không chuẩn cần được xét theo quy tắc binding của cấu trúc dữ liệu đó. Khi có nghi ngờ, kiểm tra giá trị mà bean **@ConfigurationProperties** thực sự nhận.

## 6. Phân biệt đọc cấu hình qua ba API

Đoạn mã dưới minh họa cùng một khóa nhưng ba nguồn truy cập:

~~~java
String fromOs = System.getenv("APP_REPORT_TIMEOUT");
String fromJvm = System.getProperty("app.report.timeout");
String fromSpring = environment.getProperty("app.report.timeout");
~~~

- **System.getenv(...)** chỉ trả về biến của tiến trình; nó không biết file application.yml, **-D**, hay **--**.
- **System.getProperty(...)** chỉ trả về thuộc tính hệ thống JVM; nó không tự áp dụng thứ tự ưu tiên của Spring.
- **Environment.getProperty(...)** tra cứu trong các PropertySource đã đăng ký, qua đó phản ánh độ ưu tiên của Spring tại thời điểm đọc.
- **@Value** và **@ConfigurationProperties** sử dụng cơ chế phân giải cấu hình của Spring; với **@ConfigurationProperties**, binding còn hỗ trợ chuyển kiểu như Duration, DataSize, boolean và cấu trúc lồng nhau.

Ví dụ khi đọc **Environment.getProperty("app.report.timeout")** và đối chiếu với **ReportProperties.timeout()**, giá trị chuỗi và đối tượng Duration khác nhau về kiểu biểu diễn nhưng có cùng ý nghĩa nếu binding thành công. Hãy kiểm tra cả giá trị lẫn kiểu dữ liệu khi debug các lỗi chuyển đổi.

Khi chương trình tự gọi System.setProperty(...) trong runtime, giá trị mới có thể ảnh hưởng lần tra cứu Environment tiếp theo nếu system properties đang được dùng làm PropertySource. Tuy nhiên, bean cấu hình đã được tạo và bind trước đó không đương nhiên được bind lại. Không nên coi việc sửa system property sau khi ứng dụng đã chạy là cơ chế cập nhật nóng an toàn.

## 7. Truyền cấu hình trong container và pipeline

Với Docker, nhóm tham số vẫn giữ bản chất như khi chạy trực tiếp trên máy:

~~~bash
docker run --rm -e APP_REPORT_TIMEOUT=30s demo-image
~~~

Biến này được gắn vào môi trường của tiến trình trong container. Nếu image dùng entrypoint để chạy **java -jar demo.jar**, Spring Boot có thể bind **APP_REPORT_TIMEOUT** giống một biến môi trường trên máy vật lý.

Trong Kubernetes, phần **env** của container có vai trò tương tự:

~~~yaml
containers:
  - name: demo
    image: demo-image
    env:
      - name: APP_REPORT_TIMEOUT
        value: "30s"
~~~

Khi container đồng thời được khởi chạy với **-Dapp.report.timeout=45s** hoặc đối số ứng dụng **--app.report.timeout=60s**, độ ưu tiên vẫn tuân theo PropertySource của Spring Boot. Docker/Kubernetes chỉ quyết định cách cung cấp giá trị cho tiến trình, không tự thay đổi thứ tự ưu tiên của Spring.

Đối với cấu hình nhạy cảm, không đưa mật khẩu hay token thật vào ví dụ lệnh, commit hoặc bản ghi log. Tùy nền tảng, tham số dòng lệnh và biến môi trường có thể xuất hiện trong công cụ giám sát tiến trình hay cấu hình triển khai. Dùng cơ chế quản lý secret thích hợp và giới hạn quyền xem thông tin cấu hình.

## 8. Các tình huống thực tế dễ gây sai lệch

### 8.1. Có biến môi trường nhưng ứng dụng vẫn nhận giá trị khác

Kiểm tra trước tiên xem **-D** hoặc **--** có cùng khóa không. Một biến môi trường tồn tại không có nghĩa nó được ưu tiên cao nhất. Với một launcher hoặc script khởi chạy, cần xem đối số mà script thực sự truyền cho JVM và ứng dụng.

### 8.2. Đặt -D phía sau -jar

Đây là vị trí của đối số ứng dụng, không phải JVM option. Hãy di chuyển **-Dkey=value** ra trước **-jar**, hoặc dùng **--key=value** sau JAR nếu muốn tận dụng cơ chế command-line properties của Spring Boot.

### 8.3. Nhập tên biến môi trường chưa đúng

Đối chiếu tên canonical với quy tắc relaxed binding; phân biệt dấu chấm giữa các phần, dấu gạch nối bên trong tên và chỉ số của danh sách. Khi cấu hình đã được bind vào class, kiểm tra tên prefix và tên trường của class đó.

### 8.4. Truyền --key=value nhưng giá trị không thay đổi

Mặc định SpringApplication thêm command-line properties; tuy nhiên ứng dụng có thể gọi **SpringApplication.setAddCommandLineProperties(false)** và tắt cơ chế đó. Cũng cần kiểm tra đối số có thực sự đến được phương thức **main(String[] args)** hay bị script/launcher xử lý trước đó.

### 8.5. Hai nguồn có giá trị giống nhau

Nếu file và biến môi trường đều ghi **30s**, chỉ nhìn giá trị cuối không thể kết luận nguồn nào thắng. Muốn xác định nguồn, phải kiểm tra tập hợp PropertySource hoặc công cụ chẩn đoán hỗ trợ hiển thị nguồn gốc cấu hình.

### 8.6. Giá trị rỗng không giống với việc không khai báo

Một biến môi trường được gắn giá trị rỗng có thể vẫn được xem là một giá trị cấu hình được cung cấp. Với một số thuộc tính, điều này có thể dẫn tới kết quả rỗng hoặc lỗi chuyển kiểu, thay vì tự động quay về giá trị trong application.yml. Cần phân biệt rõ biến **không tồn tại**, biến **tồn tại nhưng rỗng** và biến **có giá trị**.

### 8.7. Cấu hình được dùng quá sớm

Các khóa như **spring.config.location**, **spring.config.additional-location** và **spring.config.name** ảnh hưởng giai đoạn Spring Boot tìm và tải file cấu hình. Các giá trị này nên được truyền từ nguồn có sẵn ở thời điểm khởi động sớm, như biến môi trường, system property hoặc command-line argument. Không thể trông chờ một file chỉ được tìm thấy nhờ khóa ấy tự hướng dẫn Spring Boot tìm chính nó.

### 8.8. Đang chạy kiểm thử Spring Boot

Trong môi trường test, **@SpringBootTest(properties = ...)**, **@TestPropertySource** và **@DynamicPropertySource** có thể thêm PropertySource với độ ưu tiên khác môi trường chạy JAR thông thường. Vì vậy, kết quả kiểm thử không nhất thiết chứng minh thứ tự giữa mọi nguồn trong bản triển khai sản xuất.

## 9. Cách chẩn đoán cấu hình có hiệu lực

Bước đầu tiên là chọn **một khóa cụ thể** đang gây vấn đề, ví dụ **app.report.timeout**, và ghi lại cách ứng dụng được khởi chạy. Sau đó kiểm tra lần lượt:

1. **File cấu hình:** application.yml, application.properties và các file theo profile đang hoạt động có khai báo khóa ấy không?
2. **Biến môi trường của tiến trình:** tên đã được đổi đúng theo relaxed binding chưa và thực sự tồn tại trong tiến trình ứng dụng chưa?
3. **JVM options:** có **-Dapp.report.timeout=...** ở trước **-jar** hoặc trong cấu hình JVM của launcher không?
4. **Application arguments:** có **--app.report.timeout=...** trong các args mà SpringApplication nhận không?
5. **Spring Environment:** **environment.getProperty("app.report.timeout")** thực sự trả về gì?
6. **Bean tiêu thụ:** bean đọc lúc nào, có bind thành kiểu khác hay có logic tự xử lý sau khi nhận cấu hình không?

Khi ứng dụng có Spring Boot Actuator và endpoint được cấu hình, bảo vệ phù hợp, endpoint **/actuator/env** hoặc đường dẫn tra cứu theo tên thuộc tính có thể giúp tìm giá trị và nguồn gốc. Dữ liệu nhạy cảm có thể bị ẩn; việc endpoint không hiển thị toàn bộ giá trị không có nghĩa cấu hình bị mất. Không bật công khai endpoint env chỉ để debug một biến.

Khi cần xem PropertySource bằng mã, có thể duyệt tên nguồn mà không in toàn bộ giá trị:

~~~java
@Component
class PropertySourceInspector implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    PropertySourceInspector(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Thứ tự và danh sách nguồn trong một ứng dụng cụ thể giúp lý giải vì sao cấu hình đã khai báo lại không được chọn. Để tra cứu chính xác nguồn chứa một khóa, cần xét khả năng tên khóa được chuẩn hóa và cơ chế xử lý riêng của các PropertySource; việc in toàn bộ nội dung chúng có nguy cơ lộ secret nên chỉ dùng dữ liệu đã được lọc an toàn.

## 10. Bài thực hành: dự đoán rồi quan sát

Giữ **app.report.timeout=15s** trong application.yml và tạo một lần chạy có ba nguồn bên ngoài:

~~~bash
APP_REPORT_TIMEOUT=20s java -Dapp.report.timeout=25s -jar demo.jar --app.report.timeout=30s
~~~

Hãy dự đoán kết quả đọc từ **System.getenv("APP_REPORT_TIMEOUT")**, **System.getProperty("app.report.timeout")** và **Environment.getProperty("app.report.timeout")**. Sau đó, bỏ riêng tham số **--app.report.timeout=30s**, chạy lại và so sánh. Cuối cùng, bỏ thêm **-Dapp.report.timeout=25s** rồi thực hiện lại phép đo.

Kết quả kỳ vọng theo hành vi mặc định:

| Lần chạy | System.getenv | System.getProperty | Spring Environment |
| --- | --- | --- | --- |
| Có đủ cả ba nguồn ngoài file | 20s | 25s | **30s** |
| Bỏ tham số -- | 20s | 25s | **25s** |
| Bỏ cả -- và -D | 20s | null | **20s** |
| Bỏ luôn biến môi trường | null | null | **15s** |

Bài thực hành này chỉ ra một nguyên tắc xuyên suốt: **không thể xác định giá trị cấu hình Spring Boot bằng cách nhìn riêng từng biến môi trường hoặc JVM property; phải xét tất cả nguồn tham gia và độ ưu tiên của chúng**. Khi nắm được ba loại đầu vào và biết kiểm tra Spring Environment, người phát triển có thể giải thích phần lớn các lỗi “đã cấu hình nhưng ứng dụng không nhận” mà không cần sửa mã nghiệp vụ.