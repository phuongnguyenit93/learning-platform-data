# Phương pháp định tính trong đánh giá rủi ro bảo mật

## 1. Phương pháp định tính là gì?

**Đánh giá rủi ro định tính** (*qualitative risk assessment*) là cách nhận diện, phân tích và xếp mức ưu tiên rủi ro thông qua các **mô tả có tiêu chí** như *Thấp*, *Trung bình*, *Cao* hoặc *Rất cao*. Thay vì cố gắng ước lượng chính xác xác suất và số tiền thiệt hại, nhóm đánh giá sử dụng bối cảnh hệ thống, kinh nghiệm chuyên môn, thông tin mối đe dọa, hiện trạng kiểm soát và **bằng chứng quan sát được** để đưa ra một phán đoán có thể giải thích.

Ví dụ, một API có lỗi phân quyền đã được kiểm thử xác nhận có thể được xếp **Khả năng xảy ra: Cao** và **Tác động: Cao** nếu truy cập trái phép dễ thực hiện và có thể làm lộ dữ liệu nhạy cảm. Nhóm không cần tự đưa ra con số như “xác suất 73%” khi thiếu dữ liệu để bảo vệ ước lượng ấy.

Trong chương **Đánh giá rủi ro** của module **SECURITY_SECURITY_ASSURANCE**, phương pháp định tính được dùng để:

1. Mô tả **tình huống rủi ro** gắn với tài sản và mục tiêu bảo mật cụ thể.
2. Đánh giá khả năng xảy ra và hậu quả theo **thang đo nhất quán, có giải thích**.
3. Xác định các *security controls* cần triển khai hoặc kiểm tra.
4. Chỉ ra **bằng chứng assurance** nào hỗ trợ, giới hạn hoặc bác bỏ nhận định hiện tại.
5. Ưu tiên xử lý, trình người có thẩm quyền quyết định và **đánh giá lại** khi có thay đổi.

Định tính không có nghĩa là “đoán theo cảm giác”. Một kết luận định tính tốt phải **truy vết được căn cứ, người đánh giá, thời điểm, phạm vi và mức độ chưa chắc chắn**.

> Đánh giá rủi ro định tính tạo ra một **mức ưu tiên để quyết định**, không phải chứng nhận an toàn tuyệt đối. Nhãn “Thấp” chỉ có ý nghĩa theo thang đo, bối cảnh, bằng chứng và ngưỡng chấp nhận rủi ro của tổ chức.

## 2. Khi nào nên dùng và giới hạn của phương pháp

Phương pháp định tính phù hợp khi tổ chức cần sàng lọc nhiều hệ thống hoặc quyết định tương đối nhanh, trong khi dữ liệu về tần suất sự cố, tổn thất tài chính và hiệu lực control chưa đủ để ước tính định lượng đáng tin cậy.

| Trường hợp | Giá trị của cách đánh giá định tính |
| --- | --- |
| Rà soát kiến trúc dịch vụ mới | Nhận diện tình huống rủi ro trước khi có dữ liệu vận hành |
| Threat modeling trong thiết kế API | So sánh đường tấn công và quyết định yêu cầu bảo mật cần có |
| Phân loại phát hiện từ pentest/audit | Đặt mức ưu tiên trong bối cảnh dữ liệu và nghiệp vụ |
| Phê duyệt phát hành | Trình bày rủi ro còn lại, bằng chứng và điều kiện cần đáp ứng |
| Xem xét thay đổi lớn | Đánh giá tác động khi thêm endpoint, quyền, tích hợp hoặc nhà cung cấp |
| Báo cáo cho lãnh đạo | Truyền đạt những rủi ro trọng yếu theo ngôn ngữ dễ quyết định |

**Ưu điểm:** ít phụ thuộc vào dữ liệu thống kê lịch sử; dễ bắt đầu; tập hợp được hiểu biết của chủ sản phẩm, kỹ thuật, vận hành và bảo mật; hỗ trợ ưu tiên theo ngữ cảnh.

**Giới hạn:** thang đo có tính thứ bậc chứ không biểu thị khoảng cách số học; người đánh giá có thể bất đồng; nhãn “Cao” của hai nhóm không tự đồng nghĩa; ma trận có thể che khuất rủi ro có tác động cực lớn nhưng khó xảy ra; các giả định về hiệu quả control có thể chưa được chứng minh.

Với quyết định đầu tư lớn, rủi ro có tác động thảm họa hoặc yêu cầu kinh doanh cần so sánh chi phí và thiệt hại, có thể cần phân tích kịch bản sâu hơn hoặc **đánh giá định lượng** với dữ liệu phù hợp. Hai cách có thể bổ sung cho nhau.

### 2.1. Phân biệt định tính, bán định lượng và định lượng

| Cách tiếp cận | Đầu vào/đầu ra điển hình | Cách hiểu |
| --- | --- | --- |
| **Định tính** | Thang mô tả *Thấp / Trung bình / Cao*, lý do, bằng chứng và độ tin cậy | Xếp hạng tương đối theo tiêu chí đã định |
| **Bán định lượng** | Gán điểm thứ bậc, ví dụ 1–5 cho khả năng và tác động rồi dùng quy tắc phân loại | Số điểm thường là **mã mức**; chưa chắc là xác suất hay đơn vị tổn thất |
| **Định lượng** | Khoảng xác suất/tần suất và phân phối tác động ước tính bằng dữ liệu có căn cứ | Có thể hỗ trợ phân tích kỳ vọng và độ nhạy, nhưng phụ thuộc chất lượng dữ liệu/mô hình |

Nhân hai điểm thứ bậc **3 × 4 = 12** không tự tạo ra “12 đơn vị rủi ro” theo nghĩa vật lý. Nếu dùng phép nhân để sàng lọc, cần công khai quy tắc và tránh coi những chênh lệch nhỏ của điểm số là khác biệt chính xác về rủi ro.

## 3. Cấu trúc của một đánh giá rủi ro định tính

