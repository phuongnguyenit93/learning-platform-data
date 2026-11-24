# Ép vận tốc tăng liên tục hoặc so sánh story point giữa các nhóm

## 1. Một bảng xếp hạng velocity có thể làm gì với một đội Agile?

Một công ty phát triển nền tảng học trực tuyến có hai nhóm:

- **Nhóm Hành trình học** phát triển trải nghiệm học viên, thường có nhiều user story liên quan giao diện, hành vi và thử nghiệm sản phẩm.
- **Nhóm Nền tảng đăng ký** duy trì dịch vụ đăng ký, phân quyền và tính nhất quán dữ liệu, thường phải xử lý lỗi khó, sự cố và phụ thuộc hạ tầng.

Cuối quý, lãnh đạo xem bảng tiến độ:

| Nhóm | Story points hoàn thành trong Sprint gần nhất |
|---|---:|
| Hành trình học | 46 |
| Nền tảng đăng ký | 24 |

Một kết luận vội vàng xuất hiện:

> “Nhóm Nền tảng chỉ đạt khoảng nửa năng suất nhóm Hành trình học. Quý sau mỗi đội phải tăng velocity ít nhất 20%.”

Sau thông báo, các nhóm có thể bắt đầu ước lượng story lớn hơn, chia ticket thành nhiều phần dễ đóng, giảm thời gian đầu tư kiểm thử hoặc né những hạng mục nhiều bất định. **Số story points trên báo cáo có thể tăng dù người dùng nhận không thêm giá trị, còn chất lượng giảm.**

Sai lầm cốt lõi là dùng **velocity** như một KPI phải tăng vô hạn hoặc như một đơn vị sản lượng chung cho các đội. Trong nhiều đội, velocity có ích cho **dự báo cục bộ**; nó không phải thước đo trực tiếp của năng suất, chất lượng, giá trị kinh doanh hay sự tận tâm của con người.

Bài thuộc chương **Sai lầm thường gặp** trong module **AGILE_DEVELOPMENT**: học Agile thông qua phản hồi sớm, Increment có giá trị, user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Mục tiêu không phải loại bỏ mọi phép ước lượng; mục tiêu là **sử dụng đúng câu hỏi mà một phép đo có thể trả lời**.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích **story points**, **velocity** và các điều kiện khiến chúng có ích cho dự báo.
2. Nhận diện vì sao **ép velocity tăng liên tục** và **so sánh điểm giữa các nhóm** là những quyết định thiếu cơ sở.
3. Phân tích các hành vi phát sinh khi một chỉ số được biến thành mục tiêu thưởng/phạt: tăng điểm ước lượng, chia ticket hình thức, hạ Definition of Done, bỏ chất lượng và che việc khẩn.
4. Phân biệt **activity, output, process outcome, product outcome và impact**.
5. Sử dụng kết hợp **velocity cục bộ, throughput, cycle time, work item age, WIP, chất lượng và phản hồi người dùng** để dự báo và cải tiến.
6. Diễn giải ví dụ số học, giới hạn mẫu và khoảng dự báo mà không biến ước lượng thành cam kết chính xác giả tạo.
7. Đề xuất một cuộc đối thoại có bằng chứng khi quản lý muốn tăng điểm hoặc xếp hạng các đội.
8. Thiết kế thí nghiệm cải tiến có **baseline, giả thuyết, owner, guardrails và mốc Check**.

## 2. Story point thực sự biểu diễn điều gì?

**Story point** là đơn vị ước lượng **tương đối do một đội lựa chọn**. Nó thường giúp đội diễn đạt mức độ lớn hoặc độ khó của Product Backlog Item (PBI) trong bối cảnh hiểu biết hiện tại.

Một đội có thể cân nhắc:

- Khối lượng công việc dự kiến.
- Mức phức tạp kỹ thuật hoặc nghiệp vụ.
- Bất định và rủi ro chưa được khám phá.
- Tích hợp với hệ thống khác và độ khó kiểm chứng.

**Không có công thức phổ quát** bắt buộc mọi đội phải kết hợp các yếu tố này với cùng trọng số. Một số đội dùng dãy gần Fibonacci như 1, 2, 3, 5, 8, 13; đội khác dùng kích thước S/M/L hoặc không dùng points.

### 2.1. Ước lượng tương đối, không phải phép đo vật lý

Ví dụ, đội A coi việc bổ sung validation thông thường là **3 points** và một thay đổi tính nhất quán của hai dịch vụ là **8 points**.

Điều đó có thể mang ý:

> “Trong hiểu biết và cách làm của đội chúng ta, hạng mục thứ hai lớn hoặc bất định hơn hạng mục thứ nhất.”

Nó **không** chứng minh hạng mục 8 points tiêu tốn chính xác 8/3 lần số giờ, tạo 8/3 lần doanh thu hoặc đòi 8/3 lần số người.

Các con số story point là **ước lượng quy ước**, không phải đơn vị tiêu chuẩn quốc tế có phép hiệu chuẩn chung.

### 2.2. Một story point không bằng một giờ hoặc một ngày

Nếu doanh nghiệp tuyên bố “một point bằng bốn giờ”, họ đã chuyển sang cách quy đổi thời gian cố định. Cách này dễ mất ý nghĩa của **ước lượng tương đối** và khiến việc thay đổi điểm hoặc tốc độ bị hiểu như thay đổi năng lực lao động.

Đội có thể dùng **thời gian dự kiến** như một cách ước lượng riêng khi phù hợp, nhưng phải gọi đúng tên và không coi nó là story points theo chuẩn bắt buộc.

### 2.3. Story points không bắt buộc trong Scrum

Scrum nói về Product Backlog, Sprint Planning, Sprint Goal, Increment và tính minh bạch để kiểm tra–thích ứng. **Scrum Guide không bắt buộc dùng story points, Planning Poker hoặc velocity.**

Developers chịu trách nhiệm lựa chọn cách lập kế hoạch và quy mô công việc trong Sprint. Có đội dùng points hữu ích; có đội ưu tiên số hạng mục hoàn thành, độ lớn tương đối bằng lớp kích thước hoặc dữ liệu cycle time.

**Không dùng story points không đồng nghĩa nhóm không Agile; dùng story points cũng không chứng minh nhóm đã Agile.**

## 3. Velocity là gì và được tính như thế nào?

Trong cách dùng phổ biến, **velocity của một đội trong một Sprint** là **tổng số story points của các PBI đã hoàn thành theo Definition of Done áp dụng trong Sprint đó**.

Ví dụ:

| PBI | Ước lượng ban đầu | Kết quả tại cuối Sprint | Points được tính vào velocity minh họa |
|---|---:|---|---:|
| Mở lại bài học gần nhất | 5 | Đạt DoD | 5 |
| Cập nhật trạng thái tiến độ | 8 | Đạt DoD | 8 |
| Gửi thông báo nhắc học | 3 | Đạt DoD | 3 |
| Tích hợp hệ thống gợi ý | 13 | Chưa đạt DoD | 0 |
| **Tổng** | **29** | **Ba PBI Done** | **16** |

~~~text
Velocity của Sprint minh họa = 5 + 8 + 3 = 16 points.

13 points của PBI chưa đạt Definition of Done
không được cộng một phần chỉ vì "đã code 80%".
~~~

Việc tính points phụ thuộc **quy ước minh bạch và nhất quán** của đội. Story point có thể được điều chỉnh khi hiểu biết thay đổi theo chính sách đội, nhưng không nên viết lại lịch sử tùy ý để làm đẹp số liệu.

### 3.1. Sprint Backlog và Increment là hai khái niệm khác

Sprint Backlog là kế hoạch cho Sprint Goal, còn **Increment** phải dùng được và đáp ứng Definition of Done. Một task kỹ thuật được đánh dấu xong chưa đủ để một PBI đạt Done.

Nếu một hạng mục còn thiếu kiểm thử bảo mật, chưa tích hợp hoặc hành vi người dùng chưa đúng acceptance criteria, việc ghi “Done” để cộng points **làm hỏng tính minh bạch**.

### 3.2. Velocity không phải số points cam kết tuyệt đối

Đội có thể dùng dữ liệu các Sprint trước để cân nhắc lượng công việc có khả năng thực hiện. Nhưng mục tiêu quan trọng trong Scrum là **Sprint Goal** và Increment hữu ích, không phải đóng đúng tổng points đã chọn bằng mọi giá.

Khi một PBI phát sinh bất định, yêu cầu khẩn hoặc vấn đề chất lượng, đội cần kiểm tra và điều chỉnh kế hoạch theo quy tắc Scrum, thay vì hy sinh DoD để giữ con số.

## 4. Velocity hữu ích nhất cho câu hỏi nào?

Một câu hỏi phù hợp:

> “Với cách ước lượng và điều kiện làm việc gần đây của **đội này**, chúng ta nên chọn khoảng khối lượng PBI nào cho Sprint tới và mức bất định ra sao?”

Các ứng dụng có điều kiện:

1. Hỗ trợ Developers thảo luận năng lực trong Sprint Planning.
2. Dự báo sơ bộ số Sprint cần để đi qua một phần Product Backlog **theo ước lượng hiện tại**.
3. Phát hiện thay đổi lớn để **điều tra nguyên nhân**: sự cố, thiếu người, PBI quá lớn, rủi ro tăng, thay đổi DoD.
4. Hỗ trợ cuộc trao đổi forecast với Product Owner và stakeholder khi kèm giả định và độ biến động.

Các câu hỏi **không** được velocity tự trả lời:

- Người dùng có hài lòng hơn không?
- Đội nào làm việc chăm hơn?
- Ai là lập trình viên giỏi nhất?
- Có nên thưởng cho đội đạt điểm cao?
- Chất lượng hoặc độ an toàn có tăng không?
- Công ty có tạo thêm doanh thu?
- Dự án sẽ hoàn thành chính xác vào thứ Sáu cách đây bốn Sprint?

### 4.1. Velocity là dữ liệu quá khứ, không phải định luật tương lai

Một loạt velocity ổn định có thể giúp dự báo, nhưng Sprint tới có thể khác vì:

- Nghỉ phép, tuyển người mới hoặc thay đổi kỹ năng.
- Sự cố production hoặc nghĩa vụ bảo mật chen ngang.
- Product Backlog chứa hạng mục nhiều bất định hơn.
- Phụ thuộc liên đội hoặc môi trường thử bị chặn.
- Đội đầu tư cải tiến CI, test, kiến trúc hoặc chuyển giao tri thức.
- Cách ước lượng, cách chia PBI hoặc Definition of Done thay đổi.

**Dự báo tốt phải ghi rõ các giả định còn đúng hay đã đổi**, không lặp lại một số trung bình máy móc.

### 4.2. Velocity thấp hơn không nhất thiết là xấu

Giả sử trong một Sprint, đội:

- Sửa một lỗi đồng thời gây xác nhận đăng ký trùng.
- Bổ sung kiểm tra phân quyền cho luồng nhạy cảm.
- Đầu tư làm CI ổn định sau nhiều lần thất bại ngẫu nhiên.

Đội có thể hoàn thành ít points tính theo PBI hơn bình thường, nhưng đã **giảm rủi ro và bảo vệ giá trị thực của người dùng**. Cần xem outcome và bối cảnh trước khi đánh giá.

## 5. Vì sao ép velocity tăng liên tục là sai về mặt hệ thống?

Một tổ chức tuyên bố “velocity phải tăng 10% mỗi Sprint” có thể đang ngầm giả định **năng lực tạo points tăng vô hạn**, trong khi con người, thiết bị, thời gian, phụ thuộc và chất lượng đều có giới hạn.

### 5.1. Tăng trưởng nhân với 10% mỗi Sprint không dừng lại

Nếu velocity ban đầu là **30 points** và mục tiêu tăng **10% ở mỗi Sprint**, sau 10 Sprint:

~~~text
Target sau 10 Sprint = 30 × (1,10)^10
                    ≈ 77,8 points.

Target sau 20 Sprint = 30 × (1,10)^20
                    ≈ 201,8 points.
~~~

Đây là **hệ quả toán học của yêu cầu**, không phải tốc độ phát triển phần mềm thực. Trong 20 Sprint, mục tiêu cao gấp khoảng **6,73 lần** ban đầu, dù số người, số ngày làm việc và hệ thống có thể không đổi.

Tổ chức có thể kỳ vọng những cải tiến năng lực trong một giai đoạn, nhưng **tăng điểm theo phần trăm mãi mãi** không phải mô hình bền vững.

### 5.2. Giới hạn năng lực và điểm nghẽn

Một hệ thống giao phần mềm còn phụ thuộc vào:

- Năng lực làm rõ vấn đề và quyết định nghiệp vụ.
- Khả năng tích hợp và review.
- Môi trường kiểm thử và độ tin cậy CI.
- Kiến trúc, dữ liệu, bảo mật và quy trình phát hành.
- Nguồn phản hồi người dùng và vận hành.

Nếu nút thắt nằm ở việc chờ chuyên gia phân quyền, yêu cầu Developers tăng points **không làm hàng chờ chuyên gia biến mất**.

### 5.3. Thêm áp lực không tự tạo thêm thời gian

Một Sprint có timebox cố định. Để “tăng points” khi năng lực không tăng, đội có thể bị thúc đẩy:

- Làm thêm giờ.
- Ước lượng PBI bằng điểm cao hơn.
- Bỏ kiểm thử hoặc review.
- Ghi Done khi sản phẩm chưa tích hợp.
- Đưa việc rủi ro khỏi backlog đo.
- Chia ticket để điểm cộng trông nhiều hơn.

