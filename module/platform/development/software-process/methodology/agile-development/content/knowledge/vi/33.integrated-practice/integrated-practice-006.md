# Lập kế hoạch ngắn hạn theo năng lực, phụ thuộc và bất định

Một nhóm xây nền tảng học trực tuyến muốn hoàn thành luồng ghi danh mới trong hai tuần. Product Owner đưa ra sáu Product Backlog Items (PBIs) đều có giá trị; Developers ước lượng khối lượng trung bình khoảng 40 ngày công, trong khi cả nhóm có năm người và Sprint dài mười ngày làm việc. Người quản lý kết luận: “Năm người nhân mười ngày bằng 50 ngày công, vậy tất cả sẽ xong.”

Nhưng hai Developers nghỉ phép một phần thời gian, một người trực hỗ trợ production, môi trường kiểm thử chưa ổn định và API thanh toán mới phụ thuộc nhà cung cấp chưa xác nhận hợp đồng. Đến gần cuối Sprint, cả sáu PBIs đều ở trạng thái đang làm, không có lát cắt nào đáp ứng Definition of Done (DoD). Nhóm **bận rộn** nhưng học viên **chưa sử dụng được chức năng**.

Sai lầm không chỉ nằm ở phép tính số ngày. Kế hoạch đã trộn lẫn:

- **Năng lực danh nghĩa:** số người nhân số ngày trên lịch.
- **Năng lực thực tế:** thời gian và chuyên môn có thể dành cho công việc trong khoảng đang xét.
- **Phụ thuộc:** điều kiện phải có từ nhóm khác, dịch vụ, quyết định hoặc nhà cung cấp.
- **Bất định:** những điều chưa biết có thể khiến công việc, giải pháp và thứ tự ưu tiên đổi.
- **Mức hoàn tất:** code hoặc task xong chưa chắc tạo Increment có thể sử dụng.

Một kế hoạch Agile ngắn hạn tốt không nhằm làm mọi người bận kín 100%. Nó cần giúp đội **chọn kết quả có giá trị, giới hạn việc bắt đầu, thấy điều kiện và rủi ro sớm, tạo phần mềm đáp ứng chất lượng, rồi điều chỉnh khi có bằng chứng mới**.

Bài thuộc chương **Thực hành tổng hợp** của module **AGILE_DEVELOPMENT**. Module hướng tới hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng, giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục; kết hợp user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp. Vì vậy bài này không chỉ dạy tính ngày công, mà ghép **product goal, backlog refinement, capacity, phụ thuộc, rủi ro, Sprint Planning, Kanban flow và chất lượng kỹ thuật** thành một bài thực hành hoàn chỉnh.

> **Thông điệp cốt lõi:** Kế hoạch ngắn hạn là **giả thuyết có căn cứ về cách đạt mục tiêu**, không phải một lời hứa rằng mọi ước lượng đều chính xác. Bảo vệ mục tiêu, chất lượng và khả năng học quan trọng hơn lấp đầy hết capacity hoặc “đóng” nhiều ticket.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **capacity danh nghĩa, capacity khả dụng, năng lực theo kỹ năng, demand, throughput và khả năng hoàn tất**.
2. Lập bảng capacity thực tế theo kỳ ngắn, xét nghỉ phép, hỗ trợ production, trách nhiệm liên đội và các khoản thời gian không thể dùng cho PBI mới, tránh tính trùng.
3. Nhận diện, mô hình hóa và ưu tiên xử lý **phụ thuộc nội bộ, xuyên nhóm, bên ngoài, quyết định, dữ liệu và môi trường**.
4. Phân biệt **rủi ro có thể liệt kê** với **bất định chưa biết**, dùng khoảng ước lượng, kịch bản và giả định rõ thay vì hứa một ngày chắc chắn.
5. Từ Product Goal và Product Backlog, chia một công việc thành **lát cắt dọc có giá trị**, định nghĩa acceptance criteria/DoD và lựa chọn phạm vi dự kiến theo năng lực.
6. Thực hiện **Sprint Planning theo Scrum Guide 2020**: vì sao Sprint có giá trị, làm gì có thể Done, sẽ làm thế nào; giữ Sprint Goal và trách nhiệm Developers/Product Owner đúng bản chất.
7. Áp dụng **Kanban WIP, work item age, throughput, cycle time và policies** để giúp kế hoạch ngắn hạn không biến thành danh sách bắt đầu thật nhiều việc.
8. Xử lý thay đổi giữa kỳ: sự cố, API chậm, giả định sai, thiếu năng lực, thay đổi giá trị; biết khi nào giảm phạm vi, chia lát cắt, điều chỉnh kế hoạch hoặc escalation.
9. Thiết kế tín hiệu kiểm chứng bằng **Increment, chất lượng, flow và outcome** thay vì so story points với giờ làm hay đo mức bận rộn của cá nhân.
10. Tự lập và phản biện một kế hoạch hai tuần từ tình huống nhiều PBIs, năm Developers và các phụ thuộc thực tế.

## 1. Kế hoạch ngắn hạn trong Agile nhằm trả lời những câu hỏi nào?

Lập kế hoạch không mất đi khi dùng Agile. Điểm khác là đội **không giả định mọi chi tiết tương lai đã biết ngay từ đầu** và tạo những điểm kiểm tra để cập nhật lựa chọn theo phản hồi.

### 1.1. Sáu câu hỏi của một kế hoạch có ích

| Câu hỏi | Ý nghĩa | Ví dụ trong nền tảng học |
|---|---|---|
| **Vì sao?** | Mục tiêu giá trị hoặc rủi ro quan trọng | Học viên đủ điều kiện tự ghi danh và vào bài đầu |
| **Điều gì?** | Lát cắt/hành vi có thể hoàn tất, kiểm chứng được | Ghi danh khóa miễn phí, cấp quyền đúng, vào bài đầu |
| **Bằng năng lực nào?** | Thời gian và kỹ năng khả dụng thật | Developers có 33 ngày công khả dụng, nhưng kỹ năng API không thể thay bằng UI |
| **Phụ thuộc vào đâu?** | Điều kiện và quyền cần để hoàn tất | Contract entitlement, test environment, quyết định Product Owner |
| **Còn chưa biết gì?** | Bất định và các kịch bản có thể thay đổi | Tình huống callback lặp hoặc chính sách thanh toán chưa rõ |
| **Kiểm chứng và điều chỉnh ra sao?** | Definition of Done, quan sát và hành động | CI, integration tests, Sprint Review, work item age |

Nếu thiếu câu thứ nhất, đội có thể hoàn tất nhiều ticket không tạo giá trị. Nếu thiếu câu cuối, kế hoạch dễ thành bảng thành tích không phản ánh sản phẩm thật.

### 1.2. Ba tầng kế hoạch không nên trộn

**Định hướng sản phẩm:** kết quả dài hơn mà tổ chức muốn tạo; trong Scrum là Product Goal cùng Product Backlog liên tục được làm rõ và sắp thứ tự.

**Kế hoạch kỳ ngắn:** một mục tiêu và những PBI/lát cắt có triển vọng hoàn tất với capacity, dependency và rủi ro hiện có; nếu dùng Scrum là Sprint Goal cùng Sprint Backlog.

**Kế hoạch công việc hằng ngày:** Developers quyết định bước thực hiện, kiểm thử, phối hợp, gỡ blocker và thay đổi thứ tự kỹ thuật để tiến gần mục tiêu; nếu dùng Scrum, Daily Scrum giúp inspect/adapt Sprint Backlog.

Khi một kế hoạch quý bị chi tiết hóa đến từng task và từng ngày rồi áp xuống Sprint, **độ linh hoạt chỉ còn ở tên gọi**. Ngược lại, nếu chỉ có mục tiêu dài hạn mà không chọn lát cắt cụ thể, đội khó phối hợp và đo tiến triển.

### 1.3. Mục tiêu và phạm vi là hai thứ khác nhau

Ví dụ:

- **Mục tiêu:** “Học viên có thể ghi danh khóa miễn phí hợp lệ và vào bài đầu an toàn.”
- **Các PBI dự kiến:** validate yêu cầu, lưu ghi danh, tạo entitlement đúng, UI xác nhận, kiểm tra quyền, telemetry.
- **Task kỹ thuật:** cập nhật API, migration, fixture, test contract, cấu hình CI.

Khi phát hiện cần đổi API để đảm bảo tính đúng đắn, đội có thể **điều chỉnh task** mà không thay mục tiêu. Khi capacity giảm, đội có thể thương lượng **phạm vi chi tiết** theo thẩm quyền. Nhưng không thể âm thầm hạ DoD rồi gọi một chức năng chưa dùng được là Done.

### 1.4. Một kế hoạch là tập hợp giả định có thể kiểm chứng

Một dự báo ngắn hạn ngầm giả định:

- Người và kỹ năng dự kiến thực sự sẵn sàng.
- Các điều kiện bên ngoài đến đúng lúc hoặc có phương án thay thế.
- PBI được hiểu đủ để chọn lát cắt hợp lý.
- Môi trường/test cho phép xác nhận DoD.
- Không có sự cố bất thường vượt quá mức đội có thể hấp thụ.
- Product Goal và ưu tiên chưa bị thay đổi căn bản.

Hãy **viết rõ giả định ảnh hưởng lớn**, không cố ghi mọi điều nhỏ. Khi một giả định sai, đội biết lý do phải kiểm tra và điều chỉnh kế hoạch.

## 2. Phân biệt capacity, demand, effort, thời gian trôi qua và throughput

Các khái niệm này thường bị trộn trong buổi lập kế hoạch, dẫn tới lời hứa không thể kiểm chứng.

### 2.1. Bảng thuật ngữ thực hành

| Khái niệm | Diễn giải | Đơn vị minh họa | Không đồng nghĩa với |
|---|---|---|---|
| **Gross capacity** | Tổng thời gian lao động theo lịch trước khi trừ các khoản đã biết | Person-days hoặc giờ | Số ngày có thể làm PBI mới |
| **Net/available capacity** | Phần thời gian khả dụng cho phạm vi công việc đã định sau khi trừ các nghĩa vụ không trùng lặp | Person-days hoặc giờ | Cam kết chắc chắn sẽ hoàn tất từng PBI |
| **Skill-constrained capacity** | Khả năng thực tế theo kỹ năng, quyền và phụ thuộc | Số người/khung thời gian thuộc kỹ năng | Tổng số ngày công có thể hoán đổi tự do |
| **Effort estimate** | Ước lượng lượng công sức cần bỏ ra | Person-days, giờ, khoảng hoặc size | Elapsed lead time/cycle time |
| **Elapsed time** | Thời gian lịch từ mốc đầu đến mốc cuối, gồm chờ | Calendar days | Tổng số ngày công của nhiều người |
| **Throughput** | Số work items thực sự hoàn tất trong một kỳ theo định nghĩa | PBI/tuần | Story points hoặc công việc mới bắt đầu |
| **WIP** | Số work items đã bắt đầu nhưng chưa Done | Items | Workload hoàn tất |
| **Work item age** | Thời gian một item chưa Done đã ở trong workflow | Giờ/ngày | Thời gian ước lượng còn lại |
| **Cycle time** | Thời gian từ Started đến Finished của item Done | Giờ/ngày | Thời gian làm tay thuần |

Trong Kanban, các metrics cần **Definition of Workflow** và điểm Started/Finished thống nhất. Một item bị blocked nhưng chưa Finished thường vẫn là WIP trong boundary; không chuyển ra ngoài chỉ để biểu đồ đẹp.

### 2.2. Không đồng nhất story points và ngày công

Story points, nếu đội sử dụng, là thang ước lượng tương đối phản ánh cách đội cảm nhận độ lớn/độ phức tạp/bất định theo quy ước của mình. Chúng **không phải đơn vị giờ hay ngày công phổ quát**.

Các phép suy luận sau thiếu cơ sở:

> “Sprint trước đội hoàn thành 30 points trong 60 ngày công, vậy 1 point = 2 ngày công; Sprint này có 35 ngày công thì chắc chắn được 17,5 points.”

Vì sự biến động của loại việc, độ khó, phụ thuộc, khả năng chia PBI và cách estimate, tỷ lệ đó **không ổn định như hằng số vật lý**. Velocity có thể giúp đội dự báo theo lịch sử tương đối ổn định nhưng không nên dùng để quy đổi chính xác ra lịch, so cá nhân hoặc ép tăng output.

Trong bài thực hành, ta dùng **person-days chỉ như một cách minh họa capacity và effort ranges**. Đây không phải yêu cầu Scrum phải ước lượng bằng ngày công. Khi có dữ liệu flow tốt, đội có thể dự báo dựa vào throughput/cycle time thay vì quy đổi story points.

### 2.3. Năm người không tạo một “người 50 ngày”

Nếu mỗi người có 10 ngày theo lịch:

\[
C_{\text{gross}} = 5 \times 10 = 50\ \text{person-days}
\]

Nhưng:

- Một Developer API có thể không thay ngay tester đang kiểm chứng quyền.
- Năm người không thể cùng làm tuần tự một bước migration một ngày để biến nó thành 0,2 ngày.
- Một PBI chờ đối tác ba ngày lịch có thể không cần ba ngày công, nhưng vẫn kéo dài cycle time.
- Pair programming có hai người cùng làm; không nên tính năng lực như hai công việc độc lập đang chạy song song nếu mục tiêu là cùng tạo chất lượng và chia sẻ kỹ năng.

Tổng capacity là **ràng buộc cần thiết nhưng chưa đủ** để kết luận một kế hoạch khả thi. Còn phải xét **trình tự, concurrency, người có kỹ năng và điều kiện bắt buộc**.

### 2.4. “Hiệu suất sử dụng 100%” có thể làm flow xấu đi

Nếu mọi người phải nhận việc mới ngay khi có vài phút trống, WIP tăng; khi PBI bị blocked ở tích hợp, nhiều người chuyển sang PBI khác thay vì gỡ trở ngại. Một số hệ thống có biến động cao sẽ hình thành hàng chờ dài khi utilization tiến tới mức tối đa.

Điều cần tối ưu không phải **ai cũng bận liên tục**, mà là **giá trị hoàn tất qua DoD với chất lượng và khả năng học bền vững**. Năng lực dự phòng hợp lý để kiểm thử, xử lý bất định hoặc giúp item gần Done có thể giảm thời gian giao sản phẩm tổng thể.

### 2.5. Mốc bắt đầu và kết thúc phải rõ

Ví dụ:

~~~text
PBI-01:
  Requested        : Ngày 1
  Started          : Ngày 5
  Implementation   : Ngày 5–7
  Waiting for API  : Ngày 8–12
  Verification     : Ngày 13
  Finished (DoD)   : Ngày 14
~~~

Nếu chỉ tính ba ngày code, đội bỏ qua thời gian chờ. Với cách đánh dấu mốc minh họa, cycle time thực cần được tính từ **timestamp Started tới timestamp Finished**, không đơn thuần cộng số ngày thao tác trong một sơ đồ thiếu độ chính xác về giờ. Khi so trước–sau, phải giữ cùng quy tắc đếm ngày lịch/ngày làm việc.

## 3. Tính capacity khả dụng mà không biến con người thành ô lịch

Phần này đưa ra một **bảng capacity minh họa**, không phải công thức áp đặt cho mọi tổ chức. Trong thực tế, cần dùng lịch làm việc, nghĩa vụ hỗ trợ, quyền nghỉ và dữ liệu lịch sử của đội; tránh thu thập chi tiết nhạy cảm không cần thiết.

### 3.1. Định nghĩa phạm vi tính trước

Giả sử một Scrum Team có **năm Developers** cùng tạo Increment trong Sprint hai tuần gồm **10 ngày làm việc**; Product Owner và Scrum Master đóng góp theo accountabilities của họ nhưng **không tự được cộng vào capacity xây PBI của Developers** nếu không làm công việc tương ứng.

Đội quyết định tính capacity **cho công việc tạo Increment và kiểm chứng PBI đã chọn**, sau khi trừ:

1. Ngày nghỉ hoặc thời gian không có mặt.
2. Nghĩa vụ hỗ trợ sản phẩm/production đã dự kiến.
3. Công việc phối hợp bắt buộc, cải tiến môi trường và hoạt động không được hạch toán trong effort PBI.

Những khoản ấy phải **không chồng nhau**. Nếu effort PBI đã bao gồm một buổi pair và test, không được trừ buổi đó khỏi capacity thêm lần nữa.

### 3.2. Bảng capacity hai tuần

| Developer / năng lực nổi bật | Ngày theo lịch | Nghỉ | Hỗ trợ/incident đã dự trù | Nghĩa vụ khác không nằm trong PBI | Còn khả dụng cho phạm vi PBI |
|---|---:|---:|---:|---:|---:|
| **Lan — API, quyền học** | 10 | 2 | 1 | 1 | **6** |
| **Minh — UI, accessibility** | 10 | 0 | 2 | 1 | **7** |
| **Phương — testing, integration** | 10 | 1 | 1 | 1 | **7** |
| **Quang — full-stack, dữ liệu** | 10 | 0 | 1 | 2 | **7** |
| **Trang — CI, environments** | 10 | 1 | 1 | 2 | **6** |
| **Tổng** | **50** | **4** | **6** | **7** | **33** |

Trong ví dụ:

\[
C_{\text{available}} = 50 - 4 - 6 - 7 = 33\ \text{person-days}
\]

Đây là số giả định để luyện lập kế hoạch. Các khoản như Scrum events, trao đổi phụ thuộc hoặc thiết kế test cần được **hạch toán nhất quán**: nếu đã được phản ánh ở cột “nghĩa vụ khác”, không tính lại trong effort của PBI. Ngược lại, công việc thực hiện PBI như test, refactor và pairing **nên nằm trong effort PBI khi ước lượng công việc đó**.

### 3.3. Cần xét cả năng lực theo chuyên môn

Năm người có tổng 33 ngày công **không có nghĩa** mọi công việc tương đương về thời gian:

- Những điều kiện entitlement nhạy cảm cần Lan/Quang hoặc hỗ trợ chuyên môn.
- Phương và các Developers khác cùng chịu trách nhiệm chất lượng, nhưng Phương có kiến thức đặc biệt về test environment.
- Trang giúp CI nhưng không nên biến mọi PBI thành ticket chờ Trang.
- Minh có thể tự triển khai UI, song cần làm rõ contract với API và test phân quyền.

Nếu mọi PBI phải chờ đúng Lan hai ngày và Lan chỉ còn sáu ngày, **điểm nghẽn kỹ năng** cần được nhìn rõ. Đội có thể pair để lan tỏa kỹ năng, chia lại lát cắt hoặc giảm phụ thuộc; không cộng ngày công của người khác vào phần việc có điều kiện mà họ chưa thể tự làm.

### 3.4. Capacity không phải hợp đồng cố định từ đầu kỳ

Trong Sprint có thể xuất hiện:

- Một sự cố production chưa dự báo.
- Thành viên nghỉ ngoài kế hoạch.
- API đối tác sẵn sàng muộn.
- Test phát hiện rủi ro lớn.
- Một Product Backlog Item cần hiểu lại.

Khi đó số 33 **không còn là sự thật mới nhất**. Đội cần cập nhật dự báo, không dùng capacity ban đầu để trách cứ người không làm đủ “ngày đã cam kết”.

### 3.5. Capacity và buffer

Đội có thể giữ một phần khả dụng chưa gán cứng cho PBI mới để hấp thụ:

- Lỗi kiểm thử và việc làm lại.
- Phối hợp phụ thuộc chưa rõ.
- Việc khẩn trong phạm vi quản lý được.
- Hành vi biên hoặc chất lượng phát hiện thêm.

Không có tỷ lệ buffer cố định được Scrum Guide yêu cầu. **Chọn dựa trên biến động lịch sử và rủi ro hiện tại**; không dùng buffer làm “ngân sách bí mật” để che quá tải hoặc cho phép bỏ DoD.

Nếu kế hoạch điền đủ 33 ngày công theo median ước lượng và không có cách thích ứng khi một item vượt khoảng, nhóm đang **đặt cược vào trường hợp mọi giả định đều thuận lợi**.

### 3.6. Product Owner và Scrum Master có capacity riêng

Đối với Scrum:

- **Product Owner** phải có thời gian làm rõ giá trị, quyết định thứ tự Product Backlog và cộng tác với stakeholders/Developers.
- **Scrum Master** phải có khả năng hỗ trợ hiệu quả Scrum, giảm trở ngại và cải tiến.
- **Developers** tự quản kế hoạch tạo Increment, bao gồm các chuyên môn cần thiết.

