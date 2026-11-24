# Xác định mục tiêu chuyển đổi bằng kết quả có thể quan sát

Một công ty phát triển nền tảng học trực tuyến tuyên bố đã “chuyển đổi Agile” sau ba tháng: mọi nhóm đều có bảng công việc, Daily Scrum, Sprint Planning và Sprint Review; số nhân viên được đào tạo Scrum tăng lên và các báo cáo velocity xuất hiện đều đặn. Tuy nhiên, học viên vẫn phải đợi nhiều tuần để một lỗi mất tiến độ được sửa, Developers liên tục bị gián đoạn vì thay đổi ưu tiên, và các nhóm chỉ tích hợp mã vào cuối Sprint. Những thứ dễ đếm đã thay đổi, nhưng **kết quả mà khách hàng và tổ chức quan tâm** chưa cải thiện.

Tình huống này cho thấy **áp dụng thực hành Agile không đồng nghĩa đã đạt mục tiêu chuyển đổi Agile**. Một tổ chức có thể đổi tên chức danh, thêm nghi thức và công cụ mà vẫn duy trì cơ chế ra quyết định cũ: nhiều phê duyệt, giao việc theo dự án, tối ưu mức bận của từng người và đánh giá thành tích theo số ticket đóng. Chuyển đổi chỉ trở nên có ý nghĩa khi tổ chức **nâng được khả năng tạo giá trị, tiếp nhận phản hồi, thay đổi hướng, duy trì chất lượng và làm việc bền vững**.

Để thực hiện điều đó, cần **mục tiêu chuyển đổi bằng kết quả có thể quan sát**: phát biểu rõ ai cần nhận lợi ích nào, hành vi hoặc trạng thái của hệ thống sẽ thay đổi thế nào, cách thu bằng chứng, thời điểm xem lại và những điều không được đánh đổi. Mục tiêu ấy không biến Agile thành một con số duy nhất; nó giúp mọi người **thấy được mình đang học gì và cần quyết định gì tiếp theo**.

Bài thuộc chương **Chuyển đổi Agile** của module **AGILE_DEVELOPMENT**. Phạm vi gắn với giá trị và nguyên tắc Agile, user story, backlog, Scrum, Kanban, XP, phản hồi sớm, giao sản phẩm tăng dần, số đo dòng công việc và cải tiến liên tục. Các số liệu trong ví dụ là **giả định để học cách thiết kế phép đo**, không phải chuẩn ngành hoặc dữ liệu thực tế của tổ chức nào.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **mục tiêu chuyển đổi** với kế hoạch đào tạo, triển khai nghi thức Scrum hoặc thay công cụ quản lý.
2. Nhận diện **vấn đề hiện tại của hệ thống tạo giá trị** trước khi chọn một phương pháp Agile.
3. Phân biệt **activity, output, capability, outcome và impact**, tránh đo sự tuân thủ nghi thức thay cho kết quả.
4. Viết mục tiêu có **đối tượng hưởng lợi, baseline, kết quả mong muốn, thời hạn đánh giá, giả thuyết và guardrails**.
5. Tạo **theory of change** liên kết thay đổi trong chính sách/cấu trúc/năng lực với flow, chất lượng, giá trị người dùng và tác động dài hạn.
6. Chọn các tín hiệu **leading, lagging, định lượng và định tính** phù hợp với bối cảnh từng dòng giá trị.
7. Định nghĩa và đọc đúng **cycle time, throughput, WIP, work item age, lỗi sản phẩm, độ tin cậy CI/CD và kết quả người dùng**.
8. Thiết kế các thử nghiệm nhỏ, có giả thuyết rõ để kiểm tra xem thay đổi tổ chức có đang giúp đạt mục tiêu không.
9. Xác định những hành vi lãnh đạo và cơ chế quản trị cần thay đổi, thay vì đẩy toàn bộ trách nhiệm sang Scrum Teams.
10. Theo dõi một chương trình chuyển đổi mà không biến chỉ số thành công cụ thưởng/phạt, tạo số liệu giả hoặc hạ chuẩn chất lượng.

## 2. “Chuyển đổi Agile” thực sự nhằm thay đổi điều gì?

Một chương trình chuyển đổi có thể tác động tới **cách tổ chức chọn vấn đề, phân bổ năng lực, xây phần mềm, phối hợp và học từ phản hồi**. Agile không phải một mô hình tổ chức duy nhất được quy định sẵn. Scrum là một framework; Kanban cung cấp cách quản lý và cải tiến flow; XP tập trung các thực hành kỹ thuật. Tổ chức cần lựa chọn và điều chỉnh phù hợp với giá trị, rủi ro và hoàn cảnh.

### Bốn khả năng cốt lõi thường muốn cải thiện

| Khả năng | Biểu hiện khi còn yếu | Kết quả mong muốn có thể quan sát |
| --- | --- | --- |
| **Định hướng giá trị** | Backlog bị lấp bằng yêu cầu từ nhiều nguồn, không rõ vấn đề người dùng | Nhóm ưu tiên giả thuyết có bằng chứng, phát hiện sớm việc không tạo giá trị |
| **Thích ứng bằng phản hồi** | Kế hoạch cố định dài hạn, chỉ demo khi dự án gần xong | Feedback từ người dùng và kỹ thuật đến sớm, thực sự làm đổi backlog/quyết định |
| **Giao hàng đáng tin** | Tích hợp muộn, lỗi lặp, deploy rủi ro, chờ nhiều bước | Increment nhỏ đạt chuẩn, có thể đưa tới người dùng an toàn và thường xuyên hơn |
| **Phối hợp và cải tiến bền vững** | Nhiều handoff, quá tải, phụ thuộc cá nhân, sợ nêu vấn đề | Ít chờ vô ích, trách nhiệm rõ, học hỏi và hỗ trợ xuyên chuyên môn |

**Không nên lấy “tất cả nhóm dùng Scrum” làm bằng chứng kết quả.** Có sản phẩm phù hợp Scrum, có nhóm dịch vụ cần quản lý nhu cầu liên tục bằng Kanban, có đội cần đầu tư mạnh vào XP/CI. Kết quả cần hướng tới là **dòng giá trị và khả năng thích ứng**, không phải sự giống nhau của bảng công việc.

### Câu hỏi chẩn đoán

- Người dùng đang gặp trở ngại hoặc chờ giá trị ở đâu?
- Mất bao lâu từ lúc nhận ra nhu cầu đến khi có Increment đủ chuẩn để kiểm tra?
- Những vấn đề chất lượng nghiêm trọng được phát hiện khi nào?
- Khi giả thuyết sai, ai có quyền đổi hướng và mất bao lâu để quyết định?
- Phần lớn thời gian đang tạo giá trị hay đang chờ phê duyệt, review, môi trường, quyết định?
- Nhóm có thể làm việc ở nhịp bền vững không, hay phải dùng tăng ca để đạt số liệu?

Nếu tổ chức chưa trả lời được các câu hỏi này, **đo hiện trạng và phát hiện rào cản** có thể là bước chuyển đổi đầu tiên quan trọng hơn mua công cụ hay triển khai một đợt đào tạo lớn.

## 3. Activity, output, capability, outcome và impact

Các lớp bằng chứng không thể dùng thay nhau.

| Lớp | Câu hỏi | Ví dụ chuyển đổi Agile | Cạm bẫy diễn giải |
| --- | --- | --- | --- |
| **Activity — hoạt động** | Chúng ta đã làm gì? | 20 buổi đào tạo Scrum, 10 cuộc retro, 4 workshop CI | Họp/học nhiều chưa nói hành vi đã thay đổi |
| **Output — đầu ra** | Đã tạo ra thứ gì? | Bảng Kanban, DoD viết ra, pipeline mới, team charter | Có tài liệu/công cụ chưa bảo đảm được dùng hiệu quả |
| **Capability — năng lực thực** | Tổ chức có thể làm được điều gì? | Developers tự deploy bản đã kiểm tra; team làm rõ và chia user story nhỏ | Một buổi demo không chứng minh khả năng lặp lại |
| **Outcome — kết quả** | Hành vi/trạng thái cần cải thiện đã thay đổi thế nào? | Ít lỗi lọt production, rút ngắn thời gian tới feedback, giảm chờ, người dùng giải quyết tác vụ dễ hơn | Kết quả cục bộ chưa tự nói tác động dài hạn |
| **Impact — tác động lâu dài** | Giá trị bền vững cho người dùng/tổ chức là gì? | Học viên đạt mục tiêu học tập, niềm tin tăng, tổ chức thích ứng trước biến động | Khó quy toàn bộ cho một thay đổi tổ chức |

**Ví dụ:** “100% thành viên đã học Scrum” đo **activity/exposure**; “100% nhóm có retrospective” đo mức **áp dụng nghi thức**. “Trong ba tháng, lỗi checkpoint có tác động nghiêm trọng được phát hiện và xử lý sớm hơn; thời gian tới một bản sửa an toàn giảm, trong khi làm thêm giờ không tăng” gần hơn với **outcome vận hành**. Nếu học viên bớt mất tiến độ và tiếp tục học thuận tiện hơn, ta bắt đầu có **bằng chứng giá trị người dùng**.

### Sơ đồ chuỗi giả thuyết thay đổi

~~~mermaid
flowchart LR
    A["Vấn đề: giá trị đến chậm<br/>và lỗi phát hiện muộn"] --> B["Thay đổi chính sách/năng lực<br/>WIP, CI, ví dụ nghiệp vụ"]
    B --> C["Capability<br/>lát cắt nhỏ, feedback sớm"]
    C --> D["Outcome vận hành<br/>flow tốt hơn, chất lượng ổn"]
    D --> E["Outcome sản phẩm<br/>người dùng nhận lợi ích sớm"]
    E --> F["Impact dài hạn<br/>đáp ứng nhu cầu bền vững"]
    D -. "Đo và học" .-> B
    E -. "Phản hồi" .-> A
~~~

Mỗi mũi tên là **giả thuyết về quan hệ**, không phải bằng chứng nhân quả mặc định. Có thể CI tốt hơn nhưng người học vẫn không dùng tính năng vì vấn đề sản phẩm được chọn chưa đúng. Khi đó cần **đổi giả thuyết sản phẩm**, không phủ nhận hoàn toàn cải thiện kỹ thuật.

## 4. Bắt đầu từ vấn đề, không từ danh sách thực hành muốn triển khai

Một chương trình thường bắt đầu bằng khẩu hiệu “chuyển toàn bộ nhóm sang Scrum trong một quý”. Nhưng **vấn đề nào sẽ được giải quyết, ai nhận giá trị và tiêu chí nào cho biết đã tiến bộ** vẫn chưa rõ.

### So sánh phát biểu

| Phát biểu | Nhận xét |
| --- | --- |
| “Đến cuối quý, 100% nhân viên tham gia đào tạo Scrum.” | Mốc triển khai hoạt động; hữu ích để quản lý đào tạo, chưa phải outcome chuyển đổi |
| “Đến cuối quý, 12/12 team có Sprint board.” | Output về công cụ/cách tổ chức |
| “Nhóm giao hàng nhanh hơn.” | Outcome có hướng nhưng thiếu đơn vị đo và bối cảnh |
| “Với các thay đổi sản phẩm thường lệ của dòng học trực tuyến, giảm thời gian từ bắt đầu phát triển đến Increment đạt DoD và có thể phát hành, từ baseline được xác minh tới target có ý nghĩa trong hai quý; đồng thời không tăng lỗi nghiêm trọng hoặc giờ làm thêm.” | Mục tiêu có đối tượng, ranh giới, kết quả, thời hạn, guardrails |
| “Người học ít gặp mất checkpoint hơn và nhận bản sửa an toàn sớm hơn, được đo theo cohort/incident và phản hồi người dùng.” | Nối mục tiêu chuyển đổi với giá trị cuối |

**Không nhất thiết mọi mục tiêu phải có một con số duy nhất.** Một thay đổi văn hóa hay khả năng cộng tác có thể cần bằng chứng định tính. Nhưng vẫn phải nêu **hành vi có thể quan sát và quyết định sẽ đưa ra** khi kết quả tốt, xấu hoặc chưa rõ.

### Xác định phạm vi trước khi đo

Một doanh nghiệp có thể có các dòng việc khác nhau: feature mới, vận hành hệ thống hiện có, sự cố bảo mật, nội dung học và nghiên cứu sản phẩm. Nếu gộp tất cả vào một chỉ số cycle time, kết quả có thể không đại diện cho vấn đề cần cải thiện. Nên bắt đầu bằng **một hoặc vài dòng giá trị có ranh giới rõ**, sau đó mở rộng khi học được cách đo và làm việc.

## 5. Mục tiêu chuyển đổi có thể kiểm chứng gồm những thành phần gì?

Một mục tiêu đủ tốt cho ra **quyết định**, không chỉ số đẹp để báo cáo. Có thể dùng mẫu:

~~~text
1. AI ĐƯỢC LỢI?
   Nhóm người dùng cuối, nhóm nội bộ hoặc dòng giá trị nào?

2. HIỆN TRẠNG:
   Bằng chứng và baseline, các nút thắt, mức độ tin cậy dữ liệu.

3. OUTCOME MONG MUỐN:
   Hành vi, kết quả hoặc năng lực nào phải thay đổi?

4. LÝ THUYẾT THAY ĐỔI:
   Vì sao các chính sách/kỹ thuật/phối hợp được chọn có thể giúp?

5. METRIC:
   Định nghĩa, numerator/denominator, population, start/finish.

6. TARGET & HORIZON:
   Mức cải thiện có ý nghĩa và thời điểm/cửa sổ đánh giá.

7. GUARDRAILS:
   An toàn, dữ liệu, chất lượng, trải nghiệm, sức khỏe nhóm.

8. OWNER & DECISION:
   Ai chịu trách nhiệm xem bằng chứng, điều chỉnh đầu tư và phạm vi?

9. UNCERTAINTY:
   Điều gì chưa biết, giả thuyết nào cần kiểm tra trước?
~~~

### Một ví dụ phát biểu đầy đủ

> **Trong dòng giá trị phát triển tính năng học trực tuyến**, từ baseline được đo nhất quán ở các user story tương tự, chúng tôi muốn **giảm thời gian chờ tích hợp và kiểm thử để phần mềm đạt Definition of Done sớm hơn** trong hai quý. Chúng tôi giả định việc **chia user story theo lát cắt, kiểm soát WIP, thực hành CI và đưa kiểm tra quyền/dữ liệu tới sớm** giúp đạt điều đó. Thành công được xem qua **cycle time và phân bố, work item age, số lỗi phát hiện sau tích hợp và phản hồi Developers**. Không được đánh đổi **an toàn dữ liệu, lỗi production nghiêm trọng hoặc nhịp làm việc bền vững**. Mỗi tháng chúng tôi sẽ đánh giá để quyết định giữ, thay đổi hoặc dừng thử nghiệm.

