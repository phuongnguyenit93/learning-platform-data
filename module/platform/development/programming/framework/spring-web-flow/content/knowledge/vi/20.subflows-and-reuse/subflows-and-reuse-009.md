# Subflow lồng nhau và khả năng theo dõi trạng thái

Một quy trình nghiệp vụ thường được ghép từ nhiều hành trình nhỏ. Ví dụ, quy trình tiếp nhận hồ sơ có thể gọi một subflow xác minh danh tính; subflow xác minh lại gọi một subflow kiểm tra giấy tờ. Khi mỗi phần có state, event và kết quả riêng, flow cha vẫn điều phối được toàn bộ hành trình mà không phải biết chi tiết từng bước nội bộ.

Trong chương **Subflow và tái sử dụng**, bài này trình bày cách tổ chức subflow lồng nhau và theo dõi trạng thái khi luồng đi qua nhiều cấp. Đây là kỹ thuật quan trọng trong **SPRING_WEB_FLOW**, nơi các hành trình nhiều bước được mô hình hóa bằng state, event, transition và subflow, đồng thời cần kiểm thử và phục hồi khi một nhánh con gặp lỗi.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích cách flow cha gọi subflow và cách một subflow tiếp tục gọi subflow khác.
- Truyền dữ liệu đầu vào, nhận kết quả đầu ra và xử lý outcome của từng cấp.
- Phân biệt flow session, flow execution và conversation trong một cây subflow.
- Theo dõi state hiện tại, transition, thời điểm vào/ra subflow và kết quả hoàn tất.
- Dùng listener của flow execution để ghi trace có cấu trúc.
- Chẩn đoán lỗi định tuyến, mapping dữ liệu và lỗi phát sinh ở cấp lồng nhau.
- Kiểm thử đường đi thành công, từ chối, hủy và lỗi giữa các cấp.

## 1. Mô hình cây subflow

Giả sử hệ thống tiếp nhận hồ sơ có ba phần:

1. **booking** là flow cha, quản lý hành trình tiếp nhận hồ sơ.
2. **identity-check** là subflow xác minh danh tính và điều phối việc kiểm tra giấy tờ.
3. **document-review** là subflow lồng bên trong, chuyên kiểm tra một tài liệu.

Cây gọi có dạng:

~~~mermaid
flowchart TD
    A[booking - Flow cha] --> B[identity-check - Subflow]
    B --> C[document-review - Subflow lồng]
    C --> D[approved]
    C --> E[rejected]
    D --> F[identity-check tiếp tục]
    E --> F
    F --> G[booking tiếp tục]
~~~

Mỗi flow definition có state và transition riêng. Khi flow cha đi vào một **subflow-state**, Spring Web Flow bắt đầu một flow session cho subflow. Flow cha tạm dừng tại subflow-state cho đến khi subflow kết thúc. Nếu subflow đó lại gọi subflow khác, một session lồng nữa được mở. Khi flow con kết thúc, kết quả và output được trả về state cha; flow cha tiếp tục từ transition tương ứng với outcome của flow con.

Subflow lồng nhau vẫn thuộc cùng flow execution/conversation do flow gốc khởi tạo. Chúng không tự tạo một HTTP session mới hoặc yêu cầu trình duyệt khởi chạy một flow gốc khác. Điều này giúp dữ liệu trong conversation scope có thể được chia sẻ theo thiết kế, trong khi flow scope của mỗi flow session vẫn độc lập.

## 2. Flow cha gọi subflow xác minh

Giả sử registry đã đăng ký ba flow ID **booking**, **identity-check** và **document-review** với các định nghĩa tương ứng. Flow cha có thể gọi **identity-check** bằng state sau:

~~~xml
<subflow-state id="verifyIdentity" subflow="identity-check">
    <input name="applicantId"
           value="flowScope.application.applicantId"/>
    <input name="documentId"
           value="flowScope.application.documentId"/>

    <output name="identityStatus"
            value="flowScope.application.identityStatus"/>

    <transition on="verified" to="review"/>
    <transition on="rejected" to="correction"/>
