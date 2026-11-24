# Giới hạn thời gian bằng timebox và lựa chọn nhịp phản hồi

Một nhóm phát triển nền tảng học trực tuyến đang tranh luận về tính năng “Học tiếp”. Người phụ trách sản phẩm muốn thử ngay với học viên, nhóm kỹ thuật cần kiểm tra cách đồng bộ tiến độ, còn các bên liên quan đề nghị “cứ nghiên cứu cho chắc rồi mới làm”. Nếu không giới hạn, hoạt động nghiên cứu có thể kéo dài mà chưa tạo bằng chứng cho quyết định. Nhưng nếu áp hạn chót cứng cho toàn bộ tính năng rồi bỏ qua kiểm thử để kịp ngày, nhóm lại tăng rủi ro mất dữ liệu.

**Timebox** giúp giới hạn thời gian dành cho một hoạt động, buộc nhóm tập trung vào mục tiêu và cách sử dụng thời gian. **Nhịp phản hồi (feedback cadence)** xác định khi nào và bằng cách nào nhóm chủ động kiểm tra thông tin mới để điều chỉnh quyết định. Hai khái niệm liên quan nhưng không đồng nhất: có thể kết thúc một timebox mà chưa nhận được phản hồi có giá trị; cũng có thể nhận phản hồi liên tục mà không tổ chức công việc theo Sprint.

Bài thuộc chương **Kế hoạch thích ứng** của module **AGILE_DEVELOPMENT**. Mục tiêu là biết lựa chọn nhịp phối hợp phù hợp để **giao sản phẩm tăng dần, kiểm tra user story và backlog, nhận phản hồi sớm, phối hợp Scrum/Kanban/XP và cải tiến dòng công việc**. Kế hoạch có ích khi giúp nhóm ra quyết định tốt hơn trước bất định, thay vì biến ngày tháng thành mục đích.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **timebox, deadline, cadence, cycle time, lead time** và các loại phản hồi.
2. Thiết kế một timebox có mục tiêu, phạm vi lựa chọn, sản phẩm đầu ra, tiêu chí dừng và quyết định tiếp theo.
3. Hiểu các timebox trong Scrum và tránh xem mọi buổi họp định kỳ là một sự kiện Scrum bắt buộc.
4. Thiết kế nhịp phản hồi cho nhóm vận hành theo **Scrum, Kanban hoặc cách kết hợp phù hợp**, phân biệt phản hồi kỹ thuật với phản hồi giá trị sản phẩm.
5. Chọn tần suất kiểm tra theo độ bất định, hậu quả nếu sai, thời gian tạo bằng chứng, khả năng tham gia của người dùng và chi phí phối hợp.
6. Dùng số liệu dòng công việc và chất lượng để đánh giá nhịp đã chọn, rồi điều chỉnh bằng thử nghiệm nhỏ.
7. Bảo vệ tiêu chuẩn chất lượng và nhịp làm việc bền vững khi thời gian đã hết mà công việc chưa hoàn tất.

## 2. Từ vựng cốt lõi: giống nhau ở chỗ có thời gian, khác nhau ở mục đích

| Khái niệm | Câu hỏi nó trả lời | Ví dụ | Điều cần tránh |
| --- | --- | --- | --- |
| **Timebox** | Chúng ta dành **tối đa bao lâu** cho hoạt động này, rồi đánh giá/ra quyết định gì? | Dành tối đa hai ngày kiểm tra rủi ro đồng bộ tiến độ | Nghĩ rằng hết giờ thì kết quả phải được tuyên bố “xong” |
| **Deadline / hạn chót** | Đến thời điểm nào một nghĩa vụ hoặc kết quả phải được đáp ứng? | Ngày phải cung cấp báo cáo cho đối tác | Tưởng deadline tự cho biết phạm vi nào có thể hoàn thành an toàn |
| **Cadence / nhịp** | Hoạt động kiểm tra, phối hợp hoặc ra quyết định **lặp lại khi nào**? | Họp làm rõ backlog mỗi tuần; xem phản hồi người dùng hai lần/tháng | Tổ chức buổi họp chỉ vì lịch có sẵn, dù không có mục tiêu |
| **Cycle time** | Mất bao lâu từ mốc **bắt đầu xử lý** đến mốc **hoàn tất** đã định nghĩa? | Một work item hoàn tất trong 4 ngày sau khi bắt đầu | Đánh đồng thời gian xử lý một item với thời lượng Sprint |
| **Lead time** | Người yêu cầu phải chờ bao lâu từ mốc **đưa yêu cầu** đến lúc nhận kết quả? | Yêu cầu được ghi nhận ngày 1, giao ngày 9 | So sánh số liệu khi các nhóm dùng mốc đo khác nhau |
| **Feedback latency / độ trễ phản hồi** | Sau khi có điều cần kiểm chứng, bao lâu mới có thông tin đủ để điều chỉnh? | Phải đợi 3 tuần mới gặp được học viên để quan sát luồng mới | Chỉ đếm số buổi review mà không xét độ trễ học hỏi |
| **Release / phát hành** | Khi nào phần sản phẩm được đưa đến môi trường/đối tượng sử dụng? | Giao Increment đạt Done cho một nhóm thử nghiệm khi an toàn | Mặc định mỗi timebox đều phải có phát hành production |

Ví dụ: Nhóm chọn **Sprint hai tuần** là nhịp làm việc có timebox. Một user story có thể có **cycle time ba ngày**, được phát hành vào ngày thứ năm và nhận phản hồi từ học viên ngay ngày thứ sáu. Các mốc này có thể khác nhau. Scrum không bắt buộc chỉ phát hành ở cuối Sprint.

### Timebox không phải “cố làm cho xong bằng mọi giá”

Một timebox tốt thường **giữ giới hạn thời gian và điều chỉnh phạm vi hoặc cách tiếp cận** khi phát hiện thực tế khác dự tính. Nó không cho phép bỏ qua Definition of Done, kiểm thử an toàn, quyền truy cập hoặc nghĩa vụ tuân thủ để gọi công việc là hoàn tất.

Kết thúc timebox khám phá có thể cho ba kết quả hợp lệ:

- Bằng chứng đã đủ để chọn một giải pháp.
- Bằng chứng bác bỏ giả định ban đầu và nhóm thay đổi hướng.
- Bằng chứng chưa đủ; nhóm trình bày rõ điều đã học, rủi ro còn lại và đề xuất có gia hạn khám phá bằng **một quyết định mới** hay không.

Khác với timebox nghiên cứu, một cam kết giao hàng theo hợp đồng có thể có ngày hoàn thành không được tự ý thay đổi. Nhóm cần chủ động làm rõ phạm vi, ưu tiên, dự phòng và cách xử lý nếu dự báo cho thấy không kịp hạn.

## 3. Vì sao timebox có ích cho kế hoạch thích ứng?

