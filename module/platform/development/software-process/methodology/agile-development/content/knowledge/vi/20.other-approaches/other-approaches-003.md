# DSDM và cân bằng thời gian, chi phí, chất lượng với phạm vi

Một nhóm phát triển phần mềm nhận yêu cầu: “Hệ thống đăng ký workshop phải sử dụng được trước ngày mở khóa học; ngân sách không tăng; không được để lộ dữ liệu học viên; đồng thời phải hoàn thành tất cả tính năng trong danh sách”. Khi phát hiện tích hợp khó hơn dự kiến, nhóm thường đứng trước bốn lựa chọn: lùi ngày, tăng người hoặc chi phí, bỏ kiểm thử, hay giảm số tính năng. Trong nhiều bối cảnh, ba lựa chọn đầu có thể gây hậu quả lớn. **Dynamic Systems Development Method (DSDM)** đưa ra một cách nhìn thực dụng: nếu **thời gian, chi phí và chất lượng cần được bảo vệ**, hãy **chủ động điều chỉnh phạm vi chi tiết theo thứ tự giá trị**, thay vì giả vờ mọi yêu cầu đều quan trọng ngang nhau.

Điều đó không có nghĩa được phép giao sản phẩm thiếu an toàn hoặc lén bỏ nhu cầu cốt lõi. DSDM nhấn mạnh **nhu cầu kinh doanh, hợp tác giữa các bên, giao đúng hạn, xây dựng tăng dần, phát triển lặp, giao tiếp liên tục và kiểm soát minh bạch**. Trong thực tế, nhóm thường dùng **MoSCoW** để phân biệt những yêu cầu tối thiểu phải có với những phần có thể lùi sang sau mà không làm mất giá trị của giải pháp.

Bài học thuộc chương **Các cách tiếp cận khác** của module **AGILE_DEVELOPMENT**. Ngoài Scrum, Kanban và XP, DSDM là một cách tiếp cận đáng tìm hiểu khi dự án cần **quản trị mốc giao hàng, ngân sách, phạm vi và sự tham gia của bên kinh doanh** một cách rõ ràng. Bài tập trung vào câu hỏi: **Làm thế nào vừa thích ứng với thay đổi vừa giao đúng thời điểm, trong phạm vi chi phí cho phép và không đánh đổi chất lượng?**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tư duy **cố định thời gian, chi phí, mức chất lượng và linh hoạt phạm vi** trong DSDM.
2. Phân biệt phạm vi chức năng có thể thương lượng với các **điều kiện chất lượng và nghĩa vụ bắt buộc** không được bỏ.
3. Sử dụng **MoSCoW: Must Have, Should Have, Could Have, Won't Have This Time** để xây phạm vi khả thi.
4. Nhận biết khi nào một danh sách có quá nhiều Must Have và cần trao đổi lại với người có thẩm quyền.
5. Lập kế hoạch theo **timebox**, tạo Increment nhỏ và dùng phản hồi để điều chỉnh phần ưu tiên thấp.
6. Mô tả vai trò hợp tác của bên kinh doanh, kỹ thuật, quản lý dự án và người ra quyết định.
7. Dùng dữ liệu năng lực, tiến độ, chất lượng và rủi ro để ra quyết định phạm vi minh bạch.
8. So sánh vai trò của DSDM với Scrum, Kanban và XP trong phát triển phần mềm thích ứng.

## 2. DSDM là gì, dùng khi nào?

**DSDM — Dynamic Systems Development Method** là một cách tiếp cận Agile có lịch sử từ những năm 1990, nhấn mạnh quản trị dự án và phát triển giải pháp theo hướng **được định hướng bởi nhu cầu kinh doanh, hợp tác chủ động, giao đúng hạn và kiểm soát chất lượng**. Các tư tưởng này tiếp tục xuất hiện trong các cách trình bày sau này như **DSDM Agile Project Framework**, gắn với hệ sinh thái AgilePM.

DSDM không chỉ là một kỹ thuật ước lượng, cũng không chỉ là bảng MoSCoW. Nó kết nối **nguyên tắc làm việc, vòng đời dự án, trách nhiệm của bên kinh doanh và kỹ thuật, ưu tiên yêu cầu, timeboxing, phát triển lặp và kiểm soát tiến độ**.

### DSDM thường hữu ích khi

- Có **ngày cần sử dụng thực tế** như khai giảng, chiến dịch hoặc sự kiện bắt buộc phối hợp.
- **Ngân sách hoặc số nguồn lực bị giới hạn**, không thể cứ thiếu tiến độ là thêm người.
- Các bên cần **minh bạch về phạm vi chắc chắn phải đạt và phạm vi có thể tùy chọn**.
- Sản phẩm có đủ sự bất định để cần **phản hồi sớm**, nhưng vẫn phải có kiểm soát quản trị.
- Người đại diện nghiệp vụ **có thể tham gia thường xuyên và được trao thẩm quyền quyết định phù hợp**.
- Có khả năng chia phần lớn giải pháp thành **lát cắt giá trị**, thay vì chỉ kiểm chứng được khi toàn bộ chương trình kết thúc.

### Khi cần thận trọng

Nếu mọi hạng mục đều là nghĩa vụ bắt buộc không thể giảm, ngày giao không thể đổi và nguồn lực không đủ, **không phương pháp Agile nào làm mâu thuẫn đó tự biến mất**. DSDM giúp đưa rủi ro ra ánh sáng và thương lượng các ràng buộc; nó không bảo đảm mọi dự án đều đáp ứng được tất cả mong muốn.

## 3. Tam giác ràng buộc: tại sao phạm vi là biến số?

Trong quản lý dự án, bốn yếu tố quan trọng gồm **thời gian, chi phí, phạm vi và chất lượng**. Mọi thay đổi của một yếu tố có thể tác động tới những yếu tố còn lại.

Ở nhiều cách quản lý dự án truyền thống, tổ chức cố gắng cố định toàn bộ phạm vi rồi thay đổi thời gian hoặc nguồn lực khi dự báo tăng. DSDM đưa ra một trọng tâm khác cho bối cảnh phù hợp:

| Yếu tố | Cách tiếp cận DSDM điển hình | Ví dụ triển khai workshop |
| --- | --- | --- |
| **Thời gian** | Giữ timebox và mốc giao đã thống nhất; không kéo dài âm thầm | Luồng đăng ký cốt lõi có sẵn trước ngày mở đăng ký |
| **Chi phí** | Làm trong ngân sách và năng lực được phê duyệt; chủ động nhìn phần dự phòng | Nhóm bốn người làm trong giới hạn kinh phí của đợt phát hành |
| **Chất lượng** | Thỏa thuận mức chất lượng cần đạt từ trước và **không hạ xuống để bù chậm tiến độ** | Quyền truy cập đúng, không đăng ký vượt số chỗ, dữ liệu nhất quán, kiểm thử phù hợp |
| **Phạm vi** | Sắp thứ tự theo giá trị, giảm hoặc dời phần ưu tiên thấp để bảo vệ các điều kiện trên | Dời lịch tháng nâng cao, mã khuyến mại, bộ lọc phụ |

### 3.1. Đây là chiến lược quản lý đánh đổi, không phải phép màu

Muốn giữ thời gian và chi phí, nhóm cần **đủ không gian trong phạm vi tùy chọn**. Nếu 100% khối lượng việc được gắn “bắt buộc” mà vượt năng lực, không còn phạm vi để điều chỉnh. Khi đó phải **thay đổi cách triển khai, kiểm chứng lại nhu cầu tối thiểu hoặc đưa các giới hạn lên cấp quyết định**, thay vì cố ép nhóm làm thêm giờ hay hạ chất lượng.

### 3.2. Chất lượng và phạm vi không phải cùng một thứ

Giả sử nhóm có thể bỏ chức năng **gợi ý workshop theo sở thích**, bởi nó chưa cần để người học tự đăng ký.

Nhưng nhóm **không thể bỏ kiểm tra quyền truy cập vào dữ liệu đăng ký** rồi gọi đó là “giảm phạm vi”, nếu tính năng đăng ký vẫn được mở cho người dùng thật. Kiểm soát quyền là điều kiện chất lượng/tuân thủ của phần được giao.

**Phạm vi linh hoạt** nghĩa là thay đổi **những khả năng kinh doanh được cung cấp**, không làm suy yếu độ đúng đắn, độ tin cậy hoặc an toàn của khả năng đã chọn.

### 3.3. Mọi yếu tố đều có giới hạn thực tế

Không phải mọi dự án DSDM đều luôn có thời gian, chi phí và chất lượng hoàn toàn bất biến trong mọi hoàn cảnh. Mấu chốt là **thỏa thuận rõ những ràng buộc đang được bảo vệ** và cơ chế quyết định khi không còn phương án khả thi. Với nghĩa vụ pháp lý, sự cố nghiêm trọng hoặc thay đổi chiến lược, các bên có thẩm quyền có thể phải xem lại cả phương án đầu tư. DSDM không thay thế quản trị rủi ro.

## 4. Tám nguyên tắc DSDM và mối liên hệ với đánh đổi phạm vi

DSDM thường được trình bày với **tám nguyên tắc**:

