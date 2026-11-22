# ImportCandidates và việc đọc tài nguyên từ các JAR trên classpath

> **Bối cảnh:** Spring Boot → auto-configuration → khám phá ứng viên. Bài giải thích lớp `ImportCandidates`, định dạng file `.imports`, cách class loader tìm **nhiều tài nguyên cùng đường dẫn** trong các JAR trên classpath, và những bước xảy ra **sau** khi có danh sách ứng viên. Ví dụ dùng Java 17, Maven và Spring Boot 3.5.7; các thao tác liên quan nội bộ Spring Boot có thể thay đổi ở phiên bản khác.

## 1. Câu hỏi nền tảng: Spring Boot tìm các auto-configuration ở đâu?

Giả sử một ứng dụng phụ thuộc vào:

- `spring-boot-autoconfigure.jar`: mang các cấu hình chuẩn của Spring Boot;
- `alpha-autoconfigure.jar`: mang cấu hình cho thư viện Alpha;
- `beta-autoconfigure.jar`: mang cấu hình cho thư viện Beta.

Cả ba JAR có thể chứa một tài nguyên **trùng tên đường dẫn**:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi tài nguyên là một file text với các **tên class đầy đủ** của những auto-configuration do JAR đó đóng góp:

```text
# Một tài nguyên imports do thư viện Alpha cung cấp
dev.sample.alpha.AlphaAutoConfiguration
```

```text
# Một tài nguyên imports khác do thư viện Beta cung cấp
dev.sample.beta.BetaAutoConfiguration
```

Spring Boot không chỉ đọc một file duy nhất của ứng dụng rồi bỏ qua những file cùng tên trong JAR dependency. Nó có thể thu thập các file imports **từ mọi classpath root/JAR có liên quan**, ghép danh sách các ứng viên và tiếp tục lọc, sắp xếp, đánh giá điều kiện.

Một class thuộc `dev.sample.alpha` hoàn toàn có thể trở thành ứng viên dù class `@SpringBootApplication` nằm ở `dev.sample.app`. Việc tìm ứng viên auto-configuration dựa trên **resource metadata** và class loader, **không phải `@ComponentScan` của application**.

## 2. `ImportCandidates` là gì?

Lớp Spring Boot:

```java
org.springframework.boot.context.annotation.ImportCandidates
```

cung cấp API chính:

```java
public static ImportCandidates load(
    Class<?> annotation,
    ClassLoader classLoader
);
```

Đây là **chữ ký API để minh họa**, không phải method do ứng dụng tự viết. Một đối tượng `ImportCandidates` thực thi `Iterable<String>`, và `getCandidates()` trả về `List<String>`. Các phần tử là **tên class** của ứng viên; không phải các bean đã tạo và cũng không phải instance của auto-configuration.

Tài liệu API quy định quy ước đường dẫn tài nguyên:

```text
META-INF/spring/<fully-qualified-annotation-class-name>.imports
```

Trong trường hợp `AutoConfiguration.class`, đường dẫn chính xác là:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ người học có thể gọi:

```java
List<String> names = ImportCandidates
    .load(AutoConfiguration.class, getClass().getClassLoader())
    .getCandidates();
```

Đoạn mã này là **fragment minh họa**; cần import `java.util.List`, `ImportCandidates`, `AutoConfiguration` và một ngữ cảnh method có `getClass()`. Phần ví dụ Maven đầy đủ ở mục 5 sử dụng cách gọi tương đương trong một chương trình chạy được.

### Ý nghĩa của tham số `annotation`

Tham số này xác định **tên file imports cần tìm**. Nó không phải package cần scan và không yêu cầu quét toàn bộ classpath để khám phá annotation trên mọi class.

- `ImportCandidates.load(AutoConfiguration.class, loader)` tìm `.../AutoConfiguration.imports`.
- Một annotation khác dẫn đến **một tên file khác**. Nếu thư viện không cung cấp file theo tên đó, danh sách được tìm thấy có thể trống.
- `@ImportAutoConfiguration` có trường hợp dùng cơ chế imports riêng phục vụ các cấu hình được chỉ định, đặc biệt trong test; không nên nhầm đường dẫn này với danh sách auto-configuration chung.

