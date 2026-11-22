# Thay thế vị trí mặc định bằng `spring.config.location`

Trong Spring Boot, các tệp `application.properties` và `application.yml` thường được tự động tìm ở những vị trí quen thuộc trong classpath và thư mục làm việc. Khi cần triển khai cùng một bản ứng dụng cho nhiều môi trường, chúng ta có thể muốn **chỉ đọc cấu hình từ một thư mục hoặc một tệp được chỉ định** thay vì để ứng dụng dò toàn bộ vị trí mặc định. Thuộc tính `spring.config.location` giải quyết nhu cầu đó.

Điểm cần nắm: `spring.config.location` **thay thế tập vị trí tìm tệp cấu hình mặc định của Spring Boot** bằng tập vị trí được truyền lúc khởi động. Nó không vô hiệu hóa các nguồn cấu hình khác như biến môi trường, Java system properties hay tham số dòng lệnh. Đồng thời, nó khác với `spring.config.additional-location`, vốn giữ lại vị trí mặc định rồi bổ sung vị trí mới.

Bài học sử dụng ngữ cảnh Spring Boot 3.3.x và Java 21.

## 1. Spring Boot tìm cấu hình ở đâu khi không chỉ định vị trí?

Spring Boot hỗ trợ *externalized configuration*: cấu hình có thể nằm trong JAR, nằm ngoài JAR hoặc được truyền từ môi trường chạy. Với config data dạng `application.properties`, `application.yaml` và `application.yml`, Spring Boot mặc định xem xét các vị trí như:

| Vị trí mặc định | Ý nghĩa |
| --- | --- |
| `optional:classpath:/` | Gốc classpath, thường là `src/main/resources` khi phát triển |
| `optional:classpath:/config/` | Thư mục `config` trong classpath |
| `optional:file:./` | Thư mục làm việc hiện tại của tiến trình |
| `optional:file:./config/` | Thư mục `config` dưới thư mục làm việc |
| `optional:file:./config/*/` | Các thư mục con trực tiếp của `./config/` |

Các vị trí này tham gia vào cơ chế nạp config data, với quy tắc ưu tiên và ghi đè của Spring Boot. `optional:` nghĩa là vị trí có thể không tồn tại và việc thiếu vị trí đó được bỏ qua. Đừng hiểu bảng này như danh sách mọi `PropertySource` của Spring: đây chỉ là các đường dẫn tìm **tệp config data** mặc định.

Ví dụ dự án:

~~~text
catalog-service/
├── build/
│   └── libs/
│       └── catalog-service.jar
├── config/
│   └── application.yml
└── src/
    └── main/
        └── resources/
            └── application.yml
~~~

Khi chạy trong thư mục `catalog-service` và không truyền thay đổi về location, Spring Boot có thể xét cả cấu hình đóng gói trong JAR lẫn cấu hình ngoài JAR tại `./config/`. Bản cấu hình ngoài JAR có thể ghi đè các khóa từ bản được đóng gói theo thứ tự ưu tiên config data.

## 2. `spring.config.location` thay thế danh sách vị trí mặc định

Giả sử chúng ta muốn chạy ứng dụng với cấu hình nằm trong thư mục `deployment`:

~~~text
catalog-service/
├── catalog-service.jar
├── deployment/
│   └── application.yml
└── config/
    └── application.yml
~~~

Lệnh chạy:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Khi đó, cơ chế tìm **tệp config data thông thường** sử dụng vị trí `file:./deployment/` thay cho danh sách mặc định. Spring Boot tìm `application.properties`, `application.yml` hoặc `application.yaml` tương ứng trong thư mục này, cùng các biến thể theo profile khi thích hợp.

Một cách hình dung:

~~~text
KHÔNG truyền spring.config.location
  → tìm các vị trí mặc định trong classpath và file system

CÓ --spring.config.location=file:./deployment/
  → dùng vị trí được chỉ định: ./deployment/
  → không tự động tìm thêm các vị trí mặc định đã bị thay thế
~~~

