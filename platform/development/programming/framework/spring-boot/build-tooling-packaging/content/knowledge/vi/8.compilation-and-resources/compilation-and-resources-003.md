# Cấu hình annotation processor và mã nguồn được sinh

Khi biên dịch một ứng dụng Spring Boot, ngoài các tệp `.java` do lập trình viên viết, trình biên dịch còn có thể gọi **annotation processors** để đọc chú thích và khai báo Java, kiểm tra quy tắc, rồi **sinh thêm tệp nguồn Java hoặc tài nguyên metadata**. Ví dụ, MapStruct sinh lớp thực thi interface mapper, còn `spring-boot-configuration-processor` sinh `spring-configuration-metadata.json` từ các lớp `@ConfigurationProperties`.

Một dự án có thể chạy trong IDE nhưng thất bại khi `mvn clean verify` hoặc `./gradlew clean build` nếu processor chưa được khai báo đúng. Ngược lại, một bản build thành công có thể thiếu metadata hỗ trợ IDE dù ứng dụng runtime vẫn chạy. Cần hiểu **processor được chạy ở bước nào, lấy từ classpath nào, tạo loại tệp gì, tệp đó được biên dịch/đóng gói ra sao và kiểm chứng bằng gì**.

Bài này áp dụng cho Java 17+, lấy **Spring Boot 3.3.13**, **MapStruct 1.6.3** và Maven/Gradle làm ví dụ nhất quán. Các phiên bản là lựa chọn cố định để mô tả cơ chế, không phải tuyên bố chúng là phiên bản mới nhất.

## 1. Annotation processor là gì?

Annotation processor là chương trình chạy **trong thời gian biên dịch** qua Java Annotation Processing API (thường gọi là JSR 269), với các kiểu như `javax.annotation.processing.Processor`, `AbstractProcessor`, `RoundEnvironment` và `javax.lang.model.element.Element`. Từ mã nguồn đã được phân tích, processor truy cập mô hình cú pháp/các khai báo và có thể tạo tệp bằng `Filer`.

Luồng tổng quát:

```text
src/main/java/*.java
       |
       v
javac / JavaCompile / maven-compiler-plugin
       |
       +--> Compile classpath: annotation API, thư viện ứng dụng
       |
       +--> Processor path: MapStruct processor,
       |                    Spring Boot configuration processor,...
       |
       v
Phân tích annotation / types / elements
       |
       +--> Sinh .java  ------> các vòng xử lý tiếp theo --> biên dịch .class
       |
       +--> Sinh metadata/resources (JSON, service file...)
       |
       v
classes + resources + dependencies
       |
       v
Executable JAR/WAR hoặc artifact khác
```

Trình biên dịch có thể chạy **nhiều round**: khi processor sinh tệp nguồn Java mới, tệp đó được phân tích trong round tiếp theo; cuối cùng compiler biên dịch source gốc và source được sinh theo cấu hình. Processor không phải một bước HTTP request, không phải Spring bean trong application context, và thường không chạy mỗi khi ứng dụng xử lý một request.

Về mặt kiểm soát bản dựng, processor là **mã bên thứ ba được thực thi trong quá trình build**. Chỉ dùng các processor tin cậy, pin phiên bản và không để compiler tự tìm và chạy mọi processor tình cờ xuất hiện trên dependency classpath.

### Ba loại kết quả dễ bị nhầm

| Công cụ/cơ chế | Đầu vào | Kết quả điển hình | Có sinh `.java` không? |
| --- | --- | --- | --- |
| **MapStruct** | Interface `@Mapper`, `@Mapping` | `CustomerMapperImpl.java` rồi `CustomerMapperImpl.class` | **Có** |
| **Spring Boot configuration processor** | `@ConfigurationProperties` trên class/record | `META-INF/spring-configuration-metadata.json` | **Không bắt buộc; mục đích chính là JSON metadata** |
| **Lombok** | `@Getter`, `@Builder`, `@Data`... | Bổ sung thành phần vào cây biên dịch để ra bytecode | **Thường không tạo file `.java` riêng** |
| **Hibernate JPA metamodel processor** | Entity JPA | Lớp metamodel như `Customer_` | Có |
| **Spring AOT** | Phân tích ứng dụng và bean definitions qua task AOT riêng | Mã nguồn/resources/hints dùng cho AOT/native | **Có thể có**, nhưng **không đồng nghĩa** JSR 269 annotation processing |

**Phân biệt annotation và processor:** `@Mapper` hoặc `@ConfigurationProperties` chỉ là metadata/annotation API được import trong mã Java. Một processor cụ thể phải được cấp ở **processor path** và được compiler chạy; nếu không, không có tác nhân tạo ra triển khai/metadata tương ứng.

## 2. Hai đường phụ thuộc khác nhau: compile classpath và processor path

Trong một build Java, nên phân biệt:

1. **Compile classpath**: những class/annotation types mà mã nguồn có thể import khi biên dịch, ví dụ `org.mapstruct.Mapper`.
2. **Annotation processor path**: các JAR chứa compiler plugins/processor implementations được `javac` thực thi, ví dụ `org.mapstruct:mapstruct-processor`.

Với Gradle, hai cấu hình thường là `implementation`/`compileOnly` và `annotationProcessor`. Với Maven Compiler Plugin 3.x, dùng `<dependencies>` cho API mà source cần và `<annotationProcessorPaths>` cho processor khi muốn kiểm soát đường chạy.

Ví dụ MapStruct:

```text
Source: import org.mapstruct.Mapper
          |
          +-- cần org.mapstruct:mapstruct trên compile classpath

Compiler: tìm org.mapstruct.ap.MappingProcessor
          |
          +-- cần org.mapstruct:mapstruct-processor trên processor path
          |
          +-- tạo CustomerMapperImpl.java
```

Nếu chỉ thêm `mapstruct` mà không cấp `mapstruct-processor`, annotation có thể được nhận diện nhưng **không có mapper implementation** được tạo. Nếu chỉ thêm `mapstruct-processor` vào processor path mà quên API `mapstruct` trên compile classpath, mã import `@Mapper` sẽ không biên dịch. Một số bộ thư viện gộp API và processor, nhưng hãy đọc tài liệu của từng bộ thay vì giả định tất cả có cùng cấu trúc.

### Compiler xử lý và lưu đầu ra

- **Maven**: tệp Java do processor sinh mặc định thường ở `target/generated-sources/annotations/`; class đã biên dịch ở `target/classes/`. Spring Boot metadata nằm dưới `target/classes/META-INF/` khi được sinh thành công.
- **Gradle Java plugin**: Java source sinh bởi `compileJava` thường ở `build/generated/sources/annotationProcessor/java/main/`; class và class-output resources ở `build/classes/java/main/` hoặc thư mục output tương ứng của task.
- **JAR** thường chứa **`.class` đã biên dịch và tài nguyên**, không mặc nhiên chứa toàn bộ source `.java` được sinh. Trong executable Spring Boot JAR, đầu ra của ứng dụng xuất hiện dưới `BOOT-INF/classes/`.

Đừng copy source được sinh vào `src/main/java` để “chữa lỗi thiếu class”. Generated sources là output của build; file generator tạo lại phải xuất phát từ annotation + processor + cấu hình build. Chỉnh trực tiếp generated files thường bị mất ở lần build sau và khiến cùng một class có nhiều bản khai báo.

## 3. Ví dụ hoàn chỉnh: một processor sinh Java, một processor sinh JSON

Ví dụ này cho phép thấy **hai loại đầu ra trong cùng một Spring Boot application**:

- MapStruct đọc interface `CustomerMapper` và tạo Java class `CustomerMapperImpl` có thể đăng ký như Spring bean.
- Spring Boot configuration processor đọc record `CustomerSettings` có `@ConfigurationProperties(prefix = "demo")` và tạo metadata cho property `demo.message`.
- Controller gọi bean mapper; một test HTTP qua `MockMvc` xác nhận Spring thực sự khởi tạo implementation đã được sinh.

### 3.1. Cấu trúc

```text
annotation-processor-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/aptdemo/
    │   │   ├── AptDemoApplication.java
    │   │   ├── Customer.java
    │   │   ├── CustomerView.java
    │   │   ├── CustomerMapper.java
    │   │   ├── CustomerSettings.java
    │   │   └── CustomerController.java
    │   └── resources/application.yml
    └── test/
        └── java/dev/example/aptdemo/
            └── CustomerControllerTest.java
```

Đây là ví dụ Maven chạy độc lập với Java 17. Ở mục Gradle, có thể dùng **cùng các tệp Java/YAML** nhưng thay `pom.xml` bằng cấu hình Gradle tương đương.

### 3.2. Maven `pom.xml` đầy đủ

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

    <groupId>dev.example</groupId>
    <artifactId>annotation-processor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <mapstruct.version>1.6.3</mapstruct.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct</artifactId>
            <version>${mapstruct.version}</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.mapstruct</groupId>
                            <artifactId>mapstruct-processor</artifactId>
                            <version>${mapstruct.version}</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao cấu hình như vậy?**

