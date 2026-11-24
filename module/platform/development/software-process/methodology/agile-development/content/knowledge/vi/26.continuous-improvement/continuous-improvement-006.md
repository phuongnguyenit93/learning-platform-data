# Theo dõi hành động cải tiến trong công việc thực tế

## 1. Vì sao cải tiến liên tục thường dừng lại ở những cuộc họp?

Một Scrum Team đang phát triển nền tảng học trực tuyến. Trong Sprint Retrospective, các thành viên thống nhất ba vấn đề: user story thường phải hỏi lại nghiệp vụ, pull request chờ review lâu và kiểm thử tích hợp không ổn định. Mọi người đề xuất “trao đổi sớm hơn”, “review nhanh hơn” và “cải thiện CI”. Cuộc họp kết thúc với cảm giác tích cực.

Hai Sprint sau, nhóm vẫn gặp những vấn đề tương tự. Lý do không hẳn là mọi người thiếu thiện chí. Những đề xuất ban đầu **chưa trở thành hành động có thể thực hiện, có người hỗ trợ, thời điểm kiểm tra và bằng chứng kết quả**. Không ai biết:

- Ai sẽ tiến hành việc cụ thể nào?
- Khi nào hành động được đưa vào công việc thật, bên cạnh các Product Backlog Items?
- Điều gì cho thấy hành động đã được triển khai?
- Điều gì cho thấy **cách làm mới thực sự giải quyết vấn đề**?
- Nếu giả thuyết cải tiến sai hoặc tác dụng phụ xuất hiện, ai quyết định điều chỉnh?
- Sau khi một thử nghiệm có hiệu quả, làm sao biến kết quả thành thói quen bền vững?

**Theo dõi hành động cải tiến** là quá trình chuyển quan sát thành những thay đổi có chủ đích trong cách làm việc, **làm rõ trách nhiệm và bằng chứng**, kiểm tra kết quả trong các chu kỳ ngắn, rồi quyết định **duy trì, điều chỉnh hoặc dừng**.

Trong module **AGILE_DEVELOPMENT**, thực hành này gắn với tư duy thích ứng qua phản hồi sớm và giao sản phẩm tăng dần. Scrum cung cấp nhịp kiểm tra và thích ứng; Kanban giúp nhìn dòng công việc; XP cung cấp những thực hành kỹ thuật để thay đổi an toàn; Lean/Kaizen khuyến khích cải tiến hệ thống liên tục. Các phương pháp đó không thay thế việc **thực sự theo dõi và hoàn tất một hành động cải tiến**.

> **Thông điệp cốt lõi:** Một đề xuất trong Retrospective không tự động trở thành cải tiến. Giá trị xuất hiện khi nhóm **thử thay đổi trong công việc thật, quan sát hệ quả và điều chỉnh cách làm dựa trên bằng chứng**.

## 2. Từ vấn đề tới cải tiến: cần phân biệt những khái niệm nào?

Trong trao đổi hằng ngày, nhóm dễ dùng lẫn các từ “vấn đề”, “ý tưởng”, “action item” và “kết quả”. Phân biệt chúng giúp theo dõi mà không biến công việc thành danh sách việc vặt.

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong nhóm phát triển |
| --- | --- | --- |
| **Quan sát (observation)** | Điều gì đã xảy ra, nguồn bằng chứng nào? | 7 trong 12 story hoàn tất gần đây đã phải hỏi lại quy tắc sau khi bắt đầu |
| **Vấn đề/tác động (problem/impact)** | Vì sao điều đó cản trở giá trị, chất lượng hoặc phối hợp? | Story nằm chờ câu trả lời, lead time kéo dài |
| **Giả thuyết (hypothesis)** | Thay đổi nào được kỳ vọng cải thiện điều gì, vì sao? | Làm rõ ví dụ nghiệp vụ trước khi kéo story sẽ giảm thời gian chờ |
| **Hành động/thử nghiệm (action/experiment)** | Ai sẽ làm gì trong phạm vi nào và khi nào? | Thử phiên Three Amigos 20 phút cho 5 story sắp thực hiện |
| **Output của hành động** | Có bằng chứng hành động đã được thực hiện không? | Đã có 5 phiên làm rõ, tiêu chí chấp nhận được cập nhật |
| **Outcome cải tiến** | Dòng công việc/khả năng người dùng có thay đổi theo hướng mong muốn? | Ít story bị chặn bởi câu hỏi nghiệp vụ hơn |
| **Guardrail** | Điều quan trọng nào không được xấu đi? | Không tăng thời gian chuẩn bị quá mức hoặc lỗi production |
| **Quyết định học hỏi** | Giữ, thay, mở rộng hay bỏ thử nghiệm? | Tiếp tục cho story có rủi ro nghiệp vụ cao, không áp bắt buộc cho mọi bug |
| **Chuẩn hóa (standardize)** | Nếu hiệu quả, làm sao duy trì? | Bổ sung chính sách refinement ngắn vào cách nhóm vận hành |

### Hoàn tất hoạt động không đồng nghĩa đã tạo cải tiến

“Đã tổ chức bốn buổi trao đổi” chỉ chứng minh **một hoạt động đã diễn ra**. Nếu các buổi ấy không giúp story rõ hơn hoặc thời gian chờ giảm, chưa đủ kết luận cách làm đã hiệu quả.

Tương tự, “đã viết thêm 50 unit tests” không tự chứng minh số lỗi lọt production giảm. Cần biết **test bảo vệ hành vi nào, có phát hiện sai lệch thực sự không và chi phí CI có chấp nhận được không**.

### Không phải mọi thứ cần một thí nghiệm thống kê

Một lỗi cấp quyền nghiêm trọng đòi hỏi khắc phục ngay theo tiêu chuẩn bắt buộc, không chờ thử A/B. “Cải tiến có bằng chứng” bao gồm cả **kiểm tra tuân thủ chất lượng, tái hiện lỗi, chạy test hồi quy và xác minh an toàn**, không chỉ thử nghiệm ngẫu nhiên. Chọn loại bằng chứng theo **bản chất quyết định và mức rủi ro**.

## 3. Lấy đầu vào cải tiến từ đâu?

Retrospective là nguồn quan trọng nhưng không phải nguồn duy nhất. Cải tiến có thể xuất hiện bất kỳ khi nào nhóm phát hiện khoảng cách giữa **cách làm hiện tại** và **kết quả mong muốn**.

| Nguồn | Tín hiệu ví dụ | Hành động cải tiến có thể cân nhắc |
| --- | --- | --- |
| **Sprint Retrospective** | Nhiều story bị chặn vì làm rõ muộn | Điều chỉnh cách chọn story và làm rõ acceptance criteria |
| **Daily Scrum và công việc hằng ngày** | Một API đang chờ review lâu | Đặt chính sách ưu tiên giúp hoàn tất trước khi kéo việc mới |
| **Sprint Review / phản hồi stakeholder** | Người học thấy khó hiểu trạng thái ghi danh | Thêm ví dụ nghiệp vụ và phản hồi người dùng vào refinement |
| **Kanban board / flow metrics** | Work item age tăng ở cột Test | Phân tích hàng đợi, môi trường và chính sách WIP |
| **CI/CD và kiểm thử** | Pipeline flaky, khó biết mã nào gây lỗi | Cô lập dữ liệu test, cải thiện tín hiệu và thời gian phản hồi |
| **Production / hỗ trợ khách hàng** | Lỗi tiến độ đa thiết bị lọt production | Bổ sung integration test đa phiên, observability và rollout |
| **Sự cố và postmortem** | Khôi phục chậm do thiếu runbook | Tạo runbook và thử diễn tập khôi phục phù hợp |
| **Onboarding / cộng tác liên nhóm** | Thành viên mới mất nhiều ngày tìm quy tắc quyền | Tạo một nguồn thông tin chung, ví dụ nghiệp vụ và đường hỏi đúng |
| **Discovery và dữ liệu sản phẩm** | Tính năng mới ít được học viên sử dụng | Cải thiện vòng xác nhận giả thuyết trước khi đầu tư |

### Cải tiến nhằm giải quyết vấn đề, không nhằm “đạt chỉ tiêu số hành động”

Đếm số action items trong mỗi Retrospective dễ khiến nhóm tạo nhiều nhiệm vụ nhỏ nhưng không thay đổi hệ thống. Một hành động cải tiến **nhỏ, có trọng tâm và được kiểm tra** thường hữu ích hơn mười cam kết không đủ năng lực thực hiện.

### Bảo vệ những nguồn phản hồi không dễ nói ra

Trong một nhóm thiếu an toàn tâm lý, người làm có thể không dám đề cập code review chậm, lỗi do API giữa nhóm hoặc sự cố suýt gây hại. Người điều phối cần khuyến khích **quan sát cụ thể, ngôn ngữ không buộc tội và thảo luận hệ thống**, đồng thời giữ sự rõ ràng về trách nhiệm thực hiện và mức độ nhạy cảm của dữ liệu.