Không nên tính Product Owner như “0,5 backend Developer” chỉ để đẹp bảng capacity trừ khi người đó **thực sự đóng góp năng lực tương ứng** và tổ chức accountabilities phù hợp. Đồng thời, nếu Product Owner không sẵn sàng làm rõ quyết định trong Sprint, **đây là một dependency quan trọng** chứ không chỉ là số ngày công thiếu.

## 4. Ước lượng công việc như một cách bộc lộ bất định

Ước lượng không phải chứng minh nhóm biết tương lai chính xác. Nó là **một cách trao đổi về phạm vi, rủi ro, phương án và năng lực**.

### 4.1. Tránh một con số duy nhất khi rủi ro rõ

Ví dụ:

| PBI | Lát cắt giá trị | Effort range minh họa | Rủi ro lớn |
|---|---|---|---|
| **ENR-01** | Ghi danh khóa miễn phí và vào bài đầu đúng quyền | **10–15 ngày công** | Contract entitlement, dữ liệu trùng |
| **ENR-02** | Hiển thị lỗi/điều kiện không hợp lệ của luồng miễn phí | **6–10 ngày công** | Edge cases, accessibility, UX |
| **ENG-01** | Đưa kiểm tra hợp đồng quyền học vào CI cho lát cắt | **4–7 ngày công** | Test fixtures và môi trường |
| **ENR-03** | Thanh toán qua nhà cung cấp ngoài, cấp quyền khi xác thực hợp lệ | **9–18 ngày công** | Sandbox/chính sách webhook chưa xác nhận |
| **ANL-01** | Ghi nhận sự kiện người học vào bài đầu | **3–6 ngày công** | Privacy, định nghĩa event và dữ liệu |
| **OPS-01** | Tối ưu pipeline triển khai toàn sản phẩm | **5–11 ngày công** | Quyền và ảnh hưởng các services |

Các khoảng ước lượng đều **giả định**, không phải tiêu chuẩn ngành. Không thể cộng tất cả range để suy ra một ngày giao chắc chắn: công việc có thể chồng nhau, chờ điều kiện, cần kỹ năng cùng lúc và có tính phụ thuộc.

### 4.2. Điều gì nằm trong một ước lượng?

Một effort range tốt phải nêu:

- Phạm vi nghiệp vụ đã hiểu và các giả định.
- Phần thiết kế, triển khai, test, tích hợp, sửa lỗi, review cần để đáp ứng DoD.
- Điều kiện môi trường dữ liệu và API.
- Những điểm chưa biết và mức biến động có thể xảy ra.
- Điều gì nằm **ngoài** phạm vi và cần quyết định riêng.

Nếu Developers chỉ ước lượng “viết code” mà DoD đòi test, security review hoặc migration, range sẽ bị thấp một cách có hệ thống.

### 4.3. Đừng dùng khoảng ước lượng làm lời hứa xác suất

Một PBI được ước lượng “6–10 ngày công” **không tự có nghĩa** 90% khả năng sẽ hoàn tất trước mười ngày lịch. Khoảng là thông tin về effort trong giả định nào đó; cần dữ liệu/hệ thống dự báo phù hợp để suy ra xác suất và elapsed time.

Không thể đơn giản nhân/chia số ngày công với số người để biến nó thành calendar duration vì:

- Một số công việc tuần tự.
- Có người có kỹ năng/ủy quyền cụ thể.
- Có thời gian chờ và handoff.
- DoD có kiểm tra tích hợp.
- Item khác chia sẻ cùng capacity.

### 4.4. Three-point estimation và giới hạn

Đội có thể dùng ba ước lượng:

- **O (optimistic):** trường hợp thuận lợi có căn cứ.
- **M (most likely):** trường hợp thường xảy ra nhất theo giả định.
- **P (pessimistic):** trường hợp bất lợi hợp lý, không phải mọi thảm họa có thể tưởng tượng.

Ví dụ ENR-01:

~~~text
O = 10 person-days
M = 12 person-days
P = 15 person-days
~~~

Một số phương pháp PERT dùng công thức:

\[
E=\frac{O+4M+P}{6}
\]

Với ví dụ trên:

\[
E=\frac{10+4(12)+15}{6}=\frac{73}{6}\approx12{,}17
\ \text{person-days}
\]

**Đây chỉ là một heuristic mô hình hóa effort, không phải kỳ vọng thống kê được xác minh chỉ vì có ba số**. Phân phối giả định, khả năng tương quan và lịch sử của đội có thể khiến kết quả khác đáng kể. Không dùng 12,17 như số đo chính xác tới hai chữ số thập phân để cam kết Sprint.

### 4.5. Slicing giúp giảm bất định hiệu quả hơn “ước lượng lại”

Khi ENR-03 phụ thuộc webhook chưa rõ, đội có thể chia:

1. **Spike có mục tiêu học:** xác minh cơ chế sandbox và security requirements.
2. **Lát cắt trạng thái PENDING:** hiển thị đúng và không cấp quyền giả.
3. **Lát cắt callback hợp lệ:** xử lý một phương thức thanh toán có điều kiện xác thực.
4. **Lát cắt idempotency và phục hồi:** xử lý callback gửi lặp, timeout và sự kiện đến sai thứ tự.

Không được tự gọi spike/prototype chưa đạt DoD là Increment thanh toán đã hoạt động. Mỗi lát cắt người dùng được tính Done cần đáp ứng tiêu chuẩn chất lượng tương ứng. **Spike làm giảm bất định về sau**, không thay bằng chứng sản phẩm.

### 4.6. Ước lượng phục vụ quyết định, không phục vụ chấm điểm

Trong Scrum Guide, Developers chịu trách nhiệm sizing các PBIs. Product Owner có thể giúp hiểu trade-off giá trị; Developers chọn lượng PBI có triển vọng hoàn tất trong Sprint khi Planning.

Những ứng dụng đúng của estimate:

- Phát hiện PBI quá lớn để hoàn tất có chất lượng.
- Thảo luận cần thêm chuyên môn hoặc kiểm chứng nào.
- So các phương án tạo giá trị sớm.
- Giúp Product Owner có thông tin để order backlog.
- Tạo forecast có điều kiện.

Ứng dụng sai: quy điểm/ngày công thành KPI cá nhân, buộc estimate tăng để chứng minh hiệu suất hoặc ép người mới làm một task “đúng số giờ” khi công việc chưa hiểu.

## 5. Quản lý phụ thuộc bằng điều kiện kiểm chứng, không chỉ bằng ngày hứa

Một PBI có effort nhỏ vẫn có thể chưa Done khi phụ thuộc chưa sẵn sàng. Vì thế lập kế hoạch phải xem **đồ thị điều kiện để tạo Increment**, không chỉ tổng công sức của từng hạng mục.

### 5.1. Phân loại phụ thuộc

| Loại | Ví dụ trong hệ thống học trực tuyến | Điều cần làm rõ |
|---|---|---|
| **Nghiệp vụ/quyết định** | Khi nào đơn ghi danh đủ điều kiện cấp quyền? | Ai có thẩm quyền, quy tắc và acceptance example |
| **Kỹ thuật/contract** | Giao diện cần API trạng thái đơn và entitlement | Schema, status semantics, authorization, version |
| **Dữ liệu** | Chuyển khóa đã đăng ký qua nguồn entitlement mới | Source of truth, migration, tính tương thích |
| **Môi trường/CI** | Test tích hợp cần database sandbox và test identities | Ai tạo, tính ổn định, quyền truy cập, test evidence |
| **Năng lực chuyên môn** | Một người biết rõ xử lý callback trùng | Phương án pairing, tài liệu, review hoặc hỗ trợ |
| **Ngoài tổ chức** | Nhà cung cấp thanh toán chưa cấp sandbox | Điều kiện hợp đồng, deadline có nguồn, fallback |
| **Phát hành/tuân thủ** | Cần xác minh quyền riêng tư và chính sách thanh toán | Guardrails bắt buộc và ai quyết định |

Một số phụ thuộc **chỉ cần trao đổi trực tiếp**. Một số khác yêu cầu contract, test và theo dõi; một danh sách phụ thuộc quá lớn mà không có hành động cũng có thể là lãng phí.

### 5.2. Tách “phải có trước” và “nên làm trước”

Ví dụ:

- **Phải có trước:** muốn xác minh học viên vào bài đúng quyền, cần quy tắc entitlement và môi trường kiểm chứng quyền.
- **Có thể làm song song:** thiết kế thông điệp UI và xây bộ fixture test, nếu ngữ nghĩa trạng thái đã thống nhất.
- **Nên làm trước:** nghiên cứu rủi ro callback của nhà cung cấp để không dựa toàn bộ Sprint Goal vào hợp đồng chưa rõ.
- **Không phải phụ thuộc bắt buộc:** banner marketing không cần hoàn tất trước khi thử luồng ghi danh miễn phí, trừ khi có điều kiện kinh doanh thực tế đặc biệt.

Nếu coi mọi quan hệ là “blocked”, đội có thể tự tạo một đồ thị chuỗi dài vô ích. Nếu coi mọi thứ là độc lập, integration tests sẽ phát hiện sai ngữ nghĩa khi đã quá muộn.

### 5.3. Bảng phụ thuộc có owner và bằng chứng

| ID | Bên cần / PBI | Điều kiện từ ai | Trạng thái hiện tại | Tác động nếu chậm | Bước tiếp/owner |
|---|---|---|---|---|---|
| **DEP-01** | ENR-01 | Quy tắc entitlement do PO và Developers liên quan xác nhận | Có giả định, chưa chốt edge case | Không thể kết luận cấp quyền đúng | Họp làm rõ ví dụ, owner PO + Developers |
| **DEP-02** | ENR-01 | Test environment và identity fixtures | Sẵn sàng một phần | Test authz/integration có thể chậm | Trang, Phương kiểm chứng trên build thật |
| **DEP-03** | ENR-02 | UI copy và hành vi khi không đủ điều kiện | Chưa kiểm chứng với người học | Hệ thống thông báo gây hiểu nhầm | Minh + PO + UX làm rõ |
| **DEP-04** | ENR-03 | Sandbox/hợp đồng callback của đối tác | Chưa xác nhận | Không thể test giao dịch thật | PO/đầu mối đối tác xác nhận điều kiện; không hứa Done |
| **DEP-05** | ENG-01 | Quyền thay pipeline CI | Có chủ sở hữu, chờ phê duyệt policy | Tự động hóa test có thể bị chặn | Trang trao đổi service owner |

Đây là **bảng minh họa**, không phải giao diện công cụ bắt buộc. Với một sản phẩm nhỏ, PBI có thể mang trực tiếp các ghi chú này.

### 5.4. Đồ thị phụ thuộc theo kết quả

~~~mermaid
flowchart LR
    G["Sprint Goal:<br/>Ghi danh miễn phí và vào bài đầu đúng quyền"] --> A["ENR-01: hành trình đầu-cuối"]
    A --> R["Quy tắc entitlement"]
    A --> I["Identity + test data"]
    A --> T["Integration / authorization checks"]
    R --> T
    I --> T
    T --> D["Increment đạt DoD"]
    A --> D
    X["ENR-03: thanh toán trả phí"] --> P["Sandbox đối tác"]
    X --> C["Callback contract"]
    P --> C
    C --> V["Security + idempotency tests"]
    V --> Z["Increment thanh toán — đợt sau"]
~~~

Hình giúp thấy ENR-03 có một chuỗi điều kiện **không thể bảo đảm trong kỳ**, trong khi ENR-01 có thể kiểm soát nhiều điều kiện bằng việc làm rõ, phối hợp và kiểm chứng nội bộ. Điều đó là lý do **không chọn ENR-03 làm phụ thuộc bắt buộc cho Sprint Goal đầu tiên** khi thông tin còn thiếu.

### 5.5. Dependency owner không nhất thiết là người được giao task

Ví dụ DEP-04:

- Product Owner có trách nhiệm về thứ tự Product Backlog và nhu cầu giá trị.
- Developers có trách nhiệm đánh giá kỹ thuật/hợp đồng có thể dùng chưa.
- Đầu mối đối tác có thể có trách nhiệm lấy thông tin sandbox.
- Người có thẩm quyền bảo mật quyết định điều kiện bắt buộc phù hợp.

Không thể chỉ ghi “Team Payments” làm owner rồi hy vọng một người tự xử lý. Trong bảng phụ thuộc, cần **đầu mối chịu trách nhiệm tiến hành bước tiếp**, còn accountabilities của Scrum vẫn được giữ đúng.

### 5.6. Thời điểm sẵn sàng không phải lúc nào cũng là ngày dự kiến

“Đối tác nói sẽ có API vào thứ Tư” là **giả định**. “Hợp đồng và sandbox đã có, callback hợp lệ chạy được theo test cases” mới là **bằng chứng sẵn sàng**.

Một checklist sẵn sàng có thể gồm:

1. Đã có contract phiên bản cụ thể.
2. Có quyền và dữ liệu kiểm thử phù hợp.
3. Đã thống nhất success, error, timeout, duplicate semantics.
4. Có đường trao đổi khi nhà cung cấp đổi contract.
5. Có quyết định phạm vi/rollback khi điều kiện không đạt.

Nếu chưa đạt, đội có thể làm việc khám phá giảm rủi ro, nhưng **không nên biến một lời hứa ngoài quyền thành cam kết Done không điều kiện**.

### 5.7. Dependency buffering khác effort buffering

Đối với một PBI phụ thuộc bên ngoài, thêm hai ngày công dự phòng **không tạo ra sandbox**. Cần:

- Xác minh điều kiện trước Sprint nếu có thể.
- Chọn phần việc tạo giá trị không phụ thuộc.
- Có phương án dự phòng hoặc đổi thứ tự backlog.
- Tạo contract/mock phù hợp để học, nhưng công bố giới hạn.
- Escalate khi vượt quyền đội.

**Buffer thời gian/capacity có thể giúp hấp thụ biến động**, nhưng không thay nguồn thông tin, hợp đồng và quyền quyết định.

### 5.8. Gỡ phụ thuộc lặp lại bằng thay hệ thống

Nếu mọi PBI chờ Trang tạo environment hai ngày, có thể hợp lý đầu tư self-service hoặc chia sẻ năng lực. Nếu mọi PBI phải sửa cả UI, API, DB và qua ba hàng chờ, cần xem team boundary và contract.

Không nên chỉ thêm “dependency sync” hằng ngày để giữ một hàng chờ có thể loại bỏ bằng thay đổi cấu trúc hoặc tự động hóa.

## 6. Bất định: từ danh sách rủi ro tới kịch bản điều chỉnh có điều kiện

Lập kế hoạch ngắn hạn không nhằm loại bỏ bất định. Nó giúp **phát hiện sớm giả định quan trọng, giảm điều có thể giảm và không che những phần còn chưa biết**.

### 6.1. Hai nguồn bất định khác nhau

**Bất định do thiếu hiểu biết (epistemic):**

- Chưa biết API đối tác trả những trạng thái nào.
- Chưa hiểu quy tắc cấp quyền khóa học.
- Không rõ người dùng sẽ hiểu thông báo PENDING.
- Chưa biết migration làm ảnh hưởng dịch vụ nào.

Có thể giảm bằng refinement, discovery, thử tích hợp, spike, test và trao đổi hợp đồng.

**Biến động ngẫu nhiên/khó dự báo đầy đủ (aleatory):**

- Có thể xuất hiện incident production bất thường.
- Một lần test có thể tìm ra lỗi phức tạp hơn dự tính.
- Thời gian phản hồi của bên ngoài dao động.
- Hệ thống có tải thay đổi theo mùa/đợt ghi danh.

Có thể ứng phó bằng capacity dự phòng phù hợp, policies, khả năng phục hồi và dự báo theo phân phối dữ liệu; không thể học hết để biến mọi biến động thành số chính xác.

Trong thực tế nhiều vấn đề kết hợp cả hai nguồn. Không cần dán nhãn từng PBI; **dùng phân biệt này để chọn cách phản ứng**.

### 6.2. Một risk register nhỏ, có tín hiệu kích hoạt

| Rủi ro | Tín hiệu kích hoạt | Tác động | Cách giảm / lựa chọn | Ai theo dõi |
|---|---|---|---|---|
| Quy tắc cấp quyền chưa thống nhất | AC về PENDING/CONFIRMED còn mâu thuẫn | Không thể xác minh DoD | Làm rõ bằng ví dụ trước khi tích hợp | PO và Developers |
| CI integration test không ổn định | Test fail không tái hiện hoặc data bị dùng chung | Phát hiện lỗi muộn/sai tín hiệu | Fixture cô lập, test hữu ích, không tắt gate bừa | Phương và Trang |
| Incident làm giảm capacity | On-call phải xử lý sự cố có mức ưu tiên cao | Giảm năng lực hoàn tất PBI | Reforecast, bảo vệ Sprint Goal khi còn khả thi | Scrum Team/incident owner |
| Đối tác chậm cung cấp sandbox | Chưa có contract kiểm chứng trước Planning | ENR-03 không thể Done | Không đưa ENR-03 vào scope cần thiết; spike khi có ý nghĩa | Đầu mối đối tác |
| Nhu cầu người học không đúng giả định | Quan sát cho thấy vấn đề khác | Lát cắt ít giá trị | Product Owner xem lại thứ tự/giải pháp | PO và stakeholders |
| Một người là điểm nghẽn | Mọi test entitlement phải chờ Lan | Age tăng, nhiều blocker | Pair, giảm coupling, chia sẻ test contract | Developers |

Không cần gán “risk score = 92” từ những xác suất không có dữ liệu. Đôi khi mô tả **mức ảnh hưởng, khả năng phát hiện và hành động rõ** hữu ích hơn điểm số giả chính xác.

### 6.3. Thiết kế ba kịch bản capacity

Dựa trên 33 person-days khả dụng ban đầu:

| Kịch bản | Điều kiện | Capacity còn cho PBI trong phạm vi | Hệ quả kế hoạch |
|---|---|---:|---|
| **A — Cơ sở** | Nghỉ, hỗ trợ, nghĩa vụ khác đúng dự kiến | **33 person-days** | Có thể xét ENR-01, ENR-02 và cải tiến CI theo phạm vi |
| **B — Có incident** | Sự cố thêm **6 person-days** ngoài phần hỗ trợ đã dự trù | **27 person-days** | Giữ mục tiêu cốt lõi, thương lượng ENR-02 hoặc ENG-01 không thiết yếu |
| **C — Phụ thuộc đối tác chưa sẵn sàng** | Sandbox thanh toán vẫn thiếu, capacity nội bộ không đổi | **33 person-days**, nhưng **ENR-03 vẫn không khả thi để Done** | Không kéo ENR-03 chỉ vì có người rảnh; chọn PBI độc lập hoặc giảm rủi ro |

Kịch bản B:

\[
33-6=27\ \text{person-days}
\]

Kịch bản C cho thấy **năng lực thời gian không giải quyết được mọi dependency**. Không nên suy “33 ngày công = làm xong ENR-03” khi thiếu điều kiện hợp đồng.

### 6.4. Kịch bản không tự có xác suất

Đội có thể mô tả A/B/C mà **chưa biết mỗi kịch bản có bao nhiêu phần trăm khả năng**. Đây là cách làm hợp lý khi dữ liệu chưa đủ. Không nên tự đặt:

> “A xảy ra 70%, B 20%, C 10%, nên xác suất kế hoạch thành công 70%.”

Những con số đó là phỏng đoán và các kịch bản có thể **đồng thời** xảy ra: incident và sandbox chậm có thể cùng lúc, nên không tự là các trường hợp loại trừ lẫn nhau.

Nếu cần dự báo xác suất, phải có dữ liệu lịch sử phù hợp, giả định về tương quan, cách lấy mẫu và kiểm tra độ tin cậy. Một mô hình mô phỏng có thể hữu ích, nhưng **độ phức tạp của mô hình không tạo ra dữ liệu thực còn thiếu**.

### 6.5. Chọn trigger thay vì đợi cuối kỳ

Một kế hoạch tốt nêu **khi nào cần kiểm tra lại**:

- Nếu contract entitlement chưa thống nhất sau bước refinement đầu, đưa đúng người vào trao đổi trước khi tiếp tục xây UI phụ thuộc.
- Nếu integration test còn đỏ sau khi merge thay đổi, không gọi PBI Done.
- Nếu capacity giảm do incident, cập nhật dự báo và thảo luận phạm vi.
- Nếu work item age vượt xu hướng lịch sử của cùng loại item, kiểm tra blocker và khả năng gỡ.
- Nếu phản hồi người dùng làm giả thuyết chính sai, Product Owner xem lại thứ tự.

