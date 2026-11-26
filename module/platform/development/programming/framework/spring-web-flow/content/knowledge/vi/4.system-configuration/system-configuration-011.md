# Cấu hình Web Flow trong ứng dụng Spring Boot

Trong chương **Cấu hình hệ thống**, bài này trình bày cách đưa Spring Web Flow vào một ứng dụng Spring Boot để điều khiển những hành trình web có nhiều bước. Mục tiêu của module **SPRING_WEB_FLOW** là mô hình hóa luồng bằng state, event, transition và subflow; kết hợp form binding, validation, scope, phiên làm việc và Spring MVC để luồng có thể kiểm thử và phục hồi khi gặp lỗi.

## 1. Khi nào nên dùng Spring Web Flow?

Spring MVC xử lý tốt các request độc lập như xem danh sách, mở chi tiết hoặc lưu một biểu mẫu đơn. Khi một nghiệp vụ cần nhiều bước có quan hệ với nhau — chẳng hạn đăng ký tài khoản, đặt chỗ, mở hồ sơ hoặc thanh toán — controller thường bắt đầu phải giữ trạng thái trung gian, quyết định bước tiếp theo và xử lý nút quay lại. Nếu các quyết định này nằm rải rác trong nhiều controller, việc kiểm soát thứ tự và kiểm thử hành trình sẽ khó hơn.

Spring Web Flow (SWF) biểu diễn hành trình đó thành một **flow definition**. Một flow có các state, nhận event từ người dùng, đi theo transition và có thể gọi một subflow. SWF quản lý vòng đời của lần thực thi flow và cung cấp các scope để lưu dữ liệu tạm trong đúng khoảng thời gian.

Ví dụ: quy trình đăng ký có các bước nhập thông tin cá nhân, nhập thông tin liên hệ, xem lại và xác nhận. Người dùng có thể quay lại bước trước, sửa dữ liệu, hoặc gặp lỗi validation mà vẫn ở đúng bước hiện tại.

Chọn SWF khi thứ tự các bước là một phần rõ ràng của nghiệp vụ và cần giữ ngữ cảnh giữa các request. Với CRUD đơn giản hoặc một biểu mẫu độc lập, controller Spring MVC thường gọn hơn.

## 2. Các thành phần khi tích hợp với Spring Boot

Một request đi vào ứng dụng qua `DispatcherServlet`. `FlowHandlerMapping` nhận diện URL thuộc về flow nào; `FlowHandlerAdapter` chuyển request cho `FlowExecutor`. Executor tra định nghĩa trong `FlowDefinitionRegistry`, tiếp tục hoặc khởi tạo một lần thực thi flow, rồi trả về view hoặc kết quả kết thúc. Các view được Spring MVC phân giải qua `ViewResolver` phù hợp với công nghệ giao diện đang dùng.

| Thành phần | Vai trò |
|---|---|
| `FlowDefinitionRegistry` | Đăng ký và tìm các flow definition theo flow ID. |
| `FlowExecutor` | Khởi tạo, tiếp tục và kết thúc một flow execution. |
| `FlowHandlerMapping` | Ánh xạ URL đến flow tương ứng. |
| `FlowHandlerAdapter` | Chuyển request/response Spring MVC cho SWF xử lý. |
| `FlowBuilderServices` | Cung cấp dịch vụ cho flow builder, ví dụ cách tạo view và validation. |
| `FlowExecutionRepository` | Lưu trạng thái và snapshot của flow execution để request sau có thể tiếp tục. |

Luồng xử lý khái quát:

```text
Browser
  -> DispatcherServlet
  -> FlowHandlerMapping
  -> FlowHandlerAdapter
  -> FlowExecutor
  -> FlowDefinitionRegistry
  -> state / transition / subflow
  -> ViewResolver và view
```

Flow ID thường được suy ra từ vị trí file trong registry. Ví dụ `flows/registration/registration-flow.xml` thường được đăng ký với ID `registration`, nên URL khởi đầu có thể là `/registration`. Hãy xác nhận ID thực tế qua registry thay vì đoán từ tên URL.

