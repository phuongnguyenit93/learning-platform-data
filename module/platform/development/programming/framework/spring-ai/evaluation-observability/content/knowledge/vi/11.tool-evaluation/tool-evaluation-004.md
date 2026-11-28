# Đánh giá chuỗi nhiều bước và điều kiện dừng

Một ứng dụng Spring AI có khả năng gọi công cụ thường không thể hoàn thành yêu cầu chỉ bằng một lời gọi. Để báo phí vận chuyển của một đơn hàng, trợ lý có thể phải **tra trọng lượng thực tế**, **ước tính phí dựa trên trọng lượng và địa chỉ nhận**, rồi **giải thích báo giá**. Để trả lời câu hỏi liên quan đến quy định nội bộ, trợ lý có thể phải **truy xuất tài liệu**, **kiểm tra phiên bản và tính liên quan**, sau đó **tổng hợp câu trả lời có căn cứ**.

Trong những tình huống đó, mỗi lời gọi riêng lẻ có thể hợp lệ, nhưng toàn bộ chuỗi vẫn sai: gọi bước hai trước bước một, bỏ qua kiểm tra quyền, lặp công cụ vô hạn, hoặc dừng khi chưa có dữ liệu đủ tin cậy. Ngược lại, một trợ lý có thể tiếp tục gọi công cụ dù đã đạt mục tiêu, làm tăng chi phí, độ trễ và rủi ro tác động ngoài ý muốn.

Bài này thuộc chương **Đánh giá công cụ** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Trọng tâm là xây dựng bộ dữ liệu và tiêu chí chấm **cả đường đi của nhiều lời gọi lẫn quyết định dừng**, gắn kết quả với traces, metrics, chi phí, độ trễ, đánh giá RAG và kiểm chứng câu trả lời để phát hiện lỗi hồi quy giữa các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt một **tool call**, một **lượt model**, một **bước nghiệp vụ** và một **chuỗi thực thi**.
2. Mô tả chuỗi công cụ hợp lệ bằng thứ tự, quan hệ phụ thuộc, nhánh điều kiện, kết quả trung gian và bất biến.
3. Định nghĩa các trường hợp dừng đúng: **hoàn thành**, **cần thông tin**, **thiếu quyền**, **lỗi không thể khôi phục**, **đạt giới hạn tài nguyên** hoặc **chờ xử lý bên ngoài**.
4. Phát hiện **dừng sớm**, **gọi thừa sau khi đạt mục tiêu**, **gọi lặp không có tiến triển** và **thực hiện bước gây tác động khi thiếu tiền điều kiện**.
5. Xây dựng tập dữ liệu, oracle và báo cáo cho các luồng nhiều bước, kể cả luồng RAG có các nhánh hợp lệ.
6. Ghi nhận chuỗi tool bằng Spring AI, kiểm thử với công cụ giả lập và phân tích kết quả bằng traces, metrics, độ trễ và chi phí.

## 2. Đơn vị quan sát: từ yêu cầu đến chuỗi hành động

Trước khi chấm chuỗi, cần thống nhất một số khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **User task** | Mục tiêu thực sự của người dùng | “Báo phí giao đơn A123 đến Đà Nẵng” |
| **Model turn** | Một lần mô hình xử lý ngữ cảnh để sinh nội dung hoặc đề nghị gọi tool | Đề nghị tra đơn hàng |
| **Tool call** | Một yêu cầu gọi công cụ cụ thể, kèm tên và đối số | get_order_package(orderId=A123) |
| **Business step** | Một bước logic cần thực hiện để đạt mục tiêu | Biết trọng lượng đã xác minh |
| **Tool result** | Dữ liệu/lỗi nhận về sau lời gọi | weightKg=2.5 |
| **Trajectory / execution trace** | Chuỗi các bước, quyết định, kết quả và trạng thái trung gian | Tra đơn → tính phí → trả lời |
| **Termination** | Quyết định ngừng gọi công cụ hoặc ngừng xử lý tác vụ hiện tại | Có báo giá, kết thúc đúng |

Một model turn có thể phát sinh **không, một hoặc nhiều** tool call tùy khả năng của model và cấu hình framework. Một business step cũng có thể không cần tool nếu dữ liệu hợp lệ đã có trong ngữ cảnh. Vì vậy, **số lời gọi công cụ không đồng nghĩa với số bước nghiệp vụ**.

Không nên chấm chỉ từ nội dung câu trả lời cuối. Ví dụ, mô hình có thể may mắn đoán đúng giá và nói “đã tính phí” dù chưa kiểm tra trọng lượng; hoặc đã tra và tính đúng nhưng lặp lời gọi tính phí bốn lần trước khi trả lời. Hai đường đi này cần được phân biệt.

### Các tầng đánh giá liên quan

| Tầng | Tiêu chí | Vai trò trong bài |
| --- | --- | --- |
| Quyết định gọi | Có nên gọi công cụ tại một thời điểm? | Nền tảng để xét mỗi bước |
| Chọn tool và đối số | Đúng tên công cụ, thực thể, kiểu và giá trị? | Mỗi lời gọi phải hợp lệ |
| **Chuỗi nhiều bước** | Đúng thứ tự, nhánh, phụ thuộc và giới hạn? | Trọng tâm thứ nhất |
| **Điều kiện dừng** | Đã đủ cơ sở để ngừng hay phải xử lý tiếp? | Trọng tâm thứ hai |
| Kết quả nghiệp vụ | Trạng thái cuối có đạt mục tiêu và bất biến? | Bằng chứng để chấm dừng |
| Grounding / fact checking | Câu trả lời có dựa vào kết quả hoặc nguồn thực tế? | Xác nhận đầu ra có căn cứ |

## 3. Ví dụ xuyên suốt: báo phí giao hàng

Giả sử hệ thống chỉ có hai công cụ đọc dữ liệu:

- **get_order_package(orderId)**: lấy trọng lượng thực tế của một kiện hàng thuộc đơn đã được phép xem.
- **quote_shipping_fee(destinationProvince, weightKg)**: tính báo giá vận chuyển cho tỉnh nhận và trọng lượng đã xác minh.

Người dùng hỏi: **“Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?”**

Trong fixture kiểm thử:

~~~json
{
  "user": "Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?",
  "authorizedOrderIds": ["A123"],
  "order": {"orderId": "A123", "weightKg": 2.5},
  "shippingQuote": {
    "destinationProvince": "Đà Nẵng",
    "weightKg": 2.5,
    "amount": 34000,
    "currency": "VND"
  }
}
~~~

Chuỗi đúng, nếu không có kết quả cũ hợp lệ trong ngữ cảnh, là:

~~~mermaid
flowchart TD
    A["Nhận câu hỏi và xác thực ngữ cảnh"] --> B{"Đã có mã đơn, tỉnh nhận và quyền?"}
    B -->|Thiếu thông tin| C["Hỏi bổ sung: dừng có lý do"]
    B -->|Không có quyền| D["Từ chối thao tác: dừng có lý do"]
    B -->|Đủ| E["get_order_package(A123)"]
    E --> F{"Trọng lượng có hợp lệ?"}
    F -->|Không| G["Báo không thể tính, xử lý lỗi"]
    F -->|Có: 2,5 kg| H["quote_shipping_fee(Đà Nẵng, 2.5)"]
    H --> I{"Báo giá hợp lệ?"}
    I -->|Có| J["Trả lời 34.000 VND và dừng"]
    I -->|Không| K["Thông báo trạng thái / retry nếu được phép"]