## 4. Xác định vấn đề trước khi chọn giải pháp

Một Retrospective kết luận “Chúng ta phải dùng công cụ X” trước khi làm rõ nguyên nhân có thể dẫn tới cải tiến hình thức. Hãy bắt đầu bằng **tuyên bố vấn đề có thể kiểm chứng**.

### Mẫu phát biểu vấn đề

~~~text
Trong <phạm vi công việc / khoảng quan sát>,
chúng tôi quan sát <điều xảy ra / bằng chứng>,
làm ảnh hưởng tới <người dùng / luồng / chất lượng> theo cách <tác động>.
Điều chúng tôi chưa biết là <giả định hoặc câu hỏi nguyên nhân>.
~~~

Ví dụ:

> Trong ba Sprint gần đây, 9/18 user story đã bắt đầu bị chặn ít nhất một lần vì thiếu ví dụ xử lý trạng thái ghi danh. Việc chờ xác nhận làm kéo dài cycle time; chúng tôi chưa biết nguyên nhân chủ yếu do chọn story quá sớm hay do thiếu người nghiệp vụ trả lời.

Đây là mô tả tốt hơn “Product Owner không chuẩn bị đủ” vì **nó có phạm vi, bằng chứng và câu hỏi điều tra**, không quy kết nguyên nhân cho một cá nhân trước khi kiểm tra.

### Tìm nguyên nhân đóng góp thay vì vội kết luận

Có thể dùng một số kỹ thuật:

- **5 Whys:** hỏi tiếp vì sao khi có bằng chứng hỗ trợ, không mặc định đúng năm câu hỏi là đủ.
- **Fishbone/cause-and-effect:** xem nhiều nhóm nguyên nhân như quy trình, kỹ thuật, dữ liệu, phụ thuộc và môi trường.
- **Value Stream Mapping:** xác định nơi công việc chờ hoặc làm lại trong dòng giá trị.
- **Phân tích work item age/blocked time:** thấy hạng mục nào bị kẹt và ở đâu.
- **Xem mẫu story và acceptance criteria:** đối chiếu trường hợp rõ/không rõ để tìm khác biệt.
- **Phỏng vấn người thực hiện/người nghiệp vụ:** hiểu điều kiện thực tế khiến quyết định đến muộn.

Không có kỹ thuật nào tự sinh ra nguyên nhân đúng. Ví dụ “story chờ vì thiếu PO” có thể là kết luận quá đơn giản; thực tế có thể là **người đưa quyết định không được ủy quyền, glossary không thống nhất, phụ thuộc liên nhóm hoặc quá nhiều WIP**.

## 5. Biến một ý tưởng thành hành động cải tiến có thể theo dõi

Hành động tốt không chỉ nêu ý định, mà chỉ ra **ai làm gì, khi nào, trên phạm vi nào và kiểm tra thành công ra sao**.

| Hành động mơ hồ | Hành động có thể theo dõi |
| --- | --- |
| “Giao tiếp tốt hơn” | “Trong hai tuần, tổ chức phiên 20 phút giữa nghiệp vụ–phát triển–kiểm thử cho 5 story có quy tắc phức tạp trước khi kéo vào In Progress; ghi lại câu hỏi chưa rõ và người chốt” |
| “Review nhanh hơn” | “Thử chính sách ưu tiên review PR nhỏ vào đầu buổi làm việc, giới hạn WIP review, theo dõi thời gian chờ trong ba tuần” |
| “Tăng coverage” | “Bổ sung integration test cho hai request ghi danh đồng thời; test phải phát hiện tạo hai đăng ký hiệu lực” |
| “Đỡ họp nhiều” | “Thử dùng bản ghi quyết định bất đồng bộ cho vấn đề đơn giản trong hai chu kỳ; giữ cuộc trao đổi trực tiếp cho quyết định nhiều rủi ro” |
| “Sửa pipeline” | “Định danh hai test flaky gây thất bại thường xuyên, tạo dữ liệu thử độc lập và theo dõi tỷ lệ chạy lại” |
| “Giảm lead time” | “Giảm hàng đợi Review/Test của story tiêu chuẩn bằng chính sách không mở thêm việc khi review vượt WIP limit, kiểm tra phân phối cycle time và lỗi” |

### SMART chỉ là một công cụ diễn đạt

Tiêu chí **Specific, Measurable, Achievable, Relevant, Time-bound** có thể giúp hành động rõ hơn. Nhưng tránh ép mọi kết quả phải thành một con số chắc chắn từ đầu. Với giả thuyết nhiều bất định, có thể đo **bằng chứng học được** hoặc việc loại bỏ một rủi ro thay vì hứa trước “lead time sẽ giảm 40%”.

Một mục tiêu cải tiến có thể là:

> “Trong hai chu kỳ kế tiếp, thử chính sách review thay đổi nhỏ. Đến buổi xem lại, so sánh thời gian chờ review, phân phối cycle time và lỗi hồi quy với đường cơ sở; quyết định có giữ chính sách hay không.”

Nó có phạm vi, thời hạn, chỉ số và quyết định. **Phần trăm cải thiện mong muốn** chỉ nên được đặt khi có căn cứ và không tạo động cơ thao túng số liệu.

### Phân chia hành động và kết quả

**Action:** thực hiện một việc nhóm kiểm soát được, chẳng hạn cấu hình pipeline chạy contract test.

**Outcome:** kết quả có thể chịu nhiều yếu tố khác, chẳng hạn số lỗi hợp đồng API lọt production giảm. Người sở hữu action chịu trách nhiệm **thực hiện và đưa bằng chứng**, không thể hứa chắc outcome sẽ xảy ra nếu giả thuyết chưa được xác nhận.

## 6. Một thẻ hành động cải tiến cần những trường nào?

Không cần một biểu mẫu phức tạp cho mọi đề xuất. Nhưng để theo dõi mà không phải nhớ bằng miệng, một thẻ cơ bản nên có:

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| **ID và tiêu đề** | Có một đối tượng theo dõi ổn định | IMP-014 – Giảm chờ review cho story tiêu chuẩn |
| **Nguồn/quan sát** | Biết vì sao quyết định cải tiến | Sprint Retrospective; 8/14 story chờ review trên hai ngày |
| **Vấn đề/tác động** | Giữ liên hệ với giá trị | Story không đạt Done đúng nhịp; khó kiểm chứng sớm |
| **Giả thuyết** | Nêu cơ chế cải thiện dự kiến | PR nhỏ và ưu tiên review làm giảm hàng đợi |
| **Hành động cụ thể** | Người thực hiện biết cần làm gì | Giới hạn WIP ở Review/Test, review trước khi mở story mới |
| **Owner/DRI** | Một đầu mối theo dõi và tháo cản trở | Một Developer được nhóm giao đầu mối |
| **Người phối hợp** | Thể hiện ai cần tham gia | Developers, người kiểm thử, nhóm phụ thuộc |
| **Phạm vi thử** | Ngăn làm quá rộng hoặc áp sai loại việc | Chỉ story tiêu chuẩn trong ba tuần |
| **Mốc bắt đầu và xem lại** | Cải tiến xuất hiện trong lịch thực | Thử từ Sprint tới; review tại Retrospective kế tiếp |
| **Đường cơ sở** | Có gì để so sánh | Median chờ review 1,8 ngày trong kỳ đo trước |
| **Bằng chứng hoàn tất action** | Biết đã thực hiện thay đổi hay chưa | Có chính sách, thẻ việc và lịch sử review |
| **Outcome/guardrail** | Xem hiệu quả và tác dụng phụ | Chờ review giảm; lỗi production không tăng |
| **Trạng thái/quyết định** | Có điểm dừng minh bạch | Đang thử → Đánh giá → Giữ/Điều chỉnh/Dừng |
| **Liên kết bằng chứng** | Có thể truy lại khi cần | Dashboard, log CI, PR, quyết định nhóm |

### Owner là đầu mối, không phải người bị đổ lỗi

Một **Directly Responsible Individual (DRI)** hoặc đầu mối hành động giúp tránh tình huống “tất cả cùng phụ trách nhưng không ai theo dõi”. Owner có trách nhiệm **điều phối, cập nhật blocker và mang bằng chứng về xem lại**; những thay đổi liên quan cả nhóm vẫn cần sự cộng tác.

Ví dụ, một Developer có thể là owner thử chính sách review, nhưng không phải người ấy có quyền bắt tất cả thành viên làm thêm giờ hay bỏ các kiểm tra chất lượng. **Quyền thay đổi chính sách** cần được nhóm và người chịu trách nhiệm liên quan thống nhất.

### Deadline phải dẫn tới một quyết định

