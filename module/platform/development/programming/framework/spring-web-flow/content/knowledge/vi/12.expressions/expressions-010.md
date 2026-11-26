# flowRequestContext, flowExecutionContext và externalContext

Trong chương **Biểu thức**, ba đối tượng `flowRequestContext`, `flowExecutionContext` và `externalContext` giúp biểu thức trong Spring Web Flow truy cập đúng phần thông tin cần thiết của một lần xử lý. Chúng liên quan chặt chẽ nhưng đại diện cho ba góc nhìn khác nhau: ngữ cảnh của request đang xử lý, trạng thái thực thi flow và môi trường bên ngoài flow như request, session hoặc servlet context.

Module `SPRING_WEB_FLOW` hướng tới việc mô hình hóa hành trình web nhiều bước qua state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên; tích hợp Spring MVC; kiểm thử và phục hồi luồng khi gặp lỗi. Hiểu ranh giới giữa ba đối tượng này giúp viết expression dễ đọc, giảm phụ thuộc trực tiếp vào Servlet API và tránh lưu nhầm dữ liệu vào scope có vòng đời không phù hợp.

## 1. Nhìn nhanh ba đối tượng

| Đối tượng | Đại diện cho | Dùng khi cần |
|---|---|---|
| `flowRequestContext` | Request context của lần xử lý flow hiện tại | Đọc event, state hiện tại, message context, flow scope, request parameters hoặc truy cập execution/external context |
| `flowExecutionContext` | Thông tin về execution đang chạy | Xem flow definition, execution key, session đang hoạt động và state của flow session |
| `externalContext` | Môi trường bên ngoài engine flow | Đọc tham số HTTP, request/session/application attributes, thông tin locale, đường dẫn hoặc native request/response khi thực sự cần |

Có thể ghi nhớ theo câu hỏi:

- **Request này đang xử lý điều gì?** Dùng `flowRequestContext`.
- **Lần thực thi flow đang ở đâu và thuộc định nghĩa nào?** Dùng `flowExecutionContext`.
- **Request web hoặc môi trường container cung cấp dữ liệu gì?** Dùng `externalContext`.

Các tên này thường được cung cấp như biến ngầm định trong biểu thức flow. Chúng không phải các biến nghiệp vụ do ứng dụng tự khai báo trong `flowScope`. Cú pháp truy cập thuộc tính và biểu thức cụ thể phụ thuộc expression language, cấu hình và phiên bản Spring Web Flow.

## 2. `flowRequestContext`: ngữ cảnh của request hiện tại

`flowRequestContext` đại diện cho `RequestContext` mà Spring Web Flow tạo và sử dụng trong quá trình xử lý một request. Đây là điểm truy cập thuận tiện khi action cần biết sự kiện nào vừa được gửi, flow đang ở state nào, dữ liệu trong các scope ra sao hoặc cần gọi một service dựa trên ngữ cảnh hiện tại.

Một request có thể mang event như `continue`, `back`, `confirm` hoặc `cancel`. Flow nhận event, đánh giá transition và thực hiện action tương ứng. Request context giúp action đọc event và truy cập các thành phần liên quan trong cùng lần xử lý.

Ví dụ, một action cần ghi nhận event hiện tại cùng state đang hoạt động:

```xml
<action-state id="recordUserAction">
    <evaluate expression="auditService.recordFlowEvent(flowRequestContext)" />
    <transition on="success" to="continueProcess" />
</action-state>
```

Trong Java, action có thể nhận `RequestContext`:

```java
public class AuditActions {

    public Event recordFlowEvent(RequestContext context) {
        String eventId = context.getCurrentEvent().getId();
        String stateId = context.getCurrentState().getId();

        auditService.record(eventId, stateId);
        return new Event(this, "success");
    }
}
```

