# Đóng gói autoconfigure cùng starter và dùng từ dự án Spring Boot độc lập

## 1. Mục tiêu và kết quả cần đạt

Một thư viện Java có thể chạy tốt trong repository của chính nó nhưng người dùng vẫn gặp khó khăn khi tích hợp vào một ứng dụng Spring Boot khác. Họ phải tự thêm nhiều dependency, tự khai báo bean, tự nhớ cấu hình mặc định và tự xử lý các phiên bản tương thích.

Spring Boot starter giải quyết trải nghiệm đó bằng một dependency có chủ đích: ứng dụng chỉ cần khai báo starter của thư viện, còn starter kéo theo thư viện lõi, module auto-configuration và các dependency nền tảng cần thiết.

Bài này xây dựng thư viện ví dụ tên `Acme Widget`, đóng gói thành ba artifact:

- `acme-widget-client`: thư viện Java lõi, chứa `WidgetClient`.
- `acme-widget-spring-boot-autoconfigure`: chứa `@AutoConfiguration`, properties và resource đăng ký auto-configuration.
- `acme-widget-spring-boot-starter`: artifact tổng hợp dependency để ứng dụng bắt đầu sử dụng thư viện.

Sau đó tạo một dự án consumer độc lập nằm ngoài multi-module build, publish artifact vào Maven local repository, thêm đúng một dependency starter và chạy ứng dụng để xác nhận auto-configuration được khám phá từ JAR.

**Kết quả cuối:** consumer chỉ khai báo `com.acme:acme-widget-spring-boot-starter`; Spring Boot tự tìm `WidgetClientAutoConfiguration`, bind cấu hình `acme.widget.*` và tạo `WidgetClient` mặc định.

## 2. Phân biệt thư viện lõi, autoconfigure và starter

| Artifact | Trách nhiệm | Có cần chứa Java class không? |
| --- | --- | --- |
| `acme-widget-client` | API và implementation độc lập với Spring Boot | Có |
| `acme-widget-spring-boot-autoconfigure` | Tạo bean mặc định, đọc properties, conditions, customizer và descriptor imports | Có |
| `acme-widget-spring-boot-starter` | Gom các dependency thường cần để sử dụng thư viện | Thường không |

Module autoconfigure là phần tích hợp Spring. Nó biết cách biến properties và các dependency có mặt thành bean trong ApplicationContext.

Starter là một artifact định hướng dependency. Nó thường là JAR gần như rỗng về code; giá trị chính nằm ở POM khai báo dependency đến module autoconfigure, thư viện lõi và `spring-boot-starter`. Vì vậy, khi kiểm tra JAR starter, không thấy class auto-configuration là điều bình thường. Class và resource imports nằm trong JAR autoconfigure.

Có thể gộp hai module nếu thư viện nhỏ, không có feature tùy chọn và không cần người dùng tự xây starter khác. Tách riêng có lợi khi thư viện có nhiều flavor, tích hợp web/reactive hoặc dependency chỉ cần ở một số ứng dụng.

## 3. Luồng từ source code đến ứng dụng consumer

~~~mermaid
flowchart TD
    A["acme-widget-client<br/>WidgetClient"] --> B["acme-widget-spring-boot-autoconfigure<br/>AutoConfiguration + properties + imports"]
    B --> C["acme-widget-spring-boot-starter<br/>Dependency aggregator"]
    A --> C
    D["Consumer project độc lập"] --> C
    C --> E["Maven/Gradle resolve dependency graph"]
    E --> F["Spring Boot đọc AutoConfiguration.imports"]
    F --> G["WidgetClientAutoConfiguration"]
    G --> H["Bind acme.widget.*"]
    H --> I["Tạo WidgetClient nếu chưa có bean tùy chỉnh"]
~~~

Các giai đoạn cần phân biệt:

1. **Build:** Maven/Gradle biên dịch từng module và đóng gói JAR.
2. **Publish:** artifact và POM được đưa vào local hoặc remote Maven repository.
3. **Dependency resolution:** consumer tải starter và các dependency bắc cầu.
4. **Auto-configuration discovery:** Spring Boot đọc resource `AutoConfiguration.imports` trong JAR autoconfigure.
5. **Condition evaluation:** Boot kiểm tra classpath và bean hiện có.
6. **Bean creation:** container tạo bean theo dependency graph sau khi configuration đã được xử lý.

