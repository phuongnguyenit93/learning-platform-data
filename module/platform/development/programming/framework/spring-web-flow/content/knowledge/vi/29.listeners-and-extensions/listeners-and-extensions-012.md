# Kiểm thử mở rộng bằng các hợp đồng và tình huống lỗi

## 1. Mục tiêu và bối cảnh

Một listener ghi nhận chuyển state có thể chạy đúng trong bản demo nhưng gây lỗi khi người dùng gửi lại form, một subflow kết thúc hoặc hệ thống đo lường bị gián đoạn. Một extension kiểm tra quyền có thể vượt qua unit test nhưng chưa hề được đăng ký với flow executor đang phục vụ HTTP. Vì vậy, kiểm thử phần mở rộng cần chứng minh cả hành vi riêng của extension lẫn cách nó tham gia vào hành trình nhiều bước.

Trong module **SPRING_WEB_FLOW**, bài này tập trung vào phần mở rộng gắn với state, event, transition và subflow của Spring Web Flow. Ví dụ xuyên suốt là hành trình gửi hồ sơ: `details → review → submit → done`, có nhánh quay lại và phục hồi khi dịch vụ tạm thời chưa sẵn sàng. Spring MVC tiếp nhận request; Web Flow điều phối; listener hỗ trợ quan sát hoặc thực thi một chính sách cắt ngang đã được xác định rõ.

Sau bài học, bạn có thể:

- Viết hợp đồng có đầu vào, kết quả quan sát được và các tác dụng phụ bị cấm.
- Chọn đúng lớp kiểm thử cho listener, action, validator, bộ chuyển đổi và cấu hình đăng ký.
- Kiểm chứng lỗi kỹ thuật, retry và vòng đời scope bằng các tình huống có thể lặp lại.
- Phân biệt kết thúc một flow session, hoàn thành nghiệp vụ và commit dữ liệu.
- Xác định phần nào cần flow engine thật, repository thật hoặc tích hợp HTTP.

Ví dụ API trong bài dùng mốc **Spring Web Flow 3.0.0** để có chữ ký xác định; đây không phải tuyên bố về phiên bản mới nhất. Ví dụ kiểm thử dùng phong cách `junit.framework.TestCase` của bộ hỗ trợ kiểm thử flow; nếu dự án chỉ chạy JUnit Platform, cần cấu hình khả năng chạy các test kiểu này. Các đoạn mã là tài liệu thực hành để đưa vào dự án thử nghiệm, không tự tạo thêm mã nguồn trong module bài học.

## 2. Hợp đồng của extension gồm những gì?

Hợp đồng là phát biểu về hành vi mà bên sử dụng được quyền dựa vào. Nó phải cụ thể hơn “listener hoạt động đúng”. Một hợp đồng hữu ích gồm:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Điều kiện trước | Extension được gọi ở thời điểm nào, dữ liệu nào đã tồn tại? | State đích đã được nhập; có flow đang hoạt động |
| Đầu vào | Dữ liệu nào được đọc, giá trị thiếu được xử lý ra sao? | Chỉ dùng flow ID và state ID |
| Kết quả | Có thể kiểm chứng điều gì sau lời gọi? | Sink nhận một bản ghi chuyển state |
| Tác dụng phụ | Được phép thay đổi những gì? | Ghi telemetry; không đổi form hoặc outcome |
| Chính sách lỗi | Lỗi nào được chặn, lỗi nào phải làm thao tác thất bại? | Sink telemetry mất kết nối không chặn điều hướng |
| Vòng đời | Trạng thái tạm thuộc request, flow hay toàn ứng dụng? | Không giữ `RequestContext` trong singleton |
| Lặp và đồng thời | Gọi lại hoặc hai execution cùng chạy có an toàn không? | Không dùng field `currentUser` chung |
| Khả năng quan sát | Bằng chứng lỗi và phục hồi được lưu ở đâu? | Bộ đếm mẫu bị bỏ, mã lỗi nghiệp vụ |