“Xong trước thứ Sáu” có thể đủ cho task kỹ thuật nhỏ. Với thử nghiệm cải tiến, cần thêm **ngày xem lại kết quả**. Một hành động có thể được triển khai hôm nay nhưng chưa có đủ dữ liệu đến tuần sau. Không nên ép gắn nhãn “cải tiến hiệu quả” ngay sau khi thay đổi một quy trình.

## 7. Trạng thái theo dõi: đừng dùng mỗi “To do – Done”

Nếu action được đánh Done ngay khi hoàn thành hoạt động, nhóm mất dấu câu hỏi “nó có hiệu quả không?”. Có thể sử dụng một luồng đơn giản:

~~~mermaid
flowchart LR
    A["Ghi nhận / đề xuất"] --> B["Được chọn + có owner"]
    B --> C["Đang thực hiện / thử nghiệm"]
    C --> D["Đã triển khai, chờ bằng chứng"]
    D --> E["Đánh giá kết quả"]
    E --> F["Duy trì / chuẩn hóa"]
    E --> G["Điều chỉnh / thử lại"]
    E --> H["Dừng / không hiệu quả"]
    G --> C
~~~

### Một ví dụ quy tắc chuyển trạng thái

| Trạng thái | Điều kiện để vào | Điều kiện để rời |
| --- | --- | --- |
| **Proposed** | Có quan sát hoặc ý tưởng, chưa cam kết làm | Ưu tiên/loại bỏ dựa trên giá trị và năng lực |
| **Selected** | Có giả thuyết, owner, phạm vi, thời điểm thử | Owner và người phối hợp có khả năng bắt đầu |
| **In Progress** | Đang thực hiện việc cụ thể | Có bằng chứng action đã triển khai, hoặc cần điều chỉnh |
| **Evidence Pending** | Cách làm mới đã được áp dụng, cần thêm dữ liệu | Đã tới mốc quan sát hoặc có tín hiệu cần xem sớm |
| **Review** | Nhóm so sánh dữ liệu và thảo luận hệ quả | Có quyết định rõ giữ/đổi/dừng |
| **Adopted/Standardized** | Có bằng chứng đủ dùng và được đưa vào cách làm thường xuyên | Có cách duy trì và người chịu trách nhiệm xem lại nếu cần |
| **Adjusted/Stopped** | Giả thuyết không đúng, có tác dụng phụ hoặc không còn giá trị | Ghi điều học được, không để ticket treo vô hạn |

Đây là **gợi ý chính sách nhóm**, không phải trạng thái Scrum/Kanban bắt buộc. Với nhóm rất nhỏ, có thể gộp các cột nếu vẫn phân biệt được **đã làm việc** và **đã xác minh hiệu quả**.

### Tránh một “hàng đợi thử nghiệm” không bao giờ kết thúc

Nếu action ở trạng thái Evidence Pending nhiều tháng vì không ai xem metric, nó vẫn là **công việc dở dang**. Hãy đưa **mốc xem lại** vào lịch và có quyết định dựa trên mức bằng chứng thực tế: giữ tạm có điều kiện, thay cách đo, dừng hoặc chờ thêm dữ liệu với lý do rõ ràng.

Không nên đợi kết quả có ý nghĩa thống kê cho mọi cải tiến nhỏ nếu chi phí chờ vượt giá trị. Nhưng cũng không được tự coi một số liệu thuận lợi trong hai ngày là chứng minh chắc chắn cho cả sản phẩm.

## 8. Tích hợp cải tiến vào công việc thật thay vì tạo một danh sách nằm ngoài luồng

Một action cải tiến dễ thất bại khi nhóm ghi nó vào biên bản họp nhưng **không có năng lực, lịch phối hợp hoặc nơi theo dõi**.

### Ba cách đưa hành động vào luồng

1. **Là một phần của công việc sắp triển khai:** ví dụ khi làm story ghi danh, bổ sung test integration chống trùng trong phạm vi DoD; không cần tạo một dự án cải tiến tách rời nếu cải thiện gắn trực tiếp thay đổi đó.
2. **Là công việc kỹ thuật hoặc công việc nhóm độc lập:** ví dụ cải thiện CI, chuẩn bị dữ liệu test hoặc triển khai dashboard work item age; cần được ưu tiên, giao owner và theo dõi minh bạch.
3. **Là chính sách làm việc mới:** ví dụ review PR nhỏ thường xuyên, đặt WIP limit hoặc trao đổi Three Amigos cho story rủi ro cao; cần thử trên công việc hằng ngày, không chỉ viết tài liệu.

### Nếu dùng Scrum

Sprint Retrospective giúp Scrum Team **lập kế hoạch cách tăng chất lượng và hiệu quả**. Những thay đổi quan trọng nhất có thể được giải quyết càng sớm càng tốt và được **đưa vào Sprint Backlog** khi nhóm lựa chọn phù hợp. Điều đó **không đồng nghĩa** Scrum bắt buộc có một loại ticket “improvement” đặc biệt hay phải có đúng một action sau mỗi Retrospective.

Developers giữ trách nhiệm điều chỉnh Sprint Backlog để tiến tới Sprint Goal; Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả; Scrum Master hỗ trợ hiệu quả Scrum Team và loại bỏ trở ngại theo phạm vi thích hợp. Cần phối hợp để **đầu tư cho cải tiến không bị coi là công việc vô hình**.

### Nếu dùng Kanban

Có thể thể hiện action trên cùng một board với class of service rõ, hoặc trên bảng improvement riêng có liên kết với luồng sản phẩm. **WIP limit** giúp tránh khởi động quá nhiều cải tiến mà không hoàn thành cái nào. Không cần một bảng phụ thật lớn nếu cả nhóm không sử dụng nó để ra quyết định.

### Bảo vệ năng lực một cách thực tế

Không nên cam kết “mỗi Sprint hoàn thành 10 cải tiến” bất kể mức phức tạp. Nhóm cần tính tới **năng lực dành cho delivery, duy trì hệ thống, phản ứng sự cố và cải tiến**, rồi chọn ít hành động có khả năng thực hiện. Nếu có sự cố khẩn, ưu tiên và phạm vi có thể cần thay đổi minh bạch.

## 9. Ưu tiên hành động cải tiến khi có quá nhiều vấn đề

Không phải mọi vấn đề đều quan trọng như nhau. Nhóm có thể chọn theo **tác động, tần suất, rủi ro, mức cấp bách, khả năng kiểm chứng và chi phí thực hiện**.

### Bộ câu hỏi ưu tiên gọn

- Nếu không giải quyết vấn đề này, **người dùng hoặc chất lượng** chịu tác động gì?
- Vấn đề xảy ra thường xuyên hay chỉ là một trường hợp đặc biệt?
- Có liên quan **bảo mật, mất dữ liệu hoặc nghĩa vụ bắt buộc** không?
- Hành động có ảnh hưởng tới **điểm nghẽn của cả hệ thống** hay chỉ một bộ phận?
- Nhóm có **quyền và năng lực** thực hiện không, hay cần phối hợp bên ngoài?
- Có cách thử nhỏ và thu bằng chứng trong thời gian hợp lý không?
- Hành động nào là **tiền điều kiện** cho hành động khác?

### Ví dụ một buổi chọn action

| Đề xuất | Tác động/rủi ro | Khả năng thử sớm | Quyết định minh họa |
| --- | --- | --- | --- |
| Sửa quy tắc quyền đang gây truy cập trái phép | Rất cao, an toàn sản phẩm | Cần hành động ngay | Kích hoạt xử lý sự cố; không chờ retro |
| Bổ sung contract test cho API ghi danh liên nhóm | Cao, có lỗi tương thích lặp | Có thể thử trên một hợp đồng | Ưu tiên cao |
| Giảm WIP Review/Test của story tiêu chuẩn | Hàng đợi lặp thường xuyên | Thử chính sách trong hai tuần | Chọn một action nhỏ |
| Đổi toàn bộ công cụ quản lý dự án | Chưa rõ lợi ích, chi phí chuyển đổi lớn | Khó thử và dễ gây gián đoạn | Chưa chọn; cần bằng chứng vấn đề |
| Đổi màu thẻ ticket để dễ nhìn | Tác động nhỏ | Dễ làm | Chỉ thực hiện nếu có nhu cầu thật và không lấn át việc quan trọng |

**Không nhất thiết tính điểm số ưu tiên thật chính xác** khi dữ liệu còn mơ hồ. Bảng chỉ giúp cuộc trao đổi bớt dựa vào người nói lớn nhất. Các vấn đề nghiêm trọng phải tuân theo chính sách an toàn/khắc phục ngay, không phải xếp hàng cùng các thử nghiệm cải tiến thông thường.

### Chọn ít, làm đến nơi đến chốn

Một nhóm có thể quyết định thử **một hoặc hai thay đổi chính** trong một chu kỳ, đồng thời giữ một số ý tưởng ở Proposed. Đó là **lựa chọn dựa trên năng lực**, không phải con số bắt buộc của Scrum. Nếu không có đủ thời gian kiểm chứng một hành động, không nên đánh dấu Selected chỉ để tăng số cam kết.