- `spring-boot-starter-parent` quản lý version các starter và mặc định Java/Maven plugin của Spring Boot. Phiên bản `maven-compiler-plugin` được ghi tường minh ở đây để dễ đối chiếu cấu hình processor.
- `org.mapstruct:mapstruct` chứa annotation/API mà source Java import; vì thế nằm trong `<dependencies>`.
- `mapstruct-processor` và `spring-boot-configuration-processor` chỉ được cấp cho compiler qua `<annotationProcessorPaths>`, **không cần** đưa chúng vào runtime dependencies của ứng dụng.
- Spring Boot Maven Plugin tạo executable JAR nhờ execution `repackage` do starter parent quản lý khi plugin được khai báo; đó là **packaging plugin**, độc lập với hai annotation processors.
- Các processor path được liệt kê tường minh, giúp tránh tình cờ chạy một processor có trong dependency graph thông thường. Khi thêm processor mới, phải bổ sung vào danh sách này.

Để chạy ví dụ cần JDK 17 tương thích và Maven 3.9.x (hoặc Maven Wrapper tương ứng). Ví dụ cố định Maven Compiler Plugin 3.13.0; với một dự án khác, kiểm tra tương thích JDK/plugin theo baseline build của dự án.

### 3.3. Mã Java của ứng dụng

Tệp `src/main/java/dev/example/aptdemo/AptDemoApplication.java`:

```java
package dev.example.aptdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class AptDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AptDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/dev/example/aptdemo/Customer.java`:

```java
package dev.example.aptdemo;

public record Customer(long id, String name) {
}
```

Tệp `src/main/java/dev/example/aptdemo/CustomerView.java`:

```java
package dev.example.aptdemo;

public record CustomerView(long id, String displayName) {
}
```

Tệp `src/main/java/dev/example/aptdemo/CustomerMapper.java`:

```java
package dev.example.aptdemo;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CustomerMapper {
    @Mapping(source = "name", target = "displayName")
    CustomerView toView(Customer customer);
}
```

Đây là interface, không có phương thức `toView` được viết tay. Khi `javac` xử lý `@Mapper` và `@Mapping`, MapStruct sinh `CustomerMapperImpl.java` với logic sao chép `id` và ánh xạ `name → displayName`. `componentModel = "spring"` làm implementation được sinh có annotation thích hợp để Spring quản lý nó như một bean.

Tệp `src/main/java/dev/example/aptdemo/CustomerSettings.java`:

```java
package dev.example.aptdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record CustomerSettings(String message) {
}
```

Record này cung cấp binding cấu hình runtime. `@ConfigurationPropertiesScan` ở application class giúp Spring đăng ký bean `CustomerSettings`. **Annotation processor không thực hiện property binding khi chạy ứng dụng**; nhiệm vụ của nó là tạo metadata để IDE/tool hỗ trợ cấu hình. Spring Boot runtime vẫn có thể bind `demo.message` ngay cả khi JSON metadata không được sinh, miễn classes/configuration đã được setup đúng.

Tệp `src/main/java/dev/example/aptdemo/CustomerController.java`:

```java
package dev.example.aptdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    private final CustomerMapper mapper;
    private final CustomerSettings settings;

    public CustomerController(CustomerMapper mapper, CustomerSettings settings) {
        this.mapper = mapper;
        this.settings = settings;
    }

    @GetMapping("/customer")
    public CustomerView customer() {
        return mapper.toView(new Customer(7L, settings.message()));
    }
}
```

Với Spring component model của MapStruct, constructor injection trên `CustomerController` nhận một bean triển khai `CustomerMapper` sau khi source sinh đã được biên dịch. Không cần tự tạo `new CustomerMapperImpl()` hoặc tự khai báo `@Bean`.

Tệp `src/main/resources/application.yml`:

```yaml
demo:
  message: Lan
```

### 3.4. Test kiểm chứng end-to-end

Tệp `src/test/java/dev/example/aptdemo/CustomerControllerTest.java`:

```java
package dev.example.aptdemo;

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
class CustomerControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void mappingIsGeneratedAndRegisteredAsSpringBean() throws Exception {
        mvc.perform(get("/customer"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }
}
```

Bài test chứng minh source `CustomerMapperImpl` đã được sinh, biên dịch và Spring đăng ký như bean: nếu thiếu implementation, application context thường không khởi tạo được `CustomerController`. Kiểm tra `jsonPath` không phụ thuộc thứ tự thuộc tính trong JSON.

### 3.5. Biên dịch, test và chạy

