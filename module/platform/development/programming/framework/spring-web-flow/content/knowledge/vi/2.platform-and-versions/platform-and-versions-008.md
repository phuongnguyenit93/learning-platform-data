# Lựa chọn ứng dụng Servlet và công nghệ giao diện tương thích

Spring Web Flow (SWF) được thiết kế để điều khiển những hành trình web nhiều bước trong **môi trường Servlet**, thường được tích hợp qua **Spring MVC**. Khi chọn nền tảng, cần kiểm tra đồng thời phiên bản Java, Spring Framework, Servlet API, namespace Java EE/Jakarta EE và công nghệ dùng để render view. Một ứng dụng có thể chạy Spring MVC tốt nhưng vẫn không tương thích với SWF nếu trộn nhầm thế hệ `javax.*` và `jakarta.*`, hoặc dùng Servlet container thấp hơn baseline của phiên bản SWF.

Bài học thuộc chương **Nền tảng và phiên bản** của module **SPRING_WEB_FLOW**. Module hướng dẫn mô hình hóa hành trình web bằng state, event, transition và subflow; thực hành form binding, validation, scope/phiên, tích hợp Spring MVC, kiểm thử và phục hồi lỗi. Ta sẽ chọn một nền tảng Servlet phù hợp, sau đó chọn JSP, Thymeleaf, FreeMarker, JSF hay giao diện JavaScript dựa trên cách ứng dụng cần hiển thị và tiếp tục flow.

Các phiên bản trong bài được đối chiếu theo tài liệu chính thức tại ngày **25-11-2026**. Ở thời điểm này, Spring Web Flow **4.0.2** là bản phát hành mới nhất được liệt kê trong kho release của dự án.

## 1. Xác định ứng dụng có phù hợp với Spring Web Flow không

SWF phù hợp khi nghiệp vụ có một hành trình với điểm bắt đầu, các bước trung gian, sự kiện điều hướng và điểm kết thúc rõ ràng. Ví dụ:

- Đặt phòng: tìm phòng → nhập khách → thanh toán → xác nhận.
- Đăng ký khoản vay: thông tin cá nhân → thu nhập → hồ sơ → thẩm định.
- Quy trình onboarding: thông tin tài khoản → xác minh → cấu hình → hoàn tất.
- Checkout: địa chỉ → giao hàng → thanh toán → xác nhận.

SWF không phải thư viện giao diện độc lập. Engine flow tích hợp với **Spring Web MVC**, xử lý request trong Servlet stack và dùng các view để hiển thị từng `view-state`.

~~~mermaid
flowchart TD
    B["Browser / HTTP client"] --> C["Servlet container"]
    C --> D["Spring Security filters"]
    D --> E["DispatcherServlet"]
    E --> F["FlowHandlerMapping"]
    F --> G["FlowHandlerAdapter"]
    G --> H["FlowExecutor"]
    H --> I["FlowRegistry + flow definition"]
    I --> J["state / event / transition"]
    J --> K["ViewFactory + ViewResolver"]
    K --> L["JSP / Thymeleaf / FreeMarker / JSF"]
    L --> B
~~~

Trong chuỗi này:

- Servlet container nhận request và cung cấp Servlet API.
- `DispatcherServlet` điều phối request trong Spring MVC.
- `FlowHandlerMapping` tìm flow phù hợp với URL.
- `FlowHandlerAdapter` chuyển request cho `FlowExecutor`.
- `FlowExecutor` chạy hoặc tiếp tục execution theo flow definition.
- View factory kết hợp với view resolver để render giao diện của state hiện tại.

Vì vậy, lựa chọn nền tảng đầu tiên là một ứng dụng Servlet có thể chạy Spring MVC và Spring Web Flow tương thích. Công nghệ giao diện được chọn sau đó thông qua cơ chế view của Spring MVC hoặc tích hợp chuyên biệt của Spring Faces.

### 1.1. Phân biệt Servlet MVC và Reactive WebFlux

Spring Web Flow dựa trên mô hình request/response của Servlet và tích hợp qua Spring MVC `DispatcherServlet`. Nó không phải adapter có thể cắm trực tiếp vào một ứng dụng Spring WebFlux thuần reactive.

Nếu ứng dụng hiện tại dùng WebFlux làm web stack chính, đừng thêm `spring-webflow` rồi kỳ vọng các flow chạy trực tiếp trên `DispatcherHandler`. Có thể triển khai một ứng dụng Servlet/MVC riêng cho những quy trình cần SWF, hoặc chọn kiến trúc khác cho phần reactive. Việc chạy hai web stack trong cùng một tiến trình cần được thiết kế và kiểm tra riêng theo cách triển khai; không coi đây là cấu hình mặc định.

### 1.2. Khi nào nên dùng controller thông thường?

Không phải mọi trang có nhiều bước đều cần SWF. Một form đơn giản có hai endpoint hoặc một REST API stateless thường có thể dùng controller/service thông thường. SWF hữu ích hơn khi cần quản lý execution, state, event, subflow, scope, validation theo từng view và điều hướng có cấu trúc.

## 2. Kiểm tra baseline của phiên bản trước khi chọn công nghệ

