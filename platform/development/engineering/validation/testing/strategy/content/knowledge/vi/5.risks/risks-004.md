# Ghi nhận độ bất định và giới hạn của việc chấm điểm rủi ro

**Chương:** Rủi ro  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Chấm điểm rủi ro giúp nhóm sắp xếp những điều có thể gây hại cho sản phẩm và quyết định nên tập trung kiểm thử vào đâu. Tuy nhiên, một con số như `12` hoặc nhãn “cao” không thể mô tả đầy đủ mức độ hiểu biết của nhóm về rủi ro. Điểm số thường được tạo từ các ước lượng, thang phân loại và giả định; dữ liệu có thể thiếu, tình huống có thể thay đổi và các rủi ro có thể phụ thuộc lẫn nhau.

Nếu coi điểm số là sự thật chính xác, nhóm có thể ưu tiên sai, bỏ qua rủi ro nghiêm trọng nhưng ít gặp hoặc tạo cảm giác an toàn giả. Bài học này giải thích cách ghi nhận độ bất định, nhận biết giới hạn của các phương pháp chấm điểm và sử dụng kết quả một cách thận trọng trong chiến lược kiểm thử.

Sau bài học, người học có thể:

- Phân biệt rủi ro, điểm rủi ro và độ bất định của một ước lượng.
- Giải thích vì sao thang điểm định tính không tạo ra phép đo chính xác.
- Ghi lại bằng chứng, giả định, khoảng ước lượng và mức độ tin cậy.
- Nhận biết các sai lệch và giới hạn thường gặp của ma trận rủi ro.
- Dùng thông tin về độ bất định để chọn hoạt động kiểm thử, biện pháp giảm thiểu và thời điểm đánh giá lại.

## 1. Rủi ro và điểm rủi ro là hai thứ khác nhau

Rủi ro là khả năng một sự kiện hoặc điều kiện không chắc chắn xảy ra và gây ra hậu quả đối với mục tiêu. Trong kiểm thử phần mềm, rủi ro có thể liên quan đến sản phẩm hoặc quá trình dự án.

- **Rủi ro sản phẩm:** phần mềm có thể hoạt động sai hoặc không đáp ứng thuộc tính chất lượng. Ví dụ: giao dịch bị ghi nhận hai lần, dữ liệu bị lộ, trang thanh toán phản hồi quá chậm.
- **Rủi ro dự án:** hoạt động phát triển hoặc kiểm thử có thể không đạt kế hoạch. Ví dụ: môi trường kiểm thử không sẵn sàng, thiếu dữ liệu đại diện hoặc chuyên gia nghiệp vụ không thể tham gia đúng thời điểm.

Điểm rủi ro là cách biểu diễn giản lược để hỗ trợ so sánh hoặc phân loại. Một mô hình thường gặp là:

\[
\text{Điểm rủi ro} = \text{Điểm khả năng xảy ra} \times \text{Điểm tác động}
\]

Ví dụ, nhóm chấm khả năng xảy ra là 3 và mức tác động là 5, nên điểm rủi ro bằng 15. Con số 15 là kết quả của quy ước chấm điểm mà nhóm đã chọn. Nó không có nghĩa rủi ro có xác suất 15%, cũng không có nghĩa hậu quả lớn gấp ba lần một rủi ro có điểm 5.

Để hiểu một điểm số, người đọc cần biết ít nhất thang điểm, định nghĩa từng mức, khoảng thời gian đánh giá, bối cảnh, bằng chứng và các giả định được sử dụng.

## 2. Độ bất định nằm ở đâu?

Độ bất định là mức độ chưa chắc chắn trong hiểu biết hoặc ước lượng về một rủi ro. Nhóm có thể không biết chính xác tần suất lỗi, mức thiệt hại, phạm vi ảnh hưởng hoặc hiệu quả của biện pháp kiểm soát.

Ví dụ, nhóm đánh giá khả năng lỗi callback thanh toán ở mức “có thể xảy ra”. Nhưng dữ liệu lịch sử chỉ có vài lần thử nghiệm, chưa có số liệu ở tải cao và chưa xác minh đầy đủ cách nhà cung cấp gửi lại callback. Điểm khả năng xảy ra có thể là 3, nhưng mức độ tin cậy của ước lượng này thấp.

