# Đánh giá tần suất gián đoạn, loại công việc và khả năng bàn giao để lựa chọn cách tiếp cận Agile

> **Ý tưởng cốt lõi:** Không nên chọn Scrum, Kanban hay cách kết hợp chỉ vì đội khác đang áp dụng hoặc vì công cụ có sẵn một mẫu bảng. Trước khi quyết định, hãy xem **công việc thực sự đi vào đội như thế nào**, **bao lâu có việc phải chen ngang**, **mức bất định và thời hạn của từng loại việc**, và **công việc có thể chuyển giữa người/nhóm mà không mất kiến thức, quyền quyết định và chất lượng hay không**. Những quan sát đó giúp lựa chọn nhịp lập kế hoạch, chính sách kéo việc, cơ chế xử lý khẩn cấp và thực hành kỹ thuật phù hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **gián đoạn thật**, thay đổi ưu tiên có kiểm soát, công việc khẩn cấp theo chính sách và nhu cầu hỗ trợ bình thường.
2. Thu thập dữ liệu về **tần suất, thời điểm, mức tác động, độ dài và tính lặp lại** của gián đoạn, thay vì chỉ đếm tin nhắn hoặc số ticket được đánh nhãn gấp.
3. Phân loại công việc theo **nguồn nhu cầu, khả năng dự đoán, mức khẩn, độ bất định, rủi ro, kích thước và yêu cầu chuyên môn**, không đánh đồng mọi Product Backlog Item.
4. Đánh giá **khả năng bàn giao** qua sự rõ ràng của mục tiêu, trạng thái, bằng chứng kiểm tra, tri thức cần có, quyền truy cập, mức ghép cặp và phụ thuộc bên ngoài.
5. Hiểu khi nào một nhịp có Sprint Goal, Product Backlog và Increment của **Scrum** hữu ích, khi nào quản lý **dòng công việc bằng Kanban** hữu ích, và khi nào các thực hành **XP** giúp giảm chi phí chuyển đổi.
6. Đề xuất **cách kết hợp có chủ đích** mà không gọi một bảng Kanban là Scrum, không gọi mọi cuộc họp thành Scrum Event và không bỏ Definition of Done để chạy theo yêu cầu khẩn.
7. Phân bổ năng lực dựa trên **dữ liệu quá khứ và mức bất định**, giữ chính sách cho việc khẩn và kiểm soát WIP mà không hứa tỷ lệ “buffer chuẩn” áp dụng cho mọi đội.
8. Dùng **WIP, throughput, cycle time, work item age, SLE và các tín hiệu chất lượng/outcome** để kiểm tra liệu lựa chọn cách làm có hiệu quả.
9. Thiết kế một thử nghiệm cải tiến nhỏ, có giả thuyết, thời gian xem lại và tiêu chí giữ–sửa–dừng.
10. Phân tích case study nhóm phát triển nền tảng học trực tuyến phải vừa giao chức năng mới, vừa xử lý sự cố, hỗ trợ và phụ thuộc đối tác.

## 2. Tình huống mở đầu: một đội có ba dòng nhu cầu khác nhau

Một đội phát triển nền tảng học trực tuyến có các nhiệm vụ:

- Xây luồng **lưu và tiếp tục bài học**, cần khám phá quy tắc, chia lát cắt và kiểm tra giá trị người dùng.
- Xử lý các **lỗi sản xuất**: đôi khi có sự cố mất tiến độ cần phản ứng ngay; đôi khi chỉ là lỗi hiển thị ít ảnh hưởng.
- Hỗ trợ **đối tác định danh SSO**: yêu cầu cấu hình đến không đều, nhiều việc phải chờ xác nhận bên ngoài.

Đội từng lập Sprint hai tuần. Có Sprint thực hiện đúng kế hoạch, có Sprint bị ngắt quãng bởi sự cố và hàng loạt câu hỏi hỗ trợ. Sau đó một thành viên đề nghị:

> “Chúng ta nên bỏ Scrum, chuyển hết sang Kanban, vì Sprint không phù hợp với đội có nhiều việc phát sinh.”

Một người khác phản đối:

> “Cần giữ Scrum vì không có Sprint thì mọi người sẽ chỉ chạy theo ticket hỗ trợ mà không giao tính năng mới.”

Cả hai nhìn thấy một phần vấn đề, nhưng **chưa đủ dữ kiện để chọn**. Có thể việc ngắt quãng thực sự cao và khó dự đoán; cũng có thể nhóm chỉ thiếu chính sách phân loại sự cố, Product Goal chưa rõ hoặc có nhiều yêu cầu không khẩn được đánh nhãn “khẩn”. Có thể làm luồng hỗ trợ với WIP và chính sách riêng **ngay trong Scrum Team**, hoặc dùng mô hình luồng công việc liên tục mà vẫn duy trì định hướng sản phẩm.

Nhóm cần đánh giá ba trục:

| Trục đánh giá | Câu hỏi | Rủi ro nếu không nhìn |
|---|---|---|
| **Tần suất và tác động gián đoạn** | Bao nhiêu yêu cầu không thể chờ? Chúng lấy mất bao nhiêu năng lực và làm dở bao nhiêu công việc? | Sprint liên tục vỡ kế hoạch hoặc mọi ticket bị gắn nhãn khẩn |
| **Loại công việc** | Feature, discovery, bug, incident, support, vận hành, tuân thủ hay phụ thuộc đối tác? Mỗi loại có độ bất định và thời hạn nào? | Một chính sách áp cho mọi việc, không bảo vệ rủi ro và giá trị |
| **Khả năng bàn giao** | Người khác có thể tiếp tục từ trạng thái, tài liệu, test và quyền sẵn có không? | Nhiều việc mở nhưng kẹt ở một cá nhân, một múi giờ hoặc một bộ phận |

**Lựa chọn cách làm là giả thuyết vận hành cần được kiểm chứng**, không phải cuộc bỏ phiếu “Scrum hay Kanban tốt hơn”.

## 3. Ba trục đánh giá phải được nhìn cùng nhau

### 3.1. Vì sao không thể chỉ nhìn số việc khẩn?

Hai đội đều nhận mười ticket không có trong kế hoạch mỗi tuần:

- **Đội A:** chín ticket là câu hỏi nhỏ, có tài liệu và người tiếp nhận rõ; một ticket thật sự là sự cố ưu tiên cao. Chúng chiếm ít năng lực và có thể xử lý theo lô nhỏ.
- **Đội B:** sáu ticket là gián đoạn bảo mật/sự cố cần điều tra nhiều giờ, liên quan cùng các chuyên gia đang xây feature; việc chuyển đổi ngữ cảnh làm kéo dài mọi PBI.

Nếu chỉ đếm “mười ticket”, hai đội trông giống nhau. Nhưng **tác động tới Sprint Goal, khả năng lập kế hoạch và lưu lượng hoàn tất** rất khác.

Tương tự, một đội có nhiều việc liên tục nhưng **handoff tốt** có thể vận hành theo luồng rõ; một đội ít sự cố nhưng mọi quyết định phải chờ một chuyên gia duy nhất vẫn có hàng đợi dài.

### 3.2. Ma trận ước lượng bằng định tính trước khi có dữ liệu

| Trục | Tình trạng có lợi cho lập kế hoạch theo mục tiêu ngắn hạn | Tình trạng cần quản lý luồng/gián đoạn chặt hơn |
|---|---|---|
| **Nhu cầu đến** | Có phần lớn việc được làm rõ và có thể chủ động chọn | Nhiều việc phát sinh ngẫu nhiên, hạn xử lý khác nhau |
| **Độ khẩn** | Phần lớn có thể đợi điểm ưu tiên kế tiếp | Nhiều trường hợp tác động người dùng nếu chờ |
| **Độ bất định** | Có thể chia lát cắt, làm rõ trong Sprint | Điều tra sự cố, discovery hoặc dependency khó dự báo |
| **Độ dài việc** | Nhiều hạng mục đủ nhỏ để tạo Increment thường xuyên | Một số việc kéo dài, không rõ điểm kết thúc |
| **Bàn giao** | Có trạng thái, test, hợp đồng và tri thức chia sẻ | Phụ thuộc cá nhân, quyền đặc biệt hoặc kiến thức ngầm |
| **Chất lượng phản hồi** | CI/test/DoD cung cấp bằng chứng đáng tin | Kiểm tra muộn, cần nhiều lần hỏi lại |
| **Phụ thuộc** | Nhóm có thể tự chủ phần lớn vòng làm việc | Chờ đối tác, nhóm khác, lịch đánh giá ngoài |

Đây là **khung quan sát**, không phải bộ điểm tuyệt đối. Nhóm có thể ở cả hai cột với những loại việc khác nhau.

### 3.3. Sơ đồ quyết định theo thực nghiệm

~~~mermaid
flowchart TD
    A["Quan sát 2–6 tuần hoặc chu kỳ phù hợp"] --> B["Phân loại nhu cầu, gián đoạn, phụ thuộc"]
    B --> C["Đo tác động lên flow, chất lượng, Sprint Goal"]
    C --> D["Đánh giá khả năng bàn giao / tự chủ"]
    D --> E{"Công việc có thể gom thành mục tiêu ngắn hạn?"}
    E -->|"Phần lớn có"| S["Cân nhắc Scrum với Sprint Goal và chính sách việc khẩn"]
    E -->|"Ít hoặc nhu cầu biến động mạnh"| K["Cân nhắc quản lý dòng bằng Kanban và chính sách rõ"]
    E -->|"Có nhiều loại nhu cầu"| H["Thiết kế luồng/nhịp phối hợp có chủ đích"]
    S --> X["Bổ sung thực hành XP và kiểm soát WIP khi phù hợp"]
    K --> X
    H --> X
    X --> F["Thử trong khoảng xác định, đo kết quả"]
    F --> G{"Flow, chất lượng và giá trị tốt hơn?"}
    G -->|"Chưa rõ hoặc không"| B
    G -->|"Có với guardrails đạt"| I["Giữ cách làm, cải tiến tiếp"]
~~~

Sơ đồ không có nghĩa một hình thức phải được chọn một lần và giữ mãi. **Scrum có thể dùng thực hành Kanban**, và **XP là tập thực hành kỹ thuật có thể bổ trợ nhiều cách điều phối**.

## 4. “Gián đoạn” là gì và điều gì không phải gián đoạn?

### 4.1. Định nghĩa làm việc

Trong bài này, **gián đoạn công việc** là sự kiện hoặc yêu cầu khiến người/nhóm phải **dừng, đổi hướng, ưu tiên lại hoặc bỏ dở công việc đang thực hiện** ngoài nhịp đã dự kiến; nó có thể phát sinh từ khách hàng, sự cố, phụ thuộc, công cụ hoặc quyết định tổ chức.

Nhưng không nên đếm mọi việc mới tới như một gián đoạn. Ví dụ:

| Tình huống | Có nhất thiết là gián đoạn? | Điều cần xem |
|---|---|---|
| Một PBI đã có thứ tự trong Product Backlog được kéo vào đúng lúc có năng lực | **Không** | Đây là dòng làm việc bình thường |
| Người dùng hỏi cách dùng chức năng qua kênh hỗ trợ đã phân công | **Không nhất thiết** | Có yêu cầu chuyển người đang xây feature sang xử lý không? |
| Production bị mất dữ liệu, đội phải dừng việc khác để ứng cứu | **Có, thường là gián đoạn khẩn** | Mức tác động, quyền quyết định và chính sách ứng cứu |
| Thêm acceptance example được làm rõ khi xây PBI | **Không nhất thiết** | Đây có thể là học hỏi và điều chỉnh phạm vi bình thường |
| Stakeholder yêu cầu “gấp” nhưng chưa nêu tác động/hạn hợp lệ | **Chưa thể kết luận** | Cần triage, không tự nâng ưu tiên |
| CI đỏ và làm chặn merge | **Có thể là blocker của công việc hiện tại** | Sửa lỗi trong luồng hay cần chuyển nguồn lực từ việc khác? |
| Một người chuyển giữa ba PR đang làm vì liên tục bị nhắn | **Có tác động ngữ cảnh** | Có công việc mới thực sự khẩn hay chính sách WIP/giao tiếp kém? |
| Nghĩa vụ mới có thời hạn được xác nhận | **Có thể yêu cầu tái ưu tiên** | Hạn áp dụng, rủi ro, phụ thuộc, thẩm quyền |

Tách bạch **demand đến** với **gián đoạn gây tái phân bổ** giúp dữ liệu đáng tin hơn.

### 4.2. Năm đặc trưng cần ghi cho một gián đoạn

1. **Nguồn:** incident, khách hàng, stakeholder, vận hành, đối tác, kỹ thuật hay nghĩa vụ đã xác nhận.
2. **Thời điểm:** khi nào xuất hiện và khi nào buộc phải hành động; có lặp theo lịch không?
3. **Mức khẩn và hậu quả chờ:** nếu chờ tới điểm sắp thứ tự tiếp theo thì hậu quả nào xảy ra?
4. **Nỗ lực và thời gian chuyển ngữ cảnh:** người nào cần đổi việc, kéo dài bao lâu, có phải quay lại công việc ban đầu không?
5. **Tác động tới mục tiêu và chất lượng:** Sprint Goal, Product Goal, DoD, SLA/SLE, thời gian chờ và người dùng bị ảnh hưởng ra sao?

Không nên gán một nhãn **P1/P2/P3 chung** cho mọi đội nếu tổ chức chưa định nghĩa. Mức ưu tiên cần có **tiêu chí dựa trên tác động, tính khẩn và người có thẩm quyền phân loại**.

### 4.3. Tần suất không đồng nghĩa mức thiệt hại

Ba câu hỏi khác nhau:

- **Frequency:** trong một khoảng có bao nhiêu lần công việc bị đổi hướng?
- **Load:** tổng năng lực bị tiêu hao cho nhu cầu phát sinh là bao nhiêu?
- **Disruption cost:** bao nhiêu công việc phải dừng, chờ, làm lại hoặc chịu rủi ro chất lượng?

Ví dụ dữ liệu **giả định** trong một tuần:

| Loại phát sinh | Số lần | Tổng công sức trực tiếp | Tác động phụ |
|---|---:|---:|---|
| Hỏi cách cấu hình tài khoản | 12 | 3 giờ | Hỗ trợ viên xử lý theo ca, ít ảnh hưởng Developers |
| Lỗi nội dung bài học | 4 | 6 giờ | Có thể xếp thứ tự theo ảnh hưởng |
| Sự cố mất tiến độ nghiêm trọng | 1 | 16 giờ | Nhiều người dừng việc, kiểm tra lại rollout |
| Chờ đối tác SSO xác nhận | 3 | 1 giờ trao đổi trực tiếp | Một PBI nằm chờ ba ngày làm việc |

Nếu chỉ đếm số lần, **cấu hình tài khoản** có vẻ đáng lo nhất. Nhưng **sự cố mất tiến độ** tác động lớn hơn nhiều tới năng lực, người dùng và kế hoạch. **Chờ đối tác** tiêu ít giờ làm trực tiếp nhưng có thể làm **work item age** tăng mạnh.

### 4.4. Gián đoạn tốt và gián đoạn có thể phòng ngừa

Không phải mọi gián đoạn đều xấu:

- Người dùng báo mất dữ liệu thật: **phản hồi quan trọng cần phản ứng**.
- Kiểm thử tự động phát hiện lỗi an toàn: gián đoạn cần thiết để giữ chất lượng.
- Một thay đổi thị trường làm Product Goal cần kiểm tra lại: có thể là cơ hội học hỏi.

Những gián đoạn có thể giảm:

- Câu hỏi lặp lại vì thiếu tài liệu.
- Lỗi integration do hợp đồng API không thống nhất.
- Build đỏ do test flaky dùng chung dữ liệu.
- Người không có trách nhiệm điều phối bị nhắn “gấp” cho vấn đề không khẩn.
- Một PR lớn phải hỏi lại nhiều lượt do thiếu bối cảnh.

Mục tiêu **không phải đưa số gián đoạn về 0**, mà là bảo vệ người dùng và giá trị sản phẩm trong khi giảm chi phí chuyển ngữ cảnh không cần thiết.

## 5. Thu thập dữ liệu gián đoạn đúng cách

### 5.1. Cửa sổ quan sát phải đủ phản ánh dòng công việc

