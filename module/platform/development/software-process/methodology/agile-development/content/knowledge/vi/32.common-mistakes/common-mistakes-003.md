# Sai lầm thường gặp: Thực hiện đủ nghi thức nhưng không có phản hồi và thích ứng

Một nhóm phát triển nền tảng đăng ký workshop tổ chức Sprint Planning đều đặn, Daily Scrum đủ 15 phút, Sprint Review có slide đẹp, Sprint Retrospective ghi nhiều ý kiến và một bảng Kanban đầy đủ cột. Tuy nhiên, sau ba Sprint, học viên vẫn hiểu nhầm nhãn “Đang chờ xác nhận” thành “Đã được giữ chỗ”. Support ghi nhận khiếu nại, các Developers đã nhìn thấy lỗi trong demo, nhưng Product Backlog không thay đổi, acceptance criteria không bổ sung và Sprint sau vẫn triển khai kế hoạch cũ. Trong Retrospective, nhóm tiếp tục ghi “cải thiện giao tiếp” như kỳ trước, không có người thực hiện hay bằng chứng kiểm tra.

Nhóm **có nghi thức Agile nhưng thiếu phản hồi dẫn tới thích ứng**. Các cuộc họp đã diễn ra; những quyết định tạo giá trị và hành động học hỏi thì chưa. Vấn đề không phải cuộc họp nào đó thiếu vui vẻ, cũng không thể giải bằng cách thêm một dashboard hay tổ chức nhiều workshop hơn. Cần khôi phục một vòng lặp có thể quan sát:

**Làm rõ mục tiêu → tạo Increment/kiểm tra cách làm → thu bằng chứng → hiểu chênh lệch → quyết định điều chỉnh → thực hiện thay đổi → đo lại.**

Bài này thuộc chương **Sai lầm thường gặp** của mô-đun **AGILE_DEVELOPMENT**. Mô-đun hướng tới các giá trị và nguyên tắc Agile: phát triển phần mềm thích ứng qua phản hồi sớm, bàn giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp. Chủ đề trực tiếp là **“Thực hiện đủ nghi thức nhưng không có phản hồi và thích ứng”**: cách nhận diện, phân tích nguyên nhân và sửa một hệ thống làm việc chỉ “diễn Agile” nhưng chưa thực sự **inspect and adapt**.

Ví dụ, số liệu, lịch thí nghiệm và nhãn trạng thái trong bài là **giả định để học**, không mô tả một doanh nghiệp thật. Scrum, Kanban, XP có nền tảng và quy tắc riêng; bài này phân biệt mục đích chính thức của chúng với những đề xuất thực hành có thể điều chỉnh theo bối cảnh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **thực hiện nghi thức**, **nhận phản hồi**, **kiểm tra dựa trên bằng chứng** và **thực sự thích ứng**.
2. Nhận diện dấu hiệu **cargo-cult Agile**: có lịch họp, vai trò, bảng công việc và báo cáo nhưng hành vi/quyết định không đổi.
3. Phân biệt **feedback về sản phẩm**, **feedback về chất lượng kỹ thuật** và **feedback về luồng/cách phối hợp**.
4. Giải thích cách các sự kiện Scrum hỗ trợ **transparency, inspection, adaptation** thay vì chỉ báo cáo tình trạng.
5. Viết một user story và acceptance criteria có thể kiểm chứng, rồi nối phản hồi người dùng tới thay đổi Product Backlog.
6. Nhận biết vòng lặp bị đứt ở đâu: không thu bằng chứng, không xử lý, thiếu quyền quyết, không thực thi hay không đo lại.
7. Chọn chỉ số **outcome, quality, flow và learning** phù hợp; tránh tối ưu velocity, số cuộc họp hoặc số action items.
8. Tạo một **thử nghiệm cải tiến nhỏ** từ Retrospective có giả thuyết, owner, mốc xem lại, guardrails và điều kiện dừng.
9. Kết hợp Kanban, WIP, cycle time, work item age, CI, TDD và XP để rút ngắn vòng phản hồi mà không hạ chất lượng.
10. Xử lý bất đồng, tín hiệu tiêu cực, dữ liệu ít và sự thay đổi ưu tiên một cách minh bạch.
11. Đọc một tình huống xuyên suốt về nền tảng đăng ký workshop và tính các kết quả cơ bản.
12. Sử dụng biểu mẫu và checklist để chuyển “chúng ta đã họp” thành “chúng ta đã học và thay đổi điều gì?”.

## 2. Nghi thức chỉ có ý nghĩa khi phục vụ kiểm tra và thích ứng

### 2.1. Nghi thức, tín hiệu và kết quả là ba thứ khác nhau

- **Nghi thức/hình thức:** một sự kiện diễn ra đúng lịch, có người dự, có báo cáo hoặc bảng biểu.
- **Phản hồi/tín hiệu:** thông tin có thể cho biết sản phẩm, giả định hay cách làm đang khác kỳ vọng.
- **Kiểm tra (inspection):** nhóm cùng xem tín hiệu trong bối cảnh, đối chiếu với mục tiêu và nhận diện điều cần điều tra.
- **Thích ứng (adaptation):** nhóm **đổi một quyết định hoặc cách làm** dựa trên điều học được và kiểm tra ảnh hưởng của thay đổi đó.
- **Kết quả:** người dùng nhận được giá trị, chất lượng được bảo vệ hoặc nhóm phối hợp tốt hơn.

Một Sprint Review có 40 người tham dự **không chứng minh** sản phẩm đáp ứng nhu cầu. Một Retrospective có 30 sticky notes **không chứng minh** quy trình đã cải thiện. Một biểu đồ burn-down đẹp **không chứng minh** phần mềm đạt Definition of Done.

### 2.2. Scrum dựa trên thực nghiệm, không chỉ dựa lịch sự kiện

Scrum Guide 2020 mô tả Scrum dựa trên **empiricism** và tư duy Lean; ba trụ cột của empirical process control là **transparency, inspection, adaptation**.

- **Transparency:** những người cần quyết định có thể thấy trạng thái thật, mục tiêu, chất lượng, trở ngại và kết quả.
- **Inspection:** thường xuyên kiểm tra các artifact và tiến triển hướng mục tiêu, nhưng không kiểm tra nhiều tới mức cản công việc.
- **Adaptation:** điều chỉnh quy trình hoặc sản phẩm **sớm nhất có thể** khi điều kiểm tra cho thấy kết quả lệch khỏi mong đợi hay có cách làm tốt hơn.

Nếu không có transparency, nhóm có thể tranh luận trên dữ liệu sai. Nếu không có inspection, tổ chức nhìn dashboard nhưng không học. Nếu không có adaptation, các buổi họp trở thành thủ tục.

### 2.3. Phân biệt cải tiến thực với hành động tượng trưng

| Hình thức nhìn thấy | Tín hiệu có ích | Thích ứng có thể kiểm tra |
| --- | --- | --- |
| Daily Scrum diễn ra đúng giờ | Ba story đang bị blocked bởi Review | Developers điều chỉnh kế hoạch và cùng hỗ trợ Review |
| Sprint Review có demo | Học viên nhầm PENDING với CONFIRMED | Product Owner cập nhật Product Backlog và AC, nhóm thử nhãn khác |
| Retrospective có ghi ý kiến | CI đỏ lặp lại, ảnh hưởng Sprint Goal | Có owner sửa pipeline và theo dõi lỗi/lưu lượng chạy test |
| Bảng Kanban có màu sắc | Review band liên tục dày lên | Nhóm thử WIP policy và đo age/cycle time |
| Báo cáo velocity đều đặn | Increment chưa Done vì thiếu integration | Đầu tư kiểm thử tích hợp sớm, không tăng points danh nghĩa |
| Có quy trình “lessons learned” | Cùng lỗi production lặp lại | Action phòng ngừa, test và cảnh báo được triển khai |

**Phản hồi có giá trị khi dẫn tới lựa chọn có trách nhiệm**, kể cả lựa chọn tạm thời **không đổi** vì dữ liệu chưa đủ, với điều kiện có lý do và mốc kiểm lại. Thích ứng không phải thay đổi lung tung sau mọi ý kiến.

## 3. Bản đồ một vòng phản hồi hoàn chỉnh

### 3.1. Từ giả thuyết đến thay đổi

~~~mermaid
flowchart TD
    A[Product Goal / vấn đề của người dùng] --> B[Giả thuyết và tiêu chí thành công]
    B --> C[User story / Increment nhỏ đạt DoD]
    C --> D[Demo, phát hành có kiểm soát, quan sát và đo lường]
    D --> E[Phản hồi: outcome, chất lượng, dòng công việc]
    E --> F{Có đủ bằng chứng để ra quyết định?}
    F -->|Chưa| G[Đặt câu hỏi, thu dữ liệu hoặc thử nhỏ hơn]
    G --> D
    F -->|Có| H{Cần thay đổi gì?}
    H -->|Sản phẩm| I[Cập nhật Product Backlog / mục tiêu / AC]
    H -->|Kỹ thuật| J[Thay test, thiết kế, CI, DoD hoặc release policy]
    H -->|Cách làm| K[Thay WIP, phối hợp, dependency hoặc working agreement]
    H -->|Giữ hiện trạng| L[Ghi lý do, điều kiện theo dõi]
    I --> M[Owner, hành động, mốc kiểm]
    J --> M
    K --> M
    L --> M
    M --> N[Thực thi và quan sát kết quả]
    N --> A
~~~

Sơ đồ là **mô hình học**, không bắt buộc mọi phản hồi phải đi qua toàn bộ các bước hoặc phải lập tài liệu lớn. Sự cố dữ liệu nghiêm trọng cần hành động ngay theo runbook; sau đó mới học và cập nhật hệ thống. Một câu hỏi nhỏ có thể được giải quyết trong vài phút nếu đúng người có quyền quyết và bằng chứng đủ rõ.

### 3.2. Sáu điểm mà vòng lặp thường bị đứt

| Điểm đứt | Biểu hiện | Câu hỏi chẩn đoán |
| --- | --- | --- |
| **1. Mục tiêu không rõ** | Họp đầy đủ nhưng không biết đang tối ưu điều gì | Product Goal, Sprint Goal hoặc kết quả mong muốn là gì? |
| **2. Không có Increment kiểm chứng** | Chỉ có slide, mockup, code nhánh chưa tích hợp | Điều gì đã đạt DoD và có thể đánh giá đáng tin? |
| **3. Phản hồi thiếu/đến muộn** | Không có người dùng, CI chậm, chỉ hỏi quản lý | Ai/cái gì có thể cung cấp bằng chứng sớm hơn? |
| **4. Phản hồi không được diễn giải** | Mọi ý kiến được ghi thành danh sách không phân biệt | Điều nào là quan sát, giả thuyết, mong muốn hoặc rủi ro? |
| **5. Không có quyền/owner quyết định** | “Ghi nhận ý kiến” nhưng không ai đổi backlog/chính sách | Ai có quyền chốt, ai thực hiện và đến lúc nào? |
| **6. Không đóng vòng kiểm tra** | Action tồn nhiều Sprint, không đo lại kết quả | Thay đổi đã triển khai chưa, tác động đo bằng gì? |