Đây là ví dụ minh họa cách đọc event và state qua API request context. Việc đăng ký action bean, kiểu trả về và cách tạo `Event` cần phù hợp với phiên bản dự án. Nếu action chỉ cần một vài giá trị, hãy truyền các giá trị đó vào service thay vì để service phụ thuộc toàn bộ `RequestContext`.

### Những dữ liệu thường lấy từ request context

`RequestContext` cung cấp các điểm truy cập hữu ích như:

- Event hiện tại và state hiện tại.
- Flow execution context đang được xử lý.
- External context của request.
- Các scope như `requestScope`, `flashScope`, `viewScope`, `flowScope` và `conversationScope`.
- Message context để thêm hoặc đọc thông báo validation và lỗi hiển thị.
- Các tham số request và thông tin điều phối flow theo API của phiên bản.

Ví dụ, action có thể thêm lỗi nghiệp vụ vào message context để view hiện tại hiển thị cho người dùng. Khi validation thất bại và flow vẫn ở view state, thông báo được gắn vào đúng request context để view render lại. Không nên dùng `on-exit` hoặc một state kết thúc để xử lý lỗi validation cần hiển thị ngay trên form.

Request context có vòng đời gắn với lần xử lý request. Không giữ tham chiếu `RequestContext` trong singleton service, static field, executor chạy nền hoặc object được lưu lâu trong flow scope. Sau khi request hoàn tất, đối tượng context không còn là một nguồn dữ liệu hợp lệ để sử dụng về sau.

## 3. `flowExecutionContext`: thông tin về lần thực thi flow

`flowExecutionContext` cung cấp góc nhìn về execution đang chạy. Nó cho phép tìm hiểu flow definition nào đang được thực thi, execution key là gì, flow session nào đang hoạt động và state hiện tại thuộc flow session đó.

Trong một ứng dụng có subflow, việc phân biệt execution với session rất quan trọng. Một flow execution có thể chứa nhiều flow session theo quan hệ cha-con. Flow cha có thể gọi subflow, subflow thực hiện một phần hành trình rồi trả kết quả cho flow cha. Khi đó, thông tin flow session đang hoạt động giúp xác định state và định nghĩa của phần flow hiện tại.

Ví dụ, một action chẩn đoán có thể ghi nhận định danh execution và flow đang hoạt động:

```java
public void recordExecutionContext(RequestContext context) {
    FlowExecutionContext execution = context.getFlowExecutionContext();
    FlowSession activeSession = execution.getActiveSession();

    String executionKey = execution.getKey().toString();
    String flowId = activeSession.getDefinition().getId();
    String stateId = activeSession.getState().getId();

    logger.debug("Flow execution {}, flow {}, state {}",
            executionKey, flowId, stateId);
}
```

Đoạn mã minh họa các thông tin thường cần quan sát; kiểu và phương thức truy cập cụ thể phải đối chiếu API của phiên bản Spring Web Flow đang dùng. Tránh ghi execution key hoặc dữ liệu có thể được dùng để tiếp tục flow vào log có phạm vi truy cập rộng. Nếu cần correlation ID cho tracing, hãy dùng mã tương quan riêng được quản lý theo chính sách bảo mật.

### Execution context khác với request context

Một execution có thể tồn tại qua nhiều HTTP request. Người dùng có thể nhập form, gửi event `continue`, nhận view kế tiếp rồi gửi event `confirm` ở request sau. Request context được tạo cho từng lần xử lý, còn execution context mô tả lần thực thi flow đang tiếp tục qua những request đó.

Điều này dẫn đến một nguyên tắc: không lưu dữ liệu tạm của một request vào execution context chỉ để giữ nó qua nhiều bước. Dữ liệu nghiệp vụ cần qua nhiều request nên nằm trong scope thích hợp hoặc kho dữ liệu bền vững. Execution context chủ yếu dùng để quan sát và điều phối trạng thái thực thi, không phải một túi chứa dữ liệu tùy ý.

## 4. `externalContext`: môi trường bên ngoài flow

