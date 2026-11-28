# Business logic abuse

## 1. Lạm dụng logic nghiệp vụ là gì?

**Business logic abuse** là sử dụng các chức năng, quy trình hoặc sự thiếu ràng buộc của hệ thống để đạt kết quả trái với quy tắc nghiệp vụ được phê duyệt. Yêu cầu có thể đúng định dạng, người gọi có thể đã đăng nhập và mỗi thao tác riêng lẻ có vẻ hợp lệ, nhưng kết quả của cả chuỗi hành động vẫn làm tổn hại tài sản hoặc quyền lợi của bên khác.

Ví dụ, khách hàng được phép yêu cầu hoàn tiền cho một đơn hàng. Nếu hai yêu cầu được xử lý đồng thời và mỗi yêu cầu chỉ kiểm tra số tiền đã hoàn trước đó, cả hai có thể cùng được chấp nhận, khiến tổng tiền hoàn vượt số tiền được phép hoàn. Vấn đề nằm ở việc không giữ được quy tắc nghiệp vụ trong điều kiện đồng thời, dù cả hai request đều có số tiền dương và trỏ đến đơn hàng thật.

Trong chương **Business logic security** của module yêu cầu bảo mật, mục tiêu là chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành các yêu cầu cụ thể, đo được và kiểm chứng được. Với logic nghiệp vụ, các yêu cầu cần mô tả ai được làm gì, với đối tượng nào, ở trạng thái nào, trong giới hạn nào và bằng chứng nào phải được giữ lại.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện kịch bản lạm dụng dựa trên tài sản, động cơ và chuỗi hành động.
2. Chuyển quy tắc nghiệp vụ thành bất biến và điều kiện chuyển trạng thái.
3. Đặc tả kiểm soát phía máy chủ cho giá trị, danh tính, thứ tự và số lần thực hiện.
4. Viết yêu cầu cho xử lý đồng thời, idempotency và kết quả chưa xác định.
5. Liên kết yêu cầu với kiến trúc, nhật ký, điều tra và bài kiểm thử.

## 2. Vì sao kiểm tra đầu vào và đăng nhập chưa đủ?

Kiểm tra kiểu dữ liệu trả lời những câu như “số tiền có phải số nguyên dương không?”. Xác thực trả lời “người gọi là ai?”. Phân quyền đối tượng trả lời “người này có được truy cập đơn hàng này không?”. Logic nghiệp vụ còn cần trả lời “đơn hàng hiện có đủ điều kiện hoàn số tiền này hay không, và tác động của quyết định này lên toàn bộ nghĩa vụ tài chính là gì?”.

| Lớp kiểm tra | Ví dụ | Điều vẫn có thể bị bỏ sót |
|---|---|---|
| Cú pháp và kiểu dữ liệu | Số lượng là số nguyên dương | Tổng lượng được giữ vượt tồn kho |
| Xác thực | Người gọi có phiên hợp lệ | Tài khoản hợp lệ lạm dụng ưu đãi |
| Quyền đối tượng | Người gọi sở hữu đơn hàng | Đơn hàng đã hoàn đủ tiền hoặc chưa thanh toán |
| Quyền thao tác | Nhân viên có quyền duyệt hoàn tiền | Nhân viên tự duyệt yêu cầu do mình tạo |
| Quy tắc từng request | Mã giảm giá còn hạn | Mã được áp dụng lại hoặc cộng dồn trái chính sách |
| Bất biến toàn quy trình | Tổng hoàn không vượt phần được phép hoàn | Cần giữ đúng cả khi retry, chạy đồng thời hoặc lỗi dependency |

Các lớp này bổ sung cho nhau. Logic nghiệp vụ không thay thế việc kiểm tra quyền; quyền truy cập cũng không thay thế các ràng buộc về số tiền, trạng thái hoặc số lần thực hiện.

Không nên chỉ gọi mọi hành vi bất thường là gian lận. Một người dùng có thể thao tác nhanh, gửi lại do mạng lỗi hoặc có nhiều giao dịch hợp lệ. Đặc tả cần phân biệt **vi phạm một quy tắc xác định được** với **tín hiệu rủi ro cần xác minh thêm**. Hai loại này có thể dẫn tới hành động khác nhau.

## 3. Bắt đầu từ tài sản và abuse case

Một abuse case mô tả cách quy trình có thể tạo kết quả không được phép. Đối tượng thực hiện có thể là người ngoài, tài khoản bị chiếm đoạt, khách hàng hợp lệ, nhân viên nội bộ hoặc dịch vụ tích hợp bị lỗi.

| Tài sản hoặc cam kết | Kịch bản lạm dụng | Quy tắc cần được làm rõ |
|---|---|---|
| Doanh thu và giá bán | Gửi giá hoặc mức giảm do client tự đặt | Giá cuối được tính từ dữ liệu và chính sách có thẩm quyền |
| Ngân sách khuyến mại | Áp dụng ưu đãi nhiều lần hoặc kết hợp trái điều kiện | Phạm vi sử dụng, số lần, khả năng cộng dồn và ngân sách |
| Tiền thanh toán | Hoàn nhiều lần vượt phần tiền có thể hoàn | Giới hạn tổng hoàn và việc giữ chỗ cho yêu cầu đang xử lý |
| Tồn kho | Giữ hàng lặp lại mà không có ý định thanh toán | Số lượng, thời hạn giữ và điều kiện giải phóng |
| Điểm thưởng hoặc tín dụng | Nhận lợi ích nhưng không đảo quyền lợi khi giao dịch bị hủy | Điều kiện cấp, chuyển, thu hồi và chống ghi nhận trùng |
| Quy trình phê duyệt | Bỏ qua bước duyệt hoặc đổi nội dung sau duyệt | Chuyển trạng thái hợp lệ và phạm vi dữ liệu được phê duyệt |
| Quyền lợi dùng thử | Tái sử dụng quyền lợi trái phạm vi chính sách | Đơn vị hưởng quyền lợi, thời hạn và cơ sở xác minh |
| Năng lực vận hành | Tạo nhiều công việc tốn kém nhưng giá trị thấp | Ngân sách công việc và giới hạn theo phạm vi phù hợp |

Mỗi abuse case nên có tối thiểu:

- Tài sản và kết quả cần ngăn chặn.
- Vai trò, quyền ban đầu và giả định về khả năng của người thực hiện.
- Điểm vào, đối tượng và các trạng thái có liên quan.
- Chuỗi hành động, bao gồm retry, chạy đồng thời hoặc thay đổi thứ tự nếu cần.
- Quy tắc bị vi phạm và tác động nghiệp vụ.
- Kiểm soát phòng ngừa, tín hiệu phát hiện và tiêu chí kiểm thử.

Không giới hạn phân tích ở màn hình chính. API mobile, phiên bản API cũ, công cụ hỗ trợ khách hàng, import dữ liệu, tác vụ nền và webhook đều có thể thay đổi cùng một tài sản. Quy tắc chỉ tồn tại trong một giao diện không tạo ra bảo đảm toàn hệ thống.

## 4. Từ quy tắc thành yêu cầu có thể kiểm chứng

Một quy tắc như “không cho lạm dụng hoàn tiền” cần được tách thành các thành phần rõ ràng:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Chủ thể | Ai được khởi tạo, duyệt và thực thi? |
| Đối tượng | Đơn hàng, tenant, tài khoản nhận tiền hoặc quyền lợi nào? |
| Điều kiện trước | Đã thanh toán, chưa hết hạn, không bị khóa và còn ngân sách không? |
| Dữ liệu có thẩm quyền | Giá, số tiền đã thu và trạng thái lấy từ đâu? |
| Bất biến | Đại lượng nào không được vượt hoặc bị ghi nhận trùng? |
| Chuyển trạng thái | Từ trạng thái nào sang trạng thái nào, bởi ai? |
| Ngữ nghĩa lỗi | Từ chối, chờ duyệt, thất bại xác nhận hay chưa xác định kết quả? |
| Bằng chứng | Nhật ký, phiên bản chính sách và dữ liệu nào chứng minh quyết định? |

Ví dụ chuyển đổi:

> Yêu cầu chưa rõ: Không cho người dùng hoàn tiền nhiều lần.

> Yêu cầu rõ hơn: Khi chấp nhận một yêu cầu hoàn tiền để thực thi, máy chủ phải giữ chỗ số tiền tương ứng bằng thao tác nguyên tử với việc kiểm tra ngân sách còn lại của đơn hàng. Tổng tiền hoàn đã thành công và số tiền đang được giữ chỗ không được vượt số tiền được phép hoàn. Yêu cầu gửi lại hoặc callback lặp không được tạo khoản hoàn mới ngoài ngữ nghĩa idempotency đã công bố.

“Nhiều lần” không nhất thiết là sai: một đơn hàng có thể được hoàn từng phần nhiều lần. Bất biến phải phản ánh đúng điều không được phép, thay vì cấm một hành vi nghiệp vụ hợp lệ vì nó trông giống lạm dụng.

### Một số dạng bất biến thường gặp

| Dạng | Ví dụ |
|---|---|
| Giới hạn tổng | Tổng lượng giữ hàng còn hiệu lực không vượt tồn kho khả dụng |
| Tính duy nhất | Một quyền lợi chỉ được cấp một lần cho một sự kiện nghiệp vụ đủ điều kiện |
| Quan hệ chủ thể | Người duyệt không được là người tạo trong quy trình yêu cầu tách nhiệm vụ |
| Ràng buộc trạng thái | Không thực thi yêu cầu chưa được phê duyệt hoặc đã bị thu hồi |
| Liên kết dữ liệu | Phê duyệt chỉ có hiệu lực với đúng nội dung và phiên bản đã xem |
| Bảo toàn giá trị | Chuyển giá trị không tạo thêm tiền hoặc điểm ngoài nghiệp vụ cho phép |
| Giới hạn thời gian | Quyền lợi chỉ được dùng trong khoảng hiệu lực do máy chủ xác định |

Bất biến cần được giữ sau mỗi thao tác có ảnh hưởng và tại ranh giới cam kết đã chọn. Nếu kiến trúc chỉ hội tụ sau một khoảng thời gian, phải nêu rõ khoảng sai lệch được chấp nhận và cơ chế xử lý; không gọi một tổng hợp cập nhật trễ là ràng buộc tài chính tức thời.

## 5. Ví dụ xuyên suốt: quy trình hoàn tiền

### 5.1. Mô hình giản lược

Giả sử một hệ thống cho phép hoàn từng phần đối với đơn hàng đã thu tiền, trong cùng một loại tiền tệ. Định nghĩa:

```text
C = số tiền đã thu được phép dùng làm cơ sở hoàn theo chính sách
R = tổng tiền hoàn đã xác nhận thành công
P = tổng tiền đang giữ chỗ cho yêu cầu hoàn chưa có kết quả kết thúc

Ngân sách còn lại = C - R - P
Bất biến: 0 ≤ R + P ≤ C
```

`C` không phải số tiền còn lại sau khi đã trừ `R`; nếu định nghĩa như vậy rồi tiếp tục trừ `R`, hệ thống sẽ tính hai lần. Các khoản phí không được hoàn, giảm giá và phần tiền đủ điều kiện phải được đưa vào quy tắc xác định `C` một cách rõ ràng.

Mô hình này chưa bao phủ mọi trường hợp như tranh chấp thanh toán, điều chỉnh sau quyết toán hoặc đa tiền tệ. Khi có các nghiệp vụ đó, cần mở rộng sổ cái và quy tắc phân bổ; không tự coi công thức giản lược là đầy đủ cho mọi sản phẩm thanh toán.

Số tiền nên được biểu diễn bằng đơn vị tiền tệ nhỏ nhất hoặc kiểu số thập phân có quy tắc chính xác. Phải chỉ rõ loại tiền, độ chính xác và cách làm tròn. Không cộng các số tiền khác loại tiền tệ hoặc dùng phép tính số thực thiếu kiểm soát để quyết định ngân sách.

### 5.2. Vì sao cần tính cả tiền đang giữ chỗ?

Một đơn hàng có `C = 1.000.000`, đã hoàn thành công `R = 200.000`, chưa có yêu cầu đang xử lý nên `P = 0`. Hai yêu cầu khác nhau cùng xin hoàn `500.000`.

Nếu mỗi request đọc riêng số đã hoàn, cả hai đều thấy còn `800.000` và cùng đi tiếp. Tổng hoàn có thể thành `1.200.000`, vượt cơ sở hoàn.

