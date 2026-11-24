# Xác định người thực hiện, thời hạn và cách đo hiệu quả cải tiến

## 1. Vì sao có nhiều ý tưởng cải tiến nhưng cách làm không thay đổi?

Một Scrum Team vừa kết thúc Sprint Retrospective của nền tảng học trực tuyến. Nhóm nhận ra ba vấn đề lặp lại:

- User story thường chờ người hiểu nghiệp vụ trả lời quá lâu.
- Các thay đổi giao diện và backend chỉ được tích hợp sát cuối Sprint.
- Lỗi đã xảy ra lại tái xuất hiện vì kiểm thử hồi quy chưa bao phủ tình huống quan trọng.

Cuộc họp diễn ra tích cực. Mọi người thống nhất: “Cần giao tiếp sớm hơn”, “Cần tăng chất lượng” và “Cần cải thiện CI”. Nhưng hai Sprint sau, các vấn đề vẫn gần như cũ. Không ai chắc người nào sẽ thực hiện bước đầu tiên, bao giờ cần hoàn thành hoặc dựa vào bằng chứng nào để biết cách làm mới có hiệu quả.

Điểm thiếu không nhất thiết là **thiếu ý thức cải tiến**. Nhóm đã dừng ở **nhận diện vấn đề và mong muốn thay đổi**, chưa chuyển nó thành một **hành động có trách nhiệm, thời hạn, tiêu chí hoàn thành và cách kiểm tra kết quả**.

Một cải tiến thực dụng cần trả lời đồng thời:

1. **Cải thiện điều gì và vì sao?** Vấn đề, tác động, giả thuyết nguyên nhân.
2. **Ai đưa hành động tới kết quả?** Người chịu trách nhiệm điều phối, người thực hiện và người hỗ trợ.
3. **Làm gì, đến khi nào?** Bước cụ thể, giới hạn phạm vi, ngày đến hạn và điểm kiểm tra.
4. **Làm sao biết đã làm xong?** Bằng chứng đầu ra của hành động.
5. **Làm sao biết cách làm mới tốt hơn?** Chỉ số kết quả, baseline, mục tiêu, guardrail và thời điểm đánh giá.
6. **Nếu không hiệu quả thì sao?** Cách học lại, điều chỉnh, dừng hoặc thử phương án khác.

Bài học thuộc chương **Cải tiến liên tục** trong module **AGILE_DEVELOPMENT**. Trong Agile, phản hồi sớm, giao phần giá trị tăng dần và cải tiến cách phối hợp không chỉ áp dụng cho tính năng. Chúng còn áp dụng cho **chính hệ thống làm việc của nhóm**, từ user story, backlog và Scrum đến Kanban, XP và đo lường flow.

### Kết quả học tập

Sau bài này, người học có thể:

- Chuyển một phát hiện từ retrospective hoặc số liệu flow thành **hành động cải tiến cụ thể, đủ nhỏ và kiểm chứng được**.
- Phân biệt **người chịu trách nhiệm đưa cải tiến tới kết quả (owner)** với người thực hiện, người hỗ trợ và người có quyền phê duyệt.
- Đặt **ngày bắt đầu, ngày cần hoàn thành đầu ra, mốc kiểm tra và cửa sổ đo kết quả** phù hợp.
- Thiết kế phép đo có **định nghĩa, baseline, target, nguồn dữ liệu, thời gian và guardrails**.
- Dùng các vòng **Plan–Do–Check–Act (PDCA)** hoặc thử nghiệm nhỏ để đánh giá hiệu quả thay vì chỉ đánh dấu một ticket Done.
- Gắn việc cải tiến vào Product Backlog, Sprint Backlog hoặc dòng công việc Kanban một cách đúng vai trò và năng lực.
- Nhận diện anti-pattern như “mọi người cùng chịu trách nhiệm nên không ai làm”, deadline tượng trưng, metric gaming và đổ lỗi cá nhân.

## 2. Phân biệt vấn đề, giả thuyết, hành động, đầu ra và hiệu quả

Một câu “Cần giảm thời gian chờ review” chứa **mục tiêu**, chưa phải kế hoạch. Để làm rõ, nhóm nên tách những khái niệm sau.

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Hiện trạng/vấn đề** | Điều gì đang xảy ra, gây hậu quả gì? | PBI thường chờ xem xét pull request 2–3 ngày, làm hạng mục dồn cuối Sprint. |
| **Bằng chứng ban đầu** | Chúng ta dựa vào quan sát hoặc dữ liệu nào? | Trong 14 PR gần nhất, trung vị từ lúc yêu cầu review đến phản hồi đầu tiên là 21 giờ làm việc. |
| **Giả thuyết nguyên nhân** | Vì sao việc đó có thể xảy ra? | Người review không được báo rõ, ai cũng bận nhiều việc; trách nhiệm phản hồi chưa được thỏa thuận. |
| **Giả thuyết cải tiến** | Nếu đổi cách làm, điều gì có thể thay đổi? | Nếu có người nhận review theo ca trong giờ làm và giới hạn PR lớn, thời gian chờ phản hồi sẽ giảm. |
| **Hành động** | Đội sẽ thử làm gì cụ thể? | Thử cơ chế nhận review rõ người, phản hồi trong khung làm việc đã đồng thuận, kiểm tra lại sau 2 tuần. |
| **Đầu ra của hành động** | Dấu hiệu nào cho thấy thí nghiệm đã được thực hiện? | Thỏa thuận review được công bố; nhánh thử áp dụng cho các PR đủ điều kiện; dữ liệu thời điểm được thu. |
| **Kết quả (outcome)** | Dòng làm việc có thực sự tốt hơn? | Trung vị thời gian chờ review giảm; PBI ít bị chặn ở bước review. |
| **Guardrail** | Điều gì không được xấu đi? | Lỗi hồi quy nghiêm trọng, gánh nặng review, thời gian tập trung và chất lượng phản biện không suy giảm. |
| **Quyết định sau thử nghiệm** | Tiếp tục, điều chỉnh hay bỏ? | Sau khi đo đủ dữ liệu, duy trì cơ chế, sửa phạm vi hoặc thử giả thuyết khác. |

Đặc biệt cần phân biệt:

- **Hoàn thành hành động:** đã áp dụng chính sách review mới đúng phạm vi.
- **Hoàn thành đánh giá:** đã thu và phân tích dữ liệu sau khi áp dụng.
- **Đạt hiệu quả:** có bằng chứng phù hợp rằng cách làm mới giúp cải thiện mục tiêu mà không gây tác dụng phụ không chấp nhận được.

Ba trạng thái trên **không đồng nghĩa nhau**. Việc đóng ticket “Tạo bảng review” chỉ chứng minh một đầu ra đã có, chưa cho biết thời gian chờ giảm.

### 2.1. Một cải tiến có thể tạo ra học hỏi dù không đạt mục tiêu

Giả sử sau hai tuần thử cơ chế review, thời gian chờ vẫn không giảm. Đội quan sát rằng nguyên nhân chính không phải người nhận review, mà là PR quá lớn và các kiểm thử tích hợp mất nhiều giờ.

Thử nghiệm ban đầu **không đạt outcome kỳ vọng**, nhưng đã giúp loại bỏ một giả thuyết và tìm nút thắt thực. Khi được ghi nhận trung thực, đó vẫn là một vòng học hỏi có giá trị.

Không nên báo “thành công” chỉ vì đã thực hiện đúng kế hoạch, cũng không nên gọi người phụ trách “thất bại” khi một giả thuyết được kiểm chứng và bị bác bỏ.

## 3. Chu trình cải tiến: từ phát hiện tới bằng chứng và thích ứng

**Plan–Do–Check–Act (PDCA)** là một mô hình hữu ích để quản lý vòng thử nghiệm cải tiến:

- **Plan:** xác định vấn đề, baseline, giả thuyết, hành động, người phụ trách, thời hạn và cách đo.
- **Do:** thử thay đổi với phạm vi có thể kiểm soát, ghi nhận việc đã thực hiện và ngoại lệ.
- **Check:** so sánh kết quả thực với baseline, mục tiêu và guardrails; xem giới hạn dữ liệu.
- **Act:** chuẩn hóa cách làm nếu phù hợp, điều chỉnh thử nghiệm hoặc dừng và chọn giả thuyết mới.

~~~mermaid
flowchart TD
    A["Phát hiện vấn đề từ Retro, flow, lỗi, người dùng"] --> B["Plan: giả thuyết, owner, hạn, baseline, chỉ số"]
    B --> C["Do: thử thay đổi nhỏ, có bằng chứng"]
    C --> D["Check: đo outcome và guardrails"]
    D --> E{"Hiệu quả và an toàn có đủ bằng chứng?"}
    E -->|Có| F["Act: duy trì, ghi thỏa thuận, mở rộng nếu phù hợp"]
    E -->|Chưa rõ| G["Bổ sung dữ liệu hoặc thử lại có điều chỉnh"]
    E -->|Không| H["Dừng/sửa giả thuyết, học từ kết quả"]
    F --> I["Xem lại hiệu quả sau khi vận hành"]
    G --> B
    H --> B
    I --> A
~~~

PDCA không bắt buộc mọi đội tổ chức bốn cuộc họp riêng. Một đội nhỏ có thể dùng một action card và vài lần kiểm tra trong nhịp làm việc hiện có. Quan trọng là **đi từ ý tưởng tới hành động có bằng chứng, rồi thực sự dùng bằng chứng để thay đổi**.

### 3.1. Cải tiến liên tục không phải một dự án phụ vô hạn

Nếu đội chỉ thêm danh sách “cần cải tiến” nhưng không phân bổ năng lực, việc mới sẽ cạnh tranh ngầm với user story, sửa lỗi và vận hành. Nên chọn **một vài thay đổi ưu tiên cao**, thực hiện tới nơi tới chốn và kiểm tra kết quả trước khi mở thêm hàng loạt thử nghiệm.

