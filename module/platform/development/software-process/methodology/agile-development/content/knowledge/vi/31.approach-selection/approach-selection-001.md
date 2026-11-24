# Đánh giá mức bất định về nhu cầu và giải pháp

## 1. Trước khi chọn cách phát triển, hãy hỏi điều gì chưa được biết

Một nền tảng học trực tuyến nhận được yêu cầu: **“Hãy xây hệ thống gợi ý bài học bằng AI để học viên quay lại học nhiều hơn.”** Một nhà quản lý cho rằng cách làm là viết tài liệu yêu cầu đầy đủ rồi giao đội kỹ thuật thực hiện trong ba tháng. Một Developer muốn thử mô hình gợi ý ngay. Product Owner băn khoăn: có thể học viên bỏ dở đơn giản vì **không tìm được bài tiếp theo**, chứ không phải vì thiếu gợi ý thông minh.

Ở đây có **hai sự bất định khác nhau**:

1. **Bất định về nhu cầu:** Học viên có thật sự cần một hệ thống gợi ý không? Vấn đề nào khiến họ bỏ dở? Ai gặp vấn đề, thường xuyên tới đâu, kết quả nào có giá trị?
2. **Bất định về giải pháp:** Nếu đã hiểu nhu cầu, có thể tạo một giải pháp hoạt động đúng, đủ nhanh, an toàn dữ liệu, tương thích hệ thống và vận hành được không?

Nếu chưa biết **mình đang giải quyết đúng vấn đề hay không** mà đầu tư lớn vào công nghệ, nhóm có nguy cơ giao rất tốt **một thứ ít người cần**. Ngược lại, nếu nhu cầu đã được xác nhận nhưng kỹ thuật đồng bộ tiến độ có rủi ro mất dữ liệu, một cuộc phỏng vấn người học bổ sung **không tự giải quyết** vấn đề nhất quán dữ liệu.

**Đánh giá mức bất định về nhu cầu và giải pháp** là quá trình làm rõ **những giả định chưa được kiểm chứng**, mức độ ảnh hưởng nếu chúng sai, bằng chứng hiện có và **cách học rẻ, nhanh, an toàn nhất** trước khi cam kết giải pháp hoặc cách tổ chức delivery.

Trong module **AGILE_DEVELOPMENT**, mục tiêu là dùng các giá trị Agile để học qua phản hồi sớm, giao phần mềm tăng dần và liên tục cải tiến. User story, Product Backlog, Scrum, Kanban, XP, discovery, kiểm thử và các phép đo flow đều có ích, nhưng **không nên chọn thực hành chỉ vì tên framework**.

> **Nguyên tắc chính:** Chọn cách tiếp cận theo **loại bất định cần giảm và hậu quả nếu đoán sai**. Không mặc định mọi công việc đều cần Sprint, mọi vấn đề đều cần prototype, hay mọi giải pháp kỹ thuật đều phải thiết kế đầy đủ từ đầu.

## 2. Phân biệt những khái niệm dễ bị dùng lẫn

**Bất định (uncertainty)** là khi thông tin hiện có chưa đủ để dự đoán hoặc quyết định một cách đáng tin trong phạm vi đang xét. Nó không đồng nghĩa với sự thiếu trách nhiệm, cũng không có nghĩa nhóm phải tìm cách xóa mọi điều chưa biết trước khi bắt đầu.

| Khái niệm | Câu hỏi điển hình | Ví dụ |
| --- | --- | --- |
| **Bất định về nhu cầu** | Người dùng có vấn đề này không; vấn đề quan trọng đến đâu? | Học viên bỏ học vì quên bài tiếp theo hay vì nội dung quá khó? |
| **Bất định về giải pháp** | Cách làm nào hoạt động, có khả thi và an toàn? | Cache tiến độ có đồng bộ đúng giữa điện thoại và web không? |
| **Mơ hồ (ambiguity)** | Các bên có hiểu cùng một khái niệm/quy tắc không? | “Đã ghi danh” là PENDING hay ACTIVE? |
| **Biến động (volatility)** | Nhu cầu, luật, thị trường hoặc hệ thống có thay đổi thường xuyên không? | Chính sách duyệt khóa thay đổi theo chương trình học |
| **Phức tạp (complexity)** | Có nhiều tương tác khiến hành vi khó dự đoán không? | Identity, Progress, Enrollment và Cache tác động lẫn nhau |
| **Rủi ro (risk)** | Nếu giả định sai, tác động bất lợi và khả năng xảy ra ra sao? | Mở sai bài là bất tiện; cấp quyền trái phép có thể nghiêm trọng |
| **Phụ thuộc (dependency)** | Kết quả có cần hành động/quyết định của bên khác không? | Chờ đối tác xác nhận hợp đồng API |
| **Giới hạn bắt buộc (constraint)** | Điều gì không được vượt, kể cả khi thử nghiệm? | Dữ liệu cá nhân, quyền nội dung, DoD, nghĩa vụ hợp đồng |

### Một điều chưa biết có thể thuộc nhiều loại

“Liệu học viên PENDING có được xem nội dung thử không?” có thể là **mơ hồ nghiệp vụ** nếu quy tắc chưa được chốt. Nếu quy tắc đã rõ là không được xem, nhưng API chưa chắc chặn đúng, đó là **bất định giải pháp/kỹ thuật**. Nếu tổ chức đang cân nhắc đổi chính sách truy cập, còn có **rủi ro về sản phẩm, quyền dữ liệu và thẩm quyền quyết định**.

### Rủi ro và bất định cần được xử lý khác nhau

Một giả thuyết chưa chắc đúng nhưng **dễ đảo ngược, tác động nhỏ** có thể được thử sớm. Một thay đổi rất ít bất định về kỹ thuật nhưng có thể **làm lộ dữ liệu** vẫn cần kiểm soát chặt. Không được dùng câu “chúng ta đã biết cách code” để kết luận release là an toàn.

### Đừng coi bất định là nhược điểm của nhóm

Việc nói **“chúng tôi chưa biết học viên có thực sự muốn tính năng này”** là thông tin có giá trị. Một nhóm giả vờ biết để bảo vệ kế hoạch có thể khiến tổ chức đầu tư sai nhiều tháng. Mục tiêu là biến điều chưa biết thành **câu hỏi có thể kiểm chứng**.

## 3. Hai trục đánh giá: nhu cầu và giải pháp

Để chọn hướng đi, có thể dùng **ma trận hai trục**:

- **Trục nhu cầu:** mức tin cậy về người dùng, vấn đề, giá trị, bối cảnh và điều kiện chấp nhận.
- **Trục giải pháp:** mức tin cậy về cách thực hiện, khả thi kỹ thuật, tích hợp, dữ liệu, an toàn, vận hành và khả năng mở rộng.

Đây là **công cụ tư duy định tính**, không phải một tiêu chuẩn chính thức chấm điểm Agile. “Cao” và “thấp” luôn phải được giải thích theo bằng chứng và phạm vi.

| Bất định nhu cầu | Bất định giải pháp | Tình huống điển hình | Việc nên học trước |
| --- | --- | --- | --- |
| **Thấp** | **Thấp** | Sửa lỗi hiển thị đã tái hiện, cách sửa đã biết và có test | Giao lát nhỏ, kiểm tra hồi quy và hiệu quả; tránh thủ tục thừa |
| **Cao** | **Thấp** | Có thể làm nút gợi ý nhanh nhưng chưa biết người học có cần | Quan sát người dùng, thử ý tưởng/luồng, đo hành vi |
| **Thấp** | **Cao** | Cần đồng bộ tiến độ đã rõ, nhưng nhất quán đa thiết bị khó | Spike kỹ thuật, test tích hợp, prototype kỹ thuật, giảm rủi ro kiến trúc |
| **Cao** | **Cao** | Gợi ý AI cá nhân hóa chưa xác nhận nhu cầu, dữ liệu và kỹ thuật đều khó | Thử giả định giá trị nhỏ nhất, kiểm tra khả thi và bảo mật song song có giới hạn |

### Sơ đồ đường đi của quyết định

~~~mermaid
flowchart TD
    A["Một cơ hội / yêu cầu / vấn đề"] --> B["Nhu cầu đã được hiểu và có bằng chứng?"]
    B -->|"Chưa"| C["Discovery: quan sát, phỏng vấn, prototype và đo nhu cầu"]
    B -->|"Đủ cho quyết định hiện tại"| D["Giải pháp có bằng chứng khả thi, an toàn?"]
    C --> D
    D -->|"Chưa"| E["Spike, POC, integration/security test, kiểm chứng phụ thuộc"]
    D -->|"Đủ cho lát đầu"| F["Delivery: lát giá trị nhỏ đạt DoD"]
    E --> F
    F --> G["Dùng thực tế, xem outcome và guardrails"]
    G --> H{"Giả thuyết còn phù hợp?"}
    H -->|"Có"| I["Mở rộng/tiếp tục theo dữ liệu"]
    H -->|"Không"| J["Điều chỉnh, thu hẹp hoặc dừng"]
    I --> B
    J --> B
~~~

Sơ đồ **không yêu cầu đi tuần tự qua tất cả ô**. Discovery và delivery có thể diễn ra song song với nhịp phù hợp. Đối với bảo mật hoặc mất dữ liệu đang gây hại, nhóm phải **ứng phó ngay**, không chờ một vòng thử nghiệm sản phẩm.

## 4. Bất định về nhu cầu: không chỉ hỏi “người dùng có thích không?”

Nhu cầu không phải một phiếu bình chọn tính năng. Cần xem **người dùng là ai, họ muốn đạt kết quả gì, vấn đề xảy ra trong ngữ cảnh nào và giá trị của việc giải quyết**.

### Sáu nhóm câu hỏi về nhu cầu

1. **Đúng người dùng?** Người học mới, người học quay lại, giảng viên, quản trị viên hay nhân viên hỗ trợ?
2. **Đúng vấn đề?** Họ khó tìm bài, không có thời gian, thiếu động lực hay không có quyền truy cập?
3. **Tần suất và mức tác động?** Vấn đề xảy ra một lần hay lặp lại, gây bỏ học hay chỉ bất tiện nhẹ?
4. **Hành vi hiện tại?** Người dùng xử lý bằng cách nào, có workaround nào và chi phí của workaround?
5. **Giá trị của thay đổi?** Kết quả nào cải thiện, ai trả chi phí, có rủi ro khiến người dùng khác chịu thiệt?
6. **Quy tắc và điều kiện chấp nhận?** Thế nào là “tiếp tục học thành công”, ai có quyền và trường hợp nào không được phép?

### “Khách hàng yêu cầu” chưa chắc là “người dùng cần”

Một stakeholder có thể yêu cầu dashboard với 20 biểu đồ vì họ thiếu khả năng phát hiện học viên có nguy cơ bỏ học. Nhu cầu thật có thể là **một cảnh báo đáng tin và hành động hỗ trợ đúng lúc**. Nếu chỉ hỏi “cần những biểu đồ nào?” sẽ dễ khóa giải pháp quá sớm.

### Desirability, viability, usability và ethics

Bất định nhu cầu có thể bao gồm:

- **Desirability:** người dùng có muốn kết quả này không?
- **Usability:** họ có hiểu và dùng được giải pháp theo ngữ cảnh thực tế không?
- **Viability:** kết quả có phù hợp mô hình hoạt động, kinh tế, chính sách sản phẩm và mục tiêu tổ chức không?
- **Tác động và công bằng:** tính năng có bỏ qua hoặc gây bất lợi cho nhóm người học nào không?

Một giải pháp nhiều người thấy hấp dẫn có thể **không phù hợp kinh tế**, hoặc tạo tác động không mong muốn lên quyền riêng tư. Vì vậy, **“người dùng thích” không đủ để cam kết phát hành**.

### Nhu cầu có thể đã rõ ở phạm vi nhỏ nhưng chưa rõ ở phạm vi lớn

Nền tảng có thể biết chắc học viên của **khóa tuyến tính** muốn mở bài chưa hoàn thành, nhưng chưa biết tính năng ấy có phù hợp **khóa tự chọn, học ngoại tuyến hoặc lớp theo lịch trực tiếp** không. Đừng tuyên bố nhu cầu đã được xác nhận cho toàn bộ sản phẩm chỉ từ một phân khúc.

## 5. Bất định về giải pháp: khả thi không chỉ nghĩa là “viết được mã”

Sau khi nhu cầu được hiểu, nhóm cần đánh giá khả năng hiện thực hóa kết quả trong **ràng buộc kỹ thuật và vận hành**.

| Khía cạnh | Câu hỏi | Ví dụ kiểm chứng |
| --- | --- | --- |
| **Thuật toán/logic** | Quy tắc có thể thực hiện chính xác ở trường hợp biên? | Unit test chọn bài tiếp theo khi bài đã hoàn tất |
| **Hệ thống tích hợp** | Các dịch vụ có trao đổi đúng hợp đồng? | Contract test giữa Learning và Identity |
| **Dữ liệu** | Dữ liệu có đủ, đúng, cập nhật và nhất quán? | Ghi tiến độ trên mobile, đọc trên web |
| **Concurrency** | Hai yêu cầu đồng thời có tạo trạng thái sai? | Integration test hai request ghi danh |
| **Bảo mật và quyền** | Người không đủ quyền có thể truy cập đường API trực tiếp? | API/security integration test |
| **Hiệu năng/khả dụng** | Luồng đáp ứng được tải và mục tiêu đã chốt? | Load/latency check theo cohort, giám sát |
| **Vận hành** | Có cách phát hiện, rollback, phục hồi và hỗ trợ? | Canary, feature flag, runbook, restore drill |
| **Tính tương thích** | Client hiện tại có bị phá khi thay hợp đồng/schema? | Consumer contract tests, migration plan |
| **Kỹ năng/phụ thuộc** | Nhóm có năng lực, quyền và môi trường để triển khai? | Spike kỹ thuật, trao đổi bên liên quan |
| **Chi phí** | Hạ tầng, license, vận hành có nằm trong hạn mức? | Ước lượng cost với giả định, test tải nhỏ |

### Bằng chứng yếu: “đã từng làm dự án tương tự”

Kinh nghiệm giúp hình thành giả thuyết nhưng không đủ để bảo đảm API ngoài, dữ liệu legacy hoặc tải thực tế của hệ thống mới. Khi hậu quả sai lớn, nên **chứng minh một khả năng nhỏ** trong điều kiện gần với rủi ro cần giải quyết.

### Bằng chứng mạnh hơn: kiểm tra đúng chỗ có thể hỏng

Nếu lo lắng hai thiết bị đọc tiến độ không nhất quán, một prototype giao diện đẹp không giảm được bất định chính. Một integration test ghi ở thiết bị A rồi đọc ở phiên B, kiểm tra hợp đồng nhất quán và tình huống conflict sẽ có giá trị hơn.

### Công nghệ mới có thể làm tăng cả hai trục bất định

Gợi ý AI có thể chưa được người học mong muốn, đồng thời đặt câu hỏi về dữ liệu huấn luyện, chất lượng gợi ý, chi phí, sai lệch và quyền riêng tư. Việc “thư viện chạy được bản demo” chỉ chứng minh **một phần feasibility**, không chứng minh sản phẩm có giá trị hoặc có thể triển khai an toàn.

## 6. Mơ hồ yêu cầu và bất định nhu cầu không hoàn toàn giống nhau

Đôi khi không cần nghiên cứu thị trường; chỉ cần **người có thẩm quyền xác nhận một quy tắc**.

Ví dụ:

> “Học viên đã ghi danh thì được vào bài.”

Đây là câu chưa đủ rõ: một số khóa ghi danh là **ACTIVE ngay**, số khác cần xét duyệt và ở trạng thái **PENDING**. Nếu hợp đồng nghiệp vụ đã tồn tại, vấn đề là **làm rõ và chia sẻ đúng quy tắc**, không phải tiến hành một thử nghiệm A/B để xem có nên bỏ phân quyền hay không.

### Bốn cách giảm mơ hồ

- Viết các ví dụ chấp nhận (acceptance examples) cho **trường hợp chính, trường hợp từ chối và biên**.
- Dùng **Three Amigos/ATDD**: nghiệp vụ, Developers và góc nhìn kiểm thử cùng xác nhận.
- Dùng **decision table/state machine** cho quyền và trạng thái.
- Ghi **người có quyền chốt, quyết định và điều kiện thay đổi**.

### Bảng quyết định minh họa

| Trạng thái ghi danh | Khóa cần duyệt? | Có quyền mở nội dung hạn chế? | Điều cần giải thích ở UI |
| --- | --- | --- | --- |
| Chưa ghi danh | Có hoặc không | Không, trừ nội dung công khai theo chính sách | Chưa ghi danh |
| PENDING | Có | Không | Đang chờ duyệt |
| ACTIVE | Có hoặc không | Có, nếu đáp ứng các điều kiện khác | Đang học/đã ghi danh |
| REJECTED | Có | Không | Yêu cầu bị từ chối |
| EXPIRED | Theo chính sách | Không nếu quyền đã hết hiệu lực | Cần gia hạn hoặc liên hệ hỗ trợ |

**Bảng chỉ là mô hình học tập**. Mỗi tổ chức cần xác nhận quy tắc thực; không được dùng ví dụ để tự đổi hợp đồng quyền truy cập.

### Phân biệt “không biết quy tắc” với “quy tắc có thể thay đổi”

Nếu quy tắc đã được ban hành nhưng tài liệu thiếu, hãy sửa **nguồn sự thật và luồng làm rõ**. Nếu tổ chức đang cân nhắc thay chính sách, nhu cầu và tính khả thi của thay đổi phải được đánh giá cùng người có thẩm quyền, rủi ro và dữ liệu.

## 7. Những loại bằng chứng giúp đánh giá bất định nhu cầu

Không một nguồn dữ liệu nào phản ánh hoàn hảo nhu cầu. Phỏng vấn có thể giàu ngữ cảnh nhưng mẫu nhỏ; analytics có số lượng lớn hơn nhưng không tự giải thích **vì sao** người dùng hành động như vậy.

| Nguồn | Học được điều gì? | Hạn chế cần nhớ |
| --- | --- | --- |
| **Phỏng vấn theo tình huống thật** | Động cơ, workaround và bối cảnh | Người tham gia nhớ sai hoặc nói điều họ nghĩ mình nên làm |
| **Quan sát thực hiện nhiệm vụ** | Người dùng gặp khó ở bước nào | Kịch bản thử có thể khác thói quen thực |
| **Support tickets** | Những trường hợp gây bức xúc rõ | Chỉ gồm người chủ động báo và cách phân loại của hỗ trợ |
| **Product analytics** | Tần suất, tỷ lệ hoàn thành và đoạn rơi khỏi hành trình | Cần định nghĩa event, mẫu số, cohort và bảo vệ dữ liệu |
| **Khảo sát** | Tín hiệu ưu tiên và cảm nhận trên mẫu rộng hơn | Câu hỏi dẫn dắt, thiên lệch tự chọn, tỷ lệ phản hồi |
| **Usability test** | Người dùng có hiểu một prototype hay không | Prototype chưa chứng minh nhu cầu dài hạn hoặc hành vi thật |
| **Thử nghiệm cohort/pilot** | Hành vi quan sát khi tính năng có thể dùng | Cần guardrails, chọn mẫu và thời gian thích hợp |
| **Bằng chứng thị trường/đối thủ** | Những cách giải quyết khác đang tồn tại | Đối thủ làm chưa chắc người dùng của mình cần |

### Phỏng vấn tốt hỏi về quá khứ cụ thể

Thay vì **“Nếu có AI gợi ý, bạn có dùng không?”**, hãy thử:

- “Lần gần nhất bạn quay lại học sau vài ngày, bạn làm gì trước?”
- “Bạn có nhớ đã học đến đâu không, và đã tìm bài tiếp theo bằng cách nào?”
- “Điều gì làm bạn mất nhiều thời gian nhất?”
- “Bạn đã dùng cách nào để ghi nhớ hoặc lưu vị trí học?”
- “Bạn quyết định dừng hay tiếp tục học vì lý do gì?”

Những câu hỏi này **không tự loại bỏ bias**, nhưng thường ít thúc đẩy người dùng đồng ý với một ý tưởng đã được giới thiệu hơn.

### Đếm lượt click khác đếm người dùng

Một học viên có thể nhấn “Tiếp tục học” năm lần vì ứng dụng không phản hồi. Nếu chỉ đếm số click, có thể tưởng tính năng được yêu thích. Hãy chọn **đơn vị phù hợp**: yêu cầu hợp lệ, học viên duy nhất, lần quay lại học hoặc hành trình hoàn thành.

### Không sử dụng dữ liệu cá nhân ngoài phạm vi cho phép

Thử nghiệm nhu cầu cần tuân thủ chính sách quyền riêng tư, có cơ sở xử lý dữ liệu phù hợp, hạn chế lưu dữ liệu thô và bảo vệ người dùng dễ bị ảnh hưởng. Không sao chép toàn bộ lịch sử học viên lên máy cá nhân chỉ để làm discovery.

## 8. Những cách giảm bất định giải pháp mà chưa cần xây toàn bộ sản phẩm

Nếu một giả định kỹ thuật chưa được chứng minh, nhóm có thể chọn **bằng chứng nhỏ hơn một tính năng production hoàn chỉnh**.

### Phân biệt prototype, spike, proof of concept và Increment

| Hình thức | Câu hỏi chính | Đầu ra và giới hạn |
| --- | --- | --- |
| **Prototype trải nghiệm** | Người dùng có hiểu luồng, từ ngữ, tương tác không? | Mô hình giấy/Figma/UI mô phỏng; thường không chứng minh kỹ thuật vận hành |
| **Technical spike** | Chưa biết điều gì và cần học cách nào? | Kết quả điều tra/thử kỹ thuật có giới hạn thời gian; không mặc định là mã production |
| **Proof of concept (POC)** | Một khả năng kỹ thuật cụ thể có thể hoạt động không? | Chứng minh feasibility một phần, có thể bỏ qua production hardening |
| **Vertical slice** | Các thành phần có phối hợp tạo kết quả nhỏ đúng end-to-end không? | Một lát tích hợp từ UI/API/data với chất lượng phù hợp |
| **Experiment/pilot** | Người dùng hoặc hệ thống có hành vi mong đợi trong phạm vi kiểm soát? | Bằng chứng từ cohort/điều kiện thật, đi kèm guardrails |
| **Increment đạt DoD** | Phần sản phẩm đã đạt chuẩn chất lượng chung và sử dụng được? | Phần sản phẩm được xác minh, không phải demo tùy tiện |

