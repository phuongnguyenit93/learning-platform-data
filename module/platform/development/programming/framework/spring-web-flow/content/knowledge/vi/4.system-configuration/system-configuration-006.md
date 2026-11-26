# Tạo FlowExecutor và gắn registry trong Spring Web Flow

Một ứng dụng Spring Web Flow có thể chứa nhiều hành trình như đăng ký tài khoản, đặt phòng và thanh toán. Mỗi hành trình được mô tả bằng một **flow definition**, thường là file XML gồm state, event và transition. Để ứng dụng thực thi được các định nghĩa đó, cần hai thành phần trung tâm: **FlowDefinitionRegistry** để đăng ký và tra cứu flow definition, và **FlowExecutor** để khởi chạy hoặc tiếp tục flow execution dựa trên definition đã đăng ký.

Bài thuộc chương **Cấu hình hệ thống** của module `SPRING_WEB_FLOW`. Ta sẽ cấu hình registry và executor bằng XML namespace hoặc Java Config, gắn executor với registry, tổ chức flow location và ID, tùy chỉnh flow builder services, listener và repository, rồi kết nối các bean này với Spring MVC.

## 1. Flow registry và FlowExecutor có vai trò gì?

`FlowDefinitionRegistry` là nơi đăng ký các flow definition mà ứng dụng cho phép tra cứu. Mỗi flow được nhận diện bằng một **flow ID**. Registry biết flow nằm ở resource nào và cung cấp definition khi một thành phần cần lấy theo ID.

`FlowExecutor` là dịch vụ trung tâm điều phối việc thực thi flow. Nó nhận yêu cầu khởi chạy một flow mới hoặc tiếp tục execution đang tồn tại, tìm definition thông qua registry và phối hợp với repository để lưu hoặc khôi phục trạng thái execution.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **`Flow definition`** | Mô tả state, event, transition, action và view | `booking.xml` |
| **`FlowDefinitionRegistry`** | Đăng ký và tra cứu definition theo flow ID | ID `booking` trỏ tới `booking.xml` |
| **`FlowExecutor`** | Khởi chạy hoặc tiếp tục flow execution | Bắt đầu `booking`, xử lý event `confirm` |
| **`FlowExecutionRepository`** | Lưu và khôi phục trạng thái execution theo cấu hình | Giữ execution/snapshot giữa các request |
| **`FlowHandlerMapping`** | Ánh xạ URL MVC tới flow ID | URL `/booking` tìm flow `booking` |
| **`FlowHandlerAdapter`** | Chuyển request MVC vào `FlowExecutor` | Gọi executor để launch/resume |

Có thể nhớ bằng một câu: **registry cho biết flow nào có thể được tìm thấy; executor dùng flow đó để thực thi hành trình**. Registry không tự xử lý event, còn executor không tự dò toàn bộ thư mục dự án nếu các flow chưa được đăng ký.

### 1.1. Chuỗi xử lý khi trình duyệt khởi chạy flow

~~~mermaid
flowchart TD
    A["GET /booking"] --> B["Servlet container / Filter chain"]
    B --> C["DispatcherServlet"]
    C --> D["FlowHandlerMapping"]
    D -->|"Flow ID = booking"| E["FlowHandlerAdapter"]
    E --> F["FlowExecutor"]
    F --> G["FlowDefinitionRegistry"]
    G --> H["booking flow definition"]
    H --> I["Tạo flow execution"]
    I --> J["State đầu tiên và view"]
    J --> K["HTTP response"]
~~~

Sơ đồ thể hiện mối nối chính trong ứng dụng Spring MVC. Registry và executor là phần cấu hình Web Flow; mapping và adapter là lớp tích hợp để request HTTP đi vào flow. Kiểm thử trực tiếp `FlowExecutor` có thể xác minh việc thực thi mà không cần mô phỏng toàn bộ URL routing.

## 2. Đăng ký flow bằng XML namespace

Spring Web Flow cung cấp namespace `webflow-config`. Cấu hình tối thiểu gồm `flow-registry` và `flow-executor`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/webflow-config
           http://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <webflow:flow-registry id="flowRegistry">
        <webflow:flow-location
            id="booking"
            path="/WEB-INF/flows/booking/booking.xml" />
    </webflow:flow-registry>

    <webflow:flow-executor
        id="flowExecutor"
        flow-registry="flowRegistry" />

</beans>
~~~

Trong ví dụ:

- `flow-registry` tạo bean có ID `flowRegistry`.
- `flow-location` đăng ký file định nghĩa flow ở đường dẫn đã chỉ định.
- `id="booking"` đặt flow ID tường minh là `booking`.
- `flow-executor` tạo bean `flowExecutor` và tham chiếu registry qua `flow-registry`.

Nếu không khai báo `id` trên `flow-location`, SWF có thể suy ra flow ID theo quy ước từ vị trí hoặc tên file. Đặt ID tường minh giúp tránh nhầm lẫn giữa tên file, thư mục và URL.

### 2.1. Đường dẫn resource khác URL trình duyệt

Đường dẫn trong `flow-location` là **vị trí resource mà Spring đọc khi xây dựng registry**, không nhất thiết là URL trình duyệt. Ví dụ `/WEB-INF/flows/booking/booking.xml` là file trong web application; trình duyệt không truy cập trực tiếp file nằm trong `WEB-INF`.

| Giá trị | Ví dụ | Dùng ở đâu |
|---|---|---|
| Resource path | `/WEB-INF/flows/booking/booking.xml` | `flow-location` |
| Flow ID | `booking` | Registry và lời gọi khởi chạy flow |
| URL bên ngoài | `/booking` | Routing HTTP qua Spring MVC |
| Flow execution key | `e1s1` (minh họa) | Nhận diện execution/snapshot khi tiếp tục |

URL bên ngoài được xác định bởi `FlowHandlerMapping`, servlet mapping, context path và flow handler. Không lấy resource path của XML làm URL công khai.

### 2.2. Đăng ký nhiều flow

Một registry có thể quản lý nhiều flow definition:

~~~xml
<webflow:flow-registry id="flowRegistry">
    <webflow:flow-location
        id="booking"
        path="/WEB-INF/flows/booking/booking.xml" />
    <webflow:flow-location
        id="registration"
        path="/WEB-INF/flows/registration/registration.xml" />
    <webflow:flow-location
        id="checkout"
        path="/WEB-INF/flows/checkout/checkout.xml" />
</webflow:flow-registry>

<webflow:flow-executor
    id="flowExecutor"
    flow-registry="flowRegistry" />
~~~

Các flow có ID riêng nên được tra cứu độc lập. Mỗi flow nên nằm trong thư mục riêng để chứa definition và tài nguyên liên quan như JSP, message bundle hoặc subflow. Nếu hai flow cùng dùng ID, registry không thể phân biệt chúng theo ý đồ của ứng dụng; hãy chọn ID duy nhất hoặc đặt base path để ID được tạo từ cấu trúc thư mục.

## 3. Dùng base-path và location pattern

Khi dự án có nhiều flow, khai báo từng `flow-location` có thể dài. `base-path` cho phép đặt thư mục gốc; đường dẫn trong mỗi location sẽ tương đối với thư mục đó.

~~~xml
<webflow:flow-registry
    id="flowRegistry"
    base-path="/WEB-INF/flows">
    <webflow:flow-location path="/booking/booking.xml" />
    <webflow:flow-location path="/registration/registration.xml" />
    <webflow:flow-location path="/checkout/checkout.xml" />
</webflow:flow-registry>
~~~

Với base path `/WEB-INF/flows`, các location được giải quyết từ thư mục gốc đó. Theo quy ước ID của registry có base path, phần đường dẫn thư mục tương đối có thể trở thành flow ID. Với cấu trúc ví dụ, các ID thường là `booking`, `registration` và `checkout`. Nếu cần ID khác quy ước, chỉ định `id` trực tiếp.

### 3.1. Tự động đăng ký theo pattern

Có thể đăng ký mọi flow file khớp location pattern:

~~~xml
<webflow:flow-registry
    id="flowRegistry"
    base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern
        value="/**/*-flow.xml" />
</webflow:flow-registry>
~~~

Với cấu trúc:

~~~text
/WEB-INF/flows/
  booking/
    booking-flow.xml
  registration/
    registration-flow.xml
  checkout/
    checkout-flow.xml
~~~

Pattern tìm các file kết thúc bằng `-flow.xml` trong cây thư mục. Base path giúp ID được tạo từ đường dẫn thư mục tương đối, chẳng hạn `booking`, `registration` và `checkout`.

Location pattern phù hợp khi quy ước đặt tên thống nhất. Nếu có XML không phải flow hoặc một số flow cần ID đặc biệt, dùng danh sách location tường minh. Sau khi thêm file mới, kiểm tra registry thật sự nhận flow đó thay vì chỉ thấy file tồn tại trên đĩa.

