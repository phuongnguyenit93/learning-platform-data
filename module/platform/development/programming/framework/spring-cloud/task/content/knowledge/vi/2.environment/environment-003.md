# Quản lý phụ thuộc bằng Spring Cloud BOM với Maven hoặc Gradle

## 1. Mục tiêu và bối cảnh

Một ứng dụng **Spring Cloud Task** là tiến trình Spring Boot chạy trong thời gian hữu hạn: khởi động, thực hiện công việc và kết thúc. Spring Cloud Task cung cấp hạ tầng như `TaskRepository` để ghi nhận lần chạy (`TaskExecution`), thời điểm bắt đầu/kết thúc và trạng thái thực thi. Khi ứng dụng còn dùng Spring Batch, Spring JDBC và trình điều khiển cơ sở dữ liệu, các thư viện phải có phiên bản phù hợp với nhau.

Sau bài này, bạn có thể:

- Giải thích BOM (Bill of Materials), release train và khác biệt giữa *quản lý phiên bản* với *thêm thư viện*.
- Chọn cặp Spring Boot – Spring Cloud tương thích trước khi tạo dự án Task.
- Import `spring-cloud-dependencies` trong Maven hoặc Gradle và khai báo `spring-cloud-starter-task` không ghi phiên bản riêng.
- Kiểm tra phiên bản thực tế được phân giải, chẩn đoán xung đột và thực hiện nâng cấp có kiểm soát.

Đây là bài thuộc chương **Môi trường**, tập trung vào cách dựng hệ thống phụ thuộc cho Spring Cloud Task. Cấu hình `TaskRepository`, tham số, xử lý lỗi, lịch chạy và phối hợp Spring Batch sẽ dùng nền tảng phụ thuộc này ở các bước tiếp theo.

## 2. BOM quản lý điều gì?

**BOM** là tệp POM mô tả các phiên bản phụ thuộc đã được phối hợp trong một hệ sinh thái. `org.springframework.cloud:spring-cloud-dependencies` là BOM theo **Spring Cloud release train**; `org.springframework.boot:spring-boot-dependencies` quản lý các thành phần Spring Boot và nhiều thư viện liên quan.

Ví dụ, khi BOM thích hợp đã được import, ta có thể khai báo:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-task</artifactId>
</dependency>
```

Không có thẻ `<version>` ở đây: công cụ build sẽ tra phiên bản được quản lý. Điều đó **không** có nghĩa BOM tự động đưa Spring Cloud Task vào ứng dụng. Phải khai báo `spring-cloud-starter-task` trong `dependencies`.

| Thành phần | Vai trò | Có tự thêm mã thư viện vào ứng dụng? |
| --- | --- | --- |
| Spring Boot parent/BOM | Quản lý phiên bản Spring Boot và hệ thư viện liên quan | Không |
| Spring Cloud release train BOM | Quản lý phiên bản các dự án Spring Cloud tương ứng | Không |
| `spring-cloud-starter-task` | Kéo những thư viện cần để bật hạ tầng Spring Cloud Task | Có |
| `com.h2database:h2` | Cung cấp cơ sở dữ liệu nhúng để thử nghiệm | Có |
| Maven/Gradle plugin | Biên dịch, kiểm thử, đóng gói và chạy ứng dụng | Không phải BOM |

Luồng xử lý phụ thuộc:

```text
Spring Boot parent/BOM ──> phiên bản thư viện Spring Boot
Spring Cloud BOM ────────> phiên bản thư viện Spring Cloud
                               │
dependencies {                 │
  spring-cloud-starter-task  } ─┘
          │
          └─> Spring Cloud Task, các thư viện chuyển tiếp phù hợp