~~~

**Tiền điều kiện** cho bước tính phí là đã có trọng lượng có nguồn gốc đáng tin. **Điều kiện dừng thành công** là đã có báo giá hợp lệ cho đúng địa điểm và trọng lượng, đồng thời câu trả lời phản ánh đúng kết quả. Nếu mô hình đoán trọng lượng và gọi thẳng công cụ tính phí, kết quả tình cờ trùng báo giá vẫn không làm chuỗi hợp lệ.

### Những đường đi cần phân biệt

| Chuỗi quan sát được | Đánh giá | Lý do |
| --- | --- | --- |
| Tra đơn A123 → tính phí với 2.5 kg → trả lời | **Đạt** | Đúng phụ thuộc, dữ liệu, điều kiện dừng |
| Tính phí với 2.5 kg → trả lời, không tra đơn | **Không đạt** | Trọng lượng không có căn cứ trong fixture |
| Tra đơn A123 → trả lời “không biết phí” | **Dừng sớm** | Đã có đủ thông tin để gọi tính phí |
| Tra đơn A123 → tính phí → tính phí lần nữa không có lý do → trả lời | **Gọi thừa** | Đã có kết quả đủ dùng nhưng vẫn gọi lại |
| Tra đơn A132 → tính phí → trả lời | **Sai thực thể** | Bước đầu dùng nhầm mã đơn |
| Thiếu tỉnh nhận → hỏi người dùng bổ sung | **Dừng hợp lệ** | Không thể tính đúng khi thiếu tham số bắt buộc |
| Không có quyền xem A123 → không tra, thông báo giới hạn | **Dừng hợp lệ** | Không được vượt quyền để hoàn thành tác vụ |
| Tra đơn trả NOT_FOUND → tự gọi lại vô hạn | **Không đạt** | Không có tiến triển và không có chiến lược dừng |

Các đánh giá trên phụ thuộc **hợp đồng ứng dụng**. Nếu trọng lượng đã được xác minh và lưu trong ngữ cảnh còn hiệu lực, chuỗi hợp lệ có thể **bỏ qua get_order_package**. Vì vậy, không nên áp một chuỗi duy nhất cho mọi trạng thái hội thoại.

## 4. Mô hình hóa đường đi: chuỗi, đồ thị và máy trạng thái

### 4.1. Chuỗi cố định

Nếu nghiệp vụ bắt buộc một thứ tự duy nhất, có thể khai báo:

~~~text
START
  -> get_order_package(orderId=A123)
  -> quote_shipping_fee(destinationProvince=Đà Nẵng, weightKg=2.5)
  -> FINAL_ANSWER
  -> STOP_SUCCESS
~~~

Khi đó oracle có thể chấm khớp chính xác cả **tên tool, đối số, thứ tự, số lần** và **lý do dừng**.

Tuy nhiên, chấm khớp cứng sẽ quá khắt khe nếu có nhiều cách hợp lệ để đạt cùng mục tiêu.

### 4.2. Đồ thị phụ thuộc (partial order)

Một người dùng yêu cầu: “Cho biết phí giao đơn A123 và thời gian dự kiến nhận”.

Giả sử **get_order_package** xác minh trọng lượng; **get_delivery_zone** xác minh tuyến; **quote_shipping_fee** cần cả hai. Hai công cụ đầu có thể thực hiện theo bất kỳ thứ tự nào, thậm chí song song nếu framework cho phép, nhưng bước tính phí phải chờ cả hai.

~~~mermaid
flowchart TD
    A["START"] --> B["get_order_package"]
    A --> C["get_delivery_zone"]
    B --> D["quote_shipping_fee"]
    C --> D
    D --> E["Kiểm tra báo giá / ETA"]
    E --> F["STOP_SUCCESS"]
~~~

Oracle cần chấp nhận cả:

~~~text
get_order_package → get_delivery_zone → quote_shipping_fee → STOP
get_delivery_zone → get_order_package → quote_shipping_fee → STOP
~~~

Nếu **quote_shipping_fee** xuất hiện trước khi có đủ dữ liệu phụ thuộc, đó là lỗi **thứ tự**. Nếu lặp lại get_delivery_zone sau khi đã có kết quả hợp lệ, đó có thể là lỗi **gọi thừa**.

### 4.3. Nhánh điều kiện

Một tác vụ có thể có nhiều đường đi đúng:

- Nếu đơn có trạng thái **CANCELLED**, không cần tính phí giao mới; giải thích rằng đơn không còn ở trạng thái giao hàng.
- Nếu đơn **PROCESSING** và đủ trọng lượng, tiếp tục tính phí.
- Nếu đơn **NOT_FOUND**, hỏi xác minh mã hoặc nêu không tìm thấy.
- Nếu trả về **PENDING** từ công cụ bất đồng bộ, dừng và thông báo đang chờ, hoặc chuyển cho một quy trình giám sát theo hợp đồng.

Trong bộ chấm, mỗi nhánh phải đi kèm **điều kiện kích hoạt** và **hậu điều kiện**. Không nên coi một nhánh khác với đường tham chiếu là sai khi dữ liệu thực tế cho phép nhánh đó.

### 4.4. Invariant: điều không bao giờ được vi phạm

Dù chọn nhánh nào, các bất biến vẫn phải được giữ:

- Không truy cập đơn ngoài quyền được cấp.
- Không tạo đối số giả khi thiếu dữ liệu.
- Không dùng kết quả của đơn A123 để tính phí cho đơn B456.
- Không thực hiện thao tác ghi dữ liệu khi người dùng chưa xác nhận theo chính sách.
- Không gọi lặp tác vụ có tác động phụ nếu không có cơ chế chống trùng.

Một chuỗi có vẻ đạt mục tiêu cuối vẫn **FAIL** nếu vi phạm bất biến nghiêm trọng.

## 5. Điều kiện dừng là một quyết định cần chấm

Ứng dụng dùng tool calling phải xác định **khi nào ngừng gọi công cụ và trạng thái nào nên báo cho người dùng**. Dừng không đơn thuần là lúc mô hình tạo ra một đoạn văn cuối hoặc lúc không còn tool request.

Các loại điều kiện dừng:

| Mã dừng | Khi nào hợp lệ? | Hành vi đáp ứng |
| --- | --- | --- |
| **SUCCESS** | Mục tiêu được kiểm chứng, dữ liệu đủ mới, không vi phạm bất biến | Trả lời dựa trên kết quả và kết thúc |
| **NEEDS_INPUT** | Thiếu thông tin bắt buộc mà không thể tự suy ra an toàn | Hỏi rõ dữ kiện cần bổ sung |
| **NOT_AUTHORIZED** | Thiếu quyền hoặc phê duyệt cần thiết | Dừng, giải thích giới hạn phù hợp |
| **UNRECOVERABLE_ERROR** | Công cụ lỗi không thể khôi phục theo chính sách | Báo lỗi chính xác; không bịa kết quả |
| **RETRY_EXHAUSTED** | Đã sử dụng hết số lần retry hợp lệ | Dừng hoặc chuyển xử lý, nêu trạng thái |
| **BUDGET_LIMIT** | Đạt giới hạn bước, token, chi phí hoặc thời gian | Dừng an toàn, báo chưa hoàn tất nếu đúng |
| **PENDING_EXTERNAL** | Đã tiếp nhận tác vụ nhưng đang chờ hệ thống ngoài | Báo đang xử lý, lưu mã theo dõi nếu có |
| **CANCELLED_BY_USER** | Người dùng yêu cầu dừng | Ngừng hành động tiếp theo, thông báo trạng thái đã xảy ra |