Không áp một chính sách lỗi cho mọi loại extension. Telemetry không thiết yếu thường có thể suy giảm chức năng. Kiểm tra quyền hoặc ghi nhận bắt buộc theo yêu cầu nghiệp vụ có thể cần từ chối thao tác. Với trường hợp thứ hai, hợp đồng phải nói rõ từ chối trước tác dụng phụ nào và trả kết quả nào cho người dùng.

### 2.1. Ví dụ hợp đồng của listener quan sát

Đặt tên hợp đồng là `STATE_TELEMETRY_V1`:

1. Mỗi lần engine thông báo đã vào một state, listener gửi đúng một mẫu tới sink trong lần callback đó.
2. Mẫu chỉ gồm định danh flow và state, không chứa dữ liệu form hay tham số request.
3. Listener không sửa scope, không phát thêm event và không tự điều hướng.
4. Khi sink ném `TelemetryUnavailableException`, listener tăng bộ đếm mất mẫu và trả về bình thường.
5. Những lỗi lập trình khác không bị bắt chung rồi bỏ qua.

“Đúng một mẫu trong mỗi callback” không đồng nghĩa một mẫu cho mỗi thao tác nghiệp vụ. Quay lại một state tạo một lần vào state mới. Muốn thống kê số hồ sơ thực sự được tạo, cần bằng chứng từ dịch vụ nghiệp vụ hoặc dữ liệu đã commit.

### 2.2. Ví dụ hợp đồng của extension kiểm tra quyền

Với extension chặn truy cập bước xác nhận:

- Người dùng không có quyền không được gọi dịch vụ gửi hồ sơ.
- Kết quả từ chối được chuyển thành trang hoặc thông báo theo chính sách của ứng dụng.
- Không ghi form chứa dữ liệu cá nhân vào log từ chối.
- Thay đổi quyền giữa hai request phải được xử lý theo chính sách đã chọn, không dựa vào một cờ quyền cũ vô thời hạn trong flow scope.

Kiểm thử phải có cả khẳng định dương và khẳng định âm: có kết quả từ chối **và** số lần gọi dịch vụ bằng không.

## 3. Hiểu đúng ranh giới callback trước khi đặt assertion

`stateEntering` là điểm trước khi vào state, còn `stateEntered` là thông báo sau khi chuyển vào state. `exceptionThrown` thông báo lỗi trước khi handler của flow xử lý; quan sát được lỗi chưa chứng minh request cuối cùng thất bại. `sessionEnded` cũng được gọi khi một subflow session kết thúc, nên không thể xem mọi lần gọi là hoàn thành toàn bộ hành trình. Những ranh giới này được mô tả trong [Javadoc FlowExecutionListener 3.0.0](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/execution/FlowExecutionListener.html).

Các hệ quả đối với thiết kế test:

- Dùng tham số `session` của callback kết thúc để xác định session vừa kết thúc; không suy từ active session có thể đã đổi.
- Khi kiểm tra lỗi có phục hồi, assertion phải bao gồm state cuối cùng và dữ liệu cần giữ lại.
- Một callback hoàn tất request không phải bằng chứng transaction đã commit hoặc hệ thống ngoài đã nhận thông điệp.
- Nếu thứ tự giữa hai extension là yêu cầu nghiệp vụ, cần kiểm thử cấu hình thực tế và kết quả của thứ tự đó.

Không snapshot toàn bộ danh sách callback chỉ để khóa chặt chi tiết triển khai. Hãy kiểm tra các mốc có ý nghĩa đối với hợp đồng, chẳng hạn việc kiểm tra quyền xảy ra trước lời gọi ghi dữ liệu. Chỉ kiểm tra toàn bộ thứ tự khi chính thứ tự đầy đủ là hành vi đã được cam kết.

## 4. Chọn lớp kiểm thử theo bằng chứng cần có

| Lớp | Dùng gì? | Chứng minh được | Chưa chứng minh được |
|---|---|---|---|
| Unit | Gọi trực tiếp extension với test double | Mapping dữ liệu, chính sách lỗi, không sửa scope | Engine có thực sự gọi nó không |
| Flow integration | Flow XML và engine thật, dịch vụ giả | Event dẫn tới đúng state; listener được gọi trong vòng đời flow | Cấu hình MVC và repository production |
| Configuration integration | Application context và registry/executor thực tế | Bean được đăng ký, bộ lọc flow đúng, phụ thuộc được nối đúng | Hành vi của trình duyệt |
| Repository integration | Cơ chế lưu và khôi phục execution thực tế | Pause/resume, serialization nếu có, hết hạn và lock | Mọi tình huống mạng phía người dùng |
| HTTP/end-to-end | MVC, session, form và trình duyệt hoặc HTTP client | Binding, redirect, execution key, kết quả người dùng thấy | Mọi tổ hợp lỗi của extension |

