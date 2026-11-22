# Quản lý contributor qua management.info và cấu hình mặc định

## 1. Contributor là gì và vì sao cần quản lý?

Endpoint `info` trả về thông tin mô tả ứng dụng, chẳng hạn phiên bản bản dựng, mã commit hoặc tên dịch vụ. Mỗi bộ phận cung cấp một phần dữ liệu được gọi là bộ đóng góp thông tin (`InfoContributor`). Endpoint tập hợp dữ liệu từ các bean này để tạo phản hồi.

Ví dụ, đội vận hành muốn biết ứng dụng đang chạy có đúng bản vừa triển khai hay không. Thông tin `build` và `git` có ích cho việc đối chiếu; thông tin hệ điều hành hay tiến trình có thể không cần công bố. Quản lý contributor giúp chọn dữ liệu phù hợp thay vì đưa mọi thông tin kỹ thuật ra cùng một endpoint.

Cần phân biệt ba loại tên:

- `info` là ID của endpoint.
- `env`, `build`, `git`, `java`, `os`, `process` là ID của các contributor có sẵn trong Spring Boot 3.3.x.
- `app`, `release` hoặc những khóa khác trong JSON là tên dữ liệu được đóng góp. Chúng không mặc nhiên là ID contributor.

Chẳng hạn, `EnvironmentInfoContributor` có ID `env` nhưng đọc `info.app.name` và tạo khóa `app` trong phản hồi. Muốn bật nguồn dữ liệu này phải dùng `management.info.env.enabled`; đặt `management.info.app.enabled` không điều khiển nó. [API EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html)

Bài này tập trung vào Spring Boot **3.3.x**. Ví dụ tối thiểu dùng 3.3.0; không suy rộng danh sách contributor hay thuộc tính của phiên bản mới hơn sang nhánh này.

## 2. Ba lớp cấu hình phải được hiểu riêng

Để lấy dữ liệu qua HTTP, cần lần lượt xét endpoint, khả năng truy cập và nguồn dữ liệu:

| Lớp cấu hình | Thuộc tính tiêu biểu | Câu hỏi được giải quyết |
| --- | --- | --- |
| Bật endpoint | `management.endpoint.info.enabled` | Endpoint `info` có được bật không? |
| Mở endpoint qua HTTP | `management.endpoints.web.exposure.include` | Có công bố endpoint này qua web không? |
| Chọn contributor | `management.info.<id>.enabled` | Nguồn thông tin nào được tự động cấu hình? |

