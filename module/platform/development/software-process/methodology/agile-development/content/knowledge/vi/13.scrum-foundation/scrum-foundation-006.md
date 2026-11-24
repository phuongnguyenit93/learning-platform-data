# Mối liên hệ giữa trách nhiệm, sự kiện, tạo tác và cam kết

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện **ba trách nhiệm giải trình (accountabilities)** trong Scrum Team: Product Owner, Scrum Master và Developers; giải thích cách họ phối hợp thay vì làm việc như ba bộ phận tách biệt.
2. Mô tả **năm sự kiện Scrum**: Sprint, Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective, cùng thông tin được kiểm tra và quyết định có thể được điều chỉnh tại mỗi sự kiện.
3. Ghép chính xác **ba tạo tác (artifacts)** với **ba cam kết (commitments)**: Product Backlog – Product Goal, Sprint Backlog – Sprint Goal, Increment – Definition of Done.
4. Giải thích cách các trách nhiệm, sự kiện, tạo tác và cam kết hỗ trợ **minh bạch – kiểm tra – thích nghi** trong một vòng phát triển sản phẩm tăng dần.
5. Phân tích tình huống Scrum thực tế để xác định ai cần hành động, thông tin nào phải minh bạch, sự kiện nào giúp kiểm tra và điều gì quyết định một Increment thật sự hoàn thành.

## 1. Scrum là một hệ thống, không phải bộ nghi thức độc lập

Scrum là một khung làm việc nhẹ giúp con người, nhóm và tổ chức tạo ra giá trị thông qua các giải pháp thích ứng cho vấn đề phức tạp. Thay vì cố xác định toàn bộ công việc từ đầu, Scrum giúp nhóm chọn mục tiêu có ý nghĩa, tạo **Increment** dùng được, kiểm tra kết quả và điều chỉnh hướng đi.

Những thành phần Scrum có vai trò bổ sung:

| Thành phần | Câu hỏi giúp trả lời | Vai trò trong thực nghiệm |
| --- | --- | --- |
| **Trách nhiệm giải trình** | Ai chịu trách nhiệm về giá trị, cách áp dụng Scrum và việc tạo Increment đạt chất lượng? | Xác định quyền và nghĩa vụ để chuyển quan sát thành hành động. |
| **Sự kiện** | Khi nào nhóm cùng lập kế hoạch, kiểm tra tình hình và điều chỉnh? | Tạo cơ hội kiểm tra và thích nghi theo một nhịp đều đặn. |
| **Tạo tác** | Thực trạng sản phẩm, công việc và kết quả được minh bạch qua đâu? | Cung cấp thông tin chung để các quyết định dựa trên thực tế. |
| **Cam kết của tạo tác** | Mục tiêu hoặc tiêu chuẩn nào định hướng và giúp kiểm tra tạo tác? | Làm rõ hướng tiến triển, mức tập trung và chất lượng cần có. |

Trong Scrum, **tính minh bạch của tạo tác và cam kết** giúp các sự kiện kiểm tra có ý nghĩa. Người có trách nhiệm phù hợp sau đó có thể thích nghi **thứ tự ưu tiên, kế hoạch hoặc cách cộng tác** dựa trên điều đã học.

### Ví dụ mở đầu

Một Scrum Team đang xây dựng tính năng **“Tiếp tục học”** cho nền tảng học trực tuyến:

- Product Owner muốn giảm khó khăn khi học viên tìm lại bài đang học.
- Developers thấy API lưu tiến độ có thể trả dữ liệu cũ khi người dùng đổi thiết bị.
- Scrum Master nhận thấy nhiều vấn đề chỉ được báo vào cuối Sprint, khiến cả nhóm khó thích nghi kịp.

Nếu chỉ tổ chức đủ họp nhưng che lỗi, gọi mọi ticket “Done” và không điều chỉnh Product Backlog, nhóm **chưa thực sự vận hành theo thực nghiệm**. Ngược lại, khi có mục tiêu rõ, trạng thái thật, tiêu chuẩn chất lượng chung và các cuộc kiểm tra dẫn đến quyết định, các thành phần mới kết nối thành Scrum.

## 2. Bản đồ tổng thể: ba tạo tác gắn với ba cam kết

Trong Scrum, **mỗi tạo tác có đúng một cam kết gắn với nó** theo Scrum Guide:

| Tạo tác | Cam kết tương ứng | Câu hỏi trọng tâm |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Sản phẩm cần đạt trạng thái tương lai nào và còn cần làm gì để tiến đến đó? |
| **Sprint Backlog** | **Sprint Goal** | Vì sao Sprint này có giá trị và Developers dự định đạt mục tiêu bằng cách nào? |
| **Increment** | **Definition of Done (DoD)** | Phần sản phẩm nào thật sự đáp ứng tiêu chuẩn chất lượng để được xem là hoàn thành? |

Sơ đồ liên hệ:

~~~mermaid
flowchart TD
    PG["Product Goal: hướng sản phẩm"] --> PB["Product Backlog: việc cần để cải tiến sản phẩm"]
    PB --> PL["Sprint Planning: chọn mục tiêu và cách tiếp cận"]
    PL --> SG["Sprint Goal: mục tiêu chung của Sprint"]
    PL --> SB["Sprint Backlog: mục tiêu + item được chọn + kế hoạch"]
    SG --> SB
    SB --> DEV["Developers tạo, tích hợp và kiểm tra sản phẩm"]
    DEV --> INC["Increment: phần sản phẩm dùng được"]
    DOD["Definition of Done: tiêu chuẩn chất lượng"] --> INC
    INC --> SR["Sprint Review: xem kết quả và bối cảnh"]
    SR --> PB
    SB --> DS["Daily Scrum: kiểm tra tiến triển, điều chỉnh kế hoạch"]
    DS --> SB
    INC --> RET["Sprint Retrospective: cải tiến chất lượng và hiệu quả"]
    RET --> DEV
~~~

Sơ đồ biểu diễn **các mối liên hệ thực hành**, không hàm ý rằng chỉ được tạo Increment đúng một lần hoặc chỉ được cập nhật Product Backlog vào Sprint Review. Trong một Sprint có thể có **nhiều Increment**, chúng có thể được giao cho các bên liên quan trước Sprint Review nếu đáp ứng điều kiện. Product Backlog và kế hoạch có thể được làm rõ khi xuất hiện thông tin mới, không phải đợi đến một “ngày họp được phép sửa”.

### Ba lớp định hướng

- **Product Goal** cho đội biết **đích đến ở cấp sản phẩm**.
- **Sprint Goal** cho đội biết **mục tiêu chung quan trọng nhất trong Sprint hiện tại**.
- **Definition of Done** cho đội và các bên liên quan biết **khi nào sản phẩm thật sự đạt chất lượng của Increment hoàn thành**.

Thiếu Product Goal, đội dễ chỉ hoàn tất ticket mà không đi tới kết quả sản phẩm. Thiếu Sprint Goal, đội dễ chạy theo từng yêu cầu rời rạc. Thiếu DoD, mọi người có thể hiểu chữ “xong” theo những tiêu chuẩn khác nhau.

