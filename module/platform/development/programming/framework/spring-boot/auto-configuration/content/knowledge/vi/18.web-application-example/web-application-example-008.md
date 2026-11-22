# Đối chiếu bean và Condition Evaluation Report trong ứng dụng web mà không tạo API nghiệp vụ giả

## 1. Mục tiêu: quan sát hạ tầng Spring MVC có sẵn

Khi học Spring Boot auto-configuration, ta thường muốn biết:

- Spring Boot đã tạo những bean web nào?
- Bean nào đến từ Servlet infrastructure, bean nào đến từ Spring MVC?
- Khi thay một property, bean nào xuất hiện hoặc biến mất?
- Condition nào trong report giải thích sự thay đổi đó?
- Những bean nền khác có giữ nguyên không?

Không nhất thiết phải viết một `@RestController` chỉ để có endpoint phục vụ việc quan sát. Chính Spring Boot đã cung cấp một hệ thống bean thực tế để kiểm tra: `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, `HttpMessageConverters`, các filter và embedded web server.

Bài này dùng một ứng dụng **không khai báo controller nghiệp vụ**. Ứng dụng chỉ khởi động Spring MVC, in danh sách bean hạ tầng và expose Actuator `/actuator/conditions` để đọc Condition Evaluation Report. Ta thay đúng một property có sẵn của Spring MVC để đối chiếu hai lần chạy.

Điểm quan trọng: `/actuator/conditions` là endpoint vận hành do Actuator cung cấp. Nó không phải API nghiệp vụ tự xây cho ví dụ.

## 2. Phân biệt bean registry với Condition Evaluation Report

Hai nguồn quan sát này trả lời hai câu hỏi khác nhau:

| Nguồn | Cho biết | Không tự chứng minh |
| --- | --- | --- |
| Bean registry / `ApplicationContext` | Bean nào thực sự có mặt, tên bean, số lượng theo kiểu | Vì sao condition được đánh giá như vậy |
| Condition Evaluation Report | Auto-configuration/`@Bean` nào match hoặc không match, condition và message liên quan | Bean có thực sự được sử dụng đúng trong luồng nghiệp vụ |
| Test / assertion | Kết quả có đáp ứng hợp đồng mong muốn không | Toàn bộ hành vi runtime ở mọi môi trường |

Ví dụ, report có thể cho thấy `WebMvcAutoConfiguration#hiddenHttpMethodFilter` không match vì property chưa bật. Bean registry xác nhận không có `HiddenHttpMethodFilter`. Khi bật property, report chuyển sang positive match và bean xuất hiện.

Ta cần **đối chiếu cả hai**. Chỉ nhìn report có thể bỏ sót bean custom do ứng dụng tạo; chỉ nhìn bean registry thì không biết lý do default được tạo hoặc nhường chỗ.

## 3. Các bean web thực tế cần quan sát

### 3.1. Servlet container và DispatcherServlet

`ServletWebServerFactory` đại diện cho factory tạo embedded server (ví dụ Tomcat). `DispatcherServlet` là Front Controller của Spring MVC: nó nhận request từ Servlet container rồi phối hợp với các thành phần MVC để xử lý.

Một ứng dụng dùng `spring-boot-starter-web` thông thường sẽ có các bean tương ứng khi được khởi động ở Servlet web mode.

### 3.2. Handler mapping và handler adapter

- `RequestMappingHandlerMapping` tìm mapping cho các method controller được khai báo bằng annotation như `@RequestMapping`, `@GetMapping`, `@PostMapping`.
- `RequestMappingHandlerAdapter` thực thi các handler method đã được mapping, xử lý argument resolution, return value và các cơ chế liên quan.

Hai bean này là hạ tầng framework. Chúng vẫn có thể tồn tại khi ứng dụng **chưa khai báo controller nghiệp vụ nào**.

### 3.3. HTTP message converters

`HttpMessageConverters` là abstraction do Spring Boot cung cấp để quản lý các `HttpMessageConverter` được dùng cho đọc request body và ghi response body. Danh sách converter thực tế phụ thuộc classpath và cấu hình.

