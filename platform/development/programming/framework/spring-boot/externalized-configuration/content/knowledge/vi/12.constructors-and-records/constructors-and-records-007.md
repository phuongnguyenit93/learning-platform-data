# Yêu cầu tên tham số -parameters và cấu hình biên dịch

Trong Spring Boot, `@ConfigurationProperties` cho phép ánh xạ cấu hình bên ngoài vào một Java object có kiểu rõ ràng. Với **constructor binding**, Spring Boot tạo đối tượng bằng cách gọi constructor và chuyển giá trị của các key cấu hình vào **từng tham số**. Để biết tham số `connectTimeout` nhận giá trị từ `client.connect-timeout`, framework phải xác định được **tên tham số constructor** khi chạy ứng dụng.

Với một class Java thông thường, **tên tham số có trong mã nguồn không có nghĩa chúng luôn được giữ trong bytecode**. Trình biên dịch `javac` có cờ `-parameters` để lưu metadata tên tham số vào file `.class` cho reflection. Tài liệu Spring Boot nêu rõ yêu cầu biên dịch với `-parameters` khi sử dụng constructor binding. Spring Boot Maven parent và Spring Boot Gradle plugin thường đã cấu hình điều này, nhưng dự án dùng cấu hình build tùy chỉnh, BOM không đi kèm parent, module thư viện, IDE compiler hoặc pipeline khác vẫn cần kiểm tra.

Bài này hướng dẫn vì sao cần tên tham số, cách bật `-parameters` trong Maven/Gradle, cách kiểm tra bytecode, liên hệ với Java `record` và cách chẩn đoán lỗi binding phát sinh từ cấu hình biên dịch.

## 1. Tại sao constructor binding cần tên tham số?

Giả sử file `application.yml` chứa:

~~~yaml
gateway:
  base-url: "https://api.example.invalid"
  connect-timeout: 3s
  max-retries: 4
~~~

Một immutable properties class:

~~~java
package example.gateway;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public final class GatewayProperties {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    public GatewayProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxRetries) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

Trong Spring Boot 3.x, khi một configuration-properties type chỉ có một constructor có tham số phù hợp, constructor binding thường được suy ra mà không cần gắn `@ConstructorBinding` lên constructor đó.

Binder cần hiểu:

| Tham số constructor | Property được bind | Giá trị sau conversion |
| --- | --- | --- |
| `baseUrl` | `gateway.base-url` | `URI` |
| `connectTimeout` | `gateway.connect-timeout` | `Duration.ofSeconds(3)` |
| `maxRetries` | `gateway.max-retries` | Số nguyên `4` |

Tên tham số `baseUrl`, `connectTimeout` và `maxRetries` giúp Binder nối **cấu trúc Java** với **tên key cấu hình** thông qua relaxed binding.

Nếu bytecode không mang metadata tên tham số và không có cơ chế suy ra tên phù hợp, reflection trên constructor có thể chỉ thấy `arg0`, `arg1`, `arg2`. Khi đó Spring Boot không thể xác định đáng tin cậy `arg1` phải nhận `gateway.connect-timeout` và có thể báo lỗi tạo/bind configuration-properties bean.

**Cốt lõi:** `-parameters` không làm Spring Boot tự đọc một file YAML khác, không sinh getter và không tự đăng ký bean. Nó giúp **giữ tên tham số từ quá trình biên dịch để framework có thể quan sát ở runtime**.

## 2. Cờ javac -parameters thực sự làm gì?

Ví dụ Java thuần:

~~~java
package example;

public class ExampleConstructor {

    public ExampleConstructor(String name, int retries) {
    }
}
~~~

Nếu biên dịch bằng `javac` có `-parameters`:

~~~bash
javac -parameters -d out src/main/java/example/ExampleConstructor.java
~~~

compiler có thể ghi metadata `MethodParameters` vào `.class`. Các framework dùng Java reflection có thể đọc tên khai báo thực tế.

Reflection:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class InspectParameters {

    public static void main(String[] args) {
        Constructor<?> constructor =
            ExampleConstructor.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(
                parameter.getName() + " -> " +
                parameter.isNamePresent());
        }
    }
}
~~~

Đối với constructor Java thông thường được biên dịch với `-parameters`, đầu ra mong đợi là:

~~~text
name -> true
retries -> true
~~~

Khi biên dịch **không** có flag và không có cơ chế metadata đặc biệt, reflection có thể trả:

~~~text
arg0 -> false
arg1 -> false
~~~

Java không tự cam kết giữ tên tham số của mọi constructor/method thông thường khi không bật `-parameters`. Tham số là một phần của chữ ký source, nhưng bytecode chạy được không nhất thiết cần lưu tên đó để JVM gọi phương thức.

**Đây là tùy chọn tại thời điểm compile.** Thêm `-parameters` vào lệnh `java -jar ...` lúc chạy **không** tạo metadata đã mất. Phải biên dịch lại các class có constructor cần bind.

## 3. MethodParameters khác LocalVariableTable và debug symbols

Một ngộ nhận phổ biến: “Compiler đã bật debug, tên biến nằm trong `.class` nên Spring chắc đọc được tên constructor parameter.”

Các loại metadata có mục đích khác nhau:

| Metadata/tùy chọn | Mục tiêu |
| --- | --- |
| `-parameters` | Lưu tên formal parameters cho reflection, thường thể hiện ở `MethodParameters` |
| `-g` và debug info | Có thể tạo `LineNumberTable`, `LocalVariableTable` và thông tin phục vụ debug |
| `-g:none` | Hạn chế debug info; không đồng nghĩa đã tắt `MethodParameters` nếu dùng `-parameters` |
| `-source` / `--release` | Điều khiển mức tương thích Java; không thay thế `-parameters` |

Đặc biệt từ **Spring Framework 6.1**, một số cơ chế suy luận tên tham số trước đây dựa trên local variable table không còn được xem là fallback chuẩn như các phiên bản cũ. Cấu hình compile với `-parameters` giúp các phần khác của Spring cũng có thể dựa trên tên tham số một cách nhất quán.

Không nên kết luận từ việc thấy `LocalVariableTable` trong kết quả `javap -v` rằng constructor binding đã có đủ metadata tương ứng. Hãy kiểm tra phần `MethodParameters` và/hoặc kiểm tra reflection trên chính class liên quan.

