# Chuyển mục tiêu sản phẩm thành các giả thuyết và phần tăng trưởng nhỏ

> **Chương:** Thực hành tổng hợp  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một nhóm phát triển nền tảng đặt lịch tư vấn được giao mục tiêu **“Khách có thể tự đặt lịch thành công và tin tưởng trạng thái xác nhận mà không cần gọi tổng đài”**. Mục tiêu nghe hợp lý, nhưng nhóm có thể biến nó thành những danh sách việc rất khác nhau: thiết kế lại toàn bộ trang đặt lịch, xây hệ thống gửi SMS, bổ sung nút Đặt lại, viết lại Booking API, nâng cấp cơ sở dữ liệu hoặc phỏng vấn người dùng. Không phải việc nào cũng có cơ sở tạo ra kết quả mong muốn.

Nếu nhóm chọn ngay phương án “xây mọi tính năng đã đề xuất”, họ có thể mất nhiều tháng mới biết rằng khách không gọi tổng đài vì thiếu SMS, mà vì **trạng thái Pending bị hiểu nhầm là lỗi**. Nếu nhóm chỉ viết thử nghiệm mà không giao phần mềm dùng được, họ có thể học được nhiều điều nhưng không tạo giá trị. Nếu giao giao diện đẹp khi API còn có thể tạo lịch trùng, họ tạo **đầu ra** nhưng chưa tạo một **Increment an toàn**.

Bài học này kết nối các kỹ năng của Agile thành một quy trình thực hành:

> **Product Goal → Vấn đề/cơ hội → Giả thuyết → Bằng chứng cần thu → Product Backlog có thứ tự → Lát cắt giá trị nhỏ → Increment đạt Definition of Done → Phản hồi thực tế → Quyết định thích ứng.**

Điểm quan trọng không phải đi hết các bước như một “waterfall thu nhỏ”, mà là tạo **những vòng học ngắn**: giả thuyết có thể kiểm chứng trước khi xây; khi xây, phần mềm đủ chất lượng để có thể dùng; khi có phản hồi, kế hoạch có thể đổi. Mỗi vòng cải thiện cả **hiểu biết sản phẩm** và **khả năng giao phần mềm**.

Tất cả nhân vật, số liệu và tình huống dưới đây là **ví dụ giả định phục vụ học tập**, không phải dữ liệu sản phẩm thật, quy tắc Scrum bắt buộc hoặc cam kết hiệu quả.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **Product Goal, outcome, vấn đề/cơ hội, giải pháp, giả thuyết, Product Backlog Item (PBI), Sprint Goal, Increment và release**.
2. Chuyển một Product Goal rộng thành **các vấn đề người dùng được ưu tiên dựa trên bằng chứng**, tránh nhảy thẳng đến danh sách tính năng.
3. Viết **giả thuyết giá trị, khả năng sử dụng, tính khả thi kỹ thuật và rủi ro** có tiêu chí quan sát/bác bỏ rõ.
4. Chọn cách **giảm bất định rẻ và an toàn** bằng phỏng vấn, prototype, spike có timebox, dữ liệu hành vi hoặc một Increment nhỏ.
5. Lập **bản đồ hành trình/story map** rồi chia công việc thành các lát cắt **đầu-cuối** thay vì chỉ tách UI/API/database.
6. Viết **user story hoặc PBI đủ rõ**, acceptance criteria, trường hợp lỗi, yêu cầu phi chức năng và tiêu chí Definition of Done.
7. Xếp thứ tự PBI theo **giá trị, rủi ro, chi phí trì hoãn, cơ hội học, phụ thuộc và năng lực**, không chỉ điểm số hoặc ý kiến stakeholder.
8. Kết nối việc chọn PBI với **Scrum Sprint Goal, Sprint Backlog, Kanban flow/WIP** và các thực hành **XP/TDD/CI**.
9. Phân biệt **Done, Increment, deploy, release và outcome**; tránh tính một phần giao diện chưa tích hợp là tính năng hoàn tất.
10. Thiết kế thước đo **outcome, flow, chất lượng và guardrails** với mẫu số rõ, diễn giải đúng phần trăm, điểm phần trăm và mức bất định.
11. Xử lý thông tin mới: giả thuyết sai, API đối tác không đáp ứng, lỗi production, thiếu năng lực hoặc feedback trái chiều.
12. Tự hoàn thành một **bài thực hành tổng hợp** có Product Goal, opportunity map, hypothesis backlog, lát cắt Increment, kế hoạch đo và quyết định thích ứng.

## 2. Bức tranh tổng thể: từ mục tiêu đến một vòng tạo giá trị

### 2.1. Các tầng tư duy không được trộn lẫn

| Tầng | Câu hỏi | Ví dụ ở nền tảng đặt lịch |
| --- | --- | --- |
| **Product Goal** | Chúng ta đang tiến tới trạng thái giá trị dài hạn nào? | Khách tự đặt lịch đáng tin, ít cần nhờ tổng đài để xác nhận. |
| **Outcome/điều cần cải thiện** | Người dùng/hệ thống nên thay đổi hành vi hoặc kết quả gì? | Tỷ lệ phiên đặt lịch được xác nhận tăng, lượt gọi hỏi trạng thái giảm. |
| **Vấn đề/cơ hội** | Điều gì đang cản kết quả đó? | Khách không biết yêu cầu còn Pending hay đã Confirmed. |
| **Giả thuyết** | Nếu thay điều gì, vì sao chúng ta nghĩ kết quả sẽ tốt hơn? | Nếu hiển thị trạng thái rõ, khách sẽ ít gửi lặp và ít gọi xác nhận. |
| **Thử nghiệm/bằng chứng** | Điều gì giúp biết giả thuyết đúng hoặc sai sớm? | Usability test và quan sát phiên đã sử dụng trạng thái mới. |
| **Product Backlog Item** | Phần công việc có giá trị/giảm rủi ro nào nên làm tiếp? | Tra cứu trạng thái yêu cầu đặt lịch. |
| **Lát cắt nhỏ** | Phạm vi nào có thể hoàn tất an toàn và kiểm tra được? | Tra cứu trạng thái cho lịch tư vấn đơn với ba trạng thái rõ. |
| **Increment** | Phần phần mềm nào đã tích hợp và đạt chất lượng chung? | UI + API + xử lý trạng thái + test đạt Definition of Done. |
| **Phản hồi và quyết định** | Bằng chứng mới gợi ý tiếp tục, sửa, dừng hay mở rộng? | Có thể ưu tiên đối soát timeout thay vì xây SMS. |

**Product Goal không phải một tập hợp PBI cố định.** **Giả thuyết không phải sự thật.** **Task hoàn tất không tự bằng Increment**. **Increment đạt Done chưa tự chứng minh đã có outcome ở khách hàng**.

### 2.2. Một vòng học có thể tạo nhiều loại đầu ra

~~~mermaid
flowchart TD
    G["Product Goal"] --> O["Vấn đề / cơ hội ưu tiên"]
    O --> H["Giả thuyết có thể kiểm chứng"]
    H --> Q{"Loại bất định lớn nhất?"}
    Q -->|Nhu cầu / khả năng sử dụng| R["Nghiên cứu / prototype có giới hạn"]
    Q -->|Khả thi / rủi ro kỹ thuật| S["Spike / test hợp đồng / thử nghiệm sandbox"]
    Q -->|Giá trị trong sử dụng thật| B["Lát cắt PBI có giá trị"]
    R --> E["Bằng chứng, giới hạn và quyết định"]
    S --> E
    B --> I["Increment tích hợp, đạt DoD"]
    I --> L["Release phù hợp khi an toàn"]
    L --> M["Outcome, phản hồi và guardrails"]
    M --> E
    E --> D{"Tiếp tục / sửa / dừng / đổi thứ tự"}
    D --> O
    D --> G
~~~

Sơ đồ có các vòng quay về trước: **không phải mọi giả thuyết đều cần xây feature**. Một số bất định nên giảm bằng nghiên cứu hoặc spike. Nhưng khi quyết định xây, mục tiêu là **lát cắt phần mềm hữu ích có thể tích hợp và đạt chuẩn**, không phải tạo thật nhiều task kỹ thuật.

### 2.3. Product discovery và product delivery liên tục trao đổi

**Discovery** tìm vấn đề đúng, rủi ro và bằng chứng cho việc chọn giải pháp. **Delivery** tạo Increment chất lượng rồi giúp thu phản hồi thực tế. Hai hoạt động **có thể chồng lấp và hỗ trợ nhau**, không nên biến thành “bộ phận nghiên cứu thiết kế mọi thứ xong rồi bàn giao cả khối cho đội phát triển”.

Ví dụ:

- Trong lúc nhóm đang đưa trạng thái Pending vào sản phẩm, một Developer cùng Product Owner thử khả năng hiểu của khách về từ “Đang xác nhận”.
- Kết quả thử cho thấy khách hiểu “Đang xác nhận” nhưng vẫn nhấn gửi lại vì không thấy mã yêu cầu. Nhóm bổ sung mã tra cứu vào PBI gần nhất.
- Trong khi viết contract tests, nhóm phát hiện API đối tác có thể trả timeout sau xử lý; backlog cần thêm công việc đối soát.

**Bằng chứng thay đổi công việc tiếp theo**, không phải được thu chỉ để làm tài liệu đẹp.

### 2.4. Thực hành tổng hợp không buộc mọi nhóm dùng chung một framework

Scrum giúp minh bạch **Product Goal, Product Backlog, Sprint Goal, Increment và nhịp kiểm tra/thích ứng**. Kanban giúp trực quan hóa **dòng công việc, WIP, cycle time, throughput và work item age**. XP đóng góp **TDD, CI, refactoring, pairing và thay đổi nhỏ** để tăng phản hồi kỹ thuật.

Nhóm có thể phối hợp những thực hành này theo bối cảnh. **Nếu gọi cách làm là Scrum**, cần tôn trọng các thành phần thiết yếu trong Scrum Guide; không dùng tên Scrum để hợp thức hóa một quy trình chỉ có Daily Scrum và bảng task.

## 3. Phân biệt mục tiêu, kết quả và việc cần làm

### 3.1. Mục tiêu sản phẩm không phải một tính năng

Ba cách viết khác nhau:

**Danh sách đầu ra chưa phải Product Goal rõ:**

> “Xây SMS, thêm nút Đặt lại và viết lại API trước cuối quý.”

**KPI đơn lẻ chưa nói đủ định hướng giá trị:**

> “Tăng conversion lên 80%.”

**Mục tiêu sản phẩm thể hiện trạng thái tương lai mong muốn:**

> “Khách đặt được lịch tư vấn hợp lệ và biết kết quả xác nhận đáng tin ngay trên ứng dụng, không phải phụ thuộc tổng đài.”

Một Product Goal tốt có thể gắn **cách quan sát tiến triển**, nhưng không nên biến thành danh sách giải pháp đã chốt bất chấp phản hồi.

### 3.2. Trong Scrum, Product Goal là commitment của Product Backlog

Theo **Scrum Guide 2020**:

- **Product Backlog** là danh sách có thứ tự, liên tục phát triển về những gì cần để cải thiện sản phẩm.
- **Product Goal** là commitment của Product Backlog, mô tả trạng thái tương lai của sản phẩm và là mục tiêu dài hạn để Scrum Team lập kế hoạch.
- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog, bao gồm việc sắp thứ tự và bảo đảm minh bạch.
- Scrum Team tập trung đạt hoặc từ bỏ một Product Goal trước khi nhận Product Goal tiếp theo.

Không cần tuyên bố mọi chỉ số OKR hay business KPI **tự động là Product Goal**. Chúng có thể hỗ trợ Product Goal nhưng có mục đích và thời hạn khác.

### 3.3. Chọn outcome phản ánh giá trị, không chỉ hoạt động của nhóm

| Không nên dùng một mình | Outcome gần giá trị hơn | Cẩn trọng |
| --- | --- | --- |
| Số story points đã đóng. | Tỷ lệ người dùng hoàn tất một tác vụ có ý nghĩa. | Không so velocity giữa nhóm hoặc biến hoàn tất task thành giá trị. |
| Số lần bấm nút Đặt lịch. | Tỷ lệ phiên dẫn tới trạng thái Confirmed có thẩm quyền. | Phân biệt click, request accepted và booking Confirmed. |
| Số lần gửi SMS. | Tỷ lệ khách hiểu và truy cập được kết quả đặt lịch. | SMS là kênh, chưa phải giá trị. |
| Số cuộc Sprint Review. | Số quyết định sản phẩm được cải thiện dựa trên feedback phù hợp. | Không chạy theo số quyết định thay đổi cho đẹp. |
| Số PR merge. | Lát cắt end-to-end đạt chất lượng và có thể dùng. | Code merge chưa thay thế DoD. |
| Số lần deploy. | Giao thay đổi an toàn và quan sát giá trị người dùng. | Không tăng tần suất release bằng bỏ kiểm soát. |

Các tín hiệu về hoạt động vẫn có thể giúp kiểm tra can thiệp được thực hiện hay chưa, nhưng không nên **được gọi là kết quả cuối**.

### 3.4. Đừng trộn Product Goal, Sprint Goal và acceptance criteria

| Khái niệm | Chân trời/tác dụng | Ví dụ |
| --- | --- | --- |
| **Product Goal** | Mục tiêu dài hạn giúp định hướng nhiều Increment. | Khách đặt và tra cứu lịch đáng tin không cần tổng đài. |
| **Outcome metric** | Quan sát thay đổi có ý nghĩa đối với kết quả. | Completion rate và số cuộc gọi xác nhận trên 100 phiên. |
| **Sprint Goal** | Mục tiêu duy nhất cho Sprint, commitment của Sprint Backlog. | Khách có thể tra cứu trạng thái yêu cầu đặt lịch khi mạng chậm. |
| **PBI** | Công việc được cân nhắc và sắp thứ tự để cải thiện sản phẩm. | API tra cứu trạng thái và UI hiển thị phù hợp. |
| **Acceptance criteria** | Các ví dụ/điều kiện xác nhận hành vi của PBI. | Với PENDING, UI không hiển thị “Đã đặt lịch thành công”. |
| **Definition of Done** | Tiêu chuẩn chất lượng áp dụng cho Increment. | Tích hợp/test/bảo mật/vận hành đạt chuẩn phù hợp. |

**Sprint Goal không phải danh sách mọi task.** Acceptance criteria mô tả các điều kiện cụ thể của PBI; **DoD là tiêu chuẩn chất lượng chung**, không nên thay nó bằng các tiêu chí nghiệp vụ của một story.

## 4. Tình huống nền: sản phẩm đặt lịch có nhiều dấu hiệu mâu thuẫn

### 4.1. Giới hạn của ví dụ

Nền tảng giả định có:

- Khách chọn chuyên gia, dịch vụ và khung giờ.
- Booking Service ghi yêu cầu và phối hợp nhà cung cấp lịch bên ngoài.
- Giao diện có thể nhận các trạng thái **Pending, Confirmed, Rejected** và đôi khi **Unknown** khi không rõ kết quả từ đối tác.
- Các nhóm trải nghiệm, Booking domain và tích hợp đối tác cùng tham gia.
- Support nhận cuộc gọi khi khách không biết lịch đã được xác nhận.

Tất cả chính sách đặt lịch, trạng thái và số đo trong bài là **thiết kế minh họa**, không phải tiêu chuẩn API có sẵn.

### 4.2. Dữ liệu đầu vào giả định

Một cửa sổ bốn tuần:

| Dấu hiệu | Số liệu/quan sát giả định | Điều cần thận trọng |
| --- | --- | --- |
| Phiên bắt đầu luồng đặt lịch | **1.000 phiên** | Một khách có thể có nhiều phiên. |
| Phiên có lịch Confirmed trong 24 giờ | **680 phiên** | Không đồng nghĩa 680 khách duy nhất. |
| Phiên có ít nhất một lần submit | **850 phiên** | Mẫu số khác tổng phiên bắt đầu. |
| Trong các phiên đã submit, có submit lặp | **255 phiên** | Gửi lặp có thể do lỗi hoặc người dùng đổi ý. |
| Liên hệ hỗ trợ hỏi trạng thái | **150 lượt liên hệ** | Một phiên có thể tạo nhiều lượt liên hệ. |
| Lỗi đặt lịch trùng đã xác minh | **2 sự cố** | Mức nghiêm trọng quan trọng hơn tỷ lệ nhỏ. |
| Khách trả lời khảo sát cho rằng Pending là “đã lỗi” | **12/20 người** | Mẫu nhỏ và có thiên lệch chọn mẫu. |
| Phàn nàn phổ biến | “Không biết đã đặt thành công chưa.” | Chưa chứng minh SMS là phương án tối ưu. |

Một số tỷ lệ đầu kỳ:

\[
\text{Tỷ lệ Confirmed trong 24h}=\frac{680}{1000}\times100\%=68\%
\]

\[
\text{Tỷ lệ phiên submit lặp trong phiên đã submit}=\frac{255}{850}\times100\%=30\%
\]

\[
\text{Lượt hỗ trợ trên 100 phiên bắt đầu}=\frac{150}{1000}\times100=15
\]

**15 lượt liên hệ/100 phiên** là một **rate**, không tự là “15% khách phải gọi”, vì một phiên có thể tạo nhiều lượt liên hệ và một khách có thể có nhiều phiên.

### 4.3. Các đề xuất đang cạnh tranh

Stakeholder đưa ra:

1. Gửi SMS sau mỗi lần bấm Đặt lịch.
2. Thêm nút **Thử lại** khi request chậm.
3. Hiển thị trạng thái và mã yêu cầu để tra cứu.
4. Xây API đối soát trạng thái với đối tác.
5. Viết lại hoàn toàn Booking Service.
6. Thay đổi nội dung hiển thị Pending và kiểm tra khả năng hiểu.
7. Bổ sung test chống gửi lặp và điều kiện cạnh tranh.
8. Cho khách tự đổi lịch đã Confirmed.

Không nên coi **tất cả đề xuất đều có giá trị ngang nhau** hoặc bắt buộc làm theo thứ tự người nói. Ta cần chuyển từ **danh sách giải pháp** sang **giả thuyết về vấn đề và giá trị**.

### 4.4. Hai điều không thể đem thử tùy tiện

- Lỗi tạo lịch trùng đã xác minh có thể gây thiệt hại; cần **triage, giảm rủi ro và sửa** theo mức nghiêm trọng, không đưa vào A/B test bỏ kiểm soát.
- Không hiển thị “Confirmed” khi hệ thống chưa có **kết quả có thẩm quyền**; việc làm đẹp tỷ lệ click không biện minh cho trạng thái sai.

**Học nhanh không đồng nghĩa học bằng cách để người dùng chịu lỗi đã biết.** Những guardrails này đi xuyên suốt bài.

## 5. Diễn đạt Product Goal đủ rõ để chọn việc

### 5.1. Mẫu viết một Product Goal có thể dùng

> “Đối với [nhóm người dùng], sản phẩm sẽ giúp họ [kết quả/hành vi có giá trị] trong [bối cảnh], để [giá trị/tác động], trong khi [ranh giới quan trọng] vẫn được bảo vệ.”

Ví dụ:

> “Đối với khách đặt lịch tư vấn trên điện thoại, sản phẩm giúp họ tạo và tra cứu lịch hợp lệ với trạng thái xác nhận dễ hiểu, giảm nhu cầu gọi hỗ trợ, trong khi dữ liệu và quy tắc chống đặt trùng luôn được bảo vệ.”

**Đây là bản diễn đạt minh họa**, không phải mẫu Product Goal chính thức bắt buộc của Scrum Guide.

### 5.2. Một Product Goal có thể cần nhiều outcome

Trong ví dụ:

- **Hiệu quả:** Tăng tỷ lệ phiên có lịch Confirmed trong 24 giờ.
- **Niềm tin/hiểu trạng thái:** Giảm tỷ lệ khách hiểu nhầm Pending là thất bại.
- **Khả năng tự phục vụ:** Giảm lượt liên hệ hỗ trợ chỉ để hỏi xác nhận trên 100 phiên.
- **Chất lượng:** Không tăng lỗi tạo lịch trùng, sai trạng thái hoặc sự cố riêng tư.
- **Bền vững:** Không làm tăng workload ứng cứu hoặc rework vượt khả năng nhóm.

Các outcome **có thể xung đột**. Chẳng hạn thêm nhiều bước xác nhận giúp tránh đặt trùng nhưng có thể giảm completion vì quá phiền; dùng thuật ngữ rõ mà API không đúng vẫn gây hại. Cần thảo luận đánh đổi với chuyên gia miền và người có trách nhiệm rủi ro.

### 5.3. Chọn thước đo với mẫu số có ý nghĩa

| Tín hiệu | Định nghĩa minh họa | Cảnh báo |
| --- | --- | --- |
| **Completion rate** | Phiên bắt đầu dẫn tới booking Confirmed trong 24 giờ / tổng phiên bắt đầu. | Có thể loại trừ trường hợp không phù hợp theo quy tắc đã xác định trước. |
| **Submit-repeat rate** | Phiên đã submit có hơn một submit cho cùng yêu cầu / các phiên đã submit. | Không nhầm thao tác sửa/đổi lịch hợp lệ với gửi lặp nguy hiểm. |
| **Support contact rate** | Lượt liên hệ hỏi xác nhận / 100 phiên bắt đầu. | Là lượt liên hệ, không phải tỷ lệ khách duy nhất. |
| **State comprehension** | Người tham gia hiểu đúng Pending/Confirmed/Unknown trong tác vụ thử / số người đủ điều kiện. | Mẫu usability nhỏ giúp phát hiện vấn đề, không tự đại diện toàn dân số. |
| **Duplicate-booking incident** | Các sự cố/lịch trùng đã xác minh theo quy tắc nghiệp vụ. | Sự kiện hiếm cần test phòng ngừa, không chỉ quan sát production. |
| **Time to value** | Thời gian từ yêu cầu đủ điều kiện tới kết quả hữu ích cho khách. | Định nghĩa mốc bắt đầu/kết thúc rõ và xem độ trễ ngoài code. |

