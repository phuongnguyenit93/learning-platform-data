# Lựa chọn ca theo tần suất chạy, độ ổn định và giá trị phản hồi

Tự động hóa kiểm thử có giá trị khi giúp nhóm nhận được bằng chứng chất lượng nhanh, lặp lại và đủ tin cậy trong suốt quá trình phát triển. Tuy nhiên, không phải ca kiểm thử nào cũng nên tự động hóa. Một ca chỉ chạy vài lần trong năm, phụ thuộc môi trường khó kiểm soát hoặc tạo ra kết quả khó chẩn đoán có thể tốn nhiều công xây dựng và bảo trì hơn lợi ích mà nó mang lại.

Khi lựa chọn ứng viên, nhóm cần xem xét ba yếu tố chính: **tần suất chạy**, **độ ổn định** và **giá trị phản hồi**. Tần suất cho biết kiểm thử được thực hiện thường xuyên đến đâu và có thể tiết kiệm bao nhiêu công sức lặp lại. Độ ổn định cho biết kết quả có đáng tin cậy và có thể tái hiện không. Giá trị phản hồi thể hiện kiểm thử giúp phát hiện rủi ro hoặc lỗi quan trọng, giải thích kết quả và hỗ trợ quyết định nhanh đến mức nào.

Ba yếu tố cần được cân nhắc cùng chi phí tạo, vận hành và bảo trì. Mục tiêu là chọn các ca đem lại tín hiệu chất lượng có ích ở đúng thời điểm, không chạy theo số lượng ca tự động hoặc tỷ lệ tự động hóa.

## 1. Vì sao cần chọn lọc ca kiểm thử để tự động hóa?

Tự động hóa có chi phí ban đầu và chi phí duy trì. Nhóm cần thiết kế mã kiểm thử, dữ liệu, môi trường, cơ chế chạy, báo cáo, xử lý lỗi và cập nhật khi sản phẩm thay đổi. Một ca tự động hóa kém có thể thất bại ngẫu nhiên, tạo cảnh báo giả, kéo dài pipeline hoặc buộc người phát triển mất thời gian điều tra.

Ngược lại, một ca kiểm thử phù hợp có thể chạy sau mỗi thay đổi, xác nhận hành vi cốt lõi và phát hiện lỗi trước khi thay đổi được tích hợp hoặc phát hành. Khi cùng một kiểm tra phải thực hiện nhiều lần, tự động hóa còn giúp giảm thao tác thủ công và tạo kết quả nhất quán.

Việc lựa chọn có chủ đích giúp:

- Tập trung đầu tư vào những kiểm tra có khả năng được sử dụng thường xuyên.
- Phát hiện sớm lỗi có tác động lớn đến người dùng hoặc nghiệp vụ.
- Giữ tín hiệu CI đáng tin cậy, giảm cảnh báo giả và thời gian điều tra.
- Tránh tự động hóa các kịch bản thay đổi liên tục khi yêu cầu chưa ổn định.
- Cân bằng phạm vi kiểm thử, tốc độ phản hồi và chi phí bảo trì.
- Xác định rõ phần nào nên tự động, phần nào phù hợp kiểm thử thủ công hoặc thăm dò.

Tự động hóa là một quyết định về đầu tư. Một ca có thể rất quan trọng nhưng chưa phù hợp để tự động hóa ngay nếu chưa có oracle đáng tin cậy, dữ liệu ổn định hoặc môi trường có thể tái tạo. Trong trường hợp đó, nhóm có thể cải thiện điều kiện trước, hoặc duy trì kiểm thử thủ công có mục tiêu trong thời gian chuyển tiếp.

## 2. Tần suất chạy: kiểm tra nào được lặp lại nhiều nhất?

Tần suất chạy mô tả số lần một ca kiểm thử cần được thực hiện trong một khoảng thời gian hoặc tại các điểm kiểm tra của quy trình phát triển. Ca được chạy mỗi khi tạo pull request, mỗi lần tích hợp hoặc sau mỗi lần triển khai thường có cơ hội tiết kiệm công sức và phát hiện lỗi sớm cao hơn ca chỉ chạy trước một đợt phát hành lớn.

Khi đánh giá tần suất, cần xem xét cả:

- **Tần suất của quy trình:** Ca được chạy mỗi commit, mỗi pull request, mỗi đêm, mỗi tuần hay chỉ theo mốc phát hành?
- **Tần suất thay đổi:** Thành phần hoặc luồng nghiệp vụ có thường xuyên được sửa đổi không?
- **Mức sử dụng của tính năng:** Người dùng có thường xuyên thực hiện hành vi đó không?
- **Tần suất rủi ro xuất hiện:** Lỗi ở khu vực đó có thường phát sinh sau các thay đổi hoặc tích hợp không?
- **Số môi trường cần xác minh:** Một ca có cần chạy trên nhiều trình duyệt, phiên bản, cấu hình hoặc tenant không?

Một ca được chạy thường xuyên có thể đem lại lợi ích tích lũy lớn. Ví dụ, kiểm tra đăng nhập và tạo đơn hàng ở mỗi pull request có thể phát hiện hồi quy sớm hơn việc đợi đến cuối sprint mới chạy thủ công.