Một số loại class như Java record có metadata cấu trúc riêng; hành vi chi tiết của tên parameter đối với canonical constructor có thể khác class thông thường. Dù vậy, cấu hình build cấp dự án với `-parameters` vẫn là phương án thống nhất theo hướng dẫn Spring Boot, đặc biệt khi codebase chứa cả record và class có constructor thủ công.

## 4. Cấu hình @ConfigurationProperties đúng cách trước khi nói về compiler

Một class đã compile với `-parameters` vẫn phải được **đăng ký như configuration-properties bean**.

Ví dụ đăng ký tường minh:

~~~java
package example.gateway;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
public class GatewayConfiguration {
}
~~~

Hoặc quét:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = "example.gateway")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Đây là **hai phương án đăng ký thay thế nhau** trong nhiều trường hợp. Không cần vừa scan vừa enable cùng một class chỉ để “chắc ăn”.

Với constructor binding:

- `@ConfigurationProperties(prefix = ...)` mô tả root cấu hình.
- `@EnableConfigurationProperties(...)` hoặc `@ConfigurationPropertiesScan` đưa typed properties vào container.
- `-parameters` giúp giữ metadata tên tham số Java để Binder tra cứu.
- Conversion và validation quyết định dữ liệu bind có đúng kiểu/hợp lệ không.

Không dùng `@Component` đơn thuần để thay thế registration cho constructor-bound immutable properties. Bean được tạo bằng cơ chế Spring thông thường (ví dụ `@Bean`, `@Component`) không tương đương với việc Binder chọn constructor tham số cấu hình.

## 5. Maven với spring-boot-starter-parent

Nếu project có Maven parent của Spring Boot:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- phiên bản Spring Boot của dự án --></version>
    <relativePath/>
  </parent>

  <!-- dependencies, build... -->
</project>
~~~

Trong các phiên bản Spring Boot hiện đại, Maven parent đã quản lý nhiều thiết lập plugin cho ứng dụng, trong đó có việc biên dịch Java có tên tham số. Vì vậy **thường không cần** tự thêm `-parameters` nếu dùng parent chuẩn và không có cấu hình nào khác override.

Nhưng cần phân biệt:

- Dùng `spring-boot-starter-parent`: nhận plugin management/build conventions từ parent.
- Chỉ import `spring-boot-dependencies` BOM vào `dependencyManagement`: chủ yếu quản lý versions dependencies; **không tự mang theo đầy đủ cấu hình build plugin của starter parent**.
- Dùng parent do công ty tự quản lý: cần kiểm tra parent đó có cấu hình `maven-compiler-plugin` hoặc property `maven.compiler.parameters` đúng chưa.
- Một multi-module build có thể có các parent/plugin overrides khác nhau giữa các module.

Nếu parent đã cấu hình đúng, không nên thêm cấu hình trùng chỉ vì thói quen. Hãy kiểm tra **effective POM** khi cần xác nhận điều gì thực sự được áp dụng.

## 6. Maven: bật -parameters tường minh

Nếu không dùng Spring Boot parent hoặc cần bảo đảm ở một module độc lập, cấu hình `maven-compiler-plugin`.