## 10. Đo đường cơ sở trước khi thay đổi

**Baseline (đường cơ sở)** mô tả hiện trạng để sau này so sánh. Không cần mọi baseline là nghiên cứu lớn, nhưng cần đủ rõ về **định nghĩa, khoảng thời gian, loại công việc và nguồn dữ liệu**.

Giả sử nhóm muốn giảm thời gian chờ code review. Có thể thu:

| Trường | Ví dụ minh họa |
| --- | --- |
| Câu hỏi | “Story tiêu chuẩn chờ review bao lâu?” |
| Đơn vị đo | Ngày lịch đã trôi qua, có timestamp đầy đủ |
| Bắt đầu đo | PR sẵn sàng review theo chính sách nhóm |
| Kết thúc đo | Review có quyết định/feedback đầu tiên có thể hành động |
| Khoảng quan sát | Các PR story tiêu chuẩn hoàn tất trong bốn tuần trước thử |
| Kích thước mẫu | 24 PR; không gồm hotfix theo luồng khẩn |
| Trung vị thời gian chờ | 1,8 ngày, **giả định** |
| Phân vị P85 | 3,6 ngày theo một quy tắc tính đã thống nhất, **giả định** |
| Guardrail | Không tăng lỗi hồi quy; không đẩy thời gian review sang giai đoạn khác |

### Vì sao phải định nghĩa timestamp?

Nếu một người tính chờ review từ lúc PR được tạo, còn người khác tính từ lúc PR được đánh “Ready for Review”, hai số liệu có thể khác vì **PR nháp chưa sẵn sàng không phải hàng đợi review theo chính sách đó**. Hãy đặt tên đúng và giữ định nghĩa nhất quán trước/sau.

### Đường cơ sở có thể là quan sát định tính

Đối với vấn đề “học viên không hiểu trạng thái chờ duyệt”, baseline có thể gồm **tình huống quan sát sử dụng, đoạn phỏng vấn đã được xử lý an toàn, số yêu cầu hỗ trợ và kết quả nhiệm vụ**. Tránh tự tạo con số với độ chính xác giả tạo nếu hiện chưa có hệ thống đo.

### Không biến baseline thành công cụ trách phạt

Dữ liệu về story bị chặn, PR chờ lâu hoặc lỗi test nên giúp cả nhóm xác định **chính sách và phụ thuộc nào gây ma sát**. Nếu dùng nó để xếp hạng từng cá nhân, người làm có thể ngại ghi blocker hoặc tạo trạng thái Done quá sớm.

## 11. Theo dõi hiệu quả: output, outcome và guardrail đi cùng nhau

Sau khi thử cách làm mới, nhóm cần **hai loại bằng chứng tách biệt**:

1. **Thực thi:** action đã làm đúng phạm vi hay chưa?
2. **Hiệu quả:** vấn đề đã giảm theo mục tiêu và rủi ro/tác dụng phụ có được kiểm soát không?

### Ví dụ thử chính sách review

| Câu hỏi | Tín hiệu | Giới hạn cần nhớ |
| --- | --- | --- |
| Action có thực hiện? | Có chính sách review và lịch sử PR được xử lý theo chính sách | Có tài liệu không chứng minh đã làm trong thực tế |
| Thời gian chờ có giảm? | Trung vị/P85 chờ review trước và sau | Cần loại PR tương tự và cùng cách đo |
| Dòng công việc có nhanh hơn? | Cycle time của story từ bắt đầu đến Done | Nếu chỉ chuyển chờ sang Test, kết quả tổng có thể không đổi |
| Chất lượng có giữ? | Lỗi hồi quy, incident, kết quả DoD | Số lỗi ít không chứng minh không có lỗi chưa phát hiện |
| Có tác dụng phụ? | Mức gián đoạn, tỷ lệ phải review lại, áp lực làm việc | Tốc độ tốt hơn không đáng nếu gây kiệt sức |
| Kết quả có bền? | Quan sát thêm vài chu kỳ sau khi chuẩn hóa | Thử hai ngày có thể chưa đủ phản ánh xu hướng |

### Ví dụ phép so sánh minh họa

Giả sử hai giai đoạn có **24 PR tương đương** mỗi giai đoạn, cùng định nghĩa:

~~~text
Trước thử:
  Median waiting for first actionable review = 1,8 ngày
  P85 waiting = 3,6 ngày

Sau thử:
  Median waiting for first actionable review = 0,9 ngày
  P85 waiting = 2,4 ngày

Giảm tương đối trung vị = (1,8 - 0,9) / 1,8 × 100% = 50%
Giảm tương đối P85     = (3,6 - 2,4) / 3,6 × 100% ≈ 33,3%
~~~

Các số trên **hoàn toàn minh họa**. Chúng là tín hiệu ban đầu, **không tự chứng minh** chính sách gây ra thay đổi. Có thể đồng thời có thêm người review, story nhỏ hơn, ít việc khẩn hơn hoặc cách đo dữ liệu khác. Hãy kiểm tra bối cảnh và guardrail trước khi mở rộng.

### Chỉ số dẫn dắt và chỉ số kết quả

**Leading indicator** như “phần trăm PR có feedback trong vòng một ngày” có thể cho tín hiệu sớm về chính sách. **Lagging indicator** như “lỗi hồi quy sau phát hành” hoặc “lead time end-to-end” cho thấy tác động muộn hơn. Không nên đánh giá chỉ bằng một chỉ số vì nó có thể bị tối ưu lệch.

## 12. Vòng PDCA/PDSA để thử – học – điều chỉnh

Tư duy **Plan – Do – Check – Act (PDCA)** hoặc biến thể **Plan – Do – Study – Act (PDSA)** cung cấp cấu trúc đơn giản để cải tiến có căn cứ.

| Bước | Câu hỏi | Đầu ra hữu ích |
| --- | --- | --- |
| **Plan** | Vấn đề nào, giả thuyết nào, phạm vi nào, cách đo và guardrail nào? | Thẻ action có owner, baseline, thời điểm xem lại |
| **Do** | Thử thay đổi trong phạm vi đã chọn như thế nào? | Bằng chứng áp dụng, sự kiện bất thường được ghi nhận |
| **Check/Study** | Điều gì thay đổi; dữ liệu có ủng hộ giả thuyết không? | Kết quả, độ bất định và các tác dụng phụ |
| **Act** | Giữ, chuẩn hóa, điều chỉnh hay dừng? | Quyết định và bước tiếp theo với trách nhiệm rõ |

~~~mermaid
flowchart LR
    A["PLAN: Vấn đề + giả thuyết + phép đo"] --> B["DO: Thử trong phạm vi nhỏ"]
    B --> C["STUDY: Đối chiếu bằng chứng + guardrail"]
    C --> D{"Quyết định"}
    D -->|"Hữu ích"| E["ADOPT: Chuẩn hóa có điều kiện"]
    D -->|"Chưa rõ"| F["ADJUST: Thay giả thuyết/cách đo"]
    D -->|"Không hiệu quả"| G["STOP: Ghi điều học được"]
    E --> A
    F --> A
    G --> A
~~~

### Thử nhỏ không đồng nghĩa thử tùy tiện

Ví dụ, áp dụng chính sách Review/Test mới cho các story tiêu chuẩn có thể là một thử nghiệm an toàn. Nhưng thử giảm kiểm tra quyền truy cập cho một phần học viên thật để “xem có nhanh hơn không” là **không phù hợp**, vì guardrail an toàn không được đem ra đánh đổi.

### Kết quả “không hiệu quả” vẫn có thể là học hỏi

Nếu thử phiên Three Amigos hằng ngày làm tăng thời gian họp mà không giảm câu hỏi muộn, nhóm có thể **dừng hoặc giới hạn phiên chỉ cho PBI rủi ro cao**. Đánh dấu action “Stopped – giả thuyết không được hỗ trợ” kèm bằng chứng **tốt hơn** giữ một nghi thức không tạo giá trị vì sợ bị coi là thất bại.

## 13. Nhịp kiểm tra hành động trong Scrum và công việc hằng ngày

Không cần một sự kiện Scrum mới chỉ để theo dõi improvement. Có thể dùng nhịp có sẵn, miễn phù hợp thời điểm ra quyết định.

