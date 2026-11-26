# DispatcherServlet trong ứng dụng có Spring Web Flow

## 1. Vai trò của DispatcherServlet khi tích hợp Web Flow

Trong một ứng dụng Spring MVC, `DispatcherServlet` là **front controller**: tiếp nhận các HTTP request đã được servlet container chuyển đến, tìm thành phần xử lý phù hợp và điều phối việc trả response. Khi ứng dụng bổ sung **Spring Web Flow (SWF)** để thực hiện những hành trình nhiều bước như đăng ký, đặt hàng hoặc duyệt hồ sơ, `DispatcherServlet` vẫn là điểm tiếp nhận request của tầng web.

Điểm thay đổi là ứng dụng có thêm các thành phần MVC chuyên dụng để nhận diện và thực thi **flow**. Một request có thể tiếp tục được xử lý bởi `@Controller` thông thường hoặc được giao cho **FlowHandler**, tùy URL và cấu hình các `HandlerMapping`. Spring Web Flow quản lý state, event, transition, subflow và thời gian sống của flow execution; Spring MVC đảm nhiệm việc định tuyến HTTP, phối hợp handler adapter và hiển thị view.

Ví dụ, cùng một ứng dụng có thể phục vụ:

| Request | Thành phần xử lý | Mục đích |
|---|---|---|
| `GET /products` | `@Controller` / Spring MVC handler | Hiển thị danh sách sản phẩm |
| `GET /registration` | `FlowHandlerMapping` và `FlowHandlerAdapter` | Khởi động flow đăng ký |
| `POST /registration?execution=e1s1` | Các thành phần Web Flow | Tiếp tục flow từ state hiện hành |
| `GET /health` | Controller hoặc endpoint quản trị | Kiểm tra trạng thái dịch vụ |

`e1s1` là ví dụ minh họa về **execution key**. Giá trị thực tế do SWF phát sinh và không nên được dựng thủ công trong ứng dụng.

**Điều cần nhớ:** `DispatcherServlet` không tự hiểu file định nghĩa flow XML, không trực tiếp thực thi transition và không tự lưu state của wizard. Những việc này được giao cho các thành phần SWF thông qua cơ chế mở rộng chuẩn của Spring MVC.

## 2. Chuỗi xử lý request: MVC gặp Web Flow

### 2.1. Các thành phần tham gia

| Thành phần | Trách nhiệm chính |
|---|---|
| **Servlet container** (Tomcat, Jetty, ...) | Ánh xạ HTTP request tới `DispatcherServlet` theo servlet mapping |
| **DispatcherServlet** | Tìm handler, chọn `HandlerAdapter` và điều phối request/response |
| **HandlerMapping** của MVC | Tìm handler cho `@RequestMapping`, view controller hoặc handler khác |
| **FlowHandlerMapping** | Đối chiếu đường dẫn request với **flow ID** trong `FlowDefinitionRegistry` |
| **FlowHandlerAdapter** | Kết nối cơ chế xử lý request của MVC với `FlowExecutor` |
| **FlowDefinitionRegistry** | Đăng ký và tìm định nghĩa các flow theo ID |
| **FlowExecutor** | Khởi động hoặc tiếp tục flow execution; xử lý state và transition |
| **MvcViewFactoryCreator / ViewResolver** | Kết nối view của SWF với cách resolve/render view trong MVC |
| **FlowExecutionRepository** và cơ chế lưu trữ liên quan | Lưu/khôi phục trạng thái thực thi theo cấu hình SWF |

Các tên lớp Spring Web Flow quan trọng trong cấu hình là `org.springframework.webflow.mvc.servlet.FlowHandlerMapping`, `org.springframework.webflow.mvc.servlet.FlowHandlerAdapter` và `org.springframework.webflow.mvc.builder.MvcViewFactoryCreator`.

### 2.2. Sơ đồ xử lý

