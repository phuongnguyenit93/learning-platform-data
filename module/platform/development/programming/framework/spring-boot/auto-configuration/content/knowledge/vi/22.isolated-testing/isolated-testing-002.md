# Phân biệt mô-đun API, mô-đun autoconfigure và mô-đun starter

## Mục tiêu học tập

Khi phát triển thư viện tích hợp Spring Boot, ba thành phần thường được nhắc đến là **API**, **autoconfigure** và **starter**. Chúng liên quan với nhau nhưng đảm nhận các trách nhiệm khác nhau. Nếu đặt nhầm trách nhiệm, API có thể phụ thuộc Spring Boot không cần thiết, ứng dụng phải kéo theo dependency tùy chọn, auto-configuration không được phát hiện, hoặc người dùng phải tự import cấu hình dù đã thêm starter.

Bài học này giải thích ranh giới của từng mô-đun, hướng phụ thuộc giữa chúng, cách đóng gói thành artifact, cách Spring Boot phát hiện auto-configuration và cách kiểm tra trải nghiệm của ứng dụng sử dụng thư viện.

Sau bài học, bạn có thể:

- Xác định nội dung nào thuộc API công khai, nội dung nào thuộc auto-configuration và nội dung nào thuộc starter.
- Thiết kế dependency graph một chiều, không tạo vòng phụ thuộc.
- Tổ chức Gradle multi-project hoặc Maven multi-module cho thư viện.
- Đặt AutoConfiguration.imports đúng artifact và hiểu vì sao starter thường gần như rỗng.
- Tách optional integration để core starter không kéo dependency không cần thiết.
- Kiểm thử API, điều kiện auto-configuration và trải nghiệm tiêu thụ starter.

## 1. Nhìn từ phía ứng dụng sử dụng thư viện

Giả sử một công ty phát hành thư viện Acme cung cấp client gọi dịch vụ Acme. Ứng dụng muốn thêm thư viện bằng một dependency duy nhất, cấu hình endpoint trong application.yml, rồi inject AcmeClient vào service của mình.

Người dùng kỳ vọng:

1. Có một contract Java ổn định để gọi dịch vụ.
2. Spring Boot tự đăng ký implementation mặc định khi dependency cần thiết hiện diện và feature được bật.
3. Có thể cấu hình endpoint/timeout mà không tự viết @Bean.
4. Có thể thay implementation mặc định khi muốn.
5. Chỉ phải thêm dependency cho các integration thực sự cần.

Để đáp ứng điều đó, thư viện có thể tách thành ba mô-đun:

~~~text
acme-api/
    AcmeClient.java
    AcmeRequest.java
    AcmeException.java

acme-spring-boot-autoconfigure/
    AcmeAutoConfiguration.java
    AcmeProperties.java
    DefaultAcmeClient.java
    META-INF/spring/
        org.springframework.boot.autoconfigure.AutoConfiguration.imports

acme-spring-boot-starter/
    build.gradle / pom.xml
    (chủ yếu khai báo dependency)
~~~

Luồng phụ thuộc:

~~~text
Ứng dụng Spring Boot
       |
       v
acme-spring-boot-starter
       |
       +---- spring-boot-starter
       |
       v
acme-spring-boot-autoconfigure
       |
       +---- spring-boot-autoconfigure
       |
       v
acme-api
~~~

Trong ví dụ này, starter đưa auto-configure và các dependency cần thiết vào ứng dụng; auto-configure dùng API để tạo bean mặc định; API không cần biết Spring Boot tồn tại.

**Lưu ý:** đây là kiến trúc ba mô-đun để làm rõ ranh giới. Không phải thư viện nào cũng cần tách thành ba artifact. Nếu API chỉ được dùng cùng Spring Boot, có thể đặt API trong mô-đun autoconfigure. Spring Boot cũng mô tả mô hình tối thiểu gồm một mô-đun chứa auto-configuration (có thể chứa API) và một mô-đun starter.

## 2. Mô-đun API: hợp đồng mà người dùng lập trình trực tiếp

API module chứa các kiểu mà ứng dụng hoặc integration khác cần tham chiếu khi biên dịch. Đây là **mặt công khai của thư viện**.

