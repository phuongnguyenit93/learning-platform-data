# Yêu cầu về tính nhất quán, lịch sử, truy vết và bảo vệ dữ liệu

Khi phân tích yêu cầu cho một hệ thống dữ liệu, việc xác định hệ thống cần lưu những thực thể và thuộc tính nào mới chỉ là một phần của công việc. Ta còn phải hiểu dữ liệu được phép thay đổi như thế nào, những người dùng khác nhau cần nhìn thấy trạng thái nào, hệ thống phải giữ lại quá khứ trong bao lâu, làm sao giải thích một thay đổi đã xảy ra, và ai được phép xem hoặc sửa dữ liệu.

Bốn nhóm yêu cầu này ảnh hưởng trực tiếp đến mô hình dữ liệu:

- **Tính nhất quán** xác định những quy tắc mà dữ liệu phải luôn thỏa mãn và thời điểm các bên cần nhìn thấy cùng một trạng thái.
- **Lịch sử** xác định hệ thống phải lưu những phiên bản hoặc sự kiện nào để trả lời câu hỏi về quá khứ.
- **Truy vết** xác định cần biết ai hoặc hệ thống nào đã tạo ra thay đổi, thay đổi đến từ đâu và liên quan đến hoạt động nào.
- **Bảo vệ dữ liệu** xác định dữ liệu nào cần được giữ kín, giới hạn quyền truy cập ra sao, và dữ liệu được lưu giữ hoặc xóa theo quy tắc nào.

Các yêu cầu này thường giao nhau. Ví dụ, lịch sử thay đổi giá sản phẩm giúp giải thích vì sao một đơn hàng có tổng tiền cụ thể; nhật ký truy cập giúp phát hiện việc xem dữ liệu trái phép; còn quy tắc xóa dữ liệu cá nhân có thể ảnh hưởng đến cách lưu lịch sử và nhật ký. Vì vậy, cần khảo sát chúng cùng với yêu cầu nghiệp vụ trước khi chốt mô hình khái niệm, mô hình logic và cách lưu trữ vật lý.

## 1. Nhận diện đúng bốn nhóm yêu cầu

### 1.1. Tính nhất quán

Tính nhất quán mô tả mức độ dữ liệu phản ánh đúng các quy tắc nghiệp vụ tại một thời điểm. Một hệ thống có thể lưu dữ liệu ở nhiều bảng, dịch vụ hoặc bản sao, nhưng vẫn phải xác định được những trạng thái nào được xem là hợp lệ.

Ví dụ, với một đơn hàng:

- Số lượng mỗi dòng hàng phải lớn hơn 0.
- Tổng tiền đơn hàng phải được tính theo các dòng hàng, chiết khấu, thuế và quy tắc làm tròn đã xác định.
- Không thể xác nhận thanh toán thành công cho một khoản thanh toán đã bị từ chối.
- Một mặt hàng không được xuất kho vượt quá số lượng có thể bán, nếu nghiệp vụ không cho phép bán vượt tồn.
- Mã đơn hàng phải duy nhất trong phạm vi được quy định.

Cần phân biệt hai câu hỏi:

1. **Tính đúng đắn của trạng thái:** dữ liệu có thỏa mãn các bất biến nghiệp vụ hay không?
2. **Tính nhất quán khi quan sát:** người dùng hoặc dịch vụ khác nhìn thấy thay đổi mới vào thời điểm nào?

Một giao dịch cơ sở dữ liệu có thể bảo đảm nhiều cập nhật được thực hiện nguyên tử trong một ranh giới giao dịch. Tuy nhiên, nếu dữ liệu được sao chép sang hệ thống tìm kiếm, bộ nhớ đệm hoặc dịch vụ phân tích, các bản sao đó có thể cập nhật trễ. Khi ấy, yêu cầu cần mô tả rõ độ trễ chấp nhận được và hành vi người dùng có thể gặp.

### 1.2. Lịch sử dữ liệu

Yêu cầu lịch sử trả lời câu hỏi: **hệ thống cần biết điều gì về dữ liệu trong quá khứ?**

Không phải thuộc tính nào cũng cần lưu mọi phiên bản. Một số thuộc tính chỉ cần giá trị hiện tại; một số cần biết giá trị tại thời điểm giao dịch; một số cần lưu toàn bộ các lần thay đổi vì mục đích kiểm toán hoặc nghiệp vụ.

Ví dụ:

- Địa chỉ giao hàng tại thời điểm đặt đơn cần được giữ cùng đơn hàng, kể cả khi khách hàng đổi địa chỉ mặc định sau đó.
- Giá bán đã áp dụng cho một đơn hàng cần được giữ như một dữ kiện của giao dịch.
- Địa chỉ hiện tại của khách hàng có thể được cập nhật, nhưng nếu nghiệp vụ cần xác định khách hàng đã cư trú ở đâu trong một khoảng thời gian thì cần lưu các giai đoạn hiệu lực.
- Trạng thái đơn hàng có thể cần lịch sử chuyển trạng thái để giải quyết khiếu nại.

Lịch sử có thể được lưu dưới dạng bản ghi phiên bản, bảng lịch sử riêng, sự kiện phát sinh hoặc ảnh chụp trạng thái. Chọn cách nào phụ thuộc vào câu hỏi cần trả lời, tần suất thay đổi, dung lượng, yêu cầu truy vấn và chính sách lưu giữ.

### 1.3. Truy vết dữ liệu

Truy vết giúp giải thích nguồn gốc và quá trình thay đổi dữ liệu. Với một thay đổi quan trọng, hệ thống có thể cần biết:

- Ai thực hiện: người dùng, quản trị viên, dịch vụ hay tiến trình tự động?
- Hành động nào đã xảy ra: tạo, sửa, duyệt, hủy, xuất dữ liệu hay truy cập?
- Đối tượng nào bị tác động?
- Thay đổi xảy ra khi nào và được hệ thống ghi nhận khi nào?
- Thay đổi đến từ giao diện, API, tác vụ nền hay hệ thống tích hợp nào?
- Thay đổi thuộc yêu cầu, phiên làm việc hoặc giao dịch nào?
- Vì sao thay đổi được thực hiện, nếu nghiệp vụ yêu cầu lý do?

Truy vết không chỉ là thêm hai cột created_at và updated_at vào mọi bảng. Hai cột này cho biết một phần thời điểm, nhưng không cho biết ai đã thay đổi, thay đổi từ giá trị nào sang giá trị nào, hoặc thay đổi có liên quan đến quy trình nào.

Cũng cần phân biệt **nhật ký kiểm toán nghiệp vụ** với **nhật ký bảo mật** và **nguồn gốc dữ liệu**. Nhật ký kiểm toán ghi lại hành động trên dữ liệu nghiệp vụ; nhật ký bảo mật ghi nhận hoạt động xác thực, phân quyền và truy cập; nguồn gốc dữ liệu mô tả dữ liệu được tạo ra hoặc biến đổi từ nguồn nào trong một luồng xử lý.

### 1.4. Bảo vệ dữ liệu

Bảo vệ dữ liệu bao gồm việc giữ bí mật, bảo đảm tính toàn vẹn và duy trì khả năng truy cập phù hợp. Phân tích yêu cầu cần xác định:

- Dữ liệu nào là công khai, nội bộ, nhạy cảm hoặc bị hạn chế?
- Vai trò nào được xem, tạo, sửa, xuất hoặc xóa từng loại dữ liệu?
- Có cần giới hạn theo tổ chức, chi nhánh, chủ sở hữu hoặc phạm vi bản ghi không?
- Dữ liệu có cần mã hóa khi truyền và khi lưu không?
- Có cần che một phần, ẩn danh hoặc giả danh dữ liệu trong môi trường kiểm thử và phân tích không?
- Dữ liệu được lưu bao lâu, khi nào phải xóa hoặc ẩn danh?
- Bản sao, bản sao lưu, nhật ký và dữ liệu dẫn xuất có chịu cùng chính sách không?

Yêu cầu bảo vệ dữ liệu phải được gắn với từng loại dữ liệu và từng hoạt động. Một vai trò có thể được phép xem hồ sơ khách hàng nhưng không được xem thông tin thanh toán; nhân viên hỗ trợ có thể xem trạng thái đơn hàng nhưng không được xuất hàng loạt dữ liệu cá nhân.

## 2. Khảo sát yêu cầu trước khi thiết kế

Không nên bắt đầu bằng việc chọn ngay một kiểu lưu trữ hoặc thêm các cột kỹ thuật theo thói quen. Hãy hỏi về tình huống nghiệp vụ, hậu quả nếu dữ liệu sai, và câu hỏi mà hệ thống cần trả lời trong hiện tại lẫn tương lai.

| Nhóm | Câu hỏi cần hỏi | Hệ quả đối với mô hình dữ liệu |
|---|---|---|
| Nhất quán | Quy tắc nào không được vi phạm? Những thao tác nào phải thành công hoặc thất bại cùng nhau? | Ràng buộc, khóa, ranh giới giao dịch, cách xử lý cạnh tranh cập nhật |
| Nhất quán | Dữ liệu mới phải xuất hiện ở đâu ngay lập tức? Nơi nào chấp nhận độ trễ? | Chiến lược đọc/ghi, bản sao, bộ nhớ đệm, đồng bộ giữa dịch vụ |
| Lịch sử | Cần trả lời câu hỏi về quá khứ nào? Cần giữ giá trị cũ hay chỉ cần sự kiện? | Bảng phiên bản, bảng lịch sử, sự kiện, ảnh chụp trạng thái |
| Lịch sử | Thời điểm nào có ý nghĩa: lúc có hiệu lực, lúc ghi nhận hay cả hai? | Mốc thời gian nghiệp vụ và mốc thời gian hệ thống |
| Truy vết | Ai hoặc thành phần nào được phép tạo thay đổi? Cần lưu lý do và nguồn phát sinh không? | Trường tác nhân, nguồn, mã tương quan, nhật ký kiểm toán |
| Truy vết | Cần phát hiện sửa đổi hoặc xóa nhật ký không? | Quyền ghi, quyền đọc, lưu trữ tách biệt, cơ chế bảo đảm tính toàn vẹn |
| Bảo vệ | Dữ liệu nào nhạy cảm? Ai được truy cập theo vai trò và phạm vi nào? | Phân loại dữ liệu, mô hình quyền, ranh giới tenant, bảo vệ cột hoặc bản ghi |
| Bảo vệ | Khi hết mục đích sử dụng, dữ liệu và bản sao phải được xử lý thế nào? | Thời hạn lưu giữ, xóa, ẩn danh, vòng đời bản sao lưu |

### 2.1. Chuyển câu trả lời thành yêu cầu kiểm chứng được

Yêu cầu như “dữ liệu phải nhất quán”, “lưu lịch sử đầy đủ” hoặc “bảo mật cao” chưa đủ cụ thể để thiết kế và kiểm thử. Hãy chuyển chúng thành quy tắc có phạm vi và tiêu chí chấp nhận.

Ví dụ:

- Khi hai yêu cầu mua cùng một đơn vị tồn kho cuối cùng được xử lý đồng thời, chỉ một yêu cầu được phép giữ chỗ thành công.
- Sau khi giao dịch thanh toán được xác nhận, mọi lần đọc trực tiếp từ dịch vụ đơn hàng phải trả về trạng thái đã thanh toán; báo cáo phân tích có thể cập nhật trong tối đa một khoảng trễ được nghiệp vụ chấp thuận.
- Khi địa chỉ giao hàng của khách hàng thay đổi, đơn hàng đã tạo vẫn giữ địa chỉ được chốt tại thời điểm đặt hàng.
- Mỗi lần quản trị viên thay đổi trạng thái đơn hàng phải lưu được người thực hiện, thời điểm, trạng thái trước, trạng thái sau và lý do.
- Nhân viên hỗ trợ chỉ được xem đơn hàng thuộc phạm vi được phân công và không được xem dữ liệu thanh toán đầy đủ.
- Khi hồ sơ hết thời hạn lưu giữ, dữ liệu cá nhân phải được xóa hoặc ẩn danh theo chính sách, kể cả trong các bản sao và luồng xử lý được chính sách điều chỉnh.

Mỗi yêu cầu nên chỉ rõ đối tượng, hành động, điều kiện, kết quả mong đợi và cách xác minh. Nếu yêu cầu có con số như thời gian đồng bộ, thời hạn lưu giữ hoặc thời gian phản hồi, con số đó cần được người có thẩm quyền nghiệp vụ xác nhận.

## 3. Phân tích và mô hình hóa tính nhất quán

### 3.1. Xác định bất biến nghiệp vụ

Bất biến là quy tắc mà trạng thái dữ liệu hợp lệ phải luôn thỏa mãn. Một bất biến tốt có thể diễn đạt rõ và kiểm tra được.

Ví dụ với tồn kho:

- available_quantity không âm.
- reserved_quantity không âm.
- available_quantity + reserved_quantity không vượt quá quantity_on_hand, nếu mô hình tồn kho dùng ba đại lượng này theo định nghĩa đã thống nhất.

Ví dụ với thanh toán:

- Một giao dịch thanh toán thành công phải tham chiếu đến một đơn hàng hợp lệ.
- Tổng số tiền đã thu không được vượt số tiền phải thu, trừ trường hợp nghiệp vụ có hoàn tiền hoặc thu nhiều lần và đã định nghĩa rõ.
- Mỗi thông báo thanh toán từ nhà cung cấp phải được xử lý theo mã định danh duy nhất để tránh ghi nhận trùng.

Hãy làm rõ phạm vi của bất biến: trong một bản ghi, giữa nhiều bản ghi, trong một đơn vị nghiệp vụ, hay giữa nhiều hệ thống. Ràng buộc trong một bản ghi thường dễ biểu diễn bằng kiểu dữ liệu, NOT NULL hoặc CHECK. Ràng buộc liên quan nhiều bản ghi có thể cần khóa ngoại, chỉ mục duy nhất, giao dịch hoặc logic nghiệp vụ phối hợp.

### 3.2. Xác định ranh giới nguyên tử

Một quy trình gồm nhiều bước không đồng nghĩa tất cả các bước phải nằm trong cùng một giao dịch cơ sở dữ liệu. Cần hỏi bước nào phải cùng thành công hoặc cùng thất bại để nghiệp vụ không rơi vào trạng thái sai.

Ví dụ, khi xác nhận đơn hàng, hệ thống có thể cần tạo đơn, ghi các dòng hàng và giữ chỗ tồn kho. Nếu ba thao tác này thuộc cùng một cơ sở dữ liệu quan hệ, có thể thực hiện trong một giao dịch. Nếu tồn kho nằm ở dịch vụ khác, không thể mặc nhiên giả định một giao dịch cục bộ bao trùm cả hai dịch vụ.

Với quy trình phân tán, cần xác định:

- Trạng thái trung gian nào được phép tồn tại?
- Nếu một bước thất bại, hệ thống thử lại, hủy thao tác hay thực hiện hành động bù?
- Người dùng nhìn thấy trạng thái “đang xử lý” trong bao lâu?
- Làm sao tránh xử lý trùng khi thông điệp được gửi lại?

Mô hình dữ liệu cần thể hiện trạng thái quy trình và mã định danh nghiệp vụ đủ để hệ thống khôi phục hoặc đối soát. Không nên tuyên bố một quy trình phân tán có tính nguyên tử toàn cục nếu kiến trúc thực tế không cung cấp bảo đảm đó.

### 3.3. Xác định mức nhất quán khi đọc

Các nơi đọc dữ liệu có thể có yêu cầu khác nhau. Màn hình xác nhận thanh toán thường cần thấy trạng thái mới ngay sau khi thao tác hoàn tất. Một bảng thống kê theo ngày có thể chấp nhận dữ liệu trễ vài phút.

Hãy phân loại các luồng đọc:

- **Đọc cần trạng thái mới nhất:** dùng cho quyết định có hậu quả trực tiếp như giữ chỗ tồn kho, cấp quyền hoặc xác nhận thanh toán.
- **Đọc chấp nhận độ trễ:** dùng cho tìm kiếm, báo cáo, phân tích hoặc bảng điều khiển tổng hợp, nếu nghiệp vụ đồng ý.
- **Đọc cần thứ tự:** dùng khi các thay đổi trên cùng một đối tượng phải được quan sát theo đúng thứ tự nghiệp vụ.
- **Đọc cần dữ liệu tại một thời điểm:** dùng cho hóa đơn, báo cáo đã chốt hoặc điều tra một giao dịch trong quá khứ.

Không nên dùng cụm từ “strong consistency” hoặc “eventual consistency” như một nhãn chung cho toàn bộ hệ thống. Hãy gắn yêu cầu với đối tượng, thao tác, nơi đọc và thời gian chấp nhận được.

### 3.4. Chọn cơ chế bảo đảm phù hợp

Một số cơ chế thường được cân nhắc:

- Ràng buộc NOT NULL, CHECK, UNIQUE và khóa ngoại để chặn trạng thái sai ngay tại nơi lưu trữ.
- Giao dịch để nhóm các cập nhật cần nguyên tử.
- Khóa bi quan khi cần ngăn nhiều tiến trình sửa cùng tài nguyên trong một khoảng xử lý.
- Cập nhật lạc quan bằng cột phiên bản hoặc điều kiện cập nhật để phát hiện dữ liệu đã bị thay đổi kể từ lúc đọc.
- Khóa định danh yêu cầu hoặc khóa idempotency để việc gửi lại yêu cầu không tạo giao dịch trùng.
- Outbox hoặc cơ chế phát sự kiện đáng tin cậy khi cần đồng bộ thay đổi dữ liệu với hệ thống khác.
- Đối soát định kỳ khi có các bước phân tán có thể thất bại hoặc đến trễ.

Ví dụ cập nhật lạc quan: một bản ghi tồn kho có version = 12. Lệnh cập nhật chỉ thành công nếu version vẫn là 12; sau khi cập nhật, version tăng lên 13. Nếu một tiến trình khác đã cập nhật trước, điều kiện không còn đúng và tiến trình hiện tại phải đọc lại, tính lại hoặc báo xung đột.

## 4. Thiết kế lưu trữ lịch sử

### 4.1. Chọn câu hỏi lịch sử cần trả lời

Trước khi chọn cấu trúc, hãy viết các câu hỏi mà hệ thống cần trả lời:

- Giá trị hiện tại là gì?
- Giá trị nào có hiệu lực tại ngày X?
- Ai đã thay đổi giá trị và thay đổi vào lúc nào?
- Hệ thống đã biết thông tin gì tại thời điểm Y?
- Trạng thái đã chuyển qua những bước nào?
- Dữ liệu nào đã được dùng để tạo ra báo cáo hoặc quyết định?

Mỗi câu hỏi có thể yêu cầu một cách lưu khác nhau. Nếu chỉ cần biết địa chỉ giao hàng của đơn đã đặt, lưu bản chụp địa chỉ trên đơn hàng có thể đủ. Nếu cần xem toàn bộ lịch sử địa chỉ của khách hàng, cần một mô hình phiên bản hoặc lịch sử riêng.

### 4.2. Phân biệt thời gian hiệu lực và thời gian ghi nhận

Trong một số nghiệp vụ, hai mốc thời gian có ý nghĩa khác nhau:

- **Thời gian hiệu lực (valid time):** khoảng thời gian một dữ kiện được xem là đúng trong thế giới nghiệp vụ.
- **Thời gian ghi nhận (transaction time hoặc recorded time):** thời điểm hệ thống lưu hoặc biết dữ kiện đó.

Ví dụ, ngày 10/05 hệ thống nhận được thông báo rằng địa chỉ mới của khách hàng có hiệu lực từ ngày 01/05. Khi đó, thời gian hiệu lực bắt đầu ngày 01/05, còn thời gian ghi nhận bắt đầu ngày 10/05.

Nếu chỉ lưu updated_at = 10/05, hệ thống không thể phân biệt ngày thông tin bắt đầu đúng với ngày hệ thống nhận được thông tin. Những nghiệp vụ cần điều tra, đối soát hoặc tái dựng quyết định có thể cần cả hai loại thời gian.

### 4.3. Các mẫu lưu lịch sử phổ biến

| Mẫu | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Chỉ lưu trạng thái hiện tại | Cập nhật trực tiếp giá trị cũ | Không cần truy vấn quá khứ và dữ liệu không cần kiểm toán thay đổi |
| Lưu bản chụp tại giao dịch | Sao chép các giá trị quan trọng vào bản ghi giao dịch | Cần giữ dữ kiện đã áp dụng tại thời điểm phát sinh giao dịch |
| Bảng lịch sử/phiên bản | Mỗi giai đoạn hoặc phiên bản là một bản ghi riêng | Cần truy vấn giá trị theo khoảng thời gian hoặc xem các phiên bản |
| Nhật ký sự kiện | Ghi thêm sự kiện mô tả điều đã xảy ra | Cần biết chuỗi thay đổi, tác nhân hoặc tái dựng trạng thái từ sự kiện |
| Ảnh chụp định kỳ | Lưu trạng thái tại các mốc thời gian | Cần báo cáo lịch sử trên lượng dữ liệu lớn và chấp nhận độ phân giải theo kỳ |

Một bảng phiên bản có thể có các trường như entity_id, valid_from, valid_to, recorded_at, recorded_by và version. Khoảng thời gian cần được quy ước rõ, chẳng hạn dùng khoảng nửa mở [valid_from, valid_to) để tránh hai phiên bản cùng có hiệu lực tại đúng một thời điểm.

Ví dụ cấu trúc minh họa:

~~~sql
CREATE TABLE customer_address_history (
    history_id       BIGINT PRIMARY KEY,
    customer_id      BIGINT NOT NULL,
    address_text     VARCHAR(500) NOT NULL,
    valid_from       TIMESTAMP NOT NULL,
    valid_to         TIMESTAMP NULL,
    recorded_at      TIMESTAMP NOT NULL,
    recorded_by      VARCHAR(100) NULL,
    change_reason    VARCHAR(200) NULL
);
~~~

Đây chỉ là một ví dụ về dữ liệu có thời gian hiệu lực. Khi triển khai thực tế, cần xác định múi giờ, độ chính xác thời gian, quy tắc không chồng lấn khoảng hiệu lực, cách sửa dữ liệu nhập sai và chính sách bảo vệ địa chỉ cá nhân.

### 4.4. Không đồng nhất lịch sử với event sourcing

Lưu sự kiện có thể giúp truy vết và tái dựng trạng thái, nhưng không phải mọi hệ thống cần áp dụng event sourcing. Với event sourcing, sự kiện là nguồn dữ liệu chính để tái dựng trạng thái hiện tại; điều này kéo theo yêu cầu về phiên bản sự kiện, thứ tự, xử lý sự kiện lặp, sửa sai và tạo ảnh chụp.