Trong thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
java -jar target/annotation-processor-demo-1.0.0.jar
```

Nếu project đã có Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows dùng `mvnw.cmd`). Lệnh `clean verify` xóa output cũ, chạy compiler/annotation processors, unit test và các goal được gắn đến `verify`.

Mở terminal thứ hai sau khi ứng dụng đã khởi động:

```bash
curl -s http://localhost:8080/customer
```

Nội dung response theo các trường:

```json
{"id":7,"displayName":"Lan"}
```

Thứ tự thuộc tính JSON có thể do serializer/configuration quyết định; giá trị `id = 7` và `displayName = "Lan"` mới là điều test kiểm chứng.

## 4. Quan sát đầu ra thật sau khi compiler chạy

Không chỉ nhìn log `BUILD SUCCESS`. Hãy kiểm tra **tệp được sinh, class đã biên dịch và metadata** để phân biệt hai processor:

| Đường dẫn Maven | Ai tạo? | Ý nghĩa |
| --- | --- | --- |
| `target/generated-sources/annotations/dev/example/aptdemo/CustomerMapperImpl.java` | MapStruct | Java source được sinh từ interface `CustomerMapper` |
| `target/classes/dev/example/aptdemo/CustomerMapperImpl.class` | Java compiler | Bytecode đã biên dịch từ source được sinh |
| `target/classes/META-INF/spring-configuration-metadata.json` | Spring Boot configuration processor | Metadata mô tả cấu hình như `demo.message` |
| `target/annotation-processor-demo-1.0.0.jar` | Maven JAR + Spring Boot Maven Plugin | Executable JAR; chứa class/resource application |

Trên Linux/macOS, trong thư mục dự án:

```bash
ls target/generated-sources/annotations/dev/example/aptdemo/
ls target/classes/dev/example/aptdemo/CustomerMapperImpl.class
grep -n 'demo.message' target/classes/META-INF/spring-configuration-metadata.json
jar tf target/annotation-processor-demo-1.0.0.jar
```

Trong danh sách `jar tf`, kiểm tra:

```text
BOOT-INF/classes/dev/example/aptdemo/CustomerMapperImpl.class
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Đây là hai entry quan trọng; đầu ra `jar tf` sẽ có nhiều entry khác. Trong output metadata, tìm một property entry cho `demo.message`. Nếu tệp không có, cần kiểm tra processor configuration và cấu trúc `@ConfigurationProperties`. Không mặc định metadata processor sinh ra một class Java chỉ vì MapStruct có tạo `.java`.

Trên Windows PowerShell có thể dùng:

```powershell
Test-Path target/generated-sources/annotations/dev/example/aptdemo/CustomerMapperImpl.java
Test-Path target/classes/META-INF/spring-configuration-metadata.json
Select-String -Path target/classes/META-INF/spring-configuration-metadata.json -Pattern 'demo.message'
```

Giá trị mong đợi ở hai lệnh `Test-Path` là `True` nếu build đúng. Lệnh `Select-String` tìm chuỗi `demo.message`; cách format JSON và thứ tự các trường có thể thay đổi theo processor.

**Điểm kiểm chứng cốt lõi:** source được sinh rồi được compiler biên dịch; JAR thường mang **class đã biên dịch**. Metadata JSON là một resource build-time hỗ trợ công cụ, không phải thứ quyết định profile nào được kích hoạt hoặc giá trị runtime của `demo.message`.

## 5. Cấu hình Gradle tương đương

Nếu dự án sử dụng Gradle, tạo `settings.gradle` và `build.gradle` ở thư mục gốc **thay cho `pom.xml`**. Giữ nguyên source Java, YAML và test ở mục 3.

`settings.gradle`:

```groovy
rootProject.name = 'annotation-processor-demo'
```

`build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.mapstruct:mapstruct:1.6.3'

    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi `org.springframework.boot` và `io.spring.dependency-management` cùng được áp dụng, Spring Boot Gradle Plugin phối hợp nhập BOM của Boot release tương ứng, nên dependency `spring-boot-configuration-processor` trong ví dụ có thể bỏ version. Nếu dùng Gradle native `platform(...)` thay vì dependency management plugin, phải bảo đảm configuration chứa processor cũng nhận constraints/versions cần thiết; đừng giả định BOM tự có hiệu lực ở mọi configuration.

Các đường phụ thuộc:

- `implementation 'org.mapstruct:mapstruct:1.6.3'`: source compile thấy annotation API.
- `annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'`: chạy processor sinh `CustomerMapperImpl.java`.
- `annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'`: chạy processor tạo configuration metadata JSON.
- `testImplementation ...starter-test`: biên dịch/chạy test; nếu **test sources tự khai báo mapper cần xử lý**, phải xem xét `testAnnotationProcessor` riêng, chứ không mặc định processor của main áp dụng giống hệt cho test compilation.

Trong dự án đã có Gradle Wrapper phù hợp, chạy (Windows dùng `gradlew.bat`):

```bash
./gradlew clean build
java -jar build/libs/annotation-processor-demo-1.0.0.jar
```

Kiểm tra những đầu ra thường gặp của Java plugin:

```text
build/generated/sources/annotationProcessor/java/main/dev/example/aptdemo/CustomerMapperImpl.java
build/classes/java/main/dev/example/aptdemo/CustomerMapperImpl.class
build/classes/java/main/META-INF/spring-configuration-metadata.json
build/libs/annotation-processor-demo-1.0.0.jar
```