## 3. Khai báo dependency và bố trí tài nguyên

Spring Boot cung cấp Spring MVC qua `spring-boot-starter-web`. Thêm thư viện Spring Web Flow trực tiếp vào ứng dụng; nếu dùng Bean Validation thì thêm starter validation tương ứng.

Ví dụ Maven (phiên bản SWF được đặt tại property để dễ quản lý):

```xml
<properties>
    <spring-webflow.version><!-- phiên bản tương thích với stack Spring của dự án --></spring-webflow.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.webflow</groupId>
        <artifactId>spring-webflow</artifactId>
        <version>${spring-webflow.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Không chọn phiên bản SWF chỉ vì Maven tải được artifact. Hãy đối chiếu phiên bản SWF với phiên bản Spring Framework, Spring MVC, Java và Servlet API mà phiên bản Spring Boot đang quản lý. Để Boot quản lý các dependency Spring qua BOM/parent của dự án; tránh tự nâng riêng Spring Framework để chữa một xung đột tương thích.

Có thể tổ chức tài nguyên như sau:

```text
src/main/java/com/example/config/WebFlowConfiguration.java
src/main/resources/flows/
  registration/
    registration-flow.xml
  address/
    address-flow.xml
src/main/resources/templates/
  registration/
    personal.html
    contact.html
    review.html
```

Đường dẫn và tên view trong flow phải khớp với quy ước của `ViewResolver` trong ứng dụng. Với Thymeleaf, các view như `registration/personal` thường được phân giải thành template `templates/registration/personal.html` khi cấu hình resolver theo mặc định của starter.

## 4. Đăng ký flow và kết nối với Spring MVC

Tạo một lớp cấu hình kế thừa `AbstractFlowConfiguration`. Registry quét các file có hậu tố `-flow.xml` dưới thư mục `classpath:/flows`. Executor sử dụng registry này. Hai bean MVC kết nối URL với executor.

```java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.execution.FlowExecutor;
import org.springframework.webflow.mvc.servlet.FlowHandlerAdapter;
import org.springframework.webflow.mvc.servlet.FlowHandlerMapping;

@Configuration
public class WebFlowConfiguration extends AbstractFlowConfiguration {

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
                .setBasePath("classpath:/flows")
                .addFlowLocationPattern("**/*-flow.xml")
                .build();
    }

    @Bean
    public FlowExecutor flowExecutor() {
        return getFlowExecutorBuilder(flowRegistry()).build();
    }

    @Bean
    public FlowHandlerMapping flowHandlerMapping() {
        FlowHandlerMapping mapping = new FlowHandlerMapping();
        mapping.setOrder(-1);
        mapping.setFlowRegistry(flowRegistry());
        return mapping;
    }

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter() {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor());
        adapter.setSaveOutputToFlashScopeOnRedirect(true);
        return adapter;
    }
}
```

`setBasePath` chỉ định thư mục gốc để tìm flow definition; `addFlowLocationPattern` chọn các file cần đăng ký. Dùng `classpath:/flows` phù hợp với tài nguyên đóng gói trong ứng dụng Boot. Nếu đặt flow ở vị trí khác, hãy thay base path và pattern đồng bộ với cấu trúc thực tế.

`FlowHandlerMapping` được đặt order `-1` trong ví dụ để xử lý các URL flow trước mapping request thông thường của Spring MVC. Nếu ứng dụng có URL trùng nhau, cần rà soát thứ tự và quy ước URL để một request chỉ được xử lý bởi handler dự kiến.

Không thêm `@EnableWebMvc` chỉ để bật SWF trong ứng dụng Boot. Annotation này chuyển quyền cấu hình MVC sang ứng dụng và có thể làm mất một phần auto-configuration của Boot. Chỉ dùng khi chủ động muốn tự cấu hình toàn bộ MVC.

### 4.1. Cấu hình view factory khi cần

Các state thường trả về tên view logic, ví dụ `registration/personal`. SWF cần biết cách chuyển tên đó thành view Spring MVC. Nếu view mặc định không được phân giải đúng, cấu hình `MvcViewFactoryCreator` với các `ViewResolver` đang dùng trong ứng dụng và cung cấp nó qua `FlowBuilderServices`.

```java
import java.util.List;
import org.springframework.web.servlet.ViewResolver;
import org.springframework.webflow.config.FlowBuilderServices;
import org.springframework.webflow.mvc.builder.MvcViewFactoryCreator;