Nếu chưa có baseline hoặc chưa thể đặt target đáng tin, nêu **một mốc khám phá** để đo hiện trạng và lựa chọn target. Không tự đặt con số “giảm 50% trong 30 ngày” chỉ để có KPI.

## 6. Xây baseline đáng tin trước khi đặt target

Baseline là mô tả **tình trạng ban đầu trong một cửa sổ và phạm vi xác định**. Nó không nhất thiết là một điểm số; có thể là phân bố thời gian, các trường hợp thất bại, mô tả workflow và phản hồi người dùng.

### Nguồn bằng chứng bổ sung nhau

| Nguồn | Có thể cho biết | Giới hạn cần thận trọng |
| --- | --- | --- |
| **Value-stream mapping** | Công việc đang tạo giá trị hay chờ ở đâu? | Phụ thuộc người mô tả, dễ bỏ sót handoff ngầm |
| **Work item history** | Cycle time, WIP, age, throughput và blocked time | Các trạng thái thường không được ghi nhất quán |
| **CI/CD logs** | Thời gian kiểm tra, build failures, deploy/recovery | Deploy không đồng nghĩa người dùng nhận giá trị |
| **Production incidents** | Sự cố, mức ảnh hưởng, thời gian khôi phục | Ít incident được báo có thể do khả năng phát hiện yếu |
| **Product analytics** | Hoàn thành tác vụ, sử dụng chức năng, lỗi trải nghiệm | Tracking/eligibility hoặc mùa vụ có thể lệch |
| **Quan sát user story thực** | Nơi làm rõ yêu cầu, review và tích hợp bị chậm | Một vài story chưa đại diện toàn hệ thống |
| **Phỏng vấn Developers và người dùng** | Nguyên nhân cảm nhận, hành vi phối hợp và vấn đề chưa ghi log | Mẫu nhỏ không tự suy rộng thành tỷ lệ chung |
| **Chính sách và quyền quyết định** | Cổng phê duyệt, mức tự chủ, cách xử lý ưu tiên | Văn bản có thể khác hành vi thực tế |

### Chuẩn hóa định nghĩa đo

Trước khi nói “cycle time hiện là 14 ngày”, hãy trả lời: **ngày lịch hay ngày làm việc?** Bắt đầu ở In Progress hay ngay khi item được cam kết? Kết thúc khi code merged, đạt DoD hay production? Bao gồm blocked time hay chỉ active work? User story và bug có cùng cách tính không?

**Ví dụ:** Nếu ngày trước đo tới “code merged”, còn sau chuyển sang “Increment đạt DoD”, cycle time có thể trông tăng dù hệ thống thực sự tốt hơn. Phải **ghi thay đổi định nghĩa**, không trộn chuỗi thời gian rồi công bố hiệu quả.

### Không tạo baseline bằng dữ liệu giả

Nếu tổ chức chưa có lịch sử đủ tin cậy, dùng một đợt quan sát ngắn có ranh giới rõ: chọn loại công việc, theo dõi start–finish, ghi blocked reasons, đối chiếu với sự kiện thực. Báo rõ độ bất định. **“Chưa đủ dữ liệu” là kết luận tốt hơn số đẹp không có căn cứ**.

## 7. Mục tiêu nào cần ưu tiên: giá trị, flow, chất lượng hay con người?

Không nên chọn chỉ số vì dashboard hiện có sẵn. Cần bắt đầu từ **vấn đề giới hạn giá trị của dòng sản phẩm**.

| Miền kết quả | Vấn đề hiện tại | Outcome có thể quan sát | Metric/quan sát gợi ý |
| --- | --- | --- | --- |
| **Giá trị người dùng** | Học viên khó tiếp tục bài đang dở | Người đủ quyền mở lại đúng bài nhanh, ít gặp sai tiến độ | Task success, thời gian tác vụ, khảo sát/quan sát người học |
| **Phản hồi sản phẩm** | Chỉ kiểm tra giả thuyết sau nhiều tháng | Có thể kiểm chứng một lát cắt sớm và điều chỉnh backlog | Thời gian từ giả thuyết tới exposure, quyết định dựa trên phản hồi |
| **Flow** | Nhiều việc chờ review/phê duyệt | Work items hoàn tất ổn định, đuôi thời gian ngắn hơn | WIP, age, cycle time distribution, throughput |
| **Chất lượng** | Regression và mất dữ liệu sau release | Lỗi quan trọng được phòng ngừa/phát hiện sớm | Automated check health, escaped defects, incidents |
| **Khả năng giao hàng** | Build/deploy thủ công và dễ hỏng | Có thể đưa bản đã kiểm chứng tới môi trường đích an toàn | Lead time thay đổi kỹ thuật, deployment reliability |
| **Hợp tác** | Phụ thuộc cá nhân, chờ quyết định lâu | Các nhóm chia sẻ ví dụ, owner và xử lý blocker sớm | Blocked time, rework, quan sát handoff, phản hồi nhóm |
| **Tính bền vững** | Thường xuyên tăng ca và chuyển ngữ cảnh | Nhịp làm việc ổn định, dám nêu vấn đề | WIP, interruption, làm thêm giờ, phản hồi định tính |

### Đừng tối ưu cục bộ

Nếu thay đổi giúp một đội phát triển đóng PR nhanh hơn nhưng đưa mọi kiểm tra sang hàng đợi QA chung, **thời gian end-to-end có thể tăng**. Nếu tăng deployment frequency bằng cách bỏ kiểm thử bảo mật, hệ thống có thể **giao lỗi đến người dùng nhanh hơn**. Đo **toàn dòng giá trị và guardrails**, không chỉ một bước thuận tiện.

### Kết quả có thể xung đột

Thời gian tới thị trường, độ chính xác dữ liệu, chi phí, bảo mật, quyền riêng tư và nhịp làm việc đôi khi xung đột. Mục tiêu chuyển đổi cần **công khai nguyên tắc trade-off**. Với những điều kiện bắt buộc như bảo vệ quyền truy cập, không thể “bù trừ” bằng nhiều story Done hoặc tăng số lượt dùng.

## 8. Theory of change: liên kết can thiệp và kết quả

Một **theory of change** (lý thuyết thay đổi) là bản đồ các giả thuyết mô tả **vì sao một hoặc nhiều thay đổi có thể tạo ra kết quả mong muốn**. Nó ngăn nhóm chỉ liệt kê các thực hành nổi tiếng.

### Ví dụ về bài toán phát hiện lỗi muộn

| Tầng | Nội dung | Câu hỏi kiểm chứng |
| --- | --- | --- |
| **Vấn đề** | Lỗi checkpoint chỉ được phát hiện sát cuối Sprint | Có đúng do tích hợp muộn hay vì dữ liệu kiểm thử thiếu? |
| **Can thiệp** | Chia vertical slices, CI, unit/API tests, làm rõ ví dụ nghiệp vụ trước code | Nhóm có thực sự thay cách làm không? |
| **Năng lực mới** | Tích hợp và kiểm chứng một lát cắt trong lúc phát triển | Bao nhiêu story có bằng chứng tích hợp sớm? |
| **Outcome trung gian** | Ít công việc chờ cuối Sprint, lỗi phát hiện trước khi release | Cycle time, regression timing, WIP có thay đổi? |
| **Outcome người dùng** | Số lỗi mất tiến độ và thời gian nhận bản sửa giảm | Có bằng chứng ở production và phản hồi học viên? |
| **Guardrail** | Không tăng flaky tests, quyền truy cập sai, làm thêm giờ | Chúng ta có đang chuyển rủi ro sang nơi khác? |

### Dùng một sơ đồ giả thuyết, không phải sơ đồ thành tích

~~~mermaid
flowchart TD
    A["Lỗi phát hiện muộn<br/>và thời gian chờ cao"] --> B{"Giả thuyết nguyên nhân?"}
    B -->|Tích hợp muộn| C["CI + contract/integration tests"]
    B -->|Quy tắc mơ hồ| D["Ví dụ nghiệp vụ + refinement"]
    B -->|Quá nhiều việc dở| E["Pull policy + WIP limit"]
    C --> F["Feedback kỹ thuật sớm"]
    D --> G["Giảm hiểu sai và rework"]
    E --> H["Ít chờ và context switching"]
    F --> I["Increment nhỏ đạt DoD sớm"]
    G --> I
    H --> I
    I --> J["Người dùng nhận cải tiến an toàn sớm"]
    J -. "Đo outcome" .-> A
~~~

Không cần triển khai tất cả nhánh ngay. Nếu dữ liệu cho thấy **phần lớn thời gian là chờ API contract**, có thể ưu tiên một thử nghiệm **làm rõ contract sớm và kiểm tra tích hợp** thay vì bắt đầu từ việc đổi toàn bộ cấu trúc tổ chức.

## 9. Xây bộ mục tiêu cân bằng theo hệ thống thay vì hàng chục KPI rời rạc

Chương trình chuyển đổi cần **một số mục tiêu ưu tiên có quan hệ rõ**, mỗi mục tiêu có bằng chứng gần và xa. Một cây mục tiêu giúp tổ chức thấy **năng lực kỹ thuật và cách làm việc phục vụ giá trị nào**, tránh đo từng phòng ban bằng những chỉ số xung đột.

~~~mermaid
flowchart TD
    A["Mục tiêu chuyển đổi:<br/>giao cải tiến học tập có ích<br/>nhanh hơn và an toàn hơn"] --> B["Giá trị người học"]
    A --> C["Năng lực phản hồi và flow"]
    A --> D["Chất lượng và an toàn"]
    A --> E["Phối hợp bền vững"]
    B --> B1["Task success, phản hồi,<br/>kết quả học có nghĩa"]
    C --> C1["Cycle time, WIP, tuổi item,<br/>time to feedback"]
    D --> D1["Escaped defects, incident,<br/>CI và tests đáng tin"]
    E --> E1["Blocked time, rework,<br/>tải công việc, học hỏi"]
    B1 -.-> F["Review giả thuyết<br/>và điều chỉnh backlog"]
    C1 -.-> F
    D1 -.-> F
    E1 -.-> F
~~~

### Ba lớp tín hiệu

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| **Outcome chính** | Điều tổ chức thực sự muốn thay đổi | Học viên nhận bản sửa lỗi tiến độ đúng, an toàn sớm hơn |
| **Diagnostic/leading** | Phát hiện sớm vấn đề và gợi ý can thiệp | Item age, thời gian chờ review, pipeline duration, thời gian làm rõ yêu cầu |
| **Guardrails** | Không để mục tiêu chính gây hại | Vi phạm quyền, lỗi dữ liệu, sự cố production, làm thêm giờ kéo dài |

Không có một tỷ lệ “đúng” về số lượng metrics. Tốt hơn là **ít thước đo có định nghĩa và được dùng để quyết định**, thay vì một dashboard lớn mà không biết cần hành động ra sao.

### Bằng chứng không nhất thiết chỉ là số

Đối với vấn đề “các team không dám nêu blocker”, có thể cần **phản hồi ẩn danh đúng cách, quan sát cuộc trao đổi và ví dụ tình huống**, thay vì một điểm “psychological safety” gán cho từng người. Phân tích định tính giúp giải thích vì sao số liệu đang thay đổi, nhưng cũng phải mô tả **phạm vi, cách lấy mẫu và giới hạn**.

## 10. Metric contract: biến khẩu hiệu thành phép đo lặp lại

Mỗi metric quan trọng cần một **định nghĩa vận hành**. Nếu hai nhóm hiểu “hoàn thành” khác nhau, so sánh cycle time của họ có thể tạo ra động lực sai.

### Mẫu khai báo một metric của chương trình chuyển đổi

~~~text
METRIC_NAME:
  cycle_time_feature_to_done

PURPOSE:
  Đo khả năng hoàn tất user story thuộc loại feature
  theo Definition of Workflow đã thống nhất.

POPULATION:
  Những feature PBIs của một dòng giá trị trong phạm vi thử;
  loại trừ incident/maintenance hoặc báo riêng.

UNIT:
  Một work item có ranh giới và loại nhất quán.

START:
  Lúc item thực sự bắt đầu theo policy.

FINISH:
  Lúc item đáp ứng Definition of Done áp dụng.

TIME_UNIT:
  Ngày lịch hoặc ngày làm việc; phải chọn và công bố.

WINDOW:
  Thời kỳ quan sát, ngày chốt và quy tắc item xuyên kỳ.

AGGREGATION:
  Median, phân bố, percentiles và số lượng mẫu.

DATA_SOURCE:
  Workflow events, xác minh bằng ví dụ công việc thật.

SEGMENTS:
  Loại feature, phụ thuộc, độ phức tạp hoặc nhóm cần xem.

GUARDRAILS:
  Lỗi nghiêm trọng, rework, chất lượng CI, làm thêm giờ.

OWNER:
  Người bảo trì định nghĩa, nguồn và giải thích.
~~~

**Tại sao nên giữ cả phân bố?** Một median đẹp có thể che những item rất lâu do phụ thuộc. Nếu tổ chức đặt mục tiêu “giảm trung vị”, có thể vô tình bỏ qua nhóm người dùng có lỗi nghiêm trọng nằm ở đuôi. Cần xem **work item age đang tăng, những item bị blocked và độ biến thiên** cùng số tổng.

### Thay đổi định nghĩa làm hỏng so sánh

Nếu trước chuyển đổi Done nghĩa là “code merged”, sau chuyển đổi Done nghĩa là “tích hợp và đạt DoD”, **không được nối chuỗi thời gian như thể cùng ranh giới**. Trong giai đoạn đầu có thể đo **song song một khoảng** hoặc chú thích rõ thay đổi cách tính, rồi thiết lập baseline mới.

### Metric không có nguồn dữ liệu đáng tin

Nếu blocked time được ghi thủ công nhưng người tham gia sợ bị đánh giá kém, dữ liệu có thể thiếu có hệ thống. Giải pháp không phải đặt KPI “bắt buộc ghi blocked 100%” rồi kỷ luật người báo chậm. Cần **làm rõ mục đích học hỏi, thay đổi cách phản ứng và tạo điều kiện ghi trung thực**, kết hợp quan sát để kiểm tra nguồn dữ liệu.

## 11. Leading và lagging: biết mình đi đúng hướng trước khi impact xuất hiện

Chuyển đổi tổ chức thường diễn ra trong nhiều tháng; tác động lên người dùng có thể cần thời gian. **Leading indicators** giúp nhóm nhận tín hiệu sớm về khả năng đạt kết quả; **lagging indicators** đánh giá kết quả đã xuất hiện. Cách phân loại **phụ thuộc chuỗi giả thuyết**, không cố định tuyệt đối.

