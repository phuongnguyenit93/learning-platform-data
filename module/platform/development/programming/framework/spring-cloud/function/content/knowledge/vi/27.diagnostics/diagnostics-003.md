# Tra cứu tên sai vẫn trả hàm khi bật cơ chế tra cứu dự phòng

## 1. Triệu chứng: gõ sai tên mà FunctionCatalog vẫn trả hàm

Trong một ứng dụng **Spring Cloud Function**, bạn chỉ khai báo một hàm:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Sau đó tra cứu nhầm tên:

~~~java
Function<String, String> function =
    functionCatalog.lookup(Function.class, "upprcase");
// Sai chính tả: "upprcase" thay vì "uppercase".
~~~

Thay vì nhận `null` như kỳ vọng, bạn có thể nhận một function hợp lệ và khi gọi:

~~~java
String result = function.apply("hello");
// Có thể trả "HELLO"!
~~~

Đây không nhất thiết là lỗi của Spring hay bằng chứng đã đăng ký một bean tên `upprcase`. Spring Cloud Function có **single-function fallback**: khi chỉ có **một functional bean phù hợp**, catalog có thể chọn hàm duy nhất nếu caller không cung cấp tên, cung cấp tên rỗng hoặc thậm chí **cung cấp tên không khớp**.

Cơ chế này thuận tiện khi deploy một ứng dụng nhỏ chỉ có một `Supplier`, `Function` hoặc `Consumer`. Nhưng nếu dùng nó mà không biết, ứng dụng có thể:

- Che lỗi chính tả của `spring.cloud.function.definition`.
- Làm test “function có tồn tại” cho kết quả dương tính giả.
- Gọi nhầm business function khi router/adapter truyền sai tên.
- Hỏng sau khi thêm hàm thứ hai hoặc thay đổi danh sách function đủ điều kiện.
- Gây nhầm lẫn giữa tên bean thật và tên mà catalog **chấp nhận để fallback**.

Bài thuộc chương **Chẩn đoán** của module **SPRING_CLOUD_FUNCTION**, trong đó logic được viết bằng `Supplier`, `Function`, `Consumer` và tái sử dụng thông qua `FunctionCatalog`, composition, chuyển đổi message, HTTP, sự kiện hoặc môi trường serverless.

**Câu hỏi chẩn đoán trung tâm:**

> `catalog.lookup("someName") != null` chứng minh đã tìm thấy function có **đúng tên** đó, hay chỉ chứng minh catalog đã tìm được **một function để dùng thay thế**?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích single-function fallback và tại sao tên không tồn tại vẫn có thể resolve thành function duy nhất.
2. Phân biệt **đăng ký tên**, **lookup thành công**, **function được chọn thực tế** và **invocation thành công**.
3. Xác định khi nào fallback được áp dụng, khi nào không nên giả định nó áp dụng.
4. Dùng `getNames(null)`, `lookup(...)` và `ApplicationContext` để phát hiện tên sai.
5. Tắt fallback bằng `spring.cloud.function.single-function-fallback-enabled=false`.
6. Phân biệt fallback của catalog với tự động bind một function duy nhất trong Spring Cloud Stream.
7. Nhận diện hậu quả đối với composition, HTTP adapter, routing, error handlers và serverless.
8. Viết kiểm thử Spring Boot để xác nhận tên đúng, tên sai và hành vi khi số lượng function thay đổi.

## 2. Vì sao Spring Cloud Function có cơ chế fallback?

Spring Cloud Function tách **logic nghiệp vụ** khỏi **giao thức gọi**. Trong ứng dụng nhỏ, bạn có thể chỉ viết:

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(java.util.Locale.ROOT);
}
~~~

Bean này có thể được:

- Caller Java tìm thông qua `FunctionCatalog`.
- Web adapter xuất thành HTTP endpoint.
- Spring Cloud Stream chọn làm message handler.
- Serverless adapter sử dụng như business function.
- Ghép với một function khác khi có composition.

Nếu chỉ có một ứng viên, framework có thể suy luận “hàm duy nhất chính là hàm caller muốn”. Tài liệu chính thức cho ví dụ `uppercase` là hàm duy nhất và các lệnh sau đều có thể tìm nó:

~~~java
catalog.lookup(null);
catalog.lookup("");
catalog.lookup("foo");
~~~

Trong trường hợp này, `foo` **không nhất thiết được đăng ký**. Nó chỉ là tên không khớp được cơ chế fallback chuẩn hóa thành hàm duy nhất.

### 2.1. Tiện lợi và rủi ro

| Tình huống | Lợi ích của fallback | Rủi ro |
| --- | --- | --- |
| Ứng dụng mẫu chỉ có `uppercase` | Không phải cấu hình tên ở mọi caller | Che lỗi gõ sai tên |
| Serverless deploy một business function | Có thể tự chọn function mặc định | Một cấu hình target sai vẫn gọi một function khác |
| Test chỉ kiểm tra kết quả `lookup != null` | Test có vẻ đơn giản | Dương tính giả cho tên chưa đăng ký |
| Spring Cloud Stream có một handler | Thuận tiện khi không đặt definition | Dễ nhầm với cơ chế **auto-binding** riêng của Stream |
| Thêm function thứ hai | Cần lựa chọn tường minh hơn | Tên sai từng được fallback bỗng thất bại |

**Điều quan trọng:** fallback là cơ chế **lựa chọn function**, không phải tự động tạo thêm một Spring bean có tên gõ sai, không phải alias được đăng ký vĩnh viễn và không phải cơ chế sửa lỗi chính tả.

## 3. Cơ chế chọn tên: nhìn từ ApplicationContext đến lookup

Với Spring Cloud Function, các functional beans trong `ApplicationContext` được phát hiện/đăng ký lazy vào `FunctionCatalog`. Catalog hỗ trợ lookup có tên, lookup theo loại, composition và wrapper phục vụ chuyển đổi kiểu.

~~~mermaid
flowchart TD
    CALL["lookup('upprcase')"] --> NAME{"Catalog có tên 'upprcase'?"}
    NAME -->|Có| EXACT["Tra cứu đúng tên"]
    NAME -->|Không| ENABLED{"Single-function fallback bật?"}
    ENABLED -->|Không| NULL["Không tìm được target đó"]
    ENABLED -->|Có| ONE{"Chỉ một function đủ điều kiện?"}
    ONE -->|Có| REWRITE["Chuẩn hóa sang tên function duy nhất"]
    ONE -->|Không| NULL
    REWRITE --> FIND["Tra wrapper/function thật"]
    EXACT --> FIND
    FIND --> END["Caller nhận function"]
~~~

Sơ đồ mô tả **trường hợp lookup tên đơn giản**. Cách xử lý composition, type, router và alias có thêm quy tắc; không coi mọi chuỗi đầu vào đều được đổi sang function duy nhất.

### 3.1. Các tên khác nhau

| Tên/khái niệm | Ví dụ | Có chứng minh là tên bean catalog thực? |
| --- | --- | --- |
| Bean name thật | `uppercase` | Có, sau khi xác minh qua catalog/context |
| Tên lookup sai | `upprcase` | **Không**, dù lookup có thể trả function |
| Function definition | `uppercase` hoặc `uppercase|reverse` | Chỉ rõ function/composition được chọn |
| HTTP path | `/uppercase` hoặc `/` | Là mapping của web adapter, không phải bean name |
| Stream binding | `uppercase-in-0`, `uppercase-out-0` | Tên binding, không phải tên function |
| Broker destination | `orders-in` | Tên topic/queue, không phải tên catalog |
| Router target | `headers.targetFunction` quyết định tên | Phải xác minh target cuối có hợp lệ |