```

Lợi ích quan trọng nhất là khi nâng cấp một release train, các thành phần Spring Cloud do BOM quản lý được cập nhật theo một bộ nhất quán, thay vì phải đoán và gắn phiên bản thủ công cho từng `starter`.

### Chọn phiên bản Spring Boot và Spring Cloud tương thích

Spring Cloud không có cùng số phiên bản với Spring Boot. Trước hết chọn thế hệ Spring Boot theo yêu cầu dự án, sau đó tra **bảng tương thích release train** chính thức tại [spring.io/projects/spring-cloud](https://spring.io/projects/spring-cloud/).

Một số cặp minh họa:

| Spring Boot | Spring Cloud release train | Ghi chú |
| --- | --- | --- |
| `4.1.x` | `2025.1.2+` (Oakwood) | Có hỗ trợ theo bảng tương thích chính thức |
| `4.0.x` | `2025.1.x` (Oakwood) | Chọn bản vá tương thích trong nhánh |
| `3.5.x` | `2025.0.x` (Northfields) | Nhánh cũ; kiểm tra tình trạng hỗ trợ trước khi dùng cho dự án mới |

**Bộ phiên bản dùng trong ví dụ của bài:** Spring Boot **4.1.0**, Spring Cloud **2025.1.5**, Java **17+**. Cặp này thuộc các nhánh tương thích đã công bố tại thời điểm soạn bài (24/11/2026); đây là bộ phiên bản minh họa có thể thay thế khi có bản vá thích hợp. Không sao chép số phiên bản vào sản phẩm mới mà bỏ qua kiểm tra phiên bản hỗ trợ và cảnh báo bảo mật.

## 3. Cấu hình Maven: Spring Boot parent và Spring Cloud BOM

Trong `pom.xml`, Spring Boot parent cung cấp quản lý phiên bản Spring Boot và cấu hình build thông dụng. Import thêm Spring Cloud BOM tại `dependencyManagement`; sau đó thêm starter ở `dependencies`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>daily-report-task</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.5</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-task</artifactId>
        </dependency>
        <!-- H2 dùng để học và thử nghiệm tại máy cục bộ. -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
</project>
```

Đọc cấu hình theo đúng thứ tự:

1. `spring-boot-starter-parent` chốt phiên bản và cấu hình chung của Spring Boot.
2. Thuộc tính `spring-cloud.version` đặt phiên bản release train tại một chỗ.
3. `dependencyManagement` dùng `type=pom` và `scope=import` để nhập BOM; **không** đặt BOM như một `dependency` runtime thông thường.
4. `dependencies` thực sự bổ sung `spring-cloud-starter-task` và H2 vào ứng dụng, không khai báo `version` khi đã được BOM thích hợp quản lý.

Nếu dự án không thể dùng Spring Boot parent vì đã có parent POM nội bộ, bạn có thể import **cả** `spring-boot-dependencies` và `spring-cloud-dependencies` trong `dependencyManagement`, đồng thời cấu hình riêng các plugin cần thiết. BOM Spring Boot chỉ quản lý phiên bản thư viện; nó không tự mang sang toàn bộ cấu hình plugin của `spring-boot-starter-parent`.

## 4. Cấu hình Gradle

Gradle có hai cách phổ biến: dùng plugin `io.spring.dependency-management` hoặc cơ chế BOM gốc `platform(...)`. Chọn một chiến lược quản lý phiên bản rõ ràng cho mỗi dự án.

### Cách A: plugin `io.spring.dependency-management`

Ví dụ `build.gradle` theo **Groovy DSL**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
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

ext {
    set('springCloudVersion', '2025.1.5')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    runtimeOnly 'com.h2database:h2'
}
```

Khi áp dụng `io.spring.dependency-management` cùng Spring Boot plugin, Spring Boot BOM được import theo cách tích hợp của các plugin này. Khối `dependencyManagement.imports` bổ sung Spring Cloud BOM. Bạn vẫn cần khai báo starter trong `dependencies`.

### Cách B: Gradle `platform(...)` gốc

Nếu ưu tiên quản lý phụ thuộc bằng tính năng sẵn có của Gradle, có thể bỏ plugin `io.spring.dependency-management` và import rõ ràng **hai** BOM:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.0')
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.5')

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    runtimeOnly 'com.h2database:h2'
}
```

Ở cách này, `platform(...)` đưa các ràng buộc phiên bản từ BOM vào quá trình phân giải của Gradle. Cần giữ phiên bản Spring Boot BOM đồng bộ với phiên bản Spring Boot plugin và tự quản lý Java toolchain/các cấu hình build khác nếu dự án cần. Đừng mặc định việc áp dụng `org.springframework.boot` plugin **một mình** sẽ tự import Spring Boot BOM khi không dùng plugin dependency management.

