# Nhóm phân tán: Kết hợp giao tiếp đồng bộ với trao đổi bất đồng bộ

Một Scrum Team phát triển nền tảng đăng ký workshop có Developers tại Việt Nam, một chuyên gia kiểm thử ở châu Âu và người phụ trách tích hợp ở Bắc Mỹ. Cả nhóm làm việc chăm chỉ nhưng một thay đổi nhỏ về trạng thái “Đang chờ xác nhận” mất ba ngày chỉ để làm rõ: gửi tin nhắn rồi chờ người khác thức dậy, mở cuộc họp có người phải tham gia lúc nửa đêm, sau họp không ai ghi quyết định. Ngày kế tiếp, hai người sửa cùng một chỗ theo hai cách hiểu khác nhau. Họp nhiều hơn có chắc giải quyết được không? Chuyển tất cả sang tin nhắn bất đồng bộ có tốt hơn không?

**Câu trả lời là kết hợp hai cách giao tiếp theo mục đích.** Giao tiếp **đồng bộ** (*synchronous communication*) giúp những người liên quan tương tác gần như cùng lúc để giải quyết điểm mơ hồ, xử lý xung đột, thảo luận vấn đề phức tạp hoặc ứng phó sự cố cần phối hợp tức thời. Trao đổi **bất đồng bộ** (*asynchronous communication*) cho phép người nhận đọc, suy nghĩ và phản hồi vào thời điểm phù hợp với ca làm việc, đồng thời tạo dấu vết để nhóm tiếp nối công việc qua múi giờ.

Khi sử dụng tốt, hai cách này không đối lập: **chuẩn bị và chia sẻ bối cảnh bất đồng bộ → gặp nhau đồng bộ khi cần → ghi lại quyết định và hành động bất đồng bộ**. Mục tiêu không phải loại bỏ cuộc họp, cũng không phải bắt ai luôn trực tuyến, mà là **giảm thời gian chờ vô ích và chi phí chuyển ngữ cảnh trong khi giữ phản hồi, chất lượng và khả năng cộng tác**.

Bài thuộc mô-đun **AGILE_DEVELOPMENT**: thực hành giá trị, nguyên tắc Agile, giao phần mềm tăng dần qua phản hồi sớm, phối hợp bằng user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Chủ đề trực tiếp là **kết hợp giao tiếp đồng bộ với trao đổi bất đồng bộ trong nhóm phân tán**. Những quy tắc thời gian, kênh và vai trò trong ví dụ là **đề xuất minh họa**, không phải tiêu chuẩn bắt buộc cho mọi tổ chức; cần điều chỉnh theo mục tiêu, văn hóa, pháp luật, tính sẵn sàng và điều kiện tiếp cận của từng thành viên.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt giao tiếp **đồng bộ**, **bất đồng bộ**, thông báo trạng thái và hoạt động cộng tác thực chất.
2. Chọn phương thức dựa trên **mức khẩn, độ mơ hồ, mức phụ thuộc, tác động quyết định và nhu cầu phản hồi** thay vì sở thích công cụ.
3. Thiết kế **working agreement** cho múi giờ, giờ làm việc, thời hạn phản hồi, kênh trao đổi, quy tắc chuyển sang họp và cơ chế leo thang.
4. Viết yêu cầu bất đồng bộ có đủ **bối cảnh, câu hỏi, người quyết định, thời điểm cần phản hồi và đường dẫn bằng chứng**.
5. Điều hành một phiên đồng bộ ngắn có mục tiêu, chuẩn bị trước, kết luận rõ và không làm mất thông tin của người vắng mặt.
6. Xây quy trình **handoff** giữa các múi giờ mà không buộc mọi người làm việc 24/7 hoặc phải chờ cá nhân “người hùng”.
7. Vận dụng cách phối hợp vào **Scrum events, Product Backlog, Sprint Goal, Kanban flow, code review, pairing, CI và xử lý sự cố**.
8. Phân biệt **acknowledgment (đã nhận)** với **resolution (đã giải quyết)** để tránh suy đoán từ tín hiệu trực tuyến.
9. Đo độ trễ phụ thuộc, tuổi item bị chặn, thời gian hoàn tất và giá trị người dùng mà không giám sát vi mô cá nhân.
10. Phân tích tình huống nhóm trải ba múi giờ, thiết kế lịch trao đổi, ví dụ thông điệp, quyết định và kế hoạch cải tiến.

## 2. Hai chế độ giao tiếp và những điều dễ hiểu nhầm

### 2.1. Đồng bộ là tương tác cùng thời điểm

Các hình thức thường gặp:
- Trao đổi trực tiếp hoặc cuộc gọi âm thanh/video.
- Pair programming hoặc ensemble programming theo thời gian thực.
- Workshop làm rõ phạm vi, thiết kế API hoặc giải quyết bất đồng.
- Các sự kiện Scrum khi nhóm cùng kiểm tra và thích ứng.
- Họp điều phối sự cố production.

**Đồng bộ không nhất thiết là video.** Có thể dùng âm thanh, chat trực tiếp trong một khung thời gian, bảng cộng tác hoặc chia sẻ màn hình. Điều quan trọng là **các bên sẵn sàng phản hồi ngay cho nhau**, giảm số vòng hỏi–đáp nối tiếp khi vấn đề cần thương lượng.

### 2.2. Bất đồng bộ là trao đổi không yêu cầu phản hồi tức thì

Các hình thức thường gặp:
- Tài liệu thiết kế, RFC/ADR và nhận xét có lịch sử.
- Product Backlog item có acceptance criteria, ví dụ nghiệp vụ.
- Pull request/code review và phản hồi kỹ thuật.
- Issue, ticket, bảng Kanban, changelog và status page nội bộ.
- Tin nhắn chứa câu hỏi rõ, bối cảnh, thời điểm cần câu trả lời.
- Bản ghi quyết định, runbook, video demo kèm mô tả hoặc phụ đề khi phù hợp.

**Bất đồng bộ không có nghĩa chỉ gửi một đoạn chat rồi không ai chịu trách nhiệm.** Để có hiệu quả, thông điệp phải dễ tìm, có người nhận/phản hồi, thời hạn hợp lý, bối cảnh cần thiết và cách nhận biết kết quả.

### 2.3. Không phải mọi “tin nhắn” đều là bất đồng bộ

Một nhóm có thể sử dụng công cụ chat nhưng mong người khác trả lời trong 30 giây, bất kể giờ làm việc. Khi đó chat đang bị sử dụng như **giao tiếp đồng bộ không hẹn trước**. Cách này làm việc sâu bị ngắt liên tục và khiến thành viên khác múi giờ cảm thấy phải luôn online.

Ngược lại, một tài liệu được mọi người cùng chỉnh trong một workshop có thể là **cộng tác đồng bộ trên công cụ vốn hỗ trợ bất đồng bộ**. Đừng chọn cách làm chỉ theo tên ứng dụng.

### 2.4. So sánh các tính chất

| Khía cạnh | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| **Vòng hỏi–đáp** | Nhanh khi mọi người cùng có mặt | Có thể kéo dài qua một hoặc nhiều ngày làm việc |
| **Chi phí phối lịch** | Cao hơn khi phân tán múi giờ | Thường thấp hơn |
| **Khả năng xử lý mơ hồ** | Hữu ích khi cần giải thích, thương lượng liên tục | Tốt khi câu hỏi đủ rõ hoặc người nhận cần nghiên cứu |
| **Tập trung sâu** | Có thể gây ngắt quãng nếu quá nhiều cuộc họp | Cho phép chọn thời điểm phản hồi khi có working agreement |
| **Dấu vết quyết định** | Dễ mất nếu không ghi lại | Thường thuận lợi hơn nếu dùng nơi có lịch sử |
| **Tính bao trùm** | Bất lợi nếu giờ họp nằm ngoài ca của ai đó | Hỗ trợ nhiều múi giờ, nhưng cần chú ý khả năng đọc/viết và tiếp cận |
| **Ứng phó khẩn cấp** | Phù hợp khi cần điều phối ngay | Cần kênh cảnh báo/leo thang riêng khi hậu quả lớn |
| **Rủi ro** | Họp dài, thiếu chuẩn bị, người vắng mặt không biết quyết định | Chờ lâu, hiểu nhầm, lạc chủ đề, im lặng bị coi là đồng ý |

Hai cột đều có ưu và nhược điểm. **Cách làm tốt thường là phối hợp chứ không cực đoan chọn một.**

## 3. Chọn đồng bộ hay bất đồng bộ dựa trên tính chất vấn đề

### 3.1. Năm câu hỏi trước khi chọn kênh

1. **Mức khẩn:** Nếu chờ đến ngày làm việc tiếp theo, có gây thiệt hại hoặc chặn mục tiêu quan trọng không?
2. **Độ mơ hồ:** Câu hỏi đã đủ rõ để trả lời sau khi đọc, hay cần hỏi–đáp nhiều vòng?
3. **Số phụ thuộc:** Có bao nhiêu người/hệ thống cần đồng thời thống nhất một hợp đồng?
4. **Độ khó đảo ngược:** Quyết định có ảnh hưởng dữ liệu, bảo mật, khách hàng hoặc kiến trúc khó đổi không?
5. **Nhu cầu dấu vết:** Người khác phải tra được lý do, quyết định và tác động sau vài tuần không?

Một quyết định khó đảo ngược thường **cần cả trao đổi trực tiếp lẫn hồ sơ bền vững**. Một câu hỏi dễ, không khẩn thường **nên bắt đầu bất đồng bộ**.

### 3.2. Bảng lựa chọn thực hành

| Tình huống | Khởi đầu đề xuất | Khi nào chuyển chế độ |
| --- | --- | --- |
| Cập nhật tiến độ thường kỳ, không có blocker | **Async:** cập nhật bảng công việc và kết quả | Nếu có lệch mục tiêu cần điều chỉnh trực tiếp |
| Hỏi quy tắc nghiệp vụ đã có tài liệu | **Async:** dẫn link, hỏi một câu cụ thể | Sau vài vòng vẫn có cách hiểu khác nhau |
| Review một pull request nhỏ | **Async:** bình luận trên diff, test | Nếu review tranh luận dài hoặc block nghiêm trọng |
| Thiết kế contract giữa hai nhóm | **Async trước:** proposal và phương án | **Sync ngắn** để giải quyết các điểm chưa thống nhất, rồi ghi quyết định |
| Tìm lỗi pipeline ảnh hưởng nhiều người | Async cập nhật và điều phối theo mức khẩn | **Sync** khi cần cùng chẩn đoán nhanh để khôi phục luồng |
| Sự cố production gây mất dữ liệu | **Sync/incident channel ngay** theo quy trình trực | Sau xử lý: biên bản, timeline, quyết định async |
| Phản hồi của stakeholder về Increment | Có thể chia tài liệu/demo trước | **Sync** để kiểm tra nhận thức và cùng thích ứng khi thích hợp |
| Góp ý nhỏ về tên biến và style | **Async:** PR comment có ví dụ | Hiếm khi cần họp |
| Mâu thuẫn kéo dài giữa hai cách hiểu | Đăng tài liệu làm rõ hai lập luận | **Sync** với đúng người có quyền quyết, ghi kết luận |
| Chuyển giao công việc cuối ca | **Async:** handoff có trạng thái và next steps | **Sync** nếu lỗi đang diễn biến và nhận bàn giao cần xác nhận tức thì |

### 3.3. Sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A[Cần trao đổi một vấn đề] --> B{Đang gây sự cố nghiêm trọng hay cần hành động tức thì?}
    B -->|Có| C[Kênh khẩn / sync theo on-call và quyền quyết định]
    B -->|Không| D{Câu hỏi đã rõ và có thể tự nghiên cứu?}
    D -->|Có| E[Async: nguồn bối cảnh, câu hỏi, owner, deadline]
    D -->|Không| F[Async: tài liệu vấn đề và các lựa chọn trước]
    F --> G{Cần nhiều vòng tranh luận hay thống nhất trực tiếp?}
    G -->|Có| H[Sync ngắn với đúng người và agenda]
    G -->|Không| E
    H --> I[Ghi quyết định, rationale, owner, việc tiếp theo]
    E --> J{Đến mốc mà vẫn blocked hoặc thiếu đồng thuận?}
    J -->|Có| H
    J -->|Không| K[Cập nhật nguồn sự thật chung]
    C --> I
    I --> K
~~~

Sơ đồ không yêu cầu **mọi** vấn đề đi qua cả hai chế độ. Khi hành động đã rõ và không khẩn, tránh mở họp chỉ để đọc nội dung người khác có thể xem trước.