Vì vậy, cần ghi riêng hai thông tin:

- **Mức rủi ro được ước lượng:** nhóm đang đánh giá rủi ro ở mức thấp, trung bình hay cao theo thang đã thống nhất.
- **Mức độ tin cậy của ước lượng:** bằng chứng và hiểu biết hiện có hỗ trợ đánh giá đó mạnh đến đâu.

Một rủi ro được chấm thấp nhưng có độ tin cậy thấp cần được xem xét thêm. “Chưa có bằng chứng cho thấy lỗi xảy ra thường xuyên” không đồng nghĩa với “đã có bằng chứng rằng lỗi hiếm khi xảy ra”.

### 2.1. Phân biệt bất định do thiếu hiểu biết và biến thiên tự nhiên

Có thể phân biệt hai nguồn bất định để chọn cách xử lý:

- **Bất định do thiếu hiểu biết (epistemic uncertainty):** xuất hiện vì nhóm chưa có đủ dữ liệu hoặc chưa hiểu đầy đủ hệ thống. Ví dụ: chưa biết dịch vụ thanh toán xử lý callback lặp như thế nào. Có thể giảm loại bất định này bằng nghiên cứu, đo đạc, thử nghiệm và thu thập thêm bằng chứng.
- **Biến thiên ngẫu nhiên (aleatory variability):** xuất hiện do bản chất biến động của hoạt động. Ví dụ: lưu lượng người dùng thay đổi theo giờ, độ trễ mạng thay đổi theo điều kiện kết nối. Có thể mô tả biến thiên bằng phân bố hoặc khoảng quan sát; thường không thể loại bỏ hoàn toàn.

Trong thực tế, hai nguồn này có thể cùng tồn tại. Lưu lượng vừa biến động tự nhiên, vừa có thể được ước lượng kém vì nhóm chưa có dữ liệu của mùa cao điểm. Phân biệt chúng giúp nhóm biết nên thu thập thêm thông tin hay chuẩn bị hệ thống để chịu được biến động.

### 2.2. Những câu hỏi làm lộ độ bất định

Khi đánh giá một rủi ro, hãy hỏi:

- Ước lượng dựa trên dữ liệu thực tế, ý kiến chuyên gia hay giả định?
- Dữ liệu có đủ lớn, mới và đại diện cho môi trường sắp triển khai không?
- Có phần nào của hệ thống hoặc chuỗi phụ thuộc chưa được quan sát?
- Khoảng hậu quả có thể xảy ra rộng đến đâu?
- Những giả định nào nếu sai sẽ làm thay đổi thứ hạng rủi ro?
- Có sự kiện hoặc phép đo nào có thể xác nhận hay bác bỏ giả định?

Không phải mọi câu hỏi đều cần một con số. Ghi rõ điều chưa biết và cách tìm hiểu thường có giá trị hơn việc tạo ra một ước lượng có vẻ chính xác nhưng không có căn cứ.

## 3. Những giới hạn của thang điểm và ma trận rủi ro

Ma trận rủi ro thường đặt khả năng xảy ra trên một trục và mức tác động trên trục còn lại. Mỗi trục được chia thành một số mức, sau đó các ô được gán nhãn hoặc màu như thấp, trung bình, cao và rất cao.

Ví dụ về thang điểm minh họa cho một chu kỳ phát hành:

| Điểm khả năng | Mô tả tham khảo trong một chu kỳ phát hành |
|---:|---|
| 1 | Hiếm: dưới 5% |
| 2 | Ít có khả năng: từ 5% đến dưới 20% |
| 3 | Có thể: từ 20% đến dưới 50% |
| 4 | Có khả năng cao: từ 50% đến 80% |
| 5 | Gần như chắc chắn: trên 80% |

