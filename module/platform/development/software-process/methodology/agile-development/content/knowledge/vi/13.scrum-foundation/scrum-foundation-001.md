# Scrum là khung làm việc hỗ trợ giải quyết vấn đề phức tạp

## 1. Scrum là gì?

**Scrum** là một **khung làm việc nhẹ (lightweight framework)** giúp con người, nhóm và tổ chức tạo giá trị thông qua những giải pháp **thích ứng** cho các vấn đề phức tạp. Theo Scrum Guide 2020, Scrum cung cấp một cấu trúc tối thiểu gồm **Scrum Team, các sự kiện, các artifact và những cam kết đi kèm**. Trong cấu trúc đó, nhóm liên tục xây dựng sản phẩm, kiểm tra bằng chứng thực tế và điều chỉnh cách làm.

Điểm quan trọng của định nghĩa:

- **Khung làm việc, không phải một quy trình chi tiết cho mọi công việc.** Scrum xác lập những trách nhiệm và cơ hội kiểm tra–thích ứng thiết yếu, nhưng không chỉ định ngôn ngữ lập trình, kiến trúc, kỹ thuật kiểm thử hay cách viết mọi user story.
- **Tạo giá trị, không chỉ hoàn thành tác vụ.** Thành công không được chứng minh chỉ bằng số ticket, giờ làm, story point hoặc số cuộc họp.
- **Thích ứng, không dự đoán chính xác tất cả từ đầu.** Khi nhu cầu và giải pháp chưa chắc chắn, nhóm học từ những phần sản phẩm có thể sử dụng được.
- **Giải quyết vấn đề phức tạp.** Nhiều yếu tố liên quan nhau, phản ứng của người dùng khó dự đoán và một quyết định có thể bộc lộ hậu quả chỉ sau khi thử trong môi trường phù hợp.
- **Trách nhiệm rõ, tự quản lý trong nhóm.** Scrum không có nghĩa là mọi thành viên làm tùy ý hoặc không cần phối hợp với các bên liên quan.

Ví dụ, một nhóm đang tạo chức năng tự đăng ký khóa học trên nền tảng học trực tuyến. Nhóm có thể viết bản đặc tả dài về mọi khả năng, nhưng chưa biết học viên có hiểu quy trình đăng ký hay không; đồng thời, các quy tắc về chỗ trống và tính đồng thời có thể phức tạp hơn dự kiến. Scrum giúp nhóm chọn một mục tiêu gần, xây phần hành vi có thể kiểm chứng, nhận phản hồi và điều chỉnh Product Backlog.

Trong module **AGILE_DEVELOPMENT**, Scrum là một lựa chọn tổ chức công việc phù hợp với những nguyên tắc Agile: nhận phản hồi sớm, giao phần tăng trưởng có giá trị, cộng tác và cải tiến liên tục. **Agile rộng hơn Scrum**; một nhóm có thể vận dụng tư duy Agile bằng phương pháp khác, và một nhóm tổ chức đầy đủ sự kiện Scrum vẫn có thể làm việc kém thích ứng nếu không thực sự kiểm tra và học từ kết quả.

## 2. Vì sao Scrum phù hợp với vấn đề phức tạp?

### 2.1. Phân biệt việc có thể dự báo với công việc có nhiều bất định

Một vấn đề đơn giản hoặc quen thuộc thường có các bước thực hiện đã được kiểm chứng. Ví dụ, cập nhật một thông tin đã được xác nhận trên trang web theo quy trình ổn định có thể không cần một vòng khám phá lớn.

Trong bài toán phức tạp, nhiều câu hỏi chỉ có thể được trả lời đáng tin cậy thông qua **quan sát, thử nghiệm và phản hồi**:

| Nguồn bất định | Câu hỏi minh họa | Bằng chứng có thể thu thập |
| --- | --- | --- |
| **Nhu cầu người dùng** | Học viên có thực sự muốn tự đăng ký không? | Phỏng vấn, quan sát thử tác vụ, dữ liệu sử dụng. |
| **Hành vi nghiệp vụ** | Khi chỉ còn một chỗ, hai yêu cầu đồng thời xử lý thế nào? | Ví dụ được xác nhận, kiểm thử cạnh tranh, kiểm tra dữ liệu. |
| **Giải pháp kỹ thuật** | API hiện tại có chịu tải và trả lỗi nhất quán không? | Spike, kiểm thử tích hợp và đo hiệu năng. |
| **Phụ thuộc** | Hệ thống quản lý lớp học có đủ thông tin xác nhận không? | Hợp đồng API, thử tích hợp, trao đổi với chủ sở hữu. |
| **Thị trường và bối cảnh** | Ưu tiên có thay đổi khi bước vào mùa tuyển sinh không? | Kết quả sản phẩm, phản hồi stakeholder, dữ liệu hiện trạng. |

Một kế hoạch cố định quá sớm có thể làm nhóm tối ưu một giả định đã sai. Ngược lại, không có mục tiêu và tiêu chuẩn nào sẽ khiến thử nghiệm tản mạn. Scrum tạo một **nhịp có cấu trúc để vừa tập trung vừa thích ứng**.

### 2.2. Kiểm soát bằng kinh nghiệm thực tế (empiricism)

Scrum dựa trên **empiricism**: hiểu biết đến từ kinh nghiệm và quyết định dựa trên điều đã quan sát. Empiricism được hỗ trợ bằng ba trụ cột:

| Trụ cột | Ý nghĩa | Trong phát triển phần mềm |
| --- | --- | --- |
| **Transparency — Minh bạch** | Người ra quyết định nhìn thấy tình trạng công việc và chất lượng thực tế. | Backlog, Sprint Goal, tiến độ, trở ngại, trạng thái Done và rủi ro được công khai. |
| **Inspection — Kiểm tra** | Thường xuyên xem sản phẩm, cách làm và tiến độ hướng tới mục tiêu. | Xem Increment hoạt động, kiểm thử, Sprint Review, Daily Scrum. |
| **Adaptation — Thích ứng** | Điều chỉnh khi phát hiện sai lệch hoặc cơ hội tốt hơn. | Cập nhật Sprint Backlog, sắp thứ tự Product Backlog, cải thiện quy trình. |

Ba trụ cột không hoạt động tách biệt. Nếu trạng thái Done bị báo sai, việc kiểm tra khó đưa ra kết luận đúng; nếu nhóm nhìn thấy vấn đề nhưng không được điều chỉnh kế hoạch, kiểm tra sẽ biến thành nghi thức.

Scrum cũng dựa trên **lean thinking**: chú ý vào điều thiết yếu và giảm lãng phí. Thí dụ, tích hợp sớm và làm rõ yêu cầu cần thiết có thể giảm việc làm lại, trong khi mở quá nhiều tính năng chưa hoàn tất làm tăng công việc dở dang và thời gian chờ.

~~~mermaid
flowchart LR
    A["Minh bạch mục tiêu, backlog và chất lượng"] --> B["Xây Increment nhỏ"]
    B --> C["Kiểm tra kết quả và phản hồi"]
    C --> D["Thích ứng sản phẩm và cách làm"]
    D --> A
~~~

### 2.3. Scrum không xóa bỏ việc lập kế hoạch

Một nhóm Scrum vẫn có mục tiêu sản phẩm, dự báo khả năng thực hiện, lập kế hoạch cho Sprint, làm rõ Product Backlog và thảo luận phụ thuộc. Điểm khác là kế hoạch được coi là **cơ sở để hành động và học hỏi**, không phải lời tiên tri bất biến.

Ví dụ, Sprint dự kiến giao luồng đăng ký. Khi kiểm thử phát hiện xử lý chỗ cuối phức tạp, Developers cùng Product Owner có thể xem lại phạm vi các khả năng phụ, thay đổi kế hoạch kỹ thuật và bảo vệ Sprint Goal. **Không được hạ chất lượng hoặc gọi công việc chưa đáp ứng Definition of Done là hoàn tất**.