Vì vậy, **không nên mặc định rằng `src/main/resources/application.yml` vẫn được nạp** khi `spring.config.location` trỏ hoàn toàn sang một thư mục khác. Các thiết lập trong file đóng gói có thể không còn hiệu lực nếu file đó không được đưa vào tập vị trí được nạp hoặc không được import qua cơ chế khác.

Cần phân biệt phạm vi: việc thay thế này áp dụng cho **vị trí tìm config data**, không phải toàn bộ cơ chế externalized configuration. Ví dụ, tham số CLI `--server.port=9090` vẫn có thể ghi đè `server.port` từ tệp được nạp.

## 3. Truyền location lúc khởi động

`spring.config.location` được dùng rất sớm, trước khi Spring Boot quyết định nạp những tệp nào. Vì vậy, hãy truyền qua nguồn có sẵn từ **thời điểm khởi động**, như command-line argument, Java system property hoặc biến môi trường.

### 3.1. Command-line argument

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Với tệp cụ thể:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/application-prod.yml
~~~

Với đường dẫn tuyệt đối trên Linux:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:/etc/catalog/application.yml
~~~

Dùng dấu nháy bao quanh toàn bộ argument nếu đường dẫn có khoảng trắng hoặc chứa ký tự có ý nghĩa với shell:

~~~bash
java -jar catalog-service.jar '--spring.config.location=file:./my config/'
~~~

### 3.2. Java system property

Chú ý đặt `-D...` **trước** `-jar`:

~~~bash
java -Dspring.config.location=file:./deployment/ -jar catalog-service.jar
~~~

Đây là JVM system property. Nếu đặt nhầm phía sau tên JAR mà không theo cú pháp tham số của ứng dụng, JVM sẽ không nhận nó như một system property.

### 3.3. Biến môi trường

Trên Linux/macOS:

~~~bash
export SPRING_CONFIG_LOCATION=file:./deployment/
java -jar catalog-service.jar
~~~

Trong Windows PowerShell:

~~~powershell
$env:SPRING_CONFIG_LOCATION = 'file:./deployment/'
java -jar catalog-service.jar
~~~

Spring Boot nhận dạng tên biến môi trường `SPRING_CONFIG_LOCATION` tương ứng với `spring.config.location`. Cách đặt này phù hợp với Docker, Kubernetes, script triển khai và hệ thống quản lý runtime configuration.

### 3.4. Không dựa vào `application.yml` để thay đổi location của chính nó

Ví dụ sau không phải cách đáng tin cậy để quyết định Spring Boot tìm file ban đầu ở đâu:

~~~yaml
# Không đặt logic xác định vị trí khởi động vào file đang chờ được tìm
spring:
  config:
    location: file:./deployment/
~~~

Spring Boot phải **biết vị trí cần tìm trước khi tải file**. Do đó, hãy truyền `spring.config.location` qua tham số dòng lệnh, system property hoặc biến môi trường từ bên ngoài quá trình nạp config data. Đây là điểm phân biệt quan trọng với các thuộc tính ứng dụng thông thường như `server.port`.

## 4. Đường dẫn thư mục khác đường dẫn tệp

Spring Boot phân biệt một **thư mục tìm kiếm** với một **tệp được nêu đích danh**.

### 4.1. Thư mục: phải kết thúc bằng dấu `/`

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Dấu `/` cuối đường dẫn báo rằng `deployment/` là thư mục. Spring Boot nối thêm các tên tệp cấu hình thích hợp dựa trên `spring.config.name`, mặc định là `application`, rồi xét biến thể theo profile khi cần.

Ví dụ:

~~~text
deployment/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Với `--spring.profiles.active=prod`, Spring Boot có thể nạp cấu hình chung `application.yml` và bản theo profile `application-prod.yml` từ thư mục đã khai báo. Giá trị ở file theo profile đang hoạt động có thể ghi đè giá trị chung của cùng khóa.

### 4.2. Tệp cụ thể: ghi đủ tên và phần mở rộng

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/application.yml
~~~

Khi truyền file cụ thể, Spring Boot lấy tên file đó làm vị trí cấu hình trực tiếp, thay vì dùng `spring.config.name` để dò các tên bất kỳ trong cùng thư mục. Với các tên được chỉ rõ, cơ chế config data cũng có thể xét biến thể theo profile tương ứng khi áp dụng.