### 3.2. Không cần đợi tới cuối Sprint mới xử lý sự cố nghiêm trọng

Scrum Retrospective là thời điểm quan trọng để cải tiến chất lượng và hiệu quả, nhưng khi một lỗi bảo mật đang bị khai thác hoặc một sự cố dữ liệu gây hậu quả, đội phải dùng quy trình ứng phó phù hợp **ngay khi cần**. Chu trình cải tiến có thể bổ sung các biện pháp phòng ngừa về sau; nó không thay thế ứng phó khẩn cấp.

## 4. Chọn cải tiến đáng làm trước khi gán người và ngày

Không phải mọi ý kiến trong Retro đều cần biến thành ticket. Một nhóm có thể nêu 15 vấn đề, nhưng chỉ đủ năng lực thử 1–2 thay đổi có ý nghĩa trong giai đoạn tiếp.

### 4.1. Đánh giá lợi ích, rủi ro và khả năng thực hiện

Hãy hỏi:

1. Vấn đề có đang **lặp lại, gây chậm dòng công việc hoặc hại người dùng**?
2. Có **bằng chứng cụ thể** hay hiện chỉ là cảm nhận? Nếu chưa đủ, cần điều tra gì?
3. Thay đổi có khả năng tạo **cải thiện đáng kể** trong phạm vi nhỏ?
4. Chi phí áp dụng và duy trì cách làm mới là bao nhiêu?
5. Có cần quyền, tài nguyên hoặc một đội ngoài để thực hiện?
6. Chúng ta có thể **đo được tín hiệu sau thử nghiệm** trong thời gian hợp lý?
7. Có nghĩa vụ an toàn/bảo mật bắt buộc cần được xử lý bất kể thứ tự ưu tiên?

Một bảng chọn sơ bộ:

| Ý tưởng | Tác động giả định | Nỗ lực thử | Độ bất định | Quyết định minh họa |
|---|---|---|---|---|
| Làm rõ người nhận phản hồi PR | Khá lớn đối với nút thắt hiện tại | Nhỏ | Trung bình | Thử 2 tuần với PR đủ điều kiện. |
| Viết lại toàn bộ hệ thống CI | Có thể lớn | Rất lớn | Cao | Tách spike đo các bước chậm trước. |
| Bổ sung kiểm thử cho lỗi ghi đăng ký lặp | Quan trọng đối với dữ liệu | Vừa | Thấp về nhu cầu, chưa rõ giải pháp | Ưu tiên theo rủi ro, không chờ một Retro mới. |
| Thêm buổi họp tiến độ mỗi ngày | Chưa rõ lợi ích | Nhỏ về công tổ chức nhưng tốn thời gian liên tục | Cao | Không tự triển khai; xác định vấn đề và thử cách nhẹ hơn. |
| Chuẩn hóa câu hỏi nghiệp vụ còn mở | Giảm thời gian chờ quyết định | Nhỏ | Trung bình | Thử kênh và người nhận rõ. |

Đây là ví dụ suy luận, không phải điểm số ưu tiên chính thức. Nếu không chắc giải pháp nào hiệu quả, hãy **đầu tư một thử nghiệm nhỏ** thay vì lập kế hoạch triển khai thay đổi lớn ngay.

### 4.2. Chọn ít hành động, không chọn ít vấn đề quan trọng

Đội vẫn cần ghi nhận rủi ro chưa được xử lý, đặc biệt nghĩa vụ bảo mật và chất lượng. “Chọn ít” ở đây nói về **số thí nghiệm cải tiến chủ động đang chạy cùng lúc**, không phải bỏ qua sự cố cần xử lý hay yêu cầu bắt buộc.

## 5. Từ lời hứa chung đến một hành động đủ cụ thể

So sánh:

| Phát biểu quá chung | Vì sao khó thực hiện? | Phiên bản có thể thử |
|---|---|---|
| “Cải thiện giao tiếp.” | Không rõ giao tiếp về việc gì, ai và khi nào. | Thử khung giải đáp câu hỏi đang chặn PBI trong giờ làm và ghi quyết định cạnh PBI, xem lại sau 2 tuần. |
| “Giảm bug.” | Không rõ loại lỗi, nguyên nhân hoặc điều kiện đo. | Bổ sung kiểm thử tích hợp cho 3 tình huống gửi lặp gây lỗi đăng ký đã từng xảy ra, theo dõi tái diễn trong các bản phát hành tiếp. |
| “Tăng tốc review.” | “Nhanh hơn” mơ hồ; dễ hy sinh chất lượng. | Thử quy định ai nhận review trong ca, ghi thời gian chờ, theo dõi tỷ lệ phản hồi trong giới hạn đã thống nhất và guardrail lỗi hậu review. |
| “Làm CI tốt hơn.” | Không chỉ rõ pipeline nào và nút thắt ở đâu. | Đo thời gian từng bước của pipeline chính, tối ưu bước chậm có bằng chứng và đánh giá p50/p95 cùng độ tin cậy kiểm thử. |
| “Mọi người chủ động hơn.” | Biến vấn đề hệ thống thành lời nhắc đạo đức. | Minh bạch blocker, quyền xử lý và quy trình yêu cầu hỗ trợ; thử check-in ngắn cho các việc đang chờ lâu. |

### 5.1. Dùng cấu trúc hành động một câu

Một cấu trúc thực dụng:

> **Người chịu trách nhiệm** sẽ **thực hiện thay đổi cụ thể** trong **phạm vi nào**, hoàn thành **đầu ra xác định** trước **ngày nào**; đến **mốc kiểm tra nào**, nhóm sẽ so **chỉ số kết quả với baseline/mục tiêu** và xem các **guardrails** để quyết định tiếp tục, sửa hay dừng.

Ví dụ:

> Huy điều phối việc thử cơ chế phản hồi PR theo người nhận trong hai tuần với repository ứng dụng học trực tuyến; công bố thỏa thuận và bắt đầu thu thời điểm trước ngày 27/11; ngày 11/12 nhóm xem trung vị thời gian chờ review, tỷ lệ PR phải làm lại và cảm nhận tải của người review để quyết định có duy trì không.

Các tên và ngày trong bài là **ví dụ giả định**, không phải giao việc cho nhân sự thật.

### 5.2. SMART là công cụ giúp kiểm tra, không phải biểu mẫu hành chính

Có thể dùng tinh thần **SMART**: Specific, Measurable, Achievable, Relevant, Time-bound. Tuy nhiên, đừng biến mỗi phát hiện thành một mục tiêu số chắc chắn khi vấn đề còn bất định.

Ví dụ, lúc chưa biết tốc độ CI hiện tại, việc đặt “giảm 50% trong 5 ngày” có thể tùy tiện. Hành động SMART phù hợp hơn là **đo baseline đáng tin trong tuần đầu**, thử tối ưu một bước, rồi đặt mục tiêu có căn cứ cho vòng sau.

## 6. Ai là owner? Phân biệt trách nhiệm điều phối và công việc thực hiện

Một hành động cải tiến có thể có nhiều người cùng làm, nhưng nên có **một đầu mối chịu trách nhiệm đưa hành động tiến tới quyết định cuối**.

**Action owner** không nhất thiết là người trực tiếp viết toàn bộ mã, tạo dashboard hoặc tổ chức mọi cuộc họp. Owner là người:

- Giữ rõ mục tiêu và phạm vi hành động.
- Phối hợp người tham gia và các phụ thuộc.
- Chủ động theo dõi tiến độ, trở ngại và thời hạn.
- Bảo đảm có bằng chứng cho đầu ra và kết quả.
- Đưa trạng thái, rủi ro hoặc quyết định cần thiết ra đúng nơi.
- Đề nghị điều chỉnh khi điều kiện thực tế thay đổi.

**Owner không phải đối tượng để quy trách nhiệm cá nhân về mọi biến động của kết quả**. Một outcome có thể chịu tác động bởi nhiều yếu tố không thuộc quyền kiểm soát của người điều phối.

### 6.1. Phân biệt các vai trò hỗ trợ

| Vai trò trong một action card | Trách nhiệm minh họa | Câu hỏi cần rõ |
|---|---|---|
| **Owner — đầu mối chịu trách nhiệm** | Theo dõi từ khi chọn hành động tới lúc đánh giá và quyết định. | Ai sẽ chủ động nhắc nếu hành động bị trôi? |
| **Executor — người thực hiện** | Làm các bước kỹ thuật/nghiệp vụ cụ thể. | Ai sẽ viết kiểm thử, cấu hình pipeline hoặc cập nhật chính sách? |
| **Reviewer / verifier — người xác minh** | Kiểm tra đầu ra, dữ liệu và hiệu quả theo tiêu chí đã thống nhất. | Ai có góc nhìn độc lập đủ để chất vấn kết luận? |
| **Decision maker / sponsor** | Có quyền cấp nguồn lực, duyệt thay đổi ngoài phạm vi hoặc ưu tiên. | Ai quyết định nếu cần hoãn tính năng để làm cải tiến? |
| **Data steward (khi cần)** | Giải thích nguồn và định nghĩa phép đo, bảo đảm truy cập hợp lệ. | Ai xác nhận dữ liệu đang được tính giống nhau? |
| **Stakeholders** | Người chịu ảnh hưởng, được tham vấn hoặc thông tin. | Ai cần biết và ai có thể phát hiện tác dụng phụ? |

Một người có thể kiêm nhiều vai trò trong đội nhỏ. Với hành động rủi ro cao, tách người thực hiện và người xác minh có thể hữu ích; mức độ tách phụ thuộc tiêu chuẩn tổ chức.

### 6.2. Ví dụ phân công rõ

Giả sử cải tiến là **giảm thời gian chờ quyết định nghiệp vụ**:

- **Owner:** một thành viên được nhóm thống nhất điều phối thử nghiệm.
- **Executor:** người quản lý backlog và đại diện nghiệp vụ cùng thiết lập khung giải đáp và cách ghi câu trả lời.
- **Verifier:** một người xem dữ liệu tuổi blocker và mẫu PBI, có thể có góc nhìn kiểm thử/phân tích.
- **Decision maker:** người có thẩm quyền điều chỉnh ưu tiên và thời gian tham gia của đại diện nghiệp vụ.
- **Stakeholders:** Developers, Product Owner và những người đang bị chặn bởi quyết định.

Nếu chưa có ai có quyền cam kết thời gian từ chuyên gia nghiệp vụ, việc gán owner cho một lập trình viên **không tự tạo ra năng lực thực hiện**. Cần giải quyết phụ thuộc và thẩm quyền trước hoặc song song.

### 6.3. Owner phải có điều kiện thực hiện

Trước khi gán:

1. Người đó có **hiểu mục tiêu và đồng ý nhận** không?
2. Có **thời gian/năng lực** phù hợp, hay đang quá tải?
3. Có quyền truy cập, dữ liệu và sự hỗ trợ cần thiết?
4. Có khả năng kéo chuyên gia hoặc người có thẩm quyền khi bị chặn?
5. Ai thay thế nếu vắng mặt?
6. Trạng thái và trở ngại sẽ được công bố ở đâu?

Nếu không, “gán tên” chỉ tạo một hàng chờ vô hình. **Trách nhiệm hiệu quả đòi hỏi cả quyền hạn và năng lực**, không chỉ một ô Owner trong bảng.

## 7. Ai chịu trách nhiệm cải tiến trong Scrum và Kanban?

### 7.1. Scrum: không mặc định mọi cải tiến là việc riêng của Scrum Master

Trong Scrum, Scrum Team chịu trách nhiệm về hiệu quả và chất lượng của công việc chung. **Sprint Retrospective** là cơ hội kiểm tra cách làm, chất lượng và hiệu quả, rồi lên kế hoạch cải thiện.

Những cải tiến có tác động lớn nhất thường được nhóm xử lý sớm; chúng **có thể** trở thành hạng mục trong Sprint Backlog của Sprint tiếp theo, nhưng không nhất thiết mọi ý tưởng retrospective đều phải thành PBI hoặc có một quy trình phê duyệt riêng.

Các accountability cần được tôn trọng:

- **Product Owner:** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog. Nếu cải tiến cần thay đổi ưu tiên sản phẩm, cần phối hợp đúng thẩm quyền.
- **Developers:** tạo Increment dùng được, duy trì và điều chỉnh Sprint Backlog; có thể trực tiếp sở hữu những cải tiến kỹ thuật/quy trình trong phạm vi tự quản.
- **Scrum Master:** hỗ trợ hiệu quả Scrum Team, tháo trở ngại và giúp cải tiến cách áp dụng Scrum; **không tự động phải làm owner của mọi action**.
- **Scrum Team:** cùng xem chất lượng và kết quả của các thử nghiệm cải tiến, không đẩy trách nhiệm cải tiến sang một cá nhân rồi quên.

Nếu một action liên quan nhiều đội hoặc quyền tổ chức, owner có thể là đầu mối điều phối và phải nêu rõ decision maker. Không nên diễn giải quyền tự quản là cho phép bỏ qua chính sách bảo mật hoặc trách nhiệm vận hành bắt buộc.

### 7.2. Kanban: cải tiến flow và thực hành công việc hiện tại

Trong Kanban, nhóm có thể phát hiện vấn đề qua **WIP, throughput, cycle time, work item age, blocked time và chính sách dịch vụ**. Một action có thể được kéo vào luồng công việc rõ ràng, với người phụ trách, trạng thái và mốc đánh giá.

Ví dụ:

> “Trong 3 tuần, áp dụng WIP limit thử nghiệm cho cột Đang phát triển và chính sách hỗ trợ hạng mục bị chặn trên 1 ngày làm việc; xem tuổi hạng mục, cycle time, throughput và guardrail chất lượng.”

WIP limit giúp kiểm soát công việc dở dang nhưng **không tự bảo đảm mọi hạng mục giao nhanh hơn hoặc giá trị tăng**. Nhóm cần đo và điều chỉnh. Với sự cố khẩn cấp thực sự, chính sách ứng phó theo rủi ro vẫn có thể ưu tiên hơn dòng thường.

### 7.3. XP: cải tiến những vòng phản hồi kỹ thuật

Nhóm dùng thực hành XP có thể đặt action về:

- Rút ngắn vòng TDD hoặc thời gian chạy test cục bộ.
- Tăng độ tin cậy CI, giảm flaky tests.
- Lập trình cặp cho vùng rủi ro cao để chia sẻ tri thức.
- Refactoring phần mã thường gây lỗi hồi quy.
- Thu hẹp kích thước thay đổi trước khi tích hợp.

Owner có thể là người điều phối thử nghiệm; người thực hiện gồm nhiều kỹ sư; người xác minh xem dữ liệu pipeline và chất lượng. **Đếm số unit test mới không đủ để kết luận lỗi sản phẩm đã giảm**.

## 8. Đặt thời hạn: phân biệt ngày làm xong, ngày bắt đầu đo và ngày kiểm tra

Một lỗi phổ biến là chỉ ghi “Due: thứ Sáu”. Nhưng cải tiến là một **giả thuyết thay đổi cách làm**, thường cần thời gian thử và quan sát.

Nên phân biệt ít nhất bốn mốc:

| Mốc | Ý nghĩa | Ví dụ giả định |
|---|---|---|
| **Ngày khởi động** | Bắt đầu thỏa thuận, triển khai thử hoặc thu baseline. | 2026-11-24. |
| **Hạn hoàn thành đầu ra** | Cơ chế mới được thiết lập và có bằng chứng dùng được. | 2026-11-27: thỏa thuận review và đo dữ liệu đã sẵn sàng. |
| **Cửa sổ thử/quan sát** | Khoảng có đủ công việc thực tế để xem hành vi sau thay đổi. | 2026-11-30 tới 2026-12-10. |
| **Mốc Check và quyết định** | Ngày xem số liệu, guardrails và chọn Act. | 2026-12-11. |

**Các ngày chỉ là ví dụ**, không phải lịch thực tế của một nhóm đang tồn tại.

### 8.1. Deadline phải gắn với phạm vi đầu ra

“Hoàn thành cải tiến trong 2 tuần” không rõ là:

- Đã tạo dashboard?
- Đã áp dụng chính sách?
- Đã thu đủ mẫu sau áp dụng?
- Hay đã chứng minh giảm chậm 30%?

Không nên hứa **kết quả outcome chắc chắn xảy ra đúng ngày**. Người phụ trách có thể cam kết thực hiện thí nghiệm và báo cáo bằng chứng vào ngày xác định, còn kết quả phụ thuộc thực tế. Nếu không đạt target, đó là dữ liệu để học và ra quyết định.

### 8.2. Cửa sổ đánh giá phải phù hợp tần suất công việc

Một đội chỉ tạo 4 PR mỗi tháng khó đánh giá thay đổi review sau 2 ngày. Ngược lại, pipeline chạy hàng trăm lần một tuần có thể cung cấp tín hiệu rất nhanh.

Hãy xét:

- Số hạng mục/sự kiện cần có để nhìn xu hướng.
- Biến động theo tuần, ngày nghỉ, mốc release.
- Độ trễ của tác động: một thay đổi kiểm thử hôm nay có thể cần vài lần phát hành để thấy lỗi hồi quy giảm.
- Cửa sổ để quan sát guardrail và tác dụng phụ.
- Nhu cầu quyết định sớm nếu có rủi ro không chấp nhận được.

**Không có một công thức “mọi cải tiến phải đo trong đúng một Sprint”.**

### 8.3. Một lịch minh họa cho thử nghiệm giảm thời gian chờ review

~~~mermaid
gantt
    title Lịch thử cải tiến review (minh họa)
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Chuẩn bị
    Xác nhận baseline và người nhận :a1, 2026-11-24, 3d
    section Áp dụng
    Thử chính sách review :a2, 2026-11-27, 14d
    section Đánh giá
    Tổng hợp dữ liệu và guardrails :a3, 2026-12-11, 1d
    Quyết định cách làm tiếp :milestone, a4, 2026-12-11, 0d
~~~

Đây là sơ đồ minh họa theo ngày lịch. Nếu đội dùng **giờ làm việc** khi đo thời gian chờ, phải tính nhất quán lịch làm việc; không suy diễn 14 ngày lịch thành 14 ngày làm việc.

### 8.4. Deadline có thể điều chỉnh, nhưng không biến mất

Nếu chủ sở hữu cần lùi hạn vì một sự cố production hoặc chuyên gia vắng mặt, nên cập nhật công khai:

1. Lý do và tác động tới thử nghiệm.
2. Mốc mới cùng người xác nhận.
3. Điều đã hoàn thành và điều đang bị chặn.
4. Khi nào sẽ đánh giá lại và ai quyết định.

Mục tiêu là minh bạch và bảo vệ ưu tiên, không dùng ngày đến hạn làm công cụ trừng phạt.

## 9. Xây action card: một nơi đủ để biết phải làm và kiểm tra điều gì

Một **improvement action card** ngắn gọn thường hiệu quả hơn tài liệu nhiều trang mà không ai cập nhật.

### 9.1. Mẫu hành động đề xuất

~~~yaml
improvement_id: "CI-REVIEW-01"
problem: "PR chờ phản hồi đầu tiên quá lâu, làm dồn việc cuối chu kỳ"
evidence: "14 PR gần nhất; median wait = 21 giờ làm việc"
hypothesis: "Giao người nhận review theo ca sẽ giảm thời gian chờ"
action: "Thử cơ chế review theo người nhận và ghi thời điểm phản hồi"
scope: "PR ứng dụng học trực tuyến trong phạm vi nhóm thử"
owner: "Người điều phối đã được nhóm thống nhất"
executors:
  - "Các kỹ sư nhận review theo ca"
  - "Người hỗ trợ thu dữ liệu"