Một phương án rõ ràng trong `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Với compiler plugin hỗ trợ tham số `parameters`, cấu hình `<parameters>true</parameters>` chỉ thị plugin chuyển tương ứng thành `-parameters` khi gọi Java compiler.

Có thể thiết lập thuộc tính:

~~~xml
<properties>
  <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Phương án property phụ thuộc vào phiên bản Maven Compiler Plugin có hỗ trợ `maven.compiler.parameters`. Nếu build dùng plugin cũ, nâng hoặc cấu hình plugin thích hợp theo chiến lược quản lý phiên bản của dự án.

Một cách khác dùng compiler args:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <compilerArgs>
          <arg>-parameters</arg>
        </compilerArgs>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Nên ưu tiên thuộc tính chuyên dụng `<parameters>true</parameters>` khi plugin đã hỗ trợ, vì nó diễn đạt ý định rõ hơn.

### Có cần khai báo version của maven-compiler-plugin?

Nếu parent hoặc `pluginManagement` đã quản lý một phiên bản phù hợp, có thể không cần đặt `<version>` trên declaration của plugin. Nếu không có nơi quản lý phiên bản, nên pin phiên bản được build hệ thống chấp thuận thay vì dựa ngầm vào default. Các ví dụ tập trung vào cấu hình flag; không đặt số phiên bản cố định vì nó cần tương thích với Java, Maven và chuẩn của dự án.

### Parent và pluginManagement trong Maven multi-module

Với Maven, `pluginManagement` cung cấp **mặc định phiên bản và cấu hình** cho các plugin được dùng trong module. Nó không luôn tương đương việc ép mọi module phải sử dụng một plugin trong mọi pha lifecycle. `maven-compiler-plugin` thường tham gia lifecycle của module Java, nhưng quan trọng là **effective plugin configuration** của module chứa source file cần kiểm tra.

Ví dụ thư viện `shared-config` chứa `GatewayProperties.class`:

~~~text
root/pom.xml
  services/order-service/pom.xml
  libraries/shared-config/pom.xml
~~~

Nếu chỉ `order-service` có `-parameters` nhưng `shared-config` không có, constructor của `GatewayProperties` nằm trong JAR thư viện vẫn có thể thiếu metadata. Không thể “sửa lại” metadata của thư viện đã compile chỉ bằng cách bật flag ở module tiêu thụ.

## 7. Maven: cách kiểm tra cấu hình build thực tế

Dùng Maven Wrapper của repository nếu có:

~~~bash
./mvnw clean compile
~~~

Windows:

~~~powershell
.\mvnw.cmd clean compile
~~~

Để xem POM đã hợp nhất giữa parent, plugin management và module:

~~~bash
./mvnw help:effective-pom
~~~

Có thể xuất ra file để kiểm tra:

~~~bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

Hãy tìm `maven-compiler-plugin`, `parameters` hoặc `compilerArgs` trong effective POM của module đang build. Không phải chỉ tìm thấy một đoạn trong root POM đã đủ; cần biết cấu hình có được kế thừa và áp dụng đúng module không.

Để kiểm tra metadata sau compile, dùng `javap -v` trên class (trình bày ở phần kiểm chứng). Đây là bằng chứng trực tiếp hơn việc chỉ đọc POM, vì bytecode là output cuối cùng của compiler.

### Test source cũng có thể cần metadata

Khi Spring dùng reflection trên constructor hoặc method trong test classes, test compilation cũng quan trọng. `maven-compiler-plugin` thường có các goal compile và testCompile, nhưng nếu build có custom plugin executions hoặc profile riêng thì cần xác nhận cả hai.

Không nên nhầm `maven.compiler.testSource` hoặc thư mục test source với `-parameters`. Tham số metadata phải có trong bytecode của **class được phản chiếu tại runtime/test runtime**, chứ không chỉ trong một target build bất kỳ.

## 8. Gradle với Spring Boot plugin

Một dự án Gradle có:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}
~~~

Đối với Java compilation task được Spring Boot Gradle plugin cấu hình theo convention thích hợp, `-parameters` thường đã được thêm tự động. Đây là hành vi được tài liệu Spring Boot mô tả, nhưng **đừng chỉ dựa vào sự hiện diện của plugin ở một subproject khác** để kết luận mọi JavaCompile task đều có flag.

Những điểm cần kiểm tra:

- Module thực sự biên dịch properties class có apply plugin/hệ thống convention đúng không?
- Multi-project Gradle có áp dụng plugin ở root với `apply false` nhưng không apply ở module con không?
- Có task `JavaCompile` được tạo thủ công, thay compiler hoặc override `options.compilerArgs` sau khi plugin cấu hình không?
- CI và IDE có gọi đúng Gradle task hay dùng compiler riêng?
- File `.class` cuối cùng trong JAR có thực sự mang `MethodParameters` không?

Nếu chưa chắc convention có hiệu lực, có thể bật tường minh cho tất cả JavaCompile tasks của module.

## 9. Gradle Groovy DSL: build.gradle

Cấu hình:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

`configureEach` áp dụng cấu hình cho các task kiểu `JavaCompile`, bao gồm cả task được tạo sau. Với một dự án không dùng Spring Boot plugin nhưng có Java source chứa constructor-bound properties, đây là một cách đặt flag rõ ràng.

Nếu project đã có compiler args khác, `+=` bổ sung thay vì ghi đè toàn bộ danh sách:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-parameters',
        '-Xlint:deprecation'
    ]
}
~~~

Tránh cấu hình:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs = ['-parameters']
}
~~~

khi dự án đã có các flag bắt buộc khác do plugin hoặc conventions cung cấp; phép gán danh sách mới có thể vô tình loại bỏ compiler arguments trước đó.

Dùng Gradle Wrapper để build:

~~~bash
./gradlew clean classes
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean classes
~~~

Với subproject `shared-config`, cần bảo đảm cấu hình Gradle áp dụng vào **subproject này** chứ không chỉ root project.

## 10. Gradle Kotlin DSL: build.gradle.kts

Một cấu hình tương đương:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Kotlin DSL sử dụng API `options.compilerArgs.add(...)` để bổ sung flag. Nếu đã dùng Spring Boot Gradle plugin và convention của plugin thực sự có hiệu lực, đoạn cấu hình này có thể là dư thừa; quan trọng là không vô tình tạo hai lệnh `-parameters` hoặc ghi đè các compiler arguments khác.

Một multi-project Gradle có thể áp dụng cấu hình qua convention plugin được chia sẻ, giúp các module thư viện và ứng dụng dùng cùng quy tắc compile. Nhưng việc một convention nằm ở root không có nghĩa mọi subproject đã nhận nó. Hãy kiểm tra nơi class được build.

### Không nhầm Java plugin và Kotlin compiler

Nếu properties class viết bằng **Java**, flag `-parameters` phải đi tới Java compiler. Với code **Kotlin**, cơ chế nhận diện tên tham số và metadata của Kotlin có khác biệt; không nên lấy snippet `JavaCompile` rồi cho rằng nó đang cấu hình `KotlinCompile`. Một project mixed-language cần xem từng compiler và phiên bản plugin phù hợp.

Bài này tập trung vào Java, constructor Java và record Java.

## 11. Java record và tên tham số

Java `record` rất phù hợp với immutable configuration:

~~~java
package example.report;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled,
        int batchSize,
        Duration timeout
) {}
~~~

YAML:

~~~yaml
reporting:
  enabled: true
  batch-size: 100
  timeout: 5s
~~~

Đăng ký:

~~~java
package example.report;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingProperties.class)
public class ReportingConfiguration {
}
~~~

Trong Spring Boot 3.x, canonical constructor của record thường được dùng cho constructor binding. Nếu record có một canonical constructor thông thường, không cần đặt `@ConstructorBinding` chỉ để yêu cầu sử dụng constructor đó.

**Điểm tinh tế:** record có **record component metadata** do Java định nghĩa. Một số constructor của record có thể giữ tên tham số theo quy tắc của Java record ngay cả khi behavior của class constructor thông thường khác. Không nên lấy kết quả của **một record** rồi suy ra rằng `-parameters` hoàn toàn không cần cho cả dự án.

Tài liệu Spring Boot vẫn đưa ra yêu cầu chung biên dịch các class dùng constructor binding với `-parameters`. Để các kiểu Java khác nhau — record, class bất biến, class từ thư viện, framework injection — hoạt động nhất quán, giữ compiler flag ở build system là lựa chọn có thể kiểm chứng.

### Record không thay thế registration

Việc record tự có component name **không làm nó thành Spring bean**. Nếu không có `@EnableConfigurationProperties(ReportingProperties.class)` hoặc scan phù hợp, service inject `ReportingProperties` vẫn có thể thiếu bean.

Một ví dụ có đủ ba phần:

~~~java
@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled, int batchSize
) {}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingProperties.class)
class ReportingConfiguration {}
~~~

~~~java
@Service
class ReportService {

    private final ReportingProperties properties;

    ReportService(ReportingProperties properties) {
        this.properties = properties;
    }
}
~~~

Cần phân biệt tên tham số constructor của `ReportingProperties` — dùng để bind — với tên tham số `properties` của `ReportService` — có thể tham gia autowiring của Spring container trong một số tình huống khác.

## 12. Constructor thủ công và nhiều constructor

Ví dụ một class có hai constructor:

~~~java
package example.worker;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "worker")
public final class WorkerProperties {

    private final int maxThreads;
    private final Duration pollingInterval;

    @ConstructorBinding
    public WorkerProperties(int maxThreads, Duration pollingInterval) {
        this.maxThreads = maxThreads;
        this.pollingInterval = pollingInterval;
    }

    public WorkerProperties() {
        this(4, Duration.ofSeconds(5));
    }

    public int getMaxThreads() {
        return maxThreads;
    }

    public Duration getPollingInterval() {
        return pollingInterval;
    }
}
~~~

Trong Spring Boot 3.x, khi class có nhiều constructor và muốn dùng constructor cụ thể, annotation `@ConstructorBinding` có thể được đặt trên constructor được chọn theo API thuộc `org.springframework.boot.context.properties.bind`.

**Annotation không tạo ra tên tham số bị thiếu.** Nếu class được compile mà không có metadata cần thiết, thêm `@ConstructorBinding` có thể chỉ giúp Spring biết **chọn constructor nào**, chứ không đảm bảo Spring biết `maxThreads` tương ứng với key nào.

Đừng trộn lẫn ba câu hỏi:

1. Constructor nào dùng để tạo properties object?
2. Tham số của constructor đó tên gì khi framework quan sát bytecode?
3. Có property nào cung cấp giá trị cho từng tham số và có chuyển đổi được không?

`@ConstructorBinding` giải quyết câu hỏi đầu tiên khi có nhiều lựa chọn. `-parameters` phục vụ câu hỏi thứ hai. File cấu hình, Binder và converter giải quyết câu hỏi thứ ba.

## 13. @DefaultValue, nested object và tên tham số

Với immutable properties, giá trị mặc định có thể được khai báo trên constructor parameter hoặc record component bằng `@DefaultValue`:

~~~java
package example.worker;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @DefaultValue("4") int maxThreads,
        @DefaultValue("5s") Duration pollingInterval,
        @DefaultValue("false") boolean enabled
) {}
~~~

Với YAML:

~~~yaml
worker:
  enabled: true
~~~

khi các field thiếu trong nguồn config, Binder có thể dùng `maxThreads=4`, `pollingInterval=5s` theo giá trị default được khai báo.

Đây là một cơ chế khác hoàn toàn với `-parameters`:

- `-parameters` giúp framework **biết tên tham số**.
- `@DefaultValue` cung cấp một giá trị khi **property tương ứng vắng mặt**.
- ConversionService/Binder chuyển chuỗi default sang kiểu Java.
- Validation có thể tiếp tục kiểm tra giá trị nhận được.

Không nên dùng default như cách bỏ qua sai kiểu, chẳng hạn `worker.max-threads: "many"`. Dù có `@DefaultValue("4")`, dữ liệu hiện diện nhưng không thể chuyển thành số vẫn có thể gây lỗi binding.

### Nested value

~~~java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        String name,
        Retry retry
) {
    public record Retry(int attempts, Duration delay) {}
}
~~~

Với:

~~~yaml
client:
  name: "warehouse"
  retry:
    attempts: 3
    delay: 250ms
~~~

Tên của root constructor parameter `retry` cũng quan trọng để tìm cấu trúc nested. Bên trong, `attempts` và `delay` cũng cần được Binder ánh xạ. Việc có metadata tên tham số nhất quán cho các kiểu sử dụng constructor binding giúp cấu hình nested hoạt động dễ đoán hơn.

## 14. Cách kiểm tra .class bằng javap

**Kiểm tra bytecode sau build** là cách trực tiếp để biết compiler thực sự đã giữ metadata.

Giả sử bạn có:

~~~text
target/classes/example/gateway/GatewayProperties.class
~~~

Chạy:

~~~bash
javap -v -p target/classes/example/gateway/GatewayProperties.class
~~~

Với Gradle:

~~~bash
javap -v -p build/classes/java/main/example/gateway/GatewayProperties.class
~~~

Tùy JDK và platform, bạn cũng có thể dùng tên class cùng classpath:

~~~bash
javap -classpath target/classes -v -p example.gateway.GatewayProperties
~~~

Trong output, tìm method/constructor:

~~~text
public example.gateway.GatewayProperties(
    java.net.URI, java.time.Duration, int);
...
MethodParameters:
  Name                 Flags
  baseUrl
  connectTimeout
  maxRetries
~~~

Đoạn trên là **minh họa phần có ý nghĩa**, không phải toàn bộ output thực tế của `javap`. Quan trọng là tìm được `MethodParameters` cùng tên tham số tương ứng cho constructor.

Nếu output chỉ có các metadata debug, hoặc `MethodParameters` không chứa tên mong muốn, hãy xem lại cách build. Nếu class là record, hãy nhớ record có các quy tắc metadata riêng; kiểm tra thêm một class constructor thường nếu cần xác định convention `-parameters` có đang áp dụng rộng hay không.

**Không dùng kết quả trong thư mục `target/classes` cũ để khẳng định cấu hình hiện tại đúng.** Clean build trước rồi inspect artifact vừa tạo.

## 15. Kiểm tra bằng reflection thay vì chỉ nhìn POM

Một đoạn Java test đơn giản:

~~~java
package example.gateway;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorMetadataCheck {

    public static void main(String[] args) {
        Constructor<?> constructor =
            GatewayProperties.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            System.out.printf(
                "%s: present=%s%n",
                parameter.getName(),
                parameter.isNamePresent()
            );
        }
    }
}
~~~

Nếu class thật được compile với flag và tên tham số được ghi đúng, output có thể là:

~~~text
baseUrl: present=true
connectTimeout: present=true
maxRetries: present=true
~~~

Với class thông thường không có metadata, có thể thấy:

~~~text
arg0: present=false
arg1: present=false
arg2: present=false
~~~

Trong ứng dụng thật, hãy chọn đúng constructor thay vì chỉ dùng index `[0]` khi class có nhiều constructor. Với record, có thể lấy canonical constructor theo các component types hoặc kiểm tra `getRecordComponents()` để hiểu metadata riêng của record.

Trong build CI, một test phản chiếu **class chứa configuration-properties constructor** có thể giúp phát hiện việc module vô tình bị biên dịch thiếu flag.

## 16. Unit test không đủ nếu chỉ tạo object bằng new

Ví dụ test:

~~~java
@Test
void createsObjectDirectly() {
    GatewayProperties properties =
        new GatewayProperties(
            URI.create("https://api.example.invalid"),
            Duration.ofSeconds(3),
            4
        );

    assertEquals(4, properties.getMaxRetries());
}
~~~

Test này kiểm tra **Java constructor có thể gọi được**. Nó không cần Spring Binder tìm tên tham số nên có thể pass ngay cả khi bytecode thiếu `-parameters`. Do đó test như vậy **không chứng minh constructor binding hoạt động**.

Để kiểm tra binding, phải tạo context/Binder phù hợp và đưa property source vào.

## 17. Test binding bằng ApplicationContextRunner

Với Spring Boot Test, có thể dùng `ApplicationContextRunner`:

~~~java
package example.gateway;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsConstructorParameters() {
        runner
            .withPropertyValues(
                "gateway.base-url=https://api.example.invalid",
                "gateway.connect-timeout=3s",
                "gateway.max-retries=4"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                    GatewayProperties.class);

                GatewayProperties properties =
                    context.getBean(GatewayProperties.class);

                assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
                assertThat(properties.getMaxRetries())
                    .isEqualTo(4);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {
    }
}
~~~

Test trên cần project có Spring Boot Test và Assertions phù hợp. Nó thể hiện đường đi thật:

1. Context nạp cấu hình đăng ký `GatewayProperties`.
2. Property source cung cấp giá trị.
3. Binder xác định constructor và tên tham số.
4. Converter chuyển kiểu.
5. Bean được tạo và có giá trị mong đợi.

Nếu context fail trước khi bean được tạo, hãy xem nguyên nhân gốc thay vì mặc định là do `-parameters`. Có thể là registration, prefix, converter, validation hoặc lỗi dependency khác.

### Test thiếu metadata có thể biểu hiện thế nào?

Một build module Java không có `-parameters` có thể khiến test constructor binding thất bại ở lúc Binder xác định constructor parameter names. Tùy phiên bản Spring Boot, thông báo có thể đề cập rằng tên parameter không được xác định hoặc cần biên dịch với `-parameters`.

Khi gặp loại lỗi đó, kiểm tra bytecode trước khi đổi YAML. Nếu cấu hình key và Java constructor đúng nhưng class không có metadata, sửa file YAML không phải giải pháp.

## 18. Spring Framework 6.1 và autowiring theo tên tham số

Có một vấn đề liên quan nhưng cần tách riêng. Với một số trường hợp dependency injection có **nhiều bean cùng type**, Spring có thể dùng **tên tham số constructor** để tìm bean trùng tên khi không có qualifier hoặc ưu tiên khác. Từ Spring Framework 6.1, cơ chế matching theo tên tham số này cần metadata `-parameters`.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientBeans {

    @Bean
    HttpClient primaryClient() {
        return new HttpClient("primary");
    }

    @Bean
    HttpClient archiveClient() {
        return new HttpClient("archive");
    }
}
~~~

Một consumer:

~~~java
@Service
class ArchiveService {

    private final HttpClient archiveClient;

    ArchiveService(HttpClient archiveClient) {
        this.archiveClient = archiveClient;
    }
}
~~~

`HttpClient` ở đây là class giả định. Nếu có hai bean cùng type, framework có thể dùng tên tham số `archiveClient` để disambiguate khi metadata và các điều kiện phù hợp. Không có `-parameters`, ứng dụng có thể báo ambiguity ở tình huống vốn dựa vào tên.

Nhưng **dependency injection theo bean name** không giống **constructor binding từ externalized properties**:

| Trường hợp | Tên tham số được dùng để làm gì? |
| --- | --- |
| `@ConfigurationProperties` constructor binding | Ánh xạ tham số vào property key |
| Constructor injection thông thường | Có thể hỗ trợ chọn bean cùng type khi tên bean khớp |
| Gọi Java constructor bằng `new` | Không cần Spring tìm tên tham số |
| Parse `application.yml` | Không phụ thuộc flag của class Java |

Khi cần chọn một bean trong nhiều bean cùng type, `@Qualifier` hoặc thiết kế tên bean rõ ràng thường đáng tin cậy hơn việc chỉ dựa vào tên tham số.

## 19. Tại sao build bằng IDE chạy được nhưng JAR chạy lại lỗi?

Một hiện tượng phổ biến:

~~~text
Chạy main class từ IDE: thành công.
Đóng gói bằng CI / Maven / Gradle: thất bại khi startup.
Hoặc ngược lại.
~~~

Nguyên nhân có thể là **hai đường compile dùng cấu hình khác nhau**:

- IDE dùng compiler riêng và bật lưu tên tham số.
- Maven hoặc Gradle task không bật `-parameters`.
- Một module dependency đã được build sẵn bằng cấu hình cũ.
- CI dùng phiên bản JDK, Gradle, Maven parent hoặc compiler plugin khác.
- Một jar cache chứa `.class` được build trước khi thêm flag.
- Một task tạo source/compile riêng không kế thừa flag.
- IDE đang chạy từ `out/production` trong khi JAR chứa bytecode từ `target/classes` hoặc `build/classes/java/main`.

Cách tiếp cận đúng:

1. Xác định **artifact nào** đang được khởi động.
2. Xác định class `@ConfigurationProperties` thực tế được load từ JAR/module nào.
3. Kiểm tra `MethodParameters` trên **class trong artifact đó**.
4. Kiểm tra build system thực sự gọi Java compiler với `-parameters`.
5. Sửa cấu hình build ở module sở hữu source.
6. Clean, rebuild dependency/module, sau đó chạy lại cùng artifact.

Không nên chỉ sửa setting “Store information about method parameters” trong IDE nếu CI mới là nơi phát hành production artifact. Nguồn chân lý phải là build reproducible của repository.

## 20. Cách kiểm tra JAR hoặc thư viện ngoài

Với Java application đóng gói thành JAR, class trong output có thể nằm ở đường dẫn khác so với `target/classes`. Một Spring Boot executable JAR thường đóng gói application classes dưới cấu trúc riêng (chẳng hạn `BOOT-INF/classes`) và dependencies trong thư mục libs.

Có thể kiểm tra nội dung JAR:

~~~bash
jar tf target/app.jar
~~~

Sau đó xác định đúng class cần xem và giải nén ra một thư mục tạm phục vụ kiểm tra bytecode nếu cần. Với thư viện JAR thông thường có thể dùng `javap -classpath <library.jar> -v -p ...` trực tiếp khi classpath/kiểu class phù hợp.

Điểm quan trọng không phải lệnh cụ thể, mà là **đọc bytecode trong đúng artifact chạy ở runtime**. Một module `shared-config` đã publish vào repository nội bộ có thể khác với source `shared-config` trong working tree hiện tại.

Nếu một dependency third-party đã compile thiếu metadata và bạn không sở hữu source/build của nó, thêm `-parameters` ở module chính không tự phục hồi tên tham số của dependency đó. Cần dùng bản dependency được biên dịch đúng, cập nhật thư viện hoặc chọn mô hình binding phù hợp.

## 21. Những lỗi thường bị nhầm với thiếu -parameters

Không phải mọi lỗi `Failed to bind properties` đều là lỗi compiler. Hãy phân loại:

| Triệu chứng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| Không có bean `GatewayProperties` | Thiếu `@EnableConfigurationProperties` hoặc scan |
| Binder báo không nhận diện được tên constructor parameter | Metadata `-parameters`, loại class, artifact đã compile |
| `gateway.timeout` không bind | Prefix/key sai, không có nguồn property, tên Java khác |
| `"many"` không bind sang `int` | Lỗi conversion, không phải metadata tên |
| `-1` không hợp lệ với `@Min(1)` | Validation |
| Nested object null | Chưa cung cấp nested values hoặc thiếu default/validation phù hợp |
| Nhiều bean cùng type làm constructor injection ambiguous | Cần `@Qualifier` hoặc cơ chế ưu tiên phù hợp |
| IDE chạy được nhưng CI fail | Khác compiler args/artifact/dependency |
| Có `-parameters` nhưng không dùng constructor binding | Có thể là bean được tạo bằng `@Component`/`@Bean`, sai registration |
| Class có nhiều constructor không rõ lựa chọn | Cần chỉ ra constructor binding phù hợp |

Một ví dụ dễ nhầm:

~~~yaml
gateway:
  max-retries: "several"
~~~

Java:

~~~java
public GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries) {
    // ...
}
~~~

Dù class có `-parameters`, Binder không thể biến `"several"` thành `int` theo quy tắc thông thường. Phải sửa dữ liệu hoặc định nghĩa conversion riêng; thêm compiler flag lần nữa không giúp.

Ngược lại, nếu property đúng:

~~~yaml
gateway:
  max-retries: 4
~~~

nhưng Binder không xác định được tên constructor parameter, lỗi nằm trước giai đoạn ánh xạ key và conversion; lúc này kiểm tra bytecode đúng hướng hơn.

## 22. Không tự sửa lỗi bằng cách thêm @Component

Một “cách sửa” nguy hiểm:

~~~java
@Component
@ConfigurationProperties(prefix = "gateway")
public final class GatewayProperties {
    public GatewayProperties(
            URI baseUrl, Duration connectTimeout, int maxRetries) {
        // ...
    }
}
~~~

`@Component` có thể khiến Spring cố tạo object qua cơ chế dependency injection thông thường. Các constructor arguments như `URI`, `Duration` và `int` vốn là **giá trị property** chứ không phải Spring beans được đăng ký sẵn. Vấn đề có thể chuyển từ “không bind được property” sang “không autowire được dependency”.

Dùng:

~~~java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

và đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
class GatewayConfiguration {}
~~~

**Cơ chế đăng ký đúng** và **metadata tên tham số** là hai yêu cầu độc lập. Không dùng annotation của cơ chế này để che lỗi cơ chế khác.

## 23. Có cần -parameters khi dùng setter binding?

Một kiểu mutable JavaBean-style:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "legacy.client")
public class LegacyClientProperties {

    private int retries = 3;

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }
}
~~~

Khi dùng setter binding phù hợp, Binder chủ yếu dựa trên **tên JavaBean properties** (getter/setter), không phải tên các tham số của một constructor nhận nhiều giá trị. Vì vậy, lỗi thiếu tên tham số constructor không phải vấn đề chính của mẫu này.

Tuy nhiên:

- Project vẫn có thể cần `-parameters` cho các trường hợp framework khác.
- Không nên chuyển một immutable properties class thành mutable chỉ để “tránh compiler flag” khi constructor binding vốn là lựa chọn thiết kế tốt.
- Getter/setter phải tuân theo JavaBean conventions để Binder nhận diện đúng.
- Type có nhiều field vẫn cần validation và default phù hợp.

Cơ chế đăng ký kiểu JavaBean có thể khác constructor-bound record, nhưng hai cách cùng nhắm tới typed configuration. Hãy chọn theo nhu cầu bất biến, validation và style codebase, không vì một vấn đề build có thể sửa ở gốc.

## 24. @Name và tên key không thể dùng làm Java identifier

Đôi lúc property key tương ứng với một từ khóa Java, ví dụ:

~~~yaml
service:
  import: "catalog"
~~~

Không thể đặt constructor parameter Java có tên `import` vì `import` là keyword. Spring Boot cung cấp annotation `@Name` trong binding API để chỉ định tên property cần dùng thay vì tên Java parameter:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.Name;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @Name("import") String importValue
) {}
~~~

Đây là trường hợp đặc biệt **chủ ý ánh xạ một tên không thể viết thành Java identifier**. Không nên lạm dụng `@Name` trên mọi tham số để né yêu cầu `-parameters` cho phần còn lại của ứng dụng.

Nếu tên cấu hình do dự án tự quản lý, tốt nhất chọn key dễ hiểu và tương thích naming convention như `service.import-mode`, rồi dùng tham số `importMode`. Việc dùng `@Name` có giá trị khi hợp đồng property hiện có hoặc key bắt buộc không thể đổi.

## 25. Lombok, code generation và constructor được sinh

Với Lombok hoặc code generator, source file có thể chỉ có field:

~~~java
@Getter
@RequiredArgsConstructor
public class GeneratedLikeProperties {
    private final String name;
    private final int maxRetries;
}
~~~

Constructor thực tế được công cụ sinh ra trong quá trình compile. Nếu class đó được dùng cho constructor binding, điều quan trọng vẫn là **bytecode của constructor được dùng** có tên parameter phù hợp.

Một số rủi ro:

- Annotation processor của IDE khác với Maven/Gradle build.
- Constructor được sinh có signature khác ý định.
- Một constructor bổ sung làm Binder không còn suy ra constructor duy nhất.
- Plugin/build step tạo source sau khi compiler flags đã được thiết lập cho một task khác.
- Dependency publish chứa bytecode không giống source đang mở trong IDE.

Vì vậy, không nên coi “có Lombok” hoặc “có record” là bằng chứng rằng mọi case đều không cần `-parameters`. Hãy xác định code generation và compiler nào tạo class cuối cùng.

Khi phát triển typed externalized configuration, record hoặc class constructor thủ công nhỏ thường giúp dễ đọc hơn một chuỗi annotation sinh constructor phức tạp.

## 26. Maven, Gradle, IDE và CI: một hợp đồng build

Một dự án tốt nên tránh mỗi môi trường tạo ra bytecode khác nhau.

| Nơi build | Điều cần đảm bảo |
| --- | --- |
| Maven local | `maven-compiler-plugin` / parent cấp `-parameters` |
| Gradle local | JavaCompile task có `-parameters` |
| IDE | Tốt nhất delegate build/run cho Maven/Gradle hoặc đồng bộ compiler settings |
| CI | Dùng cùng wrapper, toolchain và build logic được version-control |
| Module thư viện | Tự compile với flag nếu chứa constructor-bound properties |
| Packaging/release | Kiểm tra artifact mới nhất chứa class đúng |
| Unit/integration test | Có test dùng Binder thực sự, không chỉ `new Properties(...)` |

Nếu dự án có nhiều module, việc đặt flag ở một nơi **chỉ có hiệu lực cho những task/module thực sự kế thừa nó**. Kiểm tra build convention cùng dependency graph thay vì suy luận từ root POM hoặc root Gradle script.

### Tại sao clean build có ích?

Build tăng dần có thể tái sử dụng class file được compile trước khi bạn sửa plugin settings. Sau khi thêm `-parameters`, nên clean rồi compile lại các module chứa class cấu hình. Sau đó kiểm tra `MethodParameters` trong artifact mới tạo.

Không cần xóa cache toàn hệ thống một cách mù quáng. Mục tiêu là bảo đảm class có vấn đề thực sự được compile lại với cấu hình mới.

## 27. Phân biệt cờ compiler và annotation processor

Một nhầm lẫn khác:

- `-parameters` là **cờ của javac** để sinh metadata tên tham số.
- `spring-boot-configuration-processor` là **annotation processor** thường dùng để sinh metadata cấu hình cho công cụ/IDE gợi ý key.

Ví dụ dependency `spring-boot-configuration-processor` có thể tạo `META-INF/spring-configuration-metadata.json` giúp autocomplete và documentation properties, nhưng **không thay thế metadata `MethodParameters` của Java constructor**.

Ngược lại, có `-parameters` không tự sinh configuration metadata JSON cho IDE nếu dự án không cấu hình annotation processor tương ứng.

Đây là hai lớp metadata khác nhau:

~~~text
javac -parameters
      |
      v
.class -> MethodParameters
      |
      v
Reflection / Spring Binder có thể biết tên constructor parameters

spring-boot-configuration-processor
      |
      v
META-INF/spring-configuration-metadata.json
      |
      v
IDE có thể gợi ý tên key, description, type
~~~

Không nên giải lỗi startup thiếu constructor parameter names bằng cách chỉ thêm `spring-boot-configuration-processor` dependency.

## 28. Phân biệt -parameters với -D... hoặc cấu hình runtime

Lệnh chạy như:

~~~bash
java -Dspring.profiles.active=prod -jar app.jar
~~~

thiết lập một **Java system property** cho Spring Environment. Nó thay đổi cấu hình runtime theo profile.

Lệnh:

~~~bash
javac -parameters ...
~~~

lại thay đổi **metadata được compiler ghi vào class file**. Hai việc hoàn toàn khác nhau.

Các lựa chọn không tương đương:

| Cách thay đổi | Có thể sửa vấn đề thiếu tên constructor parameter? |
| --- | --- |
| Thêm `-parameters` vào `javac` rồi rebuild | Có, đối với class cần metadata |
| Thêm `--spring.profiles.active=prod` khi chạy | Không |
| Đổi `application.yml` | Không, trừ khi lỗi thật ra là property key/value |
| Thêm `spring-boot-configuration-processor` | Không thay thế compiler flag |
| Thêm `@Component` vào record | Không; có thể tạo lỗi registration khác |
| Bật Java debug symbols `-g` | Không phải giải pháp thay thế đáng tin cậy |
| Chuyển `getProperty` sang `@Value` ở service khác | Không xử lý metadata constructor của typed properties |

Nhớ rằng `-parameters` áp dụng cho **class được compile**, không phải toàn bộ tiến trình JVM sau khi chạy.

## 29. Một ví dụ Maven hoàn chỉnh ở mức module

Giả sử module `config-model` chứa `GatewayProperties` và không dùng starter parent:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>config-model</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đoạn POM trên là **mẫu phần build độc lập để minh họa**, không phải một cấu hình đầy đủ dependencies để compile mọi ví dụ Spring Boot. Trong project thật, cần các dependencies và parent/plugin versions phù hợp. `release=17` chỉ là ví dụ cho dự án Spring Boot 3.x sử dụng Java 17; hãy dùng target Java của project.

Khi dùng cả `maven.compiler.parameters=true` và `<parameters>true</parameters>`, hai cấu hình là **dư thừa**, không nhất thiết phải giữ cả. Chọn một cách phù hợp với conventions. Nội dung mẫu cố tình cho thấy có thể đặt ở cả property và plugin config, nhưng triển khai thực tế nên chỉ cần một đường rõ ràng.

Sau compile, inspect:

~~~bash
./mvnw clean compile
javap -classpath target/classes -v -p example.gateway.GatewayProperties
~~~

Nếu properties class nằm trong một module khác, chạy lệnh cho module ấy và chỉ đúng classpath của module đó.

## 30. Một ví dụ Gradle multi-module

Giả sử cấu trúc:

~~~text
root/
  settings.gradle
  build.gradle
  config-model/
    build.gradle
    src/main/java/example/gateway/GatewayProperties.java
  web-app/
    build.gradle
    src/main/java/example/Application.java
~~~

Trong `config-model/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Trong `web-app/build.gradle`, app có thể dùng plugin Spring Boot và dependency tới module cấu hình:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation project(':config-model')
}
~~~

