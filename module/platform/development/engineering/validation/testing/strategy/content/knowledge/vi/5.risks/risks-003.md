# Đánh giá khả năng xảy ra và mức tác động theo thang phù hợp

Chiến lược kiểm thử xác thực cần tập trung vào những điều có thể làm sản phẩm không đạt mục tiêu, gây tổn hại cho người dùng hoặc tạo ra hậu quả không thể chấp nhận. Để lựa chọn phạm vi kiểm thử hợp lý, nhóm phải đánh giá được hai yếu tố cốt lõi của từng rủi ro: **khả năng xảy ra** và **mức tác động nếu rủi ro xảy ra**. Việc dùng thang đo rõ ràng giúp các thành viên cùng hiểu một mức “cao” hay “thấp”, so sánh các rủi ro và quyết định cần kiểm chứng hoặc xử lý điều gì trước.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, đánh giá rủi ro là đầu vào để xác định giả thuyết cần kiểm tra, hành trình cần ưu tiên, độ sâu kiểm thử và bằng chứng cần thu thập. Một điểm số không tự chứng minh sản phẩm an toàn hay sẵn sàng phát hành. Giá trị của đánh giá nằm ở lập luận, dữ liệu hỗ trợ, người chịu trách nhiệm và quyết định được đưa ra từ kết quả đó.

## 1. Hiểu rủi ro và mục đích đánh giá

### Rủi ro là điều chưa chắc chắn có thể ảnh hưởng đến mục tiêu

Rủi ro là một sự kiện hoặc điều kiện chưa chắc chắn mà nếu xảy ra có thể ảnh hưởng tích cực hoặc tiêu cực đến mục tiêu. Trong đánh giá rủi ro sản phẩm và kiểm thử xác thực, nhóm thường tập trung trước hết vào các khả năng gây hại: người dùng không hoàn thành được công việc, dữ liệu bị sai hoặc mất, hệ thống ngừng hoạt động, chi phí tăng, hoặc tổ chức không đáp ứng nghĩa vụ của mình.

Cần phân biệt:

- **Rủi ro:** điều có thể xảy ra trong tương lai, chưa chắc chắn, ví dụ dịch vụ xác minh danh tính có thể phản hồi chậm khiến người dùng không hoàn tất đăng ký.
- **Vấn đề hoặc sự cố:** điều đã xảy ra, ví dụ dịch vụ xác minh đang trả lỗi và người dùng hiện không thể đăng ký.
- **Nguyên nhân:** điều kiện có thể dẫn đến sự kiện, ví dụ giới hạn tần suất của nhà cung cấp thấp hơn lưu lượng dự kiến.
- **Tác động:** hậu quả nếu sự kiện xảy ra, ví dụ tỷ lệ đăng ký hoàn tất giảm và bộ phận hỗ trợ nhận thêm yêu cầu.

Một vấn đề đang tồn tại vẫn có thể tạo ra rủi ro tiếp theo. Chẳng hạn, sự cố đồng bộ dữ liệu hiện tại có thể dẫn đến nguy cơ báo cáo sai trong kỳ tiếp theo. Nhóm cần ghi nhận trạng thái hiện tại và đánh giá phần bất định còn lại.

### Vì sao phải đánh giá cả khả năng xảy ra và tác động

Chỉ nhìn vào khả năng xảy ra có thể khiến nhóm bỏ qua một sự kiện hiếm nhưng gây hậu quả nghiêm trọng. Chỉ nhìn vào tác động có thể khiến mọi rủi ro đều bị xếp ở mức cao vì nhiều sự kiện, nếu xảy ra, đều có hậu quả đáng kể. Đánh giá cả hai chiều giúp phân biệt:

- Sự kiện thường xảy ra nhưng hậu quả nhỏ, có thể xử lý bằng cải tiến thông thường.
- Sự kiện ít xảy ra nhưng có hậu quả rất lớn, cần biện pháp phòng ngừa và kiểm chứng nghiêm ngặt.
- Sự kiện vừa dễ xảy ra vừa gây tác động lớn, thường cần ưu tiên xử lý ngay.
- Sự kiện ít khả năng và tác động thấp, có thể theo dõi theo chu kỳ phù hợp.

Mục tiêu không phải là tạo ra một bảng điểm đẹp. Mục tiêu là dùng một cách đánh giá nhất quán để quyết định rủi ro nào cần giảm, rủi ro nào cần kiểm thử sâu, rủi ro nào cần theo dõi và ai có thẩm quyền chấp nhận phần rủi ro còn lại.

## 2. Mô tả rủi ro đủ rõ trước khi chấm điểm

### Viết rủi ro theo nguyên nhân, sự kiện và hậu quả

Một câu mô tả rủi ro tốt cần cho người đọc biết điều gì có thể xảy ra, vì sao có thể xảy ra và điều đó ảnh hưởng đến mục tiêu nào. Có thể dùng cấu trúc:

> Do [nguyên nhân hoặc điều kiện], [sự kiện không chắc chắn] có thể xảy ra, dẫn đến [hậu quả đối với người dùng, sản phẩm hoặc doanh nghiệp].

Ví dụ:

> Do nhà cung cấp gửi webhook thanh toán nhiều lần khi không nhận được xác nhận, cùng một giao dịch có thể được xử lý lặp, dẫn đến trạng thái thuê bao hoặc số tiền ghi nhận không chính xác.