Starter chỉ giải quyết dependency resolution. Việc khám phá auto-configuration vẫn phụ thuộc resource imports trong đúng JAR.

## 4. Quy tắc đặt tên và phiên bản

Dùng namespace của thư viện:

- `groupId`: `com.acme`
- `artifactId` lõi: `acme-widget-client`
- `artifactId` autoconfigure: `acme-widget-spring-boot-autoconfigure`
- `artifactId` starter: `acme-widget-spring-boot-starter`

Không đặt tên module bắt đầu bằng `spring-boot-`, vì tên đó nên dành cho các module do dự án Spring Boot cung cấp. Dùng namespace riêng giúp tránh xung đột tên và thể hiện rõ chủ sở hữu artifact.

Trong ví dụ, toàn bộ thư viện dùng version `1.0.0-SNAPSHOT` và Spring Boot `3.3.13`. Consumer cũng dùng Spring Boot `3.3.13`. Với ứng dụng thật, hãy quản lý một version tương thích rõ ràng, kiểm thử trên các phiên bản Spring Boot được hỗ trợ và không để từng module tự chọn một version khác nhau của thư viện lõi.

Nếu dùng Maven BOM, khai báo `spring-boot-dependencies` trong `dependencyManagement`. BOM quản lý version; nó không tự thêm dependency vào module. Mỗi module vẫn phải khai báo những artifact mà source hoặc runtime của nó cần.

## 5. Cấu trúc repository multi-module

Tạo một thư mục repository cho thư viện:

~~~text
acme-widget/
├── pom.xml
├── acme-widget-client/
│   ├── pom.xml
│   └── src/main/java/com/acme/widget/client/
│       └── WidgetClient.java
├── acme-widget-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/acme/widget/autoconfigure/
│       │   │   ├── WidgetClientAutoConfiguration.java
│       │   │   └── WidgetClientProperties.java
│       │   └── resources/META-INF/spring/
│       │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/com/acme/widget/autoconfigure/
│           └── WidgetClientAutoConfigurationTests.java
└── acme-widget-spring-boot-starter/
    └── pom.xml
~~~

Consumer là một dự án riêng, không nằm trong danh sách modules ở root:

~~~text
workspace/
├── acme-widget/
│   └── ... thư viện multi-module ...
└── widget-consumer/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/example/consumer/
        │   │   └── ConsumerApplication.java
        │   └── resources/application.properties
        └── test/java/com/example/consumer/
            └── ConsumerApplicationTests.java
~~~

Tách consumer ra ngoài reactor là chủ ý của bài thực hành. Nó chứng minh artifact đã được đóng gói và publish đúng, thay vì chỉ hoạt động nhờ Maven reactor nhìn thấy source module bên cạnh.

## 6. Parent POM quản lý module và version

Tệp `acme-widget/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <modules>
        <module>acme-widget-client</module>
        <module>acme-widget-spring-boot-autoconfigure</module>
        <module>acme-widget-spring-boot-starter</module>
    </modules>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Root dùng packaging `pom`, vì nó là aggregator và parent. `modules` liệt kê các module con. Maven reactor đọc quan hệ dependency để xác định thứ tự build; thứ tự trong danh sách không thay thế dependency declaration.

`dependencyManagement` import BOM Spring Boot để các module dùng cùng version của `spring-boot-autoconfigure`, `spring-boot-starter` và test dependencies mà không phải lặp version ở từng POM.

## 7. Tạo thư viện lõi độc lập với Spring

Tệp `acme-widget-client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-client</artifactId>
</project>
~~~

Tệp `WidgetClient.java`:

~~~java
package com.acme.widget.client;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;

public final class WidgetClient {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final HttpClient httpClient;

    public WidgetClient(URI baseUrl, Duration connectTimeout) {
        this.baseUrl = Objects.requireNonNull(baseUrl, "baseUrl");
        this.connectTimeout = Objects.requireNonNull(
                connectTimeout, "connectTimeout");

        if (connectTimeout.isZero() || connectTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "connectTimeout must be positive");
        }

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public URI baseUrl() {
        return this.baseUrl;
    }

    public Duration connectTimeout() {
        return this.connectTimeout;
    }

    public HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        URI target = this.baseUrl.resolve(path);
        HttpRequest request = HttpRequest.newBuilder(target)
                .GET()
                .build();

