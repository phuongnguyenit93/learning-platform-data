# Chuyển đổi Agile: Điều chỉnh cơ chế giao việc, đánh giá và phân bổ nguồn lực

Một công ty phát triển nền tảng đăng ký workshop tuyên bố đã chuyển sang Agile: các nhóm có bảng Kanban, họp Daily Scrum và làm việc theo Sprint hai tuần. Thế nhưng trưởng bộ phận vẫn phân task trực tiếp cho từng lập trình viên vào đầu tuần, mỗi người đồng thời phục vụ ba dự án; KPI cá nhân thưởng theo số ticket và story points; Product Owner không được đổi thứ tự Product Backlog nếu chưa qua ba cấp quản lý. Khi có lỗi production, người đang làm Sprint Goal bị kéo sang xử lý sự cố nhưng cam kết ban đầu không thay đổi. Cuối Sprint, nhiều ticket được đóng, song tính năng xác nhận chỗ vẫn chưa đạt Definition of Done.

Vấn đề không nằm ở tên cuộc họp. **Cơ chế giao việc, cách đánh giá và cách phân bổ nguồn lực đang gửi những tín hiệu mâu thuẫn với mục tiêu Agile.** Công việc bị đẩy vào nhiều hơn khả năng hoàn tất; chỉ tiêu cá nhân khuyến khích tối đa hóa số task thay vì cộng tác để tạo Increment; đội hình bị xáo trộn làm thời gian chờ và chi phí chuyển ngữ cảnh tăng.

Ngược lại, thay toàn bộ cơ chế bằng khẩu hiệu “tự quản” cũng không đủ. Tổ chức vẫn phải chọn đầu tư, bảo vệ chất lượng, thực hiện nghĩa vụ nhân sự, đáp ứng ràng buộc tài chính/pháp lý và xử lý ưu tiên khẩn. Một chuyển đổi đáng tin là **thiết kế lại những quyết định hằng ngày**: ai xác định giá trị, ai lựa chọn công việc và cách thực hiện, khi nào được bắt đầu một item mới, đánh giá kết quả bằng bằng chứng nào, nguồn lực ổn định được tài trợ cho mục tiêu nào và cách điều chỉnh khi nhu cầu thay đổi.

Bài thuộc chương **Chuyển đổi Agile**, mô-đun **AGILE_DEVELOPMENT**. Mục tiêu của mô-đun là hiểu giá trị, nguyên tắc Agile trong phát triển thích ứng qua phản hồi sớm và bàn giao sản phẩm tăng dần; thực hành user story, backlog, Scrum, Kanban, XP và số đo dòng công việc để phối hợp phù hợp. Bài này tập trung vào **điều chỉnh cơ chế giao việc, đánh giá và phân bổ nguồn lực** sao cho các cơ chế không tự triệt tiêu khả năng giao giá trị và học từ phản hồi.

Tất cả số liệu doanh nghiệp, ngân sách, tên nhóm, thời hạn và biểu mẫu trong bài là **tình huống giả định để học**. Không có tỷ lệ phân bổ ngân sách, mô hình thưởng hay chu kỳ đánh giá nào đúng cho mọi tổ chức. Những thay đổi liên quan hợp đồng lao động, quyền riêng tư, phân biệt đối xử, công đoàn hoặc thù lao phải được xem xét theo chính sách và pháp luật áp dụng; các ví dụ không thay thế tư vấn nhân sự/pháp lý.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao cơ chế giao việc, đánh giá và tài trợ năng lực cần nhất quán với **giá trị, chất lượng, dòng công việc và cải tiến liên tục**.
2. Phân biệt **push assignment** (đẩy việc), **pull system** (kéo việc theo năng lực/chính sách), tự quản trong phạm vi trách nhiệm và sự buông lỏng quản trị.
3. Thiết kế chính sách chọn và bắt đầu công việc từ Product Backlog/Ready, WIP limit, handling of expedite và công việc ngoài kế hoạch.
4. Phân biệt vai trò **Product Owner, Developers, Scrum Master, lãnh đạo, HR, finance và các bên kiểm soát rủi ro** trong các quyết định.
5. Nhận biết KPI tạo hành vi sai khi thưởng theo **số task, giờ bận, story points hoặc velocity cá nhân**.
6. Thiết kế bộ đánh giá kết hợp **outcome người dùng, chất lượng, flow, học hỏi và đóng góp cộng tác**, không lấy một thước đo làm phán quyết cá nhân.
7. Phân biệt đánh giá **hệ thống/nhóm** và đánh giá **phát triển năng lực nhân sự**, bao gồm công bằng, quyền riêng tư và giới hạn dữ liệu.
8. Giải thích lợi ích và đánh đổi của **nhóm sản phẩm ổn định**, funding theo sản phẩm/dòng giá trị, cấp người ngắn hạn và tài trợ dự án theo mốc.
9. Lập mô hình **capacity hữu dụng**, phân bổ cho phát triển sản phẩm, vận hành, công việc bắt buộc và dự phòng với giả định minh bạch.
10. Điều chỉnh portfolio và quyền quyết định khi ngân sách, nhu cầu hoặc bằng chứng sản phẩm thay đổi.
11. Thiết kế một **lộ trình chuyển đổi tăng dần** với baseline, thử nghiệm, guardrails, mốc xem lại và cơ chế phản hồi.
12. Phân tích tình huống workshop, tính toán các ví dụ và xây một đề xuất thực thi trong nhóm.

## 2. Ba cơ chế tạo thành một hệ thống hành vi

### 2.1. Giao việc quyết định điều gì được bắt đầu

Cơ chế giao việc trả lời:
- Ai có quyền xác định mục tiêu và thứ tự ưu tiên?
- Công việc đi vào hệ thống từ đâu?
- Khi nào một người hoặc nhóm được kéo item mới?
- Ai điều chỉnh kế hoạch khi phát hiện thông tin mới?
- Công việc khẩn và phụ thuộc bên ngoài được xử lý ra sao?
- Ai chịu trách nhiệm đảm bảo một lát cắt hoàn tất đạt Definition of Done?

### 2.2. Đánh giá quyết định điều gì được xem là thành công

Cơ chế đánh giá trả lời:
- Tổ chức đo **sản lượng đầu ra** hay **kết quả đối với người dùng**?
- Chất lượng và tác động lâu dài được bảo vệ thế nào?
- Các đóng góp khó đếm như hỗ trợ, review, mentoring, giảm sự cố có được ghi nhận?
- Một kết quả không đạt giả thuyết nhưng giúp học và tránh đầu tư sai có được xem xét công bằng?
- Đánh giá để **cải thiện hệ thống** hay để giám sát từng người?
- Việc phát triển nghề nghiệp, thù lao và phản hồi cá nhân được thực hiện thế nào mà không làm méo flow metrics?

### 2.3. Phân bổ nguồn lực quyết định điều gì khả thi

Cơ chế phân bổ nguồn lực trả lời:
- Bao nhiêu **năng lực ổn định** được tài trợ cho một sản phẩm hoặc dòng giá trị?
- Những chuyên gia dùng chung phục vụ bằng cách nào để tránh nút thắt?
- Khi thay đổi ưu tiên, điều chỉnh **mục tiêu và backlog** hay thường xuyên chuyển người giữa các nhóm?
- Có chỗ cho bảo trì, bảo mật, vận hành, nợ kỹ thuật và sự cố không?
- Ngân sách được xem lại dựa trên bằng chứng ở những mốc nào?
- Chi phí chuyển đổi, onboarding và mất kiến thức hệ thống được tính ra sao?

### 2.4. Một vòng phản hồi sai lệch

~~~mermaid
flowchart TD
    A[Quản lý đẩy nhiều task cho từng người] --> B[WIP và chuyển ngữ cảnh tăng]
    B --> C[Cycle time dài, review và test dồn]
    C --> D[Không đạt mốc giao giá trị]
    D --> E[Đánh giá kém theo số task/đúng hạn cục bộ]
    E --> F[Khuyến khích đóng task nhỏ, bỏ hỗ trợ]
    F --> G[Tích hợp và chất lượng suy giảm]
    G --> D
    D --> H[Chuyển người giữa dự án để chữa cháy]
    H --> B
~~~

Đây là một **vòng lặp có thể xảy ra**, không phải kết luận mọi tổ chức đều vận hành như vậy. Muốn sửa nó, chỉ đổi Daily Scrum thành một định dạng khác không đủ; phải xem lại những **tín hiệu, quyền hạn và luồng đầu tư** đằng sau hành vi.

### 2.5. Một vòng phối hợp phù hợp hơn

~~~mermaid
flowchart TD
    A[Product Goal và nhu cầu khách hàng] --> B[Product Backlog minh bạch, một trật tự]
    B --> C[Nhóm có năng lực ổn định kéo việc phù hợp WIP]
    C --> D[Increment đạt Definition of Done]
    D --> E[Phát hành và kiểm tra phản hồi]
    E --> F[Outcome, quality, flow, learning]
    F --> G[Thích ứng backlog, chính sách và đầu tư]
    G --> B
    G --> H[Phát triển năng lực và gỡ trở ngại tổ chức]
    H --> C
~~~

Đánh giá và tài trợ ở đây **không biến mất**; chúng giúp nhóm có điều kiện và trách nhiệm để làm việc có ích.

## 3. Chẩn đoán trạng thái hiện tại trước khi thay cơ chế

Một thay đổi cơ cấu lớn dựa trên cảm giác có thể tạo thêm thủ tục và mất lòng tin. Hãy quan sát **quyết định và dòng công việc thực**, không chỉ khảo sát “chúng ta có Agile không?”.

### 3.1. Bản đồ hiện trạng

Với một user story gần đây, truy vết:
1. Yêu cầu xuất phát từ đâu? Ai xác nhận nhu cầu người dùng?
2. Ai sắp thứ tự trong backlog? Có bao nhiêu danh sách ưu tiên song song?
3. Ai chỉ định từng người thực hiện? Nhóm có thể tự chọn cách phối hợp không?
4. Item bắt đầu khi nào? Có bao nhiêu item đã mở đồng thời?
5. Bao nhiêu lần chờ review, môi trường, quyết định, phê duyệt?
6. Khi bị gián đoạn, ai cập nhật dự báo và điều gì được ngừng?
7. Khi nào item đạt DoD? Có thêm một hàng chờ phát hành khác không?
8. Người dùng đã nhận giá trị và phản hồi gì?
9. Ai được đánh giá cao/thấp trong chuỗi này và dựa trên tín hiệu nào?
10. Việc này được tài trợ bằng nguồn nào, có ngắt vì dự án khác không?

### 3.2. Ba mẫu bất nhất thường gặp

| Mục tiêu được tuyên bố | Cơ chế thực tế trái chiều | Hành vi có thể xuất hiện |
| --- | --- | --- |
| “Tập trung vào Sprint Goal” | Trưởng phòng giao việc ngoài Sprint trực tiếp cho từng người | Sprint Goal mất ý nghĩa, kế hoạch thay mà không minh bạch |
| “Hợp tác đa chức năng” | KPI cá nhân dựa số ticket đóng; hỗ trợ đồng nghiệp không được ghi nhận | Người ta ưu tiên task dễ, né review/test chung |
| “Giao phần mềm liên tục” | Các nhóm chỉ được cấp người theo dự án ba tuần, đội hình đổi liên tục | Onboarding và handoff lặp lại, CI và ownership yếu |
| “Phản hồi sớm” | Mọi phát hành nhỏ phải qua nhiều cấp duyệt giống thay đổi dữ liệu lớn | Trễ cơ hội học, backlog tích tụ |
| “Chất lượng quan trọng” | Thưởng chỉ theo đúng hạn, không theo lỗi hoặc khả năng phục hồi | Đẩy lỗi sang QA/production, giảm test |
| “Tự chủ nhóm” | Quản lý chỉ định mọi việc và mọi giải pháp kỹ thuật | Nhóm không thể thích ứng với bằng chứng mới |

Không nên tự kết luận rằng một chỉ tiêu **luôn** gây các hành vi ấy. Đây là giả thuyết cần xem dữ liệu, quan sát và trao đổi an toàn với những người thực hiện.

### 3.3. Baseline tối thiểu trước thay đổi

| Góc nhìn | Dữ liệu có thể thu | Câu hỏi |
| --- | --- | --- |
| **Giá trị** | Tỷ lệ hoàn thành tác vụ, phản hồi người dùng, mục tiêu sản phẩm | Người dùng thực sự được lợi chưa? |
| **Flow** | Throughput, cycle time distribution, WIP, work item age | Việc đi qua hệ thống thế nào? |
| **Chất lượng** | Lỗi nghiêm trọng, lỗi thoát ra production, rework, recovery | Có đánh đổi chất lượng để nhanh hơn không? |
| **Ưu tiên** | Số lần đổi thứ tự và nguồn yêu cầu ngoài luồng | Có bao nhiêu luồng điều hành song song? |
| **Năng lực** | Chuyển người giữa dự án, thời gian onboarding, shared dependency | Năng lực có ổn định không? |
| **Cơ chế đánh giá** | Mục tiêu thưởng/ghi nhận thực tế và hành vi phát sinh | Tín hiệu khuyến khích có hợp mục đích? |
| **Quyết định** | Số tầng duyệt, thời gian chờ, nguyên nhân block | Đâu là kiểm soát tạo giá trị, đâu là chờ? |