### 3.4. Quy tắc chuyển từ async sang sync

Một working agreement có thể định nghĩa điều kiện **escalate sang huddle 15–30 phút** khi:
- Có **hai hoặc ba vòng hỏi–đáp** vẫn không rõ điều đang quyết định.
- Hai phương án hợp lý có đánh đổi quan trọng, không thể chọn chỉ qua nhận xét rời rạc.
- Work item đang bị chặn và **nguy cơ không đạt Sprint Goal** tăng.
- Sự khác biệt về ngôn ngữ, quy tắc hoặc dữ liệu cần cùng nhìn một ví dụ.
- Cần ra quyết định trước một mốc mà chờ thêm sẽ làm mất lựa chọn.
- Có dấu hiệu hiểu sai gây hậu quả an toàn, bảo mật hoặc dữ liệu.

**Ngưỡng hai hoặc ba vòng chỉ là ví dụ**, không phải quy định Agile. Nếu một vấn đề nghiêm trọng cần gặp ngay thì không đợi đủ số vòng; nếu cả hai bên đang nghiên cứu độc lập và việc chưa khẩn, có thể tiếp tục async.

## 4. Hiểu đúng chi phí: số giờ họp và độ trễ chờ

### 4.1. Đồng bộ có chi phí phối hợp

Một cuộc họp có **8 người trong 45 phút** sử dụng **8 × 45 phút = 360 phút = 6 person-hours** thời gian tham gia, chưa tính chuẩn bị, ngắt mạch công việc và ghi chép. Cuộc họp đó có thể vẫn **rất đáng giá** nếu giải quyết được quyết định lớn hoặc ngăn vài ngày làm lại.

**Không nên kết luận “6 giờ bị lãng phí” chỉ dựa phép nhân.** Cần đánh giá kết quả và chi phí của phương án thay thế.

### 4.2. Bất đồng bộ có chi phí chờ

Giả sử một yêu cầu có ba bước phụ thuộc liên tiếp:

~~~text
Hỏi A -> chờ phản hồi A -> hỏi B -> chờ phản hồi B -> hỏi C
~~~

Nếu mỗi người chỉ đọc vào ngày làm việc tiếp theo, một vấn đề thực chất cần 20 phút có thể bị kéo qua **nhiều ngày lịch**. Cách cải thiện:
- Nêu đủ giả định, ví dụ và phương án ngay trong câu hỏi đầu tiên.
- Gửi đồng thời những câu hỏi **độc lập** thay vì chờ nối tiếp không cần thiết.
- Chỉ định người quyết định/đầu mối trả lời.
- Chuyển sang sync khi nhiều vòng hỏi–đáp trở thành nút thắt.
- Tránh chuyển một yêu cầu cần quyết ngay thành “nhắn rồi hy vọng”.

### 4.3. Công thức tư duy

~~~text
Tổng chi phí cộng tác cần cân nhắc:
    Thời gian trực tiếp trao đổi
  + Thời gian chuẩn bị, ghi lại kết quả
  + Thời gian chờ phụ thuộc
  + Chi phí chuyển ngữ cảnh và làm lại
  + Rủi ro do quyết định sai hoặc quá muộn
~~~

Đây là **khung ra quyết định**, không phải công thức kinh tế đã được đo chuẩn. Cách kết hợp tốt là cách làm cho **dòng công việc tiến lên với chất lượng và sức làm việc bền vững**, không chỉ cách có số cuộc họp ít nhất.

## 5. Working agreement: thống nhất kênh, thời gian và kỳ vọng

### 5.1. Quy tắc cần viết ra

Một working agreement của nhóm phân tán nên trả lời:

- Nhóm có **nguồn sự thật chung** nào cho Product Goal, Sprint Goal, backlog, công việc đang làm, quyết định và rủi ro?
- Những **kênh** nào dành cho thông báo thường lệ, code review, câu hỏi, quyết định, sự cố?
- Khoảng thời gian **mỗi người thường làm việc** và các cửa sổ chồng giờ nào thật sự có?
- **Kỳ vọng phản hồi** cho tin thường, việc blocked, incident là gì?
- Ai là **người điều phối/ra quyết định**, ai phải được tham vấn?
- Khi nào chuyển từ async sang sync, ai chủ động đặt lịch và chuẩn bị agenda?
- Nếu người cần trả lời vắng mặt hoặc nghỉ phép thì **người thay thế** là ai?
- Sau cuộc họp, ai ghi **decision log và action items**?
- Một quyết định quan trọng bị phản đối hoặc phát hiện sai thì **được xem lại thế nào**?
- Cách tôn trọng **ngày nghỉ, giờ ngoài ca, sức khỏe và quyền riêng tư**?

Thỏa thuận nên ngắn và có thể kiểm chứng trong vận hành. **Không xây quy trình nhiều trang khiến người mới phải đọc cả giờ chỉ để gửi một câu hỏi.**

### 5.2. Ví dụ kênh và kỳ vọng phản hồi

| Loại trao đổi | Kênh phù hợp | Kỳ vọng minh họa | Quy tắc khi không nhận được |
| --- | --- | --- | --- |
| Cập nhật thường lệ | Bảng công việc, tài liệu chung | Trước mốc đồng bộ của ngày làm việc kế tiếp | Kiểm tra lại ở nhịp nhóm |
| Câu hỏi nghiệp vụ không chặn | Comment trên PBI/RFC | Trong 1–2 **ngày làm việc của người nhận** | Nhắc ở nơi có lịch sử, đổi người tham vấn nếu cần |
| PR chờ review | PR với checklist và owner review | Có phản hồi đầu tiên trong một khoảng làm việc đã thống nhất | Đưa vào hàng chờ ưu tiên, pairing nếu blocked |
| Blocker đe dọa Sprint Goal | Item đánh dấu blocked + nhắn người phụ trách | Xác nhận tiếp nhận trong khung giờ đã thống nhất | Chủ động escalation hoặc huddle ngắn |
| Quyết định nhiều nhóm | Proposal có hạn và owner | Trước mốc cần quyết, có đường dẫn bằng chứng | Huddle với người có quyền quyết |
| Sự cố production nghiêm trọng | Kênh on-call/incident chuyên dụng | Theo quy trình trực và mức nghiêm trọng | Escalation tự động/backup theo runbook |

**Các con số trên không phải SLA áp dụng sẵn.** Một nhóm phải tự chọn kỳ vọng hợp lý với giờ làm việc, số lượng người, loại dịch vụ và ràng buộc vận hành. Không mặc định người khác phải phản hồi ngày nghỉ hoặc lúc đang ngủ.

### 5.3. Phân biệt các mốc phản hồi

- **Acknowledged:** “Tôi đã thấy yêu cầu, sẽ xem trong ca tiếp theo.”
- **Clarification requested:** còn câu hỏi thiếu dữ kiện, có người đang thu thập.
- **Decision made:** lựa chọn và lý do đã được người có quyền xác nhận.
- **Action completed:** mã/test/tài liệu đã thay đổi theo quyết định.
- **Verified:** kết quả đã được kiểm chứng theo DoD hoặc tiêu chí liên quan.

Một biểu tượng “đã xem” hoặc emoji không đồng nghĩa người nhận **đồng ý, đã giải quyết hoặc đã bảo đảm thời hạn**.

### 5.4. Không dùng sự im lặng làm đồng thuận mặc định

Nếu proposal được gửi hôm nay và không ai trả lời, không thể tự động nói “cả nhóm đã nhất trí” trừ khi nhóm đã **thống nhất rõ cơ chế ra quyết định cho loại việc rủi ro thấp**, danh sách người cần phản hồi và điều kiện hợp lệ.

Đối với thay đổi liên quan quyền dữ liệu, hợp đồng bên ngoài, bảo mật hoặc schema khó đảo ngược, **im lặng không thể thay thế xác nhận của người có thẩm quyền**.

## 6. Múi giờ, cửa sổ chồng giờ và sự công bằng

### 6.1. Hiển thị cả múi giờ lẫn giờ địa phương

Một lịch “họp lúc 9:00” là không đủ khi có thành viên ở nhiều quốc gia. Cần ghi:
- Múi giờ chuẩn, tốt nhất bằng **múi giờ khu vực** trong lịch (ví dụ Asia/Ho_Chi_Minh, Europe/Warsaw, America/New_York).
- Ngày và giờ của từng người trong ứng dụng lịch.
- Điều kiện đổi giờ mùa hè (*daylight saving time – DST*) ở khu vực áp dụng.
- Những thành viên không thể tham dự và cách tham gia sau qua tài liệu.

Việt Nam không đổi giờ mùa hè, nhưng một số nước châu Âu và Bắc Mỹ **có thể đổi offset trong năm** và ngày đổi không trùng nhau. Vì vậy đừng duy trì lịch “UTC+1 mãi mãi” nếu thực tế người đó dùng Europe/Warsaw.

### 6.2. Ví dụ ba khu vực không có giờ chung lý tưởng

Giả sử vào một ngày mùa đông thông thường:
- Thành viên ở Việt Nam đang theo **UTC+7**.
- Thành viên ở Warsaw theo **UTC+1** vào mùa đông.
- Thành viên ở New York theo **UTC−5** vào mùa đông.

Một số mốc cùng thời điểm để minh họa:

| Mốc UTC | Việt Nam | Warsaw (mùa đông) | New York (mùa đông) |
| --- | --- | --- | --- |
| 08:00 UTC | 15:00 cùng ngày | 09:00 cùng ngày | 03:00 cùng ngày |
| 12:00 UTC | 19:00 cùng ngày | 13:00 cùng ngày | 07:00 cùng ngày |
| 16:00 UTC | 23:00 cùng ngày | 17:00 cùng ngày | 11:00 cùng ngày |

Nếu buộc cả ba khu vực họp mỗi ngày vào một mốc, **ít nhất một nhóm dễ phải tham gia ngoài giờ thuận tiện**. Phương án phù hợp hơn có thể là:
- **Gặp theo cặp khu vực khi cần:** Việt Nam–Warsaw trong khung thuận tiện; Warsaw–New York trong khung khác.
- **Bất đồng bộ hóa phần chuyển tiếp:** ghi cùng một tài liệu quyết định và handoff, không bắt một người dự cả hai cuộc mỗi ngày.
- **Chỉ họp toàn nhóm khi thực sự cần**, luân phiên khung giờ và phân bổ bất tiện công bằng.
- **Cho phép phản hồi sau** bằng nhận xét, tài liệu tóm tắt, bản ghi khi được phép và có sự đồng ý phù hợp.
- **Không hy sinh nhịp nghỉ ngơi dài hạn** để tạo cảm giác mọi người luôn sẵn sàng.

Các giờ là minh họa theo offset mùa đông, không phải lịch làm việc cố định hay xác nhận về một ngày cụ thể.

### 6.3. Công bằng không nhất thiết là mọi người chịu bất tiện giống hệt nhau

Luân phiên khung giờ là một cách chia sẻ chi phí, nhưng cần tính:
- Giờ chăm sóc gia đình hoặc trách nhiệm cá nhân.
- Khả năng tiếp cận, sức khỏe và thời gian nghỉ.
- Những ngày nghỉ quốc gia, lịch trực và ca làm việc.
- Định mức làm việc đã thỏa thuận.
- Vai trò ai thực sự cần có mặt trực tiếp.

Một cuộc họp đặt vào 23:00 của một người **không tự trở thành hợp lý chỉ vì tuần trước người khác đã chịu bất tiện**. Cần hỏi ý kiến, ưu tiên async nếu có thể và tránh tạo lịch họp đêm lặp lại.

### 6.4. Thực hành lịch bền vững

1. Cập nhật giờ làm việc và ngày nghỉ dự kiến trong lịch nhóm.
2. Đánh dấu khoảng chồng giờ **có thật**, không đoán từ quốc gia.
3. Đặt những cuộc họp cần nhiều người vào giờ hợp lý nhất có thể.
4. Gửi pre-read và lựa chọn phản hồi bất đồng bộ cho người vắng mặt.
5. Ghi kết quả bằng văn bản tại nguồn sự thật chung.
6. Đánh giá lại khi đổi DST, thêm thành viên hoặc xuất hiện mệt mỏi do họp.
7. Với sự cố, dùng **on-call roster có trách nhiệm** thay vì mong cả nhóm 24/7.

## 7. Viết thông điệp bất đồng bộ để người khác trả lời được

### 7.1. Vì sao câu hỏi mơ hồ tạo thêm một vòng chờ?