Đơn vị được đánh giá nên là **risk scenario** (kịch bản rủi ro), không chỉ tên một lỗ hổng hoặc một tài sản.

Một risk scenario tốt trả lời được:

- **Tài sản:** dữ liệu, chức năng, dịch vụ hoặc mục tiêu nào chịu tác động?
- **Threat source và threat event:** ai/điều gì có thể gây sự kiện, theo đường nào?
- **Điểm yếu và điều kiện:** hệ thống phải ở trạng thái nào thì sự kiện có thể xảy ra?
- **Hậu quả:** tác động lên bí mật, toàn vẹn, sẵn sàng, quyền riêng tư, tài chính hoặc vận hành ra sao?
- **Control hiện có:** điều gì đang ngăn ngừa, phát hiện hoặc giảm tác động? Có bằng chứng hiệu quả chưa?
- **Chủ sở hữu:** ai chịu trách nhiệm rủi ro, ai chịu trách nhiệm control và khắc phục?
- **Phạm vi và thời gian:** phiên bản, môi trường, tập dữ liệu và khoảng thời gian được xem xét?

Ví dụ chưa đủ rõ: **“Rủi ro SQL injection: Cao.”**

Ví dụ tốt hơn: “Một người dùng bên ngoài có thể gửi đầu vào được thao tác vào API tìm kiếm. Nếu mã ứng dụng ghép trực tiếp chuỗi vào truy vấn SQL, người đó có thể đọc hoặc sửa bản ghi khách hàng ngoài quyền, ảnh hưởng dữ liệu và hoạt động kinh doanh. Cần xác minh cách tạo truy vấn trên phiên bản API đang triển khai và kiểm thử trường hợp đầu vào bất thường.”

**Threat**, **vulnerability** và **risk** cần được phân biệt. Threat là sự kiện/nguồn có thể gây hại; vulnerability là điểm yếu tạo điều kiện; risk là khả năng gánh chịu hậu quả khi sự kiện tác động lên tài sản trong hoàn cảnh thực tế. Một phát hiện chưa được xác minh không nên được diễn đạt thành sự cố đã xảy ra.

## 4. Quy trình đánh giá rủi ro định tính

### Bước 1. Thiết lập phạm vi và tiêu chí trước khi chấm mức

Đầu tiên xác định:

1. **Phạm vi hệ thống:** service, API, luồng dữ liệu, môi trường, nhóm người dùng, nhà cung cấp và phiên bản nào?
2. **Mục tiêu:** đánh giá để thiết kế control, ưu tiên khắc phục, duyệt phát hành, xem ngoại lệ hay chuẩn bị audit?
3. **Tài sản và giá trị:** dữ liệu có nhạy cảm không, chức năng có quan trọng cho doanh nghiệp không?
4. **Chân trời thời gian:** đánh giá cho đợt phát hành, vài tháng vận hành hay một chu kỳ kinh doanh?
5. **Thang đo và ngưỡng:** các định nghĩa khả năng, tác động, mức ưu tiên và đường chuyển cấp.
6. **Trách nhiệm:** risk owner, control owner, nhóm đánh giá và người ra quyết định.

Nếu hai nhóm dùng định nghĩa “Cao” khác nhau, kết quả có thể không so sánh được. Do đó, **thang đo cần được thống nhất trước** khi xem từng sự cố cụ thể để giảm thiên lệch do biết trước kết luận mong muốn.

### Bước 2. Nhận diện kịch bản có thể gây hại

Sử dụng kết hợp threat modeling, sơ đồ luồng dữ liệu, rà soát thay đổi, kết quả kiểm thử, sự cố đã biết, phỏng vấn chuyên gia và thông tin đe dọa phù hợp.

Kịch bản cần nêu sự kiện, điều kiện, điểm tiếp cận và hậu quả. Ví dụ:

- Người dùng đã xác thực thay ID trong URL để xem đơn hàng của người khác.
- Token pipeline CI bị chiếm quyền khiến artifact không được phép được triển khai.
- Sao lưu không thể khôi phục khi dịch vụ gặp sự cố dữ liệu.
- Dịch vụ xác thực phụ thuộc một nhà cung cấp duy nhất và không có phương án phục hồi phù hợp.
- Nhân viên vô tình xuất dữ liệu khách hàng đến nơi lưu trữ công khai.

Không chỉ liệt kê kịch bản tấn công có chủ đích. Sai sót, hỏng hóc, thay đổi quy trình và nhà cung cấp cũng tạo ra rủi ro cần đánh giá.

### Bước 3. Thu thập bằng chứng trước khi nhận định

Một đánh giá có căn cứ nên xem:

| Nguồn bằng chứng | Câu hỏi cần kiểm tra | Giới hạn |
| --- | --- | --- |
| Kiến trúc và phân luồng dữ liệu | Đường truy cập, ranh giới tin cậy, tài sản và phụ thuộc ở đâu? | Sơ đồ có thể chưa phản ánh production |
| Cấu hình và mã nguồn | Control được cài đặt như thế nào? | Có thể khác bản đang chạy |
| Kiểm thử tích hợp, bảo mật, pentest | Trường hợp được phép/bị từ chối có hoạt động như yêu cầu? | Test chỉ bao phủ các kịch bản đã chạy |
| Log, telemetry, cảnh báo | Hệ thống thực tế có dấu hiệu bất thường hoặc control không hoạt động? | Không thấy cảnh báo không có nghĩa không có sự kiện |
| Danh mục lỗ hổng/phụ thuộc | Có điểm yếu đã biết với thành phần đang sử dụng? | Severity kỹ thuật không tự bằng rủi ro kinh doanh |
| Incident, near-miss, audit trước đây | Hình thức sự cố/thiếu sót nào đã xuất hiện? | Dữ liệu quá khứ có thể thiếu hoặc không còn phù hợp |
| Threat intelligence đáng tin | Nguồn đe dọa và kỹ thuật nào liên quan tới loại hệ thống này? | Không suy từ tin tức chung thành xác suất chắc chắn |

