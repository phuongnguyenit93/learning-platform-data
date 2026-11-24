# Quản lý tuổi công việc cùng kỳ vọng thời gian phục vụ

## 1. Vấn đề: công việc đã bắt đầu nhưng vẫn chưa hoàn tất

Một nhóm phát triển nền tảng học trực tuyến vận hành theo Kanban. Trên bảng công việc, nhóm thấy:

- Hạng mục **A — Sửa nhãn trình độ khóa học** mới bắt đầu hai ngày và đang được kiểm thử.
- Hạng mục **B — Lưu khóa học yêu thích** đã bắt đầu chín ngày, đang chờ review.
- Hạng mục **C — Đồng bộ trạng thái đăng ký** đã bắt đầu mười hai ngày, bị chặn vì môi trường tích hợp.
- Hạng mục **D — Cải thiện bộ lọc khóa học** đã bắt đầu bốn ngày, đang được phát triển.

Nếu chỉ nhìn số lượng việc **Done** trong tuần, nhóm có thể bỏ qua B và C vì chúng chưa hoàn tất nên chưa có số liệu *cycle time* cuối cùng. Nhưng chính những hạng mục chưa xong ấy có thể là nguồn rủi ro lớn nhất đối với người học và kế hoạch sản phẩm.

Kanban giúp nhóm **nhìn thấy công việc đang chảy qua hệ thống**, quản lý lượng việc đang làm và cải tiến khả năng hoàn tất giá trị. Hai khái niệm đặc biệt hữu ích là:

1. **Work Item Age (tuổi công việc):** Hạng mục đang thực hiện đã trôi qua bao lâu tính từ lúc bắt đầu?
2. **Service Level Expectation — SLE (kỳ vọng thời gian phục vụ):** Dựa trên những gì đã biết, hệ thống được kỳ vọng hoàn tất một hạng mục trong bao lâu với một mức xác suất/kỳ vọng được diễn đạt rõ?

Kết hợp chúng giúp nhóm chuyển câu hỏi từ **“Ai đang bận việc gì?”** sang **“Công việc nào đang có nguy cơ già đi trong luồng, vì sao và nhóm cần hành động gì để hoàn tất giá trị?”**.

Đây là nội dung thuộc module **AGILE_DEVELOPMENT**: áp dụng phản hồi sớm, quản lý backlog, giao phần tăng dần, thực hành Scrum, Kanban, XP và đo lường dòng công việc để thích ứng. Mục tiêu của đo lường không phải ép cá nhân làm nhanh bằng mọi giá, mà là nâng khả năng dự báo, chất lượng và nhịp giao hàng bền vững.

## 2. Phân biệt tuổi công việc, thời gian hoàn thành và kỳ vọng phục vụ

Một hạng mục đi từ “đã bắt đầu” đến “hoàn tất” qua nhiều bước: phát triển, review, kiểm thử và tích hợp. Các chỉ số sau trả lời những câu hỏi khác nhau.

| Chỉ số | Đối tượng được đo | Cách hiểu | Đơn vị minh họa |
| --- | --- | --- | --- |
| **Work Item Age** | Hạng mục **đã bắt đầu nhưng chưa hoàn tất** | Thời gian từ mốc bắt đầu đến **hiện tại** | 9 ngày làm việc |
| **Cycle Time** | Hạng mục **đã hoàn tất** | Thời gian từ mốc bắt đầu đến mốc hoàn tất | 8 ngày làm việc |
| **Throughput** | Các hạng mục hoàn tất trong một khoảng | Số việc thực sự Done mỗi tuần/tháng | 5 hạng mục/tuần |
| **Work in Progress (WIP)** | Các hạng mục đang trong luồng | Số việc đã bắt đầu nhưng chưa Done trong phạm vi đo | 7 hạng mục |
| **SLE** | Một loại hạng mục trong luồng đã định nghĩa | Kỳ vọng về thời gian hoàn tất, thường biểu thị bằng **mốc thời gian và xác suất** | Khoảng 85% trong ≤ 10 ngày |
| **Lead Time** | Yêu cầu theo ranh giới từ lúc phát sinh/tiếp nhận tới khi được đáp ứng | Thời gian chờ và thực hiện theo mốc đã chọn | 15 ngày từ yêu cầu đến giao |

**Cycle Time và Work Item Age dùng cùng một mốc “bắt đầu” nếu muốn so sánh trực tiếp**. Điểm khác biệt là cycle time chỉ trở thành một giá trị hoàn chỉnh khi hạng mục Done; tuổi công việc tăng theo thời gian khi hạng mục còn dở.

Ví dụ:

- Story được bắt đầu từ đầu ngày làm việc thứ nhất, hoàn tất cuối ngày làm việc thứ sáu theo chính sách đo của nhóm: cycle time có thể được ghi là **6 ngày làm việc**, nếu nhóm định nghĩa cách đếm như vậy.
- Một story khác bắt đầu theo cùng cách nhưng đến hết ngày thứ chín vẫn chưa Done: work item age lúc đó là **9 ngày làm việc**. **Không được gán cycle time bằng 9 cho story chưa hoàn tất.**

Tuổi công việc không nói bản thân hạng mục đã hoàn thành được bao nhiêu phần trăm. Một item chín ngày tuổi có thể gần Done hoặc vẫn ở đầu luồng vì phụ thuộc chưa được giải quyết. Vì vậy cần đọc **số liệu cùng trạng thái thực tế**.

## 3. Định nghĩa luồng trước khi tính toán

Một con số có vẻ chính xác nhưng dùng ranh giới đo không nhất quán sẽ dễ gây hiểu lầm. Nhóm cần thống nhất chính sách đo ngay tại **Definition of Workflow** hoặc nơi mô tả cách vận hành Kanban.

~~~mermaid
flowchart LR
    A["Chưa bắt đầu<br/>Backlog"] --> B["Đã bắt đầu<br/>Thực hiện"]
    B --> C["Review và kiểm thử"]
    C --> D["Hoàn tất theo chính sách Done"]
    C -->|"Phát hiện lỗi"| B
~~~

*Sơ đồ là ví dụ luồng công việc; tên cột và số bước tùy hệ thống.*

### 3.1. Chọn mốc bắt đầu và kết thúc

Ví dụ, nhóm phát triển chức năng đăng ký khóa học thống nhất:

- **Bắt đầu:** Thời điểm một PBI được kéo từ “Sẵn sàng” sang “Đang thực hiện”, khi nhóm thực sự tiêu thụ năng lực để tạo kết quả.
- **Hoàn tất:** Thời điểm hạng mục đạt chuẩn chất lượng áp dụng và chuyển sang “Done”; nếu nhóm dùng Scrum, điều này phải thống nhất với **Definition of Done** của Increment.
- **Đang làm:** Tất cả trạng thái nằm giữa hai mốc, bao gồm phát triển, review, kiểm thử và **Blocked**.
- **Đơn vị:** Ngày làm việc hoặc ngày lịch; chọn một cách và giải thích rõ cách tính ngày bắt đầu, ngày nghỉ, mốc giờ.

