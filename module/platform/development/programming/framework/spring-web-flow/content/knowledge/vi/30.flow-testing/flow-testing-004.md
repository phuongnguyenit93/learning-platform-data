# Đăng ký service giả bằng MockFlowBuilderContext khi kiểm thử Spring Web Flow

Trong một flow đăng ký tài khoản, đặt hàng hoặc duyệt hồ sơ, logic điều hướng không chỉ phụ thuộc vào event người dùng gửi. Một `decision-state` có thể gọi `eligibilityService.isEligible()`, `action-state` có thể gọi `orderService.save(...)`, hoặc action khởi tạo flow có thể lấy bản nháp từ database. Khi kiểm thử flow, nếu phải khởi động cả database, hệ thống email và HTTP server chỉ để xác minh một transition, bộ test sẽ chậm, khó tái lập và khó tạo những kết quả hiếm như từ chối nghiệp vụ.

**Spring Web Flow (SWF)** cung cấp `MockFlowBuilderContext` để hỗ trợ việc **dựng định nghĩa flow trong kiểm thử**. Thông qua context này, test có thể đăng ký các bean/service giả mà expression trong flow XML tham chiếu. Ta chủ động điều khiển kết quả service, kích hoạt event rồi kiểm tra state hoặc outcome của flow mà không cần chạy toàn bộ Spring MVC.

Bài học thuộc chương **Kiểm thử flow** của module `SPRING_WEB_FLOW`. Trọng tâm là dùng `MockFlowBuilderContext.registerBean(...)` trong hook `configureFlowBuilderContext(...)`, phân biệt service giả với context giả, viết ví dụ kiểm thử XML có thể mở rộng, thiết kế test cho thành công/thất bại/hủy/thử lại, và xác định giới hạn của loại test này đối với form binding, validation, session, Spring Security và HTTP integration.

## 1. MockFlowBuilderContext giải quyết vấn đề gì?

Một flow XML có thể tham chiếu Spring bean bằng expression:

~~~xml
<decision-state id="checkEligibility">
    <if test="eligibilityService.isEligible()"
        then="approved"
        else="rejected" />
</decision-state>
~~~

Ở ứng dụng thật, `eligibilityService` có thể gọi database hoặc API khác. Trong **flow execution test**, ta không muốn lời gọi này đi ra hệ thống thật. Thay vào đó, đăng ký một object giả có cùng tên bean và phương thức cần thiết:

~~~java
@Override
protected void configureFlowBuilderContext(
        MockFlowBuilderContext builderContext) {
    builderContext.registerBean("eligibilityService", fakeEligibilityService);
}
~~~

Khi flow definition được xây dựng, builder có thể resolve bean `eligibilityService` từ test context. Khi test chạy event đi vào `checkEligibility`, expression sẽ gọi fake service. Giá trị `true` hoặc `false` do fake trả về quyết định flow đi theo nhánh nào.

Cần tách ba trách nhiệm:

| Đối tượng | Vai trò | Không làm thay |
|---|---|---|
| **`MockFlowBuilderContext`** | Cung cấp bean/điều kiện xây dựng flow definition trong test | Không tự sinh response giả cho mọi service |
| **Fake/stub/mock service** | Trả kết quả do test điều khiển; có thể ghi lại số lần gọi | Không tự dựng flow XML hoặc chọn transition |
| **`AbstractXmlFlowExecutionTests`** | Nạp flow definition, khởi chạy execution, gửi event và assert state/outcome | Không tự kiểm tra ánh xạ URL, filter bảo mật hay JSP thực tế |

**Điểm mấu chốt:** `MockFlowBuilderContext` không phải một đối tượng dùng để thay thế `FlowExecutor` trong production và cũng không tự động biến mọi dependency của flow thành mock. Chính bài test phải tạo object giả, đăng ký nó **trước khi flow definition được dùng**, và xác minh kết quả.

### 1.1. Đường đi của một bài kiểm thử