Nội dung thường có:

- Interface/service contract, ví dụ AcmeClient.
- Request/response model hoặc DTO.
- Exception công khai.
- Enum và kiểu giá trị.
- SPI/extension interface nếu muốn cho phép bên khác cung cấp implementation.

Ví dụ:

~~~java
package com.acme.api;

import java.net.URI;

public interface AcmeClient {
    AcmeResponse send(AcmeRequest request);
    URI endpoint();
}
~~~

Model công khai:

~~~java
package com.acme.api;

public record AcmeRequest(String message) {
}

public record AcmeResponse(String requestId, boolean accepted) {
}
~~~

Exception công khai:

~~~java
package com.acme.api;

public class AcmeException extends RuntimeException {
    public AcmeException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là các tệp Java minh họa; mỗi public top-level type nên nằm trong file riêng có tên tương ứng.

### 2.1. API module nên biết ít nhất có thể

Nếu có thể, API module nên độc lập với Spring Boot và framework triển khai. Nó không nên chứa:

- @AutoConfiguration, @Bean, @ConditionalOnClass.
- Cấu hình DataSource, HTTP client pool hoặc connection factory.
- Mã đọc Environment và bind property.
- Lớp implementation mặc định.
- File AutoConfiguration.imports.

Lợi ích:

- Ứng dụng Java thuần hoặc framework khác vẫn dùng được contract.
- Integration của nhiều nền tảng có thể dùng chung API.
- Không kéo Spring Boot vào mọi consumer chỉ vì họ cần interface/model.
- API ít thay đổi hơn implementation, dễ giữ binary compatibility.

Không nên đưa chi tiết SDK vendor vào public API nếu muốn cho phép thay vendor. Ví dụ, nếu AcmeClient nhận VendorSdkRequest, mọi consumer của API sẽ bị phụ thuộc vào SDK. Hãy dùng request/response do thư viện sở hữu và chuyển đổi sang kiểu vendor ở adapter.

### 2.2. API module không tự kích hoạt bean

Chỉ thêm dependency acme-api không khiến Spring Boot tạo AcmeClient. API chỉ cung cấp kiểu Java. Để có bean tự động, ứng dụng cần artifact chứa auto-configuration và cơ chế discovery của Spring Boot.

### 2.3. Khi nào không cần API module riêng?

Nếu thư viện nhỏ, chỉ có một implementation và API không được dùng độc lập, việc tách thêm một artifact có thể làm tăng chi phí build, versioning và phát hành. Khi đó có thể đặt interface/model trong mô-đun autoconfigure hoặc mô-đun thư viện chính.

Tách API riêng khi:

- Nhiều integration cùng triển khai một contract.
- Ứng dụng khác cần compile chỉ với interface/model.
- Muốn giữ API trung lập với Spring Boot.
- Muốn quản lý compatibility và phát hành API độc lập.

## 3. Mô-đun autoconfigure: nối API với Spring Boot

Autoconfigure module chứa **mã đăng ký và cấu hình implementation** để ứng dụng Spring Boot dùng thư viện thuận tiện.

Nội dung thường gồm:

- Các lớp @AutoConfiguration.
- Implementation mặc định của API.
- @ConfigurationProperties và default.
- Các condition @ConditionalOnClass, @ConditionalOnProperty, @ConditionalOnBean, @ConditionalOnMissingBean.
- Callback/customizer để người dùng mở rộng.
- Các cấu hình con cho integration tùy chọn.
- Resource META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.
- Metadata điều kiện auto-configuration và metadata configuration properties do annotation processor tạo.

### 3.1. Ví dụ properties và implementation mặc định

Giả sử API module đã có AcmeClient. Autoconfigure module định nghĩa properties:

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        @DefaultValue("https://api.acme.example") URI endpoint
) {
}
~~~

Một implementation mặc định đơn giản có thể dùng Java HttpClient:

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeException;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;

final class DefaultAcmeClient implements AcmeClient {

    private final URI endpoint;
    private final HttpClient httpClient;

    DefaultAcmeClient(URI endpoint) {
        this.endpoint = endpoint;
        this.httpClient = HttpClient.newHttpClient();
    }