Tuy nhiên, tần suất cao không tự động làm một ca trở thành ứng viên tốt. Nếu ca đó rất chậm, không ổn định hoặc chỉ xác nhận một chi tiết ít rủi ro, chi phí chạy và bảo trì có thể vượt lợi ích. Tần suất cần được cân nhắc cùng giá trị của thông tin mà ca cung cấp.

### 2.1. Ước lượng tần suất bằng dữ liệu thực tế

Không nên chỉ dựa vào cảm nhận rằng “ca này quan trọng nên chắc sẽ chạy thường xuyên”. Hãy xem lịch sử pipeline, lịch phát hành, lịch kiểm thử thủ công, tần suất thay đổi mã và dữ liệu sử dụng tính năng nếu có.

Ví dụ:

| Nhóm ca kiểm thử | Nhịp chạy dự kiến | Tín hiệu về tần suất |
|---|---|---|
| Kiểm tra khởi động và đăng nhập | Mỗi pull request hoặc build chính | Nhiều thay đổi có thể ảnh hưởng đến xác thực và truy cập |
| Kiểm tra tính toán phí | Mỗi thay đổi liên quan đến giá, thuế hoặc đơn hàng; hồi quy theo lịch | Quy tắc nghiệp vụ quan trọng và có thể được sửa thường xuyên |
| Kiểm tra báo cáo cuối kỳ | Theo lịch nghiệp vụ hoặc trước mỗi kỳ chốt | Tần suất thấp hơn nhưng có thời điểm bắt buộc và tác động lớn |
| Kiểm tra nâng cấp trình duyệt | Theo lịch cập nhật nền tảng và trước phát hành | Phụ thuộc chu kỳ phiên bản của nền tảng |
| Kiểm thử thăm dò trải nghiệm | Khi có thay đổi lớn hoặc cần điều tra | Tần suất thay đổi theo nhu cầu học hỏi và rủi ro |

Tần suất có thể thay đổi theo giai đoạn. Một ca từng chạy mỗi ngày có thể ít cần thiết sau khi tính năng ổn định; một ca hiếm có thể trở nên thường xuyên khi nhóm thay đổi thành phần liên quan. Nên rà soát lựa chọn định kỳ thay vì giữ nguyên quyết định tự động hóa mãi mãi.

## 3. Độ ổn định: kết quả có đáng tin cậy và tái hiện được không?

Độ ổn định thể hiện khả năng một ca kiểm thử cho kết quả nhất quán khi sản phẩm không thay đổi và điều kiện thực thi tương đương. Một ca ổn định thường có đầu vào, dữ liệu, môi trường và kết quả mong đợi được kiểm soát rõ.

Các yếu tố hỗ trợ độ ổn định:

- **Điều kiện đầu vào rõ:** Dữ liệu và trạng thái ban đầu được chuẩn bị có chủ đích.
- **Oracle đáng tin cậy:** Kết quả mong đợi được xác định từ yêu cầu, quy tắc hoặc nguồn độc lập phù hợp.
- **Môi trường có thể tái tạo:** Phiên bản dịch vụ, cấu hình và phụ thuộc được kiểm soát.
- **Không phụ thuộc thứ tự:** Ca có thể chạy độc lập và không dựa vào kết quả của ca khác.
- **Quản lý thời gian và đồng bộ:** Không phụ thuộc vào sleep cố định, đồng hồ thực hoặc lịch xử lý không được kiểm soát.
- **Tài nguyên riêng:** Dữ liệu, tài khoản, tệp và dịch vụ giả lập không bị ca khác ghi đè.
- **Điều kiện chờ hợp lý:** Ca chờ sự kiện hoặc trạng thái thực tế thay vì giả định một khoảng thời gian luôn đủ.

Một ca không ổn định có thể lúc đạt, lúc thất bại dù mã sản phẩm không thay đổi. Hiện tượng này thường được gọi là flaky test. Nguyên nhân có thể nằm ở kiểm thử, môi trường, dữ liệu, hạ tầng hoặc sản phẩm có hành vi phi xác định.

### 3.1. Nhận diện nguyên nhân không ổn định

Các nguyên nhân phổ biến gồm:

- Chờ một khoảng thời gian cố định trong khi tác vụ bất đồng bộ chưa hoàn tất.
- Dữ liệu dùng chung bị nhiều ca thay đổi đồng thời.
- Phụ thuộc dịch vụ bên ngoài có độ trễ hoặc giới hạn tốc độ biến động.
- Đồng hồ, múi giờ, ngày hiện tại hoặc số ngẫu nhiên làm thay đổi kết quả.
- Kiểm thử phụ thuộc thứ tự thực thi hoặc trạng thái còn sót từ lần chạy trước.
- Tài nguyên CI không đồng đều, chẳng hạn CPU quá tải hoặc dung lượng bộ nhớ thiếu.
- Selector giao diện phụ thuộc cấu trúc hoặc nội dung thường xuyên thay đổi.
- Hệ thống có race condition hoặc lỗi đồng bộ thực sự.