Ví dụ này minh họa **flag nằm ở nơi class được biên dịch**. Nếu `GatewayProperties` sống trong `config-model`, configuration của `web-app` không thể tự thêm metadata vào class đã compile bởi `config-model`.

Trong dự án thật, Gradle plugin/dependency versions, repository và convention thường được khai báo tập trung. Mục tiêu ở đây là nhìn rõ trách nhiệm từng module chứ không đưa một skeleton build đầy đủ.

## 31. Checklist chẩn đoán theo thứ tự ngắn

Khi gặp lỗi constructor binding, kiểm tra:

1. **Source:** properties class có `@ConfigurationProperties(prefix = ...)` đúng chưa?
2. **Registration:** có `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` và configuration class được nạp không?
3. **Constructor:** class có một constructor rõ ràng hay nhiều constructor cần chỉ định `@ConstructorBinding`?
4. **Tên tham số:** source code đặt tham số đúng với property cần bind không?
5. **Bytecode:** `javap -v -p` có `MethodParameters` tương ứng không?
6. **Build task:** module sở hữu class có `-parameters` không?
7. **Artifact:** đang chạy đúng JAR/class mới build hay một dependency cũ?
8. **Property source:** có key hợp lệ trong profile và config import đang active không?
9. **Conversion:** dữ liệu có đổi được sang `int`, `Duration`, `URI`, enum...? 
10. **Validation:** dữ liệu bind được nhưng có ràng buộc bị vi phạm không?
11. **CI/IDE:** compiler args ở local và pipeline có nhất quán không?
12. **Test:** có test thực sự khởi tạo configuration-properties bean bằng Binder không?