### Spike cần câu hỏi và điểm dừng

Spike tốt:

> “Trong tối đa hai ngày làm việc, kiểm tra liệu cơ chế versioned progress có thể ngăn trả dữ liệu cũ khi hai thiết bị cập nhật gần nhau; kết luận bằng test, trade-off, các rủi ro còn lại và khuyến nghị”.

Spike yếu:

> “Nghiên cứu công nghệ đồng bộ đến khi nào thấy ổn”.

Một spike không nhất thiết tạo mã có thể merge. Nếu đem mã thử nghiệm vào sản phẩm thật, nó **phải được đánh giá, hoàn thiện và đáp ứng DoD/quy định kỹ thuật thích hợp**. Không được gọi kết quả thử kỹ thuật là Increment đã sẵn sàng sử dụng chỉ vì demo chạy.

### Prototype có thể xác nhận usability nhưng chưa xác nhận adoption

Trong usability test, học viên mở đúng bài qua một nút rõ ràng. Điều đó giúp giảm bất định **“người dùng có hiểu UI không?”**. Nó chưa chứng minh người học sẽ quay lại thường xuyên hơn trong đời thực, hoặc giải pháp có thể đồng bộ tốt khi có hàng nghìn thiết bị.

### Thiết kế phép thử để có khả năng thất bại

Một thử nghiệm chỉ ghi **“demo thành công”** khi dữ liệu dễ và người thực hiện đã biết hết thao tác có thể không giảm bất định. Hãy đặt trước **điều kiện thất bại hoặc ranh giới chấp nhận**, chẳng hạn hai request đồng thời vẫn chỉ tạo một enrollment ACTIVE.

## 9. Đánh giá độ mạnh của bằng chứng và độ tin cậy của kết luận

Không phải một bình luận trên chat, một buổi phỏng vấn và một phép thử tích hợp có cùng ý nghĩa. Cần đánh giá **bằng chứng có trả lời đúng câu hỏi không**.

### Một thang thảo luận định tính

| Mức bằng chứng minh họa | Ví dụ | Điều có thể kết luận thận trọng |
| --- | --- | --- |
| **Giả định chưa kiểm tra** | “Có lẽ ai cũng muốn gợi ý AI” | Chỉ đủ để tạo câu hỏi khám phá |
| **Ý kiến và kinh nghiệm** | Hai stakeholder nghĩ học viên cần AI | Có giả thuyết; chưa biết hành vi người học |
| **Quan sát sơ bộ** | Một số học viên kể chuyện tìm bài cũ khó | Có dấu hiệu vấn đề; chưa biết mức độ phổ biến |
| **Kiểm chứng có mục tiêu** | Usability test cho nhiều trường hợp và dữ liệu hành vi rõ | Giảm bất định về tác vụ/luồng đã thử |
| **Pilot có guardrails** | Cohort mục tiêu dùng tính năng thật, thấy outcome và lỗi | Bằng chứng mạnh hơn trong phạm vi pilot |
| **Quan sát lặp lại ở bối cảnh phù hợp** | Hành vi và chất lượng ổn qua nhiều đợt/cohort | Tăng tin cậy, nhưng không bảo đảm mọi bối cảnh tương lai |

Đây **không phải thang đo khoa học cố định**; giá trị phụ thuộc **độ phù hợp**. Một test API nghiêm ngặt là bằng chứng mạnh về phân quyền, nhưng yếu về việc học viên có muốn AI gợi ý không.

### Chất lượng bằng chứng cần kiểm tra

- **Đúng đối tượng?** Mẫu gồm học viên thực tế hay chủ yếu nhân viên nội bộ?
- **Đúng bối cảnh?** Thử trên khóa tuyến tính có đại diện khóa tự chọn?
- **Đúng hành vi?** Người dùng nói thích hay thật sự hoàn thành nhiệm vụ?
- **Đúng môi trường?** POC chạy local hay trong điều kiện tải và dữ liệu tương tự production?
- **Đúng mẫu số?** Có biết ai đủ điều kiện nhưng không sử dụng?
- **Đủ thời gian?** Một tuần đầu có khác mùa khai giảng?
- **Có bằng chứng trái chiều?** Những trường hợp thất bại được ghi như thế nào?

### “Chưa có bằng chứng thất bại” không bằng “đã chứng minh thành công”

Nếu pilot có 10 học viên và không ai gặp lỗi, không thể tuyên bố hệ thống đã loại trừ mọi lỗi hiếm. Nếu một POC chạy với vài bản ghi, không thể suy ra hiệu năng khi có hàng trăm nghìn dữ liệu hoặc khi mạng gián đoạn.

## 10. Chọn mức thẩm định theo tác động và khả năng đảo ngược

**Cao/thấp về bất định** chưa đủ. Cần cân nhắc **mức ảnh hưởng nếu giả định sai**, khả năng phục hồi, chi phí thay đổi và nghĩa vụ bắt buộc.

| Tình huống | Bất định | Tác động nếu sai | Lựa chọn thận trọng |
| --- | --- | --- | --- |
| Đổi nhãn nút “Tiếp tục học” cho cohort nhỏ | Nhu cầu/usability còn chưa rõ | Thấp nếu dễ đảo ngược, không ảnh hưởng quyền | Prototype hoặc pilot có kiểm soát |
| Đồng bộ tiến độ hai thiết bị | Kỹ thuật trung bình/cao | Có thể ghi lùi/mất tiến độ | Integration tests, chiến lược dữ liệu và rollback |
| AI gợi ý dựa trên lịch sử cá nhân | Nhu cầu và giải pháp đều có thể cao | Quyền riêng tư, chất lượng gợi ý, chi phí | Xác nhận vấn đề, dữ liệu và thẩm quyền trước khi mở rộng |
| Thay chính sách PENDING thành có quyền học | Có thể rõ về code nhưng mơ hồ về thẩm quyền | Truy cập trái quyền nội dung | Không tự thử; xác nhận chính sách nghiệp vụ/bảo mật |
| Refactor phương thức private đã có test | Nhu cầu thấp, kỹ thuật thấp | Thấp nếu có hồi quy thích hợp | Làm theo kỹ thuật thông thường; không cần workshop lớn |
| Di chuyển dữ liệu lịch sử khó đảo ngược | Kỹ thuật có thể cao | Mất dữ liệu và vi phạm cam kết | Migration plan, backup/restore, kiểm tra theo quy trình |

### Phân biệt quyết định dễ đảo ngược và khó đảo ngược

Một thử nghiệm giao diện có feature flag và khả năng dừng ngay thường dễ đảo ngược hơn xóa dữ liệu cũ. **Quyết định càng khó đảo ngược, càng cần bằng chứng và cơ chế bảo vệ tương xứng trước khi thực hiện**.

### Guardrails không phải biến để tối ưu

Không được thử giảm kiểm tra quyền ở một nhóm học viên để xem conversion tăng. Có thể thử trải nghiệm khác nhau **trong phạm vi an toàn và được phép**, nhưng quyền truy cập, bảo vệ dữ liệu và Definition of Done không phải thứ đem đánh đổi vì KPI tăng trưởng.

### Escalation khi vượt quyền quyết định

Developers có thể tự chọn cách tổ chức mã và test. Product Owner có accountability về giá trị và Product Backlog. Quy tắc pháp lý/dữ liệu hoặc ngoại lệ an toàn cần **người có thẩm quyền tương ứng**. Không một ma trận 2×2 nào tự cấp thêm quyền cho nhóm.

## 11. Cách đặt câu hỏi thành giả thuyết có thể bác bỏ

Để giảm bất định, nhóm nên diễn đạt **điều mình tin, kết quả dự kiến, cách kiểm tra và điều gì khiến mình đổi quyết định**.

### Mẫu giả thuyết nhu cầu

~~~text
Chúng tôi tin rằng:
  <nhóm người dùng> gặp <vấn đề> trong <ngữ cảnh>.

Nếu cung cấp:
  <lát giải pháp hoặc thay đổi trải nghiệm>,

thì:
  <hành vi/outcome có thể quan sát> sẽ thay đổi.

Bằng chứng hiện có:
  <quan sát thực, số lượng, thời gian, giới hạn>.

Phép thử nhỏ nhất an toàn:
  <prototype/quan sát/pilot>.

Chúng tôi sẽ xem lại nếu:
  <kết quả trái kỳ vọng, tác dụng phụ hoặc giới hạn mẫu>.
~~~

**Ví dụ:** “Học viên khóa tuyến tính đã hoàn tất ít nhất một bài thường mất thời gian tìm bài tiếp theo sau khi quay lại; nút ‘Tiếp tục học’ có thể giúp họ mở đúng bài trong ít bước hơn”.

Đây là giả thuyết có thể kiểm chứng bằng quan sát hành trình, usability test và dữ liệu sử dụng theo cohort. Nó không mặc định AI là giải pháp.

### Mẫu giả thuyết giải pháp

~~~text
Rủi ro kỹ thuật:
  <cơ chế có thể sai hoặc giới hạn chưa rõ>.

Giải pháp ứng viên:
  <thiết kế/thuật toán/cơ chế>.

Chứng cứ cần có:
  <test/POC/benchmark/contract và điều kiện dữ liệu>.

Điều kiện an toàn:
  <bất biến, DoD, dữ liệu, thẩm quyền, phục hồi>.

Điểm dừng:
  <kết quả không đạt sẽ khiến chọn phương án khác>.
~~~

**Ví dụ:** “Phiên bản tiến độ có thể giúp ngăn đọc cache cũ. Một bài test tích hợp ghi trên mobile rồi đọc trên web phải mở đúng bài theo hợp đồng nhất quán; nếu phát hiện ghi lùi hoặc đọc sai, chưa được rollout”.

### Phải phân biệt điều đang đo

Một thử nghiệm có thể **không bác bỏ giả thuyết** vì chưa có đủ mẫu, không phải vì giả thuyết chắc chắn đúng. Nên ghi các trạng thái **được hỗ trợ trong phạm vi**, **bị phản bác**, hoặc **chưa kết luận**, thay vì ép mọi thử nghiệm thành “thành công/thất bại”.

## 12. Đánh giá nhanh bằng bảng giả định – bằng chứng – hành động

Để giảm tranh luận cảm tính, mỗi giả định quan trọng có thể được đặt vào một bảng:

| Giả định | Trục bất định | Bằng chứng hiện có | Tác động nếu sai | Phép thử phù hợp |
| --- | --- | --- | --- | --- |
| Học viên muốn nút mở bài tiếp theo | Nhu cầu | Phản hồi hỗ trợ từ một số học viên | Trung bình | Quan sát hành trình, prototype nhỏ |
| Học viên muốn AI gợi ý khóa mới | Nhu cầu | Ý tưởng của stakeholder, chưa có hành vi | Trung bình/cao vì chi phí và dữ liệu | Phỏng vấn/kiểm tra giá trị trước khi xây mô hình |
| API trả đúng bài từ tiến độ hiện có | Giải pháp | Unit tests cho quy tắc tuyến tính | Trung bình | Vertical slice + integration tests |
| Cache đồng bộ đa thiết bị | Giải pháp | Chưa có test đa phiên | Cao vì dữ liệu tiến độ | Spike và kiểm thử nhất quán dữ liệu |
| PENDING được cấp quyền học | Nghiệp vụ/tuân thủ | Mâu thuẫn với chính sách hiện hành | Cao | Người có thẩm quyền làm rõ; test từ chối quyền |
| Model AI có thể dùng dữ liệu học viên đúng chính sách | Giải pháp/quản trị | Chưa có thẩm định sử dụng dữ liệu | Cao | Thẩm định phạm vi dữ liệu, privacy/security review |