## 3. Nền tảng hành vi: năm giá trị Scrum

Scrum nêu năm giá trị: **Commitment, Focus, Openness, Respect, Courage**.

| Giá trị | Ý nghĩa trong nhóm | Ví dụ hành vi quan sát được |
| --- | --- | --- |
| **Commitment — Cam kết** | Cùng nghiêm túc hướng tới mục tiêu và hỗ trợ nhau. | Cùng chịu trách nhiệm tạo Increment đáp ứng chuẩn chất lượng, không “xong phần tôi là đủ”. |
| **Focus — Tập trung** | Dồn sự chú ý vào công việc và mục tiêu Sprint. | Hạn chế mở thêm việc không liên quan; ưu tiên tháo gỡ hạng mục gần Done. |
| **Openness — Cởi mở** | Minh bạch về công việc, trở ngại và thách thức. | Báo sớm khi kiểm thử thất bại hoặc một giả định chưa được xác nhận. |
| **Respect — Tôn trọng** | Tôn trọng năng lực, đóng góp và trách nhiệm của nhau. | QA, kỹ sư, Product Owner và chuyên gia vận hành cùng được lắng nghe. |
| **Courage — Can đảm** | Dám làm điều đúng và giải quyết vấn đề khó. | Nêu rủi ro bảo mật dù điều đó ảnh hưởng kế hoạch phát hành. |

Năm giá trị này hỗ trợ các trụ cột Scrum. Chẳng hạn, muốn minh bạch cần sự cởi mở và can đảm; muốn thích ứng cần cam kết với mục tiêu thay vì giữ nguyên mọi tác vụ chỉ để bảo vệ kế hoạch cũ.

**Scrum không chỉ là lịch họp.** Nếu nhóm không dám nói rằng Increment chưa đạt DoD, hoặc Product Owner không thể thay đổi ưu tiên theo bằng chứng, việc tuân thủ lịch sự kiện sẽ không tạo ra lợi ích của Scrum.

## 4. Scrum Team: một đơn vị tạo giá trị, không phải các phòng ban chuyển việc

Trong Scrum Guide 2020, **Scrum Team** gồm **một Scrum Master, một Product Owner và các Developers**. Scrum Team là **liên chức năng (cross-functional)** và **tự quản lý (self-managing)**. Nhóm đủ nhỏ để linh hoạt và đủ năng lực để hoàn tất công việc quan trọng trong một Sprint; thông thường có **10 người hoặc ít hơn**.

Scrum Team không có các nhóm con hoặc cấp bậc nội bộ được định nghĩa bởi Scrum. Đây là một đơn vị tập trung vào một mục tiêu sản phẩm và cùng chịu trách nhiệm đối với các hoạt động liên quan sản phẩm, từ hợp tác với stakeholder đến xác minh, vận hành hoặc bảo trì khi thích hợp.

### 4.1. Product Owner: tối đa hóa giá trị sản phẩm

**Product Owner (PO)** chịu trách nhiệm tối đa hóa giá trị sản phẩm từ công việc của Scrum Team. PO cũng chịu trách nhiệm quản lý Product Backlog hiệu quả, bao gồm:

- Phát triển và truyền đạt rõ **Product Goal**.
- Tạo và truyền đạt các Product Backlog Items phù hợp.
- **Sắp xếp thứ tự Product Backlog** theo mục tiêu và giá trị.
- Bảo đảm Product Backlog minh bạch, dễ hiểu.

PO có thể ủy quyền người khác thực hiện các hoạt động quản lý backlog, nhưng vẫn **chịu trách nhiệm cuối cùng**. Product Owner là **một người, không phải một hội đồng**; các stakeholder có thể thuyết phục bằng dữ liệu và mục tiêu nhưng không nên tự ý gửi cam kết trái ngược cho Developers.

**Trong ví dụ đăng ký khóa học:** PO cùng người dùng làm rõ giá trị của tự đăng ký, thứ tự ưu tiên giữa đăng ký cơ bản và SMS nhắc học, cũng như các quy tắc nghiệp vụ cần được xác nhận.

### 4.2. Developers: tạo Increment dùng được

**Developers** là những người trong Scrum Team cam kết tạo ra phần sản phẩm dùng được trong mỗi Sprint. Đây là một **trách nhiệm Scrum**, không đồng nghĩa chỉ với chức danh lập trình viên. Thành viên đóng góp kỹ năng kiểm thử, thiết kế, dữ liệu, hạ tầng hay các chuyên môn khác để tạo Increment có thể thuộc nhóm Developers tùy cách nhóm tổ chức.

Các Developers chịu trách nhiệm:

1. Tạo kế hoạch cho Sprint — **Sprint Backlog**.
2. Duy trì chất lượng bằng cách tuân thủ **Definition of Done**.
3. Điều chỉnh kế hoạch hằng ngày để tiến tới **Sprint Goal**.
4. Giữ trách nhiệm nghề nghiệp với nhau trong Scrum Team.

Trong tình huống đặt lịch, Developers quyết định cách thực hiện kiểm soát đồng thời, phân chia việc và kiểm tra tích hợp; họ không tự đặt chính sách sản phẩm nếu việc đó thuộc trách nhiệm của PO hoặc chuyên gia nghiệp vụ.

### 4.3. Scrum Master: hỗ trợ Scrum Team và tổ chức

**Scrum Master (SM)** chịu trách nhiệm về việc thiết lập Scrum theo Scrum Guide và về **hiệu quả của Scrum Team**. Scrum Master là một người lãnh đạo phục vụ (true leader who serves), giúp Scrum Team, Product Owner và tổ chức hiểu, áp dụng Scrum và cải thiện cách làm việc.

Ví dụ hành động:

- Hỗ trợ nhóm tự quản lý và tăng năng lực liên chức năng.
- Giúp tạo Increment có giá trị, đáp ứng Definition of Done.
- **Thúc đẩy việc tháo gỡ trở ngại** ảnh hưởng tiến độ.
- Bảo đảm các sự kiện Scrum diễn ra hiệu quả, trong timebox phù hợp.
- Giúp PO quản lý Product Backlog và thiết lập mục tiêu sản phẩm hiệu quả.
- Hỗ trợ tổ chức cải thiện tương tác với Scrum Team và áp dụng Scrum phù hợp.

Scrum Master **không phải mặc định là quản lý nhân sự**, người giao task cho từng Developer hay người duy nhất có nghĩa vụ sửa mọi impediment. Developers chủ động xử lý điều nằm trong quyền hạn; SM hỗ trợ và kết nối người có thẩm quyền khi vướng mắc ở cấp hệ thống.

### 4.4. Ba trách nhiệm phối hợp thế nào?

| Câu hỏi | Trách nhiệm dẫn dắt | Cách cộng tác |
| --- | --- | --- |
| Sản phẩm cần hướng tới giá trị gì? | Product Owner | Trao đổi với stakeholder và Developers, dùng bằng chứng sản phẩm. |
| Hạng mục nào được sắp thứ tự trên Product Backlog? | Product Owner | Developers cung cấp kích thước, rủi ro và phụ thuộc. |
| Trong Sprint, sẽ triển khai kỹ thuật và phân chia công việc ra sao? | Developers | Trao đổi với PO về phạm vi và với SM về trở ngại. |
| Increment có đạt chuẩn hoàn tất không? | Scrum Team sử dụng DoD; Developers chịu trách nhiệm tuân thủ khi tạo Increment. | Cùng minh bạch bằng chứng kiểm thử, tích hợp và chất lượng. |
| Cách vận hành Scrum có hiệu quả không? | Scrum Master chịu trách nhiệm về hiệu quả Scrum Team. | Cả nhóm cùng cải tiến, tổ chức hỗ trợ tháo gỡ trở ngại. |

Tránh biến bảng trách nhiệm thành ba bộ phận làm việc riêng lẻ. **Scrum Team chỉ có ý nghĩa khi cùng theo một Product Goal, cùng kiểm tra kết quả và cộng tác liên tục**.

