# Lean: Ra quyết định vào thời điểm có đủ thông tin cần thiết

Một nhóm phát triển hệ thống đăng ký workshop vừa nhận đề xuất: “Phải tích hợp ngay cổng gửi SMS để xác nhận đăng ký”. Họ có thể ký hợp đồng, thiết kế bảng dữ liệu và triển khai SMS từ tuần đầu. Nhưng chưa ai biết học viên thực sự cần SMS, email hay chỉ một màn hình trạng thái rõ ràng. Nếu cam kết với một nhà cung cấp quá sớm, nhóm có thể trả phí và xây một chức năng ít giá trị; nếu cứ chờ dữ liệu cho đến sát ngày mở đăng ký, nhóm lại không đủ thời gian kiểm tra bảo mật, tích hợp và phát hành.

**Lean khuyến khích ra quyết định khi đã có đủ thông tin cần thiết, nhưng không trễ đến mức đánh mất cơ hội hoặc gây hại.** Nguyên tắc thường được diễn đạt là *decide as late as possible* hoặc *defer commitment*: trì hoãn những **cam kết khó đảo ngược** trong khi chủ động học hỏi, giữ các phương án còn khả thi và quyết định trước thời điểm chậm nhất vẫn có thể thực hiện một cách có trách nhiệm (*last responsible moment*).

Điều đó **không có nghĩa trì hoãn mọi quyết định**. Có những việc phải quyết ngay để bảo vệ dữ liệu, đáp ứng nghĩa vụ pháp lý hoặc giữ tiến độ phụ thuộc; những việc dễ đảo ngược có thể quyết nhanh, triển khai nhỏ và học qua phản hồi. Mục tiêu là **giảm lãng phí do chọn giải pháp khi còn mù mờ**, chứ không phải thay thế việc giao sản phẩm bằng vô số cuộc họp.

Bài học thuộc mô-đun **AGILE_DEVELOPMENT**, hướng tới phát triển phần mềm thích ứng bằng phản hồi sớm, giao giá trị tăng dần và cải tiến liên tục. Những thực hành về user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc cung cấp phương tiện để **học đủ trước khi cam kết**, ra quyết định minh bạch và điều chỉnh khi dữ liệu thay đổi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Lean khuyến khích **trì hoãn cam kết khó đảo ngược** nhưng không cổ vũ chần chừ.
2. Phân biệt **thời điểm bắt đầu tìm hiểu**, **thời điểm quyết định**, **thời điểm triển khai** và **thời điểm nhận phản hồi**.
3. Nhận diện quyết định dễ đảo ngược, khó đảo ngược, có chi phí chuyển đổi lớn hoặc có hậu quả khẩn cấp.
4. Xác định thông tin **đủ để quyết định** thay vì chờ “biết mọi thứ”.
5. Đặt **mốc quyết định và điều kiện kích hoạt** dựa vào thời gian thực hiện, phụ thuộc, chi phí trì hoãn và rủi ro.
6. Sử dụng thử nghiệm nhỏ, nguyên mẫu, lát cắt dọc, thiết kế giữ nhiều phương án và dữ liệu quan sát để giảm bất định.
7. Phối hợp Product Owner, Developers, Scrum Master và các bên liên quan trong quyết định sản phẩm, kỹ thuật và quy trình.
8. Đánh giá một tình huống workshop từ yêu cầu đến quyết định, tính toán kịch bản và rút ra bài học qua bài tập thực hành.

## 2. Nguyên tắc Lean: trì hoãn cam kết, không trì hoãn học hỏi

Trong các nguyên tắc Lean Software Development, *decide as late as possible* nhấn mạnh lợi ích của việc **giữ quyền lựa chọn** khi còn những thông tin quan trọng sẽ sớm được khám phá. Một quyết định sớm có thể tạo ra **chi phí của việc phải sửa lại** khi giả định ban đầu sai. Ngược lại, trì hoãn quá mức có thể gây **chi phí chờ đợi, mất cơ hội, rủi ro tích lũy** và khiến nhóm không còn thời gian làm đúng.

### 2.1. Bốn mốc không nên đánh đồng

| Mốc | Ý nghĩa | Ví dụ đăng ký workshop |
| --- | --- | --- |
| **Bắt đầu tìm hiểu** | Nhận diện vấn đề, rủi ro và câu hỏi chưa có bằng chứng | Phỏng vấn học viên về việc không biết trạng thái |
| **Quyết định cam kết** | Chọn một phương án hoặc điều kiện triển khai có chi phí đổi hướng đáng kể | Ký hợp đồng SMS hoặc chốt dùng email cho giai đoạn đầu |
| **Bắt đầu triển khai** | Thực hiện công việc tạo Increment hoặc thực hiện nghĩa vụ | Tích hợp thông báo, viết test, kiểm tra quyền dữ liệu |
| **Nhận phản hồi thực** | Quan sát phần mềm hoạt động và kết quả người dùng | Đếm lượt hỏi lại, xem học viên hiểu trạng thái không |

Bốn mốc có thể gần nhau đối với thay đổi nhỏ. Với hợp đồng nhà cung cấp, thiết kế dữ liệu hoặc hạ tầng, chúng có thể cách nhau nhiều tuần.

**Học sớm, cam kết đúng lúc, giao giá trị liên tục** là cách hiểu phù hợp hơn “để mọi việc tới phút cuối”.

### 2.2. Thời điểm muộn nhất còn có trách nhiệm

*Last responsible moment* là **thời điểm muộn nhất mà nhóm vẫn có đủ thời gian, năng lực và phương án dự phòng để quyết định và thực hiện an toàn**. Qua mốc đó, việc tiếp tục chờ có thể gây mất cơ hội hoặc buộc nhóm đánh đổi chất lượng.

Không tồn tại “ngày thứ N của dự án” là mốc chung cho mọi quyết định. Nó phụ thuộc vào:

- **Thời hạn cần có kết quả:** ngày mở đăng ký, nghĩa vụ hợp đồng, đợt triển khai.
- **Lead time thực tế:** tìm hiểu, mua sắm, phát triển, review, kiểm thử, triển khai.
- **Mức bất định:** điều gì quan trọng còn chưa biết, thông tin mới sẽ đến khi nào.
- **Khả năng đảo ngược:** đổi quyết định có mất dữ liệu, phí phạt hay công sức lớn không.
- **Mức nguy hại nếu chậm:** lỗi bảo mật đang xảy ra, mất doanh thu, rủi ro pháp lý.
- **Khả năng dự phòng:** có thể chuyển sang phương án đơn giản hơn nếu thử nghiệm thất bại không.
- **Độ tin cậy của các ước lượng:** lịch nghỉ, phụ thuộc bên thứ ba, biến động công việc.

### 2.3. Một số hiểu lầm cần loại bỏ

- **Sai:** “Chưa quyết định tức là chưa cần làm gì.” **Đúng:** có thể đang làm việc quan trọng nhất: phỏng vấn, thử nghiệm, chia nhỏ hoặc thiết kế ranh giới giữ tùy chọn mở.
- **Sai:** “Cứ có thêm dữ liệu thì đợi tiếp.” **Đúng:** chỉ đợi nếu dữ liệu sắp có có khả năng **thay đổi lựa chọn** và giá trị của nó lớn hơn rủi ro trì hoãn.
- **Sai:** “Lean nói phải quyết mọi thứ càng muộn càng tốt.” **Đúng:** quyết sớm những việc cần thiết, khó hồi phục khi trễ hoặc có rủi ro cấp bách; trì hoãn cam kết không cần thiết.
- **Sai:** “Đã quyết là không được đổi.” **Đúng:** dùng bằng chứng mới để thích ứng, nhưng ghi rõ chi phí đổi hướng và trách nhiệm ra quyết định.
- **Sai:** “Giữ nhiều lựa chọn nghĩa là triển khai tất cả.” **Đúng:** có thể giữ **phương án kỹ thuật khả thi** mà chưa phải trả toàn bộ chi phí xây dựng chúng.

## 3. Phân loại quyết định trước khi lựa chọn thời điểm

Không phải quyết định nào cũng cần cùng độ nghiên cứu.

### 3.1. Quyết định dễ đảo ngược

Ví dụ:
- Thử một cách diễn đạt của nút đăng ký cho nhóm người dùng nhỏ.
- Điều chỉnh thứ tự hai câu hỏi trong khảo sát.
- Thay đổi cách trình bày dashboard nội bộ khi có thể hoàn tác.
- Thử WIP limit trên bảng Kanban trong một khoảng ngắn.

Nếu tác động nhỏ, chi phí đổi lại thấp và người dùng không chịu rủi ro đáng kể, nhóm có thể **quyết nhanh, triển khai nhỏ, quan sát và sửa**. Không cần hội đồng phê duyệt nhiều tầng.

### 3.2. Quyết định khó đảo ngược

