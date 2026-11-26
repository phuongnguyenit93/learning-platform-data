# Tạo view-state và view tương ứng

**Spring Web Flow (SWF)** giúp mô hình hóa một hành trình web có nhiều màn hình bằng `state`, `event` và `transition`. Ví dụ, người dùng nhập thông tin, bấm **Tiếp tục** để xem lại, bấm **Quay lại** để sửa hoặc bấm **Hoàn tất** để kết thúc. Nếu chỉ dùng controller thông thường, lập trình viên phải tự ghép các URL và trạng thái; với Web Flow, sơ đồ điều hướng được khai báo rõ ràng.

Bài thuộc chương **Flow đầu tiên** của module `SPRING_WEB_FLOW`. Bạn sẽ tạo hai `view-state` kết nối tới hai trang HTML, thêm hai `end-state`, đưa một JavaBean vào flow và cấu hình Spring MVC để các view có thể được hiển thị. Đây cũng là nền tảng để học tiếp form binding, validation, flow scope, HTTP session, subflow, kiểm thử và phục hồi flow khi có lỗi.

Ví dụ sử dụng **Java 17, Spring Framework 6.x, Spring Web Flow 3.x, Spring MVC và Thymeleaf**. Với Web Flow 2.5/Spring 5 hoặc Web Flow 4/Spring 7, cần đối chiếu đúng các phiên bản Java, Servlet API và cách cấu hình tương ứng. Nội dung tập trung vào **hiển thị và điều hướng**, chưa có database hay thao tác nghiệp vụ thật.

## 1. Mục tiêu và kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **flow ID**, **state ID**, **view ID** và **file template**.
2. Viết `<view-state>` với các thuộc tính `id`, `view` và `model`.
3. Đặt file Thymeleaf đúng nơi `ViewResolver` tìm thấy.
4. Gửi event từ một nút submit bằng tên `_eventId_next`, `_eventId_back` hoặc `_eventId_finish`.
5. Giữ object Java qua hai màn hình bằng biến flow, không lưu vào singleton controller.
6. Kết nối `FlowRegistry`, `FlowExecutor`, `FlowHandlerMapping` và `FlowHandlerAdapter` với Spring MVC.
7. Nhận biết các lỗi flow URL, view resolution, event và binding thường gặp.
8. Tự kiểm tra hành trình bằng trình duyệt và flow test.

Đường đi thành công cần quan sát:

~~~text
GET /signup
  -> enterDetails: nhập họ tên và email
  -> nhấn Tiếp tục (_eventId_next)
  -> review: xem lại thông tin đã nhập
  -> nhấn Hoàn tất (_eventId_finish)
  -> completed: màn hình kết thúc
~~~

Tại `review`, người dùng có thể nhấn **Quay lại** để sửa. Tại `enterDetails`, có thể nhấn **Hủy** để kết thúc qua một nhánh khác.

## 2. View-state khác view ở điểm nào?

Một `view-state` là **trạng thái của flow** mà khi vào, engine hiển thị một view rồi chờ request tiếp theo. `view` là **tên logic của giao diện** được Spring MVC `ViewResolver` ánh xạ tới HTML/JSP/Thymeleaf hoặc công nghệ view khác.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Flow definition** | `signup-flow.xml` | Định nghĩa cả hành trình |
| **Flow ID** | `signup` | Tên để tìm và bắt đầu flow |
| **View-state ID** | `enterDetails` | State đang chờ tương tác |
| **View ID** | `signup/details` | Tên logic mà view resolver nhận |
| **Template vật lý** | `templates/signup/details.html` | File giao diện được render |
| **Event** | `next` | Tín hiệu gửi từ request |
| **Transition** | `on="next" to="review"` | Chỉ định state đích |
| **End-state** | `completed` | Kết thúc execution |

Điểm dễ nhầm nhất: **`id="enterDetails"` không buộc view phải tên `enterDetails.html`**. Bạn có thể đặt `view="signup/details"`, rồi để Thymeleaf tìm file `classpath:/templates/signup/details.html`.

~~~mermaid
flowchart LR
    A["Flow ID: signup"] --> B["view-state: enterDetails"]
    B --> C["View ID: signup/details"]
    C --> D["Thymeleaf ViewResolver"]
    D --> E["templates/signup/details.html"]
~~~

Một flow definition có thể chứa nhiều view-state dùng các view khác nhau; một view cũng có thể được dùng lại bởi nhiều state nếu bạn chủ động chọn. Tuy nhiên, dùng tên view rõ ràng ngay từ đầu giúp dễ debug.

### 2.1. Sơ đồ điều hướng của bài

~~~mermaid
stateDiagram-v2
    [*] --> enterDetails
    enterDetails --> review: next
    enterDetails --> cancelled: cancel
    review --> enterDetails: back
    review --> completed: finish
    completed --> [*]
    cancelled --> [*]
~~~

Hai state `enterDetails` và `review` là **view-state**; `completed` và `cancelled` là **end-state**. Trong ví dụ, không có `action-state` vì chưa cần truy vấn hoặc lưu dữ liệu; chỉ cần điều hướng và hiển thị.

## 3. Tổ chức file cho flow đầu tiên

Gợi ý cấu trúc của một dự án Spring Boot có Web Flow:

~~~text
src/main/java/com/example/firstflow/
  FirstFlowApplication.java
  SignupDraft.java
  config/SignupWebFlowConfig.java

src/main/resources/
  flows/signup/signup-flow.xml
  templates/signup/details.html
  templates/signup/review.html
  templates/signup/completed.html
  templates/signup/cancelled.html
  application.properties
~~~

Nếu ứng dụng sử dụng Spring Boot 3.x đã cấu hình Java toolchain, plugin và Maven Central, phần Gradle dependencies minh họa như sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.webflow:spring-webflow:3.0.2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn trên **không phải file Gradle hoàn chỉnh**. Version Web Flow phải phù hợp thế hệ Spring Framework; ví dụ này dùng SWF 3.x với Spring 6/Jakarta. Trước khi triển khai, kiểm tra version đã được resolve, bản vá và servlet container thực tế. Spring Boot thêm hạ tầng Spring MVC/Thymeleaf, nhưng **không tự đăng ký toàn bộ các bean điều phối Web Flow**.

