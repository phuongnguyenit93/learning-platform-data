# Xác định phần nền tảng cần giữ khi điều chỉnh một cách tiếp cận

Một nhóm xây nền tảng học lập trình đã quen làm việc theo Scrum với Sprint hai tuần. Khi sản phẩm đi vào vận hành, sự cố sản xuất xuất hiện bất ngờ, một số yêu cầu cần xử lý ngay, người dùng ở nhiều múi giờ và bộ phận bảo mật yêu cầu lưu bằng chứng kiểm soát. Nhóm bắt đầu đề xuất: “Bỏ mọi sự kiện Scrum, dùng một bảng Kanban, mỗi người tự nhận ticket và cuối tháng báo cáo kết quả. Như vậy vẫn Agile vì chúng ta linh hoạt”.

Đề xuất ấy có thể chứa ý tưởng hữu ích, nhưng chưa trả lời được những câu hỏi then chốt: **Ai chịu trách nhiệm ưu tiên? Làm sao biết công việc thực sự hoàn tất? Nhóm nhận phản hồi người dùng khi nào? Công việc khẩn có thể đẩy lùi mọi cải tiến dài hạn không?** Nếu không trả lời, “tùy biến” chỉ đổi tên quy trình trong khi những cơ chế tạo giá trị và học hỏi bị mất.

Ở chiều ngược lại, một nhóm khác lại khăng khăng giữ nguyên mọi biểu mẫu, cách họp, công cụ và hệ thống story points dù hoạt động thực tế đã đổi. Họ đang giữ **thói quen** thay vì phân biệt đâu là bản chất của cách tiếp cận và đâu là lựa chọn triển khai.

**Điều chỉnh một cách tiếp cận (tailoring/adaptation)** là thiết kế cách làm phù hợp bối cảnh, trong khi chủ động **bảo vệ những nguyên lý, trách nhiệm, cơ chế phản hồi và điều kiện chất lượng làm cho cách tiếp cận đó có ý nghĩa**.

Bài học thuộc chương **Các cách tiếp cận khác** của module **AGILE_DEVELOPMENT**. Mục tiêu của module là phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục, có thể sử dụng user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Vì thế, bài không chọn một phương pháp “tốt nhất cho mọi nơi”, mà cung cấp **cách nhận diện điều cần giữ, điều có thể điều chỉnh và dấu hiệu cần đổi hẳn phương pháp**.

Sau bài học, bạn có thể:

1. Phân biệt **giá trị, nguyên tắc, framework, phương pháp, thực hành, chính sách và công cụ**.
2. Xác định phần **cốt lõi do phương pháp đã chọn quy định**, phần **điều kiện an toàn bắt buộc**, và phần **có thể thử thay đổi**.
3. Nhận diện ranh giới khi áp dụng Scrum, Kanban, XP, Lean hoặc một cách phối hợp nhiều thực hành.
4. Thiết kế cách làm phù hợp loại sản phẩm, độ bất định, công việc khẩn, phụ thuộc, quy mô và ràng buộc tổ chức.
5. Bảo vệ **giá trị người dùng, tính minh bạch, quyền quyết định, chất lượng, phản hồi và cải tiến** khi thay đổi nghi thức hoặc công cụ.
6. Lập một **hồ sơ tailoring** nêu lý do, giả thuyết, rủi ro, số đo và điều kiện xem lại.
7. Đánh giá một thay đổi quy trình bằng dữ liệu trước/sau, thay vì chỉ dựa vào cảm nhận “ít họp hơn” hoặc “nhiều ticket hơn”.

## 1. Điều chỉnh cách tiếp cận là gì và không phải là gì?

Một **cách tiếp cận** trong phát triển phần mềm có thể bao gồm cách nhìn về giá trị, cấu trúc trách nhiệm, nhịp ra quyết định, chính sách di chuyển công việc và kỹ thuật tạo ra phần mềm đáng tin cậy.

**Tailoring** là thay đổi những thành phần phù hợp với bối cảnh **có chủ đích và có khả năng kiểm chứng**. Nó không đồng nghĩa với:

- **Bỏ mọi nguyên tắc vì “chúng ta đặc biệt”** mà không thay bằng cơ chế đáp ứng cùng nhu cầu.
- **Sao chép nghi thức từ một mô hình khác** mà không hiểu vấn đề cần giải quyết.
- **Đổi tên công việc cũ** thành Sprint, Kanban hoặc Agile để báo cáo đẹp hơn.
- **Hạ tiêu chuẩn Done và bảo mật** để có nhiều hạng mục hoàn thành.
- **Tránh trách nhiệm:** không ai rõ người quyết định, còn mỗi sự cố được đẩy sang người khác.
- **Tối đa hóa việc tuân thủ quy trình** dù quá trình đó không còn giúp người dùng hoặc nhóm.

Một thay đổi hợp lý thường có cấu trúc:

> “Vì tình trạng **A** đang gây vấn đề **B**, chúng ta sẽ đổi thực hành **C** nhưng giữ cơ chế bảo vệ **D**, thử trong phạm vi **E**, quan sát tín hiệu **F**, rồi quyết định có tiếp tục hay không.”

Ví dụ:

> “Do pull request thường chờ review ba ngày, nhóm sẽ dùng review theo cặp và giới hạn WIP ở cột Review trong hai tuần; vẫn giữ Definition of Done, kiểm thử phân quyền và review kỹ thuật phù hợp. Chúng ta sẽ xem thời gian chờ, lỗi sau merge và phản hồi của người thực hiện trước khi giữ chính sách mới.”

Đây là tailoring có **lý do, ranh giới và bằng chứng**, không chỉ là “thay đổi cho linh hoạt”.

## 2. Đừng trộn giá trị, framework và công cụ thành một thứ

Các cuộc tranh luận “có còn Agile không?” thường bế tắc vì các bên nói về những cấp độ khác nhau.

| Cấp độ | Câu hỏi | Ví dụ | Khả năng tùy biến |
| --- | --- | --- | --- |
| **Giá trị và tư duy** | Điều gì được coi là quan trọng khi đưa ra quyết định? | Cộng tác, phản hồi sớm, chất lượng và tạo giá trị. | Cần được thể hiện bằng hành động; không chỉ là khẩu hiệu. |
| **Nguyên tắc vận hành** | Cơ chế nào giúp đạt giá trị? | Giao từng phần nhỏ, kiểm tra thực tế, thích ứng, hạn chế lãng phí. | Cách triển khai linh hoạt, nhưng bỏ cơ chế phải hiểu tác động. |
| **Framework có định nghĩa** | Thành phần nào tạo nên framework đã chọn? | Scrum có accountabilities, events, artifacts và commitments xác định. | Một số lựa chọn triển khai linh hoạt; không nên tùy tiện bỏ cấu trúc cốt lõi rồi vẫn tuyên bố dùng nguyên framework. |
| **Phương pháp quản lý luồng** | Công việc đi qua hệ thống, được kiểm soát và cải tiến thế nào? | Kanban với Definition of Workflow, kiểm soát WIP và số đo dòng công việc. | Nhiều chính sách được thiết kế theo bối cảnh. |
| **Thực hành kỹ thuật** | Làm sao tạo phần mềm tốt và giảm rủi ro thay đổi? | TDD, CI, refactoring, pair programming. | Chọn và áp dụng theo nhu cầu; phải giữ cách kiểm chứng chất lượng tương ứng. |
| **Chính sách làm việc** | Trong nhóm này, ta ra quyết định cụ thể ra sao? | WIP limit, tiêu chí Ready, kênh xử lý sự cố, thời điểm release. | Có thể thử và đổi theo kết quả. |
| **Công cụ và biểu mẫu** | Thông tin được ghi ở đâu, ai nhìn thấy? | Bảng giấy, Jira, GitHub Issues, biểu đồ, mẫu user story. | Thay thế tương đối dễ nếu tính minh bạch vẫn được bảo đảm. |

**Nguyên tắc quan trọng:** không thể kết luận nhóm không Agile chỉ vì không dùng một công cụ. Ngược lại, cài bảng Kanban hoặc đặt tên cuộc họp là “Daily Scrum” **không bảo đảm** tổ chức đã có khả năng thích ứng.

### Ví dụ: story points có bắt buộc không?

**Không.** Scrum không bắt buộc dùng story points, dãy Fibonacci hoặc Planning Poker. Nhóm có thể dùng dữ liệu throughput/cycle time, chia nhỏ Product Backlog Items và trao đổi về khả thi để hỗ trợ dự báo.

Nhưng nếu bỏ story points, nhóm vẫn cần trả lời:

- Làm sao biết phạm vi có khả năng hoàn tất?
- Làm sao phát hiện mục quá lớn hoặc quá bất định?
- Làm sao trình bày forecast, giả định và rủi ro cho người liên quan?

**Bỏ một thực hành mà không giữ khả năng ra quyết định cần thiết** là thay đổi thiếu thiết kế.

## 3. Ba lớp cần kiểm tra trước khi thay đổi

Khi xem một thực hành, hãy phân loại thành ba lớp khác nhau.

### Lớp A — Thành phần xác định cách tiếp cận đã chọn

Nếu đang tuyên bố áp dụng **Scrum đầy đủ**, những phần cốt lõi do Scrum Guide xác định không thể bị thay theo ý thích mà vẫn gọi kết quả là Scrum như cũ.

Nếu dùng **Kanban**, phải có cơ chế xác định, trực quan hóa, quản lý và cải thiện luồng công việc. Chỉ có bảng cột mà không quản lý WIP hay quan sát flow metrics sẽ thiếu những năng lực cơ bản của phương pháp.

### Lớp B — Điều kiện an toàn và nghĩa vụ của sản phẩm/tổ chức

Đây không phải “nghi thức Agile” nhưng có thể **không được phép bỏ**:

- Bảo mật, phân quyền và quyền riêng tư.
- Tính toàn vẹn dữ liệu và đúng đắn giao dịch.
- Yêu cầu pháp lý, hợp đồng hoặc kiểm soát có hiệu lực.
- Điều kiện vận hành, quan sát sự cố và khả năng khôi phục phù hợp.
- Tiêu chuẩn chất lượng phải đạt trước khi coi sản phẩm sẵn sàng sử dụng.

Có thể cải thiện **cách** đáp ứng các điều kiện, chẳng hạn tự động hóa chứng cứ hoặc đưa chuyên gia vào sớm. Không được coi chúng là “lãng phí” rồi xóa khi chưa có cách bảo vệ tương đương hoặc phê chuẩn hợp lệ.

### Lớp C — Lựa chọn triển khai có thể thử thay đổi

Ví dụ:

- Phần mềm quản lý ticket, màu cột bảng.
- Cách trình bày backlog hoặc dùng user story theo mẫu nào.
- Thời điểm refinement hoặc hình thức trao đổi, trong giới hạn framework đang dùng.
- Cách ước lượng hoặc dự báo.
- WIP limit cụ thể, chính sách kéo việc, cách hiển thị blocked.
- Công cụ CI, mức tự động hóa, thiết kế pipeline.
- Nhịp kiểm tra roadmap hoặc báo cáo bên liên quan ngoài sự kiện bắt buộc của framework.