Các khoảng trên chỉ là ví dụ. Tổ chức cần điều chỉnh theo loại hệ thống, dữ liệu và khoảng thời gian. Nếu nhóm không có cơ sở ước lượng xác suất, nên dùng mô tả định tính và nói rõ đó là nhận định chuyên gia, không nên giả vờ rằng các tỷ lệ đã được đo.

Một thang tác động cũng cần định nghĩa theo hậu quả, chẳng hạn:

| Điểm tác động | Mô tả tham khảo |
|---:|---|
| 1 | Rất nhỏ: ảnh hưởng hạn chế, dễ khắc phục, không làm gián đoạn luồng chính |
| 2 | Nhỏ: ảnh hưởng một nhóm nhỏ, có cách xử lý tạm thời rõ ràng |
| 3 | Trung bình: làm gián đoạn một chức năng quan trọng hoặc cần can thiệp đáng kể |
| 4 | Lớn: ảnh hưởng nhiều người dùng, gây gián đoạn dịch vụ hoặc tổn thất đáng kể |
| 5 | Nghiêm trọng: mất dữ liệu, thiệt hại lớn, ảnh hưởng an toàn hoặc vi phạm nghĩa vụ quan trọng |

Định nghĩa tác động phải phản ánh bối cảnh. Với một hệ thống, vài phút gián đoạn có thể chấp nhận được; với hệ thống khác, cùng khoảng gián đoạn có thể gây hậu quả nghiêm trọng.

### 3.1. Thang điểm thường là thang thứ bậc

Trong nhiều ma trận, các mức 1 đến 5 chỉ biểu thị thứ tự từ thấp đến cao. Khoảng cách giữa mức 1 và 2 không nhất thiết bằng khoảng cách giữa mức 4 và 5. Đây là thang thứ bậc, không phải thang đo có đơn vị bằng nhau.

Do đó, phép nhân `khả năng × tác động` là một quy ước xếp hạng hữu ích trong một số bối cảnh, nhưng không phải phép đo toán học chính xác của tổn thất. Hai rủi ro có thể cùng điểm 5 nhưng rất khác nhau: một rủi ro gần như chắc chắn gây bất tiện nhỏ (5 × 1), trong khi một rủi ro hiếm có thể gây thiệt hại nghiêm trọng (1 × 5).

Nếu nhóm dùng các khoảng xác suất hoặc giá trị thiệt hại thực tế, cần nói rõ cách quy đổi thành điểm. Không nên gán cho các con số thứ bậc ý nghĩa định lượng mà chúng không có.

### 3.2. Ranh giới giữa các mức có thể làm thay đổi kết luận

Một ước lượng nằm gần ranh giới có thể được xếp vào hai mức khác nhau chỉ vì cách diễn giải của người chấm. Chẳng hạn, xác suất 19% có thể được chấm mức 2, trong khi 20% được chấm mức 3. Chênh lệch nhỏ về ước lượng có thể làm màu của ô thay đổi mạnh.

Để hạn chế vấn đề này:

- Định nghĩa rõ các khoảng và ví dụ cho từng mức.
- Cho phép ghi khoảng hoặc mức nằm giữa khi dữ liệu chưa đủ.
- Nêu rõ lý do khi xếp một rủi ro ở gần ranh giới.
- Kiểm tra xem thay đổi nhỏ trong giả định có làm thay đổi quyết định hay không.

### 3.3. Điểm tổng có thể che khuất loại hậu quả

Một điểm tổng hợp có thể làm mất thông tin quan trọng về bản chất hậu quả. Rủi ro mất dữ liệu, rủi ro vi phạm quyền riêng tư và rủi ro giao diện phản hồi chậm có thể cùng được xếp vào một mức “cao”, nhưng cách kiểm soát và người có quyền chấp nhận chúng rất khác nhau.

Hãy giữ các chiều tác động quan trọng riêng biệt khi cần thiết, ví dụ tác động đến người dùng, dữ liệu, tài chính, pháp lý, an toàn và hoạt động vận hành. Ràng buộc bắt buộc hoặc hậu quả nghiêm trọng không nên bị bù trừ bởi điểm tốt ở chiều khác.

### 3.4. Ma trận không thể hiện đầy đủ quan hệ giữa các rủi ro