| Nguyên tắc | Diễn giải thực hành | Liên hệ với việc giữ mốc và chất lượng |
| --- | --- | --- |
| **1. Focus on the Business Need** — Tập trung nhu cầu kinh doanh | Bắt đầu từ kết quả thực sự cần đạt, không mặc định mọi tính năng được đề nghị đều cần | Giúp nhận diện phần Must Have và loại bỏ chi phí ít giá trị |
| **2. Deliver on Time** — Giao đúng hạn | Làm việc theo timebox và phối hợp mốc giao rõ | Giảm rủi ro kéo dài dự án vì cố thêm phạm vi phụ |
| **3. Collaborate** — Hợp tác | Bên kinh doanh, kỹ thuật, kiểm thử và người có thẩm quyền cùng quyết định | Cho phép đổi phạm vi kịp thời khi có thông tin mới |
| **4. Never Compromise Quality** — Không đánh đổi chất lượng | Thống nhất và kiểm chứng mức chất lượng phù hợp ngay từ đầu | Không đẩy phần kiểm thử, bảo mật và vận hành sang “lúc nào rảnh” |
| **5. Build Incrementally from Firm Foundations** — Xây tăng dần từ nền tảng đủ vững | Làm rõ mục tiêu, phạm vi, kiến trúc và rủi ro cốt lõi ở mức vừa đủ rồi giao từng phần | Tránh vừa đặc tả tất cả từ đầu, vừa tránh xây không có định hướng |
| **6. Develop Iteratively** — Phát triển lặp | Thử, nhận phản hồi, hoàn thiện giải pháp nhiều vòng | Giúp điều chỉnh trước khi hết ngân sách |
| **7. Communicate Continuously and Clearly** — Giao tiếp liên tục và rõ ràng | Minh bạch rủi ro, tiến độ, quyết định và người chịu trách nhiệm | Thay đổi phạm vi không thành bất ngờ vào cuối dự án |
| **8. Demonstrate Control** — Thể hiện khả năng kiểm soát | Theo dõi mục tiêu, sản phẩm thực, nguồn lực, chất lượng và ngoại lệ | Giúp người liên quan tin vào bằng chứng, không phải bảng phần trăm suy đoán |

### Ví dụ về một nguyên tắc bị hiểu sai

**Deliver on Time** không có nghĩa phát hành mọi thứ chưa kiểm thử khi đến ngày. Nó đi cùng **Never Compromise Quality**: ngày giao được bảo vệ nhờ **ưu tiên và điều chỉnh phạm vi**, tạo Increment hoàn chỉnh và giảm nguy cơ phát hiện lỗi muộn.

Tương tự, **Build Incrementally from Firm Foundations** không phải lời mời thiết kế toàn bộ kiến trúc thật chi tiết trong sáu tháng. Nền tảng đủ vững là **mục tiêu rõ, ranh giới quan trọng đã hiểu, trách nhiệm phù hợp và rủi ro chính được nhận diện**, sau đó học thêm qua phát triển thực tế.

## 5. MoSCoW: ngôn ngữ chung để quyết định phạm vi

**MoSCoW** là kỹ thuật ưu tiên thường gắn với DSDM. Tên gọi viết tắt bốn nhóm:

| Nhóm | Nghĩa | Câu hỏi kiểm tra |
| --- | --- | --- |
| **Must Have (M)** | Điều tối thiểu **phải có** để giải pháp hoặc mốc đang xét còn khả thi, có giá trị hoặc đáp ứng nghĩa vụ bắt buộc | Nếu thiếu yêu cầu này, đợt giao hàng có còn sử dụng hợp lệ và hữu ích không? |
| **Should Have (S)** | Điều quan trọng, đem lại giá trị đáng kể, nhưng có **cách chấp nhận hoặc phương án tạm** nếu không kịp đợt này | Có thể giao sau mà vẫn giữ kết quả cốt lõi không? |
| **Could Have (C)** | Điều đáng làm nếu còn đủ thời gian/năng lực; tác động bỏ lỡ thấp hơn | Nếu không kịp, người dùng vẫn đạt mục tiêu chính chứ? |
| **Won't Have This Time (W)** | Điều **chủ động không làm trong khoảng thời gian/phạm vi đang xét** | Các bên đã hiểu và thống nhất nó nằm ngoài đợt giao này chưa? |

**W không có nghĩa “không bao giờ làm”.** Một yêu cầu Won't Have This Time có thể trở lại trong đợt sau nếu giá trị và bối cảnh thay đổi.

### 5.1. MoSCoW là ưu tiên có thời hạn và ngữ cảnh

Không nên gắn nhãn “M vĩnh viễn” hoặc “C vĩnh viễn” cho một yêu cầu. Ví dụ, email nhắc lịch có thể là Could Have trong bản thử workshop miễn phí, nhưng trở thành Must Have nếu một chương trình mới có nghĩa vụ thông báo cụ thể. Phải nói rõ:

- Đang ưu tiên cho **mốc phát hành, dự án hay timebox nào**?
- **Kết quả tối thiểu** cần đạt là gì?
- Ràng buộc bảo mật, pháp lý, dữ liệu và vận hành nào áp dụng?
- Ai có quyền quyết định khi các yêu cầu xung đột?
- Khi nào các ưu tiên được xem lại dựa trên phản hồi?

### 5.2. Must Have thật sự phải nghiêm ngặt

Yêu cầu Must Have thường có đặc tính:

- **Thiếu nó thì đợt giao không còn khả thi hoặc không đáp ứng mục tiêu tối thiểu đã thỏa thuận**.
- Không có một phương án tạm chấp nhận được trong phạm vi mốc đó.
- Nằm trong các nghĩa vụ không thể bỏ như kiểm soát truy cập hoặc tính đúng đắn của dữ liệu khi có áp dụng.
- Được người có trách nhiệm kinh doanh và kỹ thuật xác nhận về giá trị, rủi ro và khả năng thực hiện.

Đừng nâng một yêu cầu lên Must Have chỉ vì **người yêu cầu có chức vụ cao**, “đã hứa từ lâu” hoặc “đội thiết kế rất thích”. Điều đó có thể là thông tin cần cân nhắc, nhưng chưa chứng minh tính bắt buộc của yêu cầu.

### 5.3. Phân biệt yêu cầu chức năng với điều kiện chất lượng

Mỗi hạng mục được chọn phải thỏa mãn các **điều kiện chất lượng đã thỏa thuận**. Nhóm có thể ghi một hoạt động riêng cho môi trường kiểm thử, giám sát, sao lưu hoặc thẩm định bảo mật khi cần, nhưng **không nên xem các điều kiện thiết yếu của một chức năng là phần Could Have dễ dàng bỏ đi**.

Ví dụ, đối với PBI “Đăng ký một chỗ”:

> **Phạm vi chức năng:** Học viên đủ điều kiện có thể đăng ký workshop còn chỗ.  
> **Điều kiện chất lượng:** Chỉ người có quyền được thao tác; số xác nhận không vượt sức chứa; trạng thái lỗi rõ ràng; kiểm thử theo rủi ro; khả năng quan sát và phục hồi phù hợp.

Nếu không có các điều kiện cốt lõi ấy, việc “đăng ký” được giao có thể **không phải giải pháp hoạt động được**, dù giao diện đã đẹp.

## 6. Quy tắc phân loại MoSCoW để tránh “mọi thứ đều Must”

Một buổi ưu tiên hiệu quả nên bắt đầu từ **mục tiêu và giới hạn nguồn lực**, rồi xem xét từng yêu cầu.

### 6.1. Bộ câu hỏi phân loại

1. **Nếu không có yêu cầu này vào ngày giao, điều gì cụ thể không thể xảy ra?**
2. **Đó là hậu quả đã được chứng minh hay chỉ là lo ngại/ưu thích?**
3. **Có cách thay thế tạm thời phù hợp, an toàn và được chấp nhận không?**
4. **Yêu cầu này bảo vệ điều kiện pháp lý, bảo mật, chất lượng hoặc vận hành bắt buộc nào?**
5. **Yêu cầu có thể chia nhỏ thành phần Must và phần Should/Could không?**
6. **Chi phí cơ hội của việc làm nó là gì? Việc nào có thể phải dời?**
7. **Người dùng và người chịu trách nhiệm kinh doanh có đồng ý với hậu quả nếu hoãn không?**

Nếu trả lời “không làm thì sản phẩm không dùng được”, hãy kiểm tra bằng ví dụ người dùng hoặc nghĩa vụ cụ thể. Nếu tất cả đều nói như vậy, có thể **mục tiêu chưa được thu hẹp đủ** hoặc **không ai được trao quyền đưa ra lựa chọn khó**.

### 6.2. Không dùng tỷ lệ MoSCoW như luật cứng

Một hướng dẫn thực hành DSDM thường đề cập việc **giữ nỗ lực dành cho Must Have ở mức đủ thấp để còn khoảng linh hoạt cho Should/Could và rủi ro**. Trong một số tài liệu, có ví dụ phân bổ **khoảng 60% effort cho Must Have**, nhưng đây **không phải tỷ lệ bắt buộc** và cũng **không phải 60% số lượng thẻ**. Quy mô, mức độ bất định, thời hạn và rủi ro của từng dự án khác nhau.

Thay vì áp một phần trăm máy móc, hãy tự hỏi:

> **Nếu xảy ra một hoặc hai rủi ro có thể dự đoán, ta còn phần phạm vi nào thực sự dời được mà vẫn giữ ngày giao, ngân sách và chất lượng?**

Nếu câu trả lời là **“không có”**, kế hoạch chưa có độ linh hoạt cần thiết, bất kể bảng MoSCoW có bốn màu đẹp đến đâu.

### 6.3. Độ lớn của yêu cầu quan trọng hơn số lượng nhãn

Ví dụ backlog có 10 Must Have nhưng mỗi việc chỉ một ngày và 2 Could Have nhưng mỗi việc ba tuần. Tính theo **số lượng** sẽ cho tỷ lệ hoàn toàn khác tính theo **công sức ước lượng và phụ thuộc**.

Vì thế, để cân bằng công suất dự án, nhóm cần kết hợp MoSCoW với **ước lượng độ lớn ở mức thích hợp**, năng lực thực tế và dữ liệu hoàn tất đã có. Không cần tạo cảm giác chính xác giả cho từng giờ; cũng không nên gắn nhãn rồi bỏ qua khối lượng công việc.

## 7. Ví dụ thực hành: lập kế hoạch 4 tuần cho đăng ký workshop

Giả sử một nhóm xây chức năng đăng ký workshop cho nền tảng học tập, cần phiên bản có thể sử dụng **trước đợt khai giảng**.

Các ràng buộc **minh họa**:

- **Thời gian:** 4 tuần, chia thành **hai timebox**, mỗi timebox 2 tuần.
- **Chi phí:** Sử dụng nhân sự và ngân sách đã được duyệt; không giả định có thể tăng người giữa chừng.
- **Năng lực:** Sau khi trừ nghỉ phép, trực hỗ trợ, phối hợp và nghĩa vụ cố định, nhóm dự kiến có **50 ngày-người khả dụng** cho toàn bộ công việc đã chọn, gồm xây dựng, kiểm thử và tích hợp.
- **Chất lượng:** Đáp ứng kiểm soát quyền, không xác nhận vượt sức chứa, dữ liệu đúng và có cách theo dõi lỗi vận hành.
- **Giá trị tối thiểu:** Học viên có thể thấy workshop còn chỗ, đăng ký hợp lệ và kiểm tra kết quả đáng tin cậy.

### 7.1. Phân loại backlog bằng MoSCoW

| Mã | Hạng mục | Nhóm | Nỗ lực minh họa (ngày-người) | Lý do |
| --- | --- | --- | ---: | --- |
| M1 | Xem workshop còn chỗ theo dữ liệu đáng tin | **Must** | 6 | Nếu không thấy lựa chọn hợp lệ, luồng đăng ký không khả dụng |
| M2 | Đăng ký hợp lệ, kiểm tra quyền và không vượt sức chứa | **Must** | 12 | Là kết quả cốt lõi, cần tính đúng đắn |
| M3 | Xem trạng thái đăng ký của chính mình | **Must** | 4 | Học viên cần xác minh kết quả, dữ liệu không lộ cho người khác |
| M4 | Khả năng giám sát lỗi và vận hành thiết yếu cho luồng đăng ký | **Must** | 4 | Bảo vệ sự tin cậy của giải pháp được đưa vào sử dụng |
| S1 | Tự hủy đăng ký theo chính sách | **Should** | 6 | Giảm việc thủ công; giai đoạn đầu có phương án hỗ trợ tạm chấp nhận |
| S2 | Email xác nhận sau khi trạng thái đã ghi đúng | **Should** | 4 | Tăng tiện ích; trạng thái trong ứng dụng đã là nguồn xác minh |
| C1 | Lọc workshop theo chủ đề | **Could** | 3 | Có ích nhưng không bắt buộc cho luồng cốt lõi |
| C2 | Giao diện lịch tháng nâng cao | **Could** | 5 | Tăng tiện lợi, chưa được xác nhận là điều kiện sử dụng |
| W1 | Tích điểm và mã ưu đãi | **Won't This Time** | Chưa đưa vào kế hoạch | Đưa ra ngoài phạm vi phát hành này |
| | **Tổng công việc đã dự kiến (M+S+C)** | | **44** | Không bao gồm phần dự phòng |

Phép tính:

\[
\text{Must}=6+12+4+4=26\ \text{ngày-người}.
\]

\[
\text{Should}=6+4=10;\quad \text{Could}=3+5=8.
\]

\[
\text{Dự phòng chưa phân bổ}=50-(26+10+8)=6\ \text{ngày-người}.
\]

Trong ví dụ này, **Must chiếm 26/50 = 52% năng lực khả dụng**. Đó là kết quả của tình huống minh họa, **không phải chỉ tiêu chuẩn**. Có phần Should, Could và dự phòng để xử lý biến động; mọi công việc đạt chất lượng cần thiết được bao gồm trong các ước lượng tương ứng.

### 7.2. Hai timebox minh họa

| Timebox | Năng lực dự kiến | Mục tiêu chính | Công việc được cân nhắc | Phần chưa phân bổ |
| --- | ---: | --- | --- | ---: |
| **TB1 — tuần 1–2** | 25 ngày-người | Luồng xem và đăng ký có thể kiểm chứng đầu cuối, có giám sát cơ bản | M1 (6), M2 (12), M4 (4) = **22** | **3** |
| **TB2 — tuần 3–4** | 25 ngày-người | Học viên xác minh trạng thái; tăng tiện ích nếu năng lực cho phép | M3 (4), S1 (6), S2 (4), C1 (3), C2 (5) = **22** | **3** |

**Đây là bản kế hoạch sơ bộ, không phải cam kết rằng 22 ngày-người chắc chắn hoàn tất đúng theo ước lượng.** Trong TB1, M2 cần được chia thành những lát cắt có kiểm chứng sớm; nếu thử nghiệm phát hiện rủi ro lớn, nhóm phải công khai tác động ngay, không đợi tới ngày cuối.

Trong TB2, các mục **S và C là phần có thể thương lượng**, không phải lời hứa độc lập bất biến. Nếu M3 hoặc việc sửa lỗi quan trọng tiêu tốn thêm năng lực, nhóm có thể dời C2, C1, S2 rồi tới các lựa chọn khác theo giá trị và điều kiện thực tế.

### 7.3. Vì sao không dồn 100% năng lực vào Must?

Với cùng 50 ngày-người, nếu Must đã 48 ngày-người:

- Rủi ro vắng mặt, lỗi tích hợp hay kiểm thử phát hiện vấn đề sẽ khiến mục tiêu không còn khả thi.
- Không có phạm vi tùy chọn đáng kể để dời.
- Áp lực thường chuyển thành yêu cầu làm thêm giờ hoặc bỏ bước kiểm chứng.

DSDM không khuyên **giảm chất lượng của Must**, mà khuyên **xem lại điều gì thật sự phải có**, thử giải pháp nhỏ hơn hoặc đưa quyết định vượt ràng buộc lên người có thẩm quyền.

## 8. Timeboxing: bảo vệ thời gian bằng học hỏi và điều chỉnh phạm vi

**Timebox** là khoảng thời gian cố định trong đó nhóm tập trung tạo **một kết quả được thỏa thuận**, dùng phản hồi và giới hạn thời gian để đưa ra quyết định. Khi timebox kết thúc, việc đánh giá tiến độ và chất lượng phải dựa trên **sản phẩm thực sự hoàn chỉnh**, không chỉ tỷ lệ công việc đã bắt đầu.

### 8.1. Timebox khác “deadline để ép tăng tốc” thế nào?

| Timebox được vận dụng tốt | Deadline bị biến thành áp lực đơn thuần |
| --- | --- |
| Có mục tiêu kinh doanh rõ và mức chất lượng thống nhất | Có danh sách việc dài, chưa rõ phần cốt lõi |
| Có ưu tiên Must/Should/Could và quyền quyết định | Mọi yêu cầu đều được coi là bắt buộc |
| Đánh giá Increment sớm, thay đổi cách làm hoặc phạm vi | Chỉ kiểm tra phần trăm hoàn thành vào cuối kỳ |
| Chấp nhận không giao phần Could/Should nếu cần | Bắt làm thêm giờ để giao đủ mọi thứ |
| Phơi bày rủi ro và phụ thuộc kịp thời | Trì hoãn báo cáo xấu tới ngày giao |

### 8.2. Các hoạt động trong một timebox

Một timebox có thể gồm các hoạt động:

1. **Khởi động:** Thống nhất mục tiêu, phạm vi ưu tiên, năng lực, tiêu chí chất lượng và cách ra quyết định.
2. **Điều tra/làm rõ:** Xác nhận những hiểu biết quan trọng, kiểm chứng rủi ro và phụ thuộc.
3. **Xây dựng và tinh chỉnh:** Tạo lát cắt nhỏ, kiểm thử, nhận phản hồi và điều chỉnh.
4. **Củng cố:** Tích hợp, sửa lỗi, kiểm chứng trạng thái hoàn chỉnh và khả năng vận hành.
5. **Đánh giá/kết thúc:** Kiểm tra kết quả thật, học được gì, phần nào chuyển sang backlog và dự báo lần tiếp.

