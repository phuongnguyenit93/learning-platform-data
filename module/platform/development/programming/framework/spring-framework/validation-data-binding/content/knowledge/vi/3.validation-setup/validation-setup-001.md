# Xác định phiên bản Spring, Java và Jakarta Validation tương thích

Khi xây dựng chức năng **validation** và **data binding** trong Spring, cần chọn cả một **bộ phiên bản tương thích**, thay vì chỉ tìm một phiên bản mới của thư viện `jakarta.validation-api`. Một ứng dụng có thể biên dịch được nhưng vẫn không chạy đúng nếu Spring Framework, Java, API Jakarta Validation và bản triển khai validation thực tế lệch thế hệ.

Bài này hướng dẫn nhận biết các lớp phiên bản, chọn cấu hình phù hợp cho dự án mới hoặc đang bảo trì, kiểm tra dependency thực tế và xử lý lỗi thường gặp. Các phiên bản minh họa được đối chiếu với tài liệu phát hành chính thức **tại ngày 02/11/2026**; với dự án sử dụng bản phát hành sau ngày đó, hãy đối chiếu lại tài liệu tương ứng.

## 1. Cần kiểm tra những thành phần nào?

| Thành phần | Vai trò trong ứng dụng | Điều phải kiểm tra |
| --- | --- | --- |
| **Java / JDK** | Biên dịch và chạy ứng dụng | Phiên bản tối thiểu, JDK dùng để build, mức bytecode được tạo ra và JDK dùng để chạy |
| **Spring Framework** | IoC, data binding, Spring MVC, hỗ trợ Bean Validation | Major/minor tương thích với Jakarta API và hệ sinh thái của phiên bản Spring |
| **Spring Boot** (nếu dùng) | Tự cấu hình và quản lý bộ dependency thông qua BOM | Dòng Boot đã chọn quản lý Spring Framework và Hibernate Validator nào |
| **Jakarta Validation API** | Định nghĩa `@Valid`, `@NotNull`, `@Size`, `Validator`, `ConstraintViolation`… | Đúng thế hệ API và namespace `jakarta.validation.*` hoặc `javax.validation.*` |
| **Validation provider** | Thực thi kiểm tra constraint lúc chạy | Hibernate Validator (hoặc provider khác) triển khai đúng phiên bản Jakarta Validation API |
| **Build tool / môi trường triển khai** | Maven, Gradle, máy CI, server/container | Có hỗ trợ Spring Boot và JDK đã chọn; không tạo khác biệt giữa môi trường build và run |

**Điểm cốt lõi:** API chỉ là hợp đồng. Ví dụ `jakarta.validation-api` chứa định nghĩa `@NotBlank` nhưng bản thân nó không cung cấp bộ máy thực thi tất cả constraint. Một provider như **Hibernate Validator** mới đảm nhiệm công việc đó.

### Spring Framework và Spring Boot khác nhau như thế nào?

**Spring Framework** là nền tảng cung cấp các tính năng như `DataBinder`, `ConversionService`, `org.springframework.validation.Validator` và tích hợp với Jakarta Validation. **Spring Boot** sử dụng Spring Framework và định nghĩa bộ thư viện đã được kiểm thử chung. Vì thế, nếu dự án dùng Boot, nên **chọn bản Boot trước**, rồi để BOM/parent của Boot quản lý Spring Framework, Jakarta Validation API và Hibernate Validator.

Không nên tự nâng riêng `spring-core` lên một major mới hoặc tự ép một phiên bản Hibernate Validator vượt khác thế hệ chỉ vì thấy số phiên bản cao hơn.

## 2. Bảng đối chiếu các thế hệ

Các cột “API” và “provider” dưới đây thể hiện bộ mà Spring Boot **quản lý**, không khẳng định mọi bản phát hành của các thư viện ấy đều có thể hoán đổi tự do.

