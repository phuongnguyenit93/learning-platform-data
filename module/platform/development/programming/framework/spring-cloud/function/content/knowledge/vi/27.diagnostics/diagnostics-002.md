# Hàm ngoài ý muốn được đăng ký hoặc công bố

## 1. Vấn đề: một hàm nội bộ bỗng có thể được gọi từ bên ngoài

Trong một ứng dụng **Spring Cloud Function**, nhóm phát triển viết một hàm để chuẩn hóa đơn hàng và một hàm trợ giúp phục vụ quản trị:

~~~java
@Bean
Function<String, String> normalizeOrder() {
    return String::trim;
}

@Bean
Function<String, String> internalRebuildIndex() {
    return key -> indexMaintenance.rebuild(key);
}
~~~

Người viết `internalRebuildIndex` chỉ muốn các thành phần Java nội bộ gọi nó. Tuy nhiên, cả hai object đều là **Spring beans kiểu `java.util.function.Function`**. Theo mô hình Spring Cloud Function, các functional beans đủ điều kiện trong `ApplicationContext` có thể được đăng ký vào `FunctionCatalog`. Nếu cùng ứng dụng có web adapter hoặc Spring Cloud Stream, một số hàm có thể được **xuất thành endpoint hoặc được chọn cho binding** theo cấu hình của adapter.

Vì vậy một thay đổi tưởng vô hại — thêm `@Bean`, bổ sung starter, bật một profile hoặc import cấu hình từ thư viện — có thể khiến hàm bất ngờ:

- xuất hiện trong `FunctionCatalog.getNames(null)`;
- được HTTP adapter ánh xạ thành route;
- được Spring Cloud Stream tự chọn khi nó là functional bean duy nhất;
- được một composition hoặc `functionRouter` lựa chọn;
- trở thành business function của một serverless invocation.

Đây là đề bài **“Hàm ngoài ý muốn được đăng ký hoặc công bố”** thuộc chương **Chẩn đoán**. Mục tiêu là điều tra chính xác việc gì đã được *đăng ký*, việc gì thực sự *có thể được gọi* và việc gì đã *được gọi*, rồi chặn đúng tại tầng tương ứng.

> **Ba trạng thái phải phân biệt:** **tồn tại trong ApplicationContext**, **có tên trong FunctionCatalog** và **được công bố/được gọi qua một adapter**. Chúng liên quan nhưng không đồng nghĩa.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Xác định các functional beans vô tình được Spring Cloud Function phát hiện.
2. Phân biệt đăng ký vào catalog, xuất HTTP endpoint, tạo Stream binding và serverless routing.
3. Dùng `ApplicationContext`, `FunctionCatalog` và cấu hình runtime để tìm bằng chứng.
4. Kiểm soát `@Bean`/`@Component`, component scanning, function scanning, profile và đăng ký tường minh.
5. Hiểu đúng `spring.cloud.function.ineligible-definitions`, `spring.cloud.function.definition`, `spring.cloud.stream.function.autodetect` và single-function fallback.
6. Tránh để một function nội bộ được gọi ngoài ý muốn qua HTTP header hoặc router.
7. Tổ chức quyền truy cập, test âm tính và quy trình xử lý sự cố.
8. Viết kiểm thử Spring Boot để ngăn một function nội bộ quay lại catalog sau refactor.

## 2. Sơ đồ các tầng: không gộp “đăng ký” với “công bố”

Spring Cloud Function hỗ trợ xây dựng logic nghiệp vụ bằng `Supplier`, `Function` và `Consumer`, tra cứu qua `FunctionCatalog`, composition và chuyển đổi thông điệp. Các adapter HTTP, sự kiện hoặc serverless sử dụng cùng các function đó nhưng quyết định **đường vào**, **cách chọn** và **thời điểm gọi** theo hợp đồng riêng.

~~~mermaid
flowchart TD
    SOURCE["Java code + dependency + component scan"] --> CONTEXT["Spring ApplicationContext"]
    CONTEXT --> CATALOG["FunctionCatalog"]
    CATALOG --> LOOKUP["lookup / composition / functionRouter"]
    LOOKUP --> HTTP["HTTP Web Adapter"]
    LOOKUP --> STREAM["Spring Cloud Stream binder"]
    LOOKUP --> LAMBDA["Serverless adapter"]
    HTTP --> INVOKE["Function được thực thi"]
    STREAM --> INVOKE
    LAMBDA --> INVOKE
    CONTEXT --> DIRECT["Spring bean được gọi trực tiếp\nkhông qua FunctionCatalog"]
~~~

| Tầng | Ý nghĩa | Cách xác minh |
| --- | --- | --- |
| **Bean Spring** | Object được container tạo và quản lý | `containsBean`, `getBeanNamesForType`, bean definition |
| **FunctionCatalog** | Functional bean đủ điều kiện được catalog công bố theo tên; có thể dùng wrapper/composition | `catalog.getNames(null)`, `catalog.lookup(...)` |
| **HTTP export** | Web adapter cung cấp đường dẫn/method để gọi function | Cấu hình web adapter, mapping, request thực |
| **Stream binding** | Binder nối input/output của function với destination | `spring.cloud.function.definition`, binding logs, broker |
| **Serverless invocation** | Runtime/handler chọn business function | Handler, environment, artifact, routing |
| **Invocation** | Function thật sự được gọi và có thể gây side effect | Trace, log nghiệp vụ, audit, metrics |

Một bean có thể tồn tại trong context nhưng không nằm trong catalog. Một function có thể nằm trong catalog nhưng **không có Stream binding**. Một function được bind tới broker chưa chắc có HTTP endpoint. Cần kiểm tra độc lập từng tầng, đặc biệt khi đánh giá rủi ro bảo mật.

### 2.1. Đừng dùng từ “public” quá sớm

`catalog.getNames(null)` có tên `internalRebuildIndex` **không tự chứng minh** người dùng Internet có thể gọi nó. Ngược lại, việc đã bảo vệ HTTP route **không tự chứng minh** function không bị gọi từ broker, router, direct bean injection hoặc một serverless entry point khác.

Để xác định mức độ phơi lộ, cần thêm bằng chứng về **mạng**, **authentication/authorization**, **target selection**, **binding** và **hành vi invocation thực tế**.

## 3. Bắt đầu điều tra từ triệu chứng

Các dấu hiệu thường gặp:

| Triệu chứng | Điều có thể đang xảy ra | Việc cần kiểm tra trước |
| --- | --- | --- |
| `getNames(null)` xuất hiện `internalRebuildIndex` | Bean được catalog nhận diện | Bean type, scan, ineligible filters |
| `/internalRebuildIndex` có response HTTP | Web adapter đang export/route function | Web module, function definition, security, request mapping |
| Broker bất ngờ có consumer hoặc producer | Stream autodetection/binding chọn function | `function.definition`, `function.autodetect`, bindings |
| `Supplier` tự phát message định kỳ | Stream poller tự kích hoạt nguồn | Số functional beans, selected definition, poller |
| Lookup tên sai vẫn chạy function nội bộ | Single-function fallback | Số function đủ điều kiện, fallback property |
| Một HTTP header dẫn tới hàm khác | `functionRouter` hoặc adapter hỗ trợ routing instructions | Routing config, target allowlist, input trust |
| Sau khi thêm dependency xuất hiện function lạ | Autoconfiguration/library bean hoặc function scan | Bean origin, condition report, package |
| Local không có route nhưng production có | Profile/artifact/environment khác | Dependency, active profiles, effective properties |
| Không có HTTP route nhưng function bị gọi | Stream, serverless hoặc direct caller | Trace đường vào, binding, handler |

**Nguyên tắc vận hành:** trước khi xóa bean hay sửa nhiều property, xác định chức năng bất ngờ xuất hiện ở **tầng nào** và liệu có dấu hiệu đã bị gọi ngoài dự kiến hay không.