**Những biện pháp làm số tăng mà giá trị không tăng là tín hiệu metric đang bị dùng sai**, không phải bằng chứng đội đã có năng lực cao hơn.

## 6. “Hôm nay 40 points, Sprint sau phải 50” tạo động lực gì?

Một chỉ số khi chuyển thành **mục tiêu đánh giá hoặc thưởng/phạt** có thể làm thay đổi hành vi người bị đo. Đây là một dạng rủi ro thường được diễn đạt qua **Goodhart's law**: khi chỉ số trở thành mục tiêu, nó dễ mất đi khả năng phản ánh điều ban đầu định đo.

### 6.1. Tăng điểm ước lượng (point inflation)

Trước khi có KPI:

| PBI | Ước lượng theo quy ước đội |
|---|---:|
| Chỉnh hiển thị tiến độ | 3 |
| Bổ sung validation | 5 |
| Xử lý một điều kiện lỗi mạng | 8 |
| **Tổng** | **16** |

Sau khi đặt thưởng theo velocity, chính những hạng mục tương tự có thể bị ước lượng thành **5, 8, 13** points, tổng **26**.

~~~text
Tăng points báo cáo = (26 - 16) / 16 × 100%
                   = 62,5%

Nhưng nếu cùng phạm vi, cùng chất lượng và cùng thời gian,
không có bằng chứng năng lực tạo giá trị đã tăng 62,5%.
~~~

Số points tăng khi **thang ước lượng bị nới**. Khi điều đó xảy ra, so sánh velocity mới với cũ mà không ghi đổi định nghĩa là sai.

### 6.2. Chia ticket để tăng tổng points

Một user story **8 points** có thể được chia hợp lý thành hai lát giá trị độc lập, giúp kiểm chứng và giao sớm. Nhưng nếu bị ép tăng velocity, đội có thể tách thành:

- “Tạo DTO” — 3 points.
- “Tạo service” — 5 points.
- “Tạo controller” — 5 points.
- “Viết test” — 3 points.

Tổng thành **16 points**, nhưng không chắc có **bốn phần giá trị độc lập dùng được**. Nếu chỉ toàn bộ luồng tích hợp mới giúp người dùng hoàn thành tác vụ, đây là chia theo task kỹ thuật để báo cáo dễ hơn.

**Chia nhỏ là tốt khi giảm rủi ro và tăng phản hồi; chia để cộng thêm điểm không tự tăng giá trị.**

### 6.3. Đẩy chất lượng ra khỏi thời điểm Done

Nếu team vẫn dùng Definition of Done nhưng dưới áp lực đóng points, họ có thể gọi “code complete” là Done rồi đẩy test sang Sprint sau. Velocity nhìn tăng trong ngắn hạn, nhưng lỗi và công việc dở dang **chỉ chuyển sang nơi khác**.

Một bản báo cáo tăng points trong khi số PBI chưa đạt DoD, lỗi hậu triển khai và rework đều tăng **không thể coi là tiến bộ vững chắc**.

### 6.4. Tránh hạng mục khó và không được thưởng

Người phát triển có thể không muốn nhận:

- Lỗi không rõ nguyên nhân.
- Refactoring giúp giảm rủi ro dài hạn.
- Tạo hạ tầng kiểm thử.
- Hỗ trợ thành viên mới.
- Làm rõ phụ thuộc liên đội.
- Sự cố cần ứng phó ngay.

Những việc này thường có **giá trị hệ thống** nhưng khó quy đổi trực tiếp thành points Done trong Sprint. Hệ thống thưởng sai có thể làm chúng thiếu người làm.

### 6.5. Che chờ đợi và báo tiến độ ảo

Nếu quản lý chỉ muốn xem biểu đồ velocity tăng, người tham gia có thể ngại báo blocked time, giảm mức nghiêm trọng của bug hoặc bỏ hạng mục còn treo khỏi thống kê.

Khi ấy, tổ chức không chỉ mất tính chính xác của một con số mà còn mất **khả năng kiểm tra–thích ứng dựa trên thực tế**, vốn là phần quan trọng của Agile.

## 7. Vì sao không so sánh story points giữa các nhóm?

Story points **không được hiệu chuẩn chung**. Hai nhóm có thể cùng dùng dãy 1–2–3–5–8–13 nhưng gán điểm khác nhau cho cùng việc vì lịch sử, cách hiểu và tiêu chuẩn ước lượng khác nhau.

| Khía cạnh | Nhóm A | Nhóm B | Vì sao không so trực tiếp? |
|---|---|---|---|
| Hạng mục tham chiếu 5 points | Form có nhiều trạng thái UI | Thay đổi hợp đồng API có migration nhỏ | Hai mốc không cùng nội dung. |
| Thành viên | 7 Developers | 4 Developers | Quy mô không bằng nhau. |
| Loại công việc | Tính năng sản phẩm | Nền tảng và sự cố | Mức bất định và nghĩa vụ khác. |
| Definition of Done | UI, test và truy cập | Dữ liệu, bảo mật và phục hồi | Phạm vi kiểm chứng khác theo rủi ro. |
| Phụ thuộc | Chủ yếu trong một hệ thống | Nhiều dịch vụ và đối tác | Thời gian chờ và khả năng làm song song khác. |
| Công việc không dự báo | Ít | Trực sự cố thường xuyên | Năng lực có thể bị tiêu hao ngoài kế hoạch. |
| Thang ước lượng | Lịch sử riêng | Lịch sử riêng | Một point không có tỷ giá chung. |

### 7.1. Hai đội có cùng số points vẫn không chắc làm cùng lượng công việc

Giả sử cả hai đều hoàn thành **30 points**. Nhóm A có thể hoàn tất ba lát trải nghiệm người dùng, còn nhóm B bảo vệ dữ liệu trước một điều kiện đồng thời hiếm nhưng nghiêm trọng.

Số 30 không thể tự kết luận **độ khó, số giờ, giá trị hay chất lượng** bằng nhau.

### 7.2. “Points/người” không chữa được lỗi so sánh

Ví dụ:

~~~text
Nhóm A: 64 points / 8 người = 8 points/người/Sprint
Nhóm B: 36 points / 4 người = 9 points/người/Sprint
~~~

**Không có cơ sở nói nhóm B năng suất hơn 12,5%** chỉ vì tỷ lệ 9 so với 8. Points của hai nhóm không cùng đơn vị, chưa kể vai trò, nghỉ phép, sự cố, DoD và loại công việc.

Ngay trong một nhóm, **points/người** còn có thể tạo động lực cá nhân hóa công việc và giảm hợp tác.

### 7.3. “Một point chung cho toàn công ty” có giải quyết vấn đề?

Tổ chức có thể thống nhất định nghĩa, phân nhóm work item và DoD cho mục tiêu phối hợp. Nhưng cố tạo một **bảng điểm chung** vẫn khó biến points thành thước đo hiệu suất:

- Khác nhau về kiến trúc, dữ liệu, sản phẩm và rủi ro.
- Độ khó có thể tăng khi codebase hoặc nhu cầu thay đổi.
- Cùng mức effort không tạo cùng outcome.
- Ước lượng vẫn phụ thuộc sự hiểu biết và kinh nghiệm của nhóm.

Điều phối nhiều đội nên dùng **mục tiêu sản phẩm chung, phụ thuộc minh bạch, Increment tích hợp và số liệu flow theo loại việc**, không tìm một tỷ giá points để xếp hạng con người.

## 8. Khi nào có thể so sánh giữa các nhóm một cách có trách nhiệm?

Không nên suy ra **mọi phép so sánh** đều cấm. Cần phân biệt **benchmark thứ hạng** với **học hỏi giữa các điều kiện tương đương**.

Ví dụ, nhiều đội cùng làm trên một sản phẩm có thể xem:

- Các hạng mục bị chặn vì cùng một bước kiểm duyệt.
- Tỷ lệ lỗi nghiêm trọng theo phạm vi sản phẩm.
- Số lần phải làm lại do hợp đồng API đổi muộn.
- Các yếu tố khiến cycle time có phần đuôi dài.
- Mức tuân thủ Definition of Done chung khi áp dụng.
- Tác động người dùng trên một hành trình sản phẩm chung.

### 8.1. So sánh có điều kiện

Nếu xem cycle time của hai đội, cần làm rõ:

1. Định nghĩa **bắt đầu và Done** có tương đương?
2. Work item được chia theo nguyên tắc tương tự?
3. Loại việc, rủi ro và phụ thuộc có khác đáng kể?
4. Cửa sổ và số mẫu có đủ để đánh giá xu hướng?
5. Hai nhóm đang tối ưu cùng một outcome hay nhiệm vụ khác?
6. Bằng chứng có nhằm **tìm nút thắt và chia sẻ thực hành**, hay để thưởng/phạt?

Ngay cả với chỉ số đo cùng đơn vị thời gian, **khác biệt bối cảnh** vẫn cần được giải thích.

### 8.2. Chia sẻ thực hành, không chọn đội chiến thắng

Giả sử đội A có khả năng tự kiểm thử API hợp đồng tốt nên ít lỗi tích hợp muộn. Đội B có thể học cách thiết kế contract tests và CI. Nhưng không nên chuyển thành lệnh “B phải đạt đúng velocity của A” khi phần việc của B có rủi ro khác.

**Học từ cách làm tạo kết quả, thay vì xếp hạng con số không tương đương.**

## 9. Velocity không đồng nghĩa năng suất, output hay giá trị

Một chuỗi suy luận sai thường là:

> Nhiều story points hơn → làm nhiều hơn → tạo giá trị hơn → hiệu quả kinh doanh tốt hơn.

Mỗi mũi tên đều cần bằng chứng. Một đội có thể hoàn thành nhiều points cho tính năng không được dùng, trong khi đội khác sửa lỗi nhỏ giúp hàng nghìn học viên khôi phục tiến độ.

### 9.1. Phân biệt tầng đo

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Activity — hoạt động** | Đã dành thời gian làm gì? | Giờ coding, refinement, testing, họp. |
| **Output — đầu ra** | Đã tạo được khả năng nào? | Increment, PBI Done, phiên bản triển khai. |
| **Process outcome — kết quả dòng công việc** | Khả năng hoàn thành và học hỏi có tốt hơn? | Cycle time, blocked time, độ tin cậy CI, rework. |
| **Product outcome — kết quả người dùng** | Hành vi hoặc trải nghiệm có cải thiện? | Học viên tìm lại bài cũ nhanh hơn, ít xác nhận sai. |
| **Impact — tác động dài hạn** | Sản phẩm góp phần tạo ích lợi nào? | Học viên tiến bộ và duy trì học tập có chất lượng. |

Story points của PBI Done có thể giúp **ước lượng lượng backlog đã xử lý theo quy ước riêng**, nhưng không tự đại diện cho outcome.

### 9.2. Một PBI ít points có thể có giá trị lớn

Giả sử người dùng bị lỗi **trừ chỗ hai lần** khi gửi lại yêu cầu hủy sau timeout. Một thay đổi tương đối nhỏ về idempotency có thể ngăn dữ liệu sai ở nhiều trường hợp.

Nếu đội ước lượng nó **3 points**, không có lý do xem nó kém giá trị hơn một tính năng báo cáo **13 points** ít người sử dụng. **Giá trị và kích thước nỗ lực là hai chiều khác nhau.**

### 9.3. Một PBI nhiều points có thể không nên xây

Một hệ thống gợi ý khóa học **40 points** có thể thú vị về kỹ thuật, nhưng nếu người học chưa có nhu cầu hoặc chưa giải quyết được lỗi lưu tiến độ, Product Owner có thể đúng khi ưu tiên vấn đề đơn giản hơn.

**Tối đa hóa points hoàn thành có thể xung đột với tối đa hóa giá trị sản phẩm.**

## 10. Tối ưu points có thể làm tăng thời gian thực sự tới giá trị

Giả sử nhóm muốn đạt 50 points nên bắt đầu đồng thời tám PBI. Mỗi PBI chờ review, dữ liệu thử hoặc quyết định nghiệp vụ. Nhiều việc đã “80% xong” nhưng chưa đạt Done.

Một lựa chọn khác là giảm WIP, cùng tập trung hoàn thành hai lát giá trị, nhận phản hồi từ người dùng rồi mới kéo việc tiếp.

### 10.1. Hai cách nhìn tiến độ

| Cách báo cáo | Điều trông tốt | Rủi ro không nhìn thấy |
|---|---|---|
| “Đã coding xong 70% của 8 PBI” | Nhiều công việc đang tiến. | Chưa có Increment dùng được, tích hợp và test dồn cuối. |
| “Hoàn thành 2 lát giá trị đạt DoD, 1 lát đang thử” | Ít ticket nhìn thấy hơn. | Nhưng người dùng có thể nhận và phản hồi sớm hơn. |

Nếu áp lực KPI thúc đẩy đội báo phần trăm hoàn thành, cần cẩn trọng: **70% mã đã viết không có nghĩa 70% giá trị đã bàn giao**.

### 10.2. Little's Law là công cụ suy luận, không phép màu

Trong một hệ thống flow **tương đối ổn định** với các giả định phù hợp, định luật Little mô tả quan hệ giữa **số việc trung bình đang trong hệ thống, tốc độ hoàn thành trung bình và thời gian đi qua hệ thống**:

~~~text
Average WIP ≈ Average throughput rate × Average cycle time

Suy ra, cùng throughput rate:
  WIP cao hơn thường đi với cycle time cao hơn
  trong hệ thống ổn định và cùng ranh giới đo.
~~~