Nhớ bảo vệ dữ liệu cá nhân và không gắn tên người để suy diễn năng suất. **Mục tiêu của baseline là cải tiến hệ thống**, không tìm người chịu lỗi.

## 4. Cơ chế giao việc: từ “đẩy task cho người” sang “kéo việc để hoàn tất”

### 4.1. Push và pull khác nhau ở thời điểm bắt đầu

**Push assignment**: người điều phối giao trước nhiều task cho mỗi cá nhân bất kể WIP hiện có. Ví dụ “A làm ba UI tickets, B làm bốn API tickets, C làm hai bug”. Hệ thống dễ tạo nhiều item mở cùng lúc và người nhận bị kỳ vọng xử lý tất cả song song.

**Pull system**: công việc có thứ tự và điều kiện sẵn sàng rõ; khi có năng lực, người/nhóm **kéo item theo chính sách WIP và mục tiêu chung**, tập trung hoàn tất trước khi mở thêm. Pull không có nghĩa muốn chọn bất kỳ việc nào theo sở thích.

| Quyết định | Push thường gặp | Pull có chính sách |
| --- | --- | --- |
| Item nào được ưu tiên? | Nhiều quản lý cùng đẩy việc | Product Backlog/priority minh bạch |
| Bắt đầu lúc nào? | Ngay khi được giao, dù đã bận | Khi có capacity và đáp ứng điều kiện pull |
| WIP | Dễ tăng theo số người và đầu việc | Giới hạn theo trạng thái/luồng phù hợp |
| Blocker | Người thực hiện tự xoay xở | Nhóm hỗ trợ giải chặn theo chính sách |
| Hoàn tất | Có thể tối ưu task của người | Tập trung Increment/đầu ra thực sự Done |
| Đổi ưu tiên | Cử thêm người hoặc task bất ngờ | Minh bạch trade-off, tái hoạch định có trách nhiệm |

### 4.2. Pull không phải bỏ vai trò lãnh đạo

Lãnh đạo/nhóm vẫn cần:
- Product Goal và tiêu chí giá trị.
- Danh sách công việc được sắp thứ tự.
- Điều kiện Ready/Started/Finished.
- Quyền ra quyết định, người xử lý blocker.
- Giới hạn WIP và chính sách expedite.
- Guardrails chất lượng, bảo mật, vận hành.
- Cơ chế đánh giá kết quả và cải tiến.

Nếu chỉ nói “mọi người cứ tự chọn việc” trong khi có 100 PBI không rõ mục tiêu, đó **không phải một cơ chế phối hợp đủ trưởng thành**.

### 4.3. Ví dụ bảng công việc đăng ký workshop

~~~text
Intake --> Ready --> Doing --> Review --> Verify --> Done
                      ^ STARTED                     ^ FINISHED

Quy ước minh họa:
- Intake: yêu cầu mới, chưa cam kết.
- Ready: được ưu tiên và đủ thông tin để kéo.
- Doing: công việc đang được thực hiện.
- Review/Verify: công việc vẫn thuộc WIP.
- Done: đạt Definition of Done đã thống nhất.
~~~

Giả sử một nhóm thử giới hạn:
- Doing ≤ 3 item.
- Review ≤ 2 item.
- Tổng WIP từ Started đến Finished ≤ 5 item.

Đây là **ngưỡng giả định để thử**, không phải công thức tính từ số thành viên. Nếu Review đầy, chính sách có thể là **giúp hoàn tất review** trước khi mở thêm Doing. Nếu một item bị blocked, **vẫn tính trong WIP**; chuyển về Ready chỉ để chỉ số đẹp sẽ che tình trạng thật.

### 4.4. Cơ chế giao việc còn bao gồm quyền từ chối hoặc đổi cách thực hiện

Một nhóm có trách nhiệm phải có khả năng phản hồi:
- “Story này chưa rõ acceptance criteria; chưa thể bắt đầu an toàn.”
- “Có việc khẩn production; cần thương lượng lại phạm vi.”
- “Để đạt DoD, phải ưu tiên test trước nhánh giao diện mới.”
- “Chúng tôi có thể giao một lát cắt giá trị nhỏ hơn sớm hơn.”
- “Không có năng lực để nhận cả hai mục tiêu cùng lúc, cần lựa chọn.”

**Được phản hồi trên bằng chứng không đồng nghĩa được bỏ mục tiêu.** Trách nhiệm giải thích trade-off, cập nhật dự báo và bảo vệ chất lượng phải đi cùng quyền tự chủ.

## 5. Ai quyết việc gì? Product Owner, Developers, Scrum Master và quản lý

### 5.1. Trách nhiệm trong Scrum

Nếu nhóm áp dụng Scrum theo Scrum Guide 2020:
- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog, bao gồm mục tiêu sản phẩm và thứ tự backlog.
- **Developers** chịu trách nhiệm tạo kế hoạch Sprint Backlog, điều chỉnh kế hoạch mỗi ngày hướng Sprint Goal, giữ chất lượng theo Definition of Done và tạo Increment hữu ích.
- **Scrum Master** chịu trách nhiệm về tính hiệu quả Scrum và giúp tổ chức cải thiện Scrum, gỡ trở ngại.
- **Scrum Team** tự quản, đa chức năng, không có các phân nhóm hoặc cấp bậc bên trong Scrum Team theo định nghĩa framework.

Lãnh đạo tổ chức vẫn có trách nhiệm về **đầu tư, nhân sự, chiến lược, pháp lý và điều kiện làm việc**. Những trách nhiệm này không tự biến họ thành người chỉ định mọi task hằng ngày trong Sprint.

### 5.2. Sprint Goal là cam kết định hướng, không phải danh sách task cứng

Trong Sprint Planning, Scrum Team xác định Sprint Goal và lựa chọn công việc khả thi. Developers lập kế hoạch thực hiện. Nếu phát hiện việc mới:
- Không nên lặng lẽ giao thêm task rồi giữ nguyên mọi kỳ vọng.
- Product Owner và Developers có thể **thương lượng phạm vi** theo điều kiện mục tiêu, không làm suy giảm Sprint Goal.
- Nếu xuất hiện công việc mới đe dọa Sprint Goal, cần minh bạch và điều chỉnh cách phối hợp.
- Trường hợp Sprint Goal trở nên lỗi thời do hoàn cảnh thay đổi, Scrum Guide cho phép **Product Owner hủy Sprint** theo điều kiện phù hợp; đó không phải công cụ dùng hằng tuần cho mọi việc chen ngang.

**Tự quản không có nghĩa Scrum Team có quyền quyết ngân sách hoặc yêu cầu bảo mật ngoài thẩm quyền**, và quản lý nhân sự không có nghĩa được âm thầm sửa Sprint Backlog như một danh sách giao việc cá nhân.

### 5.3. Ma trận quyền quyết định minh họa

| Quyết định | Người chịu trách nhiệm chính | Người cần phối hợp | Guardrail |
| --- | --- | --- | --- |
| Product Goal và thứ tự Product Backlog | Product Owner | Stakeholders, Developers | Minh bạch chiến lược và giá trị |
| Sprint Goal và lựa chọn công việc Sprint | Scrum Team theo trách nhiệm từng thành phần | PO/Developers | Khả thi, DoD, capacity thực |
| Cách phân chia kỹ thuật, pairing, test | Developers | PO khi ảnh hưởng phạm vi/giá trị | Chất lượng và an toàn |
| WIP policy và cách xử lý blocker | Nhóm quản lý luồng theo thỏa thuận | PO, người điều phối phụ thuộc | Không che WIP, rõ ranh giới |
| Ưu tiên danh mục nhiều sản phẩm | Lãnh đạo portfolio/những người có thẩm quyền | Product leadership, finance | Mục tiêu và ngân sách |
| Tuyển, đánh giá nhân sự, thù lao | Cấp quản lý/HR được ủy quyền | Người lao động, chuyên gia liên quan | Công bằng, bảo mật và pháp luật |
| Review quyền dữ liệu hoặc tuân thủ | Người có thẩm quyền theo chính sách | Developers/security/legal | Không bỏ kiểm soát bắt buộc |
| Incident nghiêm trọng | Incident lead/on-call theo quy trình | Các bên chịu tác động | Bảo vệ người dùng và phục hồi |

Bảng chỉ định hướng **phân tách quyền**, không thay chính sách thực của bất kỳ tổ chức nào. Tránh hai cực đoan: **manager quyết mọi chi tiết**, hoặc **không ai chịu trách nhiệm cuối**.

## 6. Chính sách nhận công việc khẩn, công việc ngoài luồng và phụ thuộc

### 6.1. “Ưu tiên cao” không tự tạo thêm năng lực

Giả sử nhóm đã có năm item WIP và một production bug nghiêm trọng xuất hiện. Nếu tổ chức yêu cầu nhận bug đồng thời vẫn giữ mọi deadline, người thực hiện có thể phải làm quá giờ hoặc giảm test.

Một chính sách tốt cần:
1. Phân loại hậu quả: an toàn/dữ liệu, sự cố dịch vụ, yêu cầu có hạn thật, yêu cầu thường.
2. Ai có quyền **expedite** một item?
3. Điều kiện nào cho phép vượt WIP tạm thời, và phải **tạm dừng/đổi việc nào**?
4. Ai thông báo trade-off tới Product Owner và stakeholder?
5. Bao giờ xem lại danh mục để tránh mọi item đều là “khẩn”?
6. Cần bảo vệ đường xử lý incident độc lập ra sao?

**Expedite là cơ chế ngoại lệ có kiểm soát**, không phải một backlog thứ hai của người có quyền lực hơn.

### 6.2. Capacity buffer và loại demand

Một nhóm không chỉ xây tính năng mới. Có:
- Công việc sản phẩm theo Product Goal.
- Production support, bug và incident.
- Bảo mật, tuân thủ, nâng cấp dependency.
- Test automation, refactoring và giảm nợ kỹ thuật.
- Học kỹ năng và chia sẻ kiến thức.
- Công việc khẩn khó dự báo.

Không nên lập kế hoạch 100% thời gian là feature coding rồi coi mọi hoạt động khác là “không năng suất”. Tỷ lệ dự phòng cần dựa **lịch sử demand, rủi ro, năng lực và mục tiêu**, không có chuẩn 10%, 20% hay 30% bắt buộc.

### 6.3. Khi có nhiều yêu cầu từ nhiều nơi

Nếu Product Owner đặt một thứ tự backlog nhưng người quản lý phòng ban, sales và vận hành đều giao việc trực tiếp cho Developers, nhóm sẽ có **nhiều kênh ưu tiên thực tế**. Cách sửa:
- Tạo điểm tiếp nhận và công bố chính sách xử lý.
- Phân biệt incident thật với đề xuất mới.
- Với công việc sản phẩm, đưa vào backlog có thứ tự và owner rõ.
- Với sự cố, dùng on-call/runbook, cập nhật tác động lên kế hoạch.
- Người có quyền quyết ưu tiên giữa sản phẩm cần nêu **cái gì bị lùi** khi đưa cái mới vào.
- Ghi nhận thông tin cho stakeholder và điều chỉnh forecast khi cần.

## 7. Từ giao task cá nhân sang ownership của kết quả nhóm

### 7.1. Hoàn thành một task chưa đồng nghĩa hoàn thành user story

Ví dụ PBI “Học viên phân biệt rõ đang chờ và đã có chỗ” có những việc:
- Giao diện dùng đúng nhãn.
- API trả trạng thái nhất quán.
- Test quyền và tình huống lỗi.
- Kiểm chứng trên thiết bị có rủi ro.
- Thu phản hồi để biết học viên hiểu đúng.

Nếu mỗi người được đánh giá chỉ bằng task riêng, họ có thể đóng UI/API tickets mà không ai chịu trách nhiệm **tích hợp và xác minh end-to-end**.

### 7.2. Phân chia trách nhiệm không phải phân chia silo

Developers có thể chủ động:
- Pairing ở phần khó.
- Hỗ trợ người đang bị blocker.
- Review code của nhau.
- Hoàn tất một story trước khi bắt đầu story khác.
- Chia sẻ kiến thức để tránh key-person dependency.
- Làm việc với PO để chia nhỏ story.