    @Override
    public AcmeResponse send(AcmeRequest request) {
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(endpoint)
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(request.message()))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    httpRequest,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new AcmeException(
                        "Acme service returned HTTP " + response.statusCode(),
                        null);
            }

            return new AcmeResponse(response.body(), true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AcmeException("Acme request was interrupted", ex);
        } catch (java.io.IOException ex) {
            throw new AcmeException("Could not call Acme service", ex);
        }
    }

    @Override
    public URI endpoint() {
        return endpoint;
    }
}
~~~

Đây là implementation minh họa có thể biên dịch trên Java 17+ với các API Java chuẩn và API module ở trên. Giao thức HTTP thực tế của dịch vụ Acme là giả định; khi triển khai thật, cần xác định path, authentication, request/response format, status mapping và timeout theo API của dịch vụ.

Auto-configuration:

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }
}
~~~

Condition @ConditionalOnMissingBean cho phép ứng dụng cung cấp implementation riêng. Condition @ConditionalOnProperty ở class-level quy định rằng acme.enabled=false sẽ tắt nhánh core; khi không khai báo key, default-on theo matchIfMissing=true.

### 3.2. Auto-configuration phải được đăng ký

Spring Boot 3.x phát hiện auto-configuration từ file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Mỗi dòng là tên đầy đủ của một auto-configuration class. Khi ứng dụng dùng @SpringBootApplication hoặc @EnableAutoConfiguration, Boot tìm file này trong các JAR trên classpath, rồi xử lý các candidate theo condition và thứ tự.

**File imports phải nằm trong JAR autoconfigure**, không phải chỉ trong starter aggregator. Starter thường không chứa mã cấu hình và không cần tự liệt kê lại class. Khi build, hãy kiểm tra resource thực tế bên trong artifact được publish.

Auto-configuration nên là top-level class, không phải mục tiêu của component scan. Không dùng @ComponentScan rộng trong auto-configuration để tìm các class thư viện; dùng @Import tường minh cho cấu hình hỗ trợ khi cần.

### 3.3. Dependencies của autoconfigure

Autoconfigure module thường cần:

- API module.
- spring-boot-autoconfigure.
- Các thư viện runtime bắt buộc để tạo default implementation.
- spring-boot-configuration-processor để sinh metadata cho key cấu hình.
- spring-boot-autoconfigure-processor để sinh metadata condition nếu dự án cần tối ưu lọc auto-configuration.

Nếu public method/constructor signature trong autoconfigure module lộ kiểu API cho consumer, hãy khai báo dependency API phù hợp (ví dụ Gradle api(project(":acme-api"))). Nếu dependency chỉ là chi tiết nội bộ, dùng implementation khi dependency graph cho phép.

Với thư viện có dependency optional, cần quyết định rõ nó thuộc runtime graph của artifact nào. Một SDK optional không nên bị kéo vào mọi ứng dụng chỉ dùng core.

## 4. Mô-đun starter: gói dependency để người dùng thêm một lần

Starter có mục đích khác với autoconfigure: **gom các dependency cần thiết cho một trải nghiệm sử dụng có chủ đích**.

Một starter tiêu chuẩn thường gần như một JAR rỗng:
- Không chứa service implementation.
- Không chứa @AutoConfiguration.
- Không cần component scan.
- Không chứa file AutoConfiguration.imports nếu nó không cung cấp auto-configuration.
- Chủ yếu khai báo dependency tới autoconfigure và các thư viện cần thiết.

Ví dụ người dùng thêm:

~~~kotlin
dependencies {
    implementation("com.acme:acme-spring-boot-starter:1.2.0")
}
~~~

Starter có thể kéo theo:
- acme-spring-boot-autoconfigure.
- acme-api thông qua dependency transitive của autoconfigure.
- spring-boot-starter nếu starter cần bảo đảm core Spring Boot starter có mặt.
- HTTP client hoặc dependency nền tảng mà core library thực sự cần.

Khi thêm starter, người dùng có thể cấu hình:

~~~yaml
acme:
  enabled: true
  endpoint: https://tenant.example
~~~

Sau đó inject API:

~~~java
@Service
class NotificationService {

