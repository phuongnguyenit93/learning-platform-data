# Lập kế hoạch cộng tác và phát hành theo phần nhỏ

Một nhóm xây dựng nền tảng học trực tuyến nhận yêu cầu: “Học viên phải tiếp tục học từ vị trí đang dở trên mọi thiết bị”. Nếu lập một kế hoạch chi tiết kéo dài ba tháng rồi chờ hoàn thành tất cả tính năng mới đưa tới người dùng, nhóm có thể phát hiện quá muộn rằng học viên cần nút “Học tiếp” dễ tìm hơn là một cơ chế đồng bộ phức tạp. Ngược lại, nếu chỉ cố ra bản mới hằng ngày mà không có kiểm thử hoặc tiêu chí hoàn tất, nhóm có thể làm mất tiến độ của học viên.

**Extreme Programming (XP) đề cao việc lập kế hoạch cùng người hiểu giá trị sản phẩm và giao những phần mềm nhỏ, hoạt động được, đủ chất lượng để nhận phản hồi sớm.** Bên hiểu nhu cầu kinh doanh quyết định điều gì có giá trị và cần ưu tiên; những người thực hiện giải thích chi phí, khả năng kỹ thuật và rủi ro; cả nhóm thương lượng phạm vi thay vì biến ước lượng thành mệnh lệnh. Các thực hành kỹ thuật như **test-first, tích hợp liên tục, thiết kế đơn giản, refactoring và lập trình cặp** làm cho những lần thay đổi nhỏ có thể thực hiện an toàn.

Bài thuộc chương **Extreme Programming** của module **AGILE_DEVELOPMENT**. Nội dung tập trung vào **lập kế hoạch cộng tác và phát hành theo phần nhỏ**, đồng thời kết nối với user story, backlog, Scrum, Kanban và đo lường dòng công việc để lựa chọn cách phối hợp thích hợp. Mục tiêu không phải học một lịch phát hành cứng mà là xây được **vòng học hỏi ngắn**: lựa chọn giá trị → lập kế hoạch đủ dùng → tạo phần mềm đáng tin → giao/phát hành an toàn → nhận phản hồi → điều chỉnh kế hoạch.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích cách **Planning Game** và các chu kỳ lập kế hoạch trong XP giúp người hiểu nghiệp vụ và Developers cùng ra quyết định.
2. Phân biệt trách nhiệm về **giá trị, mức ưu tiên, phạm vi** với trách nhiệm về **ước lượng, thiết kế, cách thực hiện và chất lượng**.
3. Chuyển một yêu cầu lớn thành các **user story dạng lát cắt dọc**, mỗi lát cắt có thể kiểm thử và tạo phản hồi.
4. Lập một kế hoạch phát hành tăng dần với **mục tiêu, phạm vi, rủi ro, tiêu chí chấp nhận và điểm điều chỉnh**.
5. Phân biệt **iteration, Increment, deployment, release và outcome**; không nhầm nhịp lập kế hoạch với lịch phát hành.
6. Sử dụng dữ liệu năng lực, flow và phản hồi sản phẩm để điều chỉnh thứ tự ưu tiên, thay vì bảo vệ dự báo ban đầu bằng mọi giá.
7. Áp dụng TDD, CI, refactoring, pair programming và kiểm thử chấp nhận để bảo vệ chất lượng khi giao thường xuyên.
8. Nhận diện những phản mẫu: “lập kế hoạch thay cho khách hàng”, “tính năng nào cũng phải xong một lần”, “ra nhanh bằng cách cắt kiểm thử” hoặc “đo năng suất bằng số story point”.

## 2. Vì sao XP nối lập kế hoạch với phát hành nhỏ?

Phần mềm có độ bất định ở ít nhất ba phía:

- **Bất định về giá trị:** người dùng có cần giải pháp này không? Vấn đề quan trọng nhất của họ là gì?
- **Bất định về cách làm:** công nghệ, kiến trúc, dữ liệu và phụ thuộc nào có thể gây trở ngại?
- **Bất định về việc giao hàng:** thực tế nhóm có thể hoàn thành bao nhiêu công việc đạt chất lượng trong khoảng thời gian tới?

Một kế hoạch dài hạn thường phải giả định trước cả ba điều trên. Khi giả định sai, chi phí làm lại tăng theo số lượng công việc đã thực hiện mà chưa được kiểm chứng. XP phản ứng bằng cách **giảm khoảng cách từ một quyết định đến lúc nhận bằng chứng**.

| Cách vận hành | Nhận phản hồi khi nào? | Rủi ro điển hình |
| --- | --- | --- |
| Thiết kế toàn bộ rồi triển khai một lần | Sau khi hoàn tất nhiều tháng phát triển | Phát hiện sai nhu cầu, khó tích hợp, chi phí sửa lớn |
| Chỉ chia lịch thành nhiều đợt nhưng mỗi đợt không có phần mềm dùng được | Có báo cáo tiến độ thường xuyên, phản hồi người dùng vẫn muộn | Nhầm lịch họp ngắn với vòng học hỏi ngắn |
| Lập kế hoạch cộng tác và giao lát cắt nhỏ đạt chuẩn | Ngay khi có phần mềm đủ an toàn để thử và dùng | Giảm độ lớn mỗi quyết định, điều chỉnh được ưu tiên |

**Phát hành nhỏ không có nghĩa làm hệ thống nửa vời hoặc bỏ qua bảo mật.** Một lát cắt có thể hẹp về tính năng và đối tượng phục vụ nhưng phải đúng với điều đã hứa. Ví dụ, bản đầu chỉ hỗ trợ học tiếp trên cùng thiết bị, tuy nhiên vẫn phải kiểm soát quyền truy cập và lưu tiến độ đúng tài khoản.

## 3. Nền tảng tư duy XP: giá trị, phản hồi và kỷ luật kỹ thuật

XP thường được giới thiệu với các giá trị **Communication, Simplicity, Feedback, Courage, Respect** — giao tiếp, đơn giản, phản hồi, dũng cảm và tôn trọng. Chúng không chỉ dành cho việc viết mã:

| Giá trị | Biểu hiện trong lập kế hoạch | Biểu hiện trong phát hành |
| --- | --- | --- |
| **Giao tiếp** | Người hiểu nghiệp vụ nói rõ điều cần đạt; Developers nói rõ rủi ro, năng lực và phương án | Các bên thấy phần đã Done, phản hồi và giới hạn chức năng |
| **Đơn giản** | Chọn lát cắt ít phức tạp nhất vẫn tạo giá trị thực | Không xây trước mọi biến thể chưa có bằng chứng cần thiết |
| **Phản hồi** | Kế hoạch được kiểm tra bằng hiểu biết mới sau mỗi chu kỳ | Kiểm thử tự động, tích hợp và người dùng phản hồi nhanh |
| **Dũng cảm** | Báo sớm rằng phạm vi không khả thi; đề xuất bỏ giả định sai | Sửa thiết kế, refactor hoặc dừng phát hành khi rủi ro quá cao |
| **Tôn trọng** | Không ép người thực hiện hứa điều thiếu cơ sở; lắng nghe vai trò khác | Không đánh đổi an toàn người dùng hoặc đổ lỗi khi một thử nghiệm không xác nhận giả thuyết |

XP là cách làm có cả **thực hành cộng tác** và **thực hành kỹ thuật**. Nếu chỉ tổ chức buổi Planning Game mà không có khả năng tích hợp, kiểm thử và giao phần mềm thường xuyên, vòng phản hồi sẽ vẫn chậm. Nếu chỉ có CI và TDD nhưng không hỏi người dùng cần gì, nhóm có thể phát triển rất nhanh một giải pháp sai.

## 4. Planning Game: đưa quyết định giá trị và khả năng thực hiện vào cùng một cuộc trao đổi

Trong XP cổ điển, **Planning Game** là cách các bên kinh doanh và kỹ thuật cộng tác để lựa chọn phạm vi cho bản phát hành hoặc chu kỳ làm việc. Đây không phải trò chơi lấy phiếu xem ai thắng, mà là cơ chế **đàm phán liên tục giữa điều mong muốn và điều có thể thực hiện**.

### Hai loại quyết định cần phân biệt