Không cần mỗi trigger biến thành một cuộc họp mới; **thông tin cần tới đúng người có quyền quyết định**.

### 6.6. Khoảng ước lượng và sự tương quan

Giả sử ba PBIs đều phụ thuộc vào cùng test environment. Khi environment trục trặc, **cả ba có thể cùng chậm**; không nên giả định các độ trễ độc lập rồi “triệt tiêu” nhau.

Tương tự, nếu Lan phải review cả ENR-01 và ENR-02, việc hai PBI cùng “ước lượng sáu ngày công” không nghĩa chúng song song hoàn hảo. Các khoảng effort **không phải calendar ranges**, và phụ thuộc chung làm rủi ro tăng cùng lúc.

### 6.7. Horizon ngắn, forecast dài hơn nhưng ít chi tiết hơn

Một cách lập kế hoạch theo tầng:

| Horizon | Mức chi tiết hợp lý | Điều dùng để ra quyết định |
|---|---|---|
| **Ngay hôm nay/vài ngày tới** | Blocker, test, dependency, PBI đang WIP | Ai cần giúp gì để một item Done |
| **Sprint/vài tuần** | Sprint Goal, lát cắt ưu tiên, capacity và kịch bản | Điều gì có triển vọng hoàn tất trong nhịp ngắn |
| **Một số Sprint tiếp theo** | Các khả năng sản phẩm và rủi ro lớn, phụ thuộc và dữ liệu flow | Thứ tự tương đối, điều kiện cần, forecast có giới hạn |
| **Quý/nửa năm** | Product Goal, outcome, đầu tư năng lực và cột mốc bắt buộc | Những lựa chọn chiến lược, không khóa hết task |

**Càng xa càng ít chi tiết** là cách giảm chi phí lập kế hoạch cho giả định chưa được kiểm chứng. Điều này không đồng nghĩa không cam kết những mốc pháp lý/hợp đồng có thật; cần công khai điều gì cố định và điều gì có thể thích ứng.

## 7. Chọn lát cắt theo giá trị, capacity, phụ thuộc và DoD

Sau khi có Product Goal, 33 person-days khả dụng, bảng phụ thuộc và effort ranges, đội mới bắt đầu **chọn phạm vi có triển vọng**. Thứ tự nên do Product Owner quản lý trong Product Backlog; Developers dùng năng lực và bằng chứng để lựa chọn lượng công việc trong Sprint.

### 7.1. Không tính kế hoạch chỉ bằng phép cộng range

Giả sử ba item:

- ENR-01: 10–15 person-days.
- ENR-02: 6–10 person-days.
- ENG-01: 4–7 person-days.

Tổng khoảng công sức đơn giản:

\[
10+6+4=20,\qquad15+10+7=32\ \text{person-days}
\]

Trong kịch bản cơ sở 33 person-days, có vẻ “đủ” vì mức trên 32 còn ít hơn 33. Nhưng kết luận **chắc chắn hoàn tất cả ba** vẫn sai vì:

- Effort ranges không phải các cận trên chắc chắn.
- Cả ba có thể cần cùng một chuyên gia/test environment.
- Nếu incident tăng sáu ngày công, capacity chỉ còn 27.
- Có thể phải làm lại sau khi phát hiện edge case.
- Tổng effort không mô tả trình tự và thời gian lịch.

Đây là lý do **không nên lấp đầy capacity bằng các con số median rồi xem đó là cam kết**.

### 7.2. Phân biệt công việc hỗ trợ Sprint Goal với mục tiêu độc lập

Ví dụ Product Goal là tự phục vụ ghi danh an toàn. Sprint Goal được đề xuất:

> **“Học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu trong một luồng tích hợp đạt DoD.”**

Các PBIs:

| Item | Vai trò đối với Sprint Goal | Quyết định minh họa |
|---|---|---|
| **ENR-01** | Lát cắt **cốt lõi** đạt Sprint Goal, gồm hành vi và kiểm chứng cần thiết | Chọn làm trọng tâm |
| **ENR-02** | Nâng chất lượng thông điệp/đường xử lý lỗi cho luồng miễn phí | Chọn phần tối thiểu gắn DoD/goal, làm rõ phần mở rộng có thể hoãn |
| **ENG-01** | Tự động hóa **tái sử dụng** contract checks qua nhiều modules, ngoài những test cần thiết đã tính trong ENR-01 | Chọn phạm vi nhỏ nếu giúp Done sớm; phần cải tiến mở rộng có thể hoãn |
| **ENR-03** | Thanh toán nhà cung cấp mới, phụ thuộc chưa có | **Không chọn làm điều kiện cho Sprint Goal này** |
| **ANL-01** | Dữ liệu outcome và quan sát hành vi | Chọn một event tối thiểu nếu cần đo và bảo vệ quyền riêng tư |
| **OPS-01** | Cải tiến pipeline rộng hơn phạm vi Sprint Goal | Có thể đưa vào Product Backlog hoặc service backlog phù hợp |

**Không được đẩy các kiểm tra bắt buộc của ENR-01 sang ENG-01 rồi hoãn ENG-01** để gọi ENR-01 Done. ENR-01 đã bao gồm chi phí thực hiện và xác minh đủ DoD; ENG-01 chỉ là năng lực tái sử dụng ngoài phạm vi đó, được ước lượng riêng để tránh đếm trùng.

### 7.3. Thứ tự chọn: giá trị, rủi ro và khả năng hoàn tất

Một cuộc trao đổi hữu ích:

1. Product Owner nêu vì sao ENR-01 hỗ trợ Product Goal.
2. Developers xác nhận các điều kiện entitlement/test có thể kiểm chứng trong Sprint.
3. Đội chia ENR-01 nếu phạm vi quá lớn nhưng giữ một lát cắt có ý nghĩa.
4. Đội xác định ENR-02 phần nào bắt buộc cho hành vi đúng, phần nào là cải tiến tiện ích.
5. Đội quyết định có nên làm ENG-01 trong phạm vi nhỏ vì nó giúp giảm lỗi lặp.
6. ENR-03 không được chọn chỉ để “khai thác 100% năng lực” khi đối tác chưa sẵn sàng.
7. Developers chọn lượng việc dự kiến phù hợp với lịch sử, năng lực và sự bất định; giữ cơ hội thích ứng khi phát hiện mới.

Không có một công thức điểm số trong Scrum Guide bắt buộc cân giá trị, công sức và rủi ro. Các kỹ thuật như WSJF, RICE hoặc cost of delay có thể hỗ trợ thảo luận nhưng **đầu vào thiếu tin cậy phải được công bố**.

### 7.4. Chia dọc thay vì chia theo tầng

**Cách chia dễ tạo hàng chờ:**

~~~text
TASK-01: Xây UI ghi danh
TASK-02: Xây API ghi danh
TASK-03: Tạo bảng dữ liệu
TASK-04: Viết test end-to-end
TASK-05: Nối vào bài đầu
~~~

Những task có thể cần trong implementation, nhưng **mỗi task riêng chưa chắc tạo khả năng dùng được cho học viên**.

**Cách chia theo hành vi:**

| Lát cắt | Giá trị/kiểm chứng |
|---|---|
| ENR-01A — Ghi danh miễn phí hợp lệ và vào bài đầu | Khép kín từ yêu cầu, dữ liệu, quyền tới truy cập |
| ENR-01B — Ngăn trùng ghi danh và báo trạng thái đúng | Bảo vệ tính đúng đắn cho trường hợp lặp |
| ENR-01C — Xử lý trường hợp không đủ điều kiện | Không cấp quyền sai; hướng dẫn phù hợp |

Nếu ENR-01A chưa kiểm tra phân quyền tối thiểu cần cho DoD thì **không được xem là Increment đạt DoD**. Không phải cứ đặt hậu tố A/B/C là đã chia dọc thành công; phải đánh giá **mỗi lát cắt có hành vi có thể sử dụng và chất lượng phù hợp**.

### 7.5. Công việc bắt buộc và công việc tùy chọn cần diễn đạt đúng

Trong một kế hoạch, “tùy chọn” có thể nghĩa:

- Chưa cần để đạt Sprint Goal.
- Có giá trị nhưng thứ tự thấp hơn theo Product Backlog.
- Chỉ làm thêm khi capacity thật và dependency cho phép.

**Không có nghĩa:** test bảo mật tùy chọn, DoD tùy chọn, xác thực callback tùy chọn hoặc hạng mục bất cứ ai có thể kéo vào theo sở thích cá nhân. Ràng buộc chất lượng bắt buộc phải nằm trong công việc cần để đạt Done.

### 7.6. Một kế hoạch có chỗ cho giảm rủi ro

Nếu dữ liệu cho thấy rủi ro môi trường test lớn, một PBI nhỏ về contract tests có thể **hỗ trợ Sprint Goal trực tiếp** ngay cả khi người dùng không thấy một UI mới. Product Owner có thể cân nhắc giá trị kỹ thuật qua **khả năng giao an toàn, giảm thời gian chờ và tránh lỗi**.

Tuy nhiên, không nên dùng câu “kỹ thuật quan trọng” để tự thêm một dự án tái cấu trúc rộng khiến Sprint Goal mất ý nghĩa. Mức đầu tư cần dựa trên rủi ro thật và phương án nhỏ có thể kiểm chứng.

### 7.7. Kế hoạch không được che capacity theo kỹ năng

Với ENR-01 và ENR-02, Lan có sáu ngày khả dụng. Nếu cả hai yêu cầu sáu ngày review chuyên sâu của Lan **mỗi item**, chúng không thể hoàn tất theo cách hiện tại dù tổng capacity đội là 33.

Các phương án:

- Pair Quang với Lan trên entitlement để giảm phụ thuộc.
- Đổi thứ tự hoặc chia lát cắt giảm số thay đổi contract.
- Chuẩn hóa contract tests và review những trường hợp quan trọng.
- Không chọn cả hai item với cùng điều kiện chuyên môn chưa thể đáp ứng.

**Đừng âm thầm giả sử một UI Developer sẽ hoàn thành nghiệp vụ bảo mật mà chưa có kỹ năng và guardrails phù hợp.**

## 8. Sprint Planning theo Scrum: vì sao, làm gì, làm thế nào?

Nếu đội sử dụng Scrum, capacity và dependencies cần **phục vụ Sprint Goal**, không biến Sprint Planning thành buổi cấp phát task theo giờ cho từng người.

### 8.1. Ba chủ đề của Sprint Planning

Theo **Scrum Guide 2020**, Sprint Planning đề cập ba câu hỏi:

1. **Why is this Sprint valuable?** Product Owner đề xuất cách sản phẩm có thể tăng giá trị; cả Scrum Team xác định **Sprint Goal**.
2. **What can be Done this Sprint?** Developers cùng Product Owner thảo luận Product Backlog, và **Developers lựa chọn lượng công việc** họ tin có thể hoàn tất trong Sprint.
3. **How will the chosen work get Done?** Developers lên kế hoạch triển khai đủ chi tiết để bắt đầu, rồi tiếp tục thích ứng trong Sprint.

Sprint Goal là **commitment của Sprint Backlog**, không phải lời hứa mọi task/PBI dự kiến từ ngày đầu chắc chắn Done. Chất lượng không được giảm và các thay đổi không được gây nguy hại Sprint Goal; phạm vi có thể được làm rõ, thương lượng lại với Product Owner khi hiểu thêm.

### 8.2. Ai chịu trách nhiệm quyết định?

| Quyết định | Accountability/chủ thể phù hợp | Vai trò tham gia |
|---|---|---|
| Product Goal và thứ tự Product Backlog | **Product Owner** | Developers, stakeholders, chuyên gia |
| Sizing PBIs | **Developers** | Product Owner làm rõ giá trị và trade-off |
| Sprint Goal | **Toàn Scrum Team** xác định khi Planning | Product Owner đề xuất hướng tăng giá trị |
| Những PBIs chọn vào Sprint và kế hoạch thực hiện | **Developers** chọn lượng và xây Sprint Backlog | Product Owner cộng tác làm rõ |
| Các cải tiến để hiệu quả Scrum | **Scrum Master** chịu trách nhiệm hiệu quả, hỗ trợ đội/PO/tổ chức | Scrum Team và tổ chức |
| Những guardrails pháp lý/bảo mật đặc thù | Theo trách nhiệm/thẩm quyền tổ chức | Developers, PO, các bên chuyên môn |

Không ai trong Scrum Team được dùng sự tự quản làm lý do **bỏ an toàn người dùng**, nhưng cũng không để quản lý vi mô giao toàn bộ task từ bên ngoài rồi nói Developers “đã tự cam kết”.

### 8.3. Mẫu Product Goal và Sprint Goal cho ví dụ

**Product Goal (hướng dài hơn):**

> “Học viên đủ điều kiện có thể tự hoàn tất ghi danh các khóa được hỗ trợ, nhận đúng quyền và vào bài đầu với thông tin trạng thái đáng tin.”

**Sprint Goal (hai tuần, minh họa):**

> “Học viên đủ điều kiện ghi danh một khóa miễn phí và vào bài đầu qua một luồng tích hợp đáp ứng DoD.”

Sự tập trung này giúp:

- ENR-01 là trọng tâm.
- ENR-02 về trường hợp không hợp lệ có giá trị trong phạm vi đảm bảo hành vi đúng.
- ENG-01 chỉ làm phần cải tiến CI cần thiết/hữu ích, không nuốt toàn bộ Sprint.
- ENR-03 thanh toán qua nhà cung cấp chưa sẵn sàng không thành điều kiện để nói Sprint Goal đạt.

**Lưu ý bối cảnh:** nếu sản phẩm thực tế không có khóa miễn phí hoặc luồng miễn phí không giúp Product Goal, ví dụ này cần thay bằng **lát cắt trả phí tối thiểu thật sự có giá trị**, không dùng chức năng giả tạo chỉ vì dễ đưa vào Sprint.

### 8.4. Lựa chọn phạm vi minh họa với 33 person-days

Developers có thể đề xuất:

| Item | Effort range | Vai trò trong kế hoạch | Điều kiện cần giữ |
|---|---:|---|---|
| **ENR-01** | 10–15 | Lát cắt cốt lõi cho Sprint Goal | Entitlement, dữ liệu, UI, test và DoD |
| **ENR-02** | 6–10 | Mở rộng handling lỗi/không hợp lệ trong luồng mục tiêu | Những điều kiện bắt buộc cho ENR-01 phải có, dù ENR-02 bị giảm phạm vi |
| **ENG-01** | 4–7 | CI contract fixture **tái sử dụng** ngoài test đã nằm trong ENR-01 | Quyền pipeline và test environment |
| **ENR-03** | 9–18 | Chưa chọn vì sandbox/hợp đồng chưa sẵn | Cần discovery và xác minh nhà cung cấp |

Nếu ba item đầu đều làm hết theo phạm vi dự kiến, tổng effort range là **20–32 person-days**. So với 33, khoảng trống ở cận trên rất nhỏ. Đội có thể:

1. Chọn ENR-01 cùng phần ENR-02 **thật sự cần** để tạo luồng đúng.
2. Không làm rộng ENG-01 nếu capacity/permission không cho phép, nhưng vẫn bảo đảm test cần thiết của ENR-01.
3. Chọn những việc tăng giá trị thêm **khi có năng lực thật** và không phá Sprint Goal.
4. Đặt trigger sớm để thương lượng lại phạm vi ENR-02 hoặc cải tiến CI không thiết yếu.

Không có quy định Scrum phải ghi “core/optional” hoặc gắn mọi item một ngày công. Mục đích ở đây là **làm rõ lựa chọn và cách thích ứng**, không tạo một bản hợp đồng khối lượng công việc mới.

### 8.5. Kiểm tra ràng buộc theo kỹ năng trước khi chốt kế hoạch

Đội nên xem câu hỏi thực tế:

| Câu hỏi | Ví dụ |
|---|---|
| Ai xác nhận quy tắc entitlement và test authz? | Lan, Quang và Phương cùng làm rõ, không đợi Lan cuối Sprint |
| Ai có thể giúp minh bạch UI khi dữ liệu sai? | Minh phối hợp trực tiếp người làm API |
| Ai có quyền làm CI fixture? | Trang cần kiểm tra policy trước khi đặt ENG-01 thành điều kiện |
| Ai phản hồi về giá trị người học? | Product Owner và nguồn quan sát/support thích hợp |
| Nếu thiếu một người? | Pairing, giảm scope phụ thuộc kỹ năng, không bỏ quality |

Nếu câu trả lời chỉ là “việc của team bên kia”, một Sprint Goal được viết đẹp vẫn chưa có năng lực giao end-to-end.

### 8.6. Sprint Backlog là kế hoạch thích ứng của Developers

Một Sprint Backlog minh họa:

~~~text
SPRINT GOAL:
  Hoc vien du dieu kien ghi danh khoa mien phi
  va vao bai dau theo quyen dung.

SELECTED ITEMS (du kien):
  ENR-01 — core end-to-end enrollment
  ENR-02 — error/invalid-state handling trong pham vi phu hop
  ENG-01 — reusable CI fixture neu dieu kien cho phep

IMPLEMENTATION PLAN:
  - Thong nhat acceptance examples va data contract
  - Test truoc cho rules quan trong
  - Tao lat cat API/DB/UI du nho
  - Tich hop thuong xuyen, xac minh authz
  - Chay CI/integration tests tren build
  - Inspect increment va feedback trong Sprint

DEPENDENCIES:
  DEP-01 entitlement semantics
  DEP-02 environment & identities
  DEP-03 error UX/content
  DEP-05 CI pipeline permission

TRIGGERS:
  - Contract chua ro: dung dung UI phu thuoc de lam ro
  - Incident chiem them capacity: reforecast
  - Quality gate fail: khong tinh PBI Done
  - Product feedback moi: xem lai scope va gia tri voi PO
~~~

Kế hoạch kỹ thuật trong Sprint Backlog **không cần dự đoán từng giờ của tất cả ngày còn lại**. Developers có thể điều chỉnh khi học thêm để đạt Sprint Goal.

### 8.7. Timebox và nhịp Scrum

Scrum Guide quy định Sprint dài cố định **một tháng hoặc ngắn hơn**, các Sprint liên tiếp. Trong Sprint có:

- **Sprint Planning:** lập mục tiêu, lựa chọn công việc và kế hoạch.
- **Daily Scrum:** 15 phút để Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog.
- **Sprint Review:** Scrum Team cùng stakeholders kiểm tra kết quả và thích ứng.
- **Sprint Retrospective:** lập kế hoạch cải thiện chất lượng và hiệu quả.

Product Backlog refinement là **hoạt động liên tục**, không phải một event chính thức với timebox bắt buộc.

Không nên tổ chức một “Sprint test” sau Sprint phát triển để bù cho thiếu DoD. Những PBI chưa đáp ứng DoD **không là một phần Increment Done**.

### 8.8. Daily Scrum: hỏi về tiến triển tới goal và blocker

**Không có ích:**

> “Lan code bốn giờ, Minh vẽ UI ba giờ, Phương kiểm tra tám test.”

**Có ích hơn:**

> “Để đạt Sprint Goal, chúng ta còn thiếu kiểm chứng entitlement cho người dùng không đủ quyền. Contract test đang fail. Hôm nay Lan, Quang và Phương sẽ cùng tái hiện, Minh tạm không mở thêm UI state mới. Nếu policy cấp quyền chưa chốt trước buổi làm rõ, PO cần trao đổi quyết định với đúng stakeholder.”

Sau Daily, người liên quan có thể trao đổi thêm chi tiết; Daily không phải nơi mọi người phải giải toàn bộ vấn đề trong đúng 15 phút.

### 8.9. Sprint Review và Retrospective đánh giá hai mặt khác nhau

**Review:** Increment đã đạt DoD nào? Học viên có thao tác được không? Còn giả định sai hoặc cơ hội nào làm Product Owner thay thứ tự Product Backlog?

**Retrospective:** Điều gì ở teamwork, hợp đồng, test environment, WIP và quyền quyết định đã giúp/cản Sprint Goal? Thử thay đổi cụ thể nào trong Sprint sau?

Review không phải buổi phê duyệt phát hành. Increment đạt DoD có thể được phát hành trước Review nếu phù hợp chính sách, nhưng **Done, released và outcome observed** là các mốc khác nhau.

## 9. Lập kế hoạch ngắn hạn với Kanban khi công việc kéo đến liên tục

Không phải mọi đội làm việc theo Sprint. Một nhóm vận hành nhận incident, request và hỗ trợ platform liên tục có thể không có Sprint Goal ổn định nhưng vẫn cần **dự báo năng lực, phụ thuộc và bất định**.

### 9.1. Bắt đầu từ dịch vụ và Definition of Workflow