| Nhịp/cơ hội | Hỏi điều gì? | Điều không nên biến thành |
| --- | --- | --- |
| **Trong khi thực hiện hằng ngày** | Action có blocker? Có cần phối hợp hoặc chỉnh phạm vi ngay không? | Báo cáo từng giờ về người sở hữu action |
| **Daily Scrum** | Cải tiến đang thực hiện có ảnh hưởng tới kế hoạch tiến tới Sprint Goal? Developers cần phối hợp ra sao? | Cuộc họp trạng thái gửi lên cấp trên |
| **Sprint Planning** | Có công việc cải tiến quan trọng cần đưa vào kế hoạch Sprint, có đủ năng lực và liên quan mục tiêu không? | Cố nhồi tất cả action cũ vào Sprint |
| **Sprint Review** | Thay đổi cách làm có giúp Increment/value hoặc phản hồi stakeholder tốt hơn? | Một cuộc postmortem kỹ thuật dài cho mọi action |
| **Sprint Retrospective** | Hành động trước đã thực hiện chưa, dữ liệu nói gì, nên giữ/đổi/dừng? | Nơi lập thêm danh sách mới mà quên danh sách cũ |
| **Buổi review cải tiến theo tuần/chu kỳ** | Những action chưa đến mốc hoặc cần người ngoài xử lý đang ra sao? | Một lớp họp thừa không đưa ra quyết định |

### Cách mở đầu một Retrospective hữu ích

Trước khi chọn ý tưởng mới, nhóm có thể dành vài phút xem lại **một hoặc hai action quan trọng từ lần trước**:

- Đã thực hiện đúng phạm vi thử chưa?
- Có bằng chứng gì mới, kể cả kết quả trái kỳ vọng?
- Điều gì cản trở, có cần giúp ngay không?
- Quyết định tiếp theo là gì; ai theo dõi?

Sau đó mới bàn vấn đề mới. Cách này tạo **vòng học hỏi liên tục** thay vì một chuỗi cuộc họp độc lập.

### Cải tiến có thể đi vào Sprint Backlog nhưng không thay mục tiêu Sprint

Một số thay đổi như sửa pipeline CI hoặc tách logic dùng chung có thể cần công việc kỹ thuật rõ ràng. Scrum Team cần cân nhắc tác động tới Sprint Goal, chất lượng và năng lực. Không nên xem action cải tiến như **công việc “lúc rảnh mới làm” không ai tính**, cũng không nên dùng nó để né các Product Backlog Items quan trọng mà không trao đổi minh bạch.

## 14. Kanban: nhìn hành động cải tiến như một dòng công việc

Nếu nhóm dùng Kanban cho delivery, có thể áp dụng cùng tư duy **minh bạch, WIP và quản lý tuổi công việc** cho cải tiến.

### Ví dụ board cải tiến gọn

~~~text
PROPOSED          SELECTED (WIP <= 2)     IN PROGRESS (WIP <= 2)
IMP-018           IMP-014                 IMP-011
IMP-019           IMP-016
IMP-020

EVIDENCE PENDING (WIP <= 2)                REVIEW / DECISION
IMP-009                                   IMP-006

ADOPTED / ADJUSTED / STOPPED
IMP-002 (Adopted)
IMP-004 (Stopped; học được nguyên nhân)
~~~

Các giới hạn 2 chỉ là **ví dụ**, không phải chuẩn của Kanban hay Scrum. Nhóm có thể dùng cùng bảng với công việc sản phẩm, miễn là **nhìn thấy được ai đang thực sự làm và thứ gì đang chờ bằng chứng**.

### Hai chỉ số cần xem ngoài “bao nhiêu action đã đóng”

**Work item age:** hành động cải tiến đã ở trong luồng bao lâu mà chưa đến quyết định? Nếu IMP-009 nằm ở Evidence Pending quá lâu, cần hỏi mốc review hoặc nguồn dữ liệu nào đang thiếu.

**Throughput của action có quyết định:** bao nhiêu thử nghiệm đã đến điểm **giữ/đổi/dừng với bằng chứng** trong một kỳ? Nó khác số task kỹ thuật được tick Done, và không nên trở thành mục tiêu “đóng càng nhiều càng tốt”.

### Tránh cải tiến tự tạo thêm WIP không kiểm soát

Nhóm có thể rất nhiệt tình khởi động năm công cụ mới, hai quy trình review và ba dashboard. Kết quả là thêm nhiều thay đổi đồng thời nên **khó biết giải pháp nào có ích**, người làm liên tục chuyển tác vụ và chất lượng delivery giảm. Giới hạn số thử nghiệm đồng thời giúp tăng khả năng **hoàn tất và rút ra kết luận**.

## 15. XP, Lean và cải tiến kỹ thuật cần bằng chứng

Một số vấn đề cải tiến có tính kỹ thuật sâu: TDD thiếu, CI chậm, test flaky, refactor nhiều rủi ro hoặc lỗi lọt production.

### Với XP

Các thực hành như **TDD, Continuous Integration, refactoring, pair programming và tích hợp thường xuyên** có thể được thử theo vấn đề cụ thể:

- Nếu lỗi quy tắc đơn giản lặp lại, thử TDD trên một module có hành vi thuần, kiểm tra chất lượng test và lỗi hồi quy.
- Nếu PR dài dẫn tới lỗi tích hợp, thử tích hợp các thay đổi nhỏ và xem lead time cùng tỷ lệ lỗi.
- Nếu test flaky, tập trung vào một nhóm test gây mất niềm tin trong CI, theo dõi lần chạy thất bại không ổn định.

Không cần “cài đặt toàn bộ XP trong một Sprint”. Hãy bắt đầu bằng **giả thuyết phù hợp nguyên nhân và khả năng áp dụng thực tế**.

### Với Lean/Kaizen

**Kaizen** thúc đẩy những cải tiến nhỏ, thường xuyên và dựa trên thực tế làm việc. **Lean** nhấn mạnh dòng giá trị tổng thể, giảm thời gian chờ, công việc dở và làm lại. Vì vậy, nếu mục tiêu là giảm thời gian người học chờ nhận tính năng, **đừng chỉ tối ưu số dòng code được viết mỗi ngày**; hãy theo dõi hàng đợi, phụ thuộc và chất lượng đầu-cuối.

### Kết hợp kỹ thuật với kết quả người dùng

Một action “bổ sung contract tests cho API quyền học” có thể được xác minh bằng khả năng phát hiện sai khác hợp đồng trước khi merge. Lợi ích dài hạn hơn có thể là **ít lỗi quyền khi release và ít thời gian sửa tương thích**, cần được quan sát cùng thời gian và rủi ro phù hợp. Một test mới xanh **không tự chứng minh người dùng học tốt hơn**, nhưng là một phần cần thiết để giao giá trị an toàn.

## 16. Case study: cải tiến liên tục luồng “Tiếp tục học”

### 16.1. Bối cảnh và đường cơ sở

Một nhóm phát triển nền tảng học có vấn đề: học viên phản hồi rằng tính năng “Tiếp tục học” đến chậm hơn kỳ vọng. Trong sáu tuần quan sát, nhiều story hoàn tất muộn vì đợi xác nhận quy tắc và review liên nhóm.

Dữ liệu **hoàn toàn minh họa**:

| Tín hiệu | Đường cơ sở giả định | Ghi chú |
| --- | ---: | --- |
| User story tiêu chuẩn hoàn tất trong kỳ | 18 | Cùng quy tắc bắt đầu và Done |
| Story từng bị chặn do thiếu quy tắc nghiệp vụ | 9/18 | Có bản ghi blocker |
| Trung vị cycle time | 12 ngày lịch | Từ Work Started tới DoD |
| Trung vị thời gian chờ review | 2,2 ngày lịch | Từ Ready for Review tới feedback hữu ích đầu |
| Số lỗi quyền/progress lọt production | 2 defect đã xác nhận | Không đủ để suy ra xu hướng dài hạn |

Nhóm không quyết định ngay “thêm một ngày refinement”. Họ chọn **hai giả thuyết có phạm vi rõ**, vì vấn đề có thể đến từ cả quyết định nghiệp vụ muộn và hàng đợi review.

### 16.2. Hai hành động cải tiến được chọn

| ID | Giả thuyết | Hành động trong thử nghiệm | Owner theo dõi | Cách đánh giá |
| --- | --- | --- | --- | --- |
| **IMP-021** | Làm rõ ví dụ chấp nhận gần lúc thực hiện sẽ giảm blocker nghiệp vụ | Thử Three Amigos ngắn cho tối đa 6 story rủi ro cao trước khi kéo vào In Progress | Đại diện nghiệp vụ được ủy quyền, phối hợp Developers/tester | Số story chờ câu trả lời muộn, thời gian chuẩn bị và feedback |
| **IMP-022** | Review thay đổi nhỏ theo pull policy sẽ giảm thời gian chờ | Giới hạn WIP Review/Test, ưu tiên giúp PR đang chờ thay vì bắt đầu story mới | Một Developer làm đầu mối, phối hợp cả nhóm | Median/P85 waiting, cycle time, lỗi hồi quy |

Lưu ý: người được chỉ định **chịu trách nhiệm theo dõi và đưa bằng chứng**, không phải chịu lỗi nếu metric không cải thiện. Nhóm cần có quyền điều chỉnh chính sách review và kênh quyết định nghiệp vụ phù hợp.

### 16.3. Một dòng thời gian hành động minh họa

