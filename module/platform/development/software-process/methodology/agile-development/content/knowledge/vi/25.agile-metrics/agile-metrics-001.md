# Chọn chỉ số theo câu hỏi và quyết định cần hỗ trợ

## 1. Đo lường Agile để quyết định tốt hơn, không phải để làm đẹp bảng số

Một nhóm phát triển nền tảng học trực tuyến đang nhận được ba ý kiến:

- Product Owner hỏi: “Người học mới có **bắt đầu học được** sau khi đăng ký khóa không?”
- Developers hỏi: “Tại sao những user story tưởng nhỏ lại **tồn tại lâu** trước khi Done?”
- Người phụ trách vận hành hỏi: “Tính năng mới có làm **tăng lỗi đăng ký và mất dữ liệu** không?”

Nếu nhóm chỉ đưa ra một dashboard với velocity, số commit, số ticket Done và số lượt truy cập, cả ba câu hỏi quan trọng vẫn có thể chưa được trả lời. Dashboard có nhiều số **không đồng nghĩa** với khả năng ra quyết định tốt.

Trong **Agile**, đo lường nên giúp nhóm:

1. Hiểu người dùng có nhận giá trị mong muốn hay không.
2. Nhìn thấy dòng công việc và nguyên nhân chậm trễ.
3. Phát hiện nguy cơ chất lượng trước khi ảnh hưởng lớn.
4. Dự báo một cách có căn cứ nhưng không che giấu bất định.
5. Kiểm tra tác động của một cải tiến và điều chỉnh cách làm việc.

Chương **Đo lường Agile** của module **AGILE_DEVELOPMENT** hướng tới việc áp dụng giá trị và nguyên tắc Agile trong phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Các thực hành **user story, backlog, Scrum, Kanban, XP** chỉ tạo giá trị bền vững khi nhóm biết **quan sát kết quả thực tế**, không chỉ hoàn thành hoạt động theo kế hoạch.

**Nguyên tắc của bài:** *Bắt đầu bằng quyết định cần hỗ trợ, chuyển nó thành câu hỏi có thể kiểm chứng, rồi mới chọn chỉ số, dữ liệu và cách diễn giải.*

## 2. Phân biệt mục tiêu, câu hỏi, chỉ số, tín hiệu và quyết định

Năm khái niệm liên quan nhưng không thể dùng thay nhau:

| Khái niệm | Vai trò | Ví dụ về nền tảng học trực tuyến |
| --- | --- | --- |
| **Mục tiêu (goal)** | Kết quả có giá trị muốn đạt | Người học mới bắt đầu học thuận lợi hơn |
| **Câu hỏi (question)** | Điều chưa biết cản trở quyết định | Người đăng ký có mở bài học đầu tiên trong bảy ngày không? |
| **Chỉ số (metric)** | Định nghĩa phép đo cụ thể | Tỷ lệ người đăng ký hợp lệ mở bài đầu trong bảy ngày |
| **Tín hiệu/bằng chứng (evidence)** | Dữ liệu quan sát và ngữ cảnh đi kèm | 96/160 người học thuộc cohort đã đủ bảy ngày bắt đầu học |
| **Quyết định (decision)** | Hành động sau khi diễn giải bằng chứng | Thử cải tiến màn hình sau đăng ký; chưa đầu tư tính năng gợi ý lớn |

Chỉ số là một **cách tóm tắt dữ liệu**, không phải toàn bộ sự thật. Hai nhóm có cùng tỷ lệ đăng ký nhưng bối cảnh người học, chương trình, chiến dịch và chất lượng dữ liệu khác nhau có thể cần quyết định khác nhau.

### 2.1. Chỉ số có thể là kết quả hoặc đại diện

- **Outcome metric:** Đo kết quả người dùng hoặc sản phẩm quan tâm, chẳng hạn tỷ lệ bắt đầu học thành công.
- **Process/flow metric:** Đo cách công việc được tạo và hoàn tất, chẳng hạn cycle time của Product Backlog Item.
- **Quality metric:** Đo biểu hiện chất lượng, chẳng hạn tỷ lệ đăng ký bị lỗi hoặc lỗi nghiêm trọng sau phát hành.
- **Proxy metric:** Một tín hiệu thay thế khi chưa thể quan sát trực tiếp điều cần biết, ví dụ số lần bấm “Bắt đầu học” được dùng tạm để suy về khả năng học thực tế.

**Proxy không phải outcome** chỉ vì có tương quan. Một người bấm nút có thể gặp lỗi tải bài và chưa thật sự bắt đầu học.

### 2.2. Một con số không tự tạo ra quyết định

Nếu báo cáo “Cycle Time trung vị là 6 ngày” nhưng nhóm không biết mốc bắt đầu, mốc Done, loại công việc và cách định nghĩa ngày, thông tin rất khó dùng.

Nếu báo cáo “Cycle Time trung vị tăng từ 6 lên 8 ngày”, nhóm vẫn cần tìm lý do: có thêm item tích hợp phức tạp, thiếu môi trường, review bị nghẽn hay cách đo đã thay đổi?

**Kết luận không nên đến trước câu hỏi điều tra.**

## 3. Đi ngược từ quyết định: Goal → Question → Metric

Một cách lập luận hữu ích là **Goal–Question–Metric (GQM)**:

1. Xác định mục tiêu và người sẽ đưa ra quyết định.
2. Viết câu hỏi cụ thể có thể làm thay đổi hành động.
3. Chọn một hoặc vài phép đo đủ tin cậy để trả lời.
4. Định trước cách dùng kết quả và điều kiện cần kiểm tra thêm.

GQM là **phương pháp tư duy hữu ích**, không phải một sự kiện, artifact hay quy định bắt buộc trong Scrum.

~~~mermaid
flowchart TD
    A["Mục tiêu có giá trị"] --> B["Quyết định sắp phải đưa ra"]
    B --> C["Câu hỏi chưa được trả lời"]
    C --> D["Định nghĩa chỉ số và nguồn dữ liệu"]
    D --> E["Thu thập, xác minh, phân tích cùng ngữ cảnh"]
    E --> F{"Bằng chứng đủ để hành động?"}
    F -->|"Có"| G["Chọn hành động và nêu giả định"]
    F -->|"Chưa"| H["Học thêm hoặc sửa câu hỏi/phép đo"]
    H --> C
    G --> I["Theo dõi outcome và tác dụng phụ"]
    I --> A
~~~

### 3.1. Ví dụ tốt và chưa tốt

**Cách chưa tốt:**

> “Cần tăng velocity 20% trong hai Sprint tới vì chúng ta muốn nhóm Agile hơn.”

Chưa rõ tăng velocity sẽ tạo kết quả gì, vì sao 20% là hợp lý và việc tăng story points có giúp người học nhận giá trị không.

**Cách tốt hơn:**

> “Chúng ta muốn người học nhận cải tiến đăng ký sớm hơn. Có phải hàng chờ review và kiểm thử tích hợp đang làm những story nhỏ mất nhiều ngày mới Done? Hãy đo Work Item Age, Cycle Time phân theo công đoạn, WIP và thời gian chờ review trong bốn tuần, đồng thời theo dõi lỗi sau phát hành. Nếu review là điểm nghẽn, thử giảm WIP và cùng hoàn tất trước khi mở nhiều PBI mới.”

Ví dụ sau có **câu hỏi, phép đo, giả thuyết và hướng hành động** rõ ràng. Nó cũng đặt guardrail về chất lượng để không “nhanh hơn” bằng cách bỏ kiểm thử.

### 3.2. Một bảng lập kế hoạch đo từ quyết định

| Quyết định đang cân nhắc | Câu hỏi dẫn tới quyết định | Chỉ số ban đầu | Tín hiệu đối chiếu |
| --- | --- | --- | --- |
| Ưu tiên cải thiện bước sau đăng ký hay thêm gợi ý khóa học? | Người đăng ký bị rơi ở bước nào trước khi học? | Tỷ lệ bắt đầu bài đầu trong bảy ngày theo cohort | Phỏng vấn, lỗi mở bài, phân khúc người mới |
| Giảm WIP ở bước phát triển? | Công việc có già đi vì hàng chờ không? | WIP, Work Item Age, Cycle Time | Trạng thái blocked, review queue, throughput |
| Đầu tư sửa pipeline CI? | Kiểm thử chậm hoặc không ổn định có gây trễ Done? | Thời gian đến phản hồi CI, tỷ lệ flaky | Thời gian chờ PR, lỗi tích hợp thoát ra staging |
| Có thể dự báo đợt phát hành tiếp theo? | Năng lực hoàn tất thực tế và độ biến động thế nào? | Throughput theo kỳ, phân bố Cycle Time | Phạm vi thay đổi, WIP, rủi ro phụ thuộc |
| Có nên mở rộng rollout chức năng mới? | Chức năng có đủ an toàn và mang lại giá trị? | Outcome người dùng và tỷ lệ lỗi theo nhóm | Guardrail dữ liệu, vận hành, nghiên cứu người dùng |

## 4. Năm kiểm tra trước khi nhận một chỉ số vào dashboard

**Kiểm tra 1 — Có quyết định cụ thể không?** Nếu chỉ số tăng, giảm hoặc giữ nguyên thì ai sẽ làm gì khác? Nếu không có hành động nào, xem lại có cần đo không.

**Kiểm tra 2 — Nó thực sự phản ánh khái niệm cần biết không?** Số đăng ký mới có thể đo mức quan tâm, nhưng không cho biết người đăng ký có học được. Đừng đặt tên “mức thành công học tập” cho số lượt bấm.

**Kiểm tra 3 — Định nghĩa có thể lặp lại không?** Phải biết đơn vị đo, tử số/mẫu số, mốc thời gian, ranh giới workflow, loại item và dữ liệu ngoại lệ.

**Kiểm tra 4 — Hành vi tối ưu sai có thể xuất hiện không?** Nếu thưởng cho số story Done, nhóm có thể chỉ nhận việc dễ hoặc chia task giả tạo. Nếu thưởng cho số lỗi thấp, người ta có thể ngừng ghi nhận lỗi.

**Kiểm tra 5 — Có tín hiệu cân bằng không?** Tối ưu tốc độ cần theo dõi chất lượng; tối ưu conversion cần theo dõi lỗi và quyền người dùng; tối ưu số cuộc thử nghiệm cần xem giá trị học hỏi thật.

Một chỉ số tốt không nhất thiết là chỉ số dễ đo nhất. Nhưng phép đo quá đắt, thiếu độ tin cậy hoặc không thể dẫn tới hành động cũng không phù hợp.

## 5. Chọn loại chỉ số theo cấp độ câu hỏi