Câu này cụ thể hơn “rủi ro thanh toán” vì nó chỉ ra điều kiện, sự kiện và hậu quả có thể kiểm chứng. Từ mô tả đó, nhóm có thể xác định kịch bản kiểm thử: gửi webhook trùng, mất phản hồi xác nhận, khởi động lại bộ xử lý và đối chiếu trạng thái cuối.

Một số ví dụ khác:

- Do hướng dẫn thiết lập không giải thích quyền truy cập, quản trị viên có thể cấp quyền quá rộng, dẫn đến người không phù hợp xem được dữ liệu của nhóm.
- Do ứng dụng không kiểm tra kết quả sau timeout, người dùng có thể gửi lại thao tác tạo đơn hàng, dẫn đến đơn hàng trùng.
- Do dữ liệu kiểm thử không đại diện cho người dùng có mạng yếu, nhóm có thể bỏ sót lỗi đồng bộ và đánh giá quá cao tỷ lệ hoàn thành thực tế.

### Xác định mục tiêu và phạm vi bị ảnh hưởng

Mỗi rủi ro phải gắn với một mục tiêu hoặc kết quả có ý nghĩa. Mục tiêu có thể thuộc các nhóm:

- **Người dùng:** hoàn thành công việc, hiểu trạng thái, tiếp cận chức năng, bảo vệ dữ liệu cá nhân.
- **Sản phẩm và kỹ thuật:** tính đúng đắn, độ sẵn sàng, hiệu năng, khả năng phục hồi, tương thích.
- **Kinh doanh:** doanh thu, chuyển đổi, giữ chân khách hàng, chi phí vận hành và uy tín.
- **Tổ chức:** an toàn, bảo mật, quyền riêng tư, tuân thủ và nghĩa vụ hợp đồng.

Ghi rõ phạm vi ảnh hưởng: một người dùng, một nhóm khách hàng, một khu vực, một loại thiết bị, một luồng nghiệp vụ hay toàn bộ hệ thống. Cùng một lỗi kỹ thuật có thể có mức tác động khác nhau tùy hành trình và nhóm người dùng liên quan.

### Tránh gộp nhiều rủi ro vào một mục

“Đăng ký có thể lỗi” có thể bao gồm nhiều sự kiện: xác minh danh tính thất bại, email không đến, dữ liệu bị trùng, quyền được cấp sai hoặc dịch vụ bên ngoài ngừng hoạt động. Những sự kiện này có nguyên nhân, xác suất, hậu quả và cách kiểm thử khác nhau.

Hãy tách rủi ro khi chúng cần biện pháp xử lý hoặc quyết định khác nhau. Có thể nhóm chúng dưới một chủ đề chung, nhưng từng mục cần đủ cụ thể để gán người phụ trách và theo dõi.

## 3. Chọn thang đo khả năng xảy ra

### Xác định khoảng thời gian đánh giá

Khả năng xảy ra phải gắn với một khoảng thời gian hoặc số lần phơi nhiễm cụ thể. “Có khả năng xảy ra” trong một ngày có thể khác hoàn toàn so với trong một năm. Ví dụ, một lỗi có xác suất nhỏ trên mỗi giao dịch vẫn có thể xuất hiện thường xuyên nếu hệ thống xử lý hàng triệu giao dịch.

Trước khi chấm điểm, thống nhất:

- Khoảng thời gian: trong một lần thử nghiệm, một chu kỳ phát hành, một tháng vận hành hay một năm.
- Đơn vị phơi nhiễm: mỗi giao dịch, mỗi phiên, mỗi tài khoản, mỗi lần tích hợp hoặc mỗi lần triển khai.
- Điều kiện giả định: lưu lượng, cấu hình, phiên bản, nhóm người dùng và môi trường.
- Bằng chứng: lịch sử sự cố, dữ liệu phân tích, kết quả thử nghiệm, báo cáo nhà cung cấp hoặc nhận định chuyên gia.

Nếu không xác định được thời gian và điều kiện, điểm khả năng xảy ra giữa các rủi ro có thể không so sánh được.

### Thang định tính năm mức

Khi dữ liệu xác suất chưa đủ, thang định tính có thể giúp nhóm đánh giá nhất quán. Ví dụ:

| Điểm | Mức | Hướng dẫn diễn giải |
|---|---|---|
| 1 | Hiếm | Chỉ có thể xảy ra trong điều kiện ngoại lệ; chưa có dấu hiệu đáng kể trong bối cảnh tương tự |
| 2 | Khó xảy ra | Có thể xảy ra nhưng không được kỳ vọng trong điều kiện vận hành thông thường |
| 3 | Có thể | Có cơ sở để tin sự kiện có thể xuất hiện trong một số điều kiện thực tế |
| 4 | Dễ xảy ra | Đã có dấu hiệu hoặc sự kiện tương tự thường xuất hiện trong điều kiện dự kiến |
| 5 | Gần như chắc chắn | Sự kiện được kỳ vọng lặp lại hoặc đã xảy ra thường xuyên trong cùng điều kiện |

Đây là thang mẫu. Nhóm cần thay các mô tả chung bằng ví dụ phù hợp với sản phẩm, lịch sử và tần suất sử dụng. “Hiếm” không có nghĩa là không thể xảy ra; “gần như chắc chắn” cũng không có nghĩa sự kiện sẽ xảy ra trong mọi lần.

