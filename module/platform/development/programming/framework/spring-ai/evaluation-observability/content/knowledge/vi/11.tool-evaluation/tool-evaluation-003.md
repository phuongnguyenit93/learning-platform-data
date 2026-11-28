# Kiểm chứng kết quả nghiệp vụ bằng dữ liệu hoặc trạng thái thực tế

Trong một ứng dụng Spring AI có gọi công cụ, mô hình ngôn ngữ có thể chọn đúng công cụ, truyền đối số hợp lệ và nhận phản hồi thành công nhưng **yêu cầu nghiệp vụ vẫn chưa hoàn thành**. Một API có thể trả về “đã tiếp nhận” trong khi giao dịch còn chờ xử lý; một công cụ có thể trả dữ liệu từ bộ nhớ đệm trong khi trạng thái thực đã thay đổi; một trợ lý có thể tuyên bố “đã hủy đơn” dù hệ thống quản lý đơn hàng vẫn hiển thị “đang xử lý”.

Vì vậy, đánh giá tool calling phải đi xa hơn việc kiểm tra JSON, trạng thái HTTP hay câu trả lời của mô hình. Ta cần so sánh **kết quả mà nghiệp vụ thực sự cần** với **bằng chứng đáng tin cậy về dữ liệu hoặc trạng thái cuối**. Bài học này trình bày cách thiết kế bằng chứng, oracle kiểm thử, bộ dữ liệu, công cụ giả lập và quan sát thực thi để kiểm chứng kết quả của ứng dụng Spring AI.

Đây là nội dung thuộc chương **Đánh giá công cụ** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Các kỹ thuật được kết nối với đánh giá relevance, fact checking, RAG, metrics, traces, chi phí và độ trễ để phát hiện suy giảm chất lượng qua những phiên bản prompt, model và pipeline khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao lời gọi công cụ thành công không đồng nghĩa với kết quả nghiệp vụ đúng.
2. Xác định trạng thái đầu, trạng thái đích, điều kiện trước/sau và các bất biến cần giữ nguyên của một tác vụ.
3. Chọn nguồn dữ liệu có thẩm quyền (source of truth) để làm bằng chứng, phân biệt với lời xác nhận của mô hình hoặc phản hồi trung gian.
4. Xây dựng bộ kiểm tra tự động đối chiếu dữ liệu trước/sau, bao gồm tiến trình bất đồng bộ, eventual consistency và lỗi một phần.
5. Sử dụng công cụ giả lập trong Spring AI để đo sự khác nhau giữa **request được chấp nhận**, **thao tác thực thi** và **nghiệp vụ thực sự hoàn tất**.
6. Báo cáo tỷ lệ thành công nghiệp vụ, tỷ lệ tuyên bố thành công sai, lỗi bất biến, độ trễ xác minh, chi phí trên một kết quả đã kiểm chứng và dấu vết phục vụ phân tích lỗi.

## 2. Các tầng “thành công” trong luồng gọi công cụ

Hãy xét yêu cầu: “Hủy đơn A123 giúp tôi và cho biết đã hủy xong chưa”.

Mô hình có thể gọi đúng **request_order_cancellation(orderId=A123)**. Công cụ trả về **ACCEPTED** và mô hình trả lời “Đã hủy xong”. Nhưng hệ thống quản lý đơn hàng chỉ mới ghi nhận yêu cầu, chưa chuyển trạng thái đơn từ **PROCESSING** sang **CANCELLED**. Khi mục tiêu được định nghĩa là *đơn đã hủy hoàn tất*, ca này phải bị chấm **chưa đạt**, bất kể lời gọi công cụ thành công.

| Tầng | Câu hỏi | Bằng chứng thường có | Đã đủ kết luận nghiệp vụ? |
| --- | --- | --- | --- |
| Quyết định gọi | Có cần gọi công cụ không? | Tool request trong trace | Chưa |
| Lựa chọn và đối số | Gọi đúng tool, đúng đối tượng chưa? | Tên tool, JSON args, quyền truy cập | Chưa |
| Chấp nhận yêu cầu | Backend có tiếp nhận yêu cầu không? | HTTP 202, message ACCEPTED, mã tác vụ | Chưa, nếu mục tiêu là kết quả cuối |
| Thực thi kỹ thuật | Dịch vụ đã chạy và trả mã thành công chưa? | Log thực thi, HTTP 200, transaction result | Chưa chắc |
| **Trạng thái nghiệp vụ** | Dữ liệu/thực thể đã đạt trạng thái đích chưa? | Truy vấn source of truth, bản ghi giao dịch | Có, khi đúng phạm vi và thời hạn kiểm chứng |
| **Câu trả lời có căn cứ** | Trợ lý có mô tả chính xác trạng thái đã kiểm chứng không? | Đối chiếu câu trả lời với bằng chứng | Cần đánh giá riêng |

Một phản hồi HTTP 200 hoặc 202 chỉ có ý nghĩa theo **hợp đồng API**. HTTP 200 có thể là dữ liệu đã xử lý; HTTP 202 thường thể hiện yêu cầu đã được tiếp nhận để xử lý tiếp. Không suy luận từ mã giao thức sang “đã hoàn tất” nếu hợp đồng không đảm bảo điều đó.

### Ba trạng thái đánh giá nên phân biệt

- **VERIFIED_SUCCESS:** có đủ bằng chứng rằng điều kiện nghiệp vụ đã thỏa mãn trong phạm vi và thời hạn quy định.
- **VERIFIED_FAILURE:** có bằng chứng điều kiện không thỏa mãn, bị từ chối, vi phạm bất biến hoặc thất bại trong thời hạn theo hợp đồng.
- **UNKNOWN / PENDING:** chưa đủ bằng chứng để kết luận; có thể đang chờ xử lý, thiếu nguồn xác minh hoặc hết thời gian quan sát nhưng SLA chưa hết.

Không ép tất cả trạng thái chưa biết thành thất bại, và càng không coi **không thấy lỗi** là thành công. Trong một phép kiểm thử đã quy định deadline rõ ràng, trạng thái chờ quá deadline có thể được tính là **vi phạm SLA**, nhưng vẫn cần lưu loại lỗi chính xác để phân tích.

## 3. Bắt đầu từ hợp đồng kết quả nghiệp vụ

Trước khi viết một assertion, hãy xác định **người dùng muốn hoàn thành điều gì**. Hai yêu cầu có thể dùng cùng một tool nhưng khác tiêu chí đạt:

| Yêu cầu người dùng | Điều kiện để đạt | Điều chưa đủ |
| --- | --- | --- |
| “Tạo yêu cầu hoàn tiền” | Có bản ghi yêu cầu hoàn tiền hợp lệ, gắn đúng đơn, đúng số tiền | Chỉ có câu trả lời “đã tạo” |
| “Đã nhận được tiền hoàn chưa?” | Trạng thái thanh toán/đối soát chứng minh tiền đã được hoàn theo hợp đồng | Yêu cầu hoàn tiền đang PENDING |
| “Hủy xong đơn A123” | Đơn A123 thực sự ở trạng thái CANCELLED hợp lệ | Cổng đơn hàng báo ACCEPTED |
| “Giữ chỗ 2 sản phẩm” | Có reservation hợp lệ cho đúng SKU, số lượng và thời hạn | Chỉ giảm số tồn kho hiển thị tạm thời |
| “Gửi email thông báo” | Theo chính sách sản phẩm: bản ghi gửi đã được provider chấp nhận hoặc có bằng chứng giao đến nơi nhận | Mô hình tuyên bố “đã gửi” |
| “Cập nhật lịch hẹn lúc 9 giờ” | Lịch hẹn đúng ID đã lưu giờ mới tại nguồn dữ liệu chính | Tool nhận yêu cầu nhưng giờ cũ vẫn tồn tại |
| “Trả lời dựa trên chính sách mới nhất” | Phát biểu được hỗ trợ bởi phiên bản tài liệu có thẩm quyền tại thời điểm tham chiếu | Có một đoạn truy xuất trông có vẻ liên quan |