| Nhóm câu hỏi | Ví dụ quyết định | Chỉ số có thể dùng | Không nên suy ra |
| --- | --- | --- | --- |
| **Giá trị sản phẩm** | Nên đầu tư vào trải nghiệm nào? | Activation, task success, retention theo định nghĩa | Nhiều click chắc chắn là nhiều giá trị |
| **Dòng công việc** | Nút nghẽn ở đâu, có nên giảm WIP? | WIP, Work Item Age, Cycle Time, Throughput | Nhiều item Done chắc chắn tạo nhiều giá trị |
| **Chất lượng** | Đã đủ tin cậy để mở rộng phát hành? | Lỗi sau phát hành, sự cố, tỷ lệ yêu cầu thất bại | Ít bug được báo nghĩa là không có bug |
| **Năng lực kỹ thuật** | CI/refactoring có giúp thay đổi an toàn? | Thời gian phản hồi CI, thời gian tích hợp, lỗi hồi quy | Nhiều commit nghĩa là Dev giỏi |
| **Dự báo** | Có thể hoàn tất phạm vi nào trước mốc? | Throughput lịch sử, phân bố thời gian, số item còn lại | Một giá trị trung bình là cam kết chắc chắn |
| **Sức khỏe phối hợp** | Nhịp làm có bền vững và minh bạch? | Hàng chờ, gián đoạn, khảo sát nhóm, sự cố lặp | Một điểm khảo sát thay thế mọi trao đổi |

**Đừng cố gộp mọi nhóm vào một “Agile score” duy nhất.** Chỉ số tổng hợp có thể làm biến mất mâu thuẫn cần nhìn thấy, ví dụ throughput cao nhưng lỗi dữ liệu cũng tăng.

## 6. Viết hợp đồng đo lường trước khi thu thập

Một **metric definition** hoặc *measurement contract* ngắn giúp các nhóm so sánh cùng nghĩa.

| Trường | Nội dung cần có |
| --- | --- |
| **Tên metric** | Tên mô tả đúng hành vi được đo |
| **Quyết định** | Ai dùng kết quả, để chọn hành động nào |
| **Câu hỏi** | Điều chưa biết metric sẽ hỗ trợ trả lời |
| **Công thức** | Tử số/mẫu số, đơn vị, phép làm tròn |
| **Đối tượng** | Loại item, nhóm người dùng, cohort hoặc môi trường |
| **Ranh giới thời gian** | Khi nào bắt đầu/kết thúc; ngày lịch hay ngày làm việc |
| **Nguồn dữ liệu** | Event, hệ thống quản lý công việc, CI, logs |
| **Loại trừ** | Bot, dữ liệu lỗi, item loại khác; lý do loại trừ |
| **Độ tin cậy** | Dữ liệu thiếu, trùng, thay đổi schema, cỡ mẫu |
| **Chu kỳ xem** | Hằng ngày, hằng tuần, sau một rollout hoặc theo cohort |
| **Guardrail** | Rủi ro không được làm xấu khi cải tiến metric chính |
| **Hành động** | Nếu có tín hiệu, bước điều tra/quyết định tiếp theo |

### 6.1. Ví dụ đặc tả tỷ lệ bắt đầu học

~~~yaml
# YAML mô tả phép đo, không phải cấu hình tự động cho một công cụ.
metric: first_lesson_activation_7d
question: "Người đăng ký hợp lệ có bắt đầu bài đầu trong 7 ngày?"
unit: "phan_tram"
numerator: "So nguoi hoc du dieu kien da bat dau bai dau trong 7 ngay"
denominator: "So nguoi hoc dang ky hop le trong cohort du 7 ngay"
cohort: "Ngay dang ky lan dau theo mui gio da thong nhat"
exclusions: "Tai khoan thu nghiem, bot duoc xac dinh hop le"
source: "Enrollment events va lesson-start events da duoc kiem tra"
cadence: "Hang tuan, chi doc cohort da truong thanh du 7 ngay"
guardrails:
  - "Ty le loi dang ky"
  - "Ty le loi mo bai"
  - "Su co quyen truy cap du lieu"
decision: "Thu nghiem cai thien buoc sau dang ky neu co rao can"
~~~

Trong hệ thống thực, cần dùng tên trường, cách phân biệt người dùng và sự kiện hợp lệ chính xác hơn. Đặc tả trên **không phải tài liệu dữ liệu triển khai được trực tiếp**; nó giúp mọi người thống nhất phép đo trước khi viết query.

### 6.2. Vì sao đơn vị và mốc đo quan trọng?

“Cycle time 6 ngày” khác nhau nếu một nhóm đếm từ *In Progress* đến *Done* theo **ngày làm việc**, nhóm khác đếm từ lúc PBI được tạo đến khi phát hành theo **ngày lịch**.

“60% người học bắt đầu trong bảy ngày” phải cho biết cohort nào đã **đủ bảy ngày quan sát**. Nếu tính cả người mới đăng ký sáng nay, tỷ lệ dễ thấp giả vì họ chưa có đủ thời gian.

### 6.3. Ranh giới thay đổi thì ghi phiên bản định nghĩa

Nếu nhóm đổi cột bắt đầu hoặc thay sự kiện xác nhận đã mở bài, chuỗi thời gian có thể **không còn so sánh trực tiếp**. Đừng âm thầm nối số cũ với số mới như cùng một định nghĩa. Ghi ngày thay đổi, lý do và ảnh hưởng tới diễn giải.

## 7. Bốn flow metrics quan trọng trong Kanban

Kanban thường dùng bốn chỉ số cơ bản để nhìn dòng công việc:

1. **Work in Progress (WIP):** Số công việc đã bắt đầu nhưng chưa hoàn tất tại thời điểm đo.
2. **Throughput:** Số công việc thật sự hoàn tất trong một khoảng thời gian.
3. **Work Item Age:** Thời gian một item đang làm đã trôi qua kể từ mốc bắt đầu.
4. **Cycle Time:** Thời gian từ bắt đầu tới hoàn tất của một item đã Done.

Để đo đúng, nhóm cần định nghĩa **workflow**, điểm bắt đầu, điểm kết thúc, chính sách Done và đơn vị thời gian.

~~~mermaid
flowchart LR
    A["Product Backlog<br/>Chưa bắt đầu"] --> B["Đang phát triển<br/>WIP"]
    B --> C["Review và kiểm thử<br/>WIP"]
    C --> D["Done<br/>Đạt tiêu chuẩn hoàn tất"]
    C -->|"Phát hiện lỗi"| B
~~~

*Sơ đồ chỉ mô tả một workflow minh họa. Trạng thái Blocked nằm trong phạm vi WIP nếu item đã bắt đầu mà chưa Done.*

### 7.1. Work in Progress — WIP

Nếu cuối ngày có 8 item đã qua điểm bắt đầu và chưa qua điểm Done thì **WIP tại thời điểm đó là 8**. Một item chờ review, chờ môi trường hoặc bị chặn vẫn là WIP.

**Quyết định có thể hỗ trợ:** Nhóm có cần giảm lượng việc khởi động và tập trung xử lý hàng chờ thay vì nhận thêm PBI mới?

**Không nên suy ra:** WIP thấp luôn tốt trong mọi bối cảnh; nếu WIP quá thấp vì thiếu đầu vào hay có người không thể làm việc, hệ thống cũng có thể gặp vấn đề. Giới hạn WIP cần phù hợp năng lực và chính sách phục vụ.

### 7.2. Throughput

Nếu tuần này có 5 item đạt Done theo ranh giới đã thống nhất, **throughput là 5 item/tuần**.

**Quyết định có thể hỗ trợ:** Khi cần lập kế hoạch phạm vi, năng lực hoàn tất đã quan sát là bao nhiêu và biến động ra sao?

**Không nên suy ra:** 5 item lớn hơn 4 item chắc chắn có năng suất hoặc giá trị cao hơn. Loại công việc, kích thước item và chất lượng cần được xem cùng.

### 7.3. Work Item Age

Nếu một item bắt đầu 9 ngày làm việc trước và hiện chưa Done, **tuổi công việc là 9 ngày làm việc** theo cách đếm của nhóm. Tuổi tiếp tục tăng khi item Blocked, trừ khi workflow có chính sách đo khác được định nghĩa và công bố rõ.

**Quyết định có thể hỗ trợ:** Item nào đang có nguy cơ kéo dài, nằm ở bước nào, cần hỗ trợ review hoặc gỡ phụ thuộc?

**Không nên suy ra:** Item có tuổi 9 ngày đã “hoàn thành 90%” hoặc chỉ còn một ngày nếu SLE là 10 ngày.

### 7.4. Cycle Time

Nếu một item bắt đầu vào mốc được chọn và sau 6 ngày làm việc đạt Done, **cycle time là 6 ngày làm việc** theo chính sách đếm của nhóm.

**Quyết định có thể hỗ trợ:** Phân bố thời gian hoàn tất có giảm sau cải tiến WIP, review, kiểm thử hay không?

**Không nên suy ra:** Cycle time chỉ của những item đã hoàn tất phản ánh tất cả công việc đang còn dở; cần xem **Work Item Age** để tránh bỏ sót item khó kéo dài.

### 7.5. Lead Time là gì?

**Lead Time** phụ thuộc điểm bắt đầu được chọn. Với góc nhìn người dùng, nhóm có thể đo từ lúc yêu cầu được tiếp nhận đến khi nhu cầu được đáp ứng; khoảng này thường bao gồm cả thời gian chờ **trước khi bắt đầu phát triển**.

Không nên tự đồng nhất lead time của yêu cầu với **lead time for changes** trong ngữ cảnh giao hàng kỹ thuật, vì mốc bắt đầu và mục đích đo có thể khác. Luôn ghi rõ **từ đâu tới đâu**.

## 8. Dùng phân bố Cycle Time thay cho chỉ một số trung bình

Người hỏi “mất bao lâu để hoàn tất một story?” thường muốn biết mức bất định, không chỉ giá trị trung bình.

### 8.1. Bộ dữ liệu minh họa

Giả sử có 20 PBI đã Done thuộc loại tương đồng, cycle time tính bằng **ngày làm việc** và xếp tăng dần:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

| Thống kê | Giá trị | Diễn giải |
| --- | ---: | --- |
| Số quan sát | 20 | Mẫu nhỏ dùng cho học phương pháp |
| Trung vị | 6 ngày | Giá trị ở vị trí 10 và 11 đều bằng 6 |
| P85 theo nearest-rank | 10 ngày | Vị trí \(\lceil0{,}85\times20\rceil=17\) |
| P95 theo nearest-rank | 13 ngày | Vị trí \(\lceil0{,}95\times20\rceil=19\) |
| Lâu nhất | 18 ngày | Một trường hợp đuôi dài cần hiểu bối cảnh |

Trong mẫu, **17/20 = 85%** item hoàn tất trong **không quá 10 ngày làm việc**.

