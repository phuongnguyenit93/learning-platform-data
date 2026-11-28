# Thử nhiều profile và label rồi giải thích giá trị được chọn

Trong Spring Cloud Config, cùng một ứng dụng có thể nhận các giá trị khác nhau tùy profile và label mà client yêu cầu. Profile chọn nhóm cấu hình theo môi trường hoặc chức năng; label chọn phiên bản của repository, thường là branch, tag hoặc commit Git. Khi nhiều file cùng khai báo một property, thứ tự ưu tiên của các PropertySource quyết định giá trị cuối cùng.

Bài thực hành này dựng một Git config repository cho ứng dụng `orders-service`, tạo hai label `main` và `release-v1`, sau đó gọi Config Server với các tổ hợp profile `dev`, `mysql`, `dev,mysql` và `mysql,dev`. Bạn sẽ đọc response, xác định PropertySource thắng, so sánh giá trị giữa các label và xác minh client đang dùng đúng cấu hình.

Mục tiêu không chỉ là làm cho request trả HTTP 200. Sau mỗi lần gọi, bạn cần giải thích được: client đã yêu cầu application/profile/label nào, Config Server đã đọc revision nào, property source nào có độ ưu tiên cao nhất và vì sao giá trị cuối cùng được chọn.

Sau bài thực hành, bạn có thể:

- Tạo repository cấu hình Git với file dùng chung, file theo application và file theo profile.
- Tạo và phân biệt branch, tag làm label cho Config Server.
- Gọi Environment endpoint với một profile, nhiều profile và nhiều label khác nhau.
- Đọc `name`, `profiles`, `label`, `version` và `propertySources` trong response.
- Giải thích quy tắc profile cuối cùng có độ ưu tiên cao hơn khi có nhiều active profile.
- Giải thích vì sao file riêng cho application có thể ghi đè file dùng chung.
- Xác minh giá trị được bind trong Config Client.
- Phân biệt thay đổi nội dung trên cùng label với thay đổi label client đang yêu cầu.
- Ghi lại bằng chứng để người khác có thể tái lập kết quả.

## 1. Bài toán và kiến trúc lab

Một nhóm phát triển có ứng dụng `orders-service`. Ứng dụng chạy với cấu hình dùng chung, cấu hình theo profile và cấu hình riêng của ứng dụng. Nhóm duy trì hai phiên bản cấu hình:

- `main`: cấu hình đang phát triển.
- `release-v1`: cấu hình đã được chốt cho một bản phát hành.

Ứng dụng cần lấy cấu hình từ Config Server. Ta sẽ kiểm tra cùng một property `demo.timeout` qua nhiều profile và label để quan sát precedence.

~~~mermaid
flowchart LR
    G["Git config repository<br/>main / release-v1 / tag"] --> S["Spring Cloud Config Server"]
    C["orders-service<br/>profile + label"] -->|"GET /orders-service/{profile}/{label}"| S
    S --> E["Environment<br/>PropertySources + version"]
    E --> C
    C --> B["ConfigurationProperties bean"]
    B --> R["Runtime endpoint / actuator"]
~~~

Các thành phần:

| Thành phần | Vai trò trong lab |
|---|---|
| Git config repository | Lưu `application*.yml` và `orders-service*.yml` |
| Branch `main` | Cấu hình đang phát triển |
| Branch `release-v1` | Một nhánh có giá trị khác để so sánh |
| Tag `config-v1.0` | Mốc cấu hình bất biến cho release |
| Config Server | Đọc Git và cung cấp Environment endpoint |
| Config Client | Yêu cầu cấu hình theo application/profile/label |
| `DemoProperties` | Nhận giá trị đã bind để xác minh runtime |

Bạn có thể dùng Config Server và Config Client hiện có trong môi trường thực hành. Các ví dụ dưới đây dùng Config Server tại `http://localhost:8888`.

## 2. Chuẩn bị Git config repository

Tạo thư mục repository riêng, ví dụ `C:/lab/config-repo` trên Windows hoặc `/work/config-repo` trên Linux/macOS.

Cấu trúc file:

~~~text
config-repo/
├── application.yml
├── application-dev.yml
├── application-mysql.yml
├── orders-service.yml
├── orders-service-dev.yml
└── orders-service-mysql.yml
~~~