Ví dụ một câu hỏi yếu:

> “Mọi người xem giúp màn hình trạng thái nhé, có vẻ sai.”

Người nhận phải hỏi lại: màn hình nào, có lỗi gì, dữ liệu gì, cần làm gì, có gấp không, ai quyết? Với chênh múi giờ, **mỗi câu hỏi thiếu có thể cộng thêm một chu kỳ chờ**.

### 7.2. Một thông điệp có thể hành động

Thông điệp tốt có các thành phần:

1. **Bối cảnh:** Product Goal, story, PR/issue và trạng thái hiện tại.
2. **Quan sát:** điều gì đã xảy ra hoặc dữ kiện nào đang có.
3. **Quyết định/câu hỏi:** cần người nhận trả lời điều gì cụ thể.
4. **Phương án và đánh đổi:** đề xuất một lựa chọn hoặc nêu các hướng.
5. **Mức ảnh hưởng:** công việc nào đang blocked, rủi ro nếu chậm.
6. **Người chịu trách nhiệm:** ai quyết và ai hỗ trợ.
7. **Thời hạn hợp lý:** ngày/giờ kèm múi giờ và cách hiểu theo ca làm việc.
8. **Cách leo thang:** nếu còn mơ hồ hoặc quá hạn thì chuyển sang huddle/đầu mối nào.
9. **Nguồn hồ sơ:** nơi ghi quyết định để người không tham dự vẫn theo được.

### 7.3. Ví dụ yêu cầu làm rõ user story

~~~text
Chủ đề: [WS-18][Cần quyết trước refinement thứ Năm]
          Khi workshop đầy, PENDING được hiển thị ra sao?

Bối cảnh:
Story WS-18 cải thiện trạng thái đăng ký để học viên
không hiểu nhầm "Đã nhận yêu cầu" = "Đã xác nhận chỗ".

Bằng chứng:
- API hiện có PENDING, CONFIRMED và REJECTED.
- Bài thử nghiệm nhỏ cho thấy nhãn cũ gây hiểu nhầm.
- PR và ví dụ giao diện: [link vào tài liệu/PR].

Câu hỏi cần Product Owner quyết:
Khi workshop đã đầy nhưng yêu cầu vẫn đang chờ xem xét,
UI sẽ dùng nhãn nào và có cho người dùng rút yêu cầu không?

Đề xuất:
A. "Đang chờ xác nhận" + giải thích chưa được giữ chỗ.
B. Từ chối ngay mọi yêu cầu mới khi đã đầy.

Rủi ro:
Nếu chưa thống nhất, kiểm thử acceptance không thể chốt.
Không được hiển thị PENDING thành CONFIRMED.

Mốc cần phản hồi:
Trước 15:00 giờ Việt Nam thứ Năm (ghi ngày cụ thể trên ticket).
Nếu cần thảo luận, đề xuất huddle 20 phút trong khung chồng giờ.

Owner:
PO quyết hành vi; Developers kiểm dữ liệu và điều kiện hiển thị.
Kết luận sẽ được ghi vào WS-18, không chỉ trong chat.
~~~

Đây là **tình huống giả định**, không có link, dữ liệu hay ngày thật. Cách viết này giúp người nhận hiểu vấn đề và **có thể phản hồi mà không phải đặt câu hỏi từ đầu**.

### 7.4. Đưa thông tin dài ra khỏi chat khi cần

Với một vấn đề nhiều giả định, nên tạo **một tài liệu hoặc issue có lịch sử** rồi gửi liên kết và câu hỏi trong chat. Không đưa toàn bộ 50 tin nhắn rời rạc thành “nguồn sự thật”.

Tin chat nên dẫn đến tài liệu bền vững cho:
- Quyết định về nghiệp vụ và acceptance criteria.
- Hợp đồng API hoặc event.
- Quyết định kiến trúc có ảnh hưởng lâu dài.
- Kết quả spike/experiment.
- Hành động cần theo dõi và mốc kiểm tra.

### 7.5. Trả lời có cấu trúc

Một phản hồi async hữu ích không chỉ “OK”:

~~~text
Tôi đã kiểm tra đề xuất WS-18.
Tôi đồng ý với A theo điều kiện:
- PENDING không hàm ý đã được giữ chỗ.
- Nhãn giải thích phải hiển thị trên mobile.
- Acceptance test cần bao gồm trường hợp workshop vừa hết chỗ.

Lý do: đây là ràng buộc giúp người dùng hiểu đúng trạng thái.
Người cập nhật AC: PO.
Người làm test: Developers.
Mốc xem lại: khi có kết quả dùng thử giao diện.
~~~

Nếu chưa đủ thông tin, nêu **điều gì thiếu và bao giờ có thể trả lời**; không im lặng hoặc gửi “để xem” vô thời hạn.

## 8. Tổ chức phiên đồng bộ nhỏ nhưng có kết quả

### 8.1. Mỗi cuộc họp nên có một mục tiêu ra quyết định

Trước cuộc họp cần xác định:
- **Tại sao không giải quyết được async?**
- Đến cuối cuộc họp cần **quyết định, thống nhất hoặc phát hiện** điều gì?
- Những người nào **bắt buộc** phải có mặt để giải quyết? Ai chỉ cần kết quả?
- Tài liệu nào người tham gia cần đọc trước?
- Có thể giảm còn **15–30 phút** và có người điều phối không?
- Ai chịu trách nhiệm tóm tắt để người vắng mặt không mất thông tin?

Một cuộc họp chỉ để báo lần lượt “hôm qua tôi làm gì” khi bảng công việc đã cập nhật đầy đủ thường không khai thác tốt ưu điểm của tương tác trực tiếp. Trong Scrum, Daily Scrum có mục đích riêng sẽ được trình bày ở phần sau.

### 8.2. Một agenda 25 phút minh họa

| Phút | Hoạt động | Đầu ra |
| ---: | --- | --- |
| 0–3 | Nhắc mục tiêu, quyết định cần đưa ra và ràng buộc | Mọi người thống nhất câu hỏi |
| 3–8 | Kiểm chứng dữ liệu, ví dụ nghiệp vụ, điều chưa biết | Cùng hiểu sự kiện |
| 8–15 | So sánh hai phương án, tác động với Product Goal/DoD | Hiểu đánh đổi |
| 15–20 | Người có trách nhiệm ra quyết định hoặc xác định thí nghiệm cần thiết | Decision / next experiment |
| 20–25 | Ghi kết luận, owner, deadline và tác động tới backlog/test | Hành động có thể kiểm chứng |

Nếu chưa đủ bằng chứng, đầu ra hợp lệ là **quyết định trì hoãn có điều kiện**, kèm thử nghiệm/owner/ngày xem lại. Không ép chọn phương án vì “đã hết 25 phút”.

### 8.3. Kỹ thuật điều phối giúp giảm bất đồng văn hóa/ngôn ngữ

- Gửi **pre-read bằng văn bản** để người nói ngôn ngữ thứ hai có thời gian chuẩn bị.
- Cho mọi người ít phút viết ý kiến trước khi người nói nhiều phát biểu.
- Hỏi từng vai trò về **tác động/rủi ro**, không chỉ hỏi “ai đồng ý?”.
- Tách **ý kiến, dữ kiện và giả định**.
- Nói rõ nếu quyết định thuộc Product Owner, Developers hay người có trách nhiệm bảo mật.
- Nhắc lại các điều đã thống nhất bằng ngôn ngữ ngắn.
- Ghi **bất đồng còn lại** và tiêu chí kiểm tra, không xóa dấu vết ý kiến thiểu số.
- Sau cuộc họp, gửi bản tóm tắt mở cho người vắng mặt bổ sung sự kiện quan trọng.

Không nên ép mọi người bật camera. Hãy chú ý điều kiện kết nối, phụ đề, tài liệu viết và nhu cầu tiếp cận. Ghi hình/ghi âm khi cần chỉ thực hiện **khi phù hợp quy định, quyền riêng tư và sự đồng ý cần thiết**, không biến ghi hình thành yêu cầu mặc định.

### 8.4. Khi phiên đồng bộ đang bị biến thành họp dài

Dấu hiệu:
- Chưa có câu hỏi cụ thể.
- Phần lớn thời gian là đọc thông tin đã có trong issue.
- Không có người có thẩm quyền ra quyết định.
- Cần quá nhiều người chỉ để “cho biết”.
- Họp xong không có action/owner và vẫn trao đổi lại như ban đầu.

Cách sửa: chuyển thông tin nền sang async, giảm thành phần, chia thành hai câu hỏi hoặc chuyển sang **spike nhỏ có kết quả kiểm chứng**.

## 9. Mẫu phối hợp ba bước: async trước – sync khi cần – async sau

### 9.1. Trước cuộc thảo luận

Một người phụ trách gửi:
- Vấn đề, mục tiêu người dùng và nguồn dữ liệu.
- Hai hoặc ba phương án thật sự.
- Các giả định chưa rõ.
- Ai cần chuẩn bị điều gì.
- Điều kiện khi **không cần họp** (ví dụ mọi phản hồi đã thống nhất và không có rủi ro còn lại).

Người khác có thể thêm comment theo ca làm việc riêng. Cuộc họp **không phải nơi lần đầu đọc toàn bộ tài liệu**.

### 9.2. Trong cuộc thảo luận

Tập trung vào:
- Những câu hỏi **không giải được qua tài liệu**.
- Đánh đổi kiến trúc hoặc nghiệp vụ.
- Kiểm chứng cách hiểu bằng ví dụ.
- Chọn quyết định hoặc một thử nghiệm cụ thể.
- Nêu rủi ro và cách phát hiện kết quả sai.

Không lặp lại toàn bộ progress update hoặc thông tin nền.

### 9.3. Sau cuộc thảo luận

Trong cùng ngày làm việc của người phụ trách, ghi:
- **Decision:** đã chọn gì.
- **Rationale:** vì sao.
- **Scope:** áp dụng cho phần nào.
- **Assumptions:** điều gì chưa có bằng chứng.
- **Owners:** người thực hiện và xác minh.
- **Next steps:** issue/PR/test, mốc thời gian.
- **Review triggers:** khi nào cần xem lại quyết định.
- **Communication:** ai cần được biết nhưng không có mặt.

Ví dụ dòng trạng thái trên issue:

~~~text
Decision WS-18 / 2026-11-23 (ngày minh họa)
Trạng thái PENDING hiển thị "Đang chờ xác nhận".
Không được hàm ý đã giữ chỗ.
PO chịu trách nhiệm câu chữ; Developers bổ sung test;
nhóm thử nghiệm người dùng kiểm tra mức hiểu đúng.
Hẹn xem lại sau khi có bằng chứng thực tế.
Link: WS-18, PR, acceptance tests.
~~~

Một kết luận trong cuộc gọi mà không được đưa về **nguồn sự thật chung** dễ biến thành kiến thức chỉ một vài người nắm giữ.

## 10. Scrum trong nhóm phân tán: bảo vệ mục đích từng sự kiện

### 10.1. Các sự kiện Scrum không chỉ là kênh báo cáo

Trong Scrum, các events tạo nhịp **kiểm tra và thích ứng**:
- **Sprint Planning:** cả Scrum Team hợp tác về lý do (Why), nội dung (What) và cách làm (How) của Sprint.
- **Daily Scrum:** Developers kiểm tra tiến triển tới **Sprint Goal** và điều chỉnh Sprint Backlog; **15 phút**, vào cùng thời điểm và địa điểm mỗi ngày làm việc của Sprint theo Scrum Guide.
- **Sprint Review:** Scrum Team và stakeholders kiểm tra kết quả Sprint/Increment, cùng điều chỉnh hướng sản phẩm.
- **Sprint Retrospective:** Scrum Team lên kế hoạch cải thiện chất lượng và tính hiệu quả.

Các Scrum events có timebox và mục đích riêng. **Bản cập nhật trạng thái bất đồng bộ có thể hỗ trợ, nhưng không nên được tuyên bố tự động thay thế một Scrum event nếu nhóm đang áp dụng Scrum theo Scrum Guide.** Nếu nhóm theo một framework lai hoặc điều chỉnh phương pháp, hãy nói rõ đang thay đổi quy ước nào thay vì gọi mọi cuộc trao đổi là một Scrum event.

### 10.2. Daily Scrum không phải báo cáo cho quản lý

