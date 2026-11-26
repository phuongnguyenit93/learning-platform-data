# Đặt chỗ với tìm kiếm, chọn dịch vụ và xác nhận

Một ứng dụng đặt chỗ có nhiều bước: người dùng **tìm dịch vụ**, **chọn dịch vụ**, **xem lại thông tin** và **xác nhận**. Trong lúc đó, giá có thể đổi, suất cuối cùng có thể bị người khác đặt, người dùng có thể quay lại màn hình trước hoặc gửi nút xác nhận hai lần. Đó là một tình huống thực tế để kết hợp **Spring Web Flow (SWF)** với **Spring MVC, form binding, validation, scope, session, security và transaction**.

Bài thực hành thuộc chương **Thực hành tổng hợp** của module `SPRING_WEB_FLOW`. Ta xây dựng luồng đặt chỗ cho các dịch vụ có lịch, ví dụ workshop, tư vấn hoặc trải nghiệm trong ngày. Hướng dẫn lấy **Java 17 + Spring Framework 6.x + Spring Web Flow 3.x + Spring MVC/Thymeleaf** làm môi trường minh họa. Các nguyên tắc có thể chuyển sang Web Flow 4.x/Spring 7 khi sử dụng tổ hợp dependency và Servlet API tương thích.

> **Phạm vi:** Bài cung cấp cấu trúc, flow XML, hợp đồng Java, mẫu màn hình và kịch bản kiểm thử. Để chạy thành ứng dụng hoàn chỉnh, bạn cần triển khai catalog/repository, tạo các class được nhắc đến, cấu hình database/Spring Security, bổ sung template đầy đủ và kiểm thử trên bộ dependency thực tế. Không coi các snippet tách rời là một ứng dụng đã biên dịch, đóng gói và triển khai thành công.

## 1. Mục tiêu và đầu ra

Sau khi thực hành, bạn có thể:

1. Chuyển hành trình đặt chỗ thành **state, event, transition và end-state**.
2. Sử dụng `view-state` để nhập form, `action-state` để gọi service, `flowScope` để giữ bản nháp qua các bước.
3. Tích hợp `FlowRegistry`, `FlowExecutor` và handler của Web Flow vào `DispatcherServlet` của Spring MVC.
4. Bind và validate **đúng những field người dùng được sửa** ở từng màn hình; chuyển `String` từ request thành `LocalDate` hoặc `Long`.
5. Truy vấn lại catalog, hiển thị báo giá server tính và kiểm tra giá/chỗ trống lần cuối khi commit.
6. Tổ chức xác nhận bằng transaction có kiểm soát quyền, cạnh tranh và **idempotency**.
7. Kiểm thử cả đường đi thành công, sai dữ liệu, đổi giá, hết chỗ, hủy bỏ, quay lại, timeout và submit lặp.

**Đầu ra mong muốn:** sau khi nhập từ khóa và ngày, người dùng thấy các dịch vụ phù hợp, chọn một dịch vụ, xem giá và thông tin liên hệ rồi nhận mã đặt chỗ sau xác nhận. Không tạo booking khi hủy hoặc khi kiểm tra nghiệp vụ thất bại.

## 2. Yêu cầu nghiệp vụ và giới hạn tin cậy

| Bước | Dữ liệu do client nhập | Dữ liệu server phải kiểm soát | Thành công khi |
| --- | --- | --- | --- |
| Tìm kiếm | `keyword`, `visitDate` | Danh sách dịch vụ, ngày khả dụng | Trả danh sách theo tiêu chí |
| Chọn | `serviceId` | Quyền xem/chọn, thông tin dịch vụ, chỗ trống tham khảo | ID hợp lệ, chuyển tới báo giá |
| Xem lại | `fullName`, `email` | Giá, tiền tệ, chính sách và thông tin dịch vụ | Dữ liệu liên hệ hợp lệ |
| Xác nhận | Event `confirm` | Danh tính, quyền, giá, suất còn lại, transaction | Booking bền vững được tạo đúng một lần |
| Hủy/quay lại | Event `cancel`/`back` | Vòng đời execution và trạng thái đã lưu | Điều hướng đúng, không tạo giao dịch |

Những yêu cầu cần chứng minh khi hoàn thành:

- Một `serviceId` không có trong catalog hoặc không thuộc quyền người dùng **không thể được xác nhận** chỉ vì client tự gửi tham số.
- Giá hiển thị và giá được lưu đều lấy từ server. Nếu giá mới khác giá người dùng đã xem, phải **yêu cầu xem lại và đồng ý**.
- Nếu suất cuối đã hết, service từ chối tạo booking; flow đưa người dùng tới danh sách mới.
- Gửi lại cùng một yêu cầu nghiệp vụ không tạo hai booking. Hai giao dịch song song không vượt số suất còn.
- Flow execution key, HTTP session cookie, hidden field và event từ client **không phải bằng chứng phân quyền**.

## 3. Phân rã state machine

~~~mermaid
stateDiagram-v2
    [*] --> search
    search --> loadResults: find + validate
    loadResults --> choose: success
    choose --> search: back
    choose --> loadQuote: next + validate
    loadQuote --> review: success
    review --> choose: back
    review --> commitBooking: confirm + validate
    commitBooking --> completed: success
    commitBooking --> loadResults: unavailable
    commitBooking --> loadQuote: priceChanged
    search --> cancelled: cancel
    choose --> cancelled: cancel
    review --> cancelled: cancel
    completed --> [*]
    cancelled --> [*]
~~~

| State | Loại | Nhiệm vụ | Dữ liệu liên quan |
| --- | --- | --- | --- |
| `search` | `view-state` | Nhập từ khóa và ngày | `draft.keyword`, `draft.visitDate` |
| `loadResults` | `action-state` | Lấy các dịch vụ từ catalog | `flowScope.options` |
| `choose` | `view-state` | Chọn một kết quả | `draft.serviceId` |
| `loadQuote` | `action-state` | Đọc giá mới nhất ở bước xem lại | `flowScope.quote` |
| `review` | `view-state` | Xem giá, nhập người liên hệ | `draft.fullName`, `draft.email` |
| `commitBooking` | `action-state` | Ghi booking và trả outcome | `draft.confirmationCode` |
| `completed` | `end-state` | Kết thúc thành công | Mã xác nhận |
| `cancelled` | `end-state` | Kết thúc không đặt chỗ | Không có giao dịch |

Việc tách `loadResults` và `loadQuote` khỏi các màn hình giúp truy vấn rõ ràng, có thể mock khi test flow. Chúng là hành động **đọc**, có thể trả lại dữ liệu đã thay đổi. `commitBooking` là hành động **ghi**, nên các ràng buộc nghiệp vụ phải được kiểm tra lại tại đây.

## 4. Sơ đồ thành phần và cấu trúc thư mục