## 3. Scrum Team và ba trách nhiệm giải trình

Scrum Team gồm **một Product Owner, một Scrum Master và Developers**. Đây là một nhóm **liên chức năng (cross-functional)**, **tự quản (self-managing)**: có những kỹ năng cần thiết để tạo giá trị mỗi Sprint và tự quyết định nội bộ **ai làm gì, khi nào và như thế nào** trong phạm vi trách nhiệm của mình.

Scrum Team không có các **đội con hoặc hệ thống cấp bậc nội bộ** theo định nghĩa Scrum; trách nhiệm không biến Product Owner thành quản lý kỹ thuật, Scrum Master thành thư ký cuộc họp hoặc Developers thành người chỉ nhận lệnh. Scrum Guide mô tả Scrum Team thường **10 người hoặc ít hơn**, đủ nhỏ để linh hoạt và đủ lớn để hoàn thành công việc có ý nghĩa; đây không phải quy tắc rằng đội 11 người tự động không thể tạo ra giá trị.

### 3.1. Product Owner: tối đa hóa giá trị sản phẩm

**Product Owner chịu trách nhiệm giải trình về việc tối đa hóa giá trị sản phẩm** tạo ra từ công việc của Scrum Team. Họ cũng chịu trách nhiệm quản lý Product Backlog hiệu quả, bao gồm:

1. Xây dựng và truyền đạt rõ **Product Goal**.
2. Tạo và truyền đạt rõ **Product Backlog Items**.
3. Sắp xếp thứ tự **Product Backlog Items**.
4. Bảo đảm Product Backlog minh bạch, được nhìn thấy và hiểu rõ.

Product Owner có thể **ủy quyền việc thực hiện** một số hoạt động trên, nhưng **không chuyển giao trách nhiệm giải trình**. Product Owner là **một người**, không phải một ủy ban. Họ cần trao đổi với khách hàng, người dùng, kỹ thuật và các bên liên quan, nhưng các bên muốn đổi Product Backlog phải tôn trọng quyền quyết định ưu tiên của Product Owner.

**Ví dụ:** Doanh nghiệp muốn thêm dashboard mới, còn học viên đang gặp lỗi mất tiến độ. Product Owner trao đổi về giá trị, mức nghiêm trọng, nghĩa vụ hợp đồng và chi phí trì hoãn, rồi giải thích thứ tự Product Backlog; họ không cần tự viết code hoặc tự quyết định cách sửa API.

### 3.2. Developers: tạo Increment đạt chất lượng

**Developers** là những thành viên Scrum Team cam kết tạo ra mọi phần của **Increment dùng được trong mỗi Sprint**. Họ chịu trách nhiệm giải trình về:

- Tạo **kế hoạch cho Sprint**, tức Sprint Backlog.
- Bảo đảm chất lượng bằng việc **tuân thủ Definition of Done**.
- Điều chỉnh kế hoạch mỗi ngày để hướng tới **Sprint Goal**.
- Giữ nhau có trách nhiệm như những người làm nghề chuyên nghiệp.

Từ “Developers” trong Scrum không chỉ giới hạn ở người viết code. Tùy sản phẩm, những người có kỹ năng kiểm thử, thiết kế, dữ liệu và các năng lực tạo Increment có thể nằm trong Developers, không phải một nhóm “nhận bàn giao” độc lập khỏi Scrum Team.

**Ví dụ:** Khi phát hiện API đồng bộ không bảo toàn dữ liệu, Developers cần minh bạch rủi ro, điều chỉnh cách thực hiện và làm việc với Product Owner nếu cần thương lượng phạm vi. Họ không được gắn nhãn “Done” cho luồng đang sai chỉ để đạt số lượng ticket đã dự báo.

### 3.3. Scrum Master: thiết lập Scrum và nâng hiệu quả Scrum Team

**Scrum Master chịu trách nhiệm giải trình về việc thiết lập Scrum theo Scrum Guide** và về **hiệu quả của Scrum Team**. Họ phục vụ Scrum Team và tổ chức thông qua hỗ trợ hiểu Scrum, coaching, giúp loại bỏ trở ngại ảnh hưởng hiệu quả, bảo đảm các sự kiện diễn ra tích cực, hữu ích và trong timebox.

Scrum Master còn hỗ trợ Product Owner trong việc xác định mục tiêu, quản lý backlog hiệu quả và hỗ trợ tổ chức hiểu cách tiếp cận thực nghiệm. Đây là **trách nhiệm phục vụ và tạo điều kiện**, không đồng nghĩa sở hữu backlog, tự giao ticket hay quyết định chất lượng thay Developers.

**Ví dụ:** Khi Daily Scrum biến thành báo cáo từng người cho quản lý, Scrum Master giúp đội thấy vấn đề: sự kiện này phải phục vụ **Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh kế hoạch**. Họ hỗ trợ thay đổi cách họp chứ không đứng ra phân công từng task thay đội.

### 3.4. Trách nhiệm riêng và trách nhiệm chung

| Câu hỏi | Trọng tâm trách nhiệm | Các bên cần cộng tác |
| --- | --- | --- |
| Sản phẩm nên giải quyết nhu cầu nào trước? | **Product Owner** chịu trách nhiệm với giá trị và thứ tự Product Backlog | Người dùng, các bên liên quan, Developers |
| Cách nào khả thi và đủ chất lượng để giao? | **Developers** lập kế hoạch và bảo đảm Increment đáp ứng DoD | Product Owner làm rõ giá trị; chuyên gia phù hợp tham gia |
| Scrum đang bị áp dụng máy móc hoặc đội gặp trở ngại hệ thống? | **Scrum Master** giúp thiết lập Scrum và cải thiện hiệu quả | Cả Scrum Team và tổ chức |
| Sprint này hướng đến kết quả gì? | **Cả Scrum Team** phối hợp ở Sprint Planning | Product Owner đề xuất giá trị; Developers dự báo công việc và cách làm |
| Kết quả cuối Sprint có tạo giá trị và đáng thay đổi backlog? | **Cả Scrum Team và các bên liên quan** trao đổi ở Sprint Review | Product Owner chịu trách nhiệm thứ tự Product Backlog |
| Sản phẩm đã thật sự đạt chất lượng chung chưa? | **Developers** tuân thủ DoD; Scrum Team duy trì minh bạch chất lượng | Các tiêu chuẩn của tổ chức và bên có trách nhiệm liên quan |

Một Scrum Team có **trách nhiệm chung** đối với việc tạo ra Increment có giá trị và dùng được mỗi Sprint. Sự khác biệt về trách nhiệm giải trình giúp định rõ **ai phải bảo đảm điều gì**, không nhằm đẩy lỗi qua lại.

## 4. Năm sự kiện tạo nhịp kiểm tra và thích nghi

Scrum có **năm sự kiện**: Sprint, Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective. **Sprint là sự kiện bao chứa bốn sự kiện còn lại**; mỗi Sprint bắt đầu ngay sau Sprint trước kết thúc.