Nếu nhóm muốn biết **bao lâu từ lúc khách hàng yêu cầu đến khi sử dụng được**, nên đo thêm lead time theo mốc yêu cầu và giao hàng. Không được mặc định thời điểm “Done” luôn trùng lúc người dùng được phát hành tính năng.

### 3.2. Công việc bị chặn có tiếp tục già đi không?

**Có, nếu nó đã vượt qua mốc bắt đầu và chưa đạt mốc hoàn tất.** Hạng mục đang chờ quyền truy cập, quyết định nghiệp vụ, môi trường kiểm thử hoặc review vẫn tiêu thụ **thời gian trôi qua đối với luồng**.

Nhóm có thể đo riêng **blocked time** để chẩn đoán nguyên nhân, nhưng không nên lặng lẽ dừng đồng hồ tuổi công việc khi chuyển sang cột Blocked. Làm vậy có thể khiến báo cáo đẹp hơn trong khi người dùng vẫn phải chờ.

Chỉ khi chính sách đo từ trước định nghĩa một luồng khác, nhóm mới có cơ sở dùng một đồng hồ khác; khi so sánh cần ghi rõ sự khác biệt và tránh trộn tập dữ liệu.

### 3.3. Quy tắc dữ liệu tối thiểu

| Quy tắc | Vì sao quan trọng? |
| --- | --- |
| Mỗi item có thời điểm bắt đầu và loại công việc | Đủ dữ liệu tính tuổi và chọn nhóm so sánh |
| Item chỉ được tính Done khi đạt định nghĩa hoàn tất | Tránh báo nhanh bằng cách bỏ kiểm thử |
| Hạng mục chưa Done vẫn xuất hiện trong danh sách tuổi | Tránh thiên lệch chỉ nhìn việc dễ hoàn tất |
| Trạng thái Blocked có nguyên nhân và bước gỡ | Dữ liệu dẫn tới hành động |
| Chính sách làm tròn ngày/giờ nhất quán | Tránh sai khác do cách đếm |
| Phân tách loại công việc thật sự khác nhau khi cần | Không áp kỳ vọng của lỗi nhỏ cho tích hợp phức tạp |
| Ghi nhận khi thay đổi ranh giới workflow | Tránh so sánh sai trước và sau cải tiến |

Không nên tạo các “hạng mục giả Done” chỉ để khởi động lại đồng hồ. Nếu tách story vì lý do giá trị và triển khai hợp lý, cần giữ dấu vết và diễn giải thay đổi cách đếm.

## 4. Xây dựng SLE từ dữ liệu Cycle Time

Một **Service Level Expectation (SLE)** hữu ích trả lời:

> “Với **loại công việc và ranh giới workflow** này, **bao nhiêu phần trăm** hạng mục được kỳ vọng hoàn tất trong **không quá bao nhiêu thời gian**?”

Ví dụ:

> “Đối với user story có kích thước tương đối nhỏ, từ lúc vào trạng thái Đang thực hiện đến lúc đạt Done, chúng tôi kỳ vọng khoảng **85% hạng mục hoàn tất trong không quá 10 ngày làm việc**.”

Phát biểu trên cần có **đơn vị thời gian**, **mốc bắt đầu/kết thúc**, **mức kỳ vọng** và **phạm vi loại công việc**. Một con số “10 ngày” đứng riêng sẽ khó biết là trung bình, giới hạn, hứa hẹn hay quy ước.

Khi có dữ liệu Cycle Time lịch sử, nhóm có thể dùng phân vị (*percentile*) để tạo SLE có căn cứ. Khi chưa có dữ liệu, nhóm có thể nêu **SLE ban đầu là giả thuyết** dựa trên nhu cầu phục vụ và hiểu biết hiện tại, đồng thời bắt đầu ghi số liệu để kiểm chứng và điều chỉnh. Không nên giả vờ có xác suất thực nghiệm khi chưa quan sát.

### 4.1. Ví dụ: 20 hạng mục đã hoàn tất

Giả sử cùng một nhóm đã hoàn tất 20 user story có loại công việc và mốc đo tương đồng. **Cycle Time tính bằng ngày làm việc**, đã xếp từ nhỏ đến lớn:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

| Thống kê | Giá trị | Cách diễn giải |
| --- | ---: | --- |
| Số item | 20 | Đây là mẫu nhỏ để học phương pháp |
| Cycle Time ngắn nhất | 2 ngày | Giá trị quan sát, không phải mức tốt nhất có thể mãi mãi |
| Trung vị | 6 ngày | Giá trị ở vị trí 10 và 11 đều là 6 |
| P85 theo **nearest-rank** | 10 ngày | Vị trí \(\lceil0{,}85\times20\rceil=17\) |
| P95 theo **nearest-rank** | 13 ngày | Vị trí \(\lceil0{,}95\times20\rceil=19\) |
| Lâu nhất | 18 ngày | Một trường hợp đuôi dài đáng điều tra |

Trong mẫu này, **17/20 = 85%** hạng mục hoàn tất trong không quá **10 ngày làm việc**. Nhóm có thể chọn SLE khởi đầu “85% trong 10 ngày” để cùng quan sát và cải tiến.

**Lưu ý:** Có nhiều cách ước lượng phân vị, nên các phần mềm thống kê có thể đưa ra con số khác trên mẫu nhỏ. Bài này dùng **nearest-rank**; khi báo cáo thật, cần công bố phương pháp tính và phạm vi dữ liệu. Không lấy con số P85 của bảng này áp dụng cho mọi sản phẩm.

### 4.2. Cách tính phân vị nearest-rank

Với \(n\) giá trị đã sắp tăng dần và phân vị \(p\) từ 0 đến 1:

\[
\text{Vị trí phân vị} = \left\lceil p\times n\right\rceil
\]

Ví dụ, \(p=0{,}85\), \(n=20\), vị trí là \(\lceil17\rceil=17\). Giá trị thứ 17 trong dãy là 10. Với \(p=0{,}95\), vị trí thứ 19 bằng 13.

Đây là cách mô tả **phân bố quan sát**, không phải mô hình hoàn chỉnh về các tình huống tương lai. Với 20 quan sát, phát biểu “85% đã xong trong 10 ngày” đúng với mẫu nhưng **không đủ để khẳng định chính xác 85% mọi item tương lai cũng sẽ xong trong 10 ngày**.

### 4.3. Vì sao không chỉ dùng Cycle Time trung bình?

Nếu một số hạng mục kéo dài lâu vì phụ thuộc, trung bình có thể che rủi ro ở phần đuôi phân bố. SLE biểu diễn bằng mốc và xác suất/kỳ vọng giúp đối thoại rõ hơn về mức phục vụ.

Tuy nhiên, **SLE không phải mốc thời gian mà mọi hạng mục phải đạt**. Nếu đặt SLE P85, điều đó tự nó đã hàm ý có phần công việc hoàn tất muộn hơn mốc trong dữ liệu tham chiếu. Nhóm cần tìm cách giảm chậm trễ và trao đổi sớm, không được tự ý hạ chất lượng để “đạt 100% đúng hạn SLE”.

## 5. SLE không phải SLA và cũng không phải Definition of Done