~~~mermaid
flowchart TD
    T["Flow execution test"] --> R["getResource: chọn flow XML"]
    R --> C["configureFlowBuilderContext"]
    C --> B["registerBean: eligibilityService = fake"]
    B --> D["Build flow definition"]
    D --> S["startFlow: review"]
    S --> E["signalEvent: submit"]
    E --> F["decision-state gọi fake.isEligible"]
    F -->|"true"| A["end-state: approved"]
    F -->|"false"| N["view-state: rejected"]
    A --> K["Assert outcome và số lần gọi"]
    N --> K
~~~

Sơ đồ biểu diễn ý tưởng kiểm thử, không mô tả mọi lớp nội bộ của SWF. Thứ tự hook và lifecycle cụ thể phụ thuộc phiên bản test support, nhưng dependency phải sẵn sàng khi builder cần resolve chúng.

## 2. Thiết kế một flow nhỏ để kiểm thử

Giả sử người dùng ở trang `review` và nhấn nút `submit`. Flow hỏi service xem người dùng có đủ điều kiện hay không:

- **Đủ điều kiện:** flow kết thúc với outcome `approved`.
- **Không đủ điều kiện:** hiển thị trang `rejected`, có thể quay lại để thử sau hoặc hủy.
- **Hủy:** kết thúc với outcome `cancelled` mà không gọi service kiểm tra điều kiện.

File minh họa nằm ở:

~~~text
src/
  test/
    java/com/example/flow/FakeEligibilityService.java
    java/com/example/flow/EligibilityFlowExecutionTests.java
    resources/flows/eligibility/eligibility-flow.xml
~~~

Đây là cấu trúc **ví dụ**, không yêu cầu thay đổi cấu trúc module hiện tại. Bài kiểm thử sẽ trỏ chính xác tới tài nguyên XML trong thư mục test.

### 2.1. Định nghĩa XML tối giản

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <view-state id="review" view="review">
        <transition on="submit" to="checkEligibility"
                    bind="false" validate="false" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <decision-state id="checkEligibility">
        <if test="eligibilityService.isEligible()"
            then="approved"
            else="rejected" />
    </decision-state>

    <view-state id="rejected" view="rejected">
        <transition on="retry" to="review"
                    bind="false" validate="false" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <end-state id="approved" />
    <end-state id="cancelled" />
</flow>
~~~

Vì mục tiêu ở đây là **kiểm thử dependency và điều hướng**, flow không có form model và không thực hiện binding/validation. Vì vậy, ta chủ động đặt `bind="false" validate="false"` cho các event. Những phần form/validation phải được kiểm thử riêng ở flow có model thực tế.

`decision-state` sẽ tự đánh giá điều kiện khi được đi vào; test **không gửi event** `true` hoặc `false`. Thuộc tính `then` và `else` trỏ tới state ID, không phải URL hay tên Bean.

### 2.2. Quy tắc nghiệp vụ được kiểm thử

| State hiện tại | Sự kiện / kết quả | State hoặc outcome kế tiếp | Service được gọi? |
|---|---|---|---|
| `review` | `submit`, fake trả `true` | `approved` (flow kết thúc) | Có, một lần |
| `review` | `submit`, fake trả `false` | `rejected` | Có, một lần |
| `review` | `cancel` | `cancelled` (flow kết thúc) | Không |
| `rejected` | `retry` | `review` | Không gọi lại ở bước retry |
| `rejected` | `cancel` | `cancelled` | Không gọi thêm |
| `review` sau retry | `submit` lần hai | Theo giá trị fake ở lần kiểm tra thứ hai | Có thêm một lần |

Bảng này là hợp đồng hành vi để viết test. Nó không dùng HTTP status `200` hoặc nội dung HTML để suy ra flow đi đúng; test cần kiểm tra **state hiện tại hoặc end-state outcome**.

## 3. Viết service giả có thể điều khiển được

Fake service không nhất thiết cần Mockito. Một lớp Java nhỏ thường đủ cho quyết định Boolean:

~~~java
package com.example.flow;

public class FakeEligibilityService {

    private boolean eligible;
    private int invocationCount;