Đây **không** phải phương trình bảo đảm “cắt WIP một nửa thì chắc chắn cycle time giảm một nửa” trong mọi thực tế. WIP, thời gian và throughput phải được đo cùng phạm vi, cùng đơn vị, đủ ổn định; thay đổi rủi ro, tắc nghẽn và loại việc có thể khiến hiệu quả khác kỳ vọng.

## 11. Không biến một con số thành bảng xếp hạng nhân sự

Đánh giá **cá nhân** bằng points mà họ “đóng” khuyến khích cạnh tranh không lành mạnh và làm suy giảm phối hợp:

- Người hỗ trợ debug cho đồng nghiệp không được ghi nhận nếu ticket không đứng tên họ.
- Reviewer chuyên sâu làm giảm lỗi nhưng không “kiếm points” trực tiếp.
- Kỹ sư dạy người mới hoặc gỡ dependency cho nhóm khác trông ít thành tích.
- Người nhận sự cố khó có thể có ít points Done dù góp phần bảo vệ người dùng.
- Tranh giành ticket dễ làm thay việc giải quyết nút thắt chung.

### 11.1. Trách nhiệm giải trình không có nghĩa đo mọi người bằng một metric

Tổ chức vẫn cần đánh giá chất lượng công việc và phát triển năng lực nhân sự. Nhưng nên dựa trên **nhiều bằng chứng phù hợp vai trò, bối cảnh, chất lượng, hợp tác và tác động**, với chính sách công bằng và quyền riêng tư.

Velocity không được thiết kế như thước đo xếp hạng từng lập trình viên, và việc cá nhân hóa số đó sẽ làm hỏng mục đích **dự báo của đội**.

### 11.2. Một lời nhắc quan trọng

Không nên hỏi:

> “Ai đang kéo velocity của chúng ta xuống?”

Thay vào đó:

> “Công việc đang chờ ở đâu? Có phụ thuộc hoặc quyết định nào khiến đội không hoàn thành lát giá trị? Chúng ta bảo vệ chất lượng và giúp nhau giải quyết thế nào?”

**Câu hỏi dẫn tới hành động cải tiến hệ thống quan trọng hơn câu hỏi dẫn tới tìm người chịu lỗi.**

## 12. Khi velocity thay đổi, điều tra điều gì trước khi kết luận?

Một Sprint có velocity thấp hơn không tự động chứng minh đội yếu đi; một Sprint cao hơn cũng không tự động chứng minh cải tiến. Hãy xem cả **cách đo, bối cảnh và outcome**.

### 12.1. Kiểm tra tính nhất quán của phép đo

- Đội có cùng quy ước story points và loại PBI không?
- Definition of Done có thay đổi không?
- Có tình trạng tính cả task chưa hoàn thành hoặc công việc “gần xong”?
- Hạng mục chuyển qua nhiều Sprint được tính một lần hay bị cộng trùng?
- PBI bị bỏ, tách hoặc thay scope được ghi nhận nhất quán không?
- Có đổi công cụ, tự động hóa báo cáo hoặc trường dữ liệu không?
- Có ép ước lượng lại để số Sprint hiện tại đẹp hơn không?

Nếu thang đo hoặc cách ghi nhận đổi, **không nên so hai số như một chuỗi hoàn toàn cùng nghĩa**.

### 12.2. Kiểm tra nguồn lực và biến động công việc

| Yếu tố | Tình huống minh họa | Cách đọc |
|---|---|---|
| **Nghỉ phép/ngày lễ** | Hai Developers nghỉ vài ngày. | Năng lực Sprint giảm; không cần thay độ lớn points của PBI. |
| **Sự cố sản phẩm** | Có lỗi dữ liệu cần khắc phục ngay. | Năng lực chuyển sang rủi ro cấp bách, có thể giảm points kế hoạch. |
| **Onboarding** | Kỹ sư mới cần mentoring. | Đầu tư tạo năng lực tương lai, không nên gọi mentoring là lãng phí. |
| **Phụ thuộc** | Chờ API hoặc người duyệt bên ngoài. | Velocity thấp có thể do hàng chờ hệ thống. |
| **Kiến trúc và CI** | Pipeline đỏ hoặc flaky tests. | Thời gian chờ tích hợp tăng; cần đầu tư kỹ thuật. |
| **Thay đổi backlog** | Product Owner phát hiện giả thuyết sai, không xây tiếp tính năng. | Ít points hơn có thể là quyết định giá trị tốt. |
| **Giảm nợ kỹ thuật** | Refactoring/kiểm chứng dữ liệu khó. | Cần xem rủi ro và năng lực thay đổi, không chỉ ticket Done. |
| **Cách tách PBI** | Đội bắt đầu chia lát giá trị nhỏ hơn. | Độ lớn points của mỗi hạng mục có thể đổi; không so cơ học. |

### 12.3. Đừng phản ứng với một điểm dữ liệu

Velocity của một Sprint có thể bị ảnh hưởng bởi vài PBI chưa Done. Một chuỗi có biến động vừa phải cần được đọc qua **nhiều Sprint và sự kiện bối cảnh**, tránh đặt mục tiêu tăng ngay sau một Sprint thấp.

Tư duy phù hợp:

> “Điều gì đã thay đổi trong hệ thống, và nó có ảnh hưởng tới khả năng giao Increment dùng được không?”

Không phải:

> “Ai đã làm cho đồ thị đi xuống?”

## 13. Dự báo bằng velocity: dùng phân phối và khả năng thực tế

Khi một đội có lịch sử ước lượng tương đối ổn định, velocity có thể hỗ trợ forecast **cục bộ**. Nhưng cần nêu tính biến động và điều kiện làm việc.

### 13.1. Một chuỗi ví dụ

Giả sử năm Sprint gần đây cùng một đội ghi:

| Sprint | Velocity (points đã Done) | Bối cảnh giả định |
|---|---:|---|
| S1 | 21 | Bình thường. |
| S2 | 27 | Ít phụ thuộc. |
| S3 | 24 | Có một PBI phức tạp. |
| S4 | 20 | Có sự cố sản phẩm. |
| S5 | 28 | Nhiều PBI nhỏ đã hoàn tất. |
| **Tổng** | **120** | **Cùng thang ước lượng của đội.** |

~~~text
Trung bình velocity = (21 + 27 + 24 + 20 + 28) / 5
                    = 120 / 5 = 24 points/Sprint

Trung vị velocity = 24 points/Sprint

Khoảng quan sát được = 20–28 points/Sprint
~~~

Không có lý do nói Sprint tiếp theo **chắc chắn** 24 points. Các Sprint có cùng đội vẫn khác về loại việc, năng lực và phụ thuộc.

### 13.2. Một forecast sơ bộ cho backlog

Nếu một nhóm PBI được ước lượng **73 points** theo cùng quy ước:

~~~text
Ước lượng theo trung bình lịch sử = 73 / 24
                                ≈ 3,04 Sprint
~~~

Điều đó **không phải lời hứa hoàn thành sau đúng 3,04 Sprint**. Nếu năng lực giống chuỗi gần đây và các PBI đủ nhỏ để đóng trong Sprint, nhóm có thể thảo luận **khoảng 3–4 Sprint** như một hướng nhìn ban đầu; cần cập nhật theo phụ thuộc, sự cố, hạng mục lớn chưa tách và mức bất định.

Ngay cả khoảng 3–4 chỉ là **minh họa dựa trên lịch sử hạn chế**, không phải khoảng tin cậy thống kê hay xác suất ấn định. Nếu backlog chứa một migration chưa hiểu, forecast có thể kém đáng tin hơn nhiều.

### 13.3. Dự báo phải được cập nhật khi backlog thay đổi

Product Backlog là danh sách tiến hóa. Nếu người dùng phản hồi rằng một tính năng không cần thiết, Product Owner có thể bỏ hoặc thay hạng mục. Forecast mới phải phản ánh **những gì còn đáng làm**, không coi việc giảm points còn lại là “đội đã sản xuất được phần chênh lệch”.

### 13.4. Đặt mục tiêu Sprint theo giá trị, không theo số trung bình

Trong Sprint Planning, Developers cân nhắc năng lực, hiệu quả quá khứ, Definition of Done và kế hoạch hướng tới **Sprint Goal**. Velocity có thể là một dữ kiện phụ; **Sprint Goal** không nên chỉ là “đóng 24 points”.

Ví dụ Sprint Goal:

> “Học viên có thể tiếp tục bài gần nhất trên thiết bị khác mà tiến độ không bị ghi sai.”

Nếu xuất hiện lỗi phân quyền trong luồng này, việc tập trung sửa và xác minh có thể quan trọng hơn lấy thêm một PBI 3 points để đạt mục tiêu điểm.

## 14. Năng lực của Sprint không chỉ là số người nhân số ngày

Khi muốn giải thích velocity giảm, một cách đơn giản là nhìn **capacity** thực tế, nhưng không biến capacity thành tỷ giá story points.

### 14.1. Tính năng lực thời gian có sẵn để đối thoại

Giả sử nhóm có bốn Developers, mỗi người dự kiến làm việc 10 ngày trong Sprint. Một người nghỉ 4 ngày; hai người tham gia hỗ trợ sự cố tổng 3 ngày làm việc:

~~~text
Năng lực lý thuyết ban đầu = 4 × 10 = 40 person-days
Trừ nghỉ phép                = 4 person-days
Trừ hỗ trợ sự cố             = 3 person-days
Năng lực còn lại sơ bộ       = 33 person-days
~~~

Phép tính giúp làm rõ **thời gian khả dụng**, không phải bảo đảm 33 ngày đó chuyển được thành số points cụ thể. Việc review, phối hợp, học kỹ năng, sửa môi trường và bất định còn ảnh hưởng.

### 14.2. Công thức “mỗi người phải làm X points” rất dễ sai

Nếu đội có vận tốc trung bình 24 points với bốn người, không nên suy ra:

> “Mỗi người phải làm 6 points; tuyển thêm người là Sprint sau chắc đạt 30.”

Phần mềm có phụ thuộc, kỹ năng và chi phí phối hợp. Người mới có thể cần thời gian học; số người tăng không bảo đảm throughput hay giá trị tăng tuyến tính.

### 14.3. Không dùng capacity để ép làm đủ 100%

Capacity planning có ích để **tránh cam kết vượt điều kiện thực**, không phải để lấp kín mọi phút bằng ticket. Hệ thống còn cần thời gian xử lý bất định, học hỏi, kiểm thử, cải tiến và phục hồi.

**Một đội bền vững không phải đội có biểu đồ sử dụng nhân sự luôn bằng 100%.**

## 15. Khi points không đáng tin, có thể dự báo bằng throughput

**Throughput** là số work item hoàn thành trong một khoảng thời gian theo định nghĩa rõ. Nó không cần dùng story points.

Ví dụ, trong năm Sprint, một đội hoàn thành:

| Sprint | Số PBI đạt DoD |
|---|---:|
| S1 | 4 |
| S2 | 6 |
| S3 | 5 |
| S4 | 7 |
| S5 | 3 |
| **Tổng** | **25** |

~~~text
Throughput trung bình = 25 / 5 = 5 PBI/Sprint

Nếu backlog hiện có 17 PBI tương tự:
  Forecast trung bình thô = 17 / 5 = 3,4 Sprint.
~~~

**3,4 Sprint không phải cam kết.** Nếu kích thước PBI khác nhau, việc chia ticket thay đổi, có nhiều phụ thuộc hoặc số hạng mục mới phát sinh, dự báo cần xem lại.

### 15.1. Throughput cũng có thể bị gaming

Đặt KPI “mỗi Sprint phải đóng 20 PBI” có thể khiến đội:

- Chia PBI thành task nhỏ không mang giá trị độc lập.
- Chọn việc dễ trước.
- Bỏ các hạng mục phức tạp.
- Đóng công việc chưa đạt DoD.

Vì vậy, **đổi velocity thành throughput KPI không tự giải quyết sai lầm**. Cần quan tâm mục đích, định nghĩa, rủi ro và outcome.

### 15.2. Khi nào throughput phù hợp hơn story points?

Có thể hữu ích khi:

- Đội chia PBI thành những lát giá trị tương đối đồng đều và đủ nhỏ.
- Dữ liệu hoàn thành nhiều kỳ được ghi ổn định.
- Đội muốn giảm chi phí họp ước lượng.
- Đội quản lý dòng Kanban liên tục thay vì Sprint.

Nếu loại việc quá khác biệt, nên **phân loại công việc hoặc kết hợp với cycle time** để tránh một con số trung bình che biến động.

## 16. Cycle time, work item age và WIP cho thấy vấn đề mà velocity không thấy

Velocity ghi nhận **tổng points Done trong Sprint** theo thang đo đội. Nó không trực tiếp cho biết từng hạng mục **đợi bao lâu** hay công việc nào đang kẹt.

### 16.1. Các phép đo flow

| Chỉ số | Định nghĩa dùng trong thực hành | Câu hỏi có thể trả lời |
|---|---|---|
| **WIP** | Số work item đã bắt đầu nhưng chưa Done trong ranh giới đo. | Có quá nhiều việc đang dở? |
| **Cycle time** | Thời gian từ điểm bắt đầu tới Done theo chính sách đã thống nhất. | Một hạng mục đi qua hệ thống mất bao lâu? |
| **Work item age** | Thời gian từ lúc bắt đầu tới hiện tại của item chưa Done. | Item nào có nguy cơ chậm và cần trợ giúp? |
| **Throughput** | Số work item Done trong một kỳ. | Hệ thống hoàn thành được bao nhiêu item? |
| **Blocked time** | Thời gian ở trạng thái chờ được xác định. | Đội đang chờ người, dữ liệu hoặc môi trường ở đâu? |
| **SLE** | Kỳ vọng thời gian hoàn thành dựa trên dữ liệu và chính sách. | Có thể báo kỳ vọng theo phân phối lịch sử thế nào? |