Các rủi ro thường có quan hệ phụ thuộc. Một sự cố mạng có thể làm callback bị trễ, dẫn đến thử lại, gây tải tăng và làm trạng thái đơn hàng không nhất quán. Nếu đánh giá từng rủi ro độc lập, nhóm có thể bỏ qua hiệu ứng dây chuyền hoặc đếm cùng một nguyên nhân nhiều lần.

Với các chuỗi phụ thuộc quan trọng, hãy mô tả quan hệ nguyên nhân và hậu quả, dùng sơ đồ luồng hoặc phân tích kịch bản. Điểm số riêng lẻ chỉ là một phần của bức tranh.

## 4. Ghi nhận độ bất định trong hồ sơ rủi ro

Một hồ sơ rủi ro hữu ích cần cho người đọc biết nhóm đã đánh giá điều gì, dựa trên căn cứ nào và còn chưa biết điều gì. Ngoài điểm khả năng và tác động, nên ghi các thông tin sau:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Mô tả rủi ro | Nguyên nhân, sự kiện có thể xảy ra và hậu quả |
| Phạm vi và thời hạn | Thành phần, nhóm người dùng, môi trường và khoảng thời gian đánh giá |
| Điểm hoặc mức rủi ro | Kết quả theo thang đã thống nhất |
| Bằng chứng | Số liệu, sự cố trước đây, kết quả thử nghiệm, tài liệu hoặc ý kiến chuyên gia |
| Giả định | Điều đang được tạm coi là đúng để đưa ra ước lượng |
| Độ tin cậy | Mức cao, trung bình hoặc thấp cùng lý do |
| Khoảng hoặc kịch bản | Mức thấp nhất, điển hình, cao nhất hợp lý hoặc các tình huống khác nhau |
| Yếu tố chưa biết | Thông tin còn thiếu và tác động có thể có đến kết luận |
| Biện pháp kiểm soát | Cách giảm khả năng xảy ra hoặc giảm hậu quả |
| Rủi ro còn lại | Mức rủi ro sau khi áp dụng biện pháp kiểm soát |
| Chủ sở hữu và ngày xem xét | Người theo dõi, thời điểm cập nhật và điều kiện cần xem xét sớm |

### 4.1. Dùng mức độ tin cậy có định nghĩa

Có thể dùng ba mức đơn giản:

- **Cao:** có dữ liệu mới, đủ đại diện và liên quan trực tiếp đến môi trường hoặc hành vi đang đánh giá; các giả định quan trọng đã được kiểm chứng.
- **Trung bình:** có một phần dữ liệu hoặc bằng chứng phù hợp, nhưng còn giới hạn về quy mô, độ mới hoặc khả năng đại diện.
- **Thấp:** chủ yếu dựa trên giả định, ý kiến hoặc dữ liệu ít, cũ hay khác biệt đáng kể so với bối cảnh dự kiến.

Đây cũng là thang định tính, vì vậy cần ghi lý do. Hai người chấm có thể hiểu “trung bình” khác nhau nếu không có tiêu chí chung. Khi cần so sánh giữa nhiều nhóm, hãy thống nhất định nghĩa và ví dụ trước.

Không nên tự động cộng điểm bất định vào điểm rủi ro theo một công thức tùy ý. Thay vào đó, hiển thị điểm rủi ro và độ tin cậy cạnh nhau, rồi xác định hành động cần thiết. Rủi ro có điểm cao và độ tin cậy thấp có thể cần kiểm soát ngay đồng thời thu thập thêm bằng chứng. Rủi ro có điểm thấp và độ tin cậy thấp cũng cần được xem xét để tránh bỏ sót.

### 4.2. Ghi khoảng và kịch bản thay vì một con số duy nhất

Khi có thể, hãy ghi khoảng ước lượng hoặc một vài kịch bản:

- **Kịch bản thuận lợi:** điều kiện tốt, các kiểm soát hoạt động như dự kiến.
- **Kịch bản điển hình:** điều kiện có khả năng gặp nhất theo bằng chứng hiện có.
- **Kịch bản bất lợi hợp lý:** một hoặc nhiều giả định quan trọng không đúng, khiến hậu quả tăng.

