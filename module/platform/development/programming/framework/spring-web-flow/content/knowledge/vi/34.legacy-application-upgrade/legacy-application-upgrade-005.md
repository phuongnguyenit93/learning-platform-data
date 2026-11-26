# Rà lại cơ chế ExpressionParser và biểu thức cũ

## 1. Vì sao cần rà soát ExpressionParser khi nâng cấp?

Trong **Spring Web Flow (SWF)**, biểu thức (Expression Language — EL) xuất hiện ở nhiều vị trí của flow definition: gọi service, đọc input, gán biến vào scope, kiểm tra điều kiện rẽ nhánh, chọn view, ánh xạ dữ liệu và xử lý kết quả của action. Một biểu thức ngắn như `bookingService.createBooking(hotelId)` vẫn phụ thuộc vào **ngôn ngữ biểu thức**, **parser đang được cấu hình**, **ngữ cảnh đánh giá** và **các biến mà Web Flow cung cấp**.

Các ứng dụng cũ có thể đã được viết bằng OGNL hoặc Unified EL. Khi nâng cấp từ Web Flow 1.x lên 2.x, hoặc nâng cấp một ứng dụng Web Flow 2.x đã tồn tại lâu năm, những biểu thức này có thể tiếp tục chạy nhờ parser cũ trên classpath. Khi thay dependency, loại bỏ thư viện hoặc thay parser mặc định, flow có thể gặp lỗi cú pháp, lỗi truy cập thuộc tính, lỗi chuyển kiểu hoặc lỗi runtime vì cách hiểu biểu thức đã thay đổi.

Bài này tập trung vào việc **xác định parser thật sự đang chạy, hiểu lịch sử thay đổi OGNL/Unified EL/Spring EL, chuyển cú pháp cũ có kiểm soát và kiểm thử lại các flow**. Mục tiêu là bảo đảm state, event, transition, form binding và service invocation vẫn cho kết quả như trước sau khi nâng cấp.

## 2. ExpressionParser là gì?

`org.springframework.binding.expression.ExpressionParser` là abstraction của Spring Binding dùng để phân tích chuỗi biểu thức thành một đối tượng `Expression` có thể đánh giá trong một context. Web Flow sử dụng abstraction này thay vì gắn toàn bộ flow engine vào một cú pháp EL duy nhất.

Có thể phân biệt ba tầng:

| Tầng | Thành phần | Trách nhiệm |
|---|---|---|
| Chuỗi biểu thức | Ví dụ `bookingService.find(hotelId)` | Nội dung được khai báo trong XML |
| Parser | `ExpressionParser` | Phân tích chuỗi theo ngôn ngữ và cú pháp đã chọn |
| Expression + evaluation context | `Expression` và `RequestContext` liên quan | Đánh giá biểu thức, truy cập biến/scope/bean và trả kết quả |

Một parser có thể phân tích biểu thức thành object đánh giá được:

```java
import org.springframework.binding.expression.Expression;
import org.springframework.binding.expression.ExpressionParser;
import org.springframework.binding.expression.ParserContext;

// Ví dụ minh họa contract của Spring Binding.
// Parser thực tế được Web Flow cấu hình và quản lý.
Expression expression =
        expressionParser.parseExpression(
                "bookingService.find(hotelId)",
                parserContext);
```

Đây là ví dụ về abstraction, không phải lời khuyên tự tạo parser trong mỗi action. Trong ứng dụng, Web Flow nhận parser qua `FlowBuilderServices` khi xây dựng flow definitions.

**Parser không phải transition engine.** Parser chỉ diễn giải biểu thức. Engine vẫn chịu trách nhiệm xác định state hiện tại, nhận event, chọn transition và gọi biểu thức tại đúng lifecycle hook như `on-start`, `on-entry`, `on-render` hoặc `<evaluate>`.

## 3. Lịch sử các ngôn ngữ biểu thức qua các phiên bản Web Flow

Khi đọc một ứng dụng cũ, không thể chỉ nhìn cú pháp `#{...}` rồi kết luận chắc chắn parser nào đang sử dụng. Lịch sử chính của Web Flow như sau:

| Phiên bản / giai đoạn | Ngôn ngữ và hành vi được tài liệu mô tả | Ý nghĩa khi nâng cấp |
|---|---|---|
| Web Flow 1.0 | OGNL được dùng độc quyền trong flow definitions | Biểu thức cũ có thể mang cú pháp và hành vi OGNL |
| Web Flow 2.0 | Bổ sung Unified EL; Unified EL là mặc định trong giai đoạn đầu, thường dùng JBoss EL | Ứng dụng có thể phụ thuộc `el-api`/`org.jboss.el` |
| Web Flow 2.1 | Spring EL trở thành lựa chọn mặc định được khuyến nghị; Unified EL và OGNL vẫn có thể được cắm vào | Có thể bắt đầu chuyển biểu thức sang SpEL |
| Web Flow 2.4.8 | Hỗ trợ OGNL bị đánh dấu deprecated | Không nên tiếp tục xây mới trên OGNL |
| Web Flow 2.5.1 | Tài liệu khuyến nghị Spring EL; phần cấu hình hệ thống cũng ghi nhận parser mặc định có thể chọn Unified EL nếu có trên classpath, nếu không thì dùng Spring EL | Cần xác minh cấu hình và classpath thực tế, tránh phụ thuộc lựa chọn ngầm |

Một điểm cần chú ý khi đọc tài liệu 2.5.1: chương Expression Language gọi Spring EL là ngôn ngữ mặc định được khuyến nghị và mô tả Unified EL như lựa chọn thay thế; phần System Setup lại nói parser mặc định chọn Unified EL nếu implementation có trên classpath, nếu không sẽ dùng Spring EL. Với một ứng dụng legacy, điều này có nghĩa **dependency trên classpath có thể ảnh hưởng parser được chọn**. Cách triển khai dễ kiểm soát là cấu hình rõ parser mong muốn thay vì dựa vào classpath tình cờ.

Lịch sử phiên bản cũng giải thích vì sao cùng một ứng dụng có thể chạy khác nhau giữa môi trường development và production: một container có thể cung cấp Unified EL trong khi môi trường khác không có; một dependency cũ được kéo bắc cầu có thể làm thay đổi parser mặc định.

## 4. Phân biệt OGNL, Unified EL và Spring EL

### 4.1. OGNL

OGNL (Object-Graph Navigation Language) được Web Flow 1.0 sử dụng cho biểu thức trong flow definition. Ứng dụng cũ có thể chứa các biểu thức đọc thuộc tính, gọi method, truy cập collection và dùng các toán tử theo cú pháp OGNL.

Ví dụ mang tính minh họa:

```text
booking.customer.name
booking.guests.size()
```

Không nên dùng vài biểu thức đơn giản như trên để kết luận toàn bộ cú pháp OGNL tương thích với SpEL. Các biểu thức phức tạp, truy cập static member, constructor, collection projection/selection và quy tắc chuyển kiểu cần được rà soát riêng.

OGNL support đã bị deprecated từ Web Flow 2.4.8. Nếu ứng dụng còn parser hoặc dependency OGNL, hãy xác định rõ nó còn được dùng ở đâu trước khi loại bỏ.

### 4.2. Unified EL

Unified EL là ngôn ngữ biểu thức được sử dụng rộng trong Java web, thường đi cùng `el-api` và một implementation như JBoss EL. Web Flow 2.0 dùng Unified EL làm lựa chọn mặc định ở giai đoạn đầu; Web Flow 2.x vẫn cho phép cấu hình parser Unified EL.

Ví dụ cấu hình parser Unified EL theo tài liệu Web Flow 2.5.1:

```xml
<webflow:flow-builder-services
        id="flowBuilderServices"
        expression-parser="expressionParser" />

<bean id="expressionParser"
      class="org.springframework.webflow.expression.el.WebFlowELExpressionParser">
    <constructor-arg>
        <bean class="org.jboss.el.ExpressionFactoryImpl" />
    </constructor-arg>
</bean>
```

Đây là cấu hình để **nhận diện hoặc duy trì có chủ đích** một ứng dụng đang dùng Unified EL, không phải lựa chọn mặc định được khuyến nghị cho một dự án mới. Nếu ứng dụng có custom converters, parser Unified EL cần được cấu hình với conversion service phù hợp; nếu không, hành vi chuyển kiểu trong flow có thể khác hành vi ở Spring MVC.

### 4.3. Spring EL (SpEL)

Spring Expression Language (SpEL) được tích hợp trong Spring Framework. Web Flow cung cấp `WebFlowSpringELExpressionParser` để kết nối SpEL với abstraction `ExpressionParser` và đăng ký các property accessor dành riêng cho Web Flow.

SpEL là lựa chọn được tài liệu Web Flow khuyến nghị vì tích hợp tốt với hệ sinh thái Spring, bao gồm cơ chế chuyển kiểu và formatting của Spring. Ứng dụng sử dụng SpEL có thể tham chiếu bean, biến flow, gọi method và dùng các cú pháp như safe navigation.

Ví dụ:

```xml
<on-start>
    <evaluate expression="bookingService.createBooking(hotelId, currentUser?.name)"
              result="flowScope.booking" />
</on-start>
```

