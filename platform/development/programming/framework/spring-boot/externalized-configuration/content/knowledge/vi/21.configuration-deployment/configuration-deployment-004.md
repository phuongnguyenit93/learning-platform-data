# Thư mục làm việc khác nhau và lỗi tìm cấu hình khi triển khai Spring Boot

## 1. Tình huống thực tế: cùng một JAR, chạy ở nơi này được, nơi khác lại sai

Một ứng dụng Spring Boot có thể chạy ổn trong IDE hoặc terminal của lập trình viên, nhưng khi chuyển sang máy chủ Linux, Windows Service, Docker hay Kubernetes thì:

- Không tìm thấy `application-prod.yml` từng nằm cạnh file JAR.
- Khởi động được nhưng lại nhận URL database, timeout hoặc profile cũ từ cấu hình đóng gói.
- Báo `ConfigDataLocationNotFoundException` với một đường dẫn tương đối.
- Thêm `--spring.config.additional-location=file:./config/` mà vẫn không thấy tệp mong muốn.
- Dùng cùng lệnh `java -jar /opt/catalog/catalog.jar` nhưng kết quả khác nhau giữa hai thư mục hiện tại.
- Một lần chạy bằng `systemd` hoặc container không đọc được volume mount, dù đọc được khi gọi từ shell tương tác.
- Đọc được tệp nhưng property bị một biến môi trường hoặc đối số dòng lệnh có ưu tiên cao hơn ghi đè.

Nguyên nhân thường không nằm ở bản thân nội dung YAML. Nhiều lỗi xuất phát từ việc nhầm **thư mục chứa JAR**, **working directory của tiến trình**, **đường dẫn trong classpath**, **đường dẫn tuyệt đối của filesystem** và **thứ tự ưu tiên nguồn cấu hình**.

> **Nguyên tắc quan trọng:** đường dẫn `file:./...` được giải quyết theo thư mục làm việc hiện tại của tiến trình Java. Nó không tự động lấy thư mục chứa `.jar` làm gốc. Cấu hình nằm bên trong JAR với `classpath:` lại tuân theo cơ chế classpath, không phụ thuộc đường dẫn `./config` của filesystem.

Bài này hướng tới Spring Boot 3.x với cơ chế **Config Data** từ Spring Boot 2.4 trở lên. Những quy tắc cốt lõi cũng xuất hiện trong các phiên bản mới hơn, nhưng luôn kiểm tra reference của phiên bản đang triển khai trước khi sử dụng tùy chọn mới.

## 2. Phân biệt bốn vị trí dễ bị nhầm

Hãy tưởng tượng một cấu trúc trên Linux:

~~~text
/opt/catalog/
├── catalog.jar
├── start.sh
└── config/
    └── application-prod.yml

/etc/catalog/
└── application.yml

/var/log/catalog/
└── ...
~~~

Có bốn khái niệm độc lập.

### 2.1. Thư mục chứa file JAR

Trong ví dụ là `/opt/catalog`. File `catalog.jar` nằm trong thư mục này, nhưng vị trí của file thực thi **không tự quyết định** thư mục gốc cho mọi `file:./...`.

### 2.2. Working directory hay current directory

Đây là **thư mục làm việc hiện tại của tiến trình** tại thời điểm thực thi. Nó thường được kế thừa từ shell, service manager hoặc container runtime.

Ví dụ:

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

Working directory thông thường là `/opt/catalog`.

Nhưng:

~~~bash
cd /tmp
java -jar /opt/catalog/catalog.jar
~~~

Working directory là `/tmp`, **không phải** `/opt/catalog`. Cùng file JAR nhưng `./config/` trỏ tới hai vị trí khác nhau.

### 2.3. Classpath

File `src/main/resources/application.yml` thường được đóng gói trong JAR và được tìm thấy ở classpath root. Các tài nguyên như `classpath:/application.yml` và `classpath:/config/application.yml` không được resolve như `file:./...`.

Một file `/etc/catalog/application.yml` trên filesystem **không tự biến thành classpath resource** chỉ vì có cùng tên. Cần dùng cơ chế cấu hình ngoài tương ứng.

### 2.4. Absolute filesystem path

Đường dẫn `/etc/catalog/application.yml` trỏ tới vị trí xác định theo filesystem của môi trường đang chạy. Nếu muốn chỉ định nó cho Spring Boot:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/application.yml
~~~

Ví dụ này tránh phụ thuộc current directory, dù còn phụ thuộc việc tệp có tồn tại và tài khoản tiến trình có quyền đọc.

## 3. Spring Boot tìm `application.properties`/`application.yaml` ở đâu theo mặc định?

Theo cơ chế Config Data, Spring Boot mặc định xem xét các nhóm vị trí cơ bản sau, từ vị trí ưu tiên thấp hơn đến cao hơn:

| Thứ tự khái quát | Vị trí | Phụ thuộc working directory? |
| --- | --- | --- |
| 1 | `classpath:/` | Không |
| 2 | `classpath:/config/` | Không |
| 3 | `file:./` | **Có** |
| 4 | `file:./config/` | **Có** |
| 5 | `file:./config/*/` | **Có** |

Các mục được sắp theo quy tắc precedence; cấu hình từ vị trí ưu tiên cao hơn có thể ghi đè property trùng tên từ vị trí thấp hơn.

Trong đó:

- `classpath:/` thường chứa file `application.yml` đã đóng gói cùng JAR.
- `classpath:/config/` là thư mục `config` trong classpath.
- `file:./` trỏ tới **working directory của tiến trình Java**.
- `file:./config/` trỏ tới thư mục con `config` của working directory.
- `file:./config/*/` mở rộng tới các thư mục con trực tiếp trong `./config` trên filesystem.

Vì vậy, khi shell đang ở `/tmp`, file mặc định bên ngoài được tìm trong:

~~~text
/tmp/application.yml
/tmp/config/application.yml
/tmp/config/<thu-muc-con>/application.yml
~~~

chứ không phải mặc định trong `/opt/catalog/config/application.yml` chỉ vì JAR nằm ở `/opt/catalog`.

### 3.1. Tên file thông thường

Không có tùy chỉnh, basename là `application`. Spring Boot hỗ trợ các định dạng Java Properties và YAML theo đuôi tương ứng, ví dụ:

~~~text
application.properties
application.yml
application.yaml
application-prod.properties
application-prod.yml
application-prod.yaml
~~~

File profile-specific như `application-prod.yml` được xét khi profile `prod` hoạt động.

Đừng giả định Spring Boot sẽ tự tìm một file tên `catalog-config.yml` ở bất cứ đâu. Muốn dùng basename khác cần `spring.config.name`, hoặc chỉ định vị trí file cụ thể.

### 3.2. Mặc định không có nghĩa luôn báo lỗi khi file không tồn tại

Spring Boot có thể khởi động bình thường nếu không có file external `./config/application.yml`, vì những vị trí mặc định không buộc phải chứa file. Khi đó cấu hình từ JAR, environment, system properties hoặc default của ứng dụng có thể vẫn giúp context được tạo.

Đây là lý do một lỗi working directory có thể **không xuất hiện dưới dạng exception**: ứng dụng chạy nhưng dùng giá trị không mong muốn.

## 4. Tái hiện: cùng một JAR nhưng working directory khác

Giả sử JAR có file nội bộ:

~~~yaml
# application.yml được đóng gói trong catalog.jar
app:
  region: dev
  mode: sandbox
~~~

Trên máy chủ có external config:

~~~text
/opt/catalog/config/application.yml
~~~

Nội dung:

~~~yaml
app:
  region: apac
  mode: production
~~~

Một bean quan sát:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class StartupInfo {

    @Bean
    ApplicationRunner printConfig(Environment environment) {
        return args -> {
            System.out.println("cwd=" + System.getProperty("user.dir"));
            System.out.println("app.region="
                    + environment.getProperty("app.region"));
            System.out.println("app.mode="
                    + environment.getProperty("app.mode"));
        };
    }
}
~~~

### Chạy cách A — trong thư mục ứng dụng

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

Working directory là `/opt/catalog`. Spring Boot có thể tìm được `/opt/catalog/config/application.yml` qua `file:./config/`.

Kết quả minh họa, giả sử không có nguồn cao hơn ghi đè:

~~~text
cwd=/opt/catalog
app.region=apac
app.mode=production
~~~

### Chạy cách B — ở thư mục khác

~~~bash
cd /tmp
java -jar /opt/catalog/catalog.jar
~~~

Bây giờ `file:./config/` là `/tmp/config/`. Nếu không có config ở đó, các giá trị đóng gói trong JAR có thể được dùng:

~~~text
cwd=/tmp
app.region=dev
app.mode=sandbox
~~~

**File JAR không đổi, mã nguồn không đổi, file external cũng không đổi.** Chỉ có **working directory** thay đổi nên nguồn cấu hình hiệu lực khác nhau.

### 4.1. Java `user.dir` và thao tác kiểm tra ở OS

Trong ứng dụng Java, có thể dùng:

~~~java
String currentDirectory = System.getProperty("user.dir");
~~~

Hoặc:

~~~java
import java.nio.file.Path;

Path cwd = Path.of("").toAbsolutePath().normalize();
System.out.println("cwd=" + cwd);
~~~

Đây là thông tin để **chẩn đoán**, không nên dùng nó làm nguồn duy nhất cho mọi chính sách bảo mật đường dẫn. Nó cũng không làm Spring Boot tự đổi đường dẫn config.

Trên terminal Unix:

~~~bash
pwd
pwd -P
~~~

Lệnh `pwd -P` giúp xem physical path khi shell đang ở một đường dẫn có symbolic link. Đối với symlink và filesystem mounts, cần quan sát cả tên đường dẫn mà tiến trình sử dụng và vị trí đích.

Trên PowerShell:

~~~powershell
Get-Location
~~~

Lệnh chạy Java qua service manager không mặc nhiên dùng working directory của **shell bạn đang đăng nhập**; phải kiểm tra cấu hình của chính service hoặc process.

## 5. Vì sao IDE chạy được nhưng production thất bại?

Một IDE như IntelliJ IDEA, Eclipse hoặc VS Code thường có cấu hình **Working directory** trong run/debug configuration. IDE có thể để working directory là project root, module root hoặc giá trị do người dùng chỉnh.

Giả sử source tree:

~~~text
catalog-service/
├── pom.xml
├── config/
│   └── application-local.yml
├── src/
│   └── main/
│       └── resources/
│           └── application.yml
└── target/
    └── catalog.jar
~~~

Nếu IDE dùng working directory `catalog-service/`, `file:./config/` trỏ vào thư mục `catalog-service/config`. Nhưng khi deploy JAR đến `/srv/catalog/` và khởi động service từ `/`, Spring Boot sẽ tìm `/config/` thay vì thư mục `/srv/catalog/config`.

Những khác biệt điển hình:

| Môi trường | Working directory thường gặp hoặc có thể đặt | `file:./config/` trỏ tới |
| --- | --- | --- |
| IDE theo project root | `.../catalog-service` | `.../catalog-service/config` |
| Shell sau `cd /srv/catalog` | `/srv/catalog` | `/srv/catalog/config` |
| Shell ở `/tmp` chạy JAR absolute | `/tmp` | `/tmp/config` |
| systemd | Theo `WorkingDirectory=` của unit, nếu có | Đường dẫn tương ứng |
| Docker | Theo `WORKDIR` trong image hoặc override runtime | `<container-cwd>/config` |
| Kubernetes | Theo `workingDir` của container hoặc default từ image/runtime | `<container-cwd>/config` |
| Windows Service | Tùy service wrapper và cấu hình startup | Không nên suy đoán |

Giải pháp là **quy định tường minh working directory hoặc config location** cho từng deployment, không dựa vào hành vi tình cờ của IDE.

## 6. `spring.config.location`: chỉ định nơi tìm cấu hình và thay thế mặc định

Khi cấu hình nằm ở một nơi cụ thể, có thể cung cấp:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.location=file:/etc/catalog/
~~~

Với một **directory location**, nên kết thúc đường dẫn bằng dấu `/`. Spring Boot dùng các tên file được hình thành từ `spring.config.name` và xét thêm profile-specific variants khi phù hợp.

Có thể chỉ định một file:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.location=file:/etc/catalog/application.yml
~~~

Trong trường hợp đó, đây là một **file location**, không phải directory. File được nạp trực tiếp; các profile-specific variants cũng có thể được xét theo quy tắc Config Data.

### 6.1. Điều rất quan trọng: `location` thay thế danh sách vị trí mặc định

Đặt:

~~~properties
spring.config.location=file:/etc/catalog/
~~~

là yêu cầu Spring Boot sử dụng tập location đã chỉ định **thay cho default search locations**, không đơn thuần thêm `/etc/catalog/` vào cuối.

Hệ quả: nếu trước đó ứng dụng dựa vào `classpath:/application.yml` để cung cấp defaults, cách đặt `spring.config.location` không có classpath location có thể khiến các default ấy **không còn được nạp theo đường tìm kiếm mặc định**.

Nếu muốn dùng cả nguồn classpath và external, phải cấu hình các locations phù hợp hoặc chọn `spring.config.additional-location`.

Ví dụ có chủ đích khai báo cả hai:

~~~bash
java -jar /opt/catalog/catalog.jar \
  '--spring.config.location=classpath:/,file:/etc/catalog/'
~~~

Trong ví dụ, location sau có thể ghi đè property cùng tên của location trước. Với profile-specific files và nhiều location groups, thứ tự cụ thể còn chịu quy tắc grouping.

### 6.2. Không đặt `spring.config.location` trong file mà nó có nhiệm vụ tìm

Để quyết định file nào được nạp, Spring Boot phải biết `spring.config.location` **từ rất sớm**.

Vì vậy, cách sau thường không giải quyết được bài toán:

~~~yaml
# application.yml được hy vọng sẽ tự chỉ đường tới file khác
spring:
  config:
    location: file:/etc/catalog/
~~~

Giá trị `spring.config.location` dùng để tìm config data phải được cung cấp qua nguồn **có mặt trước quá trình đó**, chẳng hạn OS environment, JVM system property hoặc command-line argument.

Ví dụ:

~~~bash
SPRING_CONFIG_LOCATION=file:/etc/catalog/ java -jar catalog.jar
~~~

hoặc:

~~~bash
java -Dspring.config.location=file:/etc/catalog/ -jar catalog.jar
~~~

Đặt ở thời điểm quá muộn không khiến Spring Boot quay lại quét toàn bộ file đã bỏ lỡ.

