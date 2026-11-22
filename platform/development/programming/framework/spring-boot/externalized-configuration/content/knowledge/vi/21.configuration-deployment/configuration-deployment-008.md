# Phân biệt đọc lúc khởi động với thay đổi tệp sau khi ứng dụng đã chạy

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Triển khai cấu hình

## 1. Bài toán: sửa cấu hình trên ổ đĩa, tại sao ứng dụng vẫn dùng giá trị cũ?

Giả sử một ứng dụng Spring Boot được chạy với tệp `./config/application.yml` bên ngoài JAR:

~~~yaml
catalog:
  client:
    timeout: 3s
    enabled: true
~~~

Một nhân viên vận hành muốn tăng timeout do dịch vụ Catalog đang đáp ứng chậm. Họ sửa file:

~~~yaml
catalog:
  client:
    timeout: 10s
    enabled: true
~~~

Tệp lưu thành công; mở lại bằng trình soạn thảo thấy chính xác `10s`. Tuy nhiên, những request mới tới Spring Boot service vẫn timeout sau khoảng 3 giây. Điều này **không nhất thiết là lỗi** của Spring Boot hay filesystem.

Nhiều ứng dụng đọc Config Data khi **khởi động**, tạo `Environment`, bind các giá trị vào `@ConfigurationProperties` và dùng chúng để tạo HTTP client, connection pool hoặc bean. Việc tệp bên ngoài được chỉnh sửa sau đó **không tự làm Spring Boot nạp lại file, bind lại bean và cấu hình lại các tài nguyên đã được tạo**.

Bài học tập trung phân biệt ba sự kiện thường bị đánh đồng:

1. **Tệp trên filesystem thay đổi.**
2. **Nguồn property có hiệu lực trong tiến trình được đọc/nạp lại.**
3. **Các component đang hoạt động thực sự dùng giá trị mới.**

Việc hoàn thành bước 1 không chứng minh bước 2 hoặc bước 3 đã xảy ra.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

- Nêu được các bước từ nạp Config Data tới bean hoạt động lúc khởi động.
- Phân biệt nội dung hiện tại của file, giá trị trong Spring `Environment`, giá trị trong `@ConfigurationProperties` và trạng thái của client đã tạo.
- Hiểu tại sao file `application.yml`, `spring.config.import`, config tree và file qua `@PropertySource` không tự cung cấp hot reload mặc định.
- Phân biệt thay file trong classpath/JAR với thay file bên ngoài JAR.
- Xác định ảnh hưởng của việc đổi ConfigMap/Secret mount, environment variables và file `subPath` trong Kubernetes.
- Chọn giữa restart/rolling rollout và refresh động khi nhu cầu triển khai thực sự đòi hỏi.
- Thiết kế kiểm tra, runbook, readiness và rollback cho một lần đổi cấu hình.
- Tránh dùng dấu hiệu “file đã sửa” thay cho xác nhận ứng dụng đã áp dụng cấu hình.

## 2. Chu trình cấu hình cơ bản của Spring Boot

Ở một lần khởi động thông thường, quá trình có thể hình dung như sau:

~~~text
T0 — Trước khi chạy JVM
  - application.yml/application.properties tồn tại
  - biến môi trường và tham số CLI được thiết lập
  - ConfigMap/Secret hoặc file externalized được cấp
                   |
                   v
T1 — SpringApplication chuẩn bị Environment
  - đọc config data từ các location có hiệu lực
  - xét profiles, imports, documents, precedence
                   |
                   v
T2 — Khởi tạo ApplicationContext
  - tạo các beans
  - bind @ConfigurationProperties
  - giải quyết @Value
  - chuyển kiểu/validation
                   |
                   v
T3 — Khởi tạo tài nguyên runtime
  - HTTP clients, DataSource, pools, schedulers
  - các cấu trúc cache hoặc chính sách nghiệp vụ
                   |
                   v
T4 — Ứng dụng nhận traffic
                   |
                   v
T5 — Có người sửa tệp application.yml ngoài JAR
  - bytes của tệp trên đĩa thay đổi
  - KHÔNG mặc định quay lại T1, T2, T3
~~~

Đây là sơ đồ khái quát: các hook trong Spring có thứ tự chi tiết theo framework và từng bean. Nhưng vấn đề vận hành nằm ở ranh giới **T5 không tự kích hoạt chu trình nạp và tái tạo cấu hình**.

### 2.1. Externalized configuration không đồng nghĩa hot reload

“Externalized” nghĩa là giá trị cấu hình được tách khỏi code ứng dụng và có thể cấp từ các nguồn bên ngoài artifact. Nó giúp cùng một JAR chạy ở dev, staging và production với giá trị khác nhau.

Nó **không mang ý nghĩa** cứ sửa bất kỳ nguồn nào bên ngoài là mọi tiến trình đang chạy sẽ thấy thay đổi ngay lập tức. Cách cấp cấu hình và cách cập nhật cấu hình là **hai quyết định kiến trúc độc lập**.

### 2.2. Một Spring bean có thể là ảnh chụp của cấu hình

Với Spring Boot 3 và Java 17+:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        boolean enabled
) {}
~~~

Khi bean `CatalogClientProperties` được bind, record là một object có các component đã được thiết lập. Sửa file YAML không làm các field của record tự đổi từ `3s` sang `10s`.

