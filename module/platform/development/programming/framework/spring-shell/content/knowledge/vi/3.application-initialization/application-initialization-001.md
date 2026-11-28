# Tạo ứng dụng Spring hoặc Spring Boot phù hợp phiên bản mục tiêu

Để xây dựng CLI bằng Spring Shell, trước hết cần tạo một ứng dụng Spring có runtime phù hợp với phiên bản Spring Shell dự định sử dụng. Với dự án mới, Spring Boot thường là lựa chọn thuận tiện nhất vì starter của Spring Shell được thiết kế để tích hợp với hệ sinh thái Spring Boot: dependency được quản lý tập trung, cấu hình được nạp tự động và ứng dụng có điểm khởi chạy rõ ràng.

Việc khởi tạo dự án không chỉ là tạo một class có hàm `main`. Cần chọn đúng bộ phiên bản JDK, Spring Boot, Spring Framework và Spring Shell; khai báo dependency; đặt package để component được phát hiện; rồi chạy thử ứng dụng để xác nhận shell đã khởi động.

## 1. Chọn kiểu ứng dụng và phiên bản mục tiêu

Trước khi tạo project, hãy xác định ứng dụng đang ở tình huống nào:

| Tình huống | Hướng khởi tạo phù hợp |
|---|---|
| Tạo một CLI mới | Tạo Spring Boot project và thêm Spring Shell starter tương thích |
| Đã có ứng dụng Spring Boot | Giữ nền tảng hiện tại nếu tương thích, thêm Spring Shell starter và cấu hình command |
| Đã có ứng dụng Spring Framework không dùng Boot | Kiểm tra cách tích hợp và bootstrap được tài liệu của đúng phiên bản Spring Shell hỗ trợ trước khi thêm dependency |
| Nâng cấp ứng dụng Spring Shell cũ | Xác định bộ JDK, Boot, Framework và Shell đang dùng; lập kế hoạch nâng cấp theo ma trận tương thích |

Spring Shell có các dòng phát hành khác nhau và yêu cầu nền tảng có thể thay đổi theo dòng. Không nên chọn phiên bản chỉ vì đó là phiên bản mới nhất nhìn thấy trên kho dependency. Hãy kiểm tra tài liệu phát hành và hướng dẫn tương thích của phiên bản mục tiêu.

### 1.1. Kiểm tra bốn thành phần phiên bản

Bốn thành phần cần được xem cùng nhau:

- **JDK:** phiên bản Java tối thiểu mà Spring Boot và Spring Shell mục tiêu yêu cầu.
- **Spring Boot:** phiên bản nền tảng ứng dụng và cơ chế auto-configuration.
- **Spring Framework:** phiên bản nền tảng mà Spring Boot quản lý.
- **Spring Shell:** phiên bản cung cấp command, parser, prompt, help và completion.

Với dự án dùng Spring Boot, Spring Boot quản lý phiên bản Spring Framework thông qua dependency management. Vì vậy, thông thường nên để Boot chọn phiên bản Spring Framework tương ứng, tránh tự ghi đè một module Spring riêng lẻ nếu chưa có lý do và kiểm tra tương thích.

Có thể dùng bảng sau làm checklist trước khi tạo project:

| Thành phần | Cần xác nhận |
|---|---|
| JDK | Đã cài đúng phiên bản và IDE/build tool đang dùng cùng JDK |
| Spring Boot | Có hỗ trợ JDK đã chọn và tương thích với dòng Spring Shell mục tiêu |
| Spring Framework | Được quản lý theo bộ phiên bản của Spring Boot hoặc theo hướng dẫn tích hợp chính thức |
| Spring Shell | Có starter và hướng dẫn cấu hình dành cho nền tảng đã chọn |
| Maven hoặc Gradle | Wrapper và plugin build tương thích với JDK, Boot và cách khai báo dependency |