`MockRequestContext` hữu ích cho việc gọi độc lập action hoặc listener, nhưng bản thân nó không chạy vòng đời engine. Xem [Javadoc MockRequestContext](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/test/MockRequestContext.html). Kiểm thử flow XML có thể dùng `AbstractXmlFlowExecutionTests`; lớp này cung cấp các điểm mở rộng cho tài nguyên và phụ thuộc flow. Xem [Javadoc AbstractXmlFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/test/execution/AbstractXmlFlowExecutionTests.html).

## 5. Ví dụ unit test: listener telemetry có chính sách lỗi rõ ràng

### 5.1. Mã extension

Đặt mã minh họa trong package `example.webflow`. Sink là cổng do ứng dụng định nghĩa, không phải API có sẵn của Spring Web Flow.

```java
package example.webflow;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.webflow.definition.StateDefinition;
import org.springframework.webflow.execution.FlowExecutionListener;
import org.springframework.webflow.execution.RequestContext;

public final class StateTelemetryListener implements FlowExecutionListener {
    public interface Sink {
        void record(String flowId, String stateId);
    }

    public static final class TelemetryUnavailableException
            extends RuntimeException {
        public TelemetryUnavailableException(String message) {
            super(message);
        }
    }

    private final Sink sink;
    private final AtomicInteger droppedSamples = new AtomicInteger();

    public StateTelemetryListener(Sink sink) {
        this.sink = sink;
    }

    @Override
    public void stateEntered(RequestContext context,
                             StateDefinition previousState,
                             StateDefinition state) {
        try {
            sink.record(context.getActiveFlow().getId(), state.getId());
        } catch (TelemetryUnavailableException ex) {
            droppedSamples.incrementAndGet();
        }
    }

    public int getDroppedSamples() {
        return droppedSamples.get();
    }
}
```

Mẫu dùng bộ đếm cục bộ để minh họa chính sách. Trong triển khai thật, có thể xuất bộ đếm qua hệ thống metrics phù hợp. `AtomicInteger` chỉ bảo vệ bộ đếm; sink vẫn phải có hợp đồng an toàn khi dùng chung. Không được suy ra toàn bộ listener đã an toàn đồng thời chỉ vì có một field atomic.

Việc bắt ngoại lệ được đặt sát cổng sink và chỉ bắt loại lỗi đã định nghĩa. Nếu `record()` trả về ngay nhưng gửi dữ liệu bất đồng bộ, lỗi xảy ra sau đó phải do tầng bất đồng bộ xử lý; khối `catch` này không quan sát được lỗi ấy.

### 5.2. Test double có khả năng tiêm lỗi

Fixture sau chỉ dành cho test, chạy tuần tự; danh sách của nó không phải bộ thu thập an toàn đồng thời.

```java
package example.webflow;

import java.util.ArrayList;
import java.util.List;

public final class RecordingSink implements StateTelemetryListener.Sink {
    public final List<String> samples = new ArrayList<>();
    public boolean unavailable;

    @Override
    public void record(String flowId, String stateId) {
        if (unavailable) {
            throw new StateTelemetryListener.TelemetryUnavailableException(
                "sink temporarily unavailable");
        }
        samples.add(flowId + ":" + stateId);
    }
}
```

### 5.3. Kiểm tra hợp đồng thay vì chỉ kiểm tra không ném lỗi