Thay vì thêm một cuộc họp mới, hãy tìm **điểm đứt sớm nhất** trong chuỗi. Nếu nhóm chưa có Increment kiểm thử được thì “thu thật nhiều survey” chưa chắc giải quyết. Nếu ý kiến người dùng đầy đủ nhưng mọi quyết định chờ hội đồng, vấn đề không nằm ở công cụ khảo sát.

### 3.3. Bản chất vòng phản hồi là quyết định thay đổi

Ví dụ ngắn:
- **Giả thuyết:** dùng nhãn “Đang chờ xác nhận” sẽ khiến học viên ít hiểu nhầm trạng thái hơn.
- **Thử:** tạo một lát cắt giao diện, có test quyền và nghiệp vụ, triển khai có kiểm soát.
- **Quan sát:** học viên vẫn cho rằng họ đã được giữ chỗ.
- **Kiểm tra:** phỏng vấn và xem hành vi trong ngữ cảnh; có thể do nhãn, vị trí hiển thị hoặc chính sách nghiệp vụ.
- **Thích ứng:** thêm giải thích “Chưa được giữ chỗ” và kiểm thử lại, không mặc định sửa chữ sẽ luôn giải quyết.
- **Đo lại:** xem tỷ lệ hiểu đúng, lỗi nghiệp vụ, support requests và tác dụng phụ.

Vòng lặp có thể kết thúc bằng **đổi phương án hoặc dừng phát triển một giả thuyết sai**. Đó vẫn là tiến triển nếu giúp tránh lãng phí và bảo vệ người dùng.

## 4. Dấu hiệu “Agile trên lịch, Waterfall trong quyết định”

### 4.1. Những triệu chứng có thể quan sát

- Sprint Planning chỉ đọc lại kế hoạch cố định nhiều tháng, không có cơ hội thương lượng trên capacity và bằng chứng mới.
- Daily Scrum thành buổi báo cáo từng người cho manager; blockers không được gỡ.
- Sprint Review biến thành trình chiếu thành tích hoặc cổng ký duyệt, không có tương tác thực chất với stakeholder.
- Sprint Retrospective lặp “cần giao tiếp tốt hơn” nhiều Sprint nhưng không có hành động.
- Product Backlog đầy ticket, không có Product Goal hoặc không được sắp thứ tự theo giá trị.
- Nhóm tăng story points để thể hiện tiến bộ, nhưng Increment chưa đạt DoD.
- Khách hàng phản hồi lỗi quan trọng nhưng Product Owner không thể điều chỉnh backlog.
- Công việc đã bắt đầu bị chặn, nhưng vẫn kéo thêm việc mới.
- Test chỉ được chạy cuối Sprint; lỗi phát hiện quá muộn để thích ứng.
- Mọi số liệu đều báo màu xanh, trong khi Support và người dùng kể câu chuyện khác.
- “Đã nhận phản hồi” được hiểu nhầm là “đã xử lý”.
- Một experiment có kết quả không như kỳ vọng bị xem là thất bại cá nhân nên không ai dám báo bằng chứng bất lợi.

### 4.2. Không phán xét chỉ từ số nghi thức

Một nhóm ít cuộc họp nhưng thường xuyên bàn giao Increment, kiểm tra feedback và điều chỉnh nhanh **có thể học hiệu quả**. Tuy vậy, nếu tự nhận **đang áp dụng Scrum**, nhóm cần tôn trọng mục đích, trách nhiệm và những sự kiện Scrum theo framework, không gọi một tập status messages rời rạc là Daily Scrum đầy đủ mà không có kiểm tra/thích ứng chung.

Ngược lại, đủ Scrum events **không bảo đảm** có empirical process control. Cần xem **đầu ra và thay đổi hành vi** của các sự kiện, không chỉ sự hiện diện.

### 4.3. Các câu hỏi “chạm vào thực tế”

Hãy chọn hai Sprint gần nhất và hỏi:
1. Phản hồi người dùng quan trọng nhất là gì?
2. Quyết định nào thay đổi vì phản hồi ấy?
3. Product Backlog đã đổi ra sao, vào ngày nào, bởi ai?
4. Thực hành kỹ thuật nào thay đổi vì CI, lỗi hoặc sự cố?
5. Một action Retrospective đã được làm chưa? Kết quả ra sao?
6. Một item đang già nhất bị chặn tại đâu và ai đang hỗ trợ?
7. Sprint Goal/DoD có thật sự hướng lựa chọn công việc không?
8. Những gì nhóm **quyết định không làm** sau khi học là gì?

Nếu nhóm chỉ trả lời được “chúng ta đã họp đầy đủ”, đó là tín hiệu để **điều tra vòng học**, không phải lời buộc tội mọi thành viên.

## 5. Sprint Planning: lập kế hoạch là một dự báo có khả năng điều chỉnh

### 5.1. Planning bị biến thành nghi thức giao task

Một Sprint Planning thất bại về mục đích khi:
- Manager đem danh sách task đã chia theo từng người và yêu cầu xác nhận.
- Developers không thể nêu khả năng thực hiện hay rủi ro.
- Sprint Goal chỉ là một câu nhãn sau khi đã chọn hết item.
- Nghỉ phép, support, bug và phụ thuộc bị bỏ khỏi capacity.
- Item quá lớn chưa rõ AC vẫn bị đưa vào để “đủ points”.
- Mỗi thay đổi nhỏ đều cần manager phê duyệt dù nhóm có bối cảnh.

Theo Scrum, Sprint Planning do **cả Scrum Team** cộng tác để xác định **Why, What, How**: tại sao Sprint có giá trị, có thể hoàn tất những gì, và cách Developers lên kế hoạch thực hiện. Sprint Goal là cam kết với Sprint Backlog, không phải bảng điểm task cá nhân.

### 5.2. Dấu hiệu inspection/adaptation đúng

Trong Planning, nhóm có thể nói:
- “Từ Sprint trước, item có nhiều phụ thuộc tích hợp thường không Done; Sprint này chọn lát cắt nhỏ hơn.”
- “Kỳ tới có lịch support nên không nên nhận cùng lượng work.”
- “Người dùng đang hiểu sai trạng thái; mục tiêu Sprint nên tập trung vào tín hiệu xác nhận đúng trước khi thêm animation.”
- “Chúng ta thiếu dữ liệu cho lựa chọn A/B, nên trước tiên cần một experiment nhỏ.”

Sau Planning, Developers có kế hoạch đủ rõ để bắt đầu; khi học được điều mới, họ có thể điều chỉnh Sprint Backlog. **Không âm thầm thay Sprint Goal bằng một danh sách ưu tiên khác**. Nếu phạm vi cần thương lượng, Product Owner và Developers trao đổi minh bạch với nhau.

### 5.3. Câu hỏi kiểm tra ngay cuối Planning

| Câu hỏi | Nếu chưa trả lời được |
| --- | --- |
| Sprint Goal tạo giá trị gì? | Làm rõ mục tiêu, tránh chỉ ghép ticket |
| Chúng ta dựa dữ liệu/giả định nào? | Ghi mức bất định và cần học gì |
| Item nào cần hợp đồng/AC bổ sung? | Refinement hoặc chọn lát cắt khác |
| Capacity và nguy cơ gián đoạn đã được tính? | Điều chỉnh phạm vi dự kiến |
| Điều kiện Done và cách chứng minh? | Làm rõ test, integration, yêu cầu an toàn |
| Khi xuất hiện thông tin mới, ai có thể điều chỉnh? | Phân quyền và kênh trao đổi minh bạch |

Planning tốt không phải **hứa chắc một lượng points** mà là tạo dự báo hợp lý, mục tiêu chung và khả năng thích ứng.

## 6. Daily Scrum: từ báo cáo cá nhân sang điều chỉnh kế hoạch

### 6.1. Dấu hiệu Daily Scrum “đủ nghi thức nhưng rỗng”

Một nhóm họp đều 15 phút, mỗi người kể hôm qua/hôm nay, nhưng:
- Không ai xem tiến triển đến Sprint Goal.
- Các items bị blocked vẫn đứng yên.
- Không ai đề xuất hỗ trợ review/test.
- Manager quyết định từng task thay vì Developers điều chỉnh kế hoạch.
- Mọi người chỉ muốn nói xong lượt để quay lại làm.
- Các phụ thuộc mới không được phản ánh vào Sprint Backlog.

Scrum Guide 2020 quy định Daily Scrum là sự kiện **15 phút dành cho Developers**, với mục đích kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog theo cần thiết. Developers có thể chọn cấu trúc/hình thức phù hợp; **không bắt buộc trả lời ba câu hỏi cố định**.

### 6.2. Một Daily Scrum có tác dụng

Giả sử bảng việc cuối ngày:
- Story A: gần Done nhưng chờ review.
- Story B: đang làm, chưa có integration test.
- Story C: được đề xuất bắt đầu mới.
- Sprint Goal: “Học viên xem trạng thái đăng ký đáng tin”.

Trong Daily Scrum, Developers có thể quyết:
1. Hai người cùng review A trước.
2. Một người hỗ trợ test B.
3. **Chưa kéo C** cho đến khi A/B tiến tới Done.
4. Nếu có rủi ro không đạt mục tiêu, làm rõ với Product Owner sau Daily Scrum.
5. Thống nhất ai thực hiện và cập nhật bảng để đồng nghiệp thấy.

Điều cần thay đổi là **kế hoạch và phối hợp**, không phải số người đã báo trạng thái.

### 6.3. Chi tiết kỹ thuật nên thảo luận đúng nơi

Nếu cần debug CI 40 phút, không phải kéo Daily Scrum thành cuộc họp dài. Developers có thể xác nhận vấn đề và nhóm người cần xử lý, sau đó tổ chức **huddle/pairing** ngay sau sự kiện. Tính ngắn của Daily Scrum giúp tập trung; tính hiệu quả đến từ **quyết định thích ứng**.

### 6.4. Khi nhóm phân tán múi giờ

Cập nhật async trước sự kiện có thể giúp mọi người thấy blockers, nhưng không biến một chuỗi cập nhật một chiều thành tương tác inspect/adapt chung theo mục đích Daily Scrum. Nếu lịch nhóm không cho phép phối hợp bền vững, cần xem lại cách tổ chức nhóm và các điều kiện làm việc, thay vì mặc định thành viên phải tham gia ngoài giờ mỗi ngày.

## 7. Sprint Review: không chỉ demo, mà là học và điều chỉnh Product Backlog

### 7.1. Sai lầm: Review = trình diễn slide để được khen

Một Sprint Review bị rỗng khi:
- Chỉ chiếu danh sách PBI “đã hoàn thành” dù nhiều item chưa đạt DoD.
- Stakeholders chủ yếu nghe báo cáo, không được cùng xem Increment.
- Không có câu hỏi về mục tiêu sản phẩm hoặc phản hồi thật.
- Ý kiến được ghi nhưng không có người quyết định thay đổi backlog.
- Review thành **cổng phê duyệt release** bắt buộc cho mọi Increment thay vì kiểm tra/thích ứng.
- Nhóm tránh demo tình huống lỗi vì sợ mất điểm.
- Người dùng thật không xuất hiện trong bất kỳ kênh phản hồi nào.

Sprint Review trong Scrum là **working session** để Scrum Team và stakeholders cùng kiểm tra outcome của Sprint và xác định thích ứng tiếp theo; **không nên bị giới hạn thành một bài thuyết trình**.

