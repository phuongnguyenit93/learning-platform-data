# User story: Cấu trúc người dùng, nhu cầu và lợi ích trong mô tả câu chuyện

Một **user story (câu chuyện người dùng)** giúp nhóm phát triển hiểu **ai cần một khả năng, họ muốn làm được gì và vì sao điều đó có ích**. Chẳng hạn, câu “làm màn hình đăng ký workshop” mô tả việc cần xây dựng nhưng chưa cho biết người dùng đang gặp khó khăn gì. Khi diễn đạt từ góc nhìn người dùng, nhóm có cơ sở trao đổi, lựa chọn giải pháp, chia công việc nhỏ, bàn giao sớm và kiểm chứng kết quả.

Trong mô-đun **AGILE_DEVELOPMENT**, viết user story là một thực hành hỗ trợ tư duy Agile: giao phần mềm có giá trị theo từng phần, nhận phản hồi sớm và cải tiến liên tục. User story có thể phối hợp với Product Backlog, Scrum, Kanban, các kỹ thuật XP và đo lường dòng công việc. Tuy nhiên, **một câu đúng mẫu ngữ pháp chưa bảo đảm đúng nhu cầu**. Giá trị đến từ việc đặt câu hỏi, trao đổi với người liên quan và dùng bằng chứng thực tế để điều chỉnh.

Bài này tập trung vào cấu trúc **người dùng – nhu cầu – lợi ích**, cách viết từng thành tố và kiểm tra mối liên hệ giữa chúng. Các ví dụ sử dụng một sản phẩm giả định: hệ thống đăng ký workshop dành cho học viên và ban tổ chức.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa ba thành tố **Who** (ai), **What** (muốn làm gì) và **Why** (để đạt lợi ích gì).
2. Chọn vai trò người dùng đủ cụ thể, phân biệt người sử dụng trực tiếp, người vận hành và người ra quyết định.
3. Viết nhu cầu thành một hành vi hoặc kết quả có thể quan sát, tránh mô tả sớm cách lập trình.
4. Nêu lợi ích có ý nghĩa, phân biệt lợi ích người dùng với mục tiêu nghiệp vụ và giả thuyết chưa được xác minh.
5. Phát hiện story mơ hồ, lệch vai trò, thiếu giá trị hoặc chứa nhiều hành vi; biết cách đặt câu hỏi để sửa.
6. Dùng story làm cơ sở cho **Conversation**, **Confirmation**, tiêu chí chấp nhận, phân rã và đánh giá theo INVEST.
7. Liên hệ lời hứa trong phần Why với bằng chứng sau bàn giao để điều chỉnh Product Backlog.

## 2. Mẫu câu Who – What – Why

Mẫu thường dùng:

> **Là** [người dùng hoặc vai trò], **tôi muốn** [nhu cầu hoặc khả năng], **để** [lợi ích hoặc mục đích].

Tương đương tiếng Anh: *As a [type of user], I want [some goal], so that [some benefit]*. Đây là **cách ghi nhớ phổ biến**, không phải cú pháp bắt buộc trong Agile hoặc Scrum.

Ví dụ:

> **Là học viên lần đầu đăng ký workshop**, tôi muốn **xem những buổi còn chỗ và gửi yêu cầu đăng ký trực tuyến**, để **chủ động chọn thời gian phù hợp mà không cần nhắn hỏi ban tổ chức**.

| Thành tố | Câu hỏi chính | Trong ví dụ | Tác dụng |
| --- | --- | --- | --- |
| **Who – Người dùng** | Ai đang cần? Trong bối cảnh nào? | Học viên lần đầu đăng ký workshop | Chọn góc nhìn, đối tượng trao đổi và kiểm tra |
| **What – Nhu cầu** | Họ muốn làm được gì? | Xem buổi còn chỗ và gửi yêu cầu | Nêu hành vi người dùng nhận biết được |
| **Why – Lợi ích** | Họ được lợi gì khi làm được điều đó? | Chủ động chọn thời gian, giảm hỏi thủ công | Giúp ưu tiên và đánh giá kết quả |

Ba phần phải **liên kết về mặt nguyên nhân**: người dùng đã chọn thực sự có nhu cầu đó; hành vi giải quyết một vấn đề của họ; lợi ích nêu được tại sao hành vi đáng làm. Nếu thay Who bằng “nhân viên kế toán” mà What vẫn là tự đăng ký workshop, story có thể đã chọn sai góc nhìn. Nếu Why chỉ lặp lại What, nhóm chưa biết giá trị nằm ở đâu.

### 2.1. Story ngắn không có nghĩa bỏ qua chi tiết quan trọng

Mẫu Who–What–Why giúp ghi phần cốt lõi lên một thẻ trong Product Backlog. Khi thực hiện, nhóm vẫn cần trao đổi về quy tắc nghiệp vụ, quyền truy cập, ngoại lệ, kiểm thử, Definition of Done và cách đo lợi ích. Đừng cố nhét toàn bộ chi tiết vào một câu duy nhất khiến story khó đọc.

Không nhất thiết phải mở đầu mọi backlog item bằng “Là…”. Một câu tự nhiên như “Học viên xem được trạng thái đăng ký của mình để không phải hỏi lại ban tổ chức” vẫn có thể là story hữu ích nếu nhóm hiểu cùng ba thành tố và có cuộc trao đổi đầy đủ.

## 3. Who: xác định người dùng và hoàn cảnh

### 3.1. “Người dùng” có thể có nhiều vai trò

Một sản phẩm có thể phục vụ:

- **Người sử dụng trực tiếp:** học viên tìm buổi học và đăng ký.
- **Người vận hành:** điều phối viên xét yêu cầu, kiểm soát số chỗ, xử lý hủy.
- **Người mua hoặc ra quyết định:** đại diện đơn vị tổ chức quan tâm chi phí, trải nghiệm và hiệu quả.
- **Người chịu tác động:** giảng viên nhận danh sách tham dự và chuẩn bị nội dung.

