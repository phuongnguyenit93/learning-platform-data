# flowScope và dữ liệu của một flow session trong Spring Web Flow

Trong quy trình đăng ký, đặt hàng hoặc đặt lịch nhiều màn hình, người dùng nhập dữ liệu ở bước đầu, xem lại ở bước sau, rồi có thể quay về chỉnh sửa. Một HTTP request thông thường kết thúc sau mỗi lần gửi form; dữ liệu lưu trong request scope không tự đi theo người dùng qua toàn bộ hành trình. **Spring Web Flow (SWF)** giải quyết nhu cầu này bằng các scope gắn với vòng đời flow, trong đó **`flowScope`** lưu thông tin dùng qua nhiều state của **một flow session**.

Bài thuộc chương **Dữ liệu và scope** của module `SPRING_WEB_FLOW`. Trọng tâm là cách khởi tạo, đọc, ghi và giải phóng dữ liệu trong `flowScope`; phân biệt flow session với flow execution và HTTP session; kết hợp form binding/validation, action, subflow, kiểm thử, quản lý phiên và phục hồi khi flow gặp lỗi.

## 1. Phân biệt flow execution, flow session và flowScope

Khi người dùng khởi chạy một flow, SWF tạo **flow execution**: một lượt thực hiện hành trình web, có thể gồm flow gốc và các subflow. Trong execution, mỗi lần một flow được kích hoạt có một **flow session** tương ứng. Khi flow cha gọi flow con, flow con có một flow session khác và sau khi kết thúc trả kết quả về flow cha.

`flowScope` là vùng dữ liệu key/value gắn với **flow session đang hoạt động**. Các state trong cùng flow session có thể cùng đọc và thay đổi giá trị ở vùng này. Khi flow session kết thúc, scope của nó cũng kết thúc về mặt ngữ nghĩa của execution.

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| **Flow definition** | Bản mô tả các state, event, transition | File XML định nghĩa `checkout` |
| **Flow execution** | Một lượt thực thi hành trình, có thể chứa cả subflow | Người mua A đang đặt một đơn |
| **Flow session** | Một lần thực thi một flow trong stack của execution | Flow `checkout` hoặc subflow `selectShipping` |
| **flowScope** | Dữ liệu của flow session hiện tại | `orderDraft`, `deliveryOption` |
| **HTTP session** | Phiên HTTP của người dùng ở servlet container | Phiên đăng nhập và có thể là kho giữ các flow executions |

Hai cửa sổ/tab cùng đăng nhập có thể khởi chạy hai **flow execution khác nhau**. Cả hai ở trong cùng HTTP session nhưng mỗi execution có flowScope riêng; model ở wizard A không tự động là model ở wizard B. Ngược lại, nếu hai tab dùng chung URL của **cùng một execution**, chúng có thể tương tác với các snapshot liên quan và cần kiểm thử hành vi submit lặp hoặc request cũ.

~~~mermaid
flowchart TD
    B["Trình duyệt: bắt đầu checkout"] --> E["Flow execution"]
    E --> P["Flow session cha: checkout"]
    P --> PS["flowScope: orderDraft"]
    P --> V1["view-state: enterAddress"]
    V1 -->|"next"| V2["view-state: review"]
    V2 -->|"back"| V1
    P --> S["subflow-state: selectShipping"]
    S --> C["Flow session con: shippingFlow"]
    C --> CS["flowScope riêng của flow con"]
    C --> X["end-state: selected"]
    X -->|"output / outcome"| P
    P --> F["end-state: completed"]
~~~

Lưu ý: `conversationScope` có thể được chia sẻ qua flow cha và các subflow của cùng conversation, nhưng hai flowScope của cha/con **không phải một map chung**.

## 2. Vòng đời của một biến trong flowScope

Có thể nhìn vòng đời theo chuỗi:

1. **Flow bắt đầu:** SWF tạo flow session và khởi tạo dữ liệu được khai báo bằng `<var>` hoặc hành động `<on-start>`.
2. **Hiển thị view-state:** view đọc model thuộc flowScope để hiển thị giá trị form.
3. **Nhận POST/event:** form binding cập nhật model và validator kiểm tra dữ liệu nếu được cấu hình.
4. **Chuyển state:** dữ liệu còn đó khi chuyển sang view khác trong cùng flow session.
5. **Quay lại:** view trước có thể render lại dữ liệu đã nhập mà không cần tạo một request-scoped model mới.
6. **Gọi subflow:** flow con có scope riêng, nhận dữ liệu bằng input và trả về bằng output.
7. **Kết thúc flow:** khi đến end-state, flow session kết thúc; không tiếp tục dùng flowScope như một kho dữ liệu vĩnh viễn.

Một số thao tác thủ công cũng có thể cập nhật hoặc xóa biến trước khi flow kết thúc, nên không nên giả định mọi key luôn tồn tại.

### 2.1. Khởi tạo bằng `<var>`

Ví dụ flow đăng ký đặt hàng dùng DTO `OrderDraft` có các field `deliveryAddress`, `deliveryInstructions` và `customerEmail`:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <var name="orderDraft"
         class="com.example.checkout.OrderDraft" />

    <view-state id="enterAddress"
                view="checkout/enter-address"
                model="orderDraft">
        <transition on="next" to="review"
                    bind="true" validate="true" />
        <transition on="cancel" to="cancelled"
                    bind="false" />
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="back" to="enterAddress" />
        <transition on="confirm" to="placeOrder" />
    </view-state>

    <action-state id="placeOrder">
        <evaluate expression="orderService.placeOrder(flowScope.orderDraft)" />
        <transition on="success" to="completed" />
        <transition on="failure" to="orderError" />
    </action-state>

    <view-state id="orderError" view="checkout/order-error">
        <transition on="back" to="review" />
    </view-state>

    <end-state id="completed" view="checkout/completed" />
    <end-state id="cancelled" />
</flow>
~~~

`<var name="orderDraft" .../>` khai báo biến của flow, được khởi tạo từ kiểu ứng dụng cung cấp và có thể tham chiếu qua `flowScope.orderDraft`. Lớp `OrderDraft` phải có cơ chế khởi tạo phù hợp (ví dụ constructor không tham số) và getters/setters cho binding. `model="orderDraft"` chỉ ra đối tượng form mà view-state thao tác.

Mỗi lần đi giữa `enterAddress` và `review`, flow session chưa kết thúc nên `orderDraft` vẫn được giữ. Điều này không có nghĩa SWF tự lưu một bản ghi đơn hàng vào database. Đoạn flow chỉ làm việc đó khi bước action/service được thiết kế thực hiện ghi; service phải tự kiểm tra các tiền điều kiện nghiệp vụ và trả outcome tương thích `success` hoặc `failure`.

### 2.2. Khởi tạo từ service ở `<on-start>`

Nếu một bản nháp cần được dựng từ dữ liệu server, có thể dùng:

~~~xml
<on-start>
    <evaluate expression="draftService.createForCurrentUser()"
              result="flowScope.orderDraft" />
</on-start>
~~~

Đây là **phương án thay thế** cách khởi tạo `orderDraft` bằng `<var>` ở ví dụ trước; nên chọn một chiến lược khởi tạo rõ ràng. `draftService` là bean nghiệp vụ phải được đăng ký. Nếu trả `null` hoặc ném exception, ứng dụng cần có đường xử lý lỗi phù hợp trước khi bước kế tiếp truy cập model.

## 3. Đọc, ghi và kiểm tra dữ liệu bằng flow expressions

Trong flow XML, expression có thể tham chiếu rõ scope đang dùng. Các dạng phổ biến:

| Việc cần làm | Ví dụ | Kết quả |
|---|---|---|
| Đọc toàn bộ draft | `flowScope.orderDraft` | Đối tượng draft hiện tại |
| Đọc một field | `flowScope.orderDraft.deliveryAddress` | Địa chỉ giao hàng đã nhập |
| Ghi một flag trong scope | `<set name="flowScope.reviewSeen" value="true" />` | Ghi dấu đã xem trang review |
| Lưu kết quả một phép tính | `<evaluate expression="quoteService.quote(flowScope.orderDraft)" result="flowScope.quote" />` | Dùng báo giá ở các bước sau |
| Kiểm tra điều kiện | `flowScope.orderDraft != null` | Guard trước khi truy cập các field |