**Outcome metric không cần trở thành một lời hứa chắc chắn cho từng Sprint.** Nó giúp xem Product Goal có tiến triển và quyết định nào có cơ sở.

### 5.4. Outcome không thay thế Product Goal

Một Product Goal có thể tồn tại qua nhiều vòng cải tiến; một outcome metric có thể cần sửa nếu cách thu thập sai hoặc hành vi người dùng thay đổi. Không nên chỉ chạy theo chỉ số bằng cách:

- Giảm mẫu số cho đẹp.
- Tự coi trạng thái Pending là Confirmed.
- Bỏ những phiên thất bại khỏi phép đo.
- Đếm số email gửi thay vì khách hiểu kết quả.
- Tăng tính năng phụ nhưng không cải thiện khả năng đặt lịch.

**Đo điều mang ý nghĩa cho người dùng, giữ nguyên định nghĩa khi so trước–sau và công khai mọi thay đổi.**

## 6. Từ Product Goal tới bản đồ vấn đề và cơ hội

### 6.1. Đừng đi thẳng từ mục tiêu tới tính năng

Một cách nhảy bước thường gặp:

~~~text
Product Goal: "Khách ít phải gọi hỗ trợ"
               |
               v
    Ý tưởng: "Phải thêm SMS"
               |
               v
       Xây SMS cho mọi khách
~~~

Điều còn thiếu là câu hỏi: **“Khách gọi vì sao?”** Nếu nguyên nhân là trạng thái sai, SMS có thể chỉ **phát tán trạng thái sai qua thêm một kênh**. Nếu khách không có điện thoại nhận SMS, giải pháp này có thể bỏ sót họ. Nếu khách cần chứng cứ mã đặt lịch, một trang tra cứu có thể phù hợp hơn.

Hướng suy nghĩ tốt hơn:

~~~text
Product Goal
  └─ Outcome: Khách tự xác minh được kết quả đặt lịch
       ├─ Vấn đề: Không hiểu Pending
       │   ├─ Giả thuyết: Giải thích trạng thái rõ hơn
       │   └─ Giả thuyết: Cung cấp mã tra cứu và trạng thái cập nhật
       ├─ Vấn đề: API timeout, không rõ kết quả
       │   ├─ Giả thuyết kỹ thuật: Có thể đối soát trạng thái
       │   └─ Giả thuyết: Hiển thị Unknown an toàn và bước tiếp
       └─ Vấn đề: Gửi lặp do chờ lâu
           ├─ Giả thuyết: Phản hồi tiến trình giảm submit lặp
           └─ Rủi ro phải xử lý: Idempotency và bất biến không đặt trùng
~~~

**Một vấn đề có thể có nhiều giải pháp; một giải pháp có thể giải quyết nhiều vấn đề; không cần xây hết để học.**

### 6.2. Thu bằng chứng bằng nhiều nguồn

| Nguồn | Có thể giúp hiểu gì? | Giới hạn |
| --- | --- | --- |
| **Phỏng vấn khách** | Ngôn ngữ khách dùng, cách họ hiểu trạng thái, lý do cần hỗ trợ. | Ký ức và lời nói không luôn khớp hành vi. |
| **Usability test theo tác vụ** | Khách có thể tự tra cứu và hiểu Pending/Confirmed không? | Mẫu nhỏ; phiên có người quan sát có thể khác sử dụng thật. |
| **Dữ liệu hành vi có kiểm soát** | Đường rời bỏ, gửi lặp, trạng thái phản hồi, thời gian xử lý. | Cần định nghĩa event, bảo vệ dữ liệu, không suy nguyên nhân từ click. |
| **Log kỹ thuật** | Timeout, retry, lỗi tích hợp, idempotency key, độ trễ. | Log không tự cho biết cảm xúc/nhu cầu người dùng. |
| **Support tickets** | Vấn đề lặp lại, hậu quả khách đang chịu, ngôn ngữ phản hồi. | Chỉ phản ánh người liên hệ, có thiên lệch chọn mẫu. |
| **Stakeholder/đối tác** | Ràng buộc kinh doanh, API, chính sách, nghĩa vụ. | Có thể đưa giải pháp trước vấn đề và ưu tiên theo chức năng riêng. |
| **Kiểm thử kỹ thuật** | Ranh giới đúng/sai của transaction, concurrency, contract. | Không chứng minh tính năng tạo giá trị người dùng. |

**Triangulation**: đối chiếu nhiều nguồn để xem cùng một vấn đề có biểu hiện nhất quán không. Không cần đủ mọi nguồn trước mỗi quyết định nhỏ, nhưng khi tác động lớn hoặc rủi ro cao, nên nâng chất lượng bằng chứng.

### 6.3. Opportunity map có thứ tự bằng chứng

| ID | Vấn đề/cơ hội | Dấu hiệu hiện có | Điều chưa biết | Hướng thử đầu tiên |
| --- | --- | --- | --- | --- |
| **O1** | Khách hiểu nhầm trạng thái Pending. | 12/20 người thử hiểu sai; support có cuộc gọi hỏi trạng thái. | Cách diễn đạt nào dễ hiểu? Khác biệt theo nhóm khách? | Usability test nội dung và trạng thái. |
| **O2** | Khách không thể tra cứu sau khi rời trang. | Phản ánh hỗ trợ và phiên rời bỏ. | Mã yêu cầu/link tra cứu có giảm gọi không? | Prototype và lát cắt tra cứu cơ bản. |
| **O3** | API timeout gây kết quả Unknown. | Log timeout, tình huống kỹ thuật. | Đối tác hỗ trợ tra cứu/idempotency không? | Spike hợp đồng trong sandbox. |
| **O4** | Submit lặp và lỗi đặt trùng. | 30% phiên đã submit có gửi lặp; 2 sự cố đặt trùng. | Gửi lặp nào hợp lệ? Transaction nào có vấn đề? | Ứng cứu/sửa lỗi an toàn, test cạnh tranh; sau đó thử UX. |
| **O5** | Khách muốn đổi lịch tự phục vụ. | Một số đề nghị qua support. | Nhóm nào cần nhất? Chính sách đổi phí thế nào? | Phỏng vấn, kiểm tra chính sách và story map. |

**O4 có phần rủi ro đã biết**: việc giảm thiệt hại và sửa lỗi theo mức nghiêm trọng **không phải giả thuyết thị trường được phép chờ đo thêm**. Các giả thuyết UX còn lại có thể được kiểm chứng theo thứ tự phù hợp.

### 6.4. Đừng đồng nhất số người phàn nàn với thứ tự ưu tiên

Một tình huống rủi ro dữ liệu có thể ảnh hưởng rất ít người nhưng nghiêm trọng, trong khi một yêu cầu thẩm mỹ có nhiều người thích nhưng không giúp Product Goal. Để sắp thứ tự **opportunities**, hãy hỏi:

- **Kết quả mong muốn nào bị cản?** Mức tác động nếu không xử lý?
- **Bằng chứng hiện tại mạnh hay yếu?** Có thiên lệch mẫu không?
- **Chi phí trì hoãn** là gì, có hạn thực hay mong muốn?
- **Rủi ro an toàn** có bắt buộc phải xử lý riêng không?
- **Chi phí học và chi phí triển khai** ra sao?
- **Phụ thuộc** nào khiến một bước nhỏ mở khóa nhiều lựa chọn?

Các câu hỏi này giúp chọn **vấn đề đáng giải**, không ép tạo một bảng điểm chính xác giả.

### 6.5. Sơ đồ quan hệ outcome – opportunity – solution

~~~mermaid
flowchart LR
    G["Product Goal: đặt lịch tin cậy"] --> M1["Outcome: tỷ lệ Confirmed"]
    G --> M2["Outcome: ít liên hệ hỏi trạng thái"]
    M1 --> O1["O1: không hiểu Pending"]
    M2 --> O1
    M2 --> O2["O2: không tra cứu được"]
    M1 --> O3["O3: timeout và submit lặp"]
    O1 --> S1["S1: nội dung/trạng thái rõ"]
    O2 --> S2["S2: mã yêu cầu + trang tra cứu"]
    O3 --> S3["S3: idempotency + đối soát"]
    O1 --> S2
~~~

Sơ đồ chỉ là **bản đồ những giả định liên hệ**, chưa là kết quả nhân quả đã chứng minh. Từng nhánh có thể bị bỏ, đổi hoặc chia khi học thêm.

## 7. Biến cơ hội thành các giả thuyết rõ và có thể bác bỏ

### 7.1. Bốn nhóm giả thuyết thường cần

| Loại | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị (value)** | Khách có thực sự cần và được lợi không? | Khách sẽ dùng tính năng tra cứu thay vì gọi hỗ trợ. |
| **Khả năng sử dụng (usability)** | Khách có hiểu và thao tác được không? | Khách hiểu “Đang xác nhận” không đồng nghĩa “Thất bại”. |
| **Khả thi kỹ thuật (feasibility)** | Có thực hiện an toàn với hệ thống/phụ thuộc hiện tại không? | Có thể đối soát kết quả sau timeout mà không tạo lịch trùng. |
| **Khả năng vận hành/khả năng tồn tại (viability)** | Có phù hợp chi phí, chính sách, nguồn lực và nghĩa vụ không? | Chi phí truy vấn trạng thái/đối tác và hỗ trợ ở mức chấp nhận được. |

Một feature có thể **hấp dẫn và dễ dùng nhưng chưa khả thi an toàn**. Hoặc có thể dễ xây mà **không ai cần**. Cần giảm những bất định quan trọng trước khi đầu tư lớn.

### 7.2. Mẫu giả thuyết hành vi

> “Chúng tôi tin rằng **[nhóm người dùng]** gặp **[vấn đề]**. Nếu **[can thiệp]**, thì **[kết quả quan sát được]** sẽ **[thay đổi theo hướng dự đoán]**, vì **[cơ chế]**. Chúng tôi sẽ kiểm tra bằng **[nguồn bằng chứng/cửa sổ]** và xem lại nếu **[kết quả bác bỏ/guardrail]**.”

Ví dụ:

> “Chúng tôi tin rằng khách gặp mạng chậm không gửi lặp chủ yếu vì họ muốn đặt thêm lịch, mà vì không biết request đầu đã được tiếp nhận. Nếu UI hiển thị mã yêu cầu và trạng thái Pending có thể tra cứu, tỷ lệ phiên submit lặp sẽ giảm trong nhóm đủ điều kiện, vì khách có cách xác nhận tiến trình mà không gửi lại. Chúng tôi sẽ kiểm tra khả năng hiểu qua usability test trước, rồi xem dữ liệu sử dụng trong một pilot an toàn; nếu khách vẫn hiểu sai hoặc lỗi đặt trùng tăng, phải sửa cách làm.”

Đây là **một giả thuyết**, chưa phải một kết luận về nguyên nhân của 30% submit lặp.

### 7.3. Ví dụ các hypothesis cards

| ID | Giả thuyết | Bằng chứng nhanh cần lấy | Điều có thể bác bỏ |
| --- | --- | --- | --- |
| **H1** | Ngôn ngữ Pending rõ giúp khách hiểu đúng. | Thử tác vụ với hai cách diễn đạt và giải thích của người dùng. | Nhiều người vẫn nghĩ yêu cầu đã thất bại hoặc đã Confirmed. |
| **H2** | Mã tra cứu giúp giảm gửi lặp và gọi tổng đài. | Prototype, pilot giới hạn, submit-repeat/contact rate. | Không ai dùng tra cứu, tỷ lệ gọi không đổi với cách đo đáng tin. |
| **H3** | Đối tác hỗ trợ idempotency hoặc truy vấn trạng thái đủ an toàn. | Contract/API sandbox test, timeout/retry. | Hợp đồng không có khả năng cần thiết hoặc sai khác thực tế. |
| **H4** | Đổi lịch đơn không phí có giá trị đủ để làm trước SMS. | Phân tích yêu cầu support, phỏng vấn, test willingness/usage. | Khách ít dùng hoặc rủi ro/chính sách vượt lợi ích. |
| **H5** | Test concurrent booking mới bắt được lỗi trước release. | Test đỏ/xanh với trường hợp cạnh tranh và transaction thực. | Test không phát hiện đường lỗi hoặc dữ liệu vẫn bất nhất. |

**H5 không thay việc sửa bug đã biết.** Kiểm thử và sửa lỗi là trách nhiệm chất lượng; giả thuyết H5 kiểm tra **hiệu lực một biện pháp phòng ngừa**.

### 7.4. Giả thuyết phải có phạm vi, không phải “mọi khách đều…”

Khách mới đặt lần đầu có thể cần giải thích nhiều hơn khách đặt thường xuyên. Khách dùng mạng yếu có thể gặp timeout nhiều hơn khách dùng Wi-Fi ổn định. Hãy nói rõ:

- Đối tượng nào: khách mới, khách quay lại, người dùng một khu vực/dịch vụ?
- Tình huống nào: mạng chậm, request Pending, yêu cầu bị từ chối?
- Kênh nào: web, mobile, email, support?
- Cửa sổ đo nào: 24 giờ, 7 ngày, thời gian tới lịch diễn ra?
- Ngoại lệ nào: người dùng tự thay đổi dịch vụ hoặc gửi yêu cầu mới hợp lệ?

**Không cần phân khúc cực nhỏ để luôn tạo kết quả đẹp**; phân đoạn phải có ý nghĩa nghiệp vụ và được nêu trước khi phân tích khi có thể.

### 7.5. Giả thuyết giá trị và giả thuyết kỹ thuật có thể nối tiếp nhau

Trước khi xây tra cứu trạng thái, nhóm có thể cần hai câu hỏi:

1. **Khách có thể dùng trang tra cứu và hiểu trạng thái không?** → Prototype/usability.
2. **Backend có biết trạng thái chính xác sau timeout không?** → Spike/test API đối tác.

Nếu (2) không đạt, không nên phát hành UI “Confirmed” chỉ vì (1) có tín hiệu tốt. Cần giải quyết **nguồn sự thật trạng thái**, hoặc điều chỉnh trải nghiệm để biểu diễn **Unknown/Pending** trung thực.

### 7.6. Giả thuyết không phải promise về hiệu quả

Một ngưỡng như “giảm 15% submit lặp” có thể là **mức tác động tối thiểu nhóm coi đáng đầu tư** khi có baseline đủ tin. Không nên viết “phải giảm 15%, nếu không nhóm không Agile” hoặc coi một thí nghiệm nhỏ tự chứng minh hiệu quả thống kê.

Nếu kết quả không phù hợp dự đoán, **đó là thông tin để đổi quyết định**. Đừng thay định nghĩa metric sau pilot để luôn báo “thành công”.

## 8. Chọn bằng chứng nhỏ nhất có ích trước khi xây nhiều

### 8.1. Mỗi bất định cần một phép thử phù hợp

| Bất định | Phép thử có thể chọn | Đầu ra mong muốn | Không nên kết luận |
| --- | --- | --- | --- |
| Khách hiểu chữ Pending không? | Usability test với bản mẫu nội dung và tác vụ cụ thể. | Các trường hợp hiểu đúng/sai, ngôn ngữ người dùng. | “Mọi khách đều hiểu” từ 5 người thử. |
| Khách cần mã tra cứu? | Prototype có hướng dẫn dùng và ghi hành vi/thắc mắc. | Cơ chế dùng được không, rào cản gì. | Tỷ lệ sử dụng thật đã được chứng minh. |
| API đối tác trả gì khi timeout? | Spike có timebox, thử trong sandbox và xem contract. | Khả năng retry, tra cứu, trạng thái và giới hạn. | Production luôn giống sandbox 100%. |
| Có tạo lịch trùng khi gửi hai request? | Test cạnh tranh/transaction/constraint có chủ đích. | Bất biến được thực thi và có test hồi quy. | Không bao giờ có lỗi mới chỉ vì một test pass. |
| Tra cứu trạng thái có giảm gọi hỗ trợ? | Pilot với Increment đủ chất lượng và đo theo phiên. | Tín hiệu outcome và guardrails sau sử dụng thật. | Nhân quả chắc chắn nếu chỉ đo trước–sau. |
| SMS có đáng ưu tiên? | Phỏng vấn, ước lượng chi phí, khảo sát nhu cầu/kênh. | Quyết định giữ/hạ/loại ý tưởng. | “Nhiều người bấm thích” đồng nghĩa trả được chi phí lâu dài. |

**Đường thử cần phù hợp câu hỏi.** Prototype không kiểm chứng an toàn transaction; test transaction không chứng minh người dùng hiểu UI.

### 8.2. Một experiment canvas gọn

~~~text
HYPOTHESIS ID:
  Nhóm người dùng / bối cảnh:
  Vấn đề, bằng chứng ban đầu:
  Giả thuyết và cơ chế:
  Điều chưa biết lớn nhất:

TEST:
  Phương pháp: interview / prototype / spike / Increment nhỏ / pilot...
  Phạm vi, thời gian và người tham gia:
  Điều được giữ nguyên:
  Bằng chứng cần thu:
  Điều kiện bác bỏ / giới hạn suy luận:

QUALITY AND SAFETY:
  Dữ liệu/đối tượng chịu tác động:
  Guardrails, người có quyền quyết định/dừng:
  Incident path:

DECISION:
  Giữ, sửa, bỏ, học thêm:
  Product Backlog bị ảnh hưởng thế nào:
  Khi nào xem lại:
~~~

Không cần biến canvas thành một hồ sơ 20 trang cho mọi ý tưởng. Nó giúp **người học không nhảy qua câu hỏi “Điều gì khiến chúng ta đổi ý?”**.

### 8.3. Spike cần có câu hỏi và timebox

Một spike giả định:

~~~text
ID: SP-01
Câu hỏi: API đối tác có nhận cùng idempotency key qua timeout/retry không?
Timebox: 2 ngày làm việc với sandbox, nếu tài khoản khả dụng.
Bằng chứng cần: contract, thử request gửi lặp, timeout, tra cứu trạng thái.
Đầu ra: lựa chọn kỹ thuật, giới hạn chưa giải quyết, rủi ro, PBI cần sửa.
Không bao gồm: xây xong luồng đổi lịch cho khách production.
Khi quá timebox: báo điều chưa biết và đề nghị quyết định tiếp, không kéo vô hạn.
~~~

**Không nên đánh dấu một feature của khách Done chỉ vì spike hoàn tất.** Spike tạo **kiến thức/giảm rủi ro**; việc tạo Increment có thể còn phải làm.

### 8.4. Prototype không nhất thiết là code bỏ đi hoặc sản phẩm thật

Nhóm có thể dùng:

- Bản phác giấy/clickable mock để thử khả năng hiểu.
- Trang nội bộ với dữ liệu giả để thử quy tắc trình bày.
- API sandbox và test contract để kiểm chứng kỹ thuật.
- Một lát cắt thực tế rất nhỏ nếu cần quan sát hành vi dùng thật.

**Ranh giới phải công khai:** Demo có thể cho thấy UI; **chỉ Increment đạt DoD và điều kiện release** mới đủ cơ sở dùng trong môi trường phù hợp. Không được dùng prototype dựa dữ liệu giả để tuyên bố tính năng an toàn cho production.

### 8.5. Dừng nghiên cứu khi đã có quyết định tốt hơn

Không cần phỏng vấn 100 người nếu đã phát hiện một lỗi usability rõ và chi phí sửa nhỏ, rủi ro thấp. Ngược lại, không đủ cơ sở mở rộng một tính năng liên quan dữ liệu nhạy cảm chỉ vì 3 người trong nhóm nội bộ thích.

Câu hỏi quyết định:

> “Bằng chứng hiện tại đã đủ cho **quyết định và mức rủi ro cụ thể này** chưa? Nếu chưa, **thử nghiệm tiếp theo nào giảm bất định có giá trị nhất với chi phí và phơi nhiễm thấp**?”

Đây là cách cân bằng **học nhanh** với **độ tin cậy quyết định**.

## 9. Thiết kế phép đo cho giả thuyết và phần tăng trưởng

### 9.1. Một thước đo tốt cần contract

Ví dụ đo gửi lặp:

~~~yaml
metric: repeat_submit_session_rate
purpose: "Kiểm tra hành vi gửi lại cùng yêu cầu đặt lịch"
unit: "Tỷ lệ phần trăm các phiên đã submit"
numerator: "Phiên có >=2 submit cùng một yêu cầu đặt lịch"
denominator: "Tổng phiên có ít nhất một submit đủ điều kiện"
window: "Bốn tuần, theo tuần và phân đoạn mạng chậm khi có thể"
guardrails:
  - "Không tăng lịch Confirmed trùng"
  - "Không tăng tỷ lệ thất bại/Unknown không được xử lý"
  - "Không tăng liên hệ hỗ trợ do mất trạng thái"
data_rules:
  - "Ẩn danh/tối thiểu hóa thông tin phù hợp"
  - "Không coi hai yêu cầu khác nhau hợp lệ là gửi lặp"
  - "Giữ cùng định nghĩa khi so trước và sau"
~~~

