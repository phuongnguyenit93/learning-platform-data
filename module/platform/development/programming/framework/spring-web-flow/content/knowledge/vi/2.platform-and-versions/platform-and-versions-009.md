# Tổ chức mã Java, định nghĩa flow, view và tài nguyên

*Chương: Nền tảng và phiên bản · Module: SPRING_WEB_FLOW*

Spring Web Flow giúp mô hình hóa một hành trình web gồm nhiều bước bằng state, event, transition và subflow. Thay vì để controller tự quyết định màn hình tiếp theo, ta khai báo hành trình trong flow definition, đặt nghiệp vụ trong các lớp Java và để Spring MVC kết nối yêu cầu HTTP với bộ máy thực thi flow. Cách tổ chức này đặc biệt hữu ích cho quy trình đăng ký, đặt chỗ, thanh toán, phê duyệt hoặc nhập liệu nhiều màn hình.

Trong module SPRING_WEB_FLOW, mục tiêu là hiểu cách tổ chức một ứng dụng dùng Spring Web Flow: mã Java đảm nhiệm nghiệp vụ và cấu hình; flow definition mô tả trạng thái và điều hướng; view hiển thị dữ liệu và phát event; các tài nguyên hỗ trợ cung cấp thông điệp, giao diện tĩnh và kiểm thử. Bài học này tập trung vào cách những phần đó được đặt cạnh nhau và phối hợp trong một ứng dụng Spring MVC.

Sau bài học, bạn có thể:

- Phân biệt flow definition với một lần thực thi flow của người dùng.
- Tổ chức package Java, thư mục flow, view và tài nguyên theo một quy ước dễ tìm.
- Giải thích vai trò của FlowDefinitionRegistry, FlowExecutor và các thành phần tích hợp Spring MVC.
- Đọc và xây dựng flow XML có view state, action state, transition và end state.
- Kết nối form binding, validation, scope và subflow với các lớp Java.
- Chọn vị trí lưu cấu hình, template, thông điệp và bài kiểm thử phù hợp.

## 1. Phân chia trách nhiệm giữa Java, flow và view

Một ứng dụng Spring Web Flow thường có ba lớp trách nhiệm chính:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Mã Java | Chứa mô hình miền, nghiệp vụ, truy cập dữ liệu, validator và cấu hình Spring | OrderDraft, CheckoutService, ShippingValidator, WebFlowConfig |
| Flow definition | Mô tả các state, event, transition, action và subflow của hành trình | checkout-flow.xml |
| View | Hiển thị dữ liệu, nhận dữ liệu biểu mẫu và gửi event về flow | cart.jsp, shipping.jsp, review.jsp |

Các tài nguyên khác bổ sung cho ba lớp trên. File properties chứa nhãn và thông báo đa ngôn ngữ; CSS, JavaScript và hình ảnh tạo nên giao diện; cấu hình Spring MVC xác định cách tìm view và xử lý request; test xác minh từng nhánh của hành trình.

Không nên đặt toàn bộ nghiệp vụ vào biểu thức trong XML. Flow definition nên đọc được như một bản mô tả quy trình. Khi cần tính giá, lưu đơn hàng, kiểm tra quyền hoặc gọi hệ thống ngoài, flow gọi một Spring bean có trách nhiệm rõ ràng. Cách làm này giữ cho flow dễ xem xét và cho phép kiểm thử nghiệp vụ độc lập.

Sơ đồ dưới đây thể hiện đường đi điển hình của một request:

~~~mermaid
flowchart TD
    A[Trình duyệt gửi request hoặc event] --> B[FlowHandlerMapping]
    B --> C[FlowHandlerAdapter]
    C --> D[FlowExecutor]
    D --> E[FlowDefinitionRegistry]
    E --> F[Flow definition và state hiện tại]
    F --> G[Java service hoặc validator]
    F --> H[ViewResolver]
    H --> I[View template]
    I --> A
~~~

FlowHandlerMapping tìm flow phù hợp với URL. FlowHandlerAdapter chuyển request cho FlowExecutor. Executor tìm định nghĩa trong registry, tiếp tục đúng lần thực thi đang hoạt động, gọi hành động cần thiết và trả kết quả về view. Tên bean và cách đăng ký có thể khác giữa cấu hình Java và XML, nhưng các trách nhiệm trên vẫn là nền tảng của kiến trúc.