    public void setEligible(boolean eligible) {
        this.eligible = eligible;
    }

    public boolean isEligible() {
        invocationCount++;
        return eligible;
    }

    public int getInvocationCount() {
        return invocationCount;
    }

    public void reset() {
        eligible = false;
        invocationCount = 0;
    }
}
~~~

Fake cung cấp hai khả năng:

1. **Điều khiển kết quả:** gọi `setEligible(true/false)` để ép flow đi vào nhánh mong muốn.
2. **Quan sát tương tác:** kiểm tra `getInvocationCount()` để xác minh flow có gọi service đúng số lần.

Không cần đặt fake vào `flowScope`. Đây là dependency mà định nghĩa flow resolve từ builder context; còn `flowScope` là nơi lưu **dữ liệu của một flow session đang chạy**, ví dụ bản nháp đơn hàng. Hai khái niệm không thể dùng thay thế cho nhau.

### 3.1. Fake, stub và mock khác nhau thế nào?

Các thuật ngữ thường được dùng hơi chồng lấn:

| Kiểu test double | Ví dụ | Khi phù hợp |
|---|---|---|
| **Stub** | `isEligible()` luôn trả `true` | Chỉ cần kiểm tra nhánh đơn giản |
| **Fake** | Có biến `eligible`, bộ đếm và một ít logic nội bộ | Muốn thử nhiều kịch bản trong cùng lớp test |
| **Mock theo thư viện** | Mockito `when(...).thenReturn(...)` và `verify(...)` | Cần thiết lập tương tác chi tiết và assertions trên lời gọi |

`MockFlowBuilderContext` là **test context**, không đồng nghĩa rằng bean đưa vào phải được tạo bởi Mockito. Nó có thể nhận một fake thủ công, mock Mockito, implementation in-memory hoặc stub đơn giản miễn object có API mà expression của flow cần.

## 4. Đăng ký fake bằng configureFlowBuilderContext

Với test support truyền thống của Spring Web Flow 2.x, một bài kiểm thử XML thường kế thừa `AbstractXmlFlowExecutionTests`. Hai hook quan trọng:

- `getResource(FlowDefinitionResourceFactory)`: chỉ định file XML cần dựng.
- `configureFlowBuilderContext(MockFlowBuilderContext)`: đăng ký các bean mà XML sẽ tham chiếu trong quá trình xây dựng/chạy flow.

Ví dụ Java dùng **phong cách test method `test...`** tương thích test support dựa trên JUnit 3 của một số bản SWF 2.x. Trong dự án dùng JUnit 4/5, cần chọn runner/adapter hoặc chuyển cấu trúc test theo API đang dùng; không chỉ gắn `@Test` rồi giả định các lifecycle hook luôn được gọi như nhau.

~~~java
package com.example.flow;

import org.springframework.webflow.engine.builder.FlowDefinitionResource;
import org.springframework.webflow.engine.builder.FlowDefinitionResourceFactory;
import org.springframework.webflow.test.MockFlowBuilderContext;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;

public class EligibilityFlowExecutionTests
        extends AbstractXmlFlowExecutionTests {

    private final FakeEligibilityService fakeEligibilityService =
        new FakeEligibilityService();

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createFileResource(
            "src/test/resources/flows/eligibility/eligibility-flow.xml");
    }

    @Override
    protected void configureFlowBuilderContext(
            MockFlowBuilderContext builderContext) {
        builderContext.registerBean(
            "eligibilityService", fakeEligibilityService);
    }

    public void testEligibleApplicantIsApproved() {
        fakeEligibilityService.setEligible(true);

        startFlow();
        assertCurrentStateEquals("review");

        signalEvent("submit");

        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("approved");
        assertEquals(1, fakeEligibilityService.getInvocationCount());
    }

    public void testIneligibleApplicantSeesRejected() {
        fakeEligibilityService.setEligible(false);

        startFlow();
        signalEvent("submit");

        assertCurrentStateEquals("rejected");
        assertEquals(1, fakeEligibilityService.getInvocationCount());
    }

    public void testCancelNeverInvokesService() {
        startFlow();
        signalEvent("cancel");

        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("cancelled");
        assertEquals(0, fakeEligibilityService.getInvocationCount());
    }

    public void testRetryEvaluatesAgain() {
        fakeEligibilityService.setEligible(false);
        startFlow();

        signalEvent("submit");
        assertCurrentStateEquals("rejected");

        fakeEligibilityService.setEligible(true);
        signalEvent("retry");
        assertCurrentStateEquals("review");

        signalEvent("submit");
        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("approved");
        assertEquals(2, fakeEligibilityService.getInvocationCount());
    }
}
~~~