```java
package example.webflow;

import junit.framework.TestCase;
import org.springframework.webflow.test.MockRequestContext;

public class StateTelemetryListenerTest extends TestCase {
    public void testRecordsStateWithoutChangingFlowData() {
        RecordingSink sink = new RecordingSink();
        StateTelemetryListener listener = new StateTelemetryListener(sink);
        MockRequestContext context = new MockRequestContext();
        context.getFlowScope().put("draftId", "draft-42");

        listener.stateEntered(context, null, context.getCurrentState());

        assertEquals(1, sink.samples.size());
        assertEquals(context.getActiveFlow().getId() + ":"
                + context.getCurrentState().getId(), sink.samples.get(0));
        assertEquals("draft-42", context.getFlowScope().get("draftId"));
        assertEquals(0, listener.getDroppedSamples());
    }

    public void testUnavailableSinkDropsSampleWithoutChangingDraft() {
        RecordingSink sink = new RecordingSink();
        sink.unavailable = true;
        StateTelemetryListener listener = new StateTelemetryListener(sink);
        MockRequestContext context = new MockRequestContext();
        context.getFlowScope().put("draftId", "draft-42");

        listener.stateEntered(context, null, context.getCurrentState());

        assertTrue(sink.samples.isEmpty());
        assertEquals(1, listener.getDroppedSamples());
        assertEquals("draft-42", context.getFlowScope().get("draftId"));
    }
}
```

Các test trên chứng minh phần xử lý callback với context giả. Chúng chưa chứng minh listener không cản điều hướng trong một flow thật. Assertion về `draftId` là một mẫu kiểm tra dữ liệu được bảo vệ; nếu hợp đồng bảo vệ nhiều scope hoặc output hơn, fixture phải đưa thêm những dữ liệu đó vào.

Có thể bổ sung một test cho sink ném `IllegalArgumentException` để chứng minh lỗi lập trình không bị bắt như lỗi mất kết nối. Khi đó test phải kiểm tra đúng ngoại lệ, không dùng `catch (Exception)` rồi coi mọi lỗi là đạt.

## 6. Kiểm thử listener cùng flow engine thật

### 6.1. Flow tối thiểu để kiểm tra điều hướng

Tài nguyên minh họa `src/test/resources/flows/review-flow.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="details">

    <view-state id="details">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="done"/>
    </view-state>

    <end-state id="done"/>
</flow>
```

Flow này cố ý tách khỏi tác vụ gửi hồ sơ, form binding và database để đo riêng tác động của listener lên điều hướng. Bộ hỗ trợ test flow cung cấp môi trường kiểm thử view; test này không xác nhận template giao diện render đúng.

### 6.2. Đăng ký trước khi start flow

`setFlowExecutionListener()` gắn listener cho execution được khởi tạo tiếp theo trong lớp test. Đây là API của bộ hỗ trợ kiểm thử, không phải cách cấu hình bean production. Xem [AbstractExternalizedFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/test/execution/AbstractExternalizedFlowExecutionTests.html).

```java
package example.webflow;

import org.springframework.webflow.engine.builder.support.FlowDefinitionResource;
import org.springframework.webflow.engine.builder.support.FlowDefinitionResourceFactory;
import org.springframework.webflow.test.MockExternalContext;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;

public class ReviewFlowListenerTest extends AbstractXmlFlowExecutionTests {
    private RecordingSink sink;
    private StateTelemetryListener listener;

    @Override
    protected void setUp() throws Exception {
        super.setUp();
        sink = new RecordingSink();
        listener = new StateTelemetryListener(sink);
        setFlowExecutionListener(listener);
    }

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory factory) {
        return factory.createFileResource(
            "src/test/resources/flows/review-flow.xml");
    }

    public void testNextStillWorksWhenTelemetryIsUnavailable() {
        startFlow(new MockExternalContext());
        assertCurrentStateEquals("details");
        int before = listener.getDroppedSamples();

        sink.unavailable = true;
        MockExternalContext request = new MockExternalContext();
        request.setEventId("next");
        resumeFlow(request);

        assertCurrentStateEquals("review");
        assertFlowExecutionActive();
        assertEquals(before + 1, listener.getDroppedSamples());
    }

    public void testReturningToDetailsProducesAnotherEntrySample() {
        startFlow(new MockExternalContext());

        MockExternalContext next = new MockExternalContext();
        next.setEventId("next");
        resumeFlow(next);
        assertCurrentStateEquals("review");

        MockExternalContext back = new MockExternalContext();
        back.setEventId("back");
        resumeFlow(back);
        assertCurrentStateEquals("details");

        long detailEntries = sink.samples.stream()
            .filter(sample -> sample.endsWith(":details"))
            .count();
        assertEquals(2L, detailEntries);
    }

    public void testConfirmEndsFlow() {
        startFlow(new MockExternalContext());
        MockExternalContext next = new MockExternalContext();
        next.setEventId("next");
        resumeFlow(next);
        assertCurrentStateEquals("review");

        MockExternalContext confirm = new MockExternalContext();
        confirm.setEventId("confirm");
        resumeFlow(confirm);

        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("done");
    }
}
```

