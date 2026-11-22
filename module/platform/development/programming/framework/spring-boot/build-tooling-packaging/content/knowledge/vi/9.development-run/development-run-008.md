# Kiểm soát việc loại DevTools và công cụ hỗ trợ phát triển khỏi sản phẩm phát hành

## 1. Mục tiêu và nguyên tắc

Khi phát triển ứng dụng Spring Boot, ta thường cần **tự khởi động lại khi đổi mã**, **tự mở dịch vụ Docker Compose**, **chạy test**, **tạo mã từ annotation**, **debug** hoặc **xem dữ liệu cục bộ**. Các tiện ích này giúp phát triển nhanh hơn nhưng không mặc nhiên phải đi vào JAR, WAR hay container image đưa lên production.

Sau bài học, bạn sẽ có thể:

1. Phân biệt **dependency cần trong lúc phát triển**, **dependency phục vụ build/test**, **dependency runtime thực sự cần**, và **tài nguyên/cấu hình phát triển**.
2. Cấu hình `spring-boot-devtools` với Maven và Gradle để có trải nghiệm phát triển tốt nhưng **không đi vào executable artifact phát hành**.
3. Hiểu Maven `spring-boot-maven-plugin`, `repackage`, `excludeDevtools` và `excludeDockerCompose`; dùng `<excludes>` có kiểm soát cho các thư viện phát triển khác.
4. Hiểu Gradle `developmentOnly` và khác biệt giữa `runtimeClasspath` dùng khi phát triển với classpath đóng gói của `bootJar`/`bootWar`.
5. **Kiểm chứng bằng cách mở JAR/WAR thật**, không chỉ dựa vào profile, log khởi động hay cấu hình trên giấy.
6. Thêm kiểm tra vào CI để tránh vô tình phát hành DevTools, bộ test, file cấu hình cục bộ hoặc thư viện hỗ trợ không cần thiết.

**Điều kiện ví dụ:** các file `pom.xml` và `build.gradle` minh họa ứng dụng **Spring Boot 3.3.13, Java 17** để thống nhất cú pháp trong bài. Khi dự án dùng Spring Boot 3.5, 4.x hoặc Gradle/Maven plugin khác, hãy kiểm tra tài liệu chính thức **đúng phiên bản**. Đừng nâng/hạ phiên bản của dự án chỉ để sao chép ví dụ.

**Nguyên tắc trung tâm:** "DevTools không hoạt động ở production" **không đồng nghĩa** "DevTools không nằm trong artifact". Chỉ kiểm tra byte/nội dung archive phát hành mới xác nhận được việc loại trừ đóng gói.

## 2. Chọn đúng thứ cần loại: bốn nhóm khác nhau

| Nhóm | Ví dụ | Thường có trong artifact production? | Biện pháp |
| --- | --- | --- | --- |
| Runtime bắt buộc | Spring MVC, JSON serializer, driver CSDL thực dùng, security, logging runtime cần thiết | **Có**, tùy kiến trúc | `implementation`/`runtimeOnly` ở Gradle; Maven `compile`/`runtime` phù hợp |
| Dev runtime chỉ cho môi trường lập trình | `spring-boot-devtools`, `spring-boot-docker-compose`, thư viện trợ giúp chạy local | **Không**, trừ khi có lý do kiểm soát đặc biệt | Gradle `developmentOnly`; Maven plugin exclusion và khai báo đúng |
| Test/compile tooling | JUnit, Mockito, `spring-boot-starter-test`; annotation processor như Lombok/MapStruct processor | Thông thường **không** | Maven `test`, processor path; Gradle `testImplementation`, `annotationProcessor`/`compileOnly` |
| Cấu hình/dữ liệu cục bộ | `application-local.yml`, `.env`, script debug, test fixture, certificate dùng riêng | Thường **không**, tùy nhu cầu | Không đặt secret trong `src/main/resources`; exclude tài nguyên có chủ đích; dùng external config/secret store |

Không đánh đồng "**công cụ hỗ trợ**" với "**mã độc**". Chẳng hạn `spring-boot-starter-actuator` cung cấp endpoint quan sát hệ thống có thể **thực sự cần trong production** khi quản trị truy cập và exposure phù hợp; tự động loại Actuator chỉ vì nó hỗ trợ vận hành là sai. Ngược lại, một HTTP inspector, local database hoặc remote-devtool không có nhu cầu runtime thì không nên được mang theo chỉ vì tiện.

Với JAR/WAR, một tiện ích có thể đi vào artifact theo hai con đường:

- **Thư viện dependency**: ví dụ `spring-boot-devtools-<version>.jar` nằm trong `BOOT-INF/lib` của executable JAR.
- **Mã/tài nguyên của ứng dụng**: ví dụ debug controller, `application-local.yml`, mock data, file `.env` bị copy vào `BOOT-INF/classes`.

Loại dependency chỉ xử lý nhóm thứ nhất; muốn dọn nhóm thứ hai phải xem **source sets, resource processing, profile/configuration và chính nội dung archive**.

## 3. DevTools là gì và vì sao cần tách khỏi bản phát hành?

`spring-boot-devtools` cung cấp trải nghiệm phát triển: restart ứng dụng khi classpath thay đổi, LiveReload và một số mặc định thân thiện với phát triển (ví dụ cache template). Một dự án có thể cần nó khi chạy trong IDE hoặc `bootRun`/`spring-boot:run`, nhưng artifact phân phối cho production không cần mang nó theo.

### 3.1 Ba trạng thái phải phân biệt

| Trạng thái | Câu hỏi nó trả lời | Bằng chứng cần dùng |
| --- | --- | --- |
| **Có trong dependency declaration** | File POM/build có khai báo DevTools không? | `pom.xml` / `build.gradle[.kts]` |
| **Có trên development classpath** | Khi chạy lúc phát triển, ứng dụng có thể dùng DevTools không? | Maven/Gradle dependency resolution và cách chạy trực tiếp |
| **Có trong archive phát hành** | JAR/WAR gửi đi có chứa byte của DevTools không? | `jar tf` trên **đúng file artifact** |

Tài liệu Spring Boot nêu rằng DevTools **tự bị vô hiệu hóa** khi ứng dụng chạy như một fully-packaged application (ví dụ khởi động từ `java -jar`). Đây là **bảo vệ hành vi khi chạy**, không phải bằng chứng rằng `spring-boot-devtools-*.jar` đã bị loại khỏi ZIP/JAR/WAR. Nếu tùy biến plugin sai, bạn vẫn có thể đưa thư viện vào archive; nó chỉ không hoạt động trong trường hợp khởi động bình thường.