</subflow-state>
~~~

Các mapping có vai trò rõ ràng:

- **input** truyền dữ liệu từ flow cha vào flow con khi subflow bắt đầu.
- **output** nhận giá trị mà flow con xuất ra và ghi vào phạm vi được chỉ định trong flow cha.
- **transition** chọn state tiếp theo của flow cha theo outcome mà subflow trả về.

Trong ví dụ, flow cha truyền mã người nộp hồ sơ và mã tài liệu. Flow con trả về outcome **verified** hoặc **rejected**, đồng thời trả giá trị **identityStatus**. Flow cha có thể tiếp tục đến màn hình rà soát hoặc yêu cầu người dùng bổ sung thông tin.

Nên truyền các giá trị cần thiết một cách tường minh. Subflow không nên phụ thuộc vào tên biến nội bộ hoặc cấu trúc object không được công bố của flow cha. Input/output mapping giúp định nghĩa ranh giới giữa hai flow rõ ràng và giúp kiểm thử subflow độc lập hơn.

## 3. Subflow xác minh gọi tiếp subflow kiểm tra tài liệu

Định nghĩa **identity-check** nhận các input từ flow cha, sau đó gọi **document-review** để xử lý một phần chuyên biệt:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="applicantId"/>
    <input name="documentId"/>

    <subflow-state id="inspectDocument"
                   subflow="document-review">
        <input name="documentId" value="documentId"/>
        <output name="documentStatus"
                value="flowScope.documentStatus"/>

        <transition on="approved" to="verified"/>
        <transition on="rejected" to="rejected"/>
    </subflow-state>

    <end-state id="verified">
        <output name="identityStatus" value="'VERIFIED'"/>
    </end-state>

    <end-state id="rejected">
        <output name="identityStatus" value="'REJECTED'"/>
    </end-state>
</flow>
~~~

Ở đây, **identity-check** không tự xử lý nội dung giấy tờ. Nó gọi subflow chuyên trách, nhận kết quả **documentStatus**, rồi quyết định outcome của chính nó. Flow cha chỉ cần biết kết quả xác minh tổng thể, không phải biết các bước nội bộ của việc kiểm tra tài liệu.

Định nghĩa **document-review** có thể đơn giản như sau:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="documentId"/>

    <view-state id="inspect" view="documents/inspect">
        <transition on="approve" to="approved"/>
        <transition on="reject" to="rejected"/>
    </view-state>

    <end-state id="approved">
        <output name="documentStatus" value="'APPROVED'"/>
    </end-state>

    <end-state id="rejected">
        <output name="documentStatus" value="'REJECTED'"/>
    </end-state>
</flow>
~~~

Các outcome **approved** và **rejected** là ID của end-state trong flow con. Khi end-state được kích hoạt, flow con kết thúc và outcome trở thành event mà subflow-state ở cấp gọi nhận được. Output **documentStatus** được ánh xạ về **flowScope.documentStatus** của flow **identity-check**.

Flow cha nhận một kết quả khác ở cấp nghiệp vụ: **verified** hoặc **rejected**. Cách phân lớp outcome này tránh để flow cha phải hiểu event chi tiết như **approve** hoặc **reject** của màn hình kiểm tra giấy tờ.

## 4. Dữ liệu và trạng thái qua nhiều cấp

Mỗi flow session có **flowScope** riêng. Vì vậy, **flowScope.documentStatus** trong **identity-check** là dữ liệu của flow đó; nó không tự động trở thành biến cùng tên trong flow cha. Muốn đưa kết quả ra ngoài, hãy khai báo output ở end-state và mapping output trong subflow-state của cấp gọi.