### 7.2. Đề xuất cấu trúc Review theo câu hỏi

1. **Nhắc Product Goal và bối cảnh đã đổi:** khách hàng, thị trường, rủi ro mới.
2. **Minh bạch Increment:** phần nào đạt DoD, phần nào chưa; không gắn nhãn “Done” cho tính năng chưa tích hợp.
3. **Cho người liên quan dùng hoặc xem tình huống thật:** màn hình trạng thái, dữ liệu, ràng buộc nghiệp vụ.
4. **Đặt câu hỏi kiểm chứng:** học viên hiểu gì? Có bằng chứng khác kỳ vọng không?
5. **Thảo luận lựa chọn:** giữ, đổi, thu hẹp, dừng hoặc thử thêm; cần dữ liệu nào?
6. **Product Owner cập nhật Product Backlog** phù hợp và ghi những quyết định chưa thể chốt.
7. **Theo dõi:** ai xác minh kết quả, mốc review hoặc feedback tiếp theo.

Điều này không bắt buộc Sprint Review phải diễn ra với đúng một agenda. **Mục đích là cùng inspect/adapt**, không tạo thêm một checklist cứng.

### 7.3. Ví dụ thực hành

Giả sử nhóm demo bản v2:
- API trả **PENDING** hoặc **CONFIRMED** chính xác.
- UI hiển thị “Đang chờ xác nhận” với PENDING.
- Trong buổi thử, một số người vẫn nói “vậy tôi chắc đã có chỗ”.

Phản hồi cần được chuyển thành:
- **Quan sát:** người dùng hiểu sai.
- **Giả thuyết:** thiếu lời giải thích “chưa được giữ chỗ” hoặc luồng quá giống bước xác nhận.
- **Lựa chọn:** thêm giải thích, thay vị trí hiển thị, thử nội dung khác.
- **Quyết định:** Product Owner ưu tiên một PBI cải thiện; Developers bổ sung AC và test.
- **Cách kiểm lại:** bài thử hiểu đúng trạng thái, support requests và lỗi xác nhận.

Nếu Review kết thúc bằng “cảm ơn ý kiến, Sprint sau làm theo kế hoạch cũ” mà không cân nhắc tác động, thì dù demo rất đẹp, **vòng phản hồi đã bị ngắt**.

### 7.4. Phản hồi stakeholder không phải mọi ý kiến đều thành PBI

Một stakeholder có thể yêu cầu đổi màu nút; người dùng khác gặp lỗi nghiêm trọng với sức chứa. Product Owner phải **đánh giá giá trị, rủi ro, mức tin cậy, chi phí và Product Goal**. Thích ứng không có nghĩa mọi yêu cầu được đưa vào Sprint ngay.

Đầu ra tốt của Review có thể là:
- Một PBI được ưu tiên lại.
- Một giả thuyết cần experiment thêm.
- Một rủi ro được đưa vào hàng xử lý đúng quy tắc.
- Một ý kiến được **từ chối có lý do**.
- Một Product Goal được điều chỉnh khi bối cảnh thay đổi đủ lớn.

**Ghi rõ lựa chọn và lý do** là điều giúp nhóm không xem việc thu phản hồi như hình thức.

## 8. Sprint Retrospective: không dừng ở “cải thiện giao tiếp”

### 8.1. Một danh sách ý kiến không phải kế hoạch cải tiến

Retrospective thường bị rỗng khi:
- Cùng một vấn đề được nhắc qua nhiều Sprint.
- Action viết chung chung (“làm tốt hơn”, “giao tiếp rõ hơn”).
- Có 20 actions nhưng không ai có capacity để làm.
- Không có owner, thời điểm kiểm tra hoặc điều kiện thành công.
- Nhóm chỉ bàn những vấn đề nhỏ vì không có quyền thay governance/WIP.
- Dữ liệu về lỗi, chờ và chất lượng không được đem vào.
- Không xem các actions từ kỳ trước.
- Có văn hóa đổ lỗi khiến không ai nêu vấn đề thật.

Mục đích Sprint Retrospective là **lên kế hoạch cải thiện chất lượng và tính hiệu quả**. Những cải tiến tác động lớn có thể được thực hiện sớm nhất có thể, kể cả được đưa vào Sprint Backlog kế tiếp khi phù hợp.

### 8.2. Chuyển lời phàn nàn thành giả thuyết có thể kiểm

Câu mơ hồ:

> “Review chậm, mọi người cố gắng phản hồi nhanh hơn.”

Câu có thể thử:

> “Trong ba Sprint gần đây, các story ở trạng thái Review có age tăng và năm item chờ reviewer trên hai ngày làm việc. Nếu hạn chế kéo thêm Doing khi Review đầy và tổ chức pairing 20 phút cho PR khó, số item chờ Review lâu sẽ giảm, trong khi Definition of Done và lỗi sau release không xấu đi.”

Phải nêu rõ **baseline thuộc hệ thống nào, có bao nhiêu item, đơn vị và cách đếm**, không dùng một ảnh chụp đơn lẻ như bằng chứng chắc chắn.

### 8.3. Mẫu một action có trách nhiệm

| Thuộc tính | Ví dụ |
| --- | --- |
| **Vấn đề** | PR chờ Review làm story không hoàn tất trước Sprint Goal |
| **Quan sát** | Review queue age cao ở các item có cùng kiểu phụ thuộc |
| **Giả thuyết** | Hỗ trợ review trước khi kéo việc mới sẽ giảm tồn chờ |
| **Can thiệp** | Thử WIP policy và huddle ngắn cho PR phức tạp |
| **Owner** | Developers thống nhất người theo dõi chính sách |
| **Thời hạn thử** | Một Sprint, sau đó xem thêm nếu mẫu nhỏ |
| **Dữ liệu** | Review wait, work item age, throughput và defects |
| **Guardrail** | Không bỏ test/DoD, không ép làm ngoài giờ |
| **Mốc review** | Retrospective kế tiếp và trong Sprint nếu có tín hiệu xấu |
| **Quyết định tiếp** | Giữ, chỉnh hoặc dừng theo bằng chứng |

**Không cần mọi action có nhiều trường như bảng này.** Nhưng ít nhất phải biết **ai làm gì và kiểm bằng cách nào**.

### 8.4. Đừng chờ Retro mới dám thích ứng

Scrum diễn ra trong các Sprint, nhưng inspection/adaptation không bị khóa ở cuối Sprint. Developers có thể điều chỉnh kế hoạch hằng ngày; PO có thể làm rõ hoặc sắp lại Product Backlog khi có bằng chứng; lỗi nghiêm trọng cần xử lý ngay.

Retrospective giúp nhìn **mẫu hình hệ thống và khả năng cải tiến lâu dài**, không phải “ngày duy nhất được sửa quy trình”.

## 9. Product Backlog: phản hồi không được biến thành kho ý kiến bất động

### 9.1. Backlog lớn không có nghĩa nhóm học nhiều

Một Product Backlog có hàng trăm ý kiến từ Sprint Review nhưng không có phân loại, thứ tự và quyết định:
- Có thể làm che khuất Product Goal.
- Tạo ảo tưởng mọi yêu cầu đều đã được “tiếp nhận”.
- Khiến stakeholders không biết kết quả phản hồi.
- Gây nhiều công việc cũ/trùng lặp.
- Làm Developers chạy theo ticket thay vì câu hỏi giá trị.

**Backlog là công cụ quản lý lựa chọn**, không phải nơi chứa mọi thông điệp mà tổ chức không muốn từ chối.

### 9.2. Luồng xử lý phản hồi minh họa

~~~text
Feedback arrives
    -> Triage: đây là bug, rủi ro, quan sát hay yêu cầu?
    -> Xác minh bối cảnh, tác động và độ tin cậy
    -> Gắn Product Goal / outcome / quyết định cần có
    -> Product Owner cân nhắc thứ tự hoặc thí nghiệm
    -> Thực hiện/đo hoặc từ chối có lý do
    -> Thông báo kết quả cho người liên quan
    -> Cập nhật dữ liệu và học tiếp
~~~

Với incident gây hại đang xảy ra, **không đợi cuộc họp backlog thông thường**; dùng đường xử lý khẩn và báo ảnh hưởng.

### 9.3. Ví dụ user story và acceptance criteria

**User story:**

> Là **học viên** đang đăng ký workshop, tôi muốn **biết yêu cầu của mình chưa hay đã được xác nhận**, để **không hiểu nhầm việc đăng ký thành công khi chưa được giữ chỗ**.

**Acceptance criteria ví dụ:**

1. Với trạng thái **PENDING**, UI hiển thị “Đang chờ xác nhận” và giải thích rõ **chưa được giữ chỗ**.
2. Với trạng thái **CONFIRMED**, UI chỉ hiển thị xác nhận sau khi hệ thống có dữ liệu nghiệp vụ có thẩm quyền.
3. Khi lấy trạng thái gặp lỗi/timeout, UI không tự suy đoán CONFIRMED.
4. Người dùng không được xem dữ liệu đăng ký của người khác.
5. Test phù hợp xác minh các trạng thái và quyền truy cập.
6. Khi có thay đổi về nội dung, kiểm tra lại người dùng có hiểu đúng trong bối cảnh sử dụng.

Các tiêu chí này nối **feedback → thay đổi yêu cầu → bằng chứng kiểm tra**, không chỉ “sửa chữ cho xong”.

### 9.4. “Không làm” cũng là một quyết định sản phẩm

Đôi khi Product Owner không đưa phản hồi vào ưu tiên ngay vì:
- Mẫu quá ít hoặc có cách giải thích khác.
- Vấn đề ít ảnh hưởng so với lỗi an toàn hiện tại.
- Một giải pháp tốn kém có thể được kiểm bằng experiment nhỏ hơn.
- Ý kiến không phục vụ Product Goal.
- Yêu cầu trùng một PBI đã có.
- Nhu cầu đã thay đổi và giải pháp cũ không còn hợp lý.

Hãy ghi **lý do, người quyết và điều kiện xem lại** khi tác động đáng kể. Không bắt đội phải thay đổi kế hoạch sau từng lời bình; đó là **phản ứng tùy hứng**, không phải thích ứng theo bằng chứng.

## 10. Ba vòng phản hồi phải liên kết với nhau

### 10.1. Phản hồi về **sản phẩm**

**Câu hỏi:** “Người dùng nhận được giá trị gì, có hiểu và sử dụng đúng không?”

Nguồn có thể có:
- Quan sát người dùng thực hiện tác vụ.
- Phỏng vấn về trải nghiệm và nhu cầu.
- Phản hồi trong Sprint Review.
- Support tickets và hành vi sử dụng sản phẩm.
- Telemetry với mẫu số và quyền riêng tư phù hợp.
- Kết quả thử nghiệm giao diện/feature flags theo cohort.
- Dữ liệu nghiệp vụ như tỷ lệ đăng ký hợp lệ, không xác nhận vượt sức chứa.

**Quyết định:** sửa Product Backlog, mục tiêu, cách thiết kế, phạm vi phát hành hoặc thí nghiệm.

### 10.2. Phản hồi về **chất lượng kỹ thuật**