Bạn có thể tắt restart qua system property `-Dspring.devtools.restart.enabled=false`, nhưng **đó cũng không phải thao tác loại dependency khỏi archive**. Việc cố bật lại bằng `-Dspring.devtools.restart.enabled=true` trên production là hành động rủi ro và không nên thực hiện. Remote DevTools đặc biệt không nên được đưa vào một hệ thống production chỉ để debug từ xa.

### 3.2 Không phải mọi thư viện hỗ trợ đều có cơ chế loại mặc định

Spring Boot plugin nhận diện đặc biệt **`spring-boot-devtools`** và, ở các phiên bản Spring Boot có hỗ trợ, **`spring-boot-docker-compose`**. Những dependency bên thứ ba khác như một "local debug helper" do tổ chức tự viết **không tự động được loại** chỉ vì tên chứa "dev", "debug" hoặc do chúng đang được bật dưới profile `local`.

Đừng giả định một thư viện được loại bởi tên đặt trong `artifactId` hay có annotation `@Profile("dev")`. Cần kiểm tra **scope/configuration** và **cách task đóng gói nhận classpath**.

## 4. Maven: `optional`, `repackage` và tùy chọn loại DevTools

### 4.1 Ví dụ Maven POM đầy đủ cho một ứng dụng JAR

Tệp `pom.xml` dưới đây áp dụng Spring Boot parent và Maven plugin. `spring-boot-devtools` được khai báo `optional`, còn `repackage` đặt hai cờ loại trừ ở `true` (giá trị mặc định của plugin tương ứng phiên bản này; khai báo rõ để dễ review).

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-docker-compose</artifactId>
            <optional>true</optional>
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
                <configuration>
                    <excludeDevtools>true</excludeDevtools>
                    <excludeDockerCompose>true</excludeDockerCompose>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM đầy đủ cho phần build/dependency; để chạy đóng gói thành executable JAR, dự án vẫn cần lớp `main` có `@SpringBootApplication` (có ví dụ ở phần 7). `spring-boot-starter-parent` cấu hình sẵn execution `repackage`, nên chỉ cần khai báo `spring-boot-maven-plugin` trong `<plugins>`. Nếu dự án **không** kế thừa parent, bạn phải cấu hình execution `repackage` rõ ràng; đừng cho rằng mọi POM có plugin sẽ chạy repackage khi `package`.

#### Ý nghĩa từng thuộc tính

- `<optional>true</optional>` ở **dependency của Maven** chủ yếu nói với những module *tiêu thụ artifact của bạn* rằng họ không nên lấy dependency này **theo đường bắc cầu**. Nó **không phải** là "Maven không thể dùng dependency này trong chính project"; DevTools vẫn có thể phục vụ chạy tại môi trường phát triển.
- `<excludeDevtools>true</excludeDevtools>` là tùy chọn **Spring Boot Maven Plugin `repackage`** để loại `spring-boot-devtools` khỏi executable archive; mặc định là `true`.
- `<excludeDockerCompose>true</excludeDockerCompose>` loại `spring-boot-docker-compose` khỏi archive; mặc định là `true` với plugin có hỗ trợ.
- `<scope>test</scope>` giữ Spring Boot test starter trong dependency dành cho kiểm thử; nó không được coi là runtime dependency thông thường của bản phát hành.
- `<packaging>jar</packaging>` tạo loại artifact JAR; phần chính của Spring Boot repackage tổ chức dependency dưới `BOOT-INF/lib`.

**Lưu ý khác biệt phiên bản:** Spring Boot Maven Plugin các thế hệ mới có thêm lựa chọn chung về optional dependencies (như `includeOptional`); khả năng và giá trị mặc định có thể khác với 3.3.13. Vì vậy trong dự án thật **không chỉ suy luận từ `optional`**: hãy dùng đúng tài liệu plugin version và đọc artifact cuối cùng.

### 4.2 `spring-boot:repackage` khác `jar` và `scope` như thế nào?

Luồng Maven thường là:

```text
src/main/java + src/main/resources
          |
          v
       compile
          |
          v
        package ----> JAR/WAR thường trước khi repackage
          |
          v
spring-boot:repackage ---> executable Boot JAR/WAR
          |
          +-- loại spring-boot-devtools
          +-- loại spring-boot-docker-compose
          +-- áp dụng các <excludes> được cấu hình
```

Thứ tự và các artifact phụ thuộc configuration thực tế. Khi dùng Boot parent, `repackage` được gắn với lifecycle; `./mvnw package` thực hiện các phase trước và tạo artifact cuối. Trong một dự án không dùng parent và không cấu hình `repackage`, `target/*.jar` có thể chỉ là **JAR thường**, không phải cùng bố cục executable Boot JAR.

**Đặc biệt:** Maven scope `provided` không phải là "bảo đảm không đóng gói trong executable Spring Boot archive". Spring Boot Maven Plugin có thể đưa **provided dependencies** vào executable JAR/WAR để chạy độc lập; trong WAR chúng có thể nằm ở `WEB-INF/lib-provided`. Do đó nếu muốn loại một công cụ chỉ dùng local, đừng chỉ chuyển nó thành `provided` rồi kết luận an toàn. Đối với DevTools và Docker Compose, hãy tận dụng tùy chọn loại chuyên biệt và kiểm tra archive.

Đối với WAR triển khai lên servlet container ngoài, tài liệu Spring Boot còn nêu cần đánh dấu `spring-boot-devtools` và `spring-boot-docker-compose` là `optional` hoặc `provided` để cơ chế loại trừ hoạt động đúng theo cách WAR packaging. **Ưu tiên `optional` như ví dụ** và tiếp tục kiểm chứng cả `WEB-INF/lib` lẫn `WEB-INF/lib-provided`.

### 4.3 Cách loại thư viện hỗ trợ *khác* bằng `<excludes>`

Nếu một dependency bên thứ ba chỉ phục vụ local nhưng đang bị đưa vào archive, Spring Boot Maven Plugin có `<excludes>` theo tọa độ `groupId` và `artifactId`. **Ví dụ trích đoạn cấu hình**, thay tọa độ giả định bằng đúng dependency thực tế:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
        <excludeDockerCompose>true</excludeDockerCompose>
        <excludes>
            <exclude>
                <groupId>com.example.tools</groupId>
                <artifactId>local-debug-helper</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