Ghi rõ **phiên bản, môi trường, thời điểm, người tạo và phạm vi kiểm tra**. Nếu bằng chứng không đủ, ghi **UNKNOWN / CHƯA XÁC MINH** và yêu cầu thu thập thêm; không ngầm xem tình huống đó là ít rủi ro.

### Bước 4. Chấm khả năng xảy ra (*likelihood*)

Khả năng xảy ra thể hiện **độ hợp lý rằng kịch bản bất lợi sẽ diễn ra trong phạm vi và khoảng thời gian đang xét**, có tính đến nguồn đe dọa, khả năng tiếp cận, điều kiện khai thác và các control liên quan.

Không đánh giá chỉ dựa trên “hacker có thể làm được hay không”. Hãy xét cả:

- Đường tấn công có tiếp cận được từ Internet hay cần quyền nội bộ/đặc biệt?
- Điều kiện khai thác có đang tồn tại? Có bằng chứng thử nghiệm hay chỉ suy đoán?
- Hành động cần nhiều kỹ năng, sự phối hợp hoặc quyền truy cập đến đâu?
- Có động cơ, tiền lệ hoặc tín hiệu tấn công phù hợp không?
- Những control phòng ngừa/phát hiện thực tế hoạt động đến mức nào?
- Có điểm đơn lẻ dễ bị thất bại, thiếu giám sát hoặc khả năng lặp thử lớn không?
- Phạm vi hệ thống và thời hạn đánh giá có thay đổi khả năng xảy ra không?

Đề xuất **thang ba mức**, dùng nhất quán cho bài học:

| Mức likelihood | Mô tả tình huống | Ví dụ minh họa |
| --- | --- | --- |
| **Thấp** | Kịch bản khó xảy ra trong phạm vi và thời gian xét vì điều kiện tiếp cận hạn chế hoặc control phù hợp đã được kiểm chứng; vẫn có thể xảy ra | Chức năng chỉ nội bộ, phân quyền được test trên bản chạy và giám sát phù hợp |
| **Trung bình** | Kịch bản khả thi, nhưng cần thêm điều kiện, có control giảm bớt hoặc bằng chứng cho thấy sự phơi nhiễm không thường xuyên | Endpoint có thể tiếp cận nhưng cần quyền đặc biệt hoặc qua nhiều bước |
| **Cao** | Kịch bản dễ thực hiện/tiếp cận, điều kiện gây hại đang hiện diện hoặc có bằng chứng lỗi control rõ ràng | API Internet thiếu kiểm tra quyền cấp đối tượng, test đã xác nhận truy cập sai quyền |

**Không tự động cho “Thấp” vì chưa thấy sự cố**. Nếu chưa có kiểm thử kiểm soát, nên ghi độ tin cậy thấp hoặc **chưa đủ thông tin**, đồng thời đặt hành động bổ sung bằng chứng trước khi hạ mức.

### Bước 5. Chấm tác động (*impact*)

Tác động là hậu quả **nếu kịch bản xảy ra**. Hãy xét hậu quả đáng tin cậy, không mặc định tình huống tệ nhất không giới hạn hay tình huống nhẹ nhất.

Thang ba mức minh họa:

| Mức impact | Mô tả tác động | Ví dụ minh họa |
| --- | --- | --- |
| **Thấp** | Ảnh hưởng cục bộ, có thể phục hồi bằng quy trình thường nhật; dữ liệu quan trọng và dịch vụ cốt lõi ít bị ảnh hưởng | Một báo cáo nội bộ không nhạy cảm bị trễ ngắn |
| **Trung bình** | Gián đoạn hoặc sai lệch đáng kể với một bộ phận, một nhóm người dùng; cần xử lý có phối hợp | Chức năng đặt hàng chậm hoặc sai lệch giới hạn trong một nhóm giao dịch |
| **Cao** | Tiết lộ/sửa dữ liệu nhạy cảm trên phạm vi lớn, mất dịch vụ cốt lõi đáng kể, hoặc hậu quả nghiêm trọng về nghĩa vụ/khả năng phục hồi | API làm lộ dữ liệu nhiều khách hàng hoặc làm sai thanh toán trọng yếu |

Tổ chức cần **hiệu chỉnh mô tả** với quy mô, loại dữ liệu và các ngưỡng tác động nội bộ. Nên phân tích nhiều chiều:

| Chiều tác động | Câu hỏi |
| --- | --- |
| **Bí mật / quyền riêng tư** | Dữ liệu nào lộ, số chủ thể, mức nhạy cảm và nghĩa vụ liên quan? |
| **Toàn vẹn / gian lận** | Dữ liệu hoặc giao dịch có thể bị sửa sai, có thể khôi phục đáng tin không? |
| **Sẵn sàng / phục hồi** | Gián đoạn dịch vụ nào, bao lâu, có vượt mục tiêu phục hồi không? |
| **Khách hàng / hợp đồng** | Có ảnh hưởng quyền lợi, độ tin cậy hay cam kết dịch vụ không? |
| **Tài chính / vận hành** | Có cần điều tra, khắc phục, tái xử lý hay mất doanh thu đáng kể không? |
| **Pháp lý / quy định** | Có phát sinh nghĩa vụ bắt buộc, cần báo cáo hay vi phạm quy tắc áp dụng không? |

Có thể dùng **mức tác động trọng yếu nhất** để tránh bỏ sót chiều nghiêm trọng, nhưng phải ghi **chiều nào, lý do nào và tiêu chí nào**. Không cộng điểm tùy ý giữa các chiều hay tính trung bình để che khuất hậu quả nặng.

### Bước 6. Kết hợp likelihood và impact thành mức rủi ro

Một **ma trận 3 × 3 minh họa** cho hai thang trên:

| Likelihood \ Impact | **Thấp** | **Trung bình** | **Cao** |
| --- | --- | --- | --- |
| **Thấp** | Thấp | Thấp | Trung bình |
| **Trung bình** | Thấp | Trung bình | Cao |
| **Cao** | Trung bình | Cao | Cao |

Ví dụ:

- API đã **xác nhận** không kiểm tra quyền và có thể truy cập qua Internet, dữ liệu nhạy cảm: **Cao × Cao → Cao**.
- Dịch vụ có kiểm tra quyền được kiểm chứng, nhưng hậu quả nếu control thất bại vẫn lớn: **Thấp × Cao → Trung bình** theo ma trận mẫu.
- Một chức năng phụ có thể gặp lỗi thao tác tương đối thường xuyên nhưng tác động giới hạn: **Cao × Thấp → Trung bình**.

Đây là **quy tắc phân loại minh họa để học**, không phải thang mặc định dùng cho mọi tổ chức. Thứ tự ưu tiên của một kịch bản hiếm nhưng hậu quả thảm họa có thể cần **chuyển cấp đặc biệt** ngay cả khi ô ma trận không được ghi “Cao”. Các nghĩa vụ pháp lý bắt buộc hoặc ngưỡng không được vượt cần áp dụng **độc lập với ma trận**.

Một ma trận giúp nhất quán hóa thảo luận, nhưng **không phải bằng chứng** rằng các giả định về khả năng hoặc tác động là đúng.

### Bước 7. Đánh giá hiệu lực control và rủi ro còn lại

Phải phân biệt:

- **Inherent risk – rủi ro vốn có:** mức rủi ro theo kịch bản **trước khi xét những control được chỉ định trong phương pháp đánh giá**; phạm vi và giả định “chưa xét control nào” cần được nêu rõ.
- **Residual risk – rủi ro còn lại:** mức rủi ro sau khi xét các control thực tế, bao gồm **mức hiệu quả đã được chứng minh**.

Control có thể làm giảm likelihood, giảm impact hoặc giúp phát hiện/giới hạn hậu quả. Ví dụ, kiểm tra quyền theo đối tượng giúp giảm khả năng lộ dữ liệu; mã hóa có thể hạn chế hậu quả trong một số tình huống nhất định, tùy kiểu khóa và cách tấn công; sao lưu có kiểm thử khôi phục có thể giảm hậu quả mất dữ liệu.

Một lỗi phổ biến là ghi “đã có MFA” nên hạ likelihood ngay, trong khi MFA không bảo vệ được một số tài khoản dịch vụ hoặc đường truy cập còn lại. Phải xem **độ bao phủ, cấu hình, điều kiện thất bại và bằng chứng đúng môi trường**.

Nếu control mới chỉ được đề xuất hoặc đang triển khai, có thể ghi **target residual risk (dự kiến)**, nhưng **không đồng nhất** với residual risk đã được xác minh.

### Bước 8. Quyết định xử lý rủi ro

Các hướng xử lý phổ biến:

| Phương án | Nội dung | Ví dụ |
| --- | --- | --- |
| **Mitigate – giảm thiểu** | Triển khai/sửa control để giảm khả năng hoặc hậu quả | Thêm phân quyền cấp đối tượng và test hồi quy |
| **Avoid – tránh** | Dừng hoặc thay đổi hoạt động gây ra rủi ro | Không triển khai endpoint xuất dữ liệu chưa kiểm soát được |
| **Transfer / share – chuyển giao/chia sẻ** | Chuyển một phần hậu quả hoặc trách nhiệm hợp đồng trong giới hạn phù hợp | Bảo hiểm, điều khoản nhà cung cấp; vẫn còn trách nhiệm của tổ chức |
| **Accept – chấp nhận** | Chủ thể có thẩm quyền chấp nhận residual risk có căn cứ và điều kiện | Phê duyệt ngoại lệ giới hạn thời gian với giám sát và đánh giá lại |

Mức *Thấp / Trung bình / Cao* là **đầu vào** cho xử lý; việc chấp nhận, hoãn phát hành hoặc chuyển cấp phải theo khẩu vị rủi ro, chính sách, nghĩa vụ và quyền phê duyệt thực tế. Nhóm kiểm thử không tự chấp nhận rủi ro thay cho **risk owner**.

### Bước 9. Ghi hồ sơ, theo dõi, kiểm chứng và đánh giá lại

Đánh giá cần tạo một bản ghi đủ để người khác kiểm tra: tình huống, phạm vi, tiêu chí, likelihood, impact, mức rủi ro, bằng chứng, độ tin cậy, control, rủi ro còn lại, chủ sở hữu, hành động, thời hạn và điều kiện đóng.

Khi xảy ra thay đổi code, quyền, cấu hình, nhà cung cấp, dữ liệu, threat intelligence hoặc sự cố, cần xem **mức rủi ro và độ hiệu lực của bằng chứng cũ còn phù hợp không**. Assurance liên tục yêu cầu **kiểm thử lại và cập nhật kết luận**, không chỉ duy trì một bảng xếp hạng tĩnh.

## 5. Vai trò của bằng chứng và độ tin cậy trong đánh giá định tính

Hai người có thể cùng xếp risk là “Trung bình” nhưng một người dựa trên kết quả test thực tế, người còn lại dựa trên mô tả chưa xác minh. **Chất lượng hai kết luận khác nhau**.

Nên ghi riêng **confidence** (mức tin cậy của nhận định), ví dụ:

| Mức confidence | Mô tả | Hành động gợi ý |
| --- | --- | --- |
| **Cao** | Bằng chứng phù hợp, cập nhật, có thể truy vết; kịch bản và control được kiểm tra đủ trong phạm vi | Dùng làm căn cứ trong giới hạn đã nêu; duy trì kiểm tra khi thay đổi |
| **Trung bình** | Có bằng chứng đáng dùng nhưng còn thiếu một số môi trường, trường hợp hoặc thời gian | Bổ sung các kiểm tra quan trọng và nêu rõ giới hạn |
| **Thấp** | Chủ yếu suy luận, tài liệu chưa xác minh, dữ liệu cũ hoặc nhiều giả định quan trọng | Ưu tiên thu thập thêm bằng chứng, chuyển cấp khi tác động có thể lớn |