Các thuật ngữ nghe gần giống nhưng có mục đích khác:

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **SLE — Service Level Expectation** | Kỳ vọng xác suất về thời gian hạng mục đi qua workflow | “Khoảng 85% story loại A hoàn tất trong ≤ 10 ngày làm việc” |
| **SLA — Service Level Agreement** | Cam kết mức dịch vụ mang tính thỏa thuận chính thức, có thể gắn trách nhiệm/hợp đồng | Hợp đồng yêu cầu phản hồi sự cố mức nghiêm trọng cao trong thời hạn xác định |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng để công việc trở thành phần sản phẩm hoàn tất | Kiểm thử bắt buộc đạt, tích hợp thành công, thỏa yêu cầu bảo mật áp dụng |
| **Acceptance Criteria** | Hành vi và quy tắc một PBI cần đáp ứng | Lưu khóa yêu thích hai lần không tạo bản ghi trùng |
| **Deadline / mốc kinh doanh** | Thời điểm mục tiêu cần đạt theo kế hoạch hoặc cam kết bên ngoài | Phiên bản phục vụ khai giảng vào ngày nhất định |

**SLE không tự biến thành SLA** chỉ vì nhóm đưa vào dashboard hoặc có người gọi là “deadline”. Nếu sản phẩm chịu ràng buộc hợp đồng, pháp lý hoặc bảo mật, nghĩa vụ đó vẫn phải được thực hiện và được quản trị theo đúng thẩm quyền.

**SLE không thay thế DoD.** Một PBI hoàn thành sau 6 ngày nhưng chưa kiểm thử tích hợp cần thiết **không được tính Done** chỉ vì muốn bảng Cycle Time đẹp. Đo lường phải dựa trên giá trị hoàn tất thực sự.

### 5.1. SLE là một kỳ vọng sống

SLE nên được xem lại khi:

- Chuẩn Done hoặc ranh giới bắt đầu/kết thúc thay đổi.
- Loại công việc chuyển từ sửa lỗi nhỏ sang tích hợp phức tạp.
- Năng lực nhóm hoặc phụ thuộc vận hành thay đổi đáng kể.
- Có nhiều item vượt mốc và nguyên nhân cho thấy workflow đang nghẽn.
- Nhóm cải tiến thành công kiểm thử, review, hạ tầng và có số liệu mới.

Điều chỉnh SLE để phản ánh hệ thống không phải thất bại. Nhưng **đổi SLE liên tục chỉ để làm tỷ lệ đạt đẹp hơn** sẽ khiến kỳ vọng mất giá trị. Nên giữ lịch sử phiên bản, lý do điều chỉnh và trao đổi với bên sử dụng thông tin.

## 6. Dùng Work Item Age để quản lý công việc hiện tại

Cycle Time cho biết quá khứ **đã hoàn tất**. Work Item Age phản ánh tình trạng của những item **chưa Done** ngay lúc nhóm cần quyết định.

### 6.1. Ví dụ bảng tuổi công việc

Giả sử nhóm đang dùng SLE tham khảo **85% trong 10 ngày làm việc** cho loại story nhỏ, cùng ranh giới đo. Tuổi các hạng mục ở cuối một ngày làm việc:

| Item | Trạng thái | Work Item Age | So với mốc 10 ngày | Hành động cần xem xét |
| --- | --- | ---: | ---: | --- |
| A — Sửa nhãn trình độ | Kiểm thử | 2 ngày | 20% mốc | Theo dõi bình thường, tiếp tục làm rõ DoD |
| B — Lưu khóa yêu thích | Chờ review | 9 ngày | 90% mốc | Ưu tiên review, kiểm tra điều đang chờ |
| C — Đồng bộ đăng ký | Blocked | 12 ngày | 120% mốc | Trao đổi trực tiếp về nút nghẽn, hỗ trợ/leo thang |
| D — Bộ lọc khóa học | Đang phát triển | 4 ngày | 40% mốc | Kiểm tra tiến độ và phụ thuộc cần thiết |
| E — Xác nhận email | Đang tích hợp | 7 ngày | 70% mốc | Xem rủi ro tích hợp và chuẩn bị kiểm thử sớm |

Các tỷ lệ 20%, 90%, 120% là **tuổi chia cho mốc thời gian SLE**, **không phải tỷ lệ hoàn thành công việc**, cũng **không phải xác suất thất bại**. Một item đã 9 ngày không có nghĩa “chắc 90% sẽ trễ” hoặc “đã xong 90%”.

### 6.2. Vì sao tuổi tăng cần chú ý?

Khi công việc đang tồn lâu, nó có thể gặp:

- Hàng chờ review hoặc kiểm thử quá dài.
- Phụ thuộc bên ngoài chưa có người giải quyết.
- Story quá lớn hoặc thiếu tiêu chí chấp nhận.
- Công việc bị gián đoạn nhiều lần bởi yêu cầu khẩn.
- Tích hợp muộn, lỗi khó phát hiện hoặc thay đổi nghiệp vụ.
- Quyền quyết định không rõ, nhóm đợi phản hồi quá lâu.

Tuổi công việc là **tín hiệu cần điều tra**, không phải bằng chứng một cá nhân làm việc kém. Một hạng mục 12 ngày có thể già đi chủ yếu vì cần phê duyệt bảo mật hoặc môi trường kiểm thử, không phải vì người thực hiện thiếu năng lực.

### 6.3. Ưu tiên tuổi cao không có nghĩa bỏ hết yếu tố khác

Nếu item C đã 12 ngày nhưng đang chờ phê duyệt pháp lý mà nhóm không thể tự giải quyết, một hành động hữu ích là **leo thang đúng kênh và ghi rõ thời gian phản hồi mong đợi**. Song song, nhóm có thể hoàn tất B đang chờ review để giảm hàng đợi.

Mặt khác, một sự cố thanh toán nghiêm trọng mới xuất hiện có thể cần ưu tiên hơn cả C, dù tuổi mới bằng một giờ. **Mức độ khẩn và tác động kinh doanh, an toàn** vẫn phải được xem cùng tuổi.

Đừng tạo chính sách cứng “item già nhất luôn được phục vụ trước” cho mọi tình huống. Kanban cần **chính sách luồng rõ**, phù hợp loại công việc và mục tiêu giá trị.

## 7. Aging WIP Chart: nhìn tuổi công việc ở đâu trong luồng?

Bảng Kanban thông thường trả lời “công việc nằm ở cột nào?”. **Aging WIP Chart** kết hợp vị trí trong workflow với **tuổi hiện tại**, giúp thấy hạng mục chậm đang nằm tại công đoạn nào.

Ví dụ minh họa bằng bảng:

| Item | Đang phát triển | Review | Kiểm thử | Blocked | Tuổi |
| --- | --- | --- | --- | --- | ---: |
| A | | | ● | | 2 |
| B | | ● | | | 9 |
| C | | | | ● | 12 |
| D | ● | | | | 4 |
| E | | | ● | | 7 |

Trong công cụ biểu đồ, mỗi item có thể là một điểm nằm tại công đoạn hiện hành và độ cao theo tuổi. Các **đường phân vị cycle time lịch sử** giúp nhóm nhận ra item nào đang tiến gần hoặc vượt những mốc thường gặp.

