# Định tuyến theo header với danh sách hàm được phép

## 1. Bài toán thực hành

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đăng ký dưới dạng `Supplier`, `Function` hoặc `Consumer` và được `FunctionCatalog` quản lý. Nhờ các adapter, cùng một hàm có thể được gọi qua HTTP, hệ thống sự kiện hoặc môi trường serverless. Khi ứng dụng có nhiều chức năng nhưng chỉ muốn công bố **một điểm vào**, ta có thể dùng **RoutingFunction** để chọn hàm xử lý dựa trên từng thông điệp.

Giả sử một nền tảng nhận nhiều loại văn bản từ các hệ thống đối tác. Cùng một endpoint/message input phải hỗ trợ ba thao tác:

| Mã tuyến | Hàm đích | Nghiệp vụ |
| --- | --- | --- |
| `normalize` | `normalizeText` | Gộp khoảng trắng, chuyển thành chữ hoa |
| `reverse` | `reverseText` | Đảo ngược chuỗi |
| `mask` | `maskDigits` | Thay chữ số bằng `*` |

Producer gửi payload và một header do ứng dụng quy ước:

~~~text
route-key: normalize
~~~

Payload:

~~~text
  Spring   Cloud Function 101
~~~

Kết quả:

~~~text
SPRING CLOUD FUNCTION 101
~~~

**Yêu cầu bảo mật:** producer chỉ được chọn một trong ba mã tuyến đã công bố. Producer không được gửi tên bean tùy ý, một chuỗi composition tùy ý hoặc biểu thức SpEL để yêu cầu ứng dụng thực thi.

Ta sẽ tạo một **allowlist** ánh xạ mã tuyến sang tên function cố định:

~~~text
route-key từ message
        |
        v
Allowlisted MessageRoutingCallback
        |
        +-- normalize --> normalizeText
        |
        +-- reverse ---> reverseText
        |
        +-- mask ------> maskDigits
        |
        +-- giá trị khác --> từ chối
~~~

Điểm chính của bài:

1. Dùng `functionRouter` có sẵn trong `FunctionCatalog`.
2. Đọc header `route-key` qua `MessageRoutingCallback`.
3. Chỉ trả về function definition nằm trong allowlist được khai báo ở server.
4. Kiểm thử định tuyến đúng, thiếu header, header lạ và nỗ lực ghi đè bằng routing header chuẩn.
5. Hiểu khác biệt giữa routing theo từng message và routing cho toàn bộ reactive stream.
6. Biết giới hạn của allowlist: nó giới hạn **đích có thể chọn qua router**, không thay thế authentication/authorization hoặc cấu hình adapter chỉ công bố router.

## 2. RoutingFunction và các cơ chế định tuyến

Spring Cloud Function đăng ký một router có tên `functionRouter` trong `FunctionCatalog`. Router này có thể được tra cứu như một function và nhận thông điệp để quyết định hàm đích.

~~~java
Function<Object, Object> router =
        functionCatalog.lookup("functionRouter");
~~~

Khi router nhận `Message<?>`, hướng định tuyến có thể được xác định bởi:

- `spring.cloud.function.definition`: tên function hoặc một composition như `foo|bar`.
- `spring.cloud.function.routing-expression`: biểu thức SpEL trả về function definition.
- `MessageRoutingCallback`: một strategy bean tự quyết định function definition.

### 2.1. Độ ưu tiên khi có nhiều cơ chế

Trong trường hợp imperative function, thứ tự ưu tiên theo tài liệu Spring Cloud Function:

| Ưu tiên | Cơ chế | Ý nghĩa |
| ---: | --- | --- |
| 1 | `MessageRoutingCallback` | Strategy callback do ứng dụng đăng ký |
| 2 | Message headers | `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` |
| 3 | Application properties | Cấu hình routing ở cấp ứng dụng |

**Nếu có `MessageRoutingCallback`, callback được ưu tiên trước các routing header và application properties** đối với định tuyến theo từng message. Đây là điểm quan trọng để triển khai allowlist: callback chỉ trả về tên bean đã ánh xạ trong mã nguồn.

### 2.2. Vì sao không dùng trực tiếp tên function từ header?

Một cách ngắn gọn nhưng nguy hiểm là:

~~~java
// Không dùng cách này cho header do producer bên ngoài kiểm soát.
return (String) message.getHeaders()
        .get("function-name");
~~~

Nếu producer gửi `reverseText`, `internalMaintenance` hoặc `normalizeText|someOtherFunction`, router sẽ nhận chuỗi đó như một function definition. Khi catalog có hàm tương ứng, producer có thể gọi hàm mà ứng dụng không định cho phép qua điểm vào này.

Tương tự, `spring.cloud.function.routing-expression` cho phép cung cấp biểu thức SpEL. Spring Cloud Function giới hạn evaluation context cho biểu thức đến từ message header bằng `SimpleEvaluationContext`, nhưng **đó không phải lý do để cho client tự quyết định biểu thức**. Hãy nhận một mã tuyến đơn giản rồi ánh xạ bằng danh sách cố định.

### 2.3. Mã tuyến khác tên bean

Trong lab:

~~~text
Header: route-key = normalize
Server map: normalize -> normalizeText
Router trả: normalizeText
~~~