Trong môi trường phức tạp, nhiều quyết định không thể giải bằng cách “lập kế hoạch thật chi tiết ngay từ đầu”. Timebox hữu ích vì:

1. **Giới hạn chi phí học hỏi:** Nhóm không dành vô hạn thời gian cho một câu hỏi chưa chắc quan trọng.
2. **Buộc làm rõ mục tiêu:** “Hai ngày để biết cơ chế đồng bộ có khả thi không” cụ thể hơn “nghiên cứu đồng bộ”.
3. **Tạo mốc kiểm tra:** Đến hạn, nhóm đối chiếu giả thuyết, bằng chứng và mức rủi ro còn lại.
4. **Giảm trì hoãn quyết định:** Những lựa chọn đủ cơ sở được chốt trong phạm vi quyền hạn; câu hỏi chưa rõ được nêu minh bạch.
5. **Tăng khả năng phối hợp:** Các bên biết thời điểm cần cung cấp thông tin và tham gia phản hồi.
6. **Bảo vệ sự tập trung:** Giới hạn một cuộc họp hay phiên phân tích giúp giảm thời gian lan man, đặc biệt khi mục tiêu đã rõ.

Tuy vậy, timebox **không tự tạo ra giá trị**. Nếu nhóm dành một giờ họp nhưng thiếu người có quyền quyết định hoặc không có thông tin cần thiết, kết quả vẫn có thể là một giờ bị mất. Cần thiết kế **điều kiện trước, cách làm trong timebox và hành động sau**.

## 4. Thiết kế một timebox có thể kiểm chứng

Một timebox thực hành có thể được mô tả qua sáu thành phần:

| Thành phần | Câu hỏi cụ thể | Ví dụ kiểm chứng kỹ thuật |
| --- | --- | --- |
| **Mục tiêu/điều cần học** | Sau hoạt động, phải biết hoặc quyết định được gì? | Chọn cách xử lý hai thiết bị cùng cập nhật tiến độ |
| **Giới hạn thời gian** | Bắt đầu, kết thúc và tối đa bao lâu? | Tối đa hai ngày làm việc |
| **Phạm vi/giới hạn an toàn** | Những tình huống nào sẽ xem, những gì chưa cần xây? | Mô phỏng cập nhật cạnh tranh; không triển khai thử nghiệm vào production |
| **Người và nguồn lực** | Ai tham gia, ai có quyền quyết định, cần môi trường nào? | Hai Developers, người kiểm thử, môi trường staging |
| **Đầu ra/bằng chứng** | Dấu vết nào chứng minh điều đã làm hoặc đã học? | Kịch bản thử, kết quả, giới hạn, khuyến nghị và rủi ro |
| **Tiêu chí dừng/điểm quyết định** | Khi hết thời gian hoặc đủ bằng chứng, tiếp tục như thế nào? | Chọn cơ chế A/B, kiểm chứng thêm câu hỏi hẹp hơn hoặc đổi thiết kế |

### Mẫu timebox ngắn

~~~text
Vấn đề/giả định:
  [Điều gì chưa rõ, vì sao đáng kiểm chứng?]

Quyết định cần hỗ trợ:
  [Sau khi có bằng chứng, ta phải chọn điều gì?]

Timebox:
  [Bắt đầu] → [Kết thúc], tối đa [...]

Đối tượng/phạm vi:
  [Những trường hợp thử; điều gì nằm ngoài phạm vi]

Sản phẩm đầu ra:
  [Kết quả đo, mẫu thử, quyết định, danh sách rủi ro...]

Điều kiện chất lượng/an toàn:
  [Những giới hạn không được bỏ qua]

Khi hết timebox:
  [Ai xem bằng chứng; chọn tiếp tục/đổi hướng/thử thêm/dừng]
~~~

**Ví dụ tốt:** “Trong tối đa 90 phút, Product Owner, Developers và người hiểu nghiệp vụ sẽ tìm ra ba lát cắt user story có thể kiểm chứng, xác định quy tắc phân quyền bắt buộc và đánh dấu câu hỏi chưa rõ để xử lý trước Sprint Planning.”

**Ví dụ yếu:** “Họp đến khi mọi người thống nhất toàn bộ yêu cầu của quý.” Câu này thiếu giới hạn và có thể ép nhóm giả vờ chắc chắn về những điều chưa kiểm chứng.

## 5. Timebox và nhịp phản hồi tác động nhau như thế nào?

Timebox là **giới hạn của một hoạt động hoặc chu kỳ**; cadence là **tần suất lặp lại những cơ hội kiểm tra/thích ứng**. Một nhóm có thể tổ chức Sprint đều nhưng vẫn thiếu phản hồi từ người dùng, hoặc có hệ thống CI phản hồi trong vài phút nhưng chỉ xem lại giá trị sản phẩm sau nhiều tháng.

~~~mermaid
flowchart LR
    A["Đặt mục tiêu và giả thuyết"] --> B["Tạo lát cắt giá trị<br/>trong giới hạn thời gian"]
    B --> C["Kiểm tra kỹ thuật<br/>và chất lượng"]
    C --> D["Giao hoặc thử an toàn"]
    D --> E["Nhận phản hồi<br/>đủ dùng cho quyết định"]
    E --> F["Điều chỉnh backlog,<br/>cách làm và dự báo"]
    F --> B
~~~

Các vòng phản hồi có thể chạy **đồng thời ở nhiều tốc độ**:

| Cấp độ | Phản hồi cần nhận | Nhịp khả thi thường gặp | Cách dùng |
| --- | --- | --- | --- |
| **Kỹ thuật** | Kiểm thử, review mã, tích hợp, bảo mật, chất lượng build | Mỗi thay đổi hoặc nhiều lần trong ngày, tùy hệ thống | Sửa sớm lỗi mới phát sinh |
| **Công việc hằng ngày** | Trở ngại, ưu tiên ngắn hạn, WIP và tiến độ mục tiêu | Liên tục qua bảng/trao đổi; có thể họp ngắn hằng ngày | Điều phối để hoàn thành việc đang làm |
| **Sản phẩm/khách hàng** | Tính khả dụng, hành vi người dùng, outcome và giả định giá trị | Ngay khi có lát cắt thử được; nhiều ngày/tuần tùy cách đo | Điều chỉnh giải pháp và ưu tiên |
| **Quy trình/nhóm** | Điểm nghẽn, chất lượng cộng tác, năng lực và học hỏi | Mỗi Sprint hoặc chu kỳ cải tiến được chọn | Thử thay đổi cách làm và kiểm tra tác động |
| **Chiến lược/đầu tư** | Mục tiêu, thị trường, chi phí cơ hội, phụ thuộc và nguồn lực | Theo mốc quyết định của tổ chức | Giữ, thay đổi hoặc dừng hướng đầu tư |

Các tần suất trên chỉ là **ví dụ**, không phải chuẩn chung. Phản hồi kỹ thuật nhanh không thay thế nghiên cứu người dùng, còn họp sản phẩm mỗi tuần không thay thế kiểm thử và giám sát lỗi mỗi lần triển khai.