Những sự kiện là các cơ hội chính thức để **kiểm tra và thích nghi**, giảm nhu cầu tạo ra nhiều cuộc họp khác không cần thiết.

| Sự kiện | Để làm gì? | Người tham gia liên quan | Kết quả mong đợi |
| --- | --- | --- | --- |
| **Sprint** | Tạo nhịp công việc ngắn, nhất quán để tạo giá trị | Toàn Scrum Team | Một hoặc nhiều Increment đạt DoD; học hỏi và tiến gần Product Goal |
| **Sprint Planning** | Xác định vì sao Sprint có giá trị, làm gì và làm thế nào | Toàn Scrum Team | **Sprint Goal và Sprint Backlog** với kế hoạch ban đầu |
| **Daily Scrum** | Kiểm tra tiến độ hướng Sprint Goal, điều chỉnh kế hoạch tiếp theo | **Developers**; PO/SM tham gia như Developers nếu họ thực hiện công việc Sprint Backlog | Điều chỉnh kế hoạch thực hiện, nhận diện phối hợp/trở ngại |
| **Sprint Review** | Kiểm tra kết quả Sprint và xác định điều chỉnh hướng tương lai | Scrum Team và các bên liên quan quan trọng | Thông tin phản hồi, thích nghi Product Backlog hoặc hướng sản phẩm |
| **Sprint Retrospective** | Tìm cách tăng chất lượng và hiệu quả làm việc | Scrum Team | Những cải tiến có thể đưa vào thực hành sớm |

### Timebox trong Scrum

| Sự kiện | Giới hạn theo Scrum Guide cho Sprint dài một tháng | Ghi chú |
| --- | --- | --- |
| Sprint | **Tối đa một tháng** | Là một khoảng thời gian cố định; Sprint ngắn hơn có các timebox sự kiện thường ngắn hơn. |
| Sprint Planning | **Tối đa 8 giờ** | Với Sprint một tháng; Sprint ngắn hơn thường cần ít thời gian hơn. |
| Daily Scrum | **15 phút** | Diễn ra mỗi ngày làm việc của Sprint. |
| Sprint Review | **Tối đa 4 giờ** | Với Sprint một tháng. |
| Sprint Retrospective | **Tối đa 3 giờ** | Với Sprint một tháng; là sự kiện kết thúc Sprint. |

Timebox là **giới hạn tối đa**, không phải yêu cầu dùng hết giờ. Một Daily Scrum 15 phút không giúp ích nếu chỉ đọc ticket; một Sprint Review 30 phút có thể có giá trị nếu thực sự kiểm tra Increment và có điều chỉnh dựa trên bằng chứng.

## 5. Sprint: khung thời gian của giá trị và học hỏi

**Sprint** dài tối đa một tháng, có độ dài nhất quán đủ để tạo nhịp thực nghiệm. Trong Sprint:

- Không thực hiện thay đổi làm **nguy hiểm Sprint Goal**.
- Chất lượng **không bị giảm**.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng với Product Owner khi học thêm.

Scrum không yêu cầu “đóng băng mọi yêu cầu” suốt Sprint. Điều cần bảo vệ là **Sprint Goal**, không phải danh sách task bất biến từ ngày đầu tiên.

**Chỉ Product Owner có quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời.** Đây là tình huống đặc biệt, không phải biện pháp thông thường để xử lý việc trễ hoặc một item khó hơn dự kiến.

### Ví dụ

Sprint Goal là “Học viên mở lại được bài đang học một cách chính xác”. Giữa Sprint:

- Đội kinh doanh đề nghị thêm hiệu ứng huy hiệu: có thể đưa vào Product Backlog để cân nhắc sau.
- Tester phát hiện người dùng B nhìn thấy tiến độ người dùng A: phải xử lý theo mức rủi ro và tiêu chuẩn chất lượng; Developers phối hợp Product Owner nếu tác động phạm vi.
- Dữ liệu người dùng cho thấy vị trí nút “Tiếp tục học” khó tìm: đội có thể điều chỉnh cách thực hiện để đạt Sprint Goal tốt hơn.

Sprint tạo **sự tập trung ổn định đủ để hoàn tất**, nhưng vẫn cho phép học và điều chỉnh có kỷ luật.

## 6. Sprint Planning: kết nối Product Goal, Product Backlog và Sprint Goal

Sprint Planning bắt đầu Sprint bằng cách giải quyết ba chủ đề:

1. **Why — Vì sao Sprint này có giá trị?** Product Owner đề xuất cách tăng giá trị; cả Scrum Team cộng tác xác định **Sprint Goal**.
2. **What — Có thể hoàn thành điều gì trong Sprint?** Developers thảo luận với Product Owner để chọn các Product Backlog Items. Năng lực, hiệu quả gần đây, Definition of Done và độ hiểu biết của công việc giúp họ dự báo phù hợp.
3. **How — Công việc được thực hiện như thế nào?** Developers lên kế hoạch để biến những item được chọn thành **Increment đạt Definition of Done**; kế hoạch có thể được chia thành việc nhỏ hơn và bổ sung khi học thêm.

Đến cuối Sprint Planning, **Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện** cùng tạo nên **Sprint Backlog**.

### Ví dụ Sprint Planning

Giả sử Product Goal là:

> “Học viên học liên tục trên thiết bị thường dùng và không mất tiến độ đã ghi nhận.”

Product Backlog được xếp thứ tự với những item như:

| Item | Mục đích | Tình trạng hiểu biết |
| --- | --- | --- |
| Sửa dữ liệu tiến độ bị gửi lặp | Bảo vệ tính đúng đắn của tiến độ | Lỗi đã tái hiện, tiêu chí rõ |
| Hiển thị bài gần nhất còn quyền | Giúp học viên quay lại bài nhanh | Phạm vi nhỏ, API đã có |
| Đồng bộ vị trí video trên hai thiết bị | Giảm gián đoạn khi chuyển thiết bị | Còn rủi ro xung đột dữ liệu |
| Huy hiệu hoàn thành bài | Tăng hứng thú học | Chưa có bằng chứng ưu tiên cao |

Scrum Team có thể thống nhất **Sprint Goal**:

> “Học viên nhìn thấy và mở lại được bài hợp lệ gần nhất mà không truy cập nhầm tiến độ của người khác.”

Developers sau đó chọn lượng công việc có thể hoàn thành theo năng lực và DoD, lập kế hoạch API, giao diện, kiểm thử và xử lý lỗi. Hạng mục đồng bộ video toàn diện có thể tiếp tục ở Product Backlog vì chưa đủ thông tin để hứa giao.

### Ngộ nhận cần tránh

- **Product Owner** không đơn phương giao danh sách task cố định cho Developers.
- **Developers** không chỉ nhận một số story point rồi cam kết bất chấp chất lượng.
- **Scrum Master** không phải người ấn định nội dung Sprint để “bảo đảm velocity”.
- **Sprint Goal** không nhất thiết là tên của một tính năng; nó mô tả kết quả chung đủ rõ để định hướng các quyết định.

## 7. Daily Scrum: Developers điều chỉnh Sprint Backlog, không báo cáo cho cấp trên

