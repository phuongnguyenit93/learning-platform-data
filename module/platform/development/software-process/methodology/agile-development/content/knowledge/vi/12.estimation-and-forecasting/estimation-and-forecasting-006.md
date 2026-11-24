# Ước lượng và dự báo: Phân biệt vận tốc nhóm với năng suất và giá trị tạo ra

Một nhóm Scrum vừa hoàn thành 30 story points trong Sprint, cao hơn 20 points ở Sprint trước. Người quản lý vui mừng kết luận: “Năng suất tăng 50%, sản phẩm chắc chắn tạo ra nhiều giá trị hơn”. Kết luận ấy nghe hợp lý nhưng **chưa có đủ bằng chứng**. Điểm ước lượng có thể thay đổi theo cách chia story, những chức năng hoàn tất có thể chưa được khách hàng sử dụng, hoặc Sprint trước đã dành nhiều thời gian xử lý sự cố. Trong Agile, cần phân biệt **vận tốc hoàn tất công việc đã ước lượng**, **khả năng làm việc hiệu quả** và **kết quả có ích mà người dùng nhận được**.

Trong mô-đun **AGILE_DEVELOPMENT**, nhóm học cách phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục bằng user story, Product Backlog, Scrum, Kanban, XP và các chỉ số dòng công việc. **Velocity (vận tốc nhóm)** có thể giúp một nhóm dùng story points dự báo ngắn hạn, nhưng nó không phải thước đo trực tiếp cho năng suất con người, chất lượng hay giá trị sản phẩm. Muốn đưa ra quyết định đúng, nhóm phải kết hợp dữ liệu hoàn tất công việc với phản hồi người dùng, chất lượng và bối cảnh thực hiện.

Bài học này tập trung vào cách **định nghĩa, đọc, sử dụng và không lạm dụng velocity**; đồng thời đưa ra cách so sánh với throughput, cycle time, outcome và những cách dự báo có nêu rõ bất định.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích velocity là gì, cách tính trong một nhóm dùng story points, khi nào số liệu có ý nghĩa.
2. Phân biệt **velocity**, **throughput**, **năng suất/hiệu quả**, **đầu ra**, **kết quả người dùng** và **giá trị kinh doanh**.
3. Tính velocity từ dữ liệu Sprint và nhận ra vì sao story chưa đạt Definition of Done không được tính là phần hoàn tất.
4. Giải thích tại sao không nên dùng story points hoặc velocity để so sánh cá nhân, nhóm hay đặt thưởng phạt.
5. Xây dựng dự báo dựa trên dữ liệu lịch sử, phạm vi công việc và thay đổi năng lực; diễn đạt thành **khoảng hoặc kịch bản** thay vì hứa một ngày chắc chắn.
6. Chọn tín hiệu về giá trị và chất lượng để kiểm tra liệu việc hoàn thành nhiều công việc hơn có thực sự đem lại lợi ích.
7. Ứng dụng tư duy thực nghiệm vào kế hoạch Scrum, luồng Kanban và các thực hành XP để cải thiện khả năng giao sản phẩm bền vững.

## 2. Định nghĩa velocity đúng phạm vi

### 2.1. Velocity đo điều gì?

Trong một nhóm **ước lượng Product Backlog items bằng story points**, velocity của một Sprint thường được tính là:

> **Velocity Sprint = tổng story points của các hạng mục được hoàn tất theo Definition of Done trong Sprint đó.**

Nếu nhóm hoàn tất ba story lần lượt được ước lượng **3**, **5** và **8** points, velocity của Sprint là:

~~~text
Velocity = 3 + 5 + 8 = 16 story points
~~~

Điểm số được dùng như **đơn vị tương đối do nhóm thống nhất**, không phải số giờ lao động. Nhóm có thể cân nhắc mức phức tạp, lượng công việc và bất định khi ước lượng; cách cân nhắc cụ thể cần thống nhất trong nhóm. Velocity cho biết **bao nhiêu điểm của công việc đã đạt chuẩn hoàn tất trong một Sprint**, chứ không cho biết người dùng đã hài lòng hay chưa.

**Lưu ý về Scrum:** Scrum Guide không bắt buộc sử dụng story points, velocity hoặc một kỹ thuật ước lượng cụ thể. Velocity là công cụ tùy chọn thường thấy ở các nhóm Scrum, không phải một trong các trách nhiệm hay hiện vật bắt buộc của Scrum.

### 2.2. Các điều kiện để số velocity có thể đọc được

- **Cùng một nhóm và cách ước lượng tương đối ổn định:** khi thay đổi thang điểm hoặc quy ước, không thể so sánh máy móc với giai đoạn trước.
- **Cùng độ dài Sprint hoặc được diễn giải theo độ dài:** Sprint một tuần không nên đặt cạnh Sprint ba tuần như thể cơ hội hoàn tất bằng nhau.
- **Cùng tiêu chuẩn hoàn tất:** hạng mục chỉ được tính khi đáp ứng Definition of Done (DoD), không phải chỉ khi lập trình xong.
- **Phạm vi điểm được nhất quán:** không tùy tiện cộng điểm của task kỹ thuật chưa hoàn tất hoặc các mục phát sinh được gán điểm hồi tố chỉ để tăng velocity.
- **Đã biết năng lực thực tế của giai đoạn:** nghỉ phép, hỗ trợ vận hành, gián đoạn hoặc thay đổi thành viên có thể làm số điểm hoàn tất dao động.
- **Dữ liệu được dùng để học và dự báo:** không biến nó thành chỉ tiêu thưởng phạt, nếu không hành vi ước lượng có thể bị bóp méo.

Khi các điều kiện thay đổi, velocity vẫn là một **dấu vết lịch sử**, nhưng khả năng dự báo của nó có thể giảm. Không nên sửa lại điểm đã hoàn tất chỉ để biểu đồ có xu hướng tăng.

### 2.3. Story chưa xong được xử lý ra sao?

Giả sử Sprint có các story:

| Hạng mục | Điểm ước lượng | Trạng thái cuối Sprint | Điểm đưa vào velocity |
| --- | ---: | --- | ---: |
| Đăng ký workshop và nhận kết quả | 5 | Đạt DoD | 5 |
| Xem trạng thái đăng ký | 3 | Đạt DoD | 3 |
| Hủy đăng ký đúng chính sách | 8 | Đang kiểm thử, chưa đạt DoD | 0 |
| Sửa lỗi hiển thị ngày | 2 | Đạt DoD | 2 |
| Báo cáo thống kê | 5 | Mới viết mã, chưa tích hợp | 0 |
| **Tổng** | **23** | | **10** |