Một người có thể mang nhiều vai trò ở các tình huống khác nhau. **Vai trò trong story mô tả góc nhìn về một mục tiêu**, không nhất thiết trùng tên chức danh hoặc vai trò phân quyền đã lập trình.

| Cách ghi Who | Vấn đề thường gặp | Cách làm rõ |
| --- | --- | --- |
| “Là người dùng…” | Không biết hỏi ai, kiểm tra trong bối cảnh nào | “Là học viên đang chọn workshop đầu tiên…” |
| “Là admin…” | Chỉ nói tên quyền tài khoản, chưa nói công việc | “Là điều phối viên phụ trách xác nhận đăng ký…” |
| “Là khách hàng…” | Có thể là người trả tiền, người dùng hoặc bên liên quan khác | Xác định ai thật sự thực hiện hành vi trong What |
| “Là học viên dùng điện thoại…” | Có ích khi hạn chế thiết bị ảnh hưởng nhu cầu | Chỉ nêu thiết bị nếu có tác động thực sự |
| “Là hệ thống…” | Dễ che giấu ai hưởng lợi | Xem có thể mô tả người/dịch vụ thụ hưởng hoặc dùng backlog item kỹ thuật |

Không nên mô tả quá chi tiết khi chưa có bằng chứng: một story hiếm khi cần tuổi chính xác, loại điện thoại và địa chỉ của một người để xác định nhu cầu. Chỉ giữ những đặc điểm ảnh hưởng đến mục tiêu, giới hạn hoặc cách kiểm chứng.

### 3.2. Vai trò, persona và phân khúc

**Vai trò (role)** là mục đích hoặc trách nhiệm trong quá trình sử dụng, chẳng hạn học viên hoặc điều phối viên.

**Persona** là hồ sơ đại diện cho nhóm người dùng với mục tiêu, hành vi, trở ngại và bối cảnh. Persona có giá trị khi dựa trên nghiên cứu; persona tự nghĩ ra là **giả thuyết cần kiểm tra**, không phải sự thật về tất cả người dùng.

**Phân khúc** phân biệt những nhóm có hành vi liên quan, như học viên đăng ký lần đầu và học viên tham dự thường xuyên. Cả hai cùng vai trò học viên nhưng nhu cầu có thể khác:

- Người lần đầu cần hiểu **“đã tiếp nhận”** khác **“đã xác nhận chỗ”** như thế nào.
- Người tham dự thường xuyên có thể muốn kiểm tra nhanh những đăng ký đã gửi.

Chỉ nên tách thành các story riêng khi khác biệt tạo ra hành vi, quy tắc hoặc lợi ích cần kiểm chứng khác nhau. Đừng tạo thêm một thẻ cho mỗi persona chỉ vì có nhiều hồ sơ người dùng.

### 3.3. Câu hỏi để chọn Who

1. **Ai** gặp vấn đề hoặc hưởng lợi trực tiếp từ khả năng được nêu?
2. **Khi nào** họ gặp vấn đề đó?
3. Có vai trò khác với quyền hoặc mục tiêu khác đáng kể không?
4. Nhóm có thể **quan sát hoặc trao đổi với ai** để xác minh nhu cầu?
5. Việc chọn vai trò có làm rõ yêu cầu về quyền truy cập và dữ liệu riêng tư không?

Ví dụ, “xem toàn bộ danh sách người đăng ký” có thể thuộc phạm vi điều phối viên; “xem trạng thái đăng ký của tôi” thuộc phạm vi học viên. Gộp thành “người dùng xem dữ liệu đăng ký” có thể che khuất sự khác biệt quyền và làm sai mục tiêu.

**Dấu hiệu phần Who tốt:** nhóm biết đối tượng cần hỏi, tình huống sử dụng, vai trò liên quan và người cần xác nhận rằng vấn đề thực sự tồn tại.

## 4. What: diễn tả nhu cầu thay vì tác vụ triển khai

### 4.1. Hành vi người dùng và cách triển khai là hai tầng khác nhau

Phần What nên nêu một **khả năng người dùng muốn có**. Chi tiết công nghệ thường là phương án để nhóm xây khả năng đó.

| What ban đầu | Vì sao còn yếu | What theo nhu cầu |
| --- | --- | --- |
| “Tạo bảng dữ liệu đăng ký” | Chỉ là một thao tác phát triển | “Gửi và lưu được yêu cầu đăng ký một buổi” |
| “Viết API POST đăng ký” | Người dùng không tương tác trực tiếp với phương thức HTTP | “Đăng ký một buổi còn chỗ” |
| “Làm nút màu cam nổi bật” | Chốt giải pháp giao diện trước khi hiểu vấn đề | “Nhận ra hành động đăng ký trên trang thông tin buổi học” |
| “Làm dashboard hiện đại” | Không nói người dùng cần biết gì | “Xem số chỗ đã xác nhận và đang chờ theo từng buổi” |
| “Có chức năng CRUD workshop” | Thuật ngữ kỹ thuật che hành vi | “Điều phối viên cập nhật lịch và đóng đăng ký khi buổi đã đủ chỗ” |

Không phải lúc nào giải pháp kỹ thuật cũng nên ẩn. Nếu người dùng thật sự cần xuất CSV để làm việc với một công cụ đã được xác nhận, có thể ghi định dạng CSV vào nhu cầu hoặc tiêu chí chấp nhận. Điều quan trọng là **lý do chọn giải pháp đã rõ**, không chỉ do quen công nghệ.

### 4.2. Nhu cầu cần đủ nhỏ để hiểu và kiểm chứng