Để biết tên thực, dùng `catalog.getNames(null)` hoặc thông tin registration, **không suy ra từ tham số đã truyền vào `lookup`**.

### 3.2. Lookup trả wrapper, không đơn giản là bean gốc

~~~java
Function<String, String> fromCatalog =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> fromContext =
    context.getBean("uppercase", Function.class);
~~~

`fromCatalog` có thể là wrapper được instrument bởi Spring Cloud Function để hỗ trợ conversion và composition. Vì vậy:

- Không nên dựa vào `==` hoặc `assertSame(...)` để kiểm tra catalog lookup.
- Nên kiểm tra tên thực, kiểu và hành vi đầu vào/đầu ra.
- Lookup thành công không đồng nghĩa function đã được **invoke**.
- Với reactive function trả `Mono`/`Flux`, `apply` có thể mới tạo pipeline; việc xử lý thật diễn ra khi subscribe.

## 4. Ví dụ tối thiểu có đúng một functional bean

Tạo ứng dụng Java 17+ dùng Spring Boot và Spring Cloud Function:

~~~java
package demo.fallback;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OneFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OneFunctionApplication.class, args);
    }

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Ví dụ giả định project có bộ dependency Spring Boot/Spring Cloud Function tương thích, không có bean chức năng ứng dụng nào khác. Khi fallback bật, bạn có thể quan sát:

~~~java
Function<String, String> exact =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");

Function<String, String> randomName =
    catalog.lookup(Function.class, "somethingElse");
~~~

Với tình huống chỉ một ứng viên hợp lệ, `exact`, `typo` và `randomName` **có thể hoạt động giống nhau**: tất cả đều đưa tới logic uppercase.

### 4.1. Bảng đối chiếu kết quả mong đợi

| Lookup | Fallback bật; một function phù hợp | Fallback tắt; không có definition mặc định khác |
| --- | --- | --- |
| `lookup("uppercase")` | Function uppercase | Function uppercase |
| `lookup("upprcase")` | Có thể trả uppercase | Không tìm thấy tên này |
| `lookup("somethingElse")` | Có thể trả uppercase | Không tìm thấy tên này |
| `lookup("")` | Có thể trả uppercase | Không tự thay thành uppercase |
| `lookup(null)` | Có thể trả uppercase | Không tự thay thành uppercase |

**Giới hạn của bảng:** giá trị `spring.cloud.function.definition` ở runtime có thể cung cấp một definition mặc định khi caller để tên rỗng hoặc `null`. Bảng giả định **không có definition mặc định bổ sung**, để cô lập hiệu ứng fallback.

### 4.2. Vì sao mã sau tạo test sai?

~~~java
boolean exists = catalog.lookup("upprcase") != null;
~~~

Nếu `exists` là `true` do fallback, test chỉ chứng minh **có một function được trả về**, chứ không chứng minh có tên `upprcase`.

Nếu cần xác minh tên:

~~~java
boolean nameIsRegistered =
    catalog.getNames(null).contains("upprcase");
~~~

Trong ứng dụng mẫu, `nameIsRegistered` phải là `false`, dù lookup typo có thể vẫn trả uppercase.

## 5. Nhận diện điều kiện áp dụng thay vì dựa vào phép đếm thô

Tài liệu Spring Cloud Function diễn giải điều kiện phổ biến là **chỉ có một functional bean**. Tuy nhiên, trong ứng dụng thực, danh sách catalog có thể chứa function hỗ trợ của framework, router hoặc các registration đặc biệt.

Vì vậy đừng dùng phép kiểm tra cứng:

~~~java
if (catalog.getNames(null).size() == 1) {
    // Sai khi coi đây là điều kiện duy nhất quyết định mọi fallback.
}
~~~

Các điểm cần xem xét:

1. Có **bao nhiêu functional candidates hợp lệ** sau khi registration/filter?
2. Có function đặc biệt do framework cung cấp (ví dụ router) không?
3. Tên đang lookup có phải **một tên đơn giản** hay là expression composition?
4. Có cấu hình `single-function-fallback-enabled` hay không?
5. Có `spring.cloud.function.definition` mặc định ở runtime không?
6. Lookup có yêu cầu đúng kiểu `Function`, `Supplier` hoặc `Consumer` không?
7. Framework đang dùng phiên bản nào và có các extension nào?

### 5.1. Không phải mọi lookup đều fallback

Trong implementation của các phiên bản hiện đại, thao tác chuẩn hóa tên có một số điều kiện bảo vệ, chẳng hạn không tự thay một **definition có dấu composition `|`** bằng tên của một function duy nhất. Các tên framework hỗ trợ như router cũng được xem xét đặc biệt.

Vì vậy:

~~~java
catalog.lookup("upprcase");        // Có thể fallback.
catalog.lookup("uppercase|missing"); // Composition thiếu bước;
                                    // không mặc nhiên thành uppercase.
~~~

Nếu composition không tìm được một mắt xích, cần xử lý **composition error** thay vì giả định fallback sẽ chữa mọi lỗi tên.

### 5.2. Loại function cũng quan trọng

~~~java
@Bean
Supplier<String> greeting() {
    return () -> "hello";
}
~~~

Nếu chỉ có `greeting`, việc lookup không tên có thể chọn supplier mặc định theo cơ chế adapter/caller. Nhưng không được suy ra rằng:

~~~java
Function<String, String> function =
    catalog.lookup(Function.class, "greeting");
~~~

sẽ là một function hợp lệ nhận input. `Supplier<T>`, `Function<T,R>` và `Consumer<T>` có hợp đồng khác nhau. **Fallback tên không tự chuyển Supplier thành Function hoặc Consumer thành Supplier**.

Khi kiểm tra, hãy kết hợp inventory, loại function và hành vi gọi thật; đừng coi một giá trị khác null ở wrapper là đủ để đảm bảo hợp đồng kiểu của caller.

## 6. Cách kiểm tra tên thật bằng FunctionCatalog

Khi gặp tình huống tên sai vẫn trả hàm, hãy bắt đầu từ API công khai:

~~~java
import java.util.Set;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;

FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

Set<String> names = catalog.getNames(null);
int size = catalog.size();

System.out.println("Catalog names = " + names);
System.out.println("Catalog size = " + size);

System.out.println("exact name registered = " +
    names.contains("uppercase"));

System.out.println("typo registered = " +
    names.contains("upprcase"));

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");

System.out.println("typo lookup returned function = " +
    (typo != null));
~~~

Một bộ kết quả đáng chú ý là:

~~~text
exact name registered = true
typo registered = false
typo lookup returned function = true
~~~

Đây chính là bằng chứng phù hợp với cơ chế fallback: **tên gõ sai không nằm trong inventory nhưng lookup vẫn tìm được một function**.

### 6.1. Đối chiếu Spring ApplicationContext

~~~java
boolean realBeanExists =
    applicationContext.containsBean("uppercase");

boolean typoBeanExists =
    applicationContext.containsBean("upprcase");

System.out.println(realBeanExists);
System.out.println(typoBeanExists);
~~~