Ý nghĩa:

- `application.yml`: cấu hình dùng chung cho mọi ứng dụng và profile.
- `application-dev.yml`: cấu hình dùng chung cho profile `dev`.
- `application-mysql.yml`: cấu hình dùng chung cho profile `mysql`.
- `orders-service.yml`: cấu hình riêng cho `orders-service`.
- `orders-service-dev.yml`: cấu hình riêng cho `orders-service` khi có profile `dev`.
- `orders-service-mysql.yml`: cấu hình riêng cho `orders-service` khi có profile `mysql`.

Tạo từng file với nội dung sau.

**application.yml**

~~~yaml
demo:
  message: shared-main
  timeout: 5s
  source: application.yml
  release: main
  datasource:
    platform: generic
~~~

**application-dev.yml**

~~~yaml
demo:
  message: shared-dev
  timeout: 2s
  source: application-dev.yml
  profile-marker: dev
~~~

**application-mysql.yml**

~~~yaml
demo:
  message: shared-mysql
  timeout: 1500ms
  source: application-mysql.yml
  datasource:
    platform: mysql
~~~

**orders-service.yml**

~~~yaml
demo:
  message: orders-main
  timeout: 4s
  source: orders-service.yml
  service-name: orders-service
~~~

**orders-service-dev.yml**

~~~yaml
demo:
  message: orders-dev
  timeout: 800ms
  source: orders-service-dev.yml
  profile-marker: orders-dev
~~~

**orders-service-mysql.yml**

~~~yaml
demo:
  message: orders-mysql
  timeout: 1200ms
  source: orders-service-mysql.yml
  datasource:
    url: jdbc:mysql://mysql.internal:3306/orders
~~~

Các giá trị `message`, `timeout` và `source` được cố ý khai báo trùng giữa nhiều file. Chúng giúp ta nhìn thấy file nào thắng. Những thuộc tính chỉ xuất hiện ở một nguồn như `demo.service-name` hoặc `demo.datasource.url` cho thấy property source có thể bổ sung key mà không ghi đè toàn bộ cấu trúc cấu hình.

## 3. Tạo hai label có nội dung khác nhau

Khởi tạo branch `main`, commit bộ cấu hình ban đầu:

~~~powershell
Set-Location C:/lab/config-repo
git init -b main
git add .
git commit -m "Add baseline orders configuration"
~~~

Nếu Git phiên bản cũ chưa hỗ trợ `git init -b`, chạy `git init`, sau đó đổi tên branch hiện tại thành `main`.

Tạo branch `release-v1` từ snapshot hiện tại:

~~~powershell
git switch -c release-v1
~~~

Trên branch `release-v1`, thay đổi các giá trị để có thể nhận ra label này trong response.

Trong **application.yml**:

~~~yaml
demo:
  message: shared-release-v1
  timeout: 6s
  source: application.yml
  release: release-v1
  datasource:
    platform: generic
~~~

Trong **orders-service.yml**:

~~~yaml
demo:
  message: orders-release-v1
  timeout: 5s
  source: orders-service.yml
  service-name: orders-service
~~~

Trong **orders-service-dev.yml**:

~~~yaml
demo:
  message: orders-dev-release-v1
  timeout: 900ms
  source: orders-service-dev.yml
  profile-marker: orders-dev-release-v1
~~~

Trong **orders-service-mysql.yml**:

~~~yaml
demo:
  message: orders-mysql-release-v1
  timeout: 1300ms
  source: orders-service-mysql.yml
  datasource:
    url: jdbc:mysql://mysql.internal:3306/orders
~~~

Các file `application-dev.yml` và `application-mysql.yml` giữ nguyên so với `main`. Điều này giúp phân biệt giá trị lấy từ file theo application/profile với giá trị kế thừa từ file dùng chung.

Commit branch release và tạo tag:

~~~powershell
git add .
git commit -m "Prepare release v1 configuration"
git tag config-v1.0
~~~

Quay lại `main`:

~~~powershell
git switch main
~~~

Kiểm tra branch, tag và commit:

~~~powershell
git branch --list
git tag --list
git log --oneline --decorate -5
~~~