### 3.2. Gán flow ID tùy chỉnh

Nếu tên file hoặc cấu trúc thư mục không phù hợp với ID muốn công bố, chỉ định `id`:

~~~xml
<webflow:flow-registry id="flowRegistry">
    <webflow:flow-location
        path="/WEB-INF/flows/hotel/reserve-room.xml"
        id="bookHotel" />
</webflow:flow-registry>
~~~

Trong cấu hình này, flow ID là `bookHotel`, dù file tên `reserve-room.xml` và nằm trong thư mục `hotel`. Các thành phần khác phải dùng đúng ID `bookHotel` khi tra cứu hoặc định tuyến.

## 4. Tạo FlowExecutor và gắn với registry

Sau khi registry đã đăng ký các definition, tạo `FlowExecutor` và truyền registry vào cấu hình của nó:

~~~xml
<webflow:flow-executor
    id="flowExecutor"
    flow-registry="flowRegistry" />
~~~

Mối quan hệ này là điểm cốt lõi của bài. Executor cần registry để tìm flow definition theo ID khi có yêu cầu khởi chạy. Khi tiếp tục một execution, executor còn phối hợp với flow execution repository để khôi phục trạng thái đã lưu.

Trong ứng dụng thực, nên đặt cả hai bean trong application context mà thành phần tích hợp Web Flow có thể nhìn thấy. Với ứng dụng Spring MVC dùng context cha/con, context chứa `FlowHandlerAdapter` phải truy cập được `flowExecutor`; executor phải tham chiếu đúng registry. Bean nằm trong context con không tự động được context cha nhìn thấy.

### 4.1. Tạo FlowExecutor bằng Java Config

Nếu ứng dụng dùng Java Config, kế thừa `AbstractFlowConfiguration` và khai báo hai bean:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.executor.FlowExecutor;

@Configuration
public class WebFlowConfig extends AbstractFlowConfiguration {

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
            .addFlowLocation(
                "/WEB-INF/flows/booking/booking.xml",
                "booking")
            .addFlowLocation(
                "/WEB-INF/flows/registration/registration.xml",
                "registration")
            .build();
    }

    @Bean
    public FlowExecutor flowExecutor() {
        return getFlowExecutorBuilder(flowRegistry()).build();
    }
}
~~~

`getFlowDefinitionRegistryBuilder()` tạo builder cho registry; `addFlowLocation(path, id)` đăng ký file và gán ID; `getFlowExecutorBuilder(flowRegistry())` tạo builder executor đã gắn với registry. Các bean được Spring quản lý nhờ `@Bean`.

Đây là cách cấu hình thay thế cho XML ở phần trước. Không khai báo đồng thời hai registry/executor trùng chức năng trong cùng context nếu không có lý do rõ ràng; khi trộn XML và Java Config, hãy bảo đảm mỗi bean ID duy nhất và executor tham chiếu đúng registry.

## 5. Tùy chỉnh FlowBuilderServices

`FlowBuilderServices` cung cấp các dịch vụ mà SWF sử dụng khi **xây dựng flow definition**. Nếu không chỉ định `flow-builder-services`, registry dùng các triển khai mặc định. Khi cần tùy chỉnh, có thể cấu hình conversion service, expression parser hoặc view factory creator.

~~~xml
<webflow:flow-builder-services
    id="flowBuilderServices"
    conversion-service="conversionService"
    expression-parser="expressionParser"
    view-factory-creator="viewFactoryCreator" />

<webflow:flow-registry
    id="flowRegistry"
    flow-builder-services="flowBuilderServices">
    <webflow:flow-location
        id="booking"
        path="/WEB-INF/flows/booking/booking.xml" />
</webflow:flow-registry>
~~~

Các bean `conversionService`, `expressionParser` và `viewFactoryCreator` phải được khai báo riêng. Chỉ cấu hình dịch vụ thực sự cần thay đổi; không phải dự án nào cũng cần custom expression parser hoặc view factory.

| Dịch vụ | Vai trò khi xây dựng flow | Khi nào cần tùy chỉnh |
|---|---|---|
| `ConversionService` | Chuyển kiểu dữ liệu khi xử lý request parameter, action và binding | Có kiểu domain riêng hoặc quy tắc định dạng đặc thù |
| `ExpressionParser` | Phân tích và đánh giá biểu thức trong flow | Cần parser/cấu hình EL khác mặc định |
| `ViewFactoryCreator` | Tạo view factory cho các view-state | Cần tích hợp công nghệ view hoặc resolver riêng |
| Development mode | Cho phép hot reload flow definition và tài nguyên phụ thuộc trong môi trường phát triển | Chỉ bật khi phát triển, không tùy tiện bật production |

