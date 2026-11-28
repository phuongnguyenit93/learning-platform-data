# Risk là gì?

Trong chương **Quản lý rủi ro**, **risk (rủi ro)** là một khái niệm nền tảng để trả lời câu hỏi: **Điều gì có thể xảy ra, vì sao có thể xảy ra, hậu quả đối với mục tiêu của tổ chức là gì và chúng ta có đủ cơ sở để chấp nhận mức rủi ro hiện tại hay không?**

Đối với bảo mật thông tin, rủi ro xuất hiện khi một sự kiện hoặc tình huống bất định có thể ảnh hưởng đến mục tiêu bảo vệ dữ liệu, dịch vụ, tài sản, con người và hoạt động kinh doanh. Ví dụ, một nền tảng học trực tuyến có thể bị lộ kết quả học tập nếu API kiểm tra quyền không đầy đủ, có thể gián đoạn nếu bị tấn công từ chối dịch vụ, hoặc có thể mất dữ liệu nếu bản sao lưu không khôi phục được khi cần.

Trong module **SECURITY_SECURITY_ASSURANCE**, hiểu risk không dừng ở việc “liệt kê mối nguy”. Chúng ta cần **chứng minh bằng bằng chứng** rằng các mục tiêu bảo mật đang được đáp ứng: nhận diện rủi ro, xác định yêu cầu, thiết kế security controls, kiểm thử, đánh giá hiệu quả vận hành, audit và khắc phục phát hiện. Kết luận cuối cùng phải nêu rõ **rủi ro còn lại**, căn cứ của nhận định và điều gì vẫn chưa được kiểm chứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích risk trong bối cảnh bảo mật, phân biệt nó với threat, vulnerability, event, incident và issue.
2. Phân tích một kịch bản rủi ro bằng tài sản, nguồn đe dọa, điểm yếu, điều kiện xảy ra và hậu quả đối với mục tiêu.
3. Hiểu vai trò của **likelihood**, **impact**, độ bất định và chất lượng bằng chứng khi ước lượng mức rủi ro.
4. Phân biệt **inherent risk** và **residual risk**, risk appetite và risk tolerance.
5. Đọc hoặc tạo một bản ghi risk register có owner, controls, bằng chứng, phương án xử lý và thời hạn đánh giá lại.
6. Kết nối đánh giá rủi ro với các hoạt động security assurance liên tục trong phát triển và vận hành.

## 2. Định nghĩa risk trong bảo mật

### 2.1. Rủi ro gắn với mục tiêu và sự bất định

Trong quản trị rủi ro nói chung, risk được hiểu theo ý tưởng **ảnh hưởng của sự bất định lên mục tiêu**. Ảnh hưởng đó có thể được nhìn nhận theo chiều tích cực hoặc tiêu cực trong bối cảnh rộng. Riêng khi đánh giá **security risk**, chúng ta chủ yếu quan tâm đến những kịch bản có thể gây hại: mất tính bí mật, toàn vẹn, sẵn sàng hoặc làm gián đoạn việc đạt mục tiêu kinh doanh.

Hai yếu tố không thể bỏ qua:

- **Mục tiêu cần bảo vệ:** dữ liệu học viên, quyền riêng tư, chức năng nộp bài, giao dịch, uy tín, cam kết dịch vụ, sự liên tục của hoạt động...
- **Sự bất định:** chưa chắc sự kiện sẽ xảy ra, chưa biết toàn bộ điều kiện gây ra sự kiện, chưa xác định chính xác tần suất hoặc mức thiệt hại nếu xảy ra.

Một máy chủ tồn tại trên Internet **không tự động** có cùng mức rủi ro với mọi máy chủ khác. Mức rủi ro còn phụ thuộc thông tin được xử lý, mức phơi bày, khả năng khai thác, control đang hoạt động và hậu quả khi xảy ra sự cố.

**Ví dụ:** Một endpoint nội bộ chỉ trả về danh sách khóa học công khai và một endpoint xuất toàn bộ hồ sơ học viên có mức tác động rất khác nhau nếu bị truy cập trái phép. Cùng một lỗi thiếu kiểm tra phân quyền có thể dẫn tới các mức rủi ro khác nhau vì **tài sản và hậu quả khác nhau**.

### 2.2. Công thức thường gặp và giới hạn của nó

Trong đánh giá đơn giản, người ta hay tóm tắt:

\[
\text{Risk level} \approx f(\text{Likelihood},\text{Impact})
\]

Khi dùng thang điểm có quy ước nội bộ, một phép tính tham khảo là:

\[
\text{Risk score} = \text{Likelihood score} \times \text{Impact score}
\]

Tuy nhiên, **đây là mô hình hỗ trợ phân loại, không phải công thức vật lý hoặc định luật chung**. “Likelihood = 3” trong ma trận 5 mức thường là **nhãn định tính** chứ không phải xác suất 3/5. Nhân hai nhãn thứ tự không tự tạo ra ước lượng tiền bạc, tần suất hay độ chính xác thống kê.

Trong bối cảnh có đủ dữ liệu và mô hình phù hợp, rủi ro có thể được phân tích định lượng bằng phân bố tần suất sự kiện và mức thiệt hại; khi thiếu dữ liệu, có thể dùng cách định tính hoặc bán định lượng kèm giả định rõ ràng.

### 2.3. Risk là một kịch bản có nguyên nhân và hậu quả

So sánh ba cách nói:

- **“Hệ thống có CVE nghiêm trọng.”** Đây là dấu hiệu về một điểm yếu hoặc thông tin lỗ hổng; chưa diễn đạt trọn vẹn rủi ro đối với mục tiêu.
- **“Cơ sở dữ liệu có thể bị tấn công.”** Câu còn mơ hồ về điều kiện, tài sản, hình thức tấn công và hậu quả.
- **“Nếu dịch vụ xuất báo cáo cho phép giảng viên truy cập học viên ngoài lớp mình quản lý, kẻ có tài khoản hợp lệ có thể lấy hồ sơ học viên khác, dẫn tới lộ dữ liệu và vi phạm cam kết bảo vệ thông tin.”** Đây là một **risk scenario** có thể phân tích, kiểm thử và quản lý.

Một rủi ro có thể hiện hữu **ngay khi chưa có sự cố xảy ra**. Ngược lại, khi sự cố đã xảy ra, dữ kiện thực tế phải được đưa ngược vào đánh giá likelihood, impact, hiệu quả control và rủi ro tái diễn.

## 3. Các khái niệm dễ nhầm lẫn

