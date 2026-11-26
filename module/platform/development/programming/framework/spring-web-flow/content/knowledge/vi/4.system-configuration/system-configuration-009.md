# Cấu hình XML tương ứng với Java configuration

Trong Spring Web Flow, một hành trình web nhiều bước được mô hình hóa bằng flow, state, event, transition và subflow. Ví dụ, quy trình đặt chỗ có thể đi qua các bước chọn dịch vụ, nhập thông tin, xác nhận và hoàn tất. Spring cần một nhóm bean để tìm định nghĩa flow, thực thi flow và kết nối yêu cầu HTTP của Spring MVC với flow đó.

Nhóm bean hạ tầng này có thể được khai báo bằng XML hoặc Java configuration. Hai cách khai báo tạo ra cùng một cấu trúc runtime nếu chúng đăng ký cùng thành phần và cùng giá trị cấu hình. Bài học này đặt hai cách cạnh nhau để bạn có thể đọc một dự án đang dùng XML, viết cấu hình mới bằng Java hoặc chuyển đổi từng phần mà không làm thay đổi hành vi của flow.

## 1. Phân biệt cấu hình hạ tầng và định nghĩa flow

Trước khi so sánh, cần tách hai lớp thường cùng xuất hiện trong một ứng dụng Spring Web Flow:

- **Cấu hình hạ tầng Spring** khai báo registry, executor và các thành phần tích hợp Spring MVC. Đây là phần có thể viết bằng XML bean configuration hoặc Java configuration.
- **Định nghĩa flow** mô tả state, event, transition, action, subflow và view của một hành trình. Spring Web Flow thường lưu định nghĩa này trong các file XML có tên như **booking-flow.xml**.

Java configuration không tự động biến nội dung của **booking-flow.xml** thành mã Java. Trong ví dụ của bài học, Java configuration chỉ thay thế phần khai báo bean hạ tầng; registry vẫn đọc các file định nghĩa flow.

| Thành phần | Vai trò |
|---|---|
| **FlowDefinitionRegistry** | Tìm và đăng ký các định nghĩa flow để ứng dụng có thể tra cứu theo flow id. |
| **FlowExecutor** | Khởi chạy, tiếp tục và quản lý quá trình thực thi flow. |
| **FlowHandlerMapping** | Nhận diện URL thuộc về một flow và chọn flow handler phù hợp. |
| **FlowHandlerAdapter** | Chuyển yêu cầu đã được ánh xạ sang **FlowExecutor** để xử lý. |
| Flow definition | Mô tả các state, event và transition của từng hành trình. |

Có thể hình dung đường đi của một yêu cầu như sau:

~~~text
HTTP request
    |
    v
FlowHandlerMapping
    |
    v
FlowHandlerAdapter
    |
    v
FlowExecutor ------> FlowDefinitionRegistry
    |                         |
    |                         v
    |                  booking-flow.xml
    v
State / Event / Transition
    |
    v
Spring MVC view
~~~

Registry và executor là nền tảng để flow hoạt động. Mapping và adapter kết nối nền tảng đó với Spring MVC. Khi thay XML bean configuration bằng Java configuration, mối quan hệ này vẫn phải được giữ nguyên.

## 2. Chuẩn bị vị trí lưu định nghĩa flow

Giả sử ứng dụng lưu các flow trong thư mục sau:

~~~text
src/main/webapp/
└── WEB-INF/
    └── flows/
        ├── booking/
        │   └── booking-flow.xml
        └── registration/
            └── registration-flow.xml
~~~

Registry cần biết thư mục gốc và quy tắc tìm file. Trong ví dụ này, base path là **/WEB-INF/flows** và pattern **/**/*-flow.xml** tìm các file kết thúc bằng **-flow.xml** trong những thư mục con.

Tên flow id thường được suy ra từ vị trí hoặc tên file theo quy tắc của registry. Vì vậy, khi đổi base path hay pattern, hãy kiểm tra lại URL khởi chạy flow và cách ứng dụng tham chiếu flow id. Một registry không tìm thấy file có thể khiến URL flow trả về lỗi dù các controller và view khác vẫn hoạt động.

## 3. Khai báo bằng XML