Daily Scrum là sự kiện **15 phút mỗi ngày làm việc của Sprint**, dành cho Developers kiểm tra tiến độ hướng **Sprint Goal** và thích nghi **Sprint Backlog** khi cần.

Scrum Guide không bắt buộc mẫu “Hôm qua tôi làm gì? Hôm nay làm gì? Có blocker gì?”; đội có thể chọn hình thức khác nếu hướng vào Sprint Goal và tạo ra kế hoạch hành động cho ngày làm việc tiếp theo.

### Một Daily Scrum có ý nghĩa

> **Sprint Goal:** Học viên mở lại được bài hợp lệ gần nhất.
>
> **Thực tế:** Luồng đọc tiến độ đã chạy; kiểm thử phát hiện trường hợp quyền truy cập chưa được lọc đúng.
>
> **Ảnh hưởng:** Chưa thể xem story hoàn thành theo DoD.
>
> **Điều chỉnh:** Hai Developers tập trung xử lý lỗi phân quyền và bổ sung test; một thành viên hỗ trợ kiểm tra truy vấn; việc chỉnh hiệu ứng giao diện chưa cần bắt đầu.
>
> **Theo dõi:** Chạy lại test tích hợp và kiểm tra trên thiết bị thử trong ngày.

Đây là kiểm tra và thích nghi. Nếu cần trao đổi kỹ thuật dài, các thành viên liên quan có thể làm ngay **sau Daily Scrum**, không kéo cả đội vượt timebox.

### Mối liên hệ với trách nhiệm và tạo tác

- **Developers** chủ động điều chỉnh kế hoạch.
- **Sprint Goal** là tiêu chí để biết việc gì quan trọng.
- **Sprint Backlog** minh bạch thay đổi kế hoạch và trạng thái.
- **Scrum Master** hỗ trợ đội hiểu mục đích và tháo gỡ trở ngại đối với hiệu quả Scrum, không biến Daily Scrum thành buổi giao việc.

Daily Scrum là cơ hội chính thức, không có nghĩa các thành viên chỉ được phối hợp **một lần mỗi ngày**. Trở ngại cần xử lý ngay nên được trao đổi ngay.

## 8. Sprint Review: kiểm tra Increment và điều chỉnh Product Backlog

Sprint Review diễn ra gần cuối Sprint để **kiểm tra kết quả Sprint và xác định các thích nghi trong tương lai**. Scrum Team cùng các bên liên quan xem **điều đã đạt, môi trường đã thay đổi ra sao và việc gì có giá trị tiếp theo**.

Một Sprint Review hữu ích thường gồm:

1. Nhắc lại **Product Goal** và mục tiêu Sprint đã theo đuổi.
2. Cho mọi người thấy **Increment thực sự hoạt động** và phần nào đáp ứng DoD.
3. Trao đổi phản hồi người dùng, bối cảnh thị trường, rủi ro và điều kiện mới.
4. Thảo luận lựa chọn tiếp theo; **Product Backlog có thể được điều chỉnh** để phản ánh hiểu biết mới.

Sprint Review **không phải** chỉ là buổi trình chiếu slide, đánh giá từng người hay cổng phê duyệt bắt buộc trước mỗi lần phát hành. Increment có thể được giao cho người dùng **trước khi Sprint kết thúc** nếu đáp ứng các điều kiện cần thiết; Review vẫn là dịp quan trọng để cùng kiểm tra và học hỏi.

### Ví dụ phản hồi dẫn đến thay đổi

Ở Sprint Review, người học dùng thử nhận thấy nút “Tiếp tục học” dễ tìm nhưng mong muốn mở đúng vị trí video thay vì đầu bài. Đội cũng nhìn thấy dữ liệu việc mở lại bài đã tăng, nhưng mẫu thử còn nhỏ.

Product Owner có thể:

- Giữ Product Goal vì vấn đề học liên tục vẫn có giá trị.
- Đưa nghiên cứu “vị trí video” lên cao hơn trong Product Backlog.
- Đề nghị một lát cắt thử nghiệm nhỏ để xác minh mức cần thiết trước khi đầu tư đồng bộ mọi thiết bị.
- Giữ nguyên ràng buộc quyền truy cập và khả năng vận hành.

Đó là **điều chỉnh từ bằng chứng**, không phải thay kế hoạch tùy ý.

## 9. Sprint Retrospective: cải tiến cách tạo Increment

**Sprint Retrospective** là sự kiện kết thúc Sprint. Mục đích là lên kế hoạch tăng **chất lượng và hiệu quả**: cách cộng tác, quy trình, công cụ, kỹ năng, Definition of Done và những yếu tố ảnh hưởng đến công việc.

Scrum Team có thể kiểm tra:

- Vì sao ticket thường nằm chờ review nhiều ngày?
- Vì sao lỗi tích hợp chỉ xuất hiện sát Sprint Review?
- Vì sao tiêu chí chấp nhận bị hiểu khác nhau?
- Có rào cản tổ chức nào khiến đội không tự quản được?
- Cách làm nào giúp giao Increment đạt DoD ổn định hơn?

### Ví dụ cải tiến có thể kiểm chứng

**Quan sát:** Trong Sprint vừa qua, ba story bị chậm do quy tắc xử lý lỗi chỉ được hỏi khi gần hoàn thành.

**Giả thuyết cải tiến:** Một cuộc trao đổi ngắn giữa Product Owner, Developer và Tester trước khi bắt đầu các story rủi ro cao sẽ giảm thời gian chờ quyết định nghiệp vụ.

**Thử nghiệm:** Với một số story sắp tới, nhóm dùng ví dụ “luồng chính – ngoại lệ – lỗi”, ghi quyết định và người xác nhận; theo dõi số lần bị chặn do thiếu quy tắc và mức làm lại.

**Điểm xem lại:** Sprint Retrospective tiếp theo.

Cải tiến có thể đưa vào **Sprint Backlog kế tiếp** nếu phù hợp và khả thi. Không nên tạo danh sách nhiều hành động mà không có người sở hữu hoặc cách quan sát tác dụng.

### Phân biệt Review và Retrospective

| Sprint Review | Sprint Retrospective |
| --- | --- |
| Trọng tâm: **sản phẩm, kết quả và hướng đi tiếp theo**. | Trọng tâm: **cách Scrum Team làm việc, chất lượng và hiệu quả**. |
| Có các bên liên quan quan trọng cùng Scrum Team. | Là sự kiện của Scrum Team. |
| Xem Increment, phản hồi, bối cảnh, Product Goal và Product Backlog. | Xem tương tác, quy trình, công cụ, Definition of Done và cơ hội cải tiến. |
| Có thể dẫn tới sắp xếp lại Product Backlog. | Dẫn tới thay đổi cách làm và kế hoạch cải tiến. |

Hai sự kiện có liên quan: **phản hồi sản phẩm** có thể cho thấy đội cần cải thiện năng lực kỹ thuật; **cải tiến kỹ thuật** giúp Sprint sau kiểm chứng giá trị nhanh hơn.

## 10. Product Backlog và Product Goal: nhìn thấy hướng đi sản phẩm