decision_maker: "Người có quyền điều chỉnh ưu tiên và lịch tham gia"
start_date: "2026-11-24"
output_due_date: "2026-11-27"
check_date: "2026-12-11"
output_done_when: "Chính sách được công bố, có người nhận, đo thời gian được"
primary_metric: "Median working-hours to first meaningful review response"
baseline: "21 giờ làm việc, mẫu 14 PR"
target: "Thử hướng tới <= 12 giờ làm việc nếu dữ liệu đủ so sánh"
guardrails:
  - "Không tăng lỗi hồi quy nghiêm trọng trong phạm vi quan sát"
  - "Không đẩy quá tải lên người review"
decision_rule: "Đánh giá kết quả, mẫu và guardrails để duy trì/sửa/dừng"
status: "PLANNED"
~~~

Đây là **mẫu mô tả trong bài học**, không phải file cấu hình của dự án và không phải metadata của bài. Các giá trị đều giả định.

### 9.2. Điều tối thiểu không nên thiếu

Nếu một đội không muốn nhiều trường, có thể dùng bảng ngắn:

| Trường bắt buộc cho một thử nghiệm nhỏ | Nội dung |
|---|---|
| Vấn đề & bằng chứng | Một câu về hiện trạng và tín hiệu cụ thể. |
| Hành động & giả thuyết | Thay đổi nào được thử, kỳ vọng vì sao tốt hơn. |
| Owner & người hỗ trợ | Một đầu mối rõ, ai thực hiện và ai quyết định khi có phụ thuộc. |
| Hạn & điểm Check | Khi nào triển khai, khi nào đo và ra quyết định. |
| Tiêu chí đầu ra | Làm sao xác nhận hành động được áp dụng. |
| Chỉ số kết quả & guardrail | Cách biết tốt hơn và điều không được xấu đi. |
| Trạng thái & quyết định | Đang ở đâu, trở ngại, kết luận và bước tiếp. |

### 9.3. Tách một hành động quá lớn

Nếu action card ghi “Xây lại toàn bộ CI, cải thiện chất lượng, giảm cycle time toàn hệ thống trong một tháng”, đó thường là **nhiều giả thuyết và phụ thuộc** chứ không phải một hành động nhỏ.

Nên tách:

1. Đo baseline và tìm 2 bước chậm nhất của pipeline.
2. Thử tối ưu một bước có thể đảo ngược, đánh giá thời gian và độ tin cậy.
3. Chọn bước tiếp theo theo bằng chứng.

Những hạng mục lớn hoặc ảnh hưởng nhiều hệ thống cần kế hoạch, trách nhiệm, kiểm chứng và ưu tiên tương ứng, không bị ép vào một card nhỏ không phản ánh độ phức tạp.

## 10. Thiết kế phép đo: trước khi đo, phải định nghĩa điều sẽ tính

Một yêu cầu “Giảm thời gian chờ 30%” chưa đủ nếu không nói **chờ từ mốc nào tới mốc nào, theo đơn vị nào và trong quần thể nào**.

Phép đo tốt nên làm rõ:

1. **Đối tượng:** PR, PBI, sự cố hay người dùng nào?
2. **Mốc bắt đầu:** khi yêu cầu review, khi PR đủ điều kiện hay khi có người nhận?
3. **Mốc kết thúc:** phản hồi đầu tiên có ý nghĩa, approval hay merge?
4. **Đơn vị:** phút, giờ làm việc, ngày lịch, tỷ lệ phần trăm hoặc số trường hợp.
5. **Cửa sổ:** các hạng mục hoàn thành trong giai đoạn nào?
6. **Phân khúc:** thay đổi nhỏ/lớn, lỗi/feature, người mới/quen vùng mã.
7. **Nguồn dữ liệu:** công cụ quản lý mã, bảng flow, log CI hay sự kiện sản phẩm?
8. **Chất lượng dữ liệu:** trường hợp thiếu mốc, ghi lặp, thay đổi định nghĩa.
9. **Baseline và target:** đo ban đầu từ mẫu nào, kỳ vọng thay đổi bao nhiêu?
10. **Quyết định:** nếu số này tăng hoặc giảm thì đội sẽ làm gì?

### 10.1. Định nghĩa cụ thể thời gian chờ PR

Ví dụ:

> **Time to first meaningful review response** là khoảng **giờ làm việc** từ lúc tác giả đánh dấu PR đủ điều kiện và yêu cầu review, đến lúc nhận một phản hồi chuyên môn có thể hành động hoặc quyết định review đầu tiên. Không tính bot tự động, thông báo emoji hay comment không có nội dung xem xét.

Định nghĩa này cần quy tắc về:

- PR đang ở trạng thái draft và chưa sẵn sàng.
- PR thiếu mô tả, thiếu kiểm thử hoặc không thể chạy được.
- Người phụ trách ở múi giờ khác.
- Nghỉ lễ hoặc ngoài giờ làm việc.
- PR bị yêu cầu sửa rồi gửi lại.
- PR bị đóng mà không merge.

Nên chọn cách tính theo **mục tiêu thực**, rồi giữ định nghĩa nhất quán để so sánh. Không tùy ý loại bỏ những trường hợp chậm nhất chỉ để số liệu đẹp.

### 10.2. Median và p85/p95 giúp nhìn phân phối

Một vài PR rất chậm có thể kéo **trung bình** lên cao. Vì vậy, bên cạnh mean, nhóm có thể xem:

- **Median/p50:** khoảng một nửa PR có thời gian chờ không vượt mức này.
- **p85/p95:** mức thời gian chờ mà phần lớn PR trong quần thể đo không vượt quá; hữu ích để nhìn phần đuôi.
- **Tỷ lệ vượt ngưỡng:** số PR chờ trên giới hạn mong muốn / tổng PR đủ điều kiện.
- **Biểu đồ từng điểm theo thời gian:** thấy dao động, sự kiện đặc biệt và độ không chắc.

Với mẫu rất nhỏ, p95 có thể không ổn định. Đừng tuyên bố “tăng 20% là cải tiến chắc chắn” chỉ vì hai trung vị lệch nhau khi mỗi giai đoạn có 3 PR.

## 11. Baseline, target, actual và mức thay đổi

**Baseline** là trạng thái ban đầu theo định nghĩa đo nhất quán. **Target** là mức kỳ vọng có căn cứ. **Actual** là kết quả quan sát được. **Guardrail** là ràng buộc không được xấu đi quá mức chấp nhận.

Giả sử nhóm đo thời gian chờ review trong hai giai đoạn:

| Chỉ số giả định | Trước thử | Sau thử |
|---|---:|---:|
| Số PR đủ điều kiện | 14 | 17 |
| Trung vị thời gian chờ phản hồi đầu tiên (giờ làm việc) | 21 | 12 |
| p85 thời gian chờ (giờ làm việc) | 37 | 23 |
| PR vượt 24 giờ làm việc | 6 | 3 |

Từ đó:

~~~text
Mức giảm trung vị tuyệt đối = 21 - 12 = 9 giờ làm việc

Mức giảm tương đối theo baseline =
    (21 - 12) / 21 × 100% ≈ 42,9%

Tỷ lệ PR vượt ngưỡng trước = 6 / 14 ≈ 42,9%
Tỷ lệ PR vượt ngưỡng sau  = 3 / 17 ≈ 17,6%

Thay đổi tỷ lệ vượt ngưỡng ≈ 17,6% - 42,9%
                           = -25,3 điểm phần trăm
~~~

**Tất cả con số đều giả định**, không chứng minh phương pháp review mới gây ra thay đổi. Số lượng PR, kích thước, thành phần đội hoặc độ khó có thể khác; mẫu cũng còn nhỏ. Kết luận phù hợp là: **“Có tín hiệu tích cực cần xem thêm cùng bằng chứng định tính và chất lượng.”**

### 11.1. Đừng nhầm phần trăm và điểm phần trăm

Tỷ lệ vượt ngưỡng từ 42,9% xuống 17,6% là giảm khoảng **25,3 điểm phần trăm**, không phải giảm 25,3% tương đối.

Nếu cần mức giảm tương đối của tỷ lệ này thì tính:

~~~text
(42,9% - 17,6%) / 42,9% × 100% ≈ 59,0%
~~~

Nêu rõ loại so sánh và mẫu số, đặc biệt khi báo cáo cho người quyết định.

### 11.2. Target không tự động là tiêu chí “được phép bỏ qua chất lượng”

Giả sử target thời gian review là 12 giờ nhưng một PR liên quan phân quyền cần chuyên gia kiểm tra sâu. Không nên yêu cầu review “cho nhanh” để đạt số đẹp. Có thể phân nhóm PR theo rủi ro, xác định đường hỗ trợ chuyên gia và bảo toàn điều kiện chất lượng bắt buộc.

**Mục tiêu hiệu quả là giảm chờ đợi vô ích, không phải giảm tư duy chuyên môn thiết yếu.**

## 12. Chọn chỉ số phù hợp với loại cải tiến