Không nên mặc định mọi flaky test đều là lỗi của bộ kiểm thử. Một ca dao động có thể đang phát hiện lỗi cạnh tranh hoặc vấn đề độ tin cậy trong sản phẩm. Cần điều tra bằng cách chạy lại có kiểm soát, lưu log và so sánh điều kiện thay vì tắt ca ngay.

### 3.2. Cải thiện độ ổn định trước khi mở rộng tự động hóa

Có thể cải thiện độ ổn định bằng cách:

1. Tạo dữ liệu riêng cho mỗi lần chạy và dọn dẹp theo quy tắc rõ ràng.
2. Dùng đồng hồ giả, seed cố định hoặc bộ mô phỏng khi mục tiêu không phải kiểm tra tính ngẫu nhiên của phụ thuộc.
3. Chờ điều kiện cụ thể như phần tử xuất hiện, trạng thái hoàn tất hoặc message được nhận.
4. Đặt timeout có giới hạn và cung cấp thông tin chẩn đoán khi hết thời gian.
5. Cô lập tài nguyên giữa các worker chạy song song.
6. Thay dịch vụ không liên quan bằng stub hoặc fake ở kiểm thử cấp thấp; vẫn giữ kiểm thử tích hợp để xác nhận ranh giới thật.
7. Làm rõ expected result và loại bỏ phụ thuộc vào trạng thái môi trường không được ghi nhận.

Nếu chưa thể ổn định ngay, hãy phân loại ca là cần điều tra hoặc chỉ chạy trong một nhóm thử nghiệm có kiểm soát. Không nên để ca thất bại ngẫu nhiên chặn mọi thay đổi mà không có người phụ trách và thời hạn xử lý.

## 4. Giá trị phản hồi: kiểm thử giúp nhóm quyết định điều gì?

Giá trị phản hồi là mức độ hữu ích của thông tin mà một ca kiểm thử cung cấp cho người phát triển, QA hoặc người ra quyết định. Một ca có giá trị cao thường phát hiện lỗi có ý nghĩa, cho biết hành vi nào không đạt và giúp nhóm xác định bước tiếp theo.

Có thể đánh giá giá trị phản hồi theo các khía cạnh:

- **Mức độ rủi ro được bao phủ:** Ca kiểm tra hành vi có thể gây mất dữ liệu, sai giao dịch, lộ thông tin hoặc gián đoạn dịch vụ không?
- **Khả năng phát hiện lỗi:** Ca có đủ nhạy để phát hiện sai lệch quan trọng thay vì chỉ kiểm tra một trạng thái bề mặt không?
- **Tính hành động:** Khi thất bại, kết quả có cho biết bước, dữ liệu hoặc điều kiện liên quan không?
- **Tốc độ phản hồi:** Kết quả có đến đủ sớm để sửa lỗi khi thay đổi còn nhỏ không?
- **Phạm vi tác động:** Ca có xác nhận một hành vi cốt lõi hoặc ranh giới mà nhiều thành phần phụ thuộc không?
- **Khả năng truy vết:** Kết quả có liên kết được với yêu cầu, rủi ro, build và bằng chứng không?
- **Tính bổ sung:** Ca có cung cấp tín hiệu mới hay lặp lại điều đã được nhiều ca khác xác nhận?

Một ca kiểm tra mã HTTP 200 có thể chạy rất nhanh và ổn định, nhưng giá trị phản hồi thấp nếu không xác nhận nội dung, trạng thái dữ liệu hoặc kết quả nghiệp vụ. Một ca xác nhận tiền đã trừ đúng một lần, đơn hàng được cập nhật nhất quán và người dùng nhận được trạng thái chính xác thường có giá trị cao hơn đối với luồng thanh toán.

### 4.1. Giá trị phản hồi và khả năng chẩn đoán

Một ca phát hiện được lỗi nhưng chỉ báo “workflow failed” có thể buộc nhóm điều tra qua nhiều dịch vụ. Giá trị của ca sẽ cao hơn nếu có mã đơn hàng, mã tương quan, bước thất bại, kết quả mong đợi và trạng thái thực tế.

Khả năng chẩn đoán được cải thiện khi:

- Tên ca nêu hành vi cần xác nhận.
- Dữ liệu đầu vào và trạng thái ban đầu được lưu.
- Thông báo lỗi hiển thị giá trị mong đợi và thực tế.
- Log hoặc trace liên kết được các bước xuyên dịch vụ.
- Ca có thể chạy riêng để xác minh nguyên nhân.
- Kết quả phân biệt lỗi sản phẩm với lỗi môi trường hoặc điều kiện bị chặn.

Một bộ kiểm thử có nhiều ca nhưng phần lớn chỉ trả về lỗi chung có thể tạo ra nhiều tín hiệu mà ít thông tin hành động. Khi chọn ứng viên, cần tính cả thời gian điều tra sau khi ca thất bại.

## 5. Cân bằng ba yếu tố với chi phí tự động hóa

Tần suất, độ ổn định và giá trị phản hồi không phải ba điểm số độc lập có thể cộng máy móc. Chúng là các góc nhìn giúp nhóm đánh giá lợi ích dự kiến và chi phí vòng đời.