Trong ứng dụng mẫu, bean thật là `uppercase`. Fallback không làm xuất hiện một bean tên `upprcase` trong `ApplicationContext`.

Cũng có thể liệt kê các bean ứng viên:

~~~java
String[] functions =
    applicationContext.getBeanNamesForType(
        java.util.function.Function.class
    );
~~~

**Phân biệt:** Spring context là nơi đăng ký bean; FunctionCatalog là lớp tra cứu/wrapper; adapter là lớp cung cấp điểm gọi. Chúng có thể hiển thị danh sách tên khác nhau.

### 6.2. Nếu getNames có những tên lạ?

Kiểm tra những nguồn tạo registration:

- `@Bean` hoặc class `@Component` implement `Function`/`Supplier`/`Consumer`.
- Component scanning quá rộng hoặc cấu hình `@Import`.
- Function-specific component scanning của Spring Cloud Function.
- `FunctionalSpringApplication` và `FunctionRegistration`.
- Autoconfiguration từ dependency.
- `spring.cloud.function.ineligible-definitions` đang lọc những tên nào.

Không tự sửa fallback khi nguyên nhân thực là **catalog có nhiều function không mong đợi**. Phân loại chính xác danh sách trước.

## 7. Tắt cơ chế tra cứu dự phòng để yêu cầu tên chính xác

Property được tài liệu Spring Cloud Function hướng dẫn là:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Sau khi áp dụng và khởi động lại context thích hợp, lookup một tên sai **không còn được tự động chuẩn hóa thành hàm duy nhất chỉ nhờ fallback này**.

~~~java
// Khi đã tắt fallback và không có registration/alias tên đó:
Function<String, String> exact =
    catalog.lookup(Function.class, "uppercase");  // Có function.

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");    // Không tìm thấy.
~~~

### 7.1. Biểu diễn trong YAML

~~~yaml
spring:
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Hoặc environment variable theo quy tắc relaxed binding của Spring Boot:

~~~text
SPRING_CLOUD_FUNCTION_SINGLE_FUNCTION_FALLBACK_ENABLED=false
~~~

Sau khi deploy, phải xác minh **giá trị có hiệu lực tại runtime**. Một property trong source có thể bị profile, environment hoặc tham số khởi động ghi đè.

### 7.2. Property này không làm gì?

| Mong muốn | `single-function-fallback-enabled=false` có làm không? |
| --- | --- |
| Bắt tên gõ sai không được tự đổi thành một function duy nhất | **Có**, đúng mục đích |
| Xóa bean `uppercase` khỏi Spring context | **Không** |
| Xóa `uppercase` khỏi FunctionCatalog | **Không** |
| Tắt HTTP endpoints | **Không** |
| Ngăn Spring Cloud Stream tự bind một functional bean duy nhất | **Không**, đó là cơ chế riêng |
| Bật authorization cho function | **Không** |
| Tắt routing expression do ứng dụng chủ động cung cấp | **Không** |
| Sửa tên function không tồn tại trong definition | **Không**, lỗi cấu hình phải được sửa |
| Tự làm component scan chính xác | **Không** |

**Khuyến nghị:** với hệ thống phụ thuộc tên chính xác — multi-function, routing phức tạp, handler lỗi, production cần fail-fast — nên cân nhắc tắt fallback và có regression test tên function.

### 7.3. Tên rỗng/null vẫn có ngoại lệ do definition

Nếu caller gọi `lookup(null)` hoặc `lookup("")`, Spring Cloud Function còn có cơ chế lấy **default function definition** từ environment. Vì vậy khi đã đặt:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.function.single-function-fallback-enabled=false
~~~

thì lookup không tên **vẫn có thể chọn uppercase** do definition đã cấu hình — đây **không phải** single-function fallback theo tên sai.

Để test việc tắt fallback một cách chính xác, dùng **một tên sai không rỗng** và đảm bảo không có alias/function registration mang tên đó, thay vì chỉ dùng `lookup(null)`.

## 8. Test chuẩn: cùng một ứng dụng, hai chế độ fallback

Unit test chỉ có một function cần kiểm tra cả **trạng thái bật** và **tắt**. Mẫu sau có hai Spring test contexts độc lập, sử dụng Java 17+, JUnit 5, AssertJ và Spring Boot Test.

### 8.1. Application configuration tối thiểu cho test

Dùng `@SpringBootConfiguration` và `@EnableAutoConfiguration` để tạo context có một function ứng dụng, tránh component scan mở rộng vô tình đưa function khác vào test.

~~~java
package demo.fallback;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
class OneFunctionTestConfiguration {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Project test phải có dependency của Spring Cloud Function để `FunctionCatalog` được auto-configure. Không dựa vào Spring Boot Test thuần mà thiếu Spring Cloud Function context.

### 8.2. Bật fallback: tìm tên sai vẫn trả uppercase

~~~java
package demo.fallback;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
    classes = OneFunctionTestConfiguration.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=true",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class FallbackEnabledTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typoIsNotRegisteredButFallsBackToOnlyFunction() {
        assertThat(catalog.getNames(null))
            .contains("uppercase")
            .doesNotContain("upprcase");

        Function<String, String> byTypo =
            catalog.lookup(Function.class, "upprcase");

        assertThat(byTypo).isNotNull();
        assertThat(byTypo.apply("hello")).isEqualTo("HELLO");
    }

    @Test
    void explicitNameStillWorks() {
        Function<String, String> byExactName =
            catalog.lookup(Function.class, "uppercase");

        assertThat(byExactName).isNotNull();
        assertThat(byExactName.apply("spring"))
            .isEqualTo("SPRING");
    }
}
~~~

Đây là test **minh họa behavior khi fallback bật**, không phải test khuyến khích dựa vào tên sai trong production.

### 8.3. Tắt fallback: cùng tên sai phải bị từ chối

~~~java
package demo.fallback;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
    classes = OneFunctionTestConfiguration.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=false",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class FallbackDisabledTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typoMustNotResolve() {
        assertThat(catalog.getNames(null))
            .contains("uppercase")
            .doesNotContain("upprcase");

        assertThat(catalog.lookup("upprcase")).isNull();
    }

    @Test
    void exactNameStillResolves() {
        Function<String, String> exact =
            catalog.lookup(Function.class, "uppercase");

        assertThat(exact).isNotNull();
        assertThat(exact.apply("hello")).isEqualTo("HELLO");
    }
}
~~~

Hai test contexts dùng property khác nhau để tránh một test phụ thuộc trạng thái của test trước. `spring.cloud.stream.function.autodetect=false` ở đây chỉ giúp cách ly Stream nếu dependency Stream có trong test; nó **không thay** property fallback của SCF.

### 8.4. Điều kiện kiểm thử cần giữ ổn định

- Chạy đúng test application, không vô tình scan nhiều functional beans.
- Đảm bảo không cấu hình `spring.cloud.function.definition` mặc định ngoài chủ đích.
- Đảm bảo không có alias `upprcase` hoặc registration thật với tên đó.
- Không dùng `assertSame(bean, catalogResult)` vì wrapper có thể khác bean.
- Nếu nâng cấp Spring Cloud Function, xác minh behavior theo phiên bản thực tế.
- Nếu có function framework/router, đừng chỉ nhìn số tên tuyệt đối; xem **các ứng viên đủ điều kiện của ứng dụng**.