~~~mermaid
flowchart TD
    B["Trình duyệt: GET/POST /registration"] --> C["Servlet container"]
    C --> D["DispatcherServlet"]
    D --> HM{"Chọn HandlerMapping"}
    HM -->|"URL khớp flow"| FM["FlowHandlerMapping"]
    HM -->|"URL khớp controller"| MC["Spring MVC Controller"]
    FM --> FH["FlowHandler"]
    FH --> FA["FlowHandlerAdapter"]
    FA --> FE["FlowExecutor: launch hoặc resume"]
    FE --> ST["State / event / transition"]
    ST --> VW["View của flow qua MVC view infrastructure"]
    MC --> V2["MVC View / ResponseBody"]
    VW --> RESP["HTTP Response"]
    V2 --> RESP
~~~

Sơ đồ diễn giải trách nhiệm giữa các thành phần, không thể hiện đầy đủ tất cả lớp nội bộ và lời gọi framework. Về mặt lập trình MVC, `DispatcherServlet` chọn handler thông qua `HandlerMapping` rồi nhờ một `HandlerAdapter` tương thích thực thi handler đó.

### 2.3. Lần truy cập đầu tiên: khởi động flow

Giả sử flow có ID `registration` và đã được đăng ký trong `FlowDefinitionRegistry`.

1. Trình duyệt gửi `GET /registration` tới ứng dụng.
2. Servlet container chuyển request cho `DispatcherServlet`.
3. `FlowHandlerMapping` nhận diện path phù hợp với flow ID `registration` và cung cấp handler để xử lý flow.
4. `DispatcherServlet` chọn `FlowHandlerAdapter`; adapter làm việc với `FlowExecutor` để **khởi động flow execution**.
5. Flow vào state đầu tiên, ví dụ `view-state` `enterEmail`.
6. Hệ thống render view `registration/enter-email` bằng cơ chế view của SWF/MVC. Trang chứa URL cho request tiếp theo gắn với flow execution hiện tại.

Nếu URL không tương ứng với controller hay flow nào, request thường đi theo cơ chế không tìm thấy handler của MVC. Việc flow XML đã tồn tại trên đĩa **không đủ** để bảo đảm đường dẫn web đã được đăng ký đúng.

### 2.4. Request tiếp theo: tiếp tục flow

Từ trang form, người dùng chọn `Tiếp tục` và gửi:

~~~http
POST /registration?execution=e1s1 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId_next=&email=learner%40example.org
~~~

Đây là request minh họa, phụ thuộc cách trang render tên nút và mã hóa form. SWF dùng thông tin **flow execution** từ request để khôi phục đúng execution, nhận event ID `next`, thực hiện form binding/validation theo cấu hình và chọn transition ở state hiện tại.

Sau khi chuyển sang state kế tiếp, flow có thể render view mới mà không cần thêm một URL controller tương ứng cho từng bước. State ID `review` không đồng nghĩa phải có endpoint `/registration/review` riêng.

Khi flow kết thúc, `end-state` hoặc `FlowHandler` có thể quyết định view/redirect của kết quả tùy định nghĩa và cấu hình. Request đến flow đã kết thúc, flow đã hết hạn hoặc execution key không hợp lệ có thể dẫn đến xử lý lỗi thay vì tự động tạo lại trạng thái cũ.

## 3. Cấu hình tích hợp Spring MVC bằng XML

Một cấu hình minh họa theo phong cách **Spring MVC XML + Spring Web Flow** đặt trong web application context của `DispatcherServlet` như sau. Ví dụ sử dụng namespace `webflow-config` quen thuộc trong các phiên bản Web Flow hỗ trợ XML; cần chọn phiên bản Spring MVC, Spring Web Flow và Servlet API tương thích khi áp dụng.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:mvc="http://www.springframework.org/schema/mvc"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/mvc
           http://www.springframework.org/schema/mvc/spring-mvc.xsd
           http://www.springframework.org/schema/webflow-config
           http://www.springframework.org/schema/webflow-config/spring-webflow-config-2.0.xsd">

    <!-- Spring MVC vẫn xử lý các @Controller thông thường. -->
    <mvc:annotation-driven />

    <!-- View resolver dùng cho JSP của ví dụ. -->
    <bean id="viewResolver"
          class="org.springframework.web.servlet.view.InternalResourceViewResolver">
        <property name="prefix" value="/WEB-INF/views/" />
        <property name="suffix" value=".jsp" />
    </bean>

    <!-- Tích hợp việc dựng view của SWF với MVC ViewResolver. -->
    <bean id="mvcViewFactoryCreator"
          class="org.springframework.webflow.mvc.builder.MvcViewFactoryCreator">
        <property name="viewResolvers">
            <list>
                <ref bean="viewResolver" />
            </list>
        </property>
    </bean>

    <webflow:flow-builder-services id="flowBuilderServices"
                                   view-factory-creator="mvcViewFactoryCreator" />

    <!-- Đăng ký ID của flow và file định nghĩa tương ứng. -->
    <webflow:flow-registry id="flowRegistry"
                           flow-builder-services="flowBuilderServices">
        <webflow:flow-location id="registration"
                               path="/WEB-INF/flows/registration/registration-flow.xml" />
    </webflow:flow-registry>

    <!-- Bộ máy quản lý các flow execution. -->
    <webflow:flow-executor id="flowExecutor" />

    <!-- Spring MVC tìm handler cho URL của flow. -->
    <bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
        <property name="flowRegistry" ref="flowRegistry" />
        <property name="order" value="-1" />
    </bean>

    <!-- Spring MVC giao request của flow cho FlowExecutor. -->
    <bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
        <property name="flowExecutor" ref="flowExecutor" />
    </bean>