Ví dụ để chỉ rõ một tệp cấu hình của nhà vận hành:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./ops/catalog.yml
~~~

Không được nhầm ý nghĩa của hai cách viết:

| Location | Diễn giải |
| --- | --- |
| `file:./ops/` | Thư mục chứa các tệp có tên cấu hình theo quy tắc Spring Boot |
| `file:./ops/application.yml` | Tệp YAML cụ thể |
| `file:/etc/catalog/` | Thư mục ngoài JAR ở đường dẫn tuyệt đối |
| `classpath:/config/` | Thư mục config trong classpath |
| `classpath:/config/application.yml` | Tệp YAML được đóng gói trong classpath |

`classpath:` chỉ tài nguyên trong classpath, thường đóng gói cùng ứng dụng. `file:` chỉ tài nguyên trong hệ thống tệp. Với cấu hình triển khai cần thay đổi độc lập với JAR, một đường dẫn `file:` bên ngoài JAR thường phù hợp.

### 4.3. Đường dẫn tương đối phụ thuộc thư mục làm việc

Trong `file:./deployment/`, dấu `./` được hiểu từ **working directory của tiến trình Java**, không tự động từ thư mục chứa JAR.

Giả sử JAR nằm tại `/opt/catalog/catalog-service.jar`. Hai lệnh sau có thể trỏ tới các vị trí khác nhau:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

~~~bash
cd /tmp
java -jar /opt/catalog/catalog-service.jar --spring.config.location=file:./deployment/
~~~

Lệnh đầu tìm trong `/opt/catalog/deployment/`; lệnh thứ hai tìm trong `/tmp/deployment/`. Trong script dịch vụ, container hay CI/CD, nên dùng đường dẫn rõ ràng và đặt working directory có chủ đích.

## 5. Vị trí không tồn tại và tiền tố `optional:`

Theo mặc định, nếu một location đã khai báo bắt buộc phải có nhưng không tồn tại, Spring Boot có thể dừng quá trình khởi động với lỗi dạng `ConfigDataLocationNotFoundException`.

Ví dụ:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./does-not-exist/
~~~

Nếu thư mục không tồn tại, ứng dụng sẽ gặp lỗi nạp config data. Điều này hữu ích khi một tệp cấu hình triển khai là bắt buộc và chạy thiếu nó phải được phát hiện sớm.

Khi muốn cho phép vị trí bị thiếu, đặt `optional:` ở đầu từng location:

~~~bash
java -jar catalog-service.jar --spring.config.location=optional:file:./deployment/
~~~

Nếu `./deployment/` không tồn tại, Spring Boot bỏ qua location này. **Bỏ qua location không đồng nghĩa với tự động khôi phục danh sách mặc định**. Vì `spring.config.location` vẫn thay thế danh sách mặc định, ứng dụng có thể không có cấu hình từ các file `application.yml` cũ nếu bạn không khai báo lại chúng.

Có thể kết hợp vị trí bắt buộc và tùy chọn:

~~~bash
java -jar catalog-service.jar '--spring.config.location=classpath:/base/,optional:file:./overrides/'
~~~

Trong ví dụ, `classpath:/base/` được yêu cầu tồn tại; `file:./overrides/` có thể vắng mặt. Những tệp trong hai vị trí được xét theo thứ tự ưu tiên của nhóm location.

**Khi nào dùng `optional:`?** Dùng nếu ứng dụng vẫn có đủ cấu hình hợp lệ khi vị trí đó vắng mặt. Nếu toàn bộ cấu hình vận hành bắt buộc phải có, nên để vị trí bắt buộc để quá trình khởi động báo lỗi ngay khi thiếu.

## 6. Nhiều vị trí, thứ tự và location group

`spring.config.location` cho phép chỉ định nhiều vị trí. Đối với nhóm vị trí xử lý tuần tự, các vị trí về sau có thể ghi đè thuộc tính trùng khóa từ các vị trí trước.

Ví dụ:

~~~bash
java -jar catalog-service.jar '--spring.config.location=optional:classpath:/defaults/,optional:file:./deployment/'
~~~

Giả sử:

~~~yaml
# classpath:/defaults/application.yml
app:
  display-name: "Danh mục mặc định"
  page-size: 20
~~~

~~~yaml
# file:./deployment/application.yml
app:
  display-name: "Danh mục production"
~~~

Khi cả hai tồn tại và được nạp, kết quả dự kiến:

~~~text
app.display-name = Danh mục production
app.page-size    = 20
~~~

`app.display-name` ở vị trí sau ghi đè giá trị cùng khóa ở vị trí trước; `app.page-size` vẫn có từ nguồn đầu tiên nếu nguồn sau không cung cấp nó.

Spring Boot còn phân biệt dấu phẩy `,` và dấu chấm phẩy `;` khi liệt kê location:

- **Dấu phẩy `,`** dùng để phân tách các location group được xử lý theo thứ tự.
- **Dấu chấm phẩy `;`** nhóm nhiều location thành các vị trí cùng mức, đặc biệt quan trọng khi xử lý cấu hình theo profile.

Ví dụ cú pháp:

~~~text
spring.config.location=classpath:/cfg/,classpath:/ext/
spring.config.location=classpath:/cfg/;classpath:/ext/
~~~

Cả hai đều liệt kê hai thư mục, nhưng cách tổ chức group có thể làm **thứ tự áp dụng file theo profile** khác nhau. Khi có `application-dev.yml`, `application-prod.yml` trong nhiều thư mục và nhiều profile hoạt động cùng lúc, hãy lựa chọn dấu phân cách có chủ đích thay vì xem chúng tương đương.

Nếu chỉ cần một thư mục duy nhất, không cần quan tâm đến location group. Khi nhiều nhóm ghi đè lẫn nhau, hãy ghi nhận rõ thứ tự và giá trị mong đợi của cùng khóa.

## 7. Profile-specific configuration tại vị trí mới

Giả sử:

~~~text
deployment/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Nội dung `deployment/application.yml`:

~~~yaml
app:
  endpoint: https://api.example.org
  retry-count: 3
~~~

Nội dung `deployment/application-dev.yml`:

~~~yaml
app:
  endpoint: http://localhost:8080
~~~

Nội dung `deployment/application-prod.yml`:

~~~yaml
app:
  retry-count: 5
~~~

Chạy cho môi trường dev:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=dev
~~~

Kết quả hiệu lực đối với các khóa trong ví dụ:

~~~text
app.endpoint    = http://localhost:8080
app.retry-count = 3
~~~

Chạy cho môi trường prod:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=prod
~~~

Kết quả:

~~~text
app.endpoint    = https://api.example.org
app.retry-count = 5
~~~

Cấu hình dùng chung từ `application.yml` được kết hợp với cấu hình theo profile của thư mục mới, và thuộc tính trùng tên được xử lý theo thứ tự ưu tiên config data. Nhiều profile, nhiều location group hoặc import có thể làm thứ tự thực tế phức tạp hơn, nhưng nguyên tắc khai báo location sớm vẫn giữ nguyên.

## 8. So sánh `spring.config.location`, `spring.config.additional-location` và `spring.config.import`

Ba cơ chế đều liên quan việc nạp thêm tệp, nhưng giải quyết nhu cầu khác nhau.

| Cơ chế | Phạm vi | Cách dùng |
| --- | --- | --- |
| `spring.config.location` | **Thay** vị trí tìm config data mặc định | Khi muốn kiểm soát rõ ứng dụng chỉ tìm ở các vị trí chỉ định |
| `spring.config.additional-location` | **Bổ sung** location bên cạnh vị trí mặc định | Khi muốn giữ `application.yml` đóng gói trong JAR và thêm cấu hình bên ngoài |
| `spring.config.import` | **Import** tài nguyên cấu hình khác từ một document đã được nạp | Khi một file cấu hình tham chiếu thêm file hoặc nguồn cần thiết |