Ví dụ, thời gian phục hồi của một dịch vụ phụ thuộc có thể được ước lượng là 5–10 phút trong điều kiện thông thường, nhưng có thể kéo dài 30–60 phút nếu nhà cung cấp gặp sự cố diện rộng. Ghi cả hai kịch bản giúp nhóm thấy được phạm vi hậu quả và nhu cầu có phương án dự phòng.

Không nên tạo ra khoảng số chỉ để làm hồ sơ trông đầy đủ. Khoảng phải có căn cứ hoặc được ghi rõ là giả định cần kiểm chứng.

## 5. Ví dụ: đánh giá rủi ro callback thanh toán

Giả sử cửa hàng trực tuyến nhận callback từ cổng thanh toán để cập nhật trạng thái giao dịch. Nếu callback bị mất hoặc xử lý lặp, đơn hàng có thể ở trạng thái sai hoặc giao dịch có thể bị ghi nhận nhiều lần.

### 5.1. Đánh giá ban đầu

Nhóm sử dụng thang khả năng và tác động 1–5 đã định nghĩa cho một chu kỳ phát hành:

| Thành phần | Đánh giá minh họa |
|---|---|
| Nguyên nhân | Callback bị trễ, mất hoặc gửi lại trong điều kiện mạng không ổn định |
| Sự kiện | Hệ thống không xử lý callback đúng một lần hoặc không đối soát được trạng thái |
| Hậu quả | Đơn hàng có trạng thái sai, khách hàng bị thông báo sai hoặc phát sinh xử lý giao dịch thủ công |
| Khả năng | 3 – Có thể xảy ra |
| Tác động | 5 – Nghiêm trọng |
| Điểm rủi ro | 15 – mức cao theo ma trận giả định |
| Độ tin cậy | Thấp – chỉ có ít dữ liệu thử nghiệm, chưa mô phỏng tải cao và chưa xác minh đầy đủ cơ chế gửi lại của nhà cung cấp |
| Giả định | Nhà cung cấp có thể gửi lại callback; cùng một giao dịch có thể tạo nhiều thông báo |
| Điều chưa biết | Thứ tự callback, thời gian gửi lại tối đa và hành vi khi phản hồi bị mất |

Điểm 15 giúp đưa rủi ro vào nhóm cần ưu tiên. Độ tin cậy thấp cho thấy nhóm chưa hiểu đủ cơ chế để kết luận khả năng xảy ra là chính xác. Không nên diễn giải điểm 15 như một xác suất hoặc dùng nó để khẳng định rủi ro đã được định lượng.

### 5.2. Thu thập thêm bằng chứng

Nhóm có thể giảm bất định bằng các hoạt động sau:

1. Xem tài liệu hợp đồng API và xác minh quy tắc gửi lại callback với nhà cung cấp.
2. Tạo thử nghiệm tích hợp cho callback trùng, callback đến sai thứ tự và callback đến sau thời hạn chờ.
3. Mô phỏng mất kết nối giữa lúc nhà cung cấp gửi thông báo và lúc cửa hàng ghi nhận kết quả.
4. Kiểm tra khả năng xử lý lặp bằng mã định danh giao dịch và cơ chế idempotency.
5. Đối chiếu log, bản ghi giao dịch và trạng thái đơn hàng để phát hiện sai lệch.

Sau khi có bằng chứng mới, nhóm cập nhật điểm, độ tin cậy, giả định và biện pháp kiểm soát. Nếu bằng chứng cho thấy khả năng xảy ra thấp hơn, điểm có thể giảm; nhưng hậu quả nghiêm trọng vẫn cần được kiểm soát bằng thiết kế và kiểm thử phù hợp.

### 5.3. Chọn biện pháp và kiểm thử

Biện pháp có thể gồm lưu mã định danh callback đã xử lý, bảo đảm cập nhật trạng thái có tính lặp an toàn, đối soát giao dịch và cảnh báo khi trạng thái không nhất quán. Các kiểm thử cần xác minh cả hành vi bình thường lẫn trường hợp lỗi, gửi lại và phục hồi.