### Ý nghĩa của tham số `classLoader`

Class loader chịu trách nhiệm tìm tài nguyên trên classpath thực tế của tiến trình. Nó có thể thấy tài nguyên ở:

- `target/classes/META-INF/spring/...` khi chạy module bằng Maven/IDE;
- gốc tài nguyên của các JAR dependency;
- các JAR lồng dưới `BOOT-INF/lib/` của Spring Boot executable JAR khi dùng class loader do Spring Boot launcher cung cấp.

Tài nguyên không cần là file vật lý dễ mở trực tiếp bằng `java.io.File`. Trong executable JAR, URL tài nguyên có thể có biểu diễn dành riêng cho nested JAR; hãy đọc thông qua class loader, `URL.openStream()` hoặc API của Spring thay vì tự cắt một chuỗi path.

## 3. Vì sao phải đọc nhiều tài nguyên cùng tên?

API Java:

```java
ClassLoader.getResource(String name)
ClassLoader.getResources(String name)
```

có hành vi khác nhau:

| API | Kết quả | Phù hợp khi nào? |
| --- | --- | --- |
| `getResource(name)` | Một `URL` hoặc `null` | Bạn chủ đích cần một tài nguyên theo thứ tự tìm kiếm của class loader. |
| `getResources(name)` | `Enumeration<URL>` của các tài nguyên tìm thấy | Khi **nhiều JAR có thể đóng góp cùng một resource path** và cần duyệt đầy đủ. |
| `ImportCandidates.load(annotation, loader)` | Các tên class ứng viên từ tài nguyên imports tương ứng | Khi cần cơ chế đọc danh sách import candidates theo quy ước của Spring Boot. |

Nếu tự viết code khám phá auto-configuration và chỉ gọi `getResource(...)`, chương trình có thể thấy một file từ JAR A nhưng **bỏ sót** file trong JAR B. Lỗi này khó phát hiện khi chạy IDE với ít dependency và chỉ xuất hiện khi đóng gói thêm starter.

Ví dụ Java chuẩn độc lập, không phụ thuộc Spring Boot, để quan sát các URL resources đang có:

```java
import java.net.URL;
import java.util.Collections;
import java.util.List;

public class ListResourceUrls {
    public static void main(String[] args) throws Exception {
        String name = "META-INF/MANIFEST.MF";
        ClassLoader loader = ListResourceUrls.class.getClassLoader();
        List<URL> urls = Collections.list(loader.getResources(name));
        System.out.println("resourceCount=" + urls.size());
        for (URL url : urls) {
            System.out.println(url);
        }
    }
}
```

Chạy bằng JDK 17:

```bash
javac ListResourceUrls.java
java ListResourceUrls
```

Các URL và tổng số resource **phụ thuộc vào classpath**, vì vậy bài không bịa một stdout cố định. Ví dụ chỉ cho thấy cách chuyển `Enumeration<URL>` thành `List<URL>` rồi duyệt toàn bộ.

Spring Boot dựa trên quy ước imports để đọc tên class; trong các phiên bản Boot khác nhau, chi tiết nội bộ thực thi có thể được tối ưu hoặc thay đổi. Điều quan trọng về mặt kiến trúc là **một classpath có thể chứa nhiều file cùng đường dẫn**, và mọi đóng góp đúng định dạng cần được xét.

## 4. Định dạng và quy tắc của file `.imports`

Đường dẫn chính xác khi phát hành một auto-configuration:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Quy tắc:

1. Ghi **tên class đầy đủ** gồm package, một tên trên một dòng.
2. Dòng bắt đầu với ký tự `#` có thể dùng làm chú thích.
3. Không dùng tên package dạng wildcard `dev.sample.autoconfigure.*`; Boot cần tên class cụ thể.
4. Đường dẫn resource phải chính xác, kể cả chữ hoa/chữ thường và đuôi `.imports`.
5. Lớp được khai báo thông thường là `@AutoConfiguration` và nằm trong package tách biệt, không được component scan tình cờ nạp.
6. Một thư viện có hai cấu hình thì liệt kê hai dòng; các JAR khác có thể có file **cùng đường dẫn** của riêng chúng.

Ví dụ:

```text
# Client integrations
com.acme.payment.autoconfigure.PaymentAutoConfiguration
com.acme.payment.autoconfigure.PaymentMetricsAutoConfiguration
```

Dòng trong file **không thực thi class**; nó chỉ đưa tên class vào bước khám phá ứng viên. Việc class thực sự được nhập và bean có tồn tại hay không là vấn đề của **các bước sau**.

### Lưu ý khi đóng gói

Maven/Gradle thường đưa file dưới `src/main/resources` vào classpath của artifact. Với Maven JAR thông thường, resource xuất hiện ở gốc JAR:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Với Spring Boot executable JAR, class/resource của ứng dụng nằm dưới `BOOT-INF/classes/`, còn dependency JAR thường nằm dưới `BOOT-INF/lib/`. Boot launcher dựng class loader phù hợp để chương trình nhìn thấy các resource này. Không dùng quy tắc “resource bắt buộc ở filesystem path hiện tại” để kiểm tra một nested JAR.

Khi tạo thư viện autoconfigure, giữ artifact là **JAR thư viện thông thường**; chỉ module ứng dụng cần plugin repackaging để thành executable JAR.

## 5. Ví dụ chạy được: hai JAR cung cấp hai imports file

Để thấy rõ việc ghép candidates từ nhiều JAR, ta tạo một Maven reactor gồm ba module: hai **JAR thư viện** và một **ứng dụng**.

```text
candidate-demo/
├── pom.xml
├── alpha-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/sample/alpha/AlphaAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── beta-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/sample/beta/BetaAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/sample/app/CandidateApplication.java
        └── test/java/dev/sample/app/
            ├── ImportCandidatesTest.java
            └── ExcludedBetaTest.java
```

### 5.1. POM gốc (aggregator/parent)