**Velocity = 5 + 3 + 2 = 10 points**, không phải 23. Hạng mục 8 points chưa hoàn tất không nên được ghi “hoàn thành 70%” rồi cộng 5,6 points vào velocity. Nếu nhóm chia nó thành các lát cắt độc lập, mỗi lát cắt phải có giá trị và DoD rõ ràng; không chia giả tạo chỉ để lấy điểm.

Khi hạng mục hoàn thành ở Sprint sau, chỉ tính theo quy ước nhất quán của nhóm tại lúc đạt DoD; không cộng lại điểm đã được tính. Nếu cần ước lượng lại phần còn lại để lập kế hoạch, hãy ghi rõ sự thay đổi quy ước để không hiểu nhầm chuỗi số liệu.

## 3. Velocity, throughput, năng suất và giá trị: bốn khái niệm khác nhau

| Khái niệm | Đo hoặc mô tả điều gì? | Câu hỏi phù hợp | Không tự chứng minh điều gì? |
| --- | --- | --- | --- |
| **Velocity** | Tổng điểm tương đối của công việc đạt DoD trong một Sprint | “Theo cách ước lượng của chính nhóm này, lịch sử hoàn tất ra sao?” | Năng suất từng người, so sánh nhóm, giá trị khách hàng |
| **Throughput** | Số hạng mục hoàn tất trong một đơn vị thời gian, với định nghĩa loại hạng mục rõ | “Trong một tuần, nhóm thường hoàn tất bao nhiêu mục?” | Mức độ khó, giá trị mỗi mục, chất lượng |
| **Cycle time** | Thời gian từ lúc bắt đầu xử lý đến lúc hoàn tất theo mốc đã thống nhất | “Một yêu cầu đang mất bao lâu để đi qua dòng việc?” | Hạng mục có tạo giá trị thật không |
| **Lead time** | Thời gian từ một mốc nhận yêu cầu đến lúc được đáp ứng theo quy ước | “Người yêu cầu chờ bao lâu?” | Nguyên nhân chờ nếu chỉ nhìn một con số |
| **Năng suất/hiệu quả làm việc** | Khái niệm đa chiều về khả năng tạo kết quả hữu ích trong tương quan với nguồn lực và ràng buộc | “Nhóm tạo ra kết quả tốt, bền vững và ít lãng phí đến đâu?” | Không thể thay bằng một số story points |
| **Output (đầu ra)** | Phần mềm, chức năng hoặc tài liệu đã tạo ra | “Nhóm đã bàn giao khả năng gì?” | Người dùng có dùng và nhận lợi ích không |
| **Outcome (kết quả)** | Thay đổi ở hành vi, khả năng hoặc trải nghiệm của người dùng | “Người dùng hoàn thành tác vụ tốt hơn không?” | Tác động kinh doanh lâu dài trong mọi trường hợp |
| **Impact/value (tác động/giá trị)** | Lợi ích có ý nghĩa đối với người dùng, tổ chức và những bên chịu ảnh hưởng | “Sản phẩm có giải quyết mục tiêu quan trọng không?” | Không phải lúc nào cũng đo được ngay hoặc quy về một con số |

Các khái niệm liên quan nhưng **không có dấu bằng** giữa chúng. Ví dụ, nhóm hoàn tất 12 thẻ nhỏ trong một tuần (throughput 12) chưa chắc tạo nhiều giá trị hơn khi hoàn thành hai thay đổi quan trọng giúp tránh mất dữ liệu.

### 3.1. Vận tốc không phải tốc độ gõ mã

Một nhóm xử lý story gồm phát triển, kiểm thử, review, tích hợp và đáp ứng DoD. Story points không phải “giờ lập trình” và không thể cộng dồn như số dòng code. Người dành thời gian tìm lỗi nghiêm trọng hoặc hỗ trợ đồng nghiệp có thể khiến số điểm cá nhân hoàn tất ít hơn nhưng giúp cả nhóm giao sản phẩm an toàn hơn.

### 3.2. Năng suất không chỉ là “làm nhiều hơn”

“Năng suất” đôi khi được định nghĩa bằng **đầu ra trên một đơn vị nguồn lực**, nhưng trong phát triển phần mềm, đầu ra rất khác nhau về giá trị, rủi ro và độ khó. Nếu nhóm tăng số story nhưng lỗi sau phát hành tăng mạnh, chi phí sửa chữa và tổn hại niềm tin có thể vượt lợi ích.

Để đánh giá cải tiến năng suất một cách có trách nhiệm, cần nhìn **giá trị và chất lượng của kết quả**, chi phí duy trì, sự ổn định, khả năng thích ứng và sức khỏe làm việc. Những điều này khó gộp thành một điểm số duy nhất.

### 3.3. Giá trị không nằm sẵn trong story points

Một story 13 points có thể tạo chức năng ít ai dùng; một story 2 points sửa câu thông báo dễ gây hiểu nhầm có thể giảm đáng kể cuộc gọi hỗ trợ. Story points giúp ước lượng công việc **để lên kế hoạch**, không phải “điểm giá trị” mà khách hàng nhận được.

## 4. Ví dụ số học: velocity khác nhau không đồng nghĩa giá trị tương ứng

Sản phẩm giả định là ứng dụng đăng ký workshop. Hai Sprint liên tiếp của **cùng một nhóm** có dữ liệu sau:

| Tiêu chí | Sprint A | Sprint B |
| --- | ---: | ---: |
| Velocity | 24 points | 16 points |
| Chức năng chính hoàn tất | Nhiều thành phần giao diện và báo cáo nội bộ | Sửa trạng thái đăng ký và kiểm soát xác nhận trùng |
| Tỷ lệ học viên thử hoàn tất đăng ký | 60% | 80% |
| Sự cố đăng ký được ghi nhận trong phạm vi thử | 5 | 1 |
| Phản hồi định tính | Nhiều người hỏi mình đã được xác nhận chưa | Phần lớn người thử hiểu trạng thái hơn |

**Dữ liệu hoàn toàn giả định** để minh họa việc đọc chỉ số, không phải kết quả nghiên cứu về một sản phẩm thật.

Sprint B có velocity **thấp hơn 8 points** nhưng kết quả quan sát về hoàn tất và lỗi có vẻ tốt hơn. Không thể từ bảng này khẳng định Sprint B đã tạo ra chính xác bao nhiêu tiền hoặc chứng minh thay đổi Sprint B là nguyên nhân duy nhất: nhóm người dùng thử, lượng yêu cầu và cách đo có thể khác. Tuy nhiên, bảng **đủ để bác bỏ suy luận đơn giản** “24 points luôn có giá trị hơn 16 points”.

Điều nhóm nên hỏi tiếp:

1. Người dùng thử ở hai Sprint có cùng phân khúc và tình huống không?
2. Tỷ lệ hoàn tất được đo theo cùng cách, mẫu số đủ rõ chưa?
3. Các lỗi giảm có liên quan trực tiếp đến thay đổi đã giao không?
4. Sprint A có làm công việc nền tảng mà Sprint B sử dụng không?
5. Người dùng có tiếp tục sử dụng và đánh giá giải pháp hữu ích sau vài tuần không?

Một đánh giá tốt kết hợp **velocity để hiểu khả năng hoàn tất**, **chất lượng để bảo vệ độ tin cậy**, và **outcome để hiểu lợi ích**.

## 5. Vì sao không được dùng velocity để xếp hạng nhóm hoặc cá nhân?

### 5.1. Story points là thang tương đối của từng nhóm

Nhóm X có thể gọi một story là **3 points**; nhóm Y gọi story có phạm vi gần giống là **8 points** vì họ có nền tảng, rủi ro và cách ước lượng khác nhau. Không có thước đo chuẩn chung bảo đảm một point của nhóm X bằng một point của nhóm Y.

Do vậy:

~~~text
Nhóm X: 40 points/Sprint
Nhóm Y: 20 points/Sprint
~~~

**Không thể kết luận** X năng suất gấp đôi Y. X và Y có thể dùng thang khác nhau, phân loại công việc khác nhau, độ dài Sprint khác nhau hoặc có lượng hỗ trợ vận hành không giống nhau. Ngay cả khi dùng cùng thang Fibonacci, cách gán điểm vẫn phụ thuộc vào hiểu biết và bối cảnh của từng nhóm.

### 5.2. Velocity không phải điểm KPI cá nhân

Nếu manager yêu cầu “mỗi developer phải có 15 points/Sprint”, nhóm dễ gặp:

- Người thực hiện chọn các story đã được ước lượng cao, tránh việc khó nhưng ít điểm.
- Phần việc hỗ trợ, review, đào tạo và điều tra sự cố bị xem là không tạo thành tích.
- Ước lượng bị thổi phồng để đạt chỉ tiêu.
- Mọi người ưu tiên đóng thẻ thay vì cùng hoàn thành mục tiêu sản phẩm.
- Test, refactoring hoặc vấn đề chất lượng bị trì hoãn để làm biểu đồ đẹp.

Trong Scrum, **Developers cùng chịu trách nhiệm tạo Increment đáp ứng DoD**. Velocity là dữ liệu của luồng công việc nhóm theo quy ước, không phải thước đo đóng góp của từng thành viên.

### 5.3. Khi biểu đồ tăng nhưng thực lực không tăng

Giả sử nhóm đổi cách ước lượng, mọi story trước đây là 3 points nay được gán 5 points mà độ khó và phương pháp thực hiện không đổi. Velocity có thể tăng khoảng **67%** chỉ vì đổi thang số, không phải nhờ giao nhiều giá trị hơn.

Đây là lý do nhóm không nên dùng velocity như mục tiêu phải tăng qua mỗi Sprint. Công dụng phù hợp của nó là **tham khảo lịch sử hoàn tất để dự báo trong chính bối cảnh đã tạo ra dữ liệu**.

### 5.4. Khi nào velocity giảm không phải tin xấu?

- Nhóm dành thời gian sửa lỗi nghiêm trọng để phục hồi độ tin cậy.
- Có nghỉ phép, onboarding hoặc thay đổi cấu trúc nhóm.
- Một phụ thuộc bên ngoài chặn story.
- Nhóm đang đầu tư nâng chất lượng CI, kiểm thử hoặc giảm nợ kỹ thuật.
- Các story ước lượng ban đầu thiếu hiểu biết nên chưa đạt DoD.
- Nhóm thay đổi cách chia story hoặc tiêu chuẩn kiểm tra.

Không phải mọi trường hợp trên đều “ổn”: có trường hợp phản ánh điểm nghẽn cần sửa. Quan trọng là **điều tra nguyên nhân**, thay vì mặc định giảm điểm nghĩa là nhân viên làm kém.

## 6. Dùng velocity để dự báo: có ích nhưng có điều kiện

### 6.1. Đầu vào cần có

Một dự báo dựa trên velocity cần:

1. **Danh sách hạng mục gần cần giao**, được làm rõ đủ để ước lượng theo cùng quy ước.
2. **Tổng story points của phạm vi đang xét**, không ngầm coi các yêu cầu chưa được khám phá đã được tính hết.
3. **Velocity lịch sử của chính nhóm** trong những Sprint có điều kiện gần tương đồng.
4. **Sức chứa và thay đổi đã biết**: nghỉ phép, nhân sự, phụ thuộc, hỗ trợ vận hành, độ dài Sprint.
5. **Bất định** về giải pháp, phạm vi và chất lượng dữ liệu.
6. **Quy tắc cập nhật dự báo** mỗi khi nhóm học điều mới hoặc Product Backlog đổi thứ tự.

Cần phân biệt **ước lượng (estimation)**: dự kiến quy mô/độ khó tương đối của hạng mục; và **dự báo (forecasting)**: dự kiến điều có thể hoàn tất vào khi nào hoặc với xác suất ra sao dựa trên khả năng giao thực tế.

### 6.2. Ví dụ sáu Sprint lịch sử

Giả sử nhóm có Sprint dài hai tuần và các hạng mục hoàn tất được ước lượng nhất quán:

| Sprint | Velocity (points) | Ghi chú bối cảnh |
| --- | ---: | --- |
| 1 | 18 | Bình thường |
| 2 | 20 | Bình thường |
| 3 | 16 | Có một phụ thuộc mất thời gian xử lý |
| 4 | 22 | Nhóm hoàn tất nhiều lát cắt nhỏ |
| 5 | 19 | Bình thường |
| 6 | 11 | Sự cố vận hành và nghỉ phép |
| **Tổng** | **106** | |

**Trung bình sáu Sprint:** (18 + 20 + 16 + 22 + 19 + 11) / 6 = **106/6 ≈ 17,7 points/Sprint**.

**Trung vị:** sắp xếp 11, 16, 18, 19, 20, 22; trung vị là (18 + 19) / 2 = **18,5 points/Sprint**.

**Khoảng đã quan sát:** **11–22 points/Sprint**, trong đó 11 gắn với điều kiện vận hành bất thường. Không thể xóa Sprint 6 chỉ vì nó khiến trung bình thấp hơn; nếu sự cố lặp lại thường xuyên, đó là thực tế cần đưa vào dự báo.

Giả sử backlog đã được làm rõ còn **54 points** theo cách ước lượng nhất quán. Một phép tính tham khảo:

~~~text
54 / 17,7 ≈ 3,05 Sprint
~~~