| Bộ phiên bản tham khảo | Java | Spring Framework | Jakarta Validation API | Provider mặc định qua starter | Namespace |
| --- | --- | --- | --- | --- | --- |
| **Spring Boot 4.1.2** (ổn định tại ngày đối chiếu) | Tối thiểu **17**; Boot nêu phạm vi tương thích đến Java **27** | **7.0.10+** trong dòng tương ứng | **3.1.1** (đặc tả Jakarta Validation 3.1) | Hibernate Validator **9.1.5.Final** | `jakarta.validation.*` |
| **Spring Boot 3.5.16** | Tối thiểu **17**; Boot nêu phạm vi tương thích đến Java **25** | **6.2.19+** trong dòng tương ứng | **3.0.2** (đặc tả Jakarta Bean Validation 3.0) | Hibernate Validator **8.0.3.Final** | `jakarta.validation.*` |
| **Spring Boot 2.7.x** (dòng cũ, để nhận diện/migration) | Khởi điểm Java **8** | **5.3.x** | Bean Validation **2.0** | Hibernate Validator **6.2.x** | `javax.validation.*` |

Nguồn kiểm tra: [Spring Boot 4.1 system requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html), [Spring Boot 3.5 system requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html), [managed dependencies của Boot 4.1](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html), [managed dependencies của Boot 3.5](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html), [Hibernate Validator compatibility matrix](https://hibernate.org/validator/releases/).

**Lưu ý khi đọc bảng:**

1. **Java tối thiểu** là điều kiện khởi chạy; **Java tối đa mà Boot tuyên bố tương thích** không phải lời bảo đảm rằng mọi thư viện bên thứ ba cũng được thử nghiệm trên mọi JDK trong khoảng ấy. Hibernate Validator 9.1, chẳng hạn, công bố danh sách Java được hỗ trợ riêng; nếu ưu tiên môi trường phổ biến, chọn **JDK 21 hoặc 25** trong bộ Boot 4.1.
2. “Spring Framework **7.0.10+**” và “**6.2.19+**” là ngưỡng yêu cầu được nêu trong hướng dẫn Boot của các bản tương ứng, **không** có nghĩa nên ghép một dòng Spring Framework mới tùy ý vào Boot cũ. Hãy để BOM chọn patch version thực tế.
3. “Jakarta Validation **3.1**” là **phiên bản đặc tả**; “`jakarta.validation-api:3.1.1`” là **phiên bản artifact** được BOM quản lý. Tương tự, API `3.0.2` triển khai hợp đồng của đặc tả `3.0`.
4. Boot 2.7 được đưa vào để nhận biết hệ thống lịch sử, không phải lựa chọn mặc định cho dự án mới. Việc nâng từ Boot 2 lên Boot 3 kéo theo đổi namespace `javax.validation.*` sang `jakarta.validation.*`.
5. Các bản RC, milestone, snapshot (chẳng hạn một nhánh Boot mới chưa GA) cần được phân biệt với bản ổn định. Tránh dùng bản xem trước khi bài toán chỉ cần một stack đã phát hành chính thức.

## 3. Java nào nên dùng?

**Java 17** là mức cơ sở của Spring Framework 6 và 7, cũng như Spring Boot 3 và 4. Với dự án mới đang chọn Boot 4.1 hoặc Boot 3.5, **Java 21** là lựa chọn thực tế, phổ biến và thuộc dòng LTS; Java 25 cũng là một dòng LTS có thể cân nhắc nếu toàn bộ dependency, công cụ và môi trường sản xuất đều hỗ trợ.

Trước khi cấu hình project, kiểm tra:

~~~bash
java -version
javac -version
mvn -version
~~~

Lệnh `java -version` hiển thị Java Runtime được gọi; `javac -version` hiển thị trình biên dịch JDK; `mvn -version` cho biết Maven thực sự sử dụng Java nào. Với Gradle:

~~~bash
./gradlew --version
~~~

Trên Windows, có thể thay `./gradlew` bằng `gradlew.bat` hoặc sử dụng `mvnw.cmd` nếu dự án cung cấp Maven Wrapper.

Nếu `java -version` là 21 nhưng `mvn -version` lại sử dụng 17, build có thể thất bại khi khai báo `--release 21`. Điều chỉnh `JAVA_HOME`, cấu hình IDE/CI và Java toolchain cho khớp. Đừng chỉ dựa vào lựa chọn “Project SDK” đang hiển thị trong IDE.

### Phân biệt ba khái niệm Java version

- **JDK chạy build:** JDK mà Maven/Gradle và plugin build sử dụng.
- **Target/release bytecode:** phiên bản class file mà compiler tạo ra, ví dụ Java 21.
- **JDK chạy ứng dụng:** JVM thực tế trên máy chủ hoặc trong container. Nó phải đọc được bytecode và đáp ứng yêu cầu của framework/provider.

Ví dụ ứng dụng biên dịch với `--release 21` không thể chạy bằng JVM 17; lỗi điển hình là `UnsupportedClassVersionError`. Nếu không có nhu cầu dùng tính năng mới hơn, đặt release theo JDK triển khai thấp nhất đã được xác nhận là tương thích.

## 4. Chọn Jakarta Validation 3.0 hay 3.1?

### Jakarta Bean Validation 3.0

Đây là thế hệ đổi package từ `javax.validation.*` thành `jakarta.validation.*`, được sử dụng trong stack Jakarta EE 9/10 và Hibernate Validator 7/8. Bộ thực tế của Spring Boot **3.5.16** dùng **Jakarta Validation API 3.0.2 + Hibernate Validator 8.0.3.Final**. Java runtime vẫn phải đáp ứng yêu cầu **Java 17+** của Spring Boot 3.5.

### Jakarta Validation 3.1

Đặc tả Jakarta Validation **3.1** thuộc Jakarta EE **11**, dùng Java **17+** và làm rõ hỗ trợ **Java records**. Spring Framework 7 và Spring Boot 4 thuộc thế hệ Jakarta EE 11; Boot **4.1.2** quản lý **Jakarta Validation API 3.1.1 + Hibernate Validator 9.1.5.Final**.

Không nên kết luận rằng chỉ việc thay artifact API `3.0.2` thành `3.1.1` là đã nâng toàn bộ ứng dụng sang thế hệ mới. Provider, Spring integration và các thư viện phụ thuộc phải cùng phù hợp. Tương tự, việc thêm API `3.1` vào Boot 3.5 không tự động nâng Spring Framework 6 thành 7.

### API, provider và Spring Validator

Ba lớp thường gặp trong source code:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.BindingResult;
~~~

- `jakarta.validation.Valid` và `jakarta.validation.Validator` thuộc **Jakarta Validation API**.
- `org.hibernate.validator.*` thuộc **Hibernate Validator**, provider thực thi Jakarta Validation.
- `org.springframework.validation.Validator` là **interface validation của Spring**, khác với `jakarta.validation.Validator` dù Spring có adapter tích hợp hai API; `BindingResult` cũng thuộc Spring.

Chọn import theo nhu cầu cụ thể, không đổi lẫn hai interface `Validator` một cách máy móc.

**Quy tắc namespace:** mã Spring Boot 3/4 dùng `jakarta.validation.constraints.NotNull`, không dùng `javax.validation.constraints.NotNull` của dự án Boot 2. Bên cạnh source Java, phải rà soát constraint XML, custom validator, thư viện extension và các dependency cũ khi migration.

## 5. Cấu hình Maven khả dụng: Spring Boot 4.1.2 + Java 21

Ví dụ này chọn **Spring Boot 4.1.2**, **Java 21**, Jakarta Validation **3.1** và Hibernate Validator **9.1** do BOM của Boot quản lý. Đây là ứng dụng Java nhỏ để tự kiểm tra validation provider; không cần máy chủ HTTP.

Tạo file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>validation-compatibility</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

**Không cần ghi `<version>` cho starter, `jakarta.validation-api` hay `hibernate-validator`:** Spring Boot parent nhập bộ dependency management phù hợp. Khi cần Spring MVC cho form/data binding, thêm `org.springframework.boot:spring-boot-starter-webmvc` (Boot 4), còn ví dụ kiểm tra API thuần dưới đây không yêu cầu web.

Tạo file `src/main/java/com/example/demo/ValidationCompatibilityApplication.java`:

~~~java
package com.example.demo;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringBootVersion;
import org.springframework.context.annotation.Bean;
import org.springframework.core.SpringVersion;

@SpringBootApplication
public class ValidationCompatibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationCompatibilityApplication.class, args);
    }

    public record Registration(
            @NotBlank String name,
            @Min(18) int age) {
    }

    @Bean
    ApplicationRunner checkVersions(Validator validator) {
        return args -> {
            Registration invalid = new Registration("", 16);
            Set<ConstraintViolation<Registration>> errors =
                    validator.validate(invalid);

            System.out.println("validationErrors=" + errors.size());
            System.out.println("java=" + Runtime.version().feature());
            System.out.println("springBoot=" + SpringBootVersion.getVersion());
            System.out.println("springFramework=" + SpringVersion.getVersion());
        };
    }
}
~~~

