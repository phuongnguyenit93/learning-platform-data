# Phân biệt hệ sinh thái javax với Jakarta

Khi chuyển một ứng dụng **Spring Web Flow (SWF)** từ Spring Framework 5 sang Spring Framework 6 hoặc 7, bạn thường gặp lỗi liên quan đến `javax.servlet`, `jakarta.servlet`, `javax.validation` hay `jakarta.validation`. Nhìn qua, các class giống nhau về tên và tác dụng, nhưng JVM coi chúng là **những kiểu hoàn toàn khác nhau**. Một bộ lọc, validator hoặc thành phần JSF được viết cho namespace cũ không tự trở thành thành phần Jakarta chỉ nhờ đổi JDK.

Đây là bài thuộc chương **Nền tảng và phiên bản** của module `SPRING_WEB_FLOW`. Bạn sẽ học nguồn gốc của hai hệ sinh thái, cách nhận diện package cần chuyển đổi, ảnh hưởng của chúng tới Spring MVC và các flow có nhiều bước (`state`, `event`, `transition`, `subflow`), rồi thực hành kiểm tra classpath, binding, validation, session và tích hợp khi nâng cấp.

> **Mốc tham chiếu: 25/11/2026.** Các ví dụ chọn nền tảng minh họa Web Flow 2.5.1.RELEASE, 3.0.2 và 4.0.2 theo reference tương ứng. Trước khi nâng cấp một dự án thực tế, hãy đối chiếu lại dependency management, tài liệu phiên bản đang dùng và các bản vá bảo mật hiện hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác nhau giữa **Java EE**, **Jakarta EE** và **Java SE**; chỉ ra vì sao **Jakarta EE 8 vẫn có package `javax.*`**.
2. Phân biệt **API specification**, **implementation**, **servlet container**, **framework** và **JDK**.
3. Nhận biết nhóm import chuyển từ `javax.*` sang `jakarta.*` và những package `javax.*` của Java SE **không đổi**.
4. Chọn tổ hợp Spring Web Flow, Spring Framework, Java và Servlet API phù hợp.
5. Phát hiện sự không tương thích ở compile-time, dependency resolution, lúc khởi tạo bean và khi xử lý request.
6. Lập kế hoạch nâng cấp form binding/validation, Spring MVC, JSF, JPA và security mà vẫn giữ đúng hành vi flow.
7. Thiết kế kiểm thử xác nhận transition, scope, session, lỗi form và các action nghiệp vụ sau migration.

## 2. Lịch sử: Java EE chuyển giao cho Jakarta EE

**Java SE (Standard Edition)** cung cấp nền tảng ngôn ngữ và thư viện chuẩn Java như collections, I/O, JDBC, concurrency và security primitives. **Java EE (Enterprise Edition)** trước đây bổ sung các specification ứng dụng doanh nghiệp: Servlet, JPA, Bean Validation, JSF, CDI, JAX-RS, v.v.

Sau khi công nghệ Java EE được chuyển sang Eclipse Foundation, nền tảng doanh nghiệp mang tên **Jakarta EE**. Tên tổ chức và specification đã thay đổi trước khi các package Java thực sự đổi:

| Thời kỳ | Tên nền tảng | Namespace API doanh nghiệp | Điểm đáng nhớ |
| --- | --- | --- | --- |
| Java EE 7/8 | Java EE | `javax.servlet`, `javax.persistence`, `javax.validation`, ... | Cơ sở của nhiều ứng dụng Spring Framework 5 |
| **Jakarta EE 8** (2019) | Jakarta EE | **Vẫn là `javax.*`** | Chuyển governance/specification, chưa đổi tên package |
| **Jakarta EE 9** (2020) | Jakarta EE | **`jakarta.*`** đối với API Jakarta EE | Bước đổi namespace gây khác biệt nhị phân lớn |
| Jakarta EE 10 | Jakarta EE | `jakarta.*` | Các API tiếp tục phát triển trong namespace mới |
| Jakarta EE 11 | Jakarta EE | `jakarta.*` | Nền tảng của Spring Framework 7 / Servlet 6.1 |

Vì vậy, phát biểu “**Jakarta nghĩa là toàn bộ import đều bắt đầu bằng `jakarta`**” là sai trong trường hợp **Jakarta EE 8**. Hãy xem **phiên bản specification** và **package của class thực tế**, thay vì dựa vào chữ “Jakarta” trong tên sản phẩm.

~~~mermaid
timeline
    title Sự phát triển namespace doanh nghiệp
    Java EE 8 : javax.*
    Jakarta EE 8 : javax.* vẫn giữ
    Jakarta EE 9 : jakarta.* cho Jakarta EE APIs
    Jakarta EE 10 : jakarta.*
    Jakarta EE 11 : jakarta.*
~~~