**Confidence khác likelihood.** Một rủi ro “Likelihood: Thấp; Confidence: Thấp” nghĩa là **chúng ta chưa chắc nhận định khả năng thấp đáng tin**, chứ không có nghĩa rủi ro đã được kiểm soát tốt.

### 5.1. Bằng chứng assurance hợp lệ cần điều gì?

Mỗi kết luận định tính nên có thể trả lời:

1. **Tính liên quan:** bằng chứng có kiểm chứng đúng kịch bản và security claim?
2. **Độ bao phủ:** trường hợp được phép, bị từ chối, biên và đường truy cập thay thế đã được xét?
3. **Nguồn gốc:** ai/công cụ nào tạo, có thể truy vết đến test run, commit, cấu hình hoặc log?
4. **Tính hiện hành:** có tương ứng phiên bản, môi trường và cấu hình đang đánh giá?
5. **Tính độc lập:** có đánh giá chéo hoặc reviewer phù hợp mức độ rủi ro?
6. **Khả năng tái lập:** nếu cần, có thể chạy lại hoặc xác minh kết quả không?
7. **Bảo mật bằng chứng:** kết quả có chứa dữ liệu nhạy cảm không, quyền xem và thời hạn lưu được quản lý thế nào?

Một tài liệu chính sách cho biết **control được kỳ vọng tồn tại**, còn kiểm thử và giám sát mới hỗ trợ nhận định về **control hoạt động trong thực tế**. Kết quả audit chỉ chứng minh điều được đánh giá trong phạm vi, thời điểm và tiêu chí đã công bố.

### 5.2. Xử lý thiếu dữ liệu và bất đồng đánh giá

Nếu dữ liệu không đủ, có thể:

- Ghi **Unassessed / Chưa đủ bằng chứng** thay vì tự đưa ra mức Thấp.
- Ghi một **khoảng nhận định** (ví dụ likelihood Trung bình–Cao), nêu giả định cho từng trường hợp.
- Ưu tiên xác minh giả định có thể thay đổi quyết định: test quyền, kiểm tra cấu hình production, diễn tập restore.
- Đề nghị kiểm tra chéo khi có bất đồng quan trọng về tác động hoặc khả năng.
- Chuyển cấp với tình huống có **tác động rất lớn**, dù kết luận likelihood chưa vững chắc.

Mọi thay đổi mức rủi ro cần giải thích **đã thay đổi dữ kiện, control, phạm vi hay thang đo**. Không nên âm thầm đổi “Cao” thành “Trung bình” để đáp ứng thời hạn phát hành.

## 6. Ví dụ xuyên suốt: đánh giá định tính lỗi phân quyền API Java/Spring Boot

Giả sử dịch vụ Orders API dùng **Java / Spring Boot** và có endpoint:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-user-A>
~~~

Đơn hàng **841** thuộc user B, không thuộc user A. Nhóm chạy một integration test để kiểm tra điều gì xảy ra khi A yêu cầu tài nguyên này.

### 6.1. Mô tả kịch bản

| Thành phần | Đánh giá trong ví dụ giả định |
| --- | --- |
| Tài sản | Thông tin đơn hàng và người nhận |
| Security objective | Bảo đảm chỉ chủ thể có quyền trên đơn hàng mới đọc được nội dung |
| Threat source | Người dùng có tài khoản hợp lệ nhưng không có quyền trên đối tượng |
| Threat event | Đổi ID để truy cập đơn của người khác |
| Vulnerability | Không có kiểm tra quyền cấp đối tượng trong một đường xử lý |
| Phạm vi | Endpoint công khai của Orders API trong bản build trước phát hành |
| Hậu quả | Lộ dữ liệu khách hàng, ảnh hưởng quyền riêng tư và uy tín |
| Risk owner | Chủ sản phẩm/chủ sở hữu rủi ro được phân công |
| Control owner | Người chịu trách nhiệm kiểm soát phân quyền Orders API |

Giả sử **test thực sự chứng minh lỗi**: A nhận HTTP 200 cùng nội dung đơn B. Đây là phát hiện bảo mật, vì đã có bằng chứng một trường hợp truy cập trái phép; nếu chưa chạy test thì chỉ được xem là giả thuyết threat/risk cần xác minh.

### 6.2. Đánh giá trước khi sửa

- **Likelihood: Cao.** Lý do: API tiếp cận qua Internet; người dùng chỉ cần đăng nhập và đổi ID; kịch bản đã được integration test xác nhận.
- **Impact: Cao.** Lý do: có khả năng lộ thông tin khách hàng; cần xác định thực tế số lượng bản ghi, mức nhạy cảm và hậu quả liên quan.
- **Risk: Cao** theo ma trận mẫu.
- **Confidence: Cao đối với việc lỗi tồn tại trên bản build đã thử**, nhưng mức độ phơi nhiễm của toàn hệ thống còn phải xác minh thêm.
- **Hành động:** đánh dấu phát hiện, xác định endpoint tương tự, sửa phân quyền, áp dụng biện pháp giảm thiểu tạm thời hoặc hoãn chức năng theo thẩm quyền.

Kết luận trên là **ví dụ giả định để minh họa phương pháp**, không phải kết quả kiểm thử của một hệ thống thật.

### 6.3. Thiết kế control và yêu cầu kiểm chứng

Control phù hợp là kiểm tra quyền ngay trước khi trả dữ liệu, dựa trên danh tính đáng tin và quan hệ với đối tượng, cùng chính sách cho trường hợp được ủy quyền. Ở tầng dữ liệu, có thể dùng truy vấn **theo ID đơn hàng và customer ID từ context xác thực**, thay vì lấy customer ID do client tự khai.

Một bài kiểm thử tích hợp Spring Boot minh họa bằng **MockMvc** (giả định test environment có dữ liệu đơn B và Spring Security Test được thiết lập):

~~~java
@Test
void userAIsDeniedWhenReadingUserBOrder() throws Exception {
    mockMvc.perform(
            get("/api/orders/{id}", orderOwnedByB)
                .with(jwt().jwt(token ->
                    token.subject("user-A")))
        )
        .andExpect(status().isNotFound());
}
~~~