**Đừng đánh đồng “có thể thay đổi” với “nên bỏ”.** Một thực hành đang giúp nhóm ra quyết định tốt có thể đáng giữ cho tới khi có lý do và giải pháp thay thế rõ ràng.

## 4. Phần nền tảng Agile cần được bảo vệ

Agile là một tập hợp giá trị và nguyên tắc, **không phải một bộ sự kiện bắt buộc dùng chung**. Tuyên ngôn Agile nhấn mạnh bốn hướng ưu tiên:

1. **Cá nhân và tương tác** hơn quy trình và công cụ.
2. **Phần mềm hoạt động** hơn tài liệu đầy đủ quá mức.
3. **Cộng tác với khách hàng** hơn thương lượng hợp đồng như cơ chế duy nhất.
4. **Đáp ứng thay đổi** hơn bám theo một kế hoạch bất biến.

Điều này **không phủ nhận giá trị của vế bên phải**. Quy trình, tài liệu, hợp đồng và kế hoạch vẫn cần khi phục vụ sản phẩm và nghĩa vụ thực tế.

### Các cơ chế tối thiểu nên tự kiểm tra

| Cơ chế giá trị | Nếu thiếu, điều gì dễ xảy ra? | Một cách biểu hiện thực tế |
| --- | --- | --- |
| **Định hướng theo người dùng và kết quả** | Nhóm hoàn thành nhiều việc nhưng không tạo giá trị. | Mục tiêu sản phẩm gắn vấn đề người dùng và tín hiệu kiểm chứng. |
| **Giao phần tăng trưởng nhỏ có thể sử dụng** | Rủi ro tích hợp và phản hồi dồn về cuối. | Lát dọc đáp ứng DoD, có thể demo hoặc phát hành phù hợp. |
| **Phản hồi thường xuyên** | Tiếp tục đầu tư vào giả thuyết sai. | Xem kết quả sử dụng, kiểm thử, quan sát và trao đổi với bên liên quan. |
| **Minh bạch công việc và rủi ro** | Báo cáo xanh giả, phụ thuộc không được xử lý. | Backlog/bảng luồng nhìn thấy Done, blocked, mục tiêu và dự báo. |
| **Trách nhiệm và quyền quyết định rõ** | Ưu tiên xung đột, không ai xử lý trở ngại. | Người quyết định giá trị, người chịu chất lượng và kênh chuyển cấp được xác định. |
| **Kỹ thuật chất lượng và an toàn** | Mỗi thay đổi mới làm hệ thống kém ổn định. | Kiểm thử, tích hợp và chuẩn Done phù hợp; khắc phục lỗi sớm. |
| **Cải tiến dựa trên bằng chứng** | Quy trình tích lũy nghi thức, lãng phí không được gỡ. | Thử một thay đổi, đo kết quả, điều chỉnh hoặc hoàn tác. |
| **Nhịp làm việc bền vững** | Quá tải kéo dài, năng lực giao hàng suy giảm. | WIP phù hợp, có khả năng xử lý sự cố, không mặc định bù trễ bằng làm thêm giờ. |

Đây là **bộ câu hỏi thiết kế** rút ra từ tinh thần Agile, không phải danh sách “tám nghi thức Agile chính thức”. Khi một cách tiếp cận thay đổi, điều cần kiểm tra là **các chức năng này còn được thực hiện hữu hiệu không**.

### Phản hồi nhanh không có nghĩa phải phát hành mọi ngày

Một sản phẩm nhúng hoặc hệ thống có nghĩa vụ kiểm soát nghiêm có thể không đưa bản mới tới mọi người dùng hằng ngày. Nhóm vẫn có thể rút ngắn vòng phản hồi bằng mô phỏng, thử nghiệm có kiểm soát, tích hợp thường xuyên hoặc trình diễn Increment trong môi trường phù hợp.

Hãy phân biệt **tần suất phản hồi**, **tần suất deploy** và **tần suất release**. Chúng có thể khác nhau và cần được chọn theo giá trị cùng rủi ro.

## 5. Nếu chọn Scrum, cần giữ những gì để vẫn là Scrum?

**Scrum** là một framework nhẹ giúp con người, nhóm và tổ chức tạo giá trị thông qua giải pháp thích ứng cho những vấn đề phức tạp. Theo **Scrum Guide 2020**, Scrum dựa trên **empiricism (chủ nghĩa kinh nghiệm)** và **Lean thinking**, với ba trụ cột **transparency, inspection, adaptation**.

Scrum Guide cũng nêu framework là một **tổng thể không thể tùy ý thay cấu trúc cốt lõi**. Có thể chỉ thực hiện một phần của Scrum, nhưng kết quả đó **không còn là Scrum đầy đủ theo định nghĩa**. Nhóm vẫn có thể làm việc hữu ích; điều quan trọng là gọi đúng cách làm và nhìn rõ điều đã thay đổi.

### 5.1. Những thành phần cốt lõi

| Nhóm | Thành phần | Mục đích cần giữ |
| --- | --- | --- |
| **Accountabilities** | **Product Owner, Scrum Master, Developers** | Rõ trách nhiệm tối đa hóa giá trị, hiệu quả Scrum và tạo Increment đạt chất lượng. |
| **Events** | **Sprint, Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective** | Tạo nhịp kiểm tra và thích ứng có chủ đích. |
| **Artifacts** | **Product Backlog, Sprint Backlog, Increment** | Minh bạch về công việc, mục tiêu và kết quả. |
| **Commitments** | **Product Goal, Sprint Goal, Definition of Done** | Tăng tập trung và bảo đảm điều kiện rõ để đánh giá tiến bộ. |
| **Scrum values** | **Commitment, Focus, Openness, Respect, Courage** | Hỗ trợ hành vi cần thiết cho nhóm tự quản và empiricism. |

Các accountabilities không phải ba “phòng ban” tách biệt; Scrum Team cần **liên chức năng và tự quản**. Product Owner là **một người** chịu trách nhiệm về Product Backlog, dù có thể ủy quyền thực hiện một số công việc. Developers chịu trách nhiệm lập kế hoạch Sprint và chất lượng Increment.

### 5.2. Những lựa chọn thường có thể thay đổi trong Scrum

- **Độ dài Sprint**: chọn phù hợp sản phẩm trong giới hạn Scrum (**không quá một tháng**), giữ nhịp ổn định cần thiết.
- **Cách biểu diễn backlog**: user story, ví dụ, bảng, công cụ điện tử hay giấy nếu thông tin rõ.
- **Cách ước lượng và dự báo**: story points không bắt buộc; nhóm có thể dùng các kỹ thuật khác.
- **Định dạng thảo luận** trong sự kiện: câu hỏi, bảng trực quan, cách demo, kỹ thuật ra quyết định; vẫn giữ mục đích và timebox.
- **Các thực hành kỹ thuật**: TDD, pairing, CI, feature flags, flow metrics.
- **Chính sách phối hợp ngoài các sự kiện Scrum**: cách xử lý phụ thuộc, hỗ trợ vận hành, truyền thông với nhóm khác.

Ví dụ, Daily Scrum là sự kiện **15 phút của Developers** để kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog. Không có yêu cầu mỗi người phải lần lượt trả lời ba câu “hôm qua/hôm nay/trở ngại”, cũng không bắt buộc đứng. Thay định dạng từ báo cáo cá nhân sang kiểm tra flow có thể **làm Scrum hiệu quả hơn**.

### 5.3. Những thay đổi không nên gọi là “vẫn Scrum đầy đủ”

- **Bỏ Sprint Review** vì “đã demo riêng cho khách hàng”, nhưng không còn sự kiện Scrum Team cùng bên liên quan kiểm tra kết quả và thích ứng.
- **Bỏ Sprint Retrospective** vì “không đủ thời gian để cải tiến”.
- **Bỏ Daily Scrum** và không có sự kiện cùng mục đích trong Sprint, rồi vẫn gọi nguyên framework.
- **Để Project Manager tự sắp Product Backlog** trong khi Product Owner chỉ nhập ticket.
- **Giao task cho từng Developer từ bên ngoài** và loại bỏ quyền tự quản kế hoạch của Developers.
- **Đổi Definition of Done** thành “đã code xong” chỉ để Sprint có nhiều điểm.
- **Không có Sprint Goal**, chỉ cam kết danh sách công việc rời rạc.

Tổ chức có thể chủ động chọn một cách làm khác phù hợp hơn. Nhưng khi đã bỏ một phần định nghĩa, nên nói **“chúng tôi sử dụng một số thực hành lấy cảm hứng từ Scrum”** hoặc mô tả mô hình lai, thay vì tuyên bố tuân thủ đầy đủ.

### 5.4. Ví dụ thay đổi hợp lý

**Vấn đề:** Developers làm việc ở hai địa điểm nhưng họp Daily Scrum theo kiểu đọc báo cáo kéo dài 30 phút, không gỡ được điểm nghẽn.

**Tailoring trong Scrum:** Ghi cập nhật trước trên bảng; trong Daily Scrum 15 phút, Developers tập trung xem việc nào chặn Sprint Goal, chọn hành động phối hợp và điều chỉnh Sprint Backlog. Các trao đổi chuyên sâu tiếp tục sau sự kiện nếu cần. Nhóm vẫn giữ sự kiện và mục đích của nó, chỉ cải thiện **cách thực hiện**.

**Thay đổi khác về bản chất:** Bỏ hẳn Daily Scrum và chỉ gửi báo cáo mỗi tuần. Tổ chức có thể thử một mô hình làm việc khác, nhưng không nên coi đó là tuân thủ Scrum đầy đủ.

## 6. Nếu chọn Kanban, nền tảng cần giữ là quản lý dòng công việc

**Kanban** có tính thích ứng cao về cấu trúc nhóm, các cuộc họp và nhịp thời gian. Nhưng không phải “chỉ cần một bảng cột” là đủ.

Một cách áp dụng Kanban nghiêm túc cần làm rõ **Definition of Workflow** (định nghĩa luồng công việc), **trực quan hóa và chủ động quản lý các mục trong luồng**, **kiểm soát WIP** và **cải tiến luồng bằng phản hồi/số đo**.

### 6.1. Các nội dung cần có trong Definition of Workflow

| Nội dung | Câu hỏi thiết kế | Ví dụ cho nhóm hỗ trợ sản phẩm |
| --- | --- | --- |
| **Loại work items** | Những yêu cầu nào đi qua hệ thống? | Lỗi production, cải tiến nhỏ, thay đổi quyền truy cập. |
| **Mốc started/finished** | Khi nào một mục được coi đã bắt đầu và hoàn tất? | Bắt đầu khi kéo vào Develop; xong khi đạt DoD và qua Verify. |
| **Các trạng thái** | Mục đi qua bước nào, điểm chờ nào cần nhìn thấy? | Ready → Develop → Review → Verify → Done. |
| **Kiểm soát WIP** | Số mục đang dở được giới hạn hoặc điều phối ra sao? | WIP limit cho Develop/Review và chính sách xử lý blocked. |
| **Chính sách rõ ràng** | Tiêu chí kéo việc, xử lý gấp, tắc nghẽn, hoàn tất là gì? | Chỉ kéo mục mới khi có chỗ; sự cố mức cao theo chính sách expedite. |
| **Service Level Expectation (SLE)** | Dựa trên dữ liệu/giả định, kỳ vọng thời gian của loại mục này ra sao? | SLE được xem lại khi có đủ dữ liệu tương thích. |