| Loại cải tiến | Outcome cần xem | Chỉ số hỗ trợ | Guardrails |
|---|---|---|---|
| **Giảm chờ quyết định nghiệp vụ** | PBI bị chặn ít hơn; thời gian chờ giảm. | Tuổi blocker, thời gian nhận câu trả lời có thể hành động. | Quy tắc nghiệp vụ không bị hiểu sai, chuyên gia không quá tải. |
| **Giảm WIP** | Flow ổn định hơn, hạng mục hoàn thành sớm hơn. | WIP, cycle time, work item age, throughput. | Lỗi hồi quy, làm việc quá sức, việc khẩn bị trì hoãn. |
| **Cải thiện CI** | Phát hiện lỗi sớm hơn và khôi phục pipeline nhanh hơn. | Thời gian phản hồi CI, tỷ lệ flaky tests, thời gian nhánh chung đỏ. | Phạm vi kiểm tra, chất lượng và bảo mật không suy giảm. |
| **Bổ sung TDD/kiểm thử hồi quy** | Lỗi cùng loại ít tái diễn hơn, sửa đổi tự tin hơn. | Loại lỗi được phát hiện trước release, lỗi lọt ra production. | Độ tin cậy kiểm thử, thời gian chờ phát triển không tăng vô lý. |
| **Cải thiện review** | Thời gian chờ review giảm, chất lượng vẫn tốt. | Median/p85 chờ phản hồi, PR phải làm lại. | Không duyệt qua loa, không dồn tải lên một người. |
| **Làm rõ user story sớm** | Ít làm lại vì hiểu sai, quyết định nhanh hơn. | Rework, blocker, số câu hỏi chưa rõ theo thời gian. | Không tạo quá nhiều họp hoặc “đóng câu hỏi” bằng giả định sai. |
| **Cải thiện ứng phó sự cố** | Giảm tác động và khả năng tái diễn lỗi. | Thời gian phát hiện, giảm thiệt hại, khôi phục và hành động hậu kiểm. | An toàn dữ liệu, tải trực, báo cáo sự cố trung thực. |
| **Cải thiện accessibility** | Người dùng có nhu cầu tiếp cận hoàn thành tác vụ tốt hơn. | Lỗi cản trở hành trình, thử nghiệm bàn phím và công nghệ hỗ trợ. | Không đánh đổi độ đúng hoặc gây rào cản ở nhóm khác. |

### 12.1. Phân biệt đo hành động, đo dòng và đo giá trị

Một action có thể cần ba lớp bằng chứng:

1. **Activity/Output:** chính sách đã công bố; test được thêm; dashboard được tạo.
2. **Process outcome:** thời gian chờ, độ tin cậy CI hoặc lỗi lặp lại được cải thiện.
3. **Product outcome:** người dùng nhận giá trị sớm hơn, ít lỗi hơn hoặc tiếp cận sản phẩm dễ hơn.

Không phải mọi action ngắn đều đo được product outcome trực tiếp. Tuy nhiên, nên ghi **giả thuyết liên hệ** để đội không tối ưu quy trình mà quên mục tiêu sản phẩm.

### 12.2. Không dùng chỉ số một chiều

Nếu mục tiêu là tăng throughput, team có thể chia ticket nhỏ hơn hoặc giảm DoD để tăng số lượng Done. Nếu mục tiêu là giảm lỗi, team có thể ngại báo lỗi.

Vì vậy, khi đặt target cần hỏi:

> Nếu chỉ số chính đẹp lên, có cách nào để chất lượng, người dùng hoặc sức khỏe đội tệ hơn không?

Đó là nơi **guardrail** trở nên cần thiết.

## 13. Guardrails: tránh cải tiến một phần nhưng làm hỏng phần khác

**Guardrail** là chỉ số hoặc điều kiện giúp phát hiện tác dụng phụ của việc tối ưu.

Ví dụ, thử tăng tốc review:

- **Primary metric:** thời gian chờ phản hồi đầu tiên.
- **Quality guardrail:** không tăng lỗi nghiêm trọng được phát hiện sau merge.
- **Human guardrail:** không dồn quá nhiều lượt review cho một người, không phải review ngoài giờ liên tục.
- **Flow guardrail:** các công việc khác không bị chặn vì người được giao review phải bỏ hết việc của mình.

### 13.1. Guardrail có thể định lượng hoặc định tính

Không phải yếu tố nào cũng có một con số tin cậy ngay lập tức. Đội có thể dùng:

- Số lỗi hồi quy hoặc sự cố trong phạm vi đo.
- Phân phối lượt review theo người, thời gian bị ngắt quãng.
- Phản hồi định tính tự nguyện về mức tập trung và tải.
- Các ví dụ review quan trọng bị bỏ sót.
- Quy định không được vi phạm: phân quyền, bảo vệ dữ liệu, Definition of Done.

**Không có sự cố được báo trong hai tuần** chưa chứng minh rủi ro bằng không, nhất là khi tần suất thay đổi thấp. Guardrail phải được đọc cùng quy mô mẫu và mức độ quan sát.

### 13.2. Ngưỡng an toàn khác mục tiêu tối ưu

Đặt mục tiêu trung vị 12 giờ là **điều muốn cải thiện**. Yêu cầu không bỏ kiểm tra bảo mật bắt buộc là **giới hạn không được vi phạm**. Nếu hai điều xung đột, đừng hạ kiểm soát thiết yếu để đạt target.

## 14. Phân biệt bằng chứng triển khai với bằng chứng hiệu quả

Một nhóm có thể đánh dấu mọi ô trong checklist triển khai nhưng vẫn chưa biết cải tiến có tác dụng hay không.

| Câu hỏi | Bằng chứng hợp lệ | Điều chưa thể kết luận |
|---|---|---|
| **Đã triển khai hành động?** | Quy định review mới được áp dụng ở các PR đủ điều kiện, có dữ liệu ghi. | Thời gian chờ đã giảm bền vững. |
| **Mọi người có dùng đúng?** | Mẫu PR và trao đổi cho thấy thỏa thuận được thực hiện. | Thỏa thuận có tối ưu về chi phí và chất lượng. |
| **Outcome có tốt hơn?** | Median và phân phối chờ giảm trong phạm vi đo, đủ mẫu so sánh. | Chắc chắn chỉ action gây ra thay đổi. |
| **Có tác dụng phụ không?** | Số lỗi, tải review, phản hồi định tính được xem. | Những rủi ro hiếm hoàn toàn không thể xảy ra. |
| **Có nên duy trì?** | Lợi ích và guardrails đáng tin, chi phí duy trì chấp nhận. | Mọi đội khác đều nên sao chép nguyên mô hình. |

### 14.1. Đừng tự cho rằng hoàn thành task nghĩa là đã cải tiến

Trong Retrospective, “Đã viết tài liệu quy trình” là một **output**. Nếu tài liệu không được biết đến hoặc không thay đổi cách làm, đội chưa có outcome.

Ngược lại, nếu thí nghiệm đơn giản giúp mọi người hiểu vấn đề rõ hơn nhưng cách làm cũ vẫn tốt, đội có thể quyết định không duy trì thay đổi. **Đó là quyết định có cơ sở**, không cần tạo thêm quy định để chứng minh đã làm việc.

## 15. Theo dõi trạng thái để cải tiến không bị lãng quên

Một vòng theo dõi tối giản có thể dùng các trạng thái:

~~~mermaid
flowchart LR
    A["Đề xuất"] --> B["Đã chọn và có owner"]
    B --> C["Đang chuẩn bị"]
    C --> D["Đang thử"]
    D --> E["Chờ đủ dữ liệu / Check"]
    E --> F["Duy trì"]
    E --> G["Điều chỉnh và thử lại"]
    E --> H["Dừng và lưu bài học"]
    G --> C
~~~

Không nhất thiết phải tạo bảng riêng. Nếu đội đang dùng Product Backlog, Sprint Backlog hoặc một bảng Kanban, có thể gắn action vào cách theo dõi sẵn có, miễn không làm mờ loại công việc và quyền sở hữu.

### 15.1. Đề xuất một bảng nhìn nhanh

| Action | Owner | Hạn đầu ra | Mốc Check | Trạng thái | Trở ngại | Bằng chứng tiếp theo |
|---|---|---|---|---|---|---|
| Giảm chờ review | Người điều phối A | 27/11 | 11/12 | Đang thử | Thiếu dữ liệu PR đầu tuần | Thời gian chờ và số PR |
| Làm rõ story trước coding | Người điều phối B | 30/11 | 15/12 | Chuẩn bị | Chuyên gia nghiệp vụ chưa xác nhận khung trao đổi | Tuổi câu hỏi chưa giải đáp |
| Ổn định bộ test lỗi đăng ký lặp | Kỹ sư C | 03/12 | 20/12 | Đang phát triển | Môi trường thử concurrency | Kết quả test và tái diễn lỗi |

Những tên và ngày trong bảng chỉ minh họa cách quản lý trạng thái.

### 15.2. “Đang bị chặn” cần người và bước gỡ cụ thể

Một action ở trạng thái BLOCKED quá lâu mà không có bước tiếp giống hệt vấn đề workflow ban đầu. Khi bị chặn, cần ghi:

- Phụ thuộc vào ai/điều gì?
- Owner đã yêu cầu hỗ trợ chưa?
- Ai có thẩm quyền quyết định đổi phạm vi hoặc ưu tiên?
- Khi nào xem lại trạng thái?
- Có thể thực hiện một phần khác để học sớm hơn không?

Không nên che tình trạng thiếu nguồn lực bằng việc lùi deadline nhiều lần mà không thảo luận.

## 16. Nhịp cập nhật: ít nghi thức, đủ thông tin

Để action không chìm trong công việc hàng ngày, nhóm nên có **cadence** theo dõi phù hợp:

| Thời điểm | Câu hỏi cần xem | Kết quả mong muốn |
|---|---|---|
| **Ngay sau khi chọn cải tiến** | Vấn đề, owner, năng lực, hạn, baseline, phép đo rõ chưa? | Action đủ điều kiện bắt đầu. |
| **Trong lúc thực hiện** | Có blocker mới? Phạm vi hoặc rủi ro thay đổi? | Owner gỡ trở ngại hoặc thông báo quyết định cần thiết. |
| **Khi đầu ra hoàn thành** | Chính sách/công cụ/thử nghiệm đã vận hành trong phạm vi định nghĩa chưa? | Xác nhận output Done, chuyển sang quan sát. |
| **Mốc Check** | Dữ liệu có đủ tin, outcome/guardrail thế nào? | Quyết định tiếp tục, sửa, dừng hoặc đo thêm. |
| **Sau khi duy trì** | Cải tiến có giữ lợi ích, tạo gánh nặng mới không? | Điều chỉnh hoặc chuẩn hóa có trách nhiệm. |

### 16.1. Với Scrum, dùng nhịp sẵn có

Nhóm có thể cập nhật blocker cải tiến khi nó ảnh hưởng Sprint Goal và kế hoạch trong Daily Scrum, xem chất lượng và outcome trong Sprint Review nếu liên quan sản phẩm, và kiểm tra hiệu quả thử nghiệm trong Retrospective.