Có thể bắt đầu bằng **vài tuần hoặc một số Sprint gần đây** rồi xem có đại diện không. Nếu đội chịu sự cố mùa vụ, có các đợt phát hành lớn hoặc lịch hỗ trợ hàng tháng, cần chọn khoảng quan sát rộng hơn hoặc phân nhóm theo giai đoạn.

**Không có số tuần chuẩn.** Mục đích là hiểu *nhu cầu đến và ảnh hưởng thật*, không phải thu số liệu dài nhất có thể.

Một log tối giản:

| Trường | Cách ghi |
|---|---|
| Thời điểm đến | Ngày/giờ và múi giờ hoặc timestamp nhất quán |
| Loại yêu cầu | Incident, support, defect, policy, dependency… |
| Mức tác động | Người dùng, dữ liệu, hệ thống hoặc nghĩa vụ liên quan |
| Tính khẩn | Có cần dừng việc khác? Dựa trên tiêu chí nào? |
| Thời điểm nhận xử lý | Khi nào bắt đầu, không đồng nhất thời điểm đến |
| Người/nhóm tham gia | Theo vai trò hoặc nhóm; tránh bảng chấm công cá nhân |
| Kết quả | Đã khắc phục, đang chờ, điều tra, chuyển tiếp |
| Nỗ lực và tác động | Ước lượng đủ dùng, PBI bị gián đoạn hoặc chờ |
| Bằng chứng/nguồn | Ticket/incident/CI/log được phép, không chứa dữ liệu bí mật |

**Không tạo hồ sơ giám sát từng cá nhân.** Số liệu ở cấp hệ thống đủ để cải tiến luồng công việc; nếu có thông tin nhạy cảm cần bảo vệ theo chính sách.

### 5.2. Ví dụ tính tỷ lệ công việc phát sinh

Trong bốn tuần **giả định**, một đội bắt đầu 40 work items, gồm:

- 25 items được lựa chọn từ kế hoạch/sắp thứ tự trước.
- 15 items đến sau và được kéo vào làm sớm hơn dự kiến.

Tỷ lệ theo **số item bắt đầu**:

\[
\text{Tỷ lệ item phát sinh}=\frac{15}{40}=37{,}5\%.
\]

Nhưng nếu 15 items chỉ tốn 20 giờ trong khi các items còn lại chiếm 180 giờ, tỷ lệ **công sức trực tiếp** dành cho phát sinh là:

\[
\text{Tỷ lệ công sức phát sinh}=\frac{20}{20+180}=10\%.
\]

Hai tỷ lệ **khác nhau vì mẫu số khác nhau**. Cả hai chưa đo **thời gian mất do chuyển ngữ cảnh, hàng chờ, gián đoạn người khác hoặc chất lượng bị ảnh hưởng**.

Không nên chọn một tỷ lệ duy nhất rồi tuyên bố “trên 30% phải dùng Kanban”. Những ngưỡng như vậy **không phải quy tắc của Scrum Guide hay Kanban Guide**.

### 5.3. Đo trong các thời điểm khác nhau

| Câu hỏi | Phép quan sát phù hợp |
|---|---|
| Yêu cầu đến có ngẫu nhiên không? | Số arrivals theo ngày/tuần và loại |
| Có tập trung quanh release không? | Lịch sử incidents theo giai đoạn phát hành |
| Khi bị chen ngang, việc cũ nằm chờ bao lâu? | Work item age, blocker duration |
| Nhu cầu hỗ trợ có thể phân tuyến không? | Tỷ lệ giải quyết ở tuyến tiếp nhận so với phải kéo Developers |
| Mức khẩn có được áp đúng không? | Mẫu incident hậu kiểm theo chính sách |
| Có làm hỏng Sprint Goal không? | Số Sprint Goal đạt/chưa đạt và nguyên nhân, không chỉ completion points |
| Bằng chứng chất lượng có suy giảm? | DoD, CI, lỗi hồi quy/sự cố sau release |

**Một Sprint không đạt Goal chưa chứng minh Scrum không phù hợp.** Cần xem lý do: sự cố thật, mục tiêu quá lớn, phụ thuộc, thay đổi ưu tiên, nợ kỹ thuật hay cách phối hợp.

### 5.4. Cách đọc phân phối thay vì chỉ xem trung bình

Một đội có thể gặp không sự cố trong ba tuần rồi gặp bốn sự cố lớn trong tuần thứ tư. “Trung bình một sự cố/tuần” che mất **mức dao động**.

Nên xem:

- Số yêu cầu/tuần theo loại.
- Độ lớn và độ dài từng trường hợp.
- Những tuần cực đoan, không chỉ trung bình.
- Thời gian chờ và các item đã mở lâu.
- Khoảng tin cậy của dữ liệu hoặc giới hạn mẫu nhỏ nếu cần.

Mục đích không phải xây mô hình thống kê phức tạp, mà là tránh **lập kế hoạch quá chắc** từ một số trung bình không đại diện.

## 6. Phân loại công việc trước khi chọn cách vận hành

### 6.1. Không nên ép mọi công việc thành một loại user story

Một đội phát triển phần mềm có thể nhận nhiều loại nhu cầu:

| Loại công việc | Ví dụ | Đặc điểm cần xem | Cách tiếp cận hữu ích |
|---|---|---|---|
| **Feature delivery** | Lưu tiến độ người học | Có Product Goal, giá trị tăng dần, cần AC và DoD | Chia lát cắt, Sprint Goal hoặc flow liên tục phù hợp |
| **Product discovery** | Kiểm chứng vì sao người học bỏ dở | Bất định cao, đầu ra có thể là bằng chứng chứ chưa là chức năng | Timebox nghiên cứu, giả thuyết và tiêu chí học được |
| **Defect thông thường** | Sai căn lề trên thiết bị cụ thể | Có thể đánh giá tác động và xếp thứ tự | Cùng backlog/flow, không mặc định khẩn |
| **Incident production** | Mất tiến độ đã xác minh | Có thể khẩn cấp, cần ứng cứu và hồi phục | Chính sách triage/incident và giới hạn công việc chen ngang |
| **Operational request** | Cấp cấu hình hợp lệ cho đối tác | Có thể lặp, cần quyền và thông tin đầu vào | Workflow rõ, tự động hóa việc lặp khi an toàn |
| **Technical improvement** | Giảm flaky tests hoặc refactor cơ chế lưu | Giá trị giảm rủi ro và chi phí thay đổi | Kết nối với DoD và khả năng giao Increment |
| **Compliance/security** | Kiểm soát quyền truy cập tiến độ | Có nghĩa vụ/rủi ro; quyền quyết định và bằng chứng | Làm rõ nguồn, kiểm tra sớm và xử lý ngoại lệ đúng thẩm quyền |
| **External dependency** | Chờ nhà cung cấp SSO xác nhận contract | Nhiều thời gian chờ, ít thời gian code | Hiển thị blocker, hợp đồng bàn giao và điểm escalation |
| **Learning/spike** | Thử API mới để đánh giá khả thi | Chưa biết giải pháp, cần giới hạn đầu tư | Timebox, tiêu chí kết thúc và decision log |
| **Maintenance** | Nâng phiên bản thư viện theo kế hoạch | Khả năng dự báo khác nhau, có risk/regression | Sắp thứ tự, kiểm tra tương thích và evidence |

Một PBI có thể thuộc **nhiều đặc điểm**: nâng cấp thư viện có thể phát sinh nghĩa vụ bảo mật; user story mới có thể phải nghiên cứu trước. Bảng là **lăng kính phân tích**, không phải taxonomy có tính pháp lý hoặc yêu cầu của Scrum.

### 6.2. Sáu thuộc tính cần ghi cho loại việc

1. **Mục đích:** tạo outcome, giảm rủi ro, vận hành, phục hồi hay học giả thuyết?
2. **Độ rõ:** đã có acceptance criteria hoặc điều kiện kết thúc đáng tin chưa?
3. **Khả năng dự đoán:** arrival và nỗ lực thường ổn định hay dao động mạnh?
4. **Tính khẩn:** nếu chờ tới nhịp lập kế hoạch kế tiếp, hậu quả ra sao?
5. **Mức phụ thuộc và bàn giao:** cần ai, quyền gì, bao nhiêu bối cảnh?
6. **Độ nhạy chất lượng:** có ảnh hưởng dữ liệu, bảo mật, trải nghiệm và nghĩa vụ không?

Một lỗi bảo mật được xác minh có thể cần ưu tiên ngay dù rất khó dự đoán; một việc “cập nhật mô tả” có thể làm trong luồng thông thường. **Độ khó không tự đồng nghĩa khẩn cấp.**

### 6.3. Discovery không nhất thiết có kết quả là code

Giả sử Product Owner hỏi: “Tại sao nhiều người bắt đầu học nhưng không hoàn thành?”

Một PBI khám phá có thể có kết quả:

- Định nghĩa cohort và nguồn dữ liệu đủ tin cậy.
- Quan sát/phỏng vấn một số người học theo cách phù hợp.
- Phân biệt các giả thuyết: độ khó bài, lưu tiến độ, nhắc học, kỳ vọng sai.
- Đề xuất **một thử nghiệm sản phẩm nhỏ** và cách kiểm tra outcome.

Nếu người học thật sự cần sửa dữ liệu đang bị mất, đội phải ứng cứu chất lượng theo chính sách; **discovery không được dùng để trì hoãn bảo vệ người dùng**.

Với việc khám phá, không nên đếm “không có code” là thất bại, nhưng cần **hạn mức đầu tư, kết luận và quyết định tiếp** để không biến discovery thành hoạt động vô hạn.

### 6.4. Công việc định kỳ và công việc ngẫu nhiên khác nhau

Hai yêu cầu đều liên quan vận hành:

- **Gia hạn cấu hình định kỳ:** có thể dự đoán theo lịch và chuẩn bị trước.
- **API đối tác đột ngột từ chối tất cả request:** khó dự đoán và có thể thành incident.

Vì vậy không nên gọi tất cả vận hành là “không thể lên kế hoạch”. Một phần có thể đưa vào backlog theo thời điểm, tự động hóa hoặc chuẩn hóa để giảm biến động.

### 6.5. Rủi ro khi dùng một kênh duy nhất cho mọi loại việc

Nếu mọi thứ vào một backlog không có chính sách:

- Incident thực sự có thể bị chôn dưới các feature requests.
- Feature có giá trị dài hạn bị bỏ vì những ticket “gấp” không rõ tác động.
- Spike nghiên cứu bị đánh giá bằng số tính năng giao.
- Công việc tuân thủ bị đẩy tới cuối vì không có giao diện mới.
- Việc phụ thuộc đối tác bị che là “Developer làm chậm”.

Có thể dùng **một board với loại việc và chính sách rõ**, hoặc các luồng khác nhau có **cơ chế phối hợp**. Chia công cụ không nhất thiết đồng nghĩa chia sản phẩm thành các đội tách biệt.

## 7. Khả năng bàn giao: trục thường bị đánh giá thấp

### 7.1. Bàn giao là chuyển khả năng hành động, không chỉ chuyển ticket

Một handoff tốt trả lời:

> “Người nhận có đủ **mục tiêu, quyết định, quyền, trạng thái thật, bằng chứng, tri thức và điều kiện kết thúc** để tiếp tục an toàn mà không phải điều tra lại toàn bộ không?”

Nếu một ticket ghi “làm tiếp phần còn lại” nhưng không có link hợp đồng API, test và blocker, việc chuyển trạng thái trên bảng chỉ tạo **ảo giác công việc đang trôi**.

**Bàn giao tốt không bắt buộc chuyển qua càng nhiều người càng tốt.** Với một quyết định phức tạp, giữ người có bối cảnh xuyên suốt hoặc pairing có thể giảm chi phí hơn chuyển qua nhiều vai trò.

### 7.2. Sáu chiều đánh giá bàn giao

| Chiều | Câu hỏi | Ví dụ rủi ro |
|---|---|---|
| **Mục tiêu và phạm vi** | Người nhận hiểu kết quả cần tạo và điều cố ý không làm? | Tự thêm phạm vi hoặc bỏ rủi ro quan trọng |
| **Tri thức và quyết định** | Có acceptance examples, spec, ADR, người có thẩm quyền? | Hai nơi dùng hai định nghĩa “Đã lưu” |
| **Trạng thái và bằng chứng** | Test nào đã chạy; PBI đã đạt DoD chưa; CI gắn build nào? | Nhầm PR approved với Increment Done |
| **Quyền và tài nguyên** | Có môi trường, dữ liệu thử, cấp quyền hợp lệ? | Người nhận chờ tài khoản quản trị cả ngày |
| **Phụ thuộc và đầu mối** | Chờ ai, tại sao, mốc phản hồi nào? | Ticket đi vòng giữa UI–API–đối tác |
| **Khả năng chia nhỏ và đảo ngược** | Có thể giao lát cắt có giá trị và kiểm tra độc lập? | Phải thay toàn hệ thống mới xác minh được |

**Không đánh giá bàn giao chỉ bằng chất lượng tài liệu.** Một trang wiki hoàn chỉnh không bù được thiếu quyền test hoặc sự phụ thuộc vào người duy nhất có thể quyết định nghiệp vụ.

### 7.3. Thang đánh giá bàn giao minh họa

| Mức | Mô tả quan sát | Cách làm phù hợp |
|---|---|---|
| **0 — Chưa thể bàn giao an toàn** | Thiếu quyền, phạm vi, quyết định hay bằng chứng thiết yếu | Không chuyển như Done; giải quyết blocker trước |
| **1 — Phụ thuộc người gốc** | Có ticket nhưng người nhận phải gọi lại để hiểu phần lớn ngữ cảnh | Pairing, bổ sung ví dụ và nguồn quyết định |
| **2 — Bàn giao có hỗ trợ** | Có mô tả/bằng chứng nhưng còn câu hỏi cần người gốc | Timebox trao đổi, handoff có checklist |
| **3 — Bàn giao độc lập tương đối** | Người nhận có thể tiếp tục phần rõ với quyền và test thích hợp | Pull theo năng lực, cập nhật blocker và kết quả |
| **4 — Công việc lặp được chuẩn hóa** | Đầu vào/điều kiện hoàn tất rõ; công cụ kiểm chứng tin cậy | Tự phục vụ/tự động hóa hợp lý và giám sát ngoại lệ |

Đây là **thang thực hành tự thiết kế**, không phải thang chính thức của Scrum hay Kanban. Không dùng để **chấm điểm nhân viên**; dùng nhận diện phần công việc cần bớt phụ thuộc.

### 7.4. Ví dụ: cùng một thay đổi API, hai cách bàn giao

**Bàn giao yếu:**

> “API lưu tiến độ xong, frontend làm tiếp nhé.”

**Bàn giao đủ điều kiện hành động:**

~~~yaml
# Thẻ bàn giao minh họa, không phải một chuẩn bắt buộc.
pbi: "LEARN-42 — Tiếp tục bài học"
purpose: "Người học nhận trạng thái lưu đáng tin"
current_state: "Backend đã merge, PBI chưa đạt DoD"
source_of_truth:
  acceptance_criteria: "AC-07"
  api_contract: "progress-api-v2"
  decision: "ADR-012"
verified:
  - "Unit tests cho CONFIRMED, FAILED, UNKNOWN"
  - "Contract checks ở build được gắn link"
not_yet_verified:
  - "Integration test với database trên môi trường thử"
  - "Frontend xử lý UNKNOWN đúng ngữ nghĩa"
blocker: "Môi trường integration chưa khả dụng"
handoff_to: "Người nhận đã xác nhận có quyền và năng lực phù hợp"
next_steps:
  - "Kiểm tra kết quả integration khi môi trường khôi phục"
  - "Tạo lát cắt UI và test trạng thái UNKNOWN"
quality: "Không được chuyển Done trước khi đạt Definition of Done"
~~~

Không cần tạo file YAML riêng trong công việc thật; có thể đặt thông tin này vào **ticket/PR hiện có**. Quan trọng là người nhận thấy **điều đã biết, điều chưa biết và bước tiếp an toàn**.

### 7.5. Khả năng bàn giao và quy mô lô công việc

Một PBI dài ba tuần, thay đổi mười service và chưa tích hợp thường khó bàn giao hơn ba lát cắt nhỏ có giao diện hợp đồng, test và tiêu chí rõ.