Ví dụ, nếu Jackson có mặt trên classpath, converter JSON tương ứng thường được cấu hình. Không nên kết luận một converter luôn tồn tại chỉ vì starter-web có mặt; hãy quan sát type và điều kiện thực tế.

### 3.4. Các filter của Spring MVC

Ví dụ này đối chiếu hai filter thật:

- `FormContentFilter`: hỗ trợ đọc form body cho các HTTP method như PUT/PATCH/DELETE. Trong cấu hình Boot 3.3, auto-configuration bật filter này mặc định nếu chưa có bean thay thế.
- `HiddenHttpMethodFilter`: cho phép form HTML dùng field `_method` để biểu diễn method như PUT/DELETE qua một request POST. Bean này chỉ được auto-configure khi property `spring.mvc.hiddenmethod.filter.enabled` được bật; mặc định là false.

Hai filter là ví dụ tốt để phân biệt **bean nền vẫn giữ nguyên** với **một bean tùy chọn thay đổi theo property**.

## 4. Condition thật trong Spring Boot 3.3

Trong `WebMvcAutoConfiguration`, method `hiddenHttpMethodFilter()` có hai điều kiện:

```java
@Bean
@ConditionalOnMissingBean(HiddenHttpMethodFilter.class)
@ConditionalOnProperty(
        prefix = "spring.mvc.hiddenmethod.filter",
        name = "enabled")
public OrderedHiddenHttpMethodFilter hiddenHttpMethodFilter() {
    return new OrderedHiddenHttpMethodFilter();
}
```

Đây là đoạn trích cấu trúc của auto-configuration Spring Boot 3.3; không cần chép method này vào ứng dụng.

Hai condition được kết hợp theo phép AND:

1. `@ConditionalOnMissingBean(HiddenHttpMethodFilter.class)`: chưa có bean `HiddenHttpMethodFilter` do người dùng hoặc cấu hình khác cung cấp.
2. `@ConditionalOnProperty(prefix = "spring.mvc.hiddenmethod.filter", name = "enabled")`: property `spring.mvc.hiddenmethod.filter.enabled` có giá trị phù hợp. Với annotation không chỉ rõ `havingValue`, giá trị tồn tại và khác chuỗi `false` sẽ match.

Do đó:

| Property | Bean custom cùng kiểu | Kết quả |
| --- | --- | --- |
| Không khai báo / false | Không | Không tạo filter mặc định |
| true | Không | Tạo `OrderedHiddenHttpMethodFilter` mặc định |
| true | Có | Default nhường chỗ cho bean custom |
| false | Có | Bean custom vẫn tồn tại; property chỉ chặn default auto-config |

`OrderedHiddenHttpMethodFilter` là implementation của `HiddenHttpMethodFilter`. Vì vậy khi kiểm tra bean, có thể dùng kiểu cha `HiddenHttpMethodFilter.class` để thấy cả implementation mặc định lẫn bean custom.

Trong Condition Evaluation Report, source thường được nhận diện là `WebMvcAutoConfiguration#hiddenHttpMethodFilter`. Khi property false, source xuất hiện trong `negativeMatches` với `OnPropertyCondition` không match; `OnBeanCondition` có thể vẫn match vì chưa có bean filter. Khi property true và không có custom bean, source chuyển sang `positiveMatches` với cả hai condition match.

## 5. Ví dụ ứng dụng Spring Boot 3.3.5 / Java 17+ không có controller nghiệp vụ

Ta tạo một ứng dụng thật với Spring MVC và Actuator. Chương trình in bean names từ context sau khi khởi động. Không tạo `@RestController`, DTO nghiệp vụ, service nghiệp vụ hoặc endpoint giả.

### 5.1. Cấu trúc thư mục

