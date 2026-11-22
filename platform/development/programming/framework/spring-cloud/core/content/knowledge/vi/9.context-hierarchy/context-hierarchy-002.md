# Xây dựng parent, child và sibling bằng `SpringApplicationBuilder`

Spring có thể chạy nhiều `ApplicationContext` trong cùng một tiến trình và tổ chức chúng thành một **cây phân cấp context**. Context cha (*parent*) chứa những bean dùng chung; context con (*child*) chứa thành phần chuyên biệt và có thể truy cập bean của cha. Hai context có cùng parent được gọi là **sibling**: chúng có thể dùng chung hạ tầng ở parent nhưng không truy cập trực tiếp bean riêng của nhau.

Spring Boot cung cấp `SpringApplicationBuilder` để tạo cấu trúc này bằng API fluent. Trong module **SPRING_CLOUD_CORE**, mô hình hữu ích khi cần hiểu context hierarchy của Spring, cách Spring Cloud bootstrap và chia sẻ cấu hình, cũng như giới hạn giữa việc chia sẻ bean trong một JVM với giao tiếp giữa các service phân tán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích quan hệ parent, child và sibling giữa các `ApplicationContext`.
2. Dùng `SpringApplicationBuilder` để tạo context cha-con và các context cùng cấp.
3. Dự đoán bean nào có thể được tra cứu từ từng context và xử lý bean trùng tên.
4. Thiết kế context dùng chung cho hạ tầng và context riêng cho từng ứng dụng con.
5. Cấu hình web application type, profile, property và lifecycle phù hợp với từng context.
6. Phân biệt context hierarchy với Spring Cloud bootstrap context và với ranh giới microservice.
7. Kiểm thử việc tạo context, bean visibility, Environment và đóng context đúng cách.

## 2. Vì sao cần context hierarchy?

Một `ApplicationContext` là container chứa bean definitions, bean instances, event listeners, resource loading và các dịch vụ của Spring. Trong ứng dụng đơn giản, một context thường đủ. Khi một tiến trình cần nhiều vùng cấu hình hoặc nhiều ứng dụng con, việc chia thành parent và child có thể giúp tổ chức bean theo phạm vi.

Ví dụ, một tiến trình nội bộ có hai ứng dụng web:

- API context cung cấp endpoint cho client.
- Admin context cung cấp giao diện hoặc API vận hành.
- Parent context giữ các bean hạ tầng thực sự dùng chung, ví dụ `Clock`, cấu hình nền hoặc một dịch vụ không phụ thuộc web.

~~~mermaid
flowchart TD
    P[Parent ApplicationContext<br/>Shared infrastructure]
    P --> A[API child context]
    P --> B[Admin child context]
    A --> A1[REST controllers]
    A --> A2[API services]
    B --> B1[Admin controllers]
    B --> B2[Admin services]
~~~

Hai child context cùng tham chiếu một parent. Bean trong parent có thể được tra cứu từ child; bean riêng trong API không tự xuất hiện trong Admin context.

**Lưu ý kiến trúc:** parent/child/sibling là cấu trúc container trong **cùng JVM**. Chúng không tạo ra network boundary, process isolation, khả năng scale độc lập hay fault isolation như các microservice triển khai ở tiến trình riêng.

## 3. Ba quan hệ cần phân biệt

### 3.1. Parent và child

Một context có thể có một parent. Child kế thừa khả năng tra cứu bean từ parent theo hierarchy.

- Parent giữ bean dùng chung hoặc cấu hình nền.
- Child giữ bean dành riêng cho ứng dụng con.
- Child có thể truy cập bean của chính nó và bean ở parent.
- Parent không thể tra cứu bean chỉ tồn tại trong child.
- Parent không thể inject dependency chỉ được khai báo ở child.

~~~mermaid
flowchart TD
    P[Parent context]
    C[Child context]
    P --> C
    C --> C1[Tra cứu bean của child]
    C --> C2[Tra cứu bean của parent nếu cần]
    P --> P1[Chỉ tra cứu bean của parent]
~~~

