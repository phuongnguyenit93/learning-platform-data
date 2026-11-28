# Đánh giá lựa chọn công cụ và tính đúng của đối số

Khi xây dựng ứng dụng Spring AI có **tool calling**, việc mô hình quyết định gọi một công cụ chỉ là bước đầu. Để hoàn thành tác vụ đúng, mô hình còn phải **chọn đúng công cụ** trong số các công cụ được cấp và **truyền đối số chính xác, có căn cứ, hợp lệ theo schema lẫn quy tắc nghiệp vụ**.

Hãy xét trợ lý chăm sóc khách hàng có ba công cụ: tra cứu trạng thái đơn hàng, tra cứu chính sách và ước tính phí vận chuyển. Người dùng hỏi: “Đơn A123 của tôi đã giao chưa?”. Nếu mô hình gọi công cụ tìm chính sách thì sai lựa chọn công cụ. Nếu gọi công cụ tra cứu đơn hàng nhưng truyền mã **A132** thì sai đối số. Cả hai lỗi đều có thể làm câu trả lời cuối thiếu tin cậy, dù hệ thống đã thực hiện một tool call thành công về mặt kỹ thuật.

Trong phạm vi **SPRING_AI_EVALUATION_OBSERVABILITY**, bài học này hướng dẫn cách xây dựng tập dữ liệu, gán nhãn, chấm điểm lựa chọn tool và đối số, rồi nối kết các lỗi đó với metrics, traces, chi phí và độ trễ. Mục tiêu là phát hiện khi chất lượng giảm sau một thay đổi về prompt, model, công cụ hoặc pipeline RAG.

## 1. Kết quả học tập

Sau khi học xong, bạn có thể:

1. Phân biệt lỗi **có gọi hay không**, lỗi **chọn công cụ**, lỗi **đối số**, lỗi **thực thi** và lỗi **dùng kết quả**.
2. Viết hợp đồng cho mỗi công cụ gồm tên, mục đích, schema, điều kiện sử dụng, quyền và tác động bên ngoài.
3. Thiết kế tập ca kiểm thử có nhãn công cụ đúng, những công cụ thay thế được chấp nhận và quy tắc kiểm tra từng đối số.
4. Đánh giá đối số ở nhiều tầng: JSON/schema, ngữ nghĩa, ngữ cảnh, quyền và ràng buộc nghiệp vụ.
5. Dùng Java và Spring AI để ghi nhận công cụ đã thực thi cùng đối số thực tế, so sánh với kỳ vọng.
6. Tính chỉ số lựa chọn công cụ, độ đúng đối số và tỷ lệ hoàn thành luồng tool calling; điều tra lỗi qua traces và dữ liệu vận hành.

## 2. Tách các tầng của một lần tool calling

Một tool call đi qua nhiều quyết định:

~~~mermaid
flowchart TD
    A["Yêu cầu người dùng + ngữ cảnh"] --> B{"Có cần gọi công cụ?"}
    B -->|Không| C["Trả lời / hỏi thêm / nêu giới hạn"]
    B -->|Có| D["Chọn công cụ thích hợp"]
    D --> E["Sinh tên và các đối số"]
    E --> F{"Schema, ngữ nghĩa, quyền hợp lệ?"}
    F -->|Không| G["Chặn / yêu cầu bổ sung / sửa trong giới hạn cho phép"]
    F -->|Có| H["Thực thi công cụ"]
    H --> I["Đọc kết quả, kiểm tra căn cứ"]
    I --> J["Trả lời hoặc thực hiện bước kế tiếp"]
~~~

Sơ đồ mô tả **các bước cần kiểm thử**, không khẳng định mọi ứng dụng dùng cùng cơ chế thực thi. Một hệ thống có thể tách bộ kiểm tra quyền khỏi tool dispatcher hoặc xử lý nhiều lời gọi song song.

| Tầng | Câu hỏi đánh giá | Ví dụ |
| --- | --- | --- |
| Quyết định gọi | Có cần công cụ ở thời điểm này không? | Không tra cứu đơn hàng dù cần dữ liệu hiện tại |
| **Lựa chọn tool** | Đã chọn đúng năng lực cần dùng chưa? | Dùng công cụ tìm chính sách để tra trạng thái đơn |
| **Đối số** | Giá trị và cấu trúc truyền vào có đúng không? | Gửi **orderId=A132** thay cho **A123** |
| Thực thi | Công cụ có được phép chạy và trả kết quả thành công không? | Timeout, thiếu token xác thực, lỗi mạng |
| Sử dụng kết quả | Câu trả lời có phản ánh đúng dữ liệu nhận được không? | Tool trả “đang vận chuyển” nhưng trả lời “đã giao” |

**Phạm vi của bài:** tập trung vào hai hàng in đậm. Các tầng còn lại cần được đo riêng để tránh gán nhầm lỗi mô hình, lỗi cấu hình và lỗi hệ thống.

## 3. Hiểu đúng thế nào là “chọn đúng công cụ”

Một công cụ thường có:

- **Tên định danh** duy nhất trong tập công cụ cấp cho yêu cầu.
- **Mô tả tác vụ** và điều kiện nên/không nên sử dụng.
- **Schema đầu vào:** tên tham số, kiểu dữ liệu, thuộc tính bắt buộc hoặc tùy chọn, enum, giới hạn.
- **Quyền và tác động:** chỉ đọc hay có thể thay đổi dữ liệu; có cần xác thực, xác nhận hoặc khóa chống gọi trùng không.
- **Định nghĩa đầu ra và lỗi:** kết quả gì được trả về, xử lý trường hợp không tìm thấy hoặc timeout.

Ví dụ một catalog có thể được mô tả theo bảng sau:

| Công cụ | Mục đích | Đối số | Điều kiện sử dụng |
| --- | --- | --- | --- |
| **get_order_status** | Đọc trạng thái hiện tại của một đơn | **orderId**: chuỗi, bắt buộc | Có mã đơn và quyền xem đơn |
| **search_internal_policy** | Truy xuất văn bản chính sách nội bộ | **query**: chuỗi, bắt buộc; **effectiveDate**: ngày, tùy chọn | Cần trích nguồn chính sách được phân quyền |
| **estimate_shipping_fee** | Ước tính phí vận chuyển | **destinationProvince**: chuỗi; **weightKg**: số dương | Có đích nhận và cân nặng |
| **create_refund_request** | Tạo yêu cầu hoàn tiền | **orderId**, **amount**, **reason** | Đã xác nhận, đúng quyền và mức tiền được phép |