| Thời điểm tương đối | IMP-021 | IMP-022 |
| --- | --- | --- |
| **Retrospective N** | Chọn giả thuyết và owner | Chọn chính sách thử và guardrail |
| **Tuần đầu** | Chạy phiên làm rõ đầu tiên; phát hiện thuật ngữ “đã hoàn thành” chưa thống nhất | Đặt WIP limit; bắt đầu ghi thời gian chờ review |
| **Tuần thứ hai** | Điều chỉnh mẫu acceptance criteria, không ép story đơn giản qua phiên dài | Giảm kích thước PR; ghi tình huống review bị chặn |
| **Retrospective N+1** | Xem blocker nghiệp vụ và thời gian làm rõ | Xem phân phối waiting/cycle time và lỗi |
| **Sau quyết định** | Chuẩn hóa phiên theo loại story nếu có ích | Giữ/đổi WIP limit và cập nhật chính sách review |

**Tối quan trọng:** action chỉ có thể được đóng với trạng thái **“đã xác minh quyết định”** sau khi có bằng chứng đủ để nhóm chọn giữ/điều chỉnh/dừng; việc chạy buổi họp hoặc đổi cấu hình board **chưa đủ để tuyên bố đã cải tiến**.

### 16.4. Kết quả giả định sau thử

Giả sử nhóm quan sát thêm 16 story tiêu chuẩn có cách đo tương tự:

| Tín hiệu | Trước thử | Sau thử | Nhận xét |
| --- | ---: | ---: | --- |
| Story có blocker nghiệp vụ | 9/18 = 50% | 4/16 = 25% | Giảm 25 điểm phần trăm trong dữ liệu quan sát |
| Trung vị cycle time | 12 ngày | 9 ngày | Giảm 25% tương đối |
| Trung vị chờ review | 2,2 ngày | 1,2 ngày | Giảm khoảng 45,5% tương đối |
| Lỗi quyền/progress production | 2 | 1 | Quá ít để kết luận xu hướng đáng tin |
| Thời gian làm rõ trung bình | Chưa có baseline tốt | Có ghi trong giai đoạn thử | Chưa đủ để biết tổng chi phí làm rõ thay đổi ra sao |

**Không được kết luận** hai action đã tạo ra toàn bộ mức giảm từ bảng trước/sau: số mẫu nhỏ, story có thể khác độ khó, nhân sự và lượng yêu cầu có thể thay đổi. Nhóm cần xem **mẫu công việc, yếu tố gây nhiễu, guardrail và phản hồi người dùng**, sau đó quyết định có mở rộng hay điều chỉnh.

### 16.5. Quyết định cải tiến có căn cứ

Một quyết định hợp lý có thể là:

- **IMP-021 – Adopt with refinement:** tiếp tục dùng phiên Three Amigos ngắn cho story có rủi ro nghiệp vụ cao; không bắt mọi PBI qua cuộc họp dài.
- **IMP-022 – Continue experiment:** giữ chính sách review thêm một chu kỳ với cùng cách đo vì kết quả ban đầu tích cực, nhưng cần xem P85 và tác dụng phụ trước khi chuẩn hóa.
- **Guardrail:** tiếp tục theo dõi lỗi quyền, dữ liệu tiến độ, mức độ gián đoạn và các tình huống Sprint Goal bị ảnh hưởng.

Quyết định “tiếp tục thử vì chưa đủ bằng chứng” **cũng là quyết định**, miễn có thời hạn, người theo dõi và điều kiện xem lại rõ ràng.

## 17. Theo dõi một action từ phản hồi lỗi production tới phòng ngừa

Giả sử học viên gửi hai request ghi danh đồng thời và nhận **hai đăng ký hiệu lực** cho một khóa. Nhóm khôi phục dữ liệu, sửa lỗi và xác nhận đã ngừng tạo bản ghi trùng. Nếu chỉ dừng ở việc đóng bug, hệ thống có thể còn khoảng trống trong kiểm thử và quy tắc dữ liệu.

### Phân biệt việc phải làm ngay và hành động cải tiến

**Ứng phó sự cố/sửa lỗi bắt buộc:**

- Ngăn hệ thống tiếp tục tạo dữ liệu sai và đánh giá phạm vi ảnh hưởng.
- Sửa bất biến ở tầng lưu trữ/transaction hoặc cơ chế phù hợp.
- Khôi phục dữ liệu có kiểm soát, xác minh quyền học.
- Truyền thông và phối hợp theo chính sách vận hành/bảo mật.

**Hành động phòng ngừa sau sự cố:**

- Thêm **integration test concurrency** tái hiện hai yêu cầu đồng thời.
- Rà soát acceptance criteria cho retry và idempotency.
- Bổ sung telemetry phát hiện bất biến đăng ký trùng.
- Cập nhật cách review các thay đổi chạm transaction/dữ liệu.
- Thử rollout nhỏ khi thay đổi luồng ghi danh có rủi ro cao.

Những hoạt động đầu là **khắc phục rủi ro hiện tại**; những hoạt động sau là **cải tiến hệ thống để nhận biết và phòng ngừa tốt hơn**. Không được trì hoãn xử lý sự cố nguy hiểm chỉ để chờ cuộc họp chọn improvement.

### Ví dụ thẻ cải tiến cụ thể

~~~text
ID: IMP-030
Nguồn: Postmortem lỗi ghi danh trùng
Quan sát: Hai request đồng thời tạo hai enrollment ACTIVE
Giả thuyết: Integration test cùng bất biến DB sẽ phát hiện
             sai lệch này trước khi release
Hành động: Thêm test chạy hai request đồng thời, kiểm tra
           đúng một enrollment ACTIVE, đưa vào CI phù hợp
Owner: Developer phụ trách đầu mối, có người kiểm thử phối hợp
Điều kiện hoàn tất action:
  - Test chạy ổn định trên DB/môi trường phù hợp
  - Test đỏ khi cố tình tái tạo cơ chế lỗi trong môi trường thử
  - CI chạy test theo chính sách đã thỏa thuận
Guardrails:
  - Không cấp quyền sai
  - Không xóa nhầm dữ liệu đăng ký/tiến độ hợp lệ
Mốc xem lại: Sau khi có bằng chứng CI và một chu kỳ theo dõi thích hợp
Quyết định: Chưa có — chờ đối chiếu bằng chứng
~~~

### Không biến phản hồi lỗi thành danh sách vô tận

Sau một incident nghiêm trọng, nhóm có thể đề xuất hàng chục action. Nên **phân nhóm nguyên nhân, chọn các lớp phòng vệ có tác động rộng và ưu tiên rủi ro**, thay vì bổ sung một checklist cực dài cho mọi thay đổi. Một integration test kiểm tra **bất biến đăng ký duy nhất** có thể có giá trị tái sử dụng hơn mười test UI lặp cùng happy path.

## 18. Phối hợp cải tiến liên nhóm: ai sở hữu, ai có quyền quyết định?

Một nhóm khó giảm lead time nếu code review hoặc môi trường tích hợp phụ thuộc nhóm khác. Cải tiến có tác động toàn hệ thống cần **rõ người chịu trách nhiệm theo dõi, bên phối hợp và quyền thay đổi chính sách**.

### Ví dụ phụ thuộc ba nhóm

Trong nền tảng học:

- **Identity** quản lý xác thực và quyền truy cập.
- **Learning** quản lý tiến độ học.
- **Experience** xây hành trình hiển thị bài học.

Nếu lỗi contract giữa Learning và Experience thường chỉ xuất hiện sát release, một action cải tiến có thể là **thống nhất contract tests được chạy trong CI của cả hai bên**.

| Việc cần quyết định | Người/nhóm tham gia | Bằng chứng cần có |
| --- | --- | --- |
| Hợp đồng API nào phải ổn định? | Developers của bên cung cấp và tiêu thụ | Ví dụ request/response và chính sách versioning |
| Khi nào hợp đồng được kiểm tra? | Người phụ trách CI của các nhóm | Pipeline chạy đúng test khi thay đổi liên quan |
| Ai chịu trách nhiệm hành động tổng thể? | Một owner đầu mối được các bên thống nhất | Bản ghi action, blocker và trạng thái rõ |
| Khi có thay đổi phá tương thích? | Các nhóm tiêu thụ/cung cấp và người có quyền quyết định sản phẩm | Quy trình phối hợp và lựa chọn chuyển tiếp |
| Đánh giá hiệu quả thế nào? | Đại diện các nhóm, người xem chất lượng | Số lỗi contract, thời gian sửa, độ tin cậy pipeline |

### “Ai phụ trách?” chưa đủ

Một action có thể có owner là Developers của Experience nhưng họ **không có quyền tự sửa pipeline của Identity**. Khi đó cần ghi rõ:

- Quyết định và phụ thuộc nào nằm ngoài quyền owner.
- Người có thẩm quyền phê duyệt hoặc hỗ trợ.
- Mốc cần quyết định để tránh action bị treo.
- Cách nâng cấp vấn đề nếu phối hợp không thành công.