Không được đọc kết quả này thành cam kết “chắc chắn xong sau 3,05 Sprint”. Công việc chỉ hoàn tất theo từng hạng mục, velocity có biến động, phạm vi có thể thay đổi và một vài story chưa được khám phá rủi ro.

Nếu dùng hai kịch bản **16–22 points/Sprint** từ những Sprint có điều kiện gần bình thường:

- Với 22 points/Sprint: ceil(54/22) = **3 Sprint**.
- Với 16 points/Sprint: ceil(54/16) = **4 Sprint**.
- Nếu điều kiện thấp như Sprint 6 lặp lại, với 11 points/Sprint: ceil(54/11) = **5 Sprint**.

**Cách truyền đạt có trách nhiệm:** “Với phạm vi 54 points hiện nay, trong điều kiện gần các Sprint thường thấy, nhóm dự kiến khoảng 3–4 Sprint; có kịch bản kéo dài đến khoảng 5 Sprint nếu gián đoạn tương tự Sprint 6 lặp lại. Chúng ta sẽ cập nhật sau mỗi Sprint khi phạm vi và khả năng giao thực tế rõ hơn.”

Đây là **kịch bản minh họa**, không phải khoảng tin cậy thống kê được suy ra từ sáu điểm dữ liệu. Nếu muốn tuyên bố xác suất hoàn tất trước một ngày, cần phương pháp và dữ liệu đủ đáng tin để hỗ trợ xác suất đó.

### 6.3. Những giả định cần công khai

Một dự báo nêu 3–4 Sprint chỉ có nghĩa khi:

- Không có story mới lớn được thêm mà không tính vào phạm vi.
- Chất lượng, Definition of Done và cách ước lượng không bị đổi để chạy theo điểm.
- Năng lực đội gần tương đồng với những Sprint được dùng làm tham chiếu.
- Các phụ thuộc bên ngoài được làm rõ, không có vấn đề nghiêm trọng chưa tính.
- Phạm vi 54 points đã đủ rõ, không phải một phần nhỏ của toàn bộ yêu cầu còn ẩn.

Nếu một giả định thay đổi, **đổi dự báo** là hành vi minh bạch, không phải thất bại. Một dự báo tốt có mốc xem lại thay vì hứa cứng rồi cố che dữ liệu mới.

### 6.4. Không lấy trung bình làm lời hứa

Một số nhóm dùng trung bình ba Sprint gần nhất, số khác xem phân bố nhiều Sprint. Không có “ba Sprint” hay “sáu Sprint” là chuẩn bắt buộc. Cửa sổ quá ngắn có thể bị nhiễu bởi sự cố, cửa sổ quá dài có thể không phản ánh cách làm mới.

Cần xem biến động, độ dài Sprint, điểm bất thường và thay đổi đội hình. Những lần dự báo trước sai lệch ra sao cũng là bằng chứng để cải thiện cách dự báo tiếp theo.

## 7. Dự báo theo throughput và dòng công việc khi story points không phù hợp

Không phải nhóm nào cũng dùng story points. Một nhóm Kanban có thể theo dõi **hạng mục hoàn tất theo tuần**, **cycle time**, **work item age** và **WIP** để dự báo dựa trên dòng công việc.

### 7.1. Ví dụ throughput

Giả sử số hạng mục hoàn tất của một nhóm trong sáu tuần là **3, 5, 4, 4, 2, 6**.

- Tổng: **24 hạng mục trong 6 tuần**.
- Trung bình: **4 hạng mục/tuần**.
- Trung vị: **4 hạng mục/tuần**.
- Khoảng quan sát: **2–6 hạng mục/tuần**.

Nếu còn **20 hạng mục gần tương tự**, cách chia thô là 20/4 = **5 tuần**. Tuy nhiên, nếu tuần yếu tương tự tuần có throughput 2 lặp lại, có thể cần đến **10 tuần**; nếu liên tục hoàn tất 6 việc/tuần, có thể cần khoảng **4 tuần**. Những kịch bản chỉ giúp thấy mức biến động, không chứng minh khoảng phân bố tương lai.

Cách dự báo theo số hạng mục có ích khi chúng được chia **khá nhất quán**, dữ liệu lịch sử đủ nhiều và luồng công việc tương tự. Nếu một tuần toàn việc nhỏ, tuần khác có hạng mục tích hợp lớn, throughput thô có thể gây hiểu nhầm.

### 7.2. Cycle time và work item age

- **Cycle time:** từ lúc bắt đầu làm đến khi hoàn tất theo mốc nhóm thống nhất.
- **Work item age:** khoảng thời gian một việc đang làm dở đã trải qua từ mốc bắt đầu.
- **WIP:** số việc đã bắt đầu nhưng chưa hoàn tất.
- **Throughput:** số việc hoàn tất trong khoảng thời gian.

Một việc đang có tuổi lớn so với những việc cùng loại trước đây là dấu hiệu cần **kiểm tra điểm nghẽn**. Giảm WIP có thể giúp nhóm tập trung hoàn tất hạng mục thay vì liên tục bắt đầu việc mới. Khi dự báo, cần nhìn phân bố thời gian, các ngoại lệ và những loại việc khác nhau; không chỉ lấy số trung bình.

### 7.3. Monte Carlo là lựa chọn nâng cao, không phải câu trả lời thần kỳ

Nếu có đủ dữ liệu lịch sử phù hợp, nhóm có thể mô phỏng nhiều kịch bản bằng cách **lấy mẫu các throughput quan sát được** để xem phân bố số hạng mục có khả năng hoàn tất trước các mốc. Kết quả có thể diễn đạt bằng mức xác suất được mô hình ước tính, ví dụ “với giả định tương tự dữ liệu lịch sử, mô phỏng cho thấy ...”.

Nhưng mô hình sẽ sai lệch nếu backlog đổi kích thước, loại công việc thay đổi, dữ liệu bị thiếu hoặc sự cố tương lai khác đáng kể quá khứ. **Xác suất từ mô phỏng luôn có điều kiện**; không nên diễn giải thành bảo đảm giao hàng.

## 8. Ước lượng không thay thế việc chia nhỏ và kiểm chứng

Velocity biến động lớn đôi khi không đến từ người làm chậm mà từ **story quá lớn hoặc chưa rõ**. Một hạng mục 13 points gần xong nhưng chưa đạt DoD có thể khiến số điểm Sprint thấp, rồi sang Sprint sau velocity tăng mạnh khi hạng mục hoàn tất. Đó là biến động của cách đóng gói công việc.

Một cách cải thiện:

1. Làm rõ nhu cầu bằng **user story** và tiêu chí chấp nhận.
2. Chọn một **lát cắt dọc có ích** cho người dùng, đi qua những lớp kỹ thuật cần thiết.
3. Xác định Definition of Done và các quy tắc chất lượng không được bỏ qua.
4. Đưa lát cắt vào dòng công việc, giới hạn WIP và kiểm tra chỗ bị chặn.
5. Bàn giao an toàn và hỏi người dùng có giải quyết được vấn đề hay không.
6. Dùng lịch sử mới để cập nhật dự báo thay vì sửa điểm ước lượng vì áp lực.