Với **Kotlin DSL**, cách khai báo BOM gốc tương đương là:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.0"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:2025.1.5"))
    implementation("org.springframework.cloud:spring-cloud-starter-task")
    runtimeOnly("com.h2database:h2")
}
```

Đây là phần `dependencies` của `build.gradle.kts`, không phải tệp build hoàn chỉnh; phần `plugins`, `repositories` và Java toolchain vẫn cần được khai báo như dự án tương ứng.

## 5. Kiểm tra BOM đã hoạt động

Không nên chỉ quan sát việc IDE hết báo đỏ. Hãy xem *effective dependency graph* mà công cụ build phân giải, vì một thư viện chuyển tiếp hoặc khai báo phiên bản thủ công có thể ảnh hưởng kết quả cuối cùng.

**Maven** (tại thư mục gốc dự án, đã có Maven Wrapper):

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework.cloud
./mvnw test
```

- `help:effective-pom` hiển thị cấu hình POM hiệu lực sau kế thừa và import.
- `dependency:tree` cho biết các module Spring Cloud thực sự xuất hiện và phiên bản được chọn.
- `test` xác nhận phụ thuộc đủ để dự án biên dịch và kiểm thử; một build thành công chưa chứng minh cấu hình cơ sở dữ liệu production chính xác.

**Gradle** (tại thư mục gốc dự án, đã có Gradle Wrapper):

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-task-core --configuration runtimeClasspath
./gradlew test
```

`dependencyInsight` giúp xác định vì sao một phiên bản được chọn (BOM, phụ thuộc trực tiếp hoặc phiên bản yêu cầu bởi thư viện khác). Trên Windows, chạy các wrapper tương ứng bằng `mvnw.cmd` và `gradlew.bat`.

### Phân biệt thành công của build và thành công của Task

Khai báo BOM đúng giúp **phân giải thư viện đúng**, không tự động xác nhận Task đã chạy thành công. Khi thêm `spring-cloud-starter-task`, Spring Cloud Task tự cấu hình các bean hạ tầng, gồm `TaskRepository` trong điều kiện phù hợp. Ví dụ với H2 nhúng chỉ phù hợp để học: dữ liệu thực thi có thể mất khi tiến trình thoát. Để theo dõi lịch sử chạy lâu dài, dùng cơ sở dữ liệu quan hệ được hỗ trợ, cấu hình datasource và kiểm soát schema theo môi trường triển khai.

Ví dụ `ApplicationRunner` đơn giản để thấy mục đích của một tiến trình hữu hạn:

```java
package com.example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner generateReport() {
        return arguments -> System.out.println("Đã tổng hợp báo cáo trong ngày.");
    }
}
```

Khi bắt đầu thực hiện logic trong runner, Spring Cloud Task theo dõi vòng đời tác vụ qua hạ tầng của nó. Phần code này minh họa phạm vi ứng dụng của starter; trọng tâm của bài vẫn là quản lý đúng phiên bản trước khi chạy.

## 6. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
| --- | --- | --- |
| Maven báo thiếu `version` của `spring-cloud-starter-task` | Chưa import Cloud BOM hoặc đặt sai vị trí `dependencyManagement` | Kiểm tra `groupId`, `artifactId`, `type=pom`, `scope=import` và phiên bản BOM |
| Gradle báo `Could not find ...` hoặc không xác định được phiên bản | Không import BOM vào cấu hình phù hợp; thiếu repository | Kiểm tra `mavenCentral()` và `dependencyManagement` hoặc `platform(...)` |
| Ứng dụng báo lỗi tương thích khi khởi động | Kết hợp Spring Boot và Spring Cloud khác thế hệ | Đối chiếu bảng tương thích trên spring.io, sửa đồng bộ hai phiên bản |
| Có `NoSuchMethodError` / `ClassNotFoundException` | Có thể có xung đột phụ thuộc chuyển tiếp hoặc override phiên bản | Chạy `dependency:tree` / `dependencyInsight`; bỏ override không cần thiết, kiểm tra thư viện bên thứ ba |
| Đã import BOM nhưng không có `TaskRepository` | BOM không tự thêm starter, hoặc auto-configuration chưa được kích hoạt phù hợp | Xác nhận `spring-cloud-starter-task` có trong runtime classpath, kiểm tra log cấu hình |
| Task chạy xong nhưng lần sau không còn dữ liệu lịch sử | Dùng H2 in-memory; dữ liệu sống cùng tiến trình | Chuyển sang database bền vững và cấu hình schema/datasource cho môi trường thật |

**Lưu ý về ưu tiên phiên bản:** Một `<version>` khai báo trực tiếp trong Maven hay chuỗi phiên bản ghi ngay trên dependency Gradle có thể làm kết quả phân giải lệch khỏi bộ phiên bản mong muốn. Trong Gradle, các constraint và quy tắc giải quyết xung đột cũng ảnh hưởng phiên bản cuối. Hãy đọc dependency graph thay vì suy luận rằng BOM luôn thắng mọi khai báo khác.

### Khi cần thêm Spring Batch

Spring Cloud Task ghi nhận *lần thực thi tiến trình/tác vụ*; Spring Batch quản lý *Job*, *Step*, checkpoint và cơ chế đọc/ghi theo lô. Nếu ứng dụng sử dụng cả hai, thêm starter Batch phù hợp, ví dụ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-batch</artifactId>
</dependency>
```