Phân vị tính theo *nearest-rank* ở đây là một cách tính cụ thể; phần mềm khác có thể dùng phương pháp nội suy cho kết quả khác trên mẫu nhỏ. Báo cáo thực cần công bố phương pháp, số quan sát và phạm vi item.

### 8.2. Service Level Expectation — SLE

Một **SLE** có thể được diễn đạt:

> “Đối với loại user story đã định nghĩa, từ lúc vào Đang thực hiện đến lúc đạt Done, chúng tôi kỳ vọng khoảng **85% hạng mục hoàn tất trong không quá 10 ngày làm việc**.”

Phát biểu phải có **mức kỳ vọng/xác suất, mốc thời gian và ranh giới đo**. Khi có dữ liệu, SLE có thể dựa trên phân bố quá khứ; khi chưa có, nhóm có thể đưa ra một **giả thuyết SLE ban đầu** rồi kiểm chứng, chứ không giả vờ đã đo được xác suất.

SLE **không phải SLA** hợp đồng, không phải deadline tuyệt đối và không phải bằng chứng 85% item tương lai chắc chắn sẽ đạt mốc trong mọi điều kiện.

### 8.3. So sánh Work Item Age với SLE

Giả sử hiện có:

| Item còn dở | Work Item Age | Trạng thái | Ý nghĩa cần điều tra |
| --- | ---: | --- | --- |
| A — Sửa nhãn khóa | 2 ngày | Kiểm thử | Còn mới, theo dõi bình thường |
| B — Lưu yêu thích | 9 ngày | Chờ review | Gần mốc tham khảo 10 ngày, ưu tiên gỡ hàng chờ |
| C — Đồng bộ đăng ký | 12 ngày | Blocked | Đã vượt mốc, cần xem nguyên nhân và tác động |
| D — Bộ lọc khóa học | 4 ngày | Phát triển | Theo dõi và phối hợp |

**9/10 = 90% mốc SLE** không phải “90% đã làm xong” và **không phải xác suất trễ là 90%**. Item C 12 ngày cũng không thể lấy \(10-12=-2\) rồi suy về thời gian còn lại.

SLE mô tả phân bố **thời gian hoàn tất của item**, còn dự báo thời gian còn lại cho một item **đã tồn tại lâu mà chưa Done** đòi hỏi quan sát trạng thái thực và, nếu định lượng, phương pháp điều kiện phù hợp. Tập cycle time chỉ gồm item Done dễ thiên lệch khi những item khó vẫn nằm trong WIP.

## 9. Little's Law và câu hỏi “WIP có làm chậm dòng công việc?”

Với hệ thống đo nhất quán và đủ ổn định, **Little's Law** nối các đại lượng trung bình:

\[
\text{WIP trung bình}
\approx
\text{Throughput trung bình}
\times
\text{Cycle Time trung bình}
\]

Ví dụ độc lập với bộ dữ liệu ở mục trước: trong một luồng đủ ổn định, WIP trung bình là **8 item**, throughput trung bình là **4 item/tuần**:

\[
\text{Cycle Time trung bình}
\approx
\frac{8\ \text{item}}{4\ \text{item/tuần}}
=2\ \text{tuần}
\]

Phép tính giúp thảo luận việc **giảm công việc dở dang và hàng chờ** để tăng khả năng hoàn tất. Tuy nhiên:

- Đây là quan hệ **trung bình**, không cho P85 hoặc SLE.
- Không phải cứ giảm một nửa WIP là mọi item tự nhanh gấp đôi.
- Nếu lượng việc vào/ra, loại item hoặc ranh giới thay đổi mạnh, cần kiểm tra điều kiện áp dụng.
- Không dùng chỉ số để ép nhân viên “lúc nào cũng bận 100%” vì điều đó có thể làm hàng chờ tăng.

**Quyết định phù hợp:** Thử giới hạn WIP tại một công đoạn nghẽn, quan sát age/cycle time/throughput và chất lượng qua nhiều kỳ thay vì chỉ xem một tuần.

## 10. Dự báo thời gian và phạm vi cần phản ánh bất định

Giả sử backlog có **20 item còn lại**, và throughput bốn tuần gần đây là:

~~~text
Tuần 1: 3 item Done
Tuần 2: 5 item Done
Tuần 3: 2 item Done
Tuần 4: 6 item Done
~~~

Throughput trung bình:

\[
\frac{3+5+2+6}{4}=4\ \text{item/tuần}
\]

Một phép chia đơn giản \(20/4=5\) tuần cho **điểm tham khảo thô**, không phải ngày hoàn thành chắc chắn. Nó giả định kích thước/phân bố item, năng lực, WIP và loại công việc không thay đổi đáng kể, trong khi dữ liệu bốn tuần vẫn biến động từ 2 đến 6.

### 10.1. Dự báo dựa trên phân bố

Khi có đủ dữ liệu lịch sử phù hợp, nhóm có thể dùng **mô phỏng Monte Carlo** từ throughput để ước lượng một khoảng thời gian hoàn tất backlog:

1. Chọn chuỗi throughput theo những kỳ so sánh được.
2. Xác định số item còn lại và phạm vi dự báo.
3. Mô phỏng nhiều kịch bản lượng item hoàn tất theo từng kỳ.
4. Tổng hợp phân bố tuần hoàn tất.
5. Công bố các phân vị, giả định và yếu tố không được mô hình hóa.

**Không được tự tạo “80% chắc xong tuần thứ N” chỉ từ trung bình 4 item/tuần.** Với mẫu bốn tuần quá ít và hệ thống đang thay đổi, mô phỏng cũng có độ bất định cao. Mục tiêu là **minh bạch rủi ro của kế hoạch**, không tạo vẻ chính xác giả.

### 10.2. Phạm vi backlog thay đổi thì sao?

Nếu Product Owner liên tục bổ sung PBI có giá trị hơn hoặc nhóm học rằng một item cần chia lại, con số “20 item còn lại” có thể không còn đại diện. Cần ghi rõ **phạm vi đầu vào**, những thay đổi được chấp nhận và giả định năng lực.

Đối với một hạn cố định, một câu hỏi thực dụng là: **“Với năng lực thực tế và chất lượng cần giữ, những phần giá trị nào có khả năng Done trước hạn?”**. Đây có thể hữu ích hơn việc yêu cầu cam kết mọi item ban đầu.

### 10.3. Dự báo khác mục tiêu

- **Mục tiêu:** Kết quả muốn đạt, ví dụ mở đăng ký trước đợt khai giảng.
- **Dự báo:** Điều dữ liệu hiện tại cho thấy có thể xảy ra, với giả định và bất định.
- **Cam kết/điều kiện bắt buộc:** Nghĩa vụ mà tổ chức hoặc sản phẩm phải xử lý theo thẩm quyền.

Không được sửa dữ liệu dự báo chỉ để làm mốc mục tiêu trông chắc chắn hơn. Nếu dự báo có rủi ro, nhóm cần **đổi phạm vi, thứ tự ưu tiên, cách phối hợp hoặc kế hoạch** theo quyết định có trách nhiệm.

## 11. Chọn chỉ số cho Scrum: hướng tới Sprint Goal và Increment

Scrum xác định **accountabilities, events, artifacts và commitments**, nhưng **không bắt buộc một bộ KPI duy nhất như velocity, burndown chart hay story point**.

Ba commitments cần luôn rõ:

| Artifact | Commitment | Câu hỏi cần hỏi trước khi chọn metric |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Những tín hiệu nào chứng minh sản phẩm đang tiến tới kết quả mong muốn? |
| **Sprint Backlog** | **Sprint Goal** | Điều gì cho thấy khả năng đạt mục tiêu đang tăng/giảm trong Sprint? |
| **Increment** | **Definition of Done (DoD)** | Có bao nhiêu phần giá trị thật sự đạt chuẩn chất lượng và có thể dùng? |

### 11.1. Sprint Goal không thể rút gọn thành phần trăm task

Một Sprint Goal là “Người học đăng ký được khóa miễn phí và thấy trạng thái đáng tin”. Nhóm có thể Done 8/10 technical tasks, nhưng nếu API không chống đăng ký trùng và giao diện báo sai khi lưu lỗi, **không thể suy Sprint Goal đạt 80%**.

Những tín hiệu có ích:

- Lát cắt giá trị nào đã **đạt DoD**?
- Các điều kiện nghiệp vụ thiết yếu nào còn chưa đạt?
- Có trở ngại nào đe dọa khả năng đáp ứng Sprint Goal?
- Developers đang điều chỉnh Sprint Backlog ra sao?
- Khi thử với người dùng hoặc stakeholder, Increment có tạo hiểu biết gì?

### 11.2. Burn-down và burn-up có ích khi nào?

**Burndown** có thể cho thấy công việc ước lượng còn lại qua thời gian; **burnup** có thể cho thấy lượng việc Done và thay đổi phạm vi. Cả hai là công cụ trực quan **tự chọn**, không phải phần bắt buộc của Scrum.

Nếu nhóm thay đổi phạm vi hoặc ước lượng, biểu đồ có thể thay đổi vì **thông tin mới**, không nhất thiết vì làm việc kém. Nên kiểm tra đồ thị cùng Sprint Goal, DoD và các PBI đang bị chặn.

### 11.3. Velocity là chỉ số kế hoạch nội bộ, không phải điểm thành tích

Velocity thường biểu thị tổng đơn vị ước lượng của công việc hoàn tất trong một Sprint, nếu nhóm **tự chọn** cách ước lượng bằng story points.

Ví dụ nhóm A hoàn tất 22 điểm và nhóm B hoàn tất 36 điểm. **Không được kết luận B làm việc hiệu quả hơn A** vì cách định cỡ điểm, kiến trúc, loại công việc và DoD có thể rất khác.

Không nên dùng velocity để:

- Xếp hạng Developers hoặc các Scrum Teams.
- Đặt mức thưởng theo số điểm.
- Ép nhóm tăng 20% mỗi Sprint.
- Coi công việc chưa đạt DoD là hoàn tất để giữ “cam kết điểm”.

Nếu dùng velocity, nên dùng như **thông tin lịch sử phục vụ dự báo của chính nhóm**, cùng việc xem rủi ro, chất lượng, phạm vi và Sprint Goal. Nhóm cũng có thể dự báo bằng throughput mà không cần story points.

## 12. Chỉ số sản phẩm: đo giá trị từ hành trình người học

Đội phát triển có thể giao nhiều chức năng hơn nhưng người dùng không nhận kết quả mong muốn. Vì vậy cần **chỉ số outcome sản phẩm** gắn với Product Goal.

Ví dụ hành trình:

~~~text
Xem danh mục khóa -> Xem chi tiết -> Đăng ký hợp lệ
                  -> Mở bài đầu -> Tiếp tục học -> Hoàn thành mục tiêu
