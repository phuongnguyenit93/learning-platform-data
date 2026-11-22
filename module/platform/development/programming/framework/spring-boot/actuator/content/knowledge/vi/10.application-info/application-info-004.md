# Đọc metadata bản dựng từ META-INF/build-info.properties

Khi hai máy cùng chạy một ứng dụng nhưng cho kết quả khác nhau, câu hỏi đầu tiên thường là: “Hai máy có thực sự chạy cùng bản dựng không?”. Thông tin trong kho mã nguồn chưa trả lời được điều đó: tệp JAR đang triển khai có thể được tạo từ một lần dựng trước.

Metadata bản dựng là một nhóm dữ liệu mô tả sản phẩm đã được tạo, chẳng hạn tên, tọa độ thư viện, phiên bản và thời điểm dựng. Spring Boot có quy ước lưu dữ liệu này tại `META-INF/build-info.properties` trên classpath, đọc thành đối tượng `BuildProperties`, rồi có thể đưa vào thông tin ứng dụng của Actuator.

Bài này tập trung vào đường đi **tệp tài nguyên → BuildProperties → mã ứng dụng**, đồng thời giải thích vị trí của Actuator trong đường đi đó. Ví dụ sử dụng Java 21 và Spring Boot 3.3.0; các liên kết API phía dưới thuộc dòng 3.3.

## 1. Hiểu đúng dữ liệu mình đang đọc

### 1.1. Bản dựng, tiến trình đang chạy và mã nguồn là những đối tượng khác nhau

Giả sử một JAR phiên bản `1.2.0` được dựng lúc 04:05 UTC, sau đó được khởi động lại nhiều lần. Trường `build.time` vẫn mô tả lần dựng ấy, không trở thành thời điểm khởi động mới.

Cũng cần phân biệt:

- Phiên bản ứng dụng do dự án đặt, ví dụ `1.2.0`.
- Mã định danh commit do Git quản lý.
- Thời điểm bắt đầu một tiến trình JVM.
- Thời điểm đóng gói bản dựng.

Một phiên bản có thể bị dùng lại cho nhiều lần dựng; một commit có thể được dựng nhiều lần. Vì thế, đừng xem riêng `build.version` là bằng chứng hai tệp JAR giống hệt nhau, hay xem metadata do ứng dụng tự công bố là cơ chế xác minh tính toàn vẹn.

### 1.2. Tệp .properties chứa những gì?

Đây là dữ liệu mẫu cố định dùng cho bài thực hành:

```properties
build.group=com.example
build.artifact=build-info-demo
build.name=Build Info Demo
build.version=1.2.0
build.time=2025-02-03T04:05:06Z
build.channel=training
```

| Khóa trong tệp | Ý nghĩa trong ví dụ | Cách đọc từ BuildProperties |
| --- | --- | --- |
| `build.group` | Nhóm dự án `com.example` | `getGroup()` |
| `build.artifact` | Tên sản phẩm `build-info-demo` | `getArtifact()` |
| `build.name` | Tên hiển thị `Build Info Demo` | `getName()` |
| `build.version` | Phiên bản `1.2.0` | `getVersion()` |
| `build.time` | Thời điểm dựng, biểu diễn bằng UTC | `getTime()` trả về `Instant` |
| `build.channel` | Thuộc tính bổ sung của ví dụ | `get("channel")` |

Tên hiển thị và tên sản phẩm có thể khác nhau. `Build Info Demo` phục vụ việc đọc, còn `build-info-demo` phù hợp để nhận diện sản phẩm trong hệ thống đóng gói.

Các phương thức truy cập chuẩn có thể trả về `null` khi trường tương ứng không có. `getTime()` cũng có thể trả về `null` khi giá trị thời gian không phân tích được; khi đó có thể đọc giá trị gốc bằng `get("time")` để chẩn đoán. Xem [API BuildProperties 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html).

## 2. Tệp trở thành bean như thế nào?

### 2.1. Vị trí trên classpath

Đường dẫn mặc định của Spring Boot là:

```text
classpath:META-INF/build-info.properties
```

Nếu viết tệp mẫu bằng tay để học, đặt nó ở:

```text
src/main/resources/META-INF/build-info.properties
```

Nếu tạo bằng tác vụ Gradle của Spring Boot 3.3, vị trí đầu ra thường là:

```text
build/resources/main/META-INF/build-info.properties
```

Với executable JAR theo bố cục mặc định của `bootJar`, tài nguyên ứng dụng nằm ở:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

`BOOT-INF/classes/` là chi tiết đóng gói. Mã ứng dụng vẫn tra cứu `META-INF/build-info.properties` từ classpath.

Không nối đường dẫn thư mục dự án để đọc tài nguyên này bằng `new File(...)`. Cách đó có thể chạy trong IDE nhưng thất bại khi tài nguyên nằm bên trong JAR. Khi cần tự đọc, dùng luồng tài nguyên; trong ứng dụng Spring Boot thông thường, nên dùng bean đã được cấu hình sẵn.

### 2.2. Bỏ tiền tố build. là công việc của cấu hình tự động

Trong ứng dụng có cấu hình tự động của Spring Boot, `ProjectInfoAutoConfiguration`:

1. Kiểm tra tài nguyên tại vị trí đã cấu hình.
2. Nếu tài nguyên tồn tại và chưa có bean `BuildProperties`, nạp nội dung tệp.
3. Chọn các khóa bắt đầu bằng `build.`.
4. Bỏ tiền tố đó rồi tạo `BuildProperties`.

Vì vậy, ánh xạ thực tế là:

```text
Tệp:                 build.version=1.2.0
Khóa trong đối tượng: version
Cách đọc:             build.getVersion() hoặc build.get("version")
```

Thuộc tính bổ sung cũng theo cùng quy tắc:

```text
Tệp:                 build.channel=training
Khóa trong đối tượng: channel
Cách đọc:             build.get("channel")
```

`build.get("build.version")` không tìm lại khóa trong tệp gốc; trong ví dụ này nó trả về `null`. Ngược lại, một dòng chỉ ghi `version=1.2.0` trong tệp sẽ không được cơ chế trên nhập thành trường phiên bản.

Đây là hành vi của bước nạp trong [ProjectInfoAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/info/ProjectInfoAutoConfiguration.java). Không suy ra rằng constructor `new BuildProperties(properties)` luôn tự bỏ tiền tố: nếu tự tạo đối tượng, bên gọi phải cung cấp các khóa đã chuẩn hóa như `version`, `artifact`, `time`.

### 2.3. Có bean không đồng nghĩa có endpoint HTTP

Việc đọc `BuildProperties` có thể diễn ra trong ứng dụng không chạy máy chủ web. Actuator chỉ là một bên sử dụng thông tin đó.

Khi các điều kiện cấu hình phù hợp, `BuildInfoContributor` đưa thông tin vào nhóm `build` của endpoint `info`. Muốn truy cập bằng HTTP còn cần ứng dụng web, endpoint được bật, được công bố qua web và người gọi có quyền truy cập. Việc tệp tồn tại không tự giải quyết các điều kiện HTTP này.

## 3. Chọn cách cung cấp tệp cho bài thực hành

Có hai cách thực hành độc lập. **Chọn một cách cho mỗi lần chạy**, tránh tạo hai nguồn cạnh tranh cho cùng một tài nguyên.

### Cách A: Dùng tệp mẫu để cô lập việc đọc

Đặt nguyên nội dung mẫu ở mục 1.2 vào `src/main/resources/META-INF/build-info.properties`. Chưa bật `springBoot.buildInfo()`.

Cách này phù hợp khi muốn quan sát việc nạp bean và cách đọc dữ liệu trước khi học tác vụ dựng. Thời gian trong tệp là dữ liệu giả lập có chủ ý, không phải thời gian thực của lần biên dịch.

Trong dự án thực tế, viết tay phiên bản lâu dài dễ gây sai lệch: đổi `project.version` nhưng quên sửa tệp sẽ khiến ứng dụng công bố phiên bản cũ.

### Cách B: Để Gradle tạo tệp