Các giới hạn cụ thể, tên cột, loại việc và SLE **không phải số chuẩn áp cho mọi nhóm**. Nhóm cần tự thiết kế theo nhu cầu và năng lực.

### 6.2. Điều có thể tùy biến mạnh

- Có hay không Sprint/timebox cố định.
- Các cuộc họp bổ sung và nhịp review flow.
- Số cột, nhãn, chính sách nhóm loại việc.
- Cách giới hạn WIP và khi nào dùng ngoại lệ cho sự cố.
- Độ chi tiết của công việc, miễn là đo và quản lý flow nhất quán.
- Công cụ hiển thị board, dashboard, cảnh báo công việc già.

### 6.3. Điều không nên bỏ mà vẫn coi là quản lý Kanban hiệu quả

Nếu nhóm có bảng ba cột **To Do – Doing – Done** nhưng:

- Mỗi người mở vô hạn việc.
- Không ai nhìn work item age hoặc các mục bị chặn.
- Không có chính sách xác định thế nào là Done.
- Không biết cycle time/throughput và không xem lại flow.
- Không có phản hồi để cải tiến cách làm.

Thì bảng đang là **công cụ theo dõi**, chưa tạo được các năng lực cốt lõi của phương pháp Kanban. Nhóm nên cải thiện chính sách và phản hồi trước khi đầu tư thêm phần mềm.

### 6.4. Kanban không bắt buộc làm việc không có mục tiêu sản phẩm

Một nhóm Kanban vẫn có thể dùng Product Goal, backlog có thứ tự, roadmap và các mốc kiểm tra giá trị. **Không có Sprint không đồng nghĩa không có ưu tiên dài hạn**, và việc xử lý sự cố khẩn không có nghĩa toàn bộ cải tiến sản phẩm luôn bị bỏ lại.

## 7. Nếu chọn XP, cần bảo vệ năng lực tạo phần mềm chất lượng

**Extreme Programming (XP)** tập trung vào năng lực kỹ thuật và cộng tác để phát triển phần mềm đáp ứng thay đổi nhanh mà vẫn đáng tin. Những giá trị thường được gắn với XP là **communication, simplicity, feedback, courage, respect**.

Nhóm có thể lựa chọn các thực hành XP để bổ trợ Scrum hoặc Kanban, ví dụ:

- Test-driven development (TDD).
- Continuous Integration (CI).
- Refactoring thường xuyên.
- Pair Programming.
- Small releases.
- Simple design.
- Collective code ownership và coding standards phù hợp.
- Sustainable pace.

### Phần nền tảng cần bảo vệ

Không nhất thiết mọi nhóm đều lập trình cặp cho **100%** công việc, nhưng nếu nhóm muốn phản hồi kỹ thuật nhanh và thay đổi an toàn, phải có **một hệ thống kiểm chứng có hiệu lực**.

| Câu hỏi | Dấu hiệu giữ được nền tảng kỹ thuật |
| --- | --- |
| Làm sao biết thay đổi mới không làm hỏng chức năng cũ? | Kiểm thử hồi quy phù hợp, có kết quả đáng tin. |
| Khi nào phát hiện xung đột tích hợp? | Tích hợp thường xuyên, pipeline hoặc quy trình phản hồi kịp thời. |
| Code có còn dễ thay ở Sprint tiếp theo? | Refactoring có mục đích, thiết kế đủ đơn giản, không sao chép quy tắc tràn lan. |
| Kiến thức có bị khóa vào một người? | Review, pairing, tài liệu cần thiết và chia sẻ trách nhiệm. |
| Có thể phát hành phần nhỏ an toàn không? | Lát dọc, DoD, kiểm soát vận hành và khả năng khôi phục phù hợp. |

Nếu “tailoring XP” bằng cách **bỏ kiểm thử, không tích hợp cho tới cuối quý và dừng refactoring**, nhóm đã đánh mất nhiều cơ chế cho phép thích ứng an toàn. Khi đó không thể chỉ nói “chúng tôi vẫn nhanh” rồi coi kỹ thuật chất lượng là tùy chọn không có hậu quả.

### Tùy biến nhưng cần mô tả chính xác

Một nhóm có thể nói: “Chúng tôi sử dụng TDD cho logic nghiệp vụ rủi ro cao, CI cho mọi thay đổi và lập trình cặp khi chạm mã ít người hiểu.” Đây là **sử dụng một số thực hành XP**, không nhất thiết khẳng định nhóm thực hiện đầy đủ mọi thực hành của XP.

## 8. Lean và các cách tiếp cận khác: giữ mục tiêu, không giữ tên gọi

**Lean thinking** hướng tới tối ưu dòng tạo giá trị, giảm lãng phí, xây chất lượng vào quá trình và học hỏi cải tiến. Khi điều chỉnh một cách làm theo Lean, cần giữ góc nhìn **toàn hệ thống**, thay vì chỉ làm từng cá nhân bận hơn.

### 8.1. Lean: những cơ chế nên bảo vệ

- Làm rõ **giá trị thực sự** từ góc nhìn khách hàng/người dùng.
- Xem **dòng giá trị đầu cuối**, gồm hàng chờ, bàn giao, làm lại và việc chưa Done.
- Giảm kích thước lô công việc, quản lý WIP và cải thiện flow.
- Phát hiện lỗi sớm, giữ tiêu chuẩn chất lượng.
- Dùng phản hồi và thực nghiệm để tiếp tục cải tiến.
- Tôn trọng con người và xây năng lực bền vững.

**Chỉ cắt bớt số cuộc họp** chưa thể kết luận là Lean nếu thời gian chờ và lỗi sản phẩm tăng.

### 8.2. Những tên gọi khác có thể gặp

| Cách tiếp cận | Có thể phù hợp khi | Điều cần thận trọng |
| --- | --- | --- |
| **Scrumban** | Muốn giữ một số cơ chế Scrum và dùng cách quản lý luồng của Kanban. | Không có một định nghĩa duy nhất cho mọi mô hình mang tên Scrumban; phải công khai thành phần giữ/bỏ và chính sách. |
| **Crystal** | Muốn điều chỉnh cách cộng tác theo quy mô nhóm và mức độ nghiêm trọng của rủi ro. | Không nên lấy “ít quy trình” làm lý do bỏ giao tiếp, chất lượng hay điều kiện an toàn. |
| **Feature-Driven Development (FDD)** | Muốn tổ chức công việc theo những tính năng nhỏ có giá trị trong bối cảnh phù hợp. | Cần tránh biến “feature” thành danh sách output không có phản hồi về outcome. |
| **DSDM / AgilePM** | Cần một cách tiếp cận quản trị dự án Agile với một số cấu trúc và nguyên tắc rõ. | Nếu sử dụng phương pháp có định nghĩa cụ thể, cần xem đúng các thành phần chính thức trước khi tuyên bố tuân thủ. |
| **Các mô hình mở rộng tổ chức** | Nhiều nhóm cùng sản phẩm hoặc nhiều đơn vị có phụ thuộc lớn. | Tăng lớp phối hợp không tự giải quyết ưu tiên xung đột hay thiếu tích hợp; giữ rõ quyền sản phẩm và chất lượng. |
| **Cách làm kết hợp Agile – quản trị truyền thống** | Có ngân sách, hợp đồng, quy định và mốc cấp tổ chức phải đáp ứng. | Tránh một hệ thống báo cáo cố định lấn át phản hồi và quyền tự quản của nhóm. |

Bảng chỉ cho thấy **những lựa chọn có thể nghiên cứu**, không xếp hạng hoặc khẳng định chúng có cùng quy tắc. Với từng phương pháp được chọn, cần đối chiếu cấu trúc chính thức của phương pháp đó nếu muốn tuyên bố áp dụng theo đúng định nghĩa.

### 8.3. Mô hình lai không mặc nhiên xấu

Một Scrum Team có thể áp dụng **Kanban để quản lý WIP/flow** và **XP để kiểm thử, tích hợp, refactoring**. Nếu vẫn giữ đầy đủ Scrum, đó có thể là **Scrum được bổ sung các thực hành**.

Ngược lại, nhóm có thể chọn một luồng Kanban không Sprint và tổ chức review sản phẩm theo nhịp riêng. Cách này có thể rất hiệu quả, nhưng không nên gọi là Scrum đầy đủ khi các sự kiện và commitments cốt lõi không còn.

## 9. Cách nhận diện “phần nền tảng” bằng bốn câu hỏi

Trước khi bỏ hoặc thay một thực hành, hãy hỏi:

1. **Nguồn gốc:** thành phần này là yêu cầu chính thức của framework, nghĩa vụ tổ chức, hay chỉ thói quen của nhóm?
2. **Chức năng:** nó tạo ra minh bạch, chất lượng, phản hồi, quyền quyết định hoặc dòng công việc nào?
3. **Rủi ro khi bỏ:** điều gì có thể hỏng hoặc không còn được kiểm chứng? Ai chịu ảnh hưởng?
4. **Cơ chế thay thế và bằng chứng:** nếu bỏ, cách nào vẫn bảo đảm chức năng cần thiết và làm sao biết hiệu quả?

### Ví dụ phân loại

| Thực hành được đề xuất thay | Bản chất | Có thể thay như thế nào? | Điều cần giữ/kiểm tra |
| --- | --- | --- | --- |
| **Dùng Jira thay bảng giấy** | Công cụ. | Đổi công cụ thoải mái nếu nhóm sử dụng được. | Minh bạch backlog, trạng thái và quyết định. |
| **Dùng story points** | Kỹ thuật ước lượng tùy chọn. | Dùng throughput/cycle time hoặc ước lượng cách khác. | Ra quyết định về phạm vi và forecast có cơ sở. |
| **Daily Scrum kiểu ba câu hỏi** | Định dạng sự kiện. | Dùng walkthrough bảng, tập trung Sprint Goal. | Daily Scrum vẫn có mục đích kiểm tra/thích ứng, timebox và người tham gia phù hợp. |
| **Bỏ hẳn Sprint Review trong Scrum** | Bỏ một sự kiện cốt lõi. | Nếu muốn Scrum đầy đủ, không bỏ; cải thiện nội dung Review. Nếu chọn mô hình khác, mô tả trung thực. | Phản hồi stakeholder và kiểm tra tiến độ Product Goal. |
| **Thay WIP limit 3 bằng 4** | Chính sách luồng. | Thử với dữ liệu và năng lực phù hợp. | WIP vẫn được kiểm soát; cycle time và hàng chờ được quan sát. |
| **Bỏ mọi kiểm thử hồi quy** | Bỏ cơ chế chất lượng. | Không nên bỏ mà không có lưới an toàn tương đương. | Độ tin cậy, quyền truy cập và khả năng thay đổi an toàn. |
| **Tự động hóa việc tạo bằng chứng tuân thủ** | Cải tiến cách đáp ứng nghĩa vụ. | Có thể thay thao tác thủ công bằng pipeline kiểm chứng. | Bằng chứng đúng, có thể truy xuất, được chức năng có thẩm quyền chấp nhận. |
| **Release trước Sprint Review** | Lựa chọn giao hàng. | Có thể khi Increment đạt DoD và điều kiện phát hành phù hợp. | Không dùng Sprint Review như cổng phát hành mặc định; vẫn giữ sự kiện để kiểm tra/thích ứng. |
| **Bỏ Product Owner, PM tự ưu tiên** | Thay accountability Scrum. | Không phù hợp khi tuyên bố dùng Scrum đầy đủ. | Một nguồn ưu tiên giá trị rõ và trách nhiệm giải trình. |
| **Đổi giờ hoặc hình thức refinement** | Chính sách phối hợp. | Điều chỉnh theo nhu cầu nhóm và người liên quan. | Product Backlog Items đủ được hiểu để lựa chọn công việc hiệu quả. |