```

`com.example.tools:local-debug-helper` chỉ là **tọa độ mô phỏng**, không khẳng định thư viện này tồn tại. Đoạn cấu hình nằm trong `<build><plugins>` của POM hiện có. Dùng exclusion **chính xác** an toàn hơn `<excludeGroupIds>` diện rộng vì có thể vô tình loại thư viện runtime hợp lệ khác chung group.

Trước khi loại, hãy điều tra **tại sao nó xuất hiện** (`dependency:tree`); tốt nhất là **đặt dependency vào scope phù hợp hoặc xóa khai báo không cần thiết**. `<excludes>` ở tầng đóng gói là hàng rào hữu ích nhưng có thể che giấu dependency đang được mã ứng dụng dùng. Nếu ứng dụng gọi API của công cụ đã bị loại, `java -jar` sẽ có nguy cơ `ClassNotFoundException` hoặc `NoClassDefFoundError`.

### 4.4 Cấu hình Maven WAR khác JAR ở điểm nào?

Maven có thể dùng `<packaging>war</packaging>` và Spring Boot repackage để tạo executable WAR. Trong trường hợp đó, thư viện ứng dụng thường nằm trong `WEB-INF/lib`; các dependency dành cho container có thể nằm trong `WEB-INF/lib-provided`. Đừng chỉ grep `BOOT-INF/lib` khi bạn đang kiểm thử WAR.

Nếu dự án triển khai trên servlet container ngoài, vẫn phải đáp ứng yêu cầu `SpringBootServletInitializer`, Servlet API tương thích và phân loại servlet container ở scope phù hợp. **Đó là bài toán khác với việc loại DevTools**, nhưng nếu thiếu bước triển khai bạn có thể nhầm một lỗi container thành lỗi DevTools.

Không bật `<excludeDevtools>false</excludeDevtools>` ở production chỉ để "tiện debug"; nếu có ngoại lệ phục vụ phát triển remote, đó phải là artifact tách riêng, không được đưa nhầm vào luồng phát hành production.

## 5. Gradle: `developmentOnly` và `bootJar`/`bootWar`

### 5.1 Ví dụ Groovy DSL đầy đủ

Với `settings.gradle`:

```groovy
rootProject.name = 'demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Có khi chạy phát triển, không đóng trong bootJar/bootWar mặc định.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là cấu hình **Spring Boot 3.3.x dùng Gradle Java plugin**. Project cũng cần lớp Java `main`. `io.spring.dependency-management` là lựa chọn quản lý BOM cho ví dụ, không phải cơ chế tự loại DevTools; khi dùng Gradle native BOM có thể quản lý version khác nhưng vẫn phân loại `developmentOnly`.

**`developmentOnly`** là configuration do Spring Boot Gradle plugin tạo khi áp dụng thích hợp. Các dependency khai báo ở đó phục vụ **quá trình phát triển**, và **mặc định không được đưa vào executable JAR/WAR** do `bootJar`/`bootWar` tạo. Để chạy từ IDE hoặc `bootRun`, source set runtime classpath dùng cho phát triển có thể bao gồm chúng; đây là điều mong muốn.

Trái lại, dòng sau **không phải cấu hình được khuyến nghị** nếu muốn DevTools chỉ dùng lúc phát triển:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

`runtimeOnly` nói thư viện này là **runtime dependency thông thường**. Khi DevTools đi vào lớp runtime production thay vì `developmentOnly`, bạn không được dựa vào việc nó "auto-disable" để bảo đảm JAR sạch. Hãy dùng `developmentOnly` rồi kiểm tra kết quả `bootJar`.

### 5.2 Kotlin DSL tương đương

Trong `build.gradle.kts`, các phần quan trọng là:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    developmentOnly("org.springframework.boot:spring-boot-docker-compose")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

**Đây là trích đoạn**: để có build file hoàn chỉnh, cần `group`, `version`, `java toolchain`, `repositories`, `tasks.test` tương ứng. Không dán cú pháp `developmentOnly '...'` của Groovy vào Kotlin DSL.

### 5.3 Ba classpath không đồng nghĩa

| Phần của Gradle | Vai trò | Có thể thấy DevTools? |
| --- | --- | --- |
| `runtimeClasspath` / `bootRun` cho ứng dụng phát triển | Chạy app trực tiếp từ classes/resources trong quá trình phát triển | **Có**, khi thêm đúng `developmentOnly` |
| `productionRuntimeClasspath` (cấu hình Boot plugin cung cấp ở phiên bản áp dụng) | Biểu diễn runtime đã loại những dependency chỉ dùng development | Theo thiết kế **không** chứa dependency chỉ xuất hiện qua `developmentOnly` |
| `bootJar`/`bootWar` classpath | Nguồn để tạo executable archive phát hành | Theo mặc định **không** chứa dependency `developmentOnly` |

Đây là sự khác nhau **có chủ đích**: nếu DevTools có mặt trong report `runtimeClasspath`, điều đó **không tự chứng minh** `bootJar` của bạn đang chứa DevTools. Phải so sánh classpath thích hợp và nội dung archive thật.

Lệnh điều tra:

```bash
# Development runtime; có thể có DevTools.
./gradlew dependencies --configuration runtimeClasspath

# Production runtime theo mô hình Spring Boot Gradle plugin.
./gradlew dependencies --configuration productionRuntimeClasspath

# Xem nguồn gốc một dependency trên runtime classpath.
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath

# Chạy để phát triển.
./gradlew bootRun

# Tạo artifact phát hành.
./gradlew clean bootJar
```

`developmentOnly` và `productionRuntimeClasspath` là các configuration **phụ thuộc plugin/phiên bản**; hãy đọc `./gradlew dependencies`/`./gradlew help --task bootJar` nếu tên không tồn tại. Với ứng dụng đa module, thêm đường project như `:app:dependencies` và kiểm tra classpath của **module ứng dụng phát hành**, không phải chỉ root project.

### 5.4 Không vô tình đưa `developmentOnly` trở lại archive

Tài liệu Spring Boot Gradle plugin có hướng dẫn **cố ý thêm** development-only dependency vào archive bằng cách thay classpath của `bootJar` hoặc `bootWar`. Ví dụ dưới đây là **mẫu cần tránh trong cấu hình phát hành**, chỉ minh họa lỗi review:

```groovy
// KHÔNG đặt vào pipeline release nếu mục tiêu là loại DevTools.
tasks.named('bootJar') {
    classpath configurations.developmentOnly
}
```

Đoạn này yêu cầu Boot task mang thêm dependency trong `developmentOnly` vào archive, **làm mất bảo đảm loại trừ mặc định**. Đừng nhầm `classpath configurations.developmentOnly` với việc "loại classpath" — đó là **thêm**.

Tương tự, với `war` plugin, hãy dùng `bootWar` cho executable WAR và xem task classpath; một override `classpath` hoặc custom Copy task có thể mang lại dependency dev vốn đã được phân loại đúng.

`jar`/`war` thường khác `bootJar`/`bootWar`, nên chỉ test task plain hoặc xem `-plain.jar` **không chứng minh** executable archive phát hành sạch.