Ngay cả một JavaBean mutable:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public class MutableClientProperties {
    private Duration timeout;

    public Duration getTimeout() { return timeout; }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

cũng không mặc định tự chạy lại setter chỉ vì file thay đổi. Mutable object **có khả năng** cập nhật, không có nghĩa framework đã tự cài đặt một file watcher/rebind pipeline.

### 2.3. Giá trị đã được copy vào một client còn khó cập nhật hơn

Ví dụ cấu hình HTTP client một lần:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfig {

    @Bean
    HttpClient catalogHttpClient(CatalogClientProperties props) {
        return HttpClient.newBuilder()
                .connectTimeout(props.timeout())
                .build();
    }
}
~~~

Giả sử các import Java cần thiết đã được khai báo. Khi tạo `HttpClient`, timeout được cấp cho builder. Về sau, nếu một cơ chế nào đó thay đổi `CatalogClientProperties`, cũng không thể tự suy ra instance `HttpClient` đã được xây dựng sẽ đổi theo. Phải xem contract của client và phương án tạo lại bean/tài nguyên.

Vì vậy, có **ít nhất bốn vị trí** cần kiểm tra: filesystem, `Environment`, properties bean và resource client.

## 3. Bảng phân biệt nhanh bốn trạng thái

| Thành phần | Giữ gì? | Tự đổi khi file `application.yml` bị sửa? |
| --- | --- | --- |
| File ngoài JAR | Bytes/nội dung được lưu trên đĩa | **Có**, nếu thao tác sửa thực sự thành công |
| Spring `Environment` với Config Data đã nạp | Các PropertySource tạo trong lần nạp | **Không mặc định** |
| Singleton `@ConfigurationProperties` | Giá trị đã bind | **Không mặc định** |
| `@Value` trên field của singleton bean | Giá trị được inject khi tạo bean | **Không mặc định** |
| Client hoặc connection pool đã tạo | Tham số cấu hình nội bộ, connections, cache | **Không mặc định** |
| Đọc file trực tiếp mỗi lần gọi `Files.readString` | Bytes tại lần đọc đó | Có thể thấy thay đổi khi mở/đọc lại file |
| Client dùng secret/config supplier có refresh thật | Giá trị do supplier/cache quyết định | Tùy implementation và refresh policy |
| Bean trong cơ chế refresh chuyên biệt | Giá trị của bản bean sau refresh | Chỉ khi refresh được kích hoạt và áp dụng đúng |

“Không mặc định” là cách diễn đạt cần giữ. Một ứng dụng có thể tích hợp Spring Cloud, file watcher hoặc thư viện reload riêng; các cơ chế đó thay đổi hành vi. Nhưng **Spring Boot externalized configuration cơ bản không đưa ra bảo đảm hot reload cho mọi loại file và bean**.

## 4. Trường hợp 1: file application.yml trong classpath hoặc trong JAR

Một project:

~~~text
catalog-service/
├── src/main/resources/application.yml
└── src/main/java/...
~~~

Khi đóng gói Spring Boot executable JAR, resource này thường nằm bên trong artifact. Ở một lần chạy bình thường, Boot đọc nó từ classpath trong giai đoạn nạp Config Data.

Nếu developer sửa `src/main/resources/application.yml` trên máy sau khi JAR đã build và chạy:

- File source mới không tự sửa nội dung bên trong JAR cũ.
- Tiến trình đang chạy không tự lấy lại file source mới.
- Chạy lại **chính JAR cũ** vẫn thường dùng nội dung được đóng gói trong JAR ấy, không phải nội dung source vừa sửa.
- Muốn thay nội dung embedded config, thường cần build/redeploy artifact mới hoặc cấp một nguồn externalized phù hợp.

### 4.1. Đừng sửa trực tiếp archive đang được tiến trình sử dụng

Sửa file bên trong JAR đang chạy không phải một chiến lược cập nhật cấu hình đáng tin cậy. Archive có thể đang được classloader sử dụng; cách sửa có thể làm hỏng artifact hoặc cho ra hành vi không dự đoán được.

Thực hành tốt là coi artifact **immutable** và tách giá trị của từng môi trường ra Config Data bên ngoài, biến môi trường hoặc secret manager. Điều này tránh phải build lại cùng code chỉ để đổi một timeout.

### 4.2. DevTools không phải quy tắc runtime production

Spring Boot DevTools có cơ chế restart trong môi trường phát triển khi classpath được cập nhật. Nhưng đây là **development convenience**, không phải bảo đảm hot reload cho production.

Một lần restart do DevTools có thể khiến ứng dụng đọc lại cấu hình, nhưng đó là do **ngữ cảnh được tạo lại**, không phải bằng chứng mọi bean tự thay đổi trực tiếp trong một tiến trình không restart. Không thiết kế vận hành production dựa vào hành vi của IDE/DevTools.

## 5. Trường hợp 2: file application.yml ngoài JAR

Giả sử:

~~~text
/deploy/catalog/
├── catalog.jar
└── config/
    └── application.yml
~~~

File:

~~~yaml
catalog:
  client:
    timeout: 3s
~~~

Chạy từ working directory `/deploy/catalog`:

~~~bash
java -jar catalog.jar
~~~

Spring Boot có các default config locations ngoài classpath, trong đó có các vị trí tương đối như `file:./` và `file:./config/`. Nếu working directory và quy tắc config data phù hợp, `./config/application.yml` sẽ được nạp lúc khởi động.

### 5.1. Một file externalized dễ đổi hơn, nhưng không tự live reload

Việc người vận hành có thể sửa `./config/application.yml` mà không build lại JAR là lợi ích quan trọng. Tuy nhiên, những singleton beans được tạo trước thời điểm sửa thường vẫn giữ giá trị cũ.

Ví dụ timeline:

~~~text
09:00:00  JVM khởi động, Config Data đọc timeout=3s
09:00:01  Binder tạo CatalogClientProperties(timeout=3s)
09:00:02  HTTP client được tạo với timeout tương ứng
10:15:00  Operator sửa file timeout=10s
10:15:01  File trên disk là 10s
10:15:02  Bean trong JVM vẫn là 3s
10:15:03  Client vẫn có thể dùng 3s
10:20:00  JVM được restart bằng cấu hình hiện hành
10:20:01  Bean mới nhận 10s nếu nguồn ưu tiên cao hơn không override
~~~

Không cần giả định mọi file update gây restart. Nên coi **restart/reload** là một bước triển khai riêng, có xác nhận.

### 5.2. Đường dẫn file phụ thuộc working directory

`file:./config/application.yml` thường được giải quyết tương đối với working directory của tiến trình, không tự động tương đối với thư mục chứa JAR.

Một service chạy từ systemd, Docker hoặc IDE có thể có working directory khác. Nếu sửa một file ở `/deploy/catalog/config/application.yml` nhưng JVM đang tìm `/app/config/application.yml`, restart cũng không giúp nếu vị trí đang dùng không thay đổi.

Nên ghi rõ đường dẫn tuyệt đối hoặc làm rõ working directory trong runbook. Không sửa ngẫu nhiên nhiều file cùng tên để tìm “file nào có tác dụng”.

### 5.3. Vấn đề precedence

File ngoài JAR có thể được nạp nhưng giá trị của nó vẫn không thắng, nếu một nguồn có ưu tiên cao hơn cung cấp cùng key.

Ví dụ:

~~~yaml
# ./config/application.yml
catalog:
  client:
    timeout: 10s
~~~

Nhưng runtime có:

~~~bash
java -jar catalog.jar --catalog.client.timeout=2s
~~~

Trong cấu hình thông thường, command-line property thắng Config Data. Dù restart, giá trị cuối vẫn có thể là `2s`.

Do đó, khi thấy “sửa file nhưng không đổi giá trị”, hãy phân biệt hai nguyên nhân:

1. **Chưa nạp lại** cấu hình sau khi sửa.
2. **Đã nạp lại nhưng nguồn khác override**.

## 6. Trường hợp 3: thêm file qua spring.config.import

Ví dụ `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/catalog-extra.yml"

catalog:
  client:
    timeout: 3s
~~~

File import:

~~~yaml
catalog:
  client:
    timeout: 10s
~~~

Spring Boot Config Data xử lý `spring.config.import` **trong giai đoạn chuẩn bị cấu hình**, nên file import có thể góp property và override trong thứ tự được Boot quy định.

Nhưng khi file `catalog-extra.yml` thay đổi sau khi ứng dụng chạy, chỉ vì nó được import không có nghĩa Boot tự đọc lại và bind lại mọi bean.

### 6.1. optional: không phải auto-refresh

Prefix `optional:` nghĩa là khi location không tồn tại, cơ chế Config Data có thể bỏ qua lỗi missing location. Nó **không** có nghĩa:

- Chờ file xuất hiện rồi tự đọc lại.
- Tự reload khi file bị sửa.
- Bỏ qua mọi lỗi YAML sai cú pháp.
- Biến một property bắt buộc thành hợp lệ.
- Cập nhật các bean đã được tạo.

Nếu file chứa dữ liệu bắt buộc, cần validation hoặc hợp đồng startup phù hợp.

### 6.2. Import nhiều nguồn cần hiểu thứ tự

Khi có nhiều file import hoặc location groups, precedence có thể quyết định property cuối cùng. Sau restart, vẫn cần xác nhận nguồn đang được áp dụng. Một file đã được đọc lại nhưng bị file khác ưu tiên hơn ghi đè có thể tạo cảm giác “restart mà vẫn không đổi”.

Không lấy thời gian chỉnh sửa của file để suy ra file đó có precedence cao. Config Data có quy tắc riêng về locations, imports, profiles và document order.

## 7. Trường hợp 4: configtree và file mounted

Spring Boot hỗ trợ một import kiểu config tree, thường dùng khi mỗi property nằm trong một file riêng.

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Ví dụ cây:

~~~text
/run/config/
├── catalog.client.timeout
├── catalog.client.enabled
└── partner.api.token
~~~

Mỗi **tên file** đại diện property name; **nội dung file** là property value. Nếu file `catalog.client.timeout` chứa `3s`, Binder có thể nhận `catalog.client.timeout=3s`.

### 7.1. File cập nhật không làm record tự đổi

Một orchestrator có thể thay nội dung file `catalog.client.timeout` thành `10s`. Nếu record `CatalogClientProperties` đã được tạo trong lúc startup, nó không tự đổi.

Quan hệ:

~~~text
File /run/config/catalog.client.timeout
            |
            | được đọc khi Config Data nạp
            v
Environment / Config Data PropertySource
            |
            | bind vào object
            v
CatalogClientProperties(timeout=3s)
            |
            | cấp giá trị cho client
            v
HttpClient(timeout=3s)
~~~

Sửa file chỉ tác động rõ ràng lên **nút đầu tiên**. Các bước tiếp theo cần cơ chế cập nhật được thiết kế hoặc restart.

### 7.2. Nội dung file và cách đọc lại

Nếu muốn đọc file trực tiếp cho mỗi request, có thể dùng `Files.readString`; nếu muốn đọc theo chu kỳ, có thể dùng scheduler/file watcher. Nhưng đó là **logic ứng dụng tùy chỉnh**, không phải tính năng tự động của config tree import.

Với file chứa secret, cần xác định encoding, trailing newline, quyền truy cập và cơ chế atomic replacement. Không tự dùng `trim()` lên mọi giá trị secret vì có thể làm thay đổi credential hợp lệ.

## 8. @PropertySource cũng có thời điểm nạp riêng

Một cấu hình Spring Framework:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-settings.properties")
class LegacySettingsConfiguration {}
~~~

có thể thêm resource `.properties` vào `Environment` khi configuration class được xử lý trong quá trình refresh ApplicationContext.

Khi file được sửa sau đó, annotation không tự xử lý lại, và bean dùng `@Value` cũng không tự nhận lại giá trị.

### 8.1. @PropertySource không thay thế Config Data

- `@PropertySource` mặc định phù hợp với resource `.properties`.
- YAML không được nó hỗ trợ theo cùng cách Boot nạp `application.yml` nếu không có factory riêng.
- Các tài liệu nhiều phần và profile activation cần cơ chế Config Data.
- `@PropertySource` được thêm tương đối muộn so với những cấu hình như `logging.*` hoặc `spring.main.*`.

Việc chọn một custom YAML `PropertySourceFactory` không tự giải quyết vấn đề dynamic reload. Factory thay đổi cách parse resource khi được gọi, chứ không tự biến annotation thành file watcher.

### 8.2. Config Data location và thời điểm khởi động

Các property như `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được dùng rất sớm để quyết định nơi nạp file. Nếu đặt chúng trong một resource chỉ được thêm sau bằng `@PropertySource`, đừng kỳ vọng Boot quay lại quá trình tìm file.

Đây là một ví dụ khác cho thấy **thời điểm đọc cấu hình** quan trọng tương đương với nội dung giá trị.

## 9. Spring Environment có phải luôn bất biến?

Không. Spring `ConfigurableEnvironment` và `MutablePropertySources` cho phép code thay đổi danh sách PropertySource hoặc thêm các giá trị tại runtime.

Ví dụ một chương trình có thể thêm:

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.ConfigurableEnvironment;

public void addOverride(ConfigurableEnvironment env) {
    env.getPropertySources().addFirst(
            new MapPropertySource(
                    "runtime-override",
                    Map.of("catalog.client.timeout", "10s")
            )
    );
}
~~~

Sau thao tác này, một phép `environment.getProperty("catalog.client.timeout")` có thể nhìn thấy `10s` do source mới ưu tiên cao.

Tuy nhiên:

- Singleton `CatalogClientProperties` đã bind trước đó vẫn có thể là `3s`.
- Field được inject bằng `@Value` khi tạo bean không tự đổi.
- HTTP client đã xây dựng với `3s` không tự tái tạo.
- Thay đổi tùy ý `Environment` tại runtime có thể tạo **các component đọc hai phiên bản cấu hình khác nhau**.

**Đổi Environment không đồng nghĩa đổi toàn bộ hệ thống.** Nếu làm vậy, cần thiết kế quy trình rebind/recreation và sự nhất quán.

### 9.1. Tránh “hot patch” Environment bằng tay trong production

Nếu một operator gọi custom endpoint để thêm `MapPropertySource` vào một JVM, nó có thể chỉ tác động instance ấy mà không tác động các replica khác. Khởi động lại tiến trình có thể làm mất override in-memory.

Nếu có nhu cầu đổi cấu hình chung cho nhiều instance, hãy dùng một cơ chế quản trị có phân phối, xác nhận và bảo mật thích hợp thay vì trông chờ mỗi instance tự đồng bộ các thay đổi thủ công.

## 10. @ConfigurationProperties là object được bind, không phải file watcher

Bảng so sánh:

| Mô hình sử dụng | Giá trị khi khởi tạo | Khi file đổi | Để áp dụng giá trị mới |
| --- | --- | --- | --- |
| Constructor-bound record | Final components | Không tự đổi | Tạo/bind bean mới |
| JavaBean @ConfigurationProperties | Setters/field values | Không tự gọi setter | Rebind hoặc khởi tạo lại |
| @Value trên singleton | Giá trị inject | Không tự inject lại | Tái tạo bean hoặc cơ chế refresh |
| HttpClient builder | Client config được copy | Không tự rebuild | Tạo client mới |
| HikariCP pool | Connection settings và pool state | Không tự cập nhật tất cả | Restart/recreate hoặc API quản trị được test |
| Scheduler được tạo với cron ban đầu | Trigger đã lập lịch | Không tự schedule lại | Tái đăng ký trigger/scheduler |
| Code gọi Files.readString mỗi request | Nội dung file tại mỗi lần mở | Có thể nhận file mới | Xử lý đọc và consistency an toàn |

### 10.1. Record bất biến giúp xác định hợp đồng

Record:

~~~java
@ConfigurationProperties(prefix = "reports.export")
public record ExportProperties(
        String directory,
        Duration interval
) {}
~~~

Rõ ràng là snapshot. Trong một lần restart, một record mới nhận các giá trị từ nguồn hiện hành. Điều này phù hợp với mô hình **immutable deployment**: artifact ổn định, cấu hình được áp dụng tại mỗi lần khởi động.

### 10.2. Mutable JavaBean không làm hệ thống tự refresh

Class có setter:

~~~java
@ConfigurationProperties(prefix = "reports.export")
public class ExportProperties {
    private Duration interval = Duration.ofMinutes(5);

    public Duration getInterval() { return interval; }
    public void setInterval(Duration interval) {
        this.interval = interval;
    }
}
~~~

vẫn giữ `5m` hoặc giá trị đã bind cho tới khi có code/framework gọi lại setter hoặc khởi tạo object mới. Mutable object không tự quan sát filesystem.

### 10.3. Object cấu hình là một lớp; object sử dụng là một lớp

Ngay cả khi properties bean được update thành 10s bằng một cơ chế refresh, một executor hoặc scheduler đã tạo với 3s vẫn có thể cần được dừng và tạo lại. Vì vậy, thiết kế refresh phải liệt kê **đường truyền giá trị** từ nguồn đến từng component tiêu thụ.

## 11. Tại sao thay file nhưng Environment vẫn có giá trị cũ?

Có nhiều nguyên nhân có thể xảy ra:

1. File không được nạp lại sau khi sửa.
2. File người vận hành sửa không nằm ở config location đang dùng.
3. File được nạp lại nhưng property bị nguồn khác ưu tiên cao hơn ghi đè.
4. Profile đang active khác file đã sửa.
5. Tài liệu YAML có `spring.config.activate.on-profile` không active.
6. File import qua `optional:` không tồn tại ở thời điểm nạp.
7. File mới đã có giá trị đúng nhưng bean vẫn giữ snapshot cũ.
8. Bean được cập nhật nhưng client/cache vẫn dùng giá trị cũ.
9. Một replica khác đang phục vụ request và chưa được cập nhật.
10. Một cơ chế refresh tùy chỉnh đã thất bại hoặc chưa được gọi.

### 11.1. Phân biệt bằng một key không nhạy cảm

Nếu dùng test property `catalog.client.timeout`, có thể quan sát:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final Environment environment;
    private final CatalogClientProperties properties;

    public ConfigProbe(
            Environment environment,
            CatalogClientProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Environment timeout = "
                + environment.getProperty("catalog.client.timeout")
        );
        System.out.println(
                "Bound bean timeout = " + properties.timeout()
        );
    }
}
~~~