DSDM có mô tả các cách **timeboxing có cấu trúc** với những giai đoạn như *Kick-off, Investigation, Refinement, Consolidation, Close-out*. Tùy cách áp dụng và bối cảnh, nhóm cần giữ **mục đích phản hồi và giao kết quả**, không nhất thiết biến mọi timebox thành năm cuộc họp cố định.

### 8.3. Timebox không cho phép dồn chất lượng sang lần sau

Với một hạng mục được xem là hoàn chỉnh, nhóm phải thỏa mãn tiêu chí đã thống nhất: hành vi đúng, tích hợp phù hợp, kiểm thử theo rủi ro, bảo mật và vận hành thiết yếu. Nếu tới cuối timebox một PBI chưa đạt, **trạng thái phải minh bạch**; phần chưa hoàn chỉnh không được giới thiệu như năng lực sẵn sàng sử dụng.

**Timebox cố định thời gian, không tự động bảo đảm tất cả Must sẽ xong.** Nếu dự báo một Must không thể đáp ứng, phải báo sớm, đánh giá lại phương án và đưa ra quyết định đúng thẩm quyền.

## 9. Chất lượng không đánh đổi: làm rõ từ đầu và kiểm tra liên tục

Nguyên tắc **Never Compromise Quality** là ranh giới cứng của tư duy DSDM trong bài toán phạm vi linh hoạt.

### 9.1. Chất lượng là thỏa thuận có thể kiểm chứng

Không nên chỉ ghi “phần mềm phải chất lượng cao”. Với chức năng đăng ký workshop, cần làm rõ:

| Thuộc tính | Ví dụ điều kiện chấp nhận/chất lượng |
| --- | --- |
| **Tính đúng đắn** | Không bao giờ có nhiều xác nhận hơn sức chứa cho cùng một chỗ |
| **Phân quyền** | Học viên chỉ xem, sửa hoặc hủy đăng ký trong phạm vi được phép |
| **Tính toàn vẹn dữ liệu** | Trạng thái đăng ký và số chỗ không bị lệch sau lỗi giao dịch |
| **Khả năng sử dụng** | Người dùng hiểu khi đăng ký thành công/thất bại, không bị báo thành công giả |
| **Khả năng phục hồi** | Có cách theo dõi, xử lý và khôi phục khi giao dịch thất bại |
| **Kiểm thử** | Các kịch bản nghiệp vụ, đồng thời và quyền truy cập quan trọng đã được kiểm chứng |
| **Vận hành** | Có log/cảnh báo phù hợp để hỗ trợ phát hiện vấn đề mà không lộ dữ liệu nhạy cảm |

Các điều kiện cần được điều chỉnh theo sản phẩm và mức rủi ro. Ví dụ hệ thống y tế hoặc thanh toán có yêu cầu đặc thù cao hơn. Không thể mượn bảng trên làm cam kết kiểm thử đầy đủ cho mọi ngành.

### 9.2. Phân biệt chất lượng với “xây tất cả tính năng”

Giả sử tổ chức quyết định **không phát hành giao diện lịch tháng** trong đợt đầu. Điều đó không làm giảm chất lượng của luồng danh sách workshop đã được chọn nếu nó đạt các tiêu chí cần thiết.

Ngược lại, nếu tổ chức giao **chức năng thanh toán** nhưng bỏ kiểm tra số tiền hoặc nhật ký giao dịch thiết yếu, thì đây là **giảm chất lượng của phần được giao**, không phải một cách sử dụng MoSCoW đúng.

### 9.3. Liên hệ với Definition of Done trong Scrum

**Definition of Done** là khái niệm chính thức của Scrum cho trạng thái hoàn chỉnh của Increment. DSDM có nguyên tắc **mức chất lượng được thống nhất trước và kiểm chứng trong suốt quá trình**, nhưng không nên gộp hai thuật ngữ thành “DSDM cũng bắt buộc có DoD theo Scrum Guide”.

Nếu nhóm đang vận dụng cả Scrum và DSDM, một DoD rõ ràng là công cụ hữu ích để **biến nguyên tắc không đánh đổi chất lượng thành điều kiện có thể quan sát**. Đối với nhóm không dùng Scrum, có thể dùng tiêu chí nghiệm thu và chính sách hoàn tất tương đương phù hợp.

## 10. Phát triển tăng dần và lặp: nền tảng cho phạm vi linh hoạt

DSDM thường kết hợp:

- **Incremental development:** Giao các phần giải pháp có thể kiểm chứng theo từng lần, không giữ toàn bộ giá trị tới cuối.
- **Iterative development:** Nhận phản hồi, điều chỉnh thiết kế và hành vi qua nhiều vòng lặp.

Hai cách này bổ trợ nhau nhưng không đồng nghĩa. Một phiên bản đầu có thể giao khả năng xem workshop; các vòng tiếp theo bổ sung đăng ký, cải thiện phản hồi lỗi, hỗ trợ hủy và trải nghiệm tìm kiếm.

### 10.1. Tại sao “nền tảng đủ vững” quan trọng?

Trước khi xây hàng loạt chức năng, nhóm cần hiểu:

1. **Mục tiêu kinh doanh tối thiểu:** Người dùng cần hoàn thành tác vụ nào trước mốc giao?
2. **Ranh giới giải pháp:** Các hệ thống bên ngoài, dữ liệu và quyền truy cập nào liên quan?
3. **Rủi ro cần kiểm chứng sớm:** Tính đồng thời khi giữ chỗ, dữ liệu kế thừa, giới hạn API, an toàn.
4. **Vai trò ra quyết định:** Ai chốt ưu tiên, ai xác nhận nghiệp vụ, ai chốt rủi ro kỹ thuật hoặc tuân thủ?
5. **Khả năng giao Increment:** Có môi trường, kiểm thử và quy trình triển khai phù hợp không?

Nền tảng đủ vững **không đồng nghĩa biết trước toàn bộ tính năng tương lai**. Nếu nhóm quá lâu ở giai đoạn thiết kế không tạo phần mềm kiểm chứng được, khả năng thích ứng thực tế sẽ suy giảm.

### 10.2. Ví dụ vòng phản hồi

~~~mermaid
flowchart TD
    A["Nhu cầu kinh doanh và ràng buộc"] --> B["Phạm vi ưu tiên MoSCoW"]
    B --> C["Timebox có mục tiêu, năng lực, chất lượng rõ"]
    C --> D["Xây lát cắt giá trị + kiểm thử"]
    D --> E["Increment được đánh giá với người dùng"]
    E --> F{"Có bằng chứng mới?"}
    F -->|"Có"| G["Đổi thứ tự, chia nhỏ hoặc dời phạm vi thấp"]
    F -->|"Chưa"| H["Tiếp tục mục tiêu, quan sát rủi ro"]
    G --> B
    H --> C
~~~

**MoSCoW không phải danh sách được phân loại một lần rồi khóa vĩnh viễn.** Nó cần được xem lại bằng bằng chứng, trong ranh giới cam kết và thẩm quyền.

## 11. Hợp tác và quyền quyết định: điều kiện để DSDM thành công

Nếu nhóm phải xin ý kiến hàng tuần mới được dời một Could Have, “phạm vi linh hoạt” chỉ tồn tại trên giấy. DSDM nhấn mạnh **sự tham gia chủ động của bên kinh doanh và quyền quyết định được làm rõ**.

Trong các cách trình bày DSDM/AgilePM, có những trách nhiệm vai trò như **Business Sponsor, Business Visionary, Project Manager, Technical Coordinator, Business Analyst, Business Ambassador, Team Leader, Solution Developer, Solution Tester** và những vai trò hỗ trợ khi cần. Không nên hiểu đây là yêu cầu mỗi chức danh phải do một người khác nhau đảm nhiệm trong mọi nhóm.

### 11.1. Một bản đồ trách nhiệm thực dụng

| Trách nhiệm | Nội dung cần có | Ví dụ trong dự án workshop |
| --- | --- | --- |
| **Bảo trợ và quyết định đầu tư** | Xác nhận giá trị, giới hạn ngân sách, các quyết định vượt thẩm quyền nhóm | Chấp thuận mục tiêu ra mắt trước ngày khai giảng và ngân sách |
| **Định hướng nghiệp vụ/sản phẩm** | Làm rõ kết quả, ưu tiên MoSCoW và hậu quả khi dời phạm vi | Xác nhận M2 đăng ký đúng chỗ quan trọng hơn lịch tháng |
| **Phối hợp tiến độ và phụ thuộc** | Duy trì timebox, minh bạch chi phí, các mốc và rủi ro liên nhóm | Xử lý môi trường kiểm thử hoặc phụ thuộc nhà cung cấp |
| **Điều phối giải pháp kỹ thuật** | Làm rõ kiến trúc đủ vững, các rủi ro kỹ thuật và quyết định tương ứng | Kiểm tra chiến lược giao dịch chống vượt sức chứa |
| **Phân tích nghiệp vụ** | Chuyển nhu cầu thành ví dụ hành vi, tiêu chí chấp nhận và quyết định rõ | Làm rõ quy tắc hủy và tình huống người học không đủ điều kiện |
| **Xây dựng và kiểm chứng giải pháp** | Tạo Increment, tích hợp, thử nghiệm và bảo vệ mức chất lượng | Thiết kế, code, test, kiểm soát quyền và theo dõi lỗi |