## 5. Năm sự kiện Scrum tạo nhịp kiểm tra và thích ứng

Scrum có **năm sự kiện chính thức**: **Sprint**, **Sprint Planning**, **Daily Scrum**, **Sprint Review** và **Sprint Retrospective**. Sprint là **vật chứa (container)** cho các sự kiện còn lại và cho công việc tạo ra Increment.

Các sự kiện tạo những cơ hội thường xuyên để kiểm tra và thích ứng; chúng được **timebox** để giữ mục đích rõ và tránh lãng phí. Các buổi trao đổi cần thiết khác vẫn có thể diễn ra ngoài sự kiện chính thức.

### 5.1. Sprint: một nhịp tạo giá trị nhất quán

**Sprint** là một khoảng thời gian cố định **không quá một tháng**. Một Sprint mới bắt đầu ngay sau khi Sprint trước kết thúc. Trong Sprint, mọi công việc cần thiết để đạt Product Goal — bao gồm xây dựng, tích hợp, kiểm thử, trao đổi và kiểm tra kết quả — có thể diễn ra.

Trong Sprint:

- Không thực hiện những thay đổi làm nguy hại **Sprint Goal**.
- **Chất lượng không được giảm**.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi có thêm hiểu biết.

Sprint ngắn giúp rủi ro và chi phí giữ hướng sai không kéo dài quá lâu. Nhưng thời gian ngắn không tự tạo giá trị; nhóm vẫn phải có **Increment hoàn tất theo DoD** và đủ năng lực kiểm chứng.

Nếu **Sprint Goal trở nên lỗi thời**, Sprint có thể bị hủy và **chỉ Product Owner có thẩm quyền hủy**. Đây là cơ chế đặc biệt, không phải cách kết thúc Sprint vì nhóm ước lượng sai một vài tác vụ.

### 5.2. Sprint Planning: tại sao, cái gì, bằng cách nào?

Sprint Planning là buổi tạo kế hoạch cho Sprint. Cả Scrum Team cùng tham gia, và khi cần có thể mời người khác để nhận tư vấn. Theo Scrum Guide 2020, sự kiện giải quyết ba chủ đề:

1. **Why is this Sprint valuable?** — Vì sao Sprint này có giá trị? Nhóm xác định **Sprint Goal**.
2. **What can be Done this Sprint?** — Có thể hoàn tất những Product Backlog Items nào? Developers lựa chọn qua trao đổi với Product Owner và xem xét năng lực.
3. **How will the chosen work get done?** — Developers lập kế hoạch để biến các hạng mục được chọn thành Increment đáp ứng DoD.

Kết quả là **Sprint Backlog**, gồm Sprint Goal, các Product Backlog Items được chọn và kế hoạch để giao Increment. Với Sprint một tháng, Sprint Planning được timebox **tối đa tám giờ**; Sprint ngắn hơn thường có sự kiện ngắn hơn.

Một Sprint Goal tốt nêu **một mục đích chung**, không chỉ sao chép danh sách task. Nếu Sprint Goal là “Học viên thử nghiệm tự đăng ký được khóa miễn phí còn chỗ”, nhóm có cơ sở thương lượng khi gặp yêu cầu thêm dashboard không phục vụ mục tiêu này.

### 5.3. Daily Scrum: kiểm tra tiến độ và điều chỉnh kế hoạch

**Daily Scrum** là sự kiện **15 phút dành cho Developers**, nhằm kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. Nó diễn ra mỗi ngày làm việc của Sprint, vào cùng thời điểm và địa điểm để giảm phức tạp.

Daily Scrum không bắt buộc phải đi theo ba câu hỏi “hôm qua làm gì, hôm nay làm gì, có blocker nào?”. Developers được chọn cấu trúc phù hợp, miễn tập trung vào tiến độ đối với Sprint Goal và có kế hoạch hành động cho công việc tiếp theo.

Ví dụ cách trao đổi hữu ích:

> “Luồng đăng ký đã tích hợp giao diện–API, nhưng kiểm thử hai người tranh chỗ cuối chưa qua. Để đạt Sprint Goal, hai người sẽ ghép cặp điều tra transaction; phần lọc nâng cao tạm chưa bắt đầu.”

Đó là cuộc thảo luận nhằm **điều chỉnh kế hoạch**, không phải báo cáo tình hình cho Scrum Master hoặc quản lý. Vấn đề chi tiết có thể được xử lý ngay sau Daily Scrum với những người liên quan.

### 5.4. Sprint Review: kiểm tra kết quả sản phẩm cùng stakeholder

**Sprint Review** nhằm kiểm tra **kết quả Sprint** và xác định cách thích ứng tiếp theo. Scrum Team trình bày những gì đã đạt được so với Product Goal, cùng stakeholder thảo luận tiến độ, bối cảnh thay đổi và các bước tiếp theo. Product Backlog có thể được điều chỉnh theo hiểu biết mới.

Đây là **buổi làm việc cộng tác**, không chỉ là màn demo một chiều hoặc cổng phê duyệt phát hành. Nhóm nên đưa Increment hoạt động được vào cuộc trao đổi; nếu chưa có đủ bằng chứng hoàn tất, phải nói rõ giới hạn.

Ví dụ, học viên dùng thử phát hiện thông báo “Đăng ký thành công” chưa làm họ hiểu thời điểm bắt đầu lớp. Nhóm có thể cập nhật backlog để làm rõ xác nhận trước khi ưu tiên SMS nhắc học.

Với Sprint một tháng, Sprint Review được timebox **tối đa bốn giờ**. Trong Sprint ngắn hơn, sự kiện thường ngắn hơn.

### 5.5. Sprint Retrospective: cải thiện chất lượng và hiệu quả

**Sprint Retrospective** giúp Scrum Team lập kế hoạch nâng cao **chất lượng và hiệu quả**. Nhóm nhìn lại con người, tương tác, quy trình, công cụ và Definition of Done, tìm nguyên nhân của điều đã thuận lợi hoặc gây khó khăn.

Ví dụ, nếu kiểm thử tích hợp luôn bị chặn cuối Sprint vì tài khoản sandbox, nhóm đề xuất:

- Phối hợp cấp quyền môi trường từ sớm và đúng chính sách.
- Thêm contract test vào CI.
- Làm rõ người chịu trách nhiệm khi hợp đồng API thay đổi.
- Chia lát cắt nhỏ hơn để tích hợp thường xuyên.

Sự kiện không kết thúc ở việc “nêu cảm nhận”. Nên chọn một hoặc vài cải tiến có thể hành động và xem xét tác dụng trong thời gian tiếp theo. Với Sprint một tháng, Retrospective được timebox **tối đa ba giờ**.

### 5.6. Tổng quan sự kiện

| Sự kiện | Đối tượng và mục đích | Timebox theo Scrum Guide 2020 |
| --- | --- | --- |
| **Sprint** | Vật chứa mọi sự kiện và công việc để tạo giá trị. | Độ dài cố định, tối đa 1 tháng. |
| **Sprint Planning** | Cả Scrum Team tạo Sprint Goal và lập kế hoạch. | Tối đa 8 giờ cho Sprint 1 tháng. |
| **Daily Scrum** | Developers kiểm tra tiến độ đến Sprint Goal, điều chỉnh kế hoạch. | 15 phút mỗi ngày làm việc của Sprint. |
| **Sprint Review** | Scrum Team và stakeholder xem kết quả, cộng tác về bước tiếp theo. | Tối đa 4 giờ cho Sprint 1 tháng. |
| **Sprint Retrospective** | Scrum Team cải thiện chất lượng và hiệu quả. | Tối đa 3 giờ cho Sprint 1 tháng. |

Các con số trên **không phải mục tiêu sử dụng hết thời gian**. Sprint ngắn hơn thường có các sự kiện ngắn hơn, tùy nhu cầu thực tế. Sự kiện hữu ích khi có sự minh bạch, kiểm tra đúng đối tượng và **dẫn đến điều chỉnh có căn cứ**.

