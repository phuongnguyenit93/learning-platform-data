# Giới hạn Devtools ở môi trường phát triển và hành vi với ứng dụng đóng gói

`spring-boot-devtools` giúp rút ngắn vòng phản hồi trong quá trình phát triển Spring Boot: thay đổi classpath có thể kích hoạt **restart ApplicationContext**, thay đổi một số static resource có thể kích hoạt **LiveReload**, và các cấu hình mặc định được điều chỉnh để thuận tiện khi sửa giao diện/đọc lỗi. Nhưng những tiện ích này **không phải tính năng nên mang nguyên vào môi trường vận hành**.

Đặc biệt, có hai câu hỏi khác nhau:

1. **JAR/ảnh container cuối cùng có chứa dependency `spring-boot-devtools` không?**
2. **Nếu Devtools có trên classpath, nó có thực sự kích hoạt restart/LiveReload/default properties khi chạy theo cách hiện tại không?**

Trong **Spring Boot 3.3**, việc chạy ứng dụng đóng gói bằng `java -jar` thường được nhận diện là cách chạy kiểu production và Devtools **bị vô hiệu hóa mặc định**. Ngoài ra, **repackaged archives không chứa Devtools theo mặc định** khi dùng cơ chế build được Spring Boot khuyến nghị. Hai lớp hành vi này hỗ trợ nhau, nhưng **không nên nhầm “bị vô hiệu hóa” với “không có dependency trong artifact”**.

Bài Knowledge thuộc module **Spring Boot Application Runtime**, chương **Devtools**, áp dụng cho **Spring Boot 3.3.x, Java 17+, Gradle hoặc Maven**. Mục tiêu là hiểu giới hạn của Devtools trong local development, đối chiếu **IDE/`bootRun` với executable JAR**, thực hành kiểm tra file đã đóng gói, và thiết lập ranh giới an toàn giữa development/staging/production.

## 1. Devtools là gì và giải quyết vấn đề nào?

Spring Boot Devtools là **dependency dành cho giai đoạn phát triển**, có tên:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

Khi được đặt đúng ở development classpath và được kích hoạt, nó cung cấp các khả năng chính:

| Nhóm | Giá trị khi phát triển | Điều không nên suy diễn |
| --- | --- | --- |
| Automatic restart | Khởi tạo lại ứng dụng nhanh khi classpath được cập nhật | Không phải hot swap mọi Java bytecode ngay trong JVM |
| LiveReload | Thông báo browser đang bật LiveReload khi tài nguyên thích hợp thay đổi | Không phải tự động rebuild frontend hoặc thay code server ở production |
| Development property defaults | Tắt một số cache, hiển thị thêm thông tin phục vụ debug | Không nên xem là cấu hình mặc định an toàn cho production |
| Global/local Devtools settings | Điều chỉnh watcher, trigger file, restart behavior | Không thay thế quản lý cấu hình deployment |
| Remote development support | Một số tình huống dev có thể cập nhật ứng dụng từ xa, có kiểm soát | **Không bao giờ bật remote Devtools trên production** |

**Devtools không phải một môi trường ứng dụng `dev` theo nghĩa `spring.profiles.active=dev`.** Profile là cơ chế chọn cấu hình Spring. Devtools là module có mặt/không có mặt trên classpath, cùng với điều kiện cách khởi chạy và cờ kiểm soát riêng.

Ví dụ hai môi trường đều dùng profile `dev` nhưng một bên chạy `bootRun` (classpath dạng thư mục), một bên chạy executable JAR (classpath kiểu đóng gói). Hành vi Devtools có thể khác nhau dù profile giống nhau.

## 2. Hai lớp bảo vệ khác nhau: dependency và runtime activation

### Lớp A — Dependency có trong artifact không?

Nếu Devtools **không có trong JAR phát hành**, không có mã của module đó để tự kích hoạt. Đây là hàng rào mạnh hơn so với chỉ dựa vào runtime flag.

Cấu hình Gradle khuyến nghị:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Cấu hình Maven thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Trong Spring Boot 3.3, **repackaged executable archives không bao gồm Devtools theo mặc định**. Với Gradle, `developmentOnly` giữ dependency ở phạm vi phục vụ phát triển và tránh nó trở thành dependency transitively applied cho module khác. Với Maven, `optional=true` không chỉ định “cấm dùng trong mọi trường hợp”, mà đánh dấu dependency không nên bị kéo theo một cách transitively khi module được tiêu thụ bởi module khác.

### Lớp B — Nếu module vẫn có trên classpath thì nó có chạy không?

Spring Boot 3.3 còn dùng cách **phát hiện kiểu khởi chạy**. Khi dùng `java -jar` trên fully packaged application (hoặc classloader đặc biệt được xem như production launch), các tính năng Devtools thường bị **tắt tự động**.

Trong tài liệu, system property:

~~~properties
spring.devtools.restart.enabled=false
~~~

có thể dùng để tắt chức năng restart. Ngược lại, nếu đặt JVM system property `-Dspring.devtools.restart.enabled=true`, có thể **ép bật Devtools ngay cả với kiểu launch vốn bị xem là production**, miễn là module có trên classpath. **Không sử dụng cách ép bật này ở production** vì rủi ro bảo mật và ổn định.

**Quy tắc phát hành nên có cả hai:** loại Devtools khỏi artifact production **và** không dùng JVM/system/application properties ép bật các khả năng Devtools.

### Ma trận tình huống

| Tình huống | Devtools trên classpath? | Hành vi nên kỳ vọng |
| --- | --- | --- |
| IDE/classpath với `developmentOnly` | Có trong cấu hình phát triển | Restart/LiveReload/default dev properties có thể hoạt động |
| `./gradlew bootRun` với `developmentOnly` | Có ở development runtime | Có thể kích hoạt Devtools và giám sát classpath |
| `./gradlew bootJar` theo cấu hình chuẩn | **Không** trong repackaged JAR mặc định | Không có Devtools để kích hoạt |
| `java -jar` với JAR chuẩn ở trên | Không | Chạy như ứng dụng Spring Boot bình thường |
| Fully packaged JAR **cố ý nhúng Devtools** | Có | Mặc định Spring Boot xem đây là production-style launch và vô hiệu hóa tính năng Devtools |
| JAR cố ý nhúng Devtools **và bị ép `-Dspring.devtools.restart.enabled=true`** | Có | Có thể kích hoạt lại Devtools; **cấm trên production** |
| Container chạy exploded classpath **có Devtools** | Có thể có | Không nên dựa vào tên môi trường; phải xác minh classpath và activation thực tế |
| `spring.profiles.active=prod` nhưng chạy kiểu IDE với Devtools có mặt | Có | Profile `prod` **không tự bảo đảm module đã biến mất** |

