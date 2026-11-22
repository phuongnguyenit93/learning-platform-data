# Lộ trình chuyển đổi

Trong quá trình phát triển một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), nhu cầu sử dụng và nhóm người dùng có thể thay đổi. Một DSL ban đầu chỉ dành cho lập trình viên có thể cần được cung cấp cho chuyên viên nghiệp vụ, người vận hành hoặc hệ thống bên ngoài. Ngược lại, một DSL bên ngoài được thiết kế để người dùng cấu hình độc lập có thể trở nên quá phức tạp, khiến nhóm phát triển muốn chuyển một phần cách mô tả về API hoặc DSL nội bộ trong ngôn ngữ lập trình chủ.

Vì vậy, lựa chọn giữa **DSL nội bộ (internal DSL)** và **DSL bên ngoài (external DSL)** không nhất thiết là quyết định cố định trong suốt vòng đời sản phẩm. Có thể chuyển đổi dần khi yêu cầu thay đổi. Lộ trình tốt cần bảo toàn ý nghĩa nghiệp vụ, kiểm soát rủi ro, hỗ trợ người dùng trong giai đoạn chuyển tiếp và có tiêu chí rõ ràng để kết thúc việc chuyển đổi.

Bài học này trình bày cách lập kế hoạch chuyển đổi giữa hai hình thức DSL, đặc biệt là quá trình phát triển từ DSL nội bộ sang DSL bên ngoài, đồng thời xem xét chiều ngược lại và mô hình kết hợp.

## 1. Nhắc lại điểm khác nhau giữa DSL nội bộ và DSL bên ngoài

DSL nội bộ được xây dựng bằng cú pháp và khả năng của một ngôn ngữ lập trình chủ. Người dùng viết mô tả miền như một phần của mã nguồn bằng ngôn ngữ đó. DSL bên ngoài có cú pháp riêng, thường được phân tích bởi parser và chuyển thành cấu trúc trung gian để thực thi.

Ví dụ, một DSL nội bộ viết bằng Kotlin có thể khai báo quy trình xử lý đơn hàng:

~~~kotlin
workflow("processOrder") {
    step("validate") {
        action = "validateOrder"
    }
    step("reserveStock") {
        action = "reserveInventory"
    }
    step("chargePayment") {
        action = "chargePayment"
    }
}
~~~

Một DSL bên ngoài có thể biểu diễn cùng ý định bằng YAML:

~~~yaml
workflow: processOrder
steps:
  - id: validate
    action: validateOrder
  - id: reserveStock
    action: reserveInventory
  - id: chargePayment
    action: chargePayment
~~~

Hai ví dụ mô tả cùng một quy trình ở mức khái niệm. Cú pháp và cách xử lý khác nhau:

| Khía cạnh | DSL nội bộ | DSL bên ngoài |
| --- | --- | --- |
| Cú pháp | Dựa trên ngôn ngữ chủ, ví dụ Kotlin hoặc Groovy | Có cú pháp riêng, ví dụ YAML, JSON hoặc ngữ pháp tự định nghĩa |
| Phân tích | Thường do compiler hoặc runtime của ngôn ngữ chủ đảm nhiệm | Cần parser, bộ kiểm tra và mô hình cú pháp |
| Công cụ | Có thể tận dụng IDE, kiểu dữ liệu, refactoring và debugger của ngôn ngữ chủ | Cần xây dựng hoặc tích hợp editor, validator, formatter và thông báo lỗi phù hợp |
| Người dùng phù hợp | Thường là lập trình viên quen ngôn ngữ chủ | Có thể phục vụ người dùng không viết mã bằng ngôn ngữ chủ |
| Tích hợp mã | Gọi hàm, thư viện và kiểu dữ liệu trực tiếp | Thường tích hợp qua API, plugin hoặc bộ thực thi |
| Phân phối cấu hình | Có thể gắn với mã và chu kỳ build | Có thể lưu, trao đổi và chỉnh sửa như tài liệu độc lập |
| Kiểm soát ngữ nghĩa | Dựa nhiều vào cấu trúc và quy tắc của ngôn ngữ chủ | Có thể kiểm soát riêng cú pháp, kiểu và ngữ nghĩa của DSL |

Không có hình thức nào luôn tốt hơn. Chuyển đổi chỉ hợp lý khi lợi ích đối với người dùng, quy trình hoặc kiến trúc lớn hơn chi phí xây dựng và duy trì hình thức mới.

## 2. Khi nào cần chuyển đổi?