**Owner không nên bị coi là người thất bại** khi trở ngại liên nhóm không được giải quyết; điều quan trọng là đã nhận biết và đưa ra quyết định minh bạch đúng lúc hay chưa.

## 19. Cách báo cáo cải tiến để hỗ trợ quyết định, không tạo KPI ảo

Báo cáo hiệu quả không phải bảng càng nhiều cột càng tốt. Một bản tóm tắt có thể trả lời:

1. **Vấn đề nào đáng quan tâm?**
2. **Hành động nào được chọn và vì sao?**
3. **Hành động đã được thực hiện đến đâu?**
4. **Bằng chứng cho thấy điều gì thay đổi?**
5. **Rủi ro hoặc guardrail nào cần theo dõi?**
6. **Quyết định tiếp theo là gì và ai chịu trách nhiệm?**

### Ví dụ một bản cập nhật gọn

| ID | Mục tiêu | Trạng thái | Bằng chứng hiện có | Quyết định tiếp theo |
| --- | --- | --- | --- | --- |
| IMP-021 | Giảm blocker nghiệp vụ | Review | Tỷ lệ story có blocker trong mẫu quan sát giảm; cần xem thêm chi phí làm rõ | Giữ cho story rủi ro cao |
| IMP-022 | Giảm chờ review | Evidence Pending | Trung vị giảm nhưng P85 cần thêm dữ liệu | Thử thêm một chu kỳ |
| IMP-030 | Phòng ngừa đăng ký trùng | In Progress | Test concurrency đã viết, chưa đủ ổn định trong CI | Sửa môi trường test và xác minh lại |
| IMP-017 | Thay toàn bộ công cụ quản lý việc | Stopped | Không có bằng chứng vấn đề nằm ở công cụ; chi phí chuyển đổi cao | Giữ hiện tại, tập trung chính sách luồng |

### Những con số có thể xem, nhưng phải hiểu đúng

| Chỉ số cải tiến | Giá trị sử dụng | Sai lầm thường gặp |
| --- | --- | --- |
| **Action aging** | Nhìn action đang mở quá lâu hoặc chờ quyết định | Coi mọi action cũ là lỗi của owner |
| **Tỷ lệ action tới được quyết định** | Kiểm tra vòng học hỏi có kết thúc hay không | Đóng vội để đạt tỷ lệ đẹp |
| **Tỷ lệ action được áp dụng** | Hiểu bao nhiêu thử nghiệm hữu ích theo tiêu chí nhóm | Coi action dừng vì bằng chứng xấu là thất bại |
| **Cycle/lead time của công việc chính** | Biết cải tiến có ảnh hưởng dòng giá trị hay không | Dùng sự thay đổi không tương đương để chứng minh nhân quả |
| **Lỗi và chất lượng** | Kiểm tra guardrail | Chỉ đếm bug mà quên mức nghiêm trọng |
| **Outcome người dùng** | Kết nối cải tiến với giá trị sản phẩm | Suy từ output kỹ thuật sang outcome không có dữ liệu |

Đặc biệt, **action bị dừng vì đã chứng minh không có ích** có thể là một kết quả tốt: nhóm tránh duy trì chi phí của cách làm kém hiệu quả. Không nên tạo KPI “100% action phải Adopted” khiến mọi thử nghiệm đều bị báo thành công.

## 20. Các phản mẫu thường khiến hành động cải tiến bị quên hoặc phản tác dụng

| Phản mẫu | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| **Retro nào cũng tạo 10 action** | Nhiều WIP, ít việc tới kết luận | Chọn ít, có tác động và năng lực thực hiện |
| **Không có owner rõ** | Mọi người nghĩ người khác sẽ làm | Chỉ định đầu mối cùng người phối hợp và quyền quyết định |
| **Action chỉ là khẩu hiệu “giao tiếp tốt hơn”** | Không biết làm gì, kiểm chứng thế nào | Nêu hành động, phạm vi, thời điểm và bằng chứng |
| **Có deadline nhưng không có review kết quả** | Hoàn thành hoạt động rồi quên hiệu quả | Ghi mốc đánh giá sau khi thử |
| **Đánh Done ngay khi đổi cấu hình** | Không biết cải tiến có giúp gì không | Tách implemented khỏi evaluated/adopted |
| **Không có baseline hoặc định nghĩa metric thay đổi** | Số liệu trước/sau không so sánh được | Ghi ranh giới và nguồn dữ liệu ngay lúc chọn action |
| **Chỉ theo dõi số ticket hoàn thành** | Tối ưu output, che value và chất lượng | Dùng flow, quality và outcome làm bằng chứng |
| **Dùng chỉ số để phạt cá nhân** | Người làm che blocker và tạo số đẹp giả | Xem dữ liệu ở mức hệ thống, tìm phụ thuộc/chính sách |
| **Thử quá nhiều thay đổi cùng lúc** | Khó xác định điều gì có ích | Thử theo phạm vi nhỏ, ghi các thay đổi đồng thời |
| **Chọn giải pháp trước khi hiểu vấn đề** | Đổi công cụ mà điểm nghẽn vẫn còn | Mô tả quan sát và giả thuyết nguyên nhân |
| **Bỏ guardrail để giao nhanh** | Lỗi dữ liệu/bảo mật hoặc kiệt sức | Giữ DoD và điều kiện chất lượng bắt buộc |
| **Biến Retrospective thành nơi đổ lỗi** | Giảm chia sẻ sai lệch và near miss | Điều tra hệ thống, ngôn ngữ dựa trên bằng chứng |
| **Đợi Retro mới xử lý sự cố khẩn** | Tăng thiệt hại | Kích hoạt phản ứng sự cố ngay theo chính sách |
| **Đẩy mọi action lên Product Owner** | Chồng quyền và giảm tự chủ kỹ thuật | Phân biệt quyết định sản phẩm với cải tiến cách làm/thiết kế |
| **Cải tiến nằm ngoài kế hoạch và năng lực** | Liên tục bị hoãn bởi công việc khác | Đưa vào luồng, có WIP và thời gian phối hợp thực |
| **Chỉ thử trên một hạng mục rất dễ** | Khó suy sang luồng công việc bình thường | Ghi loại việc và điều kiện áp dụng |
| **Tính phần trăm từ mẫu quá nhỏ** | Kết luận chắc chắn giả tạo | Báo kích thước mẫu, độ bất định và bối cảnh |
| **Không chuẩn hóa sau khi thử thành công** | Kết quả biến mất khi người hỗ trợ rời nhóm | Ghi chính sách, người duy trì và cách xem lại |
| **Không dừng thử nghiệm vô ích** | Nghi thức mới tăng chi phí nhưng không có giá trị | Quyết định Stop/Adjust minh bạch |
| **Dùng một dashboard thật phức tạp** | Chi phí cập nhật lớn hơn giá trị quyết định | Bắt đầu từ thẻ action và vài tín hiệu có thể hành động |

## 21. Bài thực hành: biến Retrospective thành vòng cải tiến thật

### 21.1. Bối cảnh

Nhóm phát triển nền tảng học vừa trải qua ba Sprint. Retrospective thu được những thông tin:

1. **8 trong 14 user story** được làm gần đây bị chặn do thiếu ví dụ nghiệp vụ.
2. Trung vị thời gian chờ code review là **2,4 ngày lịch**, nhưng nhóm chưa lưu dữ liệu về P85.
3. Một lỗi cấp quyền lọt production sau khi sửa API; QA chỉ kiểm tra UI và unit tests.
4. Một Developer muốn thay toàn bộ công cụ quản lý công việc.
5. Học viên phản hồi nhiều trường hợp “Tiếp tục học” mở nhầm bài khi đổi thiết bị.
6. Retrospective trước đã quyết định “họp nhiều hơn” nhưng không ai nhớ có áp dụng không.

Nhóm có năng lực hạn chế; công việc phát hành khóa học mới vẫn quan trọng. Product Owner tham dự phiên làm rõ khi cần, Developers có quyền đề xuất chính sách review và kỹ thuật kiểm thử, một số thay đổi CI cần phối hợp với nhóm nền tảng.

### 21.2. Nhiệm vụ

1. Viết **hai phát biểu vấn đề** có bằng chứng, tránh quy kết cá nhân.
2. Chọn **không quá hai hành động cải tiến** để thử trước, nêu tiêu chí ưu tiên.
3. Với mỗi action, ghi **owner, người phối hợp, giả thuyết, phạm vi, mốc xem lại và bằng chứng thực thi**.
4. Chọn **baseline, một outcome và ít nhất một guardrail** cho từng action.
5. Vẽ hoặc mô tả luồng trạng thái từ **Proposed tới quyết định cuối**, phân biệt Implemented và Adopted.
6. Nêu công việc nào **không được chờ cuộc Retrospective tiếp theo**.
7. Giải thích vì sao đổi công cụ quản lý việc **chưa chắc** giảm cycle time.
8. Đề xuất cách dùng Scrum events và Kanban board để **giữ action xuất hiện trong công việc thật**.
9. Khi metric cải thiện nhưng lỗi production tăng, nhóm phải làm gì?
10. Nếu action không đạt mục tiêu sau hai chu kỳ, làm sao đóng mà vẫn rút được bài học?