## 9. Tình huống hồi quy: thêm hàm thứ hai làm lộ lỗi bị che

Ban đầu ứng dụng chỉ có:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Caller ghi sai:

~~~java
catalog.lookup("upprcase");
~~~

Khi fallback bật và catalog có một ứng viên, hệ thống có thể hoạt động như thể tên đúng. Sau khi thêm:

~~~java
@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

catalog giờ có nhiều ứng viên chức năng. Một tên sai `upprcase` không còn được suy thành function duy nhất theo single-function fallback; lookup có thể không tìm được target.

### 9.1. Hai cách hiểu sai

**Sai:** “Hàm reverse làm hỏng uppercase.”

**Đúng hơn:** “Một cấu hình lookup sai tên đã tồn tại trước đó; fallback che lỗi khi ứng dụng chỉ có một function. Hàm thứ hai làm lỗi trở nên nhìn thấy.”

Không xóa `reverse` chỉ để khôi phục fallback. Cần sửa target thành `uppercase` và thêm test bắt tên sai.

### 9.2. Có thể xảy ra chiều ngược lại

Nếu một ứng dụng có nhiều function, lookup tên sai thất bại rõ ràng. Sau refactor, một function bị loại khỏi catalog bởi profile hoặc `ineligible-definitions`. Khi chỉ còn một ứng viên, tên sai có thể **bắt đầu resolve thành ứng viên còn lại** nếu fallback được bật.

Vì vậy behavior có thể thay đổi khi **số ứng viên đủ điều kiện thay đổi**, không chỉ khi người dùng sửa chuỗi tên.

### 9.3. Test sau mỗi thay đổi cấu hình

Thêm regression test:

~~~java
assertThat(catalog.getNames(null))
    .contains("uppercase", "reverse")
    .doesNotContain("upprcase");

// Với strict fallback disabled:
assertThat(catalog.lookup("upprcase")).isNull();
~~~

Nếu muốn bảo vệ contract rõ ràng hơn, test `spring.cloud.function.definition` thực tế và output của function được chọn.

## 10. Phân biệt fallback với tên bean hoặc alias thật

Một bean có thể được đăng ký với tên khác tên method:

~~~java
@Bean("formatOrder")
Function<String, String> uppercase() {
    return String::trim;
}
~~~

Tên dự kiến ở Spring context là `formatOrder`. Nếu caller gọi `uppercase` và nhận kết quả khi chỉ có một functional bean, rất có thể **fallback** đang che việc sử dụng tên method thay cho bean name.

### 10.1. Cách xác minh

~~~java
System.out.println(
    applicationContext.containsBean("formatOrder")
);

System.out.println(
    applicationContext.containsBean("uppercase")
);

System.out.println(catalog.getNames(null));
~~~

Nếu Spring bean được đăng ký với nhiều tên/alias thực, chúng có thể có những quy tắc lookup riêng. Đừng suy alias từ việc lookup thành công. Dùng API Spring bean aliases/bean definition và catalog inventory để chứng minh tên nào được đăng ký thật.

### 10.2. Một tên được chấp nhận không có nghĩa đã tạo alias

So sánh:

| Dấu hiệu | Alias thật | Fallback |
| --- | --- | --- |
| Được cấu hình/đăng ký có chủ đích | Có | Không cần |
| Có thể được Spring nhận diện như bean name/alias | Có | Không do fallback tạo ra |
| Có thể thay đổi khi số functional candidates thay đổi | Không do cơ chế fallback | **Có thể** |
| Có thể tắt bằng `single-function-fallback-enabled=false` | Không phải cơ chế này | Có |
| Chứng minh bằng `lookup("alias") != null` | Không đủ | Không đủ |

Sử dụng contract **tên chính xác** trong application configuration, adapter và test.

## 11. Phân biệt với spring.cloud.function.definition

Trong Spring Cloud Function, có hai thao tác khác nhau:

1. `FunctionCatalog.lookup(name)` do code/caller thực hiện.
2. `spring.cloud.function.definition` để cấu hình function hoặc composition được adapter sử dụng.

Ví dụ:

~~~properties
spring.cloud.function.definition=uppercase
~~~

Đây là một lựa chọn tường minh và đúng.

Nhưng:

~~~properties
spring.cloud.function.definition=upprcase
~~~

là một **lỗi cấu hình tên**. Nếu catalog chỉ còn một ứng viên và fallback bật, tùy luồng lựa chọn function của adapter, sai tên đó có thể không làm startup thất bại ngay mà bị chuẩn hóa thành function duy nhất.

### 11.1. Explicit definition không tự chống typo

Một số người nghĩ “đã đặt `spring.cloud.function.definition` thì framework phải reject tên sai”. Không thể suy điều đó khi fallback còn bật và chỉ có một ứng viên.

Để có chính sách fail-fast:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.function.single-function-fallback-enabled=false
~~~

Sau đó integration test function definition thực tế. **Tắt fallback không sửa value `upprcase` thành `uppercase`**; bạn vẫn phải sửa config lỗi.

### 11.2. Composition dùng dấu |

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

Đây là **composition** gồm hai bước. Nếu một bước không tồn tại, cần kiểm tra từng mắt xích:

~~~java
catalog.lookup("uppercase");
catalog.lookup("reverse");
catalog.lookup("uppercase|reverse");
~~~

Không xem `uppercase|missing` như một lookup tên đơn giản cần được fallback. Các implementation hiện đại có quy tắc bảo vệ đối với composition strings.

### 11.3. Dấu ; khác dấu |

Trong Spring Cloud Stream, dấu `;` trong `spring.cloud.function.definition` thường chọn **nhiều function độc lập**:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Còn `|` ghép thành **một pipeline**. Nếu khai báo sai dấu, có thể tạo bindings khác kỳ vọng, không liên quan trực tiếp đến single-function fallback.

## 12. Phân biệt với Spring Cloud Stream single-function autodetection

**Rất dễ nhầm hai cơ chế có tên gần giống nhau.**

Spring Cloud Function có:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Mục tiêu: không tự chọn function duy nhất khi **lookup tên sai hoặc không tên**.

Spring Cloud Stream có:

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

Mục tiêu: tắt cơ chế **tự phát hiện và auto-bind functional bean duy nhất** để xử lý message khi không có function definition rõ ràng.

| Tiêu chí | SCF single-function fallback | Stream function autodetect |
| --- | --- | --- |
| Hoạt động ở đâu? | `FunctionCatalog.lookup` | Spring Cloud Stream functional binding |
| Khi nào đáng chú ý? | Caller đưa tên sai/null/rỗng | App có một functional bean và không khai báo definition |
| Mục tiêu | Chọn function để trả từ catalog | Chọn function để nối với broker |
| Property | `spring.cloud.function.single-function-fallback-enabled` | `spring.cloud.stream.function.autodetect` |
| Tắt một cơ chế có tắt cơ chế kia? | **Không** | **Không** |
| Có trực tiếp bật/tắt HTTP? | Không | Không |
| Có làm mất Spring bean? | Không | Không |

### 12.1. Ví dụ một Supplier tự được bind vào broker

~~~java
@Bean
Supplier<String> heartbeat() {
    return () -> "alive";
}
~~~

Nếu ứng dụng có Spring Cloud Stream binder và chỉ có một functional bean, framework có thể auto-bind supplier này theo cấu hình. Việc nó được poll và phát message **không phải** kết quả của `catalog.lookup("upprcase")`.