Một quy tắc hữu ích: **chỉ bỏ bước khi đã xác định rõ chức năng của nó, tác động khi bỏ và cách bù cho chức năng còn cần thiết**.

## 10. Một sơ đồ quyết định trước khi tùy biến

~~~mermaid
flowchart TD
    A["Muốn thay hoặc bỏ một thực hành"] --> B["Vấn đề thực tế và kết quả mong muốn là gì?"]
    B --> C{"Có nghĩa vụ chất lượng, an toàn, hợp đồng không?"}
    C -->|"Có"| D["Giữ điều kiện; cải tiến cách đáp ứng và làm rõ thẩm quyền"]
    C -->|"Không"| E{"Là phần cốt lõi của framework đang tuyên bố dùng?"}
    E -->|"Có"| F{"Vẫn muốn dùng nguyên framework?"}
    F -->|"Có"| G["Giữ phần cốt lõi; cải thiện cách thực hiện hoặc kỹ thuật bổ trợ"]
    F -->|"Không"| H["Chọn mô hình khác và gọi đúng tên; thiết kế cơ chế thay thế"]
    E -->|"Không"| I["Đề xuất lựa chọn triển khai mới"]
    D --> J["Nêu giả thuyết, rủi ro, phạm vi và số đo"]
    G --> J
    H --> J
    I --> J
    J --> K["Thử thay đổi có giới hạn"]
    K --> L["Đo chất lượng, giá trị, flow và phản hồi"]
    L --> M{"Kết quả chấp nhận được?"}
    M -->|"Có"| N["Chuẩn hóa chính sách; tiếp tục quan sát"]
    M -->|"Không/Chưa rõ"| O["Điều chỉnh, hoàn tác hoặc thử thêm; ghi điều học được"]
    O --> J
~~~

Sơ đồ mang tính **khung suy nghĩ**. Trong thực tế một đề xuất có thể vừa là vấn đề framework vừa là vấn đề kiểm soát. Khi đó, cần giải quyết **cả hai**, không coi mũi tên là cổng phê duyệt theo thứ tự bất biến.

### Chất lượng của một quyết định tailoring

Một quyết định tốt không chỉ ghi “bỏ họp X”, mà giải thích:

- Vấn đề xác định từ đâu?
- Ai đang chịu tác động?
- Cơ chế cũ phục vụ mục đích gì?
- Khả năng nào vẫn phải giữ?
- Rủi ro lớn nhất là gì?
- Người nào có quyền quyết định thử?
- Sau bao lâu hoặc khi xuất hiện tín hiệu nào sẽ đánh giá lại?

## 11. Tình huống 1: Scrum Team phân tán và muốn giảm họp

Nhóm có Developers làm việc ở nhiều địa điểm. Daily Scrum buổi sáng bị biến thành họp quản lý kéo dài 40 phút. PO và người quản lý lần lượt hỏi từng người “hôm qua đã làm gì”, khiến mọi người cảm thấy cuộc họp không giúp đưa Sprint Goal tiến lên.

### Đề xuất A — Điều chỉnh cách thực hiện, giữ Scrum

- Developers chuẩn bị thông tin trạng thái bằng bảng chung.
- Daily Scrum giữ **15 phút**, tập trung tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog.
- Chỉ những người cần phối hợp sâu ở lại trao đổi thêm sau Daily Scrum.
- Scrum Master hỗ trợ cải thiện cách hiểu mục đích sự kiện.
- Vấn đề khác múi giờ được giải quyết bằng lịch làm việc phù hợp và sự minh bạch; nhóm không dùng cập nhật bất đồng bộ để thay thế mọi tương tác cần thiết.

**Điều được giữ:** sự kiện Scrum, khả năng kiểm tra/thích ứng hằng ngày, trách nhiệm Developers và mục tiêu chung.

### Đề xuất B — Bỏ hẳn Daily Scrum, chuyển sang cập nhật tuần

Nếu nhóm quyết định cách làm mới hiệu quả hơn, họ có thể thử một mô hình khác. Nhưng khi **không còn Daily Scrum theo định nghĩa**, không nên tuyên bố “vẫn Scrum đầy đủ”. Cần xây cơ chế thay thế để:

- Phát hiện trở ngại sớm.
- Đồng bộ quyết định khi rủi ro xuất hiện.
- Thích ứng kế hoạch ngắn hạn.
- Bảo đảm người phụ trách giải quyết phụ thuộc.
- Không để trao đổi bất đồng bộ kéo dài hàng ngày khi cần quyết định trực tiếp.

**Câu hỏi quyết định:** lợi ích giảm thời gian họp có bù cho rủi ro phản hồi chậm, WIP tăng hoặc hiểu sai mục tiêu không? Cần đo thay vì mặc định ít họp hơn luôn tốt hơn.

## 12. Tình huống 2: Nhóm bảo trì bị gián đoạn bởi sự cố

Một nhóm phụ trách API cho nền tảng học có nhiều ticket nhỏ nhưng mỗi tuần xuất hiện sự cố production không dự báo trước. Họ đang dùng Sprint hai tuần, nhưng liên tục đổi công việc giữa Sprint và rất ít Sprint Goal còn có ý nghĩa.

### 12.1. Chẩn đoán trước khi đổi framework

Hãy kiểm tra:

- Tỷ lệ thời gian dành cho sự cố, cải tiến và yêu cầu mới.
- Mức khẩn và nghĩa vụ phản hồi của các loại sự cố.
- Mục đang In Progress bị gián đoạn bao nhiêu lần.
- Có phụ thuộc nào gây hàng chờ dài?
- Scrum Team có thể tạo Sprint Goal có ý nghĩa trong bối cảnh hiện tại không?
- Hệ thống trực ban/sự cố có đầu mối và chính sách xử lý không?

Nếu vấn đề chỉ là không có chính sách xử lý sự cố, **bỏ Scrum ngay** chưa chắc giải quyết được. Nếu bản chất công việc liên tục thay đổi và mục tiêu Sprint khó ổn định, **Kanban với chính sách rõ** có thể phù hợp hơn.

### 12.2. Một mô hình Kanban có thể chọn

~~~text
Intake -> Ready -> In Progress -> Review -> Verify -> Done
                    WIP <= 3     WIP <= 2

Lớp công việc:
  - Expedite: sự cố nghiêm trọng theo tiêu chí và thẩm quyền rõ.
  - Standard: lỗi/cải tiến thông thường.
  - Fixed-date: công việc có mốc bên ngoài thực sự.
  - Intangible: cải tiến phòng ngừa hoặc giảm nợ kỹ thuật.
~~~

Các lớp công việc và WIP limit là **ví dụ thiết kế**. Nhóm cần làm rõ khi nào được dùng expedite, ai xác nhận mức khẩn và làm sao ngăn mọi yêu cầu tự gắn nhãn “gấp”.

### 12.3. Những phần nền tảng không được mất

- **Ưu tiên:** người chịu trách nhiệm phân xử khi sự cố và cải tiến cạnh tranh năng lực.
- **Chất lượng:** tiêu chí Done/kiểm thử và bảo mật cho lỗi production.
- **Minh bạch:** WIP, blocked, tuổi công việc, thông tin sự cố.
- **Dự báo:** cycle time/throughput theo loại việc với dữ liệu thích hợp.
- **Phản hồi:** kết quả xử lý sự cố, phản hồi người dùng và mốc đánh giá cải tiến.
- **Bảo vệ công việc phòng ngừa:** tránh dành 100% năng lực chạy theo sự cố khiến nguyên nhân gốc không được giải quyết.

Một nhóm Kanban vẫn cần giải thích **vì sao các mục đang được làm**, chứ không chỉ tự động kéo ticket gần nhất.

## 13. Tình huống 3: Sản phẩm có nghĩa vụ tuân thủ

Một nhóm xây hệ thống liên quan thông tin tài chính hoặc dữ liệu nhạy cảm có điều kiện kiểm soát về phân quyền, lưu vết, kiểm thử và phê duyệt ở phạm vi nhất định. Họ muốn giảm thời gian từ code tới release.

### Điều chỉnh sai

> “Agile ưu tiên phần mềm hoạt động hơn tài liệu, vậy bỏ bằng chứng kiểm thử và phê duyệt bắt buộc để release mỗi ngày.”

Cách hiểu này sai cả về Agile lẫn rủi ro sản phẩm. Ưu tiên giá trị **không đồng nghĩa bỏ luật, quyền riêng tư hoặc nghĩa vụ hợp đồng**.

### Một cách làm có thể cải tiến

| Công việc | Cần giữ | Có thể cải tiến |
| --- | --- | --- |
| **Kiểm tra quyền truy cập** | Không để tài khoản trái quyền thao tác hoặc xem dữ liệu. | Kiểm thử tự động, kiểm tra sớm trong pipeline. |
| **Bằng chứng thay đổi** | Có khả năng truy xuất ai thay, phạm vi, kết quả kiểm tra theo nghĩa vụ. | Thu thập tự động từ commit, build, test và phê duyệt phù hợp. |
| **Phê duyệt chuyên môn bắt buộc** | Người có thẩm quyền và tiêu chí rõ. | Đưa chuyên gia vào sớm, giảm chuyển giao lặp hoặc làm rõ thời hạn phản hồi. |
| **Quản lý dữ liệu và migration** | Tính toàn vẹn, khả năng khôi phục và quyền riêng tư. | Thử trên dữ liệu phù hợp, chuyển đổi theo giai đoạn, quan sát kết quả. |
| **Release** | Có điều kiện sẵn sàng và cách xử lý sự cố. | Tự động hóa các bước đủ tin cậy, mở giới hạn trước khi mở rộng. |

Nếu tổ chức chọn Scrum, vẫn giữ **DoD và các cấu trúc Scrum**; thêm cơ chế tuân thủ phù hợp. Nếu chọn Kanban, vẫn quản lý luồng và kiểm soát WIP, đồng thời thể hiện rõ các bước kiểm soát cần thiết.