| Phạm vi | Ai sử dụng | Ví dụ |
|---|---|---|
| **flowScope** của booking | Flow cha | Hồ sơ tổng thể, state nghiệp vụ hiện tại, kết quả xác minh cuối cùng. |
| **flowScope** của identity-check | Subflow xác minh | Kết quả kiểm tra từng bước, dữ liệu trung gian của xác minh. |
| **flowScope** của document-review | Subflow tài liệu | Lựa chọn approve/reject và metadata riêng của lần kiểm tra. |
| **conversationScope** | Flow gốc và các subflow trong cùng conversation | Correlation ID nghiệp vụ hoặc ngữ cảnh cần chia sẻ ở nhiều cấp. |
| **viewScope** | View-state đang hoạt động | Tab đang chọn, bộ lọc và dữ liệu hiển thị tạm thời. |

Nếu một dữ liệu chỉ cần truyền một chiều, input/output mapping thường là lựa chọn rõ ràng nhất. Nếu nhiều cấp thật sự cần truy cập cùng một ngữ cảnh trong toàn conversation, có thể cân nhắc **conversationScope**. Không nên dùng conversation scope như kho chứa mọi biến của mọi subflow, vì điều đó làm ranh giới trách nhiệm mờ đi và khiến việc kiểm thử khó hơn.

Cũng không nên lưu lịch sử trace không giới hạn trong flow scope. Flow scope phục vụ trạng thái nghiệp vụ có vòng đời theo flow; log và lịch sử quan sát nên được ghi vào hệ thống logging, tracing hoặc metrics bên ngoài.

## 5. Theo dõi trạng thái của cây subflow

Khi flow chỉ có một cấp, việc đọc state hiện tại trong log thường khá đơn giản. Với subflow lồng nhau, chỉ ghi tên state như **inspect** là chưa đủ, vì có thể có nhiều flow cùng khai báo state ID đó.

Mỗi bản ghi theo dõi nên giúp xác định ít nhất:

- Flow gốc và flow đang hoạt động.
- State hiện tại.
- Cấp gọi hoặc đường dẫn lồng nhau.
- Transition/event vừa được xử lý.
- Outcome khi subflow kết thúc.
- Correlation ID để nối các request thuộc cùng hành trình.
- Thời điểm và thời lượng của bước nếu cần đo hiệu năng.

Một đường đi có thể được biểu diễn thành:

~~~text
booking
  └── verifyIdentity [identity-check]
        └── inspectDocument [document-review]
              └── approved
        └── verified
  └── review
  └── completed
~~~

Khi ghi log, hãy phân biệt **flow execution** với các **flow session** trong stack. Execution là đơn vị thực thi tổng thể; session cho biết flow definition nào đang hoạt động tại một cấp. Khi subflow bắt đầu, session con được mở; khi nó kết thúc, session đó được đóng và session cha tiếp tục.

### Dùng FlowExecutionListener

Spring Web Flow cung cấp **FlowExecutionListener** để quan sát vòng đời của flow execution. Listener có thể nhận các callback khi session bắt đầu/kết thúc, state được vào/ra, transition được thực thi, request được xử lý, execution pause/resume hoặc phát sinh exception.

Có thể xây dựng listener để ghi sự kiện theo cấu trúc thay vì ghi một chuỗi log khó phân tích. Pseudocode minh họa các điểm cần quan sát:

~~~text
onSessionStarted:
    record(flowId, sessionStarted, parentFlowPath)

onStateEntered:
    record(activeFlowId, stateId, entered)

onTransitionExecuted:
    record(activeFlowId, sourceState, eventId, targetState)

onSessionEnded:
    record(activeFlowId, outcome, outputsSummary)

onExceptionThrown:
    record(activeFlowId, currentState, exceptionType, failure)
~~~

Đăng ký listener với **FlowExecutor** trong cấu hình Web Flow của ứng dụng. Với Java configuration, listener được thêm vào cấu hình flow executor; với XML configuration, khai báo listener trong phần cấu hình executor tương ứng. Tên callback cụ thể và cách đăng ký cần khớp phiên bản Spring Web Flow đang sử dụng.