Một DSL nội bộ thường phù hợp ở giai đoạn đầu vì nhóm có thể tận dụng ngôn ngữ chủ, thư viện và công cụ sẵn có. Khi phạm vi sử dụng mở rộng, một số dấu hiệu cho thấy cần xem xét DSL bên ngoài.

### 2.1. Dấu hiệu nên chuyển từ nội bộ sang bên ngoài

- Người dùng cần viết cấu hình nhưng không biết hoặc không được phép sử dụng ngôn ngữ lập trình chủ.
- Cấu hình cần được tạo, chỉnh sửa hoặc kiểm tra bởi một hệ thống khác.
- Muốn tách dữ liệu cấu hình khỏi mã nguồn và chu kỳ biên dịch.
- Cần lưu trữ, trao đổi, ký duyệt hoặc quản lý phiên bản cấu hình độc lập.
- Cần giới hạn khả năng thực thi để người dùng chỉ khai báo những thao tác được phép.
- Cú pháp nội bộ phụ thuộc quá nhiều vào chi tiết của ngôn ngữ chủ, gây khó khăn khi nâng cấp hoặc hỗ trợ nhiều ngôn ngữ.

Ví dụ, nhóm phát triển ban đầu viết quy trình triển khai bằng Kotlin DSL. Sau đó, bộ phận vận hành cần thay đổi tham số triển khai mà không sửa mã ứng dụng hoặc chạy quy trình biên dịch. Một tệp cấu hình bên ngoài có thể phù hợp hơn.

### 2.2. Dấu hiệu nên chuyển từ bên ngoài sang nội bộ

Chiều chuyển đổi ngược cũng có thể xảy ra:

- DSL bên ngoài chỉ được dùng bởi một nhóm lập trình viên nhỏ và mọi cấu hình đều cần thay đổi mã.
- Cú pháp riêng, parser và công cụ hỗ trợ tạo ra chi phí bảo trì lớn.
- Người dùng cần khả năng biểu đạt phong phú của ngôn ngữ chủ, chẳng hạn kiểu dữ liệu, hàm và thư viện.
- DSL bên ngoài có quá nhiều cơ chế mở rộng khiến ngữ nghĩa khó hiểu.
- Nhu cầu trao đổi cấu hình độc lập không còn quan trọng bằng khả năng tích hợp và refactoring trong mã.

Ví dụ, một DSL truy vấn bên ngoài ban đầu được thiết kế cho nhiều nhóm nghiệp vụ, nhưng thực tế chỉ còn được sử dụng trong mã backend bởi các lập trình viên. Nhóm có thể cân nhắc chuyển sang API có kiểu dữ liệu hoặc DSL nội bộ trong Kotlin.

### 2.3. Không chuyển đổi chỉ vì cú pháp khác lạ

Một cú pháp YAML hoặc JSON không tự làm cho ngôn ngữ trở nên dễ dùng với nghiệp vụ. Người dùng vẫn cần hiểu khái niệm, thuộc tính, quy tắc và lỗi. Tương tự, DSL nội bộ không nhất thiết khó tiếp cận nếu ngôn ngữ chủ cung cấp cú pháp biểu đạt tốt và người dùng đã quen thuộc.

Trước khi chuyển đổi, hãy xác định vấn đề thực tế: nhóm người dùng nào đang gặp khó khăn, công việc nào bị cản trở và hình thức mới giải quyết vấn đề đó bằng cách nào.

## 3. Nguyên tắc quan trọng: tách ngữ nghĩa khỏi cú pháp

Lộ trình chuyển đổi dễ kiểm soát hơn khi ý nghĩa của DSL không bị gắn chặt vào một hình thức cú pháp.

Giả sử DSL mô tả quy trình:

1. Kiểm tra đơn hàng.
2. Giữ hàng trong kho.
3. Thu tiền.
4. Gửi thông báo.

Ý nghĩa nghiệp vụ của quy trình là phần cốt lõi. Kotlin DSL, YAML hay một ngôn ngữ văn bản tự định nghĩa chỉ là các cách khác nhau để biểu đạt ý nghĩa đó.

Có thể tổ chức kiến trúc theo luồng:

~~~text
DSL nội bộ ---------+
                    |
                    v
              Mô hình trung gian
                    |
                    v
              Kiểm tra ngữ nghĩa
                    |
                    v
               Bộ thực thi
                    ^
                    |
DSL bên ngoài -> Parser
~~~

Mô hình trung gian (intermediate representation — IR) lưu cấu trúc có ý nghĩa mà bộ thực thi hiểu được. Ví dụ, IR có thể là danh sách bước, mỗi bước gồm mã định danh, hành động, tham số và phụ thuộc.

