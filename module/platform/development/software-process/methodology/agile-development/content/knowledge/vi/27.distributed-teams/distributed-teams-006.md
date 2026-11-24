# Lưu trữ kiến thức để hỗ trợ thành viên mới và người vắng mặt

Một nhóm Agile phát triển nền tảng đăng ký workshop với thành viên làm việc ở nhiều địa điểm và múi giờ. Người hiểu rõ cơ chế giữ chỗ cuối cùng chuẩn bị nghỉ phép hai tuần. Đúng lúc đó, một Developer mới gia nhập, hệ thống đăng ký xuất hiện lỗi “đã xác nhận nhưng vẫn báo còn chỗ” và Product Owner cần đổi ưu tiên. Cả nhóm biết rằng các cuộc trao đổi quan trọng đã từng diễn ra, nhưng thông tin nằm rải rác trong tin nhắn riêng, cuộc họp không ghi quyết định, những đường dẫn cũ và trí nhớ của một người.

Vấn đề không đơn thuần là **thiếu tài liệu**. Nhóm thiếu **khả năng chuyển giao ngữ cảnh có thể tìm thấy, đáng tin và đủ để hành động**. Một tài liệu dài nhưng lỗi thời hoặc không ai biết ở đâu cũng không giúp người mới tiến bộ hơn. Ngược lại, một bộ hướng dẫn ngắn, quyết định có lý do, bản đồ hệ thống và quy trình xử lý sự cố được kiểm tra định kỳ có thể giảm rất nhiều sự phụ thuộc vào cá nhân.

Trong chương **Nhóm phân tán** thuộc module **AGILE_DEVELOPMENT**, bài này trình bày cách **lưu trữ và duy trì kiến thức như một phần của dòng công việc Agile**. Mục tiêu không phải viết mọi thứ thành một kho văn bản đồ sộ, mà là bảo đảm **thông tin quan trọng có thể được người khác tìm, hiểu, kiểm chứng và dùng để tiếp tục giao sản phẩm tăng dần**, ngay khi người sở hữu ban đầu chưa trực tuyến hoặc vắng mặt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **kiến thức ngầm, kiến thức được ghi lại và kiến thức cần được thực hành** trong nhóm phân tán.
2. Nhận diện rủi ro khi quyết định, thao tác vận hành hoặc ngữ cảnh sản phẩm chỉ nằm trong tin nhắn/cuộc họp của một người.
3. Tổ chức một **điểm bắt đầu dễ tìm** để thành viên mới xác định đúng tài liệu, môi trường, trách nhiệm và đường liên hệ.
4. Biết khi nào nên dùng **README, hướng dẫn bắt đầu, sơ đồ hệ thống, ADR, runbook, decision log, FAQ và handoff note**.
5. Viết một bản bàn giao bất đồng bộ giúp người vắng mặt có thể trở lại hoặc người thay thế tiếp tục công việc an toàn.
6. Liên kết cập nhật kiến thức với **user story, Product Backlog, Definition of Done hoặc chính sách hoàn tất phù hợp**, mà không tạo quy trình quan liêu.
7. Thiết kế cơ chế **quyền sở hữu, ngày xem lại, phiên bản và thông báo thay đổi** để giảm tài liệu lỗi thời.
8. Bảo vệ thông tin nhạy cảm, phân quyền truy cập và tôn trọng việc nghỉ phép/ngoài giờ của đồng đội.
9. Dùng những thử nghiệm nhỏ để xem kiến thức có thực sự giúp onboarding, giảm thời gian chờ và duy trì chất lượng hay không.

## 2. Vì sao kiến thức dễ thất lạc trong nhóm phân tán?

Ở nhóm cùng địa điểm, một người có thể quay sang hỏi đồng nghiệp. Trong nhóm phân tán, sự khác biệt về **múi giờ, lịch làm việc, ngôn ngữ, kết nối mạng và khả năng tham gia họp** khiến câu hỏi “ai biết việc này?” có thể mất nhiều giờ hoặc nhiều ngày mới được trả lời.

Các tình huống dễ xảy ra:

- **Người giữ ngữ cảnh đang ngủ:** Một thay đổi API được thống nhất trong cuộc họp ở múi giờ khác.
- **Thành viên nghỉ phép:** Không ai biết vì sao giao dịch cần một ràng buộc dữ liệu đặc biệt.
- **Người mới gia nhập:** Có nhiều tài liệu nhưng không rõ nên bắt đầu từ trang nào.
- **Thay đổi sản phẩm nhanh:** Quyết định ưu tiên trong backlog đã đổi nhưng ghi chú onboarding chưa cập nhật.
- **Kênh trao đổi phân mảnh:** Lý do thiết kế ở chat, mã nguồn ở Git, hướng dẫn deploy ở wiki, lỗi ở hệ thống ticket.
- **Rủi ro phân quyền:** Người thay thế biết phải làm gì nhưng không có quyền xem log, mở runbook hoặc chạy quy trình khôi phục.
- **Áp lực tiến độ:** Mọi người chỉ ghi “đã sửa” mà không lưu cách tái hiện, nguyên nhân và test để phòng lỗi quay lại.

### 2.1. Tài liệu giúp loại bỏ độ trễ thông tin, không thay thế hợp tác

Viết tài liệu không phải cách phủ nhận **“Individuals and interactions over processes and tools”** trong Agile Manifesto. Một ghi chú đúng chỗ có thể **nâng chất lượng tương tác**: đồng đội đọc trước, hỏi điều còn mơ hồ và dành thời gian trao đổi cho vấn đề mới thay vì hỏi lại những điều đã được trả lời.

**Ưu tiên con người và tương tác** không có nghĩa mọi kiến thức phải truyền miệng. **Ưu tiên phần mềm hoạt động** cũng không có nghĩa bỏ hướng dẫn cần thiết để người khác xây, kiểm thử hoặc phục hồi hệ thống an toàn.

### 2.2. Ví dụ: cùng một câu hỏi, hai kết quả

| Cách làm | Tình huống khi người hiểu hệ thống vắng mặt | Hệ quả |
| --- | --- | --- |
| Quyết định chỉ trong chat cá nhân | Người mới hỏi “vì sao không retry thao tác giữ chỗ?” nhưng không có người trả lời | Chờ đợi hoặc thử giải pháp nguy hiểm |
| Quyết định có ADR, test, liên kết mã | Người mới đọc lý do tránh xác nhận trùng, biết giả định và kiểm chứng | Có thể tiếp tục làm việc và hỏi đúng điểm còn chưa rõ |
| Quy trình deploy chỉ nằm trong trí nhớ | Người trực thay không biết ngưỡng dừng | Tăng rủi ro khi phát hành |
| Runbook có điều kiện, quyền, tác động và cách rollback | Người trực thay đánh giá đúng tình huống và biết khi nào escalates | Phản ứng an toàn, tránh thao tác đoán mò |

## 3. Ba dạng kiến thức cần quan tâm

### 3.1. Kiến thức ngầm (*tacit knowledge*)

Là hiểu biết tích lũy qua kinh nghiệm: vì sao một hướng tiếp cận không hiệu quả, khi nào cần cảnh giác với một pattern lỗi, người dùng thực tế thường xử lý thế nào. Nó khó được chuyển đầy đủ chỉ bằng một văn bản.

Ví dụ: một Developer nhiều kinh nghiệm nhận ra rằng lỗi đăng ký trùng thường phát sinh khi hai service cập nhật sức chứa với giả định sai về transaction.

### 3.2. Kiến thức đã được diễn đạt (*explicit knowledge*)

Là thông tin có thể ghi và tra cứu: quyết định kiến trúc, chính sách quyền, ví dụ nghiệp vụ, cách chạy test, các bước release và liên hệ trách nhiệm.

Ví dụ: ADR mô tả lựa chọn ràng buộc dữ liệu, bài test đồng thời và điều kiện để xem lại quyết định.

### 3.3. Kiến thức được kiểm chứng trong thực hành

Một người đọc runbook có thể hiểu mô tả, nhưng **chưa chắc làm đúng trong sự cố thật**. Kiến thức quan trọng cần **được thử trong môi trường phù hợp**, dùng pairing, game day hoặc thực hành có giám sát.

Ví dụ: trước kỳ nghỉ của người trực chính, người dự phòng thử quy trình chẩn đoán lỗi ở môi trường an toàn, kiểm tra quyền truy cập và xác nhận các bước không còn lỗi thời.

### 3.4. Không cố biến mọi kiến thức ngầm thành trang tài liệu

Kỹ năng phán đoán thiết kế, giao tiếp với stakeholder và xử lý tình huống mới vẫn cần:

- Pair programming, review và shadowing.
- Buổi trao đổi có ghi lại quyết định chính.
- Luân phiên thực hiện những tác vụ có mức rủi ro phù hợp.
- Phản hồi sau khi thử làm thật.

**Kho kiến thức là một phần của hệ thống học hỏi**, không phải bản sao hoàn hảo của kinh nghiệm con người.

## 4. Năm phẩm chất của kiến thức có thể sử dụng

Một trang “đã tồn tại” chưa chắc hữu ích. Khi đánh giá tài liệu, hãy hỏi:

| Phẩm chất | Câu hỏi kiểm tra | Dấu hiệu tốt |
| --- | --- | --- |
| **Dễ tìm (findable)** | Người chưa biết tên người sở hữu có tìm đúng nội dung được không? | Điểm vào rõ, tiêu đề tốt, từ khóa, liên kết từ repo/backlog |
| **Đúng và có ngữ cảnh (trustworthy)** | Nội dung áp dụng cho phiên bản/môi trường nào? | Nguồn sự thật, owner, ngày kiểm tra, trạng thái hiệu lực |
| **Đủ để hành động (actionable)** | Người đọc biết bước tiếp theo, điều kiện và giới hạn không? | Lệnh, điều kiện trước, tiêu chí thành công, cảnh báo và đường trợ giúp |
| **Phù hợp người đọc (accessible)** | Người mới có hiểu thuật ngữ, quyền và bối cảnh không? | Giải thích ngắn, ví dụ, bố cục dễ quét, ngôn ngữ rõ |
| **Duy trì được (maintainable)** | Khi hệ thống đổi, có ai cập nhật được không? | Chủ sở hữu, review qua PR, kiểm tra liên kết và lịch xem lại |

### 4.1. Tài liệu cần trả lời “vì sao” và “khi nào”, không chỉ “làm gì”

Một lệnh chạy database migration thiếu điều kiện **không đủ an toàn**. Người mới cần biết:

- Lệnh dùng trên môi trường nào?
- Khi nào **không** được chạy?
- Cần quyền, backup hoặc phê duyệt nào?
- Làm sao xác nhận thành công?
- Nếu thất bại, ai có thẩm quyền quyết định khôi phục?

### 4.2. “Càng nhiều trang càng tốt” là mục tiêu sai

Nếu mỗi PR phải viết ba trang không ai đọc, tài liệu sẽ trở thành gánh nặng và lỗi thời. Thay vì đếm số trang, hãy đo **người cần kiến thức có tự tìm được câu trả lời đúng và thực hiện an toàn không**.

## 5. Bản đồ dòng tri thức trong một nhóm Agile

Kiến thức hình thành từ phản hồi của người dùng, cuộc trao đổi backlog, quyết định kỹ thuật, kiểm thử và vận hành. Nó cần đi về nơi **người tiếp theo sẽ tìm**.

~~~mermaid
flowchart TD
    A["Nhu cầu người dùng / Product Backlog"] --> B["Trao đổi và ví dụ chấp nhận"]
    B --> C["Quyết định kiến trúc, quy tắc nghiệp vụ"]
    C --> D["Mã nguồn, test, pipeline"]
    D --> E["Increment / phát hành"]
    E --> F["Phản hồi người dùng, Support và vận hành"]
    F --> G["Bài học, ADR, runbook, backlog"]
    G --> B
    G --> H["Điểm vào tài liệu / hướng dẫn người mới"]
    H --> I["Thành viên mới hoặc người thay thế"]
    I --> B
~~~

### 5.1. Đừng ghi lại mọi cuộc nói chuyện

Nhóm nên ghi **kết luận và ngữ cảnh quan trọng**:

