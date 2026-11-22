# Lựa chọn phiên bản tương thích của Java, Spring Boot và Spring Data REST

## Mục tiêu

Sau bài học, bạn có thể:

- Chọn JDK đáp ứng cả môi trường build và môi trường chạy.
- Chọn phiên bản Spring Boot phù hợp với JDK, build tool và các thư viện của dự án.
- Phân biệt phiên bản Spring Boot starter với phiên bản các module Spring Data REST.
- Dùng Spring Boot BOM để đồng bộ dependency.
- Dùng Spring Data Release Train BOM khi quản lý Spring Data độc lập.
- Kiểm tra dependency thực tế được Maven hoặc Gradle resolve.

## 1. Vì sao cần chọn phiên bản tương thích?

Spring Data REST không hoạt động độc lập. Một ứng dụng thường có các lớp phụ thuộc sau:

1. **Java JDK** cung cấp compiler, runtime và các API nền tảng.
2. **Spring Boot** cung cấp cách khởi tạo ứng dụng, auto-configuration, starter và bộ phiên bản dependency đã được tuyển chọn.
3. **Spring Framework** cung cấp IoC, dependency injection, Spring MVC và các API nền tảng mà ứng dụng Spring sử dụng.
4. **Spring Data** cung cấp repository abstraction và các module tích hợp với từng loại hệ quản trị dữ liệu.
5. **Spring Data REST** xuất bản Spring Data repository thành tài nguyên HTTP, thường thông qua Spring MVC và biểu diễn HAL.

Các lớp này có ràng buộc tương thích. Một phiên bản Spring Data REST mới có thể cần API của Spring Framework mới hơn; phiên bản Framework đó lại có thể yêu cầu một JDK tối thiểu. Nếu tự chọn từng thư viện mà không kiểm tra quan hệ giữa chúng, ứng dụng có thể không biên dịch, không khởi động hoặc lỗi khi chạy.

Có thể hình dung chuỗi phụ thuộc như sau:

```text
JDK
 │
 ▼
Spring Boot
 │  BOM quản lý các phiên bản tương thích
 ├── Spring Framework
 ├── Spring Data Commons
 ├── Spring Data REST
 └── các thư viện tích hợp khác
      │
      ▼
Spring Data Repository được xuất bản thành HTTP resources
```

Điều cần nhớ: **các thành phần không nhất thiết có cùng số phiên bản**. Spring Boot có hệ phiên bản riêng; các module Spring Data cũng có phiên bản riêng. Hãy chọn một nhánh Spring Boot phù hợp, sau đó để BOM quản lý các dependency thuộc hệ sinh thái đó.

## 2. Hiểu đúng các loại phiên bản

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Java | 17, 21, 25 | Phiên bản JDK dùng để build và chạy |
| Spring Boot | 4.1.2 | Phiên bản nền tảng ứng dụng |
| Spring Framework | 7.0.10 | Nền tảng Spring mà nhánh Boot tương ứng yêu cầu |
| Spring Boot Data REST starter | 4.1.2 | Starter tích hợp Spring Data REST vào ứng dụng Boot |
| Spring Data REST WebMVC | 5.1.2 | Module Spring Data REST chạy trên Spring MVC, theo BOM của Boot 4.1.2 |
| Spring Data release train | 2026.0.1 | Phiên bản BOM đồng bộ các module Spring Data khi quản lý độc lập |

Ví dụ, Spring Boot 4.1.2 quản lý spring-boot-starter-data-rest ở phiên bản 4.1.2 và spring-data-rest-webmvc ở phiên bản 5.1.2. Hai con số khác nhau là bình thường: chúng thuộc hai hệ phát hành khác nhau.

Spring Data dùng release train để phối hợp các module được phát triển và phát hành theo lịch riêng. Không nên suy luận rằng Spring Data REST phải có cùng số phiên bản với Spring Data JPA, Spring Data Commons hoặc Spring Boot.

## 3. Kiểm tra ràng buộc Java trước khi chọn Boot

Hãy xác định JDK mà ứng dụng cần hỗ trợ trước khi chọn phiên bản framework.

### 3.1. JDK chạy ứng dụng

Đây là JDK có trên máy chủ, container hoặc nền tảng triển khai. Ứng dụng phải chạy được trên phiên bản này.

Ví dụ, production chỉ có Java 17 thì không thể triển khai bytecode yêu cầu Java 21. JDK mới trên máy lập trình viên không làm thay đổi giới hạn của production.

### 3.2. JDK chạy build tool

Maven hoặc Gradle có thể chạy bằng một JDK khác với JDK mà bạn dự định dùng cho ứng dụng. Kiểm tra cả Java trên PATH và JDK mà build tool đang sử dụng:

```bash
java -version
./mvnw -version
./gradlew --version
```

Trên Windows, dùng mvnw.cmd -version và gradlew.bat --version.

### 3.3. JDK biên dịch và Java toolchain

Build bằng JDK mới không bắt buộc ứng dụng phải tạo bytecode cho chính phiên bản JDK đó. Có thể dùng Java toolchain hoặc compiler release để đặt mức Java mục tiêu, miễn là phiên bản framework và thư viện hỗ trợ mức đó.

Cần phân biệt:

- **Build JDK**: JDK thực sự chạy Maven hoặc Gradle.
- **Compile release/toolchain**: mức Java mà mã nguồn được biên dịch cho.
- **Runtime JDK**: JDK cài ở môi trường chạy ứng dụng.

Ba giá trị này cần được cấu hình có chủ đích. Nếu CI build bằng Java mới nhưng production chạy Java cũ, hãy kiểm tra bytecode target và các dependency trước khi phát hành.

Ngoài Java, cần kiểm tra Maven/Gradle Wrapper, IDE, plugin build, driver cơ sở dữ liệu, Spring Cloud, thư viện bảo mật và các thư viện bên thứ ba. Một phiên bản Spring Boot hỗ trợ JDK mới không có nghĩa mọi dependency bên ngoài đều đã hỗ trợ JDK đó.

## 4. Chọn Spring Boot trước

Với ứng dụng Spring Boot, nên chọn một bản GA ổn định trong nhánh đáp ứng yêu cầu của dự án. Sau đó dùng dependency management của Boot để quản lý Spring Framework, Spring Data và các thư viện liên quan.

Trình tự chọn phiên bản:

1. Xác nhận JDK có thể sử dụng ở CI và production.
2. Đọc **System Requirements** của nhánh Spring Boot dự định chọn.
3. Kiểm tra Maven hoặc Gradle Wrapper có nằm trong dải được hỗ trợ.
4. Kiểm tra thư viện bên thứ ba quan trọng có tương thích không.
5. Chọn bản vá stable phù hợp trong nhánh đã quyết định.
6. Cố định phiên bản Boot trong parent, plugin hoặc BOM của dự án.

### Ví dụ theo tài liệu tại ngày 11/11/2026

Tài liệu Spring Boot hiện liệt kê Spring Boot **4.1.2** là bản stable. System Requirements của bản này nêu:

- Java tối thiểu: **17**.
- Java tối đa tương thích được công bố: **27**.
- Spring Framework tối thiểu: **7.0.10**.
- Maven: **3.6.3 trở lên**.
- Gradle: **8.14 trở lên trong nhánh 8.x**, hoặc nhánh **9.x**.

Java 21 và Java 25 nằm trong dải Java được công bố cho Spring Boot 4.1.2. Dự án vẫn cần kiểm tra các plugin build và thư viện bên thứ ba trước khi nâng JDK.

Đây là ví dụ theo tài liệu tại ngày biên soạn, không phải bảng tương thích cố định. Trước khi bắt đầu dự án hoặc nâng cấp, hãy mở lại trang System Requirements của đúng phiên bản Spring Boot để xác nhận giới hạn hiện hành.

## 5. Dùng Spring Boot BOM để quản lý Spring Data REST

BOM (Bill of Materials) là một POM khai báo các phiên bản dependency được quản lý cùng nhau. Spring Boot cung cấp BOM spring-boot-dependencies; Spring Boot parent và Gradle plugin giúp dự án sử dụng bộ phiên bản này.

Khi dùng Spring Boot dependency management:

- Khai báo spring-boot-starter-data-rest mà không ghi phiên bản.
- Không tự đặt phiên bản cho spring-data-rest-webmvc.
- Không tự đặt phiên bản cho spring-data-commons hoặc các module Spring Data liên quan.
- Không nâng riêng một module lên bản mới nhất nếu chưa kiểm tra tương thích toàn bộ dependency graph.

Boot BOM đã chọn các phiên bản để các thành phần hoạt động cùng nhau. Khi nâng Spring Boot, các phiên bản được quản lý cũng được cập nhật theo BOM mới.

### 5.1. Maven dùng Spring Boot parent

Ví dụ một ứng dụng dùng Java 21 và Spring Boot 4.1.2:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
    </dependencies>