Với JDK 21, Maven tương thích và các artifact đã tải về, chạy:

~~~bash
mvn spring-boot:run
~~~

Trong log, chương trình sẽ in **dòng đáng kiểm tra**:

~~~text
validationErrors=2
java=21
springBoot=4.1.2
~~~

Giá trị `springFramework=...` là phiên bản Spring Framework thực tế do dependency management chọn, vì vậy hãy **đọc giá trị được in ra**, không giả định mọi lần build trong tương lai luôn chọn cùng một patch. Nếu dùng JDK khác, `java=...` sẽ thay đổi tương ứng. Các log khởi động của Spring Boot không được coi là một phần cố định của output minh họa.

Tại sao có **2** lỗi? `name=""` vi phạm `@NotBlank` và `age=16` vi phạm `@Min(18)`. Nếu không có provider hoạt động, chương trình sẽ không có kết quả validation như mong đợi; bước này kiểm tra được cả API, provider và tích hợp của Spring Boot.

Cấu trúc file:

~~~text
validation-compatibility/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── demo/
                        └── ValidationCompatibilityApplication.java
~~~

Đây là ví dụ hoàn chỉnh trong một dự án Maven, không chạy bằng mỗi lệnh `javac ValidationCompatibilityApplication.java` vì nó cần Spring và Jakarta Validation trên classpath.

