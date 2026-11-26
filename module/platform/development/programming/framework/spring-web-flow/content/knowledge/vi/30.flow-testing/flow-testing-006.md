# Khởi chạy flow và kiểm tra state đầu tiên trong Spring Web Flow

Một flow đặt hàng có thể gồm các bước nhập thông tin, xem lại và xác nhận. Trước khi kiểm thử event `next` hay `confirm`, cần biết flow có **khởi chạy đúng hay không**: input ban đầu có được nhận, action `on-start` có chạy, service phụ thuộc có được gọi, và execution có dừng tại đúng state đầu tiên để chờ người dùng không.

Spring Web Flow cung cấp bộ test support cho việc kiểm thử trực tiếp **flow execution** mà không cần dựng toàn bộ Servlet container hoặc mở browser. Với flow XML, lớp `AbstractXmlFlowExecutionTests` giúp nạp flow definition, đăng ký service giả, khởi chạy execution bằng input và `MockExternalContext`, rồi kiểm tra state hiện tại và dữ liệu trong scope.

Bài học thuộc chương **Kiểm thử flow** của module `SPRING_WEB_FLOW`. Nội dung tập trung vào **khởi chạy flow và kiểm tra state đầu tiên**; đồng thời phân biệt kiểm thử flow engine với kiểm thử tích hợp HTTP/Spring MVC để biết chính xác mỗi loại test chứng minh điều gì.

Sau bài học, bạn có thể:

- Giải thích điều cần xác minh trong lần khởi chạy đầu tiên của flow.
- Dùng `AbstractXmlFlowExecutionTests` để kiểm thử flow định nghĩa bằng XML.
- Chỉ định flow resource bằng `FlowDefinitionResourceFactory`.
- Cấp input ban đầu cho `startFlow(input, context)`.
- Dùng `MockExternalContext` để cung cấp principal, locale và dữ liệu môi trường test.
- Đăng ký stub/mock service bằng `configureFlowBuilderContext`.
- Kiểm tra execution đang active, state hiện tại và thuộc tính được tạo trong `on-start`.
- Kiểm thử input bắt buộc, state khởi đầu không mong đợi và lỗi khởi tạo.
- Phân biệt flow execution test với MVC integration test và browser end-to-end test.

## 1. Vì sao cần kiểm tra ngay lúc khởi chạy?

Flow có thể thất bại trước khi người dùng nhìn thấy màn hình đầu tiên. Một số nguyên nhân thường gặp:

- Flow input bị thiếu, sai tên hoặc không chuyển đổi được kiểu.
- Flow definition không được nạp hoặc cấu hình state ban đầu không đúng.
- Bean mà `on-start` gọi chưa được đăng ký trong test context.
- Action khởi tạo trả dữ liệu sai hoặc ném exception.
- Flow đi vào một state khác dự kiến do state đầu tiên là action/decision state và tự chuyển tiếp.
- Flow kết thúc ngay trong lúc khởi chạy thay vì dừng ở view-state cần hiển thị.

Một test startup tốt trả lời ít nhất bốn câu hỏi:

1. **Flow có khởi chạy thành công không?**
2. **Execution có còn active không?**
3. **Execution đang dừng ở state nào?**
4. **Input và dữ liệu khởi tạo có nằm đúng scope, đúng kiểu không?**

Ví dụ, nếu flow đăng ký cần `applicationId` để tạo bản nháp, chỉ kiểm tra `assertCurrentStateEquals("enterDetails")` chưa đủ. Test cũng nên xác nhận `applicationId` đã được đưa vào flow và service tạo bản nháp đã được gọi đúng.

## 2. Phân biệt flow definition, flow execution và state đầu tiên

Trước khi viết test, cần phân biệt ba đối tượng:

| Khái niệm | Ý nghĩa | Trong kiểm thử startup |
| --- | --- | --- |
| **Flow definition** | Bản thiết kế gồm state, transition, action, input/output | Được nạp từ XML resource |
| **FlowExecution** | Một lượt chạy cụ thể của flow definition | Được tạo khi gọi `startFlow` |
| **Current state** | State đang hoạt động trong execution | Được kiểm tra bằng `assertCurrentStateEquals` |