Kết quả mong đợi có branch `main`, branch `release-v1` và tag `config-v1.0`. Branch `release-v1` và tag `config-v1.0` cùng trỏ tới commit release vừa tạo. Tag là mốc thuận tiện để tái lập cấu hình; branch có thể tiếp tục thay đổi khi có commit mới.

Nếu đang dùng repository từ xa, push cả branch và tag:

~~~powershell
git push origin main
git push origin release-v1
git push origin config-v1.0
~~~

## 4. Cấu hình Config Server đọc repository

Config Server cần Git URI trỏ tới repository lab và default label được đặt rõ ràng là `main`.

Đảm bảo hai ứng dụng dùng Spring Cloud BOM tương thích với phiên bản Spring Boot. Config Server cần dependency `spring-cloud-config-server`; Config Client cần `spring-cloud-starter-config`. Ứng dụng client trong ví dụ còn dùng `spring-boot-starter-web` cho endpoint `/config-view` và `spring-boot-starter-actuator` để kiểm tra Environment/refresh. Để tránh lệch phiên bản thư viện, không tự gán version riêng cho từng starter khi đã quản lý bằng BOM.

Ví dụ **application.yml** của Config Server:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: file:///C:/lab/config-repo
          default-label: main
          clone-on-start: true
~~~

Đổi `uri` thành đường dẫn repository thực tế của bạn. Nếu dùng Git server từ xa, thay bằng HTTPS hoặc SSH URI và cấu hình credential qua secret/environment theo chính sách của môi trường.

Ứng dụng Config Server phải bật server:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ConfigServerApplication.class,
            args
        );
    }
}
~~~

Khởi động Config Server và kiểm tra log clone repository. Khi server sẵn sàng, gọi thử:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
~~~

Response cần có `name` là `orders-service`, profile chứa `dev`, label là `main` và các property source từ repository. Nếu request không tìm thấy dữ liệu, kiểm tra Git URI, quyền đọc repository, branch label và tên file trước khi tiếp tục.

## 5. Đọc Environment response trước khi chạy client

Gọi lần lượt các URL sau:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/mysql/main"
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev,mysql/main"
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/mysql,dev/main"
~~~

Một response Environment thường có các trường:

| Trường | Cần quan sát |
|---|---|
| `name` | Application mà server đã resolve |
| `profiles` | Các profile được áp dụng |
| `label` | Label được yêu cầu/resolve |
| `version` | Revision Git nếu backend cung cấp |
| `propertySources` | Danh sách nguồn theo thứ tự ưu tiên |

Mở rộng response và tìm `demo.message`, `demo.timeout`, `demo.source`. Không chỉ đọc giá trị cuối cùng: hãy xem thuộc tính đó xuất hiện trong những PropertySource nào và nguồn nào đứng trước.

Trong Environment response, PropertySource đứng trước có độ ưu tiên cao hơn nguồn đứng sau. Với repository mặc định, các file cụ thể cho application và profile được đưa lên trước các file dùng chung. Khi có nhiều active profile, profile đứng cuối có độ ưu tiên cao hơn profile đứng trước.

## 6. Thử từng profile trên label main

Gọi profile `dev`:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
~~~

Giá trị mong đợi:

| Property | Giá trị được chọn | Nguồn |
|---|---|---|
| `demo.message` | `orders-dev` | `orders-service-dev.yml` |
| `demo.timeout` | `800ms` | `orders-service-dev.yml` |
| `demo.source` | `orders-service-dev.yml` | `orders-service-dev.yml` |
| `demo.release` | `main` | `application.yml` |
| `demo.datasource.platform` | `generic` | `application.yml` |

Giải thích: `orders-service-dev.yml` vừa khớp application vừa khớp profile, nên có ưu tiên cao hơn `application-dev.yml`, `orders-service.yml` và `application.yml`. Thuộc tính không được khai báo ở nguồn ưu tiên cao hơn có thể được kế thừa từ nguồn thấp hơn.

Gọi profile `mysql`:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/mysql/main"
~~~

Giá trị mong đợi:

| Property | Giá trị được chọn | Nguồn |
|---|---|---|
| `demo.message` | `orders-mysql` | `orders-service-mysql.yml` |
| `demo.timeout` | `1200ms` | `orders-service-mysql.yml` |
| `demo.source` | `orders-service-mysql.yml` | `orders-service-mysql.yml` |
| `demo.datasource.platform` | `mysql` | `application-mysql.yml` |
| `demo.datasource.url` | `jdbc:mysql://mysql.internal:3306/orders` | `orders-service-mysql.yml` |

`demo.datasource.platform` không có trong file riêng `orders-service-mysql.yml`, vì vậy giá trị từ `application-mysql.yml` vẫn có thể được dùng. `demo.datasource.url` chỉ có trong file riêng của ứng dụng, nên được bổ sung từ nguồn đó.

## 7. Thử nhiều profile và đảo thứ tự profile

Đây là phần quan trọng của bài lab. Gọi với `dev,mysql`:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev,mysql/main"
~~~

Với quy tắc profile của Spring Boot, profile cuối trong danh sách có độ ưu tiên cao hơn. Do đó `mysql` thắng `dev` đối với các key trùng nhau.

Thứ tự PropertySource mong đợi từ cao xuống thấp trong repository mặc định là:

1. `orders-service-mysql.yml`
2. `application-mysql.yml`
3. `orders-service-dev.yml`
4. `application-dev.yml`
5. `orders-service.yml`
6. `application.yml`

Các giá trị được chọn:

| Property | Giá trị | Nguồn thắng |
|---|---|---|
| `demo.message` | `orders-mysql` | `orders-service-mysql.yml` |
| `demo.timeout` | `1200ms` | `orders-service-mysql.yml` |
| `demo.datasource.platform` | `mysql` | `application-mysql.yml` |
| `demo.profile-marker` | `orders-dev` | `orders-service-dev.yml` |
| `demo.release` | `main` | `application.yml` |

Chú ý `demo.profile-marker` chỉ được khai báo ở các file profile tương ứng. Vì `orders-service-dev.yml` vẫn nằm trong danh sách property source, thuộc tính đó có thể tồn tại dù `mysql` là profile có ưu tiên cao hơn đối với những key trùng nhau.

Bây giờ đảo thứ tự profile:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/mysql,dev/main"
~~~

Thứ tự ưu tiên mong đợi:

1. `orders-service-dev.yml`
2. `application-dev.yml`
3. `orders-service-mysql.yml`
4. `application-mysql.yml`
5. `orders-service.yml`
6. `application.yml`

Các key trùng nhau nay lấy từ file profile `dev` của `orders-service`:

| Property | Giá trị | Nguồn thắng |
|---|---|---|
| `demo.message` | `orders-dev` | `orders-service-dev.yml` |
| `demo.timeout` | `800ms` | `orders-service-dev.yml` |
| `demo.datasource.platform` | `mysql` | `application-mysql.yml` |
| `demo.profile-marker` | `orders-dev` | `orders-service-dev.yml` |
| `demo.release` | `main` | `application.yml` |

Tại sao `demo.datasource.platform` vẫn là `mysql`? Vì file `application-dev.yml` không khai báo key này. Nguồn `application-mysql.yml` vẫn bổ sung giá trị dù `dev` là profile ưu tiên cao nhất. Precedence quyết định giá trị của từng key, không loại bỏ toàn bộ PropertySource thấp hơn.

Nếu response của phiên bản đang dùng có thứ tự khác với bảng, hãy dùng `propertySources` thực tế làm bằng chứng và kiểm tra version/release train, repository implementation và cấu hình search locations. Không kết luận từ tên file nếu chưa kiểm tra response.

## 8. So sánh label main và release-v1

Gọi cùng profile `dev` với label `main`:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
~~~

Sau đó gọi label `release-v1`:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/release-v1"
~~~

So sánh:

| Property | `dev/main` | `dev/release-v1` |
|---|---|---|
| `demo.message` | `orders-dev` | `orders-dev-release-v1` |
| `demo.timeout` | `800ms` | `900ms` |
| `demo.source` | `orders-service-dev.yml` | `orders-service-dev.yml` |
| `demo.release` | `main` | `release-v1` |

Tên PropertySource có thể giống nhau vì hai label chứa cùng tên file. Giá trị và `version` mới cho biết server đã đọc nội dung từ revision nào. Kiểm tra trường `label` và `version` trong response để xác minh.