Tuy nhiên, **không cắt nhỏ giả tạo** thành nhiều ticket “sửa tên hàm” không tạo giá trị hoặc không kiểm chứng độc lập. Mục tiêu là **lát cắt dọc đủ nhỏ và có thể Done**, không tăng số lượng thẻ.

### 7.6. Chi phí bàn giao có thể lớn hơn chi phí viết tài liệu

Một handoff có thể làm mất:

- Thời gian người nhận tái dựng vấn đề.
- Thời gian người giao trả lời thêm sau khi đã chuyển việc.
- Cơ hội phát hiện lỗi sớm nếu bối cảnh bị chia nhỏ.
- Thời gian chờ quyền truy cập hoặc chuyên gia.
- Rủi ro phải làm lại vì hai bên hiểu khác.

Trong dữ liệu điều hành, **thời gian trực tiếp viết handoff** không phải toàn bộ chi phí; cần xem cả **work item age, rework và chất lượng**.

### 7.7. Phân tán múi giờ khác với thiếu khả năng bàn giao

Một đội có thành viên ở hai khu vực khác nhau vẫn có thể làm tốt nếu:

- Hợp đồng API và decisions có nguồn hiện hành.
- PR nhỏ, có test và mô tả rủi ro.
- Trách nhiệm review và mốc phản hồi theo giờ làm rõ ràng.
- Công việc chưa đạt DoD không bị bàn giao như Done.

Ngược lại, đội ngồi cùng phòng vẫn có thể bị tắc nếu mọi thứ chỉ nằm trong đầu một cá nhân. **Vị trí địa lý là một yếu tố, không phải lời giải thích duy nhất cho handoff kém.**

## 8. Dựng bản đồ luồng công việc và điểm chờ

### 8.1. Bảng trạng thái phải mô tả công việc thật

Ví dụ Definition of Workflow của một đội:

~~~text
Ready
  Có mục tiêu, loại việc, tiêu chí chấp nhận/điều kiện hoàn tất.
In Progress
  Đang tạo thay đổi hoặc điều tra, tính vào WIP.
Review / Verify
  Đang chờ hoặc thực hiện review/test; vẫn tính WIP.
Blocked
  Có trở ngại rõ, vẫn là việc đang mở; không xóa khỏi WIP.
Done
  Đạt Definition of Done / tiêu chuẩn kết thúc được áp dụng.
~~~

Đội có thể định nghĩa workflow khác; các trạng thái cần **chính sách chuyển rõ và dữ liệu đáng tin**. Nếu một ticket support chỉ cần cung cấp thông tin, tiêu chuẩn hoàn tất sẽ khác một Increment phần mềm, nhưng phải xác định rõ loại công việc đang được đo.

### 8.2. Visualize các dòng phụ thuộc

~~~mermaid
flowchart LR
    A["Nhu cầu mới"] --> T{"Phân loại và mức tác động"}
    T -->|"Incident"| I["Ứng cứu theo chính sách"]
    T -->|"Feature / khám phá"| P["Product Backlog và mục tiêu"]
    T -->|"Support / vận hành"| S["Luồng dịch vụ"]
    T -->|"Dependency"| X["Chờ bên ngoài có chủ sở hữu"]
    P --> R["Thực hiện / kiểm chứng"]
    S --> R
    X --> R
    I --> R
    R --> Q{"Điều kiện Done đạt?"}
    Q -->|"Chưa"| B["Blocked / sửa / kiểm tra tiếp"]
    B --> R
    Q -->|"Đạt"| D["Hoàn tất / Increment / kết quả dịch vụ"]
~~~

**Cần phân biệt tác phẩm có giá trị người dùng với ticket dịch vụ** khi tổng hợp throughput; trộn chúng thành một số đếm duy nhất dễ gây ảo giác dự báo.

### 8.3. Dòng công việc bị chặn khác dòng công việc đang chủ động phát triển

Một item chờ chuyên gia xác nhận hai ngày có thể **không dùng nhiều giờ code** nhưng vẫn kéo dài thời gian đến giá trị. Nếu nhóm chỉ hỏi “ai đang làm việc?” thay vì “điều gì đang chờ?”, blocker sẽ bị che.

Nên hiển thị:

- **Lý do chờ**: decision, environment, review, external service, dữ liệu.
- **Thời điểm bắt đầu chờ**.
- **Người/đầu mối có thể xử lý theo thẩm quyền**.
- **Điều kiện để mở chặn**.
- **Tác động tới Sprint Goal hoặc người dùng**.

Không tự động mở thêm năm PBI khi một việc bị chặn; điều đó có thể tăng **WIP và tải chuyển ngữ cảnh** mà không giải quyết điểm nghẽn.

### 8.4. Những dữ liệu Kanban cần định nghĩa thống nhất

| Phép đo | Định nghĩa | Câu hỏi giúp trả lời |
|---|---|---|
| **WIP** | Work items đã bắt đầu nhưng chưa hoàn tất theo workflow | Có quá nhiều việc dở và chờ không? |
| **Throughput** | Số work items hoàn thành trong một khoảng | Luồng giao có ổn định không, theo từng loại việc? |
| **Cycle time** | Thời gian từ mốc bắt đầu tới kết thúc của việc đã Done | Việc hoàn tất thường mất bao lâu? |
| **Work item age** | Thời gian một việc đang mở đã tồn tại từ khi bắt đầu | Việc nào đang già, có cần can thiệp không? |
| **SLE** | Service Level Expectation: kỳ vọng dựa trên lịch sử về thời gian một item hoàn thành, thường có phần trăm xác suất đi kèm | Item hiện tại có đang vượt kỳ vọng flow không? |

SLE là **kỳ vọng có tính xác suất**, không tự động là **SLA hợp đồng** hoặc cam kết chắc chắn cho từng ticket.

Ví dụ một đội có thể dùng:

> “Theo lịch sử loại công việc A, khoảng **85%** items đã hoàn thành trong **8 ngày làm việc hoặc ít hơn**.”

Đây là **ví dụ minh họa**, không phải ngưỡng chuẩn; cần định nghĩa loại item, mốc tính, dữ liệu lịch sử và khả năng đại diện. Không nên suy ra việc mới chắc chắn xong sau tám ngày.

### 8.5. Dòng công việc liên tục có thể giữ định hướng dài hạn

Một đội dùng Kanban không nhất thiết chỉ “chọn ticket tiếp theo có thời gian chờ lâu nhất”. Họ vẫn cần:

- **Mục tiêu sản phẩm hoặc dịch vụ** rõ.
- Quy tắc ưu tiên giữa feature, support và rủi ro.
- Nhịp đánh giá nhu cầu và kết quả sản phẩm.
- Chính sách cho incident/urgent.
- Thực hành kỹ thuật để giữ chất lượng.

**Không có Sprint không đồng nghĩa không có kế hoạch.** Ngược lại, có Sprint không đồng nghĩa nhu cầu đã đủ dự đoán để lập kế hoạch có chất lượng.

## 9. Ma trận lựa chọn theo tần suất gián đoạn, loại việc và bàn giao

### 9.1. Tình huống điển hình và giả thuyết phù hợp

| Bối cảnh | Điểm nổi bật | Phương án nên cân nhắc | Điều cần cảnh giác |
|---|---|---|---|
| Phát triển sản phẩm có mục tiêu rõ, phần lớn việc lựa chọn chủ động | Sprint Goal khả thi, ít chen ngang thật | **Scrum** với PBI nhỏ, DoD và feedback | Dồn kiểm thử cuối Sprint hoặc Sprint Goal quá cứng |
| Dòng support/ops liên tục, arrivals khó dự đoán | Nhiều loại yêu cầu, thời điểm nhận không đều | **Kanban** với policies, WIP và SLE theo loại | Chạy theo mọi ticket, không đánh giá giá trị và rủi ro |
| Cùng đội có feature và incidents thỉnh thoảng | Có Product Goal nhưng cần xử lý sự cố | **Scrum + thực hành Kanban** và triage minh bạch | Dùng lane “khẩn” để chen tất cả yêu cầu |
| Nhiều yêu cầu nhỏ lặp được, handoff tốt | Khả năng chuẩn hóa cao | **Flow/pull + automation** khi hợp lệ | Bỏ kiểm soát chất lượng khi tự động hóa |
| Công việc nghiên cứu bất định cao | Chưa thể cam kết giải pháp nhưng có thể giới hạn thời gian học | **Discovery timebox** nối kết quả vào backlog/flow | Gọi “nghiên cứu” để không bao giờ kết luận |
| Nhiều incident nặng, handoff thấp | Vừa biến động vừa phụ thuộc tri thức một người | **Ổn định ứng cứu, chia tri thức, test, review** trước khi tranh luận nhãn framework | Chỉ đổi Scrum sang Kanban nhưng sự cố và nút cổ chai không đổi |
| Phụ thuộc đối tác/kiểm soát ngoài nhóm | Công việc chủ yếu là chờ quyết định | **Hiển thị flow, handoff/evidence, escalation**, cùng Product Goal | Chấm điểm Developer theo thời gian chờ bên ngoài |
| Công việc có rủi ro cao và bắt buộc review độc lập | Handoff cần bằng chứng, quyền và chuẩn | **Kiểm soát theo rủi ro tích hợp workflow** | Cắt approval bắt buộc để tăng throughput |

Ma trận đưa ra **giả thuyết để thử**, không phải luật xác định một khuôn khổ từ vài ô tick.

### 9.2. Một phương án lựa chọn phải nêu cả điều không phù hợp

Ví dụ:

> “Đội giữ Sprint Goal cho luồng học, nhưng dùng chính sách triage và WIP rõ cho incidents. Chúng ta **không** mở thêm một đội on-call 24/7 khi chưa có nhu cầu/nguồn lực chính thức. Chúng ta **không** tính mọi ticket support vào velocity của feature. Chúng ta sẽ xem lại sau ba Sprint dựa trên kết quả và tải công việc.”

Nói rõ **giới hạn và đánh đổi** giúp nhóm không vô thức trượt sang mô hình khác.

### 9.3. Tránh nhầm Scrum, Kanban và XP

- **Scrum:** khuôn khổ với accountabilities, events, artifacts và commitments; có Sprint Goal, Product Goal, Increment/DoD.
- **Kanban:** phương pháp quản lý **dòng công việc**, định nghĩa và trực quan hóa workflow, kiểm soát WIP, đo flow và cải tiến policies.
- **XP (Extreme Programming):** tập giá trị/nguyên tắc/thực hành kỹ thuật như TDD, CI, pair programming, refactoring và small releases để giao phần mềm an toàn hơn.

Chúng giải quyết **những lớp câu hỏi khác nhau**. Một Scrum Team có thể áp dụng chiến lược Kanban nhằm tối ưu flow, và dùng XP để giảm rủi ro kỹ thuật. Không nên trình bày “Scrum = họp”, “Kanban = bảng”, “XP = chỉ viết test”.

## 10. Khi nào Scrum hữu ích và thích ứng thế nào với gián đoạn?

### 10.1. Mục tiêu Sprint tạo giá trị gì?

Trong Scrum, Sprint tạo nhịp **kiểm tra và thích ứng** với thời gian cố định, tối đa một tháng. **Sprint Goal** tạo mục đích chung; **Sprint Backlog** gồm Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện; **Increment** phải đáp ứng Definition of Done (DoD).

Scrum có lợi khi:

- Đội có **mục tiêu sản phẩm** tương đối rõ trong khoảng ngắn.
- Có thể chọn **một tập PBI phù hợp năng lực** để tiến tới Sprint Goal.
- Cần thời điểm đều đặn để xem Increment và phản hồi với stakeholders.
- Nhóm có đủ quyền, tri thức và phối hợp để **tạo Increment có thể sử dụng**.
- Nhu cầu phát sinh có thể **phân loại** và xử lý mà không biến mọi ngày thành một thay đổi Sprint Goal.

**Sprint Goal không phải danh sách tất cả ticket nhất thiết phải xong**; nó là mục tiêu hướng công việc, cho phép thích ứng phạm vi khi hiểu biết tăng.

### 10.2. Scrum không hứa “không được chen ngang”

Theo Scrum Guide 2020, trong Sprint:

- **Không thay đổi nào được gây nguy hại Sprint Goal**.
- **Chất lượng không được giảm**.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng với Product Owner khi đội học thêm.

Điều này khác với quan niệm “đã vào Sprint thì tuyệt đối cấm công việc mới”. Khi xuất hiện **sự cố nghiêm trọng**, đội phải hành động theo rủi ro và chính sách; đồng thời minh bạch tác động tới Sprint Goal và điều chỉnh kế hoạch với Product Owner.

Chỉ **Product Owner** có thẩm quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời; việc này khác với thay đổi Sprint Backlog bình thường hoặc xử lý sự cố.

### 10.3. Thiết kế một luồng sự cố trong Scrum Team

Đội có thể đặt chính sách:

| Tín hiệu | Phản ứng minh họa | Ảnh hưởng tới kế hoạch |
|---|---|---|
| Lỗi hiển thị ít tác động | Ghi backlog, Product Owner sắp thứ tự | Không tự chen vào Sprint |
| Lỗi ảnh hưởng một phân khúc nhưng có cách giảm tác động | Triage mức rủi ro, quyết định thời điểm xử lý | Có thể đàm phán điều chỉnh Sprint Backlog |
| Người học đang mất tiến độ diện rộng | Ứng cứu theo policy, phân công người có trách nhiệm | Minh bạch, ưu tiên bảo vệ người dùng, đánh giá Sprint Goal |
| Yêu cầu cấu hình SSO bình thường | Luồng support hoặc PBI theo thứ tự | Tránh kéo Developers rời Sprint nếu không cần |
| CI đỏ làm chặn Increment hiện tại | Xử lý chất lượng trong luồng làm việc | Không báo Done khi DoD chưa đạt |

Một chính sách triage tốt giảm **việc giả khẩn**, không ngăn xử lý khẩn thật.

### 10.4. Cân nhắc năng lực và kế hoạch Sprint

Khi sự cố lặp nhưng vẫn chiếm tỷ lệ năng lực hạn chế:

- Dùng dữ liệu lịch sử để **không lập kế hoạch feature chiếm toàn bộ năng lực danh nghĩa**.
- Xem người trực hỗ trợ có thể tham gia những PBI dễ dừng, ít phụ thuộc hay không.
- Chọn Sprint Goal có thể đạt dù có mức bất định đã quan sát.
- Dùng PBI nhỏ và WIP thấp để việc ngắt quãng không để lại nhiều nhánh dở.
- Theo dõi khả năng đạt Goal và tác động lên chất lượng.

**Không có quy tắc Scrum bắt buộc “dành 20% thời gian cho support”.** Mọi tỷ lệ chỉ là giả thuyết dựa trên dữ liệu và phải được điều chỉnh.

### 10.5. Scrum khi nào không còn đem lại đủ lợi ích?

Nếu nhiều Sprint liên tiếp chỉ có một chuỗi sự cố và việc khẩn khó dự đoán, Sprint Goal liên tục bị vô hiệu hóa dù nhóm đã triage, chia lát cắt và cải thiện kỹ thuật, đội nên **xem lại cách tổ chức dòng nhu cầu**.

Nhưng cần phân tích:

- Sự cố có thuộc **một sản phẩm và cùng nguồn rủi ro** cần khắc phục?
- Phân tuyến hỗ trợ có đang kéo sai người?
- Product Owner có thể ưu tiên giảm nguồn gốc incident thay vì luôn phát hành feature mới?
- Có cần tách hoặc xoay **năng lực ứng cứu** theo chính sách hợp lệ?
- Nhóm có cần **Kanban flow** cho loại việc này mà vẫn giữ Product Goal?

Không chuyển phương pháp chỉ để tránh phải sửa một vấn đề chất lượng lặp lại.

## 11. Khi nào Kanban hữu ích và cần chính sách gì?

### 11.1. Kanban không đơn thuần là bảng ba cột

Kanban giúp xác định, trực quan hóa và quản lý **Definition of Workflow**, kiểm soát WIP và đo flow để cải tiến.

Một workflow có thể mô tả:

- **Work item types** và khi nào từng loại được nhận.
- **Điểm bắt đầu và kết thúc** work item.
- **Các trạng thái** hoạt động, review, blocker và Done.
- **Cách kiểm soát WIP** (giới hạn, policy).
- **Chính sách rõ** cho cách kéo, ưu tiên, giải quyết blocker và ngoại lệ.
- **Service Level Expectation (SLE)** phù hợp với dữ liệu.