Các hàng trên mô tả hành vi phổ biến của **Spring Boot 3.3**. Khi sử dụng plugin đóng gói đặc biệt, custom classloader, layered image, exploded archive hoặc build tool không chuẩn, **kiểm tra artifact và cách launcher chạy thật** thay vì dựa vào tên lệnh đơn thuần.

## 3. Cách thêm Devtools đúng trong Gradle

Với Spring Boot 3.3.x, dùng cấu hình `developmentOnly` thay vì viết:

~~~groovy
implementation 'org.springframework.boot:spring-boot-devtools'
~~~

Dòng `implementation` phía trên là **ví dụ về lựa chọn không được khuyến nghị cho mục đích chỉ phát triển**, vì trộn Devtools vào phạm vi dependency của ứng dụng thay vì tách rõ development-only. Đừng sao chép nó vào cấu hình mẫu bên dưới.

Cấu hình đầy đủ với Gradle native BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Chỉ dành cho chạy trong môi trường phát triển:
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Điểm dễ sai:** Spring Boot Gradle plugin không đồng nghĩa tất cả dependencies không ghi version đều tự được quản lý mà không có BOM/dependency-management mechanism. Trong ví dụ đã khai báo `platform(SpringBootPlugin.BOM_COORDINATES)`, nên starters và Devtools được phân giải theo bộ version đồng bộ của Spring Boot. Khi dự án đã dùng plugin `io.spring.dependency-management` hoặc version catalog phù hợp, nên giữ một chiến lược dependency management nhất quán.

Với **multi-module project**, đặt Devtools vào module ứng dụng phục vụ development theo nhu cầu thật; không kéo nó thành một dependency production của các library modules chỉ vì muốn IDE của dự án chính tự restart.

### Maven: `optional` và đóng gói là hai câu chuyện

Nếu ứng dụng dùng Maven, thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Maven plugin Spring Boot mặc định **loại Devtools khỏi repackaged archive**. `optional` ngăn dependency này tự bị kéo theo từ một module dùng library của bạn, nhưng **nó không có nghĩa “Devtools chắc chắn không có ở bất kỳ loại package nào”**. Nếu dùng một build system khác hoặc tự copy dependency vào image, phải kiểm tra lại artifact.

## 4. Khi nào Devtools theo dõi thay đổi và restart?

Một hiểu lầm phổ biến: “Chỉ cần lưu file `.java`, Devtools ngay lập tức đọc source và sửa code đang chạy.” Cách hoạt động đúng là:

1. Developer sửa source Java.
2. IDE hoặc Gradle/Maven **biên dịch lại class**.
3. Classpath directory chứa class/resource được cập nhật.
4. Devtools phát hiện **thay đổi classpath** thông qua file system watcher.
5. Nếu thay đổi phù hợp restart rules, Devtools đóng context cũ, thay restart classloader và tạo context mới.

~~~text
Sửa HelloController.java
   |
   v
Compile / Build Project / gradle classes
   |
   v
build/classes/java/main/HelloController.class thay đổi
   |
   v
Devtools FileSystemWatcher phát hiện
   |
   v
Đóng ApplicationContext đang chạy
   |
   v
Tạo restart ClassLoader mới
   |
   v
Khởi động lại context / Spring Boot application
   |
   v
Gọi lại HTTP endpoint -> thấy logic mới
~~~

**Nếu chỉ sửa source mà IDE không biên dịch và classpath không cập nhật, có thể không có restart.**

Tùy IDE:

- Eclipse/Spring Tools thường có cơ chế build/update classpath khi save.
- IntelliJ IDEA thường cần `Build Project` hoặc thiết lập auto-build phù hợp.
- Với Gradle `bootRun`, Devtools dùng classpath của main source set; khi compiler/Gradle cập nhật output, watcher có thể phát hiện.

### Restart không giống JVM process restart

Spring Boot Devtools dùng **hai classloaders**:

- **Base classloader**: các class từ thư viện JAR ít thay đổi.
- **Restart classloader**: các class thuộc project đang phát triển thường được nạp từ output directory.

Khi restart, restart classloader cũ bị loại bỏ và một classloader mới được tạo; không cần luôn tạo **một process JVM mới**. Nhờ giữ phần base đã nạp, chu kỳ có thể nhanh hơn khởi động lạnh.

Điều đó cũng có nghĩa:

- Mỗi restart thường tạo **ApplicationContext và các singleton beans mới**.
- Bean fields, static state thuộc restart classloader và in-memory cache của context có thể được reset.
- Các resource ngoài Spring context hoặc thread tự tạo không được dọn đúng có thể gây leak qua nhiều lần restart.
- Kết quả “restart trong 1 giây” **không tương đương** “cold production startup trong 1 giây” vì JVM, JIT và base classloader có thể đã warm.

**Devtools không phải một cơ chế thay thế rolling deployment, container restart hay phát hành JAR mới.**

## 5. LiveReload khác automatic restart

Devtools có thể khởi chạy một **LiveReload server** để thông báo browser đang bật LiveReload extension khi resource thay đổi. Nhưng ba hành vi cần phân biệt:

| Thay đổi | Hành vi mặc định thường gặp |
| --- | --- |
| Compiled Java class hoặc resource không nằm trong nhóm exclude | Trigger **application restart** |
| Static resource ở `/static`, `/public`, `/resources` hoặc template ở `/templates` | Thường **không restart context**, nhưng có thể tạo **LiveReload** |
| File `.java` vừa sửa nhưng chưa biên dịch, classpath không đổi | Không bảo đảm restart |
| File nằm ngoài classpath và không được cấu hình additional paths | Không tự được Devtools theo dõi |
| Code trong một JAR dependency thay đổi | Không phải cơ chế hot reload tổng quát; có thể cần rebuild/restart theo cách khác |

Một số đường resource được Spring Boot Devtools loại khỏi restart mặc định gồm:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

Nếu cần điều chỉnh loại trừ:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Cấu hình trên **thay thế** pattern loại trừ tương ứng theo yêu cầu. Nếu chỉ muốn **thêm** pattern vào danh sách mặc định, xem:

~~~properties
spring.devtools.restart.additional-exclude=uploads/**,generated/**
~~~

**Không thêm thư mục chứa dữ liệu production vào watcher** để “tiện debug”, vì Devtools có thể restart ứng dụng khi file do hệ thống thay đổi.

### LiveReload có cần browser extension?

Có. Devtools gửi tín hiệu LiveReload, nhưng browser cần **client hỗ trợ LiveReload** (thường là extension hoặc tích hợp tương ứng) để tự refresh. Đừng coi việc Devtools server chạy là bằng chứng mọi browser đã tự làm mới.

Chỉ nên có **một LiveReload server đang chạy trên một máy/cổng tương ứng**. Khi mở nhiều ứng dụng Devtools ở IDE, không phải app nào cũng có thể đồng thời chiếm LiveReload port.

Tắt LiveReload khi không cần:

~~~properties
spring.devtools.livereload.enabled=false
~~~

Dòng trên **chỉ tắt LiveReload**, không tự tắt restart hay xóa dependency khỏi classpath.

## 6. Devtools thay đổi property defaults: tiện khi dev, không nên dùng làm baseline production

Một số framework có cache để tối ưu throughput. Khi phát triển, cache có thể khiến sửa template/static resource mà refresh không thấy khác biệt. Devtools cung cấp **development-time property overrides**, ví dụ:

| Property | Devtools default phục vụ phát triển trong Spring Boot 3.3 |
| --- | --- |
| `spring.thymeleaf.cache` | `false` |
| `spring.freemarker.cache` | `false` |
| `spring.mustache.servlet.cache` | `false` |
| `spring.web.resources.cache.period` | `0` |
| `spring.web.resources.chain.cache` | `false` |
| `server.error.include-message` | `always` |
| `server.error.include-stacktrace` | `always` |

Đây là **một số ví dụ**, không phải toàn bộ bảng mặc định. Các framework không được đưa vào dự án (ví dụ không dùng Thymeleaf) có thể khiến property tương ứng không có tác động thực tế.

Devtools dễ làm môi trường local **khác production** theo nhiều chiều:

- Static/template caching khác nhau, khiến hiệu năng local không phản ánh hành vi production.
- HTTP error response có thể hiển thị **chi tiết bổ sung**, không nên để lộ trong môi trường public.
- Restart classloader và việc khởi động context nhiều lần thay đổi trạng thái.
- LiveReload/watcher bổ sung thread, cổng và cơ chế giám sát file.

Nếu muốn tắt **chỉ các Devtools property defaults** trong local:

~~~properties
spring.devtools.add-properties=false
~~~

**Cấu hình này không đồng nghĩa đã tắt automatic restart/LiveReload.**

### Không chạy load test production giả lập với Devtools đang hoạt động

Devtools có thể thay đổi caching và cơ chế classloading, vì vậy benchmark ở `bootRun` không đủ để kết luận về:

- Cold startup của executable JAR.
- Tải CPU/RSS và GC dưới lượng traffic thật.
- Độ trễ tĩnh/template có production caching.
- Hành vi classloader và dependency của container image phát hành.

Để kiểm chứng hành vi production, hãy chạy **artifact phát hành thật** bằng cách khởi chạy tương ứng với môi trường triển khai, cùng JDK/profile/memory limit.

## 7. Tắt restart đúng mức: property khác JVM system property

Tài liệu Spring Boot 3.3 phân biệt hai trường hợp:

### Tắt giám sát thay đổi nhưng vẫn khởi tạo phần hỗ trợ restart

Đặt trong `application.properties`:

~~~properties
spring.devtools.restart.enabled=false
~~~

Cách này **không theo dõi file để restart**, nhưng Spring Boot cho biết restart classloader vẫn có thể được khởi tạo. Nếu bạn đang gặp **vấn đề classloader**, chỉ thay property trong file cấu hình có thể chưa loại được toàn bộ cơ chế restart khỏi bootstrap.

### Vô hiệu hóa restart support từ rất sớm

Đặt **JVM system property trước khi `SpringApplication.run(...)`**:

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DisableRestartDemoApplication {

    public static void main(String[] args) {
        System.setProperty("spring.devtools.restart.enabled", "false");
        SpringApplication.run(DisableRestartDemoApplication.class, args);
    }
}
~~~

Đây là **class độc lập minh họa kỹ thuật tắt restart**; nó **không phải file dùng đồng thời trong dự án ví dụ chính ở phần 9**. Một dự án có hai lớp `@SpringBootApplication` cùng package có thể khiến component scan/conflicts, nên khi thử hãy dùng **một** entrypoint.

Có thể truyền khi khởi chạy:

~~~bash
java -Dspring.devtools.restart.enabled=false \
     -jar build/libs/devtools-scope-demo-1.0.0.jar
~~~

Lưu ý: `-D...` là **JVM system property**, phải đặt **trước `-jar`**. Đặt sau JAR trở thành application argument và không bảo đảm cùng thời điểm kích hoạt như system property.

**Quan điểm vận hành:** cần thực sự bảo đảm production không có Devtools thì **loại dependency khỏi artifact**. Tắt restart bằng property là biện pháp điều khiển runtime, không phải bằng chứng JAR không còn mã Devtools/remote support.

## 8. `spring.profiles.active` không thay thế dependency scoping

Ví dụ:

~~~properties
spring.profiles.active=prod
spring.devtools.restart.enabled=false
~~~

Có thể làm một môi trường **tắt restart** nhưng không chứng minh Devtools không nằm trong artifact, và cũng không phải bằng chứng các thành phần Devtools khác đã được loại khỏi classpath.

Ngược lại:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

không làm Devtools được tự nhúng vào JAR nếu `bootJar` đã loại dependency. Profile điều chỉnh config, **không thể tải một dependency không tồn tại trong artifact bằng phép đổi profile**.

Ma trận kiểm chứng đúng:

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Devtools dependency có được khai báo dành cho development? | `build.gradle` / `pom.xml` |
| Nó có trong runtime classpath của local `bootRun` không? | Gradle dependencies/classpath ở development mode |
| Nó có nằm trong executable JAR không? | `jar tf build/libs/....jar` và kiểm tra `BOOT-INF/lib` |
| App đang chạy bằng launcher nào? | Process command line, container ENTRYPOINT, app logs |
| Restart classloader được kích hoạt không? | Log Devtools, classloader và test thay đổi classpath |
| LiveReload có mở cổng trong local không? | Log/port của LiveReload, browser extension |
| Production có vô tình bật remote support không? | Kiểm build manifest, remote secret, exposed endpoints và network |

**Đừng đặt một “profile=prod” làm hàng rào an ninh duy nhất.**

## 9. Ví dụ chạy được: so sánh `bootRun` với executable JAR

Ta xây dựng dự án **Spring Boot 3.3.13 + Java 17 + Gradle**. Có một endpoint HTTP trả:

- Một marker `v1` để quan sát thay đổi class.
- Một `instanceToken` được tạo khi bean controller được tạo; token giúp nhìn thấy context được khởi tạo lại sau classpath restart.
- Tên lớp của classloader nạp controller, chỉ để **debug trên máy local**.
- Một static resource để kiểm tra thay đổi tài nguyên không nhất thiết tạo restart.

**Cảnh báo:** endpoint chẩn đoán classloader dưới đây dành cho **môi trường test/local**, không nên giữ công khai trong sản phẩm production. Devtools không được đóng gói không đồng nghĩa mọi debug endpoint do bạn tự viết cũng tự biến mất.

### 9.1 Cấu trúc thư mục

~~~text
devtools-scope-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/devtoolsscope/
    │   │   ├── DevtoolsScopeApplication.java
    │   │   └── ProbeController.java
    │   └── resources/
    │       └── static/
    │           └── message.txt
    └── test/
        └── java/com/example/devtoolsscope/
            └── ProbeControllerTest.java
~~~

### 9.2 `settings.gradle`

~~~groovy
rootProject.name = 'devtools-scope-demo'
~~~

### 9.3 `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Phục vụ bootRun / IDE, không đi vào bootJar theo cấu hình chuẩn.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**BOM quan trọng:** khi khai báo starter và Devtools không kèm version, cần cơ chế dependency management tương thích. `SpringBootPlugin.BOM_COORDINATES` là cách dùng Gradle native BOM. Không mặc định plugin Spring Boot tự quản lý hết phiên bản nếu dự án chưa đưa BOM hoặc dependency-management vào.

### 9.4 `DevtoolsScopeApplication.java`

~~~java
package com.example.devtoolsscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsScopeApplication.class, args);
    }
}
~~~

Không có API Devtools nào được gọi trực tiếp từ code ứng dụng. Đây là chủ ý: **Devtools là dependency phát triển**, app phải chạy được khi Devtools vắng mặt trong JAR phát hành.

### 9.5 `ProbeController.java`

~~~java
package com.example.devtoolsscope;

import java.util.Map;
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final String instanceToken = UUID.randomUUID().toString();

    @GetMapping("/api/probe")
    public Map<String, String> probe() {
        return Map.of(
                "marker", "v1",
                "instanceToken", instanceToken,
                "controllerClassLoader",
                ProbeController.class.getClassLoader().getClass().getName());
    }
}
~~~

**Giải thích:**

- `"marker"` cố định là `"v1"` trong bản nguồn đầu tiên.
- `instanceToken` chỉ được tạo một lần khi Spring tạo bean controller; nếu context được restart và bean được tạo mới, token sẽ đổi. Đây là **tín hiệu minh họa**, không thay thế việc theo dõi context lifecycle trong hệ thống thực.
- `controllerClassLoader` phản ánh lớp nạp `ProbeController`. Với Devtools restart có thể thấy classloader thuộc package `org.springframework.boot.devtools.restart.classloader`; với executable JAR chuẩn, loader khác và tên chính xác tùy launcher/version. **Không viết test ràng buộc vào tên classloader nội bộ**.
- `Map.of` trả JSON qua Jackson từ web starter; **thứ tự key JSON không được bảo đảm**, nên test theo field, không so chuỗi JSON nguyên văn.

### 9.6 Static file `message.txt`

Tạo `src/main/resources/static/message.txt`:

~~~text
resource-v1
~~~

Spring MVC static resource handler mặc định phục vụ file này ở:

~~~text
http://localhost:8080/message.txt
~~~

Khi lớp output `build/resources/main/static/message.txt` đổi nội dung, Devtools có thể phát LiveReload mà **không restart context** do default restart exclusions. Khi chỉ sửa tệp source, cần đảm bảo build/IDE đã copy resource sang classpath directory đang chạy.

### 9.7 `ProbeControllerTest.java`

~~~java
package com.example.devtoolsscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProbeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void respondsWithMarker() throws Exception {
        mvc.perform(get("/api/probe"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.marker").value("v1"));
    }
}
~~~

Test này xác nhận chức năng HTTP cơ bản không phụ thuộc Devtools. **Nó không chứng minh Devtools được loại khỏi repackaged archive**; bước đó sẽ kiểm tra trực tiếp `bootJar`.

### 9.8 Build và chạy dưới development classpath

Trong thư mục dự án đã có Gradle Wrapper tương thích:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

Trong Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp, có thể dùng `gradle bootRun`.

Khi app đã startup, terminal khác:

~~~bash
curl -sS http://localhost:8080/api/probe
curl -sS http://localhost:8080/message.txt
~~~

**Ví dụ cấu trúc kết quả HTTP** (UUID và classloader name thực tế là biến thiên, không phải chuỗi phải khớp chính xác):

~~~json
{
  "marker": "v1",
  "instanceToken": "a-valid-uuid-generated-at-runtime",
  "controllerClassLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader"
}
~~~

Nội dung file static:

~~~text
resource-v1
~~~

Trong `bootRun` với Devtools hoạt động, tên classloader ở trên là **điển hình**, không phải hợp đồng public phải dùng làm assertion. Nếu Devtools bị tắt hoặc cách launch khác, tên có thể khác.

### 9.9 Thay đổi Java class và quan sát restart

Trong **máy phát triển**:

1. Giữ `bootRun` đang chạy.
2. Sửa `ProbeController.java`: thay `"marker", "v1"` thành `"marker", "v2"`.
3. Dùng IDE `Build Project` hoặc chạy compile để cập nhật classpath:
   
~~~bash
./gradlew classes
~~~

4. Theo dõi log restart; Devtools thường phát hiện class đã được biên dịch lại.
5. Gọi lại:

~~~bash
curl -sS http://localhost:8080/api/probe
~~~

Khi restart hoàn tất, kỳ vọng:

- `marker` thành `v2`.
- `instanceToken` khác lần đầu vì controller bean được tạo mới.
- Classloader có thể vẫn cùng **tên lớp** `RestartClassLoader` nhưng object loader thực tế mới.
- Process JVM chạy `bootRun` có thể giữ nguyên, không cần gọi lại `java -jar`.

**Nếu không thấy thay đổi**, kiểm tra thời điểm copy `.class`, tính năng auto-build của IDE, có dùng Gradle daemon/launch khác không, `spring.devtools.restart.enabled`, watcher logs và việc output directory có đúng classpath mà `bootRun` theo dõi hay không. Đừng kết luận Devtools không hoạt động chỉ vì nhấn Save mà class chưa được build.

Sau thử nghiệm, khôi phục `"marker", "v1"` và build lại trước khi chạy phần so sánh JAR để giữ dữ liệu hướng dẫn nhất quán.

### 9.10 Chỉ sửa static resource

Đổi `src/main/resources/static/message.txt` từ `resource-v1` sang `resource-v2`, rồi bảo đảm `processResources` hoặc IDE đã cập nhật output classpath.

~~~bash
./gradlew processResources
~~~

Khi đó:

- `GET /message.txt` thường trả nội dung mới.
- Devtools có thể phát tín hiệu LiveReload tới browser extension.
- **Không nhất thiết restart toàn bộ context** vì `static/**` nằm trong các pattern không trigger restart mặc định.
- `instanceToken` của controller có thể giữ nguyên khi chỉ có static resource update.

**Lưu ý cache/browser:** nếu đã có caching hoặc proxy khác, phải kiểm chứng request thật và response headers; một lần refresh browser không đủ chứng minh server đã đọc resource mới.

### 9.11 Build executable JAR

Dừng `bootRun` sau khi đã thử local. Build archive:

~~~bash
./gradlew clean test bootJar
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Với `rootProject.name` và `version` của ví dụ, JAR thường được tạo tại:

~~~text
build/libs/devtools-scope-demo-1.0.0.jar
~~~

Kiểm tra tên thực nếu dự án tùy chỉnh artifact, archive classifier hoặc build configuration.

### 9.12 Kiểm tra Devtools không có trong JAR

Trên Bash (JDK có lệnh `jar`):

~~~bash
jar tf build/libs/devtools-scope-demo-1.0.0.jar |
    grep 'BOOT-INF/lib/spring-boot-devtools'
~~~

Với cấu hình Gradle chuẩn, lệnh trên **không in dòng match nào**; `grep` có thể trả exit `1` khi không tìm thấy, nên **đừng coi đó là lỗi build**. Để có kiểm tra rõ ràng cho CI:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar_file="build/libs/devtools-scope-demo-1.0.0.jar"

if jar tf "$jar_file" | grep -q 'BOOT-INF/lib/spring-boot-devtools'; then
    echo "FAIL: devtools found in release jar"
    exit 1
fi

echo "PASS: no spring-boot-devtools in executable jar"
~~~

Trên Windows PowerShell:

~~~powershell
$jar = ".\build\libs\devtools-scope-demo-1.0.0.jar"
$matches = jar tf $jar | Select-String 'BOOT-INF/lib/spring-boot-devtools'
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list jar contents"
}
if ($matches) {
    throw "Unexpected devtools dependency in executable jar"
}
Write-Output "PASS: no spring-boot-devtools in executable jar"
~~~

**Đây là kiểm tra nội dung artifact, không phải kiểm tra chỉ từ build script.** Trên Gradle build chuẩn, nested dependencies thường nằm trong `BOOT-INF/lib`. Nếu dự án tạo image từ exploded/layered artifact hay assembly tùy biến, kiểm tra cả output ở bước tạo image tương ứng.

### 9.13 Chạy packaged application

Trong terminal:

~~~bash
java -jar build/libs/devtools-scope-demo-1.0.0.jar
~~~

Và ở terminal thứ hai:

~~~bash
curl -sS http://localhost:8080/api/probe
curl -sS http://localhost:8080/message.txt
~~~

Khi JAR được build theo cấu hình mẫu:

- Endpoint vẫn trả `marker=v1` nếu đã khôi phục source về `v1` trước build.
- `instanceToken` được tạo mới khi JVM khởi động; không có lý do để so UUID với lần `bootRun`.
- `controllerClassLoader` **không** phải restart classloader do Devtools trong ví dụ thông thường.
- Sửa `src/main/java` hoặc `src/main/resources` trên máy phát triển **không tự sửa executable JAR đã build**.
- Ứng dụng đóng gói sẽ **không tự restart do Devtools** khi bạn build lại source ở thư mục project.
- Muốn chạy code/resource mới trong JAR, cần **build artifact mới và chạy lại/deploy artifact đó**.

**Không đoán tên classloader chính xác** của executable JAR, vì Spring Boot loader thay đổi giữa các version/kiểu packaging. Chỉ cần chứng minh Devtools không có trong archive và hành vi restart do sửa classpath không còn xảy ra.

## 10. Vì sao có thể thấy Devtools khi chạy IDE nhưng không thấy ở `java -jar`?

Thứ tự kiểm tra:

~~~text
IDE/bootRun
  -> dùng output directories + dependency developmentOnly
  -> Devtools thấy classpath directory
  -> Devtools monitor class/resource updates
  -> restart/LiveReload có thể chạy

bootJar
  -> đóng gói classes/resources + runtime dependencies
  -> loại Devtools theo mặc định
  -> JAR không chứa spring-boot-devtools

java -jar
  -> chạy JAR đã đóng gói
  -> Devtools không có trong archive
  -> sửa source/build output bên ngoài không tác động nội dung JAR
~~~

Điểm then chốt là **build layout và launcher**, không phải tên profile “dev/prod” tự tạo phép màu.

### Packaged không đồng nghĩa “đọc source live”

Một executable JAR chứa bản snapshot **bytecode/resources tại thời điểm đóng gói**. Sửa `src/main/java` hoặc `src/main/resources` sau khi đóng gói không làm JAR tự đổi. Nếu một external configuration file được Spring đọc lại bởi cơ chế khác, đó là hành vi **cấu hình runtime**, không tự là Devtools restart.

Kể cả khi bạn build lại JAR **cùng tên file** trong lúc một JVM đang chạy JAR cũ, không nên trông chờ JVM tự nhận bytecode mới. Hãy triển khai bản mới có version/digest rõ ràng và dùng lifecycle/restart orchestration phù hợp.

## 11. Devtools và các hình thức chạy khác

| Hình thức khởi chạy | Ranh giới cần nhớ |
| --- | --- |
| IDE từ `build/classes`/`target/classes` | Classpath dạng thư mục, Devtools có thể restart khi output đổi |
| `gradle bootRun` | Chạy qua JavaExec với main runtime classpath, phù hợp development |
| `mvn spring-boot:run` | Chạy ở dev classpath, có hành vi tương tự khi Devtools phù hợp |
| `java -jar app.jar` | Fully packaged application, Devtools mặc định bị tắt nếu còn được nhúng |
| Docker image từ JAR phát hành | Không nên có Devtools; phải kiểm image thực tế |
| Exploded/loose classpath trong container | Không được xem tự động là production-safe nếu Devtools có mặt |
| WAR deploy vào servlet container | Kiểm kiểu packaging/classloader và dependency; không dùng Devtools ở production |
| Native image/GraalVM | Không nên giả định classloader restart Devtools hoạt động như JVM dev classpath |

**Luôn kiểm tra artifact cuối cùng và cách launcher thật.** Một pipeline có thể tạo `bootJar` đúng nhưng Dockerfile lại copy nguyên `build/libs` hoặc thêm development libraries vào image ở bước khác.

## 12. Nếu cố nhúng Devtools vào archive thì sao?

Spring Boot có cách tùy chỉnh packaging để **cố ý đưa Devtools vào repackaged archive**, chủ yếu dành cho một số trường hợp remote development đặc biệt. Ví dụ tài liệu nói Maven có tùy chọn `excludeDevtools=false`, còn Gradle có thể tùy chỉnh classpath của task packaging để bao gồm `developmentOnly`.

**Bài học này không khuyến nghị bật tùy chọn đó.** Đây là ngoại lệ dành cho môi trường thử nghiệm cách ly/trusted, không phải cấu hình production.

Vì sao nguy hiểm?

1. Remote support là cơ chế có thể cập nhật ứng dụng từ xa; nếu bật sai, ảnh hưởng đến bảo mật.
2. Devtools development property defaults có thể làm lộ nhiều thông tin lỗi hơn mức chấp nhận trong production.
3. Tự động restart dựa trên classpath updates không phải cơ chế release có kiểm toán, version/digest và rollback rõ.
4. Restart classloader và watcher có thể tạo hành vi ngoài dự kiến khi ứng dụng chạy lâu.
5. Quy trình vận hành dùng container/Deployment cần triển khai artifact đã xác thực thay vì tự thay bytecode trong JVM đang phục vụ khách hàng.

Tài liệu Spring Boot nêu rõ **không bao giờ bật remote Devtools support trên production deployment**. Nếu tổ chức có môi trường remote development nội bộ riêng, vẫn cần network bảo vệ, TLS, secret mạnh và chính sách vận hành riêng; **không chuyển exception này thành đường deploy chính thức**.

## 13. So sánh Devtools với hot reload và production deployment

| Cơ chế | Cái gì thay đổi? | Phù hợp ở đâu? |
| --- | --- | --- |
| Devtools automatic restart | ApplicationContext và restart classloader | Máy phát triển / dev environment |
| Devtools LiveReload | Thông báo browser refresh khi resource đổi | Máy phát triển có client hỗ trợ |
| JVM HotSwap/JRebel hoặc công cụ bytecode reload | Có thể thay class definitions ở mức khác | Theo khả năng/giấy phép của công cụ, thường dev |
| Full JVM restart | JVM/process mới, classpath được nạp từ đầu | Kiểm thử lạnh và vận hành |
| Docker/Kubernetes rolling update | Pod/instance mới dùng image/artifact version mới | Staging/production |
| Spring Cloud Config/Actuator refresh hoặc cơ chế cấu hình riêng | Một số giá trị cấu hình/runtime state | Phải dựa vào cơ chế và giới hạn cụ thể, không phải Devtools |

Devtools restart **không phải “hot reload mọi thứ”**. Nó dùng hai classloaders và tạo lại context. JVM có thể giữ base classloader, vì vậy không phải mọi dependency JAR đều được tải lại, không phải thay đổi library binary nào cũng được nhận tự động.

## 14. Giới hạn classloader trong dự án nhiều module

Devtools restart classloader hoạt động tốt ở đa số ứng dụng đơn giản, nhưng trong dự án multi-module hoặc dùng reflection/serialization có thể gặp:

- `ClassCastException` khi cùng một tên class được load bởi **hai classloader khác nhau**.
- `ClassNotFoundException` khi thư viện dùng thread context classloader không phù hợp.
- Resource/annotation type được base classloader tải sớm nhưng class của ứng dụng nằm ở restart loader.
- Tái khởi tạo context làm lộ resource/thread leak từ mã không dọn dẹp đúng.
- Object được deserialize bằng `ObjectInputStream` chuẩn có thể không tương thích classloader.

Cách điều tra:

1. Reproduce lỗi ở `bootRun` với Devtools.
2. Tắt restart support bằng **system property** `-Dspring.devtools.restart.enabled=false` trước `run()`.
3. Nếu lỗi biến mất, nghi ngờ classloader boundary thay vì ngay lập tức sửa logic nghiệp vụ.
4. Đối chiếu tên class và identity của classloader ở nơi lỗi xuất hiện.
5. Nếu cần, dùng `META-INF/spring-devtools.properties` để điều chỉnh `restart.include` và `restart.exclude` theo classpath.
6. Kiểm thử lại sau thay đổi trên cả dev classpath và packaged application.

Ví dụ tài liệu dùng `spring-devtools.properties`:

~~~properties
restart.include.projectcommon=.*/project-common-[^/]+\\.jar
restart.exclude.legacy=.*/legacy-module/(build|target)/.*
~~~