Ví dụ:
- Ký hợp đồng nền tảng với mức cam kết dài hạn, phí rút lui lớn.
- Chọn mô hình dữ liệu khiến việc chuyển đổi sau này tốn công và có nguy cơ mất dữ liệu.
- Cam kết ngày phát hành công khai với đối tác khi phụ thuộc chưa được xác nhận.
- Thiết kế lưu dữ liệu cá nhân theo cách khó thay đổi vì yêu cầu pháp lý.
- Chuyển toàn bộ người dùng sang cơ chế đăng nhập mới không có kế hoạch quay lui.

Những quyết định này thường cần **thử nghiệm, đánh giá phụ thuộc, phương án dự phòng và người chịu trách nhiệm rõ**, đồng thời phải có hạn quyết định.

### 3.3. Quyết định phải làm sớm vì nguy cơ nếu chậm

Không nên trì hoãn:
- Chặn lỗ hổng đang làm lộ dữ liệu.
- Khôi phục dịch vụ đang ngừng hoạt động gây thiệt hại.
- Tuân thủ mốc pháp lý hoặc an toàn không thể lùi.
- Đặt lịch đánh giá bảo mật nếu nó là điều kiện trước khi phát hành.
- Mở đầu trao đổi với đối tác khi thời gian họ phản hồi kéo dài.

Ở đây nguyên tắc Lean không biện hộ cho việc chờ đủ bằng chứng hoàn hảo. Nhóm có thể ra **quyết định giảm thiểu rủi ro ngay**, sau đó tiếp tục học hỏi để chọn giải pháp bền vững.

### 3.4. Ma trận lựa chọn chiến lược quyết định

| Tác động / khả năng đảo ngược | Dễ đảo ngược | Khó đảo ngược |
| --- | --- | --- |
| **Tác động nhỏ** | Quyết nhanh, thử nhỏ, xem lại | Xác định chi phí đổi, thử giới hạn trước khi cam kết |
| **Tác động lớn** | Thử có kiểm soát, đặt guardrail và rollback | Thu bằng chứng sớm, đánh giá rủi ro/phụ thuộc, đặt mốc quyết định có dự phòng |
| **Đang gây hại nghiêm trọng** | Ưu tiên ứng phó, kiểm soát tác động | Ưu tiên quyết định an toàn với người có trách nhiệm; không chờ thí nghiệm dài |

Đây là **khung thực hành**, không phải bảng chuẩn bắt buộc trong Lean. “Dễ đảo ngược” phải được đánh giá cả về kỹ thuật lẫn **niềm tin người dùng, hợp đồng, quyền riêng tư và chi phí vận hành**.

## 4. “Đủ thông tin” là mức nào?

Câu hỏi khó nhất không phải “có nhiều dữ liệu chưa?” mà là **“Thông tin nào có thể làm thay đổi lựa chọn, và nếu chưa biết thì rủi ro khi quyết định là gì?”**

### 4.1. Phân biệt ba loại thông tin

| Loại thông tin | Ví dụ | Ý nghĩa đối với quyết định |
| --- | --- | --- |
| **Bắt buộc trước khi quyết** | Quy tắc xác nhận chỗ, nghĩa vụ bảo vệ dữ liệu, hạn ký hợp đồng | Thiếu có thể gây quyết định sai hoặc không hợp lệ |
| **Có ích và có thể thu sớm** | Học viên thực sự cần kênh thông báo nào; khả năng tích hợp của nhà cung cấp | Thu bằng phỏng vấn, nguyên mẫu hoặc thử nhỏ |
| **Có thể học sau bằng thay đổi an toàn** | Màu sắc thông báo nào dễ đọc hơn trong ngữ cảnh thực | Tránh giữ toàn bộ công việc chờ nghiên cứu chi tiết không quan trọng |

Cần giữ **độ chắc chắn phù hợp mức độ hậu quả**. Một nút giao diện dễ đổi thường chỉ cần dữ liệu đủ dùng; một cơ chế xử lý thanh toán đòi hỏi đánh giá nghiêm túc hơn nhiều.

### 4.2. Bộ câu hỏi quyết định tối thiểu

1. **Chính xác quyết định cần đưa ra là gì?** Không dùng nhãn mơ hồ như “chọn công nghệ tốt nhất”.
2. **Các phương án còn khả thi là gì?** Bao gồm phương án đơn giản hơn hoặc chưa làm.
3. **Tiêu chí thành công và rủi ro không được vượt là gì?**
4. **Chưa biết điều gì có thể đảo chiều thứ tự các phương án?**
5. **Có cách học rẻ và nhanh hơn việc triển khai toàn bộ không?**
6. **Chậm thêm một tuần sẽ mất gì?**
7. **Đến ngày nào phải quyết để còn đủ thời gian thực hiện và kiểm chứng?**
8. **Ai có trách nhiệm quyết định và ai cần được tham vấn?**
9. **Điều kiện nào khiến quyết định cần xem lại?**

Một quyết định có trách nhiệm có thể nói: “Chưa biết chắc 100%, nhưng đã biết các rủi ro trọng yếu, có đường quay lui và phương án phù hợp với mục tiêu; chờ thêm chưa chắc làm thay đổi lựa chọn.” Đó là **đủ thông tin**, không phải sự chắc chắn tuyệt đối.

### 4.3. Phân biệt sự kiện, giả định và phán đoán

Ví dụ:

- **Sự kiện quan sát:** 12 trong 20 người dùng thử hỏi lại trạng thái đăng ký.
- **Giả định:** thêm SMS sẽ làm số người hỏi lại giảm đáng kể.
- **Phán đoán:** thử cải thiện thông báo trên trang trước khi ký hợp đồng SMS là lựa chọn hợp lý.
- **Điều còn thiếu:** những người dùng khác có cần thông báo khi không mở trang không?

Việc ghi rõ các loại thông tin giúp nhóm tránh trình bày ý kiến cá nhân như bằng chứng thực nghiệm.

## 5. Giá trị của thông tin và chi phí trì hoãn

### 5.1. Vì sao học thêm có thể đáng giá?

Giả sử hai giải pháp đều có vẻ đáp ứng nhu cầu. Nếu thử nghiệm nhỏ cho thấy một giải pháp phù hợp hơn hẳn, nhóm tránh được chi phí tích hợp, bảo trì hoặc thay đổi dữ liệu của giải pháp kém phù hợp.

**Giá trị thông tin (value of information)** không đơn giản là số lượng báo cáo được đọc. Giá trị đến từ việc **thông tin đó có thể thay đổi quyết định tốt hơn** và ngăn chi phí lựa chọn sai.

Một thử nghiệm có thể đáng làm nếu:
- Câu hỏi thực sự ảnh hưởng lựa chọn.
- Có thể có câu trả lời trước mốc quyết định.
- Chi phí thử tương xứng với hậu quả của việc chọn nhầm.
- Kết quả được đo đủ tin cậy cho mục đích quyết định.
- Không tạo rủi ro chất lượng, quyền riêng tư hoặc an toàn không chấp nhận được.

### 5.2. Chi phí trì hoãn là gì?

**Cost of delay** là giá trị hoặc cơ hội có thể mất đi khi việc giao kết quả hoặc ra quyết định bị chậm. Nó có thể bao gồm:
- Người dùng tiếp tục gặp vấn đề và phải thao tác thủ công.
- Công việc hỗ trợ và sửa lỗi tiếp tục tiêu tốn năng lực.
- Bỏ lỡ đợt mở bán, đối tác hoặc mốc thị trường.
- Tiếp tục chịu rủi ro dữ liệu, bảo mật hoặc tuân thủ.
- Mất cơ hội nhận phản hồi thật để điều chỉnh giải pháp.

Không phải mọi chi phí đều quy đổi đáng tin thành tiền. Nhóm có thể dùng **mức ảnh hưởng, bằng chứng và giới hạn thời gian** thay vì dựng các con số chính xác giả.

### 5.3. Công thức suy nghĩ, không phải máy ra quyết định

Một phép cân nhắc đơn giản:

~~~text
Lợi ích tiềm năng của việc chờ thêm
    = giảm rủi ro chọn sai + giữ khả năng đổi hướng

Chi phí tiềm năng của việc chờ thêm
    = giá trị bị trì hoãn + nguy cơ trễ hạn
    + chi phí cơ hội + rủi ro do chưa xử lý

Nên chờ khi thông tin sắp thu được có khả năng
thay đổi lựa chọn đủ nhiều so với chi phí và rủi ro chờ.
~~~

Đây là **khung thảo luận định tính**. Không có phép tính này thay thế đánh giá bắt buộc về bảo mật, pháp lý hoặc tác động đến con người.

### 5.4. Ví dụ định lượng giả định

Một nhóm cân nhắc tích hợp SMS ngay hay thử thông báo rõ ràng trên giao diện trước:

- Cam kết tích hợp SMS ngay có thể làm phát sinh **12 ngày công**.
- Một nguyên mẫu và đợt dùng thử nhỏ mất **3 ngày công**.
- Nếu thử nghiệm chỉ ra không cần SMS, nhóm tránh được phần lớn 12 ngày công.
- Nhưng nếu chờ ba ngày khiến lỡ một mốc hợp đồng quan trọng, chi phí thực tế có thể lớn hơn thời gian tiết kiệm.

**Kết luận hợp lý:** cần hỏi có bao nhiêu thời gian trước hạn, kịch bản nào cần SMS thật, chi phí của việc chậm ba ngày và liệu dùng thử có đủ khả năng phân biệt phương án. Không thể kết luận “cứ thử ba ngày” chỉ vì 3 nhỏ hơn 12.

### 5.5. Ví dụ expected value với giả định công khai

Giả sử một nhóm đang phân vân giữa giải pháp A và B. Dựa trên đánh giá sơ bộ **giả định**, rủi ro nếu chọn sai có thể gây thêm **20 ngày công**, với khả năng nhóm tự ước lượng là **30%**. Giá trị tổn thất kỳ vọng ở mức sơ bộ là:

~~~text
Tổn thất kỳ vọng ước tính = 0,30 × 20 = 6 ngày công
~~~

Một phép thử chi phí 2 ngày công **chỉ đáng xem xét**, chứ chưa tự động đáng làm: phép thử phải có khả năng phát hiện lựa chọn sai đủ tốt; chưa kể chi phí chờ đợi và giới hạn thời gian.

Nếu thử nghiệm chỉ phân biệt được những điều không ảnh hưởng lựa chọn, **giá trị thông tin có thể gần bằng không**. Các tỷ lệ nêu trên là số giả định minh họa tư duy, không phải dữ liệu dự báo thực tế.

## 6. Xác định mốc quyết định từ thời gian thực hiện và rủi ro

### 6.1. Một cách ước lượng mốc muộn nhất

Nếu các bước phải diễn ra **tuần tự**:

~~~text
Mốc quyết định muộn nhất
    ≈ Mốc cần kết quả
      − thời gian mua sắm/tích hợp
      − thời gian kiểm thử/chấp nhận
      − khoảng dự phòng phù hợp
~~~

Ví dụ nhóm cần sẵn sàng trước ngày ra mắt. Theo ước lượng và phụ thuộc hiện biết:
- Tích hợp nhà cung cấp sau khi ký: **10 ngày làm việc**.
- Đánh giá an toàn và kiểm chứng sau tích hợp: **5 ngày làm việc**.
- Khoảng đệm rủi ro: **3 ngày làm việc**.

Nếu các bước tuần tự, nhóm cần quyết định **ít nhất khoảng 18 ngày làm việc trước thời điểm cần kết quả**. Đây là mốc **ước lượng kèm giả định**, chưa tính lịch nghỉ và thay đổi phạm vi.

Không được quy đổi máy móc 18 ngày làm việc thành 18 ngày lịch. Nếu các bước có thể chồng lấp, có thể rút ngắn; nếu có phụ thuộc hoặc chậm trễ nhà cung cấp, có thể phải quyết sớm hơn.

### 6.2. Mốc quyết định khác mốc bắt đầu học hỏi

Nếu phải ký trước mốc 18 ngày làm việc, nhóm nên khởi động các hoạt động có thể thu được thông tin **trước đó**:
- Xác nhận người dùng nào cần nhận tin khi không mở ứng dụng.
- Làm nguyên mẫu hai cách truyền đạt trạng thái.
- Hỏi nhà cung cấp về bảo mật, giới hạn và chi phí.
- Thử một luồng thông báo không cần gắn chặt với nhà cung cấp.
- Xác định phương án dự phòng nếu tích hợp không thể hoàn tất.

Một nhóm làm theo Lean có thể **rất chủ động từ sớm** dù giữ lại quyết định cam kết cuối cùng.

### 6.3. Ba loại điều kiện kích hoạt cần theo dõi

| Điều kiện | Ví dụ | Hành động |
| --- | --- | --- |
| **Theo bằng chứng** | Đủ phản hồi để nhận diện nhu cầu SMS khi người dùng ngoại tuyến | Chốt phương án theo tiêu chí đã thống nhất |
| **Theo thời gian** | Còn 18 ngày làm việc trước ngày cần kết quả | Quyết định dựa trên dữ liệu tốt nhất hiện có và dự phòng |
| **Theo rủi ro** | Xuất hiện lỗi xác nhận trùng trên production | Ưu tiên ứng phó ngay; không chờ đủ kết quả nghiên cứu thông báo |

Đặt mốc thời gian **và** điều kiện dựa trên bằng chứng giúp tránh tình trạng “chờ mãi vì chưa hoàn hảo”. Điều kiện rủi ro bảo vệ người dùng ngay cả khi kế hoạch ban đầu cho phép trì hoãn.

## 7. Giữ nhiều phương án khả thi mà không triển khai tất cả

Một cách giảm cam kết sớm là **set-based thinking/design**: tìm hiểu một số phương án trong thời gian giới hạn, loại dần phương án không phù hợp khi có bằng chứng, rồi hội tụ khi cần.

### 7.1. Ví dụ các phương án thông báo

| Phương án | Giá trị có thể có | Bất định quan trọng | Cách thử rẻ |
| --- | --- | --- | --- |
| **A. Trạng thái rõ trong trang** | Học viên tự kiểm tra khi mở trang | Có đủ cho người không quay lại trang? | Nguyên mẫu, quan sát dùng thử |
| **B. Email** | Người dùng nhận lại thông tin không cần truy cập | Khả năng đến hộp thư, hiểu trạng thái | Gửi thử trên phạm vi nhỏ, kiểm tra nội dung |
| **C. SMS** | Có thể tiếp cận khi không dùng email/app | Đồng ý nhận tin, chi phí, bảo mật, tích hợp | Khảo sát nhu cầu, đánh giá nhà cung cấp, thử kỹ thuật giới hạn |
| **D. Không thêm kênh, cải tiến quy trình duyệt** | Loại bỏ nguyên nhân phải hỏi lại | Nhu cầu có đến từ chậm xử lý chứ không phải kênh? | Quan sát điều phối và thời gian phản hồi |

Nhóm không cần xây đầy đủ cả bốn phương án. Có thể:
- Trình bày cùng một **trạng thái nghiệp vụ** qua một lớp giao diện dễ thay đổi.
- Tách **quy tắc xác nhận chỗ** khỏi **kênh thông báo**, tránh khóa logic nghiệp vụ vào SMS.
- Kiểm tra trước phương án ít chi phí và dễ đảo ngược.
- Lựa chọn kênh thêm sau nếu người dùng thực sự cần.

### 7.2. Thiết kế giữ tùy chọn mở

Một số kỹ thuật hỗ trợ:
- **Đường ranh giới mô-đun rõ:** phần xác định trạng thái không phụ thuộc trực tiếp vào từng kênh thông báo.
- **Interface/adapter:** mô tả hành vi gửi thông báo ở ranh giới có thể thay đổi nhà cung cấp.
- **Feature flag:** bật/tắt hoặc mở dần một tính năng khi có cách quản lý và rollback phù hợp.
- **Trường dữ liệu có thể mở rộng:** tránh khóa nghiệp vụ vào một lựa chọn khi còn nhiều kịch bản đáng tin.
- **Automated tests:** bảo vệ hành vi cốt lõi khi thay đổi giải pháp.
- **Thử nghiệm ngắn:** kiểm tra kỹ thuật hoặc trải nghiệm trước khi cam kết lớn.

Tuy nhiên, thiết kế để giữ tùy chọn **cũng có chi phí**. Không nên xây kiến trúc trừu tượng phức tạp cho mười nhà cung cấp giả định chưa có lý do sử dụng. Chỉ giữ những lựa chọn có **xác suất cần và chi phí đổi hướng đáng kể**.

### 7.3. Điểm hội tụ phải có tiêu chí

Nhóm có thể loại một phương án khi:
- Không đáp ứng tiêu chuẩn quyền riêng tư, an toàn hoặc pháp lý.
- Không thể hoàn tất trong cửa sổ thời gian cần thiết.
- Chi phí và rủi ro vận hành không tương xứng lợi ích dự kiến.
- Dữ liệu thử cho thấy nhu cầu được đáp ứng tốt bằng cách đơn giản hơn.
- Một phụ thuộc ngoài nhóm khiến nó không còn khả thi.

Sau khi loại, ghi rõ **vì sao** để không phải tranh luận lại từ đầu ở Sprint sau.

## 8. Học nhanh bằng thử nghiệm nhỏ trước khi cam kết lớn

### 8.1. Chọn câu hỏi cần trả lời, không chỉ chọn tính năng để demo