| Nhóm quyết định | Ai có thông tin và trách nhiệm chính? | Câu hỏi tiêu biểu |
| --- | --- | --- |
| **Giá trị và ưu tiên sản phẩm** | Customer / người đại diện nghiệp vụ có quyền quyết định; cùng các bên liên quan cần thiết | Người dùng nào cần hành vi này? Story nào quan trọng hơn? Phần nào có thể hoãn? |
| **Khả năng thực hiện và giải pháp kỹ thuật** | Programmers / Developers, phối hợp kiểm thử, vận hành và chuyên gia | Story lớn đến đâu? Rủi ro gì? Có thể kiểm thử và giao an toàn trong thời gian nào? |

“Customer” trong thực hành XP là **người có khả năng đưa ra quyết định nghiệp vụ kịp thời**, không nhất thiết một cá nhân đại diện cho mọi người dùng. Trong tổ chức thực tế, vai trò này có thể do người phụ trách sản phẩm đảm nhiệm, có sự hỗ trợ của người dùng, chuyên gia nghiệp vụ, thiết kế, hỗ trợ khách hàng và các bên liên quan.

**Không nên hiểu là khách hàng chỉ viết danh sách chức năng rồi Developers bị buộc hứa ngày.** Hai phía trao đổi để chọn một tập công việc có giá trị, phù hợp năng lực, có rủi ro được nhìn thấy.

### Một vòng trao đổi thường gặp

1. Người hiểu nghiệp vụ diễn đạt **mục đích** và các **câu chuyện** theo hành vi người dùng.
2. Developers đặt câu hỏi về ví dụ, giới hạn, tiêu chuẩn kiểm thử và rủi ro.
3. Developers đưa ra ước lượng tương đối/dự báo và những phần chưa biết.
4. Người quyết định nghiệp vụ **ưu tiên** dựa trên giá trị, tính khẩn, phụ thuộc và cơ hội học hỏi.
5. Các bên thương lượng tập story có thể hoàn tất trong chu kỳ hoặc đợt phát hành.
6. Khi nhóm giao phần mềm và nhận phản hồi, **quay lại** các quyết định trên.

Planning Game không kết thúc trách nhiệm lập kế hoạch. **Kế hoạch là một dự báo có thể cập nhật**, không phải lời khẳng định rằng mọi story đã chọn chắc chắn sẽ hoạt động như kỳ vọng.

## 5. Lập kế hoạch dài hơi và ngắn hạn: hai chân trời quyết định

Các mô tả thực hành XP có thể nhắc đến **release planning / iteration planning** trong cách tiếp cận cổ điển, hoặc **quarterly cycle / weekly cycle** trong các mô tả ở ấn bản sau. Đừng biến tên gọi và độ dài ví dụ thành luật cứng: điểm chung là **định hướng sản phẩm ở chân trời rộng** và **lựa chọn, điều chỉnh việc sắp làm ở chân trời gần**.

| Chân trời | Câu hỏi chính | Đầu ra có ích | Điều chưa nên giả vờ chắc chắn |
| --- | --- | --- | --- |
| **Định hướng phát hành / nhiều tuần** | Giá trị nào đáng đạt trước? Những đợt tăng dần nào có ý nghĩa? Rủi ro lớn nằm ở đâu? | Mục tiêu, thứ tự các lát cắt, giả định, phương án phát hành, điểm review | Ngày chính xác cho từng story xa nhiều tuần khi nhu cầu còn thay đổi |
| **Lập kế hoạch chu kỳ ngắn** | Với năng lực hiện tại, story nào nên làm tiếp và có thể Done? Cần phối hợp ra sao? | Tập story ưu tiên, tiêu chí chấp nhận, kế hoạch đủ hành động, trở ngại cần giải quyết | Mọi task sẽ diễn ra đúng giờ dự đoán |
| **Điều phối hằng ngày** | Đang bị chặn ở đâu? Cần kết hợp để hoàn tất việc gì? | Thứ tự công việc mới, hỗ trợ review/test, phản hồi kỹ thuật | Xem kế hoạch ngắn hạn là bất biến |

Ví dụ một nhóm chọn chu kỳ kế hoạch **một tuần**, còn đánh giá hướng sản phẩm theo **vài tuần**. Nhóm khác có thể dùng nhịp khác nếu loại công việc, phụ thuộc và thời gian tạo bằng chứng khác nhau. **Tần suất phù hợp phải giúp nhận phản hồi hữu ích, không chỉ tạo thêm cuộc họp.**

### Đặt mốc đánh giá, không khóa mọi chi tiết

Một kế hoạch phát hành có thể đánh dấu:

- **Mốc 1:** Học viên có thể tìm lại bài dở trên cùng thiết bị.
- **Mốc 2:** Học viên quay lại từ thiết bị khác mà tiến độ vẫn đúng.
- **Mốc 3:** Trải nghiệm xử lý mất mạng và xung đột cập nhật an toàn.

Thứ tự chỉ là **giả thuyết giá trị và rủi ro**. Nếu phản hồi cho thấy người dùng chủ yếu đổi thiết bị, mốc 2 có thể phải làm sớm hơn. Nếu rủi ro mất dữ liệu rất cao, cần xác minh cơ chế đồng bộ **trước khi phát hành** phần có thể gây hại.

## 6. Từ nhu cầu lớn đến các user story tạo giá trị

User story diễn đạt nhu cầu để nhóm cùng trao đổi, thường theo dạng:

> “Là **[đối tượng]**, tôi muốn **[hành vi/khả năng]** để **[lợi ích]**.”

Đây là cách mở đầu trao đổi, không thay thế ví dụ nghiệp vụ, tiêu chí chấp nhận hay thảo luận về giải pháp.

**Yêu cầu lớn:**

> “Là học viên, tôi muốn học tiếp ở vị trí gần nhất trên mọi thiết bị, ngay cả khi kết nối kém, để không mất tiến độ.”

Yêu cầu có nhiều luồng, quy tắc và rủi ro. Nhóm có thể tách thành các lát cắt:

| Story nhỏ | Lợi ích độc lập | Điều còn chưa hỗ trợ |
| --- | --- | --- |
| **S1 — Học tiếp trực tuyến trên cùng thiết bị** | Không phải duyệt danh sách để tìm bài dở | Chưa hứa đồng bộ tức thời giữa các thiết bị |
| **S2 — Học tiếp từ thiết bị thứ hai** | Có thể chuyển thiết bị mà không tìm thủ công | Chưa hứa làm việc offline |
| **S3 — Xử lý hai cập nhật tiến độ gần đồng thời** | Tránh mất dữ liệu do đồng bộ sai | Có thể chưa hỗ trợ lưu nhiều phiên offline kéo dài |
| **S4 — Tiếp tục sau mất kết nối** | Trải nghiệm ổn định hơn trong điều kiện mạng yếu | Những trường hợp ngoài phạm vi đã công bố vẫn cần chính sách |
| **S5 — Hướng dẫn khi bài đã hoàn thành hoặc không còn quyền học** | Người dùng hiểu hành động tiếp theo | Giao diện nâng cao không phải điều kiện để phân quyền cơ bản có hiệu lực |

**Lưu ý quan trọng:** Những điều kiện **bắt buộc về phân quyền, tính đúng đắn dữ liệu và an toàn** phải hiện diện ngay trong mọi story được phát hành. S5 có thể bổ sung thông điệp hướng dẫn, nhưng **không được hoãn kiểm tra quyền truy cập** đến khi làm S5. Nếu S1 có thể mất dữ liệu khi nhiều phiên thao tác, phải xử lý rủi ro trước khi mở cho người dùng tương ứng.

## 7. “Small release” là lát cắt dọc, không phải chia nhỏ các tầng kỹ thuật

Một lỗi phổ biến là chia tính năng thành:

~~~text
Đợt A: Tạo database
Đợt B: Viết API
Đợt C: Làm UI
Đợt D: Kiểm thử
Đợt E: Người dùng mới thử được
~~~

Đây là cách chia **công việc kỹ thuật** có thể cần thiết để phối hợp, nhưng các đợt A–D chưa chắc tạo một phần mềm có thể đem đến người dùng. Vòng học từ sản phẩm chỉ bắt đầu ở E.

Một cách chia dọc:

~~~mermaid
flowchart LR
    A["Nhu cầu học viên<br/>tìm lại bài đang dở"] --> B["Lát cắt 1<br/>UI + logic + dữ liệu + test"]
    B --> C["Increment nhỏ đạt chuẩn<br/>có thể thử an toàn"]
    C --> D["Quan sát người học<br/>và lỗi thực tế"]
    D --> E["Chọn lát cắt 2<br/>theo điều học được"]
    E --> F["Increment tiếp theo<br/>vẫn đạt chuẩn"]
    F -. "Phản hồi" .-> D