Với Spring Boot Gradle Plugin 3.3, thêm `springBoot { buildInfo() }` để có tác vụ `bootBuildInfo`. Khi plugin Java được áp dụng, tác vụ `classes` được nối với tác vụ tạo thông tin này. Những trường chuẩn lấy từ thông tin dự án, và có thể thêm trường riêng.

Đó là cơ chế tạo tài nguyên, không phải thao tác gọi API vào ứng dụng đang chạy. Chi tiết DSL và đầu ra được mô tả tại [Spring Boot 3.3 — Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html).

Trong dự án nhiều module, phải cấu hình đúng dự án tạo ra JAR cần kiểm tra. Một `build-info.properties` được tạo ở module khác không tự trở thành metadata đúng của ứng dụng hiện tại.

## 4. Ví dụ hoàn chỉnh: đọc thông tin khi ứng dụng khởi động

Đây là một dự án độc lập nhỏ để thực hành, không cần controller hay cổng HTTP. Chuẩn bị JDK 21 và Gradle Wrapper 8.5. Lần dựng đầu cần tải plugin và dependency nếu chúng chưa có trong bộ nhớ đệm.

### 4.1. Cấu trúc tệp

```text
build-info-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/BuildInfoDemo.java
    └── resources/application.properties
```

Với Cách A, thêm `src/main/resources/META-INF/build-info.properties` và bỏ khối `springBoot` phía dưới. Với Cách B, giữ khối đó và không tạo tệp mẫu trong `src/main/resources`.

### 4.2. settings.gradle

```groovy
rootProject.name = 'build-info-demo'
```

### 4.3. build.gradle

```groovy
import java.time.Instant

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'com.example'
version = '1.2.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

springBoot {
    buildInfo {
        properties {
            name = 'Build Info Demo'
            time = Instant.parse('2025-02-03T04:05:06Z')
            additional = ['channel': 'training']
        }
    }
}
```

Ví dụ cố định `time` để người học đối chiếu kết quả. Khi dùng thời điểm dựng mặc định, bỏ dòng gán `time`; stdout ở trường đó sẽ thay đổi theo lần dựng.

Trong `additional`, viết `channel`, không viết `build.channel`: tác vụ tạo tệp chịu trách nhiệm thêm tiền tố. Không thêm mật khẩu, token hay dữ liệu cá nhân vào metadata đóng gói.

### 4.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

Các thiết lập này giúp ví dụ chỉ in dữ liệu cần quan sát. Tắt log như trên nhằm phục vụ bài thực hành; khi chẩn đoán lỗi khởi động, hãy bật lại log để đọc nguyên nhân.

### 4.5. BuildInfoDemo.java

```java
package example;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BuildInfoDemo {
    public static void main(String[] args) {
        SpringApplication.run(BuildInfoDemo.class, args);
    }

    @Bean
    ApplicationRunner printBuild(ObjectProvider<BuildProperties> provider) {
        return args -> {
            BuildProperties build = provider.getIfAvailable();
            if (build == null) {
                System.out.println("build-info=missing");
                return;
            }

            System.out.println("group=" + build.getGroup());
            System.out.println("artifact=" + build.getArtifact());
            System.out.println("name=" + build.getName());
            System.out.println("version=" + build.getVersion());
            System.out.println("time=" + build.getTime());
            System.out.println("channel=" + build.get("channel"));
            System.out.println("prefixedLookup=" + build.get("build.version"));
        };
    }
}
```

`ObjectProvider` cho phép xử lý trường hợp bean không được tạo vì thiếu tài nguyên, thường gặp khi IDE không chạy tác vụ tạo metadata. Nó không che mọi lỗi cấu hình: nếu tệp tồn tại nhưng không đọc được, quá trình tạo bean vẫn có thể thất bại.

Nếu thông tin bản dựng là điều kiện bắt buộc để vận hành, có thể tiêm trực tiếp `BuildProperties` và để ứng dụng dừng khi thiếu bean. Lựa chọn bắt buộc hay tùy chọn phải có chủ ý; đừng tự chế phiên bản “hợp lệ” để che sự thiếu dữ liệu.

### 4.6. Dựng và chạy JAR

Trên Windows, chạy từ thư mục dự án:

```powershell
.\gradlew.bat clean bootJar
java -jar build/libs/build-info-demo-1.2.0.jar
```