Nếu nghiệp vụ chỉ cần giữ vài thay đổi quan trọng, bảng lịch sử riêng hoặc nhật ký kiểm toán có thể đơn giản và phù hợp hơn. Chọn cách lưu dựa trên nhu cầu truy vấn và vận hành đã được xác nhận.

### 4.5. Xác định cách xử lý sửa sai và xóa

Lịch sử có thể chứa thông tin đã nhập sai hoặc dữ liệu cá nhân không còn được phép lưu. Cần xác định:

- Sửa sai bằng cách cập nhật bản ghi cũ, tạo phiên bản điều chỉnh hay ghi sự kiện đính chính?
- Có cần giữ dấu vết rằng dữ liệu từng sai không?
- Khi xóa dữ liệu cá nhân, có thể xóa trực tiếp, ẩn danh hay cần giữ một phần theo nghĩa vụ nghiệp vụ hoặc pháp lý?
- Dữ liệu trong bản sao lưu, chỉ mục tìm kiếm, kho phân tích và nhật ký được xử lý theo thời hạn nào?

Không nên mặc định nhật ký bất biến đồng nghĩa với việc có thể giữ mọi dữ liệu vô thời hạn. Thiết kế cần phối hợp giữa yêu cầu kiểm toán, quyền riêng tư, thời hạn lưu giữ và cơ chế xóa hoặc ẩn danh đã được tổ chức phê duyệt.

## 5. Thiết kế khả năng truy vết

### 5.1. Xác định sự kiện nào cần ghi nhận

Không nhất thiết ghi mọi lần đọc hoặc mọi thay đổi nhỏ vào cùng một bảng nhật ký. Hãy xác định các hành động quan trọng theo rủi ro và nhu cầu nghiệp vụ:

- Tạo, sửa, duyệt, từ chối, hủy hoặc hoàn tất giao dịch.
- Thay đổi quyền, vai trò, cấu hình hoặc chính sách.
- Xuất dữ liệu hoặc truy cập dữ liệu nhạy cảm.
- Đồng bộ dữ liệu từ đối tác hoặc hệ thống bên ngoài.
- Tác vụ tự động sửa trạng thái hoặc thực hiện đối soát.

Với mỗi loại sự kiện, cần biết ai chịu trách nhiệm tạo sự kiện, thông tin nào phải được lưu và ai được phép đọc nhật ký.

### 5.2. Chọn thông tin truy vết

Một bản ghi kiểm toán có thể bao gồm:

| Trường | Ý nghĩa |
|---|---|
| event_id | Định danh duy nhất của sự kiện |
| entity_type, entity_id | Loại đối tượng và đối tượng bị tác động |
| action | Hành động đã xảy ra |
| actor_type, actor_id | Người dùng, dịch vụ hoặc tiến trình thực hiện |
| occurred_at | Thời điểm hành động xảy ra theo ngữ cảnh nguồn |
| recorded_at | Thời điểm hệ thống ghi nhận sự kiện |
| source | Giao diện, API, tác vụ nền hoặc hệ thống tích hợp |
| correlation_id | Mã liên kết các bước thuộc cùng một yêu cầu hoặc quy trình |
| reason | Lý do nghiệp vụ, nếu cần |
| changed_fields | Các trường đã thay đổi, nếu cần |
| before/after | Giá trị trước và sau, chỉ lưu khi có căn cứ và được phép |

Không phải sự kiện nào cũng cần lưu toàn bộ before/after. Những giá trị như mật khẩu, token, khóa bí mật, thông tin xác thực hoặc dữ liệu thanh toán nhạy cảm không được đưa nguyên dạng vào nhật ký. Với dữ liệu cá nhân, cần đánh giá liệu việc sao chép giá trị vào nhật ký có tạo thêm một nơi lưu giữ ngoài chính sách hay không.

### 5.3. Bảo đảm nhật ký hữu ích và đáng tin cậy

Nhật ký chỉ hữu ích nếu được ghi đúng thời điểm, liên kết được với đối tượng và không dễ bị sửa trái phép. Tùy mức độ rủi ro, có thể cần:

- Chỉ cho phép ứng dụng ghi thêm; giới hạn quyền sửa hoặc xóa nhật ký.
- Lưu nhật ký ở kho hoặc miền quyền truy cập tách biệt với dữ liệu nghiệp vụ.
- Đồng bộ thời gian và quy định múi giờ thống nhất.
- Dùng mã tương quan để nối sự kiện qua nhiều dịch vụ.
- Có cơ chế phát hiện sự kiện bị thiếu, trùng hoặc đến sai thứ tự.
- Bảo vệ bản sao nhật ký và quy định thời hạn lưu giữ.
- Cân nhắc chữ ký, chuỗi băm hoặc kho lưu trữ chống sửa đổi khi mức rủi ro yêu cầu.

Nếu một thay đổi dữ liệu đã commit nhưng việc ghi nhật ký thất bại, hệ thống có thể mất dấu vết quan trọng. Nếu ghi nhật ký trước rồi thay đổi dữ liệu thất bại, nhật ký có thể mô tả một hành động chưa thực sự xảy ra. Đây là lý do cần xác định rõ quan hệ giao dịch giữa dữ liệu và sự kiện, ví dụ ghi dữ liệu cùng bản ghi outbox trong một giao dịch rồi phát sự kiện sau khi commit.

## 6. Đưa bảo vệ dữ liệu vào mô hình

### 6.1. Phân loại và giảm thiểu dữ liệu

Trước tiên, xác định dữ liệu nào thực sự cần thu thập. Mỗi thuộc tính nên có mục đích nghiệp vụ, chủ thể sở hữu, mức độ nhạy cảm và thời hạn lưu giữ dự kiến.