**Câu hỏi:** “Increment có đúng, an toàn và có thể tiếp tục thay đổi không?”

Nguồn:
- Unit/integration/contract tests, TDD.
- CI pipeline, build failures.
- Code review và pairing.
- Lỗi production, monitoring, cảnh báo.
- Kiểm tra bảo mật/quyền truy cập.
- Recovery/rollback drills khi phù hợp.
- Test coverage theo rủi ro và lỗi lặp lại.

**Quyết định:** bổ sung regression tests, refactoring, sửa contract, kiểm soát rollout, cải thiện CI, khôi phục dịch vụ hoặc cập nhật DoD.

### 10.3. Phản hồi về **luồng và phối hợp**

**Câu hỏi:** “Công việc đang mắc kẹt ở đâu, chính sách nào gây chờ và nhóm có thể hoàn tất đều đặn không?”

Nguồn:
- WIP và work item age.
- Throughput và cycle time distribution.
- CFD dải Doing/Review/Verify.
- Blocked reasons và thời gian chờ review.
- Lịch sử phụ thuộc liên nhóm.
- Feedback từ Developers, PO và stakeholders.
- Dữ liệu về công việc ngoài luồng và mức gián đoạn.

**Quyết định:** giới hạn WIP, đổi cách handoff, nâng khả năng review, cải thiện phân quyền, điều chỉnh capacity và làm rõ Working Agreement.

### 10.4. Không dùng một vòng thay cho vòng khác

| Nếu chỉ có… | Nhóm có thể bỏ lỡ… |
| --- | --- |
| **Feedback người dùng** | Lỗi kỹ thuật chưa phát lộ, hàng chờ và khả năng vận hành |
| **CI/test xanh** | Sản phẩm đúng kỹ thuật nhưng giải sai nhu cầu |
| **Cycle time giảm** | Chất lượng bị hạ hoặc người dùng không còn giá trị |
| **Velocity tăng** | Công việc Done không được tích hợp hoặc không phù hợp Product Goal |
| **Retrospective vui vẻ** | Những hành động chưa thực hiện hoặc chất lượng tồi |
| **Báo cáo incident** | Cải tiến lâu dài chưa được thực hiện |
| **Khảo sát hài lòng** | Hành vi thực khác với câu trả lời khảo sát |

**Agile hiệu quả đòi hỏi nhiều vòng phản hồi tương hỗ**. Không thể nói nhóm thực sự thích ứng chỉ vì một chỉ số có xu hướng đẹp.

## 11. Kanban: nhìn dòng việc thật, không chỉ bảng thẻ đầy màu

### 11.1. Bảng cột không đồng nghĩa quản lý flow

Có thể có một bảng Kanban rất đẹp mà:
- Hàng chờ Review dài.
- WIP bị đẩy ngày càng nhiều.
- Người phụ trách chỉ đổi màu thẻ cho kịp báo cáo.
- Item đang blocked được chuyển về Ready để không tính WIP.
- Không ai xem age của các item rất cũ.
- Không có chính sách pull hay thời điểm xem lại.

Kanban nhấn mạnh **định nghĩa workflow, trực quan hóa, quản lý WIP, đo flow và cải tiến qua bằng chứng**. Cách đặt cột không phải mục tiêu cuối.

### 11.2. Định nghĩa flow trước khi đo

~~~text
Ready -> Doing -> Review -> Verify -> Done
          ^ STARTED                 ^ FINISHED

WIP(t) = Số item đã Started nhưng chưa Finished tại thời điểm t
Throughput(kỳ) = Số item Finished trong kỳ
Cycle time(item Done) = Finished_at - Started_at
Work item age(item chưa Done) = now - Started_at
~~~

Nếu blocked xảy ra sau Started thì **thời gian chờ vẫn thuộc flow** theo ranh giới này. Muốn cải thiện, nhóm cần nhìn được nó, không giấu vào trạng thái “không tính”.

### 11.3. CFD và cycle time cho biết nơi kiểm tra

Giả sử:
- Trong ba tuần, số item ở Review tăng từ 3 lên 9.
- Throughput theo tuần gần như không đổi.
- Cycle time p85 của các story tương đồng tăng từ 6 lên 10 ngày.
- Năm item đang mở đã già hơn thời gian nhóm thường thấy.

Những quan sát này **gợi ý có hàng chờ**, nhưng không chứng minh một reviewer làm chậm. Cần kiểm:
- Item có quá lớn?
- Thiếu test và bối cảnh?
- Có một chuyên gia duy nhất?
- CI/môi trường có chặn?
- Quy tắc sắp thứ tự có khiến nhóm bắt đầu nhiều việc mới?
- Dữ liệu có đổi Started/Finished trong kỳ?

Phản hồi trở thành thích ứng khi nhóm **chọn một can thiệp nhỏ** và đo lại các tín hiệu ấy, đồng thời giữ quality guardrails.

### 11.4. SLE hữu ích khi có dữ liệu phù hợp

Một Service Level Expectation có thể phát biểu:

> “Dựa trên lịch sử các story cùng loại, khoảng 85% item hoàn tất trong 8 ngày lịch hoặc ít hơn kể từ Started.”

Đây là **kỳ vọng có điều kiện**, không phải deadline chắc chắn. Cần công bố ranh giới, loại item, cỡ mẫu, phương pháp percentile và thay đổi workflow. Không dùng nó để quy lỗi cho người đang có item age 9 ngày; hãy dùng như tín hiệu **hỗ trợ item bị chặn** và cập nhật forecast.

## 12. XP và phản hồi kỹ thuật nhanh: đừng đợi cuối Sprint mới biết mã sai

### 12.1. “Có kiểm thử” chưa chắc vòng phản hồi tốt

Một nhóm có thể báo “mọi PBI đều được QA kiểm thử” nhưng chỉ đưa mã sang QA ngày cuối Sprint, rồi mất thêm một tuần để sửa integration. Nghi thức bàn giao đã đủ, **phản hồi đến quá muộn để điều chỉnh kế hoạch kịp thời**.

Các thực hành kỹ thuật như **TDD, continuous integration (CI), pair programming, refactoring, small releases** tạo tín hiệu sớm khi được áp dụng có chất lượng:
- **TDD:** chu trình test đỏ → mã đủ cho test xanh → refactor; vẫn cần test tích hợp, quyền dữ liệu và kiểm chứng sản phẩm.
- **CI:** tích hợp thay đổi nhỏ thường xuyên, chạy kiểm tra tự động, phát hiện lỗi khi ngữ cảnh còn mới.
- **Pair programming:** xử lý hiểu nhầm hoặc quyết định khó ngay lúc làm, đồng thời chia sẻ kiến thức.
- **Refactoring:** cải thiện thiết kế dưới mạng kiểm tra đáng tin để giữ khả năng thay đổi.
- **Small releases:** giảm kích thước lô và tạo cơ hội học từ người dùng sớm hơn.

### 12.2. Vòng phản hồi kỹ thuật

~~~text
Ví dụ nghiệp vụ -> Test mô tả hành vi -> Thay đổi mã nhỏ
     -> Code review / pairing -> CI / contract / integration tests
     -> Phản hồi lỗi sớm -> Sửa và refactor -> Increment đạt DoD
     -> Quan sát trong sử dụng thật -> Cập nhật yêu cầu và test
~~~

**Test xanh không chứng minh người dùng nhận giá trị.** Nó chỉ cung cấp bằng chứng về những điều đã được kiểm. Nếu test không bao phủ rủi ro chính, báo cáo “CI xanh” dễ tạo cảm giác an toàn giả.

### 12.3. Đặc tả minh họa cho workshop

~~~gherkin
Tính năng: Trạng thái đăng ký workshop

  Tình huống: Yêu cầu đang chờ chưa được giữ chỗ
    Cho trước đăng ký có trạng thái PENDING
    Khi học viên mở trang trạng thái
    Thì hệ thống hiển thị "Đang chờ xác nhận"
    Và giải thích rõ "Chưa được giữ chỗ"

  Tình huống: API trạng thái bị timeout
    Cho trước API lấy trạng thái không phản hồi
    Khi giao diện hiển thị thông báo
    Thì giao diện không tự suy đoán trạng thái CONFIRMED

  Tình huống: Không tiết lộ đăng ký của người khác
    Cho trước một đăng ký thuộc học viên A
    Khi học viên B truy cập đường dẫn của đăng ký A
    Thì hệ thống không tiết lộ dữ liệu cá nhân của A
~~~

Đây là **ví dụ đặc tả**, không phải xác nhận hệ thống thực đã an toàn. Nhóm cần test transaction, concurrency, phân quyền, môi trường tích hợp và hành vi thực của người dùng khi phù hợp.

### 12.4. “Nhanh hơn” không được đổi bằng bỏ chất lượng

Nếu sau Review khách hàng muốn sửa gấp, một phản ứng sai là giảm test, bypass review vùng rủi ro, đánh dấu Done trước integration hoặc release không có observability/rollback. Khi ấy “thích ứng nhanh” thực chất **chuyển chi phí sang người dùng và vận hành**. Mục tiêu là rút ngắn vòng học **trong guardrails về tính đúng, an toàn và khả năng phục hồi**.

## 13. Phản hồi đáng tin cần bối cảnh, mẫu số và câu hỏi quyết định

### 13.1. Không phải feedback nào cũng giống nhau

| Nguồn | Ví dụ | Giúp biết gì | Giới hạn |
| --- | --- | --- | --- |
| **Quan sát tác vụ** | 8/12 học viên không biết PENDING nghĩa gì | Người dùng thực sự hiểu thế nào | Mẫu nhỏ và cách tuyển người |
| **Phỏng vấn** | Học viên nghĩ nút “Gửi” xác nhận chỗ ngay | Cách suy nghĩ và nhu cầu | Lời nói có thể khác hành vi |
| **Telemetry** | Nhiều người mở lại trang trạng thái | Mẫu hành vi ở quy mô rộng | Không tự suy nguyên nhân |
| **Support** | Nhiều câu hỏi về xác nhận chỗ | Vấn đề xuất hiện trong vận hành | Chỉ phản ánh người liên hệ Support |
| **Logs/incident** | Timeout khiến giao diện hiển thị sai | Lỗi kỹ thuật/độ tin cậy | Cần xét severity, traffic |
| **Flow metrics** | Cycle time tăng, Review band dày | Gợi ý hàng chờ | Không kết luận ai gây chậm |
| **Stakeholder** | Người tổ chức muốn SMS | Mục tiêu vận hành và kỳ vọng | Đề xuất chưa chắc giải đúng nhu cầu |

### 13.2. Phân biệt quan sát, giả thuyết, đề xuất, quyết định

- **Quan sát:** “5 trong 10 học viên thử nghĩ PENDING có nghĩa được giữ chỗ.”
- **Giả thuyết:** “Dòng chữ ‘Đăng ký thành công’ ở bước trước có thể tạo hiểu nhầm.”
- **Đề xuất:** “Thêm câu ‘chưa được giữ chỗ’.”
- **Quyết định:** “Thử hai cách hiển thị và kiểm tra tỷ lệ hiểu đúng; tuyệt đối không khẳng định CONFIRMED khi chưa có dữ liệu có thẩm quyền.”
- **Hành động:** “PO cập nhật AC; Developers sửa/test; người nghiên cứu thu kết quả.”