Để tránh auto-binding ngoài ý muốn, lựa chọn tường minh function nào cần bind hoặc tắt Stream autodetection khi phù hợp:

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

Để tránh lookup sai tên, cấu hình **riêng**:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Tùy ứng dụng, có thể cần cả hai, nhưng không sao chép tất cả property một cách máy móc nếu chưa biết yêu cầu vận hành.

## 13. HTTP web adapter: tên route không giống kết luận lookup

Khi dùng module web của Spring Cloud Function, function có thể được xuất thành endpoint. Tài liệu web adapter mô tả rằng nếu catalog chỉ có một function, URL có thể gọi qua:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "hello" \
  http://localhost:8080/uppercase
~~~

và root path:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "hello" \
  http://localhost:8080/
~~~

đều có thể gọi cùng function, nếu web adapter đúng version/configuration.

### 13.1. Đừng suy URL lạ luôn chạy được

Một HTTP request tới `/upprcase` có thể được xử lý theo mapping của web adapter, definition fallback và các quy tắc path riêng. **Không thể lấy việc `catalog.lookup("upprcase")` fallback làm bằng chứng mọi URL bất kỳ sẽ tự route thành uppercase**.

Tài liệu web adapter còn mô tả trường hợp `spring.cloud.function.definition` ánh xạ một function/composition vào root path hoặc một URL không resolve trực tiếp. Vì vậy cần test **chính HTTP adapter**, không chỉ gọi catalog trong unit test.

### 13.2. Security implication

Nếu chỉ có một function nhạy cảm và route/adapter cho phép chọn nó khi tên không rõ, có thể tăng rủi ro một caller truy cập không đúng dự kiến. Nhưng:

- Fallback không tự bỏ qua Spring Security, IAM hoặc proxy authentication.
- Fallback không biến function thành public endpoint nếu không có adapter.
- Một route có thể đã được export theo quy tắc web ngay cả khi bạn tắt fallback.
- Bảo vệ phải dựa trên **authorization theo target/capability thực tế**, không chỉ tên URL.

Đối với function quản trị, tránh export trong cùng context web không kiểm soát; dùng security allowlist/deny-by-default và negative tests.

### 13.3. Cần test hai lớp

| Lớp | Điều cần test |
| --- | --- |
| Catalog | Lookup tên sai bị từ chối khi strict fallback |
| HTTP | URL lạ/root/composition không vô tình gọi target nhạy cảm |
| Security | Caller không quyền không kích hoạt side effect |
| Operations | Log/audit biết function thật sự được gọi |

Chỉ assert HTTP 404 chưa đủ nếu mục tiêu là không có side effect: hãy kiểm tra bằng fake/spy service rằng operation nhạy cảm **không được thực thi**.

## 14. Serverless và FunctionInvoker: cấu hình tên sai có thể khó phát hiện

Một serverless adapter có thể dùng business function từ `FunctionCatalog` và một handler do nền tảng gọi. Với AWS Lambda adapter, handler/entry point là thành phần khác với tên functional bean.

Ví dụ:

~~~text
Lambda handler: FunctionInvoker
Business function: uppercase
Configured definition: upprcase  (typo)
~~~

Nếu catalog chỉ có một ứng viên, fallback có thể làm typo bị che trong một số đường chọn function. Khi bổ sung function thứ hai hoặc thay đổi artifact, invocation có thể thất bại vì không còn ứng viên duy nhất.

### 14.1. Hướng khắc phục

1. Xác định **handler** và **business function** là hai tên riêng.
2. Kiểm tra catalog ở artifact serverless thật.
3. Đọc giá trị `spring.cloud.function.definition` hiệu lực trong runtime.
4. Cân nhắc tắt fallback để yêu cầu tên chính xác.
5. Test invocation với payload đại diện, bao gồm trường hợp target sai.
6. Không để routing instructions do caller không tin cậy điều khiển target nhạy cảm.
7. Khi function có side effect, phải kiểm tra idempotency vì invocation có thể bị retry.

**Không suy ra mọi serverless adapter xử lý lỗi giống nhau.** Handler, startup, serializer và error response phụ thuộc nền tảng/phiên bản; fallback chỉ là một yếu tố trong lựa chọn target.

## 15. FunctionRouter: không dùng fallback thay cho quy tắc routing

Spring Cloud Function có `functionRouter` để định tuyến tới một function khác dựa trên cấu hình hoặc, với imperative message routing, header/callback phù hợp.

Giả sử:

~~~text
Client/Message → functionRouter → targetName → FunctionCatalog
~~~

Nếu `targetName` bị gõ sai và chỉ có một function ứng viên, fallback có thể khiến router hoặc một bước lookup liên quan chọn một function không như ý định. Không nên xây logic dựa trên sự tình cờ này.

### 15.1. Đường dẫn cần xác minh

~~~mermaid
flowchart LR
    INPUT["Message/Invocation"] --> ROUTER["RoutingFunction"]
    ROUTER --> NAME["Target name từ config/header"]
    NAME --> LOOKUP["FunctionCatalog.lookup"]
    LOOKUP --> TARGET["Function được chọn thực tế"]
~~~

Với vấn đề route sai:

- Log tên target **được tính ra** thay vì chỉ in “router invoked”.
- So target với `catalog.getNames(null)`.
- Tắt single-function fallback khi cần strict routing.
- Có danh sách target được phép cho từng caller/capability.
- Đảm bảo input không tin cậy không thể tự chọn bất kỳ internal function nào.
- Kiểm thử target sai bị từ chối, không rơi vào function duy nhất.

### 15.2. Reactive routing không phải per-message routing tùy ý

Với `Function<Flux<T>, Flux<R>>`, đơn vị lời gọi có thể là toàn publisher, không phải từng phần tử. Tài liệu Spring Cloud Function phân biệt routing instructions của reactive stream với imperative message routing. Không suy rằng một header trong mỗi event có thể chọn lại function cho từng item chỉ vì router được bật.

## 16. Trường hợp thực tế: handler lỗi không tồn tại nhưng lookup vẫn “thành công”

Một hệ thống có thể tra cứu một function đặc biệt để xử lý lỗi:

~~~java
Function<?, ?> errorHandler =
    catalog.lookup("handleProcessingError");
~~~

Developer quên đăng ký bean `handleProcessingError`. Nếu catalog thực tế chỉ có một function khác, ví dụ `processOrders`, fallback có thể trả **processOrders** thay vì `null`.

### 16.1. Vì sao nguy hiểm hơn typo thông thường?

- Code cho rằng đã chọn error handler.
- Khi có lỗi, framework/caller có thể **gọi lại business function chính**.
- Side effects có thể được thực hiện ngoài ý định.
- Test chỉ kiểm tra handler khác null vẫn vượt qua.
- Việc thiếu handler không bị phát hiện ở startup.

Đây là **một kịch bản rủi ro**, không phải khẳng định mọi API error-handler của mọi framework đều gọi `FunctionCatalog.lookup` theo cách này. Phải kiểm tra tích hợp cụ thể.

### 16.2. Thiết kế fail-fast

Nếu callback bắt buộc phải có function name đã khai báo:

~~~java
String expectedName = "handleProcessingError";