**Cách đọc đoạn test:**

1. Trường `fakeEligibilityService` được tạo bởi test, không phải bean production.
2. `getResource(...)` chọn flow XML cần kiểm tra; đường dẫn phải tồn tại tương ứng với cách runner chạy. Nếu ứng dụng chọn classpath resource, điều chỉnh factory method và vị trí tài nguyên cho đúng API phiên bản đang dùng.
3. `configureFlowBuilderContext(...)` dùng `registerBean("eligibilityService", fakeEligibilityService)`. Chuỗi tên này **phải khớp chính xác** với `eligibilityService` trong XML.
4. `startFlow()` khởi tạo execution của flow đã dựng; state đầu tiên là `review`.
5. `signalEvent("submit")` mô phỏng người dùng phát event tại view, đi tới decision-state.
6. Assertion kiểm tra state/outcome và số lần fake được gọi, qua đó phát hiện cả lỗi điều hướng lẫn lỗi không gọi dependency.

Các lớp và import ở ví dụ theo dòng test support SWF 2.x. Với bản Spring Web Flow khác, hãy đối chiếu package, chữ ký hook, resource factory và cách tích hợp JUnit trong dependency đang dùng; đây là **mẫu minh họa kỹ thuật**, không phải lời bảo đảm có thể compile với mọi thế hệ Spring Framework/Jakarta.

### 4.1. Vì sao phải đăng ký trước khi startFlow?

Flow definition chứa expression tham chiếu bean name. Nếu `startFlow()` hoặc bước build đã chạy rồi mới thay đổi object trong builder context, thay đổi đó có thể không được dùng để resolve dependency theo cách bạn mong đợi.

Vì vậy đặt việc đăng ký trong hook `configureFlowBuilderContext(...)`, không đặt ở cuối test sau `startFlow()`. Muốn thay đổi **kết quả** trong cùng test, hãy thay field của fake đã đăng ký; muốn thay đổi **bean implementation**, cần dựng lại flow/context theo cơ chế test support đang dùng.

### 4.2. Không dùng cùng một fake bị rò trạng thái giữa các test

Fake có `invocationCount` nên nếu nhiều test dùng chung instance mà không reset, assert về số lần gọi sẽ trở nên phụ thuộc thứ tự chạy test.

Các cách quản lý:

- Mỗi test tạo **một instance test fixture mới**, như lifecycle kiểu JUnit 3 thông thường.
- Nếu dùng JUnit 5 với `@TestInstance(PER_CLASS)` hay custom runner tái sử dụng object, gọi `reset()` trong hook phù hợp trước mỗi test.
- Không đăng ký static singleton fake cho nhiều test chạy song song trừ khi đã xử lý race condition và cô lập dữ liệu.
- Với Mockito, có thể tạo mock mới trong mỗi test hoặc reset theo chính sách rõ ràng, tránh tái sử dụng stub ngoài chủ đích.

Ở ví dụ trên, các test dùng state riêng theo instance. Nếu dự án thay test runner, phải kiểm tra lại assumption này.

## 5. Kiểm thử nhánh, kết thúc và retry

### 5.1. Nhánh then: service trả true

Đường mong đợi:

~~~text
review --(submit)--> checkEligibility
                       isEligible() == true
                           |
                           v
                       approved [end-state]
~~~

Test `testEligibleApplicantIsApproved` kiểm tra ba điều:

- Fake trả `true` nên `decision-state` chọn `then="approved"`.
- Flow thực sự **kết thúc**, không chỉ hiển thị một view cùng tên.
- Service được gọi một lần khi đi vào decision-state.

Chỉ assert `assertFlowExecutionEnded()` chưa đủ: một bug có thể kết thúc nhầm ở `cancelled`. Vì vậy nên assert thêm **outcome ID**.

### 5.2. Nhánh else: service trả false

Đường mong đợi:

~~~text
review --(submit)--> checkEligibility
                       isEligible() == false
                           |
                           v
                       rejected [view-state]
~~~

Ở đây flow **chưa kết thúc** vì `rejected` là `view-state`; người dùng có thể phát `retry` hoặc `cancel`. Vì vậy test xác minh `assertCurrentStateEquals("rejected")`, không khẳng định execution đã end.

### 5.3. Hủy không được gọi service

Một lỗi thường gặp khi bố trí flow là đặt action kiểm tra trong một hook chạy ngay lúc vào view; khi đó cả thao tác hủy cũng vô tình gọi service. Với XML mẫu, event `cancel` đi thẳng tới `end-state cancelled`, nên fake có bộ đếm `0`.

Test nên kiểm tra **điều không được phép xảy ra**, không chỉ điều được phép: `cancel` không kích hoạt kiểm tra điều kiện, không tạo giao dịch, không gửi email và không thực hiện ghi dữ liệu.

### 5.4. Thử lại có gọi service lần thứ hai không?

Trong XML, `retry` chỉ chuyển về `review`. Lần submit thứ hai mới đi vào `checkEligibility` một lần nữa. Test có thể đổi fake từ `false` sang `true` giữa hai lần submit để chứng minh cả đường retry và lần đánh giá kế tiếp.

Đây là ví dụ đơn giản về việc kiểm thử **flow qua nhiều event**, không chỉ một transition độc lập.

## 6. Đăng ký nhiều service giả

Flow thực tế có thể dùng nhiều dependency. Ví dụ:

~~~xml
<on-start>
    <evaluate expression="draftService.load()" result="flowScope.draft" />
</on-start>

<action-state id="submitOrder">
    <evaluate expression="orderAction.execute(flowRequestContext)" />
    <transition on="success" to="completed" />
    <transition on="invalid" to="review" />
</action-state>
~~~

Khi đó test có thể đăng ký nhiều bean:

~~~java
@Override
protected void configureFlowBuilderContext(
        MockFlowBuilderContext builderContext) {
    builderContext.registerBean("draftService", fakeDraftService);
    builderContext.registerBean("orderAction", fakeOrderAction);
}
~~~

**Lưu ý:** đây chỉ là đoạn cấu hình phụ thuộc của một **flow khác**, không chèn thêm vào flow `eligibility` ở phần trước. Các object `fakeDraftService` và `fakeOrderAction` phải được khởi tạo trong fixture test với phương thức tương ứng. `orderAction` có thể là action thật dùng fake repository/service hoặc bản fake action trả Event theo hợp đồng.

Nếu muốn test không bỏ qua phần logic quan trọng trong Java action, thay vì mock luôn `orderAction`, nên để **action thật** chạy với **service fake** được inject qua constructor; nhờ vậy test xác minh được cả xử lý outcome của action và transition của flow. Chỉ fake dependency bên ngoài như database/email/API là cách kiểm thử thường có giá trị hơn.

### 6.1. Ví dụ action thật gọi service fake

~~~java
public final class SubmitOrderAction implements Action {

    private final OrderService orderService;