### Thang định lượng khi có dữ liệu

Nếu có dữ liệu đủ tin cậy, nhóm có thể dùng các khoảng xác suất trong một khoảng thời gian đã thống nhất. Ví dụ minh họa:

| Điểm | Xác suất ước tính trong khoảng thời gian đã chọn |
|---|---|
| 1 | Không quá 5% |
| 2 | Trên 5% đến 20% |
| 3 | Trên 20% đến 50% |
| 4 | Trên 50% đến 80% |
| 5 | Trên 80% |

Các ngưỡng này không phải chuẩn chung. Một tổ chức có thể cần khoảng khác, đặc biệt khi sự kiện rất hiếm nhưng có hậu quả nghiêm trọng hoặc khi số lần phơi nhiễm rất lớn. Không nên gán xác suất phần trăm chỉ để tạo cảm giác chính xác nếu không có dữ liệu hoặc phương pháp ước lượng đáng tin cậy.

### Nguồn bằng chứng để ước lượng khả năng xảy ra

Có thể dùng nhiều nguồn để hình thành nhận định:

- Lịch sử lỗi, sự cố, yêu cầu hỗ trợ và khiếu nại.
- Tỷ lệ thất bại theo giao dịch, thiết bị, phiên bản hoặc nhóm người dùng.
- Kết quả kiểm thử trước đó, thử nghiệm thực địa và thử nghiệm tải.
- Tần suất thay đổi API, cấu hình, dữ liệu hoặc dịch vụ phụ thuộc.
- Mức độ phức tạp của luồng, số bước chuyển giao và số thành phần liên quan.
- Ý kiến của người vận hành, chuyên gia miền nghiệp vụ và chủ sở hữu dịch vụ.

Cần phân biệt “chưa từng thấy” với “không thể xảy ra”. Nếu hệ thống chưa có log hoặc chưa từng được thử trong điều kiện tương ứng, việc thiếu sự cố không phải bằng chứng mạnh cho khả năng thấp. Hãy ghi nhận mức độ tin cậy của ước lượng và khoảng trống dữ liệu.

## 4. Chọn thang đo mức tác động

### Xác định tác động trên nhiều chiều

Mức tác động không chỉ là thời gian hệ thống ngừng hoạt động. Một sự kiện có thể gây thiệt hại nhỏ về kỹ thuật nhưng ảnh hưởng lớn đến người dùng hoặc nghĩa vụ của tổ chức. Tùy sản phẩm, hãy xem xét:

- **Người dùng và trải nghiệm:** không thể hoàn thành công việc, mất dữ liệu, bị khóa tài khoản, nhầm lẫn trạng thái hoặc mất khả năng tiếp cận.
- **Tài chính và kinh doanh:** thất thu, giao dịch sai, hoàn tiền, chi phí hỗ trợ, mất khách hàng hoặc gián đoạn doanh thu.
- **Vận hành:** thời gian gián đoạn, số nhóm phải xử lý thủ công, công sức khôi phục và tồn đọng công việc.
- **Bảo mật và quyền riêng tư:** truy cập trái phép, tiết lộ, sửa đổi hoặc mất dữ liệu nhạy cảm.
- **Pháp lý và tuân thủ:** vi phạm nghĩa vụ, thời hạn thông báo, điều khoản hợp đồng hoặc yêu cầu quản lý.
- **An toàn:** khả năng gây hại cho con người hoặc môi trường trong sản phẩm có liên quan.
- **Uy tín và niềm tin:** mất niềm tin, phản hồi tiêu cực hoặc ảnh hưởng đến quan hệ khách hàng.

Không phải sản phẩm nào cũng cần mọi chiều. Chọn những chiều liên quan đến mục tiêu, đối tượng sử dụng và nghĩa vụ thực tế. Với rủi ro bảo mật, an toàn hoặc tuân thủ, cần dùng tiêu chí chuyên môn phù hợp và không để một điểm tổng hợp thấp che khuất hậu quả nghiêm trọng ở một chiều.

### Thang tác động định tính năm mức

Ví dụ dưới đây dùng cho một sản phẩm phần mềm dịch vụ. Tổ chức cần điều chỉnh ngưỡng theo quy mô, mức độ quan trọng và chính sách rủi ro của mình.

| Điểm | Mức | Ví dụ về hậu quả |
|---|---|---|
| 1 | Không đáng kể | Bất tiện nhỏ, có cách tự khắc phục rõ ràng; không mất dữ liệu; ảnh hưởng kinh doanh không đáng kể |
| 2 | Nhẹ | Một nhóm nhỏ gặp khó khăn tạm thời; có giải pháp thay thế; hỗ trợ xử lý trong hoạt động thông thường |
| 3 | Trung bình | Một chức năng quan trọng suy giảm; nhiều người dùng cần trợ giúp; có gián đoạn hoặc chi phí xử lý đáng kể |
| 4 | Nghiêm trọng | Hành trình cốt lõi bị chặn trên diện rộng; có nguy cơ mất dữ liệu, tổn thất tài chính hoặc ảnh hưởng uy tín lớn |
| 5 | Rất nghiêm trọng | Hậu quả nghiêm trọng về an toàn, bảo mật, quyền riêng tư, nghĩa vụ pháp lý hoặc hoạt động kinh doanh thiết yếu |