Các phép đo có thể phối hợp, không có chỉ số duy nhất thay thế tất cả.

### 16.2. Ví dụ một vấn đề ẩn sau velocity

Giả sử đội đạt đều **30 points/Sprint** trong ba Sprint. Lãnh đạo cho rằng mọi thứ ổn. Nhưng:

- WIP tăng từ **6 lên 13** hạng mục.
- Nhiều PBI chưa Done có **work item age** vượt kỳ vọng.
- Thời gian chờ review tăng.
- Số lần context switching tăng.

Velocity ổn định có thể che **hàng chờ đang phình**. Nhóm cần xem khả năng hoàn thành Increment và nút thắt thay vì chỉ giữ một đồ thị ngang.

### 16.3. Đừng chuyển việc sang cột Waiting để làm đẹp số

Nếu PBI bị chặn và nhóm chuyển nó sang một cột không tính WIP hoặc cycle time, báo cáo có thể cải thiện giả. Cần định nghĩa nhất quán **điểm bắt đầu, kết thúc, khi nào tính thời gian chờ**, đồng thời giữ thông tin bị chặn rõ ràng.

### 16.4. Không dùng thời gian chu kỳ để phạt việc khó

Một thay đổi dữ liệu cần kiểm tra nhiều hệ thống có thể tốn lâu hơn PBI sửa nội dung. Để cải tiến, cần phân khúc theo loại việc và rủi ro, xem những trường hợp dài nhất và điều kiện hệ thống, **không tự kết luận người làm item dài là kém hiệu quả**.

## 17. Dự báo theo phân phối, không hứa ngày hoàn thành bằng một số trung bình

Một nhóm có thể dùng dữ liệu throughput hoặc cycle time lịch sử để mô phỏng kịch bản giao hàng. **Mục tiêu là minh bạch độ bất định**, không khoác lên con số một vẻ chính xác khoa học khi dữ liệu yếu.

### 17.1. Một cách báo dự báo có trách nhiệm

Thay vì:

> “Backlog còn 73 points, trung bình 24; chắc chắn hoàn thành sau 3 Sprint.”

Nên:

> “Với velocity lịch sử của chính đội quanh 20–28 points/Sprint và giả định backlog hiện tại còn phù hợp với cách ước lượng đó, phần việc 73 points có thể cần khoảng 3–4 Sprint trong điều kiện tương tự. Chúng ta sẽ cập nhật sau mỗi Sprint; những phụ thuộc và yêu cầu khẩn chưa được phản ánh đầy đủ.”

Đây là **mô tả có điều kiện**, không phải xác suất thống kê được chứng minh.

### 17.2. Khi nào dùng Monte Carlo?

Khi có đủ dữ liệu flow/throughput đáng tin và phạm vi tương đối ổn định, nhóm có thể dùng **mô phỏng Monte Carlo** để tạo một **phân phối kết quả có điều kiện theo giả định**.

Nhưng phải giải thích:

- Dữ liệu quá khứ có đại diện cho công việc sắp tới?
- Có đổi team, policy, backlog, DoD hoặc nhịp release?
- Item được chia theo cùng logic?
- Các quan sát có đủ nhiều, có bị chọn lọc?
- Kịch bản sự cố hoặc phụ thuộc chưa tính sẽ tác động thế nào?

Một phần mềm mô phỏng cho ra “xác suất 85%” **không tự làm số đó đáng tin** nếu dữ liệu hoặc giả định sai.

### 17.3. Không dùng xác suất để làm cam kết ẩn

Nếu báo “khoảng 85% khả năng xong trong quý” nhưng hợp đồng lại coi đó là nghĩa vụ chắc chắn, tổ chức đã đổi nghĩa phép đo. Các nghĩa vụ cứng phải được **thỏa thuận rõ với quyền, scope, rủi ro và điều kiện thay đổi**, không nấp sau một forecast.

## 18. SLE và dữ liệu Kanban: kỳ vọng theo xác suất không phải bảo đảm

Trong một dòng công việc tương đối ổn định, team có thể phát biểu một **Service Level Expectation (SLE)** cho loại work item cụ thể.

Ví dụ minh họa:

> “Trong 40 hạng mục Standard đã hoàn thành gần đây, 34 hạng mục có cycle time không quá 10 ngày làm việc.”

~~~text
34 / 40 × 100% = 85%
~~~

Đây là **tỷ lệ quan sát lịch sử**, không chứng minh hạng mục tiếp theo chắc chắn hoàn thành trong 10 ngày, cũng không tự động là **SLA hợp đồng**.

Khi công việc khẩn, loại item hoặc chính sách thay đổi, cần cập nhật phân phối và kỳ vọng.

### 18.1. SLE có thể gợi hành động sớm

Nếu một hạng mục chưa Done đã có tuổi gần hoặc vượt kỳ vọng, đội có thể hỏi:

- Nó đang chờ quyết định nào?
- Có phụ thuộc liên đội hoặc test nào bị chặn?
- Có thể hỗ trợ hoàn thành trước khi kéo việc mới không?
- Có cần cập nhật người liên quan về rủi ro thời gian?

Điều này có thể thực tế hơn yêu cầu **velocity cuối Sprint phải tăng**, vì nhóm có cơ hội can thiệp vào công việc đang kẹt.

### 18.2. Không nâng ngưỡng SLE để giấu hàng chờ

Nếu cycle time xấu đi, đội không nên âm thầm đổi SLE rồi tuyên bố mọi việc vẫn “đạt”. Có thể cập nhật kỳ vọng sau khi xem dữ liệu và bối cảnh, nhưng cần **ghi lại thay đổi và hành động cải tiến**.

## 19. Bảo vệ chất lượng và tính đúng khi đo năng lực

Nếu một đội tăng throughput/velocity mà bỏ kiểm thử, tổ chức có thể nhận về **nhiều lỗi hơn, tăng rework và chi phí vận hành**. Cần xem các chỉ số **guardrail** phù hợp.

### 19.1. Ví dụ guardrails

| Hướng cải tiến | Primary metric khả dĩ | Guardrails cần xem |
|---|---|---|
| Giảm chờ review | Thời gian tới phản hồi chuyên môn đầu tiên. | Lỗi hậu merge, tải reviewer, vùng bảo mật chưa kiểm tra. |
| Tích hợp sớm hơn | Thời gian từ commit tới kiểm chứng tích hợp. | Flaky tests, lỗi dữ liệu, độ ổn định CI. |
| Giảm WIP | Cycle time, work item age, blocked time. | Không trì hoãn sự cố khẩn; không tăng lỗi; không làm ngoài giờ. |
| Chia PBI theo lát nhỏ | Thời gian tới Increment dùng được và phản hồi. | DoD, lỗi tích hợp, giá trị thực của lát. |
| Tăng tốc phục hồi lỗi | Thời gian phát hiện/giảm tác động/khôi phục. | Tính đúng dữ liệu, quy trình ứng phó, tải trực. |
| Cải thiện khả năng tiếp cận | Tỷ lệ hoàn thành hành trình bằng công nghệ hỗ trợ. | Không làm hỏng hành vi của nhóm người dùng khác. |

### 19.2. Số lỗi thấp có thể phản ánh việc không phát hiện lỗi

Nếu KPI thưởng khi “ít bug”, đội có thể ngại ghi bug. Cần xét **chất lượng kiểm tra và độ minh bạch của báo cáo**, không đơn giản xem ít ticket lỗi là tốt.

Tương tự, một tỷ lệ deployment thất bại thấp có thể do đội **ngừng triển khai những thay đổi quan trọng**, không tự chứng minh năng lực phát hành tốt.

### 19.3. Không đánh đổi Definition of Done

Definition of Done tạo tiêu chuẩn chất lượng chung cho Increment. Một PBI không đạt tiêu chuẩn này **không nên được gọi là Done để thu points**.

Khi lịch, scope và chất lượng xung đột, cách làm Agile phù hợp là **minh bạch và điều chỉnh kế hoạch trong phạm vi quyền**, không che việc chưa xong.

## 20. Đo outcome người dùng để tránh sản xuất nhiều tính năng không cần

Giả sử mục tiêu sản phẩm là giúp học viên quay lại học và không mất tiến độ. Đội có thể theo dõi:

- **Tỷ lệ học viên quay lại một hoạt động học có ý nghĩa trong bảy ngày**, theo cohort đủ thời gian quan sát.
- **Thời gian cần để tìm lại bài gần nhất** trong hành trình thực.
- **Tỷ lệ hoàn thành tác vụ đăng ký/hủy đúng** trong các trường hợp mục tiêu.
- **Lỗi xác nhận sai hoặc mất tiến độ**, được điều tra theo mức ảnh hưởng.
- **Phản hồi về tính dễ dùng và accessibility**.

Đây là những chỉ số gần **giá trị người dùng** hơn story points, nhưng vẫn cần định nghĩa tử số, mẫu số, nguồn và cửa sổ đo.

### 20.1. Ví dụ một outcome thay vì points

Trong một phép đo giả định:

| Cohort | Học viên đủ điều kiện | Có hoạt động học có ý nghĩa trong bảy ngày | Tỷ lệ |
|---|---:|---:|---:|
| Trước thử | 1.000 | 240 | 24% |
| Sau thử | 1.000 | 320 | 32% |

~~~text
Thay đổi tuyệt đối = 32% - 24% = 8 điểm phần trăm
Thay đổi tương đối = (32 - 24) / 24 × 100% ≈ 33,3%
~~~

Đây là **số liệu minh họa**. Nó **không chứng minh tính năng mới gây ra toàn bộ mức tăng** nếu hai cohort khác nhau về nội dung, mùa vụ, thiết bị hoặc thông báo. Có thể cần thử nghiệm phù hợp hoặc phân tích bổ sung.

### 20.2. Outcome cũng có thể bị chơi số

Nếu đặt mục tiêu “tăng số click nút Tiếp tục học”, team có thể làm nút nổi bật hơn mà chưa giúp học viên thực sự học tiếp. Nếu chỉ thưởng “giữ chân cao”, có thể vô tình tối ưu những nhóm người dùng dễ quay lại và bỏ qua nhóm cần hỗ trợ.

Vì vậy, **không đơn giản thay velocity bằng một outcome KPI rồi bỏ guardrails và kiểm tra định nghĩa**. Cần nhiều góc nhìn và ra quyết định dựa trên giá trị thực.

## 21. Một scorecard cân bằng cho đội sản phẩm

Không có bộ chỉ số chung bắt buộc cho mọi đội. Một scorecard ngắn nên được **thiết kế từ Product Goal và rủi ro cụ thể**.

| Câu hỏi | Chỉ số minh họa | Dấu hiệu cần xem cùng |
|---|---|---|
| Người dùng có nhận giá trị? | Tỷ lệ hoàn thành tác vụ học quan trọng. | Lỗi, accessibility, cohort và phản hồi định tính. |
| Đội có giao an toàn? | Chất lượng Increment, lỗi sau triển khai, phục hồi. | Độ bao phủ rủi ro và cách phát hiện lỗi. |
| Flow có tốt hơn? | Cycle time, throughput, work item age, blocked time. | WIP, loại việc, phụ thuộc và thay đổi cách chia item. |
| Có học hỏi sớm? | Thời gian từ giả thuyết tới phản hồi dùng được. | Chất lượng thí nghiệm và quyết định đã thay đổi. |
| Có bền vững? | Tải ngoài giờ, thời gian chờ review, khả năng tập trung. | Quyền riêng tư và công bằng khi thu dữ liệu. |
| Có kiểm soát nguồn lực? | Forecast theo khoảng, actual và rủi ro. | Không đồng nhất chi ít hay chi hết với giá trị. |

Velocity nếu được dùng có thể xuất hiện **như dữ liệu dự báo riêng của đội**, không phải một cột xếp hạng.

### 21.1. Mỗi metric phải dẫn tới hành động

Trước khi thêm chỉ số, hỏi:

1. Câu hỏi quyết định nào nó hỗ trợ?
2. Ai có quyền hành động?
3. Dữ liệu có đáng tin và rủi ro diễn giải sai là gì?
4. Nếu tăng hoặc giảm, nhóm sẽ làm gì khác?
5. Có guardrail nào ngăn tối ưu một chiều?

Một dashboard có 40 metric mà không ai sử dụng để cải tiến có thể tạo **chi phí thu thập cao nhưng rất ít giá trị**.

## 22. Scrum: Product Goal và Sprint Goal không phải “đạt càng nhiều points càng tốt”

Trong Scrum, **Product Goal** định hướng giá trị dài hơn, còn **Sprint Goal** mang mục tiêu của Sprint. Developers lập kế hoạch thực hiện, kiểm tra–thích ứng và tạo Increment đáp ứng Definition of Done.

### 22.1. Sprint Goal có ý nghĩa hơn tổng points được nhặt

Một Sprint Goal minh họa:

> “Học viên có thể hủy đăng ký buổi học hợp lệ mà số chỗ được cập nhật đúng kể cả khi gửi lại yêu cầu.”

Giả sử đội đạt Sprint Goal và Increment đáp ứng DoD với **18 points**, trong khi Sprint trước đạt **26 points** cho các việc khác. Không thể kết luận Sprint hiện tại kém thành công chỉ từ chênh lệch points.

Nếu đội xử lý được một lỗi dữ liệu rủi ro cao, **giá trị và độ tin cậy có thể tốt lên dù velocity thấp**.