</project>
```

Giải thích:

- spring-boot-starter-parent cố định Spring Boot ở 4.1.2 và cung cấp dependency management mặc định.
- java.version đặt mức Java mục tiêu cho cấu hình Maven do parent cung cấp.
- spring-boot-starter-data-rest không có thẻ version; Maven lấy phiên bản được quản lý từ Boot.
- Boot 4.1.2 quản lý starter Data REST ở 4.1.2 và module spring-data-rest-webmvc ở 5.1.2.

Starter cung cấp tích hợp Spring Data REST. Nó không tự tạo entity, repository, schema hay cấu hình kết nối cơ sở dữ liệu. Nếu ứng dụng dùng JPA, cần khai báo thêm starter JPA và driver phù hợp; các dependency do Boot quản lý cũng nên được khai báo mà không gắn phiên bản riêng.

### 5.2. Maven không dùng Spring Boot parent

Nếu dự án cần kế thừa một parent POM khác, có thể import BOM trực tiếp trong dependencyManagement:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau khi import BOM, các dependency được Boot quản lý có thể khai báo mà không cần version. Lưu ý rằng import BOM không tự áp dụng toàn bộ cấu hình plugin Maven như spring-boot-starter-parent; nếu cần các cấu hình plugin đó, hãy khai báo riêng hoặc dùng parent phù hợp.

### 5.3. Gradle

Với Gradle, Spring Boot plugin có thể tự động cấu hình dependency management và import Boot BOM. Ví dụ:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
}
```

Không cần gắn phiên bản cho starter vì Boot plugin quản lý phiên bản thông qua BOM. Nếu dự án không dùng Spring Boot Gradle plugin, có thể import BOM bằng Gradle native platform:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
}
```

Hãy chọn một cơ chế quản lý phiên bản rõ ràng và áp dụng nhất quán trong dự án.

## 6. Khi nào dùng Spring Data Release Train BOM?

Một ứng dụng Spring Framework thuần hoặc dự án tự quản lý Spring Data mà không dùng Spring Boot BOM cần phối hợp phiên bản các module Spring Data. Trong trường hợp này, dùng **Spring Data Release Train BOM**.

Tại thời điểm biên soạn, tài liệu Spring Data nêu release train hiện hành là **2026.0.1**. Ví dụ Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-rest-webmvc</artifactId>
    </dependency>
</dependencies>
```

Sau khi import BOM, không cần khai báo phiên bản riêng cho từng module Spring Data do BOM quản lý. Release train giúp đồng bộ các module có lịch phát hành khác nhau.

Tài liệu Spring Data hiện tại yêu cầu các module Spring Data dùng Spring Framework **7.0.9 trở lên**. Hãy đối chiếu điều kiện này với phiên bản Framework mà ứng dụng độc lập đang dùng.

### Dự án Spring Boot có cần import thêm Spring Data BOM không?

Thông thường không. Spring Boot đã chọn phiên bản các module Spring Data trong Boot BOM. Import thêm một BOM khác quản lý cùng dependency có thể làm phiên bản được chọn khác với tổ hợp Boot đã kiểm thử.

Nếu dự án Spring Boot thực sự cần nâng Spring Data lên một release train mới hơn, tài liệu Spring Data hướng dẫn dùng thuộc tính spring-data-bom.version của Spring Boot để chọn train và iteration mong muốn. Chỉ thực hiện sau khi kiểm tra tương thích với Spring Framework, Spring Boot và các module liên quan, rồi xác nhận dependency tree và chạy integration test.

## 7. Xác minh phiên bản Maven hoặc Gradle đã chọn

File build cho biết dependency trực tiếp được khai báo. Dependency tree cho biết phiên bản thực tế mà build tool resolve, bao gồm cả dependency bắc cầu.

### 7.1. Maven

Kiểm tra Java và Maven đang chạy:

```bash
java -version
./mvnw -version
```