Không nên dùng listener để thay đổi luồng nghiệp vụ hoặc sửa scope tùy tiện. Listener có trách nhiệm quan sát, đo thời gian và ghi nhận sự kiện. Các quyết định như từ chối hồ sơ, yêu cầu bổ sung giấy tờ hoặc chuyển state phải nằm trong flow definition và action nghiệp vụ.

### Ví dụ bản ghi trace

Một bản ghi có cấu trúc có thể có dạng:

~~~json
{
  "correlationId": "req-8f31",
  "rootFlowId": "booking",
  "activeFlowId": "document-review",
  "flowPath": [
    "booking",
    "identity-check",
    "document-review"
  ],
  "stateId": "inspect",
  "eventId": "approve",
  "targetState": "approved",
  "eventType": "transition-executed",
  "durationMs": 42
}
~~~

Các giá trị trên chỉ minh họa. Trong hệ thống thực, correlation ID nên được tạo hoặc tiếp nhận ở tầng request và truyền xuyên suốt các request của cùng flow execution. Nếu cần liên kết với execution key, hãy dùng cách ghi nhận an toàn theo chính sách bảo mật của ứng dụng; không ghi nguyên URL có token hoặc dữ liệu đầu vào nhạy cảm vào log công khai.

## 6. Theo dõi outcome và đo hiệu năng

Ngoài trace từng transition, hãy đo các chỉ số ở cấp subflow:

| Chỉ số | Ý nghĩa |
|---|---|
| Số lần gọi subflow | Biết subflow nào được sử dụng thường xuyên. |
| Số lần hoàn tất theo outcome | Phân biệt thành công, từ chối và hủy. |
| Tỷ lệ exception | Phát hiện subflow thường xuyên lỗi. |
| Thời lượng subflow | Xác định cấp nào làm hành trình chậm. |
| Số lần retry hoặc quay lại state | Nhận diện trải nghiệm bị mắc kẹt hoặc lỗi dữ liệu. |

Các metric nên dùng nhãn có số lượng giá trị giới hạn như flow ID, subflow ID, outcome và loại lỗi. Không dùng applicant ID, document ID, email hoặc execution key làm metric label vì số lượng giá trị có thể tăng không giới hạn và có thể chứa dữ liệu nhạy cảm. Những định danh cụ thể phù hợp hơn với log có kiểm soát quyền truy cập.

Khi đo thời gian, bắt đầu đồng hồ lúc session subflow được mở và kết thúc khi session đó kết thúc. Nếu một subflow gọi subflow khác, cần quyết định rõ metric của flow cha có bao gồm thời gian chờ subflow con hay không. Có thể đo cả thời gian tổng của subflow cha và thời gian riêng từng subflow con để tìm đúng nút thắt.

## 7. Xử lý lỗi trong subflow lồng nhau

Lỗi có thể xảy ra ở bất kỳ cấp nào: flow cha truyền thiếu input, registry không tìm thấy flow con, action trong subflow ném exception hoặc view-state không nhận được event phù hợp.

| Biểu hiện | Nguyên nhân cần kiểm tra |
|---|---|
| Không tìm thấy subflow | Flow ID trong thuộc tính **subflow** không khớp định danh đã đăng ký trong FlowDefinitionRegistry. |
| Flow con thiếu dữ liệu | Tên input hoặc biểu thức mapping sai; input chưa được khai báo trong flow con. |
| Flow cha không nhận được kết quả | End-state không xuất đúng output hoặc output mapping ở subflow-state sai tên. |
| Transition cha không chạy | ID outcome của end-state không khớp với event được khai báo trong transition của subflow-state. |
| State log bị nhập nhằng | Chỉ ghi state ID mà không ghi active flow ID hoặc flow path. |
| Flow bị dừng ở cấp con | Action lỗi, exception chưa được xử lý hoặc subflow chưa đi đến end-state. |
| Dữ liệu cấp cha bị thay đổi ngoài dự kiến | Dùng chung object mutable qua conversation scope mà không kiểm soát quyền cập nhật. |