`candidate-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.sample</groupId>
    <artifactId>candidate-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>alpha-autoconfigure</module>
        <module>beta-autoconfigure</module>
        <module>app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

Root là `packaging=pom` để Maven build các module theo thứ tự dependency.

### 5.2. Module Alpha

`alpha-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>alpha-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
```

`alpha-autoconfigure/src/main/java/dev/sample/alpha/AlphaAutoConfiguration.java`:

```java
package dev.sample.alpha;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AlphaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "alphaGreeting")
    public String alphaGreeting() {
        return "from-alpha-jar";
    }
}
```

Tạo file `alpha-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Auto-configuration provided by alpha-autoconfigure.jar
dev.sample.alpha.AlphaAutoConfiguration
```

### 5.3. Module Beta

`beta-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>beta-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
```

`beta-autoconfigure/src/main/java/dev/sample/beta/BetaAutoConfiguration.java`:

```java
package dev.sample.beta;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class BetaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "betaGreeting")
    public String betaGreeting() {
        return "from-beta-jar";
    }
}
```

Tạo file `beta-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Auto-configuration provided by beta-autoconfigure.jar
dev.sample.beta.BetaAutoConfiguration
```

Hai module này là **JAR thường** vì không khai báo `spring-boot-maven-plugin` để repackage, trong khi module ứng dụng sẽ có plugin đó.

### 5.4. Module ứng dụng và hai dependency

`app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.sample</groupId>
            <artifactId>alpha-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>dev.sample</groupId>
            <artifactId>beta-autoconfigure</artifactId>
            <version>1.0.0</version>
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
</project>
```

### 5.5. Đọc ứng viên bằng `ImportCandidates` và `ClassLoader.getResources`

`app/src/main/java/dev/sample/app/CandidateApplication.java`:

```java
package dev.sample.app;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CandidateApplication {

    private static final String IMPORTS_PATH =
        "META-INF/spring/"
        + "org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    public static void main(String[] args) throws Exception {
        ClassLoader loader = CandidateApplication.class.getClassLoader();

        List<URL> resources =
            Collections.list(loader.getResources(IMPORTS_PATH));

        List<String> demoCandidates = ImportCandidates
            .load(AutoConfiguration.class, loader)
            .getCandidates()
            .stream()
            .filter(name -> name.startsWith("dev.sample."))
            .distinct()
            .sorted()
            .toList();

        try (ConfigurableApplicationContext context =
                 SpringApplication.run(CandidateApplication.class, args)) {

            System.out.println("imports.multiple=" + (resources.size() >= 2));
            System.out.println(
                "candidates=" + String.join(",", demoCandidates)
            );
            System.out.println(
                "alpha.bean=" + context.getBean("alphaGreeting", String.class)
            );
            System.out.println(
                "beta.bean=" + context.getBean("betaGreeting", String.class)
            );
        }
    }
}
```

Giải thích từng phần:

- `loader.getResources(IMPORTS_PATH)` tìm **các URL resource** có đúng tên đường dẫn trên classpath. Ví dụ có resource của Boot và ít nhất hai module thư viện; dòng `imports.multiple` sẽ in `true` khi module được build/đóng gói đúng.
- `ImportCandidates.load(AutoConfiguration.class, loader)` đọc **tên class** từ những resources hợp lệ. Do `spring-boot-autoconfigure.jar` cũng đóng góp nhiều ứng viên, code lọc `dev.sample.` để output chỉ hiển thị hai lớp do ví dụ tạo.
- `distinct().sorted()` chỉ giúp **hiển thị** dễ kiểm chứng. Đây không phải cách áp đặt thứ tự xử lý auto-configuration trong Spring Boot.
- Sau đó, `SpringApplication.run(...)` mới tạo context. `getBean(...)` kiểm tra bean thực tế, một bước khác với việc đọc danh sách candidate.

Build và chạy tại thư mục gốc `candidate-demo/`:

```bash
mvn -q clean package
java -jar app/target/app-1.0.0.jar
```

Bỏ qua log Spring Boot và thứ tự log, bốn dòng do ứng dụng in ra là:

```text
imports.multiple=true
candidates=dev.sample.alpha.AlphaAutoConfiguration,dev.sample.beta.BetaAutoConfiguration
alpha.bean=from-alpha-jar
beta.bean=from-beta-jar
```

**Tại sao kết quả đáng chú ý?**

- `CandidateApplication` nằm ở `dev.sample.app`.
- Hai class `AlphaAutoConfiguration`/`BetaAutoConfiguration` ở các package **anh em** `dev.sample.alpha` và `dev.sample.beta`, đều **ngoài phạm vi component scan mặc định**.
- Chúng vẫn được xét qua file imports trong hai JAR.
- Mỗi auto-configuration có một bean method nên, khi không bị exclude và không có bean tên trùng, context có hai bean `String` tên khác nhau. Trong ví dụ luôn lookup **theo tên**, tránh nhầm giữa hai bean cùng kiểu.

Không nên suy ra từ hai dòng `candidates=...` rằng bean đã sẵn sàng: chỉ kết luận có bean sau khi context khởi động và kiểm tra `alpha.bean`/`beta.bean`.

## 6. Kiểm thử: tài nguyên có thật và candidate khác với bean đã kích hoạt

### 6.1. Test nhìn thấy hai JAR và bean thực

`app/src/test/java/dev/sample/app/ImportCandidatesTest.java`:

```java
package dev.sample.app;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = CandidateApplication.class)
class ImportCandidatesTest {

    @Autowired
    ApplicationContext context;