## 7. `spring.config.additional-location`: bổ sung ngoài defaults

Đa số ứng dụng muốn giữ cấu hình mặc định đóng gói trong JAR, rồi cho phép deployment ghi đè một vài key. Trong trường hợp đó, dùng:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Theo cơ chế Config Data, `additional-location` **mở rộng** các default locations chứ không thay thế chúng. Những property từ additional locations có thể ghi đè giá trị trùng key trong default config data.

Ví dụ JAR:

~~~yaml
# src/main/resources/application.yml
app:
  endpoint: https://sandbox.example.test
  connect-timeout: 3s
  retries: 2
~~~

File external:

~~~yaml
# /etc/catalog/application.yml
app:
  endpoint: https://api.example.test
  connect-timeout: 8s
~~~

Khi chạy với additional location và không có nguồn ưu tiên cao hơn:

~~~text
app.endpoint        = https://api.example.test
app.connect-timeout = 8s
app.retries         = 2
~~~

Giá trị `retries` vẫn được lấy từ JAR vì external config không khai báo key đó. Spring Boot giải quyết **từng property**, không chọn “một file thắng toàn bộ”.

### 7.1. So sánh ngắn

| Thuộc tính | Cách xử lý locations | Khi phù hợp |
| --- | --- | --- |
| `spring.config.location` | **Thay thế** các default search locations | Muốn toàn quyền chỉ định bộ nguồn Config Data |
| `spring.config.additional-location` | **Bổ sung** locations vào defaults | Giữ defaults trong JAR và thêm file theo deployment |
| `spring.config.name` | Thay đổi basename thay cho `application` | Dùng tên như `catalog` thay vì `application` |
| `spring.config.import` | Import location từ tài liệu Config Data đang được nạp | Phân tách cấu hình, import file/secret/config tree |

Các thuộc tính điều khiển tìm file phải có mặt đủ sớm để quy trình Config Data sử dụng.

## 8. `optional:`: file không tồn tại là lỗi hay được phép bỏ qua?

Khi **chỉ định rõ** một location mà nó không tồn tại, Spring Boot mặc định có thể ném:

~~~text
ConfigDataLocationNotFoundException
~~~

Ví dụ:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/missing.yml
~~~

Nếu deployment bắt buộc phải có file ấy, hành vi fail-fast là có ích: ứng dụng không âm thầm chạy với defaults không phù hợp.

Nếu file là tùy chọn, thêm `optional:`:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/optional.yml
~~~

Hoặc với directory:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/
~~~

Phân biệt:

- `optional:` cho phép **location không tồn tại** mà không tự tạo lỗi location-not-found.
- `optional:` **không** có nghĩa bỏ qua mọi YAML sai cú pháp, mọi lỗi conversion, mọi lỗi quyền đọc hay mọi cấu hình nghiệp vụ sai.
- `optional:` không tự xác minh xem file chứa những key bắt buộc hay không.
- Nếu file không tìm thấy, ứng dụng có thể tiếp tục dùng cấu hình khác hoặc fail do thiếu một property bắt buộc.

### 8.1. Vì sao `optional:` có thể nguy hiểm trong production?

Một service cần credentials từ `/etc/catalog/secret.yml` nhưng deploy nhầm đường dẫn. Nếu cấu hình là:

~~~bash
--spring.config.additional-location=optional:file:/etc/catalog/secret.yml
~~~

thì lỗi location missing có thể bị bỏ qua và ứng dụng chạy với thông số không mong muốn, hoặc thất bại muộn khi sử dụng dependency.

Với nguồn **thực sự bắt buộc**, không nên dùng `optional:` như một mẹo để “ứng dụng chạy bằng được”. Hãy giữ yêu cầu location bắt buộc, đồng thời validate các property quan trọng khi startup.

Nếu muốn bỏ qua *mọi* location-not-found exception, Spring Boot có `spring.config.on-not-found=ignore`, nhưng đây là cấu hình rất rộng; chỉ dùng khi hiểu rõ chính sách đối với file thiếu.

## 9. `file:`, `classpath:` và import-relative: ba cách giải quyết đường dẫn

### 9.1. `classpath:` tìm resource trên classpath

~~~properties
spring.config.import=optional:classpath:/features.yml
~~~

`features.yml` phải là resource trên classpath, ví dụ đặt trong `src/main/resources` để được đóng gói. Nó không tự tìm `/etc/catalog/features.yml` ngoài JAR.

### 9.2. `file:` tìm theo filesystem

~~~properties
spring.config.import=optional:file:/etc/catalog/features.yml
~~~

Đây là vị trí cố định theo filesystem Linux của môi trường chạy.

~~~properties
spring.config.import=optional:file:./features.yml
~~~

Dạng này phụ thuộc **working directory**.

### 9.3. Import-relative khác `file:./...`

Một điểm tinh tế: với `spring.config.import`, đường dẫn **không có prefix location** và không bắt đầu bằng `/` có thể được hiểu là **import-relative**, tức tương đối so với tài liệu đang khai báo `spring.config.import`.

Ví dụ:

~~~text
/etc/catalog/
├── application.yml
└── fragments/
    └── database.yml
~~~

Nếu `/etc/catalog/application.yml` chứa:

~~~yaml
spring:
  config:
    import: optional:fragments/database.yml
~~~

thì vị trí import có thể được giải quyết tương đối với file `application.yml` tại `/etc/catalog`, tức `/etc/catalog/fragments/database.yml`.

Ngược lại, cấu hình:

~~~yaml
spring:
  config:
    import: optional:file:./fragments/database.yml
~~~

là một location với prefix `file:` và `./`; nó là một đường dẫn filesystem tương đối theo working directory, **không mang cùng ngữ nghĩa import-relative**.

Đây là nguồn lỗi phổ biến khi một file được chuyển từ project root sang `/etc/catalog` và người triển khai giữ lại đường dẫn `file:./...` vì nghĩ nó luôn tương đối với vị trí YAML.

## 10. Xác định đúng đường dẫn khi dùng `spring.config.import`

Giả sử file trên máy:

~~~text
/etc/catalog/
├── application.yml
└── components/
    └── kafka.yml
~~~

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: optional:components/kafka.yml
~~~

Cách này biểu đạt: “import file bên cạnh trong thư mục con `components`”, theo quy tắc import-relative.

Nếu muốn tuyệt đối:

~~~yaml
spring:
  config:
    import: optional:file:/etc/catalog/components/kafka.yml
~~~

Hai cách có thể cùng trỏ tới một file trong deployment hiện tại, nhưng có trade-off:

- Import-relative thuận tiện khi di chuyển **cả bộ thư mục config** sang nơi khác.
- Absolute filesystem path thuận tiện khi môi trường quy định một đường dẫn cố định.
- `file:./...` thuận tiện khi working directory được kiểm soát nhưng rất dễ sai nếu startup được kích hoạt từ nhiều nơi.

### 10.1. Trường hợp file không có phần mở rộng

Kubernetes và một số cơ chế secret mount có thể tạo file không đuôi:

~~~text
/etc/catalog/keys/token
~~~

Khi cần import file như YAML nhưng nó không có suffix, Spring Boot có **extension hint**:

~~~properties
spring.config.import=optional:file:/etc/catalog/keys/token[.yaml]
~~~