**SUCCESS** khác các loại dừng còn lại: chỉ SUCCESS được phép khẳng định nghiệp vụ đã hoàn tất. Một yêu cầu được tiếp nhận để xử lý bất đồng bộ có thể dừng phiên hội thoại bằng **PENDING_EXTERNAL**, nhưng không được biến thành tuyên bố “đã xử lý xong”.

### Dừng quá sớm (premature stop)

Dừng sớm xảy ra khi mô hình ngừng tác vụ trong khi:

1. Điều kiện đích chưa đạt.
2. Vẫn có bước hợp lệ và cần thiết để tiếp tục.
3. Không có lý do dừng an toàn như thiếu quyền, thiếu thông tin, lỗi không thể khôi phục hoặc hết budget.

Ví dụ: công cụ **get_order_package** trả **weightKg=2.5**, mô hình trả lời “Tôi không biết phí” mà không gọi **quote_shipping_fee** dù công cụ đang sẵn có. Đây là lỗi dừng sớm.

### Dừng quá muộn (overrun / overcalling)

Mô hình đã có đủ bằng chứng để hoàn tất nhưng vẫn thực hiện thêm bước không cần thiết:

~~~text
get_order_package → quote_shipping_fee → quote_shipping_fee
                  → get_order_package → quote_shipping_fee → FINAL
~~~

Lỗi này làm tăng token, phí công cụ, độ trễ p95 và có thể gây tác động trùng nếu tool là thao tác ghi. Khi đánh giá, phải tìm **điểm sớm nhất đã đủ điều kiện dừng** rồi kiểm tra các sự kiện phát sinh sau đó.

### Dừng vì giới hạn không đồng nghĩa thành công

Nếu giới hạn 6 lời gọi bị vượt, lớp điều phối có thể dừng để bảo vệ hệ thống. Nhưng một **BUDGET_LIMIT** như vậy vẫn là **tác vụ chưa hoàn tất**, cần được ghi rõ trong báo cáo. Không được lấy việc “không còn vòng lặp” làm bằng chứng chất lượng tốt.

## 6. Thiết kế tập dữ liệu đánh giá nhiều bước

Một test case có khả năng chấm đường đi cần mô tả **trạng thái ban đầu, công cụ được cấp, dữ liệu trả về từng bước, đồ thị đường đi và trạng thái dừng mong đợi**.

Các trường thiết yếu:

| Trường | Ý nghĩa |
| --- | --- |
| case_id, goal | Mã ca và mục tiêu nghiệp vụ |
| user, conversation_context | Câu hỏi, lịch sử cần thiết, dữ liệu có sẵn |
| available_tools | Công cụ thực sự được đưa cho mô hình |
| permissions, confirmations | Quyền, điều kiện phê duyệt ở thời điểm chạy |
| fixture | Kết quả giả lập và trạng thái của công cụ, bao gồm lỗi |
| expected_steps | Các lời gọi bắt buộc hoặc tập bước tương đương |
| dependencies | Quan hệ bước trước/bước sau; nhánh điều kiện |
| constraints | Số lượt gọi tối đa, số retry, giới hạn tác động |
| expected_stop | Lý do dừng đúng và bằng chứng để dừng |
| expected_answer | Những nội dung bắt buộc, cấm nói hoặc cần trích nguồn |
| severity | Mức rủi ro nếu đi sai đường hoặc dừng sai |

Ví dụ dữ liệu theo JSON Lines (mỗi dòng là một ca). Schema này do **bộ đánh giá của dự án** tự định nghĩa, không phải định dạng Spring AI mặc định:

~~~json
{"case_id":"SHIP-01","goal":"QUOTE_SHIPPING","user":"Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"],"knownWeightKg":null},"fixture":{"A123":{"weightKg":2.5},"quote":{"province":"Đà Nẵng","weightKg":2.5,"amountVnd":34000}},"expected":{"steps":["get_order_package","quote_shipping_fee"],"constraints":{"orderId":"A123","weightKg":2.5,"province":"Đà Nẵng","maxToolCalls":2},"stop":"SUCCESS"},"severity":"medium"}
{"case_id":"SHIP-02","goal":"QUOTE_SHIPPING","user":"Phí giao đơn A123 là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"],"destinationProvince":null},"expected":{"steps":[],"stop":"NEEDS_INPUT","askFor":"destinationProvince"},"severity":"medium"}
{"case_id":"SHIP-03","goal":"QUOTE_SHIPPING","user":"Phí giao đơn B456 tới Đà Nẵng là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"]},"expected":{"steps":[],"stop":"NOT_AUTHORIZED"},"severity":"high"}
{"case_id":"SHIP-04","goal":"QUOTE_SHIPPING","user":"Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"]},"fixture":{"get_order_package":"NOT_FOUND"},"expected":{"steps":["get_order_package"],"stop":"UNRECOVERABLE_ERROR","mustNotCall":"quote_shipping_fee"},"severity":"medium"}
{"case_id":"SHIP-05","goal":"QUOTE_SHIPPING","user":"Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"],"verifiedWeightKg":2.5,"weightFresh":true},"fixture":{"quote":{"amountVnd":34000}},"expected":{"steps":["quote_shipping_fee"],"stop":"SUCCESS"},"severity":"medium"}
{"case_id":"SHIP-06","goal":"QUOTE_SHIPPING","user":"Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?","context":{"tools":["get_order_package","quote_shipping_fee"],"authorizedOrders":["A123"]},"fixture":{"get_order_package":"TIMEOUT_TRANSIENT","retry_then":{"weightKg":2.5},"quote":{"amountVnd":34000}},"expected":{"steps":["get_order_package","get_order_package","quote_shipping_fee"],"stop":"SUCCESS","maxRetries":1},"severity":"medium"}
~~~

Trong ca **SHIP-02**, nếu nghiệp vụ có địa chỉ mặc định đã được người dùng xác nhận và cho phép dùng, nhãn có thể khác. Vì vậy dữ liệu phải mô tả rõ ngữ cảnh và quy tắc định tuyến, tránh suy nhãn chỉ từ câu chữ.

### Những biến thể khó không nên bỏ sót

- Cùng câu hỏi, dữ liệu từ bước trước đã có hoặc đã hết hiệu lực.
- Công cụ trả dữ liệu rỗng, sai schema, timeout hoặc lỗi nghiệp vụ cuối.
- Hai công cụ độc lập có thể chạy hoán đổi thứ tự.
- Một công cụ trả nhiều kết quả cần lọc, dẫn đến một hoặc nhiều nhánh.
- Công cụ có thao tác ghi: cần xác nhận, chống trùng và giới hạn retry.
- Tool trả **ACCEPTED** nhưng nghiệp vụ còn **PENDING**.
- Người dùng thay đổi yêu cầu giữa hai lượt, khiến đường đi cũ không còn đúng.
- Prompt injection trong dữ liệu tool cố khiến model gọi công cụ ngoài nhiệm vụ.
- RAG truy xuất nguồn chưa đủ độ liên quan, cần tìm bổ sung một cách có điều kiện.
- Không đủ budget để hoàn tất: phải ghi nhận dừng có lý do, không tuyên bố thành công.

Tập đánh giá nên bao gồm cả các **ca thành công** và các **ca dừng đúng dù không hoàn thành**. Nếu chỉ chấm khả năng hoàn thành, bộ đánh giá sẽ vô tình thưởng cho việc cố gọi tool khi thiếu quyền hoặc thông tin.