### 22.2. Vai trò cần được hiểu đúng

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog.
- **Developers** chịu trách nhiệm tạo Sprint Backlog, chất lượng và các Increment đáp ứng Definition of Done.
- **Scrum Master** hỗ trợ hiệu quả Scrum Team và giúp tổ chức hiểu, áp dụng Scrum phù hợp.
- **Stakeholders và người có thẩm quyền quản trị** cung cấp mục tiêu, ràng buộc và phản hồi nhưng không dùng velocity để thay thế trách nhiệm sản phẩm.

Nếu lãnh đạo yêu cầu velocity tăng 20%, Scrum Master không cần chỉ giải thích công thức tính điểm. Cần giúp các bên nhận ra **mục tiêu thật là giá trị, năng lực giao phần dùng được hay khả năng dự báo**, rồi chọn bằng chứng tương ứng.

### 22.3. Daily Scrum không phải buổi kiểm điểm điểm số

Daily Scrum dành để Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh kế hoạch. Nếu mọi ngày chỉ hỏi “hôm nay làm thêm mấy points”, tổ chức dễ mất khả năng phát hiện blocker và phối hợp hoàn thành phần quan trọng.

### 22.4. Sprint Review không phải buổi tuyên dương velocity

Sprint Review giúp Scrum Team và stakeholders kiểm tra kết quả Sprint và điều chỉnh hướng tương lai. Nên trình bày **Increment, phản hồi người dùng, dữ liệu sản phẩm, rủi ro và điều có thể đổi ở Product Backlog**, không chỉ đồ thị points.

## 23. Kanban và XP: tập trung vào flow, chất lượng và phản hồi kỹ thuật

### 23.1. Kanban không yêu cầu velocity

Kanban giúp **trực quan hóa công việc, quản lý WIP và flow, làm rõ chính sách, dùng vòng phản hồi và cải tiến cộng tác**. Một nhóm có thể dự báo bằng throughput, cycle time và SLE mà không hề gán story points.

Với công việc trực sự cố nhiều biến động, việc buộc gán điểm và đặt tăng velocity theo Sprint đôi khi làm lệch ưu tiên ứng phó rủi ro.

### 23.2. XP giúp tạo khả năng thay đổi an toàn

Những thực hành như **TDD, pair programming, refactoring, continuous integration và kiểm thử tự động** có thể:

- Rút ngắn vòng phản hồi kỹ thuật.
- Giảm lỗi tích hợp và làm lại.
- Chuyển giao tri thức giữa thành viên.
- Giúp thay đổi backlog thường xuyên mà không làm giảm chất lượng.

Đầu tư vào các thực hành đó đôi khi **làm ít PBI Done hơn trong giai đoạn học**, nhưng có thể tạo năng lực thay đổi dài hạn. Nên đo kết quả thực và chi phí duy trì, không yêu cầu số points phải tăng ngay trong Sprint đầu áp dụng.

### 23.3. Tăng tần suất deploy chưa tự chứng minh giá trị

Một đội có thể tăng số lần triển khai nhờ CI tốt hơn, nhưng vẫn cần theo dõi **lỗi sau release, khả năng phục hồi và outcome người dùng**. Đây là ví dụ vì sao nhiều chỉ số cần **được đọc chung**, không chuyển sang một KPI tốc độ đơn lẻ khác.

## 24. Nhiều nhóm cùng một sản phẩm: phối hợp bằng mục tiêu chung, không cộng points tùy tiện

Khi nhiều Scrum Team cùng phát triển một sản phẩm, điều quan trọng là **Increment tích hợp và Product Goal chung**, không phải tổng số points từng nhóm cộng lại.

### 24.1. Cạm bẫy “velocity cấp chương trình”

Giả sử:

~~~text
Nhóm A dùng thang ước lượng riêng: 50 points/Sprint.
Nhóm B dùng thang ước lượng riêng: 30 points/Sprint.

50 + 30 = 80 (về số học).
Nhưng "80 points/Sprint cấp sản phẩm" không có đơn vị
ước lượng thống nhất được xác minh.
~~~

Phép cộng đúng số học nhưng **không tự có ý nghĩa đo lường**. Nó không thể chứng minh sản phẩm giao nhanh hơn, cũng không hỗ trợ dự báo đáng tin khi backlog có phụ thuộc giữa A và B.

### 24.2. Điều cần biết để giao một lát giá trị xuyên đội

| Câu hỏi | Minh chứng phù hợp |
|---|---|
| Mục tiêu sản phẩm nào đang được ưu tiên? | Product Goal, các outcome và quyết định Product Backlog. |
| Lát giá trị nào cần nhiều đội phối hợp? | User story/feature outcome và dependency map. |
| Hợp đồng giữa các thành phần có ổn định? | API contract, ví dụ nghiệp vụ và kiểm thử tích hợp. |
| Có một Increment dùng được chưa? | Bằng chứng tích hợp và Definition of Done áp dụng. |
| Hạng mục đang bị chặn ở đâu? | Work item age, blocked time, dòng phụ thuộc và owner. |
| Người dùng đã nhận giá trị chưa? | Kết quả sử dụng trong phạm vi quan sát và phản hồi thực. |
| Có thể dự báo giao tiếp theo những gì? | Lịch sử flow của các lát tương đương, phụ thuộc và mức bất định. |

Nếu nhiều đội Scrum cùng phát triển **một sản phẩm**, họ cần chia sẻ Product Goal, Product Backlog và Definition of Done thống nhất theo Scrum. Điều đó **không biến thang story point riêng của các đội thành một phép đo năng suất chung**.

### 24.3. Tổng hợp forecast bằng phần giá trị tích hợp

Một bản forecast liên đội có thể theo dõi:

- Các lát giá trị có acceptance criteria và phụ thuộc đã làm rõ.
- Trạng thái tích hợp thực tế, không chỉ task Done của từng đội.
- Khoảng thời gian qua hàng chờ review, bảo mật, pháp lý hoặc đối tác.
- Điều kiện phát hành và độ tin cậy của kiểm chứng.
- Tác động sản phẩm quan sát sau khi người dùng có thể sử dụng.

Việc tổng hợp phải xem **nút thắt chung**, không lấy năng suất giả định từ phép cộng points.

## 25. Những tình huống tính velocity cần có chính sách rõ

Một số sai lệch không đến từ ý đồ gian lận mà từ việc đội **chưa thống nhất cách ghi dữ liệu**.

| Tình huống | Cách xử lý nên thảo luận | Điều cần tránh |
|---|---|---|
| PBI chưa đạt DoD cuối Sprint | Không tính PBI đó vào points Done của Sprint đang kết thúc. | Cộng 70% points dựa trên cảm giác “sắp xong”. |
| PBI chuyển sang Sprint sau | Ghi trạng thái thật, hoàn tất và tính theo chính sách đội khi đạt DoD; tránh tính trùng. | Cộng một hạng mục vào hai Sprint. |
| PBI bị chia thành nhiều lát | Tách theo giá trị và điều kiện Done; làm rõ ước lượng mới và lưu lịch sử nếu cần. | Chia chỉ để tổng points tăng. |
| PBI bị hủy vì giả thuyết sai | Ghi quyết định và bài học; không tự coi points hủy là output đã giao. | Đếm “đã tiết kiệm 13 points” như points hoàn thành. |
| Nhu cầu mới xuất hiện giữa Sprint | Developers điều chỉnh Sprint Backlog, hợp tác với Product Owner theo quy tắc Scrum và Sprint Goal. | Tự thêm vào rồi dùng chênh lệch điểm để đánh giá ai chịu lỗi. |
| Sự cố ngoài kế hoạch | Minh bạch tác động và công việc thực; nếu ước lượng, dùng quy ước nhất quán. | Giấu sự cố vì không đóng góp velocity. |
| Một task kỹ thuật cần thiết | Theo dõi công việc và rủi ro, có thể là PBI hoặc phần kế hoạch theo chính sách nhóm. | Gán points chỉ để “nhận công” mà mất ý nghĩa dữ liệu. |
| Đội thay đổi thang ước lượng | Ghi thời điểm, lý do, định nghĩa mới và giới hạn so với lịch sử cũ. | Nối đồ thị như không có thay đổi phép đo. |
| Một Increment đã đạt DoD nhưng chưa release | Phân biệt DoD, Increment và hành động release theo quy tắc sản phẩm. | Gọi chưa có giá trị đã quan sát là outcome chắc chắn. |
| Nâng tiêu chuẩn DoD | Xem sự thay đổi về lượng kiểm chứng, năng lực và lịch sử đo. | Phạt team vì điểm giảm khi chất lượng được tăng. |

### 25.1. “Re-estimate khi PBI xong” có thể làm lịch sử khó hiểu

Nếu đội dự kiến 8 points nhưng sau khi thực hiện lại đổi thành 13 để “phản ánh công sức”, dữ liệu mới có thể phản ánh **nhận thức đã biết kết quả** thay vì chất lượng dự báo ban đầu.

Điều quan trọng là **thống nhất mục đích ước lượng**. Với dự báo, có ích khi biết ước lượng tại thời điểm quyết định và hiểu sai lệch đã xảy ra ở đâu. Không cần cấm mọi điều chỉnh, nhưng cần **tránh sửa quá khứ mà không giữ bối cảnh**.

### 25.2. Công việc không có story points không phải công việc vô giá trị

Hỗ trợ sự cố, cố vấn nhân sự mới, xử lý bảo mật hoặc duy trì hạ tầng có thể không được nhóm gán story points. Đừng kết luận **không có points nghĩa là không đóng góp**.

### 25.3. “Done ảo” nguy hiểm hơn việc velocity thấp

Nếu người quản lý dùng velocity làm chỉ tiêu, nhóm có thể bị thúc đẩy bỏ qua yêu cầu DoD. Hậu quả là **forecast thiếu tin cậy, chất lượng bị che và giá trị người dùng bị ảnh hưởng**. Chính sách rõ về Done quan trọng hơn cố làm đẹp biểu đồ.

## 26. Case study: hai đội bị yêu cầu tăng velocity 25%

**Toàn bộ công ty, số liệu, tên đội, sự kiện và kết quả trong case study này đều giả định để học.** Không đại diện cho dữ liệu một doanh nghiệp thật.

### 26.1. Bối cảnh sản phẩm

Một nền tảng học trực tuyến muốn cải thiện việc học viên quay lại khóa học và đăng ký buổi hướng dẫn đáng tin cậy.

- **Đội Trải nghiệm học tập (A):** giao diện, điều hướng bài học, khả năng truy cập.
- **Đội Dịch vụ nền tảng (B):** API đăng ký, phân quyền, tính đúng dữ liệu và xử lý sự cố.

Hai đội dùng story points nhưng tự chọn PBI tham chiếu và định nghĩa độ lớn, không có phép hiệu chuẩn chung.

### 26.2. Lãnh đạo xem dữ liệu bốn Sprint đầu

| Sprint | Velocity A | Velocity B |
|---|---:|---:|
| S1 | 21 | 34 |
| S2 | 24 | 31 |
| S3 | 23 | 35 |
| S4 | 22 | 32 |
| **Tổng** | **90** | **132** |
| **Trung bình** | **22,5** | **33,0** |

Lãnh đạo kết luận:

> “B làm nhanh hơn A vì 33 lớn hơn 22,5. Cả hai đội cần tăng velocity ít nhất 25% trong bốn Sprint tiếp theo.”

Có hai lỗi:

1. **33 và 22,5 không cùng thang điểm có thể so sánh**.
2. **Tăng points** được chọn làm mục tiêu dù chưa nói rõ cần cải thiện outcome, chất lượng hay khả năng dự báo nào.

### 26.3. Điều gì xảy ra sau chỉ tiêu?

Giả sử bốn Sprint kế tiếp:

| Sprint | Velocity A được báo cáo | Velocity B được báo cáo |
|---|---:|---:|
| S5 | 28 | 37 |
| S6 | 29 | 39 |
| S7 | 31 | 42 |
| S8 | 33 | 43 |
| **Tổng** | **121** | **161** |
| **Trung bình** | **30,25** | **40,25** |

~~~text
Đội A:
  Từ 22,5 lên 30,25 points/Sprint.
  Mức tăng = (30,25 - 22,5) / 22,5 × 100%
           ≈ 34,4%.

Đội B:
  Từ 33 lên 40,25 points/Sprint.
  Mức tăng = (40,25 - 33) / 33 × 100%
           ≈ 22,0%.
~~~

Theo bảng points, A “vượt mục tiêu” còn B “chưa đạt”. Nhưng kiểm tra thêm cho thấy:

- Một số hạng mục tương tự ở A được ước lượng điểm cao hơn trước.
- B phải dành thời gian xử lý sự cố đăng ký trùng sau lỗi mạng.
- Có nhiều PBI được chia theo task kỹ thuật để tăng lượng có thể đóng.
- Một số thay đổi tích hợp chỉ hoàn thành khi cả hai đội phối hợp, không nằm gọn trong điểm một đội.

Đây là những **dấu hiệu cần điều tra**, không tự kết luận ai cố tình gian lận.

### 26.4. Bảng dữ liệu cần xem cạnh points

Giả sử dữ liệu giai đoạn A:

| Tín hiệu đội A, hoàn toàn giả định | Bốn Sprint trước | Bốn Sprint sau |
|---|---:|---:|
| Velocity trung bình | 22,5 | 30,25 |
| Số PBI đạt DoD trong kỳ | 22 | 24 |
| Cycle time trung vị (ngày làm việc) | 9 | 12 |
| PBI có lỗi tích hợp phát hiện muộn | 3/22 | 8/24 |
| Tỷ lệ học viên quay lại hoạt động học có ý nghĩa sau bảy ngày | 27% | 27% |
| Giờ làm ngoài ca theo khảo sát có giới hạn | Chưa thu nhất quán | Có phản ánh tăng, cần đo phù hợp |