Ví dụ chủ đề lớn “quản lý toàn bộ workshop” có thể được chia thành những khả năng **xem buổi còn chỗ**, **gửi đăng ký và nhận kết quả**, **xem trạng thái của mình**, **hủy đúng chính sách**. Một Sprint giao được một luồng hữu ích sẽ đem lại bằng chứng tốt hơn nhiều màn hình chưa tích hợp.

Không chia story bằng cách tạo các thẻ “database”, “API”, “frontend” riêng nếu việc đó khiến toàn bộ giá trị chỉ xuất hiện ở cuối. Những task kỹ thuật vẫn cần thiết, nhưng có thể là các bước thực hiện của một lát cắt người dùng.

## 9. Đo giá trị: điều gì thay đổi với người dùng sau khi giao?

### 9.1. Kết nối story với giả thuyết kết quả

Ví dụ:

> Là học viên đăng ký workshop, tôi muốn biết yêu cầu đã được ghi nhận hay đã xác nhận chỗ, để không cần nhắn hỏi ban tổ chức sau khi gửi.

Story được hoàn thành về mặt kỹ thuật khi phần mềm đáp ứng acceptance criteria và DoD. Nhưng **lợi ích trong Why** còn cần kiểm tra:

- Người dùng có hiểu “đã tiếp nhận” khác “đã xác nhận” không?
- Tỷ lệ người hoàn tất đăng ký có tăng không?
- Số lượt hỏi lại tình trạng yêu cầu có giảm không?
- Có phát sinh lỗi xác nhận trùng, tiết lộ dữ liệu hay ngừng hoạt động không?

Các tín hiệu có thể dùng:

| Loại | Chỉ số hoặc quan sát | Câu hỏi |
| --- | --- | --- |
| **Output** | Increment đã phát hành, story đạt DoD | Khả năng mới nào thực sự sẵn sàng sử dụng? |
| **Outcome** | Tỷ lệ hoàn tất, số người hiểu trạng thái, lượt hỏi lại | Hành vi và trải nghiệm người dùng thay đổi thế nào? |
| **Quality guardrail** | Lỗi dữ liệu, sự cố, truy cập sai quyền, tỷ lệ phải quay lại thao tác | Giá trị có bị đánh đổi bằng lỗi hoặc rủi ro không? |
| **Flow** | Cycle time, WIP, throughput, thời gian từ phản hồi đến kiểm chứng | Nhóm có học và giao giá trị nhanh, ổn định hơn không? |
| **Impact** | Công điều phối giảm, nhiều học viên tham dự phù hợp hơn | Mục tiêu tổ chức có được cải thiện bền vững không? |

Không thể chỉ lấy số lần nhấn nút “Đăng ký” làm bằng chứng người dùng đã có chỗ. Nhóm cần xác định chính xác **tử số, mẫu số, khoảng thời gian, nguồn dữ liệu và đối tượng** trước khi so sánh.

### 9.2. Phản hồi định tính giải thích điều các con số chưa nói

Giả sử tỷ lệ hoàn tất tăng nhưng số lần người dùng gọi để hỏi vẫn cao. Bảng số liệu chưa chỉ ra nguyên nhân. Có thể thông báo trạng thái chưa rõ, người dùng không tin kết quả hoặc quy trình ban tổ chức cần thêm bước duyệt.

Nên quan sát người dùng thực hiện và hỏi trung lập: “Bạn hiểu trạng thái này thế nào?”, “Bạn sẽ làm gì tiếp theo?”, “Lần gần nhất bạn phải liên hệ ban tổ chức vì điều gì?”. Cần tránh câu dẫn dắt “Màn hình này dễ hiểu hơn đúng không?”.

### 9.3. Không quy toàn bộ outcome cho một Sprint khi thiếu bằng chứng

Một kết quả có thể chịu tác động từ nhiều thay đổi và yếu tố bên ngoài: quảng bá, mùa workshop, loại người tham gia, lỗi vận hành hoặc điều chỉnh quy trình. Nói “tỷ lệ hoàn tất tăng trong giai đoạn quan sát” thường có căn cứ hơn “Sprint 5 làm tăng năng suất/giá trị đúng 30%” khi chưa có thiết kế kiểm chứng nhân quả.

## 10. Ví dụ tổng hợp: nhóm giao ít điểm hơn nhưng học nhanh hơn

### 10.1. Bối cảnh

Nhóm phát triển nền tảng đặt lịch tư vấn trực tuyến. Ban đầu backlog ưu tiên trang quản trị và hệ thống báo cáo. Sau một buổi dùng thử, nhóm phát hiện người dùng không phân biệt được **lịch đã gửi yêu cầu** với **lịch được xác nhận**.

Nhóm phải chọn:

- **Phương án A:** tiếp tục kế hoạch các hạng mục nhiều points để giữ velocity dự kiến.
- **Phương án B:** ưu tiên lát cắt nhỏ sửa thông báo trạng thái, thêm kiểm thử và cho người dùng dùng thử trước khi mở rộng.

Nếu mục tiêu là giảm số người phải gọi hỏi lại, phương án B có thể tạo cơ hội học có giá trị hơn. Nhưng không được kết luận chỉ từ cảm giác; nhóm cần xác định cách kiểm chứng.

### 10.2. Kế hoạch phản hồi dựa trên bằng chứng

1. **Giả thuyết:** thông báo rõ “chờ xác nhận”, thời điểm phản hồi dự kiến và hành động tiếp theo sẽ giúp người dùng hiểu tình trạng lịch.
2. **Bản bàn giao:** một lát cắt hoạt động từ việc gửi yêu cầu đến thông báo kết quả, đáp ứng quyền riêng tư và kiểm thử.
3. **Đối tượng:** nhóm dùng thử nhỏ đại diện các cách sử dụng quan trọng.
4. **Chỉ số chính:** tỷ lệ người dùng hiểu đúng trạng thái mà không cần giải thích.
5. **Chỉ số bảo vệ:** lỗi xác nhận sai, dữ liệu bị lộ, người dùng bỏ dở luồng.
6. **Tín hiệu bổ sung:** số lần gọi hỏi lại và nội dung câu hỏi thực tế.
7. **Quyết định tiếp:** nếu phần lớn hiểu đúng trong phạm vi thử và không có lỗi nghiêm trọng, cân nhắc mở rộng thử; nếu chưa, điều chỉnh lời thông báo/quy trình trước khi thêm báo cáo.