Ví dụ: `InventoryDirectory` được khai báo ở parent. Một controller ở child có thể inject `InventoryDirectory`. Nhưng nếu một bean parent cố inject `ApiController` chỉ được khai báo trong child, việc khởi tạo parent sẽ không tìm thấy bean đó.

### 3.2. Sibling

Hai context là sibling nếu chúng có **cùng parent**:

~~~mermaid
flowchart TD
    P[Shared parent]
    P --> A[API context]
    P --> B[Admin context]
~~~

Sibling không phải parent hoặc child của nhau. Vì vậy:

- API child nhìn thấy bean trong API và parent.
- Admin child nhìn thấy bean trong Admin và parent.
- API child không nhìn thấy bean chỉ có trong Admin.
- Admin child không nhìn thấy bean chỉ có trong API.

Nếu API và Admin cần chia sẻ một dịch vụ, đặt dịch vụ đó ở parent hoặc đưa nó vào một module cấu hình chung phù hợp. Không dựa vào việc hai sibling cùng chạy trong một JVM để giả định chúng dùng chung bean.

### 3.3. Root context

Context không có parent là root context. Root có thể chứa các bean nền tảng được những child cùng sử dụng. Một ứng dụng chỉ có một context cũng là một trường hợp không có hierarchy.

| Quan hệ | Có parent? | Tra cứu bean từ đâu? |
| --- | --- | --- |
| Root | Không | Bean thuộc chính context |
| Child | Có một parent | Bean child trước, sau đó theo hierarchy lên parent |
| Sibling A | Cùng parent với sibling B | Bean của A và parent; không thấy bean riêng của B |
| Sibling B | Cùng parent với sibling A | Bean của B và parent; không thấy bean riêng của A |

## 4. Tạo parent và child bằng SpringApplicationBuilder

### 4.1. Ví dụ tối thiểu

Giả sử có hai lớp cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;

@Configuration(proxyBeanMethods = false)
public class SharedParentConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
~~~

Child:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
}
~~~

Tạo hierarchy:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class OrdersLauncher {

    public static void main(String[] args) {
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE)
                .child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET)
                .run(args);
    }
}
~~~

Các bước:

1. Constructor nhận source của context cha.
2. `.web(WebApplicationType.NONE)` đặt parent thành context không chạy web server.
3. `.child(OrdersApiApplication.class)` tạo builder cho child.
4. `.web(WebApplicationType.SERVLET)` đặt child là ứng dụng Servlet.
5. `.run(args)` khởi chạy parent trước nếu parent chưa chạy, rồi khởi chạy child và trả về context của ứng dụng hiện tại.

Đây là một ví dụ minh họa. Trong dự án thật, cần giới hạn component scan của child để không vô tình quét lại cấu hình dùng chung hoặc các thành phần thuộc child khác.

### 4.2. Parent có thể được khai báo bằng `parent(...)`

Một cách viết khác:

~~~java
new SpringApplicationBuilder()
        .parent(SharedParentConfiguration.class)
        .child(OrdersApiApplication.class)
        .run(args);
~~~

`parent(...)` thêm một ứng dụng cha; `child(...)` tạo ứng dụng con. Cả hai đều trả về builder để tiếp tục cấu hình.

Nếu chỉ có một ứng dụng Boot độc lập, không cần tạo hierarchy chỉ để dùng fluent API. `SpringApplication.run(...)` hoặc một `SpringApplicationBuilder` đơn giản thường dễ hiểu hơn.

### 4.3. `run(...)` khởi chạy parent trước

Theo API của `SpringApplicationBuilder`, `run(args)` tạo context hiện tại và context cha nếu đã cấu hình. Parent được chạy trước với cùng command-line arguments nếu chưa được khởi động.

Điều này quan trọng khi child phụ thuộc bean của parent. Nếu parent không thể khởi tạo, child cũng không thể hoàn thành quá trình startup theo hierarchy đó.

Có thể giữ builder để truy cập context sau khi chạy:

~~~java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder childBuilder =
        parentBuilder.child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET);

ConfigurableApplicationContext childContext = childBuilder.run(args);
ConfigurableApplicationContext parentContext = parentBuilder.context();
~~~

`context()` trả về context hiện tại của builder nếu đã được tạo. Khi cần thao tác lifecycle hoặc kiểm thử, giữ reference đến builder/context thay vì giả định `run()` trả về mọi context trong hierarchy.

