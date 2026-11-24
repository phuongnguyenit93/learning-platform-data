# Mở rộng cách làm dựa trên điều kiện thành công của thí điểm

Một công ty phát triển nền tảng học tập cho phép một nhóm thử **giới hạn công việc đang làm (WIP), chia user story nhỏ hơn, review sớm và triển khai liên tục** trong tám tuần. Nhóm báo cáo cycle time giảm, nhiều hạng mục đạt Done hơn và thành viên hài lòng. Lãnh đạo tuyên bố “thí điểm Agile thành công” rồi yêu cầu tất cả phòng ban áp dụng cùng một bảng Kanban, cùng giới hạn WIP và cùng mẫu họp ngay tháng sau.

Ba tháng tiếp theo, nhóm vận hành có sự cố khẩn liên tục không thể duy trì WIP giống nhóm sản phẩm; nhóm tích hợp đối tác có thời gian chờ phê duyệt dài; nhóm mới chưa có CI và test đáng tin; những người từng hỗ trợ thí điểm cũng không thể coaching cho tất cả cùng lúc. Báo cáo vẫn ghi “100% nhóm đã triển khai Agile”, nhưng **thời gian tới người dùng, chất lượng và khả năng hợp tác không cải thiện đồng đều**.

Vấn đề không nhất thiết là Scrum, Kanban hay Extreme Programming (XP) sai. Vấn đề là tổ chức đã **nhân rộng hình thức trước khi kiểm chứng điều kiện tạo ra kết quả**. Một thí điểm tốt không chỉ chứng minh một nhóm có thể làm theo phương pháp nào đó; nó giúp biết **thực hành nào giải quyết vấn đề gì, trong điều kiện nào, bằng bằng chứng nào và cần thay đổi gì trước khi áp dụng ở bối cảnh khác**.

Trong chương **Chuyển đổi Agile** của module **AGILE_DEVELOPMENT**, bài này hướng dẫn **mở rộng cách làm dựa trên điều kiện thành công của thí điểm**. Chủ đề gắn với mục tiêu module: hiểu giá trị, nguyên tắc Agile và thực hành **user story, Product Backlog, Scrum, Kanban, XP, phản hồi sớm, Increment tăng dần và đo lường dòng công việc** để chọn cách phối hợp thích hợp. Trọng tâm là **mở rộng năng lực tạo giá trị và học hỏi**, không phải chạy chiến dịch đổi tên chức danh, tăng số cuộc họp hay đạt tỷ lệ “adoption” đẹp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **thí điểm có mục đích học hỏi**, rollout công cụ và áp dụng Agile trên diện rộng.
2. Xác định **vấn đề, giả thuyết, ranh giới và điều kiện thành công** trước khi bắt đầu một pilot.
3. Chọn bộ bằng chứng cân bằng giữa **outcome người dùng, flow, chất lượng, độ tin cậy, sức khỏe nhóm và khả năng duy trì**.
4. Tránh suy luận sai từ chỉ số đẹp, mẫu nhỏ, đội thí điểm đặc biệt hoặc thay đổi nhiều yếu tố cùng lúc.
5. Thiết kế các quyết định **tiếp tục thử, mở rộng có điều kiện, điều chỉnh, dừng hoặc quay lại giải quyết vấn đề nền**.
6. Đánh giá **mức độ tương đồng và khác biệt bối cảnh** trước khi mang thực hành từ nhóm A sang nhóm B.
7. Lập kế hoạch phát triển năng lực, quyền quyết định, phụ thuộc liên nhóm và hạ tầng kỹ thuật để mở rộng bền vững.
8. Phân biệt thực hành **cốt lõi cần giữ**, thực hành **có thể điều chỉnh** và **nghi thức không nên sao chép máy móc**.
9. Tạo kế hoạch nhân rộng theo từng đợt, có điều kiện dừng, phản hồi và rollback cách làm nếu gây hại.
10. Đọc một case study, thực hành viết pilot charter, decision record và đánh giá readiness của nhóm tiếp nhận.

## 2. Mở rộng Agile nghĩa là mở rộng năng lực, không phải nhân bản nghi thức

**Chuyển đổi Agile** thường bị hiểu thành chuyển từ “không Agile” sang một bộ quy trình cố định. Trong thực tế, thay đổi có ích hơn là:

- Giảm thời gian từ ý tưởng tới **phần mềm hoàn chỉnh có giá trị**.
- Tăng khả năng **phát hiện sai giả định và điều chỉnh sớm**.
- Làm rõ ưu tiên, người dùng, Product Goal và **quyền quyết định**.
- Giảm hàng đợi, WIP, chuyển giao không cần thiết và phụ thuộc bị che.
- Tăng chất lượng nhờ kiểm thử, review, tích hợp và vận hành xuyên suốt.
- Xây dựng **hợp tác, tự quản trong ranh giới và học hỏi bền vững**.

Một nhóm dùng Scrum, nhóm khác dùng Kanban có thể đều đang thực hành tốt nếu họ giao được Increment, quản lý rủi ro và cải tiến theo bối cảnh. Ngược lại, mười nhóm cùng có Daily Scrum lúc 9 giờ nhưng vẫn chờ phê duyệt hai tuần **không tự chứng minh tổ chức linh hoạt hơn**.

### 2.1. Ba tầng thay đổi cần phân biệt

| Tầng | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Hình thức thực hành** | Board, event, role, template, công cụ | Nhóm có triển khai được cách làm không? |
| **Năng lực vận hành** | Ưu tiên, giới hạn WIP, CI, kiểm chứng, tự quản, phối hợp | Nhóm có thể lặp lại cách làm mà không phụ thuộc người thúc đẩy? |
| **Kết quả tạo ra** | Cycle time, độ tin cậy, phản hồi người dùng, khả năng đạt mục tiêu | Cách làm có cải thiện điều tổ chức thật sự cần không? |

Không nên đánh đồng **“đã đào tạo”**, **“đã có board”**, **“đã đặt tên Product Owner”** với **“đã tạo năng lực Agile”**.

### 2.2. Nhân rộng thực hành khác với nhân rộng điều kiện

Nhóm thí điểm có một Product Owner dành thời gian đầy đủ, pipeline CI ổn định và quyền quyết định rõ. Nếu nhóm tiếp nhận thiếu những điều ấy, sao chép lịch họp và WIP limit chưa chắc tạo kết quả tương tự.

**Nhân rộng bền vững phải giải quyết cả điều kiện cho phép thực hành có tác dụng.**

## 3. Thí điểm nên bắt đầu từ một vấn đề quan sát được

Một pilot đáng tin cần câu hỏi rõ, không phải khẩu hiệu “thử Agile để hiện đại hóa”.

| Vấn đề ban đầu | Giả thuyết cải tiến có thể thử |
| --- | --- |
| Story gần cuối Sprint mới được review và test | Giảm kích thước lát cắt, review sớm và giới hạn WIP sẽ giảm hàng đợi |
| Thay đổi sản phẩm phải chờ quyết định qua nhiều cấp | Làm rõ thẩm quyền Product Owner và đường escalation sẽ giảm thời gian chờ quyết định |
| Code tích hợp cuối kỳ gây lỗi nhiều | CI, automated tests và tích hợp nhỏ thường xuyên sẽ phát hiện lỗi sớm |
| Người dùng chỉ phản hồi sau vài tháng | Phát hành Increment nhỏ và quan sát hành vi sẽ rút ngắn vòng học hỏi |
| Nhiều đội cùng phụ thuộc một nhóm nền tảng | Hiển thị dependency, chính sách phục vụ và cải thiện interface sẽ giảm blocked time |

### 3.1. Phân biệt vấn đề với giải pháp

“Chúng ta cần Scrum” là đề xuất phương pháp. “Các PBI thường chờ làm rõ yêu cầu 12 ngày trước khi bắt đầu” là một vấn đề có thể kiểm tra.

Thí điểm nên mô tả:

1. Ai đang gặp khó và **hậu quả với giá trị/người dùng**?
2. Hành vi, quy trình hoặc phụ thuộc nào có thể là nguyên nhân?
3. Thực hành nào có khả năng tác động tới cơ chế đó?
4. Điều gì sẽ chứng minh hoặc bác bỏ giả thuyết?
5. Nếu thực hành không hiệu quả, nhóm có thể **thay đổi điều gì**?

### 3.2. Không ép phải chứng minh phương pháp đã chọn là đúng

Một pilot có giá trị ngay cả khi cho thấy **Scrum theo cách tổ chức hiện tại không xử lý được luồng sự cố ngắt quãng**, hay Kanban không giải quyết vấn đề chỉ vì người phê duyệt chưa được trao quyền.

Kết luận “thực hành này chưa phù hợp trong điều kiện X” có thể giúp tránh một rollout tốn kém hơn nhiều.

## 4. Khái niệm cần tách bạch: pilot, rollout, scaling và transformation

| Khái niệm | Ý nghĩa thực dụng | Ví dụ |
| --- | --- | --- |
| **Pilot/thí điểm** | Thử một giả thuyết trong ranh giới có thể kiểm chứng, có tiêu chí và điều kiện dừng | Một nhóm áp dụng chia PBI nhỏ và review sớm trong tám tuần |
| **Rollout** | Đưa một thực hành/công cụ đã lựa chọn tới đối tượng tiếp nhận theo kế hoạch | Triển khai luồng CI và quy tắc review cho nhóm tiếp theo |
| **Scaling/mở rộng** | Phát triển năng lực phối hợp, học hỏi và giao giá trị ở nhiều nhóm/phạm vi | Nhiều nhóm xử lý dependency và điều chỉnh cách làm theo bối cảnh |
| **Transformation/chuyển đổi** | Thay đổi hệ thống quản trị, năng lực, cấu trúc, văn hóa và cách tạo giá trị trong thời gian dài | Chuyển ưu tiên từ đo “tỷ lệ bận” sang outcome và thời gian phản hồi |
| **Adoption** | Mức độ một thực hành được sử dụng, có thể quan sát | Có board và chính sách WIP |
| **Effectiveness** | Thực hành có đạt mục đích mong đợi không | WIP giảm cùng với cycle time/quality tốt hơn |

**Adoption là điều kiện quan sát một phần, không tự đồng nghĩa effectiveness.** Một báo cáo “95% đã học khóa Scrum” không trả lời khách hàng có nhận phần mềm sớm hơn hay không.

## 5. Bản đồ nhân quả giả định: từ thực hành tới kết quả

Trước khi đo, nên mô tả **cơ chế** mà nhóm kỳ vọng.

~~~mermaid
flowchart TD
    A["Vấn đề: PBI chờ review, kiểm thử cuối kỳ"] --> B["Giả thuyết: giảm kích thước lát cắt, giới hạn WIP"]
    B --> C["Thực hành: review sớm + CI + phối hợp kiểm thử"]
    C --> D["Tín hiệu trung gian: queue time, blocked time giảm"]
    D --> E["Kết quả: nhiều Increment Done sớm, cycle time bớt kéo dài"]
    E --> F["Outcome: người dùng nhận và phản hồi giá trị sớm hơn"]
    G["Điều kiện: PO rõ ưu tiên, test và quyền review sẵn sàng"] --> C
    H["Guardrail: lỗi, bảo mật, quá tải, độ tin cậy"] -.-> C
    H -.-> E
    I["Bằng chứng từ pilot"] --> J{"Mở rộng, điều chỉnh, thử thêm hay dừng?"}
    D --> I
    E --> I
    F --> I
~~~

### 5.1. Cơ chế thay đổi giúp biết cần giữ điều gì

Nếu giả thuyết là **“review sớm giảm thời gian chờ và phát hiện sai thiết kế”**, điều quan trọng có thể là **review các thay đổi nhỏ trong khi ngữ cảnh còn mới**. Việc có đúng ba cột “Ready / Doing / Done” hay một công cụ cụ thể **không nhất thiết là yếu tố quyết định**.

### 5.2. Một chỉ số cải thiện không tự xác nhận cơ chế

Nếu cycle time giảm sau pilot, có thể do:

- Chia PBI nhỏ hơn.
- Ít sự cố hơn vì mùa vụ.
- Chuyển những item khó sang nhóm khác.
- Thay đổi ranh giới bắt đầu/kết thúc.
- Thêm một chuyên gia review trong thời kỳ thử.

Phải xem **dữ liệu về cơ chế, thay đổi bối cảnh và phản hồi định tính** trước khi nói “đặt WIP limit đã gây ra toàn bộ mức giảm”.

## 6. Chọn phạm vi thí điểm: vừa đủ thử, không thiên lệch cực đoan

Một nhóm thí điểm nên **đủ điều kiện thực hiện thay đổi và quan sát kết quả**, đồng thời có bối cảnh liên quan với những nhóm định nhân rộng.

### 6.1. Những tiêu chí chọn pilot

| Tiêu chí | Vì sao quan trọng | Câu hỏi |
| --- | --- | --- |
| Vấn đề thật có bằng chứng | Tránh chạy chiến dịch hình thức | Đang có hàng đợi/lỗi/feedback chậm nào? |
| Ranh giới công việc rõ | Đo được trước và sau | Tính từ đâu tới đâu, loại item nào? |
| Khả năng thay đổi cách làm | Pilot có thể tác động vào vấn đề | Nhóm có quyền điều chỉnh WIP, review, backlog? |
| Khách hàng hoặc stakeholder có thể phản hồi | Biết outcome chứ không chỉ output | Ai xác nhận giá trị và khi nào? |
| Năng lực kỹ thuật tối thiểu | Không mắc kẹt chỉ do hạ tầng thiếu | Có build/test/CI đủ để thử không? |
| Bối cảnh có thể mô tả | Biết nơi có thể áp dụng | Độ lớn, phụ thuộc, loại công việc, mức rủi ro? |
| Mức độ an toàn thử nghiệm | Hạn chế ảnh hưởng người dùng | Thực hành thay đổi có thể rollback/điều chỉnh? |
| Mức hỗ trợ có thể tái tạo | Tránh “pilot siêu được ưu ái” | Coach và chuyên gia có thể hỗ trợ nhiều nhóm không? |

### 6.2. Tránh “chỉ chọn đội mạnh nhất”

Nếu một nhóm vốn có Product Owner giỏi, ít phụ thuộc và hạ tầng hiện đại đạt kết quả cao, đó có thể là **thí điểm về trường hợp thuận lợi**, không đại diện tổ chức. Không cần cố chọn đội yếu nhất để “công bằng”; cần **ghi lại đặc điểm lựa chọn và giới hạn khái quát**.