Một phép thử tốt bắt đầu từ câu hỏi:
> “Học viên phải nhắn hỏi lại vì không hiểu trạng thái hay vì không nhận được thông báo khi rời trang?”

Hai nguyên nhân dẫn đến hai giải pháp khác nhau. Nếu chỉ hỏi “Bạn có muốn SMS không?”, phản hồi có thể bị thiên lệch bởi mong muốn có thêm chức năng miễn phí.

Thử nghiệm có thể gồm:
1. Phỏng vấn về **trải nghiệm thực trước đây**, không chỉ hỏi người dùng thích gì.
2. Quan sát một mẫu người dùng tự thực hiện đăng ký với thông báo rõ hơn.
3. Đo tỷ lệ hiểu đúng trạng thái và số lần phải hỏi lại.
4. Kiểm thử khả năng cập nhật trạng thái đúng và quyền truy cập.
5. Thu ý kiến về các tình huống ngoại tuyến hoặc thông báo muộn.
6. Chốt quyết định dựa trên tiêu chí được công bố trước.

### 8.2. Mẫu giả thuyết kiểm chứng

~~~text
QUYẾT ĐỊNH CẦN HỖ TRỢ:
Có cần tích hợp SMS trong phiên bản đầu không?

GIẢ THUYẾT:
Thông báo trạng thái rõ và email khi thích hợp đủ giúp
phần lớn học viên hiểu kết quả trong luồng thử nghiệm.

ĐỐI TƯỢNG:
Học viên thử nghiệm, có cả người ít sử dụng email.

PHÉP THỬ:
Cho người dùng thực hiện đăng ký với nguyên mẫu và
quan sát họ diễn giải trạng thái, hành động tiếp theo.

THÔNG TIN CẦN GHI:
Số người hiểu đúng, trường hợp hỏi lại, lỗi gửi thông báo,
người dùng cần thông báo khi không mở ứng dụng.

GUARDRAIL:
Không phát sinh xác nhận sai chỗ hoặc lộ dữ liệu cá nhân.

MỐC QUYẾT ĐỊNH:
Trước hạn bắt buộc để tích hợp, kiểm thử và phát hành.

CÁCH DÙNG KẾT QUẢ:
Nếu nhu cầu ngoại tuyến đáng kể, đánh giá kỹ SMS;
nếu chưa, ưu tiên phương án đơn giản có thể mở rộng.
~~~

Ví dụ trên không đề xuất ngưỡng tỷ lệ có tính phổ quát. Nhóm cần đặt tiêu chí theo mục tiêu, mức độ rủi ro, tính đại diện của mẫu và tác động của sai lầm.

### 8.3. Không nhầm thử nghiệm với bằng chứng chắc chắn

Nếu 8/10 người dùng thử hiểu trạng thái, nhóm có **tín hiệu ban đầu** chứ không có bằng chứng rằng đúng 80% của toàn bộ người dùng sẽ hiểu. Cần xem người dùng được chọn thế nào, có tình huống đặc biệt nào chưa thử, có đồng thời nhiều thay đổi hay không.

Dữ liệu định tính có thể chỉ ra **nguyên nhân cần điều tra**; chỉ số định lượng hỗ trợ theo dõi khi định nghĩa và cỡ mẫu phù hợp. Quyết định có thể vẫn phải được đưa ra với bất định còn lại, nhưng cần **ghi lại bất định**, không biến suy đoán thành sự thật.

## 9. Quy trình ra quyết định Lean có mốc kết thúc

### 9.1. Luồng quyết định minh họa

~~~mermaid
flowchart TD
    A[Nhận diện vấn đề và quyết định cần đưa ra] --> B[Phân loại hậu quả, khả năng đảo ngược]
    B --> C{Có nguy cơ đang gây hại hoặc nghĩa vụ cấp bách?}
    C -->|Có| D[Ra quyết định bảo vệ người dùng và giảm thiểu rủi ro ngay]
    C -->|Không| E[Liệt kê phương án và giả định còn thiếu]
    E --> F[Đặt tiêu chí đủ thông tin và hạn quyết định]
    F --> G{Thông tin mới có thể đảo chiều lựa chọn?}
    G -->|Không| H[Quyết định theo bằng chứng hiện có]
    G -->|Có, còn đủ thời gian| I[Thử nghiệm nhỏ, giữ tùy chọn khả thi]
    I --> J[Đánh giá dữ liệu và chi phí tiếp tục chờ]
    J --> K{Đủ bằng chứng hoặc đã tới hạn?}
    K -->|Chưa| I
    K -->|Rồi| H
    D --> L[Thực hiện và kiểm tra kết quả]
    H --> L
    L --> M[Đối chiếu giả thuyết, cập nhật backlog và học hỏi]
~~~

Vòng thử nghiệm phải có **giới hạn thời gian và tiêu chí dừng**. Nếu mỗi lần thất bại lại yêu cầu thêm một thí nghiệm mà không thay đổi quyết định, nhóm có thể đang né tránh trách nhiệm lựa chọn.

### 9.2. Chín bước thực hành

1. **Đặt tên quyết định cụ thể.** Ví dụ “có cam kết nhà cung cấp SMS cho phiên bản đầu không?”
2. **Xác định ai chịu trách nhiệm.** Ai quyết giá trị sản phẩm, ai chấp thuận ràng buộc bảo mật, ai chọn thiết kế kỹ thuật?
3. **Liệt kê 2–4 phương án thực sự khả thi.** Đừng chỉ ghi hai ý tưởng đối lập hình thức.
4. **Đánh giá mức đảo ngược, tác động và deadline.**
5. **Liệt kê giả định có thể thay đổi thứ tự lựa chọn.**
6. **Chọn thông tin đủ và cách thu dữ liệu phù hợp chi phí.**
7. **Đặt mốc quyết định trước last responsible moment**, có người theo dõi.
8. **Quyết định, thực hiện lát cắt nhỏ, giữ chất lượng và quan sát thực tế.**
9. **Đối chiếu kết quả, cập nhật quyết định/backlog và chia sẻ điều đã học.**

### 9.3. Mẫu quyết định tối thiểu

| Trường | Câu hỏi |
| --- | --- |
| **Decision ID** | Làm sao tìm lại quyết định? |
| **Vấn đề và mục tiêu** | Vì sao phải quyết, gắn với người dùng/giá trị nào? |
| **Các phương án** | Có thể chọn gì ngoài phương án đang được đề xuất? |
| **Thông tin hiện có** | Điều gì là quan sát, điều gì chỉ là giả định? |
| **Bất định trọng yếu** | Thông tin mới nào có thể làm đổi quyết định? |
| **Rủi ro và điều kiện bắt buộc** | Điều gì không được đánh đổi? |
| **Hạn quyết định** | Khi nào còn đủ thời gian để triển khai an toàn? |
| **Người chịu trách nhiệm** | Ai quyết, ai phải được tham vấn? |
| **Quyết định và lý do** | Vì sao phương án này được chọn ở thời điểm đó? |
| **Điều kiện xem lại** | Dữ liệu hoặc sự kiện nào khiến cần đổi hướng? |

Biểu mẫu chỉ cần đủ rõ để quyết định được **truy vết**, không biến thành hồ sơ dài làm chậm một thay đổi nhỏ.

## 10. Tình huống xuyên suốt: chọn phương thức xác nhận workshop

### 10.1. Bối cảnh giả định

Nhóm đang phát triển sản phẩm đăng ký workshop. **Product Goal** là để học viên tự tìm buổi còn chỗ, gửi yêu cầu và hiểu kết quả, đồng thời điều phối viên kiểm soát sức chứa chính xác.

Trong một buổi họp, marketing đề xuất:
> “Phải có SMS ngay từ bản đầu vì nhìn chuyên nghiệp và khách hàng lớn sẽ thích.”

Developers cho biết tích hợp SMS cần:
- Đánh giá và ký hợp đồng nhà cung cấp.
- Kiểm tra quy định đồng ý nhận tin và dữ liệu liên hệ.
- Tích hợp API, kiểm thử lỗi gửi lại, phát hiện trùng thông báo.
- Thiết lập theo dõi sự cố và giới hạn chi phí.
- Có phương án xử lý khi nhà cung cấp chậm hoặc không hoạt động.

Người dùng thử lại nói điều làm họ lo nhất là **nhầm giữa “đã tiếp nhận yêu cầu” và “đã được xác nhận chỗ”**.

### 10.2. Tách vấn đề ra khỏi giải pháp