Spring Boot 3.3 bật endpoint `info` theo mặc định, nhưng chỉ mở `health` qua HTTP theo mặc định. Cấu hình contributor không tự mở đường dẫn HTTP. Ngoài ba lớp trên, quy tắc Spring Security hoặc hạ tầng mạng còn có thể giới hạn người được truy cập. [Bật và mở endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

Hai cấu hình sau giải quyết hai việc khác nhau:

```properties
management.endpoints.web.exposure.include=health,info
management.info.java.enabled=true
```

Dòng đầu công bố endpoint; dòng sau bổ sung nguồn dữ liệu Java. Nếu chỉ có dòng đầu, endpoint vẫn có thể trả `{}`. Nếu chỉ có dòng sau, dữ liệu Java có thể được chuẩn bị nhưng endpoint chưa được công bố qua HTTP.

Không nhầm `management.endpoint.info.enabled` với `management.info.enabled`. Thuộc tính thứ hai không phải công tắc chung cho endpoint này trong Spring Boot 3.3.

## 3. Mặc định của từng contributor trong Spring Boot 3.3.x

| ID | Thuộc tính bật/tắt riêng | Khi không đặt thuộc tính riêng | Điều kiện hoặc nguồn dữ liệu |
| --- | --- | --- | --- |
| `build` | `management.info.build.enabled` | Được phép bật theo mặc định chung | Thông thường cần `META-INF/build-info.properties` để tạo `BuildProperties` |
| `git` | `management.info.git.enabled` | Được phép bật theo mặc định chung | Thông thường cần `git.properties` ở gốc classpath để tạo `GitProperties` |
| `env` | `management.info.env.enabled` | Tắt | Đọc các thuộc tính có tiền tố `info.` từ Spring Environment |
| `java` | `management.info.java.enabled` | Tắt | Thông tin môi trường Java |
| `os` | `management.info.os.enabled` | Tắt | Thông tin hệ điều hành |
| `process` | `management.info.process.enabled` | Tắt | Thông tin tiến trình |

Các giá trị mặc định này được liệt kê trong [danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

“Được phép bật” không đồng nghĩa “chắc chắn có dữ liệu”. Việc tạo contributor `build` hoặc `git` còn phụ thuộc bean dữ liệu tương ứng. Tệp metadata là cách thông thường để cơ chế tự động cấu hình tạo những bean ấy.

Ví dụ:

```properties
management.info.build.enabled=true
```

Dòng này không chạy tác vụ sinh metadata, không tạo tệp `build-info.properties` và không đọc phiên bản trong tệp build thay cho metadata còn thiếu. Tương tự, bật `git` không khiến ứng dụng tự chạy lệnh Git trong thư mục làm việc.

Vì vậy, khi `build` và `git` không có đầu vào, còn bốn contributor kia vẫn tắt, phản hồi `{}` là kết quả hợp lệ. Nó chưa đủ để kết luận Actuator bị hỏng.

## 4. management.info.defaults.enabled thực sự làm gì?

### 4.1. Thuộc tính riêng được xét trước

Với `build` và `git`, cách quyết định có thể diễn giải như sau:

```text
Có đặt management.info.<id>.enabled?
  Có   -> dùng giá trị true/false riêng.
  Không -> xét management.info.defaults.enabled.
           Không đặt defaults -> mặc định chung là true.

Sau đó vẫn phải đáp ứng điều kiện tạo bean và có dữ liệu thích hợp.
```

Với `env`, `java`, `os`, `process`, nếu không đặt thuộc tính riêng thì chúng vẫn tắt. Chúng không dùng mặc định chung để tự bật.

Do đó:

```yaml
management:
  info:
    defaults:
      enabled: true
```

không có nghĩa là bật cả sáu contributor. Trong ứng dụng không có tùy chỉnh khác, nó giữ cơ chế mặc định cho `build` và `git`; bốn nguồn còn lại vẫn phải được bật riêng.

### 4.2. false không phải lệnh cấm mọi contributor

Xét cấu hình:

```yaml
management:
  info:
    defaults:
      enabled: false
    git:
      enabled: true
    env:
      enabled: true
```

Kết quả:

- `build` không được bật theo mặc định chung nữa.
- `git` được bật riêng, nhưng vẫn cần `GitProperties`.
- `env` được bật riêng và sẽ đọc dữ liệu `info.*`.
- `java`, `os`, `process` vẫn tắt vì chưa được bật riêng.

Bảng sau giả sử các bean dữ liệu build/git cần thiết đều có sẵn và ứng dụng không tự thay thế contributor:

| Cấu hình | build | git | env/java/os/process |
| --- | --- | --- | --- |
| Không đặt thuộc tính nào trong `management.info` | Bật | Bật | Tắt |
| Chỉ đặt `defaults.enabled=true` | Bật | Bật | Tắt |
| Chỉ đặt `defaults.enabled=false` | Tắt | Tắt | Tắt |
| `defaults.enabled=false`, `git.enabled=true` | Tắt | Bật | Tắt |
| `defaults.enabled=true`, `git.enabled=false` | Bật | Tắt | Tắt |
| `defaults.enabled=false`, `java.enabled=true` | Tắt | Tắt | Chỉ Java bật |

Điểm cần nhớ là **giá trị riêng thắng mặc định chung; điều kiện đầu vào vẫn phải thỏa mãn**. Đây là hai bước khác nhau.

### 4.3. Contributor tự viết cần điều kiện của chính nó

Các thuộc tính trên được đọc bởi cơ chế cấu hình có điều kiện. Chúng không phải bộ lọc xóa mọi bean `InfoContributor` khỏi Spring context.

Nếu ứng dụng tự khai báo một bean `InfoContributor` không kèm điều kiện, đặt `management.info.defaults.enabled=false` không tự loại bean đó. Tương tự, thêm `management.info.release.enabled=false` cũng không có tác dụng với một bean tự viết nếu không có đoạn cấu hình nào đọc thuộc tính này.

Không nên hiểu đây là cơ chế bật/tắt trực tiếp lúc ứng dụng đang chạy. Trong ví dụ cấu hình điều kiện, các bean được quyết định khi tạo Spring context; sau khi sửa cấu hình cần khởi động lại ứng dụng để kiểm chứng.

## 5. Thực hành tối thiểu: bật env và quan sát dữ liệu

### 5.1. Chuẩn bị ứng dụng độc lập

Ví dụ là một dự án Gradle nhỏ để chạy riêng với **JDK 21 và Gradle 8.5**, có kết nối đến kho dependency. Không thêm Spring Security hay contributor tự viết trong bước này. Các tệp dưới đây tạo thành ví dụ hoàn chỉnh; không chép nguyên tệp build này để thay build của một module có sẵn.

Tệp `settings.gradle`:

```groovy
rootProject.name = 'info-contributor-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Tệp `src/main/java/example/infodemo/InfoDemoApplication.java`:

```java
package example.infodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.yml`:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: "info-contributor-demo"
    description: "Ung dung minh hoa contributor"
```

Trong YAML:

- `management.info.env.enabled` quyết định có tạo nguồn đọc Environment hay không.
- `info.app.*` là dữ liệu cần công bố.
- `defaults.enabled=false` giúp bài thực hành không phụ thuộc việc classpath có thêm metadata build/git.
- Chuỗi dữ liệu minh họa cố ý cố định để có thể dự đoán phản hồi.

### 5.2. Chạy và kiểm tra

Từ thư mục dự án, chạy:

```shell
gradle bootRun
```

Giữ ứng dụng chạy, mở terminal khác rồi gọi:

```shell
curl -s http://localhost:8080/actuator/info
```

Nếu dùng Windows PowerShell có alias `curl`, dùng `curl.exe` thay cho `curl` để chạy đúng chương trình curl.

Với đúng ứng dụng tối thiểu này, phản hồi có HTTP 200 và phần thân tương đương dưới đây. JSON được xuống dòng để dễ đọc; không dựa vào thứ tự khóa hay khoảng trắng của JSON:

```json
{
  "app": {
    "name": "info-contributor-demo",
    "description": "Ung dung minh hoa contributor"
  }
}
```

Khóa đầu ra là `app`, không phải `env`. Tên contributor thể hiện nguồn dữ liệu; tên khóa thể hiện cấu trúc dữ liệu mà nguồn đó đóng góp.

### 5.3. Tắt nguồn dữ liệu nhưng giữ endpoint

Dừng ứng dụng, sau đó chạy lại với thuộc tính dòng lệnh:

```shell
gradle bootRun --args='--management.info.env.enabled=false'
```

Gọi lại cùng URL. Với điều kiện bài thực hành chưa thêm contributor khác, HTTP vẫn là 200 và phần thân là:

```json
{}
```

Endpoint vẫn tồn tại; chỉ nguồn dữ liệu đã bị tắt. Đây là cách phân biệt một phản hồi rỗng hợp lệ với lỗi truy cập endpoint.

### 5.4. Bật mặc định chung không tự bật env

Dừng ứng dụng, chạy lại:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.defaults.enabled=true'
```

Dự án tối thiểu không cấu hình sinh metadata build/git, nên phần thân vẫn là `{}`. Thuộc tính mặc định chung không đảo `env.enabled=false` thành `true`, cũng không tạo metadata còn thiếu.

Để thử thông tin Java mà không phụ thuộc dữ liệu build/git, chạy:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.java.enabled=true'
```

Phản hồi có khóa `java`. Các giá trị chi tiết phụ thuộc JVM thực tế; không chép một phiên bản Java cố định làm kết quả đúng cho mọi máy.

## 6. Chọn contributor theo nhu cầu triển khai

Giả sử yêu cầu là công bố mô tả dịch vụ và phiên bản bản dựng, không công bố thông tin Git, hệ điều hành hoặc tiến trình. Một cấu hình lựa chọn rõ ràng là:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    defaults:
      enabled: false
    build:
      enabled: true
    env:
      enabled: true
    git:
      enabled: false
    java:
      enabled: false
    os:
      enabled: false
    process:
      enabled: false

info:
  app:
    name: "order-service"
    description: "Dich vu xu ly don hang"
```

Đây là cấu hình chọn nguồn thông tin, không phải cam kết rằng `build` chắc chắn xuất hiện. Cần kiểm tra quy trình build đã tạo và đóng gói metadata. Nếu thiếu metadata, dữ liệu `app` vẫn có thể hiện đúng trong khi `build` vắng mặt.

Các dòng `false` riêng giúp người đọc thấy chủ đích triển khai. Chúng cũng làm rõ rằng không nên vô tình bật thêm một nguồn chỉ vì muốn xử lý lỗi thiếu dữ liệu của nguồn khác.

Nếu dự án có Spring Security, giữ quy tắc xác thực/phân quyền phù hợp với endpoint đã công bố. Không cần mở toàn bộ endpoint bằng `include: "*"` để sử dụng `info`.

## 7. Điều khiển một contributor tự viết

Ví dụ sau bổ sung một nguồn `release` có công tắc riêng. Tệp này là phần mở rộng của ứng dụng ở mục 5, đặt tại `src/main/java/example/infodemo/ReleaseInfoConfiguration.java`:

```java
package example.infodemo;

import java.util.Map;

import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReleaseInfoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "management.info.release",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    public InfoContributor releaseInfoContributor() {
        return builder -> builder.withDetail(
            "release",
            Map.of("channel", "stable")
        );
    }
}
```

`InfoContributor` là giao diện hàm với phương thức `contribute(Info.Builder)`, nên có thể dùng lambda như trên. [API InfoContributor của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html)

Lựa chọn của ví dụ:

- Chỉ tạo bean khi `management.info.release.enabled=true`.
- Khi thiếu thuộc tính hoặc có giá trị `false`, không tạo bean.
- `management.info.defaults.enabled` không tham gia quyết định của điều kiện tự viết này.
- Khóa JSON `release` được chọn trong `withDetail`; nó không được suy ra tự động từ tên phương thức hay tên thuộc tính.

Dừng ứng dụng, rồi chạy:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.release.enabled=true'
```

Với cấu hình gốc ở mục 5 và chỉ phần mở rộng này, phần thân phản hồi là:

```json
{
  "release": {
    "channel": "stable"
  }
}
```

Nếu đổi `release.enabled` thành `false`, phản hồi trở lại `{}`. Cần giữ `env.enabled=false` trong thí nghiệm này để không có dữ liệu `app` từ nguồn khác làm nhiễu quan sát.

Nếu bỏ annotation `@ConditionalOnProperty` khỏi phương thức bean thì bean luôn được đăng ký khi lớp cấu hình được nạp. Khi đó, đặt `release.enabled=false` không tự tắt nó. Đây là lý do không thể kiểm soát contributor tự viết chỉ bằng cách đặt một tên thuộc tính trông giống cấu hình có sẵn.

## 8. Chẩn đoán lỗi theo đúng lớp

| Hiện tượng | Điều cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| HTTP 200, phần thân `{}` | Contributor nào đang bật? Có metadata hoặc `info.*` không? | Bật đúng nguồn và kiểm tra dữ liệu của nguồn đó |
| Có `info.app.name` nhưng không có `app` trong JSON | `management.info.env.enabled` | Bật `env`; đặt dữ liệu dưới `info.*` |
| Đã bật `build` nhưng không có khóa `build` | Bean `BuildProperties` và metadata đã đóng gói | Kiểm tra đầu ra build và classpath, không chỉ tệp cấu hình |
| Đặt `defaults.enabled=false` mà vẫn có dữ liệu | Thuộc tính riêng đang `true` hoặc có contributor tự viết | Kiểm tra điều kiện đăng ký từng nguồn |
| Đặt `defaults.enabled=true` nhưng không có Java/OS | Các nguồn này mặc định tắt riêng | Đặt đúng `management.info.java.enabled` hoặc `os.enabled` |
| HTTP 404 | URL, cổng, base path, endpoint enablement và web exposure | Kiểm tra định tuyến/công bố trước khi sửa contributor |
| HTTP 401 hoặc 403 | Quy tắc xác thực/phân quyền và hạ tầng phía trước | Kiểm tra lớp kiểm soát truy cập; bật contributor không cấp quyền |

Không dùng mã trạng thái HTTP như bằng chứng tuyệt đối cho một nguyên nhân duy nhất: proxy hoặc quy tắc bảo mật có thể làm thay đổi cách phản hồi lỗi. Bảng giúp chọn thứ tự kiểm tra.

Một số lỗi cấu hình thường gặp:

1. **Sai vị trí YAML.** `info.app.name` nằm ở gốc `info`; không đặt dữ liệu thành `management.info.app.name`.
2. **Sai số ít/số nhiều.** `management.endpoint.info.enabled` điều khiển một endpoint; `management.endpoints.web.exposure.include` là cấu hình công bố nhiều endpoint.
3. **Nhầm env contributor với env endpoint.** Bật `management.info.env.enabled` không tự mở `/actuator/env`; nó chỉ thêm dữ liệu `info.*` vào `/actuator/info`.
4. **Quên nguồn ghi đè cấu hình.** Với ví dụ này, đối số dòng lệnh được dùng để ghi đè giá trị trong `application.yml`. Khi chẩn đoán môi trường khác, kiểm tra profile và nguồn cấu hình đang có hiệu lực.
5. **Mong thay đổi ngay mà không khởi động lại.** Các ví dụ dùng điều kiện tạo bean lúc khởi động; sửa tệp không bảo đảm context tự tái tạo.

Về dữ liệu công bố, chỉ đưa vào `info.*` những thông tin được chủ động chọn để trả cho người gọi. Không đặt mật khẩu, token hoặc chuỗi kết nối có thông tin đăng nhập vào đó. Không suy ra rằng cơ chế che giá trị của endpoint `env` sẽ tự che dữ liệu của `EnvironmentInfoContributor`; đó là hai đường cung cấp dữ liệu khác nhau. Để tránh ghi đè dữ liệu ngoài ý muốn, contributor tự viết cũng nên dùng khóa riêng thay vì dùng lại `build`, `git` hoặc khóa của nguồn khác.

## 9. Tự kiểm tra cách hiểu

Hãy dự đoán kết quả trước khi chạy thử. Giả sử endpoint đã mở và người gọi có quyền truy cập:

| Tình huống | Kết quả cần dự đoán |
| --- | --- |
| Có `info.app.name`, chưa bật `env`, không có metadata hoặc contributor tự viết | HTTP 200 với `{}` |
| `defaults.enabled=false`, `env.enabled=true`, có `info.app.name` | Có khóa `app` |
| `defaults.enabled=false`, `git.enabled=true`, không có `GitProperties` | Không có khóa `git` chỉ nhờ công tắc |
| `defaults.enabled=true`, chưa đặt `java.enabled` | Không tự có khóa `java` |
| `defaults.enabled=false`, bean tự viết không có điều kiện | Bean đó vẫn có thể đóng góp dữ liệu |
| `release.enabled=false`, dùng đúng lớp cấu hình ở mục 7 | Không tạo bean `releaseInfoContributor` |

Sau bài học, cần giải thích được ba ý: **công bố endpoint**, **cho phép contributor** và **có dữ liệu đầu vào** là ba việc riêng. Khi muốn thay đổi thông tin trả về, hãy xác định đúng contributor, xem giá trị riêng có ghi đè mặc định không, rồi kiểm tra nguồn dữ liệu và điều kiện đăng ký bean.