Sau khi kiểm soát được triển khai, hãy đánh giá **rủi ro còn lại**. Không nên tự động đặt điểm rủi ro bằng 0 chỉ vì đã có thêm cơ chế xử lý. Cần kiểm tra bằng chứng rằng biện pháp thực sự hoạt động và ghi rõ những tình huống vẫn còn có thể gây hậu quả.

## 6. Những yếu tố làm sai lệch điểm rủi ro

Chấm điểm có yếu tố phán đoán của con người. Một số sai lệch thường gặp gồm:

- **Neo vào con số đầu tiên:** người tham gia có xu hướng giữ nguyên ước lượng ban đầu dù xuất hiện bằng chứng mới.
- **Thiên lệch sẵn có:** sự cố vừa xảy ra hoặc dễ nhớ được đánh giá là thường xuyên hơn thực tế; sự cố hiếm nhưng nghiêm trọng có thể bị xem nhẹ.
- **Lạc quan quá mức:** nhóm đánh giá thấp khả năng lỗi vì tin rằng thiết kế hoặc kiểm soát mới chắc chắn sẽ hoạt động.
- **Áp lực thời hạn hoặc mục tiêu:** điểm bị hạ để dễ đạt điều kiện phát hành hoặc bị nâng để xin thêm nguồn lực.
- **Khác biệt cách hiểu:** các thành viên dùng định nghĩa khác nhau cho “có thể xảy ra”, “nghiêm trọng” hoặc “đã kiểm soát”.
- **Đếm trùng hoặc bỏ sót:** cùng một nguyên nhân được ghi thành nhiều rủi ro riêng, hoặc một hậu quả dây chuyền không được xem xét.
- **Dữ liệu không đại diện:** số liệu từ môi trường thử nghiệm nhỏ được dùng để suy ra hành vi ở tải thật hoặc nhóm người dùng khác.

Để giảm sai lệch, hãy xác định thang điểm trước khi chấm, yêu cầu nêu bằng chứng và giả định, mời các vai trò có góc nhìn khác nhau, ghi lại bất đồng và xem xét độc lập các rủi ro có hậu quả nghiêm trọng. Khi cần, dùng dữ liệu sự cố, log và thử nghiệm để kiểm tra nhận định.

## 7. Từ điểm số đến quyết định kiểm thử

Điểm rủi ro có thể giúp sắp xếp công việc, nhưng quyết định kiểm thử cần xem thêm độ tin cậy, mức độ bao phủ, khả năng phát hiện và hậu quả nếu bỏ sót.

| Tình huống đánh giá | Hành động phù hợp |
|---|---|
| Điểm cao, độ tin cậy cao | Ưu tiên biện pháp giảm thiểu và kiểm thử sâu; theo dõi tiêu chí chấp nhận |
| Điểm cao, độ tin cậy thấp | Kiểm soát rủi ro trước mắt, đồng thời thu thập bằng chứng để xác minh giả định và phạm vi hậu quả |
| Điểm thấp, độ tin cậy cao | Có thể phân bổ mức kiểm thử tương xứng; vẫn theo dõi khi bối cảnh thay đổi |
| Điểm thấp, độ tin cậy thấp | Không kết luận rằng rủi ro an toàn; cần tìm hiểu thêm nếu hậu quả tiềm tàng đáng kể hoặc dữ liệu còn thiếu |

Một số nguyên tắc khi chuyển đánh giá thành hoạt động kiểm thử:

1. Kiểm thử các ràng buộc bắt buộc và rủi ro có hậu quả nghiêm trọng, kể cả khi khả năng xảy ra được đánh giá thấp.
2. Dùng độ bất định để tìm ra nơi cần kiểm thử thăm dò, thử nghiệm chịu lỗi, đo tải hoặc xác minh hợp đồng.
3. Chọn mức kiểm thử dựa trên hậu quả, phạm vi ảnh hưởng, khả năng phát hiện và khả năng phục hồi, không chỉ dựa vào tích hai con số.
4. Ghi lại rủi ro chưa được kiểm thử, lý do, người chấp nhận và biện pháp theo dõi.
5. Cập nhật đánh giá khi có kết quả kiểm thử, sự cố mới, thay đổi kiến trúc hoặc thay đổi môi trường.

