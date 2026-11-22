# Đọc danh mục SBOM, vị trí tệp và các SBOM bổ sung được cấu hình

## 1. SBOM giúp trả lời câu hỏi nào?

SBOM là **bảng kê thành phần phần mềm** (Software Bill of Materials). Khi kiểm tra một bản triển khai, bạn có thể cần biết ứng dụng được mô tả bởi tài liệu nào, tài liệu đó nằm trong gói ứng dụng hay ở một tệp bên ngoài, và có bảng kê riêng cho những phần khác của hệ thống hay không.

Spring Boot bổ sung hỗ trợ endpoint `sbom` từ phiên bản 3.3.0. Endpoint phục vụ các tài liệu SBOM đã có; việc tạo bảng kê từ quá trình build là một công việc riêng. [Javadoc SbomEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/sbom/SbomEndpoint.html)

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Định danh SBOM | Tên dùng để chọn tài liệu qua endpoint. | `application`, `platform` |
| Vị trí tài nguyên | Nơi tiến trình đọc các byte của tài liệu. | `classpath:sbom/application.cdx.json` |
| Nội dung và định dạng | Bảng kê thực tế được trả về. | Tài liệu CycloneDX JSON |

Định danh không phải đường dẫn tệp. Đuôi `.json` cũng chưa đủ xác định nội dung là CycloneDX, SPDX hay một định dạng khác.

Bài dùng **Java 21 và Spring Boot 3.3.13**. Trọng tâm là đọc danh mục, lần theo cấu hình vị trí và kiểm chứng tài liệu trả về; việc quét lỗ hổng hoặc xác nhận bảng kê đầy đủ cần các công cụ và bằng chứng bổ sung.

## 2. Hai kiểu yêu cầu cần đọc

| Yêu cầu GET | Kết quả |
| --- | --- |
| `/actuator/sbom` | Object chứa mảng `ids` của các SBOM hiện có. |
| `/actuator/sbom/{id}` | Nội dung tài liệu SBOM được chọn. |

Ví dụ danh mục:

```json
{
  "ids": ["application", "platform"]
}
```