    @Test
    void seesImportsAcrossMultipleJars() throws Exception {
        ClassLoader loader = CandidateApplication.class.getClassLoader();
        String path =
            "META-INF/spring/"
            + "org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        List<URL> resources =
            Collections.list(loader.getResources(path));

        List<String> names =
            ImportCandidates.load(AutoConfiguration.class, loader)
                .getCandidates();

        assertThat(resources).hasSizeGreaterThanOrEqualTo(2);
        assertThat(names).contains(
            "dev.sample.alpha.AlphaAutoConfiguration",
            "dev.sample.beta.BetaAutoConfiguration"
        );
        assertThat(context.getBean("alphaGreeting", String.class))
            .isEqualTo("from-alpha-jar");
        assertThat(context.getBean("betaGreeting", String.class))
            .isEqualTo("from-beta-jar");
    }
}
```

### 6.2. Test chứng minh “được khám phá” chưa chắc “được kích hoạt”

`app/src/test/java/dev/sample/app/ExcludedBetaTest.java`:

```java
package dev.sample.app;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = CandidateApplication.class,
    properties = "spring.autoconfigure.exclude="
        + "dev.sample.beta.BetaAutoConfiguration"
)
class ExcludedBetaTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoveryCanIncludeAnExcludedCandidate() {
        List<String> candidateNames =
            ImportCandidates.load(
                AutoConfiguration.class,
                CandidateApplication.class.getClassLoader()
            ).getCandidates();

        assertThat(candidateNames)
            .contains("dev.sample.beta.BetaAutoConfiguration");
        assertThat(context.containsBean("alphaGreeting")).isTrue();
        assertThat(context.containsBean("betaGreeting")).isFalse();
    }
}
```

Chạy cả hai test:

```bash
mvn -q test
```

Nếu cấu trúc và file imports đúng, hai test sẽ pass. Test thứ hai đặc biệt quan trọng:

- `ImportCandidates.load(...)` **vẫn thấy** `BetaAutoConfiguration` vì file imports nằm trong JAR trên classpath.
- `spring.autoconfigure.exclude` khiến Spring Boot **loại ứng viên khỏi tập auto-configuration được áp dụng**.
- Context không có `betaGreeting`, dù candidate list vẫn có tên class.
- Component scan mặc định không hề thay đổi.

Hai class test sử dụng `@SpringBootTest`, không khai báo các class `@Configuration` lồng bên trong package của app, vì thế tránh việc cấu hình test bị component scan vô tình nạp vào test còn lại.

## 7. Trình tự từ import candidates đến auto-configuration thực sự

Sơ đồ thể hiện các bước theo ý nghĩa nghiệp vụ; một số bước nội bộ như metadata filtering có thể được tối ưu theo phiên bản:

```text
Ứng dụng bật @EnableAutoConfiguration
        |
        v
AutoConfigurationImportSelector
        |
        v
ImportCandidates.load(AutoConfiguration.class, ClassLoader)
        |
        v
Đọc các AutoConfiguration.imports từ JAR/classpath roots
        |
        v
Danh sách tên class ứng viên (có thể từ nhiều JAR)
        |
        +--> loại trùng tên class theo quá trình chọn ứng viên
        |
        +--> loại auto-configuration bị exclude
        |
        +--> áp dụng filtering dựa trên metadata/điều kiện
        |
        +--> áp dụng thứ tự auto-configuration
        |
        v
Các cấu hình được import vào quá trình xử lý bean definitions
        |
        v
Đánh giá điều kiện còn lại ở cấp class và @Bean
        |
        v