**Chú ý:** “đã gửi email” có thể được sản phẩm định nghĩa là **nhà cung cấp tiếp nhận** hoặc **đã giao thành công**. Hai mức này phải được đặt tên rõ trong hợp đồng. Không đặt oracle theo kỳ vọng quá mạnh hoặc quá yếu so với mục tiêu thực.

### Mô hình hóa trạng thái

Với ví dụ hủy đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING
    PROCESSING --> CANCELLATION_REQUESTED: Yêu cầu được tiếp nhận
    CANCELLATION_REQUESTED --> CANCELLED: Hủy thành công
    CANCELLATION_REQUESTED --> CANCELLATION_REJECTED: Không được hủy
    PROCESSING --> SHIPPED: Đơn được chuyển giao
    SHIPPED --> DELIVERED: Đã giao
    CANCELLED --> [*]
    CANCELLATION_REJECTED --> [*]
    DELIVERED --> [*]
~~~

Đây là **state machine minh họa**, không phải danh sách trạng thái bắt buộc của Spring AI hay của một hệ thống thương mại điện tử cụ thể. Một ứng dụng thực tế có thể có các nhánh hoàn hàng, hoàn tiền hoặc trạng thái trung gian khác.

Từ sơ đồ, có thể viết hợp đồng cho yêu cầu “hủy hoàn tất”:

- **Tiền điều kiện:** đơn A123 tồn tại, người dùng được phép thao tác, trạng thái cho phép hủy theo quy tắc hiện hành.
- **Hành động được phép:** chỉ gửi yêu cầu hủy cho A123, không tác động đơn khác.
- **Hậu điều kiện thành công:** trạng thái chuẩn của A123 là CANCELLED trước thời hạn theo hợp đồng.
- **Bất biến:** không thay đổi ID khách hàng, tổng tiền hay trạng thái của đơn khác; không có yêu cầu hủy trùng ngoài chính sách retry.
- **Đầu ra cho người dùng:** chỉ nói “đã hủy xong” khi có bằng chứng tương ứng; nếu còn chờ, phải nói rõ đang chờ.

Một trường hợp quan trọng là **đạt trạng thái đích nhưng sai đường đi**. Ví dụ đơn đã CANCELLED từ trước, mô hình vẫn gọi lại thao tác hủy gây tác động phụ. Phép đo hậu điều kiện có thể đạt, trong khi **chất lượng điều phối** vẫn sai; cần chấm hai tiêu chí độc lập.

## 4. Xác định nguồn sự thật và chất lượng bằng chứng

**Source of truth** là nơi có thẩm quyền xác nhận một sự thật nghiệp vụ cụ thể. Nó có thể là bảng giao dịch chính, sổ cái, hệ thống vận hành đơn hàng, event log được xác nhận hoặc API đọc trạng thái có cam kết về tính nhất quán.

Nguồn sự thật tùy thuộc loại kết quả:

| Nghiệp vụ | Bằng chứng mạnh hơn | Bằng chứng không nên dùng một mình |
| --- | --- | --- |
| Hủy đơn | Trạng thái đơn đã lưu tại hệ thống quản lý đơn; sự kiện hoàn tất có định danh | Lời model, response ACCEPTED |
| Hoàn tiền | Ledger/đối soát thanh toán; trạng thái thanh toán cuối | Chỉ mã yêu cầu hoàn tiền |
| Tạo lịch | Bản ghi lịch theo ID tại hệ thống đặt lịch | Văn bản model vừa sinh |
| Giữ hàng | Bản ghi reservation còn hiệu lực gắn đúng SKU và số lượng | Lời hứa “đã giữ hàng” |
| Gửi thông báo | Trạng thái gửi/giao do hệ thống gửi thông báo ghi nhận theo định nghĩa của sản phẩm | Thông báo đã nằm trong hàng đợi |
| Tra cứu chính sách | Tài liệu có thẩm quyền, phiên bản và ngày hiệu lực hợp lệ | Chỉ đoạn model trích dẫn mà không có nguồn |

Một trình tự bằng chứng thông thường:

1. **Lời tự thuật của mô hình** — độ tin cậy thấp, chỉ là nội dung cần kiểm chứng.
2. **Response công cụ** — có ích nhưng có thể chỉ là trạng thái trung gian, bị cache hoặc sai nghiệp vụ.
3. **Truy vấn đọc độc lập** từ nguồn có thẩm quyền — mạnh hơn khi có thông tin phiên bản và thời điểm.
4. **Sự kiện hoặc bản ghi giao dịch bền vững có định danh** — hữu ích để đối chiếu ai đã thay đổi gì, khi nào, và kết quả có hoàn tất không.

Không phải lúc nào một loại bằng chứng cũng mạnh hơn loại còn lại. Ví dụ sổ cái có thể xác nhận giao dịch đã ghi nhận, còn thông báo bên ngân hàng xác nhận thời điểm thực nhận. Hãy chọn bằng chứng theo **đúng hậu điều kiện**.

### Metadata của bằng chứng

Mỗi bản kiểm chứng nên lưu:

- **Entity ID:** đối tượng nghiệp vụ được kiểm chứng, chẳng hạn mã đơn hoặc request ID.
- **Source:** tên hệ thống hoặc bảng dữ liệu có thẩm quyền.
- **Observed state/value:** trạng thái/giá trị thực tế.
- **As-of / observed_at:** mốc thời gian dữ liệu đại diện và thời điểm đọc.
- **Revision / event ID:** phiên bản hoặc sự kiện liên quan nếu có.
- **Consistency guarantee:** đọc từ primary, replica, cache hay luồng sự kiện; độ trễ cập nhật đã biết.
- **Confidence/availability:** nguồn có đầy đủ, đúng quyền và sẵn sàng không.

Nếu ứng dụng dùng replica có độ trễ vài giây, một lần đọc trả trạng thái cũ **chưa đủ kết luận thất bại ngay**. Ngược lại, một dữ liệu cache báo CANCELLED từ ngày hôm qua không được dùng để chứng minh một thao tác vừa thực hiện đã thành công.

## 5. Xây dựng oracle nghiệp vụ

**Oracle** là quy tắc xác định một kết quả có đạt kỳ vọng hay không. Nó phải độc lập với lời giải thích của mô hình và đủ cụ thể để có thể kiểm tra.

Một oracle tốt cần năm thành phần:

1. **Trạng thái đầu / snapshot trước hành động.** Ghi đúng đối tượng, phiên bản, quyền và các trường quan trọng.
2. **Hậu điều kiện cần đạt.** Xác định chính xác trạng thái cuối, giá trị, dấu thời gian hoặc sự kiện.
3. **Bất biến và giới hạn tác động.** Xác minh không sửa ngoài phạm vi, không nhân đôi bản ghi, không sai đơn vị hoặc sai người nhận.
4. **Cửa sổ quan sát.** Có thể kiểm tra ngay, hoặc chờ đến deadline khi nghiệp vụ bất đồng bộ.
5. **Kết quả ba trạng thái.** VERIFIED_SUCCESS, VERIFIED_FAILURE hoặc PENDING/UNKNOWN kèm lý do.

Ví dụ hợp đồng JSON do dự án tự định nghĩa:

~~~json
{
  "case_id": "CANCEL-001",
  "objective": "CANCEL_ORDER_COMPLETED",
  "subject": {"orderId": "A123"},
  "preconditions": {
    "initialStatus": "PROCESSING",
    "authorized": true
  },
  "expected": {
    "status": "CANCELLED",
    "maxCancellationRequests": 1,
    "unrelatedOrdersMustRemainUnchanged": true
  },
  "verification": {
    "source": "order-system-primary",
    "eventualConsistencyAllowed": true,
    "deadlineSeconds": 30
  }
}
~~~

Đây **không phải schema mặc định của Spring AI**. Nó minh họa cách viết hợp đồng kiểm thử riêng, cố định kỳ vọng trước khi chạy mô hình.

### Phân biệt trạng thái và thay đổi

Chỉ kiểm tra **status == CANCELLED** có thể tạo kết quả giả nếu đơn đã bị hủy từ trước. Để chứng minh tác động do lần chạy hiện tại gây ra, hãy đối chiếu:

- Snapshot trước và sau: **PROCESSING → CANCELLED**.
- Operation ID hoặc idempotency key: một thao tác cụ thể đã được chấp nhận.
- Event ID và thời gian cập nhật: bản ghi thay đổi tương ứng với thao tác.
- Số lần thực thi và các đối tượng khác: không có tác động ngoài dự kiến.

Với tác vụ chỉ đọc, không nhất thiết có thay đổi trạng thái; oracle lúc này kiểm tra **giá trị trả về so với dữ liệu chuẩn ở thời điểm xác định**, cùng quyền truy cập và độ mới.

### Đánh giá bất biến âm tính

Không chỉ kiểm tra rằng “điều tốt đã xảy ra”; phải kiểm tra rằng “điều cấm không xảy ra”:

| Trường hợp | Bất biến cần kiểm tra |
| --- | --- |
| Người dùng chưa xác nhận hoàn tiền | Không có bản ghi yêu cầu hoàn tiền mới |
| Người dùng không có quyền sửa đơn B456 | Không có thay đổi trên B456 |
| Hủy đơn A123 | Không sửa A132 hoặc đơn thuộc tenant khác |
| Retry thao tác tạo giao dịch | Không có hai giao dịch tài chính cho một yêu cầu hợp lệ |
| Truy xuất RAG có phân quyền | Không đọc/đưa vào câu trả lời tài liệu ngoài quyền truy cập |

Một ca có thể đạt hậu điều kiện chính nhưng vẫn **FAIL do vi phạm bất biến nghiêm trọng**.

## 6. Xây dựng tập dữ liệu kiểm chứng

Tập đánh giá cần bao gồm **cả trường hợp thành công, thất bại có chủ đích, trạng thái chờ và vi phạm quyền**. Không chỉ lưu câu hỏi rồi dùng mô hình khác chấm câu trả lời.

Các trường nên có trong mỗi test case:

- **case_id, business_goal:** định danh và mục tiêu nghiệp vụ cần xác minh.
- **user_request, conversation_context:** yêu cầu và ngữ cảnh hội thoại cần thiết.
- **fixture / initial_state:** dữ liệu trước khi chạy, trong môi trường thử nghiệm có thể tái lập.
- **available_tools, permissions:** công cụ và quyền thực sự được cấp.
- **expected_outcome:** các hậu điều kiện và bất biến.
- **verification_source, deadline:** nguồn sự thật, thời gian và chính sách trạng thái chờ.
- **allowed_assistant_claims:** phát biểu được phép ở từng trạng thái, ví dụ “đã tiếp nhận” hay “đã hoàn tất”.
- **severity:** mức độ rủi ro khi kết quả sai hoặc trợ lý tuyên bố quá mức.

Ví dụ JSON Lines (mỗi dòng một ca):

~~~json
{"case_id":"CANCEL-01","user":"Hủy xong đơn A123 giúp tôi","initial":{"A123":"PROCESSING"},"tool_behavior":"ACCEPTED_THEN_CANCELLED","expected":{"final_state":{"A123":"CANCELLED"},"max_requests":1},"verification":{"source":"order-primary","deadline_seconds":30},"severity":"high"}
{"case_id":"CANCEL-02","user":"Gửi yêu cầu hủy đơn A123","initial":{"A123":"PROCESSING"},"tool_behavior":"ACCEPTED_PENDING","expected":{"request_exists":true,"immediate_state":{"A123":"CANCELLATION_REQUESTED"},"assistant_must_not_claim":"CANCELLED"},"verification":{"source":"order-primary","deadline_seconds":5},"severity":"medium"}
{"case_id":"REFUND-01","user":"Tạo yêu cầu hoàn 150000 VND cho A123","initial":{"refundRequests":0},"tool_behavior":"CREATE_REQUEST","expected":{"refund_request":{"orderId":"A123","amount":"150000","currency":"VND","status":"PENDING"},"request_count":1},"verification":{"source":"refund-primary"},"severity":"high"}
{"case_id":"REFUND-02","user":"Xác nhận tiền hoàn đã về chưa","initial":{"refundStatus":"PENDING"},"tool_behavior":"READ_ONLY","expected":{"no_mutation":true,"assistant_must_not_claim":"SETTLED"},"verification":{"source":"payment-ledger"},"severity":"critical"}
{"case_id":"AUTH-01","user":"Hủy đơn B456 của người khác","initial":{"B456":"PROCESSING"},"context":{"authorized_order_ids":["A123"]},"expected":{"final_state":{"B456":"PROCESSING"},"no_cancellation_request_for":"B456"},"verification":{"source":"order-primary"},"severity":"critical"}
~~~

Các giá trị **tool_behavior** là cơ chế dựng fixture giả lập, không phải kết quả đo được từ Spring AI. Trước mỗi lần chạy, cần reset môi trường, giữ cùng phiên bản nguồn và công cụ; nếu dùng dữ liệu thật đang biến động, phải ghi snapshot hoặc mô phỏng lại một môi trường nhất quán.

### Các lớp tình huống cần bao phủ

| Nhóm ca | Điều cần phát hiện |
| --- | --- |
| Thành công đồng bộ | Hậu điều kiện đúng ngay sau công cụ |
| Chấp nhận bất đồng bộ | Tool trả ACCEPTED nhưng kết quả đang PENDING |
| Lỗi kỹ thuật | Timeout, lỗi mạng, thiếu quyền, công cụ trả lỗi |
| Lỗi nghiệp vụ | Hết hàng, đơn đã giao, giao dịch bị từ chối |
| Dữ liệu cũ | Cache/replica trả trạng thái khác primary |
| Thực thi một phần | Một trong nhiều bước hoàn tất, bước khác thất bại |
| Gọi lặp | Hai thao tác giống nhau do retry hoặc mất kết quả |
| Sai đối tượng | Đạt kết quả với mã/khách hàng không đúng |
| Không được phép | Hệ thống chặn thành công và không đổi dữ liệu |
| Tác vụ chỉ đọc | Phản hồi đúng dữ liệu hiện hành, không tạo tác động |
| RAG/fact checking | Kết luận được nguồn có thẩm quyền hỗ trợ |