Các thế hệ SWF đi cùng các thế hệ Spring và Servlet khác nhau. Bảng dưới đây tóm tắt các mốc quan trọng:

| Dòng SWF | Java tối thiểu | Spring Framework | Servlet baseline | Namespace | JSF tích hợp |
|---|---:|---|---|---|---|
| 2.5.1 | Java 8 | Spring 5.0+ | Servlet 3.1+ theo yêu cầu dòng 2.5 | `javax.*` | JSF 2.2+ |
| 3.0.2 | Java 17 | Spring 6.0+; bản 3.0.2 dùng Framework 6.2.19 | Jakarta Servlet 5.0+; Servlet 6.0 khi theo EE 10 | `jakarta.*` | JSF 4.0+ |
| 4.0.2 | Java 17 | Spring Framework 7.0 baseline; bản 4.0.2 nâng lên 7.0.11 | Servlet 6.1 | `jakarta.*` | JSF 4.1+ |

Các điểm cần đọc đúng:

- SWF 2.5.1 reference guide ghi Java 8+ và Spring Framework 5.0+; ghi chú phát hành SWF 2.5 yêu cầu Servlet 3.1 và JSF 2.2 trở lên.
- SWF 3.0.2 reference guide ghi Java 17+ và Spring Framework 6.0+; dòng 3.0 dùng Jakarta EE và JSF 4.0+.
- SWF 4.0.2 reference guide nêu baseline Java 17+, Spring Framework 7.0 và Servlet 6.1; JSF tích hợp yêu cầu JSF 4.1+.
- Release SWF 3.0.2 nâng dependency lên Spring Framework 6.2.19 và Spring Security 6.5.11. Release SWF 4.0.2 nâng lên Spring Framework 7.0.11 và Spring Security 7.0.9.

Các con số trên là baseline để bắt đầu đánh giá. Khi triển khai thật, hãy kiểm tra POM/BOM và dependency tree của đúng phiên bản patch, vì bản release có thể nâng dependency so với yêu cầu tối thiểu trong reference guide.

### 2.1. Vì sao `javax.*` và `jakarta.*` không thể trộn tùy ý?

Spring Framework 5.x thuộc thế hệ Java EE dùng namespace `javax.servlet.*`. Spring Framework 6.x chuyển sang Jakarta EE 9+ với `jakarta.servlet.*`. Spring Framework 7.x dùng baseline Jakarta EE 11, vẫn theo namespace `jakarta.*`.

Đây là khác biệt ở tên package và kiểu API trong bytecode. Một class biên dịch với `javax.servlet.http.HttpServletRequest` không phải cùng kiểu với `jakarta.servlet.http.HttpServletRequest`, dù hai API có tên class gần giống nhau.

Ví dụ:

~~~java
// Thế hệ Java EE / Spring Framework 5
import javax.servlet.http.HttpServletRequest;

// Thế hệ Jakarta EE / Spring Framework 6+
import jakarta.servlet.http.HttpServletRequest;
~~~

Không thể sửa lỗi tương thích bằng cách chỉ đổi phiên bản Tomcat. Cần nâng đồng bộ framework, thư viện tích hợp, Servlet container và mã ứng dụng đang tham chiếu API cũ.

### 2.2. Chọn dòng phiên bản theo tình trạng hệ thống

- **Duy trì hệ thống cũ:** nếu ứng dụng đang dùng Java 8/11, Spring 5 và thư viện `javax.*`, SWF 2.5.x có thể là đường duy trì phù hợp. Đây là lựa chọn cho hệ thống legacy; cần đánh giá tình trạng hỗ trợ và kế hoạch nâng cấp bảo mật.
- **Đã chuyển sang Jakarta EE 9/10:** SWF 3.0.x phù hợp với Java 17+, Spring 6 và Servlet 5/6. Kiểm tra bản patch cụ thể và chính sách hỗ trợ Framework 6.2.
- **Dự án mới trên Jakarta EE 11:** ưu tiên đánh giá SWF 4.0.2 với Java 17+, Spring Framework 7.0.x và Servlet 6.1.

Tại ngày 25-11-2026, Spring Framework 5.3 đã kết thúc hỗ trợ mã nguồn mở từ tháng 8-2024 và dòng 6.2 đã kết thúc hỗ trợ mã nguồn mở từ tháng 6-2026; các tùy chọn hỗ trợ thương mại có thể khác. Vì vậy, không nên chọn dòng cũ cho dự án mới chỉ vì nó dễ chạy trên container hiện tại.

## 3. Chọn Servlet container phù hợp

Servlet container phải hỗ trợ ít nhất Servlet API mà dòng Spring Framework/SWF yêu cầu. Ví dụ thường gặp:

| Nền tảng | Container thường gặp | Lưu ý |
|---|---|---|
| Java EE 8 / Servlet 4.0 | Tomcat 9, Jetty 9.4 | Thuộc hệ `javax.*`, phù hợp ứng dụng legacy với Spring 5 |
| Jakarta EE 9 / Servlet 5.0 | Tomcat 10.0, Jetty 11, Undertow 2.2 bản Jakarta | Thuộc hệ `jakarta.*`, phù hợp baseline Spring 6 ban đầu |
| Jakarta EE 10 / Servlet 6.0 | Tomcat 10.1, Jetty 12, Undertow 2.3 | Phù hợp hệ Spring 6.2 |
| Jakarta EE 11 / Servlet 6.1 | Tomcat 11, Jetty 12.1 | Phù hợp baseline Spring Framework 7 và SWF 4 |