Sơ đồ quyết định:

~~~text
Service inject Properties bị thiếu?
    |
    +-- Có --> Kiểm tra registration và context composition
    |
    +-- Không, nhưng binding thất bại
         |
         +-- Binder không xác định tên constructor parameter?
         |      |
         |      +-- Có --> Kiểm tra -parameters và bytecode
         |
         +-- Có tên nhưng key không khớp?
         |      |
         |      +-- Có --> Kiểm tra prefix/naming/source
         |
         +-- Value không đổi được sang kiểu Java?
         |      |
         |      +-- Có --> Sửa dữ liệu/converter
         |
         +-- Value đúng kiểu nhưng sai ràng buộc?
                |
                +-- Có --> Sửa validation/config contract
~~~

## 32. Bài tập thực hành

**Yêu cầu:** tạo immutable properties object đại diện cho cấu hình HTTP client; dùng constructor binding và kiểm chứng class file có tên tham số.

### Bước 1 — Viết YAML

~~~yaml
pricing:
  endpoint: "https://pricing.example.invalid/v1"
  timeout: 2s
  retry-count: 3
~~~

### Bước 2 — Viết class Java thường

~~~java
package example.pricing;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pricing")
public final class PricingProperties {

    private final URI endpoint;
    private final Duration timeout;
    private final int retryCount;