Nếu ứng dụng không có khái niệm **phiên** đáng tin, nhóm phải xây định nghĩa hoặc dùng mẫu số khác rồi **không so trực tiếp** với con số cũ. Một metric có phép tính đúng nhưng **đo sai hiện tượng** vẫn nguy hiểm.

### 9.2. Đo primary, supporting và guardrails

| Nhóm đo | Ví dụ | Mục đích |
| --- | --- | --- |
| **Primary outcome** | Tỷ lệ phiên có lịch Confirmed trong 24h; mức tự tra cứu thành công. | Xem giá trị người dùng. |
| **Supporting/diagnostic** | Submit-repeat, hiểu trạng thái, thời gian từ Pending tới kết quả. | Giải thích cơ chế có thể tạo outcome. |
| **Flow** | Cycle time PBI, throughput, WIP, work item age, blocked duration. | Nhìn khả năng giao giá trị, không chỉ ý tưởng. |
| **Quality guardrails** | Lỗi đặt trùng, sai trạng thái, incident, lỗi hồi quy, quyền dữ liệu. | Ngăn tốc độ hoặc conversion đánh đổi an toàn. |
| **Sustainability** | Tải trực, overtime, công việc bị ngắt, chất lượng CI. | Tránh lợi ích ngắn hạn làm hệ thống suy yếu. |

**Không nên chọn 25 chỉ số “chính”**. Mỗi giả thuyết cần một hoặc vài tín hiệu quyết định, các chỉ số khác giúp đọc đúng bối cảnh và rủi ro.

### 9.3. Theo dõi người dùng thực và điều kiện ngoài sản phẩm

Nếu đối tác lịch nghỉ bảo trì vào cuối tuần, tỷ lệ Confirmed có thể giảm dù UI tốt hơn. Nếu chiến dịch marketing thu hút nhiều người dùng mới, tổng số cuộc gọi hỗ trợ có thể tăng dù **tỷ lệ trên 100 phiên** giảm.

Nên ghi:

- Thời gian và nguồn dữ liệu.
- Cơ cấu khách mới/quay lại, thiết bị/kết nối.
- Những thay đổi chính sách hoặc nhà cung cấp.
- Sự cố và thay đổi năng lực ứng cứu.
- Tính đầy đủ của event logging.
- Những can thiệp khác cùng thời điểm.

**Báo trước–sau không tự chứng minh nguyên nhân.** Có thể có tín hiệu tốt nhưng cần kiểm chứng tiếp.

### 9.4. Điều kiện an toàn không thể bị biến thành ngưỡng “chấp nhận lỗi”

Với dữ liệu đặt lịch, **lỗi tạo trùng đã biết** phải được xử lý theo chính sách chất lượng, không đặt thử nghiệm “cho phép tối đa ba khách bị trùng để xem conversion”. Những mức ngưỡng kỹ thuật (latency, error budgets, rollout) nếu dùng phải phù hợp rủi ro và được người có thẩm quyền phê duyệt; không tự lấy ví dụ trong bài làm chính sách production.

### 9.5. Đặt kỳ vọng thống kê đúng mức

Nếu trong pilot chỉ có 20 phiên, tỷ lệ completion tăng từ 12/20 lên 15/20 **có thể chỉ là biến động ngẫu nhiên hoặc khác nhóm khách**. Nếu một nhóm thay cả UI, API và quy tắc dữ liệu, rất khó quy mọi thay đổi cho một thông báo.

Trong những quyết định cần độ tin cậy cao, cần thiết kế so sánh phù hợp, lượng mẫu và phân tích tính bất định. Với các cải tiến ít rủi ro, có thể dùng bằng chứng định tính và pilot nhỏ để **quyết định thử tiếp**, nhưng phải gọi đúng mức kết luận.

## 10. Từ giả thuyết tới Story Map và những lát cắt đầu-cuối

### 10.1. Story map nhìn hành trình trước khi nhìn ticket

Một bản đồ hành trình đơn giản:

~~~text
HÀNH TRÌNH KHÁCH
  Tìm chuyên gia -> Chọn giờ -> Gửi yêu cầu -> Biết kết quả -> Quản lý lịch
          |             |              |               |              |
     Đúng dịch vụ   Giờ hợp lệ    Xử lý an toàn    Hiểu Pending    Xem lịch
     Kết quả tìm    Múi giờ       Gửi lặp         Mã tra cứu      Đổi lịch
     Khả năng đọc   Còn chỗ       Timeout         Unknown         Hủy lịch

LÁT CẮT 0 - An toàn nền tảng:
  Không tạo hai lịch Confirmed xung đột; xử lý gửi lặp theo chính sách.

LÁT CẮT 1 - Trạng thái rõ sau gửi:
  Khách gửi một yêu cầu hợp lệ và biết Pending / Confirmed / Rejected đúng.

LÁT CẮT 2 - Tra cứu yêu cầu đã gửi:
  Khách có mã yêu cầu, có thể xem trạng thái mà không submit lại.

LÁT CẮT 3 - Đối soát kết quả chưa rõ:
  Khi timeout, khách thấy trạng thái trung thực và có đường xác minh tiếp.

LÁT CẮT 4 - Tự đổi lịch trường hợp cơ bản:
  Khách đổi một lịch đơn không phí khi còn chỗ, với bảo vệ transaction.
~~~

**Đây là một bản đồ lát cắt minh họa, không phải thứ tự phát hành đã được xác minh**. Ví dụ lát cắt 1 có thể phụ thuộc cách backend xử lý Unknown; phải kiểm tra các ràng buộc trước khi gọi nó đủ điều kiện dùng thật.

### 10.2. Vertical slice thay cho chia ngang theo tầng kỹ thuật

**Chia ngang dễ tạo bàn giao:**

~~~text
Team A: toàn bộ UI đổi lịch (chạy mock)
Team B: toàn bộ Booking API
Team C: toàn bộ tích hợp đối tác
=> Cuối kỳ mới ghép, chưa có hành vi đầu-cuối đạt Done.
~~~

**Chia dọc theo hành vi giá trị:**

~~~text
Slice V1: Xem trạng thái một yêu cầu hợp lệ
  UI trạng thái + API có thẩm quyền + dữ liệu + quyền truy cập + test

Slice V2: Tra cứu lại bằng mã yêu cầu
  UI tra cứu + endpoint/query + chính sách quyền + test

Slice V3: Đối soát trường hợp timeout
  Cơ chế kỹ thuật + trạng thái Unknown/Pending + UX bước tiếp + test
~~~

Mỗi lát cắt có thể thay đổi nhiều tầng nhưng **hoàn tất một hành vi có ý nghĩa**. Không nhất thiết mỗi lát cắt được phát hành riêng nếu còn phụ thuộc an toàn; nhưng nó giúp **tích hợp và kiểm tra sớm** hơn chia từng tầng một cách cứng nhắc.

### 10.3. Bảy cách chia lát cắt thực dụng

| Kỹ thuật chia | Một lát cắt nhỏ trước | Phần mở rộng sau |
| --- | --- | --- |
| **Theo bước workflow** | Chỉ xem trạng thái sau khi gửi yêu cầu. | Tra cứu sau khi rời trang, nhắc lịch, đổi/hủy. |
| **Theo quy tắc nghiệp vụ** | Lịch đơn, không phí, trong thời hạn rõ. | Đổi sát giờ, nhiều chuyên gia, trường hợp hoàn phí. |
| **Theo loại dữ liệu** | Một loại dịch vụ và khung giờ phổ biến. | Dịch vụ/đối tác đặc thù có quy tắc khác. |
| **Theo vai trò/người dùng** | Khách đặt lịch cho chính mình. | Người đặt hộ hoặc quản trị viên, nếu có quyền phù hợp. |
| **Theo tình huống lỗi** | Luồng hợp lệ với trạng thái chính xác. | Timeout, không đồng bộ, recovery — **không trì hoãn phần an toàn bắt buộc**. |
| **Theo kênh** | Tra cứu trên web/mobile đang dùng chính. | Email/SMS/push sau khi xác minh nhu cầu và quyền riêng tư. |
| **Theo phạm vi tích hợp** | Một đối tác có contract đáng tin. | Đối tác khác với API và policy riêng. |

**Điều kiện:** Phạm vi nhỏ phải vẫn **đúng và an toàn**. Không thể chọn “happy path trước, để lỗi trùng production quý sau” nếu happy path cũng chịu rủi ro concurrent requests.

### 10.4. Một slice không nhất thiết là một user story cố định

Một lát cắt có thể tương ứng:

- Một PBI có acceptance criteria đủ rõ.
- Một vài PBI gắn chung mục tiêu nhỏ nếu mỗi phần đã đủ DoD và có ý nghĩa.
- Một spike giảm rủi ro trước khi PBI khả thi.
- Một thay đổi kỹ thuật bảo vệ bất biến cần làm trước hoặc cùng lát cắt.

**Không đếm số story là số Increment.** Trong Scrum, một Increment là phần phần mềm **có thể dùng, tích hợp và đạt Definition of Done**. Có thể có nhiều Increment trong một Sprint, không nhất thiết trùng một story hay một release.

### 10.5. Kiểm tra một lát cắt bằng năm câu hỏi

1. **Ai được lợi hoặc tránh rủi ro?** Có thể chỉ rõ bối cảnh?
2. **Hành vi end-to-end nào mới có?** Không chỉ “một API đã được tạo”.
3. **Giả thuyết nào được kiểm chứng?** Dữ liệu nào có thể quan sát?
4. **Có bảo vệ chất lượng và bất biến?** Test, quyền, dữ liệu và vận hành thế nào?
5. **Nếu xong, có lựa chọn tiếp theo rõ?** Giữ, mở rộng, đổi hoặc dừng?

Nếu không trả lời được, có thể item đang là **task kỹ thuật**, **một feature quá lớn** hoặc **thử nghiệm chưa có tiêu chí kết thúc**.

## 11. Viết Product Backlog Items và user stories từ một lát cắt

### 11.1. User story là công cụ giao tiếp, không phải hợp đồng đầy đủ

Một mẫu thường dùng:

> “Là **[đối tượng]**, tôi muốn **[khả năng]** để **[giá trị]**.”

Ví dụ cho lát cắt tra cứu:

> “Là **khách đã gửi yêu cầu đặt lịch**, tôi muốn **xem trạng thái mới nhất bằng mã yêu cầu** để **biết có cần làm thêm bước nào hay không mà không gửi lại yêu cầu**.”

Câu chuyện giúp các bên nói về **người dùng, hành vi và lý do**, nhưng không giải quyết tự động:

- Chính sách trạng thái sau timeout.
- Quyền ai được tra cứu yêu cầu.
- Khi nào có mã tra cứu và mã còn hiệu lực.
- Trường hợp mã không hợp lệ hoặc không tìm thấy.
- Dữ liệu nhạy cảm được hiển thị tới đâu.
- Test tích hợp và điều kiện được coi là Done.

**User story là lời mời cùng làm rõ** qua ví dụ, điều kiện và phản hồi, không phải chỗ để bỏ hết tiêu chuẩn an toàn vào một câu.

### 11.2. Product Backlog không chỉ có user stories

Một PBI có thể là:

| Loại | Ví dụ | Bằng chứng/đầu ra mong muốn |
| --- | --- | --- |
| **Giá trị người dùng** | Tra cứu trạng thái bằng mã yêu cầu. | Hành vi đầu-cuối đạt tiêu chí và DoD. |
| **Lỗi** | Request lặp có thể tạo lịch Confirmed trùng. | Sửa đường lỗi, test hồi quy và đối soát khi cần. |
| **Rủi ro kỹ thuật** | Xác minh API đối tác xử lý timeout/retry. | Kết luận khả thi, giới hạn và quyết định thiết kế. |
| **Cải tiến chất lượng** | Tự động kiểm thử concurrency trong CI. | Test chạy đáng tin và bảo vệ bất biến. |
| **Discovery** | Thử cách diễn đạt Pending với khách. | Bằng chứng hiểu đúng/sai và thay đổi backlog. |
| **Khả năng vận hành** | Thêm quan sát trạng thái Unknown an toàn. | Có thể nhận biết và xử lý trường hợp cần đối soát. |

Không cần viết một yêu cầu như “Là hệ thống, tôi muốn chạy CI để tôi vui hơn” chỉ để hợp một mẫu story. **Diễn đạt rõ vấn đề và giá trị cần bảo vệ** có ích hơn.

### 11.3. INVEST là heuristics, không phải kiểm tra hình thức

Một user story thường được đánh giá qua **INVEST**:

- **Independent (tương đối độc lập):** Giảm phụ thuộc không cần thiết, có thể sắp thứ tự linh hoạt.
- **Negotiable:** Phạm vi được trao đổi, không khóa chi tiết sớm.
- **Valuable:** Có giá trị người dùng/kinh doanh hoặc giảm rủi ro có ý nghĩa.
- **Estimable:** Có thể hiểu đủ để dự báo trong bối cảnh, không đòi chính xác tuyệt đối.
- **Small:** Vừa đủ nhỏ để hoàn tất và nhận phản hồi sớm.
- **Testable:** Có cách kiểm chứng hành vi hoặc kết quả.

**Không phải mọi PBI đều hoàn toàn Independent**: chống trùng và tra cứu có thể phụ thuộc hợp đồng dữ liệu chung. Mục tiêu là **làm lộ và giảm phụ thuộc**, không giả lập sự độc lập bằng cách tách task theo phòng ban.

### 11.4. Viết story ở các mức khác nhau

**Epic quá lớn:**

> “Là khách, tôi muốn tự quản lý mọi lịch tư vấn trong mọi trường hợp.”

**Lát cắt phù hợp hơn:**

> “Là khách có một lịch Confirmed, tôi muốn xem thời gian và trạng thái của lịch đó để biết khi nào cần tham gia tư vấn.”

**Một bước tiếp theo:**

> “Là khách có lịch Confirmed còn trong thời hạn cho phép, tôi muốn đổi sang một giờ còn trống để tự điều chỉnh lịch mà không gọi hỗ trợ.”

Các lát cắt khác nhau **về điều kiện và kết quả**. Nếu một story vẫn cần cả nhóm làm nhiều tuần và không thể tích hợp sớm, tiếp tục chia theo **nhánh workflow, quy tắc, đối tượng, trạng thái hoặc dữ liệu**.

### 11.5. Một mẫu PBI giàu bối cảnh nhưng không thừa giấy tờ

~~~text
PBI ID: BOOK-STATE-01
Mục tiêu liên quan:
  Khách đặt lịch đáng tin và tự xác minh trạng thái.
Vấn đề / đối tượng:
  Khách đã gửi yêu cầu không biết kết quả khi mạng chậm.
Giá trị:
  Có thể tra cứu trạng thái mà không tạo yêu cầu mới.
Hành vi:
  Xem trạng thái qua mã yêu cầu được cấp hợp lệ.
Phạm vi lát cắt:
  Một loại lịch tư vấn, trạng thái Pending/Confirmed/Rejected/Unknown.
Chưa thuộc phạm vi:
  Đổi lịch, SMS và hoàn phí.
Bằng chứng cần:
  Tác vụ tra cứu thành công; submit-repeat/contact rate khi dùng thật.
Acceptance examples:
  Mã hợp lệ, mã sai, trạng thái chưa xác định, quyền truy cập.
Phụ thuộc:
  Hợp đồng trạng thái Booking API và chính sách tra cứu.
Chất lượng:
  Definition of Done chung, test ranh giới và quan sát lỗi.
Giả định mở:
  API đối tác có thể truy vấn lại kết quả sau timeout?
~~~

Không cần biến mọi PBI thành hồ sơ giống mẫu nếu việc nhỏ và rủi ro thấp. **Mức chi tiết nên đủ cho nhóm hiểu, quyết định và kiểm chứng**, không phải tối đa hóa số trường mô tả.

## 12. Acceptance criteria và ví dụ Given–When–Then

### 12.1. Bốn câu hỏi trước khi chọn tiêu chí

Một acceptance criterion tốt trả lời:

1. Trong **trạng thái đầu** nào của hệ thống/người dùng?
2. Khi người dùng hoặc hệ thống **thực hiện hành động** nào?
3. Kết quả **có thể quan sát/kiểm tra** nào phải xuất hiện?
4. Có **quy tắc, quyền, trạng thái, dữ liệu hoặc lỗi** nào phải được bảo vệ?

**Không chỉ dùng câu “chạy nhanh, thân thiện, không có bug”**; chúng không cho biết hành vi nào được chấp nhận.

### 12.2. Ví dụ cho tra cứu trạng thái

~~~gherkin
Feature: Khach tra cuu trang thai yeu cau dat lich

Scenario: Yeu cau dang cho xac nhan
  Given khach co mot ma yeu cau hop le o trang thai PENDING
  When khach tra cuu ma yeu cau
  Then ung dung hien "Dang xac nhan"
  And ung dung khong bao "Lich da duoc xac nhan"
  And ung dung dua ra cach xem lai trang thai an toan

Scenario: Yeu cau da duoc xac nhan
  Given mot ma yeu cau hop le co trang thai CONFIRMED co tham quyen
  When khach tra cuu ma yeu cau
  Then ung dung hien thoi gian va trang thai xac nhan phu hop
  And ung dung khong tao them yeu cau dat lich

Scenario: Khong ro ket qua sau timeout
  Given ket qua tu doi tac chua xac dinh
  When khach tra cuu ma yeu cau
  Then ung dung hien trang thai chua the ket luan
  And ung dung khong tu suy ra CONFIRMED hoac REJECTED
  And ung dung chi dan buoc tiep theo theo chinh sach doi soat

Scenario: Ma khong hop le hoac khong du quyen
  Given nguoi dung khong co quyen xem yeu cau
  When nguoi dung tra cuu ma yeu cau
  Then he thong khong tiet lo thong tin lich cua nguoi khac
  And thong bao loi khong lam ro thong tin nhay cam
~~~

Các câu Gherkin dùng tiếng Việt không dấu trong khối kỹ thuật cho dễ sao chép; đây là **ví dụ yêu cầu**. Khi tự động hóa, phải ánh xạ vào trạng thái, quyền và chính sách thực tế, không chỉ so khớp chữ.

### 12.3. Bảng trạng thái giúp bắt mâu thuẫn

| Trạng thái có thẩm quyền | Diễn đạt cho khách | Có được coi lịch đã xác nhận? | Hành động an toàn |
| --- | --- | --- | --- |
| **PENDING** | “Đang xử lý yêu cầu; chưa có kết quả cuối.” | **Không** | Xem lại bằng mã hoặc chờ thông báo phù hợp. |
| **CONFIRMED** | “Lịch đã được xác nhận.” | **Có**, nếu dữ liệu có thẩm quyền. | Xem chi tiết và bước tiếp theo hợp lệ. |
| **REJECTED** | “Yêu cầu không được chấp nhận.” | **Không** | Giải thích lý do không nhạy cảm và cách chọn yêu cầu khác. |
| **UNKNOWN** | “Chưa xác định được kết quả; đang kiểm tra.” | **Không** | Tra cứu/đối soát hoặc liên hệ hỗ trợ theo quy trình. |

**UNKNOWN là trạng thái minh họa có thể cần trong một hệ thống phân tán**, không phải quy tắc mà mọi Booking API bắt buộc phải dùng đúng tên này. Điều cốt lõi là **không đánh đồng thiếu phản hồi với thất bại hoặc thành công**.

### 12.4. Tiêu chí chấp nhận không chỉ có happy path

Trong giao dịch đặt lịch, cần xem:

- Submit lặp cùng request và idempotency key.
- Hai người cạnh tranh một slot, ở gần cùng thời điểm.
- Timeout từ đối tác **sau khi** request được chấp nhận.
- Dữ liệu quá hạn, phiên hết hiệu lực, mất quyền truy cập.
- Mã tra cứu không hợp lệ, mã không tồn tại, nhiều lần nhập sai.
- Người dùng ở múi giờ khác, thời gian đổi ngày, lịch đã bị hủy.
- Trạng thái cập nhật chậm hoặc không đồng bộ giữa các thành phần.
- Khả năng tiếp cận và thông điệp khi mạng yếu.

Không phải **mọi trường hợp hiếm phải nằm trong một story duy nhất**, nhưng những điều kiện **bắt buộc để lát cắt hiện tại an toàn** không được dời lại chỉ để đạt mục tiêu “nhỏ”.

### 12.5. Phân biệt ví dụ nghiệm thu và Definition of Done

**Acceptance criteria** của BOOK-STATE-01 có thể nói:

> “Nếu trạng thái là PENDING, UI không được hiển thị Confirmed và có đường tra cứu lại.”

**DoD chung** có thể bao gồm:

- Test tự động thiết yếu chạy đạt.
- Code được review theo tiêu chuẩn và tương thích hợp đồng.
- Thay đổi tích hợp vào sản phẩm.
- Bảo mật và quyền dữ liệu được kiểm tra phù hợp.
- Không có lỗi nghiêm trọng chưa xử lý trong phạm vi thay đổi.
- Có thể quan sát/khắc phục sự cố theo yêu cầu vận hành.

**DoD không tự quy định tiêu chí nghiệp vụ cho mọi story; acceptance criteria không thay thế tiêu chuẩn chất lượng chung.** Cả hai đều cần phù hợp, đồng thời không bắt mọi nhóm sao chép đúng checklist minh họa này.

## 13. Definition of Done, Increment, deploy, release và outcome

### 13.1. Những trạng thái thường bị gọi nhầm là “xong”

