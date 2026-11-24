# Đánh giá chất lượng, mức độ ổn định và tính bền vững của nhịp làm việc

Một Scrum Team hoàn thành nhiều story hơn Sprint trước và triển khai phần mềm thường xuyên hơn. Báo cáo nhìn rất tích cực. Tuy nhiên, mỗi đợt phát hành đều có lỗi phải sửa khẩn cấp, một số Pull Request chờ review hàng tuần, các Developer liên tục làm ngoài giờ và Product Owner không còn biết thời điểm nào một khả năng có thể sử dụng được. **Đội có thật sự đang làm việc hiệu quả hơn không?**

Đo lường Agile không chỉ là đếm khối lượng công việc. Nó giúp đội **nhìn thấy sự thật về giá trị, chất lượng, luồng công việc và năng lực duy trì nhịp làm việc**, rồi chọn thử nghiệm cải tiến có cơ sở. Một đội có thể giao nhiều tính năng trong một tháng nhưng tích lũy lỗi và sự kiệt sức; hoặc giảm số lượng hạng mục hoàn thành trong thời gian ngắn để loại bỏ nút thắt, sau đó giao sản phẩm đáng tin cậy hơn.

Bài này thuộc chương **Đo lường Agile** của mô-đun **AGILE_DEVELOPMENT**. Cách tiếp cận gắn với giá trị Agile: **phản hồi sớm, phần mềm tăng dần, cải tiến liên tục**, sử dụng user story, Product Backlog, Scrum, Kanban, XP và các thước đo dòng công việc theo bối cảnh.

**Sau bài học, bạn có thể:**

- Phân biệt **chất lượng sản phẩm, độ tin cậy vận hành, độ ổn định dòng công việc, tính dự báo và nhịp làm việc bền vững**.
- Chọn tập chỉ số cân bằng giữa **outcome, quality, flow, reliability và team sustainability**.
- Đọc và tính **throughput, cycle time, Work Item Age, WIP, độ biến thiên, SLE** mà không nhầm với velocity hoặc năng suất cá nhân.
- Diễn giải **lỗi lọt ra sau phát hành, change failure, thời gian phục hồi, SLI/SLO và error budget** đúng bối cảnh.
- Nhận biết khi nào số liệu bị sai lệch vì thay đổi cách tách ticket, dữ liệu thiếu, mẫu nhỏ hoặc tối ưu chỉ tiêu.
- Kết hợp **định lượng, phản hồi người dùng và tín hiệu từ người làm việc** để phát hiện tốc độ được tạo bằng làm thêm giờ hoặc tăng nợ kỹ thuật.
- Thiết kế một thử nghiệm cải tiến có **giả thuyết, baseline, guardrail, người phụ trách và thời điểm xem lại**.

## 1. Đo lường để học hỏi, không để tạo bảng xếp hạng

Agile nhấn mạnh **thích ứng dựa trên kiểm tra thực tế**. Muốn kiểm tra hiệu quả, đội cần dữ liệu đủ rõ để trả lời:

1. **Giá trị:** Người dùng có giải quyết vấn đề tốt hơn không?
2. **Chất lượng:** Phần mềm đúng, an toàn và đáng tin cậy hơn không?
3. **Dòng công việc:** Yêu cầu có đi tới Done với thời gian chờ và độ biến thiên có thể quản lý không?
4. **Khả năng dự báo:** Đội có thể đưa ra dự báo với độ tin cậy thích hợp, nêu rõ bất định không?
5. **Tính bền vững:** Nhịp làm việc có thể duy trì qua nhiều tháng mà không phụ thuộc vào làm ngoài giờ hoặc người hùng cứu sự cố không?

Đo lường tốt **không trả lời hộ con người**. Nó cung cấp tín hiệu để những người hiểu nghiệp vụ, kỹ thuật và người dùng cùng diễn giải, kiểm tra giả định và thử thay đổi.

### Khi một chỉ số tăng mà kết quả lại xấu

| Chỉ số tăng | Vì sao có thể chưa tốt? | Tín hiệu nên xem cùng |
| --- | --- | --- |
| Số ticket hoàn thành | Story được chia nhỏ hơn, hoặc nhiều ticket chỉ là task kỹ thuật | Outcome, cycle time, DoD và loại công việc |
| Số lần triển khai | Mỗi lần triển khai có thể mang lỗi hoặc không tới người dùng | Change failure, độ tin cậy, khả năng phục hồi |
| Tỷ lệ sử dụng tính năng | Người dùng có thể phải thử lại nhiều lần vì lỗi | Task success, người dùng duy nhất, phản hồi |
| Số giờ làm việc | Có thể phản ánh quá tải hoặc xử lý sự cố liên tục | Chất lượng, thời gian phục hồi, nhịp nghỉ |
| Mức sử dụng nhân lực | Mọi người bận 100% có thể khiến hàng đợi dài | WIP, flow, blocked time |
| Velocity | Có thể thay cách ước lượng, tăng point mà giá trị không đổi | Sprint Goal, Increment đạt DoD, outcome |

**Một chỉ số đơn độc rất dễ bị tối ưu sai.** Vì vậy, đội cần **một hệ tín hiệu nhỏ, cân bằng** thay vì cố tổng hợp mọi mặt vào một “điểm Agile” duy nhất.

## 2. Năm góc nhìn cần phân biệt

| Góc nhìn | Câu hỏi trung tâm | Ví dụ thước đo |
| --- | --- | --- |
| **Product outcome** | Người dùng có đạt mục tiêu? | Tỷ lệ học viên quay lại đúng vị trí đã lưu |
| **Product quality** | Chức năng đúng và có thể duy trì? | Lỗi lọt sau phát hành, lỗi hồi quy, kiểm thử hành vi trọng yếu |
| **Service reliability** | Khi được sử dụng, dịch vụ có ổn định và khôi phục được? | SLI, SLO, sự cố, thời gian phục hồi |
| **Flow stability/predictability** | Công việc di chuyển đều đặn và có thể dự báo? | Throughput, phân phối cycle time, WIP, Work Item Age |
| **Sustainable pace** | Đội có thể tiếp tục tạo giá trị mà không tăng gánh nặng vô hạn? | Làm ngoài giờ, gián đoạn, on-call, khối lượng hỗ trợ, phản hồi đội |

### Đừng dùng một lớp kết quả thay lớp khác

Một chức năng đạt **Definition of Done** nhưng người dùng không tìm thấy hoặc không cần sử dụng: chất lượng kỹ thuật có thể đạt, outcome chưa đạt.

Một cải tiến **tăng chuyển đổi người dùng** nhưng gây mất tiến độ: outcome trung bình có dấu hiệu tốt, chất lượng và độ tin cậy không chấp nhận được.

Một đội giảm **cycle time** bằng cách tạo hàng trăm task nhỏ: dữ liệu luồng công việc không còn so sánh được nếu đơn vị công việc thay đổi.

Một Sprint hoàn thành Sprint Goal nhưng mọi người phải làm thêm giờ kéo dài: **không thể kết luận nhịp làm việc bền vững** chỉ từ một lần đạt mục tiêu.

## 3. Thiết kế hệ chỉ số cân bằng theo mục tiêu

Thay vì chọn 25 con số rồi mới tìm lý do đo, hãy đi từ **Product Goal và vấn đề đội cần giải quyết**.

~~~mermaid
flowchart TD
    A["Product Goal và rủi ro hiện tại"] --> B["Câu hỏi cần học / giả thuyết"]
    B --> C["Chỉ số kết quả chính"]
    C --> D["Chỉ số chất lượng và độ tin cậy"]
    D --> E["Chỉ số dòng công việc và tính dự báo"]
    E --> F["Chỉ số bảo vệ nhịp làm việc bền vững"]
    F --> G["Kiểm tra nguồn dữ liệu, ranh giới và thiên lệch"]
    G --> H["Thử cải tiến, quan sát, ra quyết định"]
    H --> A
~~~

### Ví dụ cho nền tảng học trực tuyến

**Product Goal:** Học viên tiếp tục học từ tiến độ đã lưu mà không phải làm lại các phần đã hoàn thành.

| Lớp | Một chỉ số gợi ý | Điều được bảo vệ |
| --- | --- | --- |
| **Outcome** | Tỷ lệ học viên đủ điều kiện tiếp tục thành công từ tiến độ đã xác nhận | Giá trị cho người dùng |
| **Chất lượng** | Số lỗi mất tiến độ nghiêm trọng, tỷ lệ phiên khôi phục sai | Tính đúng |
| **Độ tin cậy** | Tỷ lệ yêu cầu lưu/đọc hợp lệ thành công trong giới hạn thời gian | Trải nghiệm đang vận hành |
| **Dòng công việc** | Phân phối cycle time cho user story và tuổi các hạng mục đang bị chặn | Thời gian giao Increment |
| **Nhịp bền vững** | Thời gian xử lý sự cố ngoài kế hoạch, mức làm thêm giờ tự báo và khả năng nghỉ phục hồi | Năng lực tiếp tục cải tiến |

Đây là **bộ ví dụ**, không phải dashboard bắt buộc cho mọi đội. Với nhóm đang sửa một lỗi dữ liệu nghiêm trọng, **tính đúng và an toàn** sẽ là ưu tiên cao hơn việc tăng throughput.

### Mỗi chỉ số cần một “hợp đồng đo”

Một định nghĩa đủ dùng nên ghi:

~~~text
Tên chỉ số:
  Tỷ lệ khôi phục tiến độ thành công.

Câu hỏi:
  Người học đủ điều kiện có thực sự quay lại đúng vị trí không?

Tử số:
  Số lần khôi phục đúng tiến độ đã xác nhận (hoặc số người,
  tùy mục tiêu đo và đã thống nhất).

Mẫu số:
  Tổng số lần khôi phục hợp lệ có đủ dữ liệu kiểm chứng.

Ranh giới:
  Chỉ môi trường production, phiên bản/nhóm đủ điều kiện.

Thời gian:
  Cửa sổ quan sát, múi giờ và cách xử lý sự kiện đến muộn.

Nguồn:
  Telemetry và kết quả lưu/đọc dữ liệu được kiểm chứng.

Chủ sở hữu định nghĩa:
  Người chịu trách nhiệm bảo đảm cách đo nhất quán.

Guardrail:
  Không tăng lỗi dữ liệu, không bỏ qua yêu cầu bảo vệ người học.

Giới hạn:
  Các phiên không đủ dữ liệu có thể làm mẫu bị thiên lệch.
~~~

Không cần tạo biểu mẫu dài cho mọi phép đo nhỏ, nhưng **định nghĩa phải đủ rõ để người khác tính cùng một kết quả**.

## 4. Chất lượng không chỉ là số lượng bug

**Chất lượng sản phẩm** gồm nhiều chiều: chức năng có đúng không, dễ hiểu và dùng được không, có bảo vệ dữ liệu không, có thể bảo trì không, có đáp ứng yêu cầu hiệu năng và khả năng tiếp cận không?

### Những tín hiệu chất lượng

| Chỉ số/tín hiệu | Câu hỏi | Điểm mù |
| --- | --- | --- |
| **Defect escape** | Những lỗi nào chỉ bị phát hiện sau khi giao hoặc phát hành? | Phụ thuộc cách ghi nhận và mức sử dụng |
| **Lỗi nghiêm trọng** | Có lỗi gây mất dữ liệu, lộ thông tin hoặc gián đoạn lớn? | Một lỗi nghiêm trọng có thể quan trọng hơn 20 lỗi nhỏ |
| **Lỗi hồi quy** | Thay đổi mới có phá hành vi đang hoạt động? | Cần phân biệt lỗi cũ chưa biết và lỗi do thay đổi |
| **Reopen/rework** | Hạng mục đã báo Done có phải làm lại vì chưa đạt yêu cầu? | Có thể vì yêu cầu hợp lý thay đổi, không phải lỗi |
| **Kiểm thử hành vi quan trọng** | Những rủi ro cốt lõi có được kiểm chứng? | Đếm test hoặc % coverage không đo chất lượng assertion |
| **Defect age** | Lỗi quan trọng tồn tại bao lâu trước khi được xử lý? | Không thể so chung lỗi nhẹ với sự cố nghiêm trọng |
| **Phản hồi người dùng** | Người học có gặp vấn đề mà test chưa mô tả? | Người gửi phản hồi không đại diện toàn bộ người dùng |
| **Maintainability signals** | Mã có khó thay đổi, phức tạp, phụ thuộc chuyên gia? | Số class/độ phức tạp thô không phải phán quyết tuyệt đối |