**Ownership nhóm đối với Increment** không xóa accountability cá nhân về chất lượng công việc và hành vi nghề nghiệp. Nó điều chỉnh nơi tổ chức đặt mục tiêu cuối: **một kết quả chung có ích**, thay vì nhiều phiếu việc riêng lẻ.

### 7.3. Ví dụ Working Agreement cho giao việc

~~~text
- Một Product Backlog với thứ tự ưu tiên minh bạch cho một sản phẩm.
- Nhóm kéo item từ Ready khi có capacity và đúng mục tiêu.
- Không giao việc trực tiếp ngoài luồng trừ incident/ngoại lệ đã định nghĩa.
- Item blocked vẫn nằm trong WIP, có lý do và người hỗ trợ.
- Trước khi bắt đầu mới, xem item gần Done nào cần giúp.
- Chia việc và pairing do Developers phối hợp trong guardrails.
- Thay đổi lớn ảnh hưởng Sprint Goal cần minh bạch với PO/Developers.
- Không giảm Definition of Done để tăng throughput ngắn hạn.
- Mỗi item Done phải có bằng chứng chất lượng phù hợp.
- Mọi chính sách sẽ được xem lại sau một thời gian thử.
~~~

Đây là **ví dụ chính sách**, không phải quy tắc bắt buộc cho mọi team.

## 8. Đánh giá theo hệ thống kết quả, không tối đa hóa một con số

### 8.1. Outcome, output, flow và quality trả lời câu hỏi khác nhau

| Góc nhìn | Ví dụ workshop | Câu hỏi | Điều không thể tự kết luận |
| --- | --- | --- | --- |
| **Outcome** | Học viên hiểu đúng trạng thái; giảm hỏi lại | Người dùng nhận giá trị không? | Một thay đổi code có là nguyên nhân duy nhất? |
| **Output** | 15 user stories Done | Đã bàn giao được gì? | Mỗi story có giá trị như nhau? |
| **Flow** | WIP, throughput, cycle time, work item age | Công việc đi qua hệ thống thế nào? | Ai là nhân viên “giỏi nhất”? |
| **Quality** | Lỗi xác nhận chỗ, availability, rework | Có giao đúng và an toàn không? | Chỉ số thấp do chất lượng hay do ít traffic? |
| **Learning** | Giả thuyết đã thử, quyết định thay đổi | Có học từ phản hồi không? | Nhiều thí nghiệm có đồng nghĩa giá trị tăng? |
| **Capability** | CI, test, chia sẻ kiến thức, độ sẵn sàng ứng phó | Có duy trì khả năng giao lâu dài? | Có thể quy hết cho một cá nhân? |

**Không có một KPI thay thế cho phán đoán có bối cảnh.** Các chỉ số cần định nghĩa mẫu số, giai đoạn, mức tin cậy và quyền truy cập phù hợp.

### 8.2. Vì sao velocity không phải chỉ số đánh giá cá nhân

**Story points** là ước lượng tương đối trong bối cảnh một nhóm sử dụng kỹ thuật ước lượng đó. **Velocity** là lượng story points hoàn tất theo Sprint khi nhóm có dùng points; nó có thể hỗ trợ forecast trong cùng nhóm.

Những cách sử dụng có vấn đề:
- Thưởng theo story points cá nhân.
- So velocity giữa hai nhóm có thang điểm khác nhau.
- Yêu cầu mỗi Sprint tăng points dù item và DoD thay đổi.
- Gọi story points là “giờ công” hoặc “giá trị khách hàng”.
- Ép tách item chỉ để số ticket/points tăng.

Khi điểm trở thành mục tiêu thưởng, hành vi ước lượng, chia task và chọn item có thể thay đổi để đạt điểm, làm dữ liệu mất ích lợi. **Không nên dùng velocity như bảng xếp hạng năng suất.**

### 8.3. Throughput cũng không tự là giá trị

Một nhóm đóng 30 ticket nhỏ thay vì 10 ticket tương đối lớn: throughput tăng, nhưng điều này chưa chứng minh:
- Người dùng tốt hơn.
- Chất lượng cải thiện.
- Năng lực được sử dụng hiệu quả hơn.
- Mục tiêu sản phẩm tiến triển hơn.
- Những item cũ không bị bỏ lại.

Cần xem loại item, kích thước, Definition of Done, cycle time distribution và outcome.

### 8.4. Nhìn cả hạng mục chưa hoàn tất

Nếu một đội xử lý 20 ticket nhỏ nhanh nhưng còn 4 story cũ bị chặn từ nhiều tuần, báo cáo “cycle time các item đã Done giảm” có thể bỏ qua những item **chưa finished**. Cần nhìn **work item age**, hàng chờ và lý do block song song với phân bố cycle time.

### 8.5. Không thưởng vì làm hỏng guardrails

Chỉ số outcome tăng nhưng:
- Lỗi quyền dữ liệu gia tăng.
- Xác nhận vượt sức chứa.
- Incidents production nhiều.
- Nhân viên phải làm ngoài giờ thường xuyên.
- Nợ kỹ thuật tích lũy tới mức không thể thay đổi.

thì chưa thể gọi là thành công bền vững. Bất biến nghiệp vụ, DoD và điều kiện an toàn phải được xác định **trước** khi đánh giá một thử nghiệm.

## 9. Đánh giá nhóm và đánh giá con người: hai mục đích khác nhau

### 9.1. Flow metrics chủ yếu dùng để cải tiến hệ thống

Cycle time của một PBI phụ thuộc:
- Độ khó và kích thước item.
- Các hệ thống và chuyên gia liên quan.
- Hàng chờ review, kiểm thử, phê duyệt.
- Thay đổi ưu tiên và số lần bị ngắt.
- Tình trạng CI/môi trường.
- Cách định nghĩa Started/Finished.

Vì vậy **không nên gán cycle time của item cho hiệu suất một cá nhân**. Một người hỗ trợ review, mentoring hoặc xử lý sự cố có thể đóng ít task hơn nhưng tạo đóng góp quan trọng cho cả nhóm.

### 9.2. Đánh giá phát triển nhân sự vẫn cần

Agile **không xóa phản hồi nghề nghiệp, đánh giá trách nhiệm hoặc chính sách nhân sự**. Người quản lý và HR vẫn cần hỗ trợ:
- Năng lực chuyên môn và kỹ năng tăng trưởng.
- Khả năng cộng tác, chia sẻ kiến thức và hỗ trợ người khác.
- Chất lượng, sự thận trọng về an toàn và trách nhiệm với cam kết đã thương lượng.
- Sự chủ động làm rõ bất định và báo rủi ro.
- Kết quả và đóng góp có thể kiểm chứng trong bối cảnh vai trò.
- Hướng phát triển nghề nghiệp, đào tạo và hỗ trợ cần thiết.

Cách đánh giá nên dựa trên **nhiều nguồn bằng chứng, mô tả cụ thể và đối thoại**, có cơ chế kiểm tra thiên lệch. Không biến một dashboard cấp nhóm thành công cụ tự động quyết thù lao từng người.

### 9.3. Mẫu rubric định tính có bối cảnh

| Năng lực/đóng góp | Bằng chứng hữu ích | Điều phải tránh |
| --- | --- | --- |
| **Chuyên môn** | Thiết kế an toàn, test, code review, xử lý sự cố phù hợp | Chỉ đếm số commit/PR |
| **Cộng tác** | Pairing, hỗ trợ gỡ blocker, chia sẻ hiểu biết | Đếm số tin nhắn/họp |
| **Kết quả** | Phần trách nhiệm với Increment và mục tiêu nhóm | Gán toàn bộ outcome cho một người |
| **Học hỏi** | Thử nghiệm có căn cứ, cải thiện kỹ năng, phản hồi | Thưởng cho số “khóa học đã xem” |
| **Chất lượng** | Bảo vệ DoD, phát hiện lỗi rủi ro cao, khắc phục | Dùng bug count cá nhân không xét ownership |
| **Trách nhiệm** | Minh bạch tiến độ/rủi ro, phối hợp điều chỉnh | Trừng phạt người nêu blocker sớm |
| **Tính bền vững** | Hợp tác có kế hoạch, hỗ trợ on-call theo quy tắc | Tôn vinh làm thêm giờ làm chuẩn thành tích |

Đây không phải biểu mẫu thang lương bắt buộc. **Đánh giá nhân sự có hệ quả thật phải phù hợp luật lao động và chính sách**, có quy trình phản hồi/chỉnh sai, bảo vệ thông tin cá nhân và tránh phân biệt đối xử.

### 9.4. Phản hồi 360 độ hoặc peer feedback: dùng cẩn thận

Nhận xét đồng nghiệp có thể giúp thấy đóng góp vô hình như mentoring và việc gỡ phụ thuộc. Nhưng:
- Dễ bị thiên lệch quan hệ, độ gần gũi hoặc mức độ hiển thị.
- Không nên mặc định “nhiều người vote” là công bằng.
- Cần mô tả hành vi và dẫn chứng, không chỉ đánh giá tính cách.
- Bảo vệ sự an toàn tâm lý và dữ liệu nhạy cảm.
- Có người chịu trách nhiệm tổng hợp và giải quyết khác biệt.

Mục tiêu là **phản hồi có thể cải thiện**, không biến teamwork thành cuộc thi được yêu thích.

### 9.5. Một thí nghiệm thất bại có thể tạo giá trị

Giả sử nhóm thử một giao diện trạng thái mới nhưng người dùng không hiểu rõ hơn. Nếu nhóm:
- Có giả thuyết hợp lệ.
- Thiết kế đo lường an toàn.
- Phát hiện kết quả sớm.
- Từ chối mở rộng tính năng không hữu ích.
- Chia sẻ bằng chứng và điều chỉnh backlog.

thì thử nghiệm có thể là **một kết quả học tập tốt**, dù outcome không đạt kỳ vọng ban đầu. Không nên thưởng cho việc “mọi thử nghiệm đều thành công”; như vậy tổ chức sẽ che kết quả bất lợi.

## 10. Thiết kế hệ thống đo hiệu quả đa chiều

### 10.1. Chọn ít tín hiệu có câu hỏi rõ

Một dashboard ví dụ:

| Mục tiêu | Tín hiệu | Nhịp xem | Quyết định hỗ trợ |
| --- | --- | --- | --- |
| Học viên hiểu trạng thái | Tỷ lệ hiểu đúng trong phép đo phù hợp | Theo đợt release/Review | Giữ hay đổi trải nghiệm |
| Giao Increment thường xuyên | Throughput cấp sản phẩm | Theo tuần/Sprint | Có quá nhiều việc bắt đầu? |
| Giảm thời gian chờ | Cycle time p85, WIP, aging WIP | Theo tuần và lịch sử đủ mẫu | Review/Verify đang nghẽn ở đâu? |
| Bảo vệ đúng nghiệp vụ | Vi phạm xác nhận vượt sức chứa | Liên tục với cảnh báo | Dừng xử lý, khôi phục, cải tiến |
| Duy trì năng lực | CI reliability, rework, incidents | Theo release/tháng | Cần đầu tư test hoặc nền tảng? |
| Học từ giả thuyết | Quyết định backlog thay từ bằng chứng | Theo Review/quý | Có đang đầu tư sai hướng? |
| Giảm gián đoạn | Tỷ lệ nhu cầu khẩn và số lần đổi ưu tiên | Theo Sprint/tháng | Capacity policy có phù hợp? |

Không cần biến mỗi hàng thành một mục tiêu thưởng. Một dashboard phải hỗ trợ **thảo luận và điều chỉnh**, không tạo xung đột chỉ tiêu.

### 10.2. Ví dụ tính tỉ lệ lỗi có mẫu số

Một đợt triển khai giả định:
- Nhánh giao diện cũ: 9.000 request, 45 lỗi không mong muốn.
- Nhánh mới: 1.000 request, 15 lỗi không mong muốn.

~~~text
Error rate cũ = 45/9000 = 0,5%
Error rate mới = 15/1000 = 1,5%
~~~

Nhánh mới có tỷ lệ lỗi cao hơn trong quan sát này, cần điều tra loại lỗi và khác biệt cohort trước khi mở rộng. Không kết luận nhánh mới **chắc chắn gây ra** mọi khác biệt nếu chưa kiểm soát bối cảnh. **Số lỗi tuyệt đối 15 < 45 không có nghĩa nhánh mới tốt hơn**.

Đây là ví dụ chất lượng gắn với kết quả, không phải KPI hiệu suất người viết UI.

### 10.3. Nếu một mục tiêu được thưởng quá mạnh

Giả sử cuối quý quản lý thưởng theo số story points cá nhân. Hành vi có thể đổi:
- Các item bị ước lượng cao hơn.
- Ít người hỗ trợ một task khó vì không ghi điểm.
- Việc test/review ít người muốn nhận.
- Task được chia nhỏ vì mục tiêu đếm.
- Nhóm ngại khám phá vấn đề vì thí nghiệm chưa chắc đạt điểm.