        return this.httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Lớp này chỉ dùng Java 17 API, không phụ thuộc Spring. Điều đó cho phép ứng dụng Java thuần dùng thư viện lõi mà không cần Spring Boot. Module autoconfigure sẽ thêm lớp tích hợp Spring ở bước tiếp theo.
## 8. POM của module autoconfigure

Tệp `acme-widget-spring-boot-autoconfigure/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-spring-boot-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-client</artifactId>
            <version>${project.version}</version>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
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
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>${spring-boot.version}</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>${spring-boot.version}</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency `acme-widget-client` được đánh dấu optional. Module autoconfigure cần thư viện lõi để compile, nhưng việc phụ thuộc vào autoconfigure không tự động buộc mọi consumer phải kéo thư viện lõi nếu họ chỉ muốn tái sử dụng metadata hoặc tự tạo starter riêng.

Starter chuẩn sẽ khai báo thư viện lõi một cách tường minh. Đây là điểm quan trọng của Maven optional dependency: nó vẫn là dependency của chính module autoconfigure, nhưng không được truyền tự động như dependency bắc cầu cho consumer.

Hai annotation processor có vai trò riêng:
- `spring-boot-autoconfigure-processor` thu thập metadata condition của auto-configuration để Boot có thể lọc sớm các cấu hình không phù hợp.
- `spring-boot-configuration-processor` sinh `META-INF/spring-configuration-metadata.json`, hỗ trợ gợi ý và mô tả properties trong IDE.

Processor được khai báo trong `annotationProcessorPaths`, không phải dependency runtime của ứng dụng.

## 9. Định nghĩa Configuration Properties

Tệp `WidgetClientProperties.java`:

~~~java
package com.acme.widget.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.widget")
public class WidgetClientProperties {

    /**
     * Base URI used by the Widget service.
     */
    private URI baseUrl = URI.create("https://api.example.test");

    /**
     * Timeout for establishing a connection to the Widget service.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return this.baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return this.connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Dùng namespace riêng `acme.widget`. Không đặt property của thư viện vào namespace dành riêng cho Spring Boot như `spring`, `server` hoặc `management`.

Dùng `Duration` để người dùng có thể ghi đơn vị rõ ràng, ví dụ `1500ms`, `2s` hoặc `1m`. Giá trị mặc định trong class giúp thư viện có thể chạy ngay cả khi consumer không khai báo property.

## 10. Tạo AutoConfiguration và điều kiện classpath

Tệp `WidgetClientAutoConfiguration.java`:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class WidgetClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(WidgetClient.class)
    @EnableConfigurationProperties(WidgetClientProperties.class)
    static class WidgetClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        WidgetClient widgetClient(WidgetClientProperties properties) {
            return new WidgetClient(
                    properties.getBaseUrl(),
                    properties.getConnectTimeout());
        }
    }
}
~~~

Một số quyết định thiết kế trong ví dụ:

- `@AutoConfiguration` đánh dấu entry point của thư viện.
- `@ConditionalOnClass` bảo đảm phần tạo client chỉ được áp dụng khi thư viện lõi thực sự có mặt.
- Cấu hình có điều kiện được đặt trong nested `@Configuration` riêng. Cách tách này hữu ích khi method hoặc return type tham chiếu đến class của dependency tùy chọn.
- `@EnableConfigurationProperties` đăng ký properties class.
- `@ConditionalOnMissingBean` cho phép ứng dụng tự cung cấp `WidgetClient` nếu cần implementation khác.
- Method `@Bean` trả về type cụ thể `WidgetClient`, giúp condition và container có đủ thông tin về bean.

Không dùng `@ComponentScan` trong auto-configuration để tìm class của thư viện. Hãy đăng ký auto-configuration bằng imports và dùng `@Import` tường minh nếu cần cấu hình hỗ trợ khác.

## 11. Đăng ký auto-configuration bằng resource imports

Tạo đúng file:

~~~text
acme-widget-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/
        └── spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file, mỗi class một dòng:

~~~text
com.acme.widget.autoconfigure.WidgetClientAutoConfiguration
~~~

Tên trong file là fully qualified class name (FQCN), không có đuôi `.java` hoặc `.class`. File này phải được đóng gói trong JAR autoconfigure đã publish.

Với Spring Boot 3.x, đây là resource chuẩn để công bố auto-configuration candidates. `spring.factories` của các phiên bản cũ không còn là cách đăng ký `EnableAutoConfiguration` thay thế cho file này. `spring.factories` vẫn có thể còn cần cho một số extension point khác.

Không thêm class auto-configuration vào component scan của ứng dụng. Cơ chế imports là đường khám phá chính thức của module.

## 12. Tạo starter module chỉ để gom dependency

Tệp `acme-widget-spring-boot-starter/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-spring-boot-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-client</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

Starter có ba dependency:

1. `spring-boot-starter`: cung cấp các thành phần nền tảng Spring Boot.
2. `acme-widget-spring-boot-autoconfigure`: cung cấp auto-configuration và properties.
3. `acme-widget-client`: cung cấp implementation lõi mà auto-configuration cần.

Không cần thêm class Java vào starter. Maven vẫn tạo JAR và POM; POM là phần quan trọng vì nó mô tả dependency graph mà consumer sẽ nhận.

Không đưa mọi integration tùy chọn vào starter mặc định. Nếu thư viện có module web, reactive hoặc database chỉ một số ứng dụng cần, hãy tạo starter riêng cho từng flavor hoặc ghi rõ dependency bổ sung để tránh kéo quá nhiều thư viện không sử dụng.

## 13. Build và test các module trong repository

Từ thư mục `acme-widget`, chạy:

~~~bash
mvn clean verify
~~~

`verify` chạy các phase trước đó, bao gồm compile, test và package. Nếu các module build thành công, tiếp tục cài vào local repository:

~~~bash
mvn clean install
~~~

Maven reactor build các module trong cùng lượt. Vì starter phụ thuộc autoconfigure và client, Maven xác định thứ tự build dựa trên dependency graph.

Nếu chỉ muốn build starter cùng các dependency module cần thiết:

~~~bash
mvn -pl acme-widget-spring-boot-starter -am clean install
~~~

Tùy chọn `-pl` chọn project; `-am` yêu cầu Maven cũng build các project mà project đó phụ thuộc. Với multi-module library, đây là cách hữu ích để publish một starter cùng các artifact nội bộ của nó.

## 14. Kiểm tra nội dung JAR sau khi build

Kiểm tra JAR autoconfigure:

~~~bash
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar
~~~

Danh sách cần có các entry tương tự:

~~~text
com/acme/widget/autoconfigure/WidgetClientAutoConfiguration.class
com/acme/widget/autoconfigure/WidgetClientProperties.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

Hai file metadata có thể phụ thuộc việc annotation processor tìm thấy metadata cần sinh. Hãy kiểm tra file thực tế sau build; không giả định rằng chỉ khai báo processor là bảo đảm mọi property đều có mô tả chính xác.

Trên Windows PowerShell, lọc resource imports:

~~~powershell
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    Select-String "AutoConfiguration.imports"
~~~

Trên macOS/Linux:

~~~bash
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    grep "AutoConfiguration.imports"
~~~

Để đọc nội dung resource từ JAR, có thể giải nén vào thư mục tạm:

~~~bash
mkdir inspect-autoconfigure
cd inspect-autoconfigure
jar xf ../acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mở file vừa giải nén và xác nhận FQCN khớp hoàn toàn với class đã biên dịch. Nếu file có trong source nhưng không có trong JAR, kiểm tra vị trí resource, cấu hình includes/excludes và source set của module.

Kiểm tra JAR starter riêng:

~~~bash
jar tf acme-widget-spring-boot-starter/target/acme-widget-spring-boot-starter-1.0.0-SNAPSHOT.jar
~~~

Starter có thể chỉ chứa `META-INF/MANIFEST.MF` và metadata JAR cơ bản. Đó là kết quả bình thường; class và imports thuộc JAR autoconfigure.
## 15. Kiểm thử descriptor và auto-configuration trong module

Thêm test `WidgetClientAutoConfigurationTests.java`:

~~~java
package com.acme.widget.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.widget.client.WidgetClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WidgetClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WidgetClientAutoConfiguration.class));

    @Test
    void descriptorContainsAutoConfigurationClass() {
        ImportCandidates candidates = ImportCandidates.load(
                AutoConfiguration.class, getClass().getClassLoader());

        assertThat(candidates.getCandidates())
                .contains(WidgetClientAutoConfiguration.class.getName());
    }

    @Test
    void createsClientFromProperties() {
        this.runner
                .withPropertyValues(
                        "acme.widget.base-url=https://test.example.test",
                        "acme.widget.connect-timeout=750ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);

                    WidgetClient client = context.getBean(WidgetClient.class);
                    assertThat(client.baseUrl())
                            .isEqualTo(URI.create("https://test.example.test"));
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofMillis(750));
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnClient() {
        this.runner
                .withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);
                    assertThat(context.getBean(WidgetClient.class).baseUrl())
                            .isEqualTo(URI.create("https://custom.example.test"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        WidgetClient customWidgetClient() {
            return new WidgetClient(
                    URI.create("https://custom.example.test"),
                    Duration.ofSeconds(1));
        }
    }
}
~~~

Test `descriptorContainsAutoConfigurationClass` xác minh resource imports có candidate đúng. Hai test còn lại xác minh properties và hành vi back-off của bean mặc định.

Lưu ý quan trọng: `ApplicationContextRunner` với `AutoConfigurations.of(WidgetClientAutoConfiguration.class)` nạp class trực tiếp. Nó kiểm tra điều kiện và bean behavior nhưng không tự chứng minh starter đã mang descriptor đến ứng dụng consumer. Vì vậy cần thêm một integration test ở dự án độc lập.

## 16. Publish artifact vào Maven local repository

Từ root thư viện, chạy:

~~~bash
mvn clean install
~~~

Maven cài POM, JAR và metadata của từng module vào local repository mặc định, thường là:

~~~text
%USERPROFILE%\.m2\repository\com\acme\
~~~

Trên macOS/Linux, vị trí mặc định thường là:

~~~text
~/.m2/repository/com/acme/
~~~

Cấu trúc artifact có thể giống:

~~~text
com/acme/
├── acme-widget-parent/1.0.0-SNAPSHOT/
├── acme-widget-client/1.0.0-SNAPSHOT/
├── acme-widget-spring-boot-autoconfigure/1.0.0-SNAPSHOT/
└── acme-widget-spring-boot-starter/1.0.0-SNAPSHOT/
~~~

`mvn install` là thao tác phù hợp khi phát triển và kiểm tra trên cùng máy. Nó không publish lên Maven Central hoặc repository dùng chung của team.

Không dùng `install:install-file` cho module vừa build trong một Maven reactor bình thường. Goal đó chủ yếu dùng để cài một JAR bên ngoài không có project build/POM tương ứng. Với multi-module project, `mvn install` giữ đúng POM và dependency graph của từng module.

## 17. Tạo consumer project độc lập

Tạo thư mục `widget-consumer` bên cạnh `acme-widget`. Consumer có POM riêng và không khai báo module của thư viện trong `<modules>`.

Tệp `widget-consumer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>widget-consumer</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <acme-widget.version>1.0.0-SNAPSHOT</acme-widget.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-spring-boot-starter</artifactId>
            <version>${acme-widget.version}</version>
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

Consumer chỉ khai báo custom starter. Nó không cần khai báo riêng `spring-boot-autoconfigure` hoặc `acme-widget-client`, vì starter đã cung cấp những dependency cần thiết.

Đây là phép thử quan trọng của packaging: nếu consumer chỉ chạy được khi mở cùng reactor với source modules, nhưng không chạy được sau `mvn install`, dependency hoặc artifact metadata có thể chưa đầy đủ.

## 18. Dùng WidgetClient từ consumer mà không khai báo @Bean

Tệp `ConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.acme.widget.client.WidgetClient;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    CommandLineRunner showWidgetClient(WidgetClient widgetClient) {
        return args -> {
            System.out.println(
                    "WidgetClient baseUrl=" + widgetClient.baseUrl());
            System.out.println(
                    "connectTimeout=" + widgetClient.connectTimeout());
        };
    }
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
acme.widget.base-url=https://sandbox.example.test
acme.widget.connect-timeout=1500ms
~~~

Consumer không khai báo `@Bean WidgetClient`, cũng không `@Import(WidgetClientAutoConfiguration.class)`. Spring Boot tự đọc imports trong JAR autoconfigure, đăng ký cấu hình, bind properties và tạo bean mặc định.

Chạy từ thư mục consumer:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Stdout ứng dụng có hai dòng do `CommandLineRunner` in ra:

~~~text
WidgetClient baseUrl=https://sandbox.example.test
connectTimeout=PT1.5S
~~~

`PT1.5S` là biểu diễn ISO-8601 của `Duration.ofMillis(1500)`. Chương trình không gửi HTTP request nên có thể xác minh auto-configuration mà không cần endpoint bên ngoài đang hoạt động.

## 19. Viết integration test trong consumer

Tạo `ConsumerApplicationTests.java`:

~~~java
package com.example.consumer;

import java.net.URI;
import java.time.Duration;

import com.acme.widget.client.WidgetClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ConsumerApplicationTests {

    @Autowired
    private WidgetClient widgetClient;

    @Test
    void starterMakesWidgetClientAvailable() {
        assertThat(this.widgetClient).isNotNull();
        assertThat(this.widgetClient.baseUrl())
                .isEqualTo(URI.create("https://sandbox.example.test"));
        assertThat(this.widgetClient.connectTimeout())
                .isEqualTo(Duration.ofMillis(1500));
    }
}
~~~

Test này chạy trong ứng dụng consumer thật. Vì test không trực tiếp import `WidgetClientAutoConfiguration`, nó kiểm tra cả dependency starter, JAR autoconfigure, resource imports và property binding.

Nếu test pass nhưng chạy ứng dụng đóng gói lại fail, hãy kiểm tra dependency tree và nội dung artifact được deploy.

## 20. Kiểm tra dependency graph của consumer

Từ `widget-consumer`, chạy:

~~~bash
mvn dependency:tree -Dincludes=com.acme
~~~

Cây dependency phải thể hiện tối thiểu:

~~~text
com.example:widget-consumer
\- com.acme:acme-widget-spring-boot-starter
   +- com.acme:acme-widget-spring-boot-autoconfigure
   \- com.acme:acme-widget-client
~~~

Nếu `acme-widget-client` không xuất hiện, kiểm tra POM starter. Nếu autoconfigure không xuất hiện, consumer có thể đã khai báo nhầm artifactId hoặc version. Nếu Maven không tìm được artifact, xác nhận `mvn install` đã chạy thành công và version trong consumer khớp version đã cài.

Có thể yêu cầu Maven cập nhật metadata khi dùng remote repository:

~~~bash
mvn -U clean test
~~~

Với local repository, `-U` không thay thế bước cài artifact mới. Khi source thay đổi, hãy chạy lại `mvn install` từ root thư viện trước khi test consumer.

## 21. Publish lên remote Maven repository

Khi muốn chia sẻ artifact với team hoặc CI, publish lên repository manager như Nexus, Artifactory hoặc GitHub Packages. Khai báo `distributionManagement` trong POM parent hoặc cấu hình theo chuẩn repository của tổ chức:

~~~xml
<distributionManagement>
    <repository>
        <id>acme-releases</id>
        <url>https://repo.example.test/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>acme-snapshots</id>
        <url>https://repo.example.test/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đặt thông tin đăng nhập trong Maven `settings.xml`, dùng cùng `id` với repository:

~~~xml
<servers>
    <server>
        <id>acme-releases</id>
        <username>YOUR_USERNAME</username>
        <password>YOUR_TOKEN</password>
    </server>
    <server>
        <id>acme-snapshots</id>
        <username>YOUR_USERNAME</username>
        <password>YOUR_TOKEN</password>
    </server>
</servers>
~~~

Các giá trị trên là placeholder minh họa; dùng credential thực tế do tổ chức cấp và không commit token/password vào repository source.

Sau khi cấu hình repository và quyền truy cập, publish từ root:

~~~bash
mvn clean deploy
~~~

Maven chọn release repository hay snapshot repository theo version. Consumer ở máy khác cần khai báo repository tương ứng trong `pom.xml` hoặc `settings.xml`, rồi dùng version đã publish.

Đối với production, ưu tiên version release bất biến thay vì tái sử dụng cùng một version cho các nội dung artifact khác nhau. Nếu thay đổi code nhưng giữ nguyên version release, cache ở repository và máy consumer có thể khiến việc debug rất khó.
## 22. Gradle: dependency và publish tương đương

Nếu dự án dùng Gradle, vẫn giữ cùng ranh giới module. `settings.gradle.kts`:

~~~kotlin
rootProject.name = "acme-widget"

include(
    "acme-widget-client",
    "acme-widget-spring-boot-autoconfigure",
    "acme-widget-spring-boot-starter"
)
~~~

Trong module autoconfigure, dùng `java-library` để phân biệt dependency được expose với dependency chỉ cần khi compile:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

dependencies {
    api("org.springframework.boot:spring-boot-autoconfigure:3.3.13")
    compileOnly(project(":acme-widget-client"))

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor:3.3.13"
    )

    testImplementation(project(":acme-widget-client"))
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test:3.3.13"
    )
}
~~~