## 4. Ví dụ có chủ đích: public function và internal function

Ví dụ dùng Java 17+, Spring Boot và Spring Cloud Function. Hai bean có cùng kiểu `Function<String,String>`, nhưng ý định sử dụng khác nhau:

~~~java
package demo.exposure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExposureApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExposureApplication.class, args);
    }

    @Bean
    Function<String, String> publicNormalize() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    // Dùng cho maintenance, KHÔNG được phép export công khai.
    @Bean
    Function<String, String> internalRebuildIndex(
            MaintenanceService service) {
        return service::rebuild;
    }
}
~~~

`MaintenanceService` là dịch vụ giả định với phương thức `String rebuild(String key)`. Trong ví dụ này, bean `internalRebuildIndex` có thể được Spring Cloud Function nhận diện **vì nó thật sự là `Function` bean**, bất kể tên bắt đầu bằng `internal` hay comment nói không công bố.

Đặt tên `internal...` không phải cơ chế an toàn. `private` ở một phương thức factory không phải hàng rào bảo mật đối với object bean đã đăng ký. Cần cấu hình/quyền truy cập đúng tầng.

### 4.1. Ý định khác với kết quả runtime

| Thành phần | Ý định developer | Điều runtime có thể làm |
| --- | --- | --- |
| `publicNormalize` | Xử lý message/HTTP request | Có thể được catalog và adapter chọn |
| `internalRebuildIndex` | Trợ giúp quản trị nội bộ | Vẫn đủ dạng `Function` để vào catalog |
| `MaintenanceService` | Cung cấp API Java nội bộ | Nếu là một service thông thường, không tự thành function catalog |
| `spring-cloud-function-web` | Truy cập HTTP | Có thể tự xuất function thành route nếu web autoconfig hoạt động |
| Stream binder | Xử lý sự kiện | Có thể tự chọn một functional bean khi chỉ có một ứng viên |

Để giảm rủi ro, chức năng quản trị không cần hợp đồng functional nên được biểu diễn bằng **service/domain API bình thường**, thay vì tạo một `@Bean Function` chỉ để tái sử dụng vài dòng code.

## 5. Thu thập bằng chứng: liệt kê bean và catalog

Bước đầu tiên là quan sát ngay trong process đang chạy:

~~~java
import java.util.Arrays;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

FunctionCatalog catalog = context.getBean(FunctionCatalog.class);

System.out.println("Spring Function beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Function.class)
    ));

System.out.println("Spring Supplier beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Supplier.class)
    ));

System.out.println("Spring Consumer beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Consumer.class)
    ));

System.out.println("Catalog names: " + catalog.getNames(null));
System.out.println("Catalog size: " + catalog.size());
~~~

Hai tập tên có thể khác nhau:

- `ApplicationContext` phản ánh các bean mà Spring nhận diện theo type.
- `FunctionCatalog` cung cấp tên các function đủ điều kiện, kèm khả năng wrapper/đăng ký riêng.
- Một function có thể bị SCF loại trừ khỏi catalog nhưng bean vẫn tồn tại và caller Spring vẫn có thể inject trực tiếp.
- Một function có thể do `FunctionRegistration` hoặc function scan đưa vào theo cơ chế không giống `@Bean` thông thường.

### 5.1. Đọc cấu hình có hiệu lực, không chỉ file local

~~~java
import org.springframework.core.env.Environment;

void reportSettings(Environment environment) {
    for (String key : new String[] {
        "spring.cloud.function.definition",
        "spring.cloud.function.scan.packages",
        "spring.cloud.function.scan.enabled",
        "spring.cloud.function.ineligible-definitions",
        "spring.cloud.function.single-function-fallback-enabled",
        "spring.cloud.stream.function.autodetect",
        "spring.cloud.function.web.path"
    }) {
        System.out.println(key + "=" +
            environment.getProperty(key, "<unset>"));
    }
}
~~~

Đoạn này chỉ in **một allowlist các property không chứa secret theo thiết kế**. Không thay bằng việc log toàn bộ `Environment`, tất cả headers hoặc payload.

Một property trong file `application.yml` chưa chắc là giá trị runtime: command-line argument, environment variable, profile hoặc deployment config có thể ghi đè. Cần nhìn giá trị **hiệu lực trong process**.

### 5.2. Trace nguồn gốc bean bất ngờ

Với tên đã tìm thấy:

~~~java
String name = "internalRebuildIndex";

System.out.println("exists=" + context.containsBean(name));
System.out.println("type=" + context.getType(name));
System.out.println("catalog=" + catalog.getNames(null).contains(name));
~~~

Nếu cần tìm factory method, resource source hoặc condition, sử dụng `ConfigurableListableBeanFactory` và bean definition metadata trong môi trường debug có kiểm soát. Với bean từ thư viện, kiểm tra chính xác `factoryBeanName`, `factoryMethodName`, resource description và condition evaluation report; **không đọc toàn bộ dependencies ngoài phạm vi công việc nếu chưa cần**.

**Lưu ý:** `catalog.lookup("someName") != null` không luôn chứng minh tên có thật vì single-function fallback có thể trả function duy nhất khi tên sai. Dùng `getNames(null)` làm phép kiểm chứng tên và test khi fallback bị tắt.

## 6. Nguyên nhân A: @Bean trả Function/Supplier/Consumer chỉ để dùng nội bộ

Một phương thức `@Bean` là lời khai báo rằng object trả về thuộc Spring container:

~~~java
@Bean
Function<String, String> internalFormatter() {
    return input -> internalFormat(input);
}
~~~

Nếu dự án chỉ cần phép biến đổi trong một service khác, đây có thể là **lựa chọn abstraction quá rộng**. SCF nhận diện bean theo functional interface, chứ không đọc ý định “internal” qua tên hoặc comment.

### 6.1. Giải pháp bền vững: service thông thường

~~~java
import org.springframework.stereotype.Service;

@Service
public class InternalFormatter {

    public String normalizeForAudit(String input) {
        return input.trim();
    }
}
~~~

Function được phép công bố có thể inject service:

~~~java
@Bean
Function<String, String> publicNormalize(InternalFormatter formatter) {
    return formatter::normalizeForAudit;
}
~~~

Trong mô hình này:

- `InternalFormatter` là bean nghiệp vụ kiểu service, không phải functional bean.
- `publicNormalize` là functional bean được công bố theo ý định.
- Không cần một `@Bean Function` riêng cho việc format nội bộ.
- Có thể kiểm soát rõ danh sách các function muốn export.

### 6.2. Đừng xóa bean khi vẫn có dependency sử dụng nó

Nếu nhiều thành phần đang inject bean `internalFormatter` theo tên/type, việc đổi sang service cần refactor DI cho phù hợp. Tạo regression test trước khi xóa hoặc đổi bean, nhất là khi nó còn được gọi trực tiếp từ batch hoặc workflow khác.

### 6.3. Một @Bean Supplier cũng có thể gây side effect

~~~java
@Bean
Supplier<String> internalStatusSnapshot() {
    return () -> statusService.snapshot();
}
~~~

Với Spring Cloud Stream và một functional bean đủ điều kiện, supplier có thể được tự chọn làm source và được poll theo cấu hình. `Supplier.get()` có thể thực hiện I/O hoặc phát dữ liệu vốn chỉ dùng để debug. Đây không chỉ là nguy cơ “thêm tên vào danh sách”; nó có thể tạo **công việc nền ngoài ý muốn**.

Nếu chỉ muốn API nội bộ, dùng service với phương thức `snapshot()` thay vì tạo `Supplier` bean cho mọi adapter.

## 7. Nguyên nhân B: component scan quét quá rộng

Một class `@Configuration` nằm trong package được Spring scan sẽ đăng ký các `@Bean` bên trong, kể cả những function chỉ dành cho test, demo hoặc maintenance.

~~~java
@Configuration
public class ExperimentalFunctions {