Một bảng có nhiều màu nhưng không có tiêu chí chuyển cột, không biết Done là gì, không có giới hạn WIP hay số đo sẽ khó giúp đội học từ dòng công việc.

### 11.2. Flow hữu ích khi yêu cầu đến không đều

Một nhóm xử lý support và incidents có thể không gom nhu cầu thành gói hai tuần ổn định. Với Kanban, họ có thể:

- Nhận diện nhu cầu liên tục và **kéo khi có năng lực**.
- Xếp hạng theo **tác động, khẩn cấp và chính sách dịch vụ**.
- Tập trung **hoàn thành** trước khi bắt đầu quá nhiều việc.
- Xem item nào **đã mở quá lâu** để giúp tháo blocker.
- Dự báo bằng dữ liệu lịch sử thay vì ép toàn bộ việc vào một Sprint.

**Dòng liên tục không phải làm bất cứ việc mới tới ngay lập tức.** Chính sách triage và WIP bảo vệ năng lực hữu hạn.

### 11.3. WIP limit làm giảm chi phí chuyển ngữ cảnh như thế nào?

Giả sử nhóm có ba Developers đang xử lý tám PBI, đồng thời PR review và test đang chờ.

Thay vì bắt đầu thêm ba việc, họ có thể thử:

1. Giới hạn việc đang thực hiện theo workflow và năng lực.
2. Khi đạt giới hạn, ưu tiên **hỗ trợ review, kiểm thử hoặc tháo blocker**.
3. Không tự xóa ticket blocked khỏi WIP để lấy chỗ.
4. Xem lại throughput, work item age và DoD trong giai đoạn thử.

WIP limit **không phải “mỗi người phải có đúng một ticket”**. Đôi khi pairing hoặc xử lý song song có ích; mức limit được chọn và điều chỉnh bằng quan sát thực tế.

### 11.4. Nhịp Kanban và quyết định ưu tiên

Không cần Sprint để có các điểm xem xét:

| Loại xem xét | Câu hỏi | Người cần tham gia |
|---|---|---|
| **Triage nhu cầu** | Đây là khẩn thật hay yêu cầu chuẩn? | Đầu mối chịu trách nhiệm theo chính sách |
| **Replenishment** | Khi có năng lực, nên kéo item nào theo Product Goal/rủi ro? | Người chịu trách nhiệm ưu tiên và đội thực hiện |
| **Flow review** | Work item age, WIP và blocker nào đang nguy hiểm? | Người quản lý workflow và người có thể tháo trở ngại |
| **Service delivery review** | Dự báo/SLE, chất lượng dịch vụ và phản hồi có phù hợp? | Nhóm cung cấp dịch vụ và stakeholders phù hợp |
| **Improvement review** | Thử chính sách mới có giúp flow tốt hơn? | Nhóm thực hiện và người có quyền thay đổi policy |

Các tên/nhịp có thể khác nhau; đừng tự coi đây là **Scrum Events** hoặc quy tắc bắt buộc cho mọi ứng dụng Kanban.

### 11.5. Cẩn trọng với SLE và cam kết thời hạn

SLE từ dữ liệu lịch sử ví dụ:

> “Với những PBI sửa lỗi loại B đã Done trong giai đoạn quan sát, 85% có cycle time không quá sáu ngày làm việc.”

Đây là **kỳ vọng**, không phải chứng nhận mọi PBI tới sẽ xong trong sáu ngày. Phải xem:

- Loại việc có tương đồng không?
- Giai đoạn lịch sử có phản ánh năng lực hiện tại không?
- Nhu cầu có đổi cấu trúc?
- Có incident bất thường hoặc phụ thuộc mới?
- Sự kiện “Done” có thực sự theo DoD không?

Khi một nghĩa vụ có hạn hợp đồng thật, SLE **không thay thế** lịch trình, trách nhiệm hoặc biện pháp giảm rủi ro đã cam kết.

### 11.6. Cạm bẫy của Kanban khi thiếu định hướng sản phẩm

Nếu mọi người chỉ tối ưu throughput:

- Có thể chọn việc nhỏ, ít giá trị để tăng số ticket Done.
- Việc khó nhưng quan trọng cho Product Goal bị bỏ lại.
- Công việc cải thiện nguyên nhân incident không được ưu tiên.
- Mọi giờ bị chiếm bởi support dễ làm nhưng không tăng outcome.

Do đó cần **nguyên tắc ưu tiên giá trị và rủi ro**, đối chiếu cùng flow; không dùng throughput làm thước đo duy nhất.

## 12. XP: giảm chi phí gián đoạn và bàn giao ở tầng kỹ thuật

### 12.1. Chọn framework điều phối không đủ khi code khó đổi

Nếu mỗi thay đổi nhỏ gây hồi quy vì không có test, mỗi PR đợi một người duy nhất, hoặc integration diễn ra cuối tháng, đội sẽ bị tắc dù dùng Scrum hay Kanban.

**Extreme Programming (XP)** hỗ trợ thay đổi và phản hồi kỹ thuật:

| Thực hành | Giúp khi có gián đoạn | Giúp khi cần bàn giao |
|---|---|---|
| **TDD** | Có kiểm tra quy tắc nhỏ để sửa an toàn | Test diễn đạt hành vi người nhận có thể chạy |
| **Continuous Integration** | Phát hiện sớm xung đột khi đổi việc/merge | Build/test gắn phiên bản, tạo bằng chứng chung |
| **Pair programming** | Hai người cùng giải quyết lỗi khó, giảm phụ thuộc một người | Chia tri thức khi chuyển việc |
| **Refactoring** | Code ít rối hơn khi phải sửa liên tục | Người mới hiểu/sửa thuận lợi hơn |
| **Simple design** | Tránh thiết kế lớn trước khi có phản hồi | Ranh giới thay đổi nhỏ và dễ giải thích |
| **Small releases** | Giảm phạm vi rủi ro khi cần rollback | Kết quả từng lát cắt rõ ràng |
| **Collective code ownership** | Người khác có thể hỗ trợ đúng năng lực | Giảm silo, vẫn cần chuẩn chất lượng |
| **Sustainable pace** | Tránh vòng lặp quá tải → lỗi → sự cố → quá tải | Bàn giao không biến thành trực 24/7 |

**XP không tự phân loại incident hoặc quyết định thứ tự Product Backlog.** Nó là phần quan trọng của lời giải khi chi phí đổi việc và chất lượng kỹ thuật đang làm luồng công việc bất ổn.

### 12.2. Test giúp thay đổi kế hoạch nhưng có giới hạn

Ví dụ TDD cho một quy tắc nhỏ:

~~~java
// Ví dụ Java độc lập minh họa điều kiện nghiệp vụ.
// Không thay thế kiểm tra bảo mật/DB/API thực tế.
enum SaveResult { CONFIRMED, FAILED, UNKNOWN }

final class SaveStatus {
    static String message(SaveResult result) {
        return switch (result) {
            case CONFIRMED -> "Đã lưu";
            case FAILED -> "Không thể lưu";
            case UNKNOWN -> "Chưa xác định được kết quả lưu";
        };
    }
}
~~~

Các kiểm tra nên bảo đảm **UNKNOWN không báo “Đã lưu”**. Tuy vậy unit tests cho hàm này **không chứng minh dữ liệu thật đã được lưu hoặc quyền truy cập API là đúng**. Cần chọn contract/integration/E2E theo rủi ro.

### 12.3. Pairing không có nghĩa mọi công việc phải làm hai người

Pairing có thể đặc biệt có ích khi:

- Sự cố liên quan vùng code chỉ một người hiểu.
- Cần review quyết định thiết kế có nhiều ngoại lệ.
- Thành viên mới cần học ranh giới sản phẩm.
- Handoff giữa các nhóm gây hiểu sai lặp lại.

Nên giới hạn thời gian, nêu mục tiêu và để lại **test/PR/decision log** sau phiên. Không kéo mọi người vào cùng cuộc gọi kéo dài để thay cho việc làm rõ công việc.

### 12.4. Refactoring và chất lượng phòng ngừa gián đoạn tương lai

Nếu cùng một service thường tạo sự cố:

1. Khắc phục tác động hiện tại theo mức khẩn.
2. Hậu kiểm xem nguyên nhân và cơ chế phát hiện.
3. Đưa cải tiến chất lượng có giá trị vào backlog.
4. Chia thành lát cắt, giữ hệ thống hoạt động.
5. Kiểm tra sự cố tái diễn, cycle time và khả năng thay đổi.

Chỉ làm “sửa tạm” liên tục mà không có năng lực cho **nguyên nhân gốc** có thể khiến tần suất gián đoạn mãi cao; ngược lại, đòi viết lại toàn hệ thống trước khi xử lý nguy cơ đang gây hại cũng không phù hợp.

## 13. Các cách phối hợp: tránh chọn một nhãn thay cho thiết kế

### 13.1. Scrum kết hợp thực hành Kanban

Một Scrum Team có thể:

- Giữ **Product Goal, Sprint Goal, Sprint Review và Retrospective**.
- Dùng **board phản ánh workflow thật**, không chỉ To Do/In Progress/Done.
- Giới hạn WIP khi thích hợp để hoàn thành PBI sớm.
- Quan sát throughput, cycle time, work item age và blockers trong Sprint.
- Có chính sách triage incident rõ, phản ứng theo rủi ro.
- Dùng XP để test/integrate thường xuyên.

Điều này **không yêu cầu bỏ Scrum**, nhưng đội phải giữ accountabilities và commitments; không biến Sprint thành “chạy ticket liên tục nhưng cuối Sprint báo cáo cho quản lý”.

### 13.2. Luồng Kanban cho support, nhịp Scrum cho sản phẩm: cần ranh giới rõ

Một tổ chức có thể chọn:

- Đội sản phẩm tập trung Increment và outcome người dùng.
- Đầu mối dịch vụ tiếp nhận, triage và xử lý support theo workflow.
- Incident nghiêm trọng có cơ chế kéo chuyên gia sản phẩm khi thực sự cần.
- Work items vượt quyền giải quyết được **bàn giao có bối cảnh**, không biến thành ping-pong.

Rủi ro:

- Silo support không chia sẻ nguyên nhân hệ thống với đội sản phẩm.
- Product Developers mất hiểu biết trực tiếp về lỗi người dùng.
- Các PBI sửa nguyên nhân gốc không được ai ưu tiên.
- Handoff tăng và thời gian chờ kéo dài.

Vì vậy, nếu tách luồng hoặc năng lực, phải có **cơ chế học hỏi và trách nhiệm đầu-cuối**, không chỉ chuyển ticket sang nhóm khác.

### 13.3. Một đội, nhiều loại service: coi chừng WIP ẩn

Nhóm có thể dùng **lanes theo loại việc** với policies khác nhau, nhưng tổng năng lực của thành viên vẫn là một:

| Luồng | Chính sách minh họa | Rủi ro |
|---|---|---|
| Feature | PBI nhỏ, ưu tiên mục tiêu và DoD | Feature bị ngắt liên tục nếu lane khẩn không giới hạn |
| Standard support | Triage, tự phục vụ hoặc pull theo năng lực | Ticket nhỏ chiếm hết thời gian nếu không phân tuyến |
| Incident | Chính sách mức độ tác động, ứng cứu theo quyền | Bất kỳ yêu cầu nào cũng được gắn incident để vượt hàng |
| Discovery | Timebox, tiêu chí học và quyết định tiếp | Nghiên cứu không có mốc kết thúc |
| Compliance | Nguồn yêu cầu và evidence được xác nhận | Việc review thành nút cổ chai cuối dòng |

**Năm lanes không tạo ra năm đội.** Nếu tổng WIP vượt khả năng xử lý, việc dở vẫn tăng. Cần xem **toàn flow và năng lực thực tế**.

### 13.4. “Scrumban” là nhãn thực hành, không phải một chuẩn duy nhất

Trong cộng đồng, nhiều cách kết hợp Scrum và Kanban được gọi là **Scrumban**, nhưng cách áp dụng khác nhau. Không nên giả định cứ có cột “Expedite” và họp hằng ngày là tuân thủ một quy trình chuẩn chung.

Khi mô tả phương án, tốt hơn nên nói rõ:

- Có/không có Sprint và Sprint Goal?
- Ai chịu trách nhiệm **thứ tự công việc**?
- WIP được giới hạn thế nào?
- Ai triage sự cố và ưu tiên thay đổi?
- Công việc Done nghĩa là gì?
- Nhịp kiểm tra outcome và điều chỉnh workflow ra sao?

**Tên phương pháp không thay thế thiết kế operating policies.**

### 13.5. Khi nào phải thay đổi cấu trúc tổ chức thay vì bảng?

Nếu tất cả việc đi qua một chuyên gia hiếm, một môi trường tích hợp duy nhất hoặc một nhóm phê duyệt không đủ năng lực, đổi từ Sprint board sang Kanban board không làm nút cổ chai biến mất.

Cần cân nhắc:

- Xây năng lực review/pairing và giảm kiến thức chỉ một người.
- Thỏa thuận SLA/phản hồi và hợp đồng bàn giao với nhóm phụ thuộc.
- Tự động hóa kiểm tra thường lặp và giảm test flaky.
- Đàm phán quyền truy cập và môi trường theo chính sách.
- Điều chỉnh phạm vi Product Goal, năng lực hoặc trách nhiệm dịch vụ.

Scrum Master có thể hỗ trợ tháo gỡ trở ngại tổ chức trong Scrum; những quyết định nguồn lực/chính sách vẫn cần **người có thẩm quyền**.

## 14. Phân bổ năng lực khi nhu cầu không dự báo chắc chắn

### 14.1. Capacity khác throughput và khác commitment

- **Capacity:** năng lực thời gian/con người thực tế có thể dành cho công việc trong một kỳ, sau nghỉ, hỗ trợ và ràng buộc.
- **Throughput:** số work items được hoàn thành trong một khoảng theo workflow đã định.
- **Forecast:** dự báo về lượng việc có thể hoàn thành hoặc thời gian, với mức bất định.
- **Commitment trong Scrum:** Product Goal, Sprint Goal và DoD gắn artifacts; **không đồng nghĩa cam kết cố định mọi ticket được ước lượng**.

Không dùng một con số velocity hoặc story points như **số giờ tuyệt đối**. Các đội có cách phân loại và kích thước việc khác nhau.

### 14.2. Ví dụ tính năng lực với dữ liệu giả định

Giả sử trong hai tuần, cả đội có **240 giờ công việc có thể phân bổ** sau khi trừ nghỉ và nghĩa vụ cố định. Quan sát bốn giai đoạn gần nhất:

| Giai đoạn | Nỗ lực ứng cứu/hỗ trợ trực tiếp | Tỷ lệ trên 240 giờ giả định |
|---|---:|---:|
| A | 18 giờ | 7,5% |
| B | 42 giờ | 17,5% |
| C | 28 giờ | ≈ 11,7% |
| D | 64 giờ | ≈ 26,7% |

Trung bình công sức phát sinh trực tiếp:

\[
\frac{18+42+28+64}{4} = 38\text{ giờ/chu kỳ}.
\]

Nếu giả sử năng lực danh nghĩa tương đương và mọi số liệu hợp lệ, 38/240 ≈ **15,8%**. Nhưng giai đoạn D cần tới 64 giờ, nên **lập kế hoạch tất cả 202 giờ còn lại như một cam kết chắc chắn** có thể là ảo tưởng.

Con số 38 giờ chỉ là **thông tin lịch sử, không phải định mức buffer đúng cho tương lai**. Cần xem tính mùa vụ, chính sách ứng cứu, ảnh hưởng chuyển ngữ cảnh và chất lượng.

### 14.3. Cách lập phương án thay vì một con số chắc chắn

Có thể dựng ba tình huống:

| Tình huống | Nhu cầu phát sinh giả định | Phương án đối với kế hoạch |
|---|---|---|
| **Nhẹ** | Ít sự cố, support nằm trong tuyến riêng | Tiếp tục PBI theo thứ tự, giữ DoD |
| **Thường gặp** | Gần mức lịch sử hợp lý | Sprint Goal/flow capacity có dự phòng và WIP vừa phải |
| **Nặng** | Incident lớn tiêu nhiều năng lực | Triage, ứng cứu, điều chỉnh phạm vi và minh bạch dự báo |