Phép kiểm tra được chạy khi ApplicationRunner hoạt động sau startup, không phải file watcher. Đọc lại các trường sau này có thể cho các kết quả khác nhau nếu một cơ chế riêng đã update Environment nhưng không rebind bean.

Chỉ dùng để quan sát key **không chứa bí mật**. Không in mọi property hoặc toàn bộ objects có token/password vào log.

### 11.2. Đọc trực tiếp source sau khi file đổi

Một câu lệnh shell như:

~~~bash
cat ./config/application.yml
~~~

chỉ chứng minh nội dung tệp tại vị trí shell đọc. Nó không chứng minh Java process đang dùng cùng working directory, đã đọc lại tệp hay không có nguồn cao hơn ghi đè.

Nếu nghi ngờ đường dẫn, kiểm tra working directory, systemd WorkingDirectory, Docker WORKDIR, volume mount path và tham số `spring.config.location` hoặc `spring.config.additional-location`.

## 12. Kubernetes ConfigMap qua environment variables

Trong Kubernetes, ứng dụng có thể nhận ConfigMap dưới dạng biến môi trường:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: example/catalog-service:1.0
          env:
            - name: CATALOG_CLIENT_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: catalog-runtime
                  key: timeout
~~~

Khi Kubernetes tạo container, biến môi trường được cấp dựa trên ConfigMap ở thời điểm tạo. Nếu sau đó ConfigMap `catalog-runtime` được cập nhật, **environment của container đang chạy không được cập nhật tự động**.