1. **Điều gì đã quyết?**
2. **Vì sao quyết như vậy và đã cân nhắc phương án nào?**
3. **Điều kiện/giả định nào có thể khiến quyết định đổi?**
4. **Nội dung ảnh hưởng mã, test, vận hành hoặc người dùng ở đâu?**
5. **Ai cần biết, ai chịu trách nhiệm xem lại?**

Ghi toàn bộ đoạn chat mà không có tóm tắt và liên kết ngược thường khiến người mới **phải tự làm lại công việc phân tích**.

## 6. Kiểm kê kiến thức quan trọng trước khi xây kho tài liệu

Không cần bắt đầu bằng việc viết một “bách khoa toàn thư” của sản phẩm. Hãy **xem những điểm mà người mới hoặc người dự phòng thường bị chặn**.

### 6.1. Câu hỏi kiểm kê

- Nếu một người nghỉ hai tuần, **công việc nào dừng lại**?
- Nếu có sự cố trong giờ thấp điểm, **ai biết cách chẩn đoán**?
- Nếu một Developer mới nhận PBI, **điểm bắt đầu trong repo** ở đâu?
- Nếu Product Owner vắng một ngày, **mục tiêu, ưu tiên và điều kiện chấp nhận** đã rõ chưa?
- Nếu quyết định kiến trúc bị chất vấn, **lý do và phương án bị loại** nằm ở đâu?
- Nếu một đối tác đổi API, **người nào theo dõi phụ thuộc và hợp đồng tích hợp**?
- Nếu CI đỏ, **cách phân biệt lỗi code với hạ tầng** ở đâu?
- Nếu người dùng báo sai trạng thái, **cách tìm phiên bản và log liên quan** ở đâu?

### 6.2. Lập bản đồ rủi ro tri thức

| Lĩnh vực | Tri thức quan trọng | Rủi ro nếu thiếu | Đầu ra tối thiểu có ích |
| --- | --- | --- | --- |
| Sản phẩm | Product Goal, luồng người dùng, quy tắc đăng ký | Làm sai nhu cầu | Hướng dẫn miền nghiệp vụ và ví dụ |
| Kiến trúc | Ranh giới service, luồng dữ liệu, quyết định đồng thời | Sửa sai cấu trúc | Sơ đồ khái quát + ADR |
| Phát triển | Cách chạy build/test, cấu hình môi trường | Người mới bị chặn | README và quickstart |
| Kiểm thử | Test quan trọng, dữ liệu thử, các rủi ro | Lỗi lọt khi thay đổi | Testing guide có liên kết suite |
| Vận hành | Alert, cách chẩn đoán, khôi phục, rollback | Phản ứng chậm hoặc sai | Runbook theo tình huống |
| Hợp tác | Ai quyết ưu tiên, ai review, ai thay thế | Chờ người vắng mặt | Working agreement và trách nhiệm |
| Phụ thuộc | Chủ sở hữu API đối tác, giới hạn, đầu mối | Tắc tích hợp | Dependency map và điều kiện liên hệ |

### 6.3. Ưu tiên theo hậu quả, không theo số tài liệu

Nếu vừa thiếu runbook khôi phục dữ liệu vừa thiếu mô tả thiết kế một nút UI phụ, ưu tiên thường thuộc về **phần có thể gây hại hoặc chặn cả nhóm**. Một cách kiểm tra đơn giản:

> **“Nếu ngày mai người duy nhất biết điều này không truy cập được, hậu quả có thể là gì?”**

Rủi ro càng cao, càng nên có **tài liệu đủ dùng, người dự phòng và thực hành kiểm chứng**.

## 7. Chọn một nguồn sự thật và những đường dẫn dễ tìm

Nhóm thường dùng Git, công cụ backlog, wiki, chat và hệ thống ticket. Không nhất thiết gom mọi nội dung về **một ứng dụng duy nhất**, nhưng cần biết **nội dung nào có nơi cập nhật chính thức**.

### 7.1. “Single source of truth” nên hiểu thế nào?

Một thông tin có thể được **liên kết hoặc tóm tắt** ở nhiều nơi, nhưng cần có nơi quản lý **phiên bản có hiệu lực**.

Ví dụ:

| Thông tin | Nơi quản lý chính có thể phù hợp | Những nơi nên liên kết tới |
| --- | --- | --- |
| Cách build/test một repo | README hoặc tài liệu versioned cùng repo | Trang onboarding, ticket |
| Quyết định kiến trúc | ADR trong repo tài liệu phù hợp | PR, sơ đồ hệ thống |
| Product Backlog và thứ tự ưu tiên | Công cụ backlog được nhóm chọn | Sprint note, trang sản phẩm |
| Sự cố và lịch sử ứng phó | Hệ thống incident/ticket có kiểm soát | Runbook, Retrospective action |
| Bí mật/cấu hình nhạy cảm | Secret manager và cơ chế quản trị được phê duyệt | Tài liệu chỉ mô tả cách xin quyền, không copy secret |
| Hướng dẫn người mới | Điểm vào tài liệu dễ truy cập | Repo, working agreement, đầu mối hỗ trợ |
| Kênh hỗ trợ đối tác | Danh bạ trách nhiệm được cập nhật | Hướng dẫn tích hợp và runbook |

**Nguồn sự thật không đồng nghĩa tài liệu nào cũng phải nằm trong Git**. Quyết định phụ thuộc đối tượng, nhu cầu truy cập, mức nhạy cảm và công cụ tổ chức.

### 7.2. Cạm bẫy hai bản tài liệu “chính”

Wiki ghi “chạy JDK 17”, README ghi “JDK 21”. Người mới không thể biết bản nào đúng. Cách sửa:

1. Xác định phiên bản/công cụ thực tế dựa trên nguồn được kiểm chứng.
2. Chỉ định một nơi chịu trách nhiệm nội dung chính.
3. Trang khác **liên kết hoặc tóm tắt có ghi nguồn**, tránh copy toàn bộ.
4. Chặn hoặc thông báo khi hướng dẫn quan trọng đổi.
5. Xem lại các liên kết bị lỗi và nội dung xung đột.

### 7.3. Thiết kế thông tin để có thể tìm

Điểm vào nên trả lời:

- **Tôi là ai?** Người mới, người trực thay, người kiểm thử, Product Owner, bên hỗ trợ.
- **Tôi cần làm gì?** Cài môi trường, hiểu hệ thống, xử lý sự cố, tra quyết định.
- **Tôi nên bắt đầu đâu?** Một trang tổng quan hoặc README rõ.
- **Tôi cần quyền nào?** Hướng dẫn xin quyền an toàn, không ghi thông tin bí mật.
- **Khi trang này sai, báo cho ai?** Người/nhóm sở hữu và kênh phản hồi.

## 8. Bộ tài liệu tối thiểu phục vụ nhóm phân tán

| Loại tài liệu | Người đọc chính | Nội dung cần có | Thời điểm nên tạo/cập nhật |
| --- | --- | --- | --- |
| **README/Quickstart** | Người mới, Developer hỗ trợ | Mục đích repo, chuẩn bị môi trường, build/test, troubleshooting, liên kết | Khi tạo repo hoặc cách chạy thay đổi |
| **Team working agreement** | Toàn nhóm | Giờ giao nhau, cách liên hệ, thời hạn phản hồi, mức khẩn, kênh quyết định | Khi nhóm hình thành, thay cách phối hợp |
| **Product/domain guide** | Người mới, QA, Product | Mục tiêu người dùng, thuật ngữ, quy tắc trọng yếu | Khi phát hiện hiểu nhầm hoặc thay nghiệp vụ |
| **Architecture overview** | Developer, người review/khôi phục | Ranh giới hệ thống, dữ liệu, dependency và luồng chính | Khi cấu trúc hoặc rủi ro thay đổi |
| **ADR** | Người thiết kế và bảo trì | Quyết định, bối cảnh, phương án, hệ quả | Khi có quyết định khó đảo ngược hoặc gây ảnh hưởng lớn |
| **Runbook** | Người vận hành/trực thay | Triệu chứng, kiểm tra, bước hành động, quyền, khôi phục, escalation | Khi có quy trình vận hành quan trọng |
| **Testing guide** | Developer, QA, người review | Cách chạy test, fixture, môi trường, test rủi ro cao | Khi bổ sung suite hoặc thay cách kiểm chứng |
| **Decision/meeting note** | Người vắng họp | Quyết định, lý do, việc tiếp, owner, thời hạn | Sau trao đổi có quyết định ảnh hưởng nhóm |
| **Handoff note** | Người thay thế hoặc người trở lại | Trạng thái, việc chưa xong, rủi ro, liên kết, ưu tiên | Trước kỳ nghỉ, đổi người trực hoặc đổi trách nhiệm |
| **FAQ/troubleshooting** | Người thường gặp vấn đề | Triệu chứng, cách xác định, nguồn tham khảo đáng tin | Khi câu hỏi/lỗi lặp lại |
| **Onboarding path** | Người mới và người hỗ trợ | Trình tự học, quyền, ví dụ thực hành, cách nhận hỗ trợ | Khi có người mới hoặc phản hồi onboarding |

Đây là **danh mục để lựa chọn theo nhu cầu**, không phải danh sách giấy tờ mỗi Sprint đều bắt buộc phải tạo. Một nhóm nhỏ có thể gom nhiều loại vào vài trang có cấu trúc tốt.

## 9. Onboarding: thiết kế hành trình tự phục vụ nhưng không cô lập người mới

Một người mới không chỉ cần “đọc tài liệu”. Họ cần một lộ trình từ **hiểu sản phẩm** tới **thực hiện thay đổi nhỏ an toàn** cùng hỗ trợ phù hợp.

### 9.1. Những mốc onboarding hữu ích

| Mốc | Người mới cần đạt | Bằng chứng thực hành |
| --- | --- | --- |
| **Tiếp cận** | Biết nơi tìm tài liệu, môi trường và kênh trợ giúp | Tìm đúng repo, điểm vào, cách xin quyền |
| **Hiểu ngữ cảnh** | Mô tả Product Goal, người dùng, luồng nghiệp vụ | Giải thích bằng lời hành trình đăng ký workshop |
| **Chạy được** | Build/test trong môi trường được hỗ trợ | Chạy test mẫu hoặc xem pipeline tương ứng |
| **Thay đổi nhỏ** | Hiểu cách đóng góp, kiểm tra và review | Hoàn tất một thay đổi có người hướng dẫn, đạt chính sách Done |
| **Xử lý câu hỏi** | Biết phân loại lỗi/tài liệu sai và hỏi đúng nơi | Đề xuất sửa một trang hướng dẫn không còn đúng |
| **Chủ động dần** | Có thể tham gia một lát cắt thực với feedback | Thực hiện PBI phù hợp và báo rủi ro sớm |

### 9.2. Trang “Start here” mẫu

~~~markdown
# Bắt đầu với nhóm Workshop

## Hiểu sản phẩm
- Mục tiêu: học viên tìm và đăng ký workshop an toàn
- Luồng chính: xem danh sách -> đăng ký -> kiểm tra trạng thái
- Thuật ngữ nghiệp vụ: [Domain guide](./domain-guide.md)

## Làm việc với code
- Nơi xem phiên bản JDK/build: [README repo](./README.md)
- Cách chạy unit/integration test: [Testing guide](./testing.md)
- Quy tắc review và hoàn tất: [Working agreement](./working-agreement.md)

## Khi bị chặn
- Lỗi môi trường: mở issue theo mẫu và liên hệ kênh hỗ trợ nội bộ
- Lỗi nghiệp vụ: trao đổi với Product Owner / người đại diện nghiệp vụ
- Sự cố nghiêm trọng: theo runbook và quy trình incident được phê duyệt

## Việc thực hành đầu
- Chạy bộ test mẫu trong môi trường an toàn
- Đọc một ADR liên quan phần đang làm
- Thực hiện một thay đổi nhỏ có người review

## Khi tài liệu có lỗi
- Đề xuất sửa ngay tại nguồn sở hữu tài liệu
- Nếu khẩn hoặc ảnh hưởng an toàn, thông báo theo kênh thích hợp
~~~

Đường dẫn là **ví dụ cấu trúc**, không khẳng định các tệp đó đã tồn tại trong một repo cụ thể.

### 9.3. Không biến onboarding thành cuộc thi “tự tìm hiểu”

Người mới có thể cần **buddy, pairing, phiên hỏi đáp có thời gian rõ**. Tài liệu nên giúp giảm câu hỏi lặp, không khiến người mới ngại hỏi vì bị coi là thiếu độc lập.