**Product Backlog** là danh sách có thứ tự, phát triển liên tục về những gì cần để cải tiến sản phẩm; nó là **nguồn công việc duy nhất được Scrum Team thực hiện**. Product Goal là cam kết của Product Backlog, mô tả **trạng thái tương lai của sản phẩm** để Scrum Team lập kế hoạch.

Product Backlog không phải bảng hợp đồng cố định từ ngày khởi động dự án. Các hạng mục gần triển khai thường cần rõ hơn, còn ý tưởng xa có thể tồn tại ở mức giả thuyết. Hoạt động **Product Backlog refinement** giúp chia nhỏ và làm rõ item, nhưng **không phải sự kiện Scrum bắt buộc riêng** với timebox cố định.

### Ví dụ Product Goal

> “Học viên có thể bắt đầu, tiếp tục và hoàn thành phần học trên thiết bị thường dùng mà không mất tiến độ.”

Một Product Goal tốt định hướng quyết định về **giá trị**, không chỉ liệt kê công nghệ hoặc số màn hình. Nhóm có thể dùng outcome như thời gian tìm lại bài, tỷ lệ người dùng mở đúng bài và lỗi mất tiến độ để xem tiến triển. Những chỉ số cụ thể cần định nghĩa, dữ liệu nền và điều kiện đo trước khi được coi là mục tiêu định lượng.

### Điều Product Owner cần minh bạch

| Nội dung | Ví dụ cần thấy trên backlog |
| --- | --- |
| **Thứ tự ưu tiên** | Vì sao xử lý lỗi mất tiến độ trước khi làm huy hiệu? |
| **Mục tiêu/value** | Item cải thiện kết quả nào của người dùng hoặc mục tiêu tổ chức? |
| **Mức độ hiểu biết** | Điều gì đã xác minh, điều gì còn giả định? |
| **Phụ thuộc/rủi ro** | API ngoài, bảo mật, migration, công việc bị chặn? |
| **Khả năng chia nhỏ** | Có lát cắt nào giao được để nhận phản hồi sớm hơn? |

Product Owner cần cộng tác với Developers để hiểu tính khả thi và chất lượng; họ không phải người duy nhất nghĩ ra giải pháp, nhưng là người **chịu trách nhiệm về Product Backlog và giá trị**.

## 11. Sprint Backlog và Sprint Goal: tập trung nhưng có thể thích nghi

**Sprint Backlog** gồm ba thành phần:

1. **Sprint Goal** — lý do, mục tiêu chung của Sprint (*why*).
2. **Product Backlog Items được chọn** — điều dự kiến làm (*what*).
3. **Kế hoạch có thể hành động để giao Increment** — cách thực hiện (*how*).

Đây là **kế hoạch do Developers tạo và dành cho Developers**, được điều chỉnh khi biết thêm thông tin. Scrum Master và Product Owner hỗ trợ theo trách nhiệm của họ, nhưng không dùng Sprint Backlog như bảng phân công từ cấp trên.

### Ví dụ bảng Sprint Backlog

| Thành phần | Nội dung |
| --- | --- |
| **Sprint Goal** | Học viên mở lại được bài hợp lệ gần nhất sau khi đăng nhập thiết bị khác. |
| Item 1 | Hiển thị bài gần nhất của tài khoản đang đăng nhập và còn quyền truy cập. |
| Item 2 | Mở đúng bài qua nút “Tiếp tục học”. |
| Item 3 | Xử lý rõ trường hợp không có tiến độ hoặc dịch vụ đọc tiến độ thất bại. |
| Kế hoạch kỹ thuật | Kiểm tra API, xây luồng giao diện, tích hợp, kiểm thử phân quyền và hồi quy. |
| Rủi ro | Dữ liệu tiến độ cũ, quyền truy cập đã hết hạn; cần xác nhận quy tắc với Product Owner. |

Khi phát hiện item 3 lớn hơn dự kiến, Developers và Product Owner có thể trao đổi về **cách đạt Sprint Goal**, điều chỉnh kế hoạch và minh bạch dự báo. Không nên che phần chưa làm hoặc âm thầm bỏ kiểm thử để báo “đúng kế hoạch”.

### Sprint Goal khác “hoàn tất toàn bộ danh sách”

Một Sprint Goal là **một mục tiêu chung** tạo sự liên kết giữa các việc. Nó cung cấp mức linh hoạt về **phần công việc chính xác cần làm** để đạt mục tiêu. Nếu đội chỉ đặt Sprint Goal là “Hoàn thành ticket A, B, C, D”, họ có thể khó đánh giá điều gì cần giữ khi phát sinh phản hồi.

Sprint Goal cũng không đồng nghĩa Product Goal; Product Goal thường lớn và tồn tại qua nhiều Sprint, còn Sprint Goal là **một bước cụ thể** hướng về đích đó.

## 12. Increment và Definition of Done: chất lượng quyết định chữ “xong”

**Increment** là một bước tiến cụ thể hướng tới Product Goal, bổ sung vào những Increment trước và được **xác minh kỹ để hoạt động cùng nhau**. Một Sprint có thể tạo **nhiều Increment**. Công việc chỉ được xem là một phần của Increment khi đáp ứng **Definition of Done**.

### Definition of Done là gì?

**Definition of Done (DoD)** là mô tả chính thức trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng cần có của sản phẩm. Nó tạo **sự minh bạch về chất lượng và điều kiện hoàn tất**.

- Nếu tổ chức đã có **tiêu chuẩn DoD bắt buộc**, mọi Scrum Team phải tuân theo mức tối thiểu đó.
- Nếu chưa có tiêu chuẩn từ tổ chức, Scrum Team cần xây dựng DoD phù hợp với sản phẩm.
- Nếu nhiều Scrum Team cùng làm trên một sản phẩm, họ phải **cùng định nghĩa và tuân theo một DoD** cho sản phẩm đó.

**Ví dụ minh họa về DoD** cho một sản phẩm học trực tuyến:

- Chức năng đã tích hợp với phần sản phẩm hiện có và vận hành theo tiêu chí chấp nhận áp dụng.
- Các kiểm thử quan trọng và kiểm thử hồi quy liên quan đạt; lỗi nghiêm trọng chặn phát hành đã được xử lý theo tiêu chuẩn sản phẩm.
- Yêu cầu phân quyền, bảo mật dữ liệu và tính toàn vẹn tiến độ được đáp ứng.
- Những thay đổi cần thiết về quan sát, cấu hình, triển khai hoặc khôi phục được chuẩn bị và kiểm chứng.
- Tài liệu/hồ sơ bắt buộc cho sử dụng, bảo trì hoặc tuân thủ được cập nhật khi có tác động.

Đây **không phải DoD mặc định của Scrum**. Mỗi sản phẩm phải xác định tiêu chuẩn dựa trên bối cảnh, nghĩa vụ và rủi ro. DoD không nên chỉ là hộp đánh dấu hình thức.

### Acceptance Criteria khác DoD thế nào?