Đừng hiểu “dự phòng” là **thời gian không có giá trị**. Khi không xuất hiện incident, đội có thể kéo việc đã ưu tiên, test, cải tiến môi trường hoặc discovery phù hợp.

### 14.4. Cơ chế xoay vòng hỗ trợ

Một số đội thử **support rotation**:

- Một người hoặc nhóm nhỏ nhận support thường lệ theo lịch.
- Có tiêu chí rõ để kéo thêm chuyên gia khi rủi ro vượt khả năng.
- Người đang trực chọn những việc có **khả năng dừng/bàn giao** phù hợp.
- Có tài liệu/runbook và quyền kiểm tra đủ.
- Trách nhiệm on-call ngoài giờ được thiết lập theo quy định riêng, không tự động áp cho cả đội.
- Hậu kiểm sự cố chuyển thành backlog giảm rủi ro.

Thử nghiệm này có thể giúp bảo vệ thời gian tập trung, nhưng cũng có rủi ro **chuyên gia trực bị cô lập hoặc không đủ năng lực ứng cứu**. Cần theo dõi tải và chất lượng.

### 14.5. Không tự tạo “lịch sử đẹp” bằng loại bỏ sự cố khỏi dữ liệu

Nếu chỉ đo feature throughput và loại tất cả giờ incident, đội có thể dự báo quá lạc quan. Ngược lại, nếu gộp ticket support nhỏ với PBI phức tạp vào một số throughput, cũng khó dự báo feature.

Nên công bố **loại việc, điểm bắt đầu/kết thúc, mức tương đồng và ngoại lệ**; dùng số liệu để học, không để ép năng suất cá nhân.

## 15. Chính sách phân loại khẩn và thứ tự dịch vụ

### 15.1. “Ưu tiên cao” khác “phải chen ngang ngay”

Một Product Backlog Item quan trọng cho Product Goal có thể **ưu tiên cao nhưng không cần dừng công việc đang thực hiện trong giờ này**. Một incident ít xảy ra có thể cần hành động ngay vì đang gây mất dữ liệu.

Trước khi chen ngang, hỏi:

- Người dùng/hoạt động nào đang bị ảnh hưởng, có bằng chứng nào?
- Nếu chờ nhịp ưu tiên kế tiếp, hậu quả có thể xảy ra?
- Có biện pháp **giảm tác động** mà không phải kéo toàn đội không?
- Ai có thẩm quyền xác nhận mức độ sự cố hoặc nghĩa vụ?
- Hành động hiện tại làm dở những PBI nào và tác động Sprint Goal?
- Có yêu cầu giữ chất lượng, bảo mật, dữ liệu hay thông báo khẩn nào?

**Cao về giá trị** và **khẩn về thời gian** là hai chiều khác nhau. Đừng dùng chữ “khẩn” để vượt Product Owner hoặc chính sách workflow.

### 15.2. Các lớp dịch vụ thường được thảo luận trong Kanban

Trong thực hành cộng đồng Kanban, đôi khi dùng các **classes of service** như:

| Lớp minh họa | Khi phù hợp | Chính sách cần thiết |
|---|---|---|
| **Expedite** | Có tác hại đáng kể khi chờ và cần xử lý sớm hơn luồng thường | Ai được gắn nhãn, điều kiện vào/ra, giới hạn năng lực và hậu kiểm |
| **Fixed Date** | Có ngày ràng buộc được xác nhận | Xác minh ngày, việc cần đạt, tiến độ, rủi ro trễ |
| **Standard** | Việc thông thường theo giá trị/rủi ro | Pull theo thứ tự và WIP |
| **Intangible** | Việc giảm nợ kỹ thuật hoặc rủi ro dài hạn dễ bị trì hoãn | Chính sách dành năng lực dựa trên tác động, không để quên mãi |

**Đây không phải bộ bốn lớp bắt buộc của Kanban Guide.** Nhóm có thể thiết kế lớp khác hoặc không dùng nhãn này; điều quan trọng là **chính sách rõ, được kiểm tra và điều chỉnh**.

### 15.3. Hạn chế lạm dụng expedite

Nếu mọi ticket được gắn **Expedite**, nhãn mất ý nghĩa và các hạng mục quan trọng khác bị dừng vô hạn.

Một chính sách minh họa:

1. Chỉ gắn Expedite khi có **tiêu chí tác động và thời gian** được xác minh.
2. Có **người có thẩm quyền phân loại/triage** được nêu rõ.
3. Hiển thị work items bị tạm ngưng và chi phí cơ hội.
4. Đội không hạ **Definition of Done, các quality gates hay kiểm soát bắt buộc**.
5. Hậu kiểm khi sự cố kết thúc; tìm cách giảm nguyên nhân tái diễn.
6. Xem lượng việc expedite và tác động lên các luồng khác trong review.

Không nên đặt “mỗi Sprint chỉ được đúng một incident thật” nếu thực tế có sự cố nghiêm trọng hơn. Có thể **giới hạn WIP luồng khẩn theo năng lực**, nhưng sự cố nhiều hơn khả năng ứng cứu cần **escalation và biện pháp tổ chức**, không phải bỏ qua tác hại.

### 15.4. Phân biệt incident và yêu cầu sản phẩm

Ví dụ:

| Phát sinh | Triage hợp lý | Điều cần nhớ |
|---|---|---|
| Người học mất tiến độ đã xác minh và còn xảy ra | Incident theo chính sách; bảo vệ người dùng và khắc phục | Không chờ thống kê hoàn hảo mới giảm tác hại |
| Một người đề nghị thêm gamification | Ý tưởng sản phẩm, phân tích nhu cầu trước khi ưu tiên | Yêu cầu của một người không tự thành việc khẩn |
| Đối tác SSO báo sẽ đổi API theo lịch đã xác nhận | Công việc phụ thuộc/fixed-date nếu phù hợp hợp đồng | Chuẩn bị sớm, theo dõi hợp đồng và kiểm chứng |
| Một test flaky gây merge bị chặn thường xuyên | Vấn đề chất lượng kỹ thuật | Có thể ưu tiên cải tiến để giảm gián đoạn lặp |
| Yêu cầu chứng minh quyền truy cập với hạn thật | Ràng buộc đã xác nhận, cần kiểm soát/evidence | Không chấm điểm như tính năng trang trí |
| Khách hàng muốn “sửa trước 15:00” nhưng không nêu tác động | Cần làm rõ và thương lượng | Hạn mong muốn không tự là nghĩa vụ bắt buộc |

### 15.5. Không để chính sách triage tách khỏi Product Goal

Sau khi xử lý incident, đội cần hỏi:

> “Điều kiện nào khiến sự cố lặp lại? Việc sửa nguyên nhân có nên được đưa lên trước các feature mới để bảo vệ Product Goal không?”

Nếu chỉ xử lý ticket từng lần, nhóm có thể dùng hết năng lực cho những sự cố có thể phòng ngừa. **Dữ liệu incident là đầu vào quản lý Product Backlog**, không chỉ báo cáo vận hành.

## 16. Giảm chi phí bàn giao giữa vai trò, nhóm và đối tác

### 16.1. Bốn mẫu bàn giao thường gặp

| Mẫu | Bối cảnh | Rủi ro | Điều chỉnh |
|---|---|---|---|
| **Developer → Reviewer** | PR cần kiểm tra | PR lớn/thiếu test, review đợi qua múi giờ | PR nhỏ, mô tả why/risk, kiểm tra đủ trước review |
| **Product → Developers** | Làm rõ yêu cầu nghiệp vụ | Giả định chưa được chốt, ví dụ thiếu | Acceptance examples, Product Goal, câu hỏi mở |
| **Support → Engineering** | Ticket người dùng vượt khả năng hỗ trợ | Thiếu bước tái hiện, không có tác động/phiên bản | Mẫu triage, log an toàn, ảnh hưởng, mức khẩn |
| **Team → Đối tác/chuyên gia** | API contract hoặc phê duyệt | Không rõ người quyết định, thời gian chờ và nguồn hợp đồng | Handoff có scope, evidence, mốc, escalation |

**Không phải mọi bàn giao đều tránh được**. Vấn đề là làm sao **thông tin và khả năng hành động** không thất lạc ở điểm chuyển.

### 16.2. Mẫu handoff cho công việc bị chặn

~~~text
PBI / INCIDENT:
Mục tiêu sản phẩm hoặc dịch vụ:
Loại công việc / mức tác động:
Kết quả cần xác nhận từ bên nhận:
Phạm vi và điều ngoài phạm vi:
Trạng thái thật / phần đã làm:
Điều đã được kiểm chứng (link test, build, log được phép):
Điều chưa biết hoặc giả định:
Blocker và thời điểm bắt đầu chờ:
Tác động khi chờ:
Đầu mối và thẩm quyền quyết định:
Thời điểm mong muốn phản hồi, có múi giờ / lý do:
Phương án có thể làm an toàn trong khi chờ:
Điều kiện kết thúc / DoD:
~~~

Mẫu có thể đặt trong ticket hoặc PR; **không cần sinh thêm file chỉ để chứng minh có handoff**.

### 16.3. Vận hành tuyến đầu và chuyển cấp

Một đội có thể thiết kế **cấp tiếp nhận**:

- Những câu hỏi đã có hướng dẫn có thể được hỗ trợ viên xử lý mà không kéo Developers.
- Ticket khó được chuyển kèm **ngữ cảnh và bằng chứng**, không chỉ “khách báo lỗi”.
- Incidents theo mức tác động được đưa tới đầu mối ứng cứu đúng.
- Các trường hợp lặp lại dẫn tới **cải tiến tài liệu, công cụ tự phục vụ hoặc sản phẩm**, không chỉ tăng nhân lực tiếp nhận.

Tách tuyến tiếp nhận không có nghĩa **ngăn Developers tiếp xúc phản hồi người dùng**; cần vẫn có đường học hỏi từ hỗ trợ tới Product Backlog và Sprint Review/flow review.

### 16.4. Bàn giao theo múi giờ

Trong nhóm phân tán:

- Ghi **ngày/giờ/múi giờ cụ thể**, không chỉ “chiều mai”.
- Phân biệt phản hồi bình thường với cơ chế on-call đã được phân công.
- Ghi **phần chưa chạy kiểm tra** rõ hơn “xong rồi”.
- Không coi người vắng cuộc họp là đã đồng ý.
- Có nguồn hợp đồng/spec/decision log hiện hành.
- Luân phiên lịch trao đổi đồng bộ khi các vùng phải chia sẻ gánh nặng.

Không nên áp dụng **follow-the-sun** máy móc cho nghiên cứu sâu chưa rõ vấn đề, vì chuyển qua nhiều người có thể tốn nhiều thời gian khôi phục ngữ cảnh hơn thời gian tiết kiệm.

### 16.5. Giao tiếp đồng bộ và bất đồng bộ theo mức mơ hồ

| Tình huống | Hình thức gợi ý |
|---|---|
| Review PR nhỏ đã có test/rủi ro rõ | Async trong PR |
| Chốt quy tắc API có ba ngoại lệ chưa hiểu thống nhất | Sync ngắn có chuẩn bị, sau đó ghi quyết định |
| Yêu cầu đối tác xác nhận trường hợp OAuth/SSO | Async có ví dụ và mốc phản hồi; sync khi tranh luận kéo dài |
| Sự cố đang gây hại nghiêm trọng | Incident coordination theo chính sách |
| Cập nhật trạng thái routine | Board/ticket, không cần họp status riêng |
| Thảo luận why một lỗi chỉ tái hiện trên máy một người | Pairing/debug đồng bộ nếu có ích |

**Async-first không đồng nghĩa không bao giờ họp**. Đồng bộ có giá trị khi giảm nhiều lượt hiểu sai; bất đồng bộ có giá trị khi vấn đề đã đủ rõ và cần bảo vệ thời gian tập trung.

### 16.6. Quyền truy cập và kiểm soát cũng quyết định khả năng bàn giao

Một ticket có tài liệu đầy đủ vẫn không thể tiếp tục nếu người nhận:

- Không có quyền chạy integration tests.
- Không được xem log theo chính sách.
- Không có môi trường an toàn để tái hiện.
- Cần approval bảo mật/tuân thủ từ người có thẩm quyền khác.

Không nên “giải quyết” bằng cách gửi credentials hoặc dữ liệu người học qua kênh cá nhân. Phải **xử lý quyền và phụ thuộc hợp lệ**, minh bạch thời gian chờ trong workflow.

### 16.7. Khi nào không nên bàn giao?

Một số việc có **chi phí chia bối cảnh quá cao**:

- Điều tra race condition chưa có bước tái hiện rõ.
- Thiết kế kiến trúc đang có nhiều đánh đổi chưa thống nhất.
- Một sự cố nghiêm trọng cần người điều phối duy trì mạch quyết định.
- Phân tích nghiệp vụ nhiều ngoại lệ chưa có nguồn tham chiếu.

Có thể để người đang hiểu sâu **tiếp tục sở hữu mạch điều tra**, đồng thời ghép cặp để chia sẻ tri thức, cập nhật log và từng bước làm việc **bàn giao được trong tương lai**. Không nên dùng một mệnh lệnh “phải chuyển việc mỗi ngày” để tạo flow đẹp trên board.

## 17. Case study: đội học trực tuyến có Sprint liên tục bị gián đoạn

### 17.1. Bối cảnh và mục tiêu

Scrum Team phụ trách nền tảng học có **Product Goal**:

> “Người học mới có thể bắt đầu, lưu và tiếp tục bài đầu đáng tin, tăng khả năng hoàn thành học tập trong bảy ngày.”

Đội gồm Product Owner, Scrum Master và Developers có chuyên môn UI, backend, kiểm thử/vận hành. Nhu cầu thực tế gồm ba dòng:

1. **Feature delivery:** cải thiện lưu tiến độ, thiết kế trải nghiệm tiếp tục bài và đo completion.
2. **Reactive work:** lỗi sản xuất, câu hỏi hỗ trợ, CI bị chặn và thay đổi cấu hình cần xử lý.
3. **External work:** tích hợp SSO với đối tác, cần phê duyệt hợp đồng API và quyền truy cập môi trường thử.

Trước đây đội sử dụng Sprint hai tuần; mỗi lần có incident, nhiều người phải dừng feature. Một số PBI chuyển sang Sprint sau vì còn chờ review và tích hợp.

### 17.2. Dữ liệu ban đầu: bốn chu kỳ minh họa

**Tất cả dữ liệu trong case study là giả định để thực hành.** “Chu kỳ” ở đây tương đương một khoảng hai tuần; các PBI được đếm theo cùng định nghĩa minh họa.

| Chỉ báo | Chu kỳ 1 | Chu kỳ 2 | Chu kỳ 3 | Chu kỳ 4 |
|---|---:|---:|---:|---:|
| Năng lực có thể phân bổ của đội | 240 giờ | 240 giờ | 240 giờ | 240 giờ |
| Nỗ lực reactive/support trực tiếp | 18 giờ | 42 giờ | 28 giờ | 64 giờ |
| Incidents cần điều tra kéo Developers khỏi feature | 0 | 2 | 1 | 3 |
| Feature PBI bắt đầu | 8 | 9 | 7 | 10 |
| Feature PBI đạt DoD | 6 | 6 | 6 | 4 |
| Feature PBI còn mở cuối chu kỳ | 2 | 3 | 1 | 6 |
| PBI bị chặn bởi đối tác/CI lâu hơn hai ngày | 1 | 2 | 2 | 4 |
| Sprint Goal đạt theo đánh giá của team | Có | Có, đổi phạm vi | Có | Không |

**Không suy ra từ bảng:**

- Ba incident trong chu kỳ 4 là nguyên nhân duy nhất của Sprint Goal không đạt.
- Nỗ lực reactive bằng tất cả chi phí gián đoạn; chưa đo đủ chuyển ngữ cảnh và hàng chờ.
- Feature PBI có cùng kích thước, rủi ro hay độ phức tạp.
- Số Done giảm luôn có nghĩa Developers làm việc kém.
- Việc giữ Scrum chắc chắn không phù hợp chỉ sau bốn chu kỳ.

### 17.3. Phân tích tần suất và tải gián đoạn