Một mô hình suy nghĩ đơn giản:

\[
\text{Giá trị ròng} \approx \text{Lợi ích lặp lại} + \text{Giảm rủi ro} - \text{Chi phí vòng đời}
\]

Trong đó:

- **Lợi ích lặp lại** phụ thuộc tần suất chạy, công sức thủ công được tiết kiệm và thời điểm nhận phản hồi.
- **Giảm rủi ro** phụ thuộc mức độ quan trọng của hành vi, khả năng phát hiện lỗi và độ tin cậy của bằng chứng.
- **Chi phí vòng đời** gồm thiết kế, triển khai, dữ liệu, môi trường, chạy, phân tích, sửa và bảo trì ca kiểm thử.

Không cần chuyển mọi yếu tố thành một con số chính xác. Nếu dùng thang điểm để sắp xếp, hãy định nghĩa mức điểm, nêu căn cứ và xem điểm như công cụ thảo luận. Một ca có rủi ro an toàn hoặc tài chính rất cao có thể cần được tự động hóa dù tần suất chạy thấp.

### 5.1. Ma trận đánh giá ứng viên

| Tần suất chạy | Độ ổn định | Giá trị phản hồi | Hướng xử lý gợi ý |
|---|---|---|---|
| Cao | Cao | Cao | Ưu tiên tự động hóa và đưa vào pipeline phù hợp |
| Cao | Cao | Thấp | Xem xét giữ nếu chi phí thấp; loại trùng lặp hoặc tăng nội dung kiểm tra |
| Cao | Thấp | Cao | Ưu tiên điều tra và ổn định trước; có thể chạy có kiểm soát trong thời gian khắc phục |
| Cao | Thấp | Thấp | Không mở rộng tự động hóa; xem lại mục tiêu và thiết kế ca |
| Thấp | Cao | Cao | Cân nhắc tự động hóa nếu rủi ro lớn hoặc ca tốn công thực hiện thủ công |
| Thấp | Cao | Thấp | Thường để thủ công, chạy theo nhu cầu hoặc loại bỏ nếu không còn hữu ích |
| Thấp | Thấp | Cao | Cải thiện điều kiện, dùng kiểm thử thủ công/thăm dò hoặc tự động hóa ở mức phù hợp |
| Thấp | Thấp | Thấp | Ưu tiên thấp; xem xét bỏ hoặc thiết kế lại |

Ma trận là gợi ý, không phải luật cứng. Ví dụ, một kiểm tra khôi phục dữ liệu có thể chỉ chạy trước một đợt phát hành lớn nhưng hậu quả nếu lỗi rất nghiêm trọng. Giá trị phản hồi và mức rủi ro có thể khiến nó vẫn là ứng viên ưu tiên.

### 5.2. Ước lượng lợi ích và chi phí

Có thể ước lượng theo chu kỳ:

| Thành phần | Câu hỏi |
|---|---|
| Chi phí thủ công hiện tại | Mỗi lần chạy cần bao nhiêu thời gian và kỹ năng? |
| Tần suất | Trong một tháng hoặc một quý, ca sẽ được chạy bao nhiêu lần? |
| Chi phí tự động hóa ban đầu | Cần bao nhiêu công để thiết kế, viết, dữ liệu và môi trường? |
| Chi phí bảo trì | Khi giao diện, API hoặc quy tắc thay đổi, ca cần sửa bao nhiêu? |
| Chi phí thất bại giả | Mỗi lần flaky test thất bại cần bao nhiêu thời gian điều tra? |
| Giá trị phát hiện | Lỗi mà ca có thể phát hiện gây tác động gì và được phát hiện sớm hơn bao nhiêu? |

Một ca chạy 200 lần trong tháng, mỗi lần kiểm tra thủ công mất 5 phút, có thể tiết kiệm nhiều thời gian thao tác. Nhưng nếu tự động hóa mất nhiều ngày, thường xuyên thất bại do môi trường và cần bảo trì liên tục, lợi ích ròng có thể thấp. Một ca kiểm tra quyền truy cập quan trọng có thể không tiết kiệm nhiều thao tác nhưng vẫn đáng tự động hóa vì giảm rủi ro nghiêm trọng.

## 6. Chọn ca theo cấp độ kiểm thử

Việc lựa chọn cần tính đến nơi ca được đặt trong hệ thống. Cùng một hành vi có thể được kiểm tra ở nhiều mức, nhưng mỗi mức tạo ra loại phản hồi khác nhau.

| Cấp độ | Ứng viên thường phù hợp | Lý do |
|---|---|---|
| Đơn vị/thành phần | Quy tắc tính toán, kiểm tra biên, chuyển trạng thái, xử lý lỗi | Nhanh, ổn định khi phụ thuộc được kiểm soát, dễ chẩn đoán |
| Hợp đồng/API | Cấu trúc request/response, schema, mã lỗi, quy tắc giao tiếp | Phản hồi rõ ở ranh giới giữa provider và consumer |
| Tích hợp | Giao dịch với cơ sở dữ liệu, message broker hoặc dịch vụ quan trọng | Xác nhận hành vi phối hợp giữa các thành phần thật |
| Hệ thống/đầu cuối | Luồng người dùng quan trọng, smoke test, hành trình phát hành | Xác nhận các thành phần kết hợp để tạo kết quả nghiệp vụ |
| Phi chức năng | Hiệu năng, bảo mật, khả năng truy cập, tương thích | Kiểm tra thuộc tính cần điều kiện hoặc công cụ chuyên biệt |