~~~

| Phân rã theo tầng | Phân rã theo hành vi |
| --- | --- |
| “Tạo endpoint đọc tiến độ” | “Học viên mở lại đúng bài đang dở” |
| “Tạo component nút” | “Học viên tìm thấy và sử dụng được hành động Học tiếp” |
| “Viết kịch bản kiểm thử” | “Story đạt điều kiện chấp nhận và có kiểm thử cần thiết” |

**Công việc kỹ thuật không biến mất**; nó trở thành các task nằm trong story có giá trị và được thực hiện theo cách giúp sớm tích hợp end-to-end. Một số backlog item kỹ thuật hoặc thử nghiệm rủi ro độc lập vẫn có thể hợp lý; điều cần tránh là **gọi mỗi task kỹ thuật là một release mang giá trị người dùng**.

## 8. Chọn thứ tự phát hành: giá trị, rủi ro và phụ thuộc

Không nhất thiết làm story dễ nhất trước. Nhóm cần cân đối:

1. **Giá trị người dùng:** lát cắt nào giải quyết khó khăn đang được quan sát rõ?
2. **Rủi ro nếu giả định sai:** phần nào có thể khiến phải làm lại nhiều hoặc gây hậu quả nghiêm trọng?
3. **Tốc độ học:** story nào cho phản hồi đủ tin cậy trong thời gian ngắn?
4. **Phụ thuộc:** story nào cần API, dữ liệu, quyền truy cập hoặc quyết định bên ngoài?
5. **Chi phí trì hoãn:** điều gì mất giá trị nếu chưa giao trong thời gian thích hợp?
6. **Năng lực giao an toàn:** nhóm có kiểm thử, triển khai và theo dõi cần thiết chưa?

| Lát cắt | Giá trị | Bất định/rủi ro | Quyết định minh họa |
| --- | --- | --- | --- |
| Nút Học tiếp trong cùng phiên học | Dễ kiểm chứng người học có tìm bài nhanh hơn không | Phải lưu tiến độ đúng tài khoản | Có thể ưu tiên sớm với phạm vi người dùng phù hợp |
| Đồng bộ nhiều thiết bị | Rất quan trọng nếu người dùng thường đổi thiết bị | Xung đột cập nhật, tính nhất quán và quyền truy cập | Cần kiểm chứng rủi ro sớm, có thể ưu tiên trước tính năng trang trí |
| Cá nhân hóa màu và hình minh họa | Có thể làm giao diện hấp dẫn hơn | Rủi ro kỹ thuật thấp | Chưa cần nếu vấn đề chính vẫn là mở đúng bài |
| Chống mất dữ liệu khi mất mạng | Bảo vệ trải nghiệm và tin cậy | Rủi ro vận hành cao | Bắt buộc trước khi hứa hỗ trợ offline thực sự |

**Ưu tiên một điều chưa biết có hậu quả lớn** có thể có ích hơn làm xong nhiều story ít quan trọng. Tuy nhiên, không nên biến mọi bất định thành một dự án “nghiên cứu đến khi chắc chắn”; hãy chọn **phép kiểm chứng hẹp có thời hạn** và nêu quyết định cần hỗ trợ.

## 9. Lập kế hoạch một release nhỏ: mẫu thực hành

Một kế hoạch phát hành cần đủ thông tin để cùng quyết định, không phải tài liệu hàng trăm trang.

~~~text
MỤC TIÊU GIÁ TRỊ
  Người dùng nào cần kết quả gì? Vì sao quan trọng?

PHẠM VI CỦA ĐỢT
  Các user story/lát cắt được chọn và điều kiện chấp nhận.
  Những hành vi chưa hỗ trợ phải được nói rõ.

TIÊU CHUẨN CHẤT LƯỢNG
  Kiểm thử, dữ liệu, bảo mật, vận hành, tài liệu cần thiết.
  Điều kiện nào là bắt buộc trước khi gọi Done/release?

RỦI RO VÀ GIẢ ĐỊNH
  Điều gì có thể sai? Bằng chứng nào cần có trước?

NĂNG LỰC VÀ DỰ BÁO
  Dữ liệu lịch sử, thời gian, phụ thuộc và mức bất định.

CÁCH GIAO VÀ THU PHẢN HỒI
  Đối tượng phát hành, feature flag/canary nếu phù hợp,
  phép đo/quan sát, cách rollback, liên hệ hỗ trợ.

ĐIỂM QUYẾT ĐỊNH TIẾP THEO
  Khi nào và ai đánh giá kết quả để giữ, đổi hoặc dừng hướng?
~~~

### Ví dụ release đầu tiên

**Mục tiêu:** Học viên đang học dở có thể quay lại đúng bài nhanh hơn.

**Phạm vi:** Một học viên đã đăng nhập, một khóa học đang có quyền truy cập, một bài chưa hoàn thành, trực tuyến trên cùng thiết bị; nút “Học tiếp” mở đúng vị trí hợp lệ.

**Chất lượng:** Phân quyền theo tài khoản, dữ liệu không hợp lệ được xử lý đúng, kiểm thử tự động và tích hợp, có khả năng phát hiện lỗi/hoàn tác phù hợp.

**Chưa hỗ trợ:** Không tuyên bố đồng bộ offline hay đồng bộ nhiều thiết bị trong thời gian thực.

**Bằng chứng cần học:** Học viên có tìm thấy nút và mở đúng bài không? Thời gian từ trang khóa học tới bài tiếp theo thay đổi ra sao? Có lỗi mất tiến độ không?

**Quyết định sau phản hồi:** Mở rộng đa thiết bị, cải thiện khả dụng hoặc điều chỉnh lại giả thuyết sản phẩm.

## 10. Từ release planning đến chu kỳ thực hiện ngắn

Một cách triển khai XP có thể dùng chu kỳ ngắn một tuần; nhóm khác chọn nhịp khác miễn giúp giao phần mềm và học hỏi thực chất. Chu kỳ **không tự động đồng nghĩa một lần phát hành production**, và một chu kỳ có thể hoàn tất nhiều lát cắt nếu chúng đạt điều kiện cần thiết.

### Trước chu kỳ

- Người đại diện nghiệp vụ trình bày các story đang ưu tiên và lý do.
- Developers nêu năng lực có thể sử dụng, các việc đang dở, rủi ro và phụ thuộc.
- Nhóm làm rõ acceptance criteria và giới hạn chất lượng.
- Hai phía chọn tập story vừa đủ; không ép công việc lấp đầy mọi phút.

### Trong chu kỳ

- Các Developers phối hợp, tích hợp liên tục, test-first/refactor khi phù hợp.
- Người hiểu nghiệp vụ có thể trả lời câu hỏi và đưa ví dụ chấp nhận kịp thời.
- Cả nhóm thấy sớm lỗi tích hợp, nhiệm vụ bị chặn và phạm vi cần làm rõ.
- Không đợi cuối chu kỳ mới thảo luận một điều có thể gây hại cho release.

### Kết thúc chu kỳ

- Xác nhận story nào thực sự đạt điều kiện chấp nhận và tiêu chuẩn chất lượng.
- Chạy kiểm thử tích hợp, xem phần mềm hoạt động và thu phản hồi phù hợp.
- Nêu rõ item còn dở, rủi ro còn lại và những giả định vừa được xác nhận/bác bỏ.
- Người quyết định nghiệp vụ cập nhật thứ tự ưu tiên; Developers cập nhật ước lượng và kế hoạch.

**Chu kỳ ngắn là điểm kiểm tra sự thật, không phải cơ chế tự động biến phần chưa đạt chất lượng thành Done.**

## 11. Acceptance tests và sự hiện diện của người hiểu nghiệp vụ

Một phần quan trọng của lập kế hoạch cộng tác là **làm rõ điều kiện để người dùng/nghiệp vụ chấp nhận story**. Developers có thể làm đúng đặc tả kỹ thuật nhưng vẫn giải quyết sai vấn đề nếu ví dụ nghiệp vụ chưa rõ.

### Ví dụ story

> “Là học viên đã đăng nhập và còn quyền học, tôi muốn mở lại đúng bài chưa hoàn thành từ trang khóa học để không phải tìm lại thủ công.”

**Acceptance criteria có thể trao đổi bằng ví dụ:**