Một dịch vụ ví dụ: “Cung cấp môi trường test phù hợp để product teams giao phần mềm an toàn”.

Workflow minh họa:

~~~text
Requested -> Ready -> In Progress -> Verification -> Finished
                           |
                           +-- Blocked (ghi owner, reason, age)

Policies:
  - Pull item khi co capacity phu hop, khong day work vao team vo han.
  - WIP control duoc cong bo, co co che xem lai.
  - Incident khan theo severity va class of service.
  - Finished khi hoan tat service criteria, khong chi code merged.
  - Blocked van tinh WIP trong boundary neu da Started.
  - Replenishment/service review dua tren feedback va flow data.
~~~

Các trạng thái và policies là **ví dụ thiết kế**, không phải một board Kanban chuẩn cho mọi dịch vụ. Cần nói rõ loại item, điểm bắt đầu/đến đích, WIP control, các chính sách xử lý, SLE khi áp dụng và cách cải tiến workflow.

### 9.2. Capacity Kanban không nhất thiết lập bằng số ticket cố định mỗi tuần

Một đội có 20 person-days khả dụng trong tuần không nên tự hứa “hoàn tất 20 tickets” nếu:

- Một số ticket cần một giờ, số khác ba ngày.
- Có incident khẩn.
- Có ticket chờ thay đổi quyền từ product team.
- Mức độ rủi ro và kiểm chứng khác nhau.

Nhóm có thể dùng **throughput lịch sử của cùng loại work items**, work item age, WIP và SLE phù hợp để đưa ra **forecast theo điều kiện**. Capacity vẫn hữu ích để nhận diện thiếu người/giờ, nhưng không thay cách quan sát flow.

### 9.3. Bốn flow metrics tối thiểu của Kanban

| Metric | Câu hỏi thực hành | Sai lầm cần tránh |
|---|---|---|
| **WIP** | Bao nhiêu item đã Started nhưng chưa Finished? | Giấu blocked items hoặc đếm trùng trạng thái |
| **Throughput** | Bao nhiêu item Finished trong một kỳ? | Đếm mỗi subtask như một yêu cầu dịch vụ |
| **Work Item Age** | Item chưa Finished đã ở workflow bao lâu? | Chỉ xem item Done nên bỏ qua item rất già |
| **Cycle Time** | Item Finished mất bao lâu từ Started? | Chỉ đếm giờ làm tay, loại toàn bộ hàng chờ |

SLE gồm **thời lượng và xác suất**, ví dụ “85% yêu cầu loại X được Finished trong 12 ngày lịch” **chỉ khi** có dữ liệu/giả định hỗ trợ. Nó không phải bảo đảm cho mọi item.

### 9.4. Policies cho việc khẩn và phụ thuộc

Một chính sách phù hợp có thể nêu:

1. **Expedite:** chỉ cho severity được xác định trước; ghi tác động lên các item khác.
2. **Blocked:** ghi lý do, owner và điều kiện gỡ; không xóa khỏi WIP.
3. **Capacity:** dành khả năng cho reliability/incident theo biến động lịch sử.
4. **Pull:** chỉ bắt đầu mới khi năng lực theo kỹ năng cho phép và WIP policy không bị phá.
5. **Feedback:** khi vượt age/SLE kỳ vọng, trao đổi để tháo trở ngại và cập nhật forecast.

Không áp một hàng “khẩn” vô hạn. Nếu mọi yêu cầu đều được gọi urgent, policy sẽ mất tác dụng.

### 9.5. Có thể dùng Kanban practices cùng Scrum

Một Scrum Team có Sprint Goal nhưng nhiều PBI dở có thể dùng:

- Bảng PBI với Started/Done rõ.
- WIP control hợp lý.
- Work item age để thấy item bị kẹt.
- Throughput/cycle time để hiểu lịch sử và giới hạn dự báo.
- Policies giúp hoàn tất item trước khi kéo thêm.

Những thực hành này **bổ sung cơ chế Scrum**, không xóa Product Goal, Sprint Goal, Scrum Team accountabilities hoặc Scrum events khi đội đang dùng Scrum.

### 9.6. Dòng planned và unplanned work có thể cần nhìn riêng

Nếu đội vừa phát triển capability mới vừa trực sự cố, cần phân biệt:

| Dòng | Điều cần quan sát | Một lựa chọn phối hợp |
|---|---|---|
| Feature/Increment hướng Product Goal | Goal, DoD, dependencies và feedback | Scrum với Sprint Goal khi khả thi |
| Incident khẩn | Severity, khả năng giảm ảnh hưởng, response/recovery | Kanban/incident policies và on-call |
| Service requests thường ngày | Demand, age, WIP, SLE, chất lượng dịch vụ | Kanban với replenishment |
| Cải tiến nền tảng | Tác động tới product teams, khả năng self-service | Product Backlog hoặc service improvements có thứ tự |

Đây không phải lý do tự động lập bốn đội riêng. Cần xem **team boundary, năng lực chuyên môn và quyền quyết định** trước khi tách cấu trúc tổ chức.

## 10. Thay đổi kế hoạch khi thực tế không đi theo dự kiến

Một kế hoạch ngắn hạn tốt **không loại bỏ nhu cầu điều chỉnh**; nó khiến đội biết điều chỉnh điều gì và bảo vệ điều gì.

### 10.1. Sự kiện A: thêm incident làm giảm capacity

Giả sử kịch bản cơ sở 33 person-days, giữa Sprint xảy ra incident tốn thêm sáu ngày công tương đương:

\[
C_{\text{updated}}=33-6=27\ \text{person-days}
\]

Không nên nói “đã cam kết 33 nên mọi người phải làm bù cho đủ”. Đội cần:

1. Giảm ảnh hưởng sự cố theo quyền và chính sách áp dụng.
2. Cập nhật capacity còn lại **theo ngày hiện tại**, tránh trừ lại thời gian đã tiêu tốn.
3. Xem ENR-01 còn có thể đáp ứng Sprint Goal và DoD không.
4. Thương lượng lại phạm vi ENR-02 hoặc phần tái sử dụng ENG-01 chưa cần thiết.
5. Minh bạch tiến triển tới Sprint Goal, những item chưa Done.
6. Trong Retrospective, xem mô hình on-call/capacity đã phản ánh thực tế chưa.

**Đừng tự hạ DoD** hoặc báo PBI gần xong thành Done để duy trì biểu đồ.

### 10.2. Sự kiện B: phụ thuộc API chậm

ENR-03 cần sandbox mà bên ngoài không cung cấp được trong Sprint. Những quyết định hợp lý:

- Không kéo item này vào Sprint chỉ vì có effort estimate đẹp.
- Tập trung vào ENR-01 hoặc một lát cắt khác độc lập.
- Thực hiện một spike đủ nhỏ để xác minh contract, không gọi đó là thanh toán production.
- Product Owner cập nhật thứ tự khi có thông tin mới.
- Nếu phụ thuộc ảnh hưởng nhiều hạng mục, escalation tới đúng service/vendor owner.

**Không hợp lý:** tự ghi “90% Done” cho chức năng chưa thể test end-to-end với nguồn tin cậy.

### 10.3. Sự kiện C: kiểm thử tìm ra lỗi nghiêm trọng

PBI ENR-01 đã merge code nhưng integration test cho thấy tài khoản B có thể đọc quyền của A.

Điều kiện cần:

1. Không xem PBI đạt DoD.
2. Khắc phục theo mức rủi ro và quy trình bảo mật.
3. Kiểm tra quy tắc nghiệp vụ, kiểm thử xuyên danh tính và nguồn dữ liệu.
4. Điều chỉnh kế hoạch để dành năng lực sửa đúng, không nhận thêm UI không cần thiết.
5. Product Owner và Developers thảo luận phạm vi, nhưng **không thương lượng bỏ kiểm tra phân quyền bắt buộc**.

Đây là lý do effort và buffer không thay được **một chiến lược chất lượng sớm**.

### 10.4. Sự kiện D: phản hồi người học làm giả thuyết sai

Đội tin rằng học viên bỏ dở vì không nhìn thấy nút “Vào bài”. Sau khi quan sát, họ thấy nhiều người đã có nút nhưng không được cấp entitlement đúng.

Hướng phản ứng:

- Product Owner nhìn lại vấn đề và ưu tiên.
- Developers xác định rủi ro dữ liệu và đường sửa.
- Nếu Sprint Goal vẫn là “vào bài đúng quyền”, điều chỉnh chi tiết implementation để giải quyết nguyên nhân thật.
- Nếu Sprint Goal trở nên lỗi thời, Scrum Guide quy định **Product Owner có thẩm quyền hủy Sprint**; không hủy chỉ vì một task khó hơn dự đoán.
- Bằng chứng mới cần làm Product Backlog và kế hoạch tiếp theo tốt hơn.

Mục tiêu Agile là **thích ứng dựa trên dữ liệu**, không phải bảo vệ kế hoạch ban đầu bằng mọi giá.

### 10.5. Sự kiện E: team member nghỉ đột xuất

Khi người nắm contract vắng mặt:

1. Xác định capability nào bị ảnh hưởng.
2. Xem tài liệu/test/owner có đủ để người khác làm đúng không.
3. Pair hoặc hỗ trợ từ chuyên gia khi được phép.
4. Đổi thứ tự hoặc phạm vi nếu không an toàn để tiếp tục.
5. Không đặt toàn bộ rủi ro vào “người thay thế phải học xong trong một ngày”.

Sau Sprint, xem cần cải thiện **khả năng chia sẻ tri thức** hay contract để giảm phụ thuộc cá nhân.

### 10.6. Replanning không đồng nghĩa thay Sprint Goal mỗi ngày

Theo Scrum:

- **Sprint Goal** tạo tập trung và ổn định hướng giá trị trong Sprint.
- **Sprint Backlog** được Developers thích ứng khi học thêm.
- **Product Owner** giúp làm rõ/đàm phán scope khi cần.
- **DoD** bảo vệ chất lượng.
- Một Sprint có thể bị hủy **chỉ khi Sprint Goal trở nên lỗi thời**, với thẩm quyền Product Owner.

Nếu đội phải thay mục tiêu mỗi ngày chỉ vì yêu cầu mới của stakeholder, cần kiểm tra **thứ tự Product Backlog, quyền và loại công việc**; không nên coi đó là biểu hiện Agile càng linh hoạt càng tốt.

### 10.7. Cập nhật dự báo bằng dữ liệu mới nhất

Khi một giả định thay đổi, bản kế hoạch nên ghi:

~~~text
REFORECAST DATE:
  [Ngay/cua so, nhu cau can ra quyet dinh]

CURRENT GOAL:
  [Sprint Goal hoac service outcome]

DONE WITH EVIDENCE:
  [PBI dat DoD, build, behavior]

CURRENT WIP / AGE:
  [Danh sach item chua Done va tuoi]

CAPACITY REMAINING:
  [Ngay/ky nang con lai, khong dung capacity ban dau]

DEPENDENCIES:
  [Blocked, owner, dieu kien, rui ro]

SCENARIOS:
  [Neu A/B, dieu nao co the Done va dieu nao khong]

QUALITY GUARDRAILS:
  [DoD/security/privacy/operations]

DECISIONS NEEDED:
  [PO/Developers/service owner/quan ly co quyen]

NEXT CHECK:
  [Su kien co nghia, khong chi ngay bao cao]
~~~

Mẫu này dùng để giúp đội **đưa ra một lựa chọn**. Nó không cần thành một báo cáo hành chính dài mỗi ngày.

## 11. Tình huống tổng hợp từng bước: một Sprint hai tuần của nhóm ghi danh

> **Toàn bộ con số, tên người, thời lượng và kết quả trong tình huống này đều giả định** để luyện lập kế hoạch. Không suy ra đó là chuẩn hiệu suất hoặc số liệu thực của một tổ chức.

Đội phụ trách năng lực ghi danh cho nền tảng học có năm Developers: Lan, Minh, Phương, Quang và Trang. Product Owner có quyền quản lý một Product Backlog cho sản phẩm; Scrum Master hỗ trợ hiệu quả Scrum. Đội đã làm một số Sprint và có CI cơ bản nhưng contract entitlement chưa được chuẩn hóa.

### 11.1. Đầu vào trước Sprint

**Product Goal:** học viên đủ điều kiện tự ghi danh và vào bài đầu đúng quyền trên các luồng được hỗ trợ.

**Bối cảnh người dùng:** một số học viên đã nhận xác nhận ghi danh miễn phí nhưng không thể mở bài; một số khác nhìn trạng thái chưa rõ hoặc bị cấp quyền không đúng khi yêu cầu lặp.

**Các giả định:**

- Khóa miễn phí có ý nghĩa và đúng với sản phẩm đang học.
- Quy tắc entitlement được Product Owner và Developers liên quan chốt đủ sớm.
- Môi trường test có các identity và permission cases phù hợp.
- Một phần hỗ trợ production đã được dự trù trong capacity.
- Sandbox cho nhà cung cấp thanh toán trả phí chưa sẵn sàng và không trở thành ràng buộc Sprint Goal.

### 11.2. Bản capacity nhóm

| Người | Nghỉ | Support | Nghĩa vụ khác | Net capacity |
|---|---:|---:|---:|---:|
| Lan (API) | 2 | 1 | 1 | **6** |
| Minh (UI) | 0 | 2 | 1 | **7** |
| Phương (integration quality) | 1 | 1 | 1 | **7** |
| Quang (full-stack) | 0 | 1 | 2 | **7** |
| Trang (CI/platform) | 1 | 1 | 2 | **6** |
| **Tổng** | **4** | **6** | **7** | **33** |

Mỗi người có 10 ngày lịch công trong ví dụ, nên gross capacity 50 person-days. **Phần trừ là các khoản riêng biệt**; nếu một hoạt động như kiểm thử của PBI được ước lượng trong PBI thì không trừ lại từ net.

### 11.3. Product Backlog ban đầu

| Thứ tự minh họa | PBI | Giá trị/rủi ro | Effort range | Tình trạng dependency |
|---|---|---|---:|---|
| 1 | **ENR-01** — ghi danh miễn phí và vào bài đầu | Giá trị end-to-end; quyền đúng | 10–15 | DEP-01, DEP-02 cần kiểm chứng |
| 2 | **ENR-02** — thông báo và xử lý không đủ điều kiện | Tránh hiểu nhầm/cấp quyền sai | 6–10 | DEP-03 UX cần làm rõ |
| 3 | **ENG-01** — cải thiện CI contract fixture tái sử dụng | Giảm lỗi contract về sau | 4–7 | DEP-05 cần quyền |
| 4 | **ANL-01** — theo dõi sự kiện vào bài đầu | Kiểm chứng outcome, bảo vệ dữ liệu | 3–6 | Metric contract/consent |
| 5 | **ENR-03** — thanh toán mới | Giá trị tương lai nhưng rủi ro đối tác cao | 9–18 | DEP-04 chưa sẵn |
| 6 | **OPS-01** — cải tiến pipeline rộng | Có thể giúp nhiều team | 5–11 | Quyền platform và ưu tiên |

**Không phải Product Owner bắt buộc tự sắp theo đúng số thứ tự trên**; bảng cho biết cách nhóm trao đổi một thứ tự có lý do. Các PBI kỹ thuật cần minh bạch quan hệ với Product Goal và ranh giới dịch vụ.

### 11.4. Refinement trước Planning: điều gì phải được biết?

Đội chọn ENR-01 để làm rõ trước:

1. Học viên “đủ điều kiện” là ai?
2. Ghi danh miễn phí có tạo entitlement ngay hay phụ thuộc điều kiện nào?
3. Nếu gửi yêu cầu trùng, hệ thống xử lý thế nào?
4. Người dùng khác có thể đọc hoặc sử dụng quyền đó không?
5. Dữ liệu giao diện lấy từ nguồn đáng tin nào?
6. Khi API lỗi/timeout, thông báo và hành vi có trung thực không?
7. Test nào đủ để minh bạch DoD, môi trường nào cần?
8. Khi nào Product Owner xác nhận các điều kiện nghiệp vụ còn mở?

Nếu không trả lời được những câu hỏi cốt lõi, đội có thể **giảm phạm vi chọn ban đầu hoặc làm rõ/spike** trước khi đưa một mục tiêu quá rộng vào Sprint.

### 11.5. Một tập acceptance examples

~~~gherkin
Feature: Ghi danh mien phi va truy cap bai dau

  Scenario: Hoc vien du dieu kien ghi danh thanh cong
    Given hoc vien A du dieu kien ghi danh khoa mien phi K
    When A yeu cau ghi danh K
    Then he thong luu ghi danh hop le
    And A nhan dung quyen hoc theo chinh sach
    And A co the vao bai dau cua K

  Scenario: Tai khoan khac khong xem duoc quyen
    Given hoc vien A co quyen hoc cua khoa K
    And hoc vien B khac A da dang nhap
    When B yeu cau truy cap quyen hoc cua A
    Then he thong tu choi theo quy tac phan quyen

  Scenario: Gui lai yeu cau khong tao ghi danh sai
    Given hoc vien A da ghi danh hop le khoa K
    When A gui lai yeu cau ghi danh K
    Then he thong khong tao ban ghi/quyen trung sai
    And thong bao ket qua phu hop chinh sach
~~~

Gherkin là **cách mô tả hành vi**; chưa phải bằng chứng test chạy. Developers cần xây test implementation, chuẩn bị test data/identities và chạy trên build/môi trường thích hợp.

### 11.6. Sprint Goal và lựa chọn PBIs

Sau refinement:

**Sprint Goal:**

> “Học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu an toàn trên một Increment tích hợp.”

**Kế hoạch ban đầu minh họa:**

- ENR-01 là lõi.
- ENR-02 chọn những trường hợp cần rõ cho luồng đang hỗ trợ; mở rộng trải nghiệm có thể thương lượng theo capacity.
- ENG-01 thử hoàn tất phần fixture tái sử dụng nếu quyền và thời gian cho phép; mọi kiểm tra bắt buộc của ENR-01 vẫn thuộc ENR-01.
- ENR-03 không được chọn vì sandbox chưa sẵn sàng.

Tổng effort range ba item được cân nhắc là 20–32 person-days so với 33 khả dụng; đội đánh dấu **độ tin cậy thấp đối với việc hoàn tất tất cả phạm vi mở rộng** và không sử dụng kết quả phép cộng để cam kết chắc chắn.

### 11.7. Diễn tiến trong mười ngày làm việc

| Ngày | Thông tin mới/hoạt động | Quyết định hướng tới Sprint Goal |
|---|---|---|
| **1** | Planning, chốt mục tiêu và các giả định trọng yếu | Ưu tiên ENR-01, thống nhất DoD và rủi ro quyền |
| **2** | Pair API–UI–quality làm rõ trạng thái và contract | Không code hai định nghĩa entitlement khác nhau |
| **3** | Lát cắt đầu tiên chạy qua CI, phát hiện test authz chưa đủ | Bổ sung bằng chứng phù hợp, không gọi Done sớm |
| **4** | Một API contract đổi trường trạng thái | Phối hợp trực tiếp, cập nhật contract test |
| **5** | Có incident production cần thêm năng lực | Reforecast capacity và phạm vi mở rộng, không hạ DoD |
| **6** | ENR-02 phần copy/validation còn chưa rõ | Product Owner làm rõ, chọn phần thực sự cần cho goal |
| **7** | ENR-01 đạt các kiểm tra tích hợp chính trong môi trường phù hợp | Chỉ xác nhận Done sau khi đủ DoD |
| **8** | Người học thử hành trình và nêu một điểm khó hiểu | Điều chỉnh nội dung nếu nằm trong goal và capacity |
| **9** | Kiểm tra regression, phân quyền, dữ liệu và Increment | Minh bạch những phần chưa Done |
| **10** | Sprint Review và Retrospective | Kiểm tra sản phẩm/outcome sơ bộ; quyết định backlog và cải tiến |

Bảng không phải **lịch Scrum chính thức ngày nào bắt buộc làm gì**; nó minh họa cách liên tục inspect/adapt. Scrum không yêu cầu đợi ngày 10 mới có Increment hoặc mới được nhận feedback.

### 11.8. Incident ngày 5: capacity đổi nhưng Sprint Goal chưa tự động đổi

Giả định incident cần sáu ngày công **thêm** ngoài phần support đã dự trù. Capacity toàn Sprint trong kịch bản mới là:

\[
33 - 6=27\ \text{person-days}
\]

Giả sử ENR-01 cần thực tế 14 ngày công (trong range), phần ENR-02 được làm hợp lý 7 ngày và ENG-01 phần tối thiểu 4 ngày, tổng effort thực của ba nhóm công việc minh họa là:

\[
14+7+4=25\ \text{person-days}
\]

Kết quả này **không bảo đảm** tất cả Done chỉ vì 25 nhỏ hơn 27: có sequencing, chuyên môn, dependency và kiểm chứng. Nếu incident liên quan người giữ contract hoặc test environment không sẵn sàng, vẫn có thể trễ. Đội ưu tiên **đảm bảo ENR-01 đáp ứng DoD**, rồi thảo luận phần mở rộng ENR-02/ENG-01 dựa trên khả năng còn lại.

### 11.9. Kết quả Sprint có thể khác dự đoán

Giả sử cuối Sprint:

- **ENR-01 Done:** học viên đủ điều kiện ghi danh và vào bài đầu trên Increment tích hợp đáp ứng DoD.
- **ENR-02 một phần Done:** một lát cắt xử lý trạng thái không hợp lệ có thể sử dụng và đạt DoD; những trường hợp mở rộng chưa Done được đưa lại Product Backlog hoặc làm rõ tiếp.
- **ENG-01 chưa Done:** fixture CI tái sử dụng còn vướng permission, không báo hoàn tất; các test bắt buộc của ENR-01 vẫn đã chạy và có bằng chứng.
- **ENR-03 chưa bắt đầu:** phụ thuộc bên ngoài chưa đủ, không mở WIP vô ích.

**Sprint Goal có thể được đánh giá đạt** nếu ENR-01 thật sự tạo khả năng đã nêu và đạt DoD, dù không hoàn tất mọi PBI dự kiến. Việc Product Owner/Developers ghi nhận phạm vi còn lại và quyết định tiếp là minh bạch; không tự ghi tất cả “100% hoàn thành” để báo cáo đẹp.

### 11.10. Review không chỉ hỏi bao nhiêu ticket Done

Trong Sprint Review, stakeholders có thể kiểm tra:

1. Một học viên mới có ghi danh được khóa miễn phí hợp lệ không?
2. Sau ghi danh, quyền truy cập có đúng với nguồn dữ liệu không?
3. Người khác có bị từ chối đúng khi truy cập trái quyền không?
4. Người học có hiểu trạng thái và bước tiếp theo không?
5. Sản phẩm đã hỗ trợ được cohort nào, chưa hỗ trợ cohort nào?
6. Có phản hồi nào làm thay đổi thứ tự Product Backlog cho Sprint sau?

Với một tính năng chưa phát hành, chỉ nên kết luận **Increment đạt DoD và feedback trong môi trường kiểm tra** theo bằng chứng có, không tuyên bố outcome toàn bộ học viên đã cải thiện.

### 11.11. Retrospective chọn đúng cơ chế cần sửa

Nhóm quan sát:

- DEP-01 được làm rõ sau một phiên trao đổi trực tiếp, giảm hiểu nhầm.
- DEP-02 mất thời gian vì test identities không tự tạo được.
- ENG-01 vướng quyền pipeline từ platform.
- Incident ngoài dự trù gây biến động capacity.

Một cải tiến nhỏ:

> “Trong hai Sprint tiếp theo, chúng ta chuẩn hóa test identities/contract fixture cho entitlement, cùng service owner xác nhận quyền CI, và theo dõi thời điểm integration mismatch được phát hiện cùng work item age. Đừng mở thêm PBI nếu quality gate của lát cắt hiện tại chưa đạt.”

Đây là một thử nghiệm vừa **kỹ thuật**, vừa **phối hợp**, vừa tăng khả năng lập kế hoạch. Nó hữu ích hơn yêu cầu mọi người “estimate chính xác hơn” khi nguyên nhân lớn nằm ở môi trường và phụ thuộc.

### 11.12. Sau Sprint, dự báo Sprint tiếp theo phải cập nhật

Đội đã học rằng:

- Có những trường hợp quyền học mà refinement ban đầu thiếu.
- Test environment có hạn chế xác định.
- Năng lực on-call có thể dao động.
- Quyền tự động hóa CI cần làm rõ ở cấp service.
- Người học cần thêm thông tin về tình huống không đủ điều kiện.

Các bài học này thay đổi **cách chia PBI, risk assumptions, capacity reserve và thứ tự Product Backlog**. Không nên bê nguyên bảng estimate ban đầu vào Sprint tiếp theo như chưa có bằng chứng mới.

## 12. Kết nối kế hoạch ngắn hạn với chất lượng và outcome

Một bản kế hoạch chỉ nhìn số item Done có nguy cơ tối ưu output cục bộ, nhất là khi deadline tạo áp lực. **Năng lực giao sản phẩm** phải được đo cùng **giá trị và chất lượng**.

### 12.1. Bốn loại bằng chứng

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| **Tiến triển mục tiêu** | Sprint Goal/Product Goal có được hỗ trợ? | Lát cắt đã kiểm chứng, trade-off đã đưa ra |
| **Chất lượng Increment** | Có phần mềm có thể sử dụng đạt DoD không? | Integration/authorization tests, review và evidence trên build |
| **Flow** | Công việc từ Started tới Done với bao nhiêu WIP/age? | WIP, throughput, work item age, cycle time, blockers |
| **Outcome** | Học viên có thực sự đạt kết quả? | Ghi danh hợp lệ, quyền đúng, vào bài, sự cố và feedback |

**Không dùng chỉ một lớp để thay các lớp khác.** Throughput tăng không chứng minh value nếu nhiều ticket ít giá trị; conversion tăng không biện minh cho lỗi cấp quyền; test count cao không chứng minh rủi ro đã được bảo vệ.

### 12.2. Outcome metric contract cho luồng ghi danh

Ví dụ đội muốn theo dõi tỷ lệ học viên đủ điều kiện vào bài đầu **trong 24 giờ sau ghi danh thành công**:

\[
\text{Tỷ lệ vào bài đầu}
=\frac{\text{Số lượt ghi danh hợp lệ có hành vi vào bài trong 24 giờ}}
{\text{Số lượt ghi danh hợp lệ đã đủ thời gian theo dõi 24 giờ}}
\times 100\%
\]

Định nghĩa cần nêu:

- Một lượt ghi danh hay một học viên được tính?
- Trạng thái “hợp lệ” lấy từ nguồn nào?
- Cửa sổ 24 giờ tính từ mốc nào?
- Những lượt vừa ghi danh lúc chốt báo cáo chưa đủ 24 giờ có được loại khỏi cohort theo quy tắc nhất quán không?
- Học viên miễn phí và trả phí có gộp không?
- Đếm sự kiện vào bài theo đúng danh tính/khóa và tránh trùng thế nào?
- Tracking có tuân thủ yêu cầu riêng tư, retention và quyền truy cập không?

Nếu người mới ghi danh cách thời điểm chốt hai phút, **không được coi họ thất bại mục tiêu 24 giờ**. Dữ liệu outcome có thể đến chậm hơn nhịp Sprint; điều đó không làm Sprint Review vô ích nếu Increment và tín hiệu sớm vẫn được kiểm tra trung thực.

### 12.3. Chất lượng không được bù bằng số lượng

Một dashboard có thể ghi:

~~~text
PBI Done:             8
Tests passed:         450
Conversion observed:  88%
Authz incident:       1 nghiem trong
~~~

Không thể kết luận “Sprint thành công tuyệt đối” vì ba số đầu nhìn tốt. **Một sự cố phân quyền nghiêm trọng là tín hiệu phải xử lý theo chính sách**; không có phép cộng điểm cho phép đổi rủi ro người dùng lấy throughput.

### 12.4. Metric contract cho flow

~~~text
FLOW METRIC:
  Cycle Time — PBI integrated practice v1

POPULATION:
  Product Backlog Items co cung loai va granularity.

STARTED:
  Timestamp item bat dau active delivery.

FINISHED:
  Timestamp item dat DoD theo workflow cua san pham.

UNIT:
  Calendar hours/days; timezone va data cutoff ro.

BLOCKED:
  Tinh trong cycle time trong boundary.

REOPEN:
  Quy tac ghi nhan Done cuoi va rework duoc cong bo.

EXCLUDE:
  Canceled/duplicate theo policy nhat quan, khong xoa de lam dep.

CONTEXT:
  Work mix, DoD version, workflow change, CI/people/vendor changes.
~~~

Không được so “Done trước = code merged” với “Done sau = đạt DoD” như cùng một chỉ số. Một thay đổi cách làm tốt có thể làm throughput thấp tạm thời do **nâng chuẩn chất lượng**, không đồng nghĩa năng lực sản phẩm kém hơn.

### 12.5. Work item age cần xem cả item chưa Done

Giả sử một kỳ có bốn PBI Done, cycle time lần lượt **3, 5, 6, 8 ngày lịch**. Trung vị cycle time là:

\[
\frac{5+6}{2}=5{,}5\ \text{ngày lịch}
\]

Nhưng vẫn còn hai PBI WIP có tuổi **14 và 19 ngày**. Không được tuyên bố “mọi PBI đều chỉ mất 5,5 ngày”; một số item khó đang bị kẹt chưa đi vào mẫu Completed. Cần xem blocker, dependency và cách giúp item gần Done.

### 12.6. Throughput khác velocity

Throughput đếm **work items Done** trong một kỳ; story points/velocity là quy ước ước lượng/đếm điểm nội bộ nếu đội dùng. Nếu một PBI được tách thành bốn task rồi đóng bốn task:

- Có thể có **bốn tasks Done**.
- Nhưng chưa chắc có **một PBI đạt DoD**.
- Không thể báo “throughput PBI tăng bốn lần” chỉ vì thay cách chia.

Muốn sử dụng throughput cho dự báo, cần giữ **đơn vị item tương đối nhất quán** và nhìn work mix, flow state, quality.

### 12.7. Không suy ra hiệu quả từ tương quan đơn giản

Nếu sau ba Sprint cycle time giảm nhưng cùng kỳ đội:

- Thêm một Developer chuyên CI.
- Chuyển từ feature khó sang sửa UI nhỏ.
- Đổi Definition of Done.
- Cải thiện test environment.
- Thay cách chia PBI.

...thì không thể nói một mình “Sprint Planning theo capacity đã làm năng suất tăng 40%”. Cần mô tả các thay đổi đồng thời, xem nhiều kỳ và kết hợp evidence.

**Giá trị của đo lường là giúp đội quyết định đúng tiếp theo**, không phải tạo một câu tuyên bố nhân quả hấp dẫn vượt dữ liệu.

### 12.8. Health check của Sprint không phải compliance checklist

Một kiểm tra ngắn hữu ích giữa Sprint:

| Câu hỏi | Nếu câu trả lời đáng lo |
|---|---|
| Sprint Goal có còn khả thi với capacity còn lại? | Reforecast và thương lượng phạm vi |
| Có PBI gần Done nhưng blocked do điều kiện nhỏ? | Giúp tháo trước khi mở việc mới |
| Có test quan trọng đang bị bỏ qua? | Dừng việc gọi Done, xử lý quality |
| Có dependency ngoài quyền chưa cập nhật? | Nêu owner, điều kiện, phương án |
| Có phản hồi người dùng làm giả định sai? | PO xem thứ tự/giải pháp |
| Các dữ liệu flow/outcome có cùng định nghĩa? | Sửa metric contract trước kết luận |

Không cần họp cả giờ để trả lời sáu câu hỏi. Quan trọng là **có một quyết định và hành động khi tín hiệu đổi**.

## 13. Quyền quyết định, nhịp phối hợp và dự báo khi nhiều nhóm cùng tham gia

Một bản kế hoạch ngắn hạn có thể thất bại không vì Developers ước lượng sai, mà vì **những quyết định nằm ngoài quyền của họ** hoặc các nhóm khác cũng có lịch ưu tiên riêng. Phối hợp đúng cần nêu rõ **ai có thể chốt điều gì và điều kiện nào đủ để bắt đầu/tính Done**.

### 13.1. Bản đồ quyền quyết định tối thiểu

| Quyết định | Ai chịu trách nhiệm cốt lõi trong bối cảnh phù hợp | Ai cần được tham gia |
|---|---|---|
| Giá trị sản phẩm, thứ tự Product Backlog trong Scrum | **Product Owner** | Stakeholders, Developers, chuyên gia |
| Sizing và lượng công việc chọn vào Sprint | **Developers** | Product Owner làm rõ giá trị; Scrum Team xác định Sprint Goal |
| Kế hoạch triển khai và điều chỉnh Sprint Backlog | **Developers** | Product Owner khi phạm vi/giá trị đổi |
| Hiệu quả Scrum và cải tiến cách áp dụng | **Scrum Master** | Scrum Team và tổ chức |
| Quy tắc entitlement và hành vi nghiệp vụ | Người có quyền nghiệp vụ/sản phẩm; PO chịu trách nhiệm giá trị/backlog | Developers và chuyên gia pháp lý/bảo mật khi cần |
| Thay đổi API/service contract giữa sản phẩm độc lập | Service owners và những người có quyền theo tổ chức | Product teams dùng dịch vụ |
| Điều kiện an toàn/pháp lý bắt buộc | Vai trò có thẩm quyền theo tổ chức/quy định | Product Owner, Developers, operations |
| Lựa chọn release và phạm vi rollout | Theo chính sách release và quyền được tổ chức xác định | Product Owner, Developers, vận hành, kiểm soát cần thiết |

Đây là **bản đồ trách nhiệm thực hành**, không thêm các Scrum accountabilities mới. Product Owner không tự duyệt mọi class/code; Developers không tự đổi ưu tiên kinh doanh; Scrum Master không biến thành quản lý giao task.

### 13.2. Dependencies giữa các sản phẩm không thể giải bằng quyền PO của một sản phẩm

Giả sử Product Team ghi danh muốn dùng một API mới từ **Developer Platform** phục vụ năm sản phẩm. Nếu Platform là sản phẩm/dịch vụ độc lập, nó có backlog/owner hoặc chính sách vận hành riêng.

Một thỏa thuận hữu ích cần có:

- Mục tiêu cần dùng dịch vụ và tác động người dùng.
- Contract và loại thay đổi tương thích.
- Mức ưu tiên, service expectation và cách tiếp nhận yêu cầu.
- Owner của việc ra quyết định khi conflict.
- Phương án khi điều kiện trễ.
- Cách kiểm chứng và báo sự cố.

Không nên tự coi Product Owner của sản phẩm học viên có quyền đổi toàn bộ ưu tiên platform chỉ vì Sprint Goal của mình đang cần.

### 13.3. Nhịp phối hợp nên theo nhu cầu quyết định

| Hoạt động | Câu hỏi quyết định | Khi nào hữu ích |
|---|---|---|
| **Refinement liên quan nhiều bên** | PBI có hành vi, phụ thuộc và AC gì chưa rõ? | Trước khi chọn PBI có rủi ro |
| **Sprint Planning** nếu dùng Scrum | Vì sao Sprint có giá trị, điều gì có thể Done, cách làm? | Đầu mỗi Sprint |
| **Daily Scrum** nếu dùng Scrum | Có tiến triển tới Sprint Goal; điều chỉnh gì hôm nay? | Mỗi ngày làm việc, 15 phút |
| **Dependency sync ngắn** | Item nào bị chặn, ai giúp và điều kiện gỡ? | Khi có phụ thuộc xuyên nhóm thực |
| **CI/Integration feedback** | Contract, test và dữ liệu đã đúng chưa? | Thường xuyên theo thay đổi |
| **Sprint Review** nếu dùng Scrum | Increment cho thấy điều gì; Product Backlog cần đổi gì? | Cuối Sprint |
| **Retrospective** nếu dùng Scrum | Quy trình/chất lượng nên cải thiện thế nào? | Cuối Sprint |
| **Service review** | WIP/age/SLE và chất lượng dịch vụ ra sao? | Theo policy của luồng Kanban |

Không phải mỗi hàng cần một cuộc họp mới. Một bản ghi quyết định ngắn, test contract hoặc trao đổi trực tiếp có thể **giảm thời gian chờ** tốt hơn một lịch đồng bộ hàng ngày quá đông.

### 13.4. Khi một blocker đòi escalation

Escalation không phải “đổ việc lên quản lý”, mà là chuyển quyết định **đúng người có quyền**:

1. PBI nào và mục tiêu nào bị ảnh hưởng?
2. Điều kiện cụ thể nào chưa được đáp ứng?
3. Đội đã thử tháo trở ngại trong phạm vi nào?
4. Cần quyết định về quyền, contract, ngân sách, rủi ro hay thứ tự ưu tiên?
5. Có những phương án và đánh đổi nào?
6. Nếu không có quyết định, đội sẽ làm gì để vẫn giữ chất lượng?

Ví dụ:

> “ENG-01 đang bị chặn do quyền sửa CI pipeline thuộc platform. Để tích hợp entitlement an toàn, ENR-01 đã có test bắt buộc chạy trong quy trình hiện tại; phần fixture tái sử dụng dự kiến có thể trễ. Chúng tôi cần platform owner xác nhận quyền/chính sách self-service. Nếu chưa có trước mốc kiểm tra, đội vẫn giữ DoD của ENR-01 và đưa ENG-01 trở lại Product Backlog để ưu tiên sau.”

Thông tin trên **đưa ra một lựa chọn có căn cứ**, không chỉ ghi “bị block”.

### 13.5. Phân biệt ngày bắt đầu, ngày hoàn tất và mốc ra quyết định

Một PBI có thể:

- Bắt đầu sau khi contract rõ.
- Hoàn tất khi đáp ứng DoD và có evidence.
- Được release ở thời điểm phù hợp policy.
- Được đánh giá outcome khi người dùng có đủ thời gian sử dụng.

Một deadline hợp đồng về release không đồng nghĩa thời điểm mọi giả thuyết sản phẩm được xác nhận. Một Sprint không tự là mốc release bắt buộc. **Lập kế hoạch tốt nêu riêng những mốc này** để không tạo hứa hẹn mơ hồ.

### 13.6. Khi có deadline bắt buộc

Giả sử kỳ khai giảng ngày 1 tháng 9 yêu cầu hỗ trợ ghi danh cho một cohort nhất định.

Đội cần:

1. Xác minh **nghĩa vụ tối thiểu**, các trường hợp bắt buộc và guardrails.
2. Sắp thứ tự những lát cắt có giá trị và rủi ro cao.
3. Tạo Increment và kiểm chứng sớm, không chờ tuần cuối.
4. Dự báo theo data và giả định, công bố những phụ thuộc chưa kiểm chứng.
5. Điều chỉnh phạm vi **nếu được phép**; không tự bỏ nghĩa vụ pháp lý/hợp đồng.
6. Khi phạm vi không thể giảm, báo trade-off về năng lực, thời gian, phương án và quyết định đúng thẩm quyền.

Đừng hứa cùng lúc **ngày cố định, mọi tính năng cố định, nguồn lực cố định, rủi ro không thay đổi và chất lượng tuyệt đối** nếu chưa có cơ sở. Agile giúp quản lý bất định, không biến điều phi thực tế thành chắc chắn.

### 13.7. Công việc dự kiến và công việc khẩn cần có chính sách

Một đội có thể định nghĩa:

- **Lát cắt sản phẩm:** hướng Sprint Goal hoặc Product Goal.
- **Sự cố production:** xử lý theo severity và incident process.
- **Việc hỗ trợ/lặp:** theo service policy và WIP.
- **Cải tiến kỹ thuật:** ưu tiên theo rủi ro và khả năng tạo Increment.

Khi một incident khẩn xuất hiện, đội không cần “giấu” capacity đã bị tiêu tốn. Họ cần **ghi tác động lên forecast và tiến triển mục tiêu**, đồng thời kiểm tra cách phân luồng/đội trực nếu vấn đề lặp.

## 14. Hai mươi phản mẫu của lập kế hoạch ngắn hạn

### 14.1. “Năm người, mười ngày, chắc chắn có 50 ngày công giao PBI”

**Sai ở đâu:** bỏ nghỉ phép, on-call, nghĩa vụ và kỹ năng.

**Cách sửa:** tính gross/net capacity không trùng lặp; xem kỹ năng và phụ thuộc; reforecast khi điều kiện đổi.

### 14.2. “Story point bằng đúng một số giờ”

**Sai ở đâu:** thang ước lượng tương đối bị coi là đơn vị vật lý chính xác.

**Cách sửa:** dùng points có giới hạn nội bộ hoặc forecast flow theo dữ liệu; không ép quy đổi point sang ngày để giao KPI.

### 14.3. “Tổng effort nhỏ hơn capacity thì chắc chắn Done”

**Sai ở đâu:** quên trình tự, chuyên môn, environment, dữ liệu và biến động.