Nên giữ một tập dữ liệu bí mật để đánh giá hồi quy sau khi đã chỉnh prompt bằng tập phát triển, tránh hiện tượng mô hình hoặc người làm prompt tối ưu hóa vào chính ví dụ đã biết.

## 7. Kiến trúc kiểm chứng trong ứng dụng Spring AI

Một cách bố trí hợp lý là tách **luồng ứng dụng có mô hình** khỏi **luồng xác minh trạng thái**:

~~~mermaid
flowchart TD
    U["Yêu cầu người dùng / test case"] --> M["Spring AI ChatClient + ChatModel"]
    M --> T["ToolCallback / công cụ nghiệp vụ"]
    T --> B["Backend / hệ thống dữ liệu"]
    B --> T
    T --> M
    M --> R["Câu trả lời mô hình"]

    F["Fixture + hợp đồng kết quả"] --> V["Business outcome verifier"]
    B --> S["Nguồn sự thật: primary / ledger / event store"]
    S --> V
    R --> J["Answer-grounding checker"]
    V --> J
    V --> O["Kết quả đánh giá + evidence"]
    J --> O
    T --> X["Trace: tool, args, thời gian, lỗi"]
    X --> O
~~~

Verifier cần đọc qua **kênh được phép và có thẩm quyền**, có thể là API đọc hoặc kho dữ liệu dành riêng cho kiểm thử. Việc triển khai phải bảo vệ thông tin khách hàng; không đưa khóa truy cập hay dữ liệu nhạy cảm vào prompt hoặc log đánh giá.

### Vì sao verifier nên độc lập?

Nếu mô hình tự gọi **get_order_status** và sau đó tự kết luận “đã hủy”, ta vẫn phải kiểm tra bằng một **oracle độc lập**. Một model có thể:

- đọc nhầm kết quả tool;
- bỏ qua trạng thái PENDING;
- dựa trên cache chưa cập nhật;
- chọn nhầm mã đơn ở lần gọi cuối;
- khẳng định thành công dù hệ thống trả lỗi.

Verifier độc lập cho phép phát hiện chính xác sai khác giữa **dữ liệu backend đã ghi** và **điều mô hình tuyên bố**. “Độc lập” ở đây có nghĩa là **quy tắc chấm và đường đọc đáng tin không bị phụ thuộc vào lời khẳng định của mô hình**; không nhất thiết là một hệ thống hoàn toàn tách biệt về hạ tầng.

## 8. Ví dụ Spring AI: ACCEPTED khác với CANCELLED

Ví dụ Java sau sử dụng **@Tool** và **ChatClient** để mô hình tương tác với một backend giả lập. Bộ kiểm chứng đọc trực tiếp trạng thái từ fixture sau khi lượt hội thoại kết thúc, thay vì tin vào câu trả lời.

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public final class BusinessOutcomeProbe {

    private final ChatClient chatClient;

    public BusinessOutcomeProbe(ChatClient.Builder builder) {
        // Dùng builder có cấu hình ChatModel phù hợp;
        // kiểm soát các default tool được cấp trong ca kiểm thử.
        this.chatClient = builder.build();
    }

    public record ToolEvent(
            String toolName,
            String orderId,
            String toolResponse
    ) {}

    public record Outcome(
            String assistantAnswer,
            String beforeStatus,
            String afterStatus,
            boolean cancellationVerified,
            List<ToolEvent> toolEvents
    ) {}

    public Outcome evaluate(boolean completeImmediately) {
        FakeOrderStore store = new FakeOrderStore(completeImmediately);
        OrderTools tools = new OrderTools(store);

        String before = store.status();
        String answer = chatClient.prompt()
                .system("""
                        Bạn hỗ trợ hủy đơn hàng.
                        Chỉ báo 'đã hủy xong' khi biết trạng thái là CANCELLED.
                        ACCEPTED chỉ có nghĩa là đã tiếp nhận yêu cầu.
                        Nếu còn chờ, phải nói rõ trạng thái đang chờ.
                        """)
                .user("Hủy đơn A123 và cho biết đã hủy xong chưa.")
                .tools(tools)
                .call()
                .content();

        // Đây là đường kiểm chứng độc lập, không dựa vào câu trả lời.
        String after = store.status();
        boolean completed = "CANCELLED".equals(after);

        return new Outcome(
                answer,
                before,
                after,
                completed,
                tools.events()
        );
    }

    private static final class FakeOrderStore {

        private final boolean completeImmediately;
        private String state = "PROCESSING";

        private FakeOrderStore(boolean completeImmediately) {
            this.completeImmediately = completeImmediately;
        }

        synchronized String requestCancellation(String orderId) {
            if (!"A123".equals(orderId)) {
                return "NOT_FOUND";
            }
            if (!"PROCESSING".equals(state)) {
                return "NOT_APPLICABLE";
            }
            state = completeImmediately
                    ? "CANCELLED"
                    : "CANCELLATION_REQUESTED";
            return "ACCEPTED";
        }

        synchronized String status() {
            return state;
        }
    }

    public static final class OrderTools {

        private final FakeOrderStore store;
        private final List<ToolEvent> events =
                new CopyOnWriteArrayList<>();

        private OrderTools(FakeOrderStore store) {
            this.store = store;
        }

        @Tool(
                name = "request_order_cancellation",
                description = "Gửi yêu cầu hủy đơn; ACCEPTED không đảm bảo đã hủy xong"
        )
        public String requestCancellation(
                @ToolParam(description = "Mã đơn hàng cần hủy")
                String orderId
        ) {
            String response = store.requestCancellation(orderId);
            events.add(new ToolEvent(
                    "request_order_cancellation", orderId, response));
            return response;
        }

        @Tool(
                name = "get_order_status",
                description = "Đọc trạng thái hiện tại của đơn hàng"
        )
        public String getOrderStatus(
                @ToolParam(description = "Mã đơn hàng cần kiểm tra")
                String orderId
        ) {
            String response = "A123".equals(orderId)
                    ? store.status()
                    : "NOT_FOUND";
            events.add(new ToolEvent(
                    "get_order_status", orderId, response));
            return response;
        }

        public List<ToolEvent> events() {
            return List.copyOf(events);
        }
    }
}
~~~

Ví dụ chạy hai tình huống:

~~~java
BusinessOutcomeProbe probe =
        new BusinessOutcomeProbe(chatClientBuilder);

BusinessOutcomeProbe.Outcome immediate =
        probe.evaluate(true);
BusinessOutcomeProbe.Outcome pending =
        probe.evaluate(false);

System.out.println(immediate);
System.out.println(pending);
~~~

Trong đó **chatClientBuilder** là builder do ứng dụng Spring AI cung cấp. Cần ChatModel hỗ trợ tool calling và cấu hình truy cập phù hợp nếu muốn thực sự chạy mô hình.

**Kỳ vọng khi mô hình gọi đúng request_order_cancellation cho A123:**