Nếu kiểm tra và giữ chỗ đúng, chỉ một yêu cầu có thể giữ `500.000`. Khi đó:

```text
R = 200.000
P = 500.000
Ngân sách còn lại = 300.000
```

Yêu cầu khác xin `500.000` phải bị từ chối hoặc chuyển sang trạng thái chưa được chấp nhận theo hợp đồng, không được gửi tiếp tới bên xử lý thanh toán như một khoản đã đủ ngân sách.

### 5.3. Chuyển giữ chỗ thành kết quả

- Khi khoản hoàn thành công được xác minh, chuyển giá trị tương ứng từ `P` sang `R` trong cùng cập nhật nhất quán của trạng thái nội bộ.
- Khi xác nhận khoản hoàn thất bại và không phát sinh tác động, giải phóng giá trị tương ứng khỏi `P`.
- Khi hết thời gian chờ nhưng chưa biết bên thanh toán đã thực hiện hay chưa, giữ trạng thái chưa xác định và tiếp tục hạch toán phần tiền đó trong `P` cho đến khi đối soát được.

Timeout không phải bằng chứng rằng khoản hoàn chưa xảy ra. Tự trả lại ngân sách ngay khi timeout có thể cho phép một khoản hoàn mới trong khi khoản cũ vẫn thành công ở hệ thống bên ngoài.

## 6. Đặc tả máy trạng thái và phạm vi phê duyệt

Một mô hình tham khảo:

```text
PENDING_REVIEW → APPROVED → EXECUTING → SUCCEEDED
       ↓             ↓          ↓
   REJECTED        CANCELLED   OUTCOME_UNKNOWN
                                  ↓
                    SUCCEEDED hoặc FAILED_CONFIRMED
```

Các trạng thái cần có ngữ nghĩa rõ:

| Trạng thái | Ý nghĩa trong ví dụ |
|---|---|
| PENDING_REVIEW | Đã ghi nhận đề nghị, chưa cam kết đủ điều kiện thực thi và chưa giữ ngân sách |
| APPROVED | Đã duyệt đúng nội dung và đã giữ chỗ ngân sách bằng thao tác nhất quán |
| EXECUTING | Đang thực hiện khoản hoàn; phần giữ chỗ vẫn còn hiệu lực |
| SUCCEEDED | Có bằng chứng khoản hoàn thành công; ngân sách được ghi nhận vào `R` |
| FAILED_CONFIRMED | Đã xác minh không có khoản hoàn thành công; có thể giải phóng giữ chỗ |
| OUTCOME_UNKNOWN | Chưa xác định được kết quả; không tự giải phóng giữ chỗ |
| CANCELLED | Đã hủy an toàn trước tác động hoặc sau khi có xác nhận cần thiết theo hợp đồng |
| REJECTED | Đề nghị không được duyệt, không được thực thi |

Ví dụ này cho phép hủy `APPROVED` khi công việc chưa được gửi đi và hệ thống xác nhận việc hủy không xung đột với bắt đầu thực thi. Nếu cần hủy sau khi đã gửi, phải bổ sung quy trình riêng; không chỉ đổi trường trạng thái.

### 6.1. Điều kiện chuyển trạng thái

Với mỗi chuyển trạng thái, cần ghi người có quyền, điều kiện hiện tại, phiên bản đối tượng, tác động lên ngân sách và audit bắt buộc. Gọi trực tiếp API thực thi không được bỏ qua bước phê duyệt.

Trạng thái hiện tại phải được xác minh tại thời điểm cam kết thay đổi. Việc người dùng đã mở màn hình lúc yêu cầu còn hợp lệ không tạo quyền thực thi sau khi yêu cầu đã bị thu hồi hoặc nội dung đã đổi.

### 6.2. Phê duyệt phải gắn với nội dung

Phê duyệt cần liên kết với đơn hàng, tenant, số tiền, loại tiền, nơi nhận và các trường nhạy cảm có liên quan. Nếu các trường đó thay đổi, phê duyệt cũ không được tự động có hiệu lực với nội dung mới.

Một cách đặc tả là gắn phê duyệt với phiên bản bất biến của đề nghị. Máy chủ kiểm tra phiên bản đó trước khi chuyển sang thực thi. Cách triển khai cụ thể có thể khác, nhưng phải chứng minh rằng đối tượng được thực thi chính là đối tượng đã được duyệt.

### 6.3. Tách nhiệm vụ

Nếu chính sách yêu cầu người tạo và người duyệt khác nhau, phải xác định danh tính dùng để so sánh. Hai vai trò hoặc hai phiên khác nhau chưa chắc đại diện hai người khác nhau. Trong môi trường có ánh xạ nhân sự có thẩm quyền, cần dùng đúng danh tính đó theo chính sách tách nhiệm vụ.

Cũng cần xem xét hành vi chia nhỏ giao dịch để tránh ngưỡng duyệt. Nếu rủi ro phụ thuộc tổng giá trị trong một khoảng thời gian, phải định nghĩa phép cộng dồn, phạm vi chủ thể và cửa sổ đánh giá; chỉ đặt một ngưỡng trên mỗi request có thể không đáp ứng mục tiêu.

## 7. Đồng thời, idempotency và ranh giới hệ thống

### 7.1. Kiểm tra và cập nhật phải tạo một quyết định nhất quán

Không tách rời thao tác đọc ngân sách khỏi thao tác giữ chỗ nếu giữa hai bước có thể có giao dịch khác. Có thể dùng cập nhật có điều kiện, khóa hoặc cơ chế tuần tự hóa phù hợp với kiến trúc. Yêu cầu cần nêu bất biến và phạm vi bảo đảm, không chỉ chỉ định một kỹ thuật rồi mặc nhiên coi là an toàn.

Pseudocode mô tả ý định:

```text
approve_refund(actor, refund_id, expected_version):
    begin local_transaction
        refund = load_current_refund(refund_id)
        require actor may approve this tenant and object
        require refund.state == PENDING_REVIEW
        require refund.version == expected_version
        require separation_of_duties_is_satisfied(actor, refund)
        require sufficient_refundable_budget(refund.order, refund.amount)

        reserve_refundable_budget(refund.order, refund.amount)
        set_state_and_approval(refund, APPROVED, actor)
        record_required_audit_and_execution_intent(refund)
    commit local_transaction
```