## 4. Tạo object giữ dữ liệu giữa hai view

Một HTTP request không giữ biến local của request trước. Để xem lại dữ liệu ở màn hình thứ hai, ta khai báo một JavaBean:

~~~java
package com.example.firstflow;

import java.io.Serializable;

public class SignupDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    private String fullName;
    private String email;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Lớp này có constructor không tham số ngầm định, getter/setter public và các property đơn giản để Web Flow/Spring binder có thể làm việc. Việc triển khai `Serializable` phù hợp với các cơ chế có thể snapshot/serialize flow state; nếu dùng repository khác, kiểm tra chính sách thực tế.

Không đặt bản nháp vào một field mutable của singleton controller hoặc singleton Spring service. Một server xử lý nhiều người dùng và nhiều tab: trạng thái của một execution nên được Web Flow quản lý.

## 5. Viết XML flow đầu tiên

Tạo file `src/main/resources/flows/signup/signup-flow.xml` với nội dung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <!-- Một SignupDraft cho từng flow execution -->
    <var name="signup" class="com.example.firstflow.SignupDraft"/>

    <!-- Màn hình thứ nhất -->
    <view-state id="enterDetails"
                view="signup/details"
                model="signup">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>

        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <!-- Màn hình thứ hai -->
    <view-state id="review" view="signup/review">
        <transition on="back" to="enterDetails"/>
        <transition on="finish" to="completed"/>
    </view-state>

    <!-- Hai kết quả kết thúc -->
    <end-state id="completed" view="signup/completed"/>
    <end-state id="cancelled" view="signup/cancelled"/>
</flow>
~~~

Giải nghĩa các khai báo:

| Đoạn XML | Ý nghĩa |
| --- | --- |
| `<flow>` | Root của một định nghĩa flow |
| `<var name="signup".../>` | Tạo object `SignupDraft`, dùng làm model xuyên các state |
| `<view-state id="enterDetails">` | Màn hình đầu và nơi nhận event |
| `view="signup/details"` | View ID cần có resolver/template tương ứng |
| `model="signup"` | Dùng object `signup` để bind form |
| `<binder>` | Chỉ cho phép các property được liệt kê |
| `<transition on="next" to="review"/>` | Khi nhận event `next`, chuyển sang `review` |
| `bind="false"` | Không bind form khi muốn hủy |
| `<end-state id="completed".../>` | Kết thúc flow và render kết quả |

Flow chọn state đầu theo cấu hình initial state. Trong XML đơn giản này, **`enterDetails` là state đầu** theo thứ tự khai báo. Nếu định nghĩa flow lớn hơn cần initial state tường minh, kiểm tra schema của dòng Web Flow đang dùng.

### 5.1. Thuộc tính `view` có bắt buộc không?

Web Flow có quy ước suy ra view ID từ state ID khi `view` không được chỉ định. Ví dụ:

~~~xml
<view-state id="enterDetails"/>
~~~

có thể trông đợi view logic tên `enterDetails`; nó không tự đồng nghĩa với file `signup/details.html`. Đối với bài đầu tiên, hãy **luôn ghi rõ `view="signup/details"`** để tránh nhầm tên state với tên file giao diện.

### 5.2. Binding và validation là hai trách nhiệm khác nhau

`model="signup"` yêu cầu binder đưa form field vào object. `<binding property="email" required="true"/>` là quy tắc binding; nó **không đảm bảo email đúng định dạng hay người gửi có quyền thực hiện hành động nghiệp vụ**. Khi mở rộng dự án, cần validator, kiểm tra server-side và bảo vệ CSRF nếu form sử dụng HTTP session.

Vì binder chỉ nêu `fullName` và `email`, những field khác do client tự thêm vào không nên được nhận để thay đổi dữ liệu đặc quyền. Không dùng object JPA nhiều property nhạy cảm trực tiếp làm form model nếu chưa thiết kế whitelist rõ ràng.

## 6. Tạo bốn view tương ứng bằng Thymeleaf

Với Spring Boot/Thymeleaf, logical view `signup/details` thường được giải tới `classpath:/templates/signup/details.html`. Chúng ta sẽ tạo bốn template tương ứng với hai `view-state` và hai `end-state`.

### 6.1. `templates/signup/details.html` — màn hình nhập

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Nhập thông tin</title>
</head>
<body>
    <h1>Bước 1: Nhập thông tin</h1>

    <form method="post"
          th:action="${flowExecutionUrl}"
          th:object="${signup}">
        <label for="fullName">Họ và tên</label>
        <input id="fullName" type="text"
               th:field="*{fullName}" maxlength="120" required>

        <label for="email">Email</label>
        <input id="email" type="email"
               th:field="*{email}" maxlength="200" required>

        <button type="submit" name="_eventId_next" value="next">
            Tiếp tục
        </button>
        <button type="submit" name="_eventId_cancel" value="cancel"
                formnovalidate>
            Hủy
        </button>
    </form>
</body>
</html>
~~~

Ý nghĩa các thuộc tính:

- `th:action="${flowExecutionUrl}"` lấy URL tiếp tục **execution hiện tại** do Web Flow cung cấp; không cố định form action vào controller tùy ý.
- `th:object="${signup}"` dùng object trong flow, `th:field="*{fullName}"` và `th:field="*{email}"` giúp binder nhận đúng property.
- `name="_eventId_next"` là quy ước gửi event `next`; `name="_eventId_cancel"` gửi event `cancel`.
- `formnovalidate` giúp nút Hủy không bị kiểm tra HTML5 phía trình duyệt chặn lại; trong XML còn có `bind="false"` ở transition hủy.