## 6. Các công cụ khác: áp dụng chính sách theo chức năng

### 6.1 `spring-boot-docker-compose`

Từ Spring Boot 3.1, module `spring-boot-docker-compose` có thể hỗ trợ quản lý các dịch vụ bằng Docker Compose khi phát triển. Nó khác với việc ứng dụng production **phải chạy trong Docker**; Dockerfile/image không tự cần module này.

- **Maven:** thêm như optional dependency, giữ `excludeDockerCompose=true` trong `spring-boot-maven-plugin`, kiểm tra JAR/WAR.
- **Gradle:** khai báo trong `developmentOnly`. Không đưa module vào `implementation` chỉ vì dùng Compose trên laptop.
- **Đừng nhầm** "image build chạy Docker" với "application cần thư viện Spring Boot Docker Compose ở runtime". Chúng là hai khâu khác nhau.

Một dự án có thể không dùng `spring-boot-docker-compose`. Khi đó **không cần thêm dependency chỉ để có thứ mà ta loại**; file build tối giản vẫn tốt hơn.

### 6.2 Testing libraries

Thư viện `spring-boot-starter-test`, JUnit, Mockito và các fixture cho unit/integration test nên được khai báo theo scope/configuration **test**, không trong runtime.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đặt test helper trong `src/test/java` và `src/test/resources` thay vì `src/main` khi thực sự chỉ dùng để test. Nếu cần chia sẻ test fixtures giữa các module, dùng cấu hình/plugin chuyên biệt cho test fixtures thay vì cố kéo cả thư viện kiểm thử vào `implementation` của ứng dụng chính.

**Điểm cần nhớ:** `-DskipTests` hoặc `./gradlew -x test` chỉ **bỏ qua thực thi test**, không phải cơ chế chuyển dependency test thành "không còn trong artifact". Scope/configuration và cách đóng gói mới quyết định lớp thư viện trong archive.

### 6.3 Lombok và annotation processors

Thư viện annotation processor giúp tạo mã ở **compile time**; không mặc nhiên cần đóng vào runtime. Ví dụ với Gradle:

```groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'
}
```

Tọa độ và version có thể được dependency management hoặc configuration khác quản lý; đoạn trên chỉ minh họa **cách phân loại**, không phải một build.gradle hoàn chỉnh. Với Maven, dùng annotation processor paths hoặc cơ chế processor của Maven Compiler Plugin phù hợp phiên bản, và tránh đưa processor vào runtime dependency.

Không loại các thư viện runtime thực sự cần như MapStruct **runtime API**, database driver hoặc thư viện đã được mã sinh ra gọi ở runtime chỉ vì có phần "processor" trong hệ sinh thái tương ứng. Cần phân loại **artifact cụ thể**, không xét nhóm một cách mơ hồ.

### 6.4 Local diagnostics / debug agents / UI công cụ

Các tiện ích debug có thể được gắn bằng:

- Java agent lúc khởi động qua `-javaagent:/path/to/agent.jar`.
- Java system properties/IDE run configuration.
- Task `bootRun`, Maven `spring-boot:run` hoặc custom start script.
- Dependency trong `runtimeOnly`/`implementation` bị khai báo nhầm.

Một Java agent được truyền qua command line **không có nghĩa nằm trong executable JAR**; ngược lại, một jar debug trong `BOOT-INF/lib` không biến mất vì lệnh production không dùng `-javaagent`. Hãy kiểm tra **cả archive**, Dockerfile/entrypoint và script khởi động nếu mục tiêu là đảm bảo không đưa tooling vào môi trường phát hành.

Remote DevTools và remote debugging để lộ bề mặt rủi ro cao. Không bật cấu hình remote trên production như một mẹo kiểm chứng; ưu tiên quan sát hệ thống qua những cơ chế được thiết kế cho production, phân quyền và không đính kèm công cụ phát triển.

### 6.5 Không gọi mọi thứ có chữ "tools" là DevTools

Một số bản Spring Boot executable archive có `spring-boot-jarmode-tools` hỗ trợ layered archive/extraction phục vụ đóng gói container. Đây **không phải** `spring-boot-devtools`. Spring Boot Maven/Gradle plugin có tùy chọn `includeTools` để điều khiển một công cụ liên quan đến packaging ở những phiên bản hỗ trợ.

Nếu chính sách yêu cầu hạn chế, kiểm tra ý nghĩa và tác động của `includeTools=false` trước khi thay đổi; bỏ nó có thể ảnh hưởng pipeline tạo image dựa trên layer extraction. **Mục tiêu bài học không phải xóa mọi file có tên chứa "tools"**, mà xác định các artifact không cần tại runtime và tránh phá hành vi đóng gói đã thiết kế.

## 7. Ví dụ Java 17+ để kiểm chứng runtime sau khi đóng gói

Trong cả Maven và Gradle ví dụ, tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đây là **một lớp Java hoàn chỉnh cho dự án Spring Boot đã có các starter**. Nó không chạy bằng `javac DemoApplication.java` độc lập vì cần Spring Boot thư viện trên classpath. Với `spring-boot-starter-web`, endpoint `GET /ready` trả text:

```text
ready
```

Đó là **response body của controller**, không phải log Maven/Gradle. Khi chạy ứng dụng độc lập ở cổng mặc định 8080 và không đặt context path khác, có thể dùng `curl http://localhost:8080/ready`. Nếu đổi port/profile/context path, phải dùng URL thực tế.

Tạo test tối thiểu `src/test/java/com/example/demo/DemoApplicationTests.java`:

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

Khi chạy `./mvnw test` hoặc `./gradlew test` với những cấu hình Maven/Gradle bên trên, test sẽ kiểm tra context khởi động được. Nó **không tự chứng minh DevTools đã bị loại khỏi JAR**; bằng chứng đó nằm ở phần kiểm tra archive bên dưới.

### Chạy lúc phát triển rồi chạy artifact

Maven:

```bash
# Từ thư mục có pom.xml và mvnw
./mvnw spring-boot:run

# Ở một terminal khác, gọi endpoint:
curl http://localhost:8080/ready

# Dừng ứng dụng rồi đóng gói:
./mvnw clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

Gradle:

```bash
# Từ thư mục có build.gradle và gradlew
./gradlew bootRun

# Terminal khác:
curl http://localhost:8080/ready

# Dừng ứng dụng rồi đóng gói:
./gradlew clean bootJar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Lưu ý `spring-boot:run`/`bootRun` thường **giữ terminal** trong lúc ứng dụng chạy; phải dừng ứng dụng hoặc mở terminal khác trước lệnh build để không xung đột cổng 8080. Khi dùng Docker Compose dev support, việc tạo/kết nối container phục vụ local phụ thuộc file Compose và môi trường Docker; nếu không muốn Spring Boot tự chạy Compose ở bài tập endpoint, có thể **không thêm module `spring-boot-docker-compose`** hoặc cấu hình tắt trong môi trường thực hành.