Một nhóm phân tán có thể cập nhật bảng công việc async trước Daily Scrum. Trong 15 phút, Developers nên dùng thời gian để:
- Nhìn Sprint Goal còn khả thi không.
- Xác định những story nào đang blocked hoặc có nguy cơ không Done.
- Điều chỉnh phối hợp: ai giúp review/test, ai làm rõ phụ thuộc.
- Quyết định trao đổi kỹ thuật chi tiết **sau Daily Scrum** với người liên quan.

Không có yêu cầu bắt buộc dùng đúng ba câu hỏi “hôm qua/hôm nay/blocker”. Daily Scrum nên **giúp Developers lập kế hoạch cho ngày làm việc**, không tạo màn hình chấm công.

### 10.3. Không có khung giờ đẹp cho tất cả?

Nếu có ba khu vực không chồng giờ hợp lý, nhóm cần thảo luận **cách tổ chức thật sự đáp ứng mục đích sự kiện**:
- Chọn một khung giờ ít gây bất lợi nhất có thể và **luân phiên khi hợp lý**.
- Dùng nguồn sự thật async để giảm phần đọc thông tin và thời gian họp.
- Dành Daily Scrum cho việc cần kiểm tra/điều chỉnh trực tiếp; điều tra chi tiết ở sau.
- Xử lý lịch làm việc, ngày nghỉ và sự tham gia của Developers với sự minh bạch.
- Nếu cách tổ chức hiện tại liên tục khiến thành viên phải thức đêm, xem lại **cấu trúc nhóm, phụ thuộc và cách làm Scrum**, không đơn thuần yêu cầu chịu đựng.

Không nên gọi một chuỗi status messages theo múi giờ là “Daily Scrum 15 phút của mọi Developers” nếu thực tế **không có cơ hội kiểm tra và thích ứng chung** theo mục đích đã công bố.

### 10.4. Sprint Planning, Review và Retrospective trong môi trường phân tán

**Planning:**
- Async trước: backlog items, mục tiêu, acceptance criteria, phụ thuộc và dữ liệu capacity.
- Sync: cùng thống nhất Sprint Goal, chọn công việc khả thi, định hướng cách thực hiện.
- Async sau: cập nhật Sprint Backlog, risks/owners và lịch cần phối hợp.

**Review:**
- Async trước: demo, tài liệu dùng thử, bằng chứng về outcome và questions.
- Sync: stakeholders cùng xem Increment và thảo luận hướng tiếp theo; **không biến thành cổng phê duyệt release**.
- Async sau: ghi insight, thay đổi Product Backlog, câu hỏi cần thử tiếp.

**Retrospective:**
- Async trước: thu quan sát về chờ phản hồi, bất tiện múi giờ, blocked work và chất lượng.
- Sync: tìm nguyên nhân và thống nhất ít cải tiến có khả năng thực hiện.
- Async sau: đưa hành động vào hệ thống công việc, đặt mốc đo lại.

Không nên đưa mọi quan điểm nhạy cảm lên bảng công khai nếu điều đó làm mất an toàn tâm lý; chọn hình thức thu thập và phân phối thông tin phù hợp.

### 10.5. Điều cần không đổi dù cách giao tiếp khác

- **Sprint Goal** phải được mọi người hiểu giống nhau.
- **Product Backlog** và **Sprint Backlog** có thông tin đáng tin.
- **Definition of Done** không thấp đi vì nhóm phân tán.
- Cộng tác giúp có **Increment hữu ích**, không chỉ nhiều tin nhắn/meeting minutes.
- Scrum Team chịu trách nhiệm cải tiến cách làm việc khi nhịp hiện tại gây chậm hoặc quá tải.

## 11. User story và backlog: thiết kế để ít phụ thuộc hỏi lại

### 11.1. Một user story rõ giảm số vòng chờ

Story:

> **Là học viên** đăng ký workshop, **tôi muốn** thấy phân biệt “đang chờ” và “đã xác nhận chỗ”, **để** không phải hỏi ban tổ chức liệu mình đã được giữ chỗ.

Acceptance criteria minh họa:
1. Khi trạng thái backend là PENDING, UI hiển thị “Đang chờ xác nhận” và không khẳng định đã giữ chỗ.
2. Khi backend là CONFIRMED, UI hiển thị “Đã xác nhận chỗ”.
3. Người dùng không được xem thông tin đăng ký của người khác.
4. Khi API trả lỗi, UI không suy đoán xác nhận thành công.
5. Kiểm thử trên các thiết bị/trình duyệt có rủi ro liên quan.

Một story có **đầu vào/đầu ra và ví dụ cụ thể** thường dễ review async hơn câu “làm màn hình trạng thái mới”.

### 11.2. Refinement bất đồng bộ không phải giao bài đơn phương

Developers, Product Owner và stakeholder có thể góp ý trên Product Backlog item theo ca làm việc riêng. Nhưng khi có nhiều cách hiểu hợp lý, cần chủ động tổ chức buổi làm rõ ngắn.

Ví dụ tiêu chí chuyển sang sync:
- Hai nguồn dữ liệu cho trạng thái khác nhau.
- Một acceptance criterion có thể dẫn đến sai dữ liệu.
- Có nhiều team cần thống nhất API và mức tương thích.
- Sprint Goal có nguy cơ vì câu hỏi tồn quá lâu.

Không dùng “đã viết trên ticket” như lý do từ chối trao đổi khi người khác chưa hiểu.

### 11.3. Tách item theo lát cắt giá trị

Thay vì tạo một epic “Xây nền tảng đăng ký hoàn chỉnh” kéo nhiều tháng, nhóm có thể chia:
- Hiển thị danh sách workshop có sức chứa.
- Gửi yêu cầu đăng ký và xem trạng thái.
- Bảo vệ bất biến không xác nhận vượt sức chứa.
- Cải thiện thông báo theo phản hồi người dùng.

**Lát cắt nhỏ và đạt DoD** làm cho handoff, review và dự báo qua múi giờ ít khó hơn. Nhưng không cắt nhỏ đến mức mỗi item chỉ còn “tạo DTO”, “sửa CSS” mà không tạo được kết quả kiểm tra hay giá trị.

## 12. Kanban: trực quan hóa hàng chờ giao tiếp, không chỉ hàng chờ code

### 12.1. Cột trên bảng phải thể hiện tình trạng thật

Một workflow minh họa:

~~~text
Ready -> Doing -> Review -> Verify -> Done
              |
              +-> BLOCKED (gắn lý do và người cần phối hợp,
                            vẫn nằm trong WIP theo ranh giới)
~~~

Với mỗi item đang blocked, nên ghi:
- Blocked **từ khi nào**.
- Đang chờ **câu trả lời hay kết quả gì**.
- **Ai có thể giúp**, theo ca làm việc nào.
- Mốc cần phản hồi và cách leo thang.
- Có thể hoàn tất công việc độc lập khác trong lúc chờ không?
- Rủi ro tới mục tiêu và chất lượng ra sao?

Không đẩy item về Ready chỉ để WIP giảm trên dashboard nếu item thực sự vẫn đang nằm trong công việc đã bắt đầu.

### 12.2. Các tín hiệu flow đáng theo dõi

| Số đo | Dùng trong nhóm phân tán để hỏi gì? | Tránh hiểu nhầm |
| --- | --- | --- |
| **WIP** | Nhóm mở bao nhiêu việc đồng thời? | Không phải số người đang “bận” |
| **Work item age** | Item chưa Done đã tồn bao lâu? | Không đo năng suất cá nhân |
| **Blocked time** | Chờ bối cảnh/quyết định/review chiếm bao lâu? | Cần phân loại nguyên nhân và ca làm việc |
| **Cycle time** | Từ Started tới Finished mất bao lâu? | Không bằng thời gian chờ từ yêu cầu đầu tiên nếu Started muộn |
| **Throughput** | Bao nhiêu item đạt Finished theo kỳ? | Không trực tiếp đo giá trị mỗi item |
| **Review queue age** | PR/story nào chờ phản hồi lâu? | Không đồng nghĩa reviewer chậm |
| **Rework/defects** | Có phải hiểu sai khi handoff dẫn đến sửa lại? | Không quy toàn bộ lỗi cho cách liên lạc |

### 12.3. Giảm WIP thường tốt hơn yêu cầu “phản hồi nhanh hơn mọi lúc”

Nếu Review có 8 item chờ, Developers tiếp tục mở thêm 5 story có thể làm tăng thời gian chờ tổng. Một chính sách pull/WIP phù hợp có thể khuyến khích:
- Người đang rảnh xem item gần Done.
- Tổ chức pairing ngắn để xử lý review khó.
- Làm rõ bối cảnh và test ngay trước handoff.
- Ưu tiên hoàn tất những item đã già trước khi bắt đầu thêm.

**Giảm WIP không phải lời giải cho mọi vấn đề**; nếu hệ thống thiếu quyền quyết định hoặc công cụ CI luôn lỗi, cần sửa nút thắt thật.

### 12.4. Không biến thời gian phản hồi thành KPI xếp hạng

Một thành viên ở Bắc Mỹ không phản hồi trong 6 giờ khi đang ngủ **không tương đương cố tình chậm**. Khi đo độ trễ nên phân biệt:
- Giờ lịch và **giờ làm việc được thống nhất**.
- Yêu cầu có đủ bối cảnh hay không.
- Yêu cầu có đúng người xử lý không.
- Blocker có thực sự nghiêm trọng?
- Người đang giải quyết sự cố ưu tiên cao hơn?

Dữ liệu flow giúp **cải tiến cấu trúc phối hợp**, không được dùng để yêu cầu mọi người bật thông báo 24/7.

## 13. Kỹ thuật XP giúp async handoff đáng tin hơn

### 13.1. Test và CI là một phần ngôn ngữ chung

Một bản bàn giao chỉ nói “code xong rồi” khó kiểm tra. Bản bàn giao có:
- Acceptance criteria đã áp dụng.
- PR/commit, cách chạy test.
- Trạng thái CI và những kiểm tra chưa chạy.
- Ví dụ expected/actual.
- Phạm vi còn thiếu.
- Cách xác minh trên môi trường an toàn.

sẽ giúp người nhận ở múi giờ khác **tiếp tục từ bằng chứng**, thay vì phải gọi người viết mã để hỏi lại mọi bước.

### 13.2. Pair programming đồng bộ có mục đích

Pairing hữu ích khi:
- Làm rõ kiến trúc hoặc bất biến khó.
- Chuyển giao kiến thức bị giữ bởi một chuyên gia.
- Khởi đầu một thay đổi rủi ro lớn.
- Đưa người mới vào codebase.
- Debug sự cố cần hai góc nhìn.

Không nên ép pairing **toàn bộ ca** khi hai người chỉ có một giờ chồng. Có thể:
1. Gửi bối cảnh và test đang đỏ trước.
2. Pairing 30–60 phút với mục tiêu hẹp.
3. Ghi thiết kế, test và next step.
4. Mỗi người tiếp tục phần độc lập trong ca riêng.
5. Hẹn thêm pairing khi xuất hiện nút thắt thật.

Pairing không phải tình huống một người thao tác và người kia chỉ xem; cần luân phiên đóng góp, tôn trọng khả năng tiếp cận và nhịp nghỉ.

### 13.3. Mẫu handoff qua PR

~~~text
PR: WS-18 - Trạng thái đăng ký v2

Mục tiêu:
Học viên phân biệt PENDING và CONFIRMED.

Phạm vi thay đổi:
UI labels, view model; không thay quy tắc xác nhận chỗ.

Đã kiểm:
- Unit tests cho trạng thái PENDING/CONFIRMED/REJECTED.
- Authorization test vẫn xanh.
- CI build: PASS tại commit abc123 (minh họa).

Chưa kiểm:
- Kiểm tra layout trên trình duyệt cũ.
- Nghiên cứu người dùng về mức hiểu đúng.

Cần người review trả lời:
Trường hợp API timeout có được giữ trạng thái "Đang chờ"
hay phải hiển thị "Không thể tải trạng thái"?

Đề xuất:
Không suy luận trạng thái nếu thiếu dữ liệu; hiện thông báo lỗi.

Bối cảnh:
Link story, acceptance criteria, screenshot mô tả không có PII.

Nếu phát hiện lỗi:
Bình luận trên PR và đánh dấu blocked, không merge khi thiếu DoD.

Mốc:
Trước lượt kiểm chứng nhóm tiếp theo, theo giờ làm việc reviewer.
~~~

Một PR như vậy cho người khác **điểm vào cụ thể** và giảm phụ thuộc vào người tạo PR đang ngủ.

### 13.4. Refactoring và ownership