| Khái niệm | Ý nghĩa | Ví dụ trong nền tảng học trực tuyến |
|---|---|---|
| **Asset – tài sản** | Thứ tạo giá trị hoặc cần được bảo vệ | Cơ sở dữ liệu kết quả học tập, mã nguồn, tài khoản quản trị |
| **Objective – mục tiêu** | Kết quả bảo mật/kinh doanh cần đạt | Chỉ giảng viên được phân quyền mới xem kết quả của lớp |
| **Threat – mối đe dọa** | Nguồn hoặc hoàn cảnh có thể gây hại | Kẻ có tài khoản hợp lệ lạm dụng quyền; lỗi vận hành; malware |
| **Threat event – sự kiện đe dọa** | Hành động hoặc biến cố có thể dẫn tới tác động | Người dùng sửa classId để gọi API của lớp khác |
| **Vulnerability – điểm yếu** | Điểm có thể bị khai thác hoặc làm tăng khả năng hậu quả | Backend chỉ kiểm tra đăng nhập, không kiểm tra quyền theo lớp |
| **Exposure – mức phơi bày** | Mức độ tài sản/đường tấn công có thể tiếp cận | API truy cập từ Internet; token có phạm vi quá rộng |
| **Control – biện pháp kiểm soát** | Biện pháp phòng ngừa, phát hiện, đáp ứng hoặc giảm tác động | Kiểm tra quyền trên server, log, alert và revoke token |
| **Risk – rủi ro** | Khả năng và hậu quả bất định đối với mục tiêu | Dữ liệu lớp học bị người không có quyền lấy được |
| **Incident – sự cố** | Sự kiện gây ảnh hưởng hoặc đe dọa ảnh hưởng cần xử lý theo quy trình | Đã có truy cập chéo lớp và dữ liệu bị xuất trái phép |
| **Finding/Issue – phát hiện/vấn đề** | Sai lệch đã được nhận diện qua kiểm tra hoặc vận hành | Test API cho thấy có thể đọc dữ liệu lớp khác |

**Threat không đồng nghĩa với risk.** Một kiểu tấn công được biết đến vẫn cần bối cảnh tài sản, đường tác động và control để xác định rủi ro thực tế. **Vulnerability không đồng nghĩa với incident:** có lỗ hổng chưa chắc đã có ai khai thác. **Finding không tự nó là mức rủi ro:** kết quả kiểm thử cần liên kết với khả năng và tác động để quyết định ưu tiên.

Rủi ro không nhất thiết phải bắt đầu từ một CVE hay kẻ tấn công có chủ ý. Một thao tác triển khai sai, xóa nhầm khóa giải mã backup hoặc thiếu người trực khi cảnh báo xảy ra đều có thể tạo rủi ro bảo mật và vận hành.

## 4. Thành phần của một risk scenario

Một kịch bản rủi ro hữu ích nên mô tả ít nhất **tài sản, mục tiêu bị ảnh hưởng, sự kiện/điều kiện gây rủi ro, điểm yếu hoặc đường phơi bày, hậu quả**. Với risk register cần bổ sung owner, mức độ, controls, giả định và cách xử lý.

### 4.1. Tài sản và bối cảnh kinh doanh

Đừng chỉ liệt kê máy chủ hoặc database. Cần hiểu nó hỗ trợ hoạt động gì, chứa dữ liệu nào, phục vụ ai và mức độ quan trọng:

- **Thông tin:** hồ sơ, điểm số, bài nộp, mật khẩu/bí mật, dữ liệu đối tác.
- **Dịch vụ:** đăng nhập, chấm bài, API nội bộ, thanh toán, quản trị production.
- **Nền tảng/phụ thuộc:** cloud account, CI/CD, kho mã nguồn, identity provider, nhà cung cấp.
- **Con người/quy trình:** đội trực vận hành, người phê duyệt thay đổi, nhân sự có quyền đặc biệt.
- **Nghĩa vụ:** bảo vệ dữ liệu, điều khoản hợp đồng, thời gian khôi phục theo cam kết.

Mức quan trọng của tài sản thường được xác định cùng **business owner**, không chỉ dựa trên cảm nhận của nhóm kỹ thuật.

### 4.2. Đe dọa, điều kiện và điểm yếu

Một threat actor có thể là người ngoài, tài khoản nội bộ bị chiếm quyền, người dùng lạm dụng quyền hoặc bên thứ ba. Với lỗi không chủ đích, nguồn sự kiện có thể là thao tác nhầm, sự cố hạ tầng hoặc lỗi quy trình.

Điểm yếu làm rủi ro dễ xảy ra hơn hoặc nặng hơn: phân quyền thiếu, cấu hình cloud lỏng, secret tồn tại lâu, thiếu monitoring, backup không kiểm thử, việc cấp quyền thiếu chủ sở hữu. Một kịch bản có thể có **nhiều điểm yếu nối tiếp**, cũng có thể không gắn với một “lỗ hổng phần mềm” cụ thể.

### 4.3. Hậu quả và đường tác động

Đừng dừng ở “bị hack” hoặc “mất dữ liệu”. Cần diễn giải tác động lên mục tiêu:

- **Confidentiality:** lộ điểm học viên, hồ sơ cá nhân, thông tin xác thực.
- **Integrity:** sửa điểm, thay nội dung bài thi, can thiệp artifact phát hành.
- **Availability:** không thể truy cập dịch vụ hoặc mất thời gian khôi phục.
- **Khả năng điều tra/trách nhiệm:** thiếu log khiến không xác định được dữ liệu bị ảnh hưởng.
- **Kinh doanh và nghĩa vụ:** chi phí khắc phục, gián đoạn hợp đồng, mất uy tín, nghĩa vụ thông báo hoặc chế tài tùy bối cảnh.

Một sự cố có thể đồng thời gây nhiều loại tác động. Cần tránh **đếm lặp** cùng thiệt hại khi tổng hợp.

### 4.4. Mẫu diễn đạt risk statement

Có thể dùng cấu trúc:

> **Do [điều kiện/điểm yếu] trong [tài sản/quy trình], [nguồn sự kiện] có thể [sự kiện], dẫn tới [hậu quả] và ảnh hưởng [mục tiêu].**

Ví dụ:

> Do API xuất báo cáo chỉ kiểm tra đăng nhập mà chưa xác minh người dùng sở hữu lớp học, giảng viên có tài khoản hợp lệ có thể yêu cầu xuất dữ liệu của lớp khác, dẫn tới lộ kết quả học tập và ảnh hưởng nghĩa vụ bảo vệ dữ liệu học viên.

Mẫu câu giúp dễ truy vết, nhưng đánh giá chất lượng dựa trên **kịch bản có thể kiểm chứng** và **hậu quả có ý nghĩa**, không phải việc điền đủ mọi ô một cách hình thức.

## 5. Từ risk scenario đến likelihood và impact

### 5.1. Likelihood: sự kiện có khả năng xảy ra đến đâu?

Likelihood có thể phản ánh xác suất, tần suất hoặc khả năng xảy ra theo **kỳ thời gian và phạm vi cụ thể**. Nếu đánh giá định tính, phải công bố tiêu chí xếp mức.