## 2. Cấu trúc thư mục tham khảo

Với một ứng dụng checkout nhỏ, có thể bắt đầu bằng cấu trúc sau:

~~~text
src/
├── main/
│   ├── java/com/acme/checkout/
│   │   ├── config/
│   │   │   ├── WebMvcConfig.java
│   │   │   └── WebFlowConfig.java
│   │   ├── domain/
│   │   │   ├── OrderDraft.java
│   │   │   └── ShippingAddress.java
│   │   ├── service/
│   │   │   └── CheckoutService.java
│   │   ├── validation/
│   │   │   └── ShippingValidator.java
│   │   └── repository/
│   │       └── OrderRepository.java
│   ├── resources/
│   │   ├── messages.properties
│   │   └── messages_vi.properties
│   └── webapp/WEB-INF/
│       ├── flows/
│       │   └── checkout/
│       │       ├── checkout-flow.xml
│       │       ├── cart.jsp
│       │       ├── shipping.jsp
│       │       ├── review.jsp
│       │       └── complete.jsp
│       └── views/
│           └── error.jsp
└── test/
    └── java/com/acme/checkout/
        ├── service/CheckoutServiceTests.java
        └── flow/CheckoutFlowTests.java
~~~

Đây là một quy ước tham khảo, không phải cấu trúc bắt buộc của Spring Web Flow. Điểm quan trọng là có thể nhận ra ngay đâu là mã nghiệp vụ, đâu là định nghĩa hành trình và đâu là giao diện của hành trình.

Một số nguyên tắc tổ chức hữu ích:

- Chia package Java theo trách nhiệm hoặc miền nghiệp vụ. Service không nên phụ thuộc vào JSP; domain object không nên biết state ID của flow.
- Gom các file định nghĩa và view liên quan vào cùng thư mục flow để dễ lần theo một hành trình.
- Đặt flow definition ở nơi ứng dụng có thể nạp được nhưng trình duyệt không thể truy cập trực tiếp. Với ứng dụng servlet truyền thống, thư mục dưới WEB-INF là lựa chọn thường gặp.
- Đặt tài nguyên tĩnh và tài nguyên đa ngôn ngữ ở vị trí được cấu hình riêng. Không đặt file flow XML trong thư mục public static.
- Đặt test flow riêng với unit test của service, vì hai loại test xác minh hai lớp hành vi khác nhau.

Nếu dự án dùng Thymeleaf hoặc một template engine khác, template có thể nằm trong thư mục tài nguyên mà view resolver của dự án quy định, chẳng hạn src/main/resources/templates. Không cần ép mọi dự án dùng JSP; điều cần giữ nhất quán là tên view trong flow phải được view resolver ánh xạ tới đúng template.

## 3. Flow definition, flow execution và các thành phần runtime

Ba khái niệm sau thường bị nhầm lẫn:

**Flow definition** là bản mô tả quy trình. Nó định nghĩa state có thể xuất hiện, event nào làm thay đổi state và hành động nào cần chạy. Nhiều người dùng có thể cùng chạy một flow definition.

**Flow execution** là một lần chạy cụ thể của định nghĩa đó. Mỗi người dùng có thể đang ở một state khác nhau, mang dữ liệu riêng trong scope và có execution key riêng để tiếp tục hành trình qua nhiều request.

**Flow ID** là tên dùng để tìm flow definition trong registry. **State ID** là tên một state bên trong definition. Hai ID này thuộc hai cấp khác nhau: flow ID xác định hành trình, state ID xác định vị trí hiện tại trong hành trình.

Các thành phần runtime phối hợp như sau:

| Thành phần | Vai trò |
|---|---|
| FlowDefinitionRegistry | Đăng ký và tra cứu flow definition theo flow ID |
| FlowExecutor | Khởi chạy, tiếp tục và kết thúc flow execution |
| FlowHandlerMapping | Ánh xạ request của Spring MVC tới flow tương ứng |
| FlowHandlerAdapter | Chuyển request đã được ánh xạ cho FlowExecutor xử lý |
| ViewResolver / view factory | Chuyển tên view trong flow thành template hoặc view object có thể render |
| FlowExecutionRepository | Lưu hoặc khôi phục trạng thái execution giữa các request, tùy cấu hình repository |