</beans>
~~~

Cấu hình này truyền tải bốn mối nối quan trọng:

1. **`flowRegistry`** biết ID flow và nơi đọc định nghĩa XML.
2. **`flowExecutor`** là bộ máy xử lý flow execution.
3. **`FlowHandlerMapping`** đưa các URL của flow vào quy trình chọn handler của `DispatcherServlet`.
4. **`FlowHandlerAdapter`** kết nối handler đó với `FlowExecutor`, còn **`MvcViewFactoryCreator`** phối hợp cách tạo view với `ViewResolver` của Spring MVC.

Các bean nghiệp vụ và view template sử dụng trong flow cần được ứng dụng khai báo riêng. `<mvc:annotation-driven/>` hỗ trợ MVC controller, không tự thay thế những bean tích hợp Web Flow.

### 3.1. Vị trí của cấu hình trong ứng dụng

Với ứng dụng Servlet truyền thống, các bean MVC/Web Flow trên thường thuộc **web application context** mà `DispatcherServlet` truy cập được. Ứng dụng có thể khởi tạo context qua `web.xml` hoặc thông qua Java initializer.

Ví dụ về servlet mapping trong `web.xml`:

~~~xml
<servlet>
    <servlet-name>app</servlet-name>
    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
    <load-on-startup>1</load-on-startup>
</servlet>

<servlet-mapping>
    <servlet-name>app</servlet-name>
    <url-pattern>/</url-pattern>
</servlet-mapping>
~~~

Với cấu hình theo quy ước của Spring MVC truyền thống, servlet tên `app` tìm file cấu hình tương ứng (ví dụ `/WEB-INF/app-servlet.xml`), trừ khi ứng dụng chỉ định `contextConfigLocation` hoặc cơ chế khởi tạo khác. Trong ứng dụng Java config/Spring Boot, cách tạo `DispatcherServlet` và ApplicationContext sẽ khác; các thành phần tích hợp Web Flow vẫn cần được đăng ký trong context phù hợp.

**Phân biệt `/` và `/*`:** dùng `/` làm mapping mặc định thường phù hợp với Spring MVC vì còn cho phép các cơ chế khác xử lý request theo quy tắc servlet mapping. Ánh xạ `/*` có thể khiến request forward tới JSP bị bắt lại bởi `DispatcherServlet` và gây lỗi render view nếu không cấu hình bổ sung.

### 3.2. Đăng ký nhiều flow

Một ứng dụng có thể đăng ký các luồng độc lập với ID khác nhau, chẳng hạn `registration`, `checkout`, `changePassword`:

~~~xml
<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location id="registration"
                           path="/WEB-INF/flows/registration/registration-flow.xml" />
    <webflow:flow-location id="checkout"
                           path="/WEB-INF/flows/checkout/checkout-flow.xml" />
    <webflow:flow-location id="changePassword"
                           path="/WEB-INF/flows/change-password/change-password-flow.xml" />
</webflow:flow-registry>
~~~