Các kiểm tra nhỏ và nhanh thường có thể chạy thường xuyên hơn. Kiểm thử đầu cuối thường tốn thời gian và dễ phụ thuộc môi trường, vì vậy nên chọn các hành trình có giá trị cao và giữ số lượng ở mức nhóm có thể duy trì. Những biến thể chi tiết có thể được kiểm tra ở mức đơn vị, API hoặc tích hợp.

Không nên áp dụng tỷ lệ cố định cho số lượng ca ở từng cấp. Cách phân bổ phải phản ánh kiến trúc, rủi ro, khả năng quan sát và chi phí của sản phẩm.

## 7. Chọn thời điểm chạy để phản hồi đúng lúc

Một ca có giá trị nhưng chạy quá muộn có thể không giúp người phát triển xử lý lỗi kịp thời. Nhóm nên gắn nhóm kiểm thử với điểm kiểm tra trong quy trình.

| Thời điểm | Nhóm kiểm thử thường phù hợp | Mục tiêu phản hồi |
|---|---|---|
| Khi phát triển cục bộ | Kiểm tra đơn vị và các kiểm tra rất nhanh | Phản hồi tức thì cho người viết mã |
| Pull request | Kiểm tra đơn vị, hợp đồng và tích hợp trọng yếu | Ngăn lỗi đi vào nhánh chính |
| Sau khi tích hợp | Bộ hồi quy chọn lọc, smoke và kiểm thử tích hợp rộng hơn | Xác nhận các thành phần phối hợp đúng |
| Hằng đêm hoặc theo lịch | Bộ hồi quy mở rộng, tương thích và một số kiểm thử phi chức năng | Phát hiện vấn đề không cần chặn từng thay đổi nhỏ |
| Trước phát hành | Kiểm thử theo rủi ro, luồng đầu cuối và tiêu chí phát hành | Cung cấp bằng chứng cho quyết định phát hành |
| Sau triển khai | Smoke, health check và kiểm tra giám sát | Xác nhận môi trường triển khai hoạt động đúng |

Không phải ca nào cũng nên chạy ở mọi điểm. Nếu một ca đầu cuối mất 20 phút và cần môi trường dùng chung, chạy nó cho mỗi commit có thể làm chậm toàn nhóm. Có thể chạy các kiểm tra nhỏ ở pull request và chạy luồng đầu cuối trọng yếu sau khi tích hợp hoặc trước phát hành.

### 7.1. Phân tầng theo tốc độ và rủi ro

Một cách tổ chức thường dùng:

- **Tầng phản hồi nhanh:** Ca ngắn, ổn định, giá trị cao, chạy thường xuyên.
- **Tầng xác nhận tích hợp:** Ca kiểm tra ranh giới quan trọng và phụ thuộc thật, chạy sau khi tích hợp.
- **Tầng hồi quy mở rộng:** Ca nhiều dữ liệu, nền tảng hoặc luồng phức tạp, chạy theo lịch hoặc trước mốc.
- **Tầng chuyên biệt:** Kiểm thử tải, bảo mật sâu, tương thích thiết bị hoặc thăm dò, chạy theo nhu cầu và kế hoạch riêng.

Phân tầng không có nghĩa tầng chậm kém quan trọng. Nó chỉ định thời điểm phù hợp để thu thập bằng chứng mà không làm mọi thay đổi phải chờ toàn bộ bộ kiểm thử.

## 8. Những loại ca thường là ứng viên tốt

Một số đặc điểm thường làm ca kiểm thử phù hợp để tự động hóa:

- Thực hiện lặp lại nhiều lần với các đầu vào hoặc môi trường xác định.
- Có kết quả mong đợi rõ hoặc oracle đáng tin cậy.
- Bao phủ hành vi cốt lõi hoặc rủi ro có tác động đáng kể.
- Cần chạy trên nhiều dữ liệu, phiên bản hoặc cấu hình.
- Tốn nhiều thao tác thủ công hoặc dễ xảy ra sai sót khi thực hiện bằng tay.
- Có thể chạy độc lập và cung cấp thông báo lỗi có ích.
- Có khả năng duy trì khi sản phẩm thay đổi.

Các ví dụ điển hình:

1. Kiểm tra quy tắc tính tiền, thuế, chiết khấu và giới hạn giá trị.
2. Kiểm tra quyền truy cập của các vai trò người dùng.
3. Kiểm tra schema và hợp đồng API giữa các dịch vụ.
4. Kiểm tra hồi quy cho các luồng đăng nhập, tạo đơn và thanh toán.
5. Kiểm tra chuyển đổi dữ liệu với tập dữ liệu chuẩn và bất biến.
6. Kiểm tra xử lý lỗi, timeout và retry ở các ranh giới quan trọng.
7. Kiểm tra tương thích trên tổ hợp nền tảng được hỗ trợ.
8. Smoke test sau khi triển khai để xác nhận các chức năng cốt lõi.