Một phản hồi có ích sau onboarding:

> “Chỗ nào bạn tìm hơn mười phút mà vẫn không biết đáp án? Bạn đã phải hỏi ai? Tài liệu nào nói một điều nhưng môi trường thật làm một điều khác?”

Chính những điểm vướng này giúp **sửa hệ thống kiến thức**.

## 10. Bàn giao khi thành viên vắng mặt

Vắng mặt có nhiều dạng: nghỉ phép có kế hoạch, nghỉ ốm bất ngờ, đổi múi giờ, chuyển vai trò hoặc mất kết nối tạm thời. Mỗi dạng có **độ chuẩn bị khác nhau**, nhưng nhóm có thể tạo sự linh hoạt bằng cách giảm phụ thuộc vào một người từ trước.

### 10.1. Bàn giao khi biết trước lịch vắng mặt

Trước khi nghỉ, người phụ trách nên làm rõ:

1. **Các hạng mục đang mở** và trạng thái đúng theo board/backlog.
2. **Quyết định quan trọng** đã có, liên kết ADR hoặc decision log.
3. **Rủi ro hoặc phụ thuộc chưa giải quyết**.
4. **Điều kiện hoàn tất** và việc kiểm chứng còn lại.
5. **Người/nhóm thay thế phù hợp** và thẩm quyền thực tế.
6. **Sự kiện có thể xảy ra khi vắng mặt** như release, đối tác đổi API, gia hạn chứng chỉ.
7. **Cách liên hệ và escalation chính thức**, không mặc định người nghỉ luôn sẵn sàng.

### 10.2. Mẫu handoff bất đồng bộ

~~~text
TIEU DE: Ban giao luong dang ky workshop
KHOANG VANG MAT: Ngay bat dau -> ngay ket thuc
MUC TIEU / SPRINT GOAL LIEN QUAN:

TRANG THAI THUC:
- PBI A: Da dat Done; bang chung: <link>
- PBI B: Dang test transaction, chua Done; PR: <link>
- PBI C: Cho PO lam ro quy tac huy; backlog: <link>

QUYET DINH QUAN TRONG:
- Co che khong xac nhan vuot suc chua: ADR <link>
- Dieu kien chot pham vi: <link>

RUI RO VA VIEC CAN THEO DOI:
- API doi tac co the doi gioi han goi
- Test concurrency dang chay tren moi truong X
- Neu p95 tang bat thuong: xem runbook <link>

AI CO THE LAM GI:
- Review thay doi du lieu: nhom ky thuat duoc uy quyen
- Uu tien Product Backlog: PO hoac co che uy quyen phu hop
- Xu ly incident: lich truc va quy trinh hien hanh

KHONG NEN LAM:
- Khong chay script sua du lieu production bang cach doan
- Khong merge PBI chua dat chinh sach Done

KHI QUAY LAI:
- Xem cac quyet dinh moi trong decision log
- Xem thay doi ADR/runbook va tinh trang incident
- Lam viec voi nguoi ban giao lai ve viec chua ro
~~~

Mẫu là **công cụ giao tiếp**, không yêu cầu ghi tên người, quyền hoặc đường dẫn nhạy cảm vào tài liệu công khai. Các liên kết phải tới nơi được phân quyền đúng.

### 10.3. Khi vắng mặt đột xuất

Không thể đòi người ốm hoặc mất kết nối phải tạo tài liệu ngay. Nhóm cần **kế hoạch dự phòng đã có**:

- Board và trạng thái PBI được cập nhật thường xuyên.
- Những quyết định rủi ro cao đã có bản ghi.
- Người dự phòng đã từng review hoặc pairing với phần quan trọng.
- Runbook và cơ chế tiếp cận môi trường đủ rõ.
- Quyền quyết định và kênh escalation không phụ thuộc một cá nhân duy nhất.

**Khả năng vận hành khi người khác vắng mặt là đặc tính của nhóm**, không phải nghĩa vụ cá nhân phải trực tuyến trong kỳ nghỉ.

## 11. ADR: lưu lý do của quyết định kỹ thuật

**Architecture Decision Record (ADR)** là bản ghi ngắn về một **quyết định thiết kế quan trọng trong bối cảnh cụ thể**. Nó đặc biệt hữu ích khi người tạo quyết định không còn trong dự án hoặc sau nhiều tháng lý do ban đầu bị quên.

### 11.1. Khi nào đáng tạo ADR?

- Chọn giữa hai phương án có ảnh hưởng lớn tới dữ liệu hoặc kiến trúc.
- Quyết định khó đảo ngược hoặc sẽ bị người mới thắc mắc.
- Chấp nhận một trade-off có rủi ro cần theo dõi.
- Thay đổi contract, cách lưu trữ hoặc cơ chế đảm bảo nhất quán.
- Có nhiều quan điểm và nhóm cần nhớ **vì sao đã chọn**.

Không cần ADR cho từng tên biến hoặc chỉnh sửa nhỏ mang tính triển khai.

### 11.2. Ví dụ ADR minh họa

~~~markdown
# ADR-007: Kiểm soát xác nhận vượt sức chứa workshop

Trạng thái: Accepted
Ngày quyết định: YYYY-MM-DD
Chủ sở hữu: Nhóm phát triển luồng đăng ký
Liên quan: User story đăng ký workshop, test đồng thời, schema dữ liệu

## Bối cảnh
Hai học viên có thể đăng ký gần như đồng thời khi workshop còn một chỗ.
Nếu chỉ kiểm tra sức chứa ở ứng dụng rồi ghi riêng lẻ, có nguy cơ
đưa ra nhiều xác nhận hơn sức chứa.

## Quyết định
Việc xác nhận chỗ phải được thực thi bởi cơ chế giao dịch/ràng buộc
dữ liệu phù hợp và có kiểm thử tích hợp trên cơ chế lưu trữ thực tế.

## Phương án đã cân nhắc
- Chỉ kiểm tra ở UI: loại vì không bảo vệ truy cập đồng thời.
- Chỉ kiểm tra ở application memory: không đủ cho nhiều instance.
- Cơ chế giao dịch/ràng buộc ở nguồn dữ liệu: chọn sau khi xác minh.

## Hệ quả và rủi ro
- Cần kiểm thử concurrency, xử lý lỗi và retry có kiểm soát.
- Cần xem tác động hiệu năng dưới tải phù hợp.

## Điều kiện xem lại
- Thay storage hoặc thay mô hình đăng ký.
- Dữ liệu vận hành cho thấy contention vượt ngưỡng chấp nhận.

## Bằng chứng / liên kết
- Thiết kế: <link>
- Integration tests: <link>
- Runbook điều tra dữ liệu: <link>
~~~

**Đây là ví dụ lý luận**, không chứng minh một cơ chế database cụ thể tự bảo đảm đúng mọi trường hợp. Khi triển khai phải chọn transaction/constraint dựa trên công nghệ thực tế và kiểm chứng tương xứng.

### 11.3. ADR không cần bị sửa để “giả vờ luôn đúng”

Khi đổi quyết định, có thể tạo ADR mới với trạng thái **supersedes/superseded** hoặc cách ghi tương tự, liên kết lại lịch sử. Mục tiêu là biết **điều gì đúng ở thời điểm nào**, không xóa bối cảnh quá khứ.

## 12. Runbook: biến tri thức vận hành thành hành động có kiểm soát

Runbook hướng dẫn **chẩn đoán và xử lý một tình huống vận hành cụ thể**. Nó không phải một bản chép lại mọi lệnh terminal từng dùng.

### 12.1. Một runbook cần những gì?

| Thành phần | Câu hỏi |
| --- | --- |
| **Phạm vi áp dụng** | Runbook dành cho dịch vụ, môi trường, phiên bản nào? |
| **Tín hiệu kích hoạt** | Alert, biểu hiện người dùng hay điều kiện nào? |
| **Tác động và mức nghiêm trọng** | Có nguy cơ dữ liệu, bảo mật hoặc gián đoạn lớn không? |
| **Điều kiện trước** | Cần quyền, backup, môi trường và phê duyệt gì? |
| **Bước chẩn đoán an toàn** | Xem dashboard/log/trace nào mà không làm thay đổi dữ liệu? |
| **Hành động được phép** | Ai được thực hiện bước giảm thiểu hoặc phục hồi nào? |
| **Tiêu chí thành công** | Làm sao biết hệ thống ổn và dữ liệu đúng? |
| **Kế hoạch khi thất bại** | Khi nào dừng, rollback, escalate hoặc chuyển kênh sự cố? |
| **Owner/ngày kiểm tra** | Ai chịu trách nhiệm cập nhật? Lần gần nhất kiểm chứng? |

### 12.2. Ví dụ runbook điều tra timeout đăng ký

~~~text
TEN: Dieu tra tang timeout o API dang ky workshop
PHAM VI: Dich vu dang ky, moi truong production duoc uy quyen
KICH HOAT: Alert do tre / ticket nguoi dung / ty le timeout tang

TRUOC KHI THUC HIEN:
- Xac nhan minh co quyen va dang dung moi truong
- Khong thao tac sua du lieu neu chua co phuong an duoc phe duyet
- Neu nghi ngo mat an toan du lieu: chuyen quy trinh incident

CHUAN DOAN KHONG PHA HUY:
1. Kiem tra error rate va latency theo phien ban / dependency
2. Doi chieu trace cua request bi anh huong
3. Kiem tra trang thai giao dich tu nguon su that theo quyen cho phep
4. Xac dinh co dang ghi nhan trung / vuot suc chua hay khong

GIOI HAN QUYET DINH:
- Neu co nguy co du lieu sai: bao incident lead, can nhac dung mo rong
- Neu dependency giam chat luong: theo co che khac phuc da phe duyet
- Khong tu chay script sua production khong duoc tham dinh

XAC MINH SAU CAN THIEP:
- Error rate, timeout va luong dang ky duoc ghi dung
- Nguoi dung bi anh huong duoc xem xet ho tro / doi soat neu can

ESCALATION / OWNER: Theo so do truc duoc cap nhat
LIEN KET: Dashboard <link>; ADR <link>; incident policy <link>
NGAY KIEM TRA: YYYY-MM-DD
~~~

Runbook cố ý **không cung cấp một lệnh sửa dữ liệu trực tiếp thiếu ngữ cảnh**. Với thao tác có tác động production, nhóm cần quy trình được phê duyệt và thử trước trong môi trường phù hợp.

### 12.3. Kiểm tra runbook bằng thực hành

Một người dự phòng có thể đọc thử và trả lời:

1. Tôi có biết alert nào đưa tôi tới runbook này không?
2. Tôi có đủ quyền xem dashboard theo chính sách không?
3. Tôi có biết bước nào chỉ đọc, bước nào thay đổi trạng thái?
4. Tôi có biết khi nào **phải dừng** không?
5. Tôi có liên hệ được người trực hoặc incident lead?
6. Tôi có thể xác nhận trạng thái nghiệp vụ sau xử lý?

Nếu trả lời “không”, tài liệu chưa đủ hỗ trợ thay thế an toàn.

## 13. Decision log và ghi chú họp để người vắng mặt theo kịp

Không cần ghi lại từng phút của cuộc họp; cần lưu **quyết định có tác động và điều cần làm tiếp**.

### 13.1. Bản ghi sau cuộc trao đổi

~~~text
NGAY / CHU DE:
MUC TIEU HOAC CAU HOI:
BOI CANH CAN THIET:
QUYET DINH:
LY DO / BANG CHUNG:
PHUONG AN CHUA CHON:
RUI RO VA DIEU KIEN XEM LAI:
AI CO QUYEN QUYET:
HANH DONG / OWNER / MOC:
LINK PRODUCT BACKLOG / ADR / PR:
DOI TUONG CAN DUOC THONG BAO:
~~~

Một người không dự họp nên đọc được câu trả lời:

> **“Nhóm đã quyết điều gì; tại sao; có thay đổi phạm vi hoặc công việc của tôi không; tôi cần làm gì; hỏi ai khi có bằng chứng mới?”**

### 13.2. Không gọi im lặng là đồng ý tuyệt đối

Trong nhóm khác múi giờ, người không phản hồi ngay có thể **đang ngủ, chăm sóc gia đình, không có quyền truy cập hoặc đã nghỉ phép**. Đừng mặc định “không trả lời trong hai giờ thì coi như chấp thuận” cho mọi quyết định rủi ro.