~~~mermaid
flowchart TD
    Browser["Trình duyệt: form + event"] --> Security["Spring Security filter chain"]
    Security --> MVC["DispatcherServlet / FlowHandlerAdapter"]
    MVC --> Flow["FlowExecutor / state machine"]
    Flow --> Actions["BookingFlowActions"]
    Flow --> Catalog["ServiceCatalog"]
    Actions --> Catalog
    Actions --> Reservation["ReservationService @Transactional"]
    Reservation --> DB["Database: slots + bookings + unique constraint"]
    Flow --> View["Thymeleaf ViewResolver"]
    View --> Browser
~~~

Cấu trúc đề xuất:

~~~text
src/main/java/com/example/booking/
  config/BookingWebFlowConfig.java
  flow/BookingDraft.java
  flow/BookingFlowActions.java
  catalog/ServiceCatalog.java
  catalog/ServiceOption.java
  catalog/PriceQuote.java
  reservation/ReservationCommand.java
  reservation/ConfirmationReceipt.java
  reservation/ReservationService.java
  reservation/ReservationRepository.java
src/main/resources/
  flows/booking/booking-flow.xml
  templates/booking/search.html
  templates/booking/choose.html
  templates/booking/review.html
  templates/booking/completed.html
  templates/booking/cancelled.html
  messages_vi.properties
~~~

Spring Web Flow quản lý hành trình; `BookingFlowActions` xử lý hành động gắn với form; `ServiceCatalog` cung cấp dữ liệu tra cứu; `ReservationService` là chốt kiểm tra quyền, giá, chỗ trống và transaction. Không đặt dữ liệu người dùng trong field mutable của singleton controller/service.

### 4.1. Dependency tham khảo

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.webflow:spring-webflow:3.0.2'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là phần `dependencies` minh họa của dự án Spring Boot 3.x, chưa bao gồm cấu hình plugin, Java toolchain, repository và database. Nếu chọn Spring 7/Boot 4 cần dùng nhánh SWF 4.x và Servlet container tương thích. Khi triển khai thật, kiểm tra lại bản vá SWF, Spring Security và dependency tree.

## 5. Model cho bản nháp trong flowScope

Người dùng chỉ được phép sửa những field thể hiện trong form tương ứng; những field còn lại do server kiểm soát:

| Thuộc tính | Kiểu | Nguồn | Có cho client bind? |
| --- | --- | --- | --- |
| `keyword` | `String` | Form `search` | Có, tại `search` |
| `visitDate` | `LocalDate` | Form `search` | Có, tại `search` |
| `serviceId` | `Long` | Form `choose` | Có, tại `choose` |
| `fullName`, `email` | `String` | Form `review` | Có, tại `review` |
| `requestId` | `String` | Server tạo khi flow bắt đầu | Không |
| `confirmationCode`, `notice` | `String` | Server cập nhật | Không |
| `quote` và `options` | DTO/collection từ catalog | Action của server | Không |

~~~java
package com.example.booking.flow;

import java.io.Serializable;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingDraft implements Serializable {
    private static final long serialVersionUID = 1L;
    private String keyword;
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate visitDate;
    private Long serviceId;
    private String fullName;
    private String email;
    private final String requestId = UUID.randomUUID().toString();
    private String confirmationCode;
    private String notice;

    public String getKeyword() { return keyword; }
    public void setKeyword(String value) { keyword = value; }
    public LocalDate getVisitDate() { return visitDate; }
    public void setVisitDate(LocalDate value) { visitDate = value; }
    public Long getServiceId() { return serviceId; }
    public void setServiceId(Long value) { serviceId = value; }
    public String getFullName() { return fullName; }
    public void setFullName(String value) { fullName = value; }
    public String getEmail() { return email; }
    public void setEmail(String value) { email = value; }
    public String getRequestId() { return requestId; }
    public String getConfirmationCode() { return confirmationCode; }
    public void setConfirmationCode(String value) { confirmationCode = value; }
    public String getNotice() { return notice; }
    public void setNotice(String value) { notice = value; }
}
~~~

`BookingDraft` được tạo cho **mỗi execution**, nên key idempotency sinh một lần ở constructor. Những object đưa vào flow execution repository cần phù hợp chính sách snapshot/serialization; không nhét `EntityManager`, kết nối database, HTTP request hoặc bean service vào bản nháp.

Một HTTP session có thể có nhiều flow executions. Để tránh lẫn dữ liệu hai tab, hãy dùng `flowScope` của từng execution và không ghi lựa chọn vào singleton:

~~~java
@Controller
class UnsafeController {
    private Long selectedServiceId; // Sai: shared mutable field
}
~~~

### 5.1. Hợp đồng catalog

~~~java
// Mỗi public top-level type đặt trong file .java riêng ở dự án thật.
public record ServiceOption(
    Long id, String title, int remaining, BigDecimal displayPrice) {}

public record PriceQuote(
    Long serviceId, LocalDate visitDate,
    BigDecimal amount, String currency) {}

public interface ServiceCatalog {
    List<ServiceOption> search(String keyword, LocalDate visitDate);
    Optional<ServiceOption> find(Long id, LocalDate visitDate);
    PriceQuote quote(Long id, LocalDate visitDate);
}
~~~

Các class record là DTO do server xây dựng. `remaining` và `displayPrice` chỉ mang tính **tham khảo tại thời điểm tìm kiếm**. Service xác nhận phải kiểm tra lại slot và giá đang có trong database; client không được gửi `displayPrice` hoặc `amount` rồi yêu cầu server ghi nguyên như thế.

## 6. Flow XML chính