    @Bean
    Function<String, String> debugEcho() {
        return Function.identity();
    }
}
~~~

Nếu `ExperimentalFunctions` vô tình nằm trong package quét của production, `debugEcho` có thể trở thành ứng viên catalog.

### 7.1. Cách sửa theo đúng phạm vi

- Di chuyển cấu hình demo/test khỏi production source set.
- Chỉ `@Import` các cấu hình chức năng có chủ đích.
- Giữ `@SpringBootApplication` và component scan ở package hợp lý.
- Dùng `@Profile` hoặc `@ConditionalOnProperty` để tạo bean chỉ trong môi trường phù hợp.
- Kiểm tra các thư viện/starter mới có import thêm cấu hình chức năng không.

Ví dụ giới hạn bean debug:

~~~java
@Configuration
@Profile("local-debug")
class DebugFunctionConfiguration {

    @Bean
    Function<String, String> debugEcho() {
        return Function.identity();
    }
}
~~~

Nếu profile `local-debug` không active, bean không được tạo; đây là kiểm soát **ở tầng ApplicationContext**. Nhưng profile không phải cơ chế authorization: không được bật nhầm profile ở production rồi cho rằng tên `debugEcho` tự an toàn.

### 7.2. Kiểm tra @Component trên functional class

~~~java
@Component
public class InternalEcho implements Function<String, String> {
    @Override
    public String apply(String value) {
        return value;
    }
}
~~~

Class này là **một Spring bean** và implement Java `Function`, nên có thể vào catalog nếu đủ điều kiện. Nếu không muốn catalog nhận diện, đừng triển khai/đăng ký nó dưới dạng functional bean ở cùng context.

## 8. Nguyên nhân C: Spring Cloud Function tự scan package chức năng

Ngoài component scanning thông thường của Spring, SCF có **Function Component Scan**. Tài liệu mô tả cơ chế tìm các implementation của `Function`, `Consumer`, `Supplier` trong package tên `functions` theo convention, kể cả khi class không có `@Component`.

Ví dụ:

~~~java
package functions;

import java.util.function.Function;

public class DebugEcho implements Function<String, String> {
    @Override
    public String apply(String input) {
        return input;
    }
}
~~~

Một class tưởng chỉ là helper có thể được phát hiện khi SCF function scanning được bật.

Các property liên quan:

~~~properties
spring.cloud.function.scan.packages=demo.allowed.functions
spring.cloud.function.scan.enabled=false
~~~

Hai dòng trên là **hai phương án cấu hình để minh họa**, không nên coi là cần đặt đồng thời. Nếu `scan.enabled=false`, chức năng scan đặc thù bị tắt dù đã chỉ định package.

### 8.1. Cách lựa chọn

| Mong muốn | Cách xử lý |
| --- | --- |
| Không cần function scan tự động | `spring.cloud.function.scan.enabled=false` |
| Vẫn cần scan nhưng không muốn quét package test/debug | `spring.cloud.function.scan.packages` chỉ tới package cho phép |
| Chủ yếu dùng `@Bean` tường minh | Giữ Spring component scanning phù hợp; SCF scan không bắt buộc |
| Phải giữ một class functional nhưng không được export | Xem lại registration + `ineligible-definitions` hoặc tách context/artifact |

**Quan trọng:** tắt **SCF function scan** không xóa các bean chức năng được tạo qua Spring `@Bean` hoặc `@Component`. Đây là hai cơ chế phát hiện khác nhau.

### 8.2. Regression sau khi thêm package

Sau một lần refactor package `functions`, catalog có thể bất ngờ thêm function. Test phải kiểm tra **danh sách toàn bộ tên catalog** hoặc ít nhất một denylist các function nội bộ, thay vì chỉ kiểm tra function được chọn vẫn chạy.

## 9. Nguyên nhân D: autoconfiguration hoặc dependency thêm functional bean

Một thư viện hoặc starter có thể tạo bean kiểu `Function`, `Consumer`, `Supplier` để phục vụ mục đích nội bộ. SCF mặc định có cơ chế lọc một số known ineligible beans, nhưng một bean mới từ thư viện/ứng dụng có thể vẫn được catalog xem là ứng viên.

Các dấu hiệu:

- Trước khi cập nhật dependency, catalog không có `auditLibraryFunction`.
- Sau khi thay BOM/starter, `getNames(null)` có thêm tên đó.
- `ApplicationContext` có bean do một configuration class trong dependency tạo.
- Không có code app nào trực tiếp khai báo function mới.

### 9.1. Kiểm tra trước khi loại bỏ

1. Xác định nguồn gốc bean và điều kiện tạo.
2. Xem library có API/config để tắt bean không cần thiết không.
3. Kiểm tra chức năng nào trong ứng dụng đang inject bean đó.
4. Nếu bean cần ở context nhưng không nên vào catalog, dùng filter của SCF.
5. Nếu bean không cần, điều chỉnh dependency/autoconfiguration hoặc profile có chủ đích.

Không tự xóa một bean thư viện đang được các thành phần khác sử dụng. Lỗi injection sau đó có thể nghiêm trọng hơn việc tên xuất hiện trong catalog.

## 10. Kiểm soát tại catalog: ineligible-definitions

Spring Cloud Function có property:

~~~properties
spring.cloud.function.ineligible-definitions=internalRebuildIndex,debugEcho
~~~

Theo hợp đồng của SCF, danh sách này bổ sung các bean definition names không nên là ứng viên của `FunctionCatalog`.

### 10.1. Chính xác property này làm gì?

Giả sử có bean:

~~~java
@Bean
Function<String, String> internalRebuildIndex(
        MaintenanceService service) {
    return service::rebuild;
}
~~~

Với filter tương ứng:

- Spring `ApplicationContext` **vẫn có thể chứa** bean `internalRebuildIndex`.
- Các caller inject bean trực tiếp vẫn có thể gọi nó.
- Catalog không nên công bố tên này như functional candidate theo cấu hình.
- Adapter chỉ tra cứu thông qua catalog sẽ không thể chọn bean theo tên catalog đó nếu filter có hiệu lực.
- Không đồng nghĩa toàn bộ ứng dụng đã an toàn, vì một route hoặc service khác có thể gọi bean trực tiếp.

### 10.2. Verify sau khi áp dụng

~~~java
boolean existsInContext =
    applicationContext.containsBean("internalRebuildIndex");

boolean appearsInCatalog =
    functionCatalog.getNames(null)
        .contains("internalRebuildIndex");

System.out.println(existsInContext); // Có thể là true.
System.out.println(appearsInCatalog); // Mong đợi false.
~~~

Không chỉ test `lookup("internalRebuildIndex") == null` khi single-function fallback có thể đang bật. Nên tắt fallback trong test để kết quả không bị thay bằng function khác.

### 10.3. Bảng so sánh các biện pháp

| Biện pháp | Bean còn trong Spring context? | Có nhằm chặn catalog registration? | Có trực tiếp chặn HTTP/Stream? |
| --- | --- | --- | --- |
| Không tạo `@Bean` / refactor thành service | Không còn functional bean đó | Có, tại nguồn | Gián tiếp vì không còn target |
| `@Profile` / `@ConditionalOnProperty` không kích hoạt | Không | Có, vì bean không được tạo | Gián tiếp |
| `spring.cloud.function.scan.enabled=false` | Không ảnh hưởng `@Bean` thông thường | Chặn một nguồn registration qua SCF scan | Gián tiếp với class chỉ scan bằng SCF |
| `spring.cloud.function.ineligible-definitions` | Có thể còn | Có, tại catalog | Gián tiếp với adapter dựa vào catalog |
| `spring.cloud.function.definition` | Thường vẫn còn | **Không**, chủ yếu chọn/export function | Có tác động tùy adapter |
| Spring Security/IAM/gateway | Vẫn còn | **Không** | Kiểm soát quyền gọi tại biên |