Điểm này không liên quan trực tiếp tới mutability của `@ConfigurationProperties`: ngay cả nếu code muốn đọc lại env mỗi request, process environment vẫn chứa giá trị ban đầu.

### 12.1. Pod mới có thể nhận giá trị mới

Để nhận ConfigMap mới qua environment variables, cần tạo Pod/container mới theo cơ chế triển khai. Với Deployment, một rolling restart hoặc thay đổi Pod template có thể tạo những Pod mới, và chúng nhận env hiện tại.

Cập nhật ConfigMap object **không phải lúc nào tự tạo rollout**. Nếu manifest chỉ tham chiếu cùng tên ConfigMap và Pod template không đổi, một Deployment thông thường có thể giữ các Pod cũ.

### 12.2. Ví dụ thao tác đã được phê duyệt

Trong môi trường có quyền và change plan phù hợp:

~~~bash
kubectl rollout restart deployment/catalog-service \
  --namespace production

kubectl rollout status deployment/catalog-service \
  --namespace production
~~~

Đây là ví dụ lệnh vận hành, không phải gợi ý chạy ngay trên production để thử nghiệm. Cần kiểm tra namespace, deployment và tác động trước khi thực hiện.

## 13. Kubernetes ConfigMap/Secret qua volume mount

Kubernetes cũng có thể mount ConfigMap hoặc Secret thành file:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: example/catalog-service:1.0
          volumeMounts:
            - name: catalog-settings
              mountPath: /app/config
              readOnly: true
      volumes:
        - name: catalog-settings
          configMap:
            name: catalog-config-files
~~~

Giả sử ConfigMap có data key `application.yml`, kubelet có thể làm tệp `/app/config/application.yml` xuất hiện trong Pod.

### 13.1. File volume có thể đổi mà tiến trình chưa áp dụng

Với mount ConfigMap/Secret volume thông thường, Kubernetes có cơ chế cập nhật nội dung volume khi object thay đổi, theo hướng **eventual consistency**, không phải đồng bộ tức thì.

Timeline:

~~~text
10:00  ConfigMap được cập nhật
10:00+ Kubelet nhận thay đổi, sau độ trễ
10:01  File /app/config/application.yml trong Pod có thể đã mới
10:01  Spring Environment vẫn có Config Data của lần startup
10:01  @ConfigurationProperties bean và HTTP client vẫn có thể dùng cũ
10:05  Pod mới được tạo, Boot đọc file hiện tại khi startup
10:05  Bean mới dùng value mới nếu không bị source khác override
~~~

Việc một file watcher phát hiện tệp mới là **một điều kiện cần** cho hot reload dựa trên file, nhưng **chưa đủ** nếu không có logic parse, validation, rebind và cập nhật clients.

### 13.2. Giới hạn subPath

Nếu mount file bằng Kubernetes `subPath`, các cập nhật tự động của ConfigMap/Secret volume không hoạt động theo cùng cách như mount thông thường.

Do đó, đừng thiết kế hot reload bằng cách giả định một file mount qua `subPath` sẽ thay đổi khi ConfigMap/Secret object đổi. Cần tạo lại Pod/mount hoặc dùng cơ chế phân phối khác đã được thử nghiệm.

### 13.3. Secret khác ConfigMap ở bảo mật, không ở nguyên tắc snapshot bean

Secret chứa dữ liệu nhạy cảm; ConfigMap dành cho cấu hình không bí mật. Nhưng khi cùng được cung cấp qua file lúc startup, việc Spring Boot bind vào bean vẫn có tính snapshot tương tự.

Không in secret vào log hoặc dùng `kubectl get secret -o yaml` bừa bãi để đối chiếu. Base64 trong Kubernetes Secret không phải encryption. Dùng RBAC, encryption-at-rest và hệ thống quản lý secret phù hợp.

## 14. Một chỉnh sửa config có thể ảnh hưởng tới nhiều replica

Giả sử có bốn Spring Boot Pods:

~~~text
pod-a: timeout=3s
pod-b: timeout=3s
pod-c: timeout=3s
pod-d: timeout=3s
~~~

Nếu operator chỉ sửa file trên một máy/Pod hoặc chỉ refresh một process:

~~~text
pod-a: timeout=10s
pod-b: timeout=3s
pod-c: timeout=3s
pod-d: timeout=3s
~~~

Load balancer phân phối traffic tới nhiều phiên bản cấu hình, có thể tạo lỗi ngẫu nhiên khó chẩn đoán.

Một kế hoạch thay đổi cấu hình cần trả lời:

- Nguồn config chung là gì?
- Những instance nào đã nhận source mới?
- Có rollout hoặc refresh orchestration cho tất cả instance chưa?
- Có cách xác nhận mỗi instance dùng cùng phiên bản không?
- Có thể chấp nhận giai đoạn hai phiên bản cấu hình tồn tại song song không?
- Nếu không, cần maintenance, drain hoặc chiến lược đồng bộ nào?

### 14.1. Version ID không nhạy cảm

Có thể gắn một `config.version` hoặc annotation checksum không nhạy cảm vào deployment để quan sát tiến độ:

~~~yaml
app:
  config-version: "catalog-2026-11-rotation-01"
~~~

Không sử dụng giá trị version ID như một bằng chứng tuyệt đối rằng mọi field đã được bind đúng. Nó chỉ là một dấu hiệu để đối chiếu rollout, cần kết hợp với kiểm tra hành vi thật và nguồn được dùng.

### 14.2. Không in fingerprint của secret tùy tiện

Nếu version ID gắn với secret, dùng định danh không nhạy cảm do secret manager cung cấp. Tránh in hash của token/password trực tiếp vào log: với một số loại credential có entropy thấp hoặc bị đoán được, fingerprint có thể tăng rủi ro.

## 15. Restart và rolling rollout: cách dễ dự đoán nhất

Với nhiều ứng dụng Spring Boot, một mô hình đơn giản và đáng tin cậy là **mỗi phiên bản process dùng một tập cấu hình xác định**. Khi cấu hình thay đổi, tạo instance mới thay cho instance cũ.

Quy trình:

~~~text
Chuẩn bị file/env/ConfigMap/Secret mới
                  |
                  v
Kiểm tra định dạng và nguồn chính xác
                  |
                  v
Khởi động instance mới
                  |
                  v
Spring Boot đọc config data mới
                  |
                  v
Bind/validate bean, khởi tạo clients
                  |
                  v
Readiness cho instance mới
                  |
                  v
Chuyển traffic, drain instance cũ
                  |
                  v
Dừng instance cũ
                  |
                  v
Xác nhận metrics và hoàn tất rollout
~~~

### 15.1. Ưu điểm của restart