Chỉ các bean đủ điều kiện mới được đăng ký
```

### Không đánh đồng bốn trạng thái

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Classpath resource found** | Có thể tìm thấy file imports | `getResources(...)` cho thấy URL từ JAR Alpha. |
| **Candidate discovered** | Tên class xuất hiện trong danh sách `ImportCandidates` | `dev.sample.alpha.AlphaAutoConfiguration`. |
| **Auto-configuration considered/selected** | Qua bước loại trừ, filtering và import | Alpha không bị exclude, các điều kiện ban đầu phù hợp. |
| **Bean registered** | Method `@Bean`/cấu hình đáp ứng điều kiện thực tế | Có bean `alphaGreeting` nếu chưa có bean tên trùng. |

`@ConditionalOnMissingBean` có thể làm bean mặc định **back off** dù class auto-configuration đã được nhập. `@ConditionalOnClass` có thể làm một candidate không đủ điều kiện khi thiếu thư viện. `@ConditionalOnProperty` còn có thể tắt cấu hình theo cấu hình runtime.

Ngoài ra, **thứ tự tên class trong các file imports không phải cơ chế quy định thứ tự khởi tạo bean**. Nếu cần tương quan giữa các auto-configuration, dùng thuộc tính `before`/`after` của `@AutoConfiguration` hoặc `@AutoConfigureOrder` khi phù hợp. Thứ tự tạo instance bean vẫn chủ yếu phụ thuộc quan hệ dependency và `@DependsOn`.

## 8. Các tình huống classpath khác nhau

### 8.1. Chạy bằng Maven trong IDE

Trong development, các module có thể hiện diện dưới dạng thư mục `target/classes` hoặc các JAR trong Maven local repository. Class loader vẫn có thể tìm resource theo cùng đường dẫn. Nếu IDE chưa đánh dấu `src/main/resources` là resources root, file imports có thể không được copy vào output — candidates sẽ thiếu.

### 8.2. Chạy JAR đóng gói bởi Spring Boot plugin

Các dependency thông thường có thể được đặt dưới `BOOT-INF/lib/` trong executable JAR. Đây **không phải** một classpath thường dạng các file rời khi nhìn bằng file explorer. Spring Boot launcher xây dựng class loader hiểu layout đó, nên mã `getResources(...)` và `ImportCandidates.load(...)` vẫn hoạt động.

Không tự biến `URL` tài nguyên thành `Path.of(url.toURI())` rồi giả định mọi URL đều trỏ đến file vật lý; với nested JAR cách làm này không đáng tin.

### 8.3. Shaded/uber JAR không giữ nhiều imports resources

Một số cách đóng gói **gộp bytecode của nhiều JAR vào một JAR phẳng** có thể làm các file cùng tên đè lên nhau. Nếu file imports của Alpha bị thay bằng Beta khi shade, class loader chỉ còn thấy một resource với một danh sách, dẫn đến thiếu ứng viên.

Khi bắt buộc shade, cấu hình resource transformer để **gộp nội dung imports đúng cách**, đồng thời kiểm tra artifact cuối. Đừng mặc định transformer có sẵn sẽ xử lý file `AutoConfiguration.imports` như mong muốn; transformer cho `META-INF/services` hoặc `spring.factories` không nhất thiết tự xử lý resource path `.imports` này. Với ứng dụng Boot thông thường, ưu tiên kiểu đóng gói executable JAR giữ dependency JAR riêng.

### 8.4. Thiếu dependency ở runtime

Một module có resource imports trong compile classpath nhưng không có mặt trên runtime classpath thì Spring Boot sẽ không phát hiện ứng viên của module đó khi chạy thật. Xem lại dependency scope, optional dependency, cấu hình đóng gói, Maven profile và class loader khác nhau giữa IDE/test/production.

### 8.5. Nhiều class loader

Application server, plugin system hoặc class loader tách biệt có thể có phạm vi nhìn thấy resources khác nhau. Không kết luận rằng file tồn tại trên máy là class loader của ứng dụng **chắc chắn** nhìn thấy. Chẩn đoán bằng đúng class loader mà Boot dùng để tìm ứng viên.

## 9. Cách kiểm tra file imports trong artifact

Sau khi chạy `mvn -q clean package` từ root của ví dụ:

```bash
jar tf alpha-autoconfigure/target/alpha-autoconfigure-1.0.0.jar
jar tf beta-autoconfigure/target/beta-autoconfigure-1.0.0.jar
jar tf app/target/app-1.0.0.jar
```

Trong hai JAR thư viện, cần thấy entry:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Trong executable JAR của app, tìm:

```text
BOOT-INF/lib/alpha-autoconfigure-1.0.0.jar
BOOT-INF/lib/beta-autoconfigure-1.0.0.jar
```

Lệnh `jar tf` liệt kê các entry; nó **không đọc nội dung** của file imports trong nested JAR. Để kiểm chứng tên class bên trong, mở JAR thư viện hoặc đọc classpath resources bằng code ví dụ ở trên.

Một cách kiểm tra nhẹ khác khi chạy ứng dụng:

```bash
java -jar app/target/app-1.0.0.jar --debug
```

Condition Evaluation Report của Spring Boot hữu ích khi **candidate đã được tìm thấy nhưng không tạo bean**. Nếu candidate **không xuất hiện trong imports**, cần kiểm tra file JAR/classpath trước; report không thể giải thích được một class chưa từng được đăng ký làm candidate.

## 10. So sánh với `spring.factories` và API liên quan

Spring Boot trước đây sử dụng cơ chế khai báo `EnableAutoConfiguration` trong:

```text
META-INF/spring.factories
```

Ví dụ cú pháp legacy (chỉ để nhận biết, **không phải cách khai báo auto-configuration của ví dụ Spring Boot 3.5.7**):

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.OldAutoConfiguration
```