Spring Web Flow cung cấp namespace **webflow-config** để khai báo các bean hạ tầng. Cấu hình tối thiểu có thể đặt trong application context của Spring MVC:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/webflow-config
           https://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <webflow:flow-registry id="flowRegistry"
                           base-path="/WEB-INF/flows">
        <webflow:flow-location-pattern value="/**/*-flow.xml"/>
    </webflow:flow-registry>

    <webflow:flow-executor id="flowExecutor"
                           flow-registry="flowRegistry"/>

    <webflow:flow-handler-mapping order="-1"
                                  flow-registry="flowRegistry"/>

    <webflow:flow-handler-adapter flow-executor="flowExecutor"/>

</beans>
~~~

Ý nghĩa từng khai báo:

1. **flow-registry** quét các file flow theo base path và location pattern.
2. **flow-executor** sử dụng registry để tìm flow và quản lý các lần thực thi.
3. **flow-handler-mapping** ánh xạ URL tới flow. Giá trị **order** quyết định thứ tự mapping này được xét so với các handler mapping khác trong Spring MVC.
4. **flow-handler-adapter** nhận yêu cầu đã được mapping và gọi executor.

Giá trị **order="-1"** giúp mapping của flow được xét sớm trong cấu hình ví dụ. Giá trị phù hợp còn phụ thuộc thứ tự các **HandlerMapping** khác của ứng dụng. Nếu một controller và một flow cùng có thể nhận một URL, hãy kiểm tra thứ tự mapping để tránh yêu cầu đi nhầm handler.

Các ứng dụng có nhu cầu tùy biến cách xây dựng flow có thể khai báo thêm flow builder services, chẳng hạn để cấu hình view factory, expression parser, conversion service hoặc binding. Chỉ thêm các thành phần này khi ứng dụng thực sự cần tùy biến; cấu hình cơ bản ở trên đã thể hiện các bean cốt lõi để tích hợp flow với Spring MVC.

## 4. Khai báo tương đương bằng Java configuration

Với phiên bản Spring Web Flow có hỗ trợ **AbstractFlowConfiguration**, có thể dùng lớp này để tạo registry và executor bằng các builder do Spring Web Flow cung cấp. Mapping và adapter được khai báo như các bean Spring thông thường.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.executor.FlowExecutor;
import org.springframework.webflow.mvc.servlet.FlowHandlerAdapter;
import org.springframework.webflow.mvc.servlet.FlowHandlerMapping;

@Configuration
public class WebFlowConfiguration extends AbstractFlowConfiguration {

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
                .setBasePath("/WEB-INF/flows")
                .addFlowLocationPattern("/**/*-flow.xml")
                .build();
    }

    @Bean
    public FlowExecutor flowExecutor(FlowDefinitionRegistry flowRegistry) {
        return getFlowExecutorBuilder(flowRegistry).build();
    }

    @Bean
    public FlowHandlerMapping flowHandlerMapping(
            FlowDefinitionRegistry flowRegistry) {
        FlowHandlerMapping mapping = new FlowHandlerMapping();
        mapping.setOrder(-1);
        mapping.setFlowRegistry(flowRegistry);
        return mapping;
    }

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter(FlowExecutor flowExecutor) {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor);
        return adapter;
    }
}
~~~

Các method **@Bean** có quan hệ tương ứng trực tiếp với cấu hình XML:

- **flowRegistry()** tạo registry với cùng base path và location pattern.
- **flowExecutor(...)** tạo executor dựa trên registry được Spring inject.
- **flowHandlerMapping(...)** đăng ký mapping với cùng thứ tự và registry.
- **flowHandlerAdapter(...)** kết nối adapter với executor.

Tham số của các method **@Bean** được Spring inject theo kiểu. Cách viết này làm rõ dependency giữa các bean và tránh phải tự tạo instance bằng cách gọi method cấu hình từ nơi khác. Ứng dụng vẫn cần cấu hình Spring MVC phù hợp; lớp trên chỉ thể hiện phần tích hợp Spring Web Flow.

Nếu dự án dùng phiên bản Spring Web Flow cũ không có **AbstractFlowConfiguration** hoặc các builder tương ứng, hãy kiểm tra API của đúng phiên bản đang dùng. Không nên sao chép cấu hình Java của phiên bản mới vào dự án cũ mà chưa xác nhận class và method tồn tại.

## 5. Đối chiếu XML và Java configuration