if (!catalog.getNames(null).contains(expectedName)) {
    throw new IllegalStateException(
        "Required error handler is not registered: " +
        expectedName
    );
}

Function<?, ?> handler =
    catalog.lookup(Function.class, expectedName);

if (handler == null) {
    throw new IllegalStateException(
        "Required error handler cannot be resolved: " +
        expectedName
    );
}
~~~

Ở đây, kiểm tra inventory trước lookup giúp **xác minh tên**, thay vì chỉ kiểm tra catalog trả bất cứ function nào.

Nếu handler bắt buộc phải là `Consumer<ErrorEvent>`, kiểm tra type đó chứ không dùng `Function.class` theo thói quen. Thêm test gửi một lỗi giả định và xác minh đúng handler được gọi; tránh test với side effect thật.

## 17. FunctionCatalog không đồng nghĩa ApplicationContext có alias đó

Đôi khi lỗi bị truy ngược sai thành “Spring tự tạo alias theo tên lookup”.

Phân biệt:

~~~java
boolean existsAsBean =
    context.containsBean("upprcase");

boolean appearsInCatalog =
    catalog.getNames(null).contains("upprcase");

boolean resolvesByFallback =
    catalog.lookup("upprcase") != null;
~~~

Có thể quan sát:

~~~text
existsAsBean        = false
appearsInCatalog    = false
resolvesByFallback  = true
~~~

Đó là minh chứng fallback. Nếu `containsBean` là true, có thể thực sự đã khai báo alias/bean khác; cần điều tra registration chứ không chỉ tắt fallback.

### 17.1. Bean có thể đến từ nơi không ngờ

Catalog candidates có thể tới từ:

- `@Bean` trong `@Configuration`.
- `@Component` implement functional interface.
- SCF function-specific scanning.
- `FunctionRegistration` qua functional initializer.
- Library autoconfiguration.
- Bean test/demo ngoài ý muốn do component scan quá rộng.

Nếu số candidates thay đổi giữa môi trường, fallback cũng có thể đổi behavior. Cần so runtime artifact và danh sách tên giữa local/staging/prod.

## 18. ineligible-definitions tác động gián tiếp đến fallback

Spring Cloud Function cho phép loại các functional beans không nên vào catalog:

~~~properties
spring.cloud.function.ineligible-definitions=internalMaintenance
~~~

Property này **không phải** nút bật/tắt fallback. Nhưng nó có thể thay đổi số ứng viên mà catalog xem xét.

Ví dụ:

~~~text
Trước filter:
  uppercase
  internalMaintenance
=> Nhiều ứng viên, tên sai thường không fallback.

Sau filter:
  uppercase
=> Một ứng viên; nếu fallback bật, tên sai có thể resolve thành uppercase.
~~~

Do đó một thay đổi filter được thực hiện để giảm bề mặt công bố có thể làm lỗi typo **ẩn đi**, nếu không có strict lookup.

### 18.1. Phòng ngừa

Khi dùng `ineligible-definitions`, cân nhắc thêm:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

và regression test cả ba điều kiện:

1. Internal function **không nằm trong inventory catalog**.
2. Tên internal **không resolve nhầm** thành function khác.
3. Function public **vẫn** được lookup và chạy đúng.

Không chỉ test “internal function bị ẩn” bằng `lookup("internalMaintenance") == null` khi fallback còn bật; kết quả có thể phản ánh fallback sang uppercase thay vì trạng thái đăng ký thật.

## 19. Log/Actuator: quan sát đúng bằng chứng

Để chẩn đoán trong một ứng dụng đang chạy, có thể tạo một `ApplicationRunner` chỉ bật ở profile debug.

~~~java
package demo.fallback;

import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.core.env.Environment;

public final class CatalogFallbackInspector
        implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogFallbackInspector.class);

    private final FunctionCatalog catalog;
    private final Environment environment;

    public CatalogFallbackInspector(
            FunctionCatalog catalog,
            Environment environment) {
        this.catalog = catalog;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String strict = environment.getProperty(
            "spring.cloud.function.single-function-fallback-enabled",
            "<unset>"
        );

        log.info("single-function-fallback-enabled={}", strict);
        log.info("function.definition={}",
            environment.getProperty(
                "spring.cloud.function.definition",
                "<unset>"
            )
        );
        log.info("catalog names={}", catalog.getNames(null));

        String requested = "upprcase";
        log.info("requested name registered={}",
            catalog.getNames(null).contains(requested));

        Function<?, ?> resolved =
            catalog.lookup(Function.class, requested);

        log.info("lookup returned function={}",
            resolved != null);
    }
}
~~~

Bean inspector cần được đăng ký qua `@Bean` hoặc `@Component` trong profile debug, không tự chạy nếu chỉ tạo class. Cẩn trọng: **đoạn code quan sát sẽ cố ý lookup tên sai** để xác minh, nhưng không `apply` hay `subscribe` nên không tự thực hiện side effect nghiệp vụ.

### 19.1. Cẩn thận với log “function found”

Nếu logger chỉ ghi:

~~~text
Requested function 'upprcase' found
~~~

log dễ gây hiểu nhầm. Nên ghi:

~~~text
requestedName=upprcase
registeredName=false
lookupReturnedNonNull=true
fallbackEnabled=true
catalogNames=[uppercase, ...]
~~~

Không tự gắn nhãn “function thực sự tên upprcase” chỉ dựa vào lookup non-null. Với router/registration phức tạp, cần kiểm tra target cuối bằng metadata của framework và trace invocation.

### 19.2. Actuator có thể giúp xác nhận inventory

Khi có Actuator và web dependency phù hợp, Spring Cloud Function có thể cung cấp endpoint `functions`, ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

Sau đó trong môi trường được phép:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

Endpoint có thể liệt kê function metadata. Nó **không tự có mặt** chỉ vì dùng catalog, URL phụ thuộc management base path/port và security; không expose công khai để debug.

### 19.3. Giá trị của catalog.size()

`catalog.size()` giúp quan sát số registration theo API, nhưng trong môi trường có wrappers, framework functions và lazy registration, nó không nhất thiết tương đương “số business functions đủ điều kiện cho fallback”. Dùng `getNames(null)`, bean inventory và thực nghiệm strict lookup kết hợp.

## 20. Đọc cấu hình runtime để tìm khác biệt môi trường

Một lỗi “staging tra cứu sai vẫn trả hàm nhưng production không” thường do các yếu tố:

| Yếu tố khác nhau | Hậu quả |
| --- | --- |
| Số bean chức năng | Fallback có thể bật ở một môi trường nhưng không đủ điều kiện ở môi trường kia |
| Profile/conditional bean | Bean thứ hai chỉ xuất hiện ở prod |
| `ineligible-definitions` | Danh sách ứng viên thay đổi |
| `spring.cloud.function.definition` | Lựa chọn mặc định khác |
| `single-function-fallback-enabled` | Một môi trường strict, môi trường khác permissive |
| Version Spring Cloud Function | Quy tắc xử lý và extension có thể khác |
| Functional bean từ dependency | Thư viện tạo thêm function ứng viên |
| Web/Stream/serverless adapter | Cùng catalog nhưng đường chọn target khác |

### 20.1. Kịch bản đối chiếu

~~~text
LOCAL:
  names = [uppercase]
  fallback = true
  lookup("upprcase") = uppercase

STAGING:
  names = [uppercase, reverse]
  fallback = true
  lookup("upprcase") = not found