Đây là đoạn **thay thế bean registry ở ví dụ trước**, không phải một registry thứ hai để thêm vào cùng file cấu hình. URL bên ngoài chịu ảnh hưởng của context path, servlet mapping và flow ID. Kiểm tra URL thực tế thay vì giả định mọi ứng dụng đều dùng đường dẫn gốc như nhau.

## 4. Flow XML được DispatcherServlet kích hoạt như thế nào?

File được đăng ký ở `/WEB-INF/flows/registration/registration-flow.xml` có thể mô tả wizard tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <var name="signup" class="com.example.registration.SignupForm" />

    <view-state id="enterEmail"
                view="registration/enter-email"
                model="signup">
        <transition on="next" to="review"
                    bind="true" validate="true" />
        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>

    <view-state id="review" view="registration/review">
        <transition on="back" to="enterEmail" />
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="completed" view="registration/completed" />
    <end-state id="cancelled" />
</flow>
~~~

`SignupForm` là lớp model do dự án định nghĩa, ví dụ có field `email` cùng getter/setter và quy tắc validation. Ví dụ trên chỉ minh họa trình tự, không gọi service ghi tài khoản thật; trong ứng dụng thực tế nên thêm `action-state` để kiểm tra và ghi dữ liệu trước khi kết thúc.

Khi bắt đầu flow, SWF khởi tạo model `signup` và dùng tên view `registration/enter-email`. Với `InternalResourceViewResolver` ở trên, tên view đó tương ứng đường dẫn JSP `/WEB-INF/views/registration/enter-email.jsp`. View này có thể sử dụng Spring Form tags:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="signup">
    <label for="email">Email</label>
    <form:input path="email" id="email" />
    <form:errors path="email" cssClass="error" />

    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel">Hủy</button>
</form:form>
~~~

`${flowExecutionUrl}` là biến URL thực thi do Web Flow cung cấp cho view. Không thay nó bằng URL cố định `/registration`, vì URL do SWF render có thể kèm execution key dùng để tiếp tục đúng phiên luồng. Nếu đã cấu hình CSRF protection, form còn phải truyền CSRF token theo cơ chế của ứng dụng; đây là ví dụ tối giản.

Khi người dùng nhấn `Tiếp tục`, request có field tên `_eventId_next`. SWF nhận event `next` tại `enterEmail`, binding `email` vào model `signup` rồi kiểm tra validation. Nếu hợp lệ, transition đi tới `review`. Khi nhấn `Quay lại` ở màn hình review, model vẫn được giữ trong flow để hiển thị giá trị trước đó.

`DispatcherServlet` không cần định nghĩa một controller riêng cho `enterEmail`, `review` hoặc `completed`: các state đó nằm trong định nghĩa flow, còn view được resolve thông qua cơ chế MVC đã tích hợp.

## 5. Phối hợp giữa @Controller và FlowHandlerMapping