@Bean
public MvcViewFactoryCreator mvcViewFactoryCreator(List<ViewResolver> viewResolvers) {
    MvcViewFactoryCreator creator = new MvcViewFactoryCreator();
    creator.setViewResolvers(viewResolvers);
    creator.setUseSpringBeanBinding(true);
    return creator;
}

@Bean
public FlowBuilderServices flowBuilderServices(
        MvcViewFactoryCreator mvcViewFactoryCreator) {
    return getFlowBuilderServicesBuilder()
            .setViewFactoryCreator(mvcViewFactoryCreator)
            .build();
}
```

Đây là phần cấu hình bổ sung khi cần tích hợp rõ ràng với resolver của ứng dụng; chỉ đăng ký một cấu hình view factory thống nhất. Nếu dùng JSP, Thymeleaf hoặc một công nghệ view khác, bảo đảm resolver tương ứng đã được cấu hình và tên view trong flow phù hợp với resolver đó.

## 5. Định nghĩa một flow nhiều bước

Tạo `src/main/resources/flows/registration/registration-flow.xml`. Ví dụ dưới đây mô hình hóa việc nhập thông tin, xem lại và xác nhận. Lớp `RegistrationForm` là JavaBean có getter/setter cho các thuộc tính được bind.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="registration" class="com.example.registration.RegistrationForm"/>

    <view-state id="personal" view="registration/personal" model="registration">
        <transition on="continue" to="contact">
            <evaluate expression="registrationValidator.validate(registration, messageContext)"/>
        </transition>
    </view-state>

    <view-state id="contact" view="registration/contact" model="registration">
        <transition on="back" to="personal"/>
        <transition on="continue" to="review">
            <evaluate expression="registrationValidator.validate(registration, messageContext)"/>
        </transition>
    </view-state>

    <view-state id="review" view="registration/review">
        <transition on="back" to="contact"/>
        <transition on="confirm" to="completed">
            <evaluate expression="registrationService.submit(registration)"/>
        </transition>
    </view-state>

    <end-state id="completed"
               view="externalRedirect:contextRelative:/registration/done"/>
</flow>
```

`view-state` hiển thị một màn hình và chờ event. `transition` mô tả event nào dẫn đến state nào. `end-state` kết thúc flow. Biểu thức `evaluate` gọi bean Spring theo tên bean; vì vậy `registrationValidator` và `registrationService` phải được đăng ký trong application context.

Ở ví dụ này, thao tác ghi dữ liệu chỉ diễn ra khi người dùng xác nhận. Service nên thực hiện thao tác ghi trong transaction phù hợp và xử lý xác nhận lặp một cách an toàn. Không đặt một thao tác thanh toán hoặc tạo đơn không idempotent trong `on-entry` của view vì state có thể được vào lại khi người dùng quay lại hoặc flow được khôi phục.

### 5.1. Gửi event từ form

View gửi form đến URL thực thi flow mà SWF cung cấp trong model. Tên nút submit theo dạng `_eventId_<tên-event>` để SWF nhận diện transition.

Ví dụ với Thymeleaf:

```html
<form th:action="${flowExecutionUrl}" method="post" th:object="${registration}">
    <label for="fullName">Họ tên</label>
    <input id="fullName" type="text" th:field="*{fullName}">

    <button type="submit" name="_eventId_continue">Tiếp tục</button>
</form>
```