Không thể kết luận chắc những hành vi ấy xảy ra ở mọi nơi, nhưng chúng là **rủi ro khuyến khích sai** cần đánh giá. Một metric có ích cho forecast có thể mất ích lợi khi trở thành mục tiêu quyền lợi cá nhân.

### 10.4. Đánh giá một thay đổi phải công bố điều chưa biết

Bảng trước/sau có thể đẹp hơn vì:
- Item kỳ sau nhỏ và ít rủi ro hơn.
- DoD thay đổi.
- Người dùng ít hơn.
- Release cadence khác.
- Một dự án lớn đã kết thúc.
- Lỗi đo hoặc ticket được đóng hàng loạt.

Không tuyên bố “chuyển đổi thành công” từ hai biểu đồ ngắn. **Chọn thước đo và điều kiện so sánh trước khi thử**, rồi ghi biến gây nhiễu.

## 11. Thưởng, ghi nhận và động lực cộng tác

### 11.1. Đừng thưởng cho hành vi xung đột với mục tiêu

| Cơ chế thưởng/ghi nhận có rủi ro | Hành vi vô tình có thể khuyến khích | Tín hiệu cần bổ sung hoặc đổi cách nhìn |
| --- | --- | --- |
| Chỉ theo số ticket cá nhân | Chọn ticket nhỏ, tránh hỗ trợ | Đóng góp với Increment, chất lượng, hợp tác |
| Chỉ theo velocity của nhóm | Phóng đại ước lượng, tăng output danh nghĩa | Outcome/quality và bối cảnh forecast |
| Thưởng ai “bận 100%” | WIP cao, không có buffer cho sự cố | Khả năng hoàn tất và năng lực ứng phó |
| Chỉ theo ngày giao cam kết cứng | Giấu rủi ro, hạ DoD | Minh bạch forecast và chất lượng |
| Tôn vinh người cứu production mỗi đêm | Dựa vào anh hùng, không phòng ngừa | Reliability, runbook, giảm sự cố lặp lại |
| Chỉ theo doanh thu ngắn hạn | Hoãn bảo mật, kiểm thử và nền tảng | Guardrails dài hạn, chi phí vận hành |
| Chỉ theo tỷ lệ sử dụng nhân lực | Mọi người bị phân vào nhiều dự án | Capacity có dự phòng, flow cấp sản phẩm |

### 11.2. Ghi nhận cả những đóng góp khó đếm

Một đóng góp có giá trị có thể là:
- Dừng một quyết định khiến lộ dữ liệu.
- Xây contract tests giúp hai team tích hợp độc lập.
- Chia sẻ chuyên môn để giảm phụ thuộc vào một người.
- Refactoring làm giảm lỗi ở nhiều release.
- Đưa một giả định sai ra ánh sáng trước khi đầu tư lớn.
- Hỗ trợ Product Owner làm rõ một PBI mơ hồ.
- Giúp một story chung đạt Done thay vì đóng ba task riêng.

Việc ghi nhận cần có **ví dụ cụ thể** và không biến thành danh sách hoạt động làm màu.

### 11.3. Tránh hứa hẹn sửa chính sách nhân sự bằng một con số

Thù lao, thưởng, đánh giá năng lực và xử lý hiệu suất là những quyết định có ảnh hưởng lâu dài tới con người. Một chuyển đổi Agile nên:
- Có HR và lãnh đạo có thẩm quyền tham gia.
- Tách **flow metrics cấp hệ thống** khỏi quyết định cá nhân.
- Minh bạch tiêu chí và quyền được phản hồi.
- Kiểm tra rủi ro thiên lệch, điều kiện làm việc khác nhau và đóng góp ít hiển thị.
- Tôn trọng nghĩa vụ pháp lý, hợp đồng và dữ liệu cá nhân.
- Xem lại cơ chế nếu tạo hành vi che giấu blocker hoặc chạy theo metric.

**Agile không có nghĩa bỏ trách nhiệm hoặc thay mọi chính sách bằng “thưởng cả team bằng nhau”.** Mô hình ghi nhận cần hợp mục tiêu, công bằng và khả thi với bối cảnh tổ chức.

## 12. Phân bổ nguồn lực: từ “cấp người theo task” sang tài trợ năng lực tạo giá trị

### 12.1. Ba mô hình thường gặp

| Mô hình | Cách vận hành | Điểm mạnh có thể có | Rủi ro cần quản lý |
| --- | --- | --- | --- |
| **Phân người theo từng dự án ngắn hạn** | Mỗi dự án xin một phần thời gian của nhiều nhân sự | Linh hoạt với việc ngắn, nguồn lực hiếm | Chuyển ngữ cảnh, đổi team, ownership yếu, hàng chờ |
| **Tài trợ nhóm sản phẩm tương đối ổn định** | Nhóm giữ năng lực theo Product Goal/value stream qua nhiều đợt | Kiến thức domain, CI, trách nhiệm end-to-end, feedback nhanh | Cần portfolio governance và điều chỉnh đầu tư theo bằng chứng |
| **Shared services/platform hoặc chuyên môn dùng chung** | Một capability phục vụ nhiều team bằng hợp đồng/chính sách | Tránh lặp kỹ năng hiếm, tạo self-service | Nếu mọi task phải qua ticket queue thì thành nút thắt |

Không nên chọn một kiểu cho toàn bộ doanh nghiệp. Một sản phẩm có nhu cầu dài hạn thường hưởng lợi từ **đội hình ổn định**; một migration có thời hạn có thể cần lực lượng tạm; một dịch vụ bảo mật dùng chung có thể hợp lý nếu hỗ trợ chủ động và không làm cổng duyệt tất cả việc.

### 12.2. “Resource” ở đây không chỉ là người

Khả năng tạo giá trị phụ thuộc vào:
- **Nhân sự và kỹ năng:** phân tích nghiệp vụ, lập trình, kiểm thử, thiết kế, vận hành.
- **Thời gian và sự tập trung:** ít chuyển giữa nhiều backlog.
- **Hạ tầng:** CI, môi trường tích hợp, dữ liệu thử, observability.
- **Quyền quyết định:** không cần chờ ba cấp cho thay đổi rủi ro thấp.
- **Ngân sách vận hành:** cloud, nhà cung cấp, support, security.
- **Kiến thức sản phẩm:** hiểu người dùng, hợp đồng, lỗi lịch sử, kiến trúc.
- **Khả năng giảm rủi ro:** backup, on-call, rollback, test và bảo mật.

Thêm Developers mà môi trường test vẫn chỉ phục vụ một nhóm vào thứ Sáu có thể không tăng throughput cấp sản phẩm.

### 12.3. Tài trợ năng lực ổn định không đồng nghĩa cấp ngân sách vô hạn

Một cách tiếp cận là:
1. Lãnh đạo portfolio xác định **mục tiêu đầu tư và guardrails**.
2. Nhóm sản phẩm có năng lực tương đối ổn định để theo đuổi Product Goal.
3. Product Owner điều chỉnh backlog theo giá trị và phản hồi.
4. Nhóm chọn cách triển khai, giữ chất lượng và quản lý WIP.
5. Portfolio kiểm tra bằng chứng ở mốc phù hợp để **tiếp tục, tăng/giảm hoặc chuyển hướng đầu tư**.
6. Với thay đổi đầu tư lớn, xem chi phí chuyển đổi và nghĩa vụ đối với người lao động.

Điểm khác với mô hình xin người cho từng task là **đầu tư gắn với năng lực và mục tiêu**, thay vì chỉ gắn với một kế hoạch cố định hàng trăm task. Tuy nhiên, finance vẫn có thể yêu cầu dự toán, báo cáo chi phí, phân loại chi phí vốn/chi phí vận hành hoặc hồ sơ dự án theo quy định.

### 12.4. Nhóm ổn định giúp giảm chi phí chuyển ngữ cảnh

Giả sử một Developers làm 50% thời gian cho sản phẩm A, 30% cho B, 20% cho C. Đây là **phân bổ kế hoạch**, không bảo đảm ba dòng công việc nhận được các tỷ lệ năng lực tương đương, vì còn:
- Họp và công cụ khác nhau.
- Khác domain và thiết kế.
- Bị ngắt bởi yêu cầu khẩn.
- Chờ khi người có phụ thuộc đang ở dự án khác.
- Relearning sau mỗi lần quay lại.

Không thể khẳng định “chuyển ngữ cảnh mất đúng 20%” nếu chưa đo. Nhưng đó là rủi ro cần quan sát qua **blocked time, lead time, số lần đổi ưu tiên và phản hồi từ team**.

### 12.5. Chuyển người giữa nhóm phải xét chi phí chuyển đổi

Có trường hợp chuyển người hợp lý:
- Một Product Goal đã hoàn thành hoặc không còn có giá trị.
- Nhu cầu đã thay đổi rõ ràng.
- Một nhóm liên tục thiếu năng lực mà không thể điều chỉnh workflow khác.
- Cần đáp ứng nghĩa vụ an toàn hoặc sự cố dài hạn.
- Phát triển nghề nghiệp của thành viên được thương lượng phù hợp.

Trước khi chuyển:
- Có phạm vi và người chịu trách nhiệm bàn giao kiến thức không?
- Ai tiếp tục sở hữu sự cố cũ?
- Bao lâu thành viên mới có thể đóng góp an toàn?
- Những item đang mở phải xử lý thế nào?
- Là chuyển tạm thời hay dài hạn?
- Việc thay đổi có làm phá sự ổn định của nhiều team khác không?

Một chính sách tốt thường **điều chỉnh thứ tự công việc trước khi điều chuyển con người liên tục**, trừ khi có lý do đủ mạnh.

## 13. Capacity planning: từ công suất lý thuyết đến kế hoạch có khả năng thực hiện

### 13.1. Capacity là ràng buộc để thương lượng, không phải lời hứa sản lượng

Ví dụ một nhóm gồm **8 người** có thể tham gia công việc kỹ thuật trong kỳ 4 tuần, mỗi người có **20 ngày làm việc lý thuyết**. Tổng danh nghĩa:

~~~text
8 người × 20 ngày = 160 person-days danh nghĩa
~~~

Nhưng trong kỳ giả định:
- Nghỉ phép và các ngày vắng đã biết: **16 person-days**.
- Hỗ trợ production/on-call, lỗi phát sinh được dự tính: **24 person-days**.
- Hoạt động năng lực dùng chung hoặc đào tạo đã lên kế hoạch: **8 person-days**.

Công sức còn lại để **lập kế hoạch cho các hạng mục khác** theo giả định:

~~~text
160 − 16 − 24 − 8 = 112 person-days
~~~

**112 person-days không đồng nghĩa 112 story points, 112 ngày lịch hay cam kết chắc chắn xong một lượng PBI cụ thể.** Đây chỉ là ước lượng năng lực thời gian sau các khoản được dự kiến. Kỹ năng, phụ thuộc, rủi ro, kích thước item và sự biến động vẫn cần forecast từ dữ liệu thực.

### 13.2. Khi incident vượt dự tính

Nếu thực tế production support cần **40 person-days** thay vì 24, phần còn lại theo cùng mô hình trở thành:

~~~text
160 − 16 − 40 − 8 = 96 person-days
Chênh so với kế hoạch ban đầu = 96 − 112 = −16 person-days
~~~

Đội không được yêu cầu “vẫn giao toàn bộ 112 person-days planned work” như thể 16 person-days đã biến mất có thể bù bằng khẩu hiệu Agile. Cần:
1. Bảo vệ khôi phục dịch vụ, an toàn dữ liệu.
2. Product Owner và Developers/nhóm liên quan đánh giá tác động tới Sprint Goal hoặc mục tiêu kỳ.
3. Điều chỉnh phạm vi, thứ tự và forecast, nêu trade-off.
4. Ghi nguyên nhân sự cố để đầu tư phòng ngừa.
5. Xem lại tỷ lệ buffer và cách phân bổ support theo lịch sử.

### 13.3. Phân bổ tỷ lệ chỉ là điểm xuất phát

Một đề xuất minh họa đối với **112 person-days kế hoạch** còn lại có thể là:
- 70% cho lát cắt tính năng theo Product Goal.
- 20% cho độ tin cậy, kỹ thuật nền tảng và giảm rủi ro.
- 10% cho khám phá/kiểm chứng giả thuyết sản phẩm.

Tính ra:
- Tính năng: **112 × 0,70 = 78,4 person-days**.
- Nền tảng/chất lượng: **112 × 0,20 = 22,4 person-days**.
- Khám phá: **112 × 0,10 = 11,2 person-days**.

Các số thập phân là **phép tính kế hoạch**, không phải chỉ dẫn chia người thành 0,4 ngày trong mọi thực tế. Cần chọn đơn vị phân bổ tiện dụng, cân bằng rủi ro và tránh gán cứng thời gian vào mục tiêu không còn giá trị. **Không có tỷ lệ 70–20–10 bắt buộc của Agile.**