| Cấp độ | Phát biểu | Loại thông tin |
| --- | --- | --- |
| **Vấn đề người dùng** | Học viên không biết đã giữ được chỗ hay còn chờ | Cần kiểm chứng, có thể đo qua thử nghiệm |
| **Giả thuyết giải pháp** | SMS sẽ giúp học viên hiểu và tin vào kết quả | Chưa được chứng minh |
| **Giải pháp thay thế** | Thông báo trên trang, email, cải thiện quy trình duyệt | Cần so sánh |
| **Ràng buộc** | Không xác nhận sai, không lộ dữ liệu, tuân thủ quyền liên hệ | Phải được bảo vệ |
| **Quyết định** | Có cam kết tích hợp SMS trong đợt đầu hay không? | Được đưa ra sau khi cân nhắc bằng chứng và hạn |

Nếu nhóm bỏ qua phân tách này, họ dễ coi “thêm SMS” là yêu cầu chắc chắn, trong khi vấn đề có thể được giải quyết với chi phí và rủi ro thấp hơn.

### 10.3. Kế hoạch học trước khi chốt

**Tuần khám phá giả định:**

1. Product Owner làm rõ nhóm người dùng, hành vi mong muốn và yêu cầu trải nghiệm.
2. Developers đề xuất phương án kỹ thuật tách trạng thái đăng ký khỏi kênh thông báo.
3. Thiết kế một nguyên mẫu có “đã tiếp nhận” và “đã xác nhận” rõ ràng.
4. Cho người dùng thực hiện luồng đăng ký và diễn giải kết quả bằng lời.
5. Ghi những trường hợp người dùng không mở ứng dụng nên thực sự cần thông báo.
6. Song song, kiểm tra khả năng ký hợp đồng, tích hợp và các yêu cầu pháp lý đối với SMS.
7. Đến mốc quyết định, Product Owner cùng nhóm đánh giá theo Product Goal và rủi ro.

**Điểm Lean quan trọng:** nhóm **không chờ nghiên cứu xong mới bắt đầu mọi việc**. Họ có thể xây lát cắt đăng ký và kiểm thử tính đúng đắn của sức chứa trong khi chưa cam kết kênh thông báo trả phí.

### 10.4. Dữ liệu minh họa để ra quyết định

Trong một đợt dùng thử nhỏ **giả định**:

| Tín hiệu | Bản thông báo ban đầu | Bản làm rõ trạng thái |
| --- | ---: | ---: |
| Người dùng thử | 20 | 20 |
| Hiểu đúng “chờ xác nhận” | 9 | 16 |
| Phải hỏi lại ban tổ chức | 11 | 4 |
| Cần thông báo khi rời trang | Chưa hỏi rõ | 6 trường hợp được ghi nhận |
| Tình huống xác nhận trùng | Có rủi ro chưa kiểm chứng hết | Cần kiểm thử độc lập |

Các tỷ lệ quan sát tương ứng: hiểu đúng tăng từ **45% lên 80%** và hỏi lại giảm từ **55% xuống 20%** trong hai nhóm thử. Không được khẳng định thay đổi hiển thị **là nguyên nhân duy nhất**, vì mẫu nhỏ và có thể khác về người dùng.

Bằng chứng ban đầu cho thấy **làm rõ trạng thái có ích**, nhưng sáu trường hợp cần thông báo khi rời trang cho thấy vẫn cần tìm hiểu **kênh, tần suất và thời điểm**. Nhóm có thể chọn thử email trước hoặc chỉ mở SMS cho một trường hợp thực sự cần, thay vì ký hợp đồng rộng ngay.

### 10.5. Đưa ra quyết định có điều kiện

Một quyết định có thể được ghi:

> **Quyết định tạm thời:** Bản đầu sẽ ưu tiên trạng thái rõ trên giao diện, email nếu phù hợp quy trình và kiểm soát sức chứa. Chưa cam kết tích hợp SMS cho toàn bộ người dùng. Giữ ranh giới tích hợp thông báo có thể thay đổi nhà cung cấp.
>
> **Lý do:** Vấn đề chính được xác nhận là hiểu sai trạng thái; dữ liệu hiện tại chưa chứng minh SMS là lựa chọn có giá trị nhất.
>
> **Điều kiện xem lại:** Qua thử nghiệm tiếp, nếu nhóm người dùng mục tiêu thường cần thông báo khi không mở ứng dụng hoặc có nghĩa vụ dịch vụ phù hợp, đánh giá phương án SMS với bảo mật, chi phí, đồng ý nhận tin và thời hạn.
>
> **Giới hạn:** Không hy sinh quy tắc xác nhận chỗ và bảo vệ dữ liệu trong mọi trường hợp.

Đây là **phương án cho tình huống minh họa**, không phải lời khuyên rằng sản phẩm thực tế nên dùng email thay SMS. Nếu có mốc kinh doanh bắt buộc với SMS và dữ liệu đủ, quyết định phải điều chỉnh cho phù hợp.

### 10.6. Học từ kết quả bàn giao

Sau khi phát hành một Increment đạt Definition of Done, nhóm theo dõi:
- Tỷ lệ học viên hiểu đúng trạng thái.
- Tỷ lệ đăng ký hoàn tất, số lần hỏi lại.
- Lỗi xác nhận trùng, tiết lộ sai dữ liệu hoặc thông báo sai.
- Thời gian điều phối viên xử lý và xác nhận yêu cầu.
- Phản hồi về trường hợp ngoại tuyến hoặc cần nhắc nhở.

Nếu email và giao diện giải quyết đủ nhu cầu, việc không xây SMS có thể tránh lãng phí. Nếu người dùng cần SMS thật, kiến trúc giữ khả năng thay đổi sẽ giúp ra quyết định ở bước sau với thông tin tốt hơn.

## 11. Không chỉ sản phẩm: quyết định kỹ thuật và kiến trúc

### 11.1. Khi nào nên quyết sớm?

Một số quyết định kiến trúc có **chi phí đổi sau này rất cao** hoặc ảnh hưởng ngay đến an toàn:
- Cơ chế phân quyền và ranh giới dữ liệu cá nhân.
- Quy tắc không xác nhận vượt sức chứa.
- Cơ chế sao lưu/phục hồi cho dữ liệu quan trọng.
- Điều kiện kiểm toán hoặc tuân thủ bắt buộc.
- Phương án ứng phó khi thành phần quan trọng gặp sự cố.

Nhóm cần đánh giá rủi ro sớm, nhưng vẫn có thể tránh thiết kế phức tạp ngoài nhu cầu. Ví dụ nên định nghĩa **bất biến không xác nhận trùng** từ đầu, trong khi chưa nhất thiết phải chọn toàn bộ nền tảng giao thông báo cho các năm tiếp theo.

### 11.2. Khi nào giữ tùy chọn công nghệ?

Ví dụ nhóm chưa biết lượng đăng ký sẽ tăng đến đâu. Một cách tiếp cận là:
1. Xác định **yêu cầu tải và tính đúng đắn hiện biết**.
2. Dùng kiến trúc đơn giản đủ đáp ứng, có đo lường và kiểm thử.
3. Thiết kế ranh giới hợp lý để có thể tối ưu hoặc thay đổi thành phần khi số liệu cho thấy cần.
4. Chỉ cam kết hạ tầng chuyên dụng khi biết điểm nghẽn, chi phí và điều kiện chuyển đổi.

Không nên vừa chưa có nhu cầu, vừa tốn nhiều Sprint xây hệ thống phân tán phức tạp chỉ vì “sau này chắc sẽ lớn”. Nhưng cũng không thể chờ sản phẩm sập khi tải tăng mới bắt đầu kiểm tra khả năng chịu tải.

### 11.3. Architecture Decision Record (ADR) ngắn

~~~text
ADR-07: Kênh thông báo cho đăng ký workshop

Bối cảnh:
Người dùng hiểu sai trạng thái; nhu cầu thông báo ngoài ứng dụng chưa rõ.

Quyết định hiện tại:
Giữ logic trạng thái độc lập kênh; chưa ký hợp đồng SMS dài hạn.
Dùng phương thức thông báo đơn giản đã đáp ứng kiểm tra cần thiết.

Lựa chọn đã cân nhắc:
Giao diện, email, SMS, cải tiến quy trình duyệt.

Bằng chứng và giả định:
Dùng thử nhỏ cho thấy thông báo rõ hơn giảm hỏi lại;
chưa biết nhu cầu ngoại tuyến của toàn bộ người dùng.

Rủi ro:
Thông báo chậm, quyền liên hệ, chi phí nhà cung cấp, lỗi gửi lặp.

Điều kiện xem lại:
Nhu cầu ngoại tuyến được xác minh hoặc thời hạn hợp đồng bắt buộc.

Người ra quyết định và người tham vấn:
Product Owner về ưu tiên giá trị;
Developers và chuyên môn bảo mật về thiết kế/ràng buộc.

Ngày xem lại:
Trước mốc tích hợp còn đủ thời gian triển khai và kiểm thử.
~~~

ADR không tự quyết định thay nhóm. Giá trị của nó là **giữ bối cảnh và giả định**, để khi quyết định thay đổi, người sau hiểu vì sao ban đầu nhóm chọn phương án đó.