### Bảng ưu tiên không phải bảng bình chọn công nghệ

Hãy ưu tiên **giả định có khả năng làm lựa chọn sai tốn kém hoặc nguy hiểm**, không phải tính năng nghe hấp dẫn nhất. Ví dụ rủi ro cấp sai quyền có thể cần xử lý ngay dù tần suất phản hồi khách hàng thấp.

### Số hóa mức độ tự tin nên rất cẩn trọng

Nhóm có thể dùng thang định tính **Thấp – Trung bình – Cao** hoặc một thang 0–3 để thảo luận. Nhưng **“confidence = 87%”** không có ý nghĩa nếu không có cách ước lượng hoặc dữ liệu phù hợp. Nếu dùng điểm, cần công bố **định nghĩa từng mức và bằng chứng**; không nhầm điểm đánh giá nội bộ với xác suất thống kê.

## 13. Ma trận mức bất định và cách chọn bước tiếp theo

### Ô 1: Nhu cầu rõ, giải pháp rõ

**Ví dụ:** sửa một lỗi căn chỉnh nút đã tái hiện, yêu cầu và cách kiểm thử đều rõ.

Ưu tiên:

- Giao thay đổi nhỏ, tích hợp và kiểm thử hồi quy theo rủi ro.
- Dùng board/workflow đủ minh bạch, không thêm nhiều lớp discovery không cần thiết.
- Xác nhận sửa đúng triệu chứng trong môi trường phù hợp.
- Theo dõi một số guardrail và ảnh hưởng nếu sửa chạm luồng quan trọng.

**Sai lầm:** ép tạo prototype, tổ chức workshop giả thuyết nhiều tuần chỉ để sửa một lỗi đã hiểu rõ.

### Ô 2: Nhu cầu chưa rõ, giải pháp có vẻ đơn giản

**Ví dụ:** thêm nút “Học ngay” ở nhiều vị trí giao diện rất dễ code, nhưng chưa biết vì sao học viên rời trang.

Ưu tiên:

- Phỏng vấn theo hành vi, quan sát luồng và kiểm tra phân khúc người học.
- Dùng prototype hoặc thử nghiệm giới hạn để làm rõ usefulness và usability.
- Đặt một giả thuyết outcome thay vì “phải có nút mới”.
- Không đầu tư mở rộng khi chưa có tín hiệu giá trị phù hợp.

**Sai lầm:** vì “chỉ mất hai ngày code” nên triển khai đại trà mà không quan sát chi phí chú ý, trải nghiệm hoặc hậu quả.

### Ô 3: Nhu cầu rõ, giải pháp chưa chắc

**Ví dụ:** đồng bộ tiến độ hai thiết bị là điều đã được xác nhận, nhưng cách nhất quán dữ liệu khi offline và xung đột vẫn chưa rõ.

Ưu tiên:

- Làm rõ bất biến và điều kiện chất lượng: không ghi lùi, không cấp sai quyền.
- Thử POC kỹ thuật/spike có câu hỏi cụ thể và thời hạn.
- Dùng contract, integration, concurrency và recovery tests.
- Chia lát kỹ thuật có thể chứng minh rủi ro, không gọi POC thành Increment Done.

**Sai lầm:** phỏng vấn thêm rất nhiều người để giải quyết một giới hạn transaction đã biết.

### Ô 4: Nhu cầu và giải pháp đều chưa chắc

**Ví dụ:** gợi ý học tập cá nhân hóa bằng AI từ dữ liệu lịch sử, chưa rõ nhu cầu, chất lượng mô hình, chi phí và chính sách dữ liệu.

Ưu tiên:

- Giảm rủi ro lớn nhất trước: xác nhận có vấn đề thực tế và đánh giá việc dùng dữ liệu có hợp lệ.
- Dùng prototype trải nghiệm **không xử lý dữ liệu nhạy cảm thật** nếu có thể.
- Chọn một feasibility spike hẹp để kiểm tra khả năng cơ bản.
- Quy định rõ điều kiện **dừng đầu tư** khi giá trị hoặc an toàn không được xác nhận.
- Chỉ tăng phạm vi khi bằng chứng đủ dùng cho quyết định tiếp theo.

**Sai lầm:** ký hợp đồng nền tảng lớn và thiết kế cả kiến trúc khi chưa biết học viên có cần kết quả ấy hay không.

### Mức bất định có thể thay đổi sau một ngày

Một test tích hợp mới có thể làm lộ thêm rủi ro; một cuộc phỏng vấn tốt có thể bác bỏ giả thuyết về người dùng. Ma trận là **ảnh chụp tại thời điểm quyết định**, cần được cập nhật theo bằng chứng, không phải nhãn vĩnh viễn của team.

## 14. Workshop đánh giá trong một buổi: từ ý tưởng tới quyết định thử

Không cần bắt đầu bằng chương trình khảo sát nhiều tháng. Với một cơ hội sản phẩm cụ thể, có thể làm một **workshop ngắn 60–90 phút**.

### Chuẩn bị

- Chọn **một quyết định thực** cần đưa ra: ví dụ có nên xây AI gợi ý bài học trong quý này?
- Mời đúng góc nhìn: Product Owner, Developers, tester, người nghiệp vụ, bảo mật/dữ liệu nếu liên quan, hỗ trợ hoặc đại diện người dùng.
- Mang vài nguồn hiện có: phản hồi, ví dụ hành trình, bug, quy tắc quyền, số liệu sử dụng.
- Nói rõ **không đánh giá năng lực cá nhân**, không ép mọi người tỏ ra chắc chắn.

### Sáu bước điều phối

1. **Viết kết quả người dùng cần đạt:** không bắt đầu từ tên công nghệ.
2. **Liệt kê giả định:** về người dùng, giá trị, kỹ thuật, dữ liệu, vận hành và quyền quyết định.
3. **Đánh dấu đã biết/chưa biết:** ghi bằng chứng, nguồn và phạm vi; phân biệt facts với opinions.
4. **Ước lượng tác động nếu sai:** quyền, mất dữ liệu, chi phí, làm lại và khả năng đảo ngược.
5. **Chọn tối đa vài câu hỏi cần trả lời trước:** không tạo backlog 100 nghiên cứu.
6. **Giao phép thử và mốc xem lại:** owner, kết quả dự kiến, guardrail, người chốt quyết định.

### Bảng đầu ra

| Câu hỏi | Tình trạng | Việc tiếp theo | Người cùng tham gia |
| --- | --- | --- | --- |
| Học viên có thực sự khó tìm bài tiếp theo? | Có tín hiệu hỗ trợ, chưa đo phạm vi | Quan sát vài hành trình và phân tích event | PO, UX, hỗ trợ |
| Nút tiếp tục học đơn giản có giúp? | Giải pháp ứng viên | Usability prototype cho khóa tuyến tính | UX, Developers, tester |
| Có đồng bộ được hai thiết bị an toàn? | Rủi ro kỹ thuật cao | Integration spike và test không ghi lùi | Developers, vận hành |
| Dữ liệu dùng cho AI có đúng mục đích? | Chưa được thẩm định | Làm rõ với người có thẩm quyền | PO, privacy/security |
| Khi nào được bật rollout? | Phụ thuộc release policy | Xác định cohort, DoD và guardrails | Developers, vận hành, PO |

**Đầu ra tốt nhất của buổi đánh giá** có thể là quyết định **“chưa xây AI; thử lát tiếp tục học đơn giản trước”**. Đó không phải thất bại nếu nó tránh đầu tư lớn vào điều chưa biết.

## 15. Một ví dụ xuyên suốt: “Tiếp tục học” từ nhu cầu tới giải pháp

### 15.1. Bối cảnh sản phẩm

Nền tảng phục vụ khóa tuyến tính ba bài. Học viên có thể học trên điện thoại và mở lại trang web. Nhóm nhận phản hồi:

> “Em học xong bài đầu trên điện thoại rồi hôm sau mở máy tính không biết bấm vào đâu để học tiếp.”

Có ít nhất ba giả định:

- **Giả định N1 (nhu cầu):** nhiều học viên mất thời gian tìm bài chưa hoàn thành khi quay lại.
- **Giả định N2 (giải pháp trải nghiệm):** một nút “Tiếp tục học” rõ ràng giúp họ mở đúng bài với ít thao tác hơn.
- **Giả định S1 (giải pháp kỹ thuật):** hệ thống có thể xác định tiến độ mới nhất giữa các thiết bị mà không làm sai quyền.

### 15.2. Không vội biến phản hồi thành một epic lớn

Một nhóm có thể đề xuất **AI phân tích lịch sử học, đồng bộ offline, hệ thống nhắc học, dashboard tiến độ**. Nhưng nếu giả thuyết N1 chưa được xác nhận, một nghiên cứu sản phẩm nhỏ có thể hữu ích hơn việc ước lượng toàn bộ epic.

### 15.3. Kế hoạch học theo thứ tự rủi ro

| Giai đoạn | Câu hỏi cần giảm bất định | Phép kiểm tra | Điều kiện xem lại |
| --- | --- | --- | --- |
| **Discovery nhu cầu** | Người học gặp khó khăn gì khi quay lại? | Phỏng vấn gần hành vi, support, analytics | Có bằng chứng tình huống và phân khúc |
| **Prototype UI** | Họ có tìm và hiểu nút không? | Usability test trong luồng khóa tuyến tính | Quan sát thành công/thất bại, không chỉ ý kiến |
| **Vertical slice** | Logic quyền và tiến độ có đúng? | Unit + API/security + integration tests | Đạt DoD/guardrails |
| **Pilot** | Học viên thật có mở đúng bài dễ hơn? | Cohort có phép đo và đường dừng | Outcome và tác dụng phụ |
| **Mở rộng** | Bằng chứng có phù hợp thiết bị/khóa khác? | Theo dõi từng nhóm và hợp đồng | Quyết định mở rộng có căn cứ |

### 15.4. Acceptance criteria làm rõ hành vi đã chốt

~~~gherkin
Feature: Tiếp tục học đúng quyền và đúng tiến độ

  Scenario: Học viên đủ điều kiện mở bài tiếp theo
    Given học viên có đăng ký ACTIVE cho khóa tuyến tính
    And khóa có ba bài học theo thứ tự
    And học viên đã hoàn tất bài thứ nhất
    When học viên chọn "Tiếp tục học"
    Then hệ thống mở bài thứ hai

  Scenario: Học viên đã hoàn thành khóa
    Given học viên có quyền và đã hoàn thành cả ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không điều hướng đến bài thứ tư

  Scenario: Người chưa được duyệt không được mở bài hạn chế
    Given học viên chỉ có yêu cầu ghi danh PENDING
    When học viên gọi API trực tiếp để mở bài hạn chế
    Then hệ thống từ chối cấp nội dung

  Scenario: Tiến độ đã cập nhật trên thiết bị khác
    Given học viên đủ điều kiện đã hoàn tất bài thứ hai trên thiết bị A
    And hệ thống đã xác nhận tiến độ mới theo hợp đồng đồng bộ
    When học viên chọn "Tiếp tục học" từ thiết bị B
    Then hệ thống mở bài thứ ba