## 6. Tương đương khi dùng Gradle

Với **Gradle Groovy DSL** và JDK 21, có thể khai báo:

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Lưu file tên `build.gradle`. Bản plugin Spring Boot áp dụng cùng với `io.spring.dependency-management` để sử dụng BOM tương ứng; starter vẫn không khai báo số phiên bản thủ công. Kiểm tra Gradle Wrapper là **8.14+** (thuộc Gradle 8) hoặc phiên bản Gradle 9 được Boot 4.1 hỗ trợ. Chạy:

~~~bash
./gradlew bootRun
./gradlew dependencyInsight --dependency hibernate-validator --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.validation-api --configuration runtimeClasspath
~~~

Nếu môi trường của dự án sử dụng **Spring Boot 3.5**, hãy thay bằng Gradle version phù hợp Boot 3.5 và dùng JDK 17 hoặc 21; giữ nguyên nguyên tắc **để Boot quản lý API/provider**. Không sao chép nguyên cấu hình plugin/bộ starter của Boot 4 vào một build Boot 3 mà không kiểm tra tương thích.

## 7. Cách kiểm chứng phiên bản thực tế bằng dependency tree

Đừng chỉ đọc `pom.xml` hoặc `build.gradle`: dependency có thể đến gián tiếp qua starter, BOM, parent hoặc thư viện khác.

Với Maven:

~~~bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework:spring-core,jakarta.validation:jakarta.validation-api,org.hibernate.validator:hibernate-validator
~~~

Có thể xem cả cây đầy đủ bằng:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-validator --configuration runtimeClasspath
~~~

Hãy đối chiếu các artifact **được chọn cuối cùng** với dòng Boot đang chạy. Ví dụ đối với Boot 4.1.2, kỳ vọng thấy Java 21 (nếu cấu hình theo ví dụ), Spring Framework dòng 7.0 và Jakarta Validation API 3.1.1 cùng Hibernate Validator 9.1.5.Final; còn Boot 3.5.16 sẽ thuộc Spring 6.2, Validation API 3.0.2 và Hibernate Validator 8.0.3.Final.

Nếu dependency tree cho thấy hai version cùng một API hoặc provider bị ép từ dependency khác, hãy xác định **đường dẫn transitive** dẫn đến xung đột. Trong Maven, `dependencyManagement` quyết định phiên bản được chọn; trong Gradle, resolution strategy, platform/BOM hoặc constraint có thể ảnh hưởng đến kết quả. Việc phân tích **runtimeClasspath** đặc biệt quan trọng vì ứng dụng phải chạy với đúng dependency đã kiểm thử.

### Một checklist nhanh trước khi kết luận stack tương thích