~~~gherkin
Feature: Tiếp tục bài học đang dở

  Scenario: Học viên tiếp tục một bài đang học
    Given học viên đã đăng nhập và có quyền truy cập khóa học K
      And học viên đang học dở bài B và đã có vị trí lưu hợp lệ
    When học viên mở trang khóa học K và chọn "Học tiếp"
    Then hệ thống mở bài B tại vị trí đã lưu
      And không hiển thị dữ liệu tiến độ của tài khoản khác

  Scenario: Người dùng không còn quyền truy cập
    Given học viên không còn quyền truy cập khóa học K
    When học viên yêu cầu mở lại bài B
    Then hệ thống từ chối trả nội dung được bảo vệ
      And hiển thị trạng thái không thể truy cập phù hợp
~~~

Những ví dụ này có thể được **tự động hóa thành kiểm thử chấp nhận** khi phù hợp, nhưng quan trọng hơn là chúng khiến bên nghiệp vụ và kỹ thuật có **cùng cách hiểu về hành vi**. Chúng không thay thế mọi kiểm thử hiệu năng, bảo mật, khả năng phục hồi hoặc các tiêu chuẩn chất lượng chung.

### Ví dụ không nằm trong phạm vi đầu tiên

Người hiểu nghiệp vụ và Developers cùng ghi:

> “Release này chưa hỗ trợ học tiếp offline; khi kết nối bị mất, hệ thống phải phản hồi an toàn, không báo lưu thành công nếu chưa lưu.”

Nêu ranh giới rõ là **trung thực về khả năng sản phẩm**, không phải thiếu Agile. Người dùng cần biết hành vi nào đáng tin và hành vi nào sẽ được mở rộng sau.

## 12. Kỷ luật kỹ thuật giúp small releases trở nên an toàn

XP không chỉ nói “phát hành thường xuyên”. Nó cung cấp những thực hành giúp **mỗi thay đổi nhỏ được kiểm chứng nhanh và ít làm hỏng phần đã có**.

| Thực hành XP | Vòng phản hồi tạo ra | Hỗ trợ phát hành nhỏ thế nào? |
| --- | --- | --- |
| **Test-first / TDD** | Viết kiểm thử hành vi nhỏ trước khi triển khai, sửa mã rồi refactor | Phát hiện sớm hiểu sai quy tắc và giảm lỗi hồi quy |
| **Continuous Integration (CI)** | Tích hợp và kiểm tra thường xuyên mỗi thay đổi | Tránh dồn xung đột giao diện/API đến cuối release |
| **Refactoring / incremental design** | Cải thiện cấu trúc khi kiểm thử giữ hành vi ổn định | Không cần thiết kế trước tất cả biến thể mới có thể mở rộng |
| **Pair programming** | Phản hồi giữa hai người khi làm việc | Nhìn ra lỗi và lựa chọn thiết kế sớm, chia sẻ hiểu biết |
| **Shared code / coding conventions** | Thành viên cùng có khả năng sửa phần cần thiết theo quy tắc | Giảm chờ một cá nhân “sở hữu” duy nhất đoạn mã |
| **Small releases** | Phần mềm tới người dùng/đối tượng thử sớm | Đưa giả định giá trị vào kiểm chứng thực tế |
| **Energized work / sustainable pace** | Nhịp làm việc có thể duy trì | Giảm việc chạy nước rút liên tục làm suy giảm chất lượng lâu dài |

Các thực hành trên cần điều chỉnh theo hệ thống và yêu cầu vận hành thực tế. Pair programming không có nghĩa mọi phút đều phải có hai người gõ cùng một bàn phím; CI không bảo đảm đúng nghiệp vụ nếu bộ kiểm thử thiếu trường hợp quan trọng.

### TDD ở mức quy tắc nghiệp vụ

~~~text
Red:
  Nếu học viên đã hoàn thành bài B, "Học tiếp"
  không được đưa tới một vị trí dở giả của bài B.

Green:
  Viết mã tối thiểu để chọn bài hợp lệ theo quy tắc đã thống nhất.

Refactor:
  Làm rõ hàm chọn bài, giảm lặp,
  giữ mọi kiểm thử hành vi cũ vẫn đạt.

Tiếp tục:
  Thêm trường hợp chưa có tiến độ hoặc bài bị khóa
  theo ưu tiên, chất lượng và phạm vi đã được chốt.
~~~

Thực hành kỹ thuật tốt giúp nhóm **thay đổi ý tưởng ít tốn kém hơn**, từ đó việc cập nhật kế hoạch theo phản hồi trở nên khả thi.

## 13. Deployment, release và phản hồi giá trị không phải một mốc duy nhất

Các từ thường bị sử dụng lẫn nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Build / tích hợp** | Thay đổi đã hợp nhất và kiểm tra kỹ thuật chưa? | CI xanh cho luồng học tiếp |
| **Increment đạt chuẩn** | Phần mềm có hành vi hữu ích và chất lượng cần thiết chưa? | Luồng trên cùng thiết bị đạt kiểm thử chấp nhận và bảo mật |
| **Deploy** | Phiên bản đã được đưa tới môi trường nào? | Mã chạy trên production nhưng tính năng chưa bật |
| **Release / expose** | Người dùng nào được phép trải nghiệm khả năng mới? | Bật tính năng cho nhóm học viên thử nghiệm |
| **Outcome** | Người dùng có thực sự nhận được lợi ích không? | Tỷ lệ mở đúng bài và tiếp tục học có cải thiện |

**Deploy thường xuyên không tự đồng nghĩa release thường xuyên**, nhất là khi sản phẩm dùng feature flags. Một nhóm có thể đưa mã lên production nhưng bật dần cho từng nhóm người dùng để quan sát và giảm rủi ro. Ngược lại, không nên tuyên bố đã tạo giá trị cho người dùng nếu tính năng mới chỉ tồn tại ở môi trường staging.

### Chuỗi giao hàng an toàn

~~~mermaid
flowchart LR
    A["Story nhỏ + acceptance criteria"] --> B["Code, test-first,<br/>CI và review"]
    B --> C["Kiểm tra chất lượng<br/>và điều kiện bảo mật"]
    C --> D["Deploy an toàn"]
    D --> E["Release cho đối tượng<br/>phù hợp / bật tính năng"]
    E --> F["Quan sát người dùng,<br/>lỗi và hiệu quả"]
    F --> G["Thương lượng ưu tiên<br/>story tiếp theo"]
    G -.-> A
~~~

Nếu sản phẩm có quy định tuân thủ hoặc nguy cơ cao, cần thêm bằng chứng và phê duyệt phù hợp. Phát hành phần nhỏ giúp **giới hạn phạm vi thay đổi**, không cho phép bỏ quy tắc an toàn.

## 14. Các kỹ thuật giao tăng dần có kiểm soát

| Kỹ thuật | Mục đích | Điều kiện sử dụng có trách nhiệm |
| --- | --- | --- |
| **Feature flag** | Tách triển khai mã khỏi thời điểm bật tính năng | Phân quyền, dọn flag cũ, kiểm thử cả trạng thái bật/tắt, quan sát lỗi |
| **Canary / progressive rollout** | Thử với tỷ lệ/nhóm người dùng nhỏ rồi mở rộng | Có giám sát, tiêu chí dừng, khả năng rollback và tránh gây hại cho nhóm thử |
| **Lát cắt dọc** | Giao một hành vi hoàn chỉnh trước khi mở rộng biến thể | Có tiêu chí chấp nhận, test, dữ liệu, bảo mật và thông tin giới hạn |
| **Backward-compatible changes** | Thay đổi API/schema từng bước không phá phiên bản đang hoạt động | Thử tương thích và kế hoạch chuyển đổi dữ liệu khi cần |
| **Observability** | Biết tính năng có hoạt động và người dùng bị ảnh hưởng không | Log/metrics đủ dùng, bảo vệ quyền riêng tư, có người phản ứng khi cảnh báo |
| **Rollback / roll-forward** | Giảm tác động khi phát hành gây sự cố | Đánh giá trường hợp không thể rollback dễ dàng, nhất là dữ liệu |

Không phải mọi story đều cần feature flag hay canary; lựa chọn phải tương ứng mức rủi ro. Một tính năng chỉ dùng nội bộ có thể đơn giản hơn hệ thống thanh toán. Tuy nhiên, **kế hoạch phát hành phải trả lời được “Nếu sai thì chúng ta phát hiện và xử lý thế nào?”**.

### Vấn đề dữ liệu không thể chỉ dùng rollback mã