| Giả thuyết chuyển đổi | Leading signal | Outcome theo sau | Điều cần xác nhận |
| --- | --- | --- | --- |
| Chia story nhỏ giúp giao sớm | Item size hợp lý, PR nhỏ, ít work items già | Cycle time giảm và Increment dùng được thường xuyên hơn | Có đúng là lát cắt giá trị, không chỉ chia ticket? |
| CI giúp phát hiện lỗi trước release | Thời gian test feedback, builds đáng tin, integration checks sớm | Lỗi tích hợp lọt production giảm | Suite có bắt đúng rủi ro không? |
| WIP limit giảm chuyển ngữ cảnh | WIP và blocked age giảm | Flow ổn định hơn, ít việc dồn cuối Sprint | Có bị giấu work items hoặc tăng giờ làm không? |
| Trao đổi nghiệp vụ sớm giảm hiểu sai | Acceptance examples rõ, ít chờ clarification | Rework giảm, hành trình người dùng đúng hơn | Người dùng cuối có được lợi? |
| Tự chủ phù hợp giúp ra quyết định nhanh | Ít tầng phê duyệt không cần thiết, owner rõ | Time-to-feedback giảm | An toàn và điều kiện pháp lý vẫn được bảo vệ? |
| Nâng phản hồi người dùng giúp chọn đúng việc | Nhiều quyết định được cập nhật từ nghiên cứu/đo lường | Outcome sản phẩm cải thiện | Có chỉ tăng số cuộc phỏng vấn nhưng không hành động? |

**Cảnh báo:** “80% story có automated tests” có thể là tín hiệu thực hành, nhưng không tự chứng minh tests đáng tin hoặc có tác động. Một tổ chức hoàn toàn có thể **tăng hoạt động leading** mà kết quả không cải thiện. Đó là lúc phải **xem lại cơ chế giả thuyết**, không tiếp tục ép mục tiêu tuân thủ.

### Chọn nhịp đánh giá

- **Ngay khi có rủi ro nghiêm trọng:** phản ứng với lỗi mất dữ liệu, quyền truy cập hoặc outage.
- **Hằng ngày/tuần:** work item age, WIP, build reliability, blocked reasons.
- **Theo Sprint/vòng giao ngắn:** Increment đạt DoD, phản hồi kỹ thuật/sản phẩm, rework.
- **Theo cohort đủ thời gian:** retention, học viên tiếp tục học có nghĩa, tác động nghiệp vụ.
- **Theo quý/chu kỳ chiến lược:** năng lực thay đổi, giá trị kinh doanh, lựa chọn đầu tư và cơ chế tổ chức.

Không nên xem một chỉ số D30 mới có hai ngày dữ liệu rồi tuyên bố chuyển đổi thất bại; cũng không thể đợi báo cáo cuối quý mới xử lý lỗi phân quyền.

## 12. Kết quả chuyển đổi trong Scrum: mục tiêu, không phải nghi thức

Scrum có các **accountabilities, events và artifacts** giúp thực hiện minh bạch, kiểm tra, thích ứng. Một tổ chức có thể dùng chúng đúng về hình thức nhưng **không thay đổi cách ra quyết định hoặc sản phẩm**.

### Đo đúng chức năng của từng yếu tố

| Scrum element | Câu hỏi về kết quả | Tránh đo thành tích hình thức |
| --- | --- | --- |
| **Product Goal** | Nhóm có tập trung vào một trạng thái giá trị tương lai và điều chỉnh backlog theo phản hồi? | Đếm số Product Goals được viết |
| **Product Backlog** | Việc ưu tiên có phản ánh vấn đề, giá trị và rủi ro mới không? | Đếm tổng PBIs hoặc story points |
| **Sprint Goal** | Mọi người có phối hợp để tạo một mục tiêu Sprint hữu ích thay vì chạy nhiều việc rời rạc? | Tỷ lệ hoàn thành từng task như lời hứa tuyệt đối |
| **Increment/Definition of Done** | Phần mềm tích hợp có đạt chuẩn và dùng được, có thể đưa tới người dùng không? | Gọi “Done” khi code xong hoặc demo giả |
| **Sprint Review** | Feedback của bên liên quan có làm thay đổi hướng sản phẩm khi phù hợp? | Đếm số người tham dự và slides |
| **Sprint Retrospective** | Nhóm có thử và đánh giá được cải tiến cụ thể? | Đếm số action items mỗi lần họp |

### Không biến Sprint Goal thành con số kết quả ngoài tầm kiểm soát

Ví dụ Sprint Goal hợp lý: **“Học viên còn quyền có thể mở lại đúng bài đang dở từ trang khóa học”**, với Increment đạt DoD. **Outcome “tỷ lệ học viên quay lại tăng”** có thể cần thêm thời gian và exposure, phù hợp làm mục tiêu sản phẩm/giả thuyết kiểm chứng theo cohort.

Trong Scrum, **Product Owner chịu trách nhiệm tối đa hóa giá trị**, Developers chịu trách nhiệm tạo Increment đạt DoD, Scrum Master hỗ trợ hiệu quả Scrum Team. Chuyển đổi muốn có kết quả phải trao **khả năng ra quyết định và trách nhiệm tương xứng**, không vừa yêu cầu Product Owner ưu tiên dựa trên giá trị vừa áp một danh sách tính năng bất biến từ bên ngoài.

### Nhiều nhóm trên một sản phẩm

Nếu nhiều Scrum Teams cùng tạo một sản phẩm, họ cần có **Product Goal, Product Backlog, Product Owner và Definition of Done chung** theo Scrum Guide; Increment phải tích hợp. **Mỗi nhóm “hoàn tất” một phần không chạy được cùng nhau** không chứng minh chuyển đổi đã cải thiện giao giá trị. Nếu các nhóm làm những sản phẩm riêng biệt, cần điều phối bằng contracts/ownership phù hợp thay vì giả định một backlog duy nhất cho toàn doanh nghiệp.

## 13. Kết quả chuyển đổi với Kanban: flow và chính sách minh bạch

Kanban giúp quản lý **dòng công việc thực** và cải tiến qua dữ liệu. Bốn flow metrics thường được dùng gồm **WIP, throughput, work item age, cycle time**. Chúng hữu ích khi tổ chức muốn giảm **chờ đợi, chuyển ngữ cảnh, tuổi công việc và biến thiên**.

| Metric | Định nghĩa | Câu hỏi cải tiến |
| --- | --- | --- |
| **WIP** | Số work items đã bắt đầu, chưa xong theo Definition of Workflow | Có quá nhiều việc dở đang tranh cùng năng lực? |
| **Throughput** | Số work items hoàn tất trong một khoảng | Hệ thống thực sự hoàn tất việc ở nhịp nào? |
| **Work item age** | Thời gian một item dở đã trải qua từ khi bắt đầu | Item nào có rủi ro bị kẹt ngay hôm nay? |
| **Cycle time** | Thời gian work item hoàn tất từ start tới finish | Phân bố thời gian hoàn tất có phù hợp kỳ vọng? |

### Ví dụ flow minh họa

~~~text
Ready → Developing → Review / Verify → Done
              │                │
              └── Blocked, được hiển thị rõ ──┘

Chính sách cần được thống nhất:
- Ranh giới start/finish và điều kiện Done.
- WIP được kiểm soát ở đâu.
- Khi Review đầy thì hỗ trợ hoàn tất trước khi pull.
- Việc khẩn cấp có điều kiện và owner riêng.
- Blocked items được xem lại, không giấu khỏi hệ thống.
~~~

### Một thay đổi từ WIP 12 xuống WIP 7 có phải thành công?

Chưa chắc. Nếu số công việc dở giảm nhưng throughput, cycle time và quality xấu đi vì một chính sách quá chặt, cần điều chỉnh. Nếu WIP giảm và việc tới Done ổn định hơn, ít giờ làm thêm, đó là bằng chứng phù hợp với giả thuyết cải tiến flow. **Không có WIP limit “chuẩn Agile” cố định cho mọi nhóm**.

### SLE là kỳ vọng xác suất, không phải deadline cho mọi item

Ví dụ một **Service Level Expectation**: “Với feature nhỏ thuộc workflow này, kỳ vọng **85%** work items được hoàn tất trong tối đa **10 ngày làm việc**.” Đây là **minh họa**, cần lấy dữ liệu thực để thiết lập. Item đang dở gần ngưỡng ấy có thể được ưu tiên gỡ blocker; không dùng SLE như bảo đảm 100%.

### Flow tốt không thay giá trị người dùng

Một hệ thống có thể đóng ticket nhanh bằng cách chia nhỏ task kỹ thuật không tạo khả năng dùng được. Hãy đo **lát cắt end-to-end, chất lượng Increment và product outcomes**, tránh tối ưu số thẻ chỉ vì con số throughput tăng.

## 14. XP và DevOps: khả năng giao hàng an toàn là năng lực chuyển đổi

Các thực hành **Extreme Programming** như test-first/TDD, continuous integration, pair programming, refactoring, simple design và small releases có thể rút ngắn feedback kỹ thuật và giảm chi phí thay đổi. Những năng lực này thường rất quan trọng khi tổ chức có nhiều team đã họp theo Scrum nhưng **vẫn không thể giao phần mềm an toàn**.

| Thực hành/năng lực | Giả thuyết tác động | Quan sát cần xem |
| --- | --- | --- |
| **TDD/unit tests** | Quy tắc nghiệp vụ được kiểm tra sớm và refactor an toàn hơn | Test reliability, lỗi hồi quy, thời gian sửa |
| **API/contract tests** | Tương thích producer/consumer được xác nhận trước triển khai | Lỗi tích hợp phát hiện trước staging/production |
| **Continuous Integration** | Thay đổi nhỏ được tích hợp và phản hồi sớm | Build duration, failed builds, thời gian từ commit tới feedback |
| **Refactoring** | Code dễ thay đổi mà không giảm hành vi đúng | Chi phí thay đổi tương tự, rework, độ tin cậy tests |
| **Pairing/knowledge sharing** | Giảm phụ thuộc một cá nhân, nâng chất lượng quyết định | Blocked time, review age, khả năng hỗ trợ chéo |
| **Small releases / progressive delivery** | Giá trị và feedback tới người dùng sớm hơn, giảm phạm vi rủi ro | Time-to-feedback, khả năng rollback, lỗi sau release |
| **Observability** | Phát hiện, chẩn đoán và phục hồi sự cố nhanh hơn | Incident detection/recovery và business guardrails |

### Phân biệt engineering outcomes và product outcomes

**Deployment frequency** và **thời gian dẫn thay đổi kỹ thuật** phản ánh năng lực giao bản đã kiểm tra; chúng **không chứng minh** người dùng đã thấy feature flag bật hoặc giải pháp tạo giá trị. **Change failure** và **recovery** đo chất lượng vận hành theo định nghĩa; chúng không thay thế kết quả học tập hoặc khả dụng.

Các nhóm có thể dùng **DORA metrics** để quan sát năng lực giao và độ tin cậy, nhưng phải nêu **phiên bản định nghĩa, population, nguồn dữ liệu và ranh giới**. Không đặt mục tiêu “deploy 20 lần/ngày” nếu chỉ có ba thay đổi mang giá trị và việc chia nhỏ làm tăng rủi ro.

### Technical agility có thể là điều kiện tiên quyết

Nếu mỗi lần sửa ứng dụng đều cần ba tuần regression test thủ công, tổ chức khó phản hồi nhanh dù Scrum events rất đúng. Cải tiến **CI, tự động kiểm tra rủi ro quan trọng, môi trường thử đáng tin và phân chia lát cắt** có thể tạo nền để sản phẩm học từ thị trường nhanh hơn. Không nên chỉ đào tạo người quản lý mà bỏ qua **năng lực kỹ thuật giao hàng**.

## 15. Lãnh đạo và quản trị phải thay đổi để mục tiêu đạt được

Chuyển đổi Agile không thể thành công nếu chỉ yêu cầu Developers “tự tổ chức” nhưng mọi quyết định vẫn phải qua nhiều tầng phê duyệt, quản lý giao ưu tiên mới từng ngày và đánh giá thành tích theo mức bận của mỗi cá nhân.

### Những thay đổi hệ thống mà lãnh đạo cần xem

| Cơ chế hiện tại | Hậu quả có thể quan sát | Điều chỉnh cần thử |
| --- | --- | --- |
| Dự án được tài trợ theo scope cố định rất dài | Khó đổi backlog khi học được thông tin mới | Xem lại đầu tư theo outcome, rủi ro và khoảng quyết định |
| Mọi yêu cầu từ lãnh đạo có cùng mức khẩn | WIP cao, Sprint Goal mất tập trung | Một đường ưu tiên rõ, chính sách xử lý expedite |
| Team phụ thuộc phê duyệt cho thay đổi thường lệ | Thời gian chờ lớn | Chính sách ủy quyền theo mức rủi ro, tự phục vụ có guardrails |
| Thưởng theo story points, tickets hoặc giờ bận | Hành vi chia vụn việc, giấu blocker, né việc khó | Đánh giá đóng góp theo bối cảnh và học hỏi hệ thống; không xếp hạng người bằng flow metrics |
| Chuyên gia dùng chung là điểm quyết định duy nhất | Hàng đợi và single point of failure | Coaching, tiêu chuẩn hóa, platform capability và backup |
| Sự cố bị dùng để truy lỗi cá nhân | Không ai muốn nêu vấn đề sớm | Incident review có trách nhiệm, học nguyên nhân hệ thống, bảo vệ sự minh bạch |
| Không dành năng lực cải tiến kỹ thuật | CI flaky, tech debt tăng, thay đổi chậm | Đầu tư giảm nút thắt kỹ thuật theo dữ liệu |

### Quyền quyết định và trách nhiệm

Muốn Product Owner chịu trách nhiệm giá trị, tổ chức phải cho phép **điều chỉnh thứ tự Product Backlog theo bằng chứng** trong quyền hạn phù hợp. Muốn Developers chịu trách nhiệm chất lượng Increment, họ cần **thời gian, công cụ, kỹ năng và khả năng phản hồi** để đạt DoD, không bị yêu cầu bỏ test để giữ mốc báo cáo.

**Autonomy không có nghĩa ai muốn làm gì cũng được.** Nó là khả năng ra quyết định trong **mục tiêu, tiêu chuẩn và giới hạn rủi ro rõ**, với trách nhiệm minh bạch. Các kiểm soát pháp lý/bảo mật bắt buộc vẫn phải được tôn trọng.

### Đo sự thay đổi trong hành vi lãnh đạo

Một tín hiệu có ích không phải “bao nhiêu lãnh đạo học Agile Leadership”, mà là:

- Các quyết định ưu tiên có được giải thích bằng outcome và trade-off?
- Có bao nhiêu lần nhóm bị buộc thay Sprint Goal bởi yêu cầu thiếu căn cứ?
- Khi phát hiện giả thuyết sai, có thể đổi hướng mà không bị phạt?
- Những phụ thuộc ngoài quyền nhóm có owner và được gỡ trong khoảng phù hợp?
- Nhân viên có dám công khai rủi ro/chất lượng chưa đạt?