Thay vào đó:

- Quy định **mức khẩn và khoảng phản hồi thực tế** theo working agreement.
- Nêu rõ loại quyết định **cần đúng người có thẩm quyền**.
- Cung cấp thời gian nhận phản biện hợp lý cho việc không khẩn.
- Có người dự phòng đối với quyết định cần thực hiện khi một người vắng.
- Với sự cố khẩn, dùng **quy trình incident riêng**, không đợi đồng thuận async vô hạn.

### 13.3. “Đã ghi biên bản” khác “đã thông báo”

Một quyết định đổi API có thể được ghi đúng nhưng team khác không biết. Cần xác định **ai bị ảnh hưởng** và dùng kênh thông báo phù hợp, có liên kết nguồn chính để tránh sao chép nhiều bản mâu thuẫn.

## 14. Docs-as-code: đưa tài liệu thay đổi gần với mã

**Docs-as-code** là cách quản lý tài liệu bằng các thực hành quen thuộc của phát triển: version control, review, pull request, kiểm tra tự động và phát hành cùng chu kỳ phù hợp.

### 14.1. Những loại tài liệu thường phù hợp gần repo

- Lệnh build/test và phiên bản toolchain.
- API contract, schema và cách chạy môi trường cục bộ.
- ADR và sơ đồ module quan trọng.
- Quy tắc kỹ thuật hoặc checklist review.
- Hướng dẫn chẩn đoán liên quan code/version.
- Ví dụ fixture và cách tái hiện lỗi đã biết.

Tài liệu quyền nhân sự, hợp đồng đối tác hoặc incident bảo mật có thể **không phù hợp để ở repo chia sẻ rộng**.

### 14.2. Một cấu trúc minh họa

~~~text
repo/
  README.md
  docs/
    index.md
    getting-started.md
    domain/
      workshop-registration.md
    architecture/
      overview.md
      adr/
        0007-registration-consistency.md
    testing/
      testing-guide.md
    operations/
      registration-timeout.md
    team/
      working-agreement.md
      handoff-template.md
  src/
  tests/
~~~

Đây là **sơ đồ ví dụ**, không phải cấu trúc hiện có của dự án và không yêu cầu mọi team phải tạo đúng tên thư mục.

### 14.3. Review tài liệu theo rủi ro

Một thay đổi tên lệnh build có thể yêu cầu cập nhật README cùng PR. Một thay đổi giao dịch quan trọng có thể cần cập nhật ADR, test và runbook. Nhưng không nên ép viết ADR cho mỗi sửa chính tả.

### 14.4. Kiểm tra tự động cũng có giới hạn

Tùy công cụ, nhóm có thể tự động kiểm tra:

- Liên kết nội bộ bị hỏng.
- Markdown/YAML hợp lệ.
- Tiêu đề và từ khóa có cấu trúc.
- Mẫu trang yêu cầu owner hoặc trạng thái.
- Những đoạn code/lệnh có thể chạy trong môi trường kiểm chứng an toàn.

**Link checker xanh không chứng minh nội dung vẫn đúng**, cũng như build xanh không chứng minh người dùng nhận giá trị. Cần người hiểu bối cảnh đọc và thử thực tế.

## 15. Liên kết cập nhật kiến thức với công việc Agile

Một nguyên nhân tài liệu lỗi thời là xem cập nhật tài liệu như việc “làm khi rảnh”, không liên hệ với thay đổi đang được phát triển.

### 15.1. Câu hỏi trong refinement và trước khi triển khai

- PBI thay đổi quy tắc nghiệp vụ nào?
- Người mới hoặc người trực thay có cần biết điều này để làm đúng?
- Một ADR hay runbook nào bị ảnh hưởng?
- Có cần cập nhật test, ví dụ chấp nhận hoặc sơ đồ dữ liệu?
- Quyết định có làm đổi đường liên hệ hoặc quyền vận hành?
- Có thể gắn cập nhật tài liệu vào **cùng lát cắt** thay vì tạo việc không có owner?

### 15.2. Ánh xạ loại thay đổi tới thông tin cần cập nhật

| Loại thay đổi | Thông tin nên xem lại | Vì sao |
| --- | --- | --- |
| Đổi cách chạy build | README/quickstart và pipeline | Người mới không bị kẹt |
| Thêm API | Contract, testing guide, ví dụ gọi | Các team tích hợp đúng |
| Đổi quy tắc đăng ký | Domain guide, acceptance examples, test | Không tạo hành vi không nhất quán |
| Đổi mô hình giao dịch | ADR, integration tests, vận hành | Giữ lý do và rủi ro kỹ thuật |
| Đổi cảnh báo hoặc recovery | Runbook, lịch trực, đường escalation | Người thay thế hành động an toàn |
| Đổi quyền thao tác | Hướng dẫn xin quyền, threat model hoặc chính sách liên quan | Không mở lỗ hổng quyền |
| Đổi Product Goal hoặc phạm vi quan trọng | Product Backlog, thông báo stakeholder | Người vắng mặt quay lại đúng hướng |

### 15.3. Liên hệ với Definition of Done

Trong Scrum, **Definition of Done (DoD)** mô tả trạng thái chất lượng cần thiết của Increment. Nếu một thay đổi cần hướng dẫn vận hành hoặc cập nhật tài liệu để sản phẩm **được sử dụng và duy trì an toàn**, nhóm có thể đưa những điều kiện phù hợp vào tiêu chuẩn hoàn tất hoặc tiêu chí chấp nhận của công việc.

**Không nên tự gán rằng Scrum Guide bắt buộc mọi PBI phải có trang wiki riêng.** Mức tài liệu hợp lý phụ thuộc rủi ro và nhu cầu, nhưng không được biến “working software” thành cớ bỏ thông tin thiết yếu để chạy, kiểm thử hoặc khôi phục.

### 15.4. Tài liệu cũng có thể là một backlog item có giá trị

Khi một việc giảm lệ thuộc cá nhân lớn — ví dụ **xây runbook phục hồi đăng ký an toàn** — nó có thể được ưu tiên như một hạng mục cải tiến kỹ thuật hoặc vận hành. Nên mô tả **rủi ro được giảm và cách kiểm chứng** thay vì chỉ ghi “viết tài liệu”.

## 16. Bảo mật, quyền riêng tư và truy cập trong kho kiến thức

Tài liệu có thể gây hại nếu công khai credential, sơ đồ nhạy cảm, dữ liệu cá nhân hoặc quy trình có quyền cao. **Dễ tìm** không có nghĩa **ai cũng có quyền đọc mọi nội dung**.

### 16.1. Phân loại nội dung theo mức truy cập

| Loại thông tin | Cách tiếp cận thường phù hợp | Điều cần tránh |
| --- | --- | --- |
| Hướng dẫn cài môi trường và coding convention | Chia sẻ cho người được làm việc với repo | Copy token hoặc password vào ví dụ |
| Domain guide và quy tắc nghiệp vụ thường | Chia sẻ cho nhóm sản phẩm liên quan | Làm lộ dữ liệu thật khi minh họa |
| Architecture/security-sensitive details | Phân quyền theo nhu cầu, theo chính sách | Đưa cấu hình nhạy cảm vào wiki công khai |
| Credentials, private keys và tokens | Secret manager/quy trình quản lý bí mật | Lưu trong Markdown, issue hoặc chat |
| Log, dữ liệu sản xuất | Truy cập tối thiểu, audit và làm mờ thông tin | Dùng bản ghi người dùng thật trong hướng dẫn công khai |
| Incident bảo mật | Nơi lưu và quy trình hạn chế truy cập | Chia sẻ timeline nhạy cảm cho người không có quyền |
| Thông tin cá nhân/nhân sự | Theo quy định dữ liệu và lao động phù hợp | Dùng tài liệu onboarding để lộ thông tin riêng |

### 16.2. Viết “cách xin quyền”, không viết “mật khẩu để dùng”

Một hướng dẫn tốt nói rõ:

1. Vai trò nào cần quyền gì?
2. Yêu cầu quyền qua quy trình nào?
3. Ai phê duyệt và cách kiểm tra quyền?
4. Làm sao thu hồi quyền khi chuyển dự án hoặc kết thúc hợp tác?
5. Nếu cần truy cập khẩn, cơ chế **break-glass** được tổ chức phê duyệt là gì?

Đừng bày cách vượt phân quyền chỉ để onboarding “nhanh”. Một thành viên mới cần **đường cấp quyền đúng**, không cần tài khoản chia sẻ không kiểm soát.

### 16.3. Đừng mặc định bản ghi cuộc họp có thể chia sẻ rộng

Ghi âm, transcript hoặc AI summary có thể chứa thông tin cá nhân, sự cố nhạy cảm hoặc ý kiến chưa được xác minh. Nhóm nên cân nhắc:

- Sự đồng ý/thông báo theo chính sách áp dụng.
- Giới hạn lưu trữ và nơi chia sẻ.
- Kiểm tra độ đúng của bản tóm tắt trước khi coi là quyết định chính thức.
- Tách **kết luận được phê duyệt** khỏi ý kiến thảo luận.
- Không đưa dữ liệu nhạy cảm vào công cụ không được tổ chức cho phép.

### 16.4. Không biến kho kiến thức thành công cụ giám sát cá nhân

Mục tiêu là **giảm phụ thuộc và tăng khả năng hợp tác**, không phải đo số trang mỗi người viết hoặc thời điểm ai online. Đánh giá đóng góp cần xem **chất lượng kiến thức được dùng thật**, bối cảnh công việc và những đóng góp không thể quy về số lượng tài liệu.

## 17. Quyền sở hữu, phiên bản và lịch xem lại: chống tài liệu chết

Nhiều nhóm có kho kiến thức rất lớn nhưng gần như không ai tin vì nội dung đã lỗi thời. Để người mới có thể dùng, tài liệu cần **cơ chế xác nhận độ tin cậy**.

### 17.1. Metadata tối thiểu hữu ích

~~~yaml
title: "Hướng dẫn kiểm tra lỗi timeout đăng ký"
owner: "Nhóm vận hành dịch vụ đăng ký"
status: "active"
applies_to: "Dịch vụ đăng ký, phiên bản đang được hỗ trợ"
last_reviewed: "YYYY-MM-DD"
review_trigger:
  - "Thay đổi luồng đăng ký hoặc dependency"
  - "Sau incident liên quan timeout"
  - "Thay đổi quy trình trực và escalation"
source_of_truth: "Liên kết tới runbook chính thức"
~~~

Đây là **mẫu minh họa metadata** cho tài liệu giả định, không phải YAML của bài học và không yêu cầu bổ sung trường vào file metadata của module.

### 17.2. Owner là trách nhiệm, không nhất thiết một người duy nhất

Một nhóm hoặc vai trò được phân công có thể chịu trách nhiệm:

- Kiểm tra tài liệu còn đúng khi hệ thống thay đổi.
- Tiếp nhận phản hồi từ người đọc.
- Đảm bảo quyền truy cập phù hợp.
- Điều phối review khi có quyết định mới.
- Giữ liên kết tới nguồn sự thật.

Tài liệu quan trọng nên có **kênh dự phòng** khi owner đang vắng mặt. Nếu chỉ một cá nhân có quyền sửa runbook, nhóm vẫn có điểm lỗi đơn.

### 17.3. Hai loại kích hoạt xem lại

**Theo sự kiện:**

- Có thay đổi API, dependency, kiến trúc hoặc luồng vận hành.
- Có sự cố cho thấy hướng dẫn không đủ hoặc sai.
- Người mới báo không thể làm theo quickstart.
- Quy trình cấp quyền hoặc công cụ thay đổi.

**Theo nhịp định kỳ:**

- Xem lại những runbook rủi ro cao theo tần suất hợp lý.
- Kiểm tra trang onboarding trước đợt có người mới.
- Rà soát liên kết và các trang có nhiều lượt truy cập hoặc nhiều vấn đề.

Không có một tần suất xem lại chung cho mọi tài liệu. Hướng dẫn khôi phục production có thể cần kiểm tra thường xuyên hơn một trang giải thích khái niệm ít biến động.

### 17.4. Trạng thái tài liệu phải rõ