Điều bài học muốn nhấn mạnh: **đạt 8 points và kiểm chứng được một giả thuyết cốt lõi** có thể có ích hơn **đạt 25 points nhưng không ai sử dụng**, tùy ngữ cảnh. Việc đánh giá cần dựa trên giá trị, chất lượng và độ tin cậy của bằng chứng, không dựa vào số điểm tự thân.

## 11. Scrum, Kanban và XP hỗ trợ đo lường và dự báo ra sao?

### 11.1. Scrum: dự báo phục vụ Sprint Goal, không làm chủ mục tiêu

Trong Scrum, Developers chọn công việc và lập kế hoạch hướng tới **Sprint Goal** dựa trên sự hiểu biết, năng lực và dữ liệu có ích. Các thành viên có thể tham khảo velocity trước đây, nhưng **Scrum không bắt buộc velocity** và không yêu cầu mỗi Sprint phải hoàn tất số điểm tăng dần.

- **Sprint Planning:** xem mục tiêu, backlog đã làm rõ, khả năng thực tế; velocity chỉ là một tín hiệu.
- **Daily Scrum:** kiểm tra tiến độ đạt Sprint Goal, điều chỉnh kế hoạch, gỡ cản trở thay vì “đếm điểm còn thiếu”.
- **Sprint Review:** kiểm tra Increment, phản hồi người dùng và điều chỉnh Product Backlog.
- **Sprint Retrospective:** nhìn cách phối hợp, chất lượng, dữ liệu dòng việc và thử cải tiến một điểm nghẽn.

Không nên chọn các story chỉ vì cộng đủ điểm theo kỳ vọng nếu chúng **không cùng đóng góp vào Sprint Goal**. Sprint Review cũng không nên trở thành buổi chứng minh “velocity đẹp” thay vì thảo luận sản phẩm chạy được.

### 11.2. Kanban: tập trung dòng công việc và khả năng dự báo

Kanban thường nhấn mạnh **visualization, explicit policies, WIP, flow metrics** và cải tiến dựa trên dữ liệu. Một nhóm có thể dự báo theo throughput, cycle time và phân bố lịch sử thay vì story points.

Hãy tưởng tượng bảng:

~~~text
Sẵn sàng → Đang làm (WIP 3) → Review (WIP 2) → Kiểm thử → Hoàn tất
                                      ↑
                              Hạng mục chờ lâu
~~~

Nếu nhiều hạng mục bị chặn ở review, việc bắt đầu thêm không giúp chúng hoàn tất nhanh. Nhóm có thể thử ưu tiên hỗ trợ review và giới hạn WIP, rồi quan sát **cycle time, throughput, lỗi và khả năng bàn giao giá trị** trong những tuần sau.

### 11.3. XP: phản hồi kỹ thuật nhanh và chất lượng bền vững

**Test-driven development (TDD)**, **pair programming**, **continuous integration** và **refactoring** giúp giảm rủi ro thay đổi và phát hiện lỗi sớm. Những thực hành này có thể giúp nhóm giao Increment nhỏ, thường xuyên và đáng tin hơn, nhưng không nên được đánh giá chỉ bằng mức tăng points.

Một Sprint dành thời gian bổ sung kiểm thử cho quy tắc chống đăng ký trùng có thể có velocity thấp hơn. Nếu sau đó số sự cố và thời gian khôi phục giảm, khả năng giao giá trị dài hạn có thể tốt hơn. Cần theo dõi và kiểm chứng trước khi kết luận.

## 12. Cách trình bày dự báo cho Product Owner và bên liên quan

Một dự báo có ích phải giúp người ra quyết định **hiểu lựa chọn, giả định và rủi ro**, không chỉ nhận một ngày hẹn cứng.

### 12.1. Nội dung tối thiểu của một bản dự báo

| Nội dung | Ví dụ cách trình bày |
| --- | --- |
| **Phạm vi** | 54 points đã được làm rõ cho nhóm và quy ước hiện tại |
| **Nguồn dữ liệu** | Sáu Sprint gần nhất của chính nhóm, velocity 11–22 points |
| **Mốc thường thấy** | Trung bình khoảng 17,7; trung vị 18,5 points/Sprint |
| **Kịch bản** | Khoảng 3–4 Sprint trong điều kiện gần thông thường, có thể 5 nếu gián đoạn lặp lại |
| **Giả định** | Không thêm nhiều hạng mục, giữ DoD và đội hình tương tự |
| **Rủi ro nổi bật** | Phụ thuộc tích hợp thanh toán chưa kiểm chứng |
| **Điều có thể điều chỉnh** | Chia phạm vi ưu tiên, giảm tính năng chưa quan trọng, làm rõ rủi ro trước |
| **Mốc cập nhật** | Sau mỗi Sprint và khi phạm vi/nguồn lực thay đổi đáng kể |

Tránh đưa ra phần trăm “độ tin cậy 90%” nếu không có phương pháp xác định phù hợp. Khi các mốc ngày thật được yêu cầu, cần tính lịch nghỉ, sự kiện phụ thuộc, thời gian chấp nhận hoặc phát hành riêng; không đơn giản nhân số Sprint rồi coi đó là ngày chắc chắn cho khách hàng.

### 12.2. Mẫu trao đổi khi bị yêu cầu “tăng velocity 30%”

Một cách trả lời hợp tác:

> “Velocity đo số điểm các story đạt Definition of Done theo quy ước của nhóm, không phản ánh trực tiếp năng suất hoặc giá trị. Nếu mục tiêu là giao tính năng quan trọng sớm hơn, chúng ta có thể xem hạng mục đang chờ ở đâu, giảm WIP, chia story rõ hơn và cải thiện kiểm thử. Tôi sẽ theo dõi thời gian giao, chất lượng và kết quả người dùng cùng velocity để đánh giá cải tiến. Chúng ta không nên tăng điểm ước lượng chỉ để đạt con số.”

Nếu mục tiêu là thời hạn giao một chức năng quan trọng, nhóm có thể so sánh **phạm vi tối thiểu tạo giá trị**, các phụ thuộc và kịch bản năng lực thay vì cam kết “thêm người là points lập tức tăng”.

### 12.3. Burn-up và thay đổi phạm vi

Khi phạm vi thay đổi, nên thể hiện rõ **khối lượng đã hoàn tất** và **tổng phạm vi hiện tại** (chẳng hạn biểu đồ burn-up) thay vì chỉ nói “nhóm chậm”. Việc tăng phạm vi có thể khiến mốc hoàn thành lùi dù velocity ổn định. Cũng cần ghi nhận điểm không còn so sánh được nếu cách ước lượng thay đổi.