    private final AcmeClient acmeClient;

    NotificationService(AcmeClient acmeClient) {
        this.acmeClient = acmeClient;
    }

    AcmeResponse notify(String message) {
        return acmeClient.send(new AcmeRequest(message));
    }
}
~~~

Người dùng **không cần** tự @Import(AcmeAutoConfiguration.class) hoặc @ComponentScan("com.acme.autoconfigure"). Boot tự tìm imports file trong autoconfigure JAR.

### 4.1. Starter có phải luôn là một JAR rỗng?

Theo convention của Spring Boot, starter là một dependency aggregator, thường là JAR gần như rỗng. Tên artifact và POM/build file mô tả những dependency được chọn.

Có thể gộp autoconfigure và starter nếu thư viện nhỏ, không có nhiều optional features. Khi đó một artifact vừa chứa code auto-configuration vừa cung cấp dependency cần thiết. Tuy nhiên, nếu muốn cho phép ứng dụng chỉ dùng autoconfigure để tự chọn dependency hoặc tạo nhiều starter với các tổ hợp khác nhau, tách riêng hai mô-đun sẽ linh hoạt hơn.

## 5. So sánh trách nhiệm và artifact

| Tiêu chí | API module | Autoconfigure module | Starter module |
| --- | --- | --- | --- |
| Mục đích | Contract công khai | Tự động tạo/cấu hình bean | Gom dependency cho consumer |
| Chứa interface/model | Có | Có thể tham chiếu | Không nên |
| Chứa implementation mặc định | Không | Có | Không |
| Chứa @AutoConfiguration | Không | Có | Thông thường không |
| Chứa @ConfigurationProperties | Thường không | Có thể có | Không |
| Chứa AutoConfiguration.imports | Không | Có | Thường không |
| Phụ thuộc Spring Boot | Tốt nhất không | Có | Thường gián tiếp |
| Có thể được dùng độc lập | Có thể dùng bởi Java/framework khác | Có thể dùng khi tự chọn dependency | Dành cho trải nghiệm tích hợp Spring Boot |
| Vai trò với người dùng | Compile contract | Cung cấp hành vi tự động | Dependency duy nhất cần thêm |

Ba module không phải ba tầng phải luôn tồn tại. Hãy tách theo nhu cầu sử dụng và dependency graph thực tế.

## 6. Thiết kế dependency graph một chiều

Với ba mô-đun:

~~~text
acme-api
    ^
    |
acme-spring-boot-autoconfigure
    ^
    |
acme-spring-boot-starter
    ^
    |
Ứng dụng sử dụng
~~~

Mũi tên biểu diễn dependency từ dưới lên trong sơ đồ: autoconfigure phụ thuộc API; starter phụ thuộc autoconfigure; ứng dụng phụ thuộc starter.

Không tạo vòng như:

~~~text
acme-api -> autoconfigure -> starter -> acme-api
~~~

API không được biết starter, và autoconfigure không nên phụ thuộc starter. Starter là lớp ngoài cùng, gom các thành phần đã có.

### 6.1. Khi nào tách optional integration?

Giả sử Acme có thêm codec Vendor, nhưng chỉ một số ứng dụng cần. Có thể tạo:

~~~text
acme-api
acme-spring-boot-autoconfigure
acme-spring-boot-starter

acme-vendor-codec-autoconfigure
acme-spring-boot-starter-vendor-codec
~~~

Dependency graph:

~~~text
Ứng dụng core
    |
    v
acme-spring-boot-starter
    |
    v
acme-spring-boot-autoconfigure
    |
    v
acme-api

Ứng dụng cần codec
    |
    +---- acme-spring-boot-starter
    |
    +---- acme-spring-boot-starter-vendor-codec
                |
                +---- acme-vendor-codec-autoconfigure
                |
                +---- Vendor SDK
~~~

Core starter không kéo Vendor SDK. Starter codec thể hiện một lựa chọn bổ sung, có thể phụ thuộc vào core starter, codec autoconfigure và SDK.