Trên Linux/macOS, thay lệnh đầu bằng `./gradlew clean bootJar`.

Với dữ liệu cố định ở trên, stdout của ứng dụng là:

```text
group=com.example
artifact=build-info-demo
name=Build Info Demo
version=1.2.0
time=2025-02-03T04:05:06Z
channel=training
prefixedLookup=null
```

Phần thông báo của Gradle là đầu ra của công cụ dựng, không nằm trong đoạn stdout ứng dụng vừa nêu.

Dòng cuối là một phép kiểm tra có chủ đích: nó chứng minh khác biệt giữa tên khóa trong tệp và tên khóa mà `BuildProperties` sử dụng. Không giữ phép tra cứu sai đó trong mã nghiệp vụ.

### 4.7. Quan sát khi không có tệp

Với Cách A, bỏ tệp mẫu rồi dựng sạch lại. Với Cách B, bỏ khối `springBoot { buildInfo { ... } }` rồi chạy lại `clean bootJar`.

Kết quả của ứng dụng:

```text
build-info=missing
```

Lệnh `clean` giúp tránh dùng lại tài nguyên được tạo từ lần trước. Nếu chỉ xóa cấu hình nhưng vẫn còn tệp trong đầu ra cũ, bạn có thể tưởng rằng Spring Boot tự sinh metadata trong lúc khởi động.

Ở đây, ứng dụng vẫn chạy vì thông tin được coi là tùy chọn. Điều đó khác với trường hợp bean có tồn tại nhưng riêng `build.version` bị thiếu: khi ấy chương trình vẫn in các dòng và dòng phiên bản sẽ là `version=null`.

## 5. Tự đọc tài nguyên khi thực sự cần

Nếu đang chẩn đoán dữ liệu thô, có thể đọc tài nguyên mà chưa đi qua bước bỏ tiền tố. Đoạn dưới là **một phương thức minh họa đặt trong lớp của ứng dụng Spring**, không phải chương trình độc lập:

```java
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.core.io.ClassPathResource;

static Properties readRawBuildInfo() throws IOException {
    var resource = new ClassPathResource("META-INF/build-info.properties");
    var raw = new Properties();

    try (Reader reader = new InputStreamReader(
            resource.getInputStream(), StandardCharsets.UTF_8)) {
        raw.load(reader);
    }

    return raw;
}
```

Ở lớp dữ liệu thô, phải tra cứu `raw.getProperty("build.version")`. Chưa có thao tác tự động bỏ tiền tố.

Đọc qua `getInputStream()` giúp tránh giả định tài nguyên là tệp nằm trực tiếp trên hệ thống tệp. `try-with-resources` đóng luồng sau khi đọc. Nếu tài nguyên không có, phương thức này ném lỗi I/O; nó không có nhánh dự phòng giống ví dụ dùng `ObjectProvider`.

Đoạn minh họa chọn UTF-8 một cách tường minh. Nếu có chuỗi ngoài ASCII, cần thống nhất cách sinh và cách đọc tệp; không xem `Properties.load(InputStream)` và `Properties.load(Reader)` là hai lựa chọn có cùng quy tắc giải mã. Mẫu metadata của bài dùng ASCII nên không phụ thuộc khác biệt này.

Đối với đường đi tiêu chuẩn của Spring Boot, tránh tự nạp lần nữa ở từng nơi cần phiên bản. Dùng chung `BuildProperties` giúp các thành phần cùng đọc một mô hình dữ liệu.

## 6. Liên hệ với /actuator/info

Ví dụ ở mục 4 cố ý không chạy web. Để quan sát cùng metadata qua HTTP trong một ứng dụng web thử nghiệm:

1. Thêm `spring-boot-starter-web` vào dependency.
2. Bỏ `spring.main.web-application-type=none`.
3. Giữ việc cung cấp tệp bằng một trong hai cách đã chọn.
4. Cấu hình công bố endpoint `info`.

Phần cấu hình bổ sung:

```properties
management.endpoints.web.exposure.include=health,info
management.info.build.enabled=true
```

Với đường dẫn quản trị và cổng mặc định, request là:

```http
GET /actuator/info HTTP/1.1
Host: localhost:8080
```

Phản hồi JSON có nhóm `build`; ví dụ dưới chỉ minh họa một số trường, không phải cam kết thứ tự hay toàn bộ response:

```json
{
  "build": {
    "artifact": "build-info-demo",
    "name": "Build Info Demo",
    "version": "1.2.0",
    "group": "com.example",
    "time": "2025-02-03T04:05:06Z",
    "channel": "training"
  }
}
```

`BuildInfoContributor` sử dụng chế độ đầy đủ, nên thuộc tính bổ sung cũng có thể được công bố. Xem [mã nguồn BuildInfoContributor](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/BuildInfoContributor.java) và [điều kiện tạo contributor](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.java).

Bật `management.info.build.enabled` không tạo tệp còn thiếu, không tạo bean từ hư không và không thay thế quy tắc bảo vệ HTTP. Nếu ứng dụng có Spring Security, người gọi vẫn phải đáp ứng cấu hình bảo mật của ứng dụng.

Metadata là dữ liệu có thể đọc từ sản phẩm đóng gói; việc chặn endpoint không biến token ghi trong tệp thành bí mật an toàn. Chỉ đưa vào đây những trường phù hợp để đi cùng bản phát hành.

## 7. Chẩn đoán theo thứ tự từ sản phẩm đến người đọc

Khi không thấy thông tin mong đợi, kiểm tra từng tầng, tránh thay nhiều cấu hình cùng lúc.

### 7.1. Kiểm tra tài nguyên trong đúng JAR

Trên Windows:

```powershell
jar tf build/libs/build-info-demo-1.2.0.jar |
    Select-String -SimpleMatch 'META-INF/build-info.properties'
```

Với executable JAR ở ví dụ, tìm mục:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Hãy kiểm tra JAR thực sự đang chạy. Xem tệp ở `src/main/resources` không chứng minh rằng nó đã được đưa vào sản phẩm đang triển khai.

### 7.2. Kiểm tra bean và khóa

| Hiện tượng | Điều cần phân biệt | Hướng kiểm tra |
| --- | --- | --- |
| Không có bean `BuildProperties` | Thiếu tài nguyên, đổi vị trí, hoặc không có cấu hình tự động tương ứng | Kiểm tra classpath của lần chạy và điều kiện cấu hình tự động |
| Có bean nhưng `getVersion()` là `null` | Bean tồn tại không bảo đảm mọi trường có giá trị | Kiểm tra dòng `build.version` trong tài nguyên thực tế |
| `get("build.version")` là `null` | Đang dùng tên khóa trước bước chuẩn hóa | Đổi thành `getVersion()` hoặc `get("version")` |
| `getTime()` là `null` | Trường thời gian bị bỏ hoặc không phân tích được | Kiểm tra `get("time")` và dữ liệu nguồn |
| Đọc đúng bean nhưng HTTP trả 404 | Đường đọc dữ liệu và đường công bố HTTP là hai tầng | Kiểm tra ứng dụng web, endpoint, exposure và base path |
| HTTP trả 401/403 | Yêu cầu đã gặp cơ chế bảo vệ | Kiểm tra xác thực và phân quyền, không sửa tệp để chữa lỗi HTTP |
| IDE không có metadata nhưng JAR có | Hai cách chạy có thể dùng đầu ra tài nguyên khác nhau | Chạy tác vụ tạo tài nguyên hoặc chọn chạy qua Gradle |
| Phiên bản vẫn cũ sau khi sửa cấu hình | Có thể đang dùng JAR hoặc tài nguyên cũ | Dựng sạch và đối chiếu đúng sản phẩm |

Nếu chủ ý đổi vị trí, có thể dùng cấu hình như sau:

```properties
spring.info.build.location=classpath:metadata/build-info.properties
```

Khi đó phải cung cấp tài nguyên ở vị trí mới. Đổi thuộc tính vị trí chỉ đổi nơi đọc, không chuyển tệp hay sinh nội dung. Nếu đã khai báo bean `BuildProperties` riêng, cấu hình tự động sẽ nhường cho bean đó; cần kiểm tra cả nguồn dữ liệu của bean tự khai báo.