### 8.1. Chỉ định lại toàn bộ location

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Nếu trước đó ứng dụng phụ thuộc vào giá trị `spring.application.name` chỉ tồn tại trong `classpath:/application.yml`, giá trị ấy có thể mất đi, vì vị trí classpath mặc định đã bị thay thế.

### 8.2. Giữ mặc định và bổ sung overrides

~~~bash
java -jar catalog-service.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Trong trường hợp này, Spring Boot vẫn có thể nạp các cấu hình tại location mặc định rồi dùng các giá trị trong thư mục `deployment` để ghi đè các khóa tương ứng.

Đây là lựa chọn thường phù hợp khi tổ chức cấu hình theo mô hình:

~~~text
application.yml nằm trong JAR  → mặc định chung
./deployment/application.yml   → giá trị riêng môi trường
~~~

Chỉ dùng `spring.config.location` khi việc **thay thế** là chủ đích.

### 8.3. Import cấu hình từ file đã được nạp

Ví dụ trong một file `application.yml` đang được Spring Boot tải:

~~~yaml
spring:
  config:
    import: optional:file:./secrets/feature.yml
~~~

Cơ chế này khiến Spring Boot xem xét tài nguyên được import; nó không có cùng ý nghĩa với việc thay thế toàn bộ đường dẫn tìm kiếm lúc khởi động. Điều kiện tiên quyết là document chứa `spring.config.import` phải được tải qua một location đã có hiệu lực. Nếu `spring.config.location` khiến document đó không được nạp, chỉ thị import trong đó cũng không được áp dụng.

## 9. Kết hợp `spring.config.location` và `spring.config.name`

Mặc định Spring Boot dùng tên cơ sở `application` để tìm `application.yml`, `application.yaml` hoặc `application.properties`. Có thể thay tên cơ sở qua `spring.config.name`, cũng phải được cung cấp từ thời điểm khởi động.

Giả sử:

~~~text
settings/
├── catalog.yml
└── catalog-prod.yml
~~~

Chạy:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./settings/ --spring.config.name=catalog --spring.profiles.active=prod
~~~

Bây giờ Spring Boot tìm các tệp có tên cơ sở `catalog` trong thư mục `settings/` thay vì chỉ mặc định dùng tên `application`. Tệp theo profile `catalog-prod.yml` tham gia khi profile `prod` được kích hoạt.

Cách này hữu ích khi nhiều ứng dụng chia sẻ một thư mục cấu hình nhưng có tên file riêng:

~~~text
shared-config/
├── catalog.yml
├── catalog-prod.yml
├── billing.yml
└── billing-prod.yml
~~~

Tuy nhiên, nếu chỉ cần một tệp cụ thể, truyền thẳng đường dẫn file cho `spring.config.location` thường đơn giản hơn.

## 10. Ví dụ Spring Boot hoàn chỉnh

### 10.1. Mã Java đọc giá trị cuối cùng

Ứng dụng dùng `spring-boot-starter`; nếu cần HTTP server thì thêm `spring-boot-starter-web`.

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(Environment environment) {
        return args -> {
            System.out.println("app.mode = "
                    + environment.getProperty("app.mode", "<missing>"));
            System.out.println("app.endpoint = "
                    + environment.getProperty("app.endpoint", "<missing>"));
            System.out.println("spring.application.name = "
                    + environment.getProperty("spring.application.name", "<missing>"));
        };
    }
}
~~~

`Environment` trả về giá trị hiệu lực theo thứ tự ưu tiên của các nguồn cấu hình; việc in này giúp quan sát sự khác nhau giữa location mới và location mặc định.

### 10.2. Cấu hình đóng gói trong JAR

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog-service
app:
  mode: packaged
  endpoint: https://packaged.example.org
~~~

### 10.3. Cấu hình bên ngoài

Tạo `deployment/application.yml` tại working directory:

~~~yaml
app:
  mode: external
  endpoint: https://external.example.org
~~~

Chạy với location thay thế:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Kết quả ví dụ:

~~~text
app.mode = external
app.endpoint = https://external.example.org
spring.application.name = <missing>
~~~