### Lỗi lọt ra sau phát hành

Một cách tính cục bộ có thể là:

\[
\text{Tỷ lệ lỗi phát hiện sau phát hành}
=\frac{\text{Số lỗi xác định sau phát hành trong nhóm đo}}
{\text{Tổng lỗi xác định trước và sau phát hành trong nhóm đo}}
\times100\%.
\]

**Ví dụ giả định:** Trong cùng một phạm vi tính năng và kỳ quan sát, nhóm xác nhận 24 lỗi trước phát hành và 6 lỗi sau phát hành:

\[
\frac{6}{24+6}\times100\% = 20\%.
\]

Đây là **một định nghĩa minh họa**, không phải công thức chuẩn duy nhất được mọi tổ chức áp dụng. Nó chỉ có nghĩa khi **tiêu chí đếm lỗi, mức nghiêm trọng, nguồn phát hiện và cửa sổ thời gian được thống nhất**. Số lỗi sau phát hành ít cũng có thể do ít người dùng hoặc thiếu kênh báo lỗi, không nhất thiết sản phẩm tốt hơn.

### Nên cân nhắc độ nghiêm trọng, không chỉ tổng số

| Loại sự cố | Ví dụ | Lý do cần phân biệt |
| --- | --- | --- |
| **Nghiêm trọng** | Học viên đọc được tiến độ của tài khoản khác | Liên quan quyền truy cập và quyền riêng tư |
| **Cao** | Lưu tiến độ sai làm mất nội dung đã hoàn thành | Ảnh hưởng trực tiếp giá trị sản phẩm |
| **Trung bình** | Nút tiếp tục đôi khi không hoạt động trên trình duyệt ít dùng | Ảnh hưởng trải nghiệm trong điều kiện nhất định |
| **Thấp** | Thông điệp có lỗi trình bày không gây hiểu nhầm | Có thể sửa theo ưu tiên và chi phí cơ hội |

Ngưỡng phân loại thực tế cần được **nhóm/tổ chức thống nhất theo hậu quả, không dựa vào cảm giác hoặc chức danh người báo**.

### Test coverage cao không đồng nghĩa độ tin cậy cao

Một dòng code được kiểm thử thực thi chưa chắc các trường hợp dữ liệu sai, truy cập trái phép hay phản hồi đến muộn đã được kiểm tra. Vì vậy:

- Coverage có thể giúp **phát hiện vùng mã thiếu kiểm chứng**.
- Chất lượng test còn phụ thuộc **assertion, dữ liệu thử, rủi ro, khả năng chẩn đoán và độ ổn định**.
- Cần bổ sung **test tích hợp, contract, kiểm thử bảo mật và các kịch bản người dùng quan trọng** theo phạm vi thực.
- Đừng đặt “100% coverage” là mục tiêu tự thân rồi tạo nhiều test vô nghĩa.

## 5. Definition of Done và chất lượng không thể đánh đổi

Trong Scrum, **Definition of Done (DoD)** là commitment cho Increment, mô tả tiêu chuẩn chất lượng của phần sản phẩm được coi là hoàn thành. Một PBI chưa đáp ứng DoD **không được tính là Increment hoàn thành**, dù mã đã viết xong hoặc có thể demo.

### Chất lượng nên được xây vào dòng công việc

~~~mermaid
flowchart LR
    A["Ví dụ nghiệp vụ rõ"] --> B["Kiểm thử và phát triển từng lát cắt"]
    B --> C["Review / tích hợp thường xuyên"]
    C --> D["Kiểm tra chất lượng, bảo mật phù hợp"]
    D --> E["Increment đạt Definition of Done"]
    E --> F["Phát hành an toàn và quan sát"]
    F --> G["Phản hồi thực và cải tiến"]
~~~

### Dấu hiệu rủi ro khi đẩy chất lượng về cuối

- Rất nhiều story “code complete” nhưng **không đạt DoD**.
- Một Sprint thường kết thúc bằng hàng đợi kiểm thử lớn.
- Hệ thống chỉ kiểm thử tích hợp khi gộp nhiều thay đổi.
- Mọi lỗi được gọi là “hạng mục mới” để giữ báo cáo Done đẹp.
- Những kiểm tra bảo mật bắt buộc bị tắt để pipeline nhanh hơn.
- Không có ai chịu trách nhiệm phục hồi khi phát hành lỗi.

**Đừng dùng metrics để hợp thức hóa việc giảm chất lượng.** Nếu tăng tốc chỉ bằng cách chuyển kiểm thử, sửa lỗi hoặc xử lý sự cố sang tương lai, đội đang **dời chi phí**, không nhất thiết giảm chi phí.

## 6. Độ tin cậy vận hành: SLI, SLO và SLA

Khi phần mềm được sử dụng thật, chất lượng còn thể hiện qua **khả năng đáp ứng ổn định của dịch vụ**.

- **SLI (Service Level Indicator):** Chỉ số đo một đặc tính thực tế của dịch vụ, ví dụ tỷ lệ yêu cầu lưu tiến độ hợp lệ thành công trong ngưỡng thời gian.
- **SLO (Service Level Objective):** Mục tiêu mong muốn cho SLI trong cửa sổ xác định, ví dụ “99,9% yêu cầu hợp lệ hoàn tất trong điều kiện định nghĩa qua 30 ngày”.
- **SLA (Service Level Agreement):** Thỏa thuận về mức dịch vụ và những cam kết/hệ quả có liên quan. SLA **không đơn giản là cách viết khác của SLO**.

### Chọn SLI gắn với trải nghiệm người học

| Đặc tính | SLI gợi ý | Vấn đề đo |
| --- | --- | --- |
| **Availability** | Tỷ lệ yêu cầu hợp lệ có phản hồi chức năng thành công | Thế nào được tính “hợp lệ” và “thành công”? |
| **Latency** | Tỷ lệ yêu cầu đọc tiến độ hoàn tất dưới ngưỡng đã định | Độ trễ p50 khác p95/p99 |
| **Correctness** | Tỷ lệ khôi phục khớp tiến độ được xác nhận | Cần nguồn sự thật và cách xác minh |
| **Durability** | Tỷ lệ dữ liệu đã xác nhận được giữ đúng sau chu kỳ sử dụng | Khó suy ra từ HTTP 200 |
| **Freshness** | Độ trễ cập nhật tiến độ giữa các thành phần theo quy tắc | Mục tiêu khác nhau giữa một thiết bị và đa thiết bị |

**Không lấy “API trả HTTP 200” làm định nghĩa thành công** khi hợp đồng thực chỉ xác nhận đã nhận yêu cầu mà chưa lưu bền vững. Cần chọn chỉ số phản ánh **những gì người dùng thật sự tin tưởng**.

### Ví dụ về SLO và error budget

Giả sử SLI là **tỷ lệ thời gian dịch vụ sẵn sàng** và mục tiêu là **99,9% trong một cửa sổ 30 ngày liên tục**, với cách đo downtime đã được định nghĩa. Ngân sách không sẵn sàng tương đương:

\[
30\times24\times60\times(1-0{,}999)
=43{,}2\text{ phút}.
\]

Đây là **phép minh họa theo thời lượng**, không tự áp dụng cho mọi SLO. Với SLI dựa trên **số yêu cầu thành công**, error budget được tính trên **tổng yêu cầu đủ điều kiện**, không thể đổi trực tiếp thành số phút nếu không có giả định bổ sung.

### Error budget không phải giấy phép làm hỏng dữ liệu

Error budget có thể giúp đội cân bằng **tốc độ thay đổi và độ tin cậy**, nhưng không thay trách nhiệm bảo vệ dữ liệu, quyền truy cập hoặc quy định bắt buộc. Một sự cố rò rỉ dữ liệu **không được biện minh** vì “vẫn còn ngân sách lỗi”.

### Khi SLO liên tục không đạt

Nhóm có thể cân nhắc:

1. Điều tra nguồn sự cố và mức độ ảnh hưởng người dùng.
2. Ưu tiên sửa nguyên nhân lặp lại, độ tin cậy và khả năng phát hiện.
3. Điều chỉnh nhịp phát hành rủi ro cao theo chính sách.
4. Cải thiện test, rollback/roll-forward và phương án phục hồi.
5. Xem SLO có phản ánh đúng trải nghiệm hay cần định nghĩa lại với lý do minh bạch.

Không nên tự hạ mục tiêu ngay sau khi hụt SLO chỉ để báo cáo đạt.

## 7. Change failure và khả năng phục hồi

Một mặt quan trọng của nhịp phát hành là **thay đổi gây sự cố bao nhiêu và nhóm phục hồi thế nào**.

### Những thước đo gợi ý

| Tín hiệu | Câu hỏi | Giới hạn diễn giải |
| --- | --- | --- |
| **Deployment frequency** | Nhóm đưa thay đổi tới môi trường đích thường xuyên ra sao? | Không tự chứng minh giá trị hoặc an toàn |
| **Lead time for changes** | Từ mốc thay đổi mã đã thống nhất tới production mất bao lâu? | Mốc bắt đầu/kết thúc cần nhất quán |
| **Change failure rate** | Bao nhiêu thay đổi/đợt triển khai gây suy giảm dịch vụ theo quy ước? | Phụ thuộc cách quy trách nhiệm sự cố |
| **Failed deployment recovery time** | Sau triển khai lỗi, cần bao lâu để phục hồi theo điều kiện xác định? | Cửa sổ đo, điểm bắt đầu và mức sự cố cần rõ |
| **Incident frequency/severity** | Những sự cố nào ảnh hưởng người dùng và ở mức nào? | Nhiều báo cáo hơn có thể do phát hiện tốt hơn |
| **Rework/recovery burden** | Bao nhiêu năng lực bị chiếm bởi sửa lỗi và phục hồi? | Không phạt người báo lỗi hoặc tham gia ứng cứu |

Các chỉ số trên có điểm tương đồng với cách đánh giá năng lực giao phần mềm trong cộng đồng DevOps/DORA, nhưng **không nên tự xem một nhóm số là thước đo duy nhất của hiệu suất đội**, cũng không đồng nhất tất cả định nghĩa giữa những phiên bản nghiên cứu hoặc tổ chức khác nhau.

### Ví dụ tỷ lệ triển khai gây sự cố

Giả sử trong một kỳ có **30 lượt triển khai đủ điều kiện**, và **6 lượt** được xác minh gây suy giảm dịch vụ cần xử lý theo định nghĩa đã thống nhất:

\[
\text{Change failure rate}
=\frac{6}{30}\times100\% = 20\%.
\]

Nếu nhóm **chia một lượt triển khai lớn thành nhiều lượt nhỏ** nhưng thay đổi cách đếm “đợt triển khai” hoặc “thất bại”, phép so sánh với kỳ trước có thể không công bằng. Một sự cố có nhiều thay đổi liên quan cũng cần quy tắc quy thuộc minh bạch.

### Thời gian phục hồi: trung bình không nói hết mọi thứ

Giả sử thời gian khôi phục bốn sự cố được xác định lần lượt là **10, 15, 20 và 195 phút**:

- **Mean** = (10 + 15 + 20 + 195) / 4 = **60 phút**.
- **Median** = (15 + 20) / 2 = **17,5 phút**.
- Sự cố dài nhất kéo **195 phút** và có thể gây ảnh hưởng lớn.

Báo cáo chỉ “trung bình 60 phút” có thể che việc đa số sự cố khôi phục nhanh nhưng một sự cố rất dài; báo cáo chỉ median lại có thể che **đuôi rủi ro nghiêm trọng**. Nên xem mức độ ảnh hưởng, phân phối và trường hợp ngoại lệ, không chỉ một số.

### Sau sự cố: học để ngăn lặp lại

Các câu hỏi hữu ích cho post-incident review:

- Người dùng thực sự bị ảnh hưởng thế nào, trong bao lâu?
- Tín hiệu nào phát hiện sự cố đầu tiên? Có bị chậm cảnh báo không?
- Những điều kiện kỹ thuật và tổ chức nào cùng tạo ra sự cố?
- Có thể **giảm xác suất lặp lại hoặc giảm thời gian phục hồi** bằng kiểm thử, cảnh báo, thay đổi quy trình?
- Ai chịu trách nhiệm thực hiện các cải tiến đã chọn và khi nào xem lại?

Một cuộc phân tích **không đổ lỗi cá nhân** giúp tăng khả năng báo cáo trung thực. Nếu việc báo sự cố bị dùng để trừng phạt, số sự cố ghi nhận giảm có thể phản ánh **giấu lỗi**, không phải chất lượng tốt hơn.

## 8. Dòng công việc: throughput, WIP, cycle time và Work Item Age

Chất lượng khó bền vững nếu đội không nhìn được **cách công việc di chuyển qua hệ thống**. Kanban dùng một số phép đo dòng công việc rất hữu ích.

### Bốn đại lượng cơ bản

| Đại lượng | Một định nghĩa thực hành | Cách dùng |
| --- | --- | --- |
| **WIP (Work in Progress)** | Số hạng mục đã bắt đầu nhưng chưa hoàn thành theo ranh giới workflow | Xem tồn kho, hàng chờ và quá tải |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng thời gian | Quan sát năng lực hoàn tất |
| **Cycle time** | Thời gian từ khi hạng mục bắt đầu xử lý tới khi hoàn thành theo workflow | Xem tốc độ luồng và độ biến thiên |
| **Work Item Age** | Thời gian một hạng mục đang dở đã tồn tại kể từ mốc bắt đầu | Phát hiện việc mắc kẹt **trước khi** nó hoàn thành |

### Ranh giới phải được thống nhất

Ví dụ một đội định nghĩa **Started** là lúc kéo user story vào “Đang phát triển” và **Finished** là lúc story đáp ứng DoD. Đội khác định nghĩa Finished là **đã phát hành**. Hai cycle time này **không cùng nghĩa**.

Thời gian nhận yêu cầu tới khi giao phần mềm thường được gọi là **lead time** theo một quy ước; thời gian từ lúc bắt đầu xử lý tới Done là **cycle time**. Cần nêu mốc trong báo cáo, vì thuật ngữ và biên đo có thể khác giữa các công cụ.

### Ví dụ hạng mục hoàn thành

Trong một tuần nhóm hoàn tất 5 story, có cycle time theo **ngày làm việc** lần lượt:

~~~text
Story A: 2 ngày
Story B: 3 ngày
Story C: 3 ngày
Story D: 5 ngày
Story E: 12 ngày
~~~

- **Throughput** = 5 story/tuần.
- **Cycle time trung bình** = (2 + 3 + 3 + 5 + 12) / 5 = **5 ngày**.
- **Cycle time trung vị (median)** = **3 ngày**.
- Một story mất **12 ngày**; nếu chỉ nhìn median, việc bị chặn lâu này dễ biến mất khỏi cuộc thảo luận.

Chỉ năm quan sát **không đủ** để thiết lập một mức dự báo ổn định. Cần nhìn nhiều hạng mục cùng loại, điều kiện làm việc và phân phối theo thời gian.

### Vì sao Work Item Age rất quan trọng?

Một story bị kẹt 15 ngày nhưng chưa Done sẽ **không xuất hiện trong dữ liệu cycle time của những story đã hoàn thành**. Nếu chỉ báo cáo “cycle time trung bình của story hoàn thành giảm”, đội có thể bỏ qua nút thắt đang tăng lên.

Hãy nhìn **Work Item Age của những việc đang mở**, cùng trạng thái blocked và hàng đợi; đây là tín hiệu **dẫn trước** để hỗ trợ việc đang gặp vấn đề.

## 9. Độ ổn định khác tốc độ trung bình

Một đội có cycle time trung bình 5 ngày nhưng lúc thì 1 ngày, lúc thì 30 ngày sẽ khó dự báo hơn đội có phần lớn hạng mục tương đương hoàn thành trong khoảng ổn định.

### Các cách nhìn phân phối

- **Median (p50):** Khoảng một nửa quan sát không vượt mức này, theo phương pháp tính percentile.
- **p85/p95:** Cho thấy các mức thời gian ở phần đuôi, hữu ích để hiểu mức chậm đáng quan tâm.
- **Biểu đồ tần suất/scatterplot:** Cho thấy mức trải rộng và trường hợp bất thường.
- **Dữ liệu theo thời gian:** Giúp thấy xu hướng mới hoặc sự thay đổi sau một thử nghiệm cải tiến.

Không có percentile nào là **chuẩn bắt buộc cho mọi đội**. Quan trọng là chọn mức phù hợp mục tiêu dự báo và định nghĩa rõ dữ liệu quan sát.

### SLE (Service Level Expectation) trong Kanban

**SLE** là kỳ vọng dự báo về thời gian một hạng mục có thể đi qua workflow, thường thể hiện bằng **một khoảng thời gian và xác suất**.

Ví dụ:

> “Với các user story tương tự đã hoàn thành theo workflow hiện tại, khoảng **85% hoàn thành trong 10 ngày làm việc hoặc ít hơn**.”

Đây là **phát biểu lịch sử có điều kiện**, không phải lời hứa “mọi story xong trong 10 ngày” hoặc SLO kỹ thuật của dịch vụ. Cần chỉ rõ loại việc, ranh giới, mẫu quan sát, độ ổn định và thời điểm đo. Một SLE có thể dùng để đặt dấu hiệu cảnh báo sớm khi **Work Item Age tiệm cận hoặc vượt mốc**.

### Độ biến thiên từ đâu tới?

| Nguyên nhân có thể | Dấu hiệu | Gợi ý kiểm tra |
| --- | --- | --- |
| Story quá lớn hoặc phụ thuộc nhiều nơi | Một số story kéo dài bất thường | Chia lát cắt dọc, làm rõ rủi ro |
| Review/test là nút thắt | Tuổi thẻ tăng trong cột chờ | Giới hạn WIP, phối hợp và năng lực bước sau |
| Công việc khẩn chen thường xuyên | Hạng mục thường bị dừng giữa chừng | Chính sách ưu tiên và capacity buffer |
| Môi trường/đối tác khó dự báo | Nhiều thời gian blocked | Nhìn ranh giới quyết định, tránh giấu thời gian chờ |
| Thiếu kiểm thử/CI | Sửa lỗi tích hợp lâu | Cải thiện phản hồi kỹ thuật |
| Cách tách ticket thay đổi | Cycle time giảm đột ngột nhưng outcome không đổi | Kiểm tra đơn vị đo và giá trị |

**Ổn định không có nghĩa loại bỏ mọi biến động**. Phần mềm có loại công việc khẩn, nghiên cứu, thay đổi nền tảng và yêu cầu mới. Mục tiêu là **hiểu biến động, giảm biến động gây hại và dự báo với độ tin cậy trung thực**.

## 10. Little's Law: quan hệ giữa WIP, throughput và cycle time

Đối với hệ thống dòng công việc **tương đối ổn định, có ranh giới và đơn vị đo nhất quán**, định luật Little cho quan hệ trung bình:

\[
\text{WIP trung bình}
= \text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Suy ra:

\[
\text{Cycle time trung bình}
=\frac{\text{WIP trung bình}}{\text{Throughput trung bình}}.
\]

**Ví dụ giả định:** Nếu trung bình có 12 hạng mục đang thực hiện và throughput trung bình là 3 hạng mục/tuần, quan hệ tương ứng với cycle time trung bình **4 tuần**.

Nếu WIP trung bình giảm còn 6 **và throughput vẫn giữ 3/tuần**, cycle time tương ứng khoảng **2 tuần**.

**Cảnh báo:** Không được hứa rằng chỉ đặt WIP limit 6 thì mọi story hoàn thành sau 2 tuần. Việc giảm WIP có thể ảnh hưởng throughput, hệ thống có thể không ổn định và các hạng mục có độ phức tạp khác nhau. Định luật Little mô tả **quan hệ trung bình có điều kiện**, không dự báo chắc chắn thời gian của một hạng mục cụ thể.

### Khi số liệu không thỏa điều kiện đo

- WIP đang **tăng liên tục** mà throughput không theo kịp.
- Hạng mục bị hủy, chia, gộp hoặc chuyển trạng thái mà không có quy tắc ghi nhận.
- WIP bao gồm cả task kỹ thuật nhưng throughput chỉ đếm user story.
- Cycle time đo ngày làm việc, throughput lại tính số hạng mục mỗi **ngày lịch** mà chưa quy đổi phù hợp.
- Thời gian quan sát quá ngắn hoặc workflow đổi liên tục.

Trước khi dùng công thức để dự báo, cần **sửa định nghĩa và kiểm tra trạng thái hệ thống**.

## 11. Tính dự báo: đo sai lệch có nguyên nhân, không ép cam kết tuyệt đối

Người liên quan cần biết **khi nào có thể nhận giá trị**. Agile không loại bỏ dự báo; Agile khuyến khích **dự báo dựa trên bằng chứng và cập nhật khi điều kiện thay đổi**.

### Một số tín hiệu

| Tín hiệu | Câu hỏi | Rủi ro diễn giải |
| --- | --- | --- |
| **Tỷ lệ hoàn thành Sprint Goal** | Sprint có đạt mục tiêu có giá trị không? | Goal khác độ khó; không biến thành KPI cá nhân |
| **Throughput theo thời gian** | Năng lực hoàn tất có biến động lớn? | Đếm ticket không nhất quán gây méo |
| **Cycle time distribution** | Có thể dự báo thời gian với mức tin cậy nào? | Không lấy trung bình để cam kết mọi hạng mục |
| **Work Item Age / blocked time** | Việc nào có nguy cơ chậm trước khi Done? | Cần can thiệp đúng nguồn chờ |
| **Forecast ranges** | Với backlog hiện tại, mốc giao có thể nằm trong khoảng nào? | Phụ thuộc thay đổi phạm vi, throughput và rủi ro |

### Sprint Goal khác “đúng 100% kế hoạch task”

Một Scrum Team có thể đạt Sprint Goal dù phải điều chỉnh các task trong Sprint, hoặc hoàn tất nhiều task nhưng **không tạo được Increment đáp ứng DoD cho mục tiêu đã chọn**. Vì vậy, đánh giá chỉ bằng tỷ lệ ticket đã check không phản ánh đầy đủ kết quả.

**Không nên định nghĩa “Sprint thành công” là không thay đổi bất kỳ kế hoạch nào.** Kiểm tra và thích ứng là một phần của Agile.

### Dự báo bằng dải thay vì một ngày chắc chắn

Ví dụ:

> “Với throughput và độ biến thiên gần đây của cùng loại công việc, nhóm dự báo phạm vi ưu tiên này có thể hoàn tất trong một khoảng thời gian; dải dự báo sẽ được cập nhật khi phát sinh phụ thuộc hoặc thay đổi phạm vi.”

Nhóm có thể dùng **dữ liệu lịch sử, scenario analysis hoặc Monte Carlo simulation** khi đủ dữ liệu và kỹ năng. Một mô phỏng không làm bất định biến mất; nó chỉ giúp **biểu diễn những giả định đã đưa vào**.

### Những điều cần ghi khi dự báo

- Phạm vi tính năng là gì, ranh giới Done là gì?
- Công việc mới có thể được thêm/xóa không?
- Lấy throughput của giai đoạn nào và loại công việc nào?
- Có sự cố, kỳ nghỉ, phụ thuộc, on-call hoặc chuyển giao lớn?
- Dự báo là **khoảng với điều kiện**, hay một cam kết đã bao gồm phần dự phòng và rủi ro?

Tránh đưa ra mốc chính xác giả tạo chỉ vì bảng tính cho một ngày cụ thể.

## 12. Velocity và story points: hữu ích trong phạm vi nào?

**Story points** là đơn vị ước lượng tương đối mà một số đội sử dụng để trao đổi về quy mô, độ phức tạp và bất định của Product Backlog Item. **Velocity** thường là tổng điểm ước lượng của các hạng mục hoàn tất theo quy tắc của đội trong một Sprint.

Chúng **không phải đơn vị đo giá trị**, **không đo số giờ lao động thực**, **không phải thước đo năng suất của từng Developer**, và không có một quy ước điểm chung giữa các đội.

### Ví dụ

Một đội ước lượng và hoàn tất 24 points ở Sprint trước, 31 points ở Sprint sau. Có thể kết luận **tổng điểm theo quy ước nội bộ tăng**, nhưng chưa thể kết luận năng suất tăng khoảng 29%.

Vì sao?

- Đội có thể thay cách chia PBI hoặc thay cách ước lượng.
- Có thể có một thay đổi lớn **chưa đạt DoD** và không được tính.
- Sprint thứ hai có thể có lỗi nhiều hơn.
- Các PBI khác giá trị với người dùng.
- Tăng points không đo được sự phụ thuộc, hỗ trợ hoặc thời gian chờ.

### Khi velocity có thể giúp ích

- Tham khảo **năng lực lịch sử trong cùng một đội** nếu cách ước lượng tương đối nhất quán.
- Hỗ trợ trao đổi về số lượng PBI có thể chọn để hướng tới Sprint Goal.
- Phát hiện biến động lớn cần thảo luận về **nguyên nhân**: thiếu rõ yêu cầu, on-call, kỹ thuật, phụ thuộc, nghỉ phép.

### Những việc không nên làm

- So velocity đội A với đội B để xếp hạng.
- Đặt chỉ tiêu bắt buộc tăng story points mỗi Sprint.
- Gắn thưởng/phạt cá nhân với điểm hoàn thành.
- Tính hạng mục chưa đạt DoD như đã giao chỉ vì gần xong.
- Dùng velocity thay thế outcome, chất lượng hoặc khả năng duy trì nhịp.

**Nếu đội không dùng story points**, họ vẫn có thể quản lý backlog và dự báo bằng dữ liệu throughput, phân phối cycle time và hiểu biết về phạm vi. Không có yêu cầu mọi nhóm Agile bắt buộc phải dùng velocity.

## 13. Nhịp làm việc bền vững là gì?

**Nhịp làm việc bền vững (sustainable pace)** là khả năng đội duy trì việc cung cấp giá trị và cải tiến qua thời gian dài **mà không liên tục dựa vào làm ngoài giờ, thiếu phục hồi, chuyển ngữ cảnh quá mức hoặc những người “cứu dự án”**.

Một Sprint có thể đạt mục tiêu nhờ một tuần làm rất căng; điều này **chưa chứng minh** cách làm ấy sẽ tiếp tục hiệu quả trong nhiều tháng.

### Bền vững không đồng nghĩa lúc nào cũng thư thả

Trong vận hành phần mềm, sự cố khẩn cấp và giai đoạn cần tập trung cao có thể xảy ra. Vấn đề là **tần suất, sự công bằng, cơ chế bù đắp và khả năng quay lại nhịp bình thường**.

| Dấu hiệu đáng quan sát | Câu hỏi nhóm có thể đặt |
| --- | --- |
| Làm thêm giờ lặp lại | Khối lượng đã vượt năng lực thường xuyên hay chỉ là ngoại lệ? |
| Lịch trực/on-call quá nặng | Có đủ người chia sẻ trách nhiệm, nghỉ phục hồi và công cụ hỗ trợ? |
| Mở quá nhiều hạng mục | WIP cao có làm tăng chuyển ngữ cảnh và thời gian chờ? |
| Nhiều yêu cầu khẩn không được phân loại | Có chính sách xử lý interrupt và trade-off minh bạch? |
| Công việc liên tục đổi ưu tiên | Nhóm có thể hoàn tất việc đang làm hay chỉ phản ứng? |
| Hệ thống hay xảy ra sự cố ngoài giờ | Có đầu tư phòng ngừa, quan sát và giảm nguyên nhân lặp? |
| Kiến thức chỉ tập trung vào một người | Khi họ vắng mặt, công việc có bị chặn không? |
| Ít thời gian học và cải tiến | Nợ kỹ thuật và lỗi lặp có làm tương lai đắt đỏ hơn? |

### Ba cách nhìn nhịp bền vững

1. **Năng lực:** Công việc được chọn có phù hợp năng lực và rủi ro không?
2. **Cách tổ chức:** WIP, phụ thuộc, việc khẩn và lịch trực có được quản lý không?
3. **Trải nghiệm người làm việc:** Thành viên có thể lên tiếng về quá tải, nghỉ cần thiết và đề xuất cải tiến mà không bị gây bất lợi không?

Không dùng các phép đo nhịp làm việc để **chẩn đoán tình trạng sức khỏe của nhân viên**, suy đoán động lực hay kiểm soát đời tư. Những điều này vượt ra ngoài mục tiêu đo hệ thống công việc.

## 14. Chỉ số và tín hiệu cho một nhịp làm việc bền vững

Chất lượng dữ liệu ở nhóm này rất nhạy cảm: **mục tiêu là cải thiện hệ thống tổ chức công việc, không theo dõi từng cá nhân**.

| Tín hiệu | Điều có thể học | Cách sử dụng có trách nhiệm |
| --- | --- | --- |
| **Giờ làm thêm ngoài kế hoạch** | Có liên tục cần thêm thời gian để hoàn tất cam kết? | Xem tổng thể, bối cảnh và tính tự nguyện; không đếm giờ để chấm năng suất |
| **Tần suất xử lý sự cố ngoài giờ** | Vận hành đang lấy đi thời gian phục hồi? | Xem severity, phân bổ trực, năng lực tự động hóa |
| **Số lần bị gián đoạn** | Việc khẩn có làm đứt dòng công việc? | Phân biệt sự cố thật với yêu cầu có thể xếp thứ tự |
| **WIP, Work Item Age** | Nhóm có mở quá nhiều việc và chờ lâu? | Dùng ở mức workflow, không giám sát tab cá nhân |
| **Thời gian phản hồi review** | Có bị nghẽn do thiếu năng lực hoặc lịch làm việc? | Không bắt phản hồi mọi PR ngoài giờ |
| **Năng lực xử lý công việc không lên kế hoạch** | Interrupt có thường xuyên vượt phần dự phòng? | Đưa vào planning thay vì xem là lỗi cá nhân |
| **Phản hồi đội về khả năng tập trung và phục hồi** | Nhịp làm việc có đang gây áp lực khó duy trì? | Thu thập tự nguyện, tổng hợp phù hợp, bảo vệ riêng tư |
| **Khả năng thay thế/tiếp nối** | Có module chỉ một người xử lý được? | Xây kiểm thử, tài liệu và ghép cặp có chủ đích |
| **Thời gian dành cho cải tiến hệ thống** | Đội có giải quyết nguyên nhân gốc của gián đoạn? | Đánh giá tác dụng thực, không chạy KPI % cố định |

### Dùng khảo sát ngắn mà không biến thành công cụ giám sát

Ví dụ câu hỏi **tự nguyện**, theo nhóm và không yêu cầu giải thích thông tin nhạy cảm:

> “Trong hai tuần gần đây, mức độ có thể tập trung hoàn thành một hạng mục mà không bị ngắt quãng quá mức là bao nhiêu?”

> “Nhịp công việc hiện tại có thể tiếp tục trong vài Sprint nữa với nguồn lực và thời gian nghỉ như hiện nay không?”

> “Rào cản quy trình nào nếu được sửa sẽ giúp nhóm làm việc đều hơn?”

Không nên thu thập hoặc công bố câu trả lời ở một nhóm quá nhỏ khiến người tham gia dễ bị nhận diện. Nếu không thể bảo đảm tính riêng tư, nên chọn **hội thoại tự nguyện và cải tiến quy trình** thay vì làm dashboard cá nhân.

### Đừng biến “sức khỏe đội” thành một điểm số bắt buộc

Một người có thể không muốn trả lời. Một đội có tỷ lệ phản hồi cao chưa chắc có ít vấn đề; một đội ít phản hồi có thể đang lo ngại cách sử dụng kết quả. Dữ liệu tự báo **có thiên lệch chọn mẫu và bối cảnh**, nên dùng để mở cuộc trao đổi, không chấm điểm đạo đức hay hiệu suất từng người.

## 15. Tại sao mức sử dụng 100% thường làm dòng công việc khó dự báo?

Nếu một bước xử lý gần như luôn kín chỗ, chỉ cần yêu cầu phát sinh hoặc một lỗi nhỏ đã có thể tạo **hàng đợi kéo dài**. Trong những hệ thống có độ biến thiên, việc tối đa hóa mức bận của từng cá nhân **không đồng nghĩa tối thiểu hóa thời gian giao giá trị**.

### Ví dụ review code

Một đội có duy nhất một người có thể phê duyệt phần dữ liệu quan trọng. Người đó đã được xếp lịch kín cả ngày cho tính năng mới. Khi năm Pull Request cùng đến, mỗi PR phải chờ.

Nhóm có thể tăng số giờ làm của người ấy, nhưng thường đáng xem xét:

- Tách PR nhỏ hơn và review sớm hơn.
- Truyền hiểu biết để thêm người có năng lực review với quyền phù hợp.
- Dành một phần năng lực cho việc xử lý hàng đợi và sự cố.
- Giới hạn WIP ở bước phát triển trước nút thắt.
- Cải thiện kiểm thử và tiêu chuẩn mã để phản hồi review nhanh hơn.

### Buffer không phải “thời gian vô ích”

Một mức **năng lực dự phòng có chủ đích** cho sự cố, học hỏi, refactoring, hỗ trợ đồng nghiệp hoặc phản hồi người dùng có thể giúp đội giữ nhịp khi công việc biến động. Tỷ lệ dự phòng phù hợp phụ thuộc loại sản phẩm, độ ổn định và mức vận hành; không có con số bắt buộc áp dụng cho mọi đội.

**Cảnh báo:** Không dùng lý thuyết hàng đợi để khẳng định một mức utilization tối ưu tuyệt đối mà chưa có số liệu arrival rate, service rate và phân phối phù hợp. Bài học thực dụng là **giảm sự quá tải tại bước nghẽn và quan sát cả thời gian chờ**.

## 16. Quản lý công việc khẩn và gián đoạn trong nhịp bền vững

Công việc ngoài kế hoạch gồm:

- Sự cố sản xuất gây ảnh hưởng người dùng.
- Lỗ hổng bảo mật cần xử lý theo mức độ nghiêm trọng.
- Lỗi chất lượng đã được xác nhận.
- Yêu cầu làm rõ nghiệp vụ gấp để tránh quyết định sai.
- Yêu cầu “khẩn” từ stakeholder nhưng chưa có bằng chứng về thời hạn hoặc rủi ro.

Không nên gom tất cả thành một nhóm **P0**.

### Một chính sách dòng công việc minh bạch

~~~mermaid
flowchart TD
    A["Yêu cầu chen ngang"] --> B["Đánh giá hậu quả và mức khẩn"]
    B --> C{"Sự cố/đe dọa cần xử lý ngay?"}
    C -->|Có| D["Kích hoạt quy trình sự cố/khẩn cấp"]
    C -->|Không| E["Product Owner và nhóm xem thứ tự ưu tiên"]
    D --> F["Dừng/điều chỉnh công việc khác minh bạch"]
    E --> G["Xếp vào backlog hoặc bổ sung theo năng lực"]
    F --> H["Khắc phục, quan sát, học nguyên nhân"]
    G --> I["Hoàn tất công việc theo workflow"]
    H --> J["Điều chỉnh chính sách và năng lực dự phòng"]
    I --> J
~~~

### Các chỉ số hữu ích

- Tỷ lệ **công việc không lên kế hoạch** trong cùng kỳ với năng lực đã cam kết.
- Số sự cố có mức nghiêm trọng khác nhau, không chỉ số ticket.
- Thời gian hạng mục chính bị **tạm dừng** do gián đoạn.
- Thời gian phục hồi và số lần tái diễn cùng nguyên nhân.
- Mức độ phân bổ trực/cứu sự cố, không phụ thuộc một người.

Không nên chỉ tính “giờ support” rồi coi chúng là thời gian không tạo giá trị. **Giữ hệ thống an toàn và đáng tin cậy là công việc có ích**, nhưng lỗi lặp lại cần đầu tư giảm nguyên nhân thay vì liên tục chữa cháy.

## 17. Chất lượng thiết kế và nợ kỹ thuật dưới góc nhìn số liệu

**Nợ kỹ thuật (technical debt)** mô tả một số quyết định hoặc thiếu sót kỹ thuật có thể làm chi phí thay đổi trong tương lai tăng lên. Không phải mọi đoạn mã cũ, mọi thư viện cũ hoặc mọi quyết định đơn giản đều là nợ kỹ thuật xấu.

### Những câu hỏi thực dụng

- Một lỗi nhỏ có mất nhiều ngày vì mã không có kiểm thử hoặc phụ thuộc quá nhiều nơi?
- Có phần code quan trọng chỉ một người hiểu và không ai khác dám sửa?
- Build, test hoặc triển khai có mất thời gian đến mức ngăn tích hợp thường xuyên?
- Một bước xác nhận lưu tiến độ có nhiều bản sao quy tắc ở UI và backend?
- Hệ thống có sự cố cùng nguyên nhân lặp lại nhưng chưa có thời gian phòng ngừa?
- Có khả năng phát hiện sớm và phục hồi sau thay đổi hay không?

### Những tín hiệu thay cho “đếm nợ kỹ thuật”

| Tín hiệu | Có thể nói điều gì? | Không nên suy luận |
| --- | --- | --- |
| Thời gian sửa lỗi lặp lại | Phần mềm khó thay đổi hoặc điều tra | Mọi giờ sửa lỗi đều do thiết kế kém |
| Tỷ lệ lỗi hồi quy | Thay đổi phá hành vi cũ | Chỉ cần tăng code coverage là đủ |
| Thời gian pipeline | Phản hồi kỹ thuật chậm | Chạy nhanh hơn bằng cách bỏ kiểm thử |
| Phụ thuộc một chuyên gia | Kiến thức tập trung làm tăng rủi ro | Cá nhân ấy là nguyên nhân có lỗi |
| Lỗi sự cố tái diễn | Các biện pháp phòng ngừa chưa hiệu quả | Chỉ cần có postmortem là vấn đề đã giải quyết |
| Cycle time phần thay đổi tương tự | Chi phí thay đổi tăng | Mọi hạng mục đều có độ phức tạp như nhau |

### Refactoring và cải tiến hạ tầng là đầu tư giá trị

Một Sprint hoàn thành ít story hơn vì nhóm sửa một rào cản kiểm thử quan trọng có thể là **khoản đầu tư hợp lý** nếu nó giảm lỗi và hàng chờ ở các Sprint sau.

Tuy nhiên, “làm sạch mã” không tự được miễn đánh giá: đội nên nêu rõ **vấn đề, rủi ro, cách cải thiện và tín hiệu kiểm chứng**. Tránh biến cải tiến kỹ thuật thành dự án vô hạn, hoặc ép mọi giờ phải liên kết trực tiếp với một màn hình người dùng.

## 18. Chọn baseline và so sánh công bằng

**Baseline** là hình ảnh ban đầu đủ tin cậy của hệ thống trước khi thử một thay đổi. Một cải tiến có ý nghĩa chỉ có thể được diễn giải khi đội biết **đã thay đổi cái gì, trong bối cảnh nào**.

### Ví dụ một thử nghiệm giảm WIP

Nhóm nghi ngờ mở nhiều story cùng lúc khiến review/test bị nghẽn. Họ dự định:

1. Quan sát vài tuần trước thay đổi, ghi WIP và Work Item Age.
2. Đặt WIP limit ở bước phù hợp, ưu tiên giúp việc gần Done hoàn tất.
3. Theo dõi throughput, phân phối cycle time và lượng blocked work.
4. Kiểm tra lỗi sau bàn giao và khối lượng trực ngoài giờ để tránh giảm thời gian bằng cách chuyển rủi ro.
5. Xem lại sau thời gian đủ để nhiều hạng mục đi qua workflow mới.

### Những điều làm so sánh mất ý nghĩa

| Thay đổi xảy ra cùng lúc | Nguy cơ |
| --- | --- |
| Story được tách nhỏ hơn rất nhiều | Throughput tăng dù giá trị tương đương |
| Cột Done đổi từ “đã code” sang “đã phát hành” | Cycle time không còn cùng ranh giới |
| Một giai đoạn có nhiều kỳ nghỉ hơn | Năng lực làm việc và thời gian đo khác |
| Nền tảng xảy ra sự cố lớn | Gián đoạn làm biến động dòng công việc |
| Nhóm chuyển từ tính năng nhỏ sang migration dữ liệu | Hai tập công việc khác độ phức tạp |
| Công cụ analytics thay đổi cách đếm | Chênh lệch có thể do instrumentation |
| Người dùng đột nhiên tăng mạnh | Số bug/incident thô có thể tăng cùng mức tiếp xúc |

**Không có nghĩa phải bỏ dữ liệu khi có biến động.** Hãy ghi điều kiện, phân loại công việc hợp lý, phân tích tình huống và tránh tuyên bố quan hệ nhân quả quá mức.

### Khi dữ liệu quá ít

Một đội chỉ hoàn thành bốn PBI trong Sprint thì một hạng mục chậm có thể làm trung bình thay đổi rất lớn. Thay vì kết luận “Sprint này kém năng suất”, nên:

- Xem từng hạng mục, nguyên nhân chậm, phụ thuộc và loại việc.
- Dùng dữ liệu nhiều kỳ và phân phối thay vì một điểm trung bình.
- Xem thêm tín hiệu dẫn trước như Work Item Age và WIP.
- Kết hợp giải thích của người trực tiếp làm việc.

## 19. Phân biệt chỉ số dẫn trước và chỉ số kết quả

**Leading indicators** có thể báo sớm nguy cơ, còn **lagging indicators** cho thấy kết quả đã xảy ra. Không có phân loại tuyệt đối cho mọi bối cảnh; cùng một phép đo có thể đóng vai trò khác nhau theo câu hỏi.

| Câu hỏi | Tín hiệu sớm thường hữu ích | Kết quả nên kiểm tra sau |
| --- | --- | --- |
| Chất lượng phát hành | Tình trạng CI/test, tuổi PR, blocker | Lỗi sau phát hành, sự cố và phản hồi người dùng |
| Thời gian giao sản phẩm | WIP, Work Item Age, hàng đợi review | Cycle time hoàn thành, throughput, time to value |
| Độ tin cậy dịch vụ | Cảnh báo SLI, error budget burn | Mức vi phạm SLO, thời gian phục hồi, ảnh hưởng người dùng |
| Nhịp làm việc bền vững | Lượng interrupt, trực ngoài giờ, tín hiệu quá tải | Tỷ lệ lỗi lặp, khả năng duy trì nhịp qua nhiều kỳ |
| Giá trị người dùng | Exposure, activation, task success sớm | Retention, completion, mức hài lòng dài hạn |

### Cảnh báo rủi ro khác kết luận thành công

Một PR đang chờ 10 ngày là **tín hiệu nên điều tra**, không phải bằng chứng người viết PR chậm. Một phần backlog có nhiều câu hỏi chưa rõ là **cơ hội làm rõ nghiệp vụ**, không nhất thiết lỗi của nhóm phát triển.

Các chỉ số dẫn trước hữu ích nhất khi nhóm **có thể hành động**: giúp review, tháo blocker, giảm WIP hoặc hỏi đúng người có thẩm quyền.

## 20. Data quality và đạo đức đo lường trong đội Agile

Chỉ số có thể được dùng tốt để cải tiến quy trình hoặc bị dùng sai để **giám sát con người**. Cần bảo vệ cả hai vấn đề: **số liệu đúng** và **cách dùng có trách nhiệm**.

### Năm vấn đề dữ liệu phổ biến

1. **Sai đơn vị:** Đếm lượt click thay vì người dùng, đếm task thay vì hạng mục có giá trị.
2. **Sai ranh giới:** Chu kỳ này Done = code complete, chu kỳ sau Done = deployed.
3. **Thiếu dữ liệu:** Một môi trường không ghi telemetry hoặc người dùng offline bị bỏ khỏi mẫu.
4. **Đếm trùng:** Retry làm một yêu cầu thành nhiều sự kiện.
5. **Đổi cách ghi:** Tool mới làm tăng số lỗi được phát hiện dù chất lượng không nhất thiết xấu đi.

### Quyền riêng tư và an toàn tâm lý

- Không lập dashboard **số giờ online, số lần gõ phím, số commit mỗi cá nhân** để đánh giá “năng suất” mà bỏ qua bối cảnh và quyền riêng tư.
- Chỉ thu thập dữ liệu cần cho mục tiêu cải tiến đã công bố; quản lý quyền truy cập và thời hạn lưu giữ.
- Khi hỏi về áp lực hoặc khả năng phục hồi, ưu tiên **tự nguyện, tổng hợp ở mức đủ an toàn**, không đòi cung cấp thông tin sức khỏe.
- Người tham gia phải có cơ hội **phản biện định nghĩa và cách sử dụng chỉ số**.
- Tránh dùng số bug báo cáo hoặc số sự cố nhận trách nhiệm để trừng phạt; điều đó khuyến khích che giấu vấn đề.

### Goodhart's Law và hậu quả khi biến chỉ số thành mục tiêu cứng

Một câu thường được dùng để nhắc về đo lường là: **khi một thước đo trở thành mục tiêu, nó có thể không còn là thước đo tốt**.

Ví dụ:

- Ép **velocity** tăng → đội có thể nâng story points.
- Ép **số bug** giảm → bug có thể bị đổi nhãn hoặc không được ghi nhận.
- Ép **cycle time** giảm → có thể chia ticket thành hạng mục rất nhỏ nhưng giá trị vẫn đến muộn.
- Ép **deployment frequency** tăng → có thể phát hành những thay đổi không mang giá trị.
- Ép **on-call incidents** giảm → có thể giảm logging thay vì giảm sự cố.

**Biện pháp:** Đặt câu hỏi giá trị trước, dùng một nhóm tín hiệu cân bằng, giữ định nghĩa ổn định và khuyến khích thảo luận lý do. Hệ chỉ số nên **phục vụ quyết định**, không thay quyết định của con người bằng một bảng xếp hạng.

## 21. Một dashboard thực dụng: ít chỉ số nhưng có đối thoại

Dashboard hữu ích không phải bảng có nhiều ô màu nhất, mà là **bản đồ các câu hỏi đội cần giải quyết tại thời điểm đó**.

### Mẫu scorecard cho một Sprint/chu kỳ đo

| Góc nhìn | Chỉ số chính hoặc câu hỏi | Điều cần thảo luận |
| --- | --- | --- |
| **Giá trị** | Người học có tiếp tục đúng tiến độ hơn trước? | Mẫu đo, hành vi, tác dụng phụ |
| **Chất lượng** | Lỗi dữ liệu nghiêm trọng, lỗi lọt sau phát hành | Nguồn lỗi, severity, khả năng khắc phục |
| **Độ tin cậy** | SLI/SLO, sự cố và phục hồi | Tác động người dùng, nguyên nhân lặp |
| **Dòng công việc** | Throughput, p50/p85 cycle time, WIP, Work Item Age | Hàng đợi, blocker, khả năng dự báo |
| **Nhịp bền vững** | Interrupt ngoài kế hoạch, gánh nặng trực, phản hồi nhóm | Năng lực, phục hồi, cải tiến |
| **Quyết định** | Một hoặc hai vấn đề quan trọng nhất cần xử lý | Chủ sở hữu, hành động và mốc xem lại |

### Những câu hỏi dành cho buổi xem lại

1. Tín hiệu nào **đáng tin và đủ dữ liệu**?
2. Điều gì **khác kỳ vọng** và tại sao?
3. Có vấn đề chất lượng hoặc an toàn **cần xử lý ngay** không?
4. Hạng mục nào đang già đi hoặc chờ tại một nút thắt?
5. Có đang dựa vào công sức ngoài giờ để giữ tiến độ không?
6. Nếu chọn **một thử nghiệm cải tiến**, đội sẽ thay đổi điều gì?
7. Ai sẽ theo dõi và khi nào đánh giá lại?

**Dashboard không cần chấm màu đỏ từng người.** Điều quan trọng là người làm công việc có thể thảo luận trung thực về hệ thống mà không sợ bị quy lỗi vì số liệu bất lợi.

## 22. Case study xuyên suốt: khi giao nhanh hơn chưa chắc làm việc tốt hơn

**Bối cảnh giả định:** Một đội phát triển nền tảng học trực tuyến có sáu Developers và làm việc với Product Owner, người kiểm thử, vận hành và stakeholder. Product Goal là giúp học viên **tiếp tục học đáng tin cậy từ tiến độ đã lưu**.

Đội đang nhận phàn nàn về lỗi mất tiến độ, PR chờ review và việc trực sự cố ngoài giờ. Báo cáo hằng Sprint chỉ nhấn mạnh số PBI hoàn tất, nên khó thấy **chất lượng, sự biến động và tính bền vững**.

### 22.1. Hiện trạng: nhiều hoạt động nhưng ít dự báo

| Hiện tượng | Điều đội đã nhận thấy | Giả thuyết cần kiểm tra |
| --- | --- | --- |
| Nhiều story được mở cùng lúc | Hơn chục hạng mục đang xử lý, một số chờ review lâu | WIP quá cao làm kéo dài thời gian bàn giao |
| Kiểm thử tích hợp diễn ra muộn | Một số lỗi chỉ lộ trước phát hành | Lô tích hợp lớn khiến sửa lỗi tốn công |
| Thường xuyên hỗ trợ sự cố ngoài giờ | Mọi người khó tập trung vào story kế tiếp | Lỗi lặp và thiếu năng lực dự phòng làm nhịp không bền |
| Chỉ một người hiểu module lưu tiến độ | Mọi thay đổi quan trọng chờ cùng chuyên gia | Phụ thuộc kiến thức là một điểm nghẽn |
| Velocity là số chính trong Review | Không rõ người học bớt mất tiến độ hay chưa | Đo output mà chưa đo outcome |

Đội quyết định không quy trách nhiệm cho một cá nhân. Họ **lập bản đồ dòng công việc và chọn tập chỉ số nhỏ** để xem nguyên nhân.

### 22.2. Chọn thước đo có ý nghĩa

Giả sử nhóm thống nhất:

- **Outcome:** Tỷ lệ người học đủ điều kiện tiếp tục đúng tiến độ đã xác nhận trong cùng cửa sổ bảy ngày.
- **Quality:** Số lỗi mức trung bình trở lên được xác nhận sau phát hành trong phạm vi tính năng tiến độ.
- **Reliability:** Số sự cố vận hành liên quan tiến độ và mức ảnh hưởng thực.
- **Flow:** Throughput cùng loại công việc, WIP trung bình, p50/p85 cycle time.
- **Sustainable pace:** Số lần cần xử lý sự cố ngoài giờ theo kỳ và phản hồi tự nguyện của đội về khả năng tập trung.

Không dùng số giờ làm cá nhân để tạo bảng xếp hạng. Đội xem **cùng nguồn dữ liệu, cùng định nghĩa và các kỳ quan sát có điều kiện tương đối tương đương**.

### 22.3. Hai kỳ quan sát giả định

Các số dưới đây hoàn toàn là **dữ liệu minh họa**, không phải kết quả nghiên cứu hay số liệu thực:

| Chỉ số | Giai đoạn A | Giai đoạn B | Câu hỏi đặt ra |
| --- | ---: | ---: | --- |
| Tỷ lệ tiếp tục thành công của cohort đủ điều kiện | 72% | 78% | Có cùng cách đo và đối tượng không? |
| Lỗi sau phát hành mức trung bình trở lên | 12 | 5 | Mức sử dụng và kênh phát hiện có tương đương không? |
| Sự cố vận hành có ảnh hưởng người học | 4 | 1 | Mức độ nghiêm trọng và nguyên nhân đã rõ chưa? |
| Throughput user story/chu kỳ | 28 | 26 | Giảm 2 story có đáng lo khi chất lượng cải thiện? |
| WIP trung bình | 16 | 10 | Có thực sự giảm tồn kho hay chỉ đổi trạng thái? |
| Cycle time p50 | 6 ngày | 5 ngày | Có thống nhất loại story và ngày đo không? |
| Cycle time p85 | 18 ngày | 12 ngày | Đuôi các story chậm đã cải thiện? |
| Lần xử lý sự cố ngoài giờ | 12 | 4 | Có giảm gánh nặng thật, hay thay đổi cách ghi? |

**Không thể kết luận “cải tiến X gây ra tất cả thay đổi”** chỉ bằng một bảng trước/sau. Giai đoạn B có thể thay đổi lượng người dùng, loại yêu cầu hoặc chính sách phát hiện lỗi. Bảng giúp đội chọn **câu hỏi cần điều tra và quyết định tiếp theo**.

### 22.4. Điều đội có thể nói một cách trung thực

> “Trong dữ liệu minh họa, WIP và p85 cycle time thấp hơn, số lỗi và trực ngoài giờ được ghi nhận giảm, còn tỷ lệ người học tiếp tục thành công cao hơn. Throughput story giảm nhẹ. Các dấu hiệu này phù hợp với một nhịp làm việc ổn định hơn, **nhưng cần kiểm tra điều kiện đo, loại công việc, mức độ sử dụng và các thay đổi đồng thời** trước khi quy kết nguyên nhân.”

Đội **không cần ép throughput từ 26 lên 30** chỉ để vượt giai đoạn A. Nếu tăng số story bằng cách bỏ kiểm thử rồi làm lỗi quay lại, kết quả sẽ xấu hơn cho người học lẫn đội.

### 22.5. Giả thuyết về những cải tiến đã góp phần tạo thay đổi

Nhóm xem lại những thay đổi quy trình:

1. **Giới hạn WIP:** Không mở thêm story khi hàng đợi review/test đang nghẽn.
2. **Chia lát cắt nhỏ:** Tập trung hoàn tất đường lưu/khôi phục end-to-end thay vì bắt đầu nhiều phần kỹ thuật.
3. **TDD/kiểm thử tích hợp sớm:** Bảo vệ trạng thái lưu, quyền và dữ liệu.
4. **Pair programming có mục tiêu:** Lan truyền hiểu biết về module tiến độ.
5. **Sửa nguyên nhân sự cố:** Không chỉ đóng ticket vận hành mà xem lại trường hợp lỗi lặp.
6. **Dự phòng năng lực:** Có chính sách phân loại việc khẩn, không coi mọi yêu cầu stakeholder là P0.

Những cải tiến này có cơ chế hợp lý, nhưng để học chính xác hơn, đội nên **theo dõi qua nhiều kỳ và cô lập những thay đổi khi có thể**, không quy công lao cho một nghi thức duy nhất.

### 22.6. Một kết quả cần cảnh giác

Giả sử đội báo số lỗi giảm nhờ **đổi nhãn ticket “bug” thành “improvement”**. Khi đó tỷ lệ lỗi thấp hơn **không phản ánh chất lượng tăng**. Hoặc đội giảm số lần trực ngoài giờ bằng cách **ngừng ghi sự cố nhỏ**; người học vẫn bị ảnh hưởng. Đây là lý do định nghĩa, động cơ và môi trường báo cáo quan trọng ngang công thức.

### 22.7. Quyết định sau case study

Đội chọn:

- Tiếp tục chính sách WIP vì Work Item Age và hàng đợi cho dấu hiệu cải thiện.
- Xác minh lại cách đếm lỗi/sự cố và bổ sung phản hồi người học.
- Ưu tiên sửa các trường hợp lưu tiến độ bị lỗi ở mạng yếu.
- Duy trì kiểm thử tích hợp và khả năng phục hồi thay vì hy sinh để đạt nhiều story hơn.
- Xem gánh nặng on-call và phân bổ kiến thức ở Retrospective.
- Cập nhật dự báo bằng **phân phối cycle time hiện tại**, không hứa mọi story xong đúng một mốc.

**Thông điệp:** Một đội Agile làm việc tốt khi **giá trị, chất lượng, thời gian giao, độ tin cậy và năng lực con người cùng được cải thiện một cách có thể duy trì**, không phải khi một chỉ số đơn lẻ tăng.

## 23. Thiết kế thử nghiệm cải tiến trong hai đến bốn Sprint

Đo lường tốt cần dẫn tới **hành động kiểm chứng được**. Một mẫu thực hành:

~~~text
VẤN ĐỀ:
  User story chờ review lâu, lỗi tích hợp đến muộn,
  nhiều lần hỗ trợ sự cố ngoài giờ.

BASELINE:
  WIP, Work Item Age, p50/p85 cycle time,
  throughput, lỗi phát hành, số sự cố và mức ảnh hưởng,
  phản hồi đội về khả năng tập trung.

GIẢ THUYẾT:
  Giảm số story mở đồng thời, review sớm hơn
  và thêm kiểm thử hồi quy cho lỗi lưu sẽ giảm hàng đợi,
  giảm sự cố lặp và giữ nhịp bền vững hơn.

THỬ NGHIỆM:
  Đặt giới hạn WIP phù hợp với năng lực hiện tại;
  giúp hoàn tất những việc gần Done trước khi mở mới;
  thêm kiểm thử hành vi quan trọng vào CI.

GUARDRAILS:
  Không tăng lỗi nghiêm trọng, vi phạm bảo mật hoặc
  gánh nặng trực/giờ làm thêm.

CÁCH QUAN SÁT:
  Cùng định nghĩa Started/Done, cùng loại công việc;
  ghi rõ công việc chen ngang và thay đổi phạm vi.

ĐÁNH GIÁ:
  Xem mỗi Sprint và tổng kết sau khi đủ chu kỳ dữ liệu;
  giữ, điều chỉnh hoặc dừng dựa trên bằng chứng.
~~~

### Không có chỉ số nào thay câu hỏi “Vì sao?”

| Kết quả quan sát | Cách phản ứng |
| --- | --- |
| Cycle time giảm, lỗi không tăng, gánh nặng trực giảm | Xem tiếp xu hướng, mở rộng thực hành hợp lý |
| Cycle time giảm, lỗi nghiêm trọng tăng | Điều tra và bảo vệ chất lượng, không gọi là thành công |
| Throughput giảm, WIP giảm, work age ổn định hơn | Xem có đang đổi từ làm nhiều việc dở sang hoàn tất có chất lượng |
| Throughput giảm mạnh, việc gần Done không tiến triển | Kiểm tra giới hạn WIP hoặc năng lực nút thắt có đang làm tắc luồng |
| Chỉ số đều “đẹp” nhưng người dùng báo nhiều lỗi hơn | Kiểm tra telemetry, định nghĩa lỗi, mẫu người dùng và kênh hỗ trợ |
| Người tham gia phản ánh nhịp khó duy trì dù số liệu tăng | Mở trao đổi an toàn, xem khối lượng và gián đoạn thay vì phủ nhận phản hồi |

### Nhịp xem lại

- **Trong ngày:** Theo dõi sự cố nghiêm trọng, SLI/SLO, Work Item Age có dấu hiệu rủi ro.
- **Hằng tuần hoặc theo Sprint:** Xem WIP, hàng đợi, throughput, chất lượng và công việc chen ngang.
- **Trong Retrospective:** Chọn một số cải tiến quy trình và guardrail, không cố tối ưu mọi chỉ số cùng lúc.
- **Theo chu kỳ sản phẩm dài hơn:** Xem outcome người dùng, chi phí chất lượng, mức phụ thuộc kiến thức và tính bền vững của nhịp làm việc.

Đây là **ví dụ về lịch xem lại**, không phải yêu cầu tất cả tổ chức phải họp hay tính metrics hằng ngày. Chọn nhịp phù hợp mức rủi ro và chi phí thu thập.

## 24. Kết hợp với Scrum, Kanban, XP và Agile phản hồi sớm

### Scrum: đánh giá mục tiêu và Increment, không chỉ số điểm

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog. Dữ liệu outcome, lỗi và phản hồi stakeholder giúp sắp thứ tự công việc theo giá trị và rủi ro.
- **Developers** chịu trách nhiệm tạo Increment có chất lượng, lập kế hoạch và điều chỉnh cách thực hiện. Flow/quality metrics giúp họ hiểu nguyên nhân chậm và kỹ thuật cần cải tiến.
- **Scrum Master** hỗ trợ Scrum Team cải thiện hiệu quả, tính minh bạch và năng lực tự quản lý, không phải người dùng velocity để chấm từng thành viên.

**Sprint Planning** cân nhắc Sprint Goal có giá trị và năng lực thực. **Daily Scrum** giúp Developers kiểm tra tiến độ hướng tới Sprint Goal, gồm các trở ngại cần xử lý. **Sprint Review** kiểm tra kết quả cùng stakeholder và điều chỉnh Product Backlog. **Sprint Retrospective** là thời điểm nhìn lại chất lượng, nhịp làm việc và thử cải tiến.

**Không phải mọi thành quả của Sprint đều đo bằng story points**; cũng không phải mọi ảnh hưởng người dùng đều xuất hiện trong đúng một Sprint. Một outcome cần vài tuần quan sát có thể tiếp tục được kiểm chứng sau khi Increment hoàn thành.

### Kanban: nhìn công việc dở và phân phối thời gian

Kanban có những phép đo cốt lõi **WIP, throughput, cycle time và Work Item Age**. Chúng giúp đội kiểm soát luồng, hạn chế kéo việc mới khi bước sau đang nghẽn và phát hiện hạng mục có nguy cơ chậm **trước khi Done**.

Khi dùng Kanban trong Scrum hoặc ngoài Scrum, cần thiết kế workflow và chính sách rõ. **WIP limit không phải “trần tuyệt đối để phạt cá nhân”**, mà là công cụ để đội cùng điều tiết dòng việc.

### XP: tạo chất lượng trong mỗi thay đổi

Thực hành XP như **TDD, pair programming, CI, refactoring, coding standards và small releases** hỗ trợ:

- Lỗi được phát hiện sớm hơn.
- Thay đổi nhỏ, dễ kiểm chứng hơn.
- Kiến thức được chia sẻ thay vì tập trung vào một người.
- Khả năng thay đổi thiết kế được giữ qua kiểm thử hồi quy.
- Phần mềm đạt chất lượng sớm hơn, giảm sửa lỗi cuối đợt.

Các chỉ số chất lượng có thể kiểm tra liệu thực hành **đem lại kết quả thật** hay chỉ tồn tại như nghi thức.

### Lean: đo toàn bộ dòng giá trị

Lean nhắc đội xem **từ nhu cầu đến người dùng nhận giá trị**, bao gồm hàng đợi, chuyển giao, làm lại và rủi ro. Tối ưu thời gian gõ mã mà làm hàng đợi kiểm thử dài hơn có thể không cải thiện **time to value**.

**Các framework và thực hành không cạnh tranh để giành một chỉ số duy nhất.** Scrum giúp điều chỉnh mục tiêu và cách phối hợp; Kanban nhìn dòng công việc; XP cung cấp kỷ luật kỹ thuật; Lean khuyến khích tối ưu toàn hệ thống; Agile gắn tất cả với **phản hồi, kết quả và khả năng thích ứng**.

## 25. Các phản mẫu khi đo chất lượng, ổn định và nhịp bền vững

| Phản mẫu | Hệ quả | Hướng cải thiện |
| --- | --- | --- |
| **Velocity là KPI năng suất** | Khuyến khích nâng điểm, bỏ qua giá trị | Dùng nội bộ theo bối cảnh, đo outcome/quality/flow |
| **So story points giữa các đội** | Quy ước ước lượng khác nhau, so sánh sai | Dùng câu hỏi và chỉ số phù hợp từng hệ thống |
| **Đếm ticket nhỏ là cải tiến** | Throughput tăng giả khi chia hạng mục | Giữ loại đơn vị đo nhất quán và xem outcome |
| **Chỉ nhìn cycle time trung bình** | Bỏ qua story rất chậm hoặc đang bị kẹt | Xem median, percentile và Work Item Age |
| **Tính Done khi chưa đạt DoD** | Chất lượng dời về sau, báo cáo sai | Giữ định nghĩa Done và kiểm chứng |
| **Đo lỗi mà không phân severity** | Lỗi nghiêm trọng bị che bởi tổng số | Phân loại hậu quả, xem lỗi theo rủi ro |
| **Code coverage là mục tiêu tuyệt đối** | Test nhiều nhưng assertion yếu | Bảo vệ hành vi và ranh giới quan trọng |
| **CFR thấp bằng cách không báo sự cố** | Chất lượng đo sai, rủi ro thực không giảm | Văn hóa báo lỗi minh bạch, cải tiến không đổ lỗi |
| **Tăng deployment nhưng bỏ kiểm thử** | Tốc độ kỹ thuật đổi lấy lỗi | CI, test, rollout và khả năng phục hồi |
| **SLO chỉ dựa vào HTTP 200** | Dữ liệu có thể sai hoặc chưa lưu | SLI phản ánh trải nghiệm người dùng |
| **Coi error budget là giấy phép rủi ro dữ liệu** | Có thể gây hại nghiêm trọng | Giữ ràng buộc an toàn và tuân thủ |
| **Lấy mean recovery time che sự cố dài** | Không thấy đuôi rủi ro | Xem phân phối, severity và người dùng bị ảnh hưởng |
| **Giảm WIP bằng cách ẩn blocked work** | Dashboard đẹp, việc vẫn kẹt | Minh bạch ranh giới và thời gian chờ |
| **Giảm cycle time bằng cách thay mốc Started/Done** | Mất khả năng so sánh | Ghi định nghĩa và thời điểm thay đổi |
| **Mọi người luôn phải bận 100%** | Hàng đợi tăng, thiếu năng lực ứng phó | Quản lý WIP, nút thắt và mức dự phòng phù hợp |
| **Làm ngoài giờ lặp lại để đạt Sprint Goal** | Chất lượng và năng lực duy trì giảm | Lập kế hoạch thực, kiểm soát interrupt |
| **Theo dõi thời gian online cá nhân** | Xâm phạm riêng tư, tối ưu hình thức | Đo hệ thống công việc, bảo vệ quyền riêng tư |
| **Khảo sát quá tải rồi công bố từng câu trả lời** | Người tham gia có thể bị nhận diện | Tự nguyện, tổng hợp an toàn, hội thoại phù hợp |
| **Đổ lỗi cá nhân trong postmortem** | Khuyến khích che sự cố | Phân tích hệ thống, điều kiện và phòng ngừa |
| **Chỉ xem một Sprint** | Biến động nhỏ tạo kết luận sai | Xem nhiều kỳ, phân phối và bối cảnh |
| **Không đưa kết quả đo vào quyết định** | Dashboard thành nghi thức tốn công | Mỗi metric gắn câu hỏi, hành động và lần xem lại |

## 26. Bài thực hành: đọc số liệu và quyết định

Tất cả số liệu bên dưới **là giả định minh họa**; hãy nêu **đơn vị, mẫu số, ranh giới và giới hạn suy luận** trong câu trả lời.

### Bài 1 — Phân loại metric theo mục đích

Một đội có những chỉ số:

1. Tỷ lệ học viên tiếp tục đúng tiến độ đã lưu.
2. Số lỗi dữ liệu nghiêm trọng sau phát hành.
3. p85 cycle time của user story.
4. Số lần xử lý sự cố ngoài giờ.
5. Tỷ lệ yêu cầu đọc tiến độ hợp lệ thành công.
6. Số story points hoàn thành.
7. Tỷ lệ người dùng hiểu đúng trạng thái “Đang đồng bộ”.

**Nhiệm vụ:** Xếp từng chỉ số vào **outcome, product quality, reliability, flow, sustainable pace hoặc chỉ số planning nội bộ**. Có chỉ số nào thuộc nhiều góc nhìn không?

**Gợi ý:** (1) outcome; (2) quality; (3) flow; (4) sustainable pace/reliability burden; (5) reliability; (6) planning nội bộ; (7) outcome/trải nghiệm. Không cần ép mọi metric chỉ vào một ô.

### Bài 2 — Tỷ lệ lỗi phát hiện sau phát hành

Trong một phạm vi tính năng và cửa sổ đã xác định, nhóm xác nhận 24 lỗi trước phát hành và 6 lỗi sau phát hành.

1. Tính tỷ lệ lỗi phát hiện sau phát hành theo định nghĩa ở mục 4.
2. Nếu tháng sau nhóm phát hiện nhiều lỗi hơn nhờ thêm logging, có thể kết luận chất lượng xấu hơn ngay không?
3. Vì sao cần phân loại severity?

**Đáp án tham khảo:** 6/(24+6) = **20%**. Số lượng lỗi còn phụ thuộc cách phát hiện, mức sử dụng, phạm vi và thời gian; một lỗi mất dữ liệu nghiêm trọng có thể quan trọng hơn nhiều lỗi giao diện nhỏ.

### Bài 3 — Change failure và phục hồi

Trong kỳ có 30 đợt triển khai đủ điều kiện, 6 đợt được xác minh gây suy giảm dịch vụ. Thời gian khôi phục bốn sự cố được chọn là 10, 15, 20 và 195 phút.

1. Tính change failure rate theo định nghĩa đã cho.
2. Tính mean và median của bốn thời gian phục hồi.
3. Tại sao chỉ báo một số trung bình không đủ để hiểu rủi ro?

**Đáp án tham khảo:** 20%; mean **60 phút**, median **17,5 phút**. Cần xem độ nghiêm trọng, phân phối và ảnh hưởng người dùng. Bốn sự cố là mẫu nhỏ nên không thể khái quát chắc chắn cho mọi sự cố.

### Bài 4 — SLO và error budget

Một SLO thời gian sẵn sàng được định nghĩa là **99,9% trong 30 ngày**, với downtime đo được theo quy tắc đã thống nhất.

1. Tính tổng phút của 30 ngày.
2. Tính ngân sách không sẵn sàng tương ứng.
3. Nếu dịch vụ không sẵn sàng 50 phút theo cùng cách đo, SLO có đạt không?
4. Tại sao cách tính bằng phút không áp dụng nguyên vẹn cho SLI dựa trên số request thành công?

**Đáp án tham khảo:** 43.200 phút tổng; 0,1% tương đương **43,2 phút**. Nếu có 50 phút downtime tính theo cùng định nghĩa, **không đạt mục tiêu minh họa**. Request-based SLI cần mẫu số là số request đủ điều kiện.

### Bài 5 — Dòng công việc và đuôi phân phối

Trong một tuần nhóm hoàn tất năm story có cycle time 2, 3, 3, 5 và 12 ngày làm việc.

1. Throughput trong tuần là bao nhiêu?
2. Mean và median cycle time?
3. Vì sao một story đang mở 16 ngày không xuất hiện trong phép tính cycle time của năm story đã hoàn thành?
4. Chỉ số nào nên dùng để không bỏ qua story đang kẹt?

**Đáp án tham khảo:** Throughput **5 story/tuần**; mean **5 ngày**, median **3 ngày**; story chưa hoàn thành không có cycle time cuối cùng, cần xem **Work Item Age, trạng thái blocked và WIP**.

### Bài 6 — Little's Law và điều kiện áp dụng

Giả sử một workflow ổn định có WIP trung bình 12 hạng mục và throughput 3 hạng mục/tuần.

1. Cycle time trung bình tương ứng là bao nhiêu?
2. Nếu WIP giảm còn 6 nhưng throughput **vẫn giữ 3/tuần**, cycle time tương ứng?
3. Vì sao chỉ đặt WIP limit 6 không bảo đảm mọi hạng mục xong trong 2 tuần?
4. Cho hai trường hợp dữ liệu khiến kết quả không thể diễn giải đúng.

**Đáp án tham khảo:** 4 tuần và 2 tuần **trong giả định**; throughput có thể thay đổi, công việc có độ biến thiên và ranh giới đếm có thể không tương thích.

### Bài 7 — Velocity tăng nhưng nhịp bền vững giảm

Nhóm báo:

- Sprint A: 25 points, không có sự cố ngoài giờ.
- Sprint B: 33 points, ba sự cố ngoài giờ, hàng đợi review tăng, hai story “code complete” chưa đạt DoD.

Hãy đánh giá:

1. Có thể kết luận năng suất tăng 32% không?
2. Hai story chưa đạt DoD có được tính là Increment hoàn thành không?
3. Cần xem thêm dữ liệu nào về **chất lượng, flow và sustainable pace**?
4. Product Owner và Developers nên thảo luận điều gì ở Sprint Review/Retrospective?

**Gợi ý:** Không dùng story points để suy ra năng suất tuyến tính. Kiểm tra cách tính points theo quy tắc đội, tác động sự cố, Sprint Goal, blocker, chất lượng và khả năng phục hồi.

### Bài 8 — Đọc một dashboard cân bằng

Dựa vào bảng hai giai đoạn ở mục 22:

1. Chỉ số nào cho thấy **có dấu hiệu** dòng công việc ổn định hơn?
2. Vì sao throughput 28 → 26 chưa chứng minh đội làm việc kém hơn?
3. Những yếu tố nào có thể làm số lỗi 12 → 5 không phản ánh cải tiến chất lượng thật?
4. Làm sao biết số lần xử lý sự cố ngoài giờ giảm thực thay vì giảm do cách ghi?
5. Có thể tuyên bố WIP limit là nguyên nhân duy nhất khiến outcome tăng không?

**Định hướng:** Dùng từ **“có dấu hiệu”, “phù hợp với giả thuyết”**, không tuyên bố nhân quả khi chỉ có quan sát trước/sau.

### Bài 9 — Thiết kế thử nghiệm nhịp làm việc bền vững

Đội thường xuyên bị ngắt bởi yêu cầu khẩn, nhiều hạng mục chờ review/test. Hãy viết một thử nghiệm hai đến bốn Sprint:

~~~text
Mục tiêu:
  Giảm thời gian chờ và gánh nặng gián đoạn,
  không giảm chất lượng hoặc quyền riêng tư của nhân viên.

Giả thuyết:
  ...

Thay đổi quy trình:
  ...

Chỉ số flow:
  ...

Guardrails chất lượng:
  ...

Tín hiệu bền vững:
  ...

Cách bảo vệ dữ liệu con người:
  ...

Điều kiện dừng/điều chỉnh:
  ...

Thời điểm xem lại:
  ...
~~~

**Yêu cầu:** Nêu ít nhất một cách phát hiện **hệ thống đo bị thay đổi** và một cách giữ người tham gia an toàn khi phản hồi về quá tải.

### Bài 10 — Chọn một chỉ số cần bỏ

Đội đang theo dõi: số commit cá nhân, số phút online, số dòng mã, tổng story points, WIP, Work Item Age, lỗi sau phát hành, outcome người học và thời gian phục hồi.

**Nhiệm vụ:** Chọn các chỉ số nên **loại bỏ khỏi bảng đo hiệu quả đội**, nêu rủi ro khiến chúng bị tối ưu sai, rồi đề xuất tập chỉ số tối giản phục vụ **một câu hỏi có thật**.

**Gợi ý:** Số commit/dòng mã/phút online cá nhân là những proxy dễ gây hiểu lầm và rủi ro giám sát; không nên dùng để xếp hạng năng suất. Story points có thể giữ như công cụ planning nội bộ nếu đội thấy hữu ích nhưng không nên trộn với outcome và reliability.

## 27. Checklist đánh giá chất lượng, ổn định và nhịp bền vững

### Mục tiêu và định nghĩa

- [ ] Đã xác định **Product Goal/vấn đề thực tế** và lý do phải đo.
- [ ] Không đồng nhất **output, tốc độ, giá trị người dùng và chất lượng**.
- [ ] Mỗi metric có đơn vị, nguồn, cách đếm, thời điểm bắt đầu/kết thúc và khoảng quan sát rõ.
- [ ] Những thay đổi cách đo được ghi lại để tránh so sánh sai.
- [ ] Chỉ chọn một tập **chỉ số ít nhưng đủ trả lời câu hỏi**, không tạo dashboard vì hình thức.

### Chất lượng và độ tin cậy

- [ ] Hạng mục chỉ được tính Done khi đáp ứng **Definition of Done** áp dụng.
- [ ] Có kiểm chứng các **hành vi nghiệp vụ và ranh giới tích hợp quan trọng**, không chỉ coverage.
- [ ] Lỗi sau phát hành được xem theo **mức nghiêm trọng, nguồn phát hiện, mức tiếp xúc và bối cảnh**.
- [ ] Có cách phân biệt lỗi mới, lỗi hồi quy và thay đổi yêu cầu hợp lý.
- [ ] Những SLI/SLO được chọn gắn với **trải nghiệm thực**, không chỉ tình trạng máy chủ hoặc HTTP status.
- [ ] Theo dõi cả **sự cố ảnh hưởng người dùng và khả năng phục hồi**, không che trường hợp đuôi rủi ro dài.
- [ ] Có **guardrails an toàn, dữ liệu, bảo mật và tuân thủ** mà tốc độ không được phép vượt qua.

### Dòng công việc và khả năng dự báo

- [ ] WIP, throughput, cycle time và Work Item Age dùng **cùng ranh giới workflow nhất quán**.
- [ ] Hạng mục blocked và chưa Done **vẫn được nhìn thấy**, không bị ẩn để làm đẹp số.
- [ ] Không chỉ nhìn mean; có xem **median, phân phối và các hạng mục rất chậm** khi đủ dữ liệu.
- [ ] SLE hoặc dự báo có **điều kiện, mức tin cậy và loại hạng mục rõ**.
- [ ] Little's Law chỉ được diễn giải khi hệ thống đủ ổn định và các đại lượng tương thích.
- [ ] Không coi velocity/story points là KPI năng suất hay công cụ xếp hạng đội.
- [ ] Có chính sách giới hạn WIP và xử lý công việc khẩn **minh bạch**, tránh bắt đầu vô hạn.

### Nhịp làm việc bền vững

- [ ] Nhóm xem gánh nặng **gián đoạn, trực sự cố và làm ngoài giờ** mà không quy lỗi cá nhân.
- [ ] Có năng lực thực tế cho **sửa lỗi, hỗ trợ, refactoring, học hỏi và phục hồi**.
- [ ] Khi người tham gia phản ánh quá tải, nhóm xem xét **cách tổ chức và khối lượng công việc**.
- [ ] Dữ liệu phản hồi con người được thu thập **tự nguyện, giới hạn mục đích và bảo vệ riêng tư**.
- [ ] Không chấm năng suất bằng **số giờ online, số commit hoặc số lần gõ phím cá nhân**.
- [ ] Kiến thức quan trọng được chia sẻ; không phụ thuộc mãi vào một người “cứu hệ thống”.

### Học hỏi và cải tiến

- [ ] Có baseline và bối cảnh trước khi kết luận một thay đổi tạo ra tác động.
- [ ] Không tuyên bố quan hệ nhân quả chắc chắn từ một bảng trước/sau.
- [ ] Mỗi thử nghiệm cải tiến có **giả thuyết, hành động, guardrail và mốc xem lại**.
- [ ] Chỉ số xấu không bị xóa khỏi báo cáo chỉ vì không phù hợp kỳ vọng.
- [ ] Product Owner và Developers cùng dùng bằng chứng để **điều chỉnh Product Backlog và cách làm**.
- [ ] Thành công được xem là **giá trị và độ tin cậy có thể duy trì**, không phải một Sprint có nhiều con số xanh.

## 28. Câu hỏi tự kiểm tra

1. Vì sao “giao nhiều story hơn” không tự chứng minh đội Agile hiệu quả hơn?
2. Năm góc nhìn outcome, quality, reliability, flow và sustainable pace khác nhau thế nào?
3. Một bộ chỉ số cân bằng nên bắt đầu từ KPI có sẵn hay câu hỏi về giá trị/rủi ro? Vì sao?
4. Những trường nào cần có để hai người tính ra cùng một metric?
5. Vì sao số lỗi sau phát hành thấp có thể do **ít người dùng hoặc ít báo lỗi**?
6. Vì sao phải phân biệt mức nghiêm trọng của lỗi, nhất là lỗi quyền truy cập và mất dữ liệu?
7. Code coverage có thể và không thể chứng minh điều gì?
8. Definition of Done liên hệ thế nào với tính chất của Increment?
9. SLI, SLO và SLA khác nhau ở đâu?
10. Với một SLO availability 99,9% trong 30 ngày, error budget minh họa bằng phút là bao nhiêu?
11. Khi nào không được quy đổi error budget request-based thành phút?
12. Vì sao error budget không biện minh cho hành vi gây lộ hoặc mất dữ liệu?
13. Change failure rate cần những định nghĩa nào để so sánh giữa các kỳ?
14. Mean recovery time và median recovery time có thể đưa ra hai góc nhìn khác nhau ra sao?
15. WIP, throughput, cycle time và Work Item Age dùng để trả lời câu hỏi gì?
16. Vì sao cycle time chỉ của những story đã hoàn thành có thể che công việc đang kẹt?
17. p50 và p85 cycle time giúp hiểu độ ổn định và khả năng dự báo thế nào?
18. SLE trong Kanban khác một SLO về độ tin cậy dịch vụ như thế nào?
19. Định luật Little phát biểu gì và cần những điều kiện nào khi áp dụng?
20. Vì sao giảm WIP không bảo đảm throughput giữ nguyên hoặc mọi hạng mục hoàn thành đúng hạn?
21. Velocity có ích ở đâu, và vì sao không nên so giữa hai đội?
22. Sprint Goal khác tổng số task hoặc story points hoàn thành như thế nào?
23. Những tín hiệu nào cho thấy nhịp làm việc có thể đang phụ thuộc vào làm ngoài giờ?
24. Vì sao mức sử dụng 100% ở một nút thắt có thể làm thời gian chờ tăng?
25. Làm thế nào tổ chức xử lý yêu cầu khẩn mà không biến mọi việc thành P0?
26. Nợ kỹ thuật có thể ảnh hưởng tới chất lượng và cycle time ra sao?
27. Những yếu tố nào làm phép so sánh trước/sau mất ý nghĩa?
28. Leading indicator khác lagging indicator như thế nào trong một hệ thống phát hành?
29. Vì sao việc dùng số commit hoặc số phút online cá nhân làm KPI có thể gây hại?
30. Goodhart's Law cảnh báo điều gì khi một metric trở thành mục tiêu cứng?
31. Trong case study hai giai đoạn, vì sao throughput giảm nhẹ vẫn có thể đi cùng cải tiến tốt?
32. Khi cycle time giảm nhưng lỗi dữ liệu và gánh nặng trực tăng, đội nên ra quyết định gì?
33. Scrum Review và Retrospective giúp nhóm kiểm tra hai loại kết quả khác nhau nào?
34. Pair programming, TDD và Continuous Integration hỗ trợ chất lượng và nhịp bền vững bằng cơ chế gì?
35. Làm sao biết một cải tiến đã hoàn thành **vòng học hỏi** thay vì chỉ hoàn thành một báo cáo?

**Ghi nhớ:** **Đánh giá Agile đúng nghĩa là kiểm tra khả năng tạo giá trị đáng tin cậy theo một nhịp có thể duy trì**, không phải đo mức bận hay săn một con số năng suất. Chất lượng cần được bảo vệ bằng kiểm thử, Definition of Done và phản hồi sau phát hành; độ ổn định cần được nhìn qua WIP, throughput, phân phối cycle time, Work Item Age và khả năng dự báo; độ tin cậy cần được kiểm tra bằng SLI/SLO, sự cố và khả năng phục hồi; tính bền vững cần phản ánh mức gián đoạn, gánh nặng vận hành và khả năng duy trì nhịp của cả đội. Hãy **dùng ít chỉ số nhưng định nghĩa tốt, đọc cùng bối cảnh và guardrails, bảo vệ quyền riêng tư**, rồi thử cải tiến và đo lại. Thành công không phải chỉ giao nhanh hơn hôm nay, mà là **người dùng nhận giá trị tốt hơn và đội có thể tiếp tục làm điều đó vào những Sprint kế tiếp**.