### 11.2. Phân quyền nhưng không bỏ quản trị

Trao quyền có nghĩa **người hiểu vấn đề được phép quyết những thay đổi thuộc phạm vi đã thống nhất**, đồng thời biết khi nào cần báo lên cấp phù hợp.

Ví dụ:

- Đổi câu chữ của trạng thái trong ứng dụng mà không ảnh hưởng tiêu chí chức năng có thể do nhóm và đại diện nghiệp vụ thống nhất nhanh.
- Dời một Could Have phù hợp cơ chế MoSCoW đã được ủy quyền có thể được quyết trong timebox.
- Bỏ một Must Have có liên quan nghĩa vụ hợp đồng hoặc bảo mật thường **không nằm trong quyền tự quyết của nhóm triển khai**.
- Thay đổi ngân sách, ngày cam kết pháp lý hoặc mức rủi ro được chấp nhận cần **người có thẩm quyền** tham gia.

Đây là lý do **collaboration** và **demonstrate control** phải đi cùng nhau. Không có quyền quyết định, thay đổi chậm; không có minh bạch và thẩm quyền, thay đổi tùy tiện.

## 12. Nếu Must Have có nguy cơ không hoàn tất thì xử lý thế nào?

Đây là tình huống phân biệt việc dùng DSDM nghiêm túc với việc chỉ thay nhãn trên backlog.

### Bước 1. Xác minh tình trạng thật

Hỏi:

- Công việc nào chưa đạt điều kiện hoàn thành?
- Rủi ro đến từ **độ lớn hạng mục**, phụ thuộc, kỹ thuật chưa biết, năng lực hay chất lượng?
- Có thể chia Must Have thành một **lát cắt nhỏ hơn nhưng vẫn đáp ứng nhu cầu bắt buộc** không?
- Cần thử nghiệm ngắn nào để giảm bất định?
- Nếu giữ hiện trạng, điều gì có khả năng xảy ra tại ngày giao?

Tránh báo “M2 đã hoàn thành 90%” nếu phần 10% còn lại là kiểm thử tính đúng đắn giao dịch và chưa có khả năng sử dụng an toàn.

### Bước 2. Dùng trước phần linh hoạt đã thống nhất

Nếu phát hiện M2 cần thêm bốn ngày-người, nhóm xem xét:

1. Sử dụng phần dự phòng **nếu vẫn phù hợp tổng rủi ro**.
2. Dời **Could Have** chưa cần thiết.
3. Dời **Should Have** có phương án chấp nhận tạm thời.
4. Tìm cách chia công việc để nhận phản hồi và giảm làm lại.
5. Cải thiện điểm nghẽn đã xác minh, thay vì chỉ mở thêm việc.

Không tự động **cắt kiểm thử hoặc thêm giờ kéo dài**. Nguồn lực sẵn có phải được nhìn bằng dữ liệu, không bằng áp lực.

### Bước 3. Nếu vẫn không khả thi, phải báo quyết định vượt ràng buộc

Nếu mức Must Have thật sự vượt năng lực còn lại, nhóm cần trình bày:

| Phương án | Điều kiện | Rủi ro/đánh đổi |
| --- | --- | --- |
| **Xác nhận lại phạm vi Must** | Người có trách nhiệm xác nhận một yêu cầu thực ra không bắt buộc hoặc có phương án tối thiểu hợp lệ | Cần bằng chứng, không được “hạ cấp” để làm đẹp bảng |
| **Đổi cách triển khai** | Có giải pháp nhỏ, an toàn, đạt cùng kết quả tối thiểu | Cần kiểm chứng giải pháp và tác động vận hành |
| **Thay đổi ngày hoặc ngân sách qua thẩm quyền** | Không thể giữ đồng thời mọi ràng buộc | Cần được phê duyệt, truyền đạt hệ quả và cam kết mới |
| **Không phát hành phần có rủi ro nghiêm trọng** | Không đáp ứng mức chất lượng/tuân thủ | Giảm rủi ro gây hại, nhưng ảnh hưởng mốc và cần kế hoạch tiếp |

**Never Compromise Quality** không có nghĩa nhóm phải giữ một ngày giao bằng mọi giá khi việc đó trở nên bất khả thi. Nó có nghĩa **không che rủi ro hoặc giảm chuẩn chất lượng chỉ để báo hoàn tất**; nếu không còn phương án khả thi, cần quyết định minh bạch ở đúng cấp.

### Phân biệt re-prioritization và re-baselining

Đổi thứ tự Could/Should trong giới hạn ủy quyền là **điều chỉnh ưu tiên vận hành**. Thay đổi một Must Have chiến lược, ngày giao bắt buộc hoặc ngân sách có thể là **thay đổi baseline/định hướng cam kết** và cần quản trị phù hợp.

Không nên gộp hai loại thay đổi này làm một. Khả năng thích ứng không phủ nhận trách nhiệm với người dùng, bên tài trợ và nghĩa vụ đã thỏa thuận.

## 13. Khi thông tin mới xuất hiện: bốn kịch bản cụ thể

### 13.1. Nhà cung cấp email đổi API

**S2 — Email xác nhận** chưa cần để người dùng thấy trạng thái đăng ký hợp lệ trong ứng dụng, và không có nghĩa vụ bắt buộc gửi email trong đợt đầu.

**Hành động:** Xác minh tác động; tạm dời S2 và ưu tiên M1–M4. Thông báo trải nghiệm dự kiến và cách người dùng kiểm tra trạng thái. Không kéo dài timebox chỉ để hoàn tất một Should Have.

### 13.2. Lỗi xác nhận vượt số chỗ

**M2 — Đăng ký hợp lệ** có nguy cơ làm sai dữ liệu khi yêu cầu đồng thời.

**Hành động:** Ưu tiên sửa và kiểm thử; tạm dừng triển khai những phần Could. Đây không phải “thêm một Could về kiểm thử”, mà là điều kiện chất lượng để M2 có thể hoàn chỉnh.

### 13.3. Người dùng thích danh sách đơn giản hơn lịch tháng

Phản hồi thử nghiệm cho thấy **C2 — Lịch tháng nâng cao** ít giá trị hơn kỳ vọng.

**Hành động:** Product/business representative xem lại ưu tiên; có thể chuyển C2 sang Won't Have This Time hoặc không triển khai, dùng năng lực cho phần giúp hoàn thành đăng ký đáng tin. Đây là **thích ứng theo phản hồi**, không phải thất bại vì “không làm hết backlog”.

### 13.4. Có nghĩa vụ pháp lý mới về thông báo

Giả sử chính sách áp dụng mới yêu cầu gửi thông báo điện tử có nội dung và thời hạn xác định cho một loại đăng ký.

**Hành động:** Xác minh nghĩa vụ với người có thẩm quyền; nếu thông báo là bắt buộc cho mốc giao đang xét, **không được xem S2 là tùy chọn chỉ vì trước đây nó là Should**. Cần ưu tiên lại phạm vi, năng lực hoặc phương án giao, đồng thời truyền đạt tác động sớm.

### Ma trận ra quyết định

| Thông tin mới | Điều còn giữ | Phần có thể điều chỉnh | Việc cần làm ngay |
| --- | --- | --- | --- |
| Email API trễ | Mục tiêu đăng ký và chất lượng | Email tùy chọn nếu không có nghĩa vụ bắt buộc | Dời S2, cập nhật phương án phản hồi |
| Lỗi đồng thời | Tính đúng đắn đăng ký | C/S và thứ tự thực hiện | Sửa lỗi, kiểm thử, dự báo lại |
| Phản hồi không cần lịch tháng | Kết quả người dùng cần | C2 và ưu tiên tương lai | Dừng đầu tư chưa cần, học thêm |
| Nghĩa vụ mới | Tuân thủ và chất lượng | Phạm vi tùy chọn, thậm chí mốc/chi phí qua phê duyệt | Làm rõ nghĩa vụ, báo rủi ro, xin quyết định phù hợp |

## 14. Quy trình lập kế hoạch DSDM theo ràng buộc thực tế

Một trình tự ứng dụng có thể gồm tám bước.

### Bước 1 — Xác định kết quả cần đạt

Viết **mục tiêu kinh doanh ở dạng kết quả**, không mở đầu bằng danh sách tất cả tính năng.

Ví dụ:

> “Trước ngày mở đăng ký, học viên đủ điều kiện tự tìm và đăng ký workshop còn chỗ, nhận trạng thái đáng tin mà không cần nhân viên xử lý thủ công.”

### Bước 2 — Chốt ràng buộc và quyền quyết định

Thống nhất thời gian, ngân sách, năng lực, tiêu chuẩn chất lượng, nghĩa vụ pháp lý/vận hành. Ai quyết ưu tiên? Ai xử lý rủi ro? Khi nào cần đưa vấn đề lên cấp tài trợ?

### Bước 3 — Xây nền tảng đủ vững

Làm rõ rủi ro lớn nhất, phụ thuộc ngoài, dữ liệu, ranh giới giải pháp và khả năng kiểm thử. Có thể dùng một **spike giới hạn thời gian** để kiểm chứng tính đồng thời hoặc API đối tác trước khi dự báo chi tiết.

### Bước 4 — Chia backlog thành lát cắt giá trị