Một flow definition có thể được khởi chạy nhiều lần. Mỗi lần test gọi `startFlow` là một lượt execution mới theo test harness. Assertion state kiểm tra **state hiện tại của lượt chạy**, không kiểm tra tên file hoặc thứ tự dòng XML.

### State đầu tiên trong XML và state đầu tiên execution dừng lại

State được khai báo đầu tiên trong flow là điểm bắt đầu của flow. Tuy nhiên, không phải lúc nào execution cũng dừng ngay tại phần tử đầu tiên đó:

- Nếu state đầu tiên là `view-state`, execution thường dừng ở đó để chờ event và render view.
- Nếu state đầu tiên là `action-state`, action có thể chạy rồi transition sang state tiếp theo ngay trong cùng lần khởi chạy.
- Nếu state đầu tiên là `decision-state`, điều kiện có thể chọn nhánh và flow tiếp tục đến state khác.
- Nếu đường đi ban đầu đến `end-state`, execution có thể kết thúc ngay.

Vì vậy, bài kiểm thử nên xác nhận **state đầu tiên mà execution thực sự dừng tại đó sau khi xử lý startup**, thường là view-state đầu tiên chờ tương tác.

## 3. Flow XML dùng trong ví dụ

Giả sử flow `registration` nhận input `applicationId`, tạo bản nháp khi bắt đầu và hiển thị màn hình `enterDetails`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="applicationId" type="long" required="true" />

    <on-start>
        <evaluate expression="registrationService.createDraft(applicationId)"
                  result="flowScope.draft" />
    </on-start>

    <view-state id="enterDetails"
                view="registration/enterDetails">
        <transition on="next" to="review" />
    </view-state>

    <view-state id="review" view="registration/review">
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="completed" />
</flow>
```

Các thành phần có ý nghĩa:

| Thành phần | Vai trò trong startup |
| --- | --- |
| `<input name="applicationId" ... />` | Khai báo input bắt buộc của flow và kiểu dữ liệu mong đợi |
| `<on-start>` | Chạy action khởi tạo khi flow bắt đầu |
| `registrationService.createDraft(applicationId)` | Gọi service để tạo bản nháp |
| `result="flowScope.draft"` | Đưa kết quả khởi tạo vào flow scope |
| `view-state id="enterDetails"` | State đầu tiên chờ người dùng nhập thông tin |

`registrationService` là bean của ứng dụng. Trong flow test, ta sẽ đăng ký một **stub** có hành vi xác định để test không phụ thuộc database hoặc dịch vụ bên ngoài.

## 4. Bộ test support của Spring Web Flow

Với flow định nghĩa bằng XML, lớp thường dùng là:

```java
public class RegistrationFlowExecutionTests
        extends AbstractXmlFlowExecutionTests {
}
```

`AbstractXmlFlowExecutionTests` là test base dành cho flow execution test với XML flow definition. Nó kế thừa `AbstractExternalizedFlowExecutionTests` và cuối cùng là `AbstractFlowExecutionTests`.

Các khả năng quan trọng:

| API | Mục đích |
| --- | --- |
| `getResource(FlowDefinitionResourceFactory)` | Chỉ định XML flow cần kiểm thử |
| `configureFlowBuilderContext(MockFlowBuilderContext)` | Đăng ký stub/mock service và các phụ thuộc cần cho flow builder |
| `getModelResources(...)` | Khai báo flow model cha khi flow cần kế thừa definition |
| `startFlow(input, context)` | Khởi chạy execution với input và external context |
| `assertFlowExecutionActive()` | Xác nhận execution đã khởi chạy và chưa kết thúc |
| `assertCurrentStateEquals(stateId)` | Xác nhận state hiện tại |
| `getRequiredFlowAttribute(name)` | Lấy thuộc tính bắt buộc trong flow scope |
| `getFlowScope()` | Truy cập flow scope để kiểm tra dữ liệu |

### Flow test không cần browser

Test harness chạy flow engine với một external context giả. Bạn có thể kiểm tra việc khởi chạy, state, input, scope và hành vi action mà không phải deploy ứng dụng vào Servlet container.

Điều này giúp test nhanh và tập trung vào logic điều phối. Nhưng test harness **không tự kiểm tra**:

- URL mapping của `FlowHandlerMapping`.
- `FlowHandlerAdapter` có nhận request HTTP đúng không.
- Cookie, session thực, CSRF filter và authentication filter.
- View resolver có tìm được JSP/Thymeleaf template không.
- HTML có render đúng trong browser không.

Những phần đó cần Spring MVC integration test hoặc end-to-end test riêng.

## 5. Chỉ định XML flow resource

`AbstractXmlFlowExecutionTests` yêu cầu xác định resource của flow cần test. Có thể dùng classpath resource:

```java
@Override
protected FlowDefinitionResource getResource(
        FlowDefinitionResourceFactory resourceFactory) {
    return resourceFactory.createClassPathResource(
            "registration-flow.xml", getClass());
}
```

Nếu file nằm trong `src/test/resources/flows/registration-flow.xml`, có thể tham chiếu theo classpath tương ứng:

```java
@Override
protected FlowDefinitionResource getResource(
        FlowDefinitionResourceFactory resourceFactory) {
    return resourceFactory.createClassPathResource(
            "flows/registration-flow.xml", getClass());
}
```

Với flow nằm ngoài classpath, có thể dùng file resource:

```java
@Override
protected FlowDefinitionResource getResource(
        FlowDefinitionResourceFactory resourceFactory) {
    return resourceFactory.createFileResource(
            "src/main/webapp/WEB-INF/flows/registration/registration.xml");
}
```

Chọn một cách phù hợp với cấu trúc build. Đường dẫn resource trong test phải trỏ tới **đúng flow definition** mà ứng dụng muốn kiểm thử; không dùng một bản XML test khác có state giống tên nhưng nội dung khác với production.

## 6. Đăng ký stub/mock cho service mà flow gọi

Nếu `on-start` gọi bean bên ngoài như `registrationService`, test cần cung cấp bean đó trong flow builder context:

```java
@Override
protected void configureFlowBuilderContext(
        MockFlowBuilderContext builderContext) {
    builderContext.registerBean(
            "registrationService", registrationService);
}
```

`MockFlowBuilderContext` là service locator dành cho môi trường test. Phương thức `registerBean(name, bean)` đăng ký stub/mock để biểu thức trong flow có thể tìm thấy bean theo tên.

### Stub đơn giản

```java
public class StubRegistrationService {