Với ứng dụng Spring MVC, view factory mặc định thường tạo view factory tích hợp Spring MVC. Nếu dùng resolver hoặc công nghệ view tùy chỉnh, cấu hình view factory tương ứng và kiểm tra đường render thực tế.

### 5.1. Java Config cho FlowBuilderServices

~~~java
@Bean
public FlowBuilderServices flowBuilderServices() {
    return getFlowBuilderServicesBuilder()
        .setConversionService(conversionService())
        .setExpressionParser(expressionParser())
        .setViewFactoryCreator(viewFactoryCreator())
        .build();
}

@Bean
public FlowDefinitionRegistry flowRegistry() {
    return getFlowDefinitionRegistryBuilder(flowBuilderServices())
        .addFlowLocation(
            "/WEB-INF/flows/booking/booking.xml",
            "booking")
        .build();
}
~~~

Đoạn trên minh họa cách truyền builder services vào registry builder. Các phương thức `conversionService()`, `expressionParser()` và `viewFactoryCreator()` phải trả về implementation phù hợp và được khai báo trong cấu hình ứng dụng. Đây là phần bổ sung cho Java Config ở phần 4, không phải một class cấu hình độc lập nếu thiếu các bean phụ thuộc.

## 6. Gắn listener và cấu hình repository cho FlowExecutor

Ngoài registry, executor còn có thể cấu hình listener theo vòng đời execution và giới hạn lưu trữ execution/snapshot.

### 6.1. Flow execution listener

Listener quan sát các sự kiện trong vòng đời flow execution, hữu ích cho audit, tích hợp bảo mật hoặc logic hạ tầng cần chạy ở thời điểm thích hợp.

~~~xml
<webflow:flow-executor
    id="flowExecutor"
    flow-registry="flowRegistry">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="auditFlowListener" />
        <webflow:listener
            ref="securityFlowListener"
            criteria="booking,checkout" />
    </webflow:flow-execution-listeners>
</webflow:flow-executor>
~~~

Các bean listener phải triển khai interface listener mà phiên bản SWF yêu cầu. Thuộc tính `criteria` có thể giới hạn listener cho một tập flow ID; nếu bỏ tiêu chí, listener được áp dụng theo cấu hình mặc định của executor.

Listener không thay thế service nghiệp vụ và không nên dùng để giấu thao tác ghi dữ liệu quan trọng khỏi action-state. Hãy giữ logic nghiệp vụ ở service/action; listener phù hợp cho những mối quan tâm xuyên suốt vòng đời execution.

### 6.2. Giới hạn số execution và snapshot

Repository của executor quản lý trạng thái execution và lịch sử snapshot. Có thể cấu hình giới hạn bằng XML:

~~~xml
<webflow:flow-executor
    id="flowExecutor"
    flow-registry="flowRegistry">
    <webflow:flow-execution-repository
        max-executions="5"
        max-execution-snapshots="20" />
</webflow:flow-executor>
~~~

- `max-executions` giới hạn số flow execution được giữ cho mỗi HTTP session người dùng; khi vượt giới hạn, execution cũ nhất có thể bị loại bỏ.
- `max-execution-snapshots` giới hạn số snapshot lịch sử được lưu cho mỗi flow execution.
- Snapshot hỗ trợ hành vi quay lại bằng nút Back của trình duyệt. Nếu tắt snapshot, execution key trỏ đến snapshot chưa lưu có thể không còn dùng được.

Giá trị `5` và `20` chỉ là cấu hình minh họa. Chọn giới hạn theo số wizard người dùng có thể mở, độ dài hành trình, lượng dữ liệu trong flow scope và yêu cầu hỗ trợ browser history. Snapshot quá nhiều có thể tăng chi phí lưu trữ; giới hạn quá thấp có thể làm người dùng mất khả năng tiếp tục những execution cũ.

### 6.3. Cấu hình tương đương trong Java

~~~java
@Bean
public FlowExecutor flowExecutor() {
    return getFlowExecutorBuilder(flowRegistry())
        .addFlowExecutionListener(auditFlowListener())
        .setMaxFlowExecutions(5)
        .setMaxFlowExecutionSnapshots(20)
        .build();
}
~~~