Vì `spring.application.name` chỉ được khai báo ở cấu hình đóng gói, nên khi location mặc định bị thay thế hoàn toàn, ví dụ không còn nạp giá trị đó. Đây là minh họa trực tiếp cho tác động của `spring.config.location`.

Thử lại bằng:

~~~bash
java -jar catalog-service.jar --spring.config.additional-location=file:./deployment/
~~~

Kết quả mong đợi:

~~~text
app.mode = external
app.endpoint = https://external.example.org
spring.application.name = catalog-service
~~~

Với `additional-location`, cấu hình mặc định được giữ lại để cung cấp khóa không có trong tệp bên ngoài.

**Lưu ý thực hành:** Trong Gradle/Maven hoặc môi trường IDE, thư mục làm việc có thể khác thư mục đặt JAR. Hãy đặt `deployment/` đúng tại working directory hoặc chuyển thành đường dẫn tuyệt đối.

## 11. Các tình huống lỗi thường gặp

### 11.1. Quên dấu `/` ở cuối đường dẫn thư mục

~~~bash
# Muốn chỉ thư mục
java -jar catalog-service.jar --spring.config.location=file:./deployment/
~~~

Cú pháp nêu thư mục cần dấu `/` cuối. Nếu viết `file:./deployment`, đừng giả định Spring Boot vẫn coi đó là một directory location và nối thêm `application.yml`. Hãy ghi rõ slash, hoặc ghi đủ tên file.

### 11.2. Đường dẫn tương đối phụ thuộc working directory

~~~bash
java -jar /opt/catalog/catalog-service.jar --spring.config.location=file:./deployment/
~~~

Kiểm tra tiến trình đang chạy trong thư mục nào, nhất là khi gọi từ systemd, cron, Docker hay IDE. Cách khắc phục ổn định thường là dùng `file:/đường/dẫn/tuyệt/đối/`.

### 11.3. Cấu hình mặc định trong JAR biến mất

Khi dùng `spring.config.location`, đừng dựa vào `classpath:/application.yml` nếu không đưa nó vào danh sách location hoặc import từ một document đã được nạp. Nếu mục tiêu của bạn là giữ giá trị mặc định trong JAR, hãy cân nhắc `spring.config.additional-location`.

### 11.4. Thư mục tùy chọn không tồn tại

~~~bash
java -jar catalog-service.jar --spring.config.location=optional:file:./deployment/
~~~

Ứng dụng có thể không báo lỗi *missing location* nhưng vẫn thiếu các thuộc tính bắt buộc cho bean hoặc nghiệp vụ. `optional:` chỉ thay đổi cách xử lý location vắng mặt, không bảo đảm cấu hình ứng dụng đã đầy đủ.

### 11.5. Đã nạp đúng file nhưng giá trị không như mong đợi

Một tệp chứa `server.port: 8081` có thể đã được nạp, nhưng tham số CLI `--server.port=9090` vẫn ghi đè giá trị đó.

Hãy phân biệt:

1. **Tệp nào được nạp?** Phụ thuộc `spring.config.location`, `spring.config.name`, profile, import và đường dẫn.
2. **Giá trị nào có hiệu lực?** Phụ thuộc thứ tự ưu tiên giữa tất cả `PropertySource`, gồm cả biến môi trường và tham số dòng lệnh.

Đây là hai bước chẩn đoán khác nhau; chỉ nhìn nội dung file được nạp chưa đủ.

### 11.6. Khai báo nhiều đường dẫn nhưng giả định ưu tiên sai

Khi nhiều thư mục chứa cùng `application.yml`, các location group và biến thể theo profile có thể thay đổi thứ tự ghi đè. Bắt đầu bằng một location hoặc một nhóm đơn giản, sau đó thêm từng nguồn theo chủ đích. Nếu dùng dấu `;` trong shell, bao toàn bộ đối số bằng dấu nháy để shell không diễn giải nó thành dấu phân tách lệnh.

## 12. Quan sát việc nạp cấu hình

Khi muốn biết Spring Boot đã tìm những file nào, có thể tăng mức log cho cơ chế config data:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --logging.level.org.springframework.boot.context.config=TRACE
~~~