Tên container và phiên bản chỉ là gợi ý để bắt đầu kiểm tra. Cần xác nhận đúng Servlet API, JDK runtime, connector và phiên bản Spring mà ứng dụng đang dùng. Không chọn container chỉ dựa trên số phiên bản lớn hơn.

### 3.1. Embedded server hay triển khai WAR?

Spring Boot có thể chạy ứng dụng Servlet với embedded server hoặc đóng gói WAR để triển khai lên container bên ngoài. SWF không bắt buộc phải dùng Spring Boot; ứng dụng Spring MVC truyền thống với `DispatcherServlet` cũng có thể tích hợp SWF.

Chọn embedded server khi muốn đóng gói ứng dụng tự chạy, cấu hình đơn giản và phát hành cùng runtime. Chọn WAR/container ngoài khi tổ chức đã chuẩn hóa application server, cần chia sẻ hạ tầng vận hành hoặc phải dùng công nghệ view có ràng buộc với container.

### 3.2. Lưu ý JSP khi dùng Spring Boot

JSP có một số giới hạn khi chạy Spring Boot với embedded servlet container:

- Với Tomcat và Jetty, JSP có thể hoạt động khi đóng gói WAR; executable WAR vẫn có thể chạy bằng `java -jar`.
- JSP không được hỗ trợ trong executable JAR.
- Undertow không hỗ trợ JSP.

Nếu mục tiêu là executable JAR, hãy cân nhắc Thymeleaf hoặc FreeMarker để tránh phụ thuộc vào JSP engine. Nếu dự án đã có JSP lớn, WAR trên Tomcat/Jetty thường là hướng triển khai thực tế hơn.

## 4. Chọn công nghệ giao diện theo cách render của Spring MVC

Spring Web Flow sử dụng view ID trong `view-state`. View factory của SWF kết nối với cơ chế render view của Spring MVC. Bạn có thể giữ `ViewResolver` hiện tại và cấu hình `MvcViewFactoryCreator` để SWF dùng cùng hệ thống phân giải view.

~~~mermaid
flowchart LR
    A["view-state view='booking/review'"] --> B["ViewFactoryCreator"]
    B --> C["MvcViewFactoryCreator"]
    C --> D["Spring MVC ViewResolver"]
    D --> E["Template / View"]
    E --> F["HTML response"]
~~~

SWF 4.0.2 reference guide ghi default MVC view factory có thể render JSP, Velocity và FreeMarker. Khi dùng công nghệ khác, có thể cấu hình ViewResolver tương ứng thông qua `MvcViewFactoryCreator`. Spring MVC hiện cũng có các tích hợp view như Thymeleaf, Groovy Markup, JSP/JSTL, FreeMarker và những loại view khác.

### 4.1. JSP và JSTL

JSP phù hợp khi:

- Ứng dụng đã có nhiều trang JSP.
- Đội ngũ quen JSTL và tag library.
- Hệ thống triển khai WAR trên Tomcat/Jetty.
- Muốn tận dụng cấu trúc view hiện có.

Cần kiểm tra JSP engine, JSTL và packaging theo container. Nếu chọn Spring Boot executable JAR, JSP không phải lựa chọn phù hợp.

### 4.2. Thymeleaf

Thymeleaf là lựa chọn phù hợp cho ứng dụng Spring MVC server-rendered mới:

- Template HTML có thể đọc được trong editor/browser.
- Có tích hợp Spring MVC qua Thymeleaf ViewResolver.
- Dễ xây dựng layout và fragment.
- Có thể render view-state của SWF khi view resolver được cấu hình trong `MvcViewFactoryCreator`.

SWF không tự động biến mọi template engine thành view tương thích. Cần cấu hình resolver, kiểm tra tên view, model attribute, event parameter và form action URL do SWF cung cấp.

### 4.3. FreeMarker

FreeMarker là lựa chọn server-side template có thể dùng với MVC view factory của SWF. Nó phù hợp khi ứng dụng đã có template FTL, cần tách dữ liệu khỏi HTML hoặc muốn tái sử dụng layout hiện tại.

Khi gửi event, template cần tạo form/link theo hợp đồng HTTP của SWF, chẳng hạn tham số `_eventId_next` hoặc URL execution hiện tại. Template engine chỉ chịu trách nhiệm render; flow definition vẫn quyết định event và transition.

### 4.4. JSF và Facelets

SWF có module tích hợp riêng **Spring Faces** cho ứng dụng cần mô hình component/event của JSF. Đây không đơn thuần là thêm file XHTML vào Spring MVC; cần dùng đúng phiên bản JSF và cấu hình adapter/lifecycle tương ứng.

| Dòng SWF | Phiên bản JSF tối thiểu |
|---|---|
| 2.5.x | JSF 2.2 |
| 3.0.x | JSF 4.0 |
| 4.0.x | JSF 4.1 |