| Trạng thái | Điều đã có | Điều chưa được chứng minh |
| --- | --- | --- |
| **Task UI Done** | Giao diện chạy với mock/dữ liệu thử. | Backend có đúng, quyền và trạng thái thật có an toàn? |
| **API code merged** | Có mã nguồn trong nhánh tích hợp. | Hành vi đầu-cuối, test, vận hành đã đạt chuẩn? |
| **PBI đạt tiêu chí và DoD** | Phần việc tích hợp, chất lượng đáp ứng các điều kiện áp dụng. | Người dùng thật đã tiếp cận hoặc outcome đã cải thiện? |
| **Increment** | Phần sản phẩm có thể dùng, đáp ứng DoD và tích hợp với phần trước. | Tự động được release cho mọi khách? |
| **Deployed** | Phần mềm có mặt ở môi trường nào đó. | Có được mở cho người dùng? Có tạo giá trị? |
| **Released** | Một nhóm người dùng có thể tiếp cận tính năng phù hợp. | Có thực sự dùng, hiểu và đạt outcome không? |
| **Observed outcome** | Có bằng chứng tác động trong bối cảnh sử dụng. | Nhân quả đã chắc chắn nếu chỉ có trước–sau? |

**Done và release khác nhau.** Trong Scrum, khi một PBI đáp ứng DoD thì phần Increment đó có thể được tạo và sử dụng như một phần sản phẩm; việc phát hành có thể diễn ra trước Sprint Review nếu phù hợp. Sprint Review **không phải cổng duyệt release bắt buộc**.

### 13.2. Điều kiện về chất lượng không bị thương lượng xuống vì deadline

Theo Scrum Guide, trong Sprint **chất lượng không giảm**. Nếu một lát cắt cần bảo vệ không đặt trùng, nó không trở nên đủ điều kiện Done khi chỉ test một request đơn. Nếu chưa có khả năng đối soát timeout, phải minh bạch phạm vi và rủi ro, có thể **không phát hành luồng liên quan** cho tới khi an toàn.

**Thu hẹp phạm vi có thể đúng**; **hạ chuẩn chất lượng để “được Done” là sai**.

### 13.3. Một Increment nhỏ không đồng nghĩa thay đổi production thật nhỏ ở mọi tầng

Đôi khi một thay đổi nhỏ về UX đòi điều chỉnh giao thức và transaction lớn do kiến trúc đang coupling. Nhóm có thể:

- Dùng một **enabler kỹ thuật** để giảm phụ thuộc.
- Refactor an toàn theo bước có test.
- Làm hợp đồng API rõ trước.
- Tránh xây đầy đủ các tình huống chưa cần.
- Tích hợp thường xuyên, dùng flag nếu phù hợp với rủi ro.

**Không cắt lát bằng cách tách rời phần bảo vệ thiết yếu**. Mục tiêu là giá trị có thể kiểm tra, không phải bắt tất cả pull requests có đúng một số dòng code.

### 13.4. Feature flag giúp kiểm soát phơi nhiễm nhưng không sửa dữ liệu đã sai

Một flag có thể:

- Cho nhóm nội bộ thử giao diện trạng thái.
- Bật cho một nhóm khách đủ điều kiện sau khi đạt DoD.
- Tắt phần hiển thị mới nếu phát hiện vấn đề.

Nhưng flag **không tự đảo ngược booking đã ghi trùng, SMS đã gửi, dữ liệu đã xuất hiện ngoài quyền hoặc event đã phát tới đối tác**. Với thay đổi ghi dữ liệu, cần phương án rollback/compensation/đối soát thích hợp.

### 13.5. Khác biệt giữa Release Plan và Sprint Plan

**Release Plan** có thể nói về các đối tượng người dùng, điều kiện rollout, rủi ro và bằng chứng cần xem trước khi mở rộng. Đây là **công cụ tổ chức tùy chọn**, không phải một artifact chính thức của Scrum Guide.

**Sprint Plan/Sprint Backlog** là kế hoạch do Developers tạo để đạt Sprint Goal; nó gồm **Sprint Goal, PBI được chọn và kế hoạch thực hiện**, thích ứng theo hiểu biết mới.

Một Sprint có thể tạo nhiều Increment. Một release có thể gồm một hoặc nhiều Increment tùy mục đích và điều kiện. **Không có quy tắc “mỗi Sprint chỉ có một lần release”**.

### 13.6. Khép vòng bằng quan sát giá trị

Sau khi release:

1. Kiểm tra lỗi/sự cố và khả năng phục hồi.
2. Xác nhận telemetry đo đúng sự kiện và mẫu số.
3. Xem khách có tiếp cận và hiểu hành vi mới không.
4. Đọc feedback hỗ trợ và trường hợp không như dự đoán.
5. Cân nhắc **giữ, sửa, mở rộng hoặc dừng** theo guardrails.
6. Cập nhật Product Backlog và giả thuyết; không coi “đã ship” là kết thúc học.

**Một Increment hoàn thành là điều kiện để học từ phần mềm dùng được**, nhưng không có nghĩa product outcome tự cải thiện.

## 14. Sắp thứ tự Product Backlog theo giá trị, rủi ro và cơ hội học

### 14.1. Đừng để “Priority: High” thay thế thứ tự thực

Một Product Backlog cần giúp người tham gia biết **phần công việc nào nên được cân nhắc trước khi năng lực có hạn**. Nếu mọi hạng mục đều được gắn High, khi chỉ có một nhóm hiểu Booking transaction, xung đột vẫn chưa giải quyết.

Các căn cứ:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Giá trị và Product Goal** | PBI có góp trực tiếp vào kết quả ưu tiên không? |
| **Tác động nếu trì hoãn** | Có thiệt hại, chi phí hỗ trợ, cơ hội bị mất, nghĩa vụ thật? |
| **Rủi ro an toàn/chất lượng** | Có lỗi đã xác minh phải ứng cứu hoặc điều kiện bắt buộc? |
| **Mức bất định** | Có cần học trước khi xây lớn không? |
| **Công sức/khả năng chia nhỏ** | Có thể tạo một lát cắt hữu ích với chi phí thấp hơn? |
| **Phụ thuộc/mở khóa** | Công việc nào giúp nhiều PBI khác trở nên khả thi? |
| **Năng lực và WIP** | Người/nhóm cần thiết có thể hoàn tất thay vì bắt đầu quá nhiều? |
| **Chiến lược và thời hạn** | Có phù hợp Product Goal và deadline có hậu quả thật không? |

**Điểm số có thể hỗ trợ đối thoại, nhưng không thay trách nhiệm quyết định**. Những nghĩa vụ an toàn nghiêm trọng phải được xử lý theo chính sách riêng, không vì Reach thấp mà để dưới feature trang trí.

### 14.2. Một thứ tự ban đầu cho sản phẩm đặt lịch

| Thứ tự minh họa | ID | Hạng mục | Lý do |
| ---: | --- | --- | --- |
| **1** | **P01** | Khắc phục nguy cơ đặt trùng đã xác minh; kiểm thử concurrency/retry. | Bảo vệ dữ liệu và quyền lợi khách; có thể cần ứng cứu ngay. |
| **2** | **P02** | Spike hợp đồng timeout/idempotency của đối tác. | Giảm bất định kỹ thuật chặn nhiều giải pháp. |
| **3** | **P03** | Thử nội dung Pending/Unknown với khách phù hợp. | Chi phí học thấp, kiểm chứng hiểu trạng thái. |
| **4** | **P04** | Trạng thái có thẩm quyền và hành vi tra cứu cơ bản. | Lát cắt trực tiếp giúp Product Goal. |
| **5** | **P05** | Mã yêu cầu và tra cứu lại sau khi rời trang. | Giảm nhu cầu submit lại và gọi support. |
| **6** | **P06** | Đối soát timeout và hiển thị đường xử lý Unknown. | Điều kiện an toàn khi backend không có kết quả cuối. |
| **7** | **P07** | Phân tích phản hồi và sự kiện gửi lặp, completion, support. | Học outcome/guardrails; có thể làm song song ở phần an toàn. |
| **8** | **P08** | Tự đổi lịch trường hợp đơn giản được xác minh nhu cầu. | Giá trị tiếp theo, phụ thuộc chính sách và trạng thái. |
| **9** | **P09** | SMS xác nhận theo nhu cầu đã kiểm chứng. | Chưa có bằng chứng SMS giải quyết vấn đề gốc. |

**Không hiểu bảng là thứ tự tuyệt đối “làm P01 xong 100% mới được đọc P02”.** Triage P01 có thể chạy ngay, P02/P03 có thể học song song nếu có năng lực; P07 cần thiết để quan sát có thể bắt đầu sớm. Trật tự thể hiện **ưu tiên đánh đổi**, không phải sơ đồ Gantt bắt buộc.

### 14.3. Chi phí trì hoãn và WSJF là heuristic tùy chọn

Một cách so tương đối cho các lựa chọn đủ tương đồng:

\[
\text{WSJF}=\frac{\text{Cost of Delay tương đối}}{\text{Job Size tương đối}}
\]

Ví dụ **hoàn toàn giả định** trên một thang tương đối:

| PBI | CoD tương đối | Kích thước tương đối | WSJF minh họa |
| --- | ---: | ---: | ---: |
| **P02 — Spike timeout** | 12 | 2 | **6,0** |
| **P04 — Tra cứu trạng thái** | 18 | 6 | **3,0** |
| **P09 — SMS xác nhận** | 8 | 5 | **1,6** |

Thứ tự theo phép tính: P02, P04, P09. Nhưng P02 là **bằng chứng mở khóa giải pháp**, không chứng minh giá trị người dùng cao gấp đôi P04. P01 là **rủi ro đã xác minh**, không thể đưa xuống dưới chỉ vì không có điểm Reach.

**Scrum không bắt buộc dùng WSJF, RICE hay story points.** Chúng là công cụ tùy chọn để làm lộ giả định và so chi phí cơ hội khi thích hợp.

### 14.4. Cân bằng nghiên cứu với giao hàng

Một Product Backlog có thể bao gồm:

- Giả thuyết cần discovery hoặc prototype.
- Spike kỹ thuật có timebox.
- PBI tạo Increment dùng được.
- Lỗi và việc chất lượng bắt buộc.
- Công việc observability giúp đo outcome thật.

**Không có tỷ lệ 20% discovery/80% delivery bắt buộc**. Phân bổ năng lực phụ thuộc rủi ro, mức độ hiểu nhu cầu, chất lượng hiện tại và Product Goal.

Nếu giả thuyết giá trị rất yếu, xây cả feature lớn dễ lãng phí. Nếu đã có lỗi dữ liệu nghiêm trọng được xác minh, kéo dài nghiên cứu UX để né sửa lỗi không phù hợp. **Điều quan trọng là chọn công việc giúp quyết định hoặc tạo giá trị tiếp theo với trách nhiệm an toàn.**

### 14.5. PBI có thứ tự không đồng nghĩa mọi nhóm phải bận 100%

Nếu chỉ một người có thể kiểm tra API đối tác, mở năm PBI cần người đó có thể tăng WIP nhưng **không tăng số Increment**. Nhóm khác có thể hỗ trợ test, giảm nợ kỹ thuật đang chặn hoặc làm discovery hữu ích, nhưng không nên tạo nhiều UI chưa thể tích hợp.

**Ưu tiên hoàn tất lát cắt có giá trị**, không tối đa hóa số story Started.

## 15. Từ Product Goal tới Sprint Goal và kế hoạch giao phần nhỏ

### 15.1. Sprint Goal không phải bản copy của Product Goal

Product Goal: **“Khách tự đặt và tra cứu lịch đáng tin mà ít cần tổng đài.”**

Sprint Goal minh họa:

> “Khách gửi yêu cầu đặt lịch có thể xem trạng thái đúng và hiểu được kết quả trong một luồng tích hợp an toàn.”

Một Sprint Goal khác ở vòng sau:

> “Khách có thể tra cứu lại trạng thái bằng mã yêu cầu khi đã rời trang, không phải gửi lại thao tác đặt lịch.”

Các Sprint Goal là **mục tiêu nhỏ hỗ trợ Product Goal**, không cần sao chép nguyên câu Product Goal hoặc liệt kê toàn bộ task.

### 15.2. Trong Scrum, chọn PBI và lập kế hoạch là hoạt động cộng tác

Sprint Planning trả lời ba chủ đề:

1. **Why:** Vì sao Sprint này có giá trị? Scrum Team cùng xác định Sprint Goal.
2. **What:** Có thể hoàn thành PBI nào? Developers qua thảo luận với Product Owner chọn PBI phù hợp, cân nhắc năng lực và hiểu biết.
3. **How:** Công việc sẽ được thực hiện thế nào? Developers lập kế hoạch đủ để bắt đầu và điều chỉnh khi làm.

Sprint Backlog bao gồm **Sprint Goal, những PBI đã chọn và kế hoạch giao Increment**. Developers chịu trách nhiệm kế hoạch và thích ứng mỗi ngày; Product Owner làm rõ giá trị và Product Backlog; Scrum Master hỗ trợ sử dụng Scrum hiệu quả.

**Không phải PO hoặc quản lý tự giao task đến từng Developer rồi gọi đó là Sprint Planning.**

### 15.3. Ví dụ Sprint Planning hai tuần — chỉ là tình huống học

Giả sử Developers và Product Owner đã xác định:

- P01 sửa lỗi trùng và test hồi quy là ưu tiên rủi ro đã xử lý ở mức ứng cứu cần thiết.
- Spike P02 đã cho biết cần giữ Unknown nếu đối tác chưa trả kết quả cuối.
- Nhóm có thể hoàn tất một lát cắt **trạng thái sau gửi** trong Sprint hai tuần nếu hợp đồng và môi trường test sẵn sàng.

Kế hoạch minh họa:

| Thành phần Sprint Backlog | Nội dung |
| --- | --- |
| **Sprint Goal** | Khách biết kết quả yêu cầu đặt lịch đúng và có bước tiếp an toàn. |
| **PBI chọn** | Trạng thái có thẩm quyền và giao diện Pending/Confirmed/Rejected/Unknown ở phạm vi loại lịch cơ bản. |
| **Hợp tác kỹ thuật** | Contract với adapter, kiểm tra quyền truy cập, test timeout/retry, UI accessibility. |
| **Kiểm chứng** | Acceptance criteria, integration tests, DoD chung, usability review phù hợp. |
| **Bất định còn mở** | API đối tác có thay semantics? Mã yêu cầu có đủ để tra cứu sau khi rời trang không? |
| **Điều chỉnh trong Sprint** | Developers điều chỉnh kế hoạch khi học thêm, trao đổi phạm vi với PO mà không giảm chất lượng hoặc gây nguy hiểm Sprint Goal. |

**Một Sprint hai tuần không đảm bảo lát cắt chắc chắn xong trong hai tuần**; forecast phải dựa năng lực, kỹ thuật, phụ thuộc và bằng chứng. Không được đẩy phần test sang Sprint sau chỉ để tuyên bố PBI Done.

### 15.4. Một luồng phát hành không cần chờ Sprint Review

Trong Scrum:

- Sprint Review là dịp **kiểm tra outcome của Sprint và cùng stakeholder thích ứng hướng sản phẩm**.
- Increment đạt DoD có thể được tạo **nhiều lần trong Sprint** và phát hành trước Review nếu các điều kiện release khác được đáp ứng.
- Không nên dùng Review như cổng phê duyệt bắt buộc của Scrum.
- Retrospective nhằm cải tiến chất lượng và hiệu quả của Scrum Team, không phải họp duyệt backlog.

Nhóm có thể demo một prototype chưa đủ DoD **nếu nói rõ đó là prototype**, nhưng không gọi nó là Increment đã Done.

### 15.5. Khi Sprint Goal đối mặt công việc khẩn

Một lỗi production nghiêm trọng tạo lịch trùng giữa Sprint cần được ứng cứu ngay theo quyền và chính sách. Developers cùng Product Owner sẽ cần nhìn **năng lực còn lại, Sprint Goal, phạm vi và rủi ro** để thích ứng.

Trong Scrum, không làm thay đổi gây nguy hiểm Sprint Goal; chất lượng không giảm; phạm vi được làm rõ/thương lượng khi học thêm. Nếu Sprint Goal **trở nên lỗi thời**, chỉ Product Owner có quyền hủy Sprint. **Không tự hủy Sprint chỉ vì có bug hoặc một PBI bị chậm**.

### 15.6. Không bắt mọi công việc khám phá phải đợi Sprint sau

Một nhóm có thể thử ngôn ngữ Pending với khách trong khi Developers đang làm Increment của trạng thái hiện tại, nếu có năng lực và sự phối hợp phù hợp. Phát hiện mới giúp làm rõ PBI hoặc hướng tiếp theo. **Discovery và delivery là vòng trao đổi**, không cần bàn giao theo tầng cứng nhắc.

## 16. Dùng Kanban để đưa lát cắt giá trị qua dòng công việc

### 16.1. Product Backlog là nguồn chọn việc; flow là đường để hoàn tất

Một nhóm có thể có Product Backlog có thứ tự tốt nhưng vẫn thất bại khi:

- Năm PBI đang thiết kế, bốn PBI chờ review, ba PBI chờ test.
- Developers tiếp tục kéo việc mới vì muốn “luôn bận”.
- PBI gần hoàn tất lại nằm chờ một người biết API.
- Code merge nhanh nhưng không có Increment tích hợp và kiểm chứng.

Tư duy Kanban giúp nhóm nhìn **work items di chuyển qua những trạng thái thực** và quản lý **WIP (Work in Progress)**, thay vì chỉ có danh sách To Do/Doing/Done đẹp.

### 16.2. Definition of Workflow minh họa

~~~mermaid
flowchart LR
    A["Product Backlog có thứ tự"] --> B["Ready để kéo khi có năng lực"]
    B --> C["In Progress"]
    C --> D["Review và tích hợp"]
    D --> E["Kiểm thử/kiểm chứng DoD"]
    E --> F["Done / Increment"]
    F -. "Khi đủ điều kiện release" .-> G["Released / Observed"]
    C -. "Nếu bị chặn" .-> H["Blocked: công khai lý do"]
    D -. "Nếu bị chặn" .-> H
    H -. "Được tháo chặn" .-> D
~~~

Đây là workflow minh họa. Đội có thể đặt bước **Review, Test, Integration** khác nhau tùy công nghệ. Quan trọng là xác định:

1. Khi nào một item **bắt đầu**, **kết thúc**.
2. Các trạng thái/luồng và **chính sách chuyển trạng thái**.
3. Điểm nào thực sự bị chờ và **ai có thể tháo**.
4. Cách **quản lý WIP**, bao gồm chính sách cho incident khẩn.
5. Cách lấy phản hồi và **cải tiến flow**.

Nếu số liệu cycle time chỉ dừng ở Merge mà người dùng phải chờ release thêm hai tuần, nên có thước đo bổ sung từ yêu cầu tới giá trị, không che phần chờ ngoài workflow.

### 16.3. Giới hạn WIP để hoàn tất, không phải để có cột ít thẻ

Giả sử Team Booking có bốn Developers, nhưng chỉ một người nắm contract của đối tác. Mở sáu PBI cùng cần người đó không tạo sáu lần tốc độ; nó tạo **hàng đợi**.

Một thử nghiệm nhỏ:

- Đặt chính sách **kéo PBI mới khi có năng lực tại điểm nghẽn**, thay vì mọi người cùng bắt đầu.
- Khi một PBI chờ review, Developers khác có thể **giúp kiểm thử/điều tra** hoặc giảm blocker.
- Theo dõi **work item age** để nhận biết hạng mục khó không được hoàn tất.
- Giữ **ngoại lệ minh bạch cho incident** và công việc bắt buộc.
- Xem lại ngưỡng WIP khi dữ liệu cho thấy quá thấp hoặc quá cao.

**Không có số WIP limit “đúng chuẩn” cho mọi Scrum Team hoặc sản phẩm**. Mức giới hạn là một chính sách dựa vào workflow và khả năng hoàn tất thực tế.

### 16.4. Bốn metric flow và một ví dụ

| Metric | Nghĩa | Ví dụ |
| --- | --- | --- |
| **WIP** | Work items đã bắt đầu nhưng chưa kết thúc. | Trung bình 12 PBI trong workflow. |
| **Throughput** | Số work items đi qua điểm Done trong một khoảng thời gian. | 4 PBI/tuần, với định nghĩa PBI nhất quán. |
| **Cycle time** | Thời gian từ điểm bắt đầu tới điểm kết thúc của item. | Trung bình 3 tuần/PBI trong workflow giả định. |
| **Work item age** | Item hiện còn mở đã ở trong workflow bao lâu. | PBI-07 đang 11 ngày, cần xem vì sao. |

Trong một workflow **đủ ổn định, với cùng ranh giới**, Little’s Law:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Ví dụ \(12/4=3\) tuần/PBI là **thời gian trung bình theo mô hình**, không phải dự báo chắc chắn mỗi PBI kết thúc sau ba tuần. Cần kiểm tra loại việc, thay đổi đầu vào, việc còn mở và đuôi phân bố.

### 16.5. Đừng coi throughput task là throughput giá trị

Một feature được chia thành:

- Task UI.
- Task API.
- Task persistence.
- Task contract tests.
- Task QA.

Năm task Done **không nhất thiết tạo năm Increment**. Nếu API chưa an toàn, hành vi người dùng chưa hoàn tất. Đo flow cấp sản phẩm nên có ranh giới từ **lát cắt PBI có ý nghĩa tới Done tích hợp**, còn task nội bộ giúp team điều phối.

### 16.6. Kanban và Scrum có thể hỗ trợ nhau

Trong Scrum, Developers có thể dùng:

- WIP limit khi triển khai các PBI được chọn cho Sprint Goal.
- Work item age trong Daily Scrum để chọn việc nên hoàn tất trước.
- Cycle time/throughput trong Retrospective để cải tiến.
- Blocker visualization để giải quyết phụ thuộc liên nhóm.

Các thực hành này **không thay Sprint Goal, Product Goal, Scrum events, accountabilities hay DoD**. Chúng giúp tạo Increment **ít chờ hơn** trong khuôn khổ mục tiêu.

## 17. Dùng XP và kỹ thuật bảo đảm lát cắt nhỏ thật sự an toàn

### 17.1. Không thể giao tăng dần nếu mỗi thay đổi nhỏ phá phần cũ

Giả sử UI làm rõ Pending nhưng một thay đổi trong Booking Service làm request gửi lặp tạo thêm lịch. Đội có thể giao “lát cắt nhỏ” trên giấy nhưng chi phí sửa sai tăng, mất niềm tin và khó phát hành tiếp.

Các thực hành kỹ thuật thường gắn với **Extreme Programming (XP)** như **Test-Driven Development (TDD), Continuous Integration (CI), refactoring, pairing và small releases** giúp nhóm giữ phản hồi kỹ thuật nhanh khi sản phẩm phát triển tăng dần.

### 17.2. TDD trong ngữ cảnh giả thuyết kỹ thuật

Khi sửa bất biến chống đặt trùng, nhóm có thể bắt đầu từ ví dụ hành vi:

~~~text
Given còn đúng một slot cho chuyên gia vào 14:00
When hai yêu cầu khác nhau cùng cố xác nhận slot đó
Then tối đa một lịch được Confirmed theo quy tắc
And yêu cầu còn lại nhận trạng thái/hướng xử lý hợp lệ

Given request R1 đã được tiếp nhận
When client gửi lại R1 với cùng idempotency key
Then hệ thống không tạo booking mới thứ hai

Given kết quả từ đối tác chưa biết sau timeout
When client tra cứu trạng thái R1
Then hệ thống không tự suy ra Confirmed nếu chưa có căn cứ
~~~

Đội có thể viết **test fail trước**, triển khai giải pháp tối thiểu, rồi refactor với bộ test bảo vệ. Tuy nhiên:

- Unit test không tự chứng minh transaction chống concurrency trong môi trường thật.
- Cần kiểm thử ràng buộc dữ liệu, tích hợp và contract ở các tầng thích hợp.
- Có thể cần cơ chế đối soát/compensation khi giao dịch ngoài hệ thống đã xảy ra.
- Không được dùng việc “test xanh” để bỏ qua các chuẩn bảo mật/vận hành áp dụng.

### 17.3. CI làm vòng phát hiện sai khác ngắn hơn

Với UI, Booking API và adapter đối tác cùng thay đổi, CI có thể chạy:

1. Unit tests cho quy tắc nghiệp vụ.
2. Contract tests cho API trạng thái.
3. Integration tests cho những đường tương tác trọng yếu.
4. Kiểm tra tĩnh/bảo mật phù hợp.
5. Test migration/schema nếu cần.
6. Build và đóng gói phần mềm có thể tích hợp.

**Không có pipeline nào bảo đảm không có lỗi**. Nếu CI flaky liên tục hoặc test bỏ sót semantics Pending/Unknown, cần cải tiến cả test và hợp đồng nghiệp vụ.

### 17.4. Pairing để giảm phụ thuộc tri thức

Nếu chỉ một Developer hiểu idempotency, họ trở thành điểm nghẽn cho mọi Increment. Pairing có mục đích giúp:

- Cùng hiểu quy tắc không đặt trùng.
- Xây test hồi quy đáng tin.
- Chia sẻ cách dùng môi trường/sandbox đối tác.
- Tạo reviewer có đủ ngữ cảnh.

**Pairing không phải quy định mọi người luôn ngồi đôi** bất kể loại việc. Lợi ích cần xem qua chất lượng, khả năng bảo trì và giảm thời gian chờ, không chỉ “đã pair bao nhiêu giờ”.

### 17.5. Refactoring và nợ kỹ thuật liên hệ tới Product Goal

Một phần Booking Service quá coupling có thể khiến mỗi thay đổi trạng thái kéo theo sửa hàng chục nơi. Một PBI cải tiến kỹ thuật có thể có giá trị khi:

- Giảm rủi ro phát sinh bug với tính năng quan trọng.
- Cho phép tạo lát cắt nhỏ thường xuyên hơn.
- Giảm thời gian integration test/review.
- Giảm phụ thuộc một chuyên gia hoặc môi trường.

**Không phải mọi yêu cầu “viết lại kiến trúc” đều đáng ưu tiên hơn giá trị người dùng**. Hãy chỉ ra rủi ro và chi phí cơ hội có bằng chứng, thử refactor từng bước với test bảo vệ.

### 17.6. Kỹ thuật cũng cần vòng giả thuyết – bằng chứng

Ví dụ:

> “Nếu đưa contract tests cho trạng thái booking vào CI, các thay đổi adapter sai semantics sẽ bị phát hiện trước khi tích hợp muộn, giảm số lần phải làm lại phần UI.”

Đo:

- Thời gian từ thay đổi tới lỗi được phát hiện.
- Số sai khác contract được bắt trước integration.
- Độ tin cậy pipeline, false failures.
- Cycle time của lát cắt liên nhóm.
- Lỗi liên quan tới contract thoát ra môi trường thật.

**Kết quả kỹ thuật hỗ trợ Product Goal khi nó cho phép giao giá trị an toàn hơn**, không chỉ tăng một chỉ số coverage.

## 18. Bài thực hành xuyên suốt: bốn vòng nhỏ tiến tới Product Goal

Các vòng dưới đây thể hiện **một lộ trình giả định** để người học nhìn quan hệ giữa học và giao. Chúng **không phải bốn Sprint bắt buộc**, cũng không có bảo đảm mỗi vòng luôn mất đúng hai tuần.

### 18.1. Bắt đầu bằng giả định và quyết định an toàn

Product Goal:

> “Khách tự đặt và tra cứu lịch tư vấn đáng tin, ít cần gọi hỗ trợ để biết kết quả.”

Baseline giả định: 1.000 phiên bắt đầu; 680 Confirmed trong 24h; 255/850 phiên đã submit có gửi lặp; 150 lượt liên hệ hỏi trạng thái; 2 sự cố đặt trùng.

**Điều bắt buộc xử lý sớm:** Đánh giá và giảm nguy cơ đặt trùng theo mức độ rủi ro, bảo vệ dữ liệu và không hiển thị trạng thái sai. Công việc này có thể cần đường ứng cứu ngay, không đợi kết quả A/B test UX.

### 18.2. Vòng 0 — Bảo vệ bất biến, giảm bất định

**Mục đích:** Có nền tảng an toàn để mọi Increment tiếp theo không khuếch đại lỗi.

| Yếu tố | Nội dung |
| --- | --- |
| **Vấn đề** | Request gửi lặp và cạnh tranh có thể tạo lịch Confirmed trùng; API đối tác không rõ hành vi timeout. |
| **Việc cần làm** | Triaging/sửa lỗi, test concurrency, spike hợp đồng timeout/idempotency. |
| **Giả thuyết kỹ thuật** | Có thể bảo đảm bất biến ở điểm ghi có thẩm quyền và thể hiện Unknown khi chưa biết kết quả. |
| **Đầu ra** | Cơ chế chống trùng được kiểm chứng và kết luận rõ về API/đối soát, phần mềm đạt DoD khi có thay đổi. |
| **Đo** | Test bất biến, lỗi hồi quy, giám sát sự cố, kết quả API sandbox. |
| **Quyết định tiếp** | Có thể xây tra cứu trạng thái ở phạm vi nào và guardrails nào vẫn cần? |

**Không tuyên bố “đã tạo giá trị mới” chỉ vì spike xong**. Giá trị có thể là **giảm rủi ro và tăng khả năng giao an toàn**; cần báo đúng bản chất công việc.

### 18.3. Vòng 1 — Hiểu và hiển thị trạng thái sau gửi

**Giả thuyết H1:** Ngôn ngữ trạng thái rõ giúp khách hiểu đúng Pending/Confirmed/Rejected/Unknown.

**Bằng chứng trước khi xây nhiều:** Thử prototype với khách đủ điều kiện:

- Đưa ra một tình huống mạng chậm, khách vừa bấm Đặt lịch.
- Yêu cầu khách giải thích họ nghĩ điều gì đã xảy ra.
- Quan sát họ có bấm lại hoặc muốn gọi hỗ trợ không.
- Kiểm tra cách hiểu **“Đang xác nhận; chưa có kết quả cuối”**.
- Ghi chỗ khó hiểu và trường hợp lệch dự đoán.

**Increment dự kiến:** UI trạng thái sau gửi + API có thẩm quyền cho loại lịch đơn + quyền truy cập + trạng thái đúng + kiểm thử tích hợp và vận hành cần thiết.

**Không thuộc phạm vi vòng này:** SMS cho mọi khách, tự đổi lịch, hoàn phí.

**Phải đúng:** Khi Unknown, UI không tự nói Confirmed hoặc Rejected. Nếu backend chưa đáp ứng được điều này, cần sửa thiết kế hoặc chưa đưa lát cắt ra production.

### 18.4. Vòng 2 — Tra cứu lại và giảm gửi lặp

**Giả thuyết H2:** Khách có mã yêu cầu và đường tra cứu sẽ ít gửi lại thao tác đặt lịch hơn.

**Lát cắt:**

1. Sau khi request được tiếp nhận hợp lệ, khách có mã yêu cầu phù hợp.
2. Khách rời trang và trở lại, có cách tra cứu trạng thái theo chính sách.
3. Backend không tạo request mới chỉ vì tra cứu.
4. Không tiết lộ dữ liệu của khách khác.
5. Khi không biết kết quả, hệ thống nói rõ cần chờ/đối soát.

**Acceptance examples:** Mã hợp lệ, mã sai, quyền không hợp lệ, trạng thái có/không có kết quả cuối, request gửi lại.

**Đo:** Tác vụ tra cứu trong pilot, submit-repeat rate, support contact rate và các guardrails chất lượng.

**Quyết định tiếp:** Mã tra cứu có đủ giá trị không, hay khách vẫn cần thông báo chủ động? Nếu cần SMS, **nhu cầu được xác minh từ dữ liệu**, không chỉ ý kiến.

### 18.5. Vòng 3 — Đối soát khi timeout và mở rộng sử dụng

**Rủi ro/giả thuyết:** Đối tác có thể xử lý request dù client timeout. Cần đường đồng bộ/đối soát an toàn, tránh tạo lịch hai lần hoặc nói sai trạng thái.

**Lát cắt:**

- Khi timeout, Booking Service ghi trạng thái nội bộ nhất quán.
- Có đường query/reconcile theo hợp đồng thực tế hoặc quy trình xử lý phù hợp.
- Client không nhận Confirmed nếu không có kết quả có thẩm quyền.
- Hệ thống có thể theo dõi item Pending/Unknown quá lâu.
- Support có đủ thông tin **theo quyền** để giúp khách mà không gây giao dịch lặp.

**Đo:** Tỷ lệ trạng thái Unknown chưa được giải quyết trong thời hạn, blocked/support, lỗi dữ liệu và cycle time giao thay đổi.

**Điều kiện phát hành:** Contract tests và test tích hợp đúng, nghĩa vụ bảo mật/vận hành đáp ứng, có người chịu trách nhiệm theo dõi/khôi phục.

### 18.6. Vòng 4 — Một khả năng tự phục vụ tiếp theo dựa trên bằng chứng

Giả sử phản hồi sau các vòng trước cho thấy:

- Khách ít hỏi trạng thái hơn.
- Một nhóm khách vẫn phải gọi support để đổi giờ.
- Chính sách cho phép đổi **một lịch đơn, không phí, trước một thời hạn rõ**.

Nhóm có thể ưu tiên lát cắt **đổi giờ cơ bản**:

> “Là khách có một lịch Confirmed đủ điều kiện, tôi muốn đổi sang giờ còn trống để không phải gọi hỗ trợ khi lịch cá nhân thay đổi.”

Trước khi xây, phải kiểm tra:

- Quy tắc thay đổi/hủy/giữ slot.
- Transaction và tính nhất quán giữa hai lịch.
- Timeout/retry và đền bù/đối soát khi cần.
- Quyền truy cập và thông báo.
- Trường hợp không được phép đổi.

**Không mở toàn bộ tính năng đổi lịch nhiều điều kiện ngay**, và không được coi đổi lịch “nhỏ” nếu các bất biến có thể bị phá.

### 18.7. Bảng nối Product Goal – hypothesis – slice – evidence

| Vòng | Giả thuyết hoặc rủi ro | Phần việc nhỏ | Bằng chứng kiểm chứng | Quyết định sau vòng |
| --- | --- | --- | --- | --- |
| **0** | Chống gửi lặp có thể bảo đảm an toàn; API timeout còn bất định. | Sửa/test bất biến, spike timeout. | Test concurrency, contract sandbox, giám sát. | Có thể triển khai đường trạng thái nào? |
| **1** | Diễn đạt Pending rõ giúp người dùng hiểu. | Trạng thái sau submit tích hợp an toàn. | Usability + đúng semantics/test. | Có cần mã tra cứu? Nội dung nào hiệu quả? |
| **2** | Tra cứu giúp giảm submit lặp/gọi hỗ trợ. | Mã yêu cầu và tra cứu sau khi rời trang. | Repeat rate, contact rate, quyền/bug. | Giữ, sửa UX, hoặc thử thông báo chủ động? |
| **3** | Đối soát giảm Unknown tồn đọng mà không tạo trùng. | Reconciliation/observability với một đối tác. | Unknown age, test và dữ liệu production an toàn. | Mở rộng đối tác hoặc sửa thiết kế? |
| **4** | Khách cần tự đổi lịch ở trường hợp phổ biến. | Đổi giờ lịch đơn trong chính sách. | Completion theo tác vụ đổi, lỗi và hỗ trợ. | Mở rộng quy tắc hay dừng? |

**Thứ tự có thể thay đổi** theo bằng chứng. Vòng 3 đôi khi là **điều kiện an toàn phải có trước vòng 1 hoặc 2**, chứ không được trì hoãn để chạy demo. Bảng thể hiện các năng lực được học và bổ sung, **không phải lời cho phép release tính năng chưa an toàn**.

### 18.8. Một roadmap tăng dần không phải Gantt khóa phạm vi

~~~text
Product Goal: Khách đặt và xác minh lịch đáng tin
  |
  +-- [Bảo vệ dữ liệu / làm rõ hợp đồng]
  |
  +-- [Trạng thái sau submit] --> [Feedback: khách hiểu đúng?]
  |
  +-- [Tra cứu bằng mã] ------> [Feedback: giảm gửi lặp/gọi?]
  |
  +-- [Đối soát Unknown] ----> [Feedback: giảm tồn đọng/rủi ro?]
  |
  +-- [Đổi giờ cơ bản?] -----> [Chỉ khi nhu cầu/chính sách phù hợp]

Mỗi bước:
  giả thuyết + lựa chọn + lát cắt + chất lượng + đo + quyết định tiếp
~~~

**Dấu hỏi ở bước tiếp theo là có chủ đích.** Roadmap thể hiện ý định và các cơ hội, không có nghĩa phải xây tất cả tính năng ngay cả khi phản hồi bác bỏ giá trị.

## 19. Đọc số liệu sau phát hành mà không tự đánh lừa mình

### 19.1. Một bộ số liệu trước–sau giả định

Sau khi nhóm hoàn thành các phần an toàn, giải thích trạng thái và tra cứu cơ bản, họ quan sát một cửa sổ bốn tuần tiếp theo. Giả sử:

| Tín hiệu giả định | Baseline (4 tuần) | Sau phát hành (4 tuần) |
| --- | ---: | ---: |
| **Phiên bắt đầu đặt lịch** | 1.000 | 1.200 |
| **Phiên có lịch Confirmed trong 24h** | 680 | 900 |
| **Phiên có ít nhất một submit** | 850 | 990 |
| **Phiên có submit lặp cùng yêu cầu** | 255 | 198 |
| **Lượt liên hệ hỏi trạng thái** | 150 | 108 |
| **Lỗi đặt trùng đã xác minh trong kỳ** | 2 | 0 |
| **Lát cắt PBI đạt DoD** | 4 | 6 |
| **PBI tích hợp có cycle time trung vị** | 15 ngày làm việc | 11 ngày làm việc |

**Lưu ý:** Đây là số liệu minh họa **không được thu từ thử nghiệm đối chứng**, và có thể gồm nhiều can thiệp cùng lúc. Các định nghĩa, cửa sổ và phạm vi phải thật sự nhất quán mới đáng so; việc bảng ghi số trông chính xác không chứng minh dữ liệu thực tế có độ tin cậy như vậy.

### 19.2. Tỷ lệ Confirmed trong 24h

Baseline:

\[
\frac{680}{1000}\times100\%=68\%
\]

Sau phát hành:

\[
\frac{900}{1200}\times100\%=75\%
\]

**Chênh lệch: 7 điểm phần trăm** (75% − 68%).

**Mức tăng tương đối:** \((75-68)/68\times100\%\approx10{,}3\%\).

Không viết “tỷ lệ tăng 7%” khi muốn nói **7 điểm phần trăm**. Hai cách biểu đạt khác nhau.

### 19.3. Tỷ lệ submit lặp

Chỉ tính trên **phiên có ít nhất một submit**, không dùng tổng phiên bắt đầu:

\[
\text{Baseline}=\frac{255}{850}\times100\%=30\%
\]

\[
\text{Sau}=\frac{198}{990}\times100\%=20\%
\]

Mức giảm **10 điểm phần trăm**, tương đương **33,3% giảm tương đối** so với mức 30% ban đầu.

Điều này có thể hỗ trợ giả thuyết “trạng thái rõ và mã tra cứu giúp giảm gửi lặp”, nhưng chưa phân biệt được tác động của:

- Thông báo UX mới.
- Cơ chế idempotency/khả năng chặn request lặp.
- Thời gian phản hồi API nhanh hơn.
- Tỷ lệ khách mới và thiết bị/mạng đã thay đổi.
- Một thay đổi logging làm phân loại submit lặp khác trước.

**Không tự gán toàn bộ 10 điểm phần trăm cho riêng tính năng tra cứu** nếu không có thiết kế và bằng chứng phù hợp.

### 19.4. Lượt liên hệ hỗ trợ trên 100 phiên

\[
\text{Baseline}=\frac{150}{1000}\times100=15\ \text{lượt/100 phiên}
\]

\[
\text{Sau}=\frac{108}{1200}\times100=9\ \text{lượt/100 phiên}
\]

Mức giảm **6 lượt/100 phiên**, tương đương **40% giảm tương đối** theo rate này.

**Không viết “40% khách bớt gọi”**: mẫu số là **lượt liên hệ trên phiên**, không phải số khách duy nhất. Cần xem thêm khách mới, số cuộc gọi lặp, sự kiện hỗ trợ theo loại vấn đề và những trường hợp cần trợ giúp dù đã có tra cứu.

### 19.5. Lỗi đặt trùng = 0 là tín hiệu, không phải bằng chứng tuyệt đối

Số sự cố đã xác minh giảm từ 2 xuống 0 trong hai cửa sổ. Điều này đáng ghi nhận, nhưng:

- Không biết cùng lượng booking hay cùng mức độ rủi ro?
- Có đủ dữ liệu phát hiện sự cố hiếm không?
- Có phải incident đã được phân loại/đối soát nhất quán?
- Các test concurrency và idempotency có còn chạy và đạt?
- Có cơ chế xử lý khi phát hiện trạng thái sai sau timeout?

**Một khoảng không thấy lỗi chưa chứng minh hệ thống không còn khả năng lỗi**. Phải giữ test, giám sát và incident response theo mức rủi ro.

### 19.6. Cycle time giảm có thể có nguyên nhân ngoài tính năng

Cycle time trung vị của PBI tích hợp giảm từ 15 xuống 11 ngày làm việc, tức giảm \((15-11)/15\times100\%\approx26{,}7\%\) tương đối.

Nhưng đó là **metric của quá trình phát triển**, trong khi completion là metric của **người dùng**. Có thể nhóm cải thiện CI hoặc giảm WIP, chứ không phải UI trạng thái khiến PBI Done nhanh hơn. Cần xem:

- Số PBI và độ phức tạp ở hai kỳ.
- Có PBI rất lâu chưa hoàn tất không?
- Ranh giới bắt đầu/kết thúc và DoD có đổi không?
- Có thời gian chờ release sau Done không?
- Team có hỗ trợ incident bất thường trong kỳ không?

Đừng gộp hai thay đổi rồi nói “tính năng tra cứu tăng năng suất Developer 26,7%”.

### 19.7. Một bảng kết luận “quan sát – suy luận – quyết định”

| Điều quan sát | Suy luận/giả thuyết có thể hợp lý | Chưa thể kết luận | Quyết định tiếp theo |
| --- | --- | --- | --- |
| Completion 68% → 75%. | Trải nghiệm/độ tin cậy có thể cải thiện. | Riêng UI trạng thái gây toàn bộ thay đổi. | Phân tích funnel, phân đoạn, phản hồi sử dụng. |
| Submit lặp 30% → 20%. | Khách có thể bớt mơ hồ khi gửi yêu cầu. | Khách đều dùng mã tra cứu. | Đo lượt tra cứu thành công, thử usability tiếp. |
| Liên hệ hỏi trạng thái 15 → 9 lượt/100 phiên. | Khách có thể tự giải quyết nhiều trường hợp hơn. | 40% khách duy nhất không gọi nữa. | Xem nội dung gọi còn lại, phân khúc và việc cần hỗ trợ thật. |
| Sự cố đặt trùng 2 → 0. | Đường sửa/test có thể giảm rủi ro. | Không bao giờ còn lỗi tạo trùng. | Tiếp tục test/giám sát, xem mức phơi nhiễm. |
| Cycle time 15 → 11 ngày. | Flow/integration có thể tốt hơn. | Một framework là nguyên nhân duy nhất. | Xem WIP, blocked, loại PBI, CI và năng lực. |