### 7.3. Tránh nhầm với Environment

Việc Spring Boot đọc `META-INF/build-info.properties` thành `BuildProperties` không có nghĩa mọi khóa trong tệp tự động trở thành thuộc tính của `Environment`.

Vì vậy, không thay `build.getVersion()` bằng `@Value("${build.version}")` rồi mặc định rằng kết quả tương đương. Muốn dùng cách đọc từ `Environment` phải có một cơ chế nạp property source riêng; đó là một lựa chọn cấu hình khác cần quản lý rõ ràng.

Tương tự, `info.app.version` trong cấu hình môi trường, `Implementation-Version` trong manifest và `build.version` trong tài nguyên này là các nguồn khác nhau. Khi chẩn đoán, ghi rõ mình đã đọc từ đâu.

## 8. Những quyết định cần có trong dự án thực tế

**Ai tạo metadata?** Nên để quá trình dựng tạo thông tin từ cùng cấu hình tạo sản phẩm. Không sửa metadata bên trong JAR sau khi đóng gói để làm nó khớp với một phiên bản mong muốn.

**Có cần thời gian dựng không?** Giá trị thời gian tự thay đổi có thể làm đầu ra khác nhau và ảnh hưởng khả năng dùng lại kết quả dựng. Nếu chủ ý bỏ trường này, Spring Boot Gradle Plugin 3.3 hỗ trợ cấu hình sau; đây là lựa chọn thay thế cho khối `buildInfo` của ví dụ:

```groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
```

Khi trường bị loại, mã đọc phải chấp nhận `getTime() == null`. Bỏ thời gian không tự làm toàn bộ bản dựng trở nên tái lập; các đầu vào khác cũng phải được kiểm soát.

**Dữ liệu có cập nhật khi ứng dụng đang chạy không?** Bean tiêu chuẩn được tạo khi khởi động ngữ cảnh Spring; không có cơ chế mặc định theo dõi và đọc lại tệp mỗi khi nó thay đổi. Hãy kiểm tra sản phẩm mới và lần khởi động mới thay vì mong endpoint tự phản ánh một tệp vừa sửa ngoài tiến trình.

**Có thể tin metadata đến mức nào?** Dùng nó để nhận diện và chẩn đoán bản phát hành. Khi cần chứng minh hai sản phẩm giống nhau hoặc xác minh nguồn phát hành, bổ sung cơ chế kiểm tra checksum/chữ ký theo quy trình phát hành; không giao trách nhiệm đó cho chuỗi phiên bản.

## 9. Bài tập kiểm chứng

Thực hiện từng thay đổi riêng, dự đoán kết quả trước khi chạy:

1. Đổi phiên bản dự án thành `1.2.1` khi dùng Cách B, dựng sạch rồi chạy đúng JAR mới. `getVersion()` phải phản ánh phiên bản mới.
2. Đổi `build.channel=training` thành `build.channel=qa` khi dùng Cách A. `get("channel")` phải trả về `qa`.
3. Với Cách A, đổi riêng `build.version` thành `version`. Bean vẫn có thể được tạo do tài nguyên tồn tại, nhưng `getVersion()` trả về `null`.
4. Bỏ trường `build.time`. Bean vẫn dùng được, còn `getTime()` trả về `null`.
5. Ghi `build.time=not-a-time` trong tệp mẫu. `getTime()` trả về `null`, còn `get("time")` giữ giá trị không hợp lệ để chẩn đoán.
6. Chạy trường hợp không có tài nguyên. Giải thích vì sao ví dụ dùng `ObjectProvider` vẫn in được `build-info=missing`.
7. Nếu đã bật HTTP, tắt `management.info.build.enabled`. Kiểm tra rằng việc không còn nhóm `build` do contributor này cung cấp không đồng nghĩa bean đã biến mất.

Sau các phép thử, bạn cần giải thích được ba câu hỏi: tài nguyên nào đang được nạp, khóa đã qua chuẩn hóa hay chưa, và thành phần nào đang sử dụng thông tin đó. Ba điểm này giúp phân biệt lỗi dữ liệu bản dựng với lỗi cấu hình công bố Actuator.