`compileOnly` thể hiện core client là dependency tùy chọn đối với người chỉ dùng module autoconfigure. Starter sẽ kéo core client vào runtime.

Trong starter module:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

dependencies {
    api("org.springframework.boot:spring-boot-starter:3.3.13")
    api(project(":acme-widget-spring-boot-autoconfigure"))
    api(project(":acme-widget-client"))
}
~~~

Với các module cần publish, cấu hình publication:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Sau khi áp dụng `maven-publish` và cấu hình publication cho các module cần phân phối, chạy:

~~~bash
./gradlew publishToMavenLocal
~~~

Consumer Gradle có thể khai báo repository và dependency:

~~~kotlin
repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation("com.acme:acme-widget-spring-boot-starter:1.0.0-SNAPSHOT")
}
~~~

`mavenLocal()` phù hợp để phát triển trên cùng máy. Với CI hoặc team, dùng repository dùng chung thay vì phụ thuộc vào cache local của từng developer. Cần quản lý Spring Boot BOM/plugin thống nhất để version dependency không bị lệch giữa module và consumer.

## 23. Các điểm tương thích và thiết kế cần review

**Auto-configuration phải có điều kiện phù hợp.** Dùng `@ConditionalOnClass` cho integration phụ thuộc thư viện tùy chọn và `@ConditionalOnMissingBean` để cho phép consumer thay implementation mặc định.