Đây không phải mã triển khai hoàn chỉnh. Cơ chế thực tế phải giữ được tính nhất quán của các kiểm tra có thể thay đổi đồng thời và hành vi khi ghi audit hoặc ý định thực thi thất bại.

### 7.2. Idempotency có phạm vi và ngữ nghĩa

Idempotency bảo đảm các lần gửi lại đại diện cùng một thao tác không tạo thêm tác động ngoài hợp đồng. Cần xác định:

- Khóa có phạm vi theo tenant, loại thao tác và danh tính nào.
- Cùng khóa nhưng payload khác phải bị xử lý ra sao.
- Các request cùng khóa đến đồng thời được hợp nhất thế nào.
- Thời gian giữ kết quả và hành vi sau khi khóa hết hiệu lực.
- Client nhận lại trạng thái nào nếu thao tác vẫn đang chạy hoặc chưa xác định kết quả.

Một khóa idempotency không thay thế bất biến ngân sách. Hai khóa khác nhau vẫn có thể yêu cầu tổng số tiền quá lớn; cả hai phải chịu cùng kiểm tra và giữ chỗ.

### 7.3. Hệ thống thanh toán không nằm trong giao dịch nội bộ

Cam kết nguyên tử trong cơ sở dữ liệu nội bộ không tự bao phủ một lời gọi mạng tới bên thanh toán. Thiết kế cần bảo đảm ý định thực thi được lưu bền vững, lời gọi được định danh, kết quả có thể đối soát và việc gửi lại không tạo khoản hoàn trùng theo hợp đồng tích hợp.

Một cơ chế lưu ý định cùng giao dịch, chẳng hạn transactional outbox, có thể hỗ trợ không mất công việc cần gửi. Nó không tự tạo bảo đảm tác động đúng một lần ở hệ thống bên ngoài. Vẫn cần ngữ nghĩa idempotency phía tích hợp, xác minh kết quả và xử lý trạng thái chưa xác định.

Callback lặp, đến muộn hoặc sai thứ tự phải được xử lý nhất quán. Khóa nhận diện sự kiện cần có phạm vi phù hợp với bên cung cấp và tài khoản tích hợp; một sự kiện đã xử lý không được cộng tiền lần nữa. Sự kiện cũ không được làm lùi trạng thái thành công về trạng thái đang chờ.

## 8. Dữ liệu có thẩm quyền và ranh giới tin cậy

### 8.1. Máy chủ quyết định giá trị và điều kiện

Client có thể đề nghị sản phẩm, số lượng, mã ưu đãi hoặc số tiền muốn hoàn. Máy chủ phải tính và xác minh các giá trị có ảnh hưởng nghiệp vụ từ nguồn có thẩm quyền.

Những trường thường không được tin trực tiếp từ client gồm giá cuối, số tiền đã thanh toán, mức giảm được chấp thuận, số dư, trạng thái đã duyệt, vai trò nhân viên và mức độ đủ điều kiện hưởng ưu đãi. Việc client ký hoặc mã hóa dữ liệu không tự chứng minh dữ liệu còn hiệu lực nếu điều kiện nghiệp vụ đã thay đổi.

Nếu giá hoặc điều kiện có thể thay đổi giữa bước xem và bước xác nhận, cần định nghĩa cơ chế chốt giá, phiên bản báo giá, thời hạn hiệu lực và cách xử lý báo giá hết hạn. Không để client tiếp tục dùng một điều kiện cũ vô thời hạn chỉ vì đã từng nhận nó từ máy chủ.

### 8.2. Quyền gắn với hành động và trạng thái hiện tại

Kiểm tra quyền phải bao phủ chủ thể, tenant, đối tượng, loại thao tác và trạng thái. Người dùng được xem đơn hàng không mặc nhiên được thay nơi nhận tiền hoàn; người có quyền tạo yêu cầu không mặc nhiên được duyệt yêu cầu đó.

API công khai, API nội bộ, công cụ hỗ trợ và batch phải thực thi cùng bất biến nghiệp vụ. Chúng có thể dùng vai trò khác nhau nhưng không được tạo ra những đường cập nhật trực tiếp bỏ qua ngân sách hoặc máy trạng thái.

Khi có hành động đại diện, audit cần phân biệt danh tính dịch vụ thực hiện với danh tính người đã ủy quyền. Không dùng tài khoản kỹ thuật chung để làm mất dấu ai đã yêu cầu thao tác nhạy cảm.

### 8.3. Xác minh sự kiện bên ngoài

Webhook phải được xác minh nguồn theo hợp đồng tích hợp. Sau đó, hệ thống vẫn cần đối chiếu định danh giao dịch, số tiền, loại tiền và liên kết với đối tượng nội bộ. Một thông báo đúng nguồn nhưng không khớp giao dịch không được tự động làm thay đổi sổ cái của đơn hàng khác.

Tenant và quyền sở hữu của giao dịch phải được tra từ ánh xạ nội bộ đáng tin cậy, không chỉ theo trường tự khai trong payload. Callback hợp lệ cũng phải chịu quy tắc chống xử lý trùng và chuyển trạng thái sai thứ tự.

### 8.4. Thời gian và cấu hình cũng là đầu vào nghiệp vụ

Điều kiện hết hạn cần dựa trên đồng hồ hoặc nguồn thời gian được hệ thống quy định, có múi giờ và biên cửa sổ rõ ràng. Không lấy thời gian trên thiết bị người dùng làm căn cứ cuối cùng để cấp quyền lợi.

Phiên bản chính sách cần được giữ khi quyết định phụ thuộc vào thời điểm. Ví dụ, có thể áp dụng điều kiện ưu đãi đã chốt tại thời điểm mua hoặc điều kiện tại thời điểm yêu cầu hoàn; tổ chức phải chọn và mô tả rõ, không để các dịch vụ tự chọn khác nhau.

## 9. Áp dụng cùng cách tư duy cho khuyến mại và quyền lợi

Ví dụ hoàn tiền cho thấy vai trò của ngân sách và trạng thái. Với ưu đãi, cần xác định ít nhất bốn nhóm ràng buộc:

1. **Điều kiện hưởng:** sản phẩm, loại tài khoản, sự kiện nguồn và thời gian đủ điều kiện.
2. **Phạm vi sử dụng:** theo đơn hàng, tài khoản, tổ chức hoặc một đơn vị quyền lợi được xác định rõ.
3. **Giới hạn tổng:** số lượt hoặc giá trị ngân sách của chiến dịch.
4. **Khả năng kết hợp:** ưu đãi nào có thể cộng dồn, thứ tự tính và giới hạn giá trị cuối.

Ví dụ một chiến dịch có tối đa 1.000 lượt hưởng và mỗi tài khoản đủ điều kiện được dùng một lần. Nếu hệ thống chỉ đếm đơn hàng đã hoàn tất, các đơn đang giữ ưu đãi có thể làm tổng lượt được cam kết vượt ngân sách. Cần định nghĩa giữ chỗ, xác nhận sử dụng và giải phóng khi hủy, tương tự cách quản lý ngân sách trong ví dụ hoàn tiền.

Một bất biến có thể là:

```text
lượt đã xác nhận + lượt đang giữ chỗ hợp lệ ≤ 1.000
```

Đồng thời, ràng buộc duy nhất trên đơn vị quyền lợi phải được giữ dưới tải đồng thời. Chỉ kiểm tra “chưa dùng mã” bằng một truy vấn trước khi tạo đơn chưa đủ để chứng minh điều đó.

Với điểm thưởng, cần định nghĩa sự kiện nguồn và quan hệ với việc hủy hoặc hoàn đơn. Một callback thanh toán lặp không được cấp điểm hai lần. Khi hoàn tiền, số điểm cần thu hồi phải theo chính sách đã được phê duyệt; không mặc nhiên giả định người dùng vẫn chưa sử dụng điểm.

Nếu sản phẩm cần giới hạn theo một cá nhân thay vì tài khoản, phải xác định cơ sở nhận diện hợp lệ và độ tin cậy của nó. Cùng địa chỉ IP không tự chứng minh cùng một người; nhiều tài khoản cũng không tự chứng minh có vi phạm. Các tín hiệu liên kết cần được dùng theo chính sách rủi ro, với dữ liệu và quyền truy cập phù hợp.

## 10. Kiểm soát tốc độ, tích lũy và chi phí lạm dụng

Các bất biến bảo toàn tiền hoặc quyền lợi ngăn kết quả không được phép, nhưng chưa chắc ngăn được một quy trình hợp lệ bị sử dụng với khối lượng gây hại. Có thể cần thêm hạn mức và kiểm soát hành vi.

| Kiểm soát | Mục đích | Điều phải đặc tả |
|---|---|---|
| Giới hạn tần suất | Hạn chế lượng thao tác trong một khoảng | Chủ thể, cửa sổ, điểm đếm và phản hồi khi vượt |
| Giới hạn tích lũy | Kiểm soát tổng giá trị hoặc quyền lợi | Cách cộng dồn, thời điểm ghi nhận và xử lý khoản đang chờ |
| Giới hạn đồng thời | Giảm tác động của nhiều công việc cùng chạy | Đơn vị công việc và vòng đời chiếm tài nguyên |
| Thời gian giữ tài nguyên | Tránh giữ hàng hoặc quyền lợi vô hạn | Điểm bắt đầu, hết hạn và giải phóng an toàn |
| Xác minh bổ sung | Giảm rủi ro trước thao tác nhạy cảm | Tín hiệu kích hoạt, phương thức và thời hạn quyết định |
| Duyệt thủ công | Xử lý tình huống chưa đủ bằng chứng | Hàng đợi, người có quyền, thời hạn và trạng thái trả người dùng |

Các khóa giới hạn phải phù hợp với kịch bản đe dọa. Giới hạn theo IP có thể hỗ trợ một tầng nhưng không thay thế giới hạn theo tenant hoặc tài sản bị tác động. Giới hạn theo tài khoản cũng không tự bao phủ mọi kịch bản sử dụng nhiều danh tính.

Không để kiểm soát chống lạm dụng tạo ra một cơ chế gây hại mới. Ví dụ, chỉ cần biết mã tài khoản của người khác mà có thể làm tài khoản đó bị khóa lâu dài là một rủi ro cần phân tích. Các quyết định tăng mức xác minh, giữ yêu cầu để xem xét hoặc từ chối cần có phạm vi, thời hạn và đường xử lý phù hợp.

Tín hiệu nghi ngờ không nên tự biến thành bằng chứng chắc chắn. Yêu cầu cần phân biệt từ chối do vi phạm bất biến với quyết định dựa trên mô hình hoặc quy tắc rủi ro có thể nhầm. Với trường hợp sau, cần xác định việc xem xét lại, quyền can thiệp và dấu vết lý do.

## 11. Logging, phát hiện và phục hồi

### 11.1. Ghi quyết định nghiệp vụ có cấu trúc

Nhật ký HTTP thông thường có thể cho biết endpoint và mã phản hồi nhưng thiếu lý do nghiệp vụ. Một bản ghi quyết định nên thể hiện các trường phù hợp:

- Mã thao tác, mã đối tượng và tenant trong phạm vi được phép lưu.
- Danh tính thực hiện, danh tính đại diện và vai trò có hiệu lực.
- Trạng thái trước, trạng thái sau, phiên bản đối tượng và chính sách.
- Quy tắc đã được đánh giá, kết quả chấp nhận hoặc từ chối và mã lý do.
- Giá trị nghiệp vụ cần thiết, như số tiền và loại tiền, theo chính sách dữ liệu.
- Mã idempotency hoặc tham chiếu đã được bảo vệ phù hợp, mã giao dịch tích hợp và mã liên kết điều tra.
- Thời điểm quyết định, người duyệt và bằng chứng đối soát khi liên quan.

Không ghi token, mật khẩu hoặc toàn bộ dữ liệu thanh toán nhạy cảm chỉ để thuận tiện điều tra. Nhật ký và sổ cái có mục đích khác nhau: audit giải thích ai quyết định gì, còn sổ cái ghi nhận giá trị nghiệp vụ có thẩm quyền. Không coi một dòng log rời rạc là thay thế cho cập nhật tài chính nhất quán.