1. Đọc tài liệu **System Requirements** của chính bản Boot đang dùng để xác định JDK và build tool.
2. Xem **Managed Dependency Coordinates** của đúng bản Boot để tìm `spring-core`, `jakarta.validation-api` và `hibernate-validator`.
3. Đối chiếu **Hibernate Validator Compatibility Matrix** để biết đặc tả Jakarta Validation và các Java version provider hỗ trợ.
4. Chạy Maven/Gradle dependency tree hoặc `dependencyInsight` để xác nhận artifact thực tế.
5. Chạy ứng dụng và một smoke test constraint, thay vì chỉ dựa vào việc mã nguồn biên dịch.
6. Ghi lại JDK/toolchain và khóa phiên bản Boot bằng Wrapper/BOM trong CI để máy phát triển và máy build dùng cùng một cấu hình.

## 8. Tương thích ở tầng Spring MVC và data binding

Một controller Spring MVC có thể dùng:

~~~java
@PostMapping("/users")
public String create(
        @Valid @ModelAttribute UserForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "users/form";
    }
    return "users/saved";
}
~~~

Đây là **đoạn trích minh họa**, không phải class Java độc lập. Ngoài các import thích hợp, cần có controller và `UserForm` được định nghĩa trong ứng dụng, cùng MVC và validation starter.

- `@ModelAttribute` sử dụng hệ thống data binding của Spring MVC để tạo/gán thuộc tính form.
- `@Valid` yêu cầu validation của đối tượng bằng provider tương thích khi được cấu hình.
- `BindingResult` nhận lỗi binding/validation và phải đặt **ngay sau** tham số cần kiểm tra để controller xử lý lỗi.
- Với Spring Boot 4, starter cho MVC là `spring-boot-starter-webmvc`; tên cũ `spring-boot-starter-web` được đánh dấu deprecated. Với Spring Boot 3, `spring-boot-starter-web` vẫn là starter MVC thông dụng.

Nếu thiếu `spring-boot-starter-validation`, ứng dụng có thể vẫn nhận form qua Spring MVC, nhưng annotation constraint có thể không được thực thi theo mong đợi. Vì thế, “bind thành công” **khác** “validation đã chạy và trả về lỗi đúng”.

Các mức Jakarta EE và Servlet cũng cần xem xét khi triển khai WAR/container ngoài. Ví dụ dòng Boot 3.5 sử dụng thế hệ Servlet 6.0/Tomcat 10.1, còn Boot 4.1 sử dụng Servlet 6.1/Tomcat 11. Một runtime/container quá cũ có thể gây lỗi dù code validation đã viết đúng.

## 9. Những lỗi phiên bản thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `package javax.validation does not exist` sau khi nâng Boot 3/4 | Mã nguồn vẫn import namespace cũ | Chuyển sang `jakarta.validation.*`; kiểm tra thư viện/custom constraint liên quan |
| `NoProviderFoundException` khi gọi `Validation.buildDefaultValidatorFactory()` | Có Jakarta Validation API nhưng thiếu provider tương thích trên runtime classpath | Thêm `spring-boot-starter-validation` trong Boot; nếu không dùng Boot, khai báo provider và phụ thuộc theo hướng dẫn của provider |
| `NoClassDefFoundError: jakarta/validation/...` | Thiếu API hoặc có dependency bị exclude/đóng gói thiếu | Xem runtime dependency tree, sửa dependency và đóng gói |
| `NoSuchMethodError`, `ClassNotFoundException` sau khi nâng version | Spring, provider, API hoặc thư viện transitive bị pha trộn không tương thích | Loại bỏ phiên bản ép tay, dùng BOM đồng bộ, xem đường đi của artifact lỗi |
| `UnsupportedClassVersionError` | JDK chạy không hỗ trợ bytecode được biên dịch | Đồng bộ target release với JDK runtime/CI |
| `UnexpectedTypeException` | Chọn annotation không phù hợp kiểu dữ liệu, ví dụ `@NotBlank` trên `Integer` | Dùng constraint đúng kiểu như `@NotNull` và `@Min` |
| `@Valid` không tạo lỗi như kỳ vọng | Chưa gọi validation, thiếu provider, không đúng đường tích hợp, hoặc ràng buộc đặt sai chỗ | Kiểm tra starter/provider, trigger validation, mô hình DTO và kết quả `BindingResult` |
| Có hai nhóm `javax.validation` và `jakarta.validation` trong dependency | Một dependency legacy kéo API cũ vào hoặc code import lẫn | Tìm dependency gốc, nâng/migrate module tương ứng, không tùy tiện thay package bằng cách ép version |

