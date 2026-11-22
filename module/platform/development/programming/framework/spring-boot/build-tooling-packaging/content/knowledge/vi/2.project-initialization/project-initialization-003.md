# Đọc cấu trúc dự án Maven và Gradle do Spring Initializr sinh ra

## Mục tiêu bài học

Sau khi đọc, bạn có thể mở một dự án Spring Boot vừa tải từ Spring Initializr và tự trả lời được: dự án dùng Maven hay Gradle, đang nhắm tới phiên bản Java nào, khai báo thư viện ở đâu, mã nguồn và cấu hình chạy nằm ở đâu, lệnh nào dùng để kiểm thử/chạy/đóng gói, và tệp JAR được tạo ra ở vị trí nào.

Đây là kỹ năng **đọc cấu trúc dự án vừa khởi tạo**, chưa phải bài chuyên sâu về tự viết plugin, tối ưu build hoặc triển khai lên máy chủ.

## 1. Hiểu đúng thứ Spring Initializr tạo ra

[Spring Initializr](https://start.spring.io/) nhận các lựa chọn như **Project** (Maven hoặc Gradle), **Language**, **Spring Boot version**, **Group**, **Artifact**, **Name**, **Package name**, **Packaging**, **Java** và **Dependencies**, rồi sinh ra một dự án có thể mở trong IDE. Tùy lựa chọn, tên tệp và nội dung cụ thể sẽ khác nhau.

Ví dụ xuyên suốt: chọn **Java**, `Group = com.example`, `Artifact = demo`, `Package name = com.example.demo`, **Packaging = Jar** và **Java = 21**. Đây là **giá trị minh họa** để đọc cấu trúc; hãy lấy phiên bản Spring Boot, phiên bản plugin và tên gói thật từ dự án bạn vừa tải, không chép cứng theo ví dụ.

Hai dự án tạo với cùng lựa chọn nghiệp vụ có phần lõi giống nhau: mã Java trong `src/main/java`, tài nguyên trong `src/main/resources`, kiểm thử trong `src/test/java`. Khác biệt chủ yếu nằm ở **công cụ build, cấu hình build, wrapper và thư mục chứa sản phẩm build**.

### Hình dung theo ba lớp

1. **Mô tả dự án và quá trình build:** `pom.xml` với Maven; `build.gradle` hoặc `build.gradle.kts` cùng `settings.gradle[.kts]` với Gradle. Các tệp này quyết định plugin, thư viện, Java và công việc build.
2. **Ứng dụng:** `src/main/java` chứa lớp chạy chính và mã nghiệp vụ; `src/main/resources` chứa cấu hình/tài nguyên được đóng gói cùng ứng dụng.
3. **Kiểm thử và đầu ra:** `src/test` chứa bài kiểm thử; Maven thường sinh `target/`, Gradle sinh `build/` khi chạy build. Hai thư mục này **không phải mã nguồn gốc**.

## 2. Nhận diện Maven và Gradle từ thư mục gốc

Một dự án **Maven** điển hình do Initializr sinh:

```text
demo/
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw
├── mvnw.cmd
├── pom.xml
├── .gitignore
├── HELP.md
└── src/
    ├── main/
    │   ├── java/com/example/demo/DemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/demo/DemoApplicationTests.java
```

Một dự án **Gradle dùng Groovy DSL** điển hình:

```text
demo/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── settings.gradle
├── build.gradle
├── .gitignore
├── HELP.md
└── src/
    ├── main/
    │   ├── java/com/example/demo/DemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/demo/DemoApplicationTests.java
```

Nếu chọn **Gradle – Kotlin DSL**, hãy tìm `build.gradle.kts` và `settings.gradle.kts` thay cho hai tệp đuôi `.gradle`. Nếu chọn Kotlin/Groovy thay vì Java, nguồn có thể nằm tại `src/main/kotlin` hoặc `src/main/groovy`. Nếu chọn YAML, cấu hình có thể là `application.yml` thay cho `application.properties`. Một số tệp hỗ trợ như `.gitattributes`, `HELP.md`, các tài nguyên bổ sung hoặc tệp wrapper khác phụ thuộc phiên bản công cụ và tùy chọn sinh dự án; **đừng coi cây minh họa là danh sách bất biến**.

**Mẹo đọc nhanh:** thấy `pom.xml` và `mvnw` → Maven; thấy `build.gradle[.kts]`, `settings.gradle[.kts]` và `gradlew` → Gradle. Đừng quyết định chỉ từ tên thư mục `src` vì cả hai dùng cùng quy ước nguồn.

## 3. Đọc dự án Maven: bắt đầu từ `pom.xml`

`pom.xml` (Project Object Model) là tệp trung tâm. Hãy đọc theo thứ tự:

| Thành phần | Ý nghĩa và câu hỏi cần trả lời |
| --- | --- |
| `modelVersion` | Phiên bản mô hình POM, thường là `4.0.0`. Không phải phiên bản ứng dụng. |
| `parent` | Với mẫu Spring Boot thường là `spring-boot-starter-parent`: thừa hưởng cấu hình/phiên bản quản lý sẵn. |
| `groupId`, `artifactId`, `version` | Danh tính bản đóng gói của dự án; ví dụ `com.example:demo:0.0.1-SNAPSHOT`. |
| `properties` | Thuộc tính như `java.version` (phiên bản Java được chọn). |
| `dependencies` | Các starter và thư viện trực tiếp; nhìn `scope` để hiểu thư viện dùng cho chạy hay kiểm thử. |
| `build/plugins` | Plugin thao tác khi build; Spring Boot Maven Plugin hỗ trợ chạy và đóng gói ứng dụng Spring Boot. |
| `packaging` nếu có | Loại sản phẩm như `jar` hoặc `war`; vắng mặt thường theo mặc định Maven là `jar`. |

Đoạn sau **chỉ là trích đoạn minh họa các trường cần tìm**, không phải một `pom.xml` hoàn chỉnh để thay thế tệp do Initializr tạo:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
<groupId>com.example</groupId>
<artifactId>demo</artifactId>
<version>0.0.1-SNAPSHOT</version>
<properties>
    <java.version>21</java.version>
</properties>
```

Phiên bản `4.1.2` ở đây chỉ minh họa vị trí **đọc phiên bản Spring Boot**; phiên bản thực tế phụ thuộc thời điểm và lựa chọn trên Initializr. Với Maven, phiên bản các dependency được Spring Boot quản lý thường không cần khai báo riêng trong mỗi `<dependency>`. Tuy nhiên, **không phải mọi dependency trên Internet đều nằm trong danh mục được quản lý**, và việc ghi đè phiên bản vẫn có thể làm thay đổi tương thích.

Ví dụ trích đoạn từ phần khai báo dependency/plugin:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Đây cũng là **trích đoạn**, không phải toàn bộ POM. `spring-boot-starter` cung cấp nhóm dependency cơ bản; starter cho web, dữ liệu hay bảo mật **chỉ xuất hiện khi được chọn hoặc bổ sung**. `scope=test` nói rằng dependency chủ yếu phục vụ biên dịch/chạy kiểm thử. Khi đọc cấu hình thực tế, hãy phân biệt **dependency khai báo trực tiếp** với **dependency bắc cầu (transitive)** được kéo theo.

### Wrapper Maven: `mvnw`, `mvnw.cmd` và `.mvn/wrapper/`

`mvnw` (macOS/Linux) và `mvnw.cmd` (Windows) là **Maven Wrapper**: giúp nhóm dùng bản Maven được dự án cấu hình mà không nhất thiết cài `mvn` toàn cục. `.mvn/wrapper/maven-wrapper.properties` chỉ ra bản phân phối Maven cần tải. Một số phiên bản/cấu hình wrapper có thêm tệp hỗ trợ; không tự suy luận rằng phải tồn tại một `maven-wrapper.jar`.

Wrapper **không thay thế JDK**: bạn vẫn cần JDK phù hợp với phiên bản Java của dự án và điều kiện tương thích của Spring Boot. Lần dùng đầu, wrapper có thể cần mạng để tải công cụ/dependency.

## 4. Đọc dự án Gradle: `settings`, `build`, `wrapper`

Hãy đọc ba nơi theo thứ tự:

1. `settings.gradle` hoặc `settings.gradle.kts`: xác định tên dự án gốc (ví dụ `rootProject.name = 'demo'` với Groovy DSL) và các module con qua `include(...)` nếu có. Dự án Initializr đơn giản thường chỉ có một project, không có nhiều module.
2. `build.gradle` hoặc `build.gradle.kts`: plugin, mã định danh `group/version`, công cụ Java (toolchain), kho thư viện, dependency và các task build/test/run. Tệp `.gradle` dùng **Groovy DSL**; `.gradle.kts` dùng **Kotlin DSL**; cú pháp khác nhưng vai trò tương đương.
3. `gradle/wrapper/gradle-wrapper.properties` cùng `gradlew`/`gradlew.bat`: phiên bản **Gradle** được wrapper tải/chạy. Nó khác với **phiên bản Spring Boot plugin** khai báo trong build script.

Ví dụ **trích đoạn Groovy DSL** minh họa cách nhận diện cấu hình; bản thật có thể khác ở plugin, repository, dependency và task:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các số phiên bản trong trích đoạn **chỉ để minh họa vị trí**, không phải yêu cầu cập nhật dự án lên đúng số đó. Đừng chép đè tệp được sinh, vì phiên bản Gradle/Spring Boot/plugin phải tương thích. Trong ví dụ, `implementation` cung cấp dependency cho mã chính; `testImplementation` cho mã kiểm thử; `runtimeOnly` (nếu có) chỉ phục vụ lúc chạy. Nhiều dự án có thêm `testRuntimeOnly` và các task theo starter đã chọn.

Với Kotlin DSL, ví dụ cú pháp tương đương ở vài dòng là:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}
group = "com.example"
version = "0.0.1-SNAPSHOT"
```

Đây là **mảnh cấu hình để nhận diện cú pháp**, không phải toàn bộ `build.gradle.kts` có thể chạy độc lập. Khi mở Gradle trong IDE, IDE phải nhập lại (sync/import) dự án để nhận classpath, plugin và dependency.

### Wrapper Gradle không phải cache Gradle

`gradle/wrapper/gradle-wrapper.properties` thường có `distributionUrl` chỉ tới bản Gradle thích hợp; `gradle-wrapper.jar` và script wrapper là bộ phận chạy wrapper. Đừng nhầm **`gradle/`** (tệp do dự án quản lý) với **`.gradle/`** (cache/trạng thái sinh ra lúc build, thường không commit). `gradlew`/`gradlew.bat` giúp chạy đúng Gradle mà dự án chọn; máy vẫn cần JDK thích hợp.

## 5. Đọc phần chung: mã nguồn, tài nguyên và kiểm thử

### `src/main/java` và lớp ứng dụng chính

Với ví dụ `com.example.demo`, thư mục `src/main/java/com/example/demo/` chứa lớp `DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đây là lớp chạy chính được sinh cho dự án Java Spring Boot, sử dụng các lớp Spring Boot có sẵn trong dependency của dự án. `main` gọi `SpringApplication.run` để khởi động application context. `@SpringBootApplication` tập hợp cấu hình khởi động, auto-configuration và component scanning. Các thành phần trong **gói của lớp chính và các gói con** thường được quét theo mặc định; đặt lớp chính ở gói quá hẹp có thể khiến Spring không tìm thấy component ở nơi khác.

**Phân biệt:** tệp Java ở `src/main/java` được biên dịch thành class để chạy. Đường dẫn gói `com/example/demo` phản ánh khai báo `package com.example.demo;`; tên gói không bắt buộc luôn giống Artifact.

### `src/main/resources` là tài nguyên chạy ứng dụng

`application.properties` hoặc `application.yml` chứa cấu hình runtime như cổng, log, thông tin tích hợp hoặc tên ứng dụng. Ví dụ có thể thêm:

```properties
spring.application.name=demo
server.port=8081
```

Hai dòng trên chỉ là **ví dụ cấu hình**, không được mặc định có trong dự án mới. `server.port` có ý nghĩa khi ứng dụng có môi trường web phù hợp; việc thêm dòng này không tự tạo HTTP endpoint. Cấu hình ở đây **khác** `pom.xml`/`build.gradle`: tệp build mô tả cách dựng ứng dụng, còn `application.properties` ảnh hưởng hành vi ứng dụng khi chạy. Thư mục tài nguyên cũng có thể chứa `static/`, `templates/`, tệp thông báo, schema... khi bài toán sử dụng chúng; không bắt buộc được sinh sẵn.

### `src/test/java` là mã kiểm thử

Một dự án Java Spring Boot thường có `DemoApplicationTests.java`; ví dụ mẫu:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

`@SpringBootTest` cho phép kiểm tra Spring application context khởi động trong môi trường test; `@Test` là dấu hiệu phương thức kiểm thử JUnit. Test trống về mặt thân hàm **không có nghĩa là không thực hiện kiểm thử**: quá trình tải context vẫn có thể lỗi nếu cấu hình hay dependency không phù hợp. Một bài kiểm thử context chạy được chưa chứng minh nghiệp vụ hay endpoint hoạt động đúng.

Các thư mục `src/test/resources`, `src/main/resources/static` hoặc `templates` chỉ xuất hiện khi có tệp phù hợp; thiếu chúng ở dự án mới là bình thường.

## 6. Maven và Gradle thực thi cùng mục tiêu qua các lệnh khác nhau

Hãy đứng tại **thư mục gốc có wrapper và build file**, mở terminal và dùng wrapper. Bảng sau áp dụng khi các plugin/task Spring Boot tương ứng đã có trong dự án.

| Công việc | Maven (macOS/Linux) | Gradle (macOS/Linux) |
| --- | --- | --- |
| Kiểm tra phiên bản công cụ | `./mvnw -v` | `./gradlew --version` |
| Chạy kiểm thử | `./mvnw test` | `./gradlew test` |
| Dọn đầu ra và build | `./mvnw clean package` | `./gradlew clean build` |
| Chạy ứng dụng từ nguồn | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Thư mục sản phẩm | `target/` | `build/` |
| Thư mục JAR thông dụng | `target/*.jar` | `build/libs/*.jar` |

Trên **Windows PowerShell**, dùng `.\mvnw.cmd test`, `.\mvnw.cmd spring-boot:run` hoặc `.\gradlew.bat test`, `.\gradlew.bat bootRun`. Đối với macOS/Linux, đôi khi cần `chmod +x mvnw` hoặc `chmod +x gradlew` nếu script chưa có quyền thực thi. Cú pháp `./` và `.\` khác nhau theo shell.

Các lệnh `package` (Maven) và `build` (Gradle) thường chạy kiểm thử cùng các bước build khác; nếu test thất bại, quá trình có thể dừng và không tạo được JAR mong đợi. Với dự án được cấu hình đóng gói **WAR**, tìm tệp `.war` tương ứng thay vì luôn đòi JAR.

### Khi chạy thành công, kết quả nằm ở đâu?

- **Maven:** `target/classes/` chứa mã đã biên dịch và tài nguyên đã xử lý; `target/test-classes/` chứa mã test; `target/surefire-reports/` có báo cáo unit test thông thường; `target/` có sản phẩm đóng gói.
- **Gradle:** `build/classes/` và `build/resources/` chứa đầu ra biên dịch/tài nguyên; `build/test-results/test/` và `build/reports/tests/test/` có kết quả/báo cáo test; `build/libs/` chứa JAR/WAR khi task đóng gói tương ứng chạy.
- Khi có **Spring Boot packaging**, `spring-boot-maven-plugin` hoặc task `bootJar`/`bootWar` có thể tạo archive thực thi. Một bản Gradle có thể đồng thời có JAR thông thường mang hậu tố `-plain.jar`: đừng nhầm nó với archive Boot chứa đủ thành phần cần chạy. Hãy đọc cấu hình plugin/task và kiểm tra tên sản phẩm thực tế.

Không có một chuỗi stdout cố định cho `bootRun` hay `spring-boot:run`: log, port, phiên bản và các bean phụ thuộc dependency và cấu hình. Không có web starter thì bạn không nên mặc định truy cập `http://localhost:8080/` sẽ có trang hay endpoint. Khi chạy JAR Boot thực thi, lệnh thường là `java -jar <duong-dan-den-jar>`; dùng **đúng tệp** xuất hiện sau build.

## 7. Quy trình đọc một dự án vừa tải trong 10–15 phút

**Bước 1 – Giải nén và chọn đúng thư mục gốc.** Mở nơi chứa `pom.xml` hoặc `build.gradle[.kts]`. Nếu IDE chỉ mở `src/` thì công cụ build có thể không được nhận diện đúng.

**Bước 2 – Ghi lại danh tính dự án.** Tìm `groupId/artifactId/version` trong POM hoặc `group/version` và `rootProject.name` trong Gradle. Đối chiếu với các lựa chọn Group/Artifact/Name trên Initializr. Lưu ý tên project hiển thị không nhất thiết bằng tên gói Java.

**Bước 3 – Xác định phiên bản và Java.** Với Maven, đọc Spring Boot parent và `java.version`; với Gradle, đọc Spring Boot plugin, Java toolchain và Gradle wrapper. Sau đó chạy `java -version` để so với cấu hình. **Ba thứ khác nhau:** phiên bản Java dùng biên dịch/chạy, phiên bản Spring Boot, phiên bản Maven/Gradle.

**Bước 4 – Xem dependency đã chọn.** Ví dụ nếu chọn starter web, tìm dependency web tương ứng ở POM/build script. Tên starter có thể thay đổi theo dòng phiên bản Spring Boot; tin vào tệp được sinh và tài liệu phù hợp phiên bản đó, thay vì mặc định mọi dự án đều phải có `spring-boot-starter-web`.

**Bước 5 – Tìm điểm khởi động.** Mở `...Application.java`, xác nhận `@SpringBootApplication`, `main`, package; xem `src/main/resources/application.properties` hoặc YAML. Nếu ứng dụng chưa chứa controller, service hay entity, đó là bình thường: Initializr tạo **bộ khung**, chưa tạo nghiệp vụ.

**Bước 6 – Tìm bài test mặc định.** Mở `src/test/java`, giải thích vì sao có `@SpringBootTest` và `@Test`. Nếu không sinh test như cây minh họa, kiểm tra lựa chọn hoặc cấu hình build thay vì tự cho rằng dự án hỏng.

**Bước 7 – Dùng wrapper kiểm tra khả năng build.** Chạy lệnh kiểm thử tương ứng, sau đó thử đóng gói. Quan sát kết quả ở `target/` hoặc `build/`. Nếu một lệnh cần tải dependency và bị lỗi mạng, phải phân biệt lỗi tải với lỗi Java source.

**Bước 8 – So sánh hai biến thể.** Tạo thêm dự án với cùng Group, Artifact, Java, Packaging và Dependencies nhưng chọn công cụ build còn lại; lập bảng những tệp **giống** và **khác**. Tránh so sánh hai dự án chọn dependency hoặc phiên bản khác nhau rồi quy mọi khác biệt cho Maven/Gradle.

## 8. Các nhầm lẫn thường gặp và cách xử lý

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `mvnw`/`gradlew` là thư viện của ứng dụng | Đó là script **wrapper của công cụ build**; không phải mã nghiệp vụ Java. |
| Máy chưa cài Maven/Gradle nên không thể build | Wrapper thường tự tải phiên bản công cụ thích hợp; vẫn cần JDK/mạng nếu chưa có cache. |
| Dự án Gradle phải có `pom.xml` | Gradle đọc `build.gradle[.kts]` và `settings.gradle[.kts]`; không tự trộn lệnh Maven vào một dự án chỉ có Gradle. |
| `src/main/resources/application.properties` điều khiển Maven/Gradle | Nó phục vụ **cấu hình runtime** của Spring Boot; build được mô tả ở POM/build script. |
| Thư mục `target/`/`build/` phải có ngay sau giải nén | Đây thường là **đầu ra sinh sau build**; không có lúc đầu là bình thường. |
| `.gradle/` là thư mục wrapper cần commit | `gradle/wrapper/` chứa wrapper; `.gradle/` thường là trạng thái/cache sinh ra. |
| Tên package phải luôn bằng Artifact | Package là không gian tên Java, có thể đặt độc lập; kiểm tra dòng `package` trong mã. |
| Có `@SpringBootApplication` là có ngay REST API | Annotation khởi động Spring Boot; endpoint chỉ tồn tại khi có cấu hình/controller tương ứng. |
| Lỗi `Unsupported class file major version` hoặc yêu cầu toolchain là lỗi controller | Kiểm tra JDK mà terminal/IDE/Gradle đang dùng và yêu cầu Java của dự án trước. |
| Build ra hai tệp JAR thì tệp nào cũng chạy được như nhau | Phân biệt archive Boot thực thi với JAR thông thường; đọc cấu hình task và kiểm tra sản phẩm. |

## 9. Bài thực hành tự kiểm chứng

Tạo hoặc mở **hai dự án Java Spring Boot cùng thông số** (một Maven, một Gradle) và trả lời bằng **đường dẫn/tên tệp cụ thể trong dự án của bạn**:

1. File nào xác nhận dự án dùng Maven hoặc Gradle? File nào xác nhận **phiên bản công cụ wrapper**?
2. Dựa vào đâu biết Group/Artifact, phiên bản Java và phiên bản Spring Boot?
3. Dependency kiểm thử được khai báo ở đâu? Vì sao nó không nhất thiết phải có trên classpath của ứng dụng khi chạy?
4. Dòng nào gọi `SpringApplication.run`? File nào chứa cấu hình ứng dụng?
5. Chạy đúng lệnh kiểm thử qua wrapper. Báo cáo test nằm ở thư mục nào?
6. Chạy đóng gói, tìm tên archive thực tế và giải thích liệu đó có phải archive Spring Boot thực thi hay không.

**Tiêu chí hoàn thành:** bạn trỏ đúng từng tệp trong **dự án thực tế**, giải thích được vai trò của nó và thực hiện được ít nhất lệnh kiểm thử/build tương ứng trong môi trường có JDK, mạng/cache phù hợp. Nếu build lỗi, ghi lại lỗi và phân loại lỗi wrapper/JDK/dependency hay mã nguồn thay vì chỉ chụp dòng `BUILD FAILED`.

## Tài liệu đối chiếu

- Spring Initializr: https://start.spring.io/
- Spring Initializr Reference Guide: https://docs.spring.io/initializr/docs/current/reference/html/
- Spring Boot – Build Systems: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Gradle User Manual – Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html

Tệp do Initializr sinh theo **phiên bản và lựa chọn của lần khởi tạo** là nguồn kiểm tra cuối cùng khi ví dụ minh họa khác với dự án của bạn.