~~~

### 12.1. Một số câu hỏi theo hành trình

| Câu hỏi | Chỉ số có thể phù hợp | Điều cần đối chiếu |
| --- | --- | --- |
| Người học có tìm thấy khóa phù hợp? | Task success rate trong usability test | Quan sát vướng mắc, phân khúc người học |
| Có hoàn tất đăng ký? | Tỷ lệ đăng ký thành công trên các lượt đủ điều kiện | Lỗi API, lỗi phân quyền, trường hợp bot |
| Có thực sự bắt đầu học? | Activation trong bảy ngày theo cohort | Event mở bài hợp lệ, độ trễ thu thập |
| Có quay lại học? | Retention trong một khoảng đã định nghĩa | Chương trình ngắn/dài khác nhau |
| Có đạt kết quả học? | Tỷ lệ hoàn thành mục tiêu học đã xác định | Mức độ phù hợp khóa, đánh giá chất lượng học |
| Có gặp khó khăn? | Tỷ lệ lỗi thao tác, hỗ trợ, mức thành công nhiệm vụ | Phản hồi trực tiếp và khả năng tiếp cận |

Không có định nghĩa activation hoặc retention chung cho mọi sản phẩm. Một nền tảng khóa ngắn có thể xem hoàn thành một bài là giá trị; khóa dài có thể cần hành trình vài tuần. **Định nghĩa phải gắn với mục tiêu thật**.

### 12.2. Ví dụ tính activation

Một cohort có **160 người học đăng ký hợp lệ**, đã đủ bảy ngày theo dõi. Trong đó **96 người** mở bài đầu tiên hợp lệ trong vòng bảy ngày:

\[
\text{Activation 7 ngày}
=\frac{96}{160}\times100\%
=60\%
\]

Ở một cohort tiếp theo đã đủ thời gian quan sát, có **105/150 = 70%**.

Chênh lệch quan sát:

\[
70\%-60\%=10\ \text{điểm phần trăm}
\]

Nhưng hai cohort khác nhau có thể khác nguồn người dùng, chương trình học, mùa chiến dịch hoặc tỷ lệ dữ liệu thiếu. **Không được kết luận một thay đổi giao diện gây tăng 10 điểm phần trăm** chỉ từ hai tỷ lệ tổng hợp.

**Quyết định hợp lý:** Điều tra phân khúc, nguồn truy cập, lỗi kỹ thuật và thử nghiệm phù hợp trước khi mở rộng giải pháp hoặc công bố thành công nhân quả.

## 13. Tỷ lệ chuyển đổi cần có mẫu số và điều kiện đủ rõ

“Conversion tăng từ 30% lên 35%” nghe rõ nhưng vẫn thiếu định nghĩa:

- Tử số đếm **người học duy nhất**, lượt truy cập hay số giao dịch?
- Mẫu số là **người đủ điều kiện đăng ký**, người xem trang hay mọi lượt mở app?
- Tính theo **ngày, phiên, cohort** hay toàn bộ tháng?
- Có loại trừ tài khoản kiểm thử và bot theo quy tắc minh bạch không?
- Đã tính những trường hợp retry hoặc yêu cầu trùng chưa?

### 13.1. Ví dụ phép đo

Trong một tuần, có **600 người học đủ điều kiện** xem chi tiết khóa; **180 người** hoàn tất đăng ký:

\[
\text{Conversion}=\frac{180}{600}\times100\%=30\%
\]

Tuần sau cũng có 600 người đủ điều kiện, trong đó 210 người đăng ký:

\[
\frac{210}{600}\times100\%=35\%
\]

Mức tăng là **5 điểm phần trăm**, tương ứng mức tăng tương đối:

\[
\frac{35\%-30\%}{30\%}\times100\%
\approx16{,}7\%
\]

“Tăng 5 điểm phần trăm” và “tăng tương đối khoảng 16,7%” **không cùng nghĩa**. Khi báo cáo, chọn cách biểu diễn rõ và không chỉ ghi “tăng 5%”.

### 13.2. Conversion không đủ đo chất lượng trải nghiệm

Một nút đăng ký hiển thị nổi bật có thể tăng lượt hoàn tất nhưng khiến người học chọn nhầm khóa. Cần guardrail, ví dụ:

- Tỷ lệ hủy hoặc yêu cầu hỗ trợ ngay sau đăng ký.
- Tỷ lệ lỗi API và thông báo sai trạng thái.
- Tỷ lệ bắt đầu học thực sự.
- Phản hồi về mức phù hợp của khóa và khả năng tiếp cận.

Tối ưu một con số mà bỏ hành trình tiếp theo có thể khiến sản phẩm **đẹp dashboard nhưng kém giá trị**.

## 14. Đo chất lượng: lỗi được phát hiện ở đâu và ảnh hưởng gì?

Một nhóm không nên chỉ đếm số bug được tạo hoặc số test case chạy. Chỉ số chất lượng cần hỗ trợ **quyết định về rủi ro và khả năng phục hồi**.

| Câu hỏi | Tín hiệu có ích | Giới hạn |
| --- | --- | --- |
| Người dùng đang gặp lỗi gì? | Tỷ lệ yêu cầu thất bại, incident, phản hồi hỗ trợ | Không phải mọi lỗi đều được báo |
| Lỗi có nghiêm trọng không? | Phân loại theo tác động, dữ liệu, an toàn và phạm vi | Tổng số lỗi che khuất mức nghiêm trọng |
| Lỗi lọt khỏi bước kiểm tra nào? | Defects phát hiện ở staging/production theo loại thay đổi | Cần định nghĩa cửa sổ quan sát |
| Khi phát hành thay đổi, tỷ lệ thay đổi gây sự cố ra sao? | Change failure rate theo định nghĩa áp dụng | Không so sánh tùy tiện hệ thống khác nhau |
| Sự cố được phát hiện và khôi phục nhanh? | Thời gian phát hiện, khôi phục theo loại sự cố | Một incident hiếm có thể làm số trung bình biến động lớn |
| Test có đáng tin? | Flaky test, lỗi lặp và thời gian điều tra | Rerun tới khi xanh có thể che vấn đề |
| Phân quyền và dữ liệu có an toàn? | Kiểm thử/đánh giá phù hợp, sự cố truy cập trái phép | Ít sự cố được biết không bảo đảm an toàn tuyệt đối |

### 14.1. Một chỉ số tỷ lệ lỗi cần định nghĩa phạm vi

Nếu trong một giai đoạn có **12.000 yêu cầu đăng ký hợp lệ** và **180 yêu cầu thất bại theo quy tắc đo**:

\[
\text{Tỷ lệ yêu cầu thất bại}
=\frac{180}{12000}\times100\%=1{,}5\%
\]

Nhưng cần phân biệt:

- Lỗi kỹ thuật server, timeout, mạng.
- Từ chối hợp lệ theo quy tắc sản phẩm, ví dụ người dùng chưa đăng nhập.
- Yêu cầu gửi lại sau timeout.
- Những yêu cầu có thể đã ghi dữ liệu thành công nhưng phản hồi thất lạc.

Nếu gom tất cả phản hồi không phải thành công vào một loại “lỗi”, nhóm có thể hiểu sai chất lượng. **Định nghĩa phép đo phải phù hợp câu hỏi**.

### 14.2. Chất lượng gắn với Definition of Done

Trong Scrum, **Definition of Done** là commitment của Increment. Công việc chưa đáp ứng DoD **không được coi là Increment hoàn tất**, dù mã đã merge hoặc đã chạy một số bài test.

Chỉ số “số ticket đóng” hoặc “test xanh” không thay thế việc kiểm chứng **mọi tiêu chuẩn chất lượng áp dụng**. Khi thời hạn gây áp lực, nên thương lượng phạm vi, không tự ý giảm chất lượng để đạt mục tiêu số lượng.

## 15. Đo năng lực giao phần mềm: CI, phản hồi và vận hành

Với thực hành XP và DevOps, nhóm có thể chọn metric để biết **khả năng thay đổi thường xuyên mà vẫn an toàn** có được cải thiện không.

| Tín hiệu | Câu hỏi cụ thể | Hành động có thể theo sau |
| --- | --- | --- |
| Thời gian từ push tới phản hồi CI | Developers có chờ lâu mới biết lỗi? | Giảm queue time, cải thiện test suite |
| Tuổi pull request | Mã chờ review hoặc ghép chung bao lâu? | Chia PR nhỏ, cùng review, giảm WIP |
| Thời gian khôi phục build chung | Build đỏ làm cản tích hợp bao lâu? | Quy trình triage và sửa/revert sớm |
| Tỷ lệ test flaky | Cảnh báo pipeline có đáng tin? | Sửa kiểm thử hoặc môi trường |
| Tần suất deployment | Nhóm có giao thay đổi đủ thường xuyên để nhận phản hồi? | Xem các rào cản phát hành |
| Lead time for changes | Từ mốc tạo thay đổi đến triển khai mất bao lâu? | Cải thiện review, CI/CD, quy trình release |
| Tỷ lệ thay đổi gây sự cố | Tốc độ có đánh đổi độ ổn định? | Cải thiện kiểm tra theo rủi ro |
| Thời gian phục hồi khi deployment lỗi | Nhóm có khôi phục nhanh và an toàn? | Observability, rollback, diễn tập |

Các metric giao hàng thường gắn với nghiên cứu và thực hành **DORA**, nhưng định nghĩa và nhóm thước đo có thể được cập nhật theo thời gian. **Đừng mặc định một danh sách cố định là quy định Agile bắt buộc**; nên công bố mốc đo và phạm vi hệ thống đang dùng.

### 15.1. Ví dụ thời gian phản hồi CI

Giả sử một pipeline có:

| Bước | Thời gian minh họa |
| --- | ---: |
| Chờ runner | 6 phút |
| Build và unit tests | 4 phút |
| Kiểm thử tích hợp cần thiết | 8 phút |
| **Tổng nếu chạy nối tiếp** | **18 phút** |

Giảm build từ 4 xuống 3 phút chỉ đưa tổng còn **17 phút**; giảm hàng đợi runner từ 6 xuống 1 phút đưa tổng còn **13 phút**, nếu các bước khác giữ nguyên.

Đây là phép tính **theo giả định chạy nối tiếp**. Pipeline thực có thể có các bước song song, khiến thời gian thực phải đo theo đường găng. Điểm chính là **đo toàn bộ thời gian tới phản hồi hữu ích**, không chỉ tối ưu một câu lệnh.

### 15.2. Tốc độ và độ ổn định phải được đọc cùng

Nếu deployment thường xuyên hơn nhưng số sự cố nghiêm trọng tăng, không nên tuyên bố cải tiến chỉ từ tần suất. Nếu một pipeline báo xanh nhanh hơn vì bỏ contract test quan trọng, đó có thể là **giảm chất lượng tín hiệu**, không phải tăng năng lực.