Ví dụ một decision-state dùng dữ liệu của flow:

~~~xml
<decision-state id="checkAddress">
    <if test="flowScope.orderDraft != null and
              flowScope.orderDraft.deliveryAddress != null"
        then="review"
        else="enterAddress" />
</decision-state>
~~~

Ở đây toán tử `and` có ý nghĩa **ngắn mạch** khi dùng SpEL: vế sau chỉ được đánh giá khi vế trước đúng. Nhánh `else` xử lý trường hợp thiếu dữ liệu có chủ đích; nếu biểu thức ném exception vì lỗi service hoặc cách truy cập thuộc tính khác, `else` không tự động bắt exception.

Cú pháp `<set>` và `<evaluate>` chỉ nên dùng ở vị trí hợp lệ trong flow definition, chẳng hạn một action hook hoặc transition, theo schema của phiên bản SWF đang dùng.

### 3.1. Request parameter không phải dữ liệu đã được xác thực

Cách đặt thẳng giá trị form vào draft như sau có thể bỏ qua bước kiểm tra mong muốn:

~~~xml
<set name="flowScope.orderDraft.quantity"
     value="requestParameters.quantity" />
~~~

`requestParameters.quantity` do client gửi, có thể giả mạo hoặc sai kiểu. Với dữ liệu form, nên dùng binding và validation của `view-state`; với các field quan trọng như `unitPrice`, `ownerId` hoặc `paid`, service phải lấy giá trị từ nguồn tin cậy, không đưa các field đó vào danh sách thuộc tính khách được sửa.

## 4. Form binding cập nhật model đang ở flowScope

Một lợi thế của `flowScope` là cùng một model có thể được binding qua nhiều HTTP request. Ví dụ `enterAddress` khai báo:

~~~xml
<view-state id="enterAddress"
            view="checkout/enter-address"
            model="orderDraft">
    <transition on="next" to="review"
                bind="true" validate="true" />
    <transition on="cancel" to="cancelled"
                bind="false" />
</view-state>
~~~

Trong JSP dùng Spring Form tags:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="orderDraft">
    <label for="deliveryAddress">Địa chỉ</label>
    <form:input path="deliveryAddress" id="deliveryAddress" />
    <form:errors path="deliveryAddress" />

    <label for="deliveryInstructions">Ghi chú giao hàng</label>
    <form:textarea path="deliveryInstructions"
                   id="deliveryInstructions" />

    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel">Hủy</button>
</form:form>
~~~

Đối với JSP thật, `${flowExecutionUrl}` ở đây là expression `flowExecutionUrl` do SWF đưa vào view; sử dụng URL thực thi của flow đang hoạt động, vốn có thể mang execution key, thay vì tự dựng URL cố định. Nếu Spring Security bật CSRF, form cần token hợp lệ theo cấu hình; đoạn code chỉ tập trung vào binding.

Luồng xử lý khi người dùng bấm **Tiếp tục**:

1. Request có dữ liệu form và event ID `next`, được gửi đến execution URL hiện tại.
2. SWF tìm transition `on="next"` của state `enterAddress`.
3. Binding đưa field vào `orderDraft` và chạy quy tắc validation đã cấu hình.
4. Nếu dữ liệu hợp lệ, flow đi tới `review`; nếu validation thất bại, framework thường render lại view nhập với lỗi, không chuyển sang bước review.
5. Khi phát event `back`, màn hình nhập lại hiển thị các giá trị đã được giữ trong cùng flow session.

`bind="false"` trên transition `cancel` giúp người dùng hủy khi form chưa hợp lệ mà không bị bắt buộc nhập mọi trường.

### 4.1. Model được giữ không đồng nghĩa được lưu bền vững

Nếu người dùng nhấn **Quay lại**, mô hình `orderDraft` còn ở flowScope nên màn hình có thể hiển thị các field vừa nhập. Nhưng nếu flow execution đã kết thúc, session hết hạn hoặc snapshot không còn khả dụng, không nên kỳ vọng khôi phục draft bằng URL cũ.

Muốn người dùng dừng hôm nay rồi tiếp tục ngày mai, hãy lưu bản nháp vào database với `draftId`, rồi tải lại qua service sau khi xác minh danh tính và quyền sở hữu.