Không thu thập một thuộc tính chỉ vì có thể sẽ hữu ích. Dữ liệu dư thừa làm tăng chi phí lưu trữ, mở rộng bề mặt rủi ro và khiến việc đáp ứng yêu cầu xóa hoặc sửa dữ liệu khó hơn.

Có thể phân loại dữ liệu theo chính sách của tổ chức, chẳng hạn:

- Công khai: có thể công bố cho mọi người.
- Nội bộ: chỉ dành cho người trong tổ chức.
- Nhạy cảm: cần giới hạn theo vai trò hoặc mục đích.
- Hạn chế cao: cần kiểm soát truy cập chặt, giám sát và biện pháp bảo vệ bổ sung.

Tên phân loại và quy tắc cụ thể phải theo chính sách tổ chức; bảng trên chỉ là cách minh họa để bắt đầu khảo sát.

### 6.2. Mô hình quyền truy cập

Hãy xác định quyền theo hành động và phạm vi dữ liệu. Quyền đọc không tự động bao gồm quyền sửa, xuất hoặc xóa.

Ví dụ, trong hệ thống bán hàng:

- Khách hàng xem được hồ sơ và đơn hàng của chính mình.
- Nhân viên hỗ trợ xem được thông tin cần thiết để xử lý yêu cầu thuộc phạm vi phụ trách.
- Nhân viên kho xem được dòng hàng và địa chỉ giao hàng cần thiết, nhưng không cần xem thông tin thanh toán đầy đủ.
- Quản trị viên được cấp quyền theo nhiệm vụ và các hành động nhạy cảm có thể cần ghi nhật ký.

Nếu hệ thống phục vụ nhiều tổ chức hoặc khách hàng doanh nghiệp, cần làm rõ ranh giới tenant. Mọi truy vấn, khóa tham chiếu, tác vụ nền và luồng xuất dữ liệu phải duy trì đúng phạm vi đó. Chỉ thêm tenant_id vào bảng mà không kiểm tra đường truy cập không đủ để bảo đảm cách ly dữ liệu.

### 6.3. Bảo vệ dữ liệu khi lưu và sử dụng

Các biện pháp có thể bao gồm:

- Mã hóa khi truyền và khi lưu theo tiêu chuẩn của tổ chức.
- Quản lý khóa tách khỏi dữ liệu được mã hóa; quy định luân chuyển và thu hồi khóa.
- Che hoặc giả danh dữ liệu trong môi trường phát triển, kiểm thử và phân tích.
- Hạn chế trường dữ liệu trả về từ API theo quyền và mục đích sử dụng.
- Giới hạn quyền truy cập trực tiếp vào cơ sở dữ liệu.
- Ghi nhận các hành động xem hoặc xuất dữ liệu có rủi ro cao.
- Không lưu bí mật xác thực hoặc thông tin thanh toán đầy đủ nếu hệ thống không có nhu cầu và cơ sở được phép.

Mô hình dữ liệu có thể hỗ trợ các biện pháp này bằng cách tách miền dữ liệu nhạy cảm, định danh rõ chủ thể, phân tách dữ liệu theo tenant hoặc lưu tham chiếu đến hệ thống chuyên trách. Việc tách bảng tự nó không tạo ra bảo mật; quyền truy cập, khóa mã hóa, API và quy trình vận hành vẫn phải được thiết kế tương ứng.

### 6.4. Vòng đời, lưu giữ và xóa

Mỗi loại dữ liệu cần có quy tắc vòng đời:

1. Thu thập khi có mục đích hợp lệ.
2. Sử dụng trong phạm vi mục đích và quyền đã xác định.
3. Lưu giữ trong thời hạn được phê duyệt.
4. Xóa, ẩn danh hoặc lưu trữ hạn chế khi hết thời hạn.
5. Xử lý các bản sao, bản sao lưu và dữ liệu dẫn xuất theo chính sách.

Cần khảo sát riêng dữ liệu trong bảng chính, bảng lịch sử, nhật ký, chỉ mục tìm kiếm, kho phân tích, hàng đợi thông điệp và bản sao lưu. Xóa một bản ghi ở bảng chính không có nghĩa mọi bản sao đã biến mất. Ngược lại, một số dữ liệu giao dịch có thể phải được giữ theo nghĩa vụ đã xác định; khi đó cần phân biệt phần dữ liệu phải giữ với phần thông tin cá nhân có thể giảm thiểu hoặc ẩn danh.

## 7. Xem xét sự giao nhau giữa các yêu cầu

Bốn nhóm yêu cầu không thể luôn tối ưu độc lập. Khi phân tích, cần chỉ ra các xung đột và quyết định nghiệp vụ liên quan.

| Tình huống | Các yêu cầu liên quan | Câu hỏi cần giải quyết |
|---|---|---|
| Nhật ký lưu giá trị trước và sau | Truy vết, bảo vệ, lịch sử | Giá trị nào được phép sao chép? Khi nào cần ẩn danh hoặc xóa? |
| Cập nhật tồn kho qua nhiều dịch vụ | Nhất quán, truy vết | Trạng thái trung gian nào được chấp nhận? Làm sao đối soát và chống xử lý trùng? |
| Sửa thông tin có hiệu lực từ quá khứ | Lịch sử, nhất quán, truy vết | Có lưu cả thời gian hiệu lực và thời gian ghi nhận không? Ai phê duyệt điều chỉnh? |
| Xóa hồ sơ khách hàng | Bảo vệ, lịch sử, truy vết | Phần nào phải xóa, phần nào được giữ, và cách xử lý bản sao là gì? |
| Báo cáo đã chốt theo kỳ | Nhất quán, lịch sử | Báo cáo phản ánh dữ liệu tại thời điểm nào? Có cần tái lập kết quả không? |