## 16. Leading, lagging và guardrail metrics

Một số chỉ số xuất hiện trước outcome cuối, một số chỉ nhìn được sau. Phân biệt chúng giúp tránh kết luận quá sớm.

- **Leading indicator:** Tín hiệu dự báo hoặc ảnh hưởng trước outcome, ví dụ tỷ lệ người học mở bài đầu có thể liên quan việc tiếp tục học sau này.
- **Lagging indicator:** Kết quả được quan sát muộn hơn, ví dụ tỷ lệ hoàn thành khóa sau nhiều tuần.
- **Guardrail metric:** Tín hiệu giới hạn tác dụng phụ cần theo dõi khi tối ưu mục tiêu chính, ví dụ tỷ lệ đăng ký bị lỗi hoặc sự cố quyền dữ liệu.

Các nhãn “leading/lagging” phụ thuộc **mục tiêu cụ thể**. Việc mở bài đầu là outcome nếu mục tiêu là bắt đầu học, nhưng có thể là leading indicator nếu mục tiêu là hoàn thành chương trình.

### 16.1. Bộ ba chỉ số cân bằng

Giả sử nhóm muốn tăng activation:

| Vai trò | Metric | Vì sao |
| --- | --- | --- |
| **Chỉ số chính** | Activation 7 ngày sau đăng ký | Gắn với kết quả người học bắt đầu học |
| **Chỉ số chẩn đoán** | Lỗi mở bài, thời gian tải và số bước từ đăng ký tới bài đầu | Giúp hiểu cơ chế xảy ra |
| **Guardrail** | Lỗi đăng ký, dữ liệu không nhất quán, yêu cầu hỗ trợ và sự cố quyền truy cập | Ngăn tăng activation bằng cách tạo tác dụng phụ |

Không phải tất cả chỉ số cần cùng một mục tiêu tăng. Ví dụ **tỷ lệ lỗi nên giảm hoặc không vượt ngưỡng rủi ro chấp nhận**, còn số lượng người học kích hoạt có thể muốn tăng.

### 16.2. Tín hiệu sớm cần được kiểm chứng

Nếu nhóm giả định “người mở bài đầu sẽ có khả năng hoàn thành khóa cao hơn”, hãy kiểm tra giả định theo cohort và bối cảnh. Đừng biến một tương quan thành quan hệ nguyên nhân mà chưa có thiết kế nghiên cứu phù hợp.

## 17. Thử nghiệm cải tiến: đo trước và sau chưa đủ kết luận nhân quả

Một nhóm thay đổi giao diện đăng ký và thấy activation tăng. Có thể do giao diện, nhưng cũng có thể do chiến dịch đưa nhóm người học có động lực cao hơn vào nền tảng.

### 17.1. Phân biệt ba mức kết luận

1. **Mô tả:** “Trong dữ liệu quan sát, tỷ lệ tăng từ 60% lên 70%.”
2. **Giả thuyết giải thích:** “Giao diện mới có thể giúp người học tìm nút bắt đầu dễ hơn.”
3. **Kết luận nhân quả:** “Thay đổi giao diện gây ra mức tăng xác định trong bối cảnh nghiên cứu.”

Mức thứ ba đòi hỏi thiết kế phù hợp, chẳng hạn thử nghiệm có phân bổ hợp lệ, kiểm soát sai lệch hoặc phân tích thống kê đáp ứng giả định. **Không được nhảy từ mức 1 sang mức 3** chỉ vì biểu đồ đẹp.

### 17.2. Ví dụ thử hai phiên bản

Giả sử có hai nhóm thử độc lập trong một thí nghiệm minh họa:

| Phiên bản | Người đủ điều kiện | Bắt đầu bài đầu trong bảy ngày | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A — Hiện tại | 120 | 72 | 60% |
| B — Giao diện mới | 120 | 84 | 70% |

Chênh lệch quan sát là **10 điểm phần trăm**. Tuy nhiên, chỉ từ bảng này không đủ biết liệu cách phân nhóm có ngẫu nhiên, cỡ mẫu có phù hợp, dữ liệu đã đủ bảy ngày, guardrail có bị tác động, hay kết quả có ổn định ở các phân khúc khác.

**Quyết định phù hợp:** Kiểm tra chất lượng thiết kế thử, phân bố người dùng và kết quả phụ trước khi mở rộng. Nếu dữ liệu chỉ là quan sát, diễn đạt là **tín hiệu cần kiểm chứng tiếp**.

### 17.3. Bẫy chọn metric sau khi xem kết quả

Nếu thử nghiệm thu 30 chỉ số rồi chỉ công bố chỉ số có mức tăng lớn nhất, nguy cơ kết luận ngẫu nhiên tăng. Trước khi thử, nên nêu:

- Câu hỏi và **metric chính**.
- Đối tượng đủ điều kiện và cách phân bổ.
- Khoảng thời gian quan sát.
- Guardrails và trường hợp cần dừng an toàn.
- Tiêu chí ra quyết định.
- Cách xử lý dữ liệu thiếu, lỗi theo dõi và nhiều phép so sánh.

Không nhất thiết mọi quyết định nhỏ đều cần A/B test. Usability test, phỏng vấn, thử prototype hoặc quan sát vận hành có thể phù hợp nếu câu hỏi và mức rủi ro khác.

## 18. Dữ liệu thiếu, sự kiện trùng và mẫu nhỏ có thể làm sai câu trả lời

Một dashboard chỉ đáng dùng khi dữ liệu và ngữ cảnh của nó đủ tin cậy.

### 18.1. Các lỗi dữ liệu thường gặp

| Vấn đề | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Event bị mất** | Người học mở bài nhưng client không gửi sự kiện khi offline | Activation thấp giả |
| **Event trùng** | Retry sau timeout ghi hai lần đăng ký | Conversion/throughput cao giả |
| **Clock/timezone sai** | Server UTC, dashboard đếm ngày địa phương không nhất quán | Cohort hoặc cycle time sai |
| **Item thiếu mốc Done** | Ticket được hoàn tất kỹ thuật nhưng không cập nhật trạng thái | Cycle time, WIP sai |
| **Mốc đo thay đổi** | Đổi “In Progress” thành “Ready for QA” làm điểm bắt đầu | Chuỗi trước/sau không so sánh được |
| **Cohort chưa trưởng thành** | Người mới đăng ký một ngày bị tính vào activation bảy ngày | Tỷ lệ giảm giả |
| **Chọn mẫu thuận tiện** | Chỉ hỏi người dùng thường xuyên hoạt động | Bỏ sót khó khăn của người mới |
| **Loại bỏ item khó** | Chỉ thống kê những story Done nhanh, bỏ WIP đang già | Cycle time quá lạc quan |
| **Định nghĩa DoD không ổn định** | Tự đổi trạng thái Done khi còn thiếu test | Throughput tăng giả |

### 18.2. Kiểm tra nguồn dữ liệu trước khi gắn KPI

Một bước đo lường tối thiểu:

1. Lấy mẫu một vài bản ghi/sự kiện và truy ngược nguồn.
2. Kiểm tra trùng lặp, dữ liệu thiếu, mốc giờ và định danh.
3. Đối chiếu dữ liệu tổng hợp với workflow hoặc hành vi thực tế.
4. Xem các item có giá trị bất thường thay vì loại bỏ tùy tiện.
5. Ghi rõ khi data pipeline hoặc cách tính được sửa.

**Chỉ số chính xác tới hai chữ số thập phân không có ý nghĩa nếu tử số và mẫu số đã sai.**

### 18.3. Bảo vệ dữ liệu người dùng

Metric sản phẩm có thể liên quan lịch sử học, hành vi, tài khoản hoặc thông tin nhạy cảm. Nhóm cần thu thập đúng mục đích, hạn chế quyền truy cập, dùng dữ liệu tổng hợp/anonymization khi phù hợp và tuân thủ chính sách, pháp luật áp dụng.

**Không cần thu mọi sự kiện cá nhân để có quyết định hữu ích.** Đừng để mong muốn đo lường trở thành lý do giám sát quá mức hoặc giữ dữ liệu vượt phạm vi cho phép.

## 19. Goodhart's Law: khi chỉ số biến thành mục tiêu dễ bị làm đẹp

Một nguyên tắc cảnh báo thường được nhắc dưới tên **Goodhart's Law**: khi một phép đo trở thành mục tiêu thưởng/phạt cứng, nó có thể mất khả năng phản ánh điều ban đầu muốn đo.

### 19.1. Những cách méo mó hành vi

| Metric bị biến thành mục tiêu cứng | Hành vi tối ưu sai có thể xảy ra | Cách thiết kế lành mạnh hơn |
| --- | --- | --- |
| **Velocity phải tăng mọi Sprint** | Thổi story points, hạ DoD, tránh việc khó | Dùng cho dự báo nội bộ cùng chất lượng và outcome |
| **Số item Done càng cao càng tốt** | Chia task giả, bỏ item khó đang Blocked | Xem throughput cùng WIP, age và loại item |
| **Số bug được báo phải giảm** | Không ghi nhận hoặc gắn lại nhãn lỗi | Khuyến khích phát hiện sớm, phân tích mức nghiêm trọng |
| **Code coverage phải đạt một tỷ lệ cực cao** | Viết test hời hợt để phủ dòng | Kiểm thử theo rủi ro và hành vi |
| **Deployment càng nhiều càng giỏi** | Chia deploy không có giá trị, bỏ kiểm tra | Đọc tốc độ cùng độ ổn định và outcome |
| **Conversion phải tăng bằng mọi cách** | Giao diện gây nhầm lẫn hoặc thao túng người dùng | Thêm guardrail về trải nghiệm và khiếu nại |
| **Utilization cá nhân gần 100%** | Không ai rảnh hỗ trợ review, WIP và chờ tăng | Tối ưu dòng giá trị và khả năng phối hợp |

### 19.2. Không dùng metric dòng công việc để xếp hạng con người

Work Item Age hoặc Cycle Time của một PBI phụ thuộc nhiều bước: thiết kế, review, tích hợp, kiểm thử, dữ liệu, môi trường và quyết định nghiệp vụ. Nếu dùng chúng để quy trách nhiệm cá nhân, người ta có thể **tránh nhận việc rủi ro cao hoặc giấu blocker**.

Với Agile, chỉ số nên thúc đẩy **điều tra và học hỏi cấp hệ thống**, không biến thành bảng thành tích giữa Developers hoặc Scrum Teams.

### 19.3. Không chỉ nhìn điểm mục tiêu

Nếu mục tiêu là giảm cycle time trung vị, nhóm vẫn cần nhìn **đuôi phân bố**, những item chưa Done và lỗi sau phát hành. Trung vị giảm nhưng các item quan trọng bị chặn 30 ngày là tín hiệu cần điều tra.