## 12. Kết hợp với Scrum, Kanban và XP

### 12.1. Scrum: một Sprint là cơ hội học và thích ứng

Trong Scrum:
- **Product Goal** giúp biết trạng thái sản phẩm cần hướng tới, tránh tối ưu giải pháp không liên quan.
- **Product Backlog** được sắp thứ tự và cập nhật khi bằng chứng mới xuất hiện.
- **Sprint Planning** giúp chọn một mục tiêu Sprint có giá trị, đồng thời ra quyết định dựa trên thông tin hiện biết.
- **Daily Scrum** giúp Developers kiểm tra Sprint Goal, phát hiện blocker và điều chỉnh kế hoạch.
- **Sprint Review** là dịp kiểm tra Increment, bối cảnh và phản hồi để thích ứng Product Backlog.
- **Sprint Retrospective** giúp nhóm đánh giá cách quyết định, phối hợp và thử cải tiến.

**Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; **Developers** chịu trách nhiệm kế hoạch kỹ thuật, chất lượng và Increment; **Scrum Master** giúp Scrum được thực hành hiệu quả. Không nên coi Product Owner là người tự chốt mọi lựa chọn kỹ thuật hoặc coi Developers có thể thay thế người quyết định ưu tiên sản phẩm.

**Lưu ý:** Scrum không quy định mọi quyết định đều phải chờ Sprint Review. Nếu có đủ bằng chứng và cần ra quyết định sớm để bảo vệ người dùng, nhóm phải thích ứng phù hợp.

### 12.2. Kanban: giữ luồng minh bạch khi còn bất định

Kanban có thể hỗ trợ bằng:
- **Định nghĩa luồng công việc** với điểm bắt đầu/kết thúc rõ.
- Hiển thị hạng mục **discovery/thử nghiệm** và **delivery/triển khai** nếu đây là các loại công việc cần điều phối.
- **WIP limits** để ngăn mở quá nhiều thử nghiệm hoặc thay đổi cùng lúc.
- **Work item age** và blocked để thấy một quyết định hay thử nghiệm đang chờ lâu.
- **Cycle time, throughput, SLE** để hình dung khả năng hoàn tất việc, không đánh đồng với giá trị.
- Chính sách **expedite** rõ cho sự cố thực sự khẩn.

Nếu nhóm “giữ lựa chọn mở” bằng cách bắt đầu triển khai ba phương án lớn cùng lúc, WIP tăng có thể làm chậm tất cả. Lean và Kanban cùng gợi ý **thử đủ để học, rồi hoàn tất những phần có ích** trước khi mở rộng.

### 12.3. XP: giảm chi phí đổi hướng bằng chất lượng kỹ thuật

Các thực hành **test-driven development**, **pair programming**, **continuous integration**, **refactoring** và thiết kế đơn giản hỗ trợ khả năng thay đổi an toàn:
- Kiểm thử hồi quy giúp thay phương án mà không làm hỏng quy tắc cũ.
- Tích hợp thường xuyên giúp nhìn thấy vấn đề sớm.
- Refactoring có chủ đích giữ code dễ thay đổi khi hiểu biết tăng.
- Pairing giúp kiểm tra giả định kỹ thuật và chia sẻ kiến thức.
- Phát hành lát cắt nhỏ giúp nhận phản hồi trước cam kết tiếp theo.

XP **không thay thế** trách nhiệm ra quyết định sản phẩm hoặc yêu cầu bảo mật. Nhưng khi chi phí thay đổi giảm, nhóm có thể **trì hoãn cam kết thiết kế lớn** mà vẫn tiếp tục giao giá trị từng phần.

### 12.4. Liên hệ với user story và backlog

Một user story diễn đạt **ai cần gì và vì sao**; nó không tự chốt giải pháp. Ví dụ “học viên muốn biết trạng thái” có thể được đáp ứng bởi nhiều lựa chọn giao diện/kênh. Product Backlog cho phép Product Owner điều chỉnh thứ tự khi dữ liệu làm rõ giá trị.

Một Product Backlog item có thể là một **thử nghiệm học hỏi** với câu hỏi và điều kiện hoàn tất rõ, nhưng không nên trình bày kết quả khám phá như đã giao chức năng người dùng. Cần phân biệt **học được điều gì** và **Increment nào đã đạt Definition of Done**.

## 13. Phân biệt trì hoãn có trách nhiệm với do dự và làm việc dang dở

### 13.1. Khi trì hoãn là hợp lý

- Có câu hỏi cụ thể có thể thay đổi lựa chọn.
- Có hoạt động thu dữ liệu với chi phí tương xứng và người chịu trách nhiệm.
- Có mốc ra quyết định không vượt last responsible moment.
- Các phương án còn khả thi đã được xác định.
- Rủi ro nếu chậm nằm trong giới hạn chấp nhận.
- Nhóm vẫn giao các phần việc độc lập có giá trị và thu phản hồi.
- Tiêu chí dừng thử nghiệm đủ rõ để tránh nghiên cứu kéo dài vô hạn.

### 13.2. Khi trì hoãn trở thành lãng phí

- Không ai có quyền ra quyết định cuối cùng.
- Nhóm liên tục yêu cầu thêm dữ liệu mà không nói dữ liệu đó đổi lựa chọn ra sao.
- Bằng chứng đủ rõ nhưng vẫn không muốn chịu trách nhiệm.
- Một phụ thuộc kéo dài khiến toàn bộ công việc bị chặn.
- Không có thời hạn, người phụ trách hoặc điều kiện xem lại.
- Quyết định bị hoãn đến khi không còn thời gian kiểm thử, phát hành an toàn.
- “Giữ lựa chọn” bị hiểu thành xây trước mọi phương án, tăng chi phí và WIP.

### 13.3. Bảng nhận diện nhanh

| Câu nói | Khả năng là | Phản ứng hữu ích |
| --- | --- | --- |
| “Chưa biết email có đủ không; thứ Năm có kết quả thử, hạn ký còn hai tuần.” | Trì hoãn có kế hoạch | Theo dõi thử nghiệm và mốc quyết định |
| “Cứ nghiên cứu thêm, chưa biết khi nào xong.” | Do dự không có điểm dừng | Xác định điều chưa biết, tiêu chí đủ, mốc cuối |
| “Phải ký SMS ngay vì đối thủ có SMS.” | Cam kết sớm theo suy đoán | Hỏi nhu cầu, tác động, hợp đồng và lựa chọn khác |
| “Lỗi đang làm mất dữ liệu nhưng cần khảo sát khách hàng trước.” | Trì hoãn nguy hiểm | Kích hoạt ứng phó ngay, giảm thiểu rủi ro |
| “Làm cả SMS, email, push để chưa phải chọn.” | Tăng WIP/chi phí do hiểu sai tùy chọn | Giữ ranh giới thiết kế, thử giả thuyết, hội tụ có điều kiện |
| “Tính năng nhỏ này dễ hoàn tác; giao thử có guardrail rồi đo.” | Quyết nhanh có kiểm soát | Làm rõ rollback, chất lượng và chỉ số học hỏi |

**Đừng dùng “Lean” để che một quyết định khó về trách nhiệm.** Một quyết định cần người quyết, bằng chứng, thời điểm và cách kiểm chứng kết quả.

## 14. Đo xem cách ra quyết định có đang cải thiện hay không

Không có một KPI duy nhất đo “độ Lean” của quyết định. Chỉ số có ích phải được đọc cùng giá trị người dùng, chất lượng, chi phí và thời gian chờ.

| Tín hiệu | Câu hỏi | Cảnh báo |
| --- | --- | --- |
| **Thời gian từ nhận vấn đề đến quyết định** | Chúng ta có đang chờ quá lâu? | Nhanh không có nghĩa đúng |
| **Số quyết định phải đảo ngược và nguyên nhân** | Có cam kết quá sớm, hay đang học thích ứng? | Đảo ngược không phải luôn là thất bại |
| **Chi phí làm lại do giả định sai** | Cam kết sớm khiến phải bỏ bao nhiêu công việc? | Ước lượng chi phí có thể không đầy đủ |
| **Thời gian chờ phụ thuộc** | Việc nào đứng vì chưa có người quyết? | Cần phân biệt chờ dữ liệu hợp lý và tắc nghẽn |
| **WIP của thử nghiệm và delivery** | Có quá nhiều việc dang dở cùng lúc? | Giảm WIP không tự tạo giá trị |
| **Cycle time và throughput** | Dòng công việc có cải thiện không? | Phụ thuộc cách định nghĩa luồng |
| **Tỷ lệ giả thuyết được kiểm chứng** | Có học điều làm thay đổi ưu tiên không? | Nhiều thử nghiệm không chắc tốt hơn |
| **Outcome sản phẩm** | Người dùng có hoàn thành việc tốt hơn không? | Phải xác định mẫu và bối cảnh |
| **Quality guardrails** | Có lỗi dữ liệu, quyền truy cập, sự cố tăng không? | Không hy sinh an toàn để quyết/giao nhanh |