Producer chỉ biết mã nghiệp vụ `normalize`. Tên bean `normalizeText` là chi tiết triển khai phía server. Ta có thể đổi implementation hoặc tên bean mà không cần yêu cầu producer gửi tên Java mới.

## 3. Phạm vi định tuyến theo từng message

Routing qua header chỉ phù hợp khi đơn vị công việc là **một message**. Với chữ ký imperative như:

~~~java
Function<String, String>
~~~

framework có thể nhận một `Message<?>`, đọc header và chọn hàm cho riêng message đó.

Với reactive function như:

~~~java
Function<Flux<String>, Flux<String>>
~~~

Spring Cloud Function gọi hàm để thiết lập pipeline cho **cả publisher**. Lúc đó không thể dựa vào header của từng phần tử để định tuyến độc lập như imperative function. Với reactive function, routing instruction phải đến từ application properties và áp dụng cho stream như một đơn vị công việc.

**Bài thực hành này dùng imperative functions** `Function<String,String>` để kiểm thử từng message có thể đi tới một đích khác nhau.

## 4. Chuẩn bị dự án Maven

Lab sử dụng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0**. Đây là cặp phiên bản minh họa tương thích; với dự án mới, hãy chọn bản vá được hỗ trợ trong cùng release train và kiểm tra version matrix thay vì ghép các phiên bản độc lập.

Tạo thư mục `header-routing-lab`:

~~~text
header-routing-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingLabApplication.java
    │   │   ├── TextFunctions.java
    │   │   └── AllowlistedRoutingConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/routing/
            ├── TextFunctionsTest.java
            └── FunctionRouterAllowlistTest.java
~~~

Tất cả các lớp dùng package `com.example.routing`. Ta chưa cần Kafka, RabbitMQ, HTTP server hoặc dịch vụ cloud cho các test cốt lõi; chỉ cần Spring context và `FunctionCatalog`.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>header-routing-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>header-routing-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
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
            <artifactId>spring-cloud-function-context</artifactId>
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
~~~

Dependency chính:

| Artifact | Vai trò |
| --- | --- |
| `spring-boot-starter` | Spring application context và auto-configuration |
| `spring-cloud-function-context` | `FunctionCatalog`, `RoutingFunction` và routing callback |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test và assertion |

Không cần thêm `spring-cloud-function-web` hoặc Spring Cloud Stream vào phần test catalog. Ta chỉ bổ sung adapter ở phần mở rộng sau.

## 5. Khai báo ba hàm đích

Tạo `TextFunctions.java`:

~~~java
package com.example.routing;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeText() {
        return input -> input.strip()
                .replaceAll("\\s+", " ")
                .toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> reverseText() {
        return input -> new StringBuilder(input)
                .reverse()
                .toString();
    }

    @Bean
    public Function<String, String> maskDigits() {
        return input -> input.replaceAll("\\d", "*");
    }
}
~~~

Cả ba bean đều có chữ ký `Function<String,String>`. Điều đó giúp routing demo tập trung vào **lựa chọn đích** thay vì phải xử lý nhiều schema đầu vào khác nhau.

| Function bean | Input | Output |
| --- | --- | --- |
| `normalizeText` | `"  Spring   Cloud "` | `"SPRING CLOUD"` |
| `reverseText` | `"abc 123"` | `"321 cba"` |
| `maskDigits` | `"order 123"` | `"order ***"` |

Trong ứng dụng thật, mỗi hàm có thể có kiểu đầu vào/đầu ra khác nhau nếu converter và adapter được cấu hình phù hợp. Nhưng một route phải đảm bảo payload có thể chuyển thành kiểu mà function đích yêu cầu.

## 6. Tạo allowlist từ header route-key

Tạo `AllowlistedRoutingConfiguration.java`:

~~~java
package com.example.routing;

import java.util.Locale;
import java.util.Map;

import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration(proxyBeanMethods = false)
public class AllowlistedRoutingConfiguration {

    private static final String ROUTE_HEADER = "route-key";

    private static final Map<String, String> ALLOWED_ROUTES = Map.of(
            "normalize", "normalizeText",
            "reverse", "reverseText",
            "mask", "maskDigits");

    @Bean
    public MessageRoutingCallback allowlistedMessageRoutingCallback() {
        return new MessageRoutingCallback() {

            @Override
            public String routingResult(Message<?> message) {
                Object rawValue =
                        message.getHeaders().get(ROUTE_HEADER);

                if (!(rawValue instanceof String routeKey)) {
                    throw new IllegalArgumentException(
                            "Missing or invalid route-key header");
                }

                String normalizedKey = routeKey
                        .trim()
                        .toLowerCase(Locale.ROOT);

                String functionDefinition =
                        ALLOWED_ROUTES.get(normalizedKey);

                if (functionDefinition == null) {
                    throw new IllegalArgumentException(
                            "Route is not allowed");
                }

                return functionDefinition;
            }
        };
    }
}
~~~

### 6.1. Phân tích callback

**Bước 1 — đọc header do ứng dụng định nghĩa**

~~~java
Object rawValue = message.getHeaders().get("route-key");
~~~

`route-key` là header riêng của lab, không phải routing header chuẩn của Spring Cloud Function. Nó chỉ chứa mã nghiệp vụ mà producer được phép gửi.