Một biểu đồ chỉ là phương tiện hỗ trợ thảo luận; nó không thay thế kiểm tra chất lượng Increment và kết quả sử dụng.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| So sánh velocity giữa hai nhóm | Thang điểm, loại việc và bối cảnh khác nhau | So sánh kết quả với mục tiêu của từng nhóm; không dùng points liên nhóm như chuẩn chung |
| Xem velocity là KPI cá nhân | Khuyến khích tranh điểm, giảm hợp tác | Theo dõi khả năng hoàn tất của nhóm, hành vi cộng tác và kết quả sản phẩm |
| Cộng điểm story chưa đạt DoD | Báo cáo sai trạng thái Increment | Chỉ tính điểm hạng mục thực sự hoàn tất theo DoD |
| Đổi điểm ước lượng để đạt target | Biểu đồ tăng giả, dự báo mất căn cứ | Giữ quy ước nhất quán, ghi rõ khi thay đổi cách ước lượng |
| Dùng velocity làm giá trị kinh doanh | Hoàn tất nhiều nhưng có thể sai nhu cầu | Kết hợp outcome, phản hồi người dùng và chất lượng |
| Lấy trung bình một vài Sprint làm ngày giao chắc chắn | Bỏ qua biến động và yêu cầu mới | Trình bày phạm vi, kịch bản, giả định và ngày xem lại |
| Loại bỏ Sprint bất thường không có lý do | Che rủi ro vốn có trong vận hành | Phân tích điều kiện đặc biệt, giữ kịch bản bất lợi |
| Đếm số task nhỏ để tự chứng minh năng suất | Throughput tăng do thay cách chia, không do lợi ích | Giữ quy tắc loại hạng mục nhất quán và đo kết quả |
| Chỉ tăng tốc lập trình, bỏ qua review/test | Lỗi tăng, thời gian sửa lại dài | Bảo vệ DoD, tự động hóa kiểm tra và cải thiện dòng việc |
| Không tính công việc ngoài luồng | Dự báo năng lực lạc quan, người thực hiện chịu áp lực vô lý | Hiển thị hỗ trợ, sự cố và tác động lên kế hoạch |
| Dùng phương pháp thống kê phức tạp với dữ liệu kém | Tạo cảm giác chính xác giả | Cải thiện nguồn dữ liệu, phân loại công việc và giải thích giới hạn |
| Không cập nhật dự báo khi backlog đổi | Gây kỳ vọng sai và đánh mất niềm tin | Xem lại sau mỗi vòng học, báo minh bạch thay đổi |

## 14. Bài thực hành: dự báo và đánh giá giá trị có trách nhiệm

### 14.1. Bối cảnh

Nhóm phát triển ứng dụng đặt lịch có Sprint dài hai tuần. Nhóm dùng story points và đã làm việc với cùng quy ước ước lượng trong sáu Sprint.

Dữ liệu lịch sử **giả định**:

| Sprint | Points đã đạt DoD | Points còn dang dở cuối Sprint | Ghi chú |
| --- | ---: | ---: | --- |
| S1 | 14 | 5 | Bình thường |
| S2 | 18 | 8 | Bình thường |
| S3 | 12 | 13 | Nhiều chờ review |
| S4 | 20 | 5 | Hoàn tất các hạng mục nhỏ |
| S5 | 16 | 8 | Bình thường |
| S6 | 8 | 13 | Xử lý một sự cố lớn |

Nhóm đang xem xét phạm vi đã làm rõ **48 points**. Product Owner muốn biết khi nào có thể bàn giao một phiên bản dùng thử, đồng thời một người quản lý yêu cầu **“đặt chỉ tiêu Sprint tới 25 points”**.

### 14.2. Nhiệm vụ A – Tính số liệu đúng (10 phút)

1. Tính velocity từng Sprint và **trung bình** sáu Sprint.
2. Tính **trung vị** của sáu quan sát.
3. Giải thích vì sao không cộng points còn dang dở vào số hoàn tất.
4. Nêu hai thay đổi có thể làm dữ liệu lịch sử kém phù hợp cho Sprint tới.

**Gợi ý kiểm tra:** tổng points đạt DoD là 14 + 18 + 12 + 20 + 16 + 8 = **88 points**, trung bình **88/6 ≈ 14,7 points/Sprint**. Sắp xếp 8, 12, 14, 16, 18, 20, trung vị **(14 + 16)/2 = 15 points/Sprint**. Các điểm dang dở chưa đạt DoD không phải Increment hoàn tất.

### 14.3. Nhiệm vụ B – Lập dự báo có kịch bản (15 phút)

Giả sử phạm vi còn lại là **48 points**, cùng thang ước lượng và không có yêu cầu lớn phát sinh:

1. Dùng hai mức velocity thường thấy **12–20** để tính số Sprint cần thiết.
2. Thêm một kịch bản bất lợi nếu năng lực giống Sprint S6 tái diễn.
3. Diễn đạt dự báo thành câu nói cho Product Owner với phạm vi, giả định, rủi ro và mốc cập nhật.
4. Giải thích vì sao không nên cam kết “48/14,7 = đúng 3,27 Sprint”.
5. Đề xuất cách chia tính năng để giao một **lát cắt có giá trị** sớm hơn dự báo hoàn tất toàn bộ 48 points.

**Gợi ý tính:** theo mức **20 points**, ceil(48/20) = **3 Sprint**; theo **12 points**, ceil(48/12) = **4 Sprint**; với mức **8 points**, ceil(48/8) = **6 Sprint**. Đây là những kịch bản đơn giản, không phải xác suất đã được kiểm chứng.

### 14.4. Nhiệm vụ C – Phân biệt hiệu suất và giá trị (15 phút)

Trong hai giai đoạn thử nghiệm giả định của sản phẩm:

| Tín hiệu | Giai đoạn A | Giai đoạn B |
| --- | ---: | ---: |
| Velocity | 20 points | 12 points |
| Người dùng thử hoàn tất đặt lịch | 12/20 | 17/20 |
| Người dùng phải liên hệ hỗ trợ sau đặt lịch | 8/20 | 3/20 |
| Lỗi nghiêm trọng được ghi nhận trong đợt thử | 2 | 0 |

Trả lời:

- Nhóm có “kém năng suất hơn” ở B chỉ vì velocity thấp hơn không?
- Tính tỷ lệ hoàn tất và tỷ lệ liên hệ hỗ trợ ở mỗi giai đoạn.
- Chỉ số nào đang cho tín hiệu **outcome**, chỉ số nào cho **chất lượng**, chỉ số nào đo công việc đã hoàn tất?
- Có đủ bằng chứng quy toàn bộ cải thiện cho một tính năng mới không? Vì sao?
- Cần hỏi người dùng và thu thập dữ liệu nào để xác nhận giả thuyết giá trị?