PROD:
  names = [uppercase]
  fallback = false
  lookup("upprcase") = not found
~~~

Đây là **tình huống minh họa**, không phải output cố định của mọi phiên bản. Nó cho thấy phải thu thập cả **tập tên**, **giá trị fallback** và **giá trị definition** khi so sánh môi trường.

### 20.2. Đừng tự sửa bằng cách thêm function giả

Một cách đối phó sai là tạo một bean `Function.identity()` thứ hai chỉ để làm catalog có nhiều ứng viên và “ngăn fallback”. Điều đó thay đổi behavior của web adapter, Stream binding và router, có thể làm rối selection hoặc vô tình xuất thêm một endpoint.

Hãy dùng **property được thiết kế để tắt fallback**, không biến cấu trúc catalog thành mẹo kiểm soát lỗi.

## 21. Đánh giá rủi ro nếu lookup sai target có side effect

Trong ví dụ uppercase, fallback chỉ làm trả chuỗi viết hoa nên lỗi có vẻ vô hại. Nhưng giả sử function duy nhất là:

~~~java
@Bean
Function<RebuildCommand, RebuildResult> rebuildIndex(
        IndexMaintenanceService service) {
    return service::rebuild;
}
~~~

Nếu một caller dùng tên sai `validateOrder` nhưng catalog trả `rebuildIndex` do fallback, những rủi ro phụ thuộc dữ liệu và cách gọi:

- Caller có thể gọi nhầm một thao tác quản trị.
- Conversion của wrapper có thể thất bại nếu input sai kiểu.
- Nếu input tương thích, side effect có thể xảy ra.
- Logs hoặc metrics có thể ghi tên do caller yêu cầu, không phản ánh đúng target được chạy.
- Nếu adapter cho phép routing từ input không tin cậy, phải có authorization/allowlist riêng.

### 21.1. Đây không phải bypass bảo mật mặc định

Fallback **không** tự cấp quyền HTTP, broker hay IAM. Rủi ro cần được đánh giá theo các điều kiện cụ thể:

1. Có adapter hoặc caller nào thật sự gọi catalog bằng tên sai không?
2. Caller có quyền tới entry point đó không?
3. Input có đúng kiểu để target chạy không?
4. Target có side effect nhạy cảm không?
5. Có authorization trong business service/adapter không?
6. Đã có logging/audit ghi nhận invocation chưa?

Với business function nhạy cảm, ngoài tắt fallback, cần cấu hình policy ở biên hệ thống và tách chức năng nội bộ khỏi catalog/adapter công khai khi phù hợp.

### 21.2. Bảo vệ sâu hơn tại điểm gọi

Một caller cần target nhất định có thể xác minh inventory trước lookup:

~~~java
static <T> T requireFunction(
        FunctionCatalog catalog,
        String name,
        Class<?> type) {

    if (!catalog.getNames(null).contains(name)) {
        throw new IllegalArgumentException(
            "Function is not registered: " + name
        );
    }

    T function = catalog.lookup(type, name);

    if (function == null) {
        throw new IllegalStateException(
            "Function registration cannot be resolved: " + name
        );
    }

    return function;
}
~~~

Đây là helper minh họa, có thể dùng tại giai đoạn khởi động để kiểm tra config. Generic method chưa kiểm chứng type `T` tại runtime; caller phải dùng đúng interface `Function`/`Supplier`/`Consumer` và signature. Với ứng dụng dùng registration động, thời điểm lấy inventory và lookup cũng cần được đồng bộ theo lifecycle.

Nếu bạn chỉ cần một bean Java cụ thể và không cần wrapper/composition của SCF, có thể inject bean theo type/name trực tiếp; điều đó loại bỏ một lớp name fallback, nhưng phải giữ đúng thiết kế dependency của ứng dụng.

## 22. Quy trình chẩn đoán từng bước

~~~mermaid
flowchart TD
    START["lookup sai tên vẫn trả function"] --> INVENTORY["Ghi lại requestedName\nvà catalog.getNames(null)"]
    INVENTORY --> REGISTERED{"Tên sai có trong inventory?"}
    REGISTERED -->|Có| ALIAS["Kiểm tra bean/alias/registration thật"]
    REGISTERED -->|Không| FALLBACK{"single-function-fallback-enabled?"}
    FALLBACK -->|Bật/không khai báo| COUNT["Xem ứng viên hợp lệ\nsau filter/router"]
    FALLBACK -->|Tắt| OTHER["Kiểm tra definition mặc định,\nrouter hoặc extension"]
    COUNT --> ONE{"Chỉ một ứng viên phù hợp?"}
    ONE -->|Có| CONFIRM["Khả năng cao là single-function fallback"]
    ONE -->|Không| OTHER
    CONFIRM --> FIX["Sửa tên + tắt fallback\n+ kiểm thử âm tính"]
    ALIAS --> FIX
    OTHER --> FIX
    FIX --> VERIFY["Test catalog, HTTP,\nStream và serverless"]
~~~

### 22.1. Checklist xử lý sự cố

1. **Ghi rõ chuỗi tên đã lookup:** `upprcase`, tên composition hay routing target?
2. **Xác định tên đó có thật không:** `catalog.getNames(null)` và Spring bean aliases.
3. **Xác định functional candidates:** số function ứng dụng, loại, filter và router.
4. **Đọc property hiệu lực:** `single-function-fallback-enabled` và `function.definition`.
5. **Đọc phiên bản SCF:** behavior có thể khác giữa các branch/framework extensions.
6. **Tái hiện bằng catalog lookup:** không invoke side effect khi điều tra production.
7. **Sửa tên nguồn:** bean name, definition, routing target hoặc handler mapping.
8. **Tắt fallback nếu muốn strict naming:** cấu hình, restart và xác nhận.
9. **Test typo:** yêu cầu `getNames(null)` không có typo và `lookup(typo)` trả null.
10. **Test target đúng:** function chính xác vẫn nhận input/output đúng.
11. **Test adapter:** HTTP, Stream và serverless không vô tình gọi target khác.
12. **Theo dõi sau deploy:** catalog inventory, errors, function invoked, audit side effects.

### 22.2. Nếu đang xử lý production

Không gọi thử một function nhạy cảm bằng payload thật chỉ để xác minh fallback; invocation có thể có side effect. Hãy ưu tiên API inventory, môi trường staging hoặc fake service. Nếu đã có bằng chứng target không mong muốn được chạy, thực hiện đánh giá tác động nghiệp vụ và xử lý sự cố theo quy trình tổ chức.

## 23. Bảng chọn biện pháp khắc phục

| Vấn đề thực tế | Biện pháp phù hợp | Điều cần xác minh lại |
| --- | --- | --- |
| Gõ sai bean name | Sửa caller/definition | Exact lookup và output đúng |
| Chỉ có một function nên typo bị che | `single-function-fallback-enabled=false` | Typo lookup không còn resolve |
| Thiếu function bắt buộc | Fail-fast bằng inventory + strict lookup | Startup/test báo lỗi rõ |
| Có bean thứ hai ngoài ý muốn | Sửa scan/profile/filter | `getNames(null)` đúng |
| Function nội bộ bị catalog công bố | `ineligible-definitions` hoặc refactor thành service | Context/catalog và đường gọi trực tiếp |
| Stream tự bind một function duy nhất | `spring.cloud.stream.function.autodetect=false` hoặc definition rõ | Runtime bindings |
| HTTP path không như ý định | Kiểm tra web mapping/definition và security | HTTP positive + negative tests |
| Serverless chọn function sai | Handler, definition/routing và strict lookup | Invocation integration test |
| Router nhận tên không tin cậy | Allowlist/authorization, strip headers | Target nhạy cảm không được invoke |
| Test chỉ assert lookup non-null | Kiểm tra inventory và hành vi thực | Tên giả không được chấp nhận |
| Sau refactor function thứ hai lộ lỗi | Sửa typo tồn tại từ trước | Regression test cho số function thay đổi |