`setEventId()` đặt event cho request giả của test. Nó giúp kiểm tra điều phối mà không phải giả lập cú pháp tham số của nút submit; cú pháp HTTP thật vẫn cần kiểm tra ở lớp MVC. Xem [MockExternalContext 3.0.0](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/test/MockExternalContext.html).

Assertion `before + 1` phù hợp với fixture cụ thể: từ `details` tới `review` chỉ có một lần vào state. Nếu flow bổ sung action-state trung gian, cần xem lại hợp đồng đang đo; không sửa số đếm tùy tiện để làm test xanh.

### 6.3. Tránh bỏ qua chính vòng đời cần kiểm tra

`setCurrentState()` có ích khi cô lập một transition. Tuy nhiên, nếu dùng nó để nhảy thẳng tới `review`, test có thể bỏ qua listener khởi tạo, input mapping hoặc dữ liệu tạo ở bước trước. Để kiểm tra hành trình listener, hãy khởi động flow rồi gửi event qua các bước liên quan. Bộ hỗ trợ flow mô tả cả khởi động, resume và assertion trạng thái trong [AbstractFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/execution/AbstractFlowExecutionTests.html).

## 7. Ma trận lỗi: mỗi lỗi cần một kết quả quan sát được

Ví dụ sau là đặc tả kiểm thử cho ứng dụng gửi hồ sơ, không phải mọi dòng đều đã được flow tối thiểu ở trên triển khai.

| Tình huống tiêm lỗi | Thiết lập | Kết quả bắt buộc | Assertion âm |
|---|---|---|---|
| Telemetry ngừng hoạt động | Sink ném lỗi mất kết nối đã định nghĩa | Điều hướng tiếp tục, tăng mất mẫu | Không đổi draft |
| Dữ liệu form không hợp lệ | Thiếu trường bắt buộc hoặc sai định dạng | Ở lại bước nhập, có lỗi theo trường | Không gọi dịch vụ gửi |
| Quyền bị thu hồi | Thu hồi quyền trước request xác nhận | Từ chối theo chính sách | Không ghi hồ sơ |
| Dịch vụ tạm thời lỗi | Stub thất bại trước khi commit | Sang state phục hồi hoặc ở lại bước đã quy định | Không báo thành công |
| Dịch vụ commit rồi timeout | Ghi thành công nhưng phản hồi bị mất | Tra cứu bằng khóa nghiệp vụ trước retry | Không tạo bản ghi thứ hai |
| Event không được hỗ trợ | Gửi event không có transition tại state hiện tại | Kết quả xử lý lỗi được ứng dụng quy định | Không tự đi vào bước đặc quyền |
| Subflow kết thúc | Flow con trả outcome về flow cha | Flow cha tiếp tục đúng nhánh | Không ghi nhận hoàn thành root sớm |
| Execution hết hạn | Request mang key không còn tra cứu được | Phản hồi khôi phục hoặc khởi động lại đã định nghĩa | Không tái dùng draft của người khác |
| Hai request cùng execution | Điều khiển hai request qua hàng rào đồng bộ | Xung đột được xử lý theo repository | Không ghi trùng nghiệp vụ |
| Cleanup bị lỗi | Tác vụ lỗi chính và đóng tài nguyên cùng thất bại | Giữ nguyên dấu vết lỗi chính | Không thay thế nguyên nhân bằng lỗi phụ |

Đối với mỗi dòng, ghi đủ: dữ liệu trước request, điểm tiêm lỗi, kết quả người dùng thấy, state hoặc outcome sau xử lý, dữ liệu bền vững và tài nguyên còn mở. Chỉ kiểm tra “có exception” chưa chứng minh chính sách lỗi đã được thực hiện đúng.