Ví dụ, registry có thể đăng ký flow ID là checkout. Khi người dùng mở URL được ánh xạ tới flow đó, FlowExecutor bắt đầu một execution và đưa người dùng vào state đầu tiên. Sau khi view phát event continue, request tiếp theo mang thông tin execution để executor khôi phục đúng phiên làm việc rồi áp dụng transition tương ứng.

Vì vậy, không nên tự tạo một controller riêng cho từng màn hình chỉ để chuyển qua màn hình kế tiếp. Controller vẫn hữu ích cho các endpoint thông thường như trang tra cứu hoặc API, còn hành trình nhiều bước nên được mô tả bằng flow khi cần quản lý state, dữ liệu và nhánh chuyển tiếp một cách tập trung.

## 4. Định nghĩa flow và transition

Flow definition thường được viết bằng XML. Ví dụ sau mô tả một quy trình checkout giản lược:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="checkoutService.createDraft()"
                  result="flowScope.order"/>
    </on-start>

    <view-state id="cart" view="checkout/cart">
        <transition on="continue" to="shipping"/>
    </view-state>

    <view-state id="shipping" view="checkout/shipping">
        <transition on="back" to="cart"/>
        <transition on="continue" to="review"/>
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="confirm" to="saveOrder"/>
    </view-state>

    <action-state id="saveOrder">
        <evaluate expression="checkoutService.confirm(flowScope.order)"/>
        <transition to="complete"/>
    </action-state>

    <end-state id="complete" view="checkout/complete"/>
</flow>
~~~

Ví dụ này có các loại state thường gặp:

- **view-state** hiển thị một view và chờ event từ người dùng. Thuộc tính view là tên logic được chuyển cho cơ chế tạo view.
- **action-state** chạy một hoặc nhiều action phía server. Nó phù hợp với thao tác như xác nhận đơn hàng hoặc gọi service.
- **end-state** kết thúc flow. Một end state có thể trỏ tới view kết quả để hiển thị thông báo hoàn tất.

**transition** mô tả event và state đích. Ví dụ, event continue tại state cart đưa execution sang shipping. Event back tại shipping đưa người dùng trở lại cart. Tên event do view gửi phải khớp với thuộc tính on của transition; tên state đích phải tồn tại trong cùng flow definition.

**on-start** chạy khi flow execution bắt đầu. Đây là nơi phù hợp để khởi tạo dữ liệu ban đầu hoặc tải ngữ cảnh cần thiết. Các thao tác có thể thất bại nên được đặt trong service có xử lý lỗi rõ ràng, thay vì viết một chuỗi biểu thức nghiệp vụ dài trong XML.

Trong ví dụ, checkoutService là Spring bean được ứng dụng đăng ký. Flow gọi bean bằng biểu thức, còn việc tạo draft và xác nhận đơn hàng nằm trong lớp Java. Cách phân chia này giúp thay đổi quy trình mà không phải nhồi toàn bộ nghiệp vụ vào controller.

### View phát event như thế nào?

Một view cần gửi event có tên đúng với transition. Với JSP và Spring form tag, ví dụ rút gọn có thể như sau:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form modelAttribute="order" method="post">
    <label for="recipient">Người nhận</label>
    <form:input path="shippingAddress.recipient" id="recipient"/>

    <label for="street">Địa chỉ</label>
    <form:input path="shippingAddress.street" id="street"/>

    <button type="submit" name="_eventId_continue">Tiếp tục</button>
    <button type="submit" name="_eventId_back">Quay lại</button>
</form:form>
~~~

Trong quy ước gửi event của Spring Web Flow, tên nút dạng _eventId_continue phát event continue. Các trường form được bind vào object mà flow đưa ra cho view. Tên modelAttribute và đường dẫn thuộc tính phải khớp với object cùng cấu trúc dữ liệu thực tế. Nếu dùng Thymeleaf hoặc HTML thuần, cách tạo request có thể khác, nhưng event gửi về vẫn phải có tên phù hợp với transition.