Nếu một release đã thay đổi cấu trúc dữ liệu hoặc ghi tiến độ sai, quay về phiên bản mã trước **không tự phục hồi dữ liệu**. Kế hoạch nhỏ và an toàn cần nghĩ tới migration, tương thích, sao lưu phù hợp, phát hiện dữ liệu hỏng và phương án khôi phục. Những việc này có thể là điều kiện để phát hành, không phải “để Sprint sau”.

## 15. Dự báo năng lực và thương lượng phạm vi trong XP

Planning Game cần có thông tin về khả năng thực hiện, nhưng **ước lượng không phải bản hợp đồng buộc nhóm phải làm mọi thứ bằng mọi giá**.

### Dùng dữ liệu lịch sử thế nào?

Nhóm có thể tham khảo:

- **Số story đạt Done** mỗi chu kỳ với kích thước/loại việc đủ nhất quán.
- **Throughput** và **cycle time** để nhận diện mức biến thiên của dòng công việc.
- **WIP / công việc đang dở** để biết có bao nhiêu năng lực bị giữ lại ở việc chưa hoàn thành.
- **Năng lực khả dụng** do nghỉ phép, sự cố, hỗ trợ người dùng, phụ thuộc hoặc việc học.
- **Chất lượng và rework**: pipeline có ổn định, có nhiều lỗi production hoặc làm lại không?

| Dữ liệu minh họa | Cách diễn giải hữu ích | Cách diễn giải sai |
| --- | --- | --- |
| Ba chu kỳ gần đây Done 4, 5, 3 story nhỏ | Có biến thiên, nên cân nhắc năng lực thực tế và phạm vi nhỏ | “Chu kỳ tới bắt buộc 4 story, không được khác” |
| Một story đang chờ kiểm thử 8 ngày | Có thể cần giải quyết tắc nghẽn thay vì kéo thêm việc | “Lập trình viên phải viết mã nhanh hơn” |
| Dự báo theo phạm vi có 80% xác suất đạt mốc | Đưa mức rủi ro vào quyết định ưu tiên và thời gian | “Đã hứa chắc chắn ngày đó” |
| Một bản phát hành nhỏ nhận phản hồi giá trị thấp | Cần học xem giả thuyết sai và có nên đổi hướng không | “Đã triển khai thì phải xây hết roadmap để khỏi phí” |

Các con số chỉ là **ví dụ**. Không có một chuẩn story point hoặc throughput áp dụng cho mọi nhóm. Đếm story chỉ hữu ích khi loại/kích thước công việc đủ tương đồng; story point nếu được dùng là quy ước nội bộ và **không nên dùng so sánh năng suất cá nhân**.

### Cố định thời gian, thương lượng phạm vi có trách nhiệm

Khi nhóm có chu kỳ ngắn cố định, cách tiếp cận phù hợp thường là **giữ nhịp phản hồi, lựa chọn lại phạm vi theo giá trị và rủi ro**, không tăng ca vô hạn để hoàn tất mọi việc đã nêu ban đầu. Chất lượng và các nghĩa vụ bắt buộc vẫn phải được duy trì.

Nếu có **deadline hợp đồng thực sự**, người quyết định nghiệp vụ và Developers phải làm rõ đánh đổi sớm: giảm những biến thể không bắt buộc, đổi giải pháp, tăng khả năng hỗ trợ hoặc thương lượng thời gian. Không thể tự ý bỏ điều kiện pháp lý, an toàn hoặc bảo mật chỉ vì muốn bảo vệ ngày hẹn.

## 16. Tình huống xuyên suốt: ba lần phát hành cho chức năng “Học tiếp”

Tình huống dưới đây là **ví dụ giảng dạy**. Thời gian, năng lực và kết quả giả định không phải chuẩn chung hay dữ liệu dự án thật.

### 16.1. Cuộc trao đổi ban đầu

**Người phụ trách sản phẩm:** “Chúng tôi muốn học viên tiếp tục bài học từ mọi thiết bị, tránh bỏ dở lộ trình. Tôi hy vọng có bản dùng được sớm.”

**Developer:** “Chúng tôi có thể giao sớm một luồng trên cùng thiết bị. Đồng bộ nhiều thiết bị có rủi ro ghi đè, nên cần kiểm chứng song song. Những quy tắc quyền truy cập và lưu tiến độ đúng phải có từ bản đầu.”

**Tester:** “Tôi sẽ cùng mọi người xác định ví dụ cho đang học, hoàn thành, hết quyền và dữ liệu không hợp lệ. Cần biết rõ nhánh nào đã được hứa trong bản đầu.”

**Người phụ trách sản phẩm:** “Vậy bản đầu ưu tiên học viên tìm lại bài đang dở; sau khi quan sát, chúng ta đánh giá luồng đổi thiết bị và quyết định mở rộng.”

Điểm cốt lõi là hai phía **cùng lựa chọn một kết quả có thể tạo ra và kiểm chứng**, thay vì chỉ hỏi mỗi người mất bao nhiêu ngày để hoàn thành toàn bộ epic.

### 16.2. Lộ trình release minh họa

| Release | Giá trị cho học viên | Story và rủi ro nổi bật | Bằng chứng để quyết định tiếp |
| --- | --- | --- | --- |
| **R1 — Học tiếp trong phạm vi hẹp** | Học viên đang học dở tìm lại bài ngay trên cùng thiết bị | UI–API–dữ liệu end-to-end; phân quyền và tính đúng đắn bắt buộc | Quan sát tác vụ, tỷ lệ mở đúng bài, sự cố tiến độ |
| **R2 — Tiếp tục trên thiết bị thứ hai** | Người học chuyển thiết bị mà vẫn thấy đúng tiến độ | Xác thực, đọc/ghi tiến độ nhất quán, kiểm chứng cập nhật cạnh tranh | Mức thành công khi đổi thiết bị, lỗi đồng bộ, thời gian chờ |
| **R3 — Trải nghiệm khi mạng gián đoạn** | Người học biết trạng thái lưu và phục hồi khi kết nối trở lại | Retry, xung đột dữ liệu, quan sát lỗi, giới hạn offline | Số lần mất dữ liệu, khả năng phục hồi, phản hồi từ người dùng ở mạng yếu |

Thứ tự có thể đổi khi dữ liệu cho thấy ưu tiên mới. **R1 không được phát hành nếu nó vi phạm quyền truy cập hoặc có nguy cơ mất dữ liệu trong phạm vi đã hứa**. R2 cũng không được bỏ kiểm thử xung đột chỉ vì muốn ra bản đúng lịch.

### 16.3. Lập kế hoạch cho R1

**Mục tiêu:** Học viên trở lại đúng bài đang học mà không phải tìm thủ công.

**Các story nhỏ được chọn:**

1. Học viên hợp lệ mở đúng bài đang dở từ trang khóa học.
2. Khi không có tiến độ, hệ thống hiển thị hành động bắt đầu hợp lệ nếu thuộc phạm vi R1.
3. Hệ thống ghi nhận hành vi và lỗi cần thiết để hiểu hiệu quả, có kiểm soát quyền riêng tư.

**Cách thực hiện:** Xác nhận ví dụ chấp nhận → xây một luồng API–UI tối thiểu → chạy kiểm thử tích hợp và bảo mật → quan sát trên môi trường phù hợp → phát hành hạn chế nếu an toàn.

**Ranh giới:** Không hứa đồng bộ offline hoặc multi-device trong R1. Phải kiểm soát quyền truy cập và phản hồi an toàn với dữ liệu không hợp lệ.

### 16.4. Thông tin mới giữa chu kỳ

Trong ngày thứ ba, Developers phát hiện khi học viên đổi bài nhanh, phiên cũ có thể ghi đè tiến độ mới. Đây là vấn đề **tính đúng đắn của phần đang xây**, không phải “ngoại lệ để làm sau”.

Nhóm chọn:

1. Tạm dừng phần UI trang trí để tái hiện lỗi.
2. Bổ sung kiểm thử chống ghi đè theo cơ chế dữ liệu được thống nhất.
3. Cặp Developers xử lý API và chạy CI.
4. Cập nhật dự báo R1, báo người quyết định sản phẩm nếu cần bớt biến thể không bắt buộc.
5. Chỉ phát hành khi tiêu chuẩn chất lượng cần thiết được đáp ứng.

Đây là **kế hoạch cộng tác thích ứng**: người hiểu nghiệp vụ quyết định ưu tiên giá trị, Developers quyết định cách xử lý kỹ thuật và cùng thương lượng phạm vi khi có bằng chứng mới.