## 5. Truy cập `flowScope` từ Java Action

Một action Java triển khai interface `Action` có thể làm việc với flow scope thông qua `RequestContext`:

~~~java
import org.springframework.webflow.execution.Action;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class VerifyDraftAction implements Action {

    private final DraftPolicyService draftPolicyService;

    public VerifyDraftAction(DraftPolicyService draftPolicyService) {
        this.draftPolicyService = draftPolicyService;
    }

    @Override
    public Event execute(RequestContext context) {
        OrderDraft draft =
            (OrderDraft) context.getFlowScope().get("orderDraft");

        if (draft == null) {
            return new Event(this, "missingDraft");
        }

        boolean allowed = draftPolicyService.canReview(draft);
        context.getFlowScope().put("reviewAllowed", allowed);
        return new Event(this, allowed ? "approved" : "rejected");
    }
}
~~~

`DraftPolicyService` và `OrderDraft` là các kiểu minh họa do ứng dụng tự viết. `getFlowScope()` trả về scope của **flow session đang hoạt động**; lời gọi `get` để đọc model, `put` để ghi giá trị có thể dùng trong các state tiếp theo. Dữ liệu chỉ cần tồn tại trong một phương thức nên giữ trong biến cục bộ; không cần ghi mọi giá trị vào scope.

Có thể dùng action trên trong flow:

~~~xml
<action-state id="verifyDraft">
    <evaluate expression="verifyDraftAction.execute(flowRequestContext)" />
    <transition on="approved" to="review" />
    <transition on="rejected" to="enterAddress" />
    <transition on="missingDraft" to="restartRequired" />
</action-state>
~~~

`verifyDraftAction` phải là bean mà expression resolver của SWF tìm được; các state đích cần khai báo trong flow thật. Biến `flowRequestContext` là ngữ cảnh do SWF cung cấp trong các cách cấu hình hỗ trợ expression này. Nếu service ném exception, exception không tự được chuyển thành `rejected`; cần xử lý lỗi riêng.

## 6. Chọn đúng scope cho từng loại dữ liệu

| Scope | Thời gian sống điển hình | Ví dụ dùng phù hợp |
|---|---|---|
| `requestScope` | Một lần xử lý HTTP request | Một giá trị trung gian phục vụ render hiện tại |
| `flashScope` | Thông tin ngắn hạn qua lần render/transition tiếp theo | Thông báo lỗi hoặc thành công tạm |
| `viewScope` | Trong khi một view-state còn hoạt động | Từ khóa lọc trong một màn hình |
| **`flowScope`** | Trong một flow session | Form draft, lựa chọn nhiều bước |
| `conversationScope` | Conversation bao quanh flow cha và subflow | Dữ liệu cố ý chia sẻ ở cấp conversation |
| HTTP `HttpSession` | Phiên HTTP của servlet container | Một số dữ liệu ứng dụng, authentication/session |

Ví dụ, `flowScope.orderDraft` được dùng cho thông tin đặt hàng cần xem qua nhiều bước, còn `viewScope.searchPage` chỉ cần trong màn hình chọn điểm giao. Nếu rời view rồi quay lại, không nên giả định viewScope trước vẫn còn; flowScope của cùng flow session có thể giữ lựa chọn giao hàng đã xác nhận.

`conversationScope` có vòng đời rộng hơn, thích hợp khi flow cha và con cần một dữ liệu chung được quản lý có chủ đích. Không sử dụng conversationScope chỉ để né việc thiết kế input/output rõ ràng của subflow. HTTP session có thể chứa nhiều execution, nên lưu mọi bản nháp wizard vào một session attribute chung như `currentOrder` dễ gây ghi đè giữa nhiều tab.

## 7. Khi gọi subflow, flowScope của cha và con có giống nhau không?

**Không.** Khi flow cha gọi subflow, flow con có flow session riêng và `flowScope` riêng. Cần truyền dữ liệu cần thiết **vào** subflow qua input và đưa kết quả **ra** bằng output. Dùng trực tiếp cùng tên biến như `flowScope.orderDraft` ở cả hai flow không khiến chúng tự động chia sẻ cùng một object.

Ví dụ bên trong **flow cha** `checkout`:

~~~xml
<subflow-state id="selectShipping"
               subflow="shippingSelection">
    <input name="orderId"
           value="flowScope.orderDraft.orderId" />
    <transition on="selected" to="review" />
    <transition on="cancelled" to="enterAddress" />
</subflow-state>
~~~

Trong flow con `shippingSelection` có thể khai báo input và output của một lựa chọn:

~~~xml
<!-- Đoạn nằm trong flow con shippingSelection. -->
<input name="orderId" required="true" />

<view-state id="chooseMethod"
            view="shipping/choose-method">
    <transition on="next" to="selected" />
    <transition on="cancel" to="cancelled" />
</view-state>

<end-state id="selected">
    <output name="shippingMethod"
            value="flowScope.shippingMethod" />
</end-state>

<end-state id="cancelled" />
~~~

Đây là các **đoạn minh họa**, chưa phải hai flow XML hoàn chỉnh. Ứng dụng phải cấu hình phần thu nhận/ánh xạ output tại flow cha phù hợp API/schema SWF đang sử dụng và phải khởi tạo, binding `shippingMethod` trong flow con trước khi kết thúc.

Ý nghĩa của quá trình:

1. Cha lấy `orderId` trong `flowScope.orderDraft` và truyền qua input cho con.
2. Con dùng input để tải thông tin cần thiết, quản lý lựa chọn trong scope riêng.
3. Con đến `end-state id="selected"`, phát outcome `selected` cho cha và có thể xuất `shippingMethod`.
4. Cha nhận kết quả thông qua cơ chế output đã cấu hình, cập nhật draft rồi tiếp tục review.

Nếu cần chia sẻ dữ liệu rộng hơn qua một nhóm flow, `conversationScope` là công cụ khác, nhưng dùng input/output giúp hợp đồng của subflow tường minh, tránh việc flow con vô tình phụ thuộc vào tên biến nội bộ của flow cha.

### 7.1. FlowSession và stack của flow execution

Khi đang ở subflow, `RequestContext.getFlowScope()` của action trong con trỏ vào scope của **flow session con đang hoạt động**. Khi con kết thúc và trả điều khiển về cha, action trong cha truy cập lại flow scope của cha. Một flow execution có thể quản lý stack các flow session, nên khái niệm “một flow session” quan trọng hơn việc nói chung chung “dữ liệu nằm trong session”.

Điều này cũng giải thích vì sao đặt cùng key `selectedShipping` trong flow cha và flow con không đảm bảo rằng chúng nhìn thấy cùng một giá trị. Để dữ liệu đi qua ranh giới đó, hãy dùng cơ chế trao đổi có hợp đồng rõ ràng.

## 8. Dữ liệu flowScope được giữ qua HTTP request bằng cách nào?

Web Flow phải khôi phục trạng thái của một flow execution khi trình duyệt gửi event tiếp theo. Điều đó thường liên quan đến **flow execution repository** do `FlowExecutor` sử dụng. Phụ thuộc cấu hình, repository có thể giữ execution hoặc các snapshot trong HTTP session hay bằng cơ chế lưu trữ khác.

Trong trang được Web Flow render, biến `flowExecutionUrl` thường biểu thị URL cần dùng để tiếp tục execution hiện tại, ví dụ có query parameter `execution=...`. Execution key là dấu hiệu để framework tìm đúng execution/snapshot; nó **không phải bằng chứng xác thực** và cũng không phải ID của bản ghi nghiệp vụ. Không tạo execution key giả hay lưu nó như ID đơn hàng.

~~~mermaid
sequenceDiagram
    participant Browser as Trình duyệt
    participant MVC as DispatcherServlet / SWF
    participant Repo as FlowExecutionRepository
    Browser->>MVC: GET /checkout
    MVC->>Repo: Tạo/lưu flow execution
    MVC-->>Browser: Render view + flowExecutionUrl
    Browser->>MVC: POST event next + execution key
    MVC->>Repo: Khôi phục execution/snapshot
    Repo-->>MVC: flow session và flowScope
    MVC->>Repo: Cập nhật state/draft
    MVC-->>Browser: Render view review
~~~