**Đây là mẫu regex minh họa, không áp dụng nguyên trạng cho mọi workspace.** Cần so với classpath thực tế và cú pháp regex mà Java Properties parse, đặc biệt escape backslash. Sai regex có thể làm tình hình tệ hơn.

### Một giới hạn có thể kiểm tra ngay

`SpringApplication.setRegisterShutdownHook(false)` có thể làm Devtools restart không hoạt động đúng, vì Devtools dựa vào shutdown hook của context để dừng nó trong quá trình restart. Đừng tắt hook chỉ nhằm “giảm log” khi đang dùng automatic restart.

Cũng có những hạn chế với AspectJ weaving và deserialization; khi gặp lỗi đặc trưng, đọc mục **Known Limitations** theo đúng version Spring Boot đang dùng.

## 15. Tắt những gì? Chọn đúng công cụ

| Mục tiêu | Cách xử lý thích hợp | Không nên nhầm với |
| --- | --- | --- |
| Không cho Devtools vào production JAR | `developmentOnly` / Maven optional + kiểm tra artifact | Chỉ đặt profile `prod` |
| Không theo dõi classpath để restart trong local | `spring.devtools.restart.enabled=false` | Không bảo đảm restart loader không được tạo |
| Vô hiệu hóa restart support từ đầu startup | JVM system property `-Dspring.devtools.restart.enabled=false` | Không thay thế dependency removal |
| Không mở LiveReload server | `spring.devtools.livereload.enabled=false` | Không tự tắt restart |
| Không áp dụng Devtools property defaults | `spring.devtools.add-properties=false` | Không tự tắt LiveReload hoặc watcher |
| Chỉ restart có chủ đích | `spring.devtools.restart.trigger-file=.reloadtrigger` | Không phải cơ chế release production |
| Không làm lộ remote devtools trong deployment | Không đóng gói/bật remote support trên prod | Không đủ chỉ đặt secret bất kỳ |
| Tách hiệu năng production | Đo JAR/image thật, không Devtools | Không dùng thời gian devtools restart làm cold startup |