### Phản hồi nhanh phải là phản hồi có chất lượng

Một CI pipeline báo lỗi sau 5 phút nhưng thường xuyên “đỏ giả” có thể khiến nhóm bỏ qua cảnh báo. Một nghiên cứu hỏi người dùng “Bạn có thích tính năng không?” trong 10 phút có thể rẻ nhưng quá yếu cho quyết định đầu tư lớn. Nhịp tốt phải cân đối **tốc độ, độ tin cậy của tín hiệu và chi phí hành động**.

## 6. Chọn nhịp phản hồi theo bối cảnh công việc

Không có câu trả lời “mọi nhóm Agile nên họp review mỗi tuần” hoặc “Sprint ngắn hơn luôn tốt hơn”. Hãy xem năm nhóm yếu tố:

1. **Mức bất định:** Nhu cầu thay đổi nhanh hay giải pháp kỹ thuật còn nhiều giả định chưa kiểm chứng? Bất định cao thường cần cơ hội học sớm hơn.
2. **Hậu quả của quyết định sai:** Sai có thể làm mất dữ liệu, tốn chi phí lớn, ảnh hưởng an toàn hay chỉ là màu nút dễ đảo ngược? Rủi ro cao cần kiểm chứng và bảo vệ phù hợp.
3. **Thời gian để có bằng chứng:** CI có thể phản hồi sau vài phút, nhưng retention bảy ngày không thể đánh giá đầy đủ ngay trong ngày đầu.
4. **Khả năng tham gia của người có thông tin:** Người dùng, Product Owner, bộ phận vận hành hoặc đối tác có thể phản hồi theo kênh và thời gian nào?
5. **Chi phí điều phối:** Mỗi cuộc họp, chuyển trạng thái hay phát hành đều có chi phí; nhịp quá dày có thể làm giảm thời gian tạo sản phẩm.

| Bối cảnh | Nhịp nên cân nhắc | Lý do |
| --- | --- | --- |
| Xây tính năng mới với giả định người dùng còn yếu | Prototype/khảo sát tác vụ sớm khi có bản thử; review outcome theo cửa sổ quan sát | Tránh hoàn tất nhiều tháng phát triển trước khi xác minh nhu cầu |
| Sửa lỗi sản xuất nghiêm trọng | Giám sát liên tục, phối hợp theo diễn biến sự cố; hậu kiểm khi hệ thống ổn định | Tác động đòi hỏi phản ứng ngay, không chờ tới Sprint Review |
| Dịch vụ hỗ trợ có việc đến không đều | Quản lý flow liên tục, bổ sung việc theo năng lực; review dịch vụ theo lịch phù hợp | Công việc không nhất thiết gom được thành Sprint Goal ổn định |
| Nhóm sản phẩm liên chức năng giải quyết vấn đề phức tạp | Scrum với Sprint đủ ngắn để kiểm tra tiến độ và mục tiêu thường xuyên | Có nhịp lập kế hoạch, quan sát Increment và cải tiến rõ |
| Hệ thống cần kiểm thử/tuân thủ nghiêm ngặt | Tự động hóa phản hồi kỹ thuật càng sớm càng phù hợp; review rủi ro theo mốc ra quyết định | Rút ngắn phát hiện lỗi nhưng không bỏ bằng chứng chất lượng bắt buộc |
| Phụ thuộc đối tác trả dữ liệu hai tuần/lần | Thống nhất thời điểm nhận dữ liệu, mock contract và các bước nội bộ không bị chặn | Chọn nhịp dựa trên khả năng có bằng chứng, giảm thời gian chờ |

Vấn đề không phải chọn một nhịp duy nhất cho mọi việc. Nhóm có thể có **nhịp Scrum hai tuần**, **CI mỗi lần thay đổi**, **theo dõi vận hành liên tục** và **đánh giá outcome sau khi đủ cửa sổ dữ liệu**.

## 7. Timebox trong Scrum: điều gì thực sự được quy định?

Scrum là framework dựa trên kinh nghiệm thực tế với các trụ cột **minh bạch, kiểm tra và thích ứng**. Scrum Guide đưa ra những timebox cụ thể:

| Sự kiện Scrum | Giới hạn theo Scrum Guide | Mục đích |
| --- | --- | --- |
| **Sprint** | **Tối đa một tháng**, thời lượng cố định trong một Sprint | Tạo nhịp để Scrum Team hướng tới Sprint Goal, tạo Increment và kiểm tra/thích ứng |
| **Sprint Planning** | Tối đa **8 giờ cho Sprint một tháng**; Sprint ngắn hơn thường có sự kiện ngắn hơn | Làm rõ vì sao Sprint có giá trị, có thể làm gì và thực hiện như thế nào |
| **Daily Scrum** | **15 phút** | Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch |
| **Sprint Review** | Tối đa **4 giờ cho Sprint một tháng**; thường ngắn hơn với Sprint ngắn | Cùng bên liên quan kiểm tra kết quả Sprint và xác định thích ứng sản phẩm |
| **Sprint Retrospective** | Tối đa **3 giờ cho Sprint một tháng**; thường ngắn hơn với Sprint ngắn | Lập kế hoạch tăng chất lượng và hiệu quả làm việc |

**Đây là giới hạn trên, không phải yêu cầu phải dùng hết thời gian.** Ví dụ nhóm dùng Sprint hai tuần có thể chọn Sprint Planning 2 giờ nếu đủ để làm rõ mục tiêu và kế hoạch; không có quy tắc Scrum bắt buộc “Sprint hai tuần phải Planning chính xác 4 giờ”. Thời lượng thực tế phụ thuộc mức phức tạp và sự chuẩn bị của nhóm.

Ngoài các sự kiện trên:

- **Product Backlog refinement** là hoạt động liên tục để làm rõ và chia nhỏ backlog item, **không phải một sự kiện Scrum có timebox cố định** trong Scrum Guide.
- Sprint mới bắt đầu ngay sau Sprint trước; không cần thêm “tuần nghỉ giữa Sprint”.
- Một Sprint có thể có nhiều Increment; Increment đạt Definition of Done có thể được giao/phát hành **trước khi Sprint kết thúc**.
- **Sprint Goal** là cam kết định hướng, còn phạm vi chi tiết có thể được làm rõ và thương lượng giữa Developers với Product Owner khi biết thêm thông tin.
- Không được giảm chất lượng để ép công việc vào thời lượng Sprint. Hạng mục chưa đạt Definition of Done không được coi là Increment hoàn tất.
- Chỉ Product Owner có thẩm quyền hủy Sprint khi Sprint Goal trở nên lỗi thời; đây không phải cách xử lý thông thường cho mọi sai lệch dự báo nhỏ.

### Vì sao Sprint là một timebox đặc biệt?