Có thể sử dụng các nhãn tùy hệ thống như **draft, active, deprecated, superseded, archived** để người đọc biết độ hiệu lực. Khi thay ADR, giữ đường dẫn tới quyết định mới; khi thay runbook, thông báo cho người trực liên quan.

**Không xóa sạch lịch sử khi điều kiện đã đổi.** Lịch sử có thể cần để giải thích một incident cũ hoặc vì sao một bản release trước hành xử khác.

## 18. Giao tiếp bất đồng bộ: tài liệu là cầu nối, không phải hàng rào

**Asynchronous communication** cho phép thành viên trao đổi mà không nhất thiết có mặt cùng lúc. Nó đặc biệt có giá trị khi nhóm ở nhiều múi giờ hoặc có lịch tập trung khác nhau.

### 18.1. Một yêu cầu bất đồng bộ đủ ngữ cảnh

Thay vì:

> “Có ai xem giúp bug này không? Gấp.”

Một yêu cầu có ích:

> “Luồng đăng ký workshop trên môi trường thử phát sinh timeout khi hai yêu cầu đồng thời. Mục tiêu của tôi là xác minh một người chỉ được giữ chỗ cuối. Có log đã làm mờ dữ liệu ở liên kết X, PR Y và integration test Z. Tôi đã thử A/B, chưa xác định dependency nào gây chậm. Cần một người có kinh nghiệm transaction review trước buổi phối hợp ngày mai; nếu thấy rủi ro dữ liệu production, hãy dùng kênh incident thay vì chờ thread này.”

Thông điệp tốt có:

- **Bối cảnh:** Sản phẩm, môi trường, phiên bản và mục tiêu.
- **Hiện trạng:** Điều đã thử và kết quả.
- **Câu hỏi cụ thể:** Cần review, quyết định hay dữ liệu nào?
- **Đường dẫn chính:** PR, test, ADR, issue hoặc runbook.
- **Mức khẩn hợp lý:** Thời điểm và hậu quả nếu không được phản hồi.
- **Kênh escalation:** Khi nào chuyển sang xử lý đồng bộ/incident.

### 18.2. Cân bằng async và sync

| Tình huống | Async thường phù hợp | Nên cân nhắc trao đổi đồng bộ |
| --- | --- | --- |
| Đọc cập nhật tiến độ thường ngày | Bản ghi ngắn liên kết board | Khi có xung đột cần gỡ ngay |
| Review PR bình thường | Nhận xét có ngữ cảnh, thời hạn phù hợp | Khi tranh luận nhiều vòng mà vẫn không hiểu nhau |
| Làm rõ ví dụ chấp nhận | Tài liệu có phản hồi và câu hỏi mở | Khi nghiệp vụ mơ hồ và quyết định ảnh hưởng lớn |
| Báo kết quả thử nghiệm | Kết luận, bằng chứng, giới hạn | Khi cần chọn chiến lược mới giữa nhiều trade-off |
| Sự cố bảo mật hoặc dữ liệu nghiêm trọng | Ghi timeline và bằng chứng sau/đồng thời | Kích hoạt kênh ứng phó tức thời đúng thẩm quyền |
| Hỗ trợ người mới bị kẹt | Quickstart, issue, FAQ | Pairing hoặc walkthrough ngắn khi tài liệu chưa đủ |

**Không phải mọi vấn đề đều cần họp**, nhưng không nên dùng “async-first” như lý do tránh một cuộc đối thoại trực tiếp có thể tháo bế tắc nhanh.

### 18.3. Đừng biến phản hồi ngoài giờ thành nghĩa vụ

Nhóm nên thỏa thuận **giờ giao nhau có thể thực hiện, kỳ vọng phản hồi theo loại việc, quyền ngắt kết nối và đường liên hệ khẩn cấp**. Người không trực on-call không mặc nhiên phải trả lời tin nhắn công việc lúc đang ngủ hoặc nghỉ phép.

## 19. Working agreement giúp kiến thức không kẹt ở múi giờ

Một **working agreement** là thỏa thuận cách hợp tác thực dụng, không phải bộ luật cố định mọi nhóm Agile đều phải giống nhau.

### 19.1. Nội dung cần xác định

| Chủ đề | Câu hỏi | Ví dụ chính sách có thể thảo luận |
| --- | --- | --- |
| **Giờ giao nhau** | Khoảng thời gian nào thực sự cùng trực tuyến? | Dành giờ chung cho việc cần đối thoại, hạn chế họp ngoài giờ |
| **Kênh trao đổi** | Chat, issue, PR hay tài liệu dùng cho việc nào? | Quyết định bền vững ghi lại sau trao đổi |
| **Kỳ vọng phản hồi** | Việc thường và việc khẩn khác nhau thế nào? | Không suy im lặng là chấp thuận cho quyết định quan trọng |
| **Người dự phòng** | Khi owner vắng ai hỗ trợ? | Nhóm/kênh thay thế với quyền hạn rõ |
| **Bàn giao cuối ngày** | Những thông tin tối thiểu nào cần ghi? | Trạng thái, blocker, việc tiếp, liên kết |
| **Review** | Ai review loại thay đổi nào và theo chính sách? | Review thay đổi dữ liệu cần người đủ chuyên môn |
| **Sự cố** | Phản ứng khi service ảnh hưởng người dùng? | Incident channel, escalation, runbook |
| **Tài liệu** | Ai cập nhật nội dung, làm sao báo lỗi? | Sửa gần nguồn và review theo rủi ro |

### 19.2. Mẫu một cập nhật cuối ca

~~~text
CAP NHAT LUONG DANG KY — YYYY-MM-DD
MUC TIEU DANG THEO DOI:

DA HOAN TAT:
- Integration test cho luong dang ky thong thuong: <link>

DANG LAM / CHUA DONE:
- Xu ly concurrent request: PR <link>
- Test giao dich dang fail o moi truong X, log da an thong tin: <link>

BLOCKER:
- Can review cua nguoi co chuyen mon data transaction
- Quan tam mot giao dich co the xac nhan sai du lieu

VIEC NGUOI TIEP THEO CO THE LAM:
- Xem test fail va xac dinh buoc khoa/constraint chua dung
- Neu tim thay van de production, kich hoat incident policy

QUYET DINH MOI:
- Chua mo tinh nang cho nhom nguoi dung moi
- Link decision record: <link>

THONG TIN KHAC:
- Nguoi lien quan / kenh team duoc uy quyen
~~~

Mẫu nên được điền **ngắn gọn, chỉ khi có điều có ích**. Một bản cập nhật không có quyết định và không có gì thay đổi có thể chỉ cần trỏ tới board, tránh tạo tiếng ồn.

## 20. Truyền đạt quyết định giữa các nhóm có phụ thuộc

Nhóm phân tán thường không chỉ phụ thuộc người trong cùng Scrum Team: có nhóm nền tảng, bảo mật, sản phẩm, vận hành, nhà cung cấp hoặc đội cùng tiêu thụ API.

### 20.1. Những sự kiện cần thông báo có mục tiêu

- Thay đổi API contract hoặc schema dữ liệu.
- Thay chính sách xác thực/phân quyền.
- Thay đổi tiêu chuẩn tương thích hoặc thời điểm ngừng API.
- Đổi quy trình release, alert hoặc rollback.
- Phát hiện lỗ hổng ảnh hưởng nhiều dịch vụ.
- Thay ưu tiên Product Backlog có tác động tới phụ thuộc đã thỏa thuận.
- Chuyển trách nhiệm vận hành hoặc người trực hỗ trợ.

### 20.2. Ví dụ thông báo thay đổi tích hợp

~~~text
CHU DE: Thay doi trang thai dang ky workshop API
PHAM VI ANH HUONG: API /registrations va service gui thong bao
LY DO: Can phan biet "da nhan yeu cau" voi "da xac nhan cho"
THAY DOI DU KIEN: Truong status va dieu kien chuyen trang thai
TUONG THICH: Neu khong tuong thich, neu ro phien ban/ke hoach chuyen doi
CAN NGUOI NHAN LAM GI: Review contract, kiem chung consumer tests
MOC CAN PHAN HOI: Theo thoa thuan va muc do rui ro
LINK: ADR <link>, contract <link>, PR <link>
NGUOI PHOI HOP: Nhom quan ly API va cac consumer lien quan
RUI RO / PHUONG AN NEU CHUA SAN SANG:
~~~

Thông báo phải **nói rõ việc cần người nhận thực hiện**, không chỉ gửi một liên kết trống rồi xem như đã hoàn thành trách nhiệm tích hợp.

### 20.3. Không thay thế giao tiếp bằng danh sách người được gắn thẻ

Gắn thẻ 20 người trong chat có thể khiến ai cũng nghĩ người khác sẽ xử lý. Cần xác định **người/nhóm chịu trách nhiệm phản hồi và dấu hiệu đã hiểu yêu cầu**, trong khi vẫn tránh tạo quy trình phê duyệt không cần thiết.

## 21. Kiểm chứng kho kiến thức bằng “bài thử của người đọc”

Nếu một người mới không thể làm theo trang hướng dẫn, tài liệu có thể thiếu bước, sai phiên bản hoặc dùng thuật ngữ nội bộ mà chưa giải thích. Để biết **đủ dùng hay không**, hãy kiểm chứng bằng người chưa có toàn bộ ngữ cảnh.

### 21.1. Thử nghiệm onboarding nhỏ

Đề xuất:

1. Chọn một tác vụ **không gây rủi ro**, ví dụ build repo trong môi trường thử và chạy một unit test.
2. Cho người mới bắt đầu từ **điểm vào tài liệu** như một người dùng thực.
3. Ghi các câu hỏi bị chặn, thời gian tìm đường dẫn, bước sai và tài liệu xung đột.
4. Cung cấp hỗ trợ khi cần, không biến thử nghiệm thành bài thi khiến người mới sợ hỏi.
5. Cùng sửa hướng dẫn và chạy lại trên môi trường thích hợp.

### 21.2. Thử nghiệm người trực dự phòng

Trong môi trường an toàn:

- Người không viết runbook mô tả được tín hiệu alert.
- Họ biết nơi xem metric/log đã cấp quyền.
- Họ xác định được thao tác nào chỉ đọc, thao tác nào có tác động.
- Họ chỉ ra điều kiện **không tự xử lý mà phải escalation**.
- Họ trình bày được bước xác nhận an toàn sau hành động.

**Không tổ chức “diễn tập” bằng cách chủ động gây sự cố production hoặc thao tác dữ liệu thật khi chưa có kế hoạch và thẩm quyền an toàn phù hợp.**

### 21.3. Bài thử phát hiện vấn đề của thông tin, không chấm người đọc

Nếu người mới không hiểu một đoạn, hãy tìm cách **làm rõ nội dung hoặc cải thiện lộ trình**, thay vì kết luận người đó thiếu năng lực. Đồng thời, một số kỹ năng cần đào tạo trực tiếp; không nên kỳ vọng tài liệu thay hoàn toàn mentoring.

## 22. Đo khả năng chuyển giao kiến thức mà không xếp hạng người

Đếm số trang wiki, số lần sửa tài liệu hoặc số từ mỗi người viết là các **proxy dễ bị tối ưu sai**. Một kho có 300 trang có thể kém hữu ích hơn 15 trang đúng và dễ tìm.

### 22.1. Những tín hiệu có ích

| Câu hỏi | Bằng chứng có thể dùng | Lưu ý khi diễn giải |
| --- | --- | --- |
| Người mới tìm được thông tin không? | Thời gian tới câu trả lời đúng trong bài thử, số lần phải hỏi lại | Phụ thuộc tác vụ và kinh nghiệm |
| Người mới làm được tác vụ đầu an toàn không? | Build/test, PR nhỏ đạt chính sách Done với hỗ trợ thích hợp | Không dùng làm KPI tốc độ người mới |
| Nhóm phụ thuộc một người không? | Có người dự phòng, review chéo, khả năng thực hành runbook | Không chỉ đếm “hai tên trong bảng” |
| Runbook còn đúng không? | Lần thực hành/kiểm tra, phát hiện sai bước hoặc quyền | Một lần chạy thành công chưa bảo đảm mọi sự cố |
| Quyết định có tìm lại được không? | Bài thử tìm ADR/decision log từ PBI hoặc repo | Cần xem độ đúng và độ mới |
| Thông tin có trở nên lỗi thời không? | Link hỏng, tài liệu bị báo sai, thiếu owner, độ trễ cập nhật | Nhiều báo lỗi tài liệu có thể là phản hồi tích cực |
| Handoff có giúp giảm chờ không? | Work item age/blocked time khi owner vắng, phản hồi người dự phòng | Không gán mọi thay đổi cho tài liệu |
| Chất lượng có được giữ không? | Lỗi sau release, rủi ro vận hành, DoD, incident | Tốc độ tăng nhưng lỗi tăng chưa phải thành công |

