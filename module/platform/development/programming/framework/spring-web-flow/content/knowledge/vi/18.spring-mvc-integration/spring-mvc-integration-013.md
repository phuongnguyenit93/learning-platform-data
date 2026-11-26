# Kiểm tra cấu hình khi triển khai bằng WAR hoặc ứng dụng Spring Boot

Spring Web Flow chạy bên trong ứng dụng web Spring MVC. Một flow có thể được định nghĩa đúng nhưng vẫn không hoạt động sau khi triển khai nếu servlet không nhận request, flow registry không tìm thấy file định nghĩa, handler mapping bị cấu hình sai thứ tự hoặc view không được đóng gói vào artifact. Vì vậy, kiểm tra triển khai cần bao quát cả cấu hình Spring MVC, tài nguyên flow, view, session và môi trường servlet container.

Bài học thuộc chương **Tích hợp Spring MVC** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Các thành phần phải hoạt động cùng nhau

Khi một request đi vào flow, Spring MVC tiếp nhận request qua DispatcherServlet. Handler mapping nhận diện URL thuộc flow và chọn FlowHandlerAdapter. Adapter chuyển request cho FlowExecutor, thành phần điều phối việc khôi phục hoặc khởi chạy flow execution. Flow registry cung cấp định nghĩa flow; flow builder services cung cấp các dịch vụ cần thiết khi xây dựng flow, chẳng hạn view factory và conversion service.

Các thành phần chính:

| Thành phần | Vai trò khi triển khai |
|---|---|
| DispatcherServlet | Điểm tiếp nhận request của Spring MVC |
| FlowHandlerMapping | Nhận diện URL được ánh xạ tới flow |
| FlowHandlerAdapter | Chuyển request đã định tuyến tới FlowExecutor |
| FlowExecutor | Khởi chạy hoặc tiếp tục flow execution |
| FlowDefinitionRegistry | Đăng ký và tra cứu định nghĩa flow |
| FlowExecutionRepository | Lưu và khôi phục trạng thái flow execution giữa các request |
| FlowBuilderServices | Cung cấp dịch vụ dùng khi xây dựng flow, như view factory và conversion service |
| ViewResolver / view technology | Tìm và render view mà flow yêu cầu |

Có thể hình dung luồng request:

~~~mermaid
flowchart TD
    A["Trình duyệt gửi request"] --> B["Servlet container"]
    B --> C["DispatcherServlet"]
    C --> D["FlowHandlerMapping"]
    D --> E["FlowHandlerAdapter"]
    E --> F["FlowExecutor"]
    F --> G["FlowExecutionRepository"]
    F --> H["FlowDefinitionRegistry"]
    F --> I["Flow state / event / transition"]
    I --> J["ViewResolver và view"]
    J --> K["Response về trình duyệt"]
~~~

FlowHandlerMapping và FlowHandlerAdapter là cầu nối giữa Spring MVC và Web Flow. Nếu thiếu một trong hai hoặc chúng không cùng tham chiếu đúng registry/executor, URL flow có thể bị xử lý như một controller thông thường hoặc không tìm được handler.

## 2. Kiểm tra cấu hình khi đóng gói WAR truyền thống

Với ứng dụng Spring MVC triển khai thành WAR lên Tomcat, Jetty hoặc servlet container tương thích, cần xác nhận servlet được đăng ký và Spring application context được khởi tạo đúng.

Một cấu hình web.xml điển hình:

~~~xml
<web-app>
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/spring/root-context.xml</param-value>
    </context-param>

    <listener>
        <listener-class>
            org.springframework.web.context.ContextLoaderListener
        </listener-class>
    </listener>

    <servlet>
        <servlet-name>dispatcher</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>/WEB-INF/spring/mvc-context.xml</param-value>
        </init-param>
        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>dispatcher</servlet-name>
        <url-pattern>/</url-pattern>
    </servlet-mapping>
</web-app>
~~~

Đây là ví dụ tối giản để minh họa hai application context:

- Root context được tạo bởi ContextLoaderListener, thường chứa service, repository và các bean dùng chung.
- DispatcherServlet tạo servlet context, chứa cấu hình Spring MVC như handler mapping, handler adapter và view resolver.
- Servlet context có thể sử dụng bean từ root context thông qua quan hệ context cha - con.
- Các bean FlowHandlerMapping và FlowHandlerAdapter phải được đăng ký trong context mà DispatcherServlet dùng để định tuyến và xử lý request. Flow registry và executor có thể được đặt trong cùng context hoặc context cha mà servlet context nhìn thấy được.