**Không phải mọi bước chờ kiểm soát đều là lãng phí**. Việc cần tìm là phần chờ do chính sách chưa rõ, hồ sơ bị nộp nhiều lần hoặc người có thẩm quyền tham gia quá muộn.

## 14. Ví dụ xuyên suốt: thiết kế cách làm cho một nền tảng học Java

Giả sử đội phát triển có các mục tiêu:

- Giúp người mới học Java dễ dàng quay lại bài đang học.
- Khắc phục lỗi sử dụng và sự cố production trong thời gian phù hợp.
- Duy trì tốc độ thêm user story mới mà không tăng nợ kỹ thuật.
- Giữ bảo vệ thông tin người học và quyền truy cập.

Nhóm có **một Product Owner, một Scrum Master, Developers đa chuyên môn**, làm việc cùng bộ phận vận hành/bảo mật. Công việc gồm phát triển tính năng theo sản phẩm và yêu cầu hỗ trợ không báo trước.

### 14.1. Chọn nền tảng quản trị giá trị

Nhóm cân nhắc giữ **Scrum làm framework chính**, áp dụng các kỹ thuật **Kanban** để nhìn WIP và **XP** để giữ chất lượng. Lý do:

- Các mục tiêu cải thiện trải nghiệm vẫn có thể được hình thành thành **Sprint Goal**.
- Nhóm cần **Sprint Review** để học từ người dùng và **Retrospective** để cải tiến.
- Hàng chờ review và công việc khẩn cần được trực quan hóa/kiểm soát.
- Tính năng tiến độ học có rủi ro dữ liệu, cần kiểm thử và tích hợp sớm.

Đây là **một lựa chọn minh họa**, không phải kết luận tổ chức nào có cùng điều kiện đều phải chọn Scrum.

### 14.2. Bộ cấu trúc được giữ

| Lớp | Phần giữ | Vì sao |
| --- | --- | --- |
| **Scrum** | PO, SM, Developers; năm sự kiện; ba tạo tác và commitments. | Giữ minh bạch, quyền quyết định, mục tiêu, kiểm tra/thích ứng và DoD. |
| **Giá trị sản phẩm** | Product Goal và thứ tự Product Backlog rõ. | Không để lỗi khẩn hoặc yêu cầu mới che mất định hướng người học. |
| **Flow management** | Board chung, WIP limit thí điểm, blocked policy, work item age. | Thấy hàng chờ và tập trung hoàn tất. |
| **Kỹ thuật** | Kiểm thử phân quyền, CI, review và refactoring. | Có thể thêm lát nhỏ mà ít lỗi hồi quy. |
| **Phát hành** | Quy tắc release có điều kiện, người có thẩm quyền và tín hiệu theo dõi. | Không nhầm Increment Done với phần đã mở cho người dùng. |
| **Cải tiến** | Review sản phẩm và Retrospective dùng dữ liệu thực tế. | Không lặp lại quy trình kém hiệu quả. |

### 14.3. Bộ lựa chọn được thay đổi

| Trước | Sau khi thử tùy biến | Lý do |
| --- | --- | --- |
| Story points cho mọi ticket, kể cả sự cố. | Story có độ bất định cao được thảo luận/chia lát; forecast luồng dùng throughput/cycle time khi dữ liệu phù hợp. | Không tạo ước lượng giả chính xác cho sự cố. |
| Bảng Scrum chỉ có “To Do, Doing, Done”. | Bổ sung trạng thái Review, Verify và blocked hiển thị; giới hạn WIP nơi có hàng chờ. | Nhìn rõ công việc gần Done và điểm nghẽn. |
| Daily Scrum thành báo cáo cá nhân cho cấp quản lý. | Developers kiểm tra mục tiêu Sprint và việc bị chặn trong timebox 15 phút. | Giữ mục đích Scrum thay vì báo cáo hình thức. |
| Chờ cuối Sprint mới tích hợp. | CI và kiểm thử trên các lát nhỏ, tích hợp thường xuyên. | Phát hiện lỗi sớm. |
| Đợi Sprint Review mới release mọi thay đổi. | Increment đạt DoD có thể được release khi sẵn sàng theo chính sách tổ chức. | Có cơ hội nhận phản hồi sớm, vẫn giữ Sprint Review. |
| Việc khẩn được nhắn riêng cho từng Developer. | Có chính sách tiếp nhận, mức độ khẩn và trao đổi tác động tới Sprint Goal/PO. | Giảm xung đột và gián đoạn vô hình. |

Các thay đổi ở bảng được chọn để **bổ trợ Scrum**, không loại bỏ các phần cấu thành framework.

### 14.4. User story đầu tiên có thể kiểm chứng

> **Là** người học đã xem dở video, **tôi muốn** mở lại tại vị trí đã lưu trên tài khoản của mình, **để** không phải tìm lại đoạn đang học.

Tiêu chí chấp nhận minh họa:

~~~gherkin
Feature: Tiếp tục video đang học

Scenario: Khôi phục vị trí đã lưu
  Given người học đã đăng nhập và có quyền xem "Bài A"
  And hệ thống đã lưu vị trí 06:15 cho người học trong "Bài A"
  When người học mở lại "Bài A"
  Then video có thể tiếp tục ở vị trí đã lưu trong sai số đã thỏa thuận

Scenario: Không có tiến độ
  Given người học có quyền xem "Bài A"
  And chưa lưu tiến độ cho người học và "Bài A"
  When người học mở "Bài A"
  Then video bắt đầu từ đầu
  And giao diện không khẳng định đã khôi phục tiến độ

Scenario: Truy cập dữ liệu của người khác
  Given tài khoản không có quyền xem tiến độ của học viên khác
  When tài khoản đó yêu cầu tiến độ học của học viên khác
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ thông tin tiến độ riêng tư
~~~

Lát này cần đáp ứng **DoD**. Không nên trì hoãn phân quyền sang “story chất lượng” về sau chỉ để giao phần nhỏ hơn. Một số tính năng nâng cao như đồng bộ offline có thể được đưa vào backlog sau khi có bằng chứng nhu cầu.

### 14.5. Thu dữ liệu và điều chỉnh

Sau một số Sprint, nhóm xem:

- Người học có thực sự quay lại video dễ hơn không?
- Flow có bớt hàng chờ Review/Verify không?
- Cycle time có ngắn hơn với **cùng tiêu chuẩn Done** không?
- Tỷ lệ lỗi dữ liệu và quyền truy cập có ổn định không?
- Việc khẩn ảnh hưởng Sprint Goal với tần suất thế nào?
- Developers có nêu rủi ro sớm và phối hợp tốt hơn không?

Nếu công việc khẩn tiếp tục phá khả năng hình thành Sprint Goal có ý nghĩa, nhóm có thể **xem lại lựa chọn framework**. Giữ Scrum chỉ vì tên gọi không quan trọng bằng việc quản lý giá trị, rủi ro và học hỏi thật.

## 15. Sự đánh đổi cần làm minh bạch khi phối hợp nhiều cách tiếp cận

Một cách làm lai có thể đạt lợi ích của nhiều phương pháp, nhưng cũng có thể tích lũy **nghi thức trùng lặp**.

| Xung đột có thể xảy ra | Biểu hiện | Cách giải quyết |
| --- | --- | --- |
| **Sprint commitment vs yêu cầu khẩn liên tục** | Sprint Goal liên tục gặp rủi ro. | Chính sách tiếp nhận, bảo vệ mục tiêu, trao đổi ưu tiên; nếu bối cảnh không phù hợp, cân nhắc đổi mô hình. |
| **WIP limit vs mọi người phải luôn bận** | Công việc Review đầy nhưng vẫn yêu cầu mở story mới. | Tối ưu hoàn tất, phối hợp tháo nút thắt thay vì tối đa hóa sử dụng cá nhân. |
| **Story points vs flow metrics** | Hai hệ thống số liệu cạnh tranh và tạo báo cáo trùng. | Chọn dữ liệu theo quyết định; không bắt buộc đo mọi thứ bằng points. |
| **Release thường xuyên vs nghĩa vụ tuân thủ** | Nhóm muốn mở ngay nhưng thiếu chứng cứ an toàn. | Tự động hóa kiểm soát sớm, giới hạn rollout, giữ nghĩa vụ cần thiết. |
| **PO priority vs quản lý dự án** | PM giao yêu cầu theo hợp đồng còn PO có Product Backlog khác. | Làm rõ quyền PO trong Scrum; PM cung cấp nghĩa vụ/mốc, phối hợp quyết định bên ngoài. |
| **Autonomy vs tiêu chuẩn tổ chức** | Nhóm muốn bỏ kiểm tra phân quyền hoặc vận hành. | Tự quản cách thực hiện trong giới hạn điều kiện chất lượng/an toàn bắt buộc. |
| **Cải tiến kỹ thuật vs giá trị ngắn hạn** | Refactoring bị hoãn mãi hoặc chiếm toàn Sprint không rõ mục tiêu. | Ưu tiên theo rủi ro và khả năng tạo Increment, nêu công việc đáng kể trong backlog. |

**Hybrid không phải là phép cộng tất cả cuộc họp.** Khi có hai cơ chế cùng phục vụ một mục đích, hãy tìm cách dùng chung thông tin hoặc làm rõ giá trị riêng, tránh bắt nhóm nhập cùng trạng thái ở nhiều nơi.

## 16. Quyền quyết định và trách nhiệm không thể để trống

Một quy trình có thể ít nghi thức nhưng vẫn cần biết **ai có quyền ra quyết định** và ai chịu trách nhiệm làm cho quyết định có hiệu lực.

### Các câu hỏi tối thiểu

- **Giá trị:** Ai quyết định thứ tự việc dựa trên mục tiêu sản phẩm và rủi ro?
- **Thực thi:** Ai quyết định cách làm và phân chia công việc?
- **Chất lượng:** Ai xác nhận tiêu chuẩn Done, và ai thực hiện kiểm tra?
- **Sự cố:** Khi có lỗi nghiêm trọng, ai phân loại mức khẩn, ai xử lý và ai cần được thông báo?
- **Phát hành:** Ai có quyền mở/đóng tính năng cho nhóm người dùng, theo điều kiện nào?
- **Hợp đồng/ngân sách:** Ai có thẩm quyền với các nghĩa vụ ngoài Scrum Team?
- **Cải tiến:** Ai theo dõi tác động của chính sách mới, và ai có quyền điều chỉnh?

Trong **Scrum**, các accountabilities được xác định; quyền hợp đồng, ngân sách hoặc phê duyệt bên ngoài cần được tổ chức làm rõ, không tự động chuyển vào Product Owner, Developers hay Scrum Master.

Trong **Kanban không Scrum**, tổ chức vẫn phải phân định đầu mối ưu tiên, chất lượng và phát hành. Việc không quy định các vai trò giống Scrum không có nghĩa không cần trách nhiệm giải trình.

### Decision log ngắn thay cho phân quyền theo cảm tính

~~~text
VẤN ĐỀ:
  Vì sao cần quyết định?

PHẠM VI:
  Ảnh hưởng backlog, Sprint, kỹ thuật, chất lượng hay hợp đồng?