Nếu Spring Security đang bật CSRF, các POST phải có token hợp lệ. Thymeleaf và Spring Security có thể tự chèn hidden CSRF token qua `RequestDataValueProcessor` khi dùng `th:action`; kiểm tra HTML đã render và cấu hình thực tế, không tắt CSRF chỉ để ví dụ chạy được. Lỗi validation trên server cần được render vào view; bản tối thiểu trên chưa có vùng hiển thị lỗi.

### 6.2. `templates/signup/review.html` — màn hình xem lại

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Xem lại thông tin</title>
</head>
<body>
    <h1>Bước 2: Xem lại</h1>

    <dl>
        <dt>Họ và tên</dt>
        <dd th:text="${signup.fullName}">Họ tên đã nhập</dd>
        <dt>Email</dt>
        <dd th:text="${signup.email}">Email đã nhập</dd>
    </dl>

    <form method="post" th:action="${flowExecutionUrl}">
        <button type="submit" name="_eventId_back" value="back">
            Quay lại
        </button>
        <button type="submit" name="_eventId_finish" value="finish">
            Hoàn tất
        </button>
    </form>
</body>
</html>
~~~

`review` là view-state chỉ **đọc lại bản nháp**, nên không cần thêm `model` hoặc binder mới. Trong tích hợp Spring MVC/Web Flow phù hợp, biến flow `signup` được cung cấp cho view. Dùng `th:text` để escape nội dung người dùng nhập; không render dữ liệu form dưới dạng HTML thô.

Nhấn `back` đưa execution về `enterDetails`. Đối tượng `SignupDraft` vẫn còn trong flow, nên các input `th:field` có thể hiển thị lại tên và email đã nhập.

### 6.3. `templates/signup/completed.html` — kết thúc thành công

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Hoàn tất</title></head>
<body>
    <h1>Đã hoàn tất flow giới thiệu</h1>
    <p>Ví dụ chưa ghi dữ liệu vào database.</p>
    <a th:href="@{/signup}">Bắt đầu flow mới</a>
</body>
</html>
~~~

### 6.4. `templates/signup/cancelled.html` — hủy

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Đã hủy</title></head>
<body>
    <h1>Đã hủy thao tác</h1>
    <p>Flow kết thúc mà không tạo đăng ký.</p>
    <a th:href="@{/signup}">Bắt đầu lại</a>
</body>
</html>
~~~

Hai `end-state` có thể có view để hiển thị kết quả ngay khi kết thúc, nhưng sau đó execution có thể không còn. Một biên lai hoặc đăng ký muốn xem lại về sau phải lấy từ database qua endpoint khác có kiểm tra quyền. Đừng dùng execution URL cũ làm link xem dữ liệu bền vững.

### 6.5. View-state có bắt buộc dùng Thymeleaf không?

Không. `view-state` chỉ trỏ tới **logical view**, còn Spring MVC `ViewResolver` có thể chọn Thymeleaf, JSP hoặc một công nghệ được tích hợp tương ứng. Nếu dùng JSP, ánh xạ logical ID tới `/WEB-INF/jsp/...jsp` bằng một resolver phù hợp; nếu dùng JSF, cần cấu hình Spring Faces/JSF đúng thế hệ. Cấu trúc state/event/transition vẫn được định nghĩa trong Web Flow.

## 7. Khởi động Spring Boot

Tạo class ứng dụng đặt ở package cha của `config` để Spring quét được cấu hình Web Flow:

~~~java
package com.example.firstflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FirstFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirstFlowApplication.class, args);
    }
}
~~~

`@SpringBootApplication` cung cấp cấu hình Spring Boot cơ bản; **không** tự biến mọi XML có đuôi `-flow.xml` thành một endpoint. Bạn cần đăng ký hạ tầng Web Flow.

## 8. Đăng ký flow với Spring MVC

Để URL `/signup` mở được flow, Spring MVC cần:

1. `FlowDefinitionRegistry` để nạp và định danh `signup-flow.xml`.
2. `FlowExecutor` để bắt đầu và tiếp tục flow execution.
3. `FlowHandlerMapping` để tìm flow tương ứng với request.
4. `FlowHandlerAdapter` để Spring MVC gọi executor.
5. `MvcViewFactoryCreator` dùng đúng `ViewResolver` khi render các view-state.

~~~mermaid
sequenceDiagram
    actor User as Trình duyệt
    participant MVC as DispatcherServlet
    participant Map as FlowHandlerMapping
    participant Adapter as FlowHandlerAdapter
    participant Engine as FlowExecutor
    participant Registry as FlowRegistry
    participant View as ViewResolver
    User->>MVC: GET /signup
    MVC->>Map: Tìm handler
    Map-->>MVC: signup flow handler
    MVC->>Adapter: Thực thi request
    Adapter->>Engine: Bắt đầu signup flow
    Engine->>Registry: Tải flow signup
    Registry-->>Engine: XML state machine
    Engine->>View: Render signup/details
    View-->>User: HTML màn hình 1
~~~

Ví dụ Java Config trên Spring Web Flow 3.x:

~~~java
package com.example.firstflow.config;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.ViewResolver;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.engine.builder.support.FlowBuilderServices;
import org.springframework.webflow.executor.FlowExecutor;
import org.springframework.webflow.mvc.builder.MvcViewFactoryCreator;
import org.springframework.webflow.mvc.servlet.FlowHandlerAdapter;
import org.springframework.webflow.mvc.servlet.FlowHandlerMapping;

@Configuration
public class SignupWebFlowConfig extends AbstractFlowConfiguration {
    private final ViewResolver thymeleafViewResolver;

    public SignupWebFlowConfig(
            @Qualifier("thymeleafViewResolver") ViewResolver resolver) {
        this.thymeleafViewResolver = resolver;
    }

    @Bean
    public MvcViewFactoryCreator signupViewFactoryCreator() {
        MvcViewFactoryCreator creator = new MvcViewFactoryCreator();
        creator.setViewResolvers(List.of(thymeleafViewResolver));
        creator.setUseSpringBeanBinding(true);
        return creator;
    }