Trong optional auto-configuration, dùng @ConditionalOnClass ở **cấp configuration class** nếu method signature có kiểu vendor có thể thiếu. Nếu cần bean client do SDK tạo, thêm @ConditionalOnBean. Khi muốn ứng dụng thay adapter, dùng @ConditionalOnMissingBean.

## 7. Ví dụ Gradle multi-project

### 7.1. Cấu trúc thư mục

~~~text
acme/
  settings.gradle.kts
  build.gradle.kts

  acme-api/
    build.gradle.kts
    src/main/java/com/acme/api/AcmeClient.java

  acme-spring-boot-autoconfigure/
    build.gradle.kts
    src/main/java/com/acme/autoconfigure/AcmeAutoConfiguration.java
    src/main/java/com/acme/autoconfigure/AcmeProperties.java
    src/main/resources/META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-spring-boot-starter/
    build.gradle.kts
~~~

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "acme"

include(
    "acme-api",
    "acme-spring-boot-autoconfigure",
    "acme-spring-boot-starter"
)
~~~

### 7.3. API build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}
~~~

API module không cần Spring Boot dependency nếu contract chỉ dùng kiểu Java/JDK.

### 7.4. Autoconfigure build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":acme-api"))

    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
    annotationProcessor("org.springframework.boot:spring-boot-autoconfigure-processor")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Ở đây:
- api(project(":acme-api")) vì API là contract mà consumer sử dụng.
- implementation(spring-boot-autoconfigure) cung cấp annotation và runtime support cho auto-configuration.
- Hai annotation processor tạo metadata khi compile.
- Test của autoconfigure dùng spring-boot-starter-test.

### 7.5. Starter build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    api(project(":acme-spring-boot-autoconfigure"))
    api("org.springframework.boot:spring-boot-starter")
}
~~~

Starter không cần source Java. Dependency api giúp các dependency được truyền tới ứng dụng tiêu thụ starter; có thể điều chỉnh api/implementation theo contract và cách publish thực tế.

**Version:** ví dụ dùng Spring Boot 3.3.13 làm BOM minh họa. Trong thư viện được publish, cần bảo đảm dependency version được giải quyết nhất quán và không ép ứng dụng host phải dùng một Spring Boot version ngoài ý muốn. Có thể chuyển version BOM vào version catalog hoặc root dependency management.

## 8. Maven multi-module cũng dùng cùng ranh giới

Trong Maven, root project thường dùng packaging pom và liệt kê ba module:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>acme-api</module>
    <module>acme-spring-boot-autoconfigure</module>
    <module>acme-spring-boot-starter</module>
</modules>
~~~

Autoconfigure POM phụ thuộc API và Spring Boot autoconfigure:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-api</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Starter POM gom autoconfigure và core starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Các đoạn trên là phần dependencies/module chính, chưa phải toàn bộ POM publishable. Dự án thật cần khai báo groupId, artifactId, version, repository, compiler release, test plugin và dependency management. Nên dùng Spring Boot BOM để quản lý version thư viện Spring Boot tương thích; tránh khai báo nhiều version rời rạc trong từng module.

### 8.1. Có cần BOM riêng cho thư viện không?

Nếu chỉ có vài artifact và tất cả phát hành cùng version, dependency management ở parent/BOM Spring Boot có thể đủ. Nếu thư viện có nhiều module hoặc nhiều optional starter cần người dùng chọn độc lập, có thể phát hành thêm acme-bom để quản lý version đồng bộ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-api</artifactId>
            <version>1.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>1.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

BOM quản lý version; nó không tự thêm các dependency vào classpath. Consumer vẫn phải khai báo artifact starter hoặc API mà họ cần.

## 9. Trải nghiệm consumer: thêm starter, cấu hình, inject API

Một ứng dụng dùng Gradle:

~~~kotlin
dependencies {
    implementation("com.acme:acme-spring-boot-starter:1.2.0")
}
~~~

Cấu hình:

~~~yaml
acme:
  enabled: true
  endpoint: https://tenant.example
~~~

Sử dụng API:

~~~java
@Service
class OrderNotificationService {

    private final AcmeClient acmeClient;

    OrderNotificationService(AcmeClient acmeClient) {
        this.acmeClient = acmeClient;
    }