Nguồn gốc đổi namespace được trình bày trong [Eclipse Foundation — Javax to Jakarta Namespace Ecosystem Progress](https://jakarta.ee/blogs/javax-jakartaee-namespace-ecosystem-progress/). Điều này giúp giải thích vì sao các hướng dẫn cũ dành cho “Jakarta EE 8” lại chứa `javax.servlet.http.HttpServletRequest` mà vẫn đúng trong bối cảnh lịch sử của chúng.

## 3. Phân biệt Java SE, Jakarta EE, Spring và Web Flow

Một lớp có tên `javax.*` **không tự động thuộc Java EE**. Trong Java SE vẫn có các package bắt đầu bằng `javax`, ví dụ `javax.crypto`, `javax.net.ssl`, `javax.sql`, `javax.naming` và `javax.xml.parsers`. Các package Java SE đó vẫn có tên cũ khi ứng dụng sử dụng Jakarta EE.

| Thành phần | Thuộc về | Liên quan tới Web Flow |
| --- | --- | --- |
| **JDK/Java SE** | Nền tảng Java | Chạy bytecode, `LocalDate`, JDBC, XML parser, TLS |
| **Jakarta EE specification** | Hợp đồng API doanh nghiệp | `jakarta.servlet`, `jakarta.validation`, `jakarta.persistence`, `jakarta.faces` |
| **Implementation** | Thư viện thực hiện specification | Bean Validation provider, JPA provider, JSF implementation |
| **Servlet container** | Tomcat/Jetty hoặc application server | Quản lý request/response, filters, `HttpSession` |
| **Spring Framework/MVC** | Framework ứng dụng | IoC, `DispatcherServlet`, data binding, converter, validator |
| **Spring Web Flow** | Thư viện gắn trên Spring MVC | State machine, event/transition, scopes, subflows |
| **Spring Boot** (nếu dùng) | Cấu hình/BOM/starter | Chọn một tập Spring và server dependency tương ứng |

**Java 17 không có nghĩa là Jakarta EE 9.** Một ứng dụng đang chạy trên JDK 17 vẫn có thể dùng Spring 5 và Servlet `javax`. Ngược lại, ứng dụng Spring 6/7 yêu cầu không chỉ JDK đủ mới mà cả các API doanh nghiệp và container tương thích.

## 4. Bảng chuyển namespace cho các API thường gặp

| Chức năng | Java EE / Jakarta EE 8 | Jakarta EE 9+ | Cần kiểm tra thêm |
| --- | --- | --- | --- |
| Servlet HTTP request | `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | Servlet container, filters, MVC |
| Servlet filter | `javax.servlet.Filter` | `jakarta.servlet.Filter` | Spring Security và custom filters |
| HTTP session | `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` | Session store, listeners, serialization |
| Bean Validation | `javax.validation.Valid` / `javax.validation.constraints.NotNull` | `jakarta.validation.Valid` / `jakarta.validation.constraints.NotNull` | Validation provider và binding |
| JPA | `javax.persistence.Entity` / `EntityManager` | `jakarta.persistence.Entity` / `EntityManager` | Hibernate/EclipseLink và entity mappings |
| JSF | `javax.faces.context.FacesContext` | `jakarta.faces.context.FacesContext` | JSF implementation, Spring Faces |
| EL | `javax.el.ExpressionFactory` | `jakarta.el.ExpressionFactory` | EL parser, biểu thức trong view |
| CDI/Inject | `javax.inject.Inject` | `jakarta.inject.Inject` | CDI và thư viện `javax.inject` cũ |
| Lifecycle annotations | `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` | Annotation API dependency |
| WebSocket | `javax.websocket.Session` | `jakarta.websocket.Session` | Endpoint/container |
| JAXB | `javax.xml.bind.JAXBContext` | `jakarta.xml.bind.JAXBContext` | JAXB implementation, XML serialization |
| JAX-RS | `javax.ws.rs.Path` | `jakarta.ws.rs.Path` | REST runtime/Jersey/RESTEasy nếu dùng |

Không nhất thiết phải dùng tất cả những API này trong ứng dụng SWF. Một flow Thymeleaf/Spring MVC chỉ cần xem các phần **có mặt trong dependency tree**, đặc biệt Servlet, validation, security và persistence. Nếu ứng dụng sử dụng JSF/Spring Faces thì phải kiểm tra thêm Faces, EL và thư viện components.

### 4.1. Những `javax.*` không được thay hàng loạt

Đây là các ví dụ package **Java SE**, không phải API doanh nghiệp bị chuyển tên:

~~~java
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.stream.XMLInputFactory;
import javax.annotation.processing.Processor;
~~~

Nếu script thay mọi chuỗi `javax.` thành `jakarta.`, chương trình sẽ tạo những import không tồn tại như `jakarta.crypto.Cipher` hoặc `jakarta.sql.DataSource`. Cần **phân loại theo nhóm specification**, kiểm tra artifact cung cấp class và review diff.

Ngược lại, một số tên như `javax.annotation.PostConstruct` hoặc `javax.validation.Valid` thuộc API doanh nghiệp/lifecycle trước đây, nên có đối ứng `jakarta.annotation.PostConstruct` và `jakarta.validation.Valid`. **Tiền tố `javax` một mình không đủ để ra quyết định**.

## 5. Vì sao hai package có cùng tên class vẫn không tương thích?

Xét hai định nghĩa:

~~~java
// Nguồn legacy: Spring Framework 5 / Servlet theo Java EE
import javax.servlet.http.HttpServletRequest;

void handleLegacy(HttpServletRequest request) {
    // ...
}
~~~

~~~java
// Nguồn Jakarta: Spring Framework 6+ / Servlet Jakarta
import jakarta.servlet.http.HttpServletRequest;

void handleJakarta(HttpServletRequest request) {
    // ...
}
~~~

Ở JVM, tên nhị phân `javax.servlet.http.HttpServletRequest` khác `jakarta.servlet.http.HttpServletRequest`. Dù hai interface mô tả request HTTP và có nhiều method tương tự, chúng **không thể tự ép kiểu cho nhau**. Một filter được biên dịch cho `javax.servlet.Filter` không tự trở thành `jakarta.servlet.Filter` mà Tomcat 10/11 mong đợi.

~~~mermaid
flowchart LR
    A["javax.servlet.http.HttpServletRequest"] --> B{"Cùng một Java type?"}
    C["jakarta.servlet.http.HttpServletRequest"] --> B
    B -->|"Không"| D["Cần mã và dependency đúng namespace"]
~~~

Hậu quả có thể xuất hiện ở nhiều tầng:

| Giai đoạn | Triệu chứng | Nguyên nhân điển hình |
| --- | --- | --- |
| Biên dịch | `package javax.servlet does not exist` | Chỉ có Jakarta API nhưng source dùng import cũ |
| Đóng gói/khởi tạo | `ClassNotFoundException` / `NoClassDefFoundError` | JAR cũ trông đợi `javax`, classpath chỉ có `jakarta` |
| Khởi tạo Spring bean | Bean type mismatch / `BeanCreationException` | Filter/validator/integration sai thế hệ |
| Lúc gọi method | `NoSuchMethodError` / `AbstractMethodError` | API implementation/class bị biên dịch theo thế hệ khác |
| Khi gửi request | HTTP 404/500 hoặc filter không chạy | Servlet container, handler hoặc framework tích hợp không tương thích |

**Chỉ thêm cả hai dependency `javax.servlet-api` và `jakarta.servlet-api` thường không giải quyết lỗi.** Điều đó có thể khiến source biên dịch nhưng servlet container/framework vẫn dùng namespace khác và không chấp nhận object của thế hệ còn lại. Cần chuyển **trọn đường tích hợp web** sang cùng một nền tảng.

## 6. Ma trận Spring Web Flow, Spring Framework và Jakarta

Đối với module `SPRING_WEB_FLOW`, đây là bảng chọn nhanh theo **thế hệ nền tảng**:

| Trục | SWF **2.5.x** | SWF **3.0.x** | SWF **4.0.x** |
| --- | --- | --- | --- |
| Spring Framework nên ghép | **5.x** | **6.x** | **7.0 baseline** |
| JDK tối thiểu theo reference | **8** | **17** | **17** |
| Mức Servlet/EE | Servlet **3.1+**, `javax.servlet` | Jakarta EE 9+ / `jakarta.servlet` theo Spring 6 | **Servlet 6.1**, Jakarta EE 11 baseline |
| Dòng Spring Boot điển hình | **Boot 2.x** | **Boot 3.x** | **Boot 4.x** |
| JSF nếu dùng | **JSF 2.2+** | **JSF 4.0+** | **JSF 4.1+** |
| Application API | Java EE / Jakarta EE 8 `javax.*` | Jakarta EE `jakarta.*` | Jakarta EE `jakarta.*` |
| Bản tham chiếu tài liệu | `2.5.1.RELEASE` | `3.0.2` | `4.0.2` |

**Lưu ý về phiên bản 2.x:** các bản Web Flow 2.0–2.4 xuất hiện trước 2.5 và có mức nền tảng khác nhau. Không được áp ngược yêu cầu Spring 5/Java 8 của **2.5** lên mọi bản 2.x.

**Lưu ý về Spring 6/7:** reference Web Flow 3.0.2 ghi “Spring Framework 6.0 or higher”, nhưng Web Flow 4.0 đã có baseline riêng cho Spring 7/Servlet 6.1. Khi ứng dụng dùng Spring 7, ưu tiên đánh giá dòng **SWF 4.x** và kiểm chứng thực tế, thay vì suy rằng mọi tổ hợp SWF 3 với Spring 7 đều được xác nhận.

Các giá trị được đối chiếu với [Web Flow 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/), [Web Flow 3.0.2 Reference](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) và [Web Flow 4.0.2 Reference](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/).

### 6.1. Bốn tình huống để tự chọn nền

| Tình huống | Đánh giá ban đầu | Vì sao |
| --- | --- | --- |
| Java 8 + Spring 5.3 + SWF 2.5 + Tomcat 9 | Legacy theo `javax` | Phù hợp thế hệ, nhưng cần kiểm tra bản vá và hỗ trợ |
| Java 17 + Spring 6 + SWF 3 + Tomcat 10.1 | Nền Jakarta phù hợp | Servlet/Jakarta cùng thế hệ; vẫn cần integration test |
| Java 17 + Spring 7 + SWF 4 + Tomcat 11 | Nền Jakarta EE 11 phù hợp | Tomcat 11 hỗ trợ Servlet 6.1 |
| Java 17 + Spring 6 + SWF 2.5 + Tomcat 10 | **Lệch nền tảng** | SWF 2.5 gắn với Spring 5/`javax`, còn Spring 6/Tomcat 10 dùng Jakarta |

Mọi đánh giá vẫn phải dựa trên các phiên bản **được resolve trong build và được deploy ở runtime**. Spring Boot BOM, JDK, Security, JSF và các dependency bên thứ ba cũng tham gia.

## 7. Tác động cụ thể tới Spring MVC và HTTP session

Spring MVC cung cấp `DispatcherServlet`, handler mapping/adapter, request binding, validation và rendering. Spring Web Flow sử dụng MVC để đưa request vào `FlowExecutor`. **Cơ chế điều hướng vẫn là state/event/transition**; phần bị ảnh hưởng của migration chủ yếu nằm ở **các kiểu Java trong lớp tích hợp**.

Ví dụ controller kiểm tra session trong Spring 5:

~~~java
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionProbeController {
    @GetMapping("/debug/has-session")
    String hasSession(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        return session == null ? "Không có session" : "Có session";
    }
}
~~~

Với Spring 6+, **cùng logic** nhưng đổi import sang Jakarta:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
// Các import Spring @RestController/@GetMapping giữ nguyên.
~~~

`HttpSession` vẫn biểu diễn phiên HTTP, `getSession(false)` vẫn không tạo phiên mới; **đổi namespace không làm thay đổi ý nghĩa của session**. Nhưng session listener, filter, thư viện lưu session hoặc lớp custom serialization vẫn cần tương thích với API/container mới.

### 7.1. Không nhầm session với scope của Web Flow

| Trạng thái | Vòng đời | Ví dụ |
| --- | --- | --- |
| HTTP request | Một request | Form parameters, `requestScope` |
| HTTP session | Nhiều request cho tới timeout/logout | Tình trạng đăng nhập hoặc dữ liệu dùng chung theo phiên |
| `viewScope` | View-state đang hoạt động | Trạng thái của một màn hình |
| `flowScope` | Một flow execution | Bản nháp đặt chỗ |
| `conversationScope` | Conversation bao gồm flow gốc và các subflow | Ngữ cảnh chung của hành trình |
| Database | Bền theo transaction và chính sách lưu | Booking đã xác nhận |

Các scope của Web Flow **không đổi tên sang `jakarta.flowScope`**. Chúng là abstraction của thư viện Web Flow. Khi nâng cấp nền, phải test repository/session timeout, nhưng không thể giải quyết bằng cách đổi tên một vài package trong XML.

### 7.2. Luồng nhiều bước gặp lỗi khi trộn namespace ra sao?

~~~mermaid
flowchart TD
    A["POST view-state details"] --> B["Servlet container tạo jakarta.servlet request"]
    B --> C["Spring Security filter chain Jakarta"]
    C --> D["DispatcherServlet Spring MVC 6"]
    D --> E["FlowHandlerAdapter và FlowExecutor 3.x"]
    E --> F["Bind + validate model"]
    F --> G["Transition next -> review"]
    X["Legacy filter dùng javax.servlet.Filter"] -.->|"Không có hợp đồng API tương thích"| B
~~~

Trong cấu hình đúng, request đi qua Servlet Jakarta, filter chain, MVC và Web Flow đều ở một hệ. Một custom filter dùng `javax.servlet.Filter` có thể chặn quá trình bootstrapping/deploy trước cả khi người dùng gửi event `next`. Nếu form/validation còn ở `javax.validation`, request có thể vào flow nhưng không chạy validation như mong đợi.

## 8. Flow XML và Spring XML namespace có phải đổi sang jakarta?

**Không thay tự động mọi chuỗi `http://www.springframework.org/schema/...` bằng `jakarta`.** Đây là các namespace cho tài liệu cấu hình **của Spring**, không phải tên package Servlet/Jakarta EE.

Ví dụ phần mở đầu của flow XML vẫn theo Spring Web Flow:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="details" view="booking/details" model="booking">
        <transition on="next" to="review"/>
    </view-state>
    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="finished"/>
    </view-state>
    <end-state id="finished" view="booking/finished"/>
</flow>
~~~

Cấu trúc `view-state`, `transition` và `end-state` không phải thành phần của Java EE/Jakarta EE. Tương tự, các cấu hình Spring `<beans>` và `webflow-config` giữ namespace Spring tương ứng với schema của framework đang dùng.

Tuy nhiên, **tên class được tham chiếu trong XML có thể phải đổi**. Nếu flow có `<var class="...">` trỏ tới custom class triển khai `javax.servlet.Filter` hoặc biểu thức tham chiếu một implementation JSF/EL cũ, cần thay bằng class và dependency tương thích, hoặc thiết kế lại boundary. Các URL schema Jakarta EE của **web.xml**, **persistence.xml**, **faces-config.xml** và descriptors thuộc Jakarta EE mới là những chỗ có thể cần cập nhật.

## 9. Servlet container và WAR: kiểm tra ngoài phạm vi build

Trong một ứng dụng WAR, Servlet API có thể do **application server** cung cấp. Bạn có thể build thành công vì Gradle/Maven có dependency Jakarta, nhưng khi deploy lên server chỉ hỗ trợ `javax.servlet`, ứng dụng vẫn thất bại.

| Container tiêu biểu | Servlet API | Namespace | Nền phù hợp điển hình |
| --- | --- | --- | --- |
| Tomcat 9 | Servlet 4.0 | `javax.servlet` | Spring Framework 5 / Web Flow 2.5 |
| Tomcat 10.0 | Servlet 5.0 | `jakarta.servlet` | Jakarta EE 9, một số tổ hợp Spring 6 |
| Tomcat 10.1 | Servlet 6.0 | `jakarta.servlet` | Spring Framework 6 / Web Flow 3 |
| Tomcat 11 | Servlet 6.1 | `jakarta.servlet` | Spring Framework 7 / Web Flow 4 |

Bảng chỉ lấy **Tomcat làm ví dụ**, không liệt kê mọi bản/nhánh tương thích. Khi dùng Jetty, Undertow hoặc application server khác, tra mức Servlet API thật của chính phiên bản server đang triển khai.

Với WAR cũ có `web.xml`, descriptor thuộc Java EE 8 thường có namespace `http://xmlns.jcp.org/xml/ns/javaee`; descriptor ở Jakarta Servlet mới dùng namespace theo specification Jakarta. Ví dụ khung Servlet 6.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <!-- Servlet/filter/listener declarations theo Jakarta API -->
</web-app>
~~~

Đoạn này chỉ là ví dụ **descriptor** dành cho Servlet 6.0; Spring 7/Web Flow 4 yêu cầu **Servlet 6.1** nên phải chọn descriptor/server thích hợp. Với Spring Boot dùng embedded server và Java Config, bạn có thể không cần `web.xml`; đừng tạo descriptor chỉ để “sửa” namespace.

## 10. Form binding và Bean Validation thay đổi thế nào?

Trong hành trình đặt chỗ, form có thể gửi `visitDate=2027-02-20` và `attendeeCount=2`. **Binding** chuyển chuỗi thành `LocalDate` và `Integer`, còn **validation** kiểm tra ngày, số lượng và các ràng buộc. Khi nâng từ Spring 5 lên Spring 6, các class **Spring MVC binder/formatter** vẫn nằm ở package `org.springframework.*`; nhưng nhóm API **Bean Validation** chuyển từ `javax.validation` sang `jakarta.validation`.

Ví dụ DTO cho **Spring Framework 6/Web Flow 3**:

~~~java
package com.example.booking;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {
    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate visitDate;

    @Min(1)
    private int attendeeCount = 1;

    @NotBlank
    @Email
    private String email;

    public LocalDate getVisitDate() { return visitDate; }
    public void setVisitDate(LocalDate date) { this.visitDate = date; }

    public int getAttendeeCount() { return attendeeCount; }
    public void setAttendeeCount(int count) { this.attendeeCount = count; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Trong Spring 5, cùng các ràng buộc tương đương thường được import từ `javax.validation.constraints.*`. **Tên annotation giống nhau không làm chúng là cùng một annotation**: Jakarta Validation provider sẽ tìm các annotation `jakarta.validation.*` tương ứng. Nếu provider cũ không hiểu metadata mới hoặc provider mới không nhận metadata cũ, một số validation có thể **không được thực thi đúng** dù ứng dụng biên dịch.

Một flow binding đơn giản:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.BookingForm"/>
    <view-state id="details" view="booking/details" model="booking">
        <binder>
            <binding property="visitDate" required="true"/>
            <binding property="attendeeCount" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="next" to="review"/>
    </view-state>
    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="finished"/>
    </view-state>
    <end-state id="finished" view="booking/finished"/>
</flow>
~~~

Đây là **flow minh họa**: cần Spring MVC/Web Flow configuration, view templates, Bean Validation provider và quy tắc nghiệp vụ trước khi chạy. Các property `visitDate`/`email` được phép bind; điều đó không cho phép client sửa `ownerId`, `price` hoặc `status`. **Đổi từ `javax.validation` sang `jakarta.validation` không thay thế binding whitelist, CSRF hay phân quyền**.

### 10.1. Đừng nhầm validation với conversion

| Trường hợp | Cơ chế chính | Kỳ vọng |
| --- | --- | --- |
| `visitDate=khong-phai-ngay` | Conversion/formatting | Báo lỗi kiểu ngày trước khi chuyển state |
| `attendeeCount=abc` | Conversion | Lỗi chuyển `String` thành số |
| `attendeeCount=0` | Jakarta Bean Validation | Vi phạm `@Min(1)` |
| `email` trống | Jakarta Bean Validation | Vi phạm `@NotBlank` |
| Dịch vụ đã hết chỗ | Business service/database | Không commit dù form hợp lệ |

Một bản nâng cấp chỉ kiểm tra “ứng dụng khởi động” có thể bỏ sót trường hợp **annotation validation không còn được xử lý**. Hãy gửi form lỗi thật trong integration test và xác minh không chuyển sang state xác nhận.

## 11. JPA, transaction và persistence context của flow

Nếu ứng dụng dùng Hibernate/JPA, `javax.persistence.*` đổi sang `jakarta.persistence.*`:

~~~java
// Source Java EE / Spring Framework 5:
// import javax.persistence.Entity;
// import javax.persistence.Id;

// Source Jakarta / Spring Framework 6+:
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class BookingEntity {
    @Id
    private Long id;

    protected BookingEntity() {}

    public Long getId() { return id; }
}
~~~

Sự chuyển namespace này kéo theo các thành phần liên quan: version Hibernate/EclipseLink, API metadata, `persistence.xml` nếu dùng, custom converters/listeners, JPA Criteria và những thư viện xử lý entity. **Chỉ đổi `@Entity` ở một file là chưa đủ** nếu runtime vẫn cung cấp JPA provider thế hệ `javax`.

Web Flow có thể phối hợp với persistence trong một hành trình dài, nhưng một HTTP flow nhiều bước **không nên giữ một database transaction mở xuyên suốt thời gian người dùng suy nghĩ**. Dữ liệu có thể nằm trong `flowScope`/persistence context theo thiết kế; transaction nghiệp vụ quyết định nên diễn ra trong service và kiểm tra dữ liệu tại thời điểm commit.

Lưu ý cụ thể:

- Một entity được load ở bước `details` có thể đã cũ khi đến `review`; cần kiểm tra version và các bất biến nghiệp vụ.
- `JpaTransactionManager` là class Spring, không tự đổi thành package Jakarta; nhưng đối tượng JPA mà nó tích hợp phải từ thế hệ tương thích.
- Các exception hoặc annotation tự định nghĩa cho transaction cần kiểm tra package cung cấp. Không thay `javax.transaction.xa.*` thuộc Java SE bằng `jakarta.transaction.xa.*` một cách máy móc.
- Nếu phục hồi flow sau session timeout/restart, không giả định entity đang attached hoặc persistence context cũ vẫn hợp lệ.

## 12. Khi ứng dụng dùng Spring Faces/JSF

Spring Web Flow có tích hợp **JSF** qua `spring-faces`; đây là nhánh cần xem riêng so với Web Flow dùng Thymeleaf hoặc JSP.

| Tổ hợp | JSF tham chiếu | API Faces |
| --- | --- | --- |
| Web Flow 2.5 / Spring 5 | JSF 2.2+ | `javax.faces.*` |
| Web Flow 3.0 / Spring 6 | JSF 4.0+ | `jakarta.faces.*` |
| Web Flow 4.0 / Spring 7 | JSF 4.1+ | `jakarta.faces.*` |

Ví dụ JSF bootstrap của thế hệ Jakarta:

~~~xml
<servlet>
    <servlet-name>Faces Servlet</servlet-name>
    <servlet-class>jakarta.faces.webapp.FacesServlet</servlet-class>
</servlet>
~~~

Với JSF đời trước, tên class là `javax.faces.webapp.FacesServlet`. Khi nâng cấp, còn phải đánh giá **Facelets/tag library**, component library (ví dụ PrimeFaces), JSF implementation, Ajax requests, `FacesContext` lifecycle và `JsfFlowHandlerAdapter`. Khi trang dùng một thư viện component chỉ còn `javax.faces.*`, việc sửa import trong code nghiệp vụ không giải quyết dependency đó.

Trong một ứng dụng **không dùng JSF**, không cần thêm `spring-faces` hoặc JSF implementation chỉ vì Web Flow có tính năng hỗ trợ. Mẫu Thymeleaf/Spring MVC sẽ đơn giản hơn ở trục này, nhưng vẫn phải xử lý Servlet, Validation và Security theo Jakarta.

## 13. Quy trình nâng cấp có kiểm soát từ javax sang Jakarta

Một kế hoạch khả thi có thể được triển khai qua các chặng:

~~~mermaid
flowchart TD
    A["Ghi baseline hệ cũ: Java, Spring, SWF, server"] --> B["Kiểm kê javax.* dùng ở đâu"]
    B --> C["Phân nhóm Java SE và EE/Jakarta"]
    C --> D["Chọn Spring + SWF + Servlet container mới"]
    D --> E["Nâng dependency/BOM và thay source có chọn lọc"]
    E --> F["Sửa cấu hình web/JPA/JSF/validation"]
    F --> G["Build + dependency tree"]
    G --> H{"Classpath và runtime thống nhất?"}
    H -->|"Không"| E
    H -->|"Có"| I["Chạy MVC + Web Flow integration tests"]
    I --> J["Kiểm thử bảo mật, scope, session, commit và recovery"]
~~~

### Bước 1 — ghi baseline của hệ thống đang chạy

Ghi lại **JDK build**, **JDK production**, Spring Framework/Boot, SWF, Servlet container, Bean Validation provider, JPA provider, JSF nếu có, Spring Security và ứng dụng triển khai bằng embedded server hay WAR.

Đồng thời tạo các kịch bản nghiệp vụ làm baseline: mở flow, next/back/cancel, lỗi validation, subflow, refresh, login/logout, session timeout và confirm thành công. Mục tiêu là phân biệt regression do migration với lỗi đã tồn tại.

### Bước 2 — phân loại mọi import javax

Tìm trong mã nguồn và file cấu hình:

~~~bash
rg -n "javax\." src
rg -n "javax/" src
rg -n "javax" pom.xml build.gradle
~~~

Lệnh `rg` minh họa cách kiểm kê, chưa được chạy cho bài này. Nếu dự án dùng Gradle Kotlin DSL, thay `build.gradle` bằng `build.gradle.kts` hoặc tìm trong cấu hình tương ứng. Mỗi match phải được phân loại:

- **Java SE giữ nguyên:** `javax.crypto`, `javax.sql`, `javax.net.ssl`, `javax.naming`, `javax.xml.parsers`...
- **Java EE/Jakarta chuyển namespace:** `javax.servlet`, `javax.persistence`, `javax.validation`, `javax.faces`, `javax.el`, `javax.annotation.PostConstruct`...
- **Không rõ nguồn:** xác định artifact và specification, tìm release notes của chính thư viện trước khi sửa.

Kiểm tra thêm XML descriptors, `META-INF/services`, reflective class names, string literals, các plugin annotation processing, generated source và thư viện thứ ba. Không thay tự động trong comment/tên biến, một số đường dẫn XML schema hoặc các package Java SE.

### Bước 3 — nâng nền tảng đồng bộ

Ví dụ với ứng dụng Spring 5/SWF 2.5 đang dự kiến sang Spring 6:

1. Dùng JDK **17+**.
2. Dùng **Spring Framework 6.x**; nếu có Boot, chọn dòng **Boot 3.x** tương ứng.
3. Chọn **Spring Web Flow 3.0.x** với bản vá thích hợp.
4. Dùng Servlet container/runtime **Jakarta**, ví dụ Tomcat 10.1 theo tổ hợp Spring 6.
5. Nâng Bean Validation provider, JPA provider, Spring Security, JSF/component library, template engine và các tích hợp còn dùng namespace cũ.

Nếu mục tiêu là Spring Framework **7**, đi theo **Web Flow 4.x + Servlet 6.1/Jakarta EE 11**, đồng thời kiểm chứng Boot 4/JDK và các dependency liên quan. Nên xem migration giữa 5→6 và 6→7 thành hai chặng kiểm thử khi hệ thống lớn.

### Bước 4 — xác minh dependency tree

Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflow
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jakarta.servlet-api
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jakarta.validation-api
~~~

Đây là **các lệnh người học có thể chạy trong dự án**, không phải kết quả đã được thực thi. Khi dùng WAR, Servlet API có thể thuộc `providedCompile`/`providedRuntime` hoặc do server cung cấp. Vì vậy phải kiểm tra **cả classpath build và lớp thư viện thực sự được tải trong server**.

### Bước 5 — sửa cấu hình theo từng lớp

| Lớp | Việc cần đối chiếu |
| --- | --- |
| Servlet | `Filter`, `ServletContextListener`, request/response/session types, dispatcher registration |
| Spring MVC | `DispatcherServlet`, handler mapping, conversion service, view resolver |
| Spring Security | Filter chain, authentication, CSRF, session fixation/logout, method security |
| Spring Web Flow | Registry/executor, `FlowHandlerMapping`/`FlowHandlerAdapter`, listeners, EL, scopes |
| Binding/Validation | Allowed fields, Jakarta Validation provider, custom validators, message bundles |
| JPA/DB | `jakarta.persistence`, ORM provider, entity mapping, transactions, migrations |
| JSF (nếu dùng) | `jakarta.faces`, component library, Facelets, JSF config |
| Deploy | Servlet container và namespace descriptor đúng thế hệ |

### Bước 6 — chạy lại hành trình từ HTTP tới database

Chỉ khi dependency resolution và application context ổn định, hãy chạy integration tests trên các flow. Test không dừng ở việc compile; phải gửi **HTTP request thực**, phát event thật, bind dữ liệu, validate, kiểm tra session và xác minh service/database không bỏ qua các quy tắc nghiệp vụ.

## 14. Ma trận kiểm thử migration cho Web Flow

Một flow đặt chỗ giả định có ba màn hình `details → review → finished` và một subflow bổ sung thông tin người liên hệ.

| Test | Tác động | Kỳ vọng |
| --- | --- | --- |
| T01 | Khởi động ứng dụng trên servlet container mới | Tạo được `DispatcherServlet` và các bean Web Flow |
| T02 | GET URL bắt đầu flow | Hiển thị đúng `details` |
| T03 | POST `_eventId=next` với ngày hợp lệ | Bind `LocalDate`, chuyển sang `review` |
| T04 | POST ngày không thể parse | Báo lỗi conversion, giữ màn hình nhập |
| T05 | POST email rỗng | Jakarta Bean Validation thật sự chạy; không chuyển state |
| T06 | POST field ngoài whitelist như `ownerId` | Không thay property đặc quyền |
| T07 | Event không thuộc state hiện tại | Không chuyển tới state trái phép |
| T08 | Quay lại từ review | Giữ bản nháp trong scope của execution |
| T09 | Mở subflow, truyền input/output | Đúng kiểu, đúng scope và đúng kết quả |
| T10 | Hai flow trong cùng session | Không trộn bản nháp giữa hai execution |
| T11 | Session timeout trước confirm | Không commit; có đường khởi động lại |
| T12 | Logout rồi đăng nhập tài khoản khác | Flow cũ không tiết lộ hoặc ghi dữ liệu khác quyền |
| T13 | POST thiếu CSRF token | Spring Security chặn theo policy |
| T14 | Confirm hợp lệ | Service kiểm tra quyền và commit chính xác |
| T15 | Hai POST confirm đồng thời | Database/idempotency ngăn ghi trùng |
| T16 | WAR deploy lên server Servlet thiếu mức yêu cầu | Nhận diện như lỗi cấu hình, không tuyên bố tương thích |
| T17 | JSF form/Ajax nếu sử dụng | `jakarta.faces`/`spring-faces` hoạt động nhất quán |
| T18 | Mở lại execution key cũ | Xử lý expired execution an toàn |

**Tách các lớp test:** Unit test cho conversion/validator; flow state test cho event/transition; MVC integration test cho request, Spring Security và templates; database integration test cho transaction và idempotency. Một flow chạy được với mocked service **không chứng minh persistence đã tương thích**.

## 15. Tình huống lỗi và phương pháp chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Điểm kiểm tra đầu tiên |
| --- | --- | --- |
| `javax.servlet.Filter` không được nhận | Custom filter hoặc JAR cũ | Source, artifact version và container |
| `jakarta.servlet.http.HttpServletRequest` không tìm thấy | Runtime chỉ có Java EE/`javax` | Servlet container đang chạy thực tế |
| `NoClassDefFoundError: javax/validation/...` | Validation implementation/integration cũ | Dependency tree và imports |
| `@NotNull` không được kích hoạt trong form | Annotation/provider sai thế hệ hoặc chưa cấu hình | Bean Validation provider và view-state validation |
| `ClassCastException` giữa javax/jakarta | Cố ép hai kiểu khác namespace | Chữ ký method và lớp thư viện gốc |
| Flow URL trả 404 | FlowRegistry/FlowHandlerMapping không đăng ký hoặc mapping sai | Log startup, MVC mapping |
| Form nhận dữ liệu nhưng `next` thất bại | Conversion, validation hoặc event không đúng | Binder/MessageContext, mã lỗi |
| JSF không khởi động | Faces API/implementation/component lib sai | `spring-faces`, FacesServlet và JSF version |
| `EntityManager` không được tạo | JPA API/provider/class mapping sai | JPA provider và Spring transaction config |
| Test qua nhưng WAR deploy lỗi | Mismatch embedded/test container và production | Runtime container, `provided` dependencies |
| Session bị mất sau upgrade | Cookie, reverse proxy, session store hoặc repository | HTTP cookie, timeout, node routing |

**Phân biệt gốc lỗi:** thiếu class thường ở classpath/API, không tạo bean ở integration, sai binding ở converter/validator, chuyển nhánh sai ở flow, còn quyền hoặc commit trùng ở service/database. Không sửa thiếu dependency bằng cách nạp tùy tiện cả hai thế hệ javax và Jakarta vào chung runtime.

## 16. Bài tập thực hành có đáp án

### Bài A — import nào nên đổi?

Phân loại các import sau khi migrate từ Spring 5/Web Flow 2.5 sang Spring 6/Web Flow 3:

~~~java
import javax.servlet.http.HttpServletRequest;
import javax.validation.constraints.NotBlank;
import javax.persistence.Entity;
import javax.faces.context.FacesContext;
import javax.crypto.Cipher;
import javax.sql.DataSource;
import javax.xml.parsers.DocumentBuilderFactory;
~~~

**Đáp án:** bốn dòng đầu thuộc Servlet, Bean Validation, JPA, JSF cần chuyển thành `jakarta.servlet...`, `jakarta.validation...`, `jakarta.persistence...` và `jakarta.faces...` nếu dự án thực sự dùng chúng; ba dòng sau thuộc Java SE nên giữ nguyên `javax.crypto`, `javax.sql` và `javax.xml.parsers`.

### Bài B — tìm xung đột trong dependency

Giả sử dependency tree cho thấy:

~~~text
Java: 17
Spring Framework: 6.2.x
Spring Web Flow: 2.5.1.RELEASE
Servlet API: jakarta.servlet 6.x
Validation: javax.validation 2.x
~~~

**Câu hỏi:** Đâu là các điểm chặn?

**Đáp án:** Web Flow 2.5 thuộc nền Spring 5/`javax` trong khi Spring 6 và Servlet đã ở Jakarta; Bean Validation cũng còn ở namespace cũ. Phải nâng SWF sang nhánh 3.x phù hợp, nâng validation/provider và các integration khác, kiểm tra lại classpath rồi chạy test. Java 17 đơn thuần không xử lý những xung đột đó.

### Bài C — đọc nhận định đúng/sai

1. “Đã nâng lên Java 17 thì có thể đổi toàn bộ import `javax` thành `jakarta`.” — **Sai**: Java SE vẫn có những package `javax`; đồng thời cần nâng cả framework và container.
2. “Jakarta EE 8 đã đổi tất cả class thành `jakarta.*`.” — **Sai**: đổi namespace bắt đầu từ Jakarta EE 9.
3. “Spring Web Flow `flowScope` đổi tên sau khi lên Jakarta.” — **Sai**: đây là khái niệm scope riêng của Web Flow.
4. “Ứng dụng compile thành công thì mọi validator đã chạy đúng.” — **Sai**: phải test binding/validation bằng request thật và đúng provider.
5. “Tomcat 11 đáp ứng Servlet 6.1 cho baseline Spring 7/SWF 4.” — **Đúng về mức Servlet**, nhưng vẫn phải kiểm tra các dependency và cấu hình ứng dụng.

### Bài D — thiết kế kiểm thử phục hồi

Trong một flow `details → review → confirm`, người dùng logout khi đang ở `review` rồi đăng nhập bằng tài khoản khác. Hãy viết test kiểm tra request tiếp tục bằng execution URL cũ không xem được bản nháp hoặc commit theo quyền cũ. Nêu rõ trách nhiệm của Spring Security, Web Flow execution repository, service authorization và database. Lưu ý session/cookie và expiration không tự bảo đảm quyền sở hữu nếu service không kiểm tra.

## 17. Checklist trước khi chốt migration

- [ ] Biết rõ dự án dùng Java EE 8, Jakarta EE 8, Jakarta EE 9/10 hay 11.
- [ ] Không nhầm Jakarta EE 8 với việc đổi namespace `jakarta.*`.
- [ ] Đã tách `javax.*` thuộc Java SE khỏi nhóm API doanh nghiệp cần đổi.
- [ ] JDK build/runtime, Spring Framework, SWF và Servlet container tương thích.
- [ ] Spring MVC, filter chain và Web Flow integration cùng namespace Servlet.
- [ ] Không còn JAR cũ dùng `javax.servlet`/`javax.validation` trên đường code Jakarta.
- [ ] Spring Boot BOM hoặc dependency management đã được kiểm tra ở runtime classpath.
- [ ] Web Flow XML giữ đúng schema Spring; các class reference đã được rà soát.
- [ ] `web.xml`, `persistence.xml`, Faces config và ServiceLoader files (nếu có) đã được kiểm tra.
- [ ] Bean Validation provider, JPA implementation, JSF và Security cùng thế hệ.
- [ ] Binding whitelist, validation, CSRF và object authorization còn hoạt động.
- [ ] `flowScope`/`conversationScope` và HTTP session không mất dữ liệu hoặc rò dữ liệu khi back/timeout.
- [ ] Flow integration test chạy các event, transition, subflow và lỗi phục hồi.
- [ ] Service/database test bảo đảm đúng nghiệp vụ trước và sau nâng cấp.
- [ ] Đã xem bản vá và security advisories của các dependency hiện hành.

## 18. Tài liệu tham khảo chính thức

1. [Eclipse Foundation — Javax to Jakarta Namespace Ecosystem Progress](https://jakarta.ee/blogs/javax-jakartaee-namespace-ecosystem-progress/) — lịch sử Jakarta EE 8/9 và thay đổi package.
2. [Spring Framework — Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) — ma trận JDK và Java EE/Jakarta EE.
3. [Spring Framework — Spring 6.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes) — baseline Java 17/Jakarta EE 9+ và các API cần đổi.
4. [Spring Framework — Upgrading to Spring 6.x](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x) — migration Servlet, validation và JPA.
5. [Spring Web Flow 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) — Web Flow trong hệ Spring 5.
6. [Spring Web Flow 3.0.2 Reference](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — Web Flow trên Java 17/Spring 6 và Jakarta.
7. [Spring Web Flow 4.0.2 Reference](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/) — Spring 7, Servlet 6.1, tích hợp JSF 4.1.
8. [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes) — Servlet 6.1 và Jakarta EE 11 baseline.

**Điểm cần nhớ:** **Jakarta EE 8 vẫn dùng `javax.*`**, còn **Jakarta EE 9 mới chuyển API doanh nghiệp sang `jakarta.*`**; các `javax.*` thuộc Java SE vẫn giữ nguyên. Với Spring Web Flow, hãy chọn cùng thế hệ **Spring 5 + SWF 2.5 + javax**, **Spring 6 + SWF 3 + Jakarta** hoặc **Spring 7 + SWF 4 + Servlet 6.1**. Khi nâng cấp, cần chuyển nhất quán Servlet/validation/persistence/JSF và kiểm thử lại toàn bộ hành trình, vì việc compile thành công chưa chứng minh các flow, session và hành động nghiệp vụ đã tương thích.