### 16.5. Sau R1: không suy diễn từ “đã phát hành”

Giả sử trong một nhóm dùng thử nhỏ, nhiều học viên tìm thấy nút nhanh hơn, nhưng một số chưa biết “Học tiếp” sẽ mở ở vị trí nào. Nhóm cần:

- Xem mẫu thử có đại diện cho nhóm người dùng mục tiêu không.
- Tách cải thiện **khả dụng** khỏi tuyên bố **retention dài hạn** đã tăng.
- Giữ/đổi thiết kế dựa trên quan sát có căn cứ.
- Đánh giá R2 có thực sự là nhu cầu tiếp theo quan trọng nhất không.
- Kiểm tra lỗi dữ liệu, tính riêng tư và hiệu năng trước khi mở rộng.

Không nên dùng “đã ship R1” làm bằng chứng người dùng thích mọi phần còn lại trong roadmap.

### 16.6. Khi R2 khó hơn dự kiến

Nếu thử nghiệm cập nhật đồng thời cho thấy cơ chế đồng bộ gây mất tiến độ, một cách phản ứng phù hợp là **thu hẹp thử nghiệm hoặc giữ feature flag tắt**, hoàn thiện kiểm thử và xem lại dự báo. Không đánh dấu R2 hoàn tất chỉ vì giao diện giữa hai thiết bị đã hiển thị giống nhau.

### 16.7. Tổng kết câu chuyện

Ba lần phát hành là **ba cơ hội học và quản lý rủi ro**, chứ không phải ba mốc phân chia đều một danh sách code. Giá trị đến từ hành vi được sử dụng, chất lượng đáng tin và quyết định ưu tiên tiếp theo được cải thiện.

## 17. Giảm phụ thuộc tổ chức để duy trì vòng phản hồi ngắn

Ngay cả khi Developers áp dụng TDD và CI, việc phát hành vẫn có thể chậm nếu phải chờ môi trường, phê duyệt hoặc thông tin từ bộ phận khác. Lập kế hoạch cộng tác cần nhìn cả **chuỗi tạo giá trị end-to-end**.

### Các phụ thuộc thường làm vòng học kéo dài

| Phụ thuộc | Dấu hiệu | Hành động phối hợp |
| --- | --- | --- |
| **Thông tin nghiệp vụ** | Developers chờ nhiều ngày mới biết một quy tắc | Bố trí người có quyền quyết định tham gia thường xuyên; dùng ví dụ chấp nhận rõ |
| **Thiết kế và nghiên cứu người dùng** | Tính năng xây xong mới phát hiện luồng không sử dụng được | Trao đổi mẫu thử sớm, quan sát tác vụ với người dùng phù hợp |
| **Môi trường kiểm thử** | Hằng tuần có thể mất nhiều ngày chờ staging | Cải thiện quyền truy cập an toàn, dữ liệu thử và cấp môi trường |
| **API/hệ thống khác** | Tích hợp thất bại vào sát ngày release | Thống nhất contract sớm, kiểm tra tương thích, giữ liên lạc giữa nhóm |
| **Bảo mật/tuân thủ** | Chỉ đánh giá an toàn sau khi mã đã hoàn thiện | Đưa chính sách bắt buộc vào thiết kế, test và kế hoạch ngay từ đầu |
| **Triển khai/quan sát** | Có mã chạy nhưng không biết ai dùng, lỗi ra sao | CI/CD phù hợp, khả năng theo dõi, rollback và trách nhiệm vận hành rõ |

Người quản lý tổ chức có vai trò **bảo vệ năng lực nhóm, tháo phụ thuộc và cho phép giao an toàn**, không nên tự chiếm quyền lựa chọn giải pháp kỹ thuật hoặc ưu tiên nghiệp vụ.

### Không nhầm “nhóm đa chức năng” với “ai cũng làm mọi việc”

Để phát hành theo phần nhỏ, nhóm cần **truy cập được** các năng lực đủ cho một lát cắt end-to-end: hiểu nhu cầu, phát triển, kiểm thử, thiết kế và vận hành. Không có nghĩa một người phải thành thạo tất cả. Lập trình cặp, review và làm việc cùng người có chuyên môn giúp giảm thời gian chờ mà vẫn giữ chất lượng.

## 18. Đo lường để học: giao nhanh có thật sự tạo giá trị?

Một nhóm có thể tăng số lần deploy nhưng đồng thời tăng lỗi. Một nhóm khác đóng nhiều ticket hơn nhờ tách vụn việc, trong khi người dùng vẫn phải chờ một luồng sử dụng được. Vì thế cần đo **flow, chất lượng và giá trị**, không chỉ số lần phát hành.

| Nhóm chỉ số | Ví dụ | Câu hỏi cần trả lời | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Dòng công việc** | Throughput, cycle time, WIP, work item age | Công việc bị chặn ở đâu? Lát cắt đạt Done nhanh hơn không? | So sánh số ticket khi cách chia item khác nhau |
| **Khả năng giao thay đổi** | Thời gian đưa thay đổi đến môi trường dùng, tần suất triển khai | Vòng phản hồi kỹ thuật/phát hành nhanh tới đâu? | Ép tăng số deploy mà bỏ qua an toàn |
| **Chất lượng** | Lỗi hồi quy, lỗi production, sự cố dữ liệu, thời gian phục hồi | Thay đổi nhỏ có thật sự giữ phần mềm đáng tin? | Đóng lỗi sớm để số liệu đẹp |
| **Phản hồi sản phẩm** | Hoàn thành tác vụ, tỷ lệ mở đúng bài, thời gian tìm bài, phản hồi định tính | Giải pháp có giúp người học đạt mục tiêu không? | Dùng số click làm bằng chứng chắc chắn về giá trị |
| **Sức khỏe đội ngũ** | Gián đoạn, làm thêm giờ, mức quá tải, thời gian học | Nhịp lập kế hoạch và release có bền vững không? | Coi “bận 100%” là tối ưu |

### Ví dụ nhìn số liệu có bối cảnh

Giả sử trong bốn tuần:

- Nhóm deploy từ một lần/tháng thành nhiều lần/tuần.
- Cycle time của story nhỏ giảm.
- Nhưng lỗi mất tiến độ từ người dùng tăng rõ sau phát hành.

Không thể kết luận “XP thành công vì deploy thường xuyên”. Cần điều tra kiểm thử đồng bộ, cách rollout, dữ liệu và điều kiện release. **Chất lượng là một phần của năng lực giao nhanh**, không phải mục tiêu có thể bỏ qua để đạt tốc độ.

### Phân biệt số đo theo loại đơn vị

Nếu trước đây một story chứa toàn bộ luồng “Học tiếp”, còn bây giờ chia thành mười ticket kỹ thuật, throughput tính theo ticket có thể tăng mạnh mà **thời gian tới giá trị người dùng không đổi**. Khi đo, cần giữ nhất quán định nghĩa work item và ranh giới Done; công bố mọi thay đổi cách đếm.

## 19. XP liên hệ với Scrum và Kanban như thế nào?

XP, Scrum và Kanban có thể được dùng bổ sung nhau, nhưng **không phải tên gọi thay thế**.

| Khía cạnh | Extreme Programming (XP) | Scrum | Kanban |
| --- | --- | --- | --- |
| **Trọng tâm** | Phối hợp gần khách hàng và kỹ thuật để xây, kiểm thử, giao thay đổi nhỏ | Scrum Team tạo giá trị theo Sprint, mục tiêu và kiểm tra/thích ứng | Định nghĩa, điều hành và cải tiến luồng công việc |
| **Cách lập kế hoạch** | Planning Game, lựa chọn story qua thương lượng nghiệp vụ–kỹ thuật, chu kỳ ngắn | Sprint Planning với Why–What–How, Product Backlog và Sprint Goal | Chính sách pull/replenishment, ưu tiên và giới hạn WIP |
| **Cách phản hồi** | Test-first, CI, người hiểu nghiệp vụ, small releases | Daily Scrum, Sprint Review, Sprint Retrospective và học hỏi trong Sprint | Flow metrics, WIP, SLE và các vòng feedback |
| **Chất lượng** | Thực hành kỹ thuật rất rõ: TDD, refactoring, pair programming, CI | Increment phải đạt Definition of Done; framework không quy định TDD | Chất lượng được biểu diễn bằng tiêu chuẩn, chính sách Done và thông tin luồng |
| **Nhịp** | Có thể lập kế hoạch theo tuần hoặc chu kỳ được chọn | Sprint cố định, không quá một tháng | Có thể kéo việc liên tục, nhịp kiểm tra theo nhu cầu |