| Nhiệm vụ | XML configuration | Java configuration |
|---|---|---|
| Tạo registry | **<webflow:flow-registry>** | **getFlowDefinitionRegistryBuilder()** |
| Chọn thư mục flow | Thuộc tính **base-path** | **setBasePath(...)** |
| Tìm file flow | **<webflow:flow-location-pattern>** | **addFlowLocationPattern(...)** |
| Tạo executor | **<webflow:flow-executor>** | **getFlowExecutorBuilder(...).build()** |
| Ánh xạ URL | **<webflow:flow-handler-mapping>** | Bean **FlowHandlerMapping** |
| Xử lý yêu cầu flow | **<webflow:flow-handler-adapter>** | Bean **FlowHandlerAdapter** |
| Tham chiếu dependency | **ref** hoặc thuộc tính namespace | Tham số method **@Bean** hoặc dependency injection |

Điểm cần giữ nhất quán là **đồ thị dependency**. Executor phải dùng đúng registry mà mapping sử dụng; adapter phải dùng executor đang được ứng dụng quản lý. Nếu cấu hình Java tạo một registry riêng cho executor nhưng mapping lại trỏ tới registry khác, URL có thể được nhận diện theo một tập flow trong khi executor tìm kiếm ở tập flow khác.

Khác biệt chủ yếu nằm ở cách biểu diễn:

- XML thể hiện quan hệ bean bằng phần tử và thuộc tính. Cấu hình có tính khai báo, dễ đọc tập trung khi dự án vốn quản lý Spring context bằng XML.
- Java configuration thể hiện bean bằng method và dependency bằng kiểu tham số. IDE hỗ trợ điều hướng, đổi tên và kiểm tra kiểu tốt hơn; có thể kết hợp với profile hoặc điều kiện cấu hình của Spring.
- Cả hai đều được Spring quản lý trong application context. Vòng đời flow, state, event, transition, subflow, binding và validation không thay đổi chỉ vì cách khai báo bean thay đổi.

## 6. Chọn cách cấu hình cho dự án

Nên giữ XML bean configuration khi ứng dụng đã có một cấu trúc XML ổn định, nhóm vận hành quen chỉnh cấu hình khai báo hoặc việc chuyển đổi không đem lại lợi ích rõ ràng. Namespace của Spring Web Flow giúp cấu hình ngắn và thể hiện trực tiếp mục đích của từng bean.

Java configuration phù hợp khi phần lớn application context đã dùng **@Configuration**, khi cần tổ chức cấu hình theo class hoặc khi muốn tận dụng dependency injection theo kiểu và các khả năng cấu hình theo môi trường. Cấu hình Java cũng thuận tiện khi registry hoặc executor cần được xây dựng dựa trên những bean khác.

Một ứng dụng có thể dùng cả XML và Java configuration, ví dụ định nghĩa flow vẫn ở XML trong khi registry, executor và MVC integration được khai báo bằng Java. Đây là cách kết hợp phổ biến và không có nghĩa phải viết lại các state hay transition bằng Java.

Khi kết hợp hai kiểu cấu hình, hãy bảo đảm mỗi bean hạ tầng chỉ được đăng ký theo một đường cấu hình có chủ đích. Hai định nghĩa cùng tên có thể gây lỗi ghi đè hoặc xung đột tùy cách khởi tạo context. Cũng cần bảo đảm **FlowHandlerMapping** và **FlowHandlerAdapter** nằm trong context mà **DispatcherServlet** có thể nhìn thấy; các bean ở root context chỉ được dùng khi chúng có thể được context MVC truy cập.

## 7. Các lỗi cấu hình thường gặp

### Registry không tìm thấy flow

Kiểm tra base path, location pattern, vị trí file trong ứng dụng đã đóng gói và tên file. Đường dẫn trong cấu hình phải phù hợp với cách ứng dụng triển khai tài nguyên, không chỉ với đường dẫn trong IDE.

### URL flow bị controller khác nhận trước

Kiểm tra **order** của **FlowHandlerMapping** so với các **HandlerMapping** khác. Nếu URL bị controller nhận trước, request sẽ không đến **FlowHandlerAdapter**, dù registry và executor đã được tạo đúng.

### Mapping và executor dùng registry khác nhau

Đảm bảo cả hai cùng tham chiếu một bean **FlowDefinitionRegistry**. Trong Java configuration, inject registry vào tham số method; trong XML, dùng cùng bean id trong các thuộc tính tham chiếu.

### Bean không nằm trong application context phù hợp

Kiểm tra cấu trúc root context và servlet context. Mapping và adapter cần được đăng ký ở nơi Spring MVC sử dụng chúng. Nếu cấu hình bị đặt trong một context độc lập mà **DispatcherServlet** không nhìn thấy, URL flow sẽ không được xử lý như dự kiến.