Không nên coi đường dẫn không có đuôi là YAML tự động. Và nếu thư mục chứa nhiều file key/value thay vì một YAML, có thể cần `configtree:` chứ không phải extension hint.

## 11. Wildcard mặc định `file:./config/*/` và hiểu nhầm “quét đệ quy”

Từ cơ chế Config Data hiện đại, Spring Boot có thể tìm các file cấu hình trong thư mục con trực tiếp của `./config`.

Ví dụ working directory là `/srv/catalog`:

~~~text
/srv/catalog/
└── config/
    ├── database/
    │   └── application.yml
    ├── messaging/
    │   └── application.yml
    └── cache/
        └── application.yml
~~~

Default location `file:./config/*/` có thể xét các thư mục:

~~~text
./config/database/
./config/messaging/
./config/cache/
~~~

Nhưng `*` trong location dạng này **không có nghĩa quét đệ quy vô hạn** mọi cấp thư mục. Spring Boot wildcard location thường chỉ mở rộng **một tầng thư mục con** theo cú pháp được hỗ trợ.

Một số quy tắc:

- Wildcard chỉ hỗ trợ **external filesystem locations**, không dùng với `classpath:`.
- Một wildcard location có một dấu `*` ở vị trí được hỗ trợ.
- Với directory location, mẫu có dạng `*/`.
- Với file location, có thể có dạng `*/<filename>`.
- Wildcard matches được xử lý theo thứ tự xác định, thường là sắp xếp tên đường dẫn tuyệt đối theo alphabet.

Nếu bạn có cấu trúc:

~~~text
config/region/eu/application.yml
~~~

đừng mặc định `file:./config/*/` sẽ quét cả cấp `region/eu`. Khi cần các cấp lồng sâu, hãy chỉ định những location thích hợp hoặc thay đổi cấu trúc mount.

### 11.1. Wildcard chỉ còn hữu ích nếu working directory đúng

Khi working directory đổi từ `/srv/catalog` sang `/`, `file:./config/*/` trở thành `/config/*/`. Dù logic wildcard chính xác, nó vẫn có thể quét **sai cây thư mục**.

Đây là lỗi đường dẫn trước khi là lỗi YAML.

## 12. Profile: đúng thư mục nhưng sai file profile

Một lỗi khác có biểu hiện gần giống lỗi working directory: file `application-prod.yml` tồn tại ở vị trí được tìm, nhưng profile `prod` không được bật.

Ví dụ:

~~~text
/etc/catalog/
├── application.yml
└── application-prod.yml
~~~

Nếu ứng dụng chạy với:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

mà không kích hoạt `prod`, không nên kỳ vọng mọi property trong `application-prod.yml` được áp dụng.

Bật profile qua CLI:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Hoặc biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/ \
java -jar catalog.jar
~~~

Khi profile `prod` hoạt động, Spring Boot xét các file `application-prod.yml`/`.properties` trong locations có liên quan.

### 12.1. Đường dẫn file và profile-specific variants

Khi chỉ định một file location như:

~~~bash
--spring.config.location=file:/etc/catalog/application.yml
~~~

Spring Boot có thể xét cả profile-specific variants phù hợp, theo quy tắc Config Data.

Không nên tự tạo một chuỗi logic rằng “chỉ định file cụ thể thì chắc chắn không xét profile”. Điều quan trọng là biết tập location, profile đang active và nguồn nào có ưu tiên cao hơn.

### 12.2. Nhiều profile và precedence

Với `prod,live`, các tài liệu theo profile có quy tắc **last-wins** ở mức location group. Khi kết hợp nhiều locations và groups, thứ tự có thể khó quan sát bằng mắt.

Nếu đang chẩn đoán “file đã được nạp nhưng value vẫn khác”, hãy xem:

1. Profile thực sự được kích hoạt.
2. Có file cùng tên trong location ưu tiên cao hơn hay không.
3. Có biến môi trường/JVM system property/CLI cùng key hay không.
4. Các nhóm location được phân tách bằng `,` hay `;`.
5. Bản thân property có được khai báo trong nhiều tài liệu YAML với điều kiện profile hay không.

## 13. Trường hợp nhiều locations: dấu phẩy và location groups

`spring.config.location` và `spring.config.additional-location` có thể nhận nhiều locations.

Ví dụ:

~~~bash
java -jar catalog.jar \
  '--spring.config.additional-location=file:/etc/catalog/base/,file:/etc/catalog/override/'
~~~

Thông thường các locations sau có thể ghi đè values trùng key từ locations trước.

Khi xử lý nhiều profiles, Spring Boot có khái niệm **location group**. Các phần tử trong cùng group được phân tách bởi dấu `;` thay vì dấu `,`.

Ví dụ minh họa:

~~~text
file:/etc/catalog/a/;file:/etc/catalog/b/
~~~

Khác với:

~~~text
file:/etc/catalog/a/,file:/etc/catalog/b/
~~~

Sự khác nhau là cách nhóm các locations ở cùng level khi Spring Boot áp dụng thứ tự tài liệu theo profile. Nó có thể ảnh hưởng giá trị cuối khi hai locations đều có `application-prod.yml` và `application-live.yml`.

Trong shell, dấu `;` có ý nghĩa đặc biệt ở một số ngữ cảnh, nên cần **quote toàn bộ argument** chứa groups:

~~~bash
java -jar catalog.jar \
  '--spring.config.additional-location=file:/etc/catalog/a/;file:/etc/catalog/b/'
~~~

Nếu chỉ cần một external directory, **đừng làm phức tạp bằng nhiều location groups**. Dùng một directory rõ ràng, rồi bổ sung thêm khi có yêu cầu thật.

## 14. Linux `systemd`: service chạy với working directory nào?

Khi bạn tự đăng nhập SSH và chạy:

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

working directory là `/opt/catalog`.

Nhưng service `systemd` thường được chạy bởi service manager theo unit configuration, **không kế thừa thư mục bạn vừa `cd` trong shell**.

Một unit minh họa:

~~~ini
# /etc/systemd/system/catalog.service
[Unit]
Description=Catalog Spring Boot Service
After=network.target

[Service]
Type=simple
User=catalog
Group=catalog
WorkingDirectory=/opt/catalog
ExecStart=/usr/bin/java -jar /opt/catalog/catalog.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

`WorkingDirectory=/opt/catalog` làm cho `file:./config/` hướng tới `/opt/catalog/config/`.

Nếu muốn tách runtime config khỏi thư mục JAR, có thể dùng:

~~~ini
[Service]
Type=simple
User=catalog
Group=catalog
WorkingDirectory=/opt/catalog
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/
ExecStart=/usr/bin/java -jar /opt/catalog/catalog.jar
~~~

Khi đó application vừa có default classpath, vừa lấy config ở `/etc/catalog/` mà không phụ thuộc việc file cấu hình được chép cạnh JAR.

### 14.1. Chẩn đoán unit thực tế

Trên máy Linux:

~~~bash
systemctl cat catalog.service
systemctl show catalog.service -p WorkingDirectory -p Environment
journalctl -u catalog.service -b --no-pager
~~~

Các lệnh này giúp đối chiếu unit thực sự được áp dụng, thông tin working directory và log startup. Không đưa secret trực tiếp vào output chia sẻ hoặc log; biến `Environment=...` có thể chứa dữ liệu nhạy cảm nếu thiết kế deployment không phù hợp.

Sau khi sửa unit file, thông thường cần:

~~~bash
sudo systemctl daemon-reload
sudo systemctl restart catalog.service
~~~

Lệnh ví dụ dành cho môi trường bạn quản trị, không phải bước bắt buộc để hiểu lỗi. Khi sửa service production, tuân theo change management và rollback của hệ thống.

### 14.2. Quyền đọc cũng quan trọng

Một file tồn tại tại `/etc/catalog/application.yml` nhưng user `catalog` không có quyền đọc có thể làm startup fail hoặc không thể load cấu hình đúng.

Kiểm tra:

~~~bash
ls -ld /etc/catalog
ls -l /etc/catalog/application.yml
~~~

Với thư mục nằm trên nhiều cấp, process cần quyền traverse đối với các parent directories và quyền đọc file. Đừng giải quyết bằng cách `chmod 777` hoặc cấp world-readable cho secret. Chọn owner/group, ACL hoặc mount permissions phù hợp.

## 15. Docker: `WORKDIR`, mount và đường dẫn trong container

Giả sử Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/catalog.jar /app/catalog.jar
ENTRYPOINT ["java", "-jar", "/app/catalog.jar"]
~~~

Với `WORKDIR /app`, các relative locations mặc định của Spring Boot như `file:./config/` trỏ tới `/app/config/` **bên trong container**.

Chạy:

~~~bash
docker run --rm \
  --mount type=bind,source=/srv/catalog/config,target=/app/config,readonly \
  catalog:latest
~~~

Nếu host có:

~~~text
/srv/catalog/config/application.yml
~~~

thì container có thể đọc file dưới:

~~~text
/app/config/application.yml
~~~

và Spring Boot có thể tìm thấy nó qua default `file:./config/`.

### 15.1. Cùng image, working directory khác

Container runtime có thể override working directory:

~~~bash
docker run --rm -w /tmp catalog:latest
~~~

Bây giờ default `file:./config/` tương ứng với `/tmp/config/` trong container, không phải `/app/config/`. Dù JAR vẫn ở `/app/catalog.jar`, external config dưới `/app/config` không còn được tìm theo đường mặc định tương đối.

Cách khắc phục:

- Giữ `WORKDIR /app` và không override tùy tiện.
- Hoặc chỉ định absolute external location:

~~~bash
docker run --rm \
  -w /tmp \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/app/config/ \
  --mount type=bind,source=/srv/catalog/config,target=/app/config,readonly \
  catalog:latest
~~~

Đường `/app/config/` là path **trong container**, không phải path trên host.

### 15.2. Kiểm tra từ bên trong container

Khi container còn chạy, có thể quan sát:

~~~bash
docker exec catalog sh -c 'pwd; ls -la /app/config'
~~~

Điều này giúp xác nhận ba vấn đề độc lập:

1. Container current directory.
2. Có mount ở đúng path container không.
3. User chạy Java có nhìn thấy file không.

Một bind mount có source sai, target sai hoặc file permissions sai có thể gây biểu hiện giống lỗi `spring.config.location`. Không nên sửa chỉ bằng đổi tên file mà chưa kiểm tra mount topology.

## 16. Docker Compose: dùng path cố định thay vì kỳ vọng CWD

Ví dụ Compose:

~~~yaml
services:
  catalog:
    image: catalog:latest
    working_dir: /app
    volumes:
      - ./config:/etc/catalog:ro
    environment:
      SPRING_PROFILES_ACTIVE: prod
      SPRING_CONFIG_ADDITIONAL_LOCATION: file:/etc/catalog/
~~~

Ở đây có **hai loại đường dẫn tương đối khác nhau**:

- `./config` ở phía host trong cấu hình Compose là source volume path, được Compose giải quyết theo ngữ cảnh project/Compose file.
- `file:/etc/catalog/` là path tuyệt đối **bên trong container**, được Spring Boot dùng để nạp config.

Đừng gộp chúng thành một khái niệm. Việc sửa working directory của process Java trong container không thay đổi mount target tuyệt đối `/etc/catalog`.

Với cấu trúc:

~~~text
project/
├── compose.yaml
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

dịch vụ sẽ tìm hai file trong `/etc/catalog` khi deploy đúng volume.

Nếu dùng mount chứa credentials, không đưa secret plaintext vào repository; dùng cơ chế secret/config phù hợp với môi trường.

### 16.1. Lưu ý health check

Một container khởi động thành công chưa chứng minh nó đã nạp đúng external config. Nếu fallback trong JAR hợp lệ, service có thể chạy lên nhưng kết nối sai môi trường.

Bổ sung kiểm tra ứng dụng sẵn sàng theo dependency thực tế, đồng thời kiểm tra **giá trị định danh môi trường không nhạy cảm** hoặc yêu cầu một property bắt buộc thể hiện deployment.

## 17. Kubernetes: `workingDir`, ConfigMap và Secret mounts

Trong Kubernetes, container chạy trong một filesystem riêng. Đường dẫn local trên máy build hoặc node không tự xuất hiện trong pod nếu không có volume mount tương ứng.

