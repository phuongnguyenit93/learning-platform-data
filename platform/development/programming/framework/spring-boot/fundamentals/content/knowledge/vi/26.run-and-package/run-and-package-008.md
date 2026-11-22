# Thư mục làm việc, đường dẫn tương đối và cấu hình ngoài

Một ứng dụng Spring Boot có thể chạy tốt trong IDE nhưng thất bại khi đóng gói thành executable JAR, chạy qua systemd, Docker hoặc Kubernetes. File cấu hình phụ trợ không được tìm thấy, thư mục log xuất hiện ở nơi khác, đường dẫn upload trỏ nhầm vào thư mục không có quyền ghi, hoặc application-prod.yml không được nạp dù đã đặt cạnh file JAR. Rất nhiều lỗi kiểu này bắt nguồn từ việc nhầm ba khái niệm:

- **Thư mục làm việc (working directory / current working directory, CWD):** thư mục mà tiến trình Java dùng làm gốc cho những đường dẫn filesystem tương đối.
- **Vị trí của file JAR và classpath:** nơi lưu chương trình và những resource được đóng gói cùng nó; không nhất thiết trùng với CWD.
- **Vị trí cấu hình ngoài (external configuration):** những file hoặc thư mục Spring Boot được chỉ định tìm khi xây dựng Environment, có quy tắc riêng về search location, thứ tự ưu tiên và profile.

Bài học phân biệt các khái niệm trên, giải thích đường dẫn tương đối/đường dẫn tuyệt đối, cách dùng Spring Resource, cách Spring Boot tìm application.yml và application-prod.yml, cách nạp cấu hình từ ngoài JAR, và cách triển khai an toàn ở IDE, terminal, service, container.

## 1. Ba loại vị trí dễ bị nhầm lẫn

Giả sử server có cấu trúc:

~~~text
/opt/order-service/
├── order-api.jar
└── resources/
    └── seed.csv

/etc/order-service/
└── application-prod.yml

/var/lib/order-service/
└── uploads/

/var/log/order-service/
└── application.log
~~~

Bạn đứng ở thư mục /tmp và chạy:

~~~bash
cd /tmp
java -jar /opt/order-service/order-api.jar
~~~

Trong ví dụ:

| Vị trí | Vai trò | Có nhất thiết là CWD không? |
|---|---|---|
| /tmp | Thư mục làm việc của tiến trình chạy từ shell | Có, trong tình huống trên |
| /opt/order-service/order-api.jar | Vị trí artifact | Không |
| /etc/order-service/application-prod.yml | Cấu hình triển khai | Không |
| /var/lib/order-service/uploads | Dữ liệu runtime cần lưu | Không |
| /var/log/order-service/application.log | Đầu ra log theo cấu hình | Không |

Nếu code dùng:

~~~java
Path.of("uploads/order.csv");
~~~

thì đường dẫn đó được hiểu tương đối từ CWD, trong trường hợp trên là:

~~~text
/tmp/uploads/order.csv
~~~

Nó **không tự chuyển thành**:

~~~text
/opt/order-service/uploads/order.csv
~~~

chỉ vì file JAR nằm ở /opt/order-service.

Đây là quy tắc nền tảng: **đường dẫn filesystem tương đối không tự lấy thư mục chứa executable JAR làm gốc**.

## 2. Thư mục làm việc của process Java được xác định như thế nào?

Working directory thường do môi trường khởi chạy quyết định:

- Terminal: thư mục hiện tại khi gọi lệnh.
- IDE: trường working directory trong run configuration, hoặc giá trị mặc định của IDE.
- Gradle bootRun: working directory của Java process theo cấu hình task.
- systemd: thiết lập WorkingDirectory= trong unit, hoặc mặc định của service manager.
- Docker: WORKDIR của image hoặc thiết lập working_dir lúc chạy.
- Kubernetes: workingDir của container hoặc WORKDIR kế thừa từ image.
- CI/CD: thư mục thực thi của job/runner theo cấu hình pipeline.

Vì vậy, cùng một file JAR và cùng một đường dẫn tương đối có thể đọc/ghi vào những vị trí hoàn toàn khác nhau.

### 2.1. Đọc user.dir và chuyển một Path thành tuyệt đối

Java cung cấp system property **user.dir**, thường phản ánh working directory của JVM.

~~~java
import java.nio.file.Path;

public class WorkingDirectoryDemo {
    public static void main(String[] args) {
        String workingDirectory =
                System.getProperty("user.dir");

        Path relative = Path.of("data/input.csv");

        System.out.println("Working directory: "
                + workingDirectory);
        System.out.println("Relative path: " + relative);
        System.out.println("Absolute path: "
                + relative.toAbsolutePath().normalize());
    }
}
~~~

Ví dụ process khởi động từ /srv/my-app:

~~~text
Working directory: /srv/my-app
Relative path: data/input.csv
Absolute path: /srv/my-app/data/input.csv
~~~

Đây là ví dụ minh họa; kết quả còn phụ thuộc hệ điều hành và cấu hình process.

### 2.2. Đừng dùng user.dir như nơi lưu dữ liệu vĩnh viễn

**user.dir** giúp chẩn đoán CWD. Nó không tự đảm bảo:

- Thư mục có quyền ghi.
- Dữ liệu còn tồn tại khi container bị thay thế.
- Các replica cùng nhìn thấy một thư mục.
- Ổ đĩa có đủ dung lượng.
- Thư mục đó là nơi phù hợp cho secret, upload hoặc log.

Nếu cần lưu dữ liệu có vòng đời dài, hãy cấu hình một **data directory rõ ràng** và bảo đảm hạ tầng cấp volume, quyền truy cập và backup theo yêu cầu.

### 2.3. Thay đổi user.dir trong lúc chạy không phải cách chuyển CWD đáng tin cậy

Ví dụ không nên dùng làm giải pháp:

~~~java
System.setProperty("user.dir", "/another/path");
~~~

Các API, thư viện và cơ chế filesystem có thể đã khởi tạo hoặc resolve đường dẫn trước đó. Thay đổi property này không phải hợp đồng đảm bảo chuyển working directory thật của toàn bộ process.

Hãy xác định CWD **khi khởi chạy**, hoặc tốt hơn, dùng một base directory tường minh và resolve các đường dẫn của ứng dụng từ đó.

## 3. Đường dẫn tương đối, tuyệt đối và chuẩn hóa với Path

Java NIO cung cấp **Path** để làm việc với filesystem.

~~~java
Path a = Path.of("data/input.csv");
Path b = Path.of("/var/lib/my-app/data/input.csv");
~~~

Trên Linux, a là tương đối và b là tuyệt đối. Trên Windows, cú pháp đường dẫn tuyệt đối thường có drive letter như **C:\\data\\input.csv** hoặc UNC path; hãy để Path xử lý cú pháp theo hệ điều hành thay vì tự ghép dấu phân cách bằng String.

### 3.1. isAbsolute, resolve và normalize

~~~java
import java.nio.file.Path;

Path base = Path.of("/var/lib/my-app");
Path child = Path.of("reports/../input/order.csv");

Path resolved = base.resolve(child).normalize();

System.out.println(child.isAbsolute());
System.out.println(resolved);
~~~

Kết quả trên hệ thống Unix:

~~~text
false
/var/lib/my-app/input/order.csv
~~~

- **resolve** ghép một đường dẫn con vào base directory.
- **normalize** loại các thành phần cú pháp dư thừa như dấu chấm và các cặp thư mục/.. theo quy tắc chuẩn hóa lexical.
- **toAbsolutePath** biến đường dẫn tương đối thành một đường dẫn tuyệt đối dựa trên ngữ cảnh hiện hành.

### 3.2. normalize không xác nhận file tồn tại

~~~java
Path location = Path.of("/missing/folder/../file.txt")
        .normalize();
~~~

Path trên có thể được tạo và normalize dù file thực tế không tồn tại. Việc kiểm tra tồn tại, quyền đọc hoặc thao tác mở vẫn cần thực hiện riêng.

### 3.3. toRealPath khác normalize

~~~java
Path real = path.toRealPath();
~~~

**toRealPath** yêu cầu tương tác filesystem và có thể resolve symbolic links, kiểm tra file tồn tại (theo options) hoặc ném IOException.

**normalize** chỉ xử lý cấu trúc path ở mức ký tự, không tự kiểm tra symlink và không bảo đảm đường dẫn nằm trong thư mục được phép sau khi symlink được resolve.

Đây là khác biệt quan trọng khi xử lý đường dẫn đến từ người dùng không tin cậy.

### 3.4. Tránh ghép đường dẫn bằng dấu gạch chéo thủ công

Ví dụ:

~~~java
String filename = "orders.csv";
String path = baseDir + "/" + filename;
~~~

có thể tạo đường dẫn sai khi baseDir đã có separator, khi chạy đa nền tảng hoặc khi filename chứa thành phần đường dẫn bất ngờ.

Nên:

~~~java
Path file = baseDir.resolve(filename);
~~~

Với API nhận Path, hãy ưu tiên thao tác Path thay vì tự nối String.

## 4. Classpath resource không giống filesystem path

Khi Spring Boot đóng gói ứng dụng:

~~~text
src/main/resources/
├── templates/
│   └── invoice.txt
└── data/
    └── countries.csv
~~~

các file này được đưa vào classpath của runtime.

Đọc bằng Spring:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class ResourceReader {
    public byte[] readCountries() throws IOException {
        Resource resource =
                new ClassPathResource("data/countries.csv");

        try (InputStream in = resource.getInputStream()) {
            return in.readAllBytes();
        }
    }
}
~~~

**ClassPathResource** tìm dữ liệu trong classpath, không tương đối từ user.dir.

### 4.1. Vì sao không dùng src/main/resources khi runtime?

Sai cho ứng dụng đã đóng gói:

~~~java
Path path = Path.of(
        "src/main/resources/data/countries.csv");
~~~

Trong IDE, path này có thể tình cờ tồn tại vì CWD trùng root của source project.

Khi chạy executable JAR, file có thể nằm bên trong:

~~~text
order-api.jar
└── BOOT-INF
    └── classes
        └── data
            └── countries.csv
~~~

Nó không nhất thiết có bản sao dưới một thư mục **src/main/resources** trên server.

### 4.2. Resource.getFile() không phải lúc nào cũng dùng được

Ví dụ:

~~~java
File file = new ClassPathResource(
        "data/countries.csv").getFile();
~~~

có thể chạy trong IDE khi resource nằm ở thư mục classes, nhưng thất bại nếu nó nằm trong JAR và không có file filesystem độc lập.

Hãy dùng:

~~~java
try (InputStream in = new ClassPathResource(
        "data/countries.csv").getInputStream()) {
    // Xử lý byte từ classpath.
}
~~~

Nếu một thư viện bắt buộc cần Path/File thực, phải có chính sách extract ra file tạm hoặc cấu hình resource nằm ngoài JAR, kèm cleanup và bảo mật phù hợp.

### 4.3. ResourceLoader hiểu nhiều loại location

Spring cung cấp:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

Resource resource =
        resourceLoader.getResource(
                "classpath:data/countries.csv");
~~~

Các prefix quen thuộc:

~~~text
classpath:data/countries.csv
file:/var/lib/my-app/data/countries.csv
https://example.invalid/data/countries.csv
~~~

Đường dẫn có prefix **classpath:** tham chiếu classpath; prefix **file:** chỉ file URL/location; URL mạng có rủi ro latency và security riêng.