Với SWF 4, JSF dùng namespace `jakarta.faces.*`. Tài liệu tích hợp yêu cầu cấu hình `FacesServlet` để JSF khởi tạo, nhưng request do Web Flow điều khiển thường được route qua Spring `DispatcherServlet`, không phải gửi qua FacesServlet như ứng dụng JSF thuần. Cần đăng ký `FlowFacesContextLifecycleListener`, cấu hình `faces:flow-builder-services` và dùng `JsfFlowHandlerAdapter` theo hướng dẫn của phiên bản.

Chọn JSF khi ứng dụng đã dùng JSF component library, có đội ngũ và component phù hợp, hoặc đang nâng cấp hệ thống JSF hiện có. Nếu dự án mới chỉ cần HTML form nhiều bước, Spring MVC với Thymeleaf/FreeMarker thường đơn giản hơn.

### 4.5. Tiles và các công nghệ layout cũ

Không lấy ví dụ Tiles trong tài liệu SWF 2.x làm bằng chứng rằng Tiles tương thích với mọi dòng mới. Khi SWF 3 chuyển sang Spring Framework 6/Jakarta EE, Tiles không được chuyển đổi theo Jakarta; thông báo phát hành SWF 3 cho biết Tiles bị loại khỏi mẫu booking-mvc và được thay bằng Thymeleaf Layouts.

Nếu ứng dụng còn Tiles, hãy đánh giá thay thế layout trước khi nâng lên SWF 3/4. Có thể giữ hệ thống legacy trên stack tương thích trong giai đoạn chuyển đổi, nhưng không nên đưa Tiles vào kiến trúc mới dựa trên Jakarta EE.

### 4.6. Giao diện SPA với React, Vue hoặc Angular

Một SPA có thể dùng JavaScript để gọi các endpoint HTTP và hiển thị một phần giao diện, nhưng đó không phải một Spring MVC ViewResolver. SWF quản lý execution phía server và cung cấp execution URL/event để tiếp tục hành trình.

Tài liệu SWF hỗ trợ AJAX partial rendering và chế độ embedded flow. Điều này cho phép cập nhật một phần trang hoặc nhúng một subflow vào trang lớn. Tuy nhiên, client phải giữ đúng flow execution URL, session/cookie, CSRF token và event contract. Không coi flow endpoint là REST API stateless chỉ vì client gửi request bằng fetch/Axios.

Nếu ứng dụng cần một frontend SPA hoàn toàn tách biệt, hãy làm rõ ai sở hữu state và navigation:

- Để SWF sở hữu state: client phải tuân thủ execution lifecycle, event và persistence của flow.
- Để SPA sở hữu state: xây API nghiệp vụ stateless hoặc stateful theo contract riêng; không nên tạo một lớp giao tiếp giả định rằng SWF là WebFlux/REST engine.

Module `spring-js-resources` là module legacy, chỉ còn tùy chọn cho tương thích ngược; không nên chọn nó làm nền tảng JavaScript mới.

## 5. Ma trận chọn công nghệ giao diện

| Nhu cầu | Lựa chọn nên đánh giá | Điều kiện |
|---|---|---|
| Ứng dụng MVC truyền thống, nhiều JSP | JSP/JSTL | Servlet container và packaging hỗ trợ JSP |
| Dự án Spring MVC mới, server-rendered | Thymeleaf | Cấu hình Thymeleaf ViewResolver cho SWF |
| Đã có template FTL | FreeMarker | Cấu hình resolver và event form đúng |
| UI component-based, đã có JSF | JSF/Facelets + Spring Faces | Dùng đúng JSF theo dòng SWF |
| SPA cần một vài bước flow nhúng | React/Vue/Angular + embedded/AJAX integration | Quản lý execution URL, session, CSRF và event |
| API stateless hoặc reactive-first | Spring MVC/WebFlux API riêng | Đánh giá xem có thật sự cần SWF cho use case đó |

Không có view technology nào thay đổi baseline Servlet/Java/Spring của SWF. Một template Thymeleaf không thể làm SWF 2.5 chạy trên Spring 7; một ứng dụng JSF không thể bỏ qua yêu cầu namespace của phiên bản.

## 6. Cấu hình một ứng dụng Servlet tối thiểu

Với ứng dụng Servlet truyền thống, request flow đi qua Spring `DispatcherServlet`. Trong `web.xml`, servlet có thể được map vào một URL prefix:

~~~xml
<servlet>
    <servlet-name>app</servlet-name>
    <servlet-class>
        org.springframework.web.servlet.DispatcherServlet
    </servlet-class>
    <load-on-startup>1</load-on-startup>
</servlet>

<servlet-mapping>
    <servlet-name>app</servlet-name>
    <url-pattern>/app/*</url-pattern>
</servlet-mapping>
~~~

Sau đó đăng ký flow registry, executor, mapping và adapter trong Spring MVC context:

~~~xml
<webflow:flow-registry id="flowRegistry"
                       base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern value="**/*-flow.xml"/>
</webflow:flow-registry>

<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry"/>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry"/>
    <property name="order" value="0"/>
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor"/>
</bean>
~~~