Trong dự án thực, Web Flow thường chỉ phục vụ một phần giao diện. Các endpoint REST, trang danh mục và trang quản trị vẫn có thể dùng Spring MVC controller bình thường.

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {

    @GetMapping
    public String list(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
~~~

`ProductController` trên là ví dụ rút gọn; `productService` cần được inject và các import Spring MVC cần có trong mã thật. Endpoint `/products` do MVC xử lý, trong khi `/registration` được `FlowHandlerMapping` xử lý khi flow ID đó đã được đăng ký.

### 5.1. Thứ tự HandlerMapping và trùng URL

Spring MVC có thể tìm nhiều handler mapping. Mỗi mapping có thứ tự ưu tiên, thường được kiểm soát bằng thuộc tính `order`: **giá trị nhỏ hơn có ưu tiên cao hơn**.

Trong XML ví dụ, `FlowHandlerMapping` có `order=-1` để ưu tiên flow phù hợp trước các mapping thông thường. Đây là lựa chọn triển khai, không phải quy tắc cố định cho mọi dự án. Nếu cùng một path `/registration` vừa được controller xử lý, vừa trỏ tới flow ID `registration`, handler mapping có ưu tiên cao hơn có thể nhận request và tạo ra hành vi không mong muốn.

Tránh trùng lặp namespace URL:

| Đường dẫn | Đề xuất sở hữu |
|---|---|
| `/registration` | Flow `registration` |
| `/products` | MVC `@Controller` |
| `/api/**` | MVC REST controllers |
| `/assets/**` | Resource handler / static resources |

Không nên cố dùng `@GetMapping("/registration")` để khởi động một flow đã được ánh xạ trực tiếp bằng `FlowHandlerMapping`, trừ khi ứng dụng cố ý xây dựng cơ chế chuyển hướng rõ ràng. Nếu cần đặt flow sau tiền tố như `/flows/registration`, hãy thiết kế URL mapping và flow ID phù hợp theo API/cấu hình đang dùng; chỉ thay URL trên giao diện chưa đủ để đổi quy tắc tra cứu flow.

### 5.2. Thay ViewResolver có ảnh hưởng tới flow không?

Có. `MvcViewFactoryCreator` liên kết hệ thống view của Web Flow với Spring MVC. Nếu chuyển ứng dụng từ JSP sang Thymeleaf hoặc dùng nhiều resolver, phải bảo đảm tên view trong `view-state` có thể được resolver phù hợp xử lý. Ngoài template, cần kiểm tra cách biểu mẫu gửi `_eventId` và URL thực thi flow, khả năng binding/validation và thông báo lỗi.

`DispatcherServlet` giải quyết đường đi của request; **view factory và ViewResolver** giải quyết cách hiển thị màn hình sau khi state đã được xác định. Nếu handler mapping hoạt động nhưng trang không render, hãy kiểm tra phần view thay vì sửa flow ID ngay.

## 6. Scope, session và execution URL trong hệ thống MVC

Spring MVC controller thường làm việc theo **một HTTP request**. Một Web Flow lại có thể trải qua nhiều request và giữ model giữa các bước. SWF quản lý state thông qua cơ chế **flow execution**, có thể sử dụng session/repository theo cấu hình.

| Loại dữ liệu | Phạm vi sử dụng | Ví dụ |
|---|---|---|
| MVC request attributes / `Model` | Dữ liệu cần cho một lần render hoặc xử lý MVC | Danh sách sản phẩm trong một request |
| `requestScope` của SWF | Dữ liệu tạm trong một lần xử lý request của flow | Giá trị trung gian cần dùng ngay |
| `viewScope` | Dữ liệu gắn với một view-state đang hoạt động | Lựa chọn tạm chỉ thuộc màn hình |
| `flowScope` | Dữ liệu trong một flow execution | `signup` của wizard đăng ký |
| `conversationScope` | Dữ liệu ở phạm vi conversation của flow | Context cần dùng trong một chuỗi flow/subflow |
| HTTP session | Phiên HTTP do servlet container quản lý | Dữ liệu phiên; có thể liên quan kho lưu flow theo cấu hình |

`flowScope` và HTTP `session` không đồng nghĩa: không nên tự suy ra mọi biến trong flow đều là session attribute có thể lấy trực tiếp bằng `HttpSession.getAttribute(...)`. Repository chịu trách nhiệm lưu execution và có thể sử dụng chiến lược snapshot, serialization hoặc chế độ lưu khác tùy phiên bản/cấu hình.

### 6.1. Dùng flowExecutionUrl đúng cách

Trang do flow render thường nhận URL thực thi hiện tại, ví dụ `${flowExecutionUrl}`. Hãy dùng URL đó trong form/link để SWF có thể nhận đúng execution và event. Không tự ghép key giả, không đặt key cố định và không xem nó như cơ chế xác thực thay cho kiểm tra quyền.

Với event từ nút bấm:

~~~html
<form action="${flowExecutionUrl}" method="post">
    <input type="email" name="email">
    <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>
~~~

Khi thực tế kết hợp JSP/Spring Form/Thymeleaf, template engine cần render placeholder URL theo cú pháp phù hợp. Nút điều hướng không nhất thiết tạo endpoint mới: nó chỉ phát event cho state hiện tại.

### 6.2. Hết hạn, quay lại và nhiều tab

Từ góc nhìn trình duyệt, flow có thể thất bại vì session timeout, execution key không còn hợp lệ, request cũ sau thao tác Back hoặc nhiều tab sử dụng các snapshot khác nhau. Hành vi phụ thuộc cách cấu hình execution repository và giới hạn lưu trữ.

Ứng dụng nên thiết kế đường phục hồi rõ ràng: thông báo phiên thao tác đã hết hạn, chuyển về điểm bắt đầu an toàn hoặc cho phép nhập lại thông tin. Không khôi phục giao dịch quan trọng bằng cách chỉ phát lại POST cũ; nếu một thao tác ghi có thể bị gửi hai lần, service cần có kiểm tra trùng và idempotency thích hợp.

Spring Security, session management và CSRF filter thường chạy trước khi request đến `DispatcherServlet` trong filter chain. Khi tích hợp Web Flow, cần bảo đảm các flow URL cũng chịu cùng chính sách xác thực, phân quyền và CSRF như các endpoint MVC quan trọng.

## 7. Những lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân có thể | Điểm kiểm tra |
|---|---|---|
| `GET /registration` trả 404 | Flow ID không được đăng ký, flow file sai path, servlet mapping không nhận URL | `flowRegistry`, `FlowHandlerMapping`, servlet mapping và context path |
| Request vào controller thay vì flow | Trùng path và thứ tự `HandlerMapping` | `order`, các `@RequestMapping` |
| Không có adapter xử lý flow handler | Chưa khai báo `FlowHandlerAdapter` hoặc bean ở sai ApplicationContext | Adapter và `flowExecutor` |
| Trang báo không tìm thấy view | Không khớp tên view hoặc resolver thiếu/cấu hình sai | `MvcViewFactoryCreator`, `viewResolver`, template path |
| Nhấn Next nhưng không chuyển state | Thiếu/sai `_eventId`, form gửi sai URL hoặc validation thất bại | Request payload, `flowExecutionUrl` và transition `on` |
| Dữ liệu form mất ở bước kế tiếp | Model không binding đúng hoặc đặt sai scope | `model`, `bind`, `validate` và `flowScope` |
| Back/refresh gây lỗi thực thi | Execution key cũ, timeout, snapshot không khả dụng | Repository, session và chính sách phục hồi |
| POST bị HTTP 403 | CSRF token thiếu hoặc quyền truy cập bị từ chối | Security filter chain và token |
| Action ném exception | Lỗi logic/service hoặc tình trạng hệ thống ngoài | Exception handler, log, transaction và cơ chế phục hồi |
| Cấu hình chạy ở bản này nhưng lỗi ở bản khác | Không tương thích Spring MVC/Web Flow/Servlet namespace | Phiên bản thư viện, `javax.servlet` hoặc `jakarta.servlet` |

Ba điểm cần phân biệt khi chẩn đoán:

- **Không tìm được flow**: xảy ra trước khi chạy state, liên quan đường dẫn/mapping/registry.
- **Đã tìm flow nhưng không render được màn hình**: liên quan view factory, resolver và view template.
- **Đã render nhưng điều hướng sai khi submit**: liên quan execution URL, event ID, binding/validation và transition.

Không quy mọi lỗi HTTP 500 thành trạng thái `failure` của flow. Exception từ tầng Java cần được xử lý qua cơ chế exception handling phù hợp; một transition `on="failure"` chỉ chạy khi action thực sự phát outcome `failure`.

## 8. Kiểm thử đường đi qua DispatcherServlet

Cần kiểm thử cả phần **MVC integration** và phần **logic bên trong flow**. Một bộ kiểm thử state/transition ở cấp SWF không chứng minh URL ngoài đã được `DispatcherServlet` map tới flow đúng; ngược lại, kiểm tra GET trả 200 chưa chứng minh binding/validation và luồng state hoạt động đúng.

### 8.1. Kiểm thử integration qua HTTP

Có thể dùng `MockMvc` nếu cấu hình test dựng đủ MVC context và bean Web Flow, hoặc dùng kiểm thử tích hợp chạy servlet container. Các bước kiểm tra:

1. `GET /registration` khởi động flow và render trang `enterEmail`.
2. Lấy **flow execution URL/key thực tế** từ response của server hoặc mô hình request test; giữ cookie/session cần thiết giữa các request.
3. `POST` form với event `next` và dữ liệu hợp lệ; xác minh trang `review` được render.
4. Gửi dữ liệu không hợp lệ; xác minh lỗi binding/validation và flow còn ở trang nhập.
5. Gửi event `back` rồi `confirm`; xác minh dữ liệu của model, state đích và kết quả kết thúc.
6. Thử flow URL không hợp lệ, execution đã hết hạn, nhiều tab và request gửi lại.
7. Thử các endpoint `@Controller` thông thường để xác nhận việc tích hợp Web Flow không làm thay đổi handler mapping của chúng.

Chú ý: `MockMvcBuilders.standaloneSetup(controller)` chỉ dựng controller được truyền vào; nó không tự cung cấp `FlowHandlerMapping`, `FlowHandlerAdapter` và `FlowExecutor`. Với kiểm thử end-to-end flow, cần nạp application context có cấu hình Web Flow thực sự.

### 8.2. Kiểm thử định nghĩa flow độc lập

Có thể dùng các tiện ích kiểm thử của Spring Web Flow (ví dụ nhóm lớp kiểm thử `AbstractXmlFlowExecutionTests` ở các phiên bản cung cấp API này) để xác minh state ban đầu, event và transition mà không phải đi qua toàn bộ HTTP stack. Với flow đăng ký, kiểm tra cả event `next`, `back`, `cancel`, form validation và `end-state`.

### 8.3. Ma trận kiểm thử khuyến nghị

| Tình huống | Kỳ vọng |
|---|---|
| Flow ID `registration` có trong registry | GET URL được điều phối tới flow |
| URL controller `/products` | Controller MVC vẫn hoạt động |
| Event `next` với email hợp lệ | Chuyển sang `review` |
| Event `next` với email không hợp lệ | Trở lại `enterEmail` cùng lỗi validation |
| Event `cancel` dù form đang thiếu dữ liệu | Có thể kết thúc theo transition `bind="false"` |
| Execution key thiếu/sai ở request tiếp tục | Ứng dụng xử lý theo quy tắc lỗi/khởi tạo đã cấu hình |
| Session timeout khi đang ở bước giữa | Có thông báo và lộ trình phục hồi an toàn |
| POST không có CSRF token khi CSRF đang bật | Bị từ chối theo chính sách bảo mật |
| Path trùng với `@Controller` | Handler được chọn đúng theo thiết kế ưu tiên |

## 9. Thực hành: thêm flow vào ứng dụng MVC đang chạy

Giả sử ứng dụng Spring MVC hiện đã có trang danh mục sản phẩm. Bài tập là bổ sung wizard `registration` mà không làm thay đổi controller cũ:

1. Đăng ký `FlowDefinitionRegistry` với flow ID `registration` trỏ tới file định nghĩa flow thực tế.
2. Cấu hình `FlowExecutor`, `FlowHandlerMapping` và `FlowHandlerAdapter` trong application context mà `DispatcherServlet` có thể thấy.
3. Thiết lập `MvcViewFactoryCreator` kết nối với `ViewResolver` hiện tại.
4. Tạo flow có `enterEmail` → `review` → `completed`, cho phép quay lại và hủy bằng event.
5. Thực hiện form binding và validation cho model `signup`, dùng flow execution URL khi submit.
6. Kiểm thử lần đầu GET, các lần POST tiếp tục, timeout, URL sai và endpoint MVC sẵn có.

Trước khi áp dụng cấu hình mẫu vào dự án thực, xác minh phiên bản Spring Framework, Web Flow, Servlet/Jakarta API, cơ chế khai báo bean và view technology đang sử dụng. Những phiên bản dùng `javax.servlet` và những phiên bản dùng `jakarta.servlet` cần bộ thư viện tương thích; Spring Boot cũng không mặc nhiên đăng ký toàn bộ bean tích hợp Web Flow chỉ vì đã thêm dependency.

**Kết quả học tập:** Khi nhìn vào một request nhiều bước, bạn có thể xác định ranh giới trách nhiệm: **`DispatcherServlet` nhận request và chọn handler; `FlowHandlerMapping` nhận diện flow; `FlowHandlerAdapter` kết nối request với `FlowExecutor`; các state/transition quyết định bước đi; hệ thống view của MVC render màn hình; repository giữ thông tin cần thiết để tiếp tục flow.** Nắm đúng chuỗi này giúp triển khai flow song song với controller thông thường và tìm đúng nguyên nhân khi xảy ra lỗi điều hướng, phiên hoặc view.