## 6. Ba artifact Scrum và ba cam kết đi kèm

Các artifact làm thông tin quan trọng minh bạch để nhóm và stakeholder có cùng cơ sở kiểm tra. Theo Scrum Guide 2020, mỗi artifact có một **commitment** giúp tăng trọng tâm và khả năng đo tiến độ.

| Artifact | Nội dung | Commitment | Câu hỏi trọng tâm |
| --- | --- | --- | --- |
| **Product Backlog** | Danh sách nổi lên, được sắp xếp của những gì cần để cải thiện sản phẩm. | **Product Goal** | Sản phẩm đang hướng tới trạng thái tương lai nào? |
| **Sprint Backlog** | Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện. | **Sprint Goal** | Sprint này mang lại mục đích chung gì? |
| **Increment** | Phần tăng trưởng cụ thể, được tích hợp và có thể sử dụng. | **Definition of Done (DoD)** | Chất lượng nào phải đạt để được gọi là hoàn tất? |

### 6.1. Product Backlog và Product Goal

**Product Backlog** là một nguồn công việc cho Scrum Team. Backlog không bắt buộc gồm toàn bộ user story ở cùng mức chi tiết; có thể chứa tính năng, vấn đề chất lượng, rủi ro, cải tiến kỹ thuật và cơ hội khám phá, miễn phục vụ sản phẩm.

Backlog được **làm rõ liên tục (refinement)**: chia nhỏ và định nghĩa thêm các mục có khả năng thực hiện sớm. Backlog refinement **không phải một sự kiện Scrum chính thức được timebox riêng**; nhóm chọn cách làm phù hợp.

**Product Goal** mô tả trạng thái tương lai của sản phẩm mà Scrum Team hướng tới. Ví dụ:

> “Học viên đủ điều kiện có thể tự tìm, đăng ký và quản lý khóa học mà không phải phụ thuộc vào xử lý thủ công trong những trường hợp thông thường.”

Scrum Team tập trung vào một Product Goal tại một thời điểm; hoàn thành hoặc từ bỏ mục tiêu này trước khi nhận mục tiêu tiếp theo. Thứ tự Product Backlog được cập nhật để phản ánh giá trị và thông tin mới.

### 6.2. Sprint Backlog và Sprint Goal

**Sprint Backlog** thuộc quyền lập kế hoạch và cập nhật của Developers. Nó là kế hoạch **hiển thị theo thời gian thực**, được Developers điều chỉnh khi hiểu thêm, miễn hướng tới Sprint Goal.

Ví dụ Sprint Goal:

> “Đưa vào dùng thử luồng học viên tự đăng ký một khóa miễn phí còn chỗ với xác nhận đáng tin cậy.”

Các hạng mục được chọn có thể gồm: xem chỗ trống, xử lý đăng ký, lưu dữ liệu và thông báo kết quả. Trong Sprint, Developers có thể tách các hạng mục, thay đổi trình tự hoặc thiết kế kỹ thuật để đạt mục tiêu. **Sprint Backlog không phải danh sách đóng băng ngay sau Sprint Planning**.

### 6.3. Increment và Definition of Done

**Increment** là phần tăng thêm cụ thể tiến tới Product Goal, bổ sung cho các Increment trước và được xác minh đầy đủ để bảo đảm chúng hoạt động cùng nhau. Mỗi Increment phải **có thể sử dụng được** và **đáp ứng Definition of Done**.

Các điểm dễ nhầm:

- Một Sprint **có thể tạo nhiều Increment**, không bắt buộc chỉ có một.
- Một Increment **có thể được phát hành trước Sprint Review**; Sprint Review không phải cổng phát hành.
- **Chưa đáp ứng DoD thì chưa được tính là Increment**, dù mã đã viết xong hoặc demo trông có vẻ đúng.
- Một thử nghiệm giao diện dùng dữ liệu giả có thể rất hữu ích để học hỏi nhưng không tự động là Increment dùng được của sản phẩm.
- Khi tổ chức có tiêu chuẩn DoD, Scrum Team phải tuân thủ ở mức tối thiểu; nếu chưa có, Scrum Team tự tạo DoD phù hợp. Nhiều Scrum Team làm cùng một sản phẩm phải cùng định nghĩa và tuân thủ một DoD.

**DoD khác acceptance criteria.** Acceptance criteria làm rõ hành vi cần có của từng Product Backlog Item; DoD là chuẩn chất lượng chung xác định khi Increment đã hoàn tất. Nhóm không nên đánh tráo việc chưa kiểm thử bảo mật bằng cách xóa một tiêu chí chấp nhận.

### 6.4. Minh họa sự liên kết

~~~mermaid
flowchart TB
    PG["Product Goal"] --> PB["Product Backlog: cơ hội và việc cần cải thiện"]
    PB --> SP["Sprint Planning"]
    SP --> SG["Sprint Goal"]
    SP --> SB["Sprint Backlog: các mục chọn + kế hoạch"]
    SG --> WORK["Developers xây dựng và thích ứng"]
    SB --> WORK
    DOD["Definition of Done"] --> INC["Increment dùng được"]
    WORK --> INC
    INC --> REV["Sprint Review: kiểm tra giá trị và bối cảnh"]
    REV --> PB
    WORK --> RET["Retrospective: cải thiện cách làm"]
    RET --> WORK
~~~

Sơ đồ chỉ tóm tắt mối quan hệ; Daily Scrum và những tương tác thường xuyên diễn ra trong Sprint, không chỉ ở các mũi tên cố định.

## 7. Ví dụ xuyên suốt: một Scrum Team xây chức năng đăng ký khóa học

### 7.1. Bối cảnh vấn đề phức tạp

Một nền tảng học trực tuyến hiện cho học viên xem khóa học nhưng yêu cầu liên hệ nhân viên để đăng ký. Nhóm chưa chắc chắn:

- Học viên có hiểu các bước đăng ký trực tuyến không?
- Khi nhiều học viên chọn chỗ cuối, dữ liệu có nhất quán không?
- Hệ thống cũ cung cấp thông tin sức chứa theo thời gian thực hay theo lô?
- Những điều gì tạo giá trị cao nhất: đăng ký cơ bản, thanh toán, bộ lọc hay nhắc lịch?

Nếu nhóm chọn xây tất cả khả năng trước khi kiểm thử với người dùng, thời gian nhận phản hồi sẽ dài và rủi ro tích hợp tăng. Scrum tạo nhịp để **chọn một mục tiêu gần và giao phần nhỏ có thể kiểm chứng**.

### 7.2. Product Goal và Product Backlog ban đầu

**Product Goal minh họa:** “Học viên tự quản lý các bước đăng ký khóa học phổ biến trên nền tảng, giảm phụ thuộc vào nhân viên hỗ trợ”.

Product Owner và Scrum Team cùng làm rõ các mục ứng viên:

| Mục | Giá trị hoặc rủi ro | Thứ tự minh họa |
| --- | --- | --- |
| A — Học viên xem khóa còn chỗ | Cần để chọn đúng khóa học. | Cao |
| B — Học viên đăng ký và nhận kết quả | Hành vi tạo giá trị cốt lõi. | Cao |
| C — Chống đăng ký trùng và vượt sức chứa | Bắt buộc để dữ liệu đúng, đáng tin cậy. | Cao |
| D — Bộ lọc theo chủ đề nâng cao | Giúp khám phá khóa thuận tiện hơn. | Trung bình |
| E — Thanh toán khóa trả phí | Mở rộng một luồng khác, nhiều phụ thuộc. | Cần khám phá và sắp ưu tiên |
| F — SMS nhắc học | Có thể giảm quên lịch, chưa có bằng chứng nhu cầu. | Chờ kiểm chứng |