## 7. Xây dựng oracle để chấm chuỗi và điểm dừng

**Oracle** là tập quy tắc độc lập với mô hình để xác định đường đi hợp lệ. Có thể chia thành ba lớp:

1. **Step oracle:** công cụ và đối số của từng lời gọi có hợp lệ ở trạng thái đó không?
2. **Path oracle:** thứ tự, phụ thuộc, nhánh và số lần gọi có hợp lệ cho toàn bộ tác vụ không?
3. **Stop oracle:** trạng thái cuối có đúng loại kết thúc, đủ bằng chứng và không còn bước bắt buộc bị bỏ sót không?

Đây là điều kiện để **PASS** cho một ca yêu cầu hoàn thành:

~~~text
PASS =
    all_required_steps_satisfied
    AND all_tool_arguments_valid
    AND dependency_order_respected
    AND no_forbidden_side_effects
    AND business_goal_verified
    AND stop_reason == SUCCESS
    AND final_answer_grounded
~~~

Với ca **NEEDS_INPUT** hoặc **NOT_AUTHORIZED**, điều kiện PASS khác:

~~~text
PASS =
    forbidden_tools_not_executed
    AND stop_reason_matches_expected
    AND assistant_response_explains_next_valid_action
    AND no_business_invariant_violated
~~~

**Không phải chỉ có một câu trả lời cuối duy nhất được chấp nhận.** Oracle phải gắn với điều kiện và trạng thái, cho phép các cách diễn đạt phù hợp hoặc các đường đi tương đương đã được định nghĩa trước.

### 7.1. Kiểm tra chuỗi cố định

Với SHIP-01, chuỗi yêu cầu:

~~~text
Expected: [get_order_package, quote_shipping_fee]
Observed: [get_order_package, quote_shipping_fee]
Stop: SUCCESS
~~~

PASS nếu cả đối số và đầu ra được xác minh; chỉ so sánh tên công cụ chưa đủ. Chuỗi sau không đạt:

~~~text
Observed: [quote_shipping_fee, get_order_package]
Error: DEPENDENCY_VIOLATION
~~~

### 7.2. Kiểm tra partial order

Nếu hai bước A và B độc lập, và C phụ thuộc cả A lẫn B, đặt ràng buộc:

~~~text
A < C
B < C
Không bắt buộc A < B hoặc B < A
~~~

Một bộ chấm dựa trên DAG sẽ chấp nhận thứ tự A, B, C và B, A, C nhưng bác bỏ C, A, B. Nếu các kết quả có thể đến đồng thời, hãy dùng **correlation ID / dependency events**, tránh kết luận phụ thuộc chỉ bằng thứ tự timestamp rất sát nhau.

### 7.3. Kiểm tra nhánh

Ví dụ nếu **get_order_package** trả NOT_FOUND, nhánh đúng là:

~~~text
get_order_package(NOT_FOUND) -> STOP_UNRECOVERABLE_ERROR
~~~

Nếu trả weightKg=2.5:

~~~text
get_order_package(2.5) -> quote_shipping_fee(2.5) -> STOP_SUCCESS
~~~

Trong cùng một ca đã cố định fixture, chỉ có những nhánh phù hợp với phản hồi thực tế mới hợp lệ.

### 7.4. Dùng phát biểu cuối làm bằng chứng bổ sung

Một assistant có thể ngừng gọi tool và viết “Đã hoàn tất” dù **quote_shipping_fee** chưa trả kết quả. Để chấm stop oracle, phải xác minh **câu trả lời cuối** so với trạng thái đã ghi, thay vì coi một văn bản cuối là STOP_SUCCESS.

Đối với công cụ bất đồng bộ, oracle có thể cho phép **PENDING_EXTERNAL** với lời giải thích phù hợp, dù mục tiêu kinh doanh cuối vẫn chưa xảy ra.

## 8. Đo lường chất lượng chuỗi và điều kiện dừng

Một tỷ lệ success duy nhất không đủ để chỉ ra nguyên nhân. Nên báo riêng các chỉ số:

| Chỉ số | Ý nghĩa | Cách đo |
| --- | --- | --- |
| **Strict trajectory success** | Toàn bộ đường đi và kết thúc đều đạt | Ca PASS mọi oracle / tổng ca |
| **Required-step recall** | Đã thực hiện bao nhiêu bước bắt buộc | Số bước bắt buộc khớp / tổng bước bắt buộc |
| **Step precision** | Bao nhiêu lời gọi là cần thiết và hợp lệ | Lời gọi khớp một bước hợp lệ / tổng lời gọi |
| **Dependency compliance** | Tuân thủ quan hệ trước/sau | Ca không vi phạm phụ thuộc / ca có phụ thuộc |
| **Stop decision accuracy** | Đúng loại dừng theo trạng thái | Ca dừng đúng / tổng ca |
| **Premature stop rate** | Dừng khi còn bước bắt buộc khả thi | Ca dừng sớm / ca có thể tiếp tục |
| **Overcalling rate** | Gọi thêm sau khi đủ điều kiện dừng | Ca gọi thừa / ca đủ điều kiện dừng |
| **Loop / duplicate rate** | Gọi lặp không tạo tiến triển | Ca có vòng lặp hoặc lời gọi trùng / tổng ca |
| **Budget exhaustion rate** | Chạm giới hạn trước khi đạt mục tiêu | Ca dừng vì budget / tổng ca |
| **Verified task success** | Đạt mục tiêu thực theo source of truth | Ca hoàn tất đã kiểm chứng / tổng ca được chấm |

**Mẫu số và cách ghép bước phải được xác định trước**. Một bước bắt buộc có thể được thực hiện bằng một trong nhiều tool tương đương. Nếu cho phép hoán đổi hai bước độc lập, không thể chấm bằng so chuỗi ký tự thuần túy. Ngoài ra, chia kết quả theo **loại công cụ, số bước, số nhánh, mức rủi ro và nguyên nhân dừng**.

### Ví dụ số liệu giả định

Giả sử kiểm thử 100 ca nhiều bước, mỗi ca được phân loại theo **lỗi chính**:

| Kết quả | Số ca |
| --- | ---: |
| Đúng chuỗi và đúng điểm dừng | 68 |
| Dừng sớm | 12 |
| Gọi thừa sau khi đủ dữ liệu | 8 |
| Sai thứ tự/điều kiện phụ thuộc | 6 |
| Dừng vì budget trước khi hoàn thành | 4 |
| Nhánh sai do diễn giải sai tool result | 2 |

**Strict trajectory success = 68/100 = 68%**. Tỷ lệ dừng sớm trên tổng tập là 12%, tỷ lệ gọi thừa là 8%. Đây là **phân bố nhóm lỗi chính**, không đảm bảo một ca chỉ có một lỗi trong thực tế; hệ thống thực nên cho phép nhiều nhãn lỗi và báo thêm mức độ nghiêm trọng.

Giả sử sau thay prompt, strict success tăng lên 75% nhưng nhóm ca có thao tác ghi dữ liệu xuất hiện thêm ba lỗi gọi thừa sau khi đã thành công. Khi đó không thể kết luận bản mới tốt hơn chỉ từ accuracy tổng. Cần đánh giá vi phạm bất biến và tác động thực tế.

### Hiệu suất và chi phí của chuỗi

Số lời gọi càng lớn chưa chắc càng tệ nếu công cụ đang thực hiện những bước cần thiết. Điều cần đo là:

- **Tool calls per verified success**: số lời gọi công cụ trên mỗi ca hoàn thành đã xác minh.
- **Unnecessary call count**: số lời gọi ngoài các bước hợp lệ.
- **Latency p50/p95**: thời gian tổng đến câu trả lời hoặc đến hậu điều kiện đã kiểm chứng.
- **Model tokens per task**: token cho toàn bộ vòng lặp model/tool, không chỉ lần gọi đầu.
- **Cost per verified success**: chi phí mô hình, công cụ, retry và xử lý phụ trợ trên một ca thành công.

Nếu thiếu dữ liệu chi phí hoặc usage, ghi **unknown** thay vì 0. Cần tách **độ trễ phản hồi** khỏi **độ trễ hoàn thành nghiệp vụ**, đặc biệt với tác vụ chạy nền.

## 9. Ghi nhận chuỗi công cụ với Spring AI

Spring AI hỗ trợ công cụ được khai báo qua **@Tool** và cấp cho một request **ChatClient**. Khi model chọn gọi công cụ và framework thực thi, ta có thể ghi nhận **tên tool, đối số, kết quả và thứ tự** trong một lớp giả lập. Đây là cách bắt đầu thực tế khi xây dựng tập đánh giá.

Ví dụ Java dưới đây có hai công cụ chỉ đọc. Mỗi lần chạy tạo một bộ ghi riêng để không lẫn sự kiện giữa các ca:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public final class MultiStepShippingProbe {

    private final ChatClient chatClient;

    public MultiStepShippingProbe(ChatClient.Builder builder) {
        // Kiểm soát các công cụ mặc định trên builder khi chạy đánh giá.
        this.chatClient = builder.build();
    }

    public record ToolEvent(
            int ordinal,
            String tool,
            String arguments,
            String outcome
    ) {}

    public record RunResult(
            String assistantAnswer,
            List<ToolEvent> toolEvents
    ) {}

    public RunResult run(String userQuestion) {
        var tools = new RecordingShippingTools();

        String answer = chatClient.prompt()
                .system("""
                        Bạn là trợ lý báo phí vận chuyển.
                        Muốn tính phí cho một đơn chưa biết khối lượng,
                        trước tiên dùng get_order_package với đúng mã đơn.
                        Sau đó dùng quote_shipping_fee với địa điểm nhận
                        và khối lượng vừa tra được.
                        Không đoán khối lượng hoặc địa chỉ.
                        Nếu thiếu dữ kiện bắt buộc, hỏi bổ sung.
                        Khi đã có báo giá hợp lệ, trả lời rồi dừng,
                        không gọi lại công cụ nếu không có lý do.
                        """)
                .user(userQuestion)
                .tools(tools)
                .call()
                .content();

        return new RunResult(answer, tools.events());
    }

    public static final class RecordingShippingTools {

        private final AtomicInteger counter = new AtomicInteger();
        private final List<ToolEvent> calls =
                new CopyOnWriteArrayList<>();

        @Tool(
                name = "get_order_package",
                description = "Đọc khối lượng đã xác minh cho một mã đơn"
        )
        public String getOrderPackage(
                @ToolParam(description = "Mã đơn của người dùng")
                String orderId
        ) {
            String result = "A123".equals(orderId)
                    ? "{\"orderId\":\"A123\",\"weightKg\":2.5}"
                    : "{\"error\":\"NOT_FOUND\"}";

            calls.add(new ToolEvent(
                    counter.incrementAndGet(),
                    "get_order_package",
                    "orderId=" + orderId,
                    result
            ));
            return result;
        }

        @Tool(
                name = "quote_shipping_fee",
                description = "Báo phí theo tỉnh nhận và khối lượng đã xác minh"
        )
        public String quoteShippingFee(
                @ToolParam(description = "Tỉnh hoặc thành phố nhận hàng")
                String destinationProvince,
                @ToolParam(description = "Khối lượng theo kg")
                double weightKg
        ) {
            boolean valid = "Đà Nẵng".equals(destinationProvince)
                    && Double.compare(weightKg, 2.5) == 0;

            String result = valid
                    ? "{\"amount\":34000,\"currency\":\"VND\"}"
                    : "{\"error\":\"INVALID_QUOTE_INPUT\"}";

            calls.add(new ToolEvent(
                    counter.incrementAndGet(),
                    "quote_shipping_fee",
                    "destinationProvince=" + destinationProvince
                            + ",weightKg=" + weightKg,
                    result
            ));
            return result;
        }

        public List<ToolEvent> events() {
            return List.copyOf(calls);
        }
    }
}
~~~

Gọi thử với **ChatClient.Builder** được cấp từ ứng dụng:

~~~java
var probe = new MultiStepShippingProbe(chatClientBuilder);

var result = probe.run(
        "Phí giao đơn A123 tới Đà Nẵng là bao nhiêu?"
);

System.out.println(result.assistantAnswer());
result.toolEvents().forEach(System.out::println);
~~~

Vì đây là **test double**, giá và dữ liệu đơn hàng đều giả lập, không gửi yêu cầu ra hệ thống thật. Không giả định model sẽ luôn tạo đúng hai lời gọi: bộ chấm cần quan sát hành vi thực tế và trả FAIL nếu mô hình bỏ sót, chọn sai hoặc lặp thêm.

**Giới hạn quan sát:** bộ ghi nằm trong phương thức công cụ chỉ thấy những lời gọi **đã đi đến Java method**. Nếu model sinh request sai schema, framework chặn do quyền, hay dispatcher xử lý lỗi trước khi thực thi thì sự kiện đó có thể không xuất hiện. Khi cần chấm cả lời gọi được *đề nghị* và *được thực thi*, bổ sung instrumentation ở lớp model response / ToolCallback / dispatcher tùy kiến trúc.

### Chấm đường đi quan sát được

Với ca SHIP-01, có thể kiểm tra sơ bộ:

~~~java
static boolean matchesExpectedPath(
        MultiStepShippingProbe.RunResult result
) {
    var events = result.toolEvents();

    if (events.size() != 2) {
        return false;
    }

    boolean firstOk =
            events.get(0).tool().equals("get_order_package")
            && events.get(0).arguments().equals("orderId=A123")
            && events.get(0).outcome().contains("\"weightKg\":2.5");

    boolean secondOk =
            events.get(1).tool().equals("quote_shipping_fee")
            && events.get(1).arguments().contains("weightKg=2.5")
            && events.get(1).outcome().contains("\"amount\":34000");

    return firstOk && secondOk;
}
~~~

Hàm minh họa chỉ kiểm tra **chuỗi lời gọi đã thực thi** của một fixture cố định, chưa chấm sự thật câu trả lời cuối, tỉnh nhận, quyền, dừng vì lý do nào hay lỗi trong dispatcher. Trong một bộ đánh giá thực tế, dùng dữ liệu đối số có cấu trúc thay cho thao tác cắt chuỗi bằng **contains**, kiểm tra chặt chẽ mọi trường và liên kết kết quả với oracle nghiệp vụ.

Đặc biệt, **system prompt yêu cầu dừng không đủ để cưỡng chế giới hạn**. Nếu số bước, số lần retry, thời gian hoặc tác động có ràng buộc nghiêm ngặt, phải thiết lập thêm cơ chế chặn ở phía ứng dụng.

## 10. Thiết kế cơ chế chặn vòng lặp và giới hạn thực thi

Một hệ thống cho phép model gọi tool theo vòng lặp cần có **guard** để bảo vệ tài nguyên và dữ liệu. Guard không thay thế oracle đánh giá nhưng giúp ngăn hành vi lỗi gây tác động thật.