**Kết quả nghiên cứu không cần luôn khẳng định nhân quả**. Nó cần đủ trung thực để giúp Product Owner/Developers quyết định tiếp theo, hoặc chọn một thử nghiệm giảm bất định.

### 19.8. Khi cần bằng chứng mạnh hơn

Nếu sắp đầu tư lớn hoặc mở tính năng cho nhiều khách, có thể cần:

- So sánh các nhóm/luồng đủ tương đồng, có guardrails.
- Theo dõi nhiều kỳ, tránh một tuần ngẫu nhiên.
- Phân tích phân đoạn và biến số nhiễu.
- Dữ liệu định tính từ khách không chọn theo kết quả mong muốn.
- Xem độ lớn hiệu quả và khoảng bất định phù hợp.
- Đánh giá rủi ro bảo mật/dữ liệu riêng, không được thay bằng A/B test conversion.

Một A/B test có thiết kế đúng có thể hỗ trợ một số câu hỏi **về giao diện hoặc giá trị**, nhưng không nên ngẫu nhiên hóa việc có hay không có **bảo vệ giao dịch bắt buộc** cho người dùng thật.

## 20. Khi giả thuyết sai hoặc xuất hiện trở ngại, làm gì?

### 20.1. Bốn lựa chọn sau một vòng học

| Kết quả | Hành động phù hợp | Ví dụ |
| --- | --- | --- |
| **Giả thuyết có tín hiệu tốt, guardrails giữ** | Duy trì và cân nhắc mở rộng có kiểm soát. | Mã tra cứu dễ dùng, khách hiểu trạng thái và support giảm. |
| **Giá trị có, giải pháp chưa đúng** | Sửa phương án/viết giả thuyết mới. | Khách cần tra cứu nhưng không nhớ mã, thử đường truy cập khác có bảo mật. |
| **Bằng chứng chưa đủ** | Đặt câu hỏi tiếp, đo hoặc thử thêm đúng chỗ. | Mẫu usability nhỏ, dữ liệu truy cập không đầy đủ. |
| **Giả thuyết không có giá trị hoặc gây hại** | Dừng/mở lại lựa chọn, xử lý rủi ro. | SMS không giúp trạng thái, tốn chi phí hoặc gửi sai thời điểm. |

**Không nên tiếp tục làm một feature lớn chỉ vì đã lỡ viết một phần code**. Chi phí đã bỏ ra không tự làm phần còn lại có giá trị.

### 20.2. Một giả thuyết UX bị bác bỏ

Nhóm tin rằng thêm dòng “Vui lòng chờ” đủ để khách ngừng gửi lại. Usability test cho thấy nhiều người vẫn không phân biệt được **đang xử lý** với **đã lỗi**.

Quyết định có thể là:

1. Không mở rộng giải pháp chỉ đổi một dòng text.
2. Hỏi cách khách hiểu kết quả cuối và nhu cầu kiểm chứng.
3. Thử mã yêu cầu, trạng thái có thẩm quyền và đường tra cứu.
4. Cập nhật PBI/acceptance criteria thay vì cố hoàn tất màn hình cũ.

**Giả thuyết sai giúp tránh xây sai**, nếu nhóm có quyền thay quyết định.

### 20.3. Một giả thuyết kỹ thuật không đạt

Spike cho thấy API đối tác **không hỗ trợ tra cứu kết quả sau timeout** như dự kiến. Việc hiển thị Confirmed sau một timeout trở nên không an toàn.

Những lựa chọn cần cân nhắc:

- Thay đổi hợp đồng/khả năng với đối tác.
- Dùng trạng thái Unknown và quy trình đối soát trong phạm vi đáp ứng yêu cầu.
- Giới hạn lát cắt cho một đối tác/luồng có khả năng xác nhận đáng tin.
- Chọn phương án xử lý bất đồng bộ hoặc compensation nếu phù hợp nghiệp vụ và có thể bảo vệ.
- Dời hoặc bỏ feature nếu không thể làm an toàn với chi phí chấp nhận được.

**Không che kết quả spike để giữ roadmap**. Product Owner cùng Developers, chuyên gia miền và người có quyền rủi ro cần cập nhật quyết định.

### 20.4. Một PBI quá lớn hoặc bị phụ thuộc nặng

Nếu “tự đổi mọi loại lịch” yêu cầu ba nhóm trong nhiều tuần, hãy xem:

- Có thể bắt đầu bằng **xem chính sách đổi** trước khi cho phép đổi thật không?
- Có thể hỗ trợ **một loại lịch đơn không phí** không?
- Có thể thử **một đối tác đã xác minh API** không?
- Có cần enabler hoặc spike cho **transaction và compensation** trước?
- Có thể bảo vệ ranh giới phát hành bằng feature flag hoặc rollout có kiểm soát không?

**Nhỏ lại không có nghĩa yếu đi về an toàn**. Lát cắt hoàn chỉnh phải được kiểm chứng trong phạm vi được công bố.

### 20.5. Incident không đợi đến cuộc họp lập kế hoạch

Nếu production tạo lịch trùng, nhóm kích hoạt **incident response** theo mức nghiêm trọng: giảm thiệt hại, đối soát dữ liệu, thông báo phù hợp, khắc phục và kiểm chứng. Product Owner và Developers sau đó nhìn lại **ưu tiên, năng lực, Sprint Goal/flow và dự báo**.

Trong Scrum, chỉ Product Owner có thể hủy Sprint nếu Sprint Goal trở nên lỗi thời; **không hủy tự động khi gặp một blocker hoặc đổi một PBI**. Chất lượng không được hạ để bù chi phí ứng cứu.

### 20.6. Khi outcome tốt nhưng chi phí không bền vững

Giả sử SMS làm một nhóm khách bớt hỏi trạng thái, nhưng chi phí vận hành tăng mạnh, nhiều tin bị gửi lặp và support phải giải thích thêm. Nhóm phải cân nhắc **giá trị ròng, chi phí trì hoãn, chi phí vận hành, rủi ro quyền riêng tư và lựa chọn khác**.

Không nên quyết định chỉ từ “có bao nhiêu khách bấm vào SMS”. **Product Goal nói về khả năng tự xác minh lịch đáng tin**, không bắt buộc kênh SMS.

### 20.7. Tạo decision log ngắn

~~~text
Decision: D-BOOK-07
Ngày / bối cảnh: Sau pilot tra cứu trạng thái
Product Goal liên quan: Đặt lịch và xác minh kết quả đáng tin
Giả thuyết: Mã tra cứu giảm submit lặp và gọi hỗ trợ
Bằng chứng: Completion, repeat rate, contact rate, test/guardrails
Giới hạn: Cửa sổ trước/sau, khác nhóm khách, có thay đổi backend
Lựa chọn:
  A. Mở rộng an toàn
  B. Sửa cách truy cập mã
  C. Thử kênh thông báo chủ động
  D. Dừng nếu rủi ro hoặc giá trị không phù hợp
Quyết định / người có quyền:
PBI nào đổi thứ tự hoặc phạm vi:
Điều kiện xem lại:
~~~

Decision log giúp nhóm **ghi lý do và phạm vi của lựa chọn** mà không biến mọi quyết định nhỏ thành quy trình phê duyệt dài. Thông tin nhạy cảm cần được xử lý theo chính sách, không sao chép dữ liệu khách vào log công khai.

## 21. Phối hợp nhiều nhóm để vẫn tạo một giá trị sản phẩm

### 21.1. Tách người thực hiện không nên tách mục tiêu sản phẩm

Giả sử:

- **Team A — Trải nghiệm:** UI trạng thái và khả năng sử dụng.
- **Team B — Booking domain:** Quy tắc đặt trùng, transaction và trạng thái có thẩm quyền.
- **Team C — Integration:** Hợp đồng API đối tác, thông báo và đối soát.

Nếu ba nhóm độc lập ưu tiên “làm hết phần của mình”, A có thể báo UI Done, B có thể báo API Done, C có thể báo adapter Done nhưng **khách vẫn không tra cứu được trạng thái sau timeout**.

Tổ chức cần **Product Goal chung, thứ tự giá trị sản phẩm minh bạch và tiêu chuẩn tích hợp**. Trong Scrum, khi nhiều Scrum Teams cùng làm một sản phẩm, họ nên **chia sẻ Product Goal, Product Backlog, Product Owner** và phải **cùng định nghĩa/tuân thủ một Definition of Done**.

### 21.2. Một dependency map cho lát cắt tra cứu

~~~mermaid
flowchart LR
    H["Giả thuyết H2: tra cứu giúp giảm gửi lặp"] --> P["PBI: khách tra cứu trạng thái"]
    P --> A["A: UI trạng thái và mã"]
    P --> B["B: API có thẩm quyền và quyền truy cập"]
    P --> C["C: mapping/đối soát với đối tác"]
    A --> X["Contract + integration tests"]
    B --> X
    C --> X
    X --> D{"Đạt DoD chung?"}
    D -->|Chưa| F["Sửa phụ thuộc/rủi ro"]
    F --> X
    D -->|Có| I["Increment tích hợp"]
    I --> R["Release an toàn, quan sát outcome"]
~~~

Các mũi tên không nhất thiết nghĩa là phải chờ **mọi task một nhóm xong 100%** mới được bắt đầu nhóm khác. Nhóm có thể **đồng làm rõ contract, dùng stub đúng hợp đồng để thử UI, test tích hợp thường xuyên**, rồi kiểm tra với adapter thật trước khi gọi Done.

### 21.3. Refinement liên nhóm phục vụ lát cắt, không chỉ phân task

Trong một buổi refinement cho PBI tra cứu:

1. Product Owner nói rõ **vì sao** hạng mục quan trọng đối với Product Goal.
2. Support/nhà nghiên cứu cho thấy khách đang hiểu Pending ra sao.
3. Developers làm rõ **semantics**: accepted, Pending, Confirmed, Rejected, Unknown.
4. Team C nêu điều kiện API đối tác và các trường hợp timeout.
5. Team B giải thích nguồn sự thật và điểm bảo vệ idempotency.
6. Team A đề xuất cách hiển thị trạng thái và kiểm chứng khả năng hiểu.
7. Cả nhóm cùng làm rõ **acceptance criteria, ranh giới slice, test và phụ thuộc**.
8. PBI được cập nhật về phạm vi/thứ tự khi có bằng chứng mới.

**Refinement là hoạt động liên tục, không phải Scrum event chính thức bắt buộc**. Mục đích là làm rõ đủ để chọn và thực hiện việc có giá trị, không viết trước mọi chi tiết của năm tới.

### 21.4. Quyền quyết định khác nhau theo câu hỏi

| Loại quyết định | Trách nhiệm/người có quyền phù hợp |
| --- | --- |
| **Product Goal và thứ tự Product Backlog trong Scrum** | Product Owner chịu trách nhiệm về giá trị và quản lý hiệu quả Product Backlog; tham vấn Developers/stakeholder. |
| **Sprint Backlog và cách thực thi** | Developers chịu trách nhiệm kế hoạch và thích ứng, trong Scrum Team. |
| **Chất lượng kỹ thuật và hợp đồng** | Developers/người có thẩm quyền kỹ thuật phối hợp với các bên bị ảnh hưởng, tuân chuẩn và DoD. |
| **Bảo mật, dữ liệu nhạy cảm, ngân sách vượt hạn mức** | Người có thẩm quyền tương ứng theo chính sách tổ chức. |
| **Release, rollback, incident** | Vai trò được tổ chức ủy quyền theo mức rủi ro và vận hành; PO/Developers tham gia khi liên quan. |
| **Tháo phụ thuộc vượt nhóm** | Người có năng lực/thẩm quyền xử lý trở ngại, sponsor khi vượt giới hạn nhóm. |

**Một Product Owner không tự phê duyệt mọi giao dịch kỹ thuật; một trưởng nhóm kỹ thuật không tự quyết mọi ưu tiên giá trị; Scrum Master không phải người giao task cho từng Developer.**

### 21.5. Dùng một bảng phụ thuộc nhưng không tạo một Product Backlog thứ hai

| PBI | Phụ thuộc | Người phối hợp | Dấu hiệu tháo được |
| --- | --- | --- | --- |
| Tra cứu trạng thái | Contract Pending/Unknown | A + B + C | Ví dụ nghiệp vụ và contract tests chung. |
| Đối soát timeout | API đối tác, tài khoản sandbox | B + C + đầu mối đối tác | Spike có kết luận, đường xử lý lỗi rõ. |
| Chống lịch trùng | Transaction/constraint và concurrency test | B + người kiểm thử phù hợp | Test hồi quy đạt trong môi trường có nghĩa. |
| Đổi lịch đơn | Chính sách hủy/giữ chỗ và payment nếu liên quan | PO + chuyên gia miền + Developers | Phạm vi an toàn và acceptance criteria rõ. |

**Dependency view giúp nhìn điểm chặn của PBI đã có trong Product Backlog**, không tạo cơ chế ba nhóm tự ưu tiên theo một danh sách phụ thuộc tách rời.

### 21.6. Đo dòng giá trị ở mức sản phẩm

Nếu A làm UI hai ngày, chờ B năm ngày, B làm API hai ngày, chờ C bốn ngày, rồi tích hợp/test hai ngày, tổng thời gian nối tiếp là:

\[
2+5+2+4+2=15\ \text{ngày}
\]

Thời gian xử lý trực tiếp chỉ là \(2+2+2=6\) ngày; thời gian chờ là \(5+4=9\) ngày. Nếu chỉ báo “A làm UI xong trong hai ngày”, dashboard **không phản ánh thời gian tạo giá trị**.

Nên xem **blocked duration, work item age, cycle time end-to-end và Increment đạt DoD**, không lấy tổng số task của ba nhóm làm số feature đã giao.

### 21.7. Sự khác nhau giữa một sản phẩm và nhiều sản phẩm

Nếu ba team thật sự tạo **ba sản phẩm khác nhau** với người dùng, giá trị, mục tiêu và khả năng giao riêng, có thể cần Product Goals/Backlogs/PO riêng và một cơ chế đầu tư cấp portfolio. Đừng ép mọi công việc của cả công ty vào một Product Backlog chỉ vì “chúng ta cùng tổ chức”.

**Ranh giới sản phẩm phải xuất phát từ kết quả và khả năng mang lại giá trị**, không chỉ cấu trúc công ty hoặc số đội.

## 22. Những phản mẫu khi chuyển mục tiêu thành giả thuyết và Increment

| Phản mẫu | Dấu hiệu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- | --- |
| **Product Goal là danh sách tính năng** | “Ra SMS, loyalty, giao diện mới trong quý.” | Nhóm không biết tác vụ người dùng nào đang cần tốt hơn. | Diễn đạt trạng thái giá trị tương lai và outcome. |
| **Chọn giải pháp trước khi hiểu vấn đề** | “Khách gọi hỗ trợ, vậy xây SMS.” | Có thể giải sai nguyên nhân. | Opportunity map, phỏng vấn, dữ liệu và kiểm chứng giả thuyết. |
| **Giả thuyết không thể sai** | “Khách chắc chắn sẽ thích.” | Không có tín hiệu để đổi ý. | Viết điều kiện quan sát/bác bỏ và guardrails. |
| **Discovery kéo dài không có quyết định** | Phỏng vấn mãi, không rõ câu hỏi tiếp theo. | Tốn năng lực, không giao giá trị. | Timebox, bằng chứng đủ cho quyết định cụ thể. |
| **Spike thành feature Done** | Thử sandbox xong được tính như khách đã có tính năng. | Nhầm kiến thức với Increment. | Ghi đúng đầu ra khám phá và PBI còn thiếu. |
| **Chia story theo UI/API/database** | Ba team Done riêng, không có hành vi đầu-cuối. | Tích hợp muộn, feedback chậm. | Chia vertical slice có tiêu chí tích hợp. |
| **“Nhỏ” bằng cách bỏ an toàn** | Chỉ test happy path, để retry/concurrency sau. | Tạo rủi ro dữ liệu và vi phạm DoD. | Thu nhỏ quy tắc/phạm vi, giữ guardrails. |
| **Giả thuyết nào cũng phải viết code** | Mọi ý tưởng dẫn tới một feature lớn. | Chi phí học cao, lãng phí. | Prototype, spike, nghiên cứu trước khi xây nếu phù hợp. |
| **Chỉ đo click** | Số click Đặt lịch tăng, backend không Confirmed. | Sai outcome, có thể tăng thao tác thất bại. | Đo trạng thái có thẩm quyền theo phiên. |
| **Đổi mẫu số sau phát hành** | Bỏ phiên lỗi để completion cao hơn. | So sánh trước–sau sai. | Metric contract, giữ định nghĩa và giải thích thay đổi. |
| **Nhầm điểm phần trăm với phần trăm tương đối** | 68% → 75% báo “tăng 7%”. | Diễn giải mơ hồ và có thể sai về quy mô tác động. | Nêu 7 điểm phần trăm hoặc 10,3% tương đối đúng công thức. |
| **Làm đẹp dashboard bằng đổi Done** | Trước Done sau test, sau Done ở merge. | Cycle time đẹp nhưng giá trị chưa giao. | Giữ DoD/ràng buộc start-finish nhất quán. |
| **Đếm task thay Increment** | Đóng 30 task nhưng UI chưa nối API. | Tối ưu output, không có phần mềm dùng được. | Đếm lát cắt tích hợp theo DoD và outcome. |
| **Bắt đầu nhiều, hoàn tất ít** | WIP cao, PBI nằm chờ review nhiều tuần. | Cycle time dài, người dùng chờ. | Kanban flow, hỗ trợ hoàn tất và giảm blocker. |
| **Review chỉ để “demo cho sếp”** | Không có phản hồi hoặc quyết định Product Backlog. | Không đóng vòng học. | Kiểm tra kết quả sản phẩm cùng stakeholder, thích ứng. |
| **Xây feature nhưng không đo outcome** | Release xong là đóng yêu cầu. | Không biết giả thuyết có giá trị. | Telemetry, usability, support feedback và mốc xem lại. |
| **Số liệu tốt đồng nghĩa nhân quả chắc** | Trước–sau cải thiện rồi gán riêng cho UI. | Có thể mở rộng sai giải pháp. | Ghi biến số nhiễu, thiết kế so sánh phù hợp. |
| **Không nhìn item còn mở** | PBI khó chờ lâu biến mất khỏi báo cáo Done. | Che rủi ro và nợ công việc. | Work item age, blocked và WIP. |
| **Bỏ qua incident để giữ Sprint Goal** | Lịch tạo trùng bị để tới Sprint sau. | Thiệt hại cho khách, nguy cơ bảo mật/dữ liệu. | Ứng cứu theo chính sách; thích ứng kế hoạch minh bạch. |
| **PO duyệt mọi kỹ thuật hoặc Developer tự đổi giá trị** | Quyền quyết định chồng chéo. | Trễ, xung đột hoặc bỏ trách nhiệm. | Làm rõ PO, Developers và thẩm quyền rủi ro/đầu tư. |
| **Thay mọi thứ cùng lúc** | Scrum, Kanban, XP, UI và architecture thay cùng ngày. | Khó biết cơ chế nào tác động. | Chia vòng học, ghi thay đổi đồng thời. |
| **Mở rộng trước khi chất lượng sẵn sàng** | Rollout rộng vì prototype được thích. | Hệ thống không bảo đảm an toàn hoặc vận hành. | DoD, contract tests, release guardrails và giám sát. |
| **Quyết định bị “khóa vì roadmap”** | Bằng chứng mới mâu thuẫn kế hoạch nhưng phải làm hết. | Sunk cost và sản phẩm lệch nhu cầu. | Cập nhật PBI/phạm vi/dự báo theo Product Goal. |
| **Mọi stakeholder có quyền chèn ticket** | Thứ tự thay mỗi ngày theo người nói lớn. | Chuyển ngữ cảnh, ít Increment. | Intake, quyền Product Owner và đánh đổi minh bạch. |
| **Sao chép Sprint của đội khác** | Không xét công việc khẩn, phụ thuộc hoặc năng lực. | Nghi thức không giúp flow. | Chọn Scrum/Kanban/XP và biến thể qua bối cảnh, kiểm chứng. |

### 22.1. “MVP” không có nghĩa bản thử chưa an toàn

Một **Minimum Viable Product (MVP)** hoặc lát cắt kiểm chứng nhỏ nhằm học với mức đầu tư hợp lý. Nó **không cấp ngoại lệ cho bảo mật, dữ liệu hoặc tính đúng đắn trọng yếu**.

Có thể thử:

- Prototype với dữ liệu giả để đánh giá khả năng hiểu.
- Pilot giới hạn khi đủ DoD và guardrails.
- Một loại lịch đơn thay vì mọi loại lịch.

Không nên thử:

- Cho một nhóm khách dùng giao dịch có nguy cơ đặt trùng đã biết.
- Đưa thông tin người khác cho khách xem để “kiểm tra phân quyền”.
- Gửi trạng thái Confirmed sai nhằm tăng tỷ lệ completion.