Ví dụ đội rút thời gian quyết định nhà cung cấp từ bốn tuần xuống hai ngày nhưng thường phải chuyển nhà cung cấp sau đó sẽ không phải là cải tiến rõ ràng. Ngược lại, một quyết định mất ba tuần để xác minh giả thuyết quan trọng có thể phù hợp nếu nó tránh một cam kết lớn và không làm lỡ hạn.

### 14.1. Đánh giá bằng câu hỏi sau quyết định

Sau một vòng sản phẩm, nhóm có thể hỏi:
1. Giả định nào quan trọng nhất và dữ liệu nào đã thay đổi cách hiểu?
2. Có quyết định nào **chốt quá sớm**, khiến sửa lại lớn?
3. Có quyết định nào **chốt quá muộn**, khiến mất cơ hội hoặc phải giảm chất lượng?
4. Chúng ta đã chờ dữ liệu quan trọng hay chỉ chờ sự chắc chắn không tồn tại?
5. Có thể thiết kế thử nghiệm nhỏ hơn để biết sớm hơn không?
6. Nếu gặp tình huống tương tự, **mốc và người quyết định** nên đổi thế nào?

## 15. Sai lầm thường gặp và cách điều chỉnh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm nguyên tắc với “càng trễ càng tốt” | Trễ deadline, mất cơ hội, tăng rủi ro | Dùng last responsible moment và khoảng đệm thực tế |
| Đánh đồng “chưa chốt giải pháp” với “chưa làm gì” | Chậm học, chậm giao Increment | Làm discovery và phần việc độc lập sớm |
| Ký hợp đồng dài hạn dựa trên giả định | Chi phí chuyển đổi và lãng phí lớn | Thu bằng chứng phù hợp, kiểm tra điều khoản và phương án thay thế |
| Chờ dữ liệu không thể có trước khi phát hành | Quyết định bị treo vô hạn | Tách điều phải biết trước và điều học an toàn sau |
| Thử quá nhiều phương án đầy đủ | WIP tăng, chậm giao | Set-based exploration giới hạn, không phát triển toàn phần |
| Không có người chịu trách nhiệm | Mọi người tranh luận lại cùng một câu hỏi | Phân định quyền quyết sản phẩm, kỹ thuật và tuân thủ |
| Không ghi giả định hoặc điều kiện xem lại | Bằng chứng mới không chuyển thành hành động | Dùng decision log/ADR ngắn |
| Dựa vào điểm số giả định quá chính xác | Tưởng đã có bằng chứng định lượng | Ghi nguồn, dải bất định và rủi ro |
| Coi thử nghiệm trên mẫu nhỏ là chân lý | Phát hành quá rộng, gây lỗi | Xem giới hạn dữ liệu, thử theo giai đoạn và giữ guardrail |
| Giữ lựa chọn bằng kiến trúc trừu tượng quá mức | Phát triển chậm và khó bảo trì | Giữ các ranh giới thay đổi có giá trị, tránh tối ưu tương lai tưởng tượng |
| Trì hoãn xử lý lỗi nghiêm trọng | Ảnh hưởng người dùng, dữ liệu, uy tín | Ưu tiên ứng phó và quyết định bảo vệ ngay |
| Bỏ kiểm thử để kịp hạn chốt | Chất lượng giảm, phải làm lại | Đặt hạn quyết định đủ sớm cho DoD, kiểm thử và phát hành |
| Chỉ xem deadline, bỏ qua cost of delay | Chọn quá muộn hoặc quá sớm | Đọc cả giá trị thông tin và mất mát do chờ |
| Chỉ đo tốc độ ra quyết định | Nhanh nhưng chọn sai mục tiêu | Đánh giá outcome, chất lượng và chi phí đổi hướng |
| Không cập nhật backlog sau phản hồi | Tiếp tục xây theo giả định cũ | Có mốc kiểm tra, quyết định lại và thông báo minh bạch |

## 16. Bài thực hành: quyết định đúng lúc trong nhóm Agile

### 16.1. Bối cảnh và dữ kiện

Một nhóm sắp mở đăng ký workshop. Product Goal là để học viên tự tìm buổi còn chỗ, đăng ký và hiểu kết quả.

Có ba đề xuất:
- **A:** cải thiện trạng thái trên trang, công sức ước lượng **4 ngày công**.
- **B:** tích hợp email cho một số thay đổi trạng thái, công sức ước lượng **7 ngày công**.
- **C:** ký nhà cung cấp và tích hợp SMS, công sức ước lượng kỹ thuật **12 ngày công**, chưa gồm đàm phán và đánh giá bổ sung.

Giả định **hoàn toàn minh họa**:
- Mốc cần có khả năng đăng ký hoạt động an toàn cách hiện tại **25 ngày làm việc**.
- Phương án C, tính cả ký, triển khai, thử và khoảng đệm, cần **18 ngày làm việc** sau quyết định nếu các bước tuần tự.
- Một đợt quan sát người dùng để làm rõ nhu cầu thông báo mất **3 ngày làm việc**.
- Bên liên quan muốn “chốt ngay C để an tâm”.
- Chưa có bằng chứng rằng SMS quan trọng hơn việc hiển thị trạng thái rõ.
- Có lỗi tiềm ẩn về **xác nhận hai người vào cùng một suất cuối**, chưa được kiểm thử đủ.

### 16.2. Nhiệm vụ A – Phân loại quyết định (10 phút)

Với mỗi nội dung sau, xác định **dễ/khó đảo ngược** và **cần quyết sớm hay có thể chờ**:

1. Cách diễn đạt câu “đã tiếp nhận” trên giao diện.
2. Ký hợp đồng SMS dài hạn với phí rút lui lớn.
3. Quy tắc bảo vệ không xác nhận vượt số chỗ.
4. Chọn màu phụ cho một màn hình thử nghiệm.
5. Quyết định trước một mốc hợp đồng không thể lùi.

Viết **căn cứ** theo hậu quả, chi phí chuyển đổi và thời gian có dữ liệu mới. Không dùng quy tắc “kỹ thuật thì luôn chờ” hoặc “kinh doanh thì luôn quyết ngay”.

### 16.3. Nhiệm vụ B – Tính cửa sổ ra quyết định (10 phút)

Theo dữ kiện ở phần 16.1, phương án C cần 18 ngày làm việc sau khi quyết định để hoàn thành an toàn, còn 25 ngày làm việc tới mốc cần kết quả.

Câu hỏi:

1. **Muộn nhất sau bao nhiêu ngày làm việc kể từ hiện tại** phải quyết C nếu muốn giữ đủ 18 ngày làm việc?
2. Nếu làm thử nghiệm ba ngày làm việc ngay từ hôm nay, còn bao nhiêu ngày làm việc trước mốc quyết định muộn nhất?
3. Có thể kết luận “chắc chắn chọn C” chỉ từ việc thời gian cho phép không?
4. Nếu nhà cung cấp báo cần thêm 10 ngày làm việc và không thể rút ngắn, cần đổi điều gì?

**Gợi ý:** khoảng còn lại trước mốc quyết định muộn nhất là **25 − 18 = 7 ngày làm việc**. Thử nghiệm ba ngày để lại **4 ngày làm việc** trước mốc đó theo các giả định không phát sinh. Nếu lead time tăng 10 ngày thành 28 ngày, **25 − 28 = −3**, nghĩa là cách làm C không còn kịp theo kế hoạch hiện tại; cần xem giải pháp, phạm vi, mốc hoặc phương án dự phòng, không ép bỏ kiểm thử.

### 16.4. Nhiệm vụ C – Chọn thông tin cần học (15 phút)

Đề xuất một phép thử nhỏ để trả lời:

> “Thông báo nào giúp học viên hiểu đúng tình trạng mà không cần hỏi lại?”

Yêu cầu bài làm có:
- Người dùng và bối cảnh thử.
- Hai phương án có thể quan sát khác biệt.
- Cách ghi hành vi, không chỉ hỏi mức độ thích.
- Tín hiệu thành công và giới hạn dữ liệu.
- Guardrail về quyền và dữ liệu.
- Cách dùng kết quả để quyết A/B/C.
- Mốc ra quyết định không muộn hơn cửa sổ đã tính.

### 16.5. Nhiệm vụ D – Trả lời tình huống ưu tiên xung đột (15 phút)

Ngày thứ hai, Developers phát hiện lỗi có khả năng xác nhận hai người vào một chỗ, đồng thời marketing thúc giục ký SMS.