Bảng trên là mô tả tổng quát, chưa phải ngưỡng vận hành có thể áp dụng nguyên trạng. Hãy bổ sung tiêu chí đo được khi có thể, ví dụ số lượng người dùng bị ảnh hưởng, thời gian gián đoạn, giá trị giao dịch, loại dữ liệu, thời gian khôi phục hoặc nghĩa vụ phải thông báo.

### Dùng mức tác động cao nhất hay đánh giá riêng từng chiều?

Có hai cách thường dùng:

1. **Lấy mức cao nhất trong các chiều liên quan:** phù hợp khi cần một mức tác động tổng quát để ưu tiên. Cách này tránh việc hậu quả nghiêm trọng ở một chiều bị trung bình hóa bởi các chiều còn lại.
2. **Giữ điểm riêng theo từng chiều:** phù hợp khi cần giải thích hậu quả, giao trách nhiệm cho chuyên gia hoặc theo dõi nhiều mục tiêu khác nhau.

Ví dụ, một lỗi có thể chỉ ảnh hưởng một số ít người dùng nhưng làm lộ dữ liệu cá nhân nhạy cảm. Số người bị ảnh hưởng thấp không đủ để kết luận tác động tổng thể thấp. Nhóm cần đánh giá riêng chiều quyền riêng tư và áp dụng tiêu chí chuyên môn tương ứng.

## 5. Kết hợp khả năng xảy ra và mức tác động

### Ma trận rủi ro năm nhân năm

Sau khi thống nhất thang đo, nhóm có thể kết hợp hai điểm để hỗ trợ ưu tiên. Một cách đơn giản là nhân điểm khả năng xảy ra với điểm tác động:

`Điểm rủi ro = Điểm khả năng xảy ra × Điểm tác động`

Ví dụ, khả năng xảy ra ở mức 4 và tác động ở mức 5 tạo điểm 20. Ma trận dưới đây minh họa cách đọc kết quả:

| Khả năng xảy ra \ Tác động | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| 5 – Gần như chắc chắn | 5 | 10 | 15 | 20 | 25 |
| 4 – Dễ xảy ra | 4 | 8 | 12 | 16 | 20 |
| 3 – Có thể | 3 | 6 | 9 | 12 | 15 |
| 2 – Khó xảy ra | 2 | 4 | 6 | 8 | 10 |
| 1 – Hiếm | 1 | 2 | 3 | 4 | 5 |

Một cách chia nhóm minh họa:

| Điểm tổng | Mức ưu tiên | Hành động gợi ý |
|---|---|---|
| 1–4 | Thấp | Ghi nhận và xem xét theo chu kỳ |
| 5–9 | Trung bình | Xác định biện pháp kiểm soát phù hợp và theo dõi |
| 10–16 | Cao | Lập kế hoạch giảm rủi ro, gán người phụ trách và kiểm chứng trước mốc quyết định |
| 17–25 | Rất cao | Ưu tiên xử lý; cần quyết định rõ của người có thẩm quyền trước khi tiếp tục hoặc phát hành |

Các ngưỡng này chỉ là ví dụ để minh họa. Nhóm cần hiệu chỉnh theo khẩu vị rủi ro, yêu cầu ngành, quy mô tác động và năng lực xử lý. Không nên lấy bảng mẫu làm chính sách chính thức nếu tổ chức chưa thống nhất.

### Điểm nhân là công cụ sắp xếp, không phải phép đo chính xác

Các mức 1 đến 5 thường là thang thứ bậc: chúng biểu thị mức thấp hơn hoặc cao hơn, nhưng khoảng cách giữa các mức không nhất thiết bằng nhau. Vì vậy, phép nhân tạo ra một chỉ số thuận tiện để sắp xếp, không phải xác suất thiệt hại thực tế hay giá trị tổn thất kỳ vọng.

Hai rủi ro có cùng điểm tổng vẫn có thể cần cách xử lý khác nhau. Ví dụ, khả năng 5 và tác động 2 có điểm 10; khả năng 2 và tác động 5 cũng có điểm 10. Trường hợp thứ hai có hậu quả nghiêm trọng hơn dù ít xảy ra, nên có thể cần biện pháp phòng ngừa, kiểm thử chuyên sâu và người phê duyệt khác.

Khi cần ước lượng thiệt hại tài chính và có dữ liệu đáng tin cậy, nhóm có thể sử dụng xác suất và mức tổn thất dự kiến theo mô hình phù hợp. Không trộn điểm định tính với giá trị tiền tệ hoặc xác suất chưa được kiểm chứng trong cùng một phép tính.

### Dùng quy tắc ưu tiên bổ sung

Ma trận không nên là cổng quyết định duy nhất. Có thể đặt quy tắc vượt mức để bảo đảm các rủi ro đặc biệt được xem xét đúng mức:

- Rủi ro có thể gây hại về an toàn, lộ dữ liệu nhạy cảm hoặc vi phạm nghĩa vụ phải được chuyển đến người có chuyên môn và thẩm quyền, kể cả khi điểm tổng thấp.
- Rủi ro trên hành trình cốt lõi có thể cần ưu tiên cao hơn rủi ro cùng điểm trên chức năng ít quan trọng.
- Rủi ro khó phát hiện hoặc khó phục hồi có thể cần thêm kiểm thử và giám sát.
- Rủi ro có bằng chứng yếu cần được ghi rõ độ bất định, tránh xem điểm số như kết luận chắc chắn.