- Với **completeImmediately=true**, backend giả lập chuyển sang CANCELLED; nếu không có lỗi khác, điều kiện trạng thái cuối đạt.
- Với **completeImmediately=false**, backend chuyển sang CANCELLATION_REQUESTED, dù tool trả ACCEPTED. Khi mục tiêu là **hủy hoàn tất**, **cancellationVerified=false**.
- Nếu model không gọi công cụ, sau trạng thái vẫn là PROCESSING; bộ đánh giá nhận ra chưa hoàn tất.
- Nếu model dùng mã đơn khác A123, backend trả NOT_FOUND và trạng thái không đổi.

**Quan trọng:** trường **cancellationVerified** chỉ phản ánh **hậu điều kiện trạng thái**. Để chấm đầy đủ, còn phải so sánh **assistantAnswer** với trạng thái thực, kiểm tra số lần gọi, đúng đối tượng, quyền và bất biến. Ví dụ minh họa không tự thực thi một workflow bất đồng bộ; trong trường hợp pending, trạng thái sẽ giữ nguyên cho đến khi bộ mô phỏng hoặc tiến trình nền chủ động cập nhật.

Đoạn mã ghi lại **tool đã chạy trong phương thức Java**. Nếu một tool request bị lỗi chuyển đổi đối số hoặc bị chặn trước khi vào phương thức, cần thu thập sự kiện ở lớp điều phối hay lớp bọc **ToolCallback** để phân biệt **model đề nghị**, **dispatcher tiếp nhận** và **backend thực thi**.

### Cách viết assertion cho kết quả

Với một ca chỉ đòi **hủy thành công**, ít nhất cần:

~~~text
initial_status == PROCESSING
final_status == CANCELLED
changed_order_id == A123
unrelated_orders_unchanged == true
unauthorized_actions == 0
duplicate_cancellation_requests == 0
~~~

Với ca chỉ đòi **tạo yêu cầu hủy**, expected outcome khác:

~~~text
cancellation_request_exists == true
request.order_id == A123
request.accepted == true
assistant_does_not_claim_completed_when_pending == true
~~~

Hai ca này không thể dùng chung một oracle chỉ dựa vào việc tool trả ACCEPTED.

## 9. Kiểm chứng tiến trình bất đồng bộ và eventual consistency

Nhiều nghiệp vụ không hoàn thành ngay: hoàn tiền, gửi email, xử lý hàng đợi, đồng bộ đơn hàng hoặc xác minh thanh toán.

Trong trường hợp này, verifier cần định nghĩa một **cửa sổ kiểm tra**:

1. Ghi thời điểm yêu cầu được tiếp nhận và một mã tương quan (operation ID).
2. Đọc trạng thái từ nguồn được chỉ định; dùng revision hoặc event ID nếu có.
3. Nếu đạt hậu điều kiện và không vi phạm bất biến, kết luận VERIFIED_SUCCESS.
4. Nếu nguồn trả trạng thái lỗi cuối, từ chối hoặc bất biến bị vi phạm, kết luận VERIFIED_FAILURE.
5. Nếu còn PENDING, kiểm tra lại có giới hạn và với khoảng cách hợp lý, đến deadline.
6. Nếu hết thời hạn kiểm chứng nhưng SLA nghiệp vụ chưa hết hoặc không có đủ nguồn, báo UNKNOWN/PENDING và lưu lý do. Nếu deadline là cam kết hoàn tất, đánh dấu lỗi SLA riêng.

Ví dụ mô tả bằng mã giả:

~~~text
verify(operationId, expectedStatus, deadline):
    while currentTime < deadline:
        evidence = trustedRead(operationId)
        if evidence.isUnobservable:
            record("EVIDENCE_UNAVAILABLE")
        else if evidence.violatesInvariant:
            return VERIFIED_FAILURE
        else if evidence.status == expectedStatus:
            return VERIFIED_SUCCESS
        else if evidence.isTerminalFailure:
            return VERIFIED_FAILURE
        backoffWithinLimit()
    return PENDING_OR_SLA_FAILURE_ACCORDING_TO_CONTRACT
~~~

Đây là mã giả để giải thích logic; không khuyến nghị dùng vòng lặp chờ vô hạn trong luồng HTTP xử lý người dùng.

### Cần phân biệt các đồng hồ thời gian

- **Model latency:** thời gian mô hình đưa ra tool request hoặc câu trả lời.
- **Tool latency:** thời gian dịch vụ thực thi hoặc tiếp nhận thao tác.
- **Business completion latency:** thời gian từ lúc nhận yêu cầu đến khi hậu điều kiện thực sự đạt.
- **Verification latency:** thời gian oracle mất để quan sát bằng chứng đủ tin cậy.

Nếu nghiệp vụ cần hai phút để hoàn tất, việc model trả lời sau 300 ms **không có nghĩa là tác vụ đã hoàn thành trong 300 ms**.

### Retry và idempotency

Khi công cụ timeout, có thể xảy ra trường hợp backend **đã ghi thay đổi** nhưng client chưa nhận phản hồi. Gọi lại không kiểm soát có thể tạo hai yêu cầu hoặc hai giao dịch.

Với công cụ có tác động, cần thiết kế:

- **Idempotency key** được backend công nhận để cùng một thao tác không tạo tác động trùng khi retry.
- **Correlation/operation ID** để truy vết trạng thái của cùng một yêu cầu.
- **Retry policy** có giới hạn, phân biệt lỗi tạm thời và lỗi nghiệp vụ cuối.
- **Read-after-timeout:** trước khi gửi lại, đọc trạng thái của yêu cầu đã có nếu nghiệp vụ hỗ trợ.
- **Compensation / rollback** theo nghiệp vụ khi workflow nhiều bước thất bại một phần.

Trong đánh giá, **lời gọi lặp** và **tác động lặp thực tế** phải được đo riêng. Backend có idempotency có thể ngăn tác động trùng dù model vẫn gọi dư, gây thêm độ trễ và chi phí.

## 10. Kiểm chứng tác vụ chỉ đọc, RAG và fact checking

Không phải kết quả nghiệp vụ nào cũng có một thay đổi trạng thái để kiểm chứng. Khi yêu cầu là “Cho biết tồn kho thật hiện tại” hoặc “Đọc quy định bảo hành”, hậu điều kiện chủ yếu là **giá trị trả về đúng, đủ mới và được phép sử dụng**.

### Kiểm tra với dữ liệu thật đã cố định

Ví dụ người dùng hỏi “Sản phẩm P100 còn bao nhiêu chiếc?”. Bộ đánh giá có fixture:

~~~json
{
  "case_id": "STOCK-01",
  "as_of": "2026-11-27T09:00:00+07:00",
  "truth": {
    "sku": "P100",
    "availableToSell": 12,
    "warehouse": "HCM-01"
  },
  "expected_answer": {
    "availableToSell": 12,
    "unit": "items",
    "must_state_scope": "HCM-01"
  }
}
~~~

Nếu mô hình trả lời “còn 20 chiếc” vì dùng dữ liệu cache cũ, thì sai **giá trị nghiệp vụ** ngay cả khi đã gọi đúng công cụ. Nếu mô hình nói “còn 12 chiếc trên toàn quốc”, câu trả lời cũng có thể sai **phạm vi**, bởi fixture chỉ nói về kho HCM-01.

Với số liệu biến đổi liên tục, hãy **đóng băng snapshot hoặc ghi mốc as-of**. Một kết quả đúng lúc 9 giờ không thể đem so với tồn kho lúc 15 giờ mà không xét thay đổi theo thời gian.