**“Đúng tool” phải xét theo ý định và dữ kiện của người dùng**, không chỉ theo sự giống nhau giữa câu hỏi với tên hoặc mô tả công cụ.

### Một số tình huống phân biệt

| Yêu cầu và ngữ cảnh | Tool phù hợp | Tool sai thường gặp |
| --- | --- | --- |
| “Kiểm tra trạng thái đơn A123”, có quyền xem | get_order_status | search_internal_policy |
| “Quy định bảo hành trong tài liệu nội bộ là gì?”, chưa có tài liệu trong context | search_internal_policy | get_order_status |
| “Ước tính phí gửi kiện 2 kg đến Đà Nẵng”, đủ thông tin | estimate_shipping_fee | get_order_status |
| “Tóm tắt đoạn chính sách tôi vừa dán”, đã có đủ nội dung | Không cần tool | search_internal_policy bị gọi thừa |
| “Hoàn tiền đơn A123 ngay”, chưa hoàn tất xác nhận bắt buộc | Hỏi xác nhận, chưa thực thi | create_refund_request chạy sớm |
| “Tra cứu đơn của tôi”, thiếu mã và hệ thống không cho tra theo tài khoản | Hỏi thêm mã | get_order_status với mã do mô hình tự bịa |

Mô hình có thể được cấp nhiều công cụ cùng giải quyết hợp lệ một nhu cầu. Ví dụ tra cứu tài liệu qua **search_policy_by_keyword** hoặc **search_policy_by_semantics** đều có thể đúng nếu chất lượng và điều kiện truy xuất cho phép. Trong trường hợp đó, nhãn chuẩn nên chứa **tập công cụ được chấp nhận**, không ép một tên duy nhất do người viết bộ dữ liệu chọn tùy ý.

Ngược lại, công cụ chỉ có tên gần giống nhau **không có nghĩa là thay thế được nhau**: **get_order_status** đọc trạng thái, còn **update_order_status** sửa trạng thái là hai năng lực khác nhau, có mức rủi ro khác nhau.

## 4. Xây dựng hợp đồng và rubric đánh giá

Trước khi chấm mô hình, nhóm phát triển phải thống nhất thế nào là một lời gọi hợp lệ. Với mỗi tool, ghi rõ:

1. **Nhiệm vụ:** kết quả mà người dùng mong đợi và những nghiệp vụ không được áp dụng công cụ này.
2. **Điều kiện trước khi gọi:** dữ liệu sẵn có, quyền truy cập, xác nhận, trạng thái hội thoại, độ mới cần thiết.
3. **Các đối số:** ý nghĩa từng trường, nguồn dữ liệu hợp lệ, chuẩn biểu diễn, cách kiểm tra và giá trị mặc định nếu được phép.
4. **Kết quả sau khi gọi:** giá trị trả về, ngoại lệ, ngưỡng timeout, cho phép retry hay không, tác động phụ.
5. **Quy tắc chấm:** công cụ chấp nhận, các giá trị tương đương, thứ tự lời gọi, giới hạn số lần, các lỗi nghiêm trọng.

Ví dụ rubric cho **get_order_status**:

| Trường/tiêu chí | Quy tắc |
| --- | --- |
| tool.name | Phải là **get_order_status** |
| orderId | Bắt buộc; phải trùng mã đơn người dùng đã cung cấp hoặc mã được xác minh từ ngữ cảnh được phép |
| Quyền | Người dùng được xem đơn tương ứng; không dựa vào mã đoán để vượt quyền |
| Chuẩn hóa | Có thể chấp nhận khoảng trắng thừa hoặc chữ thường nếu backend công bố mã không phân biệt hoa/thường |
| Số lần gọi | Thông thường 1; thêm lần chỉ khi retry hợp lệ và có bằng chứng |
| Kết quả chấm | **PASS** khi chọn đúng tool và tất cả kiểm tra đối số/quyền đều đạt |

Các quy tắc chuẩn hóa chỉ là ví dụ; nếu mã đơn phân biệt hoa/thường, phải so sánh đúng từng ký tự. Đừng tự thay đổi chuẩn dữ liệu khi chấm.

### Đối số đúng có nhiều lớp

| Lớp | Cần kiểm tra | Ví dụ sai |
| --- | --- | --- |
| 1. Cú pháp/schema | JSON parse được, tên trường chính xác, đúng kiểu, đủ trường bắt buộc | **weightKg="hai ký"** khi schema yêu cầu number |
| 2. Giá trị và miền | Không rỗng, giá trị thuộc enum, phạm vi hợp lệ, ngày tháng đúng định dạng | **weightKg=-2**, ngày không tồn tại |
| 3. Ngữ nghĩa/ngữ cảnh | Giá trị phản ánh đúng yêu cầu và dữ kiện đáng tin | Người dùng nói A123, truyền A132 |
| 4. Quyền và nghiệp vụ | Đối số không vượt quyền, tiền tệ/khách hàng/tenant phù hợp, tác động được xác nhận | Yêu cầu hoàn tiền 150.000 nhưng tool nhận 1.500.000 |
| 5. Tính nhất quán liên bước | Đối số ở bước sau dùng đúng kết quả có nguồn gốc từ bước trước | Đọc đơn A123 rồi hoàn tiền cho A132 |

**Schema hợp lệ không đảm bảo đối số đúng.** Một chuỗi **A132** có thể đáp ứng kiểu String và regex mã đơn hoàn hảo, nhưng vẫn sai nếu người dùng yêu cầu A123. Ngược lại, cùng một địa chỉ có thể được viết nhiều cách hợp lệ nên so khớp chuỗi tuyệt đối có thể chấm oan.

## 5. Thiết kế bộ dữ liệu (evaluation dataset)

Mỗi ca nên chứa đủ thông tin để tái hiện quyết định:

- **case_id, task, user:** định danh ca, nhóm nghiệp vụ và câu hỏi.
- **context:** lịch sử liên quan, quyền, dữ liệu đã có, múi giờ/ngày đánh giá, danh sách công cụ thực sự được cấp.
- **expected_calls:** tập hoặc chuỗi công cụ kỳ vọng; tên công cụ và quy tắc xác minh đối số.
- **allowed_alternatives:** các tool hoặc biểu diễn đối số tương đương được chấp nhận.
- **constraints:** giới hạn số lần gọi, xác nhận, quyền, thứ tự và điều kiện dừng.
- **reason, severity:** căn cứ của nhãn, mức nghiêm trọng khi sai.

Đừng chỉ lưu câu hỏi và tên tool mong đợi. Nếu thiếu quyền hoặc thông tin đã có từ lượt trước, cùng câu hỏi có thể cần hành vi khác.

Ví dụ tập ca ở dạng JSON Lines (mỗi dòng là một đối tượng):

~~~json
{"case_id":"ORDER-01","user":"Trạng thái hiện tại của đơn A123 là gì?","context":{"available_tools":["get_order_status","search_internal_policy"],"authorized_order_ids":["A123"]},"expected":{"calls":[{"tool":"get_order_status","args":{"orderId":"A123"}}],"max_calls":1},"severity":"high"}
{"case_id":"POLICY-01","user":"Tìm quy định bảo hành hàng điện tử trong kho nội bộ","context":{"available_tools":["get_order_status","search_internal_policy"],"policy_in_context":false,"authorized":true},"expected":{"calls":[{"tool":"search_internal_policy","args_rules":{"query_contains_concepts":["bảo hành","hàng điện tử"]}}],"max_calls":1},"severity":"medium"}
{"case_id":"SHIP-01","user":"Ước tính phí giao kiện 2 kg đến Đà Nẵng","context":{"available_tools":["estimate_shipping_fee"],"shipping_origin":"Hà Nội"},"expected":{"calls":[{"tool":"estimate_shipping_fee","args":{"destinationProvince":"Đà Nẵng","weightKg":2.0}}],"max_calls":1},"severity":"medium"}
{"case_id":"ORDER-02","user":"Tra cứu đơn của tôi","context":{"available_tools":["get_order_status"],"order_id":null,"lookup_by_account_allowed":false},"expected":{"calls":[],"next_action":"ASK_FOR_ORDER_ID"},"severity":"medium"}
{"case_id":"REFUND-01","user":"Hoàn tiền đơn A123","context":{"available_tools":["create_refund_request"],"confirmation":false,"authorized":true},"expected":{"calls":[],"next_action":"ASK_FOR_CONFIRMATION"},"severity":"critical"}
~~~

Các trường **args_rules**, **severity**, **max_calls** và **next_action** là **schema do bộ đánh giá tự định nghĩa** để chấm, không phải định dạng đầu vào mặc định của Spring AI.

Với ca POLICY-01, so sánh toàn bộ chuỗi **query** theo từng ký tự là không hợp lý: “bảo hành thiết bị điện tử” và “quy định bảo hành hàng điện tử” đều có thể là truy vấn tốt. Rubric có thể kiểm tra các khái niệm cần có, hoặc dùng bộ đánh giá relevance độc lập. Với ca ORDER-01, mã đơn A123 lại cần khớp chặt chẽ; chỉ gần giống về ngữ nghĩa là không đủ.

### Tạo các cặp thử đối chứng

Một bộ dữ liệu tốt cần các cặp khác nhau ở một điều kiện quan trọng:

| Ca A | Ca B | Điều cần phát hiện |
| --- | --- | --- |
| Trạng thái đơn **A123** | Trạng thái đơn **A132** | Mô hình có giữ đúng mã đơn không |
| 2 kg gửi Đà Nẵng | 20 kg gửi Đà Nẵng | Có đánh mất chữ số hoặc đơn vị không |
| Tìm chính sách trong kho chưa truy xuất | Tóm tắt chính sách đã có trong context | Có gọi thừa khi nguồn đã sẵn không |
| Hoàn tiền đã xác nhận | Hoàn tiền chưa xác nhận | Có vượt quy trình xác nhận không |
| Được xem đơn A123 | Không có quyền xem đơn A123 | Có nhầm thông tin nhận diện với quyền truy cập không |
| Hôm nay theo múi giờ Việt Nam | Hôm nay theo múi giờ khác | Có suy sai ngày tham chiếu không |

Chú ý phân tầng dữ liệu theo độ khó, loại tham số, công cụ đọc/ghi và rủi ro; tách tập dùng để tinh chỉnh prompt khỏi tập kiểm tra cuối nhằm tránh “học thuộc” ví dụ.

## 6. Kiểm tra tính đúng của đối số

### 6.1. Cú pháp và JSON Schema

Kiểm tra trước tiên liệu đối số có phân tích cú pháp được và đúng định nghĩa của công cụ hay không:

~~~json
{
  "name": "estimate_shipping_fee",
  "description": "Ước tính phí vận chuyển dựa vào tỉnh nhận và khối lượng",
  "parameters": {
    "type": "object",
    "properties": {
      "destinationProvince": {
        "type": "string",
        "description": "Tỉnh hoặc thành phố nhận hàng"
      },
      "weightKg": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": "Khối lượng tính bằng kg"
      }
    },
    "required": ["destinationProvince", "weightKg"],
    "additionalProperties": false
  }
}
~~~

Ví dụ trên là **minh họa schema lý tưởng** cho một công cụ, không khẳng định Spring AI tự phát sinh đầy đủ mọi ràng buộc như **exclusiveMinimum** hay **additionalProperties** từ mọi chữ ký Java. Khi triển khai, phải đối chiếu với schema thực sự gửi cho model và bổ sung kiểm tra ở phía ứng dụng nếu cần.

| Đối số nhận được | Schema | Kết luận |
| --- | --- | --- |
| destinationProvince = “Đà Nẵng”; weightKg = 2 | Hợp lệ | Chưa kết luận đúng nghiệp vụ |
| destinationProvince = “Đà Nẵng”; weightKg = -2 | Sai | Phạm điều kiện số dương |
| destinationProvince = “Đà Nẵng”; weightKg = “2 kg” | Sai | Sai kiểu dữ liệu number |
| destinationProvince = “Đà Nẵng” | Sai | Thiếu weightKg bắt buộc |
| destinationProvince = “Huế”; weightKg = 2 | Hợp lệ | Vẫn sai ngữ nghĩa nếu người dùng nói Đà Nẵng |