Story quá lớn:

> Là học viên, tôi muốn quản lý toàn bộ trải nghiệm workshop, để thuận tiện.

Cụm “quản lý toàn bộ” có thể gồm tìm kiếm, đăng ký, thanh toán, hủy, nhận thông báo và đánh giá. Nhóm không dễ biết khi nào hoàn thành và không thể nhận phản hồi sớm về một hành vi cụ thể.

Các hành vi nhỏ hơn:

1. Xem những workshop còn chỗ vào ngày mong muốn.
2. Gửi yêu cầu đăng ký một workshop.
3. Xem trạng thái của một đăng ký đã gửi.
4. Hủy đăng ký trước hạn cho phép.
5. Xem hướng dẫn tham dự khi đã được xác nhận.

Mỗi hành vi có thể mang lợi ích riêng, nhưng phụ thuộc nghiệp vụ cần được làm rõ. Ví dụ, hệ thống nhận yêu cầu mà **không trả trạng thái hoặc thông báo kết quả** có thể khiến học viên vẫn phải hỏi lại. Vì vậy, lát cắt đầu tiên có thể cần “gửi yêu cầu **và nhận kết quả rõ ràng**”.

### 4.3. Viết bằng động từ và kết quả quan sát được

Động từ như **xem, tìm, chọn, gửi, nhận, sửa, hủy, so sánh, xác nhận** thường tạo điều kiện kiểm thử tốt hơn những từ mơ hồ như “cải thiện”, “tăng cường” hoặc “quản lý tốt hơn” nếu thiếu đối tượng cụ thể.

Hãy hỏi:

- Nếu What đã được thực hiện, người dùng **làm được việc gì**?
- Có thể đưa ra **ví dụ thành công** không?
- Tình huống lỗi hoặc ngoại lệ nào ảnh hưởng trực tiếp đến hành vi?
- Phần này còn chứa nhiều hành vi độc lập không?

Chẳng hạn, “xem trạng thái đăng ký” cần làm rõ trạng thái có những giá trị nào, ai được xem yêu cầu nào và thông tin nào giúp người dùng biết bước tiếp theo. Những câu hỏi đó trở thành nội dung thảo luận trong refinement.

**Dấu hiệu phần What tốt:** người sử dụng có thể nhận biết năng lực mới, nhóm đưa ra được ví dụ kiểm tra, và phạm vi đủ rõ để chia nếu lớn.

## 5. Why: nói rõ giá trị của nhu cầu

### 5.1. Why giải thích tại sao story đáng làm

Phần Why gắn hành vi với **một vấn đề, mục tiêu hoặc thay đổi có ích**.

> Là học viên, tôi muốn xem số chỗ còn lại, để tránh mất công nhập thông tin cho một buổi đã đầy.

Lợi ích được nêu rõ hơn “để tiện lợi” và cung cấp câu hỏi kiểm chứng: học viên có còn phải thử đăng ký những buổi không còn chỗ không?

| Why trong story | Vấn đề | Cách diễn đạt tốt hơn |
| --- | --- | --- |
| “Để có chức năng đăng ký” | Lặp What | “Để gửi yêu cầu mà không cần nhắn tin riêng” |
| “Để trải nghiệm tốt hơn” | Không rõ trải nghiệm nào | “Để biết yêu cầu đã nhận được và bước tiếp theo” |
| “Để tăng doanh thu 200%” | Giả định định lượng chưa có căn cứ | “Để giảm trường hợp học viên bỏ đăng ký vì không rõ còn chỗ” |
| “Để hệ thống dùng công nghệ mới” | Nhầm lựa chọn kỹ thuật với giá trị | “Để người dùng không phải chờ lâu khi mở danh sách lớn”, nếu có bằng chứng |
| “Để điều phối viên không nhập lại thông tin” | Lợi ích vận hành cụ thể | Giữ khi đó thật sự là vấn đề đã quan sát |

Why không bắt buộc có con số, nhưng nên đủ cụ thể để nhóm biết **điều gì cần tốt hơn** và có thể đặt câu hỏi về bằng chứng. Nếu chưa được xác nhận, hãy gọi đó là **giả thuyết giá trị**, tránh trình bày nó như một sự thật đã đo được.

### 5.2. Người dùng và người hưởng lợi có thể khác nhau

Ví dụ:

> Là điều phối viên, tôi muốn xem các yêu cầu đăng ký trùng, để tránh xác nhận vượt số chỗ và làm học viên mất suất.

Người thao tác là điều phối viên; người được bảo vệ là cả điều phối viên và học viên. Story vẫn có thể hợp lý nếu nhóm giải thích được quan hệ nguyên nhân và xác nhận quy trình. Tuy nhiên, nếu What thuộc quyền của kế toán mà Who là học viên, đó là dấu hiệu chọn nhầm vai trò.

Lợi ích có thể ở nhiều tầng:

- **Người dùng:** chủ động chọn buổi học và hiểu trạng thái của mình.
- **Vận hành:** điều phối viên giảm nhập liệu và lỗi trùng chỗ.
- **Kinh doanh:** đơn vị tổ chức phục vụ hiệu quả hơn hoặc giảm chi phí hỗ trợ.

Ba tầng có thể liên quan nhưng không tự động kéo theo nhau. Ví dụ, tính năng có thể làm thao tác gửi đăng ký nhanh hơn nhưng tổng số câu hỏi hỗ trợ vẫn không giảm do thông báo trạng thái khó hiểu.

### 5.3. Why giúp nhóm đàm phán cách giải quyết