Không chuyển trực tiếp một chuỗi location từ HTTP request của người dùng cho ResourceLoader mà không kiểm soát vì có thể tạo rủi ro đọc file nội bộ hoặc SSRF.

## 5. Dữ liệu đóng gói và dữ liệu thay đổi ngoài JAR

Hai loại dữ liệu nên được xử lý khác nhau:

| Loại dữ liệu | Vị trí phù hợp | Lý do |
|---|---|---|
| Template cố định, dữ liệu tham khảo nhỏ theo phiên bản code | Classpath trong JAR | Đi cùng artifact, dễ tái lập bản build. |
| File upload của người dùng | Data directory/volume/object storage | Phải tồn tại và được quản lý độc lập với code deploy. |
| Cấu hình dành riêng cho môi trường | External Config Data, environment, secret manager | Cùng artifact dùng cho nhiều môi trường. |
| Secret runtime | Secret store hoặc cơ chế cấp phát secret an toàn | Không đóng gói credential trong source/JAR. |
| File log trên VM | Thư mục logging được cấu hình, có rotation | Có quy tắc permission và retention. |
| Log trong container | Thường stdout/stderr → log collector | Tránh phụ thuộc filesystem tạm của container. |
| File tạm khi xử lý | Thư mục tạm có quota/cleanup | Có vòng đời ngắn, được dọn khi xong. |

Đừng dùng đường dẫn classpath cho nội dung phải cập nhật runtime: resource trong JAR thông thường không phải một file thích hợp để sửa trực tiếp.

### 5.1. Một executable JAR không phải thư mục cấu hình mặc định

Ví dụ:

~~~text
/opt/my-app/app.jar
/opt/my-app/application-prod.yml
~~~

Nếu chạy từ:

~~~bash
cd /tmp
java -jar /opt/my-app/app.jar --spring.profiles.active=prod
~~~

Spring Boot **không mặc nhiên** tìm application-prod.yml bên cạnh JAR chỉ vì hai file nằm cùng thư mục. Việc tìm cấu hình ngoài phụ thuộc các Config Data search locations và các location được chỉ định.

Bạn có thể:

- Chạy với CWD phù hợp và dùng default external locations.
- Chỉ định **spring.config.additional-location**.
- Chỉ định **spring.config.location** khi muốn kiểm soát trọn danh sách vị trí.
- Dùng **spring.config.import** từ một tài liệu cấu hình hợp lệ.

Các lựa chọn này có ý nghĩa khác nhau; không nên đổi qua lại tùy tiện.

## 6. Spring Boot Config Data: cấu hình được tìm ở đâu?

Trong Spring Boot hiện đại, hệ thống **Config Data** đảm nhiệm việc nạp application.properties, application.yml và các nguồn cấu hình tương ứng ở giai đoạn startup.

Với cấu hình mặc định thông thường, các vị trí tìm kiếm bao gồm:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

Trong đó:

- **classpath:/** là root của classpath, có thể chứa application.yml đóng gói cùng JAR.
- **classpath:/config/** là thư mục config trên classpath.
- **file:./** tham chiếu working directory của process.
- **file:./config/** là thư mục config con của working directory.
- **file:./config/*/** là các thư mục con trực tiếp của config trên filesystem theo cơ chế wildcard location được Boot hỗ trợ.

### 6.1. Dấu chấm trong file:./ là CWD, không phải thư mục JAR

Ví dụ:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar
~~~