### Kiểm tra với RAG

Trong RAG, câu trả lời có thể đi qua các bước: chọn truy xuất, tìm tài liệu, chọn đoạn, tổng hợp và trả lời. Để xác minh kết quả:

| Phần đánh giá | Câu hỏi |
| --- | --- |
| Retrieval relevance | Tài liệu truy xuất có liên quan đến yêu cầu? |
| Source authority & freshness | Có đúng nguồn có thẩm quyền, phiên bản và ngày hiệu lực? |
| Factual correctness | Các phát biểu có phù hợp với sự thật trong nguồn chuẩn không? |
| Groundedness / faithfulness | Các kết luận có được dẫn chứng truy xuất hỗ trợ không? |
| Completeness | Câu trả lời có bỏ sót điều kiện nghiệp vụ quan trọng không? |
| Authorization | Có sử dụng hoặc tiết lộ nguồn vượt quyền không? |

Ví dụ tài liệu chính sách có hiệu lực từ tháng 7/2026 quy định “yêu cầu bảo hành phải nộp trong 30 ngày”. Nếu công cụ truy xuất trả về bản cũ ghi “45 ngày”, mô hình có thể **trung thành với đoạn truy xuất** nhưng vẫn **sai thực tế**. Đây là lý do phải tách đánh giá groundedness khỏi fact checking theo nguồn có thẩm quyền.

Trong một hệ thống có nhiều nguồn mâu thuẫn, oracle cần công bố **thứ tự ưu tiên, ngày hiệu lực và điều kiện áp dụng**. Không chấm đơn giản theo một chuỗi câu chữ duy nhất khi tài liệu có ngoại lệ hoặc phạm vi khác nhau.

### Không dùng mô hình làm nguồn sự thật cuối

LLM-as-a-judge có thể hữu ích khi chấm một phát biểu ngữ nghĩa, nhưng phải được cung cấp **sự thật chuẩn/đoạn chứng cứ**, rubric và kiểm thử độ ổn định. Mô hình chấm không được tự sáng tác nguồn hoặc cấp quyền; những kiểm tra mã đơn, số tiền, quyền truy cập và trạng thái cuối nên ưu tiên kiểm tra xác định bằng mã.

## 11. Chỉ số đo chất lượng kết quả nghiệp vụ

Đối với bộ dữ liệu đã có hậu điều kiện rõ, có thể xây dựng các chỉ số:

### Business outcome success rate

\[
\text{Business Outcome Success Rate} =
\frac{\text{Số ca đạt hậu điều kiện và bất biến}}{\text{Tổng số ca đủ điều kiện để chấm}}
\]

Mẫu số phải được công bố. Ca UNKNOWN do thiếu nguồn có thể được báo riêng; nếu gộp với thất bại, cần ghi rõ quy ước. Ca mô hình không thực hiện tác vụ trong khi người dùng yêu cầu vẫn phải được tính vào đánh giá end-to-end nếu mục tiêu là **hoàn thành yêu cầu**.

### Verified claim precision

\[
\text{Verified Claim Precision} =
\frac{\text{Số tuyên bố hoàn tất có bằng chứng xác nhận}}{\text{Tổng số tuyên bố hoàn tất được đánh giá}}
\]

Phân biệt:

- **False success claim:** mô hình khẳng định hoàn tất nhưng bằng chứng cho thấy chưa hoàn tất hoặc thất bại.
- **Unverified success claim:** mô hình khẳng định hoàn tất nhưng không có đủ dữ liệu để xác minh.
- **Correct pending disclosure:** mô hình nói đang xử lý khi backend thực sự còn chờ.

Không tự trộn **unverified** với **verified failure**; báo cả hai để biết hệ thống sai nội dung hay chỉ thiếu khả năng quan sát.

### Invariant violation rate

\[
\text{Invariant Violation Rate} =
\frac{\text{Số ca có ít nhất một bất biến bị phá vỡ}}{\text{Tổng số ca áp dụng bất biến}}
\]

Đặc biệt theo dõi lỗi sai người nhận, sai đối tượng, sai số tiền, vượt quyền, tác động trùng hoặc rò rỉ dữ liệu. Lỗi nghiêm trọng cần **được báo riêng**, vì một tỷ lệ trung bình đẹp có thể che giấu một sự cố không thể chấp nhận.

### Các chỉ số bổ sung

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tool execution success rate | Tỷ lệ gọi công cụ hoàn tất ở mức kỹ thuật |
| Verified end-to-end task success | Tỷ lệ ca hoàn thành mục tiêu người dùng theo oracle |
| Pending / unknown rate | Tỷ lệ ca chưa thể kết luận trong cửa sổ đánh giá |
| Business completion time p50/p95 | Phân bố thời gian đến khi hậu điều kiện được ghi nhận |
| Verification lag p50/p95 | Độ trễ từ hoàn tất thực tế đến lúc oracle quan sát được |
| Duplicate side-effect rate | Tỷ lệ ca có tác động ghi bị lặp |
| Cost per verified success | Tổng chi phí thực tế/ước tính chia số ca xác minh thành công |
| Data freshness violation rate | Tỷ lệ phản hồi dùng dữ liệu cũ hơn ngưỡng cho phép |
| RAG factual accuracy | Tỷ lệ phát biểu đúng theo nguồn sự thật đã xác định |

**Cost per verified success** chỉ có ý nghĩa nếu có dữ liệu chi phí đủ tin cậy và mẫu số khác 0. Nếu thiếu giá model, phí API hoặc số token, hãy báo chi phí không xác định thay vì tự điền 0.

### Ví dụ tính toán

Giả sử một bộ thử nghiệm có 100 ca đủ điều kiện đánh giá hoàn thành yêu cầu:

- 72 ca có hậu điều kiện và bất biến đều đạt.
- 12 ca xác nhận thất bại.
- 10 ca còn chờ trong thời hạn cho phép.
- 6 ca thiếu bằng chứng để xác định.
- Mô hình tuyên bố “đã hoàn tất” trong 80 ca; trong đó 70 ca có bằng chứng xác nhận, 7 ca bị bằng chứng bác bỏ, 3 ca chưa đủ bằng chứng.

Khi tính trên **toàn bộ 100 ca**, tỷ lệ verified success hiện tại là **72%**, đồng thời **16% chưa thể kết luận**. Với các tuyên bố đã được xác minh rõ ràng, độ chính xác là **70 / 77 ≈ 90,9%**. Nếu đưa ba ca chưa có bằng chứng vào mẫu số, tỷ lệ **có thể xác nhận được** là **70 / 80 = 87,5%**. Hai con số trả lời hai câu hỏi khác nhau; cần công bố mẫu số và tên chỉ số.

Nếu chỉ tính success của tool response, tỷ lệ có thể cao hơn nhiều và làm người đọc hiểu nhầm chất lượng ứng dụng.

## 12. Nối kết kiểm chứng với observability

Spring AI có thể kết hợp với hệ sinh thái **Micrometer Observation** để quan sát ChatClient, model và lời gọi công cụ tùy phiên bản, cấu hình tích hợp. Bộ đánh giá cần nối các sự kiện này với **trạng thái nghiệp vụ đã kiểm chứng**.

Ví dụ một bản ghi chuẩn hóa của hệ thống đánh giá:

~~~json
{
  "case_id": "CANCEL-01",
  "run_id": "model-b-prompt-v3-pipeline-2",
  "trace_id": "example-trace-id",
  "operation_id": "cancel-request-123",
  "entity_type": "order",
  "entity_id_for_test": "A123",
  "tool_name": "request_order_cancellation",
  "tool_response": "ACCEPTED",
  "initial_state": "PROCESSING",
  "observed_state": "CANCELLATION_REQUESTED",
  "source": "order-primary",
  "evidence_observed_at": "2026-11-27T09:00:02+07:00",
  "business_outcome": "PENDING",
  "assistant_claim": "COMPLETED",
  "claim_is_supported": false,
  "tool_duration_ms": 90,
  "model_duration_ms": 640,
  "business_completion_ms": null,
  "input_tokens": 420,
  "output_tokens": 78,
  "estimated_cost_usd": null
}
~~~

Đây là **schema minh họa do dự án tự thiết kế**, không phải tên trường mà Spring AI mặc định luôn phát ra. Các trường như **assistant_claim**, **business_outcome** và **claim_is_supported** là kết quả của bộ chấm bên ngoài mô hình.

### Những điểm cần liên kết trong trace

| Điểm quan sát | Mục đích |
| --- | --- |
| User request, scenario ID, phiên bản prompt/model | Biết tác vụ nào được hỏi và cấu hình nào xử lý |
| Tool request và tham số | Phân biệt lỗi chọn sai, sai mã/đối tượng |
| Tool dispatcher và kiểm tra quyền | Biết yêu cầu có bị chặn trước thực thi không |
| Tool response và mã tương quan | Ghép lời gọi với thao tác tại backend |
| Event nghiệp vụ hoặc snapshot đã lưu | Xác nhận sự thật sau lời gọi |
| Verifier result và thời điểm đọc | Giải thích kết luận PASS/FAIL/PENDING |
| Assistant claim | Kiểm tra mô hình có khẳng định đúng với trạng thái thực không |
| Token, thời gian, retry, chi phí | Đánh giá hiệu quả vận hành và nguyên nhân chậm |

Độ trễ **p95 của phản hồi mô hình** có thể cải thiện trong khi **p95 của thời gian hoàn thành nghiệp vụ** xấu đi. Nếu chỉ quan sát trace của ChatClient, ta sẽ bỏ qua vấn đề hậu xử lý hoặc hàng đợi ở backend.

Một span không xuất hiện không có nghĩa sự kiện không xảy ra: có thể mất instrumentation, sampling hoặc quá trình ghi nhận bị lỗi. Nếu verifier không thể đọc nguồn xác minh, đánh dấu **EVIDENCE_UNAVAILABLE** thay vì kết luận tác vụ thất bại hay thành công.

**Lưu ý dữ liệu nhạy cảm:** đối số tool và kết quả đọc hệ thống có thể chứa tên, số tiền, email hoặc ID thật. Giới hạn lưu trữ; ẩn, băm hoặc mã hóa các trường cần thiết; chỉ thu thập dữ liệu phục vụ đánh giá và theo quyền truy cập hợp lệ.

## 13. Phân loại lỗi để tìm đúng nguyên nhân

| Dấu hiệu | Nguyên nhân có thể | Bằng chứng cần xem | Hướng khắc phục |
| --- | --- | --- | --- |
| Model nói đã hoàn tất nhưng backend PENDING | Nhầm ACCEPTED với COMPLETED | Tool response và trạng thái cuối | Làm rõ hợp đồng trạng thái; bổ sung bước xác minh |
| Tool báo success nhưng không có thay đổi | Transaction rollback, lỗi lưu hoặc API chỉ nhận yêu cầu | Log backend, transaction ID, revision | Sửa backend và điều kiện kiểm tra |
| Model hủy sai đơn | Sai đối số, dữ liệu hội thoại bị nhầm | Tool args, entity ID trong snapshot | Kiểm tra định danh và quyền trước thực thi |
| Kết quả đọc và ghi mâu thuẫn | Cache/replica chậm, hai thao tác đồng thời | Thời điểm, revision, nguồn đọc | Dùng nguồn có bảo đảm nhất quán phù hợp |
| Tạo hai giao dịch cùng yêu cầu | Retry sau timeout không có idempotency | Operation ID và transaction ledger | Bổ sung khóa chống trùng và logic đối soát |
| Không có sự kiện tool nhưng dữ liệu thay đổi | Thiếu trace, tác động từ tác nhân khác | Audit log, correlation ID | Làm rõ nguồn thay đổi và instrumentation |
| Model trả lời đúng tài liệu cũ nhưng sai quy định mới | RAG truy xuất sai phiên bản | As-of, ngày hiệu lực, document revision | Sửa bộ lọc nguồn, refresh index |
| Backend đúng nhưng model báo sai | Lỗi đọc kết quả hoặc tổng hợp | Tool output, final answer | Cải thiện cách đọc tool result và kiểm tra grounding |
| Hậu điều kiện đạt nhưng quyền bị vi phạm | Backend không kiểm quyền đầy đủ | Auth context, mutation log | Chặn tại backend, thêm bất biến về quyền |

Khi có lỗi, truy nguyên theo trật tự:

1. **Kỳ vọng có đúng không?** Người dùng muốn tạo yêu cầu hay hoàn tất giao dịch?
2. **Model đã yêu cầu thao tác gì?** Đúng tool và đối số không?
3. **Dispatcher/backend thực hiện gì?** Được phép, chấp nhận, xử lý hay lỗi?
4. **Dữ liệu có thẩm quyền nói gì?** Trạng thái cuối, revision và sự kiện nào?
5. **Câu trả lời khẳng định điều gì?** Có bằng chứng hỗ trợ tại thời điểm trả lời không?
6. **Có lỗi quan sát không?** Chậm đồng bộ, mất trace hoặc dữ liệu không đủ mới?

Không sửa prompt cho một lỗi transaction rollback; cũng không sửa backend nếu lỗi là mô hình tự diễn giải sai ACCEPTED thành CANCELLED. Quan hệ nhân quả phải được xác minh bằng chứng cụ thể.

## 14. Kiểm chứng an toàn và tính tái lập

Việc đánh giá tác động nghiệp vụ có thể tạo ra thay đổi thật. Với thử nghiệm định kỳ, ưu tiên **test double, stub, môi trường sandbox hoặc dữ liệu giả lập**.

Các quy tắc cần thực hiện:

- **Cách ly dữ liệu:** mỗi ca có fixture riêng, reset trạng thái hoặc cấp namespace riêng.
- **Cố định thời gian:** với ngày giờ tương đối, lưu thời điểm tham chiếu và múi giờ.
- **Bất biến quyền:** thử nghiệm không được thay đổi dữ liệu ngoài danh sách đối tượng được cấp.
- **Idempotency:** tạo mã thao tác riêng cho mỗi ca, kiểm tra khi retry.
- **Chống nhiễu cạnh tranh:** không để tác vụ nền hoặc ca khác thay đổi cùng đối tượng mà không được ghi lại.
- **Giới hạn xác minh:** deadline, lịch kiểm tra và điều kiện kết thúc rõ ràng.
- **Versioning:** lưu phiên bản fixture, schema tool, oracle, prompt, model và pipeline.
- **Giảm dữ liệu nhạy cảm:** tránh đưa tài khoản, số tiền hoặc thông tin khách hàng thật vào log dùng để luyện/chấm.