Khi gửi POST, server thực hiện binding/transition trong execution được khôi phục. Việc render lại màn hình review không đồng nghĩa dữ liệu `orderDraft` đã được persist trong database: dữ liệu đó có thể chỉ tồn tại trong repository/session cho đến khi flow kết thúc hoặc hết hạn.

### 8.1. Vì sao cần dùng DTO gọn và phù hợp snapshot?

Nếu repository lưu snapshot hoặc serialize dữ liệu execution, việc đưa một object lớn hoặc phụ thuộc tài nguyên vào flowScope có thể gây tốn bộ nhớ hoặc lỗi khi khôi phục.

| Dữ liệu trong flowScope | Đánh giá | Gợi ý |
|---|---|---|
| DTO `OrderDraft` chứa vài field/ID | Phù hợp cho wizard | Validate trước khi dùng |
| `draftId`, `orderId` | Gọn, tiện tải lại từ DB | Luôn kiểm tra chủ sở hữu khi tải |
| Danh sách hàng chục nghìn entity | Có thể tốn nhiều RAM/snapshot | Phân trang ở service, lưu ID/bộ lọc |
| Entity JPA chứa lazy proxy | Có thể lỗi khi session persistence đóng | Mapping sang DTO độc lập |
| InputStream, file upload lớn | Có thể không serializable, có tài nguyên phải đóng | Lưu file vào kho chuyên dụng, giữ ID |
| `DataSource`, kết nối DB, bean service | Không phù hợp vòng đời flow | Inject bean ở action/service |
| Mật khẩu thô, token bí mật, thông tin thẻ | Rủi ro lộ dữ liệu trong session/snapshot/log | Không lưu trong flow scope nếu không thiết yếu |

Nếu chiến lược lưu trữ yêu cầu serialization, các kiểu dữ liệu lưu trong scope cần đáp ứng khả năng serialize/restore. `Serializable` có thể là yêu cầu thực tế của một số cấu hình, nhưng không nên khẳng định mọi ứng dụng SWF đều dùng cùng một kiểu repository. Test luồng **snapshot → khôi phục** bằng cấu hình triển khai thực tế mới đủ xác nhận.

### 8.2. Nhiều tab và dữ liệu bị ghi đè

Hai flow execution độc lập thường có scope độc lập ngay cả khi cùng một HTTP session. Nhưng hai tab có thể đang dùng chung một execution URL (ví dụ người dùng duplicate tab) hoặc cùng chỉnh **một bản ghi database** từ hai draft riêng.

Hãy kiểm tra cả hai lớp:

- **Tầng flow:** execution key nào được sử dụng, request cũ có bị từ chối hay xử lý theo snapshot khác không, và thứ tự event có hợp lệ không.
- **Tầng nghiệp vụ:** nếu hai bản nháp cùng sửa một đơn hàng thì cần optimistic locking, version hoặc quy tắc xử lý xung đột ở database/service.

Không dựa vào việc mỗi flow có scope riêng để bảo đảm một giao dịch không bị xử lý hai lần. Việc đặt hàng, thanh toán hoặc duyệt hồ sơ thường cần kiểm soát trùng lặp/idempotency ở service.

### 8.3. Session timeout và đường phục hồi

Khi người dùng để trang quá lâu, HTTP session hoặc flow execution trong repository có thể hết hạn. Request chứa execution key cũ có thể không còn khôi phục được. Việc này khác với việc validation form sai hoặc action trả outcome `failure`.

Thiết kế phục hồi nên bao gồm:

1. Thông báo rõ rằng phiên thao tác đã hết hạn hoặc flow không còn khả dụng.
2. Cho phép bắt đầu flow mới hoặc khôi phục draft **đã được lưu bền vững** bằng ID và quyền sở hữu hợp lệ.
3. Tránh tự động gửi lại POST xác nhận hoặc thanh toán, vì tác động nghiệp vụ có thể đã xảy ra.
4. Đảm bảo flow mới không tự sử dụng model nhạy cảm từ execution/session trước nếu người dùng đã logout hoặc đổi tài khoản.

## 9. Bảo mật dữ liệu trong flowScope

`flowScope` giúp tổ chức trạng thái nhiều bước, nhưng **không phải cơ chế phân quyền**. Một client có thể sửa payload form, gửi `_eventId` thủ công hoặc thử dùng lại URL của execution trước. Vì thế:

- **Giới hạn binding:** chỉ cho phép các property người dùng được phép sửa; tránh binding trực tiếp `ownerId`, `approved`, `unitPrice` hoặc `paid`.
- **Validate:** kiểm tra kiểu, độ dài, tập giá trị hợp lệ và ràng buộc nghiệp vụ ở phía server.
- **Authorization:** đối chiếu tài khoản hiện tại với tài nguyên/bản nháp thực tế trước khi đọc hoặc ghi, nhất là trước khi thực thi action quan trọng.
- **CSRF:** bảo vệ các form POST phát event theo cấu hình Spring Security/Spring MVC của ứng dụng.
- **Không giữ bí mật quá mức:** dữ liệu đăng nhập, token bảo mật và dữ liệu thanh toán nhạy cảm không nên ở flow scope chỉ để chuyển qua nhiều view.
- **Tránh log toàn bộ scope:** ghi state ID, outcome và mã lỗi an toàn; không dump dữ liệu cá nhân hoặc token ra log.
- **Kiểm tra lại tại bước ghi:** giá, tồn kho, quyền truy cập và trạng thái đơn hàng có thể thay đổi sau khi view review đã hiển thị.

Ví dụ, client có thể gửi một ID đơn hàng hợp lệ nhưng **không thuộc sở hữu của mình**. Dữ liệu ID đang ở `flowScope` không khiến người gửi tự động có quyền với đơn đó. Service cần truy vấn và đối chiếu quyền theo principal hiện tại, không tin field `ownerId` do client có thể tác động.

### 9.1. Khi nào cần lưu bản nháp vào database?

Dùng `flowScope` khi dữ liệu chỉ cần sống trong một lần đi qua wizard. Dùng database khi cần:

- Người dùng tạm dừng và tiếp tục ở thiết bị khác hoặc hôm sau.
- Hành trình cần được xử lý bất đồng bộ, qua nhiều request/service hoặc qua các phiên đăng nhập.
- Cần audit, khôi phục sau lỗi máy chủ hoặc xử lý xung đột sửa đồng thời.
- Dữ liệu là đối tượng nghiệp vụ đã được chấp nhận/ghi nhận chính thức.

Một chiến lược cân bằng: giữ `flowScope.draftId` và những field đang chỉnh sửa trong DTO nhỏ; khi save draft hoặc submit chính thức, service kiểm tra lại quyền và persist có transaction.

## 10. Kiểm thử vòng đời của flowScope

Kiểm thử cần quan sát **state, event và dữ liệu scope** sau mỗi chuyển bước, đồng thời xác nhận request thật hoạt động qua Spring MVC. Một response HTTP 200 không chứng minh bản nháp vẫn còn hoặc đã được lưu đúng nơi.

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Khởi chạy `checkout` | `orderDraft` được tạo trong flow scope |
| Submit form hợp lệ với event `next` | Binding cập nhật model và state chuyển sang `review` |
| Submit dữ liệu không hợp lệ | Vẫn ở `enterAddress` với lỗi validation |
| Event `back` từ review | Quay lại form, dữ liệu đã nhập vẫn có |
| Event `cancel` khi form thiếu trường | Hủy được nếu transition thiết kế `bind="false"` |
| Khởi chạy hai execution trong cùng HTTP session | Hai bản nháp không tự ghi đè nhau |
| Gọi subflow chọn giao hàng | Flow con nhận input, dùng scope riêng |
| Subflow trả `selected` | Flow cha nhận outcome và xử lý output đã ánh xạ |
| Action `verifyDraft` gặp model null | Chuyển tới `restartRequired` theo outcome đã quy định |
| Gửi event không được khai báo | Không thực hiện transition ngoài thiết kế |
| Flow đã kết thúc nhưng request cũ gửi lại | Không tự tạo thêm giao dịch |
| Hết hạn session/execution | Có đường phục hồi, không giả định scope vẫn còn |
| Action service ném exception | Xử lý như lỗi thực thi, không mặc định coi là outcome nghiệp vụ |
| Form giả mạo `paid=true` | Dữ liệu không được dùng làm chứng cứ thanh toán |