### 13.4. Dự báo delivery nên dựa trên luồng thực tế

Capacity giúp biết **không thể nhận vô hạn**, còn forecast ngày hoàn tất thường cần:
- Throughput lịch sử cùng loại item/DoW.
- Cycle time distribution và mức bất định.
- WIP/age của việc đang mở.
- Những phụ thuộc có thể nằm trên critical path.
- Các sự kiện khẩn, nghỉ phép và thay đổi team.
- Definition of Done và điều kiện release.

Một kỳ có 112 person-days kế hoạch không cho phép tự động suy “11 story × 10 person-days sẽ hoàn thành”, nhất là khi item có kích thước và phụ thuộc khác nhau.

### 13.5. Có cần tận dụng 100% công suất?

Một hệ thống không có khoảng trống cho incident, review, học hỏi và cải tiến có thể khiến hàng chờ tăng mạnh khi nhu cầu biến động. **Tối đa hóa tỷ lệ bận của từng người không đồng nghĩa tối đa hóa số Increment Done.**

Tuy vậy, buffer quá lớn và không có mục đích cũng có chi phí. Cần đặt dự phòng theo **độ biến động demand, mức rủi ro, SLE/commitments và thực tế**, sau đó đo và điều chỉnh.

## 14. Portfolio và ngân sách: chuyển từ giám sát task sang kiểm tra giả thuyết đầu tư

### 14.1. Phân biệt ba cấp quyết định

| Cấp | Câu hỏi | Người chịu trách nhiệm theo cấu trúc tổ chức |
| --- | --- | --- |
| **Portfolio/chiến lược** | Đầu tư bao nhiêu vào sản phẩm/dòng giá trị nào, vì sao? | Lãnh đạo có thẩm quyền, finance và product leadership |
| **Sản phẩm** | Product Goal và những PBI nào tạo giá trị tiếp theo? | Product Owner với stakeholders/Developers |
| **Thực hiện** | Tạo Increment Done bằng cách nào, trong capacity và guardrails nào? | Developers/nhóm có ownership và trách nhiệm kỹ thuật |

Người cấp ngân sách **không nhất thiết phải giao từng task**, người lập trình **không mặc định được tự quyết ngân sách tổ chức**, và Product Owner không bị yêu cầu làm “người duyệt các microtask kỹ thuật” chỉ vì chịu trách nhiệm giá trị.

### 14.2. Ví dụ phân bổ một danh mục có ràng buộc

Giả sử ngân sách năng lực sản phẩm ở kỳ tới được quy đổi thành **100 đơn vị đầu tư**, hoàn toàn giả định:

| Dòng đầu tư | Mục tiêu | Phân bổ ban đầu |
| --- | --- | ---: |
| **Đăng ký workshop** | Tăng tỷ lệ đăng ký đúng, giảm hiểu nhầm trạng thái | 45 |
| **Độ tin cậy & dữ liệu** | Bảo vệ bất biến sức chứa, giảm incident | 30 |
| **Khám phá nhu cầu mới** | Kiểm chứng tính năng cho nhà tổ chức | 15 |
| **Dự phòng rủi ro danh mục** | Nhu cầu bắt buộc phát sinh, phụ thuộc ngoài dự kiến | 10 |
| **Tổng** | | **100** |

Bảng này là **phân bổ tài trợ minh họa**, không phải chia 45% thời gian của mỗi Developers cho đăng ký workshop. Các dòng có thể được thực hiện bởi team/capability có ownership rõ, với cách ghi nhận chi phí phù hợp.

Sau một đợt thử:
- Khám phá không thấy nhu cầu: có thể **giảm hoặc dừng đầu tư**, lưu bằng chứng.
- Incident tăng ở cơ chế xác nhận: có thể **điều chỉnh đầu tư cho độ tin cậy**.
- Một tính năng có giá trị và khả năng giao tốt: có thể xem **mở rộng năng lực**, sau khi đánh giá chi phí chuyển đổi.
- Không thay đổi ngân sách hàng ngày theo một biểu đồ ngắn; cần nhịp review ổn định và quyền quyết rõ.

### 14.3. Cost of delay không phải một cách xếp hạng tự động

Cost of delay là **giá trị bị mất hoặc rủi ro tăng do kết quả đến muộn**. Ví dụ:
- Vá lỗi cho phép xác nhận vượt sức chứa: rủi ro cao có thể cần xử lý ngay.
- Ra mắt chức năng bán vé trước mùa workshop: có thể có cửa sổ thời gian.
- Đổi màu nút đăng ký: có thể ít cấp thiết hơn nếu không có bằng chứng giá trị.

Có thể cân nhắc **cost of delay, thời gian thực hiện, rủi ro giảm được và cơ hội học** trong portfolio. Các mô hình ưu tiên theo tỷ số (như Weighted Shortest Job First trong một số phương pháp quy mô lớn) chỉ hữu ích khi:
- Các ước lượng có định nghĩa đủ nhất quán.
- Các hạng mục so sánh trong bối cảnh tương thích.
- Không bỏ qua nghĩa vụ bắt buộc, chất lượng hoặc dữ liệu nhạy cảm.
- Người có thẩm quyền có thể xem cả định tính, chứ không chỉ điểm số.

**Đừng coi công thức ưu tiên là phép tính chân lý cho mọi quyết định đầu tư.**

### 14.4. Tài trợ theo value stream không loại bỏ kiểm soát tài chính

Tổ chức vẫn có thể cần:
- Ngân sách và phân quyền phê duyệt theo ngưỡng.
- Theo dõi chi phí theo sản phẩm hoặc chương trình.
- Kế toán, phân loại đầu tư, hợp đồng, vendor procurement.
- Hồ sơ phê duyệt bắt buộc.
- Các yêu cầu về bảo mật và tuân thủ.
- Dự toán và thực chi ở các mốc.

Điều chỉnh Agile nằm ở **nhịp đầu tư và quyền quyết phù hợp để học từ kết quả**, không phải từ bỏ accountability tài chính.

### 14.5. Khi nào nên dừng một khoản đầu tư?

Những tín hiệu hợp lý:
- Product Goal không còn liên quan với chiến lược hoặc nhu cầu khách hàng.
- Giả thuyết giá trị bị bác bỏ qua dữ liệu đủ phù hợp.
- Chi phí/rủi ro của cơ hội mới vượt lợi ích dự kiến.
- Một nhu cầu bắt buộc hoặc khẩn cấp có ưu tiên rõ.
- Năng lực hiện có có thể tạo giá trị lớn hơn ở hướng khác.

Nhưng quyết định dừng cần xem **nghĩa vụ với khách hàng, dữ liệu, các nhân sự liên quan, chi phí chuyển giao và vận hành hệ thống đang chạy**. Không bỏ một team đang duy trì production chỉ vì biểu đồ tính năng mới thấp.

## 15. Những nút thắt nguồn lực dùng chung

### 15.1. Shared specialists có thể thành hàng chờ

Một chuyên gia về dữ liệu được “phân bổ 20%” cho năm team không có nghĩa mỗi team nhận được đúng 20% năng lực đúng lúc. Khi cả năm cùng cần review schema vào cuối Sprint, chỉ một người có thể trở thành bottleneck.

Biểu hiện:
- Các PBI nằm ở trạng thái Review/Approval rất lâu.
- Một người được mời vào mọi cuộc họp.
- Những quyết định nhỏ chờ lịch của chuyên gia.
- Tổ chức cố tăng throughput bằng cách thêm Developers ở các team đang chờ.
- Chuyên gia phải làm ngoài giờ để giải quyết nhiều ưu tiên khẩn.

### 15.2. Các phương án thay thế

| Tình huống | Thay đổi có thể thử | Điều phải bảo vệ |
| --- | --- | --- |
| Nhiều câu hỏi schema lặp lại | Contract templates và integration tests | Tính đúng và compatibility |
| Chuyên gia chỉ có một mình | Pairing, mentoring, chuẩn tài liệu | Không ép chuyển giao vội làm tăng rủi ro |
| Môi trường kiểm thử dùng chung thiếu khả năng | Tự phục vụ, cô lập môi trường, đầu tư CI | An toàn dữ liệu và chi phí |
| Phê duyệt cho mọi thay đổi | Phân loại rủi ro, ủy quyền trường hợp thấp | Review độc lập khi cần |
| Cạnh tranh ưu tiên từ nhiều team | Một chính sách intake, WIP, service class | Không bỏ việc khẩn thật |
| Nhu cầu lâu dài vượt capacity | Tăng năng lực chuyên môn/nhóm platform | Ownership, onboarding và ROI hợp lý |

### 15.3. Không nhân bản mọi chuyên gia vào mọi team

Đặt một security expert, DBA, SRE và designer riêng trong từng nhóm có thể **không khả thi** và tạo thiếu nhất quán. Thiết kế tốt là cân bằng:
- **Khả năng nhóm tự làm phần phổ biến** qua chuẩn/test.
- **Hỗ trợ chuyên môn khi rủi ro thật cần**.
- **Trách nhiệm ownership rõ**.
- **Cơ chế vận hành tránh một người thành cổng duy nhất**.

Mục tiêu là giảm những phụ thuộc lặp lại bằng **năng lực và hợp đồng rõ**, không xóa vai trò chuyên môn.

## 16. Thay đổi governance: giữ kiểm soát cần thiết, bỏ bước duyệt không tạo giá trị

### 16.1. Phân loại quyết định theo mức độ ảnh hưởng

| Lựa chọn | Rủi ro và khả năng đảo ngược | Cơ chế minh họa |
| --- | --- | --- |
| Đổi text/nhãn được test đầy đủ | Thường thấp, dễ đảo ngược | Developers review/test, PO xác nhận ý nghĩa nếu cần |
| Thay endpoint/API có consumers khác | Phụ thuộc và compatibility | Contract tests, consultation, owner quyết |
| Migration dữ liệu có nguy cơ mất dữ liệu | Cao, khó đảo ngược | Test rehearsal, recovery plan, review chuyên trách |
| Đổi quyền truy cập thông tin cá nhân | Rủi ro bảo mật/tuân thủ | Review độc lập theo chính sách |
| Cấp ngân sách lớn hoặc tuyển dụng dài hạn | Tài chính/nhân sự dài hạn | Người có thẩm quyền phê duyệt |
| Sự cố đang gây hại | Khẩn cấp | On-call/incident authority và escalation |

Thay đổi governance không đồng nghĩa **xóa mọi approval**. Có thể chuyển từ duyệt tất cả sang **đánh giá theo rủi ro**, tự động hóa điều có thể kiểm tra và giữ quyền phê duyệt thật ở những quyết định quan trọng.

### 16.2. Tránh tạo bộ đôi quyền lực mơ hồ

Một anti-pattern là Product Owner quyết backlog theo giá trị, nhưng manager lại có thể thay trực tiếp thứ tự task mà không thông qua cơ chế minh bạch. Khi ấy hai hệ thống ưu tiên cạnh tranh.

Cần định nghĩa:
- Ai có quyền thay mục tiêu portfolio?
- Ai quản lý thứ tự backlog của một sản phẩm?
- Ai có thể khai báo incident hoặc rủi ro bắt buộc ưu tiên?
- Ai cùng điều chỉnh Sprint plan hoặc WIP policy?
- Quyết định nào cần review độc lập?
- Nơi ghi và công bố quyết định là đâu?
- Khi bất đồng không giải được, escalate theo đường nào?

### 16.3. Không lấy “tự chủ” làm lý do bỏ trách nhiệm

Autonomy cần:
- **Mục tiêu và ranh giới rõ**.
- **Thông tin cần thiết** để tự quyết.
- **Năng lực thực hiện** và hỗ trợ chuyên môn.
- **Quyền can thiệp** khi nguy cơ không chấp nhận.
- **Minh bạch tiến triển** và cơ chế hỏi đáp.
- **Các chuẩn bắt buộc** như DoD, bảo mật, phục hồi và pháp lý.

Một nhóm bị yêu cầu “tự chủ” nhưng không được quyền chọn test environment, không được điều chỉnh backlog và phải xin chữ ký cho mọi PR chỉ là **được trao trách nhiệm mà thiếu quyền thực hiện**.

## 17. Lộ trình điều chỉnh tăng dần thay vì “đổi tên sang Agile”

### 17.1. Nguyên tắc thực hiện

- Chọn **một vấn đề thật** liên quan Product Goal.
- Quan sát workflow và quyền quyết định đang xảy ra.
- Không đổi cùng lúc mọi chính sách nhân sự, ngân sách và framework; khó biết điều gì có ích.
- Có sự tham gia của Developers, Product Owner, lãnh đạo, HR và finance **đúng phạm vi**.
- Coi thay đổi chính sách nhân sự/tiền lương là quyết định có hậu quả, cần quy trình chính thức.
- Thử cơ chế **ít đảo ngược trước** và đo cả tác dụng phụ.
- Đảm bảo nhân viên có kênh phản hồi, đặc biệt khi chỉ tiêu cũ và mới đang xung đột.
- Không dùng “Agile” để ép giờ làm vô hạn hoặc đổ lỗi cho người phản hồi rủi ro.