Những yếu tố thường ảnh hưởng:

- Đường tấn công có tiếp cận được không: Internet, VPN, mạng nội bộ hay chỉ có quyền cao?
- Điều kiện để thực hiện khó hay dễ: cần tài khoản, tương tác người dùng, nhiều bước phối hợp?
- Có dấu hiệu đã bị thử khai thác hay có khai thác rộng rãi ở môi trường tương tự?
- Bao nhiêu tài sản/tài khoản chịu ảnh hưởng và hiện diện trong bao lâu?
- Control phòng ngừa và phát hiện có **được xác minh đang hoạt động** hay chỉ tồn tại trên tài liệu?
- Đặc điểm thay đổi: release thường xuyên, quyền cấp ngoài quy trình, tài sản không được kiểm kê?

**Không được dùng điểm nghiêm trọng lỗ hổng (ví dụ CVSS) làm xác suất xảy ra rủi ro một cách máy móc.** Điểm severity và các tín hiệu khai thác có thể hỗ trợ ưu tiên, nhưng phải xem cả đường phơi bày và ảnh hưởng thực tế trong môi trường.

### 5.2. Impact: nếu xảy ra thì hậu quả lớn đến đâu?

Impact cần phản ánh tác động có thể xảy ra lên mục tiêu trong bối cảnh tổ chức. Ví dụ:

| Chiều tác động | Câu hỏi đặt ra | Bằng chứng hoặc dữ liệu hữu ích |
|---|---|---|
| Bảo mật thông tin | Loại dữ liệu nào bị lộ? Số đối tượng tối đa và tính nhạy cảm? | Data classification, data flow, quyền truy cập thực tế |
| Tính toàn vẹn | Dữ liệu hoặc hành động nào có thể bị sửa và có phát hiện được không? | Mô hình quyền, audit log, khả năng đối chiếu/rollback |
| Tính sẵn sàng | Dịch vụ nào dừng, bao lâu, có phục hồi được không? | Business impact analysis, RTO/RPO, restore test |
| Tài chính | Chi phí ứng phó, tổn thất trực tiếp, chi phí gián đoạn ước tính? | Thống kê vận hành, hợp đồng, giả định định lượng |
| Pháp lý/hợp đồng | Nghĩa vụ nào có thể bị ảnh hưởng? | Ý kiến Legal/Compliance và phạm vi dữ liệu/địa bàn |
| Uy tín/khách hàng | Nhóm khách hàng nào bị ảnh hưởng, mức độ tin cậy giảm ra sao? | Phạm vi tác động, thỏa thuận dịch vụ, dữ liệu sự cố trước |

Phân tích impact cần tránh giả định “một database bị xâm nhập thì chắc chắn mọi hồ sơ đều bị lộ”. Thay vào đó, mô tả **kịch bản hợp lý**, khả năng lan rộng, giới hạn truy cập và độ tin cậy của giả định.

### 5.3. Uncertainty: độ bất định không nên bị giấu

Hai rủi ro cùng được gắn “High” có thể có chất lượng thông tin rất khác nhau. Một rủi ro có log đầy đủ, test đã lặp lại và asset inventory chính xác; rủi ro khác dựa trên suy đoán vì thiếu log, không rõ quyền và chưa thực hiện test.

Vì vậy, bên cạnh mức rủi ro, có thể ghi:

- **Confidence:** cao/trung bình/thấp theo phương pháp nội bộ.
- **Assumption:** giả định quan trọng, ví dụ mọi API đều đi qua gateway.
- **Evidence gap:** chưa có log, chưa kiểm thử một tuyến truy cập hoặc không xác định được tổng thể tài khoản.
- **Decision implication:** cần điều tra/bổ sung test trước khi đưa ra quyết định cuối cùng.

**Thiếu dữ liệu không đồng nghĩa với rủi ro thấp.** Mức bất định cao có thể là lý do tăng ưu tiên kiểm tra, tạm giới hạn phạm vi hoặc triển khai control phòng ngừa phù hợp.

## 6. Đánh giá rủi ro định tính và định lượng

### 6.1. Định tính: nhanh, dễ trao đổi nhưng cần quy ước rõ

Tổ chức có thể dùng các mức likelihood và impact từ 1 đến 5, với mô tả gắn với hệ thống. Ví dụ **thang minh họa**, không phải chuẩn bắt buộc:

| Mức | Likelihood – cách diễn giải minh họa | Impact – cách diễn giải minh họa |
|---|---|---|
| 1 | Điều kiện xảy ra rất hạn chế và có control mạnh đã xác minh | Ảnh hưởng nhỏ, cục bộ, khôi phục đơn giản |
| 2 | Khó xảy ra trong điều kiện hiện tại | Ảnh hưởng giới hạn đến một chức năng hoặc nhóm nhỏ |
| 3 | Có đường xảy ra khả dĩ, một số control/điều kiện chưa chắc chắn | Ảnh hưởng đáng kể, cần điều phối xử lý |
| 4 | Có nhiều điều kiện thuận lợi hoặc dấu hiệu xảy ra tương tự | Ảnh hưởng nghiêm trọng đến dữ liệu/dịch vụ trọng yếu |
| 5 | Khả năng rất cao theo tín hiệu và điều kiện cụ thể | Ảnh hưởng rất nghiêm trọng, lan rộng hoặc kéo dài |

Đây là mô tả đơn giản để thảo luận. Muốn sử dụng nhất quán, tổ chức phải định nghĩa **kỳ thời gian, phạm vi tài sản, ngưỡng tác động, cách dùng bằng chứng, người có quyền chấm điểm**. Không nên gán mức 5 chỉ vì rủi ro nghe đáng sợ.

Một ma trận phân loại nội bộ có thể tính:

\[
S=L\times I,\qquad L,I\in\{1,2,3,4,5\}.
\]

Ví dụ giả định: L = 3, I = 4, nên **S = 12**. Nếu chính sách nội bộ quy định 10–16 thuộc nhóm cần ưu tiên cao, rủi ro này sẽ được xử lý ở nhóm đó. Các ngưỡng và điểm số **phải được doanh nghiệp định nghĩa**; 12 không có nghĩa “xác suất 12%” hay “thiệt hại 12 đơn vị tiền”.

Hạn chế cần nhớ: phép nhân trên thang điểm thứ tự có thể che mất khác biệt giữa **low likelihood – extreme impact** và **high likelihood – moderate impact**, dẫn đến ưu tiên sai nếu chỉ dựa vào score. Với kịch bản tác động thảm họa, ràng buộc pháp lý hoặc safety, có thể cần quy tắc escalation riêng bất kể điểm tổng.

### 6.2. Định lượng: hữu ích khi có dữ liệu và giả định phù hợp

Trong mô hình đơn giản của tổn thất kỳ vọng theo năm, người học có thể gặp:

\[
\text{ALE}=\text{SLE}\times\text{ARO}
\]

Trong đó **SLE** (Single Loss Expectancy) là thiệt hại cho một sự kiện giả định; **ARO** (Annualized Rate of Occurrence) là số lần kỳ vọng xảy ra mỗi năm; **ALE** (Annualized Loss Expectancy) là tổn thất kỳ vọng hằng năm trong mô hình này.

Ví dụ giả định: một loại sự cố được ước lượng gây tổn thất trung bình **200 triệu đồng/lần** và có tần suất kỳ vọng **0,1 lần/năm**. Khi đó:

\[
\text{ALE}=200\,000\,000\times0{,}1=20\,000\,000\text{ đồng/năm}.
\]

Con số 20 triệu đồng/năm là **kỳ vọng toán học theo giả định**, không phải ngân sách chắc chắn đủ để xử lý hay mức thiệt hại tối đa. Sự cố vẫn có thể gây mất 200 triệu đồng hoặc nhiều hơn nếu nhiều yếu tố thay đổi. Kết quả chịu ảnh hưởng lớn từ chất lượng dữ liệu, phân bố tổn thất, tương quan và các trường hợp cực đoan.

Trong thực tế, phân tích định lượng trưởng thành hơn có thể mô hình hóa **phân bố tần suất và phân bố mức tổn thất**, sử dụng khoảng tin cậy hoặc các kịch bản để phản ánh độ bất định. Không nên đưa số giả chính xác đến từng đồng nếu dữ liệu nền chưa đủ tin cậy.

### 6.3. Khi nào dùng cách nào?

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Cần sàng lọc nhiều rủi ro mới, dữ liệu hạn chế | Định tính với tiêu chí và assumptions rõ |
| Cần ưu tiên remediation giữa các asset | Kết hợp bằng chứng khai thác, exposure, impact và đánh giá định tính/bán định lượng |
| Cần so sánh đầu tư, chi phí gián đoạn, tổn thất tài chính | Định lượng theo kịch bản và dữ liệu đáng tin cậy |
| Tác động rất lớn nhưng tần suất khó biết | Phân tích kịch bản, độ nhạy, giả định thận trọng và quy tắc escalation |
| Có thay đổi lớn hoặc incident mới | Cập nhật kịch bản, bằng chứng và likelihood/impact; không dùng điểm cũ mặc định |

## 7. Inherent risk, control và residual risk

**Inherent risk (rủi ro vốn có)** là mức rủi ro được xem xét **trước khi tính đến các control xử lý rủi ro đang áp dụng** theo phương pháp của tổ chức. **Residual risk (rủi ro còn lại)** là mức rủi ro sau khi xét hiệu quả của những biện pháp kiểm soát có liên quan.

Phân biệt này giúp lãnh đạo hiểu **control tạo khác biệt gì** và **phần rủi ro nào vẫn phải xử lý hoặc chấp nhận**.

~~~mermaid
flowchart LR
    A["Tài sản và mục tiêu"] --> B["Kịch bản rủi ro"]
    B --> C["Inherent risk"]
    C --> D["Control phòng ngừa, phát hiện, ứng phó, phục hồi"]
    D --> E["Kiểm thử hiệu quả và thu thập bằng chứng"]
    E --> F["Residual risk"]
    F --> G{"So với appetite/tolerance?"}
    G -->|"Trong giới hạn"| H["Quyết định và theo dõi"]
    G -->|"Vượt giới hạn/chưa đủ evidence"| I["Bổ sung control, giảm phơi bày hoặc đánh giá lại"]
    I --> D
~~~

### 7.1. Ví dụ thay đổi mức rủi ro sau control

Công ty có API xuất kết quả học tập. Khi chưa tính đến control, khả năng truy cập chéo lớp có thể được chấm **likelihood = 4**, **impact = 4**, điểm minh họa **16**. Sau khi thực hiện authorization theo từng đối tượng, negative test, log và giám sát, nhóm đánh giá dự kiến likelihood giảm xuống **2**, impact vẫn là **4**, điểm minh họa **8**.

Đây chỉ là **ví dụ về cách diễn giải một ma trận nội bộ**. Không được cập nhật “16 → 8” chỉ vì control đã được lên kế hoạch hoặc code mới được merge. Cần xác nhận control đã triển khai đúng, test bao phủ các tuyến liên quan và đang hoạt động trong production. Nếu kiểm thử chưa đủ, có thể chỉ ghi **residual risk mục tiêu/dự kiến**, còn **residual risk đã được xác minh** vẫn chưa thể kết luận.

Control có thể giảm **likelihood** (ví dụ chặn truy cập trái phép), giảm **impact** (ví dụ phân đoạn dữ liệu/giới hạn quyền), hoặc cải thiện khả năng **phát hiện và ứng phó** để hạn chế hậu quả. Một control không nhất thiết làm giảm mọi chiều tác động.

### 7.2. Các trạng thái rủi ro cần tách riêng

- **Risk hiện tại:** đánh giá theo hệ thống và bằng chứng đang có.
- **Target risk:** mức rủi ro kỳ vọng sau các hành động đã lên kế hoạch.
- **Accepted risk:** mức rủi ro được người có thẩm quyền chấp nhận với phạm vi, lý do, điều kiện và thời hạn rõ.
- **Emerging risk:** rủi ro mới hoặc thay đổi nhanh, cần theo dõi và có thể chưa đủ bằng chứng để chấm điểm chắc chắn.

“Risk được chấp nhận” không đồng nghĩa “risk đã được giảm”, và “risk đã chấm điểm” cũng không đồng nghĩa đã xác minh hiệu quả các control.

## 8. Risk appetite, risk tolerance và ngưỡng xử lý

**Risk appetite** thể hiện mức độ và loại rủi ro mà tổ chức sẵn sàng theo đuổi hoặc duy trì để đạt mục tiêu, do cấp quản trị phù hợp xác định. **Risk tolerance** thường mô tả mức biến động hoặc giới hạn cụ thể tổ chức có thể chấp nhận quanh mục tiêu hay ngưỡng đã định.

Ví dụ minh họa:

- **Appetite:** gần như không chấp nhận việc lộ thông tin cá nhân của học viên do quyền truy cập bị cấu hình sai.
- **Tolerance cụ thể:** các sự cố vi phạm chính sách phân quyền quan trọng phải được cô lập và trình đúng cấp theo thời hạn quy định nội bộ; thời gian xử lý được xác định theo mức độ rủi ro.
- **Quy tắc escalation:** hệ thống production có một đường truy cập admin chưa kiểm chứng không được tự đưa vào nhóm “rủi ro thấp” chỉ do chưa ghi nhận tấn công.