    AcmeResponse notify(String message) {
        return acmeClient.send(new AcmeRequest(message));
    }
}
~~~

Người dùng chỉ cần biết API và properties công khai. Họ không phải biết class DefaultAcmeClient, không phải tự tạo bean mặc định và không phải tự import auto-configuration.

Nếu muốn thay implementation:

~~~java
@Configuration(proxyBeanMethods = false)
class MyAcmeConfiguration {

    @Bean
    AcmeClient myAcmeClient() {
        return new MyAcmeClient();
    }
}
~~~

@ConditionalOnMissingBean(AcmeClient.class) trong auto-configuration sẽ khiến bean default back off khi user bean được xử lý trước. Đây là giao ước customization cần được ghi trong tài liệu.

## 10. Kiểm thử ở đúng ranh giới mô-đun

Không nên chỉ có một test khởi động toàn bộ ứng dụng rồi kết luận mọi module đúng. Mỗi module cần test phù hợp:

| Module | Kiểm thử nên có |
| --- | --- |
| API | Compile contract, model behavior, compatibility của public types |
| Autoconfigure | ApplicationContextRunner: default, property override, disable, custom bean back-off, classpath condition |
| Starter | Dependency graph, imports resource có trong JAR, smoke test consumer chỉ thêm starter |
| Optional integration | SDK present/missing, client bean present/missing, custom adapter override |

### 10.1. Test auto-configuration bằng ApplicationContextRunner

Ví dụ dưới đây là **một tệp test hoàn chỉnh** để kiểm tra default, property override, tắt feature và bean do người dùng cung cấp. Trong production, các API/properties/auto-configuration được đặt trong các module riêng như đã mô tả.

**Tệp:** src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTest.java

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
        });
    }

    @Test
    void bindsEndpointFromEnvironment() {
        runner.withPropertyValues("acme.endpoint=https://tenant.example")
                .run(context -> {
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                });
    }

    @Test
    void explicitFalseDisablesTheAutoConfiguration() {
        runner.withPropertyValues("acme.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class));
    }

    @Test
    void userClientMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://custom.example"));
                    assertThat(context.containsBean("acmeClient")).isFalse();
                });
    }

    record TestAcmeClient(URI endpoint) implements AcmeClient {
        @Override
        public AcmeResponse send(AcmeRequest request) {
            return new AcmeResponse("test-id", true);
        }
    }

    @ConfigurationProperties(prefix = "acme")
    record AcmeProperties(
            @DefaultValue("https://api.acme.example") URI endpoint
    ) {
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "acme",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @EnableConfigurationProperties(AcmeProperties.class)
    static class AcmeAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        TestAcmeClient acmeClient(AcmeProperties properties) {
            return new TestAcmeClient(properties.endpoint());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new TestAcmeClient(
                    URI.create("https://custom.example"));
        }
    }
}
~~~

Tệp test trên dùng AcmeClient, AcmeRequest và AcmeResponse từ API module. Test implementation trả về response giả lập; nó chỉ kiểm tra binding và điều kiện bean, không gửi HTTP request.

### 10.2. Dependency và lệnh chạy test

Trong autoconfigure module, Gradle test dependency có thể là:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Chạy tại root multi-project:

~~~bash
# Linux/macOS
./gradlew :acme-spring-boot-autoconfigure:test

# Windows
gradlew.bat :acme-spring-boot-autoconfigure:test
~~~

**Kết quả mong đợi:** bốn test PASS:
- Không khai báo acme.enabled: client mặc định xuất hiện.
- Có acme.endpoint: endpoint được bind.
- acme.enabled=false: không có client mặc định.
- User bean xuất hiện: auto-configuration không tạo default thứ hai.

Các assertion kiểm tra context, không in stdout ứng dụng cố định. Output console phụ thuộc Gradle/JUnit logging.

### 10.3. Kiểm tra starter JAR thực sự

ApplicationContextRunner ở trên nạp auto-configuration trực tiếp bằng AutoConfigurations.of(...); do đó nó kiểm tra logic bean nhưng **không chứng minh** resource imports đã được đóng gói đúng trong JAR.

Sau khi build:

~~~bash
# Xem nội dung JAR autoconfigure
jar tf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar

# Kiểm tra file imports đã được đóng gói
jar xf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mở resource được trích xuất và xác nhận có dòng:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Sau đó tạo một sample consumer chỉ thêm acme-spring-boot-starter và chạy smoke test khởi động. Đây là bước xác minh discovery và dependency transitives trong môi trường gần với người dùng nhất.

## 11. Đặt tên artifact và quản lý phiên bản

Một convention phù hợp cho thư viện là:

~~~text
com.acme:acme-api
com.acme:acme-spring-boot-autoconfigure
com.acme:acme-spring-boot-starter
com.acme:acme-codec-autoconfigure
com.acme:acme-spring-boot-starter-codec
~~~

Spring Boot khuyến nghị tên module riêng của thư viện **không bắt đầu bằng spring-boot**, tránh gây nhầm lẫn với module chính thức của Spring Boot. Dùng tên thương hiệu hoặc namespace của thư viện.

### Versioning

Nếu các module phát hành cùng nhau, nên dùng cùng version, ví dụ 1.2.0. Khi nâng version:
- API thay đổi có thể là breaking change với compile-time consumer.
- Đổi property name hoặc default có thể là breaking behavior change.
- Đổi class auto-configuration/package có thể ảnh hưởng before/after, exclusions và imports metadata.
- Starter thêm dependency mới có thể làm runtime classpath của ứng dụng thay đổi.
- Optional starter thêm SDK lớn hoặc khác license cần được công bố rõ.

Không nên để acme-api:1.1.0 và acme-spring-boot-autoconfigure:1.2.0 được kéo vào cùng một ứng dụng nếu hai version không tương thích. Dùng parent version đồng bộ hoặc BOM của Acme để quản lý.

### Tương thích Spring Boot

Thư viện nên công bố dải Spring Boot được hỗ trợ. Không nên starter tự ý ép version Spring Boot mới hơn version mà ứng dụng đang sử dụng. Để người dùng quản lý version bằng Spring Boot BOM/plugin; build thư viện theo version được hỗ trợ và chạy CI với các version tương thích đã cam kết.

## 12. Những lỗi thường gặp khi chia mô-đun

1. **Đưa @AutoConfiguration vào API module.** API trở nên phụ thuộc Spring Boot dù consumer chỉ cần contract; chuyển auto-configuration sang module riêng.
2. **Đưa implementation vào starter.** Starter trở thành nơi chứa logic và khó tái sử dụng; để implementation trong library/autoconfigure module.
3. **Nghĩ starter tự tạo bean.** Starter chỉ đưa dependencies vào classpath; auto-configuration mới đăng ký bean.
4. **Đặt imports file trong starter thay vì autoconfigure.** Boot không thấy file trong artifact thực sự chứa cấu hình, hoặc file bị bỏ khỏi quá trình đóng gói.
5. **Quên imports file.** Class auto-configuration có trong JAR nhưng không trở thành candidate; thêm tên đầy đủ vào resource chuẩn.
6. **Dùng component scan để phát hiện auto-configuration.** Làm sai discovery/ordering và dễ scan nhầm class; dùng imports file.
7. **Tạo dependency vòng.** API phụ thuộc autoconfigure hoặc starter; giữ hướng API → autoconfigure → starter theo nghĩa phụ thuộc từ trên xuống.
8. **Core starter kéo SDK optional.** Ứng dụng chỉ cần core vẫn bị thêm dependency không cần; tách optional integration và starter riêng.
9. **Tách quá nhiều module dù không có ranh giới.** Tăng chi phí versioning/publish; gộp khi API không dùng độc lập và không có optional flavor.
10. **Không công bố API contract rõ.** Consumer phải import implementation class; chỉ expose interface/model cần thiết.
11. **API chứa kiểu vendor.** Mọi consumer bị khóa vào SDK; viết adapter ở integration module.
12. **Không kiểm tra dependency transitive.** Starter có thể thiếu core starter hoặc kéo sai version; xem dependency insight/tree.
13. **Không kiểm tra artifact đã publish.** Source có resource đúng nhưng JAR thiếu imports/metadata; kiểm tra JAR thực tế.
14. **Dùng tên module bắt đầu bằng spring-boot.** Dễ gây nhầm với module chính thức; dùng tên riêng như acme-spring-boot-starter.
15. **Chỉ test auto-config trực tiếp, không test consumer starter.** Logic đúng nhưng starter có thể thiếu dependency hoặc resource; thêm smoke test với starter được publish/local-published.