Không nên khai báo cùng một bean ở cả root context và servlet context nếu không có chủ đích, vì có thể tạo hai instance với trạng thái hoặc cấu hình khác nhau.

### Cấu hình flow registry và handler

Một ví dụ cấu hình XML cho Web Flow:

~~~xml
<webflow:flow-registry id="flowRegistry"
                       base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern value="/**/*-flow.xml" />
</webflow:flow-registry>

<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry" />

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="order" value="-1" />
    <property name="flowRegistry" ref="flowRegistry" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Các điểm cần kiểm tra:

1. Namespace và schema Web Flow được khai báo đúng trong file XML chứa cấu hình.
2. base-path trỏ tới thư mục thực sự chứa flow definition trong WAR đã đóng gói.
3. flow-location-pattern khớp tên file flow, ví dụ booking-flow.xml.
4. FlowHandlerMapping tham chiếu đúng flowRegistry.
5. FlowHandlerAdapter tham chiếu đúng flowExecutor.
6. Thứ tự FlowHandlerMapping cho phép nó nhận diện URL flow trước các mapping tổng quát có thể bắt cùng đường dẫn.
7. Các view được tham chiếu trong flow definition tồn tại và được view resolver xử lý.

Giá trị order phụ thuộc vào toàn bộ các handler mapping trong ứng dụng. Ví dụ đặt -1 giúp mapping flow có độ ưu tiên cao hơn mapping mặc định có order 0; hãy kiểm tra lại nếu ứng dụng đã có mapping tùy chỉnh với độ ưu tiên cao hơn.

Với JSP, view resolver thường trỏ tới thư mục không cho phép truy cập trực tiếp từ trình duyệt:

~~~xml
<bean class="org.springframework.web.servlet.view.InternalResourceViewResolver">
    <property name="prefix" value="/WEB-INF/views/" />
    <property name="suffix" value=".jsp" />
</bean>
~~~

Ví dụ view booking/review có thể được ánh xạ thành /WEB-INF/views/booking/review.jsp. Đường dẫn thực tế phải khớp cách ứng dụng tổ chức view và cách flow khai báo view.

## 3. Kiểm tra cấu hình khi chạy bằng Spring Boot

Spring Boot tự cấu hình DispatcherServlet và nhiều thành phần Spring MVC cơ bản. Tuy nhiên, không nên mặc định rằng mọi cấu hình Spring Web Flow đã tự xuất hiện chỉ vì thêm dependency. Ứng dụng vẫn phải đăng ký flow registry, flow executor, FlowHandlerMapping và FlowHandlerAdapter theo phiên bản thư viện đang dùng.

Một cách tích hợp là giữ cấu hình Web Flow trong XML rồi import vào application context của Boot:

~~~java
@SpringBootApplication
@ImportResource("classpath:/spring/webflow-config.xml")
public class BookingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookingApplication.class, args);
    }
}
~~~

File XML được import phải chứa các bean registry/executor và handler mapping/adapter cần thiết. Nếu dùng Java configuration, có thể khai báo hai bean MVC sau khi đã có FlowDefinitionRegistry và FlowExecutor:

~~~java
@Configuration
public class WebFlowMvcConfiguration {

    @Bean
    public FlowHandlerMapping flowHandlerMapping(
            FlowDefinitionRegistry flowRegistry) {
        FlowHandlerMapping mapping = new FlowHandlerMapping();
        mapping.setFlowRegistry(flowRegistry);
        mapping.setOrder(-1);
        return mapping;
    }

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter(
            FlowExecutor flowExecutor) {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor);
        return adapter;
    }
}
~~~

Đoạn Java chỉ thể hiện phần kết nối Spring MVC. Ứng dụng vẫn cần tạo FlowDefinitionRegistry, FlowExecutor và cấu hình flow builder services phù hợp. API khởi tạo registry và builder có thể khác theo phiên bản Spring Web Flow, vì vậy hãy dùng đúng tài liệu của phiên bản đã chọn.

Không thêm @EnableWebMvc một cách máy móc vào ứng dụng Boot. Annotation này chuyển quyền cấu hình MVC sang ứng dụng và có thể làm một phần auto-configuration của Boot không còn được áp dụng. Chỉ dùng khi chủ động quản lý toàn bộ cấu hình MVC và đã kiểm tra các cấu hình view, static resource, message converter và handler mapping cần thiết.

## 4. Chọn vị trí flow definition và view cho từng kiểu đóng gói

Một lỗi thường gặp là cấu hình đường dẫn tài nguyên chạy được trong môi trường IDE nhưng không tồn tại sau khi đóng gói.