## 20. Dashboard tối thiểu cho một quyết định

Một dashboard hữu ích thường **nhỏ hơn** dashboard chứa mọi dữ liệu có thể thu thập. Nhóm có thể tổ chức mỗi khu vực theo câu hỏi và hành động.

### 20.1. Ví dụ dashboard cho mục tiêu “người học bắt đầu học thuận lợi”

| Khối thông tin | Chỉ số/tín hiệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Outcome chính** | Activation 7 ngày theo cohort đã đủ bảy ngày | Người đăng ký có bắt đầu học? |
| **Bước chẩn đoán** | Tỷ lệ đăng ký hợp lệ, lỗi mở bài, thời gian từ đăng ký tới mở bài | Bị kẹt ở đâu? |
| **Chất lượng** | Tỷ lệ yêu cầu thất bại, sự cố phân quyền, dữ liệu trùng | Đang tăng giá trị hay tăng rủi ro? |
| **Dòng giao hàng** | WIP, age của PBI liên quan, throughput và cycle time | Khả năng thử cải tiến tiếp nhanh tới đâu? |
| **Bằng chứng định tính** | Kết quả usability test và phản hồi hỗ trợ | Vì sao người học gặp khó? |
| **Quyết định gần nhất** | Thử nghiệm nào sẽ chạy, ai phụ trách, mốc xem lại | Số liệu dẫn tới hành động gì? |

### 20.2. Tránh dashboard nhiều màu nhưng ít ý nghĩa

Không cần tự đặt mọi metric thành xanh–vàng–đỏ theo ngưỡng cảm tính. Nếu có ngưỡng cảnh báo, cần biết nó dựa trên **rủi ro, nhu cầu dịch vụ, phân bố lịch sử hoặc ràng buộc thực**.

Ví dụ, mốc SLE P85 có thể giúp cảnh báo item già. Nhưng **vượt SLE không tự chứng minh item vi phạm một SLA hợp đồng** hoặc đã thất bại; cần quan sát trạng thái và chính sách phục vụ.

### 20.3. Tách báo cáo điều hành khỏi công cụ điều tra nhóm

Bên liên quan có thể cần hai hoặc ba chỉ số outcome và rủi ro để quyết định ưu tiên. Developers có thể cần dữ liệu chi tiết về PR, pipeline, trạng thái item hoặc truy vấn log để xử lý nguyên nhân.

**Không nên ép hai mục đích vào cùng một màn hình** nếu làm mất ngữ cảnh hoặc tạo cảm giác giám sát cá nhân.

## 21. Tình huống xuyên suốt: đăng ký tăng nhưng người học không bắt đầu

### 21.1. Dữ liệu ban đầu

Trong một đợt cải tiến, Product Owner nhận được báo cáo:

> “Lượt đăng ký khóa miễn phí tăng. Có lẽ luồng đăng ký đã thành công; nên ưu tiên tính năng gợi ý khóa tiếp theo.”

Nhưng khảo sát hỗ trợ cho thấy người học vẫn không chắc **đã đăng ký thành công hay chưa**, và một số người không biết cách mở bài đầu.

Nhóm muốn quyết định giữa ba hướng:

1. Thêm gợi ý khóa học cá nhân hóa.
2. Cải thiện xác nhận và đường dẫn tới bài đầu.
3. Sửa nút nghẽn kỹ thuật ở luồng đăng ký/khởi tạo khóa học.

### 21.2. Viết câu hỏi đúng trước khi xem metric

| Quyết định | Câu hỏi | Dữ liệu cần thu |
| --- | --- | --- |
| Có nên cải thiện bước sau đăng ký? | Người học rơi ở bước đăng ký → bắt đầu bài đầu? | Activation theo cohort, log lỗi mở bài, usability test |
| Có vấn đề tính đúng đắn? | Có yêu cầu đăng ký trùng, phản hồi sai hoặc lỗi phân quyền? | Error rate, kiểm thử tích hợp, incident, phản hồi hỗ trợ |
| Có thể thử một lát cắt trong Sprint tiếp? | Công việc liên quan đang bị nghẽn ở đâu? | WIP, age, cycle time, review queue |
| Có đủ bằng chứng ưu tiên gợi ý cá nhân hóa? | Người học không bắt đầu vì chọn sai khóa hay vì luồng khó dùng? | Phỏng vấn, quan sát nhiệm vụ, phân khúc |

### 21.3. Bộ dữ liệu giả định

| Tín hiệu | Giai đoạn trước | Giai đoạn sau | Điều có thể nói |
| --- | ---: | ---: | --- |
| Conversion từ xem chi tiết tới đăng ký | 30% | 35% | Tăng 5 điểm phần trăm trong dữ liệu quan sát |
| Activation 7 ngày của cohort đủ thời gian | 60% | 61% | Chỉ tăng 1 điểm phần trăm, cần xem biến động |
| Lỗi mở bài trên yêu cầu đủ điều kiện | 1,2% | 2,1% | Dấu hiệu kỹ thuật xấu đi cần điều tra |
| Trung vị cycle time của PBI liên quan | 6 ngày | 8 ngày | Dòng công việc có thể chậm lại |
| Work Item Age của item review quan trọng | 4 ngày | 11 ngày | Có item già đi và có khả năng bị nghẽn |

**Toàn bộ bảng là dữ liệu minh họa**, không phải dữ liệu hệ thống thật. Những tỷ lệ qua hai giai đoạn chưa đủ để kết luận một thay đổi gây ra tác động; cần kiểm tra cách đo, số quan sát, đặc điểm người dùng và yếu tố khác.

### 21.4. Những phát hiện từ ba loại bằng chứng

**Số liệu sản phẩm:** Conversion tăng nhưng activation hầu như không đổi. Vậy việc tăng lượt đăng ký **chưa chứng minh người học nhận nhiều giá trị hơn**.

**Số liệu chất lượng:** Lỗi mở bài tăng; có khả năng một phần người học không thể truy cập bài đầu sau đăng ký.

**Số liệu dòng công việc:** Item khắc phục luồng đăng ký đang chờ review và kiểm thử lâu; kéo thêm một tính năng gợi ý lớn có thể làm WIP tăng thêm.

### 21.5. Quyết định phù hợp

Nhóm có thể ưu tiên một lát cắt nhỏ:

> “Người học đăng ký khóa miễn phí thành công sẽ thấy trạng thái chính xác và đường dẫn rõ tới bài đầu; nếu có lỗi, không được báo thành công giả.”

Đồng thời:

- Phân tích lỗi mở bài và phản hồi người dùng.
- Xem lại WIP, hàng chờ review và khả năng Done.
- Đặt guardrail về lỗi đăng ký và quyền truy cập.
- Đo lại activation của những cohort **đủ thời gian theo dõi**.
- Giữ ý tưởng gợi ý khóa như một lựa chọn Product Backlog, chưa đầu tư lớn khi chưa rõ vấn đề.

**Điểm quan trọng:** Chỉ số giúp nhóm chọn một thí nghiệm ít rủi ro hơn; nó không tự chỉ định giải pháp đúng. Quyết định còn cần kiến thức nghiệp vụ, phản hồi người dùng, năng lực kỹ thuật và quyền ưu tiên.

### 21.6. Làm rõ hành vi cần kiểm chứng

~~~gherkin
Tính năng: Bắt đầu học sau khi đăng ký khóa miễn phí

  Tình huống: Đăng ký và mở bài đầu thành công
    Cho trước người học đã đăng nhập hợp lệ
    Và khóa "Java nhập môn" đang mở đăng ký
    Khi người học hoàn tất đăng ký "Java nhập môn"
    Thì hệ thống xác nhận đúng trạng thái đăng ký
    Và cung cấp đường dẫn hợp lệ tới bài học đầu tiên

  Tình huống: Hệ thống chưa xác nhận đã ghi đăng ký
    Cho trước dịch vụ lưu đăng ký không thể xác nhận kết quả
    Khi người học yêu cầu đăng ký một khóa miễn phí
    Thì hệ thống không báo chắc chắn đăng ký thành công
    Và người học thấy thông tin phù hợp để kiểm tra hoặc thử lại

  Tình huống: Không được mở bài bằng quyền của tài khoản khác
    Cho trước tài khoản A đã đăng nhập
    Và quyền truy cập khóa thuộc tài khoản B
    Khi A cố truy cập tài nguyên chỉ B được phép dùng
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ dữ liệu riêng của B
~~~

Đây là ví dụ acceptance criteria, không phải các bước tự động chạy được ngay. **Đạt Gherkin chưa tự đồng nghĩa đạt Definition of Done**; kiểm tra tích hợp, bảo mật và chất lượng khác vẫn áp dụng theo sản phẩm.

## 22. Nhịp xem số liệu: điều tra rồi hành động, không chỉ báo cáo

Một chỉ số hữu ích cần có **vòng phản hồi và người ra quyết định**.

### 22.1. Nhịp phù hợp với loại câu hỏi

| Câu hỏi | Nhịp tham khảo | Điều cần làm sau khi xem |
| --- | --- | --- |
| Item nào bị chặn hôm nay? | Hằng ngày hoặc theo nhịp phối hợp của nhóm | Gỡ blocker, giảm WIP, điều chỉnh việc đang làm |
| Chất lượng triển khai có suy giảm? | Liên tục và khi có sự cố | Phát hiện, ứng cứu, sửa và khôi phục |
| Luồng review/CI có cải thiện? | Hằng tuần hoặc theo vài kỳ | So sánh age, cycle time, chất lượng rồi thử cải tiến |
| Sprint Goal còn khả thi? | Trong Sprint, bao gồm Daily Scrum của Developers | Điều chỉnh Sprint Backlog và trao đổi phạm vi khi cần |
| Product Goal đang tiến triển? | Theo vòng học sản phẩm, đủ thời gian cho outcome | Phân tích cohort, phản hồi và thay đổi ưu tiên |
| Thử nghiệm đã tạo giá trị? | Khi dữ liệu đủ điều kiện theo thiết kế thử | Quyết định giữ, sửa, dừng hoặc thử tiếp |

Nhịp chỉ là **gợi ý**. Với sự cố bảo mật nghiêm trọng, không thể chờ cuộc họp tuần; với retention ba tháng, không nên đánh giá sau một ngày.

### 22.2. Một cuộc họp xem số liệu nên kết thúc bằng gì?

Mẫu trao đổi:

1. **Câu hỏi:** Chúng ta đang tìm hiểu vấn đề nào?
2. **Bằng chứng:** Metric gì, định nghĩa và thời gian ra sao?
3. **Ngữ cảnh:** Những gì đã thay đổi trong sản phẩm, đội và dữ liệu?
4. **Giả thuyết nguyên nhân:** Có thể kiểm chứng như thế nào?
5. **Quyết định:** Làm, dừng hoặc tiếp tục thử điều gì?
6. **Guardrail:** Rủi ro nào cần theo dõi?
7. **Mốc xem lại:** Khi nào có bằng chứng để điều chỉnh tiếp?

Một dashboard không cần tạo thêm nhiều cuộc họp nếu nhóm đã có nhịp Scrum/Kanban phù hợp. **Kết quả cần là hành động và học hỏi**, không phải số lượng slide báo cáo.

## 23. Ai quyết định và ai sở hữu chất lượng phép đo?

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; Developers có trách nhiệm tạo Increment đạt DoD; Scrum Master hỗ trợ hiệu quả Scrum. Nhưng **Scrum không quy định chức danh “metric owner” bắt buộc**.

| Việc | Cách phối hợp phù hợp |
| --- | --- |
| Xác định outcome và câu hỏi giá trị sản phẩm | Product Owner cộng tác với Developers và stakeholder |
| Định nghĩa workflow và dữ liệu dòng công việc | Những người thực hiện công việc cùng thống nhất ranh giới |
| Đo chất lượng và năng lực kỹ thuật | Developers, kiểm thử, vận hành, an toàn theo chuyên môn |
| Xác nhận quyền dữ liệu và giới hạn sử dụng | Người có thẩm quyền dữ liệu, bảo mật/pháp lý khi cần |
| Kiểm tra độ tin cậy event/query | Người sở hữu dữ liệu/analytics cùng đội sản phẩm |
| Quyết định ưu tiên Product Backlog | Product Owner với thông tin từ các bên liên quan |
| Điều chỉnh kế hoạch Sprint hướng Sprint Goal | Developers, cộng tác với Product Owner khi phạm vi ảnh hưởng |
| Đưa ra thay đổi chính sách luồng | Nhóm liên quan theo thẩm quyền tổ chức |

**Người duy trì dashboard không mặc nhiên có quyền quyết định thay Product Owner**, và người ra quyết định không nên tự yêu cầu sửa số liệu để hợp thức hóa một lựa chọn đã chốt.

### 23.1. Mức minh bạch phù hợp

Một bản ghi ngắn về quyết định có thể gồm:

~~~text
Câu hỏi: Vì sao activation 7 ngày không tăng dù conversion tăng?
Bằng chứng: Cohort đã đủ 7 ngày; activation 60% -> 61%;
            lỗi mở bài 1,2% -> 2,1% (mẫu minh họa)
Giới hạn: Chưa xác định nguyên nhân; cần kiểm tra nguồn sự kiện
Giả thuyết: Người học bị chặn hoặc khó tìm nút mở bài
Quyết định: Ưu tiên khảo sát luồng sau đăng ký, sửa lỗi mở bài
Guardrail: Không tăng lỗi đăng ký hoặc vi phạm quyền truy cập
Mốc xem lại: Sau một vòng cải tiến và cohort đủ thời gian
~~~

Bản ghi như vậy làm rõ **chỉ số đã ảnh hưởng quyết định ra sao**; nó không biến số liệu tương quan thành khẳng định nhân quả.

## 24. Những hiểu lầm thường gặp khi đo lường Agile

**1. “Có càng nhiều KPI càng quản lý tốt.”** Nhiều con số có thể làm mất câu hỏi cốt lõi. Bắt đầu từ quyết định.

**2. “Một dashboard xanh nghĩa là sản phẩm thành công.”** Có thể chỉ số quá trình tốt nhưng outcome người dùng không cải thiện.

**3. “Velocity là chỉ số năng suất bắt buộc trong Scrum.”** Scrum không yêu cầu story points hay velocity; dùng nếu hữu ích cho dự báo nội bộ.

**4. “Có thể so velocity giữa hai đội.”** Các đội định cỡ điểm và có bối cảnh khác; so sánh trực tiếp gây ngộ nhận.

**5. “Tăng số story Done chắc chắn tạo nhiều giá trị.”** Item nhỏ dễ làm có thể nhiều nhưng không giải quyết vấn đề chính.

**6. “Cycle Time của item Done đại diện mọi công việc.”** Item khó chưa Done cần xem Work Item Age, nếu không sẽ thiên lệch.

**7. “Item 90% mốc SLE nghĩa là làm xong 90%.”** Tuổi công việc và phần trăm hoàn thành khác nhau.

**8. “SLE P85 là lời hứa tất cả item phải xong đúng mốc.”** SLE biểu đạt kỳ vọng theo phân bố, không phải SLA hay deadline tuyệt đối.

**9. “Chỉ cần throughput trung bình là dự báo chính xác ngày ra mắt.”** Cần biến động, loại item, thay đổi phạm vi và bất định.

**10. “Little's Law cho biết P85.”** Nó liên hệ các giá trị trung bình với điều kiện thích hợp, không cho phân vị.

**11. “Conversion tăng thì outcome học tập chắc tăng.”** Người đăng ký có thể chưa mở bài hoặc chọn sai khóa.

**12. “Tỷ lệ tăng 5% và tăng 5 điểm phần trăm giống nhau.”** Hai cách diễn đạt khác nhau và cần công bố đúng.

**13. “Cohort đăng ký hôm nay đã tính vào activation bảy ngày.”** Chưa đủ thời gian quan sát dễ làm tỷ lệ thấp giả.

**14. “Nếu lỗi được báo ít hơn nghĩa là chất lượng tốt hơn.”** Hệ thống có thể thiếu giám sát hoặc khuyến khích giấu lỗi.

**15. “Pipeline xanh bảo đảm không có lỗi.”** Nó chỉ chứng minh các kiểm tra đã cấu hình đạt trong điều kiện tương ứng.

**16. “Coverage 100% nghĩa là đã kiểm tra mọi hành vi.”** Coverage không chứng minh tính đúng nghiệp vụ, bảo mật hoặc tích hợp.

**17. “Có thể dùng số commit để xếp hạng Developers.”** Số commit không đo trực tiếp chất lượng, giá trị hoặc cộng tác.

**18. “Một mẫu nhỏ cho tỷ lệ 85% chứng minh xác suất tương lai chính xác là 85%.”** Cần xem cỡ mẫu, biến động và khả năng đại diện.

**19. “Trước/sau khác nhau chứng minh thay đổi gây ra kết quả.”** Yếu tố mùa vụ, phân khúc và cách đo có thể giải thích khác biệt.

**20. “Metric nào không đạt thì cứ chỉnh lại ngưỡng cho xanh.”** Thay đổi ngưỡng cần có lý do và ghi lịch sử, không phải che rủi ro.

**21. “Giảm WIP chỉ cần chuyển ticket sang cột khác.”** Ranh giới WIP và công việc thật phải nhất quán; đổi nhãn không loại hàng chờ.

**22. “Done được tính ngay khi viết mã xong.”** Với Scrum, Increment phải đáp ứng DoD, không phụ thuộc nhãn báo cáo.

**23. “Khi quá hạn nên hạ DoD để throughput tăng.”** Đây là tối ưu sai, có thể đẩy rủi ro sang người dùng.

**24. “Chỉ số chỉ để báo cáo cho quản lý.”** Nhóm dùng số liệu để tự điều chỉnh cách làm và học hỏi cấp hệ thống.

**25. “Ai có item age cao là người làm kém.”** Tuổi item phản ánh nhiều hàng chờ và phụ thuộc, không phải điểm năng lực cá nhân.

**26. “Dữ liệu được thu thập thì mặc nhiên được dùng cho mọi mục đích.”** Phải tôn trọng quyền riêng tư, mục đích và giới hạn sử dụng.

**27. “Một metric tăng là đủ để quyết định mở rộng rollout.”** Cần chất lượng, rủi ro, guardrail và ngữ cảnh.

**28. “Mỗi tuần phải thay đổi mục tiêu để metric luôn đẹp.”** Tính liên tục định nghĩa giúp học từ xu hướng; thay đổi phải có lý do.

## 25. Bài tập tính toán và chọn metric

Nhóm đang cải thiện luồng đăng ký nền tảng học trực tuyến. Dữ liệu **giả định**:

### Bộ A — Dòng công việc

20 cycle time của những story tương đồng đã Done, tính bằng ngày làm việc:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

WIP hiện tại là 8 item; ba item đáng chú ý:

| Item | Age | Trạng thái |
| --- | ---: | --- |
| A — Xác nhận đăng ký | 9 ngày | Chờ review |
| B — Đồng bộ đăng ký | 12 ngày | Bị chặn môi trường tích hợp |
| C — Nhãn trình độ | 3 ngày | Đang kiểm thử |

Throughput bốn tuần gần nhất: **3, 5, 2, 6 item/tuần**.

### Bộ B — Sản phẩm và chất lượng

| Chỉ số | Trước cải tiến | Sau cải tiến |
| --- | ---: | ---: |
| Người đủ điều kiện xem chi tiết khóa | 600 | 600 |
| Người hoàn tất đăng ký | 180 | 210 |
| Activation 7 ngày theo cohort đã đủ thời gian | 96/160 | 105/150 |
| Tỷ lệ lỗi mở bài | 1,2% | 2,1% |

### Câu hỏi

1. Nếu Product Owner hỏi “người học có bắt đầu học dễ hơn không?”, nên chọn **chỉ số chính** nào? Chỉ số nào là chẩn đoán và guardrail?
2. Conversion trước và sau là bao nhiêu? Tăng bao nhiêu **điểm phần trăm** và bao nhiêu phần trăm **tương đối**?
3. Activation trước và sau là bao nhiêu? Có thể kết luận việc đổi giao diện là nguyên nhân tăng không?
4. Tính **P85 và P95** của cycle time theo nearest-rank.
5. Với SLE giả định **85% trong 10 ngày**, item A và B nên được đọc ra sao? Có biết chính xác thời gian còn lại không?
6. Throughput trung bình bốn tuần là bao nhiêu? Nếu còn 20 item, điểm tham khảo thô về số tuần là bao nhiêu? Vì sao chưa phải lời hứa?
7. Nếu lỗi mở bài tăng từ 1,2% lên 2,1%, nhóm nên làm gì trước khi tuyên bố cải tiến thành công?
8. Nêu **hai cách làm đẹp số sai** có thể xảy ra nếu lãnh đạo ép “tăng số Done và giảm số bug”.
9. Hãy chọn một cải tiến ở hàng chờ review/CI và nêu metric dùng để đánh giá, cùng guardrail.
10. Viết một quyết định ba câu dựa trên dữ liệu, thể hiện **kết quả quan sát, giới hạn và hành động**.

### Gợi ý lời giải