~~~

**Lưu ý:** Ví dụ đồng bộ phải được nghiệp vụ và Developers xác nhận rõ **khi nào tiến độ được coi là đã đồng bộ**. Nếu sản phẩm cho phép offline và eventual consistency, không nên viết tiêu chí “luôn tức thì” nếu không phù hợp hợp đồng thực.

### 15.5. Ranh giới giữa uncertainty và DoD

Không biết nút màu nào dễ thấy hơn là bất định có thể thử nghiệm. Nhưng khi cung cấp một Increment có thể dùng, **DoD, quyền học, dữ liệu và kiểm thử bắt buộc phải được đáp ứng**. Không được giữ thiếu sót an toàn dưới nhãn “thử nghiệm Agile”.

## 16. Case study bốn cơ hội: chọn những cách tiếp cận khác nhau

Một doanh nghiệp có cùng một nhóm sản phẩm nhưng bốn loại việc:

| Cơ hội | Nhu cầu | Giải pháp | Tác động nếu sai | Đề xuất bước đầu |
| --- | --- | --- | --- | --- |
| **A. Sửa nhãn sai của trạng thái ghi danh** | Rõ: PENDING phải hiển thị chờ duyệt | Rõ: sửa mapping, có test | Trung bình, có thể làm người học hiểu sai | Thực hiện và kiểm thử hồi quy nhanh |
| **B. Nút nhắc học hàng ngày** | Chưa rõ: một số người không muốn bị làm phiền | Kỹ thuật tương đối rõ | Có thể tăng phiền nhiễu, gây opt-out | Discovery/kiểm tra quyền chọn thông báo, pilot |
| **C. Đồng bộ tiến độ hai thiết bị** | Rõ trong nhóm học viên nhiều thiết bị | Chưa rõ do cache và conflict | Có thể sai/mất tiến độ | Spike kỹ thuật + vertical slice, integration tests |
| **D. AI gợi ý lộ trình cá nhân** | Chưa rõ người dùng cần gì | Chưa rõ chất lượng, dữ liệu, chi phí | Cao về riêng tư, uy tín và đầu tư | Xác nhận nhu cầu, thẩm định dữ liệu, POC hẹp nếu hợp lệ |

### Cơ hội A: không cần Agile theatre

Lỗi PENDING có reproduction rõ, quy tắc đã được xác nhận và cách sửa được hiểu. Nhóm nên xử lý trong luồng thích hợp, chạy test liên quan, review/CI và kiểm tra kết quả. Bắt buộc tạo một chuỗi họp discovery nhiều tuần không cải thiện giá trị.

### Cơ hội B: hỏi đúng đối tượng

Nếu chỉ phỏng vấn những người học tích cực, nhóm có thể kết luận **mọi người muốn nhận thêm thông báo**. Nhưng người dễ bị phiền hoặc đã tắt thông báo không xuất hiện trong mẫu. Cần xem nhóm người học, kênh thông báo, quyền lựa chọn và guardrail về trải nghiệm/riêng tư.

### Cơ hội C: học kỹ thuật trước khi scale

Không giải quyết cache conflict bằng một bài khảo sát hài lòng. Hãy xác định **bất biến dữ liệu**, test luồng đa phiên, lỗi mạng và chiến lược khôi phục. Có thể giao lát đầu chỉ hỗ trợ khi đã online và đồng bộ xác nhận, thay vì hứa hỗ trợ offline toàn diện ngay.

### Cơ hội D: hai hướng học độc lập nhưng liên quan

Trong khi Product Owner kiểm chứng người học có vấn đề lộ trình thật, Developers có thể đánh giá **khả năng giải quyết một phần phi nhạy cảm** bằng dữ liệu giả lập. Nhưng cần người có thẩm quyền xác nhận việc xử lý dữ liệu nếu muốn tiếp tục. Nếu nhu cầu không đủ giá trị, một POC kỹ thuật rất thành công vẫn không phải lý do để xây sản phẩm.

## 17. Chọn Scrum, Kanban, XP, Lean và discovery theo vấn đề

Ma trận bất định gợi ý **loại học hỏi cần thiết**; nó **không tự quyết định** đội phải dùng framework nào. Hình thức tổ chức còn phụ thuộc loại việc, năng lực giao phần mềm, nhịp nhu cầu và ràng buộc.

| Tình huống nổi bật | Thực hành/cách tiếp cận có thể hữu ích | Điều nó không tự giải quyết |
| --- | --- | --- |
| Sản phẩm phức tạp, chưa biết giải pháp mang giá trị nào, cần nhịp kiểm tra thường xuyên | **Scrum**: Product Goal, Sprint Goal, Increment, Review và Retrospective | Không tự cung cấp nghiên cứu người dùng, CI hay test kỹ thuật |
| Yêu cầu đến liên tục, nhiều luồng ưu tiên, hàng đợi và blocker | **Kanban**: trực quan hóa, WIP limits, work item age, cycle time, SLE | Không tự xác nhận đúng nhu cầu hoặc thiết kế an toàn |
| Thay đổi kỹ thuật nhiều rủi ro, test chậm, integration muộn | **XP**: TDD, CI, refactoring, pairing, small releases | Không tự làm rõ Product Goal hoặc phân quyền dữ liệu |
| Nhiều bước bàn giao, tối ưu cục bộ, thời gian chờ cao | **Lean/VSM**: nhìn dòng giá trị, giảm batch và làm lại | Không thay thế ranh giới chất lượng hoặc quyền quyết định |
| Chưa biết người dùng cần gì hay giá trị có thật | **Product discovery**: phỏng vấn, quan sát, prototype, pilot | Không tạo Increment đạt DoD chỉ bằng slide và khảo sát |
| Chưa biết hệ thống làm được hay không | **Spike/POC, kiến trúc tiến hóa, test tích hợp** | Không chứng minh người dùng cần kết quả |
| Hợp đồng/tuân thủ bắt buộc, rủi ro khó đảo ngược | **Risk-based governance** kết hợp Agile | Không cho phép bỏ phê duyệt hoặc tiêu chuẩn bắt buộc |

### Scrum không chỉ dành cho nhu cầu bất định

Scrum hữu ích để giải quyết **những vấn đề phức tạp cần empiricism**. Tuy nhiên, có những dòng việc vận hành phản hồi theo từng request không nhất thiết hưởng lợi từ Sprint cố định. Nhóm có thể dùng Kanban hoặc kết hợp thực hành flow với Scrum tùy bối cảnh và tuân thủ các nguyên tắc khi công bố là Scrum.

### Scrum có commitments, không chỉ là nhịp họp

Trong Scrum, **Product Goal gắn với Product Backlog; Sprint Goal gắn với Sprint Backlog; Definition of Done gắn với Increment**. Những cam kết này giúp phân biệt **cần giao kết quả gì**, **tại sao Sprint có giá trị** và **khi nào Increment thực sự hoàn tất**.

### Kanban giúp nhìn cả chuyện đang chờ

Nếu hàng đợi Review/Test lớn, team có thể thử chính sách **hoàn tất trước khi bắt đầu thêm**, WIP limit và xem Work Item Age. Dữ liệu flow không thay thế việc tìm nguyên nhân về yêu cầu; nếu story liên tục phải hỏi lại nghiệp vụ, cần **refinement/acceptance examples** chứ không chỉ đổi số WIP.

### XP giảm bất định kỹ thuật bằng feedback ngắn

TDD và CI không dự đoán được toàn bộ production, nhưng giúp biến những quy tắc đã hiểu thành **bằng chứng chạy được**. Pairing và refactoring có thể giảm rủi ro kiến thức tập trung. Các thực hành phải được đánh giá cùng chất lượng test và khả năng duy trì, không bằng số lượng test hay commit.

## 18. Độ dài vòng học hỏi và khả năng giao Increment

**Iterative** nghĩa là học và điều chỉnh qua nhiều vòng. **Incremental** nghĩa là thêm những phần sản phẩm có ích và đã tích hợp. Hai đặc điểm có thể kết hợp, nhưng không đồng nghĩa.

### Khi bất định nhu cầu cao

Ưu tiên vòng học hỏi đủ ngắn để kiểm tra **những giả định lớn** trước khi xây nhiều thứ. Một prototype có thể thay đổi qua vài vòng; một Increment thật cung cấp khả năng dùng được, cho phép quan sát hành vi có giá trị hơn trong một số câu hỏi.

### Khi bất định giải pháp cao

Ưu tiên khám phá các rủi ro kỹ thuật **sớm trong lát nhỏ**: đồng bộ, quyền, migration, concurrency hoặc hiệu năng. Dùng spike nếu cần nhưng **đừng tích lũy cả Sprint chỉ có tài liệu POC mà gọi là nhiều Increment đã Done**.

### Khi cả hai đều thấp

Giảm batch size và giao thay đổi an toàn. Không nhất thiết phải tạo thêm các chu kỳ nghiên cứu không sinh thông tin mới.

### Nhịp Sprint cố định không phải độ dài tối ưu của mọi thí nghiệm

Một phỏng vấn có thể diễn ra trong ngày, một phép thử tích hợp có thể cần vài giờ, còn quan sát retention cần nhiều tuần. Các hoạt động học hỏi **có nhịp riêng**, nhưng chúng cần được phối hợp trong kế hoạch sản phẩm và chính sách team để tránh WIP vô hạn.

### Không đem DoD ra trao đổi

Nếu một lát chưa đáp ứng DoD, nó chưa phải Increment Done. Có thể **giữ thử nghiệm kỹ thuật trong môi trường an toàn** nhưng không tự xem mã prototype chưa được bảo vệ là sản phẩm sẵn sàng giao cho người dùng.

## 19. Lập kế hoạch theo mức hiểu biết: rolling-wave và quyết định có điều kiện

Khi độ bất định cao, một kế hoạch chi tiết đến từng task cho sáu tháng dễ trở thành **giả định được viết rất đẹp**. Có thể lập kế hoạch theo nhiều mức:

- **Xa:** mục tiêu và ràng buộc chiến lược, các giả định lớn cần giảm.
- **Trung hạn:** những lát cơ hội, kỹ thuật và rủi ro có khả năng thử.
- **Gần:** những công việc đủ rõ để làm, tiêu chí chấp nhận, điều kiện chất lượng và phản hồi.

### Ví dụ cho “Tiếp tục học”

| Thời điểm quyết định | Phạm vi có thể chốt | Phần chưa nên khóa cứng |
| --- | --- | --- |
| **Bắt đầu** | Vấn đề học viên khó tiếp tục, guardrail quyền và dữ liệu | Toàn bộ giải pháp gợi ý AI |
| **Sau discovery** | Khóa tuyến tính là phân khúc ưu tiên, nút rõ ràng có tín hiệu sử dụng | Offline sync mọi thiết bị |
| **Sau spike kỹ thuật** | Lát đồng bộ nào có thể đáp ứng hợp đồng dữ liệu | Kiến trúc toàn diện cho mọi client tương lai |
| **Sau pilot** | Có nên mở rộng cohort hoặc sửa UX | Cam kết outcome tuyệt đối cho mọi nhóm |