| Kiểu triển khai | Vị trí tài nguyên thường dùng | Điểm cần xác minh |
|---|---|---|
| WAR truyền thống | Flow dưới /WEB-INF/flows, view JSP dưới /WEB-INF/views | Các file được đưa vào đúng vị trí trong WAR |
| Boot executable JAR | Flow definition trong classpath, ví dụ src/main/resources/flows | Registry dùng đường dẫn classpath và pattern khớp tài nguyên trong JAR |
| Boot executable WAR | Flow definition trong classpath hoặc vị trí web application được cấu hình có chủ đích | Kiểm tra cả cách chạy bằng java -jar và khi triển khai vào servlet container |

Nếu flow definition nằm trong src/main/resources/flows, registry có thể dùng base path theo classpath, chẳng hạn classpath:/flows. Cần xác minh pattern quét tài nguyên hoạt động với cách đóng gói đang dùng, đặc biệt khi chạy từ JAR. Không nên giả định một đường dẫn /WEB-INF/... luôn có thể truy cập như file hệ thống trong executable JAR.

Với view JSP, cần chú ý giới hạn đóng gói của Spring Boot: JSP không phù hợp với executable JAR chạy bằng embedded container. Nếu cần JSP, thường triển khai dưới dạng WAR với servlet container hỗ trợ JSP. Nếu muốn chạy executable JAR, hãy cân nhắc view technology được hỗ trợ tốt trong mô hình đó, chẳng hạn Thymeleaf, và cấu hình view resolver tương ứng.

Ngoài flow definition và view, hãy kiểm tra các tài nguyên liên quan:

- File message bundle phục vụ thông báo validation và nhãn giao diện.
- Template, fragment và static resource như CSS, JavaScript, hình ảnh.
- File cấu hình locale, timezone và conversion service nếu flow sử dụng.
- Tài nguyên upload hoặc file mẫu mà action trong flow cần đọc.
- Tên flow ID, tên view và đường dẫn tương đối giữa các flow/subflow.

## 5. Kiểm tra dependency và tương thích phiên bản

Spring Web Flow phụ thuộc vào Spring Framework, Spring MVC và Servlet API. Trước khi triển khai, cần kiểm tra các phiên bản có tương thích với nhau hay không.

Các điểm cần rà soát:

- Phiên bản Spring Web Flow tương thích với phiên bản Spring Framework và Spring MVC mà ứng dụng sử dụng.
- Spring Boot BOM quản lý các dependency Spring Boot, nhưng không nên mặc định BOM đó đã quản lý phiên bản Spring Web Flow. Kiểm tra dependency management và khai báo phiên bản Web Flow rõ ràng nếu cần.
- Phiên bản Java phù hợp với yêu cầu của Spring Framework và Spring Boot đã chọn.
- Servlet API phải cùng hệ namespace mà container và thư viện sử dụng. Không trộn javax.servlet và jakarta.servlet trong cùng một cấu hình không tương thích.
- Trong WAR chạy trên container bên ngoài, servlet container dependency thường được đánh dấu provided để không đóng gói một bản servlet container thứ hai vào ứng dụng.
- Tránh đưa nhiều phiên bản khác nhau của cùng thư viện Spring vào WAR hoặc executable JAR.

Với Maven, dependency Web Flow có thể được khai báo như sau; phiên bản cần chọn theo ma trận tương thích của dự án:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>${spring-webflow.version}</version>
</dependency>
~~~

Đừng chỉ kiểm tra dependency tree ở máy phát triển. Hãy kiểm tra artifact cuối để phát hiện thư viện bị loại trừ, trùng phiên bản hoặc thiếu trong quá trình đóng gói.

## 6. Cấu hình servlet mapping và thứ tự handler