Gọi thêm tag:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/config-v1.0"
~~~

Vì tag `config-v1.0` trỏ tới commit của `release-v1` tại thời điểm tạo tag, kết quả cấu hình phải giống nội dung release đó. Nếu branch `release-v1` được commit thêm sau khi tạo tag, branch có thể thay đổi nhưng tag vẫn trỏ tới commit cũ.

### Label có vai trò gì?

- Branch phù hợp cho cấu hình đang được phát triển và có thể thay đổi theo commit.
- Tag phù hợp cho mốc cấu hình được phát hành và cần tái lập.
- Commit ID xác định một revision cụ thể, hữu ích khi cần điều tra hoặc rollback chính xác.
- Default label được Config Server sử dụng khi request không nêu label, theo cấu hình server.

Trong lab, default label được đặt là `main`, nên request `/orders-service/dev` tương đương việc yêu cầu cấu hình trên default label đó. Hãy kiểm tra `default-label` của Config Server nếu kết quả không như mong đợi.

## 9. Thử label mặc định và label không tồn tại

Gọi không truyền label:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev"
~~~

Nếu Config Server đặt `default-label: main`, kết quả phải tương ứng với `/orders-service/dev/main`.

Thử một label không tồn tại:

~~~powershell
curl.exe --include "http://localhost:8888/orders-service/dev/no-such-label"
~~~

Quan sát HTTP status và body lỗi. Không nên tự động cho rằng server sẽ quay về `main`. Hành vi lỗi phụ thuộc backend, server version và cách cấu hình xử lý label; mục tiêu của bài là nhận ra request không đọc được revision mong muốn và điều tra rõ nguyên nhân.

Không dùng label không tồn tại như một cách fallback trong production nếu chưa thiết kế rõ. Fallback ngầm có thể khiến client khởi động với cấu hình của một release khác.

## 10. Nối Config Client vào Config Server

Trong ứng dụng `orders-service`, khai báo tên ứng dụng, profile, label và Config Server URI.

Ví dụ **application.yml** của client:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: dev,mysql
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: main

management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
  endpoint:
    env:
      show-values: when-authorized
    configprops:
      show-values: when-authorized
~~~

`spring.config.import` là cơ chế Config Data của Spring Boot. Trong lab, import không có tiền tố `optional:` để ứng dụng báo lỗi startup nếu không lấy được remote config bắt buộc. Nếu mục tiêu là thử chế độ degraded, có thể đổi thành `optional:configserver:...` nhưng phải chuẩn bị local default và hiểu rằng ứng dụng có thể chạy mà không nhận được remote properties.

`spring.cloud.config.label` chọn label mà client gửi tới server. Để thử label khác, đổi thành `release-v1` hoặc `config-v1.0`, sau đó restart client để bảo đảm request bootstrap dùng label mới.

### Bind cấu hình vào bean

Ví dụ dùng `@ConfigurationProperties`:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoProperties {

    private String message;
    private Duration timeout;
    private String source;
    private String release;

    // Bổ sung getter và setter cho các field.
}
~~~

Đăng ký scan:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            OrdersServiceApplication.class,
            args
        );
    }
}
~~~