NGƯỜI QUYẾT ĐỊNH:
  Theo framework đã chọn và thẩm quyền tổ chức.

NHỮNG NGƯỜI CẦN THAM VẤN:
  Người hiểu giá trị, kỹ thuật, bảo mật, vận hành hoặc nghĩa vụ liên quan.

LỰA CHỌN VÀ ĐÁNH ĐỔI:
  Giá trị, nguồn lực, thời gian, rủi ro, chất lượng.

KẾT LUẬN:
  Quyết định, giả định, cách thông báo và mốc xem lại.
~~~

Không cần lập biên bản cho mỗi lần đổi nhãn ticket. Mẫu phù hợp với những quyết định ảnh hưởng tới nhiều người hoặc có rủi ro đáng kể.

## 17. Chọn số đo phục vụ mục tiêu, không biến số đo thành mục tiêu

Tùy biến phương pháp nên đi kèm số đo phản ánh **vấn đề thực tế**. Không nên chọn chỉ số trước rồi điều chỉnh hành vi chỉ để con số đẹp.

| Muốn bảo vệ hoặc cải thiện | Số đo/tín hiệu có thể dùng | Sai lầm khi diễn giải |
| --- | --- | --- |
| **Giá trị sản phẩm** | Tỷ lệ hoàn tất tác vụ, người dùng quay lại, phản hồi định tính. | Gán mọi biến động cho một tính năng khi chưa xét yếu tố khác. |
| **Khả năng giao hàng** | Throughput, cycle time, lead time, work item age. | Dùng số ticket để chấm năng suất cá nhân. |
| **Quản lý WIP** | Số mục đang mở, thời gian blocked, hàng chờ theo trạng thái. | Đặt WIP limit đẹp trên bảng nhưng luôn bỏ qua. |
| **Chất lượng** | Lỗi sau release, lỗi hồi quy, sự cố dữ liệu, điều kiện DoD. | Hạ DoD để cycle time ngắn hơn. |
| **Phản hồi** | Thời gian từ Increment Done đến khi có dữ liệu sử dụng phù hợp. | Đếm số buổi demo mà không biết điều gì được học. |
| **Khả năng dự báo** | Phân bố cycle time, throughput lịch sử, mức thay đổi forecast và giả định. | Xem khoảng dự báo là lời hứa tuyệt đối. |
| **Cải tiến bền vững** | Nút thắt được xử lý, phản hồi nhóm, số lần gián đoạn và năng lực xử lý sự cố. | Chỉ hỏi “giảm bao nhiêu giờ họp” mà bỏ tác động tới phối hợp. |

### 17.1. Ví dụ minh họa trước/sau

Giả sử nhóm muốn giảm thời gian chờ review. Trong hai khoảng quan sát có phạm vi tương đối giống nhau:

| Chỉ số | Trước thay đổi | Sau thay đổi thử |
| --- | ---: | ---: |
| Mục hoàn tất | 20 | 21 |
| Trung vị thời gian chờ Review | 2,5 ngày làm việc | 1,5 ngày làm việc |
| Trung vị cycle time đến Done | 7 ngày | 5,5 ngày |
| Mục bị mở lại vì lỗi review/kiểm thử | 3 | 3 |
| Lỗi nghiêm trọng sau release | 0 trong mẫu quan sát | 0 trong mẫu quan sát |

**Tất cả số liệu chỉ để minh họa.** Chúng cho thấy dấu hiệu có thể tích cực: thời gian chờ và cycle time giảm trong khi số mục bị mở lại không tăng. Nhưng mẫu nhỏ, không thể kết luận có ý nghĩa thống kê hay chắc chắn do chính sách mới tạo ra.

Nhóm cần hỏi:

- Hai giai đoạn có loại việc và độ khó tương tự không?
- DoD, cách đánh dấu trạng thái và cỡ story có thay đổi không?
- Có thành viên mới hoặc sự cố lớn ảnh hưởng một giai đoạn không?
- Lỗi production có đủ thời gian xuất hiện và được ghi nhận chưa?
- Người review có bị quá tải hoặc giảm chất lượng trao đổi không?

**Số đo hỗ trợ đối thoại và điều chỉnh**, không tự đưa ra quyết định.

### 17.2. Quy tắc đánh giá thay đổi phương pháp

Đừng coi một cải tiến là thành công nếu:

- “Giảm họp” nhưng thông tin sai và phụ thuộc tăng.
- “Tăng throughput” bằng cách chia task hoặc hạ DoD.
- “Giảm thời gian phát hành” nhưng vi phạm an toàn hoặc sự cố tăng.
- “Tăng velocity” bằng cách thay đổi thang points.
- “Giữ deadline” bằng cách giấu rủi ro hoặc làm thêm giờ không bền vững.

Hãy đánh giá **giá trị, chất lượng, luồng công việc và mức độ bền vững cùng nhau**.

## 18. Một quy trình thử nghiệm tailoring từ đầu tới cuối

Thay đổi cách tiếp cận nên được xử lý như một **giả thuyết cải tiến hệ thống**, không như quyết định niềm tin không thể xem lại.

### Bước 1 — Mô tả bối cảnh

Ghi ngắn: nhóm phục vụ ai, loại việc nào chiếm phần lớn, có phụ thuộc lớn gì, mức rủi ro và yêu cầu chất lượng nào, nguồn lực và khả năng tự quản hiện tại ra sao.

### Bước 2 — Xác định vấn đề quan sát được

Ví dụ: “Nửa số thay đổi đã viết xong phải chờ review quá ba ngày; nhiều story chưa thể đạt Done trong Sprint.” Vấn đề cụ thể hơn “Scrum không hiệu quả” hoặc “chúng ta cần Kanban”.

### Bước 3 — Phân loại điều định thay

Đối chiếu với ba lớp:

- **Cốt lõi của framework/method đã chọn**.
- **Nghĩa vụ và chuẩn an toàn bắt buộc**.
- **Chính sách/công cụ/thực hành có thể thay**.

Nếu muốn thay phần cốt lõi của một framework, lựa chọn rõ ràng là **đổi mô hình hoặc công khai dùng một số thực hành**, không âm thầm gọi như cũ.

### Bước 4 — Viết giả thuyết và dự báo hệ quả

> “Nếu chúng ta giảm WIP ở Review và yêu cầu PR mô tả tiêu chí kiểm chứng, thời gian chờ Review sẽ giảm; số lỗi sau merge không tăng. Rủi ro là người review chuyên môn bị quá tải hoặc công việc khẩn không có kênh riêng.”

### Bước 5 — Chọn phạm vi và thời điểm đánh giá

Có thể thử hai tuần, hai Sprint hoặc đủ một số lượng mục đại diện, tùy tốc độ dòng công việc. Đừng ấn định một khoảng ngắn đến mức không đủ dữ liệu rồi tuyên bố thành công.

### Bước 6 — Giữ các guardrails

Quy định trước những điều **không được hy sinh**: DoD, bảo mật, quyền truy cập, trách nhiệm, chất lượng và các nghĩa vụ áp dụng.

### Bước 7 — Thực hiện, quan sát và xử lý ngoại lệ

Giữ thông tin công việc và rủi ro minh bạch. Khi có sự cố nghiêm trọng, ưu tiên xử lý theo chính sách đã thống nhất; đừng để thí nghiệm quy trình cản phản ứng an toàn.

### Bước 8 — Đánh giá, quyết định và cập nhật working agreement

Chọn một trong các quyết định:

- **Giữ:** có bằng chứng phù hợp và không phá guardrails.
- **Điều chỉnh:** tín hiệu tốt nhưng còn điểm nghẽn hoặc tác dụng phụ.
- **Hoàn tác:** rủi ro tăng hoặc cơ chế thiết yếu bị mất.
- **Thử thêm:** dữ liệu chưa đủ, cần phạm vi hoặc thời gian quan sát khác.

Ghi lại **điều đã học**, không chỉ kết quả “được/không được”.

## 19. Mẫu hồ sơ tailoring có thể sử dụng ngay

~~~text
TÊN THAY ĐỔI:
  Tên ngắn mô tả chính sách hoặc thực hành được điều chỉnh.

BỐI CẢNH VÀ VẤN ĐỀ:
  Người dùng/sản phẩm, loại việc, điểm nghẽn và dữ liệu hiện có.

CÁCH TIẾP CẬN ĐANG DÙNG:
  Scrum đầy đủ, Kanban, XP practices, Lean hay mô hình kết hợp?
  Những thành phần chính thức nào đang được giữ?

PHẦN NỀN TẢNG KHÔNG ĐƯỢC MẤT:
  Giá trị, phản hồi, trách nhiệm, chất lượng, an toàn, nghĩa vụ.

ĐIỀU MUỐN ĐỔI:
  Bỏ/thay/giữ thực hành nào; chính sách mới ra sao?

GIẢ THUYẾT:
  Vì sao thay đổi này được kỳ vọng cải thiện vấn đề?

RỦI RO VÀ ĐÁNH ĐỔI:
  Điều gì có thể xấu đi, ai bị ảnh hưởng, cơ chế xử lý?

QUYẾT ĐỊNH VÀ THẨM QUYỀN:
  Ai đồng ý thử; ai chịu trách nhiệm thực hiện và theo dõi?

DỮ LIỆU NỀN:
  Những số đo có định nghĩa nhất quán trước khi đổi.

PHẠM VI VÀ THỜI ĐIỂM XEM LẠI:
  Nhóm/luồng/lát công việc thử; khi nào và với dữ liệu gì?

TIÊU CHÍ GIỮ / SỬA / HOÀN TÁC:
  Chỉ số giá trị, flow, chất lượng và điều kiện không được vi phạm.

KẾT QUẢ:
  Điều đã quan sát, điều chưa biết và quyết định tiếp theo.
~~~

Một nhóm nhỏ có thể ghi mẫu này trong vài đoạn ngắn. Mục đích là bảo vệ **lý do và chất lượng quyết định**, không phải tạo hồ sơ hành chính cho mọi chỉnh sửa nhỏ.

## 20. Workshop thực hành: kiểm tra cách làm hiện tại

Một buổi workshop chung giữa người phụ trách giá trị, Developers, Scrum Master/người hỗ trợ luồng và các bên có ràng buộc liên quan có thể gồm các hoạt động sau. Thời lượng tùy nhóm, không nhất thiết cần một cuộc họp dài.

### Hoạt động 1 — Vẽ luồng giá trị hiện tại

Từ nhu cầu → làm rõ → phát triển → review → kiểm thử → Done → release → phản hồi. Đánh dấu:

- Các điểm chờ dài.
- Công việc đang dở nhiều.
- Bàn giao mất ngữ cảnh.
- Lỗi hoặc việc làm lại phát hiện muộn.
- Các quyết định chưa rõ người có quyền.

### Hoạt động 2 — Gắn nhãn từng thành phần

Dùng ký hiệu:

- **F – Framework core:** phần chính thức của framework đang tuyên bố sử dụng.
- **S – Safety/obligation:** yêu cầu an toàn, chất lượng, nghĩa vụ.
- **P – Practice/policy:** thực hành/chính sách có thể thử thay.
- **T – Tool:** công cụ hoặc biểu mẫu.