Thứ tự không phải chân lý cố định. Nó thay đổi nếu Product Owner nhận được bằng chứng về nhu cầu, chi phí trì hoãn hoặc rủi ro mới. Cũng không thể dùng “cao” để tự động bỏ qua các yêu cầu bắt buộc về bảo mật và quyền truy cập.

### 7.3. Sprint Planning: chọn một Sprint Goal

Giả sử Scrum Team sử dụng Sprint dài **hai tuần**. Sprint Goal:

> “Học viên thử nghiệm có thể tự đăng ký khóa học miễn phí còn chỗ và nhận xác nhận đáng tin cậy.”

Developers cân nhắc năng lực, phụ thuộc và DoD để chọn công việc phục vụ Sprint Goal. Một kế hoạch gần có thể là:

1. Làm rõ quy tắc nghiệp vụ và trường hợp biên với Product Owner.
2. Tạo lát cắt giao diện → API → dữ liệu có thể đăng ký thành công.
3. Bổ sung xử lý đăng ký lặp và tình huống đồng thời.
4. Tích hợp, kiểm tra quyền truy cập, thực hiện các kiểm thử cần thiết.
5. Đưa Increment cho một nhóm học viên đại diện kiểm chứng.

Những hoạt động đó có thể xen kẽ nhau, không cần biến thành một quy trình tuần tự cứng. **Lý do chọn công việc là Sprint Goal**, không phải cần bảo đảm mọi kỹ sư đều có thật nhiều task.

### 7.4. User story và tiêu chí chấp nhận

**User story:**

> Là một học viên đã đăng nhập, tôi muốn đăng ký một khóa học miễn phí còn chỗ để bắt đầu học mà không cần liên hệ nhân viên hỗ trợ.

Ví dụ hành vi bằng cú pháp gần Gherkin:

~~~gherkin
Feature: Học viên tự đăng ký khóa học miễn phí

  Scenario: Đăng ký hợp lệ khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa X
    And khóa X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A thấy thông báo thành công

  Scenario: Gửi yêu cầu đăng ký lặp lại
    Given A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký khóa X
    Then hệ thống không tạo thêm đăng ký hiệu lực thứ hai
    And A nhận được trạng thái đăng ký hiện tại

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa X chỉ còn một chỗ
    When hai học viên đủ điều kiện đồng thời yêu cầu đăng ký
    Then tối đa một yêu cầu mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa

  Scenario: Truy cập thông tin không có quyền
    Given người dùng B không có quyền xem đăng ký riêng của A
    When B yêu cầu xem đăng ký của A
    Then hệ thống từ chối truy cập
~~~

Ví dụ chỉ mô tả kỳ vọng; nó trở thành kiểm thử tự động khi được nối với mã kiểm thử và chạy trong hệ thống phù hợp. Những quy tắc kinh doanh cần được xác nhận với người có thẩm quyền, thay vì để Developers tự suy đoán.

### 7.5. Trong Sprint: học từ lỗi tích hợp

Khi tích hợp, nhóm thấy hai yêu cầu gần đồng thời có thể làm số đăng ký vượt sức chứa. Điều này **không phải khả năng tùy chọn để hoãn** nếu mục tiêu là đăng ký chính xác. Developers xem lại giải pháp giao dịch, bổ sung kiểm thử cạnh tranh, thảo luận với Product Owner về tác động và điều chỉnh kế hoạch nếu cần.

Trong Daily Scrum, nhóm nhận diện đây là rủi ro đối với Sprint Goal và tập trung hỗ trợ thay vì mở thêm tính năng lọc khóa học. Scrum Master có thể giúp nhóm kết nối chuyên gia cơ sở dữ liệu hoặc tháo gỡ trở ngại môi trường kiểm thử.

Nếu có yêu cầu mới “thêm SMS nhắc lịch học”, Product Owner có thể ghi vào Product Backlog để xem xét sau, trừ khi có lý do và thỏa thuận phù hợp để điều chỉnh phạm vi hiện tại mà không gây hại Sprint Goal. **Scrum khuyến khích thích ứng có trách nhiệm, không phải chấp nhận mọi yêu cầu phát sinh lập tức**.

### 7.6. DoD và quyết định có Increment hay chưa

Definition of Done minh họa của Scrum Team có thể yêu cầu:

- Luồng sử dụng từ giao diện đến dữ liệu hoạt động trong môi trường tích hợp thích hợp.
- Tiêu chí chấp nhận quan trọng được xác minh.
- Kiểm thử tự động và kiểm thử tích hợp bắt buộc chạy đạt.
- Không tạo đăng ký trùng, không vượt sức chứa khi có yêu cầu cạnh tranh.
- Quyền truy cập và thông tin riêng tư được bảo vệ theo chính sách.
- Lỗi nghiêm trọng được xử lý, mã được review và tích hợp vào sản phẩm.
- Hợp đồng API, tài liệu chịu tác động và hướng dẫn vận hành cần thiết được cập nhật.

Nếu thiếu môi trường để kiểm tra đồng thời, nhóm **không được gọi toàn bộ luồng là Done** chỉ vì phần demo một người dùng chạy được. Nhóm cần minh bạch việc nào đã hoàn tất, việc nào đang bị chặn và kế hoạch xử lý.

### 7.7. Sprint Review: nhận phản hồi giá trị

Khi có Increment dùng được, Scrum Team cùng stakeholder kiểm tra luồng đăng ký. Giả sử học viên hoàn thành được tác vụ nhưng hiểu nhầm rằng thông báo thành công đồng nghĩa khóa học bắt đầu ngay. Kết quả này có thể dẫn tới ưu tiên làm rõ trạng thái xác nhận trước khi xây SMS.

**Điều được học** từ người dùng là một phần quan trọng của tiến độ. Việc đã tạo một Increment không tự chứng minh sản phẩm đạt mọi mục tiêu kinh doanh; cần đo hành vi sử dụng với phạm vi và chất lượng dữ liệu phù hợp.

### 7.8. Sprint Retrospective: cải thiện hệ thống làm việc

Nhóm xem lại tại sao kiểm thử đồng thời được thực hiện muộn. Giả sử nguyên nhân là hạng mục quá lớn và pipeline chưa có kịch bản dữ liệu cạnh tranh. Một cải tiến nhỏ cho Sprint sau là tạo test tích hợp đồng thời ngay khi xây lát cắt lưu đăng ký, thay vì chờ cuối Sprint.

Scrum mang lại hai vòng thích ứng liên quan:

- **Thích ứng sản phẩm:** Product Backlog thay đổi theo giá trị và phản hồi.
- **Thích ứng cách làm:** kỹ thuật, công cụ và cách phối hợp cải thiện để giao Increment tốt hơn.

## 8. Cách nhìn một Sprint từ đầu đến cuối

Một Sprint hai tuần có thể diễn ra theo sơ đồ **minh họa**, không phải lịch bắt buộc:

~~~mermaid
flowchart LR
    A["Sprint Planning: chọn mục tiêu"] --> B["Làm rõ, xây dựng và tích hợp"]
    B --> C["Kiểm tra Increment và DoD"]
    C --> D["Sprint Review: phản hồi sản phẩm"]
    D --> E["Retrospective: cải tiến cách làm"]
    E --> F["Sprint kế tiếp"]
    B -. "Daily Scrum, trao đổi liên tục" .-> B
~~~

Trong thực tế, kiểm thử, trao đổi với stakeholder và nhận phản hồi có thể bắt đầu từ ngày đầu, không nhất thiết phải chờ đến Review. Sprint Review và Retrospective thường diễn ra gần cuối Sprint, còn Sprint mới bắt đầu ngay sau Sprint trước.

Một cách trình bày theo hoạt động:

| Giai đoạn minh họa | Công việc có trọng tâm | Bằng chứng hoặc quyết định |
| --- | --- | --- |
| **Đầu Sprint** | Tạo Sprint Goal, chọn PBI và kế hoạch; xác nhận rủi ro lớn. | Sprint Backlog rõ và có căn cứ năng lực. |
| **Trong Sprint** | Xây lát cắt, tích hợp, kiểm thử; Daily Scrum kiểm tra tiến độ. | Increment hình thành, vấn đề được phát hiện sớm. |
| **Khi có thông tin mới** | Developers điều chỉnh kế hoạch, thương lượng phạm vi với PO khi cần. | Sprint Goal và DoD vẫn được bảo vệ. |
| **Sprint Review** | Kiểm tra kết quả với stakeholder, xem điều gì có giá trị. | Phản hồi và điều chỉnh Product Backlog. |
| **Retrospective** | Xem lại cách phối hợp, chất lượng, phụ thuộc. | Một số cải tiến cụ thể cho công việc tiếp theo. |

Không nên đồng nhất Sprint với “mini-waterfall” gồm ngày đầu phân tích, ngày giữa code, ngày cuối mới kiểm thử. Cách chia giai đoạn cứng làm chậm kiểm chứng và dễ khiến Increment chưa Done khi Sprint kết thúc.

## 9. Scrum, Kanban và XP liên hệ với nhau ra sao?

Scrum, Kanban và XP thường được nhắc cùng trong học Agile, nhưng chúng **không phải ba tên khác nhau cho một quy trình**.

| Khía cạnh | Scrum | Kanban | XP |
| --- | --- | --- | --- |
| **Trọng tâm** | Khung làm việc với trách nhiệm, sự kiện và artifact để tạo giá trị qua kiểm tra–thích ứng. | Quản lý và cải thiện dòng công việc, khả năng dự báo và thời gian hoàn tất. | Các giá trị và thực hành phát triển phần mềm nhấn mạnh kỹ thuật và phản hồi nhanh. |
| **Nhịp công việc** | Sprint timebox tối đa một tháng; các sự kiện Scrum. | Có thể là luồng liên tục, không bắt buộc Sprint. | Có thể sử dụng các vòng lặp ngắn và thực hành kỹ thuật thường xuyên. |
| **Cơ chế nổi bật** | Sprint Goal, Increment, DoD, Review và Retrospective. | Trực quan hóa workflow, giới hạn WIP, pull, đo flow. | TDD, pairing, CI, refactoring, thiết kế đơn giản khi phù hợp. |
| **Điểm mạnh bổ trợ** | Tạo nhịp tập trung và kiểm tra mục tiêu sản phẩm. | Làm rõ điểm nghẽn và thời gian chờ trong quá trình giao hàng. | Giúp các Increment nhỏ vẫn có chất lượng kỹ thuật. |

Một Scrum Team có thể **dùng thực hành Kanban** để trực quan hóa Sprint Backlog và quản lý WIP; đồng thời vận dụng **XP** để giữ khả năng tích hợp và kiểm thử liên tục. Tuy nhiên, khi nói “đang dùng Scrum”, nhóm vẫn cần giữ các thành phần nền tảng của Scrum thay vì lược bỏ trách nhiệm hoặc sự kiện bắt buộc rồi chỉ giữ tên gọi.

### 9.1. Scrum không chỉ dành cho dự án viết phần mềm

Scrum có thể được dùng trong các bối cảnh giải quyết vấn đề phức tạp khác, miễn có **sản phẩm/mục tiêu rõ, khả năng tạo Increment có ích, cơ hội kiểm tra và thích ứng**. Tuy vậy, không phải mọi loại công việc đều hưởng lợi như nhau từ Sprint.

Một đội tiếp nhận sự cố bất ngờ liên tục có thể cần quản lý luồng và ưu tiên khẩn cấp khác với đội tập trung phát triển năng lực sản phẩm. Có thể dùng các thực hành bổ trợ hoặc chọn cách tổ chức phù hợp, miễn bảo đảm chất lượng và phối hợp.

## 10. Đo tiến độ Scrum bằng gì?

Nguyên tắc Agile coi **phần mềm hoạt động được** là một thước đo chính của tiến độ. Trong Scrum, cần kết hợp khả năng Increment thực sự hoàn tất, tiến độ hướng tới Product Goal và bằng chứng về giá trị người dùng.

| Nhóm tín hiệu | Ví dụ | Cách sử dụng cẩn trọng |
| --- | --- | --- |
| **Increment đáp ứng DoD** | Luồng đăng ký chạy đầu cuối, đã tích hợp và kiểm thử. | Không đồng nhất demo với Increment hoàn tất. |
| **Tiến độ hướng tới Sprint Goal** | Những hành vi còn thiếu để học viên tự đăng ký đáng tin cậy. | Kiểm tra mục tiêu chung, không chỉ số task đã đóng. |
| **Outcome sản phẩm** | Tỷ lệ học viên hoàn tất, số yêu cầu hỗ trợ, thời gian thao tác. | Xem bối cảnh và bằng chứng, không suy luận nhân quả vội. |
| **Chất lượng và độ tin cậy** | Lỗi nghiêm trọng, lỗi sau phát hành, thất bại kiểm thử. | Không tăng tốc độ bằng cách cắt DoD hoặc giấu lỗi. |
| **Cycle time / work item age** | Hạng mục mất bao lâu để hoàn tất, mục nào mắc kẹt. | Định nghĩa mốc đo nhất quán; dùng để phát hiện tắc nghẽn. |
| **Throughput / WIP** | Số hạng mục Done, số việc dở dang. | Không xem số lượng thay cho giá trị và kích thước khác nhau. |
| **Khả năng học hỏi** | Thời gian từ giả thuyết đến phản hồi có ích. | Phản hồi phải từ nguồn phù hợp, không chỉ báo cáo nội bộ. |

**Velocity** hoặc **burndown chart** là các kỹ thuật hỗ trợ dự báo/quan sát mà nhóm có thể chọn, **không phải artifact hoặc sự kiện bắt buộc trong Scrum Guide**. Không nên dùng story point hay velocity để xếp hạng cá nhân hoặc so sánh năng suất trực tiếp giữa các Scrum Team, vì cách ước lượng và chia việc khác nhau.

### 10.1. Ví dụ báo cáo minh bạch

Thay vì:

> “Chúng tôi đã hoàn tất 18/20 task, tiến độ đạt 90%.”

Có thể nói:

> “Mục tiêu Sprint là để học viên thử nghiệm tự đăng ký khóa miễn phí. Luồng đăng ký thành công và xử lý đăng ký lặp đã tích hợp; kiểm thử cạnh tranh chỗ cuối chưa đạt nên Increment này chưa đáp ứng DoD. Nhóm đang sửa phần giao dịch, đã thương lượng hoãn bộ lọc nâng cao và sẽ công khai kết quả kiểm chứng trong Sprint Review.”

Thông tin thứ hai phản ánh khả năng giao giá trị và rủi ro tốt hơn tỷ lệ task.

## 11. Những hiểu lầm và phản mẫu phổ biến