Phản hồi của người dùng thường cho biết **vấn đề**, không nhất thiết cho biết **giải pháp tốt nhất**. “Tôi muốn SMS” có thể biểu thị nhu cầu được biết kết quả; email, trang trạng thái hoặc thông báo trong ứng dụng cũng cần được cân nhắc.

### 13.3. Số liệu không có định nghĩa dễ dẫn tới thích ứng sai

Nếu báo cáo “95% đăng ký thành công” nhưng:
- Mẫu số chỉ gồm HTTP 200.
- Những người bỏ dở trước khi gửi API bị loại.
- PENDING bị đếm như CONFIRMED.
- Retry tạo event trùng lặp.
- Hai giai đoạn dùng định nghĩa thành công khác nhau.

thì metric có thể **không trả lời đúng nhu cầu sản phẩm**. Trước khi quyết định phải ghi định nghĩa, thời gian, nguồn, mẫu số, dữ liệu thiếu và độ tin cậy.

### 13.4. Cần bảo vệ dữ liệu và sự đồng ý

Khi thu feedback người dùng, chỉ truy cập dữ liệu cần thiết, tuân thủ quy tắc đồng ý và lưu trữ của tổ chức. Đừng đưa email, số điện thoại, nội dung đăng ký nhạy cảm vào dashboard công khai để “minh bạch hơn”. Transparency trong Agile **không đồng nghĩa mọi người được xem mọi dữ liệu cá nhân**.

## 14. Khi nào thích ứng, khi nào tiếp tục hoặc kiểm tra thêm?

### 14.1. Thích ứng không đồng nghĩa đổi hướng theo mọi lời bình

Một nhóm có thể mắc lỗi đối nghịch: mọi stakeholder đưa ý kiến là backlog đổi, chưa hoàn tất thử nghiệm trước đã chạy sang việc khác. Điều đó không phải empiricism mà là **phản ứng tùy hứng**.

Đặt bảy câu hỏi trước quyết định:
1. **Mức ảnh hưởng:** có gây hại, mất giá trị lớn hay chỉ là sở thích?
2. **Độ tin cậy:** dữ kiện có đủ phù hợp, cần kiểm chứng thêm?
3. **Mức khẩn:** chờ tới vòng kiểm tra sau có rủi ro không thể chấp nhận?
4. **Khả năng đảo ngược:** có thể thử nhỏ trên một cohort hoặc qua feature flag?
5. **Cost of delay:** chờ thêm làm mất cơ hội gì?
6. **Phụ thuộc và guardrails:** an toàn, dữ liệu, pháp lý, SLA, compatibility?
7. **Cam kết đang có:** Sprint Goal, DoD, capacity và nghĩa vụ vận hành?

### 14.2. Bốn loại quyết định có trách nhiệm

| Quyết định | Khi hợp lý | Điều cần ghi |
| --- | --- | --- |
| **Hành động ngay** | Sự cố sản xuất gây hại hoặc dữ liệu sai | Incident process, mitigation và kiểm chứng |
| **Điều chỉnh** | Bằng chứng đủ rõ, giải pháp và rủi ro phù hợp | Backlog/AC/working agreement, owner |
| **Thử thêm** | Chưa rõ nguyên nhân hoặc hai giải pháp có đánh đổi | Giả thuyết, thí nghiệm, metric, thời hạn |
| **Giữ nguyên có lý do** | Chưa phù hợp Product Goal hoặc chứng cứ yếu | Lý do, điều kiện xem lại, thông báo |

**Không đổi** cũng có thể là kết quả kiểm tra nghiêm túc, khác với bỏ qua feedback. Điều quan trọng là **ra quyết định có lý do và theo dõi khi điều kiện đổi**.

### 14.3. Decision log ngắn

~~~text
Feedback/PBI ID:
Product Goal liên quan:
Quan sát và nguồn:
Giả định cần xác minh:
Lựa chọn khả thi:
Rủi ro/cost of delay:
Quyết định: làm / thử / giữ / dừng
Người có quyền quyết:
Hành động và owner:
Test/metric kiểm chứng:
Guardrails, điều kiện đảo:
Mốc xem lại và người cần biết:
~~~

Mẫu không bắt buộc cho mọi đổi chữ nhỏ; quyết định có rủi ro và phụ thuộc lớn cần hồ sơ tương xứng.

## 15. Ai biến phản hồi thành quyết định và hành động?

### 15.1. Feedback ownership phải rõ

- **Product Owner:** tối đa hóa giá trị, quản lý Product Backlog và sự thích ứng về ưu tiên sản phẩm.
- **Developers:** tạo Increment, bảo vệ chất lượng/DoD, tự điều chỉnh kế hoạch kỹ thuật và phối hợp.
- **Scrum Master:** cải thiện tính hiệu quả Scrum, giúp tổ chức tháo trở ngại trong inspect/adapt.
- **Stakeholders và người dùng:** cung cấp bối cảnh, quan sát, ràng buộc và phản hồi.
- **Lãnh đạo/đơn vị liên quan:** ngân sách, quyền ngoài phạm vi team và kiểm soát bắt buộc.

Trách nhiệm chung **không có nghĩa mọi người cùng có quyền chốt mọi thứ**. Thiếu decision owner có thể khiến feedback đi vòng quanh trong chat.

### 15.2. Ví dụ phân trách nhiệm

| Feedback | Người chủ trì quyết định | Đầu ra kiểm chứng |
| --- | --- | --- |
| Học viên hiểu sai PENDING | Product Owner về ưu tiên và hành vi; Developers thực thi | PBI/AC, test và kết quả dùng thử |
| CI đỏ sau thay đổi | Developers và người sở hữu pipeline | Test/rào chắn được sửa, build có chất lượng |
| Review queue tăng | Developers và nhóm quản lý luồng | Chính sách WIP thử, age/cycle time xem lại |
| Lỗi quyền dữ liệu | Incident lead và owners theo policy | Mitigation, security test, hậu kiểm |
| Product Goal không phù hợp | Product Owner với stakeholders, lãnh đạo nếu vượt thẩm quyền | Backlog/mục tiêu được cập nhật |
| Nhóm thường xuyên thiếu năng lực | Lãnh đạo có quyền phân bổ, cùng PO/Developers | Capacity và ưu tiên có trade-off rõ |

Bảng mang tính **minh họa**, không thay trách nhiệm pháp lý hay chính sách thực của tổ chức.

### 15.3. Đóng vòng với người cung cấp phản hồi

Quy trình đơn giản:
1. **Acknowledged:** xác nhận đã nhận ý kiến.
2. **Triage:** phân loại và hiểu bối cảnh.
3. **Decision:** làm, thử, dừng hay không làm cùng lý do.
4. **Execution:** PBI/test/chính sách được thay.
5. **Verification:** kiểm chứng hiệu quả hoặc rủi ro mới.
6. **Communication:** thông báo kết quả cho bên liên quan.

**Acknowledged không phải resolved.** Ticket không nên bị đóng chỉ vì đã sao chép nội dung sang backlog mà chưa có trách nhiệm xử lý tiếp.

## 16. Khi có nhiều nhóm hoặc nhiều tầng quyết định, feedback dễ thất lạc

### 16.1. Hoàn thành cục bộ không đồng nghĩa hoàn thành sản phẩm

Một feedback về trạng thái đăng ký có thể đi:
- Support đưa vào backlog UX.
- UX chờ API contract từ nhóm backend.
- Backend chờ thay đổi dữ liệu.
- QA phát hiện hợp đồng không đúng khi tích hợp cuối kỳ.
- Mỗi team có Review riêng báo việc “đã hoàn thành”, nhưng chưa có Increment sử dụng được.

Mọi team có thể đã họp đầy đủ, còn **vòng phản hồi cấp sản phẩm vẫn bị đứt qua các ranh giới**.

### 16.2. Các câu hỏi cần trả lời ở cấp sản phẩm

- Ranh giới sản phẩm là gì và Product Goal chung nào định hướng?
- Ai chịu trách nhiệm về Product Backlog?
- Definition of Done cho Increment tích hợp là gì?
- Một feedback có owner end-to-end hay bị chia vào ba hàng chờ?
- Có cơ hội kiểm tra Increment thực với stakeholder không?
- Bao nhiêu thời gian chờ do hợp đồng/phê duyệt, không do triển khai?
- Khi bất đồng liên nhóm, ai có quyền ra quyết định trước mốc quan trọng?
- Quyết định và bằng chứng lưu ở nguồn nào?

Theo Scrum Guide 2020, khi nhiều Scrum Teams cùng làm **một sản phẩm**, họ chia sẻ **Product Goal, Product Backlog và Product Owner**, và cùng tuân thủ một Definition of Done. Các sản phẩm khác nhau cần xác định ranh giới khác nhau, không áp cơ học cho toàn công ty.

### 16.3. Đừng thêm meeting khi vấn đề là ownership

Một phiên điều phối liên team có thể giúp giải quyết dependency, nhưng một “Scrum of Scrums” chỉ để các nhóm đọc lại status có thể thành nghi thức mới. **Scrum of Scrums không phải event bắt buộc trong Scrum Guide 2020.**

Trước khi thêm cuộc họp:
- Làm rõ Product Backlog và ownership.
- Ghi feedback/decision trong nguồn sự thật chung.
- Thử contract tests và CI.
- Pairing ở vùng phụ thuộc khó.
- Giảm WIP và ưu tiên hoàn tất.
- Có đường escalation và mốc quyết.
- Xem lại ranh giới nhóm nếu mọi story đều phải qua nhiều backlog.

### 16.4. An toàn tâm lý hỗ trợ sự minh bạch

Nếu người nêu rủi ro bị trừng phạt, nhóm có thể:
- Chỉ demo trường hợp thành công.
- Giấu blocker hoặc lỗi.
- Đóng ticket sớm để báo cáo.
- Tránh thí nghiệm có thể không đạt.
- Đẩy phản hồi tiêu cực vào chat riêng.

Vẫn cần accountability, bảo vệ người dùng và đánh giá năng lực có bằng chứng, nhưng **không tạo văn hóa đổ lỗi cho việc nêu dữ kiện bất lợi**. Sự thật phải được chia sẻ thì nhóm mới inspect/adapt được.

## 17. Tình huống xuyên suốt: ba Sprint đầy nghi thức nhưng người dùng vẫn hiểu sai

### 17.1. Product Goal

Một team phát triển nền tảng đăng ký workshop có Product Goal:

> “Học viên đăng ký và biết trạng thái chính xác, không được xác nhận vượt số chỗ.”

User story trọng tâm: học viên phân biệt PENDING và CONFIRMED.

Nhóm có Planning, Daily Scrum, Review, Retro, Kanban board và CI. Tuy nhiên, test chỉ kiểm API trả trạng thái, không kiểm người dùng có hiểu nhãn giao diện. Support liên tục nhận câu hỏi “Tôi đã có chỗ chưa?”.

### 17.2. Sprint 1 – nghi thức đã làm, vòng học đứt