**Properties phải có namespace riêng.** Dùng `acme.widget.*`; ghi Javadoc cho từng property để configuration processor sinh metadata hữu ích.

**Dependency optional phải có chủ đích.** Nếu autoconfigure khai báo thư viện lõi optional, starter phải kéo thư viện lõi vào. Đừng giả định dependency optional sẽ tự truyền xuống consumer.

**Không quên core Spring Boot starter.** Starter tùy chỉnh nên tham chiếu `spring-boot-starter` trực tiếp hoặc gián tiếp, để consumer chỉ thêm starter riêng vẫn có nền tảng Spring Boot cần thiết.

**Không để auto-configuration phụ thuộc component scan.** Đăng ký qua `AutoConfiguration.imports`; dùng `@Import` cho các configuration class hỗ trợ.

**Giữ version đồng bộ.** Các module cùng một release của thư viện phải dùng cùng version. Spring Boot version nên được quản lý bằng BOM hoặc dependency management.

**Kiểm tra JAR, không chỉ source tree.** Resource imports có thể tồn tại trong source nhưng bị exclude khi package. Consumer độc lập mới xác nhận được artifact đã publish đủ.

**Không nhầm build với publish.** `verify` kiểm tra build; `install` đưa artifact vào local repository; `deploy` publish tới remote repository.