Khi đó đường dẫn mặc định **file:./config/** tương ứng:

~~~text
/srv/order-api/config/
~~~

chứ không phải:

~~~text
/opt/releases/config/
~~~

Nếu bạn chạy cùng JAR từ một CWD khác, tập external configuration được phát hiện có thể thay đổi.

### 6.2. Config file được nhận dạng theo tên

Mặc định, Spring Boot tìm các file cơ sở với basename thường là **application** và các biến thể dành riêng cho profile, ví dụ:

~~~text
application.properties
application.yml
application.yaml
application-prod.yml
application-staging.properties
~~~

Đặt tên một file tùy ý như **custom-settings.yml** dưới ./config không bảo đảm nó tự được nạp theo default search. Khi đó cần chọn cơ chế import/location/name thích hợp.

### 6.3. Cấu hình ngoài có thể ghi đè cấu hình đóng gói

Ví dụ:

~~~yaml
# application.yml được đóng gói trong JAR
app:
  greeting: Hello from packaged config
~~~

Và tại CWD có:

~~~yaml
# ./config/application.yml
app:
  greeting: Hello from external config
~~~

Với Config Data locations mặc định và không có property source ưu tiên cao hơn, giá trị ở external config thường thắng giá trị tương ứng từ packaged config.

Nhờ vậy, một artifact có thể tái sử dụng ở nhiều môi trường. Tuy nhiên, **external config không nhất thiết thắng command-line arguments, system properties hoặc environment variables**. Để biết giá trị cuối, phải đọc Environment đã được xây dựng.

### 6.4. Đừng chỉ kiểm tra file nào tồn tại

Một file ở vị trí tìm kiếm hợp lệ có thể được nạp nhưng những key của nó bị nguồn ưu tiên cao hơn ghi đè. Ngược lại, một file không tồn tại không có nghĩa profile tương ứng không active.

Phân biệt:

1. File có tồn tại không?
2. File có được Config Data loader tìm và nạp không?
3. Document/profile condition trong file có phù hợp không?
4. Giá trị property cuối cùng trong Environment là gì?
5. Bean @ConfigurationProperties hoặc @Value có dùng đúng giá trị đó không?

## 7. spring.config.location: chọn lại các vị trí tìm cấu hình

**spring.config.location** cho phép chỉ định những vị trí Config Data mà Spring Boot sẽ tìm khi khởi động. Trong mô hình thông thường, tùy chọn này **thay thế các search locations mặc định** thay vì đơn giản bổ sung thêm một thư mục.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.location=optional:file:/etc/order-api/
~~~

Lệnh trên chỉ định thư mục /etc/order-api/ làm nơi tìm cấu hình. Nếu Spring Boot được yêu cầu tìm location từ đây, đừng tự giả định file application.yml đóng gói bên trong JAR vẫn được nạp theo những vị trí mặc định đã bị thay thế.

### 7.1. Chỉ định thư mục với dấu slash cuối

Một directory location cần cú pháp kết thúc thích hợp:

~~~text
file:/etc/order-api/
~~~

Spring Boot có thể ghép basename cấu hình vào directory location, ví dụ application.yml hoặc application-prod.yml khi profile prod active.

So sánh:

~~~text
file:/etc/order-api/
file:/etc/order-api/custom.yml
~~~

Đầu tiên là một **directory location**; thứ hai chỉ định **file cụ thể**. Cách Spring Boot tìm profile-specific variants và xử lý basename có thể khác giữa hai dạng. Khi cần cấu hình tự động theo profile, dùng directory location đúng quy tắc giúp tránh nhầm lẫn.

### 7.2. Chỉ định chính xác file cấu hình

~~~bash
java -jar app.jar --spring.config.location=file:/etc/order-api/custom.yml
~~~

Một explicit file location không cần file được đặt tên application.yml. Trong trường hợp này, việc nạp các profile-specific variants còn phụ thuộc quy tắc Config Data đối với file location và các profile active.

Hãy kiểm tra loại location đang dùng, không chỉ nhìn tên file ở thư mục.

### 7.3. Khi nào nên dùng spring.config.location?

Phù hợp khi:

- Muốn kiểm soát toàn bộ tập search locations.
- Artifact chỉ được dùng với một nguồn cấu hình quản lý ngoài JAR.
- Môi trường vận hành yêu cầu tách dứt khoát packaged defaults khỏi external deployment config.

Hãy cẩn thận: nếu application.yml trong JAR chứa defaults thiết yếu và bạn chỉ định location thay thế, những defaults đó có thể không còn được nạp. Điều này gây lỗi startup hoặc khiến ứng dụng dùng giá trị mặc định khác dự kiến.

Nếu ý định là **giữ cấu hình đóng gói và thêm cấu hình ngoài**, lựa chọn ở phần tiếp theo thường sát nhu cầu hơn.

## 8. spring.config.additional-location: bổ sung thư mục ngoài

**spring.config.additional-location** bổ sung location vào tập tìm kiếm mặc định, thay vì loại bỏ toàn bộ default locations.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/order-api/
~~~

Trên một dòng:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/order-api/
~~~

Spring Boot có thể nạp application.yml từ trong JAR, rồi các file cấu hình ngoài tương ứng ở /etc/order-api/ theo thứ tự ưu tiên Config Data.

Ví dụ:

~~~yaml
# application.yml trong JAR
app:
  retry:
    max-attempts: 3
  payment:
    endpoint: https://placeholder.example.invalid
~~~

~~~yaml
# /etc/order-api/application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Khi prod active và additional-location được cấu hình phù hợp, ứng dụng có thể nhận:

~~~text
app.retry.max-attempts = 3
app.payment.endpoint = https://payments.production.internal
~~~

Tức là cấu hình ngoài thay key payment.endpoint, còn retry.max-attempts vẫn dùng default trong JAR.

### 8.1. So sánh location và additional-location

| Khía cạnh | spring.config.location | spring.config.additional-location |
|---|---|---|
| Ý nghĩa chính | Chọn tập vị trí Config Data mới | Bổ sung location vào tìm kiếm mặc định |
| Các vị trí default | Thông thường bị thay thế | Được giữ lại |
| Phù hợp | Điều khiển chặt nguồn cấu hình | Override một số key theo deployment |
| Rủi ro khi dùng nhầm | Không tải packaged defaults | Ghi đè key ngoài ý muốn nếu nhiều nguồn cùng định nghĩa |

### 8.2. Dùng optional: cho location có thể vắng mặt

Ví dụ:

~~~text
optional:file:/etc/order-api/
~~~

Tiền tố **optional:** cho phép bỏ qua một location không tồn tại theo cơ chế Config Data.

Nếu bạn không đánh dấu optional cho một location bắt buộc nhưng nó không tồn tại, Spring Boot có thể fail startup với lỗi liên quan đến **ConfigDataLocationNotFoundException**.

Đừng dùng optional: cho mọi thứ chỉ để tránh startup fail. Nếu cấu hình production bắt buộc phải có để tránh kết nối nhầm hệ thống, **fail-fast** thường an toàn hơn khởi động với defaults không phù hợp.

### 8.3. Cấu hình thêm nhiều locations

Có thể khai báo nhiều địa điểm để tìm cấu hình:

~~~text
optional:file:/etc/order-api/,optional:file:/etc/shared-config/
~~~

Trong những cấu hình phức tạp, Spring Boot còn hỗ trợ **location groups** và quy tắc ưu tiên cho các nhóm location. Dấu phẩy và dấu chấm phẩy có thể mang ý nghĩa nhóm khác nhau.

Hãy thiết kế thứ tự location có chủ đích, nhất là khi nhiều nơi cùng có application-prod.yml. Không nên dựa vào thứ tự tình cờ của file trên ổ đĩa.

## 9. Thời điểm đọc spring.config.location là rất sớm

Các property quyết định việc **tìm Config Data** cần sẵn có từ rất sớm trong quá trình khởi động.

Ví dụ không phù hợp:

~~~yaml
# application.yml dự định nằm trong một vị trí chưa được biết tới
spring:
  config:
    additional-location: file:/other-location/
~~~

Để quyết định đọc application.yml ở đâu, Spring Boot phải biết search locations **trước khi** tìm xong những file đó. Vì vậy những key như **spring.config.name**, **spring.config.location**, **spring.config.additional-location** thường được đặt qua environment variable, system property hoặc command-line argument trong giai đoạn startup.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/order-api/
~~~

hoặc biến môi trường:

~~~text
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/
~~~

### 9.1. Không trông đợi @PropertySource được xử lý đủ sớm

~~~java
@Configuration
@PropertySource("classpath:locations.properties")
class LocationConfiguration {
}
~~~

@PropertySource trên một @Configuration class được xử lý trong giai đoạn xây dựng context, sau khi Spring Boot đã cần biết phần lớn Config Data locations. Vì vậy nó không phải cơ chế đáng tin cậy để chỉ ra vị trí application.yml ban đầu.

### 9.2. Không nhầm vị trí cấu hình với giá trị cấu hình

**spring.config.additional-location** trả lời: “Spring Boot cần tìm file cấu hình ở đâu?”

**app.payment.endpoint** trả lời: “Ứng dụng sẽ gọi endpoint nào?”

Hai property khác vai trò và thường phải được cung cấp vào những thời điểm khác nhau. Không nên giả định mọi key đều có thể lấy từ bất cứ nguồn nào ở bất cứ mốc startup nào.

## 10. spring.config.name: đổi basename tìm file

Mặc định, Spring Boot tìm file có basename **application**.

Nếu deployment sử dụng:

~~~text
/etc/order-api/order-config.yml
~~~

có thể chọn basename bằng:

~~~bash
java -jar app.jar --spring.config.name=order-config --spring.config.additional-location=file:/etc/order-api/
~~~

Khi đổi spring.config.name, hãy nhớ nó ảnh hưởng tên những file mà cơ chế tìm kiếm theo basename sẽ tìm ở các locations. Tùy ý định, bạn có thể không còn nạp các file tên application.yml theo đường tìm kiếm mặc định.

Nếu chỉ muốn nạp **một file có tên khác** bên cạnh cấu hình mặc định, **spring.config.import** có thể rõ nghĩa hơn:

~~~yaml
spring:
  config:
    import: optional:file:/etc/order-api/order-config.yml
~~~

### 10.1. File extension và parser

Config Data hỗ trợ những định dạng phổ biến như .properties, .yml và .yaml. Nếu nguồn file không có extension nhưng chứa nội dung YAML, trong một số trường hợp có thể cần extension hint theo cơ chế Config Data được hỗ trợ.

Không nên đặt một file JSON bất kỳ cạnh application.yml rồi giả định Boot sẽ tự nạp nó giống YAML. Tài nguyên phải được hỗ trợ bởi Config Data loader, có cấu hình import/format phù hợp hoặc cần một loader mở rộng.

## 11. spring.config.import: nhập một nguồn cụ thể

**spring.config.import** được khai báo trong một tài liệu Config Data để nhập thêm các nguồn cấu hình.

Ví dụ application.yml được đóng gói:

~~~yaml
spring:
  application:
    name: order-api
  config:
    import: optional:file:/etc/order-api/extra.yml

app:
  feature:
    audit-enabled: false
~~~

Nếu /etc/order-api/extra.yml tồn tại, Boot có thể nạp nó trong quá trình Config Data processing.

Ví dụ nội dung import:

~~~yaml
app:
  feature:
    audit-enabled: true
~~~

Với quy tắc Config Data imports thông thường, giá trị từ tài liệu import có thể có ưu tiên cao hơn tài liệu khai báo import đối với cùng key. Tuy nhiên, vẫn cần xét các property sources khác có ưu tiên cao hơn và toàn bộ location groups.

### 11.1. Import không phải một “copy/paste YAML” đơn giản

Import có ngữ nghĩa Config Data riêng:

- Có thể import file hoặc directory/data tree bằng loader hỗ trợ.
- Có thể dùng optional: cho nguồn không bắt buộc.
- Được xử lý trong giai đoạn startup, không phải một lần đọc file sau khi ApplicationContext ready.
- Có quy tắc tránh import cùng một location không cần thiết nhiều lần.
- Có thể phối hợp với profile-specific variants và tài liệu on-profile.

Vì vậy, vị trí import, profile đang active và thứ tự các Config Data documents đều có thể ảnh hưởng giá trị cuối.

### 11.2. Relative import và fixed import

Config Data location không chỉ có một kiểu relative path:

~~~yaml
spring:
  config:
    import: optional:extras.yml
~~~

Một import không có prefix location cố định có thể được xử lý **tương đối với location của document khai báo import**, theo quy tắc relative imports của Spring Boot.

Trong khi đó:

~~~yaml
spring:
  config:
    import: optional:file:./extras.yml
~~~

prefix **file:** làm rõ một fixed filesystem location; **./** được giải thích theo working directory đối với file location dạng tương ứng.

Đừng mặc định mọi relative import đều lấy CWD làm gốc. Cần phân biệt cách Boot resolve **relative Config Data location** so với **filesystem path** mà Java Path sử dụng.

### 11.3. Import các nguồn ngoài cần có chính sách vận hành

Nếu /etc/order-api/extra.yml là bắt buộc cho production, việc đánh dấu optional có thể cho phép process chạy dù file chưa được mount. Đây có thể là trạng thái nguy hiểm nếu packaged defaults trỏ tới staging hoặc local.

Hãy quyết định rõ:

- Thiếu file có khiến startup thất bại không?
- Ai tạo/mount file?
- Có cần profile-specific variant không?
- Có cần kiểm tra dữ liệu bắt buộc bằng @ConfigurationProperties validation không?
- File có chứa secret và cần permission đặc biệt không?

## 12. Cấu hình theo profile với file ngoài

Giả sử:

~~~text
/etc/order-api/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

application.yml:

~~~yaml
app:
  payment:
    timeout: 3s
    endpoint: https://placeholder.example.invalid
~~~

application-prod.yml:

~~~yaml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod --spring.config.additional-location=file:/etc/order-api/
~~~

Trong thiết lập thông thường, **application.yml** cung cấp timeout, còn file dành cho prod cung cấp endpoint production.

### 12.1. Profile active không chứng minh file được nạp

Khi:

~~~text
spring.profiles.active=prod
~~~

Boot vẫn có thể active prod dù không tồn tại application-prod.yml tại location đang tìm. Lúc đó ứng dụng có thể dùng giá trị từ application.yml, external imports, environment variable hoặc default của code.

Để khẳng định cấu hình production được áp dụng, hãy kiểm tra:

1. Environment.getActiveProfiles() có prod không?
2. File location đúng chưa?
3. Config Data document đã được nạp chưa?
4. Giá trị app.payment.endpoint sau binding là gì?
5. Bean/service có thực sự sử dụng giá trị đó không?

### 12.2. Nhiều active profiles có thể ghi đè nhau

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

Cả dev và prod đều có thể được kích hoạt. Nếu hai file cùng khai báo app.payment.endpoint, thứ tự profile cùng Config Data precedence ảnh hưởng giá trị cuối.

**Spring profile không tự loại trừ môi trường.** Đừng để dev và prod cùng active chỉ vì bạn nghĩ profile prod luôn tự thắng mọi thiết lập.

### 12.3. On-profile trong một YAML document

~~~yaml
app:
  payment:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Đây là một cách đặt profile-specific document trong cùng file.

**spring.config.activate.on-profile** là điều kiện áp dụng document, không phải lệnh kích hoạt prod.

Không đặt **spring.profiles.active** vào một document chỉ được áp dụng khi on-profile match; Boot giới hạn profile activation properties trong các profile-specific documents.

## 13. Config tree cho secret và dữ liệu mount theo file

Trong Kubernetes hoặc một số secret stores, cấu hình có thể được mount thành các file riêng:

~~~text
/run/secrets/order-api/
├── app.payment.api-key
├── app.payment.merchant-id
└── app.storage.password
~~~

Tên file là tên property, còn nội dung file là value. Spring Boot hỗ trợ **configtree:** import để đọc một thư mục theo mô hình này.

Ví dụ:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/order-api/
~~~

Khi đường dẫn và file được cung cấp đúng theo cơ chế config tree của Boot, application có thể truy cập property tương ứng bằng Environment hoặc binding.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String merchantId,
        String apiKey) {
}
~~~

Cần đăng ký PaymentProperties bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

### 13.1. Config tree không tự bảo vệ secret

Việc dùng configtree không làm secret tự được mã hóa hay đảm bảo quyền truy cập.

Vẫn cần:

- Permission filesystem chỉ cho phép process được quyền đọc.
- Không đưa secret vào source/JAR.
- Không log toàn bộ Environment hoặc properties bean.
- Chính sách cấp phát, xoay vòng và thu hồi secret.
- Xác định cần restart/reload thế nào khi secret mount thay đổi.

Nếu secret là bắt buộc, optional: có thể không phù hợp. Hãy cân nhắc fail-fast với validation và kiểm tra nguồn cấp secret của deployment.

### 13.2. Config tree không phải theo dõi file tự động

Khi một file secret được cập nhật trong volume, Spring Boot không mặc định tự chạy lại toàn bộ Config Data loading, bind lại tất cả bean và đổi connection đã tạo.

Ứng dụng thường cần restart/redeploy hoặc một cơ chế refresh/rotation chuyên biệt có quản lý. Đừng kết luận “mount được cập nhật” đồng nghĩa client đang sử dụng credential mới.

## 14. Độ ưu tiên: không có một “file quan trọng nhất” cho mọi trường hợp

Khi cùng một key xuất hiện ở nhiều nơi, Spring Environment chọn một giá trị hiệu lực theo thứ tự ưu tiên property sources.

Ví dụ:

~~~yaml
# application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Nhưng lệnh khởi động có:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.payment.endpoint=http://localhost:8099
~~~

Với cấu hình mặc định, command-line property **app.payment.endpoint** có mức ưu tiên cao và có thể ghi đè giá trị từ application-prod.yml.

Kết quả: **profile prod active nhưng effective endpoint vẫn là localhost**.

### 14.1. Các nguồn cấu hình hay gặp

| Nguồn | Ví dụ | Điểm lưu ý |
|---|---|---|
| Packaged Config Data | application.yml trong JAR | Phục vụ defaults đi cùng phiên bản code. |
| External Config Data | ./config/application-prod.yml | Có thể ghi đè packaged config theo quy tắc Boot. |
| Imported Config Data | spring.config.import | Có thứ tự precedence riêng của import. |
| Environment variable | APP_PAYMENT_ENDPOINT | Có thể ghi đè file Config Data. |
| JVM system property | -Dapp.payment.endpoint=... | Do JVM cung cấp, độc lập CWD file config. |
| Command-line argument | --app.payment.endpoint=... | Thường có ưu tiên rất cao trong ứng dụng Boot mặc định. |
| @SpringBootTest/test property source | properties trong test | Có thể thay thế kết quả khi chạy test. |

Không nên sử dụng bảng này như thứ tự precedence đầy đủ cho mọi nguồn vì Boot còn hỗ trợ property sources bổ sung và cơ chế riêng của test/devtools.

Khi cần biết **chính xác** key nào thắng, đọc giá trị cuối cùng qua Environment/@ConfigurationProperties và kiểm tra origin/property sources.

### 14.2. Một key không có giá trị khác với file không được tìm

Nếu app.payment.endpoint trả null, nguyên nhân có thể là:

- File chưa được nạp vì location sai.
- File đã nạp nhưng key không có.
- Profile document không phù hợp.
- Prefix/key viết sai.
- Import/secret chưa được mount.

Nếu value không null nhưng sai, có thể là một nguồn ưu tiên cao hơn đã ghi đè. Hai loại sự cố đòi hỏi hướng điều tra khác nhau.

## 15. Đặt đường dẫn filesystem trong @ConfigurationProperties

Một thiết kế dễ vận hành là đưa đường dẫn dữ liệu runtime thành property riêng thay vì hard-code CWD hoặc vị trí JAR.

application.yml:

~~~yaml
app:
  storage:
    upload-directory: /var/lib/order-api/uploads
~~~

Properties record:

~~~java
package com.example.orders.config;

import java.nio.file.Path;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @NotNull Path uploadDirectory) {
}
~~~

Spring Boot Binder có thể chuyển một property String về Path theo cơ chế conversion phù hợp. Để validation hoạt động cần có Bean Validation provider trên classpath, thường qua spring-boot-starter-validation.

Đăng ký configuration properties:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

Khi đặt StorageProperties dưới package com.example.orders, @ConfigurationPropertiesScan mặc định có thể tìm và đăng ký type đó.

### 15.1. Một Path lấy từ cấu hình vẫn có thể là tương đối

Nếu YAML là:

~~~yaml
app:
  storage:
    upload-directory: data/uploads
~~~

thì uploadDirectory có thể là một Path tương đối. Khi mở/ghi file từ đó, nó vẫn phụ thuộc CWD.

Không nên suy luận rằng @ConfigurationProperties tự biến mọi đường dẫn thành absolute path hoặc tự xác định một thư mục data bền vững.

### 15.2. Chuẩn hóa base directory tại một vị trí

~~~java
import java.nio.file.Path;
import org.springframework.stereotype.Component;

@Component
public class StorageLocation {

    private final Path root;

    public StorageLocation(StorageProperties properties) {
        this.root = properties.uploadDirectory()
                .toAbsolutePath()
                .normalize();
    }

    public Path root() {
        return root;
    }
}
~~~

Trong ví dụ, những lần dùng StorageLocation.root() đều có một base path đã resolve. Nhưng nếu property ban đầu tương đối, toAbsolutePath vẫn dựa trên CWD. Chính sách tốt hơn cho production là **yêu cầu path tuyệt đối**, nếu deployment đã có một thư mục dữ liệu chuẩn.

### 15.3. Fail-fast khi production yêu cầu absolute path

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StorageInitializationRunner
        implements ApplicationRunner {

    private final StorageProperties properties;

    public StorageInitializationRunner(
            StorageProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args)
            throws Exception {

        Path root = properties.uploadDirectory();

        if (!root.isAbsolute()) {
            throw new IllegalStateException(
                    "app.storage.upload-directory must be absolute");
        }

        Files.createDirectories(root);

        if (!Files.isDirectory(root)
                || !Files.isWritable(root)) {
            throw new IllegalStateException(
                    "Upload directory is not usable");
        }
    }
}
~~~

Runner được gọi trước khi Spring Boot phát ApplicationReadyEvent trong startup thông thường. Nếu thư mục bắt buộc không tạo/ghi được, exception có thể làm startup thất bại thay vì ứng dụng báo ready rồi lỗi ở request đầu tiên.

**Files.isWritable() chỉ kiểm tra quyền tại một thời điểm**; nó không bảo đảm mọi thao tác ghi về sau thành công. Vẫn cần xử lý IOException khi tạo file, ghi file và đổi tên file.

### 15.4. Không hard-code đường dẫn developer

Không nên để ứng dụng chung phụ thuộc đường dẫn trên Desktop của máy lập trình.

Nếu ứng dụng chạy trên Linux container, một đường dẫn Windows sẽ không mang ý nghĩa như dự kiến. Trong YAML, cú pháp quoting/backslash cũng có các quy tắc cần chú ý.

Hãy cung cấp đường dẫn theo chính môi trường deploy. Cùng một codebase có thể dùng các giá trị khác nhau:

~~~text
local: /home/dev/order-api/uploads
staging: /mnt/order-staging/uploads
prod: /var/lib/order-api/uploads
~~~

Các đường dẫn trên chỉ minh họa naming; đường dẫn thực tế do hạ tầng cung cấp.

## 16. Tạo file trong data directory mà không phụ thuộc filename từ client

Nếu người dùng upload một file tên **orders.csv**, không nên nối trực tiếp originalFilename vào đường dẫn filesystem.

Một mẫu tốt hơn là tạo tên file do server kiểm soát:

~~~java
package com.example.orders.storage;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class UploadStorageService {

    private final Path uploadRoot;

    public UploadStorageService(StorageLocation location) {
        this.uploadRoot = location.root();
    }

    public Path store(InputStream source)
            throws IOException {

        String storageName = UUID.randomUUID() + ".bin";
        Path destination = uploadRoot.resolve(storageName);

        try (InputStream in = source) {
            Files.copy(in, destination);
        }

        return destination;
    }
}
~~~

Phương thức trên **nhận quyền sở hữu** InputStream vì nó đóng stream được truyền vào. Nếu API của caller chỉ cho phép mượn stream, không được đóng thay; nên đổi hợp đồng method hoặc để caller quản lý close.

Ví dụ giả định uploadRoot đã được xác nhận hợp lệ và thư mục đã tồn tại. Ở hệ thống thật, cần thêm:

- Chính sách dung lượng tối đa và loại file.
- Đường dẫn/permissions được cấp chặt chẽ.
- Ngăn ghi đè file có sẵn; có thể dùng OpenOption như CREATE_NEW khi cần.
- Cleanup khi copy thất bại giữa chừng.
- Metadata hoặc database record liên kết storage ID với file người dùng.
- Chống path traversal nếu API cho phép tên đường dẫn do client cung cấp.

Đặc biệt, kiểm tra bằng normalize() và startsWith() chỉ là một lớp bảo vệ lexical; nếu có symlink hoặc race condition, cần cơ chế xác minh filesystem/secure directory operations phù hợp.

### 16.1. Quy ước ownership của InputStream

API nhận InputStream cần ghi rõ ai chịu trách nhiệm đóng. Nếu code gọi MultipartFile.getInputStream() từ request, controller thường mở stream và nên đóng sau khi service đọc xong. Nếu service được thiết kế để take ownership, method có thể dùng try-with-resources như ví dụ.

Đừng trả một InputStream đã bị đóng từ method, và đừng chuyển MultipartFile request-scoped sang công việc nền nếu backing temporary storage có thể đã bị dọn sau request.

## 17. @Value Resource: cấu hình nguồn bằng prefix rõ ràng

Ngoài cấu hình Path, Spring có thể inject Resource từ một property location.

Ví dụ application.yml:

~~~yaml
app:
  template:
    location: classpath:templates/invoice.txt
~~~

Service:

~~~java
package com.example.orders.template;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class InvoiceTemplateService {

    private final Resource template;

    public InvoiceTemplateService(
            @Value("${app.template.location}")
            Resource template) {
        this.template = template;
    }

    public String load() throws IOException {
        try (InputStream in = template.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

Nhờ prefix **classpath:** hoặc **file:** trong property, service có thể dùng cùng một contract ở nhiều môi trường.

Ví dụ cấu hình ngoài:

~~~yaml
app:
  template:
    location: file:/etc/order-api/templates/invoice.txt
~~~

Khi đó source template không nằm trong JAR; người vận hành cần mount đúng file và cấp quyền đọc.

### 17.1. Resource và Path khác nhau

**Resource** mô tả một tài nguyên có thể đến từ classpath, filesystem hoặc loại nguồn khác. Nó phù hợp khi chỉ cần mở stream để đọc.

**Path** thể hiện một đường dẫn filesystem theo quy tắc của provider. Nó phù hợp khi cần tạo thư mục, move, delete, kiểm tra permissions hoặc quản lý file do ứng dụng ghi.

Nếu chỉ đọc một template đóng gói, dùng Resource.getInputStream() thường hợp lý hơn yêu cầu File/Path. Nếu cần quản lý file upload trên volume, Path/Files thường dễ dùng hơn.

## 18. File log và thư mục tạm cũng phụ thuộc working directory

Không chỉ file dữ liệu nghiệp vụ mới bị ảnh hưởng bởi CWD.

Ví dụ:

~~~yaml
logging:
  file:
    name: logs/order-api.log
~~~

Với cách bật file logging tương ứng, đường dẫn **logs/order-api.log** là đường dẫn tương đối và có thể được resolve từ working directory của process.

Cùng một executable JAR:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar
~~~

có thể ghi file log ở /srv/order-api/logs, nhưng nếu service manager dùng CWD khác, file cũng có thể nằm nơi khác.

### 18.1. Logging trong container

Trong môi trường container, stdout/stderr thường là đích phù hợp vì nền tảng đã có cơ chế thu thập log theo process/pod.

Nếu muốn ghi file log:

- Chỉ định thư mục riêng.
- Cấp quyền ghi.
- Đảm bảo volume tồn tại và có retention/rotation.
- Tránh ghi quá nhiều vào container writable layer.

Đừng coi logging.file.name tương đối là nơi lưu log bền vững mặc định.

### 18.2. File tạm và java.io.tmpdir

Một số thư viện sử dụng **java.io.tmpdir** cho temporary files hoặc thao tác upload tạm. Thư mục này khác với working directory và khác với thư mục lưu dữ liệu dài hạn.

Ví dụ:

~~~java
String tempDirectory =
        System.getProperty("java.io.tmpdir");
~~~

Nhiều API File.createTempFile hoặc Files.createTempFile có cơ chế mặc định dùng vùng lưu tạm phù hợp, nhưng đừng giả định các temporary files sẽ nằm cạnh JAR.

Nếu upload lớn hoặc xử lý file tạm thường xuyên, cần đảm bảo dung lượng, permissions và cleanup ở thư mục tạm.

### 18.3. Multipart temp location và data location không giống nhau

Spring Boot có các property liên quan đến multipart upload, chẳng hạn **spring.servlet.multipart.location**, được dùng để cấu hình nơi lưu dữ liệu trung gian theo stack hỗ trợ.

Đây **không tự động là thư mục lưu file cuối cùng** của ứng dụng. Sau khi request kết thúc, temporary resources có thể được dọn.

Nếu cần giữ file sau request, ứng dụng phải chủ động ghi/chuyển dữ liệu tới một storage location có vòng đời do nó quản lý.

## 19. Chạy từ terminal: cùng JAR nhưng khác CWD

Giả sử artifact ở:

~~~text
/opt/releases/order-api.jar
~~~

và có cấu hình:

~~~text
/srv/order-api/config/application-prod.yml
~~~

Chạy:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar --spring.profiles.active=prod
~~~

Theo default external config search, Boot có thể tìm file ở **./config/**, tức /srv/order-api/config.

Nếu đổi CWD:

~~~bash
cd /tmp
java -jar /opt/releases/order-api.jar --spring.profiles.active=prod
~~~

thì **./config/** trở thành /tmp/config, không phải /srv/order-api/config.

### 19.1. Cách chạy không phụ thuộc CWD

Nếu muốn config luôn ở /srv/order-api/config, chỉ định location tường minh:

~~~bash
java -jar /opt/releases/order-api.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/srv/order-api/config/
~~~

Giờ việc tìm Config Data tại location bổ sung ít phụ thuộc CWD hơn. Nhưng các **property values khác vẫn có thể chứa đường dẫn tương đối**, ví dụ app.storage.upload-directory=data/uploads, và những path đó vẫn phụ thuộc CWD.

Vì thế cần xử lý **hai nhóm đường dẫn**:

1. Đường dẫn chỉ đến nơi chứa configuration files.
2. Những đường dẫn được khai báo **bên trong** configuration files để ứng dụng đọc/ghi dữ liệu runtime.

Thiết lập tuyệt đối cho nhóm 1 không tự làm nhóm 2 trở nên tuyệt đối.

### 19.2. Chạy trên Windows PowerShell

Ví dụ:

~~~powershell
Set-Location 'C:\deploy\order-api'
Get-Location
java -jar 'C:\releases\order-api.jar' --spring.profiles.active=prod
~~~

Với working directory như trên, một relative path **data\input.csv** được hiểu từ C:\deploy\order-api theo cách xử lý path của Windows.

Khi cần chỉ định một Config Data location tuyệt đối trên Windows, hãy dùng cú pháp file location tương thích với Spring Boot/Java URL và kiểm tra cách escape, quoting trong shell. Một cách đơn giản để tránh nhầm là đặt cấu hình trong thư mục config thuộc CWD đã được chọn có chủ đích.

### 19.3. Shell script và symlink

Một script khởi chạy có thể được gọi từ bất kỳ thư mục nào. Nếu script dùng relative path mà không xác định CWD, kết quả phụ thuộc người gọi.

Nếu muốn chạy từ một base directory cố định:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cd /srv/order-api
exec java -jar /opt/releases/order-api.jar \
  --spring.profiles.active=prod
~~~

Đây là ví dụ trên Linux. Script cần quyền phù hợp; các đường dẫn phải thuộc chính môi trường triển khai.

**Chú ý:** vị trí file script, symlink tới JAR, CWD của shell và đường dẫn nhập từ JVM là những khái niệm độc lập. Đừng giả định vì script được đặt cạnh JAR nên đường dẫn relative tự lấy thư mục script làm gốc.

## 20. Chạy qua systemd: WorkingDirectory có vai trò gì?

Linux systemd cho phép service khai báo WorkingDirectory tường minh.

Ví dụ một unit minh họa:

~~~ini
[Unit]
Description=Order API
After=network.target

[Service]
Type=simple
User=order-api
WorkingDirectory=/srv/order-api
Environment=SPRING_PROFILES_ACTIVE=prod
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/
ExecStart=/usr/bin/java -jar /opt/order-api/order-api.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

Trong ví dụ:

- **WorkingDirectory=/srv/order-api** xác định CWD của Java process khi service chạy.
- **ExecStart** chọn executable và JAR.
- **SPRING_PROFILES_ACTIVE** chọn profile.
- **SPRING_CONFIG_ADDITIONAL_LOCATION** thêm thư mục cấu hình ngoài.
- **User** điều khiển tài khoản OS mà process dùng.

Các giá trị này tách biệt. Changing ExecStart để trỏ tới một JAR khác **không tự đổi CWD** khi WorkingDirectory giữ nguyên.

### 20.1. Permission của service account

Nếu service chạy dưới user order-api, nó cần:

- Quyền đọc JAR và cấu hình ở /etc/order-api.
- Quyền ghi nếu ứng dụng dùng /var/lib/order-api hoặc thư mục log riêng.
- Quyền truy cập network theo chính sách bảo mật.

Một process chạy bằng terminal của administrator có thể đọc file được nhưng cùng JAR chạy dưới service account lại bị **AccessDeniedException**. Đừng khắc phục bằng cách chuyển toàn service sang root nếu có thể cấp quyền chính xác cho tài nguyên cần thiết.

### 20.2. EnvironmentFile không phải là Java properties file

systemd có cơ chế **EnvironmentFile=** để đọc các biến môi trường của service. Đây là cú pháp của systemd, không đồng nghĩa Spring Boot tự hiểu một file bất kỳ đặt cạnh JAR là application.properties.

Nếu một EnvironmentFile khai báo SPRING_PROFILES_ACTIVE hoặc SPRING_CONFIG_ADDITIONAL_LOCATION, systemd truyền chúng cho process; Spring Boot nhận chúng như environment variables.

Với secret nhạy cảm, cần đánh giá cơ chế cấp phát riêng của hạ tầng thay vì đặt credentials không bảo vệ trong service unit hoặc file có quyền đọc rộng.

### 20.3. Cơ chế hardening có thể chặn ghi file

Ngay cả khi Files.isWritable trên một path có vẻ hợp lý, service manager còn có thể áp dụng sandbox hoặc readonly filesystem restrictions.

Nếu hệ thống bật các tùy chọn hardening như ProtectSystem, có thể cần khai báo writable directories bằng cơ chế systemd được quản trị viên phê duyệt. Hãy kiểm tra hiệu quả permissions tại **process đang chạy**, không chỉ chmod của file.

## 21. Docker: WORKDIR không phải vị trí artifact

Một Dockerfile minh họa:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY order-api.jar /app/order-api.jar

USER 10001

ENTRYPOINT ["java", "-jar", "/app/order-api.jar"]
~~~

Trong ví dụ này:

- JAR được đặt ở /app/order-api.jar.
- Docker **WORKDIR /app** đặt working directory mặc định.
- Một property filesystem tương đối như data/input.csv thường được resolve dưới /app/data/input.csv.

Nếu container bị thay thế, dữ liệu ở writable layer có thể không được bảo toàn. Vì vậy **/app không nên mặc định là nơi lưu upload bền vững**.