Giả sử người đặt hàng nói “cần làm ứng dụng di động riêng để học viên biết workshop bị đổi phòng”. Hỏi “để làm gì?” giúp phát hiện mục tiêu thật là **để người tham dự biết thông tin mới trước giờ học**. Một thông báo qua kênh đã đồng ý kết hợp trang thông tin cập nhật có thể đáp ứng cùng giá trị mà ít chi phí hơn. Nhóm có quyền so sánh giải pháp dựa trên hiệu quả, an toàn và bằng chứng sử dụng.

**Dấu hiệu phần Why tốt:** có mối liên hệ với Who/What, có vấn đề đáng giải quyết, và có thể xác định được tín hiệu để xem lợi ích đã xuất hiện hay chưa.

## 6. Rà soát tính nhất quán của ba thành tố

### 6.1. Những lỗi điển hình

**Lệch vai trò:**

> Là học viên, tôi muốn xem báo cáo doanh thu tất cả lớp, để chốt sổ.

Cần chuyển góc nhìn sang **người phụ trách đối soát** và xác định quyền dữ liệu phù hợp.

**Lệch nhu cầu với lợi ích:**

> Là học viên, tôi muốn đổi ảnh đại diện, để không quên lịch workshop.

Thay ảnh đại diện không trực tiếp giải quyết lịch. Nhóm cần hỏi nguyên nhân quên lịch và xem liệu nhắc lịch có thực sự được cần đến.

**Lợi ích không chứa thông tin:**

> Là người dùng, tôi muốn đăng ký, để có thể đăng ký.

Why cần làm rõ việc tự chọn chỗ, tránh nhắn tin thủ công hoặc nhận xác nhận rõ ràng.

**Khóa thiết kế sớm:**

> Là học viên, tôi muốn nút màu xanh to, để dễ đăng ký.

Hãy tìm hiểu người dùng có thực sự không nhận ra hành động đăng ký không, rồi mô tả nhu cầu nhận biết hành động chính và kiểm tra phương án giao diện.

### 6.2. Bộ ba câu hỏi kiểm tra nhanh

1. **Who:** Người đó có thật sự gặp vấn đề này trong tình huống đã nêu không?
2. **What:** Khi hoàn thành, họ có thể thực hiện hành vi gì mà trước đây chưa làm được?
3. **Why:** Hành vi ấy có thể tạo ra lợi ích nào, và cần bằng chứng gì để kiểm tra?

Nếu một câu trả lời mơ hồ, hãy hỏi người sử dụng hoặc người hiểu nghiệp vụ trước khi ước lượng công việc. Nếu đã rõ nhưng phạm vi lớn, chuyển sang phân rã; nếu cả ba rõ và nhỏ, tiếp tục với tiêu chí chấp nhận và điều kiện chất lượng.

### 6.3. Một số câu chuyện trước và sau khi sửa

| Trước | Vấn đề | Sau |
| --- | --- | --- |
| “Là user, tôi muốn tìm kiếm, để tiện.” | Vai trò và lợi ích quá chung | “Là học viên có lịch bận, tôi muốn lọc buổi theo ngày, để tìm workshop phù hợp.” |
| “Là admin, tôi muốn CRUD workshop, để quản lý.” | Từ ngữ kỹ thuật thay hành vi | “Là điều phối viên, tôi muốn đóng đăng ký buổi đã đủ chỗ, để tránh nhận yêu cầu không thể đáp ứng.” |
| “Là học viên, tôi muốn đăng nhập, để được đăng nhập.” | Why lặp What | “Là học viên đã đăng ký, tôi muốn truy cập yêu cầu của mình an toàn, để kiểm tra trạng thái mà không lộ thông tin người khác.” |
| “Là nhân viên, tôi muốn tối ưu SQL, để trang nhanh.” | Chốt giải pháp | “Là điều phối viên, tôi muốn mở danh sách đăng ký nhanh khi số lượng tăng, để xác nhận chỗ không bị gián đoạn.” |
| “Là học viên, tôi muốn nhắc lịch liên tục.” | Thiếu lợi ích và có nguy cơ làm phiền | “Là học viên đã xác nhận chỗ, tôi muốn nhận nhắc lịch theo kênh đã chọn trước buổi học, để chuẩn bị đến đúng giờ.” |

Các câu “sau” vẫn là giả thuyết cần trao đổi, không phải bằng chứng rằng người dùng luôn có nhu cầu như vậy.

## 7. Quy trình xây story từ một vấn đề thực tế

### Bước 1 – Tìm vấn đề và bằng chứng

Tình huống minh họa: học viên đang đăng ký workshop qua tin nhắn. Họ thường hỏi “còn chỗ không?” và “mình đã được xác nhận chưa?”. Điều phối viên nhập dữ liệu thủ công, có nguy cơ trùng chỗ.

Nhóm nên tìm hiểu:

- Lần gần đây nhất học viên đăng ký đã diễn ra như thế nào?
- Họ phải hỏi ở bước nào, vì thiếu thông tin gì?
- Điều phối viên dựa vào đâu để xác nhận sức chứa?
- “Đăng ký thành công” có nghĩa là **đã gửi yêu cầu** hay **đã có chỗ**?
- Có quy tắc bắt buộc về thanh toán, quyền truy cập hoặc thời hạn hủy không?

Mọi nhận xét ban đầu cần được ghi là **quan sát** hoặc **giả định** cho rõ, tránh chọn giải pháp dựa trên một vài giai thoại.

### Bước 2 – Chọn người dùng

Nếu muốn giảm tình trạng học viên hỏi lại, chọn Who là **học viên chuẩn bị đăng ký workshop**. Nếu muốn giảm công nhập liệu, chọn Who là **điều phối viên** và mô tả công việc của họ. Hai góc nhìn có liên hệ nhưng có thể tạo ra hai story khác nhau.

### Bước 3 – Nêu hành vi

Ví dụ What: **xem những buổi còn chỗ, gửi một yêu cầu và nhận kết quả rõ ràng**. Nếu bản đầu có quy trình duyệt thủ công, What không nên hứa chắc chắn giữ chỗ ngay khi gửi.