- Đây là trích đoạn **minh họa**, không phải file test hoàn chỉnh. Cần có mockMvc, orderOwnedByB, cấu hình ánh xạ danh tính token đến người dùng trong ứng dụng và fixture dữ liệu thực sự thuộc user B.
- Tùy thiết kế che giấu sự tồn tại tài nguyên, ứng dụng có thể trả **403** hoặc **404** khi không đủ quyền; test phải theo chính sách đã định. Trong mọi trường hợp **không được trả dữ liệu đơn B**.
- Token do Spring Security Test dựng cho tình huống kiểm thử **không thay thế** bằng chứng xác thực token thật tại gateway/production.
- Phải bổ sung các tình huống được phép, các vai trò được ủy quyền, endpoint khác, token thiếu/hết quyền và truy vấn qua đường phụ trợ.

### 6.4. Đánh giá sau khi đã sửa và kiểm thử lại

Giả sử nhóm đã triển khai kiểm tra quyền theo đối tượng và **đọc được bằng chứng test hồi quy đạt trên phiên bản và môi trường phù hợp**. Khi đó có thể xem xét:

| Yếu tố | Trước sửa, có test xác nhận lỗi | Sau sửa, có bằng chứng phù hợp |
| --- | --- | --- |
| Likelihood | **Cao**: đường truy cập trái phép khả thi và được chứng minh | **Thấp** trong phạm vi đã kiểm tra, nếu control đủ độ bao phủ |
| Impact nếu control thất bại | **Cao**: dữ liệu nhạy cảm có thể bị lộ | **Cao**: hậu quả tiềm năng của sự cố không tự giảm |
| Mức rủi ro theo ma trận ví dụ | **Cao** | **Trung bình** |
| Confidence | Cao về lỗi đã thấy, thấp hơn về toàn bộ phạm vi | Phụ thuộc số endpoint, test, bản phát hành và giám sát |
| Quyết định cần có | Xử lý hoặc giảm thiểu, chuyển cấp khi cần | Risk owner/cấp có quyền quyết định residual risk và việc phát hành |

Điểm mấu chốt là **không hạ risk chỉ vì PR đã merge**. Bằng chứng phải cho thấy control mới được triển khai và hoạt động, và những đường truy cập tương đương đã được đánh giá. Mức **Trung bình** ở đây vẫn có thể đòi hỏi hành động hoặc chuyển cấp, tùy chính sách.

### 6.5. Mẫu risk record định tính

Mẫu YAML dưới đây mô tả bản ghi **minh họa trước khi sửa**, nên trạng thái chưa được đánh dấu hoàn tất:

~~~yaml
risk_id: "RISK-ORDERS-DEMO-003"
title: "Truy cap cheo don hang qua ID"
assessment_scope:
  service: "orders-api"
  version: "build-truoc-phat-hanh"
  environment: "integration-test"
  timeframe: "dot-phat-hanh-hien-tai"
asset: "Du lieu don hang khach hang"
threat_event: "User A thay ID de xem don cua User B"
vulnerability: "Thieu kiem tra authorization theo doi tuong"
security_objective: "Chi nguoi duoc cap quyen moi xem du lieu"
likelihood:
  level: "CAO"
  rationale: "Test A truy cap don B tra du lieu thanh cong"
impact:
  level: "CAO"
  rationale: "Co the lo du lieu khach hang"
qualitative_risk: "CAO"
assessment_confidence: "CAO_CHO_KICH_BAN_DA_THU"
evidence:
  ref: "TEST-DEMO-ORDERS-017"
  verified_production: false
control_owner: "Truong nhom Orders API"
risk_owner: "Chu so huu san pham Orders"
treatment:
  strategy: "MITIGATE"
  next_action: "Sua phan quyen va kiem thu hoi quy"
  verification_status: "PENDING"
residual_risk:
  level: "CHUA_DANH_GIA"
  reason: "Chua co bang chung kiem thu lai ban sua"
~~~

Tên ID, phiên bản và dữ liệu trong mẫu **không phải dữ liệu của hệ thống thực**. Một hồ sơ vận hành phải có thời điểm, người đánh giá, đường dẫn tới test run, cam kết khắc phục, hạn thực hiện, reviewer và quyết định của cấp có thẩm quyền.

## 7. Cách xây tiêu chí định tính ít chủ quan hơn

### 7.1. Dùng ví dụ neo mức (*anchors*)

Đối với từng mức Thấp/Trung bình/Cao, chuẩn bị những ví dụ gắn với loại tài sản và quy mô tổ chức. Ví dụ với impact:

- **Thấp:** gián đoạn nội bộ trong phạm vi nhỏ, khôi phục bằng quy trình thông thường, không ảnh hưởng dữ liệu quan trọng.
- **Trung bình:** gián đoạn một chức năng có ảnh hưởng tới khách hàng hoặc cần khắc phục phối hợp, nhưng hậu quả có giới hạn.
- **Cao:** lộ dữ liệu nhạy cảm trên diện rộng, sửa đổi giao dịch trọng yếu hoặc ảnh hưởng lớn đến tính liên tục kinh doanh.

Không sử dụng những mô tả vòng tròn như **“Cao vì nguy hiểm lớn”**. Mỗi mức cần có dấu hiệu quan sát, ví dụ loại dữ liệu, phạm vi sử dụng, thời gian phục hồi hay mức thiệt hại được công ty công nhận.

### 7.2. Hiệu chỉnh qua cùng một tập tình huống

Cho nhiều nhóm độc lập xếp mức cho một số risk scenario mẫu, rồi cùng phân tích sự khác biệt:

- Có người đánh giá khả năng từ góc nhìn **không có control**, người khác đánh giá sau control?
- Có người lấy hậu quả tối đa, người khác lấy hậu quả điển hình?
- Có nhóm hiểu “Cao” là cần báo ngay, nhóm khác hiểu là lỗi nghiêm trọng kỹ thuật?
- Có chứng cứ nào bị bỏ sót hoặc áp dụng nhầm môi trường?
- Có thiếu phân biệt giữa **severity lỗ hổng** và **risk kinh doanh**?