Sprint không chỉ là “đặt deadline mỗi hai tuần”. Nó tổ chức một vòng thực nghiệm: có Sprint Goal, kế hoạch, tạo Increment, kiểm tra kết quả và cách làm. Một Sprint kết thúc dù mọi backlog item dự định chưa hoàn thành; nhóm minh bạch phần đã Done, phần chưa Done và điều học được, sau đó lập kế hoạch thực tế cho Sprint tiếp theo.

**Không gọi hạng mục chưa đạt Done là hoàn tất** chỉ để giữ vẻ ngoài “Sprint đúng hạn”. Cách dùng timebox đúng là bảo vệ nhịp kiểm tra, giảm phạm vi khi có lý do và giữ chuẩn chất lượng.

### Daily Scrum không phải buổi điểm danh

Daily Scrum có timebox 15 phút để Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch thực hiện. Nhóm có thể sử dụng câu hỏi “Việc nào cần phối hợp để đạt mục tiêu?” thay vì mặc định từng người báo cho quản lý đã làm gì hôm qua. Những cuộc thảo luận kỹ thuật chi tiết có thể diễn ra ngay sau đó giữa người cần tham gia.

### Sprint Review và Sprint Retrospective cho hai loại phản hồi

Sprint Review kiểm tra **sản phẩm và môi trường sản phẩm** với các bên liên quan để thích ứng Product Backlog. Sprint Retrospective kiểm tra **cách Scrum Team làm việc** để cải thiện chất lượng và hiệu quả. Chúng khác nhau về mục tiêu; gom cả hai thành một buổi “báo cáo tiến độ” thường khiến nhóm bỏ sót cả phản hồi sản phẩm lẫn cải tiến quy trình.

## 8. Kanban: luồng liên tục và các nhịp xem xét có chủ đích

Kanban tập trung vào việc **định nghĩa, trực quan hóa và quản lý luồng công việc**, kiểm soát WIP và cải tiến qua phản hồi. Nhóm dùng Kanban có thể kéo công việc mới khi có năng lực và chính sách cho phép, thay vì chỉ nhận việc ở đầu một Sprint.

~~~mermaid
flowchart LR
    A["Yêu cầu đầu vào"] --> B["Ready / sẵn sàng"]
    B --> C["Đang thực hiện<br/>WIP được giới hạn"]
    C --> D["Kiểm tra và xác nhận<br/>WIP được giới hạn"]
    D --> E["Done / kết quả sẵn sàng"]
    E -. "Dữ liệu flow và phản hồi" .-> F["Điều chỉnh chính sách,<br/>ưu tiên và năng lực"]
    F -.-> B
~~~

Các nhịp phản hồi có thể thiết lập trong cách quản lý Kanban:

| Hoạt động | Câu hỏi | Tần suất có thể cân nhắc |
| --- | --- | --- |
| **Kiểm tra flow hằng ngày** | Việc nào đang già đi, bị chặn, sắp vi phạm kỳ vọng? | Hằng ngày hoặc liên tục qua công cụ |
| **Replenishment / bổ sung công việc** | Khi có năng lực, kéo việc ưu tiên nào vào hệ thống? | Khi đạt điều kiện kéo, hoặc theo buổi ngắn định kỳ |
| **Service delivery review** | Dịch vụ có đáp ứng kỳ vọng thời gian/độ tin cậy không? | Theo tuần hoặc tháng tùy lưu lượng và độ biến thiên |
| **Risk review** | Lớp công việc nào có rủi ro cao, tắc nghẽn hoặc phụ thuộc đáng chú ý? | Theo mốc phù hợp với mức rủi ro |
| **Operations/strategy review** | Luồng và năng lực nhiều dịch vụ có còn phù hợp ưu tiên tổ chức? | Nhịp dài hơn, dựa trên quyết định chiến lược |

Tên gọi và tần suất khác nhau giữa các cách triển khai Kanban. **Không nên hiểu các nhịp trong bảng là toàn bộ những sự kiện bắt buộc giống Scrum.** Điều cần có là cơ hội đủ rõ để quan sát dữ liệu dòng chảy và thay đổi chính sách.

### Chỉ số hỗ trợ chọn nhịp Kanban

- **WIP:** số mục đã bắt đầu nhưng chưa hoàn tất trong ranh giới workflow xác định.
- **Throughput:** số mục hoàn tất trong một khoảng thời gian.
- **Cycle time:** thời gian xử lý từng mục từ điểm bắt đầu đến Done.
- **Work item age:** thời gian một mục đang mở đã tồn tại kể từ điểm bắt đầu đo.
- **Service Level Expectation (SLE):** kỳ vọng về thời gian hoàn thành và xác suất/độ tin cậy, dựa trên bằng chứng lịch sử phù hợp; không nên biến thành lời hứa chắc chắn cho từng mục.

Ví dụ: Nếu phần lớn hạng mục hỗ trợ hoàn tất trong vài ngày nhưng có một số việc kéo dài quá ba tuần do chờ quyền truy cập, nhóm nên theo dõi **work item age trong ngày**, đồng thời đánh giá chính sách cấp quyền theo nhịp dài hơn. Chỉ họp báo cáo mỗi tháng có thể phát hiện điểm nghẽn quá muộn.

### Nhóm Scrum có thể dùng thực hành Kanban không?

Có. Một Scrum Team có thể trực quan hóa các bước, giới hạn WIP, quan sát cycle time và work item age để cải thiện dòng chảy trong Sprint. Nhịp Sprint và trách nhiệm Scrum vẫn được duy trì; các thực hành Kanban hỗ trợ nhóm hoàn thành Increment đều đặn.

## 9. XP: vòng phản hồi kỹ thuật ngắn để hỗ trợ thay đổi

Extreme Programming (XP) nhấn mạnh kỷ luật kỹ thuật, cộng tác và các vòng phản hồi ngắn. Những thực hành của XP bổ sung cho Scrum hoặc Kanban vì **nhóm không thể thích ứng nhanh nếu mỗi thay đổi mã đều dễ gây lỗi**.

| Thực hành | Vòng phản hồi | Kết quả kỳ vọng |
| --- | --- | --- |
| **TDD** | Kiểm thử nhỏ → mã tối thiểu → cải thiện thiết kế; có thể trong vài phút | Phát hiện sớm hiểu sai hành vi và lỗi khi sửa mã |
| **Pair programming** | Phản hồi liên tục giữa hai người cùng giải quyết vấn đề | Chất lượng quyết định kỹ thuật, chia sẻ hiểu biết |
| **Continuous Integration** | Mỗi lần tích hợp hoặc thay đổi đủ điều kiện chạy pipeline | Sớm phát hiện xung đột, kiểm thử hỏng, lỗi tích hợp |
| **Refactoring** | Những bước nhỏ có kiểm thử bảo vệ | Giữ cấu trúc mã dễ thay đổi khi quy tắc nghiệp vụ mở rộng |
| **Small releases** | Phát hành các lát cắt sử dụng được khi an toàn | Nhận phản hồi người dùng sớm, giảm phạm vi rủi ro của từng lần giao |