## 24. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Consumer không tìm thấy starter | Chưa `mvn install` hoặc chưa publish remote | Kiểm tra version và local/remote repository |
| Consumer tìm thấy starter nhưng không có `WidgetClient` | Starter thiếu dependency autoconfigure hoặc core client | Kiểm tra POM starter và `dependency:tree` |
| JAR autoconfigure không có imports | Resource đặt sai thư mục hoặc bị exclude | Đặt dưới `src/main/resources/META-INF/spring` rồi kiểm tra `jar tf` |
| Imports có nhưng auto-configuration không chạy | FQCN sai hoặc class không có trong JAR | So sánh entry imports với class path và package |
| Consumer phải `@Import` auto-configuration mới chạy | Descriptor không được publish hoặc dependency không chứa đúng JAR | Kiểm tra JAR autoconfigure và runtime classpath |
| `WidgetClient` không có trên runtime classpath | Core dependency trong autoconfigure là optional và starter quên thêm core | Khai báo core client trong starter |
| Auto-configuration không tạo bean | `@ConditionalOnClass`, property hoặc `@ConditionalOnMissingBean` không khớp | Bật debug và đọc Condition Evaluation Report |
| Property không được bind | Thiếu `@EnableConfigurationProperties` hoặc sai prefix | Kiểm tra properties class và `acme.widget.*` |
| IDE không gợi ý properties | Thiếu configuration processor hoặc Javadoc | Kiểm tra `spring-configuration-metadata.json` |
| Test module pass nhưng consumer fail | Test nạp auto-configuration trực tiếp, không đi qua starter | Thêm integration test ở dự án consumer độc lập |
| Consumer nhận artifact cũ | Version snapshot/release và local cache không khớp | Build/install lại, kiểm tra version và dependency tree |
| Starter JAR không có class | Nhầm trách nhiệm starter với autoconfigure | Kiểm tra class/resource trong JAR autoconfigure; starter chủ yếu là dependency aggregator |
| CI không resolve artifact | Artifact chỉ có trong Maven local của developer | Publish lên remote repository dùng chung |
| Dependency version bị lệch | Module tự khai báo version khác nhau | Dùng BOM và version property chung |