Ví dụ: Sprint Review là **F** nếu đang dùng Scrum đầy đủ; kiểm thử phân quyền bắt buộc là **S**; WIP limit 3 là **P**; Jira là **T**.

### Hoạt động 3 — Chọn một vấn đề, không sửa mọi thứ cùng lúc

Ưu tiên theo **tác động tới giá trị/rủi ro** và **khả năng thử trong phạm vi nhỏ**. Đừng biến workshop thành việc chọn tên framework mới vì nó đang thịnh hành.

### Hoạt động 4 — Thống nhất điều giữ và điều thử

Viết một phát biểu:

> “Chúng ta giữ **mục tiêu sản phẩm, người quyết định ưu tiên, DoD, phản hồi và quyền xử lý sự cố**. Chúng ta thử **giới hạn WIP và review theo nhóm** để giảm thời gian chờ, xem lại sau hai tuần với dữ liệu phù hợp.”

### Hoạt động 5 — Thỏa thuận tín hiệu và cách xem lại

Chọn không quá nhiều số đo, có người phụ trách, cách thu và thời điểm kiểm tra. Ghi lại rủi ro quan trọng và điều kiện sẽ dừng thử nghiệm.

## 21. Những sai lầm thường gặp khi điều chỉnh phương pháp

| Anti-pattern | Vì sao sai hoặc rủi ro | Hướng xử lý |
| --- | --- | --- |
| **“Chúng ta Agile nên không cần quy tắc nào.”** | Không rõ ưu tiên, chất lượng, quyết định, phản hồi. | Giữ cơ chế thiết yếu; thay thực hành theo mục đích. |
| **“Bỏ Scrum Review nhưng vẫn nói tuân thủ Scrum đầy đủ.”** | Loại bỏ một sự kiện của framework và mất cơ chế thích ứng. | Giữ Review đúng mục đích hoặc mô tả mô hình khác trung thực. |
| **“Có bảng Kanban là đã làm Kanban.”** | Không kiểm soát WIP, đo flow hoặc cải tiến. | Xây Definition of Workflow và chính sách quản lý luồng. |
| **“TDD không hợp vì cần đi nhanh, bỏ mọi kiểm thử.”** | Rủi ro hồi quy tăng và khả năng thay đổi suy giảm. | Tìm lưới kiểm chứng phù hợp; đầu tư tự động hóa theo rủi ro. |
| **“Tổ chức mình đặc biệt nên không cần người quyết định backlog.”** | Yêu cầu xung đột, mọi người tối ưu cục bộ. | Đặt trách nhiệm ưu tiên rõ theo mô hình đã chọn. |
| **“Tailoring nghĩa là gom tất cả ceremony của mọi framework.”** | Trùng lặp, tăng họp và báo cáo không phục vụ quyết định. | Chỉ giữ thực hành có chức năng rõ và không xung đột. |
| **“Đặt WIP limit nhưng sự cố nào cũng được coi là expedite.”** | WIP mất kiểm soát và công việc dài hạn luôn bị ngắt. | Nêu tiêu chí khẩn, quyền xác nhận và xem lại ngoại lệ. |
| **“Ít họp hơn luôn có nghĩa nhanh hơn.”** | Có thể làm phản hồi chậm, mất thông tin, tăng làm lại. | Đo giá trị cuộc họp và hiệu ứng lên luồng, không chỉ số phút. |
| **“Dùng story points để so năng suất của các nhóm.”** | Quy ước điểm khác nhau và không đo giá trị. | Dùng số đo theo mục đích, có bối cảnh và chất lượng. |
| **“Quy định bên ngoài là lãng phí, cứ bỏ.”** | Vi phạm nghĩa vụ hoặc gây hại. | Cải tiến cách tuân thủ, không xóa điều kiện cần thiết. |
| **“Một quy trình thành công nơi khác phải dùng y hệt.”** | Bối cảnh khác loại việc, rủi ro, năng lực và phụ thuộc. | Xác định cơ chế cốt lõi, thử với dữ liệu của nhóm mình. |
| **“Đổi framework mỗi khi Sprint khó khăn.”** | Không giải quyết nguyên nhân gốc và tạo mệt mỏi thay đổi. | Chẩn đoán flow, quyền quyết định, chất lượng và điều kiện trước. |
| **“Công việc đã release là tự động tạo giá trị.”** | Output không đồng nghĩa outcome. | Thu phản hồi, đo hành vi người dùng và điều chỉnh. |
| **“Chỉ số tăng là bằng chứng tailoring đúng.”** | Có thể đã đổi cách đo hoặc hạ DoD. | Kiểm tra dữ liệu, phân bố, tác dụng phụ và các guardrails. |
| **“Không được đổi gì vì phải theo sách.”** | Giữ cả nghi thức/công cụ không còn hữu ích. | Phân biệt framework core với những lựa chọn triển khai có thể cải tiến. |

## 22. Bài tập tình huống: giữ phần nào, thay phần nào?

Bạn tham gia nhóm phát triển hệ thống **đặt lịch học trực tuyến**. Tổ chức muốn “linh hoạt hơn” vì nhiều sự cố phát sinh.

**Thông tin cho trước:**

- Nhóm đang tuyên bố sử dụng Scrum đầy đủ, Sprint dài hai tuần.
- Có PO, SM và Developers đa chuyên môn.
- Product Goal: giảm trường hợp học viên bỏ lỡ buổi học vì thông tin lịch sai hoặc không kịp cập nhật.
- Có Product Backlog, Sprint Goal và DoD gồm kiểm thử phân quyền, không đặt lịch trùng, kiểm tra dữ liệu thời gian.
- Daily Scrum hiện thành cuộc họp 35 phút để mọi người báo cáo cho cấp quản lý.
- Sprint Review chủ yếu là demo chưa có người dùng thử, ít thảo luận kết quả.
- Bảng có 15 story đang làm, nhưng chỉ hai story Done trong tuần trước.
- PR thường chờ review hai hoặc ba ngày.
- Có sự cố lịch học bị hiển thị sai múi giờ.
- Ban quản lý đề xuất: **bỏ Retrospective, bỏ kiểm thử đồng thời, bỏ Sprint Goal, chuyển toàn bộ sang “Kanban” chỉ bằng đổi tên bảng**, nhưng vẫn báo là Scrum cho khách hàng.

### Nhiệm vụ

1. Phân loại từng đề xuất thành **thay đổi thực hành**, **đụng thành phần Scrum cốt lõi**, hay **vi phạm điều kiện chất lượng/rủi ro**.
2. Nêu ít nhất năm cơ chế nền tảng nhóm phải giữ bất kể chọn Scrum hay Kanban.
3. Đề xuất phương án **A: vẫn dùng Scrum đầy đủ** nhưng cải thiện ba vấn đề lớn nhất.
4. Đề xuất phương án **B: chuyển hẳn sang Kanban**; cần thêm chính sách và cấu trúc ra quyết định nào để cách làm mới không chỉ là một bảng?
5. Xác định cách xử lý sự cố **múi giờ** mà không hạ tiêu chuẩn Done hoặc bỏ quyền truy cập.
6. Đề xuất một lát dọc có giá trị cho người học/giảng viên và hai ví dụ acceptance criteria.
7. Chọn hai số đo flow, một số đo chất lượng và một tín hiệu giá trị sản phẩm.
8. Viết một quyết định tailoring ngắn: **vấn đề → thay đổi → điều giữ → rủi ro → cách xem lại**.
9. Nếu dữ liệu cho thấy cycle time giảm nhưng số lỗi đặt lịch trùng tăng, quyết định tiếp theo nên là gì?
10. Giải thích vì sao cách làm hiệu quả thực tế **không nhất thiết phải mang tên Scrum** nếu nhóm đã chọn bỏ một số cấu trúc của Scrum.

### Gợi ý hướng giải

**Phân loại:**

- **Đổi cách tổ chức Daily Scrum** từ báo cáo cấp quản lý sang kiểm tra Sprint Goal trong timebox 15 phút: thay đổi **cách thực hiện hợp lý**.
- **Bỏ Sprint Retrospective hoặc Sprint Goal** nhưng vẫn tuyên bố Scrum đầy đủ: bỏ **phần cốt lõi framework**, không mô tả trung thực.
- **Bỏ kiểm thử xử lý đặt lịch đồng thời** trong khi vẫn có rủi ro trùng lịch: đụng **điều kiện chất lượng cần thiết**, không nên chấp nhận.
- **Đổi tên bảng thành Kanban** mà không có Definition of Workflow, WIP, chính sách và số đo: không đủ để sử dụng Kanban hiệu quả.

**Năm cơ chế nên giữ:** giá trị người dùng và ưu tiên rõ; minh bạch WIP/blocked; kiểm tra/thích ứng thường xuyên; chất lượng và quyền truy cập; cơ chế xử lý sự cố; dự báo trung thực; cải tiến bền vững.

**Phương án A — Scrum đầy đủ:**

1. Giữ Product Goal, Sprint Goal, DoD, accountabilities, events và artifacts.
2. Developers dùng Daily Scrum 15 phút để kiểm tra tiến độ hướng Sprint Goal; không báo cáo cá nhân cho quản lý.
3. Áp dụng WIP limit thí điểm, ưu tiên các mục đang Review/Verify.
4. Cải thiện Sprint Review bằng demo kết quả thực và phản hồi từ học viên/giảng viên.
5. Trong Retrospective, điều tra vì sao PR chờ lâu và thử chính sách review mới.

**Phương án B — Kanban:**

1. Công bố thay đổi mô hình, không gọi Scrum đầy đủ khi đã bỏ Sprint/events cốt lõi.
2. Xác định loại việc, điểm bắt đầu và Done, các trạng thái luồng và WIP control.
3. Đặt chính sách tiếp nhận và xác nhận công việc khẩn, ưu tiên giá trị và nghĩa vụ.
4. Theo dõi cycle time, work item age, throughput và blocked time.
5. Tổ chức nhịp kiểm tra sản phẩm, cải tiến quy trình và phản hồi người dùng phù hợp.
6. Giữ người chịu trách nhiệm giá trị và các thẩm quyền chất lượng/triển khai rõ.

**Sự cố múi giờ:** Phân loại mức nghiêm trọng; điều tra lưu trữ, định dạng và quy tắc hiển thị thời gian; bảo vệ dữ liệu; sửa với kiểm thử múi giờ và trường hợp đổi ngày; mở cho người dùng theo điều kiện an toàn, không chờ nghi thức không cần thiết.

**Lát dọc minh họa:**

> “Là học viên, tôi muốn thấy giờ bắt đầu buổi học theo múi giờ được hiển thị rõ, để tham gia đúng giờ.”

~~~gherkin
Feature: Hiển thị lịch học rõ múi giờ

Scenario: Hiển thị thời điểm theo múi giờ đã chọn
  Given học viên có quyền xem một buổi học với thời điểm bắt đầu đã được lưu hợp lệ
  And học viên chọn một múi giờ được hỗ trợ
  When học viên mở lịch buổi học
  Then hệ thống hiển thị thời gian tương ứng với múi giờ đã chọn
  And nhãn múi giờ được hiển thị rõ