Khi người dùng nhấn nút, request gửi event `continue`; SWF bind các trường form vào model của state rồi tìm transition có event tương ứng. Với nút quay lại, dùng `name="_eventId_back"`. Không tự ghép flow execution key bằng chuỗi cố định; luôn dùng `flowExecutionUrl` do lần thực thi hiện tại cung cấp.

## 6. Form binding và validation

Khai báo `model` trên `view-state` cho biết object nhận dữ liệu form. Các trường gửi lên cần khớp tên thuộc tính của object và chỉ nên bind những thuộc tính người dùng được phép thay đổi. Với dữ liệu nhạy cảm hoặc thuộc tính do server quyết định, không đưa chúng vào form binding.

Có thể kiểm tra dữ liệu trong validator và thêm thông báo vào `MessageContext`. Ví dụ:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Component;

@Component("registrationValidator")
public class RegistrationValidator {

    public void validate(RegistrationForm form, MessageContext messages) {
        if (form.getFullName() == null || form.getFullName().isBlank()) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("fullName")
                    .defaultText("Vui lòng nhập họ tên.")
                    .build());
        }
    }
}
```

Trong flow XML, biểu thức gọi validator trước khi transition sang bước tiếp theo. Khi có lỗi, thông báo gắn với field hoặc form được đưa về view để người dùng sửa. Với dự án dùng Bean Validation, có thể dùng các annotation như `@NotBlank`, `@Email`, `@Size` trên form object và tích hợp validator tương thích với phiên bản SWF đang dùng.

Validation ở giao diện giúp phản hồi sớm; service vẫn phải kiểm tra các bất biến nghiệp vụ và quyền truy cập trước khi ghi dữ liệu. Không xem dữ liệu đã đi qua một bước của flow là dữ liệu đáng tin cậy.

## 7. Chọn scope và quản lý phiên

Chọn scope theo thời gian dữ liệu cần tồn tại:

| Scope | Vòng đời và cách dùng |
|---|---|
| `requestScope` | Chỉ tồn tại trong một request; dùng cho dữ liệu xử lý tạm thời. |
| `flashScope` | Dùng để chuyển dữ liệu qua một lần redirect. |
| `viewScope` | Gắn với một view-state; phù hợp cho dữ liệu riêng của màn hình hiện tại. |
| `flowScope` | Tồn tại trong một flow execution; phù hợp cho form object và dữ liệu trung gian của hành trình. |
| `conversationScope` | Chia sẻ dữ liệu giữa flow cha và subflow trong cùng conversation; dùng khi thật sự cần chia sẻ. |

Ví dụ, `registration` trong flow ở trên được khai báo bằng `<var>` và tồn tại trong flow scope. Một object chỉ phục vụ màn hình xác nhận có thể đặt trong view scope. Dữ liệu cần chuyển sau redirect có thể đặt trong flash scope.

Flow execution thường được lưu qua repository gắn với HTTP session. Vì vậy cần kiểm tra cấu hình cookie/session timeout, hành vi khi session hết hạn và cách lưu session khi triển khai nhiều instance. Với cluster, session cần được chia sẻ hoặc định tuyến nhất quán; các object được lưu phải có khả năng serialize nếu cơ chế session yêu cầu. Tránh đưa entity đang được quản lý bởi persistence context, stream, request object hoặc object lớn vào scope dài hạn.

SWF có các scope của riêng flow; không nhầm `flowScope` hoặc `conversationScope` với HTTP session. Khi cần truy cập session bên ngoài, thao tác qua API của `ExternalContext` hoặc dịch vụ quản lý session của ứng dụng, đồng thời giới hạn dữ liệu lưu trong session và thời gian tồn tại của dữ liệu.

## 8. Tách quy trình thành subflow

Khi nhiều hành trình dùng chung một nhóm bước, có thể tách nhóm đó thành flow con. Ví dụ flow đăng ký gọi subflow `address` để thu thập địa chỉ:

```xml
<subflow-state id="addressStep" subflow="address">
    <input name="customerId" value="flowScope.customerId"/>
    <transition on="addressCompleted" to="review"/>