`ineligible-definitions` là một công cụ **giảm bề mặt công bố**, không phải security boundary độc lập thay thế authentication/authorization.

### 10.4. Điều nên tránh

- Không thêm wildcard hoặc tên đoán chừng mà không kiểm tra tên bean thật.
- Không loại nhầm function cần dùng trong composition.
- Không giả định property của file local đã là property hiệu lực ở production.
- Không coi một bean bị filter là tuyệt đối không thể thực thi.
- Không xóa hết các filter mặc định của framework khi điều tra một tên lạ.

## 11. Kiểm soát tại HTTP: web adapter có thể tự xuất function

Theo tài liệu Spring Cloud Function, module `spring-cloud-function-web` khi được kích hoạt trong một Spring Boot web application hỗ trợ xuất functional beans thành các HTTP endpoints. Mỗi tên function có thể trở thành một phần đường dẫn URL.

Ví dụ khi catalog có `publicNormalize` và `internalRebuildIndex`, web adapter **có thể xuất cả hai** nếu không có giới hạn phù hợp.

~~~bash
# Ví dụ minh họa với web adapter đã chạy:
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data " ord-100 " \
  http://localhost:8080/publicNormalize

# Cần kiểm tra endpoint này có bị xuất ngoài ý muốn không:
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "index-42" \
  http://localhost:8080/internalRebuildIndex
~~~

**Không thực hiện request thứ hai trên production khi nó có side effect nếu chưa được cho phép.** Trong điều tra, ưu tiên mapping metadata, staging hoặc một test adapter mô phỏng, tránh vô tình chạy lệnh quản trị thật.

### 11.1. Khả năng xuất HTTP khác với FunctionCatalog

| Kiểm tra | Điều chứng minh |
| --- | --- |
| `catalog.getNames(null)` chứa `internalRebuildIndex` | Catalog biết tên |
| Có bean `spring-cloud-function-web` và web mapping | HTTP adapter đang hoạt động |
| Route `/internalRebuildIndex` được map | Có đường HTTP tương ứng |
| Request không xác thực được thực thi | Đã có rủi ro công bố truy cập không phù hợp |
| Route trả 401/403 cho caller không có quyền | Có lớp kiểm soát quyền, nhưng vẫn cần test các đường gọi khác |

Không dùng mã trạng thái 404 như bằng chứng duy nhất rằng catalog không có tên. Web adapter còn có base path, function selection, routing và các quy tắc fallback.

### 11.2. Chọn danh sách function được xuất

Tài liệu web adapter mô tả dùng `spring.cloud.function.definition` với dấu `;` để chỉ những function/composition được xuất trong trường hợp có nhiều function trong catalog:

~~~properties
spring.cloud.function.definition=publicNormalize;publicReverse
~~~

Giả sử app thật sự có hai function được phép công bố như trên; khi cấu hình được áp dụng, web adapter chỉ định các function cần export theo danh sách.

Dấu `|` mang ý nghĩa **composition**, không phải hai route độc lập:

~~~properties
# Một composition: A rồi B.
spring.cloud.function.definition=publicNormalize|publicReverse
~~~

### 11.3. Cẩn trọng với selection một function duy nhất

Ở một số quy tắc web mapping, một definition duy nhất còn được dùng để **map function hoặc composition ra root path**, thậm chí làm fallback mapping khi URL không trùng tên catalog. Vì vậy:

- Không xem việc đặt `spring.cloud.function.definition=publicNormalize` một cách đơn lẻ là một **access-control list** đủ mạnh trong mọi cấu hình.
- Khi muốn allowlist web route, kiểm tra đúng quy tắc selection/export của phiên bản adapter.
- Viết **negative integration test** cho URL không được phép, không chỉ positive test cho URL mong muốn.
- Với chức năng nhạy cảm, tách khỏi web-exposed context/artifact hoặc chặn ở Spring Security/gateway thay vì dựa duy nhất vào convention tên.
- Không để internal function trong catalog nếu không có nhu cầu gọi qua catalog.

### 11.4. HTTP method và path cũng cần kiểm tra

Web adapter hỗ trợ một số quy tắc mapping theo loại function và HTTP method; `spring.cloud.function.web.path` có thể đổi base path. Spring Cloud Function còn có cấu hình method-specific cho một số trường hợp.

Nhưng hạn chế HTTP method **không phải thay thế authorization**. Chỉ cho phép POST không khiến một lệnh rebuild index trở nên an toàn đối với caller không có quyền. Cần xác thực và phân quyền tại biên hệ thống.

## 12. Function routing và HTTP headers: nguy cơ chọn target ngoài ý muốn

Spring Cloud Function có `functionRouter` giúp quyết định function sẽ được gọi. Routing instructions có thể đến từ application properties hoặc, với các trường hợp phù hợp, `Message` headers như `spring.cloud.function.definition` và `spring.cloud.function.routing-expression`.

Ví dụ khái niệm:

~~~properties
spring.cloud.function.definition=functionRouter
spring.cloud.function.routing-expression=headers.targetFunction
~~~

Nếu hệ thống chuyển một request header do client kiểm soát thành `targetFunction` mà không xác thực/giới hạn, caller có thể cố yêu cầu router gọi một function không dành cho họ.

### 12.1. Đường đi rủi ro

~~~mermaid
flowchart LR
    CLIENT["HTTP client / external event"] --> HEADER["Routing instruction / header"]
    HEADER --> ROUTER["functionRouter"]
    ROUTER --> CATALOG["FunctionCatalog.lookup(target)"]
    CATALOG --> INTERNAL["Internal Function có side effect"]
~~~

Không được mặc định rằng tất cả HTTP headers tự động được phép chọn arbitrary target ở mọi cấu hình. **Phải kiểm tra đường chuyển header và routing thực tế**. Nhưng khi bạn chủ động xây router lấy target từ input không tin cậy, cần kiểm soát danh sách được phép.

### 12.2. Những lớp bảo vệ quan trọng

1. Chỉ cho caller đã xác thực đưa ra routing instructions.
2. Ở biên HTTP/broker, loại bỏ hoặc ghi đè các header điều khiển nội bộ không được phép.
3. Thực hiện **allowlist** target theo vai trò/capability, không dựa vào chuỗi tên ngẫu nhiên.
4. Không expose internal function qua catalog nếu không cần.
5. Ghi audit **target thực sự được chọn** và caller identity, tránh log secret.
6. Có negative test: user không có quyền không thể route đến `internalRebuildIndex`.

Tài liệu Spring Cloud Function phân biệt expression từ **message headers** với expression từ **application properties** về ngữ cảnh đánh giá. Expression từ header sử dụng ngữ cảnh hạn chế hơn, nhưng điều này **không thay thế quy tắc authorization function đích**.

### 12.3. Reactive routing có đơn vị xử lý khác

Với imperative `Function<T,R>`, một message có thể là đơn vị routing khi adapter hỗ trợ. Với `Function<Flux<T>, Flux<R>>`, đơn vị gọi có thể là cả stream; routing theo header từng message không có cùng semantics và tài liệu hướng dẫn dùng routing instructions ở application properties cho reactive function.

Nếu adapter đang route **toàn stream**, một route sai có thể khiến nhiều event đi vào function không mong muốn. Hãy test theo đúng chữ ký và adapter thực tế.

## 13. Single-function fallback: tên sai vẫn có thể gọi function duy nhất

Spring Cloud Function hỗ trợ *single-function fallback*: khi chỉ có một functional bean đủ điều kiện, lookup không tên hoặc tên không đúng có thể resolve thành function duy nhất.

Ví dụ nếu catalog chỉ có `internalRebuildIndex`:

~~~java
var maybeInternal = catalog.lookup("doesNotExist");
~~~

Tùy cấu hình fallback, `maybeInternal` vẫn có thể trỏ tới function duy nhất. Nguy cơ đặc biệt xuất hiện khi một adapter/router/caller truyền sai tên mà ứng dụng vẫn thực thi một chức năng có side effect.