### 10.1. Kết hợp kiểm thử flow, HTTP và service

**Kiểm thử flow logic:** dùng các API/test support của SWF phù hợp phiên bản để khởi chạy flow, gửi event và kiểm tra state cùng các giá trị scope. Có thể dùng fake service để chủ động tạo outcome khác nhau.

**Kiểm thử tích hợp MVC:** khởi chạy flow qua `DispatcherServlet`, lấy execution URL thật từ view, duy trì cookie/session khi gửi form tiếp tục. Kiểm tra binding, validation, render và đường đi khi Back/refresh.

**Kiểm thử service:** xác minh quyền sở hữu, tính hợp lệ của bản nháp, transaction và chống submit lặp ở bước ghi. Đây là nơi kiểm tra nhất quán nghiệp vụ khi hai execution cùng sửa một bản ghi.

### 10.2. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Mất dữ liệu khi sang trang sau | Model chỉ được giữ trong request/view scope | Đặt DTO nhiều bước trong flowScope |
| `orderDraft` là null ngay đầu flow | Chưa khởi tạo biến hoặc service trả null | Khai báo `<var>`/`<on-start>`, xử lý lỗi khởi tạo |
| POST không cập nhật field | Sai `model`, sai tên field, binding/validation lỗi | Kiểm tra tên property, conversion, validator |
| Back không giữ nội dung | Dữ liệu chỉ nằm trong viewScope hoặc bị reset | Dùng flowScope cho các field cần sống qua state |
| Flow con không thấy biến của cha | Flow con có flowScope riêng | Khai báo input và output rõ ràng |
| Nhiều tab lẫn dữ liệu | Dùng một session attribute toàn cục hoặc cùng execution | Phân biệt execution key, scope, bản nháp DB |
| Server tiêu thụ nhiều RAM | Lưu collection/entity lớn và nhiều snapshot | Giữ DTO nhỏ, chỉ lưu ID khi có thể |
| Lỗi khôi phục/serialize | Object chứa proxy, stream hoặc field không tương thích | Giới hạn kiểu dữ liệu, kiểm tra repository thực tế |
| Không tiếp tục được flow cũ | Session timeout hoặc execution key hết hiệu lực | Thông báo, tạo flow mới/khôi phục draft hợp lệ |
| Đặt hàng hai lần | Replay event confirm hoặc hai flow cùng ghi | Idempotency, transaction và kiểm tra trạng thái ở service |

## 11. Bài tập thực hành: dữ liệu qua bốn bước

Hãy xây dựng flow đặt lịch gồm `customerInfo`, `serviceChoice`, `review` và `submit`, trong đó `submit` là `action-state` lưu dữ liệu.

1. Tạo DTO `BookingDraft` gồm `customerName`, `email`, `serviceCode`, `appointmentDate`; khởi tạo trong flow scope.
2. Binding/validation dữ liệu từ hai view đầu; khi Back rồi Next, các field đã hợp lệ vẫn được giữ.
3. Viết `Action` dùng `RequestContext.getFlowScope()` để đọc draft, kiểm tra điều kiện và trả event `valid`/`invalid`.
4. Tạo subflow chọn giờ, truyền vào `serviceCode`, xuất khung giờ đã chọn về flow cha bằng output và cập nhật draft.
5. Giải thích tại sao `BookingDraft` tồn tại trong flowScope nhưng chưa chắc đã được lưu trong database.
6. Viết test cho hai execution độc lập trong một HTTP session, đảm bảo dữ liệu không tự chia sẻ.
7. Gửi lại event xác nhận và xác minh service không tạo hai lịch hẹn.
8. Mô phỏng session timeout và kiểm tra cách khôi phục từ một draft đã lưu bền vững (nếu có).

Kết quả đạt yêu cầu khi người học chỉ ra được **một giá trị thuộc flow session nào, còn sống qua state nào, được binding/validation ở đâu, truyền qua subflow ra sao và khi nào cần lưu bền vững**. `flowScope` đơn giản hóa việc quản lý dữ liệu trong một flow nhiều bước, nhưng vẫn cần phân biệt nó với HTTP session, kiểm soát quyền, giới hạn kích thước và có phương án phục hồi khi execution kết thúc.