## 8. Kiểm thử action, validation và handler trong nhánh lỗi

### 8.1. Phân biệt lỗi dự kiến với ngoại lệ kỹ thuật

Ví dụ, dịch vụ phát hiện hồ sơ hết hạn là một kết quả nghiệp vụ dự kiến. Ứng dụng có thể chuyển kết quả đó thành event `expired` rồi điều hướng tới state phù hợp. Mất kết nối không xác định là lỗi kỹ thuật; action hoặc exception handler chịu trách nhiệm chuyển nó thành kết quả phục hồi nếu chính sách cho phép.

Không bắt mọi `RuntimeException` trong listener rồi coi như đã phục hồi flow. Listener chỉ quan sát lỗi không thay thế hợp đồng của action và handler. Nhánh phục hồi phải được kiểm chứng bằng cách thực sự gây lỗi trong action đang chạy.

Một đặc tả theo Given/When/Then:

```text
Given:
  Flow đang ở review, draftId = draft-42.
  Form hợp lệ; người dùng có quyền gửi.
  Dịch vụ được cấu hình lỗi tạm thời trước khi ghi dữ liệu.
When:
  Người dùng phát event confirm.
Then:
  Flow tới submissionUnavailable theo cấu hình handler.
  draftId vẫn là draft-42.
  Người dùng nhận thông báo có thể thử lại.
  Không có hồ sơ đã lưu; không có thông báo hoàn thành.
When:
  Dịch vụ hoạt động lại và người dùng phát event retry.
Then:
  Flow đi đến outcome thành công.
  Chỉ có một hồ sơ và một tác dụng phụ nghiệp vụ tương ứng.
```

Đây là đặc tả để triển khai cho flow nghiệp vụ có `submissionUnavailable` và `retry`, không phải test có thể chạy trực tiếp với XML ở mục 6.

### 8.2. Kiểm tra binding và validation đúng lớp

Validator độc lập có thể được kiểm thử với model và message context. Test flow cần bổ sung rằng validation thất bại giữ người dùng ở state thích hợp, bảo toàn draft và không chạy action gửi hồ sơ. Test HTTP phải gửi giá trị thô như ngày sai định dạng để kiểm tra cả binding/conversion trước validation.

Nếu unit test tự tạo một đối tượng ngày hợp lệ rồi đưa thẳng vào model, nó không kiểm tra được lỗi chuyển chuỗi người dùng nhập thành ngày. Tương tự, bơm thẳng event `confirm` không chứng minh nút submit và tên tham số trên trang được cấu hình đúng.

### 8.3. Bảo toàn nguyên nhân lỗi

Khi action bị framework bọc ngoại lệ, test nên xác định nguyên nhân nghiệp vụ hoặc kỹ thuật qua cause chain thay vì khóa toàn bộ thông điệp của wrapper. Đồng thời xác nhận handler đã đưa flow tới kết quả nào. Nếu lỗi chưa được xử lý, không tiếp tục `resume` execution đó với giả định engine đã tự rollback mọi trạng thái.

Lỗi đóng tài nguyên cần có quy tắc riêng: giữ lỗi gốc làm nguyên nhân chính, ghi nhận lỗi cleanup bằng cơ chế thích hợp của ứng dụng. Test có hai lỗi đồng thời sẽ phát hiện trường hợp cleanup che khuất lỗi khiến request thất bại ban đầu.

## 9. Subflow, scope và lưu/khôi phục execution

### 9.1. Subflow không phải root flow kết thúc

Với hành trình `application → verifyAddress → application`, lập ít nhất hai test: flow con xác minh thành công và flow con bị hủy. Listener ghi telemetry có thể ghi cả hai session. Listener phát thông báo “hồ sơ hoàn tất” phải có điều kiện rõ ràng về root session và outcome thành công.

Kết quả cần kiểm tra gồm output mapping của flow con, state tiếp theo của flow cha, số thông báo hoàn thành và việc dữ liệu chỉ thuộc flow con không vô tình lọt sang dữ liệu cha. Hủy flow con không mặc nhiên là hủy toàn bộ root flow.