### Những giới hạn nên có

| Giới hạn | Nguy cơ được kiểm soát |
| --- | --- |
| Max model turns | Model tự suy nghĩ/gọi lại quá nhiều vòng |
| Max tool calls | Một lượt hoặc nhiều lượt phát sinh quá nhiều lời gọi |
| Max repeated same-call | Gọi cùng tool với cùng đối số liên tục |
| Max retries per recoverable error | Retry vô hạn sau timeout |
| Deadline / timeout | Treo quy trình hoặc chờ hệ thống ngoài quá lâu |
| Token / cost budget | Chi phí vượt ngân sách |
| Authorization / confirmation gate | Thao tác vượt quyền hoặc thiếu xác nhận |
| Idempotency for side effects | Ghi dữ liệu hai lần nếu retry |
| Tool allowlist | Model gọi công cụ ngoài phạm vi tác vụ |

**Max model turns và max tool calls là hai loại giới hạn khác nhau.** Một model turn có thể đề nghị nhiều tool; tùy tích hợp, chúng có thể được chạy tuần tự hoặc song song. Không thiết kế guard chỉ dựa trên số lượt model nếu rủi ro nằm ở số thao tác thực tế.

Mã giả mô tả bộ điều phối có giới hạn:

~~~text
function runTask(task, policy):
    state = initialize(task)

    while true:
        if goalVerified(state):
            return stop("SUCCESS", answerFromEvidence(state))

        if userCancelled(state):
            return stop("CANCELLED_BY_USER", state)

        if lacksRequiredInput(state):
            return stop("NEEDS_INPUT", askForMissingInput(state))

        if isUnauthorized(state):
            return stop("NOT_AUTHORIZED", state)

        if budgetExceeded(state, policy):
            return stop("BUDGET_LIMIT", state)

        decision = askModelForNextStep(state)

        if decision.isFinalAnswer:
            if goalVerified(state):
                return stop("SUCCESS", decision.answer)
            return stop("PREMATURE_STOP", safeIncompleteAnswer(state))

        for call in decision.toolCalls:
            if budgetWouldBeExceeded(call, state, policy):
                return stop("BUDGET_LIMIT", state)
            if not allowedByDependencies(call, state):
                return stop("DEPENDENCY_VIOLATION", state)
            if not authorizedAndConfirmed(call, state):
                return stop("NOT_AUTHORIZED", state)
            if repeatedWithoutProgress(call, state):
                return stop("NO_PROGRESS_LOOP", state)

            result = executeWithBoundedRetry(call, policy)
            recordStepAndEvidence(state, call, result)

            if result.isTerminalFailure:
                return stop("UNRECOVERABLE_ERROR", state)
~~~

Đây là **mã giả kiến trúc**, không phải một API cụ thể của Spring AI. Nó mô tả cơ chế có thể đặt ở lớp điều phối của ứng dụng. Với các cấu hình tự động xử lý tool call bên trong framework, cần kiểm tra điểm mở rộng phù hợp để bảo đảm guard chạy **trước khi dispatch**. Nếu công cụ cho phép thao tác ghi, backend vẫn phải kiểm quyền và idempotency.

### Phát hiện “không có tiến triển”

Chỉ đếm hai lời gọi giống nhau chưa đủ để xác định vòng lặp. Ví dụ retry một lần sau timeout là hợp lệ. Nên đánh giá:

1. **Tên công cụ, đối số chuẩn hóa** có lặp lại không?
2. Kết quả hoặc trạng thái nghiệp vụ **có khác trước** không?
3. Lần gọi lại **có được chính sách retry cho phép** không?
4. Có **giới hạn số lần và lý do cụ thể** hay không?

Một cách ghi nhận đơn giản:

~~~text
signature = toolName + normalize(arguments) + relevantStateRevision

if signature repeated
   AND noNewEvidence
   AND retryNotAllowed:
       NO_PROGRESS_LOOP
~~~

Với tác vụ đọc dữ liệu thay đổi theo thời gian, cần xét **độ mới** và **thời điểm** trước khi kết luận gọi lại là thừa. Với tác vụ ghi, không bao giờ dùng chỉ số trùng đơn giản thay cho cơ chế idempotency của backend.

## 11. Đánh giá điều kiện dừng trong RAG nhiều bước

Trong ứng dụng RAG có công cụ tìm kiếm, câu hỏi quan trọng là **đã truy xuất đủ bằng chứng để trả lời hay chưa**. Mô hình không nên chỉ dừng ở đoạn trích đầu tiên nếu thiếu dữ kiện bắt buộc; nhưng cũng không nên liên tục tìm kiếm khi đã có các nguồn đáng tin đủ hỗ trợ câu trả lời.

Giả sử câu hỏi: **“Theo chính sách đang hiệu lực, nhân viên toàn thời gian cần làm gì để xin nghỉ bù?”**

Luồng có thể gồm:

1. **search_internal_policy** tìm nguồn theo chủ đề nghỉ bù và đối tượng áp dụng.
2. Kiểm tra **độ liên quan**, **quyền truy cập**, **ngày hiệu lực** và **tính đầy đủ** của kết quả.
3. Nếu thiếu một điều kiện quan trọng, truy xuất có chủ đích lần nữa với query cụ thể hơn.
4. Nếu đã đủ bằng chứng, tổng hợp câu trả lời có căn cứ và dừng.
5. Nếu không có nguồn đáng tin sau các lần truy xuất hợp lệ, nêu giới hạn hoặc hỏi bổ sung, dừng theo chính sách.

~~~mermaid
flowchart TD
    A["Câu hỏi cần nguồn nội bộ"] --> B["Truy xuất tài liệu"]
    B --> C{"Relevance + authority + freshness đạt?"}
    C -->|Không, còn cơ hội tìm| D["Điều chỉnh query có căn cứ"]
    D --> B
    C -->|Đạt| E{"Đủ chứng cứ cho các ý bắt buộc?"}
    E -->|Đủ| F["Trả lời có dẫn nguồn và STOP_SUCCESS"]
    E -->|Thiếu, còn budget| D
    E -->|Thiếu, hết đường hợp lệ| G["Nêu thiếu bằng chứng / STOP_NO_EVIDENCE"]
~~~

Nhánh truy xuất lại chỉ đúng khi **có mục tiêu bổ sung cụ thể và còn budget**. Nếu model gọi cùng query ba lần, thu cùng tài liệu và không có thông tin mới, đó là **loop không tiến triển**.

### Rubric dừng đối với RAG

| Tình huống | Kỳ vọng |
| --- | --- |
| Có đủ nguồn đúng phiên bản và mọi nhận định trọng tâm được hỗ trợ | Trả lời và dừng |
| Chỉ có tài liệu đã hết hiệu lực | Tìm bản hợp lệ nếu có đường truy xuất; không khẳng định theo bản cũ |
| Thiếu điều kiện về đối tượng áp dụng | Tìm bổ sung có chủ đích hoặc nêu không đủ bằng chứng |
| Query lặp lại không tạo nguồn mới | Dừng có giới hạn hoặc thay chiến lược hợp lệ |
| Truy xuất trả nguồn ngoài quyền | Không dùng nguồn và không tiết lộ nội dung |
| Đã có nguồn đáng tin trong ngữ cảnh còn hiệu lực | Có thể bỏ qua truy xuất lại |