- Có một giai đoạn rõ ràng để nạp lại mọi Config Data.
- Beans được tạo theo thứ tự lifecycle đã định.
- Connection pools/clients được tạo mới từ cấu hình hiện hành.
- Cấu hình đã bind có thể được validate trước khi nhận traffic.
- Dễ rollback bằng deployment/revision nếu nguồn cấu hình phù hợp còn có thể khôi phục.
- Tránh các trạng thái refresh một phần trong một process dài hạn.

### 15.2. Nhược điểm cần quản lý

- Một restart có thể tạo downtime nếu service chỉ có một instance.
- Có thể mất in-memory state nếu ứng dụng thiết kế sai.
- Kết nối in-flight và batch jobs cần thời gian hoàn tất.
- Cần tài nguyên dự phòng nếu muốn nhiều replica chạy song song.
- Việc restart tất cả instance cùng lúc có thể gây spike tới database hoặc dịch vụ ngoài.

Vì vậy, **restart an toàn** bao gồm readiness, graceful shutdown, rolling strategy và capacity planning; không đơn giản chỉ là kill -9 rồi chạy lại.

## 16. Readiness và graceful shutdown khi rollout cấu hình

Trong Spring Boot với Actuator đã được cấu hình, có thể dùng health probes để phản ánh khả năng phục vụ. Ví dụ YAML:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kubernetes readiness probe minh họa:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Chỉ dùng đường dẫn/cổng đó nếu ứng dụng thực sự expose endpoint tương ứng và hạ tầng truy cập được. Readiness không nên phụ thuộc một cách mù quáng vào mọi dependency tùy chọn khiến một outage bên ngoài làm toàn bộ service mất khả năng phục vụ.

### 16.1. RollingUpdate

Một Deployment nhiều replica có thể dùng:

~~~yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
~~~

Ví dụ giúp hạn chế việc mất Pod ready trong rollout. Nó **không bảo đảm zero downtime tuyệt đối**, vì còn phụ thuộc số replica, tài nguyên, routing, startup duration, readiness correctness và khả năng server xử lý shutdown.

### 16.2. Graceful shutdown

Khi instance cũ bị yêu cầu dừng, nó cần ngừng nhận request mới và hoàn thành những request/transaction đang xử lý trong giới hạn cho phép.

Nếu có batch jobs/queue consumers, cần chính sách tương ứng để không mất message và tránh xử lý trùng bất hợp lệ. Có thể cần checkpoint, idempotency, retry và ack semantics của broker.

### 16.3. Readiness phải xác nhận cấu hình mới có hiệu lực ở chức năng thiết yếu

Một Pod có thể khởi động thành công dù một tích hợp tùy chọn chưa sẵn sàng. Nếu thay đổi timeout nhằm sửa lỗi với dịch vụ Catalog, việc chỉ thấy health endpoint trả 200 không chứng minh các request Catalog đã dùng timeout mới.

Nên bổ sung kiểm tra smoke test an toàn, metrics và một mã config version không nhạy cảm nếu cần.

## 17. Dynamic refresh: khi nào nên cân nhắc?

Có những yêu cầu khó chấp nhận restart: feature flags thay đổi thường xuyên, routing rules được cập nhật liên tục, một số loại token ngắn hạn hoặc một worker phải chạy liên tục.

Khi đó có thể cân nhắc **dynamic refresh**. Nhưng một giải pháp refresh đúng cần nhiều bước:

1. Phát hiện nguồn cấu hình thay đổi.
2. Nạp nội dung mới đúng schema và đúng thứ tự precedence.
3. Chuyển kiểu và validate đầy đủ.
4. Quyết định thay cấu hình thành công hay giữ bản cũ khi giá trị mới sai.
5. Cập nhật atomically các component cần đổi.
6. Rebuild clients/pools/schedulers nếu chúng copy giá trị vào cấu trúc riêng.
7. Đồng bộ nhiều threads và nhiều instances.
8. Ghi nhận phiên bản, metric và rollback.

Spring Boot thuần **không tự cung cấp một cơ chế tổng quát** để hot reload mọi dạng `application.yml` và mọi singleton. Cần thư viện bổ sung hoặc code ứng dụng được thiết kế tường minh.

### 17.1. Spring Cloud @RefreshScope không phải toàn bộ Spring Boot

Trong một số hệ sinh thái Spring Cloud, có cơ chế refresh context/bean, chẳng hạn `@RefreshScope`. Nhưng:

- `@RefreshScope` không phải annotation mặc định của Spring Boot Core.
- Không phải mọi bean đều thuộc refresh scope.
- Không phải mọi client/pool được rebuild khi một properties bean đổi.
- Có thể có hành vi đặc biệt với immutable configuration properties và phiên bản library.
- Endpoint thực hiện refresh, nếu có, cần bảo vệ quyền truy cập.
- Một refresh thành công ở một instance không tự bảo đảm các instance khác đồng bộ.

Do đó, không nên viết “thêm @RefreshScope là tự reload application.yml” như một quy tắc chung. Phải test cách nguồn được làm mới, bean nào được tạo lại và giá trị nào cuối cùng được sử dụng.

### 17.2. File watcher tùy chỉnh

Một nhóm có thể dùng `WatchService` của Java hoặc polling để nhận sự kiện file đổi. Điều đó mới giải quyết lớp **phát hiện thay đổi**.

Nếu muốn sử dụng cấu hình mới, phần sau còn phải:

- Đọc snapshot file đầy đủ, tránh đọc giữa lúc ghi dở.
- Parse theo đúng format YAML/properties.
- Xác định precedence với các nguồn khác.
- Validate trước khi publish.
- Đổi cấu hình atomically và thông báo các consumers.
- Bảo vệ quyền đọc và log, nhất là file chứa secret.
- Xử lý mất event, đổi symlink hoặc atomic file replacement.

Đối với ConfigMap/Secret volume trên Kubernetes, cơ chế atomic writer có thể thay file/symlink thay vì chỉ thay bytes tại inode cũ. Một watcher chỉ theo dõi sự kiện ghi lên một file handle cố định có thể bỏ lỡ cập nhật. Polling/reopen theo đường dẫn và kiểm thử trên môi trường thật thường cần thiết.

### 17.3. Không dùng @Scheduled để bind lại bừa bãi

Một task đọc file mỗi giây rồi thay các property của bean mà không đồng bộ có thể làm threads nhìn thấy cấu hình **nửa cũ nửa mới**. Ví dụ `timeout` từ bản mới nhưng `endpoint` từ bản cũ, hoặc một connection pool mới và auth header cũ cùng tồn tại.

Một phương án tốt hơn có thể là một immutable config snapshot đã được validate toàn bộ, sau đó publish atomically bằng `AtomicReference<ConfigSnapshot>` cho các nơi chủ động đọc snapshot. Đây là thiết kế ứng dụng riêng, không phải cách Binding `@ConfigurationProperties` mặc định.

## 18. Ví dụ thiết kế snapshot động có kiểm soát

Giả sử chỉ có một policy đơn giản cần cập nhật thường xuyên, không phải tất cả Spring Boot application settings.

~~~java
package com.example.routing;

import java.time.Duration;

public record RoutingPolicy(
        boolean enabled,
        Duration timeout
) {
    public RoutingPolicy {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "Routing timeout phải lớn hơn 0");
        }
    }
}
~~~

Store snapshot:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class RoutingPolicyStore {

    private final AtomicReference<RoutingPolicy> current =
            new AtomicReference<>(
                    new RoutingPolicy(true, Duration.ofSeconds(3))
            );

    public RoutingPolicy get() {
        return current.get();
    }

    public void replace(RoutingPolicy next) {
        if (next == null) {
            throw new IllegalArgumentException("Policy không được null");
        }
        current.set(next);
    }
}
~~~

Một component đọc `store.get()` cho mỗi quyết định sẽ nhìn thấy toàn bộ snapshot cũ hoặc mới, không bị pha hai field giữa các lần replace. Tuy nhiên:

- Đây mới là **cách publish snapshot**, chưa phải file loader.
- File reader cần parse và validate snapshot mới trước khi gọi `replace`.
- Nếu một HTTP client đã được build với timeout cũ, nó không tự thay theo store.
- Nhiều replica cần cùng nhận phiên bản và ghi nhận trạng thái.
- Cần chính sách nếu file mới sai, lỗi đọc hoặc update chỉ thành công một phần.

Thiết kế snapshot động thích hợp khi thực sự có yêu cầu thay đổi policy nhiều lần, còn với cấu hình database/password/HTTP connection pool, rolling restart thường đơn giản hơn.

## 19. Cấu hình thay đổi giữa lúc ứng dụng đang chạy: ba loại hành vi

Một cách phân loại thực tế:

### Loại A — Startup-only

Ví dụ: datasource URL, database password cho pool, port server, một số logging bootstrap settings, endpoint để xây dựng client.

Đặc điểm:

- Được đọc để tạo component.
- Component thường giữ giá trị đến hết vòng đời.
- Restart/rebuild là con đường rõ ràng để áp dụng thay đổi.
- Cần runbook rollout và rollback.

### Loại B — Runtime lookup

Ví dụ một service tự đọc `Environment.getProperty(...)` mỗi lần sử dụng.

Đặc điểm:

- Nếu PropertySource trong `Environment` **thực sự** được cập nhật, một lần tra cứu sau có thể nhận value mới.
- Nếu chỉ sửa file YAML mà không cập nhật PropertySource, vẫn nhận value cũ.
- Có thể gặp vấn đề chuyển kiểu, consistency và hiệu năng nếu tự xử lý nhiều property.
- Không nên coi runtime lookup là một cơ chế cấu hình động đầy đủ.

### Loại C — Explicit dynamic configuration

Ví dụ feature flag service, remote config client, application-specific policy store có refresh và versioning.

Đặc điểm:

- Có vòng đời fetch/cache/reload rõ.
- Có validation, atomic publication và rollback.
- Có thể đồng bộ các replica.
- Phải test concurrent reads và failure modes.
- Tăng chi phí vận hành và bảo mật.

Chọn loại theo nhu cầu của property, thay vì dùng một phương án cho mọi cấu hình trong ứng dụng.

## 20. Cách thay đổi file an toàn

Ngay cả khi **bắt buộc restart**, cách sửa file vẫn quan trọng. Một file YAML sai định dạng có thể khiến tất cả instance mới fail startup.

### 20.1. Tránh ghi dở file đang được đọc

Nếu operator hoặc tool ghi trực tiếp vào file đang dùng, một lần khởi động trùng lúc ghi có thể đọc file chưa hoàn chỉnh. Khi phù hợp, có thể sử dụng phương thức tạo file tạm, kiểm tra và **atomic replacement** trên cùng filesystem; cần biết semantics của mount và filesystem thực tế.

Không phải mọi filesystem hoặc mount hỗ trợ cùng cách rename. Khi config do Kubernetes quản lý, sử dụng cơ chế của nền tảng thay vì tự thao tác bên trong Pod.

### 20.2. Bảo đảm YAML hợp lệ

Ví dụ đúng:

~~~yaml
catalog:
  client:
    enabled: true
    timeout: 10s
~~~

Ví dụ sai về indentation có thể dẫn tới key khác hoặc parse error:

~~~yaml
catalog:
  client:
  enabled: true
  timeout: 10s
~~~

Cả hai có thể là YAML hợp lệ về cú pháp, nhưng bản thứ hai có cấu trúc **khác dự kiến**, có thể khiến `catalog.client.enabled` và `catalog.client.timeout` bị thiếu.

Vì vậy, kiểm tra parse YAML là chưa đủ; cần test binding vào class cấu hình và validation của những key bắt buộc.

### 20.3. Một nguồn có thể chứa nhiều documents

File `application.yml` hỗ trợ `---` để tách documents, và `spring.config.activate.on-profile` quyết định documents có hiệu lực theo active profile.

Ví dụ:

~~~yaml
catalog:
  client:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod

catalog:
  client:
    timeout: 10s
~~~

Nếu profile `prod` không active, sửa document `prod` chưa chắc tác động tới lần restart hiện tại. Ngược lại, active profile khác hoặc CLI override còn có thể dẫn đến giá trị cuối khác cả hai documents.

## 21. Validation lúc startup là hàng rào chống cấu hình sai

Một record có kiểu:

~~~java
package com.example.catalog.config;

import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "catalog.client")
@Validated
public record CatalogClientProperties(
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

`@NotNull` giúp phát hiện thiếu giá trị, nhưng không tự bảo đảm timeout dương. Có thể thêm invariant:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        boolean enabled
) {
    public CatalogClientProperties {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "catalog.client.timeout phải lớn hơn 0");
        }
    }
}
~~~

Hai ví dụ trên là **hai cách khác nhau** minh họa validation; trong project thực cần chọn một class thống nhất và cơ chế validator phù hợp.

### 21.1. Startup validation và rollout

Khi triển khai cấu hình mới:

1. Có một nguồn cấu hình mới.
2. Tạo instance mới để Boot nạp nguồn.
3. Bind và validate trước khi phục vụ.
4. Nếu giá trị sai, startup của instance mới có thể fail.
5. Instance cũ, nếu vẫn còn và đang healthy, có thể tiếp tục phục vụ theo rolling strategy.

Đây là một ưu điểm của rolling restart so với chỉnh một singleton đang sống: bản mới có một **điểm kiểm tra** trước khi nhận traffic.

### 21.2. Không sử dụng default nguy hiểm

Một default như `spring.datasource.password=test123` hoặc endpoint sandbox trong production có thể che giấu lỗi cấp cấu hình. Chỉ dùng default khi nó thật sự an toàn và đúng nghiệp vụ.

Với những property bắt buộc, nên fail fast nếu thiếu thay vì âm thầm chạy với giá trị không phù hợp.

## 22. Kiểm thử: chứng minh cấu hình được đọc lúc nào

### 22.1. Test thuộc tính đã bind