    @Bean
    public FlowBuilderServices flowBuilderServices() {
        return getFlowBuilderServicesBuilder()
            .setViewFactoryCreator(signupViewFactoryCreator())
            .build();
    }

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder(flowBuilderServices())
            .addFlowLocation(
                "classpath:/flows/signup/signup-flow.xml", "signup")
            .build();
    }

    @Bean
    public FlowExecutor flowExecutor() {
        return getFlowExecutorBuilder(flowRegistry()).build();
    }

    @Bean
    public FlowHandlerMapping flowHandlerMapping() {
        FlowHandlerMapping mapping = new FlowHandlerMapping();
        mapping.setFlowRegistry(flowRegistry());
        mapping.setOrder(0);
        return mapping;
    }

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter() {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor());
        return adapter;
    }
}
~~~

Đây là cấu hình **minh họa theo API của Web Flow**, không chứa toàn bộ security, metrics, exception handling và session repository. Nếu bean Thymeleaf resolver của dự án có tên khác, `@Qualifier("thymeleafViewResolver")` cần điều chỉnh; đừng mặc định mọi ứng dụng đều expose cùng tên bean. Tại runtime, phải xác minh `MvcViewFactoryCreator` thực sự dùng Thymeleaf resolver.

| Bean | Vì sao cần? | Dấu hiệu khi cấu hình sai |
| --- | --- | --- |
| `FlowBuilderServices` | Cung cấp view factory và các service xây flow | View/formatter không dùng như mong đợi |
| `flowRegistry` | Tìm flow definition `signup` | Flow ID không tồn tại |
| `flowExecutor` | Xử lý một execution và event | Không thể khởi tạo/tiếp tục flow |
| `flowHandlerMapping` | Ánh xạ URL tới flow | Truy cập `/signup` nhận 404 hoặc vào handler khác |
| `flowHandlerAdapter` | Tích hợp với `DispatcherServlet` | MVC tìm thấy handler nhưng không thực thi được |
| `signupViewFactoryCreator` | Tạo view Web Flow dựa trên Spring MVC resolver | Sai template/view chưa được render |

**Không tạo thêm controller `@GetMapping("/signup")` để trả `signup/details`** khi muốn Web Flow điều khiển endpoint. Controller trùng URL có thể giành quyền xử lý request, làm state/event không chạy. Hãy xem MVC handler mappings và thứ tự mapping nếu có xung đột.

### 8.1. Flow registry khác view resolver

`addFlowLocation("classpath:/flows/signup/signup-flow.xml", "signup")` chỉ định:

- File XML ở `classpath:/flows/signup/signup-flow.xml`.
- Flow ID đăng ký là `signup`.

Trong khi `view="signup/details"` **không** tìm HTML bên cạnh file XML theo đường dẫn đó. Nó gửi logical view ID cho Spring MVC/Thymeleaf; với prefix/suffix phù hợp, file cần có tại `classpath:/templates/signup/details.html`. Phân biệt được hai đường này sẽ giúp xử lý phần lớn lỗi ở bài đầu tiên.

### 8.2. Đăng ký nhiều flow

Sau này, có thể thêm flow `booking`, `checkout` hoặc `profile` vào cùng registry. Các flow có thể có state ID trùng như `review`, vì mỗi state ID được quản lý trong flow definition tương ứng. Nhưng **flow ID phải phân biệt** để URL và FlowRegistry chọn đúng hành trình.

## 9. Event trong request được ánh xạ tới transition như thế nào?

Khi người dùng bấm nút **Tiếp tục**, form gửi dữ liệu tới `flowExecutionUrl`. Tên button `_eventId_next` giúp Web Flow nhận ra event `next`; engine xem **state hiện tại** có transition `on="next"` hay không.

~~~mermaid
flowchart TD
    A["Trình duyệt submit form details"] --> B["POST flowExecutionUrl"]
    B --> C["Web Flow xác định execution và event next"]
    C --> D["Binding vào SignupDraft"]
    D --> E{"Binding/validation hợp lệ?"}
    E -->|"Không"| F["Giữ view-state enterDetails, hiển thị lỗi"]
    E -->|"Có"| G{"Có transition on=next?"}
    G -->|"Không"| H["Event không hợp lệ, xử lý lỗi theo cấu hình"]
    G -->|"Có"| I["Chuyển tới view-state review"]
    I --> J["ViewResolver render signup/review"]
~~~

### 9.1. Hai cách gửi event thường gặp

**Cách 1 — tên button mang tên event:**

~~~html
<button type="submit" name="_eventId_next">Tiếp tục</button>
~~~

**Cách 2 — một field chung mang giá trị event:**

~~~html
<input type="hidden" name="_eventId" value="next">
<button type="submit">Tiếp tục</button>
~~~

Không dùng hai cách cùng lúc khi không cần thiết; điều đó có thể khiến cách chọn event khó đoán hoặc khác theo request parsing. Với form nhiều nút, cách 1 rất dễ đọc vì mỗi nút nêu rõ event riêng.

### 9.2. Transition là quy tắc trên server

`<transition on="next" to="review"/>` quyết định **chỉ khi state hiện tại là `enterDetails`** và nhận event `next` mới tới `review`. Client không được quyền gửi một tham số `to=completed` rồi buộc flow bỏ qua các bước. Nhưng state graph **không thay thế phân quyền**: nếu sau này nút `finish` thực sự tạo booking, action cần kiểm tra lại quyền người dùng và dữ liệu nghiệp vụ ở server.

### 9.3. Event quay lại khác nút Back của trình duyệt

Khi người dùng bấm nút **Quay lại** trong form `review`, nó gửi event `back`. Web Flow thực hiện transition `review → enterDetails` đã được định nghĩa.