## 5. Tạo sibling context

### 5.1. Sử dụng `sibling(...)`

Giả sử một tiến trình cần API và Admin cùng dùng `SharedParentConfiguration`:

~~~java
SpringApplicationBuilder apiBuilder =
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE)
                .child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET);

SpringApplicationBuilder adminBuilder =
        apiBuilder.sibling(
                new Class<?>[]{AdminApplication.class},
                args
        ).web(WebApplicationType.SERVLET);

ConfigurableApplicationContext adminContext = adminBuilder.run(args);
ConfigurableApplicationContext apiContext = apiBuilder.context();
~~~

`AdminApplication` là cấu hình ứng dụng thứ hai. `sibling(...)` tạo một ứng dụng mới có cùng parent với ứng dụng hiện tại.

**Chi tiết lifecycle của API:** gọi `sibling(...)` có side effect khởi chạy ứng dụng hiện tại và parent nếu chúng chưa chạy. Overload nhận `Class<?>[]` cùng `String... args` cho phép truyền arguments khi khởi chạy ứng dụng hiện tại và parent. Sau đó gọi `run(args)` trên sibling builder để chạy ứng dụng sibling.

Điều này khác với việc gọi `.child(AdminApplication.class)` trên API builder: thao tác đó sẽ tạo Admin thành child của API, không phải sibling của API.

### 5.2. Sibling có thể có cấu hình riêng

API và Admin có thể dùng các source riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class ApiConfiguration {
    // Bean chỉ dành cho API.
}

@Configuration(proxyBeanMethods = false)
class AdminConfiguration {
    // Bean chỉ dành cho Admin.
}
~~~

Khi cả hai là sibling, bean của `ApiConfiguration` không được tự động nhìn thấy từ `AdminConfiguration`, và ngược lại. Những bean thật sự dùng chung nên được đặt trong parent.

### 5.3. Khi nào dùng sibling?

| Nhu cầu | Cách tổ chức |
| --- | --- |
| Một ứng dụng web dùng hạ tầng chung | Root + một child |
| API và Admin cần dùng chung bean hạ tầng | Một parent + hai sibling |
| Một child cần thêm cấu hình con chuyên biệt | Parent → Child → Grandchild |
| Hai ứng dụng không cần chia sẻ bean | Hai context độc lập hoặc hai tiến trình, tùy mục tiêu |
| Muốn scale hoặc deploy độc lập | Tách tiến trình/service; context hierarchy không cung cấp khả năng này |

## 6. Quy tắc tra cứu bean trong hierarchy

### 6.1. Child có thể dùng bean của parent

Ví dụ parent khai báo một dịch vụ:

~~~java
public class SharedCatalog {
    public String source() {
        return "shared-parent";
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class SharedParentConfiguration {
    @Bean
    SharedCatalog sharedCatalog() {
        return new SharedCatalog();
    }
}
~~~

Child có thể inject:

~~~java
@Component
class ApiCatalogService {
    private final SharedCatalog catalog;

    ApiCatalogService(SharedCatalog catalog) {
        this.catalog = catalog;
    }

    String source() {
        return catalog.source();
    }
}
~~~

Khi Spring tạo `ApiCatalogService` trong child, việc tìm dependency có thể đi lên parent nếu child không có bean phù hợp tại chỗ.

### 6.2. Parent không thể phụ thuộc bean của child

Ví dụ sai về kiến trúc:

~~~java
@Configuration(proxyBeanMethods = false)
class SharedParentConfiguration {
    @Bean
    SharedCoordinator coordinator(ApiController controller) {
        return new SharedCoordinator(controller);
    }
}
~~~

Nếu `ApiController` chỉ được khai báo trong child, parent không thể tìm thấy nó. Parent được khởi tạo trước child và không thể phụ thuộc vào một bean chỉ tồn tại ở child.

Cách sửa là đảo chiều trách nhiệm: parent cung cấp một abstraction dùng chung; child inject abstraction đó và điều phối hành vi riêng.

### 6.3. Bean cùng tên trong child và parent

Nếu parent và child cùng có bean tên `clock`, tra cứu qua child sẽ ưu tiên bean trong child. Bean ở parent vẫn tồn tại trong context cha nhưng có thể bị bean con che khuất khi tra cứu theo tên từ child.

Điều này có thể dẫn đến nhầm lẫn khi inject theo kiểu, nhất là khi hai bean cùng kiểu:

- Dùng `@Qualifier` để chọn rõ bean.
- Dùng `@Primary` trong phạm vi phù hợp nếu có một ứng viên mặc định.
- Tránh tạo bean cùng tên/kiểu ở nhiều cấp nếu không cần override.
- Kiểm tra context đang sở hữu bean thay vì chỉ xem tên bean.

`BeanFactory` hierarchy không hợp nhất mọi bean thành một registry duy nhất. Mỗi context có bean factory riêng và việc tra cứu đi qua quan hệ parent.

## 7. Phạm vi singleton và trạng thái dùng chung

Một bean singleton trong parent là một instance do parent quản lý. Nhiều child có thể tra cứu và cùng sử dụng chính instance đó.

Điều này hữu ích cho các dịch vụ dùng chung nhưng cũng tạo ra ràng buộc:

- Bean chia sẻ phải an toàn khi nhiều child truy cập đồng thời.
- Trạng thái mutable trong parent có thể được nhiều child cùng thay đổi.
- Không đặt request-scoped hoặc servlet-specific bean trong parent dùng chung cho nhiều web child.
- Cần xem xét vòng đời bean và resource đóng/mở khi context parent kết thúc.
- Một singleton ở child khác là instance khác, kể cả khi hai bean có cùng class.

Ví dụ, `Clock` hoặc một client stateless có thể phù hợp làm bean dùng chung nếu cấu hình và lifecycle cho phép. Một component giữ dữ liệu phiên người dùng hoặc trạng thái request thường không phù hợp để đặt trong parent chung.

**Chia sẻ bean không đồng nghĩa chia sẻ dữ liệu một cách an toàn.** Nếu nhiều child gọi một bean mutable, cần thiết kế thread safety và ownership như với mọi đối tượng được chia sẻ đồng thời trong JVM.

## 8. Environment, profile và cấu hình giữa các context

### 8.1. Environment trong hierarchy

Spring Boot `SpringApplicationBuilder` truyền/copy các thiết lập mặc định và Environment từ parent xuống child theo quy tắc của builder. Tài liệu Spring Boot cũng lưu ý hierarchy được xây dựng theo cách mặc định dùng cùng Environment cho parent và child trong những trường hợp được mô tả. Vì vậy, không nên xem parent/child là hai môi trường cấu hình hoàn toàn độc lập.

Nếu ứng dụng cần cấu hình riêng cho từng child, phải xác định rõ cách tạo/cung cấp `ConfigurableEnvironment` và kiểm thử hành vi trên phiên bản Spring Boot đang dùng. Đừng giả định rằng chỉ vì hai context có bean factory riêng thì profile hoặc property source cũng tự động độc lập.

### 8.2. Thiết lập profile bằng builder

Có thể dùng `.profiles(...)`:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
        .profiles("cloud", "prod")
        .child(OrdersApiApplication.class)
        .run(args);
~~~

Theo API builder, profile được thêm cho ứng dụng hiện tại và các context parent/child liên quan. Khi dùng hierarchy, cần xác nhận active profiles ở từng context bằng `Environment.getActiveProfiles()`.

Không dùng profile để giả lập sibling isolation. Profile quyết định cấu hình/bean nào được kích hoạt; nó không tạo ranh giới bean giữa hai context.

### 8.3. Default properties

`SpringApplicationBuilder.properties(...)` thiết lập default properties cho Environment:

~~~java
new SpringApplicationBuilder(OrdersApiApplication.class)
        .properties(
                "clients.inventory.read-timeout=700ms",
                "feature.catalog.enabled=true"
        )
        .run(args);
~~~

Default properties thường có độ ưu tiên thấp hơn những nguồn cấu hình bên ngoài như command-line arguments, system properties và Config Data. Dùng chúng làm giá trị mặc định cho ứng dụng; không xem chúng như một cơ chế override mạnh nhất.

### 8.4. Cấu hình riêng cho child

Khi có nhiều child cần profile/property khác nhau, nên thiết kế rõ cách cung cấp Environment cho từng builder. API `environment(ConfigurableEnvironment)` cho phép cung cấp Environment cho ứng dụng đang xây dựng. Cần lưu ý nếu cùng một object Environment được truyền cho nhiều context thì các thay đổi PropertySource có thể ảnh hưởng đến tất cả context dùng chung object đó.

Ví dụ khởi tạo Environment riêng:

~~~java
StandardEnvironment apiEnvironment = new StandardEnvironment();
apiEnvironment.setActiveProfiles("api");

SpringApplicationBuilder apiBuilder =
        new SpringApplicationBuilder(ApiApplication.class)
                .environment(apiEnvironment);
~~~

Ví dụ này minh họa việc cung cấp Environment cho một ứng dụng độc lập. Khi kết hợp với parent, hãy kiểm tra cách builder merge/truyền Environment theo phiên bản; không dùng đoạn mã này như cam kết rằng chỉ cần tạo object mới là tự động tách mọi cấu hình trong hierarchy.

## 9. Web application type và vị trí của web components

Spring Boot hỗ trợ các loại ứng dụng:

- `WebApplicationType.NONE`: không tạo web server.
- `WebApplicationType.SERVLET`: ứng dụng web dựa trên Servlet.
- `WebApplicationType.REACTIVE`: ứng dụng reactive dựa trên reactive web stack.

Một giới hạn quan trọng khi tạo context hierarchy là **web components nên nằm trong child context**. Parent thường nên là context không web, chứa cấu hình và bean dùng chung.

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(OrdersApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

Nếu đặt web server hoặc controller vào parent, có thể gặp xung đột khi child cũng tạo web infrastructure. Tách web-specific bean vào child giúp mỗi ứng dụng con có phạm vi rõ ràng.

### 9.1. Servlet và Reactive không nên bị trộn tùy tiện

Nếu một tiến trình có API Servlet và một ứng dụng reactive riêng, mỗi child có thể được cấu hình với web type phù hợp. Tuy nhiên, cần kiểm tra classpath, auto-configuration, port, lifecycle và khả năng hỗ trợ của từng integration. Không phải mọi starter đều tương thích với mọi loại web context.

## 10. Component scan và auto-configuration trong hierarchy

### 10.1. Tránh scan quá rộng

`@SpringBootApplication` bao gồm component scanning. Nếu parent và child đều scan một package gốc rộng, cùng một cấu hình hoặc component có thể được đăng ký ở nhiều context.

Ví dụ, parent scan `com.example` và child cũng scan `com.example.api` có thể khiến bean thuộc API xuất hiện trong parent nếu cấu hình scan không giới hạn đúng. Điều đó phá vỡ ý định đặt web bean ở child.

Một cách tổ chức package:

~~~text
com.example
  shared
    SharedParentConfiguration.java
    SharedCatalog.java
  api
    OrdersApiApplication.java
    ApiController.java
  admin
    AdminApplication.java
    AdminController.java
~~~

Parent chỉ import package `shared`; API child chỉ scan `api`; Admin child chỉ scan `admin`. Có thể dùng `@ComponentScan(basePackageClasses = ...)` hoặc `@Import` để xác định rõ cấu hình.

### 10.2. Auto-configuration có thể chạy ở nhiều context

Nếu mỗi context được khởi tạo bằng một `SpringApplication` có auto-configuration, các auto-configuration phù hợp có thể được xét trong từng context. Điều này có thể tạo các bean infrastructure riêng ở parent và child.

Ví dụ, hai child đều có web auto-configuration thì mỗi child có thể khởi tạo web infrastructure riêng. Đó có thể là chủ ý nếu hai ứng dụng web độc lập, nhưng cần kiểm tra port và tài nguyên.

Không nên giả định một auto-configuration chỉ chạy một lần trên toàn JVM. Nó được áp dụng trong phạm vi context đang được khởi tạo.

### 10.3. Tránh trùng lặp bean dùng chung

Nếu bean `Clock`, `ObjectMapper` hoặc client dùng chung đã nằm trong parent, không cần khai báo lại trong mọi child trừ khi child thực sự cần cấu hình khác. Nếu child khai báo lại, cần quyết định rõ bean con có override bean cha hay chỉ tạo thêm một ứng viên.

## 11. Application events và lifecycle

### 11.1. Event trong context hierarchy

Một event được publish trong child có thể được chuyển tiếp lên parent theo cơ chế event propagation của Spring context. Event được publish ở parent không tự động được broadcast xuống tất cả child.

Vì vậy, nếu một child publish domain event, listener trong parent có thể nhận được nếu listener được đăng ký phù hợp. Nhưng không nên dựa vào event từ parent để thông báo tự động tới sibling context khác. Muốn sibling trao đổi, hãy dùng một abstraction chung, event bus nội bộ được thiết kế rõ ràng hoặc messaging phù hợp.

### 11.2. Thứ tự khởi tạo và đóng context

`SpringApplicationBuilder.run(...)` khởi chạy parent trước khi khởi chạy child. Nếu parent chưa sẵn sàng, child không thể dựa vào bean của parent.

Khi ứng dụng dừng, cần bảo đảm các child không còn sử dụng tài nguyên trong parent trước khi parent bị đóng. Với context do code kiểm thử hoặc launcher tự quản lý, hãy giữ reference và đóng theo thứ tự phù hợp:

1. Dừng tiếp nhận công việc ở child.
2. Đóng các child context.
3. Đóng parent sau cùng.

Nếu sử dụng shutdown hook của builder, hãy hiểu context nào được đăng ký hook và ai sở hữu lifecycle. Không đóng parent trong khi child vẫn đang xử lý request hoặc dùng shared resource.

## 12. Tích hợp với Spring Cloud

### 12.1. Context hierarchy không phải bootstrap context

Spring Cloud bootstrap context là một cơ chế đặc thù của Spring Cloud legacy để nạp cấu hình trước main application context. Context này có thể là parent của main context trong mô hình bootstrap cũ.

`SpringApplicationBuilder` cũng có thể tạo parent/child hierarchy, nhưng mục đích chung hơn: tổ chức nhiều ứng dụng/context trong cùng tiến trình. Hai khái niệm có thể liên quan nhưng không đồng nhất.

Với Config Data import hiện đại, Config Client nạp nguồn từ xa trong quá trình chuẩn bị Environment; không cần tạo một hierarchy thủ công chỉ để lấy cấu hình.

### 12.2. Dùng chung discovery hoặc client bean

Nếu parent chứa một bean `DiscoveryClient` hoặc một client stateless dùng chung, child có thể tra cứu bean đó qua hierarchy nếu dependency và auto-configuration được đặt đúng. Tuy nhiên, không nên mặc định mọi discovery provider đều hỗ trợ hoặc nên được khởi tạo ở parent.

Hãy cân nhắc:

- Provider cần cấu hình riêng theo từng ứng dụng hay không.
- Registry client có phụ thuộc profile/application name của child không.
- Bean có giữ state hoặc metadata gắn với một service identity cụ thể không.
- Parent Environment có phù hợp cho tất cả child không.
- Việc đóng context parent có ảnh hưởng client đang được child sử dụng không.

Một service registry thường đại diện cho một ứng dụng/instance cụ thể. Nếu hai child cần đăng ký với tên service hoặc metadata khác nhau, có thể phù hợp hơn khi mỗi child có integration riêng thay vì chia sẻ một registration bean trong parent.

### 12.3. Không thay thế giao tiếp giữa microservice

Context hierarchy chỉ chia sẻ object trong một JVM. Nếu Orders và Inventory là hai service chạy ở các tiến trình/container khác nhau, chúng cần giao tiếp qua HTTP, messaging hoặc giao thức phân tán khác. Không thể dùng parent/child context để tra cứu bean trong tiến trình khác.

## 13. Kiểm thử context hierarchy

### 13.1. Kiểm tra bean visibility

Có thể khởi tạo một parent và child nhỏ bằng builder, sau đó xác nhận child nhìn thấy bean của parent:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ContextHierarchyTest {

    @Test
    void childCanResolveParentBean() {
        try (ConfigurableApplicationContext parent =
                     new SpringApplicationBuilder(SharedParentConfiguration.class)
                             .web(WebApplicationType.NONE)
                             .run();
             ConfigurableApplicationContext child =
                     new SpringApplicationBuilder(OrdersApiApplication.class)
                             .parent(parent)
                             .web(WebApplicationType.NONE)
                             .run()) {
            assertThat(child.getBean(SharedCatalog.class)).isNotNull();
            assertThat(child.getParent()).isSameAs(parent);
        }
    }
}
~~~

Ví dụ cần có `SharedCatalog` trong `SharedParentConfiguration` và dùng `OrdersApiApplication` đã khai báo ở phần trước làm source của child. Dùng `WebApplicationType.NONE` giúp test không mở web server.

Trong test thật, nên kiểm tra cả bean child và parent, tránh chỉ xác nhận child lookup thành công rồi kết luận toàn bộ hierarchy đúng.

### 13.2. Kiểm tra parent không thấy bean child

~~~java
assertThat(parent.context().containsBean("apiController")).isFalse();
assertThat(child.containsBean("apiController")).isTrue();
~~~

`containsBean` được gọi trên đúng context. Nếu tra cứu theo hierarchy, child có thể thấy parent; parent không tìm ngược xuống child.

### 13.3. Kiểm tra sibling isolation

Tạo hai sibling có bean riêng và cùng dùng một bean parent. Xác nhận:

- API child nhìn thấy shared bean.
- Admin child nhìn thấy shared bean.
- API child không thấy bean chỉ có ở Admin.
- Admin child không thấy bean chỉ có ở API.

Có thể dùng `SpringApplicationBuilder.sibling(...)` hoặc tạo từng child với cùng một parent context đã chạy bằng overload `parent(ConfigurableApplicationContext)`.

### 13.4. Kiểm thử profile và Environment

Kiểm tra `Environment.getActiveProfiles()` tại parent và child. Nếu dùng chung hoặc kế thừa Environment theo cấu hình builder, xác nhận profile được truyền đúng như mong đợi. Nếu có Environment riêng, kiểm tra cả property sources và thứ tự ưu tiên.

Không chỉ kiểm tra `builder.profiles(...)`; hãy xác minh profile thực tế trong context sau khi startup.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Child không inject được bean parent | Bean không nằm trong parent hoặc parent startup thất bại | Kiểm tra parent context, bean definition và lifecycle |
| Parent inject bean child thất bại | Thiết kế dependency ngược chiều hierarchy | Đưa abstraction dùng chung lên parent hoặc chuyển consumer xuống child |
| Sibling không thấy bean của nhau | Sibling không kế thừa lẫn nhau | Đặt bean dùng chung vào parent hoặc dùng giao tiếp tường minh |
| Bean xuất hiện hai lần | Component scan/auto-configuration chạy ở nhiều context | Giới hạn scan và xác định bean thuộc context nào |
| Child có bean cùng tên với parent | Bean child che khuất khi tra cứu qua child | Dùng qualifier, đổi tên hoặc bỏ khai báo trùng |
| Web server khởi tạo sai context | Web component nằm ở parent hoặc web type cấu hình sai | Đặt web infrastructure trong child, parent thường `NONE` |
| Gọi `sibling()` làm context hiện tại khởi động sớm | Đây là side effect được mô tả trong API | Dùng overload nhận args và hiểu thứ tự startup |
| Đóng parent làm child lỗi | Parent bị đóng khi child còn sử dụng shared bean | Dừng/đóng child trước parent |
| Hai child nhận cấu hình không như mong đợi | Environment/profile được truyền hoặc chia sẻ theo builder | Kiểm tra Environment thực tế của từng context |
| Tưởng hierarchy tạo hai microservice | Nhầm container boundary với process boundary | Dùng tiến trình/service riêng nếu cần scale/deploy/fault isolation |

## 15. Nguyên tắc thiết kế và khi nào không nên dùng hierarchy

Context hierarchy có ích khi một tiến trình thực sự cần chia sẻ hạ tầng và tách phạm vi bean. Nó cũng làm tăng độ phức tạp khi debug, cấu hình, event và lifecycle.

Nên dùng khi:

- Nhiều ứng dụng con trong cùng JVM cần chia sẻ một số bean nền tảng.
- Có lý do rõ ràng để parent quản lý lifecycle của infrastructure chung.
- Cần tách bean web hoặc bean theo ứng dụng thành các context riêng.
- Nhóm có thể kiểm soát component scan, profile và property sources của từng context.

Không nên dùng chỉ vì:

- Muốn chia package hoặc module Java.
- Muốn tránh tạo nhiều service process.
- Muốn chia sẻ dữ liệu giữa các microservice.
- Muốn có môi trường cấu hình độc lập nhưng chưa thiết kế Environment riêng.
- Muốn giảm số lượng bean mà không xác định ownership.

Một module Java có thể chia package và cấu hình trong cùng context mà không cần hierarchy. Chỉ tạo nhiều context khi ranh giới container mang lại lợi ích thực tế.

## 16. Bài tập vận dụng

**Bài tập 1 — Parent/child.** Tạo `SharedParentConfiguration` cung cấp bean `Clock`, sau đó tạo `OrdersApiConfiguration` làm child. Xác nhận child inject được `Clock`. Thử chuyển bean `Clock` xuống child và quan sát parent có thể inject nó hay không.

**Bài tập 2 — Sibling.** Tạo `ApiApplication` và `AdminApplication` cùng một parent. Mỗi child cung cấp một bean riêng có tên khác nhau. Xác nhận cả hai nhìn thấy bean parent nhưng không nhìn thấy bean riêng của sibling.

**Bài tập 3 — Bean override.** Đặt một bean cùng tên trong parent và child. Kiểm tra `getBean()` từ child và từ parent, sau đó dùng `@Qualifier` để xác định rõ ứng viên.

**Bài tập 4 — Component scan.** Cho parent scan package gốc chứa cả API và Admin. Quan sát bean bị đăng ký ở context không mong muốn. Thu hẹp `@ComponentScan` và kiểm tra lại hierarchy.

**Bài tập 5 — Web type.** Đặt parent là `WebApplicationType.NONE`, child là `SERVLET`. Xác nhận chỉ child mở web server. Thử cấu hình web infrastructure ở parent và phân tích lỗi hoặc xung đột.

**Bài tập 6 — Lifecycle.** Tạo hai child dùng chung một bean parent có resource cần đóng. Xây dựng trình tự shutdown để không child nào còn sử dụng resource sau khi parent bị đóng.

**Bài tập 7 — Spring Cloud.** So sánh một hierarchy tạo bằng `SpringApplicationBuilder` với bootstrap context legacy của Spring Cloud. Xác định context nào phục vụ tổ chức ứng dụng và context nào phục vụ nạp cấu hình bootstrap.

## 17. Ghi nhớ và nguồn tra cứu

- **Parent** chứa bean dùng chung; **child** có thể tra cứu bean của parent nhưng parent không nhìn xuống child.
- **Sibling** cùng parent và không nhìn thấy bean riêng của nhau.
- `SpringApplicationBuilder.child(...)` tạo child; `sibling(...)` tạo ứng dụng cùng cấp với ứng dụng hiện tại.
- `run(...)` khởi chạy parent trước nếu parent chưa chạy. `sibling(...)` có side effect khởi động ứng dụng hiện tại và parent theo API.
- Mỗi context có bean factory và lifecycle riêng; singleton trong parent có thể được nhiều child dùng chung.
- Đặt web-specific components trong child; parent thường là non-web context.
- Kiểm tra component scan và auto-configuration ở từng context để tránh bean trùng lặp.
- Context hierarchy là cấu trúc trong một JVM, không thay thế ranh giới microservice.
- Bootstrap context của Spring Cloud legacy là một trường hợp tích hợp riêng; không đồng nhất nó với mọi hierarchy tạo thủ công bằng builder.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Framework của dự án:

1. [Spring Boot Reference – Fluent Builder API và context hierarchy](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
2. [Spring Boot Javadoc – `SpringApplicationBuilder`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
3. [Spring Framework Reference – BeanFactory hierarchy](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
4. [Spring Framework Reference – ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
5. [Spring Cloud Context – Bootstrap Application Context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