Danh mục chỉ liệt kê tên. Nó không trả một object cho mỗi tài liệu với các trường `location`, `fileName` hoặc `components`. Khi chọn một id, phần thân phản hồi tuân theo định dạng SBOM tương ứng. [Hợp đồng REST của sbom](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

Luồng đọc:

```text
GET /actuator/sbom
    -> chọn một tên trong ids
    -> GET /actuator/sbom/{id}
    -> kiểm tra Content-Type và nội dung tài liệu
    -> đối chiếu id với cấu hình vị trí tài nguyên
```

Ví dụ `/actuator/sbom/application` có thể trả CycloneDX JSON. Bạn phải đọc cấu hình hoặc thông tin gói triển khai để biết tài liệu nguồn nằm ở đâu; không suy ra vị trí tệp từ URL đó.

## 3. Cấu hình vị trí tệp được hiểu thế nào?

Các thuộc tính chính của Boot 3.3:

```properties
management.endpoint.sbom.application.location=classpath:sbom/application.cdx.json
management.endpoint.sbom.application.media-type=application/vnd.cyclonedx+json

management.endpoint.sbom.additional.platform.location=classpath:sbom/platform.cdx.json
management.endpoint.sbom.additional.platform.media-type=application/vnd.cyclonedx+json
```

`application` là SBOM chính. Mỗi khóa dưới `additional` tạo một định danh bổ sung; trong ví dụ, khóa `platform` dẫn đến `/actuator/sbom/platform`. Các tài liệu được chọn độc lập, không tự hợp nhất thành một danh sách thành phần chung. Các nhóm thuộc tính này được công bố trong [danh mục cấu hình Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.1. `classpath:` và `file:` là hai nguồn khác nhau

- `classpath:sbom/application.cdx.json`: đọc tài nguyên có tên đó trên classpath của ứng dụng đang chạy.
- `file:./inventory/platform.cdx.json`: đọc một tệp bên ngoài, giải đường dẫn tương đối từ thư mục làm việc của tiến trình.
- `file:/opt/demo/inventory/platform.cdx.json`: ví dụ vị trí tuyệt đối trên hệ thống có đường dẫn đó.

Trong dự án Gradle thông thường:

```text
Tệp nguồn:
  src/main/resources/sbom/application.cdx.json

Tên tài nguyên khi chạy:
  classpath:sbom/application.cdx.json

Trong executable JAR của Boot:
  BOOT-INF/classes/sbom/application.cdx.json

URL đọc tài liệu:
  /actuator/sbom/application
```

Cách đóng gói `BOOT-INF/classes` là đặc điểm của executable JAR do Boot tạo. Nó không biến thành một phần của tên tài nguyên `classpath:` mà bạn phải ghi trong cấu hình. [Đóng gói executable archive](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)

Với `file:`, cần kiểm tra hệ thống tệp mà **tiến trình ứng dụng** nhìn thấy. Đường dẫn trên máy phát triển không tự tồn tại trong container; một tệp được tạo ngoài JAR cũng không tự được mang theo khi chỉ sao chép JAR sang máy khác.

### 3.2. Tự phát hiện và chỉ định vị trí

Khi không chỉ định `application.location`, Boot có cơ chế tự phát hiện SBOM ứng dụng được hỗ trợ. Nếu chỉ định vị trí, hãy kiểm tra chính tài nguyên đó thay vì mặc định rằng tài liệu vừa được build ở nơi khác sẽ được chọn.

Boot hỗ trợ tự nhận diện media type cho CycloneDX, SPDX và Syft; có thể đặt `media-type` để chỉ định rõ. Việc đặt header không chuyển đổi nội dung từ định dạng này sang định dạng khác. [Cấu hình định dạng và vị trí SBOM](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 4. Dự án thực hành độc lập với hai SBOM

### 4.1. Mục đích của các tài liệu mẫu

Hai tài liệu nhỏ dưới đây được viết để kiểm chứng luồng công bố và đọc tài nguyên. Tài liệu ứng dụng chỉ liệt kê một thành phần để giữ ví dụ rõ ràng; nó **không phải bảng kê đầy đủ các phụ thuộc** của ứng dụng Boot. Tài liệu `platform` là một mẫu riêng cho bài thực hành, không phải kết quả quét hệ điều hành đang chạy.

Khi áp dụng vào phát hành thật, dùng công cụ tạo bảng kê từ đúng bản build và kiểm tra phạm vi thành phần của công cụ đó.

Chuẩn bị JDK 21, Gradle 8.5 và cấu trúc:

```text
sbom-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/sbom/SbomReadApplication.java
    └── resources/
        ├── application.properties
        └── sbom/
            ├── application.cdx.json
            └── platform.cdx.json
```

### 4.2. Build và lớp khởi động

`settings.gradle`:

```groovy
rootProject.name = 'sbom-read-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'demo'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

springBoot {
    mainClass = 'demo.sbom.SbomReadApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'sbom-read-demo.jar'
}
```

`src/main/java/demo/sbom/SbomReadApplication.java`:

```java
package demo.sbom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SbomReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(SbomReadApplication.class, args);
    }
}
```

### 4.3. Hai tài liệu CycloneDX JSON

`src/main/resources/sbom/application.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "sbom-read-demo",
      "version": "1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "group": "org.springframework.boot",
      "name": "spring-boot-actuator",
      "version": "3.3.13",
      "purl": "pkg:maven/org.springframework.boot/spring-boot-actuator@3.3.13"
    }
  ]
}
```

`src/main/resources/sbom/platform.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "platform-inventory-lab",
      "version": "1.0.0"
    }
  },
  "components": []
}
```

`bomFormat` xác định họ định dạng; `specVersion` là phiên bản đặc tả; `version` ở gốc là phiên bản của bản kê. Nó khác `metadata.component.version`, vốn là phiên bản thành phần được mô tả. Danh sách `components` thuộc cấu trúc CycloneDX, không phải một trường do endpoint Actuator thêm vào. [Đặc tả CycloneDX JSON 1.5](https://cyclonedx.org/docs/1.5/json/)

### 4.4. Bật HTTP exposure và chọn tài nguyên

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,sbom

management.endpoint.sbom.application.location=classpath:sbom/application.cdx.json
management.endpoint.sbom.application.media-type=application/vnd.cyclonedx+json

management.endpoint.sbom.additional.platform.location=classpath:sbom/platform.cdx.json
management.endpoint.sbom.additional.platform.media-type=application/vnd.cyclonedx+json
```

`sbom` mặc định được bật trong Boot 3.3; HTTP mặc định chỉ công khai `health`. Nếu cấu hình chung đã tắt mặc định các endpoint, bật riêng bằng `management.endpoint.sbom.enabled=true`. Còn quyền truy cập HTTP phụ thuộc cơ chế bảo mật của ứng dụng. [Cấu hình endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Ví dụ không thêm Spring Security và chỉ lắng nghe loopback để thực hành. Trong môi trường thật, tên và phiên bản thành phần có thể là thông tin nội bộ cần cấp quyền đọc phù hợp.

Khởi động bằng Gradle 8.5:

```shell
gradle bootRun
```

Nếu đã có Gradle Wrapper tương ứng, dùng `./gradlew bootRun` hoặc `.\gradlew.bat bootRun`. Giữ ứng dụng chạy để thực hiện các yêu cầu đọc bên dưới.

## 5. Đọc danh mục và nội dung từng tài liệu

### 5.1. Xác nhận các id được công bố

Mở terminal thứ hai tại thư mục dự án:

```shell
curl -i http://127.0.0.1:8080/actuator/sbom
```

Trên PowerShell, dùng `curl.exe` nếu `curl` đang trỏ đến lệnh khác. Với hai tài nguyên đã tạo, danh mục có hai id `application` và `platform`. Thứ tự phần tử không phải ý nghĩa của danh mục.

Nếu đã cài `jq`, có thể sắp xếp để kiểm tra ổn định:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom | jq '.ids | sort'
```

Stdout của bước lọc trong ví dụ:

```json
[
  "application",
  "platform"
]
```

Hai id này không có nghĩa tài liệu đã được kiểm tra đầy đủ về nội dung; chúng cho bạn biết các tên đang được công bố trong thí nghiệm.

### 5.2. Đọc SBOM chính và SBOM bổ sung

```shell
curl -i http://127.0.0.1:8080/actuator/sbom/application
curl -i http://127.0.0.1:8080/actuator/sbom/platform
```

Cả hai dùng media type `application/vnd.cyclonedx+json` vì cấu hình và nội dung mẫu đều là CycloneDX JSON. Phần thân là tài liệu tương ứng, không được bọc thêm trong một object `sbom` hoặc `data` của Actuator. [Phản hồi một SBOM cụ thể](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

Với `jq`, đọc tên thành phần chính của tài liệu ứng dụng:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/application \
  | jq -r '.metadata.component.name'
```

Stdout:

```text
sbom-read-demo
```

Lặp lại với id `platform`:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/platform \
  | jq -r '.metadata.component.name'
```

Stdout:

```text
platform-inventory-lab
```

Ở đây, id `platform` khác tên thành phần `platform-inventory-lab`. Đổi khóa cấu hình không tự sửa trường `name` bên trong tài liệu.

### 5.3. Lưu phần thân và header riêng

Để kiểm tra tài liệu nhận được, lưu phần thân tách khỏi header:

```shell
curl -fsS -D application.headers -o downloaded-application.cdx.json http://127.0.0.1:8080/actuator/sbom/application
```

- `application.headers` chứa header HTTP, dùng để đọc trạng thái và `Content-Type`.
- `downloaded-application.cdx.json` chứa phần thân tài liệu.

Không dùng kết quả `curl -i` gồm cả header làm đầu vào cho công cụ đọc JSON. Khi HTTP thành công và đúng nội dung, công cụ kiểm tra SBOM mới có dữ liệu phù hợp để phân tích.

Đối chiếu byte của tài liệu tải về với tài nguyên nguồn trong thí nghiệm bằng PowerShell:

```powershell
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'src/main/resources/sbom/application.cdx.json').Hash
$downloadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'downloaded-application.cdx.json').Hash
$sourceHash -eq $downloadHash
```

Với các tệp của ví dụ chưa bị chỉnh sửa, chạy lại từ đúng bản tài nguyên, kết quả mong đợi là:

```text
True
```

Đây là phép kiểm tra byte, khác với việc chỉ mở JSON và thấy các trường trông giống nhau. Trong quy trình phát hành thật, đối chiếu với tài liệu thuộc **đúng artifact đã triển khai**, vì tệp trong thư mục mã nguồn có thể đã thay đổi sau khi build.

## 6. Kiểm tra vị trí khi chạy từ JAR

Để quan sát ranh giới giữa mã nguồn, artifact và tài nguyên khi chạy:

1. Dừng tiến trình `bootRun` để giải phóng cổng.
2. Tạo executable JAR.
3. Kiểm tra tài nguyên đã được đóng gói.
4. Chạy JAR rồi đọc lại danh mục và hai tài liệu.

```shell
gradle bootJar
jar tf build/libs/sbom-read-demo.jar
java -jar build/libs/sbom-read-demo.jar
```

Trong danh sách của `jar tf`, cần tìm:

```text
BOOT-INF/classes/sbom/application.cdx.json
BOOT-INF/classes/sbom/platform.cdx.json
```

Đây là hai mục cần quan sát, không phải toàn bộ stdout của `jar tf`. Khi chạy JAR, cấu hình vẫn dùng `classpath:sbom/...`; URL vẫn dùng id. Vị trí bên trong archive không phải đường dẫn tệp bên ngoài mà bạn có thể tùy ý mở bằng `file:`.

Nếu IDE đọc được SBOM nhưng executable JAR không có tài nguyên, cần kiểm tra quá trình đóng gói thay vì đổi URL endpoint theo tên thư mục mã nguồn.

## 7. SBOM bổ sung từ tệp ngoài và tiền tố optional

### 7.1. Đăng ký một id từ tệp ngoài

Giả sử quy trình triển khai cung cấp tài liệu `inventory/system.cdx.json` bên ngoài JAR. Có thể thêm:

```properties
management.endpoint.sbom.additional.system.location=file:./inventory/system.cdx.json
management.endpoint.sbom.additional.system.media-type=application/vnd.cyclonedx+json
```

Khi tài liệu sẵn có trong môi trường chạy, id được dùng để đọc là `system`, tương ứng `/actuator/sbom/system`. Tên `system.cdx.json` và thư mục `inventory` thuộc vị trí tài nguyên, không phải các đoạn tự động nối vào URL.

Trong thí nghiệm, có thể tạo tệp ngoài bằng cách sao chép tài liệu mẫu `platform.cdx.json` vào vị trí này. Điều đó chỉ phục vụ kiểm tra đường dẫn; nội dung sao chép vẫn mô tả mẫu cũ cho tới khi bạn thay nó bằng bảng kê thực tế.

Kiểm tra trước khi chạy:

- Đường dẫn được giải từ thư mục làm việc nào?
- Tệp có xuất hiện trong máy/container của ứng dụng không?
- Tài khoản chạy ứng dụng có đọc được tệp không?
- Nội dung có đúng định dạng đã khai báo không?

Một đường dẫn thiếu tiền tố `optional:` được dùng như tài nguyên bắt buộc trong cấu hình này; tệp không tồn tại có thể khiến khởi tạo endpoint thất bại khi ứng dụng khởi động. Cần đọc log thay vì mặc định rằng ứng dụng vẫn phục vụ HTTP bình thường.

### 7.2. Dùng optional khi tài liệu không bắt buộc

Nếu việc không có tài liệu được chấp nhận theo thiết kế, dùng:

```properties
management.endpoint.sbom.additional.system.location=optional:file:./inventory/system.cdx.json
management.endpoint.sbom.additional.system.media-type=application/vnd.cyclonedx+json
```

`optional:` cho phép tránh lỗi khởi động do tệp không tồn tại. Khi tệp chưa có lúc khởi tạo, Boot bỏ qua SBOM đó. Tiền tố này không tạo tài liệu hoặc tệp rỗng; sự có mặt của khóa cấu hình không chứng nhận id đã được công bố. Sau khi ứng dụng khởi động, đọc danh mục rồi kiểm tra tài liệu thực tế. [Optional SBOMs trong Spring Boot 3.3](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

Đừng dùng `optional:` để che một lỗi đóng gói của SBOM vốn bắt buộc phải có trong bản phát hành. Khi thay đổi cấu hình hoặc nguồn tài nguyên trong thí nghiệm, khởi động lại và kiểm tra lại; không suy ra cơ chế tự phát hiện lại tệp đang chạy nếu chưa xác minh hành vi đó.

### 7.3. Nhiều định dạng có thể cùng được công bố

Mỗi id có thể trỏ đến tài liệu riêng với định dạng và media type riêng. Ví dụ cấu hình cho một tài liệu SPDX JSON do quy trình triển khai cung cấp:

```properties
management.endpoint.sbom.additional.os.location=optional:file:./inventory/os.spdx.json
management.endpoint.sbom.additional.os.media-type=application/spdx+json
```

Đoạn này minh họa cấu hình cho tài liệu SPDX đã có; nó không biến tài liệu CycloneDX trong thí nghiệm thành SPDX. Với các định dạng khác nhau, bộ phân tích phải đọc đúng cấu trúc tương ứng; không mặc định mọi SBOM đều có mảng `components` của CycloneDX.

Giá trị `Content-Type` cần khớp với dữ liệu thực. Chỉ đổi `media-type` không thực hiện chuyển đổi JSON/XML, đổi chuẩn SBOM hoặc bổ sung các trường thiếu.

## 8. Liên hệ với SBOM được tạo trong lúc build

Trong quy trình thực tế, bảng kê thường được tạo từ đồ thị phụ thuộc của đúng bản build, đóng gói cùng artifact rồi mới được phục vụ qua endpoint.

Với một dự án dùng Spring Boot Gradle plugin 3.3, tài liệu của nhánh này hướng dẫn thêm CycloneDX Gradle plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.cyclonedx.bom' version '1.8.2'
}
```

Đây là phần `plugins` thay thế cho một thí nghiệm tạo bảng kê tự động trên dự án ví dụ; các cấu hình phụ thuộc và Java còn lại vẫn cần được giữ. Phiên bản plugin trên là ví dụ được tài liệu Boot 3.3 sử dụng. [Tạo CycloneDX SBOM trong lúc build](https://docs.spring.io/spring-boot/3.3/how-to/build.html)

Boot Gradle plugin cấu hình tác vụ CycloneDX, đưa SBOM vào vùng `META-INF/sbom` của artifact và thêm thông tin `Sbom-Format`/`Sbom-Location` vào manifest. Kiểm tra artifact và manifest thực tế để xác định tên/vị trí đầu ra của bộ plugin đang dùng. [Tích hợp CycloneDX của Boot Gradle plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html)

Khi muốn thử cơ chế tự phát hiện tài liệu vừa sinh, bỏ cấu hình `management.endpoint.sbom.application.location` đang trỏ tới tài liệu viết tay, build lại và chạy artifact mới. Sau đó đọc `/actuator/sbom/application` và kiểm tra tài liệu thực sự nhận được.

Nếu vẫn giữ vị trí tường minh trỏ đến tệp mẫu, việc thêm plugin tạo SBOM không tự bảo đảm endpoint đã chuyển sang tài liệu mới. Đây là lý do phải lần theo cả cấu hình, artifact và phản hồi thay vì chỉ nhìn thấy id `application`.

Ba giai đoạn có trách nhiệm khác nhau:

```text
Công cụ build
    -> tạo bảng kê theo phạm vi phụ thuộc được cấu hình

Quy trình đóng gói/triển khai
    -> mang đúng tài liệu đến môi trường chạy

Endpoint sbom
    -> công bố danh mục và phục vụ tài liệu được chọn
```

Thêm SBOM bổ sung không tự mở rộng phạm vi quét của công cụ build. Chẳng hạn bảng kê lớp hệ điều hành hoặc một thành phần ngoài JVM phải được tạo và cung cấp bởi quy trình phù hợp với phạm vi đó. [Tổng quan hỗ trợ SBOM của Spring Boot 3.3](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

## 9. Giới hạn bằng chứng và các lỗi thường gặp

HTTP 200 ở danh mục cho biết thao tác đọc danh mục thành công. HTTP 200 ở một tài liệu cho biết yêu cầu đã nhận được nội dung. Hai kết quả đó chưa tự chứng minh:

- Tài liệu tuân thủ đầy đủ đặc tả SBOM được tuyên bố.
- Danh sách thành phần bao phủ toàn bộ ứng dụng, image hoặc hệ điều hành.
- Tài liệu tương ứng chính xác với artifact đang triển khai nếu nguồn tệp ngoài đã bị thay đổi.
- Các thành phần đều không có lỗ hổng hoặc mọi thông tin giấy phép đều chính xác.

Những kết luận này cần các bước xác thực định dạng, kiểm tra phạm vi, liên kết với artifact và phân tích chuyên biệt. Trong thí nghiệm, hai tệp nhỏ giúp kiểm tra luồng phục vụ; không dùng chúng làm bằng chứng đầy đủ cho một bản phát hành.

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| 404 ở `/actuator/sbom` | Đúng cổng/base path, bật endpoint, HTTP exposure và cấu hình endpoint chưa? |
| Có danh mục nhưng id mong đợi không hiện diện | Kiểm tra khóa cấu hình, tài nguyên, bản triển khai và tài liệu nào thật sự sẵn có. |
| Một id không truy xuất được | Dùng đúng id từ danh mục; kiểm tra log và nguồn tài nguyên. |
| 401 hoặc 403 | Kiểm tra xác thực và quyền truy cập HTTP. |
| Ứng dụng không khởi động sau khi thêm SBOM | Kiểm tra tài nguyên bắt buộc có tồn tại/đọc được không và log lỗi khởi tạo. |
| JSON tải về không đọc được | Tách header khỏi phần thân, kiểm tra mã HTTP và nội dung thực tế. |
| Header đúng nhưng công cụ SBOM từ chối | Kiểm tra cấu trúc tài liệu theo đặc tả; khai báo media type không xác thực nội dung. |
| Chạy IDE được nhưng chạy JAR lỗi | Kiểm tra tài nguyên đóng gói, cấu hình classpath và vị trí tệp ngoài. |
| Đã build SBOM mới nhưng endpoint còn trả bản mẫu | Kiểm tra `application.location`, artifact được chạy và tài liệu tải về. |

Trong triển khai nhiều bản sao, xác định bản sao nào trả phản hồi. Cùng một đường dẫn `file:` không bảo đảm các máy/container có cùng byte. Nếu cần chứng minh tính đồng nhất, đối chiếu tài liệu hoặc checksum với nguồn phát hành đã xác định.

## 10. Thực hành và tự kiểm tra

Thực hiện trên dự án độc lập:

1. Chạy với hai tài nguyên classpath, đọc danh mục và xác nhận hai id `application`, `platform`.
2. Đọc từng tài liệu, kiểm tra `Content-Type` và hai tên `metadata.component.name` khác nhau.
3. Tải tài liệu ứng dụng ra tệp, đối chiếu hash với đúng tài nguyên của thí nghiệm.
4. Build và chạy executable JAR, tìm hai tài nguyên trong archive rồi lặp lại bước đọc.
5. Đăng ký `system` từ tệp ngoài đã chuẩn bị; kiểm tra đường dẫn theo thư mục làm việc và đọc lại danh mục.
6. Trong một lần chạy riêng, thử cấu hình tệp không tồn tại có `optional:`; so sánh log khởi động, danh mục và khả năng đọc tài liệu với cấu hình tài nguyên bắt buộc.

Các câu hỏi cần trả lời được:

- Vì sao `platform` trong URL không nhất thiết trùng tên tệp hoặc tên thành phần trong SBOM?
- Tệp đặt ở `src/main/resources` được định vị thế nào khi chạy từ executable JAR?
- `additional.system.location` có tự hợp nhất thành phần vào `application` không?
- Vì sao `optional:` không phải bằng chứng rằng tài liệu đang sẵn có?
- Vì sao đổi `media-type` không đổi định dạng nội dung?
- Cần kiểm tra gì để biết endpoint đang phục vụ bảng kê của đúng bản build?

Câu trả lời cần nối được định danh, vị trí tài nguyên, cấu hình định dạng, artifact và nội dung phản hồi; đó là các bằng chứng cần thiết để đọc SBOM có căn cứ.