Nếu một dự án dùng Spring Boot cũ nhưng thêm Spring Shell mới mà không kiểm tra tương thích, lỗi có thể xuất hiện ngay khi resolve dependency, khi tạo ApplicationContext hoặc lúc khởi tạo command. Chốt bộ phiên bản trước giúp giảm những lỗi khó truy nguyên này.

### 1.2. Vì sao Spring Boot thường phù hợp với CLI mới?

Spring Boot cung cấp các cơ chế hữu ích cho một ứng dụng dòng lệnh:

- Khởi tạo ApplicationContext và quản lý vòng đời bean.
- Dependency injection để command gọi application service.
- Nạp cấu hình từ file, biến môi trường và tham số khởi chạy.
- Auto-configuration dựa trên dependency có trong classpath.
- Đóng gói ứng dụng thành artifact có thể chạy bằng `java -jar`.

Spring Shell bổ sung cơ chế CLI trên nền ứng dụng Spring. Khi dùng starter phù hợp, ứng dụng có thể tập trung vào command và nghiệp vụ thay vì tự ghép các thành phần khởi động.

Một ứng dụng Spring Framework không dùng Boot có cách quản lý context và dependency khác. Không nên giả định rằng chỉ thêm `spring-shell-starter` là mọi cơ chế auto-configuration và vòng đời shell sẽ tự hoạt động trong một context Spring bất kỳ. Nếu phải tích hợp vào ứng dụng hiện hữu không dùng Boot, hãy xác minh rõ phương thức bootstrap, các dependency bắt buộc và giới hạn được tài liệu của release mục tiêu công bố. Nếu không có yêu cầu kiến trúc đặc biệt, tạo CLI mới bằng Spring Boot thường đơn giản hơn.

## 2. Tạo project bằng Spring Initializr

Spring Initializr giúp tạo bộ khung project với cấu trúc thư mục, build file và class khởi chạy ban đầu.

Quy trình tổng quát:

1. Mở Spring Initializr tại `https://start.spring.io/` hoặc dùng chức năng tạo project tương ứng trong IDE.
2. Chọn Maven hoặc Gradle theo chuẩn của nhóm phát triển.
3. Chọn ngôn ngữ Java và phiên bản JDK phù hợp với bộ phiên bản mục tiêu.
4. Chọn phiên bản Spring Boot tương thích.
5. Đặt Group, Artifact, Name và Package theo quy ước của dự án.
6. Chọn dependency cần thiết. Nếu Spring Shell không xuất hiện trong danh sách dependency của Initializr, tạo project trước rồi thêm starter theo tài liệu Spring Shell.
7. Generate project, giải nén và mở thư mục gốc trong IDE.

Ví dụ thông tin định danh:

| Trường | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Group | `com.example` | Namespace tổ chức |
| Artifact | `project-cli` | Tên artifact build |
| Name | `project-cli` | Tên ứng dụng |
| Package | `com.example.projectcli` | Package gốc để component scanning |
| Packaging | `Jar` | Đóng gói ứng dụng Java có thể chạy |
| Language | `Java` | Ngôn ngữ triển khai |

Tên ở trên chỉ là ví dụ. Trong dự án thực tế, hãy dùng namespace và quy ước đặt tên của tổ chức.

Sau khi giải nén, cấu trúc ban đầu thường tương tự:

```text
project-cli/
├── mvnw
├── mvnw.cmd
├── pom.xml                 # hoặc build.gradle
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/projectcli/
    │   │       └── ProjectCliApplication.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
```

Giữ Maven Wrapper hoặc Gradle Wrapper trong repository để các thành viên và CI dùng cùng phiên bản build tool. Wrapper cũng giúp máy mới không phải cài Maven hoặc Gradle toàn cục trước khi build.

## 3. Thêm Spring Shell starter

Với ứng dụng Spring Boot, dependency starter là điểm tích hợp chính. Tên artifact thường dùng là `org.springframework.shell:spring-shell-starter`. Phiên bản cụ thể phải được chọn theo tài liệu của dòng Spring Shell và Spring Boot mục tiêu.

### 3.1. Khai báo với Maven