**Không nên chữa lỗi `NoSuchMethodError` bằng cách cập nhật ngẫu nhiên artifact lẻ.** Hãy nhìn phiên bản **đã được resolve** và chọn lại một bộ nhất quán theo BOM. Khi một thư viện bên ngoài còn yêu cầu `javax.validation`, cần đánh giá khả năng nâng/migrate chính thư viện đó trước.

## 10. Chọn bộ phiên bản theo tình huống

**Dự án Spring Boot mới:** bắt đầu từ một bản stable hiện hành, chẳng hạn Boot **4.1.2** tại thời điểm bài này được biên soạn; chọn JDK **21** hoặc **25** nếu các dependency và hạ tầng tương thích. Khai báo validation starter và để Boot quản lý Jakarta Validation 3.1/provider 9.1.

**Dự án đang chạy Spring Boot 3.5:** giữ dòng **Spring Framework 6.2 + Jakarta Validation 3.0 + Hibernate Validator 8**, nâng các bản patch tương thích theo chính sách dự án. Không cần nâng toàn bộ chỉ để dùng `@NotNull`, `@Valid` hay data binding cơ bản.

**Dự án dùng Spring Framework thuần, không có Boot:** tham khảo system requirements của đúng dòng Spring, chọn provider theo bản Jakarta Validation API và quản lý trực tiếp các dependency cần thiết (có thể gồm implementation phục vụ message interpolation). Ở nhánh này, không có BOM Boot để tự động đảm bảo mọi thư viện khớp phiên bản.

**Hệ thống Spring Boot 2 / Spring Framework 5:** nhận diện namespace `javax.validation` và lên kế hoạch migration toàn bộ sang `jakarta.validation` khi nâng lên Boot 3/4. Đây là thay đổi package và hệ sinh thái, không chỉ thay con số version trong build file.

### Ví dụ quyết định nhanh

- **Java 11 + Boot 4.1?** Không tương thích vì Boot 4.1 yêu cầu **Java 17+**. Cần nâng JDK hoặc chọn một thế hệ Spring cũ phù hợp với ràng buộc legacy, đồng thời xem xét vòng đời hỗ trợ.
- **Java 21 + Boot 3.5 + Hibernate Validator 8?** Là bộ phù hợp với các yêu cầu đã công bố của dòng này khi sử dụng BOM của Boot.
- **Java 21 + Boot 4.1 + Jakarta Validation API 3.0.2 do ép tay?** Không nên: Boot 4.1 quản lý API **3.1.1** và provider **9.1**. Bỏ ép phiên bản, phục hồi dependency management và chạy lại kiểm thử.
- **Chỉ có dependency `jakarta.validation-api`?** Có thể biên dịch các annotation nhưng chưa đủ để thực thi constraint; cần một provider hoặc môi trường container đã cấp provider thích hợp.

## 11. Câu hỏi tự luyện

1. Vì sao chỉ nhìn tên package `jakarta.validation` chưa đủ để biết đó là API 3.0 hay 3.1?
2. Một dự án Boot 3.5 có Java 21 và annotation `@NotNull`, nhưng runtime không hề báo vi phạm. Cần kiểm tra những dependency và điểm tích hợp nào?
3. Nếu Gradle chọn Hibernate Validator 9.x trong dự án Boot 3.5 đang dùng BOM mặc định, nên dùng lệnh nào để tìm dependency đã ép phiên bản?
4. Khi nâng Boot 2 lên Boot 3, thay đổi namespace nào tác động tới constraint annotation và custom validator?
5. Vì sao “Spring Boot hỗ trợ Java X” vẫn chưa đủ để khẳng định mọi provider, JDBC driver và công cụ build trong dự án đều hỗ trợ Java X?

**Ghi nhớ:** hãy chọn **Spring Boot → Java/JDK → BOM-managed Spring Framework, Jakarta Validation API và provider**, sau đó kiểm tra dependency tree và chạy validation thực tế. Sự tương thích là thuộc tính của **toàn bộ bộ thư viện và môi trường chạy**, không chỉ một dòng trong `pom.xml`.

### Tài liệu chính thức để tự cập nhật

- [Spring Boot — System Requirements (bản stable hiện hành)](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.1 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Validation 3.1 — Specification](https://jakarta.ee/specifications/bean-validation/3.1/)
- [Hibernate Validator — Releases và Compatibility Matrix](https://hibernate.org/validator/releases/)
- [Hibernate Validator — Migration Guides](https://hibernate.org/validator/documentation/)