## 13. Checklist trước khi phát hành

### API
- [ ] Public interface/model/exception có ổn định và có tài liệu.
- [ ] Không phụ thuộc Spring Boot nếu không cần.
- [ ] Không phơi implementation hoặc kiểu SDK optional.
- [ ] Compatibility của API được kiểm tra.

### Autoconfigure
- [ ] Có @AutoConfiguration và condition phù hợp.
- [ ] Bean default có @ConditionalOnMissingBean khi cho phép override.
- [ ] Properties có namespace riêng, kiểu và default rõ.
- [ ] Imports file nằm trong đúng JAR và chứa đủ class.
- [ ] Optional classes được bảo vệ ở class-level.
- [ ] Annotation processors được cấu hình nếu cần metadata.

### Starter
- [ ] Chỉ kéo dependencies thực sự cần cho use case mặc định.
- [ ] Không chứa logic bean/auto-configuration trùng lặp.
- [ ] Có core spring-boot-starter trực tiếp hoặc gián tiếp khi cần.
- [ ] Optional features được tách thành starter riêng khi phù hợp.
- [ ] Dependency versions được quản lý nhất quán.

### Kiểm thử phát hành
- [ ] API module compile/test độc lập.
- [ ] Autoconfigure test default, override, disable và condition.
- [ ] Kiểm tra imports/metadata trong JAR.
- [ ] Consumer smoke test chỉ thêm starter.
- [ ] Dependency tree không kéo SDK tùy chọn ngoài ý muốn.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng chỉ cần interface AcmeClient, không dùng Spring Boot. Họ nên phụ thuộc module nào?

**Đáp án:** API module. Không cần kéo auto-configuration hoặc starter.

**Câu 2.** Module nào chứa AcmeAutoConfiguration và AutoConfiguration.imports?

**Đáp án:** Autoconfigure module. Đây là artifact chứa mã cấu hình và resource để Spring Boot phát hiện.

**Câu 3.** Starter có tự tạo bean AcmeClient không?

**Đáp án:** Không. Starter đưa autoconfigure và dependency cần thiết vào classpath; auto-configuration trong JAR mới đăng ký bean.

**Câu 4.** Khi có optional codec SDK, có nên đưa nó vào core starter không?

**Đáp án:** Không nếu người dùng core không cần codec. Tạo integration/autoconfigure và starter tùy chọn riêng để người dùng lựa chọn.

**Câu 5.** Vì sao phải kiểm tra JAR sau khi build dù ApplicationContextRunner test đã pass?

**Đáp án:** Test runner nạp class trực tiếp, không chứng minh imports resource có trong JAR và dependency transitive của starter đã đúng. Cần kiểm tra artifact và sample consumer.

## 15. Ghi nhớ khi thiết kế thư viện

- **API** định nghĩa contract mà consumer lập trình trực tiếp.
- **Autoconfigure** kết nối contract với Spring Boot: properties, default implementation, conditions và imports metadata.
- **Starter** cung cấp dependency set thuận tiện để ứng dụng bật thư viện bằng một khai báo.

Hướng phụ thuộc nên đi một chiều: API ở đáy, autoconfigure phụ thuộc API, starter phụ thuộc autoconfigure và các dependency runtime cần thiết. Khi có optional feature, hãy tạo integration/starter riêng để core không kéo SDK không cần thiết.

Không bắt buộc phải tách ba artifact cho mọi thư viện. Nếu API không được dùng độc lập hoặc thư viện rất đơn giản, có thể gộp API vào autoconfigure và/hoặc gộp autoconfigure với starter. Hãy tách khi ranh giới giúp consumer chọn đúng dependency, giữ API ổn định và làm cho hợp đồng kích hoạt/tùy chỉnh dễ hiểu.

### Tài liệu Spring Boot chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — @AutoConfiguration Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