Câu trả lời cần phối hợp **bằng chứng công việc và nghiên cứu định tính**, không dùng một khảo sát đơn lẻ để đánh giá phẩm chất cá nhân.

## 16. Chọn phạm vi thử nghiệm chuyển đổi có chủ đích

Áp đồng loạt một cơ cấu mới cho toàn tổ chức khi chưa hiểu rủi ro thường làm khó suy ra **thực hành nào có ích và điều gì đang gây hại**. Có thể bắt đầu bằng **một value stream hoặc một nhóm sản phẩm có khả năng kiểm chứng kết quả**, sau đó mở rộng có điều kiện.

### Đặc điểm của phạm vi thử phù hợp

1. **Vấn đề thật và có giá trị:** nếu cải thiện sẽ giúp người dùng hoặc dòng sản phẩm, không chỉ dễ được chọn vì team “ngoan”.
2. **Ranh giới công việc rõ:** biết start/finish của items, loại việc và đầu ra cần đạt.
3. **Quyền quyết định đủ:** team có thể thay chính sách, kỹ thuật hoặc phối hợp trong phạm vi cần thiết.
4. **Khả năng thu bằng chứng:** có baseline hoặc kế hoạch đo, dữ liệu chất lượng và feedback.
5. **Rủi ro chấp nhận được:** guardrails, đường dừng/hoàn tác và hỗ trợ cần thiết.
6. **Khả năng chia sẻ bài học:** những nơi khác biết điều kiện nào đã áp dụng và giới hạn kết quả.

### Tránh chọn “pilot thành công được đảm bảo”

Nếu chọn chỉ nhóm vốn đã giỏi, được lãnh đạo bảo trợ đặc biệt và nhận nhiều chuyên gia hỗ trợ, kết quả **không tự suy rộng** cho cả tổ chức. Cần mô tả các điều kiện hỗ trợ ấy, xem **sự khác biệt về năng lực, phụ thuộc và sản phẩm** trước khi nhân rộng.

### Ví dụ pilot cho luồng “Học tiếp”

Nhóm chọn luồng cập nhật tiến độ học viên:

- **Hiện trạng:** nhiều story chờ API review, checkpoint bugs xuất hiện ở integration cuối Sprint.
- **Can thiệp:** chia vertical slice, đồng bộ ví dụ nghiệp vụ sớm, WIP control ở Review/Verify và API tests trong CI.
- **Outcome gần:** thời gian chờ review và tuổi item giảm; lỗi được phát hiện sớm hơn.
- **Outcome người dùng:** khả năng mở đúng bài và nhận bản sửa dữ liệu sớm hơn.
- **Guardrails:** không lộ dữ liệu tài khoản khác, không tăng production incidents, không tăng làm thêm giờ.
- **Thời gian:** quan sát baseline trước, thử theo hai đến ba vòng làm việc thích hợp và đánh giá theo độ đủ của dữ liệu.

Một pilot nên tạo **kiến thức về cơ chế cải thiện**, không chỉ một slide nói “team pilot đạt 100% adoption Agile”.

## 17. Lập một lộ trình chuyển đổi theo những mốc học hỏi

“Lộ trình chuyển đổi” thường bị hiểu là **lịch cài đặt công cụ và tổ chức họp cho toàn công ty**. Một lộ trình dựa trên kết quả nên cho thấy **khi nào có thể kiểm tra giả thuyết quan trọng và cần quyết định điều gì**, đồng thời giữ đủ linh hoạt khi bằng chứng mới xuất hiện.

### Minh họa kế hoạch 90 ngày

| Giai đoạn | Việc cần thực hiện | Bằng chứng/mốc quyết định | Điều không nên tuyên bố quá sớm |
| --- | --- | --- | --- |
| **Ngày 1–15: hiểu hệ thống** | Phỏng vấn người dùng và nhóm, đi theo work items, đo flow, lỗi, feedback; xác định dòng giá trị | Baseline ban đầu, bản đồ điểm chờ, danh sách giả thuyết | “Đã chẩn đoán toàn tổ chức” chỉ sau vài cuộc phỏng vấn |
| **Ngày 16–30: chọn thay đổi nhỏ** | Chọn một vấn đề; làm rõ quyền quyết định, WIP, kỹ thuật và giám sát cần có | Improvement experiment với owner, metric, guardrails | “Thay đổi này chắc chắn hiệu quả” |
| **Ngày 31–60: thử trong phạm vi rõ** | Áp dụng vào lát cắt thực, tích hợp, lấy feedback và theo dõi hàng ngày | Trends về item age, chờ review, lỗi kỹ thuật và trải nghiệm | “Một Sprint nhanh hơn = chuyển đổi thành công” |
| **Ngày 61–75: đánh giá** | So kết quả với baseline phù hợp, xem ngoại lệ và phân khúc, hỏi người tham gia | Quyết định giữ, sửa, dừng hoặc thử tiếp | “Bằng chứng nhân quả tuyệt đối” khi có nhiều biến thay đổi |
| **Ngày 76–90: chuẩn hóa/mở rộng có chọn lọc** | Cập nhật policy/test/docs, thử ở một bối cảnh khác nếu an toàn | Cơ chế hữu ích được mô tả, rủi ro nhân rộng và mốc đánh giá tiếp | “90 ngày là xong Agile Transformation” |

Các mốc chỉ là **ví dụ để lập kế hoạch**. Một thay đổi liên quan bảo mật hoặc dữ liệu có thể cần thận trọng hơn; một vấn đề rất nhỏ có thể hoàn tất vòng PDCA nhanh hơn. Không bắt đội phải chờ ngày 60 mới sửa lỗi nghiêm trọng được phát hiện ở ngày 20.

### Ba loại kết quả theo từng giai đoạn

1. **Học đúng vấn đề:** Bản đồ nút thắt và baseline có độ tin cậy phù hợp.
2. **Tạo năng lực mới:** Chính sách/kỹ thuật/phối hợp thay đổi và có thể lặp lại.
3. **Kiểm tra giá trị:** Flow/quality/outcome người dùng cho thấy thay đổi có ích hoặc cần đổi hướng.

Những milestone như “hoàn thành training” hoặc “mua license” có thể được quản lý, nhưng không nên thay **mốc học hỏi hoặc kết quả** trong báo cáo chương trình.

## 18. Product Goal, mục tiêu chuyển đổi và OKR: khác tầng nhưng hỗ trợ nhau

Một tổ chức có thể dùng **OKR** để diễn đạt mục tiêu và Key Results, nhưng OKR **không phải một thành phần bắt buộc của Scrum hoặc Agile**. Mục tiêu chuyển đổi nằm ở khả năng hệ thống **tạo giá trị tốt hơn**; Product Goal mô tả **trạng thái tương lai mong muốn của một sản phẩm**.

### Ví dụ liên kết

| Tầng | Mục tiêu giả định | Bằng chứng nên xem |
| --- | --- | --- |
| **Product Goal** | Học viên có thể duy trì tiến độ học thuận tiện và tin cậy | Task success, mất tiến độ, phản hồi người học |
| **Mục tiêu chuyển đổi** | Giảm thời gian từ nhu cầu tới Increment đáng tin, tăng khả năng thích ứng | Cycle time, time-to-feedback, quality, khả năng đổi backlog |
| **Sprint Goal** | Một lát cắt Học tiếp mở đúng bài cho học viên đủ quyền | Increment đạt DoD, demo thực và feedback liên quan |
| **Improvement experiment** | Ưu tiên hoàn tất trước bắt đầu thêm; test API sớm | WIP/review age, thời gian phát hiện lỗi, phản hồi Developers |
| **Key Results nếu có OKR** | Kết quả đo ở phạm vi, baseline, cửa sổ cụ thể | Giá trị trước/sau, phân bố, guardrails, mức bất định |

### Ví dụ Objective và Key Results

**Objective:** “Dòng phát triển tính năng học tập có thể phản hồi nhu cầu người học sớm hơn mà vẫn bảo vệ dữ liệu và nhịp làm việc.”

**Các KR minh họa để thảo luận sau khi đã có baseline tin cậy:**

1. Giảm **median cycle time của feature PBIs cùng loại** từ 12 xuống 7 ngày làm việc trong hai quý.
2. Giảm **tỷ lệ các feature PBIs bị blocked hơn ba ngày** từ 30% xuống dưới 15% theo cùng workflow.
3. Tăng tỷ lệ **lát cắt đủ chuẩn được kiểm chứng với người dùng trong khoảng thời gian đã chọn** từ 20% lên 50%; có định nghĩa rõ thế nào là “đủ chuẩn” và “kiểm chứng”.
4. Giữ các quality guardrails: **không chấp nhận sự cố truy cập sai quyền**, không tăng lỗi mất dữ liệu nghiêm trọng, độ tin cậy pipeline và sức khỏe nhóm không xấu đi.

Các con số **không phải tiêu chuẩn chung**; chúng giả định baseline đã được đo và mức thay đổi có ý nghĩa với nhu cầu. Không chọn bốn KR chỉ vì dashboard có bốn ô.

### Không dùng KR như lời hứa nhân quả

Nếu tổ chức đạt cycle time 7 ngày nhưng công việc chủ yếu là các feature rất nhỏ, có thể **thành phần mẫu** đã thay đổi. Nếu tăng số lần thử nghiệm nhưng mỗi lần không ra quyết định, chỉ số số lần experiment cũng có thể bị thao túng. KR phải đi với **định nghĩa, cách kiểm tra chất lượng và đối chiếu Product Goal**, không chỉ màu xanh/đỏ.

## 19. Tính toán cụ thể: kết quả chuyển đổi nhìn qua ba loại phép đo

Số đo cần có **câu hỏi và mẫu số**. Một vài phép tính minh họa giúp phân biệt kết quả có ý nghĩa với con số dễ gây ngộ nhận.

### 19.1. Thời gian hoàn tất công việc

Giả sử năm feature PBIs cùng loại có cycle time (ngày làm việc):

~~~text
Trước: 5, 8, 12, 15, 20
Sau:   4, 6,  7,  9, 15
~~~

- Median trước = **12 ngày**; median sau = **7 ngày**.
- Chênh lệch median = **5 ngày**, giảm tương đối khoảng **41,7%**.
- Trong kỳ sau vẫn có item **15 ngày**; cần xem độ biến thiên và blocker.
- **Mẫu chỉ năm item mỗi kỳ**, nên không thể tự suy ra tác động trên toàn tổ chức hoặc quan hệ nhân quả.

Từ kết quả này, nhóm có thể **giữ thỏa thuận cải tiến trong một vòng tiếp** và điều tra item đuôi dài, chứ chưa nên tuyên bố “mọi team tăng hiệu suất 41,7%”.

### 19.2. Tỷ lệ lỗi nghiêm trọng

Giả sử trước có 3 lỗi nghiêm trọng trong 20 lần thay đổi được triển khai; sau có 1 lỗi trong 20 lần. Tỷ lệ lỗi thô lần lượt là:

\[
\frac{3}{20}\times100\%=15\%,
\qquad
\frac{1}{20}\times100\%=5\%.
\]

Số học cho thấy **giảm 10 điểm phần trăm**, nhưng mẫu rất nhỏ; các thay đổi có thể khác mức rủi ro, còn lỗi chưa được phát hiện. Không tuyên bố “chất lượng chắc chắn tăng gấp ba lần” từ phép tính này. Đối với an toàn dữ liệu quan trọng, cần thêm **kiểm thử bảo vệ, giám sát và đánh giá sự cố** chứ không chỉ tỷ lệ.

### 19.3. Tỷ lệ người dùng hoàn thành tác vụ

Giả sử có 160 lượt tác vụ **đủ điều kiện**, 112 lượt mở đúng bài trong 60 giây:

\[
\text{Task success rate}=\frac{112}{160}\times100\%=70\%.
\]

Đây là **70% lượt tác vụ được quan sát**, không đồng nghĩa 70% học viên toàn sản phẩm. Một người có thể thử nhiều lần; cần chọn đơn vị **lượt, phiên hay người duy nhất** phù hợp câu hỏi.

### 19.4. Điểm phần trăm và phần trăm tương đối

Tỷ lệ thành công tăng từ **50% lên 60%** là **10 điểm phần trăm**, tương đương mức tăng **20% tương đối** so với 50%. Không được ghi “tăng 20 điểm phần trăm” nếu thực tế chỉ từ 50% lên 60%.

### 19.5. WIP và throughput không phải tỷ lệ giá trị

Nếu một đội đóng 15 ticket/tuần rồi tăng lên 25, chưa thể biết người dùng nhận thêm giá trị: có thể cách chia ticket đã đổi. Nên đối chiếu **work item types, Increment thực sự đạt Done, quality và outcome** trước khi kết luận hệ thống tốt lên.

## 20. Chất lượng dữ liệu và sự thay đổi định nghĩa trong quá trình chuyển đổi

Một chương trình có thể “cải thiện” chỉ vì đổi cách ghi nhận. Ví dụ:

- Trước đây item bị blocked vẫn ở Doing, nay bị chuyển ra một board khác và **không tính WIP**.
- Trước đây lỗi được ghi đầy đủ, sau đội **ngại báo bug** vì KPI không cho phép.
- Trước đây Done là kiểm thử hoàn tất; sau đổi Done thành code merged.
- Trước đây deploy một feature lớn mỗi tháng, sau có nhiều commit nhỏ nhưng người dùng vẫn chỉ thấy feature theo tháng.
- Tracking người học chuyển version, làm conversion tăng chỉ vì **đã sửa lỗi đếm event**.

### Bảng kiểm tra chất lượng nguồn đo

| Rủi ro dữ liệu | Cách kiểm chứng |
| --- | --- |
| **Event thiếu/trùng** | So tracking với log nguồn, kiểm tra retry và cơ chế deduplication |
| **Workflow khác nhau** | Ghi Definition of Workflow và ngày thay đổi policy |
| **Sample selection** | Ai được tính, ai không được tính, có chỉ chọn team tốt không? |
| **Work item granularity** | Cách chia PBIs/tickets có đổi? Có còn so cùng loại việc? |
| **Timestamp/time zone** | Ngày lịch/ngày làm việc, đồng hồ và giờ hệ thống có nhất quán? |
| **Cửa sổ chưa đủ** | Cohort D7/D30 đã trưởng thành trước khi lấy denominator? |
| **Số đo bị khuyến khích thao túng** | Người làm có lý do giấu blocker, lặp chuyển trạng thái hoặc hạ tiêu chí Done? |
| **Sự kiện bên ngoài** | Có campaign, incident, đổi nhân sự/khách hàng, kỳ nghỉ hoặc migration cùng lúc? |

### Không biến số đo thành hình phạt