Khi cả DSL nội bộ và bên ngoài đều chuyển về cùng IR, nhóm có thể thay đổi cú pháp mà không phải viết lại toàn bộ logic thực thi. Đây là nền tảng hữu ích cho chuyển đổi từng phần và chạy song song hai hình thức.

### 3.1. Xây dựng mô hình miền ổn định

Trước khi thiết kế cú pháp mới, hãy xác định:

- Các khái niệm miền và thuộc tính.
- Các loại câu lệnh hoặc thao tác được phép.
- Quan hệ và ràng buộc giữa các khái niệm.
- Kiểu dữ liệu, giá trị mặc định và quy tắc chuyển đổi.
- Thứ tự thực thi, điều kiện, vòng lặp và tác động phụ.
- Quy tắc xử lý lỗi và giới hạn quyền thực thi.

Ví dụ, một bước quy trình có thể được biểu diễn bằng kiểu dữ liệu độc lập với cú pháp:

~~~kotlin
data class WorkflowStep(
    val id: String,
    val action: String,
    val parameters: Map<String, String> = emptyMap(),
    val dependsOn: List<String> = emptyList()
)

data class WorkflowDefinition(
    val name: String,
    val steps: List<WorkflowStep>
)
~~~

Đây là mô hình minh họa đơn giản. Trong hệ thống thực tế, cần dùng kiểu tham số phù hợp với miền thay vì xem mọi giá trị là chuỗi, đồng thời xác định cách biểu diễn điều kiện, tham chiếu và kiểu lỗi.

### 3.2. Định nghĩa ngữ nghĩa một lần

Cần xác định rõ cùng một mô tả sẽ có hành vi như thế nào dù được viết bằng cú pháp khác nhau.

Ví dụ, nếu một bước phụ thuộc vào bước khác, phải quy định:

- Bước phụ thuộc chỉ được chạy sau khi bước trước thành công hay có thể chạy sau khi bước trước hoàn tất với trạng thái bất kỳ?
- Điều gì xảy ra khi một bước thất bại?
- Có cho phép nhiều bước cùng phụ thuộc một bước không?
- Vòng phụ thuộc có hợp lệ không?
- Có bước nào được chạy song song không?

Nếu DSL nội bộ và DSL bên ngoài diễn giải các câu lệnh khác nhau, người dùng sẽ nhận kết quả không nhất quán. Vì vậy, parser và builder nên tạo cùng một mô hình ngữ nghĩa và sử dụng chung bộ kiểm tra, bộ lập kế hoạch và bộ thực thi.

## 4. Lộ trình chuyển từ DSL nội bộ sang DSL bên ngoài

Có thể chia quá trình thành các giai đoạn nhỏ. Không cần chuyển toàn bộ cấu hình trong một lần; hãy bắt đầu với phần có nhu cầu rõ ràng và rủi ro thấp.

### Giai đoạn 1: Khảo sát DSL nội bộ hiện tại

Thu thập các cách sử dụng DSL hiện có và phân loại:

- Cú pháp nào được sử dụng thường xuyên?
- Những tính năng nào là công khai và được người dùng phụ thuộc?
- Phần nào chỉ là tiện ích nội bộ?
- Có đoạn mã nào thực thi trực tiếp logic tùy ý?
- Những cấu hình nào cần được chỉnh sửa bởi người không viết mã?
- Có những biến thể hoặc hành vi phụ thuộc môi trường nào?

Không nên chỉ đọc định nghĩa builder hoặc API. Cần xem các ví dụ sử dụng thực tế, cấu hình đang chạy và các kiểm thử liên quan. Những trường hợp cũ có thể chứa ngữ nghĩa mà tài liệu chưa ghi lại.

Kết quả của giai đoạn này là danh mục tính năng và tập tình huống đại diện, kèm mức độ quan trọng và mức độ phức tạp.

### Giai đoạn 2: Xác định phạm vi DSL bên ngoài

Chọn những khả năng thực sự cần thiết cho nhóm người dùng mới. Ví dụ, nếu người vận hành chỉ cần chọn hành động, tham số và phụ thuộc, DSL bên ngoài không cần cho phép họ viết mã tùy ý.

Cần quyết định:

- Dùng định dạng có cấu trúc như YAML/JSON hay thiết kế ngữ pháp riêng.
- Cấu hình có cần biểu thức, biến, hàm hoặc điều kiện không.
- Cách tham chiếu tài nguyên và bí mật.
- Quy tắc đặt tên và phạm vi.
- Phiên bản của định dạng.
- Cách báo lỗi và chỉ ra vị trí lỗi.