Trong `pom.xml`, giữ parent Spring Boot mà project đã chọn và thêm dependency Spring Shell. Ví dụ dưới đây dùng chỗ giữ chỗ cho phiên bản; thay chúng bằng các phiên bản đã xác minh tương thích trước khi build:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_COMPATIBLE_VERSION</version>
    <relativePath/>
</parent>

<properties>
    <java.version>JDK_VERSION</java.version>
    <spring-shell.version>SHELL_COMPATIBLE_VERSION</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
        <version>${spring-shell.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các giá trị `BOOT_COMPATIBLE_VERSION`, `JDK_VERSION` và `SHELL_COMPATIBLE_VERSION` là chỗ giữ chỗ để minh họa, không phải số phiên bản Maven hợp lệ. Hãy thay chúng bằng giá trị cụ thể trước khi chạy build. Nếu dự án quản lý phiên bản Spring Shell bằng BOM hoặc dependency management riêng theo tài liệu của release đang dùng, hãy tuân theo cấu hình đó thay vì khai báo version lặp lại ở từng dependency.

Nếu project dùng parent Spring Boot, plugin đóng gói Spring Boot thường đã được quản lý phiên bản. Có thể khai báo plugin trong phần `build` để thể hiện rõ cách tạo executable JAR:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

### 3.2. Khai báo với Gradle

Với Gradle, thêm starter vào `dependencies`. Phiên bản plugin Spring Boot cần tương thích với phiên bản nền tảng đã chọn:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_COMPATIBLE_VERSION'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(JDK_VERSION)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.shell:spring-shell-starter:SHELL_COMPATIBLE_VERSION'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các chuỗi `BOOT_COMPATIBLE_VERSION`, `DEPENDENCY_MANAGEMENT_PLUGIN_VERSION`, `JDK_VERSION` và `SHELL_COMPATIBLE_VERSION` cũng là chỗ giữ chỗ. Thay bằng phiên bản cụ thể theo ma trận tương thích và cấu hình plugin của dự án. Nếu dùng Gradle Kotlin DSL, cú pháp khai báo plugin và dependency sẽ là dạng Kotlin tương ứng.

Không thêm đồng thời nhiều phiên bản của cùng một thư viện Spring để “ép” build chạy qua. Khi dependency tree có xung đột, hãy xác định dependency nào kéo phiên bản không mong muốn và xử lý ở dependency management đúng tầng.

## 4. Tạo điểm khởi chạy Spring Boot

Một ứng dụng Spring Boot tối thiểu có class đánh dấu `@SpringBootApplication` và gọi `SpringApplication.run(...)`.

```java
package com.example.projectcli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProjectCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProjectCliApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp cấu hình, auto-configuration và component scanning. Đặt class này trong package gốc, phía trên các package chứa command, service và repository để Spring có thể phát hiện chúng theo phạm vi quét mặc định.

Ví dụ cấu trúc khi ứng dụng bắt đầu có thêm command và service:

```text
com.example.projectcli
├── ProjectCliApplication.java
├── command/
│   └── GreetingCommands.java
├── service/
│   └── GreetingService.java
└── domain/
    └── Greeting.java
```

Nếu đặt class khởi chạy trong package con quá sâu, các component ở package ngang hàng hoặc package cha có thể không được quét như mong muốn. Khi cần, có thể cấu hình rõ `scanBasePackages`, nhưng lựa chọn đầu tiên nên là đặt class khởi chạy ở package gốc hợp lý.

## 5. Đăng ký command đầu tiên để kiểm tra shell

Sau khi thêm starter và điểm khởi chạy, tạo một command đơn giản. Ví dụ sau minh họa phong cách annotation của các phiên bản Spring Shell hiện đại; hãy đối chiếu tên annotation và thuộc tính với phiên bản đang sử dụng.

```java
package com.example.projectcli.command;

import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.shell.command.annotation.ShellComponent;

@ShellComponent
public class GreetingCommands {

    @Command(command = "hello", description = "Hiển thị lời chào")
    public String hello(@Option(longNames = "name") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Khi ứng dụng khởi động, component scanning phát hiện `GreetingCommands`; Spring Shell đăng ký command từ metadata khai báo. Trong phiên shell tương tác, người dùng có thể nhập:

```text
hello --name Linh
```

Kết quả mong đợi:

```text
Xin chào, Linh!
```

Một số dòng Spring Shell cũ sử dụng package hoặc annotation khác, chẳng hạn `@ShellMethod` và `@ShellOption`. Không sao chép nguyên ví dụ từ tài liệu của một dòng phiên bản vào project thuộc dòng khác. Khi IDE không tìm thấy annotation hoặc ứng dụng không nhận command, hãy kiểm tra dependency và API của đúng release trước khi thay đổi mã nguồn.

Command này chỉ nhằm xác nhận ba điểm: ứng dụng Spring khởi động được, component được phát hiện và Spring Shell đăng ký được command. Sau đó mới nên mở rộng sang service nghiệp vụ, validation, prompt và output.

## 6. Cấu hình ứng dụng

Cấu hình không nhạy cảm và thay đổi theo môi trường có thể đặt trong `src/main/resources/application.yml` hoặc `application.properties`.

Ví dụ:

```yaml
spring:
  application:
    name: project-cli
```

Với CLI, các cấu hình tiếp theo có thể gồm endpoint của dịch vụ, timeout, profile, mức log hoặc đường dẫn dữ liệu. Nên tách giá trị theo môi trường khỏi mã nguồn và sử dụng biến môi trường hoặc cơ chế cấu hình phù hợp khi triển khai.

Không ghi password, access token, private key hoặc secret trực tiếp vào file được commit. Nếu ứng dụng cần xác thực với dịch vụ bên ngoài, hãy dùng secret manager hoặc cơ chế cung cấp secret được tổ chức chấp thuận.

Chỉ thêm cấu hình Spring Shell khi có yêu cầu cụ thể và tên property đã được xác nhận trong tài liệu của phiên bản mục tiêu. Property có thể thay đổi theo dòng phát hành; tránh sao chép một key cấu hình từ ví dụ cũ rồi kết luận framework không hoạt động khi key đó bị bỏ qua.

## 7. Build và chạy thử ứng dụng

Sau khi tạo project, kiểm tra lần lượt từ build đến khởi chạy.

Với Maven Wrapper:

```bash
# Linux hoặc macOS
./mvnw clean package

# Windows
mvnw.cmd clean package
```

Với Gradle Wrapper:

```bash
# Linux hoặc macOS
./gradlew clean build

# Windows
gradlew.bat clean build
```

Nếu build thành công, chạy executable JAR được tạo trong thư mục `target` (Maven) hoặc `build/libs` (Gradle):

```bash
java -jar target/project-cli-0.0.1-SNAPSHOT.jar
```

Tên file thực tế phụ thuộc vào `artifactId`, `version` và cấu hình build. Khi terminal tương tác được hỗ trợ và shell được bật theo cấu hình mặc định của phiên bản đang dùng, ứng dụng sẽ cung cấp prompt để nhập command. Thử lệnh `help` để xem command đã đăng ký và chạy `hello --name Linh` để kiểm tra command vừa tạo.

Nếu ứng dụng thoát ngay, không hiện prompt hoặc không nhận command, hãy xem log khởi động và kiểm tra cấu hình chế độ tương tác, terminal và cách chạy được tài liệu của phiên bản đó mô tả. Đừng vội kết luận rằng dependency không được nạp chỉ từ việc không thấy prompt; môi trường chạy trong IDE, CI hoặc terminal không tương tác có thể có hành vi khác nhau.

## 8. Xác minh project sau khi khởi tạo

Một project mới chỉ nên được xem là sẵn sàng khi các điểm cơ bản sau đã được kiểm tra:

| Kiểm tra | Dấu hiệu đạt |
|---|---|
| JDK và build tool | Wrapper chạy bằng JDK đúng phiên bản |
| Dependency | Resolve thành công, không có xung đột phiên bản không mong muốn |
| ApplicationContext | Ứng dụng khởi động mà không có lỗi tạo bean |
| Component scanning | Spring phát hiện component command |
| Command registration | Help liệt kê command đã khai báo |
| Thực thi command | Command trả kết quả đúng với đầu vào thử |
| Đóng gói | Tạo được artifact có thể chạy |
| Cấu hình | Giá trị môi trường được nạp từ nguồn dự kiến, không chứa secret trong mã nguồn |

Nếu muốn tự động hóa kiểm tra, có thể bổ sung test khởi tạo application context và test cho command theo API test mà phiên bản Spring Shell đang dùng hỗ trợ. Ở bước khởi tạo ban đầu, ít nhất phải có một lần build và chạy thử trên đúng JDK mục tiêu.

## 9. Các lỗi khởi tạo thường gặp

**Chọn Spring Shell mà không kiểm tra Spring Boot tương thích.** Dependency có thể resolve nhưng lỗi khi chạy do API hoặc phiên bản Spring không tương thích. Hãy xác nhận ma trận tương thích trước và giữ bộ dependency đồng nhất.

**Ghi đè phiên bản Spring Framework do Spring Boot quản lý.** Việc nâng riêng một module Spring có thể tạo ra bộ thư viện không đồng bộ. Chỉ override khi có yêu cầu rõ ràng và đã kiểm tra toàn bộ dependency tree.

**Thêm nhầm artifact hoặc thiếu starter.** Một thư viện lõi không nhất thiết cung cấp đầy đủ auto-configuration của starter. Đối chiếu dependency với hướng dẫn cài đặt của phiên bản Spring Shell đang dùng.

**Đặt class khởi chạy sai package.** Component command không được phát hiện nếu nằm ngoài phạm vi scanning. Đặt class `@SpringBootApplication` ở package gốc hoặc cấu hình phạm vi quét rõ ràng.

**Dùng annotation của phiên bản khác.** IDE báo không tìm thấy `@Command` hoặc `@ShellComponent` có thể do import hoặc API không khớp với dependency. Kiểm tra package và ví dụ đúng release trước khi sửa cấu hình build.

**Chạy bằng JDK khác với JDK build.** IDE có thể dùng một JDK trong khi terminal hoặc CI dùng JDK khác. Kiểm tra `JAVA_HOME`, toolchain và cấu hình project SDK.

**Nhầm lẫn giữa chạy ứng dụng và có prompt tương tác.** Một tiến trình khởi động thành công chưa chắc đang chạy ở chế độ terminal tương tác. Kiểm tra cách khởi chạy và các điều kiện terminal mà runtime yêu cầu.

**Đưa secret vào file cấu hình được commit.** Cấu hình local thuận tiện nhưng có thể làm lộ thông tin xác thực. Tách secret khỏi repository ngay từ khi thiết kế cấu hình.

## 10. Trình tự khởi tạo đề xuất

Có thể thực hiện theo trình tự ngắn gọn sau:

1. Chọn JDK và dòng Spring Boot phù hợp với môi trường triển khai.
2. Đối chiếu release Spring Shell tương thích với bộ nền tảng đó.
3. Tạo project Maven hoặc Gradle bằng Spring Initializr hoặc IDE.
4. Thêm `spring-shell-starter` đúng phiên bản.
5. Đặt class `@SpringBootApplication` tại package gốc.
6. Tạo một command kiểm tra để xác nhận component scanning và command registration.
7. Build, chạy ứng dụng và thử command trong terminal.
8. Xác nhận cấu hình, artifact và JDK giống môi trường dự kiến.

Sau khi hoàn thành các bước này, ứng dụng đã có nền tảng để phát triển CLI. Các chức năng như tổ chức nhóm command, validation, prompt, completion, xử lý lỗi, mã thoát và định dạng output nên được bổ sung theo từng nhu cầu nghiệp vụ, đồng thời giữ nguyên nguyên tắc chọn API theo đúng phiên bản Spring Shell mục tiêu.