### Bước 4 – Nêu lợi ích

Ví dụ Why: **chủ động chọn thời gian và biết yêu cầu đã được ghi nhận mà không phải hỏi lại**. Nhóm có thể theo dõi tỷ lệ hoàn tất gửi yêu cầu và số lần học viên phải liên hệ để kiểm tra trạng thái.

### Bước 5 – Viết câu chuyện

> Là học viên muốn tham gia workshop, tôi muốn xem buổi còn chỗ, gửi yêu cầu đăng ký và thấy trạng thái hiện tại, để chủ động chọn buổi phù hợp và không phải hỏi ban tổ chức liệu yêu cầu đã được nhận hay chưa.

Nếu câu dài do ôm quá nhiều hành vi, nhóm có thể tách thành **xem buổi**, **gửi yêu cầu và nhận kết quả**, **tra cứu yêu cầu đã gửi**, nhưng cần giữ luồng đầu tiên có ý nghĩa sử dụng.

### Bước 6 – Thử câu chuyện qua một tình huống

Mai chọn workshop còn một suất, cung cấp email hợp lệ và gửi yêu cầu. Hệ thống ghi nhận yêu cầu, trả mã tham chiếu cùng trạng thái **chờ xác nhận** nếu ban tổ chức còn phải duyệt. Nếu suất đã hết, hệ thống không hứa có chỗ. Từ ví dụ này nhóm có thể hỏi thêm về đăng ký trùng, nhiều người chọn suất cuối, bảo mật thông tin và quy trình xác nhận.

## 8. 3C: Card, Conversation, Confirmation

Một cách hiểu phổ biến về user story là **3C**:

- **Card:** ghi ngắn gọn nhu cầu để cả nhóm nhớ và theo dõi.
- **Conversation:** người phát triển, người hiểu nghiệp vụ và người dùng trao đổi về mục tiêu, điều kiện, ngoại lệ, giải pháp.
- **Confirmation:** thống nhất ví dụ và tiêu chí để kiểm chứng hành vi.

Card chỉ là **lời mời trao đổi**. Nếu chỉ chuyển một câu viết sẵn giữa các bộ phận mà không nói chuyện về ý nghĩa, nhóm dễ thực hiện đúng chữ nhưng sai kỳ vọng. Confirmation giúp xác nhận cả nhóm hiểu cùng một điều nhưng vẫn phải được bổ sung bằng kiểm thử, chất lượng và phản hồi sau bàn giao.

### 8.1. Mẫu tiêu chí chấp nhận cho một story

Với nhu cầu gửi đăng ký, nhóm có thể thống nhất những tình huống như sau:

~~~gherkin
Tính năng: Gửi yêu cầu đăng ký workshop

  Tình huống: Buổi còn chỗ và thông tin hợp lệ
    Cho trước workshop đang mở đăng ký và còn chỗ
    Khi học viên gửi yêu cầu với thông tin hợp lệ
    Thì hệ thống ghi nhận đúng một yêu cầu đăng ký
    Và hiển thị mã yêu cầu cùng trạng thái hiện tại

  Tình huống: Buổi đã hết chỗ
    Cho trước workshop đã đủ số lượng theo quy tắc nghiệp vụ
    Khi học viên cố gắng đăng ký
    Thì hệ thống không xác nhận chỗ vượt sức chứa
    Và giải thích rõ buổi học đã hết chỗ

  Tình huống: Hệ thống không ghi nhận được yêu cầu
    Cho trước thao tác lưu yêu cầu gặp lỗi
    Khi học viên gửi thông tin đăng ký
    Thì hệ thống không thông báo sai rằng đăng ký thành công
    Và cung cấp hướng xử lý phù hợp
~~~

Đây là các ví dụ minh họa; khi triển khai thật cần làm rõ quy tắc trùng yêu cầu, dữ liệu bắt buộc, kiểm soát cạnh tranh và trạng thái chờ duyệt. Những chi tiết đó không thể được suy ra chỉ từ một dòng Who–What–Why.

### 8.2. Acceptance criteria và Definition of Done

| Khái niệm | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| **Tiêu chí chấp nhận** | Mô tả hành vi đúng của story cụ thể | Buổi hết chỗ không được xác nhận thêm chỗ |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung để Increment được xem là hoàn tất | Mã được tích hợp, kiểm thử cần thiết đạt, review theo quy ước và có thể sử dụng |

Một story chạy được trên máy lập trình viên có thể đáp ứng vài tiêu chí chức năng nhưng **chưa đạt DoD**. Phần mềm phải đủ chất lượng để dùng trong phạm vi đã thỏa thuận trước khi nhóm coi nó là Increment hoàn tất.

## 9. Dùng INVEST để rà soát story

**INVEST** là bộ gợi ý chất lượng thường được dùng khi chuẩn bị story:

| Chữ | Ý nghĩa | Câu hỏi |
| --- | --- | --- |
| **I – Independent** | Tương đối độc lập | Có thể giao một phần giá trị mà không bị chặn bởi quá nhiều story khác không? |
| **N – Negotiable** | Có thể thương lượng | Có thể trao đổi và điều chỉnh cách giải quyết để đạt mục tiêu không? |
| **V – Valuable** | Có giá trị | Ai hưởng lợi và giá trị đó là gì? |
| **E – Estimable** | Có thể ước lượng tương đối | Nhóm hiểu đủ nhu cầu, phạm vi và rủi ro để lên kế hoạch chưa? |
| **S – Small** | Đủ nhỏ | Có thể hoàn thành và nhận phản hồi trong nhịp làm việc phù hợp không? |
| **T – Testable** | Kiểm chứng được | Có ví dụ hoặc tiêu chí giúp xác định hành vi đúng không? |