Mỗi item nên có **người dùng/kết quả, ví dụ chấp nhận, ranh giới chất lượng và phụ thuộc**. Tránh dùng một hạng mục khổng lồ “hoàn thiện toàn bộ nền tảng” rồi gắn Must.

### Bước 5 — Ưu tiên MoSCoW cùng bên có thẩm quyền

Phân loại Must/Should/Could/Won't This Time dựa trên hậu quả nếu không có, không dựa trên chức vụ người yêu cầu. Kiểm tra tổng nỗ lực Must so với năng lực và dự phòng.

### Bước 6 — Thiết kế timebox và kiểm chứng

Xác định mục tiêu từng timebox, những lát cắt có thể hoàn tất, cách nhận phản hồi và điều kiện chất lượng. Đặt các rủi ro lớn vào phần sớm để **có thời gian phản ứng**.

### Bước 7 — Thực hiện, đo lường và thương lượng phạm vi

Theo dõi Increment đã hoàn chỉnh, WIP, thời gian chờ, năng lực và lỗi. Khi dữ liệu khác giả định, điều chỉnh phạm vi thấp trước; nếu Must có nguy cơ không đạt, báo sớm.

### Bước 8 — Đánh giá và học hỏi

Người dùng và bên kinh doanh cùng kiểm tra kết quả; nhóm xem phần nào tạo giá trị, phần nào chưa đạt, vì sao sai lệch và quyết định tiếp theo. Có thể điều chỉnh MoSCoW và kế hoạch timebox sau.

~~~mermaid
flowchart TD
    A["Mục tiêu kinh doanh, thời gian, ngân sách và chất lượng"] --> B["Nền tảng đủ vững: rủi ro, phụ thuộc, quyền quyết định"]
    B --> C["Lát cắt giá trị và MoSCoW"]
    C --> D{"Must phù hợp năng lực, còn phần linh hoạt?"}
    D -->|"Có"| E["Timebox + xây Increment + kiểm thử"]
    D -->|"Không"| F["Làm rõ Must hoặc đưa quyết định vượt ràng buộc tới đúng thẩm quyền"]
    F --> C
    E --> G["Kiểm chứng chất lượng và phản hồi"]
    G --> H{"Có nguy cơ trễ hoặc phát hiện nhu cầu mới?"}
    H -->|"Có"| I["Dời C/S, kiểm chứng phương án, báo tác động"]
    I --> C
    H -->|"Không"| J["Giao kết quả đạt chuẩn, tiếp tục timebox kế"]
    J --> E
~~~

Sơ đồ là **cách minh họa quyết định**, không phải thủ tục bắt buộc của DSDM. Điều quan trọng là **không giấu mâu thuẫn giữa Must, năng lực và mức chất lượng**.

## 15. Những số liệu giúp cân bằng thời gian, chi phí, phạm vi và chất lượng

Một kế hoạch không đáng tin chỉ vì có bảng màu xanh. DSDM cần **bằng chứng thực tế** để điều chỉnh phạm vi đúng lúc.

| Góc nhìn | Số liệu hoặc bằng chứng | Cách sử dụng |
| --- | --- | --- |
| **Thời gian** | Tiến độ các timebox, ngày chờ phụ thuộc, tuổi công việc đang làm | Phát hiện sớm nguy cơ trễ mốc |
| **Chi phí/năng lực** | Ngày-người khả dụng, việc hỗ trợ, chi phí đã phát sinh, dự báo chi phí còn lại | So nhu cầu thực với giới hạn nguồn lực |
| **Phạm vi** | Must/Should/Could đã đạt tiêu chí chấp nhận, item chưa hoàn chỉnh | Biết phần tối thiểu đã có thực hay chưa |
| **Chất lượng** | Kiểm thử theo rủi ro, lỗi nghiêm trọng còn mở, lỗi sau phát hành, khả năng vận hành | Ngăn “đạt tiến độ” bằng cách dời lỗi |
| **Dòng công việc** | WIP, throughput, cycle time, work item age, thời gian chờ | Nhìn nơi luồng bị tắc và năng lực hoàn tất thật |
| **Giá trị** | Người dùng hoàn tất đăng ký, tỷ lệ lỗi, số yêu cầu hỗ trợ, phản hồi sử dụng | Kiểm chứng Increment có giải quyết vấn đề không |
| **Rủi ro/giả định** | Phụ thuộc chưa xác nhận, thử nghiệm chưa có kết quả, quyết định còn chờ | Biết lúc nào cần thu hẹp phạm vi hoặc báo cấp quyết định |

### 15.1. Hai con số không nên dùng riêng lẻ

**Số PBI hoàn tất:** Dễ bị tăng bằng cách chia giả công việc hoặc đánh dấu Done khi chưa kiểm thử. Cần có **chính sách hoàn thành** và đối chiếu giá trị người dùng.

**Phần trăm hoàn thành:** “Đã làm 90% M2” thiếu ý nghĩa nếu 10% còn lại là phần chống đăng ký trùng mà chưa biết cách giải. Nên báo **hành vi đạt tiêu chí, rủi ro còn mở, năng lực còn lại và phương án**.

### 15.2. Dự báo là thông tin, không phải bảo đảm

Velocity hoặc throughput lịch sử có thể hỗ trợ dự báo, nhưng khi loại công việc, đội hình, yêu cầu chất lượng hoặc phụ thuộc thay đổi, cần công khai giới hạn áp dụng. Một kế hoạch tốt trình bày **kịch bản và điều kiện**, không gắn xác suất chắc chắn thiếu căn cứ.

## 16. DSDM liên hệ với Scrum, Kanban và XP thế nào?

Ba cách tiếp cận được học trong module Agile có thể bổ trợ DSDM, nhưng **không hoàn toàn thay thế nhau**.

| Cách tiếp cận | Điểm nhấn | Giá trị khi kết hợp tư duy DSDM | Điều cần tránh |
| --- | --- | --- | --- |
| **DSDM** | Kết quả kinh doanh, quản trị ràng buộc, MoSCoW, timebox và hợp tác các cấp | Giữ các quyết định phạm vi rõ, chủ động quản lý thời gian/chi phí/chất lượng | Coi MoSCoW là công thức giải mọi rủi ro |
| **Scrum** | Product Goal, Sprint Goal, Increment, các sự kiện và trách nhiệm thực nghiệm | Kiểm tra và thích ứng ở nhịp Sprint; giao Increment có chất lượng | Đồng nhất timebox DSDM với Sprint hoặc gộp quyền quyết định khác nhau một cách máy móc |
| **Kanban** | Dòng công việc, chính sách pull, giới hạn WIP, throughput và cycle time | Giảm chờ, nhìn sức chứa thực và rủi ro hạng mục dở dang | Coi tốc độ đóng thẻ là giá trị kinh doanh |
| **XP** | Giá trị hợp tác và thực hành kỹ thuật như TDD, CI, refactoring, pair programming | Giữ khả năng thay đổi, kiểm thử sớm và chất lượng khi phạm vi biến động | Dùng “small release” để bỏ các kiểm soát bắt buộc |

### 16.1. Phân biệt Sprint của Scrum với timebox của DSDM

Cả hai đều sử dụng thời gian giới hạn để tạo tập trung và phản hồi, nhưng **chúng thuộc hai phương pháp với trách nhiệm, thuật ngữ và mô hình quản trị riêng**.

Trong **Scrum**, Sprint có Sprint Goal, Sprint Backlog do Developers tự quản và các Scrum event; Product Owner chịu trách nhiệm quản lý Product Backlog và giá trị. Không nên tự suy rằng nhóm dùng Scrum bắt buộc phải áp đặt bảng vai trò DSDM hoặc quy trình thay đổi phạm vi của DSDM.

Trong **DSDM**, timebox được dùng để điều phối một kết quả với **ưu tiên MoSCoW, mục tiêu kinh doanh và các ràng buộc dự án**. Nếu kết hợp, nhóm cần **làm rõ vai trò, thẩm quyền và thuật ngữ nào đang dùng**, tránh tạo thêm tầng phê duyệt mâu thuẫn.

### 16.2. Minh họa kết hợp thực dụng

Nhóm dùng:

- **Tư duy DSDM:** Ngày mở đăng ký và ngân sách được bảo vệ; phân loại chức năng bằng MoSCoW.
- **Scrum:** Sprint Goal tập trung vào luồng đăng ký an toàn, Sprint Review lấy phản hồi thực tế.
- **Kanban:** Theo dõi WIP, tuổi PR, hàng đợi kiểm thử để tránh tích tụ công việc.
- **XP:** Kiểm thử quy tắc nghiệp vụ, CI và refactoring để giao Increment nhỏ đáng tin cậy.

Đây là **một phương án thiết kế cách làm**, không phải tên một framework chính thức hoặc tập nghi thức bắt buộc.

## 17. Những giới hạn của DSDM và điều kiện thất bại thường gặp

DSDM có ích khi tổ chức **thực sự sẵn sàng đưa ra lựa chọn về phạm vi**. Nếu điều kiện không được đáp ứng, phương pháp có thể bị biến thành cách gắn nhãn và lập báo cáo mà không tăng khả năng thích ứng.

### 17.1. Không có người đại diện nghiệp vụ đủ thẩm quyền

