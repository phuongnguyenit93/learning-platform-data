# Đưa thông tin được chọn từ info.* vào phản hồi

## 1. Chọn thông tin ứng dụng nghĩa là gì?

Khi vận hành một dịch vụ, ta thường cần biết mình đang gọi đúng ứng dụng nào, ứng dụng phục vụ mục đích gì và nhóm nào phụ trách. Những thông tin nhận diện ít thay đổi này có thể xuất hiện trong phản hồi của `GET /actuator/info`.

Trong bài này, **chọn thông tin** nghĩa là chủ động khai báo những giá trị được phép công bố dưới tiền tố cấu hình `info.`. Spring Boot có bộ đóng góp thông tin `EnvironmentInfoContributor`, mang định danh `env`, để chuyển nhóm thuộc tính đó thành dữ liệu của endpoint `info`.

Ví dụ, ta muốn công bố:

- Tên dịch vụ: `catalog-service`.
- Mô tả ngắn: `Catalog API for learning`.
- Kênh triển khai: `local`.
- Nhóm hỗ trợ: `learning-team`.

Ta giữ các thông số vận hành riêng như `app.internal-region` ngoài nhóm `info`. Đây là lựa chọn dữ liệu từ lúc thiết kế cấu hình: bộ đóng góp mặc định không tự hiểu giá trị nào là công khai hoặc nội bộ.

**Phạm vi:** Spring Boot 3.3.x, JDK 21 và HTTP Actuator. Ví dụ cố định Spring Boot 3.3.0 để dễ tái lập; không cần viết controller hoặc tự tạo endpoint `info`.

## 2. Phân biệt bốn thành phần trước khi cấu hình

| Thành phần | Vai trò trong bài |
| --- | --- |
| `Environment` | Tập nguồn cấu hình Spring đang sử dụng: YAML, properties, biến môi trường, tham số dòng lệnh… |
| Thuộc tính `info.*` | Nhóm dữ liệu ứng dụng chủ động chuẩn bị để công bố. Dấu `*` ở đây chỉ cách gọi cả nhóm thuộc tính. |
| Bộ đóng góp `env` | Đọc các thuộc tính dưới `info` và bổ sung chúng vào thông tin ứng dụng. |
| Endpoint `info` | Tổng hợp dữ liệu của các `InfoContributor` đang tham gia; khi được mở qua HTTP thì trả dữ liệu tại `/actuator/info`. |

`EnvironmentInfoContributor` đọc toàn bộ nhánh `info`, không có bước lựa chọn riêng từng trường bằng query parameter. Ví dụ `info.app.name` trở thành trường `app.name` trong JSON; tiền tố `info` không xuất hiện như một lớp bọc JSON. [API EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html)

Luồng dữ liệu:

```text
application.yml / nguồn cấu hình khác
              ↓
Environment: info.app.name, info.app.channel, ...
              ↓
EnvironmentInfoContributor (định danh: env)
              ↓
Info.Builder → InfoEndpoint
              ↓
GET /actuator/info → JSON
```

`InfoEndpoint` nhận danh sách `InfoContributor`; vì vậy trong ứng dụng thực tế, phản hồi có thể còn chứa dữ liệu từ bộ đóng góp khác. [API InfoEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html)

### Ba công tắc độc lập

1. **Endpoint có được bật không?** `management.endpoint.info.enabled`.
2. **Endpoint có được mở qua HTTP không?** `management.endpoints.web.exposure.include` phải chứa `info` và không bị danh sách `exclude` loại đi.
3. **Nguồn dữ liệu info.* có được đọc không?** `management.info.env.enabled=true`.

Trong Spring Boot 3.3, bộ đóng góp `env` mặc định tắt. Do đó, chỉ thêm `info.app.name` hoặc chỉ mở endpoint qua HTTP chưa đủ để dữ liệu ấy xuất hiện. [Điều kiện tự cấu hình của bộ đóng góp thông tin](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html)

Chú ý: `env` trong `management.info.env.enabled` là **bộ đóng góp của info**. Nó khác endpoint `/actuator/env`; bài này không cần mở endpoint `env`.

## 3. Ví dụ chạy độc lập

Ví dụ chỉ sử dụng Web và Actuator, không thêm Spring Security hay bộ đóng góp tự viết. Máy chạy cần JDK 21, Gradle 8.5 và có thể tải các phụ thuộc từ Maven Central.