Đánh giá **retrieval relevance** và **fact checking** phải tách biệt: một chuỗi có điểm dừng đúng về số lời gọi vẫn có thể trả lời sai, và một câu trả lời tình cờ đúng không bảo đảm chuỗi truy xuất đã tuân thủ chính sách.

Đối với **RAG pipeline truy xuất tự động**, cần xác định bước nào do model quyết định và bước nào do mã ứng dụng điều phối. Lỗi của retriever hoặc bộ phân nhánh pipeline phải được gán về đúng thành phần.

## 12. Kết nối chuỗi với traces và metrics

Một trace hữu ích phải giúp tái dựng **model đã biết gì tại mỗi thời điểm**, **đã yêu cầu tool nào**, **công cụ trả gì**, **vì sao tiếp tục hoặc dừng**.

Spring AI có các khả năng observability qua hệ sinh thái **Micrometer Observation**; tùy phiên bản và cấu hình, dữ liệu quan sát cho ChatClient, model và tool call sẽ khác nhau. Bộ đánh giá nên ánh xạ dữ liệu thực thu được sang một schema nhất quán.

Ví dụ schema của bộ đánh giá (không phải JSON Spring AI mặc định):

~~~json
{
  "case_id": "SHIP-01",
  "run_id": "prompt-v4-model-b",
  "trace_id": "example-trace-id",
  "model_turn": 2,
  "step": 2,
  "tool_call_id": "tool-call-002",
  "tool_name": "quote_shipping_fee",
  "arguments_valid": true,
  "depends_on": ["tool-call-001"],
  "result_status": "SUCCESS",
  "new_evidence": true,
  "goal_verified": true,
  "stop_reason": "SUCCESS",
  "tool_duration_ms": 45,
  "total_duration_ms": 960,
  "input_tokens": 350,
  "output_tokens": 76,
  "estimated_cost_usd": null
}
~~~

Trong thực tế, **stop_reason**, **new_evidence**, **goal_verified** và **depends_on** thường phải được tính hoặc gắn thêm ở lớp đánh giá/điều phối. Đừng khẳng định framework tự động phát toàn bộ các trường đó.

### Sự kiện nên ghi nhận theo thứ tự

| Sự kiện | Thông tin quan trọng |
| --- | --- |
| task.started | Mục tiêu, case ID, snapshot, quyền, phiên bản |
| model.requested_tool | Tên tool, đối số thô, model turn, call ID |
| tool.dispatched | Tool được chấp nhận để chạy hay bị chặn, nguyên nhân |
| tool.finished | Kết quả, thời gian, mã lỗi, correlation ID |
| evidence.updated | Dữ liệu/nguồn mới, revision, độ mới |
| decision.continue | Bước tiếp theo khả thi và lý do |
| decision.stop | Mã dừng, bằng chứng, trạng thái mục tiêu |
| task.completed | Câu trả lời cuối, kết quả oracle và tổng chi phí |

Phân biệt **thời điểm model yêu cầu** và **thời điểm công cụ thực thi**. Một tool request bị chặn trước khi thực thi có thể không xuất hiện trong log bên trong @Tool. Nếu dấu vết không đầy đủ hoặc sampling làm mất sự kiện, đánh dấu **UNOBSERVABLE**, tránh kết luận sai rằng model đã dừng đúng.

### Chẩn đoán độ trễ và chi phí

Với mỗi ca, nên báo:

- Tổng model turns và tool calls.
- Số lần truy xuất lại, retry, gọi trùng và bước vượt điều kiện dừng.
- Thời gian đến **đủ bằng chứng**, thời gian đến **câu trả lời**, thời gian hoàn thành nghiệp vụ nếu khác.
- p50/p95 theo loại tác vụ và số bước.
- Tổng token, chi phí mô hình, phí dịch vụ, chi phí trung bình trên một ca đạt oracle.
- Bản prompt, model, tool schema, pipeline, nguồn dữ liệu, quyền và bộ chấm.

Ví dụ một model mới có tỷ lệ trả lời đúng tăng nhưng liên tục gọi lại công cụ tìm kiếm sau khi đủ chứng cứ, khiến p95 tăng và chi phí trên mỗi ca hoàn thành gấp đôi. Đây là lỗi về **điểm dừng**, kể cả khi kết quả cuối vẫn đúng.

### An toàn dữ liệu trong trace

Tool arguments và kết quả có thể chứa tên, số tiền, địa chỉ hoặc định danh khách hàng. Khi đo, dùng ID của bộ kiểm thử, kết quả xác minh hoặc giá trị băm phù hợp; không ghi toàn bộ nội dung nhạy cảm vào span hay metric label. Tránh các metric có cardinality cực cao từ mã đơn hoặc prompt nguyên văn.

## 13. Những lỗi phổ biến và cách điều tra

| Mã lỗi | Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- | --- |
| **PREMATURE_STOP** | Trả lời khi thiếu bước còn khả thi | Prompt, nhận diện goal hoặc điều kiện dừng | Cập nhật stop oracle; đưa trạng thái thiếu vào ngữ cảnh |
| **OVERCALL_AFTER_SUCCESS** | Gọi tiếp dù đã đủ bằng chứng | Không có state “goal reached” hoặc prompt ép dùng tool | Củng cố dừng theo bằng chứng; guard trước dispatch |
| **DEPENDENCY_VIOLATION** | Bước sau dùng trước khi có kết quả bước trước | Thiếu ràng buộc dữ liệu/phụ thuộc | Kiểm tra DAG và tiền điều kiện |
| **WRONG_BRANCH** | Tool trả lỗi nhưng model tiếp tục nhánh thành công | Diễn giải kết quả sai | Chuẩn hóa trạng thái công cụ, thêm nhánh lỗi vào dataset |
| **NO_PROGRESS_LOOP** | Gọi cùng tool/args, không có kết quả mới | Không ghi trạng thái, retry không giới hạn | Phát hiện chữ ký lặp, giới hạn retry |
| **DUPLICATE_SIDE_EFFECT** | Tạo hai bản ghi/giao dịch | Timeout và retry thiếu idempotency | Kiểm soát thao tác tại backend |
| **BUDGET_EXHAUSTED** | Hết lượt/token trước khi đủ dữ liệu | Tool kém hiệu quả, query rộng, vòng lặp | Phân tích bước thừa và điều chỉnh budget hợp lý |
| **UNSUPPORTED_SUCCESS_CLAIM** | Báo hoàn tất dù backend chỉ ACCEPTED | Nhầm trạng thái trung gian và kết quả cuối | Gắn oracle nghiệp vụ, đổi thông điệp đang chờ |
| **MISSING_AUTH_GUARD** | Thực hiện bước bị cấm | Chỉ dựa vào prompt để kiểm quyền | Chặn ở lớp ứng dụng/backend |
| **OBSERVABILITY_GAP** | Trace không có call nhưng backend đã chạy | Thiếu hook, sampling, correlation ID | Bổ sung sự kiện ở dispatcher/backend |

Khi phân tích một ca lỗi, lần lượt hỏi:

1. **Gold path và stop condition** có thực sự phù hợp với mục tiêu, công cụ và quyền lúc đó không?
2. **Trạng thái đầu** và dữ liệu đã có có được truyền đầy đủ cho mô hình và oracle không?
3. Mô hình đã **đề nghị** những tool call nào và với đối số nào?
4. Lớp điều phối đã **cho chạy, chặn hoặc retry** những yêu cầu nào?
5. Mỗi tool result có đem lại **bằng chứng mới** hay chỉ lặp dữ liệu?
6. Ở bước nào **mục tiêu đã đủ điều kiện dừng**? Các bước sau đó có cần thiết không?
7. Câu trả lời cuối có **đúng với trạng thái đã kiểm chứng** không?