    private Long lastApplicationId;
    private int createDraftCallCount;

    public ApplicationDraft createDraft(Long applicationId) {
        this.lastApplicationId = applicationId;
        this.createDraftCallCount++;
        return new ApplicationDraft(applicationId);
    }

    public Long getLastApplicationId() {
        return lastApplicationId;
    }

    public int getCreateDraftCallCount() {
        return createDraftCallCount;
    }
}
```

`ApplicationDraft` là model minh họa do ứng dụng định nghĩa. Stub ghi lại input và số lần gọi để test có thể kiểm tra action `on-start` đã chạy với dữ liệu đúng.

Nên dùng stub có hành vi xác định khi chỉ cần kiểm tra flow orchestration. Nếu cần xác minh nhiều tương tác phức tạp, có thể dùng mock framework phù hợp với stack test của dự án. Không cần kết nối database thật chỉ để chứng minh flow đã gọi service khởi tạo.

## 7. Viết bài kiểm thử startup đầu tiên

Kết hợp resource, stub và `MockExternalContext`:

```java
public class RegistrationFlowExecutionTests
        extends AbstractXmlFlowExecutionTests {

    private final StubRegistrationService registrationService =
            new StubRegistrationService();

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createClassPathResource(
                "flows/registration-flow.xml", getClass());
    }

    @Override
    protected void configureFlowBuilderContext(
            MockFlowBuilderContext builderContext) {
        builderContext.registerBean(
                "registrationService", registrationService);
    }

    public void testStartFlowShowsEnterDetails() {
        MutableAttributeMap<Object> input = new LocalAttributeMap<>();
        input.put("applicationId", 42L);

        MockExternalContext context = new MockExternalContext();
        context.setCurrentUser("learner");

        startFlow(input, context);

        assertFlowExecutionActive();
        assertCurrentStateEquals("enterDetails");
        assertEquals(Long.valueOf(42L),
                getRequiredFlowAttribute("applicationId"));
        assertTrue(getRequiredFlowAttribute("draft")
                instanceof ApplicationDraft);
        assertEquals(Long.valueOf(42L),
                registrationService.getLastApplicationId());
        assertEquals(1, registrationService.getCreateDraftCallCount());
    }
}
```

Ví dụ dùng các lớp test support của Spring Web Flow; các import và class domain như `ApplicationDraft` được lược bớt để tập trung vào flow test.

### Đọc từng bước của test

1. `getResource` chỉ ra XML flow mà test sẽ nạp.
2. `configureFlowBuilderContext` đăng ký bean `registrationService` cho biểu thức `on-start`.
3. `LocalAttributeMap` tạo map input, ở đây truyền `applicationId = 42L`.
4. `MockExternalContext` mô phỏng môi trường bên ngoài; `setCurrentUser` cung cấp principal cho flow nếu biểu thức hoặc logic cần `currentUser`.
5. `startFlow(input, context)` tạo và khởi chạy execution.
6. `assertFlowExecutionActive()` xác nhận execution chưa kết thúc.
7. `assertCurrentStateEquals("enterDetails")` xác nhận execution dừng tại state đầu tiên chờ tương tác.
8. Các assertion còn lại chứng minh input được nhận, `on-start` đã tạo draft và service nhận đúng ID.

Test này kiểm tra **cả trạng thái điều phối và dữ liệu khởi tạo**. Nếu chỉ kiểm tra state mà không kiểm tra flow input hoặc action khởi tạo, một số lỗi có thể bị bỏ sót.

## 8. MockExternalContext cung cấp những gì?

`MockExternalContext` là implementation giả của `ExternalContext`. Nó cho phép thiết lập thông tin môi trường mà flow có thể truy cập trong test:

| API | Dùng để |
| --- | --- |
| `setCurrentUser("learner")` | Cung cấp principal hiện tại cho biểu thức `currentUser` hoặc logic flow |
| `setLocale(Locale.forLanguageTag("vi-VN"))` | Cung cấp locale cho conversion/formatting |
| `setEventId("next")` | Thiết lập event ID khi resume flow trong test |
| `setAjaxRequest(true)` | Mô phỏng request AJAX trong trường hợp cần kiểm thử |
| `setSessionMap(...)` | Cung cấp session attribute map cho context |
| `setRequestMap(...)` | Cung cấp request attribute map |
| `setRequestParameterMap(...)` | Cung cấp parameter map cho request |

Ví dụ thiết lập locale:

```java
MockExternalContext context = new MockExternalContext();
context.setCurrentUser("learner");
context.setLocale(Locale.forLanguageTag("vi-VN"));
```

**Giới hạn quan trọng:** `setCurrentUser` chỉ đặt principal trên mock external context. Nó không chạy Spring Security filter chain và không chứng minh authentication/authorization HTTP đã được cấu hình đúng. Tương tự, session map giả không tương đương một phiên HTTP thật qua nhiều request.

## 9. Kiểm tra input và on-start một cách có chủ đích

Startup thường gồm hai nguồn dữ liệu:

- **Input do caller truyền vào:** ví dụ `applicationId`.
- **Dữ liệu do flow khởi tạo:** ví dụ `draft` được tạo từ service trong `on-start`.

Nên kiểm tra riêng hai nhóm:

| Assertion | Điều chứng minh |
| --- | --- |
| `getRequiredFlowAttribute("applicationId")` | Input đã được map vào flow scope |
| `getRequiredFlowAttribute("draft")` | Action khởi tạo đã tạo dữ liệu |
| `registrationService.getLastApplicationId()` | Service nhận đúng input |
| `getCreateDraftCallCount() == 1` | Action được gọi đúng số lần trong lần launch test |
| `assertCurrentStateEquals("enterDetails")` | Execution dừng ở state dự kiến |

Nếu flow khai báo input có kiểu:

```xml
<input name="applicationId" type="long" required="true" />
```

test nên truyền giá trị đúng kiểu hoặc kiểm tra rõ hành vi conversion nếu truyền một kiểu khác. Đừng dựa vào một chuỗi ID không xác định rồi chỉ kiểm tra state; conversion có thể thay đổi dữ liệu hoặc khiến startup thất bại.

### Kiểm tra input bắt buộc

Với `required="true"`, test cần có trường hợp không truyền input:

```java
public void testStartFlowRejectsMissingApplicationId() {
    MutableAttributeMap<Object> input = new LocalAttributeMap<>();
    MockExternalContext context = new MockExternalContext();

    try {
        startFlow(input, context);
        fail("Flow should reject a missing required input");
    } catch (FlowExecutionException expected) {
        // Input bắt buộc không được cung cấp nên startup thất bại.
    }
}
```

Đây là ví dụ định hướng cho trường hợp input thiếu. Exception cụ thể có thể được bọc trong `FlowExecutionException` hoặc exception chuyên biệt tùy phiên bản và vị trí lỗi; khi viết test thực tế, hãy xác nhận exception contract của version đang dùng thay vì phụ thuộc message text không ổn định.

Có thể bổ sung ca input sai kiểu để kiểm tra conversion. Mục tiêu là xác nhận flow **không đi vào state tương tác với một input sai**.

## 10. Kiểm tra state đầu tiên khi flow có nhiều bước khởi tạo

Không phải flow nào cũng bắt đầu trực tiếp bằng view-state. Ví dụ:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="applicationId" type="long" required="true" />

    <action-state id="loadApplication">
        <evaluate expression="registrationService.load(applicationId)"
                  result="flowScope.application" />
        <transition on="success" to="enterDetails" />
    </action-state>

    <view-state id="enterDetails"
                view="registration/enterDetails" />
</flow>
```