Một yêu cầu có thể tạo ra đánh đổi. Ví dụ, lưu toàn bộ giá trị cũ giúp điều tra nhưng cũng tạo thêm dữ liệu nhạy cảm. Ghi nhận mọi lần đọc giúp kiểm toán nhưng có thể tạo lượng nhật ký lớn và chứa thông tin truy cập. Cần xác định mức độ cần thiết, thời hạn và quyền truy cập trước khi chọn giải pháp.

## 8. Ví dụ xuyên suốt: mô hình dữ liệu cho đơn hàng

Giả sử một cửa hàng trực tuyến cần xử lý đơn hàng, tồn kho, thanh toán và yêu cầu hỗ trợ sau bán hàng.

### 8.1. Ghi nhận yêu cầu

**Nhất quán**

- Một đơn hàng chỉ được chuyển sang trạng thái đã thanh toán sau khi có xác nhận thanh toán hợp lệ.
- Hai khách hàng không thể cùng giữ chỗ thành công cho đơn vị tồn kho cuối cùng.
- Việc nhận lại cùng một thông báo thanh toán không được ghi nhận thành hai lần thu tiền.
- Tổng tiền đơn hàng phải giữ đúng giá và chính sách đã áp dụng khi đặt hàng.

**Lịch sử**

- Đơn hàng giữ thông tin sản phẩm, đơn giá, số lượng, giảm giá và địa chỉ giao hàng tại thời điểm đặt.
- Mỗi lần chuyển trạng thái đơn hàng phải có thể xem lại.
- Khi giá sản phẩm thay đổi, đơn hàng cũ vẫn hiển thị đúng giá đã chốt.
- Nhân viên hỗ trợ có thể tra cứu các lần điều chỉnh quan trọng.

**Truy vết**

- Thay đổi trạng thái thủ công phải ghi nhận nhân viên thực hiện và lý do.
- Xác nhận thanh toán phải liên kết được với mã giao dịch từ nhà cung cấp.
- Các bước tạo đơn, giữ chỗ, thanh toán và giao hàng cần có mã tương quan để điều tra.

**Bảo vệ**

- Khách hàng chỉ xem đơn hàng của mình.
- Nhân viên kho chỉ xem thông tin cần cho việc chuẩn bị giao hàng.
- Thông tin thanh toán nhạy cảm không được sao chép vào nhật ký.
- Dữ liệu cá nhân có thời hạn lưu giữ và quy tắc xử lý đã được phê duyệt.

### 8.2. Suy ra cấu trúc dữ liệu

Một mô hình quan hệ có thể gồm các nhóm dữ liệu sau:

| Bảng/nhóm | Dữ liệu chính | Mục đích |
|---|---|---|
| orders | order_id, customer_id, status, currency, total_amount, created_at | Trạng thái và tổng tiền hiện tại của đơn |
| order_items | order_id, product_id, product_name_snapshot, unit_price, quantity | Giữ dữ kiện mặt hàng và giá tại thời điểm đặt |
| inventory | product_id, quantity_on_hand, reserved_quantity, version | Quản lý tồn kho và phát hiện cập nhật cạnh tranh |
| payments | payment_id, order_id, provider_reference, amount, status | Theo dõi giao dịch thanh toán |
| order_status_history | order_id, old_status, new_status, actor_id, reason, occurred_at | Lưu lịch sử chuyển trạng thái |
| audit_events | event_id, entity_type, entity_id, action, actor, source, correlation_id, recorded_at | Điều tra thay đổi quan trọng |
| outbox_events | event_id, aggregate_id, event_type, payload_reference, created_at, published_at | Phát sự kiện sau khi thay đổi dữ liệu được commit |

Đây là mô hình minh họa. Khi thiết kế thật, cần xác định khóa chính, khóa ngoại, chỉ mục, kiểu dữ liệu, ràng buộc duy nhất, chính sách lưu trữ và quyền truy cập. Không nên lưu payload nhạy cảm trong outbox hoặc audit_events nếu không cần thiết.

### 8.3. Theo dõi một tình huống

Một khách hàng đặt sản phẩm cuối cùng còn hàng:

1. Hệ thống kiểm tra và giữ chỗ tồn kho bằng một thao tác có kiểm soát cạnh tranh.
2. Đơn hàng được tạo với ảnh chụp tên sản phẩm, giá, số lượng và địa chỉ giao hàng.
3. Sự kiện tạo đơn được ghi cùng giao dịch hoặc qua cơ chế bảo đảm phát sự kiện.
4. Nhà cung cấp thanh toán gửi thông báo. Hệ thống kiểm tra mã giao dịch để chống xử lý lặp.
5. Khi xác nhận hợp lệ, trạng thái thanh toán và trạng thái đơn được cập nhật theo quy tắc đã thống nhất.
6. Sự kiện chuyển trạng thái lưu tác nhân là nhà cung cấp hoặc dịch vụ xử lý, thời điểm và mã tương quan.
7. Nếu thông báo đến trễ hoặc được gửi lại, hệ thống vẫn có thể đối soát mà không ghi nhận thanh toán hai lần.

Khi khách hàng đổi địa chỉ sau khi đặt đơn, đơn cũ tiếp tục giữ địa chỉ đã chốt. Hồ sơ khách hàng có thể cập nhật địa chỉ hiện tại; nếu nghiệp vụ cần lịch sử địa chỉ, các phiên bản được quản lý riêng. Nhân viên hỗ trợ tra cứu lịch sử đơn hàng theo quyền được cấp và mọi thay đổi thủ công quan trọng đều có dấu vết.

Ví dụ này cho thấy yêu cầu về nhất quán, lịch sử, truy vết và bảo vệ cần được xác định trước để chọn cấu trúc dữ liệu và ranh giới xử lý phù hợp.

## 9. Viết tiêu chí chấp nhận và kiểm chứng mô hình

Một mô hình chỉ được xem là đáp ứng yêu cầu khi có cách kiểm chứng. Có thể chuyển yêu cầu thành các kịch bản:

**Kịch bản cạnh tranh tồn kho**

- Given: sản phẩm chỉ còn một đơn vị có thể bán.
- When: hai yêu cầu giữ chỗ được xử lý đồng thời.
- Then: tối đa một yêu cầu thành công và số lượng tồn kho không trở thành giá trị âm.

**Kịch bản giữ giá tại thời điểm đặt hàng**

- Given: đơn hàng được tạo khi sản phẩm có giá A.
- When: giá sản phẩm hiện tại được đổi thành B.
- Then: đơn hàng cũ vẫn hiển thị giá A và tổng tiền đã chốt.

**Kịch bản truy vết thay đổi**

- Given: nhân viên có quyền điều chỉnh trạng thái đơn hàng.
- When: nhân viên chuyển trạng thái và nhập lý do.
- Then: hệ thống lưu trạng thái trước, trạng thái sau, tác nhân, thời điểm, lý do và mã liên kết cần thiết.

**Kịch bản giới hạn truy cập**

- Given: nhân viên hỗ trợ được phân công cho một nhóm đơn hàng.
- When: nhân viên truy cập đơn hàng ngoài phạm vi.
- Then: hệ thống từ chối truy cập và ghi nhận sự kiện bảo mật theo chính sách.

**Kịch bản xử lý hết hạn lưu giữ**

- Given: dữ liệu đã đến hạn xử lý theo chính sách được phê duyệt.
- When: quy trình lưu giữ chạy.
- Then: dữ liệu và các bản sao thuộc phạm vi chính sách được xóa hoặc ẩn danh; kết quả xử lý có thể kiểm chứng mà không làm lộ dữ liệu đã xử lý.

Khi kiểm chứng mô hình, hãy xem xét cả dữ liệu hợp lệ, dữ liệu biên, thao tác đồng thời, lỗi tích hợp, gửi lại thông điệp, thay đổi chính sách và khôi phục sau sự cố. Với dữ liệu lịch sử, cần thử truy vấn tại một thời điểm cụ thể và kiểm tra trường hợp dữ liệu được nhập muộn hoặc đính chính. Với truy vết, cần thử cả trường hợp ghi nhật ký thất bại và quyền đọc nhật ký. Với bảo vệ, cần thử truy cập trực tiếp qua API, tác vụ nền và luồng xuất dữ liệu.

## 10. Lỗi thường gặp khi phân tích

- **Chỉ yêu cầu “dữ liệu nhất quán”:** không chỉ rõ bất biến, phạm vi giao dịch, nơi đọc và độ trễ chấp nhận được.
- **Chỉ lưu updated_at:** không đủ để biết ai thay đổi, thay đổi gì và lý do nào.
- **Giữ mọi phiên bản vô thời hạn:** làm tăng rủi ro riêng tư, chi phí và độ phức tạp quản trị.
- **Đồng nhất audit log với event sourcing:** hai cách có mục đích và hệ quả vận hành khác nhau.
- **Ghi toàn bộ dữ liệu vào nhật ký:** có thể làm lộ bí mật và tạo bản sao dữ liệu cá nhân ngoài chính sách.
- **Chỉ phân quyền ở giao diện:** API, truy vấn nền, báo cáo và luồng xuất vẫn có thể truy cập sai phạm vi.
- **Chỉ xóa bản ghi chính:** bỏ sót lịch sử, bản sao, chỉ mục, thông điệp hoặc dữ liệu dẫn xuất.
- **Dùng một chính sách cho mọi loại dữ liệu:** dữ liệu giao dịch, dữ liệu cá nhân, nhật ký và dữ liệu phân tích có nhu cầu lưu giữ khác nhau.
- **Chọn công nghệ trước khi hiểu yêu cầu:** dẫn đến mô hình khó kiểm chứng hoặc phải bổ sung nhiều cơ chế phức tạp sau này.

## 11. Danh sách kiểm tra khi hoàn tất phân tích

Trước khi chuyển sang thiết kế chi tiết, hãy xác nhận:

- [ ] Các bất biến nghiệp vụ đã được diễn đạt rõ và có cách kiểm tra.
- [ ] Đã xác định thao tác nào cần nguyên tử và ranh giới dữ liệu của thao tác đó.
- [ ] Đã phân loại luồng đọc theo yêu cầu trạng thái mới nhất, thứ tự và độ trễ chấp nhận được.
- [ ] Đã xác định dữ liệu nào cần giữ lịch sử, câu hỏi lịch sử cần trả lời và thời hạn lưu.
- [ ] Đã phân biệt thời gian hiệu lực với thời gian hệ thống ghi nhận khi nghiệp vụ cần cả hai.
- [ ] Đã xác định sự kiện nào cần truy vết, tác nhân, nguồn, lý do và mã liên kết.
- [ ] Đã quy định ai được đọc, tạo, sửa, xuất và xóa từng nhóm dữ liệu.
- [ ] Đã phân loại dữ liệu nhạy cảm và xác định biện pháp bảo vệ tương ứng.
- [ ] Đã làm rõ vòng đời dữ liệu, bao gồm lịch sử, nhật ký, bản sao và dữ liệu dẫn xuất.
- [ ] Các tiêu chí chấp nhận có thể kiểm thử bằng tình huống cụ thể.
- [ ] Các đánh đổi giữa nhất quán, lịch sử, truy vết và bảo vệ đã được người có thẩm quyền nghiệp vụ xác nhận.

Kết quả của bước phân tích là một tập hợp yêu cầu có thể truy nguyên tới quy tắc nghiệp vụ và có tiêu chí xác minh. Tập hợp này tạo cơ sở để quyết định thực thể, thuộc tính, quan hệ, ràng buộc, cách lưu lịch sử, cơ chế truy vết và chính sách bảo vệ trong các bước mô hình hóa tiếp theo.