### Kết hợp trong một nhóm Scrum

Nhóm có thể dùng **Sprint Planning** để thống nhất Sprint Goal, Developers chọn PBIs cùng Product Owner, rồi sử dụng **TDD, CI, pair programming và refactoring** theo XP để tạo Increment nhỏ đạt Done. Trong Sprint, nhóm có thể dùng **WIP và work item age** của Kanban để tránh mở quá nhiều việc và nhận biết điểm nghẽn.

Việc dùng XP **không xóa bỏ** trách nhiệm Product Owner, Developers và Scrum Master khi nhóm đang thực hiện Scrum. Các thực hành Kanban cũng không thay thế Sprint Goal. Mỗi thực hành phục vụ một câu hỏi cụ thể: **giá trị gì, làm cách nào an toàn, công việc đang chảy ra sao, có thể học gì tiếp?**

### Nhóm Kanban không bắt buộc có Sprint để dùng XP

Một nhóm hỗ trợ sản phẩm có thể dùng workflow Kanban kéo việc liên tục, nhưng mỗi thay đổi vẫn được test-first, tích hợp và phát hành theo phần nhỏ. Nhóm cần cơ chế làm rõ giá trị và trách nhiệm nghiệp vụ; **không nhất thiết tổ chức Sprint Planning nếu không theo Scrum**.

## 20. Những phản mẫu thường gặp

### 20.1. Chỉ định ngày phát hành trước, rồi ép ước lượng khớp ngày

**Hệ quả:** Developers thiếu động lực báo rủi ro, dễ bỏ kiểm thử hoặc che việc còn dở.  
**Cải thiện:** Làm rõ ngày mong muốn là mục tiêu hay nghĩa vụ, trình bày dự báo có điều kiện, thương lượng phạm vi theo giá trị và bảo vệ chuẩn chất lượng.

### 20.2. Người nghiệp vụ viết hết giải pháp, Developers chỉ nhận task

**Hệ quả:** Thiếu phản hồi kỹ thuật sớm và ít khả năng tìm lát cắt đơn giản.  
**Cải thiện:** Người nghiệp vụ xác định vấn đề và ưu tiên; Developers tham gia phân tích khả thi, lựa chọn giải pháp và rủi ro.

### 20.3. Developers tự quyết định ưu tiên vì “biết kỹ thuật hơn”

**Hệ quả:** Backlog chạy theo điều thú vị hoặc dễ lập trình, xa người dùng.  
**Cải thiện:** Trao đổi bằng bằng chứng, minh bạch chi phí; quyền quyết định giá trị nằm ở người chịu trách nhiệm nghiệp vụ.

### 20.4. Chia release thành các tầng UI/API/database

**Hệ quả:** Mỗi đợt có thể hoàn tất task nhưng người dùng chưa nhận được hành vi có ích.  
**Cải thiện:** Chia thành **lát cắt dọc** đi qua những tầng cần thiết và đạt kiểm thử chấp nhận.

### 20.5. Lập kế hoạch quá chi tiết cho nhiều tháng khi chưa có phản hồi

**Hệ quả:** Cảm giác chắc chắn giả, chi phí duy trì kế hoạch cao.  
**Cải thiện:** Giữ hướng mục tiêu, mốc học và thứ tự tương đối ở chân trời xa; chi tiết hóa công việc ở chân trời gần.

### 20.6. Gọi mọi thay đổi hằng ngày là small release có giá trị

**Hệ quả:** Đếm deploy/build rồi tuyên bố thành công dù tính năng chưa bật hoặc chưa có người dùng.  
**Cải thiện:** Phân biệt build, deploy, release, Increment và outcome; đo đúng sự kiện cần học.

### 20.7. Giảm kiểm thử để tăng tần suất phát hành

**Hệ quả:** Lỗi hồi quy và sự cố dữ liệu tăng, cuối cùng làm vòng học chậm hơn.  
**Cải thiện:** Test-first, CI, review, tự động hóa có giá trị, cơ chế rollout và khôi phục phù hợp.

### 20.8. Chỉ làm các story dễ để “velocity” tăng

**Hệ quả:** Chậm xử lý rủi ro giá trị và kỹ thuật lớn.  
**Cải thiện:** Sắp xếp theo giá trị, mức bất định, phụ thuộc và hậu quả; không dùng story point để xếp hạng cá nhân.

### 20.9. Mọi thứ đều “khẩn”, không có chỗ cho công việc chất lượng

**Hệ quả:** Kế hoạch liên tục bị chen ngang; nợ kỹ thuật và lỗi tích lũy.  
**Cải thiện:** Chính sách ưu tiên rõ, năng lực cho sự cố và cải tiến, hạn chế WIP và minh bạch đánh đổi.

### 20.10. Nhận phản hồi nhưng vẫn giữ nguyên roadmap

**Hệ quả:** Phát hành nhiều phần nhỏ mà không học được gì; chỉ chia nhỏ cách xây sai.  
**Cải thiện:** Mỗi release có câu hỏi giá trị, số liệu hoặc quan sát, người ra quyết định và hành động cập nhật ưu tiên.

### 20.11. Dùng spike để kéo dài thời gian nghiên cứu vô hạn

**Hệ quả:** Có nhiều tài liệu kỹ thuật nhưng thiếu phần mềm sử dụng được.  
**Cải thiện:** Đặt giới hạn thời gian, câu hỏi, điều kiện đủ bằng chứng; sau spike phải quyết định thực hiện lát cắt, thử thêm vấn đề hẹp hoặc dừng.

### 20.12. Coi một bản thử hẹp là giấy phép làm sai với người dùng

**Hệ quả:** Phát hành cho “ít người” nhưng có nguy cơ lộ dữ liệu hoặc thu phí sai.  
**Cải thiện:** Giới hạn phạm vi tính năng và đối tượng thử, nhưng vẫn bảo vệ an toàn, tính đúng đắn và quyền riêng tư.

## 21. Workshop: lập một kế hoạch XP trong 60 phút

Đây là **bài thực hành minh họa**, không phải thời lượng chính thức bắt buộc của XP.

| Giai đoạn | Thời lượng gợi ý | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Mục tiêu và đối tượng** | 10 phút | Người phụ trách sản phẩm giải thích nhu cầu, giá trị và ràng buộc | Mục tiêu sản phẩm, giả thuyết cần học |
| **2. Story mapping nhanh** | 10 phút | Cùng vẽ luồng chính, nhánh thay thế, điều kiện biên | Bản đồ những hành vi có thể giao |
| **3. Chia lát cắt nhỏ** | 10 phút | Developers và nghiệp vụ tách theo luồng, quy tắc, rủi ro | Danh sách story dọc có thể kiểm chứng |
| **4. Khả năng thực hiện** | 10 phút | Developers nêu ước lượng, năng lực, phụ thuộc, điều kiện chất lượng | Rủi ro và dự báo có điều kiện |
| **5. Chọn release đầu** | 10 phút | Người nghiệp vụ ưu tiên, cả nhóm thương lượng phạm vi | Tập story tạo hành vi dùng được, ranh giới rõ |
| **6. Kế hoạch phản hồi** | 10 phút | Xác định kiểm thử, triển khai, phép đo, mốc điều chỉnh | Kế hoạch thực hiện và học từ người dùng |

**Cách đánh giá workshop:** Kết quả tốt không phải nhiều thẻ nhất. Nhóm phải trả lời được:

- Người dùng nhận được **hành vi hoàn chỉnh nào** sau release đầu?
- Điều kiện chất lượng nào bắt buộc và ai xác nhận?
- Rủi ro lớn nhất là gì, làm thế nào biết sớm?
- Nếu capacity thấp hơn dự báo, có thể hoãn **biến thể nào** mà vẫn giữ giá trị?
- Khi bản đầu được dùng, **bằng chứng nào** quyết định release sau?

## 22. Bài tập tình huống và gợi ý

### Bài tập A — Ai nên quyết định điều gì?

Trong Planning Game:

1. Bên kinh doanh muốn xây email nhắc học trước, nhưng phỏng vấn cho thấy học viên thường không tìm lại được bài.
2. Developers phát hiện đồng bộ offline có rủi ro ghi đè dữ liệu.
3. Người quản lý yêu cầu mọi người nhận thêm 30% story point vì “chu kỳ trước quá ít”.
4. Tester phát hiện thiếu kịch bản hết quyền truy cập.