Khi người dùng bấm nút **Back của trình duyệt**, trình duyệt có thể mở một URL/snapshot cũ. Kết quả phụ thuộc flow execution repository, giới hạn snapshot và cấu hình lịch sử. Không thể giả định browser Back luôn tương đương event `back`; cần kiểm thử riêng và thiết kế thông báo nếu execution đã hết hạn.

## 10. Request, flow execution key và redirect

Web Flow thường lưu trạng thái thực thi qua nhiều HTTP request. Một chuỗi minh họa:

~~~text
1. GET  /signup
   -> Bắt đầu execution, render enterDetails

2. POST /signup?execution=e1s1
   body: fullName=An&email=an@example.test&_eventId_next=next
   -> Bind dữ liệu, event next, chuyển tới review

3. GET  /signup?execution=e1s2
   -> Render review (trong cấu hình có redirect)

4. POST /signup?execution=e1s2
   body: _eventId_back=back
   -> Chuyển lại enterDetails
~~~

**Đây chỉ là ví dụ về URL và execution key**. Không hard-code định dạng `e1s1`/`e1s2` hay thứ tự redirect; những chi tiết này phụ thuộc `FlowUrlHandler`, repository, browser và cấu hình Spring MVC của phiên bản đang dùng.

### 10.1. Tại sao phải dùng `flowExecutionUrl`?

`flowExecutionUrl` được Web Flow cung cấp cho view để form tiếp tục **đúng flow execution**. Nếu bạn viết:

~~~html
<!-- Không khuyến nghị khi đang ở giữa flow -->
<form method="post" action="/signup">
~~~

request có thể không chứa execution key đúng; Web Flow có thể coi đó là request khởi tạo flow mới hoặc xử lý khác với ý định. Dùng biểu thức view integration để lấy URL execution, không tự ghép query string từ JavaScript.

### 10.2. Post/Redirect/Get (PRG) giúp gì?

Trong cấu hình phổ biến, Web Flow có thể redirect sau event khi bước tiếp theo là view-state, thay vì để người dùng ở một URL POST. Mô hình PRG giúp refresh màn hình review giảm nguy cơ gửi lại form vừa nhập.

Nhưng **PRG không thay thế idempotency** ở service nếu event `finish` hoặc `confirm` về sau ghi database. Hai request có thể tới đồng thời, một request có thể retry sau mất kết nối hoặc browser quay về execution snapshot cũ. Bảo vệ giao dịch phải nằm ở service/database.

### 10.3. Scope giữ dữ liệu ra sao?

`<var name="signup" class="...SignupDraft"/>` khai báo biến của flow, có thể truy cập trong biểu thức dưới dạng `signup` hoặc `flowScope.signup`. Object được giữ qua các state của cùng execution theo vòng đời `flowScope`, **không tồn tại vĩnh viễn trong database**.

| Phạm vi | Vòng đời tương đối | Có phù hợp cho bài này? |
| --- | --- | --- |
| `requestScope` | Một HTTP request | Dùng cho dữ liệu tạm, không giữ bản nháp qua nhiều bước |
| `viewScope` | Khi một view-state hoạt động | Dữ liệu riêng của màn hình |
| `flowScope` | Một flow execution | **Phù hợp** với `SignupDraft` |
| `conversationScope` | Conversation gồm flow cha/subflow | Chưa cần ở ví dụ cơ bản |
| HTTP `sessionScope` | Toàn phiên HTTP | Không nên dùng thay flowScope cho mỗi bản nháp |

Flow scopes là khái niệm của Web Flow; chúng khác `HttpSession` dù implementation có thể sử dụng session để lưu execution. Một session có thể chứa nhiều execution, vì vậy không lưu `SignupDraft` làm một biến session chung nếu mỗi tab cần hành trình độc lập.

## 11. Quy trình thử nghiệm bằng trình duyệt

Trong dự án đã lắp đặt dependency/config ở trên, chạy ứng dụng bằng cách phù hợp với build system, chẳng hạn `./gradlew bootRun` hoặc `mvn spring-boot:run`. **Các lệnh này là hướng dẫn để người học chạy, không được thực thi khi soạn bài.**

Thử theo thứ tự:

1. Mở `http://localhost:8080/signup`; nếu server cấu hình port/context path khác thì dùng địa chỉ tương ứng.
2. Kiểm tra trang hiển thị “Bước 1: Nhập thông tin”. Nếu 404, chẩn đoán route/FlowRegistry trước, không sửa template.
3. Nhập họ tên `An` và email `an@example.test`; bấm **Tiếp tục**.
4. Kiểm tra màn hình `review` hiển thị đúng họ tên/email; xem URL thực tế và network tab để thấy redirect nếu có.
5. Bấm **Quay lại**; các input ở `enterDetails` vẫn hiển thị dữ liệu cũ.
6. Bấm **Tiếp tục**, sau đó **Hoàn tất**; trình duyệt hiển thị template `completed.html`.
7. Mở một flow mới; ở bước nhập bấm **Hủy** và kiểm tra template `cancelled.html`.
8. Gửi event không tồn tại hoặc không được khai báo ở state hiện tại; flow không được đi tới state tùy ý.
9. Mở hai tab với hai flow executions riêng, nhập hai tên khác nhau; kiểm tra chúng không dùng chung draft.
10. Thử session timeout, refresh và browser Back; quan sát thông báo hoặc hành vi khi execution snapshot cũ không còn.

### 11.1. Dấu hiệu hoàn thành

| Tình huống | Kết quả cần thấy |
| --- | --- |
| GET `/signup` | `enterDetails` và `details.html` |
| Event `next` với dữ liệu hợp lệ | `review` và `review.html` |
| Event `back` từ `review` | `enterDetails` và dữ liệu giữ lại |
| Event `finish` từ `review` | `completed` và template kết thúc |
| Event `cancel` từ `enterDetails` | `cancelled` |
| Event không được định nghĩa | Không chuyển qua state cấm |
| Hai flow executions độc lập | Không trộn object `SignupDraft` |
| Flow execution đã kết thúc | Không được coi URL cũ là biên lai lâu dài |