Nếu cần **tắt hoàn toàn Devtools cho bản phát hành**, ưu tiên **artifact-level control**, không chỉ runtime property.

## 16. Kiểm tra Docker image và CI/CD

Một hệ thống triển khai bằng container cần kiểm tra **bản image cuối**, không chỉ file `build.gradle`.

Ví dụ Dockerfile đơn giản:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/devtools-scope-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là **Dockerfile minh họa** chỉ áp dụng khi `bootJar` đã tạo file tên tương ứng, không chứa ứng dụng thực tế của người đọc. Nó chạy JAR bằng exec-form, giúp tín hiệu dừng tới tiến trình Java rõ ràng.

Đừng dùng cấu hình kiểu sau trong production chỉ để tiết kiệm thời gian build:

~~~text
COPY entire-project-with-build-output /app
java -cp "/app/build/classes:/app/dev-libs/*" com.example.MyApplication
~~~

Đây là **mô hình anti-pattern minh họa**, không phải một Dockerfile chạy được. Nếu copy cả dependency development vào image và dùng loose classpath, Devtools có thể nằm trên runtime classpath, trái mục tiêu loại khỏi artifact.

### CI gates đề xuất

- **Build gate:** Gradle/Maven dependency management đã thống nhất.
- **Archive gate:** executable JAR/WAR không chứa `spring-boot-devtools`.
- **Image gate:** image cuối không vô tình copy JAR Devtools hay dev classpath.
- **Configuration gate:** không có `spring.devtools.remote.secret` và không ép `-Dspring.devtools.restart.enabled=true` trong deployment.
- **Behavior gate:** startup/health/functional smoke test trên artifact thật, không phụ thuộc Devtools.
- **Security gate:** không có debug-only HTTP endpoint, excessive error details hoặc LiveReload port public.
- **Release gate:** thay đổi code được đưa qua build/version/image digest, rolling update và rollback, không tự restart dựa trên file changed trong container.