`externalContext` là lớp trừu tượng để flow truy cập môi trường mà request đến từ đó. Với ứng dụng web Spring MVC thông thường, môi trường này thường được triển khai trên Servlet API. Tuy nhiên, việc dùng abstraction của Spring Web Flow giúp flow definition và action ít phụ thuộc trực tiếp vào `HttpServletRequest`, `HttpSession` hoặc `ServletContext`.

External context có thể cung cấp các nhóm thông tin như:

- Request parameters do client gửi lên.
- Request attributes do thành phần web đặt trong request.
- Session attributes gắn với phiên HTTP.
- Application attributes thuộc phạm vi ứng dụng/container.
- Locale, context path, request path và một số thông tin môi trường khác.
- Native request, response, session hoặc context khi cần tích hợp với API đặc thù của container.

Ví dụ, flow có thể đọc một tham số `campaign` để phục vụ việc ghi nhận nguồn truy cập:

```xml
<action-state id="captureCampaign">
    <evaluate expression="externalContext.requestParameterMap.get('campaign')"
              result="requestScope.campaign" />
    <transition on="success" to="showRegistration" />
</action-state>
```

Đoạn biểu thức minh họa việc đọc tham số request qua external context và lưu vào request scope. Cú pháp truy cập map có thể thay đổi theo expression language; hãy xác nhận cấu hình thực tế. Giá trị do client gửi vẫn là dữ liệu không đáng tin cậy: cần kiểm tra độ dài, định dạng và whitelist trước khi dùng, đặc biệt nếu nó ảnh hưởng tới giá, quyền hoặc hành vi nghiệp vụ.

### Request parameters và request attributes không giống nhau

Request parameter thường đến từ query string hoặc form submission. Request attribute được một thành phần phía máy chủ đặt vào request để các thành phần khác cùng request truy cập. Hai loại dữ liệu có nguồn gốc và mức độ tin cậy khác nhau.

Ví dụ:

- `campaign` từ URL là tham số client gửi; không thể tin cậy để cấp quyền hoặc giảm giá.
- Một đối tượng người dùng đã xác thực được filter đặt vào request attribute là dữ liệu phía máy chủ cung cấp, nhưng vẫn phải tuân thủ ranh giới bảo mật và hợp đồng của filter đó.

Đừng dùng request parameter để thay thế dữ liệu đã được xác minh từ cơ sở dữ liệu hoặc security context.

## 5. Truy cập session và application qua external context

External context có thể cung cấp session map và application map để tương tác với thuộc tính trong môi trường web. Đây là các vùng lưu trữ có phạm vi rộng hơn request hiện tại, vì vậy cần dùng có chủ đích.

Ví dụ khái niệm, một action có thể đọc ngôn ngữ giao diện được lưu trong session:

```java
public Locale resolveLocale(ExternalContext externalContext) {
    Object value = externalContext.getSessionMap().get("preferredLocale");
    if (value instanceof Locale) {
        return (Locale) value;
    }
    return externalContext.getLocale();
}
```

Tên phương thức và kiểu trả về trong ví dụ cần khớp phiên bản API. Nếu ứng dụng có cơ chế quản lý locale riêng, nên dùng cơ chế đó thay vì tự tạo thêm một nguồn trạng thái cạnh tranh.

Phân biệt session map của external context với `flowScope`:

| Nơi lưu | Phạm vi chia sẻ | Vòng đời khái quát | Ví dụ |
|---|---|---|---|
| `requestScope` | Một lần xử lý request | Kết thúc cùng request | Giá trị tạm để render view hiện tại |
| `flowScope` | Một flow execution | Trong suốt lần thực thi flow | Bản nháp form nhiều bước |
| `conversationScope` | Conversation gồm flow cha và subflow liên quan | Theo vòng đời conversation | Dữ liệu cần chia sẻ giữa flow cha và flow con |
| HTTP session map | Các request thuộc cùng HTTP session | Đến khi session hết hạn hoặc bị xóa | Locale, tùy chọn giao diện hoặc thông tin phiên phù hợp |
| Application map | Nhiều request và session trong ứng dụng | Theo vòng đời ứng dụng/container | Cấu hình dùng chung hoặc dữ liệu cache có quản lý |