## 12. Các lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `GET /signup` trả 404 | Không đăng ký flow ID, sai URL hoặc mapping | `flowRegistry`, `flowHandlerMapping`, đường dẫn XML |
| Nạp ứng dụng báo không có flow | Sai `classpath:/flows/...` hoặc XML invalid | File có được đóng gói, namespace/schema |
| Thấy 404 cho HTML/template | View ID không được resolver nhận | `view="signup/details"` và `templates/signup/details.html` |
| `TemplateInputException` | Thymeleaf không tìm thấy/parse template | Resolver prefix/suffix, cú pháp template |
| Bấm Tiếp tục nhưng vẫn ở trang nhập | Binder lỗi, field thiếu, event sai | `_eventId_next`, form submit, binding messages |
| Bấm Hủy mà HTML5 không cho đi | Input `required` đang chặn submit | `formnovalidate` và `bind="false"` |
| Trang review không có tên/email | Không có model hoặc biến không được expose | `<var>`, `model`, `MvcViewFactoryCreator` |
| Bấm Back của trình duyệt bị expired | Repository không còn snapshot | Flow execution repository, session timeout |
| Nút gửi nhưng nhận HTTP 403 | CSRF token không hợp lệ hoặc policy URL | Security filter chain và HTML đã render |
| Hiện hai view không như mong đợi | Trùng route hoặc nhiều ViewResolver | MVC handler mappings, bean config |
| Lỗi `NoClassDefFoundError` liên quan Servlet | Trộn `javax.servlet` và `jakarta.servlet` | Java/Spring/SWF/container dependency tree |
| Dữ liệu ở tab A xuất hiện ở tab B | Lưu state vào singleton hoặc session chung | Scope và cấu trúc bean |

### 12.1. Phân biệt lỗi “flow” với lỗi “view”

Nếu **FlowRegistry không tìm được `signup`**, server chưa đi tới bước render template; sửa `view` sẽ không giải quyết. Ngược lại, nếu flow đã vào `enterDetails` nhưng Thymeleaf không tìm `signup/details`, route và XML có thể đã đúng; cần sửa **view resolution**.

~~~mermaid
flowchart TD
    A["Mở /signup lỗi"] --> B{"FlowHandlerMapping nhận /signup?"}
    B -->|"Không"| C["Kiểm tra URL/FlowRegistry/handler mapping"]
    B -->|"Có"| D{"View-state enterDetails được nạp?"}
    D -->|"Không"| E["Kiểm tra flow XML và state ID"]
    D -->|"Có"| F{"Thymeleaf tìm thấy signup/details?"}
    F -->|"Không"| G["Kiểm tra view resolver và template path"]
    F -->|"Có"| H["Kiểm tra HTML, form action và event"]
~~~

Không thêm một controller `@GetMapping("/signup")` chỉ để trả HTML nếu mục tiêu bài là sử dụng Web Flow; làm như vậy có thể che mất lỗi hạ tầng và bỏ qua state machine.

## 13. Kiểm thử view-state, view và transition

Một bài có flow XML hợp lệ vẫn có thể lỗi khi hiển thị nếu `ViewResolver`, model hoặc URL thực thi không đúng. Vì vậy nên kiểm thử nhiều tầng thay vì chỉ nhìn trạng thái build thành công.

### 13.1. Kiểm thử XML và state machine

Trong một flow test dùng bộ hỗ trợ của Web Flow (ví dụ những lớp thuộc `org.springframework.webflow.test.execution` ở phiên bản tương ứng), kiểm tra:

1. Bắt đầu flow và xác nhận state đầu là `enterDetails`.
2. Gửi event `next` với form dữ liệu hợp lệ và xác nhận state `review`.
3. Gửi event `back` và xác nhận state trở về `enterDetails`.
4. Gửi event `finish` từ `review` và xác nhận flow kết thúc tại `completed`.
5. Khởi động execution khác rồi gửi `cancel`, xác nhận kết thúc tại `cancelled`.
6. Gửi event `finish` từ `enterDetails`; engine không được tùy ý bỏ qua `review`.

Flow test có thể thiết lập context/service giả, cho phép kiểm tra state mà không chạy trình duyệt. Tuy nhiên, nếu **không có MVC ViewResolver thật**, test này chưa chứng minh `signup/details.html` tồn tại hay form HTML gửi đúng event.

### 13.2. Kiểm thử MVC/HTTP integration

Với Spring Boot test dùng `MockMvc` hoặc HTTP client, cần:

- GET `/signup` qua `DispatcherServlet`; kiểm tra status, route và template được render.
- Kiểm tra HTML form có action URL hiện tại và field `_eventId_next`/`_eventId_cancel`.
- POST với đúng execution key và CSRF token nếu filter đang bật; xác minh state/view kế tiếp.
- Kiểm tra giá trị `signup.fullName` và `signup.email` không bị mất khi event `back` được gửi.
- Xác nhận một execution mới không thừa hưởng object của execution trước.

Khi dùng `MockMvc`, cần giữ đúng cookie/session và redirect chain giữa các request. Một POST gửi vào `/signup` nhưng bỏ execution key có thể tạo kết quả khác với thao tác thật của trình duyệt; **hãy lấy URL tiếp tục từ response hoặc cơ chế test của Web Flow**, đừng đoán.

### 13.3. Test thủ công lỗi dữ liệu và bảo mật