Không nên nhầm tên view với state ID. State shipping có thể render view checkout/shipping; hai tên có mục đích riêng. Tách chúng ra giúp thay template mà không nhất thiết phải đổi logic state.

## 5. Đăng ký flow và tích hợp Spring MVC

Flow definition chỉ có thể chạy khi được registry phát hiện. Với cấu hình Java, một cấu hình điển hình có dạng:

~~~java
package com.acme.checkout.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.config.EnableWebFlow;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;

@Configuration
@EnableWebFlow
public class WebFlowConfig extends AbstractFlowConfiguration {

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
                .setBasePath("/WEB-INF/flows")
                .addFlowLocationPattern("/**/*-flow.xml")
                .build();
    }
}
~~~

Trong ví dụ, registry tìm các file có hậu tố -flow.xml bên dưới base path. File checkout/checkout-flow.xml là một ứng viên phù hợp. Cách suy ra flow ID phụ thuộc vào vị trí và quy ước đăng ký; hãy xác nhận ID mà registry tạo ra rồi dùng cùng ID trong URL, lời gọi subflow và test. Không nên đoán ID chỉ từ tên file.

Annotation EnableWebFlow cùng lớp cấu hình nền của Spring Web Flow cung cấp các thành phần tích hợp cần thiết cho flow execution. Ứng dụng vẫn cần cấu hình Spring MVC và view resolver phù hợp với công nghệ giao diện đang dùng. Nếu dự án dùng cấu hình XML thay cho Java config, flow registry và flow executor có thể được khai báo bằng namespace của Spring Web Flow; hãy chọn một cách cấu hình nhất quán để tránh đăng ký trùng bean.

Ví dụ, nếu view resolver dùng prefix /WEB-INF/flows/ và suffix .jsp, tên view checkout/cart có thể được ánh xạ tới /WEB-INF/flows/checkout/cart.jsp. Đây chỉ là một cấu hình minh họa: đường dẫn thực tế phải khớp prefix, suffix và loại view resolver trong ứng dụng. Khi view không hiển thị, cần kiểm tra cả tên view trong flow lẫn đường dẫn mà resolver tạo ra.

Flow thường được truy cập qua URL do FlowHandlerMapping quản lý. Flow ID, URL mapping và registry pattern cần thống nhất. Nếu ứng dụng còn dùng controller mapping, cần kiểm tra thứ tự mapping để request dành cho flow không bị một handler khác chiếm trước.

### Khai báo dependency

Ứng dụng cần thư viện Spring Web Flow ở runtime; test flow có thể dùng thư viện hỗ trợ kiểm thử tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ không ghi version vì version nên được quản lý thống nhất qua parent POM hoặc dependency management của dự án. Trước khi nâng cấp, hãy kiểm tra khả năng tương thích giữa Spring Web Flow, Spring Framework, Spring MVC, Java, servlet container và các thư viện tích hợp như Spring Security. Không nên chọn một phiên bản Web Flow độc lập mà bỏ qua nền tảng Spring đang chạy.

## 6. Binding và validation trong view state

View state có thể khai báo các thuộc tính được phép bind từ form. Ví dụ:

~~~xml
<view-state id="shipping" view="checkout/shipping">
    <binder>
        <binding property="shippingAddress.recipient"/>
        <binding property="shippingAddress.street"/>
        <binding property="shippingAddress.postalCode"/>
    </binder>

    <transition on="continue" to="review">
        <evaluate expression="shippingValidator.validate(flowRequestContext, messageContext)"/>
    </transition>
</view-state>
~~~

Các property trong binder phải tồn tại trên model object mà view state sử dụng. Việc khai báo binding rõ ràng giới hạn dữ liệu được nhận từ form và làm cho cấu trúc form dễ kiểm tra. Không nên bind tùy tiện mọi thuộc tính của domain object, đặc biệt là giá tiền, trạng thái thanh toán hoặc quyền sở hữu do server quyết định.

ShippingValidator là Spring bean chịu trách nhiệm kiểm tra dữ liệu. Có thể dùng MessageContext để đưa lỗi có mã trường và nội dung phù hợp về view. Ví dụ minh họa:

~~~java
package com.acme.checkout.validation;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Component;
import org.springframework.webflow.execution.RequestContext;

import com.acme.checkout.domain.OrderDraft;

@Component("shippingValidator")
public class ShippingValidator {

    public void validate(RequestContext context, MessageContext messages) {
        OrderDraft order = (OrderDraft) context.getFlowScope().get("order");
        String postalCode = order.getShippingAddress().getPostalCode();

        if (postalCode == null || postalCode.trim().isEmpty()) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("shippingAddress.postalCode")
                    .defaultText("Vui lòng nhập mã bưu chính.")
                    .build());
        }
    }
}
~~~

Đây là ví dụ đơn giản để minh họa cách lấy dữ liệu trong flow scope và thêm lỗi vào message context. Trong ứng dụng thực tế, cần xử lý trường hợp order hoặc shippingAddress chưa được khởi tạo, chuẩn hóa dữ liệu trước khi kiểm tra và thống nhất tên trường lỗi với form. Cũng cần kiểm thử rằng khi có lỗi, người dùng được giữ ở màn hình phù hợp và nhìn thấy thông báo; khi dữ liệu hợp lệ, transition mới tiếp tục tới state review.

Nên phân biệt ba lớp kiểm tra:

1. Binding kiểm soát cách dữ liệu request được đưa vào model.
2. Validation kiểm tra dữ liệu có hợp lệ theo quy tắc nghiệp vụ hay không.
3. Service kiểm tra các điều kiện cần dữ liệu đáng tin cậy hoặc cần truy cập hệ thống, ví dụ tồn kho, giá hiện tại và quyền thực hiện thao tác.

Không dùng validation ở giao diện làm hàng rào bảo vệ duy nhất. Service vẫn phải kiểm tra lại các điều kiện quan trọng trước khi ghi dữ liệu.

## 7. Quản lý scope và tổ chức subflow

Spring Web Flow cung cấp nhiều scope để giữ dữ liệu trong khoảng thời gian phù hợp. Chọn scope quá rộng có thể khiến dữ liệu tồn tại lâu hơn cần thiết; chọn scope quá ngắn có thể làm mất dữ liệu khi người dùng chuyển state.

| Scope | Thời gian tồn tại điển hình | Dữ liệu phù hợp |
|---|---|---|
| requestScope | Trong request hiện tại | Giá trị tạm chỉ dùng khi xử lý một request |
| flashScope | Qua request kế tiếp, thường dùng để chuyển thông báo | Thông báo thành công hoặc lỗi sau một chuyển tiếp |
| viewScope | Trong thời gian view state hiện tại còn hoạt động | Dữ liệu hỗ trợ riêng cho một màn hình |
| flowScope | Trong suốt một flow execution | Draft hoặc dữ liệu hành trình nhiều bước |
| conversationScope | Trong conversation gốc và các subflow liên quan | Dữ liệu cần chia sẻ giữa flow cha và flow con |

Ví dụ checkout giữ OrderDraft trong flowScope vì dữ liệu cần tồn tại từ màn hình giỏ hàng tới màn hình xác nhận. Một thông báo ngắn sau khi lưu có thể đặt trong flashScope. Không nên đưa dữ liệu lớn, bí mật hoặc dữ liệu có thể tải lại dễ dàng vào scope chỉ vì tiện truy cập.

### Khi nào tách subflow?

Subflow hữu ích khi một phần quy trình có thể được tái sử dụng hoặc có vòng đời riêng. Ví dụ, checkout có thể gọi subflow địa chỉ giao hàng, còn một quy trình đăng ký tài khoản cũng dùng lại bước chọn địa chỉ. Flow cha truyền input cho subflow và nhận event cùng output khi subflow kết thúc.

Trong flow cha:

~~~xml
<subflow-state id="collectAddress" subflow="address">
    <input name="customer" value="flowScope.customer"/>
    <transition on="completed" to="review"/>
</subflow-state>
~~~

Trong flow địa chỉ, end state có thể công bố dữ liệu đầu ra:

~~~xml
<end-state id="completed">
    <output name="address" value="flowScope.address"/>