Khi nhóm phân tán có **test hồi quy đáng tin, CI, coding standards, collective code ownership và review hợp lý**, người ở múi giờ khác có thể sửa mã mà không phụ thuộc mãi vào một người. Điều đó không nghĩa “ai cũng sửa production tùy tiện”; các kiểm soát quyền, review và DoD vẫn bắt buộc.

### 13.5. Chuyển giao kiến thức qua ví dụ chạy được

Có những điều khó mô tả bằng prose dài; một test thể hiện bất biến có thể hiệu quả hơn.

Ví dụ quy tắc:

~~~gherkin
Tính năng: Trạng thái đăng ký workshop

  Tình huống: Đang chờ không được hiểu là đã giữ chỗ
    Cho trước một yêu cầu đăng ký có trạng thái PENDING
    Khi học viên xem trang đăng ký của mình
    Thì giao diện hiển thị "Đang chờ xác nhận"
    Và không hiển thị thông điệp đã giữ chỗ thành công

  Tình huống: Người dùng không xem được đăng ký của người khác
    Cho trước một đăng ký thuộc học viên A
    Khi học viên B yêu cầu xem đăng ký này
    Thì hệ thống không tiết lộ dữ liệu riêng của A
~~~

Đây là đặc tả ví dụ; nhóm vẫn cần implementation và các kiểm tra bảo mật, tích hợp phù hợp. **Test xanh không chứng minh người dùng thật đã hiểu đúng**; phản hồi sản phẩm vẫn cần quan sát.

## 14. Lưu quyết định và đồng thuận khi không có mặt cùng lúc

### 14.1. Một quyết định có giá trị phải được truy vết

Thông tin tối thiểu cần giữ:

| Thành phần | Câu hỏi |
| --- | --- |
| **Vấn đề** | Phải giải quyết điều gì và tại sao? |
| **Ngữ cảnh** | Product Goal, ràng buộc, bằng chứng nào? |
| **Phương án** | Những lựa chọn khả thi đã xét? |
| **Quyết định** | Chọn gì, trong phạm vi nào? |
| **Người quyết** | Ai chịu trách nhiệm và cần tham vấn ai? |
| **Lý do** | Vì sao chọn, đánh đổi gì? |
| **Việc tiếp theo** | Ai cập nhật code/test/backlog và khi nào? |
| **Điều kiện xem lại** | Bằng chứng nào có thể khiến đổi quyết? |

Với quyết định kiến trúc quan trọng, có thể dùng **Architecture Decision Record (ADR)**. Với quyết định nhỏ trên một story, ghi trong issue và dẫn link PR có thể đủ. Không cần tạo ADR cho mỗi dòng code.

### 14.2. Quy trình ra quyết định bất đồng bộ có điểm chặn

Một cách làm:
1. Người đề xuất đăng tài liệu đầy đủ và thời điểm cần quyết.
2. Định danh **decision owner** và các bên bắt buộc tham vấn.
3. Mọi người phản hồi theo ca; người đề xuất tổng hợp khác biệt.
4. Nếu hết thời hạn mà còn mơ hồ hoặc có phản đối quan trọng, **sync nhỏ** với đúng người.
5. Người có trách nhiệm quyết **ghi kết quả**, không dùng im lặng làm đồng ý cho quyết định rủi ro cao.
6. Cập nhật backlog, tests, runbook hoặc ADR.
7. Đặt điều kiện kiểm tra lại nếu đang dựa trên giả định chưa chứng minh.

Quy trình này giữ **trách nhiệm rõ** mà không bắt tất cả mọi người cùng dự mỗi buổi họp.

### 14.3. Ví dụ decision log

~~~text
DEC-14: Khi API trạng thái lỗi, không hiển thị CONFIRMED

Bối cảnh:
WS-18. Khi timeout, dữ liệu mới không đủ để xác nhận trạng thái.

Phương án:
A. Giữ nhãn đã tải trước đó nhưng đánh dấu có thể cũ.
B. Hiển thị "Không thể tải trạng thái, thử lại".
C. Mặc định hiển thị CONFIRMED.

Decision:
Chọn B cho bản đầu. Loại C do rủi ro thông tin sai.
A cần nghiên cứu thêm về cache và trải nghiệm người dùng.

Decision owner:
Product Owner xác nhận thông điệp; Developers xác nhận tính đúng.

Action:
Thêm acceptance test và test khi API timeout.
Liên kết PR và tài liệu API.

Review trigger:
Phản hồi người dùng hoặc nhu cầu hoạt động offline thay đổi.
~~~

Nếu quyết định được đổi, **không sửa lịch sử để che mất lý do cũ**; ghi thông tin thay đổi và liên kết phiên bản hoặc quyết định mới.

## 15. Khẩn cấp, sự cố và leo thang: không dùng chat thường thay hệ thống trực

### 15.1. Phân cấp mức khẩn theo hậu quả

Một chính sách minh họa:

| Loại tình huống | Ví dụ | Giao tiếp đề xuất |
| --- | --- | --- |
| **Sự cố nghiêm trọng đang xảy ra** | Hệ thống xác nhận vượt sức chứa, lộ dữ liệu | Kích hoạt incident process, liên hệ on-call, sync điều phối |
| **Blocker có nguy cơ ảnh hưởng mốc quan trọng** | Không thể kiểm chứng transaction trước release | Đánh dấu blocked, nhắn owner trong giờ làm, sắp huddle nhanh |
| **Quyết định sản phẩm cần trước một mốc** | Cần chọn cách hiển thị để viết acceptance tests | Async proposal có deadline, escalate khi đến mốc |
| **Câu hỏi thông thường** | Cần ví dụ response API hoặc copywriting | Async ở ticket/tài liệu |
| **Thông tin tham khảo** | Demo kết quả, tài liệu học | Async, không bắt buộc phản hồi ngay |

Đừng dùng nhãn “URGENT” cho mọi việc. Nếu mọi thông báo đều khẩn, đội mất khả năng phân biệt **điều thật sự cần can thiệp**.

### 15.2. Quy trình incident giữa các khu vực

Khi production có vấn đề đang gây hại:
1. On-call nhận cảnh báo bằng **kênh chuyên dụng**.
2. Chỉ định incident lead, người phụ trách điều tra và người thông báo.
3. Ưu tiên bảo vệ người dùng, dữ liệu và giảm tác động.
4. Dùng sync có mục tiêu để chẩn đoán và phối hợp thao tác.
5. Ghi **timeline, quyết định và trạng thái** theo thời gian thực ở nơi chung.
6. Nếu ca trực cần chuyển giao, xác nhận người nhận và trạng thái kỹ thuật rõ.
7. Xác minh phục hồi và tác dụng phụ; cập nhật người liên quan.
8. Sau sự cố: async post-incident notes và retrospective/đánh giá không đổ lỗi.

**Không gửi ping liên tục tới toàn bộ team đang ngủ khi đã có on-call rota**; nếu cần bổ sung chuyên gia, đi theo cơ chế escalation và nghỉ bù phù hợp.

### 15.3. Handoff khi sự cố chưa kết thúc

Một bản bàn giao sự cố cần:
- **Mức ảnh hưởng và thời điểm cập nhật cuối**.
- Điều đã biết/điều chưa chắc.
- Hệ thống đang ở trạng thái nào, có đang bật flag/rollback không.
- Những tác vụ đang chạy dở và rủi ro thao tác lặp.
- Metrics, log và bằng chứng có đường dẫn.
- Việc ưu tiên trong ca tiếp theo.
- Khi nào phải gọi lại người đang nghỉ.
- Người nhận **xác nhận đã nhận bàn giao**.

Khác handoff công việc bình thường, sự cố nghiêm trọng có thể cần **đối thoại đồng bộ ngắn khi chuyển trách nhiệm**, không chỉ thả một tài liệu rồi biến mất.

### 15.4. Bảo mật và quyền riêng tư khi chia sẻ nhanh

Không đưa vào chat hoặc video công khai:
- Thông tin đăng nhập, access tokens, API keys.
- Dữ liệu cá nhân khách hàng không cần thiết.
- Bản ghi database chứa thông tin nhạy cảm.
- Các liên kết dashboard mở quyền rộng.
- Ảnh chụp có thông tin nội bộ vượt phạm vi người nhận.

Dùng kênh được tổ chức cho phép, phân quyền phù hợp, ẩn dữ liệu khi cần và tuân thủ quy tắc lưu trữ. **Nhu cầu cộng tác nhanh không làm mất các điều kiện bảo vệ dữ liệu.**

## 16. Handoff theo múi giờ: chuyển trạng thái, không chuyển sự mơ hồ

### 16.1. Một handoff có ý nghĩa

Đối với công việc thường lệ, handoff nên giúp đồng nghiệp ở ca tiếp theo **khởi động từ điểm đã đạt**, không phải lặp lại toàn bộ buổi điều tra.

Mẫu tối thiểu:

~~~text
Item/Story/Incident ID:
Mục tiêu và trạng thái hiện tại:
Kết quả đã tạo được:
Bằng chứng: PR/test/log/demo/doc:
Giả định đã kiểm hoặc chưa kiểm:
Blocked bởi điều gì, từ lúc nào:
Quyết định cần người nhận:
Next action nhỏ và tiêu chí Done:
Owner hiện tại / người nhận:
Mốc cần phản hồi và múi giờ:
Khi nào escalate:
Cách xác nhận đã nhận bàn giao:
~~~

### 16.2. Ví dụ hai ca làm việc nối tiếp

Giả sử Developers ở Việt Nam xử lý rule đăng ký workshop:
- Buổi sáng: tạo test cho không xác nhận vượt sức chứa.
- Buổi chiều: kết quả unit test xanh nhưng chưa kiểm tra hai request đồng thời với database thật.
- Trước hết ca: ghi PR, cách chạy integration test, những điều đã biết và điều cần người khác xác minh.
- Thành viên ở châu Âu nhận bàn giao trong giờ làm của mình: đọc, chạy test, comment về transaction.
- Kết quả ghi ở **cùng issue**, không bị giữ trong tin riêng.
- Developers Việt Nam vào ca ngày hôm sau đọc kết quả và quyết việc tiếp.

Mục tiêu không phải “biến ba múi giờ thành một ngày làm việc 24 giờ”. **Mỗi người vẫn làm việc trong ca phù hợp**, nhưng công việc có thể tiến lên nhờ trạng thái và bằng chứng rõ ràng.

### 16.3. Handoff tệ và handoff tốt

| Handoff tệ | Vì sao chặn người nhận | Handoff tốt |
| --- | --- | --- |
| “Xem hộ bug này.” | Không có tái hiện, mức khẩn, điều kiện thành công | Link issue, bước tái hiện, expected/actual, log đã ẩn PII |
| “Code gần xong.” | Không biết phần nào còn thiếu | PR và danh sách test đã/chưa chạy, phạm vi còn lại |
| “Chờ PO.” | Không biết câu hỏi hoặc khi nào cần trả lời | Nêu quyết định cụ thể, owner, deadline và ảnh hưởng |
| “Tôi đã sửa rồi.” | Không có bằng chứng kiểm chứng | Commit, CI, môi trường xác minh, rủi ro còn lại |
| “Tối nay ai rảnh họp?” | Ép phản ứng ngoài giờ, không mục tiêu | Chọn thời gian trong overlap và pre-read, hoặc async |

### 16.4. Người nhận không phải lúc nào cũng cần một cuộc gọi

Nếu thông tin đủ rõ và mức rủi ro phù hợp, **acknowledge trong ticket** là đủ. Nếu handoff liên quan incident, dữ liệu chưa nhất quán, khóa production hoặc thao tác không được lặp, cần xem xét **bàn giao trực tiếp** và xác nhận trách nhiệm rõ.

## 17. Phản hồi của khách hàng và stakeholder trong nhóm phân tán

### 17.1. Không chỉ tối ưu giao tiếp nội bộ

Một nhóm có thể phối hợp nội bộ cực kỳ trơn tru mà vẫn giao tính năng người dùng không cần. Agile đặt trọng tâm vào **giao phần mềm hữu ích và học từ phản hồi**.

Ví dụ màn hình trạng thái:
- Async: chia demo ngắn, tiêu chí sử dụng, prototype, câu hỏi khảo sát và dữ liệu phản hồi.
- Sync: phỏng vấn, quan sát người dùng thực hiện tác vụ, Sprint Review tương tác với stakeholder.
- Async sau: tổng hợp điều học được, tác động tới Product Backlog và test.

Không thay thế quan sát người dùng bằng 50 biểu tượng đồng ý trong chat nội bộ.

### 17.2. Thu phản hồi theo mục đích