## 9. Những ca thường chưa phù hợp để tự động hóa ngay

Một số ca có thể cần cách tiếp cận khác hoặc cần cải thiện điều kiện trước:

- **Yêu cầu chưa ổn định:** Kịch bản và expected result thay đổi liên tục, khiến mã kiểm thử phải sửa thường xuyên.
- **Đánh giá chủ quan:** Chất lượng trải nghiệm hoặc nội dung chưa có rubric đủ rõ; có thể cần người đánh giá hoặc kết hợp tự động và thủ công.
- **Môi trường không thể tái tạo:** Phụ thuộc thiết bị hiếm, dịch vụ bên ngoài không ổn định hoặc quyền truy cập khó kiểm soát.
- **Chi phí bảo trì quá cao:** Giao diện hoặc quy trình thay đổi liên tục mà kiểm tra ở mức thấp hơn có thể cung cấp tín hiệu tương đương.
- **Không có oracle đáng tin cậy:** Nhóm chưa biết cách xác định kết quả đúng.
- **Giá trị trùng lặp:** Một ca mới chỉ lặp lại tín hiệu của ca khác mà không mở rộng rủi ro được bao phủ.
- **Tình huống khám phá:** Mục tiêu là học hỏi và tìm hành vi chưa biết, khó xác định trước toàn bộ thao tác.

Không nên hiểu “chưa phù hợp để tự động hóa ngay” là không cần kiểm thử. Có thể thực hiện thủ công, thăm dò, đánh giá chuyên gia hoặc bổ sung điều kiện để tự động hóa sau này.

## 10. Xử lý flaky test trong danh mục tự động hóa

Flaky test làm giảm niềm tin vào pipeline. Khi một ca thất bại ngẫu nhiên, người phát triển có thể bỏ qua cảnh báo hoặc chạy lại nhiều lần cho đến khi đạt. Nếu tình trạng kéo dài, các lỗi thật có thể bị che khuất giữa nhiều tín hiệu nhiễu.

Khi phát hiện ca không ổn định, cần:

1. Ghi lại tỷ lệ thất bại, môi trường, build, dữ liệu và lần chạy liên quan.
2. Xác định lỗi đến từ sản phẩm, kiểm thử, dữ liệu, dịch vụ phụ thuộc hay tài nguyên CI.
3. Ưu tiên sửa nguyên nhân gốc nếu ca bao phủ rủi ro quan trọng.
4. Tạm chuyển ca sang nhóm chạy có kiểm soát hoặc đánh dấu trạng thái cần điều tra nếu nó gây nhiễu pipeline.
5. Chỉ đưa lại vào nhóm chặn phát hành khi đã có bằng chứng về độ ổn định phù hợp.

Retry có thể giúp thu thập thêm bằng chứng nhưng không được biến một lần thất bại thành đạt mà không lưu lịch sử. Báo cáo nên phân biệt lần chạy đầu thất bại, lần chạy lại đạt và trạng thái cuối của ca. Nếu lỗi ngẫu nhiên phản ánh race condition thật, việc cách ly ca không được làm mất trách nhiệm xử lý rủi ro sản phẩm.

## 11. Ví dụ: lựa chọn tự động hóa cho hệ thống thương mại điện tử

Giả sử nhóm có các ca kiểm thử sau:

| Ca kiểm thử | Tần suất chạy | Độ ổn định hiện tại | Giá trị phản hồi | Quyết định gợi ý |
|---|---|---|---|---|
| Tính tổng giỏ hàng và thuế | Cao | Cao | Cao | Tự động hóa ở cấp đơn vị/API và chạy thường xuyên |
| Đăng nhập bằng tài khoản hợp lệ | Cao | Cao | Cao | Tự động hóa smoke và hồi quy trọng yếu |
| Thanh toán qua sandbox bên ngoài | Trung bình đến cao | Trung bình | Rất cao | Tự động hóa kiểm thử tích hợp có kiểm soát; chuẩn bị mô phỏng cho lỗi hiếm |
| Kiểm tra giao diện trên 20 kích thước màn hình | Trung bình | Trung bình | Trung bình đến cao | Chọn viewport đại diện, tự động hóa kiểm tra cơ bản và đánh giá thủ công các trường hợp trực quan phức tạp |
| Kiểm tra nội dung banner chiến dịch | Thấp | Thấp do nội dung thay đổi | Thấp | Kiểm tra thủ công hoặc kiểm tra cấu trúc tối thiểu |
| Báo cáo đối soát cuối tháng | Thấp | Cao | Rất cao | Tự động hóa các quy tắc tính và đối soát; chạy theo lịch nghiệp vụ |
| Khám phá trải nghiệm checkout mới | Thay đổi theo giai đoạn | Chưa ổn định | Cao | Thăm dò có mục tiêu; chuyển phát hiện ổn định thành ca tự động sau |