### Nhầm lẫn giữa flow definition và bean configuration

Đổi cấu hình hạ tầng sang Java không loại bỏ yêu cầu về file flow. Registry vẫn phải nạp các định nghĩa chứa state, transition và event. Nếu pattern chỉ tới thư mục rỗng hoặc không khớp tên file, việc khai báo bean thành công vẫn chưa chứng minh flow có thể chạy.

### Phiên bản thư viện không tương thích

Các class cấu hình, namespace và builder phải phù hợp với phiên bản Spring Web Flow và Spring Framework trong ứng dụng. Dùng các phiên bản không tương thích có thể gây lỗi khi khởi động context hoặc khi xử lý request. Hãy quản lý dependency theo một bộ phiên bản tương thích của dự án.

## 8. Kiểm tra cấu hình sau khi triển khai

Sau khi khai báo XML hoặc Java configuration, kiểm tra theo thứ tự sau:

1. **Khởi động application context.** Xác nhận Spring tạo được registry, executor, mapping và adapter mà không có lỗi bean hoặc schema.
2. **Xác nhận registry nạp flow.** Kiểm tra log khởi động hoặc truy vấn registry trong bài kiểm thử để bảo đảm các flow mong đợi đã được đăng ký.
3. **Mở URL khởi chạy flow.** Xác nhận request được **FlowHandlerMapping** nhận diện và flow hiển thị đúng view đầu tiên.
4. **Gửi event để chuyển state.** Kiểm tra transition, form binding và validation hoạt động theo định nghĩa flow.
5. **Kiểm tra subflow và kết thúc flow.** Bảo đảm luồng con trả kết quả cho luồng cha và luồng chính hoàn tất đúng cách.
6. **Kiểm tra tiếp tục phiên flow.** Thử gửi nhiều request trong cùng phiên và kiểm tra hành vi khi refresh hoặc quay lại theo chính sách của ứng dụng.

Một bài kiểm thử tích hợp hữu ích nên đi qua ít nhất một luồng nhiều bước, thay vì chỉ kiểm tra rằng application context khởi động thành công. Context có thể tạo đủ bean nhưng registry vẫn không tìm thấy file, mapping có thể sai thứ tự hoặc view có thể không được phân giải.

## 9. Chuyển từ XML sang Java configuration

Khi cần chuyển đổi, hãy thực hiện theo từng phần để dễ đối chiếu:

1. Ghi lại bean id, base path, location pattern, registry được tham chiếu và thứ tự handler mapping hiện tại.
2. Tạo bean **FlowDefinitionRegistry** bằng builder với cùng base path và pattern.
3. Tạo **FlowExecutor** dựa trên registry đó; giữ nguyên các tùy chọn executor và listener nếu dự án đang sử dụng.
4. Tạo **FlowHandlerMapping** và **FlowHandlerAdapter**, giữ nguyên thứ tự mapping và dependency.
5. Nếu XML cũ có flow builder services hoặc listener tùy chỉnh, chuyển từng cấu hình đó bằng API tương ứng của phiên bản Spring Web Flow đang dùng.
6. Chạy lại kiểm thử khởi động, khởi chạy flow, gửi event, validation, subflow và hoàn tất flow.
7. Sau khi xác nhận Java configuration hoạt động, loại bỏ các khai báo XML hạ tầng đã được thay thế để tránh đăng ký bean trùng lặp.

Không thay đổi đồng thời URL flow, vị trí file, tên flow id và cách cấu hình bean nếu mục tiêu chỉ là chuyển đổi hình thức cấu hình. Giữ nguyên các giá trị này giúp xác định lỗi phát sinh từ quá trình chuyển đổi dễ hơn.

## 10. Ghi nhớ

XML và Java configuration là hai cách khai báo cùng một hạ tầng Spring Web Flow. Khi đối chiếu, hãy lần theo bốn trách nhiệm: registry tìm định nghĩa flow, executor quản lý thực thi, handler mapping nhận diện URL và handler adapter chuyển request cho executor. Định nghĩa state, event, transition và subflow vẫn được registry nạp theo vị trí đã cấu hình.

Chọn kiểu cấu hình dựa trên cách tổ chức application context của dự án, sau đó giữ dependency và thứ tự handler nhất quán. Kiểm thử một hành trình nhiều bước từ lúc khởi chạy đến khi hoàn tất là cách xác nhận cấu hình thực sự hoạt động.