Đọc biểu đồ theo ba chiều:

1. **Tuổi:** Hạng mục đã ở trong hệ thống bao lâu?
2. **Vị trí:** Nó đang chờ tại bước nào?
3. **Mức rủi ro:** So với phân bố hoàn tất của loại công việc tương đồng, hạng mục đã tiến gần vùng cần chú ý chưa?

**Không được suy từ vị trí cột rằng một item “đã hoàn thành 80%”**. Một lỗi phát hiện trong kiểm thử có thể cần thay đổi thiết kế và đưa công việc quay lại bước trước.

### 7.1. Quy tắc cảnh báo có thể thử

Nhóm có thể chọn một quy tắc **tham khảo, không bắt buộc**:

| Tín hiệu | Hành động gợi ý |
| --- | --- |
| Tuổi còn thấp so với SLE, không bị chặn | Tiếp tục phối hợp và kiểm tra tiến độ |
| Tuổi tiệm cận mốc SLE hoặc có nguy cơ tắc nghẽn | Hỏi rõ điều còn thiếu để Done, ưu tiên giảm hàng chờ |
| Tuổi đã vượt mốc SLE | Cùng xem nguyên nhân, thông báo rủi ro, gỡ chặn và điều chỉnh kế hoạch |
| Item có tác động an toàn/nghiệp vụ khẩn | Áp chính sách phục vụ khẩn được phê duyệt, bất kể tuổi |

Nếu dùng các mức như 70%, 90%, 100% của mốc SLE để trực quan cảnh báo, cần ghi rõ chúng là **ngưỡng chú ý do nhóm thử nghiệm**, không phải phần trăm xác suất hay quy định chung của Kanban.

## 8. Phản ứng khi một item già đi

Quản lý tuổi hiệu quả không kết thúc bằng một cột màu đỏ; nhóm phải xác định và thực hiện hành động giúp item đạt Done.

~~~mermaid
flowchart TD
    A["Quan sát Work Item Age và trạng thái"]
    B{"Có nguy cơ kéo dài hoặc đang bị chặn?"}
    C["Tiếp tục theo dõi trong luồng"]
    D["Xác định nguyên nhân và tác động"]
    E{"Nhóm tự gỡ được?"}
    F["Cùng review, kiểm thử, chia nhỏ hoặc hỗ trợ"]
    G["Chuyển đúng người có quyền giải quyết"]
    H["Cập nhật bảng, dự báo và thông tin liên quan"]
    I["Kiểm tra kết quả: đã đạt Done chưa?"]
    A --> B
    B -->|"Chưa"| C
    B -->|"Có"| D
    D --> E
    E -->|"Có"| F
    E -->|"Chưa"| G
    F --> H
    G --> H
    H --> I
    I -->|"Chưa"| A
~~~

### Bước 1 — Xác định trở ngại thật

Một bản ghi “Blocked” nên trả lời:

> **Hạng mục:** C — Đồng bộ đăng ký.  
> **Tuổi hiện tại:** 12 ngày làm việc tính từ mốc bắt đầu đã thống nhất.  
> **Vướng mắc:** Môi trường tích hợp chưa cấp quyền truy cập dịch vụ đăng ký.  
> **Tác động:** Không thể kiểm tra luồng đồng bộ và xác nhận điều kiện Done.  
> **Người có thể hỗ trợ:** Bộ phận vận hành môi trường, theo kênh được phê duyệt.  
> **Bước tiếp theo:** Gửi yêu cầu cấp quyền với thông tin cần thiết, thống nhất thời điểm kiểm tra lại và thông báo rủi ro cho người phụ trách ưu tiên.

Thông tin trên hữu ích hơn một nhãn đỏ không có người nhận hoặc kế hoạch gỡ.

### Bước 2 — “Ngừng bắt đầu, bắt đầu hoàn tất”

Khi cột Review có nhiều item già đi, kéo thêm story vào phát triển có thể tăng **WIP** mà không cải thiện **throughput**. Nhóm có thể:

- Chuyển người có thể hỗ trợ sang review và kiểm thử.
- Làm việc cặp để tháo gỡ lỗi hoặc chuyển giao kiến thức.
- Ưu tiên sửa lỗi tích hợp của item gần Done.
- Chia bớt phạm vi chưa thiết yếu nếu người có trách nhiệm sản phẩm đồng thuận.
- Kiểm tra giới hạn WIP và chính sách kéo việc mới.

Không phải mọi người đều được phép thực hiện mọi thao tác; cần tôn trọng kỹ năng chuyên môn, quyền truy cập và tiêu chuẩn an toàn. Việc hỗ trợ nhau phải giúp **hoàn tất kết quả** chứ không tạo thêm chuyển giao không cần thiết.

### Bước 3 — Minh bạch tác động với bên liên quan

Nếu tuổi của item có giá trị lớn đã vượt kỳ vọng, hãy trao đổi **trạng thái, trở ngại, phương án, bước tiếp theo**. Không nên hứa “xong trong hai ngày nữa” chỉ dựa trên việc item đã 12 ngày so với SLE 10 ngày.

Một cách cập nhật:

> “Hạng mục đồng bộ đăng ký hiện đã 12 ngày làm việc, cao hơn mốc SLE 10 ngày tham khảo cho loại công việc này. Nguyên nhân chính là chờ môi trường tích hợp. Chúng tôi đang phối hợp cấp quyền, ưu tiên kiểm thử ngay sau khi có môi trường và sẽ cập nhật dự báo khi trở ngại được gỡ. Mốc SLE là kỳ vọng dựa trên phân bố, không phải thời hạn hoàn tất được bảo đảm.”

## 9. Khi item đã vượt SLE, còn bao lâu mới xong?

Đây là một câu hỏi dễ mắc lỗi thống kê.

Giả sử SLE là “85% trong không quá 10 ngày” và item C đã **12 ngày** chưa xong. Không thể suy ra:

- “Item này chỉ còn \(10-12=-2\) ngày.”
- “Vì 85% item xong trong 10 ngày nên xác suất nó xong ngày mai là 85%.”
- “Cycle time lớn nhất lịch sử là 18 ngày nên chắc chắn còn tối đa 6 ngày.”

**SLE mô tả phân bố thời gian hoàn tất của một nhóm hạng mục**, không trực tiếp cho ta phân bố thời gian còn lại **có điều kiện item hiện đã tồn tại 12 ngày mà chưa Done**.

Nếu muốn ước lượng **thời gian còn lại** một cách định lượng, cần phương pháp phù hợp với dữ liệu còn dở và điều kiện hiện tại, chẳng hạn mô hình xác suất có điều kiện hoặc phân tích thời gian đến khi hoàn tất (*survival analysis*) trong bối cảnh đủ dữ liệu. Đối với công việc có phụ thuộc đặc biệt, **điều tra trạng thái thực tế** có thể giá trị hơn một phép tính thống kê chung.

### 9.1. Thiên lệch khi chỉ nhìn item đã hoàn tất