Hãy phân loại quyết định về **giá trị/thứ tự ưu tiên**, **giải pháp/ước lượng kỹ thuật**, **chất lượng bắt buộc** và **quyết định tổ chức**, rồi đề xuất cách thảo luận.

**Gợi ý:** Người chịu trách nhiệm sản phẩm phải xem lại ưu tiên dựa trên người dùng; Developers đánh giá rủi ro và đề xuất cách làm; phân quyền là yêu cầu cần đáp ứng, không phải mục tùy chọn; mục tiêu story point không thay thế năng lực thực.

### Bài tập B — Chia epic thành ba lần phát hành

Epic: “Là người mua hàng, tôi muốn sử dụng mã giảm giá trong quá trình thanh toán để trả đúng số tiền được ưu đãi.”

Hãy đề xuất **ba lát cắt có giá trị**, ví dụ:

1. Áp một loại mã hợp lệ theo quy tắc cơ bản, thể hiện số tiền sau giảm chính xác.
2. Bổ sung một nhóm quy tắc giảm giá khác và thông báo lỗi có ích.
3. Bổ sung trường hợp dùng một lần hoặc xung đột khi nhiều giao dịch cạnh tranh, **nếu các trường hợp đó chưa thể xảy ra trong phạm vi release đầu**.

**Điều kiện quan trọng:** Nếu ngay release đầu đã có mã dùng một lần hoặc nguy cơ tính tiền sai, **không được trì hoãn kiểm soát đó**. Hãy nêu rõ trạng thái nào được phép thử, cách đảm bảo tính đúng đắn và vì sao lát cắt đầu có thể giao an toàn.

### Bài tập C — Chọn release khi năng lực hạn chế

Nhóm có sáu story ưu tiên, ba chu kỳ trước lần lượt Done 3, 5 và 4 story nhỏ, nhưng chu kỳ tới hai người phải hỗ trợ sự cố. Một story có phụ thuộc API chưa chắc chắn.

Hãy:

- Chọn **một tập story có giá trị** cho release/chu kỳ trước mắt.
- Giải thích vì sao lịch sử 3, 5, 4 không có nghĩa chắc chắn làm được bốn story.
- Đề xuất cách xử lý phụ thuộc hoặc một timeboxed spike có câu hỏi cụ thể.
- Nêu cách thương lượng nếu Product Owner vẫn cần một hạn chót kinh doanh.

**Gợi ý:** Dự báo dựa trên capacity thực, ưu tiên lát cắt nhỏ đạt Done, giữ thời gian cho chất lượng và điều chỉnh theo dữ liệu mới.

### Bài tập D — Lập tiêu chí chấp nhận và kế hoạch giao an toàn

Story: “Học viên đã đăng nhập có thể tiếp tục bài đang dở từ trang khóa học”.

Viết ít nhất ba ví dụ Given–When–Then bao gồm:

1. Có quyền học và có vị trí lưu hợp lệ.
2. Không còn quyền truy cập.
3. Dữ liệu tiến độ không hợp lệ hoặc đã cũ.

Sau đó xác định các kiểm thử kỹ thuật bổ sung, điều kiện release, chỉ số giám sát và cách thu phản hồi người dùng. Tránh chỉ dùng một bài kiểm thử UI thành công để kết luận hệ thống đủ an toàn.

### Bài tập E — Khi phản hồi bác bỏ giả định

R1 đã được phát hành an toàn cho một nhóm nhỏ. Kết quả: người học tìm bài nhanh hơn nhưng tỷ lệ quay lại sau bảy ngày chưa cải thiện rõ; nhiều người đề cập khó tìm bài phù hợp tiếp theo.

Bạn sẽ làm gì với kế hoạch R2/R3?

**Gợi ý:** Kiểm tra độ tin cậy và cửa sổ dữ liệu, nghiên cứu hành vi thực tế, xem nhu cầu mới có quan trọng hơn đồng bộ đa thiết bị hay không. Người phụ trách giá trị cùng Developers thương lượng ưu tiên thay vì tiếp tục roadmap vì đã lên lịch. Không suy từ một mẫu nhỏ rằng toàn bộ người dùng có cùng hành vi.

## 23. Checklist cho kế hoạch cộng tác và release nhỏ

- [ ] Đã xác định **người dùng, vấn đề và giá trị cần kiểm chứng**, không chỉ danh sách tính năng.
- [ ] Có người **đưa quyết định nghiệp vụ kịp thời**, được hỗ trợ bằng phản hồi thật từ người dùng.
- [ ] Developers có quyền nói rõ ước lượng, rủi ro, phụ thuộc, năng lực và phương án kỹ thuật.
- [ ] Quyết định giá trị và cách thực hiện được **thương lượng**, không áp đặt một chiều.
- [ ] Một yêu cầu lớn được tách thành **user story dọc**, không chỉ ticket UI/API/database rời rạc.
- [ ] Mỗi release đầu tạo **hành vi sử dụng được** và có thể học được điều mới.
- [ ] Phạm vi chưa hỗ trợ được công bố rõ; không hứa tính năng tổng quát khi mới hỗ trợ một trường hợp.
- [ ] Quy tắc bắt buộc về **phân quyền, dữ liệu, bảo mật, tính đúng đắn và tuân thủ** không bị hoãn sai.
- [ ] Có **acceptance criteria** và kiểm thử có thể kiểm tra hành vi.
- [ ] CI, test-first/TDD, review/cặp lập trình, refactoring và tích hợp được xem là phần năng lực giao hàng.
- [ ] Kế hoạch deploy/release có điều kiện giám sát và xử lý sự cố phù hợp.
- [ ] Đã phân biệt **Increment, deploy, release và outcome**.
- [ ] Người dùng được tiếp xúc với phần mềm sớm trong phạm vi an toàn để đưa phản hồi.
- [ ] Kế hoạch nhiều tuần ghi **giả định và mốc học**, còn kế hoạch gần đủ chi tiết để hành động.
- [ ] Throughput/cycle time được đọc đúng ngữ cảnh; không ép story points thành KPI cá nhân.
- [ ] Có cơ chế điều chỉnh **thứ tự ưu tiên, phạm vi, giải pháp hoặc thời điểm** theo bằng chứng.
- [ ] Không tuyên bố Done hoặc phát hành nếu kiểm thử bắt buộc chưa đạt.
- [ ] Có cách giữ nhịp làm việc bền vững và giảm phụ thuộc gây chậm vòng phản hồi.
- [ ] Sau mỗi release, có **quyết định kế tiếp**: mở rộng, cải tiến, tìm hiểu thêm hoặc dừng.

## 24. Tài liệu đọc tiếp và tổng kết

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị và nguyên tắc về giao phần mềm sớm, hợp tác khách hàng, phản hồi và thích ứng.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): giá trị XP, Stories, Weekly Cycle, Quarterly Cycle, Test-First Programming, Continuous Integration, Pair Programming và Incremental Design.
- Kent Beck, *Extreme Programming Explained: Embrace Change* (1999): thực hành và tư duy XP thời kỳ đầu, gồm Planning Game, Small Releases và kiểm thử.
- [The Scrum Guide](https://scrumguides.org/): Product Backlog, Sprint Goal, Sprint Backlog, Increment và Definition of Done; tham khảo khi nhóm kết hợp XP với Scrum.
- [The Kanban Guide](https://kanbanguides.org/): workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- Jeff Patton, *User Story Mapping* (2014): xây bản đồ hành trình để nhận diện các lát cắt phát hành có giá trị.
- Jez Humble và David Farley, *Continuous Delivery* (2010): các năng lực kiểm thử, tích hợp, triển khai và quản trị rủi ro giúp phần mềm sẵn sàng giao thường xuyên.

**Điểm cốt lõi:** Lập kế hoạch cộng tác trong XP đưa **người chịu trách nhiệm giá trị** và **những người thực hiện** vào cùng một quá trình lựa chọn dựa trên bằng chứng. Phát hành theo phần nhỏ đưa **một hành vi thật, đủ chất lượng** đến người dùng sớm để kiểm chứng giả định. Hai việc chỉ thực sự hỗ trợ Agile khi được nối bằng **kỷ luật kỹ thuật, phạm vi minh bạch, phản hồi đáng tin và khả năng thay đổi kế hoạch**. Mục tiêu không phải số lần phát hành hay số ticket Done cao nhất, mà là **giao giá trị bền vững và học nhanh với chi phí rủi ro có thể kiểm soát**.