Bảng các quan sát mong đợi:

| Kiểm tra | Development run | Packaged production-style run |
| --- | --- | --- |
| DevTools dependency | Có thể nằm trên classpath phát triển | Được loại khỏi executable archive nếu cấu hình đúng |
| Restart/live reload | Có thể hoạt động khi classpath thay đổi | Không phải chức năng cần cho sản phẩm phát hành |
| `/ready` | Trả `ready` khi app khởi động thành công | Vẫn trả `ready` khi archive hợp lệ |
| Test starter | Dùng trong `test` | Không nằm trong runtime library path của archive |
| Chứng minh artifact sạch | **Chưa**, vì chỉ là quá trình chạy local | Cần `jar tf`/kiểm tra image đã phát hành |

## 8. Kiểm tra trực tiếp JAR/WAR thật: bước bắt buộc

### 8.1 Kiểm tra tên archive đúng trước

Sau Maven `./mvnw clean package`, bản Spring Boot executable JAR của ví dụ có thể là `target/demo-0.0.1-SNAPSHOT.jar`. Một file `.original` khác có thể chứa archive trước repackage: **không chọn nó thay cho artifact deploy**.

Sau Gradle `./gradlew clean bootJar`, executable JAR của ví dụ có thể là `build/libs/demo-0.0.1-SNAPSHOT.jar`; nếu `jar` task cũng chạy, có thể có `demo-0.0.1-SNAPSHOT-plain.jar`. Đừng kiểm tra nhầm file plain khi CI thực tế deploy file boot (hoặc ngược lại).

Các tên trên phụ thuộc `artifactId`, `rootProject.name`, `version` và tùy chỉnh archive. Trong dự án thật, **tìm đúng file được stage deploy sử dụng** rồi kiểm tra chính file đó.

### 8.2 Mở JAR bằng công cụ JDK

`jar tf` liệt kê nội dung ZIP/JAR/WAR, không cần chạy ứng dụng:

```bash
# Maven (đúng ví dụ)
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle (đúng ví dụ)
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

Một executable Spring Boot JAR thường có bố cục:

```text
BOOT-INF/
    classes/
        com/example/demo/DemoApplication.class
    lib/
        spring-boot-...jar
        spring-webmvc-...jar
        ... runtime dependencies ...
META-INF/
org/springframework/boot/loader/...
```

Đây là cây **minh họa**. Tên thư viện, phiên bản và lớp launcher cụ thể phụ thuộc phiên bản Boot/ứng dụng. Nếu cấu hình ví dụ đúng, **không** được thấy:

```text
BOOT-INF/lib/spring-boot-devtools-<version>.jar
BOOT-INF/lib/spring-boot-docker-compose-<version>.jar
BOOT-INF/lib/spring-boot-starter-test-<version>.jar
BOOT-INF/lib/junit-jupiter-<version>.jar
```

Những dòng trên mô tả **mục cần vắng mặt**, không phải tệp tên thực tế của artifact. Chữ `<version>` chỉ là ký hiệu giải thích, không phải tên file nguyên văn.

Với executable WAR, phải kiểm tra cả `WEB-INF/lib/` **và** `WEB-INF/lib-provided/`. Một dependency không nằm ở `WEB-INF/lib` vẫn có thể bị đóng gói ở `lib-provided`. Chỉ kiểm tra `BOOT-INF/lib` thì không dùng được cho WAR.

### 8.3 Lệnh kiểm tra nhanh có thể chạy trong CI (Bash)

Đoạn này kiểm tra **tên JAR của hai module phát triển Spring Boot** bên trong executable JAR/WAR. Nó dùng `jar tf` và `grep`, không cần mở từng file thủ công:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Thay bằng đúng artifact deploy. Ví dụ Maven:
artifact="target/demo-0.0.1-SNAPSHOT.jar"

# jar tf thất bại -> script thất bại (archive thiếu hoặc hỏng).
entries="$(jar tf "$artifact")"

# Match ZIP path của executable JAR hoặc WAR.
dev_regex='^(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/(spring-boot-devtools|spring-boot-docker-compose)-[^/]+[.]jar$'

if printf '%s\n' "$entries" | grep -E "$dev_regex"; then
    echo "FAIL: development-only module exists in release archive"
    exit 1
fi

echo "PASS: no Spring Boot DevTools/Docker Compose JAR in archive"
```

**Ý nghĩa chính xác:** nếu `jar tf` thành công và `grep` không tìm thấy hai module ở các thư mục chuẩn, lệnh in:

```text
PASS: no Spring Boot DevTools/Docker Compose JAR in archive
```

Đây là stdout **chỉ trong điều kiện trên** (không khẳng định đã chạy trong dự án thật). Nếu có module, script in đường dẫn bị phát hiện và exit 1; nếu không đọc được archive, script dừng do `set -e`.

Mẫu này không thay thế kiểm tra **mọi** công cụ dev nội bộ; bạn có thể mở rộng danh sách `artifactId` theo danh mục được tổ chức phê duyệt. Đừng tự đưa một thư viện runtime thiết yếu vào denylist mà không phân tích dependency graph.

### 8.4 PowerShell (Windows)

```powershell
$artifact = "target/demo-0.0.1-SNAPSHOT.jar"
$entries = & jar tf $artifact
if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect release archive"
}

$pattern = '^(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/(spring-boot-devtools|spring-boot-docker-compose)-[^/]+[.]jar$'
$hits = @($entries | Select-String -Pattern $pattern)
if ($hits.Count -gt 0) {
    $hits
    throw "Development dependency found in release archive"
}
Write-Output "PASS: no Spring Boot DevTools/Docker Compose JAR in archive"
```

Lệnh này yêu cầu JDK `jar` trong `PATH` và đang đứng đúng thư mục làm việc. Với Gradle, thay `$artifact` bằng đường dẫn `build/libs/...jar` thực tế. Nó kiểm tra **bản đã build**, không chứng minh Docker image đã chứa đúng bản đó nếu image build dùng một artifact khác.

### 8.5 Kiểm tra test dependency và config dev bị đóng nhầm

Có thể dùng thêm tìm kiếm thủ công:

```bash
jar tf target/demo-0.0.1-SNAPSHOT.jar | grep -E \
  '(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/|application-(local|dev)[.]|(^|/)[.]env$'
```