Giả sử tuần này ba item dễ được Done sau 2–3 ngày, nhưng hai item khó đã làm 20 ngày vẫn nằm trong WIP. Thống kê cycle time **chỉ của các item Done trong tuần** sẽ có vẻ rất nhanh, trong khi khách hàng vẫn đang chờ lâu.

Đó là lý do Kanban cần xem **cycle time của item đã Done cùng với work item age của item chưa Done**. Một hệ thống có WIP ngày càng già mà throughput nhất thời vẫn cao không thể được kết luận là khỏe mạnh chỉ từ số trung bình.

### 9.2. Quy tắc ngoại lệ và đồng hồ đo

Nếu một item bị tạm dừng vì khách hàng chưa quyết định, nhóm có thể cần phân loại hoặc chuyển trạng thái. Nhưng nếu item đã bắt đầu và vẫn nằm trong phạm vi workflow, tuổi không biến mất.

Nếu tổ chức có chính sách **dừng đồng hồ SLA** theo hợp đồng, đó là quy tắc phục vụ khác cần ghi rõ. **Không tự áp quy tắc SLA để sửa cách tính Work Item Age hoặc SLE** nếu nhóm chưa xác định lại ranh giới đo và công bố điều đó.

## 10. Phối hợp SLE với loại công việc và mức độ khẩn

Không phải mọi item cần một SLE giống nhau. Công việc có thể khác về độ lớn, rủi ro, thời gian chờ và mục tiêu phục vụ:

| Loại công việc | Ví dụ | Điều cần làm rõ |
| --- | --- | --- |
| **User story thường** | Lưu khóa học yêu thích, lọc khóa theo trình độ | Mốc bắt đầu/Done, cách chia story và phân bố Cycle Time |
| **Lỗi sản phẩm** | Nút đăng ký hiển thị sai trạng thái | Mức độ nghiêm trọng, đường xử lý và kiểm chứng |
| **Sự cố khẩn cấp** | Thanh toán lỗi diện rộng hoặc dữ liệu bị lộ | Chính sách ứng cứu, quyền ưu tiên và nghĩa vụ ngoài Kanban |
| **Bảo trì phòng ngừa** | Nâng cấp thư viện sắp hết hỗ trợ | Mức rủi ro khi trì hoãn, thời hạn phụ thuộc |
| **Nghiên cứu/khám phá** | Thử xem người học hiểu nhãn trình độ không | Kết quả học hỏi được coi là Done, giới hạn phạm vi thử nghiệm |

Nếu dữ liệu các loại công việc có phân bố rất khác, gộp chung sẽ tạo một mốc SLE thiếu ý nghĩa. Nhóm có thể chọn **phân nhóm đúng mức**, miễn mỗi nhóm có đủ dữ liệu để diễn giải thận trọng.

### 10.1. Class of Service không phải một bảng màu trang trí

Nhóm có thể định nghĩa các chính sách phục vụ cho:

- **Tiêu chuẩn:** Kéo theo thứ tự ưu tiên và năng lực đã thống nhất.
- **Ngày cố định (fixed date):** Xem xét phụ thuộc mốc triển khai hoặc yêu cầu bên ngoài.
- **Khẩn cấp (expedite):** Ưu tiên theo tiêu chí tác động nghiêm trọng được xác định rõ.
- **Công việc vô hình/duy trì:** Dành năng lực cho hạ tầng, kiểm thử và rủi ro tích lũy.

Đây là **các kiểu chính sách thường được dùng**, không phải bộ phân loại bắt buộc với tên gọi và số lượng cố định cho mọi đội. Quan trọng là:

1. Khi nào một item đủ điều kiện nhận chính sách ưu tiên đặc biệt?
2. Ai có quyền phân loại và ai chịu trách nhiệm thông báo?
3. Những công việc hiện có bị ảnh hưởng như thế nào?
4. Khi đã khẩn, kiểm soát chất lượng và an toàn nào vẫn bắt buộc?
5. Có cần một SLE riêng hoặc một cam kết dịch vụ bên ngoài cho loại công việc đó không?

Không được gắn nhãn “expedite” cho mọi yêu cầu của người có chức vụ. Khi mọi item đều được ưu tiên, chính sách ưu tiên không còn ý nghĩa và dòng công việc thường bị gián đoạn.

## 11. Quản lý tuổi công việc trong nhịp cộng tác của nhóm

Kanban không yêu cầu mọi nhóm phải có một cuộc họp đúng tên, đúng giờ giống nhau. Nhưng **kiểm tra tuổi item đều đặn** giúp nhóm hành động trước khi hạng mục kéo dài quá lâu.

### 11.1. Buổi phối hợp hằng ngày dựa trên bảng

Một cuộc trao đổi ngắn có thể đi theo trình tự:

1. Nhìn những item đã già nhất hoặc đang bị chặn.
2. Hỏi “Điều gì đang ngăn item này Done?” thay vì “Hôm qua bạn làm bao nhiêu giờ?”.
3. Xem nơi nào chạm giới hạn WIP hoặc hàng chờ tăng.
4. Chọn việc nhóm có thể cùng hoàn tất trong ngày.
5. Cập nhật trở ngại, người hỗ trợ, bước tiếp theo và tác động tới ưu tiên.

Không nên hiểu “ưu tiên item già” là ép người đang làm phải tăng tốc bất chấp chất lượng. Hành động tốt thường là **gỡ hàng chờ hoặc giảm phụ thuộc**, không phải yêu cầu một người làm thêm giờ.

### 11.2. Buổi xem lại dòng công việc định kỳ

Theo tuần hoặc nhịp phù hợp, nhóm có thể xem:

- Bao nhiêu item đã vượt SLE và chúng nằm ở bước nào?
- Work Item Age có tăng đều qua nhiều ngày không?
- Có nhiều item bị chặn bởi cùng một phụ thuộc?
- Phân bố Cycle Time có thay đổi sau cải tiến?
- Throughput và WIP có phản ánh dòng hoàn tất ổn định hơn không?
- Mức SLE hiện tại có còn đại diện cho loại công việc được phục vụ không?
- Người dùng có nhận được kết quả sớm hơn và ít lỗi hơn không?

Đầu ra nên là **một hoặc vài thay đổi có thể thử**, như giảm WIP cột phát triển, review sớm hơn, làm rõ nghiệp vụ trước khi kéo việc, cải thiện môi trường tích hợp hoặc tăng tự động hóa kiểm thử.

## 12. Đánh giá mức đạt SLE mà không biến thành KPI sai

Giả sử trong tháng, nhóm có **20 item cùng loại đã Done** và 17 item có cycle time không quá 10 ngày làm việc. Tỷ lệ quan sát:

\[
\text{Tỷ lệ đạt ngưỡng 10 ngày}
=\frac{17}{20}\times100\%=85\%
\]

Nếu tháng sau có **18 item Done**, trong đó **15 item** không quá 10 ngày:

\[
\frac{15}{18}\times100\%\approx83{,}3\%
\]

83,3% thấp hơn mức tham khảo 85%, nhưng **một tháng nhỏ không đủ để kết luận nhóm suy giảm một cách chắc chắn**. Cần xem biến động tự nhiên, đặc điểm item, mức WIP, sự cố bất thường, định nghĩa Done và những item còn nằm dở.