Phiên bản starter Batch do Spring Boot BOM/parent quản lý. Vẫn cần thiết kế `JobRepository`, `TaskRepository` và database phù hợp; BOM không thay thế phần cấu hình hoặc orchestration. Đặc biệt tránh thêm một phiên bản `spring-batch-core` riêng khi chưa có lý do và kiểm thử tương thích.

## 7. Quy trình nâng cấp và bài tập thực hành

Giả sử ứng dụng báo cáo được chạy theo lịch mỗi đêm và lưu trạng thái vào PostgreSQL. Nhóm chuẩn bị nâng cấp vì một thư viện Spring Cloud có bản sửa lỗi.

1. **Xác định phiên bản hiện hữu.** Ghi nhận Spring Boot, Spring Cloud BOM, JDK, phiên bản plugin và dependency graph trước khi chỉnh sửa.
2. **Chọn cặp tương thích.** Tra bảng release train; chốt phiên bản vá thích hợp, không tăng riêng từng `spring-cloud-*` nếu chúng đã được BOM quản lý.
3. **Thay đổi tại một nguồn.** Với Maven, điều chỉnh `<spring-cloud.version>` và Spring Boot parent nếu cần. Với Gradle, sửa phiên bản BOM/Boot plugin đồng bộ theo chiến lược đang dùng.
4. **Kiểm tra build và quá trình chạy.** Xem lại dependency graph, chạy kiểm thử, rồi chạy một Task trong môi trường thử nghiệm có database phù hợp.
5. **Kiểm tra metadata thực thi.** Xác minh Task bắt đầu, kết thúc, mã thoát và các bảng theo dõi; nếu phối hợp Spring Batch, kiểm tra cả Job/Step và cách khởi chạy.
6. **Triển khai có thể quay lại.** Chốt phiên bản trong VCS, ghi nhận thay đổi schema, giữ cơ chế rollback và theo dõi các lần chạy đầu sau nâng cấp.

**Bài tự luyện:** Tạo một dự án Maven hoặc Gradle theo ví dụ trên, thêm `spring-cloud-starter-task` và H2, sau đó trả lời:

- Tại sao khai báo BOM trong `dependencyManagement` hoặc `platform(...)` chưa đủ để có `TaskRepository`?
- Công cụ build đã chọn phiên bản nào cho `spring-cloud-task-core` và nó đến từ ràng buộc nào?
- Nếu xóa Cloud BOM nhưng giữ starter không có phiên bản, build của bạn phản hồi thế nào? Khôi phục cấu hình sau thử nghiệm.
- Khi chuyển từ H2 nhúng sang PostgreSQL, phần nào là *thay đổi phụ thuộc* và phần nào là *cấu hình vận hành*?

**Tiêu chí hoàn thành:** Dự án phân giải được starter Task không chỉ định phiên bản riêng; dependency graph cho thấy bộ phiên bản do BOM quản lý; Task thử nghiệm chạy kết thúc; và bạn giải thích được vì sao dữ liệu H2 in-memory không thích hợp để lưu lịch sử chạy lâu dài.

## Tài liệu tham khảo chính thức

- [Spring Cloud — release train, bảng tương thích và cách import BOM](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.5 — thông báo phát hành và tương thích Spring Boot](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Cloud Task — Getting Started](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Gradle — Platforms và BOM](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