| Câu hỏi | Phương thức phù hợp |
| --- | --- |
| “Nhãn trạng thái có dễ hiểu không?” | Dùng thử thực tế, phỏng vấn/quan sát + ghi kết quả |
| “Có bug nghiêm trọng nào sau rollout?” | Logs, alerts, support tickets, sự cố nếu cần |
| “Stakeholder ưu tiên điều gì cho Increment tiếp?” | Đọc dữ liệu async, Review/discussion sync khi cần |
| “Một đề xuất nhỏ nên sửa từ nào?” | Bình luận async trên mock/issue có bối cảnh |
| “Có bất đồng lớn về mục tiêu sản phẩm?” | Chuẩn bị bằng dữ liệu, sync quyết định và ghi lại |

**Phản hồi định tính** giúp hiểu vì sao; **số liệu định lượng** giúp xem mẫu rộng hơn. Cần giới hạn suy luận theo cỡ mẫu và bối cảnh, không coi mọi phản hồi là đại diện toàn bộ người dùng.

### 17.3. Công bố kết quả để mọi khu vực đều hiểu

Sau Sprint Review hoặc đợt dùng thử:
- Nêu **Increment nào đã đạt DoD**, không chỉ demo trông đẹp.
- Nêu người dùng đã dùng gì và quan sát được điều gì.
- Ghi vấn đề chưa rõ và giả thuyết tiếp theo.
- Cập nhật ưu tiên backlog và mốc quyết định.
- Cung cấp bản tóm tắt dễ đọc cho người vắng mặt.
- Không đưa thông tin nhạy cảm vượt quyền truy cập.

## 18. Tình huống xuyên suốt: nhóm workshop ba múi giờ

### 18.1. Bối cảnh và mục tiêu

Nhóm giả định:
- **Việt Nam:** hai Developers triển khai API và UI.
- **Warsaw:** một Developers/QA phối hợp kiểm thử và tích hợp.
- **New York:** một người phụ trách tích hợp và vận hành.
- **Product Owner:** phối hợp yêu cầu nghiệp vụ theo lịch đã thống nhất.
- **Product Goal:** học viên gửi đăng ký, nhìn thấy trạng thái đúng; không xác nhận vượt sức chứa.

Story hiện tại **WS-18**: làm rõ “Đang chờ xác nhận” và “Đã xác nhận chỗ”. Một quyết định API khó: khi request gặp timeout sau khi ghi dữ liệu, client có được hiển thị “Đã xác nhận” hay không?

Ràng buộc:
- Không được suy đoán kết quả nghiệp vụ chỉ từ timeout.
- Không được xác nhận vượt capacity hoặc làm lộ dữ liệu.
- Không ai được kỳ vọng trực tuyến 24 giờ.
- Sprint Goal và DoD cần được mọi người hiểu giống nhau.

### 18.2. Nếu chỉ dùng sync

Nhóm đặt họp toàn bộ lúc 08:00 UTC mỗi ngày:
- Việt Nam: 15:00 (phù hợp cho nhiều người).
- Warsaw mùa đông: 09:00 (có thể phù hợp).
- New York mùa đông: 03:00 (**không phù hợp với giờ làm thường**).

Hậu quả có thể là thành viên Bắc Mỹ bỏ họp hoặc phải thức đêm; các cuộc họp lặp lại những cập nhật đã có trên bảng; sự bất tiện tập trung vào một người. **Nhiều meeting không tự bảo đảm phối hợp tốt.**

### 18.3. Nếu chỉ dùng async

Nhóm nhắn:
- Việt Nam: “Timeout có được coi là CONFIRMED không?”
- Warsaw đọc sau vài giờ, hỏi: “Timeout ở API nào?”
- Việt Nam đã hết ca, ngày sau trả lời.
- New York thêm câu hỏi: “Có request key không?”
- Việt Nam đọc ngày sau nữa, mới nhận ra cần phân biệt đã ghi DB với phản hồi HTTP.

Vấn đề rủi ro cao **đi qua nhiều chu kỳ chờ** vì câu hỏi ban đầu thiếu bối cảnh và không có người điều phối.

### 18.4. Kế hoạch kết hợp

**Bước 1 – Async chuẩn bị:**
- Tạo WS-18 với các ví dụ:
  - PENDING nghĩa chưa có chỗ.
  - CONFIRMED phải đến từ trạng thái dữ liệu có thẩm quyền.
  - Timeout không tự chứng minh giao dịch thất bại hay thành công.
- Đính kèm contract API, trạng thái lưu trữ và test hiện có.
- Nêu hai phương án: client tiếp tục hiển thị trạng thái cũ có cảnh báo hay hiển thị “Không thể xác nhận trạng thái, thử lại”.
- Gắn người có quyền quyết về câu chữ và người chịu trách nhiệm kiểm tra dữ liệu.

**Bước 2 – Async phản hồi song song:**
- Developers/QA ở Warsaw thêm rủi ro kiểm thử khi timeout và retry.
- Người ở New York trong ca của họ nêu rủi ro idempotency và observability.
- Product Owner xác nhận không được thể hiện đã giữ chỗ nếu thiếu bằng chứng.
- Mọi nhận xét nằm tại **WS-18 hoặc tài liệu liên kết**, không phân tán trong nhiều tin riêng.

**Bước 3 – Sync đúng điểm nghẽn:**
- Nếu có phương án còn tranh cãi, tổ chức **huddle 20–25 phút** trong khung hợp lý cho những người cần quyết trực tiếp.
- Những người không thể dự đã ghi câu hỏi trước và xem kết luận sau.
- Với nội dung cần cả hai phía không có giờ chồng, dùng người đại diện **có đủ bối cảnh và thẩm quyền**, tránh mặc định một người phải dự hai cuộc mỗi ngày.
- Kết luận phải được ghi và phản hồi cho người vắng mặt.

**Bước 4 – Async quyết định và triển khai:**
- DEC-14: timeout không được mặc định là CONFIRMED.
- Developers cập nhật UI/test; QA xác minh acceptance criteria.
- CI và PR được dùng để xem kết quả.
- Handoff ghi rõ điều chưa kiểm ở trình duyệt cũ hoặc lúc mạng chập chờn.

**Bước 5 – Sync/async kiểm chứng kết quả:**
- Sprint Review xem Increment và phản hồi người dùng.
- Retrospective xem nơi chờ quyết định lâu, điểm cần cải thiện trong working agreement.
- Nhóm điều chỉnh kênh/thời hạn/biểu mẫu nếu cách mới làm tăng việc giấy tờ.

### 18.5. Lịch phối hợp minh họa theo nhịp tuần

| Hoạt động | Chế độ | Khi nào | Đầu ra |
| --- | --- | --- | --- |
| Cập nhật item/PR, blockers và kết quả test | Async | Theo ca làm việc của từng người | Nguồn sự thật luôn đủ mới |
| Làm rõ nghiệp vụ đơn giản | Async trước | Trước mốc refinement có ghi ngày/múi giờ | AC và quyết định có owner |
| Kỹ thuật cần nhiều vòng tranh luận | Huddle sync có pre-read | Khi xuất hiện điểm nghẽn đã xác định | Decision + action items |
| Review PR và CI | Async; pairing khi cần | Theo chính sách review đã đồng ý | Increment tiến về Done |
| Handoff cuối ca | Async, incident đặc biệt có sync | Khi kết thúc phần việc cần bàn giao | Trạng thái và next action |
| Daily Scrum (nếu dùng Scrum) | Sync đúng mục đích sự kiện; async hỗ trợ | Theo khung khả thi, 15 phút mỗi ngày làm việc | Điều chỉnh kế hoạch hướng Sprint Goal |
| Sprint Review/Retrospective | Có cộng tác trực tiếp; tài liệu trước/sau | Nhịp Scrum đã thống nhất | Phản hồi, điều chỉnh backlog/cách làm |
| Incident nghiêm trọng | Kênh on-call và sync điều phối | Theo mức sự cố, không đợi lịch | Khôi phục và phòng ngừa |

Lịch không bắt buộc tất cả cùng họp ở một múi giờ. **Nhóm nên bảo vệ mục đích của từng hoạt động và điều kiện làm việc bền vững**, không biến “follow the sun” thành nghĩa vụ làm xuyên ngày.

### 18.6. So sánh số liệu trước và sau theo một ví dụ giả định

Giả sử nhóm ghi nhận hai khoảng ba tuần, chỉ để luyện cách đọc dữ liệu:

| Tín hiệu cấp nhóm | Ba tuần trước | Ba tuần sau |
| --- | ---: | ---: |
| Số work items từng bị blocked do chờ thông tin | 12 | 8 |
| Trung vị blocked time trong các item đã giải chặn | 18 giờ lịch | 10 giờ lịch |
| Số việc phải mở lại vì hiểu sai acceptance criteria | 5 | 2 |
| Số cuộc huddle không có quyết định/hành động rõ | 7 | 2 |
| Lỗi nghiêm trọng sau bàn giao | 2 | 1 |
| Lượt người dùng thử hiểu đúng trạng thái | 10/15 | 12/15 |

Những số này **hoàn toàn giả định**:
- Blocked items giảm từ 12 xuống 8, tức giảm **4 item**, nhưng quy mô công việc có thể khác.
- Median blocked time giảm từ 18 xuống 10 giờ lịch, tức **8 giờ**; giờ lịch chưa loại thời gian nghỉ và chênh múi giờ.
- Người dùng hiểu đúng tăng từ 10/15 lên 12/15, nhưng mẫu **15 người mỗi kỳ** chưa đủ chứng minh tác động do riêng cách giao tiếp.
- Không được kết luận “huddle ít hơn nên mọi thứ tốt hơn” nếu chất lượng, outcome hoặc Sprint Goal xấu đi.

Nhóm có thể coi đó là **tín hiệu cần theo dõi tiếp**, kiểm tra biến gây nhiễu: độ khó story, nghỉ phép, sự cố, thay DoD, thay cách ghi blocked.

### 18.7. Câu hỏi trong Retrospective

> “Câu hỏi nào bị chờ lâu vì thiếu bối cảnh? Cuộc họp nào giúp giải quyết bất định thực sự? Có người nào phải thường xuyên dự ngoài giờ? Những quyết định nào chỉ tồn tại trong chat? Thử thay đổi một quy tắc handoff hay escalation nhỏ trong Sprint tiếp, rồi xem work item age, blocked time, lỗi và phản hồi người dùng thay đổi ra sao?”

Đó là cách Agile dùng **kiểm tra và thích ứng** để phát triển phương thức phối hợp phù hợp với bối cảnh thực.

## 19. Đo hiệu quả giao tiếp mà không tạo văn hóa giám sát

### 19.1. Không dùng số tin nhắn làm thước đo năng suất

Một người gửi 200 tin nhắn mỗi ngày chưa chắc tạo giá trị hơn người viết một tài liệu rõ giúp giải quyết một blocker. Tương tự, nhiều giờ họp không chứng minh nhóm hợp tác tốt.

Nên hỏi:
- Các quyết định quan trọng có được ghi và tìm lại được không?
- Work items có ít bị chặn vì thiếu thông tin hơn không?
- Người nhận có thể tiếp tục công việc sau handoff không?
- Sprint Goal và Increment có tiến triển đáng tin không?
- Có ít rework do hiểu sai hợp đồng/nghiệp vụ không?
- Người dùng có nhận được phần mềm đúng và có ích hơn không?

### 19.2. Bộ tín hiệu minh họa

| Nhóm tín hiệu | Số đo có thể xem | Giới hạn |
| --- | --- | --- |
| **Dòng công việc** | WIP, work item age, cycle time, throughput | Phụ thuộc loại item, DoW và điều kiện thực |
| **Chờ phối hợp** | Blocked time theo loại nguyên nhân, review queue age | Không dùng để chấm điểm người đang nghỉ |
| **Chất lượng thông tin** | Số lần phải hỏi lại, quyết định thiếu owner, PR thiếu test context | Cần định nghĩa nhất quán, tránh biến thành thủ tục |
| **Hiệu quả sync** | Cuộc họp có quyết định/action rõ, thời gian tham gia theo mục đích | Không tối ưu số cuộc họp thấp bằng mọi giá |
| **Khả năng tiếp cận** | Phản hồi tự nguyện về giờ họp, khả năng theo dõi khi vắng | Tôn trọng riêng tư và hoàn cảnh cá nhân |
| **Chất lượng kỹ thuật** | Lỗi do contract sai, CI thất bại, rework, incident | Không thể quy hết cho giao tiếp |
| **Giá trị sản phẩm** | Tỷ lệ hoàn tất tác vụ, hiểu trạng thái, phản hồi người dùng | Cần thiết kế đo phù hợp, tránh khẳng định nhân quả thiếu căn cứ |