Đường dẫn class-output metadata có thể thay đổi theo task/toolchain/plugin đặc thù; xác nhận theo cấu hình JavaCompile thực tế. Với `bootJar`, các tệp `.class` và metadata cần thiết được đưa vào `BOOT-INF/classes/`. Plain JAR và executable JAR có layout đóng gói khác nhau.

Nếu dùng Gradle mặc định `annotationProcessor`, compiler nhận processor qua **processor path riêng**. Không nên chuyển processor sang `implementation` chỉ để IDE “nhìn thấy”, vì làm nhiễm classpath và có thể không kích hoạt processing như mong muốn, đặc biệt khi nâng JDK.

## 6. Vai trò riêng của spring-boot-configuration-processor

Spring Boot dùng `@ConfigurationProperties` để mô tả và bind một nhóm thuộc tính cấu hình sang Java bean/record. `spring-boot-configuration-processor` phân tích khai báo này và sinh metadata, giúp IDE gợi ý tên property, loại dữ liệu và mô tả. **Runtime property binding là cơ chế khác**, không phụ thuộc việc JSON metadata có tồn tại.

Ví dụ:

```java
package dev.example.aptdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record CustomerSettings(String message) {
}
```

Processor có thể tạo metadata cho `demo.message` dựa trên tên prefix và thành phần `message` của record. IDE hỗ trợ Spring Boot có thể dùng metadata này để gợi ý key trong `application.yml`.

Một số giới hạn quan trọng:

- Processor không phát sinh giá trị `Lan` trong tệp metadata chỉ vì nó xuất hiện trong `application.yml`; nó phân tích khai báo Java và metadata bổ sung, không dùng nó làm hệ thống cấu hình runtime.
- Metadata thường không giữ secret. Nếu có mô tả và gợi ý giá trị qua tài liệu bổ sung, đừng đưa credential thật vào metadata.
- Nếu property được định nghĩa theo cách processor không nhận diện, JSON có thể thiếu entry dù ứng dụng vẫn bind được qua runtime. Điều này cần kiểm tra tệp đầu ra, không đoán từ log start.
- Khi dùng Lombok cùng configuration processor, thứ tự và sự tương thích processor có thể quan trọng vì metadata phải nhìn thấy mô hình thuộc tính cuối cùng.
- Khi có tệp `src/main/resources/META-INF/additional-spring-configuration-metadata.json`, cần quan tâm thứ tự xử lý tài nguyên. Với Gradle, tài liệu Spring Boot hướng dẫn cho `compileJava` thấy kết quả của `processResources` (ví dụ `tasks.named('compileJava') { inputs.files(tasks.named('processResources')) }`), nhưng chỉ cấu hình khi thật sự dùng metadata bổ sung.

## 7. Annotation processing trong `javac`: discovery, round và tùy chọn

Khi được bật, Java compiler có thể tìm processor qua service provider file `META-INF/services/javax.annotation.processing.Processor` trong JAR trên processor path. Một cách khác là chỉ định tên processor tường minh. Processor dùng `RoundEnvironment` để đọc những phần tử mang annotation, còn `Filer#createSourceFile` hoặc `createResource` để tạo output.

Một workflow processor đơn giản (minh họa, không phải lệnh build độc lập):

```text
Round 1: thấy @Mapper trên CustomerMapper
  -> MapStruct sinh CustomerMapperImpl.java
Round 2: compiler nhận CustomerMapperImpl.java
  -> xử lý annotation có thể phát sinh ở source mới
Final round
  -> processor hoàn tất, compiler biên dịch source
```