Tạo một endpoint chỉ hiển thị các thuộc tính không nhạy cảm của lab:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigViewController {

    private final DemoProperties properties;

    public ConfigViewController(DemoProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/config-view")
    public Map<String, Object> view() {
        return Map.of(
            "message", properties.getMessage(),
            "timeout", properties.getTimeout().toString(),
            "source", properties.getSource(),
            "release", properties.getRelease()
        );
    }
}
~~~

Gọi endpoint:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8080/config-view"
~~~

Giá trị trả về phải khớp với kết quả dự đoán từ Environment endpoint của Config Server cho application/profile/label tương ứng. Nếu khác, kiểm tra thêm property source local, biến môi trường, system property và trạng thái refresh của client.

Lưu ý: `Duration.toString()` thường hiển thị dạng ISO-8601, ví dụ `PT0.8S` thay cho chuỗi cấu hình `800ms`. So sánh thời lượng tương đương hoặc định dạng lại trước khi đối chiếu văn bản.

## 11. Ma trận thử nghiệm tổng hợp

Chạy các request và ghi kết quả thực tế vào bảng:

| Application | Profile | Label | `demo.message` dự kiến | `demo.timeout` dự kiến |
|---|---|---|---|---|
| orders-service | `dev` | `main` | orders-dev | 800ms |
| orders-service | `mysql` | `main` | orders-mysql | 1200ms |
| orders-service | `dev,mysql` | `main` | orders-mysql | 1200ms |
| orders-service | `mysql,dev` | `main` | orders-dev | 800ms |
| orders-service | `dev` | `release-v1` | orders-dev-release-v1 | 900ms |
| orders-service | `dev` | `config-v1.0` | orders-dev-release-v1 | 900ms |

Với mỗi dòng, lưu lại:

- URL đã gọi.
- HTTP status.
- `name`, `profiles`, `label`, `version`.
- Thứ tự `propertySources`.
- Giá trị cuối cùng của `demo.message` và `demo.timeout`.
- File/PropertySource cung cấp giá trị thắng.
- Giải thích vì sao nguồn đó có precedence cao nhất.

Nếu có khác biệt với bảng dự kiến, ghi lại kết quả thực tế trước rồi tìm nguyên nhân. Kiểm tra branch/tag đã push hoặc có trong clone của Config Server, file có đúng tên, và `propertySources` trả về có đúng thứ tự.

## 12. Phân biệt nhiều profile với nhiều label

Hai khái niệm này điều khiển hai chiều khác nhau:

- Nhiều profile: yêu cầu Config Server ghép các cấu hình theo nhiều profile, ví dụ `dev,mysql`.
- Nhiều label: yêu cầu client thử hoặc lấy cấu hình từ nhiều revision label, tùy phiên bản Spring Cloud Config và cách bật tính năng.

Trong lab chính, ta gửi từng label riêng để kết quả rõ ràng và dễ tái lập. Có thể mở rộng sang danh sách label:

~~~yaml
spring:
  cloud:
    config:
      label: feature,main
~~~

Theo hành vi mặc định trước Spring Cloud Config 4.2.0, client thử lần lượt các label cho tới khi một label được chấp nhận. Từ 4.2.0, nếu bật `spring.cloud.config.send-all-labels=true` và cả client lẫn server đều dùng phiên bản hỗ trợ, client có thể gửi danh sách label trong một request để server trả property sources từ các label đó. Mặc định `send-all-labels` là `false`.

Không bật `send-all-labels` một cách độc lập khi Config Server đang chạy phiên bản cũ. Hãy kiểm tra compatibility của cả client và server theo tài liệu release train đang dùng. Nếu cần kiểm chứng một label cụ thể, gọi URL có label riêng vẫn là cách đơn giản và dễ đọc nhất.

## 13. Thử thay đổi cấu hình và refresh client

Thử một thay đổi trên branch `main`, ví dụ đổi `demo.timeout` trong `orders-service-dev.yml` từ `800ms` thành `700ms`.

Commit thay đổi:

~~~powershell
git switch main
git add orders-service-dev.yml
git commit -m "Tune dev timeout"
~~~

Gọi Config Server lại:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
~~~

Nếu server trả giá trị mới, Git backend đã nhìn thấy commit mới. Client đang chạy có thể vẫn giữ giá trị cũ cho tới khi được refresh.

Gửi refresh cục bộ nếu client đã expose và bảo vệ Actuator endpoint:

~~~powershell
curl.exe --request POST "http://localhost:8080/actuator/refresh"
~~~

Sau đó kiểm tra lại `/config-view`. Nếu bean dùng `@RefreshScope` hoặc cơ chế rebinding phù hợp, giá trị có thể được cập nhật theo cấu hình mới. Một singleton giữ field đã bind lúc khởi tạo không tự động thay giá trị chỉ vì Environment thay đổi.

Nếu thay đổi `spring.cloud.config.label` từ `main` sang `release-v1`, hãy restart client để thực hiện bootstrap fetch với label mới. Đừng nhầm việc thay nội dung trên cùng branch với việc chuyển sang một label khác.

Trong hệ thống nhiều instance, Spring Cloud Bus có thể phát refresh event tới nhiều client. Hãy xác minh từng instance đã fetch và áp dụng thành công; response thành công của publisher không chứng minh tất cả instance đã đổi giá trị.

## 14. Câu hỏi thực hành và lời giải thích cần nộp

Trả lời bằng bằng chứng từ response, không chỉ ghi một giá trị.

**Câu 1.** Với profile `dev,mysql` và label `main`, vì sao `demo.timeout` là `1200ms`?

Gợi ý: xác định file profile cụ thể của `orders-service`, sau đó so sánh thứ tự profile `dev` và `mysql`.

**Câu 2.** Đổi profile thành `mysql,dev` thì giá trị `demo.timeout` là bao nhiêu? Vì sao?

Gợi ý: profile cuối có ưu tiên cao hơn. Tìm PropertySource đầu tiên có chứa key này.

**Câu 3.** Với `dev,mysql`, tại sao `demo.profile-marker` vẫn có thể lấy từ `orders-service-dev.yml` dù `mysql` có ưu tiên cao hơn?

Gợi ý: một nguồn ưu tiên thấp vẫn có thể cung cấp key mà nguồn ưu tiên cao hơn không khai báo.

**Câu 4.** Vì sao `dev/main` và `dev/release-v1` có cùng tên PropertySource nhưng giá trị timeout khác nhau?

Gợi ý: tên file không xác định nội dung revision; kiểm tra `label` và `version`.

**Câu 5.** `dev/release-v1` và `dev/config-v1.0` có kết quả giống nhau trong lab không? Điều kiện nào làm chúng khác nhau?

Gợi ý: branch có thể tiếp tục nhận commit; tag giữ nguyên commit mà nó trỏ tới.

**Câu 6.** Nếu Config Server trả timeout mới nhưng `/config-view` vẫn hiển thị giá trị cũ, cần kiểm tra những gì?

Gợi ý: client refresh, property source local, bean binding và `@RefreshScope`.

**Câu 7.** Nếu request bỏ label, Config Server dùng label nào? Bằng chứng nào xác nhận điều đó?

Gợi ý: xem `default-label` trong Config Server và trường `label` trong response.

**Câu 8.** Nếu profile `mysql` không có `demo.message`, giá trị đó có biến mất không?

Gợi ý: property source thấp hơn vẫn có thể cung cấp key chưa được nguồn cao hơn khai báo.

## 15. Bảng giải thích mẫu

Một lời giải tốt cần trình bày được cả thứ tự và nguồn của từng key:

| Request | Nguồn ưu tiên cao nhất | `demo.timeout` | Lý do |
|---|---|---|---|
| `dev/main` | `orders-service-dev.yml` | `800ms` | App-specific + profile-specific |
| `mysql/main` | `orders-service-mysql.yml` | `1200ms` | App-specific + profile-specific |
| `dev,mysql/main` | `orders-service-mysql.yml` | `1200ms` | `mysql` là profile cuối |
| `mysql,dev/main` | `orders-service-dev.yml` | `800ms` | `dev` là profile cuối |
| `dev/release-v1` | `orders-service-dev.yml` trên label release | `900ms` | Cùng tên file nhưng nội dung revision khác |

Đối với các property khác, tìm nguồn thắng riêng cho từng key. Không kết luận rằng cả một PropertySource thắng cho mọi thuộc tính; nó chỉ thắng khi chứa key đang được tra cứu và có ưu tiên cao hơn các nguồn khác chứa cùng key.

## 16. Troubleshooting khi kết quả không khớp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTTP 404 hoặc lỗi đọc label | Branch/tag chưa có trong remote hoặc sai label | `git branch`, `git tag`, kiểm tra URI |
| `demo.timeout` luôn là 5s | Chỉ có file dùng chung được nạp | Kiểm tra tên file và `propertySources` |
| Profile `dev,mysql` không chọn mysql | Thứ tự profile request khác dự kiến hoặc server/repository khác | Xem trường `profiles` và danh sách PropertySource |
| `release-v1` vẫn trả nội dung cũ | Config Server clone chưa thấy commit mới hoặc label không đúng | Kiểm tra Git revision và server log |
| Config Server đúng nhưng client cũ | Client chưa refresh hoặc bean không hỗ trợ cập nhật | Kiểm tra refresh result, Environment và bean |
| Client lấy giá trị local | Environment variable/system property/local file ghi đè | Kiểm tra `/actuator/env/{property}` |
| Một số instance khác revision | Các instance fetch ở thời điểm khác nhau hoặc refresh không đồng đều | Ghi nhận label/version trên từng instance |
| Tag và branch cho kết quả khác | Branch đã tiến thêm commit sau khi tag được tạo | So sánh commit ID |

Một số lưu ý:

- Đảm bảo Config Server trỏ đúng repository.
- Dùng label tường minh trong URL khi kiểm tra.
- Không dựa vào branch mặc định nếu chưa cấu hình `default-label`.
- Không dùng `optional:configserver:` khi muốn startup fail nếu remote config thiếu.
- Không log hoặc chia sẻ toàn bộ Environment nếu có secret.
- Bảo vệ `/actuator/env`, `/actuator/configprops` và các endpoint refresh.
- Không commit password, token hoặc private key vào Git config repository.

## 17. Mở rộng: kiểm tra precedence với một property mới

Thêm một property `demo.banner` với giá trị khác nhau trong ba file:

Trong **application.yml**:

~~~yaml
demo:
  banner: shared-banner
~~~

Trong **application-dev.yml**:

~~~yaml
demo:
  banner: dev-banner
~~~

Trong **orders-service-dev.yml**:

~~~yaml
demo:
  banner: orders-dev-banner
~~~

Commit thay đổi vào `main`, sau đó gọi:

~~~powershell
curl.exe --fail --silent --show-error "http://localhost:8888/orders-service/dev/main"
~~~

Giải thích vì sao `demo.banner` là `orders-dev-banner`. Sau đó xóa key này khỏi `orders-service-dev.yml`, gọi lại và quan sát giá trị chuyển sang nguồn profile dùng chung. Tiếp tục xóa khỏi `application-dev.yml` và quan sát fallback về `application.yml`.

Thí nghiệm này cho thấy precedence hoạt động theo từng key. Khi nguồn cao nhất không khai báo property, Spring Environment tiếp tục tìm ở nguồn kế tiếp.

## 18. Checklist hoàn thành lab

- [ ] Tạo Git repository có đủ file dùng chung, theo application và theo profile.
- [ ] Tạo branch `main` và `release-v1`.
- [ ] Tạo tag `config-v1.0` từ commit release.
- [ ] Config Server đọc đúng repository và default label.
- [ ] Gọi Environment endpoint cho profile `dev` và `mysql`.
- [ ] Gọi Environment endpoint cho `dev,mysql` và `mysql,dev`.
- [ ] Ghi lại thứ tự `propertySources` cho mỗi request.
- [ ] Xác định giá trị `demo.message` và `demo.timeout` được chọn.
- [ ] So sánh `main`, `release-v1` và `config-v1.0`.
- [ ] Kiểm tra `label` và `version` trong response.
- [ ] Bind giá trị vào `DemoProperties` trong Config Client.
- [ ] Xác minh runtime qua `/config-view`.
- [ ] Thử thay đổi cấu hình trên cùng label và refresh client.
- [ ] Phân biệt refresh nội dung với thay đổi label client yêu cầu.
- [ ] Giải thích các kết quả dựa trên property source và precedence.
- [ ] Giữ secret ngoài repository và bảo vệ Actuator endpoint.

## 19. Tài liệu tham khảo

- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html): application/profile/label và quy tắc precedence giữa các profile.
- [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, cách client chọn application/profile/label và hỗ trợ nhiều label.
- [Spring Cloud Config — Quickstart](https://docs.spring.io/spring-cloud-config/docs/current/reference/html/quickstart.html): ví dụ cấu hình Config Server và Config Client.

Kết quả của bài lab cần chỉ ra được vì sao cùng một property thay đổi khi đổi profile, đảo thứ tự profile hoặc chuyển label. Hãy dựa vào Environment response, `propertySources` và revision để giải thích; sau đó đối chiếu với bean trong Config Client. Khi phân biệt rõ profile quyết định nhóm cấu hình, label quyết định phiên bản repository và PropertySource quyết định giá trị thắng, bạn có thể tái lập và giải thích cấu hình đang chạy thay vì chỉ đoán từ file YAML.