| ID | Request/hành động | Kết quả kỳ vọng |
| --- | --- | --- |
| F01 | Mở `/signup` | View nhập liệu xuất hiện |
| F02 | Gửi tên/email đúng qua `next` | View review xuất hiện |
| F03 | Bấm `back` từ review | Trở về form, giữ dữ liệu |
| F04 | Bấm `cancel` ở form trống | Kết thúc dù HTML form chưa hoàn chỉnh |
| F05 | Bấm `finish` ở review | End-state completed |
| F06 | Gửi `finish` ở state nhập | Không đi thẳng tới completed |
| F07 | Gửi field `role=ADMIN` ngoài binder | Không thay đổi property đặc quyền |
| F08 | Gửi email sai cú pháp | Validation server từ chối nếu đã cấu hình validator |
| F09 | Thiếu CSRF khi security bật | Request POST bị chặn theo security policy |
| F10 | Một flow execution hết hạn | Có xử lý lỗi phù hợp, không lộ dữ liệu |
| F11 | Hai tab, hai flow executions | Dữ liệu không trộn giữa các bản nháp |
| F12 | Đổi tên template nhưng không đổi view ID | Chẩn đoán được lỗi view resolution |
| F13 | Xóa flow XML khỏi classpath | Registry báo thiếu flow tại startup hoặc lúc lookup |
| F14 | Refresh và browser Back | Hành vi đúng theo flow repository, không commit lặp |

**Điểm quan trọng:** F08 chỉ đạt khi bạn thực sự bổ sung server-side validation; HTML5 `type="email"` không phải validator đáng tin cậy. F07 có ý nghĩa khi model thật có property nhạy cảm; ví dụ `SignupDraft` ban đầu chưa có `role` nên nó cũng minh họa lý do không đưa property không được bind vào form model.

## 14. Mở rộng: lỗi binding và validation trên màn hình nhập

Khi nhập email sai hoặc bỏ trống tên, mong muốn là **ở lại `enterDetails` và hiển thị lỗi**, không tự chuyển sang `review`. Trong ví dụ đơn giản, `required="true"` trong binder và HTML5 validation giúp phát hiện một số trường hợp. Nhưng validation hoàn chỉnh còn cần logic phía server, chẳng hạn Jakarta Bean Validation (`@NotBlank`, `@Email`) và một validator được Web Flow cấu hình/kích hoạt đúng phiên bản.

Ví dụ annotation cho model thuộc Spring Framework 6/Jakarta:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

// Các annotation này đặt trực tiếp trên property phù hợp của SignupDraft.
@NotBlank
private String fullName;

@NotBlank
@Email
private String email;
~~~

Đây là **trích đoạn field**, không phải class thứ hai đầy đủ. Thêm dependency Bean Validation provider phù hợp rồi kiểm tra việc validation thực sự chạy qua flow binding. Không suy rằng chỉ có annotation là mọi transition sẽ tự bị chặn trong tất cả cấu hình.

Một mẫu render lỗi cho Thymeleaf khi đã cấu hình Spring Bean Binding hỗ trợ `BindingResult`:

~~~html
<p class="field-error" role="alert"
   th:if="${#fields.hasErrors('email')}"
   th:errors="*{email}">
    Email không hợp lệ.
</p>
~~~

Lỗi validation có thể nằm trong `MessageContext` của Web Flow; cách bridge sang `#fields` tùy integration MVC/view. Nếu view không hiển thị gì dù transition không đi tiếp, kiểm tra **binder messages, MessageContext, view factory và template**, không vội giả định validation không chạy.

### 14.1. Vì sao event hủy dùng `bind="false"`?

Nếu người dùng chưa nhập họ tên/email và bấm **Hủy**, request vẫn gửi tới Web Flow. Nếu flow cố bind/validate toàn bộ form, có thể gặp lỗi thiếu field và không tới `cancelled`. Trong XML:

~~~xml
<transition on="cancel" to="cancelled" bind="false"/>
~~~

giúp xử lý hủy bỏ mà không phụ thuộc dữ liệu đang nhập. Khi thêm event `back` ở một view-state có form, bạn có thể cân nhắc `bind="false"` tương tự nếu thao tác đó không cần lưu dữ liệu mới.

### 14.2. Phân biệt validation và authorization

Nếu sau này flow có tác dụng ghi, một giá trị email đúng định dạng chỉ chứng minh input có thể được chấp nhận về mặt dữ liệu; **nó không chứng minh người dùng được phép tạo booking hoặc sửa hồ sơ**. Server phải xác minh danh tính, quyền trên đối tượng và các ràng buộc nghiệp vụ trước commit.

## 15. Bài tập mở rộng có hướng dẫn

### Bài A — đổi tên view mà không đổi state

Yêu cầu: đổi view `signup/details` thành `signup/contact` nhưng giữ state `enterDetails`.

Thực hiện:

1. Sửa đúng thuộc tính `view="signup/contact"` ở XML.
2. Đổi file `details.html` thành `contact.html` trong thư mục template.
3. Giữ nguyên `<transition on="next" to="review"/>`, vì transition phụ thuộc **state ID**, không phụ thuộc tên template.
4. Mở `/signup` và xác minh giao diện mới hiển thị, event `next` vẫn tới `review`.

**Bài học:** view ID là lớp ánh xạ giao diện; state ID là định danh trong state machine.

### Bài B — thêm view-state thứ ba

Mở rộng hành trình:

~~~mermaid
stateDiagram-v2
    [*] --> enterDetails
    enterDetails --> choosePreference: next
    choosePreference --> enterDetails: back
    choosePreference --> review: next
    review --> choosePreference: back
    review --> completed: finish
    completed --> [*]
~~~

Thêm field `preference` vào `SignupDraft`, tạo:

~~~xml
<view-state id="choosePreference"
            view="signup/preference"
            model="signup">
    <binder>
        <binding property="preference"/>
    </binder>
    <transition on="next" to="review"/>
    <transition on="back" to="enterDetails" bind="false"/>
</view-state>
~~~

Sau đó chỉnh transition `next` ở `enterDetails` thành `to="choosePreference"` và transition `back` của `review` về `choosePreference`, rồi tạo template `signup/preference.html` với form gửi event. Trích đoạn trên chỉ minh họa state mới; **đừng thêm nguyên đoạn mà không sửa các transition còn lại**.

### Bài C — hiển thị thông báo đa ngôn ngữ