Nếu nhân viên bị đánh giá dựa trên **số ticket cá nhân hoặc ít thời gian blocked**, họ có động lực chia vụn việc, không nhận việc khó hoặc không báo sự cố. Tổ chức sẽ **mất dữ liệu trung thực**, khiến cải tiến ngày càng khó. Số đo chuyển đổi nên phục vụ **học hỏi hệ thống**, không xếp hạng người.

### Một thay đổi trong metric cần được chú thích

Ví dụ nếu cập nhật tool làm work item age được tính khác, ghi “từ ngày 1/7 thay cách tính” và **tái thiết lập baseline/đo song song khi cần**. Không trình bày một đường biểu đồ liên tục mà không ghi chú mốc đổi định nghĩa.

## 21. Tránh nhầm tương quan với nhân quả

Giả sử sau khi áp dụng Scrum và CI, cycle time giảm từ 12 xuống 7 ngày. Có thể Scrum/CI góp phần, nhưng cũng có thể:

- Team bắt đầu làm các item nhỏ hơn.
- Một hệ thống phụ thuộc vừa được loại bỏ bởi một dự án hạ tầng khác.
- Tháng ấy ít incident hoặc ít ngày nghỉ.
- Các chuyên gia được tăng cường tạm thời cho pilot.
- Bảng Kanban đổi ranh giới bắt đầu/kết thúc.
- Một campaign làm product outcome thay đổi độc lập với kỹ thuật.

**Before/after không tự chứng minh nhân quả.** Tuy vậy, không nhất thiết cần thí nghiệm ngẫu nhiên cho mọi thay đổi tổ chức. Có thể nâng chất lượng suy luận bằng:

1. Nêu trước **cơ chế và outcome dự kiến**.
2. Giữ định nghĩa đo nhất quán, so những loại việc tương đồng.
3. Xem **trend trước khi can thiệp**, không chỉ hai điểm đầu/cuối.
4. So sánh với một dòng giá trị khác khi có điều kiện hợp lý, ghi rõ khác biệt.
5. Thu **bằng chứng định tính**: hành vi có thực sự đổi, nút thắt có biến mất?
6. Theo dõi **guardrails và nhóm bị ảnh hưởng xấu**.
7. Công bố **mức bất định và các lời giải thích thay thế**.

### Phát biểu báo cáo thận trọng

**Không nên:** “Chúng tôi áp dụng Scrum nên hiệu suất tăng 40%.”

**Nên:** “Trong hai vòng sau khi thử WIP control và tích hợp sớm trên dòng tính năng học tập, median cycle time của các PBIs được đo giảm từ 12 xuống 7 ngày; lỗi tích hợp được phát hiện sớm hơn. Kết quả phù hợp với giả thuyết, nhưng mẫu còn nhỏ và loại việc có khác nhau. Chúng tôi tiếp tục đo một vòng, xem các item đuôi dài và quality guardrails trước khi mở rộng.”

### Nếu kết quả xấu đi?

Một giả thuyết chuyển đổi có thể sai. Ví dụ WIP limit quá thấp khiến đội chờ vô ích hoặc một approval tự động bị sai logic. **Điều chỉnh hoặc hoàn tác có căn cứ** là kết quả của học hỏi, không phải “thiếu niềm tin Agile”. Nên định nghĩa sẵn **điều kiện dừng** đối với rủi ro không chấp nhận được.

## 22. Cohort, phân khúc và hiện tượng kết quả tổng có thể đảo chiều

Tổ chức thường muốn một con số chung: “cycle time toàn công ty giảm bao nhiêu?”. Nhưng các loại sản phẩm, team size, mức phụ thuộc và loại công việc khác nhau có thể khiến kết quả tổng **khó diễn giải**.

### Ví dụ thành phần công việc thay đổi

| Loại việc | Trước — số hoàn tất / median ngày | Sau — số hoàn tất / median ngày |
| --- | --- | --- |
| Feature nhỏ | 10 / 4 | 30 / 3 |
| Feature có phụ thuộc nhiều hệ thống | 20 / 15 | 10 / 12 |
| Incidents theo quy trình riêng | Không gộp | Không gộp |

Nhìn hai loại, mỗi loại đều có tín hiệu nhanh hơn; nhưng khi **tỉ trọng công việc nhỏ tăng mạnh**, một giá trị tổng hợp có thể thay đổi đáng kể chỉ vì mix công việc. Trường hợp ngược lại cũng có thể xảy ra: tổng xấu đi dù từng phân khúc cải thiện.

Đây là lý do nên:

- So **cùng loại việc và cùng ranh giới đo** khi cần đánh giá flow.
- Không dùng số tổng để xếp hạng team có nhiệm vụ khác nhau.
- Xem **phân bố, đuôi dài và blocked reasons**, không chỉ một trung bình.
- Mô tả điều kiện pilot có khác phần còn lại hay không.
- Cân nhắc những nhóm người dùng/nhân viên dễ bị ảnh hưởng xấu bởi thay đổi chính sách.

### Cẩn trọng khi so sánh đội

Team A có cycle time 3 ngày cho UI nhỏ, Team B có 12 ngày cho migration có yêu cầu bảo mật cao **không chứng minh Team B kém Agile**. Đánh giá nên tập trung **mức cải thiện của dòng giá trị trong bối cảnh** và xem những phụ thuộc chung có thể giảm, không tạo cuộc đua số ngày.

## 23. Bằng chứng định tính: quan sát hành vi thay đổi thật

Một số outcome quan trọng khó đo bằng một log duy nhất: **quyền chủ động trong quyết định, khả năng nêu vấn đề, chia sẻ kiến thức, hiệu quả hợp tác**. Đo chúng bằng số điểm khảo sát duy nhất có thể khiến nhóm trả lời theo điều được mong đợi.

### Phương pháp bổ trợ

| Phương pháp | Câu hỏi có thể trả lời | Cạm bẫy |
| --- | --- | --- |
| **Quan sát một user story đi qua workflow** | Ai đợi ai, quyết định trì hoãn ở đâu? | Một story có thể đặc biệt khó/dễ |
| **Phỏng vấn theo tình huống gần đây** | Vì sao team phải thay ưu tiên, ai quyết định? | Ký ức có thể không chính xác; cần đối chiếu bằng chứng |
| **Retrospective/incident review** | Điều gì đã làm hệ thống tạo lỗi/chờ? | Sợ bị trách khiến vấn đề không được nói thật |
| **Khảo sát ngắn, được bảo vệ danh tính** | Người tham gia có thấy dễ phản ánh blocker, có quyền giải quyết vấn đề? | Mẫu và cách hỏi quyết định ý nghĩa |
| **Usability research với người dùng** | Lát cắt mới có giải quyết nhiệm vụ họ muốn làm? | Vài người không tự đại diện toàn dân số |
| **Decision log** | Phản hồi nào thật sự khiến Product Backlog hoặc policy đổi? | Có tài liệu nhưng quyết định vẫn có thể không được thực thi |

### Câu hỏi phỏng vấn có giá trị

**Thay vì:** “Bạn nghĩ công ty đã Agile hơn chưa?”

**Nên hỏi:** “Lần gần nhất nhóm phát hiện user story đang đi sai hướng là khi nào? Ai nhận ra, phải trao đổi với ai, mất bao lâu mới đổi quyết định? Có bằng chứng nào chúng ta có thể xem lại?”

Một câu hỏi khác: “Lần gần nhất bạn cần triển khai bản sửa lỗi nhỏ, những bước nào tạo giá trị, những bước nào phải chờ? Ai có thể quyết định bỏ một bước không cần thiết?”

### Giữ an toàn khi thu thập phản hồi

Không lấy phát biểu cá nhân nhạy cảm rồi gắn tên trong báo cáo lãnh đạo nếu không có quyền và mục đích phù hợp. Với nhóm rất nhỏ, “ẩn danh” có thể không thật sự bảo vệ người trả lời; cần thiết kế cách thu thập và tổng hợp có trách nhiệm. Cải tiến bền vững đòi hỏi **niềm tin để dữ liệu phản ánh thực tế**, không phải một công cụ khảo sát bóng bẩy.

## 24. Cơ chế quyết định: đo xong phải hành động

Mục tiêu chuyển đổi sẽ thành một chương trình báo cáo nếu mọi cuộc họp chỉ xem dashboard mà **không có quyền thay đổi cấu trúc, chính sách hoặc Product Backlog**.

### Nhóm quyết định cần rõ ba điều

1. **Dữ liệu cho biết gì và chưa cho biết gì?** Định nghĩa, chất lượng, cửa sổ và giới hạn.
2. **Giả thuyết nào được hỗ trợ hoặc bác bỏ?** Có lời giải thích khác không?
3. **Quyết định nào được đưa ra?** Giữ, điều chỉnh, mở rộng, dừng hoặc đo thêm; ai sở hữu và mốc xem lại.

### Decision log đủ dùng

~~~text
MỤC TIÊU CHUYỂN ĐỔI:
  [Kết quả có ích của dòng giá trị]

GIẢ THUYẾT ĐANG THỬ:
  [Nếu thay đổi X thì Y cải thiện vì Z]

PHẠM VI / BASELINE:
  [Team/value stream, work item types, cửa sổ và định nghĩa]

KẾT QUẢ QUAN SÁT:
  [Flow, quality, product outcomes, phản hồi định tính]

GUARDRAILS:
  [Điều kiện đạt/chưa đạt, sự cố cần xử lý ngay]

GIỚI HẠN:
  [Mẫu nhỏ, mùa vụ, biến động mix công việc, tracking]

DECISION:
  [Giữ / sửa / dừng / thử thêm] + lý do

OWNER & NEXT REVIEW:
  [Người có quyền, việc tiếp và mốc kiểm tra]
~~~

### Quyền hành động thuộc ai?

Một thử nghiệm WIP trong team có thể do nhóm và người chịu trách nhiệm flow quyết định trong phạm vi công việc. Đổi thứ tự Product Backlog cần Product Owner hoặc người có trách nhiệm sản phẩm. Xóa một bước phê duyệt pháp lý cần người có **quyền quản trị rủi ro**. Chuyển đổi Agile muốn tạo outcome thực phải **gỡ vướng về quyền quyết định**, không biến người tư vấn chuyển đổi thành người ra mọi quyết định thay tổ chức.

### Quyết định “chưa đủ dữ liệu” vẫn cần bước tiếp

Nếu chỉ có năm work items và không có biến động nào đáng tin, có thể giữ thử nghiệm thêm một cửa sổ hợp lý, mở rộng quan sát theo loại việc hoặc làm phỏng vấn định tính. Không nên kéo dài vô hạn với lý do “chưa đủ dữ liệu” nếu cost/risk quá lớn; cần có **mốc quyết định rõ**.

## 25. Case study: chuyển đổi một dòng giá trị của nền tảng học trực tuyến

Trường hợp sau là **mô phỏng có số liệu giả định**, không phải nghiên cứu thực tế. Nó minh họa cách tổ chức một chương trình chuyển đổi thành **chuỗi giả thuyết, thay đổi nhỏ, bằng chứng và quyết định**.

### 25.1. Bối cảnh trước chuyển đổi

Nền tảng cung cấp video học tập, kiểm tra đánh giá và ghi tiến độ học viên. Ba nhóm tham gia trực tiếp vào một thay đổi:

| Nhóm/năng lực | Vai trò | Vấn đề được quan sát |
| --- | --- | --- |
| **Nhóm Trải nghiệm học viên** | Xây UI cho các hành trình học | Story bị chia thành frontend task, khó có lát cắt dùng được |
| **Nhóm Quyền và tiến độ** | API checkpoint, enrollment, authorization | API contract chỉ được xác nhận khi gần tích hợp |
| **Platform/QA/SRE hỗ trợ** | Môi trường, CI, quality/monitoring | Staging dùng chung, kiểm thử hồi quy chậm, pipeline chưa đáng tin |

Các Product Owners nhận yêu cầu tính năng từ nhiều bên; không có cách rõ để phân biệt **giá trị người học** với yêu cầu giao hàng. Scrum events đã được tổ chức đều, nhưng review chức năng vẫn diễn ra cuối Sprint và chỉ vài người có khả năng deploy.

### 25.2. Hiện trạng được xác minh

Sau một thời gian quan sát có định nghĩa đo rõ, nhóm thu được baseline giả định cho **feature PBIs thường lệ**:

| Tín hiệu | Baseline minh họa | Điều cần làm rõ |
| --- | --- | --- |
| Median cycle time từ start tới DoD | 14 ngày làm việc | Đuôi dài và nguồn chờ nằm ở đâu? |
| WIP trung bình của dòng feature | 12 items | Có bao nhiêu item cùng bị blocked? |
| Median thời gian chờ Review/Verify | 4 ngày | Có thiếu reviewer, CI chậm hay chỉ start quá nhiều? |
| Tỷ lệ feature có contract/API tests trước khi tích hợp | 30% | Tests có bảo vệ đúng quy tắc và đáng tin không? |
| Median thời gian từ phát hiện yêu cầu tới có lát cắt thử được | 28 ngày | Lựa chọn story và phụ thuộc đang cản gì? |
| Incident liên quan checkpoint | Chưa đủ baseline đáng tin | Trước tiên phải xác nhận nguồn và định nghĩa |
| Tỷ lệ học viên mở đúng bài trong 60 giây | 48% tác vụ hợp lệ được quan sát | Cần thống nhất eligibility và cách lấy mẫu |

**Đây không phải kết luận rằng mọi triệu chứng đều do “chưa Agile”**. Nhóm cần nhìn một số work items thực, log CI và phản hồi người học để thấy nguyên nhân gần và tránh gán nhãn chung chung.

### 25.3. Product Goal và mục tiêu chuyển đổi là hai câu hỏi khác nhau

**Product Goal:** “Học viên có thể tiếp tục lộ trình học đúng vị trí một cách thuận tiện và tin cậy.”

**Mục tiêu chuyển đổi:** “Dòng feature liên quan tiến độ học tập có thể tạo và kiểm chứng những lát cắt nhỏ, an toàn nhanh hơn, giảm chờ và giúp cập nhật giải pháp từ phản hồi sớm.”

**Giả thuyết chính:** Nếu các nhóm làm rõ ví dụ nghiệp vụ trước khi code, chia user story dọc theo hành trình, tích hợp liên tục với API tests và kiểm soát WIP, thì **thời gian tới DoD và thời gian tới feedback** sẽ giảm mà chất lượng không xấu đi.

### 25.4. Giai đoạn đầu: sửa cách chọn công việc

Nhóm thử các buổi trao đổi ngắn giữa Product Owner, Developers và người có góc nhìn kiểm thử. Thay vì backlog item “xây trang tiến độ đầy đủ”, họ chia lát cắt:

1. Người học đủ quyền mở lại đúng bài đang dở trong trường hợp thông thường.
2. Người không có checkpoint nhận hướng dẫn bắt đầu hợp lệ.
3. Trường hợp checkpoint không còn hợp lệ không được mở nội dung sai quyền.
4. UI thể hiện đúng trạng thái lưu, chờ và thất bại.
5. Mở rộng theo nhu cầu người dùng sau khi đã có bằng chứng.

**Đo:** số lần rework do hiểu sai quy tắc, thời gian chờ clarification, tỷ lệ lát cắt tích hợp có thể dùng thử. **Guardrail:** không được tách story thành các phần frontend/backend rời rạc rồi gọi từng phần là giá trị người dùng.

### 25.5. Giai đoạn tiếp: sửa feedback kỹ thuật

Developers bổ sung unit/API checks cho checkpoint, authorization và integration contract. CI chạy khi thay đổi được tích hợp, khuyến khích PR nhỏ, review sớm, giữ chất lượng tests đáng tin. Platform hỗ trợ đường tạo môi trường thử và observability.

**Đo:** thời gian phát hiện lỗi, tỷ lệ flaky tests, review waiting time, số lỗi nghiêm trọng lọt qua release. **Guardrails:** không giảm mức bảo vệ dữ liệu để đạt tốc độ pipeline.

### 25.6. Song song: thay chính sách flow

Team nhận thấy hàng Review/Verify có nhiều story chờ, nên thử **không bắt đầu item mới khi WIP đã chạm mức phù hợp**, ưu tiên gỡ blocker, review và test để hoàn tất. Mỗi ngày họ xem **work item age và lý do tắc**.

**Đo:** WIP, phân bố cycle time, throughput theo loại feature, thời gian blocked và tải làm việc. **Guardrail:** không giấu blocked items hoặc giữ nguyên giờ làm thêm để ép số liệu.

### 25.7. Sau các vòng thử: kết quả giả định

Sau hai đến ba vòng làm việc đủ để quan sát, nhóm ghi:

| Tín hiệu | Trước | Sau | Cách đọc có trách nhiệm |
| --- | ---: | ---: | --- |
| Median cycle time feature | 14 ngày | 9 ngày | Tín hiệu cải thiện; cần xem mix và phân bố |
| WIP trung bình | 12 | 7 | Ít việc dở hơn, xem có bị đẩy việc ra ngoài board không |
| Median chờ review | 4 ngày | 1,5 ngày | Phù hợp giả thuyết giảm hàng chờ |
| Time-to-testable-slice | 28 ngày | 15 ngày | Có thể nhận feedback sớm hơn |
| API tests ở lát cắt đủ điều kiện | 30% | 85% | **Mức áp dụng thực hành**, chưa tự chứng minh chất lượng |
| Tỷ lệ task success Học tiếp | 48% | 65% | Có tín hiệu giá trị, cần kiểm tra cohort/exposure và nguyên nhân |
| Lỗi checkpoint nghiêm trọng | Baseline chưa đáng tin | Có giám sát và tests phù hợp hơn | Không tuyên bố giảm lỗi từ số không so sánh được |

### 25.8. Kết quả bất lợi buộc nhóm đổi hướng

Phản hồi cho thấy **người dùng mobile vẫn nhấn nhiều lần do nút “Học tiếp” khó nhìn**, trong khi desktop cải thiện. Nếu chỉ báo “task success tổng tăng”, nhóm sẽ bỏ sót rủi ro cho một phân khúc.

**Quyết định sản phẩm:** ưu tiên nghiên cứu màn hình nhỏ và thử nhãn/vị trí mới; Product Owner điều chỉnh Product Backlog theo feedback.

**Quyết định chuyển đổi:** giữ cơ chế CI và làm rõ ví dụ đã giúp feedback sớm, nhưng thử thêm một cải tiến **quan sát user journey trên thiết bị hỗ trợ**, thay vì coi việc dùng Scrum đã giải quyết mọi vấn đề.

### 25.9. Cách viết báo cáo có căn cứ

> “Trên dòng feature tiến độ học tập, sau khi thử các thay đổi về slicing, WIP và CI, median cycle time giảm từ 14 xuống 9 ngày và thời gian tới lát cắt kiểm chứng được từ 28 xuống 15 ngày theo phạm vi đã thống nhất. Task success Học tiếp tăng trong mẫu quan sát, nhưng mobile vẫn có trở ngại; baseline incident trước thử chưa đáng tin để kết luận chất lượng đã tăng. Chúng tôi giữ những thực hành có bằng chứng hữu ích, xử lý guardrails và kiểm tra tiếp trên các nhóm người dùng khác trước khi mở rộng.”

Nội dung này cho thấy **điều đã thay đổi, kết quả, giới hạn và quyết định**. Nó không tô vẽ thành “chuyển đổi Agile thành công 100%”.

## 26. Dashboard chuyển đổi: ít chỉ số nhưng đi cùng câu hỏi quyết định

Một báo cáo điều hành không cần hiển thị mọi dữ liệu của Jira, Git, CI và khảo sát. Nó nên giúp trả lời **tổ chức đang có thể tạo giá trị tốt hơn không, ở đâu còn rủi ro, cần đầu tư hoặc thay đổi chính sách gì**.

### Bảng điều hành minh họa

| Câu hỏi quản trị | Metric chính | Diagnostic | Guardrail | Nhịp review |
| --- | --- | --- | --- | --- |
| Học viên có được lợi? | Task success của hành trình trọng yếu | Funnel, lỗi UX, phân khúc | Không mất dữ liệu/sai quyền | Theo cohort/exposure |
| Có thể kiểm tra ý tưởng sớm hơn? | Time-to-testable-slice | Chờ quyết định, story size, dependency | Không thử trên người dùng thiếu an toàn | Theo vòng sản phẩm |
| Công việc có đi tới Done ổn định? | Cycle time distribution | WIP, work item age, blocked time | Rework/defects, làm thêm giờ | Hằng tuần |
| Có thể thay đổi mã an toàn? | Time-to-feedback kỹ thuật/lead time phù hợp | Build reliability, test duration, contract failures | Change failure/incident impacts | Theo CI/release |
| Nhóm có học và cải tiến? | Giả thuyết được đóng bằng quyết định có bằng chứng | Decision log, retrospective follow-through | Không khuyến khích tạo experiments hình thức | Theo chu kỳ cải tiến |
| Người làm có nhịp bền vững? | Phản hồi tập trung vào trở ngại và tải | Interruption, dependency, overtime trends | Không lộ thông tin cá nhân | Theo chu kỳ đủ an toàn |

### Mỗi metric phải có owner và định nghĩa

**Owner của metric** bảo trì chất lượng định nghĩa và dữ liệu; không có nghĩa **một người chịu trách nhiệm cá nhân cho việc metric tăng/giảm**. Ví dụ cycle time là đặc tính của hệ thống công việc, chịu ảnh hưởng bởi phụ thuộc, chính sách và loại việc. Một manager không nên dùng nó để xếp hạng từng Developer.

### Cách báo cáo một mốc thay đổi

~~~text
MỤC TIÊU:
  Giảm time-to-feedback của lát cắt tiến độ học tập.

PHẠM VI / ĐỊNH NGHĨA:
  Feature PBIs cùng loại, ranh giới start tới DoD.

BASELINE:
  [Median + phân bố + số item + cửa sổ trước]

KẾT QUẢ:
  [Median + phân bố + số item + cửa sổ sau]

DIAGNOSTICS:
  [WIP, blocked reasons, CI reliability]

GUARDRAILS:
  [Lỗi quyền, checkpoint, làm thêm giờ và phản hồi]

MỨC TIN CẬY:
  [Điều kiện đã so được và lời giải thích thay thế]

QUYẾT ĐỊNH:
  [Giữ, sửa, dừng, mở rộng] + owner + review date
~~~

**Đừng dùng màu xanh/đỏ thay diễn giải.** Một giai đoạn có nhiều lỗi được phát hiện hơn trước release có thể là **tín hiệu kiểm thử tốt hơn**, không tự chứng minh chất lượng tệ đi. Ngược lại, ít bug tickets không đồng nghĩa an toàn khi người dùng khó báo lỗi.

## 27. Mở rộng chuyển đổi: nhân rộng điều kiện thành công, không nhân bản nghi thức

Sau một pilot có kết quả tích cực, tổ chức dễ yêu cầu: “Từ tháng sau, mọi team phải dùng board và WIP limit giống nhau.” Điều này thường bỏ qua **tại sao cách làm hiệu quả trong một bối cảnh**.

### Cần phân biệt khả năng tái sử dụng

| Có thể chuẩn hóa tương đối rộng | Thường cần tùy bối cảnh |
| --- | --- |
| Nguyên tắc giữ chất lượng và dữ liệu người dùng | Cách chia Product Backlog và kích thước lát cắt |
| Chính sách bảo mật bắt buộc, kiểm soát secrets | WIP limit cụ thể của từng workflow |
| Chuẩn định nghĩa “Done” đối với một sản phẩm chung | Tần suất và hình thức các nhịp phối hợp |
| Những API contracts và công cụ CI phục vụ nhiều team | Cách xử lý nhu cầu R&D với uncertainty cao |
| Cơ chế làm rõ decision rights và escalation | Chi tiết onboarding, team topology và kỹ năng |
| Cách công bố metric definitions/guardrails | Target kết quả của các dòng giá trị khác nhau |

### Mẫu mở rộng từng bước

1. **Nêu điều kiện pilot:** loại sản phẩm, team size, phụ thuộc, năng lực kỹ thuật, rủi ro.
2. **Giải thích cơ chế:** thay đổi nào có khả năng tạo kết quả và bằng chứng nào hỗ trợ?
3. **Chọn nơi thử tiếp:** tương đồng đủ để học, nhưng không chỉ chọn nhóm chắc chắn thành công.
4. **Cung cấp hỗ trợ:** coaching, platform capability, tài liệu, thời gian cải tiến.
5. **Cho phép thích ứng:** giữ nguyên tắc và quality guardrails, điều chỉnh implementation theo bối cảnh.
6. **Đo lại:** baseline riêng của dòng giá trị mới, không sao chép target của team pilot.
7. **Học từ khác biệt:** điều hiệu quả ở một nhóm có thể không tạo kết quả ở nhóm khác; ghi cơ chế và điều kiện.

### Những phụ thuộc cấp tổ chức cần được xử lý

Nếu việc phê duyệt ngân sách chỉ cho phép dự án theo scope cố định một năm và yêu cầu mọi thay đổi phải qua nhiều tầng, một Scrum Team riêng **không thể tự sửa toàn bộ**. Lãnh đạo cần xem lại **portfolio funding, ưu tiên, phân bổ chuyên gia dùng chung, platform self-service và quyền quyết định**. Gọi đó là “kháng cự thay đổi của team” sẽ bỏ qua nguyên nhân hệ thống.

### Mở rộng chất lượng, không mở rộng sự tuân thủ

Một tổ chức có thể thống nhất **nguyên tắc**: có Product Goal rõ, kiểm chứng giá trị sớm, Increment đáp ứng DoD, rủi ro được minh bạch và cải tiến dựa trên bằng chứng. Không nên bắt mọi team có cùng một form retrospective, cùng số story points hay cùng bốn cột Kanban nếu điều ấy không giúp dòng giá trị.

## 28. Khi nào chuyển đổi cần thay cấu trúc tổ chức?

Đôi khi điều chỉnh chính sách và kỹ thuật trong team **không đủ**, vì cơ cấu tổ chức tạo ra handoff cố hữu: nhóm frontend nhận tất cả yêu cầu, nhóm backend xử lý sau, QA là hàng đợi cuối và vận hành chỉ triển khai khi mọi dự án cùng xong.

### Dấu hiệu cần xem xét ranh giới nhóm

- Mỗi user story phải đi qua **nhiều queue chuyên môn** dù phạm vi thay đổi nhỏ.
- Các nhóm không có khả năng giao một **vertical slice end-to-end**.
- Một service chuyên gia chung phải duyệt hầu hết thay đổi với rủi ro thấp.
- Backlog riêng bị tối ưu cục bộ, **không ai sở hữu outcome người dùng**.
- Nhiều team code cùng một thành phần nhưng không có contract/ownership rõ.
- Context switching cao vì mỗi người bị phân bổ **một phần nhỏ vào quá nhiều dự án**.

### Không phải cứ lập “squad” là hết phụ thuộc

Đổi tên phòng thành squad mà vẫn phân bổ cùng chuyên gia 10% cho mỗi nhóm, giữ các tầng phê duyệt cũ và thiếu CI có thể **không thay đổi outcome**. Một thay đổi cấu trúc có chi phí về kiến thức, vận hành, quyền truy cập và sự ổn định con người. Cần xác định **đâu là vấn đề thực**, lựa chọn phạm vi và theo dõi tác động sau thay đổi.

### Có thể tham khảo thiết kế theo dòng giá trị

Một nhóm **gần với dòng giá trị/nhu cầu người dùng** có thể sở hữu đủ năng lực để giao lát cắt, được hỗ trợ bởi **platform capabilities dùng chung** và chuyên gia enablement. Nhưng không nên ép mọi nhóm tự biết mọi lĩnh vực phức tạp. Một số subsystem chuyên sâu vẫn cần nhóm sở hữu riêng với **interface, contract và trách nhiệm rõ**.

### Kết quả để đánh giá tái cấu trúc

Nếu giảm handoff nhưng tăng tải cognitive load khiến lỗi và làm thêm giờ tăng, mô hình mới cần điều chỉnh. Nếu giao tiếp giảm nhưng Product Goal mất rõ ràng, phải làm lại cơ chế điều phối sản phẩm. **Org chart mới chỉ là output của chuyển đổi**, không tự là outcome.

## 29. Những phản mẫu khiến mục tiêu chuyển đổi trở thành hình thức

### 29.1. “Tất cả team phải chạy Scrum trong ba tháng”

Đếm số team áp dụng nghi thức, không xác định vấn đề cần giải quyết. **Cải tiến:** mô tả outcome của từng dòng giá trị, chọn Scrum/Kanban/XP theo nhu cầu và đo kết quả thực.

### 29.2. “Velocity tăng 30% là chuyển đổi thành công”

Story points không phải đơn vị giá trị hay năng suất có thể so xuyên team. **Cải tiến:** theo dõi flow, chất lượng và outcome người dùng với định nghĩa thống nhất; không xếp hạng team theo velocity.

### 29.3. “Càng nhiều cuộc họp Agile càng hợp tác”

Một chuỗi planning, sync, review và committee không có quyết định làm tăng thời gian chờ. **Cải tiến:** mỗi nhịp feedback cần mục đích, owner và hành động; bỏ các vòng trùng lặp.

### 29.4. “Đã đào tạo là mọi người sẽ đổi hành vi”

Nhân viên biết lý thuyết nhưng hệ thống vẫn thưởng cho việc bận rộn và phạt khi báo lỗi. **Cải tiến:** xem quyền quyết định, chính sách, công cụ, coaching và phản hồi thực tế sau đào tạo.