### 17.2. Lộ trình sáu bước minh họa

| Bước | Câu hỏi | Hành động minh họa | Bằng chứng/đầu ra |
| --- | --- | --- | --- |
| **1. Baseline** | Vấn đề thực ở đâu? | Lấy mẫu PBI, WIP, blocked, đánh giá/ưu tiên hiện tại | Bản đồ dòng giá trị và các giả thuyết |
| **2. Căn chỉnh mục tiêu** | Giá trị và guardrails là gì? | Thống nhất Product Goal, DoD, owner, rủi ro bắt buộc | Mục tiêu đo được và quyền rõ |
| **3. Thử cơ chế giao việc** | Pull/WIP có giảm chờ không? | Một đội thí điểm, intake rõ, hạn WIP, giảm việc ngoài luồng | Item age, quality, phản hồi |
| **4. Đổi cách đọc kết quả** | Metric có khuyến khích đúng hành vi không? | Dashboard flow/quality/outcome, đối thoại về đóng góp | Quy tắc sử dụng số đo và phản hồi |
| **5. Thử cách phân bổ năng lực** | Đội hình ổn định tạo giá trị hơn không? | Bảo vệ một team qua vài chu kỳ, thử funding/portfolio cadence | Mức gián đoạn, throughput, chi phí, outcome |
| **6. Mở rộng/điều chỉnh** | Điều gì có thể áp dụng tiếp? | Ghi bài học, thay chính sách có thẩm quyền, giữ guardrails | Decision log, owner, review trigger |

Thời gian mỗi bước phải tùy **rủi ro, cỡ mẫu và năng lực thay đổi**. Không quy định tất cả tổ chức phải hoàn thành trong 30/60/90 ngày.

### 17.3. Phân biệt “thử trong một team” và “đổi thưởng toàn công ty”

**Có thể thí điểm** một chính sách WIP, kênh intake hoặc dashboard cấp team với đồng thuận và an toàn phù hợp. **Không nên tự ý thí điểm giảm/thay lương thưởng của một nhóm** khi chưa đủ thẩm quyền, cơ sở pháp lý, tham vấn và bảo đảm công bằng. Những thay đổi có hệ quả nhân sự cần chính sách và quy trình chính thức.

### 17.4. Khi thay đổi gây hại

Nếu một chính sách mới dẫn tới:
- Lỗi người dùng tăng nghiêm trọng.
- Nhân viên bị giao việc không có quyền quyết.
- Blocked work bị che để đạt KPI.
- Một nhóm bị kéo làm quá giờ liên tục.
- Portfolio không thể đáp ứng nghĩa vụ bắt buộc.

thì cần **pause hoặc đảo một phần chính sách** và tìm nguyên nhân. Một thử nghiệm Agile phải **có quyền điều chỉnh theo bằng chứng**, không biến kế hoạch chuyển đổi thành “deadline phải thay đổi bằng mọi giá”.

## 18. Tình huống xuyên suốt: nền tảng đăng ký workshop thay ba cơ chế

### 18.1. Bối cảnh trước chuyển đổi

Tổ chức có:
- **Team Enrollment:** đăng ký, sức chứa và transaction.
- **Team Experience:** giao diện, trạng thái và hỗ trợ hành trình người dùng.
- Một số chuyên gia kiểm thử và dữ liệu phục vụ hai nhóm.
- Product Owner được yêu cầu “chịu trách nhiệm giá trị” nhưng không thể thay thứ tự ưu tiên khi có chỉ đạo trực tiếp từ nhiều quản lý.
- Nhân viên nhận task từ cả Product Backlog lẫn các ticket cá nhân của bộ phận.
- Thưởng theo số task đóng và đúng hạn cá nhân.
- Một số thành viên bị phân 50% sang dự án khác trong cùng Sprint.

Product Goal là **học viên đăng ký đúng chỗ, biết trạng thái đáng tin, nhận phản hồi sớm và có thể tự phục vụ**.

### 18.2. Baseline giả định của một kỳ

| Tín hiệu cấp sản phẩm | Trước thử | Lưu ý |
| --- | ---: | --- |
| Throughput | 10 user stories Done/tháng | Cùng định nghĩa Done và loại item phù hợp |
| WIP trung bình | 18 item | Mốc Started/Finished rõ |
| Cycle time p85 | 14 ngày lịch | Cần mẫu lịch sử đủ phù hợp |
| Item đang mở có tuổi vượt ngưỡng theo dõi | 6 | Không đưa chúng vào cycle time của item đã Done |
| Median blocked time do chờ review/quyết định | 3 ngày làm việc | Chỉ những item có block tương ứng |
| Lỗi nghiêm trọng sau release | 2 | Cỡ mẫu nhỏ |
| Tỷ lệ học viên hiểu đúng trạng thái trong phép thử | 20/30 = 66,7% | Chỉ trong mẫu 30 người giả định |
| Thành viên đổi mục tiêu công việc giữa kỳ | 4 | Chưa biết ảnh hưởng nhân quả |

Tất cả giá trị đều **hoàn toàn giả định** để học. Không có dữ liệu đủ để kết luận việc phân người là nguyên nhân duy nhất khiến cycle time cao.

### 18.3. Ba chính sách thử trong phạm vi kiểm soát

**A. Cơ chế giao việc**

- Product Owner công bố một Product Backlog có thứ tự cho sản phẩm.
- Các yêu cầu sản phẩm khác đi vào intake; incident được xử lý qua đường khẩn riêng.
- Nhóm dùng chính sách kéo việc theo Ready/DoW và WIP.
- Item blocked vẫn ở WIP, có owner, lý do và mốc xem lại.
- Khi khẩn, PO/Developers minh bạch trade-off với Sprint Goal và forecast.

**B. Cơ chế đánh giá**

- Ngừng dùng số task cá nhân làm **kết luận về hiệu quả dòng công việc** trong phiên cải tiến nhóm.
- Dùng Product Goal outcome, chất lượng và flow để đánh giá tiến triển sản phẩm.
- Ghi nhận đóng góp hỗ trợ, test, review, chia sẻ kiến thức.
- HR/manager giữ quy trình phản hồi nghề nghiệp chính thức, đánh giá dựa bằng chứng nhiều chiều.
- Việc thay đổi chế độ thưởng/thù lao thực tế chỉ được thực hiện sau quy trình có thẩm quyền.

**C. Phân bổ nguồn lực**

- Thí điểm bảo vệ đội hình ổn định cho một luồng tính năng đăng ký trong một số chu kỳ.
- Hạn chế đổi người giữa nhiều backlog khi không có rủi ro bắt buộc.
- Dành capacity có căn cứ cho production support và test automation.
- Chuyên gia dữ liệu dùng pairing/contract tests để giảm yêu cầu review lặp.
- Portfolio kiểm tra kết quả ở mốc thống nhất, không đổi nhân sự mỗi khi một stakeholder có ý tưởng mới.

### 18.4. Một quyết định thực tế trong Sprint

Trong Sprint, nhóm đang làm story giao diện trạng thái. Production xuất hiện lỗi khiến một số học viên có nguy cơ nhận thông báo xác nhận sai. Đây là rủi ro quan trọng.

**Cơ chế cũ** có thể: manager giao bug trực tiếp cho một Developers và vẫn yêu cầu đóng toàn bộ task đúng hạn; những người khác không biết nguy cơ với Sprint Goal.

**Cơ chế điều chỉnh**:
1. Kích hoạt xử lý incident theo policy.
2. Developers có năng lực thích hợp ưu tiên bảo vệ dữ liệu và xác minh sự cố.
3. Product Owner cùng Developers đánh giá tác động tới Sprint Goal, phạm vi và forecast.
4. Cập nhật backlog và thông báo stakeholder có liên quan.
5. Sau khắc phục, tạo công việc kiểm thử/hệ thống cần thiết để ngăn lặp.
6. Trong đánh giá nhóm, xem **khả năng phục hồi và học hỏi**, không phạt người mất điểm task vì đã xử lý sự cố.

**Không đánh đổi an toàn để làm đẹp bảng thành tích.**

### 18.5. Dữ liệu sau thử: có tín hiệu nhưng chưa có bằng chứng nhân quả

Giả sử một kỳ đủ quan sát tiếp theo cho bảng giả định:

| Tín hiệu | Trước | Sau |
| --- | ---: | ---: |
| Throughput cấp sản phẩm | 10 | 12 item/tháng |
| WIP trung bình | 18 | 12 item |
| Cycle time p85 | 14 | 11 ngày lịch |
| Item đang già hơn ngưỡng theo dõi | 6 | 3 |
| Median blocked time | 3 | 1,5 ngày làm việc |
| Lỗi nghiêm trọng sau release | 2 | 1 |
| Người thử hiểu đúng trạng thái | 20/30 | 24/30 |

Những phép đọc:
- Throughput tăng **(12−10)/10 = 20%**.
- WIP trung bình giảm **6 item**.
- p85 cycle time giảm **3 ngày lịch**.
- Item đang già giảm **3** trong hai snapshot.
- Median blocked time giảm **1,5 ngày làm việc**.
- Tỷ lệ hiểu đúng trong mẫu từ **66,7% lên 80%**.

**Không được tự kết luận ba chính sách mới gây ra toàn bộ cải thiện**: kỳ sau có thể có ít incident, story nhỏ hơn, thay công cụ CI, có nhiều người dùng hơn hoặc DoD khác. Mẫu khảo sát nhỏ, không chứng minh hiệu quả cho tất cả học viên. Phải xem lịch sử, loại item, tiêu chí đo, guardrails và phản hồi.

### 18.6. Nếu đầu ra tăng mà chất lượng xấu đi?

Giả sử throughput tăng từ 10 lên 15, nhưng sau release số lỗi nghiêm trọng tăng từ 2 lên 7 và nhân viên phải làm đêm nhiều hơn. Không nên vội tuyên bố “chuyển đổi hiệu quả 50%”. Cần:
- Xác minh cách đếm lỗi và lưu lượng.
- Điều tra phần test/DoD hoặc phụ thuộc bị cắt.
- Dừng mở rộng chính sách gây hại.
- Phục hồi chất lượng và nhịp làm việc.
- Xem lại các chỉ tiêu có khuyến khích đóng ticket bằng mọi giá không.

### 18.7. Quyết định tiếp theo có điều kiện

Một kết luận có trách nhiệm:

> “Cơ chế kéo việc và bảo vệ đội hình cho thấy tín hiệu giảm WIP và thời gian chờ trong ví dụ. Chúng tôi sẽ giữ việc công bố một backlog chung, tiếp tục xem tuổi item và chất lượng; không dùng velocity cá nhân để xếp hạng. Các thay đổi nhân sự/thù lao sẽ thực hiện qua HR và cấp có thẩm quyền. Nếu dependency dữ liệu vẫn là nút thắt, chúng tôi sẽ đánh giá cách tăng capability platform hoặc tự động hóa trước khi tuyển thêm người. Mỗi quyết định có owner và mốc xem lại.”

Đó là **thích ứng trên bằng chứng**, không phải lời hứa chuyển đổi Agile tự động giải quyết mọi vấn đề.