### 22.2. Không dùng “bus factor” như nhãn cá nhân

**Bus factor** thường được dùng để nói tới số người quan trọng mà nếu không còn tham gia có thể khiến công việc bị ảnh hưởng nghiêm trọng. Đây chỉ là **cách diễn đạt rủi ro tập trung tri thức**, không phải chỉ số chuẩn đo cá nhân hay lý do gây áp lực một người phải luôn sẵn sàng.

Thay vì “Duy là người duy nhất biết phần giữ chỗ, phải hỗ trợ cả kỳ nghỉ”, hãy hỏi:

> “Rủi ro tập trung tri thức ở cơ chế giữ chỗ là gì? Chúng ta có thể cùng review, ghi ADR, kiểm thử và thực hành bàn giao thế nào để người khác tự xử lý an toàn?”

### 22.3. Chọn chỉ số để thay đổi hệ thống

Nếu người mới mất hai ngày vì thiếu quyền xem test logs, giải pháp có thể là **cải thiện quy trình cấp quyền và hướng dẫn**, không phải yêu cầu người mới “phải onboard trong một ngày”.

Nếu một runbook bị lỗi thời, cần xem **điểm cập nhật tài liệu bị bỏ qua trong luồng thay đổi** và trách nhiệm review, không tìm người để phạt vì số trang ít.

## 23. Tình huống xuyên suốt: người phụ trách cơ chế giữ chỗ nghỉ phép

**Bối cảnh:** Một nhóm phát triển nền tảng workshop có Product Owner, các Developers, người có chuyên môn QA và vận hành làm việc ở nhiều địa điểm. Sprint Goal hướng tới luồng đăng ký đúng chỗ và có trạng thái đáng tin. Người hiểu nhất về transaction, tạm gọi là thành viên **A**, sẽ nghỉ hai tuần.

### 23.1. Trước khi cải tiến

- Quy tắc “một chỗ cuối, hai yêu cầu gần đồng thời” được bàn trong cuộc họp, nhưng không có ADR.
- Test concurrency có trên nhánh cá nhân, chưa được đưa vào kiểm chứng CI.
- Một lệnh sửa dữ liệu cũ chỉ có trong lịch sử chat.
- Người mới **B** biết tên service nhưng không biết chạy integration tests thế nào.
- Runbook báo timeout dẫn tới dashboard đã đổi tên.
- Product Owner định đưa tính năng email vào Sprint dù luồng đăng ký vẫn còn rủi ro.

Nếu A nghỉ ngay, nhóm có thể bị chặn **hoặc** vội làm theo ghi chú cũ không an toàn.

### 23.2. Phần cần chuẩn bị trước kỳ nghỉ

| Vấn đề | Hành động có thể làm | Bằng chứng sẵn sàng |
| --- | --- | --- |
| Quy tắc transaction khó hiểu | Cùng viết ADR với phương án và rủi ro | Người khác giải thích đúng quyết định |
| Thiếu test concurrency trong luồng chung | Review và tích hợp test phù hợp | Pipeline chạy và kết quả có thể tái hiện |
| Không biết đường khôi phục | Cập nhật runbook theo nguyên tắc an toàn | Người dự phòng thử chẩn đoán ở môi trường phù hợp |
| Người mới không chạy test được | Sửa README/testing guide, pairing ngắn | B chạy test và hiểu kết quả |
| Lệnh sửa dữ liệu không rõ | Không copy chạy bừa; xử lý quy trình được phê duyệt | Có đường escalation hoặc thao tác an toàn đã thẩm định |
| Mục tiêu và ưu tiên không rõ | Làm rõ Sprint Goal, PBI và rủi ro với PO | Quyết định về email so với luồng cốt lõi được ghi |
| Người dự phòng thiếu quyền | Xin quyền theo quy trình và kiểm tra trước | Có quyền đúng phạm vi, không dùng tài khoản của A |

### 23.3. Kế hoạch thực hiện trong một tuần minh họa

| Ngày | Hoạt động | Giá trị kỳ vọng |
| --- | --- | --- |
| 1 | Kiểm kê chỗ nào chỉ A biết, chọn rủi ro lớn | Không mất thời gian ghi mọi chi tiết phụ |
| 2 | A và B cùng review ADR, test và ranh giới dữ liệu | Chuyển được lý do kỹ thuật quan trọng |
| 3 | B chạy test và thử chẩn đoán từ runbook | Phát hiện thiếu quyền hoặc bước sai |
| 4 | Cập nhật tài liệu theo phản hồi, liên kết PR/backlog | Kiến thức đến đúng nơi người sau tìm |
| 5 | Chốt handoff trạng thái, người dự phòng và escalation | Hỗ trợ kỳ nghỉ không cần A online |

**Lịch này chỉ minh họa**, không phải cam kết mọi sự phụ thuộc sẽ được loại bỏ trong năm ngày. Với rủi ro lớn hoặc việc cần đào tạo lâu, nhóm phải chủ động ưu tiên và điều chỉnh phạm vi.

### 23.4. Khi A đang vắng mặt

Giả sử API đăng ký bắt đầu timeout. B:

1. Tìm runbook qua điểm vào.
2. Xác định alert, phiên bản và điều kiện áp dụng.
3. Kiểm tra dashboard/log theo đúng quyền đã cấp.
4. So với ADR và test về tính nhất quán dữ liệu.
5. Nếu có dấu hiệu mất dữ liệu hoặc xác nhận vượt sức chứa, **kích hoạt quy trình incident**, không tự chạy script sửa dữ liệu.
6. Ghi phát hiện, quyết định và thay đổi liên quan cho nhóm, để A khi trở lại nắm được.

**Không gọi A khi đang nghỉ chỉ vì người khác không đọc tài liệu**, trừ khi có cơ chế ứng phó khẩn được thỏa thuận và hợp pháp, phù hợp trách nhiệm trực thực tế. Nhóm cần thiết kế để người nghỉ có thể thực sự nghỉ.

### 23.5. Sau khi A trở lại

A nên có một đường đọc ngắn:

- Decision log: những quyết định nào đã thay đổi?
- Product Backlog: điều gì được ưu tiên lại và vì sao?
- ADR/runbook: phần nào đã cập nhật?
- Incident record: có sự cố, tác động và hành động phòng ngừa nào?
- Các PR và test quan trọng: kiến thức kỹ thuật cần xem tiếp.

Một cuộc sync ngắn có thể dành cho **vấn đề còn mơ hồ**, thay vì kể lại toàn bộ hai tuần bằng trí nhớ từng người.

## 24. Tình huống thứ hai: thành viên mới ở múi giờ khác

**Bối cảnh:** Thành viên B làm ở múi giờ khác và chỉ có hai giờ giao nhau với phần lớn đồng đội. Người hỗ trợ onboarding có nhiều cuộc họp. B cần hiểu luồng API đăng ký và thực hiện một sửa lỗi nhỏ.

### 24.1. Cách tiếp cận gây chậm

1. B đọc một tài liệu onboarding không có điểm bắt đầu.
2. Tài liệu ghi JDK khác với pipeline.
3. B gửi câu hỏi trong chat, phải đợi qua đêm.
4. Khi nhận câu trả lời, người hỗ trợ chỉ gửi một lệnh không giải thích.
5. B lặp lại câu hỏi ở hạng mục tiếp theo vì chưa hiểu bối cảnh.

### 24.2. Cách tiếp cận cải tiến

1. **Start here:** B tìm được repo, Product Goal và đường xin quyền.
2. **Quickstart được thử:** B build/test trong môi trường được hỗ trợ.
3. **Domain guide:** B hiểu ý nghĩa trạng thái “yêu cầu đã nhận” và “đã xác nhận”.
4. **ADR/test:** B thấy vì sao phải bảo vệ transaction và cách kiểm chứng.
5. **Async question tốt:** B ghi rõ lỗi, điều đã thử và link, người ở múi giờ khác có thể trả lời có ngữ cảnh.
6. **Pairing trong giờ giao nhau:** Hai người xử lý phần còn mơ hồ và tạo một PR nhỏ.
7. **Đóng vòng:** B cập nhật quickstart ở chỗ bị sai, để người sau không vướng lại.

### 24.3. Đánh giá hiệu quả

Không hỏi “B onboard chậm hơn người khác bao nhiêu phần trăm?” mà hỏi:

- B đã **tự tìm được nguồn đúng** chưa?
- Câu hỏi nào vẫn phụ thuộc người đang ngủ?
- Trang nào lỗi thời hoặc thiếu quyền?
- Người hỗ trợ có thể dành thời gian cho kỹ năng và quyết định khó thay vì câu hỏi lặp?
- B có thể thực hiện thay đổi nhỏ đạt kiểm chứng cùng đồng đội?

**Độ độc lập tăng dần** không mâu thuẫn với việc được hỗ trợ; quá ít tương tác cũng có thể khiến hiểu lầm kéo dài.

## 25. Tình huống thứ ba: thay đổi gấp khi người quyết định vắng mặt

Một đối tác báo sẽ thay đổi giới hạn gọi API vào cuối tuần. Product Owner đang nghỉ, nhóm phát triển cần bảo đảm đăng ký workshop không bị lỗi hàng loạt.

### 25.1. Phân biệt ba loại quyết định

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Vận hành khẩn trong giới hạn đã ủy quyền** | Bật cơ chế giảm tải an toàn đã được phê duyệt | Thực hiện theo runbook, ghi timeline, thông báo phù hợp |
| **Thay đổi kỹ thuật trong phạm vi nhóm** | Điều chỉnh timeout/retry theo kiểm chứng và chính sách | Review, test, CI, ghi quyết định có rủi ro |
| **Thay đổi sản phẩm hoặc cam kết lớn** | Bỏ Must Have hoặc thay ngày giao bắt buộc | Đưa tới người có thẩm quyền hoặc cơ chế ủy quyền thay thế |

**Một runbook không tự tạo thêm quyền quyết định**. Nếu người trực thay chưa được ủy quyền sửa dữ liệu hoặc thay chính sách sản phẩm, tài liệu phải dẫn họ tới đúng cấp quyết định, không mô tả một phím tắt vượt quyền.

### 25.2. Sau khi quyết định

Nhóm lưu:

1. Bằng chứng đối tác thay đổi.
2. Rủi ro và phương án đã cân nhắc.
3. Quyết định với người có thẩm quyền.
4. Các PR/config, kết quả test và hệ quả vận hành.
5. Việc cần Product Owner hoặc người khác xem lại khi trở lại.

Như vậy **người vắng mặt có thể hiểu chuỗi quyết định**, không cần tin vào lời kể rời rạc.

## 26. “Không có tài liệu” và “tài liệu sai” cần xử lý khác nhau

Một hướng dẫn thiếu thông tin khiến người đọc phải hỏi. Một hướng dẫn **sai nhưng trình bày rất tự tin** có thể nguy hiểm hơn, nhất là khi liên quan tới data migration, quyền hoặc khôi phục.

### 26.1. Phân loại lỗi tài liệu

| Phát hiện | Mức quan tâm | Hành động |
| --- | --- | --- |
| Thiếu liên kết tới test | Có thể chặn onboarding | Bổ sung tại điểm vào, liên kết nguồn đúng |
| Thuật ngữ mơ hồ | Có thể tạo hiểu sai nghiệp vụ | Thêm ví dụ và định nghĩa từ người có chuyên môn |
| Lệnh build lỗi thời | Chặn nhiều người mới | Sửa và chạy thử trong môi trường sạch |
| Sai đường dẫn dashboard | Chậm chẩn đoán | Cập nhật runbook, thử với người dự phòng |
| Hướng dẫn thao tác production sai | Có thể gây sự cố, mất dữ liệu | **Ngừng áp dụng, đánh dấu không an toàn, báo đúng thẩm quyền, kiểm chứng lại** |
| Link ADR cũ không chỉ sang quyết định mới | Có thể khiến áp dụng giải pháp lỗi thời | Ghi superseded, liên kết ADR mới và điều kiện áp dụng |
| Tài liệu chứa secret | Rủi ro an toàn thông tin | Theo quy trình bảo mật, thu hồi/luân chuyển nếu đã lộ, hạn chế phân phối |