## 25. Checklist phát hành và tích hợp

1. Xác nhận core library có thể dùng độc lập và không phụ thuộc Spring nếu không cần.
2. Xác nhận module autoconfigure chứa properties, configuration và customizer API cần công khai.
3. Xác nhận dependency thư viện lõi được đánh dấu optional đúng mục đích.
4. Xác nhận `spring-boot-autoconfigure` có trong dependency runtime của module autoconfigure.
5. Xác nhận annotation processors được cấu hình cho metadata condition và configuration properties.
6. Xác nhận resource `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` liệt kê đúng FQCN.
7. Xác nhận starter khai báo core library, autoconfigure và `spring-boot-starter`.
8. Chạy `mvn clean verify` và test auto-configuration.
9. Chạy `mvn clean install` hoặc `mvn deploy` theo môi trường phân phối.
10. Dùng `jar tf` kiểm tra JAR autoconfigure và POM dependency của starter.
11. Tạo consumer ngoài reactor, chỉ thêm dependency starter.
12. Chạy integration test và ứng dụng consumer; xác nhận bean và properties.
13. Kiểm tra dependency tree, version và repository resolution.
14. Phát hành release bất biến, cập nhật tài liệu cấu hình và ví dụ consumer.

## 26. Tự kiểm tra kiến thức