### 29.5. “Chuyển đổi là trách nhiệm của Scrum Master/Agile Coach”

Coach có thể hỗ trợ, nhưng không thể thay quyền quyết định và đầu tư của lãnh đạo, Product Owner và Developers. **Cải tiến:** phân vai theo quyết định cần thay đổi, gắn người chịu trách nhiệm và capacity.

### 29.6. “Đổi tên PM thành Product Owner là đủ”

Không có quyền sắp backlog, không thể phản hồi người dùng, nhưng vẫn chịu KPI giá trị. **Cải tiến:** thống nhất ownership, quyền ra quyết định và nguồn bằng chứng sản phẩm.

### 29.7. “Điều chỉnh Definition of Done để kịp báo cáo”

Lỗi bị chuyển sang production hoặc Sprint sau. **Cải tiến:** giảm phạm vi, làm rõ dự báo, đầu tư kỹ thuật; giữ điều kiện chất lượng bắt buộc.

### 29.8. “Chúng tôi đã có CI vì build tự chạy”

CI chạy build nhưng không có contract/security tests quan trọng, pipeline flaky hoặc branch tích hợp quá muộn. **Cải tiến:** đo thời gian tới phản hồi đáng tin và lỗi bắt được sớm.

### 29.9. “Đóng càng nhiều tickets càng tốt”

Có thể chia vụn công việc mà không giao lát cắt có giá trị. **Cải tiến:** xem Increment end-to-end và outcome, không coi số ticket là năng suất.

### 29.10. “Mọi team phải có cùng WIP limit”

Team support và team phát triển sản phẩm có nhịp, nhu cầu, kỹ năng khác nhau. **Cải tiến:** công khai Definition of Workflow và thử WIP control theo dữ liệu thật.

### 29.11. “Dùng một dashboard để so sánh mọi nhóm”

Khác loại việc, độ rủi ro và ranh giới khiến cycle time không so trực tiếp. **Cải tiến:** xem xu hướng trong bối cảnh, phân khúc và guardrails; tránh xếp hạng đơn giản.

### 29.12. “Thấy conversion tăng là nhờ Agile”

Kết quả người dùng có thể đổi do lịch học, marketing hoặc thiết kế sản phẩm riêng. **Cải tiến:** nêu giả thuyết, kiểm tra cohort, thời gian, bằng chứng bổ trợ và mức bất định.

### 29.13. “Chỉ báo cáo metric đang xanh”

Nhóm bỏ qua lỗi mobile, sự cố dữ liệu hoặc người phải tăng ca. **Cải tiến:** xem toàn bộ guardrails và những trường hợp trái kỳ vọng; báo cáo trung thực điều chưa biết.

### 29.14. “Không thấy lỗi nghĩa là chất lượng đã tốt”

Ít người dùng thử hoặc logging thiếu có thể che lỗi. **Cải tiến:** tests đúng rủi ro, monitoring, exploratory testing và incident learning.

### 29.15. “Mỗi quý đều phải đạt một target bất kể bối cảnh”

Thúc đẩy thay denominator, sửa ngày Done và né việc khó. **Cải tiến:** target có lý do, phiên bản metric và đánh giá theo bằng chứng; mục tiêu để học, không ép dữ liệu phục vụ con số.

### 29.16. “Chuyển đổi phải xong sau một năm”

Đạt mốc tổ chức không đồng nghĩa có năng lực thích ứng bền vững. **Cải tiến:** xem các vòng cải tiến và khả năng tự nhận diện, giải quyết vấn đề mới; không xây chương trình tồn tại mãi không có kết quả.

### 29.17. “Muốn nhanh hơn thì mọi người bận 100%”

Thiếu năng lực review, học và xử lý incident dẫn tới chờ và chuyển ngữ cảnh. **Cải tiến:** WIP, ưu tiên hoàn tất, hỗ trợ chéo và năng lực cải tiến dựa trên rủi ro.

### 29.18. “Đổi cấu trúc tổ chức là đã loại phụ thuộc”

Org chart đổi tên, nhưng service/approval cũ còn nguyên. **Cải tiến:** đo số handoff, time-to-unblock, ownership và khả năng giao vertical slice.

### 29.19. “Retrospective thành công khi tạo nhiều action items”

Không thử/đánh giá hành động nào, vấn đề lặp lại. **Cải tiến:** chọn một giả thuyết trọng tâm có owner, timebox, guardrails và mốc review.

### 29.20. “Kết quả pilot tốt nên ép mọi nơi làm y hệt”

Thay đổi môi trường, kỹ năng và nhu cầu có thể làm mô hình không phù hợp. **Cải tiến:** nhân rộng nguyên tắc và cơ chế đã hiểu, đo baseline riêng và điều chỉnh theo bối cảnh.

### 29.21. “Con người chống thay đổi nên ta cần giám sát chặt”

Sự dè dặt có thể phản ánh rủi ro thực: quá tải, mâu thuẫn quyền, thiếu thời gian học hoặc mất an toàn tâm lý. **Cải tiến:** hỏi những ví dụ cụ thể, minh bạch trade-off, tạo quyền thử và phản hồi, không gắn nhãn cá nhân.

### 29.22. “Đã có metric là mọi quyết định data-driven”

Dashboard được cập nhật nhưng roadmap bất biến, chính sách cũ không ai sửa. **Cải tiến:** decision log ghi rõ điều giữ/sửa/dừng sau khi nhìn kết quả, với người có quyền hành động.

## 30. Workshop 90 phút: xây mục tiêu chuyển đổi từ một vấn đề thực

Workshop này là **bài tập mô phỏng**, không phải một nghi thức bắt buộc của Agile. Có thể tổ chức với Product Owner, Developers, người có năng lực kiểm thử, người hỗ trợ flow/Agile và đại diện có quyền gỡ trở ngại tổ chức.

### Tình huống

Ba nhóm đang phát triển nền tảng học trực tuyến. Trong sáu tuần gần đây, nhiều feature PBIs chờ review hơn một tuần, CI không ổn định, khả năng deploy phụ thuộc một người, và người học phàn nàn phải chờ lâu để lỗi checkpoint được sửa.

| Bước | Thời lượng gợi ý | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Nhìn vấn đề người dùng** | 10 phút | Đọc phản hồi học viên và hành trình có vấn đề | Problem statement theo giá trị |
| **2. Vẽ value stream hiện tại** | 15 phút | Đi theo một feature từ start tới DoD và release | Điểm chờ, phụ thuộc và nguồn dữ liệu |
| **3. Phân loại bằng chứng** | 10 phút | Tách activity/output/capability/outcome/impact | Những metric cần giữ, những KPI hình thức |
| **4. Viết mục tiêu chuyển đổi** | 15 phút | Đối tượng, baseline hoặc kế hoạch đo, target, guardrails, horizon | Goal statement có thể kiểm chứng |
| **5. Lập theory of change** | 10 phút | Chọn chính sách/kỹ thuật/phối hợp cần thử và cơ chế | Hai–ba giả thuyết, một ưu tiên đầu |
| **6. Thiết kế experiment** | 15 phút | Scope, owner, WIP, checks, cách thu dữ liệu và ngưỡng dừng | Experiment card có thể thực hiện |
| **7. Giả lập kết quả** | 10 phút | Review số liệu tốt/xấu/mơ hồ, rủi ro và lời giải thích khác | Decision log: giữ/sửa/dừng |
| **8. Chốt hành động** | 5 phút | Người sở hữu, mốc review và cách chia sẻ | Việc tiếp theo và điều kiện kiểm tra |

### Dữ liệu đầu vào minh họa

| Metric | Trước thay đổi | Sau một vòng thử |
| --- | ---: | ---: |
| Median cycle time feature | 12 ngày | 8 ngày |
| WIP trung bình | 11 items | 7 items |
| Median review waiting time | 4 ngày | 2 ngày |
| Feature PBIs có contract tests phù hợp | 30% | 70% |
| Lỗi mất checkpoint có ảnh hưởng nghiêm trọng | 0 ca được ghi trong kỳ trước | 1 ca được phát hiện trong kỳ thử |
| Tỷ lệ task success mobile | 42% | 43% |

**Câu hỏi trọng tâm:** Có thể tuyên bố chuyển đổi thành công vì flow tốt hơn không, khi một sự cố nghiêm trọng xuất hiện và outcome mobile gần như không đổi? Cần đánh giá **khả năng phát hiện lỗi, tác động dữ liệu, mức bảo vệ, nguyên nhân và chất lượng các nguồn đo**. Một sự cố nghiêm trọng có thể yêu cầu xử lý ngay trước khi mở rộng, bất kể median cycle time.

### Tiêu chí hoàn thành workshop

- Mục tiêu nói rõ **ai hưởng lợi, điều gì thay đổi và cách kiểm chứng**.
- Có **một giả thuyết cơ chế**, không chỉ “hãy Agile hơn”.
- Metric có ranh giới và population, không gộp số bất tương đồng.
- Có **guardrails an toàn, chất lượng và tính bền vững**.
- Có phép thử đủ nhỏ với **owner, cửa sổ quan sát và điều kiện dừng**.
- Kết luận ghi nhận **lời giải thích thay thế và mức bất định**.
- Kết quả workshop dẫn tới một **quyết định thực**, không chỉ tài liệu đẹp.

## 31. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Phân loại chỉ số chuyển đổi

Hãy phân loại activity, output, capability, outcome hoặc impact cho các phát biểu:

1. “Tổ chức đào tạo 200 nhân viên về Scrum.”
2. “Mọi team có bảng Kanban và Definition of Workflow.”
3. “Developers có thể tự tạo staging đạt chuẩn mà không chờ chuyên gia.”
4. “Median thời gian từ start tới DoD giảm ở các feature PBIs tương đồng.”
5. “Học viên ít bị gián đoạn do lỗi mất tiến độ và đạt mục tiêu học tập đáng tin hơn.”

**Gợi ý:** (1) activity; (2) output; (3) capability; (4) outcome flow; (5) kết hợp product outcome và impact dài hạn, cần kiểm tra cách đo.

### Bài tập B — Viết lại mục tiêu hình thức

Phát biểu ban đầu:

> “Trong quý tới, 100% nhóm áp dụng Scrum, hoàn thành tối thiểu 40 story points mỗi Sprint và tổ chức ít nhất ba cuộc họp Agile mỗi tuần.”

Hãy viết lại thành mục tiêu gồm **đối tượng, vấn đề, baseline, outcome, thời hạn, guardrails và mốc quyết định**. Nếu chưa có baseline, nêu **kế hoạch đo thay vì bịa số**.

**Gợi ý:** Có thể chọn “giảm thời gian chờ tích hợp và làm rõ yêu cầu cho dòng tính năng học tập” kèm định nghĩa cycle time, work item age và lỗi dữ liệu.

### Bài tập C — Tính và diễn giải

Một nhóm có cycle time (ngày) trước thay đổi: 4, 6, 9, 12, 19. Sau thay đổi: 3, 5, 6, 10, 15.

1. Median trước và sau?
2. Mức giảm tuyệt đối và tương đối của median?
3. Vì sao không thể nói mọi item đều nhanh lên đúng cùng tỷ lệ?
4. Guardrails nào phải được xem kèm?

**Gợi ý:** Median trước **9**, sau **6**, giảm **3 ngày**, tương đối \(3/9\approx33{,}3\%\). Còn phải xem loại việc, đuôi dài, chất lượng, rework và tải nhóm.

### Bài tập D — Data quality và Definition of Done

Trước chuyển đổi, hệ thống tính Done khi đạt kiểm thử tích hợp; sau chuyển đổi, một manager muốn đổi Done thành “PR merged” để cycle time giảm.

1. Vì sao so sánh sẽ sai?
2. Tác động tới Increment và guardrails ra sao?
3. Có thể đo riêng **code merge time** và **time-to-DoD** thế nào?

**Gợi ý:** Không hạ điều kiện chất lượng; có thể đo hai mốc khác nhau nếu chúng phục vụ những câu hỏi khác nhau và được công bố rõ.

### Bài tập E — Outcome tốt nhưng năng lực giao hàng xấu

Tính năng Học tiếp giúp tác vụ nhanh hơn nhưng mỗi lần sửa lỗi cần ba tuần chờ deploy. Xác định:

- Một mục tiêu Product Goal liên quan người học.
- Một mục tiêu chuyển đổi về khả năng phản hồi/giao hàng.
- Một thử nghiệm kỹ thuật hoặc chính sách.
- Một metric product outcome, hai metrics flow/engineering và hai guardrails.

**Gợi ý:** Đừng lấy deployment frequency làm product outcome. Đo thời gian tới bản sửa an toàn và tác vụ học thật; thử CI/self-service hoặc giảm phê duyệt không cần thiết trong phạm vi policy.

### Bài tập F — Những ai phải thay đổi?

Scrum Team muốn ưu tiên sửa lỗi tiến độ theo dữ liệu người dùng, nhưng roadmap cố định và mọi thay đổi phải qua bốn quản lý.

1. Team tự cải tiến được những gì?
2. Quyền quyết định nào phải được làm rõ ở cấp khác?
3. Tại sao thêm một Scrum Master chưa giải quyết ngay?
4. Bằng chứng nào giúp lãnh đạo đánh giá trade-off?

**Gợi ý:** Xem quyền Product Owner, chính sách phê duyệt, đầu tư theo outcome, mức rủi ro và chi phí chờ; phân biệt kiểm soát bắt buộc với lãng phí.

### Bài tập G — Pilot thành công giả

Team pilot có thêm hai chuyên gia, chỉ làm feature nhỏ, ít incident và giảm median cycle time từ 15 xuống 6 ngày; các team khác vẫn phải đợi review bảo mật.

1. Kết quả nào là tín hiệu có ích?
2. Những yếu tố gây thiên lệch?
3. Có nên bắt mọi team dùng y hệt mô hình pilot ngay?
4. Nên thử tiếp ở phạm vi nào?

**Gợi ý:** So cùng loại việc, ghi điều kiện được cấp thêm năng lực, xem phụ thuộc chuyên gia, quality, flow và sản phẩm; nhân rộng có kiểm chứng.

### Bài tập H — OKR và Goodhart

Lãnh đạo đặt KR “mọi nhóm tăng velocity 25%” và thưởng cho nhóm đạt cao nhất. Sau hai Sprint, story points tăng, nhưng nhiều item chưa được tích hợp.

Hãy giải thích **hành vi tối ưu metric**, đề xuất một cách đo **kết quả end-to-end** và thiết kế guardrails.

**Gợi ý:** Story points là ước lượng nội bộ; cần xem Increment, DoD, cycle time, lỗi và product outcome, không so velocity giữa team.

### Bài tập I — Trước/sau không chứng minh nhân quả