Khẩu vị rủi ro phải thống nhất với yêu cầu pháp lý, hợp đồng, safety nếu có, năng lực xử lý và mục tiêu kinh doanh. **Thẩm quyền chấp nhận rủi ro phải được ủy quyền rõ ràng**. Nhóm bảo mật/CISO có thể phân tích và khuyến nghị, nhưng không mặc nhiên thay thế risk owner hoặc lãnh đạo chịu trách nhiệm nghiệp vụ. Chấp nhận rủi ro nội bộ cũng **không tự xóa bỏ nghĩa vụ tuân thủ bắt buộc**.

## 9. Bốn hướng xử lý rủi ro phổ biến

Khi residual risk vượt ngưỡng hoặc chưa được hiểu rõ, tổ chức có thể lựa chọn phương án phù hợp:

| Phương án | Ý nghĩa | Ví dụ | Điều cần làm rõ |
|---|---|---|---|
| **Mitigate/Reduce – giảm thiểu** | Triển khai hoặc cải thiện control làm giảm likelihood/impact | Sửa authorization, MFA, giới hạn scope token, backup và restore test | Control owner, deadline, retest, mức rủi ro còn lại |
| **Avoid – tránh** | Không thực hiện hoặc chấm dứt hoạt động sinh rủi ro | Không mở tính năng xuất dữ liệu nhạy cảm khi chưa có cơ chế phân quyền | Ảnh hưởng đến mục tiêu kinh doanh và quyền quyết định |
| **Transfer/Share – chuyển giao/chia sẻ** | Phân bổ một phần hậu quả tài chính/trách nhiệm qua hợp đồng hoặc bảo hiểm | Hợp đồng hỗ trợ ứng phó với nhà cung cấp, bảo hiểm rủi ro mạng | Không thể chuyển giao toàn bộ trách nhiệm và hậu quả; phải theo hợp đồng áp dụng |
| **Accept/Retain – chấp nhận** | Giữ rủi ro theo quyết định có thẩm quyền | Chấp nhận tạm một finding mức thấp có control bù trừ và thời hạn | Risk owner, lý do, scope, hạn tái đánh giá và nghĩa vụ liên quan |

Một tổ chức có thể **kết hợp** các cách xử lý. Ví dụ tạm giới hạn phạm vi cung cấp dịch vụ (avoid một phần), triển khai control bổ sung (mitigate) và chấp nhận rủi ro còn lại trong thời gian xác định. “Chuyển giao” không biến mất khả năng lộ dữ liệu hoặc thiệt hại uy tín, nên không được ngừng giám sát.

## 10. Ai sở hữu rủi ro và ai chịu trách nhiệm control?

Trách nhiệm nên được phân định trước khi tạo kế hoạch xử lý:

| Vai trò | Trách nhiệm liên quan đến risk |
|---|---|
| **Business/asset owner** | Cung cấp giá trị tài sản, mục tiêu và hậu quả nếu kịch bản xảy ra |
| **Risk owner** | Chịu trách nhiệm theo dõi và lựa chọn phương án xử lý/chấp nhận trong phạm vi ủy quyền |
| **Control owner** | Thiết kế, triển khai, vận hành và cung cấp evidence về control |
| **Engineering/Platform/Ops** | Xây dựng và vận hành control kỹ thuật trong hệ thống, khắc phục sai lệch |
| **CISO/Security/GRC** | Định nghĩa phương pháp, tư vấn, đánh giá, thách thức giả định và báo cáo rủi ro |
| **Assessor/Internal audit** | Đánh giá bằng chứng và kết luận theo phạm vi/mức độc lập phù hợp |
| **Lãnh đạo/cấp quản trị** | Xác định mức rủi ro chấp nhận và quyết định những vấn đề vượt thẩm quyền owner |

Một người có thể kiêm nhiều vai trò ở tổ chức nhỏ nhưng cần quản lý xung đột lợi ích, nhất là khi **người triển khai control cũng tự kết luận kiểm soát của mình hoàn toàn hiệu quả**. Mức độ độc lập và giới hạn của assessment phải được báo cáo trung thực.

## 11. Risk register: hồ sơ theo dõi rủi ro có thể kiểm chứng

**Risk register** là nơi lưu kịch bản và quyết định xử lý rủi ro theo cách nhất quán. Nó phải đủ thông tin để người khác hiểu và đánh giá lại, không chỉ là một danh sách có màu.

Các trường nên có:

1. **Risk ID, tên và mô tả kịch bản**.
2. **Mục tiêu/tài sản/quy trình/phạm vi**, nguồn phát hiện, ngày ghi nhận.
3. **Threat, điểm yếu/đường phơi bày và hậu quả**.
4. **Risk owner**, control owner, các bên cần phối hợp.
5. **Phương pháp và kết quả đánh giá** likelihood, impact, inherent/current/residual risk, độ tin cậy và giả định.
6. **Controls đang hoạt động**, nguồn evidence và kết quả test.
7. **Kế hoạch xử lý**, hành động, người thực hiện, thời hạn, trạng thái, kết quả retest.
8. **Quyết định chấp nhận hoặc escalation**, người phê duyệt, giới hạn và ngày hết hiệu lực.
9. **Trigger và kỳ xem xét lại**, các liên kết đến incident, change hoặc audit finding.

### 11.1. Ví dụ một bản ghi risk register

Giả sử một đội phát triển Java vận hành API cung cấp thông tin lớp học. Hồ sơ dưới đây sử dụng thang điểm **minh họa nội bộ**; không phải bằng chứng rằng hệ thống thực tế có rủi ro đúng các con số này.

~~~yaml
risk_id: RISK-LEARNER-ACCESS-001
title: "Truy cập trái phép dữ liệu học viên giữa các lớp"
scope:
  service: "Learning Platform API"
  environment: "production"
  assets: ["learner-records", "class-management-api"]
objective: "Chỉ người được phân quyền mới truy cập hồ sơ của lớp"
scenario:
  event: "Giảng viên thay classId trong request để truy cập lớp khác"
  weakness: "Backend có thể thiếu kiểm tra quyền ở mức đối tượng"
  impact: "Lộ dữ liệu học tập và ảnh hưởng nghĩa vụ bảo vệ dữ liệu"
inherent_risk_example:
  likelihood: 4
  impact: 4
  score: 16
existing_controls:
  - "SSO/MFA cho tài khoản tương tác"
  - "Authentication gateway"
evidence_gaps:
  - "Chưa có đầy đủ negative authorization tests"
  - "Chưa đối chiếu quyền thực tế theo lớp trên production"
current_assessment: "Chưa đủ bằng chứng để xác nhận residual risk"
treatment: "Mitigate"
actions:
  - "Bổ sung server-side object authorization và negative tests"
  - "Kiểm tra audit logs truy cập và cảnh báo bất thường"
owner: "Learning Platform Risk Owner"
control_owner: "Backend API Team"
assessor: "Security Assurance"
approval: "Theo cơ chế phê duyệt rủi ro của tổ chức"
reassessment_trigger: "Release thay đổi authorization hoặc quyền theo lớp"
~~~