Khi gọi `startFlow`:

1. Flow bắt đầu ở `loadApplication`.
2. Action `registrationService.load` chạy.
3. Nếu outcome là `success`, transition đi tới `enterDetails`.
4. Execution dừng ở `enterDetails` để chờ tương tác.

Vì vậy, test startup nên kiểm tra state cuối cùng của chuỗi khởi tạo:

```java
startFlow(input, context);

assertFlowExecutionActive();
assertCurrentStateEquals("enterDetails");
assertTrue(getRequiredFlowAttribute("application") instanceof Application);
```

Nếu mục tiêu riêng là kiểm tra action-state đầu tiên, có thể viết test cho action/outcome của nó hoặc quan sát qua listener/test double phù hợp. Không giả định `assertCurrentStateEquals("loadApplication")` luôn đúng sau khi `startFlow` trả về; action-state có thể đã chạy và flow đã đi tiếp.

### Decision-state ở đầu flow

Nếu flow bắt đầu bằng `decision-state`, test nên chuẩn bị input và service result để xác định nhánh được chọn:

```xml
<decision-state id="routeApplication">
    <if test="applicationType == 'PERSONAL'"
        then="personalDetails" else="businessDetails" />
</decision-state>

<view-state id="personalDetails" />
<view-state id="businessDetails" />
```