Một ví dụ ConfigMap chứa `application.yml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config
data:
  application.yml: |
    app:
      region: apac
      endpoint: https://api.example.test
~~~

Deployment container (trích đoạn minh họa):

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: catalog:latest
          workingDir: /app
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/catalog/"
          volumeMounts:
            - name: catalog-config
              mountPath: /etc/catalog
              readOnly: true
      volumes:
        - name: catalog-config
          configMap:
            name: catalog-config
~~~

Ở đây Spring Boot nạp từ `/etc/catalog/`, không phụ thuộc `workingDir: /app`. Kubernetes ConfigMap mount hiển thị file `/etc/catalog/application.yml` bên trong container.

Một pod dùng `workingDir: /app` và **không** có `SPRING_CONFIG_ADDITIONAL_LOCATION` vẫn có thể tìm config nếu file được mount ở `/app/config/application.yml`, nhưng mount `/etc/catalog` không tự được quét bởi default `file:./config/`.

### 17.1. Phân biệt YAML file và configuration tree

Nếu volume có:

~~~text
/etc/catalog/secrets/
├── db.username
└── db.password
~~~

mỗi file chứa một value riêng, đây không phải file `application.yml` bình thường.

Có thể dùng config tree import:

~~~properties
spring.config.import=optional:configtree:/etc/catalog/secrets/
~~~

Khi đó tên file `db.username` và `db.password` có thể trở thành property names, theo quy tắc config tree. Cơ chế này khác với:

~~~properties
spring.config.additional-location=file:/etc/catalog/secrets/
~~~

vốn tìm những file có tên/định dạng Config Data như `application.properties` hoặc `application.yml` trong directory.

**Chọn đúng loại nguồn:** một file YAML hoàn chỉnh thì dùng file/directory location; nhiều file key/value thì cân nhắc `configtree:`.

### 17.2. Quyền đọc và cập nhật ConfigMap

Pod có thể mount ConfigMap/Secret nhưng user trong container vẫn gặp giới hạn quyền filesystem tùy `securityContext`, `defaultMode`, nhóm và chính sách security.

Ngoài ra, cập nhật ConfigMap volume **không bảo đảm** bean `@ConfigurationProperties` được rebind ngay. Spring Boot thông thường bind cấu hình lúc startup; muốn áp dụng thay đổi có thể cần rollout/restart hoặc cơ chế refresh được thiết kế riêng.

Đừng coi việc volume được cập nhật là bằng chứng cấu hình hiệu lực trong process đã đổi.

## 18. Windows: working directory và đường dẫn khác ổ đĩa

Trên Windows, khi dùng PowerShell:

~~~powershell
Set-Location C:\apps\catalog
java -jar .\catalog.jar
~~~

Working directory là `C:\apps\catalog`.

Nhưng:

~~~powershell
Set-Location C:\Temp
java -jar C:\apps\catalog\catalog.jar
~~~

Working directory là `C:\Temp`. Default `file:./config/` sẽ tương ứng với `C:\Temp\config`.

Để chỉ định thư mục cấu hình tuyệt đối trong Spring Boot, có thể dùng URI-style path với dấu `/`:

~~~powershell
java -jar C:\apps\catalog\catalog.jar "--spring.config.additional-location=file:C:/apps/catalog/config/"
~~~

Cú pháp file URL, dấu nháy và drive letter cần được kiểm tra trên môi trường Windows/Java đang chạy. Dùng đường dẫn tuyệt đối theo kiểu URI phù hợp thay vì tự thêm nhiều dấu backslash khiến shell hoặc parser hiểu sai.

### 18.1. Windows Service khác terminal

Khi ứng dụng chạy thông qua một service wrapper, Scheduled Task hoặc một tiến trình được khởi tạo bởi công cụ quản trị, current directory có thể khác với terminal developer. Nó thậm chí có thể là một thư mục hệ thống thay vì nơi đặt JAR.

Giải pháp đáng tin cậy:

- Khai báo working directory trong service wrapper nếu nó hỗ trợ.
- Dùng path tuyệt đối cho external Config Data.
- Kiểm tra identity của service có quyền đọc file.
- Quan sát `user.dir` trong giai đoạn chẩn đoán.
- Không dựa vào biến môi trường chỉ tồn tại trong phiên PowerShell tương tác nếu service không thừa hưởng biến đó.

## 19. CI/CD: bảo đảm artifact và config không bị phụ thuộc đường dẫn build

Pipeline CI/CD thường tạo JAR tại:

~~~text
workspace/project/target/catalog.jar
~~~

và triển khai nó đến:

~~~text
/opt/catalog/catalog.jar
~~~

Nếu trong source có code hay script đọc:

~~~text
./config/application.yml
~~~

thì ở CI có thể trỏ về `workspace/project/config` nhưng ở máy chủ lại trỏ về `/config` hoặc `/opt/catalog/config` tùy service runner.

Một deployment có thể lặp lại nên quy định rõ:

1. JAR được đặt ở đâu.
2. ConfigData được mount/copy ở đâu.
3. User chạy process là ai.
4. Working directory là gì.
5. Profile nào được bật.
6. `spring.config.location` hay `spring.config.additional-location` nào được cung cấp.
7. File nào bắt buộc, file nào optional.
8. Quyền đọc và thứ tự ưu tiên khi có override.
9. Quy trình reload/restart khi config thay đổi.

Ví dụ script khởi động rõ ràng:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_HOME=/opt/catalog
CONFIG_DIR=/etc/catalog

cd "$APP_HOME"

exec /usr/bin/java \
  -Dspring.profiles.active=prod \
  -Dspring.config.additional-location="file:$CONFIG_DIR/" \
  -jar "$APP_HOME/catalog.jar"
~~~

`exec` thay thế shell process bằng Java process, thường thuận tiện cho signal handling. Đường dẫn Config Data là absolute nên ngay cả khi thay đổi `cd` trong script, location `/etc/catalog` vẫn rõ ràng.

Trong production, đường dẫn, user và timeout cần theo convention của hệ thống. Script minh họa không tự xác minh đầy đủ chính sách bảo mật hay khả năng đọc của file.

## 20. Một bộ cấu hình deployment có thể tái lập

Đề xuất cấu trúc cho Linux:

~~~text
/opt/catalog/
└── catalog.jar

/etc/catalog/
├── application.yml
└── application-prod.yml
~~~

JAR chứa các giá trị default không nhạy cảm:

~~~yaml
# classpath:/application.yml
app:
  region: local
  connect-timeout: 3s
  retries: 2
~~~

File external:

~~~yaml
# /etc/catalog/application.yml
app:
  region: apac
  connect-timeout: 8s
~~~

File external theo profile:

~~~yaml
# /etc/catalog/application-prod.yml
app:
  retries: 4
~~~

Lệnh:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Kết quả dự kiến nếu không có nguồn ưu tiên cao hơn:

| Property | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `app.region` | `apac` | External `application.yml` |
| `app.connect-timeout` | `8s` | External `application.yml` |
| `app.retries` | `4` | External `application-prod.yml` |

Nếu external `application.yml` không có `app.retries` thì giá trị default `2` trong JAR vẫn có thể được dùng, nhưng file profile `application-prod.yml` ghi đè thành `4`.

Lưu ý một file YAML nằm đúng vị trí và được nạp không có nghĩa nó sẽ thắng **mọi** nguồn. Một biến môi trường hoặc CLI option có thể ghi đè từng property.

## 21. Không tìm thấy file hay file được nạp nhưng bị ghi đè?

Hai tình huống cần phân biệt rõ.

### 21.1. File thực sự không được nạp

Ví dụ:

~~~text
Expect: /etc/catalog/application-prod.yml
Actual: /etc/catalog/application.yml
Active profiles: default
~~~

Có thể do profile sai hoặc file missing.

Hoặc:

~~~text
Expect: /opt/catalog/config/application.yml
CWD:    /tmp
Default location resolved to: /tmp/config/
~~~

Đây là lỗi working directory.

### 21.2. File đã được nạp nhưng giá trị không thắng

Giả sử file:

~~~yaml
app:
  region: apac
~~~

Deployment có:

~~~bash
APP_REGION=eu java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Nếu OS environment đang cung cấp `APP_REGION=eu` với ưu tiên cao hơn config file, `app.region` hiệu lực có thể là `eu`.

Vì vậy, không được kết luận “Spring Boot không tìm thấy YAML” chỉ bằng việc nhìn thấy một property khác với mong đợi. Cần xác định **file có tham gia Config Data hay không** và **nguồn property nào thắng**.

### 21.3. Tránh suy luận từ `Environment.containsProperty`

~~~java
environment.containsProperty("app.region");
~~~

chỉ trả lời liệu key có giá trị được giải quyết hay không. Nó **không cho biết** key đến từ external YAML, classpath YAML, variable hay CLI. Muốn debug nguồn gốc, dùng khả năng quan sát property sources với hạn chế bảo mật.

## 22. Kiểm tra từ log Spring Boot Config Data

Để xem quá trình tìm/nạp config, Spring Boot có logger thuộc namespace:

~~~text
org.springframework.boot.context.config
~~~

Có thể bật mức TRACE khi chẩn đoán:

~~~bash
java -jar catalog.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Hoặc khi cần chỉ định location:

~~~bash
java -jar catalog.jar \
  --logging.level.org.springframework.boot.context.config=TRACE \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Log thường cung cấp dấu vết của location candidates, documents và Config Data processing theo phiên bản Spring Boot. Tên message và mức chi tiết có thể thay đổi giữa các version; đừng tạo parser production phụ thuộc nguyên văn log.

**Lưu ý bảo mật:** TRACE có thể tạo rất nhiều thông tin cấu hình/môi trường. Dùng có thời hạn và tránh sao chép log chứa secret sang nơi truy cập công khai.

Một lựa chọn khác, khi đã bật Spring Boot Actuator một cách an toàn, là xem:

~~~text
/actuator/env
/actuator/configprops
~~~

`/actuator/env` giúp quan sát property sources/giá trị hiệu lực, còn `/actuator/configprops` giúp xem những object đã bind. Các endpoint này phải được bảo vệ và được cấu hình redaction cho dữ liệu nhạy cảm; không mở public chỉ để debug một file YAML.

## 23. Checklist chẩn đoán theo thứ tự

Khi deployment báo lỗi cấu hình, có thể xử lý theo thứ tự:

1. **Đúng artifact?** Kiểm tra file JAR/version đang chạy, không giả định từ tên service.
2. **Đúng working directory?** Trong process, in `user.dir` hoặc xem service/container `workingDir`.
3. **Đúng path external?** Với `file:./...`, tự thay `.` bằng working directory thật.
4. **Tệp có tồn tại?** Kiểm tra chính filesystem nhìn từ process/container, không chỉ máy host.
5. **Có quyền đọc?** Xác minh owner/group/ACL/mount permissions của process user.
6. **Tên file có đúng không?** `application.yml` hay `application-prod.yml`; `spring.config.name` có bị override không?
7. **Profiles đúng không?** Xác minh `spring.profiles.active` từ runtime.
8. **Dùng `location` hay `additional-location`?** `location` thay default; `additional-location` bổ sung default.
9. **Có `optional:` không?** Location missing có thể bị cho qua.
10. **Import có đúng ngữ nghĩa không?** `file:./...` theo CWD, import-relative theo file khai báo.
11. **Config tree hay YAML?** Nhiều file key/value không giống một file `application.yml`.
12. **File được nạp nhưng có override?** Kiểm tra CLI, JVM system properties, OS env và profile-specific sources.
13. **Có lỗi conversion/validation không?** Tệp được tìm không có nghĩa mọi property hợp lệ.
14. **Đang chạy phiên bản nào?** Cách nạp Config Data có thể khác giữa Boot 2.3 và 2.4+, hoặc các version mới hơn.
15. **Sau khi sửa config đã restart/refresh đúng chưa?** Spring Boot thông thường không tự rebind khi file thay đổi.

Đi qua checklist này trước khi sửa mã Java. Rất nhiều sự cố có thể được giải quyết bằng sửa startup command, mount path hoặc quyền đọc.

## 24. Những lỗi cụ thể và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chạy IDE được, systemd không thấy `./config` | Working directory khác | Đặt `WorkingDirectory` hoặc dùng absolute additional-location |
| Chạy `java -jar /opt/app.jar` từ `/tmp` nhận config mặc định | CWD là `/tmp` | `cd` đúng thư mục hoặc chỉ rõ `file:/opt/...` |
| Docker có file ở host nhưng app không thấy | Chưa mount hoặc mount sai target | Kiểm tra `--mount`, `volumes` và filesystem bên trong container |
| Kubernetes mount ConfigMap ở `/etc/app` nhưng app dùng `./config` | Hai path không trùng | Đặt `SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/app/` |
| `application-prod.yml` không có hiệu lực | Profile `prod` chưa active | Cấp `SPRING_PROFILES_ACTIVE=prod` |
| Cấu hình đóng gói trong JAR không còn được dùng | `spring.config.location` đã thay defaults | Dùng `additional-location` nếu muốn giữ JAR defaults |
| Startup fail với `ConfigDataLocationNotFoundException` | Explicit location không tồn tại | Sửa path hoặc dùng `optional:` khi thật sự optional |
| File tồn tại mà không đọc được | Permission/ACL/SELinux/mount | Kiểm tra identity và quyền truy cập phù hợp |
| App không nhận file `custom.yml` | Basename không phải `application` hoặc chưa import | Dùng `spring.config.name`, location file hoặc `spring.config.import` |
| Dùng `spring.config.location` trong YAML để chỉ tới YAML khác nhưng không có tác dụng | Thuộc tính được đọc quá muộn | Cấp từ OS env/JVM system property/CLI từ đầu |
| `file:./child.yml` trỏ sai | CWD khác file chứa import | Dùng import-relative `child.yml` hoặc absolute path |
| `config/*/` không tìm file hai cấp dưới | Wildcard chỉ một tầng | Đổi layout hoặc chỉ định thêm location |
| ConfigMap đã cập nhật nhưng app vẫn dùng giá trị cũ | Không có tự động refresh | Restart/rollout hoặc áp dụng cơ chế reload được thiết kế |
| Trông như YAML bị bỏ qua nhưng `APP_REGION` đang đặt | Source precedence | Xác định giá trị hiệu lực và nguồn override |
| Bật `optional:` rồi startup được nhưng chạy sai môi trường | Missing external config bị bỏ qua | Chỉ optional hóa file thật sự tùy chọn và thêm validation |
| Nhiều profile dùng config không như dự đoán | Location groups/order | Kiểm tra thứ tự `,` và `;` cùng active profiles |
| Secret file mount được nhưng không thành property | File key/value chưa dùng config tree | `spring.config.import=configtree:/...` đúng loại nguồn |

## 25. Dùng validation để không âm thầm chạy sai môi trường

Lỗi working directory có thể khiến Spring Boot đọc file default trong JAR mà không báo lỗi. Nếu cấu hình default hợp lệ về kiểu nhưng **không hợp lệ cho production**, bạn cần contract startup rõ ràng.

Ví dụ yêu cầu deployment xác định một ID môi trường:

~~~yaml
# External config production
app:
  deployment:
    id: prod-apac-01
  endpoint: https://api.example.test
~~~

Một model `@ConfigurationProperties`:

~~~java
package com.example.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.deployment")
public record DeploymentProperties(
        @NotBlank String id) {
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(DeploymentProperties.class)` và có một Bean Validation implementation phù hợp (thường `spring-boot-starter-validation` ở Spring Boot 3.x).

Nếu không có bất kỳ nguồn nào cung cấp `app.deployment.id`, ứng dụng có thể fail trong quá trình bind/validate thay vì silently chọn environment không xác định.

Tuy vậy, nếu JAR đã đóng gói một `id` giả nhưng không blank, `@NotBlank` **không nhận ra** đó là môi trường sai. Khi cần nghiêm ngặt, hãy thiết kế rule kiểm tra deployment ID phải khớp nguồn triển khai hoặc một giá trị kỳ vọng được cung cấp độc lập. Không dùng một default production giả trong JAR để vượt qua validation.

### 25.1. Không để secrets làm dấu vết chẩn đoán

Không in database password, API token hoặc toàn bộ `Environment` để chứng minh file đã được nạp. Có thể thêm một property **không nhạy cảm** như `app.deployment.id` để log có kiểm soát.

Ví dụ:

~~~java
@Bean
ApplicationRunner printDeploymentId(DeploymentProperties properties) {
    return args -> System.out.println(
            "deployment.id=" + properties.id());
}
~~~

Một service ở production nên dùng logging framework và có quy tắc mức log cụ thể; `System.out.println` ở đây chỉ minh họa ý tưởng.

## 26. Bài tập thực hành

### Bài 1 — Dự đoán đường dẫn

Cho:

~~~text
JAR: /opt/catalog/catalog.jar
Config: /opt/catalog/config/application.yml
Current directory khi chạy: /tmp
Command: java -jar /opt/catalog/catalog.jar
~~~

**Câu hỏi:** Spring Boot mặc định dùng `file:./config/` để tìm file nào?

**Đáp án:** đường dẫn tương ứng là `/tmp/config/`. File `/opt/catalog/config/application.yml` không được tự tìm qua location đó.

**Cách sửa A:**

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

**Cách sửa B:**

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/opt/catalog/config/
~~~

Cách B không phụ thuộc current directory.

### Bài 2 — Giữ default trong JAR

JAR có `classpath:/application.yml` chứa `app.timeout=3s`. File `/etc/catalog/application.yml` chỉ chứa `app.endpoint`.

**Câu hỏi:** dùng `spring.config.location=file:/etc/catalog/` hay `spring.config.additional-location=file:/etc/catalog/` để giữ `app.timeout` từ JAR?

**Đáp án:** dùng `spring.config.additional-location`. `location` thay thế default search locations, nên không tự bảo đảm file classpath được nạp.

### Bài 3 — Location không tồn tại

Lệnh:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/missing.yml
~~~

Nếu location được chỉ định không tồn tại, ứng dụng có thể gặp lỗi gì?

**Đáp án:** `ConfigDataLocationNotFoundException`. Dùng `optional:file:/etc/catalog/missing.yml` chỉ khi file thực sự optional. Với file bắt buộc, sửa path và quyền đọc.

### Bài 4 — Phân biệt import-relative

File `/etc/catalog/application.yml` có:

~~~yaml
spring:
  config:
    import: optional:parts/limits.yml
~~~

Nó tìm file ở đâu?

**Đáp án:** theo ngữ nghĩa import-relative, dưới `/etc/catalog/parts/limits.yml`.

Nếu đổi thành:

~~~yaml
spring:
  config:
    import: optional:file:./parts/limits.yml
~~~

thì đó là một filesystem location có prefix `file:` phụ thuộc working directory của tiến trình. Chúng không tương đương khi app chạy ở một thư mục khác.

### Bài 5 — Đường dẫn trong Docker

Dockerfile đặt `WORKDIR /app`, config được mount ở `/etc/catalog/application.yml`, nhưng không có `SPRING_CONFIG_ADDITIONAL_LOCATION`.

**Câu hỏi:** Spring Boot mặc định có tự quét `/etc/catalog/` không?

**Đáp án:** Không chỉ vì đó là đường dẫn trong container. Default external search locations theo `/app` gồm `/app` và `/app/config` (cùng các thư mục con trực tiếp trong `config`). Hãy đặt additional location tuyệt đối hoặc mount vào default location phù hợp.

### Bài 6 — Đúng file nhưng sai value

YAML external:

~~~yaml
app:
  region: apac
~~~

Container chạy với biến:

~~~bash
APP_REGION=eu
~~~

**Câu hỏi:** tại sao đọc `Environment.getProperty("app.region")` có thể ra `eu`?

**Đáp án:** OS environment là property source có ưu tiên cao hơn config data file trong chế độ thông thường. Đây có thể là **override**, không phải lỗi tìm file.

### Bài 7 — Thiết kế startup không lệ thuộc CWD

Một dịch vụ chạy ở nhiều môi trường: IDE, systemd, Docker, Kubernetes. Mục tiêu là giữ default trong JAR nhưng deployment có một bộ YAML riêng.

**Đáp án gợi ý:**

1. Đóng gói default không nhạy cảm trong `classpath:/application.yml`.
2. Thống nhất một path rõ ràng **bên trong môi trường chạy**, ví dụ `/etc/catalog/`.
3. Mount/copy file vào path đó với quyền đọc thích hợp.
4. Cấp `SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/` bằng runtime.
5. Cấp `SPRING_PROFILES_ACTIVE` nếu dùng profile.
6. Bắt buộc một deployment marker hoặc ràng buộc config thật sự cần cho production.
7. Kiểm tra startup log, property source priority và test chạy từ một working directory khác.

Cách này giúp cùng một JAR được triển khai có thể tái lập, không phụ thuộc thư mục tình cờ khi người vận hành gọi lệnh.

## 27. Checklist vận hành ngắn

Trước khi kết luận lỗi do Spring Boot:

- [ ] Xác định JAR nào thực sự được chạy và phiên bản Spring Boot.
- [ ] Xác định `user.dir`/working directory của đúng **process**.
- [ ] Xác định tệp tồn tại trong đúng filesystem, kể cả container/pod.
- [ ] Kiểm tra tên `application.yml`/`application-prod.yml` và profiles.
- [ ] Xác minh đã chọn đúng `location`, `additional-location` hoặc `import`.
- [ ] Với directory location, dùng dấu `/` cuối đường dẫn.
- [ ] Với file cần có, không vô tình thêm `optional:`.
- [ ] Phân biệt `file:./...`, `file:/...`, `classpath:...` và import-relative.
- [ ] Kiểm tra quyền đọc bằng đúng user/group của process.
- [ ] Xác minh thứ tự ưu tiên: CLI, JVM system properties, environment, config data.
- [ ] Bật TRACE có kiểm soát cho `org.springframework.boot.context.config` khi cần.
- [ ] Tránh log giá trị bí mật hoặc mở public các endpoint Actuator cấu hình.
- [ ] Kiểm tra việc restart/rollout sau thay đổi cấu hình.
- [ ] Đưa config-location contract vào scripts, Helm charts hoặc service units thay vì dựa vào thói quen `cd` thủ công.

## 28. Ghi nhớ

1. **Current working directory khác thư mục chứa JAR.** `java -jar /opt/app.jar` không tự chuyển working directory sang `/opt`.
2. **Default external locations gồm `file:./`, `file:./config/` và `file:./config/*/`**, đều giải quyết theo working directory.
3. **`classpath:/` không phải filesystem `./`**; tài nguyên trong JAR có cơ chế tìm riêng.
4. **`spring.config.location` thay thế default locations**, còn **`spring.config.additional-location` bổ sung** và cho phép external override defaults.
5. **`spring.config.name/location/additional-location` cần được cấp rất sớm**, ví dụ từ OS environment, JVM system property hoặc CLI.
6. **`optional:` chỉ thể hiện location có thể vắng**, không sửa lỗi parse, permissions hoặc validation.
7. **`spring.config.import` hỗ trợ import-relative** khi khai báo location không có prefix, khác với `file:./...`.
8. **Docker/Kubernetes có filesystem và working directory riêng**; host path không tự trở thành container path.
9. **systemd và Windows Service không nhất thiết kế thừa CWD của shell tương tác**; cấu hình working directory hoặc absolute location rõ ràng.
10. **Đọc sai value chưa chắc do không tìm được file**: có thể do profile, property-source precedence, thiếu restart hoặc một override cao hơn.
11. **Production cần contract fail-fast hợp lý** cho các nguồn bắt buộc, không đơn thuần thêm `optional:` để tránh exception.
12. **Tạo deployment tái lập:** vị trí config tuyệt đối, quyền đọc, profile, startup command và diagnostics phải được định nghĩa cùng nhau.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Config Data Files / Config Data Location: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files
- Spring Boot Reference — Importing Additional Data: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing
- Spring Boot Reference — Type-safe Configuration Properties and Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot How-to — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