- **Planning:** chọn làm giao diện mới nhưng Sprint Goal chỉ là “hoàn thiện giao diện”, khó liên hệ outcome.
- **Daily Scrum:** mọi người báo task, item chờ review không được hỗ trợ.
- **Review:** trình diễn nhãn “Đang chờ xác nhận”; stakeholder nêu có thể hiểu nhầm; ý kiến được chép vào tài liệu.
- **Retrospective:** ghi “cần giao tiếp tốt hơn” nhưng thiếu owner, deadline, dữ liệu.
- **Kết quả:** code được merge nhưng test trải nghiệm chưa có, chưa thấy quyết định Product Backlog từ feedback.

### 17.3. Sprint 2 – phản hồi lặp lại, kế hoạch vẫn nguyên

- Support có thêm ví dụ thực tế.
- Product Backlog vẫn ưu tiên animation theo kế hoạch cũ, không có giải thích.
- Các Developers hoàn tất task cục bộ, integration ở cuối.
- Retrospective nhắc lại cùng lời khuyên.
- Review không trình bày các điều chưa hiểu rõ hoặc dữ liệu mới.

Không nhất thiết phải thực hiện mọi lời phàn nàn, nhưng **không triage, không ghi quyết định và không giao ai kiểm chứng** là dấu hiệu vòng học đã bị bỏ qua.

### 17.4. Đổi sang giả thuyết có thể kiểm chứng

Product Owner, Developers và người hỗ trợ học viên thống nhất:

> “Nếu hiển thị ‘Đang chờ xác nhận – chưa được giữ chỗ’ và giải thích khi nào có CONFIRMED, học viên sẽ hiểu đúng trạng thái hơn mà không tăng lỗi hiển thị/đăng ký.”

Nhóm:
1. Đổi thứ tự backlog: tạm lùi animation để kiểm vấn đề nghiệp vụ quan trọng.
2. Tạo vertical slice nhỏ với acceptance criteria và test về quyền/trạng thái.
3. Triển khai thử trên môi trường/cohort phù hợp, tránh gây hại người dùng.
4. Đo tỷ lệ người tham gia **trả lời đúng** “đã được giữ chỗ chưa?” sau tác vụ thật.
5. Theo dõi lỗi dữ liệu, thông báo sai, quyền truy cập và performance.
6. Chỉ định owner thu kết quả và thời điểm Product Owner quyết định tiếp.

### 17.5. Sprint 3 – thay đổi đã xảy ra, có bằng chứng để kiểm lại

Giả sử phép thử **minh họa** với hai mẫu người dùng:

| Tín hiệu | Trước | Sau |
| --- | ---: | ---: |
| Số người thử | 30 | 30 |
| Hiểu đúng PENDING | 20/30 | 24/30 |
| Tỷ lệ hiểu đúng | 66,7% | 80,0% |
| Trả lời sai | 10/30 | 6/30 |
| Lỗi nghiêm trọng quan sát được trong phép thử | 0 | 0 |

~~~text
Trước = 20 / 30 = 66,7% (làm tròn)
Sau   = 24 / 30 = 80,0%

Chênh lệch tuyệt đối = 80,0 − 66,7 ≈ 13,3 điểm phần trăm
Mức tăng tương đối = (24/20) − 1 = 20%
~~~

**Không nói “tăng 13,3%” khi muốn nói 13,3 điểm phần trăm.** Và không khẳng định tính năng gây toàn bộ cải thiện: hai mẫu nhỏ có thể không tương đồng, cách hỏi thay đổi hoặc có biến gây nhiễu.

Không quan sát thấy lỗi nghiêm trọng trong 30 lượt **không chứng minh không tồn tại lỗi**. Chất lượng dữ liệu, test tích hợp và monitoring tiếp tục là guardrails.

### 17.6. Cần học tiếp điều gì?

- Vì sao 6/30 người vẫn hiểu nhầm?
- Câu chữ, vị trí, thiết bị hay bước trước gây hiểu sai?
- Người thử có giống học viên thực tế?
- Support requests và lỗi thực có giảm không?
- Có item cũ bị chặn vì thay đổi ưu tiên không?
- Có hành vi nào khác xấu đi sau rollout?
- Có cần mở rộng mẫu hoặc giữ feature flag để đổi tiếp?

Nhóm có thể **giữ cải tiến có điều kiện và tiếp tục thu bằng chứng**, thay vì tuyên bố thành công hoàn toàn.

### 17.7. Thay đổi của từng sự kiện

| Nghi thức | Trước | Sau khi nối vòng học |
| --- | --- | --- |
| Planning | Chọn task theo roadmap cũ | Sprint Goal/PBI phản ánh giả thuyết cần kiểm |
| Daily Scrum | Báo cáo cá nhân | Điều chỉnh phối hợp để item đạt Done |
| Review | Demo/ghi ý kiến | Cùng kiểm Increment, chọn hành động backlog |
| Retro | Lặp khẩu hiệu | Chọn thử nghiệm có owner và review point |
| Backlog | Kho lưu mọi ý kiến | Quyết định giá trị, làm/thử/không làm có lý do |
| CI/test | Kiểm API tồn tại | Kiểm quy tắc/timeout/quyền và AC cập nhật |
| Kanban | Chuyển trạng thái để báo | Theo WIP, tuổi item và hàng chờ |
| Người dùng | Chỉ đoán mức hiểu | Dùng thử, đo và điều chỉnh |

**Bài học không phải “mỗi Sprint đều phải có metric tăng”.** Bằng chứng không như kỳ vọng vẫn có giá trị nếu giúp tránh đầu tư sai hoặc sửa rủi ro sớm.

## 18. Thử nghiệm Retrospective về hàng chờ review: ví dụ đầy đủ

### 18.1. Baseline minh họa

Một nhóm quan sát trong bốn tuần:
- 14 item từng vào Review.
- 6 trong 14 item đã hoàn tất Review với thời gian chờ **trên hai ngày làm việc**.
- 5 item đã Started còn chưa Finished ở cuối kỳ.
- Developers vẫn kéo việc mới khi Review đầy.
- Chưa chắc nguyên nhân là thiếu reviewer, item quá lớn hay CI không ổn.

**6/14 là một tín hiệu**, không phải kết luận nguyên nhân.

### 18.2. Giả thuyết có thể thử

> “Nếu hạn chế kéo item mới khi Review đầy và tổ chức pairing ngắn cho PR khó, số item Review wait vượt hai ngày làm việc sẽ giảm, trong khi Definition of Done và lỗi sau release không xấu đi.”

| Thuộc tính | Minh họa |
| --- | --- |
| **Can thiệp** | Xem item gần Done trước khi kéo thêm Doing; pairing cho PR khó |
| **Owner** | Developers thống nhất người theo dõi chính sách |
| **Primary signal** | Tỷ lệ item có Review wait vượt hai ngày làm việc |
| **Secondary signals** | WIP, work item age, throughput, cycle time |
| **Guardrails** | Test/DoD, lỗi quyền/dữ liệu, CI, giờ làm |
| **Timebox** | Một Sprint để bắt đầu học, có thể thêm khi mẫu nhỏ |
| **Review point** | Trong Sprint nếu bất lợi; Retrospective kế tiếp |
| **Stop/change trigger** | Test bị bỏ, lỗi tăng, queue chỉ chuyển sang Verify |

### 18.3. Kết quả giả định

Giả sử trong kỳ thử có 15 item đã hoàn tất Review, 3 item chờ trên hai ngày làm việc:

~~~text
Trước: 6/14 ≈ 42,9%
Sau:   3/15 = 20,0%
Chênh lệch = 20,0 − 42,9 ≈ −22,9 điểm phần trăm
~~~

Cần kiểm thêm:
- Có item còn đang ở Review và chưa có thời gian chờ cuối cùng không?
- Item sau có nhỏ hơn hoặc ít phụ thuộc hơn không?
- Review nhanh nhưng Verify chậm hơn?
- CI có lỗi phát sinh chưa được ghi?
- Thời gian chờ có bị chuyển về Ready trước Started?

Nếu các điều kiện đo không tương đồng, **không tuyên bố thử nghiệm chắc chắn làm giảm wait 22,9 điểm phần trăm**. Có thể giữ thử thêm, chỉnh policy hoặc dừng theo kết quả và guardrails.

### 18.4. Điểm khác giữa action thật và khẩu hiệu

Một action thực sự có:
- Vấn đề và tín hiệu.
- Giả thuyết.
- Can thiệp được thực thi.
- Owner và khoảng thử.
- Cách đo tác động.
- Guardrails.
- Quyết định tiếp theo từ bằng chứng.

Thiếu những thành phần ấy, câu “Tập trung review nhiều hơn” chỉ là **mong muốn** được ghi trong biên bản.

## 19. Đo vòng học mà không biến nó thành KPI nghi thức mới

### 19.1. Hỏi điều gì cần biết trước khi chọn chỉ số

| Câu hỏi | Tín hiệu có thể dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| Phản hồi đến đủ sớm chưa? | Từ release/thử nghiệm đến tín hiệu hữu ích | Nhiều feedback không có nghĩa tốt hơn |
| Nhóm đã quyết theo bằng chứng chưa? | Các quyết định quan trọng có nguồn, giả thuyết và owner | Đừng đếm decision logs để lấy điểm |
| Action đã thay đổi điều gì? | Kết quả của can thiệp sau Retro | Đóng action không đồng nghĩa cải thiện |
| Luồng công việc có bớt nghẽn? | WIP, throughput, cycle time, aging WIP | Không dùng để xếp hạng cá nhân |
| Người dùng tốt hơn? | Hoàn tất tác vụ, hiểu đúng, lỗi nghiệp vụ, support | Cần mẫu số, bối cảnh, kiểm biến gây nhiễu |
| Chất lượng được giữ? | CI reliability, defects, incident, recovery | Lỗi hiếm không thể chứng minh an toàn qua mẫu nhỏ |
| Mọi người có thể nói thật? | Blocker được nêu sớm, feedback từ nhóm an toàn | Giữ kín thông tin nhạy cảm |
| Đầu tư có thích ứng? | Quyết định tiếp tục, dừng hoặc đổi hướng có lý do | Không đổi ngân sách theo một tuần dữ liệu |

### 19.2. Nhìn độ trễ của vòng phản hồi

Có thể ghi các mốc:
1. **Signal:** lúc phản hồi hoặc sự kiện được ghi.
2. **Understood:** lúc vấn đề, phạm vi và thông tin cần quyết đã rõ.
3. **Decision:** lúc người có quyền chọn phương án.
4. **Changed:** lúc Increment/chính sách được thay đổi.
5. **Verified:** lúc có dữ liệu kiểm tra ảnh hưởng.

~~~text
Signal -> Understood -> Decision -> Changed -> Verified
       |             |           |           |
       +-- wait A ---+-- wait B --+-- wait C --+
~~~

Không nhất thiết phải giảm tất cả khoảng chờ bằng mọi giá: quyết định bảo mật hoặc dữ liệu có thể cần kiểm soát kỹ. Nhưng nếu “Decision → Changed” đứng yên ba Sprint vì không có capacity, **tổ chức cần sửa cơ chế ưu tiên/thực thi**, không thêm một cuộc họp thu feedback.

### 19.3. Tại sao “mỗi Retro đóng 10 action” là KPI tệ?

Khi số action là mục tiêu:
- Người ta chọn action dễ, không giải nút thắt chính.
- Action khó bị tách thành nhiều task để đạt chỉ tiêu.
- Các mối nguy governance bị tránh vì vượt quyền team.
- Việc chưa làm bị xóa khỏi bảng.
- Không ai xem outcome của action.