    public SubmitOrderAction(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public Event execute(RequestContext context) {
        OrderDraft draft =
            (OrderDraft) context.getFlowScope().get("draft");

        SaveResult result = orderService.save(draft);

        if (result == SaveResult.SAVED) {
            return new Event(this, "success");
        }
        return new Event(this, "invalid");
    }
}
~~~

Các kiểu `OrderService`, `OrderDraft` và `SaveResult` do ứng dụng định nghĩa; cần import `Action`, `Event` và `RequestContext` từ SWF. Service fake của test có thể trả `SAVED` hoặc `INVALID` để exercise action thật. Một exception từ service **không tự biến thành event `invalid`**; nếu cần nhánh lỗi thực thi, action/service phải có thiết kế xử lý exception tường minh.

## 7. Mockito là tùy chọn, không phải yêu cầu

Nếu dự án đã dùng Mockito, test có thể tạo mock interface service và vẫn đăng ký theo cùng cơ chế:

~~~java
private final EligibilityService eligibilityService =
    Mockito.mock(EligibilityService.class);

@Override
protected void configureFlowBuilderContext(
        MockFlowBuilderContext builderContext) {
    builderContext.registerBean("eligibilityService", eligibilityService);
}

public void testApprovedWithMockito() {
    Mockito.when(eligibilityService.isEligible()).thenReturn(true);

    startFlow();
    signalEvent("submit");

    assertFlowExecutionOutcomeEquals("approved");
    Mockito.verify(eligibilityService, Mockito.times(1)).isEligible();
}
~~~

`EligibilityService` ở đây là interface do dự án khai báo với method `boolean isEligible()`; cần dependency và import Mockito phù hợp. Không cần `@MockBean` của Spring Boot nếu flow test không khởi chạy Boot context. `registerBean(...)` nhận **instance object** đã được tạo bởi Mockito và cung cấp nó cho quá trình build/execute flow.

**Khi nào chọn cách nào?** Fake thủ công hữu ích khi muốn mô phỏng thay đổi trạng thái giữa các event (`retry`), còn Mockito tiện khi muốn `verify` method, tham số, số lần gọi hoặc cấu hình chuỗi kết quả. Không có lựa chọn nào mặc nhiên tốt hơn trong mọi tình huống.

## 8. Những giới hạn của MockFlowBuilderContext

Một test chạy xanh với fake service là minh chứng cho **logic điều hướng ở mức flow** trong điều kiện test đã thiết lập. Nó không chứng minh toàn bộ ứng dụng web hoạt động đúng.

| Cần kiểm thử | MockFlowBuilderContext có hỗ trợ đủ một mình? | Loại test bổ sung |
|---|---|---|
| Bean name được flow XML resolve | Có, nếu registerBean đúng | XML flow test |
| `then`/`else` theo kết quả fake | Có | Flow execution test |
| Event `retry`, `cancel` và end-state | Có | Flow execution test |
| Java action kết hợp fake service | Có khi test đăng ký đúng action | Flow test + unit test action |
| Chọn `FlowHandlerMapping` cho URL thật | Không | Spring MVC integration test |
| `DispatcherServlet`, `FlowHandlerAdapter` | Không | Web/MVC integration test |
| HTML/JSP/Thymeleaf render đúng | Không | View/integration test |
| CSRF và Spring Security filter chain | Không | Spring Security Test / MockMvc |
| Form binding và validation | Chỉ trong phạm vi đã cấu hình và cung cấp model/validator | Flow test + binding/validation integration |
| JPA transaction, optimistic locking, rollback | Không | Service/repository integration test |
| Session timeout và repository snapshot | Không đầy đủ | FlowExecutor/repository + HTTP integration |
| Gọi API hay gửi email thật | Không (đã thay bằng fake) | Contract/integration test có chủ đích |

Với form wizard, test flow có thể cần mock `RequestContext`/`ExternalContext`, input attributes và validator tương ứng để mô phỏng binding. Không nên vì đã sử dụng `MockFlowBuilderContext` mà suy ra các phụ thuộc của runtime đều tự động được mock hoặc mọi lỗi trong controller đều đã được kiểm tra.

### 8.1. Khác gì ApplicationContext của Spring?

- **ApplicationContext thật** quản lý bean production, scopes, post-processors, injection, transaction proxies và các cấu hình runtime khác.
- **MockFlowBuilderContext** là context hỗ trợ cho **flow builder khi kiểm thử**, cho phép cung cấp bean và các thành phần flow cần thiết theo cách gọn nhẹ.

Nếu flow dùng AOP proxy, method security hoặc `@Transactional`, một fake được tạo bằng `new` rồi `registerBean` **không nhận những interceptor production** đó một cách tự động. Test cần để việc kiểm tra transaction/quyền thực sự diễn ra ở tầng integration với context tương ứng.

### 8.2. Khác gì MockMvc?

`MockMvc` mô phỏng request qua Spring MVC, có thể kiểm tra handler mapping, filter chain khi cấu hình, kết quả HTTP và view. `AbstractXmlFlowExecutionTests` tập trung vào **flow execution model**: khởi chạy flow, phát event, kiểm tra state và outcome.

Hai loại test bổ sung cho nhau: một flow unit test cho quyết định nghiệp vụ, một web integration test cho cách trình duyệt khởi chạy/tiếp tục flow qua URL execution và session.

## 9. Các lỗi thường gặp khi registerBean

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Lỗi không tìm thấy `eligibilityService` | Bean name trong XML khác `registerBean` | So khớp tên và phân biệt chữ hoa/thường |
| Lỗi expression không gọi được method | Fake thiếu method public/chữ ký không tương thích | Đối chiếu `isEligible()` và kiểu trả về |
| Flow không đi vào nhánh mong đợi | Fake trả giá trị sai hoặc test không kích hoạt đúng event | Assert state đầu, outcome và số lần gọi |
| Test đi qua handler không mong muốn | Dựng nhầm flow XML | Kiểm tra `getResource(...)` và path fixture |
| Test có lúc pass lúc fail | Fake bị chia sẻ trạng thái giữa các test | Tạo fixture mới hoặc reset trước mỗi test |
| Test đang sửa fake sau khi flow đã build | Cố thay bean thay vì thay trạng thái bean | Đăng ký trước; đổi field fake hoặc dựng lại flow |
| Test hủy vẫn gọi service | Service được gọi ở hook khởi tạo/view, không ở decision-state | Kiểm tra vị trí action và đường transition |
| Đã test nhánh `approved` nhưng quên `rejected` | Thiếu branch coverage | Dùng fake trả cả true và false |
| Exception bị coi nhầm là `else` | Fake/service ném lỗi trong `test` | Kiểm tra error handling; `else` chỉ ứng với false |
| XML flow test xanh nhưng POST thật lỗi | Chưa kiểm thử execution URL, CSRF, view/validator | Bổ sung MVC + Security integration test |
| Service có state từ ca test trước | Test instance/static fake bị dùng chung | Cô lập fixture, reset và kiểm tra parallel execution |

## 10. Thiết kế test cho exception và kết quả bất thường

Một service có thể không trả đúng/sai mà ném exception khi không truy cập được database. Điều này **khác** với quyết định nghiệp vụ “không đủ điều kiện”.

Có thể mở rộng fake:

~~~java
public boolean isEligible() {
    invocationCount++;

    if (simulateOutage) {
        throw new IllegalStateException("Service tạm thời không khả dụng");
    }

    return eligible;
}
~~~

Biến `simulateOutage` phải được khai báo và cấu hình trong fake khi áp dụng đoạn mở rộng này. Khi exception ném ra trong `decision-state`, SWF không mặc nhiên đi theo `else="rejected"`. Test lỗi cần assert cơ chế exception handling phù hợp (nếu flow định nghĩa đường phục hồi) hoặc xác minh lỗi được phản ánh như một lỗi thực thi.

Đối với nghiệp vụ quan trọng, nên thiết kế outcome có nghĩa như `APPROVED`, `REJECTED`, `PENDING`, `TEMPORARY_ERROR` thay vì gộp mọi trạng thái vào một Boolean. Có thể dùng action-state chuyển response service thành các event rõ ràng, rồi dùng fake để lần lượt kích hoạt từng outcome.

### 10.1. Kiểm thử cả việc không ghi dữ liệu

Nếu action đặt hàng gọi fake repository/service, ngoài assert outcome `completed` hãy kiểm tra:

- Với event `cancel`, số lần gọi `save` bằng **0**.
- Với outcome `invalid`, không có bản ghi được tạo.
- Với outcome `success`, action gọi service đúng một lần.
- Với retry, không ghi dữ liệu hai lần nếu đã có một thao tác thành công trước đó; service phải có kiểm tra trùng/idempotency nếu nghiệp vụ yêu cầu.
- Với session hết hạn hoặc execution key sai, tuyệt đối không tự retry một POST giao dịch có tác động ghi.

Các assertions này đặc biệt quan trọng bởi test điều hướng **không thể thay thế** kiểm tra tác động nghiệp vụ trong service.

## 11. Bài tập thực hành: thay service thật bằng fake

Thiết kế flow xét duyệt đơn xin học bổng:

1. `view-state submitApplication` phát event `next`.
2. `decision-state eligibilityCheck` gọi bean `scholarshipPolicyService.isEligible()`.
3. Khi `true`, chuyển `reviewOffer`; khi `false`, chuyển `notEligible`.
4. Từ `reviewOffer`, người dùng có thể `accept` để kết thúc `accepted` hoặc `cancel` để kết thúc `cancelled`.
5. Từ `notEligible`, người dùng có thể `back` để quay lại hoặc `cancel`.

Yêu cầu viết test:

- Đặt XML ở test resources và tạo lớp kế thừa `AbstractXmlFlowExecutionTests`.
- Trong `configureFlowBuilderContext(MockFlowBuilderContext)`, đăng ký fake với bean name `scholarshipPolicyService`.
- Cho fake trả `true` và kiểm tra state `reviewOffer`.
- Cho fake trả `false` và kiểm tra state `notEligible`.
- Gửi event `cancel` từ state đầu và kiểm tra fake chưa được gọi.
- Sau một lần false, thay kết quả thành true, phát `back` rồi `next` và kiểm tra lần gọi thứ hai.
- Cố ý đăng ký sai bean name trong một test riêng và quan sát lỗi resolve dependency.
- Bổ sung một service giả ném exception và phân biệt lỗi này với kết quả Boolean `false`.

**Tiêu chí hoàn thành:** người học có thể nói rõ bean giả được tạo ở đâu, được đăng ký vào `MockFlowBuilderContext` lúc nào, flow XML tham chiếu bean bằng tên gì, một event khiến service được gọi như thế nào, state/outcome nào phải xuất hiện, và giới hạn của test trong việc chứng minh hoạt động của HTTP/Spring MVC/Spring Security/transaction.

## 12. Checklist cho một flow test đáng tin cậy

- [ ] Flow XML được nạp từ đúng tài nguyên fixture.
- [ ] Bean name dùng trong `registerBean(...)` khớp expression XML.
- [ ] Fake/mock có phương thức public và kiểu kết quả phù hợp.
- [ ] Đăng ký dependency trước khi flow được xây dựng/thực thi.
- [ ] Mỗi test kiểm soát trạng thái ban đầu của fake.
- [ ] Assert **state đầu** trước khi phát event.
- [ ] Assert **state hoặc outcome đúng**, không chỉ “không có exception”.
- [ ] Có test cho nhánh `true`, `false`, `cancel`, `retry`.
- [ ] Có assertion về số lần gọi hoặc tác động của service.
- [ ] Kiểm thử exception tách khỏi kết quả nghiệp vụ âm tính.
- [ ] Không dùng kết quả unit test này để tuyên bố Spring MVC, session, CSRF hoặc DB đã được kiểm thử.
- [ ] Có lớp integration test bổ sung cho những ranh giới ngoài phạm vi builder context.

**Kết luận:** `MockFlowBuilderContext` là điểm nối giữa định nghĩa flow và các dependency giả trong bài kiểm thử. Bằng cách đăng ký đúng bean name và chủ động điều khiển kết quả service, ta có thể xác minh event, transition, decision-state, end-state và đường thử lại một cách nhanh, có thể lặp lại. Hãy giữ ranh giới rõ ràng: fake phục vụ kiểm thử flow; tính đúng đắn của giao dịch, bảo mật và tích hợp web phải được xác nhận ở những tầng kiểm thử thích hợp.