Hai test có input khác nhau nên kiểm tra hai state đầu tiên khác nhau. Điều này chứng minh routing logic tại startup chứ không chỉ chứng minh flow XML parse thành công.

## 11. Khi flow kế thừa definition hoặc cần resource phụ

Nếu flow đang kiểm thử kế thừa từ flow cha hoặc sử dụng state được định nghĩa trong model resource khác, test cần khai báo các model resource:

```java
@Override
protected FlowDefinitionResource[] getModelResources(
        FlowDefinitionResourceFactory resourceFactory) {
    return new FlowDefinitionResource[] {
        resourceFactory.createClassPathResource(
                "flows/shared/common-flow.xml", getClass())
    };
}
```

Nếu thiếu parent flow resource, test có thể thất bại khi build flow dù file child riêng lẻ trông hợp lệ. Đây là lỗi **test setup/resource resolution**, không nhất thiết là lỗi logic startup.

Với flow gọi subflow, có thể đăng ký stub subflow trong `MockFlowBuilderContext` hoặc registry của test. Tuy nhiên, nếu bài test chỉ xác nhận state đầu tiên trước khi subflow được gọi, không cần dựng toàn bộ hành trình con; chỉ đăng ký các dependency mà startup thực sự sử dụng.

## 12. Những điều AbstractXmlFlowExecutionTests không chứng minh