### 13.1. Tắt fallback khi cần selection chính xác

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Khi fallback bị tắt, caller phải dùng tên thực của function. Đây là cấu hình rất hữu ích cho regression test, môi trường có nhiều đường routing và các chức năng nhạy cảm.

**Lưu ý:** tắt fallback không xóa bean khỏi catalog và không tự thêm authentication. Nó chỉ giảm nguy cơ một tên sai được ánh xạ sang function duy nhất.

### 13.2. Đừng chỉ test lookup("internal") == null

Khi kiểm thử internal function bị loại:

1. Kiểm tra `catalog.getNames(null)` không chứa tên internal.
2. Tắt fallback.
3. Xác nhận `lookup("internalRebuildIndex")` không resolve.
4. Kiểm tra lại HTTP/Stream/serverless đường vào.
5. Đảm bảo direct bean injection chỉ xảy ra trong luồng được phép.

## 14. Spring Cloud Stream: function duy nhất có thể bị auto-bind

Một rủi ro ít được chú ý: khi ứng dụng Spring Cloud Stream chỉ có **một functional bean**, framework có thể tự phát hiện và bind bean đó dù bạn **không đặt `spring.cloud.function.definition`**. Tài liệu Stream khuyến nghị dùng property definition tường minh để tránh bất ngờ.

Giả sử ứng dụng chỉ có:

~~~java
@Bean
Supplier<String> internalStatusSnapshot() {
    return () -> statusService.snapshot();
}
~~~

Nếu được Stream tự chọn như một source, supplier có thể được poll theo lịch và phát thông điệp ra output binding, thay vì chỉ nằm yên chờ người trong ứng dụng gọi `get()`.

### 14.1. Tắt single-function autodetection của Stream

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

Property này xử lý **cơ chế auto-discovery/auto-binding của Spring Cloud Stream**. Nó không có nghĩa:

- Xóa bean khỏi `ApplicationContext`.
- Xóa bean khỏi `FunctionCatalog`.
- Tắt web adapter.
- Vô hiệu hóa một binding được cấu hình **tường minh** theo definition hoặc cách khác.
- Tắt các `Supplier`/poller tự quản do code ứng dụng tạo riêng.

Đừng nhầm `spring.cloud.stream.function.autodetect` với `spring.cloud.function.single-function-fallback-enabled`: cái đầu liên quan **auto-binding vào Stream**, cái sau liên quan **catalog lookup fallback**.

### 14.2. Chọn function binding tường minh

~~~properties
spring.cloud.function.definition=publicNormalize

spring.cloud.stream.bindings.publicNormalize-in-0.destination=orders-in
spring.cloud.stream.bindings.publicNormalize-out-0.destination=orders-out
~~~

Ở đây `publicNormalize` là function được chọn, còn `orders-in`/`orders-out` là broker destinations. Nếu `internalRebuildIndex` vẫn nằm trong catalog, việc cấu hình definition để chỉ bind `publicNormalize` **không loại nó khỏi catalog hay HTTP**.

### 14.3. Dấu ; và dấu | có tác động lớn

~~~properties
# Hai function/bindings độc lập:
spring.cloud.function.definition=publicNormalize;internalRebuildIndex
~~~

Nếu một developer vô tình thêm function internal sau dấu `;`, ứng dụng có thể tạo binding mới cho nó.

~~~properties
# Một composition, đầu ra publicNormalize đi vào internalRebuildIndex:
spring.cloud.function.definition=publicNormalize|internalRebuildIndex
~~~

Trường hợp này còn có thể **thực thi hàm internal như một bước của pipeline**. Khi đánh giá phơi lộ, không chỉ kiểm tra internal là function đầu vào trực tiếp, mà còn kiểm tra nó có mặt trong bất kỳ composition hoặc routing target nào hay không.

### 14.4. Đừng nhầm Stream binding với FunctionCatalog

| Tên | Ví dụ | Công dụng |
| --- | --- | --- |
| Function | `publicNormalize` | Lookup logic |
| Binding input | `publicNormalize-in-0` | Cổng nhận message |
| Binding output | `publicNormalize-out-0` | Cổng gửi message |
| Destination | `orders-in` | Topic/queue ngoài hệ thống |

Một binding/destination được tạo do cấu hình explicit còn có thể liên quan `StreamBridge` mà không gắn trực tiếp với function. Vì vậy muốn kết luận chức năng internal đã được Stream bind, phải xem **runtime bindings** chứ không chỉ danh sách destination.

## 15. Supplier và @PollableBean: công việc có thể chạy dù không có request HTTP

`Supplier<T>` không có input nên cần tác nhân bên ngoài gọi `get()`. Trong Spring Cloud Stream, poller có thể kích hoạt supplier imperative định kỳ; reactive supplier liên tục thường được lấy publisher và subscribe theo adapter. `@PollableBean` đánh dấu reactive supplier hữu hạn có thể cần polling lặp lại.

~~~java
@Bean
Supplier<String> debugHeartbeat() {
    return () -> "heartbeat";
}
~~~

Nếu function này vô tình thành source binding, nó có thể phát message định kỳ. Với supplier làm truy vấn database hoặc tạo báo cáo tốn tài nguyên, tác động thực tế là:

- Truy vấn chạy ngoài lịch dự kiến.
- Dữ liệu có thể được publish tới một destination không chủ đích.
- Hệ thống phát sinh chi phí hoặc tải nền.
- Một số message có thể chứa thông tin nội bộ.

**Không dựa vào “chẳng ai gọi HTTP endpoint của supplier” để khẳng định supplier an toàn.** Kiểm tra Stream binding, poller, function definition và adapter khác.

### 15.1. @PollableBean không tự tạo lịch ở Function Core

Annotation này là marker; chính adapter/poller bên ngoài quyết định khi nào poll. Nếu thấy supplier bị gọi lặp lại, cần tìm **poller đang hoạt động**, không chỉ nhìn annotation.

### 15.2. Tắt hoặc giới hạn ở đúng tầng

- Nếu supplier không cần là functional bean, đổi thành service API.
- Nếu không muốn catalog đăng ký, dùng `ineligible-definitions` hoặc không tạo bean.
- Nếu không muốn Stream tự bind, tắt autodetect hoặc chọn definition tường minh.
- Nếu đã có binding explicit, phải loại binding/definition liên quan.
- Nếu poller do code riêng tạo, cần dừng scheduler/consumer đó.
- Nếu publisher đang chạy dài hạn, quản lý subscription và cancellation đúng lifecycle.

## 16. Serverless: handler được deploy có thể gọi function không mong muốn

Ở serverless (ví dụ AWS Lambda adapter), runtime gọi một **handler/entry point**, rồi adapter dùng FunctionCatalog/routing để tìm business function.

Một sai lầm phổ biến là nghĩ chỉ cần tên Java class không xuất hiện trong handler config thì function nội bộ sẽ không được gọi. Thực tế handler và business function là **hai tầng độc lập**.

### 16.1. Bảng kiểm soát

| Tầng | Cần xác nhận |
| --- | --- |
| Artifact | JAR/container có chứa các function nào, cấu hình nào active? |
| Handler | Runtime gọi đúng adapter/handler? |
| Catalog | Có function internal bị đăng ký không? |
| Definition/routing | Invocation chọn đúng function được phép? |
| IAM/authorization | Ai có quyền invoke function của nền tảng? |
| Event payload | Có header/field nào điều khiển lựa chọn function? |
| Timeout/retry | Invocation có thể chạy lại side effect ngoài ý muốn? |

Nếu một Lambda có nhiều functional beans mà selection không rõ, lựa chọn có thể không như mong đợi. Nên dùng definition/routing có chủ đích và kiểm thử trên artifact giống deployment.

### 16.2. Phòng thủ nhiều lớp