Báo cáo này dùng để **xem xét**, không phải lệnh PASS/FAIL tự động: một file tên `application-dev.yml` có thể vẫn có mục đích hợp lệ nếu không chứa secret; nhưng cần đánh giá kỹ xem có muốn đóng vào bản production không. Một `.env` hoặc file mật khẩu trong `src/main/resources` không biến mất chỉ nhờ `excludeDevtools`.

Với bài kiểm soát bảo mật, nên kiểm tra thêm **SBOM/dependency inventory**, source/secret scanning và nội dung Docker image sau build. Archive sạch ở một module không đảm bảo toàn bộ repository và mọi image đều sạch.

## 9. Vì sao DevTools còn bị đóng vào artifact dù đã "tắt trong production"?

Tình huống này có thể xảy ra khi:

1. **Gradle:** DevTools bị khai báo `implementation` hoặc `runtimeOnly` thay vì `developmentOnly`.
2. **Gradle:** custom `bootJar`/`bootWar` classpath được nối thêm `configurations.developmentOnly`.
3. **Maven:** project không thực sự chạy `spring-boot:repackage`, hoặc chạy plugin phiên bản/config khác với dự đoán; artifact kiểm tra là JAR trước repackage.
4. **Maven:** `excludeDevtools` bị đặt `false` hoặc exclusion được cấu hình sai chỗ, hoặc WAR và `optional`/scope không theo quy tắc plugin.
5. **Build chung:** DevTools bị kéo qua một module thư viện khác trên runtime dependency graph, hoặc pipeline tạo artifact tùy chỉnh thay vì Boot executable archive.
6. **CI:** dùng nhầm file `-plain.jar`, `.original`, JAR phiên bản cũ từ cache, hoặc tạo image từ một thư mục build khác.
7. **Không phải dependency:** mã debug, file cấu hình local, thư viện đã bị shade/đóng gói lại dưới tên khác; tìm `spring-boot-devtools-*.jar` có thể không phát hiện thứ đã bị copy thành class.

Khi nghi ngờ, đừng sửa ngay bằng một cờ "disable" và tuyên bố xong. Hãy giải quyết theo **đúng lớp**: dependency graph → task/scope → output archive → image/runtime.

### Maven: tìm nguồn dependency

```bash
# Nhìn đường nào kéo devtools vào build:
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools

# Xem Maven model sau khi áp dụng parent/profiles:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Build mới bằng Wrapper:
./mvnw clean package
```

Một dòng `dependency:tree` có DevTools là **bằng chứng dependency xuất hiện trong graph của project**, không phải bằng chứng nó sẽ nằm trong executable JAR. Đọc riêng phần plugin và `jar tf`. Lệnh `clean` sẽ xóa `target`; chỉ chạy ở workspace bạn được phép build.

Nếu dependency do một starter/module nội bộ khác kéo vào, nên cân nhắc đặt nó là **optional** ở module khai báo, tách thành một module chỉ cho phát triển, hoặc khai báo exclusion hợp lý tại ứng dụng. Đừng loại xung đột theo cách làm ứng dụng mất thư viện runtime cần thiết.

### Gradle: giải thích đường đi

```bash
./gradlew dependencyInsight \
  --dependency spring-boot-devtools \
  --configuration runtimeClasspath

./gradlew dependencies --configuration productionRuntimeClasspath

./gradlew clean bootJar
```

Nếu `runtimeClasspath` có DevTools nhưng `productionRuntimeClasspath` không có thì đó có thể là hành vi **đúng thiết kế** của `developmentOnly`. Nếu vẫn thấy DevTools trong `BOOT-INF/lib` của `bootJar`, xem các thay đổi `classpath` của `bootJar`, plugin tùy chỉnh và đúng file artifact.

Khi phân tích module con, chọn đúng target, ví dụ `./gradlew :app:dependencies --configuration productionRuntimeClasspath` nếu `:app` là module phát hành. Không dùng report của module khác thay bằng chứng của application module.

### "Không tìm thấy DevTools" nhưng app vẫn có hành vi dev

Một số mặc định development hoặc feature riêng có thể xuất phát từ:

- Cấu hình `application.yml`/system property (ví dụ cache template, stacktrace detail).
- IDE/Gradle task/custom run script gắn agent.
- Mã được viết riêng và bật qua `@Profile("local")` hoặc feature flag.
- Resource/script dev nằm trong JAR dù dependency DevTools chính đã vắng mặt.

Vì vậy **gỡ DevTools là một bước**, không phải lời hứa tự động "hardened production". Cần kiểm tra production profile, logging, endpoint exposure, bí mật và vận hành theo tiêu chí riêng.

## 10. Không để file dev-only rò rỉ qua `src/main/resources`

Các file trong `src/main/resources` thường được copy vào application classpath và đóng trong executable archive, dù active profile lúc chạy là `prod`. **`@Profile` hoặc `spring.profiles.active` không làm resource bị xóa khỏi JAR.**

Ví dụ:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-prod.yml
├── static/
│   └── ...
└── private-dev-data.json
```

Về mặc định, `application-local.yml` và `private-dev-data.json` vẫn có thể được đóng vào JAR. Spring không nhất thiết đọc `application-local.yml` khi chạy prod, nhưng byte của tệp vẫn tồn tại trong artifact. **Không bao giờ coi "profile không active" là biện pháp bảo mật bí mật**.

Biện pháp ưu tiên:

- Đưa credential/secret ra khỏi repository và archive; dùng environment, secret store hoặc external config theo chính sách vận hành.
- Đặt fixture và dữ liệu test trong `src/test/resources`, không phải `src/main/resources` nếu chỉ dùng test.
- Với file local có lý do tồn tại trong repo nhưng không được phát hành, đặt chúng trong thư mục dành cho development mà build không copy, hoặc dùng include/exclude có kiểm chứng.
- Không filter password lúc build vào `application-prod.yml` hoặc Dockerfile rồi cho rằng nó an toàn vì file không được "in ra" trong log.

### Gradle loại resource dev-only bằng `processResources`

Ví dụ **trích đoạn Groovy DSL**:

```groovy
tasks.named('processResources') {
    exclude('private-dev-data.json')
    exclude('application-local.yml')
}
```

Đoạn này bảo Gradle Java plugin **không copy** những đường dẫn tương đối vào `build/resources/main`. Nếu ứng dụng thật có lý do sử dụng `application-local.yml` khi chạy trực tiếp trên classpath, **không áp dụng bừa**: cần chọn cách cung cấp external config trong môi trường local. `bootRun` thường cũng dựa vào source set output, nên một exclude có thể làm thay đổi hành vi local — đó là lý do tách resource local khỏi nguồn production ngay từ đầu là tốt hơn.

### Maven loại resource theo `<excludes>`

Ví dụ **trích đoạn** trong `<build>`:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <excludes>
            <exclude>private-dev-data.json</exclude>
            <exclude>application-local.yml</exclude>
        </excludes>
    </resource>
</resources>
```