Trình tự này giúp phân biệt lỗi mô hình, lỗi tích hợp tool, lỗi dữ liệu RAG và lỗi instrumentation. Sửa prompt sẽ không giải quyết được vấn đề nếu backend bị timeout và retry ghi dữ liệu hai lần.

## 14. Đánh giá hồi quy giữa prompt, model và pipeline

Một thay đổi nhỏ ở mô tả công cụ hoặc system prompt có thể khiến model gọi công cụ nhiều hơn, dừng sớm hơn hoặc chọn nhánh khác. Bộ đánh giá nên kiểm tra **cùng một tập ca với fixture cố định**, giữ cả các ca dễ và khó.

Quy trình gợi ý:

1. **Cố định dữ liệu:** snapshot kết quả tool, quyền, mốc thời gian, danh sách công cụ, rule oracle.
2. **Ghi version:** prompt, model, model settings, tool schema, retriever, pipeline RAG và evaluator.
3. **Chạy cả ca bình thường và ca biên:** nhiều bước, thiếu dữ liệu, không đủ quyền, lỗi giữa chuỗi, dữ liệu đã có và retry.
4. **Lưu trajectory chi tiết:** thay vì chỉ lấy câu trả lời và điểm tổng.
5. **So sánh theo cùng mẫu số:** strict success, premature stop, overcalling, loop, vi phạm quyền, p95 và chi phí.
6. **Điều tra những ca hồi quy:** xác định bước đầu tiên khiến đường đi mới lệch khỏi điều kiện mong đợi.
7. **Kiểm tra độ biến thiên:** nếu model có tính ngẫu nhiên, chạy nhiều lần và báo tỷ lệ PASS cùng mức biến động.

Ví dụ kết quả giả định:

| Chỉ số trên cùng tập 200 ca | Phiên bản A | Phiên bản B |
| --- | ---: | ---: |
| Strict trajectory success | 77% | 83% |
| Premature stop rate | 11% | 6% |
| Overcalling rate | 4% | 9% |
| Tool calls trung bình/ca | 2,1 | 2,8 |
| p95 thời gian trả lời | 2,6 giây | 3,5 giây |
| Lỗi lặp thao tác ghi có tác động | 0 | 2 |

Phiên bản B giảm dừng sớm nhưng gọi thừa nhiều hơn và xuất hiện lỗi tác động trùng. Nếu các lỗi này liên quan dữ liệu hoặc giao dịch thật, không thể quyết định phát hành chỉ dựa trên việc strict success tăng. Phải đánh giá mức rủi ro, các chặn an toàn và tác động của chi phí/độ trễ.

Không áp một ngưỡng cố định cho mọi hệ thống. Tác vụ RAG chỉ đọc có thể chấp nhận một lần tìm kiếm bổ sung hợp lý; hệ thống thao tác tài chính cần quy định nghiêm ngặt về quyền, xác nhận, thứ tự, idempotency và điều kiện dừng.

## 15. Bài thực hành

**Bối cảnh:** Trợ lý Spring AI báo phí giao đơn A123 đến Đà Nẵng. Công cụ đầu trả trọng lượng 2,5 kg; công cụ thứ hai trả báo giá 34.000 VND.

**Yêu cầu thực hiện:**

1. Dùng **MultiStepShippingProbe** để ghi toàn bộ công cụ và thứ tự thực thi.
2. Tạo ít nhất tám ca, gồm đường đi thành công, thiếu tỉnh nhận, sai quyền, sai mã đơn, tool trả NOT_FOUND, lỗi tạm thời có retry, dừng sớm và gọi thừa.
3. Viết **step oracle** kiểm tra đối số, **path oracle** kiểm tra phụ thuộc và **stop oracle** xác minh lý do kết thúc.
4. Thêm ca có **trọng lượng đã xác minh trong ngữ cảnh**; chấp nhận chỉ gọi công cụ tính phí.
5. Tạo ca nhiều bước độc lập với **get_delivery_zone** để kiểm tra partial order thay vì đòi thứ tự cố định.
6. Cố ý cấu hình một prompt khiến model gọi lặp công cụ, rồi áp giới hạn lượt gọi và phân loại dừng **BUDGET_LIMIT**.
7. So sánh hai phiên bản prompt: strict success, tỷ lệ dừng sớm, tỷ lệ gọi thừa, số lời gọi trung bình và p95.
8. Với một ca RAG, tạo kết quả tìm kiếm chưa đủ chứng cứ, đo liệu model truy xuất có chủ đích hay dừng và kết luận thiếu căn cứ.

**Câu hỏi suy luận:**

- Hai công cụ độc lập chạy theo thứ tự ngược nhau có phải lỗi trajectory không?
- Khi tool trả HTTP 202/ACCEPTED, có được báo tác vụ đã hoàn tất không?
- Vì sao “mô hình đã trả lời” không chứng minh quyết định dừng là đúng?
- Làm sao phân biệt retry hợp lệ sau timeout với vòng lặp không tiến triển?
- Nếu giới hạn max tool calls chặn một vòng lặp, ta nên báo SUCCESS hay BUDGET_LIMIT?
- Một câu trả lời RAG đúng nhưng phải gọi cùng truy vấn năm lần có thể được chấm thế nào?

## 16. Những điều cần ghi nhớ

- **Chấm cả đường đi, không chỉ câu trả lời cuối.** Mỗi bước cần đúng tool, đúng đối số, đúng thứ tự hoặc quan hệ phụ thuộc và không vi phạm bất biến.
- **Điểm dừng là một quyết định có thể sai.** Dừng sớm bỏ sót bước cần thiết; dừng muộn làm tăng chi phí, độ trễ và rủi ro thao tác trùng.
- **Nhãn dừng phải theo trạng thái.** SUCCESS, NEEDS_INPUT, NOT_AUTHORIZED, PENDING_EXTERNAL và BUDGET_LIMIT là những kết quả khác nhau; chỉ SUCCESS mới xác nhận hoàn tất.
- **Đường đi hợp lệ có thể có nhánh và song song.** Dùng state machine, DAG và oracle theo điều kiện khi một chuỗi cố định không đủ mô tả nghiệp vụ.
- **Dùng bằng chứng độc lập để xác minh.** Tool response, trạng thái nghiệp vụ và nguồn RAG có thẩm quyền giúp chấm đúng điều kiện dừng và chất lượng câu trả lời.
- **Observability phải ghi cả tiến triển lẫn nguyên nhân dừng.** Kết nối model turns, tool calls, traces, metrics, token, chi phí và p95 để giải thích suy giảm chất lượng qua phiên bản prompt/model/pipeline.
- **Giới hạn và quyền phải được cưỡng chế ở lớp ứng dụng.** Prompt và bộ đánh giá giúp phát hiện lỗi; guard, xác thực và idempotency giúp bảo vệ thao tác thật.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): khai báo công cụ, truyền cho ChatClient và hành vi thực thi.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): nền tảng quan sát hoạt động của model, ChatClient và công cụ.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): cách tổ chức dữ liệu observation và mối liên hệ với metrics, traces.

Tên API, tùy chọn điều phối tool và thuộc tính observability có thể khác nhau giữa các phiên bản Spring AI. Khi tích hợp vào ứng dụng cụ thể, hãy đối chiếu với phiên bản thư viện và hợp đồng nghiệp vụ đang sử dụng.