Định dạng có cấu trúc thường là lựa chọn hợp lý cho cấu hình đơn giản. Ngữ pháp riêng có thể phù hợp khi cần cú pháp giàu biểu đạt, nhưng kéo theo chi phí xây dựng parser, tài liệu và công cụ biên tập.

### Giai đoạn 3: Thiết kế parser và mô hình trung gian

Parser chuyển văn bản bên ngoài thành cấu trúc dữ liệu. Sau đó, bộ kiểm tra ngữ nghĩa xác minh cấu trúc đó có hợp lệ trong miền hay không.

Luồng xử lý điển hình:

~~~text
Tệp DSL
   |
   v
Đọc và phân tích cú pháp
   |
   v
Cây cú pháp / cấu trúc dữ liệu
   |
   v
Kiểm tra kiểu và ngữ nghĩa
   |
   v
Mô hình trung gian (IR)
   |
   v
Lập kế hoạch và thực thi
~~~

Không nên để parser gọi trực tiếp các dịch vụ nghiệp vụ hoặc tạo tác động phụ khi đang đọc tệp. Parser nên tập trung vào việc chuyển văn bản thành cấu trúc; kiểm tra và thực thi được tổ chức ở các lớp riêng.

Với DSL YAML, có thể dùng thư viện YAML để đọc thành cấu trúc dữ liệu rồi ánh xạ sang các kiểu miền. Dù thư viện đã kiểm tra cú pháp YAML, ứng dụng vẫn phải kiểm tra trường bắt buộc, kiểu, giá trị cho phép, tham chiếu và ràng buộc nghiệp vụ.

### Giai đoạn 4: Tạo bộ chuyển đổi từ DSL nội bộ sang IR

Nếu DSL nội bộ hiện tại được xây dựng bằng builder, hãy bổ sung cơ chế chuyển kết quả builder thành cùng IR.

Ví dụ:

~~~kotlin
fun buildWorkflow(): WorkflowDefinition =
    WorkflowDefinition(
        name = "processOrder",
        steps = listOf(
            WorkflowStep(
                id = "validate",
                action = "validateOrder"
            ),
            WorkflowStep(
                id = "reserveStock",
                action = "reserveInventory",
                dependsOn = listOf("validate")
            )
        )
    )
~~~

Bộ chuyển đổi này giúp giữ lại hành vi hiện có và cung cấp dữ liệu chuẩn để so sánh với kết quả parser bên ngoài.

Nếu DSL nội bộ hiện tại gọi trực tiếp các API và tạo tác động phụ trong block cấu hình, cần tách phần mô tả khỏi phần thực thi trước. Đây có thể là phần việc lớn nhất của quá trình chuyển đổi.

### Giai đoạn 5: Chạy song song và so sánh

Trong giai đoạn thử nghiệm, một số quy trình có thể được mô tả bằng cả hai hình thức:

- Cấu hình nội bộ tạo ra IR thứ nhất.
- Tệp bên ngoài tạo ra IR thứ hai.
- Hệ thống so sánh các trường có ý nghĩa và hành vi dự kiến.
- Bộ kiểm thử xác minh hai mô tả tương đương trong các trường hợp được hỗ trợ.

Ví dụ, hai IR có thể được chuẩn hóa về thứ tự bước, giá trị mặc định và cách biểu diễn tham số trước khi so sánh. Không nên so sánh văn bản thô vì cú pháp và thứ tự trường có thể khác nhau trong khi ý nghĩa giống nhau.

Ở môi trường sản xuất, không nên thực thi hai bản mô tả chỉ để so sánh nếu chúng tạo tác động phụ như thu tiền, gửi thông báo hoặc cập nhật dữ liệu. Có thể so sánh ở chế độ kiểm tra (dry run), dùng dữ liệu thử nghiệm hoặc chỉ đối chiếu kế hoạch đã tạo.

### Giai đoạn 6: Chuyển dần người dùng và cấu hình

Bắt đầu với một nhóm người dùng, một loại quy trình hoặc một môi trường thử nghiệm. Cung cấp:

- Tài liệu chuyển đổi cú pháp.
- Ví dụ tương đương trước và sau.
- Validator chạy trước khi áp dụng cấu hình.
- Thông báo lỗi dễ hiểu.
- Hướng dẫn khôi phục về hình thức cũ trong thời gian chuyển tiếp.
- Kênh ghi nhận những trường hợp DSL mới chưa biểu đạt được.

Sau khi có dữ liệu sử dụng và xác nhận hành vi, mở rộng sang các nhóm hoặc cấu hình tiếp theo.

### Giai đoạn 7: Ngừng DSL cũ theo kế hoạch