**Bước 2 — kiểm tra kiểu dữ liệu**

~~~java
if (!(rawValue instanceof String routeKey)) {
    throw new IllegalArgumentException(...);
}
~~~

Nếu header thiếu hoặc không phải chuỗi, callback từ chối message. Không tự chuyển một object tùy ý thành tên function.

**Bước 3 — chuẩn hóa alias**

~~~java
String normalizedKey = routeKey.trim().toLowerCase(Locale.ROOT);
~~~

Việc chuẩn hóa cho phép `" NORMALIZE "` được hiểu là `"normalize"`. Nó không thay đổi allowlist và không biến chuỗi tùy ý thành một function hợp lệ.

**Bước 4 — chỉ ánh xạ qua Map cố định**

~~~java
String functionDefinition = ALLOWED_ROUTES.get(normalizedKey);
~~~

Giá trị trả về luôn là một trong ba tên function do server định nghĩa. Header không thể đưa thêm dấu `|` để tạo composition hoặc tự đặt tên bean.

**Bước 5 — từ chối mọi alias ngoài danh sách**

~~~java
if (functionDefinition == null) {
    throw new IllegalArgumentException("Route is not allowed");
}
~~~

Callback không trả `null` để âm thầm chọn một function mặc định. Một route không hợp lệ phải được biểu diễn thành lỗi rõ ràng để adapter/binder xử lý theo chính sách của ứng dụng.

### 6.2. Vì sao dùng MessageRoutingCallback?

Spring Cloud Function tự phát hiện bean `MessageRoutingCallback` và `RoutingFunction` dùng nó để xác định function definition. Callback có **độ ưu tiên cao hơn** routing headers và application properties trong trường hợp imperative routing.

Vì vậy, ngay cả khi message có:

~~~text
spring.cloud.function.definition: reverseText
spring.cloud.function.routing-expression: 'reverseText'
route-key: normalize
~~~

callback vẫn chọn `normalizeText` theo `route-key`. Hai header routing chuẩn không được dùng để ghi đè quyết định allowlist.

### 6.3. Không đưa SpEL vào allowlist

Không viết:

~~~java
// Không dùng biểu thức do producer gửi để chọn function.
return (String) message.getHeaders()
        .get("spring.cloud.function.routing-expression");
~~~

Và cũng không viết:

~~~java
// Không cho phép tên function tùy ý từ header.
return (String) message.getHeaders()
        .get("spring.cloud.function.definition");
~~~

Hai cách này trao quyền chọn function definition trực tiếp cho producer. Nếu ứng dụng cần định tuyến động, hãy parse **một mã tuyến hữu hạn** rồi map sang tên bean cố định như ví dụ.

## 7. Khởi động ứng dụng và cấu hình

Tạo `RoutingLabApplication.java`:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RoutingLabApplication.class, args);
    }
}
~~~

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: header-routing-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Không đặt `spring.cloud.function.definition` thành một hàm đích cố định, vì mục tiêu là route từng message qua `functionRouter`. Cũng không cấu hình `spring.cloud.function.routing-expression` làm biểu thức mặc định; callback sẽ quyết định đích theo allowlist.

`single-function-fallback-enabled: false` tắt fallback tra cứu function theo tên bất kỳ khi catalog chỉ có một function. Trong lab có nhiều bean, cấu hình này vẫn giúp hành vi lookup minh bạch hơn.

### 7.1. functionRouter không phải bean do ta tự viết

Spring Cloud Function đăng ký sẵn `RoutingFunction` trong `FunctionCatalog` dưới tên `functionRouter`. Ta không cần tạo một method `@Bean Function<Object,Object> functionRouter()` mới để thực hiện việc định tuyến.

Các bean do ta viết chỉ gồm:

- `normalizeText`
- `reverseText`
- `maskDigits`
- `allowlistedMessageRoutingCallback`

Khi cần thực thi, tra cứu `functionRouter` từ catalog.

## 8. Kiểm thử logic các function đích

Tạo `TextFunctionsTest.java`:

~~~java
package com.example.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

class TextFunctionsTest {

    private final TextFunctions functions = new TextFunctions();

    @Test
    void normalizesText() {
        Function<String, String> normalize =
                functions.normalizeText();

        assertEquals(
                "SPRING CLOUD FUNCTION",
                normalize.apply("  Spring   Cloud Function  "));
    }

    @Test
    void reversesText() {
        Function<String, String> reverse =
                functions.reverseText();

        assertEquals("321 cba", reverse.apply("abc 123"));
    }

    @Test
    void masksDigits() {
        Function<String, String> mask =
                functions.maskDigits();

        assertEquals("order ***", mask.apply("order 123"));
    }
}
~~~

Unit test này chỉ xác minh từng hàm đích. Nó chưa khởi động Spring, chưa tạo `FunctionCatalog` và chưa chứng minh header routing hoạt động.

## 9. Kiểm thử định tuyến qua FunctionCatalog

Tạo `FunctionRouterAllowlistTest.java`:

~~~java
package com.example.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(
        classes = RoutingLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FunctionRouterAllowlistTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private MessageRoutingCallback routingCallback;

    private Message<String> message(String routeKey, String payload) {
        return MessageBuilder
                .withPayload(payload)
                .setHeader("route-key", routeKey)
                .build();
    }

    private Function<Object, Object> router() {
        Function<Object, Object> router =
                catalog.lookup("functionRouter");
        assertNotNull(router);
        return router;
    }

    @Test
    void routesToNormalizeFunction() {
        Object result = router().apply(
                message("normalize", "  Spring   Cloud Function  "));

        assertEquals("SPRING CLOUD FUNCTION", result);
    }

    @Test
    void routesToReverseFunction() {
        Object result = router().apply(
                message("reverse", "abc 123"));

        assertEquals("321 cba", result);
    }

    @Test
    void routesToMaskFunction() {
        Object result = router().apply(
                message("mask", "order 123"));

        assertEquals("order ***", result);
    }

    @Test
    void normalizesRouteAlias() {
        Object result = router().apply(
                message(" NORMALIZE ", "  spring cloud "));

        assertEquals("SPRING CLOUD", result);
    }

    @Test
    void rejectsUnknownRouteKey() {
        Message<String> input =
                message("deleteAll", "some payload");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsFunctionNameAsRouteKey() {
        Message<String> input =
                message("reverseText", "abc");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsCompositionInRouteKey() {
        Message<String> input =
                message("normalizeText|reverseText", "abc");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsMissingRouteHeader() {
        Message<String> input = MessageBuilder
                .withPayload("Spring Cloud")
                .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsNonStringRouteHeader() {
        Message<Integer> input = MessageBuilder
                .withPayload(42)
                .setHeader("route-key", 123)
                .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void callbackOverridesStandardRoutingHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("  Spring   Cloud ")
                .setHeader("route-key", "normalize")
                .setHeader(
                        "spring.cloud.function.definition",
                        "reverseText")
                .setHeader(
                        "spring.cloud.function.routing-expression",
                        "'reverseText'")
                .build();

        Object result = router().apply(input);

        assertEquals("SPRING CLOUD", result);
    }
}
~~~

### 9.1. Đọc kết quả test

| Test | Điều được chứng minh |
| --- | --- |
| `routesToNormalizeFunction` | Alias `normalize` gọi đúng bean `normalizeText` |
| `routesToReverseFunction` | Alias `reverse` gọi đúng bean `reverseText` |
| `routesToMaskFunction` | Alias `mask` gọi đúng bean `maskDigits` |
| `normalizesRouteAlias` | Alias được trim/lowercase trước khi tra map |
| `rejectsUnknownRouteKey` | Header ngoài allowlist bị từ chối |
| `rejectsFunctionNameAsRouteKey` | Producer không thể gửi thẳng tên bean |
| `rejectsCompositionInRouteKey` | Producer không thể thêm composition tùy ý |
| `rejectsMissingRouteHeader` | Thiếu route key không được chọn một function mặc định |
| `rejectsNonStringRouteHeader` | Kiểu header sai bị từ chối |
| `callbackOverridesStandardRoutingHeaders` | Callback ưu tiên hơn các routing header chuẩn |

Hai tầng test có ý nghĩa khác nhau:

- Gọi `routingCallback.routingResult(message)` xác minh **allowlist policy** độc lập.
- Gọi `router.apply(message)` xác minh **RoutingFunction + FunctionCatalog + callback + function đích** hoạt động cùng nhau.

Nếu chỉ test callback mà không test router, ta chưa chứng minh framework đã tự nhận bean callback và dùng nó để định tuyến.

### 9.2. Vì sao test dùng Message thay vì chỉ truyền String?

Thông tin định tuyến nằm trong **header**. Nếu gọi:

~~~java
router.apply("Spring Cloud");
~~~

router không có `Message<?>` để đọc `route-key`. Với per-message routing, hãy truyền `MessageBuilder.withPayload(...).setHeader(...).build()`.

### 9.3. Vì sao callback trả về tên function đích?

`MessageRoutingCallback.routingResult` trả về **function definition** (tên một `Function`/`Consumer`, có thể là composition nếu ứng dụng chủ động cho phép). Trong bài, callback trả về đúng một trong ba tên:

~~~text
normalizeText
reverseText
maskDigits
~~~

Nó không trả về payload đã xử lý. `RoutingFunction` dùng định nghĩa đó để tra cứu function đích trong catalog rồi gọi function bằng message đầu vào.

## 10. Kiểm thử hành vi từ chối qua router

Trong `FunctionRouterAllowlistTest`, test từ chối trực tiếp callback giúp xác định rõ policy. Có thể bổ sung một test router để kiểm tra lỗi không được biến thành kết quả của function hợp lệ:

~~~java
@Test
void routerDoesNotInvokeAFunctionForUnknownAlias() {
    Message<String> input = message("admin", "payload");

    assertThrows(
            RuntimeException.class,
            () -> router().apply(input));
}
~~~

Exception thực tế có thể được framework/wrapper hoặc adapter bao lại. Vì vậy:

- Unit test callback kiểm tra chính xác `IllegalArgumentException` của policy.
- Test router kiểm tra lời gọi thất bại khi route không hợp lệ.
- Integration test của broker/HTTP kiểm tra exception được ánh xạ thành response, retry hoặc dead-letter theo cấu hình.

Không nên viết test HTTP/broker kỳ vọng một status hoặc cơ chế retry cụ thể trước khi định nghĩa error contract của adapter.

## 11. Hiểu routing header chuẩn và header ứng dụng

Spring Cloud Function có hai routing header thường gặp:

| Header | Ý nghĩa |
| --- | --- |
| `spring.cloud.function.definition` | Tên function hoặc composition definition |
| `spring.cloud.function.routing-expression` | SpEL expression dùng để tạo function definition |
| `route-key` (của lab) | Mã tuyến nghiệp vụ do ứng dụng định nghĩa |

Trong bài, chỉ `route-key` được đọc để quyết định tuyến. Hai header chuẩn bị bỏ qua vì callback đã được đăng ký và có ưu tiên cao hơn.

### 11.1. Nếu không có callback thì sao?

Khi không có `MessageRoutingCallback`, `RoutingFunction` có thể đọc `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` từ message header. Header definition có thể chứa một function name hoặc chuỗi composition. Điều này thuận tiện cho hệ thống nội bộ có producer đáng tin cậy, nhưng không phù hợp nếu client bên ngoài được phép chọn tùy ý function.

### 11.2. SpEL header được giới hạn nhưng vẫn cần kiểm soát

Spring Cloud Function đánh giá SpEL đến từ message header bằng `SimpleEvaluationContext`, có phạm vi hạn chế hơn `StandardEvaluationContext`. Biểu thức từ application properties hoặc system properties có context linh hoạt hơn.

Điều này giúp giảm khả năng thực thi biểu thức nguy hiểm từ header, nhưng **không thay thế allowlist**. Một biểu thức đơn giản như `headers['route-key']` vẫn có thể chọn một function definition không thuộc nghiệp vụ mà ứng dụng mong muốn nếu producer được phép kiểm soát toàn bộ tên đích.

### 11.3. ineligible-definitions không phải allowlist routing

Spring Cloud Function có property:

~~~yaml
spring:
  cloud:
    function:
      ineligible-definitions: internalHelper,debugFunction
~~~

Nó loại các bean được nêu tên khỏi danh sách ứng viên đăng ký trong `FunctionCatalog`. Có thể dùng để loại function helper không được phép xuất hiện trong catalog.

Tuy nhiên, property này khác với allowlist theo từng message:

- `ineligible-definitions` lọc function **toàn cục** khỏi catalog.
- `MessageRoutingCallback` ánh xạ từng `route-key` sang một function được phép.

Nếu một function bị loại khỏi catalog, callback không thể gọi nó. Nếu function vẫn nằm trong catalog nhưng không có alias trong allowlist, router của bài không thể chọn nó.

## 12. Mở rộng sang Spring Cloud Stream event routing

Định tuyến theo header đặc biệt hữu ích khi một input destination nhận nhiều loại event. Spring Cloud Stream có thể bind `RoutingFunction` vào một input binding duy nhất.

Để bật event routing, cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
      bindings:
        functionRouter-in-0:
          destination: text.events.in
          group: text-router
          content-type: text/plain
        functionRouter-out-0:
          destination: text.events.out
          content-type: text/plain
~~~

Tên input binding là `functionRouter-in-0`. Producer gửi message đến destination `text.events.in` với:

~~~text
route-key: normalize
contentType: text/plain
payload: "  Spring   Cloud Function "
~~~

`MessageRoutingCallback` sẽ chọn `normalizeText`, function trả chuỗi chuẩn hóa và output của routing function được chuyển tới output binding khi route đích là `Function`.

**Cấu hình này là phần mở rộng:** dự án Maven hiện tại chưa có Spring Cloud Stream và binder. Để chạy với RabbitMQ, thêm dependency binder phù hợp do BOM quản lý, cấu hình broker và kiểm thử message thực tế.

### 12.1. Binding khi router gọi Function hoặc Consumer

`RoutingFunction` được bind như một function đặc biệt:

- Nếu route tới một `Function` tạo output, framework có thể tạo output binding cho router để gửi kết quả.
- Nếu route tới một `Consumer`, không có payload output nghiệp vụ, nên router hoạt động như consumer và không cần output binding.

Lab hiện có ba đích đều là `Function<String,String>`, vì vậy ví dụ cấu hình input/output đều có ý nghĩa. Nếu thêm route `audit` tới `Consumer<String>`, cần kiểm tra lại output behavior và thiết kế message flow cho consumer đó.

### 12.2. Header phải được giữ qua broker

`route-key` là custom message header. Producer, binder và broker cần bảo toàn header này để callback đọc được. Khi dùng Kafka/RabbitMQ, hãy kiểm tra:

- Header mapping của binder.
- Kiểu dữ liệu header sau khi deserialize.
- Quy tắc tên header và giới hạn header của broker.
- Content type và kiểu payload mà function đích yêu cầu.

Không giả định một header tồn tại trong message ở producer sẽ luôn xuất hiện nguyên dạng trong consumer ở mọi binder hoặc bridge.

### 12.3. Routing và reactive function

Với imperative `Function<String,String>`, một message tương ứng một lần xử lý và có thể route theo `route-key`.

Với reactive `Function<Flux<String>,Flux<String>>`, đơn vị xử lý là publisher/stream. Không thể đọc route key của từng event như cách trong lab để thay function đích riêng cho từng phần tử. Khi cần phân loại event trong một reactive stream, có thể dùng `filter`/`groupBy`/`flatMap` bên trong một pipeline hoặc dùng application property để chọn function cho cả stream.

## 13. Mở rộng sang HTTP adapter

Nếu muốn gửi header từ HTTP, bổ sung dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-web</artifactId>
</dependency>
~~~

Web adapter của Spring Cloud Function có thể chuyển các HTTP headers thành message headers. Khi gọi endpoint của router, client gửi:

~~~bash
curl -i -X POST "http://localhost:8080/functionRouter" \
  -H "Content-Type: text/plain" \
  -H "route-key: normalize" \
  --data-binary "  Spring   Cloud Function "
~~~

Callback nhận `route-key` từ message được adapter tạo và chọn `normalizeText`.

**Lưu ý về bề mặt public:** Allowlist trong callback chỉ giới hạn function mà **functionRouter** được phép gọi. Nếu web adapter đồng thời expose trực tiếp `/normalizeText`, `/reverseText` hoặc `/maskDigits`, client có thể gọi thẳng những URL đó mà không đi qua allowlist. Khi triển khai, phải cấu hình adapter/gateway chỉ công bố router entry point hoặc áp dụng authorization cho từng endpoint, rồi test rằng đường gọi trực tiếp không vượt qua chính sách.

### 13.1. Test HTTP không thay thế test catalog

Catalog test xác nhận router và callback phối hợp đúng trong application context. HTTP integration test cần xác nhận thêm:

- URL router được export.
- Header `route-key` được chuyển thành message header.
- `Content-Type` và payload được chuyển đổi đúng.
- Response status, body và content type đúng hợp đồng.
- Function đích không được gọi trực tiếp nếu không nằm trong bề mặt public.

Không suy luận rằng `FunctionCatalog.lookup("functionRouter")` pass là endpoint HTTP chắc chắn đã được cấu hình an toàn.

## 14. Allowlist không thay thế xác thực và phân quyền

Allowlist giải quyết câu hỏi:

> “Router có thể chọn những function nào?”

Authentication/authorization giải quyết câu hỏi khác:

> “Ai được phép gửi message, và người đó được phép chọn những route nào?”

Trong lab, bất kỳ ai gửi được message có `route-key=normalize` đều có thể yêu cầu router gọi `normalizeText`. Nếu `maskDigits` chỉ dành cho một nhóm client, một allowlist chung chưa đủ. Có thể mở rộng callback để kiểm tra principal/tenant/permission đã được xác thực ở upstream:

~~~text
HTTP / broker authentication
          |
          v
Authorization / tenant context
          |
          v
MessageRoutingCallback
          |
          v
route-key -> function allowlist
~~~

Các quy tắc production:

1. Không dùng header do client tự khai báo như `X-Role: ADMIN` làm bằng chứng quyền.
2. Lấy identity từ security context hoặc thông tin đã được xác minh.
3. Kiểm tra quyền của identity đối với route alias.
4. Chỉ sau khi kiểm tra quyền mới trả function definition.
5. Log mã tuyến, correlation ID và kết quả định tuyến; tránh log payload nhạy cảm.
6. Không đưa function có side effect phá hủy hoặc quyền quản trị vào allowlist công khai.
7. Kiểm tra trực tiếp endpoint và binding khác để tránh bypass router.

## 15. Xử lý route không hợp lệ

Trong lab, callback ném `IllegalArgumentException` nếu header thiếu hoặc không nằm trong allowlist. Đó là lựa chọn **fail closed**: không tự đoán một route mặc định.

Có ba tình huống khác nhau:

| Tình huống | Nơi phát hiện | Chính sách minh họa |
| --- | --- | --- |
| Thiếu `route-key` | Callback | Từ chối |
| `route-key` không có trong map | Callback | Từ chối |
| Callback trả function name nhưng function không có trong catalog | RoutingFunction/catalog | Lỗi không định tuyến được |

Spring Cloud Function có `DefaultMessageRoutingHandler` cho trường hợp message không thể route tới function có trong catalog. Handler mặc định có thể log và cho message flow tiếp tục theo behavior được tài liệu mô tả; có thể cung cấp implementation riêng để xử lý message không định tuyến được.

Tuy nhiên, handler đó **không thay thế kiểm tra allowlist trong callback**. Callback vẫn phải từ chối alias không được phép trước khi trả một function definition.

### 15.1. Không dùng default route tùy tiện

Một số ứng dụng muốn route không rõ ràng vào `defaultHandler`. Điều đó chỉ nên làm khi default handler có hợp đồng an toàn, ví dụ ghi nhận message lỗi vào quarantine. Không tự động route message không hợp lệ sang một function có quyền cao hơn hoặc function thực hiện side effect.

Nếu cần fallback:

- Tạo một route alias riêng do server định nghĩa, ví dụ `unsupported`.
- Chỉ trả alias đó khi chính sách nghiệp vụ cho phép.
- Dùng consumer chỉ ghi nhận metadata cần thiết hoặc một error DTO.
- Kiểm thử rằng fallback không vô tình chạy function nghiệp vụ nhạy cảm.

## 16. Chạy kiểm thử

Trong thư mục `header-routing-lab`, chạy:

~~~bash
java -version
mvn -version
mvn test
~~~

Các test cần pass:

| Nhóm | Kết quả mong đợi |
| --- | --- |
| `TextFunctionsTest` | Ba function đích xử lý đúng chuỗi |
| `FunctionRouterAllowlistTest` | `functionRouter` route đúng alias |
| Negative routing tests | Alias lạ, tên bean, composition, thiếu header và sai kiểu bị từ chối |
| Precedence test | `route-key` được callback ưu tiên hơn routing header chuẩn |

Không cần chạy broker hoặc serverless để chứng minh allowlist hoạt động ở tầng catalog. Nếu thêm adapter, phải bổ sung integration test riêng.

## 17. Bài tập mở rộng

### Bài A — Thêm route cho loại văn bản JSON

Thêm function `summarizeText` nhận `String` và trả về JSON string mô tả độ dài/từ. Thêm alias `summary` vào map.

**Yêu cầu:**

- Chỉ route alias `summary` mới gọi `summarizeText`.
- Header `route-key=summarizeText` phải bị từ chối.
- Viết catalog test xác nhận kết quả.

### Bài B — Route theo loại sự kiện

Tạo ba alias:

~~~text
customer-created
customer-updated
customer-deleted
~~~

Ánh xạ mỗi alias sang function tương ứng. Dùng cùng một `Message<CustomerEvent>` hoặc cùng một schema sự kiện để kiểm tra kiểu payload. Nếu function nhận DTO khác nhau, cấu hình converter và content type phù hợp.

**Yêu cầu:** không dùng trực tiếp giá trị header làm tên bean; luôn ánh xạ qua map cố định.

### Bài C — Phân quyền theo tenant

Mở rộng callback để nhận một identity đã được xác thực (từ security context hoặc một service được inject). Chỉ tenant có quyền `mask` mới được route tới `maskDigits`.

**Yêu cầu:** test:

- Tenant được cấp quyền route `mask`.
- Tenant không có quyền route `mask`.
- Không có authentication context.
- Header giả mạo `tenant-id` không thể ghi đè identity đã xác thực.

### Bài D — Quarantine message không hợp lệ

Thay vì chỉ ném exception, thiết kế một consumer `quarantineMessage` nhận message lỗi có schema an toàn.

**Yêu cầu:** quyết định rõ trường hợp nào đi vào quarantine; không lưu raw payload có thông tin nhạy cảm nếu không có chính sách retention. Viết test chứng minh route hợp lệ không đi vào quarantine.

### Bài E — Thêm composition được phép

Nếu nghiệp vụ thực sự cần pipeline `normalizeText|maskDigits`, hãy thêm một alias duy nhất:

~~~text
normalize-and-mask -> normalizeText|maskDigits
~~~

**Yêu cầu:** map chỉ trả về composition cố định. Header `route-key=normalizeText|maskDigits` phải bị từ chối. Viết test kết quả và test từ chối composition do producer tự gửi.

### Bài F — So sánh routing callback và SpEL

Viết bảng so sánh:

| Tiêu chí | `routing-expression` | `MessageRoutingCallback` |
| --- | --- | --- |
| Khai báo | SpEL | Java strategy bean |
| Độ linh hoạt | Cao với biểu thức | Có thể viết logic tùy chỉnh |
| Allowlist | Phải tự thiết kế biểu thức kiểm soát | Có thể map alias qua danh sách cố định |
| Ưu tiên | Sau callback | Trước message headers và properties |
| Kiểm thử | Test biểu thức + context | Unit test callback + catalog test |

**Yêu cầu:** nêu vì sao biểu thức ngắn không đồng nghĩa với một chính sách phân quyền hoàn chỉnh.

## 18. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `catalog.lookup("functionRouter")` trả null | Context chưa nạp Spring Cloud Function hoặc lookup sai tên | Kiểm tra dependency/context và tên router |
| Callback không chạy | Bean callback chưa được scan/đăng ký | Kiểm tra `@Configuration` và package |
| Header route không được đọc | Đang truyền payload thường thay vì `Message<?>` | Dùng `MessageBuilder` và set header |
| Header bị cast exception | Producer gửi kiểu khác String | Kiểm tra `instanceof String` và từ chối |
| Producer chọn được function ngoài dự kiến | Callback trả raw header hoặc không được đăng ký | Dùng map allowlist và test precedence |
| Routing expression ghi đè callback | Callback chưa thực sự được Spring nhận diện | Test callback bean và route qua functionRouter |
| Alias hợp lệ nhưng function không tồn tại | Map trỏ sai bean name | Kiểm tra tên `@Bean` và catalog |
| Message route đúng nhưng converter lỗi | Target function có input type khác payload | Kiểm tra chữ ký generic, content type và MessageConverter |
| Catalog test pass nhưng Kafka không route | Chưa bật event routing hoặc binder chưa đúng | Bật `spring.cloud.stream.function.routing.enabled`, kiểm tra input binding |
| Custom header mất qua broker | Binder/header mapping không giữ header | Kiểm tra binder-specific header mapping |
| Reactive stream không route theo từng message | Reactive function có unit of work là stream | Dùng application property hoặc thiết kế một pipeline phân loại stream |
| Endpoint direct bypass allowlist | Adapter vẫn export function đích riêng | Chỉ công bố router hoặc bảo vệ từng endpoint |
| Route lạ bị drop mà không có log | Có handler xử lý unroutable message hoặc adapter swallow error | Xác định rõ error policy và kiểm thử adapter |
| Người dùng được route nhưng không có quyền nghiệp vụ | Allowlist bị hiểu nhầm là authorization | Kiểm tra identity/permission trước khi trả function definition |

### 18.1. Trình tự debug

1. Kiểm tra JDK/Maven và chạy `mvn test`.
2. Xác minh các function đích đã là Spring bean.
3. Xác minh `MessageRoutingCallback` có trong application context.
4. Gọi callback trực tiếp với một message hợp lệ và một message sai.
5. Tra cứu `functionRouter` qua `FunctionCatalog`.
6. Gửi `Message<String>` có `route-key` và kiểm tra kết quả.
7. Gửi thêm routing header chuẩn để kiểm tra callback precedence.
8. Chỉ sau đó mới tích hợp HTTP hoặc binder, kiểm tra header propagation.
9. Kiểm tra các endpoint/binding khác để bảo đảm không có đường bypass.

## 19. Tiêu chí hoàn thành

| Tiêu chí | Minh chứng |
| --- | --- |
| Router tồn tại | `FunctionCatalog.lookup("functionRouter")` thành công |
| Có ba function đích | `normalizeText`, `reverseText`, `maskDigits` |
| Có allowlist | Map alias sang tên function cố định |
| Định tuyến theo header | `route-key` chọn đúng function cho từng message |
| Từ chối route lạ | Header không thuộc allowlist gây lỗi |
| Không cho gửi tên bean | `route-key=reverseText` bị từ chối |
| Không cho composition tùy ý | Chuỗi chứa `|` từ producer bị từ chối |
| Callback có ưu tiên | Routing header chuẩn không ghi đè `route-key` |
| Hiểu imperative/reactive | Phân biệt per-message với per-stream routing |
| Hiểu giới hạn bảo mật | Allowlist không thay thế authz và không ngăn direct endpoint nếu adapter vẫn expose |

**Tóm tắt:** `RoutingFunction` cung cấp một điểm vào để chọn function theo message. `MessageRoutingCallback` cho phép ứng dụng kiểm soát quyết định đó bằng mã Java. Khi header chỉ chứa một alias và callback ánh xạ alias qua allowlist, producer không thể tự chọn tên bean hoặc composition tùy ý. Muốn triển khai an toàn, còn phải bảo vệ ingress, kiểm tra quyền của người gửi và bảo đảm adapter chỉ công bố những đường gọi được phép.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Tên mặc định của RoutingFunction trong FunctionCatalog là gì?

**Đáp án:** `functionRouter`.

**Câu 2.** Vì sao không nên trả trực tiếp giá trị header `function-name` từ `MessageRoutingCallback`?

**Đáp án:** Producer có thể gửi tên bean bất kỳ hoặc composition. Callback cần ánh xạ một route alias hữu hạn sang function definition do server kiểm soát.

**Câu 3.** Khi có `MessageRoutingCallback`, header `spring.cloud.function.definition` có thể ghi đè quyết định callback không?

**Đáp án:** Không đối với imperative per-message routing; callback có độ ưu tiên cao nhất trong các cơ chế routing được mô tả.

**Câu 4.** `spring.cloud.function.routing-expression` có vai trò gì?

**Đáp án:** Nó là SpEL expression có thể tạo function definition. Khi nhận từ message header, nó được đánh giá trong context giới hạn hơn; không nên chấp nhận biểu thức tùy ý từ producer.

**Câu 5.** Vì sao bài dùng `Function<String,String>` thay vì `Function<Flux<String>,Flux<String>>`?

**Đáp án:** Bài cần route theo từng message. Với reactive function, đơn vị xử lý là cả stream và routing instruction per-message không được hỗ trợ theo cùng cách.

**Câu 6.** Allowlist có bảo đảm người gửi được phép gọi function theo nghiệp vụ không?

**Đáp án:** Không. Nó chỉ giới hạn đích mà router có thể chọn. Cần authentication/authorization để kiểm tra ai được phép dùng alias nào.

**Câu 7.** Nếu web adapter vẫn expose trực tiếp `/reverseText`, allowlist của `functionRouter` có ngăn client gọi URL đó không?

**Đáp án:** Không. Phải giới hạn adapter/gateway chỉ công bố router hoặc bảo vệ endpoint riêng.

**Câu 8.** Spring Cloud Stream dùng binding input nào cho routing function?

**Đáp án:** `functionRouter-in-0`. Event routing cần bật `spring.cloud.stream.function.routing.enabled=true`.

**Câu 9.** Property `spring.cloud.function.ineligible-definitions` khác allowlist như thế nào?

**Đáp án:** Nó loại bean khỏi catalog một cách toàn cục; callback allowlist chọn function đích cho từng message trong số các function còn đủ điều kiện.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model: RoutingFunction, MessageRoutingCallback, routing precedence](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Event Routing: routing header và MessageRoutingCallback](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Function — FunctionCatalog và Filtering Ineligible Functions](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud — Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Framework — Message và MessageHeaders](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html)
- [Java 17 — Map và Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
