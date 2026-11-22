# Phân biệt info với endpoint sbom và điều kiện cung cấp danh mục thành phần phần mềm

## 1. Hai câu hỏi khác nhau về cùng một ứng dụng

Khi một dịch vụ đang chạy, người vận hành có thể cần biết hai việc:

- “Đây là ứng dụng nào, phiên bản nào, được tạo từ lần build hoặc commit nào?”
- “Bản ứng dụng này được tạo từ những thành phần phần mềm nào, với phiên bản và quan hệ phụ thuộc ra sao?”

`info` phục vụ câu hỏi thứ nhất bằng thông tin tổng quan do ứng dụng cung cấp. `sbom` phục vụ câu hỏi thứ hai bằng tài liệu danh mục thành phần phần mềm, gọi là **Software Bill of Materials — SBOM**.

Có thể hình dung `info` như nhãn nhận diện của một sản phẩm, còn SBOM là danh mục nguyên liệu đi kèm đúng sản phẩm đó. Nhãn “dịch vụ thanh toán, phiên bản 1.0.0” không đủ để suy ra toàn bộ thư viện đã được đóng gói.

Endpoint `sbom` được bổ sung từ Spring Boot 3.3.0. Bài này dùng hành vi của dòng **Spring Boot 3.3.x**, Java 21; không áp dụng nguyên xi cấu hình endpoint của các dòng phiên bản khác. [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)

## 2. info và sbom khác nhau ở dữ liệu và trách nhiệm

| Tiêu chí | `info` | `sbom` |
| --- | --- | --- |
| Mục tiêu | Nhận diện, mô tả ứng dụng | Cung cấp tài liệu về các thành phần phần mềm |
| Nguồn chính | Các bean `InfoContributor` | Tệp SBOM được tạo hoặc cung cấp trước |
| Dạng kết quả | Đối tượng JSON gồm những phần thông tin được đóng góp | Danh sách ID SBOM, hoặc nội dung một tài liệu theo ID |
| Mức độ chi tiết | Do từng bộ đóng góp thông tin quyết định | Do công cụ sinh SBOM, định dạng và phạm vi thu thập quyết định |
| Có tự quét lỗ hổng không? | Không | Không; tài liệu SBOM có thể được công cụ khác sử dụng để phân tích |
| Có thay thế nhau không? | Không thay thế danh mục thành phần | Không thay thế thông tin nhận diện ứng dụng |

### 2.1. info tổng hợp thông tin từ các bộ đóng góp

`GET /actuator/info` trả thông tin do các `InfoContributor` đóng góp. Chẳng hạn một ứng dụng có thể công bố tên, phiên bản, thông tin build hoặc Git. [Info REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html)

Ví dụ JSON sau chỉ là một cấu hình thông tin có chủ đích, không phải cấu trúc mà mọi ứng dụng bắt buộc phải có:

```json
{
  "app": {
    "name": "payment-service",
    "version": "1.0.0"
  }
}
```

Các trường thường gặp có điều kiện riêng: thông tin `build` gắn với tài nguyên `META-INF/build-info.properties`; thông tin `git` gắn với `git.properties`. Riêng các thuộc tính `info.*` cần bật bộ đóng góp `env` trong dòng 3.3. Việc có một trường `version` không có nghĩa là đã có danh sách mọi dependency. [Application Information](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info)

Nếu không có bộ đóng góp nào tạo dữ liệu, kết quả `{}` vẫn có thể là phản hồi thành công của `info`. Phải phân biệt “endpoint đã xử lý yêu cầu nhưng không có dữ liệu” với “URL không tồn tại”.

### 2.2. sbom có thao tác liệt kê và thao tác lấy tài liệu

Với tiền tố mặc định `/actuator`:

| Yêu cầu HTTP | Ý nghĩa |
| --- | --- |
| `GET /actuator/sbom` | Lấy các ID SBOM hiện có |
| `GET /actuator/sbom/application` | Lấy tài liệu có ID `application` |
| `GET /actuator/sbom/{id}` | Lấy một tài liệu khác đã đăng ký |