Nếu Developers cần trả lời “có thể dời email xác nhận không?” nhưng phải chờ ba tuần mới có người chốt, timebox sẽ không còn khả năng điều chỉnh kịp thời. Cần **đầu mối kinh doanh tham gia thường xuyên, quyền ra quyết định rõ và kênh đưa vấn đề vượt quyền lên cấp phù hợp**.

### 17.2. Không thể chia giải pháp thành Increment có giá trị

Một hệ thống có phụ thuộc chặt, di trú dữ liệu lớn hoặc giao thức đối tác chưa rõ có thể không tạo ra lát cắt độc lập ngay. Cần kiểm chứng kỹ thuật, làm nền tảng tối thiểu và có kế hoạch chuyển đổi, không ép chia giả để tăng số item.

### 17.3. Mức Must quá lớn

Nếu gần toàn bộ năng lực đã dành cho Must, việc dùng MoSCoW chỉ để trình bày bốn nhãn không giúp bảo vệ deadline. Cần **giảm nhu cầu tối thiểu bằng bằng chứng, thay đổi phương án hoặc thảo luận lại ràng buộc**.

### 17.4. Chất lượng không được định nghĩa rõ

Khi “xong” chỉ nghĩa là code merge, các thiếu sót bảo mật, kiểm thử và vận hành sẽ dồn về cuối timebox. Điều này làm **thời gian và chi phí thực tế** vượt dự báo, trái với mục đích DSDM.

### 17.5. Người liên quan không chấp nhận phạm vi linh hoạt

Nếu các bên vẫn đo thành công bằng việc giao **100% danh sách tính năng đã ghi ngày đầu**, họ sẽ xem việc dời Could Have là thất bại. Cần thống nhất từ đầu rằng **kết quả kinh doanh, Must Have đạt chất lượng và mốc giao** là thước đo quan trọng hơn việc đủ mọi tính năng.

### 17.6. Thay đổi nhanh nhưng thiếu quản trị

“Agile” không đồng nghĩa bất kỳ ai cũng được đổi Must, đổi mốc hoặc giảm chuẩn bảo mật. DSDM cần **giao tiếp, minh bạch, kiểm soát và cấp thẩm quyền đúng** để đổi nhanh nhưng có trách nhiệm.

## 18. Các hiểu lầm và phản ví dụ thường gặp

| Hiểu lầm | Rủi ro | Cách hiểu phù hợp |
| --- | --- | --- |
| “DSDM luôn cố định tất cả ngoài phạm vi” | Không thể đáp ứng biến cố hoặc nghĩa vụ mới | Chủ động bảo vệ ràng buộc đã chọn, có cơ chế quyết định khi chúng không còn khả thi |
| “Muốn đúng hạn thì bỏ kiểm thử” | Lỗi, dữ liệu sai và nguy cơ gây hại | Never Compromise Quality; dời phạm vi có thể dời |
| “Must là mọi yêu cầu stakeholder đã nói” | Không còn độ linh hoạt trong kế hoạch | Must chỉ là phần tối thiểu thật sự cần để giải pháp khả thi |
| “Won't Have nghĩa là không bao giờ làm” | Gây hiểu lầm về roadmap | Won't Have **This Time**: chưa thuộc khoảng phạm vi đang xét |
| “Đếm số item là đủ để chia MoSCoW” | Một item lớn có thể nuốt toàn bộ năng lực | Cần nhìn độ lớn, phụ thuộc và công việc chất lượng |
| “60% Must là luật bắt buộc của DSDM” | Ép tỷ lệ dù bối cảnh không phù hợp | Dùng tỷ lệ tham khảo để kiểm tra sự linh hoạt, không coi là chuẩn tuyệt đối |
| “Cứ hết timebox là tính Done” | Giao sản phẩm chưa hoàn chỉnh và hứa sai | Kết thúc timebox đúng hạn, minh bạch phần chưa đạt |
| “Phần còn lại của Must có thể chuyển sang nợ kỹ thuật” | Trì hoãn nghĩa vụ cốt lõi và chất lượng | Phải đánh giá lại tính khả thi và báo đúng thẩm quyền |
| “Bảo trợ đã duyệt ngân sách thì không cần tham gia nữa” | Quyết định phạm vi chờ quá lâu | DSDM cần hợp tác và quyền quyết định xuyên suốt |
| “Nền tảng đủ vững nghĩa là đặc tả toàn bộ dự án trước khi code” | Chậm phản hồi, thiết kế theo giả định | Làm rõ rủi ro, mục tiêu và ranh giới cốt lõi; phát triển tăng dần |
| “DSDM cạnh tranh với Scrum/XP nên chỉ được chọn một” | Bỏ lỡ thực hành bổ trợ hữu ích | Có thể phối hợp có chủ đích, làm rõ vai trò và tránh nghi thức trùng |
| “Thời gian cố định là lý do bắt làm thêm giờ liên tục” | Kiệt sức, lỗi và chi phí làm lại | Điều chỉnh phạm vi, ưu tiên đúng và quản lý năng lực thực |
| “Giá trị càng cao thì càng phải gắn Must” | Không phân biệt bắt buộc và quan trọng | Should có thể rất giá trị nhưng có phương án hoãn hợp lệ |
| “Nếu chưa đủ Must thì âm thầm hạ cấp sang Could” | Mất lòng tin và vi phạm ràng buộc | Đưa bằng chứng và phương án cho người có thẩm quyền quyết |
| “Có MoSCoW rồi thì không cần xem dữ liệu dòng công việc” | Không phát hiện nút thắt và dự báo sai | Kết hợp ưu tiên với năng lực, throughput, WIP và chất lượng |

## 19. Mẫu kế hoạch DSDM thực dụng

Mẫu dưới đây có thể dùng cho đợt giao hoặc timebox. Nó là **công cụ vận dụng**, không phải mẫu biểu bắt buộc của DSDM.

~~~text
TÊN ĐỢT GIAO / TIMEBOX:
KẾT QUẢ KINH DOANH CẦN ĐẠT:
NGƯỜI DÙNG VÀ BẰNG CHỨNG GIÁ TRỊ:

RÀNG BUỘC:
- Ngày / timebox:
- Ngân sách và năng lực khả dụng:
- Chất lượng, bảo mật, dữ liệu, vận hành bắt buộc:
- Phụ thuộc bên ngoài:
- Thẩm quyền quyết định ưu tiên và thay đổi:

NỀN TẢNG ĐÃ XÁC NHẬN:
- Các giả định quan trọng:
- Rủi ro cần thử sớm:
- Điều kiện kiểm chứng Increment:

MOSCOW:
- MUST: Mục tiêu tối thiểu, lý do bắt buộc, nỗ lực/rủi ro:
- SHOULD: Giá trị và phương án tạm nếu dời:
- COULD: Giá trị bổ sung nếu còn năng lực:
- WON'T HAVE THIS TIME: Nội dung và mốc xem lại:

KIỂM TRA TÍNH KHẢ THI:
- Năng lực tổng:
- Nỗ lực Must (bao gồm chất lượng):
- Nỗ lực Should/Could:
- Phần dự phòng và rủi ro chưa định lượng:
- Điều gì có thể dời mà không phá mục tiêu?

KẾ HOẠCH KIỂM CHỨNG:
- Increment đầu tiên tạo giá trị:
- Phản hồi từ ai và khi nào:
- Định nghĩa hoàn chỉnh/chất lượng:
- Dữ liệu tiến độ và dòng công việc:

QUYẾT ĐỊNH KHI THAY ĐỔI:
- Tín hiệu cần thương lượng lại phạm vi:
- Người có quyền chốt:
- Phương án khi Must không khả thi:
- Cách thông báo tác động và cập nhật dự báo:
~~~

Không cần điền mọi trường cho một tính năng nhỏ. Với dự án có **mốc bắt buộc, nhiều phụ thuộc hoặc nghĩa vụ chất lượng**, minh bạch thông tin này thường đáng công hơn một dự báo “chắc chắn” không nói rõ giả định.

## 20. Bài tập ứng dụng: giữ ngày khai giảng nhưng không bỏ chất lượng

**Tình huống:** Một nhóm đang làm hệ thống đăng ký học phần, có thời hạn bốn tuần, ngân sách cố định và năng lực **40 ngày-người** cho phạm vi đang xét. Các yêu cầu được đề xuất:

| Hạng mục | Nỗ lực minh họa | Bối cảnh |
| --- | ---: | --- |
| A. Sinh viên đăng ký môn còn chỗ, chống đăng ký vượt sức chứa | 15 | Năng lực cốt lõi, rủi ro dữ liệu cao |
| B. Sinh viên xem trạng thái và lịch đã đăng ký | 7 | Cần tự xác minh kết quả |
| C. Kiểm soát quyền và nhật ký thao tác thiết yếu | 6 | Nghĩa vụ bảo mật/vận hành của đợt phát hành |
| D. Gửi email xác nhận với phương án trạng thái trên ứng dụng | 4 | Tăng tiện ích, có thể tạm dùng ứng dụng |
| E. Lịch tháng với bộ lọc nâng cao | 6 | Tính năng bổ sung |
| F. Bảng xếp hạng học phần được quan tâm | 5 | Chưa có bằng chứng giá trị rõ |