### 9.2. Chọn scope bằng khoảng sống của dữ liệu

| Dữ liệu | Khoảng sống dự kiến | Kiểm thử có ý nghĩa |
|---|---|---|
| Mốc thời gian đo một request | Trong request | Request sau không dùng mốc của request trước |
| Form của một bước | Khi ở view-state tương ứng, theo thiết kế model | Rời bước rồi quay lại có đúng chính sách khởi tạo |
| Draft của flow hiện tại | Trong flow session | Chuyển bước giữ draft; execution khác không đọc được |
| Dữ liệu chia sẻ cha/con | Trong conversation nếu được thiết kế như vậy | Flow con chỉ đọc/ghi những thuộc tính được cho phép |
| Tài nguyên không tuần tự hóa được | Do dịch vụ hoặc hạ tầng quản lý | Không bị đưa vào snapshot execution |

Không giữ `RequestContext`, request HTTP hoặc model của người dùng trong field singleton để tiện dùng ở callback sau. Dữ liệu tương quan cần đi theo scope phù hợp hoặc theo dịch vụ được thiết kế rõ ràng.

### 9.3. Round-trip qua repository thực tế

Nếu cơ chế lưu execution có serialization, một phép kiểm tra `Serializable` riêng lẻ chưa đủ. Cần kiểm thử chuỗi: start → pause → lưu → khôi phục theo cơ chế triển khai → resume. Xác nhận dữ liệu cần thiết còn nguyên và listener vẫn hoạt động theo cấu hình sau khôi phục.

Factory có API riêng để khôi phục phần trạng thái transient của execution; vì vậy, serialize rồi deserialize một đối tượng Java đơn thuần không đại diện đầy đủ cho quá trình repository thực tế. Xem [FlowExecutionImplFactory 3.0.0](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/engine/impl/FlowExecutionImplFactory.html).

Khi kiểm tra hết hạn, gây ra chính điều kiện mất execution hoặc hết phiên của hạ tầng đang dùng. Lỗi có thể xảy ra trước khi callback của flow chạy, nên không mặc định `exceptionThrown` trong listener sẽ nhìn thấy mọi lỗi tra cứu key. Xác nhận phản hồi ở lớp MVC và trạng thái dữ liệu bền vững.

## 10. Retry và tính không tạo trùng tác dụng phụ

Giả sử dịch vụ đã tạo hồ sơ, nhưng phản hồi bị timeout. Người dùng thử lại, callback chạy lần nữa và gửi email lần thứ hai. Test chỉ mô phỏng lỗi trước khi ghi sẽ bỏ sót trường hợp này.

Nên xây dựng ba kịch bản riêng:

1. Thất bại trước commit: retry có thể thực hiện thao tác chưa hoàn thành.
2. Commit thành công, mất phản hồi: retry phải nhận diện thao tác đã hoàn tất bằng khóa ổn định.
3. Hai request cùng cố thực hiện: tầng lưu trữ hoặc dịch vụ phải bảo đảm quy tắc chống trùng dưới cạnh tranh.

Khóa chống trùng nên gắn với thao tác nghiệp vụ, chẳng hạn `(draftId, operationId)`, theo thiết kế ứng dụng. Không xem một execution key dùng cho điều hướng là khóa nghiệp vụ ổn định qua mọi lần khôi phục hay khởi động lại.

```text
Given: operationId op-17 chưa được thực hiện.
When: dịch vụ lưu hồ sơ rồi mô phỏng mất phản hồi.
And: request retry sử dụng lại operationId op-17.
Then: số hồ sơ mới = 1.
And: kết quả trả về tương ứng hồ sơ đã tạo.
And: số thông báo nghiệp vụ được phát theo chính sách = 1.
```

Listener trong bộ nhớ không tự cung cấp bảo đảm xử lý đúng một lần. Nếu ứng dụng cần bảo đảm đó, hãy đặt cơ chế ở ranh giới giao dịch thích hợp, ví dụ unique constraint hoặc outbox theo yêu cầu hệ thống, rồi kiểm thử bằng cơ sở dữ liệu và cơ chế phát thông điệp thực tế.

