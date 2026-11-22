# Cấu hình danh sách include và exclude cho HTTP

## 1. Vì sao cần lựa chọn endpoint được công bố?

Ứng dụng có Actuator không có nghĩa là người gọi HTTP cần truy cập mọi khả năng quản trị. Hệ thống giám sát có thể chỉ cần xem sức khỏe, còn người vận hành cần thêm thông tin ứng dụng và số liệu chẩn đoán. Danh sách công bố giúp chọn những endpoint thực sự cần có trên giao diện HTTP.

Trong phạm vi bài này, **công bố qua HTTP (HTTP exposure)** nghĩa là Actuator cho phép một endpoint tham gia vào giao diện web của ứng dụng. Việc một người gọi cụ thể có truy cập được hay không còn phụ thuộc địa chỉ, cổng, đường dẫn và chính sách bảo mật.

Có ba câu hỏi cần tách riêng:

1. Endpoint có được cung cấp và bật trong ứng dụng không?
2. Endpoint đó có được chọn để công bố qua HTTP không?
3. Yêu cầu HTTP hiện tại có đi đúng nơi và được phép truy cập không?

`include` và `exclude` giải quyết câu hỏi thứ hai. Đừng dùng chúng để suy luận thay cho hai câu hỏi còn lại.

Bài viết dùng hành vi Spring Boot 3.3.x; các thí nghiệm minh họa dùng Spring Boot 3.3.0 và Java 21.

## 2. Hai thuộc tính cấu hình và giá trị đầu vào

| Thuộc tính | Ý nghĩa | Khi chưa cấu hình lại trong Boot 3.3 |
| --- | --- | --- |
| `management.endpoints.web.exposure.include` | Chọn các ID endpoint để công bố qua HTTP | Chỉ `health` được chọn theo mặc định |
| `management.endpoints.web.exposure.exclude` | Loại các ID endpoint khỏi giao diện HTTP | Không loại thêm endpoint nào |