Từ Spring Boot 2.7, cơ chế đăng ký qua `AutoConfiguration.imports` đã được giới thiệu; đối với Spring Boot 3.x, hãy dùng đường dẫn imports theo tài liệu hiện hành. Không dùng `SpringFactoriesLoader` để đọc các ứng viên auto-configuration của ví dụ mới rồi kết luận rằng nó không có gì: **hai resource format phục vụ mục đích và giai đoạn phiên bản khác nhau**.

Các tên cần phân biệt:

| Tên | Chức năng |
| --- | --- |
| `ImportCandidates` | Đọc tên candidate từ các file `META-INF/spring/<annotation>.imports`. |
| `AutoConfigurationImportSelector` | Chọn các auto-configuration được import dựa trên danh sách ứng viên, exclusion, điều kiện/filter và thứ tự. |
| `AutoConfiguration.imports` | Resource metadata khai báo tên các lớp auto-configuration. |
| `@AutoConfiguration` | Annotation đánh dấu class là auto-configuration; **không tự tạo cơ chế tìm ứng viên nếu thiếu imports**. |
| `@EnableAutoConfiguration` | Annotation kích hoạt hệ thống chọn và nhập auto-configuration; `@SpringBootApplication` bao gồm annotation này. |
| `@ComponentScan` | Quét các component ở các package đã chỉ định; không phải đường nạp chuẩn của auto-configuration. |
| `SpringFactoriesLoader` / `spring.factories` | Hệ thống metadata/factory loading khác trong hệ sinh thái Spring; không thay thế `ImportCandidates` đối với Boot 3.x auto-configuration. |

## 11. Những lỗi hay gặp

**Lỗi A — Chỉ dùng `getResource(...)`, bỏ sót JAR khác.** Dùng `getResources(...)` nếu cần quan sát tất cả resource có cùng path, hoặc dùng trực tiếp `ImportCandidates` để đọc danh sách candidate.

**Lỗi B — Đặt file imports sai thư mục.** File dưới `src/main/java` không mặc nhiên là resource runtime. Hãy dùng `src/main/resources/META-INF/spring/...` và kiểm tra artifact đã đóng gói.

**Lỗi C — Đặt sai tên annotation trong resource path.** Với Boot 3.5, file auto-configuration chung có tên `org.springframework.boot.autoconfigure.AutoConfiguration.imports`, không phải `EnableAutoConfiguration.imports`. Cần phân biệt annotation kích hoạt (`@EnableAutoConfiguration`) và annotation đánh dấu các class candidate (`@AutoConfiguration`).