Không lưu bản nháp riêng của một lần thực thi vào session map nếu `flowScope` đã đáp ứng nhu cầu. Session có thể chứa nhiều flow execution, nhiều tab và nhiều request đồng thời; dùng session map cho dữ liệu thay đổi liên tục có thể tạo xung đột giữa các lần thực thi. Application map không phải nơi lưu dữ liệu người dùng hoặc trạng thái flow.

## 6. Khi nào cần native request hoặc response?

`externalContext` có thể cung cấp native request, response hoặc session để tích hợp với thư viện Servlet cụ thể. Đây là lối thoát hữu ích khi cần gọi một API chỉ tồn tại ở container, nhưng làm tăng sự phụ thuộc vào nền tảng web.

Ví dụ, một thư viện cũ chỉ nhận `HttpServletRequest` có thể cần native request. Trước khi dùng, hãy cân nhắc:

- Có thể thay thư viện bằng service nhận dữ liệu độc lập với Servlet API không?
- Có thể lấy thông tin cần thiết qua abstraction của Spring Web Flow không?
- Đối tượng native có chỉ được dùng trong request hiện tại không?
- Việc sử dụng có làm flow khó kiểm thử hoặc khó chạy trong môi trường khác không?

Không lưu native request/response/session vào `flowScope`, `conversationScope`, singleton bean hoặc dữ liệu bền vững. Chúng gắn với vòng đời của container và request, không phải dữ liệu có thể khôi phục qua lần thực thi khác.

## 7. Kết hợp ba đối tượng trong một action

Trong một action thực tế, ba đối tượng có thể bổ sung cho nhau. Ví dụ, người dùng mở một flow đăng ký từ URL có tham số `source`. Action cần đọc tham số từ external context, xác định state và execution để ghi nhận telemetry, rồi dùng request context để truy cập flow scope và lưu dữ liệu cần thiết cho bước tiếp theo.

```java
public class RegistrationActions {

    public Event captureSource(RequestContext requestContext) {
        ExternalContext external = requestContext.getExternalContext();
        FlowExecutionContext execution =
                requestContext.getFlowExecutionContext();

        String source = external.getRequestParameterMap().get("source");
        String flowId = execution.getActiveSession()
                .getDefinition().getId();

        String safeSource = source == null
                ? "direct"
                : source.substring(0, Math.min(source.length(), 40));

        requestContext.getFlowScope().put("registrationSource", safeSource);
        telemetry.recordFlowStart(flowId, safeSource);

        return new Event(this, "success");
    }
}
```

Đây là ví dụ minh họa cách phối hợp API; cần validate/normalize `source` theo quy tắc nghiệp vụ thay vì chỉ cắt độ dài như ví dụ. Nếu telemetry là tác vụ phụ, cần quyết định rõ việc lỗi telemetry có được phép làm flow thất bại hay không. Nếu `source` ảnh hưởng tới ưu đãi hoặc quyền, phải tải và xác minh campaign từ nguồn đáng tin cậy ở service layer.

Trong flow definition:

```xml
<action-state id="captureRegistrationSource">
    <evaluate expression="registrationActions.captureSource(flowRequestContext)" />
    <transition on="success" to="enterRegistrationDetails" />
</action-state>
```

Flow expression gọi action với `flowRequestContext`. Action lấy `externalContext` và `flowExecutionContext` từ request context, sau đó ghi dữ liệu cần dùng vào `flowScope`. Cách tổ chức này giữ flow definition ngắn và đặt logic xử lý trong Java, nơi có thể kiểm thử độc lập.

## 8. Ranh giới bảo mật khi đọc external context