Một thí nghiệm có ý nghĩa được làm và học lại thường có giá trị hơn nhiều action trang trí. **Đo tác dụng, không chỉ số thao tác.**

### 19.4. Xử lý feedback mâu thuẫn

Support muốn giảm cuộc gọi, Marketing muốn nhiều người đăng ký, Operations muốn ổn định capacity, còn học viên muốn biết chắc mình có chỗ. Không thể chỉ “lấy trung bình các ý kiến” để ra quyết định.

Hãy công bố Product Goal, các bất biến không được vi phạm, những đánh đổi, nguồn dữ liệu, người có quyền quyết, cách thử an toàn nếu còn bất định và mốc phải chốt nếu cost of delay tăng.

## 20. Những sai lầm lặp lại và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Dùng attendance để đo Agile | Họp đủ nhưng chưa tạo giá trị | Xem evidence, quyết định và outcome |
| Daily Scrum là báo cáo cho manager | Không inspect Sprint Goal | Developers điều chỉnh kế hoạch |
| Planning chỉ chia task đã định | Bỏ khả năng điều chỉnh theo capacity | Why–What–How, Sprint Goal, DoD |
| Review chỉ là demo slide | Không có kiểm chứng Increment và người dùng | Working session với stakeholder |
| Review thành cổng release approval | Trộn mục đích feedback và governance | Tách kiểm soát bắt buộc khỏi inspect/adapt |
| Retro chỉ ghi “giao tiếp tốt hơn” | Không thể hành động hay kiểm chứng | Giả thuyết, owner, mốc thử |
| Retrospective tạo quá nhiều action | Capacity không đủ, việc dang dở | Chọn 1–2 thay đổi có ý nghĩa |
| Không xem lại action kỳ trước | Không đóng vòng học | Kiểm trước/sau, giữ/chỉnh/dừng |
| Product Backlog là kho ý kiến | Phản hồi không dẫn tới quyết định | Triage, priority, rationale |
| Thay mọi thứ theo feedback mới | Rework, mất tập trung | Đánh giá mức ảnh hưởng và độ tin cậy |
| Im lặng bị xem là đồng ý | Quyết định có thể chưa được xác nhận | Decision rights rõ |
| Coi mọi mong muốn là giải pháp | Xây sai nhu cầu | Tìm mục tiêu người dùng và kiểm giả thuyết |
| Gọi merge là Done | Increment thiếu integration/DoD | Chất lượng chung, kiểm chứng sản phẩm |
| CI xanh nghĩa người dùng hài lòng | Test không bao phủ outcome | Product feedback song song kỹ thuật |
| Chỉ test cuối Sprint | Phản hồi quá muộn | CI, TDD, contract tests sớm |
| Bỏ test để giao nhanh | Dời rủi ro sang production | Guardrails và small releases |
| Velocity tăng = giá trị tăng | Metrics dễ bị méo | Outcome, quality và flow |
| Chỉ xem item Done | Bỏ việc rất già đang kẹt | Aging WIP và cycle time |
| Đổi nhãn blocked để giảm WIP | Che nghẽn | Định nghĩa started/finished trung thực |
| Percentile như deadline chắc chắn | Dự báo sai, đổ lỗi | SLE có tỷ lệ và giới hạn |
| Mỗi team báo Done riêng | Không có Increment cấp sản phẩm | Product ownership/DoD phù hợp |
| Thêm họp khi thiếu quyền quyết | Tăng chi phí, feedback vẫn đứng | Decision owner và escalation |
| Khẳng định nhân quả từ hai mẫu nhỏ | Suy luận thiếu cơ sở | Nêu bối cảnh và biến gây nhiễu |
| Không phân biệt % và điểm phần trăm | Báo sai mức thay đổi | Tính đúng và ghi đơn vị |
| Ép experiment nào cũng thành công | Giấu bằng chứng bất lợi | Ghi nhận việc học có trách nhiệm |
| Phạt người nêu blocker | Transparency mất | Chống đổ lỗi, cải tiến hệ thống |
| Chờ Retro mới sửa lỗi nghiêm trọng | Kéo dài nguy cơ | Incident response ngay |
| Thưởng theo số action đóng | Khuyến khích nghi thức rỗng mới | Đo tác dụng thực của action |
| Tự chủ nhưng thiếu thẩm quyền | Feedback không thành thay đổi | Quyền quyết và nguồn lực rõ |
| Agile đồng nghĩa không cần kế hoạch | Không quản lý rủi ro và capacity | Forecast thích ứng, guardrails |

## 21. Bài thực hành có đáp án định hướng

### 21.1. Bài A – Tìm nơi vòng phản hồi bị đứt (10 phút)

Một nhóm:
- Planning đủ lịch, có Sprint Goal.
- Sprint Review ghi ba ý kiến quan trọng về sai trạng thái.
- Ý kiến lưu trong slide, không thành PBI hoặc quyết định.
- Sprint sau vẫn theo kế hoạch cũ.
- Retrospective ghi “cần xử lý feedback tốt hơn”.

Hãy chỉ ra điểm đứt, người cần quyết, dữ liệu cần kiểm và một action cụ thể.

**Đáp án định hướng:** điểm đứt ở **triage/decision → backlog/action**. Product Owner cần cân nhắc giá trị và thứ tự; Developers giúp xác minh tính đúng và triển khai. Action nên chỉ rõ loại feedback, PBI/owner và ngày xem lại, không chỉ viết khẩu hiệu.

### 21.2. Bài B – Daily Scrum hướng vào Sprint Goal (10 phút)

Story A đang ở Review thiếu reviewer, B ở Verify có CI đỏ, C ở Ready. Sprint Goal yêu cầu giao luồng trạng thái đúng.

Viết ba quyết định Developers có thể đưa ra và một huddle kỹ thuật phù hợp **sau Daily Scrum**.

**Đáp án:** hỗ trợ review A, gỡ CI cho B, chưa kéo C khi bottleneck còn đầy; sắp huddle với người liên quan để debug pipeline và cập nhật bảng. Mục tiêu là điều chỉnh kế hoạch, không phải hoàn thành vòng báo cáo cá nhân.

### 21.3. Bài C – Sprint Review có phản hồi (15 phút)

Stakeholder nói “demo ổn”, nhưng 4/10 học viên thử hiểu sai PENDING. Viết:
1. Hai câu hỏi tìm hiểu cách hiểu của người dùng.
2. Sự kiện quan sát và giả thuyết khác nhau thế nào.
3. Hai cách kiểm chứng thay đổi.
4. Ai cân nhắc thứ tự Product Backlog.
5. Guardrails về quyền và nghiệp vụ.

**Gợi ý:** không tự triển khai giải pháp đầu tiên người góp ý nêu. Đánh giá ngữ cảnh người dùng, thử giải thích/trình bày, giữ quy tắc CONFIRMED có thẩm quyền và không lộ dữ liệu.

### 21.4. Bài D – Viết Retrospective action (15 phút)

Viết lại “Review chậm nên phải giao tiếp tốt hơn” thành:
- Tín hiệu và mẫu số.
- Giả thuyết nguyên nhân.
- Can thiệp nhỏ.
- Owner/timebox.
- Metric và guardrails.
- Điều kiện dừng hoặc điều chỉnh.

**Gợi ý:** thử WIP policy hoặc pairing, xem review queue age, item age, throughput và defects. Không yêu cầu reviewer trực chat 24/7.

### 21.5. Bài E – Tính tỷ lệ và diễn giải cẩn trọng (10 phút)

Phép thử giả định: 20/30 người hiểu đúng trước, 24/30 sau.

1. Tỷ lệ trước/sau?
2. Chênh lệch điểm phần trăm?
3. Mức tăng tương đối so với trước?
4. Có thể kết luận nhãn mới gây cải thiện không?
5. Nêu biến gây nhiễu.

**Đáp án:** **66,7% → 80,0%**, khoảng **+13,3 điểm phần trăm**; tăng tương đối **(24/20−1)×100% = 20%**. Không chứng minh nhân quả khi mẫu nhỏ, chưa kiểm nhóm người, cách hỏi, thiết bị, thời điểm.

### 21.6. Bài F – Đọc Kanban và work item age (15 phút)

Cuối ngày: Started cộng dồn = 40; Finished cộng dồn = 25; Doing = 4, Review = 8, Verify = 3. Năm item còn mở có age cao.

1. Tính WIP hai cách.
2. Dải nào dày nhất?
3. Có thể kết luận reviewer gây chậm không?
4. Nêu dữ liệu cần thêm.
5. Thử chính sách cải tiến nào?

**Đáp án:** WIP = **40−25 = 15** = **4+8+3**. Review có 8 item tại snapshot; chưa chứng minh nguyên nhân. Kiểm queue age, item history, blocked reasons, CI, size; thử hỗ trợ review trước khi kéo mới.

### 21.7. Bài G – CI xanh nhưng giá trị chưa có (15 phút)

CI và API tests đều xanh; học viên vẫn hiểu nhầm trạng thái, một số request timeout.

Hãy:
- Nêu giới hạn của CI.
- Viết một AC về PENDING.
- Viết một test về timeout.
- Chọn phương thức phản hồi người dùng.
- Nêu cách liên kết product feedback vào regression tests.

**Gợi ý:** test chỉ bảo vệ những quy tắc đã được mô tả; thêm tình huống không xác nhận giả, bảo mật và quan sát người dùng thực.

### 21.8. Bài H – Phân loại feedback và trách nhiệm (15 phút)

Có bốn tín hiệu:
1. “Chúng tôi muốn SMS.”
2. “PENDING hiển thị như đã được giữ chỗ.”
3. “Pipeline đỏ với mọi PR.”
4. “Ba story chờ review quá hai ngày.”

Chọn product/technical/flow feedback, cách kiểm chứng, owner, mức khẩn và guardrail.

**Gợi ý:** lời đề xuất SMS không tự quyết giải pháp; vấn đề trạng thái sai có thể cần bảo vệ người dùng ngay; CI đỏ cần gỡ chặn; Review dày cần điều tra workflow.

### 21.9. Bài I – Dọn Product Backlog theo feedback (20 phút)

Có 60 mục gồm 12 bug đã xác minh, 8 mục trùng, 20 ý kiến thiếu bối cảnh, 10 yêu cầu không phù hợp Product Goal, 10 giả thuyết có khả năng thử.

Thiết kế quy trình:
- Phân loại mức độ nghiêm trọng và đường incident.
- Gộp trùng mà vẫn lưu nguồn.
- Tìm dữ liệu cho ý kiến thiếu bối cảnh.
- Từ chối có lý do.
- Chọn thí nghiệm nhỏ và mốc kiểm chứng.
- Phản hồi cho bên gửi ý kiến.

Không tự động đưa cả 60 item vào Sprint kế tiếp.

### 21.10. Bài J – Thiết kế vòng học hai Sprint (25 phút)

Chọn một vấn đề: story không đạt DoD, Review band dày, người dùng không có mặt trong Review hoặc action Retro lặp qua ba Sprint.