1. Module autoconfigure chứa nội dung gì? **Auto-configuration classes, properties, customizer contracts và resource imports.**
2. Starter thường chứa gì? **POM dependency aggregator và một JAR không cần Java class.**
3. Resource nào đăng ký auto-configuration trong Spring Boot 3.x? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.**
4. Mỗi dòng trong imports chứa gì? **FQCN của một auto-configuration class.**
5. Vì sao starter phải khai báo core library nếu autoconfigure đánh dấu dependency đó optional? **Optional dependency không được truyền tự động cho consumer.**
6. `spring-boot-autoconfigure-processor` dùng để làm gì? **Sinh metadata condition để lọc auto-configuration sớm.**
7. `spring-boot-configuration-processor` tạo metadata nào? **`META-INF/spring-configuration-metadata.json`.**
8. `mvn verify` khác `mvn install` thế nào? **Verify chạy kiểm tra build; install còn cài artifact vào local Maven repository.**
9. `mvn deploy` dùng khi nào? **Publish artifact đến remote repository đã cấu hình.**
10. Vì sao test `ApplicationContextRunner` chưa đủ để chứng minh starter hoạt động? **Nó có thể nạp class trực tiếp và bỏ qua descriptor/dependency của consumer.**
11. Vì sao cần consumer nằm ngoài Maven reactor? **Để kiểm tra artifact đã cài/publish và dependency graph thực tế.**
12. Vì sao starter JAR gần như rỗng là bình thường? **Starter chỉ gom dependency; class và imports nằm trong module autoconfigure.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): quy tắc imports, conditions, kiểm thử, module autoconfigure và starter.
- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/): cấu trúc và metadata của configuration properties.
- [Spring Boot 3.3.13 — Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html): cách sinh metadata bằng configuration processor.
- [Apache Maven Install Plugin — Usage](https://maven.apache.org/plugins/maven-install-plugin/usage.html): cài artifact vào local repository bằng `mvn install`.
- [Gradle — The Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publish Java artifacts vào Maven-compatible repositories và Maven local.