Ví dụ là khung tích hợp MVC; cần khai báo đầy đủ XML namespace/schema, view resolver và các bean nghiệp vụ trong ứng dụng thật. Nếu dùng Java configuration, SWF cung cấp `AbstractFlowConfiguration` cùng builder cho `FlowDefinitionRegistry` và `FlowExecutor`.

### 6.1. Kết nối ViewResolver hiện có

Giả sử ứng dụng đã có Thymeleaf ViewResolver. Có thể cấu hình SWF dùng cùng resolver:

~~~xml
<webflow:flow-builder-services
        id="flowBuilderServices"
        view-factory-creator="mvcViewFactoryCreator"/>

<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices"
                       base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern value="**/*-flow.xml"/>
</webflow:flow-registry>

<bean id="mvcViewFactoryCreator"
      class="org.springframework.webflow.mvc.builder.MvcViewFactoryCreator">
    <property name="viewResolvers" ref="viewResolvers"/>
</bean>
~~~

`viewResolvers` là danh sách resolver của ứng dụng, được cấu hình theo template engine đang dùng. Khi flow khai báo:

~~~xml
<view-state id="review"
            view="booking/review"
            model="booking"/>
~~~

SWF yêu cầu Spring MVC phân giải view ID `booking/review`. Template thực tế có thể là JSP, FTL hoặc Thymeleaf tùy resolver và cấu hình của ứng dụng.

### 6.2. Kiểm tra đường dẫn flow và view độc lập

Flow definition và template view có thể được đặt ở thư mục khác nhau. Ví dụ flow nằm trong `/WEB-INF/flows/booking/booking-flow.xml`, còn view nằm trong `/WEB-INF/views/booking/review.html`.

Không giả định view ID luôn là đường dẫn file trực tiếp. Hãy xác định resolver đang dùng prefix/suffix gì, rồi kiểm tra view ID của từng state phân giải đúng.

## 7. Chọn dependency theo thế hệ

Artifact chính của SWF là:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>4.0.2</version>
</dependency>
~~~

Nếu dùng tích hợp JSF, thêm module Spring Faces cùng phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-faces</artifactId>
    <version>4.0.2</version>
</dependency>
~~~

Đổi phiên bản dependency theo dòng SWF đang chọn. Không sao chép version 4.0.2 vào dự án Spring 6 hoặc Java EE `javax.*`.

### 7.1. Spring Boot không thay thế bước kiểm tra dependency

Spring Boot giúp đóng gói ứng dụng và quản lý dependency qua BOM, nhưng không làm mất yêu cầu tương thích của SWF. Trước khi chốt Boot version:

1. Xác định Boot đang quản lý Spring Framework phiên bản nào.
2. Xác định Spring Security phiên bản nào nếu ứng dụng dùng bảo mật.
3. Kiểm tra SWF release đang dùng được build/test với dòng Framework tương ứng.
4. Kiểm tra Servlet container embedded có đúng Servlet API.
5. Chạy dependency tree để tìm nhiều phiên bản Spring hoặc API `javax/jakarta` bị kéo vào.

Định hướng theo thế hệ:

| Nền tảng ứng dụng | Dòng SWF để đánh giá |
|---|---|
| Spring Boot 2.x / Spring 5 / `javax.*` | SWF 2.5.x |
| Spring Boot 3.x / Spring 6 / `jakarta.*` | SWF 3.0.x |
| Spring Boot 4.x / Spring 7 / Jakarta EE 11 | SWF 4.0.x |

Đây là định hướng theo generation, không phải cam kết rằng mọi patch của Boot và SWF đều tương thích nhị phân với nhau. Hãy đối chiếu dependency management của release cụ thể. SWF 4.0.2 được phát hành với Spring Framework 7.0.11 và Spring Security 7.0.9; không nên ép một version khác vào chỉ vì BOM của dự án đang dùng version đó mà chưa chạy kiểm thử tích hợp.

## 8. Cấu hình JSF đúng với phiên bản

Nếu chọn JSF, cần cả dependency và cấu hình lifecycle. Ví dụ dưới đây minh họa cấu hình theo Spring Web Flow 4.x và Jakarta Faces:

~~~xml
<webflow:flow-executor id="flowExecutor">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="facesContextListener"/>
    </webflow:flow-execution-listeners>
</webflow:flow-executor>

<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices"
                       base-path="/WEB-INF">
    <webflow:flow-location-pattern value="**/*-flow.xml"/>
</webflow:flow-registry>

<faces:flow-builder-services id="flowBuilderServices"/>

<bean id="facesContextListener"
      class="org.springframework.faces.webflow.FlowFacesContextLifecycleListener"/>

<bean class="org.springframework.faces.webflow.JsfFlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor"/>
</bean>
~~~

Với JSF, cấu hình `FacesServlet` để JSF khởi tạo. Nhưng request được Web Flow điều khiển thường đi qua Spring `DispatcherServlet`; `JsfFlowHandlerAdapter` thay cho adapter MVC thông thường và dùng `JsfAjaxHandler`.

Đừng lấy cấu hình `javax.faces.*` của JSF 2.x áp dụng cho JSF 4.x. Trong thế hệ Jakarta, context parameter và class đều chuyển sang `jakarta.faces.*`.