Cấu trúc:

```text
info-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/infodemo/InfoDemoApplication.java
    └── resources/application.yml
```

### 3.1. Khai báo dự án và phụ thuộc

`settings.gradle`:

```groovy
rootProject.name = 'info-selection-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

BOM quản lý phiên bản các phụ thuộc tương thích với Spring Boot. Plugin Spring Boot cung cấp tác vụ `bootRun`; không cần tạo tác vụ Java riêng. [Cách áp dụng Gradle plugin Spring Boot](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)

### 3.2. Tạo lớp khởi động

Tệp `src/main/java/com/example/infodemo/InfoDemoApplication.java`:

```java
package com.example.infodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

Đây là lớp khởi động đầy đủ. Lệnh `bootRun` ở phần sau sẽ biên dịch và chạy lớp này cùng các thư viện Spring; chạy `javac` riêng mà không có classpath phụ thuộc sẽ không đủ.

### 3.3. Chuẩn bị đúng dữ liệu được công bố

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: catalog-service

app:
  internal-region: zone-a

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: "${spring.application.name}"
    description: "Catalog API for learning"
    channel: "${APP_CHANNEL:local}"
  support:
    team: "learning-team"
```

Cách đọc cấu hình:

- `spring.application.name` là tên ứng dụng dùng trong cấu hình Spring. Giá trị này được đưa vào phản hồi vì ta **tham chiếu rõ ràng** từ `info.app.name`.
- `app.internal-region` vẫn dùng được trong ứng dụng nhưng nằm ngoài `info`; ví dụ không có bộ đóng góp nào khác công bố nó.
- `management.info.defaults.enabled=false` giúp cô lập thí nghiệm khỏi các bộ đóng góp tự cấu hình được bật theo mặc định. Sau đó `management.info.env.enabled=true` bật rõ ràng nguồn dữ liệu cần học. Cấu hình này không phải lệnh vô hiệu hóa mọi bean `InfoContributor` tự viết.
- `info.app.channel` tham chiếu biến `APP_CHANNEL`; khi biến đó chưa được đặt, dùng `local`.
- `server.address=127.0.0.1` giữ ví dụ thực hành trên máy cá nhân.

Trong một dự án đang có cấu hình, hãy gộp các khóa vào cây YAML hiện hữu. Không tạo hai khóa `management:` hoặc hai khóa `info:` ở cùng cấp.

### 3.4. Chạy và đọc phản hồi

Từ thư mục dự án, dùng Gradle 8.5 với JDK 21:

```shell
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper 8.5, Windows PowerShell dùng:

```powershell
.\gradlew.bat bootRun
```

Linux/macOS dùng:

```shell
./gradlew bootRun
```

Chọn một lệnh phù hợp; không khởi động đồng thời nhiều bản trên cổng 8080.