Flow execution test là kiểm thử ở tầng flow engine. Không nên suy rộng kết quả của nó sang toàn bộ ứng dụng web.

| Điều cần xác minh | Flow execution test | MVC integration test |
| --- | --- | --- |
| XML flow nạp được | Có | Có thể |
| Input được map khi launch | Có | Có thể |
| `on-start` chạy và cập nhật scope | Có | Có thể |
| State hiện tại đúng | Có | Có thể |
| Flow service stub được gọi | Có | Có thể |
| `FlowHandlerMapping` tìm đúng flow | Không | Có |
| `FlowHandlerAdapter` dispatch request | Không | Có |
| URL launch/resume đúng | Không | Có |
| Cookie/HTTP session thực | Không | Có |
| CSRF/filter chain | Không | Có |
| View resolver tìm template | Không | Có |
| HTML render đúng trên browser | Không | Chỉ khi kết hợp browser/E2E |

### Khi nào cần thêm MockMvc?

Nếu ứng dụng có cấu hình Spring MVC và muốn kiểm tra request HTTP launch flow, hãy bổ sung integration test dùng `MockMvc` với đúng `FlowHandlerMapping`, `FlowHandlerAdapter`, flow executor và security config của ứng dụng.

Một kiểm thử MVC có thể:

1. Gửi GET tới URL launch flow.
2. Kiểm tra response redirect hoặc view theo cấu hình.
3. Trích execution URL/key từ response hoặc HTML.
4. Gửi request tiếp tục execution theo đúng event.
5. Kiểm tra response, cookie/session và trạng thái dữ liệu.

Flow test vẫn hữu ích vì nó khoanh vùng lỗi điều phối; MockMvc bổ sung bằng chứng về HTTP integration. Với giao diện phụ thuộc JavaScript, AJAX, browser history hoặc component JSF, có thể cần browser test để xác minh đầy đủ.

## 13. JUnit và tổ chức test class

`AbstractXmlFlowExecutionTests` hiện kế thừa `junit.framework.TestCase`. Vì vậy, test class sử dụng quy ước JUnit 3:

- Test method có tên bắt đầu bằng `test`.
- Assertion có thể dùng các phương thức kế thừa như `assertTrue`, `assertEquals` và `fail`.
- Không mặc định rằng chỉ thêm annotation `@Test` của JUnit Jupiter là đủ để chạy lớp test này.

Nếu dự án đang dùng JUnit 5, cần cấu hình runner/engine tương thích với JUnit 3 (chẳng hạn JUnit Vintage nếu stack test hỗ trợ), hoặc chọn cách tổ chức test khác phù hợp. Kiểm tra dependency và test engine thực tế của dự án.

### Một test cho mỗi kịch bản startup

Không nên dồn mọi tình huống vào một method. Có thể tách:

- `testStartFlowShowsEnterDetails`: input hợp lệ, state đầu đúng.
- `testStartFlowCreatesDraft`: `on-start` gọi service và lưu draft.
- `testStartFlowRejectsMissingApplicationId`: input bắt buộc bị thiếu.
- `testStartFlowRoutesPersonalApplication`: nhánh decision cho loại cá nhân.
- `testStartFlowRoutesBusinessApplication`: nhánh decision cho loại doanh nghiệp.
- `testStartFlowFailsWhenInitializationServiceThrows`: xử lý lỗi khởi tạo.