## 19. Những sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao gây hại | Cách điều chỉnh |
| --- | --- | --- |
| Đổi tên team thành Scrum Team nhưng vẫn giao task trực tiếp | Trách nhiệm và quyền tự quản mâu thuẫn | Làm rõ Product Backlog, Sprint Goal và decision rights |
| Mỗi quản lý có một backlog riêng | Ưu tiên cạnh tranh, WIP tăng | Intake và thứ tự minh bạch theo sản phẩm |
| Push mọi item ngay khi có người | Item mở quá nhiều, hàng chờ dài | Pull theo capacity và WIP |
| Coi pull là ai thích làm gì cũng được | Mất định hướng giá trị | Chính sách Ready, priority, ownership |
| Bỏ kế hoạch vì “Agile linh hoạt” | Không thể forecast hoặc quản lý rủi ro | Kế hoạch thích ứng và guardrails |
| Giữ deadline cũ sau khi thêm incident | Ép quá giờ hoặc giảm chất lượng | Minh bạch trade-off, điều chỉnh scope/forecast |
| Thưởng story points cá nhân | Dễ gaming ước lượng và chia task | Không dùng points làm năng suất cá nhân |
| Thưởng chỉ theo số ticket đóng | Tránh việc khó, review và hỗ trợ | Xem đóng góp trong Increment/quality/collaboration |
| So velocity của các team | Điểm tương đối không tương thích | Dùng forecast nội bộ, xem flow và outcome có bối cảnh |
| Lấy throughput làm giá trị kinh doanh | Item không đồng giá trị | Đo tác động người dùng và DoD |
| Bỏ item blocked khỏi WIP | Che thời gian chờ | Giữ started, đo age và blocker |
| Chỉ đo cycle time của completed items | Bỏ qua item tồn đọng | Aging WIP và histogram cùng nhau |
| Dùng flow metric để phạt cá nhân | Khuyến khích che blocker | Đánh giá hệ thống; nhân sự dựa nhiều bằng chứng |
| Bỏ đánh giá con người vì tự quản | Thiếu phát triển nghề nghiệp và accountability | HR/manager phản hồi công bằng với bối cảnh |
| Chỉ thưởng người cứu sự cố đêm khuya | Khuyến khích hero culture | Ghi nhận phòng ngừa, automation và hồi phục bền vững |
| Cấp người 20% cho năm dự án | Chuyển ngữ cảnh và queue | Bảo vệ capacity ổn định, xét demand thật |
| Thêm Developers khi CI là bottleneck | Tăng WIP nhưng không tăng Done | Đầu tư platform/test trước |
| Ấn định mọi team dùng 70–20–10 | Bỏ qua rủi ro/demand | Điều chỉnh dựa dữ liệu và mục tiêu |
| Lập kế hoạch 100% cho feature | Không có chỗ cho sự cố và chất lượng | Buffer có căn cứ, cập nhật theo thực tế |
| Bỏ mọi review để nhanh | Vi phạm an toàn hoặc tuân thủ | Review theo mức rủi ro, tự động hóa phần có thể |
| Duyệt mọi việc nhỏ qua ba cấp | Decision latency tăng | Ủy quyền trong guardrails |
| Thay cơ cấu toàn công ty một lần | Khó biết nguyên nhân và đảo quyết định | Thí điểm có phạm vi, owner và mốc học |
| Chỉ thay dashboard, không thay quyền ra quyết định | Chỉ số đẹp nhưng việc vẫn chờ | Xem lại governance và ownership |
| Thay thưởng mà không có HR/pháp lý | Bất công, rủi ro hợp đồng | Quy trình có thẩm quyền, phản hồi và công bằng |
| Đổi đội hình liên tục theo ý tưởng mới | Mất kiến thức, onboarding lặp | Đầu tư theo sản phẩm và review cadence |
| Tuyên bố thành công từ một tháng tốt | Mẫu nhỏ, nhiều biến gây nhiễu | Quan sát nhiều kỳ và nêu giới hạn |
| Tối ưu tốc độ nhưng lỗi dữ liệu tăng | Giá trị người dùng bị phá | Quality guardrails và incident policy |
| Coi áp dụng Scrum/Kanban là đích cuối | Quên mục tiêu sản phẩm | Đo khả năng giao và phản hồi người dùng |
| Dùng “tự chủ” để bỏ trách nhiệm lãnh đạo | Đội thiếu quyền và hỗ trợ | Lãnh đạo cung cấp mục tiêu, nguồn lực, quyết định |
| Gắn đánh giá nhân sự với số giờ online | Giám sát vi mô, không đo kết quả | Đánh giá năng lực, đóng góp và hành vi có bằng chứng |

## 20. Bài thực hành có đáp án định hướng

### 20.1. Bài A – Phát hiện cơ chế mâu thuẫn (10 phút)

Một team có Product Backlog và Sprint Goal. Trong Sprint:
- Manager giao thêm ba task riêng cho từng Developers.
- HR thưởng theo ticket đóng.
- Mỗi thành viên bị phân 30% sang dự án khác.
- Product Owner không được thay ưu tiên khi có feedback học viên.

Hãy:
1. Chỉ ra ba mâu thuẫn với mục tiêu giao giá trị tăng dần.
2. Xác định điều nào thuộc quyền Product Owner, Developers, HR/lãnh đạo.
3. Chọn thay đổi ít đảo ngược nhất để thử.
4. Nêu guardrails và cách xem kết quả.

**Gợi ý đáp án:** Nhiều nguồn ưu tiên, WIP/chuyển ngữ cảnh và KPI task cá nhân đều có thể cản flow. Thử đầu mối intake, bảo vệ một Sprint Goal và thống nhất cách ghi công việc ngoài luồng. Không tự sửa tiền thưởng mà thiếu thẩm quyền.

### 20.2. Bài B – Lập chính sách pull (15 phút)

Một bảng có Ready = 12, Doing = 5, Review = 4, Verify = 2 và Done = 40. Giả sử Started khi vào Doing, Finished khi đạt Done.

1. Tính WIP hiện tại.
2. Nếu WIP limit của luồng là 9, có nên kéo thêm item từ Ready không?
3. Nếu xuất hiện lỗi dữ liệu nghiêm trọng, nhóm xử lý thế nào?
4. Việc blocked trong Review có còn là WIP không?
5. Hãy viết một câu hướng dẫn khi Review đang đầy.

**Đáp án:** WIP = **5 + 4 + 2 = 11**. Với limit 9, không tự kéo thêm thường lệ. Lỗi khẩn có đường xử lý/expedite được định nghĩa, minh bạch công việc bị ảnh hưởng và không bỏ an toàn. Item blocked trong Review vẫn là WIP. Ưu tiên hỗ trợ hoàn tất item gần Done.

### 20.3. Bài C – Giải thích KPI sai (15 phút)

Hai Developers:
- Người A đóng 12 ticket nhỏ.
- Người B đóng 4 ticket, đồng thời review lỗi phân quyền, giúp pairing và sửa CI khiến cả nhóm có thể release an toàn.

Hãy:
1. Giải thích vì sao không thể kết luận A giỏi hơn B chỉ từ 12 so với 4.
2. Đề xuất ba loại bằng chứng bổ sung.
3. Phân biệt đánh giá flow nhóm với đánh giá nghề nghiệp.
4. Nêu cách tránh thiên lệch và hành vi chơi số.

**Gợi ý:** Cần độ khó, quality, ownership, đóng góp hỗ trợ, bằng chứng kết quả và phản hồi nghề nghiệp phù hợp. Không đặt thưởng trực tiếp theo ticket count.

### 20.4. Bài D – Tính capacity hữu dụng (10 phút)

Nhóm có 8 người, mỗi người 20 ngày làm việc lý thuyết. Nghỉ 16 person-days, support dự tính 24, đào tạo/hoạt động dùng chung 8.

1. Capacity danh nghĩa?
2. Capacity còn lại cho kế hoạch?
3. Nếu support thực tế 40, còn bao nhiêu?
4. Có thể quy 112 person-days thành 112 story points không?
5. Khi capacity giảm, nên điều chỉnh gì?

**Đáp án:** Danh nghĩa **160**, còn lại **112 person-days**, khi support tăng thành 40 còn **96**, hụt **16 person-days**. Không đổi sang points hoặc cam kết story máy móc. Điều chỉnh thứ tự/phạm vi, forecast và xem xét phòng ngừa incident.

### 20.5. Bài E – Chia capacity theo mục tiêu (10 phút)

Dùng 112 person-days kế hoạch. Một phương án giả định chia 70% feature, 20% reliability, 10% discovery.

1. Tính person-days từng nhóm.
2. Vì sao không nhất thiết chia mỗi Developers cùng tỷ lệ?
3. Khi xảy ra sự cố nghiêm trọng, phần nào có thể thay đổi?
4. Khi nào nên xem lại tỷ lệ?

**Đáp án:** **78,4 / 22,4 / 11,2 person-days**. Đây là phân bổ kế hoạch, không phải bảo đảm output hay ràng buộc nhân sự cứng. Cần điều chỉnh theo demand, rủi ro và mục tiêu.

### 20.6. Bài F – Flow metrics và chất lượng (15 phút)

Trước thử nghiệm: throughput 10 item/tháng, WIP 18, cycle time p85 14 ngày, 2 lỗi nghiêm trọng. Sau: throughput 12, WIP 12, p85 11 ngày, 1 lỗi nghiêm trọng.

1. Tính phần thay đổi.
2. Có thể kết luận mọi cải thiện do chuyển sang pull không?
3. Dữ liệu nào về loại item và DoD cần kiểm?
4. Nếu lỗi nghiêm trọng tăng từ 2 lên 7 thì quyết định gì?
5. Outcome của học viên cần đo là gì?

**Đáp án:** Throughput **+20%**, WIP **−6**, p85 **−3 ngày**, lỗi nghiêm trọng trong kỳ **−1**. Không chứng minh nhân quả từ một bảng trước/sau. Nếu chất lượng suy giảm lớn, cần dừng/điều chỉnh và điều tra. Outcome có thể là tỷ lệ học viên hiểu đúng trạng thái, hoàn thành đăng ký đáng tin.

### 20.7. Bài G – Vai trò và quyền quyết (15 phút)

Cho bốn tình huống:
- Marketing muốn thêm màn hình khuyến mãi trong Sprint.
- Một incident có nguy cơ xác nhận vượt sức chứa.
- Developers muốn thay thư viện logging.
- Lãnh đạo muốn cắt ngân sách sản phẩm dài hạn.

Hãy nêu:
1. Ai cần quyết hoặc phối hợp cho mỗi trường hợp?
2. Công việc nào có thể đi theo Product Backlog?
3. Công việc nào phải kích hoạt đường khẩn?
4. Khi nào cần kiểm soát bảo mật/tuân thủ?
5. Thông tin phải được cập nhật ở đâu?

**Gợi ý:** PO chịu trách nhiệm thứ tự Product Backlog; Developers quản lý kế hoạch thực hiện và chất lượng; incident theo policy; ngân sách thuộc cấp có thẩm quyền. Không để marketing giao trực tiếp cho từng Developers như một backlog ngầm.

### 20.8. Bài H – Phân bổ người dùng chung (20 phút)

Một DBA phục vụ năm nhóm, mỗi nhóm được ghi trong bảng “20% DBA”. Mọi team đều cần duyệt migration cuối Sprint.

Viết đề xuất:
- Những hàng chờ và chi phí chuyển ngữ cảnh có thể xuất hiện.
- Cách nhìn blocked time và request age.
- Một chính sách intake/priority.
- Một phương án mentoring/contract tests.
- Điều kiện phải có DBA review độc lập.
- Khi nào đáng tăng headcount chuyên môn.

**Gợi ý:** Nhu cầu đồng thời không được giải bằng cách cộng 5 × 20% trên giấy. Cần capacity thật, hướng tự phục vụ, ngưỡng rủi ro và backup.

### 20.9. Bài I – Đánh giá phương án portfolio (20 phút)

Danh mục có 100 đơn vị đầu tư với 45 cho Enrollment, 30 cho Reliability, 15 cho Discovery, 10 cho dự phòng. Trong kỳ:
- Discovery không có bằng chứng nhu cầu đủ lớn.
- Enrollment có tín hiệu tích cực.
- Một lỗi dữ liệu nghiêm trọng xuất hiện.

Hãy:
1. Nêu điều cần ưu tiên xử lý ngay.
2. Đề xuất cách xem lại đầu tư mà không điều chuyển người liên tục.
3. Liệt kê quyền quyết và guardrails.
4. Không được suy luận điều gì từ một tuần dữ liệu?
5. Ghi một quyết định có mốc xem lại.

**Gợi ý:** Bảo vệ người dùng/dữ liệu trước; xem lại giả thuyết Discovery; cân nhắc năng lực dài hạn và nghĩa vụ vận hành; không chọn lại ngân sách theo một metric ngắn.

### 20.10. Bài J – Thiết kế thử nghiệm chuyển đổi (25 phút)

Một team muốn sửa cả ba cơ chế cùng lúc. Hãy viết kế hoạch gồm:
- Product Goal.
- Vấn đề và baseline.
- Chính sách giao việc sẽ thử.
- Tín hiệu đánh giá cấp nhóm và đóng góp nghề nghiệp không bị trộn.
- Capacity/đội hình sẽ giữ ổn định.
- HR, finance và các bên cần tham vấn.
- Rủi ro và điều kiện dừng.
- Mốc review và phương án mở rộng/đảo quyết định.

**Gợi ý:** ưu tiên các bước nhỏ, đo được; không tự thay chế độ thù lao; không hạ Definition of Done.

### 20.11. Bài K – Viết thông điệp cho lãnh đạo (15 phút)

Hãy viết một đoạn ngắn trình bày:
- Vì sao tổ chức đang có “Agile về nghi thức” nhưng cơ chế vẫn push?
- Những thay đổi nào giúp giảm hàng chờ mà không bỏ trách nhiệm?
- Dựa vào dữ liệu nào để xem hiệu quả?
- Vì sao thưởng theo velocity cá nhân có rủi ro?
- Khi nào stable-team funding là lựa chọn tốt?
- Điều kiện nào khiến phải điều chỉnh hoặc dừng thử?