**Cách sửa:** vẽ dependency, kiểm tra skill bottleneck và DoD, dùng kịch bản/buffer có căn cứ.

### 14.4. “Estimate càng chi tiết thì tương lai càng chắc”

**Sai ở đâu:** thêm chữ số thập phân không giảm thiếu hiểu biết về API/nhu cầu.

**Cách sửa:** chia lát cắt, thử contract/discovery, dùng khoảng ước lượng và cập nhật giả định.

### 14.5. “Mọi người phải kín 100% capacity”

**Sai ở đâu:** WIP và hàng chờ tăng, không ai giúp item gần Done.

**Cách sửa:** giới hạn WIP, ưu tiên hoàn tất và giữ khả năng ứng phó với rủi ro.

### 14.6. “Có thể làm xong task UI trước, test để Sprint sau”

**Sai ở đâu:** Code Complete bị báo là Increment Done dù DoD chưa đạt.

**Cách sửa:** chia dọc, tích hợp và kiểm chứng theo rủi ro sớm; giữ DoD trong cùng lát cắt.

### 14.7. “Mọi PBI đều là commit cố định ngay ngày đầu Sprint”

**Sai ở đâu:** nhầm các PBI được chọn với commitment chính thức của Sprint Backlog.

**Cách sửa:** Sprint Goal là commitment; Developers điều chỉnh kế hoạch và thương lượng scope với Product Owner khi học thêm, không hạ quality.

### 14.8. “Mọi thay đổi đều được vì Agile linh hoạt”

**Sai ở đâu:** Sprint Goal mất ý nghĩa, Product Backlog bị thay bằng người nói lớn nhất.

**Cách sửa:** giữ trọng tâm mục tiêu, quyền ưu tiên và chính sách xử lý việc khẩn.

### 14.9. “Thêm vài ngày công sẽ giải quyết API chưa có”

**Sai ở đâu:** capacity không tạo được điều kiện từ nhà cung cấp.

**Cách sửa:** xác minh contract/sandbox, chọn item độc lập, spike có giới hạn và escalation.

### 14.10. “Mock hoạt động là thanh toán thật Done”

**Sai ở đâu:** prototype/stub không chứng minh tích hợp nguồn giao dịch tin cậy.

**Cách sửa:** dùng mock để học có giới hạn, không báo vượt bằng chứng; kiểm chứng thực trước Done/release theo DoD.

### 14.11. “Ẩn blocked khỏi WIP để flow đẹp”

**Sai ở đâu:** giấu hàng chờ trong boundary và nhận thêm quá nhiều việc.

**Cách sửa:** tính blocked theo Definition of Workflow, xem age/owner và gỡ phụ thuộc.

### 14.12. “Đếm bốn subtasks Done bằng bốn PBIs”

**Sai ở đâu:** thay đổi đơn vị đo, tưởng throughput tăng.

**Cách sửa:** metric contract, cùng loại item và không đếm parent/subtask trùng.

### 14.13. “PBI nào Done nhanh thì toàn hệ thống nhanh”

**Sai ở đâu:** chỉ nhìn item hoàn tất, bỏ work item age của item bị kẹt.

**Cách sửa:** xem WIP, age, cycle time, blocked và DoD trong cùng boundary.

### 14.14. “Một dự báo có xác suất chỉ vì ghi 80%”

**Sai ở đâu:** xác suất thiếu dữ liệu, giả định tương quan và cửa sổ.

**Cách sửa:** phân biệt kịch bản với forecast xác suất; chỉ công bố xác suất khi có cơ sở, điều kiện và giới hạn.

### 14.15. “Tất cả rủi ro đều độc lập”

**Sai ở đâu:** nhiều PBI cùng phụ thuộc một environment, một người hoặc một provider.

**Cách sửa:** xem đồ thị phụ thuộc chung, rủi ro tương quan và lựa chọn giảm điểm nghẽn.

### 14.16. “Retrospective chỉ cần ước lượng sát hơn”

**Sai ở đâu:** nguyên nhân thực có thể là DoD, CI, dependency hoặc quyền.

**Cách sửa:** điều tra dữ liệu; chọn một cải tiến có owner và bằng chứng, không chỉ yêu cầu cá nhân dự đoán tốt hơn.

### 14.17. “Sprint Review là cuộc phê duyệt release”

**Sai ở đâu:** nhầm kiểm tra kết quả và thích ứng với gate phát hành; trì hoãn feedback không cần thiết.

**Cách sửa:** tách Increment đạt DoD, release theo chính sách và outcome quan sát được.

### 14.18. “Chỉ Product Owner phải lo giá trị; chỉ QA phải lo chất lượng”

**Sai ở đâu:** cắt rời cộng tác và trách nhiệm Developers đối với Increment.

**Cách sửa:** PO chịu trách nhiệm giá trị/Backlog; Developers tạo Increment đạt DoD, chuyên gia góp phần làm rõ và kiểm chứng.

### 14.19. “Thêm Scrum events sẽ tự giải quyết dependency”

**Sai ở đâu:** cuộc họp không thay quyền ra quyết định, test environment, contract hay team boundary.

**Cách sửa:** xem owner, điều kiện gỡ, API contract, CI, self-service và phối hợp đúng nơi; meeting chỉ là một phương tiện.

### 14.20. “Một Sprint tốt chứng minh quy trình mới tăng năng suất”

**Sai ở đâu:** loại công việc, nhân sự, tracking hoặc môi trường có thể cùng đổi.

**Cách sửa:** nhìn nhiều chu kỳ cùng định nghĩa, quality/outcome và các yếu tố gây nhiễu; nêu kết luận đúng mức.

## 15. Dự báo dựa trên dữ liệu lịch sử: có ích nhưng không phải lời tiên tri

Ngoài capacity và effort ranges, một đội có thể dùng dữ liệu **throughput và cycle time** khi workflow, loại item và Definition of Done đủ ổn định. Mục tiêu không phải tạo một ngày giao chắc chắn mà là **bổ sung góc nhìn thực nghiệm để kiểm tra lựa chọn scope**.

### 15.1. Ví dụ throughput tám tuần

Giả sử cùng một đội hoàn tất số PBI đạt DoD theo các tuần gần đây:

| Tuần | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Throughput PBI | 3 | 2 | 4 | 3 | 5 | 2 | 3 | 4 |

Tổng **26 PBI/8 tuần**, trung bình:

\[
\bar{T}=\frac{3+2+4+3+5+2+3+4}{8}
=\frac{26}{8}=3{,}25\ \text{PBI/tuần}
\]

Con số 3,25 **không có nghĩa** mỗi tuần chắc chắn hoàn tất 3,25 PBI hoặc một PBI bất kỳ chỉ mất 0,31 tuần. Đó là **trung bình của một tập quan sát nhỏ**, với loại công việc và cách đo phải nhất quán.

### 15.2. Hai tuần lịch sử có thể cho thấy biến động

Với các cặp tuần liên tiếp không chồng nhau:

| Cửa sổ hai tuần | PBI Done |
|---|---:|
| Tuần 1–2 | 3 + 2 = **5** |
| Tuần 3–4 | 4 + 3 = **7** |
| Tuần 5–6 | 5 + 2 = **7** |
| Tuần 7–8 | 3 + 4 = **7** |

Trong **bốn cửa sổ lịch sử này**, throughput quan sát là **5, 7, 7, 7 PBI/2 tuần**. Đó **không phải** khoảng chắc chắn kỳ sau cũng 5–7: các tuần tương lai có thể khác, đặc biệt nếu loại PBI khó hơn hoặc có incident.

Nếu đội cần năng lực giao một **PBI tích hợp rủi ro cao duy nhất**, các con số item-count của bốn tuần xử lý bug nhỏ **không cung cấp dự báo đáng tin** cho PBI đó. Nên phân loại công việc hoặc dùng dữ liệu bổ sung.

### 15.3. Forecast theo số item cần các điều kiện

Một câu dự báo tốt:

> “Trong các cửa sổ hai tuần gần đây, đội đã hoàn tất 5–7 PBI cùng định nghĩa. Với backlog gồm các item được chia tương tự, ít thay đổi lớn về capacity/dependency và DoD giữ nguyên, lịch sử cho thấy phạm vi khoảng đó đáng cân nhắc, **không phải cam kết**. Với ENR-03 phụ thuộc vendor chưa sẵn sàng, lịch sử này không giải quyết điều kiện bên ngoài.”

Không được bỏ phần **“với giả định...”** chỉ để tạo một con số chính xác phục vụ báo cáo.

### 15.4. Mô phỏng Monte Carlo có thể hỗ trợ khi dữ liệu đủ

Một phương án nâng cao là mô phỏng nhiều kịch bản throughput/cycle time dựa trên mẫu lịch sử để ước lượng phân phối thời gian hoàn tất một tập item.

Quy trình ý tưởng:

1. Chọn **đơn vị work item và workflow** nhất quán.
2. Lấy dữ liệu throughput theo khoảng thời gian phù hợp, có kiểm tra thiếu/méo dữ liệu.
3. Đánh giá **work mix và tính ổn định tương đối** so với backlog sắp tới.
4. Lặp nhiều lần việc lấy mẫu/tạo kịch bản theo giả định đã công bố.
5. Tính phân bố số item có thể Done trước một mốc hoặc mốc thời gian đạt tập item.
6. Kiểm tra độ nhạy khi throughput giảm, dependency trễ, capacity thay đổi.
7. Trình bày kết quả cùng **giả định, nguồn dữ liệu, quality guardrails và rủi ro không nằm trong mô hình**.

**Không tự bịa xác suất 85% hoặc 95% nếu chưa chạy mô hình trên dữ liệu phù hợp.** Những item phụ thuộc nhau, sự kiện hiếm lớn và PBI thay đổi kích thước có thể làm cách lấy mẫu đơn giản sai. Một mô phỏng với hàng nghìn lần lặp vẫn có thể cho kết luận kém nếu nguồn dữ liệu không đại diện.

### 15.5. Dự báo theo capacity và dự báo theo flow cần đối chiếu

| Capacity/effort view | Flow/historical view | Câu hỏi kết hợp |
|---|---|---|
| Có 33 person-days khả dụng | Lịch sử Done 5–7 PBI/2 tuần | Work items và DoD có tương đồng? |
| ENR-01 cần 10–15 effort | Cycle time có thể gồm chờ contract | Dependency nào làm duration dài? |
| Lan chỉ có sáu ngày khả dụng | Một số item blocked vì entitlement review | Có điểm nghẽn chuyên môn không? |
| Có buffer hợp lý cho incident | WIP và work item age đang tăng | Đội có bắt đầu quá nhiều việc không? |
| Nâng CI tốn effort tuần này | Cycle time/quality có thể cải thiện kỳ sau | Đầu tư kỹ thuật có cơ chế và bằng chứng gì? |

Nếu hai góc nhìn mâu thuẫn, **điều tra giả định** thay vì chọn con số làm kế hoạch “đẹp” hơn. Capacity thấp nhưng throughput lịch sử cao có thể do item kỳ trước nhỏ hơn; capacity cao nhưng throughput thấp có thể do dependency/DoD.

### 15.6. Quy tắc lập forecast có trách nhiệm

- Luôn nêu **loại item, Definition of Done, start/end, kỳ và dữ liệu nguồn**.
- Xem cả item chưa Done; không chỉ cherry-pick những việc nhanh.
- Không gộp bug nhỏ với migration lớn mà không kiểm tra tính đại diện.
- Ghi năng lực/người, provider, environment và ranh giới tổ chức đã đổi.
- Không biến estimate hay forecast thành KPI cá nhân.
- Giữ chất lượng và quyền người dùng là guardrails.
- Chỉ công bố mức chắc chắn tương ứng dữ liệu thật, không hơn.
- Dùng dự báo để **chọn scope/thứ tự và quyết định có cần giảm rủi ro**, không thay Product Owner hoặc Developers.

## 16. Bộ mẫu sử dụng trực tiếp khi lập kế hoạch ngắn hạn

Những mẫu dưới đây là **công cụ hỗ trợ cho bài thực hành**, không phải artifacts bắt buộc mới trong Scrum hay Kanban. Có thể rút gọn hoặc ghép vào Product Backlog, Sprint Backlog và service board đang có.

### 16.1. Short-Horizon Planning Canvas

~~~text
PRODUCT / SERVICE:
  [Nguoi dung, ranh gioi, gia tri]

MUC TIEU NGAN HAN:
  [Sprint Goal / service outcome, ly do co gia tri]

OUTCOME / QUALITY:
  [Ket qua nguoi dung, DoD va guardrails]

HORIZON:
  [Sprint / tuan / moc kiem tra]

CAPACITY:
  Gross:
  Known leave/support/other:
  Net:
  Skill bottlenecks:
  Important uncertainty:

SELECTED WORK / OPTIONS:
  Core:
  Valuable but adjustable:
  Not selected and why:

DEPENDENCIES:
  [Owner, contract, ready condition, impact]

RISK SCENARIOS:
  [Base, incident, vendor delay, quality discovery]

WORKFLOW & WIP:
  [Started, Finished, policies, blocked]

FEEDBACK:
  [Review, user feedback, service signals]

TRIGGERS TO REPLAN:
  [When and who can decide]

UNKNOWNS:
  [What has not been verified]
~~~

### 16.2. Capacity Sheet không tính trùng

| Người / chức năng | Ngày lịch | Nghỉ | Support | Nghĩa vụ khác ngoài PBI | Capacity cho PBI | Kỹ năng/điểm nghẽn |
|---|---:|---:|---:|---:|---:|---|
| A | | | | | | |
| B | | | | | | |
| C | | | | | | |
| **Tổng** | | | | | | |

Các câu hỏi kiểm tra:

1. Đây là **giờ/ngày theo lịch** hay person-days? Có cùng đơn vị không?
2. Nhiệm vụ support đã bao gồm trong effort PBI nào chưa?
3. Scrum events, CI maintenance, kiểm thử và pairing được hạch toán ở đâu?
4. Ai có quyền/kỹ năng thiết yếu, có thể chia sẻ tri thức hay không?
5. Capacity có cập nhật khi incident/nghỉ đột xuất không?
6. Có dùng bảng để ép cá nhân báo từng giờ hoặc loại bỏ thời gian học/quality không?

Nếu câu trả lời cuối là có, cần **sửa cách sử dụng bảng**, không tối ưu phép tính.

### 16.3. Dependency Card

~~~text
DEP ID:
  [Ten duy nhat, lien ket PBI]

VALUE / GOAL AFFECTED:
  [Sprint Goal, PBI, user impact]

NEEDED FROM:
  [Service/team/person co quyen]

REQUIRED BEHAVIOR:
  [Contract, API, data, decision, permission]

READY WHEN:
  [Co the kiem chung duoc]

CURRENT EVIDENCE:
  [Da co gi, chua co gi]

OWNER FOR NEXT STEP:
  [Dau moi cu the, ngay xem lai neu co]

IF DELAYED:
  [Alternative slice, spike, escalation, scope change]

QUALITY / SECURITY IMPACT:
  [Test, authz, privacy, policy]
~~~

Một Dependency Card nên được **đóng khi điều kiện thực sự đã đáp ứng**, không chỉ khi có một email hứa sẽ xong.

### 16.4. Estimate & Assumption Card

~~~text
PBI:
  [Hanh vi / result]

EFFORT ESTIMATE:
  [Range va don vi, neu su dung]

ASSUMED IN SCOPE:
  [Code, tests, integration, data, review DoD]

OUT OF SCOPE:
  [Khong dem trung, nhung van bao dam DoD]

UNKNOWNS:
  [Product, technical, dependency, operational]

SKILL BOTTLENECK:
  [Ai/capability can cho support]

DATA CONFIDENCE:
  [Lich su tuong dong hay phan doan cua team]

SPLITTING OPTIONS:
  [Vertical slices co gia tri]

CHECKPOINT:
  [Khi nao nhan thong tin moi de re-estimate]
~~~

Không cần mọi PBI nhỏ phải có biểu mẫu này. Những item **phụ thuộc cao, khó chia, rủi ro lớn** thường xứng đáng được làm rõ như vậy.

### 16.5. Scenario Decision Table

| Kịch bản | Điều kiện kích hoạt | Capacity/dependency | Điều bảo vệ | Scope có thể điều chỉnh | Ai quyết định |
|---|---|---|---|---|---|
| Cơ sở | Các giả định chính ổn định | Net theo dữ liệu | Sprint Goal, DoD | Mở rộng khi có khả năng | Developers + PO theo accountability |
| Incident | Có sự cố ưu tiên cao | Capacity giảm | Giảm ảnh hưởng, quality | Việc không thiết yếu có thể hoãn | Incident owner, Developers, PO |
| Vendor delay | Sandbox/contract không đạt | Item phụ thuộc chưa thể Done | Không báo Done giả | Chọn lát cắt độc lập/spike | PO và Developers, vendor owner |
| Quality risk | Test bảo mật thất bại | Cần thêm sửa/kiểm chứng | DoD và phân quyền | Hoãn tính năng tùy chọn | Developers, PO, vai trò guardrail |
| User feedback | Giả thuyết sai | Giá trị/thứ tự thay đổi | Outcome/quality | Thương lượng scope hoặc goal theo quy tắc | PO, Scrum Team |

Đừng trình bày các kịch bản như **chỉ được xảy ra một trong số đó**. Incident và vendor delay có thể đồng thời.

### 16.6. Mid-Sprint Reforecast Card

~~~text
AS-OF:
  [Thoi diem cap nhat]

CURRENT SPRINT GOAL:
  [Muc tieu, con gia tri khong?]

DONE AT DoD:
  [Nhung item, build/test evidence]

ACTIVE WIP / AGE:
  [Cac item chua Done, blocked owner]

REMAINING CAPACITY:
  [Theo ngay hien tai + ky nang, khong dung gross ban dau]

CHANGED ASSUMPTIONS:
  [Incident, vendor, environment, product feedback]

OPTIONS:
  [A: giu core va hoan thien DoD
   B: thuong luong scope
   C: escalate, ...]

TRADE-OFFS:
  [Value, quality, time, dependency]

DECISION & OWNER:
  [Ai co quyen va dieu gi da thong nhat]

NEXT CHECK:
  [Moc co bang chung moi]
~~~

### 16.7. Sprint Review / Service Review Evidence

~~~text
GOAL:
  [Product Goal, Sprint Goal hoac service outcome]

COMPLETED WITH EVIDENCE:
  [Increment dat DoD / service item Finish theo policy]

NOT COMPLETED:
  [WIP, age, blocked, risk]

USER / SERVICE FEEDBACK:
  [Quan sat, phan khuc, method, limits]

QUALITY:
  [Tests, incidents, rui ro con mo]

FLOW:
  [Metric names, units, start/end, window]

WHAT CHANGED OUR ASSUMPTIONS:
  [Product, dependency, capacity, environment]

NEXT PRIORITY / IMPROVEMENT:
  [Decision va nguoi chiu trach nhiem]
~~~

### 16.8. Retrospective Experiment Card

~~~text
PROBLEM OBSERVED:
  [Vi du: PBI cho test identities tren 5 ngay]

EVIDENCE:
  [Age, test failures, dependency, user impact]

HYPOTHESIS:
  [Neu tao fixture tu phuc vu, bot wait va loi tich hop]

ONE SMALL CHANGE:
  [A specific experiment for one or two iterations]

GUARDRAILS:
  [DoD, security, privacy, release safety]

MEASURE:
  [Work item age, errors, time to Done, quality]

OTHER POSSIBLE CAUSES:
  [Work mix, people, vendor, CI]

REVIEW:
  [Giu, sua, mo rong, dung]
~~~

### 16.9. Bản thông báo kế hoạch có điều kiện

**Cách thông báo quá chắc chắn:**

> “Sprint này năm người có 50 ngày công, sẽ hoàn thành 40 ngày công công việc và bàn giao toàn bộ hạng mục vào cuối tuần thứ hai.”

**Cách thông báo có ích hơn:**

> “Mục tiêu Sprint là cho học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu trên Increment đạt DoD. Sau các nghĩa vụ đã biết, Developers có khoảng 33 ngày công khả dụng, nhưng rủi ro chính là hợp đồng entitlement và môi trường kiểm thử. Đội ưu tiên ENR-01, một phần handling lỗi cần thiết và cải tiến CI có phạm vi kiểm soát; không đặt ENR-03 phụ thuộc sandbox chưa sẵn vào mục tiêu Sprint. Nếu sự cố làm giảm capacity hoặc test phát hiện sai quyền, đội sẽ cập nhật kế hoạch, thương lượng phạm vi mở rộng và giữ DoD. Sprint Review sẽ dùng Increment thật và feedback để điều chỉnh Product Backlog.”