Tùy chọn `javac` có liên quan:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-processorpath` hoặc `--processor-path` | Nơi compiler tìm processor |
| `-processor tên.lớp.Processor` | Chỉ định processor cụ thể |
| `-proc:none` | Biên dịch **không** chạy annotation processing |
| `-proc:only` | Chạy annotation processing mà không biên dịch Java class |
| `-proc:full` | Chạy annotation processing **và** biên dịch |
| `-s thư_mục` | Thư mục lưu Java source được sinh |

Các công cụ Maven/Gradle chuyển cấu hình của chúng thành các tùy chọn compiler phù hợp. **Không cần tự gọi `javac` với danh sách JAR dài** cho các dự án Spring Boot sử dụng plugin build đã được cấu hình.

### Chú ý JDK 23 trở lên

Từ **JDK 23**, `javac` không còn mặc định quét classpath và chạy annotation processors chỉ vì tình cờ thấy chúng, khi không có yêu cầu hoặc cấu hình processing tường minh. Vì vậy một dự án dựa vào implicit discovery có thể bắt đầu thiếu generated source sau khi nâng JDK.

Giải pháp là **khai báo processor path hoặc processor cụ thể bằng build tool**, như `<annotationProcessorPaths>` hoặc Gradle `annotationProcessor`. Nếu buộc phải điều chỉnh `-proc:full`, kiểm tra JDK thực chạy có hỗ trợ tùy chọn ấy; `-proc:full` được backport vào các bản cập nhật JDK 17 gần đây, **không nên giả định mọi bản JDK 17 cũ đều nhận tùy chọn này**.

Với cấu hình Maven ở mục 3, danh sách processor path đã được khai báo tường minh; không cần thêm `<proc>full</proc>` chỉ để ví dụ Java 17 chạy được. Kiểm tra mục tiêu bảo mật của dự án khi quyết định có dùng discovery hay liệt kê đích danh các class processor.

## 8. Các công nghệ sinh mã khác cần phân biệt

### 8.1. Lombok

Lombok được nhiều dự án dùng với `@Getter`, `@Builder`, `@RequiredArgsConstructor` để giảm boilerplate. Nó can thiệp vào quá trình biên dịch, nên sau build thường **không thấy tệp nguồn `SomeClassWithGetters.java` được sinh độc lập**. Tương tác với MapStruct có thể cần adapter `lombok-mapstruct-binding` để MapStruct hiểu các getter/setter do Lombok cung cấp.

Cấu hình Gradle điển hình chỉ dành cho Lombok (đoạn thêm vào `dependencies`):

```groovy
compileOnly 'org.projectlombok:lombok:<version-compatible>'
annotationProcessor 'org.projectlombok:lombok:<version-compatible>'
```

`<version-compatible>` trong fragment này là ký hiệu thay thế cần chọn version cụ thể của Lombok theo JDK/project; đoạn này **không tự chạy độc lập**. Khi phối hợp Lombok và MapStruct, thêm binding dependency được hai dự án khuyến nghị, kiểm tra xử lý processor và chạy build sạch. Không dùng Lombok trong ví dụ MapStruct ở mục 3, do đó **không** cần binding ở POM mẫu.

### 8.2. JPA metamodel và QueryDSL

Các công cụ sinh `*_` metamodel hoặc Q-types có thể dùng annotation processing để tạo kiểu Java hỗ trợ truy vấn kiểu tĩnh. Cấu trúc thư mục đầu ra và cấu hình processor tương tự MapStruct, nhưng tên artifact/processor và tương thích `javax`/`jakarta` khác nhau giữa các thế hệ. Với Spring Boot 3.x/Jakarta Persistence, kiểm tra processor đúng nhánh Jakarta trước khi áp dụng hướng dẫn cũ.

### 8.3. Spring AOT và OpenAPI code generation

Spring AOT có thể tạo source/resources dựa trên phân tích application context ở task `processAot`/goal tương ứng; OpenAPI Generator có thể tạo client/server từ schema ở một bước plugin riêng. Cả hai đều có **generated source**, nhưng không nên gọi chúng là Java annotation processor nếu không dùng JSR 269 của compiler.

**Câu hỏi phân biệt:** Tệp được sinh trong compiler annotation-processing round, hay ở một task/goal code generation riêng trước/sau compile? Câu trả lời quyết định task dependency, source directories, cache và cách debug.

## 9. Generated sources trong IDE, CI và source control

**IDE:** IntelliJ IDEA, Eclipse hoặc VS Code có thể dùng chế độ build nội bộ/Java language server khác Maven/Gradle CLI. Khi IDE báo `Cannot resolve CustomerMapperImpl` nhưng `mvn clean verify` vẫn pass, kiểm tra annotation processing của IDE, import lại Maven/Gradle project và source root `generated-sources`. Không tự thêm generated files vào `src/main/java` để dập lỗi hiển thị.

**CI:** dùng Wrapper nếu dự án cung cấp, xác định JDK/toolchain và chạy **clean build** để loại khả năng phụ thuộc vào output cũ trên máy phát triển:

```bash
# Maven
mvn clean verify