## 9. Những dấu hiệu chọn sai nền tảng

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `ClassNotFoundException: javax.servlet...` | Code/thư viện `javax` chạy trên container Jakarta | Kiểm tra generation SWF, Spring và dependency |
| `ClassNotFoundException: jakarta.servlet...` | Thư viện Jakarta chạy trên container Java EE cũ | Nâng container/framework hoặc dùng dòng SWF cũ phù hợp |
| `NoSuchMethodError` trong Spring | Trộn phiên bản Spring module không đồng bộ | Xem dependency tree và BOM |
| Flow URL trả 404 | FlowHandlerMapping không khớp hoặc flow chưa đăng ký | Kiểm tra path, registry và order |
| Flow chạy nhưng view 404 | ViewResolver không nhận view ID | Kiểm tra prefix/suffix, resolver và viewFactoryCreator |
| JSP không render trong executable JAR | Hạn chế JSP của Spring Boot packaging | Dùng WAR với Tomcat/Jetty hoặc chọn template engine khác |
| JSF không có FacesContext | Thiếu JSF bootstrap/lifecycle listener hoặc sai adapter | Kiểm tra spring-faces, FacesServlet và FlowFacesContextLifecycleListener |
| JSF class không load | Dùng JSF không đúng thế hệ `javax/jakarta` | Đối chiếu JSF version với SWF version |
| Flow chạy trên MVC nhưng không trên WebFlux | SWF tích hợp Servlet MVC, không phải reactive adapter | Dùng Servlet/MVC cho flow hoặc chọn giải pháp khác |

### 9.1. Kiểm tra dependency tree

Với Maven, xem các dependency Spring và Servlet API đang được resolve:

~~~bash
mvn dependency:tree
~~~

Tìm các artifact:

- `org.springframework:spring-webmvc`
- `org.springframework:spring-context`
- `org.springframework.webflow:spring-webflow`
- `org.springframework.webflow:spring-faces` nếu dùng JSF
- `jakarta.servlet:jakarta.servlet-api` hoặc `javax.servlet:javax.servlet-api`
- JSF implementation và component library nếu có

Không đóng gói Servlet API theo cách khiến container và ứng dụng nạp hai bản API không tương thích. Khi deploy WAR lên container, kiểm tra scope dependency và cách container cung cấp Servlet API.

## 10. Quy trình chọn stack cho dự án mới

Dùng trình tự sau để tránh chọn giao diện trước khi xác nhận nền tảng:

~~~mermaid
flowchart TD
    A["Có quy trình nhiều bước cần server quản lý state?"] -->|"Không"| X["Dùng MVC/API thông thường"]
    A -->|"Có"| B["Ứng dụng có thể chạy Servlet + Spring MVC?"]
    B -->|"Không"| Y["Tách Servlet app hoặc chọn giải pháp khác"]
    B -->|"Có"| C["Chọn Java / Spring / Servlet generation"]
    C --> D{"Namespace hiện tại"}
    D -->|"javax / Spring 5"| E["Đánh giá SWF 2.5.x cho legacy"]
    D -->|"jakarta EE 9/10 / Spring 6"| F["Đánh giá SWF 3.0.x"]
    D -->|"jakarta EE 11 / Spring 7"| G["Đánh giá SWF 4.0.x"]
    E --> H["Chọn ViewResolver hoặc JSF đúng phiên bản"]
    F --> H
    G --> H
    H --> I["Kiểm tra container, packaging và dependency tree"]
    I --> J["Chạy integration test qua HTTP"]
~~~

Với dự án mới tại thời điểm bài học, cấu hình nên được đánh giá đầu tiên là SWF 4.0.2 trên Java 17+, Spring Framework 7.0.x và Servlet 6.1. Nếu dùng giao diện server-rendered, chọn Thymeleaf hoặc FreeMarker; nếu tổ chức đã có JSF component library và muốn giữ mô hình component, kiểm tra JSF 4.1+ cùng Spring Faces.

## 11. Tình huống lựa chọn: nâng cấp hệ thống booking

Giả sử một ứng dụng booking đang có:

- Java 11.
- Spring Framework 5.3.
- Tomcat 9.
- Spring MVC và JSP/JSTL.
- Flow booking chạy với Spring Web Flow 2.5.x.

Đội dự án muốn nâng runtime lên Java 21 và chuyển sang Jakarta EE.

### Phương án A: giữ stack hiện tại trong giai đoạn ngắn

Giữ SWF 2.5.x và JSP trong lúc chuẩn bị kế hoạch migration. Đây là phương án giảm thay đổi đồng thời, nhưng phải xem xét trạng thái hỗ trợ của Java/Spring 5 và kế hoạch bảo mật. Không xem đây là đích lâu dài mặc định.

### Phương án B: nâng lên SWF 3.0.x

Nâng Java lên 17+, chuyển Spring Framework 6, chuyển container sang Servlet 5/6 và chuyển các thư viện `javax.*` sang `jakarta.*`. Có thể giữ JSP nếu container/packaging hỗ trợ, hoặc chuyển view sang Thymeleaf. JSF nếu có phải nâng lên 4.0+.