Chỉ ngừng DSL nội bộ cũ khi các trường hợp sử dụng cần thiết đã được chuyển đổi, người dùng đã chuyển sang hình thức mới và không còn phụ thuộc quan trọng.

Quá trình ngừng sử dụng cần có:

- Thông báo phiên bản hoặc mốc ngừng hỗ trợ.
- Thời hạn chuyển đổi đủ rõ.
- Cảnh báo khi phát hiện cấu hình cũ.
- Tài liệu thay thế và công cụ hỗ trợ di trú nếu cần.
- Kế hoạch loại bỏ mã chuyển tiếp sau khi không còn người dùng.

Không nên xóa builder cũ ngay khi parser mới vừa hoạt động. Cần có bằng chứng rằng các trường hợp quan trọng đã được chuyển đổi và có thể khôi phục khi phát hiện vấn đề.

## 5. Ví dụ chuyển đổi một quy trình cụ thể

Giả sử DSL nội bộ ban đầu được viết bằng Kotlin:

~~~kotlin
workflow("approveRefund") {
    step("loadOrder") {
        action = "loadOrder"
    }

    step("checkPolicy") {
        action = "checkRefundPolicy"
        dependsOn("loadOrder")
    }

    step("issueRefund") {
        action = "issueRefund"
        dependsOn("checkPolicy")
        parameter("currency", "VND")
    }
}
~~~

Nhóm muốn cho phép nhân viên vận hành khai báo quy trình bằng tệp YAML. Cấu hình bên ngoài có thể như sau:

~~~yaml
version: 1
workflow: approveRefund
steps:
  - id: loadOrder
    action: loadOrder

  - id: checkPolicy
    action: checkRefundPolicy
    dependsOn:
      - loadOrder

  - id: issueRefund
    action: issueRefund
    dependsOn:
      - checkPolicy
    parameters:
      currency: VND
~~~

Cả hai biểu diễn cần được chuyển thành cùng một mô hình:

~~~text
WorkflowDefinition
  name: approveRefund
  steps:
    - id: loadOrder
      action: loadOrder
      dependsOn: []
    - id: checkPolicy
      action: checkRefundPolicy
      dependsOn: [loadOrder]
    - id: issueRefund
      action: issueRefund
      dependsOn: [checkPolicy]
      parameters:
        currency: VND
~~~

Bộ kiểm tra ngữ nghĩa cần xác minh:

- Tên quy trình không rỗng và hợp lệ.
- Mỗi mã bước là duy nhất.
- Mỗi action nằm trong danh sách hành động được phép.
- Tham chiếu trong dependsOn trỏ đến bước tồn tại.
- Đồ thị phụ thuộc không có chu trình nếu mô hình không cho phép chu trình.
- Tham số currency có kiểu và giá trị hợp lệ.
- Người dùng hiện tại được phép yêu cầu hành động hoàn tiền.

Sau kiểm tra, bộ thực thi xử lý IR theo cùng quy tắc bất kể nguồn đầu vào là Kotlin builder hay YAML. Như vậy, nhóm thay đổi cách người dùng viết mô tả mà không phải tạo hai hệ thống thực thi khác nhau.

## 6. Chuyển đổi từ DSL bên ngoài sang DSL nội bộ

Chuyển đổi ngược thường phù hợp khi DSL bên ngoài không còn phục vụ đúng nhóm người dùng hoặc khi việc tích hợp sâu với mã nguồn trở nên quan trọng hơn.

Lộ trình có thể gồm:

1. Thu thập các tệp cấu hình và xác định phần cú pháp thực sự được sử dụng.
2. Xác định cấu trúc IR hoặc mô hình miền tương ứng.
3. Tạo builder hoặc API có kiểu dữ liệu trong ngôn ngữ chủ.
4. Viết bộ chuyển đổi từ cấu hình bên ngoài sang builder/IR.
5. Chuyển từng cấu hình và kiểm tra hành vi.
6. Ngừng parser bên ngoài khi không còn người dùng cần định dạng độc lập.

Ví dụ, một tệp YAML:

~~~yaml
report:
  source: orders
  filter:
    status: PAID
  groupBy: customerId
  metric:
    name: revenue
    operation: sum
    field: total
~~~

Có thể chuyển sang Kotlin DSL:

~~~kotlin
report("paidRevenue") {
    source("orders")
    filter {
        equal("status", "PAID")
    }
    groupBy("customerId")
    metric("revenue") {
        sum("total")
    }
}
~~~