</subflow-state>
```

Flow con có thể trả dữ liệu khi kết thúc:

```xml
<end-state id="addressCompleted">
    <output name="address" value="flowScope.address"/>
</end-state>
```

Input làm rõ dữ liệu flow cha truyền cho flow con; output làm rõ kết quả flow con trả về. Giữ hợp đồng input/output nhỏ và ổn định để có thể kiểm thử subflow độc lập. Dữ liệu được chia sẻ qua conversation scope chỉ nên dùng khi thực sự cần chia sẻ trực tiếp giữa cha và con.

## 9. Xử lý lỗi và phục hồi flow

Phân loại lỗi theo nơi có thể xử lý:

- **Lỗi nhập liệu:** thêm message vào `MessageContext`, giữ người dùng ở view hiện tại và hiển thị lỗi gần trường tương ứng.
- **Lỗi nghiệp vụ có thể khắc phục:** chuyển đến state giải thích hoặc cho phép người dùng sửa dữ liệu, tùy quy tắc nghiệp vụ.
- **Lỗi hệ thống:** ghi log có correlation ID, trả về màn hình lỗi an toàn và không để lộ stack trace hay dữ liệu nhạy cảm.
- **Session hết hạn hoặc flow execution không còn hợp lệ:** hướng dẫn người dùng bắt đầu lại flow và khôi phục dữ liệu từ nguồn bền vững nếu nghiệp vụ cho phép.

Có thể khai báo global transition cho ngoại lệ đã xác định và có cách xử lý chung:

```xml
<global-transitions>
    <transition on-exception="java.lang.IllegalArgumentException" to="invalidRequest"/>
</global-transitions>

<view-state id="invalidRequest" view="errors/invalid-request">
    <transition on="restart" to="personal"/>