**Câu 1:** **Activation 7 ngày** có thể là chỉ số outcome chính nếu mục tiêu là bắt đầu học. Conversion và lỗi mở bài là tín hiệu chẩn đoán; tỷ lệ lỗi, an toàn dữ liệu và phản hồi hỗ trợ là guardrails. Cần kiểm tra chất lượng sự kiện và cohort đủ thời gian.

**Câu 2:** Conversion trước là \(180/600=30\%\), sau là \(210/600=35\%\). Tăng **5 điểm phần trăm**; tăng tương đối \(5/30\times100\%\approx16{,}7\%\). Không gọi chung “tăng 5%” nếu muốn tránh nhầm.

**Câu 3:** Trước \(96/160=60\%\); sau \(105/150=70\%\), chênh **10 điểm phần trăm**. Đây là hai tỷ lệ quan sát của cohort khác nhau; chưa chứng minh giao diện là nguyên nhân.

**Câu 4:** Có \(n=20\), vị trí P85 = \(\lceil0{,}85\times20\rceil=17\), giá trị thứ 17 **10 ngày**. Vị trí P95 = \(\lceil0{,}95\times20\rceil=19\), giá trị thứ 19 **13 ngày**.

**Câu 5:** A 9 ngày đang gần mốc tham khảo, nên ưu tiên nhìn hàng chờ review và cách hoàn tất. B 12 ngày đã vượt mốc, cần gỡ môi trường tích hợp và thông báo rủi ro. **Không thể lấy 10 trừ tuổi hiện tại để suy thời gian còn lại**, cũng không lấy P85 gán xác suất trễ riêng cho từng item.

**Câu 6:** Throughput trung bình \((3+5+2+6)/4=4\) item/tuần; 20/4 = **5 tuần** là tham khảo thô. Dữ liệu biến động lớn, backlog có thể đổi và loại item không hoàn toàn đồng nhất; cần dự báo có bất định.

**Câu 7:** Kiểm tra số yêu cầu, định nghĩa lỗi, tính tin cậy dữ liệu và nguyên nhân kỹ thuật. Không mở rộng rollout chỉ vì conversion cao hơn nếu guardrail chất lượng xấu đi.

**Câu 8:** Chia item thành ticket vô nghĩa hoặc đánh dấu Done khi chưa đạt DoD; giảm số bug bằng cách không ghi nhận, đổi nhãn hoặc bỏ kiểm thử phát hiện lỗi. Đây là ví dụ tối ưu số làm hại mục tiêu thật.

**Câu 9:** Thử chia PR nhỏ và cùng review trước khi kéo PBI mới; đo **thời gian chờ review**, Work Item Age ở cột chờ, Cycle Time tới DoD; guardrail là lỗi hồi quy hoặc chất lượng review không xấu đi.

**Câu 10 — Câu trả lời mẫu:**

> “Trong hai cohort đủ thời gian theo dõi, conversion tăng từ 30% lên 35%, activation từ 60% lên 70%, nhưng lỗi mở bài cũng tăng từ 1,2% lên 2,1%. Các số liệu này chưa chứng minh nguyên nhân do giao diện, và cần kiểm tra định nghĩa sự kiện cùng khác biệt giữa cohort. Nhóm sẽ ưu tiên điều tra lỗi mở bài, thử cải thiện đường dẫn sau đăng ký theo phạm vi nhỏ và đánh giá lại activation cùng các guardrail trước khi mở rộng.”

### Bài tập mở rộng

Chọn một câu hỏi thật của nhóm như “Tại sao các PBI vẫn chờ kiểm thử lâu?” và viết một **Metric Brief** theo mẫu ở mục tiếp theo. Sau một hoặc hai kỳ xem lại, trả lời: chỉ số đã giúp **đổi một quyết định cụ thể** hay chỉ tạo thêm báo cáo?

## 26. Mẫu Metric Brief có thể áp dụng ngay

~~~text
Tên phép đo:
  ...

Mục tiêu/giá trị người dùng:
  ...

Quyết định cần hỗ trợ và người chịu trách nhiệm:
  ...

Câu hỏi cụ thể:
  ...

Giả thuyết hiện tại:
  ...

Metric chính, công thức và đơn vị:
  ...

Mốc bắt đầu/kết thúc, cohort hoặc loại item:
  ...

Nguồn dữ liệu và phép kiểm tra độ tin cậy:
  ...

Guardrails và nghĩa vụ bắt buộc:
  ...

Thời gian/cadence xem lại:
  ...

Tín hiệu khiến ta điều tra hoặc đổi kế hoạch:
  ...

Điều không được suy ra từ metric:
  ...

Hành động thử, người phối hợp và mốc đánh giá:
  ...
~~~

### 26.1. Ví dụ điền ngắn cho hàng chờ review

> **Mục tiêu:** Giảm thời gian tới Increment Done mà vẫn giữ chất lượng.  
> **Quyết định:** Có nên giới hạn WIP ở phát triển và tổ chức review sớm hơn?  
> **Câu hỏi:** Hạng mục bị chờ bao lâu trước khi review; hàng chờ có gây tăng Cycle Time?  
> **Metric:** Tuổi item ở Review, thời gian chờ review, Cycle Time toàn luồng; tính theo ngày làm việc và ranh giới đã thống nhất.  
> **Guardrail:** Lỗi tích hợp, lỗi hồi quy và DoD không được xấu đi.  
> **Thử:** Ưu tiên cùng hoàn tất item chờ lâu, chia PR nhỏ, xem lại sau vài tuần.  
> **Không suy ra:** Người có PR chờ lâu là người làm việc kém.

## 27. Checklist chọn chỉ số theo câu hỏi và quyết định

### Xác định điều cần biết

1. **Mục tiêu:** Có kết quả sản phẩm hoặc dòng công việc có ý nghĩa không?
2. **Người quyết định:** Ai sẽ dùng kết quả, trong quyền hạn nào?
3. **Câu hỏi:** Câu hỏi đủ cụ thể để có thể kiểm chứng không?
4. **Hành động:** Nếu metric thay đổi, kế hoạch nào có thể khác đi?
5. **Đúng cấp độ:** Cần outcome, flow, quality, kỹ thuật hay dự báo?
6. **Proxy:** Nếu đo thay thế, nhóm có nêu rõ giới hạn không?

### Định nghĩa phép đo

7. **Công thức:** Tử số, mẫu số, đơn vị và cách làm tròn rõ chưa?
8. **Workflow:** Start/Done và quy tắc đếm thời gian nhất quán chưa?
9. **Cohort:** Những đối tượng chưa đủ thời gian quan sát đã được tách đúng chưa?
10. **Loại item:** Có trộn lỗi khẩn, story thường và nghiên cứu vào cùng phân bố không?
11. **Nguồn dữ liệu:** Có thể kiểm tra event hoặc trạng thái ban đầu không?
12. **Độ tin cậy:** Có dữ liệu thiếu, trùng, clock sai, thay đổi schema không?
13. **Quyền dữ liệu:** Việc thu thập và sử dụng có đúng phạm vi được phép?

### Diễn giải và cân bằng

14. **Ngữ cảnh:** Có nhìn thay đổi sản phẩm, mùa vụ, loại công việc, WIP và rủi ro?
15. **Phân bố:** Có xem biến động và phần đuôi thay vì chỉ số trung bình?
16. **WIP còn dở:** Có xem Work Item Age, không chỉ item Done?
17. **Bất định:** Cỡ mẫu và giới hạn dự báo có được nêu rõ?
18. **Nhân quả:** Có tránh nhầm khác biệt trước/sau với kết luận nhân quả?
19. **Guardrail:** Có chỉ số phát hiện tác dụng phụ của tối ưu?
20. **Goodhart:** Nếu metric thành chỉ tiêu cứng, người ta có thể làm đẹp bằng cách nào?
21. **DoD:** Không đánh đổi chất lượng cần thiết chỉ để số đẹp hơn?

### Chuyển thành quyết định

22. **Thử nghiệm:** Có thể chọn hành động nhỏ, có giới hạn để học?
23. **Người phụ trách:** Có người chủ động xem lại bằng chứng và phối hợp?
24. **Cadence:** Nhịp xem có phù hợp tốc độ xuất hiện tín hiệu?
25. **Minh bạch:** Kết luận có phân biệt quan sát, giả thuyết và quyết định?
26. **So sánh được:** Khi đổi định nghĩa metric có lưu lịch sử không?
27. **Cải tiến:** Sau khi xem, nhóm có thực sự thay đổi quyết định hay chỉ tạo báo cáo mới?

## 28. Tổng kết: đo để học và hành động

Không có một bộ chỉ số duy nhất biến mọi đội thành Agile. Việc đo lường có giá trị khi **câu hỏi đúng được đặt trước**, dữ liệu đủ tin cậy và kết quả dẫn tới một quyết định có trách nhiệm.

| Khi bắt đầu từ chỉ số | Khi bắt đầu từ câu hỏi và quyết định |
| --- | --- |
| “Phải tăng velocity!” | “Điều gì đang làm Increment có giá trị đến muộn?” |
| “Tăng số story Done!” | “Giảm WIP hoặc gỡ hàng chờ nào giúp hoàn tất thật?” |
| “Conversion đã tăng, sản phẩm thành công!” | “Người học có bắt đầu học và tiếp tục học tốt hơn?” |
| “Pipeline xanh, chắc không có lỗi!” | “Những ranh giới rủi ro nào đã được kiểm chứng?” |
| “P85 là ngày phải Done cho mọi việc!” | “Phân bố lịch sử giúp kỳ vọng và nhận diện item già như thế nào?” |
| “Dữ liệu tốt hơn sau thay đổi chứng minh nguyên nhân!” | “Có yếu tố nào khác, kiểm chứng nhân quả bằng cách nào?” |
| “Dùng KPI để xếp hạng người làm.” | “Công đoạn, phụ thuộc và thỏa thuận nào cần cải thiện?” |
| “Báo cáo có nhiều biểu đồ.” | “Nhóm đã quyết định, thử và học được điều gì?” |

**Ghi nhớ:** **Mục tiêu → Quyết định → Câu hỏi → Chỉ số → Bằng chứng → Hành động → Học hỏi** là một vòng lặp, không phải danh sách KPI cố định. Trong **AGILE_DEVELOPMENT**, chỉ số dòng công việc hỗ trợ Kanban và dự báo; tín hiệu về Sprint Goal, Increment và DoD giúp Scrum giữ trọng tâm giá trị và chất lượng; kiểm thử, CI và quan sát vận hành hỗ trợ XP; outcome và phản hồi người dùng giúp Product Backlog thích ứng. Đo **đúng điều quan trọng, đúng ranh giới, cùng guardrail và mức bất định** sẽ giúp nhóm giao phần tăng dần đáng tin hơn và cải tiến liên tục mà không biến con số thành mục đích cuối cùng.