**Cảnh báo:** định nghĩa lại `<build><resources>` có thể thay thế quy tắc filtering của `spring-boot-starter-parent`, ví dụ lọc `application.properties` bằng `@...@`. Trong dự án Maven hiện có, đọc `help:effective-pom` và giữ các resource groups/filters cần thiết khi áp dụng exclude; không chép trích đoạn này máy móc rồi làm hỏng filtering khác.

## 11. Kiểm soát sản phẩm phát hành ở CI/CD

Muốn ngăn hồi quy, đặt một **hàng rào kiểm chứng artifact** giữa build và deploy, không chỉ review `pom.xml`/`build.gradle` một lần.

### 11.1 Pipeline tối thiểu có bằng chứng

1. **Checkout mã đã review** và dùng Maven/Gradle Wrapper đã tin cậy.
2. **Chạy test** ở stage riêng; không để việc bỏ qua test thành "cách loại thư viện test".
3. **Build sản phẩm release** bằng đúng task: Maven `package` với Spring Boot repackage, Gradle `bootJar` hoặc `bootWar`.
4. **Chọn đúng artifact**: tuyệt đối không dùng wildcard quá rộng khi thư mục chứa cả executable và plain archive hoặc file build cũ.
5. **Kiểm tra archive** bằng `jar tf`, đối chiếu denylist dependency phát triển và các tài nguyên cấm.
6. **Thất bại pipeline nếu có artifact bị cấm**; in ra đường dẫn vi phạm để sửa.
7. **Đưa chính artifact đã kiểm tra vào deploy/image stage**, không build lại bằng command khác mà bỏ qua bước kiểm tra.
8. **Kiểm tra image cuối** nếu Dockerfile/buildpack có khả năng gắn thêm file từ build context, agent hoặc các lớp khác ngoài JAR.

Gắn hash SHA-256 cho artifact đã kiểm tra có thể giúp theo dấu "file được deploy là file nào"; hash của artifact **không tự chứng minh** nó sạch nếu chưa chạy kiểm tra nội dung.

### 11.2 Khi build container image

Một Dockerfile hoặc image builder có thể đưa vào nhiều thứ hơn executable JAR. Nếu dùng câu lệnh kiểu "copy toàn bộ thư mục workspace" vào image, `.env`, thư mục test và cache build có thể vô tình xuất hiện. Cách tốt hơn là **copy đúng artifact** đã được kiểm tra từ build stage, dùng `.dockerignore` và tránh gắn secret ở build-time vào image layer.

Ví dụ **trích đoạn Dockerfile dùng artifact đã build sẵn**, không phải Dockerfile hoàn chỉnh cho mọi CI:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Cấu hình này áp dụng cho Maven JAR ví dụ nếu file đã được build, có mặt trong Docker build context và được scan. Với Gradle, cần thay đường `target/...` bằng đúng `build/libs/...`; với WAR triển khai container ngoài, base image/entrypoint khác hẳn. Dù chỉ COPY một JAR, **nội dung JAR vẫn cần được kiểm tra**; Dockerfile không "gỡ" DevTools đã được đóng sẵn trong nó.

### 11.3 Danh mục chặn có phiên bản

Cơ chế loại mặc định của Spring Boot áp dụng một số module được biết trước. Tổ chức có thể có các thư viện dev riêng; hãy duy trì danh mục như:

```text
# Tọa độ minh họa, cần thay bằng danh mục có thật của dự án.
org.springframework.boot:spring-boot-devtools
org.springframework.boot:spring-boot-docker-compose
com.example.tools:local-debug-helper
```

Đừng biến tên tọa độ giả định thành "dependency đã được phát hiện". Quy trình release nên xem xét denylist theo thay đổi thư viện và **chọn chính xác** điều gì không được có, thay vì grep chuỗi `debug` vô tội vạ vì có thể chặn thư viện quan sát/diagnostics được phép dùng production.

## 12. Tình huống thực tế: đổi một dòng dẫn tới rò rỉ như thế nào?

### Tình huống A – Gradle: nhầm `developmentOnly` thành `runtimeOnly`

Ban đầu:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

Một pull request thay thành:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

**Tại sao nguy hiểm?** Mặc dù `bootRun` vẫn có thể có restart, dependency giờ được phân loại là runtime. Một archive tùy biến hoặc task `bootJar` có thể mang module này vào production. Cách xem lại đúng là chuyển dependency về `developmentOnly` rồi chạy **release build + archive inspection**, không chỉ test rằng app khởi động ở chế độ `local`.

### Tình huống B – Maven: `optional` không phải "xóa khỏi app"

Project có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

Nhận xét "đã có `optional=true` thì artifact chắc chắn sạch" là **thiếu bước kiểm tra**. Maven optional chủ yếu điều khiển việc dependency truyền sang các project khác; bản đóng gói ứng dụng còn chịu Spring Boot Maven Plugin `repackage` và các exclusions. Điều đúng cần chứng minh là `excludeDevtools` của plugin có hiệu lực, `package` dùng repackage và `jar tf` không có module.

### Tình huống C – Chuyển sang WAR nhưng chỉ kiểm tra `BOOT-INF/lib`

Ứng dụng chuyển từ Boot JAR sang WAR. Script scan cũ chỉ tìm `BOOT-INF/lib/spring-boot-devtools`, nên luôn báo "PASS" dù WAR có thể chứa nó trong `WEB-INF/lib` hoặc `WEB-INF/lib-provided`.

**Sửa:** nhận diện layout theo artifact rồi kiểm tra **cả ba** đường dẫn. Kiểm tra tương ứng của JAR/WAR phải nằm trong CI, không chỉ ghi trong wiki.

### Tình huống D – Bỏ DevTools khỏi JAR nhưng vẫn copy `.env`

Ứng dụng đã có Maven `excludeDevtools=true` hoặc Gradle `developmentOnly`. Tuy nhiên một developer để file `.env` hoặc khóa cá nhân trong `src/main/resources`. File vẫn được copy vào `BOOT-INF/classes` khi build, dù DevTools vắng mặt.

**Sửa:** loại dữ liệu nhạy cảm khỏi repository và artifact bằng cơ chế cấu hình/secret management thích hợp; kiểm tra resource output và image. **DevTools exclusion không phải công cụ quét bí mật.**

### Tình huống E – Docker Compose module và runtime driver bị nhầm

Local dev dùng Docker Compose để khởi động một database, và app có database driver thật. Khi lên production, bạn thường **không cần** thư viện `spring-boot-docker-compose` trong executable archive, nhưng **vẫn có thể cần** JDBC driver để kết nối tới database production.