Sau buổi hiệu chỉnh, cập nhật hướng dẫn chấm mức và ghi lại những ví dụ chuẩn. Mục tiêu không phải bắt mọi người đồng ý bằng hình thức, mà là giúp **hai người cùng tiêu chí sẽ có thể giải thích rõ vì sao kết luận giống hoặc khác nhau**.

### 7.3. Tách mức độ rủi ro và mức độ chắc chắn

Thay vì một nhãn duy nhất, hiển thị hai thông tin:

| Rủi ro | Confidence | Ý nghĩa tác nghiệp |
| --- | --- | --- |
| **Cao** | **Cao** | Có bằng chứng rõ; ưu tiên xử lý và theo đúng đường chuyển cấp |
| **Cao** | **Thấp** | Có thể nghiêm trọng nhưng nhiều giả định; vừa giảm thiểu tạm thời vừa khẩn trương xác minh |
| **Thấp** | **Cao** | Có cơ sở để theo dõi ở nhịp phù hợp |
| **Thấp** | **Thấp** | Chưa đủ cơ sở để yên tâm; xác minh trước khi dựa vào mức Thấp để phê duyệt |

Đặc biệt với hệ thống chứa dữ liệu quan trọng, **thiếu bằng chứng** không nên được dùng để mặc định đánh giá thấp.

## 8. Những lỗi điển hình và cách tránh

| Lỗi | Vấn đề gây ra | Cách xử lý |
| --- | --- | --- |
| Chấm mức cho “lỗ hổng X” không có kịch bản | Không biết tài sản, đường tấn công và hậu quả | Viết threat event + điều kiện + tác động |
| Dùng CVSS trực tiếp làm risk kinh doanh | Bỏ qua dữ liệu, phơi nhiễm và control đặc thù | Dùng severity kỹ thuật làm **đầu vào**, đánh giá ngữ cảnh riêng |
| Cho likelihood thấp vì “chưa từng có sự cố” | Thiếu dữ liệu quan sát có thể bị hiểu sai thành an toàn | Kiểm tra khả năng tiếp cận và bằng chứng hiện có |
| Cho impact cao trong mọi trường hợp | Ma trận mất khả năng phân biệt ưu tiên | Hiệu chỉnh với tài sản, phạm vi và hậu quả hợp lý |
| Nhân điểm thứ bậc và coi là con số chính xác | Tạo chính xác giả và thứ hạng khó giải thích | Dùng tiêu chí, ma trận công khai và nhận định có căn cứ |
| Hạ residual risk vì “đã mua công cụ” | Control có thể chưa phủ toàn bộ hoặc không hoạt động | Yêu cầu test, cấu hình và bằng chứng vận hành |
| Đồng nhất "đã vá" với "đã xác minh" | Rủi ro có thể vẫn hiện diện | Kiểm thử lại và liên kết kết quả phiên bản tương ứng |
| Không ghi bất định và giả định | Người phê duyệt hiểu nhầm mức tin cậy | Ghi confidence và danh sách câu hỏi chưa xác minh |
| Risk owner không tham gia | Mức impact thiếu bối cảnh kinh doanh và quyết định thiếu thẩm quyền | Mời chủ sản phẩm/nghiệp vụ, xác định quyền phê duyệt |
| Không cập nhật sau thay đổi | Kết quả cũ không còn đúng | Gắn trigger đánh giá lại với CI/CD, cấu hình, sự cố và kiểm thử |

### 8.1. Tránh “đẹp bảng” nhưng mất an toàn

Nếu một tổ chức đặt mục tiêu “không còn rủi ro Cao”, các nhóm có thể bị thúc đẩy đổi nhãn thay vì sửa nguyên nhân. Cần giữ lịch sử điều chỉnh: ai thay đổi, khi nào, bằng chứng và control nào đã thay đổi. Đánh giá định tính nên là **công cụ để đưa quyết định**, không phải bảng điểm thành tích của đội phát triển.

## 9. Tổ chức thực hiện và phân quyền

| Vai trò | Đóng góp vào đánh giá |
| --- | --- |
| **Risk owner** | Xác định tác động kinh doanh, quyết định xử lý/chấp nhận trong quyền được giao |
| **Control owner** | Mô tả control, phạm vi, bằng chứng, điều kiện lỗi và kế hoạch khắc phục |
| **Security analyst/architect** | Phân tích threat scenario, điểm yếu, đường tấn công và tiêu chí bảo mật |
| **Developer và SRE/operations** | Cung cấp kiến trúc thực tế, cấu hình, test và log; triển khai xử lý |
| **Product/data owner** | Làm rõ giá trị dữ liệu, ảnh hưởng khách hàng, chính sách truy cập |
| **Assurance reviewer/audit** | Đánh giá tính phù hợp của bằng chứng, chỉ ra điểm chưa được xác minh |
| **Hội đồng bảo mật/cấp quản trị** | Giám sát rủi ro trọng yếu, gỡ vướng nguồn lực hoặc chuyển cấp theo thẩm quyền |

Với những kịch bản có hậu quả lớn hoặc bất đồng đáng kể, nên mời người đánh giá độc lập/cross-review phù hợp. Người trực tiếp triển khai control có thể cung cấp bằng chứng nhưng không tự biến đánh giá của mình thành **assurance độc lập** nếu thiếu cơ chế kiểm tra chéo.

### 9.1. Đầu ra và điều kiện hoàn tất

Một vòng đánh giá định tính chỉ có thể xem là **hoàn tất về mặt quy trình** khi có:

1. Phạm vi, kỳ đánh giá và phiên bản cụ thể.
2. Các risk scenario đủ rõ, gắn tài sản và mục tiêu bảo mật.
3. Likelihood, impact, mức risk và **lý do cho từng mức**.
4. Mô tả control hiện tại, bằng chứng hỗ trợ, độ bao phủ và giới hạn.
5. Phân biệt inherent risk, residual risk thực tế và risk mục tiêu nếu có.
6. Confidence, giả định chưa xác minh, vấn đề cần theo dõi.
7. Risk owner/control owner/action owner, quyết định trong quyền và hạn thực hiện.
8. Kết quả xác minh khắc phục hoặc lịch kiểm tra lại, trigger đánh giá lại.
9. Hồ sơ phê duyệt và chuyển cấp phù hợp chính sách.