Nhu cầu reactive không đều: 18, 42, 28, 64 giờ trong các chu kỳ; trung bình **38 giờ** trên năng lực giả định **240 giờ**, tức khoảng **15,8%** năng lực trực tiếp.

Nhưng mức tối đa quan sát là **64/240 ≈ 26,7%**, chưa kể thời gian quay lại feature, kiểm tra hồi quy và chờ quyền hỗ trợ.

Đội nhận ra:

- Một số support requests **có thể giải quyết ở tuyến đầu**.
- Một số incidents thật sự đòi hỏi cả UI/API cùng điều tra, không thể chờ Sprint sau.
- Vài việc được gọi “urgent” thực chất chỉ là yêu cầu tính năng mong muốn.
- Một lỗi CI lặp lại do dữ liệu test chung thường khiến Developers đổi việc giữa chừng.

**Giả thuyết ban đầu:** nếu triage có chính sách và giảm lỗi kiểm thử lặp, đội có thể bảo vệ Sprint Goal tốt hơn **mà chưa cần bỏ nhịp Scrum**.

### 17.4. Phân loại và tác động theo từng luồng

| Nhóm nhu cầu | Nguồn | Mức dự báo | Tính khẩn | Bàn giao | Rủi ro chính |
|---|---|---|---|---|---|
| Luồng lưu tiến độ mới | Product Goal, phản hồi người học | Trung bình; có thể chia PBI | Thường không khẩn tức thì | Trung bình nếu có API contract/AC | Giá trị, DoD, regression |
| Lỗi mất tiến độ đã xác minh | Production incident | Thấp; đột xuất | Cao theo tác động | Thấp ở giai đoạn điều tra đầu | Mất dữ liệu, người dùng bị hại |
| Yêu cầu đổi màu/nút | Stakeholder feedback | Thường có thể chờ | Thấp nếu không có nghĩa vụ đặc biệt | Cao | Lãng phí nếu chen ngang |
| Cấp cấu hình SSO định kỳ | Đối tác/vận hành | Tương đối có lịch | Theo hạn thật | Cao sau khi chuẩn hóa | Quyền và thay đổi cấu hình |
| Hợp đồng API SSO thay đột ngột | Đối tác | Thấp | Tùy ảnh hưởng/hợp đồng | Thấp nếu quyết định chưa rõ | Service break, chờ phê duyệt |
| Sửa test flaky tích hợp | Nội bộ | Có thể lên kế hoạch cải tiến | Có thể khẩn nếu mainline chặn | Trung bình | Bằng chứng chất lượng không đáng tin |
| Phỏng vấn học viên bỏ dở | Product discovery | Chủ động tổ chức | Thường không chen ngang | Trung bình qua research notes | Diễn giải sai vấn đề người dùng |

Như vậy một chính sách chung “mọi việc xếp vào Sprint và theo thứ tự” có thể không phù hợp cho incident; ngược lại “mọi yêu cầu vào flow theo thứ tự tới trước” có thể không giữ được **Product Goal**.

### 17.5. Đánh giá khả năng bàn giao thực tế

Nhóm thử xem năm tình huống:

| Việc | Quan sát bàn giao | Mức minh họa theo thang 0–4 | Ưu tiên cải thiện |
|---|---|---:|---|
| Cấu hình SSO đã có runbook/permission chuẩn | Người trực tiếp nhận xử lý độc lập | 4 | Giữ và tự động hóa phần lặp an toàn |
| Feature lưu tiến độ có AC và contract nhưng test phụ thuộc môi trường | Có thể tiếp tục phần rõ, còn blocker | 2 | Cải thiện môi trường và test |
| Incident mất tiến độ đang điều tra | Mới có log, chưa rõ nguyên nhân, cần người giữ bối cảnh | 1 | Điều phối incident, pairing, ghi timeline |
| Yêu cầu stakeholder đổi UI | Mô tả dễ chuyển nhưng chưa rõ giá trị | 2 | Làm rõ outcome, không coi bàn giao tốt là ưu tiên cao |
| Thay hợp đồng SSO chưa được xác nhận | Không có quyền quyết định hoặc spec hiện hành | 0 | Escalation, hợp đồng và thẩm quyền trước |

**Quan sát quan trọng:** bàn giao kỹ thuật tốt **không chứng minh công việc đáng ưu tiên**; bàn giao kém cũng **không có nghĩa cứ thuê thêm người là giải quyết được**. Cần tách vấn đề giá trị, rủi ro và điều kiện thực hiện.

### 17.6. Ba nút cổ chai ẩn

**Nút cổ chai A — Triage không rõ:** support và Product Owner có thể gửi yêu cầu thẳng cho mọi Developer. Người đang làm feature bị gián đoạn ngay cả khi yêu cầu không khẩn.

**Nút cổ chai B — Quyết định SSO phụ thuộc bên ngoài:** một ticket chuyển cột In Progress khi team gửi email, rồi nằm đó nhiều ngày. Dòng công việc không phân biệt **thời gian chờ** với **thời gian thực hiện**.

**Nút cổ chai C — Chất lượng tích hợp:** CI có test flaky, thiếu contract tests theo rủi ro. Một PR nhỏ có thể kéo thêm vài người điều tra khi kết quả test không tin được.

Đổi phương pháp sẽ không tự giải quyết cả ba. Cần **chính sách triage, handoff và kỹ thuật** bên cạnh nhịp điều phối.

## 18. Chọn phương án và thiết kế thử nghiệm hai Sprint

### 18.1. So sánh các lựa chọn thật

Product Owner, Scrum Master và Developers cân nhắc:

| Phương án | Lợi thế kỳ vọng | Rủi ro/đánh đổi | Điều kiện trước khi thử |
|---|---|---|---|
| **A. Giữ nguyên Scrum và cách làm cũ** | Ít chi phí thay đổi, mọi người quen sự kiện | Triage không rõ và WIP/test flaky tiếp tục | Chỉ hợp lý nếu dữ liệu cho thấy vấn đề tạm thời |
| **B. Chuyển toàn đội sang Kanban** | Nhận luồng nhu cầu liên tục, xem WIP/chờ và SLE rõ | Có thể mất Sprint Goal như điểm tập trung nếu không thay bằng cơ chế ưu tiên outcome | Thiết kế Product Goal, policies và nhịp đánh giá mới |
| **C. Giữ Scrum, bổ sung Kanban flow/policies và XP** | Giữ nhịp sản phẩm; bảo vệ incident bằng triage và cải thiện kiểm thử | Cần năng lực cho cải tiến, làm rõ trách nhiệm | WIP, định nghĩa khẩn, handoff và test có người thực hiện |
| **D. Chia năng lực support thường lệ và feature** | Bảo vệ thời gian tập trung, xử lý ticket lặp | Rủi ro silo, mất phản hồi người dùng, tăng bàn giao | Runbook, escalation, phối hợp và tránh thiếu người ứng cứu |

Không nên mặc định C là “phương án tốt nhất mọi nơi”. Trong case study **giả định**, C là **thử nghiệm ít xáo trộn nhưng giải quyết trực tiếp những nguyên nhân đã quan sát**, có thể kết hợp một phần D sau khi xác minh khả năng bàn giao.

### 18.2. Tuyên bố quyết định có thể kiểm chứng

> “Trong hai Sprint tới, giữ Product Goal và Sprint Goal có giá trị; dùng chính sách phân loại incident/standard rõ, ưu tiên hoàn tất PBI trước khi mở thêm; thử support rotation trong giờ làm; bổ sung contract/integration checks cho luồng lưu tiến độ và mẫu handoff SSO. Chúng ta sẽ đo phần việc bị gián đoạn, thời gian chờ, chất lượng và Sprint Goal. Sau hai Sprint sẽ quyết định giữ, điều chỉnh hoặc thử mô hình flow liên tục rộng hơn.”

Đó là **một giả thuyết vận hành**, không tuyên bố “đã chọn Scrum trọn đời”.

### 18.3. Working agreements cho giai đoạn thử

1. **Nguồn công việc:** tất cả yêu cầu có ticket đủ mô tả; incidents dùng kênh ứng cứu đúng chính sách.
2. **Triage:** người chịu trách nhiệm phân loại theo tác động/khẩn; Product Owner quản lý thứ tự backlog sản phẩm.
3. **Sprint Goal:** giữ mục tiêu ngắn hạn rõ; khi phát sinh sự cố, Developers minh bạch và thương lượng phạm vi với Product Owner.
4. **WIP:** thử giới hạn số PBI đang mở theo năng lực thật; blocker vẫn hiển thị trong WIP.
5. **Handoff:** ticket SSO có contract version, môi trường, điều cần đối tác xác nhận và mốc phản hồi.
6. **CI:** test flaky được phân loại và sửa; không rerun cho tới khi xanh rồi coi là đã khắc phục.
7. **DoD:** mọi PBI feature chỉ Done khi đáp ứng tiêu chuẩn chất lượng chung.
8. **Review:** Retrospective kiểm tra số liệu và trải nghiệm, không xếp hạng cá nhân.

### 18.4. Phân chia việc khẩn và việc có thể chờ

| Tín hiệu | Trong thử nghiệm xử lý thế nào? |
|---|---|
| Người học đang mất tiến độ do lỗi được xác minh | Ứng cứu, giảm tác động, ghi chi phí cơ hội và hậu kiểm |
| Khách hàng muốn đổi màu nút | Thu phản hồi, PO xem backlog theo giá trị và bằng chứng |
| CI đỏ do code làm sai kiểm soát bắt buộc | Giữ chất lượng, sửa/test lại trước Done |
| Hỗ trợ cấu hình SSO có runbook rõ | Tuyến tiếp nhận/rotation xử lý theo quyền |
| Quyết định contract SSO chưa rõ | Blocked, handoff có cấu trúc, escalation đúng thẩm quyền |
| Chưa biết vì sao completion không tăng | Discovery timebox, không tự cam kết giải pháp lớn |

**Không cố dồn mọi yêu cầu vào Sprint Goal.** Incident ứng cứu có logic ưu tiên riêng, nhưng vẫn cần liên hệ tác động tới mục tiêu và sản phẩm.

### 18.5. Giảm WIP và tích hợp sớm

Nhóm nhận ra nhiều PBI bị dở vì:

- Người UI đợi API spec.
- Reviewer đợi PR quá lớn.
- Integration test chạy muộn.
- Developer chuyển qua support nhưng không có handoff.

Biện pháp:

1. Chia PBI thành lát dọc có thể kiểm chứng.
2. Cập nhật acceptance examples/contract trước khi UI và API triển khai song song.
3. Pairing ở phần khó và chia tri thức thay vì một người duy nhất sửa được.
4. Viết test từ nhỏ tới tích hợp phù hợp rủi ro.
5. Ưu tiên hoàn tất PBI đang chờ review/test trước khi mở việc mới.

Không đặt mục tiêu “giảm số ticket In Progress” bằng cách **đẩy thẻ sang Done khi DoD chưa đạt**; điều đó chỉ làm dashboard đẹp.

### 18.6. Kết quả sau thử nghiệm: dữ liệu minh họa, chưa chứng minh nhân quả

Giả sử có hai chu kỳ tiếp theo:

| Chỉ báo | Trước thử nghiệm: chu kỳ 4 | Sau: chu kỳ 5 | Sau: chu kỳ 6 |
|---|---:|---:|---:|
| Nỗ lực reactive trực tiếp | 64 giờ | 38 giờ | 40 giờ |
| Feature PBI bắt đầu | 10 | 7 | 8 |
| Feature PBI đạt DoD | 4 | 6 | 7 |
| Feature PBI còn mở cuối kỳ | 6 | 1 | 1 |
| Incidents thực sự cần ứng cứu | 3 | 1 | 2 |
| PBI chờ đối tác/CI hơn hai ngày | 4 | 2 | 1 |
| Sprint Goal đạt | Không | Có | Có |
| Người học gặp lỗi lưu tiến độ sau release | Chưa đủ dữ liệu | Chưa đủ dữ liệu | Chưa đủ dữ liệu |

**Các số hoàn toàn giả định**, không phải kết quả có thật và **không đủ chứng minh** các chính sách gây ra mọi cải thiện. Incidents có thể tự giảm vì vận may hoặc seasonality, scope PBI có thể khác, và chưa biết outcome sản phẩm.

Kết luận thận trọng có thể là:

> “Nhóm có dấu hiệu giảm việc mở dở và chờ kéo dài. Chưa đủ dữ liệu về giá trị người dùng hoặc độ ổn định lâu dài. Tiếp tục giữ những chính sách có ích, đo thêm chất lượng và quan sát nhu cầu phát sinh trong các giai đoạn biến động.”

### 18.7. Khi nào nên đổi phương án?

**Giữ hoặc mở rộng thử nghiệm** nếu:

- Team vẫn tạo Increment đạt DoD và tiến gần Product Goal.
- Incidents được xử lý đúng mức rủi ro.
- Work item age và thời gian chờ có xu hướng giảm ở cùng loại việc.
- Nhịp làm bền vững hơn, không tăng overtime hoặc lỗi production.

**Điều chỉnh hoặc thay mô hình** nếu:

- Sprint Goal liên tục trở nên không khả thi vì nhu cầu ngẫu nhiên thật, ngay cả khi triage và giảm lỗi.
- Một luồng support có loại việc rõ, đủ handoff, có thể vận hành tốt hơn theo flow riêng.
- Nhiều việc bị chặn vì phụ thuộc ngoài quyền nhóm, cần thay điều phối/nguồn lực chứ không chỉ bảng.
- Các chính sách mới tăng chi phí họp và phê duyệt nhưng không giảm rủi ro.

**Không bao giờ dùng việc bỏ DoD hoặc bỏ ghi incident làm điều kiện chứng minh mô hình mới thành công.**

## 19. Các ràng buộc bổ sung có thể thay đổi quyết định

### 19.1. Mức độ an toàn và kiểm soát của sản phẩm

Một đội xây chức năng liên quan tiền, dữ liệu nhạy cảm, quyền truy cập hoặc hệ thống trọng yếu cần:

- Yêu cầu và kiểm soát đã xác nhận.
- Kiểm thử và bằng chứng đúng phạm vi.
- Quyền đánh giá/phê duyệt theo chính sách.
- Trình tự ứng cứu và khôi phục.
- Handoff có đủ ngữ cảnh và quyền.

Điều này **không đồng nghĩa bắt buộc dùng Scrum hoặc Kanban**. Nó ảnh hưởng cách thiết kế **workflow, DoD, release và gián đoạn** trong phương án được chọn.

### 19.2. Cửa sổ thời gian cố định nhưng phạm vi có thể điều chỉnh

Một sự kiện công khai hoặc nghĩa vụ hợp đồng có ngày đã xác nhận không tự có nghĩa tất cả feature đều phải giao đúng ngày.

Nhóm cần phân biệt:

- **Hạn ràng buộc thật** và bên có thẩm quyền.
- **Phạm vi tối thiểu** bắt buộc.
- Phần có thể giảm/đổi để giữ chất lượng.
- Rủi ro và phụ thuộc ảnh hưởng dự báo.
- Thời điểm cần quyết định nếu có dấu hiệu không thể đạt.

Một Sprint có thể giúp kiểm tra Increment thường xuyên; Kanban có thể giúp nhìn flow và dự báo. **Không phương pháp nào biến bất định thành bảo đảm ngày chắc chắn**.

### 19.3. Cấu trúc nhóm và mức tự chủ

Nếu công việc cần đi qua năm bộ phận có quyền riêng:

- Bàn giao có hợp đồng, tiêu chí và bằng chứng đủ chưa?
- Phụ thuộc có thể được **giảm trong kiến trúc và thiết kế nhóm** không?
- Thời gian chờ ai có thể cải thiện?
- Có cùng mục tiêu sản phẩm hay đang tối ưu từng bộ phận?
- Có cần một người điều phối ra quyết định xuyên nhóm theo thẩm quyền?

Một Scrum Team được kỳ vọng **cross-functional và self-managing** trong phạm vi sản phẩm. Nếu tổ chức không tạo điều kiện để nhóm tạo Increment, chỉ đổi tên họp không giải quyết được trở ngại.

### 19.4. Công việc từ xa và múi giờ

Khi người thực hiện/reviewer ở nhiều múi giờ:

- Viết handoff có quyết định, test, rủi ro, blocker và bước tiếp.
- Dùng async cho việc rõ; sync ngắn cho vấn đề mơ hồ.
- Định nghĩa thời gian phản hồi theo **giờ làm việc thực tế**, không ép tất cả online.
- Xem work item age tại các điểm review xuyên vùng.
- Có quy trình on-call hợp lệ cho sự cố cần người trực.

Không áp hệ thống “follow-the-sun” nếu **chi phí chuyển giao vượt lợi ích** hoặc đe dọa quyền riêng tư và chất lượng.

### 19.5. Công cụ và dữ liệu đo không đủ tin cậy

Nếu board có nhiều ticket Done nhưng CI đang đỏ và thực tế còn lỗi:

1. Chuẩn hóa **định nghĩa Done và trạng thái workflow**.
2. Xác nhận mốc bắt đầu/kết thúc để đo flow.
3. Phân loại work items thay vì gộp feature/support/incident.
4. Kiểm tra logging/telemetry và quyền dữ liệu.
5. Sau đó mới dùng số liệu so sánh phương pháp.

**Một bảng đẹp không thay chất lượng, cũng không phải bằng chứng sản phẩm tạo giá trị.**

## 20. Đo xem cách tiếp cận đã chọn có thực sự phù hợp

### 20.1. Đặt giả thuyết vận hành trước khi đổi quy trình

Đừng chỉ tuyên bố:

> “Chúng ta chuyển sang Kanban để nhanh hơn.”

Hãy nêu:

> “Vì nhu cầu support đến không đều và nhiều PBI chờ review, nếu dùng chính sách triage rõ và giới hạn WIP, chúng ta kỳ vọng **work item age ở bước review giảm, công việc gần Done hoàn tất đều hơn và sự cố được xử lý đúng mức**, trong khi lỗi production và tải làm thêm giờ không tăng.”

Giả thuyết này có thể **bị phản bác**, giúp retro không trở thành cuộc họp chỉ xác nhận lựa chọn của người đề xuất.

### 20.2. Bộ tín hiệu nên cân bằng

| Nhóm | Tín hiệu | Điều cần tìm | Không suy luận |
|---|---|---|---|
| **Nhu cầu đến** | Arrivals theo loại, số incident có xác minh | Tính biến động và áp lực thực tế | Nhiều ticket nghĩa là đội làm kém |
| **Gián đoạn** | Số lần chuyển việc, giờ reactive trực tiếp, việc bị dừng | Chi phí tác động tới kế hoạch | Một tỷ lệ chung xác định framework |
| **Dòng công việc** | WIP, work item age, cycle time, throughput | Việc nào già, chờ nhiều và khó hoàn tất | Throughput tăng luôn là giá trị tăng |
| **Chất lượng** | DoD, CI reliability, lỗi hồi quy, sự cố | Có giảm lỗi phát hiện muộn không? | CI xanh bằng chứng hết mọi rủi ro |
| **Kết quả sản phẩm** | Tỷ lệ học tiếp/hoàn thành, phản hồi người dùng | Đội có tiến gần Product Goal không? | Một chỉ số trước–sau chứng minh nhân quả |
| **Bàn giao** | Số lần hỏi lại, blocker do thiếu context/quyền | Người nhận có thể hành động an toàn không? | Tài liệu nhiều hơn luôn tốt hơn |
| **Nhịp bền vững** | Overtime, mức gián đoạn, cảm nhận tải | Có bền vững qua nhiều chu kỳ không? | Mọi người ít phàn nàn nghĩa là an toàn |
| **Phụ thuộc** | Thời gian chờ đối tác/chuyên gia, số PBI bị chặn | Hợp đồng bàn giao và escalation có hiệu quả không? | Mọi ngày chờ là lỗi người đang giữ ticket |

Số liệu cần đi cùng **mẫu số, định nghĩa và bối cảnh**. So sánh hai giai đoạn có loại việc khác nhau mà không ghi phạm vi dễ tạo kết luận sai.

### 20.3. Một bảng quyết định đủ nhỏ

~~~yaml
# Decision card minh họa; không phải tiêu chuẩn bắt buộc.
decision_id: FLOW-APPROACH-02
product_goal: "Người học lưu và tiếp tục bài đáng tin"
observations:
  - "Nỗ lực reactive dao động mạnh giữa các chu kỳ"
  - "Nhiều PBI chờ CI/review và phụ thuộc SSO"
  - "Support thường lệ có thể phân tuyến"
uncertainties:
  - "Chưa đo đầy đủ chi phí chuyển ngữ cảnh"
  - "Chưa đủ dữ liệu outcome sau phát hành"
options:
  - "Giữ Scrum và thay đổi policies"
  - "Chuyển sang flow Kanban toàn đội"
  - "Tách support theo trách nhiệm với handoff rõ"
decision_to_try: "Giữ Scrum, áp WIP/triage và XP trong hai Sprint"
owner_context:
  product_priority: "Product Owner"
  delivery_and_quality: "Developers"
  scrum_effectiveness: "Scrum Master"
  incidents: "Theo chính sách tổ chức"
signals:
  - "Work item age tại review/integration"
  - "Incidents, reactive load và Sprint Goal"
  - "DoD, lỗi production và overtime"
guardrails:
  - "Không hạ chất lượng để tăng throughput"
  - "Không coi mọi yêu cầu stakeholder là incident"
review_point: "Retrospective sau hai Sprint và đánh giá tiếp nếu chưa đại diện"
decision_options: ["Giữ", "Điều chỉnh", "Dừng"]
~~~

Trên thực tế có thể ghi trong decision log/tài liệu nhóm; không cần tạo thêm công cụ chỉ để lưu thẻ.

### 20.4. Tín hiệu nào có thể khiến nhóm đổi quyết định lần nữa?

| Bằng chứng mới | Khả năng thích ứng |
|---|---|
| Hầu hết “interrupts” là câu hỏi thường, tuyến đầu giải quyết được | Cải tiến phân tuyến, giữ nhịp sản phẩm nếu có ích |
| Incidents thật liên tục chiếm phần lớn năng lực dù đã sửa nguyên nhân lặp | Xem lại cách tổ chức phản ứng và nhịp flow |
| Work item age tăng ở chờ approval ngoài tổ chức | Giải quyết thẩm quyền/handoff, không chỉ đổi board |
| Feature Done đều nhưng outcome người dùng không cải thiện | Xem lại giả thuyết sản phẩm, không chỉ tối ưu throughput |
| Thử support rotation làm người trực quá tải và chất lượng giảm | Điều chỉnh rotation, tài liệu, năng lực hoặc cơ chế chuyên gia |
| XP tests giúp giảm regression nhưng thời gian review vẫn dài | Tối ưu PR size, phân quyền review và hợp đồng bàn giao |
| Công việc đã có thể chuẩn hóa và tự phục vụ | Tự động hóa phần lặp với kiểm soát thích hợp |

Thích ứng dựa trên bằng chứng là **điều kiện thành công của Agile**, không phải biểu hiện đội “không có quy trình”.

### 20.5. Đừng biến số liệu thành mục tiêu tự thân

Một nhóm có thể “cải thiện” throughput bằng cách chia một PBI thành mười ticket cực nhỏ và gọi từng cái Done, trong khi người học vẫn không lưu được tiến độ.

Một nhóm có thể “giảm incident” bằng cách đổi nhãn ticket thành defect hoặc không ghi nhận.

Một nhóm có thể “giảm work item age” bằng cách đóng ticket chưa đạt chất lượng rồi mở ticket khác.

Vì vậy cần **Definition of Done, workflow minh bạch, chất lượng và outcome** đi cùng flow metrics. Đừng xếp hạng cá nhân bằng số ticket hoặc story points.

## 21. Những ngộ nhận khi lựa chọn Scrum, Kanban và cách kết hợp

| Ngộ nhận / phản mẫu | Vì sao sai hoặc thiếu? | Cách điều chỉnh |
|---|---|---|
| “Nhiều ticket phát sinh nghĩa là phải bỏ Scrum.” | Chưa biết cái nào thực sự khẩn và tải thực tế | Triage và đo tác động trước |
| “Có Sprint là không được xử lý sự cố giữa Sprint.” | Scrum bảo vệ Sprint Goal nhưng không cấm ứng cứu cần thiết | Xử lý rủi ro, minh bạch và thích ứng đúng trách nhiệm |
| “Kanban không cần mục tiêu hoặc ưu tiên.” | Dòng công việc vẫn phải gắn giá trị và policy | Quản lý flow cùng Product Goal/dịch vụ |
| “Chỉ cần tạo bảng To Do–Doing–Done là dùng Kanban.” | Thiếu Definition of Workflow, WIP, flow metrics và policies | Làm rõ trạng thái, điểm bắt đầu/Done, kiểm soát WIP |
| “Scrum là họp nhiều, Kanban là không họp.” | Nhầm cấu trúc events với cách cộng tác | Chọn hoạt động kiểm tra/thích ứng theo mục đích |
| “XP chỉ là viết thêm unit tests.” | XP gồm nhiều thực hành kỹ thuật và giá trị | Kết hợp TDD, CI, refactoring, pairing khi có ích |
| “Scrumban là một khuôn khổ có danh sách nghi thức cố định.” | Cách kết hợp khác nhau, nhãn không xác định chính sách | Mô tả rõ operating model thực tế |
| “Nhiều interrupts thì đặt buffer 20% là xong.” | Lịch sử biến động, chi phí phụ và tác động khác nhau | Dự báo nhiều tình huống và xem lại |
| “Một tỷ lệ trên 30% mặc định cần Kanban.” | Không có ngưỡng chính thức phổ quát | Xem loại việc, mức bất định, handoff và outcome |
| “Incident và yêu cầu stakeholder đều là việc khẩn.” | Khác mức tác động và hậu quả chờ | Có triage, bằng chứng và quyền phân loại |
| “Đánh nhãn Expedite là công việc tự hoàn tất nhanh hơn.” | Tổng năng lực và WIP không đổi | Giới hạn ngoại lệ và minh bạch chi phí cơ hội |
| “Có WIP limit thì không được xử lý sự cố thật.” | WIP limit không thay quy trình an toàn | Chính sách xử lý khẩn và escalation |
| “Item bị Blocked có thể bỏ khỏi WIP.” | Che lượng việc dở và điểm nghẽn | Hiển thị và quản lý blocker rõ |
| “Work item age lớn nghĩa là người giữ ticket kém.” | Chờ phụ thuộc, quyền, review hoặc môi trường | Phân tích luồng và điều kiện làm việc |
| “Throughput nhiều ticket hơn chứng minh giá trị cao hơn.” | Kích thước và loại ticket có thể đổi | Đo outcome, chất lượng và flow cùng nhau |
| “Velocity giữa hai đội so sánh trực tiếp được.” | Thang ước lượng và loại việc khác nhau | Dùng dữ liệu của chính workflow với định nghĩa rõ |
| “Phải chia support thành đội riêng để không làm phiền Developers.” | Có thể tạo silo và mất vòng phản hồi sản phẩm | Đánh giá khả năng bàn giao và chi phí phối hợp |
| “Handoff tốt chỉ cần ghi thật nhiều tài liệu.” | Thiếu quyền, test, người quyết định vẫn tắc | Đảm bảo khả năng tiếp tục an toàn |
| “Follow-the-sun luôn giảm cycle time.” | Tái dựng bối cảnh có thể lâu hơn khoảng chờ | Chuyển giao những việc có ranh giới rõ |
| “Một chuyên gia duy nhất giúp quyết định nhanh.” | Có thể tạo single point of failure và hàng đợi | Pairing, review rotation và chia kiến thức |
| “Không cần đo blocker vì chỉ tính giờ code.” | Thời gian chờ kéo dài thời gian tới giá trị | Đo work item age và dependency |
| “CI xanh nghĩa là Done.” | Test có giới hạn; còn yêu cầu DoD khác | Dùng DoD và evidence theo rủi ro |
| “Muốn phản ứng nhanh thì bỏ test hoặc approval bắt buộc.” | Tăng nguy cơ làm hại người dùng | Chia lát cắt, tự động hóa đúng phần, giữ chất lượng |
| “Sprint Goal là cam kết hoàn thành mọi ticket trong Sprint.” | Goal là mục tiêu, không phải checklist tuyệt đối | Dùng Goal làm trọng tâm và linh hoạt phạm vi |
| “Kanban SLE là lời hứa mọi việc xong đúng ngày.” | SLE là kỳ vọng xác suất theo dữ liệu | Nêu phạm vi, xác suất, bất định và SLA thật nếu có |
| “Cứ phát sinh sự cố thì quay lại kế hoạch cũ sau đó.” | Không học nguyên nhân gốc | Hậu kiểm và ưu tiên giảm rủi ro tái diễn |
| “Chọn mô hình tốt nhất một lần rồi giữ cố định.” | Nhu cầu, sản phẩm và đội thay đổi | Thử, đo, giữ–sửa–dừng |
| “Thêm công cụ sẽ sửa việc bị chặn.” | Thiếu quyền/thẩm quyền và chất lượng không tự hết | Làm rõ policy, handoff và năng lực |
| “Tối ưu từng đội là tối ưu toàn hệ thống.” | Handoff và phụ thuộc có thể tăng lead time | Xem dòng giá trị đầu-cuối |
| “Người làm việc nhanh nhất nên xử lý mọi việc khẩn.” | Tạo phụ thuộc cá nhân và rủi ro quá tải | Chính sách ứng cứu, pairing và năng lực bền vững |

## 22. Checklist lựa chọn cách tiếp cận

### 22.1. Quan sát nhu cầu

1. **Product Goal/dịch vụ:** đội đang tối ưu kết quả nào cho ai?
2. **Nguồn nhu cầu:** feature, discovery, support, incident, compliance, dependency?
3. **Tần suất:** bao nhiêu yêu cầu mỗi tuần/chu kỳ theo từng loại?
4. **Mức dao động:** có những tuần cao bất thường hoặc mùa vụ không?
5. **Tải thực:** công sức trực tiếp và chi phí chuyển ngữ cảnh là gì?
6. **Tác động:** công việc nào thực sự gây hại nếu chờ?
7. **Chính sách khẩn:** ai phân loại, theo tiêu chí nào?
8. **Giả khẩn:** yêu cầu nào có thể đi qua Product Backlog bình thường?
9. **Năng lực:** có tính nghỉ phép, review, ứng cứu và chất lượng không?

### 22.2. Đặc trưng công việc

10. **Giá trị:** PBI có liên hệ outcome và Product Goal không?
11. **Bất định:** điều gì cần khám phá trước khi xây?
12. **Kích thước:** có lát cắt nhỏ, có thể Done và kiểm chứng?
13. **Phụ thuộc:** cần đối tác, chuyên gia, môi trường hay approval?
14. **Rủi ro:** dữ liệu, bảo mật, quyền, vận hành, người dùng?
15. **Tính lặp:** việc nào có thể dùng runbook/tự động hóa?
16. **Thời hạn:** hạn nào thật, nguồn nào xác nhận?
17. **Definition of Done:** chuẩn chất lượng được áp dụng nhất quán?

### 22.3. Khả năng bàn giao

18. **Mục tiêu/phạm vi:** người khác đọc ticket có hiểu cần tạo gì?
19. **Quyết định:** acceptance criteria, contract, ADR có nguồn hiện hành?
20. **Evidence:** test/build/log và trạng thái kiểm tra đã rõ?
21. **Quyền:** người nhận có môi trường, quyền và dữ liệu thử hợp lệ?
22. **Đầu mối:** ai xác nhận nghiệp vụ và ai xử lý blocker?
23. **Tài liệu vừa đủ:** không tạo bản sao rải rác, không thiếu ngữ cảnh?
24. **Giờ làm:** các múi giờ/handoff có cơ chế phản hồi công bằng?
25. **Kiến thức tập trung:** có phụ thuộc một người cần pairing/chia tri thức?

### 22.4. Thiết kế và đánh giá phương án