Kiểm tra các module Spring Data được resolve:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.data:*
```

Kiểm tra POM sau khi áp dụng dependency management:

```bash
./mvnw help:effective-pom
```

Chạy toàn bộ build và test:

```bash
./mvnw clean verify
```

Nếu không dùng Maven Wrapper, thay ./mvnw bằng mvn. Trên Windows, dùng mvnw.cmd.

### 7.2. Gradle

Kiểm tra JDK và Gradle:

```bash
./gradlew --version
```

Xem dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Truy vết riêng Spring Data REST:

```bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
```

Chạy test:

```bash
./gradlew test
```

### 7.3. Những gì cần xác nhận

- Build tool đang chạy bằng JDK dự kiến.
- Java toolchain hoặc compiler release không vượt quá JDK runtime mục tiêu.
- spring-boot-starter-data-rest được quản lý theo phiên bản Spring Boot đã chọn.
- spring-data-rest-webmvc, Spring Data Commons và các module liên quan được resolve theo BOM dự kiến.
- Không có dependency bị ép về phiên bản cũ hoặc mới ngoài ý muốn.
- Không có nhiều phiên bản xung đột của cùng module trên runtime classpath.
- Build, unit test, integration test và việc khởi động ứng dụng đều thành công.
- Endpoint repository hoạt động đúng sau khi ứng dụng khởi động.

Nếu dependency tree cho thấy một thư viện bị ghi đè, hãy tìm dependency trực tiếp, dependency bắc cầu hoặc BOM đã đưa phiên bản đó vào. Sửa tại nguồn quản lý phiên bản rồi chạy lại dependency tree; không thêm một phiên bản ngẫu nhiên để che xung đột.

## 8. Các lỗi chọn phiên bản thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ rằng Spring Boot và Spring Data REST phải cùng số phiên bản | Chọn sai version hoặc hiểu sai bảng dependency | Phân biệt phiên bản starter Boot với phiên bản module Spring Data REST |
| Dùng module Spring Data REST mới nhất cùng Boot cũ | Có thể lệch Spring Framework hoặc Spring Data Commons | Để Boot BOM quản lý trong dự án Boot |
| Nâng riêng spring-data-commons hoặc spring-data-rest-webmvc | Có thể gặp lỗi linkage, NoSuchMethodError hoặc lỗi khởi động | Nâng theo BOM và kiểm tra toàn bộ dependency graph |
| Chỉ chạy java -version | Maven, Gradle hoặc CI có thể dùng JDK khác | Kiểm tra thêm mvnw -version hoặc gradlew --version |
| Build bằng JDK mới nhưng production chạy JDK cũ | Bytecode có thể không chạy trên production | Đặt toolchain/compiler release phù hợp runtime mục tiêu |
| Dùng snapshot, milestone hoặc release candidate cho production | API và dependency có thể còn thay đổi | Ưu tiên bản GA stable, trừ khi dự án chủ đích thử nghiệm |
| Import nhiều BOM quản lý cùng dependency | Phiên bản được chọn có thể khác kỳ vọng | Chọn một nguồn quản lý chính và kiểm tra dependency tree |
| Chỉ thêm starter Data REST nhưng chưa có repository | Không có repository endpoint để xuất bản | Tạo repository Spring Data và cấu hình persistence phù hợp |

Các lỗi như NoSuchMethodError, ClassNotFoundException hoặc lỗi khởi động có thể liên quan đến dependency không đồng bộ. Khi gặp lỗi, hãy kiểm tra phiên bản đã resolve và compatibility requirements trước khi thay đổi mã nghiệp vụ.

## 9. Quy trình chọn phiên bản cho dự án mới

Giả sử một dịch vụ mới có thể chạy Java 21 và dùng Maven:

1. Xác nhận CI và production đều cài được Java 21.
2. Chọn một bản Spring Boot stable có hỗ trợ Java 21.
3. Đọc System Requirements để xác nhận JDK và Maven Wrapper.
4. Cố định phiên bản Spring Boot trong parent hoặc BOM.
5. Thêm spring-boot-starter-data-rest mà không khai báo version.
6. Thêm starter lưu trữ dữ liệu phù hợp như JPA, JDBC hoặc MongoDB; để Boot quản lý version nếu dependency nằm trong BOM.
7. Chạy dependency:tree để xác nhận phiên bản Spring Data REST và các module liên quan.
8. Chạy clean verify, khởi động ứng dụng và kiểm tra endpoint thực tế.

Với dự án đang dùng Spring Boot 3.x, hãy giữ bộ Spring Data REST mà nhánh Boot hiện tại quản lý trong quá trình sửa lỗi thông thường. Nếu chuyển sang Boot 4.x, hãy xem đó là một đợt nâng cấp nền tảng: đọc migration guide, xác nhận JDK và build tool, rà soát dependency bên thứ ba, sau đó nâng cấp và chạy đầy đủ kiểm thử. Không nâng riêng Spring Data REST lên major mới trước khi nền tảng Boot sẵn sàng.

## 10. Tài liệu tham khảo chính thức

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): JDK, Maven, Gradle và yêu cầu runtime.
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): phiên bản dependency mà Boot BOM quản lý.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): cách dùng starter, Maven, Gradle và dependency management.
- [Spring Data REST — Dependencies](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): Spring Data Release Train BOM, quản lý phiên bản với Boot và yêu cầu Spring Framework.
- [Spring Initializr](https://start.spring.io): tạo cấu hình dự án theo JDK, Spring Boot và build tool.

Các phiên bản và giới hạn có thể thay đổi. Trước mỗi lần tạo dự án hoặc nâng cấp, hãy kiểm tra lại System Requirements và Managed Dependency Coordinates của đúng phiên bản Spring Boot mà dự án sẽ sử dụng.