**Lỗi D — Chỉ có `@AutoConfiguration` trên class.** Không có file imports thì class không tự biến thành ứng viên khi phụ thuộc vào JAR đó. Nó vẫn có thể được import bằng cơ chế khác, nhưng không phải auto-discovery chuẩn.

**Lỗi E — Nhầm candidate với bean.** Candidate có tên trong imports không đảm bảo điều kiện classpath/property/bean khớp. Khi nghi ngờ, kiểm tra cả danh sách candidates, exclusions và Condition Evaluation Report.

**Lỗi F — Đọc resource theo file path vật lý.** Cách chuyển `URL` thành `File` dễ hỏng khi JAR được lồng trong executable JAR hoặc môi trường cung cấp URL scheme riêng.

**Lỗi G — Shading đè mất file imports.** Kiểm tra JAR cuối cùng và cơ chế merge resource. Nếu `AlphaAutoConfiguration` biến mất khỏi danh sách candidates sau đóng gói, không nên vội thay `@ComponentScan` để chữa lỗi.

**Lỗi H — Cố sửa bằng `scanBasePackages`.** Đây là thiết lập component scan, không khôi phục resource imports bị thiếu, không tự động đưa class auto-configuration vào candidate list.

**Lỗi I — Kết luận thứ tự import theo thứ tự file.** Việc đọc tên candidate là giai đoạn khám phá; thứ tự áp dụng auto-configuration còn được Spring Boot xử lý và chịu các chỉ dẫn ordering.

## 12. Câu hỏi tự kiểm tra

1. Hai JAR có cùng resource path `AutoConfiguration.imports`, mỗi JAR liệt kê một class. Dùng `getResource(...)` có thể bỏ sót không? **Có**. `getResources(...)` phù hợp để duyệt các bản resource có cùng tên.
2. `ImportCandidates.load(AutoConfiguration.class, loader).getCandidates()` trả về bean hay tên class? **Tên class dạng `String`**.
3. Auto-configuration của thư viện nằm ngoài package `@SpringBootApplication`. Có bị bỏ qua vì `@ComponentScan` không tới không? **Không nhất thiết**; nếu tên nằm trong imports, nó có thể được xét độc lập với phạm vi scan.
4. Tên `BetaAutoConfiguration` có trong candidates nhưng bị `spring.autoconfigure.exclude` loại. Bean mặc định Beta có xuất hiện không? **Không**, vì exclusion ngăn auto-configuration đó được áp dụng.
5. Chỉ thấy `@AutoConfiguration` trên class nhưng `AutoConfiguration.imports` bị thiếu. Lỗi nằm ở đâu? **Cơ chế đăng ký ứng viên**.
6. Đường dẫn đúng trong JAR Spring Boot 3.x là gì? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**.
7. Vì sao `java.io.File` không luôn phù hợp khi đọc imports của executable JAR? **Resource có thể ở nested JAR**, được thấy qua class loader nhưng không có filesystem path thông thường.
8. File imports có hai dòng cùng tên class sẽ làm Boot tạo hai bean y hệt chứ? **Không thể suy ra như vậy**; danh sách ứng viên còn được xử lý loại trùng và chỉ có bean đủ điều kiện mới đăng ký.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 API — ImportCandidates](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/annotation/ImportCandidates.html): `load(Class, ClassLoader)` và đường dẫn resource theo annotation.
- [Spring Boot 3.5 Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): vị trí file imports, comments, kiến trúc starter và cấu hình điều kiện.
- [Spring Boot 3.5 API — AutoConfigurationImportSelector](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): cách lớp chọn ứng viên auto-configuration.
- [Spring Framework Javadoc — ClassLoader resource loading via Java SE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`/`getResources`.
- [Spring Boot Reference — Executable Jar Format](https://docs.spring.io/spring-boot/reference/executable-jar/index.html): layout `BOOT-INF/classes`/`BOOT-INF/lib` và nested JAR class loading.