Việc hoàn thành biểu mẫu không tự cho phép **đóng phát hiện bảo mật**; phát hiện chỉ được đóng khi đạt tiêu chí khắc phục và kiểm chứng đã thống nhất.

## 10. Sơ đồ quyết định đánh giá rủi ro định tính

~~~mermaid
flowchart TD
    A["Xác định tài sản, mục tiêu và phạm vi"] --> B["Mô tả risk scenario cụ thể"]
    B --> C["Thu thập evidence về threat, exposure, control"]
    C --> D{"Bằng chứng đủ để đánh giá?"}
    D -- "Không" --> E["Ghi UNKNOWN / độ tin cậy thấp, yêu cầu xác minh"]
    E --> C
    D -- "Có" --> F["Xếp likelihood và giải thích"]
    F --> G["Xếp impact theo hậu quả thực tế"]
    G --> H["Áp dụng ma trận và ghi confidence"]
    H --> I["Đánh giá control, residual risk"]
    I --> J{"Mức risk có chấp nhận được theo thẩm quyền?"}
    J -- "Không hoặc vượt quyền" --> K["Chọn xử lý và chuyển cấp"]
    K --> L["Thực hiện, kiểm thử lại, cập nhật evidence"]
    L --> I
    J -- "Có, được phê duyệt" --> M["Ghi quyết định và điều kiện theo dõi"]
    M --> N["Đánh giá lại khi thay đổi hoặc đến kỳ"]
    N --> B
~~~

Trong thực tế, ngay cả khi bằng chứng chưa đủ vẫn có thể cần **biện pháp phòng ngừa tạm thời hoặc chuyển cấp ngay** nếu hậu quả tiềm năng rất lớn. Nhánh “Chưa đủ” không phải lệnh tạm dừng quản lý rủi ro.

## 11. Checklist dùng trong buổi workshop

- [ ] Đã thống nhất hệ thống, phiên bản, môi trường và thời gian đánh giá.
- [ ] Đã nêu tài sản, mục tiêu bảo mật và hậu quả kinh doanh có liên quan.
- [ ] Kịch bản mô tả rõ threat, điều kiện, đường tiếp cận và kết quả bất lợi.
- [ ] Đã phân biệt sự kiện giả định với phát hiện hoặc incident được xác nhận.
- [ ] Có thang likelihood/impact với mô tả thống nhất, ví dụ neo mức rõ ràng.
- [ ] Đã ghi dữ liệu và lý do cho từng kết luận likelihood/impact.
- [ ] Đã xem tác động bí mật, toàn vẹn, sẵn sàng và các nghĩa vụ liên quan.
- [ ] Control hiện có có owner, phạm vi và bằng chứng hiệu lực.
- [ ] Inherent risk và residual risk sử dụng giả định nhất quán.
- [ ] Có **confidence**, giả định và câu hỏi còn chưa xác minh.
- [ ] Phương án xử lý phù hợp mức rủi ro và quyền ra quyết định.
- [ ] Có người thực hiện, thời hạn, điều kiện đóng và retest khi cần.
- [ ] Có trigger đánh giá lại sau thay đổi hoặc bằng chứng mới.
- [ ] Kết luận được lưu cùng bằng chứng cho kiểm thử, audit và vận hành.

Checklist này hỗ trợ tính nhất quán của quy trình, **không thay thế** phân tích chuyên sâu khi rủi ro, yêu cầu pháp lý hoặc hậu quả thực tế đòi hỏi mức bảo đảm cao hơn.

## 12. Câu hỏi tự kiểm tra

1. Tại sao không nên đánh giá rủi ro chỉ bằng tên một lỗ hổng hoặc điểm CVSS?
2. Likelihood “Thấp” và Confidence “Thấp” khác nhau về ý nghĩa và hành động tiếp theo thế nào?
3. Hãy lập risk scenario từ tình huống API cho phép người dùng A đọc đơn hàng của B, nêu tài sản, threat event, điểm yếu và hậu quả.
4. Sau khi thêm authorization theo đối tượng, tại sao impact tiềm năng có thể vẫn là “Cao” dù likelihood giảm?
5. Nếu báo cáo pentest chỉ áp dụng cho bản build trước, có thể dùng kết quả đó để khẳng định residual risk của bản đang chạy là Thấp không?
6. Ma trận 3 × 3 có thể bỏ sót vấn đề gì khi likelihood Thấp nhưng impact cực lớn?
7. Một control đã triển khai nhưng chưa được kiểm thử lại. Nên ghi trạng thái bằng chứng và residual risk ra sao?
8. Risk owner, control owner và người đánh giá độc lập khác nhau thế nào trong quy trình phê duyệt?
9. Hãy nêu hai điều kiện cần xem xét lại mức rủi ro ngoài lịch đánh giá định kỳ.
10. Vì sao không thể hiểu tỷ lệ “70% rủi ro thấp” là “hệ thống an toàn 70%”?

## 13. Ghi nhớ

**Phương pháp định tính** biến thông tin chưa hoàn hảo về threat, điểm yếu, hậu quả và control thành **nhận định rủi ro có tiêu chí, có lý do và có khả năng giải trình**. Một đánh giá tốt phải mô tả risk scenario rõ, chấm likelihood và impact theo thang đã hiệu chỉnh, nêu giới hạn của ma trận, tách **mức risk** khỏi **confidence**, và chỉ giảm residual risk dựa trên hiệu quả control đã được kiểm chứng. Trong chương trình **security assurance liên tục**, quyết định rủi ro luôn đi kèm bằng chứng, người có thẩm quyền, kế hoạch khắc phục và cơ chế đánh giá lại khi hệ thống thay đổi.