Hình thức nội bộ có thể tận dụng kiểu dữ liệu, hàm, IDE và refactoring. Tuy nhiên, nếu người dùng nghiệp vụ vẫn cần chỉnh sửa báo cáo mà không sửa mã, chuyển đổi toàn bộ sang nội bộ có thể làm giảm khả năng tự phục vụ. Khi đó, giữ định dạng bên ngoài hoặc hỗ trợ cả hai có thể phù hợp hơn.

## 7. Các chiến lược chuyển đổi

Không phải hệ thống nào cũng cần cùng một cách di trú. Có thể chọn một trong các chiến lược sau.

| Chiến lược | Cách thực hiện | Phù hợp khi | Rủi ro chính |
| --- | --- | --- | --- |
| Chuyển một lần (big bang) | Thay toàn bộ DSL cũ bằng DSL mới tại một mốc | Phạm vi nhỏ, ít người dùng, dữ liệu dễ chuyển đổi | Khó khôi phục nếu phát sinh lỗi diện rộng |
| Chuyển dần (incremental) | Di trú theo nhóm tính năng, người dùng hoặc cấu hình | Hệ thống lớn, nhiều trường hợp sử dụng | Phải duy trì tương thích trong thời gian dài |
| Cùng tồn tại (coexistence) | Hỗ trợ cả hai cú pháp và chuyển về cùng IR | Cần thời gian chuyển đổi hoặc có nhiều nhóm người dùng | Tăng chi phí kiểm thử và tài liệu |
| Bộ chuyển đổi (adapter) | Chuyển cấu hình cũ sang mô hình mới ở biên hệ thống | Muốn giữ hệ thống cũ hoạt động trong khi xây nền tảng mới | Có thể kéo dài việc duy trì định dạng cũ |
| Phiên bản hóa (versioning) | Duy trì nhiều phiên bản cú pháp với quy tắc nâng cấp | Cấu hình được lưu lâu dài hoặc trao đổi giữa nhiều hệ thống | Tăng độ phức tạp của parser và hỗ trợ |

Có thể kết hợp các chiến lược. Ví dụ, dùng adapter để chuyển cấu hình cũ sang IR mới, sau đó di trú dần các nhóm người dùng sang cú pháp mới.

## 8. Tương thích và quản lý phiên bản

Khi DSL bên ngoài được lưu thành tệp độc lập, cấu hình có thể tồn tại lâu hơn phiên bản ứng dụng đã tạo ra nó. Vì vậy, cần quản lý phiên bản rõ ràng.

Ví dụ:

~~~yaml
version: 2
workflow: processOrder
steps:
  - id: validate
    action: validateOrder
~~~

Trường version cho biết cấu hình tuân theo phiên bản ngữ nghĩa hoặc schema nào. Cần định nghĩa:

- Phiên bản nào được hỗ trợ.
- Thay đổi nào tương thích ngược.
- Trường mới có giá trị mặc định nào.
- Trường cũ bị loại bỏ được xử lý ra sao.
- Cách chuyển đổi tự động hoặc hướng dẫn chuyển đổi thủ công.
- Cách báo lỗi khi gặp phiên bản không được hỗ trợ.

Không nên giả định rằng parser mới có thể đọc mọi cấu hình cũ theo cùng ý nghĩa. Một thay đổi nhỏ như giá trị mặc định, thứ tự đánh giá hoặc cách xử lý lỗi cũng có thể làm thay đổi hành vi.

### 8.1. Thay đổi tương thích và không tương thích

| Loại thay đổi | Ví dụ | Cách xử lý thường gặp |
| --- | --- | --- |
| Bổ sung tùy chọn không bắt buộc | Thêm trường description | Có thể tương thích nếu mặc định được xác định rõ |
| Bổ sung action mới | Thêm action generateReport | Bổ sung registry và kiểm tra quyền |
| Đổi tên trường | currency thành currencyCode | Cung cấp alias hoặc công cụ chuyển đổi |
| Đổi kiểu trường | timeout từ số sang chuỗi có đơn vị | Cần migration và thông báo lỗi rõ |
| Thay đổi giá trị mặc định | Retry mặc định từ 0 thành 3 | Có thể thay đổi hành vi; cần phiên bản hoặc cấu hình tường minh |
| Xóa cú pháp | Bỏ action cũ | Cảnh báo, thời hạn ngừng hỗ trợ và hướng dẫn thay thế |

Việc phân loại cần dựa vào ngữ nghĩa thực tế. Một trường mới không bắt buộc vẫn có thể làm thay đổi hành vi nếu nó tác động đến cách lập kế hoạch hoặc thứ tự thực thi.

## 9. Kiểm thử trong quá trình chuyển đổi