### Forecast không phải lời hứa chắc chắn

Khi biết loại việc và có phân phối lead/cycle time tương đối ổn, nhóm có thể đưa **dự báo có điều kiện**. Nhưng PBI chứa rủi ro AI, tích hợp legacy hoặc dữ liệu mới không thể được dự báo như một bug giao diện đã biết.

**Độ bất định càng lớn, càng cần minh bạch phạm vi, giả thuyết và khả năng đổi quyết định**, thay vì tăng độ chính xác giả tạo của ngày giao.

### Cost of delay và chi phí học hỏi

Một thử nghiệm có thể đáng làm sớm vì nếu đoán sai, tổ chức mất nhiều tháng đầu tư; một phép thử khác có thể quá tốn kém so với tác động của quyết định. Hãy hỏi:

1. Nếu chờ thêm một vòng học, người dùng/tổ chức mất giá trị gì?
2. Nếu xây ngay mà giả định sai, chi phí sửa hoặc bỏ là bao nhiêu?
3. Phép thử nhỏ có thể giảm đáng kể rủi ro hay chỉ tạo thêm tài liệu?
4. Có giới hạn an toàn hoặc thời hạn bắt buộc nào khiến không thể trì hoãn?

Không cần đưa ra một **con số cost of delay chính xác** nếu thiếu dữ liệu; một so sánh có điều kiện và minh bạch giả định vẫn hữu ích.

## 20. Vai trò, quyền quyết định và giới hạn khi học dưới bất định

Không phải nhóm càng được tự chủ thì càng được phép tự đổi chính sách. Cần làm rõ **ai chịu trách nhiệm về giá trị, ai quyết kỹ thuật và ai chấp thuận rủi ro**.

### Trong Scrum

- **Product Owner** có accountability tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả; làm rõ mục tiêu và cân nhắc bằng chứng discovery.
- **Developers** chịu trách nhiệm tạo Increment đạt DoD và tự quản cách thực hiện trong Sprint; nêu rủi ro kỹ thuật và đề xuất cách giảm bất định.
- **Scrum Master** hỗ trợ việc sử dụng Scrum và hiệu quả của Scrum Team, giúp các bên tháo trở ngại và tăng minh bạch.
- **Stakeholders/người dùng** cung cấp phản hồi, điều kiện nghiệp vụ và bối cảnh; họ không mặc định có quyền điều khiển trực tiếp mọi task trong Sprint.

### Ma trận quyền quyết định minh họa

| Quyết định | Người chủ động | Điều cần phối hợp |
| --- | --- | --- |
| Câu hỏi sản phẩm cần kiểm chứng tiếp | Product Owner với Scrum Team và stakeholder | Nhu cầu, giá trị, rủi ro và Product Goal |
| Cách chia lát, test và thiết kế nội bộ | Developers | DoD, hợp đồng, quyền học và phụ thuộc |
| Đổi chính sách PENDING/ACTIVE | Người có thẩm quyền nghiệp vụ/sản phẩm | Bảo mật, API, tác động tới người dùng |
| Dùng dữ liệu học viên cho mục đích mới | Người có thẩm quyền dữ liệu/privacy theo chính sách | Product Owner, Developers, nghĩa vụ áp dụng |
| Bật hoặc dừng pilot production | Người được trao quyền release/incident | Cohort, guardrails, Product Owner, vận hành |
| Thay đổi API liên nhóm | Developers các bên và người có quyền quản lý hợp đồng | Tương thích, contract tests, kế hoạch chuyển tiếp |

Ma trận cần **được điều chỉnh theo tổ chức**, không phải quy chuẩn pháp lý. Một “thử nghiệm” vẫn cần đáp ứng các ràng buộc quyền truy cập và bảo vệ dữ liệu hiện hành.

### Khi thiếu bằng chứng nhưng quyết định vẫn phải được đưa ra

Nếu mốc khai giảng đã tới, Product Owner và các bên liên quan có thể chọn **lát an toàn có bằng chứng tốt nhất**, ghi rõ phạm vi chưa phục vụ và kế hoạch tiếp tục học. Không nên tuyên bố đã loại bỏ mọi bất định hoặc hạ DoD để giữ một ngày hứa chưa có cơ sở.

## 21. Đo lường sự giảm bất định và hiệu quả của lựa chọn

Chọn đúng cách học không có nghĩa luôn làm nhiều nghiên cứu. Cần xem **quyết định có tốt lên, người dùng có nhận giá trị và hệ thống có an toàn hơn** không.

### Ba nhóm thước đo

| Nhóm | Ví dụ | Bẫy cần tránh |
| --- | --- | --- |
| **Learning/decision** | Số giả định quan trọng được kiểm chứng, quyết định thay đổi vì dữ liệu, thời gian từ câu hỏi tới bằng chứng | Đếm số thí nghiệm hoặc báo cáo như mục tiêu tự thân |
| **Value/outcome** | Tỷ lệ học viên đủ điều kiện mở đúng bài, thời gian hoàn thành tác vụ, phản hồi thực tế | Chỉ đếm lượt click và xem là giá trị |
| **Flow/quality** | Lead time theo ranh giới, work item age, escaped defects, sự cố quyền và dữ liệu | Giảm lead time bằng cách đẩy lỗi sang production |

### Ví dụ định nghĩa outcome

~~~text
Tỷ lệ học viên tiếp tục học đúng bài
  = Số học viên đủ điều kiện quay lại và mở đúng bài tiếp theo
    / Số học viên đủ điều kiện quay lại trong cửa sổ đo
    × 100%
~~~

Giả sử trước thử có **80/200 = 40%** học viên đủ điều kiện mở đúng bài trong một khoảng quan sát, sau thử có **99/180 = 55%** trong khoảng đo tiếp theo. Chênh lệch quan sát là **15 điểm phần trăm**; mức tăng tương đối là **(55 − 40)/40 = 37,5%**.

Đây là **số minh họa**, không chứng minh thay đổi UI gây ra toàn bộ mức tăng. Hai tập có thể khác mức độ hoạt động, nội dung khóa, mùa học, cách chọn mẫu hoặc những thay đổi khác đồng thời.

### Đo giảm bất định kỹ thuật bằng khả năng phát hiện lỗi

Nếu spike về cache đã tạo được một integration test thất bại khi đọc tiến độ cũ và thành công với cơ chế đồng bộ mới, đó là bằng chứng cụ thể về rủi ro đã hiểu hơn. Nhưng vẫn cần kiểm tra **production guardrails, tình huống tải và khôi phục**, không tuyên bố “đã giải quyết mọi trường hợp”.

### Thước đo không thay thế quyết định

Một dashboard có thể thể hiện throughput tăng, nhưng một lỗi cấp quyền nghiêm trọng vẫn đủ lý do dừng rollout. **Không cho phép chỉ số trung bình che mất rủi ro không thể đánh đổi**.

## 22. Ví dụ phân tích dữ liệu: hai lựa chọn đầu tư có điểm mù khác nhau

Giả sử Product Owner cân nhắc:

- **Phương án A:** nút “Tiếp tục học” cho khóa tuyến tính.
- **Phương án B:** gợi ý AI cá nhân hóa tất cả khóa.

Một bảng ghi **giả định và dữ liệu minh họa**:

| Tiêu chí | Phương án A | Phương án B |
| --- | --- | --- |
| Nguồn nhu cầu | Phản hồi lặp về tìm bài tiếp theo; đã quan sát vài hành trình | Chủ yếu là đề xuất từ stakeholder |
| Phạm vi người học | Khóa tuyến tính có tiến độ rõ | Nhiều loại khóa, dữ liệu không đồng nhất |
| Bất định nhu cầu | Trung bình, còn cần xác nhận tần suất | Cao, chưa biết ai thật sự cần |
| Bất định giải pháp | Trung bình: quyền và đồng bộ cần test | Cao: mô hình, chất lượng, dữ liệu, chi phí |
| Rủi ro | Có thể mở sai bài hoặc sai quyền nếu thiết kế kém | Có thêm riêng tư, sai lệch gợi ý và chi phí |
| Phép thử hữu ích đầu tiên | Usability test + vertical slice có API tests | Kiểm chứng vấn đề + xem chính sách dữ liệu; sau đó POC hẹp nếu phù hợp |
| Quyết định có thể đưa ra ngay | Có thể thử lát khóa tuyến tính trong guardrails | Chưa đủ bằng chứng cam kết hệ thống toàn diện |

### Không tính ROI giả từ hai bảng điểm

Có thể định tính rằng A dễ học sớm và rủi ro hơn B về phạm vi, nhưng **không được tự chế ROI = 217%** nếu không có dữ liệu về chi phí, doanh thu, mức ảnh hưởng hoặc phương án đối chứng phù hợp.

### Câu hỏi làm thay đổi thứ tự

Nếu phát hiện tất cả học viên chỉ gặp khó do lỗi tiến độ hiện tại, ưu tiên đầu tiên có thể là **sửa dữ liệu và quyền**, không phải xây nút mới. Nếu có nghĩa vụ hỗ trợ tiếp cận cho một nhóm người học, rủi ro và ưu tiên cũng có thể thay đổi dù thị phần nhỏ. Bảng đánh giá cần **có khả năng cập nhật khi xuất hiện thông tin mới**.

## 23. Các tình huống khiến việc chọn cách tiếp cận dễ sai

### 23.1. “Khách hàng đã viết yêu cầu 100 trang, tức nhu cầu đã rõ”

Tài liệu dài có thể vẫn bỏ sót bối cảnh người dùng hoặc mâu thuẫn giữa những quy tắc. Cần kiểm tra **tính nhất quán, quyền xác nhận và ví dụ chấp nhận**, không suy ra mức tin cậy từ số trang.

### 23.2. “Chỉ cần chạy khảo sát để xác nhận giải pháp”

Nếu khảo sát đặt câu “Bạn có muốn hệ thống AI tuyệt vời giúp học hiệu quả hơn không?”, kết quả bị dẫn dắt. Nên kiểm tra **hành vi gần đây, tác vụ thực và những phương án thay thế**, không chỉ số người bấm “Có”.

### 23.3. “Đội giỏi nên mọi giải pháp đều chắc”

Một Developer giỏi vẫn có thể thiếu thông tin về API bên ngoài, dữ liệu cũ, luật hoặc tải thực tế. Sự tự tin cần đi kèm **bằng chứng đúng bối cảnh**.

### 23.4. “Spike xong thì đã Done”

Spike có thể xác nhận một lựa chọn kỹ thuật, nhưng **không tạo Increment sử dụng được** nếu mã chưa được tích hợp và đạt DoD. Cần làm rõ output của nghiên cứu và trạng thái sản phẩm.

### 23.5. “Pilot tốt thì rollout toàn bộ”

Một cohort nhỏ, người dùng tích cực hoặc được hỗ trợ đặc biệt có thể không đại diện. Cần xem **tính tương đồng, giới hạn tải, khả năng khôi phục và tác động tới nhóm khác** trước khi mở rộng.

### 23.6. “Nhu cầu chưa rõ nên có thể trì hoãn sửa lỗi bảo mật”