| Acceptance Criteria | Definition of Done |
| --- | --- |
| Mô tả **hành vi cụ thể của một Product Backlog Item** | Mô tả **tiêu chuẩn chất lượng chung** để Increment được xem là hoàn thành |
| Ví dụ: “Tài khoản B không nhìn thấy tiến độ A” | Ví dụ: “Các kiểm thử phân quyền liên quan phải đạt theo quy ước chất lượng” |
| Có thể thay đổi theo nhu cầu và phạm vi từng story | Tạo tiêu chuẩn chung, minh bạch và nhất quán của sản phẩm |
| Hỗ trợ xác nhận nội dung yêu cầu | Quyết định khi nào kết quả thực sự là Increment |

Nếu một Product Backlog Item chưa đạt DoD, **nó không được coi là một phần của Increment** và không nên được trình bày như công việc Done tại Sprint Review; nó quay lại Product Backlog để được xem xét trong tương lai. Một nguyên mẫu có thể dùng để khám phá, nhưng không được ngụy trang thành Increment đã đáp ứng chất lượng.

### Ví dụ kiểm tra một tuyên bố “đã xong”

Nhóm báo:

> “Giao diện nút ‘Tiếp tục học’ đã xong và demo được, nhưng API đang trả sai tài khoản trong một trường hợp; kiểm thử phân quyền chưa đạt.”

Kết luận đúng: phần giao diện **có thể đã hoàn thành một số task**, nhưng tính năng **chưa đáp ứng DoD** và chưa tạo Increment hoàn thành theo phạm vi đang tuyên bố. Đội cần sửa, kiểm thử và minh bạch với Product Owner; không lấy số lượng task đã làm làm thước đo hoàn tất sản phẩm.

## 13. Một Sprint từ đầu đến cuối: liên kết tất cả thành phần

### Bối cảnh

Một Scrum Team phát triển nền tảng học trực tuyến:

- **Product Goal:** Học viên có thể quay lại bài học thuận tiện và không mất tiến độ.
- **Product Owner:** Phân tích nhu cầu, chọn thứ tự Product Backlog dựa trên giá trị và rủi ro.
- **Developers:** Có năng lực phát triển, kiểm thử, UX và tích hợp cần để tạo Increment.
- **Scrum Master:** Hỗ trợ Scrum Team dùng Scrum hiệu quả, tháo gỡ trở ngại về phối hợp.

### Diễn tiến minh họa

| Thời điểm/sự kiện | Trách nhiệm và hành động | Tạo tác/cam kết được sử dụng | Điều được kiểm tra hoặc thích nghi |
| --- | --- | --- | --- |
| **Trước Sprint** | Product Owner làm rõ và sắp thứ tự hạng mục cùng Developers và các bên liên quan | Product Backlog / Product Goal | Giá trị nào đáng làm trước, câu hỏi nào còn thiếu |
| **Sprint Planning** | Scrum Team chọn Sprint Goal; Developers chọn item khả thi và lập kế hoạch | Sprint Backlog / Sprint Goal; DoD làm chuẩn chất lượng | Vì sao Sprint có giá trị, làm gì và làm thế nào |
| **Trong Sprint** | Developers phát triển, tích hợp, kiểm thử; trao đổi với Product Owner khi phát hiện quy tắc mới | Sprint Backlog; Increment / DoD | Các giả định kỹ thuật và nghiệp vụ có đúng không |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal, điều chỉnh kế hoạch | Sprint Backlog / Sprint Goal | Trở ngại, việc cần phối hợp và thay đổi kế hoạch ngày tới |
| **Khi một lát cắt đạt DoD** | Developers xác minh Increment tích hợp được và có thể dùng theo phạm vi | Increment / DoD | Sản phẩm thực tế có đạt tiêu chuẩn chất lượng không |
| **Sprint Review** | Scrum Team và các bên liên quan xem kết quả, phản hồi và bối cảnh | Increment / DoD; Product Backlog / Product Goal | Nên đổi gì trong hướng sản phẩm và backlog |
| **Sprint Retrospective** | Scrum Team tìm cải tiến về hợp tác, kỹ thuật và chất lượng | Hiệu quả làm việc, quy trình, DoD khi phù hợp | Làm cách nào giao giá trị tốt hơn Sprint tiếp theo |

### Tình huống phát sinh giữa Sprint

Trong ngày thứ tư, tester phát hiện yêu cầu lưu tiến độ có thể bị ghi lặp nếu kết nối chập chờn.

1. **Minh bạch:** Developers ghi lỗi, phạm vi ảnh hưởng, điều kiện tái hiện và tình trạng kiểm thử trên Sprint Backlog hoặc công cụ chung.
2. **Kiểm tra:** Trong trao đổi kỹ thuật và Daily Scrum, Developers đánh giá lỗi ảnh hưởng Sprint Goal và DoD ra sao.
3. **Thích nghi:** Developers đổi cách thực hiện, bổ sung kiểm thử; Product Owner tham gia nếu cần điều chỉnh phạm vi hoặc thứ tự công việc.
4. **Vai trò Scrum Master:** Hỗ trợ đội xử lý trở ngại phối hợp với hệ thống/đội khác nếu có, không quyết định thay Developers về giải pháp kỹ thuật.
5. **Kết quả:** Chỉ khi hành vi đúng, qua kiểm tra và đáp ứng DoD, phần tính năng mới tạo Increment hoàn thành.

Ở Sprint Review, người dùng có thể đề xuất tiếp tục đúng vị trí video. Product Owner xem bằng chứng và điều chỉnh Product Backlog. Trong Sprint Retrospective, nhóm có thể chọn thói quen kiểm tra tình huống gửi lại request sớm hơn ở các story xử lý dữ liệu.

**Vòng lặp hình thành:** mục tiêu dẫn dắt công việc → Increment cho bằng chứng → review điều chỉnh sản phẩm → retrospective điều chỉnh năng lực làm việc.

## 14. Ma trận quyết định: gặp vấn đề thì nhìn vào đâu?

| Tình huống | Trách nhiệm nổi bật | Sự kiện hoặc tương tác thích hợp | Tạo tác/cam kết cần xem |
| --- | --- | --- | --- |
| Một bên liên quan muốn thêm tính năng ngoài mục tiêu | Product Owner quản lý thứ tự backlog | Trao đổi trực tiếp; Sprint Review khi phù hợp | Product Backlog / Product Goal |
| Nhóm không rõ vì sao các item được chọn cùng Sprint | Scrum Team làm rõ mục tiêu; Developers lập kế hoạch | Sprint Planning hoặc trao đổi bổ sung ngay | Sprint Backlog / Sprint Goal |
| Việc đang làm bị chặn vì API | Developers chủ động gỡ; Scrum Master hỗ trợ hiệu quả phối hợp | Daily Scrum và trao đổi ngay với người liên quan | Sprint Backlog / Sprint Goal |
| Một story demo được nhưng có lỗi phân quyền | Developers tuân thủ DoD | Kiểm tra/test ngay, không đợi Review | Increment / Definition of Done |
| Người dùng không thấy tính năng mới hữu ích | Product Owner xem lại giá trị; Scrum Team cùng các bên liên quan học hỏi | Sprint Review và nghiên cứu người dùng | Increment; Product Backlog / Product Goal |
| Daily Scrum kéo dài thành cuộc họp báo cáo | Scrum Master giúp đội hiểu Scrum; Developers đổi cách sử dụng | Sprint Retrospective hoặc trao đổi cải tiến sớm | Sprint Goal, Sprint Backlog, hiệu quả phối hợp |
| Nhiều item đều mang nhãn “Done” nhưng chưa tích hợp | Developers chịu trách nhiệm chất lượng; Scrum Team thống nhất DoD | Kiểm tra thực trạng, cải tiến ở Retrospective | Increment / Definition of Done |
| Đội đổi việc liên tục theo ý tưởng mới | Product Owner làm rõ ưu tiên; Developers bảo vệ tập trung; Scrum Master hỗ trợ | Refinement, Sprint Planning, Review; tương tác khi cần | Product Goal, Sprint Goal, hai backlog |