### 19.3. Phân biệt thời gian chờ và thời gian xử lý

Một câu hỏi được gửi lúc 18:00 Việt Nam cho người ở New York. Người kia phản hồi trong ca sáng hôm sau của họ. **Thời gian lịch** giữa hai mốc có thể dài dù người nhận xử lý nhanh trong giờ làm.

Nên phân biệt:
- **Elapsed calendar time:** thời gian khách quan mà item chờ, ảnh hưởng tới ngày bàn giao.
- **Working-hours response time:** thời gian phản hồi tính trong lịch làm việc phù hợp.
- **Blocked time on work item:** khoảng thời gian item không thể tiến lên vì đang chờ phụ thuộc.
- **Time to decision:** lúc vấn đề được nêu đến lúc lựa chọn đủ rõ được ghi.

Đo cái nào phụ thuộc **câu hỏi**. Nếu khách hàng cần biết ngày giao, elapsed time là quan trọng; nếu đang cải tiến bố trí kênh và ca làm, cần xem working-hours và cấu trúc handoff.

### 19.4. Chỉ đo để cải tiến hệ thống

Không dùng:
- Thời gian online.
- Số lần bật camera.
- Thời gian trả lời từng tin nhắn ngoài giờ.
- Số emoji hoặc comment.
- Số cuộc họp tham dự.

để suy diễn **năng suất hoặc thái độ của từng cá nhân**. Những tín hiệu này rất dễ bị bóp méo, gây áp lực phải hiển thị “đang làm việc” thay vì giao kết quả.

## 20. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Mọi việc đều họp để “đảm bảo liên lạc” | Lịch họp dày, thiếu thời gian tập trung, loại trừ múi giờ | Async cho trạng thái/chuẩn bị; sync cho điểm mơ hồ có giá trị |
| Mọi việc đều chat async kể cả khủng hoảng | Sự cố chậm được giảm thiểu | Kênh on-call và sync điều phối theo mức nghiêm trọng |
| Đòi phản hồi chat ngay mọi thời điểm | Người khác không thể nghỉ hoặc làm sâu | Thỏa thuận giờ phản hồi và kênh khẩn riêng |
| Tin nhắn chỉ viết “xem hộ” | Hỏi lại nhiều vòng qua múi giờ | Ghi bối cảnh, câu hỏi, owner, bằng chứng và mốc |
| Không ghi quyết định sau họp | Người vắng mặt phải hỏi lại, mất lịch sử | Ghi decision log trong nguồn chung |
| Giữ quyết định chỉ ở tin nhắn riêng | Không thể tra cứu, phụ thuộc một người | Link từ issue/ADR/PR, tránh nguồn sự thật phân tán |
| Gửi proposal rồi coi im lặng là đồng ý | Rủi ro đồng thuận giả | Quy định người phải quyết và điều kiện chấp nhận |
| Không có deadline phản hồi | Blocker kéo dài vô hạn | Chọn mốc hợp lý và cơ chế escalation |
| Đặt deadline chỉ theo giờ người gửi | Người nhận có thể đang ngủ hoặc nghỉ | Ghi timezone, múi giờ khu vực và ca làm |
| Lịch họp cố định bất lợi cho một khu vực | Mệt mỏi, thiếu bao trùm, giảm chất lượng | Xem overlap, luân phiên khi hợp lý, cho tham gia async |
| Quên DST | Lịch bị lệch theo mùa | Dùng múi giờ khu vực trong lịch, kiểm tra định kỳ |
| Họp đông người nhưng không có người có quyền quyết | Mất nhiều giờ, vẫn blocked | Mời đúng người, chọn agenda quyết định |
| Bỏ pre-read | Họp chỉ để đọc tài liệu | Chia bối cảnh và câu hỏi trước |
| Báo cáo cá nhân thay cho Daily Scrum | Không kiểm tra Sprint Goal hoặc điều chỉnh kế hoạch | Dùng Daily Scrum cho Developers phối hợp hướng mục tiêu |
| Gọi chuỗi chat status là Scrum event đầy đủ | Sai mục đích inspect/adapt chung khi áp dụng Scrum | Thiết kế sự kiện đúng mục đích và nêu rõ lựa chọn phương pháp |
| PR không có test context | Người review phải hỏi lại hoặc dự đoán | Mẫu PR có tiêu chí, kết quả CI, rủi ro |
| Handoff chỉ nói “gần xong” | Không thể tiếp tục từ trạng thái đã đạt | Ghi next action, bằng chứng, blocked, người nhận |
| “Follow the sun” bị hiểu là cá nhân luôn 24/7 | Kiệt sức, lỗi và phụ thuộc | Phân ca và handoff, không làm ngoài giờ mặc định |
| Blocked item bị chuyển về Ready để đẹp WIP | Dashboard sai, item vẫn đứng | Giữ số đo trung thực và phân loại lý do |
| Ghi âm mọi cuộc gọi không xét quyền riêng tư | Mất tin tưởng, rủi ro pháp lý/bảo mật | Có sự đồng ý/chính sách phù hợp, tóm tắt bằng văn bản |
| Tối ưu thời gian phản hồi cá nhân | Văn hóa giám sát, giảm chất lượng | Dùng số liệu cấp nhóm để cải tiến dòng công việc |
| Chỉ đo số họp giảm | Có thể tăng hiểu sai, làm lại hoặc lỗi | Đo flow, quality, outcome và tính bền vững |
| Không xem lại working agreement | Quy tắc cũ không hợp khi nhóm đổi | Thử nghiệm cải tiến, đo lại và điều chỉnh |

## 21. Bài thực hành: thiết kế một hệ thống giao tiếp kết hợp

### 21.1. Nhiệm vụ A – Chọn chế độ cho từng tình huống (15 phút)

Với mỗi tình huống, chọn **async trước**, **sync trực tiếp**, hoặc **async + sync + async**, và giải thích lý do:

1. Product Owner cần sửa một lỗi chính tả trên bản mô tả story.
2. Hai team tranh luận cách rollback một schema migration khó đảo ngược.
3. Một PR chỉ thay tên biến nhưng đã có test xanh.
4. Production ghi xác nhận vượt sức chứa và còn tiếp tục nhận request.
5. Một Developers nhờ người khác chỉ cách chạy integration tests.
6. Stakeholder cần góp ý về prototype trong tuần sau.
7. Team không thống nhất “PENDING có giữ chỗ không?” sau ba vòng comment.
8. Thành viên mới phải tiếp nhận một phần code chưa có tài liệu.
9. Hết ca và một item đang chờ review không khẩn.
10. Trong Sprint, CI đỏ chặn nhiều story và không ai biết nguyên nhân.
11. Mọi người muốn biết tiến độ hôm qua của từng người.
12. Scrum Team cần kiểm tra kết quả Increment với stakeholder.

**Đáp án định hướng:**
- 1, 3, 5, 6, 9: thường **async trước**, trừ khi có rủi ro/chặn mới.
- 2, 7: **async chuẩn bị và ghi lại**, sync giải quyết bất đồng.
- 4: **incident sync ngay** qua kênh on-call, đồng thời ghi timeline.
- 8: pairing sync có thể rất hữu ích, kèm tài liệu async.
- 10: async báo sự cố CI và sync huddle nếu cần chẩn đoán nhanh để gỡ chặn.
- 11: cập nhật bảng async có thể đủ; nếu dùng Daily Scrum, sự kiện không chỉ hỏi báo cáo cá nhân.
- 12: Sprint Review có tương tác inspect/adapt phù hợp mục đích, được hỗ trợ bằng tài liệu trước/sau.

Không có một công cụ áp dụng cho mọi tình huống; **mức khẩn và độ mơ hồ** quan trọng hơn sở thích cá nhân.

### 21.2. Nhiệm vụ B – Kiểm tra múi giờ và tính công bằng (15 phút)

Dùng giả định mùa đông:
- Việt Nam UTC+7.
- Warsaw UTC+1.
- New York UTC−5.

Tính giờ địa phương khi họp:
1. **08:00 UTC**.
2. **12:00 UTC**.
3. **16:00 UTC**.

**Đáp án:**
- 08:00 UTC = **15:00 Việt Nam, 09:00 Warsaw, 03:00 New York**.
- 12:00 UTC = **19:00 Việt Nam, 13:00 Warsaw, 07:00 New York**.
- 16:00 UTC = **23:00 Việt Nam, 17:00 Warsaw, 11:00 New York**.

Câu hỏi thảo luận:
- Mốc nào phù hợp cả ba hơn nếu giờ làm thường là 9:00–17:00?
- Có nên yêu cầu một người tham gia lúc 03:00 hằng ngày không?
- Có thể tổ chức các phiên ngắn theo cặp khu vực và kết nối bằng decision log không?
- Khi thay đổi DST, điều gì phải kiểm lại?

**Gợi ý:** Không có mốc nào trong ba lựa chọn là khung 9:00–17:00 cho tất cả ba vùng. Cần chủ động giảm sự phụ thuộc vào họp toàn nhóm, điều chỉnh cách phối hợp và tôn trọng giờ làm.

### 21.3. Nhiệm vụ C – Viết lại tin nhắn async (15 phút)

Tin gốc:

> “API timeout có vấn đề. Ai đó quyết giúp để tôi tiếp tục.”

Viết lại thông điệp gồm:
- Story/PR liên quan.
- Expected/actual và tình huống tái hiện.
- Ảnh hưởng đến Product Goal hoặc DoD.
- Hai phương án với đánh đổi.
- Người phải quyết và người cần tham vấn.
- Mốc hợp lý kèm timezone.
- Cách escalation nếu bị chặn.
- Nơi lưu quyết định.

**Gợi ý:** Đừng đề xuất hiển thị CONFIRMED khi không biết transaction có hoàn tất hay không. Tách trạng thái nghiệp vụ khỏi lỗi truyền thông và đưa trường hợp vào acceptance tests.

### 21.4. Nhiệm vụ D – Lập handoff cuối ca (15 phút)

Developers Việt Nam tạo PR cho màn hình trạng thái v2. Unit tests xanh, nhưng một integration test trên database thật chưa chạy; cần kiểm tra trường hợp retry và timeout.

Hãy viết handoff sao cho người ở Warsaw hoặc New York **có thể tiếp tục mà không gọi lại tác giả PR**. Bắt buộc có:
- Mục đích story và AC.
- PR/commit và kết quả CI.
- Những thứ đã/chưa kiểm.
- Cách chạy test còn thiếu.
- Người nhận/phụ thuộc và deadline theo ca.
- Rủi ro nếu test không đạt.
- Điều kiện Done.

**Đáp án định hướng:** Handoff đạt khi người nhận biết **thao tác nhỏ tiếp theo, nguồn bằng chứng và tiêu chí thành công**. Không được ghi “Done” nếu DoD chưa hoàn thành.

### 21.5. Nhiệm vụ E – Phân tích độ trễ (15 phút)

Một nhóm thống kê hai khoảng thời gian giả định:

| Chỉ số | Kỳ 1 | Kỳ 2 |
| --- | ---: | ---: |
| Blocked items do chờ quyết định | 12 | 8 |
| Median blocked time | 18 giờ lịch | 10 giờ lịch |
| Reopen vì hiểu sai AC | 5 | 2 |
| Huddle không có action rõ | 7 | 2 |

Hãy:
1. Tính mức thay đổi tuyệt đối từng chỉ số.
2. Chọn hai chỉ số cần kiểm tiếp để hiểu nguyên nhân.
3. Nêu ít nhất ba biến gây nhiễu.
4. Giải thích vì sao không được dùng bảng để xếp hạng cá nhân.
5. Bổ sung **một outcome người dùng** và **một quality guardrail**.

**Đáp án:** Chênh lệch lần lượt là **−4 item, −8 giờ lịch, −3 lần reopen, −5 huddle**. Đây mới là dấu hiệu; cần xem độ khó/cơ cấu công việc, thay đổi DoD, nghỉ phép, incident và cách ghi dữ liệu. Outcome có thể là tỷ lệ học viên hiểu đúng trạng thái; guardrail là không có xác nhận vượt sức chứa.

### 21.6. Nhiệm vụ F – Giải quyết bất đồng về một quyết định (20 phút)