Giá trị là **ID endpoint**, chẳng hạn `health`, `info`, `metrics`, `loggers`, không phải URL hay tên phương thức Java. Nếu một ID xuất hiện trong cả hai danh sách, `exclude` được ưu tiên. [Quy tắc công bố endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Ví dụ đúng:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

Trong một ứng dụng có đủ ba endpoint này và chúng đang được bật, kết quả là công bố `health` và `info`; `metrics` bị loại. Thứ tự tên trong chuỗi không thay đổi thứ tự ưu tiên giữa hai thuộc tính.

Những giá trị sau không phải cách chọn endpoint đúng:

```text
/actuator/health
http://localhost:8080/actuator/health
GET /actuator/health
health.read
```

Chúng nhầm ID với đường dẫn, URL hoặc tên thao tác. Trong cấu hình, hãy dùng `health`.

### 2.1. Danh sách include mới không tự cộng thêm health

Nếu viết:

```properties
management.endpoints.web.exposure.include=info
```

thì danh sách chọn là `info`, không phải `health,info`. Trong ứng dụng thử nghiệm không có bộ lọc bảo mật, GET `/actuator/info` trả 200, còn GET `/actuator/health` trả 404.

Nếu cần cả hai, phải ghi rõ:

```properties
management.endpoints.web.exposure.include=health,info
```

Đây là lỗi dễ gặp khi ứng dụng đang được hệ thống giám sát kiểm tra `/actuator/health`: thêm một endpoint vào cấu hình bằng cách thay hẳn danh sách có thể vô tình làm mất endpoint kiểm tra sức khỏe.

### 2.2. Chỉ cấu hình exclude không có nghĩa là chọn mọi endpoint còn lại

Ví dụ:

```properties
management.endpoints.web.exposure.exclude=env
```

Nếu không có nguồn nào thay đổi `include`, danh sách công bố vẫn theo mặc định là `health`. Cấu hình này không tự công bố `info`, `metrics` hay tất cả endpoint khác. `exclude` chỉ loại bớt từ tập đã được chọn.

## 3. Cách tính kết quả khi có cả include và exclude

Có thể hình dung bộ lọc chuẩn như sau:

```text
Endpoint đáp ứng điều kiện tồn tại và được bật
    → có được include chọn không?
    → có bị exclude loại không?
    → nếu được chọn và không bị loại: thuộc tập công bố HTTP
```

Gọi `U` là tập endpoint có thể được cung cấp với điều kiện bật hiện tại; `I` là tập ID được chọn và `E` là tập ID bị loại. Trong mô hình đơn giản, chưa xét bộ lọc tùy biến:

```text
Tập công bố HTTP = (U giao I) trừ E
```

Phép tính này giúp giải thích cấu hình; nó không thay thế việc kiểm tra đường dẫn và quyền truy cập thực tế.

| include hiệu lực | exclude hiệu lực | Kết quả đối với health / info / metrics, giả sử cả ba đều có và được bật |
| --- | --- | --- |
| Không đặt lại, dùng mặc định | Không đặt | Chỉ `health` |
| `health,info` | Không đặt | `health`, `info` |
| `health,info,metrics` | `metrics` | `health`, `info` |
| `info` | Không đặt | Chỉ `info` |
| `health` | `info` | Chỉ `health`; loại `info` không thêm endpoint nào |
| `*` | `metrics` | Chọn các endpoint đủ điều kiện, riêng `metrics` bị loại |
| `*` | `*` | Không công bố endpoint Actuator nào qua HTTP |

Ví dụ một endpoint bị tắt:

```properties
management.endpoint.info.enabled=false
management.endpoints.web.exposure.include=health,info
```

`info` có tên trong `include` nhưng không được bật, nên không thể truy cập qua HTTP. Ngược lại, loại một endpoint bằng `web.exposure.exclude` chỉ diễn tả quyết định công bố qua HTTP; không phải lệnh vô hiệu hóa nó trên mọi kênh quản trị.

Tương tự, đưa `prometheus` vào danh sách không tự thêm thư viện cung cấp endpoint đó. Với dự án tối thiểu trong bài, không có `micrometer-registry-prometheus`, nên GET `/actuator/prometheus` vẫn trả 404 khi được ghi trong `include`.

## 4. Viết cấu hình trong properties và YAML

### 4.1. Danh sách tường minh

Dạng `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

Dạng tương đương trong `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - metrics
```

Cũng có thể viết danh sách YAML thành chuỗi phân tách bằng dấu phẩy:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
        exclude: "metrics"
```

Chọn một cách biểu diễn nhất quán để dễ rà soát. Các đoạn trên là những lựa chọn thay thế cho nhau; không chép nhiều khối `management` trùng cấp vào cùng một tài liệu YAML.

### 4.2. Chọn tất cả bằng dấu sao

Trong properties:

```properties
management.endpoints.web.exposure.include=*
management.endpoints.web.exposure.exclude=env,configprops
```

Trong YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
```

Phải đặt dấu sao trong dấu nháy ở YAML vì `*` có ý nghĩa riêng trong cú pháp YAML. Trong tệp properties, viết `include=*`; dấu nháy không cần để bao chuỗi như ở YAML.

`*` là giá trị chọn tất cả được hỗ trợ. Không suy rộng thành mẫu tên như `health*`, `*metrics` hoặc đường dẫn `/**`. Trong kiểm tra với Boot 3.3.0, `include=health*` khiến quá trình khởi tạo cấu hình từ chối ID chứa ký tự không hợp lệ, thay vì chọn các endpoint có tiền tố `health`.

Khi dùng `include=*`, tập công bố có thể tăng sau khi bổ sung thư viện hoặc endpoint tự viết. Danh sách tường minh phù hợp khi cần kiểm soát chính xác khả năng nào được công bố; chọn tất cả rồi loại một số ID đòi hỏi rà soát lại mỗi khi tập endpoint thay đổi.

### 4.3. Loại toàn bộ endpoint khỏi HTTP

Trong properties:

```properties
management.endpoints.web.exposure.exclude=*
```

Trong YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

Quy tắc này vẫn thắng một danh sách `include` có sẵn. Nó loại các endpoint Actuator khỏi giao diện HTTP, không đồng nghĩa tắt máy chủ web hay xóa các controller nghiệp vụ. [Cấu hình HTTP quản trị, bao gồm cách loại toàn bộ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

## 5. Thực nghiệm có thể chạy độc lập

Mục tiêu là quan sát cùng một ứng dụng nhưng danh sách endpoint HTTP thay đổi theo cấu hình. Dự án không thêm Spring Security, không có controller nghiệp vụ và chỉ lắng nghe trên loopback để kết quả tập trung vào bộ lọc công bố.

Cần JDK 21, Gradle 8.5 và kết nối tải phụ thuộc cho lần xây dựng đầu tiên. Kiểm tra `java -version` và `gradle --version` trước khi chạy.

### 5.1. Tạo các tệp

```text
actuator-http-exposure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/exposure/ExposureApplication.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-http-exposure-demo'
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

tasks.named('bootJar') {
    archiveFileName = 'actuator-http-exposure-demo.jar'
}
```

Tệp `src/main/java/example/exposure/ExposureApplication.java`:

```java
package example.exposure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExposureApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExposureApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

Không cần tự viết endpoint Java để thử quy tắc này; `health`, `info` và `metrics` đã đủ thể hiện việc chọn rồi loại.

### 5.2. Xây dựng và chạy

Tại thư mục chứa `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-http-exposure-demo.jar
```

Lệnh đầu tạo JAR; lệnh thứ hai chạy ứng dụng và giữ cửa sổ dòng lệnh đó hoạt động. Mở cửa sổ khác để gửi yêu cầu. Trên PowerShell Windows, dùng `curl.exe` nếu `curl` đang được ánh xạ thành bí danh.

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
curl -i http://127.0.0.1:8080/actuator/metrics
```

Kết quả chính của dự án mẫu:

| Yêu cầu | Mã HTTP | Cách giải thích |
| --- | --- | --- |
| GET `/actuator/health` | 200 | Có trong include, không bị exclude |
| GET `/actuator/info` | 200 | Có trong include, không bị exclude |
| GET `/actuator/metrics` | 404 | Bị exclude dù cũng có trong include |

Trong dự án mẫu mới tạo, chưa thêm nguồn thông tin ứng dụng nên thân phản hồi `info` là:

```json
{}
```

`200` với `{}` nghĩa là endpoint đã được công bố và xử lý yêu cầu, nhưng chưa có dữ liệu thông tin để trả. Nó khác với `404` do không có ánh xạ phù hợp trong thí nghiệm này. Không cần ép toàn bộ header hoặc nội dung lỗi 404 phải giống nhau giữa các máy.

Có thể mở trang khám phá `/actuator` để xem các liên kết được công bố trong cấu hình mẫu. Việc không thấy liên kết ở đó là một manh mối kiểm tra, không phải bằng chứng phổ quát: trang khám phá có cấu hình riêng và cũng có thể chịu kiểm soát truy cập.

### 5.3. Thử quyền ưu tiên của exclude

Dừng ứng dụng bằng Ctrl+C, rồi chạy lại cùng JAR với danh sách include truyền từ dòng lệnh:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=health,info,metrics
```

`metrics` vẫn trả 404 vì tệp cấu hình còn `exclude=metrics`. Ghi lại tên trong `include` không phải cách gỡ một phần tử khỏi `exclude`.

Muốn công bố `metrics`, sửa tệp nguồn để không còn loại `metrics`, chạy lại `gradle bootJar`, rồi khởi động lại JAR. Với cấu hình thông thường của dự án mẫu, chỉnh tệp đã đóng gói không tự cập nhật giao diện endpoint của tiến trình đang chạy.

### 5.4. Thử một danh sách include hẹp hơn

Giữ nguyên JAR ban đầu có `exclude=metrics`; dừng tiến trình trước rồi chạy:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=info
```

Khi gọi lại:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
```

`health` trả 404, `info` trả 200. Đây là bằng chứng rằng danh sách tường minh `info` không tự cộng thêm mặc định `health`.

## 6. Khi cấu hình có nhiều nguồn

Thuộc tính hiệu lực có thể đến từ tệp chung, tệp theo profile, biến môi trường hoặc tham số dòng lệnh. Với cơ chế cấu hình mặc định của Boot, tham số dòng lệnh có thể ghi đè giá trị từ tệp. Vì thế, hãy xác định **giá trị cuối của từng thuộc tính**, thay vì chỉ nhìn một tệp. [Thứ tự ưu tiên nguồn cấu hình của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Ví dụ tệp cấu hình có:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=metrics
```

Khởi động với:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=health,metrics
```

Trong thí nghiệm với đúng các giá trị trên:

| Thuộc tính hiệu lực | Giá trị |
| --- | --- |
| include | `health,metrics` từ dòng lệnh |
| exclude | `metrics` từ tệp cấu hình |

Kết quả: `health` được công bố; `info` không còn được chọn; `metrics` bị loại. Đừng giả định danh sách include mới sẽ nối vào danh sách cũ, hoặc việc thay include sẽ xóa exclude.

Khi dùng profile, cũng cần xem cả include và exclude của môi trường đang hoạt động. Nếu chỉ thay một thuộc tính, thuộc tính còn lại vẫn có thể đến từ một nguồn khác.

## 7. Phạm vi của cấu hình HTTP

### 7.1. Không dùng web.exposure để cấu hình JMX

`management.endpoints.web.exposure.*` dành cho HTTP. Cấu hình công bố JMX có nhánh riêng `management.endpoints.jmx.exposure.*`. Loại `info` khỏi HTTP không đủ để kết luận nó đã bị loại khỏi JMX; cần kiểm tra cấu hình và điều kiện bật JMX tương ứng.

### 7.2. Chọn endpoint không thay đổi ID khi đường dẫn đổi

Ví dụ đổi tiền tố đường dẫn:

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health,info
```

Đường dẫn mặc định tương ứng chuyển thành `/manage/health` và `/manage/info`, nhưng giá trị trong include vẫn là `health,info`. Không đổi include thành `/manage/health`.

Cổng quản trị và địa chỉ lắng nghe cũng là những quyết định khác với lựa chọn endpoint. Nếu ứng dụng sử dụng cổng quản trị riêng, phải gửi yêu cầu tới đúng cổng đó. [Đường dẫn và cổng HTTP quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 7.3. Công bố không thay thế phân quyền

`include=loggers` chọn endpoint `loggers`, không phải một chính sách “chỉ cho GET xem log”. Danh sách này chọn ID endpoint, không phân chia quyền đọc/ghi theo phương thức HTTP. Quyền truy cập từng thao tác cần được cấu hình ở lớp bảo mật phù hợp.

Trong một ứng dụng có Spring Security, endpoint được chọn vẫn có thể trả 401 hoặc 403. Đó là tình huống khác với việc endpoint bị loại khỏi giao diện HTTP. Không mở rộng `include` hoặc dùng `include=*` như một cách mặc định để giải quyết lỗi xác thực hay phân quyền.

## 8. Trình tự chẩn đoán và lỗi thường gặp

Khi một endpoint không truy cập được, kiểm tra theo thứ tự có thể kiểm chứng:

1. **Đúng đích:** địa chỉ, cổng, context path, tiền tố quản trị và ánh xạ đường dẫn.
2. **Có khả năng cung cấp:** thư viện cần thiết, bean phụ thuộc và cấu hình bật endpoint.
3. **Đúng danh sách hiệu lực:** endpoint có trong include và không có trong exclude; xem cả profile và tham số khởi động.
4. **Đúng quyền:** cơ chế xác thực, phân quyền và chính sách HTTP đang áp dụng.

Trong dự án tối thiểu không có Spring Security của bài, endpoint bị loại trả 404. Trong một hệ thống thật, lớp bảo mật hoặc proxy có thể thay đổi phản hồi; không suy ra nguyên nhân duy nhất chỉ từ một mã HTTP.

| Sai sót | Hệ quả / cách sửa |
| --- | --- |
| Viết `management.endpoint.web.exposure.include` | Sai nhánh cấu hình; tên đúng dùng `endpoints` số nhiều |
| Viết URL đầy đủ trong include | Nhầm ID với địa chỉ; dùng `health`, `info`, `metrics` |
| Chỉ ghi `include=info` nhưng vẫn cần health | Ghi rõ `include=health,info` |
| Chỉ đặt `exclude=env` rồi chờ mọi endpoint khác xuất hiện | Exclude không tự mở rộng tập include mặc định |
| Một ID ở cả include và exclude | Exclude thắng; sửa danh sách loại ở nguồn có hiệu lực |
| Dùng `include: *` trong YAML | Dấu sao cần được bao bằng dấu nháy trong YAML |
| Dùng `health*` như mẫu tiền tố | Không phải mẫu ID được hỗ trợ; có thể làm ứng dụng không khởi động |
| Chọn endpoint đang bị tắt hoặc thiếu thư viện | Include không tạo endpoint và không tự bật nó |
| Sửa application.properties nhưng chạy JAR cũ | Xây dựng lại khi sửa cấu hình đóng gói, rồi khởi động lại |
| Sửa đúng tệp nhưng kết quả không đổi | Kiểm tra profile và nguồn cấu hình đang ghi đè |
| Cho rằng exclude tắt mọi controller hoặc mọi kênh | Đây là bộ lọc công bố endpoint Actuator qua HTTP |

## 9. Bài tập tự kiểm tra

**Câu 1.** `include=health,info,metrics` và `exclude=info` công bố những endpoint nào trong ba endpoint trên?

**Đáp án:** `health` và `metrics`, nếu chúng được cung cấp và đang bật. `info` bị loại vì exclude ưu tiên.

**Câu 2.** Chỉ viết `exclude=metrics` có làm `info` được công bố không?

**Đáp án:** Không. Nếu include vẫn theo mặc định thì chỉ `health` được chọn. Loại một phần tử không tự thêm các phần tử còn lại.

**Câu 3.** `include=*` có làm endpoint Prometheus xuất hiện trong dự án mẫu không?

**Đáp án:** Không. Dự án chưa có thư viện cần để cung cấp endpoint Prometheus. Dấu sao chọn các endpoint đủ điều kiện, không bổ sung phụ thuộc.

**Câu 4.** Dòng lệnh đổi include thành `health,metrics`, nhưng tệp vẫn có `exclude=metrics`. Vì sao metrics chưa xuất hiện?

**Đáp án:** Hai thuộc tính được xác định riêng. Include mới có hiệu lực, nhưng exclude từ tệp vẫn loại metrics.

**Câu 5.** Đổi base path thành `/manage` thì danh sách phải là `/manage/health,/manage/info` hay `health,info`?

**Đáp án:** Vẫn là `health,info`. Danh sách dùng ID; base path quyết định địa chỉ HTTP.

**Câu 6.** Vì sao nên ghi tường minh `health,info,metrics` nếu môi trường chỉ cần ba endpoint đó?

**Đáp án:** Người rà soát thấy trực tiếp phạm vi được chọn. Khi bổ sung endpoint khác vào ứng dụng, nó không tự được công bố chỉ vì trước đó đã dùng dấu sao.