Hãy viết một quyết định ngắn làm rõ:
1. Điều gì cần **kiểm tra hoặc xử lý ngay** vì nguy cơ người dùng?
2. Điều gì có thể tiếp tục thử để **giữ lựa chọn**?
3. Ai phụ trách quyết định giá trị sản phẩm và ai phụ trách giải pháp kỹ thuật?
4. Có công việc nào cần dừng hoặc thay đổi thứ tự?
5. Khi nào phải ra quyết định về SMS?
6. Cách báo với bên liên quan mà không hứa ngày chưa có căn cứ?

### 16.6. Nhiệm vụ E – Tính và diễn giải lợi ích của thông tin (10 phút)

Một nhóm **giả định** đánh giá rằng việc chọn sai một phương án kỹ thuật có khả năng 25%, gây 16 ngày công làm lại; thử nghiệm nhỏ chi phí 2 ngày công.

1. Tính tổn thất kỳ vọng sơ bộ nếu không có thêm thông tin.
2. Có đủ dữ liệu để khẳng định nên luôn làm phép thử không?
3. Nếu phép thử không có khả năng phân biệt hai lựa chọn, giá trị thông tin thực tế có thể thế nào?
4. Nếu trì hoãn hai ngày khiến mất một cơ hội quan trọng, quyết định có thể đổi ra sao?

**Gợi ý:** 0,25 × 16 = **4 ngày công kỳ vọng** theo giả định. Phải biết thử nghiệm đáng tin đến đâu, chi phí trì hoãn và các ràng buộc khác trước khi so sánh với 2 ngày công. Không biến kết quả phép nhân thành bằng chứng khoa học về xác suất 25% vốn chưa được kiểm chứng.

### 16.7. Nhiệm vụ F – Viết decision record (10 phút)

Ghi quyết định dự kiến theo mẫu:
- Mục tiêu người dùng.
- Các lựa chọn và rủi ro.
- Bằng chứng đã có và điều chưa biết.
- Việc học sẽ làm ngay.
- Mốc quyết định cuối.
- Người chịu trách nhiệm.
- Lý do lựa chọn.
- Điều kiện xem lại và cách kiểm chứng sau bàn giao.

Mời một thành viên khác đọc và hỏi: **“Nếu tôi tiếp quản sau ba tuần, có đủ thông tin để hiểu vì sao nhóm chọn như vậy không?”**

### 16.8. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Hiểu nguyên tắc Lean** | Hiểu thành trì hoãn mọi thứ | Phân biệt học sớm và cam kết đúng lúc | Giải thích bằng giá trị thông tin, đảo ngược và cost of delay |
| **Chọn thời điểm** | Không có hạn hoặc quyết định theo cảm giác | Có mốc theo lead time và rủi ro | Có dự phòng, phụ thuộc và điều kiện kích hoạt rõ |
| **Đủ thông tin** | Chờ mọi dữ liệu hoặc quyết không cần bằng chứng | Xác định câu hỏi có thể đổi lựa chọn | Chọn phép thử có chi phí tương xứng, biết giới hạn dữ liệu |
| **An toàn và chất lượng** | Để lỗi quan trọng chờ hoặc bỏ kiểm thử | Bảo vệ dữ liệu, DoD và ứng phó sự cố | Có guardrail, phương án quay lui và kiểm chứng sau phát hành |
| **Cộng tác và cải tiến** | Không rõ ai quyết, không ghi lý do | Có trách nhiệm và decision log | Kết hợp Scrum/Kanban/XP và dùng phản hồi để đổi quyết định |

## 17. Mẫu sử dụng ngay

### 17.1. Mẫu quyết định Lean một trang

~~~text
MÃ QUYẾT ĐỊNH:
Ngày ghi:
Product Goal / kết quả cần đạt:
Vấn đề cần quyết:
Phương án 1:
Phương án 2:
Phương án khác / chưa làm:
Mức đảo ngược và chi phí đổi hướng:
Ràng buộc an toàn, pháp lý, chất lượng:
Điều đã biết (nguồn bằng chứng):
Giả định và bất định có thể đổi lựa chọn:
Thông tin cần thu thêm / phương pháp:
Chi phí thử và giá trị học kỳ vọng:
Cost of delay nếu chờ:
Mốc cần có kết quả:
Lead time và khoảng dự phòng:
LAST RESPONSIBLE MOMENT:
Người chịu trách nhiệm quyết định:
Người cần tham vấn:
Quyết định / lý do / ngày quyết:
Điều kiện xem lại hoặc rollback:
Kết quả thực sau phát hành:
~~~

### 17.2. Mẫu thẻ thử nghiệm nhỏ

~~~text
Câu hỏi cần học:
Vì sao câu hỏi ảnh hưởng quyết định:
Các phương án sẽ so sánh:
Đối tượng và bối cảnh:
Phương pháp và phạm vi thử:
Cách chọn mẫu / giới hạn mẫu:
Số liệu và phản hồi định tính:
Guardrail chất lượng và quyền riêng tư:
Điều kiện dừng thử:
Hạn có kết quả:
Hành động nếu giả thuyết đúng:
Hành động nếu giả thuyết sai:
Người ra quyết định tiếp:
~~~

### 17.3. Mẫu trao đổi với stakeholder

~~~text
Nhu cầu đã ghi nhận:
Product Goal liên quan:
Những điều nhóm biết chắc:
Những điều nhóm chưa biết:
Rủi ro nếu quyết ngay:
Rủi ro nếu đợi:
Việc đang thực hiện để có thông tin:
Ngày hoặc điều kiện ra quyết định:
Phương án dự phòng:
Ai chịu trách nhiệm:
Lần cập nhật tiếp theo:
~~~

Các mẫu là công cụ hỗ trợ quyết định, **không phải thủ tục bắt buộc của Lean hay Scrum**. Với một thay đổi nhỏ dễ hoàn tác, một đoạn ghi chú rõ là đủ. Với quyết định rủi ro lớn, cần hồ sơ và đánh giá chuyên môn theo quy định thực tế.

## 18. Checklist áp dụng nguyên tắc đúng lúc

**Hiểu quyết định:**

- [ ] Đã phân biệt vấn đề người dùng với giải pháp đang được đề xuất.
- [ ] Biết quyết định nào dễ đảo ngược và quyết định nào có chi phí đổi hướng cao.
- [ ] Có người chịu trách nhiệm cuối cùng về từng phạm vi quyết định.
- [ ] Không trì hoãn việc xử lý nguy cơ đang gây hại, an toàn hoặc nghĩa vụ bắt buộc.
- [ ] Nêu rõ các phương án thực sự khả thi, kể cả phương án đơn giản hơn.

**Học hỏi và thời điểm:**

- [ ] Biết câu hỏi chưa được giải đáp nào có thể làm thay đổi lựa chọn.
- [ ] Xác định thông tin phải biết trước và thông tin có thể học an toàn sau.
- [ ] Có phép thử đủ nhỏ, chi phí phù hợp và tiêu chí dừng rõ.
- [ ] Có mốc quyết định dựa trên deadline, lead time, phụ thuộc và khoảng đệm.
- [ ] Theo dõi cả giá trị học thêm và chi phí của việc tiếp tục chờ.
- [ ] Không đợi bằng chứng hoàn hảo khi chờ thêm không còn giá trị.
- [ ] Có phương án dự phòng nếu giả định quan trọng sai hoặc thời hạn thay đổi.

**Triển khai và kiểm chứng:**

- [ ] Chưa cần chốt giải pháp lớn nhưng các lát cắt độc lập vẫn có thể được phát triển.
- [ ] Giữ lựa chọn mở không đồng nghĩa xây đầy đủ nhiều giải pháp cùng lúc.
- [ ] Các quyết định kỹ thuật tôn trọng DoD, kiểm thử và bảo vệ dữ liệu.
- [ ] Product Backlog và ưu tiên được cập nhật khi có bằng chứng mới.
- [ ] Dòng công việc và WIP được nhìn thấy để tránh thử nghiệm/triển khai dang dở tràn lan.
- [ ] Kết quả được kiểm tra bằng outcome người dùng và quality guardrails, không chỉ số story hoặc tốc độ họp.
- [ ] Decision log ghi lý do, giả định, người quyết và điều kiện xem lại.
- [ ] Nhóm kiểm tra cả trường hợp quyết quá sớm lẫn quyết quá muộn để cải tiến cách làm.

**Kết luận:** Trong Lean, **ra quyết định vào thời điểm có đủ thông tin cần thiết** là một khả năng cân bằng: **học càng sớm càng có ích, giữ những lựa chọn đáng giá trong lúc bất định, nhưng cam kết đủ sớm để giao kết quả an toàn và đúng thời cơ**. Khi nhóm kết hợp tư duy này với backlog ưu tiên theo giá trị, Sprint Review, dòng công việc Kanban, thực hành chất lượng XP và phản hồi người dùng, những quyết định không còn là lời đoán một lần mà trở thành **chuỗi lựa chọn có bằng chứng, trách nhiệm và khả năng thích ứng**.