## 6. Đánh giá độ tin cậy của nhận định

### Phân biệt điểm rủi ro và mức độ tin cậy

Điểm khả năng xảy ra và tác động mô tả đánh giá hiện tại. Mức độ tin cậy mô tả nhóm có bao nhiêu bằng chứng để đưa ra đánh giá đó. Hai khái niệm này khác nhau.

Ví dụ:

- Khả năng xảy ra được chấm 2 vì chưa thấy sự cố, nhưng dịch vụ mới chỉ được thử ở tải thấp. Độ tin cậy có thể thấp.
- Khả năng xảy ra được chấm 4 dựa trên số liệu sự cố lặp lại trong sáu tháng và nhiều môi trường. Độ tin cậy có thể cao hơn.
- Tác động được chấm 5 vì có thể liên quan đến dữ liệu nhạy cảm, dù chưa rõ số người bị ảnh hưởng. Cần chuyên gia bảo mật hoặc quyền riêng tư đánh giá thêm.

Có thể ghi độ tin cậy theo ba mức: cao, trung bình, thấp, kèm lý do và nguồn dữ liệu. Không nên tự động giảm điểm rủi ro chỉ vì độ tin cậy thấp. Khi thiếu bằng chứng, hành động phù hợp có thể là nghiên cứu thêm hoặc thử nghiệm có kiểm soát.

### Xử lý bất định và thiếu dữ liệu

Khi không có số liệu, hãy ghi nhận:

- Giả định đang dùng để chấm.
- Bằng chứng hiện có và ngày cập nhật.
- Điều chưa biết có thể làm thay đổi điểm.
- Người hoặc nhóm có thể cung cấp thông tin.
- Cách kiểm chứng nhanh nhất và thời hạn cần có kết quả.

Nếu khoảng đánh giá rộng, có thể ghi một khoảng thay vì một con số duy nhất. Ví dụ, khả năng xảy ra có thể nằm giữa mức 2 và 4 do chưa đủ dữ liệu về tải thực tế. Sau khi kiểm thử hoặc thu thập số liệu, nhóm cập nhật nhận định và lưu lại lý do thay đổi.

### Dùng dữ liệu lịch sử đúng cách

Dữ liệu lịch sử hữu ích nhưng cần xem xét tính đại diện. Một hệ thống vừa thay đổi kiến trúc, lượng người dùng, nhà cung cấp hoặc quy trình vận hành có thể không còn giống giai đoạn trước. Hãy kiểm tra:

- Cùng loại sự kiện và định nghĩa lỗi hay chưa.
- Cùng môi trường, phiên bản và điều kiện sử dụng hay chưa.
- Số lần phơi nhiễm có đủ lớn không.
- Có thay đổi làm dữ liệu cũ không còn đại diện không.
- Sự cố đã được khắc phục hay nguyên nhân vẫn còn.

Không có sự cố được ghi nhận không đồng nghĩa không có sự cố xảy ra. Thiếu quan sát, thiếu báo cáo hoặc thiếu log có thể làm tỷ lệ lịch sử thấp giả tạo.

## 7. Ưu tiên rủi ro trong chiến lược kiểm thử xác thực

### Nối rủi ro với câu hỏi và bằng chứng cần thu thập

Sau khi đánh giá, mỗi rủi ro quan trọng cần được chuyển thành câu hỏi có thể kiểm chứng. Ví dụ:

| Rủi ro | Câu hỏi xác thực | Bằng chứng cần có |
|---|---|---|
| Người dùng không hiểu quyền truy cập | Quản trị viên có thể chọn đúng quyền cho từng vai trò không? | Quan sát thao tác, lỗi cấp quyền, cách người dùng giải thích quyền |
| Giao dịch có thể bị xử lý trùng | Hệ thống có giữ một kết quả nhất quán khi yêu cầu hoặc webhook được gửi lại không? | Trạng thái giao dịch, số bản ghi, log và kết quả đối soát |
| Dữ liệu có thể mất khi mạng gián đoạn | Người dùng có thể tiếp tục hoặc khôi phục công việc sau khi kết nối lại không? | Dữ liệu trước và sau ngắt mạng, tỷ lệ đồng bộ, lỗi xung đột |
| Dịch vụ phụ thuộc có thể phản hồi chậm | Hành trình có duy trì trạng thái rõ ràng khi dịch vụ vượt thời gian chờ không? | Độ trễ, timeout, retry, trạng thái giao diện và cảnh báo |
| Người dùng mới có thể không hoàn thành thiết lập | Nhóm người dùng mục tiêu có thể hoàn thành bước đầu mà không cần hỗ trợ không? | Tỷ lệ hoàn thành, thời gian, số lần trợ giúp và phản hồi |

Không phải rủi ro nào cũng được kiểm tra bằng cùng một phương pháp. Phỏng vấn và quan sát phù hợp để tìm hiểu nhu cầu, hiểu biết và hành vi. Kiểm thử chức năng, tích hợp, bảo mật, hiệu năng hoặc phục hồi phù hợp để xác minh hành vi hệ thống. Thử nghiệm thực địa và dữ liệu vận hành có thể cung cấp bằng chứng về điều kiện sử dụng thực tế.

### Xác định độ sâu kiểm thử theo mức rủi ro