Nhóm không nên tự động hóa tất cả theo cùng một cách. Quy tắc tính tiền có thể được kiểm tra nhanh với nhiều tổ hợp dữ liệu. Thanh toán sandbox cần kiểm soát phụ thuộc và có thể kết hợp contract test, integration test cùng một số luồng đầu cuối. Banner chiến dịch thay đổi thường xuyên có thể không đáng để xây dựng một bộ kiểm thử giao diện phức tạp.

### 11.1. Ví dụ tính lợi ích lặp lại

Giả sử ca đối soát đơn hàng mất 15 phút nếu làm thủ công và cần chạy 20 lần mỗi tháng. Tổng công thao tác là 300 phút mỗi tháng. Nếu tự động hóa mất 12 giờ ban đầu và khoảng 1 giờ bảo trì mỗi tháng, nhóm có thể so sánh chi phí đầu tư với thời gian tiết kiệm trong nhiều tháng.

Tuy nhiên, phép tính thời gian chưa phản ánh đầy đủ giá trị. Nếu ca tự động phát hiện sai lệch tài chính trước khi phát hành, lợi ích giảm rủi ro có thể lớn hơn thời gian tiết kiệm. Ngược lại, nếu ca tạo nhiều cảnh báo giả và mỗi lần điều tra mất 30 phút, chi phí thực tế sẽ tăng.

Ước lượng nên tính cả thời gian chạy, thời gian điều tra, công sức sửa ca và giá trị phát hiện lỗi. Các con số là dữ liệu hỗ trợ quyết định, không phải lý do duy nhất để bỏ một kiểm thử quan trọng.

## 12. Xây dựng danh mục và thứ tự ưu tiên tự động hóa

Nhóm nên duy trì danh mục ứng viên với thông tin đủ để so sánh và rà soát:

| Trường | Nội dung cần ghi |
|---|---|
| ID/tên ca | Định danh duy nhất và hành vi được xác nhận |
| Yêu cầu/rủi ro liên quan | Lý do cần kiểm tra và hậu quả nếu lỗi |
| Cấp độ | Đơn vị, API, tích hợp, hệ thống, đầu cuối hoặc phi chức năng |
| Tần suất dự kiến | Điểm chạy trong pipeline hoặc số lần chạy theo chu kỳ |
| Độ ổn định | Ổn định, cần cải thiện hoặc đang điều tra; kèm bằng chứng |
| Giá trị phản hồi | Mức rủi ro, khả năng phát hiện và mức độ hành động của kết quả |
| Chi phí | Xây dựng, dữ liệu, môi trường, chạy và bảo trì |
| Quyết định | Tự động hóa ngay, cải thiện trước, giữ thủ công, thăm dò hoặc không ưu tiên |
| Người phụ trách | Người sở hữu ca và theo dõi chất lượng của nó |
| Thời điểm rà soát | Khi nào đánh giá lại tần suất, độ ổn định và giá trị |

Có thể tổ chức phiên ưu tiên với QA, lập trình viên và chủ sản phẩm. Khi có bất đồng, hãy đưa ra căn cứ: lịch sử chạy, mức độ rủi ro, số lỗi từng phát hiện, thời gian bảo trì và phạm vi trùng lặp. Một ca có điểm thấp về tần suất vẫn có thể được ưu tiên nếu kiểm tra rủi ro nghiêm trọng.

## 13. Đo lường chất lượng danh mục tự động hóa

Sau khi tự động hóa, nhóm cần theo dõi liệu các ca có tiếp tục đem lại phản hồi hữu ích hay không. Một số chỉ số có thể dùng:

- **Tần suất chạy thực tế:** Ca có được chạy đúng lịch hoặc điểm kiểm tra dự kiến không?
- **Thời gian phản hồi:** Từ lúc bắt đầu chạy đến khi người phát triển nhận kết quả mất bao lâu?
- **Tỷ lệ flaky:** Bao nhiêu lần thất bại không thể tái hiện hoặc không liên quan đến thay đổi sản phẩm?
- **Tỷ lệ lỗi có ích:** Ca có phát hiện lỗi sản phẩm được xác nhận hay chủ yếu tạo cảnh báo giả?
- **Thời gian chẩn đoán:** Mất bao lâu để xác định nguyên nhân khi ca thất bại?
- **Chi phí bảo trì:** Cần bao nhiêu công sức cập nhật khi yêu cầu, giao diện hoặc API thay đổi?
- **Độ bao phủ rủi ro:** Những rủi ro ưu tiên nào có bằng chứng tự động đáng tin cậy?
- **Mức độ trùng lặp:** Có nhiều ca kiểm tra cùng một hành vi mà không bổ sung giá trị không?

Không nên tối ưu một chỉ số riêng lẻ. Tăng số lượng ca có thể làm tăng thời gian pipeline; giảm thời gian chạy bằng cách bỏ kiểm tra tích hợp có thể làm tăng lỗi lọt. Tỷ lệ flaky thấp cũng không có ý nghĩa nếu các ca không kiểm tra rủi ro quan trọng.

Nên xem xét kết quả theo xu hướng và theo nhóm kiểm thử. Một ca có thể được giữ, sửa, chuyển sang lịch chạy khác hoặc loại bỏ nếu không còn cung cấp tín hiệu hữu ích. Mọi quyết định loại bỏ kiểm tra rủi ro cao cần được xem xét và ghi nhận rõ.