External context phản ánh dữ liệu từ môi trường web, nhưng không làm cho dữ liệu đó tự động đáng tin cậy. Đặc biệt, request parameters, header, cookie và session attributes cần được đánh giá theo nguồn gốc và cách tạo ra.

- **Request parameters:** luôn xem là đầu vào không đáng tin cậy. Kiểm tra định dạng, độ dài, tập giá trị hợp lệ và quyền trên tài nguyên được tham chiếu.
- **Session attributes:** có thể do ứng dụng đặt, nhưng phải kiểm tra kiểu, vòng đời và quyền truy cập. Tránh dùng một thuộc tính session có thể bị client tác động như bằng chứng phân quyền.
- **Application attributes:** là dữ liệu dùng chung; tránh lưu dữ liệu nhạy cảm theo người dùng hoặc object mutable không có đồng bộ.
- **Native request/response:** không đưa nội dung nhạy cảm vào log và không giữ tham chiếu sau request.
- **Flow execution key:** không phải token xác thực hay quyền truy cập. Mọi action vẫn cần kiểm tra danh tính và quyền trên dữ liệu nghiệp vụ.

Nếu flow dùng Spring Security, hãy để cơ chế security quản lý principal và authorization. Không tự suy ra danh tính từ một request parameter hoặc session attribute tùy ý. Mọi thao tác đọc hoặc ghi hồ sơ cần kiểm tra quyền ở service/domain boundary.

## 9. Lỗi thường gặp khi dùng ba context

### Dùng request context như một kho lưu trữ lâu dài

Một action lưu `RequestContext` vào field của singleton bean để dùng ở request sau. Cách làm này vừa sai vòng đời vừa có thể gây race condition giữa người dùng. Chỉ đọc context trong lúc action đang chạy và chuyển các giá trị cần thiết sang DTO hoặc scope phù hợp.

### Nhầm execution context với dữ liệu nghiệp vụ

`flowExecutionContext` cho biết execution đang ở đâu, nhưng không phải nơi lưu bản nháp đơn hàng, hồ sơ hoặc dữ liệu người dùng. Lưu dữ liệu nghiệp vụ trong scope hoặc repository phù hợp; dùng execution context để quan sát và điều phối.

### Dùng session map thay cho flow scope

Session map chia sẻ giữa nhiều flow execution trong cùng session. Nếu hai tab cùng sửa một thuộc tính chung như `currentBooking`, dữ liệu có thể ghi đè lẫn nhau. Dữ liệu thuộc một lần thực thi nên ở `flowScope`.

### Tin tưởng request parameter

Một tham số `customerId` hoặc `price` trong URL không chứng minh người dùng sở hữu khách hàng hoặc được phép dùng mức giá đó. Tải dữ liệu từ nguồn đáng tin cậy và kiểm tra quyền trong service layer.

### Truy cập native API ở quá nhiều nơi

Nếu mọi action đều ép kiểu native request để lấy dữ liệu, flow trở nên gắn chặt với Servlet container và khó kiểm thử. Đóng gói tích hợp ở một adapter hoặc service, chỉ lấy những giá trị cần thiết.

### Log toàn bộ context để debug

Context có thể chứa tham số, session attributes, execution key và dữ liệu nghiệp vụ. Không serialize toàn bộ context hoặc ghi dump vào log. Chọn các trường không nhạy cảm như flow ID, state ID, event ID và correlation ID.

## 10. Kiểm thử các context

Kiểm thử cần xác nhận action đọc đúng nguồn dữ liệu, dùng đúng vòng đời và không rò rỉ giữa các execution. Không chỉ kiểm thử expression chạy thành công; cần thử dữ liệu thiếu, sai kiểu và trạng thái session thay đổi.