Hai nhóm muốn xử lý trạng thái timeout khác nhau:
- **Nhóm A:** giữ nhãn “Đã xác nhận” để người dùng yên tâm.
- **Nhóm B:** hiển thị “Không thể tải trạng thái, thử lại” vì không có bằng chứng xác nhận.

Nhiệm vụ:
1. Viết một proposal bất đồng bộ phân biệt **đã biết/đang giả định**.
2. Đặt tối đa **ba câu hỏi** quyết định cho một huddle 20 phút.
3. Chỉ định Product Owner/Developers và những bên phải tham vấn.
4. Ghi decision log với phạm vi và lý do.
5. Tạo test cho hành vi đã quyết.
6. Xác định dữ liệu người dùng cần xem sau bàn giao để kiểm chứng giá trị.

**Gợi ý:** Thông điệp phải phản ánh trạng thái thực; một lỗi truyền thông không thể tự động trở thành bằng chứng đã giữ chỗ. Nếu thông tin chưa đủ, cần phản hồi an toàn, không phỏng đoán.

### 21.7. Nhiệm vụ G – Thiết kế working agreement một trang (20 phút)

Theo nhóm nhỏ, soạn:
- Giờ làm việc, timezones và cách tính DST.
- Kênh cho thông báo thường, review, quyết định và incident.
- Thời hạn phản hồi trong **giờ làm việc**, không đòi 24/7.
- Định nghĩa “acknowledged”, “blocked” và “resolved”.
- Quy tắc chuyển sang sync và thành phần tối thiểu.
- Người chịu trách nhiệm ghi quyết định sau họp.
- Cách luân phiên cuộc họp khó và tham gia khi vắng.
- Cơ chế handoff và backup cho người nghỉ.
- Một cách đo flow và một cách lấy phản hồi về tính bền vững.
- Mốc thử hai tuần và cách điều chỉnh.

**Tiêu chí:** văn bản có thể sử dụng ngay, **không chỉ có những khẩu hiệu “giao tiếp tốt hơn”**.

### 21.8. Nhiệm vụ H – Một Retrospective về giao tiếp (20 phút)

Giả sử trong Sprint vừa qua:
- Có nhiều cuộc họp không ra quyết định.
- PR chờ review qua hai ca.
- Một Developers thường phải dự họp lúc 23:00.
- Chất lượng sản phẩm có lỗi do hiểu sai trạng thái.

Hãy:
1. Phân biệt **quan sát và giả thuyết**.
2. Chọn **một hoặc hai can thiệp**: pre-read, WIP policy, pairing, decision log hoặc luân phiên lịch.
3. Nêu owner, thời gian thử, cách thu dữ liệu.
4. Chọn một điều kiện **dừng/thay đổi thử nghiệm** nếu gây tác dụng phụ.
5. Giải thích vì sao chưa chắc “ít họp hơn” là thành công nếu cycle time hay lỗi tăng.

### 21.9. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Chọn sync/async** | Chọn theo sở thích công cụ | Chọn theo khẩn, mơ hồ và phụ thuộc | Nêu được chi phí chờ, rủi ro và quy tắc chuyển chế độ |
| **Thông điệp async** | Thiếu câu hỏi, owner và thời hạn | Có context, câu hỏi, bằng chứng, deadline | Giảm được vòng hỏi lại, có điều kiện escalation |
| **Phiên sync** | Họp không mục tiêu, không kết luận | Có agenda, đúng người, quyết định/action | Có pre-read, quản lý bất đồng, ghi kết quả bền vững |
| **Múi giờ và bao trùm** | Yêu cầu 24/7 hoặc họp đêm thường xuyên | Có overlap, lịch và phương án vắng mặt | Bảo vệ nhịp bền vững, kiểm lại DST và bất tiện phân bổ |
| **Scrum/Kanban/XP** | Nhầm status update với phối hợp | Dùng events đúng mục đích, flow và test hỗ trợ | Cải tiến phụ thuộc, WIP, DoD, handoff và chất lượng |
| **Đo lường** | Đếm chat/họp của cá nhân | Theo dõi blocked age, rework, outcome | Nhận diện biến gây nhiễu và thử cải tiến có guardrails |

## 22. Biểu mẫu thực hành dùng ngay

### 22.1. Working agreement cho nhóm phân tán

~~~text
Tên nhóm và Product Goal:
Múi giờ khu vực từng thành viên:
Giờ làm việc/giờ chồng có thể dùng:
Ngày nghỉ và người dự phòng:
Nguồn sự thật cho backlog/Sprint Goal/flow:
Kênh cập nhật thường lệ:
Kênh câu hỏi/PR/code review:
Kênh quyết định và tài liệu lưu lịch sử:
Kênh incident và on-call:
Thời hạn phản hồi bình thường:
Thời hạn acknowledgement cho blocked item:
Điều kiện chuyển từ async sang sync:
Người có quyền quyết từng loại vấn đề:
Cách đặt agenda, pre-read, mời người tham gia:
Cách ghi decision log và thông báo cho người vắng:
Handoff cuối ca và xác nhận người nhận:
Bảo vệ giờ nghỉ, quyền riêng tư và accessibility:
Chỉ số kiểm tra và ngày xem lại thỏa thuận:
~~~

### 22.2. Mẫu câu hỏi bất đồng bộ

~~~text
Chủ đề / issue ID:
Mục tiêu nghiệp vụ:
Vấn đề đã quan sát:
Bằng chứng và liên kết:
Điều đang cần được quyết:
Phương án A/B và đánh đổi:
Giả định và thông tin còn thiếu:
Tác động lên Sprint Goal/DoD/khách hàng:
Người có trách nhiệm quyết:
Những người cần tham vấn:
Thời điểm cần câu trả lời (ngày/giờ/múi giờ):
Nếu không thể quyết async, huddle sẽ giải quyết gì:
Nơi ghi kết luận và action:
~~~

### 22.3. Mẫu agenda đồng bộ

~~~text
Tên quyết định:
Tại sao cần sync thay vì chỉ bình luận async:
Pre-read và giả định:
Các câu hỏi phải giải quyết:
Người có quyền quyết/những người bắt buộc:
Thời lượng dự kiến:
Phương án và ràng buộc:
Quyết định hoặc phép thử tiếp theo:
Điều chưa rõ:
Owner/action/deadline:
Decision log cần cập nhật ở đâu:
Ai không tham dự và cách chia sẻ kết quả:
~~~

### 22.4. Mẫu bàn giao qua múi giờ

~~~text
Ngày giờ bàn giao theo timezone khu vực:
Item/Incident/PR:
Mục tiêu:
Trạng thái và bước vừa hoàn tất:
Nguồn bằng chứng:
Các kiểm tra đã chạy và kết quả:
Các kiểm tra chưa chạy:
Điều đang blocked và nguyên nhân:
Rủi ro, đặc biệt dữ liệu/quyền/tác dụng phụ:
Next action nhỏ:
Điều kiện thành công hoặc Done:
Người nhận và người dự phòng:
Mốc phản hồi theo giờ làm việc:
Cần sync ngay nếu:
Người nhận đã xác nhận:
~~~

### 22.5. Mẫu biên bản quyết định

~~~text
Decision ID và ngày:
Bối cảnh và người sử dụng kết quả:
Vấn đề:
Bằng chứng:
Các phương án cân nhắc:
Quyết định và phạm vi:
Người quyết:
Lý do và đánh đổi:
Giả định chưa xác minh:
Việc làm theo quyết định:
Owner/deadline:
Test hoặc outcome dùng kiểm chứng:
Điều kiện xem lại:
Liên kết issue/PR/ADR:
Những người cần thông báo:
~~~

### 22.6. Mẫu review hiệu quả phối hợp

~~~text
Khoảng thời gian và loại item:
Kỳ vọng phản hồi đã thỏa thuận:
WIP và work item age:
Blocked time, lý do và ví dụ:
PR/review queue age:
Rework do hiểu sai yêu cầu:
Những sync sessions có ích:
Những sync sessions không tạo kết quả:
Phản hồi về tính công bằng múi giờ:
Quality guardrails:
Outcome người dùng:
Giả thuyết về nút thắt:
Thử nghiệm cải tiến, owner, thời hạn:
Cách quan sát tác dụng phụ:
Mốc quyết định giữ/chỉnh/dừng:
~~~

Biểu mẫu là **công cụ để giảm bất định**, không phải thủ tục bắt buộc áp dụng cho mọi tin nhắn. Nếu một câu hỏi đơn giản giải được bằng một comment có link, không cần tạo cả tài liệu riêng.

## 23. Checklist: kết hợp giao tiếp đồng bộ và bất đồng bộ

**Mục đích và cách chọn:**

- [ ] Nhóm phân biệt thông tin một chiều với quyết định cần tương tác.
- [ ] Chọn sync/async dựa trên khẩn, mơ hồ, phụ thuộc và rủi ro.
- [ ] Không tổ chức họp chỉ để đọc trạng thái đã có trong công cụ.
- [ ] Có quy tắc chuyển từ async sang sync khi blocker không được giải quyết.
- [ ] Sự cố nghiêm trọng có cơ chế điều phối nhanh, không chờ chat thông thường.
- [ ] Không hiểu “ít họp” hoặc “nhiều tin nhắn” là mục tiêu tự thân.

**Thông tin bất đồng bộ:**

- [ ] User story/PR/issue có bối cảnh, câu hỏi, ví dụ và đường dẫn bằng chứng.
- [ ] Mỗi yêu cầu cần quyết có owner và mốc phản hồi hợp lý.
- [ ] Thời hạn ghi ngày/giờ/múi giờ rõ; không giả định trực 24/7.
- [ ] Phân biệt acknowledgement với decision và verification.
- [ ] Không coi sự im lặng là đồng thuận khi quyết định đòi xác nhận.
- [ ] Quyết định và kết quả được cập nhật vào nguồn sự thật chung.
- [ ] Handoff ghi đủ trạng thái, điều còn thiếu, next action và người nhận.
- [ ] Dữ liệu cá nhân, token và thông tin nhạy cảm được bảo vệ trên các kênh.

**Phiên đồng bộ:**

- [ ] Cuộc họp có mục tiêu và tiêu chí kết thúc rõ.
- [ ] Pre-read được chia trước cho những người tham gia.
- [ ] Có đúng người cần thảo luận và có thẩm quyền quyết.
- [ ] Người tham gia có cơ hội phát biểu, không ép camera hoặc lịch không phù hợp.
- [ ] Kết luận có rationale, action, owner, deadline và nơi lưu.
- [ ] Người vắng mặt có cách đóng góp và tiếp nhận kết quả.
- [ ] Lịch được xem lại khi DST hoặc đội hình thay đổi.
- [ ] Không có cá nhân phải thường xuyên hy sinh giờ nghỉ để tạo “độ phủ toàn cầu”.

**Agile và chất lượng:**

- [ ] Nếu dùng Scrum, các events bảo vệ mục đích inspect/adapt; Daily Scrum không bị biến thành báo cáo cho quản lý.
- [ ] Sprint Goal, Product Goal, backlog và Definition of Done được hiểu thống nhất.
- [ ] Kanban board phản ánh blocked và WIP trung thực.
- [ ] PR, CI, test và tài liệu cho phép người khác tiếp nối công việc qua múi giờ.
- [ ] Pairing/huddle được dùng khi giúp giải quyết bất định thực sự.
- [ ] Nhóm quan sát blocked time, work item age, cycle time và rework với bối cảnh.
- [ ] Không dùng tốc độ trả lời chat để xếp hạng cá nhân.
- [ ] Quality guardrails và outcome người dùng được xem cùng số đo phối hợp.
- [ ] Working agreement có mốc xem lại và cải tiến dựa trên bằng chứng.

**Kết luận:** Trong nhóm Agile phân tán, **đồng bộ và bất đồng bộ là hai khả năng bổ trợ**, không phải hai phe đối nghịch. Async giúp chia sẻ bối cảnh, giữ lịch sử, làm việc qua múi giờ và bảo vệ tập trung; sync giúp giải quyết nhanh sự mơ hồ, xây hiểu biết chung và phối hợp khi có hậu quả lớn. **Chuẩn bị trước bằng văn bản – gặp đúng người khi cần – ghi quyết định và bàn giao rõ sau đó** giúp tránh cả hai cực đoan: cuộc họp triền miên và chuỗi tin nhắn chờ vô hạn. Khi gắn cách phối hợp ấy với Sprint Goal, Product Goal, WIP, DoD, chất lượng kỹ thuật và phản hồi người dùng, nhóm có thể **giao giá trị tăng dần với sự cộng tác bền vững, dù không làm việc cùng địa điểm hay cùng giờ**.