Đợi ứng dụng khởi động xong. Từ terminal thứ hai, trên Windows chạy:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/info
```

Trên Linux/macOS, thay `curl.exe` bằng `curl`.

Khi không có `APP_CHANNEL`, không có tham số ghi đè và dùng đúng ví dụ, nội dung JSON là:

```json
{
  "app": {
    "name": "catalog-service",
    "description": "Catalog API for learning",
    "channel": "local"
  },
  "support": {
    "team": "learning-team"
  }
}
```

JSON trên đã được xuống dòng để dễ đọc. Công cụ gọi HTTP có thể in một dòng và thứ tự khóa JSON không phải cam kết của API; các trường và giá trị mới là kết quả cần đối chiếu.

Phản hồi không có lớp bọc `info`, không có cây `spring`, không có `app.internal-region`. Trong JSON, đối tượng `app` đến từ `info.app`, không phải toàn bộ cấu hình gốc `app`.

## 4. Cơ chế chọn trường: chọn lúc khai báo, không lọc sau khi thu thập

Hãy xem `info` như một bản thông tin công bố mà ứng dụng chủ động chuẩn bị.

| Thuộc tính nguồn | Có xuất hiện qua bộ đóng góp env trong ví dụ không? | Lý do |
| --- | --- | --- |
| `info.app.description` | Có | Thuộc nhánh `info`. |
| `spring.application.name` | Có, dưới tên `app.name` | Được tham chiếu qua `info.app.name`. |
| `app.internal-region` | Không | Không thuộc `info` và không được tham chiếu vào đó. |
| `server.port` | Không | Không tự động được sao chép vào `info`. |
| Một khóa mới `info.support.contact` | Có khi được khai báo | Bộ đóng góp mặc định đọc cả nhánh `info`, không chỉ các trường ban đầu. |

Vì vậy, đặt tên `info.private.*` hoặc `info.internal.*` không làm chúng trở thành dữ liệu riêng tư. Các nhánh ấy vẫn ở dưới `info`. Tương tự, `management.endpoints.web.exposure.exclude=env` chỉ loại endpoint `env` khỏi HTTP; nó không loại trường nào trong phản hồi `info`.

Không có bộ lọc mặc định `management.info.env.include` / `management.info.env.exclude` để chọn một số khóa con. Nếu ứng dụng cần bảo đảm một tập trường cố định dù người khác thêm khóa `info.*`, hãy tắt bộ đóng góp `env` và thiết kế `InfoContributor` riêng chỉ lấy các khóa được cho phép. Việc đó là một bước mở rộng; ví dụ chính ở đây giải quyết nhu cầu bằng cấu hình.

Mã nguồn `EnvironmentInfoContributor` của Spring Boot 3.3 gắn dữ liệu nhánh `info` vào một bản đồ rồi chuyển các chi tiết đó cho `Info.Builder`; nó không thực hiện chính sách bảo mật theo tên khóa. Vì vậy, đừng dựa vào tên như `password` hoặc `token` để mong dữ liệu tự bị che trong phản hồi `info`. [Mã nguồn EnvironmentInfoContributor](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.java)

Trong thực tế, hãy chọn các trường phục vụ nhận diện/hỗ trợ và không đưa thông tin đăng nhập, khóa API, dữ liệu khách hàng hay liên kết chứa thông tin bí mật vào `info.*`. Quyền truy cập endpoint và việc chọn dữ liệu công bố là hai quyết định riêng.

## 5. Placeholder và giá trị cấu hình có hiệu lực

Cú pháp `${ten-thuoc-tinh}` tham chiếu một giá trị; `${ten-thuoc-tinh:mac-dinh}` thêm giá trị dự phòng. Biến môi trường và tham số dòng lệnh có thể cung cấp giá trị khác với tệp YAML. [Placeholder và thứ tự nguồn cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.property-placeholders)

### 5.1. Đổi kênh triển khai mà không sửa YAML

Dừng ứng dụng bằng `Ctrl+C`. Trong PowerShell, đặt biến rồi khởi động lại từ chính terminal đó:

```powershell
$env:APP_CHANNEL = 'staging'
gradle bootRun
```

Khi gọi lại endpoint, `app.channel` trở thành `"staging"`; các trường còn lại như ví dụ ban đầu.

Biến phải có trong môi trường của tiến trình khởi động ứng dụng. Đặt biến ở terminal dùng để gọi `curl` không thay đổi môi trường của ứng dụng đang chạy ở terminal khác.

Để quay về ví dụ ban đầu, dừng ứng dụng, xóa biến trong terminal đã đặt nó, rồi khởi động lại:

```powershell
Remove-Item Env:APP_CHANNEL -ErrorAction SilentlyContinue
gradle bootRun
```

Cách dùng biến môi trường của Linux/macOS:

```shell
APP_CHANNEL=staging gradle bootRun
```

### 5.2. Ghi đè trực tiếp trường được công bố

Dừng bản đang chạy, bảo đảm `APP_CHANNEL` không được đặt, rồi chạy:

```shell
gradle bootRun --args="--info.app.channel=canary"
```

Trường `app.channel` trong phản hồi là `"canary"`. Ở đây tham số ghi đè chính thuộc tính `info.app.channel`, nên giá trị placeholder trong YAML không còn quyết định trường đó.

Các thay đổi trên được kiểm chứng bằng **khởi động lại**. Sửa YAML trên đĩa không đồng nghĩa ứng dụng đang chạy tự nạp lại cấu hình. Bài này không thiết lập cơ chế refresh.

## 6. Thí nghiệm tách công tắc dữ liệu và công tắc HTTP

Dừng ứng dụng trước mỗi lần chạy, giữ nguyên các tệp cấu hình.

### Thí nghiệm A: Tắt nguồn dữ liệu info.*

```shell
gradle bootRun --args="--management.info.env.enabled=false"
```

Gọi lại `/actuator/info`. Với đúng ví dụ không có bộ đóng góp tự viết và đã tắt các nguồn mặc định, phản hồi là:

```json
{}
```

Endpoint vẫn được mở qua HTTP, nhưng không có dữ liệu đóng góp. Trong dự án khác, phản hồi vẫn có thể có dữ liệu từ bộ đóng góp khác; đừng kết luận mọi ứng dụng đều trả `{}` khi tắt `env`.

### Thí nghiệm B: Giữ dữ liệu nhưng không mở info qua HTTP

```shell
gradle bootRun --args="--management.endpoints.web.exposure.include=health"
```

Kiểm tra mã HTTP:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:8080/actuator/info
```