### 26.2. Đừng giải quyết tài liệu lỗi bằng lời nhắc mơ hồ

“Mọi người cần cập nhật wiki thường xuyên hơn” không đủ. Hãy tìm:

- Thay đổi nào tạo ra thông tin sai?
- Vì sao cập nhật tài liệu không nằm trong review/DoD phù hợp?
- Có quá nhiều bản sao không?
- Owner có rõ và có quyền sửa không?
- Có bài thử hoặc linter nào có thể phát hiện sớm?
- Cần thông báo ai về thay đổi rủi ro cao?

### 26.3. Khi chưa đủ bằng chứng, nêu rõ độ chắc chắn

Nếu runbook mới chỉ được xem lại trên giấy, hãy ghi **“chưa diễn tập trên môi trường tương ứng”** thay vì “đã được kiểm chứng đầy đủ”. Khi bối cảnh sản phẩm đổi, cần biết phần nào đã thử, phần nào là giả định.

## 27. Tích hợp học hỏi sau sự cố và Retrospective vào kho kiến thức

Một sự cố có thể giúp nhóm học ra giới hạn hệ thống. Nhưng vòng học sẽ bị hở nếu kết luận chỉ nằm trong một cuộc họp postmortem rồi không thay đổi tài liệu, test hoặc cách làm.

### 27.1. Từ sự cố tới hành động có thể kiểm chứng

Ví dụ sau timeout đăng ký:

1. **Phát hiện:** Alert và Support ghi nhận lỗi.
2. **Ứng phó:** Giảm tác động, bảo vệ dữ liệu và người dùng.
3. **Điều tra:** Xác định service phụ thuộc làm tăng độ trễ; một bước retry có nguy cơ gây yêu cầu lặp.
4. **Quyết định:** Điều chỉnh cách xử lý retry/idempotency theo thiết kế đã được kiểm chứng.
5. **Cập nhật kiến thức:** ADR/rủi ro, runbook, testing guide, cảnh báo.
6. **Tạo test:** Bổ sung kiểm chứng trường hợp timeout và retry.
7. **Thực hành:** Người dự phòng thử chẩn đoán và nêu điều kiện escalation.
8. **Xem lại:** Tình huống còn tái diễn không, thời gian phát hiện và tác động ra sao?

### 27.2. Sprint Retrospective là một điểm điều chỉnh cách làm

Scrum Team có thể hỏi:

- Kiến thức nào thường khiến PBI bị blocked?
- Có quyết định nào bị lặp lại vì không tìm được bản ghi?
- Người mới hoặc người nghỉ trở lại có gặp cùng trở ngại?
- Ta nên **ngừng tạo loại tài liệu nào** vì ít giá trị?
- Một thay đổi nhỏ nào sẽ giúp việc cập nhật tài liệu diễn ra cùng code/test?

Không phải chờ Retrospective mới sửa runbook sai nguy hiểm. Những vấn đề tác động người dùng hoặc an toàn cần được xử lý **ngay khi phát hiện**.

## 28. Cân bằng độ đầy đủ với khả năng duy trì

Kiến thức có giá trị khi **người đọc hoàn thành tác vụ an toàn**. Một kho quá dài có thể làm người mới ngợp, còn một kho quá ngắn có thể giấu nguy cơ.

### 28.1. Tầng thông tin

Một cấu trúc hữu ích:

1. **Trang đầu 1–2 phút:** Mục tiêu, người dùng, điểm vào, các đường liên kết quan trọng.
2. **Quickstart theo tác vụ:** Các bước có thể thực hiện ngay với điều kiện trước.
3. **Giải thích ngữ cảnh:** ADR, domain guide, sơ đồ kiến trúc.
4. **Thông tin chuyên sâu:** Test, contract, cảnh báo, cơ chế dữ liệu, postmortem.
5. **Lịch sử:** Quyết định đã thay, tài liệu cũ có cảnh báo rõ.

Người đọc có thể dừng ở đúng tầng cần thiết mà không phải duyệt toàn bộ kho.

### 28.2. Không tự động hóa hình thức

Một trang tự sinh từ schema có thể rất chính xác về tên trường nhưng thiếu **ý nghĩa nghiệp vụ**. Một sơ đồ luôn tạo lại từ mã có thể đầy đủ kết nối nhưng không giúp hiểu **vì sao hệ thống được chia như vậy**.

Kết hợp:

- **Generated reference** cho phần máy có thể trích xuất đúng.
- **Human explanation** cho mục đích, trade-off và ngữ cảnh.
- **Tests/examples** cho hành vi có thể kiểm chứng.
- **Liên kết tới phiên bản** để tránh lẫn tài liệu của release khác.

### 28.3. “Đúng lúc” tốt hơn “viết cho mọi khả năng”

Đừng yêu cầu mô tả hàng trăm trường hợp giả định chưa có nhu cầu. Nhưng với **những rủi ro đã biết như mất dữ liệu, phân quyền và khôi phục**, cần đủ thông tin trước khi chúng trở thành tình huống thật.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| “Agile là không cần tài liệu” | Kiến thức chỉ trong trí nhớ người có kinh nghiệm | Tài liệu vừa đủ để hợp tác và vận hành |
| “Càng nhiều trang wiki càng tốt” | Kho phình to, khó tìm và lỗi thời | Đo khả năng tự thực hiện tác vụ |
| “Ghi toàn bộ chat là xong” | Không có kết luận và nguồn sự thật | Tóm tắt quyết định, lý do và liên kết |
| “Có link nghĩa là người mới hiểu” | Link chết, thiếu quyền hoặc thiếu bối cảnh | Thử đọc và làm theo bằng người mới |
| “Tài liệu thay thế mọi tương tác” | Người mới bị cô lập, sai lầm kéo dài | Mentoring, review và pairing theo nhu cầu |
| “Hỏi người nghỉ phép là cách nhanh nhất” | Tăng phụ thuộc, không tôn trọng nghỉ ngơi | Handoff, người dự phòng và runbook |
| “Nếu tác giả ADR nghỉ thì không ai được sửa” | Trách nhiệm kẹt ở một người | Owner theo nhóm và quy tắc superseding |
| “Chỉ cần có runbook, không cần diễn tập” | Quyền/lệnh lỗi thời không được phát hiện | Kiểm tra trong môi trường an toàn |
| “Chạy theo runbook được quyền làm mọi thứ” | Vượt thẩm quyền, nguy cơ dữ liệu | Điều kiện trước, quyền và escalation rõ |
| “Bí mật để trong wiki nội bộ vẫn ổn” | Secret có thể lộ qua chia sẻ và lịch sử | Secret manager, quyền tối thiểu |
| “Nguồn sự thật là copy vào mọi công cụ” | Các bản sao mâu thuẫn | Một bản chính, nơi khác liên kết |
| “Meeting note càng chi tiết càng tốt” | Khó rút quyết định từ transcript dài | Nêu kết luận, owner, việc tiếp, giới hạn |
| “Không trả lời async là đồng ý” | Người ngủ/vắng bị mất quyền tham gia | Kỳ vọng phản hồi và thẩm quyền rõ |
| “Docs-as-code nghĩa là mọi tài liệu ở Git public” | Lộ thông tin nhạy cảm | Đặt nội dung theo nhu cầu truy cập |
| “Link checker xanh chứng minh tài liệu đúng” | Nội dung có thể sai nghiệp vụ hoặc môi trường | Review và thử thực tế |
| “Mọi PBI phải có ADR mới” | Quan liêu và tài liệu trùng lặp | Chọn theo tầm ảnh hưởng quyết định |
| “Cập nhật tài liệu để Sprint sau” | Người nghỉ/trực thay dùng hướng dẫn cũ | Gắn cập nhật thiết yếu với thay đổi |
| “Bus factor thấp nghĩa là người đó phải làm cả kỳ nghỉ” | Càng làm tăng rủi ro tập trung | Chia sẻ kiến thức, người dự phòng |
| “Hướng dẫn một lần là người mới phải tự xử lý hết” | Che điểm thiếu của hệ thống onboarding | Buddy, thực hành và phản hồi |
| “Dùng số trang viết để chấm Developer” | Tạo tài liệu dài ít ai dùng | Đo tính hữu ích cấp nhóm |
| “Runbook copy lệnh sửa production là càng chi tiết càng tốt” | Có thể gây hại nếu thiếu điều kiện trước | Quyền, cảnh báo, kiểm chứng và phê duyệt |
| “Người mới không hiểu tức người mới kém” | Không cải tiến tài liệu mơ hồ | Test khả năng sử dụng thông tin |
| “Bỏ tài liệu cũ là mất mọi kiến thức thừa” | Không truy vết được quyết định lịch sử | Ghi deprecated/superseded và liên kết |
| “Họp nhiều là đã chia sẻ tri thức” | Người vắng không biết kết quả | Bản ghi có quyết định, lý do và việc tiếp |

## 30. Bài tập 1 — Tìm điểm phụ thuộc tri thức nguy hiểm

**Tình huống:** Một nhóm có sáu người phát triển dịch vụ đăng ký. A biết toàn bộ giao dịch và dữ liệu; B biết cách chạy CI; C quản lý tài liệu UI; D hiểu quy tắc nghiệp vụ; E trực vận hành; F mới gia nhập.

Quan sát:

- Chỉ A biết cách khôi phục dữ liệu khi có ghi trùng.
- Runbook của E chứa dashboard cũ.
- CI đã đổi JDK nhưng README do B viết chưa cập nhật.
- Quy tắc hủy workshop do D giải thích trong họp nhưng không có ví dụ chấp nhận.
- F phải hỏi ba người mới biết chạy test tích hợp.
- C có tài liệu rõ nhưng chưa liên kết từ trang onboarding.

### Câu hỏi

1. Những rủi ro nào có thể **gây hại người dùng**, những rủi ro nào chủ yếu gây **chậm onboarding**?
2. Chọn **ba việc ưu tiên đầu** và giải thích thứ tự.
3. Với cơ chế khôi phục dữ liệu, cần ADR, runbook hay thực hành nào? Vì sao?
4. Có nên copy lệnh sửa production từ chat của A vào README chung không?
5. Sửa trang Start here có thể giảm bao nhiêu loại câu hỏi?
6. Làm sao biết tài liệu sau sửa **thực sự sử dụng được**, không chỉ có thêm trang?
7. Ai nên là owner của các tài liệu này khi người ban đầu vắng?
8. Mẫu nào phù hợp để kiểm tra mức giảm phụ thuộc mà không xếp hạng cá nhân?

### Gợi ý hướng giải

**Ưu tiên rủi ro mất dữ liệu và khả năng khôi phục**, vì hậu quả lớn và tri thức tập trung. A nên cùng người dự phòng xây runbook/kiểm chứng trong môi trường an toàn theo đúng thẩm quyền; ADR lưu lý do thiết kế giao dịch nếu cần. Tiếp theo, sửa runbook dashboard, cập nhật toolchain và đường chạy integration tests, gắn vào nguồn chính. Domain guide nên có ví dụ hủy để F và những người khác hiểu đúng nghiệp vụ.

**Không copy lệnh sửa production thiếu điều kiện trước** vào README công khai. Kiểm chứng bằng **người chưa quen quy trình thử từ điểm vào**, ghi bước bị chặn và sửa chỗ thiếu.

## 31. Bài tập 2 — Viết handoff khi nghỉ phép

**Đề bài:** Bạn chuẩn bị nghỉ hai tuần. PBI “Đăng ký chỗ cuối” đã có code nhưng chưa đạt DoD vì integration test đồng thời chưa chạy trên môi trường phù hợp. Một đối tác có thể đổi API ngày thứ Tư tuần sau. Người dự phòng có thể review backend nhưng chưa được cấp quyền xem một dashboard vận hành.

### Yêu cầu

Viết một bản handoff với:

1. Mục tiêu Sprint/Product Goal có liên quan.
2. **Trạng thái thực** của PBI, không gọi Done sai.
3. Link PR, test, ADR hoặc tài liệu chính cần đọc.
4. Rủi ro và mốc đối tác thay đổi.
5. Quyền còn thiếu và cách yêu cầu quyền đúng.
6. Người/nhóm dự phòng, giới hạn quyền quyết định.
7. Tín hiệu cần kích hoạt quy trình incident.
8. Bước kiểm chứng khi bạn trở lại.
9. Cách bảo đảm không cần liên hệ bạn trong kỳ nghỉ cho việc thường.

### Gợi ý cách làm

Không phải ghi lại toàn bộ lịch sử hai tuần trước; cần **trạng thái mới nhất, đường đi tới nguồn sự thật, người thay và quyết định mở**. Nếu quyền xem dashboard chưa được cấp, **không bàn giao giả định rằng người dự phòng đã có quyền**.

## 32. Bài tập 3 — ADR, runbook hay FAQ?

Hãy chọn loại tài liệu phù hợp nhất cho mỗi tình huống và giải thích.

| Tình huống | Loại thường phù hợp | Lý do |
| --- | --- | --- |
| Vì sao dùng transaction ở database để chống xác nhận vượt sức chứa | **ADR** | Cần lý do kiến trúc, phương án và hệ quả |
| Alert timeout bất thường, người trực cần chẩn đoán an toàn | **Runbook** | Cần bước hành động, quyền, điều kiện dừng và escalation |
| Người mới không biết chạy test tích hợp | **Testing guide/Quickstart** | Cần bước cấu hình và kiểm chứng có thể lặp |
| Người dùng thường nhầm “đã gửi yêu cầu” với “đã xác nhận” | **Domain guide/FAQ + acceptance examples** | Cần định nghĩa nghiệp vụ và ví dụ |
| Product Owner đổi thứ tự tính năng và có lý do từ phản hồi người dùng | **Product Backlog + decision note** | Cần quyết định có hiệu lực và đường truy vết |
| Một ADR cũ không còn hiệu lực | **ADR mới/supersedes + liên kết lịch sử** | Không xóa ngữ cảnh đã có |
| Nhà cung cấp đổi API, có nhiều consumer | **Contract/update note + targeted announcement** | Người bị ảnh hưởng cần biết thay đổi và việc cần làm |

**Một tình huống có thể cần nhiều tài liệu bổ trợ**, nhưng không nên copy cùng nội dung dài sang bảy nơi rồi mỗi nơi được sửa một kiểu.

## 33. Bài tập 4 — Thiết kế thử nghiệm giảm thời gian chờ người khác

**Bối cảnh:** Nhóm phân tán nhận thấy trung bình mỗi tuần có nhiều câu hỏi lặp “Chạy integration test như thế nào?” và người trực thay thường chờ một ngày mới có đường dẫn dashboard. Không có dữ liệu đáng tin về thời gian tìm câu trả lời.

### Yêu cầu

1. Viết **giả thuyết cải tiến** có thể kiểm chứng trong hai Sprint.
2. Chọn **hai công việc tài liệu nhỏ** có tác động trực tiếp.
3. Xác định một bài thử người mới và một bài thử người dự phòng.
4. Chọn dữ liệu về **thời gian chờ, câu hỏi lặp và tính đúng của hướng dẫn**.
5. Nêu guardrail về **quyền truy cập, bảo mật và chất lượng**.
6. Làm sao giảm thiên lệch khi chỉ chọn người quá quen repo để thử?
7. Nếu thời gian tìm câu trả lời giảm nhưng lỗi production tăng, kết luận gì?
8. Nên quyết định giữ, sửa hay bỏ thực hành mới bằng cách nào?

### Gợi ý hướng giải

**Giả thuyết:** Nếu có điểm vào rõ, quickstart đã được thử và runbook có người dự phòng được cấp quyền đúng, **thời gian bị chặn vì thông tin có thể giảm** mà không tăng sai thao tác.

**Thử nghiệm:** Một người chưa biết quy trình thực hiện nhiệm vụ với hướng dẫn; một người dự phòng thử chẩn đoán ở môi trường an toàn. Ghi chỗ bị chặn, số câu hỏi lặp và tình trạng link/quyền; không biến tốc độ của người thử thành KPI cá nhân.

**Guardrail:** Không tiết lộ secret, không cấp quyền quá mức, không bỏ test và không dùng runbook để thao tác production thiếu phê duyệt. Nếu lỗi tăng, cần kiểm tra **tính đúng, rủi ro và khả năng áp dụng thực tế của kiến thức**, không chỉ nhìn số trang tài liệu được đọc.

## 34. Checklist tự đánh giá kho kiến thức của nhóm

Đây là mẫu **học tập và cải tiến**, không phải artifact bắt buộc của Scrum, Kanban hoặc XP.

~~~text
DIEM VAO / TIM KIEM
[ ] Co mot "Start here" de tim dung loai thong tin?
[ ] Nguoi moi tim duoc repo, Product Goal, test va kenh ho tro?
[ ] Cac noi tom tat co lien ket ve nguon chinh?
[ ] ADR/runbook/tai lieu cu co canh bao khi khong con hieu luc?

NOI DUNG THIET YEU
[ ] Quickstart co the thuc hien trong moi truong duoc ho tro?
[ ] Domain guide co thuat ngu va vi du nghiep vu quan trong?
[ ] ADR ghi duoc vi sao va khi nao can xem lai?
[ ] Runbook co dieu kien, quyen, buoc an toan, thanh cong va escalation?
[ ] Testing guide dan toi cac suite rui ro cao?
[ ] Product Backlog va quyet dinh thay doi co duong truy vet?

NGUOI VANG MAT / ASYNC
[ ] Work item dang mo co trang thai trung thuc?
[ ] Handoff co rui ro, blocker, link va nguoi thay?
[ ] Khong phu thuoc nguoi dang nghi de xu ly viec thuong?
[ ] Working agreement noi ro gio giao nhau, do khan, kenh phan hoi?
[ ] Quy trinh incident khong bi thay bang chat async thuong?

BAO MAT / QUYEN
[ ] Khong copy mat khau, token, PII vao tai lieu?
[ ] Co cach xin quyen dung thay vi tai khoan chia se?
[ ] Tai lieu nhay cam duoc phan quyen phu hop?
[ ] Nguoi du phong da kiem tra quyen truoc khi can?
[ ] Khong co lenh gay tac dong production thieu dieu kien va tham quyen?

DUY TRI / KIEM CHUNG
[ ] Co owner hoac nhom chiu trach nhiem va nguoi thay?
[ ] Co trigger cap nhat khi API, build, quy trinh van hanh doi?
[ ] Co phan hoi khi tai lieu sai/hong lien ket?
[ ] Nguoi moi/nguoi du phong da thu lam theo?
[ ] Co thong bao toi nhom bi anh huong khi quyet dinh quan trong doi?
[ ] Nhom xem lai tac dong toi flow, DoD, incident va chat luong?
~~~

Đừng dùng checklist để yêu cầu mỗi Developer viết nhiều trang hơn. Nên chọn **một hoặc hai khoảng trống khiến người khác bị chặn rõ nhất** và thử cải thiện trong chu kỳ tiếp theo.

## 35. Câu hỏi tự kiểm tra

1. Vì sao nhóm phân tán dễ bị mất ngữ cảnh hơn khi người giữ thông tin vắng mặt?
2. Kiến thức ngầm khác kiến thức đã được viết ra ở điểm nào?
3. Vì sao một runbook chưa được người dự phòng thực hành vẫn có rủi ro?
4. Một tài liệu dễ tìm nhưng sai phiên bản có thể gây hậu quả gì?
5. Những loại tài liệu nào là tối thiểu có ích cho onboarding một repo mới?
6. “Single source of truth” có yêu cầu tất cả nội dung phải ở cùng một công cụ không?
7. ADR khác runbook và decision log như thế nào?
8. Khi một ADR không còn đúng, tại sao nên giữ lịch sử và tạo đường dẫn tới quyết định mới?
9. Trong bản handoff nghỉ phép, những trạng thái và rủi ro nào cần ghi rõ?
10. Nếu thành viên đột ngột vắng mặt mà không thể bàn giao, nhóm nên dựa vào cấu trúc nào đã có?
11. Vì sao “người không phản hồi trong hai giờ coi như đồng ý” có thể bất công hoặc không an toàn?
12. Trường hợp nào cần kênh xử lý đồng bộ hoặc incident thay vì chờ trao đổi bất đồng bộ?
13. Những nội dung nào tuyệt đối không nên đưa vào README hoặc wiki chia sẻ rộng?
14. Làm sao bảo đảm người trực thay có quyền đúng mà không dùng tài khoản của đồng nghiệp?
15. Tài liệu nào nên cập nhật khi thay đổi transaction giữ chỗ cuối của workshop?
16. Vì sao có thể xem cập nhật kiến thức thiết yếu là một phần của hoàn tất PBI?
17. Scrum có bắt buộc mọi PBI phải có ADR mới hoặc một trang wiki mới không?
18. Làm sao kiểm tra tài liệu còn đúng ngoài việc chạy link checker?
19. Vì sao số trang hoặc số lần chỉnh sửa wiki không phù hợp làm KPI cá nhân?
20. Nêu hai tín hiệu cho biết người mới có thể tự phục vụ hiệu quả hơn.
21. Giả sử tài liệu hướng dẫn sửa dữ liệu sai, thứ tự hành động an toàn là gì?
22. Khi Support phát hiện hướng dẫn cũ khiến người dùng nhầm, thông tin nên đi theo đường nào?
23. Một sự cố chỉ được thảo luận trong Retrospective nhưng không đổi test/runbook có được coi là đã học đầy đủ không?
24. Làm sao kết hợp tài liệu với pairing, review và mentoring để tránh cả phụ thuộc cá nhân lẫn cô lập người mới?

## 36. Ghi nhớ và vận dụng

**Lưu trữ kiến thức để hỗ trợ thành viên mới và người vắng mặt** không phải mục tiêu “viết nhiều tài liệu”. Đó là năng lực của một nhóm Agile phân tán để **tiếp tục phối hợp, đưa ra quyết định đúng và vận hành an toàn khi người nắm ngữ cảnh ban đầu không có mặt**.

Những nguyên tắc cốt lõi:

1. **Bắt đầu từ rủi ro bị chặn hoặc gây hại:** Ưu tiên tri thức quan trọng tới chất lượng, dữ liệu, quyết định và vận hành.
2. **Để người đọc tìm được nguồn đúng:** Có điểm vào, liên kết rõ và tránh nhiều bản chính mâu thuẫn.
3. **Lưu cả lý do lẫn bước làm:** ADR cho trade-off, runbook cho hành động, domain guide cho quy tắc và handoff cho trạng thái.
4. **Tài liệu cần được thử:** Người mới hoặc người dự phòng phải có thể làm theo trong môi trường an toàn và nhận hỗ trợ khi cần.
5. **Gắn cập nhật tri thức với thay đổi:** Code, test, quy tắc nghiệp vụ và tài liệu thiết yếu nên cùng được xem xét khi PBI thay đổi.
6. **Giữ trách nhiệm, phiên bản và đường escalation:** Người nghỉ được nghỉ, người thay thế có thẩm quyền và thông tin phù hợp.
7. **Bảo vệ dữ liệu và quyền truy cập:** Tài liệu rõ không có nghĩa công khai secret hoặc bỏ kiểm soát production.
8. **Đo tính hữu ích, không đếm số trang:** Quan sát thời gian chờ, khả năng hoàn tất an toàn, chất lượng và trải nghiệm người đọc.
9. **Duy trì tương tác giữa con người:** Pairing, review và trao đổi chuyên môn vẫn cần thiết để truyền kiến thức ngầm.
10. **Khép kín vòng học hỏi:** Phản hồi từ người mới, incident và retrospective phải dẫn tới quyết định, cập nhật và kiểm chứng lại.

Trước khi kết thúc một ngày làm việc hoặc một Sprint, hãy hỏi: **“Nếu người đang hiểu rõ việc này vắng mặt từ ngày mai, đồng đội có tìm được trạng thái thật, lý do quyết định, cách kiểm chứng an toàn và người có thẩm quyền để tiếp tục không?”** Nếu chưa, đó là cơ hội cải tiến cụ thể để nhóm **giảm chờ, giữ chất lượng, giao Increment tăng dần và thích ứng thông qua phản hồi sớm**.