### 11.2. Risk register khác danh sách lỗ hổng thế nào?

Một danh sách scanner có thể xuất ra hàng trăm CVE, nhưng risk register thường tập trung vào **kịch bản có ý nghĩa đối với mục tiêu**, nhóm các phát hiện liên quan khi phù hợp và làm rõ quyết định xử lý.

Ví dụ cùng một lỗ hổng của một thư viện có thể xuất hiện ở nhiều service. Nếu một service chỉ xử lý dữ liệu không nhạy cảm trong mạng cô lập, còn service khác public và có token quản trị, cách ưu tiên có thể khác. Ngược lại, một rủi ro truy cập dữ liệu chéo tenant có thể bắt nguồn từ **thiết kế phân quyền sai**, không hề có CVE công khai.

## 12. Từ risk đến security requirements và controls

Một risk assessment hữu ích phải tạo hành động có thể kiểm chứng. Chỉ số điểm không tự giảm rủi ro. Xây dựng đường truy vết:

~~~mermaid
flowchart TD
    A["Business objective và tài sản"] --> B["Risk scenario"]
    B --> C["Likelihood, impact, uncertainty"]
    C --> D["Lựa chọn xử lý và risk owner"]
    D --> E["Security requirement kiểm chứng được"]
    E --> F["Control owner và triển khai"]
    F --> G["Test, telemetry, audit evidence"]
    G --> H{"Control đạt tiêu chí?"}
    H -->|"Có, bằng chứng đủ"| I["Đánh giá residual risk và báo cáo"]
    H -->|"Không hoặc thiếu bằng chứng"| J["Finding, kế hoạch và retest"]
    J --> F
    I --> K["Theo dõi biến động và đánh giá lại"]
    K --> B
~~~

Ví dụ risk “giảng viên đọc dữ liệu ngoài lớp được giao” tạo yêu cầu:

> Mọi request đọc/xuất dữ liệu học viên phải được xác thực và **ủy quyền phía server đối với đúng lớp, học viên và hành động**; truy cập ngoài quyền phải bị từ chối và có log phục vụ điều tra theo chính sách dữ liệu.

Control và kiểm thử tương ứng:

| Thành phần | Ví dụ thực hiện | Bằng chứng kiểm chứng |
|---|---|---|
| **Preventive control** | Kiểm tra role và quyền theo đối tượng ngay tại API/service | Unit/integration tests, code review, kết quả thử từ chối truy cập |
| **Detective control** | Log truy cập nhạy cảm và cảnh báo hành vi xuất dữ liệu bất thường | Log mẫu đã được kiểm tra, thử rule, alert/ticket |
| **Responsive control** | Thu hồi session/token và cô lập endpoint khi nghi lộ dữ liệu | Runbook, kết quả diễn tập, incident records |
| **Recovery/corrective control** | Sửa logic phân quyền, kiểm tra hệ thống liên quan, retest | Change record, kết quả test ở build/release đã triển khai |
| **Governance control** | Quy định ownership, release gate, hạn khắc phục và ngoại lệ | Chính sách, phê duyệt, control register, risk decision |

Không phải mọi control đều giảm cùng một yếu tố. Authorization đúng có thể giảm khả năng sự kiện truy cập trái phép thành công; audit log và phản ứng nhanh chủ yếu giúp **phát hiện, điều tra và hạn chế tác động**, nhưng không xóa sự cố đã xảy ra.

## 13. Ví dụ xuyên suốt: rủi ro ở API xuất dữ liệu của nền tảng học

Giả định nền tảng học có endpoint:

~~~http
GET /api/classes/42/learners/export
Authorization: Bearer <access-token>
~~~

Một giảng viên chỉ được quản lý lớp 42. API cũ kiểm tra token hợp lệ nhưng không kiểm tra request có thuộc lớp được cấp quyền hay không. Người dùng thay số lớp thành 43 để thử lấy file.

**Bước 1 — Mô tả rủi ro:** người dùng có tài khoản hợp lệ có thể truy cập kết quả học tập ngoài phạm vi, dẫn đến lộ dữ liệu cá nhân và sai lệch kỳ vọng của chủ thể dữ liệu.

**Bước 2 — Bối cảnh:** endpoint có thể truy cập từ Internet bởi người dùng đã đăng nhập; dữ liệu xuất là tập hợp bản ghi học tập; có thể nhiều lớp bị ảnh hưởng. Cần xác định số lượng thực tế và loại thông tin trước khi khẳng định impact.

**Bước 3 — Đánh giá hiện trạng:** SSO cho biết *ai* đăng nhập, nhưng chưa chứng minh *có quyền truy cập tập dữ liệu cụ thể hay không*. Nếu không có negative test và log truy cập liên quan, thiếu bằng chứng về control quan trọng.

**Bước 4 — Xử lý:** bổ sung kiểm tra quyền ở tầng service dựa trên danh tính, hành động và đối tượng; bổ sung test cho giảng viên khác lớp, giảng viên bị thu hồi quyền, session hết hạn, lớp đã lưu trữ và các đường export khác.

**Bước 5 — Kiểm chứng:** thử truy cập hợp lệ và không hợp lệ trong môi trường kiểm soát; đối chiếu cấu hình production; kiểm tra log có định danh, thời gian và đối tượng, nhưng không ghi token hoặc toàn bộ nội dung nhạy cảm.

**Bước 6 — Kết luận:** chỉ hạ mức rủi ro khi có đủ bằng chứng control đã triển khai và hoạt động. Nếu còn một đường export khác chưa kiểm thử, phải nêu giới hạn và tiếp tục đánh giá, không báo cáo “đã bảo mật hoàn toàn”.

### 13.1. Ví dụ test case bảo mật

| ID | Người gọi | Hành động | Kỳ vọng |
|---|---|---|---|
| AUTH-01 | Giảng viên lớp 42 | Xuất học viên lớp 42 | Cho phép theo quyền và log thích hợp |
| AUTH-02 | Giảng viên lớp 42 | Xuất học viên lớp 43 | Từ chối, không trả dữ liệu lớp 43 |
| AUTH-03 | Giảng viên đã bị thu hồi quyền | Xuất học viên lớp 42 | Từ chối theo trạng thái quyền hiện tại |
| AUTH-04 | Người chưa đăng nhập | Xuất dữ liệu lớp bất kỳ | Từ chối theo chính sách xác thực |
| AUTH-05 | Tài khoản quản trị có quyền hạn được phê duyệt | Xuất trong phạm vi được cấp | Cho phép có audit phù hợp, không mặc định mở mọi lớp |

Các test case này chỉ là **một phần** của kiểm chứng. Cần kiểm tra quyền trên các tuyến API liên quan, cache, batch job, object storage và cơ chế URL tải file nếu chúng nằm trong phạm vi rủi ro.