Hãy lập:
1. Mục tiêu và baseline.
2. Một giả thuyết.
3. Một thay đổi nhỏ có owner.
4. Feedback về sản phẩm, kỹ thuật và flow.
5. Guardrails.
6. Điều kiện giữ/chỉnh/dừng.
7. Biến gây nhiễu và cách báo kết quả.

**Đáp án định hướng:** có **thay đổi thực và đo lại**, không chỉ định lịch họp mới.

### 21.11. Bài K – Phản biện dashboard “Agile 100%” (20 phút)

Dashboard ghi:
- 100% Scrum events tổ chức.
- 98% người tham dự.
- 120 story points hoàn tất.
- 25 Retrospective actions “đã đóng”.

Nhưng chưa có dữ liệu người dùng, sáu item rất già chưa Done, CI thiếu integration tests, lỗi production tăng.

Viết nhận xét công bằng:
- Vì sao số liệu nghi thức chưa đủ?
- Những metric cần xem thêm?
- Ai có quyền thay backlog hoặc WIP?
- Hai hành động nên ưu tiên trước?

**Gợi ý:** không đổ lỗi vì họp đủ; chỉ rõ thiếu evidence → decision → action → verification.

### 21.12. Bài L – Báo tin không như kỳ vọng cho stakeholder (15 phút)

Nhóm giao Increment đạt DoD nhưng giả thuyết sản phẩm bị dữ liệu người dùng bác bỏ. Lãnh đạo muốn báo “thành công” vì tất cả task đã đóng.

Viết một thông điệp nêu:
- Increment và chất lượng đã đạt.
- Bằng chứng người dùng.
- Điều đã học.
- Quyết định Product Backlog.
- Rủi ro và kế hoạch kiểm chứng tiếp.
- Giá trị của việc phát hiện giả thuyết sai sớm.

### 21.13. Thang tự đánh giá

| Năng lực | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Nhận diện nghi thức rỗng** | Chỉ đếm họp | Hiểu mục đích mỗi Scrum event | Chỉ ra chính xác chỗ feedback bị đứt |
| **Thu phản hồi** | Chỉ hỏi ý kiến chung | Có bằng chứng, ngữ cảnh | Kết hợp user, technical và flow feedback |
| **Quyết định** | Ghi nhận rồi để đó | Có owner, lý do, mốc | Biết khi nào thử/giữ/đổi/dừng |
| **Thực thi cải tiến** | Action chung chung | Can thiệp nhỏ và đo lại | Kiểm guardrails, tác dụng phụ |
| **Đọc dữ liệu** | Chỉ nhìn velocity/attendance | Outcome, WIP, age, chất lượng | Hiểu mẫu, chênh lệch điểm %, confounders |
| **Cộng tác** | Đổ lỗi cá nhân | Quan tâm hệ thống | Bảo vệ transparency và accountability |
| **Empiricism** | Chỉ làm đúng lịch | Kiểm tra và điều chỉnh | Có vòng học bền vững qua nhiều Sprint |

## 22. Biểu mẫu có thể dùng ngay

### 22.1. Phiếu tìm điểm đứt vòng phản hồi

~~~text
Sản phẩm / Product Goal:
Hạng mục / Increment:
Giả thuyết và tiêu chí thành công:
Quan sát, nguồn, mẫu và thời điểm:
Phản hồi thuộc product / technical / flow:
Điểm đứt: thu thập / diễn giải / quyết định / thực hiện / đo lại
Điều đã biết và giả định:
Decision owner:
Hành động, owner, deadline:
Guardrails:
Mốc kiểm chứng:
Cách đóng vòng với bên góp ý:
~~~

### 22.2. Phiếu Sprint Review hướng vào thích ứng

~~~text
Product Goal:
Increment thật sự Done:
Những thứ chưa Done và rủi ro:
Bối cảnh hoặc nhu cầu thay đổi:
Feedback người dùng/stakeholder:
Bằng chứng và điều chưa biết:
Các phương án:
Quyết định Product Owner:
PBI thêm/chỉnh/đổi thứ tự/dừng:
Ý kiến chưa làm và lý do:
Người kiểm chứng, mốc:
Nơi thông báo kết quả:
~~~

### 22.3. Phiếu Retrospective action

~~~text
Vấn đề hệ thống:
Baseline và định nghĩa metric:
Giả thuyết nguyên nhân:
Can thiệp nhỏ:
Owner và người hỗ trợ:
Thời hạn thử:
Primary metric:
Secondary metrics:
Quality/user/people guardrails:
Biến gây nhiễu:
Điều kiện dừng/chỉnh:
Mốc xem lại:
Kết quả thực và giới hạn:
Quyết định giữ/chỉnh/dừng:
~~~

### 22.4. Phiếu phản hồi người dùng

~~~text
Bối cảnh tác vụ và nhóm người dùng:
Họ muốn làm gì:
Hành vi quan sát được:
Phản hồi đã được phép ghi:
Nhu cầu, không chỉ giải pháp đề xuất:
Nguồn dữ liệu bổ sung:
Mức ảnh hưởng/rủi ro:
Giả thuyết nhóm:
Cách thử an toàn:
Decision owner:
Kết quả và thông báo:
Nguyên tắc bảo vệ dữ liệu:
~~~

### 22.5. Decision log ngắn

~~~text
Decision ID:
Feedback/PBI liên quan:
Mục tiêu:
Sự kiện đã biết:
Giả định:
Phương án:
Đánh đổi/rủi ro:
Người quyết:
Lý do:
Action/owner/deadline:
Metric hoặc test kiểm chứng:
Review trigger:
Bên cần thông báo:
~~~

### 22.6. Dashboard kiểm tra vòng học

~~~text
Khoảng dữ liệu, định nghĩa item và mục tiêu:
Increment Done:
Outcome từ người dùng:
Các feedback quan trọng và nguồn:
Quyết định đã thay do phản hồi:
Retrospective actions đã làm và kết quả:
WIP, throughput, cycle time distribution:
Work item age và blocked reasons:
CI/test, defects và incidents:
Những dữ liệu thiếu hoặc thay đổi trong kỳ:
Điều chưa thể kết luận:
Lựa chọn tiếp: giữ / thử / đổi / dừng
Owner và ngày xem lại:
~~~

**Biểu mẫu không phải nghi thức mới bắt buộc.** Chỉ giữ thông tin đủ để hiểu, quyết định và học. Phản hồi nhỏ có thể xử lý trong ticket; quyết định liên quan bảo mật/dữ liệu cần quy trình và bằng chứng tương xứng.

## 23. Checklist: nhóm có thực sự kiểm tra và thích ứng?

**Mục tiêu và minh bạch**

- [ ] Product Goal và nhu cầu người dùng được nêu rõ.
- [ ] Sprint Goal hoặc mục tiêu luồng có ý nghĩa chứ không chỉ tên task.
- [ ] Item chưa đạt DoD không bị báo là Increment Done.
- [ ] Blocker, WIP, item age và lỗi được ghi trung thực.
- [ ] Metric có định nghĩa, mẫu số và kỳ quan sát.
- [ ] Người nêu rủi ro có thể báo thật, không bị đổ lỗi.

**Planning và Daily Scrum**

- [ ] Planning dùng dữ liệu, capacity và feedback kỳ trước.
- [ ] Developers được tham gia kiểm tra khả năng thực hiện.
- [ ] Sprint Goal định hướng lựa chọn, không phải nhãn trang trí.
- [ ] Daily Scrum giúp Developers điều chỉnh kế hoạch hướng mục tiêu.
- [ ] Blocker dẫn tới người hỗ trợ, không chỉ được nhắc lại.
- [ ] Thảo luận kỹ thuật chi tiết chuyển sang nơi phù hợp.
- [ ] Thông tin mới dẫn đến điều chỉnh minh bạch, không giao task ngầm.

**Sprint Review và Product Backlog**

- [ ] Review kiểm tra Increment và hướng Product Goal.
- [ ] Stakeholder/người dùng được tiếp cận để đưa feedback thực chất.
- [ ] Phân biệt sự kiện, giả thuyết, mong muốn và giải pháp.
- [ ] Feedback quan trọng có người tiếp nhận và quyết định.
- [ ] Product Backlog đổi, thử hoặc giữ có lý do.
- [ ] Có cách kiểm chứng kết quả sản phẩm sau thay đổi.
- [ ] Không nhầm Review với cổng phê duyệt release.

**Retrospective và phản hồi kỹ thuật**

- [ ] Action kỳ trước được kiểm trước khi tạo action mới.
- [ ] Có ít nhất một cải tiến cụ thể với giả thuyết, owner, mốc thử.
- [ ] Không tạo nhiều action vượt capacity.
- [ ] Vấn đề vượt quyền team có đường escalation.
- [ ] CI/tests cung cấp feedback kỹ thuật đủ sớm.
- [ ] Không bỏ test/DoD, bảo mật hoặc khả năng khôi phục để chạy KPI.
- [ ] WIP, age và item chưa Done được xem cùng cycle time completed items.
- [ ] Lỗi nghiêm trọng được xử lý ngay theo incident process.

**Quyết định và vòng học**

- [ ] Acknowledgment không bị coi là resolution.
- [ ] Không phải mọi đề xuất đều thành công việc; có triage/prioritization.
- [ ] Nhóm biết khi nào cần thử thêm và khi nào cần xử lý ngay.
- [ ] Có guardrails và điều kiện dừng/đảo thử nghiệm.
- [ ] Outcome, quality, flow và learning được nhìn cùng nhau.
- [ ] Không khẳng định nhân quả từ mẫu ngắn hoặc chỉ số đơn lẻ.
- [ ] Đã kiểm các khác biệt về loại item, quy tắc đo và bối cảnh.
- [ ] Feedback quan trọng đi qua các nhóm mà không mất Product Goal/DoD.
- [ ] Người góp ý được thông báo quyết định và kết quả khi phù hợp.
- [ ] Nhóm nêu được **một quyết định đã đổi nhờ feedback**.
- [ ] Sau hành động có dữ liệu kiểm kết quả hoặc kế hoạch thu tiếp.

## 24. Tổng kết: thành công không nằm ở số nghi thức đã làm

Một đội có thể tổ chức đúng lịch Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective và cập nhật Kanban mỗi ngày nhưng vẫn **không học hiệu quả** nếu giả định về người dùng không được kiểm chứng, lỗi kỹ thuật được phát hiện quá muộn, hàng chờ bị che, feedback không đi vào backlog, hoặc action Retro không thực hiện được.

Hãy hỏi năm câu:

1. **Increment nào đã thực sự Done và tạo giá trị hoặc bằng chứng học tập?**
2. **Tín hiệu mới nào khác kỳ vọng của chúng ta?**
3. **Quyết định nào đã đổi, được giữ có lý do hoặc cần thử thêm?**
4. **Ai thực hiện điều đó, khi nào và với guardrails nào?**
5. **Sau thay đổi, kết quả đã được kiểm lại ra sao?**

**Nghi thức tạo cơ hội kiểm tra; phản hồi tạo thông tin; quyết định và hành động tạo thích ứng.** Khi nối được các vòng sản phẩm, kỹ thuật và dòng công việc, nhóm có thể dùng Scrum, Kanban và XP đúng mục đích: **phản hồi sớm, giao phần mềm có giá trị tăng dần, bảo vệ chất lượng và cải tiến liên tục dựa trên bằng chứng**.