Rủi ro thấp có thể được bao phủ bằng kiểm thử thông thường và giám sát phù hợp. Rủi ro cao thường cần nhiều lớp bằng chứng hơn, ví dụ:

- Kiểm thử đơn vị cho logic xử lý và nhánh lỗi.
- Kiểm thử hợp đồng tại ranh giới dịch vụ.
- Kiểm thử tích hợp với cấu hình và dữ liệu đại diện.
- Kiểm thử đầu cuối cho hành trình quan trọng.
- Kiểm thử lỗi, phục hồi, tải và bảo mật theo bản chất rủi ro.
- Kiểm thử hồi quy sau khi sửa hoặc thay đổi phụ thuộc.
- Giám sát và cảnh báo sau khi phát hành.

Việc tăng số lượng kiểm thử không tự động giảm rủi ro. Kịch bản phải bao phủ nguyên nhân và hậu quả đã mô tả, có dữ liệu đáng tin cậy và xác minh được trạng thái cuối. Một bài kiểm thử chạy thành công nhưng không kiểm tra đúng rủi ro sẽ tạo cảm giác an toàn giả.

### Đặt tiêu chí quyết định trước khi kiểm thử

Với rủi ro quan trọng, nhóm cần thống nhất trước:

- Điều kiện nào được xem là kiểm soát hoạt động đúng.
- Kết quả nào khiến rủi ro được giảm xuống.
- Lỗi nào là lỗi chặn phát hành.
- Bằng chứng tối thiểu phải có.
- Ai xem xét và ai có quyền chấp nhận rủi ro còn lại.
- Khi nào cần đánh giá lại.

Ví dụ, đối với rủi ro xử lý thanh toán trùng, tiêu chí có thể là sau nhiều lần gửi lại cùng một yêu cầu hoặc webhook, hệ thống chỉ ghi nhận một giao dịch nghiệp vụ, trạng thái cuối nhất quán và có thể truy vết. Tiêu chí cần được điều chỉnh theo hợp đồng thanh toán và quy tắc nghiệp vụ thật.

## 8. Xử lý rủi ro: giảm thiểu, tránh, chuyển giao hoặc chấp nhận

Đánh giá chỉ có ý nghĩa khi dẫn đến quyết định. Các lựa chọn thường gồm:

- **Tránh rủi ro:** thay đổi phạm vi hoặc thiết kế để loại bỏ điều kiện gây rủi ro. Ví dụ không triển khai một luồng chưa có cơ chế kiểm soát quyền cần thiết.
- **Giảm khả năng xảy ra:** bổ sung kiểm tra đầu vào, kiểm thử hợp đồng, đào tạo, xác thực hoặc kiểm soát cấu hình.
- **Giảm mức tác động:** giới hạn phạm vi ảnh hưởng, phân quyền tối thiểu, sao lưu, cơ chế phục hồi hoặc quy trình xử lý sự cố.
- **Chuyển giao hoặc chia sẻ:** dùng bảo hiểm, điều khoản hợp đồng, nhà cung cấp chuyên trách hoặc phân chia trách nhiệm. Việc chuyển giao không loại bỏ hoàn toàn trách nhiệm của tổ chức đối với người dùng và dữ liệu.
- **Chấp nhận:** quyết định tiếp tục với rủi ro còn lại khi nằm trong giới hạn cho phép, có lý do và được người có thẩm quyền phê duyệt.

Với mỗi biện pháp, cần xác định chủ sở hữu, thời hạn, nguồn lực, cách xác minh hiệu quả và rủi ro mới có thể phát sinh. Ví dụ, retry có thể giảm lỗi tạm thời nhưng tạo tải lớn hơn cho dịch vụ đang suy giảm. Cần kiểm thử cả tác dụng phụ của biện pháp kiểm soát.

### Phân biệt rủi ro trước và sau kiểm soát

- **Rủi ro vốn có (inherent risk):** mức rủi ro trước khi tính đến biện pháp kiểm soát.
- **Rủi ro hiện tại:** mức rủi ro khi xét các biện pháp đang thực sự được triển khai và có bằng chứng hoạt động.
- **Rủi ro còn lại (residual risk):** phần rủi ro vẫn tồn tại sau các biện pháp xử lý đã thực hiện hoặc dự kiến được chấp nhận.

Không nên giảm điểm chỉ vì một biện pháp đã được đề xuất. Chỉ đánh giá lại khi có bằng chứng cho thấy biện pháp đã triển khai và hoạt động trong phạm vi liên quan. Nếu kiểm soát chỉ được thử ở staging, hãy ghi rõ giới hạn trước khi kết luận về production.

### Theo dõi dấu hiệu kích hoạt và điều kiện đánh giá lại

Một rủi ro có thể thay đổi khi sản phẩm, người dùng, nhà cung cấp hoặc môi trường thay đổi. Hãy xác định tín hiệu kích hoạt đánh giá lại, chẳng hạn:

- Tỷ lệ lỗi hoặc độ trễ vượt ngưỡng.
- Lưu lượng hoặc số người dùng tăng đáng kể.
- Nhà cung cấp thay đổi API, quota hoặc chính sách.
- Phát hiện lỗ hổng, sự cố hoặc phản hồi người dùng mới.
- Hành trình hoặc loại dữ liệu được xử lý thay đổi.
- Biện pháp kiểm soát không đạt tiêu chí kiểm thử.