Thêm `messages.properties` và `messages_vi.properties` chứa các key:

~~~properties
signup.details.title=Nhập thông tin
signup.review.title=Xem lại
signup.completed.message=Đã hoàn tất.
~~~

Dùng Thymeleaf `th:text="#{signup.details.title}"` để hiển thị tiêu đề. Cấu hình `MessageSource`/`LocaleResolver` phù hợp rồi thử `vi-VN` và `en-US`. Để có bản tiếng Anh đúng, cần file tương ứng hoặc fallback rõ ràng; không mặc định rằng toàn bộ UI tự được dịch chỉ nhờ có flow XML.

### Bài D — thêm một action trước khi hoàn tất

Thay transition `finish` trực tiếp bằng một action để kiểm tra dữ liệu hoặc lưu kết quả. Khi bắt đầu lưu vào database, hãy thiết kế service transactional, xử lý exception, idempotency và quyền truy cập; nếu action thất bại phải giữ hành trình ở state an toàn. Đây là điểm mở rộng tự nhiên sang `action-state` và quản lý lỗi của Web Flow.

## 16. Câu hỏi tự kiểm tra

**1. `view-state` có phải file HTML không?** Không. Nó là state trong flow definition; thuộc tính `view` tham chiếu logical view ID, rồi Spring MVC ViewResolver tìm template tương ứng.

**2. Tại sao `enterDetails` có thể render `signup/details.html`?** Vì XML ghi `view="signup/details"` và Thymeleaf resolver ghép prefix/suffix để tìm file.

**3. Nếu đổi tên file `details.html` nhưng không đổi view ID, điều gì xảy ra?** View resolution có thể thất bại; không phải lỗi transition vì state machine vẫn dùng cùng state ID.

**4. `_eventId_next` khác `to="review"` thế nào?** `_eventId_next` là cách client gửi event `next`; `to="review"` là quy tắc server quyết định state đích.

**5. Vì sao không dùng `HttpSession` chung cho mọi bản nháp?** Một session có thể chứa nhiều execution/tab; `flowScope` giữ state theo từng execution và giảm nguy cơ dữ liệu lẫn nhau.

**6. Khi nhấn `back` ở màn hình review, đối tượng Java có bị tạo lại không?** Thông thường không; cùng flow execution giữ object bản nháp. Nếu execution đã hết hạn hoặc một flow mới được bắt đầu, trạng thái có thể khác.

**7. Browser Back có luôn giống event `back` không?** Không; browser history và snapshot/execution repository có semantics riêng, cần kiểm thử.

**8. Tại sao một form gửi đúng event vẫn không chuyển state?** Có thể binding/validation lỗi, không có transition tương ứng, hoặc execution URL không đúng.

**9. End-state có thể hiển thị HTML không?** Có thể, khi cấu hình `view` phù hợp; nhưng sau khi kết thúc không nên xem execution như kho lưu dữ liệu lâu dài.

**10. Có thể ghép một SWF 2.5 JAR vào Spring MVC 6 chỉ vì XML giống nhau không?** Không nên. SWF 2.5 thuộc thế hệ Spring 5/`javax`; Spring 6 dùng nền Jakarta và nên đi với SWF 3.x.

## 17. Checklist tự hoàn thành

- [ ] Có file flow XML ở đúng vị trí được registry nạp.
- [ ] Flow ID là `signup`; state ID `enterDetails`, `review`, `completed`, `cancelled` đúng.
- [ ] Hai `view-state` có logical view ID rõ ràng, khác với state ID khi cần.
- [ ] Có bốn file HTML tương ứng với bốn `view` đã khai báo.
- [ ] `SignupDraft` có getter/setter cho hai property.
- [ ] `<var>` và `model` trỏ tới đúng biến `signup`.
- [ ] Binder chỉ nhận các field được phép chỉnh sửa.
- [ ] Event `next`, `back`, `finish`, `cancel` có transition chính xác.
- [ ] Form dùng `flowExecutionUrl` chứ không tự chế execution key.
- [ ] Thymeleaf resolver được kết nối với `MvcViewFactoryCreator`.
- [ ] `FlowRegistry`, `FlowExecutor` và MVC handler beans khởi tạo đúng.
- [ ] GET `/signup` mở màn hình nhập; POST event tới đúng view kế tiếp.
- [ ] Quay lại giữ dữ liệu; hủy kết thúc mà không ghi dữ liệu.
- [ ] Test lỗi view không tìm thấy, event sai và session timeout.
- [ ] Nếu dùng Spring Security, CSRF được xử lý ở tất cả POST.
- [ ] Đã phân biệt flow hoàn tất với một giao dịch nghiệp vụ thực sự được lưu.

## 18. Tài liệu tham khảo

1. [Spring Web Flow Reference Guide 3.0.2](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — Flow definition, view-state, transitions, model binding, flow variables và Spring MVC integration.
2. [Spring Web Flow 3.0.2 API](https://docs.spring.io/spring-webflow/docs/3.0.2/api/) — các lớp `FlowExecutor`, `FlowHandlerMapping`, `FlowHandlerAdapter` và view factories.
3. [Thymeleaf + Spring Tutorial — Spring Web Flow Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html#spring-webflow-integration) — tích hợp Thymeleaf ViewResolver và Web Flow view rendering.
4. [Spring Framework — View Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html) — cách logical view names được ánh xạ sang view.
5. [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) — binding/conversion khi form model có các field phức tạp.
6. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — chống request giả mạo khi dùng cookie/session.

**Kết luận:** `view-state` xác định **bước tương tác của flow**, thuộc tính `view` xác định **màn hình cần hiển thị**, còn `ViewResolver` tìm **template vật lý**. Khi form gửi event về `flowExecutionUrl`, Web Flow quyết định transition và giữ model đúng phạm vi execution. Nắm chắc ranh giới giữa state, view và template là nền tảng để phát triển flow nhiều bước có validation, subflow, session và kiểm thử đúng cách.