JSON Schema chỉ là lớp kiểm tra ban đầu. Không được giao toàn bộ trách nhiệm xác thực nghiệp vụ cho mô hình hoặc cho việc framework parse JSON thành công.

### 6.2. Grounding: đối số lấy từ đâu?

Với mỗi trường quan trọng, lưu **nguồn của giá trị**:

- Người dùng nói trực tiếp trong lượt hiện tại.
- Lịch sử hội thoại còn hiệu lực.
- Hệ thống xác thực hoặc thông tin máy chủ đáng tin cậy.
- Kết quả công cụ ở bước trước đã xác minh.
- Giá trị mặc định được nghiệp vụ công bố rõ.

Đối số được mô hình tự suy ra từ một giả định không có căn cứ phải bị đánh dấu **ungrounded**, ngay cả khi có dạng hợp lệ.

Ví dụ: người dùng nói “Tìm đơn của tôi” nhưng không cho mã. Nếu backend chỉ cho tra theo **orderId**, mô hình không được tự điền **A123** vì từng thấy mã đó ở ví dụ khác. Hành vi đúng là yêu cầu mã đơn hoặc dùng một công cụ tra theo tài khoản đã được cấp quyền nếu hệ thống có hỗ trợ.

### 6.3. Chuẩn hóa và tương đương ngữ nghĩa

Không phải trường nào cũng so sánh được bằng dấu bằng:

| Loại đối số | Cách so sánh phù hợp |
| --- | --- |
| Mã đơn, ID, mã giao dịch | So sánh chính xác theo định nghĩa của hệ thống; không fuzzy matching |
| Tiền và tiền tệ | So sánh số thập phân và currency; kiểm tra quy tắc làm tròn |
| Ngày/giờ | Chuyển về mốc thời gian có múi giờ, xét ngày tham chiếu của ca |
| Khối lượng/khoảng cách | Chuẩn hóa đơn vị trước khi so sánh |
| Địa danh | Chuẩn hóa theo danh mục địa lý đáng tin, tránh gộp nhầm địa danh cùng tên |
| Truy vấn tìm kiếm | Đánh giá độ bao phủ ý định, điều kiện lọc và relevance của kết quả |
| Enum nghiệp vụ | So với tập giá trị hợp lệ; tránh tự tạo trạng thái mới |

Ví dụ “9 giờ sáng ngày mai” cần được diễn giải theo **ngày và múi giờ cố định trong test case**. Nếu ngày tham chiếu thay đổi qua mỗi lần chạy mà không đóng băng, bài kiểm thử có thể báo sai khác do môi trường chứ không do mô hình.

Đối với tiền, nên dùng kiểu thập phân chính xác như **BigDecimal** trong Java và chấm cả đơn vị **VND/USD**; dùng **double** tùy tiện có thể dẫn đến sai số biểu diễn.

### 6.4. Quyền và ràng buộc nghiệp vụ

Một yêu cầu gọi **create_refund_request** có thể có mọi trường đúng kiểu nhưng vẫn bị cấm vì:

- Khách hàng chưa xác nhận hành động.
- Đơn hàng không thuộc phạm vi tài khoản hiện tại.
- Số tiền vượt số dư được hoàn.
- Đơn đã được hoàn trước đó, gọi lại có nguy cơ trùng giao dịch.
- Cần lý do nghiệp vụ bắt buộc nhưng mô hình tự điền một lý do tùy ý.

Các giá trị **tenantId, userId, role, approvalStatus** nên do phía máy chủ đáng tin cung cấp khi có thể; đừng tin vào những trường mà mô hình tự sinh để chứng minh quyền của chính nó. Với công cụ có tác động, kiểm tra quyền ở backend là bắt buộc, không chỉ là một mục trong rubric đánh giá offline.

## 7. Quan sát lời gọi bằng Spring AI

Spring AI cho phép mô tả công cụ Java bằng **@Tool**, diễn giải tham số bằng **@ToolParam** và cung cấp công cụ cho **ChatClient** ở mức từng request. Có thể tạo một **test double** để ghi nhận tên tool và tham số đã thực thi mà không truy cập hệ thống nghiệp vụ thật.