Không biến Daily Scrum thành cuộc họp báo cáo tiến độ cho owner hoặc bắt buộc Retrospective phải có đủ số hành động. **Mục tiêu của nhịp gặp là kiểm tra–thích ứng**, không phải tạo ra nhiều cuộc họp.

### 16.2. Với Kanban, theo dõi flow và tín hiệu đến hạn

Đội có thể xem action theo một buổi replenishment/delivery planning hoặc flow review đã có. Nếu action quá tuổi hoặc blocked, áp dụng chính sách minh bạch về xử lý phụ thuộc. Không cần chờ cuối tuần nếu tín hiệu đòi hỏi hành động ngay.

## 17. Trường hợp thực hành 1: giảm thời gian chờ quyết định nghiệp vụ

**Tình huống giả định:** Một đội phát triển nền tảng học trực tuyến xử lý nhiều user story liên quan quản lý lịch lớp. Developers phải chờ Product Owner hoặc người vận hành lớp giải thích chính sách hủy và hoàn chỗ. Một số PBI nằm ở trạng thái “Blocked” nhiều ngày.

### 17.1. Hiện trạng và giả thuyết

Sau khi xem các PBI gần đây, nhóm ghi:

| Tín hiệu ban đầu, số liệu giả định | Giá trị |
|---|---:|
| Số PBI có câu hỏi nghiệp vụ cần trả lời | 12 |
| Số PBI chờ câu trả lời hơn 2 ngày làm việc | 7 |
| Trung vị thời gian từ lúc đặt câu hỏi đến quyết định có thể hành động | 2,5 ngày làm việc |
| Số PBI phải làm lại vì quy tắc bị hiểu sai | 4 |

Giả thuyết: **Không có cơ chế định tuyến câu hỏi rõ ràng và quyết định thường nằm trong trao đổi riêng**. Nếu nhóm có đầu mối, khung thời gian trao đổi và ghi quyết định cạnh PBI, thời gian chờ và số lần làm lại có thể giảm.

### 17.2. Action card rút gọn

| Trường | Thỏa thuận minh họa |
|---|---|
| **Owner** | Một thành viên trong Scrum Team được thống nhất điều phối. |
| **Người thực hiện** | Người phụ trách backlog và đại diện vận hành lớp tạo khung hỏi đáp, ghi ví dụ và quyết định vào PBI. |
| **Phạm vi** | Các câu hỏi về đăng ký/hủy/đổi lịch của một nhóm sản phẩm. |
| **Đầu ra** | Có đầu mối phản hồi, bảng câu hỏi còn mở, quyết định gắn với PBI. |
| **Hạn đầu ra** | Trước khi bắt đầu hai tuần thử nghiệm. |
| **Mốc Check** | Sau khi đã có đủ các PBI liên quan được quan sát trong ít nhất hai tuần. |
| **Primary metric** | Trung vị ngày làm việc chờ quyết định có thể hành động. |
| **Supporting metrics** | Tỷ lệ PBI chờ trên 2 ngày; số lần làm lại do hiểu sai. |
| **Guardrails** | Quyết định đúng nghiệp vụ, người vận hành không bị ngắt quãng quá mức. |
| **Quyết định** | Duy trì, điều chỉnh khung trao đổi hoặc tìm nguyên nhân chờ khác. |

### 17.3. Kết quả giả định và cách diễn giải

Sau thử:

- Trung vị chờ câu trả lời từ **2,5 xuống 1,2 ngày làm việc**.
- Tỷ lệ PBI vượt 2 ngày giảm trong mẫu quan sát.
- Hai lần làm lại vẫn xảy ra vì thuật ngữ nghiệp vụ chưa được thống nhất.
- Người vận hành báo việc trả lời câu hỏi rải rác trong ngày gây gián đoạn.

Đội có thể kết luận **tín hiệu chờ đợi tốt lên**, nhưng cần sửa cách gom câu hỏi và định nghĩa thuật ngữ để không làm tăng tải chuyên gia. Một cải tiến khả thi là gom câu hỏi thường vào khung trao đổi cố định, giữ kênh riêng cho rủi ro đang chặn quan trọng.

**Kết luận không nên là “càng gửi nhiều tin nhắn càng tốt”**. Mục tiêu là quyết định đến đúng người, đúng lúc, đủ tin cậy.

## 18. Trường hợp thực hành 2: giảm lỗi hồi quy bằng kiểm thử có trọng tâm

**Tình huống giả định:** Nhóm nhiều lần gặp lỗi gửi xác nhận khi học viên đăng ký lặp sau timeout. Mỗi lần sửa, người phát triển kiểm tra thủ công ở luồng thuận lợi, nhưng thiếu bài kiểm tra tự động cho trạng thái không chắc.

### 18.1. Xác định action và owner

Thay vì “Tăng test coverage 20%”, chọn:

> Kỹ sư phụ trách điều phối cải tiến phối hợp cùng Developers và người có góc nhìn kiểm thử để viết các kiểm tra tích hợp cho ba kịch bản retry, timeout và xử lý kết quả chưa rõ; tích hợp chúng vào CI trong phạm vi module đăng ký, sau đó theo dõi lỗi cùng loại qua các bản phát hành tiếp theo.

Một tiêu chí đầu ra cụ thể:

- Các bài kiểm tra chạy ổn định và phát hiện được lỗi được tái tạo trong môi trường thử an toàn.
- CI hiển thị kết quả rõ, không có flaky test bị bỏ qua mà không xử lý.
- Người có chuyên môn xác nhận kịch bản phản ánh quy tắc nghiệp vụ.

### 18.2. Đo hiệu quả thế nào?

| Tầng bằng chứng | Phép đo minh họa |
|---|---|
| **Hoạt động/đầu ra** | Ba kịch bản kiểm tra được bổ sung và được CI thực thi. |
| **Process outcome gần** | Lỗi tái hiện được phát hiện trước release; thời gian điều tra ngắn hơn. |
| **Product outcome** | Lỗi xác nhận sai/trùng phát hiện sau release giảm trong phạm vi theo dõi. |
| **Guardrail** | CI vẫn đủ nhanh và đáng tin; không bỏ các kiểm soát hiện có; dữ liệu không bị ảnh hưởng. |

Với lỗi hiếm, **không thấy tái diễn trong hai tuần** chưa đủ chứng minh nguy cơ đã hết. Có thể cần kiểm chứng bằng kịch bản mô phỏng có kiểm soát, quan sát nhiều bản phát hành và xem mức tải thực.

### 18.3. Học hỏi sau Check

Nếu test phát hiện lỗi tốt nhưng mất 40 phút và thường thất bại ngẫu nhiên, nhóm cần điều chỉnh cơ chế chạy, dữ liệu thử hoặc môi trường. Nếu lỗi vẫn xuất hiện trong production, cần xem **khoảng trống giữa môi trường kiểm chứng và hành vi thật**, không đơn giản giao thêm nhiệm vụ “viết nhiều test hơn”.

## 19. Trường hợp thực hành 3: giới hạn WIP để cải thiện dòng giá trị

**Tình huống giả định:** Một nhóm Kanban có 11 hạng mục ở “Đang phát triển”, trong khi khả năng kiểm thử và tích hợp chỉ đủ xử lý một vài hạng mục cùng lúc. Công việc cũ liên tục bị bỏ dở khi có yêu cầu mới.

### 19.1. Một thử nghiệm có phạm vi rõ

- **Giả thuyết:** Nếu giới hạn WIP và ưu tiên hoàn thành việc đang dở trước khi kéo việc mới, cycle time và work item age có thể giảm.
- **Owner:** một thành viên được nhóm đồng ý điều phối thử nghiệm, không tự động là quản lý dự án.
- **Người thực hiện:** cả nhóm tuân thủ chính sách kéo việc và xử lý blocker.
- **Phạm vi:** loại work item Standard của một luồng, có chính sách rõ cho sự cố khẩn.
- **Thời hạn:** bắt đầu trong tuần thử, đánh giá sau số lượng hạng mục đủ so sánh.
- **Bằng chứng đầu ra:** WIP limit hiển thị, chính sách vượt giới hạn và cơ chế gỡ blocker được thống nhất.

### 19.2. Chỉ số trước–sau giả định

| Chỉ số | Trước | Sau |
|---|---:|---:|
| WIP trung bình trong phạm vi đo | 11 | 6 |
| Cycle time trung vị hạng mục Standard (ngày làm việc) | 12 | 8 |
| Hạng mục quá tuổi theo SLE đã thống nhất | 5/18 | 3/20 |
| Throughput mỗi khoảng 2 tuần | 9 | 10 |

Đội có thể quan sát **WIP và cycle time giảm**, throughput gần ổn định hoặc nhích lên trong số liệu minh họa. Nhưng không nên kết luận đây là quan hệ nhân quả chắc chắn: kích thước hạng mục, số sự cố chen ngang, ngày nghỉ và chất lượng có thể đã khác.

### 19.3. Guardrails và điều chỉnh

- Lỗi sau bàn giao không tăng vì “đẩy việc qua Done”.
- Người tham gia không phải làm quá giờ để tuân thủ ngưỡng WIP.
- Sự cố khẩn được xử lý đúng chính sách.
- Việc có giá trị cao không bị chặn chỉ vì định nghĩa trạng thái thiếu linh hoạt.

Nếu team giảm WIP bằng cách **đổi tên trạng thái** thay vì giảm công việc dở thật, metric đẹp lên nhưng flow không cải thiện. Nên thống nhất chính sách đo và xem các hạng mục cụ thể.

## 20. Khi bằng chứng trái với kỳ vọng: quyết định sau Check

Không phải mọi thử nghiệm cần kết thúc bằng việc chuẩn hóa. Có ít nhất bốn lựa chọn:

| Kết quả Check | Hành động Act có thể phù hợp | Điều cần tránh |
|---|---|---|
| **Outcome tốt hơn, guardrails ổn, dữ liệu đủ tin** | Duy trì cách làm, ghi thỏa thuận, cân nhắc mở rộng. | Khẳng định sẽ hiệu quả với mọi đội và mọi loại việc. |
| **Có tín hiệu tốt nhưng dữ liệu còn ít** | Tiếp tục thử trong cửa sổ phù hợp, mở rộng phạm vi có kiểm soát. | Tuyên bố thành công chỉ sau một vài trường hợp thuận lợi. |
| **Outcome không đổi, giả thuyết có dấu hiệu sai** | Phân tích, sửa cách thử hoặc chọn giả thuyết khác. | Đổ lỗi người thực hiện vì kết quả không đến. |
| **Guardrail xấu đi hoặc rủi ro không chấp nhận được** | Dừng/giảm phạm vi thử, khôi phục điều kiện an toàn và điều tra. | Bám target tới cùng dù gây hại. |

### 20.1. Cần có tiêu chí dừng sớm

Không cần đợi tới đúng ngày Check nếu thử nghiệm gây mất dữ liệu, vi phạm phân quyền hoặc tăng sự cố nghiêm trọng. Action card nên ghi **điều kiện dừng hoặc cơ chế báo rủi ro** phù hợp.

### 20.2. Đánh giá cả chi phí duy trì

Một chính sách giúp giảm thời gian chờ 20% nhưng yêu cầu mỗi người dành thêm 8 giờ họp mỗi tuần có thể không đáng duy trì. Cần xem **lợi ích ròng**, tải công việc, khả năng duy trì và hệ quả đối với người dùng.

## 21. Những sai lệch thường gặp khi đánh giá hiệu quả cải tiến

### 21.1. Before–after không tự chứng minh nhân quả

Ví dụ, cycle time giảm sau khi áp dụng WIP limit, nhưng cùng thời điểm đội vừa tuyển thêm kỹ sư giàu kinh nghiệm và giải quyết xong phụ thuộc khó. Không thể quy toàn bộ thay đổi cho WIP limit.

Khi có điều kiện, hãy:

- Giữ định nghĩa công việc và chỉ số nhất quán.
- Xem nhiều điểm đo, không chỉ hai trung bình.
- Ghi những sự kiện bối cảnh quan trọng.
- Phân khúc theo loại việc hoặc độ rủi ro.
- Kết hợp phỏng vấn, quan sát và dữ liệu.
- So sánh với nhóm hoặc giai đoạn phù hợp nếu việc so sánh có cơ sở.

Không phải mọi cải tiến quy trình cần A/B test; mục tiêu là **đưa ra kết luận tương xứng chất lượng bằng chứng**, không biến thử nghiệm Agile thành một dự án nghiên cứu quá mức.

### 21.2. Chọn metric quá dễ bị “chơi”

Nếu đánh giá owner bằng “số action hoàn thành”, họ có động cơ chọn việc rất nhỏ hoặc đóng sớm. Nếu đánh giá team bằng “số lần lỗi được báo”, đội có thể ít báo hơn.

Đừng dùng chỉ số làm hình phạt hay bảng xếp hạng cá nhân. Hãy gắn trách nhiệm với **minh bạch, thực hiện, học hỏi và cải tiến hệ thống**, không kiểm soát bằng một con số tách bối cảnh.

### 21.3. Dữ liệu sản phẩm phải được thu thập có trách nhiệm

Khi đo người dùng, phải bảo vệ dữ liệu cá nhân và chỉ thu thông tin cần thiết theo chính sách. Khi đo hiệu suất kỹ sư, tránh khai thác log cá nhân để suy diễn năng lực hoặc tạo giám sát xâm lấn không liên quan tới mục tiêu cải tiến.

Nếu chỉ số gắn với một người, cần rõ mục đích sử dụng, quyền truy cập và khả năng diễn giải sai.

## 22. Anti-patterns: việc cải tiến có tên nhưng không có tác dụng

| Phản mẫu | Hệ quả | Cách xử lý |
|---|---|---|
| **“Mọi người cùng owner.”** | Không có ai chủ động theo dõi hoặc báo blocker. | Chọn một đầu mối có năng lực và sự đồng thuận; nhiều người vẫn có thể thực hiện. |
| **Giao toàn bộ action cho Scrum Master.** | Nhóm bỏ trách nhiệm tự cải tiến, tạo nút thắt. | Phân công theo nơi có kiến thức, năng lực và thẩm quyền; Scrum Master hỗ trợ hiệu quả chung. |
| **Owner không có quyền hoặc thời gian.** | Deadline trễ lặp, phụ thuộc không được gỡ. | Xác nhận năng lực, người hỗ trợ và decision maker. |
| **Hành động chỉ là khẩu hiệu “giao tiếp tốt hơn”.** | Không biết phải thử điều gì. | Mô tả thay đổi nhỏ, phạm vi và bằng chứng đầu ra. |
| **Chỉ có due date, không có check date.** | Ticket đóng nhưng không ai xem hiệu quả. | Tách hạn triển khai khỏi cửa sổ đo outcome. |
| **Deadline đặt tùy tiện cho kết quả chưa chắc.** | Kỳ vọng sai và áp lực che dữ liệu. | Cam kết thí nghiệm và mốc báo cáo; target là giả thuyết để kiểm tra. |
| **Đánh dấu Done khi đã tạo bảng/dashboard.** | Có output nhưng vấn đề không đổi. | Kiểm tra process outcome và guardrails. |
| **Không thu baseline trước khi sửa.** | Khó đánh giá cải tiến do đâu. | Chọn phép đo trước, thu dữ liệu đủ tin hoặc nêu rõ giới hạn. |
| **Đổi định nghĩa đo giữa hai kỳ.** | Báo cáo tăng/giảm không còn ý nghĩa. | Giữ định nghĩa, ghi version và cách so sánh. |
| **Target một chỉ số duy nhất.** | Tốc độ tăng, chất lượng/sức khỏe giảm. | Bổ sung guardrails và xem tác dụng phụ. |
| **Có 20 action đang làm cùng lúc.** | WIP cao, không cái nào hoàn tất/được đo. | Chọn ít hành động có tác động, hoàn thành rồi mới mở thêm. |
| **Không ghi quyết định sau Check.** | Cách làm mới tồn tại theo quán tính hoặc bị bỏ quên. | Nêu duy trì/sửa/dừng, chủ sở hữu và lần xem lại. |
| **Gán lỗi cho owner nếu giả thuyết không đúng.** | Người phụ trách ngại báo kết quả xấu. | Tôn trọng bằng chứng và đánh giá hành vi học hỏi. |
| **Chỉ đo năng suất cục bộ, quên người dùng.** | Flow trông tốt nhưng không tăng giá trị sản phẩm. | Liên hệ cải tiến với mục tiêu sản phẩm khi phù hợp. |
| **Áp quy trình của đội khác không thử.** | Tăng nghi thức hoặc công việc không giá trị. | Điều chỉnh theo bối cảnh, đánh giá qua dữ liệu của chính đội. |
| **Lấy không có sự cố trong một tuần làm chứng cứ chắc chắn.** | Bỏ qua rủi ro hiếm và mẫu nhỏ. | Xem năng lực kiểm chứng, cửa sổ và bài thử có kiểm soát. |

## 23. Một bài thực hành đầy đủ: từ Retrospective tới action được kiểm chứng

Giả sử team phát triển chức năng **hủy đăng ký buổi học**. Trong ba Sprint gần đây, hạng mục thường bị chặn khi cần xác minh quy tắc trả chỗ cho người trong danh sách chờ.

**Thông tin giả định ban đầu:**

- 15 PBI liên quan đăng ký/hủy đã được làm.
- 8 PBI từng bị chặn vì thiếu quyết định nghiệp vụ.
- Trung vị thời gian chờ quyết định là 2,4 ngày làm việc.
- 3 PBI phải làm lại do hiểu sai quy tắc.
- Người vận hành lớp chỉ có khoảng thời gian hạn chế để trả lời.

### Bài tập 1 — Viết lại vấn đề

Thay vì “Product Owner phản hồi chậm”, hãy viết câu dựa trên hệ thống:

> **Các câu hỏi liên quan chính sách hủy chưa có đường xác nhận và ghi quyết định đủ rõ, làm PBI chờ lâu và phát sinh rework.**

**Vì sao tốt hơn?** Câu này thể hiện quan sát, không quy lỗi chủ quan cho một cá nhân; có thể kiểm tra bằng dữ liệu và tìm phương án phù hợp.

### Bài tập 2 — Chọn một hành động đủ nhỏ

Gợi ý:

> Thử cơ chế tổng hợp câu hỏi liên quan hủy/hoàn chỗ trong một kênh chung, có khung trả lời với đại diện vận hành và ghi quyết định cạnh PBI, áp dụng với PBI đủ điều kiện trong hai tuần.

Không cần thay toàn bộ quy trình Product Backlog của công ty.

### Bài tập 3 — Phân vai

**Gợi ý:**

- Owner là một người có thể phối hợp đúng người và theo dõi hành động.
- Người thực hiện gồm người chuẩn bị câu hỏi, đại diện vận hành và người cập nhật PBI.
- Người xác minh kiểm tra thời điểm hỏi/đáp và chất lượng ví dụ nghiệp vụ.
- Người có quyền quyết định hỗ trợ khi cần cấp thời gian từ chuyên gia.

Nếu không có quyền và năng lực để phối hợp, cần giải quyết blocker thay vì chỉ điền tên cho đủ biểu mẫu.

### Bài tập 4 — Đặt deadline và check date

Ví dụ:

- Trước 27/11: có kênh chung, người nhận và cách ghi quyết định.
- Từ 30/11: áp dụng thỏa thuận cho PBI trong phạm vi thử.
- Ngày 11/12: đánh giá dữ liệu đã thu và quyết định có tiếp tục.