Kiểm thử là cơ sở để chứng minh hai hình thức DSL có hành vi tương đương trong phạm vi được hỗ trợ.

### 9.1. Kiểm thử tương đương

Chọn các ví dụ đại diện, viết bằng cả DSL cũ và mới, rồi chuyển thành IR. So sánh cấu trúc đã chuẩn hóa:

- Tên và mã định danh.
- Các bước và thứ tự hoặc quan hệ phụ thuộc.
- Tham số sau khi áp dụng giá trị mặc định.
- Điều kiện và biểu thức.
- Các chính sách lỗi và retry.

Nếu hai IR khác nhau, cần xác định đó là khác biệt cú pháp vô hại hay khác biệt ngữ nghĩa.

### 9.2. Kiểm thử parser và thông báo lỗi

Cần có trường hợp hợp lệ và không hợp lệ:

- Thiếu trường bắt buộc.
- Sai kiểu dữ liệu.
- Giá trị ngoài tập cho phép.
- Tham chiếu đến khái niệm không tồn tại.
- Trùng mã định danh.
- Phụ thuộc tạo chu trình.
- Cấu hình dùng phiên bản không hỗ trợ.
- Tệp có lỗi cú pháp hoặc cấu trúc lồng nhau sai.

Thông báo lỗi nên chỉ rõ tệp, vị trí hoặc đường dẫn trường, nguyên nhân và gợi ý sửa nếu có thể.

### 9.3. Kiểm thử hành vi thực thi

IR giống nhau là bằng chứng tốt về tính tương đương ở tầng mô hình, nhưng chưa đủ nếu hai đường đi có logic thực thi khác nhau. Cần xác minh cùng bộ lập kế hoạch, bộ thực thi và chính sách được dùng cho cả hai nguồn đầu vào.

Với thao tác có tác động phụ, sử dụng môi trường kiểm thử, dữ liệu giả lập hoặc chế độ dry run. Không nên chạy lặp lại thao tác thực tế như thanh toán, gửi email hay xóa dữ liệu chỉ để so sánh.

### 9.4. Kiểm thử hồi quy

Giữ lại các cấu hình cũ quan trọng như bộ mẫu hồi quy. Mỗi thay đổi parser, schema hoặc IR cần chạy lại những ví dụ này để phát hiện hành vi bị thay đổi ngoài dự kiến.

## 10. Quản lý rủi ro và vận hành

Chuyển đổi DSL có thể tác động đến cấu hình triển khai, dữ liệu, quyền hạn và quy trình nghiệp vụ. Cần lập kế hoạch cho các tình huống lỗi.

### 10.1. Lỗi phân tích và xác thực

Một cấu hình mới có thể không parse được hoặc vi phạm ràng buộc. Hệ thống nên xác thực trước khi áp dụng và không để một lỗi cấu hình làm dở dang trạng thái đang hoạt động.

Có thể dùng pipeline:

~~~text
Nhận cấu hình
    |
    v
Kiểm tra phiên bản
    |
    v
Parse
    |
    v
Validate schema và ngữ nghĩa
    |
    v
Tạo kế hoạch
    |
    v
Review / phê duyệt
    |
    v
Áp dụng
    |
    v
Theo dõi kết quả
~~~

Với cấu hình nhạy cảm, cần tách quyền tạo, kiểm tra, phê duyệt và thực thi theo chính sách của tổ chức.

### 10.2. Quyền thực thi và bảo mật

DSL bên ngoài có thể được chỉnh sửa bởi người không phải lập trình viên. Điều này làm cho việc giới hạn khả năng thực thi trở nên quan trọng.

Không nên cho phép tệp cấu hình tùy ý gọi lệnh hệ điều hành, truy cập tệp hoặc chạy mã động nếu mục tiêu chỉ là khai báo quy trình nghiệp vụ. Thay vào đó, định nghĩa danh sách action được phép, kiểu tham số, quyền cần thiết và phạm vi tài nguyên.

Bí mật như mật khẩu, token hoặc khóa API nên được tham chiếu qua kho bí mật hoặc cơ chế cấp phát an toàn. Không nên ghi trực tiếp chúng vào tệp DSL hoặc log lỗi.

### 10.3. Quan sát và khả năng khôi phục

Trong giai đoạn chuyển tiếp, cần theo dõi:

- Tỷ lệ cấu hình được parse và validate thành công.
- Số lỗi theo phiên bản và theo nhóm người dùng.
- Những tính năng cũ chưa có tương đương.
- Khác biệt IR hoặc kết quả kiểm thử.
- Lỗi thực thi sau khi chuyển đổi.
- Tần suất sử dụng DSL cũ và DSL mới.