### 7.1. Phân biệt rủi ro vốn có và rủi ro còn lại

- **Rủi ro vốn có (inherent risk):** mức rủi ro trước khi tính đến các biện pháp kiểm soát cụ thể.
- **Rủi ro còn lại (residual risk):** mức rủi ro vẫn tồn tại sau khi đã áp dụng và đánh giá các biện pháp kiểm soát.

Hãy ghi rõ biện pháp nào đã được triển khai và có bằng chứng xác nhận hiệu quả hay chưa. Một biện pháp mới chỉ được đề xuất chưa làm giảm rủi ro thực tế. Nếu kiểm soát chưa được kiểm chứng, cần thận trọng khi hạ điểm rủi ro còn lại.

## 8. Khi nào nên dùng phân tích định lượng?

Ma trận định tính phù hợp khi dữ liệu ít, cần thảo luận nhanh hoặc phải sắp xếp nhiều rủi ro ở mức tổng quan. Với hệ thống quan trọng và có đủ dữ liệu, nhóm có thể dùng phân tích định lượng để hiểu phạm vi kết quả tốt hơn.

Các cách tiếp cận có thể gồm:

- **Khoảng xác suất và hậu quả:** ước lượng một khoảng thay vì một giá trị đơn, kèm nguồn dữ liệu và giả định.
- **Phân tích độ nhạy:** thay đổi từng giả định để xem yếu tố nào làm kết quả hoặc thứ hạng thay đổi mạnh nhất.
- **Phân tích kịch bản:** đánh giá tình huống thuận lợi, điển hình và bất lợi hợp lý, bao gồm các phụ thuộc quan trọng.
- **Mô phỏng Monte Carlo:** lấy mẫu từ các phân bố đầu vào để ước lượng phân bố kết quả, khi có căn cứ phù hợp cho các phân bố và mối tương quan.
- **Phân tích dữ liệu vận hành:** dùng tần suất sự cố, thời gian gián đoạn, tỷ lệ lỗi và tổn thất thực tế để hiệu chỉnh ước lượng.

Ví dụ, thay vì nói “dịch vụ có 90% khả năng phục hồi trong 10 phút”, nhóm có thể đo thời gian phục hồi qua nhiều lần thử nghiệm, báo cáo trung vị và phân vị cao, rồi phân tích các tình huống ngoại lệ. Nếu dữ liệu ít hoặc điều kiện thử khác xa môi trường thật, cần ghi rõ giới hạn áp dụng.

Mô phỏng không tự làm cho đầu vào đáng tin cậy. Nếu phân bố xác suất, dữ liệu hoặc quan hệ giữa các biến được giả định tùy tiện, kết quả có thể tạo ra độ chính xác giả. Chỉ dùng phương pháp định lượng phức tạp khi nó giúp quyết định tốt hơn và các giả định có thể giải thích, kiểm tra.

## 9. Theo dõi và cập nhật đánh giá rủi ro

Đánh giá rủi ro là hoạt động lặp lại. Một điểm số đúng tại thời điểm lập kế hoạch có thể trở nên lỗi thời khi sản phẩm hoặc môi trường thay đổi.

Nên xem xét lại rủi ro khi:

- Có thay đổi về kiến trúc, nhà cung cấp, giao thức hoặc thành phần phụ thuộc.
- Lưu lượng, nhóm người dùng, loại dữ liệu hoặc môi trường triển khai thay đổi đáng kể.
- Xuất hiện sự cố mới, lỗi lặp lại hoặc bằng chứng trái với giả định cũ.
- Một biện pháp kiểm soát được thay đổi, bị vô hiệu hóa hoặc chưa đạt kết quả kiểm thử.
- Có yêu cầu pháp lý, hợp đồng hoặc cam kết dịch vụ mới.
- Sắp đến mốc phát hành hoặc thời điểm đã hẹn để xem xét rủi ro.