| Phản mẫu | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **Scrum chỉ là họp Daily mỗi sáng.** | Thiếu mục tiêu, artifact, Increment và cơ hội thích ứng. | Hiểu toàn bộ khung, gắn sự kiện với mục đích rõ. |
| **Scrum Master giao task và đánh giá mọi thành viên.** | Developers không còn tự quản lý; Daily thành buổi báo cáo cấp trên. | Làm rõ trách nhiệm Scrum Master và quyền lập kế hoạch của Developers. |
| **Product Owner là hội đồng nhiều người.** | Ưu tiên mâu thuẫn, nhóm không biết quyết định cuối cùng. | Một PO chịu trách nhiệm, lắng nghe nhiều stakeholder. |
| **Sprint Goal là 15 ticket phải đóng bằng mọi giá.** | Đội tối ưu số task, không nhìn giá trị chung. | Viết mục tiêu kết quả có trọng tâm, dùng Sprint Backlog làm kế hoạch linh hoạt. |
| **Không được thay đổi gì trong Sprint.** | Nhóm bỏ qua hiểu biết mới hoặc phải làm lại muộn. | Làm rõ và thương lượng phạm vi với PO mà vẫn bảo vệ Sprint Goal, DoD. |
| **Review là buổi PO “nghiệm thu” và cho phép release.** | Phản hồi sản phẩm bị thu hẹp thành phê duyệt; giao hàng bị chặn vô ích. | Dùng Review để kiểm tra kết quả và cộng tác; release có thể độc lập. |
| **Retro chỉ nêu điều tốt/xấu mà không hành động.** | Vấn đề lặp lại, mất niềm tin vào cải tiến. | Chọn cải tiến cụ thể, theo dõi tác động ở Sprint sau. |
| **Chưa kiểm thử xong vẫn gọi Done.** | Minh bạch sai; tích lũy lỗi và rủi ro. | Áp dụng DoD chung, công khai phần chưa hoàn tất. |
| **Chia Sprint thành phân tích → code → test nối tiếp.** | Tích hợp và phản hồi đến cuối Sprint. | Làm lát cắt dọc, tích hợp và kiểm thử liên tục. |
| **Làm nhiều việc dở để mọi người luôn bận.** | Chuyển ngữ cảnh và chờ đợi tăng, ít Increment hoàn tất. | Hạn chế WIP, hỗ trợ công việc gần Done. |
| **Scrum bắt buộc mọi nhóm dùng story points.** | Đánh giá dựa trên số điểm thay vì giá trị và chất lượng. | Dùng kỹ thuật ước lượng phù hợp, Scrum không quy định đơn vị. |
| **Hoàn thành Sprint là phải release mọi thứ.** | Đồng nhất timebox với chiến lược phát hành, dễ tăng rủi ro. | Increment phải dùng được theo DoD; thời điểm release là quyết định riêng. |

### 11.1. Khi sự kiện không tạo ra thích ứng

Hãy kiểm tra ba câu hỏi:

1. **Minh bạch được điều gì?** Ví dụ tình trạng Increment, trở ngại, giá trị và rủi ro.
2. **Kiểm tra được bằng chứng nào?** Ví dụ hành vi sản phẩm, test tích hợp, phản hồi học viên.
3. **Đã điều chỉnh điều gì?** Ví dụ thứ tự backlog, cách phối hợp hoặc kế hoạch Sprint.

Nếu một sự kiện chỉ ghi biên bản mà không làm rõ gì hoặc không hỗ trợ quyết định, cần xem lại cách tổ chức sự kiện và mức độ tham gia của đúng đối tượng.

## 12. Bắt đầu áp dụng Scrum từ một nhóm thực tế

Không cần viết quy trình hàng trăm trang trước khi thử Scrum, nhưng cũng không nên chỉ đổi tên các cuộc họp cũ. Một cách tiếp cận có thể bắt đầu như sau:

### Bước 1 — Xác định sản phẩm và Product Goal

Nêu rõ sản phẩm phục vụ ai, vấn đề cần giải quyết và kết quả tương lai mong muốn. Xác định ranh giới sản phẩm đủ rõ để Product Backlog có một mục đích chung.

**Ví dụ:** “Giảm phụ thuộc vào nhân viên khi học viên đăng ký khóa học”.

### Bước 2 — Làm rõ Scrum Team và các trách nhiệm

Xác định một Product Owner, một Scrum Master và Developers đủ năng lực tạo Increment. Thống nhất cách nhóm tiếp cận người dùng, kỹ năng còn thiếu và các giới hạn thẩm quyền với bên ngoài.

Không nên bổ nhiệm Scrum Master chỉ như người gửi lịch họp, hoặc PO chỉ như người nhận yêu cầu mà không có quyền quyết định thứ tự sản phẩm.

### Bước 3 — Xây một Product Backlog có thứ tự

Thu thập những cơ hội chính; sắp thứ tự theo giá trị, rủi ro, phụ thuộc và tính cấp thiết. Làm rõ các hạng mục gần bằng ví dụ hành vi, tiêu chí chấp nhận và mức độ bất định.

Không cần mô tả tỉ mỉ toàn bộ backlog xa. Cần ưu tiên những mục có thể đóng góp cho **Increment đầu tiên và phản hồi sớm**.

### Bước 4 — Thiết lập DoD và khả năng kỹ thuật

Thống nhất tiêu chuẩn tích hợp, kiểm thử, bảo mật, chất lượng và tài liệu cần thiết. Đầu tư cơ chế CI, test và môi trường phù hợp để nhóm có thể thực sự tạo Increment hoàn tất.

### Bước 5 — Chọn độ dài Sprint và tạo Sprint Goal đầu tiên

Chọn độ dài Sprint cố định không quá một tháng, dựa trên nhu cầu phản hồi và khả năng hoàn tất. Tại Sprint Planning, tạo Sprint Goal có trọng tâm, Developers lựa chọn và lập kế hoạch thực hiện.

Không lấp đầy Sprint chỉ vì một bảng ước lượng nói rằng còn đủ vài story point.

### Bước 6 — Kiểm tra và thích ứng trong Sprint

Developers dùng Daily Scrum để kiểm tra tiến độ và điều chỉnh kế hoạch. Nhóm phối hợp với PO và stakeholder bất cứ khi nào cần làm rõ. Scrum Master giúp giảm trở ngại và cải thiện khả năng tự quản lý.

### Bước 7 — Kiểm tra sản phẩm và cải tiến cách làm

Tại Review, đưa kết quả và bằng chứng ra thảo luận cùng stakeholder. Tại Retrospective, chọn cải tiến thiết thực. Sau đó bắt đầu Sprint mới và lặp lại vòng kiểm tra–thích ứng.

## 13. Bài tập thực hành

### Bài tập 1 — Nhận diện Scrum hay chỉ là “họp theo Scrum”

Một nhóm có Daily 15 phút và Sprint hai tuần, nhưng người quản lý giao từng task, Product Backlog không có người chịu trách nhiệm sắp thứ tự, cuối Sprint chỉ demo giao diện dùng dữ liệu giả, còn kiểm thử được chuyển sang một tháng sau.

**Câu hỏi:**

1. Những yếu tố nào của Scrum đang thiếu hoặc bị hiểu sai?
2. Vì sao khó gọi kết quả cuối Sprint là Increment?
3. Nên thay đổi ba điều gì trước để cải thiện khả năng giao giá trị?

**Gợi ý:** làm rõ trách nhiệm PO/Developers/SM; xác lập Product Goal và Sprint Goal; tạo Definition of Done với khả năng tích hợp/kiểm thử trong Sprint. Daily và timebox tự chúng không đủ tạo Scrum hiệu quả.

### Bài tập 2 — Viết Sprint Goal từ danh sách công việc

Danh sách dự kiến:

- Tạo API kiểm tra số chỗ.
- Viết form đăng ký.
- Thêm cơ chế chống đăng ký trùng.
- Viết test tích hợp.
- Tạo dashboard số lượng đăng ký.

Hãy viết một Sprint Goal tập trung **một kết quả dùng được**, chọn các công việc cần thiết và giải thích mục nào có thể hoãn nếu không phục vụ mục tiêu chính.

**Đáp án tham khảo:** “Học viên thử nghiệm có thể tự đăng ký một khóa miễn phí còn chỗ và nhận xác nhận đúng”. API, form, chống trùng và kiểm thử tích hợp cần thiết; dashboard có thể cân nhắc làm trong hạng mục khác nếu không bắt buộc cho hành vi này.

### Bài tập 3 — Phân biệt sự kiện Scrum

Ghép mỗi tình huống với sự kiện phù hợp:

| Tình huống | Sự kiện nên dùng chủ yếu |
| --- | --- |
| Nhóm chọn Sprint Goal và công việc có thể giao. | **Sprint Planning** |
| Developers thấy một hạng mục bị chặn và điều chỉnh kế hoạch hôm nay. | **Daily Scrum** (hoặc trao đổi trực tiếp ngay khi phát hiện). |
| Người dùng thử Increment và cùng nhóm xem bước sản phẩm tiếp theo. | **Sprint Review** |
| Nhóm tìm cách giảm lỗi tích hợp bị lặp lại qua nhiều Sprint. | **Sprint Retrospective** |
| Nhóm tích hợp, kiểm thử và tạo Increment. | Diễn ra **trong Sprint**, không phải một sự kiện riêng bổ sung. |