**Gợi ý tính:** tỷ lệ hoàn tất A = **60%**, B = **85%**; tỷ lệ liên hệ hỗ trợ A = **40%**, B = **15%**. Chênh lệch có vẻ tích cực nhưng cần xem mẫu, cách chọn người thử, rủi ro và thay đổi ngoài phần mềm trước khi khẳng định nhân quả.

### 14.5. Nhiệm vụ D – Trả lời stakeholder (10 phút)

Viết thông điệp ngắn giải thích vì sao không nên đặt KPI “mọi Sprint phải đạt 25 points”, đồng thời đề xuất:
- Mục tiêu người dùng nên ưu tiên.
- Việc có thể làm để nâng khả năng giao hàng bền vững.
- Hai chỉ số dòng việc và một chỉ số bảo vệ chất lượng.
- Khi nào sẽ kiểm tra lại tác động của cải tiến.

Một câu trả lời tốt **không phủ nhận việc đo lường**; nó chuyển cuộc trao đổi từ việc tối ưu điểm sang khả năng hoàn tất công việc hữu ích, giữ chất lượng và nhận phản hồi sớm.

### 14.6. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Định nghĩa velocity** | Cộng mọi điểm đã nhận hoặc điểm dang dở | Chỉ tính points đạt DoD | Giải thích được điều kiện nhất quán và thay đổi quy ước |
| **Phân biệt khái niệm** | Đồng nhất điểm, năng suất và giá trị | Phân biệt velocity, throughput, outcome | Biết đánh giá cả chất lượng, năng lực, tác động và giới hạn |
| **Dự báo** | Hứa một con số chắc chắn | Có kịch bản, phạm vi và giả định | Nêu được biến động, điểm ngoại lệ và cách cập nhật |
| **Ra quyết định** | Chỉ cố tăng điểm | Chọn việc theo giá trị và rủi ro | Có phép thử người dùng và dữ liệu để đổi ưu tiên |
| **Cộng tác** | So sánh điểm cá nhân/nhóm | Dùng số liệu để thảo luận cải tiến nhóm | Tránh tối ưu chỉ số hình thức và giữ minh bạch với stakeholder |

## 15. Biểu mẫu áp dụng trong nhóm

### 15.1. Phiếu đọc dữ liệu Sprint

~~~text
Độ dài Sprint:
Định nghĩa và quy ước points:
Definition of Done được áp dụng:
Story đạt DoD và điểm tương ứng:
Story chưa đạt DoD (không tính points):
Velocity Sprint:
Công việc phát sinh / sự cố / nghỉ phép:
Điểm nghẽn có bằng chứng:
Kết quả người dùng nhận được:
Vấn đề chất lượng:
Điều nhóm cần học hoặc điều chỉnh:
~~~

### 15.2. Phiếu dự báo theo kịch bản

~~~text
Mục tiêu bàn giao:
Nhóm người dùng và lợi ích cần đạt:
Phạm vi hạng mục đã làm rõ:
Đơn vị dự báo: story points / số hạng mục / loại khác
Dữ liệu lịch sử và khoảng thời gian:
Cách tính và giả định:
Kịch bản thuận lợi:
Kịch bản thường thấy:
Kịch bản bất lợi:
Phụ thuộc và bất định lớn:
Giới hạn của dữ liệu:
Lát cắt giá trị có thể giao sớm:
Người chịu trách nhiệm trao đổi ưu tiên:
Khi nào cập nhật dự báo:
~~~

### 15.3. Phiếu kiểm chứng giá trị sau bàn giao

~~~text
User story / giả thuyết giá trị:
Ai sử dụng:
Khả năng phần mềm đã giao (output):
Kết quả mong muốn (outcome):
Chỉ số chính, mẫu số và kỳ quan sát:
Chỉ số chất lượng bảo vệ:
Phản hồi định tính:
Điều quan sát được:
Điều chưa thể kết luận:
Quyết định: giữ / mở rộng / sửa / thử tiếp / dừng
Backlog cần điều chỉnh:
Người phụ trách và mốc xem lại:
~~~

Biểu mẫu chỉ có ích khi phục vụ **một quyết định thật**. Không nên biến việc ghi chép thành công việc làm chậm giao sản phẩm hoặc yêu cầu mọi nhóm phải dùng cùng một thang điểm.

## 16. Checklist trước khi dùng velocity và đưa ra dự báo

- [ ] Đã phân biệt **vận tốc hoàn tất** với **năng suất**, **đầu ra** và **giá trị**.
- [ ] Velocity chỉ cộng điểm của các hạng mục thực sự đạt Definition of Done.
- [ ] Cách ước lượng và độ dài Sprint đủ nhất quán để so sánh trong chính nhóm.
- [ ] Không dùng story points để xếp hạng cá nhân hoặc so sánh trực tiếp giữa các nhóm.
- [ ] Đã xem thay đổi năng lực, nghỉ phép, hỗ trợ và sự cố của các kỳ lịch sử.
- [ ] Đã kiểm tra công việc lớn, điểm nghẽn, WIP và tỷ lệ hạng mục dang dở.
- [ ] Dự báo có phạm vi rõ, dùng dữ liệu lịch sử thích hợp và nêu các giả định.
- [ ] Có ít nhất một kịch bản bất lợi; không nói thời điểm chắc chắn từ một trung bình đơn lẻ.
- [ ] Kế hoạch xem lại dự báo được thống nhất khi backlog hoặc tình hình thay đổi.
- [ ] Có thể bàn giao một lát cắt giá trị trước khi hoàn thành toàn bộ phạm vi lớn.
- [ ] Chỉ số sản phẩm gắn với giả thuyết lợi ích của user story.
- [ ] Có theo dõi chất lượng để tránh đánh đổi lòng tin lấy số điểm.
- [ ] Nhóm kết hợp phản hồi định tính, dữ liệu sử dụng và dòng công việc.
- [ ] Khi chỉ số tăng hoặc giảm bất thường, nhóm đặt câu hỏi về nguyên nhân trước khi đánh giá con người.
- [ ] Product Owner và các bên liên quan hiểu dự báo là công cụ quyết định thích ứng, không phải bảo đảm tuyệt đối.

**Thông điệp cốt lõi:** *Velocity giúp một nhóm hiểu nhịp hoàn tất công việc đã ước lượng, không đo trực tiếp mức độ giỏi của con người hay giá trị khách hàng nhận được.* Dự báo Agile hữu ích khi có dữ liệu phù hợp, thừa nhận bất định và được cập nhật theo thực tế. Thành công bền vững đến từ việc **giao phần mềm hữu ích, đo kết quả người dùng, bảo vệ chất lượng và liên tục cải thiện khả năng giao hàng**, chứ không phải làm cho biểu đồ points tăng bằng mọi giá.