Cấu hình đúng business function, kiểm soát quyền invoke của runtime và loại internal function khỏi catalog khi không cần. Một endpoint/serverless invocation được bảo vệ bằng IAM vẫn phải được kiểm thử để không gọi một function khác thông qua routing headers mà caller có thể tác động.

## 17. FunctionCatalog, composition và FunctionRegistration

Tài liệu SCF nêu rằng các functional beans trong `ApplicationContext` được đăng ký vào catalog theo cơ chế lazy. Ngoài `@Bean`, còn có **`FunctionRegistration`** và functional startup model.

Vì vậy, điều tra chỉ tìm `@Bean Function` trong source chưa đủ nếu ứng dụng:

- đăng ký function qua initializer;
- cấu hình `FunctionalSpringApplication`;
- tạo `FunctionRegistration` với tên cụ thể;
- dùng thư viện tự đăng ký chức năng;
- có composition hoặc router được tạo từ các function có sẵn.

### 17.1. Tên composition cũng có thể trở thành target

~~~properties
spring.cloud.function.definition=publicNormalize|internalRebuildIndex
~~~

Dù `internalRebuildIndex` không được caller tra trực tiếp, nó vẫn được yêu cầu như một phần của **definition**. Do đó phải review tất cả composition đang dùng.

### 17.2. Đừng dùng filter catalog để sửa business logic

Nếu `internalRebuildIndex` thực sự là bước nội bộ trong một flow được phép, việc loại nó khỏi catalog có thể làm composition `publicNormalize|internalRebuildIndex` thất bại. Nên:

1. Đánh giá flow có thực sự cần target là functional bean độc lập không.
2. Nếu chỉ là dependency của `publicNormalize`, chuyển thành service được gọi bên trong.
3. Nếu phải composition, bảo vệ đường chọn function và chỉ cho phép route phù hợp.
4. Test cả đường được phép lẫn bị cấm.

**Câu hỏi thiết kế:** cần một **hàm để composition** hay chỉ cần một **phương thức nghiệp vụ**? Không phải mọi helper đều nên là functional bean công bố trong catalog.

## 18. Kiểm soát bảo mật: lọc tên không phải authorization

Nếu function thực hiện thao tác nhạy cảm như xóa dữ liệu, rebuild index, tạo token hoặc gửi thông tin khách hàng, rủi ro không chỉ là “nó có tên trong catalog”. Rủi ro là **ai có thể kích hoạt nó bằng cách nào**.

### 18.1. Phân tầng biện pháp

| Biện pháp | Vai trò | Giới hạn |
| --- | --- | --- |
| Không đăng ký internal function | Giảm bề mặt chức năng | Các service khác vẫn có thể gọi API tương đương |
| `ineligible-definitions` | Không cho catalog coi bean là ứng viên | Không xóa bean khỏi context |
| HTTP function selection | Giới hạn function được web adapter xuất | Cần kiểm tra fallback/mapping thực; không tự xác thực |
| Spring Security/gateway | Authentication, authorization, request restrictions | Phải bao phủ mọi route/routing path |
| Binder ACL/IAM | Giới hạn ai có thể publish/consume message | Không thay kiểm soát nghiệp vụ |
| Serverless IAM | Giới hạn quyền invoke function runtime | Không tự giới hạn target nội bộ trong catalog |
| Audit logs/metrics | Phát hiện invocation bất thường | Không ngăn lệnh đã chạy |
| Separate deployment/context | Tách miền tin cậy | Tăng chi phí vận hành nhưng giảm giao thoa |

**Khuyến nghị thiết kế:** với các chức năng có ảnh hưởng lớn, ưu tiên đặt chúng trong **application/context hoặc deployment nội bộ riêng** nếu cần cách ly đáng tin cậy. Tên bean không phải ranh giới bảo mật.

### 18.2. Ví dụ chính sách HTTP

Trong một ứng dụng có Spring Security, bạn có thể thiết kế bảo vệ theo path:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/publicNormalize")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

Đây là **đoạn minh họa một phần**, giả định app sử dụng Spring Security phiên bản hỗ trợ DSL trên, có cấu hình JWT đầy đủ và policy CSRF phù hợp với API. Trong production, cần xác định base path, HTTP method, proxy rewrite, Actuator/management port và các route dạng composition/root/fallback; không copy nguyên snippet để coi là bảo mật hoàn chỉnh.

Mục tiêu ví dụ là **allowlist quyền theo route** và deny-by-default, không phải tắt toàn bộ security để thử endpoint.

### 18.3. Nếu route có thể được remap bằng definition?

Có cấu hình web adapter cho phép map function/composition tới root hoặc xử lý những path không trùng tên catalog. Vì thế một security rule chỉ dựa trên `/internalRebuildIndex` có thể không đủ nếu cùng function còn được gọi qua root/composition/routing. Tính quyền phải gắn với **target hoặc capability cuối cùng**, cùng với network/auth layer và negative tests.

## 19. Quy trình xử lý khi phát hiện function nội bộ đã bị công bố

Nếu có dấu hiệu function nhạy cảm hiện đang accessible, nên ưu tiên giảm rủi ro trước rồi mới refactor.

### 19.1. Trình tự ứng phó

1. **Ghi nhận bằng chứng không phá hủy:** tên function, version, cấu hình hiệu lực, mapping, binding, thời gian và trace có sẵn.
2. **Xác định đường vào:** HTTP, broker, serverless, router hay direct caller; các đường này có thể cùng tồn tại.
3. **Chặn quyền gọi không được phép:** thay đổi authorization/gateway/broker ACL/IAM hoặc tạm tắt binding/route theo quy trình vận hành.
4. **Kiểm tra tác động đã xảy ra:** logs và audit có cho thấy invocation, tác dụng phụ hoặc rò rỉ dữ liệu không?
5. **Đưa ra sửa lỗi tối thiểu:** lọc catalog, đổi bean registration, giới hạn definition, tắt autodetect hoặc loại adapter không cần.
6. **Test âm tính và dương tính:** internal target không gọi được; public function hợp lệ vẫn hoạt động.
7. **Rollout có kiểm soát:** quan sát startup, catalog names, bindings, HTTP routes và metrics sau deploy.
8. **Ngăn tái diễn:** bổ sung regression tests, review cấu hình và code ownership.

**Không thực hiện thử nghiệm có side effect bằng cách gửi request tới admin function đang nghi bị lộ** trên production. Ưu tiên kiểm tra mapping, staging hoặc thực thi giả lập. Nếu đã xảy ra truy cập trái phép, làm theo quy trình ứng cứu bảo mật của tổ chức, bao gồm đánh giá thay đổi dữ liệu và thông tin xác thực nếu cần.

### 19.2. Tránh biện pháp chữa sai tầng

Ví dụ:

- Xóa HTTP starter có thể chặn HTTP nhưng **Stream binding vẫn chạy**.
- Tắt Stream autodetect không làm function biến mất khỏi **web endpoint**.
- `ineligible-definitions` không chặn một `@RestController` tự inject service nội bộ.
- Đổi destination broker không tự đổi function name hay HTTP path.
- Đổi tên bean có thể làm composition/binding cũ hỏng, nhưng không phải security policy đầy đủ.

## 20. Test catalog: function internal không phải candidate

Test dưới đây dùng application cấu hình rõ ràng, không phụ thuộc việc source được auto scan.

### 20.1. Cấu hình minh họa cho test

~~~java
package demo.exposure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExposureTestApplication {

    @Bean
    public Function<String, String> publicNormalize() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> internalRebuildIndex() {
        return key -> "REBUILT-" + key;
    }
}
~~~

`internalRebuildIndex` trong test chỉ trả chuỗi; **không** thao tác cơ sở dữ liệu thật. Mục đích là xác minh catalog bị filter mà không tạo tác dụng phụ.

### 20.2. @SpringBootTest xác nhận exclusion