Các số liệu gợi ý:

- **Points báo cáo tăng nhanh**, nhưng số PBI Done chỉ tăng nhẹ.
- **Cycle time xấu đi** trong mẫu minh họa.
- **Lỗi tích hợp phát hiện muộn tăng** về tỷ lệ, nếu định nghĩa đo nhất quán.
- **Chưa quan sát được cải thiện outcome** trên chỉ số quay lại học.

Phép tính tỷ lệ lỗi:

~~~text
Trước: 3 / 22 × 100% ≈ 13,6%
Sau:   8 / 24 × 100% ≈ 33,3%
Chênh lệch ≈ +19,7 điểm phần trăm.
~~~

**Không thể chứng minh chỉ tiêu velocity gây ra tất cả biến động** bằng hai nhóm số liệu ngắn. Cần xem thay đổi loại PBI, quy tắc đếm lỗi, độ phức tạp và các yếu tố ngoài. Nhưng **cũng không có cơ sở tuyên bố KPI tăng points là thành công** khi các tín hiệu quan trọng trái chiều.

### 26.5. Cuộc đối thoại thay đổi câu hỏi

Người bảo trợ chuyển đổi hỏi:

> “Chúng ta muốn phát triển nhanh hơn hay muốn học viên hoàn thành tác vụ quan trọng sớm và an toàn hơn?”

Product Owner trả lời:

> “Chúng ta cần học viên tìm lại bài đang học và có thể đăng ký/hủy buổi hướng dẫn mà không bị ghi trạng thái sai.”

Developers bổ sung:

> “Thời gian chờ review và bộ test tích hợp không ổn định đang làm các hạng mục dồn cuối Sprint.”

Người kiểm thử cảnh báo:

> “Nếu tiếp tục tính thưởng theo points, chúng tôi có động lực đưa phần kiểm chứng sang Sprint sau.”

Kết luận: thay mục tiêu “velocity +25%” bằng **một thử nghiệm cải tiến flow và chất lượng** được hỗ trợ bởi Product Goal.

### 26.6. Thiết kế thử nghiệm mới

Team thống nhất:

1. **Ngừng sử dụng velocity giữa đội để xếp hạng**; giữ lịch sử từng đội nếu có ích cho forecast.
2. **Giữ nguyên Definition of Done**, bổ sung các test rủi ro đã thiếu và làm rõ trạng thái Done.
3. **Giảm WIP và giới hạn PR lớn**, công khai hàng chờ review.
4. **Làm rõ API contract và acceptance criteria** giữa hai đội trước tích hợp.
5. **Ưu tiên lát giá trị tích hợp** giúp học viên tiếp tục học và đăng ký đúng.
6. **Theo dõi cycle time, blocked time, lỗi tích hợp, lỗi dữ liệu và product outcome**.
7. **Không yêu cầu tăng giờ làm hoặc giảm bảo mật** để đạt số.

### 26.7. Cột mốc đánh giá và trách nhiệm

| Hạng mục | Cách xác định |
|---|---|
| **Owner cải tiến** | Một người do đội thống nhất điều phối thử nghiệm, không phải “người chịu tội” nếu giả thuyết sai. |
| **Người thực hiện** | Developers, người kiểm thử, Product Owner và người phụ trách phụ thuộc liên quan. |
| **Người quyết định thay KPI** | Người có quyền quản trị đánh giá/thưởng và người bảo trợ chương trình. |
| **Đầu ra** | Chính sách review/WIP rõ, contract test có bằng chứng, DoD không đổi theo hướng nới lỏng. |
| **Primary process outcome** | Giảm cycle time và blocked time của lát giá trị tương đương. |
| **Product outcome** | Tỷ lệ học viên quay lại học hoặc hoàn thành tác vụ đăng ký/hủy đúng. |
| **Guardrails** | Lỗi nghiêm trọng, thời gian ngoài giờ, accessibility, security, tải review. |
| **Mốc Check** | Sau cửa sổ đủ work items và đủ thời gian cho outcome trưởng thành. |

### 26.8. Ví dụ kết quả giả định sau khi điều chỉnh

Giả sử ở một giai đoạn tiếp theo:

- Cycle time trung vị giảm từ **12 xuống 8,5 ngày làm việc** ở loại PBI tương đương.
- Tỷ lệ lỗi tích hợp phát hiện muộn giảm từ **8/24 xuống 4/25**.
- Tỷ lệ học viên quay lại học sau bảy ngày có tín hiệu tăng từ **27% lên 30%**, nhưng cohort khác nhau và chưa đủ để khẳng định tác động.
- Velocity của A dao động quanh **23–27 points/Sprint**, thấp hơn đỉnh S8 vì đội quay lại quy ước ước lượng phù hợp.
- Các kiểm soát bảo mật và DoD được thực hiện đầy đủ trong phạm vi kiểm tra.

~~~text
Tỷ lệ lỗi tích hợp muộn:
  8/24 ≈ 33,3%
  4/25 = 16,0%
  Chênh lệch ≈ -17,3 điểm phần trăm.

Outcome học viên:
  30% - 27% = +3 điểm phần trăm.
~~~

Các con số **chỉ minh họa cách đánh giá nhiều chiều**, không chứng minh một phương pháp gây ra toàn bộ thay đổi. Điều đáng chú ý là **points thấp hơn đỉnh không đồng nghĩa đội thất bại**, nếu dòng tạo giá trị và chất lượng có tín hiệu tốt hơn.

### 26.9. Bài học rút ra

- Không dùng points để thưởng/phạt giữa đội hoặc cá nhân.
- Giữ thang ước lượng phục vụ dự báo của chính đội nếu thấy hữu ích.
- Đặt câu hỏi về **giá trị, chất lượng, rủi ro và flow** trước khi yêu cầu tốc độ.
- Xem phản biện của QA và Developers là nguồn dữ liệu để thiết kế guardrails.
- Đo thử nghiệm với giới hạn suy luận và quyền điều chỉnh rõ.

## 27. Tổ chức nên làm gì nếu đã dùng velocity làm KPI?

Thay đổi chỉ số thưởng/phạt là **thay đổi hệ thống động lực và quyền lợi**, không thể giải quyết chỉ bằng một lời nhắc trong Retrospective.

### 27.1. Công khai mục đích sử dụng số liệu hiện tại

Hỏi:

- Velocity đang được dùng để forecast hay đánh giá thành tích?
- Có bị dùng để tính tiền thưởng, xếp loại, giao việc hoặc phân bổ nhân sự?
- Người tạo dữ liệu có biết mục đích đó từ trước không?
- Có trường hợp đội đổi thang hoặc che công việc vì áp lực điểm không?
- Ai có quyền thay chính sách KPI?

### 27.2. Dừng việc dùng sai trước khi thay dashboard

Nếu points đang quyết định thưởng/phạt, cần **người có thẩm quyền quản trị và nhân sự** sửa chính sách công bằng, minh bạch. Chỉ thêm một chỉ số cycle time cạnh velocity mà vẫn phạt đội có velocity thấp **không giải quyết động cơ sai**.

### 27.3. Phân biệt trách nhiệm forecast và đánh giá performance

Có thể giữ hai quy trình riêng:

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| **Dự báo và quản lý rủi ro giao hàng** | Dữ liệu flow/velocity của chính đội theo thời gian, giả định và khoảng bất định. |
| **Đánh giá chất lượng công việc và phát triển con người** | Bằng chứng phù hợp vai trò, kết quả, hợp tác, chất lượng, điều kiện làm việc; quy trình minh bạch, công bằng. |
| **Quản trị sản phẩm** | Product Goal, outcome người dùng, chi phí, rủi ro và quyết định Product Backlog. |
| **Cải tiến hệ thống** | Blocker, WIP, cycle time, lỗi hồi quy và hành động cải tiến đã kiểm chứng. |

### 27.4. Xây lại lòng tin

Nếu đội đã quen **ước lượng cao để bảo vệ mình**, đừng lập tức công khai bảng points mới rồi gọi đó là “số liệu trung thực”. Cần:

- Loại bỏ động cơ gây méo đo lường.
- Giải thích cách dữ liệu mới sẽ và sẽ không được dùng.
- Cho nhóm thống nhất lại cách đo phù hợp.
- Ghi lại ranh giới giữa chuỗi cũ và chuỗi mới.
- Đánh giá hiệu quả dựa trên công việc thực và feedback.

**Khôi phục tính minh bạch cần hành vi quản trị nhất quán**, không chỉ một buổi đào tạo đo lường.

## 28. Khi được hỏi “làm thế nào tăng velocity?”, hãy hỏi mục tiêu thật

Một yêu cầu như “cần tăng velocity 20%” có thể che nhiều mục tiêu khác nhau:

| Ý định thực có thể có | Câu hỏi tốt hơn | Hành động có thể thử |
|---|---|---|
| Muốn người dùng nhận tính năng sớm hơn | Từ ý tưởng tới Increment dùng được mất bao lâu? | Giảm WIP, chia lát giá trị, gỡ blocker. |
| Muốn forecast đáng tin hơn | Dự báo lệch vì mẫu, phụ thuộc hay cách chia việc? | Dùng phân phối flow và giới hạn bất định. |
| Muốn giảm chi phí | Chi phí nào đang phát sinh do chờ, lỗi hoặc làm lại? | Cải thiện CI, kiểm thử và quyết định sớm. |
| Muốn giao nhiều giá trị hơn | Outcome sản phẩm nào chưa cải thiện? | Ưu tiên giả thuyết giá trị, thu phản hồi sớm. |
| Muốn tăng chất lượng | Lỗi nào lọt qua kiểm chứng? | DoD, TDD/contract tests, review theo rủi ro. |
| Muốn bảo đảm trách nhiệm | Quyền quyết định và thông tin nào thiếu minh bạch? | Làm rõ owner, governance và các mốc review. |
| Muốn hỗ trợ đội kém hiệu quả | Hàng chờ, thiếu năng lực, phụ thuộc nào gây chậm? | Quan sát, huấn luyện và cấp nguồn lực phù hợp. |

### 28.1. Tránh đối thoại chỉ mang tính phủ nhận

Phản hồi “Velocity không quan trọng, đừng hỏi nữa” có thể làm người quản lý cảm thấy nhu cầu quản trị bị gạt bỏ.

Phản hồi tốt:

> “Velocity có thể giúp team tự forecast nhưng không dùng để so đội. Nếu mục tiêu là giao phần giá trị nhanh hơn, ta cùng xem cycle time, WIP, chất lượng và outcome người dùng; sau đó thử cải tiến có điều kiện.”

Nó **giữ lại nhu cầu thật** và thay phép đo không phù hợp.

### 28.2. Đừng hứa tất cả chỉ số đều tăng

Giảm WIP có thể giảm cycle time nhưng throughput chưa chắc tăng ngay. Thêm kiểm thử có thể làm tăng thời gian ở giai đoạn đầu nhưng giảm lỗi dài hạn. Đầu tư accessibility có thể chưa tác động trực tiếp tới tỷ lệ quay lại học của toàn bộ người dùng.

**Đánh giá trade-off theo mục tiêu và guardrails**, không đòi mọi đường biểu đồ đều đi lên.

## 29. Mẫu đối thoại khi lãnh đạo muốn xếp hạng các Scrum Team

### Tình huống minh họa

**Người quản lý:** “Tôi thấy nhóm A 50 points, nhóm B 28. Tôi muốn nhóm B học cách A tăng năng suất.”

**Scrum Master:** “Chúng ta muốn cải thiện năng lực giao giá trị và dự báo của B, đúng không? Hai nhóm có thang story points và loại việc khác nhau, nên 50 và 28 không đủ để xếp hạng.”

**Người quản lý:** “Nhưng tôi cần biết có nên đầu tư thêm người vào B không.”

**Scrum Master:** “Đó là câu hỏi hợp lý. Ta có thể xem backlog và các phụ thuộc của B: work item age, cycle time, việc chờ review/kiểm thử, sự cố không dự báo và outcome sản phẩm. Nếu nút thắt là môi trường thử, thêm Developers có thể không giải quyết được.”

**Product Owner:** “Tôi muốn ưu tiên lỗi tiến độ học viên bị ghi sai; nó có thể ít points nhưng ảnh hưởng lớn.”

**Người quản lý:** “Vậy ta đo gì để biết cải tiến?”

**Scrum Master:** “Chọn một giả thuyết: nếu xử lý môi trường kiểm thử và giảm WIP review, thời gian tới Increment dùng được sẽ giảm. Ta theo dõi cycle time cùng lỗi hồi quy, thời gian ngoài giờ và trải nghiệm học viên. Dữ liệu velocity có thể tiếp tục hỗ trợ B lập Sprint Planning của chính B.”

**Người quản lý:** “Sau bao lâu có thể quyết định?”

**Scrum Master:** “Sau một cửa sổ đủ hạng mục và đủ quan sát guardrails. Ta ghi ngày Check và điều kiện dừng trước khi thử; không dùng số points báo cáo làm bằng chứng duy nhất.”

**Bài học:** không phủ nhận nhu cầu giải trình nguồn lực, nhưng **đổi đối tượng so sánh từ điểm quy ước sang điều kiện dòng công việc, rủi ro và kết quả**.

## 30. Thiết kế một thí nghiệm cải tiến thay cho chỉ tiêu points tăng

Một action card cải tiến nên đủ cụ thể để quyết định **thử, đo, giữ hoặc dừng**.