</view-state>
```

Chỉ ánh xạ các ngoại lệ mà ứng dụng hiểu rõ sang state phù hợp. Không bắt mọi `Exception` rồi tiếp tục một flow với dữ liệu có thể đã ở trạng thái không nhất quán. Với lỗi không thể phục hồi, kết thúc flow và yêu cầu khởi tạo một execution mới.

Các request tiếp tục flow thường mang theo flow execution key. Dùng URL được SWF tạo ra để tiếp tục đúng execution; không tự lưu key vào nơi dùng chung giữa người dùng. Cần kiểm thử hành vi nút Back, refresh, gửi form lặp và mở cùng flow ở nhiều tab vì chúng có thể tạo ra các request hoặc execution khác nhau. Không giả định việc quay lại state sẽ tự hoàn tác side effect đã ghi vào cơ sở dữ liệu.

## 10. Bảo mật khi dùng flow

- Giữ CSRF protection của Spring Security. Form POST của flow phải gửi CSRF token theo cách tích hợp với template engine đang dùng.
- Áp dụng authorization cho URL flow và kiểm tra quyền trong service ở mỗi thao tác nhạy cảm. Flow execution key không thay thế xác thực hoặc phân quyền.
- Chỉ bind các trường người dùng được phép sửa; không bind trực tiếp `role`, `ownerId`, giá tiền đã tính hoặc trạng thái phê duyệt từ request.
- Không đưa thông tin bí mật vào URL, event name hoặc thông báo lỗi. Không ghi toàn bộ form/session vào log.
- Khi xác nhận một nghiệp vụ tạo dữ liệu hoặc thanh toán, dùng transaction, kiểm tra quyền và cơ chế chống xử lý trùng ở service/domain layer.

## 11. Kiểm thử cấu hình và hành trình

Kiểm thử ở nhiều lớp để phát hiện lỗi cấu hình sớm:

1. **Khởi động application context:** xác nhận các bean registry, executor, handler mapping và handler adapter được tạo thành công; không có xung đột bean hoặc dependency.
2. **Kiểm tra registry:** xác nhận flow ID dự kiến tồn tại và các flow XML đều được parse.
3. **Kiểm thử flow execution:** lần lượt gửi event hợp lệ, event không hợp lệ, quay lại, đi tiếp, kết thúc và gọi subflow; xác nhận state hiện tại và output.
4. **Kiểm thử validation:** dữ liệu sai phải tạo message và không cho nghiệp vụ đi qua bước cần điều kiện hợp lệ; dữ liệu đúng phải tiếp tục được.
5. **Kiểm thử MVC bằng MockMvc hoặc kiểm thử tích hợp tương đương:** GET URL flow, submit form theo execution URL, kiểm tra view/redirect và session giữa các request.
6. **Kiểm thử phục hồi:** session hết hạn, refresh, gửi event lặp, mở nhiều tab và lỗi từ service; xác nhận hành vi đúng với yêu cầu nghiệp vụ.

Spring Web Flow có test support cho flow execution ở cấp định nghĩa. Có thể kết hợp test support đó với MockMvc để kiểm tra cả logic state lẫn đường đi HTTP. Validator và service vẫn nên có unit test riêng để kiểm tra quy tắc nghiệp vụ mà không cần khởi tạo flow.

## 12. Sự cố thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| URL flow trả về 404 | Flow chưa được registry quét; sai base path, pattern, flow ID hoặc URL. |
| Request bị controller xử lý | Thứ tự `FlowHandlerMapping` hoặc URL mapping đang xung đột. |
| Không tìm thấy view | Tên view trong state không khớp template hoặc `ViewResolver`; cấu hình `FlowBuilderServices` chưa dùng resolver mong muốn. |
| Không chuyển state sau submit | Tên `_eventId_...` không khớp event trong transition; form action không dùng `flowExecutionUrl`; validation đang có lỗi. |
| Dữ liệu biến mất giữa các bước | Object nằm sai scope, flow execution key không được gửi lại hoặc session đã hết hạn. |
| Lỗi class/dependency khi khởi động | Phiên bản SWF không tương thích với Spring Framework, Java hoặc Servlet API của ứng dụng. |
| Xác nhận bị chạy hai lần | Người dùng gửi lặp hoặc refresh; thao tác nghiệp vụ thiếu idempotency ở service/domain layer. |

## 13. Checklist cấu hình

- [ ] Phiên bản `spring-webflow` tương thích với Spring Boot và Spring Framework của dự án.
- [ ] Flow XML nằm dưới base path và khớp location pattern của registry.
- [ ] Registry tìm được mọi flow ID cần dùng.
- [ ] `FlowExecutor`, `FlowHandlerMapping` và `FlowHandlerAdapter` được đăng ký trong application context.
- [ ] Thứ tự handler mapping không xung đột với controller.
- [ ] View name, template và `ViewResolver` thống nhất.
- [ ] Form dùng `flowExecutionUrl`; tên event khớp transition.
- [ ] Binding chỉ cho phép cập nhật thuộc tính hợp lệ; validation có cả ở flow và service.
- [ ] Dữ liệu được đặt đúng scope; session timeout và triển khai nhiều instance đã được xem xét.
- [ ] Side effect có transaction và xử lý request lặp an toàn.
- [ ] CSRF, authentication và authorization vẫn được áp dụng.
- [ ] Đã kiểm thử đường đi thành công, validation lỗi, back, subflow, session hết hạn và lỗi service.

## 14. Kết luận

Cấu hình Spring Web Flow trong Spring Boot gồm ba việc chính: đăng ký flow definition, tạo executor và kết nối executor với Spring MVC qua handler mapping/adapter. Khi các bean này hoạt động, flow XML mô tả state, event, transition và subflow; view gửi event qua execution URL; scope giữ dữ liệu đúng vòng đời. Validation, quản lý session, bảo mật và kiểm thử cần được thiết kế cùng flow để hành trình nhiều bước có thể tiếp tục an toàn qua nhiều request.