### 13.2. Dữ liệu vận hành làm thay đổi đánh giá risk

Giả sử sau khi vá authorization, nhóm SOC phát hiện nhiều yêu cầu bị từ chối từ cùng một danh tính. Đây có thể là dấu hiệu thử truy cập chéo lớp; nó ảnh hưởng đến đánh giá về **threat activity** và khả năng phát hiện. Nhưng số lượng 403 tăng có thể do lỗi client hoặc thử nghiệm hợp lệ. Cần điều tra nguyên nhân trước khi kết luận đã có tấn công.

Một tuần sau, một ứng dụng mobile mới sử dụng tuyến export khác không qua middleware kiểm tra quyền. Đây là **trigger tái đánh giá**: phạm vi đã thay đổi, kết luận assurance cũ có thể không còn bao phủ đường truy cập mới.

## 14. Risk trong security assurance: bằng chứng thay đổi kết luận thế nào?

Risk assessment là **đánh giá có phương pháp và giả định**, không phải lời khẳng định khách quan tuyệt đối. Security assurance đặt thêm câu hỏi: **Bằng chứng nào đủ để tin rằng control đang giảm rủi ro như dự kiến?**

### 14.1. Ba lớp xác minh control

1. **Design effectiveness:** Control về mặt thiết kế có giải quyết đúng risk scenario không? Ví dụ role check ở gateway có giải quyết được truy cập chéo lớp hay phải kiểm tra từng đối tượng ở backend?
2. **Implementation effectiveness:** Control có tồn tại và áp dụng đúng vào môi trường production, tất cả tài khoản và các đường truy cập thuộc phạm vi không?
3. **Operating effectiveness:** Control có vận hành nhất quán trong kỳ đánh giá, kể cả thay đổi, ngoại lệ và ca sử dụng thực tế không?

Một ảnh chụp cấu hình chỉ chứng minh phần trạng thái ở một thời điểm. Với claim về hiệu quả vận hành, cần kết hợp **lịch sử thay đổi, test, log, mẫu giao dịch, bằng chứng phản ứng và kết quả retest** phù hợp.

### 14.2. Chất lượng evidence

Bằng chứng nên được đánh giá theo:

- **Relevance:** chứng minh đúng risk/control/claim nào?
- **Scope:** có bao phủ các tài sản, luồng dữ liệu, tài khoản và môi trường liên quan?
- **Freshness/period:** dữ liệu phản ánh thời điểm/kỳ nào; đã có thay đổi nào làm nó hết giá trị?
- **Provenance/integrity:** ai/điều gì tạo evidence, dấu thời gian, phiên bản, có khả năng chỉnh sửa trái phép không?
- **Completeness/representativeness:** có dữ liệu đầy đủ hoặc phương pháp chọn mẫu phù hợp?
- **Repeatability:** người đánh giá khác có thể đối chiếu nguồn hoặc lặp lại phép thử không?

**Ví dụ:** “Không phát hiện truy cập trái phép” không đủ để suy ra rủi ro đã thấp nếu hệ thống không ghi log một tuyến export. Đánh giá đúng là **chưa đủ bằng chứng để kết luận** về một phần kịch bản.

### 14.3. Claim–Argument–Evidence cho một rủi ro

**Claim:** “Trong phạm vi các API export production đã xác định, người dùng không thể xuất dữ liệu học viên ngoài quyền lớp được cấp theo tiêu chí kiểm thử”.

**Argument:** Các tuyến export áp dụng cùng kiểm tra quyền theo đối tượng; test bao phủ quyền hợp lệ, không hợp lệ và thay đổi quyền; runtime được cấu hình theo bản phát hành đã test; audit log hỗ trợ phát hiện sai lệch.

**Evidence:** Danh sách endpoint thuộc phạm vi, code/policy đã phê duyệt, kết quả integration/negative tests theo build, cấu hình môi trường, log và kết quả đánh giá các ngoại lệ.

**Limitations:** Chưa bao gồm một nhà cung cấp báo cáo bên thứ ba hoặc kịch bản đã ghi rõ. Nếu chưa đủ bằng chứng, claim phải được thu hẹp hoặc chưa thể xác nhận.

## 15. Risk liên tục thay đổi theo vòng đời hệ thống

Một lần chấm điểm rủi ro tại thời điểm thiết kế là cần thiết nhưng chưa đủ. Sau đó xuất hiện tính năng mới, dữ liệu mới, thay đổi quyền, phụ thuộc mới, sự cố và lỗ hổng mới.

| Giai đoạn | Đầu vào xác định risk | Hoạt động assurance tương ứng |
|---|---|---|
| Thiết kế | Kiến trúc, data flow, tài sản và threat model | Xác định risk scenario, yêu cầu và tiêu chí control |
| Phát triển | Thay đổi code, thư viện, luồng xác thực | Review security, SAST/dependency check, test authorization |
| Build/release | Cấu hình IaC, secret, artifact, pipeline | Policy check, release evidence, kiểm tra trạng thái deploy |
| Vận hành | Log, hành vi người dùng, tài khoản, lỗ hổng, sự cố | Monitoring, access review, vulnerability management |
| Khôi phục/sự cố | Dữ liệu thực về tác động, nguyên nhân và hiệu quả phản ứng | Incident review, restore test, cập nhật risk/control |
| Audit/cải tiến | Finding, ngoại lệ, mục tiêu chưa được chứng minh | CAPA, retest, cập nhật residual risk và risk register |

### 15.1. Các trigger cần đánh giá lại risk

- Thêm môi trường production, loại dữ liệu nhạy cảm, tenant hoặc nhà cung cấp mới.
- Thay identity provider, gateway, network policy, IAM role hoặc cơ chế chia sẻ dữ liệu.
- Một lỗ hổng hoặc kỹ thuật khai thác mới ảnh hưởng đến thành phần trong phạm vi.
- Phát hiện control không hoạt động, log bị thiếu hoặc backup restore thất bại.
- Xảy ra incident hoặc near miss; xuất hiện dữ liệu thực tế trái với giả định cũ.
- Thay đổi mục tiêu kinh doanh, chính sách, hợp đồng, nghĩa vụ compliance hoặc risk appetite.
- Một ngoại lệ có thời hạn đã đến kỳ rà soát hoặc một finding không được khắc phục đúng hạn.

Tái đánh giá không nhất thiết có nghĩa bắt đầu từ số 0; tập trung cập nhật phần **thay đổi**, xác minh những control liên quan và điều chỉnh kết luận theo bằng chứng mới.

## 16. Những sai lầm thường gặp khi hiểu risk

**“Có lỗ hổng nghiêm trọng thì chắc chắn risk cao nhất.”** Không tự động. Cần đánh giá đường phơi bày, điều kiện khai thác, tài sản, hậu quả và control hiện có; một lỗ hổng severity thấp hơn nhưng dễ khai thác trên tài sản trọng yếu có thể cần ưu tiên hơn.