| Kịch bản | Điều cần xác minh |
|---|---|
| Request có event hợp lệ | `flowRequestContext` cung cấp event và state dự kiến |
| Request validation lỗi | Message context giữ lỗi cần hiển thị; flow ở đúng view state |
| Flow có subflow đang hoạt động | Execution context xác định đúng active session và flow/state hiện tại |
| Hai execution trong cùng HTTP session | Dữ liệu `flowScope` không bị trộn giữa hai execution |
| Request parameter bị thiếu hoặc sai định dạng | Action dùng giá trị mặc định hoặc trả lỗi theo hợp đồng |
| Session attribute không tồn tại hoặc sai kiểu | Action xử lý an toàn, không ném lỗi ngoài dự kiến |
| Session hết hạn | Không dựa vào dữ liệu session cũ; flow được xử lý theo chính sách hết hạn |
| Native request không khả dụng trong test | Adapter có thể được mock hoặc test qua abstraction phù hợp |

Có thể dùng test support của Spring Web Flow để khởi chạy flow và gửi event, sau đó kiểm tra state và scope. Với action Java, unit test có thể mock `RequestContext`, `ExternalContext` hoặc service phụ thuộc. Khi test session và request maps, tạo các map độc lập cho từng execution để phát hiện lỗi dùng chung dữ liệu ngoài ý muốn.

Ví dụ các điều cần xác minh (mã giả):

```java
// Request có source=partner: giá trị được lưu trong flow scope.
assertThat(flow.currentState()).isEqualTo("enterRegistrationDetails");
assertThat(flow.flowScope().get("registrationSource"))
        .isEqualTo("partner");

// Execution thứ hai không được nhận dữ liệu flow scope của execution thứ nhất.
assertThat(secondFlow.flowScope().contains("registrationSource"))
        .isFalse();
```

Các lời gọi `flow.currentState()` và `flow.flowScope()` là ký hiệu giả lập cho API kiểm thử; hãy dùng API test support của phiên bản dự án. Ngoài kiểm thử flow, nên có kiểm thử service để bảo đảm authorization và validation được thực hiện dù action được gọi từ một đường khác.

## 11. Checklist chọn đúng context

Trước khi viết expression hoặc action, hãy tự hỏi:

1. Tôi cần dữ liệu của request hiện tại, metadata của execution hay dữ liệu từ môi trường web?
2. Dữ liệu có thể tồn tại qua nhiều request không? Nếu có, scope nào phản ánh đúng vòng đời?
3. Dữ liệu đến từ client, ứng dụng hay container? Mức độ tin cậy và kiểm tra cần thiết là gì?
4. Action có cần toàn bộ `RequestContext` hay chỉ một vài giá trị đơn giản?
5. Có thể dùng abstraction của Spring Web Flow thay vì native Servlet API không?
6. Dữ liệu có bị chia sẻ giữa nhiều tab hoặc flow execution trong cùng session không?
7. Có log hoặc lưu giữ tham chiếu context vượt quá vòng đời request không?
8. Kiểm thử đã bao phủ dữ liệu thiếu, session hết hạn, subflow và nhiều execution đồng thời chưa?

Chọn context theo trách nhiệm giúp expression dễ hiểu và tránh vô tình biến session hoặc execution metadata thành kho dữ liệu nghiệp vụ.

## Kết luận

`flowRequestContext` đại diện cho request đang xử lý và cung cấp quyền truy cập tới event, state, scope, message context cùng các context liên quan. `flowExecutionContext` mô tả lần thực thi flow, giúp quan sát định nghĩa, execution key và flow session đang hoạt động. `externalContext` là abstraction cho môi trường bên ngoài như request parameters, request/session/application maps và native web objects.

Hãy dùng request context để xử lý công việc của request hiện tại, execution context để quan sát và điều phối trạng thái flow, external context để đọc môi trường web có kiểm soát. Lưu dữ liệu theo scope có vòng đời phù hợp, xác minh mọi đầu vào từ client và giới hạn việc truy cập native API. Những ranh giới này giúp flow tích hợp tốt với Spring MVC mà vẫn dễ kiểm thử, bảo trì và phục hồi khi request hoặc session gặp lỗi.