**Câu hỏi phản biện:** nếu chỉ có hai PBI trong giai đoạn thử, có đủ kết luận không? Có thể cần tiếp tục thu dữ liệu; phải ghi rõ hạn chế.

### Bài tập 5 — Thiết kế thước đo

**Primary metric:** trung vị ngày làm việc từ lúc câu hỏi đủ ngữ cảnh được gửi đến lúc có quyết định nghiệp vụ có thể thực hiện.

**Supporting metrics:** số PBI chờ trên 2 ngày, số lần làm lại vì hiểu sai.

**Guardrails:** độ chính xác quy tắc hủy/hoàn chỗ, số lần gián đoạn công việc người vận hành, không để câu hỏi rủi ro cao bị bỏ qua.

**Baseline:** 2,4 ngày làm việc với mẫu có nguồn dữ liệu đã kiểm tra.

**Target:** một mức giảm hợp lý được thảo luận sau khi hiểu biến động dữ liệu; không đặt tùy tiện chỉ để có số.

### Bài tập 6 — Ra quyết định sau Check

Giả sử thời gian chờ giảm còn 1,3 ngày nhưng số lần phải làm lại vẫn không giảm. Nhóm có thể kết luận điều gì?

**Gợi ý:** đường trả lời nhanh hơn nhưng **nội dung câu trả lời hoặc cách ghi quy tắc có thể chưa đủ chính xác/đồng nhất**. Bước tiếp theo có thể là dùng ví dụ Given–When–Then hoặc phiên làm rõ ngắn giữa nghiệp vụ, phát triển và kiểm thử trước khi lập trình. Không tuyên bố cải tiến toàn diện chỉ vì primary metric tốt hơn.

## 24. Mẫu báo cáo kết quả cải tiến ngắn gọn cho stakeholder

Một báo cáo có ích nên nêu cả kết quả **và giới hạn của kết luận**.

~~~text
IMPROVEMENT REVIEW - VÍ DỤ

Vấn đề:
  PR chờ phản hồi chuyên môn lâu, đẩy công việc về cuối Sprint.

Thử nghiệm:
  Chọn người nhận review theo ca, áp dụng 2 tuần.

Owner:
  Người được nhóm giao điều phối; executors và reviewer đã thống nhất.

Mốc:
  Output due: 27/11/2026
  Review/check: 11/12/2026

Output:
  Thỏa thuận được công bố, thử trên các PR đủ điều kiện,
  thời điểm gửi/nhận review được ghi lại.

Outcome:
  Median chờ từ 21 xuống 12 giờ làm việc;
  mẫu 14 PR trước và 17 PR sau.

Guardrails:
  Chưa thấy dấu hiệu rõ lỗi nghiêm trọng tăng trong mẫu nhỏ;
  người review báo một số ngày bị ngắt quãng nhiều.

Giới hạn:
  PR và tải công việc giữa hai giai đoạn có thể khác;
  chưa đủ cơ sở khẳng định quan hệ nhân quả.

Quyết định:
  Duy trì thử với một thay đổi: gom các yêu cầu review
  trong khung làm việc, giữ đường khẩn cho việc rủi ro cao.
  Xem lại sau cửa sổ dữ liệu tiếp theo.
~~~

Mẫu báo cáo nên dễ đọc, đi thẳng vào **điều đã thử, điều quan sát, điều chưa chắc và quyết định tiếp**. Không cần phủ nhận điểm yếu để tạo câu chuyện thành công.

## 25. Cách duy trì cải tiến mà không tăng gánh nặng quy trình

Một thay đổi có hiệu quả trong giai đoạn thử có thể không còn phù hợp khi đội tăng quy mô, đổi kiến trúc hoặc chuyển cách vận hành. Vì vậy, sau quyết định duy trì cần:

1. **Chuyển hóa kết quả thành thỏa thuận hoặc thực hành tối thiểu** (ví dụ người nhận review, cách cập nhật API).
2. **Cập nhật hướng dẫn thiết yếu** gần nơi làm việc thực, thay vì một tài liệu không ai tìm được.
3. **Phân công người duy trì cơ chế**, không nhất thiết trùng với owner của thử nghiệm ban đầu.
4. **Theo dõi tín hiệu ở nhịp hợp lý**, không tạo dashboard không ai sử dụng.
5. **Định kỳ xem lại điều kiện áp dụng**, nhất là khi quy mô, rủi ro, kiến trúc hoặc đội hình thay đổi.
6. **Loại bỏ quy định không còn tạo giá trị**, tránh mỗi Retro chỉ thêm luật mà không bao giờ bỏ luật cũ.

### 25.1. Phân biệt cải tiến một lần và cải tiến năng lực lâu dài

“Thêm một bài kiểm thử hồi quy cho lỗi đã có” có thể là một hành động cụ thể, hoàn thành một lần. “Giữ bộ kiểm thử đáng tin, cập nhật theo rủi ro và không để nhánh chung đỏ kéo dài” là một **năng lực duy trì** cần vai trò, tín hiệu và thói quen vận hành.

Người điều phối thí nghiệm có thể kết thúc trách nhiệm khi đã bàn giao cơ chế duy trì rõ ràng; không nhất thiết chịu trách nhiệm vô hạn với mọi biến động tương lai.

## 26. Checklist trước khi cam kết một hành động cải tiến

### Vấn đề và mục tiêu

- [ ] Đã nêu vấn đề quan sát được, hậu quả và phạm vi ảnh hưởng?
- [ ] Đã tách bằng chứng khỏi giả thuyết về nguyên nhân?
- [ ] Đã mô tả điều gì sẽ thay đổi nếu thử nghiệm hiệu quả?
- [ ] Hành động đủ nhỏ để kiểm chứng, không gộp quá nhiều giả thuyết?
- [ ] Đã xét nghĩa vụ an toàn/bảo mật cần xử lý ngay?

### Người chịu trách nhiệm và nguồn lực

- [ ] Có một **owner được thống nhất** và biết rõ trách nhiệm điều phối?
- [ ] Đã phân biệt người thực hiện, người xác minh và người ra quyết định khi cần?
- [ ] Owner và người thực hiện có năng lực, thời gian, quyền và dữ liệu?
- [ ] Có đường báo blocker và người hỗ trợ nếu phụ thuộc vượt thẩm quyền?
- [ ] Cách phân công có tôn trọng khả năng tự quản, không biến cải tiến thành việc riêng của Scrum Master?

### Thời hạn và phạm vi thử

- [ ] Đã có hạn hoàn thành **đầu ra của hành động**?
- [ ] Đã nêu phạm vi áp dụng, cách thu dữ liệu và điều kiện đủ mẫu?
- [ ] Có mốc **Check riêng** sau cửa sổ quan sát phù hợp?
- [ ] Khi deadline thay đổi có cách cập nhật minh bạch?
- [ ] Có điều kiện dừng hoặc tăng cấp nếu phát hiện rủi ro?

### Đo lường hiệu quả

- [ ] Primary metric phản ánh đúng vấn đề chứ không chỉ số task đã làm?
- [ ] Đã định nghĩa đối tượng, mốc đo, đơn vị, mẫu số, cửa sổ và nguồn dữ liệu?
- [ ] Baseline có đáng tin và cùng định nghĩa so sánh với sau thử?
- [ ] Target có căn cứ và được hiểu là giả thuyết kiểm chứng, không bảo đảm?
- [ ] Có guardrails về chất lượng, giá trị người dùng và tải công việc?
- [ ] Đã xét mức độ biến động, yếu tố ngoài và hạn chế suy luận nhân quả?

### Học hỏi và duy trì

- [ ] Ai xác nhận đầu ra đã hoàn thành và ai sẽ xem outcome?
- [ ] Buổi Check có dẫn tới **duy trì, chỉnh, thử tiếp hay dừng**?
- [ ] Bằng chứng và giới hạn của kết quả được ghi rõ, không thổi phồng?
- [ ] Nếu duy trì, ai sở hữu thực hành sau thử nghiệm và khi nào xem lại?
- [ ] Số action đang chạy có vừa năng lực để thực hiện tới nơi tới chốn?
- [ ] Số liệu được dùng để học hỏi và cải tiến hệ thống, không quy lỗi cá nhân đơn giản?

Checklist là công cụ tự kiểm tra, **không phải bộ thủ tục bắt buộc áp dụng giống nhau cho mọi đội**. Mục tiêu là tăng khả năng biến phản hồi thành cải tiến thực, không tăng gánh nặng hành chính.

## 27. Kết luận

Cải tiến liên tục chỉ trở thành năng lực của một nhóm Agile khi những phát hiện từ Retrospective, Kanban flow, kiểm thử kỹ thuật hay phản hồi sản phẩm được chuyển thành **hành động có người đưa tới kết quả, phạm vi rõ, thời hạn hợp lý và bằng chứng đo lường**.

Một **owner** tốt không phải người bị buộc chịu lỗi nếu giả thuyết sai, mà là người làm rõ trách nhiệm, phối hợp hỗ trợ, minh bạch trở ngại và giúp nhóm đi đến quyết định. Một **deadline** tốt không chỉ đóng ticket mà tách **ngày triển khai** khỏi **ngày đánh giá outcome**. Một **metric** tốt không chỉ đếm số việc hoàn thành mà trả lời vấn đề đã giảm chưa, với baseline, guardrails và giới hạn của dữ liệu.

Trong **AGILE_DEVELOPMENT**, Scrum tạo nhịp kiểm tra–thích ứng, Kanban giúp nhìn rõ nút thắt dòng công việc, XP tạo những vòng phản hồi kỹ thuật nhanh, và backlog giúp ưu tiên đầu tư vào giá trị thực. Khi kết hợp các cơ chế đó với **Plan–Do–Check–Act**, nhóm có thể tiến từ câu nói **“chúng ta cần cải tiến”** tới một cách làm có thể kiểm chứng: **ai thực hiện, khi nào hoàn thành, điều gì thay đổi, và chúng ta sẽ làm gì tiếp theo dựa trên bằng chứng**.