Những kiểm tra này ngăn trạng thái “build script có vẻ đúng nhưng môi trường triển khai thực tế vẫn mang Devtools”.

## 17. Phân biệt ba kiểu kiểm thử

### Kiểm thử chức năng

`@SpringBootTest` hoặc `MockMvc` xác nhận endpoint/service hoạt động. Đây là điều cần thiết nhưng **không nói được một artifact release có chứa Devtools hay không**.

### Kiểm thử classpath và packaging

Đọc `jar tf`, kiểm tra `BOOT-INF/lib` hoặc danh sách layer/dependency của image. Điều này trả lời **Devtools có nằm trong package không**, không tự nói mọi tính năng sẽ kích hoạt.

### Kiểm thử hành vi runtime

Chạy `bootRun`, quan sát restart khi classpath đổi; chạy executable JAR, quan sát rằng sửa source không làm JAR tự đổi. Trên production-like environment, kiểm tra effective JVM command line, không ép bật Devtools, không expose remote endpoint.

Cần **cả ba** để đánh giá an toàn và đúng chức năng.

## 18. Các lỗi thực hành thường gặp

**Lỗi 1 — Nghĩ chỉ cần `spring.profiles.active=prod` là Devtools biến mất.** Sai: profiles là cấu hình, không làm thay đổi nội dung JAR đã tạo. Kiểm artifact.