Scenario: Không có quyền truy cập lịch lớp khác
  Given học viên không có quyền xem lịch của lớp "B"
  When học viên yêu cầu xem lịch của lớp "B"
  Then hệ thống từ chối theo chính sách
  And không tiết lộ dữ liệu lịch học riêng tư
~~~

**Số đo:** Trung vị cycle time, work item age hoặc blocked time; số sự cố lịch học sai thời gian sau phát hành; tỷ lệ học viên tham gia đúng giờ theo phương pháp đo phù hợp và có bối cảnh.

**Quyết định tailoring minh họa:** “Thử giới hạn WIP trong Review và thay đổi cách tiến hành Daily Scrum; giữ Sprint Goal, DoD và các sự kiện Scrum. Theo dõi cycle time, lỗi múi giờ và phản hồi nhóm sau hai Sprint. Nếu lỗi tăng hoặc phản hồi chậm, đánh giá lại chính sách trước khi mở rộng.”

**Đọc kết quả:** Cycle time giảm mà lỗi đặt trùng tăng không phải thành công. Cần dừng hoặc điều chỉnh chính sách gây hại, xem xét kiểm thử/DoD và quan sát toàn luồng trước khi kết luận.

## 23. Tự kiểm tra kiến thức

**Câu 1.** Agile có bắt buộc mọi nhóm dùng Scrum, Kanban hay story points không?

**Đáp án:** Không. Agile là hệ giá trị và nguyên tắc. Các framework, phương pháp và kỹ thuật cụ thể là những cách hiện thực hóa; cần chọn theo bối cảnh và giữ cơ chế tạo giá trị, phản hồi, chất lượng, cải tiến.

**Câu 2.** Tổ chức bỏ Sprint Review nhưng vẫn gọi Scrum đầy đủ. Có chính xác không?

**Đáp án:** Không theo Scrum Guide. Sprint Review là một sự kiện của framework; có thể chọn mô hình khác nhưng nên mô tả trung thực. Nếu muốn tiếp tục Scrum, hãy cải thiện mục đích và cách thực hiện Sprint Review thay vì bỏ.

**Câu 3.** Có thể thay cách Daily Scrum được tổ chức mà không bỏ Scrum không?

**Đáp án:** Có. Có thể đổi định dạng theo nhu cầu Developers, nhưng cần giữ mục đích kiểm tra tiến độ tới Sprint Goal và thích ứng kế hoạch, trong timebox và nhịp Scrum phù hợp.

**Câu 4.** Scrum có bắt buộc ước lượng bằng story points không?

**Đáp án:** Không. Nhóm có thể dùng kỹ thuật khác hỗ trợ dự báo và lập kế hoạch, miễn là ra quyết định minh bạch và có cơ sở.

**Câu 5.** Một bảng có ba cột To Do/Doing/Done nhưng không kiểm soát WIP, không có chính sách hay số đo. Đã đủ để quản lý Kanban hiệu quả chưa?

**Đáp án:** Chưa. Cần xác định luồng công việc, kiểm soát WIP, chính sách rõ, theo dõi flow và cải tiến dựa trên dữ liệu.

**Câu 6.** Khi chọn Kanban thay Scrum, có thể bỏ luôn mục tiêu sản phẩm và người quyết định ưu tiên không?

**Đáp án:** Không nên. Kanban linh hoạt về cấu trúc vai trò/nhịp thời gian nhưng việc chọn giá trị, xử lý xung đột ưu tiên và phản hồi vẫn cần được giải quyết.

**Câu 7.** Vì sao không thể lấy “Agile coi trọng phần mềm hoạt động” để bỏ kiểm thử bảo mật bắt buộc?

**Đáp án:** Vì ưu tiên giá trị không bỏ quyền riêng tư, an toàn hay nghĩa vụ. Có thể cải tiến cách kiểm chứng và thu bằng chứng, không xóa điều kiện cần thiết để phần mềm sử dụng an toàn.

**Câu 8.** Một nhóm dùng Scrum với WIP limit và TDD. Nhóm có bắt buộc đổi tên thành Scrumban không?

**Đáp án:** Không. Scrum có thể được bổ sung các kỹ thuật Kanban và XP mà vẫn là Scrum nếu cấu trúc Scrum được giữ. Tên gọi nên mô tả đúng những gì nhóm thực sự thực hiện.

**Câu 9.** Khi thay một thực hành, vì sao phải mô tả chức năng nó từng phục vụ?

**Đáp án:** Để tránh vô tình bỏ mất phản hồi, minh bạch, chất lượng hoặc quyền quyết định. Một thực hành có thể được thay bằng cách tốt hơn, nhưng nhu cầu mà nó đáp ứng vẫn có thể tồn tại.

**Câu 10.** Nếu giảm họp giúp Developers có thêm thời gian code nhưng WIP và lỗi tích hợp tăng, tailoring đã thành công chưa?

**Đáp án:** Chưa có cơ sở. Cần đánh giá tác động toàn hệ thống, giữ guardrails và điều chỉnh hoặc hoàn tác nếu kết quả xấu đi.

**Câu 11.** Một nhóm vừa xử lý incident vừa phát triển tính năng. Cách tiếp cận tốt nhất có luôn là Scrum không?

**Đáp án:** Không có đáp án chung. Cần xem loại việc, độ bất định, khả năng hình thành Sprint Goal, mức gián đoạn, chất lượng và cơ chế ưu tiên; Kanban hoặc mô hình bổ trợ có thể phù hợp hơn.

**Câu 12.** Nếu cần chọn một thực hành để thử thay đổi, làm sao tránh cải tiến theo cảm tính?

**Đáp án:** Mô tả vấn đề và dữ liệu nền, phân loại phần cốt lõi/điều kiện bắt buộc/thực hành tùy chọn, nêu giả thuyết, giới hạn thử nghiệm, số đo, rủi ro và mốc xem lại.

## 24. Checklist quyết định điều chỉnh một cách tiếp cận

### Mục tiêu và bối cảnh

- [ ] Chúng ta biết **người dùng hoặc kết quả sản phẩm** nào cần cải thiện.
- [ ] Vấn đề đang gặp được diễn đạt thành hiện tượng quan sát được, không chỉ là cảm giác ghét một phương pháp.
- [ ] Đã xét loại công việc, mức biến động, phụ thuộc và năng lực thực tế của nhóm.
- [ ] Có thông tin về nghĩa vụ, rủi ro và điều kiện tổ chức.

### Phân định phần giữ và phần đổi

- [ ] Đã tách **framework core**, **điều kiện an toàn**, **thực hành/chính sách** và **công cụ**.
- [ ] Nếu vẫn tuyên bố dùng Scrum đầy đủ, những phần được Scrum định nghĩa vẫn được giữ.
- [ ] Nếu chọn Kanban, đã xác định luồng, WIP control, chính sách và số đo/nhịp cải tiến.
- [ ] Các cơ chế phản hồi, chất lượng, ưu tiên và quyền quyết định vẫn rõ.
- [ ] Không bỏ trách nhiệm hoặc nghĩa vụ chỉ vì đổi tên phương pháp.
- [ ] Cách làm được mô tả trung thực, không lấy danh xưng làm mục tiêu.

### Thử nghiệm và đánh giá

- [ ] Có giả thuyết rõ về tác động mong đợi.
- [ ] Có giới hạn phạm vi, thời điểm xem lại và người theo dõi.
- [ ] Có dữ liệu nền hoặc ít nhất biết giới hạn dữ liệu hiện có.
- [ ] Chọn số đo về flow, chất lượng, phản hồi và giá trị phù hợp.
- [ ] Có điều kiện dừng/hoàn tác khi an toàn hoặc chất lượng bị ảnh hưởng.
- [ ] Kết quả được bàn với những người thực hiện và người chịu trách nhiệm liên quan.

Checklist không phải một biểu mẫu phải ký đủ trước mọi thay đổi nhỏ. Nó là cách nhắc nhóm **giữ mục đích và khả năng học hỏi** trong khi đơn giản hóa quy trình.

## 25. Những điều cần ghi nhớ

- **Tailoring không phải bỏ tùy ý.** Hãy hiểu chức năng của mỗi thành phần rồi mới quyết định giữ, cải tiến, thay thế hoặc chọn cách tiếp cận khác.
- **Phân biệt giá trị, nguyên tắc, framework, phương pháp, thực hành, chính sách và công cụ.** Không nên biến công cụ hay nghi thức tùy chọn thành tiêu chí duy nhất của Agile.
- **Bảo vệ giá trị người dùng, phản hồi sớm, minh bạch, chất lượng, quyền quyết định và cải tiến liên tục** dù cách tổ chức công việc có thay đổi.
- **Scrum có cấu trúc được định nghĩa rõ**: ba accountabilities, năm events, ba artifacts cùng commitments. Có thể bổ sung kỹ thuật hoặc đổi cách thực hiện trong ranh giới framework; nếu bỏ phần cốt lõi thì mô tả cách làm khác cho trung thực.
- **Kanban không chỉ là bảng cột.** Cần định nghĩa và quản lý flow, kiểm soát WIP, chính sách rõ, quan sát và cải tiến dựa trên dữ liệu.
- **XP cung cấp nền tảng kỹ thuật giúp thích ứng đáng tin** như kiểm thử, CI, refactoring và cộng tác; không nên giữ khẩu hiệu “nhanh” mà loại bỏ lưới an toàn.
- **Lean nhìn dòng giá trị đầu cuối**, không chỉ đếm số cuộc họp hoặc số task; giảm hàng chờ và làm lại phải đi cùng chất lượng.
- **Cách làm lai có thể hữu ích** nếu các phần bổ sung không tạo quyết định mâu thuẫn hoặc thủ tục trùng lặp.
- **Nghĩa vụ bảo mật, dữ liệu, hợp đồng và chất lượng** phải được giữ; có thể cải tiến cách thực hiện chứ không tự ý xóa.
- **Dùng dữ liệu phục vụ quyết định**, không dùng story points, velocity, throughput hoặc số commit để xếp hạng cá nhân.
- **Mọi thử nghiệm tailoring nên có giả thuyết, guardrails, số đo, mốc xem lại và quyền hoàn tác.** Điều chưa chắc chắn cần được nói rõ.
- **Tên phương pháp không quan trọng bằng kết quả và tính trung thực**, nhưng nếu tuyên bố dùng một framework có định nghĩa, cần tôn trọng định nghĩa ấy.

Một nhóm trưởng thành không cố giữ mọi thói quen cũ, cũng không bỏ tất cả kỷ luật chỉ để tự nhận “linh hoạt”. Nhóm biết **vì sao một cơ chế tồn tại, giá trị và rủi ro nào nó bảo vệ, điều gì có thể đổi và bằng chứng nào cho thấy cách mới tốt hơn**. Chính khả năng giữ phần nền tảng trong khi điều chỉnh phần thích hợp giúp phát triển phần mềm theo tinh thần Agile: **giao giá trị tăng dần, nhận phản hồi sớm, bảo đảm chất lượng và cải tiến liên tục**.