FlowHandlerMapping cần nhận các URL thuộc flow trước khi một handler mapping tổng quát xử lý chúng. Nếu controller có mapping rộng như /**, hoặc có mapping cùng đường dẫn với flow, request có thể bị định tuyến sai.

Khi rà soát, hãy kiểm tra:

1. URL flow có được nhận diện bởi FlowHandlerMapping không?
2. Thứ tự handler mapping có ưu tiên đúng không?
3. URL controller và URL flow có bị trùng không?
4. Servlet mapping có đúng với context path và servlet path khi deploy không?
5. Static resource có bị handler mapping flow nhận nhầm không?
6. Các URL forward tới JSP có còn hoạt động không?

Với ứng dụng Spring MVC thông thường, servlet mapping / thường dễ phối hợp với view resolver hơn mapping /*. Mapping /* có thể can thiệp vào request forward tới JSP và các servlet khác, dẫn tới lỗi render khó phát hiện. Nếu ứng dụng có nhiều DispatcherServlet hoặc servlet riêng, hãy xác định rõ servlet nào chịu trách nhiệm xử lý flow.

## 7. Session, execution repository và triển khai nhiều node

Flow execution cần được lưu và khôi phục giữa các request. Cấu hình repository và conversation manager quyết định trạng thái execution được quản lý ra sao. Trong cấu hình web phổ biến, dữ liệu conversation gắn với HTTP session, vì vậy session timeout hoặc mất session có thể khiến người dùng không tiếp tục được flow cũ.

Trong môi trường có load balancer và nhiều node:

- Nếu session lưu trong bộ nhớ của từng node, cần cơ chế định tuyến ổn định như session affinity để request của cùng session đến đúng node.
- Nếu hạ tầng hỗ trợ session dùng chung hoặc replication, hãy xác minh dữ liệu session và đối tượng được lưu có thể được tuần tự hóa theo yêu cầu của nền tảng.
- Kiểm tra chính sách timeout, cookie session, HTTPS và cấu hình SameSite phù hợp với cách ứng dụng được truy cập.
- Không lưu dữ liệu nghiệp vụ lớn hoặc bí mật dài hạn vào flow scope hay session chỉ để tránh truy vấn lại.
- Nếu cần tiếp tục hồ sơ sau khi session hết hạn, hãy lưu bản nháp bền vững trong database và tạo flow execution mới sau khi xác thực người dùng.

Session affinity giúp các request tiếp tục truy cập cùng trạng thái trong mô hình session cục bộ, nhưng không thay thế thiết kế phục hồi khi node dừng hoặc session hết hạn. Hãy thử nghiệm hành vi khi một node bị restart và khi người dùng tiếp tục một URL execution cũ.

## 8. Bảo mật request và dữ liệu của flow

Các URL flow vẫn là endpoint của ứng dụng web và cần được bảo vệ theo cùng chính sách bảo mật với các controller khác.

- Áp dụng authentication và authorization cho URL khởi chạy flow cũng như URL tiếp tục execution.
- Với form POST, giữ bảo vệ CSRF của Spring Security và bảo đảm token được render vào form.
- Không loại trừ toàn bộ đường dẫn flow khỏi security filter chain chỉ để tránh lỗi binding.
- Kiểm tra quyền truy cập tài nguyên trong service nghiệp vụ ở mỗi bước quan trọng; biết execution key không đồng nghĩa có quyền đọc hoặc sửa dữ liệu.
- Escape nội dung render và encode dữ liệu đưa vào URL.
- Dùng HTTPS, cookie session an toàn và giới hạn thời gian tồn tại của session theo chính sách ứng dụng.
- Với upload file, kiểm tra kích thước, loại nội dung và quyền truy cập; không dựa vào tên file do client gửi.

Nếu dùng filter như CharacterEncodingFilter, security filter hoặc multipart support, kiểm tra thứ tự filter để request được giải mã, xác thực và phân tích multipart trước khi flow xử lý dữ liệu. Với Spring Boot, cấu hình filter và multipart nên dùng cơ chế cấu hình của Boot thay vì đăng ký thêm một servlet hoặc filter trùng lặp.

## 9. Kiểm tra view resolver và tích hợp MVC

Một flow có thể chạy qua state đúng nhưng vẫn trả lỗi khi render vì view resolver không tìm thấy template hoặc tên view không khớp. Hãy kiểm tra:

- View ID trong flow definition có được ánh xạ tới đúng file JSP/template không?
- Prefix và suffix của view resolver có khớp vị trí tài nguyên sau đóng gói không?
- JSP có nằm dưới WEB-INF để không bị truy cập trực tiếp ngoài luồng MVC không?
- Message source có được nạp để hiển thị lỗi conversion và validation không?
- Locale resolver có tạo locale mong muốn cho người dùng không?
- Conversion service được cấu hình cho flow builder có chứa converter cần thiết không?
- Static resources có được phục vụ qua đường dẫn và handler phù hợp không?

Đối với ứng dụng Boot, hãy kiểm tra cấu hình view technology sau khi chạy từ artifact thực tế. Một trang hoạt động trong IDE không chứng minh view sẽ được tìm thấy khi chạy từ JAR/WAR hoặc trong servlet container bên ngoài.

## 10. Quy trình kiểm tra trước và sau triển khai

Có thể chia kiểm tra thành ba giai đoạn.

**Trước khi đóng gói**

1. Xác nhận dependency và phiên bản Spring Web Flow, Spring MVC, Spring Boot, Java và Servlet API tương thích.
2. Kiểm tra FlowDefinitionRegistry tìm thấy tất cả flow definition và subflow.
3. Kiểm tra FlowExecutor, FlowHandlerMapping, FlowHandlerAdapter và thứ tự mapping.
4. Kiểm tra view resolver, conversion service, message source và security.
5. Chạy flow test cho các đường đi chính, validation lỗi và event không hợp lệ.

**Sau khi tạo artifact**

1. Mở WAR/JAR và xác nhận flow definition, view, message bundle và dependency cần thiết có mặt.
2. Kiểm tra không có dependency Spring hoặc Servlet API bị đóng gói trùng phiên bản.
3. Kiểm tra cấu hình đường dẫn tài nguyên tương ứng với kiểu đóng gói.
4. Với JSP, xác nhận ứng dụng được đóng gói theo kiểu triển khai hỗ trợ JSP.

**Sau khi triển khai lên môi trường**

1. Kiểm tra log khởi động để xác nhận registry và flow builder được tạo thành công.
2. Truy cập URL khởi chạy một flow và xác nhận view đầu tiên được render.
3. Gửi event qua form và liên kết để xác nhận execution được tiếp tục.
4. Thử validation thất bại, quay lại, hủy và hoàn tất flow.
5. Kiểm tra request sau session timeout và URL execution cũ.
6. Thử nhiều tab và request đồng thời.
7. Nếu chạy nhiều node, kiểm tra định tuyến session và hành vi khi node restart.
8. Kiểm tra log, health endpoint và thông báo lỗi để bảo đảm không lộ stack trace hoặc dữ liệu nhạy cảm.

Bảng chẩn đoán nhanh:

| Triệu chứng | Khu vực cần kiểm tra đầu tiên |
|---|---|
| URL flow trả về 404 | FlowHandlerMapping, flow ID, servlet mapping và flow registry |
| URL bị controller xử lý | Thứ tự handler mapping và các mapping wildcard |
| Flow không khởi chạy | Flow definition location, registry và log khởi tạo |
| Flow chạy nhưng không render được view | View ID, view resolver và vị trí template/JSP |
| Lỗi khi gửi form | FlowExecutionUrl, event ID, binding, converter, validation và CSRF |
| Chạy được ở IDE nhưng lỗi khi đóng gói | Resource path, WAR/JAR contents và dependency |
| Request sau một thời gian không tiếp tục được | Session timeout, execution repository và conversation lifecycle |
| Lỗi chỉ xuất hiện khi chạy nhiều node | Session affinity, session replication và khả năng tuần tự hóa |

## 11. Checklist triển khai

Trước khi phát hành, có thể dùng checklist sau để rà soát:

- [ ] Flow registry tìm thấy flow gốc và subflow.
- [ ] Flow executor được cấu hình với đúng registry.
- [ ] FlowHandlerMapping và FlowHandlerAdapter được đăng ký trong MVC context phù hợp.
- [ ] Thứ tự mapping không xung đột với controller hoặc mapping tổng quát.
- [ ] Servlet mapping và context path đúng với môi trường triển khai.
- [ ] Flow definition, JSP/template, message bundle và static resource có trong artifact.
- [ ] View resolver, conversion service và locale resolver hoạt động.
- [ ] Dependency Spring, Web Flow, Java và Servlet API tương thích.
- [ ] Security, CSRF, HTTPS và session cookie được cấu hình.
- [ ] Session timeout và lỗi execution hết hạn có đường xử lý rõ ràng.
- [ ] Các luồng chính, validation, nhiều tab và request đồng thời đã được kiểm thử.
- [ ] Artifact đã được chạy thử trong môi trường gần với production.

## 12. Kết luận

Triển khai Spring Web Flow thành công đòi hỏi sự phối hợp giữa servlet container, Spring MVC, flow registry, flow executor, execution repository và view technology. Với WAR truyền thống, cần kiểm tra web.xml, application context và vị trí tài nguyên trong web application. Với Spring Boot, DispatcherServlet được auto-configure nhưng phần tích hợp Web Flow vẫn cần được đăng ký và kiểm tra rõ ràng.

Hãy xác minh artifact thực tế thay vì chỉ dựa vào cấu hình trong IDE. Khi flow definition, handler mapping, view resolver, session, dependency và bảo mật đều được kiểm tra sau đóng gói, các hành trình nhiều bước sẽ có khả năng hoạt động ổn định hơn khi chuyển từ môi trường phát triển sang môi trường triển khai.