Có thể dùng `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void timeoutComesFromStartupProperties() {
        runner.withPropertyValues(
                "catalog.client.timeout=3s",
                "catalog.client.enabled=true"
        ).run(context -> {
            CatalogClientProperties props =
                    context.getBean(CatalogClientProperties.class);

            assertThat(props.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
        });
    }
}
~~~

Giả sử `Duration` được import và class `CatalogClientProperties` phù hợp. Test này xác nhận Binder với test properties, **chưa** chứng minh một file Config Data bên ngoài được nạp hoặc hot reload.

### 22.2. Test đúng pipeline Config Data

Để kiểm tra `application.yml`, profile activation hoặc `spring.config.import`, cần dùng một test context chạy đúng cơ chế Config Data, chẳng hạn `@SpringBootTest` với config files và active profile tương ứng.

Không chỉ tự parse YAML rồi khẳng định app đã nạp. Một parser unit test và một Boot startup integration test kiểm tra những điều khác nhau.

### 22.3. Test “sửa file khi JVM đang chạy”

Một test integration có kiểm soát:

1. Tạo file cấu hình ở location tạm với `timeout=3s`.
2. Khởi động một Spring Boot context có nạp file này.
3. Đọc bean và xác nhận `3s`.
4. Sửa file thành `10s` **không restart context**.
5. Đọc lại bean; thông thường vẫn là `3s` nếu không có refresh.
6. Dừng context rồi khởi tạo context mới với location đó.
7. Đọc bean mới; mong đợi `10s` nếu nguồn đã được nạp và không bị override.

Test này trực tiếp phân biệt **filesystem update** và **lifecycle rebind**.

### 22.4. Test client đã cấu hình

Thêm test một client được khởi tạo với timeout 3s, sau đó đổi nguồn thành 10s. Đừng chỉ assert thuộc tính trong `Environment`; kiểm tra client thực sự dùng policy mới sau restart hoặc rebuild. Điều này bắt được lỗi “properties đã đổi nhưng thành phần tiêu thụ vẫn cũ”.

### 22.5. Test nhiều replica

Trong một sandbox Kubernetes:

- Dùng ConfigMap test, không có secret thật.
- Cấp cấu hình qua env hoặc volume.
- Đổi ConfigMap khi Pods chạy.
- Quan sát file mount, environment và hành vi endpoint demo.
- Trigger rollout có kiểm soát.
- Xác nhận tất cả Pods mới dùng cùng giá trị.
- Kiểm thử rollback config và readiness khi một giá trị mới sai.

Không thực hiện phép thử này trên production đang phục vụ người dùng.

## 23. Runbook mẫu: đổi timeout ngoài JAR trên một VM

**Bối cảnh:** ứng dụng chạy một JAR và đọc `./config/application.yml` trong working directory đã xác định.

### Chuẩn bị

- Xác nhận đường dẫn file thật, working directory và service manager.
- Xác nhận key cần đổi là `catalog.client.timeout`.
- Xác nhận không có CLI/env/source ưu tiên hơn override.
- Sao lưu file trước khi sửa theo quy trình quản trị được phép.
- Xác định thời gian restart và mức ảnh hưởng.
- Chuẩn bị rollback nếu cấu hình mới không phù hợp.

### Thay đổi

1. Sửa `catalog.client.timeout` từ `3s` thành `10s`.
2. Kiểm tra cú pháp và format.
3. Dùng staging/validation nếu có để phát hiện binding error.
4. Khởi động lại service theo đúng service manager (systemd, Docker hoặc orchestrator).
5. Theo dõi startup logs, readiness, business metrics.
6. Xác nhận **hành vi timeout thực tế** hoặc một phép đo an toàn, không chỉ xem file đã sửa.
7. Nếu có lỗi, khôi phục file trước và restart theo quy trình.

### Không nên làm

- Sửa file rồi báo “đã áp dụng” mà không restart/refresh.
- Sửa nhầm file `src/main/resources/application.yml` trong source trong khi tiến trình đang dùng JAR đã build.
- Thay cùng lúc nhiều tham số không liên quan.
- Dùng log chứa toàn bộ Environment để tìm nguồn thắng.
- Restart một cách thiếu kiểm soát trên hệ thống chưa có chính sách drain/backup.

## 24. Runbook mẫu: đổi cấu hình trên Kubernetes

**Bối cảnh:** Spring Boot Deployment có nhiều replicas, cấu hình cấp qua ConfigMap.

### Xác định đường cấp

- **Env var:** Pod đang chạy giữ giá trị cũ, cần Pod mới.
- **Volume mount:** file có thể cập nhật eventual, nhưng bean/client không tự đổi.
- **subPath:** không trông chờ nội dung mount tự đổi theo ConfigMap.
- **spring.config.import/configtree:** file được đưa vào Config Data khi startup, không phải watcher tự động.

### Các bước triển khai

1. Review thay đổi ConfigMap/manifest và schema cấu hình.
2. Xác nhận nguồn chính xác, namespace và key.
3. Cập nhật ConfigMap bằng pipeline/CI/GitOps được phê duyệt.
4. Nếu dùng controller đồng bộ từ external config, chờ controller xác nhận nguồn hiện hành đã được đồng bộ.
5. Kích hoạt rolling rollout bằng thay đổi Pod template/checksum annotation hoặc thao tác restart được phép.
6. Chờ Pods mới ready; theo dõi số replicas cũ/mới.
7. Chạy smoke test an toàn ở đường nghiệp vụ cần cấu hình mới.
8. Xác nhận metrics và version ID không nhạy cảm trên tất cả instance.
9. Hoàn tất rollout và ghi nhận trạng thái.
10. Khi cần rollback, khôi phục **cả bản cấu hình** và **Pod rollout**, không chỉ quay lại image cũ.

### 24.1. Tại sao checksum annotation thường được sử dụng?

Trong các hệ thống templating/GitOps, Pod template có thể chứa một annotation thay đổi khi nội dung ConfigMap thay đổi. Vì Deployment tạo rollout khi Pod template thay đổi, điều này giúp kết nối **thay source cấu hình** với **tạo Pod mới**.

Tuy nhiên, annotation chỉ là một cơ chế trigger rollout. Nó không chứng minh ConfigMap đã được cập nhật đúng ở nơi mong muốn hoặc app đã bind value đúng. Cần kiểm tra cả source và hành vi runtime.

### 24.2. Tránh mất đồng bộ khi Secret/ConfigMap cập nhật chậm

Nếu nhiều hệ thống quản lý config cùng tham gia (secret manager, external-secrets controller, GitOps, Helm, Deployment), cần biết thứ tự từng bước. Kích hoạt restart trước khi secret/config được đồng bộ xong có thể khiến Pod mới lấy lại giá trị cũ.

Một runbook phải chỉ rõ điều kiện “nguồn đã phân phối xong” **trước** “trigger rollout”.

## 25. Dynamic refresh và an toàn khi thay đổi nửa chừng

Nếu ứng dụng buộc phải hot reload, cần thêm chính sách lỗi:

### 25.1. File mới không hợp lệ

Ví dụ file sửa từ:

~~~yaml
routing:
  timeout: 3s
  enabled: true
~~~

thành:

~~~yaml
routing:
  timeout: nonsense
  enabled: true
~~~

Một cơ chế reload tốt nên **từ chối snapshot mới không hợp lệ** và giữ policy cũ hoặc chuyển sang trạng thái lỗi đã định nghĩa, thay vì publish một object chỉ cập nhật một phần.

### 25.2. Hai field phải được cập nhật cùng nhau

Nếu `routing.endpoint` và `routing.api-key-ref` là một cặp khớp nhau, refresh riêng từng property có thể tạo cặp endpoint mới + key cũ. Đây có thể là lỗi bảo mật hoặc lỗi nghiệp vụ.

Nên xem **cấu hình là một versioned snapshot**, validate toàn bộ quan hệ trước khi publish.

### 25.3. Clients đang có request in-flight

Nếu một request đã bắt đầu dùng config phiên bản A, giữa request hệ thống cập nhật B, việc đổi client hoặc credentials ngay có thể làm request thấy trạng thái không nhất quán. Một thiết kế refresh chuyên nghiệp cần quy tắc lifecycle: giữ A cho request đang chạy, tạo client B cho request mới, đóng A sau khi drain hoặc timeout.

### 25.4. Rollback cần lưu bản hợp lệ trước

Chỉ lưu mỗi file hiện tại mà không có revision history khiến rollback khó khăn. Có thể dùng GitOps, deployment revision hoặc config store có versioning. Không nên tự ghi bí mật vào Git để có lịch sử; đối với secrets, dùng secret manager và policy quản trị phiên bản tương ứng.

## 26. Các lỗi hiểu nhầm thường gặp

| Phát biểu sai hoặc chưa đủ | Cách hiểu đúng |
| --- | --- |
| “File đổi rồi nên app đã đổi.” | File đổi chỉ chứng minh source trên đĩa đã đổi |
| “Externalized config có nghĩa hot reload.” | Externalized và dynamic reload là hai tính năng khác |
| “Record immutable, JavaBean mutable nên JavaBean tự cập nhật.” | Mutable JavaBean vẫn cần rebind/recreation |
| “Environment lúc nào cũng đọc lại application.yml.” | Config Data được nạp theo lifecycle, không mặc định watcher |
| “Đổi PropertySource là tất cả beans đổi.” | Beans/clients có thể giữ snapshot cũ |
| “@Value sẽ tra Environment mỗi lần method gọi.” | Field/constructor injection thường giải quyết khi bean được tạo |
| “spring.config.import có optional nghĩa tự reload.” | optional chỉ xử lý location thiếu |
| “ConfigMap đổi là Deployment tự rollout.” | Cần trigger rollout/Pod template thay đổi khi cần |
| “ConfigMap volume cập nhật tức thì.” | Thường eventual; subPath có giới hạn |
| “File mount cập nhật nên @ConfigurationProperties tự bind lại.” | Không mặc định |
| “@RefreshScope giải quyết mọi bean.” | Phụ thuộc Spring Cloud, phạm vi bean và resource client |
| “Restart JAR cũ đọc YAML source mới.” | Embedded resource vẫn thuộc artifact cũ |
| “CLI/env không ảnh hưởng file.” | Precedence có thể override giá trị của file |
| “Health trả 200 chứng minh timeout mới đã dùng.” | Cần kiểm tra chức năng hoặc hiệu lực của config |
| “Rollback image là rollback config.” | Cần khôi phục config source và version tương ứng |

## 27. Bài tập thực hành

### Bài tập A — File trong JAR và ngoài JAR

Tạo hai cấu hình có cùng key `lesson.timeout`:

~~~yaml
lesson:
  timeout: 3s
~~~

Đóng gói JAR với bản mặc định, chạy với một file ngoài JAR chứa `10s`. Quan sát precedence. Sửa file source trong `src/main/resources` sau khi JAR build, kiểm tra giá trị của tiến trình và giải thích vì sao không tự đổi.

### Bài tập B — Sửa file khi ứng dụng đang chạy

Tạo record:

~~~java
@ConfigurationProperties(prefix = "lesson")
public record LessonProperties(Duration timeout) {}
~~~

Chạy với file ngoài JAR `timeout=3s`. Sửa thành `10s` khi JVM đang chạy. Quan sát bean trước/sau sửa và sau restart. Ghi lại ba giá trị khác nhau: nội dung file, value trong `Environment` và `LessonProperties`.

### Bài tập C — Runtime PropertySource

Tạo một test context có `lesson.timeout=3s`. Sau khi bean đã bind, thêm `MapPropertySource` ưu tiên cao với `lesson.timeout=10s`. So sánh:

- `environment.getProperty("lesson.timeout")`.
- `lessonProperties.timeout()`.
- Client đã được tạo dựa trên timeout ban đầu.

Giải thích tại sao kết quả có thể khác nhau.

### Bài tập D — ConfigMap env vs volume

Trong một Kubernetes sandbox, cấp cùng một key cấu hình thử nghiệm từ ConfigMap qua env và qua volume. Sửa ConfigMap khi Pod chạy. Theo dõi:

1. Process environment.
2. Nội dung file mount.
3. Bean Spring Boot đã bind.
4. Behavior sau khi Pod được tạo lại.

Không dùng secret production trong bài tập.

### Bài tập E — Trường hợp subPath

Mount file ConfigMap qua `subPath` rồi sửa ConfigMap. So sánh với mount volume thông thường, giải thích vì sao không thể dựa vào subPath cho hot reload tự động.

### Bài tập F — Precedence khi restart

File ngoài JAR có `lesson.timeout=10s` nhưng CLI cấp `--lesson.timeout=2s`. Restart JVM. Dự đoán timeout và nêu nguyên nhân nếu ứng dụng vẫn dùng `2s`.

### Bài tập G — File watcher chưa đủ

Tạo một watcher phát hiện `application.yml` thay đổi. Liệt kê từng bước còn phải làm để hỗ trợ reload an toàn: parse, conversion, validation, atomic publish, component reconstruction, multi-replica synchronization và rollback.

### Bài tập H — Lập runbook rollout

Một Deployment có bốn Pods sử dụng ConfigMap cho client timeout. Hãy viết quy trình: cập nhật ConfigMap, chờ sync, trigger rolling restart, kiểm tra readiness, smoke test, xác nhận version và rollback. Giải thích vì sao không nên restart cả bốn Pods cùng lúc.

### Bài tập I — Cấu hình sai trong lần restart

Đặt `lesson.timeout=not-a-duration`. Dự đoán Binder có thể báo conversion error khi context mới startup. Thiết kế cách giữ hệ thống cũ phục vụ trong rolling rollout nếu Pod mới không ready.

### Bài tập J — Secret thay đổi

Một ứng dụng dùng token từ Secret file trong `configtree`. Secret mount nhận bản mới nhưng bean token vẫn là bản cũ. Nêu cách chuyển tiếp an toàn và thời điểm nên thu hồi secret cũ. Không log token thật để xác nhận.

## 28. Checklist triển khai thay đổi file cấu hình

### Trước khi thay đổi

- [ ] Xác định file/source cấu hình **thật sự được nạp** và working directory.
- [ ] Xác định property key, active profiles và thứ tự precedence.
- [ ] Xác định nguồn nằm trong JAR hay ngoài JAR.
- [ ] Xác định Env/ConfigMap/Secret/configtree/import và thời điểm nạp.
- [ ] Biết thành phần nào giữ value đã bind và client nào cần rebuild.
- [ ] Chọn rõ restart, rolling rollout hoặc refresh động.
- [ ] Có schema/binding/validation tests cho giá trị mới.
- [ ] Có kế hoạch bảo vệ secret và không log dữ liệu nhạy cảm.
- [ ] Xác định số instance, readiness, graceful shutdown và rollback.

### Khi áp dụng

- [ ] Thay file/source bằng quy trình an toàn, không ghi dở.
- [ ] Xác nhận cấu hình đã được phân phối tới đúng môi trường.
- [ ] Trigger restart/rollout nếu đó là cơ chế đã chọn.
- [ ] Quan sát startup và lỗi binding/validation.
- [ ] Chờ instance mới ready trước khi chuyển traffic.
- [ ] Kiểm tra hành vi chức năng và metrics, không chỉ xem file.
- [ ] Xác nhận mọi replica đã nhận đúng version.
- [ ] Theo dõi hiệu ứng với clients, pools, schedulers và credential.
- [ ] Khi rollback, khôi phục cả config source và deployment state.

### Sau thay đổi

- [ ] Lưu lại thời điểm, owner và version cấu hình.
- [ ] Xác nhận không còn Pod/instance cũ ngoài cửa sổ chuyển tiếp.
- [ ] Ghi nhận các lần fail/startup lỗi và cách xử lý.
- [ ] Rà soát log/Actuator không lộ secret.
- [ ] Cập nhật tài liệu vận hành nếu cơ chế refresh/restart thay đổi.

## 29. Kết luận

**Sửa file sau khi ứng dụng đã chạy không tương đương khởi động lại Spring Boot.** File chỉ là một đầu vào. Spring Boot đã có thể đọc file để xây dựng `Environment`, bind `@ConfigurationProperties`, inject `@Value` và tạo clients/pools trong lần khởi động.

Đối với những ứng dụng không có refresh được thiết kế riêng, **cách dễ dự đoán là thay cấu hình rồi tạo lại tiến trình** bằng restart hoặc rolling rollout có readiness và graceful shutdown. Nếu cần thay đổi ngay khi đang chạy, phải xây dựng cả một cơ chế **phát hiện → nạp lại → validate → publish → rebuild/refresh consumers → quan sát → rollback**, không chỉ gắn file watcher.

Ba câu hỏi kiểm tra sau mỗi lần đổi cấu hình:

1. **Nguồn nào đã đổi?** File ngoài JAR, env, ConfigMap/Secret, configtree hay một nguồn khác?
2. **Tiến trình đã đọc lại chưa?** Có restart/rebind/refresh được xác nhận không?
3. **Thành phần sử dụng đã đổi chưa?** Bean, HTTP client, connection pool và mọi replica có đang dùng giá trị mới không?

Trả lời được cả ba mới có cơ sở nói rằng thay đổi cấu hình **đã có hiệu lực**, thay vì chỉ xác nhận “file đã được sửa”.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): các nguồn cấu hình, precedence, config data, external file locations và imports.
- [Spring Boot Reference — Config Data Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): classpath/external locations và profile-specific configuration.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import` và config tree imports.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Binder, bean lifecycle, immutable và mutable property objects.
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): cách dừng web server có kiểm soát.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness trong triển khai Kubernetes.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): truy vấn property trong Spring `Environment`.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): cấp cấu hình bằng environment và volumes, cập nhật mounted ConfigMaps.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret env/volume, cập nhật eventual và giới hạn `subPath`.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate và rollout strategies.
- [Spring Cloud Commons — Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope): cơ chế refresh chuyên biệt khi ứng dụng thực sự tích hợp Spring Cloud.