Các khoảng “vài phút” chỉ là minh họa. Một pipeline lớn có thể cần lâu hơn; mục tiêu là **phản hồi đủ nhanh và đáng tin** để Developers có thể sửa vấn đề khi ngữ cảnh công việc còn mới.

Thực hành XP không thay thế đo outcome sau phát hành. Kiểm thử xanh cho biết mã đáp ứng các trường hợp đã kiểm tra; nó **không chứng minh** người dùng cần chức năng hoặc chức năng giúp học viên học tốt hơn.

## 10. Timebox khám phá: trả lời câu hỏi trước khi đầu tư lớn

Trong lập kế hoạch thích ứng, nhóm có thể dùng timebox cho một **spike**, một phiên phỏng vấn, một prototype hoặc một thí nghiệm kỹ thuật. Điểm chung là giới hạn chi phí tìm hiểu và tạo bằng chứng phục vụ quyết định.

### Ví dụ spike hai ngày

**Vấn đề:** Nhóm chưa biết phải xử lý cập nhật tiến độ cạnh tranh từ hai thiết bị thế nào để tránh mất dữ liệu.

**Quyết định cần hỗ trợ:** Chọn phương án đồng bộ hoặc xác định một ràng buộc kỹ thuật khiến thiết kế hiện tại cần đổi.

**Timebox:** Tối đa hai ngày làm việc; chủ động dừng sớm nếu đã có bằng chứng đủ dùng.

**Phạm vi:** Mô phỏng hai thiết bị cập nhật một bài gần cùng lúc, thử retry và thứ tự nhận thông điệp khác nhau. Không tích hợp toàn bộ giao diện đa thiết bị hoặc triển khai production.

**Đầu ra:** Danh sách kịch bản, kết quả kiểm thử, nhược điểm mỗi phương án, rủi ro chưa giải quyết và đề xuất bước tiếp theo.

**Khi hết thời gian:** Developers cùng người hiểu hệ thống xem xét bằng chứng. Nếu chưa đủ, họ đề xuất **câu hỏi hẹp hơn, thời gian bổ sung, chi phí và hậu quả** để người có thẩm quyền quyết định tiếp; không tự gọi prototype là giải pháp đã hoàn thành.

### Spike khác story như thế nào?

| Tiêu chí | Spike / khám phá giới hạn thời gian | User story giao giá trị |
| --- | --- | --- |
| Mục tiêu | Giảm bất định để ra quyết định | Tạo hành vi/kết quả có ích cho người dùng |
| Đầu ra | Bằng chứng, hiểu biết, rủi ro, lựa chọn | Phần sản phẩm sử dụng được đạt tiêu chuẩn Done |
| Ranh giới | Câu hỏi cụ thể và giới hạn thời gian | Hành vi, quy tắc và tiêu chí chấp nhận |
| Nếu hết timebox mà chưa đủ | Ghi điều biết/chưa biết; quyết định bước khám phá mới | Chỉ công nhận phần thực sự Done; điều chỉnh phạm vi/kế hoạch |

Không cần gọi mọi công việc kỹ thuật chưa rõ là spike. Nếu có thể kiểm chứng rủi ro **trong một lát cắt giá trị nhỏ**, cách đó thường tạo thêm phản hồi từ người dùng so với một prototype chỉ dùng nội bộ.

## 11. Chọn độ dài timebox bằng đánh đổi có kiểm chứng

Timebox ngắn giúp phản hồi thường xuyên nhưng làm tăng tần suất chuyển nhịp và nhu cầu chia nhỏ việc. Timebox dài giảm số lần lập kế hoạch hình thức nhưng có thể làm chậm phát hiện sai hướng.

| Khi nhịp quá ngắn | Khi nhịp quá dài |
| --- | --- |
| Nhóm dành quá nhiều thời gian lập kế hoạch, review và chuyển trạng thái | Giả định sai tồn tại lâu trước khi được kiểm tra |
| Công việc lớn bị chia vụn thành ticket kỹ thuật chưa tạo giá trị | Phạm vi tăng, rủi ro tích lũy và phản hồi đến muộn |
| Người dùng/bên liên quan chưa đủ thời gian trải nghiệm để cho phản hồi hữu ích | Cơ hội điều chỉnh ưu tiên bị bỏ lỡ |
| Các đo lường có cửa sổ dài bị đánh giá vội vàng | Vấn đề chất lượng hoặc phụ thuộc có thể chỉ lộ ra sát cuối chu kỳ |

### Quy trình lựa chọn nhịp

1. **Liệt kê quyết định cần phản hồi:** quy tắc nghiệp vụ, kiến trúc, nhu cầu người dùng, chất lượng vận hành hay chiến lược.
2. **Định nghĩa bằng chứng hữu ích:** ví dụ kiểm thử kỹ thuật ngay trong ngày, phiên usability test sau prototype, dữ liệu retention sau bảy ngày.
3. **Ước lượng độ trễ hiện tại:** mất bao lâu từ lúc xuất hiện câu hỏi đến lúc có bằng chứng đủ dùng?
4. **Chọn timebox và kênh phản hồi:** ưu tiên tạo vòng học ngắn nhất có ích với rủi ro và chi phí chấp nhận được.
5. **Thử trong vài chu kỳ:** quan sát chất lượng Increment, khả năng đạt mục tiêu, thời gian chờ và phản hồi của người tham gia.
6. **Điều chỉnh dựa trên bằng chứng:** đổi thời lượng, cách chuẩn bị, số người tham gia hoặc cách lấy phản hồi nếu nhịp đang không hiệu quả.

**Đừng chỉ hỏi “Sprint nên dài một hay hai tuần?”** Hỏi thêm: “Lát cắt sản phẩm có đủ nhỏ để hoàn tất không?”, “Bên liên quan có tham gia được không?”, “Chúng ta có thể biết được điều gì sau mỗi chu kỳ?” và “Năng lực kiểm thử/phát hành có hỗ trợ nhịp này không?”.

## 12. Ví dụ lập lịch: nhóm Scrum hai tuần phát triển tính năng “Học tiếp”

Lịch dưới là **minh họa**, không phải công thức bắt buộc. Nhóm giả sử dùng Sprint hai tuần (10 ngày làm việc), có Product Owner, Scrum Master và Developers, sử dụng CI và phản hồi người học khi có lát cắt thử được.