Nếu loại cả driver chỉ vì "database được Compose khởi động trong dev", ứng dụng có thể không kết nối được khi chạy thật. Phân biệt **công cụ khởi động dịch vụ local** với **mã kết nối database runtime** trước khi tối giản.

## 13. Checklist quyết định: khi nào một công cụ được phép vào release?

Khi review một dependency/công cụ hỗ trợ, tự trả lời:

1. Nó được **mã ứng dụng runtime** gọi, hay chỉ được IDE/build/test dùng?
2. Có bị kéo vào dưới dạng dependency bắc cầu từ module khác không?
3. Nó nằm trong Gradle `developmentOnly` / `testImplementation` hay đã lạc vào `implementation` / `runtimeOnly`?
4. Với Maven, `scope`/`optional` có đúng không? Boot `repackage` đang loại module đó thật không?
5. Có override `bootJar.classpath`, `bootWar.classpath`, `includeOptional` hay `excludeDevtools=false` nào làm thay đổi mặc định không?
6. Nếu cần ở dev, liệu **không có trong release** vẫn giữ đủ trải nghiệm ở `bootRun`/`spring-boot:run` không?
7. File có nằm trong `BOOT-INF/lib`, `WEB-INF/lib`, `WEB-INF/lib-provided` hay đã bị shade/copy vào `classes`?
8. Có mã debug, `application-local.yml`, test fixture, dữ liệu mẫu hoặc secret nào trong `BOOT-INF/classes` không?
9. CI đang scan **đúng artifact** được deploy và kiểm tra image cuối hay chỉ scan một bản build khác?
10. Sau khi loại, test và startup production-style có còn chạy được không?

Một dependency hợp lệ cho production phải có **lý do runtime rõ ràng**, không chỉ vì nó giúp developer. Nhưng "giảm kích thước JAR" không phải tiêu chí duy nhất; cần không làm hỏng tính năng vận hành thực sự cần như health/metrics/security.

## 14. Bài thực hành có thể kiểm chứng

### Bài 1 – Maven: từ khai báo đến artifact

Dùng Maven POM và lớp `DemoApplication` của phần 4 và phần 7:

1. Chạy `./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools`, ghi nhận Maven có dependency trong project.
2. Chạy `./mvnw spring-boot:run` trong môi trường phát triển có cấu hình thích hợp; xác định DevTools nếu active. Dừng ứng dụng.
3. Chạy `./mvnw clean package`, tìm đúng `target/demo-0.0.1-SNAPSHOT.jar`.
4. Dùng `jar tf` kiểm tra `BOOT-INF/lib`. Tìm `spring-boot-devtools` và `spring-boot-docker-compose`; giải thích vì sao chúng phải **vắng mặt**.
5. Chạy `java -jar target/demo-0.0.1-SNAPSHOT.jar`; kiểm tra endpoint `/ready` vẫn hoạt động.
6. Giải thích vai trò khác nhau của `<optional>true</optional>`, `<scope>test</scope>` và `<excludeDevtools>true</excludeDevtools>`.
7. **Không thay cấu hình production**, chỉ trên một bản sao thực hành, quan sát điều gì thay đổi nếu tạm tùy biến cờ plugin. Không tạo artifact cố ý mang DevTools rồi đưa nó vào release.

### Bài 2 – Gradle: so sánh classpath development và production

Với `build.gradle` và lớp `DemoApplication` như trên:

1. Chạy `./gradlew dependencies --configuration runtimeClasspath`, tìm `spring-boot-devtools` và ghi lại đường đi.
2. Chạy `./gradlew dependencies --configuration productionRuntimeClasspath`; giải thích vì sao dependency chỉ thuộc `developmentOnly` không nằm trong production runtime.
3. Dùng `./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath` nếu cần xác định ai kéo vào.
4. Chạy `./gradlew clean bootJar`, mở `build/libs/demo-0.0.1-SNAPSHOT.jar` bằng `jar tf`.
5. Kiểm tra script Bash hoặc PowerShell của phần 8 cho ra **PASS** theo cấu hình ví dụ.
6. Chạy `java -jar` và `GET /ready` để xác nhận ứng dụng không phụ thuộc vào DevTools để khởi động.
7. Trên nhánh thử nghiệm, so sánh `developmentOnly` với `runtimeOnly` mà **không** đẩy cấu hình đưa DevTools vào pipeline phát hành.

### Bài 3 – Kiểm soát WAR, file dev và CI

1. Trên một ứng dụng Spring MVC WAR hợp lệ, build `bootWar` hoặc Maven repackage WAR và kiểm tra cả `WEB-INF/lib` lẫn `WEB-INF/lib-provided`.
2. Đặt một file không nhạy cảm như `private-dev-data.json` trong `src/main/resources` để mô phỏng resource dev. Thêm include/exclude phù hợp và kiểm tra file **không nằm trong archive**; không dùng bí mật thật để test.
3. Tạo CI stage chạy script từ phần 8 với **đường dẫn artifact được stage deploy dùng**. Thử nghiệm trên bản sao artifact có dependency vi phạm để bảo đảm stage báo FAIL, không sửa artifact production thật.
4. Nếu dự án đóng Docker image, xác minh image cuối chỉ mang thành phần được phép và không copy cả workspace.

**Tiêu chí đạt:** có bằng chứng từ source build, dependency graph, **đúng executable artifact**, kết quả kiểm tra PASS/FAIL có thể lặp lại và startup smoke test. Không đủ khi chỉ nói "DevTools auto-disabled" hoặc "profile prod không sử dụng nó".

## Tài liệu chính thức

- Spring Boot Developer Tools (khai báo Maven optional / Gradle developmentOnly và hành vi khi packaged): https://docs.spring.io/spring-boot/reference/using/devtools.html
- Spring Boot Maven Plugin – Packaging Executable Archives, `excludeDevtools`/`excludeDockerCompose`/`excludes`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot Gradle Plugin – Packaging Executable Archives và `developmentOnly`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot Gradle Plugin – Running Your Application: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot Gradle Plugin – Reacting to Other Plugins: https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html
- Maven – Introduction to the Dependency Mechanism (`scope`, `optional`): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle – Dependency Configurations: https://docs.gradle.org/current/userguide/declaring_configurations.html

**Ghi nhớ:** kiểm soát dependency có ít nhất ba lớp: **khai báo và phân loại đúng → build/repackage loại đúng → chứng minh archive và image phát hành thực tế không chứa nội dung cấm**. Nếu thiếu lớp cuối, ta mới chỉ tin rằng cấu hình đúng chứ chưa xác nhận được kết quả.