~~~yaml
improvement_id: "FLOW-VELOCITY-01"
problem: "PBI chờ review và tích hợp lâu, trong khi điểm Done bị dùng làm KPI"
value_goal: "Giao lát giá trị đáng tin sớm hơn cho học viên"
hypothesis: >
  Giảm WIP review, làm rõ next actor và tăng kiểm chứng tích hợp sớm
  có thể giảm cycle time mà không làm tăng lỗi hoặc tải ngoài giờ.
scope: "Một luồng user story của một đội, trong giai đoạn thử có giới hạn"
owner: "Người điều phối được đội thống nhất"
executors:
  - "Developers"
  - "Người có góc nhìn kiểm thử"
  - "Người gỡ phụ thuộc review/CI"
decision_maker: "Người có quyền điều chỉnh quy trình/KPI và nguồn lực"
baseline: "Cycle time, blocked time, lỗi hậu tích hợp và tải review"
primary_metric: "Median cycle time của PBI tương đương"
supporting_metrics:
  - "Work item age và thời gian chờ review"
  - "Throughput theo loại việc"
  - "Thời gian tới phản hồi người dùng có thể hành động"
guardrails:
  - "Không bỏ Definition of Done"
  - "Không tăng lỗi dữ liệu/phân quyền nghiêm trọng"
  - "Không tăng làm ngoài giờ thường xuyên"
  - "Không sử dụng velocity để xếp hạng cá nhân/đội"
trial_window: "Đủ hạng mục và thời gian phù hợp, xác định trước"
check: "Xem kết quả, bối cảnh, tác dụng phụ và quyết định"
decision_options: "Duy trì / Điều chỉnh / Thu thêm dữ liệu / Dừng"
~~~

Mẫu này chỉ là **ví dụ trình bày**, không phải cấu hình bắt buộc của Scrum/Kanban hoặc metadata của hệ thống học tập.

### 30.1. Owner không phải người bị phạt khi giả thuyết sai

Owner bảo đảm **thí nghiệm được thực hiện và kết quả được xem lại trung thực**. Một giả thuyết bị bác bỏ có thể là bài học giá trị; không nên biến thử nghiệm thành cách tìm người chịu lỗi.

### 30.2. Có thể bắt đầu rất nhỏ

Ví dụ thử hai tuần trên một loại PR:

- Khi đưa PR vào review, phải có mô tả mục tiêu, test và người nhận.
- Giới hạn số PR lớn đang chờ.
- Dành khoảng tập trung review phù hợp lịch làm việc.
- Theo dõi thời gian tới phản hồi có ý nghĩa và lỗi sau review.

Nếu giảm chờ mà chất lượng không suy giảm, cân nhắc duy trì; nếu reviewer bị quá tải hoặc rủi ro cao bị bỏ qua, phải sửa chính sách.

### 30.3. Đổi định nghĩa đo phải được ghi

Nếu team thay quy tắc “đủ điều kiện review” hay điểm kết thúc cycle time, cần ghi lại phiên bản định nghĩa. Không so hai kỳ như hoàn toàn tương đương khi **phạm vi đo đã thay đổi**.

## 31. Sơ đồ quyết định: khi velocity giảm hoặc bị yêu cầu tăng

~~~mermaid
flowchart TD
    A["Velocity thay đổi hoặc có yêu cầu tăng điểm"] --> B{"Đang muốn quyết định điều gì?"}
    B -->|Lập kế hoạch Sprint| C["Dùng lịch sử của chính đội, năng lực và Sprint Goal"]
    B -->|Dự báo giao hàng| D["Xem phân phối flow, phạm vi backlog và phụ thuộc"]
    B -->|Cải thiện giá trị| E["Xác định Product Goal, outcome và guardrails"]
    B -->|Xếp hạng đội/cá nhân| F["Dừng suy luận từ points; làm rõ mục đích quản trị"]
    C --> G["Kiểm tra thay đổi DoD, cách ước lượng và nguồn lực"]
    D --> G
    E --> H["Chọn nút thắt và giả thuyết có thể thử"]
    F --> H
    G --> H
    H --> I["Thử thay đổi nhỏ, đo flow và chất lượng"]
    I --> J{"Bằng chứng có đủ và guardrails ổn?"}
    J -->|Có| K["Duy trì có điều kiện và theo dõi outcome"]
    J -->|Chưa rõ| L["Điều tra/thu thêm dữ liệu"]
    J -->|Không| M["Điều chỉnh hoặc dừng thử nghiệm"]
    L --> H
    M --> H
~~~

Sơ đồ không nói mọi trường hợp velocity giảm phải tổ chức một dự án cải tiến. Nếu đội đã biết một thành viên nghỉ phép hoặc có sự cố nghiêm trọng, **ghi nhận bối cảnh và điều chỉnh kế hoạch** có thể đủ. Chỉ mở thí nghiệm khi có vấn đề đáng giải quyết và cách kiểm chứng phù hợp.

## 32. Bài tập 1 — Tính velocity đúng khi có PBI chưa Done

Một đội Scrum chọn các PBI trong Sprint:

| PBI | Points được ước lượng | Trạng thái cuối Sprint |
|---|---:|---|
| Khôi phục bài gần nhất | 5 | Done theo DoD |
| Thông báo khi mất kết nối | 3 | Done theo DoD |
| Điều chỉnh tiến độ đa thiết bị | 8 | Done theo DoD |
| Gợi ý bài tiếp theo | 13 | Chưa hoàn thành kiểm thử tích hợp |
| Sửa lỗi hiển thị trên trình duyệt cũ | 2 | Đã viết mã nhưng thiếu kiểm chứng bắt buộc |

**Câu hỏi:** velocity minh họa của Sprint là bao nhiêu?

**Đáp án:**

~~~text
Velocity = 5 + 3 + 8 = 16 points.

13 points chưa đạt DoD => 0 points Done trong Sprint này.
2 points chưa đạt DoD  => 0 points Done trong Sprint này.
~~~

Không nên cộng 50% hoặc 90% ước lượng cho PBI chưa Done. Nếu PBI tiếp tục sang Sprint sau, đội theo dõi trạng thái và quy ước tính **khi đạt DoD**, không cộng trùng qua nhiều Sprint.

### 32.1. Câu hỏi mở rộng

Nếu một PBI 13 points được tách thành hai lát giá trị độc lập và được ước lượng lại thành 5 và 8 points, trong đó chỉ lát 5 points đạt DoD, điều gì cần ghi?

**Gợi ý:** làm rõ **lát nào đã cung cấp khả năng dùng được**, thông tin còn thiếu của lát kia, và quy ước ước lượng trước–sau. Việc tách phải vì giá trị/phản hồi và quản lý rủi ro, không phải để “đóng tạm 5 points” khi sản phẩm chưa đạt phần định nghĩa Done.

## 33. Bài tập 2 — Vì sao hai team không thể xếp hạng bằng points?

Giả sử:

- Đội A có sáu Developers; velocity trung bình 42 points/Sprint.
- Đội B có ba Developers; velocity trung bình 27 points/Sprint.
- A làm giao diện học viên; B xử lý hệ thống thanh toán và phân quyền.
- Hai đội ước lượng tương đối theo các PBI tham chiếu riêng.
- B có nhiều ca trực sự cố và kiểm chứng dữ liệu bắt buộc.

**Câu hỏi 1:** A có năng suất cao hơn vì 42 lớn hơn 27?

**Đáp án:** không thể kết luận. Points không chung đơn vị; loại công việc, năng lực, phụ thuộc và DoD theo rủi ro khác nhau.

**Câu hỏi 2:** chia cho số Developers thì có kết luận được?

~~~text
Đội A: 42 / 6 = 7 points/người/Sprint
Đội B: 27 / 3 = 9 points/người/Sprint
~~~

**Đáp án:** vẫn không. Hai tỷ lệ **không có đơn vị chuẩn tương đương**, và chúng bỏ qua hợp tác, review, kiểm thử, vận hành và giá trị. Không được dùng để tuyên bố B hơn A khoảng 28,6%.

**Câu hỏi 3:** cần gì để quyết định hỗ trợ đội B?

**Gợi ý:** xem mục tiêu giá trị của B, thời gian chờ review/đối tác, work item age, rủi ro chất lượng, năng lực trực sự cố, các nghĩa vụ không thể trì hoãn và nguồn lực thiếu thực. Có thể thấy nút thắt là quyền truy cập môi trường thử, **không phải số Developers**.

## 34. Bài tập 3 — Phân biệt số tăng thực và point inflation

Một đội đã ước lượng ba PBI tương đương theo quy ước cũ:

| PBI | Trước KPI | Sau khi thưởng theo points |
|---|---:|---:|
| Form điều chỉnh tiến độ | 3 | 5 |
| Thêm validation | 5 | 8 |
| Xử lý lỗi mạng | 8 | 13 |
| **Tổng** | **16** | **26** |

**Câu hỏi:** tổ chức có được báo “đội tăng năng suất 62,5%” không?

**Đáp án:** không. Tổng points tăng **62,5%** đúng về số học, nhưng ở ví dụ này nội dung công việc không đổi; thang ước lượng có thể đã phình lên. Cần xem time to Done, chất lượng, output tích hợp và outcome.

**Câu hỏi mở rộng:** nếu một đội thực sự cải thiện CI và có thể hoàn thành nhiều lát giá trị hơn trong cùng thời gian, có được nói velocity tăng không?

**Đáp án:** có thể mô tả **velocity lịch sử của chính đội tăng** khi cách đo và phạm vi so sánh ổn định; đó là tín hiệu cần được kiểm tra cùng dữ liệu khác. Không được tự kết luận sản phẩm tạo ra nhiều giá trị hơn đúng bằng tỷ lệ tăng points.

## 35. Bài tập 4 — Dự báo theo dữ liệu thay vì một điểm target

Một đội có velocity năm Sprint: **21, 27, 24, 20, 28 points**.

**Câu hỏi 1:** trung bình và trung vị?

~~~text
Mean   = (21 + 27 + 24 + 20 + 28) / 5 = 24
Median = 24
Min    = 20
Max    = 28
~~~

**Câu hỏi 2:** Product Backlog có 73 points cùng cách ước lượng. Có thể hứa xong sau 3 Sprint không?

**Gợi ý:** không đủ cơ sở hứa chắc. Chia theo mean ra **73/24 ≈ 3,04 Sprint**, nhưng thực tế phụ thuộc hạng mục, giới hạn DoD, sự cố và điều kiện. Có thể nói khoảng sơ bộ **3–4 Sprint nếu điều kiện tương tự** và cập nhật theo mỗi Sprint; đây không phải khoảng xác suất được kiểm chứng.

**Câu hỏi 3:** nếu Sprint tới có nhiều người nghỉ phép?

**Gợi ý:** xem lại capacity và kế hoạch; không ép đội tăng points để giữ một forecast không còn giả định đúng.

**Câu hỏi 4:** nếu backlog thay đổi theo phản hồi người dùng?

**Gợi ý:** dự báo lại **phạm vi còn giá trị**, không coi việc bỏ PBI vì giả thuyết sai là đã sản xuất thêm points.

## 36. Bài tập 5 — Thiết kế scorecard chống tối ưu một chiều

**Tình huống:** một lãnh đạo muốn “tăng tốc độ giao tính năng” trong nền tảng học, nhưng gần đây lỗi lưu tiến độ tăng.

Hãy đề xuất ba lớp phép đo:

| Lớp | Gợi ý câu trả lời |
|---|---|
| **Flow outcome** | Cycle time từ bắt đầu tới Done, blocked time và work item age của PBI tương đương. |
| **Product outcome** | Tỷ lệ học viên hoàn tất đúng hoạt động học có ý nghĩa; thời gian tìm lại bài đã học. |
| **Quality/human guardrails** | Lỗi mất tiến độ, lỗi phân quyền, tỷ lệ kiểm chứng đạt DoD và giờ làm ngoài ca. |

**Câu hỏi phụ:** nếu cycle time giảm từ 12 xuống 8 ngày làm việc, nhưng lỗi mất tiến độ tăng, có thể kết luận chuyển đổi thành công?

**Gợi ý:** không. Cần điều tra chất lượng, dừng/điều chỉnh phần thử gây hại và giữ tiêu chuẩn bắt buộc. **Tốc độ chỉ có ích khi phần giá trị được giao đúng và an toàn**.

### 36.1. Phép đo về giá trị không thay nhiệm vụ lắng nghe

Nếu tỷ lệ học viên quay lại tăng, vẫn cần xem:

- Người dùng nào hưởng lợi, nhóm nào gặp khó?
- Có chiến dịch hoặc thay đổi nội dung gây biến động?
- Có vấn đề accessibility hoặc riêng tư chưa được đo?
- Kết quả có duy trì sau một cửa sổ hợp lý?

Một chỉ số outcome **không miễn trừ yêu cầu hiểu người dùng**.

## 37. Bảng phản mẫu và cách sửa