### 21.3. Lời giải gợi ý: chọn vấn đề

**Vấn đề A – thiếu quy tắc trước khi thực hiện:** “Trong 14 story gần đây, 8 story bị chặn do phải xác nhận lại ví dụ nghiệp vụ sau khi bắt đầu. Tác động là làm gián đoạn luồng thực hiện và có thể kéo dài cycle time; chưa rõ cách chuẩn bị story hay độ sẵn sàng của người nghiệp vụ là nguyên nhân chính”.

**Vấn đề B – chờ review:** “Trong giai đoạn quan sát vừa qua, trung vị thời gian từ PR sẵn sàng review tới feedback hữu ích là 2,4 ngày lịch. Nhóm chưa có P85 và chưa rõ liệu PR lớn hoặc WIP cao đóng góp nhiều nhất”.

**Vấn đề C – cấp sai quyền** là rủi ro bắt buộc xử lý theo mức ảnh hưởng thực tế, không nên chờ chọn vào một bảng ưu tiên thông thường. Tương tự, cần kiểm tra sai lệch tiến độ đa thiết bị nếu có nguy cơ mất dữ liệu hoặc ảnh hưởng diện rộng.

### 21.4. Hai thẻ action mẫu

| Trường | IMP-A: Làm rõ sớm | IMP-B: Giảm chờ review |
| --- | --- | --- |
| **Owner** | Developer đầu mối refinement với đại diện nghiệp vụ | Developer đầu mối review |
| **Giả thuyết** | Ví dụ trước khi kéo việc giảm blocker do nghiệp vụ | Review thường xuyên với WIP nhỏ giảm chờ |
| **Hành động** | Thử phiên Three Amigos ngắn cho 5 story có quy tắc rủi ro cao | Thử chính sách review PR nhỏ, không mở thêm việc khi review đầy |
| **Phạm vi** | User story mới có nhiều ngoại lệ nghiệp vụ | PR cho story tiêu chuẩn, loại riêng sự cố khẩn |
| **Mốc xem lại** | Retrospective của chu kỳ tiếp theo | Sau hai tuần và một lần Retrospective |
| **Bằng chứng thực thi** | Ví dụ chấp nhận, câu hỏi và người chốt được ghi | Board có WIP, lịch sử review và quyết định |
| **Baseline** | 8/14 story bị chặn; cần thống nhất định nghĩa blocker | Median 2,4 ngày; cần thu thêm phân phối |
| **Outcome mong muốn** | Story chờ xác nhận muộn giảm mà tổng thời gian chuẩn bị hợp lý | Chờ review/cycle time giảm và PR vẫn dễ bảo trì |
| **Guardrail** | Không thêm quá nhiều nghi thức hoặc bỏ sót rủi ro quyền | Không tăng lỗi hồi quy, không giảm DoD |
| **Quyết định cuối** | Giữ/điều chỉnh/dừng sau khi có bằng chứng | Giữ/điều chỉnh/dừng sau khi có bằng chứng |

Đây là **đề xuất thử**, không phải cam kết kết quả đã chắc chắn. Nếu nhóm đang bị ảnh hưởng bởi lỗi quyền nghiêm trọng, cần ưu tiên khôi phục và phòng ngừa liên quan trước các thí nghiệm tối ưu tốc độ.

### 21.5. Mẫu quyết định sau thử

~~~text
Hành động: IMP-A
Đã thực hiện theo phạm vi thử? Có, 5 story rủi ro cao
Bằng chứng quan sát:
  - Những câu hỏi về trạng thái PENDING/ACTIVE được làm rõ sớm
  - 1 trong 5 story thử vẫn bị chặn vì thiếu quyết định liên nhóm
  - Thời gian chuẩn bị tăng nhưng chưa có dữ liệu so sánh đủ tốt
Guardrails:
  - Không phát hiện tác động xấu về phân quyền trong tập thử
  - Chưa đủ thời gian quan sát lỗi hậu phát hành
Giới hạn kết luận:
  - Mẫu nhỏ, độ khó story khác nhau, không xác nhận quan hệ nhân quả
Quyết định: Điều chỉnh
Bước tiếp: Thử ở một chu kỳ khác cho story có phụ thuộc liên nhóm,
           nêu người có quyền chốt trước khi thực hiện
Owner và mốc xem lại: Đã thống nhất trong cuộc review
~~~

Một action được đánh **Adjusted** ở đây không phải “không đạt KPI”. Nhóm đã có bài học cụ thể: không chỉ cần ví dụ nghiệp vụ, còn cần **người ra quyết định cho phụ thuộc liên nhóm**.

### 21.6. Trường hợp nguy hiểm: tốc độ đẹp nhưng chất lượng xấu

Giả sử sau chính sách review nhanh, median chờ review giảm 50% nhưng lỗi quyền production tăng. Không được tuyên bố cải tiến thành công chỉ từ chỉ số chờ. Cần **điều tra và xử lý rủi ro chất lượng**, xem liệu review bị làm qua loa, test bị bỏ, story khác mức phức tạp hay có thay đổi khác đồng thời. Có thể dừng thử, điều chỉnh chính sách, khôi phục kiểm soát cần thiết và đo lại.

## 22. Checklist sử dụng khi theo dõi hành động cải tiến

- [ ] Quan sát được mô tả bằng **sự kiện/bằng chứng**, không bằng lời quy kết cá nhân?
- [ ] Vấn đề có liên hệ tới **giá trị người dùng, chất lượng hoặc flow**?
- [ ] Đã phân biệt **quan sát, giả thuyết, action, output, outcome và guardrail**?
- [ ] Người có quyền quyết định/đại diện nghiệp vụ được tham gia khi có quy tắc mơ hồ?
- [ ] Hành động đủ cụ thể để biết **làm gì, trên phạm vi nào và khi nào**?
- [ ] Có **một owner/đầu mối theo dõi rõ**, kèm người phối hợp và phụ thuộc?
- [ ] Owner có khả năng xử lý hoặc **kênh nâng cấp blocker vượt quyền**?
- [ ] Có đường cơ sở với **ranh giới đo, loại việc, thời gian và nguồn dữ liệu** nhất quán?
- [ ] Có điều kiện **đã triển khai action** tách biệt khỏi **đã xác minh hiệu quả**?
- [ ] Có chỉ số outcome hoặc bằng chứng học hỏi phù hợp với loại hành động?
- [ ] Các guardrail về **DoD, bảo mật, dữ liệu, vận hành và nhịp làm việc bền vững** được giữ?
- [ ] Hành động được đưa vào **công việc thật/Sprint Backlog/chính sách luồng**, không chỉ biên bản?
- [ ] Số cải tiến đang thử phù hợp **năng lực và WIP** của nhóm?
- [ ] Hành động khẩn cấp về sự cố/an toàn **không bị trì hoãn để chờ Retrospective**?
- [ ] Có mốc xem lại, nguồn bằng chứng và người sẽ đưa quyết định?
- [ ] Work item age của những action đang mở có được nhìn thấy để tránh treo lâu?
- [ ] Tại mỗi lần review, nhóm chọn **Adopt, Adjust, Continue with a date hoặc Stop**, không chỉ “để đó”?
- [ ] Nếu kết quả không tốt, nhóm ghi **điều học được** thay vì ép báo thành công?
- [ ] Nếu cách làm mới hiệu quả, có cách **chuẩn hóa và duy trì trong hoạt động thường ngày**?
- [ ] Không dùng số action đóng, story point hoặc metric cải tiến làm thước đo xếp hạng cá nhân?
- [ ] Bằng chứng tác dụng có được xem cùng **phản hồi người dùng và chất lượng sản phẩm**?
- [ ] Cải tiến đã được đánh giá lại khi bối cảnh, kiến trúc hoặc nhu cầu sản phẩm thay đổi?

**Ghi nhớ:** **Cải tiến liên tục không phải chuỗi ý tưởng trong các buổi họp, mà là chuỗi quyết định và thay đổi được thực hiện, đo lường và học hỏi trong công việc thật.** Một action có ích cần **vấn đề rõ, owner, phạm vi thử, mốc xem lại, bằng chứng hành động, outcome và guardrail**. Khi nhóm biết duy trì, điều chỉnh hoặc dừng dựa trên bằng chứng, các thực hành Scrum, Kanban, XP và Lean mới thực sự hỗ trợ **giao sản phẩm tăng dần, giảm lãng phí, bảo vệ chất lượng và thích ứng qua phản hồi sớm**.