**Lỗi 2 — Dùng `implementation 'spring-boot-devtools'` không suy nghĩ về scope.** Devtools là dependency cho development; dùng `developmentOnly` và kiểm kết quả packaging.

**Lỗi 3 — Tin rằng `java -jar` sẽ có automatic restart vì build project chứa Devtools.** JAR chuẩn không mang Devtools; packaged launch cũng được Boot xem như production-style.

**Lỗi 4 — Thấy `spring.devtools.restart.enabled=false` trong `application.properties` và tuyên bố restart classloader hoàn toàn không tạo.** Tài liệu phân biệt với việc đặt system property sớm.

**Lỗi 5 — Nghĩ Devtools tự biên dịch source Java.** Nó xem **classpath changes**; IDE/build tool phải cập nhật output classes.

**Lỗi 6 — Nghĩ static resource phải restart toàn bộ context.** Các thư mục static/templates thường là restart exclusions và có thể LiveReload.

**Lỗi 7 — Nghĩ LiveReload server tự refresh mọi trình duyệt.** Cần browser extension/client hỗ trợ.

**Lỗi 8 — Nghĩ LiveReload và automatic restart là một toggle.** Có các property khác nhau; tắt cái này không tự xóa cái kia.

**Lỗi 9 — Đo production startup bằng thời gian Devtools restart.** Base classloader/JVM đã warm, không phải cold process.

**Lỗi 10 — Copy exploded development classpath vào container.** Có thể mang Devtools và chế độ development vào production dù `bootJar` chuẩn không chứa module.

**Lỗi 11 — Ép `-Dspring.devtools.restart.enabled=true` trên packaged production app.** Có thể tái kích hoạt Devtools nếu module hiện diện, là rủi ro bảo mật.