Việc đánh giá lại nên diễn ra trước các mốc quyết định quan trọng và khi xuất hiện bằng chứng mới, thay vì chỉ thực hiện theo lịch cố định.

## 9. Ví dụ: đánh giá rủi ro trong hành trình thanh toán thuê bao

Giả sử một sản phẩm SaaS cho phép người dùng chọn gói, thanh toán qua nhà cung cấp bên ngoài và kích hoạt thuê bao bằng một dịch vụ nội bộ. Nhóm dùng thang năm mức về khả năng xảy ra và tác động như ví dụ ở trên. Khoảng thời gian đánh giá là một chu kỳ phát hành và giai đoạn vận hành đầu tiên; các điểm số dưới đây chỉ minh họa cách lập luận.

| Rủi ro | Khả năng | Tác động | Điểm | Lý do và bằng chứng cần tìm |
|---|---:|---:|---:|---|
| Webhook thanh toán bị xử lý lặp | 3 | 5 | 15 | Nhà cung cấp có thể gửi lại khi timeout; cần kiểm thử idempotency và đối soát |
| Email xác nhận đến chậm | 4 | 2 | 8 | Dịch vụ email có thể trì hoãn; cần kiểm tra hàng đợi, trạng thái và cách gửi lại |
| Thuê bao không được kích hoạt sau khi thanh toán thành công | 2 | 5 | 10 | Cần kiểm tra cập nhật chéo dịch vụ, phục hồi và trạng thái giao dịch |
| Người dùng chọn nhầm gói do mô tả giá không rõ | 3 | 3 | 9 | Cần kiểm thử hiểu biết, cách trình bày giá và xác nhận trước thanh toán |

Từ bảng này, nhóm không nên chỉ nhìn điểm tổng để sắp thứ tự máy móc. Rủi ro webhook trùng có điểm 15 và tác động rất nghiêm trọng, nên cần ưu tiên kiểm thử hợp đồng, webhook trùng, timeout, xử lý đồng thời và trạng thái cuối. Rủi ro thuê bao không kích hoạt có điểm 10 nhưng cũng có tác động mức 5; cần xác định phương án đồng bộ lại và đối soát. Email đến chậm có điểm thấp hơn, nhưng vẫn cần trạng thái minh bạch để người dùng không hiểu nhầm giao dịch thất bại.

Một kế hoạch kiểm chứng có thể gồm:

1. Gửi cùng webhook nhiều lần và xác minh chỉ có một kết quả nghiệp vụ.
2. Mô phỏng nhà cung cấp xử lý giao dịch nhưng phản hồi bị mất.
3. Tạm ngừng dịch vụ kích hoạt sau khi thanh toán thành công rồi khôi phục.
4. Đối chiếu trạng thái giữa nhà cung cấp, dịch vụ thuê bao và giao diện.
5. Kiểm tra thông báo trong trường hợp email bị trì hoãn.
6. Quan sát người dùng chọn gói và giải thích số tiền, chu kỳ thanh toán trước khi xác nhận.

Sau khi kiểm thử, nhóm cập nhật khả năng xảy ra dựa trên bằng chứng, đánh giá hiệu lực biện pháp kiểm soát và ghi nhận rủi ro còn lại. Nếu chưa thể kiểm chứng một phụ thuộc, phải ghi rõ khoảng trống và người có thẩm quyền quyết định cách xử lý trước phát hành.

## 10. Ghi nhận và truyền đạt kết quả đánh giá

### Sổ đăng ký rủi ro

Một sổ đăng ký rủi ro nên chứa đủ thông tin để theo dõi từ lúc phát hiện đến khi đóng hoặc chấp nhận. Có thể dùng cấu trúc:

| Trường | Nội dung |
|---|---|
| ID và tên | Mã duy nhất và tiêu đề ngắn |
| Mô tả | Nguyên nhân, sự kiện và hậu quả |
| Mục tiêu bị ảnh hưởng | Người dùng, sản phẩm, kinh doanh hoặc nghĩa vụ |
| Phạm vi | Hành trình, nhóm người dùng, thành phần và môi trường |
| Khả năng xảy ra | Điểm, định nghĩa mức và khoảng thời gian |
| Tác động | Điểm theo chiều liên quan và lý do |
| Điểm ưu tiên | Kết quả ma trận và quy tắc vượt mức nếu có |
| Độ tin cậy | Cao, trung bình hoặc thấp; kèm bằng chứng |
| Kiểm soát hiện tại | Biện pháp đang triển khai và bằng chứng hiệu lực |
| Hành động tiếp theo | Kiểm thử, giảm thiểu, nghiên cứu hoặc chấp nhận |
| Chủ sở hữu | Người chịu trách nhiệm theo dõi và xử lý |
| Thời hạn và trạng thái | Mốc cần hoàn thành, trạng thái và ngày rà soát |
| Rủi ro còn lại | Đánh giá sau kiểm soát và người phê duyệt |

Một bản ghi nên ngắn gọn nhưng cụ thể. Tránh ghi “cần kiểm thử thêm” mà không nêu kịch bản, người phụ trách hoặc điều kiện hoàn thành.

### Truyền đạt cho các bên liên quan

Khi báo cáo, hãy nêu rủi ro có thể ảnh hưởng đến quyết định nào, bằng chứng hiện có, điều còn chưa biết và hành động đề xuất. Không chỉ trình bày bảng màu hoặc điểm số. Người ra quyết định cần hiểu:

- Điều gì có thể xảy ra và ai chịu ảnh hưởng.
- Vì sao nhóm đánh giá khả năng và tác động ở mức đó.
- Biện pháp hiện tại có hiệu quả đến đâu.
- Cần kiểm thử hoặc xử lý gì tiếp theo.
- Phần rủi ro còn lại có nằm trong giới hạn chấp nhận không.
- Ai có thẩm quyền đưa ra quyết định và khi nào cần xem xét lại.

Nếu có ý kiến bất đồng về điểm số, hãy ghi lại các giả định khác nhau và bằng chứng cần có để giải quyết. Không nên ép đạt đồng thuận bằng cách lấy trung bình các nhận định không cùng cơ sở.

## 11. Những sai lầm thường gặp

- **Chấm điểm mà không có khoảng thời gian:** cùng một rủi ro có thể được đánh giá khác nhau nếu không thống nhất thời hạn và số lần phơi nhiễm.
- **Dùng từ “cao” nhưng không có định nghĩa:** mỗi người hiểu mức độ theo kinh nghiệm riêng, làm kết quả thiếu nhất quán.
- **Gộp nhiều sự kiện vào một rủi ro:** nguyên nhân và biện pháp xử lý bị lẫn lộn.
- **Chỉ đánh giá tác động tài chính:** bỏ qua trải nghiệm, quyền riêng tư, an toàn, vận hành và nghĩa vụ.
- **Xem không có dữ liệu là khả năng thấp:** thiếu quan sát có thể làm rủi ro bị đánh giá thấp.
- **Coi điểm nhân là xác suất thiệt hại:** điểm thứ bậc chỉ hỗ trợ sắp xếp, không phải phép đo chính xác.
- **Để điểm thấp che khuất hậu quả nghiêm trọng:** rủi ro về an toàn, bảo mật hoặc tuân thủ cần quy tắc xem xét riêng.
- **Giảm điểm ngay khi đề xuất biện pháp:** biện pháp chưa triển khai hoặc chưa được kiểm chứng chưa làm giảm rủi ro thực tế.
- **Không gắn rủi ro với kiểm thử:** bảng đánh giá không tạo ra bằng chứng hoặc quyết định.
- **Không cập nhật khi bối cảnh đổi:** dữ liệu cũ có thể không còn đại diện sau thay đổi về sản phẩm, tải hoặc phụ thuộc.

## 12. Đầu ra cần có trước khi chốt đánh giá rủi ro

Một đánh giá đủ dùng cho chiến lược kiểm thử xác thực nên có:

1. **Danh sách rủi ro cụ thể:** mỗi mục có nguyên nhân, sự kiện, hậu quả, mục tiêu và phạm vi bị ảnh hưởng.
2. **Thang khả năng xảy ra:** định nghĩa mức, khoảng thời gian, đơn vị phơi nhiễm và nguồn bằng chứng.
3. **Thang tác động:** các chiều liên quan, tiêu chí từng mức và quy tắc xử lý hậu quả nghiêm trọng.
4. **Ma trận và quy tắc ưu tiên:** cách kết hợp điểm, ngưỡng hành động và trường hợp vượt mức.
5. **Đánh giá độ tin cậy:** giả định, khoảng trống dữ liệu và mức độ chắc chắn của nhận định.
6. **Kế hoạch xử lý:** biện pháp, người phụ trách, thời hạn và cách xác minh hiệu lực.
7. **Kế hoạch kiểm thử:** câu hỏi xác thực, kịch bản, môi trường, dữ liệu và tiêu chí quyết định.
8. **Rủi ro còn lại:** mức sau kiểm soát, lý do chấp nhận và người có thẩm quyền.
9. **Điều kiện đánh giá lại:** sự kiện kích hoạt, chu kỳ rà soát và nguồn tín hiệu vận hành.

Trước khi dùng kết quả để ra quyết định, hãy rà soát:

- Mỗi rủi ro có gắn với mục tiêu và hành trình cụ thể không?
- Mô tả có nêu rõ nguyên nhân, sự kiện và hậu quả không?
- Thang khả năng có thời gian và điều kiện đánh giá rõ ràng không?
- Thang tác động có bao phủ những hậu quả quan trọng đối với sản phẩm không?
- Có ghi nguồn bằng chứng và độ tin cậy của điểm số không?
- Ma trận có được dùng như công cụ ưu tiên thay vì kết luận tuyệt đối không?
- Rủi ro nghiêm trọng có quy tắc xem xét riêng không?
- Mỗi rủi ro ưu tiên có biện pháp, người phụ trách và kiểm thử tương ứng không?
- Rủi ro còn lại có được người có thẩm quyền xem xét và chấp nhận không?

Khi các nội dung này được thống nhất, nhóm có thể phân bổ nguồn lực kiểm thử theo mức độ rủi ro, tập trung vào những điều có thể làm thất bại mục tiêu sản phẩm và bảo vệ người dùng. Thang đo cần được hiệu chỉnh khi có dữ liệu vận hành, sự cố mới hoặc thay đổi về bối cảnh. Đánh giá rủi ro vì thế là hoạt động lặp lại trong suốt vòng đời xác thực, từ lúc hình thành giả thuyết đến khi theo dõi sản phẩm sau phát hành.