| Phản mẫu | Biểu hiện | Cách xử lý phù hợp |
|---|---|---|
| **Velocity phải tăng 10–20% mỗi Sprint.** | Target tăng theo cấp số nhân bất kể năng lực. | Dùng velocity cục bộ để forecast, xác định nút thắt và outcome cần cải thiện. |
| **Đội nào nhiều points hơn thì giỏi hơn.** | Xếp hạng A/B bằng điểm tuyệt đối. | Không so thang điểm riêng; xem giá trị, flow và rủi ro trong bối cảnh. |
| **Points/người là năng suất.** | Chia velocity cho headcount để thưởng/phạt. | Không cá nhân hóa points; đánh giá đóng góp phù hợp vai trò và hợp tác. |
| **Story point là giờ/người.** | Quy đổi 1 point = 4 giờ cho mọi đội. | Phân biệt ước lượng tương đối và capacity/time. |
| **Scrum bắt buộc dùng Planning Poker.** | Xem không có points là “không chuẩn Scrum”. | Scrum Guide không yêu cầu story points hay velocity. |
| **Sprint Goal là đạt đúng N points.** | Chọn ticket dễ để lấp quota. | Đặt mục tiêu giá trị và Increment dùng được. |
| **Chỉ số tăng nghĩa là outcome tăng.** | Báo ROI từ points. | Đo hành vi người dùng, chất lượng và chi phí phù hợp. |
| **Cộng điểm qua các đội.** | “Velocity chương trình = 80” từ các thang khác. | Dự báo lát tích hợp và phụ thuộc với dữ liệu flow tương ứng. |
| **Ước lượng lại cuối Sprint để báo điểm cao.** | Sửa lịch sử sau khi biết công thực. | Giữ lịch sử, minh bạch thay đổi ước lượng và mục đích. |
| **Cộng điểm hạng mục gần Done.** | “Đã 80%, ghi 80% points.” | Chỉ tính PBI đạt DoD theo chính sách. |
| **Chia task kỹ thuật chỉ để tăng points.** | DTO, controller, test là các “story” cộng điểm. | Chia theo lát giá trị và khả năng kiểm chứng. |
| **Giữ WIP cao để mọi người bận.** | Hàng chờ review dài, ít Increment dùng được. | Giới hạn WIP, hỗ trợ hoàn thành và gỡ blocker. |
| **Dời kiểm thử sang Sprint sau.** | Velocity tăng, DoD giảm. | Giữ Definition of Done và chất lượng tích hợp. |
| **Che sự cố để bảo vệ KPI.** | Việc khẩn không được ghi nhận. | Minh bạch công việc không dự báo và ưu tiên theo rủi ro. |
| **Không đầu tư CI/refactoring vì ít points.** | Nợ kỹ thuật và lỗi tích hợp tăng. | Xem năng lực thay đổi, lỗi và tác động dài hạn. |
| **Biến throughput thành quota mới.** | Chia ticket thật nhỏ để đóng nhiều. | Dùng throughput như dữ liệu flow, cùng DoD và loại việc. |
| **Dùng cycle time để phạt cá nhân.** | Người tránh nhận item khó. | Phân tích hệ thống, rủi ro, phân phối và blocker. |
| **Một Sprint thấp là đội yếu.** | Chỉ nhìn điểm cuối kỳ. | Xem bối cảnh, biến động, DoD và outcome. |
| **Giấu thay đổi thang ước lượng.** | Đồ thị tăng sau khi tăng điểm PBI. | Ghi mốc, lý do và giới hạn so sánh. |
| **Lấy forecast làm bảo đảm.** | 73/24 = “chắc chắn đúng 3 Sprint”. | Báo phạm vi điều kiện và cập nhật theo dữ liệu mới. |
| **Coi SLE là SLA bắt buộc.** | Dự báo percentile bị dùng như cam kết hợp đồng. | Phân biệt kỳ vọng flow và nghĩa vụ được thỏa thuận. |
| **Đánh giá mọi đội bằng một scorecard cứng.** | Bỏ qua loại sản phẩm, rủi ro và nhiệm vụ. | Chọn metric từ Product Goal, outcome và bối cảnh. |
| **Chỉ báo số thành công.** | Dashboard đẹp nhưng lỗi/rework không được xem. | Báo cả guardrails, độ không chắc và kết quả trái chiều. |
| **Ép tăng points bằng làm thêm giờ.** | Kiệt sức, lỗi và tải trực tăng. | Bảo vệ nhịp bền vững, xem capacity và phụ thuộc. |
| **Đào tạo story point thay vì sửa KPI thưởng.** | Động cơ xấu vẫn tồn tại. | Thay chính sách dùng số liệu ở đúng cấp quản trị. |

## 38. Checklist cho Scrum Team trước khi dùng velocity

### Mục đích và phạm vi

- [ ] Đội có xác định velocity nhằm **hỗ trợ forecast cục bộ**, không phải xếp hạng?
- [ ] Cách ước lượng và PBI tham chiếu được đội hiểu?
- [ ] Đội biết Scrum **không bắt buộc** story points hoặc velocity?
- [ ] Dữ liệu được dùng để hỗ trợ Sprint Goal và Product Goal, không thay thế chúng?
- [ ] Ai sẽ xem dữ liệu và dùng nó ra quyết định gì đã rõ?

### Tính đúng của cách ghi

- [ ] Chỉ PBI đạt Definition of Done mới được tính Done theo chính sách?
- [ ] Không cộng points hạng mục đang dở hoặc tính trùng qua Sprint?
- [ ] Mọi thay đổi DoD, thang ước lượng, cách chia PBI được ghi lại?
- [ ] Có phân biệt PBI bị hủy do ưu tiên thay đổi với PBI đã giao?
- [ ] Công việc sự cố, bảo mật, mentoring và chất lượng vẫn được nhìn thấy?

### Dự báo

- [ ] Xem nhiều Sprint thay vì một điểm dữ liệu bất thường?
- [ ] Có cân nhắc nghỉ phép, công việc không dự báo, phụ thuộc và môi trường?
- [ ] Forecast được truyền đạt như **kịch bản có điều kiện**, không ngày chắc chắn giả?
- [ ] Nếu backlog thay đổi, có cập nhật forecast thay vì bảo vệ con số cũ?
- [ ] Nếu dữ liệu lịch sử yếu, đã cân nhắc throughput/cycle time hoặc thu thêm dữ liệu?

### Guardrails và hệ quả

- [ ] Velocity không dùng để thưởng/phạt, xếp hạng đội hoặc cá nhân?
- [ ] Không ép tăng points bằng giảm DoD hoặc làm thêm giờ?
- [ ] Có xem lỗi hồi quy, bảo mật, accessibility và độ ổn định vận hành?
- [ ] Có xem WIP, blocked time, work item age và cycle time khi phù hợp?
- [ ] Có liên hệ cải tiến với outcome người dùng, không chỉ output?
- [ ] Đội có thể nêu kết quả xấu và bất định mà không bị trừng phạt?

## 39. Checklist cho người quản lý và Product Owner khi xem báo cáo Agile

### Khi thấy hai đội có points khác nhau

- [ ] Có tránh kết luận đội nhiều points hơn tạo nhiều giá trị hoặc năng suất hơn?
- [ ] Đã kiểm tra hai đội có cùng mục tiêu, loại công việc và DoD theo rủi ro không?
- [ ] Có hỏi các hàng chờ, phụ thuộc và năng lực thực trước khi phân bổ nhân sự?
- [ ] Có ưu tiên chia sẻ thực hành tạo hiệu quả thay vì xếp hạng?
- [ ] Có xem mục tiêu sản phẩm và Increment tích hợp xuyên đội?

### Khi thấy velocity giảm

- [ ] Có hỏi bối cảnh, biến động năng lực và độ tin cậy dữ liệu?
- [ ] Có phân biệt một Sprint bất thường với xu hướng dài hơn?
- [ ] Có xem những việc quan trọng không được gán points?
- [ ] Có giữ quyền phản biện và khả năng kiểm tra nguyên nhân?
- [ ] Có tránh yêu cầu đổi điểm hoặc mở thêm việc chỉ để giữ đồ thị?

### Khi muốn cải thiện delivery

- [ ] Mục tiêu được phát biểu bằng **giá trị, chất lượng, thời gian phản hồi hoặc dự báo**?
- [ ] Đã xác định ràng buộc cần tuân thủ như hợp đồng và an toàn?
- [ ] Có thí nghiệm nhỏ với baseline, owner, phép đo, guardrails và mốc Check?
- [ ] Có người có quyền gỡ blocker ở cấp liên đội hoặc governance?
- [ ] Có thể **sửa/dừng cách thử** nếu dữ liệu không ủng hộ?
- [ ] KPI nhân sự hoặc chính sách tài chính có đang vô tình khuyến khích tăng điểm giả?

Checklist không phải mẫu kiểm toán bắt buộc. Mục tiêu là dùng số liệu để **ra quyết định tốt và giữ tính minh bạch**, không thêm một nghi thức báo cáo.

## 40. Câu hỏi thường gặp

### 40.1. Có nên bỏ hoàn toàn story points?

**Không có yêu cầu chung phải bỏ hay phải giữ.** Nếu đội thấy ước lượng tương đối giúp thảo luận bất định và forecast hữu ích với chi phí hợp lý, có thể tiếp tục. Nếu nó tạo nhiều nghi thức, bị dùng để phạt hoặc dữ liệu throughput/cycle time đã đủ, đội có thể thử phương án khác.

### 40.2. Velocity tăng có thể là dấu hiệu tốt không?

**Có thể**, nếu cách đo không đổi, năng lực và dòng công việc thực sự cải thiện; nhưng phải xem chất lượng, WIP, rủi ro và outcome để tránh kết luận sai. Tăng points tự nó **không phải mục tiêu cuối**.

### 40.3. Velocity ổn định có phải đội không cải tiến?

**Không.** Đội có thể tăng chất lượng, giảm lỗi hoặc tạo outcome người dùng tốt hơn với lượng points tương tự. Đội cũng có thể chuyển sang PBI bất định hơn. Cần xem hệ thống và mục tiêu giá trị.

### 40.4. Có thể dùng story points để xác định giá dự án không?

Một doanh nghiệp có thể sử dụng dữ liệu lịch sử để **hỗ trợ forecast chi phí năng lực** trong điều kiện phù hợp. Nhưng không có tỷ giá “một story point bằng X đồng” dùng được giữa mọi đội; phải phân biệt thang ước lượng cục bộ, chi phí thực tế, hợp đồng, rủi ro và bất định.

### 40.5. Nếu Product Owner muốn nhiều PBI hơn trong một Sprint thì sao?

Hãy cùng xem Sprint Goal, năng lực thực, Definition of Done và giá trị. Có thể **chia lát nhỏ, làm rõ điều kiện và gỡ blocker**, nhưng không dùng áp lực bỏ test hoặc tăng point ước lượng để giả vờ có thêm năng lực.

### 40.6. Nếu hai đội cùng ước lượng một backlog thì có so points được không?

Có thể thảo luận ước lượng để **phối hợp và chia sẻ hiểu biết**, nhưng việc áp cùng tên points chưa chứng minh các đội có cùng thang và điều kiện. So sánh trực tiếp như KPI năng suất vẫn thiếu cơ sở; cần xem loại việc, phụ thuộc, tiêu chuẩn chất lượng và outcome.

### 40.7. Vì sao không chỉ dùng cycle time thay velocity?

Cycle time trả lời **thời gian một hạng mục đi qua hệ thống**, không trực tiếp cho biết giá trị người dùng, chất lượng hoặc độ khó công việc. Nó cũng có thể bị chơi số nếu team chia ticket khác đi. Nên chọn **bộ tín hiệu nhỏ phù hợp mục tiêu**, không tìm một KPI duy nhất thay thế tất cả.

### 40.8. Một PBI khẩn không có points có nên được ghi nhận?

**Có, công việc và ảnh hưởng tới năng lực phải minh bạch**. Đội có thể dùng loại work item/sự cố riêng, xem tác động tới Sprint Goal, flow và chất lượng. Không cần bịa points chỉ để nó xuất hiện trong bảng thành tích.

### 40.9. Có nên thưởng cho đội giao sản phẩm sớm?

Chính sách thưởng phải được thiết kế có trách nhiệm theo quy định và quyền thực. Nếu gắn thưởng với **một chỉ số tốc độ đơn lẻ**, tổ chức có thể tạo động cơ giảm chất lượng, giấu lỗi hoặc gây quá tải. Cần xem outcome, hợp tác, an toàn, tính công bằng và những điều nằm trong quyền kiểm soát của đội; không suy ra chính sách thưởng chỉ từ velocity.

### 40.10. Làm sao nói với stakeholder rằng forecast không chắc chắn?

Giải thích **giả định, khoảng hoặc kịch bản, yếu tố rủi ro, mốc cập nhật và các lựa chọn khi phạm vi đổi**. Minh bạch bất định không phải thiếu trách nhiệm; nó giúp người quyết định biết khi nào cần điều chỉnh ưu tiên và nguồn lực.

## 41. Kết luận

**Ép velocity tăng liên tục hoặc so sánh story points giữa các nhóm** là sai lầm vì biến một **quy ước ước lượng cục bộ** thành thước đo năng suất và giá trị chung mà nó không được thiết kế để đại diện. Hậu quả có thể là point inflation, chia việc hình thức, Work In Progress tăng, chất lượng bị đẩy ra sau, giảm hợp tác và mất khả năng nói thật về tiến độ.

Velocity có thể hữu ích **để đội tự dự báo trong bối cảnh ổn định**, không phải lời hứa điểm mỗi Sprint hay bảng xếp hạng con người. Những câu hỏi về giao hàng và cải tiến cần thêm **throughput, cycle time, work item age, blocked time, chất lượng, khả năng vận hành và outcome người dùng**, cùng cách đọc dữ liệu có giới hạn và guardrails phù hợp.

Trong **AGILE_DEVELOPMENT**, user story và Product Backlog giúp lựa chọn điều có giá trị; Scrum hướng tới Sprint Goal và Increment đạt Definition of Done; Kanban giúp minh bạch dòng công việc; XP giúp phản hồi kỹ thuật sớm và thay đổi an toàn. Khi số liệu phục vụ **học hỏi, dự báo và quyết định thay vì thưởng/phạt điểm**, nhóm có thể cải thiện khả năng giao giá trị thực mà không phải chạy đua tăng một con số không có ý nghĩa chung giữa các đội.