### 21.1. Mount cấu hình ngoài bằng volume

Ví dụ chạy container:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/ \
  -v /host/order-config:/etc/order-api:ro \
  -v /host/order-data:/var/lib/order-api \
  order-api:latest
~~~

Giả định:

- /host/order-config có application-prod.yml hoặc những file Config Data tương ứng.
- Container có quyền đọc /etc/order-api.
- /host/order-data có ownership/permission cho UID của ứng dụng.
- app.storage.upload-directory được cấu hình tới /var/lib/order-api/uploads hoặc location được cấp phù hợp.

Docker bind mount cú pháp phụ thuộc host và Docker runtime; lệnh trên minh họa trên host Linux.

### 21.2. Chạy container với working directory khác

Docker có thể cho phép thay CWD bằng tùy chọn tương ứng:

~~~bash
docker run --rm -w /work order-api:latest
~~~

Khi đó JAR vẫn được gọi theo đường dẫn tuyệt đối /app/order-api.jar trong ENTRYPOINT, nhưng các filesystem relative paths của Java process có thể chuyển sang /work.

Điều này cho thấy **đường dẫn executable và working directory vẫn là hai cấu hình độc lập**.

### 21.3. Read-only root filesystem

Trong container được harden, root filesystem có thể readonly. Nếu code cố ghi:

~~~text
./logs/application.log
./uploads/order.csv
~~~

mà thư mục đó không được mount writable, thao tác ghi sẽ thất bại. Không nên sửa bằng cách tắt bảo vệ toàn bộ container nếu có thể:

- Ghi log ra stdout/stderr.
- Mount một data volume ở vị trí rõ ràng.
- Cấu hình đường dẫn dữ liệu tuyệt đối.
- Cấp quyền ghi tối thiểu cho user đang chạy.

## 22. Kubernetes: workingDir, ConfigMap, Secret và volume

Trong Kubernetes, file JAR thường đã được đóng gói vào image. Môi trường chạy có thể cung cấp:

- **workingDir** của container.
- Environment variables.
- ConfigMap mount thành files.
- Secret mount thành files hoặc cung cấp qua cơ chế được triển khai.
- PersistentVolumeClaim cho dữ liệu cần lưu.
- emptyDir cho dữ liệu tạm gắn với vòng đời Pod.

Ví dụ Deployment minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.invalid/order-api:1.0.0
          workingDir: /work
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/order-api/
          volumeMounts:
            - name: configuration
              mountPath: /etc/order-api
              readOnly: true
            - name: data
              mountPath: /var/lib/order-api
      volumes:
        - name: configuration
          configMap:
            name: order-api-config
        - name: data
          persistentVolumeClaim:
            claimName: order-api-data
~~~

Giả sử ConfigMap **order-api-config** chứa application-prod.yml và volume data có quyền đọc/ghi phù hợp.

Khi container chạy:

- **workingDir=/work** làm gốc cho filesystem relative paths.
- **/etc/order-api/** là location ngoài được Spring Boot thêm vào Config Data search.
- **/var/lib/order-api/** là vùng dữ liệu có volume riêng.
- Image có thể chứa JAR ở một path khác; không cần trùng /work.

### 22.1. Cẩn thận khi mở rộng nhiều replica

Ví dụ chỉ khai báo một replica và một PVC nhằm minh họa. Nếu scale nhiều pod cùng ghi một volume, khả năng mount đồng thời và tính nhất quán phụ thuộc access mode/storage backend.

Trong nhiều hệ thống, file upload nên được lưu vào object storage hoặc một dịch vụ lưu trữ được thiết kế cho nhiều replica, thay vì giả định mọi pod cùng ghi lên một local directory.

### 22.2. ConfigMap hoặc Secret cập nhật có tự reload Spring không?

Không nên tự giả định. Kubernetes có thể cập nhật nội dung một volume mount theo cơ chế của nó, nhưng Spring Boot không mặc định tạo lại Environment, rebind toàn bộ beans và thay các clients đã được khởi tạo chỉ vì file thay đổi.

Cần chính sách restart/rollout hoặc một cơ chế dynamic config/secret rotation được thiết kế riêng.

### 22.3. Kubernetes workingDir phải thực sự tồn tại/phù hợp

Nếu workingDir chỉ tới một thư mục không tồn tại hoặc container không có quyền truy cập, process có thể không khởi động được.

Khi triển khai, xác minh workingDir, image filesystem, volumeMounts và securityContext/UID ở **pod thật**. Thông tin trong một YAML manifest chưa được rollout không chứng minh runtime hiện tại đã dùng nó.

## 23. Quan sát working directory và cấu hình thực tế khi startup

Khi ứng dụng không tìm thấy file hoặc sử dụng sai endpoint, đừng chỉ xem file cấu hình trong repository. Hãy đọc những dữ liệu của **process đang chạy**.

Một ApplicationRunner có thể ghi:

~~~java
package com.example.orders.diagnostics;

import java.nio.file.Path;
import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupEnvironmentInspector
        implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(
                    StartupEnvironmentInspector.class);

    private final Environment environment;

    public StartupEnvironmentInspector(
            Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Path cwd = Path.of("").toAbsolutePath().normalize();

        log.info("Working directory: {}", cwd);
        log.info("Active profiles: {}",
                Arrays.toString(
                        environment.getActiveProfiles()));

        log.info("Data directory: {}",
                environment.getProperty(
                        "app.storage.upload-directory"));
    }
}
~~~

Trong ví dụ, chỉ ghi một vài giá trị được lựa chọn và không chứa secret.

### 23.1. Không in toàn bộ Environment

Environment có thể chứa:

- Password và credential database.
- Token của API bên ngoài.
- Giá trị được mount từ Secret.
- Thông tin hệ thống nhạy cảm.

Một câu lệnh ghi log tất cả property sources có thể làm lộ dữ liệu. Đối với key nhạy cảm, chỉ xác minh sự hiện diện hoặc trạng thái hợp lệ theo cơ chế được phê duyệt.

### 23.2. Vì sao log trong ApplicationRunner có thể không xuất hiện?

ApplicationRunner chạy sau khi context được refresh. Nếu process thất bại sớm vì:

- ConfigDataLocationNotFoundException.
- YAML syntax không hợp lệ.
- Profile-specific config không được tìm thấy như mong đợi.
- Lỗi bind/validate property.
- Lỗi tạo bean bắt buộc.

thì runner có thể chưa được gọi.

Khi đó phải đọc **startup logs của Spring Boot**, lệnh chạy, environment variables và config locations được truyền vào trước khi khởi tạo context. Không nên coi việc thiếu log của runner là bằng chứng cho một CWD cụ thể.

### 23.3. Ghi relative và resolved path để so sánh

Nếu app.storage.upload-directory được cấu hình tương đối, một diagnostic hữu ích:

~~~java
String value = environment.getProperty(
        "app.storage.upload-directory");

if (value != null) {
    Path configured = Path.of(value);
    Path effective = configured.toAbsolutePath().normalize();

    log.info("Storage path is absolute: {}",
            configured.isAbsolute());
    log.info("Effective storage path: {}", effective);
}
~~~

Đây là cách giải thích rõ tại sao một đường dẫn có giá trị **uploads** nhưng process lại tìm tại /tmp/uploads.

## 24. Tìm nguồn cung cấp property trong Environment

Biết CWD đúng chưa đủ. Nếu có hai file cấu hình hoặc có override từ command line, cần biết **property source nào cung cấp giá trị cuối**.

Spring cung cấp ConfigurableEnvironment:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class ConfigOriginInspector {

    public static void showCandidates(
            ConfigurableEnvironment environment,
            String key) {

        System.out.println("Effective: "
                + environment.getProperty(key));

        for (PropertySource<?> source
                : environment.getPropertySources()) {

            if (source.containsProperty(key)) {
                System.out.println("Candidate source: "
                        + source.getName());
            }
        }
    }
}
~~~

Chỉ dùng helper này với các key không nhạy cảm như:

~~~text
app.storage.upload-directory
app.payment.endpoint
spring.application.name
~~~

Trong một Environment thông thường, property sources có thứ tự ưu tiên. Nhưng việc duyệt containsProperty trên từng source chỉ cho biết **nguồn ứng viên**, không tự mô tả chính xác mọi trường hợp relaxed binding, placeholder resolution và config origin metadata.

### 24.1. Actuator hỗ trợ quan sát cấu hình

Spring Boot Actuator có các endpoint hữu ích:

| Endpoint | Mục đích |
|---|---|
| **/actuator/env** | Quan sát Environment, active profiles và thông tin property sources/origin khi được hỗ trợ. |
| **/actuator/configprops** | Quan sát các @ConfigurationProperties beans đã bind. |
| **/actuator/beans** | Xác nhận các bean thực sự được đăng ký. |
| **/actuator/conditions** | Xem báo cáo điều kiện auto-configuration của Boot. |