```text
web-infrastructure-observer/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   └── WebInfrastructureApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/
            ├── WebInfrastructureTests.java
            └── HiddenMethodFilterEnabledTests.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>web-infrastructure-observer</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`spring-boot-starter-web` đưa Spring MVC và embedded Servlet container vào runtime classpath. `spring-boot-starter-actuator` cung cấp endpoint condition report. Không cần thêm dependency cho controller hoặc API nghiệp vụ.

### 5.3. `src/main/resources/application.properties`

```properties
server.port=8080
management.endpoints.web.exposure.include=health,conditions
```

Ta chỉ expose `health` và `conditions` để quan sát. Endpoint Actuator vẫn cần được giới hạn truy cập phù hợp khi đưa ứng dụng lên môi trường dùng chung hoặc production.

### 5.4. `src/main/java/demo/WebInfrastructureApplication.java`

```java
package demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.web.filter.FormContentFilter;
import org.springframework.web.filter.HiddenHttpMethodFilter;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@SpringBootApplication
public class WebInfrastructureApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebInfrastructureApplication.class, args);
    }

    @Bean
    ApplicationRunner printWebInfrastructure(ApplicationContext context) {
        return args -> {
            printBeanNames(context, ServletWebServerFactory.class);
            printBeanNames(context, DispatcherServlet.class);
            printBeanNames(context, RequestMappingHandlerMapping.class);
            printBeanNames(context, RequestMappingHandlerAdapter.class);
            printBeanNames(context, HttpMessageConverters.class);
            printBeanNames(context, FormContentFilter.class);
            printBeanNames(context, HiddenHttpMethodFilter.class);
        };
    }

    private static void printBeanNames(
            ApplicationContext context, Class<?> beanType) {

        String[] names = context.getBeanNamesForType(beanType);

        System.out.printf("%s=%s%n",
                beanType.getSimpleName(),
                names.length == 0 ? "[]" : Arrays.toString(names));
    }
}
```

`ApplicationRunner` chỉ đọc bean names từ `ApplicationContext` sau khi context khởi động. Các kiểu được hỏi đều là thành phần hạ tầng Spring Boot/Spring MVC:

- `ServletWebServerFactory`: factory cho embedded server.
- `DispatcherServlet`: front controller.
- `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter`: mapping và thực thi handler method.
- `HttpMessageConverters`: quản lý converter HTTP.
- `FormContentFilter` và `HiddenHttpMethodFilter`: filter của Spring MVC.

Không có controller nghiệp vụ. Việc có các bean handler mapping/adapter không có nghĩa ứng dụng đã định nghĩa một endpoint nghiệp vụ.

### 5.5. Test bean hạ tầng mặc định: `WebInfrastructureTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.web.filter.FormContentFilter;
import org.springframework.web.filter.HiddenHttpMethodFilter;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebInfrastructureTests {

    @Autowired
    ApplicationContext context;

    @Test
    void servletAndMvcInfrastructureIsPresentWithoutBusinessController() {
        assertThat(context.getBeansOfType(DispatcherServlet.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(RequestMappingHandlerMapping.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(RequestMappingHandlerAdapter.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(HttpMessageConverters.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(FormContentFilter.class))
                .isNotEmpty();
    }

    @Test
    void hiddenMethodFilterIsAbsentByDefault() {
        assertThat(context.getBeansOfType(HiddenHttpMethodFilter.class))
                .isEmpty();
    }
}
```

### 5.6. Test khi bật property: `HiddenMethodFilterEnabledTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.web.filter.HiddenHttpMethodFilter;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.mvc.hiddenmethod.filter.enabled=true"
)
class HiddenMethodFilterEnabledTests {

    @Autowired
    ApplicationContext context;

    @Test
    void hiddenMethodFilterIsCreatedWhenPropertyIsEnabled() {
        assertThat(context.getBeansOfType(HiddenHttpMethodFilter.class))
                .hasSize(1);
    }
}
```

Các test khởi động Servlet web context thực sự với cổng ngẫu nhiên. Chúng không cần gọi API nghiệp vụ: mục tiêu là xác minh các bean framework có mặt và bean tùy chọn xuất hiện đúng khi property bật.

## 6. Chạy hai lần với cùng một artifact

Yêu cầu JDK 17+ và Maven. Từ thư mục `web-infrastructure-observer`:

```bash
mvn -q test
mvn -q -DskipTests package
```

### Lần A — tắt HiddenHttpMethodFilter

Khởi động:

```bash
java -jar target/web-infrastructure-observer-0.0.1-SNAPSHOT.jar --spring.mvc.hiddenmethod.filter.enabled=false
```

ApplicationRunner in ra danh sách bean. Với Spring Boot 3.3.5 và dependencies ở trên, các bean cốt lõi dự kiến có dạng:

```text
ServletWebServerFactory=[tomcatServletWebServerFactory]
DispatcherServlet=[dispatcherServlet]
RequestMappingHandlerMapping=[requestMappingHandlerMapping]
RequestMappingHandlerAdapter=[requestMappingHandlerAdapter]
HttpMessageConverters=[messageConverters]
FormContentFilter=[formContentFilter]
HiddenHttpMethodFilter=[]
```

Tên bean là tên do cấu hình framework đăng ký; nếu ứng dụng thêm cấu hình hoặc đổi embedded server, tên/số lượng một số bean có thể khác. Đối chiếu type trước, sau đó mới so tên.

Lưu Condition Evaluation Report trong một PowerShell terminal khác:

```powershell
$off = Invoke-RestMethod 'http://localhost:8080/actuator/conditions'
$off | ConvertTo-Json -Depth 100 |
    Set-Content -Encoding utf8 .\conditions-off.json
```

### Lần B — bật HiddenHttpMethodFilter

Dừng process A bằng Ctrl+C. Khởi động cùng JAR với đúng một property thay đổi:

```bash
java -jar target/web-infrastructure-observer-0.0.1-SNAPSHOT.jar --spring.mvc.hiddenmethod.filter.enabled=true
```

Output khác biệt quan trọng:

```text
FormContentFilter=[formContentFilter]
HiddenHttpMethodFilter=[hiddenHttpMethodFilter]
```

Các bean hạ tầng cốt lõi như `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` và `HttpMessageConverters` vẫn được giữ. Bean `HiddenHttpMethodFilter` xuất hiện do property đã bật.

Lưu report thứ hai:

```powershell
$on = Invoke-RestMethod 'http://localhost:8080/actuator/conditions'
$on | ConvertTo-Json -Depth 100 |
    Set-Content -Encoding utf8 .\conditions-on.json
```

### 6.1. Điều gì thay đổi trong report?

Tìm source:

```text
WebMvcAutoConfiguration#hiddenHttpMethodFilter
```

Khi property false:

- Source thường nằm trong `negativeMatches`.
- `OnPropertyCondition` không match vì property không bật.
- `OnBeanCondition` có thể vẫn match vì chưa có bean `HiddenHttpMethodFilter` custom.
- Method `hiddenHttpMethodFilter()` không đăng ký bean mặc định.

Khi property true:

- Source chuyển sang `positiveMatches`.
- `OnPropertyCondition` match.
- `OnBeanCondition` vẫn match nếu không có bean custom.
- Bean mặc định `hiddenHttpMethodFilter` được đăng ký.

Các source khác của `WebMvcAutoConfiguration` vẫn có thể nằm trong positive/negative matches tùy dependency, property và classpath. Không nên kỳ vọng toàn bộ report giống nhau; tập trung so sánh đúng source liên quan.

## 7. Lọc và so sánh report bằng PowerShell

Condition report là JSON có các key động theo tên class hoặc bean method. Ta có thể lấy riêng source cần so sánh thay vì diff toàn bộ file.

Tạo hàm sau trong PowerShell:

```powershell
function Get-ConditionRows {
    param(
        [string]$Path,
        [string]$Source
    )

    $report = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $context = $report.contexts.application
    $rows = @()

    $positive = $context.positiveMatches.PSObject.Properties[$Source]
    if ($null -ne $positive) {
        foreach ($item in $positive.Value) {
            $rows += [pscustomobject]@{
                State = "positive"
                Condition = $item.condition
                Message = $item.message
            }
        }
    }

    $negative = $context.negativeMatches.PSObject.Properties[$Source]
    if ($null -ne $negative) {
        foreach ($item in $negative.Value.notMatched) {
            $rows += [pscustomobject]@{
                State = "notMatched"
                Condition = $item.condition
                Message = $item.message
            }
        }

        foreach ($item in $negative.Value.matched) {
            $rows += [pscustomobject]@{
                State = "matched"
                Condition = $item.condition
                Message = $item.message
            }
        }
    }

    return $rows
}

$source = 'WebMvcAutoConfiguration#hiddenHttpMethodFilter'

$before = Get-ConditionRows -Path '.\conditions-off.json' -Source $source
$after = Get-ConditionRows -Path '.\conditions-on.json' -Source $source

'--- OFF ---'
$before | Format-Table -Wrap

'--- ON ---'
$after | Format-Table -Wrap

'--- DIFF ---'
Compare-Object $before $after -Property State, Condition, Message
```

`Compare-Object` hiển thị các entry chỉ có ở một phía hoặc có trạng thái/message khác. Đây là diff của **một source đã chọn**, không phải diff tổng thể mọi auto-configuration.

Nếu source không xuất hiện ở cả hai phía, kiểm tra:

- Auto-configuration có được nạp không?
- Ứng dụng có đang chạy Servlet web context không?
- Có dùng Spring MVC hay WebFlux?
- Phiên bản Boot có đúng không?
- Tên source trong JSON có đúng với class/method đang quan sát không?

Không hard-code toàn bộ message của report vào test vì message và source set có thể thay đổi giữa các phiên bản Boot.

## 8. Đọc report và bean inventory theo đúng thứ tự

Một quy trình điều tra hiệu quả:

1. **Xác nhận loại context:** đây có phải Servlet web application không? `WebMvcAutoConfiguration` chỉ áp dụng khi điều kiện web/classpath phù hợp và chưa có `WebMvcConfigurationSupport` thay thế.
2. **Xem class-level condition:** `WebMvcAutoConfiguration` có match không? Nếu class bị loại, không nên tìm method condition của bean bên trong như thể method vẫn được đánh giá độc lập.
3. **Tìm method source:** ví dụ `WebMvcAutoConfiguration#hiddenHttpMethodFilter`.
4. **Đọc từng condition:** `OnPropertyCondition`, `OnBeanCondition`... Condition nào không match? Những condition nào vẫn match?
5. **Đối chiếu bean theo type:** gọi `getBeanNamesForType` hoặc `getBeansOfType` để xác nhận bean thật sự có mặt.
6. **Đối chiếu tên bean:** tên giúp tìm đúng factory method hoặc cấu hình tạo bean, nhưng type mới cho biết contract bean đang cung cấp.
7. **Kiểm tra consumer:** nếu một bean hạ tầng biến mất, có filter/handler/consumer nào cần nó không? Ứng dụng có khởi động được và tính năng liên quan có còn hoạt động không?
8. **So sánh baseline:** chỉ thay một property, dependency hoặc bean mỗi lần. Giữ cùng Boot version, JDK, profile và classpath để kết luận nguyên nhân chính xác.

### Bảng đối chiếu cho ví dụ này

| Quan sát | Property false | Property true | Diễn giải |
| --- | --- | --- | --- |
| `DispatcherServlet` | Có | Có | Servlet infrastructure không đổi |
| `RequestMappingHandlerMapping` | Có | Có | MVC mapping infrastructure không đổi |
| `RequestMappingHandlerAdapter` | Có | Có | MVC adapter không đổi |
| `HttpMessageConverters` | Có | Có | HTTP converter registry không đổi |
| `FormContentFilter` | Có (mặc định) | Có | Filter khác không bị property này chi phối |
| `HiddenHttpMethodFilter` | Không | Có | Bean tùy chọn được bật bằng property |
| Condition source | Negative match | Positive match | `OnPropertyCondition` đổi trạng thái |

Bảng này mô tả kịch bản mẫu với dependencies mặc định. Nếu ứng dụng cung cấp bean `HiddenHttpMethodFilter` riêng, bean custom có thể vẫn tồn tại khi property false, còn auto-configured default vẫn không được tạo.

## 9. Các trường hợp biên cần kiểm tra

### 9.1. Ứng dụng tự cung cấp filter

Nếu ứng dụng có:

```java
@Bean
HiddenHttpMethodFilter customHiddenMethodFilter() {
    return new HiddenHttpMethodFilter();
}
```

thì `@ConditionalOnMissingBean` khiến default của Boot nhường chỗ, kể cả khi property true. Khi đó report có thể cho thấy `OnPropertyCondition` match nhưng `OnBeanCondition` không match. Bean registry sẽ có bean custom với tên `customHiddenMethodFilter`.

Đây là ví dụ quan trọng: **một property condition match không có nghĩa bean default chắc chắn được đăng ký**. Tất cả condition trên method đều phải match.

### 9.2. Người dùng thay thế toàn bộ MVC configuration

`WebMvcAutoConfiguration` có condition kiểm tra thiếu `WebMvcConfigurationSupport`. Khi ứng dụng dùng `@EnableWebMvc` hoặc tự cung cấp cấu hình MVC nền tương đương, auto-configuration mặc định có thể nhường chỗ.

Điều này có phạm vi rộng hơn property filter: nhiều MVC bean mặc định có thể thay đổi. Không nên thêm `@EnableWebMvc` chỉ để sửa một formatter, converter hoặc interceptor nếu muốn giữ toàn bộ MVC auto-configuration của Boot; thông thường hãy triển khai `WebMvcConfigurer` mà không bật `@EnableWebMvc`.

### 9.3. Có class trên classpath nhưng không có Servlet context

`spring-boot-starter-web` có thể hiện diện trong runtime classpath nhưng ứng dụng được khởi động với `spring.main.web-application-type=none`. Khi đó các condition web Servlet không match; các bean MVC đặc thù không được đăng ký chỉ vì class có mặt.

Đây là lý do phải phân biệt `OnClassCondition` và `OnWebApplicationCondition` trong report.

### 9.4. Nhầm bean mapping với endpoint nghiệp vụ

`RequestMappingHandlerMapping` là một infrastructure bean. Nó có thể tồn tại mà không có controller do ứng dụng viết. Ngoài ra, Actuator và error handling có thể đăng ký handler mapping riêng. Vì vậy, đếm một bean mapping không có nghĩa ứng dụng có một API nghiệp vụ tương ứng.

Nếu cần biết endpoint thực tế được đăng ký, hãy kiểm tra `/actuator/mappings` khi endpoint được expose và bảo vệ phù hợp. Không suy ra danh sách URL từ việc có bean `RequestMappingHandlerMapping`.

### 9.5. Nhầm bean type với bean name

Nếu ứng dụng tạo một implementation custom hoặc đổi tên bean, điều kiện theo type và theo name có thể cho kết quả khác nhau. Hãy dùng:

- `getBeanNamesForType(HiddenHttpMethodFilter.class)` để tìm mọi bean theo contract.
- `getBeansOfType(HiddenHttpMethodFilter.class)` để xem các instance tương ứng.
- `/actuator/beans` nếu đã expose và cần xem toàn bộ registry trong môi trường được phép.

Không chỉ tìm chuỗi `hiddenHttpMethodFilter` trong log rồi kết luận không có bean khác cùng type.

## 10. Khi nào dùng --debug, Actuator hay test?

| Công cụ | Dùng khi | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| `--debug` | Local, CI hoặc app không có management HTTP endpoint | In Condition Evaluation Report lúc startup | Log dài; cần lọc source cần xem |
| `/actuator/conditions` | Ứng dụng đang chạy và endpoint được expose an toàn | JSON có cấu trúc, dễ lưu và diff | Phải bật Actuator/exposure và bảo vệ truy cập |
| `ApplicationContext` | Cần biết bean type/name thực tế | Xác nhận kết quả cuối cùng trong registry | Không giải thích trực tiếp condition nào dẫn đến kết quả |
| `@SpringBootTest` | Cần kiểm tra web context gần với ứng dụng thật | Kiểm tra bean infrastructure và startup | Khởi tạo context tốn thời gian hơn |
| `ApplicationContextRunner` / `WebApplicationContextRunner` | Cần cô lập một auto-configuration hoặc condition | Test nhanh từng nhánh input | Phải chọn đúng loại context và nạp đúng auto-configurations |

Với bài toán này, kết hợp **bean inventory trong ApplicationRunner**, **Actuator conditions snapshot** và **SpringBootTest** là đủ để so sánh property mà không phải xây endpoint nghiệp vụ giả.

## 11. Các lỗi thường gặp

1. **Tạo controller chỉ để có URL test.** Không cần thiết khi mục tiêu là quan sát auto-configuration. Bean runner và Actuator endpoint đã đủ.
2. **Chỉ xem positive matches.** Một bean bị loại thường có lý do trong negative matches, bao gồm condition không match và những condition khác vẫn match.
3. **Đọc report mà không kiểm tra bean registry.** Report giải thích quyết định; bean registry xác nhận kết quả thực tế.
4. **Chỉ kiểm tra bean name.** Ứng dụng có thể cung cấp bean cùng type nhưng tên khác. Hãy kiểm tra theo type trước, rồi mới xem tên.
5. **Bật property nhưng quên bean custom.** `@ConditionalOnMissingBean` vẫn có thể khiến default nhường chỗ.
6. **So sánh hai lần chạy khác dependency hoặc profile.** Khi nhiều yếu tố thay đổi, diff không còn chỉ ra nguyên nhân đơn.
7. **Cho rằng mọi bean MVC cần một controller.** DispatcherServlet, mapping, adapter và converter là hạ tầng; chúng có thể tồn tại trước khi ứng dụng đăng ký controller nghiệp vụ.
8. **Dùng `@EnableWebMvc` để sửa một thành phần nhỏ.** Việc này có thể khiến `WebMvcAutoConfiguration` nhường chỗ và thay đổi nhiều bean nền.
9. **Expose Actuator conditions công khai.** Report tiết lộ tên auto-configuration, bean và thông tin môi trường; hãy giới hạn quyền truy cập.
10. **Coi message report là hợp đồng cố định.** Message và danh sách source có thể thay đổi giữa các phiên bản Spring Boot; hãy so sánh theo source/condition và kiểm tra version.

## 12. Checklist thực hành

- [ ] Ứng dụng dùng đúng Servlet web context và Spring Boot version đã chốt.
- [ ] Không có controller/API nghiệp vụ tự tạo trong ví dụ quan sát hạ tầng.
- [ ] Đã xác nhận `DispatcherServlet`, handler mapping, handler adapter và message converters.
- [ ] Đã ghi bean names theo type, không chỉ dựa vào tên đoán trước.
- [ ] Đã lưu Condition Evaluation Report baseline.
- [ ] Chỉ thay một property trong lần chạy thứ hai.
- [ ] Đã đối chiếu source `WebMvcAutoConfiguration#hiddenHttpMethodFilter`.
- [ ] Đã kiểm tra `OnPropertyCondition` và `OnBeanCondition` riêng biệt.
- [ ] Đã xác nhận bean `HiddenHttpMethodFilter` xuất hiện/vắng mặt đúng kỳ vọng.
- [ ] Đã kiểm tra bean MVC nền khác vẫn giữ nguyên.
- [ ] Đã chạy test với web context và xác nhận hai nhánh property.
- [ ] Đã giới hạn quyền truy cập Actuator endpoint.

## Tài liệu chính thức

- [Spring Boot 3.3 — Servlet Web Applications / Spring MVC](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): hạ tầng Spring MVC và cấu hình property.
- [Spring Boot 3.3 — `WebMvcAutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): điều kiện của Web MVC auto-configuration và method `hiddenHttpMethodFilter`.
- [Spring Boot 3.3 — Conditions Evaluation Report API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): cấu trúc `positiveMatches`, `negativeMatches` và message của từng condition.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): bật, expose và kiểm soát endpoint.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test context và auto-configured test.
- [Spring Framework — Special Bean Types in DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html): vai trò của handler mappings, handler adapters và các special beans.