**Giới hạn tính năng là cách giảm phạm vi; không phải giảm trách nhiệm bảo vệ người dùng.**

### 22.2. Đừng ép mọi improvement phải là user story từ góc nhìn khách

Hạng mục **test concurrency** hoặc **sửa CI** có thể rất quan trọng cho Product Goal nhưng không cần bắt đầu bằng “Là khách, tôi muốn pipeline xanh”. Hãy ghi:

- Vấn đề kỹ thuật nào đang chặn tạo giá trị?
- Rủi ro hoặc thời gian chờ có bằng chứng?
- Phạm vi cải tiến tối thiểu?
- Tiêu chí xác nhận chất lượng/flow?
- Cách cân bằng với các PBI khác?

Một backlog tốt có thể chứa **feature, bug, enabler, discovery và công việc chất lượng**, miễn thứ tự và lý do rõ.

### 22.3. Không đặt một target tùy tiện làm lý do bỏ mục tiêu

Nếu một pilot giảm submit lặp từ 30% xuống 24%, nhưng nhóm đặt ngưỡng 20%, không nên nói “không tạo giá trị”; cũng không nên tự đổi target để báo đạt. Cần hỏi:

- Giảm sáu điểm phần trăm có ý nghĩa về người dùng/chi phí không?
- Mẫu số và mức bất định thế nào?
- Guardrails ra sao?
- Còn can thiệp nào có cơ hội tốt hơn với chi phí thấp?

**Một ngưỡng ra quyết định là công cụ đánh đổi**, không phải sự thật khoa học hoặc giấy phép bóp méo số liệu.

### 22.4. Có thể dừng một feature mà vẫn tiến tới Product Goal

Giả sử sau vài vòng, khách dùng tra cứu tốt và SMS không cải thiện thêm bao nhiêu, trong khi chi phí/đồng ý nhận tin trở thành rào cản. Product Owner có thể **loại PBI SMS khỏi thứ tự gần**, dành năng lực cho đối soát hoặc self-service đổi lịch đã có bằng chứng.

**Product Goal vẫn giữ**, trong khi tập hợp giải pháp thay đổi. Đó là tinh thần thích ứng dựa trên phản hồi, không phải thiếu cam kết.

## 23. Bài tập tình huống và đáp án định hướng

Các tình huống có thể làm cá nhân, theo cặp hoặc thảo luận nhóm. Với những câu hỏi ra quyết định sản phẩm, **có thể có nhiều phương án hợp lý** nếu nêu rõ căn cứ, ranh giới và điều kiện kiểm chứng.

### Bài 1 — Product Goal hay chỉ là danh sách đầu ra?

Một nhóm viết:

> “Product Goal quý tới: làm SMS, thêm bộ lọc chuyên gia, triển khai UI mới và hoàn thành 70 story points mỗi Sprint.”

**Câu hỏi:**

1. Câu này đang trộn những loại điều gì?
2. Viết lại một Product Goal cho nền tảng đặt lịch.
3. Nêu hai outcome và một quality guardrail.

**Hướng giải:** Câu gốc trộn feature, đầu ra và chỉ số năng lực nội bộ. Một Product Goal tốt hơn: “Khách có thể chọn, đặt và tự xác minh lịch tư vấn hợp lệ mà không phải phụ thuộc tổng đài.” Outcome có thể là completion rate theo phiên và lượt liên hệ hỏi trạng thái/100 phiên. Guardrail: không tạo lịch Confirmed trùng theo quy tắc, không lộ dữ liệu hoặc trạng thái sai.

### Bài 2 — Chọn vấn đề trước khi chọn tính năng

Stakeholder đề nghị gửi SMS ngay vì nhiều khách hỏi “Đặt lịch xong chưa?”. Dữ liệu cho thấy một số khách rời trang khi trạng thái Pending xuất hiện; hợp đồng API đối tác có thể timeout.

**Câu hỏi:**

1. Ít nhất ba giả thuyết nguyên nhân khác nhau?
2. Một phép thử nhanh cho từng giả thuyết?
3. Điều gì không nên đưa vào A/B test thiếu kiểm soát?

**Hướng giải:** (1) Khách hiểu sai Pending, (2) không có mã tra cứu, (3) backend không biết kết quả sau timeout. (1) thử usability, (2) prototype/quan sát hành vi, (3) thử API/contract trong sandbox. Không cố ý cho khách gặp giao dịch tạo trùng/sai trạng thái để đo conversion.

### Bài 3 — Viết giả thuyết có thể bị bác bỏ

Đề xuất:

> “Khách thích SMS vì tiện. Nếu làm SMS, sản phẩm sẽ thành công.”

**Câu hỏi:**

1. Điều gì còn mơ hồ?
2. Viết lại giả thuyết có nhóm khách, hành vi, bằng chứng và giới hạn.
3. Nêu dấu hiệu khiến giả thuyết cần sửa.

**Hướng giải:** Cần rõ nhóm người dùng, lý do liên hệ hỗ trợ, cơ chế và mẫu số đo. Ví dụ: “Với khách đặt lịch bằng điện thoại đã chọn nhận thông báo theo chính sách, nếu gửi xác nhận khi trạng thái có thẩm quyền thì lượt liên hệ hỏi kết quả/100 phiên sẽ giảm, vì khách có thông tin ngoài ứng dụng. Chúng tôi sẽ kiểm tra chi phí, quyền riêng tư, deliverability và không gửi sai trạng thái.” Nếu khách không hiểu thông báo hoặc liên hệ không giảm, phải xem lại.

### Bài 4 — Chia theo tầng hay theo giá trị?

Epic “Tự đổi lịch tư vấn” được chia:

- Story A: làm mọi màn hình đổi lịch.
- Story B: làm tất cả endpoint.
- Story C: tạo bảng database.
- Story D: test integration cuối quý.

**Câu hỏi:**

1. Vì sao cách chia này khiến feedback và Increment đến muộn?
2. Đề xuất ba lát cắt dọc.
3. Điều kiện nào không thể hoãn dù đang làm lát cắt đầu?

**Hướng giải:** Mỗi story theo tầng có thể Done riêng nhưng không tạo hành vi dùng được. Có thể chia: (1) xem điều kiện có được đổi, (2) đổi giờ một lịch đơn trong hạn hợp lệ, (3) xử lý trạng thái/đối soát timeout và mở rộng phạm vi. Tuy nhiên, bảo vệ không đặt trùng và trạng thái đúng **phải có trước hoặc cùng bất kỳ lát cắt nào đưa vào production chịu rủi ro**, không đẩy tất cả lỗi sang bước 3.

### Bài 5 — Từ story tới acceptance criteria

Story:

> “Là khách đã đặt lịch, tôi muốn tra cứu trạng thái bằng mã yêu cầu để không phải gửi lại thao tác đặt lịch.”

**Câu hỏi:**

1. Viết ít nhất bốn acceptance examples.
2. Chỉ ra một tiêu chí thuộc DoD chứ không phải hành vi nghiệp vụ của story.
3. Nêu một trường hợp quyền riêng tư.

**Hướng giải:** Trường hợp Pending không báo Confirmed; Confirmed hiển thị kết quả có thẩm quyền; Unknown hướng dẫn tra cứu/đối soát; mã không hợp lệ không lộ dữ liệu; tra cứu không tạo booking mới. Test tự động/contract/integration theo tiêu chuẩn nhóm là yếu tố DoD. Người không đủ quyền không thể xem thông tin lịch người khác chỉ bằng đoán mã.

### Bài 6 — Spike có phải Increment?

Team C dành hai ngày thử API đối tác và kết luận: “Không có API tra cứu kết quả sau timeout.” Product Owner nói “Vậy chúng ta đã hoàn thành một phần tính năng đổi lịch.”

**Câu hỏi:**

1. Đầu ra của spike là gì?
2. Có thể tính feature của khách đã hoàn tất không?
3. PBI và thiết kế có thể cần điều chỉnh thế nào?

**Hướng giải:** Spike tạo **kiến thức về giới hạn API** và giúp quyết định tiếp, không tự tạo hành vi đổi lịch cho khách. Cần cập nhật PBI, rủi ro, trạng thái Unknown và các phương án như hỗ trợ đối soát/đổi thiết kế/giảm phạm vi trước khi triển khai an toàn.

### Bài 7 — Done, deploy và release

UI tra cứu chạy với mock; endpoint đã merge; hợp đồng thật không được kiểm thử. Nhóm báo “Done và đã triển khai lên test environment”.

**Câu hỏi:**

1. Đã có Increment theo nghĩa Scrum chưa?
2. Còn thiếu những bằng chứng nào?
3. Khi nào có thể release cho khách thật?

**Hướng giải:** Chưa đủ căn cứ để gọi Increment nếu chưa đạt DoD chung, hành vi tích hợp và kiểm thử an toàn. Cần contract/integration tests, quyền dữ liệu, trạng thái thật, khả năng vận hành. Release khi đáp ứng DoD và các điều kiện release/tuân thủ thích hợp; Sprint Review không tự là gate bắt buộc.

### Bài 8 — Tính completion rate đúng mẫu số

Trong hai cửa sổ giả định:

| Chỉ số | Trước | Sau |
| --- | ---: | ---: |
| Phiên bắt đầu | 500 | 600 |
| Phiên Confirmed trong 24h | 325 | 420 |

**Câu hỏi:**

1. Completion rate từng kỳ?
2. Mức tăng tính bằng điểm phần trăm và phần trăm tương đối?
3. Vì sao chưa thể nói một feature cụ thể gây ra toàn bộ mức tăng?

**Đáp án:** \(325/500=65\%\); \(420/600=70\%\). Tăng **5 điểm phần trăm**, tương đương \((70-65)/65\times100\%\approx7{,}7\%\) tương đối. Các kỳ có thể khác người dùng, lưu lượng, chính sách, API và can thiệp cùng thời điểm; cần xem chất lượng/mẫu/biến số.

### Bài 9 — Đừng nhầm lượt hỗ trợ với số khách

Kỳ trước có 90 lượt gọi hỏi trạng thái trên 450 phiên bắt đầu. Kỳ sau có 72 lượt gọi trên 600 phiên.

**Câu hỏi:**

1. Lượt gọi/100 phiên trước và sau?
2. Mức giảm tuyệt đối và tương đối của rate?
3. Có được nói “40% khách không gọi nữa”?

**Đáp án:** Trước \(90/450\times100=20\); sau \(72/600\times100=12\) lượt/100 phiên. Giảm **8 lượt/100 phiên**, tương đương **40% giảm tương đối**. Không suy ra 40% khách duy nhất, vì một người/phiên có thể tạo nhiều lượt gọi.

### Bài 10 — Điều kiện an toàn bị bỏ khỏi lát cắt “nhỏ”

Nhóm muốn giao “đặt lịch cơ bản trong hai ngày” và để xử lý double-submit sang Sprint sau. QA đã chứng minh hai request có thể tạo hai booking Confirmed trùng slot.

**Câu hỏi:**

1. Đây là việc giảm phạm vi đúng hay giảm chất lượng?
2. Có thể làm một lát cắt nhỏ khác nào?
3. Lãnh đạo/PO nên đưa quyết định ra sao?

**Hướng giải:** Đó là **bỏ điều kiện an toàn thiết yếu**. Cần ứng cứu/sửa bất biến theo mức nghiêm trọng, test concurrency và không phát hành hành vi nguy hiểm. Có thể thử UX trên prototype/sandbox hoặc làm lát cắt đọc trạng thái an toàn, không đưa transaction mới chưa bảo vệ vào production. Product Owner chọn ưu tiên giá trị trong ranh giới, Developers giữ DoD và chuyên môn.

### Bài 11 — Xếp thứ tự theo điểm hay theo rủi ro?

Một bảng WSJF giả định:

| PBI | CoD tương đối | Job size | WSJF |
| --- | ---: | ---: | ---: |
| **A — Spike API timeout** | 15 | 3 | ? |
| **B — SMS xác nhận** | 9 | 6 | ? |
| **C — Trang tra cứu cơ bản** | 18 | 6 | ? |

Đồng thời có lỗi đặt trùng đã xác minh.

**Câu hỏi:**

1. Tính WSJF và thứ tự theo điểm.
2. Lỗi đặt trùng nên xử lý thế nào?
3. Vì sao spike có thể đứng trước feature?

**Đáp án:** A \(15/3=5\); B \(9/6=1{,}5\); C \(18/6=3\). Theo heuristic: A, C, B. Lỗi đặt trùng cần triage/khắc phục theo rủi ro và nghĩa vụ; không đem điểm số làm lý do trì hoãn sự cố. Spike có thể **mở khóa quyết định về an toàn/khả thi** cho C, nhưng không tự tạo nhiều giá trị người dùng hơn.

### Bài 12 — Một Sprint Goal đáng dùng

Product Goal là khách tự xác minh lịch đáng tin. Ba đề xuất Sprint Goal:

- A: “Làm xong 20 task”.
- B: “Giao UI, API, SQL, monitoring”.
- C: “Khách có thể kiểm tra trạng thái yêu cầu sau khi gửi mà không bấm lại Đặt lịch”.

**Câu hỏi:**

1. Đề xuất nào gần một Sprint Goal hướng kết quả hơn?
2. Cần kiểm tra gì để C khả thi?
3. Nếu C không đạt do API chưa an toàn, có được gọi các task Done là Increment không?

**Hướng giải:** C gần mục tiêu giá trị nhất. Cần làm rõ trạng thái có thẩm quyền, phụ thuộc, năng lực, acceptance criteria và DoD. Các phần task chưa tích hợp/không đạt DoD **không thể được tính là Increment đủ chất lượng**; forecast và backlog phải minh bạch.

### Bài 13 — Flow có đang đo đúng lát cắt?

Trong một tuần, Team A đóng 12 task, Team B đóng 9 task, Team C đóng 7 task. Sản phẩm chỉ có hai PBI tích hợp đạt DoD.

**Câu hỏi:**

1. Có thể báo “28 feature đã giao” không?
2. Nên đo thêm những gì?
3. Một cách giảm waiting có thể thử?

**Hướng giải:** Không: \(12+9+7=28\) task chứ không phải 28 feature. Đo cycle time PBI cấp sản phẩm, blocked duration, work item age, throughput PBI và outcome người dùng. Có thể phối hợp contract/integration sớm, giảm WIP của lát cắt liên nhóm và giúp tháo reviewer/CI bottleneck.

### Bài 14 — Little’s Law cho một dòng đủ ổn định

Một workflow có WIP trung bình **15 PBI**, throughput **5 PBI/tuần**. Giả sử ranh giới và điều kiện mô hình phù hợp.

**Câu hỏi:**

1. Thời gian trung bình trong hệ thống theo mô hình là bao nhiêu?
2. Nếu WIP giảm còn 10 và throughput giữ 5, kết quả xấp xỉ?
3. Có thể cam kết mọi PBI Done trong hai tuần không?

**Đáp án:** \(15/5=3\) tuần; \(10/5=2\) tuần. **Không** cam kết mọi PBI hoàn thành đúng hai tuần chỉ từ quan hệ trung bình; cần xem phân bố, loại việc, sự ổn định và việc còn mở.

### Bài 15 — Một giả thuyết không được xác nhận

Sau khi thêm mã tra cứu, submit-repeat rate không giảm; log cho thấy nhiều khách nhận được mã nhưng không tìm thấy chỗ tra cứu sau khi rời trang.

**Câu hỏi:**

1. Giả thuyết nào đang bị thách thức?
2. Có phải phải bỏ Product Goal?
3. Một lát cắt hoặc phép thử tiếp theo?

**Hướng giải:** H2 về mã tra cứu giảm gửi lặp chưa được hỗ trợ trong triển khai hiện tại. Không bỏ Product Goal chỉ vì một giải pháp chưa hiệu quả. Thử đường truy cập dễ tìm hơn, kiểm tra khả năng hiểu của khách, đo tác vụ tra cứu thành công, giữ ranh giới quyền và trạng thái đúng.

### Bài 16 — Multi-team và một PBI chung

Team A có giao diện trạng thái, B có API booking và C có adapter đối tác. A/B đều báo Done, C phát hiện timeout không trả kết quả có thẩm quyền.

**Câu hỏi:**

1. PBI cấp sản phẩm đã Done chưa?
2. Phải làm rõ contract nào?
3. Nếu các team cùng một sản phẩm dùng Scrum thì chia sẻ điều gì?

**Hướng giải:** Chưa đủ căn cứ Done nếu hành vi tích hợp và trạng thái an toàn chưa đạt. Cần hợp đồng Pending/Confirmed/Rejected/Unknown, quyền truy cập, retry/đối soát và test đầu-cuối. Các Scrum Team cùng một sản phẩm chia sẻ **Product Goal, Product Backlog, Product Owner** và cùng **Definition of Done**.

### Bài 17 — Pilot tốt không chứng minh nhân quả chắc chắn

Tỷ lệ Confirmed tăng từ 68% lên 75%. Cùng thời điểm, UI trạng thái đổi, API được sửa retry và một nhà cung cấp nâng độ ổn định.

**Câu hỏi:**

1. Có thể nói chính xác điều gì?
2. Không thể nói điều gì?
3. Muốn hiểu tác động riêng của UI phải làm gì?

**Hướng giải:** Có thể nói tỷ lệ quan sát tăng **7 điểm phần trăm** trong hai kỳ định nghĩa phù hợp. Không thể quy toàn bộ cải thiện cho UI. Cần thiết kế phân tích/so sánh phù hợp, giữ guardrails, xem nhóm người dùng/điều kiện mạng và đủ dữ liệu; có thể thử usability hoặc rollout an toàn theo mức rủi ro.

### Bài 18 — Product Goal có thể giữ dù roadmap thay

Nhóm đã đầu tư ba tuần vào SMS nhưng kết quả nghiên cứu mới cho thấy khách chủ yếu cần đối soát trạng thái chứ không cần thêm kênh. Giám đốc nói “đã bắt đầu thì phải làm hết”.

**Câu hỏi:**

1. Đây là nguy cơ ra quyết định nào?
2. Product Owner nên đưa ra những lựa chọn gì?
3. Điều gì có thể giữ nguyên?

**Hướng giải:** Có bẫy sunk cost. Cần đánh giá lợi ích/chi phí còn lại của SMS, ưu tiên đối soát khi có căn cứ, thu hẹp hoặc dừng SMS nếu không còn đáng đầu tư, tuân nghĩa vụ hợp đồng nếu có. **Product Goal khách tự xác minh lịch đáng tin** có thể vẫn giữ, còn giải pháp/backlog đổi.

### Bài 19 — Từ một feature chưa xác minh sang experiment canvas

Một yêu cầu mới: “Tất cả khách phải có nút Đặt lại ngay khi timeout”.

**Câu hỏi:**

1. Rủi ro nghiêm trọng nào của giải pháp này?
2. Viết giả thuyết nguyên nhân thay vì chốt feature.
3. Nêu phép thử và guardrail.

**Hướng giải:** Đặt lại không kiểm soát có thể tạo hai lịch khi request đầu vẫn được xử lý. Giả thuyết đúng hơn: khách cần biết request đã tới đâu và cách xác minh kết quả. Thử ngôn ngữ trạng thái/mã tra cứu với dữ liệu giả, kiểm thử idempotency/retry trong sandbox; guardrail không tạo lịch trùng, không hiển thị Confirmed giả. Chỉ đưa Retry an toàn khi contract và transaction cho phép.

### Bài 20 — Một Sprint Retrospective nên tạo gì?

Sau ba Sprint, nhóm thấy nhiều PBI tra cứu bị chặn ở integration test. Retrospective chỉ kết luận “mọi người cố gắng nhiều hơn”.

**Câu hỏi:**

1. Vì sao hành động này khó kiểm chứng?
2. Một cải tiến cụ thể và cách đo?
3. Có nên đổi Product Goal không?

**Hướng giải:** “Cố gắng” không sửa nút thắt hoặc tạo cơ chế kiểm tra. Thử contract tests chạy sớm, fixture dữ liệu an toàn, người phối hợp tháo môi trường test; đo blocked duration, cycle time, build stability và lỗi. Không cần đổi Product Goal nếu vấn đề là năng lực giao phần mềm, nhưng cần cập nhật Product Backlog/kế hoạch cho cải tiến kỹ thuật phù hợp.

## 24. Workshop 90–120 phút: từ Product Goal tới giả thuyết và Increment đầu tiên

### 24.1. Đề bài và điều kiện

Giả sử bạn là một Scrum Team hoặc một nhóm Agile đang phục vụ sản phẩm đặt lịch tư vấn. Product Goal được đề xuất:

> “Khách có thể tự đặt và biết chắc tình trạng lịch tư vấn hợp lệ mà không phải gọi tổng đài.”

Các bên cung cấp một bộ thông tin **giả định**:

- 1.000 phiên bắt đầu đặt lịch; 680 phiên có booking Confirmed trong 24 giờ.
- 850 phiên có submit; 255 phiên gửi lại cùng yêu cầu.
- 150 lượt liên hệ hỏi trạng thái; 2 lỗi tạo lịch trùng đã xác minh.
- 12/20 người trong một phiên usability hiểu Pending là thất bại.
- API đối tác có timeout, chưa rõ có hỗ trợ tra cứu/idempotency không.
- Nhóm trải nghiệm muốn làm SMS; nhóm Booking muốn sửa transaction; nhóm Integration muốn kiểm tra hợp đồng API.

**Nhiệm vụ:** Chuyển Product Goal thành **các cơ hội, giả thuyết và một chuỗi lát cắt tăng dần**. Không được bỏ qua lỗi đã biết hoặc tuyên bố đã có outcome khi chưa có bằng chứng.