Ở đây biểu thức được đánh giá trong ngữ cảnh Web Flow, nên có thể truy cập `hotelId`, `currentUser` và bean `bookingService` nếu các đối tượng đó được cung cấp đúng cách.

## 5. Standard expression và template expression

Đây là điểm cú pháp dễ bị chuyển đổi sai nhất.

Web Flow phân biệt **standard expression** và **template expression**:

- **Standard expression:** một biểu thức EL được đánh giá trực tiếp. Không cần bọc bằng `#{...}`.
- **Template expression:** chuỗi có phần văn bản tĩnh và một hoặc nhiều đoạn biểu thức. Đoạn biểu thức cần được bọc bằng `#{...}`.

### 5.1. Standard expression

```xml
<evaluate expression="bookingService.findHotels(searchCriteria)"
          result="flowScope.hotels" />

<set name="flowScope.selectedHotelId"
     value="selectedHotel.id" />
```

Không viết:

```xml
<evaluate expression="#{bookingService.findHotels(searchCriteria)}" />
```

Trong `expression` của `<evaluate>`, nội dung là standard expression. Thêm delimiter có thể khiến parser xem `#{...}` là ký tự dư thừa và gây lỗi đánh giá.

### 5.2. Template expression

```xml
<view-state id="error"
            view="error-#{externalContext.locale}.html" />
```

Kết quả là một chuỗi được ghép từ phần văn bản `error-`, giá trị `externalContext.locale` và phần đuôi `.html`.

### 5.3. Không thay delimiter hàng loạt

Khi nâng từ Unified EL sang SpEL, tài liệu Web Flow có chỉ dẫn chuyển `${...}` sang `#{...}` trong flow definitions. Tuy nhiên, **không nên thay toàn bộ chuỗi `${...}` trong toàn bộ web application**:

- `${...}` trong JSP có thể là JSP/Unified EL của view layer.
- `#{...}` trong Facelets có thể là biểu thức JSF component.
- `#{...}` trong flow XML có thể là template expression của parser Web Flow.
- Placeholder `${property.name}` trong Spring configuration có thể là property placeholder, không phải biểu thức của Web Flow.

Chỉ chuyển đổi các biểu thức thuộc **flow definition và parser thực tế đang dùng**, sau khi xác định đúng thuộc tính XML có nhận template expression hay không.

## 6. Những thay đổi cú pháp thường gặp khi chuyển Unified EL sang SpEL

Spring EL và Unified EL có nhiều điểm tương tự, nhưng tài liệu Web Flow nêu một số thay đổi cụ thể cần xử lý.

| Biểu thức cũ (Unified EL) | Biểu thức mới (Spring EL) | Vì sao cần đổi |
|---|---|---|
| `${booking.id}` trong template expression của flow | `#{booking.id}` | Delimiter template trong flow definition |
| `#{currentEvent == 'submit'}` | `#{currentEvent.id == 'submit'}` | `currentEvent` là object Event, không phải chuỗi ID |
| `#{currentUser.name}` | `#{currentUser?.name}` | Safe navigation khi `currentUser` có thể null |
| `#{currentUser != null ? currentUser.name : null}` | `#{currentUser?.name}` | Cách viết null-safe ngắn gọn của SpEL |

### 6.1. So sánh currentEvent theo ID

Đây là lỗi chuyển đổi dễ bỏ sót:

```xml
<!-- Cũ: giả định currentEvent là chuỗi -->
<decision-state id="routeAfterSubmit">
    <if test="currentEvent == 'submit'"
        then="review"
        else="enterDetails" />
</decision-state>

<!-- Mới: currentEvent là Event, so sánh thuộc tính id -->
<decision-state id="routeAfterSubmit">
    <if test="currentEvent.id == 'submit'"
        then="review"
        else="enterDetails" />
</decision-state>
```

Nếu không đổi, biểu thức có thể không trả kết quả như mong muốn vì đang so sánh object `Event` với `String`. Cách an toàn là xác định kiểu của biến trước khi so sánh, không chỉ thay cú pháp theo cảm tính.

### 6.2. Truy cập thuộc tính có thể null

Biểu thức:

```xml
<on-start>
    <evaluate expression="auditService.recordUser(currentUser.name)" />
</on-start>
```

có thể phát sinh lỗi khi `currentUser` chưa được xác thực hoặc không tồn tại trong context. SpEL hỗ trợ safe navigation:

```xml
<on-start>
    <evaluate expression="auditService.recordUser(currentUser?.name)" />
</on-start>
```