# Hoặc Gradle
./gradlew clean build
```

Không chạy cả hai với hai build model khác nhau cho cùng một bản phát hành nếu dự án không chủ động hỗ trợ chúng. Các câu lệnh trên là lựa chọn **thay thế**, không phải hai bước tuần tự bắt buộc.

**Source control:** đưa interface, annotation/configuration và POM/Gradle build script vào Git. Thông thường loại trừ `target/`, `build/` và các generated files khỏi Git nếu chúng có thể tái tạo. Nếu có yêu cầu đặc biệt phải commit generated sources (ví dụ contract từ hệ thống ngoài), quy định rõ **ai sở hữu**, cách regen và kiểm tra drift; tránh file vừa được generator tạo vừa bị sửa tay.

**Build reproducibility:** pin version processor và build plugins. Một số generator ghi thời gian/build environment vào generated sources, làm artifacts khác nhau. Cấu hình suppress timestamp nếu processor hỗ trợ, xem tùy chọn cụ thể của MapStruct và giữ JDK/toolchain phù hợp. Không tuyên bố reproducible chỉ vì đã chạy `clean`.

**Vòng đời compile:** tránh lắp đặt task sao cho `compileJava` chạy trước một task sinh source bắt buộc mà không có dependency thích hợp. Với JSR 269 processor được khai báo đúng cách, generated Java sources được compiler xử lý như một phần của compilation; không cần một custom copy task giả.

**Tách module:** nếu tự phát triển processor nội bộ, cần xây processor thành artifact riêng (hoặc một module được compile trước), để project sử dụng có thể đặt artifact đã build trên annotation processor path. Processor không thể thông thường vừa nằm trong source chưa biên dịch của chính module consumer vừa được compiler dùng để sinh code cho lần biên dịch đó.

## 10. Tìm lỗi theo tín hiệu thay vì đoán

| Triệu chứng | Nguyên nhân điển hình | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `Cannot find symbol CustomerMapperImpl` hoặc Spring thiếu bean mapper | MapStruct processor không chạy, sai processor path, generated output chưa được compile | Xem `target/generated-sources/annotations`/`build/generated/sources`, danh sách processor và log compiler; chạy clean build |
| `No qualifying bean of type CustomerMapper` | Không sinh implementation hoặc mapper được sinh không dùng Spring component model | Xác nhận `@Mapper(componentModel = "spring")`, `CustomerMapperImpl.class` và package scan |
| Interface có `@Mapper` nhưng không sinh `.java` | Chỉ có MapStruct annotation API, thiếu processor implementation | Thêm `mapstruct-processor` vào processor path thích hợp |
| Compiler báo không tìm thấy `org.mapstruct.Mapper` | Thiếu MapStruct API trên compile classpath | Khai báo `mapstruct` trong `<dependencies>` hoặc Gradle `implementation` |
| Ứng dụng chạy được nhưng IDE không autocomplete `demo.message` | Thiếu `spring-configuration-metadata.json` hoặc IDE chưa index metadata | Thêm `spring-boot-configuration-processor`, compile lại, kiểm tra JSON và IDE sync |
| `@ConfigurationProperties` không bind tại runtime | Chưa đăng ký configuration properties bean, cấu hình sai prefix/key hoặc nguồn config | Dùng `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` và kiểm tra Spring `Environment`; metadata processor không xử lý runtime binding |
| Maven build được ở máy A, thiếu generated code trên máy B | Khác JDK/plugin, annotation processing bị vô hiệu hoặc dựa vào implicit discovery | Kiểm tra `mvn -version`, POM hiệu lực, processor paths; chú ý JDK 23+ |
| Gradle IDE khác kết quả CLI | IDE tự compile, không nhận processor path hoặc generated source roots | Reimport Gradle project, bật hỗ trợ annotation processing, đối chiếu `./gradlew clean build` |
| MapStruct + Lombok không nhìn thấy getters | Thứ tự processor/binding hoặc version không tương thích | Kiểm tra `lombok-mapstruct-binding` và phiên bản chính thức; dùng processor path rõ ràng |
| Có Java generated nhưng không thấy trong Boot JAR | JAR chứa compiled `.class`, không mặc định chứa generated `.java` | Kiểm tra `BOOT-INF/classes/...Impl.class` bằng `jar tf` |
| `-proc:none` được bật và mapper biến mất | Compiler bị yêu cầu bỏ annotation processing | Gỡ/tách cờ diagnostic khỏi build phát hành |
| Generated metadata sai sau đổi source | Incremental compilation/cache/IDE chưa rebuild đầy đủ | Chạy `clean compile` để xác nhận, rồi sửa cấu hình task inputs/outputs nếu lỗi lặp lại |

### Quy trình chẩn đoán có thứ tự

1. **Xác nhận compiler thực chạy:** `mvn -version` hoặc Gradle toolchain; kiểm tra Java version, plugin version và module đang build.
2. **Kiểm tra đầu vào:** source có annotation, đúng package; MapStruct API hay `@ConfigurationProperties` được import chính xác.
3. **Kiểm tra processor path:** Maven `annotationProcessorPaths`; Gradle `annotationProcessor`. Không chỉ nhìn `implementation`/runtime dependencies.
4. **Chạy build sạch:** `mvn clean verify` hoặc `./gradlew clean build` và đọc lỗi sớm nhất trong compiler log.
5. **Xem hai đầu ra khác nhau:** `.java` MapStruct và `spring-configuration-metadata.json`; đừng kết luận processor hỏng chỉ vì không có một tệp mà nó không có trách nhiệm tạo.
6. **Xem compiled class và JAR:** `...CustomerMapperImpl.class` trong classes/Boot JAR; nếu source tồn tại nhưng class không có, kiểm tra bước compile/source roots.
7. **Chạy test tích hợp hoặc smoke test:** Spring có inject mapper? HTTP response có đúng? Property binding có đúng?
8. **Đối chiếu CI và IDE:** khi CLI pass nhưng IDE fail, sửa tích hợp IDE/source path; khi CLI fail, sửa build model/processors.

## 11. Bài tập tự kiểm tra

**Tình huống A.** Maven project dùng `@Mapper` nhưng chỉ khai báo `org.mapstruct:mapstruct` trong `<dependencies>`. Có chắc sinh `CustomerMapperImpl.java` không?

*Đáp án:* Không. `@Mapper` chỉ là annotation API; phải cung cấp MapStruct processor trên annotation processor path, bảo đảm processing được bật và compiler chạy thành công.

**Tình huống B.** Có `spring-boot-configuration-processor`, nhưng không thấy `CustomerSettingsImpl.java`. Processor hỏng?

*Đáp án:* Không. Configuration processor không có nhiệm vụ tạo Java implementation cho record; nó sinh metadata JSON như `META-INF/spring-configuration-metadata.json`. `CustomerSettings` vẫn là record do lập trình viên khai báo.

**Tình huống C.** Build Java 17 trước đây tự phát hiện processor từ classpath; chuyển JDK 23 thì tệp generated biến mất. Phải sửa gì?

*Đáp án:* Khai báo processor path tường minh ở Maven Compiler Plugin hoặc Gradle `annotationProcessor`. JDK 23 thay đổi mặc định implicit annotation processing; kiểm tra compiler options trước khi thử chỉnh source code.

**Tình huống D.** `target/generated-sources/annotations/CustomerMapperImpl.java` đã có, vậy nên commit nó vào Git để production khỏi sinh lại?

*Đáp án:* Không phải cách làm mặc định. Commit source gốc và processor/build configuration, để CI tái sinh nguồn rồi compile; kiểm soát phiên bản và test. Chỉ commit generated artifacts nếu có chính sách rõ ràng.

**Tình huống E.** Tại sao `spring-configuration-metadata.json` có thể nằm trong JAR dù không có `.java` tương ứng?

*Đáp án:* Annotation processor có thể sinh **resource** qua compiler, không nhất thiết sinh source Java. Spring Boot configuration processor dùng JSON metadata để hỗ trợ công cụ/IDE.

**Tình huống F.** `@ConfigurationProperties` binding chạy bình thường nhưng IDE không gợi ý `demo.message`. Nên kiểm tra hướng nào?

*Đáp án:* Kiểm tra metadata processor, tệp JSON sau compile và IDE indexing. Đừng sửa logic runtime binding nếu runtime đã đúng.

**Tình huống G.** Dự án vừa dùng Lombok vừa dùng MapStruct. Lỗi getter không tồn tại khiến mapper fail. Chỉ tăng Spring Boot version có giải quyết chắc chắn không?

*Đáp án:* Không. Cần kiểm tra hỗ trợ MapStruct + Lombok, đường processor và binding integration tương ứng; việc nâng Boot không tự sửa mọi tương tác của annotation processors.

## 12. Checklist trước khi chấp nhận artifact

- Source và build model đã version hóa; processor API và processor implementation được khai báo **đúng classpath**.
- Processor versions, JDK/toolchain và Maven/Gradle plugin versions được xác định rõ.
- Build sạch chạy thành công; generated Java xuất hiện ở thư mục output đúng; metadata JSON xuất hiện nếu module có processor tạo metadata.
- Generated Java đã được biên dịch thành `.class`, và các lớp/resources cần thiết xuất hiện trong artifact.
- Test Spring Boot thực sự sử dụng mapper bean và property binding đạt; không chỉ kiểm tra có file.
- Generated files có owner rõ (thường build-owned) và không bị sửa tay; CI có thể tái tạo kết quả từ source và dependencies.
- Không để compiler tùy tiện chạy processor chưa được duyệt từ dependency graph; kiểm soát artifact supply chain như với build plugins.

**Điểm nhớ quan trọng:** Annotation processor là công cụ **build-time** chạy cùng compiler, có thể tạo **Java source** hoặc **metadata resources**. Hãy đặt API trên compile classpath, đặt processor trên processor path, kiểm tra đầu ra trong generated-sources/classes và xác minh behavior trong artifact. Đối với Spring Boot, MapStruct sinh mapper implementation; `spring-boot-configuration-processor` sinh metadata hỗ trợ IDE và không thay thế property binding lúc ứng dụng chạy.

### Tài liệu tham khảo

- Java `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Apache Maven Compiler Plugin 3.13.0 — `compiler:compile` và `annotationProcessorPaths`: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html
- MapStruct 1.6 — Reference Guide: https://mapstruct.org/documentation/1.6/reference/html/
- Spring Boot — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Gradle — Java Library Plugin/Declaring an Annotation Processor: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Oracle JDK 23 release notes — Annotation processing default: https://www.oracle.com/java/technologies/javase/23-relnote-issues.html