### 12.1. Theo dõi cả lượng đang dở và mức phục vụ đã giao

| Chỉ số | Câu hỏi | Nguy cơ diễn giải sai |
| --- | --- | --- |
| Tỷ lệ item Done trong ngưỡng SLE | Phần công việc đã hoàn tất có phù hợp kỳ vọng lịch sử? | Bỏ qua item chưa Done, mẫu nhỏ |
| Work Item Age phân bố theo trạng thái | Công việc nào có nguy cơ kéo dài và bị chặn ở đâu? | Coi tuổi cao là lỗi cá nhân |
| Cycle Time các phân vị | Đuôi phân bố có giảm khi cải tiến luồng? | So sánh hai tập item khác loại |
| WIP | Có nhiều việc dở dang khiến chờ đợi tăng? | Giấu item đang làm để giảm số WIP |
| Throughput | Nhóm hoàn tất được bao nhiêu item mỗi kỳ? | Chia task nhỏ giả tạo, không đo giá trị |
| Blocked Time/nguồn chặn | Phụ thuộc nào đang làm tăng thời gian chờ? | Dừng đồng hồ age để làm đẹp chỉ số |
| Chất lượng và phản hồi người dùng | Item Done có thật sự hữu ích và ít lỗi? | Tăng tốc bằng cách bỏ kiểm thử |

**Tỷ lệ đạt SLE không nên dùng để xếp hạng lập trình viên**. SLE mô tả **năng lực phục vụ của workflow**, chịu ảnh hưởng của nhiều người, nhiều bước và phụ thuộc. Nếu biến nó thành chỉ tiêu thưởng/phạt cá nhân, người ta có thể tránh item khó, đổi tên hạng mục hoặc đánh dấu Done quá sớm.

### 12.2. Dữ liệu đang thay đổi thì làm gì?

Nếu sau một cải tiến Kanban, nhóm đổi giới hạn WIP và review tốt hơn, có thể dự đoán Cycle Time được cải thiện. Nhưng cần **thu thập mẫu mới**, ghi ngày thay đổi và giải thích khác biệt, thay vì áp nguyên một SLE cũ mãi mãi.

Nếu sản phẩm trải qua mùa tuyển sinh khiến số yêu cầu hỗ trợ tăng đột ngột, cần ghi nhận mức năng lực thực tế và nhu cầu; **không loại các tuần xấu một cách tùy tiện** chỉ để chứng minh workflow “luôn tốt”.

## 13. Quan hệ với Little's Law và khả năng dự báo

Trong hệ thống có ranh giới đo nhất quán và **đủ ổn định**, Little's Law nối các giá trị trung bình:

\[
\text{WIP trung bình} \approx \text{Throughput trung bình}\times\text{Cycle Time trung bình}
\]

Ví dụ độc lập với dữ liệu 20 item ở trên: một luồng có WIP trung bình **8 item** và throughput trung bình **4 item/tuần**. Nếu điều kiện của Little's Law được đáp ứng, cycle time trung bình tương ứng xấp xỉ **2 tuần**.

Điều này gợi ý rằng **giảm WIP và hàng chờ có thể giúp công việc hoàn tất sớm hơn**, nhưng không phải phép bảo đảm: giảm WIP một nửa **không tự động** làm mọi item nhanh gấp đôi. Năng lực, mức phụ thuộc, kích thước hạng mục, chính sách phục vụ và tính ổn định cũng ảnh hưởng hệ thống.

Little's Law nói về **trung bình**, trong khi SLE thường nói về **phân vị/xác suất của Cycle Time**. Không được lấy \(WIP/throughput\) rồi gọi ngay đó là P85 hoặc SLE 85%.

### 13.1. SLE khác dự báo ngày hoàn tất một tập backlog

**SLE** thông thường giúp trao đổi kỳ vọng **một loại item** đi qua workflow. Để dự báo **khi nào xong một nhóm 30 hạng mục**, nhóm cần xem throughput theo thời gian, phạm vi và biến động, có thể dùng mô phỏng phù hợp.

Ví dụ:

- “85% story nhỏ hoàn tất trong không quá 10 ngày kể từ lúc bắt đầu” là một **SLE**.
- “Với throughput 5 item/tuần, 30 item có trung tâm phép chia là khoảng 6 tuần, còn độ bất định cần được đánh giá” là một **nhận định dự báo phạm vi**.

Hai thông tin có thể cùng hỗ trợ lập kế hoạch, nhưng không thể thay thế nhau. Một item mất 10 ngày trong hệ thống không có nghĩa cả 30 item phải được làm tuần tự trong \(30\times10\) ngày; nhiều item có thể chồng lắp trong giới hạn WIP.

## 14. Tình huống thực hành: luồng đăng ký khóa học

Nhóm quản lý nền tảng học trực tuyến có bảng:

~~~text
Sẵn sàng        Đang phát triển    Review         Kiểm thử       Done
--------------- ------------------ -------------- -------------- --------
Lọc trình độ    Bộ lọc khóa        Lưu yêu thích  Sửa nhãn      4 item/tuần
                Đồng bộ đăng ký *

* Đồng bộ đăng ký đang bị chặn ở bước tích hợp.
~~~

Nhóm có SLE ban đầu **85% item nhỏ Done trong không quá 10 ngày làm việc**. Vào cuối ngày làm việc hiện tại, năm item đang mở có tuổi:

~~~text
Sửa nhãn trình độ:     2 ngày
Lưu yêu thích:         9 ngày
Đồng bộ đăng ký:      12 ngày (Blocked)
Bộ lọc khóa học:       4 ngày
Xác nhận email:        7 ngày
~~~

### 14.1. Chỉ đọc bảng mà không xem tuổi

Người điều phối có thể hỏi: “Ai rảnh để bắt đầu Lọc trình độ?”. Câu hỏi đó chưa nhìn thấy nguy cơ B và C đang tồn lâu.

### 14.2. Đọc bảng cùng Work Item Age và SLE

Nhóm nhận diện:

- **Đồng bộ đăng ký** đã vượt SLE tham khảo và bị chặn; cần có người giải quyết quyền môi trường, thời điểm kiểm tra lại và kế hoạch kiểm thử.
- **Lưu yêu thích** đã chín ngày, đang chờ review; có thể chuyển nguồn lực phù hợp để xử lý hàng chờ.
- **Xác nhận email** đã bảy ngày; cần xem tích hợp còn phụ thuộc hay có nguy cơ già nhanh.
- **Sửa nhãn trình độ** mới hai ngày ở kiểm thử; nếu gần Done, có thể cùng hoàn tất mà không mở thêm WIP.
- **Bộ lọc khóa học** chưa vượt ngưỡng nhưng vẫn cần theo dõi và ưu tiên theo giá trị.

### 14.3. Quyết định trong buổi phối hợp

Nhóm thống nhất thử một ngày:

1. Một người có thể review ưu tiên xử lý **Lưu yêu thích**.
2. Người nắm hệ thống tích hợp và đại diện vận hành tập trung gỡ **Đồng bộ đăng ký**, ghi rõ trở ngại và bước tiếp theo.
3. Thành viên phù hợp giúp kết thúc kiểm thử **Sửa nhãn trình độ**.
4. Tạm thời không kéo thêm **Lọc trình độ** nếu giới hạn WIP đã đạt.
5. Product Owner hoặc người phụ trách ưu tiên được thông báo về rủi ro item đăng ký và các đánh đổi phạm vi khi cần.

**Không hứa tự động “C sẽ xong trước ngày 13”**. Nhóm cần xem điều kiện gỡ nghẽn và khả năng hoàn tất theo chất lượng thực tế.

### 14.4. Kết quả cần nhìn lại

Sau một khoảng thời gian, nhóm hỏi:

- B và C có thật sự đạt Done không, hay chỉ đổi trạng thái?
- Tuổi công việc của các item còn dở có giảm hoặc bớt tích tụ ở vùng cao không?
- Thời gian chờ review, môi trường đã được giảm bằng thay đổi bền vững nào?
- Các item Done có đáp ứng tiêu chí chấp nhận, chất lượng và phản hồi người dùng không?
- Có cần thay đổi giới hạn WIP hoặc chính sách kéo việc?

Việc xem lại không chỉ nhằm “đạt 85%”, mà để **giao kết quả cho người học đáng tin cậy hơn**.

## 15. Dùng trong Scrum và XP như thế nào?

### 15.1. Kanban bổ trợ Scrum

Một Scrum Team có **Sprint Goal**, **Sprint Backlog** và các sự kiện chính thức theo Scrum. Nhóm có thể đưa Work Item Age, Cycle Time và SLE vào việc quan sát Sprint Backlog để phát hiện sớm những item gây nguy cơ không đạt Sprint Goal.

- **Daily Scrum:** Developers xem item già, trở ngại và điều chỉnh kế hoạch hướng Sprint Goal.
- **Sprint Planning:** Dữ liệu luồng giúp đánh giá mức rủi ro khi chọn PBI, nhưng không biến SLE thành lời hứa hoàn tất mọi story.
- **Sprint Review:** Kiểm tra Increment và phản hồi sản phẩm, không chỉ số liệu tốc độ.
- **Sprint Retrospective:** Phân tích hàng chờ, WIP, tuổi item và thử cải tiến dòng công việc.

**SLE và Aging WIP không thay thế Sprint Goal hoặc Definition of Done.** Nếu nhóm dùng Kanban trong Scrum, vẫn phải tôn trọng trách nhiệm, artifacts, commitments và events của Scrum.

### 15.2. Thực hành kỹ thuật XP hỗ trợ giảm tuổi công việc

XP nhấn mạnh kiểm thử tự động, tích hợp liên tục, lập trình cặp, tái cấu trúc mã và giao nhỏ. Các thực hành này có thể giúp công việc không mắc kẹt ở bước kiểm thử hoặc tích hợp quá lâu.

Ví dụ, nếu nhiều item đều già vì pipeline CI thất bại không ổn định, cải thiện pipeline có thể quan trọng hơn việc thúc từng Developer “đẩy nhanh”. Hạng mục tích hợp với nhiều dịch vụ có thể được chia thành lát cắt nhỏ, kiểm chứng sớm hơn.

Những kỹ thuật này **không trực tiếp ấn định một SLE giống nhau cho mọi nhóm**. Nhóm cần kiểm tra tác động thật lên Cycle Time, WIP, lỗi và giá trị.

## 16. Sai lầm phổ biến khi dùng tuổi công việc và SLE

**1. Chỉ theo dõi Cycle Time của item đã Done.** Item khó vẫn nằm trong WIP sẽ bị bỏ khỏi tầm nhìn. Luôn xem Work Item Age.

**2. Dừng đồng hồ khi item bị Blocked để số liệu đẹp.** Người dùng vẫn phải chờ; hãy đo thêm blocked time thay vì giấu thời gian trôi qua.

**3. Coi mốc SLE là hạn chót tuyệt đối cho mọi item.** SLE có yếu tố xác suất/kỳ vọng; thời hạn hợp đồng hoặc an toàn cần chính sách khác.

**4. Nhầm SLE với SLA.** Một kỳ vọng nội bộ không tự tạo ra hoặc xóa bỏ nghĩa vụ dịch vụ chính thức.

**5. Lấy SLE trừ tuổi hiện tại để đo thời gian còn lại.** Đây không phải mô hình thời gian còn lại có điều kiện.

**6. Dùng tuổi như phần trăm hoàn thành.** Item 90% mốc SLE có thể chưa thực hiện được một bước tích hợp quan trọng nào.

**7. Đếm Done trước khi đạt chuẩn chất lượng.** Throughput tăng giả, Cycle Time giảm giả và chất lượng sản phẩm có thể kém đi.

**8. Áp cùng SLE cho mọi loại công việc.** Lỗi nghiêm trọng và thử nghiệm nghiên cứu có ranh giới, độ lớn và cách phục vụ khác nhau.

**9. Dùng mẫu rất nhỏ nhưng công bố xác suất chắc chắn.** Quan sát 17/20 không bảo đảm chính xác 85% tương lai; cần nói rõ mức hạn chế.

**10. Tự ý loại những item già hoặc tuần có sự cố.** Xóa dữ liệu khó chịu khiến dự báo lạc quan giả tạo. Chỉ phân nhóm khi có lý do thật.

**11. Giảm WIP chỉ bằng cách giấu hoặc chuyển nhãn item.** Dòng công việc không cải thiện nếu thời gian chờ thực tế không đổi.

**12. Chỉ tối ưu mốc SLE, bỏ qua giá trị và rủi ro.** Item nhỏ dễ làm có thể được ưu tiên chỉ để đạt chỉ số, trong khi luồng đăng ký cốt lõi vẫn bị chặn.

**13. Gắn màu đỏ cho item già rồi không ai hành động.** Cần nguyên nhân, người hỗ trợ, bước gỡ và kiểm tra kết quả.

**14. Đổ lỗi cá nhân khi item quá tuổi.** Cycle Time/Work Item Age đo hiệu quả luồng công việc liên chức năng, gồm các hàng chờ và phụ thuộc.

**15. Coi xu hướng tốt của một tuần là cải tiến bền vững.** Xem nhiều kỳ, loại công việc, các item chưa Done và chất lượng trước khi kết luận.

## 17. Bài tập tự kiểm tra với dữ liệu minh họa

Một nhóm có 20 Cycle Time theo ngày làm việc:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

Hiện có năm item còn dở:

| Item | Work Item Age | Vấn đề |
| --- | ---: | --- |
| A | 3 | Đang thực hiện, không có blocker |
| B | 8 | Review chưa có người xử lý |
| C | 11 | Đang chờ môi trường tích hợp |
| D | 5 | Đang kiểm thử |
| E | 14 | Cần quyết định quyền truy cập dữ liệu |

Nhóm đang cân nhắc SLE **85% trong 10 ngày làm việc** cho loại công việc tương đồng.

### Câu hỏi