</end-state>
~~~

Tên subflow phải khớp với flow ID đã đăng ký. Input và output là hợp đồng giữa flow cha và flow con: chỉ truyền dữ liệu mà flow con thực sự cần, đặt tên rõ nghĩa và xác định event kết thúc thành công hoặc hủy. Nếu subflow có thể kết thúc theo nhiều cách, flow cha nên khai báo transition riêng cho từng event để hành vi dễ đọc.

Không nên tách subflow chỉ để chia một file XML dài thành nhiều file nhỏ. Chỉ tách khi phần quy trình có ý nghĩa độc lập, có thể tái sử dụng hoặc cần được kiểm thử riêng. Nếu việc tách làm luồng dữ liệu và event khó theo dõi hơn, giữ state trong flow cha có thể đơn giản hơn.

## 8. View, thông điệp và tài nguyên tĩnh

View là lớp trình bày. View nhận model do flow cung cấp, hiển thị dữ liệu và phát event. View không nên tự quyết định state tiếp theo hoặc gọi trực tiếp repository để thay đổi nghiệp vụ.

Tên view trong flow là tên logic. View resolver hoặc view factory quyết định tên đó trỏ tới JSP, Thymeleaf template hay một loại view khác. Vì vậy, khi một view không được tìm thấy, hãy kiểm tra theo thứ tự:

1. Thuộc tính view của view state có đúng tên logic không?
2. View resolver có được đăng ký trong Spring MVC và được flow sử dụng không?
3. Prefix, suffix và vị trí template có khớp với cấu trúc thư mục không?
4. Template có được đóng gói trong artifact triển khai không?

Thông điệp giao diện và validation nên đặt trong resource bundle, ví dụ messages.properties và messages_vi.properties. Dùng message code thay vì viết cố định mọi câu thông báo trong JSP hoặc flow XML sẽ giúp dịch thuật và thay đổi nội dung dễ hơn.

CSS, JavaScript và hình ảnh cần được phục vụ qua cơ chế static resource của Spring MVC hoặc servlet container. Chúng thường nằm trong src/main/resources/static, src/main/webapp/resources hoặc vị trí tương đương tùy cấu hình. Flow XML và các view nội bộ nên được đặt dưới vùng không truy cập trực tiếp từ trình duyệt, chẳng hạn WEB-INF trong ứng dụng servlet.

## 9. Kiểm thử flow và kiểm thử Java

Một unit test của CheckoutService nên xác minh quy tắc nghiệp vụ như tính tổng tiền, kiểm tra tồn kho và lưu đơn hàng. Một flow test nên xác minh hành trình: state bắt đầu, event hợp lệ, transition, validation, subflow và trạng thái kết thúc.

Spring Web Flow cung cấp các lớp hỗ trợ kiểm thử flow XML. Ví dụ khung test sau minh họa cách nạp flow definition và xác minh state đầu tiên:

~~~java
import org.junit.Test;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;
import org.springframework.webflow.test.execution.FlowDefinitionResource;
import org.springframework.webflow.test.execution.FlowDefinitionResourceFactory;
import org.springframework.webflow.test.MockExternalContext;

public class CheckoutFlowTests extends AbstractXmlFlowExecutionTests {

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createResource(
                "file:src/main/webapp/WEB-INF/flows/checkout/checkout-flow.xml");
    }

    @Test
    public void startsAtCart() {
        MockExternalContext context = new MockExternalContext();
        startFlow(context);
        assertCurrentStateEquals("cart");
    }
}
~~~

Đường dẫn resource trong test phải khớp cách dự án lưu flow definition. Tùy phiên bản thư viện test và cách cấu hình, dự án có thể dùng các helper assertion hoặc API kiểm thử khác; hãy đối chiếu API của phiên bản đang sử dụng. Khi mở rộng test, cần gửi event continue để xác minh state shipping, gửi dữ liệu không hợp lệ để xác minh validation, rồi kiểm tra nhánh hủy và nhánh hoàn tất.

Một bộ test có ích nên bao phủ ít nhất:

- Flow khởi động ở state dự kiến và dữ liệu ban đầu được tạo đúng.
- Mỗi event hợp lệ đi tới đúng state đích.
- Event không được khai báo không làm execution chuyển sang một state ngoài dự kiến.
- Binding và validation xử lý dữ liệu thiếu, sai định dạng và dữ liệu hợp lệ.
- Subflow nhận đúng input, phát đúng event kết thúc và trả đúng output.
- Lỗi từ service được xử lý theo chính sách của ứng dụng, không để người dùng mắc kẹt ở một state không thể tiếp tục.
- Flow hết hạn hoặc execution không còn tồn tại được đưa tới trải nghiệm phục hồi phù hợp.

## 10. Lỗi tổ chức thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy flow | Registry pattern hoặc base path không khớp vị trí XML | Kiểm tra pattern, đường dẫn đóng gói và flow ID |
| URL mở nhầm controller | Handler mapping khác nhận request trước | Kiểm tra mapping và thứ tự xử lý của Spring MVC |
| Không tìm thấy view | Tên view không khớp view resolver | Đối chiếu view ID, prefix, suffix và template |
| Biểu mẫu không chuyển state | Tên event gửi lên khác tên transition | Kiểm tra nút submit và thuộc tính on |
| Dữ liệu bị mất giữa các bước | Dữ liệu đặt trong scope có vòng đời quá ngắn | Chọn scope theo thời gian sống cần thiết |
| Bean không được gọi | Service hoặc validator chưa được đăng ký trong application context | Kiểm tra component scan và tên bean trong expression |
| Flow chạy nhưng không lưu được | Service lỗi, transaction hoặc dữ liệu đầu vào không hợp lệ | Kiểm tra log, ranh giới transaction và xử lý lỗi |
| Subflow không được mở | Subflow ID không khớp registry hoặc thiếu input bắt buộc | Kiểm tra flow ID, input mapping và output contract |

Một lỗi thiết kế khác là đặt quá nhiều logic điều hướng trong controller, view và service cùng lúc. Khi đó không có một nơi duy nhất mô tả quy trình, nên việc thêm một bước hoặc một nhánh lỗi dễ làm hành vi giữa các màn hình mất nhất quán. Hãy để flow sở hữu trình tự state và event; để service sở hữu nghiệp vụ; để view sở hữu cách trình bày.

## 11. Quy trình tạo một flow mới

Khi thêm một hành trình mới, có thể làm theo thứ tự sau:

1. Mô tả các bước người dùng thực hiện và xác định state đầu, state kết thúc, các nhánh quay lại, hủy và lỗi.
2. Xác định dữ liệu cần tồn tại qua nhiều bước; chọn scope phù hợp và tạo domain object trong Java.
3. Tạo service cho nghiệp vụ và validator cho các quy tắc nhập liệu; đăng ký chúng trong Spring context.
4. Tạo flow XML, khai báo state, event, transition, action và subflow cần thiết.
5. Tạo view tương ứng, bind đúng thuộc tính và phát event khớp với transition.
6. Kiểm tra registry tìm thấy flow, URL được ánh xạ đúng và view resolver tìm được template.
7. Viết flow test cho đường đi thành công, validation lỗi, quay lại, hủy và lỗi từ service.
8. Chạy ứng dụng qua toàn bộ hành trình để kiểm tra request thực tế, session, bảo mật và khả năng phục hồi khi execution hết hạn.

## Kết luận

Một ứng dụng Spring Web Flow dễ bảo trì khi mỗi lớp có ranh giới rõ: Java chứa mô hình và nghiệp vụ; flow definition mô tả state, event và transition; view trình bày dữ liệu và gửi event; tài nguyên cung cấp template, thông điệp và nội dung tĩnh. Registry và executor nối các định nghĩa đó với từng flow execution, còn Spring MVC đảm nhiệm việc định tuyến request và render view.

Khi tổ chức mã theo các trách nhiệm này, nhóm phát triển có thể đọc được toàn bộ hành trình ở flow definition, kiểm thử nghiệp vụ độc lập trong Java và kiểm thử các nhánh điều hướng bằng flow test. Đây là nền tảng để mở rộng quy trình nhiều bước mà vẫn kiểm soát được dữ liệu, lỗi và trải nghiệm người dùng.