## 14. Rà soát lại quyết định theo vòng đời sản phẩm

Quyết định tự động hóa không phải vĩnh viễn. Khi sản phẩm và quy trình thay đổi, tần suất, độ ổn định và giá trị phản hồi cũng thay đổi.

Nên rà soát khi:

- Một tính năng chuyển sang giai đoạn ổn định hoặc ngừng sử dụng.
- Một thành phần được viết lại hoặc chuyển sang API mới.
- Ca kiểm thử liên tục thất bại hoặc thời gian chạy tăng đáng kể.
- Người dùng bắt đầu sử dụng một luồng mới nhiều hơn dự kiến.
- Có lỗi lọt qua dù bộ kiểm thử hiện tại đạt.
- Môi trường CI, dịch vụ sandbox hoặc thiết bị kiểm thử thay đổi.
- Nhiều ca trùng lặp hoặc một ca không còn phát hiện lỗi có ích.

Trong buổi rà soát, nhóm có thể quyết định:

- Giữ nguyên và tiếp tục chạy ở lịch hiện tại.
- Chuyển ca sang giai đoạn chạy sớm hơn hoặc muộn hơn.
- Tách ca lớn thành các kiểm tra nhỏ, dễ chẩn đoán.
- Cải thiện dữ liệu, môi trường hoặc oracle để tăng độ ổn định.
- Bổ sung kiểm tra ở cấp khác để tăng bằng chứng.
- Chuyển một phần sang kiểm thử thủ công hoặc thăm dò.
- Loại bỏ ca trùng lặp hoặc không còn phù hợp sau khi đánh giá tác động.

## 15. Những sai lầm thường gặp

- **Tự động hóa chỉ vì ca được chạy nhiều:** Tần suất cao không bù được oracle yếu hoặc kết quả không ổn định.
- **Chọn ca dễ viết nhất:** Các ca đơn giản có thể bỏ qua rủi ro quan trọng của sản phẩm.
- **Tự động hóa mọi ca thủ công:** Một số đánh giá cần con người, khám phá hoặc phán đoán theo ngữ cảnh.
- **Bỏ qua chi phí bảo trì:** Ca phụ thuộc giao diện mong manh có thể tốn nhiều công sửa hơn giá trị đem lại.
- **Giữ flaky test trong pipeline chặn mà không xử lý:** Cảnh báo giả làm giảm niềm tin và che khuất lỗi thật.
- **Dùng retry để coi lỗi là đạt:** Kết quả thất bại ban đầu cần được lưu và điều tra.
- **Đánh giá giá trị chỉ bằng số lỗi phát hiện:** Ca có thể rất quan trọng dù hiếm khi tìm thấy lỗi.
- **Chạy mọi ca ở mọi lần commit:** Làm phản hồi chậm và tiêu tốn tài nguyên không cần thiết.
- **Chỉ theo dõi tỷ lệ tự động hóa:** Số lượng ca không phản ánh độ tin cậy hoặc giá trị bằng chứng.
- **Không rà soát danh mục:** Ca lỗi thời, trùng lặp hoặc không còn cần thiết tiếp tục làm tăng chi phí.

## 16. Checklist lựa chọn ca để tự động hóa

Trước khi đưa một ca vào kế hoạch tự động hóa, nhóm có thể dùng checklist sau:

- [ ] Mục tiêu, yêu cầu hoặc rủi ro mà ca kiểm tra đã rõ.
- [ ] Tần suất chạy dự kiến có căn cứ từ lịch sử, quy trình hoặc nhu cầu nghiệp vụ.
- [ ] Ca có expected result hoặc oracle đủ tin cậy.
- [ ] Dữ liệu và môi trường có thể thiết lập, tái tạo và dọn dẹp.
- [ ] Ca có thể chạy độc lập hoặc phụ thuộc được quản lý rõ.
- [ ] Độ ổn định đã được đánh giá; flaky test có người điều tra.
- [ ] Kết quả thất bại cung cấp thông tin đủ để chẩn đoán và hành động.
- [ ] Giá trị phản hồi tương xứng với rủi ro được bao phủ.
- [ ] Chi phí xây dựng, chạy và bảo trì đã được xem xét.
- [ ] Thời điểm chạy phù hợp với nhu cầu phản hồi của nhóm.
- [ ] Không có ca khác cung cấp cùng tín hiệu với chi phí thấp hơn mà không mất độ bao phủ quan trọng.
- [ ] Có người sở hữu và thời điểm rà soát lại quyết định.

Lựa chọn ca theo tần suất chạy, độ ổn định và giá trị phản hồi giúp nhóm đầu tư tự động hóa vào những kiểm tra tạo ra bằng chứng đáng tin cậy và hữu ích. Khi kết hợp ba yếu tố với rủi ro, chi phí vòng đời và thời điểm cần phản hồi, danh mục tự động hóa sẽ hỗ trợ phát hiện lỗi sớm, giảm công việc lặp lại và giữ cho kết quả kiểm thử có ý nghĩa đối với quyết định phát triển và phát hành.