Nếu chỉ có SBOM của ứng dụng, thao tác liệt kê trả:

```json
{"ids":["application"]}
```

Phản hồi lấy một SBOM phụ thuộc vào định dạng của chính tài liệu. Ví dụ, CycloneDX JSON dùng media type `application/vnd.cyclonedx+json`. Không được coi đối tượng `ids` là toàn bộ danh mục thành phần. [SBOM REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

Một SBOM hữu ích có thể mô tả tên, phiên bản, định danh gói, giấy phép, mã băm và quan hệ phụ thuộc; mức đầy đủ phụ thuộc đầu vào và công cụ tạo tài liệu. Không nên khẳng định mọi SBOM đều có đủ các trường này.

Cũng cần tách **SBOM của ứng dụng Java** khỏi **SBOM của toàn bộ môi trường chạy**. Một tài liệu được sinh từ dependency Java không tự chứng minh rằng nó đã liệt kê cả hệ điều hành, JVM, container image hoặc phần mềm được cài thêm ở máy chủ.

## 3. Điều kiện để thực sự cung cấp được SBOM qua HTTP

Đây là hai đường xử lý nối tiếp nhau:

```text
Lúc build:
Đồ thị phụ thuộc → công cụ sinh SBOM → tệp gắn với bản build → đóng gói/phân phối

Lúc chạy:
Tài nguyên SBOM đọc được → endpoint được bật và công bố → kiểm soát truy cập → người dùng lấy tài liệu
```

Tạo được tệp chưa có nghĩa là HTTP đã truy cập được. Ngược lại, có URL endpoint chưa có nghĩa là ứng dụng đã có tài liệu để cung cấp.

### 3.1. Có Actuator và hạ tầng HTTP

Trong ứng dụng web Spring Boot thông thường, cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đoạn trên là **phần khai báo dependency**, giả định phiên bản đã được quản lý bằng BOM hoặc cơ chế dependency management. Nó không phải một `build.gradle` độc lập.

`spring-boot-starter-web` ở đây chọn Spring MVC để minh họa. Ứng dụng dùng WebFlux có thể dùng starter tương ứng; không cần thêm cả hai chỉ để sử dụng SBOM.

### 3.2. Bật endpoint và công bố qua HTTP là hai việc riêng

Với Spring Boot 3.3:

```properties
management.endpoint.info.enabled=true
management.endpoint.sbom.enabled=true
management.endpoints.web.exposure.include=health,info,sbom
```

- `management.endpoint.sbom.enabled` điều khiển việc bật endpoint.
- `management.endpoints.web.exposure.include` chọn những endpoint được công bố qua HTTP.
- Nếu có `management.endpoints.web.exposure.exclude` tương ứng, danh sách loại trừ được ưu tiên.
- Mặc định chỉ `health` được công bố qua HTTP; việc một endpoint được bật không tự làm URL của nó truy cập được.

Các thuộc tính `management.endpoint.*` dùng số ít; nhóm `management.endpoints.web.*` dùng số nhiều. Gõ sai nhóm có thể khiến cấu hình không tác động đến endpoint dự định. [Enabling and Exposing Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

Ví dụ trong bài giả định không đổi management port, context path, tiền tố endpoint hay ánh xạ đường dẫn. Nếu ứng dụng có thay đổi những giá trị đó, phải sử dụng địa chỉ thực tế thay cho `http://localhost:18083/actuator/...`.

### 3.3. Có tài liệu ở vị trí endpoint nhận biết và đọc được

Với cách nhận diện mặc định trong dòng 3.3, các vị trí quen thuộc là:

```text
classpath:META-INF/sbom/bom.json
classpath:META-INF/sbom/application.cdx.json
```

Tài nguyên mặc định được nhận diện trở thành SBOM có ID `application`. Nếu dùng vị trí khác, có thể chỉ rõ vị trí thay vì dựa vào mặc định. [SBOM support in Spring Boot 3.3](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

Cần kiểm tra **bản được chạy**, không chỉ kiểm tra thư mục mã nguồn. Chẳng hạn tệp chỉ có trong `build/reports` trên máy lập trình nhưng không được đóng gói hay gắn vào môi trường chạy thì không đủ để endpoint cung cấp nó.

Các tài nguyên cũng phải có quyền đọc phù hợp. Với tệp ngoài ứng dụng, đường dẫn ở máy phát triển không tự tồn tại trong container hoặc máy chủ triển khai.

### 3.4. Người gọi được phép truy cập

Công bố endpoint và xác thực/phân quyền là những lớp khác nhau. Nếu Spring Security có mặt và ứng dụng chưa tự định nghĩa `SecurityFilterChain`, cấu hình bảo mật Actuator mặc định bảo vệ các endpoint ngoài `health`. Khi ứng dụng tự định nghĩa chuỗi lọc, cần kiểm tra chính các quy tắc của ứng dụng. [Actuator Security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

Ví dụ thực hành dưới đây không thêm Spring Security và chỉ bind vào `127.0.0.1` để tập trung quan sát dữ liệu. Khi triển khai thực tế, nên giới hạn quyền đọc SBOM cho đối tượng cần dùng vì tài liệu có thể tiết lộ công nghệ và phiên bản thư viện.

### 3.5. Nội dung phải tương ứng với đúng bản ứng dụng

Để endpoint có ý nghĩa cho vận hành, tài liệu phải mô tả bản đang chạy:

- Thay đổi dependency thì tạo lại SBOM cùng bản build.
- Không lấy SBOM của một bản phát hành cũ gắn vào bản mới.
- Kiểm tra phạm vi thu thập: dependency lúc chạy, dependency kiểm thử và thành phần ngoài Java không phải cùng một tập.
- Nếu dùng tệp gắn ngoài, giữ sự liên kết giữa phiên bản ứng dụng và phiên bản tệp.

Ví dụ: `info.app.version=1.0.0` và một tài liệu có tên “payment-service 1.0.0” vẫn chỉ là hai chuỗi dữ liệu. Tên giống nhau chưa chứng minh tệp đã được tạo từ đúng dependency của lần build đó.

## 4. Thực hành độc lập: quan sát info và sbom

Mục đích là kiểm tra sự khác nhau giữa **dữ liệu nhận diện** và **tài liệu thành phần**. Ví dụ dùng một SBOM mẫu viết tay để có đầu vào nhỏ, dễ đối chiếu. Tệp mẫu **không phải SBOM đầy đủ của ứng dụng**, vì không liệt kê các thư viện Spring và Tomcat thực sự được dùng.

Tạo một dự án riêng đã có **Gradle Wrapper 8.5** và **JDK 21**. Ví dụ khóa Spring Boot ở `3.3.0` để tái lập hành vi đầu dòng 3.3; đây là mốc minh họa, không phải khẳng định về phiên bản phát hành mới nhất.

### 4.1. Cấu trúc dự án

```text
actuator-sbom-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/
    ├── java/example/SbomDemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/sbom/application.cdx.json
```

Các tệp `gradlew`, `gradlew.bat` và `gradle/wrapper` là bộ Wrapper có sẵn, không thay bằng một tệp văn bản rỗng.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-sbom-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

BOM trong `platform(...)` quản lý phiên bản dependency; nó không phải tệp SBOM để endpoint trả về. Dù cùng có chữ “BOM”, hai khái niệm có trách nhiệm khác nhau.

### 4.2. Chương trình Java

`src/main/java/example/SbomDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SbomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SbomDemoApplication.class, args);
    }
}
```

Đây là lớp khởi động hoàn chỉnh của dự án Spring Boot, được biên dịch với dependency của dự án; không phải chương trình chỉ dùng thư viện chuẩn để chạy bằng `javac SbomDemoApplication.java`.

### 4.3. Cấu hình hai nguồn dữ liệu

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18083

management.endpoint.info.enabled=true
management.endpoint.sbom.enabled=true
management.endpoints.web.exposure.include=health,info,sbom

management.info.env.enabled=true
info.app.name=actuator-sbom-demo
info.app.version=1.0.0
```

Ở đây `management.info.env.enabled` chỉ bật bộ đóng góp đọc `info.*` cho endpoint `info`. Nó không tạo tài liệu SBOM và không bật endpoint `env`.

`src/main/resources/META-INF/sbom/application.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "actuator-sbom-demo",
      "version": "1.0.0"
    }
  },
  "components": []
}
```

`components: []` là lựa chọn cố ý của dữ liệu thực hành, để quan sát cơ chế cung cấp tệp. Không được từ đó kết luận ứng dụng Spring Boot không có dependency.

### 4.4. Build và chạy

Trong PowerShell tại thư mục dự án minh họa:

```powershell
.\gradlew.bat clean bootJar
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar
```

Trên Linux/macOS, dùng `./gradlew clean bootJar` và `java -jar build/libs/actuator-sbom-demo-1.0.0.jar`. Lần build đầu cần tải Gradle/plugin/dependency nếu máy chưa có cache.

Mở terminal thứ hai. Dùng `curl.exe` trên Windows để tránh nhầm với alias của PowerShell:

```powershell
curl.exe -sS http://localhost:18083/actuator/info
curl.exe -sS http://localhost:18083/actuator/sbom
curl.exe -i http://localhost:18083/actuator/sbom/application
```

Với đúng cấu hình mẫu, không có bộ đóng góp bổ sung, hai body JSON đầu tiên tương đương:

```json
{"app":{"name":"actuator-sbom-demo","version":"1.0.0"}}
```

```json
{"ids":["application"]}
```

Yêu cầu thứ ba trả thành công với tài liệu JSON đã đặt ở `application.cdx.json`; media type dự kiến là `application/vnd.cyclonedx+json`. Không nên so sánh toàn bộ HTTP header theo từng byte vì chúng còn phụ thuộc máy chủ và môi trường. Với JSON, thứ tự thuộc tính và khoảng trắng không phải ý nghĩa nghiệp vụ.

Có thể kiểm tra tệp nằm trong JAR bằng:

```powershell
jar tf .\build\libs\actuator-sbom-demo-1.0.0.jar | Select-String 'sbom'
```

Với tệp tài nguyên tự đặt trong ví dụ, cần tìm được mục chứa `META-INF/sbom/application.cdx.json`. Lệnh liệt kê chỉ xác nhận sự có mặt của tệp; chưa xác nhận độ đầy đủ của danh mục thành phần.

### 4.5. Thay đổi từng điều kiện để hiểu kết quả

Mỗi lần thử, dừng tiến trình hiện tại rồi chạy lại JAR với tham số tương ứng.

**Thử A — Tắt riêng bộ đóng góp env:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.info.env.enabled=false
```

Với dự án mẫu không có dữ liệu build/Git hay bộ đóng góp tùy chỉnh, `info` trả `{}`. `sbom` vẫn có ID `application` vì tệp tài liệu vẫn còn.

**Thử B — Chỉ định một SBOM tùy chọn không tồn tại:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoint.sbom.application.location=optional:classpath:missing.cdx.json
```

Thuộc tính `application.location` đã chỉ rõ tài nguyên khác nên không tiếp tục dùng tệp mặc định của ví dụ. Vì tài nguyên được đánh dấu tùy chọn, ứng dụng vẫn có thể khởi động; nếu không có SBOM bổ sung, `GET /actuator/sbom` trả:

```json
{"ids":[]}
```

`info` vẫn có tên và phiên bản. Kết quả này cho thấy endpoint tồn tại và danh sách tài liệu rỗng là hai việc có thể xảy ra đồng thời.

**Thử C — Chỉ định tài nguyên bắt buộc bị thiếu:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoint.sbom.application.location=classpath:missing.cdx.json
```

Với endpoint vẫn được bật và công bố như cấu hình mẫu, quá trình tạo endpoint gặp tài nguyên bắt buộc không tồn tại và làm khởi động thất bại. Đây không phải trường hợp “khởi động thành công rồi trả danh mục rỗng”.

**Thử D — Bỏ sbom khỏi danh sách công bố HTTP:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoints.web.exposure.include=health,info
```

Truy cập `/actuator/info` vẫn có thể thành công nhưng `/actuator/sbom` không còn được ánh xạ qua HTTP trong cấu hình mẫu, dù tệp SBOM vẫn nằm trong JAR. Kết quả HTTP cụ thể có thể bị ảnh hưởng nếu bổ sung bộ lọc bảo mật hoặc gateway.

## 5. Từ tệp mẫu sang SBOM được tạo khi build

Trong ứng dụng thực, thay tệp viết tay bằng tài liệu được sinh từ đầu vào của đúng bản build. Spring Boot có hỗ trợ phối hợp với các plugin CycloneDX của Maven/Gradle. [Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/3.3/how-to/build.html#howto.build.generate-sbom)

Với dự án Gradle dùng Spring Boot 3.3, ví dụ tích hợp trong tài liệu dùng plugin:

```groovy
id 'org.cyclonedx.bom' version '1.8.2'
```

Đây là **một dòng thêm vào khối `plugins` hiện có**, không phải toàn bộ tệp build.

Khi cả plugin Spring Boot và plugin CycloneDX được áp dụng, Spring Boot cấu hình tác vụ sinh SBOM, đưa tài liệu vào `META-INF/sbom` của JAR/WAR và bổ sung thông tin vị trí/định dạng vào manifest. [Reacting to the CycloneDX Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html#reacting-to-other-plugins.cyclonedx)

Khi chuyển ví dụ sang cách sinh tự động, loại bỏ tệp SBOM mẫu viết tay để tránh tồn tại hai nguồn cùng mô tả ứng dụng. Sau đó build lại, kiểm tra tệp trong artifact và lấy lại tài liệu qua endpoint.

Cần lưu ý sự khác nhau giữa chạy từ artifact đã đóng gói và chạy trực tiếp lớp Java từ IDE. Luồng đóng gói có thể bổ sung tài liệu vào JAR, trong khi classpath của IDE chưa có cùng tệp đó. Vì vậy, nếu chỉ lỗi khi chạy IDE, hãy kiểm tra tài nguyên ở môi trường chạy đó trước khi kết luận endpoint bị lỗi.

Một luồng kiểm chứng hợp lý là: tạo SBOM từ build hiện tại → xác minh nội dung/phạm vi → kiểm tra artifact chứa tài liệu → chạy đúng artifact → tải tài liệu bằng ID → đối chiếu danh tính và phiên bản.

## 6. Chỉ định vị trí khác, định dạng khác và nhiều SBOM

Phần dưới là các cấu hình thay thế hoặc mở rộng; không cần bật đồng thời để chạy ví dụ cơ bản.

### 6.1. Tài liệu ứng dụng ở đường dẫn riêng

```properties
management.endpoint.sbom.application.location=classpath:inventory/application.spdx.json
management.endpoint.sbom.application.media-type=application/spdx+json
```

Cấu hình trên yêu cầu cung cấp tệp tương ứng ở `src/main/resources/inventory/application.spdx.json` trước khi build.

`media-type` mô tả kiểu nội dung được trả về. Đặt media type SPDX cho một tệp CycloneDX không chuyển đổi cấu trúc tài liệu. Nếu muốn đổi định dạng, cần dùng công cụ tạo/chuyển đổi tài liệu phù hợp.

### 6.2. Thêm SBOM của một phạm vi khác

```properties
management.endpoint.sbom.additional.system.location=optional:file:/opt/inventory/system.spdx.json
management.endpoint.sbom.additional.system.media-type=application/spdx+json
```

Đây là ví dụ đường dẫn trên Linux. Nếu tệp tồn tại trong môi trường chạy và có thể đọc được, endpoint có thêm ID `system`; lấy tài liệu đó bằng `GET /actuator/sbom/system`. `optional:` cho phép bỏ qua khi tệp thiếu; nó không sinh ra tài liệu thay thế. Việc chỉ định vị trí, media type và SBOM bổ sung được Spring Boot hỗ trợ qua các thuộc tính này. [SBOM configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sbom)

Không đặt nhầm cấu hình SBOM bổ sung vào `info.*`. Một đối tượng tự đặt tên `info.sbom` chỉ là dữ liệu cho `info` nếu bộ đóng góp tương ứng đọc nó; nó không tự đăng ký tài nguyên với endpoint `sbom`.

## 7. Chẩn đoán theo đúng lớp vấn đề

| Hiện tượng | Điều cần phân biệt | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `info` trả `{}` | Endpoint có thể hoạt động nhưng không có dữ liệu đóng góp | Bộ đóng góp, `management.info.env.enabled`, dữ liệu `info.*`, tài nguyên build/Git |
| `sbom` trả `{"ids":[]}` | Endpoint hoạt động nhưng không có tài liệu đã đăng ký | Tệp trên classpath, `application.location` và tài nguyên tùy chọn bị thiếu |
| `/sbom` có ID nhưng yêu cầu một ID khác trả lỗi không tìm thấy | URL tài liệu dùng ID không được liệt kê | Lấy danh sách trước và dùng đúng ID |
| HTTP 401 hoặc 403 | Có thể bị chặn ở lớp xác thực/phân quyền | Thông tin đăng nhập, vai trò, chuỗi lọc và gateway; mã lỗi chưa tự chứng minh tài liệu có hay không |
| HTTP 404 | Có thể sai URL, port, exposure, endpoint bị tắt hoặc sai ID | Phân biệt URL liệt kê với URL tài liệu; kiểm tra cấu hình đường dẫn và công bố |
| Khởi động thất bại sau khi đặt `location` | Có thể tham chiếu tài nguyên bắt buộc bị thiếu | Đường dẫn, mount, quyền đọc và log nguyên nhân gốc |
| Tải được SBOM nhưng thiếu thư viện mong đợi | Tài liệu có mặt chưa đồng nghĩa dữ liệu đầy đủ | Phạm vi công cụ sinh, dependency thực tế và bản build tạo ra tệp |

Không nên sửa mọi hiện tượng bằng cách bật toàn bộ endpoint. Cách sửa phải khớp lớp đang lỗi: dữ liệu, đóng gói, cấu hình endpoint, địa chỉ truy cập hay bảo mật.

## 8. Tự kiểm tra khả năng áp dụng

1. **`info` có phiên bản ứng dụng thì đã biết hết phiên bản thư viện chưa?**  
   Chưa. Phiên bản ứng dụng không suy ra danh mục dependency; cần đọc tài liệu SBOM phù hợp hoặc nguồn kiểm kê tương đương.

2. **Đã có tệp JSON trong máy lập trình thì chỉ thêm `sbom` vào exposure là đủ chưa?**  
   Chưa. Tệp phải có trong môi trường chạy ở vị trí endpoint nhận biết hoặc được cấu hình, đồng thời đọc được.

3. **Danh sách ID rỗng có đồng nghĩa endpoint bị tắt không?**  
   Không. Đó có thể là phản hồi thành công khi không có tài liệu nào được đăng ký.

4. **Bật endpoint có tự sinh hoặc cập nhật SBOM theo mỗi request không?**  
   Không. Phải tổ chức bước tạo/cung cấp tài liệu riêng; endpoint thực hiện việc cung cấp tài nguyên.

5. **Một SBOM Java có chứng minh toàn bộ container không có lỗ hổng không?**  
   Không. Cần xét phạm vi thành phần được kiểm kê và phân tích bằng công cụ phù hợp; bản thân danh mục không phải kết luận an toàn.

Sau bài thực hành, người học cần chỉ ra được ba bằng chứng riêng: `info` lấy dữ liệu từ đâu, SBOM được tạo/cung cấp từ đâu, và những cấu hình nào cho phép người có quyền lấy tài liệu của đúng bản ứng dụng đang chạy.