Quyền sửa hoặc xóa audit phải được kiểm soát theo chính sách. Đặc tả cũng cần nói rõ hành vi khi không ghi được bằng chứng bắt buộc: từ chối thao tác hoặc sử dụng cơ chế bền vững đã được thiết kế, thay vì mặc nhiên bỏ qua.

### 11.2. Phát hiện dựa trên ý nghĩa nghiệp vụ

Những tín hiệu hữu ích có thể gồm nhiều yêu cầu gần ngưỡng duyệt, thay đổi liên tục nội dung sau phê duyệt, callback trùng bất thường, số lượng lớn kết quả chưa xác định hoặc cố thực thi từ trạng thái không hợp lệ.

Mỗi tín hiệu cần có phạm vi, cửa sổ, dữ liệu nguồn, chủ sở hữu và hành động tiếp theo. Không mặc định rằng mọi lần vi phạm đều có ý đồ tấn công; lỗi tích hợp hoặc thay đổi sản phẩm cũng có thể tạo mẫu tương tự.

Chỉ số nên tách rõ:

- Số yêu cầu bị từ chối bởi từng bất biến xác định.
- Số yêu cầu bị giữ để đánh giá rủi ro và thời gian chờ xem xét.
- Số khoản chưa xác định kết quả, tổng giá trị đang giữ chỗ và tuổi tồn đọng.
- Số sai lệch giữa trạng thái nội bộ và bên tích hợp qua đối soát.
- Số trường hợp bị chặn nhưng sau đó được xác minh là hợp lệ, kèm tập mẫu đã xem xét.

Không gọi tổng số tiền trong các yêu cầu bị từ chối là “thiệt hại đã ngăn chặn” nếu chưa có căn cứ. Cùng một thao tác có thể bị gửi lại nhiều lần; không phải mọi yêu cầu bị chặn đều sẽ tạo tổn thất thực tế.

### 11.3. Phục hồi và can thiệp có kiểm soát

Khi phát hiện sai lệch, cần quy trình cô lập phạm vi, dừng loại thao tác bị ảnh hưởng nếu cần, đối soát bằng chứng và khôi phục trạng thái. Không sửa trực tiếp tổng tiền hoặc bộ đếm để chúng “trông đúng” mà bỏ qua các giao dịch nguồn.

Các thao tác bù trừ phải có quyền, lý do, tham chiếu đến sự kiện ban đầu và cơ chế chống thực hiện trùng. Việc có quyền khắc phục không nên tạo đường bỏ qua mọi kiểm soát ngân sách hoặc audit.

Khoản `OUTCOME_UNKNOWN` cần có chủ sở hữu và thời hạn rà soát. Thời hạn này dùng để nâng cấp xử lý; nó không tự chứng minh đã an toàn để giải phóng tiền giữ chỗ. Muốn thay đổi ngân sách vẫn cần bằng chứng theo hợp đồng tích hợp và nghiệp vụ.

## 12. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây dùng mô hình hoàn tiền đơn tiền tệ ở phần trước. Đây là ví dụ đặc tả, không phải chính sách tài chính chung cho mọi hệ thống.

| Mã | Yêu cầu | Bằng chứng nghiệm thu chính |
|---|---|---|
| BL-01 | Máy chủ phải xác định tenant, quyền đối tượng, cơ sở hoàn `C`, loại tiền và trạng thái hiện tại từ nguồn có thẩm quyền | Request có giá trị tự khai mâu thuẫn không làm thay đổi dữ liệu có thẩm quyền |
| BL-02 | Trong các giao dịch thuộc mô hình, `R + P` không vượt `C`; kiểm tra ngân sách và giữ chỗ phải là một quyết định nguyên tử trong phạm vi cam kết | Nhiều yêu cầu đồng thời với tổng số tiền lớn hơn ngân sách |
| BL-03 | Chỉ các chuyển trạng thái được công bố mới được thực hiện; mọi đường gọi có tác động phải tuân cùng điều kiện | Gọi trực tiếp API thực thi, API hỗ trợ và tác vụ nền ở trạng thái sai |
| BL-04 | Phê duyệt phải gắn với đúng phiên bản nội dung; không cho sửa trực tiếp trường nhạy cảm của yêu cầu đã duyệt để kế thừa phê duyệt cũ | Thay số tiền, loại tiền, đơn hàng hoặc nơi nhận sau duyệt |
| BL-05 | Trong quy trình yêu cầu tách nhiệm vụ, người tạo không được tự duyệt theo danh tính có thẩm quyền đã chọn | Dùng hai vai trò hoặc hai phiên của cùng danh tính |
| BL-06 | Cùng khóa idempotency trong phạm vi đã công bố không tạo khoản hoàn thứ hai; cùng khóa nhưng nội dung khác phải bị từ chối theo hợp đồng | Gửi lại tuần tự và đồng thời, kể cả khi phản hồi trước bị mất |
| BL-07 | Timeout của tích hợp không tự làm khoản hoàn thất bại và không tự giải phóng `P`; kết quả chưa xác định phải được đối soát | Bên tích hợp thực hiện thành công nhưng phản hồi bị mất |
| BL-08 | Callback phải được xác minh nguồn và đối chiếu giao dịch; xử lý lặp hoặc sai thứ tự không làm tăng `R` lần nữa hoặc làm lùi trạng thái | Callback trùng, đến muộn, sai tham chiếu và không hợp lệ |
| BL-09 | Chuyển từ giữ chỗ sang thành công hoặc giải phóng phải cập nhật nhất quán trạng thái và ngân sách nội bộ, không tạo khoảng trống cho khoản mới dùng trùng giá trị | Lỗi giữa các bước cập nhật và khởi động lại worker |
| BL-10 | Quyết định duyệt, thực thi, từ chối, đối soát và can thiệp phải có audit theo chính sách; dữ liệu nhạy cảm phải được giới hạn | Đối chiếu audit với giao dịch và kiểm tra quyền đọc, sửa, xuất |
| BL-11 | Ngoại lệ nghiệp vụ phải có phạm vi, người phê duyệt, thời hạn và cơ chế thu hồi; không tự bỏ bất biến tài chính nền tảng | Ngoại lệ hết hạn, sửa cấu hình trái quyền và thao tác vận hành |