### Phương án C: nâng thẳng lên SWF 4.0.x

Chọn Java 17+, Spring Framework 7.0.x, Servlet 6.1 và Jakarta EE 11. Dòng này phù hợp đích nền tảng mới hơn nhưng phạm vi migration rộng hơn, nhất là khi ứng dụng còn nhiều thư viện chỉ hỗ trợ `javax.*` hoặc Tiles.

Trước khi chọn C, lập inventory cho:

- Servlet filters, listeners và custom tags.
- Thư viện bảo mật, persistence, validation và file upload.
- JSF component libraries nếu dùng.
- JSP/JSTL và layout framework.
- Các thư viện bên thứ ba có import `javax.*`.
- Spring Security và cách cấu hình authorization.

Không nâng container trước rồi mới phát hiện một thư viện cũ không thể nạp trên Jakarta runtime. Migration cần được kiểm tra từ compile-time đến request thật.

## 12. Kiểm thử tương thích sau khi chọn stack

Một ứng dụng khởi động thành công chưa chứng minh flow hoạt động. Cần test cả đường request và view:

1. Khởi động đúng Servlet container và Spring application context.
2. Kiểm tra `DispatcherServlet` nhận URL flow.
3. Kiểm tra `FlowHandlerMapping` tìm đúng flow ID.
4. Kiểm tra `FlowHandlerAdapter` gọi đúng `FlowExecutor`.
5. Mở flow và xác nhận view-state đầu tiên được render.
6. Submit một event và xác nhận transition sang state tiếp theo.
7. Kiểm tra form binding, validation và message.
8. Kiểm tra redirect/PRG, Back/Refresh và execution URL.
9. Nếu dùng AJAX, kiểm tra partial rendering và embedded mode.
10. Nếu dùng JSF, kiểm tra FacesContext, event lifecycle và component library.
11. Nếu deploy WAR, chạy trên container đích thay vì chỉ chạy embedded server.
12. Kiểm tra dependency tree không có hai thế hệ Servlet API hoặc Spring module xung đột.

### 12.1. Kiểm thử riêng view technology

Với JSP, kiểm tra render trong đúng packaging WAR. Với Thymeleaf/FreeMarker, kiểm tra ViewResolver nhận view ID và model attribute đúng. Với JSF, kiểm tra request được điều phối qua SWF adapter và Faces lifecycle được khởi tạo đúng.

Test flow engine bằng mock không thay thế được kiểm thử HTTP có container/view rendering. Cần ít nhất một integration test chạy qua DispatcherServlet để phát hiện sai mapping, resolver hoặc Servlet API.

## 13. Các lỗi kiến trúc nên tránh

- Chọn SWF chỉ vì ứng dụng đang dùng Spring Boot, chưa xác định có thật sự cần guided flow hay không.
- Chọn SWF 4 nhưng vẫn giữ thư viện Servlet `javax.*`.
- Nâng Spring Framework nhưng quên Spring Security, Spring Faces hoặc thư viện phụ thuộc.
- Dùng WebFlux làm web stack rồi kỳ vọng FlowHandlerAdapter hoạt động trên reactive dispatcher.
- Chọn JSP cho executable JAR mà không kiểm tra hạn chế packaging.
- Dùng JSF 2.x với SWF 3/4.
- Giữ Tiles khi migration sang Jakarta mà không xác nhận khả năng tương thích.
- Coi React/Vue là một Spring MVC ViewResolver.
- Tạo một flow URL nhưng để controller và SPA cùng tự thay đổi state mà không có contract rõ ràng.
- Chỉ test context startup, không test submit event và render view.
- Ép version Spring bằng dependency override mà không kiểm tra SWF release được xây dựng với phiên bản đó.

## 14. Bài tập thực hành: chọn stack cho quy trình đặt phòng

Một nhóm phát triển chuẩn bị ứng dụng đặt phòng với các bước:

~~~text
search → selectRoom → guestDetails → payment → confirmation
~~~

Hãy lập đề xuất stack và giải thích các lựa chọn:

**Yêu cầu:**

1. Xác định ứng dụng có phù hợp với Servlet + Spring MVC + SWF không.
2. Chọn một dòng SWF và ghi rõ Java, Spring Framework, Servlet API, namespace.
3. Chọn Tomcat/Jetty/container tương thích.
4. Chọn JSP, Thymeleaf, FreeMarker hoặc JSF; nêu lý do.
5. Nếu chọn JSF, xác định JSF version và Spring Faces configuration.
6. Nếu dùng Spring Boot, xác nhận BOM và packaging.
7. Nếu dùng JSP, kiểm tra executable JAR/WAR và container.
8. Cấu hình FlowRegistry, FlowExecutor, FlowHandlerMapping và FlowHandlerAdapter.
9. Cấu hình ViewResolver cho view-state.
10. Viết integration test mở flow, submit event, render state kế tiếp và xác nhận PRG.

**Bài kiểm thử migration:**

- Thử biên dịch một class dùng `javax.servlet` trên stack Jakarta.
- Thử chạy một flow với view resolver sai prefix/suffix.
- Thử đóng gói JSP trong executable JAR.
- Thử gửi event qua AJAX và kiểm tra execution URL.
- Xem dependency tree để xác nhận không có hai phiên bản Spring/Servlet API.