**Tiêu chí:** không đổ lỗi cho cá nhân, có lợi ích/rủi ro, minh bạch giới hạn bằng chứng và bước hành động.

### 20.12. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Giao việc** | Mọi task do cấp trên đẩy vào | Có intake, pull, ưu tiên và WIP | Xử lý khẩn, blocker, Sprint Goal minh bạch |
| **Đánh giá** | Dùng story points/ticket cá nhân | Phân biệt outcome, flow, quality | Công bằng đóng góp, tránh gaming, bảo vệ nhân sự |
| **Nguồn lực** | Cấp người cho nhiều dự án cùng lúc | Có capacity và đội hình ổn định phù hợp | Portfolio theo bằng chứng và chi phí chuyển đổi |
| **Quyền quyết** | Mơ hồ hoặc quản lý quyết tất cả | Có Product Owner/Developers/HR/finance đúng phạm vi | Review theo rủi ro, ủy quyền và escalation |
| **Dữ liệu** | Chỉ xem số lượng output | Có WIP, age, cycle time, outcome, defects | Cỡ mẫu, biến gây nhiễu và guardrails rõ |
| **Chuyển đổi** | Đổi toàn bộ theo mệnh lệnh | Thử nhỏ với baseline và review | Dừng/chỉnh/mở rộng theo bằng chứng, bền vững |

## 21. Biểu mẫu sử dụng trong nhóm và tổ chức

### 21.1. Phiếu chẩn đoán cơ chế hiện tại

~~~text
Tên sản phẩm / Product Goal:
Dịch vụ và Definition of Workflow:
Nguồn yêu cầu và người sắp thứ tự:
Ai giao task/có thể đổi kế hoạch:
Quyền quyết về Sprint Goal/DoD:
Số backlog/kênh giao việc song song:
WIP, work item age và blocked reasons:
Throughput, cycle time distribution:
Các thước đo đang gắn quyền lợi cá nhân:
Những hành vi không mong muốn quan sát được:
Cách phân người và số lần đổi dự án:
Phụ thuộc chuyên gia dùng chung:
Đường duyệt chất lượng/rủi ro:
Outcome và quality guardrails:
Điều chưa biết và dữ liệu cần kiểm:
~~~

### 21.2. Working agreement về giao việc và ưu tiên

~~~text
Product Goal / Sprint Goal (nếu áp dụng):
Nguồn sự thật chung cho Product Backlog:
Ai xác định thứ tự ưu tiên:
Định nghĩa Ready/Started/Finished:
Điều kiện pull từ Ready:
WIP limits và cách điều chỉnh:
Blocked reason và cách hỗ trợ item đang già:
Kênh tiếp nhận demand thường:
Kênh incident/expedite, quyền kích hoạt:
Khi việc khẩn xuất hiện, điều gì được dừng/lùi:
Cách Product Owner và Developers cập nhật forecast:
Definition of Done và bảo vệ chất lượng:
Đối tượng cần thông báo:
Ngày xem lại chính sách:
~~~

### 21.3. Phiếu đánh giá kết quả sản phẩm

~~~text
Khoảng thời gian:
Product Goal / hypothesis:
Outcome người dùng và nguồn dữ liệu:
Output/Increment đã đạt DoD:
WIP, throughput, cycle time, aging WIP:
Quality: defects, data invariants, security:
Reliability, incident, recovery:
Những điều đã học và điều chỉnh backlog:
Sự khác biệt loại item/cách đo:
Những item chưa hoàn tất đang bị bỏ ngoài phân bố:
Các đóng góp hệ thống quan trọng (không xếp hạng cá nhân):
Rủi ro và giả định chưa xác minh:
Quyết định giữ/chỉnh/dừng:
~~~

### 21.4. Phiếu phản hồi phát triển năng lực cá nhân

~~~text
Vai trò và kỳ đánh giá theo chính sách:
Phạm vi công việc và điều kiện thực tế:
Ví dụ cụ thể về chuyên môn/chất lượng:
Ví dụ về cộng tác, mentoring và gỡ blocker:
Tình huống xử lý rủi ro/trách nhiệm:
Bằng chứng về học tập và phát triển:
Phản hồi của người liên quan có bối cảnh:
Điểm mạnh và nhu cầu hỗ trợ:
Cơ hội phát triển và mục tiêu tiếp theo:
Những hạn chế/thiên lệch cần kiểm:
Quy trình phản hồi và giải quyết khác biệt:
Quyền riêng tư, quyền truy cập và thời hạn lưu theo chính sách:
~~~

Mẫu này chỉ phục vụ **đối thoại và phát triển**, không tạo ra quy định thù lao hoặc nghĩa vụ pháp lý mới.

### 21.5. Phiếu phân bổ capacity

~~~text
Nhóm sản phẩm / value stream:
Kỳ kế hoạch:
Nhân sự và ngày làm việc danh nghĩa:
Nghỉ/vắng dự kiến:
Support/incident demand theo lịch sử:
Nghĩa vụ bảo mật, đào tạo và vận hành:
Capacity còn cho các mục tiêu khác:
Các mục tiêu và thứ tự ưu tiên:
Buffer và giả định nhu cầu phát sinh:
Shared specialist và các phụ thuộc:
WIP hiện tại và item đang già:
Forecast có bất định:
Người quyết trade-off khi demand đổi:
Ngày xem lại capacity:
~~~

### 21.6. Phiếu quyết định đầu tư portfolio

~~~text
Product Goal / value stream:
Chiến lược và outcome kỳ vọng:
Năng lực/chi phí hiện tại:
Lựa chọn: tiếp tục / tăng / giảm / chuyển hướng / dừng:
Bằng chứng outcome/flow/quality:
Cost of delay và rủi ro:
Chi phí chuyển người/onboarding/chuyển giao:
Nhu cầu năng lực dùng chung:
Guardrails pháp lý, bảo mật, tài chính và con người:
Người có thẩm quyền quyết:
Những người cần tham vấn:
Mốc áp dụng và công bố quyết định:
Điều kiện xem lại hoặc đảo quyết định:
~~~

### 21.7. Phiếu thử nghiệm chuyển đổi

~~~text
Experiment ID:
Vấn đề thật và Product Goal:
Cơ chế đang gây xung đột:
Giả thuyết:
Phạm vi nhóm/loại item:
Baseline và đơn vị đo:
Chính sách giao việc mới:
Cách đọc đánh giá mới:
Điều chỉnh nguồn lực trong phạm vi được duyệt:
Owner Product/Engineering/HR/Finance (khi liên quan):
Guardrails về DoD, dữ liệu, sự cố, sức bền đội:
Điều kiện dừng/đảo thử:
Thời gian và cách thu bằng chứng:
Biến gây nhiễu:
Ngày xem lại và quyền ra quyết định:
Kết quả và giới hạn:
Bước tiếp: giữ / chỉnh / dừng / mở rộng:
~~~

Những biểu mẫu không phải nghĩa vụ của Scrum, Kanban hay XP. Chỉ giữ phần thông tin **giúp người có trách nhiệm đưa ra quyết định có căn cứ**, tránh biến chuyển đổi thành một tầng giấy tờ.

## 22. Checklist: ba cơ chế đã hỗ trợ Agile chưa?

**Cơ chế giao việc**

- [ ] Product Goal và giá trị người dùng được mô tả rõ.
- [ ] Có nguồn ưu tiên/backlog minh bạch cho sản phẩm.
- [ ] Đã phân biệt quyền Product Owner, Developers, lãnh đạo và các bên kiểm soát.
- [ ] Nhóm có thể chọn và phối hợp cách thực hiện trong guardrails.
- [ ] Công việc được kéo theo điều kiện Ready/WIP, không đẩy vô hạn.
- [ ] Blocked items vẫn được ghi và ưu tiên hỗ trợ.
- [ ] Incident và expedite có chính sách, không tạo backlog ngầm.
- [ ] Khi nhu cầu khẩn tăng, phạm vi/forecast được thương lượng minh bạch.
- [ ] Definition of Done và chất lượng không bị hạ để tăng số ticket.

**Cơ chế đánh giá**

- [ ] Phân biệt outcome, output, flow, quality và learning.
- [ ] Velocity/story points không được dùng như chỉ số năng suất cá nhân.
- [ ] Throughput và cycle time được đọc theo định nghĩa và loại item.
- [ ] Work item age của item chưa Done không bị bỏ qua.
- [ ] Dashboard hỗ trợ cải tiến hệ thống, không phải xếp hạng người.
- [ ] Có cách ghi nhận test, review, mentoring và gỡ phụ thuộc.
- [ ] Các thay đổi thưởng/nhân sự đi qua quyền và quy trình hợp lệ.
- [ ] Đánh giá nghề nghiệp có nhiều nguồn bằng chứng và kênh phản hồi.
- [ ] Quyền riêng tư và nguy cơ thiên lệch trong đánh giá được xem xét.
- [ ] Kết quả thử nghiệm bất lợi được chia sẻ để học, không bị che giấu.

**Cơ chế phân bổ nguồn lực**

- [ ] Có cách nhìn capacity hữu dụng sau nghỉ, vận hành và công việc bắt buộc.
- [ ] Không lập kế hoạch 100% mọi người chỉ cho feature coding.
- [ ] Hạn chế chuyển người liên tục giữa nhiều backlog nếu không có lý do đủ mạnh.
- [ ] Nhóm sản phẩm có ownership và năng lực tương đối ổn định khi phù hợp.
- [ ] Năng lực platform/shared specialist có intake và service policy rõ.
- [ ] Có budget/portfolio review dựa trên Product Goal và bằng chứng.
- [ ] Chi phí onboarding, chuyển giao và vận hành được tính vào quyết định.
- [ ] Không coi person-days là story points hay cam kết kết quả.
- [ ] Đầu tư bảo mật, reliability và kỹ thuật nền tảng không bị bỏ mặc.
- [ ] Những nghĩa vụ tài chính/pháp lý và quyền lao động được bảo vệ.

**Chuyển đổi và điều hành**

- [ ] Đã có baseline trước khi thay chính sách.
- [ ] Có giả thuyết và phạm vi thử đủ rõ.
- [ ] Không đổi quá nhiều cơ chế cùng lúc đến mức mất khả năng học.
- [ ] Có guardrails chất lượng, dữ liệu, an toàn và sức làm việc bền vững.
- [ ] Nhóm được tham gia phản hồi thay đổi liên quan công việc của mình.
- [ ] Quyền ra quyết định/escalation được công bố.
- [ ] Có mốc xem lại, khả năng điều chỉnh hoặc đảo thử.
- [ ] Kết luận trước/sau ghi rõ cỡ mẫu, biến gây nhiễu và điều chưa biết.
- [ ] Mục tiêu cuối là **Increment có ích, khả năng thích ứng và giá trị người dùng**, không phải số nghi thức Agile đã thực hiện.

## 23. Tổng kết: thay cơ chế để thay hành vi, không chỉ thay nghi thức

**Giao việc, đánh giá và phân bổ nguồn lực là ba đòn bẩy liên kết.** Khi một Product Owner được yêu cầu tối đa hóa giá trị nhưng nhiều quản lý vẫn giao task trực tiếp; khi Developers được khuyến khích cộng tác nhưng thưởng theo ticket cá nhân; khi nhóm được yêu cầu giao Increment liên tục nhưng mỗi người bị chia qua nhiều dự án, tổ chức đang tạo **mâu thuẫn hệ thống**. Đổi tên cuộc họp hoặc bảng công việc không xử lý được mâu thuẫn ấy.

Hướng chuyển đổi có trách nhiệm là:

1. **Giao việc theo mục tiêu và khả năng hoàn tất:** backlog minh bạch, quyền quyết rõ, pull/WIP, xử lý khẩn có trade-off, bảo vệ DoD.
2. **Đánh giá theo nhiều chiều:** outcome, chất lượng, flow và học hỏi ở cấp sản phẩm; phản hồi nghề nghiệp có bằng chứng và công bằng, không thưởng cơ học theo velocity cá nhân.
3. **Phân bổ theo năng lực tạo giá trị:** đội hình ổn định khi phù hợp, capacity có dự phòng, capability dùng chung tự phục vụ, portfolio có quyền điều chỉnh đầu tư theo bằng chứng.
4. **Thử nghiệm và thích ứng:** bắt đầu từ vấn đề thật, theo dõi chỉ số đúng, giữ các guardrails, học từ kết quả, điều chỉnh chính sách thay vì buộc con người chịu chi phí của hệ thống không hợp lý.

Cơ chế mới chỉ tạo giá trị khi giúp nhóm **nhận phản hồi sớm hơn, giao những lát cắt sản phẩm đạt chất lượng thường xuyên hơn, giảm công việc chờ và duy trì năng lực lâu dài**. Đó là cách chuyển đổi Agile đi từ **nghi thức** tới **hệ thống làm việc thích ứng**.