    public PricingProperties(
            URI endpoint, Duration timeout, int retryCount) {
        this.endpoint = endpoint;
        this.timeout = timeout;
        this.retryCount = retryCount;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

### Bước 3 — Đăng ký

~~~java
package example.pricing;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PricingProperties.class)
class PricingConfiguration {}
~~~

### Bước 4 — Bật compiler flag

Với Maven:

~~~xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Hoặc Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

### Bước 5 — Clean compile và inspect class

Maven:

~~~bash
./mvnw clean compile
javap -classpath target/classes -v -p example.pricing.PricingProperties
~~~

Quan sát xem phần `MethodParameters` của constructor có `endpoint`, `timeout`, `retryCount`.

### Bước 6 — Bind trong Spring context

Khởi động ứng dụng đã nạp `PricingConfiguration` hoặc viết `ApplicationContextRunner` test cung cấp các key `pricing.*`. Đọc bean `PricingProperties` và đối chiếu:

~~~text
endpoint   = https://pricing.example.invalid/v1
timeout    = 2 giây
retryCount = 3
~~~

### Bước 7 — Tự thay đổi một yếu tố

Thử lần lượt:

- Bỏ `-parameters` ở module chứa `PricingProperties`, clean compile, quan sát tên param ở bytecode và kết quả binding.
- Giữ `-parameters` nhưng đổi YAML `retry-count: "many"`; xác định loại lỗi.
- Đổi `@ConfigurationProperties(prefix = "pricing")` thành prefix khác mà không đổi YAML; quan sát kết quả.
- Bỏ `@EnableConfigurationProperties` và không dùng scan khác; tìm lỗi bean registration.
- Chuyển class sang record, rồi so sánh metadata của record với class thông thường.

Từ các tình huống này, cần tách được **compiler metadata**, **bean registration**, **binding data** và **validation**.

## 33. Ghi nhớ

Khi dùng constructor binding cho `@ConfigurationProperties`, Spring Boot cần xác định tên các constructor parameter để map `baseUrl` sang `base-url`, `retryCount` sang `retry-count` và các giá trị cấu hình khác. Với Java class thông thường, **`javac -parameters`** giúp lưu tên tham số vào metadata `MethodParameters` của `.class` để reflection có thể đọc.

Spring Boot Maven parent hoặc Spring Boot Gradle plugin thường đã cấu hình tùy chọn này; dự án dùng BOM, parent riêng, multi-module, thư viện hoặc đường compile tùy chỉnh cần xác nhận flag tại **module tạo ra bytecode**. Maven có thể dùng `<parameters>true</parameters>`; Gradle có thể thêm `"-parameters"` cho `JavaCompile`; `javap -v -p` và reflection giúp kiểm chứng artifact cuối cùng.

**Đừng nhầm `-parameters` với `@ConstructorBinding`, `@EnableConfigurationProperties`, `@DefaultValue` hoặc annotation processor.** Mỗi cơ chế giải một vấn đề khác nhau: chọn constructor, đăng ký bean, cung cấp mặc định, lưu metadata và chuyển đổi property.

Tài liệu tham khảo: Spring Boot Reference Guide — Externalized Configuration (Constructor Binding); Apache Maven Compiler Plugin — parameters; Gradle CompileOptions — compilerArgs; Spring Framework Reference — Annotation-based Autowiring.