Không phải endpoint nào cũng được expose mặc định. Nếu bật env hoặc configprops qua HTTP, phải có **xác thực, phân quyền và redaction** phù hợp; không công khai cấu hình nội bộ.

### 24.2. Truy vết Config Data loading bằng log

Khi không biết file nào đã được tìm/nạp, có thể tăng mức logging của thành phần Config Data trong một lần khởi động chẩn đoán:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

Log chi tiết có thể giúp tìm location được xử lý, file được bỏ qua và các mốc cấu hình. Chỉ sử dụng TRACE có kiểm soát vì có thể tạo rất nhiều output.

### 24.3. Spring profile không thay thế kiểm tra cấu hình

Log kiểu:

~~~text
The following 1 profile is active: "prod"
~~~

chỉ cho biết profile active theo luồng startup. Nó **không chứng minh**:

- /etc/order-api/application-prod.yml đã được mount.
- app.payment.endpoint đã nhận giá trị production.
- Database thực tế là database production.
- Bean sử dụng cấu hình đúng hoặc external resource còn đọc được.

Để xác nhận môi trường, phải kiểm tra active profiles, effective properties và tài nguyên/bean được sử dụng.

## 25. Kiểm thử logic đường dẫn bằng @TempDir

Một cách kiểm thử không phụ thuộc đường dẫn máy lập trình là dùng **JUnit 5 @TempDir**.

Giả sử class xử lý Path:

~~~java
package com.example.orders.storage;

import java.nio.file.Path;

public class RelativePathResolver {

    private final Path baseDirectory;

    public RelativePathResolver(Path baseDirectory) {
        this.baseDirectory =
                baseDirectory.toAbsolutePath().normalize();
    }