~~~java
package demo.exposure;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = ExposureTestApplication.class,
    properties = {
        "spring.cloud.function.ineligible-definitions=internalRebuildIndex",
        "spring.cloud.function.single-function-fallback-enabled=false",
        "spring.cloud.function.scan.enabled=false",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class CatalogExposureTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void internalBeanMayExistButMustNotBeInCatalog() {
        assertThat(context.containsBean("internalRebuildIndex"))
            .isTrue();

        assertThat(catalog.getNames(null))
            .contains("publicNormalize")
            .doesNotContain("internalRebuildIndex");

        assertThat(catalog.lookup("internalRebuildIndex"))
            .isNull();
    }

    @Test
    void publicFunctionStillWorks() {
        Function<String, String> fn =
            catalog.lookup(Function.class, "publicNormalize");

        assertThat(fn).isNotNull();
        assertThat(fn.apply("  order-10 "))
            .isEqualTo("ORDER-10");
    }
}
~~~

Test này có ba vai trò:

1. Chứng minh bean internal có thể còn trong Spring context.
2. Chứng minh catalog **không công bố** tên internal khi filter được áp dụng.
3. Chứng minh function public không bị loại nhầm và còn chạy đúng.

Cần dependency Spring Boot Test, Spring Cloud Function, JUnit 5 và AssertJ phù hợp. Không nên suy rộng test context này sang production khi dependency, profile, starter hoặc binding khác nhau.

### 20.3. Vì sao phải tắt single-function fallback trong test?

Sau khi filter `internalRebuildIndex`, catalog có thể chỉ còn một function do ứng dụng khai báo. Nếu fallback còn bật, `lookup("internalRebuildIndex")` có thể trả **function duy nhất còn lại** dù tên internal đã bị loại, làm test báo sai kết quả.

Property `single-function-fallback-enabled=false` cho phép kiểm tra theo tên chính xác.

### 20.4. Kiểm tra toàn bộ inventory thay vì một denylist

Một test nghiêm hơn có thể so tập tên catalog với tập các function được cho phép:

~~~java
Set<String> names = catalog.getNames(null);

assertThat(names)
    .contains("publicNormalize")
    .doesNotContain(
        "internalRebuildIndex",
        "debugEcho",
        "internalStatusSnapshot"
    );
~~~

Nếu test môi trường có router/framework functions tích hợp, tập catalog có thể thêm tên hỗ trợ; cần phân biệt các tên framework với functional beans do ứng dụng sở hữu trước khi áp dụng `containsExactlyInAnyOrder`. Không viết test quá giòn gây false alarm mỗi lần nâng cấp thư viện.

## 21. Test HTTP, Stream và serverless: kiểm tra *không gọi được* quan trọng như *gọi được*

### 21.1. HTTP negative test

Với dự án có `spring-cloud-function-web`, Spring MVC Test hoặc integration test HTTP thật, kiểm tra:

- `/publicNormalize` với caller đủ quyền hoạt động.
- `/internalRebuildIndex` với caller không có quyền không gọi được.
- Root path `/`, URL lạ, composition path và các HTTP methods không mở đường gián tiếp tới target internal.
- Routing headers không thể ép adapter gọi internal function.
- Nếu function thật có side effect, dùng spy/fake service để khẳng định **không có invocation**, không chỉ kiểm tra HTTP status.

Có thể viết mục tiêu test ở dạng hành vi:

~~~text
GIVEN catalog contains publicNormalize
AND internalRebuildIndex must not be callable from HTTP

WHEN unauthenticated user POSTs /internalRebuildIndex
THEN request is rejected
AND maintenanceService.rebuild() is never called

WHEN authorized user POSTs /publicNormalize
THEN only publicNormalize is invoked
~~~

Không gắn cứng một mã lỗi HTTP cho mọi cấu hình: 401, 403 hoặc 404 có thể đều phù hợp tùy security và route policy. Quan trọng là **không gọi được target**.

### 21.2. Stream negative test

Nếu ứng dụng dùng Spring Cloud Stream, kiểm tra danh sách **bindings thực tế** khi khởi động, không chỉ `catalog.getNames(null)`:

~~~text
Expected binding:
  publicNormalize-in-0
  publicNormalize-out-0

Unexpected:
  internalRebuildIndex-in-0
  internalRebuildIndex-out-0
  internalStatusSnapshot-out-0
~~~

Test có thể dùng binder test hỗ trợ của phiên bản đang dùng hoặc broker integration. Đối với function có đầu ra hoặc supplier, test cần bảo đảm **không có message gửi tới destination nội bộ ngoài ý muốn**.

Nếu app sử dụng `StreamBridge` và explicit bindings không gắn function, test phải tách các binding đó khỏi tập bindings theo functional model.

### 21.3. Serverless negative test

Tạo invocation giống sự kiện thật và xác nhận:

- Handler/definition chọn function công khai dự kiến.
- Event không thể sửa routing target sang function nội bộ nếu caller không được phép.
- Không có side effect của internal service.
- Timeout/retry của platform không làm target internal chạy lại.
- Quyền IAM/authorization được cấu hình ở deployment thực tế.

Một unit test catalog không thể thay thế test runtime/handler hoặc chính sách IAM.

## 22. Actuator và logging: quan sát nhưng không tạo thêm rủi ro

Tùy dependency và cấu hình, Spring Cloud Function có thể cung cấp endpoint Actuator hiển thị danh sách function.

Ví dụ cấu hình chỉ dành cho môi trường chẩn đoán được bảo vệ:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

Nếu endpoint được cung cấp và export:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

Nó giúp quan sát tên/kiểu function mà catalog biết. Nhưng:

- Actuator không tự có mặt chỉ vì đã thêm `FunctionCatalog`.
- URL còn phụ thuộc management port/base path và security.
- Endpoint không có phản hồi **không chứng minh** catalog rỗng.
- Không expose endpoint quản trị ra Internet chỉ để chẩn đoán.
- Thông tin catalog có thể tiết lộ tên tác vụ nội bộ; hạn chế người có quyền xem.

### 22.1. Logging có mục tiêu

~~~properties
logging.level.org.springframework.cloud.function=DEBUG
logging.level.org.springframework.cloud.stream=DEBUG
~~~

Bật trong thời gian có kiểm soát và tránh ghi toàn bộ payload hoặc secret. Đối với sự cố công bố không mong muốn, ưu tiên log các mốc **registration**, **function selection**, **HTTP mapping**, **binding creation** và **actual invocation**, kèm correlation ID đã được phép sử dụng.

### 22.2. Quan sát các số liệu phù hợp

| Tầng | Metric / log hữu ích |
| --- | --- |
| Spring context | Bean names, type, source configuration |
| Catalog | Function name inventory, size, lookup target |
| HTTP | Route mapping, method, status, authorized principal, target |
| Stream | Binding names, destinations, consumer group, publisher count |
| Serverless | Handler, selected function, invocation ID, errors |
| Business | Số lần side effect của function nhạy cảm, audit ID |
| Security | Denied attempts, unusual routing targets, IAM access |

Không dùng việc không thấy log `onNext` làm bằng chứng function không tồn tại: trong một reactive function, publisher cold có thể chưa được subscribe.

## 23. Sơ đồ quyết định khắc phục

~~~mermaid
flowchart TD
    START["Phát hiện function không mong muốn"] --> CTX{"Có trong ApplicationContext?"}
    CTX -->|Không| OTHER["Kiểm tra router/alias\nhoặc sai process/artifact"]
    CTX -->|Có| NEED{"Bean đó có cần tồn tại?"}
    NEED -->|Không| REMOVE["Bỏ registration hoặc tắt condition/profile"]
    NEED -->|Có| CAT{"Có trong FunctionCatalog?"}
    CAT -->|Có, nhưng không cần catalog| FILTER["ineligible-definitions\nhoặc đổi thành service"]
    CAT -->|Không| DIRECT["Kiểm tra direct caller/adapter khác"]
    CAT -->|Có, cần catalog nội bộ| EXPOSE{"Bị xuất ra ngoài qua đâu?"}
    EXPOSE -->|HTTP| WEB["Allowlist + security + negative route tests"]
    EXPOSE -->|Stream| BINDER["definition + autodetect + binding policy"]
    EXPOSE -->|Serverless| RUNTIME["handler + routing + IAM"]
    EXPOSE -->|Router| ROUTER["Target allowlist + input trust"]
    REMOVE --> VERIFY["Xác minh lại mọi đường vào"]
    FILTER --> VERIFY
    DIRECT --> VERIFY
    WEB --> VERIFY
    BINDER --> VERIFY
    RUNTIME --> VERIFY
    ROUTER --> VERIFY
    OTHER --> VERIFY