Các tham số của hợp đồng idempotency, thời hạn lưu bằng chứng, quyền đọc audit và lịch đối soát phải được chốt theo sản phẩm. Nếu chưa chốt, cần ghi đó là điểm chưa hoàn thiện của bản đặc tả triển khai, không giấu dưới các cụm như “giữ đủ lâu” hoặc “kiểm tra định kỳ”.

## 13. Tiêu chí nghiệm thu và dữ liệu kiểm thử

### 13.1. Hai yêu cầu cùng vượt ngân sách

```gherkin
Given đơn hàng có C = 1.000.000, R = 200.000 và P = 0
And hai đề nghị khác nhau đều xin hoàn 500.000 cùng loại tiền
And mọi điều kiện quyền và phê duyệt khác đều hợp lệ
When hai thao tác duyệt cùng tới điểm kiểm tra ngân sách
Then chỉ một đề nghị được chấp nhận giữ chỗ 500.000
And đề nghị còn lại không được gửi để thực thi như khoản đã được duyệt
And R + P không vượt 1.000.000
And quyết định của cả hai thao tác có thể đối chiếu bằng bằng chứng
```

Sử dụng điểm đồng bộ để hai luồng thực sự cạnh tranh ngân sách. Chỉ gửi hai request lần lượt chưa chứng minh khả năng giữ bất biến dưới race condition. Kiểm tra cả dữ liệu nội bộ và số yêu cầu thực tế gửi tới bên tích hợp.

### 13.2. Gửi lại cùng thao tác

```gherkin
Given một yêu cầu hoàn 500.000 đã có khóa idempotency trong phạm vi tenant A
When client gửi lại cùng khóa và cùng nội dung nhiều lần
Then các lần gọi tham chiếu cùng một thao tác nghiệp vụ
And không tạo khoản giữ chỗ hoặc khoản hoàn bổ sung

When client dùng cùng khóa nhưng đổi số tiền thành 600.000
Then hệ thống từ chối xung đột nội dung theo hợp đồng
And dữ liệu của thao tác ban đầu không bị thay đổi
```

Lặp lại với các request đến đồng thời và phản hồi ban đầu bị mất. Dùng khóa mới cho một đề nghị khác vẫn phải chịu kiểm tra ngân sách BL-02; idempotency không phải quyền bỏ qua giới hạn tổng.

### 13.3. Thay nội dung sau duyệt

```gherkin
Given một đề nghị đã được duyệt với số tiền, nơi nhận và phiên bản xác định
When client yêu cầu sửa trực tiếp một trường nhạy cảm của đề nghị đã duyệt
Then thao tác sửa bị từ chối theo BL-04
And phê duyệt cũ chỉ còn tham chiếu nội dung ban đầu
And muốn thay nội dung phải tạo phiên bản hoặc đề nghị mới theo quy trình
```

Nếu sản phẩm cho phép thay đổi qua một quy trình riêng, tiêu chí phải mô tả việc vô hiệu hóa phê duyệt và xử lý giữ chỗ an toàn. Không chỉ kiểm tra nút sửa đã bị ẩn trên giao diện.

### 13.4. Bỏ qua bước và tự phê duyệt

Tạo đề nghị ở `PENDING_REVIEW`, sau đó gọi trực tiếp API thực thi bằng người dùng hoặc dịch vụ không có đủ điều kiện. Kết quả phải không tạo tác động tài chính và không chuyển thẳng sang `EXECUTING`.

Với chính sách tách nhiệm vụ, thử duyệt bằng một phiên khác của cùng danh tính đã tạo yêu cầu. Thao tác vẫn phải bị từ chối. Sau đó kiểm tra người duyệt hợp lệ, đề nghị bị thu hồi và phiên bản đã cũ để chứng minh quyết định dựa trên trạng thái hiện tại.

### 13.5. Timeout và callback đến muộn

Giữ phản hồi của bên thanh toán trong khi bên đó đã ghi nhận khoản hoàn thành công. Hệ thống nội bộ phải chuyển sang hoặc duy trì trạng thái chưa xác định theo hợp đồng và giữ phần tiền trong `P`.

Gửi callback hợp lệ sau đó hai lần. Sau xử lý, khoản tiền chỉ được chuyển từ `P` sang `R` một lần. Gửi tiếp một sự kiện cũ không được làm lùi trạng thái hoặc mở lại ngân sách. Callback không hợp lệ hoặc thuộc giao dịch khác không được tác động đến khoản hoàn này.

### 13.6. Lỗi giữa cập nhật nội bộ và thực thi bên ngoài

Các tình huống cần có gồm:

1. Ghi giữ chỗ thất bại trước khi cam kết giao dịch nội bộ.
2. Giao dịch nội bộ đã cam kết nhưng worker chưa gửi yêu cầu ra ngoài.
3. Bên ngoài đã xử lý nhưng kết quả chưa được ghi nội bộ.
4. Worker khởi động lại và nhận lại cùng công việc.
5. Audit bắt buộc không thể ghi theo cơ chế đã chọn.

Kết quả phải tuân theo hợp đồng: không gửi một khoản chưa được cấp ngân sách, không mất ý định đã cam kết, không tạo tác động trùng và không coi trạng thái chưa xác định là thất bại chắc chắn. Cần đối chiếu sổ cái, trạng thái yêu cầu, công việc bền vững và giao dịch bên tích hợp.

### 13.7. Kiểm thử biên và đường vào khác

Bao gồm số tiền bằng 0, âm, vượt giới hạn biểu diễn, khác loại tiền, sát biên làm tròn, đúng bằng ngân sách còn lại và lớn hơn ngân sách một đơn vị nhỏ nhất. Xác minh quy tắc dựa trên biểu diễn tiền đã công bố, không chỉ dựa vào dữ liệu hiển thị.

Lặp các bất biến cốt lõi qua API mobile, công cụ hỗ trợ, import và tác vụ nền có liên quan. Đưa vào trường hợp tenant khác, định danh đối tượng đã bị thay đổi và quyền bị thu hồi theo chính sách. Một đường gọi không được kiểm tra có thể làm mất bảo đảm của toàn quy trình.

## 14. Truy vết yêu cầu tới kiến trúc và vòng đời phát triển