Các method trên thuộc builder API của Spring Web Flow 2.5.x. Nếu cần giới hạn listener theo flow ID, builder cũng hỗ trợ overload nhận criteria. Chọn XML hoặc Java Config làm nơi quản lý cấu hình executor để tránh những giá trị khác nhau giữa hai nguồn.

## 7. Kết nối registry và executor với Spring MVC

Registry và executor chưa tự biến thành endpoint HTTP. Trong Spring MVC, hai thành phần tích hợp quan trọng là:

- `FlowHandlerMapping`: nhận diện URL nào tương ứng với flow ID trong registry.
- `FlowHandlerAdapter`: nhận flow handler và chuyển request tới `FlowExecutor`.

Ví dụ phần cấu hình MVC rút gọn:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
    <property name="order" value="-1" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

`FlowHandlerMapping` dùng registry để xác định flow theo URL; `FlowHandlerAdapter` dùng executor để khởi chạy hoặc tiếp tục flow execution. Thứ tự `HandlerMapping` cần được thiết kế cùng các controller MVC khác để tránh URL trùng nhau.

Có thể hình dung request `GET /booking` được mapping tới flow ID `booking`. Khi form phát event tiếp theo, request tiếp tục execution thông qua URL do SWF tạo. Mapping/adapter xử lý phần HTTP; executor xử lý phần flow runtime.

### 7.1. ApplicationContext nào chứa các bean?

Trong ứng dụng Spring MVC truyền thống thường có root application context và một child context gắn với `DispatcherServlet`. Bean ở root context có thể được child context nhìn thấy; chiều ngược lại không tự động đúng.

Có thể đặt registry/executor trong root context dùng chung, hoặc trong context MVC nếu các thành phần cần thiết cùng truy cập được. Điều quan trọng là context chứa `FlowHandlerMapping` và `FlowHandlerAdapter` phải nhìn thấy đúng `flowRegistry` và `flowExecutor`.

Nếu ứng dụng có nhiều `DispatcherServlet` hoặc nhiều registry, dùng bean ID/qualifier và cấu hình mapping rõ ràng. Tránh để một adapter lấy nhầm executor gắn với registry của ứng dụng khác.

## 8. Kiểm tra cấu hình sau khi tạo registry và executor

Sau khi cấu hình, không chỉ kiểm tra ứng dụng khởi động thành công. Cần xác minh registry có flow ID dự kiến và executor có thể dùng registry đó.

Các bước kiểm tra:

1. Xác nhận resource path trỏ đúng file flow XML.
2. Xác nhận flow ID được tạo đúng theo `id`, filename hoặc base path.
3. Kiểm tra registry chứa ID cần dùng.
4. Khởi chạy thử flow qua `FlowExecutor` hoặc request MVC.
5. Gửi một event tiếp tục flow và xác minh execution được khôi phục.
6. Kiểm tra view factory nếu flow vào view-state nhưng không render được.
7. Kiểm tra listener và repository nếu có cấu hình riêng.

Một integration test có thể kiểm tra registry được inject đúng:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;

@SpringJUnitConfig(WebFlowConfig.class)
class WebFlowConfigurationTests {

    @Autowired
    private FlowDefinitionRegistry flowRegistry;

    @Test
    void bookingFlowIsRegistered() {
        assertTrue(flowRegistry.containsFlowDefinition("booking"));
    }
}
~~~

Ví dụ này giả định `WebFlowConfig` chỉ có một bean `FlowDefinitionRegistry` hoặc bean được chọn đúng. Nếu context có nhiều registry, dùng `@Qualifier("flowRegistry")`. Test xác minh registry nhận flow ID; nó chưa chứng minh view, HTTP routing, security hay toàn bộ execution hoạt động đúng.

### 8.1. Phân biệt lỗi registry với lỗi executor

| Hiện tượng | Lớp cần kiểm tra trước | Nguyên nhân thường gặp |
|---|---|---|
| Không tìm thấy flow ID | Registry | Chưa đăng ký location hoặc ID sai |
| Không đọc được flow XML | Flow builder/registry | Resource path sai, XML sai schema hoặc flow definition không hợp lệ |
| Registry tìm thấy flow nhưng không thể khởi chạy | Executor hoặc flow definition | Definition có lỗi khởi tạo, action/view phụ thuộc thiếu |
| Request URL không vào flow | MVC mapping | `FlowHandlerMapping` không match path hoặc thứ tự handler không phù hợp |
| Flow vào state nhưng không render view | View factory/resolver | View name, resolver hoặc template path sai |
| Request tiếp tục không tìm được execution | Execution repository | Session/execution hết hạn, key cũ hoặc snapshot không còn |