Sai. Nếu quyền truy cập trái phép hoặc dữ liệu bị ảnh hưởng, cần áp dụng quy trình bảo mật/incident ngay. Không thể viện cớ discovery chưa đủ để bỏ nghĩa vụ bảo vệ hiện tại.

### 23.7. “Nếu không biết, cứ build nhiều rồi xem”

Giao sớm Increment có giá trị giúp học, nhưng **xây toàn bộ kiến trúc để thử một giả thuyết nhỏ** là sự đầu tư không tương xứng. Chọn lát đủ nhỏ để thu tín hiệu với guardrails thích hợp.

### 23.8. “Muốn Agile thì bỏ mọi bước phê duyệt”

Một số kiểm soát về dữ liệu, hợp đồng và an toàn là bắt buộc. Cần phân biệt phê duyệt có giá trị với chờ không cần thiết; có thể **đưa kiểm tra vào pipeline hoặc trao quyền theo rủi ro** chứ không xóa hết.

## 24. Chống lại những phản mẫu khi đánh giá bất định

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Đồng nhất nhu cầu với danh sách tính năng** | Tối ưu giải pháp sớm, bỏ vấn đề thật | Hỏi người dùng cần đạt outcome nào |
| **Chỉ đánh giá bất định kỹ thuật** | Xây giải pháp tốt cho nhu cầu không tồn tại | Discovery và đo hành vi trước đầu tư lớn |
| **Chỉ hỏi người dùng, bỏ rủi ro kỹ thuật** | Hứa tính năng khó tích hợp hoặc không an toàn | Feasibility spike, test/CI và guardrails |
| **Coi câu trả lời của một stakeholder là bằng chứng thị trường** | Thiên lệch theo người có quyền lực | Triangulate với người dùng, dữ liệu và hành trình |
| **Thang confidence có số thập phân tùy tiện** | Tạo vẻ chính xác giả | Định nghĩa mức và công bố nguồn bằng chứng |
| **Không phân biệt mơ hồ với nhu cầu mới** | Tốn discovery cho việc chỉ cần chốt quy tắc | Làm rõ owner nghiệp vụ và acceptance examples |
| **Prototype đẹp được xem như đã chứng minh nhu cầu** | Nhầm usability với demand/adoption | Quan sát hành vi, pilot theo cohort |
| **POC local được xem như production ready** | Bỏ tích hợp, an toàn, vận hành | DoD, integration/performance tests và rollout |
| **Spike không thời hạn** | Nghiên cứu kéo dài, không ra quyết định | Timebox, câu hỏi cụ thể, tiêu chí dừng |
| **Thử nghiệm không thể thất bại** | Kết luận luôn “thành công” | Nêu trước điều bác bỏ và ngưỡng an toàn |
| **Bỏ trường hợp âm của quyền** | Giao đúng happy path nhưng lộ dữ liệu | API/security tests cho PENDING và người trái quyền |
| **Đổi baseline sau khi có kết quả** | Số liệu không còn đáng tin | Chốt định nghĩa mốc, cohort, cửa sổ trước |
| **Chỉ đếm click hoặc số tính năng** | Không đo giá trị người dùng | Metric hành trình có mẫu số phù hợp |
| **Đếm mọi defect như nhau** | Một lỗi quyền nghiêm trọng bị che bởi lỗi nhẹ | Xem severity, phạm vi, phát hiện và phục hồi |
| **Xem mọi team cần một framework** | Thêm nghi thức không hợp loại việc | Chọn Scrum/Kanban/XP/Lean theo vấn đề |
| **Bắt đầu nhiều thử nghiệm cùng lúc** | Tăng WIP, khó biết điều gì tác dụng | Ưu tiên giả định lớn, thử ít và có owner |
| **Tối ưu velocity để chứng minh lựa chọn đúng** | Khuyến khích tăng điểm story và bỏ quality | Dùng outcome, flow, chất lượng và learning |
| **Coi pilot nhỏ là bằng chứng nhân quả chắc chắn** | Quyết định mở rộng quá sớm | Kiểm tra mẫu, yếu tố gây nhiễu và tính đại diện |
| **Dùng dữ liệu người dùng thiếu bảo vệ** | Tạo rủi ro quyền riêng tư mới | Tối thiểu hóa dữ liệu và thẩm định thẩm quyền |
| **Không có điểm dừng khi giả thuyết sai** | Tiếp tục đầu tư để bảo vệ kế hoạch cũ | Quyết định tiếp tục/đổi/dừng theo bằng chứng |
| **Không ghi ai có quyền chốt** | Feedback và rủi ro bị treo | Decision log, owner và đường escalation |
| **Đòi chắc chắn tuyệt đối trước khi hành động** | Trì hoãn cả thay đổi nhỏ an toàn | Chọn phép thử theo tác động và tính đảo ngược |

## 25. Bài thực hành: chọn cách xử lý cho bốn yêu cầu của nền tảng học

### 25.1. Đề bài

Scrum Team đang lập kế hoạch cải thiện hành trình học. Product Owner nhận bốn yêu cầu:

1. **A – Sửa lỗi:** giao diện hiển thị “Đã ghi danh” dù đăng ký của học viên đang PENDING. Chính sách đã xác nhận rằng PENDING chưa có quyền truy cập.
2. **B – Nhắc học:** một stakeholder muốn gửi thông báo hằng ngày cho tất cả học viên. Chưa có dữ liệu về lý do họ bỏ dở, và một số học viên tắt thông báo.
3. **C – Đồng bộ tiến độ:** nhiều học viên học cả trên web và mobile; luồng đa thiết bị là nhu cầu đã được xác nhận trong phân khúc này, nhưng cache có nguy cơ trả dữ liệu cũ.
4. **D – AI gợi ý:** một nhóm đề xuất xây hệ thống gợi ý lộ trình dựa trên lịch sử cá nhân; chưa xác nhận nhu cầu, mục đích sử dụng dữ liệu và chất lượng mô hình.

Tổ chức muốn giao kết quả sớm nhưng phải tuân thủ **DoD, quy tắc quyền học, giới hạn dữ liệu và khả năng dừng rollout**.

Thông tin bổ sung về một luồng thử “Tiếp tục học”:

~~~text
Trong giai đoạn trước thử:
  200 học viên đủ điều kiện quay lại
  80 học viên mở đúng bài tiếp theo

Trong giai đoạn sau thử:
  180 học viên đủ điều kiện quay lại
  99 học viên mở đúng bài tiếp theo

Trong nhóm 14 story kỹ thuật gần đây:
  8 story phải hỏi lại quy tắc nghiệp vụ sau khi bắt đầu

Một PBI hiện tại:
  Nhu cầu đã được PO xác nhận
  Unit test chọn bài tiếp theo đều xanh
  Integration test đa thiết bị chưa có
  Quyền mở bài trực tiếp cần được xác minh ở API
~~~

### 25.2. Nhiệm vụ

1. Đặt bốn yêu cầu A–D vào **ma trận bất định nhu cầu/giải pháp** và giải thích ngắn.
2. Nêu loại bằng chứng cần tìm đầu tiên cho B và D; vì sao không bắt đầu bằng phát triển toàn diện?
3. Viết **một giả thuyết nhu cầu** và **một giả thuyết giải pháp** cho C hoặc “Tiếp tục học”.
4. Đề xuất một **technical spike** có phạm vi và điểm dừng rõ.
5. Viết ít nhất **ba acceptance examples**, gồm một trường hợp từ chối quyền.
6. Tính tỷ lệ mở đúng bài trước/sau, chênh lệch điểm phần trăm và tăng tương đối; nêu giới hạn kết luận.
7. Tính tỷ lệ story bị chặn do mơ hồ nghiệp vụ trong mẫu 14 hạng mục.
8. Nêu những **guardrails không thể đem thử** chỉ để tăng outcome.
9. Chọn Scrum, Kanban, XP hoặc kết hợp cho C, kèm lý do dựa trên vấn đề thực.
10. Nêu quyền quyết định của Product Owner, Developers, người có thẩm quyền dữ liệu/bảo mật và vận hành.
11. Nếu pilot tăng outcome nhưng xuất hiện một sự cố cấp quyền trái phép, nhóm phải quyết định gì?
12. Viết một kế hoạch **một chu kỳ học hỏi**: owner, câu hỏi, phép thử, bằng chứng, mốc review và tiêu chí giữ/đổi/dừng.

### 25.3. Đáp án tham khảo – phân loại bốn yêu cầu

| Yêu cầu | Bất định nhu cầu | Bất định giải pháp | Đề xuất |
| --- | --- | --- | --- |
| **A** | Thấp: quy tắc và lỗi đã rõ | Thấp nếu sửa mapping và test phù hợp | Sửa lỗi, xác minh UI và API không cấp sai quyền; không cần discovery lớn |
| **B** | Cao: chưa biết thông báo có giúp hay làm phiền | Tương đối thấp về gửi notification, nhưng phụ thuộc quyền chọn/opt-out | Discovery, quan sát hành vi, cân nhắc pilot có kiểm soát |
| **C** | Thấp trong phân khúc đã xác nhận | Cao vì cache/consistency đa thiết bị | Timeboxed spike, integration tests, vertical slice có guardrails |
| **D** | Cao: nhu cầu chưa rõ | Cao: mô hình, dữ liệu, chi phí và vận hành | Xác minh vấn đề, thẩm định dữ liệu, POC hẹp nếu có cơ sở |

**Lưu ý:** Mức “thấp/cao” phụ thuộc những giả định của đề. Nếu kiểm tra thực tế cho thấy quy tắc A chưa được xác nhận hoặc C chỉ là ý kiến của một stakeholder, phải **điều chỉnh phân loại**, không giữ bảng vì muốn có đáp án cố định.

### 25.4. Đáp án tham khảo – giả thuyết

**Nhu cầu:**

> “Với học viên đủ điều kiện quay lại khóa tuyến tính, việc không biết bài tiếp theo khiến họ mất nhiều thao tác; một lối tắt rõ ràng có thể tăng tỷ lệ mở đúng bài trong một phiên quay lại”.

**Giải pháp:**

> “Nếu dịch vụ tiến độ sử dụng cơ chế xác nhận phiên bản dữ liệu theo hợp đồng, sau khi mobile cập nhật và hệ thống xác nhận hoàn tất đồng bộ, web có thể mở đúng bài mà không ghi lùi tiến độ”.

Hai giả thuyết **trả lời hai câu hỏi khác nhau**, nên cần hai loại bằng chứng: hành vi người học và kiểm thử tích hợp dữ liệu.

### 25.5. Đáp án tham khảo – spike và acceptance examples

**Spike mẫu:**

~~~text
Câu hỏi: Cache có thể trả tiến độ cũ sau cập nhật từ thiết bị khác?
Phạm vi: Khóa tuyến tính, hai phiên online, một service tiến độ
Timebox: Hai ngày làm việc (ví dụ, do team thống nhất)
Bằng chứng: Tập test ghi ở A/đọc ở B và điều kiện xung đột
Điều kiện đạt: Không mở sai bài sau mốc đồng bộ đã cam kết,
               không ghi lùi tiến độ, không cấp quyền sai
Kết quả: Đề xuất giải pháp, trade-off, rủi ro còn lại
Không bao gồm: Xây toàn bộ offline sync hoặc cam kết production-ready
~~~