Thông báo thứ hai tạo **sự minh bạch và khả năng đưa quyết định đúng**, thay vì một lời hứa số học khó thực hiện.

## 17. Workshop 120 phút: lập kế hoạch, gặp biến động và điều chỉnh

Workshop thực hành trên dữ liệu giả định của nền tảng học. **Đây không phải Scrum event bắt buộc** và không thay Sprint Planning trong sản phẩm thật. Người hướng dẫn có thể giảm số vai trò hoặc thời lượng tùy trình độ.

### 17.1. Đầu vào cho nhóm học viên

**Product Goal:**

> Học viên đủ điều kiện tự ghi danh và vào bài đầu với dữ liệu và quyền đúng trên luồng được hỗ trợ.

**Sprint dài:** 10 ngày làm việc.

**Nhân sự:** 5 Developers, gross 50 person-days. Nghỉ 4, support đã biết 6 và nghĩa vụ khác không trùng lặp 7, còn **33 person-days**.

**Backlog:**

| PBI | Effort range | Giá trị | Dependency chính |
|---|---:|---|---|
| ENR-01 | 10–15 | Ghi danh miễn phí và vào bài đầu | Entitlement, integration identities |
| ENR-02 | 6–10 | Xử lý trạng thái không hợp lệ rõ ràng | UX/AC của lỗi |
| ENG-01 | 4–7 | Contract fixture tái sử dụng | Permission pipeline |
| ENR-03 | 9–18 | Thanh toán nhà cung cấp mới | Sandbox chưa xác nhận |
| ANL-01 | 3–6 | Quan sát sự kiện vào bài đầu | Metric contract, privacy |
| OPS-01 | 5–11 | Cải tiến pipeline diện rộng | Platform owner và ưu tiên |

**Guardrails:** không cấp quyền sai, không làm lộ dữ liệu người học, không tính PBI chưa đạt DoD là Done, không gọi mock vendor là xác nhận thanh toán thật.

### 17.2. Vai trò chia nhóm

- **Product Owner:** giải thích giá trị, sắp thứ tự Product Backlog, làm rõ trade-offs.
- **Developers API/data:** đánh giá entitlement, hợp đồng, nguồn dữ liệu và kỹ năng.
- **Developers UI/UX:** đánh giá trải nghiệm và trạng thái lỗi.
- **Developers quality/integration:** đánh giá DoD, test environments và test evidence.
- **Facilitator/Scrum Master trong mô phỏng Scrum:** bảo vệ thời gian trao đổi, giúp inspect/adapt và làm rõ trở ngại.
- **Observer/stakeholder:** mang thông tin người dùng hoặc rủi ro bên ngoài, không tự chèn task vào Sprint Backlog.

Một người có thể đóng nhiều vai trong workshop, nhưng khi phân tích trách nhiệm thực trong Scrum phải **giữ accountabilities chính thức rõ**.

### 17.3. Lịch workshop

| Phút | Hoạt động | Sản phẩm cần tạo |
|---|---|---|
| **0–10** | Nhận dữ liệu và xác định Product Goal/guardrails | Một câu mục tiêu giá trị và rủi ro chính |
| **10–25** | Tính capacity thực, ghi giả định không trùng lặp | Capacity sheet + skill bottleneck |
| **25–40** | Phân tích bảng dependencies và điều kiện Ready | Dependency map có owner |
| **40–55** | Xem effort ranges, chia lát cắt và chọn mục tiêu | Sprint Goal và các PBIs có lý do |
| **55–70** | Lập kế hoạch test/CI/DoD cho lát cắt cốt lõi | Sprint Backlog minh họa |
| **70–85** | Thẻ sự kiện phát sinh, cập nhật forecast | Kịch bản cập nhật và trade-offs |
| **85–100** | Giới hạn WIP, mô phỏng Daily và xử lý blocked | Một quyết định để giúp item Done |
| **100–110** | Mô phỏng Sprint Review/Retrospective | Bằng chứng và một cải tiến nhỏ |
| **110–120** | Trình bày, phản biện kết luận | Decision record và rủi ro còn mở |

### 17.4. Thẻ sự kiện phát sinh

**Thẻ A — Incident:**

> Ngày 5 có sự cố nghiêm trọng, thêm sáu person-days ngoài support đã dự trù.

Cập nhật capacity toàn kỳ từ **33 xuống 27 person-days**. Hãy chỉ ra scope nào cần bảo vệ, điều gì có thể điều chỉnh và quyền quyết định nào liên quan.

**Thẻ B — Vendor bất định:**

> Nhà cung cấp báo sandbox “có thể tới cuối tuần sau”, nhưng chưa có contract hay data test.

Nhóm có được đưa ENR-03 vào Sprint Goal không? Cần bằng chứng Ready nào trước khi hứa Increment thật?

**Thẻ C — Security fail:**

> API authz test cho thấy học viên B có thể đọc quyền học của học viên A.

Có được gọi PBI Done nếu UI chạy tốt không? Đội sẽ xử lý và minh bạch rủi ro như thế nào?

**Thẻ D — Dữ liệu người học:**

> Người học được phỏng vấn cho biết vấn đề chính không phải nút “Vào bài”, mà là entitlement chưa cấp sau ghi danh.

Product Owner có cần thay ưu tiên? Điều gì cần điều chỉnh trong Sprint nếu vẫn hướng Sprint Goal?

**Thẻ E — Người giữ kỹ năng vắng mặt:**

> Lan cần nghỉ thêm hai ngày trong tuần sau; đội chưa có người khác tự review entitlement contract.

Kế hoạch dựa trên 33 ngày công còn đúng không? Đề xuất pairing, chia scope hoặc hỗ trợ chuyên gia trong giới hạn an toàn.

**Thẻ F — Thay định nghĩa Done:**

> Trước đây “Done” nghĩa code merged. Từ Sprint này phải có integration và authorization evidence.

Có thể so throughput/cycle time thô trước–sau không? Tại sao?

### 17.5. Kết quả nhóm phải nộp

1. **Một Product Goal và Sprint Goal phù hợp**, có điều kiện kiểm chứng.
2. **Bảng net capacity**, chỉ rõ kỹ năng giới hạn và khoản không đếm trùng.
3. **Bảng lựa chọn PBI**: vì sao chọn lõi, điều gì chưa chọn.
4. **Dependency graph/card**, owner và điều kiện Ready.
5. **Một DoD phù hợp phạm vi** và ba acceptance examples, gồm một trường hợp lỗi/quyền.
6. **Một reforecast** sau thẻ sự kiện, có lựa chọn giữ/đổi scope.
7. **Bốn loại bằng chứng**: tiến triển goal, Increment/quality, flow, outcome.
8. **Một thử nghiệm Retrospective** với cách kiểm tra tác dụng.

Không cần tạo thêm một file dự án hoặc chạy một pipeline thật trong workshop nếu điều kiện kỹ thuật không có. Nhưng bài giải phải thể hiện **sự hiểu biết về điều kiện kiểm chứng trên sản phẩm thật**, không chỉ các slide khẳng định “đã xong”.

### 17.6. Rubric chấm bài

| Tiêu chí | Chưa đạt | Đạt | Tốt |
|---|---|---|---|
| **Mục tiêu** | Chỉ danh sách ticket/points | Một kết quả sản phẩm rõ | Liên kết Product Goal/Sprint Goal với DoD và outcome |
| **Capacity** | Lấy số người nhân lịch | Trừ nghĩa vụ đúng và nhất quán | Xem skill bottleneck, uncertainty và cập nhật theo kỳ |
| **Dependencies** | Chỉ ghi “chờ nhóm khác” | Có owner, điều kiện và tác động | Có hợp đồng, phương án giảm phụ thuộc, trigger |
| **Ước lượng** | Một con số chắc chắn | Range với giả định | Biết giới hạn effort vs elapsed và phụ thuộc chung |
| **Lựa chọn công việc** | Lấp đầy capacity | Chọn lát cắt có giá trị | Có core/adjustable, bảo vệ DoD khi capacity đổi |
| **Kỹ thuật/chất lượng** | Code merged là Done | Test/integration theo DoD | Bao gồm failure/authz, contract và điều kiện release |
| **Replanning** | Ép làm bù để giữ số | Cập nhật capacity/scope | Trình bày trade-offs, quyền và bằng chứng rõ |
| **Đo lường** | Chỉ points/ticket count | Có WIP/age/DoD/outcome | Metric contract và giới hạn suy luận |
| **Học tập** | Đổ lỗi estimate sai | Một cải tiến cụ thể | Giả thuyết, owner, feedback và guardrail |

### 17.7. Điều người hướng dẫn cần quan sát

Không phải đội nào chọn ít PBI hơn cũng “đúng” hơn. Một lựa chọn tốt phải **giải thích được lý do và điều kiện**. Đặc biệt quan sát xem người học có:

- Phân biệt 33 person-days và khả năng hoàn tất không.
- Nhìn thấy ENR-03 bị chặn dù còn capacity.
- Nhận ra ENR-01 không thể Done khi authz test thất bại.
- Sẵn sàng báo Sprint Goal chưa đạt nếu evidence thật chưa đủ.
- Biết Scrum không đòi dùng hết capacity hoặc đóng tất cả PBI đã chọn.
- Biết dùng feedback để điều chỉnh kế hoạch mà không phá chất lượng.

### 17.8. Một phương án workshop có thể chấp nhận

**Đề xuất:**

- Sprint Goal tập trung ENR-01 như một lát cắt người dùng.
- Chọn ENR-02 mức cần thiết, coi ENG-01 tái sử dụng là scope có thể điều chỉnh sau khi bảo vệ test bắt buộc.
- Không chọn ENR-03 tới khi sandbox/contract sẵn sàng để kiểm chứng.
- Xử lý DEP-01/02 ngay trong nửa đầu Sprint.
- Giữ WIP nhỏ để ENR-01 đạt DoD trước khi mở thêm PBI.
- Khi incident làm capacity giảm, trao đổi scope với Product Owner; không bỏ test quyền.
- Review Increment thật với stakeholders và kiểm tra outcome trên cohort đủ thời gian.

**Điều kiện:** nếu luồng miễn phí không có ý nghĩa cho người dùng của sản phẩm thực, cần **đổi lát cắt lõi** thay vì cố giữ ví dụ. Đây là dấu hiệu người học biết đưa kế hoạch trở về **giá trị sản phẩm thật**.

## 18. Bài tập vận dụng

### Bài tập A — Tính net capacity không đếm trùng

Một đội có bốn Developers, mỗi người có 10 ngày làm việc trong kỳ. Toàn đội có 3 ngày nghỉ, 5 ngày hỗ trợ production, 4 ngày nghĩa vụ vận hành không thuộc PBI và 2 ngày đào tạo bắt buộc. Các khoản **không chồng nhau** và phần công việc PBI được ước lượng riêng.

**Yêu cầu:** Tính gross capacity và net capacity cho phạm vi PBI. Có thể dùng net capacity làm lời hứa hoàn tất mọi công việc có effort thấp hơn số ấy không?

<details>
<summary>Gợi ý đáp án</summary>

Gross capacity: \(4\times10=40\) person-days. Tổng phần phải trừ là \(3+5+4+2=14\), net capacity \(40-14=26\) person-days. Đây là khả năng thời gian trên giả định đã nêu, **không phải bảo đảm hoàn tất**: còn phụ thuộc kỹ năng, thứ tự, môi trường, DoD và bất định. Nếu một khoản đã tính trong effort PBI thì phải bỏ khỏi cột trừ để không đếm hai lần.

</details>

### Bài tập B — Capacity lớn hơn effort vẫn có thể trễ

Đội có 33 person-days. Ba PBI có effort điển hình lần lượt 15, 9 và 7 person-days; chúng đều cần review entitlement từ một Developer chỉ còn 5 ngày khả dụng, tổng review dự kiến 8 ngày.

**Yêu cầu:** Có thể chốt cả ba là chắc chắn Done không? Nêu hai phương án giảm điểm nghẽn.

<details>
<summary>Gợi ý đáp án</summary>

Tổng effort điển hình \(15+9+7=31\), nhỏ hơn 33, nhưng ba PBI cần **8 ngày review** ở năng lực chỉ có **5 ngày**, nên kế hoạch không khả thi theo cách làm hiện tại. Có thể chia/trực tiếp giảm phần phụ thuộc qua contract tests, pairing để người khác làm được review phù hợp, hoặc đổi thứ tự/giảm số PBI. Cần giữ trách nhiệm kiểm chứng và guardrails, không tự coi người chưa đủ chuyên môn có thể review bảo mật mà không hỗ trợ.

</details>

### Bài tập C — Story points có phải giờ làm?

Sprint trước đội hoàn tất 28 story points trong 40 person-days khả dụng. Sprint này còn 30 person-days. Quản lý yêu cầu cam kết 21 points vì \(28/40\times30=21\).

**Yêu cầu:** Giải thích hạn chế và cách tạo forecast tốt hơn.

<details>
<summary>Gợi ý đáp án</summary>

Phép chia cho ra số học 21, nhưng story points là quy ước ước lượng tương đối, không có tỷ lệ cố định với ngày công. Work mix, kích thước PBI, dependency và DoD có thể khác. Có thể xem velocity lịch sử của **cùng đội** như một tín hiệu dự báo có giới hạn; kiểm tra net capacity, kỹ năng, sự sẵn sàng của PBI, flow/WIP và DoD; không buộc cam kết 21 points như chắc chắn.

</details>

### Bài tập D — Effort và elapsed time

Một PBI cần ba ngày công của Developer, nhưng còn phải chờ bốn ngày lịch để đối tác cấp quyền sandbox và hai ngày lịch để được tích hợp/kiểm chứng. Giả sử các khoảng **xảy ra tuần tự và không chồng nhau**, cùng quy ước ngày lịch.

**Yêu cầu:** Vì sao không được báo PBI “mất ba ngày”? Có thể tính tổng elapsed time trong giả định không?

<details>
<summary>Gợi ý đáp án</summary>

Nếu ba ngày công của một Developer được thực hiện theo ba ngày lịch liên tiếp và sau đó chờ bốn ngày rồi kiểm chứng hai ngày, elapsed time minh họa là **9 ngày lịch**. Con số ba chỉ mô tả effort làm việc chính, không gồm hàng chờ/kiểm chứng. Trong dữ liệu thật cần lấy **timestamp Finished − Started**, vì các bước có thể chồng nhau, thời gian làm việc có thể không tương ứng ngày lịch và quy ước cutoff khác.

</details>

### Bài tập E — Incident làm giảm capacity

Capacity baseline 33 person-days đã trừ sáu ngày hỗ trợ production được dự trù. Một incident mới tiêu tốn thêm tám person-days ngoài phần dự trù.

**Yêu cầu:** Capacity toàn kỳ sau cập nhật là bao nhiêu? Đội nên thay đổi điều gì và không được thay đổi điều gì?

<details>
<summary>Gợi ý đáp án</summary>

Updated capacity toàn kỳ \(33-8=25\) person-days. Cần cập nhật capacity **còn lại từ thời điểm hiện tại**, xem Sprint Goal/DoD, WIP, dependencies và lựa chọn điều chỉnh scope không thiết yếu với Product Owner. Không được lấy 33 làm mốc bắt mọi người làm bù, không hạ DoD hoặc coi PBI chưa Done là Done. Khi incident nghiêm trọng, xử lý theo chính sách và thẩm quyền trước.

</details>

### Bài tập F — Bảng phụ thuộc phải có điều kiện

ENR-03 đang chờ sandbox của nhà cung cấp. Ticket ghi “Team đối tác sẽ bàn giao sớm” nhưng không có API contract, test data hoặc người theo dõi.

**Yêu cầu:** Viết lại thành dependency có owner, điều kiện Ready và fallback.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ: “DEP-04: ENR-03 cần nhà cung cấp xác nhận sandbox version S và contract webhook gồm trạng thái success/pending/failed, timeout, duplicate behavior, phương thức xác thực và dữ liệu test. Owner tiếp theo là đầu mối đối tác được xác định; Developers kiểm chứng bằng contract/integration tests. Nếu chưa sẵn, không đưa ENR-03 làm điều kiện Sprint Goal; làm rõ/spike có giới hạn hoặc chọn PBI độc lập. Báo ngày kiểm tra lại và tác động Product Goal.” Một ngày hứa **không thay bằng chứng Ready**.

</details>

### Bài tập G — Đếm WIP khi Blocked là trạng thái hoặc nhãn

Một workflow đang có 2 item In Progress, 3 item Verification và 1 item Blocked. Trong phương án thứ nhất, Blocked là một item **khác** hai cột trước; trong phương án thứ hai, Blocked chỉ là nhãn gắn trên một item đã nằm ở Verification.

**Yêu cầu:** Tính WIP từng phương án.

<details>
<summary>Gợi ý đáp án</summary>

Nếu Blocked là item độc lập trong boundary thì WIP \(2+3+1=6\). Nếu Blocked chỉ là nhãn trên một trong ba item Verification thì WIP \(2+3=5\), không cộng thêm một lần. Item đã Started và chưa Finished không bị loại khỏi WIP chỉ vì đang chờ phụ thuộc.

</details>

### Bài tập H — Cycle time Done và age của item chưa Done

Bốn PBI Done có cycle time **3, 5, 6, 8 ngày lịch**. Hai PBI chưa Done có work item age **14 và 19 ngày**.

**Yêu cầu:** Tính median cycle time của bốn item Done và viết kết luận đúng.

<details>
<summary>Gợi ý đáp án</summary>

Median \(=(5+6)/2=5{,}5\) ngày lịch. Câu kết luận: “Trong mẫu bốn PBI Done, median cycle time là 5,5 ngày; còn hai PBI đang mở có age 14 và 19 ngày cần điều tra phụ thuộc, blocked và DoD. Chưa thể kết luận toàn bộ dòng công việc nay chỉ mất 5,5 ngày.” Đây là cách tránh bỏ những item khó chưa hoàn tất khỏi đánh giá.

</details>

### Bài tập I — Scrum chọn lượng công việc bằng cách nào?

Trong Sprint Planning, Product Owner đưa danh sách 12 PBI và yêu cầu Developers ký cam kết Done hết vì “đã có Product Backlog ordering”.

**Yêu cầu:** Theo Scrum Guide 2020, ai quyết định lượng việc được chọn, commitment của Sprint Backlog là gì, và nếu phát hiện mới thì xử lý ra sao?

<details>
<summary>Gợi ý đáp án</summary>

Product Owner chịu trách nhiệm Product Backlog và tối đa hóa giá trị; **Developers lựa chọn lượng công việc** có triển vọng hoàn tất trong Sprint, trao đổi với Product Owner, xét capacity và kinh nghiệm. **Sprint Goal** là commitment của Sprint Backlog. Khi có thêm hiểu biết, Developers thích ứng kế hoạch, thương lượng/làm rõ scope với Product Owner; không làm thay đổi gây nguy hại Sprint Goal hoặc giảm chất lượng. Không có quy tắc tất cả PBI được đưa ra trong Planning đều phải ký Done hết.

</details>

### Bài tập J — Còn capacity nhưng thiếu sandbox

Đến cuối tuần đầu, Developers còn nhiều ngày công khả dụng. PBI thanh toán ENR-03 đứng đầu danh sách việc mong muốn nhưng sandbox chưa có và webhook contract chưa xác minh.

**Yêu cầu:** Có nên kéo PBI chỉ vì còn capacity? Nêu hai lựa chọn tạo giá trị/giảm rủi ro mà không giả Done.

<details>
<summary>Gợi ý đáp án</summary>

Không nên kéo ENR-03 với lời hứa Done nếu điều kiện bắt buộc chưa sẵn. Có thể (1) làm spike giới hạn để xác minh auth, trạng thái và tài liệu contract, ghi rõ kết quả chỉ là học tập; (2) chọn một lát cắt độc lập như trạng thái PENDING trung thực, entitlement rules hoặc cải thiện test environment, nếu ưu tiên sản phẩm và DoD phù hợp. Product Owner quản lý thứ tự, Developers đánh giá khả thi; cần liên hệ đối tác với owner và điều kiện Ready rõ.

</details>

### Bài tập K — Three-point estimate không phải lời hứa

Một hạng mục có optimistic 4 ngày công, most likely 7 ngày công, pessimistic 16 ngày công.

**Yêu cầu:** Tính heuristic PERT \((O+4M+P)/6\). Có thể tuyên bố chắc chắn hoàn thành trong con số ấy không?

<details>
<summary>Gợi ý đáp án</summary>