    public Path resolve(String relativeName) {
        Path result = baseDirectory
                .resolve(relativeName)
                .normalize();

        if (!result.startsWith(baseDirectory)) {
            throw new IllegalArgumentException(
                    "Path escapes storage directory");
        }

        return result;
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class RelativePathResolverTests {

    @TempDir
    Path tempDir;

    @Test
    void resolvesChildInsideBaseDirectory() {
        RelativePathResolver resolver =
                new RelativePathResolver(tempDir);

        Path resolved = resolver.resolve("reports/orders.csv");

        assertThat(resolved)
                .isEqualTo(tempDir
                        .resolve("reports/orders.csv")
                        .toAbsolutePath()
                        .normalize());
    }

    @Test
    void rejectsEscapingRelativePath() {
        RelativePathResolver resolver =
                new RelativePathResolver(tempDir);

        assertThatThrownBy(
                () -> resolver.resolve("../outside.txt"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Test này xác minh **lexical path resolution**. Nó chưa bảo vệ đầy đủ trước symlinks, race condition hoặc quyền truy cập trong filesystem thực. Nếu path đến từ user input không tin cậy, cần thêm ràng buộc filename, chính sách symlink và secure file operations phù hợp với threat model.

### 25.1. Vì sao không test bằng một đường dẫn hard-code?

Ví dụ:

~~~java
Path.of("/home/developer/project/data/input.csv");
~~~

có thể không tồn tại trên CI agent hoặc Windows. @TempDir tạo vùng thử nghiệm theo runtime, giúp kiểm tra logic Path mà không phụ thuộc layout máy phát triển.

### 25.2. Kiểm thử xử lý file thật

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@Test
void readsUtf8FileFromTempDirectory(
        @TempDir Path tempDir) throws Exception {

    Path file = tempDir.resolve("note.txt");
    Files.writeString(
            file, "Chạy từ thư mục bất kỳ",
            StandardCharsets.UTF_8);

    String text = Files.readString(
            file, StandardCharsets.UTF_8);

    assertThat(text)
            .isEqualTo("Chạy từ thư mục bất kỳ");
}
~~~

Đây là test về đường dẫn filesystem và charset, không phải test về Spring Boot Config Data precedence. Các nhiệm vụ đó nên được kiểm tra ở những phạm vi riêng.

### 25.3. Không đổi user.dir toàn JVM chỉ để test

Ví dụ:

~~~java
System.setProperty("user.dir", "/temporary/place");
~~~

không phải cách cô lập CWD đáng tin cậy cho một test suite đa luồng. Nó còn có thể ảnh hưởng test khác.

Hãy truyền base Path vào component cần kiểm tra hoặc khởi chạy một process con với working directory tường minh nếu phải xác minh chính behavior của CWD.

## 26. Kiểm thử cấu hình ngoài ở mức tích hợp

Với Config Data, kiểm thử một @ConfigurationProperties bean là một phần quan trọng nhưng chưa đủ để biết file ngoài được tìm đúng location.

Có hai hướng:

### 26.1. Test binding khi biết property values

Với class:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path uploadDirectory) {
}
~~~

có thể dùng ApplicationContextRunner để dựng context nhỏ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class StoragePropertiesBindingTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsAbsoluteStoragePath() {
        new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class)
                .withPropertyValues(
                        "app.storage.upload-directory=/var/lib/order-api")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    StorageProperties props =
                            context.getBean(StorageProperties.class);

                    assertThat(props.uploadDirectory())
                            .isEqualTo(Path.of("/var/lib/order-api"));
                });
    }
}
~~~

Ví dụ sử dụng Path kiểu Unix để minh họa một giá trị cấu hình. Trên Windows, cần sử dụng một absolute Path hợp lệ cho hệ điều hành của test.

Test này kiểm tra **binding**, nhưng không tự chứng minh rằng application-prod.yml ở một thư mục ngoài được nạp bởi Config Data loader.

### 26.2. Test startup với external configuration thực tế

Nếu mục tiêu là xác nhận chính cách tìm file ngoài, một bài kiểm thử tích hợp có thể:

1. Tạo một thư mục tạm.
2. Viết application.yml hoặc application-test.yml vào thư mục đó.
3. Khởi động một **SpringApplication process riêng** với spring.config.additional-location trỏ đến thư mục tạm.
4. Đọc Environment hoặc kiểm tra một @ConfigurationProperties bean.
5. Xác nhận giá trị được nạp từ external file.
6. Kết thúc process và dọn dữ liệu tạm.

Tách process hoặc tạo startup harness có kiểm soát hữu ích vì một số lựa chọn Config Data được đọc **rất sớm** và có thể chịu ảnh hưởng của hệ thống property/global state trong JVM.

### 26.3. @SpringBootTest(properties=...) không phải test file location

Ví dụ:

~~~java
@SpringBootTest(properties = {
        "app.payment.endpoint=https://test.example.invalid"
})
~~~

có thể chứng minh code nhận được effective property trong test context. Nhưng giá trị được cung cấp trực tiếp qua test properties, không phải bằng chứng rằng Config Data đã tìm đúng file external của môi trường thật.

Để tránh nhầm, đặt tên test theo điều mà nó thực sự xác minh: **binding test**, **Config Data loading test** hoặc **runtime deployment smoke test**.

## 27. Đóng gói JAR không tự mang theo file ngoài

Khi build một Spring Boot executable JAR bằng Gradle hoặc Maven, các file nằm trong **src/main/resources** thường được đóng gói như classpath resources.

Ví dụ dự án:

~~~text
order-api/
├── src/
│   └── main/
│       └── resources/
│           ├── application.yml
│           └── data/
│               └── countries.csv
├── runtime/
│   └── application-prod.yml
└── build/
    └── libs/
        └── order-api.jar
~~~

File runtime/application-prod.yml trong ví dụ nằm **ngoài src/main/resources**. Không nên mặc định nó được đóng gói vào JAR chỉ vì nó nằm cùng repository.

Sau build:

- application.yml có thể được tìm qua classpath.
- data/countries.csv có thể được đọc bằng ClassPathResource.
- runtime/application-prod.yml cần được deploy/mount riêng hoặc được chủ động đưa vào artifact theo một cấu hình build rõ ràng.

Đây không nhất thiết là nhược điểm. Với cùng một JAR triển khai qua dev/staging/prod, **tách external configuration khỏi artifact** thường là chủ đích đúng.

### 27.1. Build artifact và deployment package là hai khái niệm

Một release có thể chứa:

~~~text
release/
├── order-api.jar
├── config/
│   └── application-prod.yml
└── start.sh
~~~

Đây là một **deployment bundle**, không có nghĩa file config đã nằm trong executable JAR. Nếu start.sh dùng CWD khác, thư mục config trong bundle không tự được tìm theo relative path.

Vì vậy, tài liệu triển khai nên chỉ rõ:

- Working directory khi chạy.
- Đường dẫn artifact.
- External Config Data location.
- Active profiles.
- Data/log/temp directories.
- Quyền filesystem của service account.

### 27.2. Không kiểm tra resource bằng đường dẫn source project

Ví dụ sai:

~~~java
Path path = Path.of(
        "src/main/resources/application.yml");
~~~

Đường dẫn này chỉ hữu dụng cho một số thao tác phát triển/build có CWD trùng root source tree. Khi chạy executable JAR ở server, ứng dụng nên dùng **Spring Environment** để đọc cấu hình đã resolve, không tìm đường dẫn source tree.

Nếu chỉ cần đọc một resource classpath không phải application configuration, dùng ClassPathResource.

### 27.3. application.yml trong JAR không thể được chỉnh ngay bằng việc sửa source

Khi một file đã được đóng gói vào JAR, sửa file nguồn tại máy developer không làm process trên server đang chạy tự đổi giá trị.

Cần build/deploy artifact mới hoặc cung cấp một external configuration có precedence phù hợp, sau đó áp dụng cơ chế restart/refresh thích hợp.

Không cố mở một classpath resource trong JAR như file để ghi trực tiếp từ business code.

## 28. Những lỗi thường gặp khi chạy và đóng gói

### 28.1. Chạy trong IDE được nhưng JAR không tìm thấy file

**Dấu hiệu:** NoSuchFileException với đường dẫn src/main/resources/... hoặc data/....

**Nguyên nhân:** IDE chạy với working directory của repository; JAR chạy ở nơi khác và resource có thể nằm bên trong artifact.

**Cách xử lý:** với dữ liệu đóng gói, dùng classpath Resource.getInputStream(); với file runtime, cấu hình path ngoài tường minh.

### 28.2. Đặt application-prod.yml cạnh JAR nhưng không được nạp

**Dấu hiệu:** prod active nhưng endpoint/config vẫn dùng default.

**Nguyên nhân:** Boot tìm external Config Data theo CWD/search locations, không tự lấy thư mục chứa JAR làm gốc.

**Cách xử lý:** chuyển CWD đúng hoặc dùng spring.config.additional-location/file location tuyệt đối, sau đó kiểm tra effective value.

### 28.3. Dùng spring.config.location khi chỉ muốn thêm override

**Dấu hiệu:** ứng dụng mất các packaged defaults hoặc nhiều property không còn giá trị.

**Nguyên nhân:** spring.config.location thường thay thế default search locations.

**Cách xử lý:** nếu vẫn cần cấu hình bên trong JAR, dùng spring.config.additional-location hoặc chủ động liệt kê location groups phù hợp.

### 28.4. Thiếu dấu slash ở directory location

**Dấu hiệu:** Boot không tìm file như mong đợi hoặc xử lý location khác với ý định.

**Nguyên nhân:** một directory location và explicit file location có cú pháp/semantics khác nhau.

**Cách xử lý:** dùng dạng thư mục như file:/etc/order-api/ khi muốn tìm application.yml và profile-specific files trong directory.

### 28.5. Thiếu optional: làm startup fail

**Dấu hiệu:** lỗi ConfigDataLocationNotFoundException hoặc thông báo cấu hình không tồn tại khi khởi động.

**Nguyên nhân:** Spring Boot được yêu cầu nạp một location bắt buộc nhưng nó không tồn tại.

**Cách xử lý:** xác nhận path và mount; chỉ dùng optional: nếu thiếu location là tình huống được phép. Với production config bắt buộc, fail-fast có thể là hành vi đúng.

### 28.6. Dùng optional: khiến hệ thống chạy bằng cấu hình sai

**Dấu hiệu:** ứng dụng vẫn start dù /etc/order-api/application-prod.yml bị thiếu, sau đó gọi endpoint không mong muốn.

**Nguyên nhân:** external location bị bỏ qua; packaged/default values được sử dụng.

**Cách xử lý:** phân loại cấu hình bắt buộc, bỏ optional: khi cần, thêm @ConfigurationProperties validation và guard xác thực môi trường đích.

### 28.7. Cấu hình đường dẫn tuyệt đối của Windows trên Linux

**Dấu hiệu:** dữ liệu được ghi vào path lạ hoặc báo lỗi InvalidPathException.

**Nguyên nhân:** đường dẫn mang cú pháp OS-specific nhưng artifact chạy trên OS khác.

**Cách xử lý:** để deployment cung cấp path đúng nền tảng; dùng Path API thay vì tự nối chuỗi; tránh hard-code đường dẫn developer.

### 28.8. Dùng normalize() rồi tưởng chống được mọi path traversal

**Dấu hiệu:** file vẫn có thể bị đọc/ghi ngoài vùng dự định khi có symlink hoặc race.

**Nguyên nhân:** normalize chỉ xử lý ký tự đường dẫn, không xác minh filesystem thực tế hay symlink.

**Cách xử lý:** giới hạn file names, dùng base directory tin cậy, kiểm tra canonical/real paths và secure file operations theo threat model; không cho phép raw user-controlled location được mở tùy ý.

### 28.9. File log ở thư mục khác dự kiến

**Dấu hiệu:** logs/application.log xuất hiện ở /tmp hoặc / thay vì /opt/app.

**Nguyên nhân:** logging path tương đối theo CWD của service/container.

**Cách xử lý:** log ra stdout nếu dùng container; nếu ghi file, cấu hình đường dẫn tuyệt đối và quyền ghi.

### 28.10. Service chạy bằng user khác nên không đọc được config

**Dấu hiệu:** AccessDeniedException dù developer có thể mở file thủ công.

**Nguyên nhân:** service account của systemd/container khác user ở terminal.

**Cách xử lý:** xác nhận effective UID/GID và mount permissions; cấp quyền đúng mức, không dùng root làm giải pháp mặc định.

### 28.11. K8s ConfigMap đã sửa nhưng app vẫn dùng giá trị cũ

**Dấu hiệu:** file mount mới có value đúng nhưng bean hoặc HTTP client vẫn dùng value trước.

**Nguyên nhân:** dữ liệu Config Data đã được bind khi context khởi động; thay mount không tự khởi tạo lại bean.

**Cách xử lý:** triển khai rollout/restart hoặc cơ chế dynamic configuration có quản lý.

### 28.12. Nhiều pod dùng các giá trị khác nhau

**Dấu hiệu:** cùng deployment nhưng một phần request gọi staging, một phần production.

**Nguyên nhân:** rollout chưa đồng nhất, image/config mount khác nhau hoặc pod cũ chưa restart.

**Cách xử lý:** kiểm tra image digest, active profiles, Environment và property origins của từng instance đang nhận traffic.

### 28.13. application-dev.yml không được áp dụng vì profile sai

**Dấu hiệu:** file tồn tại trong Config Data location nhưng giá trị vẫn là base config.

**Nguyên nhân:** tên profile active không khớp, ví dụ production thay vì prod, hoặc một tài liệu on-profile không match.

**Cách xử lý:** đọc Environment.getActiveProfiles() và so sánh với tên file/condition. Đừng chỉ nhìn spring.profiles.active ở một file duy nhất.

### 28.14. File cấu hình có giá trị nhưng @ConfigurationProperties vẫn dùng default

**Dấu hiệu:** Environment hoặc Config Data log cho thấy file được nạp, nhưng bean có giá trị null/default.

**Nguyên nhân:** prefix hoặc property name không khớp, type conversion lỗi, bean chưa được đăng ký, hoặc có source khác ghi đè.

**Cách xử lý:** đối chiếu effective Environment và object đã bind, kiểm tra @ConfigurationPropertiesScan/@EnableConfigurationProperties, validation và source precedence.

### 28.15. File được ghi vào container layer rồi mất sau deploy

**Dấu hiệu:** upload tồn tại trước restart nhưng biến mất sau khi pod/container được thay thế.

**Nguyên nhân:** lưu dữ liệu ở writable layer tạm thay vì durable storage.

**Cách xử lý:** dùng volume hoặc object storage phù hợp; không coi vị trí JAR/WORKDIR là storage bền vững.

### 28.16. Sai tên file hoặc sai basename

**Dấu hiệu:** application.yml được nạp nhưng custom-settings.yml đặt cùng thư mục bị bỏ qua.

**Nguyên nhân:** Config Data search mặc định dùng basename application, không scan mọi YAML.

**Cách xử lý:** chỉ định spring.config.name, logging/Config Data import hoặc explicit file location đúng mục đích.

### 28.17. Nhầm external file với classpath resource

**Dấu hiệu:** ClassPathResource("config/application.yml") không đọc được một file đặt ở /etc/order-api/.

**Nguyên nhân:** ClassPathResource tìm trong runtime classpath, không tìm ở arbitrary filesystem directory.

**Cách xử lý:** dùng FileSystemResource/Path cho file ngoài; với application configuration, để Spring Boot Config Data loader nạp theo location.

### 28.18. Tác vụ phụ thuộc CWD vô tình chạy từ thư mục khác

**Dấu hiệu:** cron, systemd hoặc batch job ghi vào thư mục không đúng khi cùng một lệnh chạy tay thì ổn.

**Nguyên nhân:** launcher thay đổi current directory hoặc không có WorkingDirectory tường minh.

**Cách xử lý:** xác định CWD ngay trong service/job hoặc resolve mọi business data path từ base directory đã cấu hình.

## 29. Hai tình huống minh họa để phân biệt nguyên nhân

### 29.1. Trường hợp A: file CSV có trong JAR nhưng không đọc được

Source:

~~~text
src/main/resources/data/tax-codes.csv
~~~

Code:

~~~java
Files.readString(
        Path.of("src/main/resources/data/tax-codes.csv"));
~~~

Trong IDE code có thể chạy vì project root là CWD. Trên server, source tree không tồn tại.

**Nguyên nhân:** code đã dùng một path của source filesystem để đọc classpath resource.

**Sửa theo bản chất:**

~~~java
Resource resource =
        new ClassPathResource("data/tax-codes.csv");

try (InputStream in = resource.getInputStream()) {
    String csv = new String(
            in.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

Đọc đúng resource đã đóng gói; không cần đổi CWD chỉ để làm code đọc từ source tree hoạt động.

### 29.2. Trường hợp B: application-prod.yml bên ngoài không được dùng

Deployment:

~~~text
/opt/order-api/app.jar
/opt/order-api/config/application-prod.yml
~~~

Lệnh:

~~~bash
cd /tmp
java -jar /opt/order-api/app.jar \
  --spring.profiles.active=prod
~~~

Ứng dụng vẫn nhận prod nhưng endpoint không đúng.

**Nguyên nhân có thể:** default ./config/ đang trỏ tới /tmp/config chứ không phải /opt/order-api/config.

**Cách xử lý:**

~~~bash
java -jar /opt/order-api/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/opt/order-api/config/
~~~

Sau đó đọc effective app.payment.endpoint từ Environment và xác minh file đã được nạp. Nếu vẫn sai, kiểm tra environment variables và command-line property overrides.

Hai trường hợp này có biểu hiện giống nhau là “không đọc được file” nhưng bản chất khác nhau:

- Trường hợp A: **nhầm classpath resource với source filesystem path**.
- Trường hợp B: **nhầm CWD/default external Config Data location với thư mục JAR**.

Vì vậy, không nên sửa mọi lỗi file bằng cách thêm nhiều dấu ../ vào path.

## 30. Những hiểu nhầm thường gặp

**“java -jar /opt/app/app.jar làm /opt/app trở thành working directory.”**  
Không. CWD thường được kế thừa từ launcher hoặc do service/container cấu hình. Đường dẫn tuyệt đối tới JAR không tự thay đổi CWD.

**“Path.of('data/input.csv') sẽ tìm file cạnh JAR.”**  
Không. Đây là một filesystem relative path, thường được resolve từ working directory.

**“File dưới src/main/resources luôn tồn tại như file thường trên server.”**  
Không. Khi đóng gói executable JAR, resource thường nằm trong classpath/JAR, không nhất thiết có bản sao trên filesystem.

**“ClassPathResource.getFile() luôn hoạt động.”**  
Không. Resource có thể nằm trong JAR nên không có File filesystem độc lập.

**“Thư mục chứa JAR và CWD luôn phải giống nhau.”**  
Không. Chúng có thể khác; quan trọng là đường dẫn được cấu hình và xử lý có chủ đích.

**“Spring Boot tự đọc mọi file YAML cạnh executable JAR.”**  
Không. Nó dùng default Config Data locations và các location/import đã cấu hình, cùng quy tắc basename và profile.

**“./config/ luôn là thư mục config nằm cạnh JAR.”**  
Không. Dấu chấm trong file:./config/ gắn với CWD của process.

**“spring.config.location và spring.config.additional-location làm cùng một việc.”**  
Không. Một lựa chọn chủ yếu thay thế search locations; lựa chọn kia bổ sung locations vào danh sách mặc định.

**“Có application-prod.yml nghĩa profile prod đang active.”**  
Không. Profile phải được kích hoạt từ Environment/startup theo cơ chế hợp lệ.

**“Prod active nghĩa toàn bộ giá trị đều lấy từ application-prod.yml.”**  
Không. External imports, environment variables, JVM properties và command-line arguments có thể thay đổi giá trị cuối.

**“optional: chỉ là cách viết đẹp hơn cho mọi config.”**  
Không. Nó thay đổi chính sách xử lý location vắng mặt. Với cấu hình bắt buộc, bỏ qua location có thể nguy hiểm.

**“Một file import tương đối luôn tính từ CWD.”**  
Không nhất thiết. Relative Config Data import có quy tắc resolve theo document/location khai báo; cần phân biệt với fixed file location.

**“Dùng @PropertySource là cách thay thế hoàn toàn spring.config.additional-location.”**  
Không. @PropertySource được xử lý muộn hơn trong lifecycle và không thay thế cơ chế Config Data startup.

**“Đặt một @ConfigurationProperties Path khiến nó trở thành absolute path.”**  
Không. Binder có thể chuyển kiểu, nhưng giá trị tương đối vẫn tương đối cho đến khi được resolve.

**“normalize() làm đường dẫn từ người dùng trở nên an toàn tuyệt đối.”**  
Không. Symlink, race condition và quyền filesystem cần được xử lý riêng.

**“Thư mục upload và thư mục multipart tạm là một.”**  
Không. Multipart temp data có thể bị framework dọn sau request; dữ liệu cần giữ phải được lưu ở nơi có lifecycle riêng.

**“Đường dẫn file log tương đối luôn là nơi lưu log vĩnh viễn.”**  
Không. CWD và chính sách volume/container quyết định vị trí và độ bền của dữ liệu.

**“WORKDIR trong Docker phải trùng nơi chứa JAR.”**  
Không. ENTRYPOINT có thể gọi JAR bằng absolute path trong khi WORKDIR được chọn độc lập.

**“Sửa ConfigMap/Secret nghĩa Spring Boot tự cập nhật mọi bean ngay.”**  
Không. Config Data thường được xử lý lúc startup; dynamic refresh/secret rotation cần cơ chế riêng.

**“Unit test với @SpringBootTest(properties=...) chứng minh external application.yml được tìm đúng.”**  
Không. Test property override kiểm tra binding/behavior của test context, không tự chứng minh location resolution của deployment.

**“Chỉ cần files tồn tại là app sẽ đọc đúng.”**  
Không. Cần đúng path, quyền, định dạng, profile, precedence và thời điểm nạp.

**“Báo profile prod là đủ để khẳng định không dùng nhầm database staging.”**  
Không. Phải xác nhận effective datasource URL, danh tính hệ thống đích và bean/config thực tế.

## 31. Quy trình kiểm tra trước khi triển khai

Để giảm lỗi giữa IDE và JAR, có thể kiểm tra theo thứ tự:

### Bước 1 — Chọn loại resource

Tài nguyên được **đóng gói cùng code** hay cần **tồn tại độc lập ngoài artifact**?

- Nếu đi cùng version code và chỉ đọc → classpath Resource.
- Nếu được chỉnh theo môi trường → external Config Data hoặc environment/secret source.
- Nếu ứng dụng ghi dữ liệu → data directory hoặc object storage có lifecycle riêng.

### Bước 2 — Xác định CWD theo launcher

Ghi rõ:

~~~text
IDE working directory:
Terminal working directory:
systemd WorkingDirectory:
Docker WORKDIR:
Kubernetes workingDir:
~~~

Nếu bất kỳ phần nào đang dựa vào mặc định không rõ ràng, cân nhắc khai báo tường minh hoặc chuyển business data paths sang absolute locations.

### Bước 3 — Phân biệt ba loại đường dẫn

~~~text
JAR path:             /opt/order-api/app.jar
Config Data path:     /etc/order-api/
Application data:     /var/lib/order-api/
~~~

Không sử dụng một location cho cả ba chỉ vì tiện. Chúng có quyền truy cập, vòng đời và chính sách backup khác nhau.

### Bước 4 — Chọn cách nạp cấu hình ngoài

- Muốn giữ packaged defaults và override theo deploy → additional-location.
- Muốn kiểm soát lại toàn bộ search locations → location.
- Muốn import một file/config tree cụ thể từ Config Data → import.
- Muốn đổi basename application → config name.

Kiểm tra optional: có phù hợp với tính bắt buộc của file không.

### Bước 5 — Xác định active profile

Không chỉ nhìn tên file. Kiểm tra:

~~~java
environment.getActiveProfiles();
~~~

Nếu không có active profile, nhớ rằng default profiles vẫn có thể được sử dụng.

### Bước 6 — Xác minh effective properties và beans

Với các key ảnh hưởng hành vi quan trọng:

- Data directory.
- Database URL/identity.
- External service endpoint.
- Chế độ sandbox/live.
- Feature flags.
- Những credential bắt buộc (không in giá trị).

Hãy xác minh giá trị cuối và nguồn; sau đó xác nhận bean/service có dùng đúng cấu hình đó.

### Bước 7 — Kiểm tra filesystem và storage

Process có quyền đọc config và ghi data không? Volume có đúng mục đích và còn dung lượng không? Khi restart/deploy lại thì dữ liệu cần giữ có tồn tại không?

### Bước 8 — Dùng fail-fast cho điều kiện không thể thiếu

Nếu không có file cấu hình hoặc data directory bắt buộc, ứng dụng nên báo lỗi rõ ràng thay vì âm thầm dùng default nguy hiểm.

ApplicationRunner, @ConfigurationProperties validation và startup checks có thể hỗ trợ. Không nên chuyển mọi lỗi thành warning nếu ứng dụng không thể phục vụ an toàn.

### Bước 9 — Thử theo đúng môi trường thực tế

Một lần chạy JAR từ thư mục khác với project root, một container có readonly filesystem và một test external config trong thư mục tạm có thể phát hiện sớm nhiều giả định sai.

Không chỉ kiểm tra trong IDE với working directory mặc định.

## 32. Bài tập tự luyện

### Bài tập 1: Dự đoán đường dẫn

Giả sử:

~~~bash
cd /tmp/run-321
java -jar /opt/demo/demo.jar
~~~

Trong code:

~~~java
Path path = Path.of("reports/output.txt");
~~~

Hỏi: file output dự kiến được resolve ở đâu?

**Gợi ý:** dùng Path.toAbsolutePath().normalize() với CWD tương ứng.

**Kết quả khái niệm:** /tmp/run-321/reports/output.txt trên Unix, không tự chuyển sang /opt/demo/reports/output.txt.

### Bài tập 2: Phân biệt classpath và external file

Ứng dụng có:

~~~text
src/main/resources/templates/report.txt
~~~

Hỏi: sau khi build executable JAR, cách đọc nào ít phụ thuộc working directory nhất?

**Đáp án:** ClassPathResource("templates/report.txt").getInputStream() hoặc ResourceLoader với prefix classpath.

### Bài tập 3: Nạp thêm file production

Bạn có packaged application.yml và muốn bổ sung:

~~~text
/etc/demo/application-prod.yml
~~~

mà không bỏ packaged defaults.

**Đáp án định hướng:** dùng profile prod và spring.config.additional-location=file:/etc/demo/, sau đó kiểm tra effective properties trong process.

### Bài tập 4: Kiểm tra một override bất ngờ

application-prod.yml chứa:

~~~yaml
app:
  endpoint: https://prod.example.invalid
~~~

Nhưng process được chạy:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.endpoint=http://localhost:9000
~~~

Hỏi: có thể kết luận ứng dụng dùng endpoint nào chỉ từ profile prod không?

**Đáp án:** không. Command-line property có thể ghi đè Config Data. Trong cấu hình mặc định, effective app.endpoint sẽ là http://localhost:9000.

### Bài tập 5: Chọn nơi lưu upload

Ứng dụng có 3 replica Kubernetes và cần giữ file upload qua rollout.

Hỏi: nên ghi file vào ./uploads trong container hay một storage có lifecycle độc lập?

**Đáp án định hướng:** cần storage có tính bền vững và hỗ trợ mô hình nhiều replica, thường là object storage hoặc shared storage được thiết kế phù hợp. Không coi CWD hoặc container writable layer là kho dữ liệu bền vững.

## Ghi nhớ cốt lõi

**Working directory là gốc của filesystem relative paths**, không phải thư mục chứa JAR. Một lệnh dùng absolute JAR path vẫn có thể resolve các path như **./data** và **./config** theo thư mục từ nơi process được khởi chạy. IDE, terminal, systemd, Docker và Kubernetes có thể cung cấp CWD khác nhau, nên cùng artifact có thể biểu hiện khác.

**Classpath resources và external files là hai loại nguồn khác nhau.** File dưới src/main/resources thường được đóng gói vào JAR; đọc bằng ClassPathResource hoặc Resource.getInputStream(), không phụ thuộc vào source tree hay giả định Resource.getFile() luôn thành công. Với file cần ghi hoặc thay đổi qua deploy, dùng một Path/Resource ngoài JAR, quyền filesystem và cơ chế lưu trữ phù hợp.

**Spring Boot Config Data có search locations và precedence riêng.** Các đường dẫn ngoài mặc định như **file:./config/** gắn với CWD. **spring.config.location** lựa chọn lại locations; **spring.config.additional-location** bổ sung locations; **spring.config.import** nạp nguồn được khai báo; **spring.profiles.active** chọn profile nhưng không chứng minh mọi property lấy từ file profile-specific. Trước khi kết luận cấu hình đã đúng, hãy kiểm tra CWD, active profiles, Config Data locations, effective property values và bean sử dụng những giá trị đó.

Thiết kế bền vững nhất là **tách rõ artifact, cấu hình triển khai và dữ liệu runtime**, chọn đường dẫn có chủ đích, tránh phụ thuộc working directory ngầm định, bảo vệ secret và fail-fast nếu thiếu cấu hình quan trọng. Khi làm được điều đó, cùng một Spring Boot JAR có thể được chạy và đóng gói nhất quán từ máy phát triển đến các hệ thống triển khai thực tế.