26. **Nhịp:** Sprint Goal có tạo giá trị không, hay flow liên tục phù hợp hơn?
27. **WIP:** chính sách kéo việc và hạn chế việc dở có rõ?
28. **Triage:** incident/standard/fixed-date có tiêu chí và quyền?
29. **Kỹ thuật:** TDD/CI/contract tests/refactoring có giảm rủi ro thay đổi?
30. **Chất lượng:** không hạ DoD hoặc kiểm soát bắt buộc?
31. **Dự báo:** có trình bày bất định và nhiều tình huống năng lực?
32. **Số liệu:** WIP, cycle time, age, throughput, quality/outcome có cùng định nghĩa?
33. **Bền vững:** overtime, on-call và tải review có được xem?
34. **Thử nghiệm:** có mô tả lựa chọn, phạm vi, người phối hợp, guardrails?
35. **Xem lại:** khi nào đánh giá giữ–sửa–dừng theo bằng chứng?

Checklist **không phải 35 bước bắt buộc trong mọi quyết định**. Tập trung vào những câu hỏi có khả năng thay đổi lựa chọn và mức rủi ro của đội.

## 23. Bài tập vận dụng

### Bài tập 1 — Phân biệt gián đoạn thật và công việc mới bình thường

Một Scrum Team nhận sáu tình huống trong hai ngày:

1. Người học không đăng nhập được, lỗi đang ảnh hưởng đa số người dùng.
2. Stakeholder muốn đổi màu nút “Tiếp tục”.
3. CI đỏ khi merge một PR đang triển khai.
4. Đối tác hỏi cách gọi endpoint có tài liệu hướng dẫn đầy đủ.
5. Một lỗ hổng kiểm soát quyền dữ liệu được xác minh.
6. Product Owner bổ sung một acceptance example sau khi nhóm phát hiện trường hợp timeout chưa rõ.

**Yêu cầu:**

- Với mỗi tình huống, xác định **nhu cầu mới, blocker của việc hiện tại hay gián đoạn cần tái ưu tiên**.
- Nêu dữ kiện còn cần để quyết định mức khẩn.
- Đề xuất **đường tiếp nhận**: backlog, support, CI/debug hay incident process.
- Giải thích vì sao không nên coi yêu cầu số 2 có mức khẩn ngang số 5.
- Nêu tác động có thể có tới Sprint Goal và DoD.

**Gợi ý:** tình huống số 6 có thể là làm rõ phạm vi bình thường khi học thêm; số 1 và 5 cần đánh giá bảo vệ người dùng theo rủi ro.

### Bài tập 2 — Tính tần suất và tải gián đoạn

Trong một chu kỳ, đội ghi nhận:

| Loại | Số items | Công sức trực tiếp |
|---|---:|---:|
| Feature đã chủ động chọn | 12 | 168 giờ |
| Support thường lệ | 9 | 12 giờ |
| Incident nghiêm trọng | 1 | 24 giờ |
| Thay đổi hợp đồng đối tác ngoài kế hoạch | 2 | 36 giờ |

**Yêu cầu:**

1. Tính tổng items và tổng giờ.
2. Nếu coi support, incident và thay đổi đối tác là phát sinh, tính **tỷ lệ items** phát sinh.
3. Tính **tỷ lệ công sức trực tiếp** phát sinh.
4. Giải thích hai tỷ lệ khác nhau và **điều gì còn thiếu** về chuyển ngữ cảnh.
5. Nêu vì sao không thể chọn Scrum/Kanban chỉ từ một tỷ lệ.

**Gợi ý kiểm tra:** tổng 24 items và 240 giờ; 12/24 = **50% items** phát sinh; (12+24+36)/240 = **30% giờ** trực tiếp. Phân loại “phát sinh” là giả định của bài; với dữ liệu thật cần định nghĩa rõ.

### Bài tập 3 — Phân loại công việc và thiết kế chính sách

Nhóm nhận:

- Một user story phát triển tính năng học tiếp.
- Một spike thử tính khả thi của thuật toán gợi ý.
- Một yêu cầu cấp quyền có quy trình xác nhận.
- Một lỗi UI ít tác động.
- Một lỗi mất dữ liệu đang tiếp diễn.
- Một nâng cấp dependency có hạn chính sách đã được xác nhận.

**Yêu cầu:** lập bảng có các cột **mục tiêu, khả năng dự đoán, tính khẩn, rủi ro, cách kiểm chứng, khả năng bàn giao và cách ưu tiên**. Nêu loại việc nào nên được timebox, loại nào có thể pull theo workflow, loại nào cần ứng cứu.

### Bài tập 4 — Chấm độ bàn giao bằng bằng chứng

Ba PBI:

- **A:** Có acceptance criteria, API contract, test xanh, người nhận có quyền truy cập và bước tiếp rõ.
- **B:** Một Developer nói “tôi hiểu hết”, code nằm trên nhánh riêng, không có test, thiếu người review.
- **C:** Có tài liệu đầy đủ nhưng cần quyền truy cập môi trường do đối tác kiểm soát; chưa biết ngày cấp.

**Yêu cầu:**

1. Đánh giá từng PBI theo thang minh họa 0–4 và nêu lý do.
2. Chỉ ra **điều cần làm** để nâng khả năng bàn giao.
3. Phân biệt “tài liệu đủ” với “có thể tiếp tục”.
4. Nếu B đang liên quan incident nghiêm trọng, có nên bàn giao cho người chưa hiểu chỉ để giảm work item age không?
5. Nêu một cách pairing giúp giảm rủi ro tập trung tri thức.

### Bài tập 5 — Lựa chọn Scrum, Kanban hoặc phối hợp

Xét ba đội:

**Đội A:** phát triển tính năng mới, có Product Goal rõ; mỗi Sprint có thể tạo Increment; incidents thật ít.

**Đội B:** vận hành một dịch vụ có nhiều yêu cầu đến ngẫu nhiên, mức tác động khác nhau; công việc nhỏ lặp lại nhiều và có thể chuẩn hóa.

**Đội C:** làm sản phẩm mới nhưng cũng hỗ trợ ứng dụng cũ; những tuần có incident lớn phải dừng feature; API có một chuyên gia duy nhất hiểu.

**Yêu cầu:**

- Với mỗi đội, đề xuất **ít nhất hai phương án khả thi**.
- Chọn một phương án **để thử trước**, không gọi là câu trả lời tuyệt đối.
- Nêu rủi ro lớn nhất nếu chọn sai.
- Đề xuất chính sách triage và một cải tiến bàn giao.
- Xác định ba tín hiệu sẽ xem lại sau vài chu kỳ.

**Gợi ý:** riêng đội C, sửa điểm phụ thuộc một chuyên gia có thể quan trọng hơn việc đổi tên phương pháp.

### Bài tập 6 — Sự cố xuất hiện giữa Sprint

Sprint Goal là “Người học lưu và mở lại tiến độ đáng tin”. Ngày thứ sáu, production xuất hiện lỗi làm mất tiến độ của một nhóm người học. Cùng lúc, một stakeholder yêu cầu nâng cấp toàn bộ giao diện trang chủ trong Sprint này.

**Yêu cầu:**

1. Phân loại mức khẩn của hai việc theo **tác động và bằng chứng**.
2. Trình bày vai trò Product Owner, Developers và Scrum Master.
3. Giải thích cách điều chỉnh **Sprint Backlog/phạm vi** mà vẫn bảo vệ Sprint Goal khi có thể.
4. Nêu những điều không được bỏ qua trong DoD.
5. Khi nào mới cân nhắc hủy Sprint và ai có thẩm quyền?
6. Đề xuất một hành động retro để giảm nguy cơ lỗi tương tự.

### Bài tập 7 — Thiết kế Definition of Workflow bằng Kanban

Một đội support có các trạng thái “Mới”, “Đang làm”, “Chờ đối tác”, “Review” và “Xong”. Ticket thường bị chuyển sang “Chờ đối tác” nhưng không có người hỗ trợ hoặc mốc xem lại.

Điền mẫu:

~~~text
Mục tiêu dịch vụ:
Loại work items:
Điểm bắt đầu:
Điểm Done:
Các trạng thái và chính sách chuyển:
WIP limit muốn thử và lý do:
Cách thể hiện Blocked và người hỗ trợ:
Chính sách Expedite nếu thực sự cần:
Cách lấy SLE từ lịch sử, với loại việc và xác suất:
Tín hiệu cycle time / work item age / throughput:
Kiểm tra chất lượng trước khi Done:
Mốc xem lại và điều kiện điều chỉnh:
~~~

**Gợi ý:** không loại các ticket Blocked khỏi WIP chỉ để bảng trông ít việc.

### Bài tập 8 — Dự báo năng lực có biến động

Đội có năng lực hai tuần là **240 giờ**; trong bốn chu kỳ vừa rồi công việc reactive trực tiếp chiếm **18, 42, 28, 64 giờ**.

**Yêu cầu:**

1. Tính trung bình, nhỏ nhất, lớn nhất.
2. Tính tỷ lệ trung bình trên 240 giờ.
3. Đề xuất cách lập Sprint Planning hoặc kế hoạch flow mà **không hứa một con số chắc chắn**.
4. Nêu hai yếu tố khiến lịch sử không đại diện cho tương lai.
5. Đề xuất cách theo dõi overtime và chất lượng để bảo vệ nhịp bền vững.

**Gợi ý:** trung bình 38 giờ ≈ 15,8%; nhỏ nhất 18, lớn nhất 64. Không biến mức trung bình thành “buffer đúng” cho mọi Sprint.

### Bài tập 9 — Handoff đối tác xuyên múi giờ

Frontend Việt Nam chờ một xác nhận từ đối tác SSO ở châu Âu. Ticket chỉ ghi “waiting SSO”; developer vẫn mở ba PBI khác. Một tuần sau, đối tác trả lời nhưng lại hỏi về contract version và môi trường.

**Yêu cầu:**

- Viết handoff có **câu hỏi cụ thể, version, scope, evidence, mốc và thẩm quyền**.
- Thiết kế cách hiển thị work item age và trạng thái Blocked.
- Đề xuất một hoạt động đồng bộ có mục tiêu khi email hỏi–đáp kéo dài.
- Nêu cách giảm WIP trong khi chờ.
- Giải thích vì sao không nên chấm điểm developer dựa trên một tuần chờ đối tác.

### Bài tập 10 — Phân loại classes of service

Một nhóm đề xuất bốn lớp Expedite, Fixed Date, Standard, Intangible. Người quản lý muốn gắn **mọi yêu cầu khách hàng lớn** vào Expedite.

**Yêu cầu:**

1. Viết định nghĩa vào lớp Expedite có thể kiểm chứng.
2. Phân biệt **giá trị cao** và **khẩn cấp thật**.
3. Nêu một ví dụ Fixed Date có nguồn hạn được xác nhận.
4. Đề xuất giới hạn thực hành và cách xử lý khi incidents vượt khả năng ứng cứu.
5. Nêu lý do bộ bốn lớp trên là **một lựa chọn thực hành**, không phải cấu trúc bắt buộc của Kanban.

### Bài tập 11 — Tập trung vào người dùng, không chỉ throughput

Sau khi chuyển sang flow liên tục, đội hoàn thành nhiều support tickets hơn nhưng tỷ lệ người học quay lại bài không tăng. Đồng thời, lỗi lưu tiến độ tiếp tục lặp lại.

**Yêu cầu:**

- Phân biệt **output, flow và outcome**.
- Nêu những quyết định ưu tiên có thể cần thay đổi.
- Đề xuất một PBI giảm nguyên nhân sự cố.
- Nêu hai điều kiện chất lượng cần kiểm chứng.
- Thiết kế cách xem lại giá trị với Product Owner/stakeholders.

### Bài tập 12 — Thiết kế thử nghiệm lựa chọn phương pháp cho đội của bạn

Chọn một đội hoặc giả định một dịch vụ phần mềm. Hoàn thành:

~~~text
Product Goal hoặc mục tiêu dịch vụ:
Loại công việc và tỷ trọng, cách lấy dữ liệu:
Tần suất arrivals / incidents theo loại:
Tác động gián đoạn lên năng lực và chất lượng:
Mẫu biến động (mùa vụ, release, phụ thuộc):
Thời gian chờ và blockers:
Khả năng bàn giao, thang đánh giá và bằng chứng:
Các lựa chọn Scrum / Kanban / phối hợp:
Phương án thử đầu tiên và lý do:
Những thực hành XP hoặc cải thiện kỹ thuật cần thiết:
Triage / WIP / handoff policies:
Phân bổ năng lực và cách diễn đạt bất định:
Người chịu trách nhiệm ưu tiên và quyết định khẩn:
Tín hiệu flow, quality, Product Goal:
Guardrails về DoD, bảo mật và sustainable pace:
Khoảng thử và mốc xem lại:
Điều kiện giữ / điều chỉnh / dừng:
~~~

**Tự đánh giá:** bạn có giải thích **vì sao công việc của đội đòi hỏi nhịp đó**, hay chỉ nêu tên framework? Có chỉ rõ cách **kiểm chứng lựa chọn và đổi ý khi bằng chứng mới xuất hiện** hay không?

## 24. Tổng kết

Đánh giá tần suất gián đoạn, loại công việc và khả năng bàn giao là bước quan trọng trong **lựa chọn cách tiếp cận Agile**, vì nó làm rõ **thực tế công việc** trước khi áp khuôn khổ:

1. **Không đếm gián đoạn máy móc:** phân biệt arrivals, số lần phải đổi việc, tải trực tiếp, chuyển ngữ cảnh, thời gian chờ và mức tác động người dùng.
2. **Không đồng nhất loại việc:** feature, discovery, incident, support, technical improvement, compliance và external dependency khác nhau về mục tiêu, độ khẩn, khả năng dự báo và kiểm chứng.
3. **Đánh giá bàn giao như khả năng hành động:** cần mục tiêu, phạm vi, quyết định, test/evidence, quyền, blocker và bước tiếp; không chỉ một ticket có người được gán.
4. **Scrum hữu ích khi nhịp Sprint Goal và Increment giúp tạo giá trị**, nhưng vẫn phải ứng cứu incident thật, thích ứng phạm vi và giữ Definition of Done.
5. **Kanban hữu ích khi cần quản lý dòng nhu cầu và thời gian chờ**, với Definition of Workflow, WIP, throughput, cycle time, work item age, SLE và chính sách triage rõ.
6. **XP giúp thay đổi an toàn và giảm chi phí bàn giao:** TDD, CI, pairing, refactoring, small releases và sustainable pace hỗ trợ Scrum hoặc Kanban.
7. **Cách kết hợp phải có thiết kế cụ thể:** mô tả ai ưu tiên, khi nào pull việc, chính sách khẩn, handoff và chất lượng; nhãn “Scrumban” không thay cho quy tắc.
8. **Dự báo theo bằng chứng và bất định:** không có tỷ lệ buffer hay ngưỡng gián đoạn phổ quát; dùng lịch sử, kịch bản và chất lượng để chọn mức năng lực hợp lý.
9. **Đo cả flow, chất lượng và outcome:** throughput hoặc velocity đẹp không có ý nghĩa nếu người học tiếp tục mất tiến độ, PBI chưa đạt DoD hoặc đội phải làm thêm giờ thường xuyên.
10. **Xem lựa chọn phương pháp là giả thuyết có thể kiểm chứng:** thử thay đổi nhỏ, công bố đánh đổi, theo dõi guardrails và **giữ–điều chỉnh–dừng** dựa trên phản hồi.

> **Câu hỏi ghi nhớ:** “Đội đang bị ngắt quãng vì **nhu cầu thật sự cần ứng cứu**, vì **cách sắp thứ tự và giới hạn WIP chưa rõ**, hay vì **công việc khó bàn giao và chất lượng kỹ thuật yếu**? Điều gì sẽ thay đổi nếu ta chỉnh chính sách, kỹ thuật và nhịp phối hợp — và sẽ đo bằng chứng nào?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint Goal, Product Goal, Increment, Definition of Done, trách nhiệm và điều kiện thích ứng trong Sprint.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — ưu tiên cộng tác, phần mềm chạy được, phản hồi sớm, sự xuất sắc kỹ thuật và nhịp bền vững.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- [Scrum.org — Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams) — tham khảo cách sử dụng thực hành Kanban để hỗ trợ Scrum.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — TDD, pair programming, continuous integration và các thực hành kỹ thuật bổ trợ.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tích hợp liên tục để phát hiện sai khác sớm.
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) — tách triển khai và mở tính năng khi cần giảm rủi ro.
- [DORA](https://dora.dev/) — tham khảo các phép đo và nghiên cứu về hiệu quả giao phần mềm, cân nhắc bối cảnh trước khi dùng số liệu so sánh.