\[
E=\frac{4+4(7)+16}{6}=\frac{48}{6}=8\ \text{person-days}
\]

Đây là **ước lượng effort dựa trên một công thức giả định**, không bảo đảm hoàn tất trong tám ngày lịch hoặc tám ngày công chính xác. Cần xem phụ thuộc, thứ tự kỹ thuật, khả năng chuyên môn, DoD, mô hình phân phối (nếu dùng) và biến động thật. Đặc biệt optimistic/most likely/pessimistic thiếu bằng chứng lịch sử không tạo ra xác suất chắc chắn.

</details>

### Bài tập L — Ưu tiên một lát cắt hay nhiều task?

Đội có UI-01, API-01, DB-01 và QA-01, mỗi task có estimate nhỏ. Người quản lý yêu cầu bốn task đều chuyển Done, dù học viên vẫn không thể vào bài đầu.

**Yêu cầu:** Đề xuất ít nhất một PBI theo lát cắt dọc và các acceptance conditions tối thiểu.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ PBI: “Học viên đủ điều kiện ghi danh một khóa miễn phí và vào bài đầu trong một hành trình đầu-cuối.” Acceptance conditions: lưu ghi danh đúng, entitlement hợp lệ theo quy tắc, truy cập bài đầu đúng, từ chối người không có quyền, xử lý yêu cầu gửi trùng phù hợp và hiển thị trạng thái trung thực. UI/API/DB/test là task nằm trong implementation, không nên mỗi task tự đại diện một Increment. Đội cần kiểm chứng đủ DoD trên build tích hợp.

</details>

### Bài tập M — Dùng throughput lịch sử thận trọng

Tám tuần gần đây có throughput **3, 2, 4, 3, 5, 2, 3, 4 PBIs** cùng định nghĩa, nhưng Sprint tiếp theo chứa một migration dữ liệu lớn chưa có hạng mục tương tự trong lịch sử.

**Yêu cầu:** Tính throughput trung bình/tuần. Vì sao không được dự báo migration theo trung bình ấy?

<details>
<summary>Gợi ý đáp án</summary>

Tổng \(3+2+4+3+5+2+3+4=26\), trung bình \(26/8=3{,}25\) PBI/tuần. Lịch sử là tín hiệu cho work mix đã quan sát, không tự đại diện migration mới có rủi ro dữ liệu và dependency khác. Nên tách loại item, kiểm tra DoD, xác minh migration/spike hoặc lập forecast riêng với giả định rõ. Không nói đội chắc chắn Done 6,5 PBI trong hai tuần.

</details>

### Bài tập N — Các kịch bản có thể đồng thời xảy ra

Kế hoạch có ba kịch bản: A cơ sở, B incident làm giảm sáu ngày công, C sandbox chậm khiến ENR-03 không thể tích hợp. Một thành viên cho A 70%, B 20%, C 10% và kết luận chỉ một kịch bản sẽ xảy ra.

**Yêu cầu:** Giải thích lỗi mô hình và đề xuất cách ghi kịch bản đúng.

<details>
<summary>Gợi ý đáp án</summary>

Incident và sandbox chậm **có thể cùng xảy ra**, nên A/B/C không tự là những trạng thái loại trừ lẫn nhau. Các xác suất 70/20/10 không có cơ sở dữ liệu. Nên mô tả các biến cố độc lập hoặc tương quan theo điều kiện, trigger và tác động: capacity có thể giảm xuống 27, đồng thời ENR-03 vẫn bị chặn vì sandbox. Khi có dữ liệu đáng tin, mới xây mô hình xác suất có giả định rõ; hiện tại dùng kịch bản có điều kiện để chọn scope và phương án dự phòng.

</details>

### Bài tập O — Cohort outcome chưa đủ thời gian

Trong 100 lượt ghi danh hợp lệ **đã đủ 24 giờ theo dõi**, có 80 lượt vào bài đầu trong 24 giờ. Ngoài ra còn 20 lượt mới ghi danh chưa đủ cửa sổ 24 giờ, chưa biết kết quả.

**Yêu cầu:** Tính tỷ lệ trên cohort đủ quan sát. Vì sao không đưa 20 lượt mới vào mẫu số để coi là thất bại?

<details>
<summary>Gợi ý đáp án</summary>

Tỷ lệ trên cohort trưởng thành là \(80/100\times100\%=80\%\). Nếu đưa 20 lượt chưa đủ thời gian vào mẫu số, tỷ lệ sai sẽ là \(80/120\approx66{,}67\%\), nhầm quan sát thiếu với thất bại. Cần giữ quy tắc cohort, cutoff, đơn vị đếm và tracking consistent, đồng thời xem những lượt mới sau khi đủ cửa sổ. Không loại các lượt thất bại thật khỏi mẫu số để cải thiện tỷ lệ giả.

</details>

### Bài tập P — Một PBI đạt Done chưa?

ENR-01 đã tích hợp UI/API và cho học viên A vào bài, nhưng test cho tài khoản B cho thấy B có thể lấy dữ liệu quyền của A. Product Owner muốn vẫn đánh dấu Done và sửa bảo mật sau.

**Yêu cầu:** Đề xuất quyết định đúng về DoD và kế hoạch.

<details>
<summary>Gợi ý đáp án</summary>

Không được coi ENR-01 đạt DoD nếu có lỗi phân quyền nghiêm trọng chưa đáp ứng điều kiện chất lượng/guardrail. Developers cần phối hợp xử lý, test lại trên build phù hợp và minh bạch tác động; PO có thể điều chỉnh thứ tự/phạm vi không thiết yếu nhưng không tự bỏ kiểm soát bảo mật bắt buộc để đẩy ticket Done. Nếu lỗi đã ở production, xử lý theo quy trình incident/security với thẩm quyền thích hợp.

</details>

### Bài tập Q — Có nên hủy Sprint?

Một Scrum Team đang theo Sprint Goal “Ghi danh khóa miễn phí và vào bài đầu”. Giữa Sprint, tổ chức quyết định ngừng kinh doanh hoàn toàn các khóa miễn phí, mục tiêu không còn giá trị; trong trường hợp khác chỉ có một API khó hơn dự kiến.

**Yêu cầu:** Phân biệt hai tình huống và ai có quyền hủy Sprint theo Scrum Guide.

<details>
<summary>Gợi ý đáp án</summary>

Nếu Sprint Goal thực sự **trở nên lỗi thời** vì sản phẩm không còn cung cấp khóa miễn phí, có cơ sở xem xét hủy Sprint; **Product Owner có thẩm quyền hủy**. Nếu chỉ một API khó hơn hoặc effort vượt dự báo nhưng mục tiêu vẫn còn giá trị, thông thường cần Developers điều chỉnh kế hoạch/thương lượng scope với PO thay vì hủy Sprint. Không dùng hủy Sprint như cách tránh báo Sprint Goal chưa đạt hay chữa estimate sai.

</details>

### Bài tập R — Viết một quyết định reforecast trung thực

Sau nửa Sprint, nhóm còn một item core cần kiểm thử authz, hai item mở rộng chưa Done, incident mới làm giảm capacity và đối tác chưa cung cấp sandbox. Một stakeholder yêu cầu đội vẫn cam kết toàn bộ PBI ban đầu.

**Yêu cầu:** Soạn một thông báo ngắn gồm mục tiêu, bằng chứng Done, capacity/dependency, các lựa chọn và guardrails.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ:

> “Sprint Goal vẫn là học viên đủ điều kiện ghi danh miễn phí và vào bài đầu trên Increment đạt DoD. Hiện core item chưa Done vì kiểm chứng authz còn mở; các hạng mục mở rộng chưa đạt chất lượng chưa được tính hoàn tất. Incident mới giảm năng lực khả dụng, còn sandbox thanh toán của đối tác chưa sẵn. Developers đang ưu tiên hoàn thành kiểm chứng quyền và sẽ trao đổi với Product Owner về phần handling lỗi/CI mở rộng có thể hoãn; không đưa ENR-03 vào phạm vi cần giao kỳ này. Chúng tôi sẽ cập nhật dự báo từ capacity còn lại và work item age ở mốc kiểm tra tiếp theo. Không bỏ DoD hoặc báo mock là tích hợp thật.”

Điểm quan trọng là **nêu sự thật và quyết định có điều kiện**, không viện một con số effort ban đầu để ép hoàn tất những việc đã thay đổi điều kiện.

</details>

## 19. Checklist tự đánh giá một kế hoạch ngắn hạn có trách nhiệm

Hãy chọn **một Product Goal hoặc một service outcome thật** rồi trả lời bằng bằng chứng. Checklist này không phải thang điểm trưởng thành Agile bắt buộc, cũng không dùng để thưởng/phạt từng Developers. Câu hỏi giúp đội phát hiện **giả định còn yếu trước khi biến nó thành cam kết**.

### 19.1. Giá trị và phạm vi

1. Chúng ta có mô tả được **người dùng và kết quả** đang hướng tới không?
2. Có phân biệt Product Goal, Sprint Goal hoặc service outcome với danh sách task không?
3. Những PBI quan trọng có được chia thành **lát cắt có giá trị** không?
4. Có acceptance examples cho thành công, lỗi và phân quyền phù hợp không?
5. Product Owner có thứ tự Product Backlog có nghĩa nếu đang dùng Scrum không?
6. Các bên có hiểu điều gì **phải đạt để gọi Increment Done** không?
7. Có phân biệt scope cốt lõi với việc mở rộng mà **không coi DoD là tùy chọn** không?
8. Có thể kiểm chứng mục tiêu bằng hành vi phần mềm và phản hồi thay vì chỉ đếm ticket không?

### 19.2. Năng lực khả dụng

9. Gross capacity được tính theo kỳ, số người và đơn vị thời gian rõ chưa?
10. Đã trừ nghỉ, support và nghĩa vụ khác phù hợp, **không đếm trùng** chưa?
11. Effort PBI có bao gồm phần kiểm thử, tích hợp và công việc cần cho DoD chưa?
12. Có phân biệt capacity Developers với thời gian đóng góp của Product Owner/Scrum Master không?
13. Những kỹ năng, quyền hoặc reviews chuyên sâu có thể thành bottleneck đã được thấy chưa?
14. Có tránh giả định mọi person-day hoán đổi tự do giữa kỹ năng không?
15. Có tránh quy đổi story points thành giờ/ngày như một hằng số không?
16. Capacity có được cập nhật khi sự cố/nghỉ thêm xảy ra không?
17. Có một mức linh hoạt phù hợp với biến động lịch sử thay vì bắt mọi người kín 100% thời gian không?
18. Có phân biệt tổng effort với elapsed time và thời gian chờ không?

### 19.3. Phụ thuộc và sẵn sàng

19. Những PBI có giá trị cao đã được xem **phụ thuộc nghiệp vụ, kỹ thuật, dữ liệu, môi trường và ngoài tổ chức** chưa?
20. Phụ thuộc có owner/đầu mối thực hiện bước tiếp theo rõ không?
21. Có điều kiện **Ready có thể kiểm chứng** thay vì chỉ một ngày được hứa không?
22. Có contract/test để bảo vệ ngữ nghĩa ở ranh giới thành phần không?
23. Có biết dependency nào bắt buộc, dependency nào có thể làm song song không?
24. Có nhận diện một người, một environment hoặc một provider chung cho nhiều PBI không?
25. Có phương án nếu dependency không sẵn: chia lát cắt, spike, chọn item khác, escalation không?
26. Các mock/spikes có được ghi rõ **giới hạn bằng chứng**, không báo là Increment production Done không?
27. Có giảm những hàng chờ lặp bằng tự động hóa, pairing hoặc thay ownership khi hợp lý không?
28. Các quyết định vượt quyền đội có được đưa tới đúng người, kèm trade-off và tác động không?

### 19.4. Bất định và dự báo

29. Mỗi estimate quan trọng có nêu phạm vi, đơn vị và giả định không?
30. Những PBI rủi ro cao có được chia nhỏ hoặc kiểm chứng giả định trước không?
31. Có nhận diện điều chưa biết về người dùng, kỹ thuật, dữ liệu và provider không?
32. Có kịch bản capacity giảm do incident hoặc biến động không?
33. Có nhớ rằng các kịch bản có thể **xảy ra đồng thời** không?
34. Có tránh tự gắn xác suất chính xác khi thiếu dữ liệu đáng tin không?
35. Dự báo throughput/cycle time có dùng work types, DoD và cửa sổ phù hợp không?
36. Có trigger rõ để cập nhật forecast khi điều kiện thay đổi không?

### 19.5. Thực hiện và điều chỉnh

37. Nếu dùng Scrum, Sprint Goal có giá trị và do Scrum Team xác định trong Planning không?
38. Developers có chọn lượng việc và điều chỉnh Sprint Backlog trong trách nhiệm của họ không?
39. Sprint Goal có được bảo vệ mà vẫn cho phép làm rõ/thương lượng scope khi học thêm không?
40. Có tránh hạ DoD để đạt kế hoạch không?
41. Daily Scrum hoặc cơ chế flow review có giúp item tiến tới Done thay vì chỉ đọc status không?
42. WIP/blocked có được minh bạch trong boundary, không đếm trùng hoặc giấu ngoài bảng không?
43. Nhóm có ưu tiên hoàn tất những item gần Done khi phù hợp thay vì mở thêm việc cho mọi người bận không?
44. Khi incident xuất hiện, đội có xử lý theo quyền/chính sách rồi cập nhật capacity và kế hoạch không?
45. Có phân biệt việc chưa Done, Increment Done, released và outcome observed không?
46. Retrospective/service review có chọn một cải tiến có giả thuyết và mốc đánh giá không?

### 19.6. Dữ liệu, chất lượng và quyết định

47. DoD có bao gồm kiểm chứng kỹ thuật/bảo mật/dữ liệu cần thiết theo phạm vi không?
48. Chỉ số WIP, throughput, age và cycle time có Definition of Workflow và đơn vị nhất quán không?
49. Có xem age của những item **chưa Done**, tránh survivorship bias không?
50. Có tránh so story points giữa đội hoặc dùng ticket count làm KPI cá nhân không?
51. Outcome có định nghĩa tử, mẫu số, cohort, cửa sổ và thời điểm chốt không?
52. Có không tính cohort chưa đủ thời gian quan sát là thất bại không?
53. Khi so trước–sau, có kiểm tra thay đổi work mix, DoD, năng lực và môi trường không?
54. Có trình bày rủi ro còn mở và giới hạn dữ liệu trước khi kết luận thành công không?
55. Kế hoạch và forecast có dẫn đến **một lựa chọn tốt hơn cho người dùng** trong khi giữ chất lượng và khả năng học của đội không?

Nếu nhiều câu trả lời chưa rõ, đừng bắt đầu bằng **một kế hoạch chi tiết hơn**. Hãy chọn **một PBI đang bị chặn**, xác định mục tiêu và điều kiện Done, tính năng lực có thể giúp nó hoàn tất, làm rõ phụ thuộc/rủi ro rồi thử một thay đổi nhỏ. Dữ liệu từ lần thử đó sẽ làm kế hoạch tiếp theo có căn cứ hơn.

## 20. Tổng kết

- **Kế hoạch ngắn hạn là forecast có điều kiện**, không phải lời hứa chắc chắn mọi estimate đúng và mọi việc đã chọn sẽ hoàn tất.
- **Giá trị đi trước capacity:** mục tiêu người dùng và DoD hướng dẫn lựa chọn lát cắt; không chọn việc chỉ để lấp kín lịch.
- **Gross capacity khác net capacity.** Phải xét nghỉ, support, nghĩa vụ không trùng lặp và năng lực theo kỹ năng/quyền. Năm người có mười ngày làm việc không tự tạo 50 ngày công giao PBIs.
- **Story points không phải giờ làm.** Có thể dùng sizing/velocity nội bộ với giới hạn; flow metrics và lịch sử cần Definition of Workflow/cùng loại item.
- **Effort khác elapsed time.** Hàng chờ API, dữ liệu, quyết định và môi trường có thể chi phối cycle time dù code viết nhanh.
- **Phụ thuộc phải có điều kiện và owner:** “hứa sẽ có API” không bằng contract có thể kiểm chứng; buffer ngày công không tạo ra sandbox.
- **Bất định cần được bộc lộ qua range, giả định, kịch bản và trigger.** Không bịa xác suất hoặc giả rằng rủi ro đồng thời có thể cộng/trừ đơn giản.
- **Vertical slicing và test tích hợp sớm** giúp tạo Increment thay vì nhiều task theo tầng chưa dùng được. Các kiểm tra cần cho DoD không bao giờ là scope tùy chọn.
- **Trong Scrum, Sprint Goal là commitment của Sprint Backlog.** Developers lựa chọn lượng việc và thích ứng kế hoạch; Product Owner quản lý giá trị/backlog; Scrum Master giúp hiệu quả Scrum. Phạm vi có thể làm rõ, nhưng không gây nguy hại Sprint Goal hoặc giảm chất lượng.
- **Kanban giúp quản lý dòng việc liên tục:** explicit policies, WIP control, throughput, work item age, cycle time và SLE theo dữ liệu; có thể bổ sung các thực hành flow cho Scrum.
- **Reforecast là hành vi có trách nhiệm:** khi incident làm capacity giảm, vendor chậm hoặc test phát hiện lỗi, đội cập nhật thông tin, thương lượng scope thích hợp và giữ guardrails, không ép làm bù để bảo vệ con số ban đầu.
- **Đo đồng thời goal, Increment/quality, flow và outcome.** Không dùng số ticket, story points, số test hay mức bận rộn để thay kết quả người dùng.
- **Lập kế hoạch tốt lên nhờ học tập:** Sprint Review và Retrospective, hoặc service review, chuyển phản hồi thành thứ tự mới, cải tiến contract/CI và dữ liệu forecast tốt hơn.

Khi phải lập kế hoạch cho một vài tuần tới, hãy hỏi:

> **“Kết quả người dùng quan trọng nhất là gì? Với năng lực khả dụng, những kỹ năng và phụ thuộc đang có, lát cắt nào có thể đạt DoD? Giả định nào dễ sai nhất, tín hiệu nào sẽ làm chúng ta đổi kế hoạch và ai có quyền quyết định mà không đánh đổi chất lượng?”**

Trả lời bằng **dữ liệu, điều kiện và khả năng giao Increment thật** sẽ giúp đội phối hợp có trách nhiệm ngay cả khi tương lai chưa thể biết chính xác.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị nền tảng về phần mềm hoạt động, tương tác, hợp tác khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, nhịp bền vững, chất lượng kỹ thuật và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Sprint Planning với Why/What/How, Product Goal, Sprint Goal, Product Backlog, Sprint Backlog, Increment, DoD và accountabilities.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, WIP, throughput, work item age, cycle time và Service Level Expectation.
- [Scrum.org — The Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams): cách bổ sung thực hành Kanban để quản lý flow khi vẫn dùng Scrum.
- **Daniel S. Vacanti — _Actionable Agile Metrics for Predictability_**: dữ liệu flow, throughput/cycle time, work item aging và dự báo có điều kiện.
- **Daniel S. Vacanti — _When Will It Be Done?_**: các câu hỏi dự báo thực dụng và sử dụng mô phỏng/độ bất định phù hợp.
- **Jeff Patton & Peter Economy — _User Story Mapping_**: nhận diện hành trình người dùng, chia lát cắt có giá trị và sắp thứ tự Product Backlog.
- **Kent Beck & Cynthia Andres — _Extreme Programming Explained: Embrace Change_** (ấn bản thứ hai): phát triển qua thay đổi nhỏ, kiểm thử, thiết kế đơn giản, CI và phản hồi kỹ thuật.
- **Kent Beck — _Test-Driven Development: By Example_**: vòng Red–Green–Refactor giúp xây và kiểm chứng hành vi.
- **Gene Kim, Jez Humble, Patrick Debois & John Willis — _The DevOps Handbook_**: giảm hàng chờ, tăng chất lượng tích hợp và phản hồi trong dòng delivery.
- [DORA](https://dora.dev/): nghiên cứu và hướng dẫn về năng lực giao phần mềm/reliability; cần đọc đúng định nghĩa metric trong bối cảnh.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): cách đặc tả hành vi và ví dụ kiểm chứng, phân biệt đặc tả với test thực thi.
- **Matthew Skelton & Manuel Pais — _Team Topologies: Organizing Business and Technology Teams for Fast Flow_**: ranh giới nhóm, cognitive load, dependency và phối hợp giữa product/platform teams.
- [W3C Web Accessibility Initiative](https://www.w3.org/WAI/): tiêu chuẩn và hướng dẫn thực hành để bảo vệ khả năng tiếp cận trong trải nghiệm web.