Cần có cách quay lại phiên bản cấu hình đã biết là hợp lệ hoặc khôi phục bộ thực thi cũ khi có sự cố. Với quy trình đã tạo tác động phụ, rollback không nhất thiết là xóa thay đổi; có thể cần thao tác bù hoặc quy trình phục hồi nghiệp vụ.

## 11. Mô hình kết hợp trong giai đoạn chuyển tiếp

Trong nhiều hệ thống, giữ cả DSL nội bộ và bên ngoài là lựa chọn lâu dài chứ không chỉ là giai đoạn tạm thời.

Ví dụ:

- Lập trình viên định nghĩa action và kiểu tham số bằng mã Kotlin.
- Người vận hành cấu hình thứ tự action bằng YAML.
- Cả hai cùng tạo IR.
- Bộ thực thi chỉ hiểu IR và không phụ thuộc nguồn đầu vào.

~~~text
Kotlin DSL -----> Builder ----+
                              |
                              v
                         Workflow IR
                              |
YAML DSL --------> Parser ----+
                              |
                              v
                       Validator / Planner
                              |
                              v
                         Runtime
~~~

Cách kết hợp này cho phép phân chia trách nhiệm:

- Nhà phát triển kiểm soát những khả năng hệ thống được phép thực hiện.
- Người vận hành cấu hình những lựa chọn được công khai.
- Bộ thực thi giữ ngữ nghĩa thống nhất.
- Nhóm có thể bổ sung định dạng đầu vào khác mà không viết lại runtime.

Đổi lại, cần duy trì tài liệu cho từng hình thức, kiểm thử adapter và quy định rõ tính năng nào có thể cấu hình từ bên ngoài. Không nên để DSL bên ngoài có thể gọi mọi hàm nội bộ một cách không kiểm soát.

## 12. Tiêu chí hoàn tất chuyển đổi

Trước khi tuyên bố chuyển đổi hoàn tất, nhóm cần có bằng chứng cho các nội dung sau:

- Các trường hợp sử dụng thuộc phạm vi đã được chuyển đổi hoặc có quyết định rõ ràng về việc giữ lại.
- Cú pháp mới và ngữ nghĩa được tài liệu hóa.
- Bộ kiểm tra phát hiện lỗi cú pháp, kiểu, tham chiếu và ràng buộc miền.
- Các cấu hình đại diện đã được kiểm thử tương đương.
- Người dùng mục tiêu có thể viết, kiểm tra và vận hành cấu hình.
- Quy trình phê duyệt, phân quyền, bảo vệ bí mật và theo dõi đã được xác định.
- Phiên bản và chính sách tương thích được công bố.
- Các phụ thuộc vào DSL cũ đã được xác định và có kế hoạch xử lý.
- Có cách phục hồi khi cấu hình mới gây lỗi.
- Việc ngừng hỗ trợ hình thức cũ có thời hạn và được thông báo rõ.

Nếu vẫn còn một số cấu hình chỉ chạy được ở DSL nội bộ, không nhất thiết phải coi toàn bộ chuyển đổi thất bại. Có thể giữ chúng trong phạm vi nội bộ, miễn là ranh giới được ghi nhận và không gây nhầm lẫn cho người dùng.

## 13. Kết luận

Chuyển đổi giữa DSL nội bộ và DSL bên ngoài là thay đổi cách người dùng diễn đạt một miền bài toán. Quá trình này cần bắt đầu từ nhu cầu thật, xác định ngữ nghĩa và mô hình miền, sau đó mới thiết kế cú pháp và công cụ phù hợp.

Một lộ trình an toàn thường tách phần ngữ nghĩa khỏi cú pháp bằng mô hình trung gian, tạo parser hoặc builder để đưa các hình thức DSL về cùng một cấu trúc, kiểm thử tương đương và chuyển người dùng theo từng giai đoạn. Quản lý phiên bản, bảo mật, thông báo lỗi, khả năng khôi phục và kế hoạch ngừng hỗ trợ cần được thiết kế ngay trong quá trình chuyển đổi.

Hãy chọn hình thức DSL dựa trên người dùng, công việc và môi trường thực thi. Nếu cần cả khả năng tích hợp của DSL nội bộ và tính độc lập của DSL bên ngoài, có thể duy trì hai đầu vào cùng dùng một mô hình ngữ nghĩa và một bộ thực thi. Mục tiêu của lộ trình là để người dùng tiếp tục mô tả đúng công việc của miền trong khi hệ thống có thể phát triển mà không làm mất ý nghĩa của các cấu hình hiện có.