Mỗi test nên chuẩn bị input, context và stub riêng để không phụ thuộc trạng thái còn sót từ ca trước.

## 14. Những lỗi thường gặp khi kiểm thử startup

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy flow resource | Sai classpath/path hoặc resource không được copy vào test runtime | Kiểm tra đường dẫn và build output |
| Flow build thất bại | XML sai, thiếu bean, thiếu parent model resource | Đọc root cause; đăng ký dependency và resource cần thiết |
| `assertCurrentStateEquals` thất bại | Flow đi vào state khác hoặc tự chuyển qua action/decision | Theo dõi initial state và outcome của action |
| Input trong flow scope bị null | Không truyền input hoặc tên input sai | Kiểm tra `<input>` và `startFlow(input, context)` |
| Input sai kiểu | Không khớp kiểu khai báo hoặc thiếu converter | Truyền kiểu đúng và test conversion riêng |
| `on-start` không chạy như mong đợi | Biểu thức không được gọi, bean chưa đăng ký hoặc flow không khởi chạy đúng | Stub service và kiểm tra call count |
| Service thật bị gọi trong test | Thiếu stub/mock hoặc bean được resolve từ context khác | Đăng ký đúng bean name trong builder context |
| Execution đã kết thúc | Initial action/decision đi tới end-state hoặc outcome | Kiểm tra đường đi startup, không chỉ assert state |
| Principal không có trong EL | Chưa gọi `setCurrentUser` hoặc logic dùng security context thật | Phân biệt mock principal với Spring Security integration |
| Test không được chạy trong JUnit 5 | JUnit 3 TestCase không được engine hiện tại phát hiện | Cấu hình JUnit Vintage hoặc runner phù hợp |
| Test startup pass nhưng URL launch lỗi | Flow test không kiểm tra MVC handler mapping | Viết thêm MockMvc integration test |
| State đúng nhưng view không render | Flow test không dùng view resolver thực tế | Kiểm tra view bằng MVC/E2E test |

## 15. Ma trận kiểm thử khởi chạy flow

Với flow đăng ký ở ví dụ, một bộ test startup tối thiểu có thể gồm:

| Kịch bản | Input/context | Kỳ vọng |
| --- | --- | --- |
| Input hợp lệ | `applicationId = 42L` | Execution active, dừng tại `enterDetails` |
| Principal có mặt | `currentUser = learner` | Flow đọc được principal nếu logic sử dụng |
| Locale được cung cấp | `vi-VN` | Formatter/conversion nhận locale mong đợi |
| `on-start` tạo draft | Service stub trả `ApplicationDraft` | `flowScope.draft` có đúng kiểu |
| Service nhận đúng ID | `applicationId = 42L` | Stub ghi nhận đúng tham số |
| Input thiếu | Không truyền `applicationId` | Startup bị từ chối |
| Input sai kiểu | Giá trị không chuyển được sang `long` | Startup thất bại theo conversion contract |
| Bean thiếu | Không đăng ký `registrationService` | Flow build/evaluate thất bại, test phát hiện |
| Action khởi tạo lỗi | Stub ném exception | Startup không được xem là thành công |
| Action-state ban đầu | Action trả `success` | Execution dừng ở view-state đích |
| Decision-state ban đầu | Input chọn nhánh cá nhân | Dừng ở `personalDetails` |
| Flow đi tới end-state | Nhánh khởi tạo kết thúc ngay | Assert execution ended và outcome phù hợp, không assert active |

Không nhất thiết test tất cả trong một lớp. Hãy chọn các trường hợp theo độ phức tạp của flow và rủi ro khởi tạo.

## 16. Bài tập thực hành: kiểm thử flow mở hồ sơ vay

Tạo flow `loanApplication` gồm input `customerId`, `on-start` tải bản nháp, state `enterApplicantDetails`, `reviewApplication` và end-state `submitted`.