Ví dụ sau dùng hai công cụ giả lập. Trong ứng dụng Spring Boot đã cấu hình ChatModel tương thích tool calling, có thể cấp **ChatClient.Builder** cho lớp kiểm thử:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public final class ToolSelectionProbe {

    private final ChatClient chatClient;

    public ToolSelectionProbe(ChatClient.Builder builder) {
        // Builder dùng cho đánh giá phải được kiểm soát, không gắn
        // thêm defaultTools không được ghi nhận.
        this.chatClient = builder.build();
    }

    public record CapturedCall(
            String toolName,
            String argumentName,
            String argumentValue
    ) {}

    public record RunResult(String answer, List<CapturedCall> calls) {}

    public RunResult run(String question) {
        var tools = new RecordingTools();

        String answer = chatClient.prompt()
                .system("""
                        Bạn là trợ lý đơn hàng.
                        Chỉ dùng get_order_status để tra cứu trạng thái đơn.
                        Chỉ dùng search_internal_policy để tìm quy định nội bộ.
                        Không đoán mã đơn hoặc dữ liệu không có trong ngữ cảnh.
                        """)
                .user(question)
                .tools(tools)
                .call()
                .content();

        return new RunResult(answer, tools.capturedCalls());
    }

    public static final class RecordingTools {

        private final List<CapturedCall> calls =
                new CopyOnWriteArrayList<>();

        @Tool(
                name = "get_order_status",
                description = "Đọc trạng thái hiện tại của một đơn hàng đã có mã"
        )
        public String getOrderStatus(
                @ToolParam(description = "Mã đơn hàng từ yêu cầu người dùng")
                String orderId
        ) {
            calls.add(new CapturedCall(
                    "get_order_status", "orderId", orderId));
            return "Đơn " + orderId + ": đang xử lý (dữ liệu giả lập).";
        }

        @Tool(
                name = "search_internal_policy",
                description = "Tìm văn bản quy định trong kho tài liệu nội bộ"
        )
        public String searchInternalPolicy(
                @ToolParam(description = "Chủ đề hoặc câu hỏi cần tìm")
                String query
        ) {
            calls.add(new CapturedCall(
                    "search_internal_policy", "query", query));
            return "Kết quả chính sách giả lập cho: " + query;
        }

        public List<CapturedCall> capturedCalls() {
            return List.copyOf(calls);
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
var probe = new ToolSelectionProbe(chatClientBuilder);

var result = probe.run("Cho biết trạng thái hiện tại của đơn A123.");

System.out.println("Final answer: " + result.answer());
result.calls().forEach(System.out::println);
~~~

**chatClientBuilder** là builder do cấu hình ứng dụng cung cấp. Kết quả thực tế phụ thuộc model, prompt và những tool đã cấp; không được mặc định rằng model luôn chọn đúng.

Ưu điểm của cách ghi nhận này là bộ đánh giá có thể kiểm tra:

- Mô hình đã **thực thi tool nào**.
- Giá trị tham số phương thức Java nhận được.
- Số lần thực thi và thứ tự quan sát được của các lời gọi.
- Có xảy ra lần gọi thừa hay không.

Tuy nhiên, đây mới là **dữ liệu của tool đã đi vào phương thức Java**, không phải toàn bộ request thô mà model sinh ra:

1. Một request có JSON sai schema có thể bị chặn hoặc lỗi parse **trước khi** phương thức chạy; bộ ghi trong phương thức sẽ không thấy lỗi này.
2. Nếu công cụ bị chặn bởi bộ xác thực, bộ phê duyệt hoặc giới hạn thực thi, việc không thấy lời gọi không chứng minh model không từng đề nghị gọi tool.
3. Nếu ChatClient có **defaultTools**, chúng có thể được cung cấp cùng những tool truyền qua **.tools(...)**. Cần ghi nhận toàn bộ tool thực sự có mặt trong request.
4. Trên các phiên bản Spring AI khác nhau, cơ chế vòng lặp xử lý lời gọi có thể khác nhau; không nên suy đoán sự kiện thô chỉ từ kết quả trả lời cuối.

Để đánh giá đầy đủ cả **tham số mà model đề xuất** lẫn **tham số đã thực thi**, hãy ghi sự kiện ở vị trí điều phối hoặc lớp bọc **ToolCallback** và liên kết với trace ID, tool call ID, trạng thái kiểm tra và kết quả thực thi.

### Chấm một ca đơn giản

Với ca ORDER-01, quy tắc chấm có thể triển khai như sau:

~~~java
static boolean passesOrderCase(ToolSelectionProbe.RunResult result) {
    if (result.calls().size() != 1) {
        return false;
    }

    ToolSelectionProbe.CapturedCall call = result.calls().get(0);
    return "get_order_status".equals(call.toolName())
            && "orderId".equals(call.argumentName())
            && "A123".equals(call.argumentValue());
}
~~~

Hàm này chỉ là **oracle cho một ca có một tool và một đối số cố định**. Với ngày tháng, truy vấn tìm kiếm, nhiều tool hoặc ca nhiều bước, phải dùng bộ chấm phù hợp với từng trường và các quy tắc nghiệp vụ. Không áp dụng so sánh toàn bộ chuỗi cho mọi loại đối số.

## 8. Tổ chức bộ chấm nhiều tầng

Một kết quả đánh giá nên chứa từng phép kiểm tra, thay vì chỉ một trường **passed**:

~~~json
{
  "case_id": "ORDER-01",
  "expected_tool": "get_order_status",
  "observed_tool": "get_order_status",
  "selection_correct": true,
  "schema_valid": true,
  "arguments_grounded": false,
  "business_valid": false,
  "execution_succeeded": true,
  "answer_grounded": false,
  "details": {
    "expected_orderId": "A123",
    "observed_orderId": "A132",
    "error_type": "WRONG_ENTITY_ID"
  }
}
~~~

Trong ví dụ, framework đã thực thi thành công công cụ đúng tên nhưng dùng mã đơn sai; bộ chấm phải báo **lỗi đối số** và không xem toàn bộ ca là PASS.

### Chỉ số lựa chọn công cụ

Khi câu hỏi có một hoặc nhiều tool được chấp nhận:

**Tool selection accuracy** = số ca chọn công cụ thuộc tập đúng / số ca bắt buộc chọn công cụ.

Chỉ số này cần công bố quy ước rõ ràng: nếu mô hình gọi cả một tool đúng lẫn một tool sai trong cùng ca, có chấm sai toàn ca hay không? Với bài toán yêu cầu chọn **một tool duy nhất**, nên chấm sai nếu phát sinh lời gọi ngoài danh sách cho phép.

Với luồng nhiều bước, báo thêm:

- **Exact tool sequence accuracy:** tỷ lệ ca có đầy đủ chuỗi tool chính xác, kể cả thứ tự nếu thứ tự quan trọng.
- **Tool precision:** trong các tool đã gọi, tỷ lệ lời gọi phù hợp với các bước được phép.
- **Tool recall:** tỷ lệ bước bắt buộc đã được thực hiện; phải định nghĩa cách ghép lời gọi quan sát với bước kỳ vọng.
- **Unnecessary tool-call rate:** tỷ lệ gọi thêm không có nhu cầu nghiệp vụ.

Các chỉ số cho chuỗi không tương đương với accuracy lựa chọn một tool; phải đặt tên và mẫu số rõ ràng.

### Chỉ số đối số

**Schema validity rate** = số lời gọi có đối số đạt schema / số lời gọi được kiểm tra schema.

**Argument exact-match accuracy** = số lời gọi có toàn bộ đối số đúng theo oracle / số lời gọi cần chấm đối số.

**Field-level accuracy** = số trường đúng / tổng trường bắt buộc được chấm.

**Grounded argument rate** = tỷ lệ đối số quan trọng có nguồn dữ liệu hợp lệ và đúng ý người dùng.

**End-to-end tool call accuracy** = tỷ lệ ca chọn đúng tool **và** có mọi đối số/quyền bắt buộc đúng.

Với field-level accuracy, cần quy định trường tùy chọn được tính thế nào và có phạt đối số thừa không. Với tool có tham số quan trọng không đồng đều, báo thêm **tỷ lệ lỗi nghiêm trọng** theo nhóm như sai người nhận, sai số tiền, sai mã đơn, sai tenant.

### Ví dụ tính điểm

Giả sử có **20 ca**: 16 ca cần dùng tool và 4 ca đúng ra không cần gọi. Trong 16 ca cần tool:

- 12 ca chọn đúng tool.
- 2 ca gọi sai tool.
- 2 ca bỏ sót lời gọi.
- Trong 12 ca chọn đúng tool, 9 ca có toàn bộ đối số đúng.
- Bốn ca không cần tool đều không gọi.

Khi đó:

| Chỉ số | Phép tính | Kết quả |
| --- | --- | ---: |
| Tool selection accuracy trên ca cần gọi | 12 / 16 | **75%** |
| Argument accuracy khi đã chọn đúng tool | 9 / 12 | **75%** |
| Tỷ lệ ca cần gọi đạt cả tool và đối số | 9 / 16 | **56,25%** |
| Tỷ lệ không gọi đúng ở nhóm không cần gọi | 4 / 4 | **100%** |

Nếu chỉ nhìn “12 ca chọn đúng tool”, ta bỏ qua ba trường hợp gửi đối số sai. Nếu chỉ nhìn kết quả công cụ có trả dữ liệu, ta có thể bỏ sót cả lỗi sai mã đơn rất nghiêm trọng. **Tỷ lệ thành công kỹ thuật không thay thế được chất lượng nghiệp vụ.**

Mọi chỉ số phải kèm số lượng ca và tiêu chí chấm. Khi mẫu số bằng 0, đánh dấu **không xác định** thay vì mặc định 100%.

## 9. Đánh giá chuỗi công cụ và luồng RAG

Trong ứng dụng thực tế, mô hình có thể cần nhiều công cụ liên tiếp hoặc truy xuất nhiều lần.

### 9.1. Đánh giá chuỗi phụ thuộc

Ví dụ nhiệm vụ: “Kiểm tra đơn A123, nếu đủ điều kiện thì tạo yêu cầu hoàn tiền 150.000 VND sau khi tôi xác nhận”.

Luồng mong đợi có thể là:

1. **get_order_status(orderId=A123)** để biết trạng thái và thông tin liên quan.
2. Kiểm tra quy tắc hoàn tiền từ dữ liệu nghiệp vụ hoặc **search_internal_policy** nếu chính sách chưa có và truy xuất là bắt buộc.
3. Hỏi hoặc kiểm tra xác nhận hiện tại của người dùng theo chính sách ứng dụng.
4. Chỉ khi đủ quyền/điều kiện, gọi **create_refund_request** với **orderId=A123, amount=150000, currency=VND** và thông tin bổ sung cần thiết.

Các lỗi phải bắt riêng:

- Lựa chọn sai tool ở bước đầu.
- Dùng dữ liệu chưa xác minh để bỏ qua kiểm tra điều kiện.
- Đổi mã đơn hoặc số tiền giữa các bước.
- Thực thi bước ghi dữ liệu trước bước xác nhận.
- Gọi yêu cầu hoàn tiền hai lần gây tác động trùng lặp.

Với chuỗi có các nhánh hợp lệ, đừng ép khớp cứng một thứ tự duy nhất. Có thể mô hình hóa bằng **đồ thị điều kiện**: bước hoàn tiền bắt buộc sau xác nhận, còn bước đọc chính sách có thể được bỏ qua nếu chính sách đã nằm trong ngữ cảnh đáng tin.

### 9.2. Đánh giá truy vấn công cụ RAG

Nếu mô hình có tool **search_internal_policy(query, effectiveDate)**, tính đúng của **query** không phải vấn đề “câu chữ giống gold hay không”. Cần đánh giá:

- Có giữ đủ **thực thể, chủ đề, phạm vi và thời gian** người dùng yêu cầu?
- Có đưa bộ lọc nhầm làm bỏ mất tài liệu liên quan?
- Có tự thêm điều kiện không có trong câu hỏi không?
- Có chọn đúng kho dữ liệu được phép truy xuất không?
- Tập tài liệu trả về có **relevance**, đúng phiên bản và hỗ trợ câu trả lời không?

Ví dụ người dùng hỏi “Chính sách nghỉ phép áp dụng từ tháng 7/2026 cho nhân viên toàn thời gian”. Query chỉ còn “nghỉ phép” có thể quá rộng; query thêm “nhân viên bán thời gian” có thể sai đối tượng. Ta cần đánh giá riêng **query fidelity**, **retrieval relevance** và **fact checking/grounding** của câu trả lời sau truy xuất.

Đối với RAG pipeline truy xuất tự động trước khi gọi mô hình, bộ đánh giá phải xác định **ai tạo query và ai chọn nguồn**. Nếu query do mã ứng dụng tạo, lỗi đó thuộc pipeline, không nên mặc định là lỗi chọn tool của mô hình.

## 10. Traces và metrics để tìm nguyên nhân

Spring AI hỗ trợ quan sát qua hệ sinh thái **Micrometer Observation**, metrics và distributed tracing. Tùy phiên bản, các quan sát cho ChatClient, ChatModel và tool calling có thể mang tên như **spring.ai.chat.client** và **spring.ai.tool**. Những thuộc tính quan sát cụ thể có thể thay đổi theo phiên bản và cấu hình; cần kiểm tra trên hệ thống đang sử dụng.

Một bản ghi chuẩn hóa dành cho **bộ đánh giá của dự án** có thể như sau:

~~~json
{
  "case_id": "ORDER-01",
  "run_id": "prompt-v4-model-b",
  "trace_id": "example-trace-id",
  "step_index": 1,
  "available_tools": ["get_order_status", "search_internal_policy"],
  "expected_tool": "get_order_status",
  "requested_tool": "get_order_status",
  "executed_tool": "get_order_status",
  "schema_valid": true,
  "argument_grounding_valid": false,
  "validation_error": "WRONG_ENTITY_ID",
  "execution_status": "SUCCESS",
  "duration_ms": 94,
  "token_usage": {"input": 420, "output": 66},
  "estimated_cost_usd": null
}
~~~

Đây là schema tự thiết kế, không phải một JSON do Spring AI tự động xuất ra nguyên dạng. Đối với dữ liệu có thể nhận diện khách hàng, nên lưu **mã ca, mã lỗi, kết quả kiểm tra hoặc giá trị băm có kiểm soát** thay cho nguyên văn ID, token hay nội dung nhạy cảm.

| Quan sát | Dùng để trả lời câu hỏi |
| --- | --- |
| Danh sách tool được cấp | Model thực sự có cơ hội chọn công cụ đúng không? |
| Tool model đề nghị và tham số thô | Model đã chọn gì trước khi framework xử lý? |
| Kết quả kiểm tra schema/quyền | Tool bị chặn do cấu trúc, thiếu quyền hay lỗi nghiệp vụ? |
| Tool đã thực thi và số lần gọi | Có gọi sai, lặp thừa, hoặc bỏ bước không? |
| Kết quả tool và mã lỗi | Công cụ thất bại do backend hay trả dữ liệu không hợp lệ? |
| Thời gian tool/model; p50, p95 | Tool sai hoặc query quá rộng làm chậm đường đi nào? |
| Token và chi phí ước tính | Thêm lần gọi, retry hoặc catalog quá lớn tốn bao nhiêu? |
| Phiên bản prompt/model/tool/schema/pipeline | Suy giảm bắt đầu sau thay đổi nào? |

**Không tìm thấy span tool không đồng nghĩa model không yêu cầu gọi tool.** Sự kiện có thể bị chặn trước execution, không được instrumentation bao phủ, hoặc bị mất do cấu hình thu thập. Khi thiếu bằng chứng, nên phân loại **UNOBSERVABLE** và không chấm như một ca lựa chọn sai đã được xác nhận.

Spring AI có cấu hình cho phép xuất nội dung đối số và kết quả tool vào observability, nhưng loại dữ liệu này thường bị tắt mặc định vì nguy cơ chứa thông tin riêng tư. Trong hệ thống thực, ưu tiên chấm ngay tại ranh giới ứng dụng rồi chỉ phát ra **kết quả kiểm tra đã giảm nhạy cảm**.

### Quan sát chi phí và độ trễ

Một lựa chọn công cụ sai có thể gây tốn kém theo nhiều cách:

- Gọi nhầm dịch vụ chậm hoặc có phí cao.
- Truy vấn RAG quá rộng, kéo về nhiều tài liệu và tăng token đầu vào.
- Gọi đi gọi lại do lỗi tham số hoặc không nhận diện được dữ liệu đã có.
- Tạo thêm lượt model sau khi kết quả tool không đáp ứng yêu cầu.

Theo dõi **số tool call trên mỗi yêu cầu, p50/p95 thời gian, token, chi phí mô hình và phí dịch vụ ngoài**. Nếu thiếu usage hoặc bảng giá, giữ giá trị chi phí là chưa biết thay vì mặc định bằng 0.

## 11. Phân loại lỗi và cách khắc phục

| Mã lỗi | Dấu hiệu | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- | --- |
| WRONG_TOOL | Chọn công cụ khác chức năng | Tên/mô tả mơ hồ, catalog quá nhiều tool tương tự | Rõ ràng hóa phạm vi, loại tool thừa, thêm ca đối chứng |
| TOOL_NOT_AVAILABLE | Mô hình đề nghị tool không được cấp | Sai cấu hình request, tên tool cũ, lệch version | Kiểm tra catalog thực cấp và schema |
| INVALID_SCHEMA | Thiếu field, sai kiểu, JSON lỗi | @ToolParam hoặc JSON Schema chưa rõ | Cải thiện schema, validate trước execution |
| WRONG_ENTITY_ID | Truyền nhầm mã đơn/khách hàng | Mất thực thể trong prompt dài, dùng dữ liệu từ lượt khác | Ghép giá trị với nguồn, kiểm tra tính nhất quán |
| WRONG_UNIT_OR_DATE | Sai khối lượng, múi giờ, tiền tệ | Thiếu chuẩn đầu vào, tự suy ngày tham chiếu | Chuẩn hóa đơn vị, ngày/múi giờ, tiền tệ |
| UNGROUNDED_ARGUMENT | Tự tạo giá trị không có căn cứ | Trường bắt buộc nhưng thiếu dữ liệu | Yêu cầu bổ sung; không ép model đoán |
| UNAUTHORIZED_ARGUMENT | Giá trị thuộc người dùng/tenant khác | Tin vào dữ liệu do model tự sinh | Cấp scope từ backend, kiểm quyền khi thực thi |
| ORDERING_ERROR | Chạy bước sau trước bước bắt buộc | Điều phối chuỗi công cụ chưa có ràng buộc | Kiểm tra tiền điều kiện và thứ tự |
| DUPLICATE_SIDE_EFFECT | Tạo hai thao tác ghi giống nhau | Retry, lỗi trạng thái, thiếu idempotency | Giới hạn retry, khóa chống trùng, kiểm tra log |
| UNGROUNDED_ANSWER | Tool đúng và args đúng nhưng trả lời sai | Mô hình đọc hoặc tổng hợp kết quả sai | Chấm grounding/fact checking ở tầng trả lời |

**Chỉ thay prompt khi dấu vết cho thấy lỗi ở quyết định của mô hình.** Nếu model gọi đúng nhưng backend nhận sai do mapping serializer, lỗi nằm tại lớp chuyển đổi/điều phối. Nếu query đúng nhưng hệ thống truy xuất tài liệu lạc hậu, hãy sửa nguồn và pipeline.

### Trường hợp có nhiều công cụ gần giống nhau

Giả sử có **search_customer**, **get_customer_profile**, **list_customer_orders**. Nếu mô tả không phân biệt rõ, mô hình có thể chọn sai dù câu hỏi đơn giản. Một biện pháp hữu ích là thiết kế mô tả theo **đầu vào, đầu ra và trường hợp sử dụng**, tạo ca thử có cùng câu chữ nhưng mục tiêu khác nhau, sau đó đo ma trận nhầm lẫn giữa tên công cụ.

Nếu ứng dụng có hàng trăm công cụ, có thể xem xét chiến lược khám phá hoặc lọc công cụ theo nhu cầu, nhưng vẫn phải chấm cả lỗi **không hiển thị đúng công cụ cho model** ở lớp chọn tool của hệ thống.

## 12. Thiết kế thử nghiệm so sánh các phiên bản

Để đánh giá một thay đổi về prompt, model hoặc tool schema:

1. **Cố định bộ ca, quyền, ngày tham chiếu, snapshot dữ liệu và công cụ giả lập.** Khác biệt môi trường sẽ làm sai kết luận.
2. **Ghi phiên bản** model, prompt, catalog, schema, resolver, pipeline RAG và bộ chấm.
3. **Chạy nhiều lần nếu mô hình không hoàn toàn xác định.** Tính tỷ lệ PASS và độ biến động theo ca.
4. **Báo các chỉ số nhiều tầng:** selection accuracy, schema validity, grounded arguments, lỗi quyền, chuỗi tool đúng, độ trễ và chi phí.
5. **Xem các ca đổi trạng thái** từ PASS sang FAIL và ngược lại; ưu tiên lỗi nặng như sai đối tượng hoặc gọi thao tác ghi chưa phép.
6. **Kiểm tra traces** để giải thích thay đổi, sau đó mới quyết định giữ hoặc hoàn tác phiên bản.

Ví dụ bảng so sánh giả định:

| Chỉ số trên cùng tập ca | Prompt A | Prompt B |
| --- | ---: | ---: |
| Chọn đúng tool | 84% | 92% |
| Toàn bộ đối số đúng khi chọn đúng tool | 90% | 86% |
| Lỗi mã đơn | 1 | 4 |
| Lời gọi trung bình trên yêu cầu | 1,2 | 1,5 |
| p95 thời gian xử lý | 2,1 giây | 3,0 giây |

Mặc dù B chọn đúng tool nhiều hơn, lỗi mã đơn lại tăng và việc gọi công cụ tốn thời gian hơn. Không thể kết luận B tốt hơn chỉ dựa vào chỉ số selection accuracy. Cần xem lỗi mã đơn thuộc ca nào, có quyền ảnh hưởng dữ liệu thật không, và ngưỡng chấp nhận của sản phẩm là gì.

### Đánh giá tự động và đánh giá bằng người

Không phải mọi đối số đều dễ kiểm tra bằng code:

- **Code kiểm tra xác định:** ID, enum, ngày/giờ, số tiền, quyền, dữ liệu có sẵn, thứ tự và số lần gọi.
- **Đánh giá ngữ nghĩa:** query tìm kiếm có giữ đúng ý, có đủ bộ lọc, có bỏ sót đối tượng không.
- **Chuyên gia nghiệp vụ:** điều kiện hoàn tiền, logic phê duyệt, các trường hợp có nhiều cách giải quyết hợp lệ.

Nếu dùng một LLM làm evaluator cho đối số ngữ nghĩa, cần cung cấp rubric rõ, chuẩn hóa đầu ra, thử với các ca đã được người đánh giá gán nhãn và kiểm tra khả năng thiên lệch. Không để mô hình chấm tự ý thay đổi nhãn chuẩn hoặc xác nhận quyền.

## 13. Bài thực hành

**Bối cảnh:** một trợ lý hỗ trợ đơn hàng có ba tool: **get_order_status**, **search_internal_policy** và **estimate_shipping_fee**.

**Yêu cầu thực hiện:**

1. Tạo tối thiểu 12 ca, gồm ba ca đúng tool với đúng đối số, ba ca dễ nhầm tool, ba ca đối số sai kiểu/sai miền và ba ca phụ thuộc dữ liệu hoặc quyền.
2. Dùng **ToolSelectionProbe** làm bộ ghi nhận. Mở rộng công cụ giả lập vận chuyển để nhận **destinationProvince** và **weightKg**.
3. Tạo bộ chấm hai lớp: **selection_correct** và **arguments_correct**. Riêng khối lượng, kiểm tra số dương và giữ đúng đơn vị kg.
4. Chạy cùng tập ca với hai cách mô tả công cụ khác nhau; ghi số lần gọi, lỗi và kết quả.
5. Tạo báo cáo theo từng nhóm lỗi, có tỷ lệ chọn tool đúng, tỷ lệ đối số đúng, số lần gọi trung bình và p95.
6. Chọn một ca sai mã đơn và một ca sai query RAG, giải thích bằng traces liệu lỗi phát sinh ở model, mapping, bộ kiểm tra hay hệ thống truy xuất.

**Câu hỏi thảo luận:** Nếu một mô hình chọn đúng tool trong 95% ca nhưng có tỷ lệ 2% truyền nhầm mã khách hàng, sản phẩm có nên phát hành phiên bản đó không? Trả lời dựa trên rủi ro cụ thể, quyền truy cập, chặn lỗi tại backend và tác động đối với người dùng, thay vì chỉ nêu một ngưỡng accuracy tổng quát.

## 14. Tóm lược

- **Chọn đúng công cụ** và **truyền đúng đối số** là hai yêu cầu độc lập. Một lời gọi đúng tên vẫn có thể tạo kết quả sai hoặc gây tác động ngoài ý muốn.
- **Schema validity là điều kiện cần, chưa đủ.** Đối số còn phải đúng thực thể, đúng đơn vị, có nguồn gốc và tuân thủ nghiệp vụ, quyền, xác nhận.
- **Gold label phải chứa ngữ cảnh:** tool thực sự được cấp, dữ liệu có sẵn, quyền, thời gian và các cách xử lý hợp lệ.
- **Chấm theo từng tầng:** selection, schema, ngữ nghĩa, grounding, quyền, chuỗi thực thi và chất lượng câu trả lời sau tool.
- **Quan sát toàn bộ đường đi:** từ request của model, kiểm tra/dispatch cho tới tool execution, kết quả và câu trả lời; dùng traces cùng metrics để tìm nguyên nhân suy giảm qua các phiên bản.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): khai báo công cụ, mô tả tham số, truyền tool cho ChatClient, cơ chế thực thi.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): dữ liệu quan sát cho ChatClient, ChatModel, tool calling và lưu ý với nội dung nhạy cảm.

Khi triển khai trên một phiên bản Spring AI cụ thể, hãy kiểm tra lại tên API, kiểu dữ liệu và các thuộc tính quan sát của phiên bản đó trước khi đưa ví dụ vào mã sản phẩm.