Khi chẩn đoán, tách lỗi theo lớp giúp tránh thay đổi registry trong khi vấn đề thực sự nằm ở URL mapping hoặc view resolution.

## 9. Những sai lầm cấu hình thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Khai báo flow file nhưng không đưa vào registry | Executor không tra cứu được flow theo ID | Thêm `flow-location` hoặc location pattern |
| Nhầm resource path với URL trình duyệt | URL gọi flow trả 404 | Cấu hình `FlowHandlerMapping` riêng |
| ID suy ra không như dự kiến | URL hoặc lời gọi executor dùng ID sai | Khai báo `id` rõ ràng hoặc kiểm tra quy tắc base path |
| Executor gắn nhầm registry | Không tìm thấy flow hoặc dùng definition khác | Tham chiếu `flow-registry` tường minh |
| Có hai flow trùng ID | Registry mơ hồ hoặc không khởi tạo được | Đặt ID duy nhất, tổ chức thư mục |
| Dùng pattern quá rộng | Đăng ký nhầm XML không phải flow | Dùng hậu tố/đường dẫn pattern nhất quán |
| Custom builder services chưa được gắn vào registry | Flow dùng converter/view factory mặc định | Đặt `flow-builder-services` trên registry |
| Listener chưa khai báo bean | Application context không khởi tạo | Đăng ký listener và kiểm tra kiểu tương thích |
| Giới hạn snapshot quá thấp | Browser Back không còn snapshot tương ứng | Điều chỉnh `max-execution-snapshots` |
| Quá nhiều execution trong session | Execution cũ bị loại bỏ sớm | Điều chỉnh giới hạn và hướng dẫn người dùng lưu tiến trình |
| Bean nằm sai application context | Mapping/adapter không thấy registry hoặc executor | Kiểm tra quan hệ root/child context |

## 10. Bài tập thực hành

Tạo cấu hình cho ba flow: `registration`, `booking` và `checkout`, với file lần lượt nằm trong các thư mục riêng dưới `/WEB-INF/flows`.

Yêu cầu:

1. Tạo `FlowDefinitionRegistry` và đăng ký ba file bằng XML namespace.
2. Gán flow ID rõ ràng cho ít nhất một file có tên khác ID.
3. Thử cấu hình `base-path` và `flow-location-pattern`, sau đó kiểm tra các ID được suy ra.
4. Tạo `FlowExecutor` tham chiếu đúng registry.
5. Thêm một execution listener chỉ theo dõi flow `checkout`.
6. Cấu hình giới hạn execution và snapshot phù hợp với wizard nhiều bước.
7. Tạo Java Config tương đương bằng `AbstractFlowConfiguration`.
8. Kết nối `FlowHandlerMapping` và `FlowHandlerAdapter` để URL bên ngoài khởi chạy được flow.
9. Viết integration test xác nhận registry chứa đủ ba ID và khởi chạy được flow `booking`.
10. Thử cố ý đổi sai ID hoặc resource path, quan sát lỗi và xác định đúng lớp chịu trách nhiệm.

**Tiêu chí hoàn thành:** bạn có thể giải thích flow definition được đăng ký ở đâu, flow ID được tạo thế nào, `FlowExecutor` lấy definition từ registry ra sao, repository giữ execution như thế nào và Spring MVC đưa request tới executor bằng cách nào. Khi các mối nối này rõ ràng, việc thêm flow mới hoặc thay đổi cách tổ chức tài nguyên sẽ ít gây lỗi cấu hình dây chuyền.

## Tài liệu tham khảo

- Spring Web Flow 2.5.1 Reference Guide — [System Setup](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/system-setup.html): FlowRegistry, FlowExecutor, location, base path, builder services, listeners và execution repository.
- Spring Web Flow 2.5.1 Reference Guide — [Spring MVC Integration](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/spring-mvc.html): FlowHandlerMapping, FlowHandlerAdapter và cách điều phối request.
- Spring Web Flow API — [FlowDefinitionRegistry](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/definition/registry/FlowDefinitionRegistry.html): tra cứu các flow definition đã đăng ký.

*Ghi chú tương thích:* Các ví dụ Java/XML tham chiếu API Spring Web Flow 2.5.x. Khi dùng phiên bản khác, kiểm tra schema namespace, package, Servlet API (`javax.servlet` hoặc `jakarta.servlet`) và bộ Spring Framework tương thích. Không ghép cấu hình của các thế hệ thư viện khác nhau mà chưa xác minh dependency.