### Câu hỏi tự kiểm tra

**1. Spring Web Flow tích hợp trực tiếp với web stack nào?** Servlet-based Spring MVC, thông qua DispatcherServlet, FlowHandlerMapping và FlowHandlerAdapter.

**2. Vì sao SWF không phải thư viện WebFlux?** SWF dùng Servlet request/response và Spring MVC flow adapters; WebFlux có reactive dispatcher và contract khác.

**3. Khác biệt quan trọng giữa SWF 2.5 và 3/4 là gì?** SWF 2.5 thuộc thế hệ `javax.*`; SWF 3/4 thuộc thế hệ `jakarta.*`, với baseline Java/Spring/Servlet mới hơn.

**4. SWF 4.0.2 yêu cầu Servlet API nào?** Servlet 6.1, cùng Java 17+ và Spring Framework 7.0 baseline.

**5. SWF 4.0 cần JSF tối thiểu phiên bản nào?** JSF 4.1 trở lên.

**6. Có thể dùng Thymeleaf với SWF không?** Có, khi cấu hình Thymeleaf ViewResolver và MvcViewFactoryCreator để view-state dùng resolver đó.

**7. Vì sao JSP có thể không chạy trong Spring Boot executable JAR?** Embedded Tomcat/Jetty chỉ hỗ trợ JSP trong WAR packaging; Undertow không hỗ trợ JSP.

**8. Khi nào nên dùng input/output của subflow thay vì chia sẻ object qua UI?** Khi cần contract dữ liệu rõ giữa flow cha và flow con; giao diện không quyết định cơ chế mapping dữ liệu.

**9. Tiles có phải lựa chọn an toàn cho SWF 3/4 không?** Không nên mặc định như vậy; Tiles không được chuyển sang Jakarta trong quá trình migration SWF 3.

**10. Kiểm tra nào chứng minh tích hợp thực sự hoạt động?** Integration test qua Servlet container/DispatcherServlet, mở flow, submit event, render view và kiểm tra dependency/runtime tương thích.

## 15. Checklist trước khi bắt đầu dự án

- [ ] Use case thật sự cần guided, stateful flow.
- [ ] Ứng dụng có thể chạy trên Servlet và Spring MVC.
- [ ] Đã chọn đúng dòng SWF theo Java và Spring Framework.
- [ ] Servlet container hỗ trợ đúng Servlet API baseline.
- [ ] Namespace `javax.*` hoặc `jakarta.*` nhất quán.
- [ ] Spring Security và các module Spring dùng version tương thích.
- [ ] Đã chọn view technology có ViewResolver/adapter phù hợp.
- [ ] Nếu dùng JSF, version JSF khớp SWF và có cấu hình Spring Faces.
- [ ] Nếu dùng JSP, packaging và container hỗ trợ JSP.
- [ ] Không dựa vào Tiles cho stack Jakarta mới.
- [ ] Nếu dùng SPA, đã xác định rõ flow execution URL, session, CSRF và event contract.
- [ ] Đã đăng ký FlowRegistry, FlowExecutor, FlowHandlerMapping và FlowHandlerAdapter.
- [ ] Đã cấu hình MvcViewFactoryCreator với ViewResolver thực tế.
- [ ] Dependency tree không trộn các thế hệ Servlet/Spring.
- [ ] Có integration test qua HTTP và view rendering thật.
- [ ] Có kế hoạch migration nếu đang ở Spring 5 hoặc Java EE `javax.*`.

**Ghi nhớ:** Spring Web Flow cần một nền tảng Servlet tương thích và thường được điều phối qua Spring MVC. Chọn phiên bản theo đồng bộ Java, Spring Framework, Servlet API và namespace trước; sau đó mới chọn JSP, Thymeleaf, FreeMarker hay JSF. Với stack mới Jakarta EE 11, SWF 4.0.2 dùng baseline Java 17+, Spring Framework 7.0 và Servlet 6.1. Nếu dùng Boot, JSF hoặc SPA, hãy kiểm tra packaging, adapter, resolver và lifecycle bằng integration test qua request thật.

### Tài liệu tham khảo

- [Spring Web Flow 4.0.2 Reference — Web Flow 4.0 Baseline](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/)
- [Spring Web Flow 4.0.2 Reference — Spring MVC Integration and View Resolution](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/)
- [Spring Web Flow 3.0.2 Reference — Requirements and JSF Integration](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/)
- [Spring Web Flow 2.5.1 Reference — Requirements and What’s New](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/)
- [Spring Web Flow 3.0.0 Released — Jakarta EE migration and Tiles removal](https://spring.io/blog/2023/07/13/spring-web-flow-3-0-0-released/)
- [Spring Web Flow Releases — dependency upgrades for 3.0.2 and 4.0.2](https://github.com/spring-projects/spring-webflow/releases)
- [Spring Framework Versions — JDK and Jakarta EE support ranges](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)
- [Spring Framework — View Technologies in Spring MVC](https://docs.spring.io/spring/reference/web/webmvc-view.html)
- [Spring Boot — JSP Limitations](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)