Thông tin mới:

1. Kiểm thử tìm ra lỗi cạnh tranh làm A cần thêm **5 ngày-người** để sửa và kiểm chứng.
2. Nhà cung cấp email báo chậm xác nhận API.
3. Một stakeholder yêu cầu đưa F vào đợt giao vì “lãnh đạo sẽ xem demo”.
4. Không thể thay đổi ngày khai giảng; bộ phận quản trị cho biết **không được mở chức năng đăng ký nếu chưa đạt kiểm soát quyền và tính đúng đắn dữ liệu**.

### Yêu cầu

1. Đề xuất một phương án phân loại A–F bằng MoSCoW. Giải thích vì sao mỗi hạng mục thuộc nhóm đã chọn.
2. Tính tổng nỗ lực Must nếu A, B, C là Must. Trước và sau khi phát hiện lỗi, nhóm còn bao nhiêu ngày-người?
3. Có nên dời D, E, F để bảo vệ A–C và mốc giao không? Điều gì khiến quyết định đó hợp lý hoặc không hợp lý?
4. Vì sao kiểm thử tính đúng đắn của A và kiểm soát quyền ở C không nên coi là Could Have để dễ đạt hạn?
5. Nếu 5 ngày-người bổ sung vẫn chưa đủ sửa A, nhóm cần cung cấp thông tin và phương án nào cho bên có thẩm quyền?
6. Nhóm nên thử rủi ro nào sớm trong timebox đầu để không phát hiện muộn?
7. Những chỉ số và phản hồi nào giúp đánh giá đợt giao thành công **mà không cần hoàn tất mọi tính năng**?
8. Viết một thông điệp ngắn tới stakeholder làm rõ phạm vi giữ lại, phần dời, lý do và ranh giới chất lượng.

### Gợi ý hướng giải

Một phương án hợp lý theo bối cảnh:

- **Must:** A, B, C — luồng đăng ký đúng, người học xem kết quả và quyền truy cập/khả năng kiểm soát thiết yếu.
- **Should:** D — hữu ích nhưng ứng dụng đã có trạng thái thay thế được trong đợt đầu **nếu không có nghĩa vụ bắt buộc gửi email**.
- **Could:** E — tăng tiện ích nhưng không phải điều kiện cho đợt khai giảng.
- **Won't Have This Time:** F — chưa chứng minh giá trị và không thuộc chức năng cốt lõi.

Trước khi phát hiện lỗi, tổng Must là:

\[
15+7+6=28\ \text{ngày-người}.
\]

Nếu không phân bổ các mục khác, phần năng lực còn lại là:

\[
40-28=12\ \text{ngày-người}.
\]

Sau khi A tăng thêm 5 ngày-người, Must dự báo thành **33 ngày-người**, còn **7 ngày-người** trong tổng 40. Hai mức “còn lại” này **chưa tự nói lên tất cả**, vì vẫn có rủi ro, công việc dở và sai số ước lượng. Nếu ưu tiên D (4) và E (6) trước khi biết rủi ro A, nhóm đã dùng gần hết khả năng linh hoạt.

**Cần làm:** Dời các mục ít bắt buộc hơn, sửa và kiểm chứng A, giữ C; nếu 7 ngày-người còn lại không đủ cho các rủi ro Must, đưa quyết định về phạm vi tối thiểu và mốc lên người có thẩm quyền. Không bỏ kiểm soát quyền hoặc cho đăng ký vượt sức chứa chỉ vì đã tới ngày.

**Thông điệp minh họa:**

> “Để sẵn sàng cho ngày khai giảng với ngân sách hiện có, đợt này chúng tôi ưu tiên đăng ký đúng sức chứa, hiển thị trạng thái và kiểm soát quyền. Kiểm thử đã phát hiện lỗi cạnh tranh cần thêm công sức nên email và lịch nâng cao sẽ được xem xét lại sau khi phần cốt lõi đạt chất lượng. Chúng tôi sẽ cập nhật trạng thái kiểm chứng và dự báo dựa trên kết quả thử nghiệm, không coi các chức năng chưa qua kiểm thử là hoàn tất.”

Một câu trả lời tốt nêu **giới hạn, giả định, thẩm quyền và bằng chứng**, không chỉ phân loại bốn nhãn.

## 21. Tình huống phản biện: khi “cố định tất cả” là không khả thi

**Đề bài:** Một tổ chức muốn ra mắt hệ thống thanh toán mới vào ngày cố định, ngân sách không tăng, yêu cầu bắt buộc bao gồm chuyển đổi toàn bộ dữ liệu lịch sử, tích hợp bốn đối tác và chứng nhận tuân thủ chưa có kết quả. Các chuyên gia ước tính riêng khối lượng Must đã vượt năng lực khả dụng.

Hãy xem hai phản ứng:

**Phản ứng A:** “Áp dụng DSDM nghĩa là không bao giờ dời ngày; cứ đổi mọi công việc chưa xong sang Should và để người dùng sử dụng trước.”

**Phản ứng B:** “Làm rõ lại kết quả bắt buộc và rủi ro, tìm lát cắt hoặc phương án chuyển đổi từng giai đoạn nếu hợp lệ, nhưng nếu không thể đáp ứng các nghĩa vụ tối thiểu thì minh bạch sự bất khả thi và xin quyết định phù hợp về phạm vi, ngày, chi phí hoặc phương án kinh doanh.”

**Phản ứng B phù hợp với tư duy quản lý ràng buộc có trách nhiệm.** DSDM giúp ưu tiên và học nhanh nhưng **không miễn trừ kiểm soát an toàn, nghĩa vụ pháp lý hay thực tế về năng lực**. Có lúc kết quả đúng là xác nhận **không thể giao phạm vi đã yêu cầu tại mốc hiện tại**, rồi thay đổi kế hoạch qua thẩm quyền phù hợp.

## 22. Ghi nhớ và tự kiểm tra

**DSDM** giúp nhóm phát triển phần mềm thích ứng nhưng vẫn **quản lý thời gian, chi phí, chất lượng và phạm vi** bằng việc tập trung vào nhu cầu kinh doanh, hợp tác, timeboxing, phát triển tăng dần/lặp và MoSCoW.

Điểm cốt lõi của bài:

1. **Giữ mốc thời gian và ngân sách** là mục tiêu quản lý cần được hỗ trợ bằng năng lực thực tế, không phải áp lực.
2. **Không đánh đổi mức chất lượng đã thỏa thuận** của phần được giao; bảo mật, tính đúng đắn và kiểm thử thiết yếu không phải “phạm vi phụ” tùy tiện.
3. **Linh hoạt phạm vi** nghĩa là biết rõ Must Have, có lựa chọn dời Should/Could và thống nhất Won't Have This Time.
4. **MoSCoW chỉ có ích khi có quyền quyết định và khoảng linh hoạt thật**, không phải khi mọi yêu cầu được dán nhãn Must.
5. **Timebox và Increment** làm lộ rủi ro sớm để có thể điều chỉnh trước khi quá muộn.
6. **Nếu Must vượt năng lực và không có phương án hợp lệ**, phải báo sự thật và xin quyết định, không che bằng số phần trăm hoặc bỏ chất lượng.

Tự kiểm tra:

1. Vì sao DSDM thường xem phạm vi là yếu tố linh hoạt khi thời gian và chi phí bị giới hạn?
2. Phân biệt **giảm phạm vi chức năng** với **giảm chất lượng** bằng một ví dụ đăng ký workshop.
3. Bốn nhóm MoSCoW có ý nghĩa gì? Vì sao W là *Won't Have This Time*?
4. Điều gì chứng minh một yêu cầu xứng đáng là Must thay vì Should?
5. Vì sao không nên áp quy tắc 60% Must theo số lượng PBI?
6. Tám nguyên tắc DSDM hỗ trợ nhau ra sao khi dự án gặp thay đổi?
7. Một timebox hữu ích khác với việc “cố code thật nhanh tới deadline” ở điểm nào?
8. **Build Incrementally from Firm Foundations** có nghĩa phải hoàn tất toàn bộ kiến trúc và đặc tả ngay từ đầu không?
9. Nếu Could Have bị dời, dự án có nhất thiết thất bại không? Cần xem điều gì để đánh giá?
10. Với Must 48 ngày-người và năng lực 50 ngày-người, rủi ro lớn nhất đối với khả năng thích ứng là gì?
11. Ai cần tham gia quyết định khi một nghĩa vụ pháp lý mới khiến Must tăng vượt năng lực?
12. DSDM có thể bổ trợ Scrum, Kanban và XP như thế nào mà không trộn lẫn trách nhiệm giữa các phương pháp?

Khi thảo luận một dự án có hạn rõ ràng, hãy hỏi: **“Điều gì bắt buộc phải đúng vào ngày giao, phần nào có thể dời mà người dùng vẫn nhận được giá trị, tiêu chuẩn chất lượng nào không thể bỏ, và dữ liệu nào cho thấy kế hoạch còn khả thi?”** Trả lời được những câu hỏi ấy là bước quan trọng để áp dụng DSDM theo tinh thần Agile: **giao giá trị đúng thời điểm, quản lý rủi ro minh bạch và điều chỉnh phạm vi bằng bằng chứng**.