**Lỗi 12 — Bật remote support trên production vì có `remote.secret`.** Tài liệu Spring Boot cấm trường hợp này; secret không biến tính năng phát triển thành an toàn production.

**Lỗi 13 — Không kiểm tra classloader leak sau nhiều restart.** App context mới liên tục có thể phơi bày executor/thread/socket không dọn.

**Lỗi 14 — Dùng `System.out.println` rồi kết luận mọi bean luôn được tạo lại do Devtools.** Phải biết event nào trigger restart và instance/context nào được tạo lại.

**Lỗi 15 — Không kiểm image cuối.** Dockerfile/assembly có thể bỏ qua JAR đã kiểm hoặc copy thêm dev dependencies.

**Lỗi 16 — Giữ debug controller trong production vì “Devtools đã được exclude”.** Endpoint do mã ứng dụng tự viết vẫn được đóng gói bình thường; phải xóa hoặc bảo vệ riêng.

**Lỗi 17 — Dùng `spring.devtools.add-properties=false` như nút tắt toàn module.** Nó chỉ ngăn các default property overrides.

**Lỗi 18 — Bỏ qua multi-module classloader issues.** Devtools dùng base/restart loader; cần xem boundary khi có `ClassCastException` hoặc lỗi reflection/serialization.

**Lỗi 19 — Không kiểm soát trigger file và additional paths.** Có thể restart quá nhiều lần khi file build/output thay đổi liên tục.

**Lỗi 20 — Phân biệt các bản Spring Boot không đúng.** Property defaults, plugin packaging và runtime behavior cần đối chiếu theo phiên bản, không sao chép vô điều kiện từ Boot 4.x vào 3.3.

## 19. Câu hỏi tự kiểm tra

1. **`spring-boot-devtools` được thiết kế chính cho môi trường nào?** Phát triển.
2. **Khai báo Devtools trong Gradle ra sao?** Dùng `developmentOnly 'org.springframework.boot:spring-boot-devtools'`.
3. **Maven thường dùng thuộc tính gì cho dependency Devtools?** `<optional>true</optional>`.
4. **`bootJar` chuẩn có bao gồm Devtools không?** Không theo mặc định với cấu hình Spring Boot 3.3 chuẩn.
5. **Devtools không có trong JAR thì `java -jar` có thể tự dùng nó không?** Không.
6. **JAR có Devtools do cố tình đóng gói thì fully packaged launch kích hoạt Devtools mặc định?** Thông thường không, Boot xem đó là kiểu chạy production.
7. **Có thể ép bật bằng system property nào, và có nên ở production?** `-Dspring.devtools.restart.enabled=true`; **không nên, và không dùng ở production**.
8. **`spring.profiles.active=prod` có xóa Devtools khỏi artifact không?** Không.
9. **Devtools watcher phát hiện thay đổi ở đâu?** Các thư mục/classpath entries phù hợp, không phải source chưa được compile.
10. **Vì sao thay `.java` không restart khi chỉ Save?** Có thể output `.class` chưa đổi.
11. **Restart của Devtools có tạo một JVM process mới mỗi lần không?** Không nhất thiết; chủ yếu đổi restart classloader/context trong JVM đang chạy.
12. **Vì sao Devtools restart không phải thước đo cold startup?** Base loader/JVM đã warm.
13. **Devtools dùng bao nhiêu classloader chính cho restart?** Hai: base và restart.
14. **Thay resource trong `static` có bắt buộc restart context không?** Thường không; có thể trigger LiveReload.
15. **LiveReload cần gì phía browser?** Extension/client hỗ trợ.
16. **Property tắt LiveReload?** `spring.devtools.livereload.enabled=false`.
17. **Property tắt Devtools property defaults?** `spring.devtools.add-properties=false`.
18. **Property trong application file tắt restart có thể vẫn khởi tạo loader không?** Có thể.
19. **Muốn tắt restart support từ sớm?** Đặt JVM system property `spring.devtools.restart.enabled=false` trước `run`.
20. **Cách chứng minh JAR không chứa Devtools?** Liệt kê `jar tf` và kiểm `BOOT-INF/lib`.
21. **Vì sao không chỉ kiểm build.gradle?** Image hoặc packaging stage khác có thể thêm dependency.
22. **Remote Devtools có nên bật production sau khi đặt secret mạnh?** Không.
23. **Devtools default error details có thể gây rủi ro gì?** Lộ thông tin phục vụ debug tới client/log.
24. **Multi-module có thể gặp lỗi gì?** Classloader identity, reflection, deserialization, resource leak.
25. **Khi thay code trong JAR đã build, có tự cập nhật code JVM đang chạy không?** Không; cần rebuild và chạy/deploy artifact mới.
26. **Có thể dùng `@SpringBootTest` để chứng minh packaging sạch Devtools không?** Không; phải kiểm artifact.
27. **Vì sao tránh debug HTTP endpoint ở production dù Devtools đã bị loại?** Vì endpoint là code ứng dụng và vẫn được build bình thường.
28. **Cơ chế triển khai production phù hợp để cập nhật code?** Artifact versioned + restart/rolling deployment có kiểm soát.

**Kết luận:** Với Spring Boot 3.3, Devtools **phục vụ development classpath**, còn bản phát hành nên **không chứa dependency Devtools**. Gradle `developmentOnly`/Maven `optional` là một phần của thiết kế dependency; repackaged JAR chuẩn loại Devtools mặc định. Khi chạy kiểu packaged `java -jar`, Spring Boot còn mặc định vô hiệu hóa các tính năng Devtools nếu module vô tình có mặt. Hãy phân biệt **classpath presence** với **runtime activation**, hiểu restart dựa trên **compiled classpath changes** chứ không tự compile source, và kiểm cả **JAR, image, effective JVM command line và behavior**. Không bật remote Devtools trong production; thay đổi code production phải đi qua build/release/rollback rõ ràng.

### Tài liệu tham khảo

- Spring Boot 3.3 — **Developer Tools**, dependency scoping, fully packaged applications, default properties, restart/LiveReload, remote support: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — **Gradle Plugin: Running your Application**, `bootRun` và cập nhật classpath: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — **Gradle Plugin: Packaging Executable Archives**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — **Gradle Plugin: Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — **Maven Plugin: Packaging Executable Archives**, Devtools exclusion: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — **Externalized Configuration and Profiles**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — **SpringApplication** and application lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