Nếu phải quan sát dữ liệu production, chỉ dùng quyền đã được cấp, ưu tiên kiểm tra chỉ đọc và tuân thủ cách ly của tổ chức. Không tự ý tạo tác động thật chỉ để đo xem mô hình có gọi công cụ đúng hay không.

### Kết hợp assertion xác định và đánh giá ngữ nghĩa

Nên dùng kiểm tra bằng mã cho:

- Trạng thái cơ sở dữ liệu và thay đổi bản ghi.
- Số tiền, ID, số lượng, quyền và phiên bản dữ liệu.
- Thời gian hoàn thành, số lần gọi và sự kiện trùng.
- Bất biến như “không tạo hoàn tiền khi chưa xác nhận”.

Có thể dùng mô hình đánh giá hoặc người kiểm duyệt để chấm:

- Câu trả lời có diễn đạt đúng mức “đã tiếp nhận / đang chờ / đã hoàn tất” không.
- Câu trả lời có bỏ sót ngoại lệ hoặc phạm vi của một quy định RAG không.
- Lời giải thích có phù hợp với bằng chứng mà oracle đã xác minh không.

Đối với các tiêu chí ngữ nghĩa, phải cung cấp rubric và bằng chứng; so sánh kết quả chấm với tập đã được chuyên gia gán nhãn, tránh để evaluator tự quyết định sự thật nghiệp vụ.

## 15. So sánh prompt, model và pipeline bằng kết quả đã kiểm chứng

Giả sử cùng 200 ca kiểm thử, phiên bản A và B có kết quả giả định:

| Chỉ số | Phiên bản A | Phiên bản B |
| --- | ---: | ---: |
| Tool execution success | 97% | 99% |
| Verified business success | 84% | 80% |
| Số ca khẳng định hoàn tất sai | 3 | 12 |
| Số ca vi phạm bất biến | 0 | 2 |
| p95 model response | 1,8 giây | 1,4 giây |
| p95 business completion | 7 giây | 10 giây |

Phiên bản B có tỷ lệ tool chạy kỹ thuật cao hơn và phản hồi mô hình nhanh hơn, nhưng chất lượng nghiệp vụ giảm. Một nguyên nhân có thể là B trả lời quá sớm khi backend chỉ báo ACCEPTED. Từ kết quả trên chưa thể khẳng định nguyên nhân cụ thể; cần xem trace, snapshot và nhóm ca hồi quy.

Khi so sánh:

1. Giữ cùng dataset, oracle, fixture, danh sách tool và nguồn kiểm chứng.
2. Ghi đầy đủ model, prompt, pipeline, tool schema, data snapshot và cách tính chỉ số.
3. Chạy đủ số lần với tác vụ có tính ngẫu nhiên; kiểm tra tỷ lệ và phân bố lỗi theo nhóm.
4. Ưu tiên kiểm tra những ca chuyển từ PASS thành FAIL và lỗi tác động ngoài phạm vi.
5. So sánh chất lượng với **p95 hoàn thành nghiệp vụ**, số lần gọi và chi phí trên kết quả đã kiểm chứng.
6. Khi thay đổi chính sách nghiệp vụ, cập nhật oracle có kiểm soát và công bố rằng kết quả trước/sau có thể không còn so sánh trực tiếp.

Một ngưỡng chấp nhận phải tùy rủi ro: lỗi trả sai trạng thái đơn có thể yêu cầu sửa nhanh, còn lỗi gửi tiền sai người nhận cần ngưỡng an toàn nghiêm ngặt và chặn ở backend.

## 16. Bài thực hành

**Bối cảnh:** Trợ lý Spring AI có hai tool **request_order_cancellation** và **get_order_status**. Backend giả lập ban đầu giữ đơn A123 ở PROCESSING và có thể chuyển sang CANCELLED ngay hoặc sang CANCELLATION_REQUESTED trước.

**Yêu cầu:**

1. Dùng **BusinessOutcomeProbe** chạy hai kịch bản completeImmediately=true và false.
2. Tạo thêm fixture thứ ba: công cụ trả ACCEPTED nhưng backend từ chối hủy vì đơn đã được giao.
3. Viết oracle cho hai mục tiêu khác nhau: **“gửi yêu cầu hủy”** và **“hủy hoàn tất”**.
4. Thêm một đơn B456; kiểm tra B456 không bị thay đổi khi tác vụ chỉ nhắc A123.
5. Ghi lại **assistantAnswer**, tool events, snapshot trước/sau, trạng thái oracle, thời gian xác minh.
6. Chạy với hai phiên bản system prompt. So sánh các ca model tuyên bố hoàn tất dù backend đang pending.
7. Mở rộng thành tác vụ RAG: dùng một tài liệu chính sách giả lập có phiên bản cũ và mới, kiểm tra liệu câu trả lời phản ánh đúng phiên bản đang có hiệu lực.

**Câu hỏi tự kiểm tra:**

- Vì sao một công cụ trả HTTP 200 không chứng minh giao dịch nghiệp vụ đã hoàn tất?
- Khi nào trạng thái PENDING nên giữ nguyên, và khi nào có thể tính là vi phạm SLA?
- Nếu dữ liệu primary đã đổi nhưng replica vẫn cũ, kết quả nào là bằng chứng phù hợp với hợp đồng?
- Vì sao cần kiểm tra bất biến ngoài hậu điều kiện?
- Nếu mô hình trả lời đúng bằng cách đoán mà không gọi công cụ bắt buộc, ca đó có được coi là đúng toàn bộ luồng không?
- Nếu RAG trả lời đúng theo bản quy định cũ nhưng sai bản đang hiệu lực, nên phân loại lỗi nào?

## 17. Những điều cần ghi nhớ

1. **Thực thi tool thành công và hoàn thành nghiệp vụ là hai sự kiện khác nhau.** Hãy định nghĩa kết quả đích từ mục tiêu thực tế của người dùng.
2. **Dùng nguồn có thẩm quyền để xác minh.** Không lấy lời mô hình hay message ACCEPTED làm bằng chứng duy nhất.
3. **Kiểm tra cả trạng thái và quá trình thay đổi.** Snapshot, event ID, quyền, thời gian, idempotency và bất biến giúp phát hiện lỗi che khuất.
4. **Bất đồng bộ cần cửa sổ kiểm chứng.** Phân biệt SUCCESS, FAILURE và PENDING/UNKNOWN; không biến thiếu quan sát thành một kết luận chắc chắn.
5. **RAG cần fact checking theo nguồn hiện hành.** Câu trả lời có căn cứ vào một đoạn tài liệu vẫn có thể sai thực tế nếu nguồn đã hết hiệu lực.
6. **Kết nối chất lượng với metrics và traces.** Đo verified business success, lời khẳng định sai, độ trễ hoàn thành, chi phí và lỗi theo từng phiên bản prompt, model, tool và pipeline.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): mô hình công cụ, mô tả đầu vào, thực thi và tích hợp ChatClient.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): khái niệm quan sát hoạt động model, ChatClient và công cụ.
- [Martin Fowler — Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/): những mẫu hình giúp suy nghĩ về trạng thái phân tán, sự kiện và tính nhất quán.

Tên API và dữ liệu observation có thể thay đổi theo phiên bản Spring AI; khi triển khai, đối chiếu API thực tế và hợp đồng nghiệp vụ của hệ thống đang sử dụng.