Không nên bắt mọi exception rồi trả outcome thành công giả. Nếu lỗi có thể phục hồi, hãy chuyển đến state xử lý lỗi hoặc yêu cầu thử lại với thông báo rõ ràng. Nếu lỗi không thể phục hồi, ghi nhận exception, giải phóng tài nguyên tạm và để flow kết thúc theo chính sách đã thiết kế.

Với nghiệp vụ có side effect như thanh toán hoặc ghi hồ sơ, hãy bảo đảm action có tính lặp an toàn. Một request có thể bị gửi lại khi mạng chập chờn hoặc người dùng thử lại sau lỗi. Flow trace giúp nhận diện việc lặp, nhưng tính idempotent phải được bảo đảm ở tầng nghiệp vụ và lưu trữ.

## 8. Kiểm thử flow lồng nhau và trace

Kiểm thử cần xác nhận cả kết quả nghiệp vụ lẫn thứ tự session/state. Không chỉ kiểm tra rằng flow cha đến được end-state, vì một subflow có thể đã trả kết quả sai mà flow cha vẫn tiếp tục.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Giấy tờ được duyệt | document-review kết thúc với **approved**, identity-check nhận kết quả và trả **verified**, booking đi đến review. |
| Giấy tờ bị từ chối | document-review trả **rejected**, identity-check trả **rejected**, booking đi đến correction. |
| Subflow bị hủy | Outcome hủy được xử lý rõ ràng ở cấp gọi; dữ liệu tạm được dọn theo chính sách. |
| Thiếu input mapping | Flow con không chạy với dữ liệu sai; lỗi được phát hiện ở ranh giới gọi. |
| Thiếu output mapping | Kiểm thử phát hiện flow cha không nhận được giá trị mong đợi. |
| Exception trong subflow lồng | Listener ghi nhận flow và state phát sinh lỗi; flow cha áp dụng chính sách lỗi. |
| Nhiều execution đồng thời | Trace và dữ liệu của mỗi flow không bị trộn lẫn. |
| Kết thúc flow gốc | Các session con đã kết thúc; tài nguyên và dữ liệu tạm được giải phóng. |

Trong kiểm thử tích hợp, hãy chạy một flow cha từ đầu đến cuối, giữ cùng session/cookie và URL execution giữa các request. Thu thập trace từ listener rồi xác nhận thứ tự mở/đóng session, state entered/exited và outcome của từng subflow. Nên có assertion cho cả nhánh thành công, từ chối, hủy và exception.

Có thể kiểm thử listener riêng bằng cách cung cấp implementation ghi sự kiện vào một bộ thu nhận trong bộ nhớ. Khi test hoàn tất, so sánh chuỗi sự kiện mong đợi với trace thực tế. Cách này giúp phát hiện lỗi mapping và lỗi thứ tự state mà assertion chỉ kiểm tra view cuối cùng có thể bỏ sót.

## 9. Nguyên tắc tổ chức và quan sát lâu dài

Hãy chia flow theo ranh giới nghiệp vụ có thể tái sử dụng. Flow cha điều phối hành trình tổng thể và quyết định bước tiếp theo dựa trên outcome; subflow xử lý một trách nhiệm cụ thể và công bố input/output rõ ràng. Khi cần lồng subflow, hãy giữ mỗi cấp có mục tiêu và kết quả dễ hiểu.

Theo dõi trạng thái bằng FlowExecutionListener và log có cấu trúc. Luôn ghi active flow ID cùng state ID để tránh nhầm state trùng tên giữa các cấp. Dùng correlation ID để nối request, đo thời lượng ở từng cấp và ghi nhận outcome/exception. Tránh lưu trace dài hạn trong flow scope hoặc đưa dữ liệu cá nhân vào log.

Khi thiết kế đúng ranh giới, một flow cha có thể gọi nhiều subflow lồng nhau mà vẫn theo dõi được đường đi, kết quả và lỗi của từng cấp. Điều này giúp hành trình web nhiều bước dễ kiểm thử, dễ vận hành và có thể mở rộng bằng cách tái sử dụng các quy trình con mà không làm flow chính trở nên khó đọc.