Tệp `src/main/resources/flows/booking/booking-flow.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="draft" class="com.example.booking.flow.BookingDraft"/>

    <view-state id="search" view="booking/search" model="draft">
        <binder>
            <binding property="keyword" required="true"/>
            <binding property="visitDate" required="true"/>
        </binder>
        <transition on="find" to="loadResults">
            <evaluate expression="bookingActions.validateSearch(draft, messageContext)"/>
        </transition>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="loadResults">
        <evaluate expression="bookingCatalog.search(draft.keyword, draft.visitDate)"
                  result="flowScope.options"/>
        <transition on="success" to="choose"/>
    </action-state>

    <view-state id="choose" view="booking/choose" model="draft">
        <binder>
            <binding property="serviceId" required="true"/>
        </binder>
        <transition on="next" to="loadQuote">
            <evaluate expression="bookingActions.validateSelection(draft, messageContext)"/>
        </transition>
        <transition on="back" to="search" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="loadQuote">
        <evaluate expression="bookingCatalog.quote(draft.serviceId, draft.visitDate)"
                  result="flowScope.quote"/>
        <transition on="success" to="review"/>
    </action-state>

    <view-state id="review" view="booking/review" model="draft">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="confirm" to="commitBooking">
            <evaluate expression="bookingActions.validateContact(draft, messageContext)"/>
        </transition>
        <transition on="back" to="choose" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="commitBooking">
        <evaluate expression="bookingActions.commit(draft, quote)"/>
        <transition on="success" to="completed" history="invalidate"/>
        <transition on="unavailable" to="loadResults"/>
        <transition on="priceChanged" to="loadQuote"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Giải thích các chi tiết:

- `<var name="draft">` tạo bản nháp trong flow scope khi execution bắt đầu.
- `model="draft"` kết nối form với đối tượng Java. `<binder>` tạo **danh sách field được phép** cho riêng state đó; không có field `requestId`, `price` hoặc `confirmationCode`.
- `validateSearch`, `validateSelection` và `validateContact` trả `boolean`; `false` ở transition action ngăn chuyển bước và cho phép render lỗi từ `messageContext`.
- `loadResults`/`loadQuote` lưu dữ liệu do server lấy vào `flowScope`; không đọc giá được client gửi.
- `commitBooking` nhận outcome String: `success`, `unavailable` hoặc `priceChanged`. Các event này có transition rõ ràng.
- Các event `back`/`cancel` dùng `bind="false"` để không bắt người dùng hoàn thiện form khi rời bước.
- Hai `end-state` kết thúc execution. Mã biên lai muốn truy cập lâu dài phải lấy từ database bằng endpoint riêng có phân quyền.

**Nhánh lỗi cần bổ sung:** Khi `catalog.quote` không tìm được dịch vụ, hãy dùng action wrapper trả event `unavailable` và chuyển sang `loadResults`; không để tình huống hợp lệ của nghiệp vụ thành lỗi server không xử lý. Khi thay tiêu chí tìm kiếm, xóa `draft.serviceId` và `quote` cũ trước khi sử dụng lựa chọn mới; với nhánh hết chỗ cũng nên bỏ lựa chọn không còn hợp lệ.

## 7. Cấu hình Web Flow với Spring MVC và Thymeleaf

Flow XML cần được đăng ký để `DispatcherServlet` nhận request. Trình tự tích hợp:

1. `FlowDefinitionRegistry` tải định nghĩa `booking-flow.xml` dưới flow ID `booking`.
2. `FlowExecutor` quản lý việc bắt đầu, tạm dừng và tiếp tục execution.
3. `FlowHandlerMapping` ánh xạ request tới flow ID, ví dụ `GET /booking`.
4. `FlowHandlerAdapter` làm cầu nối từ Spring MVC tới `FlowExecutor`.
5. `MvcViewFactoryCreator` dùng `ThymeleafViewResolver` để render các logical view IDs `booking/search`, `booking/choose`, `booking/review`.

Ví dụ Java Config dựa trên Spring Web Flow 3:

~~~java
package com.example.booking.config;

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
public class BookingWebFlowConfig extends AbstractFlowConfiguration {
    private final ViewResolver thymeleafResolver;

    public BookingWebFlowConfig(
        @Qualifier("thymeleafViewResolver") ViewResolver thymeleafResolver) {
        this.thymeleafResolver = thymeleafResolver;
    }

    @Bean
    public MvcViewFactoryCreator bookingViewFactoryCreator() {
        MvcViewFactoryCreator factory = new MvcViewFactoryCreator();
        factory.setViewResolvers(List.of(thymeleafResolver));
        factory.setUseSpringBeanBinding(true);
        return factory;
    }

    @Bean
    public FlowBuilderServices flowBuilderServices() {
        return getFlowBuilderServicesBuilder()
            .setViewFactoryCreator(bookingViewFactoryCreator())
            .build();
    }

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder(flowBuilderServices())
            .addFlowLocation(
                "classpath:/flows/booking/booking-flow.xml", "booking")
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

Ví dụ giả định Spring Boot đã tạo bean `thymeleafViewResolver` thông qua starter. Nếu trong dự án có nhiều `ViewResolver`, dùng tên/`@Qualifier` đúng với bean thực tế và kiểm tra thứ tự resolver. Với Ajax fragments của Web Flow, Thymeleaf có cấu hình riêng cho `AjaxThymeleafViewResolver`/`FlowAjaxThymeleafView`; bài cơ bản dùng các form full-page.

**Không khai báo controller khác có mapping `/booking` trùng flow một cách vô ý.** Route chính nên do Web Flow handler tiếp nhận, trừ khi ứng dụng đã chủ động thiết kế một `FlowHandler` hoặc route điều phối. Tại startup, nếu bean flow không nạp được, kiểm tra version Spring/SWF, đường dẫn tài nguyên, view resolver và kiểu bean.

### 7.1. URL tiếp tục execution

Một chuỗi request mang tính minh họa:

~~~http
GET /booking HTTP/1.1

POST /booking?execution=e1s1 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId_find=Tìm&keyword=workshop&visitDate=2027-01-15
~~~

`execution=e1s1` là ví dụ về execution key; định dạng thực tế phụ thuộc repository và `FlowUrlHandler`. Trong template nên dùng **`flowExecutionUrl` do Web Flow cung cấp**, thay vì tự tạo hoặc lấy execution key làm thông tin chứng minh quyền.

Theo mô hình phổ biến, Web Flow redirect khi chuyển tới view-state mới theo mẫu **Post/Redirect/Get**. Refresh thường không gửi lại POST do người dùng vừa thực hiện, nhưng vẫn phải chống submit lặp ngay ở service vì có thể có nhiều request đồng thời hoặc retry từ client.

## 8. Kết nối các form Thymeleaf với event của flow

Các đoạn HTML dưới đây tập trung vào **form và event**. Chúng cần được bổ sung layout, hiển thị lỗi `MessageContext`, hỗ trợ accessibility, trạng thái loading, format giá và thành phần UI thích hợp trước khi triển khai.

### 8.1. `booking/search.html` — nhập điều kiện

~~~html
<h1>Tìm dịch vụ có chỗ</h1>
<form method="post" th:action="${flowExecutionUrl}" th:object="${draft}">
    <label for="keyword">Từ khóa</label>
    <input id="keyword" type="text" th:field="*{keyword}"
           maxlength="100" required>

    <label for="visitDate">Ngày tham gia</label>
    <input id="visitDate" type="date" th:field="*{visitDate}" required>

    <input th:if="${_csrf != null}" type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <button type="submit" name="_eventId_find">Tìm kiếm</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form>
~~~

`th:field="*{visitDate}"` bind giá trị vào `LocalDate` nhờ Spring FormattingConversionService và `@DateTimeFormat(iso = ISO.DATE)` trên model. Thuộc tính HTML `required` hoặc `maxlength` không thay được validation trên server.

Khi dùng Spring Security cùng Thymeleaf, `th:action` có thể đi qua `RequestDataValueProcessor` để tự chèn token CSRF. Nếu cơ chế view integration đã chèn token thì không thêm field ẩn trùng lặp; kiểm tra HTML được render thực tế. Một request thiếu/sai token phải bị từ chối theo security policy.

### 8.2. `booking/choose.html` — chọn kết quả tìm kiếm

~~~html
<h1>Chọn dịch vụ</h1>
<p th:if="${#lists.isEmpty(options)}">
    Chưa có dịch vụ phù hợp; hãy quay lại đổi từ khóa hoặc ngày.
</p>
<form method="post" th:action="${flowExecutionUrl}" th:object="${draft}">
    <div th:each="offer : ${options}">
        <label>
            <input type="radio" th:field="*{serviceId}"
                   th:value="${offer.id}">
            <span th:text="${offer.title}">Tên dịch vụ</span>
            <span th:text="${offer.displayPrice}">Giá</span>
            <span th:text="${offer.remaining}">0</span> suất còn
        </label>
    </div>
    <input th:if="${_csrf != null}" type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_back" formnovalidate>Quay lại</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form>
~~~

Radio chỉ gửi **ID**, còn tên/giá/suất do catalog trả về. Nếu client cố ý gửi một ID khác với danh sách, `validateSelection` phải phát hiện; service xác nhận vẫn kiểm tra lại quyền, tồn tại và số suất thực tế.

### 8.3. `booking/review.html` — xem báo giá, nhập liên hệ

~~~html
<h1>Xem lại đặt chỗ</h1>
<p>Dịch vụ ID: <span th:text="${quote.serviceId}"></span></p>
<p>Ngày: <span th:text="${quote.visitDate}"></span></p>
<p>Giá đang được báo:
    <strong th:text="${quote.amount}"></strong>
    <span th:text="${quote.currency}"></span>
</p>

<form method="post" th:action="${flowExecutionUrl}" th:object="${draft}">
    <label for="fullName">Họ và tên</label>
    <input id="fullName" type="text" th:field="*{fullName}"
           maxlength="120" required>

    <label for="email">Email</label>
    <input id="email" type="email" th:field="*{email}"
           maxlength="200" required>

    <input th:if="${_csrf != null}" type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit" name="_eventId_confirm">Xác nhận đặt chỗ</button>
    <button type="submit" name="_eventId_back" formnovalidate>Đổi dịch vụ</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form>
~~~

Người dùng cần biết **tên, ngày, giá, đơn vị tiền tệ và các điều kiện quan trọng** trước xác nhận. Bài chỉ hiển thị ID để giữ ví dụ ngắn; dự án thật nên hiển thị tên dịch vụ do server tra cứu. Giá được lấy từ `quote` trong scope của flow, không có input `price` để client tự sửa.

### 8.4. `booking/completed.html` và `booking/cancelled.html`

~~~html
<!-- Trong completed.html -->
<h1>Đặt chỗ thành công</h1>
<p>Mã đặt chỗ: <strong th:text="${draft.confirmationCode}">MÃ</strong></p>

<!-- Trong cancelled.html, một template riêng -->
<h1>Đã hủy thao tác</h1>
<p>Không có đặt chỗ mới được tạo.</p>
~~~

Đây là hai **fragment mô tả hai template riêng**, không được dán thành một trang duy nhất trong dự án. Sau khi flow kết thúc, execution có thể không còn. Biên lai muốn mở lại trong tương lai nên là resource riêng như `GET /reservations/{id}`, lấy dữ liệu từ database và kiểm tra quyền của người dùng.

## 9. BookingFlowActions: validate trước khi chuyển bước

`BookingFlowActions` là một Spring service thường được dùng chung giữa các request; mọi phương thức nhận `draft` từ flow và không lưu trạng thái phiên trong field của chính bean.

~~~java
package com.example.booking.flow;

import java.time.Clock;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import com.example.booking.catalog.ServiceCatalog;
import com.example.booking.catalog.ServiceOption;
import com.example.booking.catalog.PriceQuote;
import com.example.booking.reservation.ReservationCommand;
import com.example.booking.reservation.ReservationService;
import com.example.booking.reservation.ConfirmationReceipt;
import com.example.booking.reservation.NoAvailabilityException;
import com.example.booking.reservation.PriceChangedException;

@Service("bookingActions")
public class BookingFlowActions {
    private final ServiceCatalog catalog;
    private final ReservationService reservationService;
    private final Clock clock;

    public BookingFlowActions(ServiceCatalog catalog,
                              ReservationService reservationService,
                              Clock clock) {
        this.catalog = catalog;
        this.reservationService = reservationService;
        this.clock = clock;
    }

    public boolean validateSearch(BookingDraft draft, MessageContext messages) {
        boolean valid = true;
        if (!StringUtils.hasText(draft.getKeyword())) {
            messages.addMessage(new MessageBuilder().error()
                .source("keyword").defaultText("Nhập từ khóa tìm kiếm").build());
            valid = false;
        }
        LocalDate date = draft.getVisitDate();
        if (date == null || date.isBefore(LocalDate.now(clock))) {
            messages.addMessage(new MessageBuilder().error()
                .source("visitDate").defaultText("Chọn ngày hợp lệ").build());
            valid = false;
        }
        return valid;
    }

    public boolean validateSelection(BookingDraft draft, MessageContext messages) {
        Long id = draft.getServiceId();
        List<ServiceOption> options =
            catalog.search(draft.getKeyword(), draft.getVisitDate());
        boolean valid = id != null && options.stream()
            .anyMatch(option -> Objects.equals(option.id(), id));
        if (!valid) {
            messages.addMessage(new MessageBuilder().error()
                .source("serviceId")
                .defaultText("Dịch vụ không còn phù hợp").build());
        }
        return valid;
    }

    public boolean validateContact(BookingDraft draft, MessageContext messages) {
        boolean nameOk = StringUtils.hasText(draft.getFullName());
        boolean emailOk = StringUtils.hasText(draft.getEmail())
            && draft.getEmail().contains("@");
        if (!nameOk) {
            messages.addMessage(new MessageBuilder().error()
                .source("fullName").defaultText("Nhập họ tên").build());
        }
        if (!emailOk) {
            messages.addMessage(new MessageBuilder().error()
                .source("email").defaultText("Email chưa hợp lệ").build());
        }
        return nameOk && emailOk;
    }

    public String commit(BookingDraft draft, PriceQuote quote) {
        try {
            ReservationCommand command = new ReservationCommand(
                draft.getRequestId(), draft.getServiceId(),
                draft.getVisitDate(), draft.getFullName(),
                draft.getEmail(), quote.amount());
            ConfirmationReceipt receipt = reservationService.confirm(command);
            draft.setConfirmationCode(receipt.code());
            return "success";
        } catch (NoAvailabilityException expected) {
            draft.setNotice("Dịch vụ vừa hết chỗ, hãy chọn lại");
            draft.setServiceId(null);
            return "unavailable";
        } catch (PriceChangedException expected) {
            draft.setNotice("Giá đã thay đổi, hãy xem lại");
            return "priceChanged";
        }
    }
}
~~~

Để sử dụng đoạn này, cần có `ServiceCatalog` implementation, `ReservationService`, `ReservationCommand`, `ConfirmationReceipt` và hai kiểu exception nghiệp vụ tương ứng. Ví dụ kiểm tra email bằng `contains("@")` là **rút gọn để minh họa**, chưa đạt chuẩn validation email production; nên dùng `@Email`/`@NotBlank` và kiểm soát độ dài, mã hóa, cách xử lý thông tin cá nhân.

Trong bài, `Clock` được inject để test ngày tương lai bằng một đồng hồ cố định. Đăng ký ví dụ:

~~~java
@Bean
public Clock clock() {
    return Clock.systemUTC();
}
~~~

Nếu ngày dịch vụ theo địa phương (ví dụ chỉ mở theo múi giờ Việt Nam), dùng `Clock` và `ZoneId` nhất quán với quy tắc nghiệp vụ. Không dùng `LocalDate.now()` ở nhiều lớp với múi giờ khác nhau.

### 9.1. Cơ chế MessageContext và return boolean

`messageContext` là API ghi thông báo theo field/severity, có thể đi qua redirect của flow. Khi `validateSearch` trả `false` trong transition, Web Flow có thể giữ lại `view-state` và render thông báo lỗi. Nếu parse `visitDate` đã lỗi ngay tại binder, transition không chạy; cần hiển thị **cả lỗi binding tự sinh và lỗi validation**.

Đừng biến mọi lỗi thành một thông báo chung không có field: lỗi `visitDate` nên hiện gần ngày, lỗi `serviceId` gần lựa chọn và lỗi email gần input email. Với Thymeleaf, cách truy cập các thông báo phụ thuộc `MvcViewFactoryCreator` và cấu hình binding, vì vậy phải kiểm tra HTML render thực tế.

### 9.2. Điều cần bổ sung ở ứng dụng thật

- Khi người dùng đổi tiêu chí `keyword`/`visitDate`, xóa `serviceId`, báo giá và thông báo của lựa chọn cũ. Có thể làm việc này trong một action của transition `find`.
- Khi `quote(...)` không còn hợp lệ vì dịch vụ biến mất, biến lỗi nghiệp vụ thành một outcome điều hướng an toàn, không để exception không kiểm soát trên màn hình.
- Nếu catalog bị giới hạn bởi vai trò/vùng địa lý, kiểm tra quyền trong truy vấn catalog và tại service xác nhận.
- Không bắt `Exception` hoặc `RuntimeException` chung rồi trả `success`; các lỗi database, quyền truy cập và lỗi lập trình phải giữ đúng semantics.

## 10. Service xác nhận với transaction và idempotency

Hệ thống cần hợp đồng độc lập với Web Flow để đảm bảo một booking chỉ được ghi khi mọi điều kiện cuối cùng đều thỏa. Định nghĩa các kiểu:

~~~java
// Mỗi public record/interface bên dưới đặt ở file .java riêng.
public record ReservationCommand(
    String requestId,
    Long serviceId,
    LocalDate visitDate,
    String fullName,
    String email,
    BigDecimal acceptedPrice) {}

public record ConfirmationReceipt(String code) {}

public interface ReservationService {
    ConfirmationReceipt confirm(ReservationCommand command);
}
~~~

`acceptedPrice` được truyền từ `flowScope.quote` do catalog **phía server** tạo. Nó không phải số tiền tin cậy tuyệt đối: `ReservationService` vẫn phải đọc giá hiện tại tại thời điểm commit và so sánh. Ngoài ra, service phải kiểm tra báo giá gắn với **đúng dịch vụ và đúng ngày** của lệnh, tránh dùng nhầm quote cũ.

### 10.1. Lược đồ database gợi ý

| Bảng | Trường quan trọng | Ràng buộc cần có |
| --- | --- | --- |
| `service` | `id`, `title`, `status` | ID duy nhất, trạng thái hợp lệ |
| `service_slot` | `service_id`, `visit_date`, `capacity`, `reserved`, `current_price`, `version` | Một slot duy nhất cho dịch vụ/ngày; `reserved <= capacity` |
| `reservation` | `id`, `user_id`, `request_id`, `service_id`, `visit_date`, `price`, `status` | `UNIQUE(user_id, request_id)` |

Giả sử hai người cùng chọn suất cuối, một truy vấn `search()` không thể đảm bảo độc quyền suất đó trong suốt thời gian họ điền form. Chỉ **transaction lúc xác nhận** mới quyết định ai đặt thành công.

### 10.2. Thuật toán nghiệp vụ

~~~text
confirm(command) trong transaction:
  userId = danh tính đã xác thực từ Spring Security
  kiểm tra người này có được dùng dịch vụ và ngày đã chọn
  nếu (userId, requestId) đã có reservation:
      trả cùng confirmationCode, không giảm thêm suất
  đọc service_slot và khóa/kiểm tra version phù hợp
  nếu slot đã hết chỗ: báo NoAvailability
  đọc giá hiện tại từ database
  nếu giá không khớp acceptedPrice: báo PriceChanged
  kiểm tra lại thông tin liên hệ, trạng thái dịch vụ và ngày
  tăng reserved đúng 1, tạo reservation trong cùng transaction
  commit thành công
  trả confirmationCode từ database
~~~

Một ví dụ Java **mang tính khung**, còn các repository, principal provider, exception và hàm tạo entity do bạn triển khai:

~~~java
@Transactional
public ConfirmationReceipt confirm(ReservationCommand command) {
    String userId = currentPrincipal.requireUserId();

    var existing = reservationRepository.findByUserIdAndRequestId(
        userId, command.requestId());
    if (existing.isPresent()) {
        return new ConfirmationReceipt(existing.get().getConfirmationCode());
    }

    var slot = slotRepository.findForUpdate(
        command.serviceId(), command.visitDate())
        .orElseThrow(NoAvailabilityException::new);

    authorization.checkBookingAllowed(userId, slot);
    if (slot.getReserved() >= slot.getCapacity()) {
        throw new NoAvailabilityException();
    }
    if (slot.getCurrentPrice().compareTo(command.acceptedPrice()) != 0) {
        throw new PriceChangedException();
    }

    validateContact(command.fullName(), command.email());
    slot.setReserved(slot.getReserved() + 1);
    Reservation saved = reservationRepository.save(
        createReservation(userId, slot, command));
    return new ConfirmationReceipt(saved.getConfirmationCode());
}
~~~

**Chú ý về cạnh tranh:** kiểm tra `findByUserIdAndRequestId` rồi `save` **không đủ** để chống hai transaction cùng không thấy dữ liệu cũ. Database phải có unique constraint tương ứng; khi một transaction thất bại vì trùng key, cần rollback transaction lỗi, đọc lại booking đã commit và trả receipt theo chính sách idempotency. Với slot, `findForUpdate` gợi ý khóa bi quan; nếu chọn optimistic locking bằng `@Version`, phải có xử lý xung đột riêng.

Không bao toàn bộ hành trình web nhiều bước trong **một transaction database kéo dài qua nhiều HTTP request**. Mỗi lần tra cứu là thao tác ngắn, còn transaction ghi được mở tại bước commit. Nếu cần giữ chỗ trước khi thanh toán, phải thiết kế trạng thái hold có thời hạn, cơ chế giải phóng và xử lý timeout riêng.

### 10.3. Đặt chỗ thành công nhưng response bị mất

Giả sử database đã commit, nhưng kết nối tới trình duyệt đứt trước khi gửi trang `completed`. Người dùng gửi lại `confirm`. Service phải nhận cùng `requestId`, tìm ra booking đã tạo và **trả lại receipt cũ**. Nếu hệ thống tạo một request ID mới mỗi lần retry, sẽ dễ có booking trùng.

Trường hợp booking đã commit nhưng flow execution mất hẳn, người dùng có thể cần vào trang **Tra cứu đặt chỗ** theo tài khoản và mã booking. Đây là lý do trạng thái nghiệp vụ bền vững thuộc database, không phụ thuộc tuổi thọ của `flowScope`.

## 11. Xử lý nhánh hết chỗ và giá thay đổi

Một bài thực hành nhiều bước chỉ thành công khi các nhánh lỗi là một phần thiết kế.

### 11.1. Hết chỗ khi xác nhận

Ví dụ:

1. `search` trả workshop A có **1 suất**.
2. Người dùng chọn A và chuyển sang `review`.
3. Người khác đặt thành công suất cuối.
4. Người dùng đầu tiên gửi event `confirm`.
5. `ReservationService.confirm` thấy hết chỗ và ném `NoAvailabilityException`.
6. `BookingFlowActions.commit` trả `unavailable`, Web Flow chạy `loadResults` rồi về `choose` với danh sách cập nhật.

Ở bước 6, nếu A không còn tồn tại trong options, nên xóa `draft.serviceId` và hiển thị thông báo “Dịch vụ vừa hết chỗ, hãy chọn lại”. Không tự động chọn dịch vụ khác thay người dùng.

### 11.2. Giá thay đổi sau khi người dùng xem báo giá

Giả sử người dùng xem dịch vụ B giá **300.000 VND**, nhưng giá ở database đổi thành **350.000 VND** trước khi gửi `confirm`.

| Thời điểm | Số tiền | Cách xử lý |
| --- | --- | --- |
| `loadQuote` | 300.000 VND | Hiển thị báo giá đã biết |
| `commitBooking` | 350.000 VND | Từ chối commit với `priceChanged` |
| Chuyển lại `loadQuote` | 350.000 VND | Lấy báo giá mới, hiển thị lại `review` |
| Lần `confirm` tiếp theo | 350.000 VND nếu không đổi nữa | Service xác minh lại rồi mới commit |

**Không tự thu tiền theo giá mới** khi người dùng mới đồng ý giá cũ. Nếu hệ thống áp dụng chính sách giữ giá trong một khoảng thời gian, cần mô hình quote có mã, expiry, version và chính sách xác thực ở server; một `BigDecimal` trong flowScope chưa tự tạo cam kết giá bất biến.

### 11.3. Lỗi không xác định

Lỗi mất kết nối database, timeout khi gọi cổng thanh toán hoặc exception lập trình không thuộc nhánh `unavailable`/`priceChanged`. Không bắt mọi exception rồi biến thành event `success` hoặc “hết chỗ”. Cần phân loại lỗi, bảo đảm rollback và trả thông báo phục hồi an toàn. Nếu kết quả commit **chưa rõ**, thao tác kiểm tra lại theo idempotency key phải diễn ra trước khi retry ghi.

## 12. Phạm vi dữ liệu và vòng đời execution

| Dữ liệu | Scope khuyến nghị | Tại sao |
| --- | --- | --- |
| `draft` | `flowScope` | Một bản nháp xuyên qua các màn hình của cùng execution |
| `options` | `flowScope` ở ví dụ này; hoặc `viewScope` nếu tải tại `on-render` | Danh sách tham khảo, có thể tải mới |
| `quote` | `flowScope` | Cần ở `review` và tại action xác nhận; vẫn phải đối chiếu server |
| Lỗi field | `messageContext` | Thông báo binding/validation |
| Thông báo chuyển bước | `flashScope` hoặc `messageContext` | Không cần giữ lâu |
| `confirmationCode` | Bản nháp để render ngay; database để lưu chính thức | Biên lai lâu dài không phụ thuộc flow |
| `userId` và quyền | Spring Security/service | Không lấy từ hidden field hoặc flow event |
| `ServiceCatalog` và `ReservationService` | Spring bean stateless | Được inject dùng chung, không chứa lựa chọn cá nhân |

### 12.1. Khi dùng nút Back hoặc mở nhiều tab

Spring Web Flow có thể lưu snapshot để hỗ trợ quay lại trạng thái trước. Nhưng một snapshot cũ có thể chứa giá và lựa chọn lỗi thời. Khi người dùng quay từ `review` về `choose` rồi chọn lại, phải tải báo giá mới; khi xác nhận, service kiểm tra điều kiện tại transaction. Browser Back **không được trở thành đường để tái sử dụng quyền đã hết hạn**.

Một HTTP session có thể chứa nhiều execution. Nếu hai tab mở hai flow mới, mỗi tab cần `draft` riêng. Hãy thử cả trường hợp hai tab **cố ý dùng chung cùng execution URL**: khi đó cùng một execution có thể có các thay đổi cạnh tranh và phải xử lý bằng snapshot/flow repository cùng kiểm tra ở service.

### 12.2. Khi session hoặc execution hết hạn

Flow có thể hết hạn do timeout phiên, repository giới hạn số execution/snapshot hoặc ứng dụng restart. Không giả định URL `execution` cũ luôn tồn tại. Khi không còn execution:

1. Không cố tạo booking từ giá trị chưa được xác minh còn nằm trong trình duyệt.
2. Thông báo flow đã hết hạn và cung cấp đường bắt đầu lại.
3. Nếu có booking đã commit, cho phép tra cứu từ database sau xác thực.
4. Không hiển thị dữ liệu của người dùng trước nếu phiên đã chuyển tài khoản.

Các tham số `max-executions`, `max-execution-snapshots` phải được chỉnh dựa trên tải, số tab và bộ nhớ; tăng vô hạn có thể làm session phình to. Với hệ nhiều instance, cần kiểm tra cách lưu HTTP session/flow execution và khả năng phục hồi khi đổi node.

## 13. Spring Security, CSRF và ranh giới dữ liệu

Đây là ứng dụng có dữ liệu người dùng và thao tác ghi, nên security cần đi qua từng lớp:

- **HTTP/URL:** `SecurityFilterChain` kiểm soát các URL `/booking` và URL tiếp tục flow. Nếu người dùng cần đăng nhập trước commit, chính sách đó phải được thực thi ở server.
- **CSRF:** các form POST với `_eventId_find`, `_eventId_next`, `_eventId_confirm`, `_eventId_back` và `_eventId_cancel` phải gửi token hợp lệ khi dùng cơ chế session cookie có CSRF protection.
- **Authorization:** `ReservationService` đọc principal từ Spring Security và kiểm tra người đó được phép đặt trên dịch vụ/ngày đang chọn; không tin `userId` do client gửi.
- **Binding whitelist:** `search` chỉ nhận `keyword`/`visitDate`, `choose` chỉ nhận `serviceId`, `review` chỉ nhận `fullName`/`email`.
- **Dữ liệu hiển thị:** dùng `th:text` để escape tên dịch vụ/tên khách; tránh chèn HTML/JS không đáng tin cậy vào trang xem lại.
- **Giao dịch:** database mới là nơi kiểm tra giá, sức chứa, trạng thái, unique key và commit.
- **Logs:** tránh ghi session ID, execution key, CSRF token, email nguyên văn hoặc dữ liệu cá nhân nhạy cảm.

Những điều kiện trên không thể được thay thế bằng việc ẩn nút trên giao diện. Người dùng có thể tự gửi event `confirm` hoặc một `serviceId` khác trong request. Web Flow chỉ thực hiện transition hợp lệ của state hiện tại; **có transition hợp lệ không đồng nghĩa có quyền giao dịch**.

## 14. Kiểm thử đúng các nhánh của state machine

Một bài thực hành tích hợp cần kiểm chứng cả logic điều hướng và các bất biến nghiệp vụ. Dùng unit test cho action/validator, flow test với `org.springframework.webflow.test.execution`, HTTP integration test cho MVC/security và database test cho cạnh tranh thực tế.

| ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| T01 | GET `/booking` | Vào `search`, tạo execution mới |
| T02 | `keyword` và `visitDate` hợp lệ, event `find` | Vào `choose`, trả options đúng |
| T03 | Ngày không hợp lệ | Ở `search`, có lỗi theo field |
| T04 | Không có kết quả | Danh sách trống, người dùng có đường quay lại |
| T05 | Gửi ID dịch vụ không thuộc kết quả | Ở `choose`, không tới báo giá |
| T06 | ID dịch vụ hợp lệ | Vào `review`, giá do catalog tính |
| T07 | Email trống hoặc sai định dạng | Ở `review`, không gọi commit |
| T08 | Đặt chỗ hợp lệ, còn suất và giá đúng | Một booking, vào `completed` |
| T09 | Hết suất trước khi confirm | Trả `unavailable`, tải lại options |
| T10 | Giá đổi trước khi confirm | Trả `priceChanged`, xem quote mới |
| T11 | Event `back` | Quay lại đúng state, không tạo booking |
| T12 | Event `cancel` ở ba màn hình | Kết thúc `cancelled`, không có booking |
| T13 | Hai request confirm cùng idempotency key | Một booking, kết quả retry nhất quán |
| T14 | Hai request cùng tranh suất cuối | Không vượt capacity, một request có thể bị từ chối |
| T15 | Client gửi `requestId` hoặc `price` tự sửa | Không bind field server-only, không ảnh hưởng giá thật |
| T16 | Gửi POST thiếu CSRF token | Security filter chặn request |
| T17 | Logout/hết session trước confirm | Không giao dịch với quyền đã hết hạn |
| T18 | Mở hai flow trong hai tab | Không trộn draft và quote |
| T19 | Service gặp lỗi không dự kiến | Không trả thành công giả, transaction rollback phù hợp |
| T20 | Mở biên lai sau khi flow kết thúc | Đọc từ DB qua endpoint có kiểm tra quyền |

### 14.1. Unit test xử lý kết quả hết chỗ

Một ví dụ JUnit Jupiter/Mockito, với `actions` và `reservationService` là các đối tượng được thiết lập trong test:

~~~java
@Test
void commitReturnsUnavailableWhenCapacityIsGone() {
    BookingDraft draft = new BookingDraft();
    draft.setServiceId(21L);
    draft.setVisitDate(LocalDate.of(2027, 1, 15));
    draft.setFullName("An");
    draft.setEmail("an@example.test");

    when(reservationService.confirm(any(ReservationCommand.class)))
        .thenThrow(new NoAvailabilityException());

    String event = actions.commit(
        draft,
        new PriceQuote(21L, draft.getVisitDate(),
                       new BigDecimal("300000"), "VND"));

    assertEquals("unavailable", event);
    assertNull(draft.getConfirmationCode());
    assertNull(draft.getServiceId());
}
~~~

Đây là trích đoạn method test; thêm import, mock và cấu hình fixture tương ứng. Với `Clock.fixed(...)`, test `validateSearch` không phụ thuộc ngày chạy test. Test `validateSelection` nên mock catalog trả hai options, rồi thử ID hợp lệ và ID giả. Những test này xác nhận logic action, **chưa chứng minh concurrency ở database**.

### 14.2. Flow test

Ở test flow, tạo bean giả `bookingActions` và `bookingCatalog`, rồi phát event lần lượt:

~~~text
startFlow() -> search
find      -> loadResults -> choose
next      -> loadQuote   -> review
back      -> choose
next      -> review
confirm   -> commitBooking -> completed
~~~

Chạy thêm các nhánh `cancel`, `unavailable` và `priceChanged`; xác minh một event không thuộc state hiện tại không thể đi thẳng tới `completed`. Có thể sử dụng các lớp hỗ trợ kiểm thử flow của đúng phiên bản Web Flow. Khi các action bị mock, không nên dùng kết quả test flow để tuyên bố service đã an toàn.

### 14.3. HTTP và database integration

Thực hiện request qua `MockMvc` hoặc test HTTP thật để xác minh `FlowHandlerMapping`, `FlowHandlerAdapter`, view resolver, `_eventId_*`, CSRF và cookie. Với database, chạy hai transaction song song cùng tranh suất cuối và kiểm tra số reservation cùng counter cuối cùng. Nếu production dùng PostgreSQL, nên có integration test trên PostgreSQL hoặc hệ có semantics khóa/transaction tương đương.

## 15. Chạy thử thủ công từ đầu đến cuối

1. Chuẩn bị ít nhất hai dịch vụ còn suất cho một ngày tương lai và một dịch vụ hết suất. Có bảng booking trống.
2. Khởi động ứng dụng, kiểm tra `FlowRegistry` nạp flow XML và route `/booking` hoạt động.
3. Mở `/booking`, thử thiếu ngày rồi nhập đúng từ khóa/ngày, bấm **Tìm kiếm**.
4. Ở `choose`, chọn dịch vụ A, bấm **Tiếp tục** và xác nhận báo giá hiện đúng.
5. Quay lại, chọn dịch vụ B, rồi tới `review`; kiểm tra draft và quote đã đổi.
6. Nhập email không hợp lệ, kiểm tra vẫn ở `review` và chưa có booking.
7. Nhập thông tin hợp lệ, bấm **Xác nhận**; kiểm tra `completed`, mã booking và database có đúng một bản ghi.
8. Gửi lại cùng lệnh nghiệp vụ, xác minh không có booking thứ hai.
9. Tạo tình huống dịch vụ hết suất ở transaction khác trước confirm; kiểm tra flow quay lại chọn.
10. Tạo tình huống giá thay đổi trước confirm; kiểm tra người dùng xem giá mới và phải bấm confirm lần nữa.
11. Thử `cancel`, Back, nhiều tab, session timeout, logout, sửa `serviceId`/`requestId` và thiếu CSRF token.

Khi quan sát log, chỉ ghi correlation ID, flow ID, state, event, kết quả nghiệp vụ và thời gian xử lý ở mức cần thiết; không log secret hoặc toàn bộ dữ liệu cá nhân.

## 16. Vấn đề thường gặp và hướng chẩn đoán

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| GET `/booking` trả 404 | Flow ID, vị trí XML, `FlowHandlerMapping`, thứ tự handler |
| POST `find` vẫn ở form | Lỗi binding/validation, event chưa được giải mã, action trả `false` |
| Không tìm được template | `MvcViewFactoryCreator`, `ThymeleafViewResolver`, logical view ID |
| Form ngày bị lỗi parse | `@DateTimeFormat`, ConversionService, chuỗi HTTP gửi lên |
| Chọn dịch vụ A nhưng hiện quote B | `serviceId`/`quote` stale, dữ liệu mutable dùng chung, test nhiều tab |
| Màn hình có giá mới nhưng booking lưu giá cũ | Service không kiểm tra giá trong transaction |
| Đặt quá sức chứa | Thiếu locking/version/constraint ở database |
| Hai booking từ một lần nhấn | Thiếu key idempotency, UNIQUE hoặc xử lý retry |
| Quay lại bị mất form | Flow scope, snapshot policy hoặc mã làm sạch draft sai |
| URL execution cũ tạo lỗi | Flow đã kết thúc, timeout hoặc snapshot bị loại |
| CSRF chặn form | Token không được render hoặc không được gửi ở POST |
| Exception của service bị coi là success | Action bắt lỗi quá rộng hoặc mapping outcome sai |

Lỗi route thường nằm ở MVC config; lỗi chuyển state ở flow XML; lỗi kiểu dữ liệu ở binder/converter; lỗi quyền, giá hoặc booking trùng nằm ở service/database. Đặt log/trace ở lớp phù hợp để không làm rối logic.

## 17. Bài tập mở rộng

### Bài A — thêm chọn khung giờ

Thêm state `chooseTime` sau `choose`, field `timeSlotId` và binder whitelist riêng. Thay service slot theo ngày bằng slot theo ngày + giờ. Test Back và tình huống khung giờ bị chiếm trước commit.

### Bài B — chuyển phần thông tin liên hệ thành subflow

Tạo `subflow-state` gọi `contact-details`, truyền dữ liệu đầu vào cần thiết và nhận output khi subflow hoàn thành. Thử outcome `completed` và `cancelled`, kiểm tra `conversationScope`, quyền truy cập và việc không giữ dữ liệu dư qua các flow.

### Bài C — lọc danh sách bằng Ajax

Cho người dùng lọc theo giá, sắp xếp và phân trang tại `choose`. Tìm hiểu `on-render` và `<render fragments="..."/>`, dùng Thymeleaf ViewResolver có hỗ trợ Ajax/fragment tương ứng. Không làm mất service ID đã chọn khi thay trang.

### Bài D — bổ sung thanh toán

Sau `review`, thêm bước thanh toán với trạng thái pending, paid, failed và expired. Không coi URL quay lại từ cổng thanh toán là bằng chứng đã thanh toán; phải xác minh callback và idempotency ở server, đồng thời có cơ chế giải phóng suất nếu giữ chỗ hết hạn.

### Bài E — vận hành và theo dõi

Đề xuất chỉ số: số flow bắt đầu, số tới `choose`/`review`, tỷ lệ xác nhận, tỷ lệ `unavailable`/`priceChanged`, thời gian truy vấn catalog, thời gian commit và số execution hết hạn. Ưu tiên metric tổng hợp, tránh gắn thông tin nhận dạng cá nhân vào nhãn metric.

## 18. Checklist hoàn thành bài thực hành

- [ ] Tài liệu có sơ đồ state/event/transition và xử lý các nhánh quay lại, hủy.
- [ ] `search` bind từ khóa và ngày đúng kiểu, có validation phía server.
- [ ] `loadResults` truy vấn catalog và xử lý danh sách rỗng.
- [ ] `choose` chỉ bind `serviceId`, kiểm tra ID được phép.
- [ ] `loadQuote` lấy báo giá từ server trước khi review.
- [ ] `review` hiển thị ngày, dịch vụ, giá, thông tin liên hệ và lỗi field.
- [ ] `commitBooking` có outcome `success`/`unavailable`/`priceChanged`.
- [ ] `ReservationService` kiểm tra quyền, giá, số suất, trạng thái và transaction.
- [ ] Unique constraint + idempotency bảo vệ trước các request lặp.
- [ ] Scope mỗi flow không trộn giữa hai execution; session timeout được xử lý.
- [ ] Security/CSRF/output encoding được kiểm tra ở HTTP và view.
- [ ] Có unit tests action, flow tests state và integration tests thực với database.
- [ ] Hủy hoặc lỗi không tạo booking; commit thành công chỉ tạo một booking.
- [ ] Có trang biên lai độc lập database và kiểm tra quyền khi xem lại.

## 19. Câu hỏi tự kiểm tra

**1. Vì sao cần kiểm tra lại chỗ trống ở lúc commit?** Vì danh sách tìm kiếm và báo giá là ảnh chụp, có thể đã lỗi thời trước khi người dùng hoàn tất form.

**2. Vì sao chỉ bind `serviceId` tại `choose`?** Vì tên dịch vụ, giá và các trường đặc quyền phải do server quyết định; binder whitelist giúp ngăn client thay đổi chúng.

**3. Vì sao không giữ một transaction database suốt các màn hình?** Vì người dùng có thể chờ lâu, rời trang hoặc hết phiên; transaction dài gây khóa và rủi ro tài nguyên. Chỉ cần transaction ngắn ở thao tác nghiệp vụ quyết định.

**4. Nếu giá thay đổi sau review, có nên tự xác nhận với giá mới không?** Không. Cần hiển thị giá mới và yêu cầu đồng ý lại theo chính sách.

**5. Flow execution key có bảo đảm quyền trên booking không?** Không. Key phục vụ xác định execution/snapshot; service phải kiểm tra danh tính và quyền theo đối tượng.

**6. Web Flow có tự ngăn hai request confirm đồng thời không?** Không đủ để bảo vệ invariant ở database; phải có idempotency key, unique constraint, locking/version và transaction đúng.

**7. Vì sao test flow chưa đủ?** Test flow chứng minh điều hướng; test service/database chứng minh booking không trùng, không vượt suất, đúng giá và quyền ngay cả khi request cạnh tranh.

## 20. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 Reference Guide](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — state/event/transition, flow variables, scopes, binding, validation, action-state, cấu hình engine và MVC.
2. [Spring Web Flow API](https://docs.spring.io/spring-webflow/docs/3.0.2/api/) — `FlowDefinitionRegistry`, `FlowExecutor`, `FlowHandlerMapping`, `FlowHandlerAdapter`, testing support.
3. [Thymeleaf + Spring — Web Flow Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html#spring-webflow-integration) — view factory, Thymeleaf resolver và fragment rendering.
4. [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) và [Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html).
5. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — bảo vệ form POST.
6. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — quyền theo đối tượng và deny-by-default.

**Kết quả cần nhớ:** Spring Web Flow giúp mô tả hành trình **tìm kiếm → chọn dịch vụ → xem lại → xác nhận** qua các state, event và transition, đồng thời giữ bản nháp đúng phạm vi. **Sự chính xác của đặt chỗ** vẫn do service và database bảo đảm: kiểm tra lại giá, quyền, chỗ trống, transaction và idempotency ở thời điểm xác nhận. Một bài thực hành hoàn chỉnh phải chứng minh được cả đường thành công và các nhánh phục hồi khi dữ liệu thay đổi trong lúc người dùng thao tác.