**“Risk là sự cố đã xảy ra.”** Không. Risk nói về sự bất định đối với mục tiêu, nên cần quản lý trước khi incident xảy ra. Incident cung cấp bằng chứng mới để cập nhật đánh giá.

**“Không có incident nghĩa là risk thấp.”** Có thể hệ thống chưa bị tấn công hoặc chưa phát hiện được sự kiện. Cần kiểm chứng coverage và năng lực detection.

**“Điểm số 20/25 có nghĩa xác suất 80%.”** Không. Với ma trận định tính, 20 là kết quả của quy ước chấm điểm, không phải xác suất được đo.

**“Đã mua công cụ là đã giảm risk.”** Chỉ khi công cụ/control được cấu hình đúng, bao phủ đường rủi ro và vận hành có hiệu quả thì mới có cơ sở kết luận rủi ro giảm.

**“Accept risk nghĩa là không cần làm gì nữa.”** Chấp nhận phải có thẩm quyền, lý do, phạm vi, điều kiện và lịch đánh giá lại; vẫn phải tuân thủ các yêu cầu bắt buộc.

**“Tất cả rủi ro phải loại bỏ hoàn toàn.”** Nhiều hoạt động kinh doanh vẫn có residual risk. Mục tiêu là quản lý rủi ro trong giới hạn được quyết định đúng thẩm quyền và chứng minh control đủ hiệu quả, không tuyên bố rủi ro bằng 0.

**“Risk owner cũng chính là người sửa mọi lỗi kỹ thuật.”** Risk owner chịu trách nhiệm về phương án xử lý, còn control owner và các team triển khai chịu trách nhiệm thực hiện biện pháp cụ thể; vai trò cần phân công rõ.

## 17. Bài tập tự đánh giá

### Tình huống A – Tìm risk scenario

Nền tảng học trực tuyến sử dụng object storage để lưu bài nộp. Một nhóm vận hành phát hiện bucket đang cho phép một nhóm tài khoản dịch vụ có quyền đọc quá rộng. Chưa thấy dấu hiệu dữ liệu bị tải xuống trái phép.

Hãy trả lời:

1. Tài sản và mục tiêu bảo mật ở đây là gì?
2. Đâu là **điểm yếu**, đâu là **risk scenario**, đâu là một **incident đã được xác nhận**?
3. Yếu tố nào cần biết thêm để đánh giá likelihood và impact?
4. Control nào giảm khả năng truy cập trái phép, control nào giúp phát hiện và điều tra?
5. Cần bằng chứng gì để có thể kết luận quyền đã được thu hẹp hiệu quả?
6. Ai là risk owner, control owner và người đánh giá theo cơ cấu bạn giả định?

**Định hướng:** Quyền đọc quá rộng là điểm yếu/điều kiện làm tăng phơi bày; rủi ro là khả năng một tài khoản dịch vụ bị lạm dụng hoặc chiếm quyền truy cập bài nộp ngoài phạm vi, dẫn tới lộ dữ liệu. Chưa có dấu hiệu tải xuống không đồng nghĩa chắc chắn không có sự cố. Cần xác minh quyền, lịch sử truy cập, phạm vi dữ liệu, tính đầy đủ của log, thay đổi policy và test lại. Risk owner chịu trách nhiệm quyết định phương án; team quản lý storage/IAM vận hành control; assessor đối chiếu evidence.

### Tình huống B – Hiểu sai risk score

Hai kịch bản được chấm theo ma trận nội bộ:

| Kịch bản | Likelihood (1–5) | Impact (1–5) | Score |
|---|---:|---:|---:|
| A. API công khai có thể lộ một lượng dữ liệu nhỏ | 4 | 2 | 8 |
| B. Mất toàn bộ khóa giải mã bản sao lưu thiết yếu | 2 | 5 | 10 |

Một quản lý kết luận: “B có score 10 nên chắc chắn phải xử lý trước A, không cần xem thêm”.

Hãy phân tích vì sao cách kết luận này còn thiếu: cả hai loại tác động có cùng tiêu chí không, mức 2 và 4 dựa trên bằng chứng nào, có ràng buộc phục hồi hoặc nghĩa vụ đặc biệt nào, risk appetite ra sao và phương án giảm rủi ro có chi phí/hiệu quả thế nào?

**Định hướng:** Score giúp sàng lọc, nhưng ưu tiên cuối cùng cần xem độ bất định, mức phơi bày, hậu quả nghiêm trọng, nghĩa vụ và khả năng xử lý. Có thể cần ưu tiên cả hai theo các biện pháp khác nhau. Không nên suy diễn mức chênh lệch 10 so với 8 thành xác suất hoặc tỷ lệ thiệt hại.

### Tình huống C – Viết mini risk register

Một ứng dụng Java có chức năng reset mật khẩu. Tổ chức chưa kiểm tra liệu reset token có bị sử dụng lại hoặc tồn tại quá lâu không.

Hãy viết hồ sơ gồm: **risk statement; tài sản/mục tiêu; threat event; assumptions; likelihood/impact (nếu đủ cơ sở); existing controls; evidence gaps; treatment; risk owner; control owner; test; thời hạn và trigger tái đánh giá.**

**Gợi ý:** Rủi ro có thể là kẻ có reset token sử dụng token ngoài thời gian hoặc phạm vi dự kiến để chiếm tài khoản. Test cần xác nhận TTL, one-time-use, invalidation khi thay mật khẩu và xử lý token khi retry; bằng chứng cần kết quả test trên phiên bản triển khai, cấu hình và log phù hợp. Không kết luận mức residual risk thấp khi chưa thực hiện phép thử.

## 18. Ghi nhớ

- **Risk là ảnh hưởng của sự bất định lên mục tiêu**; trong security, trọng tâm là những kịch bản có thể gây tổn thất về dữ liệu, dịch vụ và hoạt động.
- **Risk khác threat, vulnerability, finding và incident**: risk luôn cần bối cảnh về tài sản, điều kiện, khả năng xảy ra và hậu quả.
- **Likelihood và impact** giúp đánh giá mức độ, nhưng ma trận điểm số chỉ là công cụ; cần công bố giả định và mức tin cậy của bằng chứng.
- **Inherent risk** mô tả rủi ro trước khi xét control, **residual risk** là rủi ro sau khi xét hiệu quả control; kế hoạch triển khai chưa phải bằng chứng giảm rủi ro.
- Risk phải có **owner, phương án xử lý, tiêu chí kiểm chứng, bằng chứng và trigger tái đánh giá**.
- Trong security assurance, quyết định về rủi ro cần được nối thành chuỗi **risk → requirement → control → test → evidence → residual risk → quyết định và cải tiến liên tục**.