### 24.2. Vai trò trong hoạt động

Nếu có nhiều người, phân công để tăng góc nhìn:

| Vai trò thảo luận | Trách nhiệm trong bài tập |
| --- | --- |
| **Product Owner / người phụ trách giá trị** | Nói rõ Product Goal, ưu tiên cơ hội/PBI và giải thích đánh đổi. |
| **Developers** | Đề xuất lát cắt, phụ thuộc, test, DoD và năng lực thực thi. |
| **Người hỗ trợ Scrum/flow** | Giữ cuộc thảo luận tập trung vào giả thuyết, minh bạch blocked và cải tiến. |
| **Đại diện khách/support** | Cung cấp những câu hỏi, hành vi và hệ quả người dùng. |
| **Chuyên gia kỹ thuật/vận hành** | Nêu bất biến, timeout, bảo mật, release và incident path. |
| **Người phản biện** | Hỏi kết quả nào có thể bác bỏ giả thuyết và dữ liệu nào còn thiếu. |

Nếu học cá nhân, hãy **lần lượt viết câu trả lời từ mỗi góc nhìn** thay vì chỉ đóng vai Developer hoặc Product Owner.

### 24.3. Các vòng thực hành

| Thời gian | Hoạt động | Đầu ra |
| --- | --- | --- |
| **0–10 phút** | Viết Product Goal, đối tượng, outcome và guardrails. | Một mục tiêu và ba tới năm tín hiệu quan trọng. |
| **10–25 phút** | Phân loại dữ liệu, lập opportunity map; đánh dấu sự cố cần ứng cứu. | Ba tới năm vấn đề có thứ tự và dữ liệu thiếu. |
| **25–40 phút** | Viết giả thuyết giá trị, usability, feasibility và cách bác bỏ. | Ba hypothesis cards, mỗi card có phép thử. |
| **40–55 phút** | Vẽ story map, chọn một lát cắt đầu-cuối. | Hành trình người dùng, phạm vi trong/ngoài slice. |
| **55–70 phút** | Viết PBI, user story, Given–When–Then và DoD. | Một hạng mục có thể triển khai/kiểm chứng. |
| **70–85 phút** | Sắp thứ tự backlog, chọn Sprint Goal hoặc flow policy phù hợp. | Một top backlog và kế hoạch phối hợp thực tế. |
| **85–100 phút** | Thiết kế thước đo outcome/flow/quality và release guardrails. | Metric contract và mốc quyết định. |
| **100–120 phút** | Mô phỏng thông tin mới, điều chỉnh giả thuyết và thứ tự. | Quyết định giữ/sửa/dừng có bằng chứng và đánh đổi. |

Có thể dùng 90 phút bằng cách rút ngắn phần phản biện hoặc chia nhóm chuẩn bị trước. **Không cần chạy cuộc họp theo đúng số phút này trong một dự án thật**; hãy giữ các câu hỏi và đầu ra cốt lõi.

### 24.4. Mẫu một trang: Product Goal → hypothesis → slice → evidence

~~~text
PRODUCT GOAL
  Nhóm người dùng:
  Giá trị/trạng thái tương lai mong muốn:
  Outcome indicators:
  Ranh giới an toàn và nghĩa vụ:

OPPORTUNITIES
  O1 - Vấn đề:
       Bằng chứng:
       Điều chưa biết:
  O2 - Vấn đề:
       Bằng chứng:
       Điều chưa biết:
  O3 - Vấn đề:
       Bằng chứng:
       Điều chưa biết:

HYPOTHESES
  H1 - Nếu ... thì ... vì ...
       Bằng chứng đủ cho quyết định nào:
       Điều có thể bác bỏ:
       Phép thử:
       Guardrails:
  H2 - ...
  H3 - ...

PRODUCT BACKLOG TOP ITEMS
  ID | Giá trị/rủi ro | Thứ tự và lý do | Phụ thuộc | Người phối hợp

NEXT SMALL SLICE
  Người dùng/hành vi:
  Phạm vi:
  Chưa thuộc phạm vi:
  User story hoặc mô tả PBI:
  Acceptance examples:
  Definition of Done áp dụng:
  Hợp đồng kỹ thuật và test:
  Có thể release trong điều kiện nào:

PLAN
  Sprint Goal / chính sách flow phù hợp:
  Work item đang chờ, WIP và năng lực:
  Các nguy cơ gây chặn:
  Ai quyết định gì:

EVIDENCE
  Primary outcome / mẫu số:
  Diagnostic / flow:
  Chất lượng và guardrails:
  Cửa sổ và nguồn dữ liệu:
  Giới hạn suy luận:
  Khi nào xem lại:

DECISION
  Quan sát được:
  Giữ / sửa / mở rộng / dừng / cần học thêm:
  Product Backlog thay đổi:
  Bước tiếp theo và lý do:
~~~

**Mẫu này không phải một artifact bắt buộc của Scrum.** Nó hỗ trợ người học nối các phần thực hành thành một câu chuyện có căn cứ, thay vì tạo nhiều bảng độc lập không liên hệ.

### 24.5. Bài nộp mẫu rút gọn

**Product Goal:** Khách tự đặt và tra cứu trạng thái đáng tin mà ít cần hỏi tổng đài.

**Outcome chính:** Tỷ lệ phiên Confirmed trong 24 giờ, submit-repeat rate trong phiên đã submit, lượt liên hệ hỏi trạng thái/100 phiên.

**Guardrail:** Không tạo lịch Confirmed trùng, không hiển thị Confirmed khi chưa có bằng chứng, bảo vệ quyền dữ liệu và khả năng vận hành.

**Opportunity chọn:** Khách hiểu nhầm trạng thái sau khi gửi yêu cầu.

**Giả thuyết H1:** “Nếu hiển thị Pending/Unknown với ngôn ngữ rõ và bước tra cứu, khách sẽ hiểu đúng kết quả hơn, giảm gửi lặp vì không cần thử lại để biết hệ thống nhận yêu cầu chưa.”

**Phép thử nhanh:** Usability test với bản mẫu trạng thái; không dùng sản phẩm chưa đủ chất lượng để thử lỗi giao dịch trên khách thật.

**Lát cắt PBI:** Một khách gửi yêu cầu cho lịch đơn được nhìn thấy trạng thái đúng từ API có thẩm quyền, có mã yêu cầu và hướng tra cứu an toàn.

**Acceptance examples:** Pending không là Confirmed; Unknown không suy ra thành công; mã không hợp lệ không lộ dữ liệu; tra cứu không tạo booking mới.

**DoD:** Tích hợp UI + API + test + bảo mật/khả năng vận hành theo tiêu chuẩn chung; không có phần chưa hoàn tất bị gọi Done.

**Phụ thuộc:** Kết luận spike timeout và policy idempotency; bảo vệ bất biến đã biết.

**Ưu tiên:** Xử lý rủi ro đặt trùng theo mức độ trước; kiểm tra API; làm rõ nội dung và trạng thái; sau đó mới xem SMS hoặc tự đổi lịch.

**Kế hoạch thực thi:** Chọn một Sprint Goal hướng trạng thái có thể dùng hoặc một flow policy phù hợp, điều chỉnh dựa năng lực; không chốt số story points giả để cam kết.

**Bằng chứng sau release:** So các tỷ lệ với mẫu số nhất quán, usability và phản hồi support, xem incident/test, công khai nhiễu.

**Quyết định:** Nếu hiểu trạng thái cải thiện nhưng gọi hỗ trợ không giảm, kiểm tra khả năng tra cứu sau khi rời trang và những nhóm khách đặc biệt trước khi mở rộng SMS.

### 24.6. Ba thẻ biến cố để phản biện kế hoạch

**Thẻ A — Sự cố đã xác minh:** Trong lúc demo, QA phát hiện hai booking Confirmed trùng slot khi retry. Người học phải chỉ ra **đường ứng cứu, trách nhiệm chất lượng, điều kiện không release, ảnh hưởng Sprint Goal và backlog**.

**Thẻ B — Giả thuyết bị bác bỏ:** Khách hiểu Pending đúng sau khi đổi text nhưng vẫn gọi vì không thể tra cứu sau khi đóng trang. Người học phải **giữ Product Goal, sửa giả thuyết/solution, chia lát cắt tra cứu** và nêu bằng chứng cần.

**Thẻ C — Thay đổi từ đối tác:** Contract API không hỗ trợ query trạng thái sau timeout. Người học phải **nêu giới hạn kỹ thuật, ranh giới slice, phương án Unknown/đối soát, quyền quyết định và forecast**; không tự nói Confirmed để kịp release.

### 24.7. Tiêu chí đánh giá bài thực hành

| Tiêu chí | Đạt khi… | Chưa đạt khi… |
| --- | --- | --- |
| **Product Goal** | Diễn đạt kết quả có giá trị, có đối tượng và hướng đo. | Chỉ là danh sách tính năng hoặc số ticket. |
| **Opportunity và giả thuyết** | Có bằng chứng, câu hỏi chưa biết, cơ chế và dấu hiệu bác bỏ. | Tính năng được coi như sự thật hiển nhiên. |
| **Phép thử** | Phù hợp câu hỏi và mức rủi ro, có đầu ra quyết định. | Prototype được gọi là bằng chứng production an toàn. |
| **Lát cắt** | Có hành vi end-to-end, phạm vi nhỏ và phụ thuộc rõ. | Chỉ chia UI/API/database hoặc cắt bỏ lỗi nghiêm trọng. |
| **Acceptance/DoD** | Nghiệp vụ có ví dụ kiểm tra, chất lượng chung không bị hạ. | Task merge là Done, không test trạng thái và quyền. |
| **Thứ tự và kế hoạch** | Giải thích giá trị, an toàn, học và năng lực. | Mọi mục High hoặc do người lớn tiếng chọn. |
| **Đo lường** | Mẫu số, ranh giới, guardrails và giới hạn suy luận rõ. | Chỉ đếm click hoặc thay định nghĩa khi kết quả xấu. |
| **Thích ứng** | Có quyết định giữ/sửa/dừng và cập nhật Product Backlog. | Giữ feature vì đã lỡ làm bất chấp phản hồi. |

### 24.8. Cách người hướng dẫn phản hồi

Đừng chỉ hỏi “có đủ biểu mẫu không?”. Hãy đặt những câu hỏi có thể làm thay đổi quyết định:

- **“Giả thuyết nào có thể sai?”**
- **“Nếu backend chưa biết trạng thái, khách sẽ thấy gì?”**
- **“Vì sao lát cắt này có giá trị mà không cần hoàn tất cả epic?”**
- **“Đâu là trường hợp không được phát hành dù mọi Developer đã code xong?”**
- **“Số liệu nào khiến các bạn bỏ ý tưởng SMS?”**
- **“Chúng ta đang đo nhiều lượt submit hay nhiều phiên?”**
- **“Nếu hai nhóm Done riêng nhưng chưa tích hợp, báo cáo thế nào?”**
- **“Ai có quyền quyết định đổi thứ tự và ai chịu trách nhiệm chất lượng?”**

**Mục tiêu workshop là luyện khả năng ra quyết định dựa trên bằng chứng và kiểm chứng chất lượng**, không phải tạo ra một phương án hoàn hảo bất biến.

## 25. Checklist trước, trong và sau mỗi vòng tăng trưởng nhỏ

### 25.1. Trước khi chọn hạng mục

- [ ] Có **Product Goal** diễn đạt giá trị và trạng thái tương lai của sản phẩm, không chỉ danh sách feature.
- [ ] Đã xác định người dùng, tác vụ/hành trình và vấn đề cần giải quyết.
- [ ] Có ít nhất một nguồn bằng chứng cho vấn đề hoặc nêu rõ đây là giả định.
- [ ] Có **outcome và guardrails** liên hệ trực tiếp Product Goal.
- [ ] Đã phân biệt **vấn đề/cơ hội** với **phương án giải quyết** được đề xuất.
- [ ] Có bản đồ cơ hội và các phương án hợp lý, không chỉ một giải pháp được áp đặt.
- [ ] Những lỗi nghiêm trọng đã xác minh được **triage/ứng cứu** thay vì chờ thử nghiệm thị trường.
- [ ] Product Owner, Developers và người có quyền rủi ro/đầu tư hiểu phạm vi trách nhiệm.
- [ ] Product Backlog có thứ tự dựa trên giá trị, rủi ro, bất định, phụ thuộc và năng lực.

### 25.2. Trước khi thử giả thuyết

- [ ] Giả thuyết có nhóm người dùng, bối cảnh, can thiệp và kết quả dự đoán.
- [ ] Có điều kiện có thể **bác bỏ hoặc làm yếu giả thuyết**.
- [ ] Đã chọn thử nghiệm phù hợp: phỏng vấn, prototype, spike hay Increment thật.
- [ ] Không đưa prototype chưa đủ chuẩn vào production chỉ để có dữ liệu.
- [ ] Có timebox, phạm vi, người tham gia, nguồn dữ liệu và đầu ra quyết định.
- [ ] Có metric contract: mẫu số, thời gian, điểm bắt đầu/kết thúc và loại việc.
- [ ] Có guardrails bảo mật, dữ liệu, chất lượng, vận hành và trách nhiệm đối với người dùng.
- [ ] Có người có quyền dừng/thay đổi thử nghiệm và đường incident response.
- [ ] Không coi việc “đã nghiên cứu” là bằng chứng feature đã đạt DoD.

### 25.3. Khi chia lát cắt và làm rõ PBI

- [ ] Story map thể hiện hành trình và hành vi người dùng, không chỉ cấu trúc các nhóm kỹ thuật.
- [ ] Lát cắt có **giá trị hoặc giảm rủi ro có nghĩa** và đủ nhỏ để tích hợp sớm.
- [ ] Có phần **trong phạm vi/ngoài phạm vi** được công khai.
- [ ] Điều kiện an toàn thiết yếu không bị loại bỏ để lát cắt trông nhỏ hơn.
- [ ] PBI/story có mục đích, đối tượng, hành vi và các giả định mở.
- [ ] Acceptance criteria có ví dụ cho thành công, lỗi, trạng thái chưa xác định và quyền khi phù hợp.
- [ ] Quy tắc nghiệp vụ và bất biến được làm rõ với chuyên gia miền.
- [ ] Phụ thuộc API, dữ liệu, môi trường, nhân sự và các team được thể hiện.
- [ ] Có tiêu chuẩn **Definition of Done** chung phù hợp, tách khỏi acceptance criteria của riêng một PBI.
- [ ] Các việc discovery, spike, bug và enabler được mô tả đúng bản chất, không ép thành user story giả.

### 25.4. Khi lập kế hoạch và tạo Increment

- [ ] Sprint Goal hoặc chính sách flow đang dùng giúp nhóm tập trung **hoàn tất giá trị**.
- [ ] Nếu dùng Scrum, trách nhiệm Product Owner/Developers/Scrum Master, events, artifacts và commitments được hiểu đúng.
- [ ] Developers lập và thích ứng Sprint Backlog trong Scrum; không nhận danh sách task ép xuống không thể thương lượng.
- [ ] Nếu dùng Kanban, workflow, WIP, điểm chờ và work item age có nghĩa và có chính sách rõ.
- [ ] Nếu dùng XP/TDD/CI, test có ý nghĩa, pipeline đáng tin và giảm rủi ro kỹ thuật.
- [ ] Có hợp đồng trạng thái và kiểm thử tích hợp sớm giữa UI/Booking/đối tác.
- [ ] **Code merge, task Done, Increment đạt DoD và release** không bị gọi lẫn.
- [ ] Khi nhiều Scrum Teams cùng một sản phẩm: chia sẻ Product Goal, Product Backlog, Product Owner và cùng tuân DoD.
- [ ] Không đẩy kiểm thử quan trọng hoặc lỗi dữ liệu đã biết sang Sprint khác chỉ để báo hoàn thành.
- [ ] Release khi có đủ điều kiện chất lượng/vận hành/pháp lý; Sprint Review không được coi là gate bắt buộc của Scrum.
- [ ] Có cách theo dõi và khắc phục hậu quả của dữ liệu/giao dịch; không coi feature flag là rollback toàn diện.

### 25.5. Sau khi có phản hồi

- [ ] Outcome được đo bằng hành vi/trạng thái có thẩm quyền, không chỉ click.
- [ ] Mẫu số và cửa sổ quan sát nhất quán khi so trước–sau.
- [ ] Điểm phần trăm và phần trăm tương đối được tính/ghi khác nhau chính xác.
- [ ] Có xem dữ liệu chưa hoàn tất, blocked, WIP và các hạng mục có thời gian chờ dài.
- [ ] Có kiểm tra guardrails: lỗi, bảo mật, trạng thái sai, tải hỗ trợ và vận hành.
- [ ] Có đọc phản hồi định tính từ khách và người thực hiện, kể cả bằng chứng trái dự đoán.
- [ ] Những thay đổi đồng thời, mùa vụ, sự cố và khác biệt mẫu đã được ghi.
- [ ] Không suy diễn quan hệ nhân quả chỉ từ dữ liệu trước–sau.
- [ ] Có quyết định cụ thể: **giữ, sửa, thử thêm, mở rộng có kiểm soát hoặc dừng**.
- [ ] Product Backlog và dự báo được cập nhật khi bằng chứng làm thay đổi lựa chọn.
- [ ] Những giả thuyết sai được coi là **kiến thức giúp tránh lãng phí**, không bị che để giữ roadmap.
- [ ] Nhóm chọn vòng tiếp theo theo **Product Goal và giới hạn hiện tại**, không theo số story points cần báo.

## 26. Ghi nhớ cốt lõi

Một Product Goal hữu ích không tự biến thành các Increment chỉ bằng cách chia thành thật nhiều ticket. Cần nối **mục tiêu giá trị → vấn đề thực → giả thuyết có thể bác bỏ → phép thử phù hợp → lát cắt có giá trị → Increment đạt chất lượng → phản hồi và quyết định tiếp theo**.

Sáu nguyên tắc thực hành:

1. **Bắt đầu từ kết quả người dùng, không từ tính năng.** SMS, nút Retry hay một màn hình mới chỉ là phương án; điều quan trọng là khách có thể đặt và xác minh lịch an toàn.
2. **Làm rõ điều chưa biết trước khi đầu tư lớn.** Một prototype, phỏng vấn hoặc spike có timebox có thể bác bỏ giả định sớm; nhưng chỉ phần mềm đạt DoD mới là Increment thích hợp.
3. **Chia dọc theo giá trị, không chỉ ngang theo tầng.** UI, API, dữ liệu, hợp đồng và test cần cùng tạo hành vi đầu-cuối có thể kiểm chứng.
4. **Nhỏ không đồng nghĩa chất lượng thấp.** Không được trì hoãn bảo vệ idempotency, quyền dữ liệu, trạng thái có thẩm quyền hoặc xử lý incident đã biết.
5. **Đo outcome, flow và chất lượng cùng nhau.** Completion, repeat, support contact, cycle time và guardrails có mẫu số/ranh giới riêng; tránh gán toàn bộ kết quả trước–sau cho một feature.
6. **Để bằng chứng thay đổi backlog.** Khi giả thuyết sai, cần sửa/loại lựa chọn; khi rủi ro hoặc phụ thuộc mới xuất hiện, cần điều chỉnh phạm vi và dự báo thay vì giữ danh sách feature bất biến.

**Scrum** giúp phối hợp qua Product Goal, Product Backlog, Sprint Goal, Increment/DoD và kiểm tra/thích ứng. **Kanban** giúp quản lý WIP, flow và thời gian chờ. **XP** giúp bảo vệ khả năng giao tăng dần bằng TDD, CI, refactoring và cộng tác kỹ thuật. Không framework nào thay thế được **việc hiểu người dùng, ra quyết định theo bằng chứng và giữ chất lượng sản phẩm**.

> **Một vòng Agile tốt không nhất thiết giao nhiều tính năng hơn. Nó giao một phần giá trị nhỏ đủ an toàn, cho thấy rõ điều gì đã học, và giúp nhóm chọn bước tiếp theo tốt hơn.**

### Tài liệu tham khảo nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị của Agile: con người và tương tác, phần mềm hoạt động, cộng tác với khách hàng, đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao phần mềm có giá trị thường xuyên, hợp tác, chất lượng kỹ thuật, nhịp bền vững và tự cải tiến.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal/Product Backlog, Sprint Goal/Sprint Backlog, Increment/Definition of Done, các Scrum events và trách nhiệm.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, cycle time, work item age và cải tiến dòng.
- [Scrum.org — The Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams) — cách dùng chiến lược Kanban hỗ trợ Scrum mà vẫn giữ các thành phần của Scrum.
- [DORA](https://dora.dev/) — tham khảo các năng lực giao thay đổi phần mềm và độ ổn định vận hành.
- Jeff Patton (2014), *User Story Mapping* — bản đồ hành trình và chia lát cắt mang giá trị tăng dần.
- Teresa Torres (2021), *Continuous Discovery Habits* — liên kết outcome, opportunity, giả thuyết giải pháp và thử nghiệm liên tục.
- Kent Beck (2004), *Extreme Programming Explained: Embrace Change*, ấn bản thứ hai — các nguyên tắc và thực hành XP.
- Nicole Forsgren, Jez Humble và Gene Kim (2018), *Accelerate* — năng lực giao phần mềm và chất lượng tổ chức.
- Don Reinertsen (2009), *The Principles of Product Development Flow* — tư duy dòng giá trị, hàng đợi, chi phí trì hoãn và đánh đổi.