~~~

### 23.1. Checklist trước khi sửa

1. Hàm được phát hiện ở tầng nào: context, catalog, HTTP, Stream hay serverless?
2. Có bằng chứng đã thực thi hay mới chỉ tồn tại trong catalog?
3. Bean đó xuất hiện do `@Bean`, `@Component`, SCF function scan hay dependency mới?
4. Có profile, condition, configuration import hoặc environment override liên quan không?
5. Có `ineligible-definitions` hiệu lực không và danh sách đang chứa tên nào?
6. `spring.cloud.function.definition` đang chọn một function, composition hay nhiều function độc lập?
7. Stream có `function.autodetect` đang chọn bean duy nhất không?
8. Router có chấp nhận target từ header hoặc payload không tin cậy không?
9. Web adapter có map root, URL lạ hoặc composition ngoài dự kiến không?
10. Một thay đổi filter có khiến pipeline hợp lệ khác bị hỏng không?
11. Có security/IAM/ACL phù hợp ở mọi đường gọi không?
12. Sau fix, negative tests có xác nhận không thể gọi target không?

## 24. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Đặt tên bean là `internalFoo` thì SCF không công bố.” | Tên không mang nghĩa security; type/registration/adapter mới quyết định. |
| “Có trong `FunctionCatalog` tức chắc chắn có HTTP endpoint công khai.” | Còn cần web adapter, mapping và network/security. |
| “Không có HTTP endpoint tức function không thể được gọi.” | Broker, router, serverless hoặc direct Java caller vẫn có thể gọi. |
| “`spring.cloud.function.definition` xóa function khác khỏi catalog.” | Property chủ yếu chọn/compose/export theo adapter, không xóa bean. |
| “Chỉ cần `ineligible-definitions` là bảo mật tuyệt đối.” | Bean có thể còn được inject trực tiếp; authorization vẫn cần thiết. |
| “`scan.enabled=false` xóa mọi `@Bean Function`.” | Nó chỉ tắt SCF function component scan, không tắt Spring component scan thông thường. |
| “`function.autodetect=false` tắt HTTP/web adapter.” | Đây là property của Spring Cloud Stream auto-binding. |
| “Function duy nhất sẽ luôn nằm yên nếu không đặt definition.” | Stream có thể auto-bind functional bean duy nhất. |
| “Supplier không bao giờ tự chạy.” | Poller của adapter có thể kích hoạt supplier. |
| “Dấu `;` và `|` trong definition giống nhau.” | `;` chọn nhiều function độc lập; `|` là composition. |
| “Single-function fallback chỉ ảnh hưởng tên rỗng.” | Tên không tồn tại cũng có thể resolve thành hàm duy nhất. |
| “Bảo vệ `/internalFoo` đủ nếu web có root/composition routing.” | Có thể còn đường vào khác; phải test target cuối cùng. |
| “Header expression bị giới hạn nghĩa không cần phân quyền target.” | Expression context hạn chế không thay authorization. |
| “Actuator liệt kê function là bằng chứng bị lộ ra Internet.” | Phải kiểm tra security, network và endpoint thực sự. |
| “Tắt web starter sẽ ngừng broker consumer.” | Hai adapter có vòng đời và cấu hình khác nhau. |
| “Cứ thấy `Flux` không log là function không chạy.” | Nguồn cold có thể chưa subscribe; cần kiểm tra subscription. |

## 25. Câu hỏi tự đánh giá

1. Function bean xuất hiện trong `ApplicationContext` khác gì xuất hiện trong `FunctionCatalog`?
2. Một helper `@Bean Function<String,String>` có thể bị catalog nhận diện dù tên có chữ `internal` không?
3. Khi nào nên refactor helper thành `@Service` thay vì functional bean?
4. Component scan của Spring và function scan của SCF khác nhau ra sao?
5. Property nào có thể tắt SCF function component scan, và property đó có xóa bean `@Bean` thông thường không?
6. `spring.cloud.function.ineligible-definitions` loại object khỏi context hay chỉ loại ứng viên catalog?
7. Vì sao một library bean mới cũng có thể trở thành functional candidate?
8. Vì sao `catalog.lookup("badName")` có thể nguy hiểm khi chỉ có một functional bean?
9. Property nào tắt single-function fallback?
10. Khi thêm `spring-cloud-function-web`, những route nào phải được negative test?
11. `spring.cloud.function.definition=foo;bar` khác `foo|bar` ở tầng web và Stream thế nào?
12. Vì sao chỉ cấu hình `definition=publicNormalize` không được coi là authorization đầy đủ?
13. Stream có thể auto-bind một `Supplier` duy nhất không? Làm cách nào ngăn auto-binding này?
14. Vì sao `spring.cloud.stream.function.autodetect=false` không làm catalog biến mất?
15. Có gì khác giữa tên function, Stream binding name và destination?
16. Nếu router lấy target từ header, cần thực hiện allowlist và authorization ở đâu?
17. Vì sao reactive function routing không hoàn toàn tương đương routing từng message của imperative function?
18. Serverless handler và business function name khác nhau như thế nào?
19. Trong test, làm sao chứng minh bean internal còn trong context nhưng không còn trong catalog?
20. Vì sao negative integration test nên xác minh **không có side effect**, không chỉ xem HTTP status?
21. Nếu production có dấu hiệu function quản trị bị gọi, cần xử lý theo thứ tự nào để giảm rủi ro?
22. Những quan sát nào giúp phân biệt “đăng ký ngoài ý muốn” với “đã thực sự công bố/đã được gọi”?

## 26. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — các functional beans trong `ApplicationContext`, `FunctionCatalog`, single-function fallback, `ineligible-definitions`, function scanning, composition và routing.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — tự động export HTTP, function filtering, root mapping và method-specific routes.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionalSpringApplication`, `FunctionRegistration` và metadata kiểu.
- [Spring Cloud Function — AWS Adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html) — handler và chọn business function trên Lambda.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — chọn function, auto-binding, supplier polling và nhiều function độc lập.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html) — `@Configuration`, `@Component` và đăng ký beans.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — cơ chế phân quyền HTTP theo request và policy mặc định.

Các ví dụ dùng Java 17+ và các API phổ biến của Spring Cloud Function/Spring Cloud Stream. Chi tiết auto-configuration, web mapping, routing, starter và method-specific properties có thể khác giữa các phiên bản. Cần kiểm tra BOM/dependency của ứng dụng thật và chạy integration tests với đúng adapter được deploy.

**Ghi nhớ:** Một `Function`/`Supplier`/`Consumer` vô tình trở thành Spring bean có thể được `FunctionCatalog` nhận diện; khi thêm web adapter, binder hoặc serverless runtime, khả năng **công bố hoặc tự gọi** phụ thuộc ranh giới adapter. Hãy kiểm tra **ApplicationContext → FunctionCatalog → function definition/routing → HTTP/Stream/serverless → invocation thực tế**. Nếu không cần là functional bean, refactor thành service; nếu chỉ không muốn vào catalog, xem `ineligible-definitions`; nếu bị gọi ngoài ý muốn, kiểm soát selection, auto-binding và authorization ở đúng tầng. Luôn kiểm thử cả đường được phép và đường **không được phép**, vì lọc tên function không thay thế bảo mật.