### Bài tập 4 — Xác định artifact và commitment

Giả sử nhóm đang xây phần mềm đặt lịch:

1. “Người dùng có thể đặt và quản lý lịch hẹn trực tuyến an toàn” thuộc loại mục tiêu nào?
2. “Trong Sprint này, khách đặt được một khung giờ còn chỗ và biết kết quả” thuộc loại mục tiêu nào?
3. Danh sách các việc sẽ giúp đạt mục tiêu Sprint nằm trong artifact nào?
4. Chuẩn kiểm thử, tích hợp và bảo mật cần đạt trước khi gọi phần sản phẩm Done là gì?

**Gợi ý:** lần lượt là Product Goal, Sprint Goal, Sprint Backlog và Definition of Done. Cần nhớ Sprint Backlog còn gồm Sprint Goal và các Product Backlog Items được chọn, không chỉ danh sách task.

### Bài tập 5 — Xử lý thay đổi trong Sprint

Giữa Sprint, người phụ trách kinh doanh yêu cầu thêm SMS nhắc học, còn Developers phát hiện cơ chế đăng ký hiện tại có thể tạo hai bản ghi cho một học viên.

Hãy xác định:

- Đâu là hành vi cần thiết để đáp ứng mục tiêu và DoD?
- Đâu là khả năng mới cần sắp thứ tự trên Product Backlog?
- Product Owner và Developers cần trao đổi, quyết định những gì?
- Scrum Master có thể hỗ trợ tháo gỡ trở ngại nào?
- Bằng chứng nào cần có trước khi tuyên bố Increment hoàn tất?

**Gợi ý:** chống đăng ký trùng là điều kiện đúng đắn nếu đã cam kết hành vi đăng ký hợp lệ. SMS là khả năng bổ sung cần được ưu tiên có căn cứ. Developers đánh giá công việc và điều chỉnh kế hoạch; PO chịu trách nhiệm thứ tự backlog; SM giúp giải quyết trở ngại, không tự ý hạ DoD.

### Bài tập 6 — Đánh giá kết quả Sprint

Một Sprint có 10 Product Backlog Items được chọn. Cuối Sprint có:

- 6 mục đáp ứng DoD.
- 2 mục đã viết mã nhưng chưa tích hợp.
- 2 mục chưa bắt đầu.

**Câu hỏi:** Có thể báo “đã hoàn thành 80% Increment” vì tám mục đã có mã hoặc tiến độ không? Scrum Team nên trao đổi gì trong Review và Retrospective?

**Gợi ý:** không nên đồng nhất mục “có mã” với Increment đáp ứng DoD. Cần báo rõ sáu mục Done và phạm vi giá trị chúng tạo ra, xem Sprint Goal có đạt hay không, thảo luận lý do thiếu tích hợp và điều chỉnh backlog/kỹ thuật cho Sprint tiếp theo.

## 14. Checklist tự đánh giá việc áp dụng Scrum

- [ ] Sản phẩm và Product Goal được xác định và hiểu chung.
- [ ] Scrum Team có một Product Owner, một Scrum Master và Developers.
- [ ] Trách nhiệm của từng vai trò được làm rõ; nhóm tự quản lý trong phạm vi phù hợp.
- [ ] Product Backlog minh bạch, được sắp thứ tự và làm rõ khi cần.
- [ ] Sprint có độ dài cố định tối đa một tháng và diễn ra nối tiếp.
- [ ] Sprint Planning tạo một Sprint Goal có trọng tâm cùng Sprint Backlog.
- [ ] Daily Scrum giúp Developers kiểm tra và điều chỉnh kế hoạch, không biến thành buổi báo cáo cấp trên.
- [ ] Scrum Team có cơ chế tích hợp, kiểm thử và tạo Increment đáp ứng DoD.
- [ ] Sprint Review là buổi cộng tác dựa trên kết quả và phản hồi stakeholder.
- [ ] Retrospective tạo cải tiến có thể thực hiện và kiểm tra hiệu quả.
- [ ] Thay đổi phạm vi trong Sprint được xử lý minh bạch, bảo vệ Sprint Goal và chất lượng.
- [ ] Các trở ngại, rủi ro và phần chưa Done được trình bày trung thực.
- [ ] Việc đo lường gồm giá trị sản phẩm, chất lượng và khả năng giao, không chỉ ticket/story point.

Checklist hỗ trợ thảo luận chứ không thay thế Scrum Guide. Khi một mục chưa đáp ứng, nên tìm nguyên nhân và thử cải tiến có thể đo, thay vì chỉ thêm biểu mẫu hoặc cuộc họp.

## 15. Tổng kết

**Scrum là khung làm việc nhẹ để tạo giá trị khi phải giải quyết vấn đề phức tạp.** Nó dựa trên **empiricism**, **lean thinking**, ba trụ cột **minh bạch–kiểm tra–thích ứng** và năm giá trị **cam kết–tập trung–cởi mở–tôn trọng–can đảm**.

Scrum Team tự quản lý, liên chức năng; ba trách nhiệm **Product Owner, Scrum Master, Developers** phối hợp để đạt Product Goal. Năm sự kiện tạo nhịp làm việc và học hỏi; ba artifact cùng các cam kết **Product Goal, Sprint Goal, Definition of Done** giúp kết quả và tiến độ minh bạch.

Điểm phân biệt một nhóm Scrum hiệu quả không phải là sử dụng đủ thuật ngữ. Đó là khả năng **giao Increment hoạt động được, được kiểm chứng, nhận phản hồi và thay đổi quyết định kịp thời**, đồng thời liên tục cải thiện cách cộng tác và chất lượng kỹ thuật.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Scrum** | Khung làm việc nhẹ giúp tạo giá trị qua giải pháp thích ứng cho vấn đề phức tạp. |
| **Empiricism** | Tiếp cận dựa trên kinh nghiệm thực tế và quyết định từ quan sát. |
| **Transparency, Inspection, Adaptation** | Ba trụ cột: minh bạch, kiểm tra và thích ứng. |
| **Lean thinking** | Tư duy tập trung vào điều thiết yếu và giảm lãng phí. |
| **Scrum Team** | Đơn vị liên chức năng, tự quản lý gồm Product Owner, Scrum Master và Developers. |
| **Product Owner** | Người chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. |
| **Scrum Master** | Người chịu trách nhiệm thiết lập Scrum và hiệu quả Scrum Team, hỗ trợ đội và tổ chức. |
| **Developers** | Những thành viên chịu trách nhiệm tạo Increment dùng được và lập kế hoạch Sprint. |
| **Sprint** | Khoảng thời gian cố định tối đa một tháng, chứa công việc và các sự kiện Scrum khác. |
| **Product Backlog** | Danh sách nổi lên, được sắp xếp của những điều cần để cải thiện sản phẩm. |
| **Product Goal** | Cam kết về trạng thái tương lai của sản phẩm mà Scrum Team hướng tới. |
| **Sprint Backlog** | Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện của Developers. |
| **Sprint Goal** | Mục tiêu chung của Sprint, tạo sự tập trung và linh hoạt về cách thực hiện. |
| **Increment** | Phần tăng trưởng sản phẩm được tích hợp, xác minh và có thể sử dụng. |
| **Definition of Done (DoD)** | Cam kết về chuẩn chất lượng để xác định khi Increment hoàn tất. |
| **Backlog refinement** | Hoạt động liên tục chia nhỏ và làm rõ Product Backlog Items. |
| **Acceptance criteria** | Điều kiện cụ thể xác nhận hành vi mong đợi của một hạng mục. |
| **Impediment** | Trở ngại làm chậm hoặc cản nhóm đạt mục tiêu. |