Tuy nhiên, safe navigation chỉ giúp tránh lỗi truy cập thuộc tính khi receiver null. Nó không thay thế việc kiểm tra quyền hoặc xác định hành động có được phép chạy khi không có người dùng hiện tại hay không. Nếu `currentUser` bắt buộc phải tồn tại để tạo booking, nên từ chối theo chính sách bảo mật/nghiệp vụ thay vì âm thầm truyền null.

## 7. Cấu hình rõ ExpressionParser cho flow definitions

Parser được gắn vào `FlowBuilderServices`, và registry dùng các builder services đó để xây dựng flow definitions.

### 7.1. Cấu hình SpEL tường minh bằng XML

Ví dụ cấu hình Spring Web Flow 2.5.x:

```xml
<webflow:flow-builder-services
        id="flowBuilderServices"
        expression-parser="webFlowExpressionParser" />

<bean id="webFlowExpressionParser"
      class="org.springframework.webflow.expression.spel.WebFlowSpringELExpressionParser">
    <constructor-arg>
        <bean class="org.springframework.expression.spel.standard.SpelExpressionParser" />
    </constructor-arg>
</bean>

<webflow:flow-registry
        id="flowRegistry"
        flow-builder-services="flowBuilderServices"
        base-path="/WEB-INF/flows">
    <webflow:flow-location path="/WEB-INF/flows/checkout/checkout.xml" />
</webflow:flow-registry>
```

Cấu hình này nói rõ flow definitions sử dụng `WebFlowSpringELExpressionParser`. Bean parser cần dùng đúng implementation của Web Flow để có các property accessor cho flow context; không nên thay bằng một `SpelExpressionParser` thuần rồi giả định nó tự biết `flowScope`, `currentEvent` hoặc các biến đặc biệt của Web Flow.

Nếu ứng dụng có custom conversion service, hãy nối đúng conversion service vào `flow-builder-services` và parser theo API của version đang chạy. Đừng giả định conversion service của Spring MVC và Web Flow luôn là cùng một instance hoặc cùng loại abstraction.

### 7.2. Cấu hình Java

Với ứng dụng dùng Java configuration và `AbstractFlowConfiguration`, ý tưởng tương đương là:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.binding.expression.ExpressionParser;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.engine.builder.support.FlowBuilderServices;
import org.springframework.webflow.expression.spel.WebFlowSpringELExpressionParser;

@Configuration
public class WebFlowConfig extends AbstractFlowConfiguration {

    @Bean
    public ExpressionParser webFlowExpressionParser() {
        return new WebFlowSpringELExpressionParser(
                new SpelExpressionParser());
    }

    @Bean
    public FlowBuilderServices flowBuilderServices() {
        return getFlowBuilderServicesBuilder()
                .setExpressionParser(webFlowExpressionParser())
                .build();
    }

    // flowRegistry() phải dùng flowBuilderServices() này.
}
```

Đây là đoạn cấu hình minh họa cho Web Flow 2.x. Phần registry còn lại phải được cấu hình để sử dụng `flowBuilderServices()`. Nếu ứng dụng dùng JSF, cần xem cấu hình `faces:flow-builder-services` và parser có property accessor cho JSF (ví dụ `FacesSpringELExpressionParser`) thay vì sao chép nguyên cấu hình MVC.

### 7.3. Khi vẫn phải duy trì Unified EL

Một ứng dụng có thể tạm thời giữ Unified EL nếu còn nhiều flow hoặc thư viện phụ thuộc. Khi đó cần cấu hình parser có chủ đích, giữ conversion service tương thích và kiểm tra dependency `el-api`/implementation:

```xml
<webflow:flow-builder-services
        id="legacyFlowBuilderServices"
        expression-parser="legacyUnifiedElParser"
        conversion-service="flowConversionService" />

<bean id="legacyUnifiedElParser"
      class="org.springframework.webflow.expression.el.WebFlowELExpressionParser">
    <constructor-arg>
        <bean class="org.jboss.el.ExpressionFactoryImpl" />
    </constructor-arg>
    <property name="conversionService" ref="flowConversionService" />
</bean>
```

Đây là cấu hình để minh họa việc ứng dụng chủ động chọn Unified EL. Khi duy trì parser cũ, cần kiểm tra security advisory, version dependency và điều kiện triển khai. Nếu mục tiêu là nâng cấp lâu dài, lập kế hoạch chuyển sang parser được hỗ trợ thay vì giữ Unified EL chỉ vì flow cũ chưa được kiểm thử.

## 8. Những nơi thường chứa biểu thức cũ

Đừng chỉ tìm `#{` trong file XML. Biểu thức có thể nằm ở nhiều thuộc tính và nhiều loại artifact:

| Vị trí | Ví dụ | Công việc rà soát |
|---|---|---|
| `<evaluate>` | `expression="bookingService.save(booking)"` | Method call, tên bean, tham số và kiểu trả về |
| `<set>` | `value="requestParameters.hotelId"` | Nguồn/đích, scope, conversion |
| `<if>` | `test="booking != null"` | Boolean expression và null safety |
| `<decision-state>` | `if test="searchResults.size() > 0"` | Toán tử, method và kiểu collection |
| `<input>`/`<output>` | `value="flowScope.booking.id"` | Mapping input/output và type conversion |
| `<transition>` | Criterion hoặc exception condition | Event, exception và điều kiện |
| `view` / `subflow` template | `view="error-#{externalContext.locale}.jsp"` | Template delimiter và resource resolution |
| Java Action | API tạo/đánh giá `Expression` | Parser tạo thủ công và context evaluation |
| Spring XML/Java config | Bean `expressionParser` | Parser thực tế được đăng ký |
| Dependency tree | `org.ognl`, `org.jboss.el` | Dependency trực tiếp/bắc cầu ảnh hưởng parser |

Tìm theo các từ khóa `${`, `#{`, `currentEvent`, `currentUser`, `expression-parser`, `WebFlowELExpressionParser`, `Ognl` và `ExpressionParser`. Sau đó phân loại từng kết quả theo ngữ cảnh; một chuỗi `${...}` trong JSP không nhất thiết là biểu thức của flow engine.

## 9. Phân biệt EL trong flow definition với EL của view technology

Một ứng dụng có thể đồng thời dùng:

- SpEL hoặc Unified EL để đánh giá flow definitions.
- JSP EL trong JSP.
- Unified EL/Facelets EL trong JSF.
- Expression language riêng của template engine khác.

Các ngôn ngữ này có thể dùng ký hiệu tương tự nhưng thuộc các parser/lifecycle khác nhau.

Ví dụ với JSP:

```jsp
${booking.customerName}
```

Ví dụ trong flow XML:

```xml
<evaluate expression="bookingService.findBooking(orderId)"
          result="flowScope.booking" />
```

Ví dụ trong Facelets:

```xhtml
<h:outputText value="#{booking.customerName}" />
```

Không thay delimiter của JSP/Facelets chỉ vì đã chuyển parser của flow XML. Với JSF, các biểu thức gắn vào component còn chịu lifecycle của JSF; Web Flow tích hợp qua `FacesFlowBuilderServices` và parser có property accessor phù hợp.

Tương tự, `MvcViewFactoryCreator` có thể sử dụng view resolver và binding của Spring MVC. Parser dùng cho flow definition và cơ chế binding/view rendering là những cấu hình liên quan nhưng không đồng nhất.

## 10. Rủi ro khi parser được chọn ngầm từ classpath

Một hệ thống cũ có thể không khai báo `expression-parser` rõ ràng. Parser mặc định sẽ được chọn theo cấu hình và dependency có trên classpath của phiên bản Web Flow.

Trong Web Flow 2.5.1, phần System Setup ghi rõ parser mặc định dùng Unified EL nếu implementation có trên classpath, nếu không thì dùng Spring EL. Vì vậy, việc thêm một dependency vào `pom.xml` hoặc `build.gradle` có thể làm thay đổi cách flow được phân tích mà không có thay đổi trong XML.

Hãy rà soát:

1. Có bean `expressionParser` nào được khai báo không?
2. `flow-builder-services` có thuộc tính `expression-parser` không?
3. Flow registry có dùng đúng builder services đó không?
4. Classpath có `org.jboss.el`, `javax.el`, `org.ognl` hoặc implementation EL nào khác?
5. Có module/war/container cung cấp implementation khác nhau giữa các môi trường không?
6. Java configuration có gọi `setExpressionParser(...)` ở một nơi khác không?
7. JSF configuration có sử dụng parser chuyên biệt không?

Nếu môi trường dev không có JBoss EL nhưng production có, cùng một flow XML có thể được xử lý bằng parser khác. Điều này dễ dẫn đến lỗi chỉ xuất hiện sau khi deploy.

**Giải pháp:** cấu hình parser tường minh, khóa version dependency, kiểm tra dependency tree và kiểm thử khởi động flow trong môi trường có classpath tương đương production.

## 11. Lưu ý bảo mật khi duy trì Unified EL parser

Khi nâng cấp ứng dụng legacy, parser không chỉ là vấn đề cú pháp. Spring đã công bố advisory **CVE-2026-40985 — Data Binding Vulnerability in Spring Web Flow with Unified EL Parser** ngày 10-06-2026.

Advisory nêu các điều kiện để ứng dụng bị ảnh hưởng:

1. Ứng dụng cấu hình tường minh `WebFlowELExpressionParser` hoặc lớp cơ sở `ELExpressionParser`.
2. Thuộc tính cấu hình `useSpringBinding` chưa được đặt thành `true`.
3. Các `view-state` không dùng phần tử `<binding>` để khai báo các thuộc tính được phép bind.

Các phiên bản bị ảnh hưởng được advisory liệt kê gồm:

- Spring Web Flow `2.5.1.RELEASE` và các phiên bản trước đó.
- Spring Web Flow `3.0.0–3.0.1`.
- Spring Web Flow `4.0.0`.

Các phiên bản sửa lỗi được công bố:

| Nhánh | Phiên bản sửa lỗi | Tình trạng được advisory công bố |
|---|---|---|
| 2.5.x | `2.5.2` | Enterprise Support Only |
| 3.0.x | `3.0.2` | OSS |
| 4.0.x | `4.0.1` | OSS |

Nếu ứng dụng có Unified EL parser, hãy kiểm tra đúng các điều kiện trong advisory và nâng cấp lên phiên bản đã sửa phù hợp với chính sách hỗ trợ của dự án. Không suy luận rằng mọi ứng dụng dùng Unified EL đều có cùng mức độ ảnh hưởng; advisory yêu cầu đồng thời các điều kiện nêu trên. Cũng không coi việc chỉ thay cú pháp `${...}` thành `#{...}` là bản vá bảo mật.

Đọc advisory chính thức trước khi quyết định biện pháp:

[Spring Security Advisory — CVE-2026-40985](https://spring.io/security/cve-2026-40985/)

## 12. Quy trình chuyển đổi một ứng dụng legacy sang SpEL

Nên thực hiện theo từng lớp để tránh thay đổi parser, cú pháp và cấu hình view cùng một lúc.

### Bước 1: Xác định version và parser đang hoạt động

Ghi nhận:

- Phiên bản `spring-webflow`, `spring-binding`, Spring Framework và Java.
- Parser bean được khai báo trực tiếp hay được chọn mặc định.
- Dependency OGNL, Unified EL/JBoss EL và SpEL.
- Flow registry nào dùng `FlowBuilderServices` nào.
- Có tích hợp JSF hay chỉ Spring MVC.

Đừng chỉ đọc `pom.xml`. Dependency bắc cầu từ một thư viện khác hoặc container có thể làm thay đổi classpath thực tế.

### Bước 2: Lập danh sách biểu thức

Tìm toàn bộ biểu thức trong flow definitions và phân loại:

- Standard expression hay template expression.
- Thuộc tính flow XML nào chứa biểu thức.
- Parser hiện tại là OGNL, Unified EL hay SpEL.
- Có truy cập `currentEvent`, `currentUser`, scope hay bean nào?
- Có gọi method tạo side effect hay chỉ đọc dữ liệu?
- Có phụ thuộc converter/formatter tự viết không?

Đánh dấu các biểu thức phức tạp, có null, gọi method hoặc chuyển kiểu trước để ưu tiên kiểm thử.

### Bước 3: Cấu hình parser đích rõ ràng

Chọn `WebFlowSpringELExpressionParser` cho flow definitions sử dụng SpEL. Gắn parser vào `flow-builder-services` mà registry sử dụng. Nếu có nhiều registry hoặc ứng dụng đa module, kiểm tra từng registry; không giả định một bean builder services tự động áp dụng cho tất cả.

### Bước 4: Chuyển biểu thức theo từng nhóm

Bắt đầu từ các thay đổi có quy tắc rõ:

- Chuyển delimiter template trong flow từ `${...}` sang `#{...}` khi đúng ngữ cảnh.
- Sửa phép so sánh event để dùng `currentEvent.id`.
- Bổ sung null-safe navigation hoặc điều kiện rõ ràng khi object có thể null.
- Rà soát các phép toán, collection access, method overload và custom type conversion.
- Với biểu thức OGNL phức tạp, viết lại theo SpEL và test kết quả; không chỉ thay tên parser.

### Bước 5: Giữ ranh giới với view layer

Không sửa JSP/Facelets chỉ vì parser của flow definitions thay đổi. Kiểm tra riêng các biểu thức trong view theo công nghệ render của ứng dụng.

### Bước 6: Chạy regression test

Chạy tất cả flow có biểu thức được chuyển. Xác minh state, outcome, dữ liệu scope, binding, validation, subflow và exception path. Các biểu thức có side effect phải được kiểm tra số lần gọi và thứ tự gọi, không chỉ kết quả cuối.

### Bước 7: Triển khai có khả năng rollback

Triển khai trên môi trường có dependency/classpath giống production. Theo dõi lỗi parser, `EvaluationException`, `PropertyNotFoundException`, `SpelEvaluationException`, lỗi binding và lỗi conversion. Nếu phải rollback, bảo đảm version XML và parser quay lại cùng một bộ tương thích.

## 13. Ma trận kiểm thử biểu thức sau nâng cấp

Một bộ kiểm thử hữu ích nên bao gồm các nhóm sau:

| Nhóm | Ví dụ kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Gọi bean | `bookingService.find(hotelId)` | Đúng bean, đúng method và tham số |
| Gán scope | `result="flowScope.booking"` | Giá trị được lưu đúng scope |
| Input mapping | `requestParameters.hotelId` | Chuyển kiểu đúng với input contract |
| Current event | `currentEvent.id == 'submit'` | Rẽ nhánh đúng event |
| Null safety | `currentUser?.name` | Không lỗi khi user null; nghiệp vụ xử lý đúng |
| Template expression | `error-#{externalContext.locale}.html` | Sinh đúng view ID |
| Collection | `searchResults.size() > 0` | Kết quả đúng với collection rỗng/không rỗng |
| Custom converter | Giá trị domain type trong `<input>` | Converter được gọi và trả kiểu đúng |
| Action side effect | `bookingService.confirm(booking)` | Chỉ gọi đúng số lần và đúng thời điểm |
| Validation failure | Biểu thức dùng model chưa hợp lệ | Hiển thị lỗi, không chuyển nhầm state |
| Subflow output | `currentEvent.attributes.booking` | Outcome và output mapping giữ đúng contract |
| Exception path | Bean method ném exception | Handler/transition lỗi vẫn chạy đúng |
| Khác môi trường | Chạy với classpath production | Parser thực tế giống cấu hình đã chọn |

Đừng chỉ kiểm thử biểu thức bằng một đoạn unit test SpEL độc lập. Biểu thức Web Flow còn phụ thuộc property accessor, `RequestContext`, implicit variables, conversion service và lifecycle hook. Hãy có kiểm thử flow runtime để xác nhận ngữ cảnh thực tế.

## 14. Ví dụ trước và sau khi nâng cấp

Giả sử flow cũ có điều kiện kiểm tra event và hiển thị thông tin người dùng:

```xml
<!-- Cũ: giả định currentEvent là chuỗi -->
<decision-state id="routeAfterSubmit">
    <if test="currentEvent == 'submit'"
        then="review"
        else="enterDetails" />
</decision-state>

<view-state id="review"
            view="review-#{currentUser.name}.jsp" />
```

Sau khi chuyển sang SpEL, viết lại:

```xml
<!-- Mới: currentEvent là Event, currentUser được truy cập null-safe -->
<decision-state id="routeAfterSubmit">
    <if test="currentEvent.id == 'submit'"
        then="review"
        else="enterDetails" />
</decision-state>

<view-state id="review"
            view="review-#{currentUser?.name}.jsp" />
```

Hai thay đổi giải quyết hai khác biệt:

- `currentEvent` là object `Event`, nên cần đọc `id`.
- `currentUser` có thể null, nên safe navigation tránh lỗi truy cập thuộc tính.

Tuy nhiên, nếu tên người dùng được dùng để tạo view path, cần kiểm tra view resolver và whitelist/encoding phù hợp. Safe navigation không biến một chuỗi tùy ý thành đường dẫn tài nguyên an toàn. Trong ứng dụng thật, nên chọn view cố định và truyền dữ liệu người dùng vào model thay vì nhúng trực tiếp dữ liệu tự do vào view ID.

## 15. Các lỗi thường gặp sau khi đổi parser

**Lỗi 1 — Property hoặc field không tìm thấy.** Có thể do tên biến không nằm trong context, sai scope, property không tồn tại hoặc parser không có Web Flow property accessor. Kiểm tra tên bean/variable và dùng đúng `WebFlowSpringELExpressionParser`.

**Lỗi 2 — `currentEvent == 'submit'` luôn false.** `currentEvent` là Event object. So sánh `currentEvent.id` với chuỗi event ID.

**Lỗi 3 — NullPointerException khi truy cập `currentUser.name`.** Kiểm tra trường hợp user chưa có trong context; dùng safe navigation khi phù hợp và xác định rõ nhánh nghiệp vụ khi user null.

**Lỗi 4 — Template view ID không được ghép đúng.** Xác định thuộc tính có hỗ trợ template expression hay chỉ standard expression. Chỉ dùng `#{...}` trong vị trí cần ghép chuỗi.

**Lỗi 5 — Biểu thức gọi bean không tìm thấy method.** Kiểm tra bean có được expose vào evaluation context, method public, số lượng/kiểu tham số, overload và conversion service.

**Lỗi 6 — Converter hoạt động ở Spring MVC nhưng thất bại trong Web Flow.** Hai hệ thống có thể dùng conversion service khác nhau. Cấu hình `flow-builder-services` với conversion service tương ứng.

**Lỗi 7 — Chỉ production lỗi.** So sánh dependency/classpath của Unified EL, parser bean, class loader và version Spring. Không giả định parser được chọn giống môi trường dev.

**Lỗi 8 — Đổi delimiter làm hỏng JSP.** Có thể đã sửa nhầm view EL hoặc Spring property placeholder. Chỉ đổi trong flow definitions đúng ngữ cảnh.

**Lỗi 9 — OGNL cũ vẫn chạy sau nâng cấp.** Có thể ứng dụng vẫn đang cắm parser OGNL hoặc kéo dependency cũ. Kiểm tra parser bean và dependency tree; không coi việc build thành công là bằng chứng đã chuyển sang SpEL.

## 16. Checklist hoàn tất nâng cấp

- [ ] Đã xác định chính xác phiên bản Web Flow và parser runtime.
- [ ] Đã rà soát bean `ExpressionParser`, `flow-builder-services` và mọi registry sử dụng nó.
- [ ] Đã kiểm tra dependency trực tiếp/bắc cầu của OGNL, Unified EL/JBoss EL và Spring EL.
- [ ] Đã phân loại standard expression và template expression.
- [ ] Đã chuyển `currentEvent` sang so sánh `currentEvent.id` khi phù hợp.
- [ ] Đã kiểm tra null-safety và hành vi khi thiếu input/user/model.
- [ ] Đã kiểm tra custom converters/formatters của Web Flow.
- [ ] Đã giữ riêng biểu thức flow XML với JSP/Facelets/template expressions của view.
- [ ] Đã kiểm thử các state, transition, subflow, validation, output và exception path.
- [ ] Đã so sánh classpath giữa development, test và production.
- [ ] Đã đánh giá advisory CVE-2026-40985 nếu có cấu hình Unified EL parser.
- [ ] Đã triển khai trên môi trường staging và có kế hoạch rollback tương thích.

## 17. Ghi nhớ

`ExpressionParser` là abstraction phân tích chuỗi biểu thức thành `Expression` có thể đánh giá trong context. Web Flow 1.0 dùng OGNL; Web Flow 2 chuyển sang hỗ trợ Unified EL và Spring EL, với SpEL trở thành lựa chọn được khuyến nghị. OGNL support đã deprecated, còn parser mặc định của một số cấu hình 2.5.x có thể bị ảnh hưởng bởi Unified EL có mặt trên classpath.

Khi nâng cấp, hãy **xác định parser runtime trước, cấu hình parser đích tường minh, chuyển đổi cú pháp theo từng loại biểu thức và kiểm thử trong flow execution thật**. Đặc biệt chú ý standard expression so với template expression, `currentEvent.id`, null navigation, custom conversion và ranh giới giữa flow XML với view EL.

Không nên coi đổi parser là thay chuỗi cú pháp đơn thuần: một biểu thức còn phụ thuộc context, scope, bean, converter và lifecycle mà nó được đánh giá. Rà soát đúng các thành phần này giúp ứng dụng legacy tiếp tục điều khiển state/event/transition ổn định sau nâng cấp.

### Tài liệu tham khảo

- [Spring Web Flow 2.5.1 — Expression Language](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/#_expression_language) — standard/template expressions, SpEL, Unified EL, portability và implicit variables.
- [Spring Web Flow 2.5.1 — System Setup: expression-parser](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/system-setup.html) — cấu hình parser trong `flow-builder-services` và hành vi parser mặc định.
- [Spring Web Flow 2.5.1 — WebFlowSpringELExpressionParser API](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/expression/spel/WebFlowSpringELExpressionParser.html) — parser SpEL có property accessor dành cho Web Flow.
- [Spring Web Flow 2.5.1 — WebFlowELExpressionParser API](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/expression/el/WebFlowELExpressionParser.html) — parser Unified EL.
- [Spring Web Flow 2.4.x — Upgrading from 1.0](https://docs.spring.io/spring-webflow/docs/2.4.x/reference/htmlsingle/#_upgrading_from_1_0) — khác biệt Web Flow 1.x/2.x và lịch sử OGNL/SpEL.
- [Spring Security Advisory — CVE-2026-40985](https://spring.io/security/cve-2026-40985/) — điều kiện ảnh hưởng và phiên bản sửa lỗi cho Unified EL parser.