Mỗi rủi ro quan trọng nên có chủ sở hữu, ngày cập nhật, điều kiện kích hoạt xem xét và trạng thái của biện pháp kiểm soát. Khi điểm số thay đổi, ghi lý do thay đổi và bằng chứng mới để người đọc hiểu vì sao thứ tự ưu tiên khác trước.

## 10. Những sai lầm thường gặp

### 10.1. Xem điểm số như xác suất chính xác

Điểm 15 từ hai thang thứ bậc không phải xác suất 15%. Hãy giải thích cách chấm và ý nghĩa giới hạn của con số.

### 10.2. Cho rằng điểm thấp đồng nghĩa với an toàn

Điểm thấp có thể xuất phát từ thiếu dữ liệu hoặc giả định lạc quan. Hãy xem độ tin cậy, hậu quả tiềm tàng và các điều chưa biết trước khi giảm mức kiểm thử.

### 10.3. Không ghi khoảng thời gian đánh giá

“Có khả năng xảy ra” không rõ nghĩa nếu không nói trong một chu kỳ phát hành, một tháng hay toàn bộ vòng đời. Mọi ước lượng cần gắn với khoảng thời gian và bối cảnh cụ thể.

### 10.4. Cộng gộp mọi hậu quả thành một điểm

Điểm tổng có thể che khuất loại tác động cần xử lý riêng. Giữ các hậu quả quan trọng và ràng buộc bắt buộc hiển thị rõ ràng.

### 10.5. Hạ điểm ngay khi đề xuất biện pháp kiểm soát

Một biện pháp trên tài liệu chưa chứng minh nó hoạt động. Chỉ đánh giá lại rủi ro còn lại sau khi có bằng chứng triển khai và kiểm thử thích hợp.

### 10.6. Không cập nhật giả định

Nếu dữ liệu mới mâu thuẫn với đánh giá cũ, phải xem xét lại điểm và độ tin cậy. Giữ nguyên con số chỉ vì đã được phê duyệt trước đó sẽ làm hồ sơ mất giá trị.

## 11. Danh sách rà soát hồ sơ rủi ro

Trước khi dùng điểm rủi ro để quyết định phạm vi hoặc độ sâu kiểm thử, hãy kiểm tra:

- [ ] Rủi ro mô tả rõ nguyên nhân, sự kiện và hậu quả.
- [ ] Phạm vi, môi trường và khoảng thời gian đánh giá được nêu rõ.
- [ ] Thang khả năng và tác động có định nghĩa nhất quán.
- [ ] Bằng chứng, nguồn dữ liệu và giả định được ghi lại.
- [ ] Độ tin cậy của ước lượng được đánh giá riêng với điểm rủi ro.
- [ ] Những điều chưa biết và khoảng hậu quả có thể xảy ra được ghi nhận.
- [ ] Rủi ro phụ thuộc và hậu quả dây chuyền đã được xem xét.
- [ ] Ràng buộc bắt buộc và hậu quả nghiêm trọng không bị che bởi điểm tổng.
- [ ] Biện pháp kiểm soát có bằng chứng về hiệu quả; rủi ro còn lại được đánh giá riêng.
- [ ] Có chủ sở hữu, ngày xem xét và điều kiện kích hoạt cập nhật.

## 12. Kết luận

Chấm điểm rủi ro là công cụ hỗ trợ thảo luận và ưu tiên, không phải phép đo chính xác cho mọi tình huống. Các thang điểm thường mang tính thứ bậc, phụ thuộc định nghĩa và phán đoán; điểm tổng có thể che khuất hậu quả, quan hệ phụ thuộc và những điều chưa biết.

Để sử dụng kết quả có trách nhiệm, hãy ghi rõ bằng chứng, giả định, khoảng thời gian, độ tin cậy và rủi ro còn lại. Khi độ bất định cao, cần xác định hoạt động thu thập thêm bằng chứng và giữ mức kiểm soát phù hợp với hậu quả tiềm tàng. Cập nhật đánh giá khi có thông tin mới để chiến lược kiểm thử luôn phản ánh bối cảnh thực tế.