Trong đúng ví dụ độc lập, kết quả in ra là:

```text
404
```

Trên Linux/macOS, dùng `curl` và thay `NUL` bằng `/dev/null`.

Sự khác nhau cần nhớ: `{}` với HTTP 200 cho thấy endpoint có thể truy cập nhưng không có chi tiết; HTTP 404 trong thí nghiệm B cho thấy không có đường HTTP tương ứng được mở. [Bật và mở Actuator endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

## 7. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Kiểm tra sát nguyên nhân |
| --- | --- |
| Đã khai báo `info.*` nhưng phản hồi thiếu chúng | Xác nhận `management.info.env.enabled=true` trong cấu hình có hiệu lực và thụt lề YAML đúng. |
| Trả HTTP 404 | Kiểm tra phụ thuộc Actuator, endpoint đã bật, danh sách mở HTTP, `exclude`, đúng cổng và đúng đường dẫn. Ví dụ dùng cổng 8080 và tiền tố mặc định `/actuator`. |
| Trả HTTP 401 hoặc 403 trong ứng dụng hiện có | Kiểm tra quy tắc xác thực/phân quyền. Việc thêm `info` vào danh sách HTTP không tự cấp quyền truy cập. |
| Không thấy tên ứng dụng | `spring.application.name` không tự thành trường phản hồi; cần ánh xạ bằng `info.app.name` như ví dụ. |
| Xuất hiện một trường không mong muốn | Tìm cấu hình `info.*` tương ứng trong các nguồn đang nạp và kiểm tra các `InfoContributor` khác. |
| Giá trị khác YAML | Kiểm tra biến môi trường, tham số dòng lệnh và tệp cấu hình của profile đang hoạt động. |
| Đã sửa tệp nhưng phản hồi vẫn cũ | Khởi động lại để kiểm chứng cấu hình mới; không giả định có tự động refresh. |
| Lộ thông tin nội bộ dù endpoint `env` không mở | Kiểm tra dữ liệu đặt hoặc được tham chiếu dưới `info`; hai cơ chế không dùng chung danh sách chọn trường. |

Nếu dịch vụ có Spring Security, bộ đóng góp `env` vẫn chỉ quyết định nội dung; chính sách bảo vệ endpoint quyết định ai được đọc nội dung đó. Không thay toàn bộ cấu hình bảo mật chỉ để xử lý một trường thiếu.

## 8. Tự thực hành

1. Chạy ví dụ ban đầu và kiểm tra đủ bốn giá trị đã chọn, đồng thời không có `internal-region`.
2. Thêm `info.support.contact: "support@example.test"` vào nhánh `support`, khởi động lại và dự đoán vị trí trường mới.
3. Đặt `APP_CHANNEL=staging` trong môi trường tiến trình ứng dụng; xác nhận chỉ giá trị kênh đổi.
4. Tắt bộ đóng góp `env`; kiểm tra endpoint còn truy cập được nhưng dữ liệu của nhánh `info` không còn.
5. Khôi phục cấu hình, chỉ mở `health` qua HTTP và kiểm tra mã 404 khi gọi `info`.

Đáp án kiểm tra: bước 2 thêm trường `support.contact`; bước 3 đổi `app.channel` thành `"staging"`; bước 4 trả `{}` trong đúng dự án mẫu; bước 5 không cung cấp đường HTTP `/actuator/info`.

Sau bài này, người học cần giải thích được đường đi **thuộc tính được chọn → info.* → bộ đóng góp env → phản hồi info**, đồng thời biết chọn trường từ cấu hình, xác minh giá trị thực tế và phân biệt lỗi thiếu dữ liệu với lỗi không truy cập được endpoint.