Log trace có thể cho biết quá trình tìm kiếm và nạp config data, nhưng nội dung log cụ thể thay đổi theo phiên bản. Không phụ thuộc vào một thông báo log cố định trong mã nghiệp vụ.

Nếu muốn quan sát giá trị sau cùng, dùng `Environment` trong bean như ví dụ phía trên. Khi hệ thống đã sử dụng Spring Boot Actuator, endpoint `env` và `configprops` có thể giúp chẩn đoán, nhưng phải được cấu hình truy cập phù hợp để tránh lộ thông tin nhạy cảm.

Trường hợp một location bắt buộc không tồn tại, thông báo lỗi khởi động thường là dấu hiệu rõ nhất. Kiểm tra tên tệp, phần mở rộng, working directory, quyền đọc và dấu `/` cuối location thư mục.

## 13. Bài tập thực hành

**Bài 1 — Phân biệt thay thế và bổ sung.** Trong JAR có:

~~~yaml
app:
  color: blue
  page-size: 10
~~~

Trong `deployment/application.yml` có:

~~~yaml
app:
  color: green
~~~

Dự đoán `app.color` và `app.page-size` khi chạy lần lượt với:

~~~text
--spring.config.location=file:./deployment/
--spring.config.additional-location=file:./deployment/
~~~

Đáp án: với `location`, `color=green` và `page-size` không còn giá trị từ tệp đóng gói; với `additional-location`, `color=green` và `page-size=10`. Giả định không có nguồn nào khác cung cấp hoặc ghi đè các khóa này.

**Bài 2 — Nhận biết location bắt buộc.** Điều gì xảy ra nếu `./settings/` không tồn tại với hai cách?

~~~text
--spring.config.location=file:./settings/
--spring.config.location=optional:file:./settings/
~~~

Đáp án: cách thứ nhất có thể dừng khởi động vì không tìm thấy location; cách thứ hai bỏ qua location bị thiếu. Cả hai vẫn là cơ chế **thay thế** vị trí mặc định.

**Bài 3 — Kích hoạt profile ở thư mục ngoài JAR.** Tạo:

~~~text
deployment/application.yml
deployment/application-prod.yml
~~~

Trong file chung đặt `app.timeout: 5s`; trong file prod đặt `app.timeout: 15s`. Chạy:

~~~bash
java -jar catalog-service.jar --spring.config.location=file:./deployment/ --spring.profiles.active=prod
~~~

Đọc thuộc tính `app.timeout` bằng `Environment` hoặc bind `Duration` với `@ConfigurationProperties`. Kết quả mong đợi là `15s`.

**Bài 4 — Cấu hình theo biến môi trường.** Thiết lập `SPRING_CONFIG_LOCATION=file:./deployment/` và chạy JAR không truyền `--spring.config.location`. Quan sát giá trị hiệu lực, rồi kiểm tra lại khi bỏ biến môi trường.

**Bài 5 — Thay tên mặc định.** Tạo `settings/catalog.yml`, chạy với `--spring.config.location=file:./settings/ --spring.config.name=catalog`. Kiểm tra rằng cấu hình được đọc từ tên file `catalog.yml`.

## 14. Tổng kết

`spring.config.location` là cơ chế quyết định **tập vị trí config data được tìm khi Spring Boot khởi động**. Khi khai báo thuộc tính này, các location mặc định bị thay thế. Nếu location trỏ đến thư mục, hãy kết thúc bằng dấu `/` và nhớ rằng đường dẫn `file:./...` phụ thuộc working directory. Dùng `optional:` khi việc thiếu location là chấp nhận được; dùng profile khi có nhiều biến thể cấu hình môi trường.

Nếu muốn giữ các tệp cấu hình mặc định và chỉ thêm nguồn ngoài JAR, hãy dùng `spring.config.additional-location`. Khi chẩn đoán một giá trị bất ngờ, cần kiểm tra cả **tệp đã nạp** lẫn **thứ tự ưu tiên nguồn thuộc tính**.

## Tài liệu tham khảo

- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Working With Multi-Document Files and Profile-specific Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