D7 meaningful return tăng sau một đợt chuyển đổi, nhưng cùng thời điểm trường bắt đầu học kỳ và gửi thông báo nhắc học.

1. Nêu ít nhất ba lời giải thích khác.
2. Thiết kế cách kiểm chứng tiếp phù hợp.
3. Viết một câu báo cáo trung thực không quy kết nhân quả quá mức.

**Gợi ý:** Mùa vụ, nguồn học viên, thông báo, tracking; phân tích cohort, phân khúc, trước/sau có bối cảnh hoặc thử nghiệm có đối chứng khi an toàn và khả thi.

### Bài tập J — Giữ, sửa, dừng hay thử thêm?

Sau thử WIP limit, cycle time tốt hơn, nhưng feedback cho thấy Developers bị thiếu việc khi chờ môi trường chung và giờ làm thêm ở platform team tăng.

1. Có nên giữ nguyên WIP limit?
2. Điểm nghẽn nào đã dịch chuyển?
3. Cần đo và điều chỉnh chính sách ở đâu?
4. Ai chịu trách nhiệm thay đổi phụ thuộc ở cấp platform?

**Gợi ý:** Xem flow toàn hệ thống, blocked age, self-service và tải platform. Một cải tiến cục bộ có thể tạo nghẽn ở bước khác.

### Bài tập K — Bảo vệ niềm tin khi thu thập dữ liệu

Một chương trình chuyển đổi định công bố bảng xếp hạng các Developers theo số ticket hoàn thành và số lỗi phát sinh.

Hãy đề xuất cách **đo tiến bộ ở cấp hệ thống** mà vẫn giải trình được trách nhiệm, không khiến mọi người giấu blocker hay né việc phức tạp.

**Gợi ý:** Dùng định nghĩa rõ của dòng giá trị, metric tổng hợp theo bối cảnh, chất lượng/phản hồi và trao đổi đóng góp chuyên môn, tránh gán kết quả hệ thống cho một cá nhân.

### Bài tập L — Lập decision log

Giả sử sau ba tuần thử CI và review sớm, tỷ lệ build thất bại giảm nhưng tỷ lệ người học mở lại bài chưa thay đổi. Viết decision log 10–12 dòng gồm **bằng chứng đã có, điều chưa rõ, quyết định và mốc học tiếp**.

**Gợi ý:** Có thể ghi nhận **technical capability đã tiến bộ** nhưng cần xem liệu tính năng mới đã tới người học, thiết kế có giải quyết nhu cầu và tracking đủ tin cậy chưa.

## 32. Mẫu mục tiêu chuyển đổi một trang có thể dùng ngay

Mục đích của mẫu là buộc người viết **liên kết vấn đề–thay đổi–kết quả–quyết định** mà không yêu cầu tạo một hồ sơ quản trị quá nặng.

~~~text
TÊN DÒNG GIÁ TRỊ / PHẠM VI:
  [Ví dụ: phát triển và phát hành tính năng tiến độ học tập]

NGƯỜI NHẬN GIÁ TRỊ:
  [Học viên, giảng viên, nhóm vận hành, đội phát triển...]

VẤN ĐỀ THỰC:
  [Quan sát và bằng chứng, không đổ lỗi cho cá nhân]

OUTCOME CHUYỂN ĐỔI:
  [Năng lực/kết quả mong muốn cải thiện và vì sao quan trọng]

BASELINE:
  [Metric definitions, nguồn, số mẫu, cửa sổ, mức tin cậy]

TARGET / THỜI HẠN:
  [Ngưỡng có ý nghĩa, căn cứ lựa chọn, kỳ đánh giá]

THEORY OF CHANGE:
  [Nếu đổi policy/engineering/collaboration X,
   thì kết quả Y cải thiện nhờ cơ chế Z]

EXPERIMENT 1:
  [Phạm vi, owner, việc thử, thời gian, điều kiện dừng]

PRIMARY OUTCOME METRIC:
  [Đơn vị, population, numerator/denominator hoặc start/finish]

DIAGNOSTICS:
  [WIP, age, blocked time, test feedback, câu hỏi cần làm rõ...]

GUARDRAILS:
  [Bảo mật/dữ liệu, chất lượng, trải nghiệm, sức khỏe nhóm]

EVIDENCE REVIEW:
  [Ai tham gia, xem dữ liệu và người dùng khi nào?]

DECISION RULE:
  [Khi nào giữ, sửa, mở rộng, dừng hoặc tìm hiểu thêm?]

CHƯA BIẾT:
  [Giả định, dữ liệu thiếu, lời giải thích thay thế]
~~~

### Bản điền ngắn minh họa

| Thành phần | Ví dụ cho dòng “Học tiếp” |
| --- | --- |
| **Vấn đề** | Lỗi checkpoint phát hiện muộn; nhiều story chờ tích hợp và kiểm thử |
| **Outcome chuyển đổi** | Có thể đưa lát cắt đạt DoD tới kiểm chứng người dùng sớm hơn, chất lượng không xấu |
| **Baseline** | Median cycle time 14 ngày trong tập feature cùng định nghĩa, kèm phân bố và số item |
| **Target giả định** | Phấn đấu giảm về 9 ngày trong hai quý nếu mức này có ý nghĩa với khả năng đáp ứng |
| **Thay đổi thử** | CI/API tests, clarification sớm, giới hạn WIP ở Review/Verify |
| **Dữ liệu hỗ trợ** | Build feedback, blocked time, age, review waiting, rework |
| **Guardrails** | Phân quyền, mất tiến độ, incident, overtime và tính đúng dữ liệu đo |
| **Product outcome đối chiếu** | Người học mở đúng bài nhanh và tin cậy hơn trong mẫu đủ điều kiện |
| **Review** | Theo các vòng làm việc và khi đủ cửa sổ người dùng; kết quả bất lợi xử lý ngay |
| **Decision** | Giữ/sửa/dừng dựa trên flow, quality, outcome, không chỉ số nghi thức Scrum |

Con số trên chỉ minh họa cách điền; **không được dùng làm target mặc định** cho tổ chức khác.

## 33. Checklist xác định mục tiêu chuyển đổi bằng kết quả quan sát

### A. Hiểu đúng mục đích

- [ ] Tổ chức có thể giải thích **vấn đề giá trị hoặc khả năng thích ứng** cần cải thiện mà không dùng “phải Agile hơn” như câu trả lời duy nhất.
- [ ] Phạm vi là **một dòng giá trị/sản phẩm/loại công việc được xác định rõ**, không gom các nhóm khác nhau tùy tiện.
- [ ] Người dùng cuối và các nhóm nội bộ bị ảnh hưởng đã được nhận diện.
- [ ] Phân biệt **activity, output, capability, outcome và impact** trong mục tiêu/báo cáo.
- [ ] Không xem **đào tạo, số cuộc họp, phần mềm quản lý mới hoặc tên chức danh** là bằng chứng chuyển đổi thành công.
- [ ] Có lý do tại sao chọn Scrum, Kanban, XP hoặc kết hợp; không áp thực hành chỉ để giống team khác.

### B. Thiết kế mục tiêu và phép đo

- [ ] Mục tiêu nêu **hành vi/trạng thái thay đổi có thể quan sát** và lợi ích mong muốn.
- [ ] Có **baseline đáng tin**, hoặc nêu rõ bước đo baseline trước khi chốt target.
- [ ] Có **target, thời hạn và căn cứ** cho mức thay đổi được coi là có ý nghĩa.
- [ ] Metric có **population, đơn vị, nguồn dữ liệu, thời gian và định nghĩa vận hành**.
- [ ] Với flow metric, **start/finish, item type và Definition of Workflow** được thống nhất.
- [ ] Không đánh đồng **velocity/story points** với giá trị, năng suất cá nhân hoặc throughput xuyên team.
- [ ] Có **leading signals** để điều chỉnh sớm và **lagging outcomes** để đánh giá giá trị về sau.
- [ ] Số đo định tính và định lượng bổ sung nhau; không suy rộng tùy tiện từ mẫu nhỏ.
- [ ] Có xem **phân khúc, độ biến thiên, item đuôi dài và những người bị ảnh hưởng xấu**.
- [ ] Các thay đổi schema, tracking hoặc workflow definitions được chú thích.
- [ ] Khi có số liệu trước/sau, đã cân nhắc **mùa vụ, loại việc, năng lực chuyên gia và yếu tố đồng thời**.

### C. Giả thuyết và khả năng hành động

- [ ] Có **theory of change** giải thích vì sao can thiệp được chọn sẽ tạo outcome.
- [ ] Mỗi cải tiến quan trọng có **phạm vi, owner, cách làm, thời gian và điều kiện dừng**.
- [ ] Phản hồi thật có khả năng **đổi Product Backlog, chính sách flow hoặc thực hành kỹ thuật**.
- [ ] Các quyết định thuộc quyền Product Owner/Developers/lãnh đạo/bảo mật được làm rõ.
- [ ] Có đường xử lý những **phụ thuộc ngoài quyền của team**, không ghi mãi “chờ bên ngoài”.
- [ ] Cải tiến kỹ thuật như CI, TDD, automated testing và refactoring được liên kết với **rủi ro hoặc độ trễ cụ thể**.
- [ ] WIP và công việc blocked được nhìn thấy, không giấu để metric đẹp hơn.
- [ ] Không hạ **Definition of Done** hoặc bỏ kiểm soát bắt buộc để đạt target.
- [ ] Nhóm có **decision log** ghi kết quả, giới hạn, quyết định và mốc xem lại.

### D. Chất lượng và tác động ngoài ý muốn

- [ ] Có **guardrails dữ liệu, bảo mật, reliability và chất lượng trải nghiệm** phù hợp.
- [ ] Có cách phản ứng **ngay** khi phát hiện rủi ro nghiêm trọng, không đợi kỳ review.
- [ ] Theo dõi nhịp làm việc bền vững, không tăng năng suất bằng tăng ca/ép tải không giới hạn.
- [ ] Không dùng số liệu chuyển đổi để **xếp hạng hay trừng phạt cá nhân**, gây che giấu vấn đề.
- [ ] Có cơ chế bảo vệ phản hồi trung thực, không ép nhân viên trả lời khảo sát theo điều được mong đợi.
- [ ] Có thể giải thích vì sao một chỉ số tốt lên **chưa chắc tạo tác động nhân quả**.

### E. Mở rộng và cải tiến liên tục

- [ ] Pilot có điều kiện thực nghiệm được mô tả, không coi kết quả là chuẩn cho mọi team.
- [ ] Khi nhân rộng, giữ **nguyên tắc và quality guardrails**, cho phép điều chỉnh cách làm theo bối cảnh.
- [ ] Thành công được đo bằng **năng lực tạo giá trị lặp lại và khả năng tự cải tiến**, không chỉ mốc kết thúc chương trình.
- [ ] Kết quả không như mong đợi dẫn tới **sửa giả thuyết hoặc đổi hướng**, không bị che giấu.
- [ ] Có người chịu trách nhiệm duy trì metric definitions, chính sách và vòng review mà không tạo bộ máy báo cáo quá tải.

## 34. Tài liệu đọc thêm và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/) và [12 nguyên tắc Agile](https://agilemanifesto.org/principles.html): ưu tiên phần mềm hoạt động, cộng tác với khách hàng, chấp nhận phản hồi và cải tiến liên tục.
- [The Scrum Guide](https://scrumguides.org/): Product Goal, Sprint Goal, Product Backlog, Increment, Definition of Done, trách nhiệm của Scrum Team và kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age, Service Level Expectation và cải tiến dòng công việc.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): các vòng phản hồi kỹ thuật, TDD, CI, refactoring và small releases.
- Jez Humble và David Farley, *Continuous Delivery* (2010): nền tảng để giao thay đổi an toàn, thường xuyên và đáng tin.
- Nicole Forsgren, Jez Humble và Gene Kim, *Accelerate: The Science of Lean Software and DevOps* (2018): nghiên cứu năng lực giao phần mềm và kết quả tổ chức.
- [DORA](https://dora.dev/): nghiên cứu và hướng dẫn thực hành đo năng lực giao phần mềm, reliability và cải tiến kỹ thuật.
- Mary và Tom Poppendieck, *Lean Software Development: An Agile Toolkit* (2003): tối ưu toàn hệ thống, giảm lãng phí và thiết kế chất lượng vào quá trình.
- Mike Rother, *Toyota Kata* (2009): cải tiến bằng mục tiêu, hiện trạng, giả thuyết và thử nghiệm lặp.
- Eric Ries, *The Lean Startup* (2011): build–measure–learn, giả thuyết giá trị và quyết định đổi hướng.
- Teresa Torres, *Continuous Discovery Habits* (2021): các cách tiếp xúc người dùng và học hỏi liên tục quanh product outcomes.
- Matthew Skelton và Manuel Pais, *Team Topologies* (2019): thiết kế tương tác giữa các nhóm để giảm cognitive load và cải thiện flow.
- [Google SRE Books](https://sre.google/books/): reliability, service level indicators/objectives, sự cố và khả năng quan sát khi vận hành phần mềm.

### Tóm tắt các nguyên tắc thực hành

**Thứ nhất, chuyển đổi Agile phải bắt đầu từ vấn đề thật.** Đừng mở đầu bằng câu “áp Scrum lên toàn công ty”, mà bằng câu “người dùng và hệ thống đang bị chậm hoặc sai ở đâu, điều gì phải tốt lên?”.

**Thứ hai, các hoạt động Agile chỉ có giá trị khi tạo năng lực và kết quả.** Scrum events, Kanban board, TDD, CI hay thay cấu trúc team đều là cách hỗ trợ. Bằng chứng cần là **feedback sớm, Increment đáng tin, dòng giá trị hiệu quả, quyết định tốt hơn và kết quả người dùng**.

**Thứ ba, mục tiêu cần có baseline, cách đo, guardrails và quyết định.** Mọi số liệu phải được đọc theo **đơn vị, phân khúc, thời gian, chất lượng nguồn và độ bất định**; không biến metrics thành cuộc thi hay cách che giấu rủi ro.

**Thứ tư, thay đổi tổ chức phải có quyền và trách nhiệm thực.** Không thể yêu cầu nhóm tự chủ trong khi mọi quyết định vẫn được giữ ở nhiều tầng phê duyệt. Product Owners, Developers, lãnh đạo và các năng lực hỗ trợ cần có cách cộng tác rõ để thay đổi chính sách và hành vi hệ thống.

**Cuối cùng, Agile Transformation không hoàn tất khi mọi team có cùng nghi thức.** Nó tiến bộ khi tổ chức có thể **nhìn thấy một vấn đề, thử cách giải quyết an toàn, kiểm tra bằng chứng, thay đổi hướng và tiếp tục học**. **Mục tiêu chuyển đổi có thể quan sát** là phương tiện làm cho khả năng ấy minh bạch, có trách nhiệm và gắn với giá trị thật — đúng tinh thần **thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục**.