Không đưa nghiệp vụ gửi hồ sơ vào listener chỉ để dùng lại callback kết thúc. Action/service nên thể hiện tác vụ nghiệp vụ; listener quan sát kết quả hoặc hỗ trợ chính sách cắt ngang đã công bố.

## 11. Kiểm thử cấu hình, đồng thời và tính xác định

### 11.1. Bằng chứng listener được đăng ký thật

Unit test và flow fixture tự đăng ký listener có thể cùng xanh dù cấu hình production bỏ quên bean. Cần một test dùng application context thực tế để khởi động flow mục tiêu qua executor và quan sát sink. Với listener chỉ áp dụng cho một nhóm flow, thêm flow ngoài nhóm để kiểm tra điều kiện lọc.

Nếu có nhiều listener cùng tác động lên quyền, trace hoặc tài nguyên, kiểm tra hành vi phối hợp bằng cấu hình thật. Không dựa vào thứ tự bean được khai báo nếu hệ thống chưa có hợp đồng về thứ tự đó.

### 11.2. Đồng thời trên hai execution và một execution

Hai tình huống cần tách biệt:

- Hai execution khác nhau dùng chung singleton listener: kiểm tra không lẫn định danh draft/người dùng và sink an toàn khi dùng chung.
- Hai request thao tác cùng execution: kiểm tra cơ chế lock/xung đột của repository cùng khả năng chống trùng ở tầng nghiệp vụ.

Dùng latch hoặc barrier để tạo đúng điểm giao nhau, đặt timeout và luôn giải phóng tài nguyên test. Không dùng `Thread.sleep()` với hy vọng hai request sẽ va chạm. Kiểm thử concurrency của fixture dùng danh sách không đồng bộ sẽ tạo lỗi giả, vì vậy cần đổi fixture phù hợp trước khi kiểm tra cạnh tranh.

### 11.3. Các yếu tố làm test thiếu ổn định

Tiêm clock vào extension đo thời gian thay vì so sánh với thời gian thật. Dùng ID cố định hoặc bộ sinh ID điều khiển được. Nếu có hàng đợi bất đồng bộ, chờ điều kiện với timeout hữu hạn và cung cấp thông tin chẩn đoán khi hết hạn.

Mỗi test cần sink và trạng thái lỗi riêng; không dùng một cờ static khiến test chạy song song tác động lẫn nhau. Reset tài nguyên ngoài sau test phải dựa trên định danh của chính test đó.

## 12. Bài thực hành và tiêu chí hoàn thành

Bắt đầu với flow và listener ở mục 5–6, sau đó mở rộng trong một dự án thử nghiệm:

1. Bổ sung action gửi hồ sơ và một state phục hồi có event `retry`.
2. Viết đặc tả cho lỗi trước commit và lỗi sau commit nhưng mất phản hồi.
3. Thêm subflow xác minh địa chỉ; kiểm tra hủy flow con không phát hoàn tất root.
4. Thêm form binding/validation và kiểm tra dịch vụ không được gọi khi dữ liệu sai.
5. Kiểm tra listener được đăng ký qua cấu hình executor mà ứng dụng HTTP sử dụng.
6. Kiểm thử hết execution qua repository, sau đó kiểm tra phản hồi MVC.

Tiêu chí chấp nhận:

- Mỗi yêu cầu có assertion về kết quả và tác dụng phụ, không chỉ số lần callback.
- Lỗi có thể được tiêm một cách xác định, không phụ thuộc dịch vụ ngoài đang hỏng thật.
- Nhánh phục hồi chứng minh draft còn đúng và request tiếp theo có hành vi đã quy định.
- Test phân biệt rõ flow con, flow cha và dữ liệu bền vững.
- Retry không tạo trùng thao tác đã hoàn tất.
- Bộ test nói rõ phạm vi đã kiểm tra: unit, flow, cấu hình, repository hay HTTP.

Một extension đáng tin cậy có hợp đồng đủ rõ để thay đổi triển khai mà vẫn giữ được điều người dùng quan sát: điều hướng đúng, lỗi được xử lý theo chính sách, dữ liệu không lẫn phiên và tác vụ nghiệp vụ không bị thực hiện trùng.