| Abuse case | Yêu cầu liên quan | Điểm thực thi cần xác định | Bằng chứng kiểm thử |
|---|---|---|---|
| Hai khoản hoàn cùng dùng một ngân sách | BL-02, BL-09 | Giao dịch giữ chỗ và sổ cái nội bộ | Lịch thực thi đồng thời và tổng `R + P` |
| Tự nâng quyền hoặc đổi tenant | BL-01, BL-03, BL-05 | Lớp danh tính, phân quyền và dịch vụ nghiệp vụ | Request trái quyền qua từng đường vào |
| Đổi nội dung sau khi được duyệt | BL-04 | Phiên bản đề nghị và bước bắt đầu thực thi | Đối chiếu nội dung duyệt với nội dung thực thi |
| Retry tạo thêm khoản hoàn | BL-06, BL-07 | Kho idempotency, worker và tích hợp | Một thao tác nguồn, một tác động theo hợp đồng |
| Callback lặp làm tăng tổng tiền hoàn | BL-08, BL-09 | Xác minh callback, chống trùng và cập nhật trạng thái | Sự kiện lặp và sai thứ tự |
| Sửa dữ liệu để che sai lệch | BL-10, BL-11 | Phân quyền audit, đối soát và thao tác can thiệp | Dấu vết thay đổi và quyền truy cập |

Ở giai đoạn phân tích, cần làm việc với chủ quy trình để xác định điều gì thật sự không được phép. Không suy ra quy tắc quan trọng chỉ từ cách giao diện hiện tại hoạt động.

Ở giai đoạn thiết kế, biểu diễn trạng thái, bất biến, nguồn dữ liệu và ranh giới giao dịch. Với hành động qua hệ thống bên ngoài, mô tả cả lỗi mạng, kết quả chưa xác định và đối soát thay vì chỉ mô tả đường thành công.

Ở giai đoạn triển khai và nghiệm thu, gắn mã yêu cầu với các điểm kiểm tra, cập nhật dữ liệu và bài kiểm thử. Các tình huống phủ định, chuỗi thao tác và thực thi đồng thời cần được kiểm chứng cùng các use case hợp lệ.

Ở giai đoạn vận hành, duy trì audit, lịch đối soát, chủ sở hữu tồn đọng và chính sách ngoại lệ. Khi thêm ưu đãi, đổi quy tắc hoàn, thêm tiền tệ hoặc mở API mới, cần đánh giá lại bất biến và abuse case. Một thay đổi nhỏ về nghiệp vụ có thể làm kiểm soát cũ không còn đủ.

## 15. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Vấn đề | Cách làm rõ |
|---|---|---|
| “Người dùng đã đăng nhập nên được hoàn tiền” | Bỏ qua quyền đối tượng và điều kiện hiện tại | Xác định chủ thể, đối tượng, trạng thái và ngân sách |
| “Ẩn nút là đủ” | API vẫn có thể được gọi trực tiếp | Thực thi điều kiện phía máy chủ trên mọi đường có tác động |
| “Kiểm tra số tiền trước khi cập nhật” | Có khoảng hở cho giao dịch đồng thời | Giữ bất biến bằng quyết định kiểm tra và ghi nhận nhất quán |
| “Mỗi request có khóa riêng nên an toàn” | Khóa khác nhau vẫn có thể vượt tổng tiền | Kết hợp idempotency với bất biến tài nguyên hoặc giá trị |
| “Timeout thì trả lại ngân sách” | Bên ngoài có thể đã thực hiện thành công | Giữ trạng thái chưa xác định và đối soát |
| “Đã duyệt rồi thì nội dung nào cũng dùng được” | Phê duyệt bị chuyển sang đối tượng khác | Gắn phê duyệt với đúng phiên bản và trường nhạy cảm |
| “Hai tài khoản nghĩa là hai người” | Tách nhiệm vụ có thể chỉ tồn tại trên danh nghĩa | Chọn danh tính có thẩm quyền phù hợp với chính sách |
| “Tổng hợp cập nhật mỗi phút sẽ chặn vượt ngân sách” | Số liệu quan sát có thể trễ hơn quyết định thực thi | Dùng dữ liệu có thẩm quyền nhất quán cho admission nghiệp vụ |
| “Callback đúng nguồn thì cứ cộng tiền” | Có thể trùng, sai giao dịch hoặc sai thứ tự | Xác minh, đối chiếu và cập nhật trạng thái theo quy tắc |
| “Nhân viên hỗ trợ được sửa trực tiếp để khắc phục” | Tạo đường vượt kiểm soát và mất dấu vết | Dùng thao tác can thiệp có quyền, tham chiếu và audit |

## 16. Bài tập tự kiểm tra

Một hệ thống bán hàng cho phép khách hàng gửi số tiền hoàn cùng đơn hàng. Máy chủ kiểm tra người gọi sở hữu đơn hàng và số tiền nhỏ hơn tổng đã thanh toán. Hệ thống không tính khoản đang xử lý, cho phép nhân viên sửa nơi nhận sau duyệt và tự giải phóng ngân sách khi chờ bên thanh toán quá 30 giây. Callback cập nhật tổng hoàn bằng cách cộng trực tiếp số tiền nhận được.

Hãy thực hiện các việc sau:

1. Viết ít nhất bốn abuse case dựa trên tài sản và chuỗi hành động.
2. Định nghĩa `C`, `R`, `P` và nguồn có thẩm quyền của từng đại lượng.
3. Xây dựng máy trạng thái, điều kiện chuyển và điểm giữ chỗ ngân sách.
4. Viết yêu cầu về phê duyệt nội dung, tách nhiệm vụ và quyền sửa dữ liệu.
5. Đặc tả idempotency, callback trùng và kết quả chưa xác định.
6. Viết một bài kiểm thử đồng thời và một bài kiểm thử phản hồi bị mất nhưng bên thanh toán đã thành công.
7. Xác định audit, dữ liệu đối soát và người chịu trách nhiệm xử lý tồn đọng.

Một lời giải đầy đủ cần giữ được bất biến giá trị, quyền thao tác và ý nghĩa trạng thái trong cả đường thành công lẫn các tình huống lỗi. Yêu cầu bảo mật đối với business logic có giá trị khi kết quả nghiệp vụ không được phép đã được mô tả rõ và có bằng chứng kiểm chứng rằng mọi đường thực thi đều giữ được các ràng buộc đó.