**Ví dụ acceptance criteria:**

~~~gherkin
Feature: Tiếp tục học an toàn

  Scenario: Học viên ACTIVE mở bài tiếp theo
    Given học viên ACTIVE của khóa tuyến tính ba bài
    And học viên đã hoàn thành bài một
    When học viên yêu cầu tiếp tục học
    Then hệ thống mở bài hai

  Scenario: Đã hoàn tất khóa
    Given học viên ACTIVE và đã hoàn thành cả ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không điều hướng đến bài không tồn tại

  Scenario: Người chưa được duyệt thử gọi API
    Given học viên chỉ có đăng ký PENDING
    When học viên gọi API để mở nội dung hạn chế
    Then hệ thống từ chối cấp nội dung
~~~

Các câu Gherkin chỉ là **mẫu để cùng nghiệp vụ xác nhận**, không thay việc thực thi test ở tầng phù hợp và tuân thủ DoD.

### 25.6. Đáp án tham khảo – phép tính và giới hạn

~~~text
Trước thử = 80 / 200 × 100% = 40%
Sau thử   = 99 / 180 × 100% = 55%
Thay đổi  = 55% - 40% = 15 điểm phần trăm
Tăng tương đối = 15 / 40 × 100% = 37,5%

Story phải làm rõ quy tắc sau khi bắt đầu:
  8 / 14 × 100% ≈ 57,1% của mẫu đã quan sát
~~~

**Diễn giải:** tỷ lệ trong hai giai đoạn khác nhau, có thể do giải pháp, do người học, nội dung, mùa học, các thay đổi khác hoặc cách chọn mẫu. Không tự tuyên bố **“tính năng chắc chắn làm tăng retention 37,5%”**; phép tính nói về **tỷ lệ mở đúng bài trong cửa sổ đã đo**, không trực tiếp đo retention dài hạn.

### 25.7. Đáp án tham khảo – framework và guardrails

Với C, **XP practices** như TDD/CI/contract và integration tests giúp giảm bất định kỹ thuật; **Kanban** giúp nhìn blocked time/WIP trong luồng làm việc; nếu nhóm đang dùng Scrum, họ có thể đặt lát phù hợp vào Sprint Goal và kiểm tra Increment trong Sprint Review. **Không cần đổi toàn bộ framework** chỉ vì một kỹ thuật đang khó.

Guardrails: không truy cập trái quyền, không ghi lùi/mất tiến độ, không dùng dữ liệu ngoài phạm vi cho phép, Increment phải đạt DoD, có cách phát hiện và dừng rollout khi cần.

**Quyền quyết định:** Product Owner quyết định thứ tự Product Backlog và giá trị; Developers chọn cách thực thi và kiểm thử trong ranh giới; người có thẩm quyền dữ liệu/bảo mật xem những thay đổi ảnh hưởng quyền và mục đích dữ liệu; vận hành thực hiện quyền release/incident theo chính sách. Không một vai trò đơn lẻ có thể tự bỏ nghĩa vụ bắt buộc.

**Nếu có sự cố quyền:** phải ứng phó ngay, giới hạn rollout, bảo vệ người dùng, xác minh tác động và sửa theo quy trình. Outcome tăng **không bù đắp** việc cấp quyền trái phép.

### 25.8. Một kế hoạch học hỏi mẫu

| Thành phần | Nội dung |
| --- | --- |
| **Câu hỏi** | Học viên có cần cách mở bài nhanh hơn, và dữ liệu tiến độ có đủ an toàn? |
| **Owner** | Product Owner theo dõi nhu cầu; Developer đầu mối giải pháp; tester/vận hành phối hợp |
| **Phép thử nhu cầu** | Quan sát hành trình và prototype cho khóa tuyến tính |
| **Phép thử kỹ thuật** | Integration test đa phiên và API authorization test |
| **Bằng chứng cần có** | Hành vi hoàn thành tác vụ, test thất bại khi tái tạo bug, logs an toàn |
| **Guardrail** | DoD, đúng quyền, không ghi lùi tiến độ, dữ liệu tối thiểu |
| **Mốc xem lại** | Khi có đủ các kết quả thử đã thống nhất, không kéo dài nghiên cứu vô hạn |
| **Giữ/đổi/dừng** | Giữ nếu giá trị và an toàn được hỗ trợ trong phạm vi; đổi nếu còn khó sử dụng; dừng rollout nếu guardrail vi phạm |

Một đáp án tốt **không nhất thiết chọn một framework duy nhất**. Nó chứng minh được **vì sao lựa chọn phù hợp với điều chưa biết và cách nhóm sẽ biết mình đã học được điều gì**.

## 26. Mẫu ghi nhận bất định trước khi cam kết giải pháp

Có thể dùng mẫu ngắn dưới đây trong refinement, discovery, workshop chọn hướng tiếp cận hoặc decision record.

~~~text
TÊN CƠ HỘI / PBI:
Người dùng, bối cảnh và Product Goal liên quan:
Kết quả mong muốn (outcome), không chỉ solution:

A. BẤT ĐỊNH NHU CẦU
  - Giả định về người dùng/vấn đề:
  - Điều đã quan sát, nguồn và phạm vi:
  - Quy tắc nghiệp vụ còn mơ hồ:
  - Phản ví dụ và nhóm chưa được khảo sát:

B. BẤT ĐỊNH GIẢI PHÁP
  - Giả định feasibility, integration, dữ liệu, hiệu năng:
  - Bất biến quyền/chất lượng phải giữ:
  - Phụ thuộc và giới hạn tổ chức:
  - Điều đã chứng minh bằng test/POC:

C. QUYẾT ĐỊNH THEO RỦI RO
  - Mức bất định tương đối mỗi trục và bằng chứng:
  - Hậu quả nếu sai, khả năng đảo ngược:
  - Quyền quyết định/ai cần tham vấn:
  - Có rủi ro phải xử lý ngay không?

D. KẾ HOẠCH HỌC NHỎ NHẤT PHÙ HỢP
  - Câu hỏi cần trả lời trước khi cam kết tiếp:
  - Prototype / phỏng vấn / spike / vertical slice / pilot:
  - Owner, thời hạn, nguồn dữ liệu:
  - Điều kiện đạt/chưa kết luận/bác bỏ:
  - Guardrails và cách dừng/khôi phục:

E. HỌC VÀ CẬP NHẬT
  - Kết quả, giới hạn, dữ liệu trái chiều:
  - Giả định nào đã được củng cố hoặc bị bác bỏ?
  - Quyết định tiếp tục, thu hẹp, điều chỉnh hoặc dừng:
  - Product Backlog / thử nghiệm / DoD cần cập nhật:
~~~

### Dùng mẫu này ở mức phù hợp

Một bug căn lề nhỏ **không cần điền vài trang biểu mẫu**. Một tính năng mới dùng dữ liệu cá nhân hoặc một thay đổi khó đảo ngược cần ghi rõ hơn. Mẫu giúp **có dấu vết quyết định**, không nên trở thành lớp phê duyệt mới cho mọi việc.

## 27. Checklist đánh giá bất định nhu cầu và giải pháp

- [ ] Đã mô tả **người dùng, vấn đề, kết quả mong muốn** trước khi khóa giải pháp?
- [ ] Có phân biệt **nhu cầu chưa được chứng minh** với **giải pháp kỹ thuật chưa khả thi**?
- [ ] Đã nhận diện mơ hồ nghiệp vụ, biến động và phụ thuộc **khác** với hai trục bất định?
- [ ] Mỗi giả định quan trọng có **bằng chứng, nguồn, phạm vi và điều chưa biết**?
- [ ] Có hỏi người dùng về **hành vi/tình huống thật**, không chỉ hỏi họ có thích một tính năng?
- [ ] Số liệu nhu cầu có **mẫu số, cohort và cửa sổ đo** phù hợp?
- [ ] Đã xét nhóm người dùng không xuất hiện trong mẫu hoặc có nhu cầu tiếp cận khác?
- [ ] Giải pháp đã được xem theo **API, dữ liệu, concurrency, bảo mật, hiệu năng, vận hành, chi phí** khi liên quan?
- [ ] Những thay đổi khó đảo ngược có **cơ chế xác minh và phục hồi** tương xứng?
- [ ] Các guardrails **DoD, phân quyền, dữ liệu và nghĩa vụ bắt buộc** không bị đưa ra thử như tùy chọn?
- [ ] Đã xác định **ai có quyền quyết định** và khi nào cần tham vấn/escalation?
- [ ] Nếu nhu cầu cao bất định, đã cân nhắc **discovery/prototype/pilot** phù hợp?
- [ ] Nếu giải pháp cao bất định, đã cân nhắc **spike/POC/integration tests** có câu hỏi rõ?
- [ ] Spike/POC có **timebox, điểm dừng và kết quả nghiên cứu** tách với Increment Done?
- [ ] Phép thử có thể **bác bỏ giả thuyết**, không chỉ tìm bằng chứng ủng hộ?
- [ ] Không xem prototype đẹp, test local xanh hoặc pilot nhỏ là **bằng chứng tuyệt đối**?
- [ ] Đã đặt bất định cạnh **tác động nếu sai và khả năng đảo ngược**?
- [ ] Khi nhu cầu/giải pháp rõ, đã tránh tạo thêm nghi thức discovery không cần thiết?
- [ ] Khi cả hai trục cao, đã giảm **giả định lớn nhất** trước khi cam kết đầu tư rộng?
- [ ] Product Backlog và user stories được điều chỉnh theo **bằng chứng mới**, không bảo vệ kế hoạch cũ bằng mọi giá?
- [ ] Scrum, Kanban, XP, Lean và discovery được chọn theo **vấn đề thực tế**, không theo nhãn phong trào?
- [ ] Increment giao cho người dùng **đạt DoD**, không được đồng nhất với demo nghiên cứu?
- [ ] Có theo dõi **learning, outcome, flow và chất lượng**, không chỉ số tính năng/velocity?
- [ ] Khi metric cải thiện nhưng guardrail xấu, đã có cơ chế **dừng và ứng phó ngay**?
- [ ] Sau mỗi phép thử, nhóm ghi rõ **được hỗ trợ, bị phản bác hoặc chưa kết luận**, rồi quyết định bước tiếp?
- [ ] Việc giao Increment tăng dần vẫn tạo **phản hồi sớm, có ích và an toàn**?

**Ghi nhớ:** **Bất định nhu cầu hỏi liệu ta có đang giải quyết đúng vấn đề; bất định giải pháp hỏi liệu ta có thể giải quyết nó đúng cách, khả thi và an toàn.** Hãy xem hai trục này cùng mức ảnh hưởng, tính đảo ngược, quy tắc nghiệp vụ và bằng chứng hiện có. Khi nhu cầu chưa rõ, ưu tiên học từ người dùng; khi kỹ thuật chưa rõ, ưu tiên bằng chứng khả thi và kiểm thử; khi cả hai rõ, giao Increment nhỏ đạt DoD thay vì thêm thủ tục. Scrum, Kanban, XP, Lean và discovery chỉ thật sự có giá trị khi giúp đội **chọn điều cần học tiếp, nhận phản hồi sớm, thích ứng và giao sản phẩm tăng dần đáng tin cậy**.