**Valuable** gắn trực tiếp với phần **Why**. **Testable** dựa vào **What** trong bối cảnh **Who**. **Negotiable** nhắc không khóa phương án thiết kế quá sớm. Các chữ khác giúp nhận ra story còn quá lớn, thiếu hiểu biết hoặc quá nhiều phụ thuộc.

INVEST không phải hệ thống chấm điểm cứng. Một story vẫn có phụ thuộc nghiệp vụ hợp lệ; việc cố chia để “độc lập hoàn toàn” đôi khi làm mất hành vi có ích. Nếu chưa thể ước lượng vì quy tắc chưa rõ, cần trao đổi hoặc thử nghiệm nhỏ trước khi ước lượng, thay vì đoán số.

## 10. Chia story lớn thành lát cắt có giá trị

Một cách tách yếu là **cơ sở dữ liệu → API → giao diện → kiểm thử**, vì người dùng chỉ có thể thử toàn bộ ở cuối. Các tầng kỹ thuật vẫn cần triển khai nhưng nên tổ chức thành **lát cắt dọc** đi qua những phần cần thiết để tạo một hành vi hoàn chỉnh, sử dụng được.

Ví dụ backlog đăng ký workshop:

| Story nhỏ | Who | What | Why |
| --- | --- | --- | --- |
| Tìm buổi | Học viên đang chọn lịch | Xem buổi còn chỗ theo ngày | Biết buổi phù hợp trước khi nhập thông tin |
| Gửi yêu cầu | Học viên đã chọn buổi | Gửi yêu cầu và nhận trạng thái rõ ràng | Không phải nhắn riêng để hỏi đã nhận chưa |
| Tra cứu | Học viên đã gửi | Xem trạng thái của đăng ký thuộc về mình | Biết đã được xác nhận hay đang chờ |
| Xác nhận | Điều phối viên | Xem và xử lý yêu cầu theo sức chứa | Không bỏ sót hoặc xác nhận vượt chỗ |
| Hủy | Học viên không thể tham dự | Hủy đúng chính sách | Nhường chỗ và giảm liên lạc thủ công |

Đây là một **thứ tự tham khảo**, không phải kế hoạch mặc định. Nếu điều phối viên cần duyệt để kiểm soát sức chứa, chức năng nhận yêu cầu và khả năng xử lý tối thiểu có thể phải cùng xuất hiện trong bản thử đầu. Chia nhỏ không có nghĩa giao phần mềm không an toàn hoặc tạo một trải nghiệm dở dang gây hiểu lầm.

### 10.1. Cách chọn lát cắt đầu tiên

Hãy hỏi:

1. Người dùng thực sự **hoàn thành được việc gì** sau lát cắt này?
2. Ai có thể thử nó trong môi trường phù hợp?
3. Điều kiện an toàn và chất lượng nào là bắt buộc?
4. Kết quả nào sẽ xác nhận hoặc bác bỏ Why?
5. Bằng chứng mới sẽ ảnh hưởng thứ tự backlog thế nào?

Một lát cắt nhỏ có thể giữ đủ giao diện, quy tắc nghiệp vụ, lưu trữ và kiểm thử của hành vi đó. Các phần khác được đưa vào vòng tiếp theo theo giá trị và rủi ro, thay vì cố hoàn thành toàn bộ “hệ thống quản lý workshop” mới thử lần đầu.

## 11. Sử dụng cấu trúc story trong Scrum, Kanban và XP

### 11.1. Product Backlog và refinement

Người chịu trách nhiệm ưu tiên backlog cần hiểu **Who** và **Why** để cân nhắc giá trị; Developers cần làm rõ **What**, phạm vi và rủi ro để dự kiến cách thực hiện. Buổi refinement là cơ hội cùng người hiểu nghiệp vụ làm rõ tiêu chí, chia story, phát hiện phụ thuộc và cập nhật thứ tự khi có thông tin mới.

Không phải mọi hạng mục xa trong tương lai đều cần phân tích ngay ở cùng độ sâu. Những story chuẩn bị được thực hiện cần đủ rõ hơn; phần chưa chắc có thể giữ dưới dạng giả thuyết và điều chỉnh khi nhận phản hồi.

### 11.2. Scrum

Scrum **không bắt buộc** các Product Backlog item phải viết theo mẫu user story. Khi nhóm dùng story, ba thành tố giúp lựa chọn những hạng mục phục vụ **Sprint Goal** chung.

Ví dụ Sprint Goal: **“Học viên có thể gửi đăng ký một buổi còn chỗ và hiểu kết quả trong môi trường thử.”** Các story đóng góp vào mục tiêu này cần đi đến **Increment đạt DoD**. Trong Sprint Review, nhóm có thể mời bên liên quan kiểm tra luồng thực tế và trao đổi phản hồi để cập nhật backlog, thay vì chỉ trình bày danh sách task đã hoàn tất.

### 11.3. Kanban

Trong Kanban, story là một đơn vị công việc đi qua các trạng thái theo chính sách nhóm. Những câu chuyện quá lớn hoặc thiếu thông tin thường tạo ra WIP cao, hạng mục chờ lâu, cycle time kéo dài và khó dự báo. Nhìn **work item age**, **cycle time**, **throughput** và lý do bị chặn giúp nhóm quyết định làm rõ hoặc chia nhỏ.

Các chỉ số dòng việc cho biết nhóm giao công việc như thế nào; chúng **không tự chứng minh** lợi ích trong Why. Hoàn tất nhiều story không có ý nghĩa nếu học viên vẫn phải hỏi lại vì không hiểu trạng thái đăng ký.

### 11.4. XP và phản hồi kỹ thuật