1. Khai báo `customerId` là input bắt buộc kiểu `long`.
2. Trong `on-start`, gọi `loanService.loadDraft(customerId)` và đưa kết quả vào `flowScope.application`.
3. Tạo `LoanFlowExecutionTests` kế thừa `AbstractXmlFlowExecutionTests`.
4. Override `getResource` để nạp đúng XML flow từ classpath.
5. Đăng ký `StubLoanService` trong `configureFlowBuilderContext`.
6. Tạo `MockExternalContext` và đặt principal test nếu flow dùng `currentUser`.
7. Gọi `startFlow(input, context)` với `customerId` hợp lệ.
8. Assert execution active, current state là `enterApplicantDetails` và `application` tồn tại trong flow scope.
9. Xác minh service nhận đúng `customerId` và được gọi đúng số lần trong startup.
10. Viết test riêng khi thiếu input, sai kiểu, service ném exception và khi action-state ban đầu tự chuyển sang view-state.
11. Nếu ứng dụng dùng Spring MVC, viết thêm MockMvc test để xác minh URL launch flow và response thực tế.

**Câu hỏi tự đánh giá:**

- Vì sao `assertCurrentStateEquals` cần được kết hợp với `assertFlowExecutionActive`?
- `startFlow(input, context)` khác việc gửi GET tới URL launch qua Spring MVC như thế nào?
- Vì sao cần đăng ký stub service trong `configureFlowBuilderContext`?
- `MockExternalContext.setCurrentUser` có chứng minh Spring Security filter chain đã xác thực người dùng không?
- Nếu state đầu tiên là `action-state`, state hiện tại sau `startFlow` có nhất thiết là action-state đó không?
- Vì sao `setCurrentState` không phù hợp để kiểm tra đường khởi chạy ban đầu?
- `getRequiredFlowAttribute("draft")` bổ sung bằng chứng gì ngoài việc state đầu đúng?
- Khi nào cần `getModelResources`?
- Vì sao flow test pass vẫn chưa chứng minh view resolver và HTTP mapping hoạt động?

## 17. Tài liệu tham khảo

- [Spring Web Flow 4.0.2 API — AbstractXmlFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/execution/AbstractXmlFlowExecutionTests.html): lớp test XML flow, `getResource`, `configureFlowBuilderContext` và các assertion kế thừa.
- [Spring Web Flow 4.0.2 API — AbstractFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/execution/AbstractFlowExecutionTests.html): `startFlow`, `assertCurrentStateEquals`, `assertFlowExecutionActive`, flow scope và các thao tác test.
- [Spring Web Flow 4.0.2 API — MockExternalContext](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/MockExternalContext.html): external context giả cho test.
- [Spring Web Flow 4.0.2 API — MockFlowBuilderContext](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/MockFlowBuilderContext.html): đăng ký stub service và subflow.
- [Spring Web Flow Reference Guide 3.0.1 — Testing Flows](https://docs.spring.io/spring-webflow/docs/3.0.1/reference/#testing-flows): hướng dẫn `AbstractXmlFlowExecutionTests`, flow resource, dependencies, startup và event handling.
- [Spring Web Flow Reference Guide 2.5.1 — Testing flows](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): ví dụ test startup với input, `MockExternalContext` và assertion state.

## Ghi nhớ

Kiểm thử khởi chạy flow cần xác nhận **execution bắt đầu đúng, còn active, dừng ở state dự kiến và nhận đủ dữ liệu khởi tạo**. Với XML flow, `AbstractXmlFlowExecutionTests` cho phép chỉ định resource, đăng ký stub service, gọi `startFlow(input, context)` và kiểm tra bằng `assertCurrentStateEquals`, `assertFlowExecutionActive` cùng các API flow scope. `MockExternalContext` mô phỏng môi trường ngoài cho flow engine, không thay thế kiểm thử HTTP/Spring Security. Nếu flow bắt đầu bằng action-state hoặc decision-state, hãy kiểm tra state mà execution thực sự dừng lại sau chuỗi khởi tạo. Kết hợp flow test với MVC integration test khi cần xác minh URL launch, handler mapping, session và view rendering.