**Lưu ý:** Không cần đợi một sự kiện chính thức để phản ứng với lỗi bảo mật hay sự cố sản xuất. Các sự kiện Scrum bổ sung nhịp kiểm tra, chứ không giới hạn quyền trao đổi, học hỏi hoặc hành động có trách nhiệm vào một khung giờ duy nhất.

## 15. Những hiểu nhầm thường gặp về mối liên hệ các thành phần

| Hiểu nhầm | Vì sao sai hoặc thiếu | Cách hiểu phù hợp |
| --- | --- | --- |
| **“Scrum Master là quản lý dự án, phân công việc và báo cáo tiến độ.”** | Scrum Master chịu trách nhiệm thiết lập Scrum và hiệu quả đội, không thay Developers tự quản | Hỗ trợ cải tiến, coaching và tháo trở ngại; đội tự tổ chức cách thực hiện. |
| **“Product Owner một mình quyết định Sprint Backlog.”** | Developers chịu trách nhiệm tạo kế hoạch Sprint; Sprint Planning là hoạt động hợp tác | Product Owner tối đa hóa giá trị và quản lý Product Backlog, Developers chọn lượng việc khả thi và cách làm. |
| **“Daily Scrum là báo cáo từng người cho Scrum Master.”** | Trái mục đích kiểm tra tiến độ hướng Sprint Goal | Developers dùng 15 phút để điều chỉnh kế hoạch và phối hợp. |
| **“Sprint Review là buổi phê duyệt mới được deploy.”** | Review không phải cổng bắt buộc để phát hành | Increment có thể được giao trước Review nếu đủ điều kiện; Review là lúc cùng kiểm tra và thích nghi. |
| **“Retrospective chỉ để chia sẻ cảm xúc.”** | Không đủ nếu không tìm cơ hội tăng hiệu quả và chất lượng | Xem hệ thống làm việc và chọn cải tiến thực tế có thể theo dõi. |
| **“Product Backlog phải viết chi tiết hết từ ngày đầu.”** | Backlog là danh sách phát triển liên tục; hạng mục xa chưa chắc được chọn | Làm rõ theo mức cần quyết định và rủi ro. |
| **“Sprint Backlog là hợp đồng bất biến.”** | Kế hoạch của Developers được điều chỉnh khi học thêm | Giữ Sprint Goal, trao đổi với Product Owner nếu cần thương lượng phạm vi. |
| **“Sprint Goal là tổng tên các ticket.”** | Không tạo mục tiêu chung để lựa chọn khi có thay đổi | Viết mục tiêu có ý nghĩa, phản ánh giá trị cần đạt trong Sprint. |
| **“Xong code hoặc demo được nghĩa là Increment Done.”** | Increment phải đáp ứng DoD và làm việc cùng các Increment trước | Minh bạch phần đã đạt chuẩn, phần còn thiếu và rủi ro. |
| **“Acceptance Criteria chính là DoD.”** | AC riêng cho story, DoD là tiêu chuẩn chất lượng chung của Increment | Sử dụng cả hai, tránh bỏ sót chất lượng hoặc lặp hình thức. |
| **“Mỗi Sprint phải release đúng một lần ở Review.”** | Scrum cho phép nhiều Increment trong Sprint và giao trước Review | Phân biệt tạo Increment, giao Increment và thời điểm Review. |
| **“Refinement là sự kiện Scrum thứ sáu.”** | Refinement là hoạt động liên tục, không phải sự kiện chính thức | Chọn thời điểm/cách làm để hạng mục cần thiết đủ rõ. |
| **“Thành công nghĩa là velocity tăng qua từng Sprint.”** | Velocity không tự đo giá trị hay chất lượng và có thể bị tối ưu hình thức | Xem Increment đáp ứng DoD, outcome, chất lượng và khả năng thích nghi. |

## 16. Bài tập vận dụng

### Bài tập 1 — Ghép tạo tác và cam kết

Hãy ghép mỗi mục bên trái với cam kết phù hợp:

| Tạo tác | Các cam kết để chọn |
| --- | --- |
| A. Product Backlog | 1. Definition of Done |
| B. Sprint Backlog | 2. Product Goal |
| C. Increment | 3. Sprint Goal |

**Đáp án:** A–2, B–3, C–1. Giải thích thêm **vì sao** từng cam kết cần cho việc kiểm tra tạo tác tương ứng.

### Bài tập 2 — Ai có trách nhiệm giải trình?

Cho những phát biểu:

1. “Cần xếp lại thứ tự Product Backlog sau phản hồi khách hàng.”
2. “Phải xác định cách kiểm thử và tích hợp để đáp ứng DoD.”
3. “Daily Scrum đang trở thành buổi báo cáo cho quản lý.”
4. “Cần chọn Sprint Goal dựa trên giá trị và năng lực thực tế.”

**Yêu cầu:** Xác định trách nhiệm giải trình nổi bật và những người cần cộng tác; không trả lời bằng cách gán mọi việc cho một người.

**Gợi ý:** (1) Product Owner; (2) Developers; (3) Scrum Master hỗ trợ Developers và Scrum Team cải tiến; (4) toàn Scrum Team phối hợp, Developers tạo Sprint Backlog.

### Bài tập 3 — Lựa chọn sự kiện cho từng câu hỏi

Một đội có các nhu cầu:

- Xem Increment và phản hồi người dùng để điều chỉnh backlog.
- Kiểm tra vì sao nhiều lỗi tích hợp xuất hiện muộn và chọn hành động cải tiến.
- Xây Sprint Goal, chọn item và lập kế hoạch thực hiện.
- Kiểm tra tiến độ hôm nay hướng Sprint Goal và gỡ chặn.

**Yêu cầu:** Ghép với Sprint Review, Sprint Retrospective, Sprint Planning và Daily Scrum. Giải thích loại thông tin cần minh bạch tại mỗi sự kiện và **quyết định gì** có thể được đưa ra.

### Bài tập 4 — Một item có thật sự Done?

Story: “Học viên mở lại bài gần nhất trên trang chủ.” Developer đã hoàn tất giao diện và demo thành công, nhưng:

- Trường hợp tài khoản A hết quyền truy cập khóa học chưa được kiểm thử.
- API đôi khi trả dữ liệu của tài khoản B khi session hết hạn.
- CI đang thất bại ở một số test tích hợp quan trọng.

**Yêu cầu:** Xác định trạng thái theo DoD; nêu việc Developers cần làm, thông tin Product Owner cần biết và cách Scrum Master có thể hỗ trợ nếu có trở ngại hệ thống. Có nên trình bày như Increment hoàn thành ở Sprint Review không?

**Gợi ý:** Không nên coi item đạt DoD khi vấn đề phân quyền hoặc test quan trọng chưa được giải quyết. Có thể trao đổi về phần nguyên mẫu để học nếu minh bạch trạng thái, nhưng không đổi nhãn thành Done cho đẹp báo cáo.

### Bài tập 5 — Mô phỏng một Sprint

Chia vai Product Owner, Scrum Master, Developers và hai người đóng vai bên liên quan. Dùng Product Goal:

> “Giúp học viên tiếp tục bài học thuận tiện và đáng tin cậy.”

Trong 30 phút:

1. **5 phút:** Product Owner mô tả mục tiêu, backlog và thứ tự ưu tiên.
2. **7 phút:** Scrum Team xác định một Sprint Goal; Developers chọn các item và phác thảo Sprint Backlog.
3. **5 phút:** Mô phỏng Daily Scrum sau khi có lỗi API mới; chỉ rõ kế hoạch điều chỉnh.
4. **6 phút:** Mô phỏng Sprint Review bằng kết quả đã đạt và phản hồi người dùng; Product Owner cập nhật thứ tự backlog.
5. **5 phút:** Mô phỏng Retrospective, chọn một cải tiến kỹ thuật hoặc phối hợp.
6. **2 phút:** Kiểm tra từng item được gọi là Done có đáp ứng DoD hay chưa.

**Tiêu chí đánh giá:** Có Product Goal và Sprint Goal phân biệt được; Sprint Backlog do Developers lập; phản hồi dẫn đến quyết định; trạng thái Increment không bị phóng đại; người tham gia hiểu đúng trách nhiệm.

### Bài tập 6 — Tìm điểm đứt trong vòng thực nghiệm

Một đội tổ chức đủ năm sự kiện, nhưng mỗi Sprint có những biểu hiện:

- Product Owner chỉ nhận ưu tiên từ một cấp quản lý và không giải thích Product Goal.
- Developers nhận công việc đã phân sẵn, không tham gia lập kế hoạch.
- Sprint Review chỉ có slide phần trăm hoàn thành.
- Những lỗi quan trọng không xuất hiện trong báo cáo vì “chưa đến lúc”.
- Retrospective không tạo ra thay đổi nào.

**Yêu cầu:** Chỉ ra ít nhất năm điểm mà **trách nhiệm, sự kiện, tạo tác hoặc cam kết** không còn liên kết. Đề xuất một hành động khả thi cho mỗi điểm và chỉ số/tín hiệu có thể kiểm chứng sau hai Sprint.

**Gợi ý:** Không giải quyết bằng cách tạo thêm cuộc họp. Cần khôi phục quyền tự quản, minh bạch DoD và Sprint Goal, quan sát Increment thật và biến thông tin mới thành quyết định backlog/cải tiến.

## 17. Checklist vận hành Scrum như một hệ thống

Trước hoặc sau một Sprint, Scrum Team có thể tự hỏi:

- [ ] Có **một Product Goal** đang định hướng các quyết định về sản phẩm?
- [ ] Product Backlog được sắp thứ tự và đủ minh bạch để giải thích giá trị, rủi ro, phụ thuộc?
- [ ] Product Owner thực sự có quyền và trách nhiệm đối với thứ tự Product Backlog?
- [ ] Developers đủ quyền và kỹ năng để lập kế hoạch, điều chỉnh công việc, tạo Increment đạt chất lượng?
- [ ] Scrum Master đang giúp Scrum được hiểu và thực hiện hiệu quả, không biến thành người chia ticket?
- [ ] Sprint Planning tạo **Sprint Goal, item được chọn và kế hoạch** chứ không chỉ danh sách việc?
- [ ] Daily Scrum giúp Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh kế hoạch?
- [ ] Increment được xác minh và đáp ứng **Definition of Done** trước khi gọi là hoàn thành?
- [ ] Sprint Review xem kết quả thực, phản hồi, bối cảnh mới và tác động lên Product Backlog?
- [ ] Sprint Retrospective tạo cơ hội cải tiến chất lượng và hiệu quả được theo dõi?
- [ ] Mọi người có phân biệt **Product Goal, Sprint Goal và Definition of Done**?
- [ ] Việc phát hành không bị hiểu nhầm là chỉ được phép sau Sprint Review?
- [ ] Các rủi ro về bảo mật, quyền riêng tư, dữ liệu và nghĩa vụ bắt buộc vẫn được xử lý?
- [ ] Khi có thông tin mới, có người có quyền quyết định và hành động thích nghi kịp thời?

Không dùng checklist này để tự gắn “điểm Scrum” rồi so sánh các đội. Nó là công cụ tìm **mối liên hệ đang thiếu** giữa minh bạch, kiểm tra và thích nghi.

## 18. Ghi nhớ

- **Ba trách nhiệm giải trình:** Product Owner tối đa hóa giá trị sản phẩm và quản lý Product Backlog; Developers lập kế hoạch, tạo Increment đạt DoD và điều chỉnh hướng Sprint Goal; Scrum Master giúp thiết lập Scrum và cải thiện hiệu quả Scrum Team.
- **Năm sự kiện:** Sprint bao chứa Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective; mỗi sự kiện tạo cơ hội kiểm tra và thích nghi với mục đích riêng.
- **Ba cặp tạo tác–cam kết:** **Product Backlog → Product Goal**, **Sprint Backlog → Sprint Goal**, **Increment → Definition of Done**.
- **Sprint Goal tạo sự tập trung:** Kế hoạch chi tiết có thể thay đổi khi học thêm, nhưng không làm nguy hiểm mục tiêu Sprint hoặc hạ chất lượng.
- **Increment là bằng chứng tiến độ thực chất:** Code chạy demo chưa đủ; phần hoàn thành phải đạt DoD và làm việc với phần sản phẩm đã có.
- **Review và Retrospective bổ sung nhau:** Một bên kiểm tra kết quả và hướng sản phẩm; bên còn lại cải tiến cách đội tạo giá trị.
- **Tính thực nghiệm là sợi dây kết nối:** Tạo tác minh bạch giúp kiểm tra chính xác, người có trách nhiệm dùng kết quả đó để thích nghi, các sự kiện cung cấp nhịp phối hợp thường xuyên.

Khi một Scrum Team “đã làm đủ Scrum” nhưng chưa tạo ra giá trị, câu hỏi nên đặt không phải “Đã tổ chức đủ cuộc họp chưa?”, mà là: **“Mục tiêu, kế hoạch, chất lượng và kết quả có được nhìn thấy nhất quán — và những người có trách nhiệm có thể dùng thông tin ấy để quyết định tốt hơn không?”**