| Thời điểm minh họa | Hoạt động và giới hạn | Phản hồi/đầu ra cần có |
| --- | --- | --- |
| **Ngày 1** | Sprint Planning có timebox phù hợp; xác định Sprint Goal và kế hoạch | Sprint Goal: học viên đã đăng nhập quay lại đúng bài dở trong phạm vi an toàn |
| **Mỗi ngày làm việc** | Daily Scrum 15 phút; Developers phối hợp thêm khi cần | Kịp phát hiện chặn việc và cập nhật cách đạt Sprint Goal |
| **Mỗi thay đổi mã** | CI, kiểm thử tự động và review theo chính sách nhóm | Phản hồi nhanh về tính đúng đắn và khả năng tích hợp |
| **Ngày 2–3** | Prototype hoặc lát cắt nhỏ; phiên quan sát người dùng theo lịch đã thống nhất | Học viên có tìm thấy nút và hiểu cách tiếp tục học không? |
| **Ngày 4–6** | Hoàn thiện Increment và kiểm thử; dùng bảng workflow theo giới hạn WIP phù hợp | Hành vi đạt acceptance criteria và Definition of Done |
| **Khi Increment sẵn sàng** | Phát hành có kiểm soát theo điều kiện vận hành | Dữ liệu hành vi, lỗi và phản hồi sớm từ nhóm dùng thử |
| **Ngày 7–9** | Quan sát kết quả đã có, refine backlog; quyết định phần tiếp theo theo dữ liệu | Nêu rõ điều đã biết, giả định chưa kiểm chứng và rủi ro |
| **Ngày 10** | Sprint Review và Sprint Retrospective có timebox phù hợp | Thích ứng Product Backlog; chọn cải tiến cách làm cho Sprint sau |

Nếu chỉ số sản phẩm là “tỷ lệ quay lại trong bảy ngày”, học viên mới được đưa vào thử ở ngày 9 **chưa có đủ cửa sổ quan sát** khi Sprint kết thúc ngày 10. Nhóm cần tiếp tục theo dõi sau Sprint, không tuyên bố outcome đã được chứng minh chỉ để có con số ở Sprint Review.

### Ba loại công việc có thể diễn ra song song

~~~text
Trong Sprint hai tuần:
  Phát triển:  [lát cắt A] → [lát cắt B] → kiểm tra/Done
  Chất lượng: [CI & kiểm thử lặp lại ở mỗi thay đổi...]
  Phản hồi:   [usability] → [thử dùng] → [dữ liệu đủ cửa sổ]
                                           ↘ có thể sau Sprint
~~~

Timebox của Sprint bảo đảm **mốc xem xét và điều chỉnh kế hoạch**; nó không ép tất cả thông tin từ thị trường phải xuất hiện đúng ngày cuối Sprint.

## 13. Ví dụ khác: đội hỗ trợ theo Kanban không có Sprint cố định

Một nhóm phụ trách lỗi và yêu cầu hỗ trợ nền tảng có công việc đến không đều, trong đó có sự cố cần xử lý ngay. Nếu ép toàn bộ công việc vào Sprint hai tuần, việc ưu tiên khẩn có thể làm Sprint Goal liên tục không ổn định. Nhóm cân nhắc quản lý theo Kanban:

- **Khi nhận yêu cầu:** Phân loại tác động, điều kiện khẩn cấp và mức độ rủi ro theo chính sách công khai.
- **Khi có năng lực:** Kéo việc ưu tiên từ Ready, giữ giới hạn WIP và tránh khởi động thêm quá nhiều việc.
- **Hằng ngày:** Kiểm tra item già đi, công việc bị chặn và các trường hợp cần hỗ trợ giữa vai trò.
- **Hằng tuần hoặc hai tuần:** Xem phân bố cycle time, lý do chờ và phản hồi người yêu cầu để thử cải tiến workflow.
- **Hằng tháng hoặc khi cần quyết định lớn:** Xem nhu cầu năng lực, rủi ro vận hành và cải tiến có thể cần quản lý cấp tổ chức.

Nhịp trên là **quy ước gợi ý**, điều chỉnh theo số lượng việc và mức độ biến thiên. Dòng công việc có thể liên tục dù nhóm vẫn có những **timebox ngắn cho giải quyết sự cố, điều tra nguyên nhân, review chính sách hoặc thử nghiệm kỹ thuật**.

### Một ngày có sự cố

Giả sử hệ thống lỗi lưu tiến độ khiến người dùng mất dữ liệu. Nhóm không chờ đến buổi replenishment tiếp theo; chính sách xử lý khẩn cấp kích hoạt ngay, ưu tiên khôi phục an toàn và thông báo người có trách nhiệm. Sau sự cố, nhóm có thể timebox một phiên hậu kiểm để xác định các điều kiện dẫn đến lỗi và hành động phòng ngừa.

Điều này minh họa rằng **nhịp định kỳ là mặc định cho công việc bình thường, không thay thế cơ chế phản ứng theo sự kiện nghiêm trọng**.

## 14. Đo hiệu quả nhịp phản hồi bằng dữ liệu phù hợp

Không nên đánh giá timebox chỉ bằng tỷ lệ cuộc họp kết thúc đúng giờ. Hãy xem liệu nó có giúp nhóm **phát hiện vấn đề sớm, quyết định nhanh và giao giá trị an toàn hơn**.

| Góc nhìn | Cách quan sát | Điều có thể học |
| --- | --- | --- |
| **Thời gian chờ phản hồi** | Khoảng từ lúc cần quyết định đến lúc nhận bằng chứng đủ dùng | Người có thông tin hoặc quy trình nào đang làm chậm việc học? |
| **Thời gian hoàn tất công việc** | Cycle time theo loại việc và ranh giới nhất quán | Timebox có đang kèm theo việc chia nhỏ, giảm chờ và hoàn thành nhanh hơn? |
| **Khả năng dự báo** | Phân bố cycle time, tỷ lệ hoàn tất mục tiêu, lý do mục chưa Done | Cam kết có phù hợp năng lực và bất định không? |
| **Chất lượng kỹ thuật** | Lỗi hồi quy, lỗi production, độ tin cậy CI, thời gian phục hồi | Tăng nhịp có làm giảm chất lượng hay tăng việc làm lại không? |
| **Giá trị sản phẩm** | Tỷ lệ hoàn thành tác vụ, retention, phản hồi khả dụng theo phân khúc | Các lát cắt có giải quyết vấn đề người dùng hay không? |
| **Chi phí phối hợp** | Thời gian họp, số người tham gia, số quyết định hoặc vấn đề được tháo gỡ | Buổi nào đang quá dày, thiếu thông tin hoặc có thể chuyển sang bất đồng bộ? |
| **Nhịp làm việc bền vững** | Gián đoạn, làm thêm giờ thường xuyên, công việc chuyển chu kỳ, phản hồi nhóm | Cách tổ chức có tạo áp lực không bền vững không? |

### Ví dụ đo phản hồi sau khi đổi nhịp

Giả sử nhóm thay phiên review sản phẩm mỗi tháng thành **review lát cắt với người dùng mỗi tuần khi có bản thử**. Trước thay đổi, một vấn đề giao diện thường chỉ được phát hiện sau 20 ngày; sau vài chu kỳ, nhiều vấn đề được phát hiện trong 5–7 ngày. Đây là tín hiệu tốt về **độ trễ học hỏi**. Nhưng cần tiếp tục kiểm tra:

- Mẫu người dùng có phù hợp không?
- Buổi review có tạo quyết định hoặc thay đổi backlog không?
- Có phát hiện sớm hơn nhưng phát hành chậm hơn do họp quá nhiều không?
- Lỗi, nợ kỹ thuật và kết quả học tập có bị ảnh hưởng không?

Các số trong ví dụ là **giả định minh họa**, chưa chứng minh một công thức cải tiến chung. Khi thay đổi độ dài Sprint hoặc cách tách story, các chỉ số flow cũng có thể đổi ý nghĩa; nhóm phải chú thích và so sánh có bối cảnh.

## 15. Khi timebox hết mà công việc chưa xong

Đây là thời điểm thể hiện rõ nhất liệu nhóm hiểu timebox đúng hay không. Các bước xử lý:

1. **Nêu trạng thái thật:** phần nào đã đạt acceptance criteria và Definition of Done, phần nào chưa; không đổi nhãn chỉ để báo cáo đẹp.
2. **Bảo vệ tiêu chuẩn bắt buộc:** kiểm thử quan trọng, phân quyền, tính đúng đắn dữ liệu, yêu cầu vận hành và tuân thủ không bị bỏ qua.
3. **Kiểm tra mục tiêu:** mục tiêu học hỏi hoặc Sprint Goal đã đạt chưa? Điều gì còn rủi ro?
4. **Phân loại nguyên nhân:** việc quá lớn, giả định sai, nhiều phụ thuộc, sự cố phát sinh, nguồn lực thay đổi hay thiếu kỹ năng?
5. **Chọn hành động:** thu hẹp hoặc tách phần còn lại, làm rõ thêm, thay đổi thứ tự backlog, bổ sung năng lực hoặc điều chỉnh cam kết tương lai.
6. **Đưa bài học vào nhịp kế tiếp:** thay cách chuẩn bị, giới hạn WIP, thử phương pháp học sớm hơn hoặc xem lại thời lượng timebox nếu cần.

### Ví dụ với Sprint

Sprint Goal là “Học viên có thể tiếp tục bài đang dở”. Đến cuối Sprint, Developers đã có giao diện nhưng đường dẫn đôi khi hiển thị tiến độ của phiên đăng nhập cũ. Không thể gọi Increment đó Done hoặc phát hành cho người dùng rộng chỉ để đáp ứng mốc. Nhóm nêu rủi ro trung thực trong Sprint Review, hoàn thiện hoặc điều chỉnh backlog trong kỳ tiếp theo theo quyết định của Product Owner và Developers, đồng thời cải thiện cơ chế kiểm thử.

### Ví dụ với spike

Spike hai ngày chưa xác định được cơ chế đồng bộ an toàn. Kết quả hợp lệ là: “Đã loại trừ phương án A qua trường hợp ghi đè; phương án B có triển vọng nhưng cần thử khi mất kết nối; đề xuất thêm một ngày với kịch bản rõ”. Người có trách nhiệm đánh đổi chi phí và rủi ro để quyết định có duyệt bước khám phá mới hay thay chiến lược.

**Hết timebox là điểm quyết định, không phải phép màu biến phần chưa đủ chất lượng thành công việc hoàn thành.**

## 16. Những sai lầm phổ biến

### 16.1. Xem timebox như deadline phải hoàn thành mọi thứ

Timebox giới hạn hoạt động và tạo mốc phản hồi; các tiêu chuẩn an toàn không mất hiệu lực khi hết giờ. Nếu nội dung quá lớn, giảm phạm vi thành lát cắt tạo giá trị, không “đẩy Done giả”.

### 16.2. Sprint ngắn hơn chắc chắn tạo nhiều giá trị hơn

Nếu CI chậm, quy tắc chưa rõ và không có lát cắt sử dụng được, Sprint một tuần chỉ làm nhóm lập kế hoạch thường xuyên hơn. Nhịp cần phù hợp năng lực tạo Increment và nhận bằng chứng.

### 16.3. Dùng Sprint Review như lễ báo cáo hoàn thành nhiệm vụ

Sprint Review cần quan sát kết quả và môi trường sản phẩm với các bên liên quan, sau đó điều chỉnh ưu tiên. Báo số ticket không thay thế được phản hồi về giá trị.

### 16.4. Cho rằng có Daily Scrum thì mọi trở ngại sẽ tự biến mất

Daily Scrum giúp Developers nhìn và điều chỉnh kế hoạch; điểm nghẽn về quyền truy cập, phê duyệt, nhân sự hoặc công cụ có thể cần sự tham gia của quản lý và bộ phận liên quan.

### 16.5. Tổ chức phản hồi quá dày mà không có bằng chứng mới

Mời người dùng họp mỗi ngày khi sản phẩm chưa thay đổi hoặc câu hỏi không rõ thường gây mệt mỏi. Nhịp tốt là **khi có điều đáng học và đủ dữ liệu để thảo luận**.

### 16.6. Chỉ chờ cuộc họp định kỳ mới sửa vấn đề khẩn cấp

Sự cố bảo mật, lỗi mất dữ liệu hoặc vấn đề khách hàng nghiêm trọng cần cơ chế xử lý theo rủi ro, không chờ Sprint Review hoặc buổi service delivery review.

### 16.7. Dùng timebox để né câu hỏi khó

Kết thúc cuộc thảo luận đúng giờ nhưng không ghi quyết định, người phụ trách và câu hỏi còn mở sẽ làm công việc bị lặp lại. Cần dùng phần cuối timebox để chốt **điều đã biết, điều chưa biết và bước tiếp theo**.

### 16.8. Đánh đồng cadence và tốc độ làm việc của từng cá nhân

Nhiều lần họp hơn hoặc nhiều ticket Done hơn không chứng minh năng suất cao. Nên quan sát outcome, flow, chất lượng và sự bền vững; tránh xếp hạng cá nhân từ cycle time hay story point.

### 16.9. Đo outcome khi chưa đủ cửa sổ quan sát

Một thử nghiệm muốn đánh giá retention bảy ngày cần đủ bảy ngày theo dõi cho những người tham gia phù hợp. Không được thay “số người mở trang trong hai giờ” thành kết luận về retention chỉ vì timebox sắp hết.

### 16.10. Chọn nhịp rồi không bao giờ xem lại

Nhịp phù hợp khi nhóm có bốn người và sản phẩm còn mới có thể không còn tốt khi nhóm phát triển, phụ thuộc thay đổi hoặc công việc chuyển sang vận hành. Cần định kỳ đánh giá cơ chế đang dùng bằng bằng chứng thực tế.

## 17. Bài tập thực hành

### Bài tập A — Phân biệt khái niệm

Phân loại từng phát biểu:

1. “Dành tối đa 60 phút để làm rõ ba story ưu tiên.”
2. “Mỗi sáng Developers kiểm tra cách đạt Sprint Goal trong 15 phút.”
3. “Một ticket mất 3,5 ngày từ lúc bắt đầu làm tới Done.”
4. “Bên đối tác cần bản báo cáo trước 17:00 thứ Sáu.”
5. “Ngay khi có tính năng thử được, nhóm mời năm học viên phù hợp thực hiện tác vụ.”

**Gợi ý:** (1) timebox; (2) vừa là timebox của Daily Scrum vừa thuộc nhịp hằng ngày; (3) cycle time nếu ranh giới đo rõ; (4) deadline; (5) vòng phản hồi theo sự kiện có giá trị, không nhất thiết theo lịch cố định.

### Bài tập B — Thiết kế timebox khám phá

Tình huống: Nhóm định thêm nhắc học qua ứng dụng nhưng chưa biết học viên có thực sự muốn nhận thông báo.

Hãy điền:

~~~text
Giả định cần kiểm chứng:
Đối tượng người học:
Quyết định cần hỗ trợ:
Timebox tối đa:
Phương pháp quan sát/thử nghiệm:
Sản phẩm đầu ra:
Giới hạn an toàn và quyền riêng tư:
Khi nào đủ bằng chứng để tiếp tục:
Nếu chưa đủ bằng chứng thì làm gì:
~~~

**Gợi ý:** Có thể bắt đầu bằng phỏng vấn tình huống đã xảy ra và prototype thông báo; nếu cần chứng minh tác động hành vi, phải thiết kế phép đo có nhóm so sánh hoặc phương pháp phù hợp hơn. Đừng tuyên bố “người dùng thích” chỉ vì vài người nói “có thể hữu ích”.

### Bài tập C — Chọn nhịp cho ba nhóm khác nhau

| Nhóm | Bối cảnh | Nhịp cần đề xuất |
| --- | --- | --- |
| **A** | Xây sản phẩm mới; nhiều giả định giá trị; nhóm liên chức năng và tiếp xúc được người dùng | Chọn độ dài Sprint hoặc timebox học hỏi; giải thích khi nào kiểm tra outcome |
| **B** | Xử lý lỗi sản xuất và yêu cầu hỗ trợ đến liên tục, thay đổi độ khẩn thường xuyên | Chọn workflow, WIP, cách replenishment và phản ứng theo sự cố |
| **C** | Làm tính năng xử lý dữ liệu nhạy cảm, kiểm thử tích hợp tốn thời gian | Chọn nhịp CI và kiểm chứng rủi ro, thời gian review tuân thủ, cơ chế giao phần nhỏ an toàn |

Hãy trả lời **vì sao chọn nhịp ấy, tín hiệu nào cho thấy nhịp không hiệu quả và khi nào phải điều chỉnh**. Không có một tần suất đúng cho mọi tình huống.

### Bài tập D — Khi kết thúc timebox không có Increment

Một nhóm đặt Sprint hai tuần để phát hành chức năng “Học tiếp”. Cuối Sprint, giao diện hoạt động nhưng dữ liệu tiến độ của hai thiết bị còn có nguy cơ ghi đè sai.

1. Hạng mục này có thể coi là Done không? Vì sao?
2. Có thể trình bày điều gì tại Sprint Review một cách trung thực?
3. Developers, Product Owner và các bên liên quan cần quyết định gì về phạm vi và ưu tiên kế tiếp?
4. Nhóm nên thay đổi cách chia story, kiểm thử hoặc giới hạn WIP ra sao?
5. Nếu muốn rút ngắn Sprint từ hai tuần xuống một tuần, bằng chứng nào cần có trước khi quyết?

**Gợi ý:** Không gọi Increment Done nếu chưa đáp ứng Definition of Done. Có thể trình bày bài học, rủi ro và phần đã thực hiện mà không tuyên bố hoàn thành. Tối ưu nhịp phải đi cùng cách chia lát cắt và chất lượng, không chỉ thay con số “hai” thành “một”.

## 18. Checklist áp dụng trong nhóm

- [ ] Nêu rõ **quyết định hoặc kết quả** mà timebox cần hỗ trợ.
- [ ] Đặt **giới hạn thời gian** và người có trách nhiệm chốt bước tiếp theo.
- [ ] Nêu **phạm vi có thể thay đổi** và **tiêu chuẩn chất lượng không được bỏ qua**.
- [ ] Xác định **sản phẩm đầu ra hoặc bằng chứng** có thể đọc/kiểm tra.
- [ ] Phân biệt **deadline, timebox, cadence, cycle time và lead time**.
- [ ] Chọn nhịp dựa trên **độ bất định, rủi ro, tốc độ tạo bằng chứng và chi phí phối hợp**.
- [ ] Thiết lập vòng phản hồi kỹ thuật đủ nhanh và đáng tin.
- [ ] Có cách nhận phản hồi người dùng **trước khi tích lũy quá nhiều chức năng chưa kiểm chứng**.
- [ ] Không chờ cuộc họp định kỳ khi có sự cố hoặc rủi ro nghiêm trọng cần xử lý ngay.
- [ ] Nếu dùng Scrum, bảo vệ **Sprint Goal, Definition of Done và các timebox sự kiện**.
- [ ] Nếu dùng Kanban, quan sát **flow, WIP, work item age và chính sách kéo việc**.
- [ ] Chỉ đánh giá các chỉ số sản phẩm khi **cửa sổ quan sát và chất lượng dữ liệu** đủ phù hợp.
- [ ] Khi timebox hết, ghi **điều đã học, công việc chưa Done và quyết định tiếp theo**.
- [ ] Có mốc đánh giá lại xem nhịp hiện tại có tạo phản hồi hữu ích và bền vững không.

## 19. Tài liệu đọc tiếp và điểm cần nhớ

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 nguyên tắc](https://agilemanifesto.org/principles.html): giao phần mềm sớm, hợp tác thường xuyên, phản hồi và cải tiến.
- [The Scrum Guide](https://scrumguides.org/): Sprint và các timebox Scrum chính thức; trách nhiệm của Scrum Team, Sprint Goal, Increment và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/): định nghĩa và quản lý workflow, WIP, SLE, cycle time và các số đo dòng chảy.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): những thực hành phát triển phần mềm dựa trên phản hồi kỹ thuật nhanh, hợp tác và chất lượng.

**Điều cốt lõi:** Timebox hữu ích khi nhóm dùng **giới hạn thời gian để tập trung, học và ra quyết định**, còn nhịp phản hồi hữu ích khi giúp **phát hiện sớm điều cần thay đổi**. Một cách lập kế hoạch thích ứng tốt kết hợp những vòng phản hồi nhanh phù hợp với từng loại công việc, giữ tiêu chuẩn chất lượng và cập nhật kế hoạch bằng bằng chứng thực tế thay vì cố bảo vệ dự báo ban đầu.