Thực hành XP như **pair programming**, **test-driven development**, **continuous integration** và **refactoring** giúp biến những tình huống đã thống nhất thành hành vi chạy được và có thể thay đổi an toàn.

Chẳng hạn, khi làm story gửi đăng ký, hai người cùng phân tích trường hợp người dùng bấm gửi lại do mạng chậm, viết kiểm thử cho việc không tạo yêu cầu trùng theo quy tắc đã thống nhất, triển khai mã, tích hợp và xem lại kết quả. **Kiểm thử chức năng** xác minh hành vi; **phản hồi người dùng** mới giúp đánh giá giá trị trong Why.

## 12. Đo xem lợi ích trong Why có thực sự xuất hiện

User story thường chứa một **giả thuyết giá trị**: nếu người dùng làm được What, họ sẽ đạt được Why. Sau khi giao, nhóm nên kiểm tra thay vì mặc định giả thuyết đúng.

| Mức | Ví dụ | Điều thực sự được chứng minh |
| --- | --- | --- |
| **Hoạt động** | Viết mã, review, chạy thử | Nhóm đã làm công việc |
| **Đầu ra** | Có luồng gửi đăng ký hoạt động | Sản phẩm đã có một khả năng |
| **Kết quả** | Người dùng hoàn tất đăng ký, ít cần hỏi lại | Hành vi hoặc lợi ích có dấu hiệu thay đổi |
| **Tác động** | Ban tổ chức giảm công điều phối và phục vụ tốt hơn | Giá trị rộng hơn, cần quan sát lâu hơn |

Với Why “không cần hỏi ban tổ chức liệu yêu cầu đã được nhận”, nhóm có thể quan sát tỷ lệ hoàn tất, số lần hỏi lại trạng thái, lỗi trùng và cách học viên giải thích thông báo.

**Dữ liệu minh họa:** trong 20 người dùng thử, 17 người gửi được yêu cầu nhưng 8 người vẫn hỏi ban tổ chức xem mình đã có chỗ chưa. Nhóm quan sát **17/20 = 85%** hoàn tất gửi và **8/20 = 40%** hỏi lại trong mẫu. Không thể từ mẫu nhỏ này kết luận tỷ lệ toàn bộ người dùng tương tự hoặc nguyên nhân chắc chắn do thiết kế nút. Nhóm cần phỏng vấn để hiểu nhầm lẫn giữa “đã nhận yêu cầu” và “đã xác nhận chỗ”; có thể ưu tiên cải thiện thông báo trước khi xây thêm tính năng.

Đó là cách **Why dẫn dắt cải tiến**: nếu phần mềm chạy đúng nhưng người dùng chưa nhận được giá trị, nhóm có lý do để thay câu chuyện, tiêu chí chấp nhận hoặc thứ tự backlog.

## 13. Trường hợp không nên ép công việc vào mẫu user story

Backlog có thể chứa việc như vá lỗ hổng, nâng phụ thuộc thư viện, nghiên cứu kiến trúc, cải thiện CI hoặc diễn tập khôi phục. Những hạng mục này có thể thiết yếu cho chất lượng và tốc độ bàn giao nhưng **không có hành vi trực tiếp của người dùng cuối**.

Không nên viết câu giả “Là học viên, tôi muốn nâng phiên bản framework” khi học viên không có nhu cầu đó. Có thể dùng một hạng mục kỹ thuật:

> **Mục tiêu:** loại bỏ khả năng ghi trùng đăng ký khi hai yêu cầu đến gần nhau. **Giá trị/rủi ro:** không xác nhận vượt số chỗ hoặc tạo dữ liệu sai. **Xác nhận hoàn tất:** kiểm thử trường hợp đồng thời và kiểm tra bất biến dữ liệu theo quy tắc đã thống nhất.

Vẫn cần giải thích **vì sao** công việc quan trọng, phạm vi và cách kiểm chứng; chỉ không cần áp dụng khuôn Who–What–Why một cách máy móc.

## 14. Bài thực hành: phân tích, viết và kiểm chứng story

### 14.1. Bối cảnh

Một đơn vị tổ chức workshop nhận đăng ký qua tin nhắn và ghi vào bảng tính. Học viên đôi khi không biết còn chỗ hoặc đã được xác nhận; điều phối viên có thể nhập trùng; giảng viên cần danh sách đáng tin để chuẩn bị buổi học. Đây là **bối cảnh giả định** phục vụ bài tập.

### 14.2. Nhiệm vụ A – Phân tích bốn câu (15 phút)

Cho các câu:

1. “Là user, tôi muốn có nút đăng ký, để ứng dụng đầy đủ tính năng.”
2. “Là admin, tôi muốn database mới, để quản lý dữ liệu.”
3. “Là học viên, tôi muốn xem doanh thu của mọi workshop, để kế toán chốt sổ.”
4. “Là học viên đã gửi yêu cầu, tôi muốn biết đang chờ hay đã được xác nhận, để chủ động sắp xếp thời gian tham gia.”

Hãy đánh dấu Who, What, Why trong mỗi câu. Với các câu 1–3, chỉ ra điểm lệch và viết lại. Với câu 4, xác định ít nhất **hai câu hỏi cần làm rõ**, chẳng hạn cách xác thực người xem và ý nghĩa từng trạng thái. Một câu tương đối tốt vẫn cần Conversation và Confirmation.

### 14.3. Nhiệm vụ B – Viết story cho các vai trò (20 phút)

Viết ít nhất **ba story** với các vai trò hoặc hoàn cảnh khác nhau. Mỗi story phải có:

- Who cụ thể và đúng đối tượng hưởng lợi hoặc trực tiếp thao tác.
- What là hành vi quan sát được.
- Why là lợi ích có lý do.
- Hai câu hỏi làm rõ nghiệp vụ.
- Một tình huống kiểm tra hành vi.

Ví dụ:

> Là điều phối viên workshop, tôi muốn xem yêu cầu đăng ký đang chờ theo từng buổi, để xác nhận đúng chỗ và không bỏ sót người đã gửi.

Hai câu hỏi: **Thế nào là trạng thái chờ?** **Ai được phép xác nhận?** Tình huống thử: điều phối viên được phân quyền xem đúng danh sách chờ và không thể truy cập dữ liệu không thuộc phạm vi phụ trách.

### 14.4. Nhiệm vụ C – Chọn lát cắt (20 phút)

Chọn một story ở nhiệm vụ B:

1. Chia nó nếu có nhiều hành vi độc lập.
2. Viết một tiêu chí chấp nhận thành công và một trường hợp biên.
3. Nêu tiêu chuẩn chất lượng tối thiểu cần có trước khi dùng thử.
4. Chọn phản hồi hoặc chỉ số liên quan trực tiếp tới Why.
5. Giải thích vì sao lát cắt đã chọn có thể nhận phản hồi sớm.

Với story xem trạng thái, một trường hợp biên quan trọng là người dùng cố xem đăng ký của người khác. **Biết mã yêu cầu** không mặc định đồng nghĩa có quyền đọc thông tin riêng tư; phải xác định quy tắc truy cập phù hợp.

### 14.5. Nhiệm vụ D – Điều chỉnh từ dữ liệu (15 phút)

Trong đợt dùng thử giả định với mười học viên:

| Quan sát | Kết quả |
| --- | ---: |
| Hoàn tất gửi yêu cầu | 8/10 |
| Hiểu đúng “đã tiếp nhận” chưa phải “đã có chỗ” | 4/10 |
| Vẫn phải hỏi ban tổ chức sau khi gửi | 6/10 |

Hãy trả lời: **What** có dấu hiệu hoạt động không? **Why** đã được xác nhận chưa? Có thể còn những nguyên nhân nào? Nhóm nên hỏi người dùng điều gì và thay đổi thứ tự backlog ra sao?

**Gợi ý:** trong mẫu, 80% hoàn tất gửi nhưng chỉ 40% hiểu đúng thông báo và 60% phải hỏi lại. Đây là tín hiệu cho thấy phần giao thông tin trạng thái cần xem xét; chưa đủ bằng chứng để khẳng định nguyên nhân chính là màu sắc hay vị trí một nút.

## 15. Thang tự đánh giá

| Tiêu chí | Chưa rõ | Đạt | Vững |
| --- | --- | --- | --- |
| **Who** | Vai trò chung, không có bối cảnh | Biết ai cần và khi nào | Biết phân biệt các vai trò, quyền và tác động |
| **What** | Chỉ là task kỹ thuật hoặc nhiều mục tiêu trộn lẫn | Có hành vi có thể thử | Chọn được lát cắt nhỏ, xử lý phụ thuộc và ngoại lệ |
| **Why** | Lặp What hoặc dùng khẩu hiệu | Giải thích giá trị mong muốn | Có giả thuyết và tín hiệu kiểm chứng giá trị |
| **Nhất quán** | Ba phần không liên quan | Who–What–Why hỗ trợ nhau | Biết giải thích đánh đổi khi thay bối cảnh hoặc giải pháp |
| **Trao đổi** | Chỉ có một câu yêu cầu | Có câu hỏi, ví dụ, tiêu chí chấp nhận | Kiểm tra được với người dùng và tình huống biên |
| **Giao tăng dần** | Chỉ thử được khi xây toàn hệ thống | Có lát cắt đủ nhỏ và đạt chất lượng | Giao sớm, nhận phản hồi, cập nhật backlog có căn cứ |

Nếu chưa đạt Who, What hoặc Why, hãy làm rõ vấn đề trước khi ước lượng. Nếu ba phần hợp lý nhưng quá lớn, hãy chia lát cắt. Nếu đã giao đúng chức năng nhưng người dùng vẫn chưa nhận được lợi ích, hãy kiểm tra lại giả thuyết Why.

## 16. Checklist trước khi đưa một story vào vòng làm việc

- [ ] Người dùng hoặc vai trò được nêu cụ thể trong đúng bối cảnh.
- [ ] Nhóm biết phải hỏi ai để xác minh nhu cầu.
- [ ] What mô tả một hành vi hoặc kết quả có thể quan sát.
- [ ] What không áp đặt giải pháp kỹ thuật chưa có căn cứ.
- [ ] Why là một lợi ích thực tế, không lặp lại What.
- [ ] Ba phần liên kết logic và không mâu thuẫn với quyền truy cập hoặc quy tắc nghiệp vụ.
- [ ] Có thể đưa ra ví dụ thành công và trường hợp ngoại lệ.
- [ ] Có trao đổi với người liên quan và ghi tiêu chí chấp nhận.
- [ ] Story có phạm vi vừa đủ hoặc đã có cách chia thành lát cắt giá trị.
- [ ] Các yêu cầu an toàn, chất lượng và Definition of Done được hiểu rõ.
- [ ] Có tín hiệu phù hợp để đánh giá lợi ích trong Why sau bàn giao.
- [ ] Product Backlog có thể được điều chỉnh khi có phản hồi mới.

**Một user story hữu ích kết nối ba câu hỏi:** **Ai đang cần?** – **Họ muốn làm được gì?** – **Điều đó giúp họ đạt lợi ích nào?** Khi nhóm cùng hiểu ba câu trả lời, họ có cơ sở xây phần mềm chạy được, kiểm tra hành vi với đúng người và điều chỉnh dựa trên bằng chứng. Câu chuyện chỉ là điểm bắt đầu cho đối thoại; năng lực Agile thể hiện ở việc **chuyển kỳ vọng thành kết quả có thể thử, giao sớm và học liên tục**.