1. Theo phương pháp **nearest-rank**, P85 và P95 của tập Cycle Time là bao nhiêu?
2. Có bao nhiêu trong 20 item lịch sử hoàn tất trong không quá 10 ngày? Tỷ lệ quan sát là bao nhiêu?
3. Item nào hiện đã vượt mốc 10 ngày? Item nào nên được chú ý sớm dù chưa vượt?
4. Có thể kết luận item E còn \(18-14=4\) ngày vì 18 là Cycle Time dài nhất lịch sử không?
5. Nhóm nên làm gì với B, C và E để giảm nguy cơ công việc tiếp tục già đi?
6. Nếu tháng tới có 18 item Done, trong đó 15 item không quá 10 ngày, tỷ lệ quan sát là bao nhiêu? Có đủ căn cứ tuyên bố nhóm thất bại không?
7. Trong Sprint của Scrum, thông tin tuổi item nên được dùng vào đâu?

### Gợi ý lời giải

**Câu 1:** Với 20 quan sát, vị trí P85 là \(\lceil0{,}85\times20\rceil=17\), giá trị thứ 17 bằng **10 ngày**. Vị trí P95 là \(\lceil0{,}95\times20\rceil=19\), giá trị thứ 19 bằng **13 ngày**.

**Câu 2:** Có **17/20** item lịch sử hoàn tất trong ≤ 10 ngày, tương đương **85%** trong chính mẫu đã cho. Đây là tỷ lệ quá khứ, không phải bảo đảm tuyệt đối tương lai.

**Câu 3:** C (11 ngày) và E (14 ngày) **đã vượt mốc SLE**. B (8 ngày) đang chờ review, nên được chú ý sớm vì có nguy cơ tăng tuổi mà chưa tạo ra giá trị hoàn tất.

**Câu 4:** Không. Item E đã 14 ngày và chưa Done; mẫu dài nhất 18 ngày **không tạo giới hạn trên chắc chắn**. Hơn nữa, thời gian còn lại có điều kiện item đã tồn tại lâu cần dữ liệu và mô hình phù hợp, cùng đánh giá nguyên nhân thực tế.

**Câu 5:** Chuyển người có kỹ năng phù hợp ưu tiên review B; hỗ trợ gỡ môi trường cho C; xác định ai có quyền quyết định về dữ liệu cho E, trình bày tác động và thời điểm phản hồi cần thiết. Cập nhật bảng và tránh mở quá nhiều WIP mới; vẫn giữ chất lượng.

**Câu 6:** Tỷ lệ là \(15/18\times100\%\approx83{,}3\%\). Nó thấp hơn 85% nhưng chỉ một tập nhỏ không đủ để kết luận thất bại hệ thống. Cần xem phân bố, dữ liệu WIP, loại item và thay đổi điều kiện.

**Câu 7:** Developers có thể dùng tuổi item trong Daily Scrum để kiểm tra nguy cơ với Sprint Goal, cùng điều chỉnh Sprint Backlog và hỗ trợ gỡ nghẽn. Nó không thay Sprint Goal, acceptance criteria hay Definition of Done.

### Bài tập mở rộng: thiết kế chính sách xử lý

Hãy viết một **working agreement ngắn** cho nhóm của bạn:

> “Mỗi ngày làm việc, chúng tôi xem các item đang Blocked, các item già nhất và item tiệm cận SLE theo cùng ranh giới đo. Khi thấy rủi ro, nhóm ghi nguyên nhân, tác động, người hỗ trợ và bước tiếp theo. Chúng tôi ưu tiên giúp item đạt Done trước khi kéo thêm việc nếu WIP bị nghẽn. Các trường hợp khẩn cấp và nghĩa vụ pháp lý được xử lý theo chính sách có thẩm quyền; không bỏ kiểm thử để chạy theo chỉ số. Mức SLE được xem lại định kỳ bằng cả cycle time lịch sử và tuổi item còn dở.”

Sau một hoặc hai kỳ xem lại, nhóm có thể đánh giá thỏa thuận có giảm chờ đợi, tăng tính minh bạch và giúp người dùng nhận giá trị sớm hơn không.

## 18. Checklist áp dụng Work Item Age và SLE

Trước khi đưa SLE vào bảng hoặc báo cáo:

1. **Đúng workflow:** Mốc bắt đầu, mốc Done và các trạng thái nằm giữa đã được định nghĩa và nhất quán chưa?
2. **Đơn vị thời gian:** Dùng giờ, ngày làm việc hay ngày lịch? Quy tắc đếm có rõ không?
3. **Nhóm item:** Các hạng mục đem so sánh có tương đồng về loại công việc và cách hoàn tất không?
4. **Dữ liệu lịch sử:** Đã đủ và đại diện chưa? Có sự cố, item ngoại lệ hoặc thay đổi cách chia story cần giải thích không?
5. **Cách tính phân vị:** Có công bố phương pháp tính, cỡ mẫu và mức hạn chế của con số SLE không?
6. **Cách phát biểu:** SLE có cả mốc thời gian và mức xác suất/kỳ vọng, không bị viết thành hạn chót chắc chắn?

Trong vận hành hằng ngày:

7. **Tuổi item đang dở:** Có xem Work Item Age của *tất cả* công việc đã bắt đầu, kể cả Blocked không?
8. **Hàng chờ:** Item già nằm tại bước nào và có ai giúp hoàn tất được không?
9. **Hành động:** Với item nguy cơ cao, đã có nguyên nhân, người phối hợp và bước tiếp theo rõ chưa?
10. **WIP:** Nhóm có ưu tiên hoàn tất công việc trước khi mở nhiều việc mới không?
11. **Ưu tiên:** Có phân biệt tuổi cao với sự cố thật sự khẩn cấp và các ràng buộc bắt buộc không?
12. **Chất lượng:** Item Done có thực sự đáp ứng tiêu chí chấp nhận và chuẩn chất lượng áp dụng không?

Khi cải tiến:

13. **Xem đầy đủ:** Có phân tích cycle time, throughput, WIP và work item age cùng nhau không?
14. **Tránh số liệu giả:** Có nhận diện việc đếm trùng, giấu blocked time hoặc thay đổi nghĩa Done không?
15. **Thông báo:** Bên liên quan có hiểu SLE là kỳ vọng theo dữ liệu, không phải SLA hay lời hứa chắc chắn?
16. **Cải tiến thực:** Chính sách mới có giảm hàng chờ, lỗi và độ bất định cho người dùng hay chỉ làm biểu đồ đẹp hơn?

**Ghi nhớ:** **Work Item Age** trả lời “công việc đang làm đã già bao lâu?”, còn **Service Level Expectation** cho biết “với loại công việc và ranh giới này, thời gian hoàn tất được kỳ vọng ra sao theo một mức xác suất đã nêu?”. Kết hợp hai góc nhìn giúp nhóm Kanban phát hiện item có nguy cơ trễ sớm, ưu tiên gỡ nghẽn và điều chỉnh cách phối hợp trước khi chờ dữ liệu Done. SLE không bảo đảm thời hạn cho một item riêng, cũng không thay thế chất lượng hay nghĩa vụ dịch vụ bên ngoài. Dùng chúng như **công cụ học hỏi và quyết định về dòng giá trị**, nhóm sẽ có cơ sở giao phần tăng dần đáng tin cậy hơn và cải tiến liên tục.