### 6.3. Tránh pilot không có quyền thay đổi

Một nhóm bị yêu cầu giữ mọi quy trình phê duyệt cũ nhưng bị chấm điểm “đã dùng Agile hiệu quả chưa” khó tạo kết luận về Agile. Nếu nguyên nhân nằm ở hệ thống ngoài nhóm, pilot phải bao gồm **người có quyền tháo rào cản** hoặc mô tả thẳng rằng phạm vi thử bị giới hạn.

## 7. Điều kiện thành công phải được xác lập trước khi nhìn kết quả

**Success criteria** là các điều kiện giúp người ra quyết định biết pilot có đủ bằng chứng để **tiếp tục, mở rộng, sửa đổi hay dừng**. Nếu đến cuối pilot mới chọn những số tăng đẹp nhất, việc đánh giá dễ trở thành **chứng minh điều đã muốn tin từ trước**.

### 7.1. Năm nhóm điều kiện cần cân nhắc

| Nhóm | Ví dụ bằng chứng | Vai trò |
| --- | --- | --- |
| **Outcome/giá trị** | Người học đăng ký thành công hơn; phản hồi được xử lý sớm hơn | Pilot có giải quyết mục tiêu sản phẩm? |
| **Flow/delivery** | WIP, throughput, cycle time, work item age, chờ review | Cơ chế luồng có cải thiện? |
| **Quality/reliability** | DoD, lỗi lọt, lỗi nghiêm trọng, CI, incident | Không tăng tốc bằng bỏ kiểm chứng |
| **People/collaboration** | Quyền quyết định, khả năng tự quản, chia sẻ kiến thức, quá tải | Cách làm có duy trì được với con người thật? |
| **Readiness/transferability** | Thực hành có hướng dẫn, người hỗ trợ, điều kiện tiên quyết và cách điều chỉnh | Có đủ điều kiện cho nhóm khác thử? |

Không cần tạo 30 KPI. Chọn **một số tín hiệu chính**, cùng guardrail và bằng chứng định tính phù hợp mục tiêu.

### 7.2. Mục tiêu và guardrail khác nhau

Ví dụ:

> **Mục tiêu:** Giảm thời gian chờ review và tăng khả năng hoàn tất lát cắt có giá trị.
>
> **Guardrail:** Không tăng lỗi nghiêm trọng sau phát hành; không hạ DoD; không gây quá tải kéo dài; không làm giảm khả năng hỗ trợ người dùng.

Một nhóm tăng throughput bằng cách đánh dấu “code complete” là Done **không đạt điều kiện thành công**, dù số lượng thẻ đã tăng.

## 8. Viết tiêu chí thành công có khả năng bác bỏ giả thuyết

Tiêu chí **“cảm thấy Agile tốt hơn”** có thể dùng làm tín hiệu ban đầu nhưng khó hướng dẫn quyết định. Tiêu chí rõ cần định nghĩa **đơn vị đo, phạm vi, mốc ban đầu, thời gian, điều kiện chất lượng và khi nào không đạt**.

### 8.1. Ví dụ scorecard thiết kế trước pilot

Tất cả số dưới đây **là ví dụ giả định**, không phải mức chuẩn Agile áp dụng cho mọi đội.

| Mục tiêu kiểm chứng | Baseline giả định | Điều kiện xem là tín hiệu tốt | Guardrail/giới hạn |
| --- | --- | --- | --- |
| Giảm chờ review | Trung vị 3 ngày | Trung vị xuống khoảng 2 ngày hoặc thấp hơn trong mẫu đủ đại diện | Chất lượng review không giảm |
| Giảm tuổi item mở | Nhiều item trên 12 ngày | Ít item có age cao hơn SLE phù hợp, nguyên nhân được xử lý | Không reset ngày bắt đầu để làm đẹp |
| Giao lát cắt đạt DoD | Hầu hết PBI Done cuối Sprint | Có PBI thực sự Done từ giữa Sprint | Không chia giả/hạ DoD |
| Bảo vệ chất lượng | Lỗi nghiêm trọng sau release trung bình 2/kỳ | Không tăng, tốt hơn nếu giảm có bằng chứng | Mẫu ít lỗi cần quan sát dài hơn |
| Cải thiện hợp tác | Review phụ thuộc một người | Có người dự phòng và quy tắc review khả thi | Không buộc người thiếu kỹ năng phê duyệt |
| Tính lặp lại | Chỉ coach biết cách vận hành | Nhóm tự giải thích chính sách, duy trì sau khi coach giảm hỗ trợ | Không phụ thuộc hỗ trợ không thể nhân rộng |

### 8.2. Không biến số mục tiêu thành hợp đồng tuyệt đối

“Trung vị review dưới 2 ngày” là **mốc giả định để học**, không tự động là điều kiện sa thải hay phạt thưởng. Nếu nhóm phát hiện một rủi ro nghiêm trọng cần thêm review và trung vị tăng tạm thời, **cần diễn giải trong bối cảnh**.

### 8.3. Một success criterion có thể mang tính định tính

Ví dụ “người mới có thể giải thích chính sách WIP và tự xác định khi nào cần swarming” có thể kiểm chứng bằng quan sát hoặc phỏng vấn theo tình huống. Không cần bịa điểm số 0–100 nếu dữ liệu định tính phù hợp hơn.

## 9. Thiết kế baseline trước khi can thiệp

Baseline là **điểm tham chiếu**, không phải một con số được chọn tùy ý để làm pilot trông thành công.

### 9.1. Những điều phải ghi rõ

- Khoảng thời gian lấy dữ liệu và tính mùa vụ.
- Nhóm loại việc: PBI sản phẩm, bug, incident, hỗ trợ, hạ tầng.
- Định nghĩa **bắt đầu và Done** của một item.
- Kích thước/độ khó và cách chia item qua từng kỳ.
- Quy tắc WIP, blocked, hủy và reopen.
- Thay đổi nhân sự, phụ thuộc, công cụ hoặc chính sách có thể ảnh hưởng số.
- Độ tin cậy event và khả năng truy vết.
- Cách lấy phản hồi định tính, ai được phỏng vấn.

### 9.2. Ví dụ baseline dễ gây hiểu sai

Trước pilot, nhóm tính cycle time từ **bắt đầu PBI tới đạt Definition of Done**. Sau pilot, hệ thống dashboard lại tính từ **bắt đầu code tới merge**, bỏ cả kiểm thử. Số cycle time giảm rất mạnh, nhưng thực chất **đã đổi thước đo**, không thể dùng để kết luận cải tiến.

### 9.3. Nếu không có dữ liệu lịch sử thì sao?

Không nên tạo baseline giả từ trí nhớ rồi ghi như dữ liệu đáng tin. Có thể:

1. Thu dữ liệu trong một giai đoạn ngắn trước thay đổi nếu rủi ro cho phép.
2. Ghi rõ baseline hạn chế hoặc thiếu.
3. Dùng số liệu định tính và đo từ thời điểm bắt đầu thử.
4. So sánh thay đổi **trong cùng định nghĩa** qua nhiều chu kỳ.
5. Trình bày mức độ chắc chắn thấp hơn khi ra quyết định nhân rộng.

## 10. Thiết kế pilot đủ học và đủ an toàn

Một pilot tốt có **ranh giới, người tham gia, thời gian và quyền hành động** rõ. Không phải mọi thí điểm đều cần A/B test, nhưng cần biết **cách nào kiểm chứng giả thuyết và loại bỏ lời giải thích thay thế ở mức hợp lý**.

### 10.1. Những lựa chọn thiết kế

| Cách thử | Có ích khi | Giới hạn |
| --- | --- | --- |
| Trước/sau trong cùng nhóm | Có baseline và điều kiện tương đối giống | Dễ bị ảnh hưởng sự kiện khác, mùa vụ |
| Thử ở hai nhóm tương đồng | Cần nhìn khác biệt trong bối cảnh gần nhau | Nhóm không hoàn toàn tương đương, dễ lan truyền thực hành |
| Rollout từng đợt | Có thể quan sát thay đổi ở nhóm tiếp theo | Tác động thời gian và lựa chọn nhóm |
| Quan sát định tính có cấu trúc | Muốn hiểu nguyên nhân blocker hoặc trải nghiệm | Không tự chứng minh mức ảnh hưởng phổ quát |
| Thử nghiệm hạ tầng/CI kỹ thuật | Có check cụ thể đo trước/sau | Chưa đủ kết luận outcome người dùng |

### 10.2. Giữ an toàn cho người dùng và người làm việc

Pilot về cách phối hợp **không được yêu cầu bỏ kiểm thử, bỏ quyền truy cập hoặc cố tạo sự cố thật** để đo mức cải thiện. Nếu thử một pipeline mới, cần giữ gate bắt buộc và phương án quay lại khi công cụ không tin cậy.

Tương tự, không ép Developers phải tăng giờ làm để “chứng minh cách làm mới thành công”. **Nhịp làm việc bền vững là điều kiện của kết quả tốt**, không phải phần phụ.

### 10.3. Thời lượng thử phải gắn với câu hỏi

Một tuần có thể đủ để thấy **lệnh build mới hoạt động**, nhưng không đủ để khẳng định lỗi sau production giảm bền vững hoặc văn hóa hợp tác đã thay đổi. Chọn thời lượng dựa trên **số chu kỳ cần quan sát, tốc độ tạo kết quả và rủi ro**, không chỉ lịch chiến dịch đào tạo.

## 11. Pilot charter: hợp đồng học hỏi thay vì lời hứa triển khai

**Pilot charter** là bản thỏa thuận ngắn giúp mọi bên biết **cái gì đang thử, vì sao, bằng chứng nào cần có và ai có quyền quyết định sau thử nghiệm**.

### 11.1. Mẫu có thể sử dụng

~~~text
TEN THI DIEM:
SAN PHAM / NHOM / RANH GIOI CONG VIEC:
VAN DE THUC TE VA BANG CHUNG BAN DAU:
OUTCOME MONG MUON:
GIA THUYET NGUYEN NHAN:

THUC HANH THU:
- Vi du: Lat cat user story nho, WIP limits, review som, CI, DoD
NHUNG THUC HANH / CHAT LUONG KHONG DUOC BO:
RANH GIOI TRONG / NGOAI PILOT:

BASELINE VA DO TIN CAY:
- Khoang thoi gian:
- Cach tinh va nguon:
- Yeu to boi canh:

SUCCESS CRITERIA:
- Outcome:
- Flow:
- Quality / reliability:
- People / collaboration:
- Kha nang duy tri / chuyen giao:

GUARDRAILS VA DIEU KIEN DUNG:
NGUOI CO QUYEN QUYET DINH:
CAI GI CO THE DIEU CHINH TRONG THI DIEM:
NGAY KIEM TRA GIUA KY / CUOI KY:
PHUONG AN SAU PILOT:
- Mo rong co dieu kien / Thu them / Dieu chinh / Dung
~~~

Mẫu không phải artifact bắt buộc của Scrum/Kanban/XP; hãy dùng **mức chi tiết đủ cho rủi ro**. Đối với một thử nghiệm nội bộ nhỏ, một trang có thể đủ.

## 12. Điều kiện thành công về dòng công việc

Các thước đo Kanban giúp hiểu **việc thật sự đi qua hệ thống** chứ không chỉ bao nhiêu người đang bận.

| Chỉ số | Câu hỏi | Điều kiện để so sánh |
| --- | --- | --- |
| **WIP** | Có bao nhiêu item đã bắt đầu nhưng chưa hoàn tất? | Ranh giới luồng và chính sách trạng thái |
| **Throughput** | Bao nhiêu item đạt Done trong mỗi khoảng thời gian? | Đơn vị item, độ lớn/loại việc gần tương đồng |
| **Work item age** | Item đang mở đã đi qua luồng bao lâu? | Cùng mốc bắt đầu và quy tắc xử lý blocker |
| **Cycle time** | Các item đã Done mất bao lâu? | Cùng mốc bắt đầu/kết thúc và DoD |
| **Queue/blocked time** | Công việc chờ review, test, quyết định ở đâu? | Nhãn chờ phản ánh thực tế, không đổi cột để che |

### 12.1. Chỉ nhìn trung bình là chưa đủ

Ví dụ cycle time của tám PBI là **2, 3, 4, 4, 5, 6, 7, 18 ngày**. Phần lớn item hoàn tất nhanh nhưng có một item mất 18 ngày. **Trung bình** có thể bị kéo bởi item đuôi dài, còn **trung vị** có thể bỏ qua trải nghiệm của những item bị kẹt. Cần xem **phân phối, tuổi item đang mở và nguyên nhân cụ thể**.

### 12.2. Little's Law không phải máy tăng tốc

Trong một hệ thống ổn định tương đối, có thể xem gần đúng:

\[
\text{WIP trung bình} \approx \text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Nếu tốc độ hoàn tất không đổi, **đẩy thêm công việc vào luồng** thường làm tăng WIP và thời gian chờ, không tự tạo thêm giá trị. Công thức cần **ranh giới nhất quán, dòng vào/ra ổn định tương đối và dữ liệu đủ đại diện**; không lấy nó làm KPI cá nhân.

### 12.3. Chỉ số đẹp có thể đến từ chia giả item

Nếu pilot chia một PBI thành mười task “viết API”, “tạo entity”, “tạo button” và tính chúng là mười Increment, throughput sẽ tăng theo cách đếm nhưng **người dùng chưa nhận hành trình có ích**. Phải xác định **Done là trạng thái chất lượng thật** và kết hợp outcome.

## 13. Điều kiện thành công về người dùng và giá trị

Thí điểm thay cách làm chỉ có ý nghĩa đối với tổ chức khi nó **cải thiện cách giao giá trị**, trực tiếp hoặc gián tiếp.

### 13.1. Ví dụ luồng đăng ký workshop

Một user story:

> “Là học viên đủ điều kiện, tôi muốn đăng ký workshop còn chỗ để có một vị trí xác nhận đáng tin.”

Bằng chứng cần kết hợp:

- Người dùng có thể hoàn tất hành trình đăng ký hợp lệ.
- Tình trạng xác nhận đúng với nguồn dữ liệu.
- Người dùng hiểu trạng thái và ít phải hỏi Support.
- Nhóm nhận phản hồi và sửa những vướng mắc trong một khoảng hợp lý.
- Các thay đổi không làm giảm độ tin cậy, phân quyền hoặc tính đúng.

### 13.2. Một outcome có định nghĩa

\[
\text{Tỷ lệ hoàn tất đăng ký}
=\frac{\text{Số hành trình bắt đầu hợp lệ có đăng ký được xác nhận}}
{\text{Tổng hành trình bắt đầu hợp lệ}}\times100\%.
\]

Phải xác định retry, đăng ký trùng, trường hợp hết chỗ, hành trình nhiều ngày, người không đủ điều kiện và sai khác sự kiện frontend/backend. **Số click không tự đồng nghĩa số đăng ký thành công**.

### 13.3. Outcome thay đổi có thể do nhiều nguyên nhân

Một cải tiến giao diện, chiến dịch truyền thông, số workshop còn chỗ hoặc độ ổn định hạ tầng cùng lúc có thể làm conversion thay đổi. Không được tuyên bố **“chuyển sang Scrum làm conversion tăng 15%”** chỉ vì hai sự kiện xảy ra cùng thời kỳ.

Trong khi không thể quy nhân quả chắc chắn, nhóm vẫn có thể ra quyết định dựa trên **bằng chứng hiện có, mức rủi ro và điều cần kiểm tra tiếp**.

## 14. Điều kiện thành công về chất lượng và khả năng phát hành

Một pilot “nhanh hơn” nhưng tăng lỗi dữ liệu hoặc làm giảm kiểm thử chỉ đang **chuyển chi phí sang người dùng và vận hành**.

| Guardrail | Vì sao cần | Ví dụ bằng chứng |
| --- | --- | --- |
| **Definition of Done** | Increment phải có chất lượng thống nhất | PBI thật sự đạt DoD, không chỉ code complete |
| **Lỗi nghiêm trọng sau release** | Không chuyển rủi ro sang production | Phân loại severity và tác động |
| **Kiểm thử rủi ro cao** | Những lỗi quan trọng được phòng ngừa | Test giao dịch đồng thời, phân quyền |
| **Tín hiệu CI/test** | Biết thay đổi có phá kiểm chứng | Pipeline có độ tin cậy và xử lý flaky |
| **Vận hành/độ tin cậy** | Không đánh đổi tốc độ với gián đoạn | Error rate, latency, sự cố và khôi phục |
| **Bảo mật và riêng tư** | Bảo vệ người dùng, nghĩa vụ và niềm tin | Security review, không lộ dữ liệu, quyền đúng |
| **Sức chứa hỗ trợ** | Người dùng có thể được giúp khi lỗi | Ticket, runbook và kênh xử lý phù hợp |

### 14.1. Không coi ít bug được báo là thành công mặc định

Trong giai đoạn đầu của pilot, số lỗi **được phát hiện trước release** có thể tăng vì test/CI tốt hơn. Đó có thể là kết quả tích cực nếu lỗi lọt production giảm. Cần phân tích **thời điểm, severity, mức sử dụng và cách báo**.

### 14.2. Không hạ DoD để đạt điều kiện thử nghiệm

Nếu nhóm thay “Done khi tích hợp và test rủi ro” thành “Done khi Dev merge code” giữa pilot, cycle time có thể giảm giả nhưng **điểm kết thúc đã thay**. Thay đổi DoD có thể cần thiết vì học thêm về chất lượng, song phải được quản trị và giải thích; **không coi hai giai đoạn có ranh giới khác nhau là số đo trực tiếp tương đương**.

## 15. Điều kiện thành công về hợp tác và tự quản

Chuyển đổi Agile còn liên quan tới **cách ra quyết định và phối hợp**, không chỉ quy trình trên board.

### 15.1. Những tín hiệu định tính cần hỏi

- Product Owner và Developers có hiểu **Product Goal, Sprint Goal hoặc mục tiêu luồng** không?
- Nhóm có quyền xử lý blocker trong phạm vi trách nhiệm không?
- Các bên có đưa ra phản hồi bất lợi mà không sợ bị trừng phạt không?
- Những quyết định liên quan phạm vi, kiến trúc và chất lượng có đúng người phụ trách?
- Có bớt chuyển giao vô nghĩa và phụ thuộc một cá nhân không?
- Pairing, review và học hỏi có xảy ra hay chỉ còn báo cáo trạng thái?
- Mọi người có duy trì nhịp làm việc mà không tăng giờ làm kéo dài?

### 15.2. Cách hỏi tránh câu trả lời hình thức

Thay vì “Bạn có hài lòng với Agile không?”, hỏi:

> “Trong PBI gần đây nhất, điều gì làm bạn phải chờ? Ai có quyền tháo gỡ? Nếu có một lỗi quan trọng, bạn có thể báo ngay và nhận trợ giúp bằng cách nào? Việc mới có làm tăng số giờ ngoài lịch không?”

**Quan sát tình huống thật** giúp hiểu cơ chế hơn điểm số khảo sát duy nhất.

### 15.3. Không biến khảo sát thành công cụ giám sát cá nhân

Kết quả khảo sát ở nhóm nhỏ có thể dễ suy ra danh tính. Cần minh bạch mục đích, bảo vệ quyền riêng tư, tránh công khai thông tin cá nhân và **không dùng phản hồi bất lợi để trừng phạt người nói thật**.

## 16. Điều kiện thành công về khả năng duy trì sau khi coach rút lui

Một pilot có chuyên gia ngoài hỗ trợ hằng ngày có thể rất hiệu quả. Nhưng câu hỏi mở rộng quan trọng là:

> “Nếu coach hoặc sponsor không còn ở cạnh nhóm, **những cơ chế giúp kết quả tốt hơn còn hoạt động không?**”

### 16.1. Bằng chứng duy trì

| Điều kiện | Cách kiểm chứng |
| --- | --- |
| Chính sách làm việc được hiểu | Thành viên giải thích bằng ví dụ vì sao giới hạn WIP hoặc Done |
| Quyết định không phụ thuộc một người | Có người dự phòng và ranh giới quyền rõ |
| CI/test không là công cụ cá nhân | Nhiều người biết vận hành, xử lý lỗi và cải tiến |
| Cải tiến có nhịp | Nhóm tự nhận vấn đề và thử thay đổi trong Retrospective hoặc Kanban review |
| Kiến thức có thể truyền | Có onboarding, ADR/runbook hoặc ví dụ vừa đủ |
| Bằng chứng tiếp tục được xem | Nhóm dùng outcome, flow, quality để chọn hành động |
| Phụ thuộc được xử lý | Có cơ chế với platform, bảo mật, vận hành và stakeholder |

### 16.2. Dấu hiệu thành công “nhờ người hùng”

Nếu chỉ một Scrum Master bên ngoài biết điều phối Sprint, chỉ một Developer duy trì pipeline, hoặc lãnh đạo đích thân tháo mọi blocker cho team pilot, thì **khả năng nhân rộng chưa được chứng minh**.

Cần thử **giảm dần hỗ trợ đặc biệt**, quan sát nhóm tự điều hành trong ranh giới và ghi lại điều kiện cần phát triển ở đội khác.

## 17. Đánh giá bằng chứng: đừng chọn chỉ số có lợi nhất sau thử nghiệm

Đánh giá pilot nên tách:

1. **Điều đã quan sát:** Số liệu, hành vi, phản hồi với định nghĩa rõ.
2. **Điều chưa chắc:** Mẫu nhỏ, nhiễu, thay đổi bối cảnh và dữ liệu thiếu.
3. **Giả thuyết giải thích:** Vì sao kết quả có thể xảy ra?
4. **Quyết định:** Giữ, sửa, thử tiếp, mở rộng có điều kiện hay dừng?
5. **Điều kiện kiểm chứng tiếp:** Cần thấy gì ở nhóm hoặc giai đoạn sau?

### 17.1. Những nguồn sai lệch thường gặp

| Sai lệch | Ví dụ | Cách giảm kết luận sai |
| --- | --- | --- |
| **Selection bias** | Chỉ đội rất chủ động được chọn pilot | Ghi tiêu chí chọn; chọn nhóm tiếp theo có bối cảnh khác |
| **Hỗ trợ đặc biệt** | Coach, chuyên gia và lãnh đạo luôn ưu tiên team pilot | Ước lượng năng lực hỗ trợ có thể nhân rộng, thử giảm hỗ trợ |
| **Hiệu ứng mới lạ/được chú ý** | Thành viên tập trung hơn vì đang được quan sát | Theo dõi đủ thời gian và sau khi chương trình bớt nổi bật |
| **Mùa vụ** | Tuần pilot có ít yêu cầu hoặc ít incident | Phân tích loại việc và chu kỳ, so khoảng tương đồng |
| **Thay đổi đồng thời** | Cùng đổi CI, đội hình, công cụ và phạm vi | Ghi mọi thay đổi; tránh quy tác động cho một thực hành |
| **Thay định nghĩa đo** | “Done” chuyển từ đạt DoD sang merge PR | Cố định ranh giới hoặc công bố không so trực tiếp được |
| **Gaming chỉ số** | Chia giả PBI để throughput tăng | Kết hợp DoD, outcome và chất lượng |
| **Survivorship bias** | Chỉ kể các team thành công, không kể pilot dừng | Tổng hợp cả kết quả không thuận lợi |
| **Độ trễ outcome** | Giá trị người học chỉ thấy khi workshop diễn ra | Tách tín hiệu sớm và outcome cần chờ |
| **Phụ thuộc bên ngoài** | Nhà cung cấp API đột ngột ổn định hơn | Phân tích dependency và mốc thay đổi |

### 17.2. Đừng đánh đồng tương quan với nhân quả

Nếu số PBI Done tăng sau khi cài bảng mới, đó là **tương quan quan sát**, chưa đủ chứng minh bảng mới gây ra cải thiện. Có thể kiểm tra cơ chế qua **WIP, queue time, review, test và phỏng vấn**, hoặc so sánh với nhóm/cửa sổ thời gian phù hợp khi có thể.

### 17.3. “Chưa đủ bằng chứng” là quyết định hợp lệ

Đôi khi dữ liệu cho thấy một cơ chế có triển vọng nhưng **chưa biết có duy trì khi giảm hỗ trợ hoặc ở nhóm khác không**. Quyết định đúng có thể là **thử thêm một đợt hạn chế**, không phải rollout toàn công ty hoặc tuyên bố thất bại.

## 18. Cổng quyết định: khi nào nên nhân rộng, điều chỉnh hay dừng?

Trước khi bắt đầu pilot nên định nghĩa **ai đánh giá và những lựa chọn có thể xảy ra**, tránh tới ngày cuối mới phát hiện không ai có quyền quyết.

### 18.1. Ma trận quyết định theo bằng chứng

| Bằng chứng | Quyết định thường đáng cân nhắc | Điều kiện bổ sung |
| --- | --- | --- |
| Outcome/flow tốt hơn, guardrail giữ, nhóm tự duy trì, bối cảnh có thể mô tả | **Mở rộng có điều kiện** | Kiểm tra readiness nhóm tiếp theo và hỗ trợ cần thiết |
| Cơ chế tốt nhưng cần coach/CI chưa có ở nhóm khác | **Chuẩn bị điều kiện, thử ở nhóm tiếp theo** | Đầu tư nền tảng, đào tạo và quyền quyết định |
| Một số chỉ số tốt hơn, chất lượng/nhịp bền vững xấu đi | **Điều chỉnh hoặc dừng thực hành gây hại** | Ưu tiên bảo vệ người dùng và người làm việc |
| Kết quả chưa rõ vì mẫu nhỏ hoặc định nghĩa đổi | **Kéo dài/thiết kế lại phép thử** | Rõ chi phí thêm thời gian và câu hỏi cần trả lời |
| Không cải thiện vấn đề gốc dù làm đúng thực hành | **Đổi giả thuyết/phương án** | Điều tra nguyên nhân cấu trúc khác |
| Vấn đề chuyển thành không còn ưu tiên | **Dừng có chủ đích** | Ghi bài học và tái phân bổ năng lực |

### 18.2. Không cần “thành công tuyệt đối” mới học được

Một pilot phát hiện **nút thắt nằm ở quyết định liên phòng ban**, không phải thiếu Scrum event, vẫn rất có ích. Nó dẫn tới quyết định **thay quyền phê duyệt hoặc cơ chế dependency** trước khi nhân rộng nghi thức.

### 18.3. Cổng quyết định phải gắn với thẩm quyền

Scrum Team có thể tự cải tiến cách làm trong phạm vi trách nhiệm. Nhưng **mở rộng sang nhiều nhóm, thay ngân sách, cấu trúc quyền, nghĩa vụ bảo mật hoặc điều kiện lao động** có thể cần quyết định của người có thẩm quyền khác. Đừng để một dashboard tự động phê duyệt những thay đổi vượt quyền.

## 19. Từ “cách làm thành công” tới “điều kiện khiến nó thành công”

Đây là bước quan trọng nhất trước khi nhân rộng. Một thí điểm tốt thường có hai loại kết quả:

1. **Thực hành có tác dụng gì?** Ví dụ review sớm giúp giảm hàng đợi.
2. **Điều kiện nào cho phép thực hành phát huy tác dụng?** Ví dụ có đủ reviewer, test đáng tin, người có quyền quyết định và PBI đủ nhỏ.

Nếu chỉ sao chép loại thứ nhất, nhóm tiếp nhận có thể thất bại **dù mọi người làm đúng hướng dẫn**.

### 19.1. Ma trận cơ chế–điều kiện

| Thực hành trong pilot | Cơ chế cần giữ | Điều kiện cần kiểm tra khi chuyển | Có thể điều chỉnh |
| --- | --- | --- | --- |
| Giới hạn WIP | Tập trung hoàn tất, giảm hàng đợi | Có board phản ánh công việc thật, đường xử lý blocker | Con số WIP, cách nhóm cột |
| Chia PBI nhỏ | Nhận feedback sớm, giảm kích thước lô | Có Product Owner/người hiểu nghiệp vụ đủ khả năng làm rõ | Kỹ thuật chia lát cắt theo sản phẩm |
| Review sớm | Bắt sai thiết kế khi ngữ cảnh còn mới | Reviewer phù hợp, quyền và chính sách rõ | Pair review, async review, review đồng bộ |
| CI và test tự động | Phát hiện lỗi tích hợp sớm | Build lặp lại, môi trường và dữ liệu test | Công cụ và tầng test phù hợp |
| Sprint Review | Kiểm tra Increment và thích ứng Product Backlog | Có Increment Done và stakeholder có thể phản hồi | Cách trình bày, lịch tổ chức trong khung Scrum |
| Retrospective/cải tiến dòng | Học từ trở ngại và hành động nhỏ | Nhóm có khả năng thay đổi cách làm | Kỹ thuật facilitation, câu hỏi và nhịp phù hợp |
| Phát hành tăng dần | Kiểm chứng outcome nhanh hơn, hạn chế rủi ro | Guardrail, giám sát, quyền go/no-go | Feature flag, canary, pilot người dùng theo bối cảnh |

### 19.2. Những gì nên chuẩn hóa

Tổ chức có thể chuẩn hóa ở **mức nguyên tắc và interface phối hợp**, chẳng hạn:

- Điều kiện sản phẩm được gọi Done và những ràng buộc chất lượng tối thiểu.
- Cách minh bạch phụ thuộc và sự cố liên nhóm.
- Quyền ưu tiên Product Backlog và ra quyết định phát hành.
- Khả năng đo flow/outcome có định nghĩa rõ.
- Bảo mật, quyền riêng tư và yêu cầu kiểm toán có hiệu lực.
- Cơ chế cập nhật quyết định và phản hồi cải tiến.

**Không nhất thiết chuẩn hóa** mọi tên cột, mọi giờ họp, mọi quy tắc story points hay một phương pháp ước lượng cho tất cả nhóm.

### 19.3. Tách mục tiêu khỏi phương tiện

Nếu mục tiêu là **giảm thời gian chờ kiểm chứng**, có thể cần review sớm hoặc test automation. Ở một nhóm vận hành chủ yếu xử lý incident, cách tổ chức work item và chính sách expedite có thể khác nhóm làm PBI sản phẩm theo Sprint.

**Giữ nguyên lý giảm chờ và chất lượng, điều chỉnh phương tiện theo ngữ cảnh.**

## 20. Kiểm tra độ tương đồng của nhóm tiếp nhận

Đừng hỏi “Nhóm B có chịu làm giống nhóm A không?” trước khi hỏi “Nhóm B có bài toán và điều kiện gần giống A không?”.

### 20.1. Các chiều cần so sánh

| Chiều bối cảnh | Nhóm pilot A | Nhóm tiếp nhận B | Cần xác minh |
| --- | --- | --- | --- |
| **Loại công việc** | User story sản phẩm | Incident, yêu cầu hỗ trợ, tích hợp | WIP và cycle time có cùng nghĩa? |
| **Độ biến động** | Backlog tương đối ổn định | Nhiều việc khẩn ngắt quãng | Có cần chính sách expedite? |
| **Mức phụ thuộc** | Tự chủ phần lớn luồng | Chờ platform, bảo mật, đối tác | Có quyền tháo blocker? |
| **Chất lượng/tuân thủ** | Rủi ro dữ liệu trung bình | Dữ liệu nhạy cảm/kiểm toán chặt | Gate, evidence và thẩm quyền nào? |
| **Năng lực kỹ thuật** | CI, test và staging ổn | Môi trường test không đáng tin | Cần đầu tư trước khi áp dụng practices? |
| **Phản hồi người dùng** | Người học sử dụng thường xuyên | Người dùng nội bộ theo tháng | Outcome cần thời gian quan sát khác? |
| **Quy mô/đội hình** | Một nhóm sản phẩm rõ | Nhiều nhóm chung một hệ thống | Dependency và ownership thế nào? |
| **Sự sẵn sàng thay đổi** | Nhóm tình nguyện | Nhóm đang quá tải | Có thời gian đào tạo và quyền chọn phương án? |

### 20.2. Kết luận không nên là “copy” hoặc “không copy” đơn giản

Ví dụ:

> “Nhóm B có vấn đề hàng đợi review tương tự A, nên đáng thử chính sách review sớm. Tuy nhiên B có nhiều yêu cầu khẩn và phải dùng môi trường chia sẻ, vì vậy **không áp cùng WIP limit**, đồng thời cần sửa quyền ưu tiên và năng lực kiểm thử trước.”

Đây là **nhân rộng dựa trên điều kiện**, không phải ngoại lệ phá kỷ luật.

### 20.3. Đội không tương đồng vẫn có thể học

Một pilot về khả năng nhận feedback người dùng có thể truyền **nguyên tắc giả thuyết và kiểm chứng**, dù hình thức thử nghiệm của nhóm B là phỏng vấn nội bộ, còn nhóm A dùng dữ liệu sản phẩm. Điều cần giữ là **câu hỏi học hỏi và chất lượng bằng chứng**, không nhất thiết công cụ.

## 21. Readiness assessment: nhóm tiếp theo đã sẵn sàng thử ở mức nào?

**Sẵn sàng** không có nghĩa đạt một chứng chỉ hay hoàn tất mọi khóa đào tạo. Nó nghĩa là những điều kiện tối thiểu để **thực hành một cách an toàn, có khả năng học hỏi** đã hoặc có thể được chuẩn bị.

### 21.1. Sáu trụ cột readiness

| Trụ cột | Câu hỏi kiểm tra | Nếu còn thiếu |
| --- | --- | --- |
| **Mục tiêu và giá trị** | Có vấn đề thực và ai chịu trách nhiệm outcome? | Làm rõ nhu cầu/Product Goal trước |
| **Quyền quyết định** | Team có quyền điều chỉnh WIP, chia việc và xử lý blocker? | Làm rõ escalation và trách nhiệm |
| **Năng lực kỹ thuật** | Build, test, review, tích hợp có đủ tin cậy? | Đầu tư CI/test/môi trường sớm |
| **Minh bạch công việc** | Có ranh giới luồng, DoD và dependency hiện rõ? | Làm rõ trạng thái và chính sách |
| **Phản hồi và đo lường** | Có cách quan sát outcome/flow/quality? | Chốt định nghĩa và baseline khả dụng |
| **Học hỏi bền vững** | Team có thời gian, coaching, không bị trả đũa khi nêu vấn đề? | Tạo điều kiện tham gia và bảo vệ phản hồi thật |

### 21.2. Ba trạng thái quyết định thực dụng

- **Ready to experiment:** Có thể thử ngay một thay đổi nhỏ trong ranh giới an toàn.
- **Ready with enabling work:** Cần một số việc nền trước/đồng thời, như quyền review, CI và làm rõ Product Goal.
- **Not ready for this experiment:** Vấn đề hoặc điều kiện quá khác; nên chọn thí điểm khác hoặc giải quyết blocker cấu trúc trước.

Đây **không phải bảng xếp hạng đội mạnh/yếu**. Một team chịu trách nhiệm hệ thống nhạy cảm có thể cần chuẩn bị lâu hơn nhưng có năng lực chuyên môn cao.

### 21.3. Một bảng sẵn sàng minh họa

~~~text
NHOM TIEP NHAN:
VAN DE HO MUON GIAI QUYET:
THUC HANH CAN THU:

1. Outcome va nguoi quyet dinh:
   [ ] Ro  [ ] Can lam ro
2. Ranh gioi flow/DoD va dependency:
   [ ] Ro  [ ] Can lam ro
3. CI/test/moi truong:
   [ ] Du  [ ] Can dau tu
4. Nguoi co ky nang va thoi gian thuc hien:
   [ ] Du  [ ] Can bo sung
5. Co feedback nguoi dung va guardrail:
   [ ] Co  [ ] Can thiet ke
6. Co co che escalation / quyen:
   [ ] Ro  [ ] Can xac nhan

CAC DIEU KIEN KHAC PILOT GOC:
VIEC CAN LAM TRUOC KHI THU:
NGUOI CHIU TRACH NHIEM:
NGAY QUYET DINH / XEM LAI:
~~~

## 22. Thực hành nào của Scrum, Kanban, XP nên giữ theo bối cảnh?

Không nên hiểu mở rộng Agile là bắt mọi team chuyển sang **một khung duy nhất**.

### 22.1. Scrum trong nhóm phát triển sản phẩm

Scrum phù hợp khi có **Product Goal, Scrum Team, Sprint, Increment và nhịp kiểm tra/thích ứng** hữu ích. Với Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog.
- **Developers** chịu trách nhiệm kế hoạch tạo Increment và chất lượng theo Definition of Done.
- **Scrum Master** chịu trách nhiệm thúc đẩy hiệu quả của Scrum Team và giúp tổ chức áp dụng Scrum.
- **Sprint Goal** định hướng; scope có thể làm rõ/thương lượng với Product Owner trong Sprint mà không làm nguy hại mục tiêu hoặc giảm chất lượng.
- **Sprint Review** kiểm tra Increment và tiến độ tới Product Goal; **Retrospective** cải thiện cách làm.

**Không phải việc thêm chức danh “Scrum Master” vào sơ đồ tổ chức đã tạo ra những accountability đúng**. Cần kiểm tra quyền quyết định và điều kiện để các vai trò thực hiện trách nhiệm.

### 22.2. Kanban cho luồng công việc biến động

Kanban nhấn mạnh **trực quan hóa, giới hạn WIP, quản lý dòng, chính sách rõ và cải tiến bằng dữ liệu**. Một nhóm vận hành có nhiều ticket khẩn có thể cần chính sách lớp dịch vụ, đường xử lý incident và WIP khác nhóm PBI sản phẩm.

Giữ nguyên lý **tập trung hoàn tất và làm rõ điểm chờ**; đừng áp cứng “mỗi người tối đa một item” hoặc “tất cả nhóm phải dùng ba cột”.

### 22.3. XP cho phản hồi kỹ thuật nhanh và chất lượng

Các thực hành **TDD, CI, pair programming, refactoring, simple design và small releases** có thể giúp phát hiện lỗi sớm. Nhưng pilot có pipeline mạnh **không có nghĩa công cụ hoặc test pyramid có thể copy nguyên** cho mọi hệ thống.

Ví dụ một hệ thống dữ liệu legacy có thể cần **characterization tests, cải thiện CI từng bước và ranh giới refactor an toàn**, không yêu cầu viết lại toàn bộ module để theo khẩu hiệu “100% TDD từ ngày đầu”.

### 22.4. Một nhóm có thể kết hợp thực hành

Một Scrum Team có thể dùng bảng Kanban và WIP để hiểu luồng Sprint, đồng thời áp dụng TDD/CI và review sớm từ XP. Việc kết hợp cần giữ **tính đúng của framework khi tuyên bố đang sử dụng**, nhưng không cần coi các thực hành bổ trợ là đối thủ.

### 22.5. Framework không giải quyết mọi vấn đề hệ thống

Nếu phải xin quyền qua năm cấp để deploy, nhóm chỉ thay tên buổi họp **không thể tự giải quyết**. Có thể phải thay quản trị, trách nhiệm sản phẩm, hạ tầng và chính sách phụ thuộc với sự tham gia của lãnh đạo.

## 23. Nhân rộng qua dòng giá trị, không chỉ theo sơ đồ phòng ban

Một sản phẩm có thể đi qua **product discovery → backlog → development → security review → deployment → operations → user feedback**. Nhiều điểm nghẽn nằm **giữa các phòng ban**.

### 23.1. Bản đồ dòng giá trị minh họa

~~~mermaid
flowchart LR
    A["Nhu cầu người học"] --> B["Làm rõ giá trị / backlog"]
    B --> C["Phát triển + kiểm thử"]
    C --> D["Review bảo mật / tích hợp"]
    D --> E["Phát hành + vận hành"]
    E --> F["Dùng thật + hỗ trợ"]
    F --> G["Phản hồi / quyết định"]
    G --> B
    P["Platform / môi trường / CI"] -.-> C
    P -.-> D
    Q["Phê duyệt / thẩm quyền"] -.-> D
    Q -.-> E
~~~

### 23.2. Đừng “Agile hóa” một bước và giữ hàng đợi nguyên

Nếu Developers giao code trong hai ngày nhưng review bảo mật vẫn chờ ba tuần, **lead time tới người dùng** có thể gần như không đổi. Một pilot muốn cải thiện toàn luồng cần **mời đúng nhóm phụ thuộc và xác định ranh giới đo bao gồm bước chờ**.

### 23.3. Mô hình cộng tác giữa các nhóm

Các nguyên tắc hữu ích:

1. **Owner theo sản phẩm/dòng giá trị** đủ rõ để biết ai quyết ưu tiên.
2. **Interface và hợp đồng** giữa các nhóm dễ hiểu, có người duy trì.
3. **Chính sách yêu cầu hỗ trợ** và cấp độ khẩn rõ ràng.
4. **Dependency được hiển thị** trên bảng hoặc công cụ phù hợp.
5. **Dữ liệu về queue/blocked time** được xem cùng nhau.
6. **Ưu tiên hệ thống**, không tối đa số việc riêng của từng phòng.

### 23.4. Không tự kết luận tái cấu trúc tổ chức là bước đầu tiên

Có những trường hợp thay cấu trúc sẽ giúp giảm phụ thuộc, nhưng chi phí và rủi ro cũng lớn. Trước khi xáo trộn đội hình, nên kiểm tra **nguyên nhân chờ, quyền quyết định, khả năng tự phục vụ và cơ chế hợp tác**. Một thay đổi nhỏ như cho phép team tự dùng môi trường test có thể hiệu quả hơn thay toàn bộ sơ đồ quản lý.

## 24. Quản trị chuyển đổi: bảo vệ mục đích và quyền tự quản

Khi mở rộng, tổ chức thường cần một **cơ chế điều phối** để quyết định đầu tư, ưu tiên tháo trở ngại và theo dõi tác động. Nhưng điều phối không nên trở thành **một tầng phê duyệt mới cho từng PBI**.

### 24.1. Những trách nhiệm cần có ở cấp mở rộng

| Trách nhiệm | Câu hỏi quản trị |
| --- | --- |
| **Định hướng giá trị** | Mở rộng nhằm cải thiện mục tiêu sản phẩm/khách hàng nào? |
| **Quyết định đầu tư** | Hạ tầng, coaching, đào tạo, quyền và thời gian thử nghiệm lấy từ đâu? |
| **Chuẩn an toàn** | Guardrail nào áp dụng chung do quy định/tác động? |
| **Tháo rào cản liên nhóm** | Ai có quyền thay chính sách gây hàng đợi? |
| **Chất lượng bằng chứng** | Chỉ số có cùng định nghĩa, có bias và tác dụng phụ nào? |
| **Quyết định rollout** | Đội nào tiếp nhận, khi nào và với điều kiện nào? |
| **Phản hồi ngược từ nhóm** | Ai có quyền nêu cách làm không phù hợp và đề xuất dừng? |

### 24.2. Tách guardrail chung khỏi cách thực hiện địa phương

Ví dụ có thể yêu cầu mọi sản phẩm bảo vệ dữ liệu cá nhân, có năng lực audit phù hợp và có chính sách incident. Nhưng **cách chia board Kanban, thời điểm phối hợp hoặc công cụ test cụ thể** có thể khác.

**Chuẩn hóa kết quả an toàn và giao diện phối hợp khi cần; trao quyền lựa chọn phương tiện trong bối cảnh.**

### 24.3. Không dùng maturity score làm bảng xếp hạng con người

Một thang “Agile maturity 1–5” có thể hữu ích nếu diễn giải như **câu hỏi tự đánh giá để tìm chỗ cần hỗ trợ**. Nhưng nếu gắn thưởng/phạt lãnh đạo theo số team đạt “level 5”, các nhóm có thể đổi tên vai trò, tạo tài liệu hình thức và che vấn đề.

Ưu tiên **bằng chứng về dòng giá trị, chất lượng và tác động**, không phải tăng điểm maturity như mục tiêu tự thân.

## 25. Đầu tư vào enabling capabilities trước khi mở rộng

Nhiều thực hành chỉ tạo hiệu quả khi có **năng lực nền**. Đây là phần dễ bị bỏ qua khi lãnh đạo muốn rollout nhanh.

### 25.1. Những năng lực nền thường gặp

| Năng lực | Vì sao cần cho nhân rộng | Bằng chứng đã sẵn sàng |
| --- | --- | --- |
| **Product ownership** | Quyết định giá trị/phạm vi không treo vô hạn | Ưu tiên và feedback có người chịu trách nhiệm |
| **User discovery** | Thử giả thuyết trên nhu cầu thật | Có đường tiếp cận người dùng và đo outcome phù hợp |
| **CI/CD và test** | Increment nhỏ vẫn đáng tin | Build/test chạy được, gate quan trọng có chủ sở hữu |
| **Môi trường và dữ liệu thử** | Không tạo hàng đợi kiểm chứng lớn | Nhóm tự phục vụ hoặc có cơ chế phục vụ rõ |
| **DevSecOps/operations** | Release tăng dần an toàn | Alert, runbook, phân quyền, khôi phục |
| **Kiến thức/đào tạo** | Không phụ thuộc hero/coach | Quickstart, ADR, mentoring và người hỗ trợ |
| **Thẩm quyền phù hợp** | Nhóm xử lý blocker trong phạm vi | Decision rights/escalation đã thử |
| **Đo lường đúng mục đích** | Biết cải tiến thực hay gaming | Định nghĩa flow/outcome/quality và privacy |

### 25.2. Phân biệt đầu tư nền với trốn tránh thay đổi

Không nhất thiết đợi CI hoàn hảo mới được thử giới hạn WIP hoặc làm rõ backlog. Nhưng nếu pilot đã chứng minh **test chậm là nút thắt**, rollout mà không chuẩn bị năng lực test cho nhóm tiếp theo có thể thất bại **theo đúng điều đã biết**.

### 25.3. Ưu tiên hạ tầng theo nhu cầu thực

Nếu mười nhóm đều chờ một staging environment dùng chung, nên xem **năng lực self-service, môi trường cô lập và quy tắc sử dụng** trước khi tăng số coach dạy mọi người viết story card.

## 26. Nhân rộng từng đợt: từ một pilot tới nhiều bối cảnh

Mở rộng theo từng đợt giúp tổ chức **nhận phản hồi về độ chuyển giao** mà không đặt quá nhiều nhóm vào cùng một rủi ro.

### 26.1. Một lộ trình minh họa

| Giai đoạn | Phạm vi | Mục tiêu học hỏi | Điều kiện qua giai đoạn |
| --- | --- | --- | --- |
| **0. Chuẩn bị** | Nhóm pilot và người ra quyết định | Vấn đề thật, baseline, success criteria, quyền | Charter và guardrail rõ |
| **1. Pilot** | Một nhóm có ranh giới phù hợp | Cơ chế nào tạo cải thiện? | Bằng chứng đủ cho quyết định, rủi ro được kiểm soát |
| **2. Replication có điều chỉnh** | Một hoặc hai nhóm có bối cảnh gần nhưng không giống hệt | Điều gì giữ nguyên, điều gì phải đổi? | Outcome/flow/quality không suy giảm ngoài dự kiến |
| **3. Mở rộng có hỗ trợ** | Vài nhóm thuộc cùng dòng giá trị | Phụ thuộc và hạ tầng có chịu được? | Coaching, CI, quyền, đo lường và Support đủ |
| **4. Institutionalize** | Những nơi có vấn đề tương tự | Cơ chế ra quyết định và cải tiến có bền vững? | Không còn cần chiến dịch thúc ép, có feedback loop |
| **5. Xem lại định kỳ** | Toàn phạm vi áp dụng | Điều gì lỗi thời hoặc không còn phù hợp? | Có thể sửa/chấm dứt thực hành không hiệu quả |

Đây **không phải lộ trình bắt buộc**. Một tổ chức nhỏ có thể đi nhanh hơn; một hệ thống rủi ro cao cần thêm cổng an toàn.

### 26.2. Không mở rộng theo con số nhóm cố định

“Quý này phải nhân từ 1 lên 30 team” có thể là **mốc quản trị**, nhưng không chứng minh readiness. Nếu chỉ có hai người hỗ trợ kỹ thuật và một platform team đang quá tải, mở 30 thí điểm cùng lúc sẽ giảm khả năng học và sửa rủi ro.

### 26.3. Bài thử ở nhóm tiếp theo là một pilot mới có chủ đích

Khi nhóm B nhận thực hành từ A, vẫn cần:

- Vấn đề và baseline riêng của B.
- Rủi ro/guardrail riêng.
- Những thay đổi so với công thức A và lý do.
- Kế hoạch hỗ trợ và quyền quyết định.
- Mốc đánh giá, điều kiện dừng hoặc rollback cách làm.

**Nhân rộng theo bằng chứng là một chuỗi vòng học hỏi, không phải một lần sao chép tài liệu.**

## 27. Không nhân rộng vượt năng lực hỗ trợ và hấp thụ thay đổi

Một tổ chức có thể tạo thêm dashboard và buổi đào tạo nhanh hơn khả năng thay đổi **công cụ, kỹ năng, quyền và thói quen** của nhóm.

### 27.1. Những dấu hiệu quá tải chuyển đổi

- Nhiều thay đổi quy trình được công bố nhưng không có owner sửa vướng mắc.
- Coach phải dự hàng chục cuộc họp, chỉ còn nhắc nghi thức.
- Nhóm liên tục đổi board, tên cột hoặc định nghĩa Done.
- Product Owner tham gia quá nhiều team, không có thời gian làm rõ giá trị.
- CI/test và môi trường chưa đủ đáp ứng nhịp phát hành.
- Số buổi họp tăng, thời gian tập trung giảm.
- Team không được nêu cách làm nào không phù hợp.
- KPI tập trung “bao nhiêu team đã dùng Scrum” thay vì kết quả.

### 27.2. Giới hạn WIP của chính chương trình chuyển đổi

Agile khuyến khích quản lý **công việc đang làm**. Một chương trình thay đổi cũng có WIP:

| Công việc chuyển đổi | Khi nào nên bắt đầu thêm? |
| --- | --- |
| Coaching nhóm mới | Khi có người hỗ trợ đủ năng lực và lịch rõ |
| Triển khai CI hoặc công cụ quản lý | Khi có owner vận hành và hỗ trợ sau rollout |
| Thay chính sách phê duyệt | Khi người có quyền và bên chịu tác động tham gia |
| Mở rộng pilot | Khi đã đọc đủ bằng chứng và quyết định điều kiện áp dụng |
| Đào tạo bổ sung | Khi có cơ hội thực hành và phản hồi, không chỉ hoàn tất khóa |

Mục tiêu là **tạo thay đổi có thể hấp thụ**, không “triển khai nhiều hoạt động” để báo cáo đẹp.

## 28. Phát triển năng lực qua cộng đồng thực hành và người hỗ trợ

Để nhân rộng, tổ chức thường cần những người có khả năng **giải thích nguyên tắc, giúp nhóm tự cải tiến và thích nghi**, không chỉ người dạy sử dụng một công cụ.

### 28.1. Các cách truyền học hữu ích

- **Pairing/shadowing:** Người từ nhóm B quan sát và cùng làm một PBI với A.
- **Community of Practice:** Những người cùng chuyên môn chia sẻ test, backlog refinement, Kanban policies và bài học.
- **Internal coaching:** Người hiểu bối cảnh công ty giúp nhóm tự kiểm tra và thích ứng.
- **Playbook dạng lựa chọn:** Tài liệu nêu vấn đề, điều kiện áp dụng, ví dụ, chống chỉ định và cách kiểm chứng.
- **Guild kỹ thuật:** Hỗ trợ CI, security test, architecture và phát hành.
- **Office hours theo vấn đề:** Giải đáp blocker cụ thể, tránh biến hỗ trợ thành phê duyệt mọi chuyện.
- **Practice review:** Nhóm chia sẻ cái gì chưa phù hợp, thay vì chỉ kể thành tích.

### 28.2. Playbook nên có “khi nào không nên dùng”

Ví dụ một trang về giới hạn WIP nên chứa:

~~~text
THUC HANH: Gioi han WIP tai vung review
VAN DE GOC: Hang doi review phinh, cycle time dai
CO CHE KY VONG: Uu tien hoan tat item cu, tranh mo them viec

DIEU KIEN THU:
- Board phan anh dung luong viec
- Policy vao/ra va Done ro
- Nguoi review co ky nang, quyen va thoi gian

KHONG COPY MAY MOC:
- Con so WIP cua nhom pilot
- Ten cot va cong cu
- Cach xu ly expedite trong moi bối canh

DIEU CAN KHAO SAT:
- Co incident ngat quang khong?
- Loai item co chenhlech lon khong?
- Diem tac nghe co nam ngoai nhom khong?

BANG CHUNG CAN XEM:
- Queue time, age, cycle time, DoD, defects, feedback
GUARDRAILS:
- Khong ha review chat luong
- Khong ep nguoi thieu ky nang approve

NEU KHONG HIEU QUA:
- Kiem tra nut that va dieu kien
- Dieu chinh policy hoac thu giai phap khac
~~~

Playbook nên **dẫn tới quyết định phù hợp bối cảnh**, không biến nhóm khác thành bản sao của A.

### 28.3. Không tạo phụ thuộc vào “Agile champion” duy nhất

Người tiên phong có thể quan trọng ở giai đoạn đầu, nhưng phải **chia sẻ năng lực điều phối, đo lường, thiết kế thử nghiệm và xử lý blocker**. Nếu người đó nghỉ, nhóm tiếp nhận vẫn cần biết tại sao đang làm một thực hành, cách tự xem bằng chứng và ai có quyền sửa.

## 29. Kiểm tra ảnh hưởng tới văn hóa và cơ chế khuyến khích

Tổ chức có thể nói “ưu tiên hợp tác” nhưng vẫn thưởng cá nhân theo số commit và story points. Một chương trình Agile khó mở rộng nếu **chỉ số, quyền và chính sách nhân sự tạo động cơ ngược**.

### 29.1. Những mâu thuẫn cần phát hiện

| Tuyên bố mong muốn | Cơ chế cũ gây xung đột | Hướng xem lại |
| --- | --- | --- |
| Cùng hoàn tất PBI | Thưởng người bắt đầu nhiều task | Nhìn flow tới Done và kết quả nhóm |
| Phát hiện lỗi sớm | Phạt nhóm có nhiều bug được báo | Phân biệt lỗi phát hiện sớm và lỗi lọt |
| Phản hồi trung thực | Công bố bảng xếp hạng “team yếu nhất” | Dùng dữ liệu để hỗ trợ cải tiến |
| Tự quản | Mọi thay đổi WIP/ưu tiên đều xin phép ba cấp | Làm rõ quyền và guardrail |
| Tương tác và học hỏi | Lịch họp kín cả ngày, không có thời gian tập trung | Cân bằng async/sync và năng lực |
| Phát hành tăng dần | Một cổng release hàng quý không có ngoại lệ | Đánh giá rủi ro và chính sách phát hành phù hợp |
| Chất lượng liên tục | Tính Done khi chỉ merge code | Giữ DoD và kiểm thử trong lát cắt |

### 29.2. Đừng ép “Agile mindset” bằng khẩu hiệu

Nhân viên có thể ngại thử khi **sai giả thuyết sẽ bị phạt**. Một môi trường thực nghiệm cần:

- Quyền nêu blocker và kết quả không thuận lợi.
- Tôn trọng tiêu chuẩn an toàn và trách nhiệm nghề nghiệp.
- Mục tiêu chung đủ rõ để nhóm tự chọn cách đạt.
- Người quản lý tháo những rào cản vượt quyền team.
- Retrospective dẫn tới hành động, không chỉ nghi thức.

**An toàn khi phản hồi** không đồng nghĩa miễn trách nhiệm với hành vi thiếu cẩn trọng; nó giúp phát hiện rủi ro và giải quyết nguyên nhân hệ thống sớm hơn.

## 30. Quản trị bằng outcome và guardrail thay vì tỷ lệ áp dụng nghi thức

Một chương trình chuyển đổi có thể cần theo dõi tiến độ triển khai. Nhưng **“bao nhiêu team đã tạo board”** hoặc **“bao nhiêu người được đào tạo”** chỉ phản ánh hoạt động.

### 30.1. Bộ chỉ số cấp chương trình có ý nghĩa hơn

| Câu hỏi điều phối | Bằng chứng phù hợp | Giới hạn |
| --- | --- | --- |
| Những nhóm nào đang giải quyết vấn đề gì? | Pilot charter, problem statement | Không xếp hạng đội theo độ khó |
| Cơ chế nào tạo kết quả có lợi? | Flow, quality, outcome, quan sát bối cảnh | Không khẳng định nhân quả từ trước/sau đơn giản |
| Có tái tạo được trong bối cảnh khác? | Bằng chứng nhóm tiếp theo, điều chỉnh áp dụng | Không ép cùng giá trị WIP/velocity |
| Điều kiện nền đã sẵn sàng chưa? | CI, quyền, Product Ownership, coaching | Checklist không thay thực hành |
| Có tác dụng phụ không? | Lỗi, incident, quá tải, quyền riêng tư | Cần kênh báo bất lợi không bị trả đũa |
| Có tiếp tục cải tiến sau rollout? | Quyết định và thử nghiệm tiếp theo | Số buổi Retrospective không chứng minh cải tiến |

### 30.2. Không xếp hạng team bằng velocity

Story points là **thang ước lượng nội bộ**, không có chuẩn thống nhất giữa nhóm. Một team chấm 8 points cho PBI mà team khác chấm 3 points; ghép thành biểu đồ “đội nào nhanh hơn” là so những đơn vị không tương đương.

Tương tự, throughput phụ thuộc **cách chia item, chính sách Done và loại việc**. Cần kết hợp thông tin chất lượng và outcome để tránh làm đẹp số liệu.

### 30.3. Đo “adoption” chỉ khi biết sẽ dùng nó làm gì

Ví dụ thấy một nhóm **không dùng bảng WIP** có thể là dấu hiệu cần hỏi:

- Họ có vấn đề hàng đợi tương tự không?
- Họ đã có cách quản lý flow khác đủ tốt?
- Không được cấp quyền công cụ hay chưa hiểu mục đích?
- Việc áp WIP limit có thể gây rủi ro do luồng incident không?

Đừng chuyển quan sát “chưa adoption” thành kết luận “nhóm chống đối” khi **chưa xem bối cảnh**.

## 31. Case study xuyên suốt: thí điểm Agile tại nền tảng workshop

**Bối cảnh giả định:** Một công ty phát triển hệ thống quản lý workshop. Nhóm sản phẩm **A** thường hoàn tất nhiều code cuối Sprint nhưng chờ review, integration test và phản hồi người học. Nhóm có Product Owner, Developers với kỹ năng khác nhau và sự hỗ trợ từ QA/Operations. Một chương trình chuyển đổi quyết định thử trong **tám tuần**, trong đó **bốn tuần trước** dùng làm baseline và **bốn tuần sau** thử cách làm mới. Với dữ liệu ít, đây chỉ là thí điểm học hỏi, không phải chứng minh thống kê mạnh.

### 31.1. Vấn đề gốc

Trước thí điểm:

- Nhiều PBI lớn như “hoàn thiện đăng ký workshop” không thể kiểm thử cho tới cuối Sprint.
- Review chờ một chuyên gia dữ liệu; QA nhận nhiều hạng mục cùng lúc.
- CI có, nhưng test đồng thời và phân quyền chưa đáng tin.
- Product Owner nhận phản hồi muộn từ Support.
- Developers mở việc mới vì muốn luôn bận thay vì giúp PBI gần Done.

**Giả thuyết:** Nếu nhóm làm rõ acceptance examples sớm, chia lát cắt dọc nhỏ, giới hạn WIP, review/tích hợp thường xuyên và giữ DoD, thì **thời gian hoàn tất và chờ kiểm chứng sẽ giảm**, người học nhận luồng đăng ký đúng sớm hơn mà không tăng lỗi hoặc quá tải.

### 31.2. Các thay đổi được thử

| Thay đổi | Người tham gia | Cơ chế kỳ vọng |
| --- | --- | --- |
| Refinement ngắn với ba góc nhìn nghiệp vụ–kỹ thuật–kiểm thử | PO, Developers, QA | Giảm hiểu sai và phát hiện rủi ro sớm |
| Chia PBI thành lát cắt có giá trị | Scrum Team | Có Increment Done từ giữa Sprint |
| Giới hạn WIP ở các trạng thái chính | Developers | Giảm bắt đầu mới khi item cũ còn chờ |
| Review PR nhỏ hơn trong ngày khi có thể | Developers, reviewer chuyên môn | Giảm queue time và phản hồi khi ngữ cảnh còn mới |
| Bổ sung integration tests rủi ro cao trong CI | Developers, chuyên môn test/data | Ngăn lỗi chỗ cuối và phân quyền lọt muộn |
| Theo dõi work item age và lý do blocked | Team | Tháo nút thắt thay vì đổ lỗi người làm |
| Phát hành lát cắt có kiểm soát và nhận phản hồi | PO, Operations, Support | Kiểm tra outcome và guardrail |

### 31.3. Dữ liệu quan sát giả định

Các giai đoạn đều được định nghĩa là **bốn tuần**. Dữ liệu sau chỉ để luyện cách đọc; không phải số thực của một nhóm hay ngưỡng tham chiếu ngành.

| Tín hiệu | Bốn tuần trước | Bốn tuần thí điểm | Diễn giải ban đầu |
| --- | ---: | ---: | --- |
| PBI thực sự đạt DoD | 16 | 22 | Số item hoàn tất tăng |
| Cycle time trung vị | 12 ngày | 8 ngày | Lát cắt đi qua luồng nhanh hơn |
| Cycle time nhóm item chậm (ví dụ phân vị cao theo cách đo nhất quán) | 20 ngày | 15 ngày | Phần đuôi có dấu hiệu bớt kéo dài |
| Thời gian chờ review trung vị | 3,5 ngày | 1,5 ngày | Cơ chế review sớm có tín hiệu |
| PBI đang mở ở cuối khoảng quan sát | 11 | 7 | WIP giảm |
| Lỗi nghiêm trọng lọt production ghi nhận | 2 | 1 | Chưa đủ mẫu để kết luận xu hướng bền vững |
| Hành trình đăng ký hợp lệ bắt đầu | 500 | 600 | Lượng sử dụng tăng |
| Hành trình được xác nhận thành công | 285 | 396 | Outcome mô tả cải thiện |
| Ticket hỏi “Tôi đã có chỗ chưa?” | 25 | 20 | Giảm về số tuyệt đối; cần chuẩn hóa theo sử dụng |
| Các ngày nhóm báo quá tải đáng kể | 7 | 4 | Tín hiệu bền vững, cần xác minh cách thu |

**Điều kiện quan trọng:** Trong pilot có một Product Owner dành thời gian nhiều hơn bình thường, coach hỗ trợ hai lần mỗi tuần và CI được sửa trong đợt đầu. Đây là **các yếu tố có thể tác động lớn tới kết quả**, không nên bị xóa khỏi câu chuyện.

### 31.4. Tính sự khác biệt ở output

Số PBI đạt DoD tăng từ 16 lên 22:

\[
\frac{22-16}{16}\times100\%=37{,}5\%.
\]

Con số mô tả **số item được đếm tăng 37,5%**, không chứng minh **năng suất nhóm tăng 37,5%**, vì kích thước PBI và kiểu công việc có thể khác, đặc biệt nhóm đang cố ý chia lát cắt nhỏ hơn.

### 31.5. Tính tỷ lệ hoàn tất đăng ký

Trước thí điểm:

\[
\frac{285}{500}\times100\%=57\%.
\]

Trong thí điểm:

\[
\frac{396}{600}\times100\%=66\%.
\]

Chênh lệch mô tả là **9 điểm phần trăm**. Đây là tín hiệu có triển vọng cho người học, nhưng **không đủ để khẳng định cách làm Agile gây ra chính xác 9 điểm phần trăm cải thiện**; cần kiểm tra số chỗ workshop, cơ cấu người học, chiến dịch truyền thông, độ ổn định backend và event quality.

### 31.6. Chuẩn hóa ticket theo lượng sử dụng

Nếu cùng một cách phân loại và cùng mẫu số hành trình hợp lệ, tỷ lệ ticket liên quan tới trạng thái trong các tập quan sát tương ứng là:

Trước:

\[
\frac{25}{500}\times100=5\ \text{ticket trên 100 hành trình}.
\]

Trong pilot:

\[
\frac{20}{600}\times100\approx3{,}33\ \text{ticket trên 100 hành trình}.
\]

Tín hiệu có vẻ tốt hơn, nhưng cần xác minh **một học viên có thể gửi nhiều ticket**, cách phân loại hỗ trợ không đổi và hành trình trong mẫu có đủ đại diện.

### 31.7. Cần phân biệt tín hiệu trung gian với outcome

Thời gian chờ review giảm gần giả thuyết ban đầu; đây là **tín hiệu về cơ chế**. Tỷ lệ đăng ký hoàn tất tăng; đây là **outcome quan sát**, có nhiều yếu tố khác ảnh hưởng. Lỗi nghiêm trọng 2 xuống 1 là **dữ liệu quá ít** để kết luận thay đổi chất lượng ổn định.

Kết luận thích hợp:

> “Thí điểm cho thấy dấu hiệu cải thiện flow và outcome trong bốn tuần được quan sát, đồng thời chưa thấy guardrail chất lượng xấu đi rõ ràng. Tuy nhiên còn hạn chế về mẫu, khả năng so sánh và hỗ trợ đặc biệt. Chúng ta nên **thử lặp lại có điều kiện tại nhóm tương đồng**, không công bố ngay một công thức áp cho toàn tổ chức.”

## 32. Quyết định sau pilot: mở rộng phần nào, chưa mở rộng phần nào?

**Nhóm A** đạt những điều kiện triển vọng, nhưng tổ chức đang cân nhắc ba nhóm tiếp theo:

- **Nhóm B:** Phát triển nội dung và luồng tìm kiếm workshop, có Product Owner rõ nhưng kiểm thử giao diện khá chậm.
- **Nhóm C:** Vận hành và hỗ trợ incident, nhiều việc khẩn bất định, không sử dụng Sprint như A.
- **Nhóm D:** Xử lý dữ liệu báo cáo có nghĩa vụ kiểm toán chặt, phải chờ hệ thống nguồn và phê duyệt.

### 32.1. So sánh quyết định theo bối cảnh

| Nhóm | Phần có thể học từ A | Điều kiện phải điều chỉnh/chuẩn bị | Quyết định thử |
| --- | --- | --- | --- |
| **B — sản phẩm gần giống** | Lát cắt nhỏ, review sớm, CI và WIP | Cải thiện test giao diện và quyền PO ưu tiên | Thử đợt 2 với baseline riêng |
| **C — vận hành/incident** | Trực quan hóa, WIP, age, giới hạn bắt đầu mới | Chính sách expedite, incident severity, on-call, không ép Sprint | Thiết kế pilot Kanban riêng theo luồng incident |
| **D — báo cáo/kiểm toán** | Làm rõ yêu cầu, kiểm chứng sớm, giảm chờ | Evidence, quyền phê duyệt, test dữ liệu, dependency | Chuẩn bị enabling work trước khi rollout rộng |

### 32.2. Những thứ không nên sao chép

- WIP limit **3** của A sang C khi C phải xử lý sự cố khẩn.
- Velocity/story points của A làm chỉ tiêu cho B hoặc D.
- Cùng thời lượng Sprint nếu luồng công việc và phản hồi của nhóm khác.
- Cách kiểm thử của A cho hệ thống dữ liệu nhạy cảm mà không xem yêu cầu D.
- Lịch họp của A sang đội khác múi giờ mà không thỏa thuận.

### 32.3. Phần được chuẩn hóa hợp lý

- **Tại sao** phải minh bạch công việc và blocker.
- **Tại sao** phải giữ DoD/điều kiện an toàn.
- **Tại sao** cần phản hồi người dùng và vận hành.
- **Cách** ghi vấn đề, giả thuyết, bằng chứng và quyết định.
- Cách phối hợp liên nhóm, bảo vệ quyền riêng tư và thông tin nhạy cảm.

## 33. Kế hoạch mở rộng theo hai đợt có điều kiện

Một kế hoạch tốt nên mô tả **thời gian học**, không chỉ danh sách “team nào đi đào tạo”.

### 33.1. Đợt 1 — kiểm chứng tính chuyển giao tại B

| Bước | Hoạt động | Điều kiện hoàn tất |
| --- | --- | --- |
| Tuần chuẩn bị | Phỏng vấn B, chọn vấn đề chờ test, baseline và guardrail | Pilot charter mới, nhóm hiểu mục đích |
| Tuần 1–2 | Thử chia lát cắt, review sớm, sửa test flaky | Item thật đi qua luồng, dữ liệu không bị đổi định nghĩa |
| Tuần 3–4 | Quan sát flow, chất lượng và outcome gần người dùng | Có bằng chứng và câu hỏi chưa rõ |
| Cuối đợt | B và người hỗ trợ đánh giá, không chỉ người quản lý | Quyết định giữ/điều chỉnh/thử thêm, owner rõ |

**Điều kiện dừng:** Nếu việc bắt đầu test theo luồng mới làm mất kiểm soát phát hành, tăng lỗi nghiêm trọng hoặc kéo dài quá tải, cần xử lý tác động ngay và điều chỉnh cách thử.

### 33.2. Đợt 2 — chuẩn bị C và D theo hai bài toán khác nhau

- Với **C**, thử chính sách ưu tiên theo mức nghiêm trọng, WIP/age theo luồng incident và đường chuyển tiếp sang cải tiến phòng ngừa.
- Với **D**, ưu tiên contract dữ liệu, khả năng kiểm chứng độc lập, quyền quyết định và thời gian chờ phê duyệt trước khi đặt mục tiêu cycle time.

**Không nhất thiết chạy hai đợt song song** nếu coaching, platform và quyền quản trị không đủ.

### 33.3. Những cổng quyết định cần có

1. **Cổng sẵn sàng:** Nhóm tiếp nhận có vấn đề, điều kiện và người có quyền thay đổi?
2. **Cổng an toàn:** Guardrail và cách ứng phó sự cố được xác định?
3. **Cổng bằng chứng:** Dữ liệu/nhận xét có đủ để quyết định hay cần thử thêm?
4. **Cổng năng lực hỗ trợ:** Coach, CI, QA và platform có thể phục vụ mà không tạo nút thắt mới?
5. **Cổng duy trì:** Nhóm có thể tiếp tục khi giảm hỗ trợ?

Nếu một cổng chưa đạt, quyết định hợp lệ có thể là **chuẩn bị thêm hoặc giảm số nhóm được rollout**, không phải ép hoàn tất biểu đồ adoption.

## 34. Handoff kiến thức từ pilot tới nhóm tiếp theo

Khi pilot hoàn tất, đừng chỉ trao một slide “best practices”. Hãy trao **một gói kiến thức có điều kiện áp dụng**:

### 34.1. Thành phần tối thiểu

- **Vấn đề gốc:** Điều gì khiến nhóm A cần thay đổi?
- **Đặc điểm bối cảnh:** Kỹ năng, quyền, phụ thuộc, loại công việc, công cụ.
- **Thực hành đã thử:** Điều gì thay đổi, trong phạm vi nào?
- **Cơ chế kỳ vọng:** Vì sao thực hành được cho là hữu ích?
- **Dữ liệu và giới hạn:** Baseline, kết quả, bias và số chưa đủ tin.
- **Guardrail và tác dụng phụ:** Những điều không được bỏ qua.
- **Điều kiện cần:** CI, DoD, PO, reviewer, coach, thời gian, hạ tầng.
- **Phần có thể điều chỉnh:** Con số WIP, cách nhóm board, nhịp giao tiếp.
- **Điều không nên lặp:** Quyết định sai, tool không phù hợp, vướng mắc chưa giải.
- **Đường liên hệ:** Người hỗ trợ và quyền quyết định.
- **Ngày xem lại:** Khi nhóm B có dữ liệu mới.

### 34.2. Mẫu transfer note

~~~text
THUC HANH / PILOT GOC:
VAN DE DA GIAI QUYET:
SAN PHAM / NHOM / DOI TUONG:

CO CHE DA THU:
- Thuc hanh:
- Tai sao ky vong co tac dung:
- Dieu kien can:

BANG CHUNG:
- Baseline:
- Ket qua:
- Dinh nghia metric:
- Mau / khoang thoi gian:
- Han che va yeu to dong thoi:

GUARDRAIL / PHAN HOI BAT LOI:
CO THE THAY DOI GI KHI AP DUNG O NHOM MOI:
NHUNG DIEU KHONG DUOC BO:
KHI NAO KHONG NEN AP DUNG:
NGUOI HO TRO / DUONG ESCALATION:
CAU HOI THU NGHIEM TIEP THEO:
~~~

Một transfer note tốt **không được viết như tài liệu quảng cáo**. Người khác cần thấy cả **cái chưa hiệu quả, điều chưa biết và chi phí thực hiện**.

## 35. Theo dõi sau rollout: vòng học hỏi vẫn phải tiếp tục

Nhân rộng không phải điểm kết thúc. Một thực hành có thể có hiệu quả trong giai đoạn chuyển đổi nhưng dần mất giá trị khi hệ thống, quy mô và loại việc đổi.

### 35.1. Vòng giám sát sau triển khai

~~~mermaid
flowchart TD
    A["Readiness + điều kiện nhóm tiếp nhận"] --> B["Thử thực hành có điều chỉnh"]
    B --> C["Đo flow, outcome, quality, người làm việc"]
    C --> D{"Có đạt điều kiện và guardrail?"}
    D -->|"Có tín hiệu tốt"| E["Giảm hỗ trợ đặc biệt, theo dõi độ bền"]
    D -->|"Chưa rõ"| F["Điều tra và thử thêm có giới hạn"]
    D -->|"Gây hại"| G["Dừng/đổi cách làm, xử lý tác động"]
    E --> H["Cập nhật playbook và quyết định rollout tiếp"]
    F --> B
    G --> H
    H --> A
~~~

### 35.2. Dấu hiệu cần xem lại hoặc dừng thực hành

- Board có quá nhiều trạng thái không phản ánh công việc thật.
- Giới hạn WIP trở thành cớ để không xử lý sự cố khẩn.
- Sprint Planning/Review không còn nhận feedback có ý nghĩa.
- Nhân sự mới không hiểu vì sao nhóm dùng một quy tắc.
- CI/test bị bỏ qua để đạt tốc độ báo cáo.
- Chỉ số flow đẹp hơn nhưng lỗi, Support ticket hoặc quá tải tăng.
- Cấu trúc quyền thay đổi khiến Product Owner không thể ra quyết định.
- Nhóm tiếp nhận thấy bài toán gốc đã biến mất nhưng vẫn phải làm nghi thức.

### 35.3. Dừng một thực hành không phải phủ nhận Agile

Nếu một board chi tiết không còn hữu ích, nhóm có thể đơn giản hóa. Nếu Sprint cố định không phù hợp với luồng hỗ trợ mà tổ chức không thực sự sử dụng Scrum, nhóm có thể thử quản lý flow bằng Kanban. **Điều cần giữ là phản hồi, minh bạch, thích ứng, chất lượng và giá trị người dùng**, không phải mọi biểu mẫu.

### 35.4. Không “rollback” giá trị hoặc kiểm soát an toàn

Nếu phải quay về một cách phối hợp cũ vì pilot gây quá tải, vẫn cần **giữ các biện pháp bảo mật, test hoặc quyền người dùng đã được xác định là cần thiết**. “Rollback quy trình” không đồng nghĩa được phép hạ tiêu chuẩn chất lượng.

## 36. Những sai lầm thường gặp khi mở rộng Agile

| Sai lầm | Tác hại | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| Chỉ chọn nhóm pilot giỏi nhất và xem như đại diện | Bỏ qua độ khác biệt bối cảnh | Ghi selection bias, thử nhóm tương đồng/khác dần |
| Không đặt tiêu chí trước pilot | Chọn số đẹp sau khi thấy kết quả | Charter với mục tiêu, guardrail và ngưỡng xem lại |
| Dùng số cuộc họp làm bằng chứng thành công | Đo nghi thức, không đo kết quả | Outcome, flow, quality và feedback |
| Nhân rộng ngay sau một Sprint tốt | Dễ nhiễu ngẫu nhiên và hiệu ứng mới lạ | Quan sát đủ chu kỳ và thử lặp lại |
| Quên coach/PO được ưu tiên trong pilot | Không tái tạo được điều kiện | Tính năng lực hỗ trợ thực tế khi rollout |
| Sao chép cùng WIP limit mọi nhóm | Không phản ánh luồng incident hoặc dependency | Chọn chính sách theo bối cảnh |
| Ép mọi nhóm dùng cùng story points/velocity | So những đơn vị không tương thích | Không ranking, dùng dữ liệu cho dự báo nội bộ |
| Gọi code complete là Done | Giả tốc độ bằng bỏ kiểm chứng | Giữ Definition of Done |
| Lấy throughput làm KPI thưởng/phạt | Chia giả thẻ, né việc khó | Kết hợp outcome/guardrail và giải thích dữ liệu |
| Không kiểm tra nguyên nhân thay đổi | Gán công cho phương pháp thiếu căn cứ | Xem cơ chế, yếu tố đồng thời và thiên lệch |
| Không hỏi nhóm tiếp nhận có vấn đề giống pilot | Tạo quy trình không giải quyết gì | Problem statement riêng trước rollout |
| Chỉ triển khai board, bỏ quyền quyết định | Nút thắt vẫn nằm ngoài nhóm | Tháo policy/approval gây chờ |
| Mở nhiều team nhưng thiếu CI và test | Tăng rủi ro tích hợp | Đầu tư enabling capabilities |
| Bắt mọi nhóm dùng Scrum bất kể loại việc | Luồng khẩn có thể bị ép không phù hợp | Chọn/kết hợp thực hành đúng bối cảnh |
| Coi đào tạo một ngày là đủ năng lực | Thành viên không thể tự cải tiến | Thực hành, mentoring và coaching theo nhu cầu |
| Lãnh đạo chỉ kiểm “đã dùng Agile chưa” | Tạo báo cáo hình thức | Hỏi hệ thống tạo giá trị tốt hơn chưa |
| Đổi mọi quy trình cùng lúc | Không biết cơ chế nào có tác dụng | Ưu tiên thay đổi nhỏ có thể kiểm chứng |
| Không giới hạn WIP của chương trình chuyển đổi | Quá tải hỗ trợ và phản hồi | Mở rộng từng đợt |
| Bỏ sự cố/bảo mật khỏi scorecard | Tăng tốc bằng chuyển rủi ro | Guardrail có điều kiện dừng |
| Không nghe phản hồi bất lợi | Mất minh bạch, sai lầm lặp lại | Kênh phản hồi không trả đũa |
| Nhóm có maturity score thấp bị phạt | Gaming và che điểm yếu | Dùng đánh giá để điều phối hỗ trợ |
| Đòi mọi nhóm cùng công cụ và giờ họp | Tốn công chuyển đổi không tạo giá trị | Chuẩn hóa interface, cho phép thích ứng |
| Không ghi điều kiện áp dụng trong playbook | Người sau copy sai | Mô tả cơ chế, bối cảnh, chống chỉ định |
| Không kế hoạch giảm hỗ trợ coach | Pilot phụ thuộc “người hùng” | Thử tự chủ và chuyển giao năng lực |
| Coi pilot thất bại là lỗi cá nhân | Nhóm giấu dữ liệu | Học từ giả thuyết sai và điều kiện hệ thống |
| Chỉ xem review cuối kỳ, không phản ứng rủi ro giữa kỳ | Sự cố/tác dụng phụ kéo dài | Quan sát guardrail liên tục phù hợp mức rủi ro |
| Đo sai ranh giới cycle time khi đổi công cụ | Cải thiện giả tạo | Định nghĩa thống nhất và kiểm tra dữ liệu |
| Không quay lại xem sau rollout | Cách làm lỗi thời và bị duy trì hình thức | Theo dõi và loại bỏ thực hành không còn ích |
| Sao chép “thành công” rồi bỏ vấn đề khách hàng | Agile thành hoạt động nội bộ | Kết nối quyết định với Product Goal và outcome |

## 37. Checklist đánh giá trước khi mở rộng

Checklist là **mẫu thực hành phục vụ quản trị học hỏi**, không phải một chuẩn chứng nhận hoặc artifact bắt buộc của Scrum/Kanban/XP.

~~~text
VAN DE VA PILOT
[ ] Pilot giai quyet mot van de co bang chung?
[ ] Co charter, ranh gioi, doi tuong va gia thuyet?
[ ] Co mo ta dieu kien doi pilot (PO, CI, coach, quyen, dependency)?
[ ] Success criteria duoc dat truoc khi xem ket qua?
[ ] Co baseline va dinh nghia metric nhat quan?

BANG CHUNG
[ ] Outcome nguoi dung / Product Goal duoc xem?
[ ] Flow: WIP, age, throughput, cycle time co dieu kien?
[ ] Quality / DoD / security / reliability duoc giu?
[ ] Co phan hoi dinh tinh ve hop tac va qua tai?
[ ] Co kiem tra selection bias, thay doi dong thoi, mau nho?
[ ] Co neu dieu chua biet va do tin cay cua ket luan?

DIEU KIEN NHAN RONG
[ ] Co bieu do co che va cac dieu kien tao ra tac dung?
[ ] Nhom tiep nhan co van de tuong tu?
[ ] Co mo ta nhung khac biet can dieu chinh?
[ ] Co Product Ownership, quyen va co che escalation?
[ ] CI/test/moi truong/van hanh co du nang luc?
[ ] Co nguoi ho tro, coaching va thoi gian hoc?
[ ] Co du nang luc de mo them mot dot rollout?

QUAN TRI VA AN TOAN
[ ] Ai quyet dinh continue/adjust/scale/stop?
[ ] Co guardrail va trigger dung/rollback cach lam?
[ ] Khong xep hang team/ca nhan bang story points/commit?
[ ] Khong ep ha DoD de dat KPI adoption?
[ ] Quyen rieng tu va phan quyen duoc bao ve?
[ ] Phu thuoc lien nhom da duoc xem va xu ly?

SAU ROLLOUT
[ ] Nhom tiep nhan co baseline va cau hoi hoc rieng?
[ ] Thuc hanh moi co the dung / sua khi khong hieu qua?
[ ] Da thu giam ho tro dac biet de kiem tra do ben?
[ ] Bai hoc ca thanh cong lan that bai duoc ghi trong playbook?
[ ] Co thoi diem xem lai outcome, quality va suc khoe nhom?
~~~

Nếu chưa đạt một ô quan trọng, không nhất thiết dừng mọi cải tiến: có thể **giảm phạm vi và thử an toàn hơn**, chuẩn bị enabling work rồi xem lại. Checklist có ích khi tạo **quyết định cụ thể**, không phải khi dùng để chấm người hoặc tô màu phòng ban.

## 38. Bài tập 1 — Thiết kế pilot có tiêu chí thành công trước khi bắt đầu

**Đề bài:** Một nhóm tám người phát triển hệ thống workshop. Trong ba Sprint gần đây, nhiều user story được đánh dấu “dev xong” vào ngày cuối, nhưng chưa qua integration test. Product Owner nói các chức năng ra mắt chậm, QA báo hàng đợi cuối Sprint, Developers cho rằng yêu cầu thay đổi liên tục. Lãnh đạo muốn “thử Agile hai Sprint” và đo số meeting thực hiện.

### Nhiệm vụ

1. Viết một **problem statement** có hành vi và hậu quả cụ thể.
2. Phân biệt giả thuyết về yêu cầu, WIP, test và phụ thuộc — điều gì chưa được chứng minh?
3. Chọn **hai hoặc ba thực hành** sẽ thử, giải thích cơ chế mong muốn.
4. Xác định **ranh giới pilot** và nơi work item được tính bắt đầu/kết thúc.
5. Viết một **outcome chính**, hai flow metrics và ba guardrail.
6. Nếu chưa có baseline tin cậy, bạn sẽ làm gì thay vì tự bịa số?
7. Nêu tiêu chí thành công có thể **bác bỏ giả thuyết** và điều kiện dừng nếu gây hại.
8. Ai cần tham gia quyết định sau pilot, ai có quyền đổi Product Backlog và ai giữ tiêu chuẩn chất lượng?
9. Nếu thời gian hai Sprint không đủ để nhìn lỗi lọt production, bạn sẽ nêu giới hạn thế nào?
10. Viết một charter dài tối đa một trang.

### Gợi ý giải

**Problem statement mẫu:** “Các PBI bị chờ review/test nhiều ngày nên không đạt Definition of Done trước cuối Sprint; người dùng nhận phản hồi muộn. Nhóm chưa biết phần chờ đến từ kích thước PBI, yêu cầu mơ hồ, thiếu test hay năng lực reviewer.”

Pilot có thể thử **làm rõ ví dụ chấp nhận trước khi code, chia lát cắt nhỏ và giới hạn WIP/ưu tiên hoàn tất**, đồng thời tích hợp test theo rủi ro sớm hơn. Đo **cycle time tới DoD, work item age và queue time**, ghép outcome có thể quan sát như thời gian người dùng nhận lát cắt, và guardrail **lỗi nghiêm trọng, phân quyền/dữ liệu, quá tải**. Không dùng số meeting làm bằng chứng thành công và không tự tạo baseline giả.

## 39. Bài tập 2 — Kết luận đúng từ số liệu thí điểm

**Dữ liệu giả định:** Trong hai khoảng bốn tuần:

| Tín hiệu | Trước pilot | Trong pilot |
| --- | ---: | ---: |
| PBI đạt DoD | 16 | 22 |
| Cycle time trung vị | 12 ngày | 8 ngày |
| Chờ review trung vị | 3,5 ngày | 1,5 ngày |
| Hành trình đăng ký hợp lệ bắt đầu | 500 | 600 |
| Đăng ký được xác nhận | 285 | 396 |
| Lỗi nghiêm trọng sau release ghi nhận | 2 | 1 |

Trong pilot, nhóm được **coach hai lần mỗi tuần**, người Product Owner dành nhiều thời gian hơn, đồng thời pipeline được sửa. Không có nhóm đối chứng và không biết cơ cấu người dùng có giống trước không.

### Câu hỏi

1. PBI Done tăng bao nhiêu phần trăm theo phép đếm?
2. Cycle time trung vị giảm bao nhiêu ngày? Có thể suy ra mọi item đều nhanh hơn không?
3. Tỷ lệ đăng ký được xác nhận của hai giai đoạn là bao nhiêu? Chênh lệch **điểm phần trăm** là bao nhiêu?
4. Vì sao không thể tuyên bố “Scrum/giới hạn WIP gây ra toàn bộ thay đổi”?
5. Số lỗi 2 và 1 đủ để khẳng định chất lượng đã cải thiện bền vững chưa?
6. Hỗ trợ đặc biệt từ coach và Product Owner ảnh hưởng khả năng nhân rộng thế nào?
7. Bạn sẽ chọn **mở rộng đại trà, thử lặp lại tại nhóm tương đồng hay dừng**? Nêu điều kiện.
8. Điều gì cần được đo ở nhóm thứ hai để xem cơ chế có lặp lại?

### Gợi ý tính toán

PBI Done tăng:

\[
\frac{22-16}{16}\times100\%=37{,}5\%.
\]

Cycle time trung vị giảm **4 ngày**. Tỷ lệ đăng ký tăng từ:

\[
\frac{285}{500}=57\%
\quad \text{lên} \quad
\frac{396}{600}=66\%.
\]

Chênh lệch **9 điểm phần trăm**. Tuy nhiên **số item, độ phức tạp, người dùng, hạ tầng và hỗ trợ đã thay đổi**. Kết luận phù hợp là có tín hiệu tích cực để **thử lặp lại có điều kiện**, không khẳng định tỷ lệ tác động nhân quả hay xếp hạng Developers.

## 40. Bài tập 3 — Chọn cách mở rộng cho ba nhóm khác nhau

**Tình huống:** Pilot của nhóm A đã có bằng chứng triển vọng khi dùng PBI nhỏ, giới hạn WIP, CI và review sớm. Tổ chức muốn triển khai cho:

- **Nhóm B:** Làm sản phẩm giao diện, công việc gần giống A nhưng test tự động chưa ổn định.
- **Nhóm C:** Trực hỗ trợ production và incident, công việc khẩn ngắt quãng nhiều lần mỗi ngày.
- **Nhóm D:** Xử lý báo cáo dữ liệu nhạy cảm, chịu phê duyệt kiểm toán từ bộ phận khác.

### Nhiệm vụ

1. Liệt kê **hai cơ chế có thể giữ chung** khi nhân rộng.
2. Nêu **điểm khác bối cảnh** quan trọng nhất của B, C và D.
3. Thực hành nào có thể thử ngay ở B? Năng lực nào cần bổ sung?
4. Vì sao cùng giới hạn WIP với A có thể không phù hợp C?
5. Với D, thay đổi nào của **quản trị phụ thuộc/phê duyệt** có thể quan trọng hơn board?
6. Thiết kế một **readiness check** cho mỗi nhóm.
7. Gợi ý thứ tự triển khai, không giả định phải thử cả ba đồng thời.
8. Mỗi nhóm cần một guardrail hoặc điều kiện dừng nào?
9. Nếu B thất bại sau khi áp dụng, bạn sẽ kiểm tra giả thuyết nào trước khi kết luận “nhóm chống Agile”?
10. Viết một đoạn transfer note nêu **điều không nên sao chép** từ A.

### Gợi ý hướng giải

B có thể thử **review sớm và lát cắt nhỏ** trong lúc sửa test không tin cậy; C nên chọn **Kanban flow với chính sách incident/expedite phù hợp** thay vì ép Sprint; D cần làm rõ **nguồn dữ liệu, quyền review, kiểm toán, evidence và thời gian chờ**.

Điều đáng nhân rộng là **tập trung hoàn tất, phản hồi sớm, minh bạch và chất lượng**, còn **số WIP, thời điểm họp và công cụ** phải phù hợp hoàn cảnh.

## 41. Bài tập 4 — Chương trình chuyển đổi đang quá tải

**Bối cảnh:** Công ty có 20 nhóm sản phẩm/kỹ thuật, hai Agile coaches và một platform team đang chịu nhiều sự cố. Lãnh đạo yêu cầu hoàn tất “Agile rollout” cho tất cả nhóm trong sáu tuần. Các nhóm phải dùng cùng board, cùng story point scale, cùng lịch Daily Scrum. Một số nhóm phản ánh CI bị chặn, người mới chưa được đào tạo và thời gian họp tăng.

### Câu hỏi

1. Những dấu hiệu nào cho thấy **WIP của chương trình chuyển đổi** quá cao?
2. Vì sao hai coach không thể bảo đảm đào tạo đủ cho 20 nhóm chỉ bằng một lượt workshop?
3. Những điều kiện nền nào nên được ưu tiên trước rollout rộng?
4. Chỉ số “20/20 nhóm đã tạo board” đo adoption hay effectiveness?
5. Tại sao story points không phù hợp làm chỉ số xếp hạng nhóm?
6. Thiết kế một phương án **rollout từng đợt** với cổng quyết định rõ.
7. Đề xuất hai thay đổi quyền/quy trình giúp các nhóm tự xử lý blocker.
8. Nếu lỗi sau release tăng khi số PBI Done tăng, chương trình nên phản ứng thế nào?
9. Làm sao để nhóm có thể phản hồi một thực hành **không phù hợp** mà không bị phạt?
10. Một báo cáo cho lãnh đạo nên chứa những quyết định và bất định nào?

### Gợi ý hướng giải

Thay vì yêu cầu **20/20 nhóm áp dụng hình thức trong sáu tuần**, nên ưu tiên **một số nhóm có vấn đề và điều kiện thích hợp**, dành năng lực cho coaching, CI và quyền ra quyết định. Mỗi đợt cần kiểm tra **outcome, flow, quality, readiness và khả năng duy trì**, chứ không chỉ số người học. Khi guardrail xấu, **ngừng hoặc sửa cách rollout**, không ép nhóm đổi nhãn Done để đạt kế hoạch.

## 42. Mẫu ghi quyết định “scale / adapt / stop”

Một bản ghi ngắn giúp tránh tình trạng pilot được xem là “đạt” chỉ vì có slide tổng kết.

~~~text
TEN PILOT / NGAY QUYET DINH:
VAN DE GOC:
RANH GIOI VA DOI TUONG THU:
THUC HANH DA THU:

DIEU KIEN THANH CONG DA DINH TRUOC:
- Outcome:
- Flow:
- Quality / reliability:
- People / sustainability:
- Readiness:

KET QUA QUAN SAT:
- Baseline:
- Sau pilot:
- Dinh nghia metric:
- Feedback dinh tinh:
- Guardrail:

DO TIN CAY / GIOI HAN:
- Mau / thoi gian:
- Selection bias:
- Ho tro dac biet:
- Thay doi dong thoi:
- Dieu chua biet:

CO CHE DUOC HO TRO BANG CHUNG:
DIEU KIEN CAN DE CHUYEN GIAO:
NHUNG GI KHONG NEN SAO CHEP:
PHUONG AN DUOC CAN NHAC:
- Scale co dieu kien:
- Adapt:
- Thu them:
- Stop:

QUYET DINH VA LY DO:
NGUOI CO THAM QUYEN:
NHOM TIEP NHAN / ENABLEMENT CAN:
GUARDRAIL VA TRIGGER DUNG:
NGAY XEM LAI / BANG CHUNG CAN TIEP:
~~~

Mẫu này không bắt buộc mọi nhóm phải dùng nguyên văn. Phần giá trị là **ghi lại điều kiện, bằng chứng, giới hạn và quyền quyết định để người sau không nhầm một pilot có triển vọng thành công thức phổ quát**.

## 43. Câu hỏi tự kiểm tra

1. Vì sao “một nhóm có Scrum events đầy đủ” chưa đủ chứng minh Agile transformation thành công?
2. Pilot, rollout, scaling và transformation khác nhau ở mục đích nào?
3. Bắt đầu pilot từ một vấn đề thật giúp tránh rủi ro gì?
4. Vì sao cần mô tả **cơ chế kỳ vọng** giữa thực hành và outcome?
5. Điều kiện thành công của pilot nên được xác lập khi nào?
6. Những nhóm chỉ số nào cần cân bằng để không tối ưu output bằng bỏ chất lượng?
7. Định nghĩa work item và Done phải nhất quán vì sao?
8. Kết quả trước/sau có thể bị sai lệch bởi những yếu tố nào?
9. Vì sao một pilot có nhiều hỗ trợ đặc biệt chưa đủ chứng minh khả năng nhân rộng?
10. Nếu outcome tốt nhưng lỗi bảo mật tăng, có thể coi pilot thành công không?
11. Khi nào “chưa đủ bằng chứng” là quyết định phù hợp?
12. Những lựa chọn nào tồn tại tại cổng kết thúc pilot?
13. Phân biệt thực hành cốt lõi cần giữ và hình thức có thể điều chỉnh.
14. Vì sao giới hạn WIP của nhóm sản phẩm không nên áp nguyên cho nhóm vận hành sự cố?
15. Một readiness assessment cần xem những năng lực nào?
16. Scrum, Kanban và XP có thể bổ trợ nhau ra sao khi nhân rộng?
17. Vai trò của Product Goal, Sprint Goal và DoD khi nhóm thay cách làm là gì?
18. Vì sao flow metrics cần kết hợp với outcome người dùng?
19. Những phụ thuộc liên nhóm nào có thể làm cho pilot tốt nhưng rollout kém?
20. Khi nào cần thay quyền quyết định thay vì thêm một lớp họp?
21. Vì sao chương trình chuyển đổi cũng cần giới hạn WIP?
22. Tại sao không nên xếp hạng Scrum Team bằng velocity/story points?
23. Một playbook chuyển giao cần ghi phần **không nên áp dụng** như thế nào?
24. Làm sao thử độ bền của cách làm khi giảm hỗ trợ của coach?
25. Khi thực hành gây quá tải, điều kiện nào cho phép dừng hoặc điều chỉnh?
26. Vì sao kết quả thí điểm không thuận lợi vẫn có giá trị?
27. Mở rộng theo từng đợt giúp kiểm chứng điều gì mà rollout đại trà không cho thấy?
28. Một quyết định “scale” có thể đi kèm điều kiện nào để bảo vệ người dùng?

## 44. Ghi nhớ: nhân rộng điều kiện tạo giá trị, không nhân bản hình thức

**Mở rộng cách làm dựa trên điều kiện thành công của thí điểm** nghĩa là dùng một pilot để **học điều gì cải thiện dòng giá trị và trong hoàn cảnh nào**, rồi tiếp tục kiểm chứng khi đưa sang bối cảnh khác. Không phải cứ một nhóm giảm cycle time thì tất cả nhóm phải dùng cùng WIP limit, công cụ, Sprint length hay story point scale.

Những nguyên tắc cần giữ:

1. **Thí điểm nhằm kiểm chứng một vấn đề thật:** Không chọn phương pháp trước rồi tìm số liệu chứng minh nó tốt.
2. **Nêu điều kiện thành công từ đầu:** Gồm outcome, flow, chất lượng, người làm việc và khả năng duy trì.
3. **Giữ các guardrail:** Không đánh đổi DoD, dữ liệu, bảo mật hoặc nhịp bền vững để tăng báo cáo output.
4. **Đọc bằng chứng có bối cảnh:** Kiểm tra baseline, cách đếm, mẫu, yếu tố đồng thời và hỗ trợ đặc biệt.
5. **Tách cơ chế khỏi nghi thức:** Nhân rộng nguyên tắc giảm chờ, hợp tác và phản hồi sớm, không sao chép mọi tên cột hoặc buổi họp.
6. **Đánh giá readiness của nhóm tiếp nhận:** Product ownership, quyền, CI/test, phụ thuộc, người hỗ trợ và dữ liệu cần thiết.
7. **Điều chỉnh Scrum, Kanban và XP theo vấn đề:** Giữ tính đúng của thực hành đã chọn, tránh áp một mô hình cho mọi loại luồng.
8. **Mở rộng từng đợt với quyền quyết định rõ:** Có cơ chế tiếp tục, thử thêm, điều chỉnh hoặc dừng.
9. **Đầu tư vào hệ thống hỗ trợ:** Giải quyết điểm nghẽn liên nhóm, công cụ, đào tạo và quyền tự chủ.
10. **Khép kín vòng học hỏi sau rollout:** Theo dõi outcome, quality, tác dụng phụ và thay đổi thực hành khi bằng chứng mới xuất hiện.

Trước khi yêu cầu nhóm kế tiếp “làm giống thí điểm”, hãy tự hỏi: **“Vấn đề nào chúng ta đang giúp họ giải quyết, cơ chế nào thực sự tạo cải thiện trong pilot, những điều kiện nào phải có để cơ chế đó hoạt động, nhóm mới khác ở đâu và bằng chứng nào sẽ khiến chúng ta tiếp tục, điều chỉnh hoặc dừng?”**

Trả lời được những câu hỏi ấy giúp tổ chức **mở rộng năng lực học hỏi, giao Increment đáng tin cậy và cải tiến liên tục**, thay vì chỉ mở rộng số lượng bảng Agile và buổi họp.