Không trộn các property giải quyết vấn đề khác nhau chỉ vì đều chứa chữ “function”. Chúng hoạt động ở các tầng khác nhau.

## 24. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`lookup("foo") != null` chứng minh có bean tên `foo`.” | Có thể chỉ là single-function fallback. |
| “Spring đã tạo alias `foo` khi lookup thành công.” | Fallback không tự tạo Spring bean alias. |
| “Tên sai chỉ fallback nếu truyền `null`.” | Tên không tồn tại cũng có thể fallback khi đủ điều kiện. |
| “Có đúng một tên trong `getNames` là điều kiện tuyệt đối.” | Framework có router/registrations đặc biệt; cần xem ứng viên hợp lệ. |
| “Đã đặt `function.definition` thì typo luôn bị từ chối.” | Fallback có thể che sai tên ở một số đường chọn function. |
| “Tắt fallback xóa function khỏi catalog.” | Nó chỉ thay đổi cơ chế tra cứu, không xóa bean. |
| “Tắt Stream autodetect sẽ tắt catalog fallback.” | Hai property độc lập. |
| “Tắt catalog fallback sẽ tắt HTTP web adapter.” | Không, web mapping là một tầng khác. |
| “Tắt fallback là đủ để bảo vệ function nhạy cảm.” | Cần authorization/IAM và giới hạn đường gọi. |
| “Lỗi typo tự hết khi thêm function thứ hai.” | Nó thường chỉ lộ ra thay vì được che; cần sửa nguồn. |
| “`lookup(null)` luôn thất bại khi fallback tắt.” | Definition mặc định có thể vẫn chọn function. |
| “`uppercase|missing` sẽ fallback thành uppercase.” | Composition có quy tắc riêng; không coi là tên đơn cần fallback. |
| “Các function được trả từ catalog là cùng instance với Spring bean.” | Catalog có thể trả wrapper, không được kiểm tra bằng object identity. |
| “Một Supplier duy nhất nghĩa là gọi như Function được.” | Functional interfaces có hợp đồng khác nhau. |
| “Unit test catalog là đủ chứng minh HTTP route không bị lộ.” | Cần integration test adapter và security. |
| “Khi `Flux` không log gì, catalog trả sai function.” | Publisher cold có thể chưa được subscribe. |

## 25. Câu hỏi tự đánh giá

1. Cơ chế single-function fallback được thiết kế để giải quyết tình huống nào?
2. Vì sao `lookup("upprcase")` có thể trả một function khi catalog chỉ có `uppercase`?
3. Sự khác nhau giữa **tên bean thật** và **tên lookup được chấp nhận do fallback** là gì?
4. Vì sao kiểm tra `lookup(name) != null` không phải test tồn tại của tên?
5. API nào có thể dùng để liệt kê tên thật trong `FunctionCatalog`?
6. Property nào tắt single-function fallback?
7. Tại sao `lookup(null)` vẫn có thể chọn function khi fallback đã tắt?
8. Vì sao thêm một function thứ hai có thể làm lỗi chính tả trước đó xuất hiện?
9. Nếu `ineligible-definitions` loại function thứ hai, điều gì có thể thay đổi ở fallback?
10. Vì sao không nên tạo function giả thứ hai chỉ để ngăn fallback?
11. Composition `uppercase|reverse` có cùng quy tắc fallback với `lookup("upprcase")` không?
12. `spring.cloud.function.definition` có nghĩa là gì và có thay thế việc kiểm tra typo không?
13. `spring.cloud.stream.function.autodetect=false` khác gì `single-function-fallback-enabled=false`?
14. Nếu typed lookup yêu cầu `Function.class` nhưng function duy nhất là `Supplier`, có nên coi đó là function nhận input không?
15. Vì sao một web URL lạ hoạt động không tự chứng minh catalog có bean đúng tên URL?
16. Khi routing target bị lấy từ input người dùng, cần có những kiểm soát nào ngoài tắt fallback?
17. Với serverless, handler và business function name khác nhau như thế nào?
18. Tại sao error-handler lookup nhầm có thể nghiêm trọng hơn một phép uppercase bị gọi nhầm?
19. Làm cách nào viết hai Spring Boot tests so sánh fallback bật và tắt?
20. Những dữ liệu nào cần log để xác nhận fallback mà không invoke side effect?
21. Vì sao unit test về catalog chưa đủ chứng minh Stream binding hoặc HTTP authorization đúng?
22. Nếu local fallback nhưng production không fallback, bạn sẽ đối chiếu những property và danh sách function nào?

## 26. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — giải thích `FunctionCatalog`, `spring.cloud.function.definition`, trường hợp một function có thể lookup bằng bất kỳ tên nào và property `single-function-fallback-enabled`.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionRegistration`, `getNames(null)`, `size()` và cách làm việc với catalog.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — root path khi có một function, HTTP mapping, function selection và filtering.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function definition, auto-binding và các ranh giới message transport.
- [Spring Cloud Function — AWS Lambda Adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html) — handler, function selection và routing tại serverless.
- [Spring Cloud Function — SimpleFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/SimpleFunctionRegistry.java) — tham khảo điều kiện chuẩn hóa tên trong implementation; ưu tiên đối chiếu tag nguồn tương ứng với dependency của dự án.
- [Spring Cloud Function — BeanFactoryAwareFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/BeanFactoryAwareFunctionRegistry.java) — cách lookup qua Spring bean factory và function registrations.

Hành vi chính được mô tả theo tài liệu Spring Cloud Function hiện đại. Khi ứng dụng dùng version/BOM khác, adapter hoặc extension tùy chỉnh, hãy kiểm chứng bằng code/tag và integration test đúng phiên bản đã deploy. Các ví dụ Java là mẫu học tập; không thay thế kiểm thử end-to-end với HTTP, binder, IAM hoặc các dịch vụ có side effect.

**Ghi nhớ:** Khi `FunctionCatalog.lookup("tenSai")` vẫn trả function, **đừng kết luận tên sai đã được đăng ký**. Trong ứng dụng chỉ có một functional candidate hợp lệ, Spring Cloud Function có thể dùng **single-function fallback** để trả hàm duy nhất. Hãy kiểm tra tên thật bằng `catalog.getNames(null)` và `ApplicationContext`, tắt dự phòng bằng `spring.cloud.function.single-function-fallback-enabled=false` nếu cần lựa chọn chính xác, rồi kiểm thử cả **tên đúng** và **tên sai**. Phân biệt cơ chế này với Spring Cloud Stream auto-binding, HTTP route mapping và serverless routing: mỗi tầng cần cấu hình, kiểm thử và bảo vệ riêng để tránh gọi nhầm logic nghiệp vụ.
